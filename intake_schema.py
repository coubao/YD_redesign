import io
import json
import zipfile
from xml.sax.saxutils import escape


APPLICATION_STAGES = ['本科申请', '硕士申请', '博士申请']

UNDERGRADUATE_FIELDS = [
    {'name': 'name', 'label': '姓名', 'type': 'text', 'required': True, 'placeholder': '请输入学生姓名'},
    {'name': 'current_school', 'label': '目前就读的学校', 'type': 'text', 'required': True, 'placeholder': '请输入学校全称'},
    {'name': 'grade', 'label': '年级', 'type': 'text', 'required': True, 'placeholder': '例如：11年级'},
    {'name': 'graduation_date', 'label': '毕业日期', 'type': 'date', 'required': True},
    {
        'name': 'curriculum',
        'label': '校园课程系统',
        'type': 'select',
        'required': True,
        'options': ['公立', 'AP', 'IB', 'A-Level', '其他'],
    },
    {'name': 'gpa', 'label': '学校内的平均绩点', 'type': 'text', 'required': True, 'placeholder': '例如：3.8/4.0 或 90/100'},
    {'name': 'english_level', 'label': '英语水平（托福/雅思）', 'type': 'text', 'required': True, 'placeholder': '请注明考试类型和成绩'},
    {'name': 'arts_sports', 'label': '艺术或体育才能', 'type': 'textarea', 'placeholder': '请描述项目、投入时间和当前水平'},
    {'name': 'activities', 'label': '学校内外的课外活动', 'type': 'textarea', 'placeholder': '请描述主要活动、角色和持续时间'},
    {'name': 'awards_experience', 'label': '活动/竞赛中的经历和奖项', 'type': 'textarea', 'placeholder': '请描述个人贡献、成果和奖项'},
    {'name': 'target_region', 'label': '申请的目标国家/地区', 'type': 'text', 'placeholder': '例如：美国、英国、香港、新加坡'},
    {'name': 'target_school', 'label': '目标学校', 'type': 'textarea', 'placeholder': '可填写学校清单或目标梯度'},
    {'name': 'career_direction', 'label': '期望的职业方向', 'type': 'textarea', 'placeholder': '如暂不明确，也可填写正在考虑的方向'},
    {'name': 'consultation_questions', 'label': '需要咨询的问题', 'type': 'textarea', 'placeholder': '请列出本次最希望解决的问题'},
]

GRADUATE_FIELDS = [
    {'name': 'name', 'label': '姓名', 'type': 'text', 'required': True, 'placeholder': '请输入学生姓名'},
    {'name': 'current_school', 'label': '现就读学校', 'type': 'text', 'required': True, 'placeholder': '请输入学校全称'},
    {'name': 'major', 'label': '就读专业', 'type': 'text', 'required': True, 'placeholder': '请填写专业全称'},
    {'name': 'graduation_date', 'label': '毕业时间', 'type': 'date', 'required': True},
    {'name': 'gpa', 'label': '校内GPA', 'type': 'text', 'required': True, 'placeholder': '例如：3.7/4.0 或 88/100'},
    {
        'name': 'english_level',
        'label': '英文能力（托福/雅思/GRE/国内四六级）',
        'type': 'text',
        'required': True,
        'placeholder': '请注明考试类型和成绩',
    },
    {'name': 'ta_ra_experience', 'label': '校内外TA/RA经历', 'type': 'textarea', 'required': True, 'placeholder': '如暂无经历，请填写“暂无”'},
    {'name': 'research_internship', 'label': '科研实习经历', 'type': 'textarea', 'placeholder': '请描述项目、职责、成果和持续时间'},
    {'name': 'target_region', 'label': '申请目标国家/地区', 'type': 'text', 'placeholder': '例如：美国、英国、香港、新加坡'},
    {'name': 'target_school', 'label': '目标学校', 'type': 'textarea', 'placeholder': '可填写学校清单或目标梯度'},
    {'name': 'target_major', 'label': '目标专业方向', 'type': 'textarea', 'placeholder': '请填写拟申请方向和关注的细分领域'},
    {
        'name': 'phd_intent',
        'label': '是否有读博意向',
        'type': 'select',
        'options': ['是', '否', '暂未确定'],
    },
    {
        'name': 'return_to_china',
        'label': '是否毕业后回国工作',
        'type': 'select',
        'options': ['是', '否', '暂未确定'],
    },
    {'name': 'consultation_questions', 'label': '需要咨询的问题', 'type': 'textarea', 'placeholder': '请列出本次最希望解决的问题'},
]

INTAKE_FORM_CONFIGS = {
    '本科申请': {
        'key': 'undergraduate',
        'title': '本科项目申请资料',
        'description': '前7项为必填项，后7项为选填项。',
        'fields': UNDERGRADUATE_FIELDS,
    },
    '硕士申请': {
        'key': 'graduate',
        'title': '硕士项目申请资料',
        'description': '前7项为必填项，后7项为选填项。',
        'fields': GRADUATE_FIELDS,
    },
    '博士申请': {
        'key': 'doctoral',
        'title': '博士项目申请资料',
        'description': '前7项为必填项，后7项为选填项。',
        'fields': GRADUATE_FIELDS,
    },
}


def get_intake_config(stage):
    return INTAKE_FORM_CONFIGS.get(stage)


def load_intake_data(raw_data):
    if not raw_data:
        return {}
    try:
        data = json.loads(raw_data)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def parse_intake_form(form):
    stage = form.get('stage', '').strip()
    config = get_intake_config(stage)
    data = {
        'schema_version': 2,
        'application_stage': stage,
        'contact': form.get('contact', '').strip(),
    }
    if not config:
        return data

    for field in config['fields']:
        data[field['name']] = form.get(field['name'], '').strip()
    return data


def validate_intake_data(data):
    errors = []
    stage = data.get('application_stage', '')
    config = get_intake_config(stage)
    if not config:
        return ['请选择申请阶段。']

    if not str(data.get('contact', '')).strip():
        errors.append('请填写联系方式，以便接收腾讯会议信息。')

    for field in config['fields']:
        if field.get('required') and not str(data.get(field['name'], '')).strip():
            errors.append(f'请填写必填项：{field["label"]}。')
    return errors


def format_intake_value(value):
    if isinstance(value, list):
        return '、'.join(value)
    if isinstance(value, dict):
        return '；'.join(f'{key}: {item}' for key, item in value.items() if item)
    return str(value or '')


def _clean_xml_text(value):
    text = format_intake_value(value)
    return ''.join(ch for ch in text if ch in '\t\n\r' or ord(ch) >= 32)


def _run_xml(text):
    parts = _clean_xml_text(text).splitlines() or ['']
    run_parts = []
    for index, part in enumerate(parts):
        if index:
            run_parts.append('<w:br/>')
        run_parts.append(f'<w:t xml:space="preserve">{escape(part)}</w:t>')
    return '<w:r>' + ''.join(run_parts) + '</w:r>'


def _paragraph(text='', style=None):
    style_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ''
    return f'<w:p>{style_xml}{_run_xml(text)}</w:p>'


def _table(rows):
    if not rows:
        return ''
    max_cols = max(len(row) for row in rows)
    col_width = max(1200, int(9000 / max_cols))
    grid = ''.join(f'<w:gridCol w:w="{col_width}"/>' for _ in range(max_cols))
    row_xml = []
    for row_index, row in enumerate(rows):
        cells = []
        for col_index in range(max_cols):
            text = row[col_index] if col_index < len(row) else ''
            shade = '<w:shd w:fill="EAF4F2"/>' if row_index == 0 else ''
            cells.append(
                '<w:tc>'
                f'<w:tcPr><w:tcW w:w="{col_width}" w:type="dxa"/>{shade}</w:tcPr>'
                f'{_paragraph(text)}'
                '</w:tc>'
            )
        row_xml.append(f'<w:tr>{"".join(cells)}</w:tr>')
    return (
        '<w:tbl>'
        '<w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblBorders>'
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
        '</w:tblBorders></w:tblPr>'
        f'<w:tblGrid>{grid}</w:tblGrid>'
        f'{"".join(row_xml)}'
        '</w:tbl>'
    )


def _legacy_rows(intake_data):
    ignored_keys = {'schema_version', 'application_stage', 'contact'}
    rows = [['字段', '家长填写内容']]
    for key, value in intake_data.items():
        if key in ignored_keys:
            continue
        rows.append([key, format_intake_value(value)])
    return rows


def build_intake_docx(booking, intake_data):
    stage = intake_data.get('application_stage') or booking.stage
    config = get_intake_config(stage)
    body = [
        _paragraph('咨询预约资料', 'Title'),
        _paragraph('超哥留学 & Grace | 腾讯会议咨询', 'Subtitle'),
        _paragraph(f'预约编号：#{booking.id}'),
        _paragraph(f'预约时间：{booking.booking_date} {booking.time_slot}'),
        _paragraph(f'申请阶段：{stage}'),
        _paragraph(f'联系方式：{intake_data.get("contact") or booking.contact}'),
        _paragraph('填写说明', 'Heading1'),
        _paragraph('前7项申请资料为必填项，后7项为选填项。填写越详细，咨询效果越好。'),
    ]

    if config:
        rows = [['序号', '资料项目', '家长填写内容', '填写要求']]
        for index, field in enumerate(config['fields'], start=1):
            rows.append([
                str(index),
                field['label'],
                format_intake_value(intake_data.get(field['name'])),
                '必填' if field.get('required') else '选填',
            ])
        body.append(_paragraph(config['title'], 'Heading1'))
        body.append(_table(rows))
    else:
        body.append(_paragraph('历史预约资料', 'Heading1'))
        body.append(_table(_legacy_rows(intake_data)))

    body.append(
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1080" w:right="1080" w:bottom="1080" w:left="1080" '
        'w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body>{"".join(body)}</w:body></w:document>'
    )
    styles_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:rPr><w:rFonts w:ascii="Arial" w:eastAsia="Microsoft YaHei"/><w:sz w:val="22"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:color w:val="061A3A"/><w:sz w:val="40"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:rPr><w:color w:val="0F766E"/><w:sz w:val="24"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:color w:val="061A3A"/><w:sz w:val="28"/></w:rPr></w:style>
</w:styles>'''
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>'''
    rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''
    doc_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'''

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as docx:
        docx.writestr('[Content_Types].xml', content_types)
        docx.writestr('_rels/.rels', rels)
        docx.writestr('word/_rels/document.xml.rels', doc_rels)
        docx.writestr('word/document.xml', document_xml)
        docx.writestr('word/styles.xml', styles_xml)
    buffer.seek(0)
    return buffer
