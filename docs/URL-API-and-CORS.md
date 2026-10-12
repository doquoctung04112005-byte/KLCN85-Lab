# Kịch bản 3 — URL/API và CORS

## Mục tiêu

Theo kế hoạch tuần 2 (14–16/10), kiểm tra một chức năng của lab qua URL trực tiếp, phương thức HTTP và CORS. Thu thập bằng chứng để phân biệt:

1. kiểm soát truy cập đối tượng (IDOR/BOLA);
2. phương thức HTTP mà từng URL chấp nhận và hiệu lực của CSRF;
3. hành vi CORS của trình duyệt.

Đây là quy trình kiểm thử trên môi trường local với dữ liệu giả. Không chạy các bước thay đổi hoặc xóa dữ liệu trên hệ thống thật.

## Hiện trạng cần biết trước khi kiểm thử

- Ứng dụng đang là Django web app, với các route ở `/documents/` và `/sharing/`.
- `djangorestframework` có trong dependency và `rest_framework` có trong `INSTALLED_APPS`, nhưng URL gốc hiện chưa khai báo API endpoint hoặc router API. Không gọi một route API giả định là đang tồn tại; nếu nhóm muốn kiểm thử API thì cần xác định endpoint cụ thể trước.
- Các route xem chi tiết, tải xuống và xem trước tài liệu yêu cầu đăng nhập nhưng cố ý không kiểm tra quyền xem đối tượng:
  - `GET /documents/<ID>/`
  - `GET /documents/<ID>/download/`
  - `GET /documents/<ID>/preview/`
- Danh sách tài liệu, sửa tài liệu, thư mục và thao tác chia sẻ có policy riêng; không suy luận rằng mọi route đều mắc cùng lỗi.
- Cấu hình hiện tại không có Django CORS middleware hoặc thiết lập CORS nhìn thấy trong `settings.py`; dependency CORS chuyên dụng cũng không có trong `requirements.txt`. Dự kiến không có header `Access-Control-Allow-*` do chính ứng dụng phát ra. Proxy hoặc môi trường khác có thể thêm header, nên phải ghi lại response thực tế.
- `CsrfViewMiddleware` đang bật. Các thao tác thay đổi dữ liệu có bảo vệ CSRF và/hoặc giới hạn phương thức HTTP.
- CORS không thay thế xác thực, phân quyền đối tượng hoặc CSRF. CORS quyết định liệu trình duyệt có cho mã JavaScript từ origin khác đọc response hay không; nó không ngăn gửi mọi loại request và không phải cơ chế cấp quyền tài liệu.

## Chuẩn bị

1. **Chốt phạm vi và môi trường.** Dùng bản local, database kiểm thử hoặc dữ liệu có thể khôi phục. Chỉ dùng tài liệu giả; không dùng thông tin cá nhân hay tài liệu thật.
2. **Khởi động ứng dụng theo README.** PostgreSQL phải hoạt động, `.env` phải được cấu hình trên máy cá nhân, migration đã chạy và `manage.py check` thành công. Giữ nguyên cấu hình dự án trong lúc đo baseline.
3. **Tạo hoặc xác nhận tài khoản kiểm thử.** Dùng ít nhất hai tài khoản nhân viên khác nhau (A1 và A2); nên có một cặp cùng phòng ban và một cặp khác phòng ban. Nếu kiểm tra vai trò, dùng thêm trưởng phòng và admin ứng dụng. Không dùng Django `is_staff`/`is_superuser` thay cho `UserProfile.role`.
4. **Tạo fixture tài liệu.** Đăng nhập A2, tạo một tài liệu văn bản có nội dung đánh dấu giả và một tài liệu có tệp PDF/ảnh nếu cần thử tải/xem trước. Ghi lại ID, chủ sở hữu, phòng ban và trạng thái chia sẻ. Giữ một tài liệu không chia sẻ với A1 để làm ca IDOR.
5. **Ghi baseline của chủ sở hữu.** Khi đăng nhập A2, mở URL chi tiết của tài liệu và, nếu có tệp, URL tải xuống/xem trước. Ghi nhận status, nội dung/loại response và các header liên quan. Đây là đối chứng cho request của A1.
6. **Mở nơi ghi bằng chứng.** Dùng Burp Suite Repeater/Proxy hoặc công cụ HTTP tương đương. Lưu thời điểm, tài khoản/role, URL, method, status, header và kết quả quan sát. Che cookie phiên, mật khẩu, CSRF token và nội dung nhạy cảm trước khi chia sẻ ảnh chụp.

## Các bước kiểm thử tuần tự

### A. Kiểm tra URL trực tiếp và quyền đối tượng

7. **Đăng nhập A1.** Dùng phiên của A1; xác nhận A1 không sở hữu và không được chia sẻ tài liệu thử nghiệm của A2.
8. **Thử URL chi tiết trực tiếp.** Trong Repeater, gửi `GET /documents/<ID-của-A2>/` với cookie phiên A1. Ghi status và kiểm tra response có tiêu đề/nội dung tài liệu hay không. Trong lab hiện tại, đây là ca IDOR dự kiến trả nội dung tài liệu cho tài khoản đã đăng nhập.
9. **Thử các URL file trực tiếp.** Với tài liệu có attachment, gửi:
   - `GET /documents/<ID-của-A2>/download/`
   - `GET /documents/<ID-của-A2>/preview/`

   Ghi status, `Content-Type`, `Content-Disposition`, `Cache-Control` và việc response có chứa/trình bày nội dung file hay không. Ma trận hiện tại dự kiến tài khoản đã đăng nhập có thể tải/xem file bất kể quyền chia sẻ.
10. **So sánh các trạng thái quyền.** Lặp lại với tài liệu của chính A1, tài liệu được chia sẻ còn hạn, lượt chia sẻ hết hạn/đã thu hồi và tài liệu của phòng ban khác. Không tạo thêm quyền chia sẻ chỉ để làm một ca “đẹp”; ghi rõ trạng thái thực tế. Kết quả từ các URL IDOR không được nhầm với quyền xem qua danh sách.
11. **Đối chiếu route có policy.** Thử danh sách hoặc sửa tài liệu của A2 bằng A1 qua UI/URL tương ứng. Danh sách phải chỉ chứa tài liệu mà policy cho phép; thao tác sửa trái phép phải bị từ chối và dữ liệu không đổi. Ghi nhận mã 403 hoặc 404 theo nhánh thực tế; cả hai đều có thể là từ chối hợp lệ.

### B. Kiểm tra phương thức HTTP và CSRF

12. **Lập danh sách method từ route/view, rồi xác minh response.** Các route chi tiết, download, preview và folder detail chỉ định `GET`; create/edit/delete và quản lý chia sẻ có các method giới hạn riêng (thường `GET`/`POST`), còn thu hồi chia sẻ chỉ nhận `POST`. Với từng endpoint đã chọn, ghi các method đã thử, status và header `Allow` nếu có.
13. **Bắt đầu bằng request không làm thay đổi dữ liệu.** Thử `GET`, `HEAD`, `OPTIONS` và một method không được endpoint hỗ trợ như `PUT` trên tài liệu giả; ghi lại response nhưng không mặc định `OPTIONS` là CORS preflight thành công. Endpoint giới hạn method có thể trả `405 Method Not Allowed`; status/header thực tế là bằng chứng cần lưu.
14. **Kiểm tra POST/CSRF chỉ trên dữ liệu thử nghiệm.** Dùng form hợp lệ và CSRF token do ứng dụng cấp để kiểm tra thao tác được phép trên fixture. Sau đó, nếu cần kiểm tra thiếu CSRF, thực hiện với fixture có thể khôi phục và một thao tác không nguy hiểm; xác nhận request bị từ chối và dữ liệu không thay đổi. Không gửi POST xóa hoặc cập nhật tùy ý tới tài liệu cần giữ.
15. **Xác minh tính toàn vẹn sau mỗi request thay đổi.** Kiểm tra lại tiêu đề/nội dung, owner, department, lượt chia sẻ và sự tồn tại của file. Nếu có khác biệt ngoài dự kiến, dừng kiểm thử, lưu request/response đã che bí mật và khôi phục fixture.

### C. Kiểm tra CORS

16. **Chọn endpoint GET không gây thay đổi.** Dùng URL chi tiết của fixture đăng nhập được; thử cả endpoint mà A1 có quyền và endpoint IDOR để tách bạch tác động của CORS với kiểm soát quyền.
17. **Gửi preflight có chủ đích.** Gửi `OPTIONS` đến endpoint với `Origin` của một trang khác origin và các header preflight, ví dụ:

   ```http
   OPTIONS /documents/<ID>/ HTTP/1.1
   Host: 127.0.0.1:8000
   Origin: http://localhost:3000
   Access-Control-Request-Method: GET
   Access-Control-Request-Headers: content-type
   ```

   Ghi status và các header `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Credentials` và `Vary`. Một response `200` hoặc `204` tự nó không chứng minh CORS được cho phép; phải kiểm tra header.
18. **So sánh origin.** Lặp lại với origin cùng origin (đối chứng), origin khác được nhóm kiểm soát và một origin không tin cậy, ví dụ `http://evil.example`. Không thêm origin thử nghiệm vào cấu hình ứng dụng. Ghi rõ origin nào được trình duyệt phép đọc response theo header thực nhận.
19. **Phân biệt kiểm tra bằng HTTP client và trình duyệt.** Burp/curl chỉ cho thấy response header; chúng không thực thi chính sách CORS của trình duyệt. Nếu cần xác minh end-to-end, chạy một trang thử nghiệm tĩnh trên origin khác, gọi endpoint bằng `fetch`, ghi kết quả thành công/lỗi và giữ nguyên dữ liệu giả. Với request cookie/session cross-origin, ghi riêng việc dùng credentials, `SameSite` cookie và `Access-Control-Allow-Credentials`; không kết luận dựa trên preflight đơn lẻ.
20. **Đọc kết quả theo đúng lớp bảo vệ.** Nếu không có `Access-Control-Allow-Origin`, trình duyệt không cho JavaScript khác origin đọc response, nhưng request GET vẫn có thể tới server và lỗi IDOR vẫn tồn tại. Nếu CORS cho phép origin đọc response, đó là rủi ro chia sẻ dữ liệu giữa origin, nhưng vẫn phải xác định thêm request có xác thực hay không và policy đối tượng có cho phép không. CORS không chứng minh người dùng được cấp quyền.

## Tiêu chí hoàn thành và bằng chứng cần nộp

- Có bảng ca thử gồm tài khoản/role, trạng thái sở hữu/chia sẻ/phòng ban, URL, method, status, header chính và kết luận.
- Có ít nhất một request/response chứng minh kết quả truy cập trực tiếp khác chủ sở hữu; có đối chứng từ chủ sở hữu.
- Có kết quả GET và method không được hỗ trợ trên endpoint đã chọn; thao tác thay đổi chỉ thử trên fixture và xác nhận dữ liệu sau thử.
- Có response preflight và so sánh header CORS giữa các origin; nếu dùng trình duyệt, lưu kết quả `fetch` từ origin khác.
- Bằng chứng đã che cookie, session ID, CSRF token, mật khẩu và dữ liệu không thuộc fixture.
- Ghi riêng lỗi cố ý của lab (IDOR ở detail/download/preview) với kết quả CORS. Không ghi nhận “CORS chặn truy cập” chỉ vì trình duyệt không cho JavaScript đọc response.
- Không thêm endpoint API, dependency CORS hoặc cấu hình CORS trong phạm vi kịch bản này. Nếu giảng viên yêu cầu API thật hoặc whitelist origin, chốt endpoint/origin được phép và lập thay đổi riêng trước khi triển khai.

## Test hồi quy hiện có

Sau khi hoàn tất kiểm thử thủ công, chạy các test liên quan để xác nhận baseline dự án vẫn hoạt động:

```powershell
.\.venv\Scripts\python.exe manage.py test documents.tests documents.test_file_management sharing.tests audit.tests
```

Các test liên quan đã có trong repository gồm kiểm thử IDOR ở detail/download/preview, trạng thái share hết hạn/thu hồi, phân quyền danh sách/sửa và log audit. Kết quả test không thay thế bằng chứng request/response của CORS vì hiện chưa có API/CORS config trong ứng dụng.
