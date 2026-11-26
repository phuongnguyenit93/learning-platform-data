Một tổ chức có hàng trăm API key và mật khẩu dịch vụ nhưng inventory không ghi owner, hệ thống phụ thuộc hoặc ngày hết hạn; khi phát hiện một secret lộ, nhóm vận hành không xác định được phạm vi thu hồi.
Nhiều nhóm dùng chung một tài khoản quản trị cơ sở dữ liệu cho ứng dụng và tác vụ vận hành; log chỉ ghi một danh tính nên không thể quy trách nhiệm khi credential bị lạm dụng.
Một developer xóa API key khỏi commit mới nhất sau khi scanner cảnh báo nhưng secret vẫn tồn tại trong lịch sử Git và các bản clone đã tải về.
Một repository công khai được mirror sang nhiều nền tảng; secret bị commit trong nhánh thử nghiệm và tiếp tục xuất hiện trong fork dù nhánh chính đã được sửa.
Pipeline CI in toàn bộ biến môi trường khi job thất bại; mật khẩu dịch vụ xuất hiện trong log build mà nhiều thành viên dự án có thể đọc.
Workflow dùng trigger pull_request_target có quyền đọc repository secrets rồi checkout và chạy mã từ fork không tin cậy; mã đóng góp có thể gửi credential ra ngoài.
Secret được truyền qua build argument và lưu trong layer của container image; xóa file ở layer cuối không loại bỏ dữ liệu khỏi các layer trước.
Ứng dụng đọc secret từ environment variable; giá trị có thể xuất hiện trong process inspection, crash dump hoặc thông tin chẩn đoán của môi trường chạy.
Một script triển khai truyền mật khẩu qua command-line argument; công cụ giám sát tiến trình ghi lại toàn bộ command line trong log hệ thống.
Crash dump của dịch vụ chứa token truy cập và credential đã giải mã trong bộ nhớ; dump được tự động tải lên kho phân tích mà chưa có bộ lọc dữ liệu.
Agent quan sát thu thập request header và span attributes; access token trong header Authorization bị gửi vào hệ thống trace.
Frontend build nhúng API key dài hạn vào JavaScript bundle; người dùng có thể tải bundle và trích xuất secret từ trình duyệt.
Ứng dụng mobile lưu credential dùng chung trong gói cài đặt; việc obfuscate mã không ngăn được người dùng có thiết bị kiểm soát trích xuất giá trị.
Tệp .env chứa credential production được thêm nhầm vào gói phát hành; quy trình đóng gói không có allowlist file và không kiểm tra secret.
Một nhóm lưu password trong ConfigMap vì nghĩ dữ liệu cấu hình nội bộ không nhạy cảm; nhiều workload có quyền đọc toàn bộ ConfigMap của namespace.
Kubernetes Secret được xem là an toàn chỉ vì giá trị được Base64 encode; quyền đọc API và encryption at rest của cluster chưa được giới hạn.
Secret được mount vào volume dùng chung giữa nhiều container trong pod; container phụ không cần credential vẫn có thể đọc file do quyền filesystem quá rộng.
Workload lấy secret từ secret manager bằng một machine identity dùng chung cho toàn cluster; một pod bị xâm nhập có thể truy cập secret của workload khác.
Một pipeline CI có quyền đọc mọi secret của production dù job chỉ cần credential triển khai một dịch vụ; phạm vi quyền không được giới hạn theo environment và project.
Nhóm vận hành dùng access key dài hạn để workload gọi cloud API; nền tảng đã hỗ trợ workload identity nhưng credential tĩnh vẫn được lưu trong cấu hình.
Trust policy cho workload federation chỉ kiểm tra issuer mà không ràng buộc subject, audience hoặc repository; workload ngoài dự kiến có thể đổi danh tính lấy quyền đọc secret.
Secret manager phân quyền theo project lớn thay vì từng secret; một service account chỉ cần đọc một credential nhưng có thể liệt kê và lấy toàn bộ secret trong project.
Secret manager tạm ngừng hoạt động trong một vùng; ứng dụng không có chiến lược cache có giới hạn hoặc xử lý lỗi nên toàn bộ request cần credential đều thất bại.
Ứng dụng cần một secret để xác thực lần đầu với secret manager nhưng bootstrap credential được lưu trong image; kẻ lấy image có thể tiếp tục truy cập kho secret.
Secret được copy từ vault vào file cấu hình lâu dài trên máy chủ; việc thu hồi trong vault không xóa các bản sao đã phân phối trước đó.
Một hệ thống hỗ trợ dynamic credentials có lease nhưng ứng dụng không theo dõi thời hạn; request tiếp tục dùng credential sau khi lease hết hiệu lực.
Database cấp username và password tạm thời cho từng workload nhưng connection pool giữ kết nối cũ sau khi credential bị thu hồi; quyền truy cập vẫn tồn tại qua phiên đã mở.
Secret rotation tạo password mới nhưng hệ thống không có giai đoạn overlap; một số instance chưa tải cấu hình mới khiến request thất bại trong lúc triển khai.
Credential được xoay vòng ở secret manager nhưng job triển khai chỉ cập nhật một phần replica; các instance dùng secret cũ và mới đồng thời gây lỗi xác thực ngẫu nhiên.
Nhóm vận hành thay password database trước khi cập nhật các consumer và scheduled job; các tác vụ chạy theo lịch thất bại nhiều giờ sau đợt rotation.
Một secret được xoay vòng theo lịch cố định nhưng không có cơ chế phát hiện việc sử dụng bất thường; credential đã bị lộ vẫn hoạt động cho đến kỳ thay tiếp theo.
Không có dependency map cho API key webhook và credential dịch vụ; khi rotation, nhóm không biết đối tác, batch job và hệ thống dự phòng nào cần cập nhật.
Rotation diễn ra khi giao dịch dài đang chạy; hệ thống đóng credential cũ quá sớm và làm gián đoạn các thao tác cần hoàn tất trước khi chuyển phiên.
Secret bị thu hồi trong vault nhưng cache tại gateway và sidecar chưa hết hạn; request tiếp tục được xác thực bằng bản sao credential cũ.
OAuth client secret bị lộ và đã được thay thế nhưng access token hoặc refresh token đã phát hành vẫn còn hiệu lực do chưa có quy trình thu hồi liên đới.
Scanner chỉ tìm một số định dạng API key phổ biến; secret tùy biến trong file YAML và script triển khai không bị phát hiện trước khi merge.
Secret scanner chặn mọi chuỗi có entropy cao; nhiều giá trị không nhạy cảm tạo false positive khiến nhóm phát triển dần bỏ qua cảnh báo.
Một exception handler đưa toàn bộ request headers vào log khi xác thực thất bại; secret bị ghi lại ngay cả khi request bị từ chối.
Audit log chỉ ghi thao tác tạo và xóa secret mà không ghi danh tính, mục đích, nguồn truy cập hoặc kết quả đọc; điều tra việc truy xuất trái phép không đủ bằng chứng.
Quy trình break-glass cho phép quản trị viên đọc mọi secret khi có sự cố nhưng không yêu cầu lý do, thời hạn hoặc hậu kiểm độc lập.
Một người vừa tạo secret vừa tự phê duyệt quyền truy cập và thay đổi policy; không có phân tách nhiệm vụ cho các thao tác nhạy cảm.
Nhân viên chuyển nhóm nhưng quyền truy cập secret của dự án cũ vẫn còn; quy trình mover không rà soát và thu hồi quyền theo vai trò mới.
Service account của một tác vụ ngừng hoạt động nhưng secret không có owner hiện tại và không được đưa vào quy trình rà soát tài khoản tồn dư.
Secret manager có backup nhưng khóa bảo vệ backup nằm cùng môi trường và cùng nhóm quyền; kẻ chiếm quyền quản trị có thể lấy cả backup lẫn phương tiện giải mã.
Doanh nghiệp cần phục hồi secret sau thảm họa nhưng bản backup không có kiểm thử restore và không ghi rõ phiên bản secret tương ứng với từng hệ thống.
Một secret được đánh dấu deleted trong giao diện nhưng vẫn còn trong soft-delete window và bản backup; nhóm vận hành nhầm trạng thái hiển thị với việc tiêu hủy hoàn tất.
Credential bị xóa khỏi vault nhưng vẫn còn trong snapshot máy ảo, artifact build và bản sao cấu hình ở vùng DR; tổ chức chưa có quy trình xử lý các bản sao này.
Đối tác bên thứ ba yêu cầu một API key có quyền quản trị để tích hợp; tổ chức không giới hạn scope, quota, thời hạn hoặc kênh trao đổi credential.
Webhook signing secret được chia sẻ giữa nhiều đối tác; khi một bên bị lộ secret, tổ chức buộc phải thay khóa đồng loạt và không thể xác định nguồn chữ ký.
Một chứng thư client hết hạn nhưng private key vẫn được dùng ở nhiều workload; nhóm vận hành thay chứng thư mà không kiểm kê nơi lưu và nơi phân phối private key.
Secret được gửi qua ticket hỗ trợ và email nhóm để xử lý nhanh; bản sao vẫn tồn tại trong mailbox, notification và hệ thống lưu trữ đính kèm.
Ứng dụng lưu refresh token trong local storage của trình duyệt; một lỗ hổng script injection có thể đọc credential và dùng lại ngoài phiên ban đầu.
Một nhóm dùng cùng secret production cho môi trường test để giảm công sức cấu hình; bản sao dữ liệu và quyền truy cập yếu ở môi trường test làm tăng phạm vi lộ.
Developer lưu credential cá nhân trong file cấu hình cục bộ được đồng bộ qua dịch vụ backup máy trạm; secret đi tới thiết bị và tài khoản cá nhân ngoài kiểm soát.
Khi secret bị lộ, nhóm chỉ đổi giá trị trong vault mà không rà soát log truy cập, hành động đã thực hiện hoặc credential liên quan có thể bị lộ cùng lúc.
Một secret có owner là nhà thầu đã kết thúc hợp đồng; không có trigger offboarding để vô hiệu hóa credential và thu hồi quyền trên secret manager.
Chính sách secret đặt thời hạn tối đa giống nhau cho mọi loại credential; nhóm vận hành phải xoay những secret ít rủi ro quá thường xuyên nhưng bỏ sót secret có quyền cao.
Một hệ thống dùng secret cũ để rollback phiên bản ứng dụng; sau khi secret đã bị thu hồi vì nghi lộ, quy trình rollback vô tình kích hoạt lại credential không còn tin cậy.
