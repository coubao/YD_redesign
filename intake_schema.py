import io
import json
import zipfile
from xml.sax.saxutils import escape


GRADE_OPTIONS = ['6-8年级', '9年级', '10年级', '11年级', '12年级']
CURRICULUM_OPTIONS = ['体制内', 'AP', 'IB', 'A-Level', '美高', '其他']
DECISION_MAKER_OPTIONS = ['父亲', '母亲', '双方共同', '其他']
DECISION_STATUS_OPTIONS = ['初步了解', '多方对比', '准备签约', '已有机构但需把关']
TREND_OPTIONS = ['上升', '稳定', '波动', '下滑']
YES_NO_UNSURE_OPTIONS = ['是', '否', '不确定']
TARGET_REGION_OPTIONS = ['美国', '英国', '香港', '新加坡', '加拿大', '澳大利亚', '混申']
APPLICATION_STAGE_OPTIONS = ['本科', '硕士', '高中', '转学', '其他']
SCHOOL_LEVEL_OPTIONS = ['Top20', 'Top30', 'Top50', 'G5', '港前三', '新二', '其他']
CURVE_STRATEGY_OPTIONS = ['接受', '不接受', '需要解释']
STUDENT_WILL_OPTIONS = ['明确', '模糊', '与家长不同', '需要探索']
COUNTRY_PREFERENCE_OPTIONS = ['已定', '摇摆', '需要比较']
BUDGET_OPTIONS = ['充足', '需控制', '未评估', '其他']
SERVICE_BUDGET_OPTIONS = ['可接受高端申请', '只考虑规划', '需比较价格']
CONCERN_OPTIONS = ['录取结果', '专业选择', '活动规划', '成绩不足', '文书质量', '已有机构不放心']
SERVICE_MODE_OPTIONS = ['申请全程', '年度陪跑', '单项把关', '暂不确定']
DECISION_TIMELINE_OPTIONS = ['咨询后1周内', '1个月内', '暑假前后', '申请季前', '不确定']
SECOND_CONSULTATION_OPTIONS = ['是', '否', '看诊断结果']
MATERIAL_OPTIONS = [
    '近2年成绩单或校内成绩截图',
    '当前课程表/未来选课计划',
    '托福/雅思/多邻国/SAT/ACT/AP/IB/AL成绩截图',
    '活动、竞赛、奖项清单',
    '目标学校/专业清单',
    '已有机构方案、合同或服务内容说明',
    '孩子本人自述/简历/作品集/论文/科研报告',
]


INTAKE_SECTIONS = [
    {
        'key': 'basic',
        'title': '一、学生与家庭基本信息',
        'description': '用于确认学生背景、家庭决策节奏和现有服务状态。',
        'fields': [
            {'name': 'student_name', 'label': '学生姓名', 'type': 'text'},
            {'name': 'english_name', 'label': '英文名/昵称', 'type': 'text'},
            {'name': 'current_grade', 'label': '目前年级', 'type': 'select', 'options': GRADE_OPTIONS},
            {'name': 'graduation_year', 'label': '毕业年份', 'type': 'text'},
            {'name': 'current_school', 'label': '目前学校', 'type': 'text'},
            {'name': 'city', 'label': '所在城市', 'type': 'text'},
            {'name': 'curriculum', 'label': '课程体系', 'type': 'multi_checkbox', 'options': CURRICULUM_OPTIONS},
            {'name': 'curriculum_other', 'label': '课程体系补充', 'type': 'text'},
            {'name': 'agency_status', 'label': '是否已有机构', 'type': 'select', 'options': ['无', '有']},
            {'name': 'agency_name', 'label': '机构名称', 'type': 'text'},
            {'name': 'parent_contact', 'label': '家长联系人', 'type': 'text'},
            {'name': 'phone_wechat', 'label': '联系电话/微信', 'type': 'text'},
            {'name': 'decision_maker', 'label': '家庭决策人', 'type': 'select', 'options': DECISION_MAKER_OPTIONS},
            {'name': 'decision_status', 'label': '决策状态', 'type': 'select', 'options': DECISION_STATUS_OPTIONS},
        ],
    },
    {
        'key': 'academic',
        'title': '二、当前学术与成绩情况',
        'description': '用于判断当前学术竞争力、短板和成绩趋势。',
        'fields': [
            {'name': 'gpa', 'label': '校内GPA/均分', 'type': 'text'},
            {'name': 'school_rank', 'label': '校内排名/百分位', 'type': 'text'},
            {'name': 'strength_subjects', 'label': '核心强项科目', 'type': 'text'},
            {'name': 'weak_subjects', 'label': '明显短板科目', 'type': 'text'},
            {'name': 'grade_trend', 'label': '近一年成绩趋势', 'type': 'select', 'options': TREND_OPTIONS},
            {'name': 'tutoring_status', 'label': '是否有补课', 'type': 'text'},
            {'name': 'transcript_available', 'label': '成绩单是否可提供', 'type': 'select', 'options': ['可', '暂不可']},
            {'name': 'school_outcome_known', 'label': '学校升学数据是否了解', 'type': 'select', 'options': ['了解', '不清楚']},
        ],
    },
    {
        'key': 'testing',
        'title': '三、语言、标化与课程选择',
        'description': '用于判断考试节奏、课程选择和后续备考安排。',
        'fields': [
            {'name': 'language_exam_type', 'label': '托福/雅思/多邻国考试类型', 'type': 'text'},
            {'name': 'language_current_score', 'label': '当前分数', 'type': 'text'},
            {'name': 'language_target_score', 'label': '目标分数', 'type': 'text'},
            {'name': 'sat_current_score', 'label': 'SAT/ACT当前分数', 'type': 'text'},
            {'name': 'sat_target_score', 'label': 'SAT/ACT目标分数', 'type': 'text'},
            {'name': 'advanced_subjects', 'label': 'AP/IB/AL科目', 'type': 'textarea'},
            {'name': 'scored_subjects', 'label': '已出分科目', 'type': 'textarea'},
            {'name': 'future_courses', 'label': '未来选课计划', 'type': 'textarea'},
            {'name': 'need_course_advice', 'label': '是否需要选课建议', 'type': 'select', 'options': YES_NO_UNSURE_OPTIONS},
        ],
    },
    {
        'key': 'goals',
        'title': '五、目标国家、学校、专业与职业偏好',
        'description': '用于判断申请方向、专业适配度和选校策略。',
        'fields': [
            {'name': 'target_regions', 'label': '目标国家/地区', 'type': 'multi_checkbox', 'options': TARGET_REGION_OPTIONS},
            {'name': 'application_stage', 'label': '申请阶段', 'type': 'select', 'options': APPLICATION_STAGE_OPTIONS},
            {'name': 'target_school_level', 'label': '目标学校层级', 'type': 'multi_checkbox', 'options': SCHOOL_LEVEL_OPTIONS},
            {'name': 'curve_strategy', 'label': '是否接受曲线策略', 'type': 'select', 'options': CURVE_STRATEGY_OPTIONS},
            {'name': 'intended_major', 'label': '意向专业', 'type': 'text'},
            {'name': 'rejected_major', 'label': '不接受专业', 'type': 'text'},
            {'name': 'career_direction', 'label': '职业方向', 'type': 'textarea'},
            {'name': 'parent_expectation', 'label': '家长期望', 'type': 'textarea'},
            {'name': 'student_preference', 'label': '孩子本人意愿', 'type': 'select', 'options': STUDENT_WILL_OPTIONS},
            {'name': 'country_preference', 'label': '国家选择倾向', 'type': 'select', 'options': COUNTRY_PREFERENCE_OPTIONS},
        ],
    },
    {
        'key': 'budget',
        'title': '六、家庭预算、服务需求与决策节奏',
        'description': '用于判断服务匹配度和后续沟通优先级。',
        'fields': [
            {'name': 'undergrad_budget', 'label': '本科总预算', 'type': 'select', 'options': BUDGET_OPTIONS},
            {'name': 'service_budget', 'label': '服务预算', 'type': 'select', 'options': SERVICE_BUDGET_OPTIONS},
            {'name': 'biggest_concerns', 'label': '最担心的问题', 'type': 'multi_checkbox', 'options': CONCERN_OPTIONS},
            {'name': 'expected_service', 'label': '期望服务方式', 'type': 'select', 'options': SERVICE_MODE_OPTIONS},
            {'name': 'decision_timeline', 'label': '最快决策时间', 'type': 'select', 'options': DECISION_TIMELINE_OPTIONS},
            {'name': 'second_consultation', 'label': '是否愿意二次沟通', 'type': 'select', 'options': SECOND_CONSULTATION_OPTIONS},
        ],
    },
]

ACADEMIC_RECORD_FIELDS = [
    ('course', '科目/课程'),
    ('current_score', '当前成绩'),
    ('highest_score', '最高成绩'),
    ('exam_time', '考试/学期时间'),
    ('notes', '备注'),
]
TESTING_RECORD_FIELDS = [
    ('exam_course', '考试/课程'),
    ('tested_time', '已考时间'),
    ('current_score', '当前分数'),
    ('target_score', '目标分数'),
    ('next_exam', '下一次考试'),
    ('prep_plan', '备考安排'),
]
ACTIVITY_CATEGORIES = [
    {'key': 'competition', 'label': '竞赛'},
    {'key': 'research', 'label': '科研/论文'},
    {'key': 'leadership', 'label': '社团/领导力'},
    {'key': 'volunteer', 'label': '公益/志愿'},
    {'key': 'arts_sports', 'label': '艺术/体育'},
    {'key': 'other', 'label': '其他'},
]
ACTIVITY_FIELDS = [
    ('project_name', '项目名称'),
    ('time', '时间'),
    ('role', '角色/职责'),
    ('result', '成果/奖项'),
    ('major_relation', '与专业方向关系'),
]


def load_intake_data(raw_data):
    if not raw_data:
        return {}
    try:
        data = json.loads(raw_data)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def _collect_records(form, prefix, fields, count):
    records = []
    for index in range(count):
        row = {}
        for key, _label in fields:
            row[key] = form.get(f'{prefix}_{index}_{key}', '').strip()
        if any(row.values()):
            records.append(row)
    return records


def _collect_activities(form):
    activities = {}
    for category in ACTIVITY_CATEGORIES:
        item = {}
        for key, _label in ACTIVITY_FIELDS:
            item[key] = form.get(f'activity_{category["key"]}_{key}', '').strip()
        if any(item.values()):
            activities[category['key']] = item
    return activities


def parse_intake_form(form):
    data = {}
    for section in INTAKE_SECTIONS:
        for field in section['fields']:
            if field['type'] == 'multi_checkbox':
                data[field['name']] = [value.strip() for value in form.getlist(field['name']) if value.strip()]
            else:
                data[field['name']] = form.get(field['name'], '').strip()

    data['academic_records'] = _collect_records(form, 'academic', ACADEMIC_RECORD_FIELDS, 4)
    data['testing_records'] = _collect_records(form, 'testing', TESTING_RECORD_FIELDS, 4)
    data['activities'] = _collect_activities(form)
    data['consult_questions'] = [
        form.get(f'consult_question_{index}', '').strip()
        for index in range(1, 4)
        if form.get(f'consult_question_{index}', '').strip()
    ]
    data['materials'] = [value.strip() for value in form.getlist('materials') if value.strip()]
    data['materials_note'] = form.get('materials_note', '').strip()
    return data


def format_intake_value(value):
    if isinstance(value, list):
        return '、'.join(value)
    if isinstance(value, dict):
        return '；'.join(f'{k}: {v}' for k, v in value.items() if v)
    return str(value or '')


def _clean_xml_text(value):
    text = format_intake_value(value)
    return ''.join(
        ch for ch in text
        if ch in '\t\n\r' or ord(ch) >= 32
    )


def _xml_text(value):
    return escape(_clean_xml_text(value))


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


def _section_table(section, data):
    rows = [['字段', '家长填写内容']]
    for field in section['fields']:
        rows.append([field['label'], format_intake_value(data.get(field['name']))])
    return _table(rows)


def build_intake_docx(booking, intake_data):
    body = [
        _paragraph('咨询前信息采集表', 'Title'),
        _paragraph('Grace升学战略诊断会 | 家长填写', 'Subtitle'),
        _paragraph(f'预约编号：#{booking.id}'),
        _paragraph(f'预约时间：{booking.booking_date} {booking.time_slot}'),
        _paragraph(f'基础预约信息：{booking.name} / {booking.contact} / {booking.target_country} / {booking.stage}'),
        _paragraph('填写说明', 'Heading1'),
        _paragraph('请家长在咨询前24小时完成填写；如信息不完整，可先填写已知部分。本表用于帮助顾问在咨询前建立初步判断，提高1小时诊断效率。'),
    ]

    for section in INTAKE_SECTIONS:
        body.append(_paragraph(section['title'], 'Heading1'))
        body.append(_paragraph(section['description']))
        body.append(_section_table(section, intake_data))

        if section['key'] == 'academic':
            rows = [['科目/课程', '当前成绩', '最高成绩', '考试/学期时间', '备注']]
            for row in intake_data.get('academic_records', []):
                rows.append([row.get(key, '') for key, _label in ACADEMIC_RECORD_FIELDS])
            body.append(_paragraph('成绩明细', 'Heading2'))
            body.append(_table(rows))

        if section['key'] == 'testing':
            rows = [['考试/课程', '已考时间', '当前分数', '目标分数', '下一次考试', '备考安排']]
            for row in intake_data.get('testing_records', []):
                rows.append([row.get(key, '') for key, _label in TESTING_RECORD_FIELDS])
            body.append(_paragraph('考试与课程明细', 'Heading2'))
            body.append(_table(rows))

    body.append(_paragraph('四、活动、竞赛、奖项与特殊经历', 'Heading1'))
    rows = [['类别', '项目名称', '时间', '角色/职责', '成果/奖项', '与专业方向关系']]
    activities = intake_data.get('activities', {})
    for category in ACTIVITY_CATEGORIES:
        item = activities.get(category['key'], {})
        rows.append([category['label']] + [item.get(key, '') for key, _label in ACTIVITY_FIELDS])
    body.append(_table(rows))
    body.append(_paragraph('提醒：请优先填写真实投入较多、能讲出过程和成果的经历；只付费参加但缺少个人贡献的项目，请如实标注。'))

    body.append(_paragraph('七、家长最希望本次咨询解决的三个问题', 'Heading1'))
    question_rows = [['序号', '问题描述']]
    for index in range(3):
        questions = intake_data.get('consult_questions', [])
        question_rows.append([str(index + 1), questions[index] if index < len(questions) else ''])
    body.append(_table(question_rows))

    body.append(_paragraph('八、资料上传清单', 'Heading1'))
    material_rows = [['资料项', '是否已准备']]
    selected_materials = set(intake_data.get('materials', []))
    for material in MATERIAL_OPTIONS:
        material_rows.append([material, '已准备' if material in selected_materials else ''])
    body.append(_table(material_rows))
    if intake_data.get('materials_note'):
        body.append(_paragraph('资料补充说明', 'Heading2'))
        body.append(_paragraph(intake_data.get('materials_note')))

    body.append('<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1080" w:right="1080" w:bottom="1080" w:left="1080" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>')
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
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:color w:val="0F766E"/><w:sz w:val="24"/></w:rPr></w:style>
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
