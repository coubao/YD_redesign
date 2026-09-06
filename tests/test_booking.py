import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from app import (
    BOOKING_STATUS_CONFIRMED,
    BOOKING_STATUS_MANUAL_BLOCK,
    BOOKING_TIME_SLOTS,
    Booking,
    app,
    booking_meets_minimum_notice,
    build_booking_days,
    build_slot_status_map,
    booking_today,
    db,
    recurring_placeholder_name,
)


class BookingTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / 'booking-test.db'
        app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI=f'sqlite:///{database_path}',
        )
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        self.temp_dir.cleanup()

    def add_booking(self, **overrides):
        values = {
            'booking_date': (booking_today() + timedelta(days=2)).isoformat(),
            'time_slot': BOOKING_TIME_SLOTS[0],
            'name': '测试同学',
            'contact': '13900001111',
            'target_country': '美国',
            'stage': '本科',
            'question': '测试咨询问题',
            'meeting_method': '腾讯会议',
            'status': BOOKING_STATUS_CONFIRMED,
            'intake_data': '',
        }
        values.update(overrides)
        booking = Booking(**values)
        db.session.add(booking)
        db.session.commit()
        return booking

    def first_available_slot(self):
        for day in build_booking_days():
            statuses = build_slot_status_map([day['value']])[day['value']]
            for slot, status in statuses.items():
                if status['state'] == 'available':
                    return day['value'], slot
        self.fail('测试范围内没有可用时段')

    def test_booking_window_starts_tomorrow_and_contains_30_days(self):
        days = build_booking_days()

        self.assertEqual(len(days), 30)
        self.assertEqual(days[0]['value'], (booking_today() + timedelta(days=1)).isoformat())
        self.assertEqual(days[-1]['value'], (booking_today() + timedelta(days=30)).isoformat())

    def test_booking_has_four_configured_daily_slots(self):
        self.assertEqual(
            BOOKING_TIME_SLOTS,
            ['09:30-10:30', '11:00-12:00', '14:00-15:00', '15:30-16:30'],
        )

    def test_booking_and_admin_pages_render_configured_slots(self):
        booking_response = self.client.get('/booking')
        admin_response = self.client.get('/admin/bookings')

        self.assertEqual(booking_response.status_code, 200)
        self.assertEqual(admin_response.status_code, 200)
        for slot in BOOKING_TIME_SLOTS:
            self.assertIn(slot.encode(), booking_response.data)
            self.assertIn(slot.encode(), admin_response.data)
        self.assertNotIn(b'10:00-11:00', booking_response.data)
        self.assertNotIn(b'15:00-16:00', booking_response.data)

    def test_monday_morning_and_sunday_are_recurring_placeholders(self):
        monday = datetime(2026, 9, 7).date()
        sunday = datetime(2026, 9, 13).date()

        self.assertEqual(recurring_placeholder_name(monday, '09:30-10:30'), 'XX同学')
        self.assertEqual(recurring_placeholder_name(monday, '11:00-12:00'), 'XX同学')
        self.assertEqual(recurring_placeholder_name(monday, '14:00-15:00'), '')
        self.assertEqual(recurring_placeholder_name(monday, '15:30-16:30'), '')
        for slot in BOOKING_TIME_SLOTS:
            self.assertEqual(recurring_placeholder_name(sunday, slot), 'XX同学')

    def test_minimum_notice_is_calculated_from_slot_start(self):
        now = datetime(2026, 8, 29, 11, 1)

        self.assertFalse(booking_meets_minimum_notice('2026-08-30', '09:30-10:30', now=now))
        self.assertTrue(booking_meets_minimum_notice('2026-08-30', '14:00-15:00', now=now))

    def test_same_day_booking_is_rejected_server_side(self):
        response = self.client.get(
            '/booking/details',
            query_string={
                'booking_date': booking_today().isoformat(),
                'time_slot': BOOKING_TIME_SLOTS[0],
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('请选择可预约日期'.encode(), response.data)

    def test_admin_can_create_and_release_manual_block(self):
        booking_date, time_slot = self.first_available_slot()

        response = self.client.post(
            '/admin/bookings/manual-block',
            data={
                'booking_date': booking_date,
                'time_slot': time_slot,
                'placeholder_name': 'AB同学',
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        block = Booking.query.filter_by(status=BOOKING_STATUS_MANUAL_BLOCK).one()
        self.assertEqual(block.name, 'AB同学')
        status = build_slot_status_map([booking_date])[booking_date][time_slot]
        self.assertEqual(status['state'], 'booked')
        self.assertEqual(status['label'], 'AB同学已预约')

        response = self.client.post(
            f'/admin/bookings/{block.id}/manual-block/delete',
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(db.session.get(Booking, block.id))

    def test_manual_block_rejects_an_unavailable_slot(self):
        booking_date, time_slot = self.first_available_slot()
        self.add_booking(booking_date=booking_date, time_slot=time_slot)

        response = self.client.post(
            '/admin/bookings/manual-block',
            data={
                'booking_date': booking_date,
                'time_slot': time_slot,
                'placeholder_name': 'CD同学',
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('该时段已被预约'.encode(), response.data)
        self.assertEqual(Booking.query.count(), 1)

    def test_admin_search_matches_normalized_phone_number(self):
        self.add_booking(contact='+86 139-0000-1111')
        self.add_booking(
            booking_date=(booking_today() + timedelta(days=3)).isoformat(),
            time_slot=BOOKING_TIME_SLOTS[-1],
            name='另一位同学',
            contact='13800002222',
        )

        response = self.client.get('/admin/bookings', query_string={'q': '13900001111'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('测试同学'.encode(), response.data)
        self.assertNotIn('另一位同学'.encode(), response.data)


if __name__ == '__main__':
    unittest.main()
