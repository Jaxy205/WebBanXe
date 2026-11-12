"""Runtime smoke tests. Install requirements first; run: python -m unittest discover -s tests -v"""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app import create_app, db, Car, Booking


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "unittest-secret",
            "ADMIN_PASSWORD": "demo-test-pass",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
            "RESEND_API_KEY": "",
            "MAIL_FROM": "",
        })
        self.client = self.app.test_client()
        self.client.get("/")

    def csrf(self):
        with self.client.session_transaction() as sess:
            return sess['csrf_token']

    def login(self):
        return self.client.post('/admin/login', data={
            'csrf_token': self.csrf(), 'password': 'demo-test-pass'
        }, follow_redirects=True)

    def booking_data(self):
        with self.app.app_context():
            car_id = Car.query.first().id
        return {
            'customer_name': 'Khách Demo', 'phone': '0901234567',
            'car_id': car_id, 'passenger_count': '2',
            'trip_type': 'one_way',
            'travel_date': (datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')) + timedelta(days=2)).date().isoformat(),
            'travel_time': '08:30', 'return_date': '',
            'pickup': 'Thành phố Hồ Chí Minh', 'destination': 'Vũng Tàu',
            'notes': 'Đặt thử', 'email': ''
        }

    def post_booking(self, data=None):
        return self.client.post('/api/bookings', json=data or self.booking_data(),
                                headers={'X-CSRF-Token': self.csrf()})

    def test_seed_and_public_page(self):
        with self.app.app_context():
            self.assertEqual(Car.query.count(), 3)
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(len(self.client.get('/api/cars').get_json()), 3)
        self.assertEqual(self.client.get('/health').get_json()['status'], 'ok')

    def test_booking_create_and_admin_read(self):
        response = self.post_booking()
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json['ok'])
        self.assertEqual(response.json['code'], 'DL-00001')
        self.assertEqual(response.json['email_status'], 'disabled')
        with self.app.app_context():
            self.assertEqual(Booking.query.count(), 1)
        self.assertIn(b'/admin/login', self.client.get('/admin').location.encode())
        self.login()
        self.assertIn('DL-00001', self.client.get('/admin').get_data(as_text=True))

    def test_booking_validation_and_csrf(self):
        self.assertEqual(self.client.post('/api/bookings', json=self.booking_data()).status_code, 403)
        data = self.booking_data()
        data['phone'] = 'abc'
        self.assertEqual(self.post_booking(data).status_code, 400)
        data = self.booking_data()
        data['passenger_count'] = '30'
        self.assertEqual(self.post_booking(data).status_code, 400)
        data = self.booking_data()
        data['trip_type'] = 'round_trip'
        self.assertEqual(self.post_booking(data).status_code, 400)

    def test_admin_booking_status_and_delete(self):
        self.post_booking()
        self.login()
        token = self.csrf()
        response = self.client.post('/admin/bookings/1/status', data={'csrf_token': token, 'status': 'confirmed'})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.session.get(Booking, 1).status, 'confirmed')
        self.assertEqual(self.client.post('/admin/bookings/1/delete', data={'csrf_token': token}).status_code, 302)
        with self.app.app_context():
            self.assertEqual(Booking.query.count(), 0)

    def test_admin_car_crud_and_protect_booked_car(self):
        self.login()
        token = self.csrf()
        resp = self.client.post('/admin/cars/new', data={
            'csrf_token': token, 'name': 'Xe Demo 9 chỗ', 'seats': '9',
            'kind': 'Minibus', 'description': 'Xe mẫu', 'image_file': 'transit.png', 'active': 'on'
        })
        self.assertEqual(resp.status_code, 302)
        with self.app.app_context():
            car_id = Car.query.filter_by(name='Xe Demo 9 chỗ').first().id
        self.assertEqual(self.client.post(f'/admin/cars/{car_id}/edit', data={
            'csrf_token': token, 'name': 'Xe Demo Sửa', 'seats': '9',
            'kind': 'Minibus', 'description': '', 'image_file': 'transit.png'
        }).status_code, 302)
        with self.app.app_context():
            self.assertFalse(db.session.get(Car, car_id).active)
        self.assertEqual(self.client.post(f'/admin/cars/{car_id}/delete', data={'csrf_token': token}).status_code, 302)
        with self.app.app_context():
            self.assertIsNone(db.session.get(Car, car_id))
        self.client.post('/admin/logout', data={'csrf_token': token})
        self.post_booking()
        self.login()
        with self.app.app_context():
            booked_car_id = Booking.query.first().car_id
        self.client.post(f'/admin/cars/{booked_car_id}/delete', data={'csrf_token': self.csrf()})
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(Car, booked_car_id))


if __name__ == '__main__':
    unittest.main()
