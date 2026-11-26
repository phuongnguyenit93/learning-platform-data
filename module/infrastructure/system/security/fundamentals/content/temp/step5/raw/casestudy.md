Một công ty lập asset inventory chỉ từ máy chủ do bộ phận hạ tầng quản lý; các SaaS do từng phòng ban tự đăng ký, kho dữ liệu thử nghiệm và thiết bị cá nhân truy cập công việc không được ghi nhận nên phạm vi bảo vệ bị thiếu.
Data classification chỉ dựa trên tên database mà không xét nội dung từng trường; bảng chứa số định danh và thông tin sức khỏe bị gắn nhãn internal thông thường, dẫn tới áp dụng sai quyền truy cập và thời hạn lưu trữ.
Một dịch vụ đánh giá CIA triad chỉ ưu tiên confidentiality bằng cách mã hóa toàn bộ dữ liệu nhưng không có dự phòng hoặc kế hoạch khôi phục; sự cố khóa mã hóa làm hệ thống ngừng phục vụ và mục tiêu availability bị bỏ quên.
Nhóm đánh giá integrity (tính toàn vẹn) chỉ tập trung ngăn sửa dữ liệu mà không kiểm soát quyền đọc và confidentiality; một tài khoản nội bộ có thể tải hàng loạt hồ sơ hợp lệ về mặt kỹ thuật nhưng trái phép về mục đích.
Threat model của ứng dụng chỉ liệt kê hacker bên ngoài; nhân viên nội bộ, nhà cung cấp, tài khoản dịch vụ bị chiếm và lỗi cấu hình tự động hóa không được xét trong các luồng tin cậy.
Nhóm coi vulnerability scan có điểm CVSS cao là rủi ro lớn nhất mà không xét khả năng khai thác, mức phơi nhiễm, dữ liệu bị ảnh hưởng và kiểm soát bù trừ; thứ tự khắc phục không phản ánh rủi ro thực tế.
Một rủi ro được chấp nhận vì hệ thống sắp thay thế nhưng dự án trì hoãn nhiều quý; quyết định risk acceptance không có chủ sở hữu, ngày hết hạn hoặc điều kiện đánh giá lại.
Kiểm soát bảo mật được thiết kế chỉ dựa vào một firewall biên; khi tài khoản hợp lệ bị chiếm, attacker di chuyển ngang qua mạng nội bộ mà không gặp lớp kiểm soát bổ sung.
Kiến trúc zero trust được quảng bá nhưng mạng nội bộ vẫn mặc định tin cậy mọi workload cùng subnet; thiết bị bị xâm nhập có thể truy cập dịch vụ không liên quan mà không xác minh danh tính và ngữ cảnh.
Chính sách authorization và least privilege được áp dụng cho người dùng nhưng service account vẫn có quyền quản trị toàn bộ môi trường; một workload bị chiếm có thể sửa cấu hình và đọc dữ liệu của nhiều hệ thống.
Nhiều quản trị viên dùng chung một tài khoản root để thao tác ngoài giờ; audit log không thể quy hành động về cá nhân và khi credential bị lộ không thể thu hồi riêng cho một người.
Tài khoản nhân viên chuyển bộ phận vẫn giữ nhóm quyền cũ vì quy trình mover chỉ thêm role mới mà không rà soát role đã có; quyền tích lũy vượt nhu cầu công việc.
Tài khoản nhà thầu được tạo không có ngày hết hạn và không gắn với người bảo trợ; hợp đồng kết thúc nhưng credential vẫn hoạt động trong hệ thống.
Authentication cho quản trị chỉ yêu cầu mật khẩu và OTP SMS; attacker thực hiện SIM swap hoặc phishing để vượt lớp xác minh thứ hai mà tổ chức tưởng là MFA mạnh.
Người dùng liên tục nhận push MFA ngoài ý muốn và cuối cùng bấm Approve; hệ thống không có number matching, giới hạn prompt hoặc cảnh báo hành vi MFA fatigue.
Phiên đăng nhập vẫn tồn tại trên thiết bị cũ sau khi người dùng đổi mật khẩu và báo mất thiết bị; hệ thống chỉ cập nhật credential mà không revoke session hoặc refresh token.
API xác minh người gọi đã đăng nhập nhưng không kiểm tra quyền trên từng object; thay ID trong URL cho phép đọc hồ sơ thuộc người dùng khác.
Secret của service account được đặt trực tiếp trong file cấu hình và chia sẻ qua email; nhiều bản sao không được kiểm soát khiến rotation và xác định phạm vi lộ lọt khó khăn.
Quy trình break-glass cấp quyền khẩn cấp nhưng không có thời hạn tự hết, lý do bắt buộc hoặc hậu kiểm; tài khoản đặc quyền tạm thời trở thành đường truy cập thường trực.
Database dùng encryption at rest nhưng ứng dụng và tài khoản vận hành có quyền đọc toàn bộ bản ghi; nhóm nhầm mã hóa thiết bị lưu trữ với kiểm soát truy cập và bảo vệ dữ liệu ở cấp trường.
Client kết nối TLS chỉ kiểm tra certificate chain mà bỏ qua hostname verification; chứng chỉ hợp lệ của domain khác vẫn có thể được dùng để giả mạo endpoint.
Khóa mã hóa được lưu cùng database chứa ciphertext; bản sao lưu bị lấy cắp đồng thời cung cấp cả dữ liệu và khóa để giải mã.
Khóa mã hóa dùng chung nhiều môi trường và không có owner, purpose hoặc lịch rotation; lộ một workload staging có thể ảnh hưởng dữ liệu production.
Backup thành công được báo cáo mỗi đêm nhưng chưa từng thử restore; khi ransomware mã hóa hệ thống chính, tổ chức phát hiện bản sao lưu thiếu khóa và không thể khôi phục.
Firewall rule cho phép toàn bộ outbound traffic để tránh gián đoạn tích hợp; máy bị xâm nhập có thể kết nối tới hạ tầng điều khiển bên ngoài và truyền dữ liệu ra ngoài.
Network segmentation không được áp dụng giữa mạng người dùng, máy chủ, quản trị và thiết bị IoT; các vùng nằm chung một mạng phẳng nên một máy in hoặc camera bị chiếm có thể trở thành bàn đạp tới máy chủ dữ liệu.
Dịch vụ công khai không có giới hạn kết nối hoặc bảo vệ DDoS; một lượng request lớn làm cạn tài nguyên mạng và khiến người dùng hợp lệ không thể truy cập.
EDR bị tắt trên máy chủ quan trọng để giảm tải CPU và không có kiểm soát bù trừ; hoạt động mã độc không được phát hiện ở endpoint có dữ liệu nhạy cảm.
Patch management không theo kịp vòng đời hệ điều hành; máy chủ internet-facing chạy phiên bản đã hết hỗ trợ, bản vá bảo mật không còn được phát hành và lỗ hổng đã biết tiếp tục tồn tại.
Quét lỗ hổng chỉ chạy trên dải IP do nhóm hạ tầng quản lý; tài sản cloud, IPv6, endpoint từ xa và hệ thống do nhà cung cấp vận hành bị bỏ khỏi phạm vi.
Nhóm đóng ticket vulnerability vì scanner không còn phát hiện sau khi đổi banner dịch vụ; phần mềm dễ tổn thương vẫn chạy và chỉ dấu nhận diện đã bị che.
Giao diện quản trị được đưa ra internet để tiện hỗ trợ nhưng chỉ bảo vệ bằng mật khẩu; không có VPN hoặc allowlist nguồn truy cập và không yêu cầu xác minh mạnh.
Object storage chứa bản export khách hàng được cấu hình public-read do dùng template triển khai mặc định; dữ liệu bị truy cập công khai dù ứng dụng chính yêu cầu đăng nhập.
Cloud role của workload có quyền wildcard trên nhiều dịch vụ; khi một container bị khai thác, attacker có thể truy cập secret, snapshot và storage không liên quan.
Endpoint metadata của cloud instance có thể bị workload truy cập qua request do người dùng kiểm soát; lỗi SSRF làm lộ temporary credentials của instance role.
Container image chứa package lỗi thời và chạy bằng root; một lỗ hổng trong ứng dụng có thể dẫn tới quyền cao trong container và tăng khả năng thoát sang host.
Repository công khai chứa file .env có access token còn hiệu lực; xóa file ở commit mới không loại bỏ secret khỏi lịch sử Git và các bản clone.
Software supply chain không được kiểm soát; ứng dụng tải dependency từ registry không tin cậy và package giả mạo tên gần giống dependency thật được đưa vào build rồi thực thi trong pipeline.
CI runner có quyền ghi artifact production và truy cập signing key; pull request không tin cậy chạy script trên runner dùng chung rồi lấy được thông tin phát hành.
Artifact được triển khai mà không xác minh chữ ký hoặc provenance; attacker thay binary trong registry và hệ thống vẫn cài phiên bản không rõ nguồn gốc.
Máy chủ mới được triển khai với tài khoản mặc định và cổng quản trị mở; cấu hình hardening chỉ được thực hiện sau khi hệ thống đã đưa vào mạng.
Ứng dụng nhận dữ liệu đầu vào không tin cậy nhưng chỉ kiểm tra ở giao diện; request trực tiếp có thể gửi payload gây injection hoặc làm sai quy tắc nghiệp vụ.
Trang web chèn dữ liệu người dùng vào HTML mà không encode theo ngữ cảnh; nội dung bình luận chứa markup gây cross-site scripting (XSS) và thực thi script với người xem khác.
Truy vấn database ghép chuỗi từ tham số tìm kiếm; input chứa cú pháp SQL làm thay đổi điều kiện truy vấn và có thể truy cập dữ liệu ngoài phạm vi.
Chức năng upload chỉ kiểm tra phần mở rộng và Content-Type do client gửi; file có nội dung thực thi vẫn được lưu vào vùng web có thể truy cập trực tiếp.
API không áp dụng rate limit hoặc giới hạn kích thước request, số phần tử batch và độ sâu JSON; payload lớn làm cạn CPU và bộ nhớ trước khi xử lý nghiệp vụ.
Log ứng dụng ghi toàn bộ request header và body để hỗ trợ debug; password, session cookie, API key và dữ liệu cá nhân được lưu trong hệ thống log tập trung.
SIEM chỉ thu log từ firewall mà không nhận audit từ cloud, identity provider và endpoint; sự kiện chiếm tài khoản không thể được liên kết thành chuỗi tấn công.
Alert fatigue xuất hiện khi hệ thống phát sinh hàng nghìn sự kiện mức thấp mỗi giờ mà không có phân loại và ưu tiên; analyst bỏ lỡ một cảnh báo lateral movement quan trọng giữa noise.
Các hệ thống dùng đồng hồ lệch nhau nhiều phút và không đồng bộ thời gian; điều tra viên không thể sắp xếp chính xác chuỗi sự kiện giữa gateway, endpoint và identity service.
Đội ứng phó sự cố khởi động lại máy chủ bị nghi xâm nhập trước khi thu thập volatile evidence; dữ liệu bộ nhớ và trạng thái tiến trình cần điều tra bị mất.
Nhân viên phát hiện ransomware nhưng chỉ ngắt một máy trạm; kết nối chia sẻ và tài khoản đặc quyền vẫn hoạt động nên mã độc tiếp tục lan sang máy chủ file.
Khi phát hiện rò rỉ dữ liệu, nhóm xóa log và snapshot để giảm dung lượng trước khi xác định phạm vi; bằng chứng và khả năng truy vết bị phá hủy.
Kế hoạch incident response chỉ liệt kê số điện thoại liên hệ mà không xác định người có quyền cô lập hệ thống, phê duyệt truyền thông hoặc quyết định khôi phục; xử lý bị đình trệ trong sự cố.
Diễn tập tabletop chỉ dùng kịch bản đơn giản và không có bộ phận pháp chế, truyền thông, vận hành hoặc nhà cung cấp; các phụ thuộc quan trọng chỉ lộ ra khi xảy ra sự cố thật.
Tổ chức không xác định nghĩa vụ thông báo khi dữ liệu cá nhân bị lộ; đội xử lý sự cố chậm bảo toàn thông tin và đánh giá nghĩa vụ theo hợp đồng hoặc quy định áp dụng.
Backup được lưu trực tuyến bằng cùng thông tin xác thực quản trị với hệ thống production; ransomware chiếm quyền admin và xóa cả bản sao lưu.
Kế hoạch khôi phục đặt RTO và RPO rất thấp nhưng kiến trúc, dung lượng dự phòng và quy trình chuyển vùng chưa được kiểm chứng; mục tiêu phục hồi không khả thi.
Third-party risk không được quản lý khi nhà cung cấp xử lý dữ liệu khách hàng nhưng hợp đồng không quy định thông báo sự cố, quyền audit, vị trí lưu trữ hoặc thời hạn xóa; tổ chức không kiểm soát được rủi ro chuỗi cung ứng.
Đối tác tích hợp được cấp tài khoản dùng chung và quyền truy cập không giới hạn thời gian; tổ chức không thể phân biệt hoạt động của từng nhân sự nhà cung cấp.
Ứng dụng thu thập vị trí, thiết bị và thông tin định danh dù chức năng không cần; dữ liệu dư thừa làm tăng tác động nếu bị xâm phạm và khó đáp ứng yêu cầu xóa.
Dữ liệu hết thời hạn lưu trữ bị xóa khỏi bảng chính nhưng còn trong log, data lake, backup và bản sao của nhà cung cấp; chính sách retention không bao phủ toàn bộ vòng đời.
Nhân viên nhận email giả mạo yêu cầu đăng nhập vào cổng nội bộ; chương trình awareness chỉ tổ chức một lần mỗi năm và không có kênh báo cáo phishing dễ dùng.
Camera và thiết bị IoT dùng mật khẩu mặc định, firmware không cập nhật và không thể cài EDR; thiết bị bị chiếm có thể làm điểm xâm nhập vào mạng doanh nghiệp.
Security governance chỉ đo số lượng policy được ban hành thay vì mức độ thực thi, thời gian khắc phục và tỷ lệ kiểm soát hiệu quả; lãnh đạo không có dữ liệu để đánh giá rủi ro còn lại.
