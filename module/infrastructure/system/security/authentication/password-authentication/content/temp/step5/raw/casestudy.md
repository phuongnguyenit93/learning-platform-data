Một tổ chức yêu cầu mật khẩu phải chứa chữ hoa, chữ thường, số và ký tự đặc biệt, nhưng nhân viên thường chọn mẫu dễ đoán như Welcome2026!.
Một cổng dịch vụ giới hạn mật khẩu ở tám ký tự và âm thầm cắt bỏ phần dư, khiến hai mật khẩu dài khác nhau được xem là giống nhau.
Người dùng muốn đặt cụm mật khẩu dài có dấu cách, nhưng biểu mẫu từ chối khoảng trắng và khuyến khích họ dùng chuỗi ngắn khó nhớ.
Một hệ thống cho phép mật khẩu phổ biến như Password123 dù danh sách mật khẩu bị lộ đã được cập nhật vào quy trình đăng ký.
Nhân viên phải đổi mật khẩu mỗi 30 ngày dù không có dấu hiệu xâm phạm, dẫn đến việc thêm số thứ tự vào mật khẩu cũ.
Ứng dụng không cho phép dùng password manager hoặc dán mật khẩu vào biểu mẫu, khiến người dùng chọn mật khẩu đơn giản hơn.
Một dịch vụ chỉ chấp nhận ASCII trong mật khẩu, trong khi người dùng tạo mật khẩu dài bằng ký tự Unicode và không hiểu vì sao đăng nhập thất bại.
Hệ thống chuẩn hóa Unicode khi đăng ký nhưng không áp dụng cùng quy tắc khi đăng nhập, dẫn đến một số mật khẩu hợp lệ không thể xác minh.
Người dùng có thể tạo mật khẩu dài hàng nghìn ký tự và gửi liên tục yêu cầu đăng nhập, gây tải CPU và bộ nhớ bất thường.
Một ứng dụng dùng cùng chính sách mật khẩu cho tài khoản quản trị, tài khoản thông thường và tài khoản dịch vụ mà không xét mức độ rủi ro.
Nhân viên tái sử dụng mật khẩu công ty trên một diễn đàn bên ngoài và tài khoản công ty bị truy cập sau khi diễn đàn rò rỉ dữ liệu.
Kẻ tấn công dùng danh sách username/password bị lộ từ dịch vụ khác để thử đăng nhập hàng loạt vào cổng khách hàng.
Một bot thử nhiều tài khoản bằng cùng một mật khẩu phổ biến, trong khi hệ thống chỉ giới hạn số lần thử theo từng địa chỉ IP.
Nhóm vận hành khóa tài khoản sau ba lần đăng nhập sai, và kẻ tấn công lợi dụng cơ chế này để gây từ chối dịch vụ cho nhân viên.
Trang đăng nhập trả thông báo khác nhau cho username không tồn tại và mật khẩu sai, giúp kẻ tấn công thu thập danh sách tài khoản hợp lệ.
Thời gian phản hồi của luồng đăng nhập khác biệt rõ rệt giữa tài khoản tồn tại và tài khoản không tồn tại dù thông báo hiển thị giống nhau.
Một hệ thống chỉ áp dụng rate limit theo IP, nhưng botnet phân tán yêu cầu đăng nhập qua hàng nghìn địa chỉ khác nhau.
Người dùng nhập sai mật khẩu nhiều lần do bàn phím đang bật sai layout, nhưng cơ chế chống brute force khóa tài khoản quá lâu và không có quy trình mở khóa an toàn.
Ứng dụng cho phép thử mật khẩu không giới hạn trên endpoint đăng nhập dự phòng dành cho thiết bị cũ.
Nhân viên hỗ trợ có thể tra cứu mật khẩu hiện tại của khách hàng trong trang quản trị để giúp họ đăng nhập.
Cơ sở dữ liệu người dùng lưu mật khẩu dưới dạng SHA-256 không salt và bản sao lưu bị đánh cắp.
Mọi tài khoản được băm bằng cùng một salt tĩnh cấu hình toàn hệ thống, khiến các mật khẩu giống nhau tạo ra cùng giá trị hash.
Một dịch vụ dùng salt ngẫu nhiên nhưng tạo salt mới mỗi lần xác minh, khiến hệ thống không thể kiểm tra mật khẩu đã lưu.
Nhóm bảo mật chọn SHA-256 lặp nhiều vòng để lưu mật khẩu nhưng chưa đánh giá các password hashing function chuyên dụng và chi phí bộ nhớ.
Máy chủ dùng Argon2id với tham số rất thấp để tiết kiệm CPU, khiến việc dò mật khẩu ngoại tuyến trở nên rẻ hơn dự kiến.
Tham số Argon2id được đặt quá cao trên cụm đăng nhập có lưu lượng lớn, gây cạn bộ nhớ khi có đợt đăng nhập đồng thời.
Ứng dụng dùng bcrypt nhưng không kiểm tra giới hạn độ dài đầu vào theo byte, khiến phần cuối của mật khẩu dài bị bỏ qua.
Một tổ chức lưu pepper cùng cơ sở dữ liệu người dùng, nên kẻ lấy được bản sao dữ liệu cũng có đủ thông tin để xác minh hash ngoại tuyến.
Khóa pepper được lưu trong cấu hình triển khai và nhiều nhóm vận hành có thể đọc, trong khi không có kế hoạch xoay vòng hoặc khôi phục.
Sau khi nâng cấp password hashing parameters, hệ thống tiếp tục giữ hash cũ vô thời hạn dù người dùng đăng nhập thành công hằng ngày.
Một số tài khoản cũ được tạo bằng thuật toán hash yếu, nhưng hệ thống chưa lưu metadata để biết thuật toán và tham số nào đã được dùng.
Người dùng đổi mật khẩu nhưng các phiên đăng nhập cũ trên thiết bị thất lạc vẫn còn hiệu lực trong nhiều ngày.
Luồng đổi mật khẩu chỉ yêu cầu phiên đăng nhập hiện tại và không xác minh lại mật khẩu cũ hoặc một yếu tố xác thực gần đây.
Email đặt lại mật khẩu chứa token có entropy thấp, thời hạn dài và có thể được sử dụng nhiều lần.
Token đặt lại mật khẩu được lưu nguyên văn trong cơ sở dữ liệu, và bản sao dữ liệu bị truy cập trái phép.
Trang đặt lại mật khẩu phản hồi khác nhau khi email tồn tại và không tồn tại, giúp dò danh sách khách hàng.
Liên kết reset password dùng hostname lấy trực tiếp từ header của request, cho phép kẻ tấn công tạo URL khôi phục trỏ đến tên miền giả.
Token reset password xuất hiện trong URL và bị ghi vào access log, analytics hoặc header Referer khi người dùng mở trang khôi phục.
Người dùng yêu cầu nhiều email đặt lại mật khẩu và hệ thống vẫn chấp nhận mọi token cũ sau khi token mới được phát hành.
Nhân viên mất quyền truy cập email khôi phục và yêu cầu helpdesk đặt mật khẩu mới sau khi chỉ cung cấp thông tin cá nhân công khai.
Kẻ tấn công chiếm tài khoản email của người dùng rồi sử dụng chức năng quên mật khẩu để thay đổi thông tin đăng nhập của tài khoản chính.
Một nhân viên nghỉ việc nhưng tài khoản mật khẩu vẫn hoạt động vì quy trình vô hiệu hóa danh tính không đồng bộ với hệ thống đăng nhập.
Tổ chức phát hiện tệp chứa username và password bị đưa lên kho mã nguồn công khai nhưng chưa xác định được tài khoản nào đã bị sử dụng.
Audit log ghi mật khẩu người dùng và token reset trong payload request để tiện tái hiện sự cố.
Sau một vụ rò rỉ hash mật khẩu, đội vận hành chỉ yêu cầu người dùng đổi mật khẩu mà chưa thu hồi phiên, đánh giá credential reuse hoặc giám sát đăng nhập bất thường.
Một hệ thống xác thực dùng chung tài khoản mặc định cho nhiều thiết bị vận hành, khiến không thể quy trách nhiệm cho từng người và khó thu hồi riêng lẻ.
