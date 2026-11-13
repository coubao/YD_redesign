"""Extract a small, factual school snapshot from supplied MHTML archives.

Requires lxml for this offline build step; the website only reads the JSON output.
No article text, rankings, images, or third-party markup is copied.
"""

import argparse
import csv
import json
import re
from email import policy
from email.parser import BytesParser
from pathlib import Path

from lxml import html


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'data' / 'ipeds_2024_directory.csv'
OUTPUT = ROOT / 'data' / 'school_profiles.json'


def text(node):
    return ' '.join(node.text_content().split()) if node is not None else ''


def first(tree, xpath, **kwargs):
    nodes = tree.xpath(xpath, **kwargs)
    return nodes[0] if nodes else None


def number(value):
    cleaned = value.replace(',', '').replace('$', '').replace('%', '').strip()
    return float(cleaned) if '.' in cleaned else int(cleaned)


def kpi(tree, label):
    label_node = first(tree, '//p[@class="fp2-kpi__label" and text()=$label]', label=label)
    if label_node is None:
        return None
    value = first(label_node, './following-sibling::p[@class="fp2-kpi__value"]')
    return number(text(value)) if value is not None else None


def extract(path, directory):
    message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    match = re.search(r'/school/(\d+)', message.get('Snapshot-Content-Location', ''))
    if not match or match.group(1) not in directory:
        raise ValueError(f'Unknown school ID: {path.name}')
    school = directory[match.group(1)]
    part = next((part for part in message.walk() if part.get_content_type() == 'text/html'), None)
    if part is None:
        raise ValueError(f'No HTML page: {path.name}')
    tree = html.fromstring(part.get_payload(decode=True))
    heading = first(tree, '//h1[@id="school-name"]')
    if heading is None:
        raise ValueError(f'No school heading: {path.name}')
    chinese_name = (heading.text or '').strip()
    english_name = text(first(heading, './span[@lang="en"]'))
    if not chinese_name or not english_name:
        raise ValueError(f'Incomplete school heading: {path.name}')

    cost_section = first(tree, '//section[@id="sec-cost"]')
    cost_label = text(first(cost_section, './/p[@class="fp2-label"]'))
    cost_total = text(first(cost_section, './/p[@class="fp2-costcard__total"]'))
    tuition = {}
    for row in cost_section.xpath('.//div[@class="fp2-costcard"]//dl/div'):
        label = text(first(row, './dt'))
        value = text(first(row, './dd'))
        if label and value:
            tuition[label] = number(value)
    majors = []
    for row in tree.xpath('//section[@id="sec-majors"]//div[@class="fp2-hbar"]')[:3]:
        majors.append({'name': text(first(row, './span')), 'graduates': number(text(first(row, './strong')))})
    international = {}
    for figure in tree.xpath('//section[@id="sec-intl"]//figure[contains(@class,"fp2-trend")]'):
        label = text(first(figure, './figcaption/span'))
        value = text(first(figure, './figcaption/strong'))
        if label in ('本科生', '研究生') and value:
            international['undergraduate' if label == '本科生' else 'graduate'] = number(value)
    if len(majors) != 3 or len(international) != 2:
        raise ValueError(f'Incomplete major or international data: {path.name}')
    test_scores = {}
    for tile in tree.xpath('//section[@id="sec-score"]//div[@class="fp2-tile"]'):
        label = text(first(tile, './span'))
        value = text(first(tile, './strong'))
        if label in ('SAT 总分', 'ACT 综合') and re.fullmatch(r'\d{1,4}[–-]\d{1,4}', value):
            test_scores['sat' if label == 'SAT 总分' else 'act'] = value

    return {
        'unitid': school['unitid'],
        'name_zh': chinese_name,
        'name_en': english_name,
        'city': school['city'],
        'state': school['state'],
        'control': school['control'],
        'website': school['website'],
        'snapshot_date': message['Date'][:16],
        'admission_rate_2025': kpi(tree, '录取率'),
        'undergraduates_2025': kpi(tree, '本科生'),
        'four_year_graduation_rate_2025': kpi(tree, '毕业率'),
        'annual_cost_2025': number(cost_total),
        'annual_cost_label': '外州学费＋住宿生活费' if '外州' in cost_label else '学费＋住宿生活费',
        'tuition_2025': tuition,
        'international_share_2025': international,
        'historical_test_score_range': test_scores,
        'top_bachelor_majors_2025': majors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive_dir', type=Path)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    with DIRECTORY.open(newline='', encoding='utf-8') as source:
        directory = {row['unitid']: row for row in csv.DictReader(source)}
    profiles = {}
    files = sorted(args.archive_dir.glob('*2027排名、录取率、学费与专业*.mhtml'))
    if not files:
        raise SystemExit('No matching MHTML files found')
    for path in files:
        profile = extract(path, directory)
        unitid = profile['unitid']
        if unitid in profiles:
            raise ValueError(f'Duplicate school ID: {unitid}')
        profiles[unitid] = profile
    ordered = sorted(profiles.values(), key=lambda profile: profile['name_en'].casefold())
    args.output.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {len(ordered)} school profiles to {args.output}')


if __name__ == '__main__':
    main()
