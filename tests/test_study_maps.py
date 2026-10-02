import json
import unittest
from html import unescape
from pathlib import Path

from app import app, load_us_undergraduate_universities


class StudyMapsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_path = (
            Path(app.static_folder)
            / 'data'
            / 'us-undergraduate-universities.json'
        )
        cls.payload = json.loads(cls.data_path.read_text(encoding='utf-8'))

    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_us_university_data_is_complete_and_unique(self):
        universities = self.payload['universities']

        self.assertEqual(len(universities), 77)
        self.assertEqual(len({school['id'] for school in universities}), 77)
        self.assertEqual(len({school['name_en'] for school in universities}), 77)
        self.assertEqual(self.payload['meta']['university_count'], 77)
        self.assertEqual(
            self.payload['meta']['state_count'],
            len({school['state_cn'] for school in universities}),
        )

    def test_us_university_data_has_valid_map_and_ranking_fields(self):
        for school in self.payload['universities']:
            self.assertTrue(school['name_cn'])
            self.assertTrue(school['name_en'])
            self.assertTrue(school['state_cn'])
            self.assertGreaterEqual(school['latitude'], 18)
            self.assertLessEqual(school['latitude'], 54)
            self.assertGreaterEqual(school['longitude'], -132)
            self.assertLessEqual(school['longitude'], -62)
            self.assertGreaterEqual(school['us_news_national_rank'], 1)
            self.assertLessEqual(school['us_news_national_rank'], 80)
            self.assertTrue(school['qs_world_rank'])
            self.assertIsInstance(school['strengths'], list)
            self.assertTrue(school['strengths'])

    def test_unsourced_volatile_application_fields_are_not_published(self):
        volatile_fields = {'tuition', 'application_round', 'testing_policy'}

        for school in self.payload['universities']:
            self.assertTrue(volatile_fields.isdisjoint(school))

    def test_loader_returns_serializable_map_payload(self):
        payload = load_us_undergraduate_universities()

        self.assertEqual(payload['meta']['university_count'], 77)
        self.assertEqual(len(payload['universities']), 77)
        json.dumps(payload, ensure_ascii=False)

    def test_study_maps_page_renders_interactive_us_map(self):
        response = self.client.get('/study-maps')

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="usMap"'.encode(), response.data)
        self.assertIn('id="usSchoolSearch"'.encode(), response.data)
        self.assertIn(b'Princeton University', response.data)
        self.assertIn('美国本科院校互动地图'.encode(), response.data)
        self.assertIn(b'/static/vendor/leaflet/leaflet.js', response.data)
        self.assertNotIn(b'unpkg.com/leaflet', response.data)
        self.assertNotIn(b'cartocdn.com', response.data)

    def test_other_destination_tabs_remain_available(self):
        response = self.client.get('/study-maps')
        page = unescape(response.get_data(as_text=True))

        for destination in ('英国', '加拿大', '澳大利亚', '新加坡&香港'):
            self.assertIn(destination, page)


if __name__ == '__main__':
    unittest.main()
