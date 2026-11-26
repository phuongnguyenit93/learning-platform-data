Bạn sẽ giải thích mô hình ABAC quyết định quyền truy cập dựa trên thuộc tính của chủ thể, tài nguyên, hành động và môi trường như thế nào?
Bạn sẽ phân biệt ABAC với RBAC và ReBAC về cách biểu diễn quyền, khả năng mở rộng và độ phức tạp vận hành ra sao?
Bạn sẽ xác định khi nào chính sách dựa trên vai trò không đủ linh hoạt và cần bổ sung thuộc tính ngữ cảnh như thế nào?
Bạn sẽ xây dựng mô hình thuộc tính cho subject, resource, action và environment phù hợp với miền nghiệp vụ ra sao?
Bạn sẽ phân biệt thuộc tính chủ thể như phòng ban, cấp độ truy cập và trạng thái tuyển dụng với thuộc tính tài nguyên như phân loại dữ liệu và chủ sở hữu như thế nào?
Bạn sẽ mô hình hóa thuộc tính hành động để phân biệt đọc, tạo, sửa, xóa, phê duyệt và xuất dữ liệu ra sao?
Bạn sẽ lựa chọn thuộc tính môi trường như thời gian, vị trí mạng, thiết bị và mức rủi ro để đưa vào quyết định truy cập như thế nào?
Bạn sẽ xác định thuộc tính nào là tĩnh, thuộc tính nào thay đổi theo request và cách cập nhật chúng để tránh quyết định dựa trên dữ liệu cũ ra sao?
Bạn sẽ thiết kế schema và kiểu dữ liệu thuộc tính thống nhất giữa nhiều service và nguồn danh tính như thế nào?
Bạn sẽ kiểm soát namespace, tên, kiểu và ý nghĩa thuộc tính để tránh hai hệ thống diễn giải cùng một giá trị khác nhau ra sao?
Bạn sẽ giải thích kiến trúc XACML hoặc mô hình ABAC tương đương gồm Policy Enforcement Point, Policy Decision Point, Policy Information Point và Policy Administration Point như thế nào?
Bạn sẽ phân biệt PEP, PDP, PIP và PAP về trách nhiệm trong một luồng kiểm soát truy cập ra sao?
Bạn sẽ mô tả request truy cập đi từ PEP đến PDP, lấy thuộc tính qua PIP và nhận quyết định trở lại như thế nào?
Bạn sẽ xác định PEP nên đặt tại API gateway, service, data layer hay nhiều lớp dựa trên ranh giới tin cậy nào?
Bạn sẽ thiết kế PDP tập trung cho nhiều ứng dụng mà không tạo thành điểm nghẽn hoặc điểm lỗi đơn như thế nào?
Bạn sẽ lựa chọn PDP nhúng tại service hoặc PDP từ xa theo yêu cầu độ trễ, tính nhất quán và khả năng quản trị ra sao?
Bạn sẽ giải thích vai trò của PAP trong soạn thảo, phê duyệt, versioning và phát hành policy như thế nào?
Bạn sẽ xác định PIP cần truy vấn nguồn nào để lấy thuộc tính người dùng, tài nguyên, thiết bị và ngữ cảnh ra sao?
Bạn sẽ thiết kế luồng truyền attribute bag giữa PEP và PDP để có đủ ngữ cảnh nhưng không gửi dư dữ liệu nhạy cảm như thế nào?
Bạn sẽ phân biệt quyết định Permit, Deny, NotApplicable và Indeterminate trong mô hình policy như thế nào?
Bạn sẽ thiết kế nguyên tắc deny by default khi PDP không tìm được policy phù hợp hoặc không thể đưa ra quyết định ra sao?
Bạn sẽ phân tích cách xử lý nhiều policy cùng áp dụng nhưng cho kết quả trái ngược bằng thuật toán combining nào?
Bạn sẽ phân biệt deny-overrides, permit-overrides, first-applicable và only-one-applicable về kết quả khi policy xung đột ra sao?
Bạn sẽ lựa chọn policy combining algorithm để bảo đảm quy tắc cấm rõ ràng không bị một policy cho phép khác ghi đè như thế nào?
Bạn sẽ xử lý xung đột giữa policy cấp tổ chức, policy theo tenant và policy do chủ sở hữu tài nguyên định nghĩa ra sao?
Bạn sẽ thiết kế policy composition để tái sử dụng điều kiện chung mà không tạo ra kết quả khó dự đoán khi kế thừa nhiều cấp như thế nào?
Bạn sẽ phân biệt policy, rule, target, condition, obligation và advice trong một ngôn ngữ ABAC như thế nào?
Bạn sẽ biểu diễn điều kiện kết hợp AND, OR, NOT và so sánh tập hợp thuộc tính sao cho policy dễ đọc và kiểm toán ra sao?
Bạn sẽ thiết kế policy cho quy tắc người dùng chỉ được đọc tài liệu cùng tenant có classification không vượt clearance của họ như thế nào?
Bạn sẽ mô hình hóa phân tách nhiệm vụ để người tạo giao dịch không thể tự phê duyệt chính giao dịch đó bằng ABAC ra sao?
Bạn sẽ biểu diễn giới hạn truy cập theo thời gian, địa điểm hoặc thiết bị được quản lý trong policy như thế nào?
Bạn sẽ kiểm soát truy cập theo quan hệ chủ sở hữu, người quản lý hoặc thành viên dự án khi những quan hệ này thay đổi thường xuyên ra sao?
Bạn sẽ xác định cách xử lý thuộc tính bị thiếu, null, sai kiểu hoặc không thể truy xuất trong một policy quan trọng như thế nào?
Bạn sẽ phân biệt giá trị false với thuộc tính không xác định để tránh vô tình cho phép khi dữ liệu ngữ cảnh bị thiếu ra sao?
Bạn sẽ thiết kế policy cho truy cập khẩn cấp break-glass với lý do, thời hạn, phê duyệt và audit bổ sung như thế nào?
Bạn sẽ kết hợp RBAC làm lớp nền với ABAC làm điều kiện bổ sung mà vẫn giữ policy dễ hiểu ra sao?
Bạn sẽ xác định khi nào quan hệ giữa các đối tượng phù hợp hơn thuộc tính phẳng và cách kết hợp ReBAC với ABAC như thế nào?
Bạn sẽ đánh giá rủi ro khi policy phụ thuộc vào thuộc tính do chính client gửi lên mà không được xác minh từ nguồn đáng tin cậy ra sao?
Bạn sẽ phân loại nguồn thuộc tính theo mức tin cậy và xác định nguồn có thẩm quyền cho từng trường dữ liệu như thế nào?
Bạn sẽ ngăn người dùng tự nâng quyền bằng cách sửa department, clearance, tenant hoặc ownership trong request ra sao?
Bạn sẽ bảo vệ đường truyền thuộc tính giữa PIP, PDP và PEP bằng xác thực workload, integrity và kiểm soát quyền truy cập như thế nào?
Bạn sẽ xác định cách ký hoặc xác minh context assertion khi thuộc tính được chuyển qua nhiều service và trust boundary ra sao?
Bạn sẽ xử lý thuộc tính đã hết hạn hoặc thay đổi sau khi được cache để tránh cấp quyền dựa trên trạng thái cũ như thế nào?
Bạn sẽ lựa chọn TTL và invalidation cho cache thuộc tính theo mức độ nhạy cảm và tốc độ thay đổi của từng loại dữ liệu ra sao?
Bạn sẽ phân biệt freshness của thuộc tính với freshness của policy khi đánh giá một quyết định truy cập như thế nào?
Bạn sẽ ngăn confused deputy khi service có quyền rộng thực hiện hành động thay cho caller nhưng PDP không nhận đủ danh tính gốc ra sao?
Bạn sẽ thiết kế propagation danh tính và context xuyên microservice để quyết định ABAC vẫn phản ánh đúng chủ thể khởi tạo như thế nào?
Bạn sẽ xác định thuộc tính nào cần được lấy đồng bộ trong request và thuộc tính nào có thể dùng snapshot hoặc token đã ký ra sao?
Bạn sẽ xử lý PDP hoặc PIP không khả dụng theo nguyên tắc fail-closed và đánh giá ảnh hưởng đến tính sẵn sàng như thế nào?
Bạn sẽ thiết kế chế độ hoạt động khi nguồn thuộc tính tạm lỗi mà vẫn tránh dùng dữ liệu cũ vượt quá mức rủi ro cho phép ra sao?
Bạn sẽ kiểm soát timeout, retry và circuit breaker giữa PEP, PDP và PIP để tránh một request kéo dài hoặc gây quá tải dây chuyền như thế nào?
Bạn sẽ lựa chọn nơi cache quyết định truy cập và những thuộc tính nào phải nằm trong cache key để không dùng nhầm kết quả cho request khác ra sao?
Bạn sẽ xử lý policy update và cache invalidation trên nhiều PDP replica để các node không đưa ra quyết định khác nhau như thế nào?
Bạn sẽ bảo đảm version policy được đồng bộ giữa các vùng triển khai và có thể truy nguyên quyết định theo đúng phiên bản như thế nào?
Bạn sẽ thiết kế rollout policy theo canary hoặc shadow evaluation để phát hiện thay đổi quyền ngoài dự kiến trước khi áp dụng toàn hệ thống ra sao?
Bạn sẽ đánh giá tác động hiệu năng của policy phức tạp, truy vấn thuộc tính từ xa và nhiều vòng đánh giá như thế nào?
Bạn sẽ tối ưu PDP bằng cách tiền tính thuộc tính, gom truy vấn hoặc sắp xếp điều kiện mà không thay đổi ngữ nghĩa policy ra sao?
Bạn sẽ xác định các thuộc tính có cardinality lớn hoặc dữ liệu nhạy cảm không nên đưa vào log quyết định như thế nào?
Bạn sẽ thiết kế obligation để PEP thực hiện thêm hành động như masking trường dữ liệu, ghi audit hoặc giới hạn tải xuống sau khi Permit ra sao?
Bạn sẽ phân biệt obligation bắt buộc với advice tùy chọn và xử lý khi PEP không thể thực hiện obligation như thế nào?
Bạn sẽ kiểm soát quyết định Permit có điều kiện để không bỏ qua yêu cầu bổ sung như watermark, redaction hoặc xác thực tăng cường ra sao?
Bạn sẽ thiết kế policy cho phép xem tài liệu nhưng chỉ cho tải xuống khi thiết bị được quản lý và mạng ở vùng tin cậy như thế nào?
Bạn sẽ áp dụng ABAC cho API multi-tenant để quyền truy cập phụ thuộc vào tenant, classification, ownership và mục đích sử dụng ra sao?
Bạn sẽ xác định cách bảo vệ dữ liệu cá nhân khi policy engine cần thuộc tính nhạy cảm để ra quyết định nhưng không cần lưu giá trị thô như thế nào?
Bạn sẽ thiết kế audit decision log gồm subject, resource, action, policy version, outcome và lý do mà không làm lộ dữ liệu không cần thiết ra sao?
Bạn sẽ bảo đảm audit log không thể bị sửa bởi PEP, PDP hoặc người dùng có quyền quản trị policy như thế nào?
Bạn sẽ giải thích cách cung cấp decision explanation để người vận hành biết rule nào dẫn đến Permit hoặc Deny mà không tiết lộ chi tiết policy nhạy cảm ra sao?
Bạn sẽ theo dõi tỷ lệ Permit, Deny, Indeterminate, độ trễ PDP và lỗi truy xuất thuộc tính để phát hiện sự cố như thế nào?
Bạn sẽ xây dựng cảnh báo khi một thay đổi policy làm tỷ lệ Deny hoặc Permit tăng bất thường trên một nhóm tài nguyên ra sao?
Bạn sẽ kiểm tra và phát hiện policy drift giữa các môi trường development, staging và production bằng cách nào?
Bạn sẽ quản lý policy version, phê duyệt thay đổi và rollback để tránh sửa trực tiếp policy đang chạy mà không có kiểm soát như thế nào?
Bạn sẽ xây dựng bộ kiểm thử policy với ma trận subject-resource-action-environment bao phủ cả trường hợp cho phép và từ chối như thế nào?
Bạn sẽ dùng test vector hoặc decision table để kiểm tra policy combining và các trường hợp nhiều rule cùng khớp ra sao?
Bạn sẽ kiểm thử thuộc tính thiếu, sai kiểu, stale, bị giả mạo hoặc không thể truy xuất để xác minh hành vi deny-safe như thế nào?
Bạn sẽ thiết kế property-based testing để tìm tổ hợp thuộc tính làm policy đưa ra Permit ngoài dự kiến ra sao?
Bạn sẽ thực hiện differential testing giữa policy version mới và cũ để phát hiện thay đổi quyết định truy cập không mong muốn như thế nào?
Bạn sẽ kiểm thử tích hợp PEP-PDP-PIP trong môi trường phân tán gồm timeout, network partition, cache và policy rollout ra sao?
Bạn sẽ xác minh policy không thể bị bypass bằng cách gọi trực tiếp backend bỏ qua PEP tại gateway như thế nào?
Bạn sẽ đánh giá hiệu quả ABAC bằng coverage của endpoint, tài nguyên, hành động và các tổ hợp thuộc tính quan trọng như thế nào?
Nếu người dùng tự sửa thuộc tính clearance trong request để đọc tài liệu mật, bạn sẽ xác định và sửa trust boundary của thuộc tính ở đâu?
Nếu hai policy một policy cho phép và một policy từ chối cùng khớp, bạn sẽ xác định kết quả theo combining algorithm và kiểm chứng bằng test nào?
Nếu PDP replica vẫn Permit sau khi tài khoản bị khóa do cache thuộc tính cũ, bạn sẽ thiết kế invalidation và giới hạn freshness ra sao?
Nếu PIP không truy xuất được thuộc tính thiết bị trong lúc request nhạy cảm, bạn sẽ chọn kết quả an toàn và xử lý khả năng sẵn sàng như thế nào?
Nếu service backend được gọi trực tiếp mà không qua gateway PEP, bạn sẽ bố trí enforcement và xác thực caller ra sao?
Nếu policy mới làm tăng đột biến số quyết định Deny sau rollout, bạn sẽ dùng shadow evaluation, audit và rollback để tìm nguyên nhân như thế nào?
Bạn sẽ thiết kế kiến trúc ABAC đầu cuối cho nền tảng phân tán gồm mô hình thuộc tính, PDP/PEP/PIP/PAP, policy lifecycle, nguồn dữ liệu tin cậy, kiểm thử và audit như thế nào?
