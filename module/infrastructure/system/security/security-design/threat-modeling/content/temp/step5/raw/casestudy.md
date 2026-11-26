Nhóm thiết kế lập danh sách chức năng nhưng không kiểm kê dữ liệu, khóa ký và dịch vụ phụ thuộc; một kho backup chứa bản sao dữ liệu khách hàng bị bỏ sót khỏi phạm vi threat model.
Một nền tảng thanh toán có người dùng, nhân viên hỗ trợ, đối tác ngân hàng và workload tự động; nhóm phân tích gộp tất cả thành một tác nhân “user” nên bỏ qua khác biệt về năng lực và quyền của từng bên.
Sơ đồ kiến trúc chỉ mô tả các microservice mà không thể hiện luồng dữ liệu, giao thức, hướng kết nối hoặc nơi dữ liệu được lưu; nhóm đánh giá không xác định được điểm dữ liệu nhạy cảm đi qua.
Một luồng upload đi từ trình duyệt qua CDN, API gateway, dịch vụ quét tệp và object storage; sơ đồ DFD bỏ qua CDN và worker bất đồng bộ nên ranh giới tin cậy và nơi kiểm tra nội dung bị xác định sai.
Hệ thống dùng chung một tài khoản dịch vụ để đọc dữ liệu từ nhiều tenant; DFD không thể hiện principal và tenant context nên luồng truy cập chéo tenant không được đưa vào phân tích.
Một dịch vụ webhook nhận callback từ đối tác bên ngoài nhưng sơ đồ coi đối tác là thành phần nội bộ; trust boundary Internet-to-service không được đánh dấu.
Nhóm threat modeling chỉ xét dữ liệu khi truyền qua mạng mà không xét dữ liệu lưu trong cache, log, message queue và backup; nhiều đường rò rỉ thông tin không xuất hiện trong mô hình.
Ứng dụng nhận token từ identity provider nhưng DFD không mô tả issuer, audience, chữ ký hoặc điểm xác minh; nhóm không đánh giá được khả năng giả mạo danh tính.
Một API cho phép cập nhật địa chỉ thanh toán; threat model không phân biệt người dùng cuối, nhân viên hỗ trợ và hệ thống batch có quyền gọi endpoint, dẫn đến thiếu tình huống spoofing và elevation of privilege.
Thiết bị IoT gửi telemetry qua gateway dùng chung; nhóm thiết kế không xác định khả năng kẻ tấn công chiếm một thiết bị hợp lệ và giả mạo danh tính thiết bị khác.
Một attacker có được session cookie của nhân viên hỗ trợ và dùng nó để giả danh nhân viên truy cập hồ sơ khách hàng; mô hình chưa liệt kê spoofing qua session theft.
Đối tác gửi thông điệp ký số nhưng hệ thống chỉ kiểm tra chữ ký mà không ràng buộc nonce, timestamp hoặc message ID; một thông điệp cũ có thể được phát lại như giao dịch mới.
Người dùng có quyền gửi yêu cầu hoàn tiền nhưng có thể sửa tham số `accountId` để thao tác trên tài khoản khác; threat model chưa ghi nhận tampering và thiếu kiểm tra quyền theo object.
Một pipeline CI tải artifact từ registry rồi triển khai production; mô hình không xét khả năng artifact bị thay thế giữa bước build và deploy.
Nhân viên vận hành có thể sửa trực tiếp bản ghi audit trong cùng database nghiệp vụ; nguy cơ tampering và repudiation không được đưa vào phân tích.
Một dịch vụ phê duyệt giao dịch không lưu danh tính người phê duyệt, thời điểm và phiên bản dữ liệu được duyệt; khi có tranh chấp, tổ chức không thể xác định ai đã thực hiện hành động.
API trả thông báo lỗi chứa stack trace, query và thông tin nội bộ; threat model chưa xem thông tin chẩn đoán là tài sản cần bảo vệ khỏi information disclosure.
Log tập trung ghi access token, email và dữ liệu giao dịch; nhóm phân tích chỉ xem log là telemetry vận hành mà không mô hình hóa rủi ro lộ dữ liệu.
Ứng dụng cho phép truy vấn báo cáo không giới hạn khoảng thời gian; attacker có thể tạo request tốn CPU và database để làm gián đoạn dịch vụ nhưng DoS chưa có trong attack scenarios.
Một hàng đợi message có thể bị làm đầy bằng sự kiện không hợp lệ; mô hình chỉ xem xét khả năng xâm nhập dữ liệu mà bỏ qua exhaustion của queue và worker.
Người dùng thường có quyền xem báo cáo nhưng một lỗi cấu hình cho phép sửa role của chính mình; threat model chưa xét elevation of privilege qua luồng quản trị quyền.
Một tiến trình xử lý tệp chạy với quyền filesystem rộng hơn nhu cầu; file độc hại có thể ghi ra thư mục cấu hình và thay đổi hành vi dịch vụ, nhưng ranh giới đặc quyền không xuất hiện trong DFD.
Ứng dụng thu thập vị trí thiết bị theo thời gian thực nhưng threat model chỉ phân tích STRIDE; việc suy luận thói quen di chuyển từ dữ liệu vị trí không được xem xét theo LINDDUN.
Analytics dùng một mã định danh ổn định trên nhiều website và đối tác; các sự kiện riêng lẻ có thể liên kết thành hồ sơ hành vi nhưng nguy cơ linkability bị bỏ qua.
Một báo cáo hiển thị dữ liệu đã pseudonymize nhưng tập thuộc tính hiếm vẫn đủ nhận diện một cá nhân; mô hình quyền riêng tư chỉ đánh giá việc loại bỏ tên và email.
API tra cứu thành viên trả về thông báo khác nhau giữa tài khoản tồn tại và không tồn tại; kẻ ngoài có thể dò danh sách người dùng qua khả năng detectability.
Người dùng không được thông báo rằng dữ liệu telemetry được chia sẻ với nhà cung cấp phân tích; threat model chưa xem xét unawareness và tính minh bạch của mục đích xử lý.
Dữ liệu sức khỏe được lưu lâu hơn mục đích đã công bố và không có quy trình xóa theo yêu cầu; nguy cơ non-compliance trong LINDDUN không xuất hiện trong review kiến trúc.
Một attack tree cho mục tiêu chiếm tài khoản chỉ có nhánh đoán mật khẩu; nhóm bỏ qua phishing, token theft, recovery abuse và chiếm quyền email làm các đường tấn công bị đánh giá thiếu.
Nhóm viết abuse case cho chức năng chuyển tiền nhưng chỉ mô tả hành vi người dùng hợp lệ; chưa mô tả kẻ tấn công lợi dụng race condition, replay hoặc thay đổi người thụ hưởng.
Threat model liệt kê “SQL injection” như một nhãn rủi ro nhưng không chỉ ra entry point, dữ liệu chịu ảnh hưởng, trust boundary hoặc điều kiện khai thác; đội triển khai không biết kiểm soát cần đặt ở đâu.
Một lỗ hổng có xác suất thấp nhưng có thể làm lộ khóa gốc và toàn bộ dữ liệu nhiều năm; nhóm xếp hạng chỉ dựa trên likelihood nên ưu tiên thấp sai lệch.
Nhóm chấm điểm rủi ro bằng ma trận likelihood-impact nhưng mỗi nhóm dùng thang đo và giả định khác nhau; kết quả ưu tiên giữa các dịch vụ không thể so sánh.
Một threat có tác động nghiêm trọng nhưng chỉ xảy ra khi nhiều điều kiện cùng đúng; đánh giá không ghi rõ giả định, precondition và năng lực attacker nên điểm rủi ro thiếu cơ sở.
Biện pháp giảm thiểu yêu cầu MFA được ghi là đã hoàn tất khi ticket cấu hình đóng; nhóm không kiểm chứng enforcement trên mọi đường đăng nhập và recovery.
Thiết kế bổ sung WAF để xử lý rủi ro injection nhưng không sửa truy vấn động trong backend; threat model đóng rủi ro theo sự hiện diện của công cụ thay vì hiệu quả kiểm soát.
Một threat được đánh dấu “accepted” mà không có owner, thời hạn xem xét hoặc phê duyệt của người chịu trách nhiệm nghiệp vụ; residual risk không được quản trị.
Threat model được tạo trước khi thiết kế nhưng không cập nhật sau khi thêm webhook, luồng export và nhà cung cấp mới; các luồng dữ liệu mới không được đánh giá.
Một nhóm đánh giá kiến trúc chỉ bằng sơ đồ tổng quan; không có data classification, trust boundary hay danh sách external dependency nên review không phát hiện đường tấn công qua bên thứ ba.
Ứng dụng đa vùng dùng chung control plane; threat model không phân tích ảnh hưởng khi một region bị chiếm quyền và attacker di chuyển sang region khác.
Đối tác cung cấp thư viện xử lý tài liệu có quyền đọc file tải lên; mô hình coi thư viện là mã nội bộ và không đánh giá rủi ro supply chain hoặc xử lý dữ liệu bởi bên thứ ba.
Một dịch vụ lưu dữ liệu mã hóa nhưng khóa giải mã được cấp cho cùng principal có quyền đọc mọi bản backup; threat model không xem xét việc compromise một identity làm vô hiệu nhiều lớp kiểm soát.
Hệ thống ghi nhận hành động quản trị nhưng đồng hồ giữa API, identity provider và database lệch nhau; mô hình không đưa yêu cầu đồng bộ thời gian vào khả năng điều tra repudiation.
Nhóm sử dụng STRIDE cho mọi hệ thống nhưng không phân tích quyền riêng tư của dữ liệu định danh, khả năng liên kết sự kiện và mức độ người dùng được thông báo; LINDDUN không được áp dụng cho sản phẩm có dữ liệu cá nhân.
Attack tree của dịch vụ đăng nhập không phân biệt mục tiêu chiếm tài khoản cá nhân với chiếm quyền quản trị tenant; các đường tấn công và tác động khác nhau bị gộp thành một.
Một biện pháp giảm thiểu rate limit được triển khai ở API gateway nhưng không áp dụng cho endpoint nội bộ và đường gọi batch; kiểm chứng chỉ chạy qua đường công khai.
Nhóm kiểm thử threat model chỉ chạy happy path và xác nhận tính năng hoạt động; các tình huống abuse, replay, privilege escalation và boundary crossing không được kiểm chứng.
Một threat có thể được giảm bằng nhiều biện pháp nhưng nhóm không đánh giá phụ thuộc chung giữa chúng; hai lớp kiểm soát cùng dùng một identity provider nên một lỗi nền tảng có thể vô hiệu cả hai.
Kiến trúc sử dụng nhiều trust boundary giữa browser, edge, service mesh, backend và data store; nhóm không gắn threat với từng điểm chuyển tiếp nên kiểm soát được đặt sai tầng.
Threat register có hàng trăm mục nhưng không liên kết từng threat với asset, owner, mitigation, trạng thái kiểm chứng và residual risk; nhóm kiến trúc không biết rủi ro nào còn mở trước khi phát hành.
Sau một sự cố xâm nhập, nhóm cập nhật IOC và vá hệ thống nhưng không cập nhật attacker capability, abuse case và giả định trong threat model; cùng một đường tấn công có thể tái xuất hiện ở thiết kế tiếp theo.
