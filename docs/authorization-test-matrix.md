# Ma trận kiểm thử phân quyền KLCN85

Tài liệu này mô tả hành vi phân quyền hiện tại theo `UserProfile.role`, phòng ban và các lượt `DocumentShare` còn hiệu lực. Trong bản lab, ba URL chi tiết, tải xuống và xem trước tài liệu cố ý có IDOR: mọi tài khoản đã đăng nhập có thể truy cập trực tiếp theo ID. Quyền Django như `is_staff`, `is_superuser`, group và permission không thay thế vai trò ứng dụng.

| Tài khoản / vai trò | Tài nguyên | Hành động | Kết quả mong đợi | Test kiểm chứng |
|---|---|---|---|---|
| Chưa đăng nhập | Danh sách, tạo, chi tiết, sửa tài liệu | GET/POST | Chuyển tới đăng nhập; POST không làm đổi dữ liệu | `documents/tests.py::test_anonymous_requests_redirect_to_login` |
| Chưa đăng nhập | URL xem trước / tải tệp | GET trực tiếp | Chuyển tới đăng nhập; không nhận nội dung tệp | `documents/test_file_management.py::test_anonymous_cannot_open_direct_download_or_preview_url` |
| Chưa đăng nhập | Thư mục | Danh sách, tạo, mở, quản lý | Chuyển tới đăng nhập; không truy cập dữ liệu thư mục | `documents/tests.py::test_anonymous_requests_redirect_to_login` |
| Chưa đăng nhập | Quản lý tài khoản | Danh sách, tạo, sửa; GET/POST | Chuyển tới đăng nhập; không tạo hoặc khóa tài khoản | `documents/test_day5.py::test_anonymous_requests_redirect_to_login_without_deleting`, `accounts/test_user_management.py::test_anonymous_cannot_open_or_post_account_management_urls` |
| Chưa đăng nhập | Quản lý / thu hồi chia sẻ | GET/POST | Chuyển tới đăng nhập; lượt chia sẻ không thay đổi | `sharing/tests.py::test_anonymous_cannot_open_or_post_share_management_urls` |
| Nhân viên chủ sở hữu | Tài liệu của mình | Danh sách, chi tiết, sửa | Được phép; trường chủ sở hữu/phòng ban không thể giả mạo qua POST | `documents/tests.py::test_list_respects_owner_department_and_admin_role`, `test_detail_allows_owner_head_of_department_and_admin`, `test_owner_and_admin_can_edit_only_title_and_content` |
| Nhân viên cùng phòng, không phải chủ sở hữu | Tài liệu không chia sẻ | Chi tiết, sửa trực tiếp | Chi tiết bị IDOR và trả nội dung; sửa bị từ chối, dữ liệu không đổi | `documents/tests.py::test_any_logged_in_employee_can_read_foreign_detail_by_id`, `test_employee_cannot_edit_other_owner_or_department` |
| Nhân viên phòng ban khác | Tài liệu không chia sẻ | Chi tiết, sửa, xem trước/tải trực tiếp | Chi tiết, xem trước và tải tệp bị IDOR; sửa bị từ chối | `documents/test_file_management.py::test_idor_on_normal_detail_renders_foreign_document_and_inline_pdf`, `test_download_and_preview_idor_ignore_share_status_for_logged_in_users` |
| Người nhận cùng phòng có quyền `view` còn hạn | Tài liệu đã chia sẻ | Danh sách, chi tiết, xem trước, tải, sửa | Được liệt kê và xem/tải; sửa bị từ chối | `sharing/tests.py::test_owner_grants_view_and_recipient_cannot_edit`, `documents/test_file_management.py::test_download_and_preview_idor_ignore_share_status_for_logged_in_users` |
| Người nhận cùng phòng có quyền `edit` còn hạn | Tài liệu đã chia sẻ | Sửa bằng GET và POST | Được sửa qua policy; quyền này không cấp quyền xóa | `sharing/tests.py::test_edit_share_allows_recipient_to_edit_through_post`, `documents/test_file_management.py::test_document_move_requires_owner_or_admin_and_matching_folder_owner_and_department` |
| Người nhận có lượt chia sẻ hết hạn | Tài liệu đã chia sẻ | Danh sách, chi tiết, sửa, xem trước/tải trực tiếp | Mất quyền xem trong danh sách và quyền sửa; URL chi tiết/tệp vẫn bị IDOR | `sharing/tests.py::test_expired_share_hides_list_and_edit_but_detail_idor_remains`, `documents/test_file_management.py::test_download_and_preview_idor_ignore_share_status_for_logged_in_users` |
| Người nhận có lượt chia sẻ đã thu hồi | Tài liệu đã chia sẻ | Danh sách, chi tiết, sửa, xem trước/tải trực tiếp | Mất quyền xem trong danh sách và quyền sửa; URL chi tiết/tệp vẫn bị IDOR | `sharing/tests.py::test_owner_can_revoke_with_post_and_csrf_and_access_ends`, `documents/test_file_management.py::test_download_and_preview_idor_ignore_share_status_for_logged_in_users` |
| Người nhận khác phòng ban | Tài liệu được chia sẻ | Cấp quyền và truy cập trực tiếp | Không được cấp lượt chia sẻ hợp lệ; URL chi tiết/tệp vẫn bị IDOR | `sharing/tests.py::test_owner_and_admin_cannot_share_with_other_department`, `documents/test_file_management.py::test_idor_on_normal_detail_renders_foreign_document_and_inline_pdf` |
| Trưởng phòng | Tài liệu trong phòng ban | Danh sách, chi tiết | Được xem tài liệu của phòng, kể cả sau khi lượt chia sẻ của họ bị thu hồi | `documents/tests.py::test_list_respects_owner_department_and_admin_role`, `sharing/tests.py::test_non_grantor_cannot_revoke_and_department_head_keeps_base_access` |
| Trưởng phòng | Tài liệu nhân viên cùng phòng | Sửa GET/POST | Bị từ chối; tài liệu không đổi | `documents/tests.py::test_head_can_view_but_cannot_edit_employee_document` |
| Admin ứng dụng | Tài liệu bất kỳ | Danh sách, chi tiết, sửa, xóa | Được phép theo quyền admin hiện có | `documents/tests.py::test_list_respects_owner_department_and_admin_role`, `test_detail_allows_owner_head_of_department_and_admin`, `test_owner_and_admin_can_edit_only_title_and_content`, `documents/test_day5.py::test_admin_confirmation_get_is_safe_and_csrf_post_deletes` |
| Admin ứng dụng | Chia sẻ | Cấp/thu hồi | Có thể cấp trên tài liệu bất kỳ cho người nhận cùng phòng và thu hồi lượt do người khác cấp | `sharing/tests.py::test_admin_can_share_any_document_to_its_department`, `test_admin_can_revoke_another_users_grant` |
| Bất kỳ tài khoản | Tìm kiếm | Truy vấn tên tài liệu không được phép xem | Policy lọc tài liệu trước tìm kiếm; kết quả và số dòng chỉ gồm tài liệu được phép xem | `documents/test_file_management.py::test_folder_does_not_grant_document_access_and_search_only_filters_visible_documents` |
| Người gửi POST giả mạo owner/department/role/ID hoặc quyền Django | Tài liệu / tài khoản | Tạo, sửa | Máy chủ chỉ dùng trường hợp lệ và danh tính hiện tại; không nâng quyền bằng dữ liệu gửi thêm | `documents/tests.py::test_create_assigns_current_owner_and_department_despite_forged_post`, `test_owner_and_admin_can_edit_only_title_and_content`, `accounts/test_user_management.py::test_privileged_django_fields_are_rejected_on_create_and_update` |
| Tài khoản bị khóa (`is_active=False`) | Đăng nhập | POST | Không tạo phiên đăng nhập | `accounts/test_user_management.py::test_lock_unlock_events_and_locked_user_cannot_log_in` |
| Người dùng ngoài phạm vi | URL chi tiết, tải tệp, quản lý chia sẻ | GET/POST | URL chi tiết/tải tệp bị IDOR và ghi `allowed`; quản lý chia sẻ bị từ chối và ghi `denied`; log không chứa nội dung tài liệu | `audit/tests.py::test_direct_document_idor_is_allowed_but_sharing_is_denied` |
| Test suite | JSONL kiểm toán | Ghi sự kiện test | Dùng tệp tạm ngoài `logs/audit.jsonl` của web; không thay đổi tệp log đang dùng | `audit/tests.py::test_test_runner_routes_jsonl_events_away_from_live_web_log` |

## Ghi chú về mã phản hồi

Các nhánh policy hiện dùng 404 khi ẩn tài nguyên không được phép biết đến và 403 cho một số thao tác bị cấm trên tài nguyên đã thấy được. Cả hai đều là kết quả từ chối; test nên xác nhận dữ liệu không bị trả về hoặc thay đổi, thay vì buộc mọi nhánh dùng chung một mã trạng thái.

## Route lab cố ý dễ tổn thương

Các route thực tế `/documents/<ID>/`, `/documents/<ID>/download/` và `/documents/<ID>/preview/` dùng ID số tuần tự và cố ý bỏ kiểm tra quyền xem tài liệu. Đây là hành vi của bản lab để tái hiện IDOR; không triển khai bản này với dữ liệu thật.

## Các giới hạn ngoài phạm vi ma trận này

- Ma trận không kiểm tra quyền ở Django Admin site; đó là bề mặt quản trị riêng với quyền Django.
- Việc xem trước DOCX/XLSX dùng endpoint xem trước có cùng lỗi IDOR; test tệp xác nhận tài khoản đã đăng nhập nhận được nội dung.
- Thư mục chỉ tổ chức tài liệu, không cấp quyền xem cho tài liệu trong thư mục.
