Một ứng dụng lưu mật khẩu người dùng bằng SHA-256 trực tiếp, không salt; sau khi database bị lộ, attacker có thể dùng rainbow table và GPU để dò nhiều mật khẩu phổ biến rất nhanh.
Hệ thống đã thêm salt riêng cho từng mật khẩu nhưng vẫn dùng hash nhanh một vòng; nhóm cần đánh giá password hashing chuyên dụng như Argon2id, scrypt hoặc bcrypt với cost phù hợp để làm chậm dò offline.
Ứng dụng dùng bcrypt nhưng cấu hình cost quá thấp từ nhiều năm trước; năng lực phần cứng hiện tại khiến chi phí thử mỗi mật khẩu không còn phù hợp với rủi ro.
Nhóm nâng cost Argon2id cho mật khẩu mới nhưng không có chiến lược rehash sau đăng nhập; tài khoản cũ tiếp tục dùng tham số yếu trong thời gian dài.
Ứng dụng lưu pepper chung trong cùng database với password hash; một lần lộ database đồng thời làm lộ cả yếu tố bí mật bổ sung.
Chính sách mật khẩu bắt buộc đổi mỗi 30 ngày khiến người dùng chỉ thay số cuối hoặc ghi mật khẩu ra giấy; đội bảo mật muốn chuyển sang kiểm tra mật khẩu bị lộ và hỗ trợ mật khẩu dài.
Form đăng nhập phân biệt rõ 'email không tồn tại' và 'mật khẩu sai'; attacker dùng phản hồi để dò danh sách tài khoản hợp lệ.
Endpoint quên mật khẩu trả thời gian phản hồi khác nhau đáng kể giữa email tồn tại và không tồn tại; attacker có thể suy đoán tài khoản qua timing dù thông báo hiển thị giống nhau.
Một tài khoản bị credential stuffing sau khi mật khẩu bị tái sử dụng từ vụ rò rỉ dịch vụ khác; hệ thống chỉ giới hạn theo IP nên bot phân tán vẫn thử được nhiều mật khẩu.
Rate limit đăng nhập khóa cứng tài khoản sau ba lần sai; attacker cố ý nhập sai cho nhiều người để gây denial of service và buộc người dùng hợp lệ không đăng nhập được.
Đăng nhập dùng CAPTCHA sau một số lần thất bại nhưng bot farm giải được thử thách và tiếp tục credential stuffing; nhóm cần kết hợp tín hiệu rủi ro, giới hạn tốc độ và phát hiện bất thường.
Ứng dụng cho phép username không phân biệt hoa thường nhưng tạo tài khoản và tra cứu bằng quy tắc Unicode khác nhau; các biến thể tên đăng nhập có thể ánh xạ sai danh tính.
Một người dùng đổi email đăng nhập nhưng hệ thống chưa yêu cầu xác minh địa chỉ mới; attacker chiếm phiên đang mở có thể thay email và chiếm quyền khôi phục tài khoản.
Người dùng đăng nhập thành công qua email chưa xác minh; ứng dụng tự động cấp quyền nhận thông báo và đặt lại mật khẩu qua địa chỉ chưa được chứng minh quyền kiểm soát.
Nhóm thêm MFA bằng SMS OTP cho tài khoản quản trị nhưng không đánh giá nguy cơ SIM swap và chuyển hướng số điện thoại; attacker chiếm số có thể vượt lớp xác minh thứ hai.
OTP qua SMS được gửi tới số điện thoại đã thay đổi gần đây; hệ thống không áp dụng thời gian chờ hoặc xác minh bổ sung cho thay đổi yếu tố khôi phục.
Ứng dụng dùng TOTP nhưng chấp nhận cửa sổ thời gian quá rộng để giảm lỗi đồng hồ; mã đã hết hiệu lực có thể được chấp nhận lâu hơn dự kiến.
Một mã TOTP hợp lệ có thể được gửi nhiều lần trong cùng time step; hệ thống không ghi nhận mã đã dùng nên cùng OTP có thể bị replay trong cửa sổ hiệu lực.
Server và thiết bị lệch đồng hồ khiến TOTP liên tục thất bại; nhóm tăng cửa sổ chấp nhận thay vì xử lý đồng bộ thời gian và giới hạn sai lệch hợp lý.
Người dùng đăng ký TOTP và secret seed được hiển thị lại trong trang cài đặt sau khi hoàn tất; kẻ có quyền đọc session có thể lấy seed để tạo OTP lâu dài.
Ứng dụng lưu recovery codes dạng plaintext và không đánh dấu mã đã dùng; một mã khôi phục bị lộ có thể được sử dụng nhiều lần để vượt MFA.
Người dùng mất điện thoại và yêu cầu hỗ trợ tắt MFA qua cuộc gọi; quy trình help desk chỉ hỏi ngày sinh công khai nên attacker có thể social-engineer để chiếm tài khoản.
MFA push gửi liên tục khi attacker đã biết mật khẩu; người dùng mệt mỏi và bấm Approve một thông báo không mong muốn, tạo điều kiện cho MFA fatigue.
Push MFA chỉ hiển thị nút Approve/Reject mà không có number matching hoặc thông tin ngữ cảnh; người dùng khó phân biệt yêu cầu đăng nhập thật với yêu cầu do attacker khởi tạo.
Ứng dụng hỗ trợ WebAuthn nhưng không kiểm tra origin của client data; assertion từ một origin khác có thể bị chấp nhận nếu chỉ kiểm tra chữ ký.
Server WebAuthn không ràng buộc challenge với phiên đăng nhập đang chờ; assertion hợp lệ từ một phiên khác có thể bị ghép vào luồng xác thực hiện tại.
RP ID được cấu hình quá rộng so với domain ứng dụng; credential có thể được dùng trên nhiều subdomain hơn phạm vi tin cậy dự kiến.
Passkey đồng bộ qua cloud account giúp người dùng khôi phục trên thiết bị mới, nhưng nhóm nhầm cơ chế đồng bộ này với credential phần cứng không thể export và thiết kế chính sách assurance sai.
Ứng dụng chỉ cho đăng nhập bằng passkey trên một thiết bị nhưng không có quy trình thêm thiết bị thứ hai hoặc khôi phục; người dùng mất thiết bị bị khóa khỏi tài khoản.
WebAuthn registration không kiểm tra attestation theo chính sách đã công bố; hệ thống ghi nhận authenticator ngoài nhóm thiết bị được phép dù nghiệp vụ yêu cầu ràng buộc thiết bị.
Authenticator counter của một passkey đồng bộ không tăng đơn điệu như thiết bị đơn lẻ; hệ thống khóa tài khoản ngay khi thấy counter lặp mà không xem xét mô hình multi-device.
Ứng dụng dùng passkey nhưng vẫn cho phép fallback mật khẩu yếu và SMS OTP mà không áp dụng step-up; attacker bỏ qua phương thức mạnh bằng đường dự phòng yếu hơn.
Một hệ thống yêu cầu mTLS cho API nội bộ nhưng chỉ kiểm tra certificate chain; mọi client có chứng chỉ do CA chung cấp đều được gán cùng một danh tính và quyền.
Certificate client được xác minh thành công nhưng mapping Subject/SAN sang account dựa trên common name không duy nhất; hai certificate khác nhau có thể bị ánh xạ vào cùng principal.
Client certificate hết hạn nhưng proxy giữ trạng thái xác thực cũ trong connection pool; request mới trên kết nối tái sử dụng tiếp tục được xử lý sau khi chứng chỉ hết hạn.
Certificate của nhân viên bị thu hồi nhưng server không kiểm tra CRL hoặc OCSP theo chính sách; certificate đã revoke vẫn được chấp nhận trong thời gian dài.
Ứng dụng dùng chứng chỉ TLS của server để suy ra người dùng đã xác thực; chứng chỉ chỉ chứng minh danh tính endpoint và không thay thế xác thực user.
OIDC client xác minh chữ ký ID token nhưng không kiểm tra issuer và audience; token do issuer khác phát hành hoặc dành cho client khác có thể bị chấp nhận.
Ứng dụng OIDC không kiểm tra nonce trong ID token; phản hồi xác thực cũ có thể bị ghép vào phiên đăng nhập mới trong một số luồng.
Authorization Code flow không dùng PKCE cho public client; mã authorization bị chặn có thể bị đổi lấy token bởi bên không sở hữu phiên khởi tạo.
OIDC callback không kiểm tra state gắn với phiên trình duyệt; attacker có thể khởi tạo login response của họ trong browser nạn nhân và gây login CSRF hoặc account confusion.
Ứng dụng chấp nhận ID token như access token để gọi API; audience và mục đích token không đúng khiến ranh giới giữa đăng nhập và quyền truy cập tài nguyên bị xóa nhòa.
API xác minh JWT bằng cách tin thuật toán nêu trong header mà không có allowlist; cấu hình verifier sai có thể dẫn tới chấp nhận chữ ký không an toàn.
JWT access token chỉ kiểm tra chữ ký mà không kiểm tra exp, nbf và clock skew; token đã hết hạn hoặc chưa có hiệu lực vẫn được chấp nhận.
Refresh token sống lâu được lưu trong localStorage của ứng dụng web; XSS có thể lấy token và duy trì quyền truy cập sau khi người dùng đóng tab.
Ứng dụng triển khai refresh token rotation nhưng không phát hiện reuse token cũ; attacker dùng bản sao refresh token đã bị thay thế để tiếp tục lấy access token mới.
Logout chỉ xóa cookie ở trình duyệt nhưng access token bearer còn hiệu lực tới khi hết hạn; thiết bị bị mất vẫn gọi API được trong thời gian còn lại.
Session ID được tạo trước khi đăng nhập và giữ nguyên sau xác thực; attacker có thể cố định session identifier rồi chờ nạn nhân đăng nhập để chiếm phiên.
Cookie phiên thiếu Secure và HttpOnly; cookie có thể bị gửi qua kết nối không mã hóa hoặc bị JavaScript đọc khi có XSS.
Cookie SameSite=None được dùng cho đăng nhập liên miền nhưng không bật Secure; trình duyệt từ chối cookie hoặc hành vi khác nhau giữa môi trường.
Ứng dụng chỉ kiểm tra CSRF token ở form đăng nhập nhưng không kiểm tra ở thao tác đổi email hoặc bật MFA; attacker có thể ép trình duyệt đã xác thực thay đổi yếu tố khôi phục.
Session không bị rotate sau khi người dùng nâng quyền từ user lên admin; session cũ có thể tiếp tục tồn tại qua ranh giới đặc quyền.
Người dùng chọn 'remember me' và server cấp cookie có thời hạn nhiều năm không gắn với trạng thái thu hồi thiết bị; thiết bị cũ vẫn giữ quyền truy cập sau khi đổi mật khẩu.
Quy trình password reset dùng token ngẫu nhiên nhưng không ràng buộc với user, thời hạn và mục đích; token có thể bị dùng lại hoặc áp cho tài khoản khác.
Reset link được gửi qua email nhưng token vẫn còn hiệu lực sau khi đổi mật khẩu thành công; người nhặt được link cũ có thể đặt lại mật khẩu lần nữa.
Password reset endpoint cho phép nhiều yêu cầu liên tiếp và gửi email không giới hạn; attacker có thể spam hộp thư nạn nhân và gây chi phí gửi thư.
Help desk cho phép đổi email hoặc tắt MFA chỉ dựa trên thông tin cá nhân dễ tìm; quy trình recovery trở thành đường vòng yếu hơn đăng nhập chính.
Liên kết tài khoản social login bằng cách chỉ so sánh email mà không xác minh email_verified và issuer; attacker có thể liên kết nhầm danh tính vào tài khoản hiện hữu.
JIT provisioning từ SAML assertion tự động cấp quyền admin theo group name do IdP gửi; mapping group không được allowlist nên thay đổi phía IdP mở rộng quyền ngoài dự kiến.
SAML service provider kiểm tra chữ ký assertion nhưng không kiểm tra audience, recipient và InResponseTo; assertion hợp lệ dành cho ứng dụng hoặc phiên khác có thể bị replay.
Ứng dụng chấp nhận assertion SAML chưa kiểm tra NotBefore/NotOnOrAfter; assertion cũ tiếp tục được sử dụng sau thời gian hiệu lực.
Đăng nhập liên kết OIDC và SAML không có quy tắc account linking rõ ràng; cùng email từ hai issuer khác nhau bị gộp thành một account mà không xác minh quyền sở hữu.
Step-up authentication chỉ được yêu cầu lúc đăng nhập, không yêu cầu lại trước thao tác chuyển tiền hoặc đổi yếu tố MFA; session bị chiếm vẫn có thể thực hiện hành động rủi ro cao.
Hệ thống chỉ ghi nhận đăng nhập thành công mà không lưu thiết bị, IP, phương thức MFA và kết quả rủi ro; đội bảo mật khó phát hiện đăng nhập bất thường hoặc điều tra account takeover.
