# Cho Thuê Xe Đại Lợi — Flask + PostgreSQL CRUD Demo

**Mức độ:** Demo / bài tập / trình diễn chức năng. **Chưa phải production.**

Dự án đầy đủ gồm website đặt xe responsive, 3 ảnh xe đã cung cấp, Flask API, quản trị CRUD xe và đơn đặt, PostgreSQL Render Free, Dockerfile và email tùy chọn qua Resend HTTPS API.

## 1. Chạy trên máy (Windows / macOS / Linux)

Cài Python 3.12+, giải nén, mở Terminal tại thư mục **chứa `app.py`**.

**Windows PowerShell:**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY = "local-test-key-change-me"
$env:ADMIN_PASSWORD = "my-demo-admin-pass"
python app.py
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY='local-test-key-change-me'
export ADMIN_PASSWORD='my-demo-admin-pass'
python app.py
```

Mở `http://127.0.0.1:5000/`. Trang quản trị tại `http://127.0.0.1:5000/admin`. Khi chạy ở máy, ứng dụng tự tạo **SQLite local** trong thư mục `instance/` để bạn không cần thiết lập PostgreSQL lúc thử.

## 2. Deploy miễn phí lên Render (khuyên dùng)

1. Tạo repo GitHub mới (private hay public tùy bạn), đưa **toàn bộ nội dung bên trong** thư mục này lên root repo. Không push file `.env`, thư mục `instance/` hoặc mật khẩu.
2. Render Dashboard → **New → Blueprint** → Connect GitHub repo, chọn repo có `render.yaml`.
3. Render sẽ tạo **Web Service Free + PostgreSQL Free**. Tại bước thiết lập biến môi trường, nhập `ADMIN_PASSWORD` là một mật khẩu riêng, dài và khó đoán.
4. Chờ deploy hoàn tất → mở đường dẫn `https://...onrender.com/` và thử `/health` (phải trả `status: ok`, `database: ok`).
5. Mở `/admin/login` → đăng nhập, kiểm tra có 3 xe demo. Gửi form đặt xe thử từ trang chủ → `/admin` phải có đơn mới.

**Quan trọng:** Render Free PostgreSQL tồn tại **30 ngày**, lưu tối đa **1 GB** và không có backup; bạn cần xuất/lưu dữ liệu trước khi hết hạn. Web Service miễn phí có thể ngủ khi không có traffic, request đầu có thể chậm. Không sử dụng SQLite làm DB thực trên Render Free vì ổ đĩa web service không bền vững.

Nếu đã tạo một Web Service bằng `New → Web Service`, bạn có thể tạo **Render Postgres Free** riêng, copy **Internal Database URL** vào biến `DATABASE_URL` của Web Service, nhập `SECRET_KEY` và `ADMIN_PASSWORD` rồi deploy từ GitHub:
- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2`
- Health check: `/health`

## 3. Docker Image (tuỳ chọn)

Tại thư mục project:

```bash
docker build -t YOUR_DOCKERHUB_USERNAME/dai-loi-demo:v1 .
docker login
docker push YOUR_DOCKERHUB_USERNAME/dai-loi-demo:v1
```

Trên Render: **New → Web Service → Existing Image**, nhập `docker.io/YOUR_DOCKERHUB_USERNAME/dai-loi-demo:v1`.

**Docker image không chứa database.** Vẫn phải tạo Render Postgres, cấu hình `DATABASE_URL`, `SECRET_KEY`, `ADMIN_PASSWORD` trong Web Service. Không điền API key/mật khẩu vào Dockerfile hoặc source. Với nhu cầu chỉnh code thường xuyên, deploy GitHub + Blueprint đơn giản hơn Existing Image.

## 4. Cấu hình gửi email thật (tùy chọn)

Mặc định **không gửi email** nhưng đơn **vẫn được lưu vào DB**. Trong Render Web Service → Environment, thêm:

```text
RESEND_API_KEY=<API key cấp bởi Resend>
MAIL_FROM=Dai Loi <datxe@YOUR_VERIFIED_DOMAIN>
BOOKING_NOTIFY_TO=thuexedailoi@gmail.com
```

Người gửi (`MAIL_FROM`) phải được Resend chấp nhận (thường cần xác minh domain). Ứng dụng gửi bằng API HTTPS tới `https://api.resend.com/emails`, không sử dụng SMTP. Nếu chưa cấu hình, trạng thái email là `disabled`; API lỗi là `failed`; thành công từ API là `sent` (**chỉ xác nhận API nhận, không đảm bảo email đã vào inbox**).

Có nút **“Thử gửi”** tại trang `/admin` cho đơn chưa được API nhận. Email gửi thất bại **không làm mất đơn**.

## 5. Chức năng có trong bản demo

### Khách truy cập
- Trang chủ giới thiệu dịch vụ, quy trình 3 bước, đội xe.
- Danh sách xe tự lấy từ DB, 3 ảnh thật bạn gửi: **Toyota Vios 4 chỗ, Fortuner 7 chỗ, Ford Transit 16 chỗ**.
- Chọn xe trong danh sách → tự điền vào form.
- Form: tên, điện thoại, email tùy chọn, số khách, xe, loại chuyến, ngày đi, giờ đi, ngày về khi khứ hồi, điểm đón, điểm đến, ghi chú.
- Kiểm tra dữ liệu tại trình duyệt **và server**: số khách tối đa theo xe, ngày đi, ngày về, điện thoại, email.
- Khi gửi form: **CREATE** đơn → trả mã `DL-00001`, lưu DB và hiển thị kết quả.

### Quản trị `/admin`
- Đăng nhập bằng `ADMIN_PASSWORD` cấu hình qua môi trường; đăng xuất.
- Dashboard thống kê tổng đơn, đơn chờ, số xe.
- **Cars CRUD:** Create / Read / Update / Delete. Thêm tên xe, số chỗ, phân loại, mô tả, ảnh trong 3 ảnh có sẵn, trạng thái hiển thị.
- Không xóa xe đã có đơn: có thể ẩn xe khỏi trang chủ để giữ lịch sử.
- **Bookings CRUD:** Create qua form công khai, Read qua dashboard, Update trạng thái, Delete từ dashboard.
- Trạng thái đơn: Chờ xác nhận / Đã xác nhận / Hoàn thành / Đã hủy.
- Xem chi tiết đơn và trạng thái gửi email; thử gửi lại khi có lỗi.

### Công nghệ
- Flask + Flask-SQLAlchemy; SQLite khi chạy local, PostgreSQL khi Render cấp `DATABASE_URL`.
- `db.create_all()` + seed 3 xe demo lần chạy đầu. **Không có schema migrations**.
- Dockerfile; Render Blueprint `render.yaml`; thư mục static ảnh, CSS, JavaScript.
- Mã thông báo CSRF cho form thay đổi dữ liệu; mật khẩu quản trị; cơ chế chống spam honeypot cơ bản.

## 6. Hạn chế đã biết / điều cần lưu ý

- Không thanh toán, không tra cứu tồn xe theo lịch, không tự tính giá, không xác nhận đơn thật.
- Không đăng ký người dùng, không đăng nhập khách, không quản lý phân quyền nhiều tài khoản.
- Demo quản trị sử dụng **một mật khẩu**; chưa có rate limiting, reset password, audit log hoặc quy trình production.
- Không upload ảnh trong admin; chỉ chọn trong ba ảnh có sẵn. Muốn thêm ảnh khác, thêm file vào `static/images/` rồi cập nhật `IMAGES` trong `app.py`.
- Không nên đưa dữ liệu cá nhân thật vào demo công khai.
- Không lưu bản sao dữ liệu bên ngoài DB; Render Postgres Free hết hạn sau 30 ngày và không backup.
- Email thật cần Resend API + địa chỉ sender hợp lệ; chưa cấu hình thì **không có email gửi đi**.
- Kết quả `email_status=sent` nghĩa là Resend chấp nhận yêu cầu, không chắc chắn thư đã đến hộp thư.
- Dữ liệu DB đang dùng `create_all` (phù hợp bản demo), sửa schema về sau cần migration hoặc tạo DB mới.
- Chưa có cơ chế chống gửi đơn trùng khi người dùng cố tình gửi nhiều lần.

## 7. Chạy kiểm thử tự động (sau khi cài requirements)

```bash
python -m unittest discover -s tests -v
```

Bộ test kiểm tra trang chủ, seed dữ liệu, tạo đơn, kiểm tra dữ liệu/CSRF, đăng nhập quản trị, cập nhật/xóa đơn, thêm/sửa/xóa xe và ngăn xóa xe có đơn.

## 8. Cấu trúc

```text
DaiLoi_Flask_Postgres_Demo/
├── app.py
├── requirements.txt
├── render.yaml
├── Dockerfile
├── .env.example
├── .gitignore
├── .dockerignore
├── README.md
├── static/
│   ├── css/style.css
│   ├── js/main.js
│   └── images/{vios.png,fortuner.png,transit.png}
└── templates/
    ├── index.html
    ├── admin_base.html
    ├── admin_login.html
    ├── admin_dashboard.html
    ├── admin_cars.html
    ├── admin_car_form.html
    └── error.html
```
