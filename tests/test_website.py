import tempfile
import unittest
from pathlib import Path

from app import app, db, load_school_profiles


class WebsiteTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / 'website-test.db'
        app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI=f'sqlite:///{database_path}',
        )
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        self.temp_dir.cleanup()

    def test_primary_pages_and_service_details_render(self):
        for path in ('/', '/services', '/services/planning',
                     '/services/undergraduate', '/services/masters',
                     '/services/phd', '/cases', '/about', '/resources',
                     '/resources/destinations', '/resources/majors',
                     '/resources/careers', '/resources/application-process',
                     '/ranking', '/contact', '/booking'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn('瀛动教育'.encode(), response.data)

        self.assertEqual(self.client.get('/services/unknown').status_code, 404)
        self.assertEqual(self.client.get('/resources/unknown').status_code, 404)

    def test_global_services_partner_mark_and_resource_brand_boundary(self):
        services = self.client.get('/services').data
        self.assertIn('全球本科申请'.encode(), services)
        self.assertIn('全球硕士申请'.encode(), services)
        self.assertIn('全球博士申请'.encode(), services)
        self.assertIn('cg-overseas-logo.png'.encode(), services)
        self.assertIn('超哥留学'.encode(), services)

        home = self.client.get('/').data
        self.assertIn('website.css'.encode(), home)
        self.assertIn('超哥留学'.encode(), home)
        about = self.client.get('/about').data
        self.assertIn('grace-consultation.png'.encode(), about)
        self.assertIn('grace-consultation.png',
                      (Path(app.static_folder) / 'website.css').read_text())

        for path in ('/resources', '/resources/destinations',
                     '/resources/majors', '/resources/careers',
                     '/resources/application-process'):
            with self.subTest(path=path):
                self.assertNotIn('超哥留学'.encode(), self.client.get(path).data)

    def test_ipeds_directory_search_filter_and_pagination(self):
        page = self.client.get('/ranking').data
        self.assertIn('IPEDS 2024'.encode(), page)
        self.assertIn('Alabama A &amp; M University'.encode(), page)
        self.assertNotIn('U.S. News'.encode(), page)

        search = self.client.get('/ranking?q=Princeton').data
        self.assertIn('Princeton University'.encode(), search)
        self.assertNotIn('Alabama A &amp; M University'.encode(), search)

        filtered = self.client.get('/ranking?q=Harvard&state=MA&control=private').data
        self.assertIn('Harvard University'.encode(), filtered)
        public = self.client.get('/ranking?q=Harvard&state=MA&control=public').data
        self.assertIn('没有找到符合条件的学校'.encode(), public)

        empty = self.client.get('/ranking?q=not-a-real-university-xyz').data
        self.assertIn('没有找到符合条件的学校'.encode(), empty)
        self.assertEqual(self.client.get('/ranking?page=2').status_code, 200)

    def test_school_profiles_are_searchable_and_brand_free(self):
        profiles = load_school_profiles()
        self.assertEqual(len(profiles), 56)
        self.assertEqual(len({school['unitid'] for school in profiles}), 56)
        for school in profiles:
            self.assertGreaterEqual(school['admission_rate_2025'], 0)
            self.assertLessEqual(school['admission_rate_2025'], 100)
            self.assertEqual(len(school['top_bachelor_majors_2025']), 3)
            self.assertIn('historical_test_score_range', school)

        listing = self.client.get('/resources/schools')
        self.assertEqual(listing.status_code, 200)
        self.assertNotIn('找到 56 所院校'.encode(), listing.data)
        self.assertNotIn('资料快照：2026 年 11 月 13 日'.encode(), listing.data)
        self.assertIn('不代表排名'.encode(), listing.data)
        self.assertNotIn('续航教育'.encode(), listing.data)
        self.assertNotIn('超哥留学'.encode(), listing.data)

        filtered = self.client.get('/resources/schools?q=哈佛&state=MA&control=private')
        self.assertIn('哈佛大学'.encode(), filtered.data)
        self.assertNotIn('找到 1 所院校'.encode(), filtered.data)
        self.assertIn('没有找到符合条件的学校'.encode(),
                      self.client.get('/resources/schools?q=哈佛&control=public').data)
        self.assertEqual(self.client.get('/resources/schools?page=2').status_code, 200)

        detail = self.client.get('/resources/schools/166027')
        self.assertEqual(detail.status_code, 200)
        self.assertIn('Harvard University'.encode(), detail.data)
        self.assertIn('计量经济学和量化经济学'.encode(), detail.data)
        self.assertIn('2025 录取率'.encode(), detail.data)
        self.assertIn('1510–1580'.encode(), detail.data)
        self.assertNotIn('续航教育'.encode(), detail.data)
        self.assertNotIn('超哥留学'.encode(), detail.data)
        self.assertNotIn('U.S. News'.encode(), detail.data)
        self.assertEqual(self.client.get('/resources/schools/999999').status_code, 404)
        self.assertIn('没有可展示的 SAT/ACT 区间'.encode(),
                      self.client.get('/resources/schools/110635').data)
        for school in profiles:
            with self.subTest(school=school['unitid']):
                self.assertEqual(self.client.get(
                    f"/resources/schools/{school['unitid']}").status_code, 200)

        directory = self.client.get('/ranking?q=Harvard').data
        self.assertIn('/resources/schools/166027'.encode(), directory)

    def test_old_offer_link_redirects_to_case_library(self):
        response = self.client.get('/offers')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.location, '/cases')

    def test_public_cases_can_be_filtered_by_stage_and_outcome(self):
        response = self.client.get('/cases?stage=%E6%9C%AC%E7%A7%91')
        self.assertEqual(response.status_code, 200)
        self.assertIn('IB 物理方向'.encode(), response.data)
        self.assertNotIn('计算机直博'.encode(), response.data)

        response = self.client.get('/cases?q=%E8%8C%83%E5%BE%B7%E5%A0%A1')
        self.assertIn('法律硕士'.encode(), response.data)
        self.assertNotIn('IB 物理方向'.encode(), response.data)

    def test_case_details_are_public_without_student_names(self):
        app.config['TESTING'] = False
        try:
            response = self.client.get('/cases')
            self.assertEqual(response.status_code, 200)
            self.assertIn('IB 物理方向'.encode(), response.data)
            self.assertNotIn('内容草稿'.encode(), response.data)
            detail = self.client.get('/cases/masters-law-ip')
            self.assertEqual(detail.status_code, 200)
            self.assertIn('圣路易斯华盛顿大学'.encode(), detail.data)
            self.assertIn('GPA 3.22'.encode(), detail.data)
            for name in ('刘同学', 'W同学', 'L同学'):
                self.assertNotIn(name.encode(), detail.data)
            self.assertEqual(self.client.get('/cases/unknown').status_code, 404)
        finally:
            app.config['TESTING'] = True

    def test_review_required_claims_are_not_on_primary_pages(self):
        for path in ('/', '/services', '/about'):
            with self.subTest(path=path):
                page = self.client.get(path).data
                self.assertNotIn('签证通过率'.encode(), page)
                self.assertNotIn('TOP30'.encode(), page)
                self.assertNotIn('退还服务费用'.encode(), page)

    def test_debug_home_renders_service_navigation(self):
        response = self.client.get('/debug/render-home')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json['has_css_dump_marker'])
        self.assertIn('瀛动教育', response.json['html_preview_head'])


if __name__ == '__main__':
    unittest.main()
