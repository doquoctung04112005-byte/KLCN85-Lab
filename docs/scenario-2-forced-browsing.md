# Scenario #2: truy cập trực tiếp trang quản lý tài khoản thật

Đây là lỗi **cố ý** trong mã nguồn KLCN85. Chỉ chạy bản web này với tài khoản và dữ liệu thử nghiệm. Nhân viên thường có thể mở trang quản lý tài khoản thật `/users/` bằng URL trực tiếp dù menu không hiện liên kết này. Lỗi luôn có trong view, không phụ thuộc biến môi trường hoặc `DEBUG`.

## Phân quyền đúng và hành vi lỗi

| Phiên truy cập | `GET /users/` | Ý nghĩa |
| --- | --- | --- |
| Chưa đăng nhập | `302` đến `/login/` | Vẫn cần đăng nhập |
| Nhân viên thường | `200`, thấy bảng tài khoản | **Lỗi phân quyền theo vai trò** |
| Admin ứng dụng | `200`, thấy bảng tài khoản | Truy cập hợp lệ |

Route `/users/` sử dụng view và template quản lý tài khoản thật của ứng dụng. Lỗ hổng nằm trong `accounts.views.user_list`: view yêu cầu đăng nhập nhưng không gọi `is_admin_profile()` trước khi truy vấn và trả danh sách tài khoản. Nhân viên vẫn có `UserProfile.role=employee`; các chức năng `/users/new/` và `/users/<ID>/edit/` của người khác vẫn kiểm tra quyền riêng và trả `403`. Đây là [OWASP Top 10:2025 A01 Broken Access Control, Scenario #2](https://top10.owasp.org/2025/A01_2025-Broken_Access_Control/) với URL quản lý thật của dự án.

## Chuẩn bị

1. Dùng `nhanvien_a1` làm user thường. Dùng `admin_demo` hoặc tài khoản admin bạn tự tạo trong pgAdmin làm đối chứng. Nếu đã tạo `admin_pgadmin`, hãy kiểm tra tài khoản có hàng tương ứng trong `accounts_userprofile` với `role='admin'`.
2. Khởi động lại `python manage.py runserver` rồi mở `http://127.0.0.1:8000`. Không đưa bản web có lỗi hoặc dữ liệu thật ra Internet.

## Tái hiện bằng Burp Suite Repeater

1. Mở web bằng trình duyệt qua Burp Proxy, đăng nhập `nhanvien_a1`. Trong **Proxy → HTTP history**, chọn một request sau đăng nhập và **Send to Repeater**.
2. Giữ cookie `sessionid` của nhân viên, đổi dòng đầu thành `GET /users/ HTTP/1.1` và nhấn **Send**. Response là HTTP `200`, có trang HTML **Người dùng** và tên `admin_demo` (hoặc admin bạn đã tạo).
3. Gửi `GET /users/new/ HTTP/1.1` với cùng cookie. Response `403`, cho thấy tài khoản nhân viên không trở thành admin; lỗi chỉ nằm ở quyền xem danh sách.
4. Đăng nhập bằng tài khoản admin rồi gửi `GET /users/ HTTP/1.1` với cookie admin để lấy mẫu đối chiếu hợp lệ.
5. Xóa header `Cookie` và gửi lại `GET /users/ HTTP/1.1`. Response `302` chuyển đến trang đăng nhập.

Giữ nguyên `Host: 127.0.0.1:8000`. Nếu Burp tự cập nhật cookie bằng quy tắc phiên, kiểm tra request cuối cùng thực sự mang cookie của tài khoản tương ứng.

## Bằng chứng đưa vào báo cáo

- Ảnh request/response của nhân viên đến `/users/`: cookie nhân viên, HTTP `200`, bảng tài khoản có tên admin.
- Ảnh request/response của admin đến cùng URL: HTTP `200`, làm mẫu truy cập hợp lệ.
- Ảnh nhân viên đến `/users/new/`: HTTP `403`, chứng minh vai trò chưa đổi.
- Kết luận: **OWASP A01 Broken Access Control / forced browsing** do kiểm tra vai trò ở trang quản lý tài khoản bị bỏ qua. Cách sửa là luôn yêu cầu `is_admin_profile()` trước khi trả danh sách.
