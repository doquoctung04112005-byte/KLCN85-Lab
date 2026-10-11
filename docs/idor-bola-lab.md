# IDOR/BOLA lab với ID tuần tự

Tài liệu và thư mục dùng ID số tăng dần trong database và URL. Các URL chi tiết, tải xuống và xem trước tài liệu hiện tra cứu trực tiếp theo ID mà không kiểm tra quyền xem đối tượng. Chỉ dùng bản lab này với dữ liệu giả trong môi trường local.

## Chạy lab

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Migration tạo một ID tuần tự cho mỗi tài liệu hiện có. Tài liệu mới được cấp ID tự động. Có thể xem ID và chủ sở hữu trong pgAdmin bằng truy vấn:

```sql
SELECT id, title, owner_id
FROM documents_document
ORDER BY id;
```

## Tái hiện bằng Burp

1. Đăng nhập A2 và tạo tài liệu có nội dung thử nghiệm. Ghi ID của tài liệu trong bảng `documents_document`; không chia sẻ tài liệu cho A1.
2. Đăng nhập A1 và bắt một request dùng phiên A1.
3. Trong Repeater, gửi `GET /documents/<ID>/` với ID của A2. Response trả tiêu đề và nội dung tài liệu.
4. Nếu tài liệu có tệp, gửi `GET /documents/<ID>/download/` để kiểm tra tải tệp; có thể kiểm tra thêm `GET /documents/<ID>/preview/`.

Các route này yêu cầu đăng nhập nhưng tra cứu theo ID tuần tự mà không kiểm tra quyền xem tài liệu. Route danh sách và sửa tài liệu vẫn dùng policy phân quyền riêng.
