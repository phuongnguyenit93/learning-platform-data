Một cổng VPN yêu cầu mật khẩu và mã PIN do chính người dùng đặt, nhưng nhóm vận hành đang xem hai thông tin này là hai yếu tố độc lập.
Một ứng dụng yêu cầu mật khẩu và câu hỏi bảo mật về tên trường cũ, trong khi cả hai thông tin đều có thể bị thu thập từ mạng xã hội.
Nhân viên đăng nhập bằng mật khẩu rồi nhận OTP qua email công ty, nhưng hộp thư đó dùng cùng mật khẩu và chưa bật MFA.
Một khách hàng bị chiếm số điện thoại qua SIM swap và kẻ tấn công dùng SMS OTP để vượt qua bước xác minh tài khoản ngân hàng.
Nhân viên thường xuyên công tác quốc tế nhận SMS OTP chậm hoặc không nhận được khi roaming, khiến họ không thể truy cập hệ thống đúng giờ.
Trung tâm chăm sóc khách hàng cho phép chuyển sang cuộc gọi thoại để nhận mã khi SMS thất bại, nhưng quy trình xác minh số điện thoại chưa được rà soát.
Người dùng quét mã QR TOTP tại một máy tính công cộng và sau đó phát hiện có ảnh chụp màn hình mã thiết lập được lưu trong thư mục tải xuống.
Một nhóm nhân viên nhập mã TOTP liên tục thất bại sau khi điện thoại mới bị lệch đồng hồ vài phút so với máy chủ xác thực.
Thiết bị tạo mã HOTP ngoại tuyến bị lệch bộ đếm sau nhiều lần người dùng bấm nút nhưng không gửi mã đến máy chủ.
Nhân viên nhận hàng chục thông báo push MFA trong đêm và cuối cùng bấm Approve để các thông báo ngừng xuất hiện.
Ứng dụng đã bật number matching cho push MFA nhưng màn hình phê duyệt vẫn không hiển thị tên dịch vụ, vị trí hoặc thông tin phiên đăng nhập.
Kẻ tấn công dùng trang đăng nhập giả để chuyển tiếp mật khẩu và OTP TOTP theo thời gian thực trước khi mã hết hạn.
Một doanh nghiệp triển khai passkey đồng bộ qua tài khoản cloud cá nhân, nhưng chưa đánh giá rủi ro khi tài khoản cloud bị chiếm.
Quản trị viên làm mất khóa bảo mật FIDO2 duy nhất và cần khôi phục quyền truy cập vào hệ thống quản trị hạ tầng.
Nhân viên thời vụ không có điện thoại thông minh riêng nhưng chính sách MFA của công ty chỉ chấp nhận ứng dụng tạo mã trên smartphone.
Một hệ thống dùng sinh trắc học trên điện thoại để mở khóa khóa riêng của passkey, nhưng tài liệu nội bộ mô tả dữ liệu khuôn mặt được gửi đến máy chủ.
Người dùng đăng nhập trên máy kiosk dùng chung và trình duyệt vẫn giữ trạng thái thiết bị đáng tin cậy sau khi người trước đã rời đi.
Một nhóm bảo mật xem device fingerprint dựa trên trình duyệt và địa chỉ IP là yếu tố MFA thứ hai để thay thế khóa bảo mật.
Cookie phiên của một nhân viên bị đánh cắp sau khi họ hoàn thành MFA, và kẻ tấn công dùng cookie đó truy cập mà không thấy thử thách mới.
Nhân viên đăng nhập từ quốc gia và thiết bị chưa từng dùng, nhưng hệ thống chỉ kiểm tra mật khẩu vì chính sách MFA thích ứng chưa được cấu hình.
Người dùng đã đăng nhập bình thường nhưng cần phê duyệt một khoản chuyển tiền lớn, trong khi ứng dụng chưa có quy tắc step-up authentication cho giao dịch rủi ro cao.
Một cổng thanh toán chấp nhận OTP hợp lệ nhưng mã không gắn với số tiền và tài khoản thụ hưởng đang được xác nhận.
Kẻ tấn công thử hàng nghìn OTP trên một tài khoản vì endpoint xác minh mã không có giới hạn tốc độ hoặc kiểm soát thử sai.
Người dùng yêu cầu nhiều OTP liên tiếp do tin nhắn đến chậm, và hệ thống chấp nhận cả mã cũ lẫn mã mới trong cùng khoảng thời gian.
Mã OTP vẫn được chấp nhận nhiều phút sau khi phát hành, dù người dùng đã yêu cầu mã mới và phiên đăng nhập ban đầu không còn hoạt động.
Người dùng lưu recovery codes trong ảnh chụp màn hình đồng bộ lên dịch vụ lưu trữ cá nhân và sau đó làm mất quyền kiểm soát tài khoản cloud.
Một nhân viên đổi điện thoại và chuyển ứng dụng authenticator bằng bản sao lưu không được mã hóa, trong khi thiết bị cũ vẫn còn đăng ký.
Khách hàng mất điện thoại và yêu cầu tổng đài tắt MFA sau khi chỉ cung cấp ngày sinh cùng bốn số cuối của giấy tờ tùy thân.
Kẻ tấn công gọi helpdesk giả danh lãnh đạo cấp cao và yêu cầu đặt lại yếu tố MFA trước một cuộc họp khẩn.
Địa chỉ email khôi phục tài khoản bị chiếm, và kẻ tấn công dùng luồng khôi phục email để xóa yếu tố MFA hiện tại.
Quản trị viên cần truy cập khẩn cấp khi tất cả yếu tố MFA cá nhân bị mất, nhưng tổ chức chưa có tài khoản break-glass được kiểm soát.
Nhà cung cấp SSO gửi assertion cho ứng dụng với thông tin người dùng đã xác thực, nhưng ứng dụng không kiểm tra mức assurance hoặc thời điểm MFA gần nhất.
Người dùng đã thực hiện MFA khi đăng nhập SSO buổi sáng, nhưng đến cuối ngày truy cập dữ liệu nhạy cảm mà ứng dụng không yêu cầu xác thực lại.
Trong lúc dịch vụ MFA bên ngoài gặp sự cố, một hệ thống tự động bỏ qua thử thách MFA cho mọi người dùng để duy trì khả năng đăng nhập.
Nhân viên làm việc tại khu vực không có kết nối mạng cần sử dụng TOTP ngoại tuyến, nhưng thiết bị và máy chủ thường xuyên lệch thời gian.
Phiên enrollment MFA được mở ngay sau khi đặt lại mật khẩu và kẻ tấn công đang chiếm phiên trình duyệt đó để đăng ký thiết bị của họ.
Người dùng có thể xóa yếu tố MFA hiện tại chỉ bằng một phiên đã đăng nhập lâu ngày mà không cần xác thực lại hoặc xác minh yếu tố thay thế.
Một tổ chức triển khai MFA bắt buộc trong một ngày cho toàn bộ nhân viên, bao gồm người làm việc từ xa và người chưa kịp đăng ký yếu tố dự phòng.
Nhiều nhân viên dùng chung một tài khoản vận hành tại phòng điều khiển, khiến mỗi người không có yếu tố MFA và dấu vết xác thực riêng.
Người dùng khiếm thính không thể sử dụng phương thức OTP qua cuộc gọi thoại, trong khi cổng hỗ trợ chưa cung cấp lựa chọn MFA thay thế phù hợp.
Một tài khoản bị khóa sau nhiều lần nhập sai OTP và kẻ tấn công có thể cố tình kích hoạt khóa tài khoản của các nhân viên khác.
Nhóm vận hành phát hiện nhiều lần từ chối push MFA và đăng nhập thất bại nhưng audit log không ghi loại yếu tố, thiết bị hoặc kết quả thử thách.
Một nhân viên mất đồng thời điện thoại, khóa bảo mật và recovery codes trong chuyến công tác, nhưng vẫn cần truy cập dữ liệu phục vụ hoạt động khẩn cấp.
Ứng dụng ngân hàng cho phép dùng SMS làm phương thức dự phòng dù khách hàng đã đăng ký passkey chống phishing và số điện thoại có nguy cơ bị chiếm.
Nhân viên đã đăng ký nhiều yếu tố MFA nhưng chính sách không xác định yếu tố nào được phép dùng cho tài khoản đặc quyền và thao tác nhạy cảm.
