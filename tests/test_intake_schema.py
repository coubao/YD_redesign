import unittest
import zipfile
from types import SimpleNamespace

from intake_schema import (
    CONSULTATION_DECISION_FIELD,
    build_intake_docx,
    parse_intake_form,
    validate_intake_data,
)


class IntakeSchemaTestCase(unittest.TestCase):
    def undergraduate_form(self):
        return {
            'stage': '本科申请',
            'contact': '13900001111',
            'name': '测试同学',
            'current_school': '测试学校',
            'grade': '11年级',
            'graduation_date': '2027-06-30',
            'curriculum': 'AP',
            'gpa': '3.8/4.0',
            'english_level': '托福 105',
            CONSULTATION_DECISION_FIELD['name']: CONSULTATION_DECISION_FIELD['options'][1],
        }

    def test_decision_status_is_parsed_and_validated(self):
        data = parse_intake_form(self.undergraduate_form())

        self.assertEqual(data['schema_version'], 3)
        self.assertEqual(
            data[CONSULTATION_DECISION_FIELD['name']],
            CONSULTATION_DECISION_FIELD['options'][1],
        )
        self.assertEqual(validate_intake_data(data), [])

    def test_decision_status_is_required(self):
        form = self.undergraduate_form()
        form[CONSULTATION_DECISION_FIELD['name']] = ''

        errors = validate_intake_data(parse_intake_form(form))

        self.assertIn('请选择咨询后的当前状态。', errors)

    def test_decision_status_rejects_unknown_option(self):
        form = self.undergraduate_form()
        form[CONSULTATION_DECISION_FIELD['name']] = '其他未经定义的选项'

        errors = validate_intake_data(parse_intake_form(form))

        self.assertIn('请选择有效的咨询后状态。', errors)

    def test_docx_contains_decision_status(self):
        intake_data = parse_intake_form(self.undergraduate_form())
        booking = SimpleNamespace(
            id=1,
            booking_date='2026-09-20',
            time_slot='11:00-12:00',
            stage='本科申请',
            contact='13900001111',
        )

        document = build_intake_docx(booking, intake_data)
        with zipfile.ZipFile(document) as archive:
            document_xml = archive.read('word/document.xml').decode('utf-8')

        self.assertIn('咨询后计划', document_xml)
        self.assertIn(CONSULTATION_DECISION_FIELD['options'][1], document_xml)


if __name__ == '__main__':
    unittest.main()
