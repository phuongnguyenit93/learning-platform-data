Một API xác minh access token hợp lệ rồi cho phép mọi request đọc hoặc sửa mọi tài nguyên; hệ thống nhầm authentication với policy authorization và không đánh giá principal, action, resource cùng context.
Một endpoint mới được triển khai nhưng chưa có policy allow tương ứng; enforcement point mặc định cho phép khi PDP không tìm thấy rule, trái với nguyên tắc deny-by-default.
Trong hệ thống kết hợp RBAC và PBAC, role RBAC được dùng làm thuộc tính principal; XACML policy combining algorithm là permit-overrides dù policy set có cả Permit và Deny, khiến rule allow rộng thắng rule deny tài nguyên nhạy cảm.
Nhóm dùng first-applicable trong XACML nhưng sắp xếp rule allow tổng quát trước rule deny cụ thể; kết quả phụ thuộc thứ tự và lệnh cấm không bao giờ được xét.
Policy engine trả NotApplicable khi không có rule khớp nhưng PEP diễn giải trạng thái này thành Permit; request không có chính sách cấp quyền vẫn được thực hiện.
PDP trả Indeterminate do thiếu thuộc tính bắt buộc nhưng gateway coi lỗi đánh giá là quyết định cho phép; lỗi dữ liệu context trở thành đường bypass authorization.
Cedar policy có cả permit và forbid áp dụng cho cùng request; nhóm kỳ vọng permit ưu tiên nhưng ngữ nghĩa forbid-overrides khiến request bị từ chối theo thiết kế.
Cedar policy chỉ khai báo principal và action mà bỏ qua resource type; rule rộng hơn dự kiến áp dụng cho nhiều loại tài nguyên trong cùng namespace.
Một Cedar policy tham chiếu action hoặc entity type không có trong schema; lỗi tên bị phát hiện muộn khi request chạy thay vì được validate trong pipeline triển khai.
Cedar entity hierarchy biểu diễn membership nhóm nhưng dữ liệu quan hệ không được cập nhật sau khi nhân viên rời nhóm; policy tiếp tục cấp quyền dựa trên quan hệ cũ.
Cedar policy template được tái sử dụng nhưng binding của tenant hoặc resource scope bị điền sai; một policy dành cho nhóm khách hàng áp dụng nhầm sang tenant khác.
Một Cedar policy kiểm tra thuộc tính context do client tự gửi như isManagedDevice; attacker tự đặt true và vượt qua điều kiện yêu cầu thiết bị được quản lý.
OPA/Rego rule trả về undefined khi input thiếu thuộc tính; ứng dụng bọc kết quả bằng logic mặc định Permit thay vì xử lý trường hợp không xác định theo hướng từ chối.
Rego policy dùng biến chưa được ràng buộc an toàn trong biểu thức; bundle không compile ở môi trường production dù unit test cục bộ không chạy đúng cùng phiên bản.
OPA policy kiểm tra input.resource.tenant_id nhưng resource object được lấy trực tiếp từ request; caller sửa tenant_id trong payload và tự gắn tài nguyên sang tenant được phép.
OPA bundle được cập nhật trên một số replica nhưng các node khác giữ bundle cũ; cùng một request nhận kết quả khác nhau tùy gateway xử lý.
OPA bundle tải qua mạng không xác minh chữ ký hoặc nguồn phát hành; attacker thay policy bundle và mở rộng quyền mà không cần sửa ứng dụng.
Decision log của OPA ghi toàn bộ input context gồm access token, email và dữ liệu cá nhân; hệ thống audit tạo thêm kho bí mật có quyền truy cập quá rộng.
Nhóm bật decision logging nhưng không gắn decision ID với request ID của dịch vụ; khi điều tra một quyết định allow, không thể liên kết log PDP với thao tác thực tế.
Policy test chỉ kiểm tra trường hợp allow điển hình; thiếu negative test cho missing attributes, wrong tenant, revoked relationship và resource classification cao hơn.
Rego test đạt coverage dòng cao nhưng không kiểm tra nhánh deny, undefined và boundary condition; thay đổi logic vẫn có thể mở quyền mà test suite không phát hiện.
Pipeline CI chỉ kiểm tra cú pháp Rego mà không chạy test, schema validation hoặc policy simulation; policy sai ngữ nghĩa được phát hành dù compile thành công.
XACML PDP trả quyết định Permit kèm obligation yêu cầu che một số trường; PEP chỉ kiểm tra decision và bỏ qua obligation nên dữ liệu nhạy cảm được trả nguyên vẹn.
XACML Advice được dùng như thể là obligation bắt buộc; PEP từ chối request khi không thực hiện advice vốn chỉ mang tính khuyến nghị theo cấu hình.
PDP tạo obligation yêu cầu ghi audit trước khi thực hiện giao dịch; PEP thực hiện nghiệp vụ trước rồi mới ghi log, khiến thao tác vẫn thành công khi audit sink đã lỗi.
Một PEP kiểm tra quyền ở API gateway nhưng endpoint nội bộ vẫn có thể được gọi trực tiếp; caller bỏ qua gateway và không gặp cùng policy enforcement.
PDP gọi attribute provider để lấy department nhưng provider trả dữ liệu cache cũ sau khi nhân viên chuyển bộ phận; quyết định cấp quyền không phản ánh trạng thái hiện tại.
ABAC policy dựa trên device posture nhưng thuộc tính do agent không được xác thực gửi lên; attacker giả mạo compliant=true và truy cập tài nguyên.
Policy kiểm tra vị trí địa lý từ X-Forwarded-For nhưng không giới hạn proxy tin cậy; client tự đặt IP được allowlist và vượt qua điều kiện location.
Điều kiện thời gian trong policy dùng timestamp từ request thay vì đồng hồ tin cậy phía server; caller thay giờ gửi lên để truy cập ngoài khung thời gian cho phép.
Thuộc tính classification bị thiếu do dịch vụ metadata tạm ngừng; policy engine coi giá trị null tương đương public và cho phép tải tài liệu confidential.
Policy kiểm tra consent=true nhưng consent service bị timeout; adapter trả giá trị mặc định true để tránh lỗi người dùng và cho phép xử lý dữ liệu sau khi consent đã rút.
PDP timeout khi tải cao và PEP được cấu hình fail-open; attacker có thể tạo áp lực lên policy service để biến lỗi availability thành bypass quyền.
PDP timeout và PEP fail-closed nhưng không phân biệt lỗi hạ tầng với deny policy; toàn bộ thao tác đọc công khai cũng bị gián đoạn khi dịch vụ policy gặp sự cố.
Policy decision được cache chỉ theo resource ID mà không bao gồm principal, action hoặc context; quyết định allow của người dùng A bị tái sử dụng cho người dùng B.
Cache key của PDP bỏ qua tenant ID; cùng một resource identifier tồn tại ở nhiều tenant và kết quả authorization bị dùng chéo.
Admin thu hồi quyền nhưng cache decision allow có TTL dài; các PEP tiếp tục cho phép request tới khi cache hết hạn.
Policy bundle được rollout không đồng bộ giữa các vùng; một vùng áp dụng rule mới còn vùng khác vẫn dùng policy cũ trong cùng thời điểm.
Ứng dụng lưu policy decision vào JWT claim dài hạn; quyền bị thu hồi phía server nhưng token cũ tiếp tục mang claim allow tới khi hết hạn.
Policy đánh giá quyền trước khi resource owner thay đổi; một giao dịch cập nhật đồng thời làm trạng thái tài nguyên thay đổi trước commit và tạo race condition TOCTOU.
Một request bulk gồm hàng trăm resource ID chỉ được authorize trên phần tử đầu tiên; các ID còn lại được xử lý mà không có quyết định riêng.
API search áp dụng policy sau khi lấy dữ liệu và phân trang; tổng số kết quả cùng metadata vẫn tiết lộ tài nguyên mà subject không được phép nhìn thấy.
Một báo cáo export chạy truy vấn trực tiếp bỏ qua policy filter đã áp dụng ở màn hình; người dùng tải được bản ghi từ nhiều tenant dù trang danh sách đã giới hạn đúng.
Policy cho phép xem object nhưng không giới hạn field; response trả thêm internalNotes, riskScore và thông tin định danh không thuộc quyền của caller.
GraphQL root resolver gọi PDP nhưng nested resolver không kiểm tra quyền cho object con; caller truy cập trường nhạy cảm qua quan hệ lồng nhau.
Một service dùng danh tính service account để gọi downstream thay cho người dùng; downstream chỉ thấy service principal và thực hiện thao tác rộng hơn quyền được ủy quyền của subject ban đầu.
Delegation token truyền subject nhưng không ràng buộc audience và scope; token dùng cho một dịch vụ bị phát lại ở dịch vụ khác có quyền rộng hơn.
Background job được tạo khi người dùng còn quyền; trước lúc worker thực thi, quyền đã bị thu hồi nhưng worker không đánh giá lại policy.
WebSocket chỉ authorize lúc handshake; membership của user bị thu hồi nhưng kết nối dài hạn vẫn nhận event từ tài nguyên không còn được phép.
Relationship graph dùng cho ReBAC cập nhật chậm sau khi quyền chia sẻ bị xóa; PDP tiếp tục thấy quan hệ cũ và cho phép truy cập tài liệu.
ACL của thư mục được kế thừa xuống object con; khi một tài liệu được phân loại confidential, policy không áp dụng deny override nên người có quyền thư mục vẫn đọc được.
Policy cho phép approver duyệt từng khoản chi dưới ngưỡng nhưng không tính tổng giao dịch liên quan; requester chia nhỏ khoản tiền để né giới hạn phê duyệt.
Quy trình break-glass cấp quyền khẩn cấp nhưng không giới hạn thời gian, không yêu cầu lý do và không có hậu kiểm; quyền tạm thời trở thành đặc quyền lâu dài, vi phạm least privilege.
Policy admin có thể vừa viết rule vừa tự phê duyệt và triển khai rule; thiếu separation of duties khiến một người có thể âm thầm mở rộng quyền của chính mình.
Policy được sửa trực tiếp trên production mà không version control; khi phát hiện cấp quyền sai, nhóm không biết chính xác rule nào đã thay đổi và không thể rollback có kiểm chứng.
Audit log chỉ ghi Permit hoặc Deny mà không lưu policy version, principal, action, resource, context source và obligation; quyết định không thể tái dựng khi có tranh chấp.
Policy simulator dùng dữ liệu giả khác cấu trúc production; rule vượt qua thử nghiệm nhưng lỗi thuộc tính hoặc entity relationship xuất hiện khi triển khai thật.
Nhóm dùng mutation testing thay đổi điều kiện policy nhưng test vẫn xanh; điều đó cho thấy bộ test không phát hiện được thay đổi có thể mở rộng quyền.
PDP latency tăng do mỗi request gọi nhiều attribute provider tuần tự; hệ thống cần đo thời gian từng bước và cân nhắc batching hoặc partial evaluation có kiểm soát.
OPA partial evaluation tạo residual policy theo một tập input cố định; nhóm tái sử dụng kết quả sau khi tenant hoặc resource attributes thay đổi và đưa ra quyết định sai.
Policy data snapshot được cập nhật độc lập với policy bundle; rule mới giả định thuộc tính mới nhưng replica vẫn dùng dữ liệu cũ và trả kết quả không nhất quán.
Canary rollout policy mới chỉ theo dõi tỷ lệ lỗi HTTP mà không so sánh decision distribution; một rule mở rộng quyền có thể phát hành mà không tạo lỗi kỹ thuật.
Sau khi rollback policy bundle, cache decision và compiled policy ở một số node chưa được làm mới; hành vi vẫn theo rule lỗi dù phiên bản bundle đã quay lại.
Kiểm thử authorization chỉ xác nhận administrator được phép; thiếu ma trận test cho anonymous, user thường, cross-tenant, delegated identity và resource owner khác.
Fuzzing policy chỉ thay đổi giá trị scalar mà không thử missing, null, kiểu dữ liệu sai, array lớn hoặc entity reference vòng; nhiều đường xử lý lỗi chưa được kiểm tra.
