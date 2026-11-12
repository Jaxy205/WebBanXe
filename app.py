"""Cho Thuê Xe Đại Lợi - Flask demo with Render Postgres, CRUD and optional Resend.

This is a demonstration project, not production-grade booking software.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import re
import secrets
import unicodedata
from datetime import date, datetime, timezone
from functools import wraps
from html import escape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, text

LOGGER = logging.getLogger(__name__)
db = SQLAlchemy()
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
IMAGES = {"vios.png", "fortuner.png", "transit.png"}
BOOKING_STATUSES = {"pending": "Chờ xác nhận", "confirmed": "Đã xác nhận",
                    "completed": "Hoàn thành", "cancelled": "Đã hủy"}
TRIP_TYPES = {"one_way": "Một chiều", "round_trip": "Khứ hồi", "custom": "Theo lịch trình"}


class Car(db.Model):
    __tablename__ = "cars"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    seats = db.Column(db.Integer, nullable=False)
    kind = db.Column(db.String(40), nullable=False, default="Du lịch")
    description = db.Column(db.String(400), nullable=False, default="")
    image_file = db.Column(db.String(80), nullable=False, default="vios.png")
    active = db.Column(db.Boolean, nullable=False, default=True)
    bookings = db.relationship("Booking", back_populates="car")


class Booking(db.Model):
    __tablename__ = "bookings"
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(160), nullable=True)
    car_id = db.Column(db.Integer, db.ForeignKey("cars.id"), nullable=True)
    car_name = db.Column(db.String(100), nullable=False)  # snapshot if car later changes
    passenger_count = db.Column(db.Integer, nullable=True)
    trip_type = db.Column(db.String(25), nullable=False, default="one_way")
    travel_date = db.Column(db.Date, nullable=False)
    travel_time = db.Column(db.String(5), nullable=True)
    return_date = db.Column(db.Date, nullable=True)
    pickup = db.Column(db.String(250), nullable=False)
    destination = db.Column(db.String(250), nullable=False)
    notes = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="pending")
    email_status = db.Column(db.String(20), nullable=False, default="disabled")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    car = db.relationship("Car", back_populates="bookings")

    @property
    def code(self):
        return f"DL-{self.id:05d}"


def _normalize_db_url(url):
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _slugify(value):
    value = unicodedata.normalize("NFKD", value.lower().replace("đ", "d"))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")[:70]


def _validate_csrf():
    expected = session.get("csrf_token", "")
    received = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
    if not expected or not received or not hmac.compare_digest(expected, received):
        abort(403, description="Phiên thao tác không hợp lệ. Tải lại trang và thử lại.")


def _require_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def _send_booking_email(app, booking):
    """Send once per explicit call; return status string, never log credentials."""
    key = app.config.get("RESEND_API_KEY", "")
    sender = app.config.get("MAIL_FROM", "")
    recipient = app.config.get("BOOKING_NOTIFY_TO", "")
    if not (key and sender and recipient):
        return "disabled"

    details = [
        ("Mã yêu cầu", booking.code),
        ("Khách hàng", booking.customer_name),
        ("Điện thoại", booking.phone),
        ("Email khách", booking.email or "Không cung cấp"),
        ("Xe", booking.car_name),
        ("Số khách", str(booking.passenger_count or "Chưa có")),
        ("Loại chuyến", TRIP_TYPES.get(booking.trip_type, booking.trip_type)),
        ("Ngày đi", booking.travel_date.isoformat()),
        ("Giờ đi", booking.travel_time or "Chưa chọn"),
        ("Ngày về", booking.return_date.isoformat() if booking.return_date else "Không có"),
        ("Điểm đón", booking.pickup),
        ("Điểm đến", booking.destination),
        ("Ghi chú", booking.notes or "Không có"),
    ]
    rows = "".join(f"<tr><th style='text-align:left;padding:9px;background:#f2f5f2'>"
                   f"{escape(label)}</th><td style='padding:9px'>{escape(value)}</td></tr>"
                   for label, value in details)
    data = {
        "from": sender,
        "to": [recipient],
        "subject": f"[ĐẠI LỢI] Đơn mới {booking.code} - {booking.customer_name}",
        "html": "<h2>Yêu cầu đặt xe mới</h2><table>" + rows + "</table>",
    }
    req = Request(
        "https://api.resend.com/emails",
        data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "User-Agent": "DaiLoiBookingDemo/1.0",
                 "Idempotency-Key": f"dailoi-booking-{booking.id}-v1"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=10) as response:
            if not 200 <= response.status < 300:
                return "failed"
        return "sent"  # accepted by provider, not confirmation of inbox delivery
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        LOGGER.warning("Email API failed for booking %s: %s", booking.id, type(exc).__name__)
        return "failed"


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY") or "local-demo-change-this-before-public-deploy",
        SQLALCHEMY_DATABASE_URI=_normalize_db_url(os.getenv("DATABASE_URL", "sqlite:///dailoi_local.db")),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        MAX_CONTENT_LENGTH=32 * 1024,
        ADMIN_PASSWORD=os.getenv("ADMIN_PASSWORD", ""),
        RESEND_API_KEY=os.getenv("RESEND_API_KEY", ""),
        MAIL_FROM=os.getenv("MAIL_FROM", ""),
        BOOKING_NOTIFY_TO=os.getenv("BOOKING_NOTIFY_TO", "thuexedailoi@gmail.com"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=bool(os.getenv("RENDER")),
    )
    if test_config:
        app.config.update(test_config)
    if os.getenv("RENDER") and not app.config["ADMIN_PASSWORD"] and not app.config.get("TESTING"):
        raise RuntimeError("Hãy đặt ADMIN_PASSWORD trong Render Environment trước khi chạy.")
    if os.getenv("RENDER") and not os.getenv("DATABASE_URL") and not app.config.get("TESTING"):
        raise RuntimeError("Hãy liên kết DATABASE_URL tới Render PostgreSQL (không dùng SQLite trên Render Free).")
    db.init_app(app)

    @app.before_request
    def ensure_csrf():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.context_processor
    def global_template_data():
        return {"csrf_token": session.get("csrf_token", ""),
                "booking_statuses": BOOKING_STATUSES,
                "trip_types": TRIP_TYPES,
                "email_enabled": bool(app.config["RESEND_API_KEY"] and app.config["MAIL_FROM"]),
                "demo_mode": True}

    @app.template_filter("vn_date")
    def vn_date(value):
        return value.strftime("%d/%m/%Y") if value else "—"

    @app.template_filter("vn_datetime")
    def vn_datetime(value):
        if not value:
            return "—"
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(VN_TZ).strftime("%d/%m/%Y %H:%M")

    @app.get("/")
    def index():
        cars = Car.query.filter_by(active=True).order_by(Car.id).all()
        return render_template("index.html", cars=cars, now=date.today())

    @app.get("/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
            return jsonify(status="ok", database="ok")
        except Exception:
            return jsonify(status="error", database="unavailable"), 503

    @app.get("/api/cars")
    def api_cars():
        cars = Car.query.filter_by(active=True).order_by(Car.id).all()
        return jsonify([{"id": c.id, "name": c.name, "seats": c.seats,
                         "kind": c.kind, "description": c.description,
                         "image": url_for("static", filename="images/" + c.image_file)} for c in cars])

    @app.post("/api/bookings")
    def create_booking():
        _validate_csrf()
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(ok=False, message="Định dạng dữ liệu không hợp lệ."), 400
        if data.get("website"):
            # Honeypot: do not create fake bookings from bots.
            return jsonify(ok=True, demo=True, message="Yêu cầu đã được tiếp nhận."), 200

        def field(name, max_len=150):
            val = data.get(name, "")
            return val.strip()[:max_len] if isinstance(val, str) else ""

        name, phone, email = field("customer_name", 100), field("phone", 30), field("email", 160)
        pickup, destination = field("pickup", 250), field("destination", 250)
        notes, trip_type = field("notes", 1000), field("trip_type", 25)
        travel_date, travel_time, return_date = field("travel_date", 10), field("travel_time", 5), field("return_date", 10)
        if not (name and phone and pickup and destination and travel_date):
            return jsonify(ok=False, message="Vui lòng điền đủ các mục bắt buộc."), 400
        if len(name) < 2 or len(pickup) < 3 or len(destination) < 3:
            return jsonify(ok=False, message="Họ tên hoặc địa điểm quá ngắn."), 400
        if not re.fullmatch(r"[+\d ().-]{9,30}", phone) or len(re.sub(r"\D", "", phone)) < 9:
            return jsonify(ok=False, message="Số điện thoại chưa hợp lệ."), 400
        if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            return jsonify(ok=False, message="Email khách hàng không hợp lệ."), 400
        if trip_type not in TRIP_TYPES:
            return jsonify(ok=False, message="Loại chuyến không hợp lệ."), 400
        try:
            car_id = int(data.get("car_id"))
            passenger_count = int(data.get("passenger_count") or 0)
            depart = date.fromisoformat(travel_date)
            return_on = date.fromisoformat(return_date) if return_date else None
            if travel_time:
                datetime.strptime(travel_time, "%H:%M")
        except (TypeError, ValueError):
            return jsonify(ok=False, message="Xe, số khách hoặc ngày giờ không hợp lệ."), 400
        if depart < datetime.now(VN_TZ).date():
            return jsonify(ok=False, message="Ngày đi không thể ở trong quá khứ."), 400
        if return_on and return_on < depart:
            return jsonify(ok=False, message="Ngày về phải từ ngày đi trở đi."), 400
        if trip_type == "round_trip" and not return_on:
            return jsonify(ok=False, message="Chuyến khứ hồi cần ngày về."), 400
        if not (1 <= passenger_count <= 50):
            return jsonify(ok=False, message="Số hành khách phải từ 1 đến 50."), 400
        car = db.session.get(Car, car_id)
        if not car or not car.active:
            return jsonify(ok=False, message="Mẫu xe này không còn khả dụng."), 400
        if passenger_count > car.seats:
            return jsonify(ok=False, message=f"Xe này phù hợp tối đa {car.seats} khách."), 400

        booking = Booking(customer_name=name, phone=phone, email=email or None,
                          car_id=car.id, car_name=car.name, passenger_count=passenger_count,
                          trip_type=trip_type, travel_date=depart, travel_time=travel_time,
                          return_date=return_on, pickup=pickup, destination=destination,
                          notes=notes, status="pending")
        db.session.add(booking)
        db.session.commit()
        booking.email_status = _send_booking_email(app, booking)
        db.session.commit()
        result_message = f"Đã lưu yêu cầu {booking.code}."
        if booking.email_status == "sent":
            result_message += " Hệ thống email đã tiếp nhận thông báo."
        elif booking.email_status == "failed":
            result_message += " Chưa gửi được email; đơn vẫn có trong trang quản trị."
        else:
            result_message += " Email chưa bật (chế độ demo)."
        return jsonify(ok=True, code=booking.code, email_status=booking.email_status,
                       message=result_message), 201

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if session.get("admin_logged_in"):
            return redirect(url_for("admin_dashboard"))
        if request.method == "POST":
            _validate_csrf()
            passwd = request.form.get("password", "")
            admin_pwd = app.config["ADMIN_PASSWORD"]
            if admin_pwd and hmac.compare_digest(passwd, admin_pwd):
                session.clear()
                session["admin_logged_in"] = True
                flash("Đăng nhập thành công.", "success")
                return redirect(url_for("admin_dashboard"))
            flash("Mật khẩu không đúng hoặc chưa cấu hình ADMIN_PASSWORD.", "error")
        return render_template("admin_login.html")

    @app.post("/admin/logout")
    @_require_admin
    def admin_logout():
        _validate_csrf()
        session.clear()
        return redirect(url_for("index"))

    @app.get("/admin")
    @_require_admin
    def admin_dashboard():
        bookings = Booking.query.order_by(Booking.created_at.desc(), Booking.id.desc()).all()
        cars_count = Car.query.count()
        pending_count = Booking.query.filter_by(status="pending").count()
        return render_template("admin_dashboard.html", bookings=bookings,
                               cars_count=cars_count, pending_count=pending_count)

    @app.post("/admin/bookings/<int:booking_id>/status")
    @_require_admin
    def admin_booking_status(booking_id):
        _validate_csrf()
        booking = db.get_or_404(Booking, booking_id)
        status = request.form.get("status", "")
        if status not in BOOKING_STATUSES:
            abort(400, description="Trạng thái đơn không hợp lệ.")
        booking.status = status
        db.session.commit()
        flash(f"Đã cập nhật {booking.code}.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/bookings/<int:booking_id>/delete")
    @_require_admin
    def admin_booking_delete(booking_id):
        _validate_csrf()
        booking = db.get_or_404(Booking, booking_id)
        code = booking.code
        db.session.delete(booking)
        db.session.commit()
        flash(f"Đã xóa {code}.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/bookings/<int:booking_id>/email")
    @_require_admin
    def admin_booking_email(booking_id):
        _validate_csrf()
        booking = db.get_or_404(Booking, booking_id)
        if booking.email_status == "sent":
            flash("Email đã được API tiếp nhận trước đó. Không gửi lại để tránh trùng.", "info")
        else:
            booking.email_status = _send_booking_email(app, booking)
            db.session.commit()
            flash("Trạng thái gửi email: " + booking.email_status, "info")
        return redirect(url_for("admin_dashboard"))

    @app.get("/admin/cars")
    @_require_admin
    def admin_cars():
        cars = Car.query.order_by(Car.id).all()
        return render_template("admin_cars.html", cars=cars)

    def read_car_form():
        name = request.form.get("name", "").strip()[:100]
        kind = request.form.get("kind", "").strip()[:40]
        description = request.form.get("description", "").strip()[:400]
        image_file = request.form.get("image_file", "")
        active = request.form.get("active") == "on"
        try:
            seats = int(request.form.get("seats", ""))
        except ValueError:
            seats = 0
        if len(name) < 2 or not (1 <= seats <= 50) or image_file not in IMAGES:
            return None, "Tên, số chỗ hoặc hình xe không hợp lệ."
        return {"name": name, "kind": kind or "Du lịch", "description": description,
                "seats": seats, "image_file": image_file, "active": active}, None

    @app.route("/admin/cars/new", methods=["GET", "POST"])
    @_require_admin
    def admin_car_new():
        if request.method == "POST":
            _validate_csrf()
            attrs, error = read_car_form()
            if error:
                flash(error, "error")
            else:
                slug = _slugify(attrs["name"]) or "xe"
                if Car.query.filter_by(slug=slug).first():
                    slug += "-" + secrets.token_hex(3)
                db.session.add(Car(slug=slug, **attrs))
                db.session.commit()
                flash("Đã thêm xe mới.", "success")
                return redirect(url_for("admin_cars"))
        return render_template("admin_car_form.html", car=None, images=sorted(IMAGES))

    @app.route("/admin/cars/<int:car_id>/edit", methods=["GET", "POST"])
    @_require_admin
    def admin_car_edit(car_id):
        car = db.get_or_404(Car, car_id)
        if request.method == "POST":
            _validate_csrf()
            attrs, error = read_car_form()
            if error:
                flash(error, "error")
            else:
                for key, val in attrs.items():
                    setattr(car, key, val)
                db.session.commit()
                flash("Đã cập nhật thông tin xe.", "success")
                return redirect(url_for("admin_cars"))
        return render_template("admin_car_form.html", car=car, images=sorted(IMAGES))

    @app.post("/admin/cars/<int:car_id>/delete")
    @_require_admin
    def admin_car_delete(car_id):
        _validate_csrf()
        car = db.get_or_404(Car, car_id)
        if Booking.query.filter_by(car_id=car_id).first():
            flash("Xe đã có đơn đặt. Hãy tắt hiển thị thay vì xóa để giữ lịch sử.", "error")
        else:
            db.session.delete(car)
            db.session.commit()
            flash("Đã xóa xe.", "success")
        return redirect(url_for("admin_cars"))

    @app.errorhandler(403)
    def error_403(error):
        if request.path.startswith("/api/"):
            return jsonify(ok=False, message=str(error.description)), 403
        return render_template("error.html", code=403, message=str(error.description)), 403

    @app.errorhandler(413)
    def error_413(error):
        return jsonify(ok=False, message="Dữ liệu gửi lên quá lớn."), 413

    with app.app_context():
        db.create_all()  # demo only: for schema changes on a real app, use migrations
        if not Car.query.first():
            db.session.add_all([
                Car(slug="toyota-vios", name="Toyota Vios", seats=4, kind="Sedan",
                    description="Nhỏ gọn, tiện nghi, phù hợp di chuyển cá nhân và gia đình nhỏ.",
                    image_file="vios.png"),
                Car(slug="toyota-fortuner", name="Toyota Fortuner", seats=7, kind="SUV",
                    description="Thoải mái cho gia đình, nhóm bạn và những chuyến đi xa.",
                    image_file="fortuner.png"),
                Car(slug="ford-transit", name="Ford Transit", seats=16, kind="Minibus",
                    description="Không gian rộng cho đoàn du lịch, đưa đón và sự kiện.",
                    image_file="transit.png"),
            ])
            db.session.commit()
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")),
            debug=os.getenv("FLASK_DEBUG") == "1")
