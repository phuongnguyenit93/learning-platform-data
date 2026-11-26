Bạn phân biệt brute force, password spraying và credential stuffing theo cách kẻ tấn công lựa chọn tài khoản và mật khẩu như thế nào?
Bạn nhận diện dấu hiệu một chiến dịch thử nhiều mật khẩu trên một tài khoản khác gì với thử một mật khẩu trên nhiều tài khoản ra sao?
Bạn xác định những nguồn dữ liệu cần kết hợp để phát hiện đăng nhập tự động từ thông tin xác thực bị rò rỉ như thế nào?
Bạn phân biệt đăng nhập thất bại do người dùng quên mật khẩu với hành vi dò mật khẩu dựa trên chuỗi sự kiện nào?
Bạn đánh giá rủi ro của việc chỉ giới hạn số lần đăng nhập theo địa chỉ IP khi kẻ tấn công dùng proxy hoặc mạng phân tán như thế nào?
Bạn thiết kế rate limit đồng thời theo tài khoản, IP, thiết bị và phạm vi mạng để giảm lạm dụng mà không chặn nhầm người dùng hợp lệ ra sao?
Bạn lựa chọn cửa sổ thời gian, ngưỡng và cách tăng dần thời gian chờ dựa trên lưu lượng đăng nhập bình thường như thế nào?
Bạn phân biệt rate limiting ở gateway với giới hạn tại dịch vụ xác thực về khả năng áp dụng nhất quán như thế nào?
Bạn thiết kế bộ đếm đăng nhập phân tán để nhiều instance không vô tình cho phép vượt ngưỡng khi nhận request đồng thời ra sao?
Bạn xử lý khi kho lưu trạng thái rate limit hoặc dịch vụ cache tạm thời không khả dụng mà vẫn bảo vệ luồng đăng nhập như thế nào?
Bạn đánh giá trade-off giữa khóa tài khoản sau nhiều lần thất bại với nguy cơ attacker cố ý khóa tài khoản của nạn nhân ra sao?
Bạn lựa chọn progressive delay, temporary lockout hay yêu cầu xác minh tăng cường theo mức độ rủi ro như thế nào?
Bạn thiết kế giới hạn riêng cho đăng nhập, xác minh MFA, gửi OTP và yêu cầu khôi phục mật khẩu ra sao?
Bạn ngăn việc phân tán request qua nhiều endpoint hoặc nhiều biến thể API để né bộ đếm rate limit như thế nào?
Bạn xác định cách chuẩn hóa định danh tài khoản trước khi áp dụng rate limit để tránh bypass bằng chữ hoa, Unicode hoặc alias ra sao?
Bạn phát hiện password spraying trên nhiều tài khoản khi mỗi tài khoản chỉ có một vài lần đăng nhập thất bại như thế nào?
Bạn lựa chọn tín hiệu để phân biệt credential stuffing với người dùng hợp lệ đăng nhập từ thiết bị hoặc địa điểm mới ra sao?
Bạn kiểm soát thử mật khẩu bị rò rỉ hoặc mật khẩu phổ biến mà không lưu hoặc ghi log mật khẩu thô như thế nào?
Bạn xác định khi nào cần kiểm tra mật khẩu trong danh sách bị lộ và cách bảo vệ dữ liệu gửi tới dịch vụ kiểm tra ra sao?
Bạn thiết kế thông báo đăng nhập thất bại không tiết lộ tài khoản có tồn tại hay không như thế nào?
Bạn phân tích các kênh dò tài khoản qua thông báo đăng nhập, đăng ký, quên mật khẩu và xác minh email ra sao?
Bạn kiểm tra chênh lệch thời gian phản hồi giữa tài khoản tồn tại và không tồn tại để phát hiện timing-based enumeration như thế nào?
Bạn thiết kế response code, message và hành vi gửi email đồng nhất để hạn chế account enumeration ra sao?
Bạn cân bằng yêu cầu thông báo rõ cho người dùng với việc không tiết lộ trạng thái tài khoản cho người ngoài như thế nào?
Bạn xác định nguy cơ dò tài khoản qua autocomplete, gợi ý tên người dùng hoặc endpoint tra cứu danh tính ra sao?
Bạn lựa chọn dữ liệu và ngưỡng để phát hiện nhiều tài khoản được thử từ một thiết bị hoặc fingerprint tương tự như thế nào?
Bạn đánh giá độ tin cậy của IP reputation khi người dùng hợp lệ có thể dùng NAT, VPN, mạng di động hoặc proxy doanh nghiệp ra sao?
Bạn kết hợp IP, ASN, quốc gia, thiết bị, cookie và lịch sử hành vi để tính rủi ro đăng nhập như thế nào?
Bạn phát hiện hành vi impossible travel hoặc tốc độ di chuyển bất thường mà vẫn xét đến VPN và sai lệch vị trí IP ra sao?
Bạn xác định cách xử lý đăng nhập từ thiết bị mới khi các tín hiệu rủi ro khác vẫn bình thường như thế nào?
Bạn thiết kế risk-based authentication để chỉ yêu cầu xác minh bổ sung khi mức rủi ro vượt chính sách ra sao?
Bạn lựa chọn giữa CAPTCHA, email verification, OTP và MFA step-up dựa trên loại hành vi đáng ngờ như thế nào?
Bạn đánh giá giới hạn của CAPTCHA trước bot farm, dịch vụ giải CAPTCHA và trình duyệt tự động như thế nào?
Bạn thiết kế challenge sao cho không tạo một endpoint mới có thể bị lạm dụng để gửi OTP hoặc tiêu tốn chi phí ra sao?
Bạn xác định khi nào cần yêu cầu MFA lại cho hành động nhạy cảm dù phiên đăng nhập hiện tại vẫn hợp lệ như thế nào?
Bạn lựa chọn phương thức MFA chống phishing khi người dùng đăng nhập từ thiết bị hoặc mạng có rủi ro cao ra sao?
Bạn ngăn attacker lợi dụng MFA fatigue bằng cách giới hạn push prompt và yêu cầu người dùng xác nhận ngữ cảnh đăng nhập như thế nào?
Bạn phát hiện và xử lý OTP guessing, OTP replay và việc gửi lại mã xác minh quá nhiều lần ra sao?
Bạn thiết kế OTP có thời hạn ngắn, ràng buộc đúng mục đích và chỉ sử dụng được một lần như thế nào?
Bạn bảo vệ mã khôi phục MFA và quy trình thay đổi thiết bị xác thực khỏi bị chiếm đoạt như thế nào?
Bạn xác định tín hiệu cần thiết để phát hiện SIM swap hoặc thay đổi số điện thoại ngay trước một lần xác thực nhạy cảm ra sao?
Bạn thiết kế password reset token có entropy đủ lớn, thời hạn hợp lý, ràng buộc tài khoản và cơ chế tiêu thụ một lần như thế nào?
Bạn ngăn reset token bị replay hoặc tiếp tục dùng được sau khi mật khẩu đã được thay đổi ra sao?
Bạn kiểm soát rate limit và chi phí gửi email hoặc SMS trong luồng quên mật khẩu như thế nào?
Bạn thiết kế phản hồi quên mật khẩu không tiết lộ tài khoản có tồn tại nhưng vẫn giúp chủ tài khoản hợp lệ hoàn tất quy trình ra sao?
Bạn xác định khi nào cần thu hồi toàn bộ phiên hiện tại sau khi đặt lại mật khẩu hoặc khôi phục tài khoản như thế nào?
Bạn bảo vệ quy trình đổi email, đổi số điện thoại và thay phương thức MFA trước nguy cơ attacker chiếm phiên hợp lệ như thế nào?
Bạn đánh giá rủi ro social engineering trong quy trình hỗ trợ khách hàng khôi phục tài khoản ra sao?
Bạn thiết kế xác minh tăng cường cho yêu cầu reset do nhân viên hỗ trợ thực hiện mà không dựa vào câu hỏi bảo mật yếu như thế nào?
Bạn xác định cách xử lý yêu cầu khôi phục khi người dùng mất đồng thời email, điện thoại và thiết bị MFA ra sao?
Bạn bảo vệ session cookie bằng Secure, HttpOnly, SameSite và chính sách domain/path phù hợp như thế nào?
Bạn xác định thời điểm cần rotate session ID sau đăng nhập, nâng quyền hoặc hoàn tất MFA ra sao?
Bạn phát hiện session hijacking từ thay đổi thiết bị, IP, user agent hoặc hành vi phiên bất thường như thế nào?
Bạn đánh giá giới hạn của việc ràng buộc phiên vào IP hoặc fingerprint khi người dùng di chuyển giữa các mạng ra sao?
Bạn thiết kế cơ chế thu hồi session và refresh token sau khi phát hiện tài khoản bị chiếm đoạt như thế nào?
Bạn phát hiện refresh token reuse và xử lý cả token family khi có dấu hiệu sao chép token ra sao?
Bạn phân biệt đăng xuất khỏi một thiết bị với thu hồi tất cả phiên và lựa chọn hành vi mặc định sau sự cố như thế nào?
Bạn xác định cách bảo vệ session khi access token bị đánh cắp nhưng mật khẩu người dùng chưa bị thay đổi ra sao?
Bạn phát hiện cookie hoặc token bị gửi từ thiết bị lạ trong khi tài khoản vẫn có hoạt động hợp lệ đồng thời như thế nào?
Bạn thiết kế thông báo cho chủ tài khoản về đăng nhập mới, thay đổi thông tin xác thực và hành động khôi phục ra sao?
Bạn lựa chọn dữ liệu trong security event log để điều tra abuse mà không ghi mật khẩu, OTP hoặc token bí mật như thế nào?
Bạn xây dựng metric và alert cho login failure rate, account lockout, OTP send volume, password reset và token reuse ra sao?
Bạn phân biệt spike đăng nhập thất bại do chiến dịch tấn công với sự cố SSO, DNS hoặc một bản phát hành lỗi như thế nào?
Bạn thiết kế phát hiện bất thường theo baseline từng tài khoản và toàn hệ thống để hạn chế false positive ra sao?
Bạn lựa chọn cách gom nhóm sự kiện theo tài khoản, IP, thiết bị và thời gian để phát hiện chiến dịch có phân tán như thế nào?
Bạn xác định ngưỡng cảnh báo để đội bảo mật can thiệp trước khi nhiều tài khoản bị chiếm đoạt ra sao?
Bạn xây dựng quy trình ứng phó khi phát hiện credential stuffing thành công trên một nhóm tài khoản như thế nào?
Bạn xác định thứ tự containment gồm chặn nguồn tấn công, thu hồi phiên, reset credential và thông báo người dùng ra sao?
Bạn bảo toàn bằng chứng đăng nhập và audit trail khi xử lý tài khoản bị chiếm đoạt như thế nào?
Bạn thiết kế quy trình hỗ trợ người dùng bị khóa nhầm mà không mở ra kênh bypass kiểm soát bảo mật ra sao?
Bạn đánh giá tác động của rate limit quá nghiêm ngặt tới người dùng chung IP, người dùng khuyết tật hoặc mạng chất lượng thấp như thế nào?
Bạn xác định các chỉ số trải nghiệm như tỷ lệ challenge, tỷ lệ hoàn tất đăng nhập và false lockout để cân bằng bảo mật ra sao?
Bạn thử nghiệm chính sách chống abuse bằng dữ liệu mô phỏng credential stuffing, password spraying và account enumeration như thế nào?
Bạn kiểm thử rate limit phân tán với nhiều instance và request đồng thời để xác minh ngưỡng không bị vượt qua ra sao?
Bạn kiểm thử hành vi khi cache, risk engine hoặc dịch vụ CAPTCHA không khả dụng để bảo đảm chính sách fail-safe phù hợp như thế nào?
Bạn thiết kế regression test cho luồng MFA, password reset, session revocation và refresh token reuse như thế nào?
Bạn đánh giá hiệu quả của một biện pháp chống abuse bằng tỷ lệ tấn công bị chặn, false positive và mức độ hoàn tất của người dùng hợp lệ ra sao?
