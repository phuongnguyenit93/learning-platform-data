Một API kiểm tra access token hợp lệ rồi coi mọi request đã xác thực đều được phép đọc hồ sơ bất kỳ; hệ thống đang nhầm authentication với authorization và không kiểm tra quyền trên tài nguyên cụ thể.
Ứng dụng ẩn nút Delete trong giao diện với người dùng thường nhưng endpoint DELETE vẫn xử lý request trực tiếp; kiểm soát chỉ ở client không ngăn người dùng gọi API bằng công cụ riêng.
Một người dùng có role analyst được phép xem báo cáo nhưng endpoint export dữ liệu không áp dụng cùng policy; dữ liệu tải xuống vượt quyền hiển thị trên màn hình.
RBAC cấp role admin cho mọi nhân viên vận hành để xử lý sự cố nhanh; quyền quản trị rộng tồn tại cả sau khi nhân viên chuyển nhóm và vi phạm least privilege.
Tổ chức tạo role riêng cho từng tổ hợp phòng ban, khu vực và loại dữ liệu; số role tăng theo cấp số nhân và việc rà soát quyền trở nên khó kiểm soát.
Role hierarchy cho phép manager kế thừa quyền employee nhưng một role con vô tình kế thừa cả quyền phê duyệt thanh toán; người dùng có quyền quản lý nhân sự lại được duyệt giao dịch.
Một nhân viên đồng thời giữ hai vai trò requester và approver trong cùng quy trình mua sắm; hệ thống không thực thi separation of duties nên người đó tự tạo và tự phê duyệt yêu cầu.
Quyền tạm thời của quản trị viên được cấp để xử lý incident nhưng không có thời điểm hết hạn; tài khoản tiếp tục giữ đặc quyền sau khi sự cố kết thúc.
Chính sách chỉ khai báo các trường hợp allow mà không có quy tắc deny-by-default; khi policy không khớp hoặc dịch vụ quyết định lỗi, ứng dụng mặc định cho phép truy cập.
Hai policy cùng áp dụng cho một tài nguyên, một policy allow và một policy deny; policy engine dùng kết quả đầu tiên theo thứ tự không ổn định nên quyết định thay đổi giữa các lần chạy.
ABAC cho phép xem hồ sơ nếu department của subject bằng department của resource; client có thể tự gửi department trong header và giả mạo thuộc tính chủ thể.
Policy ABAC dựa vào classification của tài liệu nhưng metadata được lấy từ request body do người dùng sửa được; tài liệu confidential bị gắn nhãn public để vượt quyền.
Quy tắc ABAC kiểm tra country của IP để giới hạn truy cập nhưng tin header X-Forwarded-For từ mọi nguồn; attacker tự đặt địa chỉ IP được phép.
Policy cho phép truy cập trong giờ làm việc theo timestamp client gửi; người dùng chỉnh đồng hồ hoặc sửa request context để vượt giới hạn thời gian.
Ứng dụng kiểm tra device posture ở lúc đăng nhập rồi cache kết quả nhiều giờ; thiết bị bị đánh dấu compromised sau đó vẫn truy cập dữ liệu nhạy cảm bằng quyết định cũ.
ABAC kiểm tra risk score từ hệ thống fraud nhưng khi dịch vụ đánh giá rủi ro timeout, policy engine coi giá trị thiếu là low risk và cho phép giao dịch.
Policy engine nhận resource owner từ cache nhưng chủ sở hữu đã thay đổi; cache chưa invalidated nên người dùng cũ tiếp tục truy cập tài nguyên sau khi chuyển quyền.
Một API nhận resource ID từ URL và chỉ kiểm tra người gọi đã đăng nhập; thay ID bằng ID của người khác cho phép đọc hoặc sửa bản ghi ngoài quyền, tạo lỗ hổng BOLA/IDOR.
Endpoint lấy hóa đơn theo order ID kiểm tra quyền trên order nhưng không kiểm tra invoice thuộc đúng order; attacker thay invoice ID để đọc hóa đơn của giao dịch khác.
API cho phép xem project nếu user thuộc organization nhưng không kiểm tra project thực sự thuộc organization trong path; thay organization ID và project ID kết hợp để vượt tenant boundary.
Query danh sách khách hàng lọc tenant ở endpoint list nhưng endpoint search và autocomplete quên thêm điều kiện tenant; dữ liệu của tenant khác xuất hiện qua tìm kiếm.
Endpoint bulk update nhận mảng object ID và kiểm tra quyền chỉ trên phần tử đầu tiên; attacker thêm ID của tài nguyên không được phép vào cùng batch.
GraphQL resolver kiểm tra quyền ở root query nhưng nested resolver trả về email và payment methods của object con mà không áp dụng authorization riêng.
API hỗ trợ field selection cho phép caller yêu cầu internalNotes hoặc riskFlags; endpoint kiểm tra quyền đọc object nhưng không giới hạn thuộc tính nhạy cảm theo field.
Ứng dụng bind trực tiếp request JSON vào model domain; caller thêm trường ownerId hoặc tenantId để chuyển quyền sở hữu tài nguyên mà không qua nghiệp vụ được phép.
Người dùng được phép sửa bài viết của mình nhưng endpoint update chỉ kiểm tra quyền trên bản ghi trước khi áp dụng patch; patch thay ownerId rồi lưu khiến lần sau attacker sở hữu bài viết.
Chức năng download tạo URL ký sẵn sau khi xác minh quyền một lần; URL sống nhiều ngày và vẫn truy cập được sau khi người dùng bị thu hồi quyền.
File chia sẻ qua presigned URL được chuyển sang tenant khác nhưng URL cũ không ràng buộc audience hoặc thời hạn ngắn; người nhận cũ tiếp tục tải file sau khi quyền chia sẻ bị thu hồi.
Ứng dụng dùng ACL theo object nhưng khi clone tài liệu, quyền của bản gốc được sao chép nguyên trạng; người tạo bản sao vô tình giữ danh sách người đọc và editor cũ.
Một thư mục cho phép kế thừa quyền xuống mọi file con; khi một file được đánh dấu confidential, hệ thống không ngắt inheritance và người đọc thư mục vẫn mở được file.
Quyền chia sẻ theo quan hệ ReBAC dựa trên membership của group; người dùng đã bị xóa khỏi group nhưng cache relationship còn hiệu lực và vẫn được truy cập tài liệu.
Policy cho phép người quản lý xem hồ sơ của cấp dưới dựa trên quan hệ trong HR graph; dữ liệu sơ đồ tổ chức cập nhật chậm sau khi nhân viên chuyển nhóm nên quyền cũ chưa bị thu hồi.
Người dùng tạo link chia sẻ công khai cho tài liệu rồi chuyển tài liệu sang chế độ private; link token không bị revoke nên tài liệu vẫn truy cập ẩn danh.
Ứng dụng kiểm tra quyền trên resource cha khi tạo comment nhưng không kiểm tra trạng thái resource; comment vẫn được thêm vào hồ sơ đã khóa hoặc lưu trữ.
API cho phép người dùng sửa metadata tài nguyên nhưng không phân biệt action update-description với update-classification; caller thay mức phân loại từ confidential xuống public.
Row-level security trong database lọc tenant theo session variable nhưng connection pool tái sử dụng connection mà không reset biến; request tiếp theo có thể chạy dưới tenant trước.
Ứng dụng chỉ lọc dữ liệu theo tenant ở tầng API; một báo cáo chạy truy vấn SQL trực tiếp bỏ qua filter và tổng hợp dữ liệu của nhiều tenant.
Search index không mang tenant ID hoặc ACL filter đầy đủ; người dùng tìm kiếm được tài liệu không có quyền dù trang chi tiết từ chối mở.
Cache response dùng resource ID làm cache key nhưng không đưa subject, tenant hoặc scope vào khóa; kết quả đã được phép cho user A được trả cho user B.
Policy decision point (PDP) timeout khi ứng dụng gọi kiểm tra quyền; policy enforcement point (PEP) fail-open để giữ availability và cho phép request không được đánh giá.
PDP hoạt động bình thường nhưng một service quên gọi PEP ở endpoint mới; policy trung tâm có đầy đủ rule nhưng không được thực thi trên đường truy cập này.
Gateway kiểm tra quyền ở edge nhưng backend cũng có thể truy cập trực tiếp từ mạng nội bộ; caller bỏ qua gateway và đi vào endpoint không có enforcement tương đương.
Microservice A gọi B bằng service identity có quyền rộng; A chuyển yêu cầu của user thường nhưng B chỉ thấy danh tính service và thực hiện hành động vượt quyền user, tạo confused deputy.
Token delegation truyền subject ban đầu nhưng service downstream chỉ kiểm tra client_id; dịch vụ thực hiện quyền của ứng dụng thay vì quyền được ủy quyền của người dùng.
Background job được enqueue khi người dùng còn quyền truy cập; trước lúc worker thực thi, quyền đã bị thu hồi nhưng job không kiểm tra lại authorization và vẫn xuất dữ liệu.
Scheduled export chạy bằng service account dùng chung có quyền đọc mọi tenant; cấu hình job thiếu tenant scope nên một lỗi tham số làm export chéo dữ liệu.
WebSocket xác thực và phân quyền lúc mở kết nối nhưng không kiểm tra lại khi membership hoặc role thay đổi; kết nối tồn tại lâu tiếp tục nhận sự kiện đã mất quyền.
Policy cache lưu quyết định allow trong thời gian dài; admin thu hồi quyền nhưng các node tiếp tục chấp nhận request tới khi cache hết TTL.
Policy bundle được rollout không đồng bộ giữa các replica; cùng một hành động bị allow ở node cũ và deny ở node mới gây kết quả không nhất quán.
Ứng dụng lưu quyền trong JWT quá lâu và không kiểm tra policy thay đổi phía server; người dùng giữ token cũ vẫn có đặc quyền sau khi bị hạ role.
Policy engine không phân biệt thuộc tính không xác định với giá trị false; thiếu dữ liệu classification bị diễn giải thành public và cấp quyền ngoài ý muốn.
Quy tắc deny chỉ áp dụng cho action read nhưng không áp dụng export, print hoặc share; người dùng bị cấm xem trực tiếp vẫn lấy dữ liệu qua chức năng khác.
Kiểm tra quyền diễn ra trước khi cập nhật resource nhưng trạng thái hoặc owner có thể thay đổi trước khi commit; race condition tạo TOCTOU và cho phép thao tác trên đối tượng đã đổi quyền.
API trả 404 cho object không tồn tại nhưng 403 cho object tồn tại ngoài quyền; attacker dò ID hợp lệ và suy luận sự hiện diện của tài nguyên.
Audit log chỉ ghi user đăng nhập và endpoint được gọi, không ghi subject, action, resource, policy version và decision; điều tra một lần truy cập trái phép không thể tái dựng lý do allow.
Nhóm ghi audit log sau khi thực hiện thao tác; nếu ghi log thất bại, hành động nhạy cảm vẫn hoàn tất mà không có dấu vết kiểm toán bắt buộc.
Quyền admin khẩn cấp được cấp qua quy trình break-glass nhưng không yêu cầu lý do, phê duyệt sau sự kiện hoặc cảnh báo; cơ chế khẩn cấp trở thành lối tắt đặc quyền thường xuyên.
Policy được chỉnh sửa trực tiếp trong production mà không version control, review hoặc test; thay đổi rule vô tình mở quyền cho nhóm người dùng rộng hơn.
Kiểm thử authorization chỉ xác nhận user hợp lệ nhận 200; không có negative tests cho user khác tenant, role thấp, object không sở hữu và trạng thái đã revoke.
Test suite dùng một admin fixture cho hầu hết endpoint; lỗi thiếu kiểm tra quyền đối với user thường không bị phát hiện vì fixture luôn có quyền cao.
Fuzzing API thay resource ID nhưng không thay tenant, owner, nested ID và action đồng thời; nhiều tổ hợp BOLA và escalation vẫn chưa được kiểm thử.
Ứng dụng kiểm tra quyền dựa trên tên role hiển thị ở UI thay vì principal và policy claims tin cậy từ server; client sửa giá trị role trong request để nâng quyền.
Policy cho phép approver phê duyệt khoản chi dưới ngưỡng nhưng không kiểm tra tổng các khoản đã chia nhỏ; người yêu cầu tách một giao dịch lớn thành nhiều giao dịch nhỏ để né giới hạn.
Người dùng có quyền đọc báo cáo tổng hợp nhưng không được xem từng bản ghi; API trả aggregate đúng nhưng endpoint drill-down cho phép suy ngược dữ liệu cá nhân mà không có policy bổ sung.
Quyền truy cập dữ liệu nhạy cảm phụ thuộc consent của chủ thể; consent đã bị rút nhưng policy cache hoặc bản sao consent ở dịch vụ downstream chưa cập nhật.
