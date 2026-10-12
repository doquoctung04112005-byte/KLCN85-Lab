# KLCN85-Broken-Access-Control
Đồ án KLCN85 - phòng chống Broken Access Control

## Cấu hình PostgreSQL

Ứng dụng dùng PostgreSQL tại `127.0.0.1:5432`, với database `klcn85_lab` và tài khoản `klcn85_app`.

Tạo role và database trong `psql` bằng tài khoản quản trị PostgreSQL:

```sql
CREATE ROLE klcn85_app LOGIN;
\password klcn85_app
CREATE DATABASE klcn85_lab OWNER klcn85_app;
```

Lệnh `\password` nhập mật khẩu tương tác. Để chạy `manage.py test`, Django cần tạo database kiểm thử; có thể cấp quyền đó bằng `ALTER ROLE klcn85_app CREATEDB;`.

Cài thư viện, tạo file `.env` từ mẫu và điền mật khẩu PostgreSQL:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

```dotenv
KLCN85_DB_PASSWORD=mat_khau_postgresql_cua_ban
```

`.env` được Git bỏ qua. Chỉ lưu mật khẩu trên máy cá nhân; không thêm mật khẩu thật vào `.env.example` hoặc Git.

Sau khi PostgreSQL chạy, áp dụng migration, kiểm tra cấu hình và chạy ứng dụng:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py runserver
```

## Đường dẫn dùng ID số

Sau khi chạy migration, tài liệu và thư mục có ID số tăng dần. Ví dụ: `/documents/1/` và `/documents/folders/1/`. Các liên kết UUID cũ không còn khớp URL mới. Trong bản lab, các URL chi tiết, tải xuống và xem trước tài liệu cố ý thiếu kiểm tra quyền xem đối tượng để minh họa IDOR; xem `docs/idor-bola-lab.md`.

## Lab leo thang quyền dọc

Nhân viên có thể mở trang Hồ sơ cá nhân, chọn **Chỉnh sửa hồ sơ** và đổi vai trò ứng dụng của chính mình thành quản trị viên. Đây là lỗ hổng cố ý của bản lab để minh họa leo thang đặc quyền. Chỉ dùng tài khoản và dữ liệu giả trong môi trường local; xem ma trận tại `docs/authorization-test-matrix.md`.

## Scenario #2: forced browsing

Trang quản lý tài khoản thật `/users/` cố ý thiếu kiểm tra vai trò admin: mọi tài khoản đã đăng nhập đều xem được danh sách người dùng bằng URL trực tiếp. Không cần bật biến môi trường. Xem cách thử bằng Burp Repeater và ghi bằng chứng tại `docs/scenario-2-forced-browsing.md`.
