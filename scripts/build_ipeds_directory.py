"""Build the public college directory from the official IPEDS HD2024 file."""

import argparse
import csv
import io
import zipfile
from pathlib import Path
from urllib.request import urlopen


SOURCE_URL = 'https://nces.ed.gov/ipeds/datacenter/data/HD2024.zip'
OUTPUT = Path(__file__).resolve().parents[1] / 'data' / 'ipeds_2024_directory.csv'
FIELDS = ('unitid', 'name', 'city', 'state', 'control', 'website')


def build(source_zip):
    with zipfile.ZipFile(io.BytesIO(source_zip)) as archive:
        with archive.open('HD2024.csv') as source:
            rows = csv.DictReader(io.TextIOWrapper(source, encoding='utf-8-sig'))
            institutions = []
            for row in rows:
                if not (row['ICLEVEL'] == '1' and row['DEGGRANT'] == '1'
                        and row['CYACTIVE'] == '1'
                        and row['CONTROL'] in ('1', '2')
                        and row['SECTOR'] in ('1', '2')):
                    continue
                website = row['WEBADDR'].strip()
                if website and not website.startswith(('http://', 'https://')):
                    website = 'https://' + website
                institutions.append({
                    'unitid': row['UNITID'].strip(),
                    'name': row['INSTNM'].strip(),
                    'city': row['CITY'].strip(),
                    'state': row['STABBR'].strip(),
                    'control': 'public' if row['CONTROL'] == '1' else 'private',
                    'website': website,
                })

    institutions.sort(key=lambda item: (item['name'].casefold(), item['unitid']))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open('w', newline='', encoding='utf-8') as destination:
        writer = csv.DictWriter(destination, fieldnames=FIELDS, lineterminator='\n')
        writer.writeheader()
        writer.writerows(institutions)
    print(f'Wrote {len(institutions)} institutions to {OUTPUT}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-zip', type=Path,
                        help='Use an already downloaded official HD2024.zip file')
    args = parser.parse_args()
    build(args.source_zip.read_bytes() if args.source_zip else urlopen(SOURCE_URL).read())
