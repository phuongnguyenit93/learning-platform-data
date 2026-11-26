Một nhân viên được tạo hồ sơ trong HR nhưng identity proofing chưa hoàn tất; quy trình tự động cấp tài khoản email và quyền truy cập dữ liệu nội bộ ngay khi bản ghi nhân sự xuất hiện.
Hai hồ sơ nhân sự có cùng họ tên và ngày sinh được đồng bộ thành một identity vì hệ thống dùng thuộc tính dễ trùng để matching; quyền của hai người bị gộp vào cùng tài khoản.
Nhân viên mới được provision tài khoản và nhóm quyền production nhiều ngày trước ngày bắt đầu làm việc; tài khoản có thể đăng nhập trước khi hợp đồng và trách nhiệm có hiệu lực.
Hồ sơ Joiner lấy manager và department từ dữ liệu HR cũ; người mới nhận quyền theo đơn vị không còn tồn tại và có thể xem dữ liệu ngoài phạm vi công việc.
Quản lý tạo tài khoản trực tiếp trong một ứng dụng SaaS để nhân viên làm việc ngay, bỏ qua IdP và quy trình IAM; identity không xuất hiện trong inventory và không được đưa vào access review.
Birthright access tự động cấp mọi nhân viên quyền đọc toàn bộ shared drive; quyền mặc định rộng hơn nhu cầu của nhiều nhóm và không có bước phê duyệt theo vai trò.
Role được ánh xạ từ job title dạng văn bản tự do; các biến thể như Senior Analyst và Analyst II bị gom vào role quản trị do quy tắc so khớp chuỗi quá rộng.
Nhân viên chuyển từ phòng tài chính sang vận hành nhưng workflow chỉ thêm role mới; quyền đọc dữ liệu lương và tài khoản thanh toán cũ vẫn còn hiệu lực.
Mover event đổi department đã cập nhật IdP nhưng không đồng bộ tới các ứng dụng dùng local account; người dùng giữ quyền cũ ở những hệ thống không hỗ trợ SSO.
Nhân viên được thăng chức và nhận quyền phê duyệt cao hơn nhưng quyền requester cũ vẫn được giữ; người đó có thể vừa tạo vừa phê duyệt cùng một giao dịch.
Quản lý đổi nhóm phụ trách nhưng quan hệ manager-subordinate trong directory không cập nhật; quyền xem hồ sơ cấp dưới của quản lý cũ tiếp tục tồn tại.
Nhân viên nghỉ việc có effective date hôm nay nhưng batch leaver chỉ chạy cuối tuần; tài khoản vẫn đăng nhập được trong khoảng thời gian sau khi quan hệ lao động kết thúc.
HR gửi sự kiện termination nhưng connector bị lỗi và không có dead-letter alert; leaver không được disable ở IdP dù hệ thống nguồn đã ghi nhận nghỉ việc.
IdP disable tài khoản nhân viên nhưng ứng dụng cũ có tài khoản local và mật khẩu riêng; người dùng vẫn đăng nhập trực tiếp mà không đi qua SSO.
Refresh token và session cookie của nhân viên bị chấm dứt hợp đồng vẫn còn hiệu lực; disable identity không thu hồi các phiên đã phát hành ở những dịch vụ downstream.
SCIM client gửi PATCH active=false nhưng ứng dụng đích chỉ cập nhật displayName và bỏ qua trạng thái active; tài khoản leaver tiếp tục hoạt động.
Ứng dụng hiểu SCIM DELETE là xóa vật lý nhưng hệ thống IAM kỳ vọng deprovision giữ audit record; thao tác xóa làm mất lịch sử và quan hệ cần cho điều tra.
SCIM connector gửi group membership mới nhưng không xóa membership cũ khi user chuyển phòng ban; entitlement cũ tồn tại dù group nguồn đã thay đổi.
SCIM event cập nhật profile đến sau event termination do hàng đợi xử lý không bảo toàn thứ tự; bản cập nhật cũ vô tình kích hoạt lại tài khoản đã bị disable.
Incremental SCIM sync dùng watermark sai và bỏ qua các thay đổi trong khoảng mất kết nối; một số account và group membership không được cập nhật tới ứng dụng.
SCIM provisioning retry sau timeout tạo hai account vì ứng dụng đích không hỗ trợ idempotency theo externalId; người dùng có hai danh tính với quyền khác nhau.
SCIM connector dùng một bearer token có quyền quản trị toàn bộ directory cho mọi ứng dụng; lộ credential của một connector có thể cho phép sửa danh tính trên nhiều hệ thống.
Ứng dụng nhận SCIM userName từ IdP nhưng dùng email làm khóa liên kết; khi email đổi, hệ thống tạo user mới thay vì cập nhật identity hiện có.
JIT provisioning qua SSO tạo account khi user đăng nhập lần đầu nhưng không kiểm tra employment status từ nguồn đáng tin; tài khoản đã nghỉ việc vẫn được tạo lại.
SSO assertion chứa group attribute do IdP gửi nhưng ứng dụng tin mọi giá trị mà không kiểm tra mapping allowlist; người dùng có thể nhận role đặc quyền qua claim sai cấu hình.
NameID trong liên kết SAML thay đổi sau khi người dùng đổi email; service provider tạo account mới và để lại account cũ cùng dữ liệu và quyền tồn dư.
OIDC subject được ghép với tài khoản dựa trên email thay vì cặp issuer-subject ổn định; hai identity provider có thể cấp cùng email và bị liên kết nhầm.
Người dùng được mời làm guest nhưng không có sponsor, mục đích và ngày hết hạn; tài khoản bên ngoài tồn tại lâu sau khi dự án kết thúc.
Nhà thầu kết thúc hợp đồng nhưng sponsor không nhận được nhắc nhở access review; guest identity và quyền chia sẻ tài liệu vẫn hoạt động nhiều tháng.
Nhân viên nghỉ việc rồi được tuyển lại với cùng email; quy trình khôi phục account cũ tự động khôi phục cả group và entitlement từ công việc trước.
Identity matching khi rehire dựa trên email đã tái sử dụng; hồ sơ người mới bị gắn vào account của nhân viên cũ và có nguy cơ truy cập dữ liệu lịch sử.
Tài khoản quản trị được dùng chung với tài khoản làm việc hàng ngày; phishing một session thông thường có thể đồng thời chiếm quyền đặc quyền.
Quyền admin được cấp cố định cho nhóm vận hành thay vì cấp theo thời gian qua privileged access management; quyền không tự hết sau khi hoàn tất nhiệm vụ.
Yêu cầu nâng quyền tạm thời được phê duyệt nhưng không có expiration timestamp; role đặc quyền vẫn còn sau cửa sổ bảo trì.
Quy trình access certification gửi danh sách hàng nghìn quyền cho manager và mặc định giữ quyền nếu không phản hồi; reviewer approve hàng loạt mà không xem xét từng entitlement.
Người rà soát quyền không nhìn thấy last-used, resource sensitivity hoặc lý do cấp quyền; quyết định giữ hoặc thu hồi thiếu ngữ cảnh và thường dựa trên phỏng đoán.
Entitlement trong ứng dụng không có business owner; khi chiến dịch access review diễn ra, không ai chịu trách nhiệm xác nhận quyền còn cần thiết.
RBAC role được cập nhật nhưng quyền kế thừa qua nested group không được tính trong báo cáo; người dùng có quyền gián tiếp mà reviewer không nhìn thấy.
ABAC policy dựa vào department và employmentType từ IdP nhưng thuộc tính không đồng bộ sau khi mover; quyết định cấp quyền vẫn dựa trên thông tin cũ.
Separation of duties chỉ kiểm tra role trực tiếp; một user nhận quyền approver qua nested group và quyền requester qua role riêng, tạo xung đột không được phát hiện.
Quyền truy cập ứng dụng được cấp thủ công ngoài IAM rồi không được đưa vào entitlement catalog; access review không thể nhìn thấy hoặc thu hồi quyền đó.
Nhân viên được chuyển sang vai trò ít nhạy cảm hơn nhưng quyền truy cập vào secret vault và production console không bị rà soát; mover chỉ cập nhật nhóm nghiệp vụ.
Leaver workflow disable tài khoản ở IdP nhưng không thực hiện credential revocation đối với SSH key, cloud access key và certificate cá nhân; credential phi tương tác vẫn cho phép truy cập.
Service account được tạo cho batch job nhưng không có owner cá nhân hoặc nhóm chịu trách nhiệm; khi job không còn dùng, không ai nhận diện để thu hồi.
Service account dùng mật khẩu tĩnh được chia sẻ giữa nhiều ứng dụng; rotation làm gián đoạn nhiều hệ thống và nhóm trì hoãn thay khóa vì không biết dependency.
Access key của service account được lưu trong CI variable không có expiry; nhân viên rời công ty nhưng key vẫn cho phép pipeline truy cập cloud.
Workload identity federation được cấu hình trust toàn bộ repository hoặc namespace; workload không liên quan có thể lấy token và mạo danh service principal.
Service principal được tạo tự động cho tích hợp SaaS nhưng ứng dụng bị ngừng sử dụng; identity vẫn có quyền OAuth consent và refresh token đang hoạt động.
Certificate của non-human identity sắp hết hạn nhưng không có inventory hoặc cảnh báo owner; workload bị gián đoạn khi certificate hết hạn bất ngờ.
Tài khoản dịch vụ cho phép đăng nhập tương tác như người dùng; credential bị lộ có thể được dùng qua giao diện đăng nhập thay vì chỉ trong workload dự kiến.
Nhân viên sở hữu service account rời tổ chức nhưng tài khoản không được chuyển owner; secret, quyền và trách nhiệm vận hành bị bỏ ngỏ.
API key của đối tác không gắn với một client identity duy nhất; khi hợp đồng chấm dứt, tổ chức không biết key nào thuộc đối tác để thu hồi chính xác.
Quy trình chuyển giao vendor thay đổi nhân sự nhưng chỉ cập nhật danh sách liên hệ; account của nhân viên vendor cũ vẫn là thành viên group và có quyền tải dữ liệu.
Identity lifecycle không có quy trình xử lý tài khoản dormant; các account không hoạt động nhiều tháng vẫn giữ quyền VPN và truy cập dữ liệu nhạy cảm.
Tài khoản dùng chung cho quầy hỗ trợ không có checkout hoặc attribution theo cá nhân; hành động của nhân viên không thể quy về người thực hiện.
Khôi phục tài khoản sau khi mất yếu tố MFA chỉ dựa vào email phụ chưa xác minh; attacker chiếm email phụ có thể yêu cầu reset danh tính và lấy lại quyền.
Thay đổi số điện thoại hoặc email recovery không yêu cầu xác minh bổ sung hay thời gian chờ; attacker đang giữ session có thể thay kênh khôi phục trước khi chủ tài khoản phát hiện.
Quy trình tạo identity không kiểm tra người yêu cầu đã được xác minh danh tính và có hợp đồng hợp lệ; account được cấp dựa trên ticket giả mạo.
Directory có hai bản ghi cho cùng một người do khác employee ID; downstream app tạo hai account và một trong hai không bị disable khi người đó nghỉ việc.
Reconciliation định kỳ chỉ so sánh số lượng account giữa IdP và ứng dụng; không đối chiếu trạng thái, owner, group, role và credential nên quyền tồn dư không bị phát hiện.
Audit log ghi account được tạo nhưng không lưu nguồn HR event, approver, policy version và correlation ID; điều tra không thể xác định ai đã yêu cầu hoặc vì sao quyền được cấp.
Thay đổi group membership được thực hiện trực tiếp trong directory bởi admin nhưng không tạo ticket hoặc audit event có lý do; quyền có thể được nâng ngoài workflow.
Leaver process xóa identity record ngay lập tức cùng với manager, owner và lịch sử phê duyệt; tổ chức mất bằng chứng cần cho audit và điều tra sau nghỉ việc.
Chính sách retention xóa hồ sơ identity quá sớm nhưng giữ bản sao dữ liệu cá nhân trong log provisioning và hệ thống báo cáo; dữ liệu không được quản lý nhất quán sau khi offboard.
Metrics IAM chỉ đo thời gian tạo account Joiner mà không đo thời gian revoke Leaver, số orphaned account và tỷ lệ entitlement được review; hiệu quả vòng đời bị đánh giá thiếu.
