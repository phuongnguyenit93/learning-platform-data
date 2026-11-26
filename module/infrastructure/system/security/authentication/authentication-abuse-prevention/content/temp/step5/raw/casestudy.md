Một cổng đăng nhập chỉ giới hạn số lần sai theo từng địa chỉ IP; kẻ tấn công phân tán thử mật khẩu cho một tài khoản qua hàng nghìn proxy nên không chạm ngưỡng nào.
Một hệ thống khóa tài khoản sau năm lần đăng nhập sai; kẻ tấn công cố ý nhập sai mật khẩu cho danh sách nhân viên để khóa hàng loạt tài khoản và gây gián đoạn công việc.
Một dịch vụ dùng cùng một bộ đếm thất bại cho username viết hoa và viết thường nhưng chuẩn hóa danh tính không nhất quán, khiến attacker có thể chia lượt thử qua nhiều biến thể tên đăng nhập.
Một trang đăng nhập giới hạn theo IP nhưng nhiều người dùng hợp lệ cùng đi qua NAT doanh nghiệp; giờ cao điểm cả văn phòng bị throttling dù mỗi người chỉ thử sai vài lần.
Một API xác thực chỉ áp dụng rate limit tại gateway công khai; endpoint đăng nhập nội bộ có thể được gọi trực tiếp qua service discovery và bỏ qua giới hạn.
Một ứng dụng giới hạn request theo IP nhưng không giới hạn theo tài khoản; attacker dùng nhiều nguồn IP để brute force mật khẩu của một tài khoản quản trị.
Một nền tảng chỉ giới hạn theo tài khoản nhưng không theo nguồn; một botnet thử một mật khẩu phổ biến trên hàng triệu tài khoản mà mỗi tài khoản chỉ nhận một lần thử.
Một chiến dịch password spraying dùng một số mật khẩu phổ biến trên nhiều tài khoản với khoảng nghỉ dài, khiến ngưỡng phát hiện dựa trên số lần thử liên tiếp không nhận ra mẫu tấn công.
Một dịch vụ phát hiện brute force bằng số lần đăng nhập sai trong một phút nhưng không tính cả các lần thử qua nhiều vùng địa lý hoặc nhiều node xác thực.
Một hệ thống dùng bộ đếm rate limit lưu trong bộ nhớ từng instance; load balancer phân phối request sang nhiều replica khiến giới hạn thực tế cao gấp nhiều lần cấu hình.
Một cache rate limit dùng key không chuẩn hóa username; attacker thay đổi chữ hoa, chữ thường hoặc Unicode để tạo nhiều bucket và né giới hạn.
Một endpoint login nhận cả email và username nhưng rate limit chỉ dùng một trường; attacker chuyển qua lại hai định danh để tăng số lần thử.
Một nền tảng đăng nhập cho phép tài khoản bị khóa tự mở khóa sau thời gian ngắn; bot tự động chờ hết khóa và tiếp tục credential stuffing theo chu kỳ.
Một dịch vụ dùng CAPTCHA sau nhiều lần đăng nhập thất bại nhưng không giới hạn backend authentication; bot gọi endpoint API trực tiếp và bỏ qua CAPTCHA ở giao diện.
Một hệ thống CAPTCHA áp dụng cho mọi request sau khi vượt ngưỡng IP; người dùng hợp lệ dùng mạng di động thay đổi IP liên tục phải giải CAPTCHA lặp lại và bỏ cuộc.
Một cổng đăng nhập phản hồi khác nhau giữa email không tồn tại và mật khẩu sai; attacker dùng danh sách email để dò tài khoản hợp lệ trước khi credential stuffing.
Một chức năng quên mật khẩu trả thông báo và thời gian phản hồi khác nhau tùy tài khoản tồn tại, giúp attacker xác định người dùng qua response timing.
Một API kiểm tra username trả về trạng thái active, locked hoặc pending; endpoint này bị sử dụng để thu thập danh sách tài khoản nội bộ.
Một chiến dịch credential stuffing dùng cặp email/mật khẩu từ vụ rò rỉ bên thứ ba; nhiều tài khoản đăng nhập thành công từ thiết bị và ASN chưa từng thấy.
Một số tài khoản có mật khẩu bị tái sử dụng trên nhiều dịch vụ; attacker đăng nhập thành công bằng credential cũ nhưng hệ thống chỉ cảnh báo khi mật khẩu sai.
Một nền tảng không kiểm tra mật khẩu mới trong danh sách credential đã bị lộ; sau một đợt rò rỉ, người dùng tiếp tục đặt lại đúng mật khẩu đã bị công khai.
Một ứng dụng chỉ phát hiện đăng nhập bất thường dựa trên quốc gia; attacker dùng residential proxy tại cùng quốc gia với nạn nhân nên tín hiệu địa lý không thay đổi.
Một tài khoản xuất hiện hai phiên đăng nhập cách nhau vài phút từ hai châu lục; hệ thống không có chính sách impossible travel hoặc bước xác minh tăng cường.
Một người dùng đăng nhập thành công từ thiết bị mới sau nhiều lần thử sai; hệ thống không yêu cầu MFA bổ sung vì chỉ đánh giá rủi ro trước khi xác thực.
Một dịch vụ đánh dấu thiết bị đáng tin cậy bằng cookie lâu dài; cookie bị đánh cắp và sử dụng trên thiết bị khác nhưng không có cơ chế thu hồi hoặc ràng buộc phiên.
Một hệ thống push MFA gửi thông báo liên tục khi attacker biết mật khẩu; nạn nhân cuối cùng bấm Approve để chấm dứt các thông báo làm phiền.
Một tổ chức bật push MFA nhưng không dùng number matching hoặc hiển thị ngữ cảnh đăng nhập; người dùng chấp thuận nhầm yêu cầu do attacker khởi tạo.
Một dịch vụ TOTP chấp nhận mã trong cửa sổ thời gian quá rộng và không đánh dấu mã đã dùng; attacker có thể phát lại cùng OTP trong nhiều request.
Một endpoint xác minh OTP không giới hạn số lần thử cho mỗi challenge; attacker brute force mã ngắn trước khi challenge hết hạn.
Một ứng dụng gửi SMS OTP không giới hạn tần suất gửi theo tài khoản và số điện thoại; bot tạo chi phí SMS lớn và làm phiền người dùng.
Một API gửi mã xác minh cho phép thay đổi số điện thoại giữa các lần resend nhưng giữ nguyên challenge cũ, tạo điều kiện xác minh nhầm người nhận.
Một quy trình đăng ký MFA cho phép thêm authenticator mới chỉ bằng session cũ; attacker chiếm session có thể đăng ký thiết bị của mình rồi giữ quyền truy cập sau khi nạn nhân đổi mật khẩu.
Một người dùng báo mất điện thoại và gọi hỗ trợ; nhân viên hỗ trợ bỏ qua quy trình kiểm chứng danh tính rồi reset MFA theo yêu cầu từ kẻ mạo danh.
Một chức năng recovery code cho phép dùng lại cùng mã nhiều lần do cập nhật trạng thái không nguyên tử; hai request đồng thời cùng khôi phục thành công.
Một trang đặt lại mật khẩu dùng token có thời hạn dài và không vô hiệu hóa token sau lần sử dụng đầu; liên kết bị lộ trong email vẫn có thể bị dùng lại.
Một email reset password chứa token trong URL; hệ thống analytics và reverse proxy ghi full URL khiến token khôi phục xuất hiện trong log.
Một endpoint đổi email chỉ yêu cầu session đang đăng nhập, không xác minh lại mật khẩu hoặc MFA; attacker có session bị đánh cắp đổi email nhận recovery.
Một quy trình account recovery dựa trên câu hỏi bảo mật có câu trả lời dễ đoán từ mạng xã hội; attacker vượt qua khôi phục dù không có credential chính.
Một nền tảng cho phép support agent impersonate người dùng mà không yêu cầu lý do, phê duyệt hoặc audit; tài khoản có thể bị chiếm qua lạm dụng nội bộ.
Một hệ thống logout chỉ xóa cookie trên browser nhưng không thu hồi session phía server; cookie đã sao chép vẫn truy cập API sau khi người dùng đăng xuất.
Một ứng dụng rotate session ID sau đăng nhập nhưng vẫn chấp nhận session ID cũ trong thời gian grace không giới hạn; attacker giữ phiên cũ và tiếp tục sử dụng.
Một dịch vụ phát hiện session bất thường dựa trên IP và User-Agent nhưng không xét thay đổi hành vi; attacker dùng cùng browser profile và mạng đã quen để tiếp tục thao tác nhạy cảm.
Một tài khoản có hàng chục phiên đồng thời nhưng giao diện bảo mật chỉ hiển thị phiên gần nhất; người dùng không thể nhận biết hoặc thu hồi các phiên bị chiếm.
Một API logout-all gửi sự kiện revoke bất đồng bộ nhưng các node cache session không nhận invalidation kịp thời, khiến phiên bị đánh cắp vẫn hoạt động trong vài phút.
Một chiến dịch bot tạo hàng nghìn tài khoản mới rồi thử đăng nhập luân phiên để phân tán tín hiệu; hệ thống không giới hạn đăng ký, xác minh email hoặc tạo session theo nguồn.
Một endpoint gửi magic link cho phép yêu cầu vô hạn và trả response khác nhau theo email; attacker vừa dò tài khoản vừa làm quá tải email gateway.
Một dịch vụ xác thực dùng chung rate limit store cho login và password recovery; tấn công vào recovery làm cạn quota khiến người dùng hợp lệ không thể đăng nhập.
Một hệ thống risk scoring coi mọi request từ VPN là rủi ro cao; nhân viên làm việc từ xa bị step-up liên tục trong khi attacker dùng mạng residential không bị phát hiện.
Một bộ phát hiện bất thường tự động khóa tài khoản khi có nhiều thất bại nhưng không có quy trình khiếu nại hoặc mở khóa nhanh, gây gián đoạn hàng loạt cho khách hàng hợp lệ.
Một hệ thống chỉ theo dõi số lần đăng nhập thất bại tổng thể; credential stuffing phân tán trên nhiều tài khoản không tạo cảnh báo vì mỗi tài khoản có số lần thất bại thấp.
Một đội vận hành phát hiện nhiều đăng nhập thành công bất thường nhưng log không lưu device ID, nguồn IP, kết quả MFA và session ID đã băm nên không thể xác định phạm vi chiếm đoạt.
Một sự cố credential stuffing được phát hiện muộn; tổ chức chưa có quy trình thu hồi session, yêu cầu đổi mật khẩu, reset MFA, bảo toàn bằng chứng và thông báo người dùng.
