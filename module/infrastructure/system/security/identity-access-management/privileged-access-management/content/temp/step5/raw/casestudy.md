Một doanh nghiệp hợp nhất hai hệ thống Active Directory sau sáp nhập; danh sách tài khoản quản trị hiện nằm rải rác ở domain cũ, cloud, máy chủ Linux và thiết bị mạng, trong đó không rõ tài khoản nào còn được sử dụng.
Một cuộc kiểm toán phát hiện hàng chục tài khoản Domain Admin được cấp từ nhiều năm trước cho nhóm vận hành; nhân sự đã đổi vị trí nhưng quyền cũ vẫn còn và không có chủ sở hữu phê duyệt.
Một nhóm kỹ sư nền tảng dùng tài khoản cloud có quyền Owner thường trực để xử lý mọi yêu cầu production vì quy trình xin nâng quyền mất quá nhiều thời gian.
Một tổ chức triển khai JIT access nhưng yêu cầu quyền chỉ cần trưởng nhóm phê duyệt; người yêu cầu có thể tự chọn thời lượng tám giờ dù thao tác dự kiến chỉ mất vài phút.
Một workflow JIT đã hết thời hạn nhưng access token và phiên console được cấp trước đó vẫn hoạt động, cho phép người dùng tiếp tục thay đổi tài nguyên production.
Một nhóm vận hành muốn áp dụng JEA cho máy chủ Windows nhưng các endpoint quản trị hiện vẫn cho phép chạy PowerShell tùy ý và truy cập mọi module hệ thống.
Một nhóm Linux dùng sudoers để giới hạn lệnh quản trị; cấu hình cho phép chạy trình soạn thảo và công cụ sao lưu với quyền root, từ đó người dùng có thể thoát khỏi giới hạn lệnh.
Một tài khoản quản trị dùng chung cho ca trực đêm; mọi người đều biết mật khẩu và audit log chỉ ghi tên tài khoản chung nên không thể quy trách nhiệm cho cá nhân.
Một hệ thống legacy chỉ hỗ trợ một tài khoản root dùng chung và không hỗ trợ SSO hoặc MFA; nhóm vận hành cần đưa tài khoản này vào PAM mà vẫn duy trì khả năng hỗ trợ ứng dụng.
Một nhân viên nhà thầu kết thúc hợp đồng nhưng tài khoản VPN, SSH key và tài khoản quản trị database vẫn còn hiệu lực vì các hệ thống do nhiều nhóm khác nhau quản lý.
Một tổ chức dùng vault để cấp phát mật khẩu quản trị theo phiên checkout; người dùng tải secret về máy cá nhân rồi tiếp tục sử dụng sau khi phiên checkout đã hết hạn.
Một vault tự động rotate mật khẩu local administrator nhưng một số máy chủ không nhận được lần cập nhật do offline; credential cũ và mới không được theo dõi nhất quán.
Một service account dùng mật khẩu tĩnh để kết nối database từ nhiều ứng dụng; đội vận hành muốn xoay vòng credential nhưng không biết tất cả consumer đang phụ thuộc vào tài khoản này.
Một ứng dụng cũ lưu private key SSH của service account trong file cấu hình trên máy chủ; key được sao chép sang nhiều môi trường và không có inventory người hoặc tiến trình đang sử dụng.
Một tổ chức chuyển SSH sang certificate ngắn hạn do CA nội bộ cấp; một số automation vẫn dùng authorized_keys lâu dài và có thể bỏ qua quy trình cấp chứng chỉ mới.
Một nhóm SRE lưu credential production trong secret manager nhưng cấp quyền đọc toàn bộ secret cho mọi pipeline để đơn giản hóa việc triển khai.
Một pipeline CI/CD có quyền Administrator trên toàn bộ cloud subscription; khi một build runner bị xâm nhập, attacker có thể thay đổi IAM, network và workload production.
Một tài khoản deploy Kubernetes có cluster-admin được dùng chung bởi nhiều pipeline và kỹ sư; kubeconfig được lưu trong artifact của job để các bước sau tái sử dụng.
Một cluster Kubernetes dùng service account token dài hạn trong manifest và repository; token có quyền tạo pod đặc quyền trên nhiều namespace.
Một nền tảng cloud dùng role assumption cho quản trị viên nhưng trust policy cho phép principal từ nhiều account không liên quan assume role nhạy cảm.
Một IAM role chứa wildcard trên mọi resource vì nhóm phát triển không biết chính xác tài nguyên nào cần quyền; thay đổi này vô tình mở rộng khả năng đọc và xóa dữ liệu.
Một DBA có quyền SUPER hoặc quyền quản trị tương đương trên mọi database production dù công việc hằng ngày chỉ cần xem query plan và xử lý schema của một dịch vụ.
Một quản trị viên database cần chạy migration khẩn cấp; tài khoản cá nhân không có quyền DDL nhưng quy trình cấp quyền tạm thời chưa có nên nhóm dùng credential DBA dùng chung.
Một tài khoản quản trị firewall được tích hợp vào vault nhưng giao diện thiết bị vẫn cho phép đăng nhập trực tiếp bằng mật khẩu cũ không được rotate.
Một nhà cung cấp bên thứ ba cần truy cập máy chủ production để bảo trì; tài khoản VPN của họ có thể truy cập cả subnet quản trị và không có lịch hết hạn.
Một bastion host ghi nhận SSH session nhưng cho phép người dùng tạo tunnel và port forwarding tới mạng nội bộ mà policy không kiểm tra đích cuối.
Một phiên RDP được ghi hình nhưng hệ thống không liên kết recording với ticket, người dùng đã xác thực và lý do truy cập nên nhóm kiểm toán không thể đối chiếu thao tác.
Một nền tảng session monitoring chỉ cảnh báo sau khi phiên kết thúc; thao tác xóa hàng loạt tài nguyên có thể diễn ra trong thời gian dài mà không có can thiệp.
Một chính sách session recording ghi cả mật khẩu, token và dữ liệu khách hàng được nhập trong terminal; kho lưu trữ recording có quyền đọc rộng hơn cả hệ thống production.
Một phiên quản trị bị bỏ quên trên jump host sau giờ làm; timeout chỉ áp dụng cho màn hình RDP nhưng kết nối SSH bên trong vẫn duy trì hoạt động.
Một nhân viên dùng clipboard để sao chép password từ vault sang phiên quản trị; clipboard history và đồng bộ đám mây trên máy trạm có thể giữ lại credential.
Một công cụ endpoint privilege management cho phép người dùng nâng quyền cục bộ theo yêu cầu; rule hiện tại chỉ kiểm tra tên file thực thi và bỏ qua publisher, hash cùng đường dẫn thực tế.
Một nhóm hỗ trợ cần quyền admin cục bộ để cài driver; quyền Local Administrators đã được cấp vĩnh viễn cho toàn bộ nhân viên IT thay vì theo từng tác vụ.
Một quy trình access review gửi danh sách tài khoản đặc quyền cho manager nhưng không hiển thị lần sử dụng gần nhất, phạm vi resource hoặc lý do cấp quyền.
Một tài khoản break-glass được tạo để dùng khi SSO hoặc IdP ngừng hoạt động; mật khẩu được niêm phong nhưng không có kiểm tra định kỳ và không có cảnh báo khi sử dụng.
Một sự cố production buộc đội vận hành dùng break-glass account; sau khi khôi phục, không ai thu hồi phiên, đổi credential hoặc rà soát các hành động đã thực hiện.
Một tổ chức yêu cầu MFA cho mọi tài khoản quản trị nhưng phương thức hiện tại là OTP qua SMS; một cuộc tấn công phishing real-time đã chiếm được phiên đăng nhập đặc quyền.
Một quản trị viên có quyền truy cập từ thiết bị cá nhân chưa được quản lý; PAM chỉ xác thực người dùng mà không đánh giá posture, mã hóa ổ đĩa hoặc trạng thái EDR của thiết bị.
Một workflow phê duyệt JIT cho phép người yêu cầu và người phê duyệt thuộc cùng một nhóm, đồng thời không yêu cầu ticket hoặc mục đích nghiệp vụ.
Một yêu cầu nâng quyền production được phê duyệt cho một resource cụ thể nhưng session broker cho phép người dùng truy cập các máy chủ khác trong cùng subnet.
Một tổ chức triển khai vault HA nhưng các node dự phòng không đồng bộ đầy đủ metadata và audit log; khi node chính lỗi, credential có thể truy cập nhưng không có bằng chứng phiên sử dụng.
Một vault ngừng hoạt động trong giờ cao điểm và đội vận hành lưu bản sao mật khẩu quản trị trong spreadsheet mã hóa để duy trì hoạt động khẩn cấp.
Một quy trình rotation đổi mật khẩu trên vault trước rồi mới cập nhật các hệ thống phụ thuộc; một số service restart thất bại và không thể xác thực tới database.
Một lần rotation credential thành công trên phần lớn máy chủ nhưng một số thiết bị mạng offline vẫn dùng mật khẩu cũ; inventory không ghi nhận trạng thái cập nhật từng tài sản.
Một tổ chức phát hiện private key của tài khoản automation đã xuất hiện trong repository công khai; chưa xác định được pipeline, máy chủ và nhà cung cấp nào đang dùng key này.
Một service account được dùng tương tác qua SSH dù chỉ được thiết kế cho batch job; credential của nó có thể đăng nhập shell và thực hiện các thao tác ngoài mục đích.
Một workload cloud dùng access key dài hạn được cấp quyền quản trị; nhóm nền tảng muốn chuyển sang workload identity nhưng có nhiều job chạy ngoài cloud chưa hỗ trợ cơ chế mới.
Một hệ thống PAM tích hợp HR để thu hồi quyền khi nhân viên nghỉ việc; dữ liệu HR cập nhật chậm khiến tài khoản quản trị vẫn hoạt động thêm nhiều ngày.
Một tài khoản đặc quyền thuộc nhóm nested group và được cấp quyền qua nhiều đường khác nhau; nhóm IAM không thể xác định đầy đủ quyền hiệu lực khi cần thu hồi.
Một tổ chức cần chứng minh với kiểm toán viên ai đã truy cập hệ thống trọng yếu, ai phê duyệt, lệnh nào được chạy và credential nào đã được sử dụng mà không tiết lộ secret.
Một kho session recording có thời hạn lưu giữ không phù hợp; dữ liệu chứa thông tin nhạy cảm được lưu quá lâu nhưng các bản ghi cần thiết cho điều tra lại bị xóa sớm.
Một cảnh báo PAM phát hiện đăng nhập quản trị ngoài giờ nhưng không phân biệt lịch bảo trì đã phê duyệt với hành vi bất thường, tạo ra quá nhiều false positive.
Một hệ thống phát hiện cùng credential quản trị được dùng đồng thời từ hai quốc gia và nhiều địa chỉ IP; chưa có quy trình xác minh session và thu hồi credential khẩn cấp.
Một quản trị viên bị nghi chiếm đoạt tài khoản trong khi phiên SSH vẫn đang hoạt động; nhóm ứng cứu cần khóa quyền, chấm dứt session và bảo toàn bằng chứng mà không phá hủy log.
Một công ty có nhiều nền tảng PAM riêng cho Windows, Linux, database và cloud; mỗi nền tảng quản lý vault, approval và session recording khác nhau khiến chính sách không nhất quán.
Một tổ chức triển khai PAM cho cả tài khoản người dùng và tài khoản máy; các secret machine-to-machine được checkout thủ công và không có cơ chế rotation hoặc identity binding tự động.
Một nhóm vận hành muốn áp dụng least privilege cho tài khoản quản trị nhưng chỉ dựa vào job title; quyền thực tế theo tác vụ, môi trường và thời gian chưa được phân tích.
Một hệ thống PAM cấp quyền JIT dựa trên ticket đã mở; ticket có thể bị tái sử dụng cho nhiều lần truy cập và không ràng buộc với session hoặc resource cụ thể.
Một lần kiểm toán phát hiện một số thao tác đặc quyền được thực hiện trực tiếp bằng tài khoản local không đi qua PAM; nhóm vận hành chưa có cơ chế phát hiện đường truy cập bypass.
Một trung tâm dữ liệu cần quyền quản trị thiết bị vật lý khi mạng và IdP nội bộ mất kết nối; quy trình offline access chưa xác định người giữ credential, phê duyệt kép và bằng chứng sau sự cố.
Một tổ chức cần đánh giá hiệu quả PAM sau sáu tháng nhưng chỉ đo số tài khoản đã đưa vào vault; thời gian cấp quyền, quyền thường trực, phiên không ghi hình và credential chưa rotate chưa được thống kê.
