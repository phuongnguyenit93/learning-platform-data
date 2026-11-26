Bạn sẽ phân biệt định danh, xác thực danh tính và phân quyền trong một hệ thống ứng dụng như thế nào?
Bạn sẽ mô hình hóa vòng đời xác thực từ đăng ký, chứng minh quyền sở hữu credential, đăng nhập đến thu hồi ra sao?
Bạn sẽ xác định trust boundary giữa người dùng, thiết bị, ứng dụng client, identity provider và service đích như thế nào?
Bạn sẽ phân biệt identifier, authenticator, credential và yếu tố xác thực trong một luồng đăng nhập ra sao?
Bạn sẽ giải thích ba nhóm yếu tố biết, sở hữu và sinh trắc học cùng giới hạn khi kết hợp chúng như thế nào?
Bạn sẽ đánh giá độ mạnh của một phương thức xác thực theo khả năng chống giả mạo, phishing, replay và chiếm đoạt credential ra sao?
Bạn sẽ lựa chọn xác thực phù hợp cho người dùng tương tác, workload máy-với-máy và thiết bị không có giao diện như thế nào?
Bạn sẽ thiết kế chính sách xác thực nhất quán cho web, mobile, API và ứng dụng nội bộ mà vẫn phù hợp từng môi trường ra sao?
Bạn sẽ phân biệt xác minh danh tính ban đầu với xác thực lại trong các phiên sử dụng kéo dài như thế nào?
Bạn sẽ xác định khi nào một hành động nhạy cảm cần step-up authentication thay vì chỉ tin phiên đăng nhập hiện tại ra sao?
Bạn sẽ lựa chọn yêu cầu độ mạnh xác thực theo mức rủi ro của tài khoản, dữ liệu và thao tác nghiệp vụ như thế nào?
Bạn sẽ thiết kế quy trình đăng ký tài khoản để hạn chế tạo danh tính giả và chiếm đoạt tài khoản ngay từ đầu ra sao?
Bạn sẽ phân biệt account proofing với authentication và xác định mức độ kiểm tra danh tính phù hợp theo dịch vụ như thế nào?
Bạn sẽ thiết kế quy trình thay đổi email hoặc số điện thoại đăng nhập để ngăn kẻ tấn công chiếm quyền liên kết tài khoản ra sao?
Bạn sẽ giải thích password hashing khác với encryption và vì sao mật khẩu không nên được lưu dạng có thể giải mã như thế nào?
Bạn sẽ lựa chọn Argon2id, scrypt, bcrypt hoặc PBKDF2 theo môi trường triển khai và yêu cầu tương thích ra sao?
Bạn sẽ xác định cost parameters của password hashing dựa trên tài nguyên máy chủ và mục tiêu chống dò mật khẩu như thế nào?
Bạn sẽ giải thích vai trò của salt riêng cho từng mật khẩu và pepper được quản lý tách biệt ra sao?
Bạn sẽ thiết kế nâng cấp password hash theo kiểu rehash-on-login khi thuật toán hoặc cost parameters thay đổi như thế nào?
Bạn sẽ xử lý mật khẩu yếu, mật khẩu phổ biến và mật khẩu đã xuất hiện trong dữ liệu rò rỉ bằng chính sách nào?
Bạn sẽ cân bằng password length, passphrase, password manager và yêu cầu đổi mật khẩu định kỳ theo rủi ro ra sao?
Bạn sẽ ngăn password enumeration khi phản hồi đăng nhập hoặc khôi phục tài khoản có thể tiết lộ email tồn tại như thế nào?
Bạn sẽ lựa chọn thông báo lỗi đăng nhập và thời gian phản hồi để hạn chế dò tìm tài khoản mà vẫn hỗ trợ người dùng ra sao?
Bạn sẽ thiết kế rate limiting và progressive delay chống brute force, password spraying và credential stuffing như thế nào?
Bạn sẽ phân biệt brute force, password spraying và credential stuffing qua mẫu lưu lượng và nguồn credential ra sao?
Bạn sẽ đánh giá rủi ro khóa tài khoản cứng sau nhiều lần đăng nhập sai và lựa chọn biện pháp chống denial of service phù hợp như thế nào?
Bạn sẽ xác định khi nào nên yêu cầu CAPTCHA, step-up hoặc xác minh bổ sung khi phát hiện hành vi đăng nhập bất thường ra sao?
Bạn sẽ thiết kế multi-factor authentication và giải thích vì sao hai yếu tố thuộc cùng một nhóm không tạo thành MFA đúng nghĩa như thế nào?
Bạn sẽ so sánh TOTP, HOTP, push notification, SMS OTP và email OTP về khả năng chống phishing và chiếm đoạt như thế nào?
Bạn sẽ giải thích cách TOTP dùng secret và thời gian để tạo mã dùng một lần, cùng cách xử lý lệch đồng hồ ra sao?
Bạn sẽ bảo vệ secret TOTP khi cấp phát, hiển thị QR code, lưu trữ và thay thế thiết bị xác thực như thế nào?
Bạn sẽ xác định cách ngăn một OTP bị sử dụng lại hoặc bị thử nhiều lần trong cửa sổ thời gian hợp lệ ra sao?
Bạn sẽ thiết kế push MFA có number matching hoặc thông tin ngữ cảnh để giảm MFA fatigue như thế nào?
Bạn sẽ đánh giá rủi ro SMS OTP trước SIM swap, chuyển tiếp tin nhắn và chiếm quyền số điện thoại ra sao?
Bạn sẽ thiết kế recovery codes dùng một lần và bảo đảm mã dự phòng không trở thành điểm yếu của MFA như thế nào?
Bạn sẽ xác định quy trình thay đổi hoặc mất thiết bị MFA mà không cho phép kẻ tấn công dùng hỗ trợ khách hàng để vượt xác thực ra sao?
Bạn sẽ phân biệt passkey, passwordless authentication và MFA trong các tình huống sử dụng thực tế như thế nào?
Bạn sẽ mô tả WebAuthn và FIDO2 dùng cặp khóa công khai-riêng để xác thực với relying party như thế nào?
Bạn sẽ giải thích vai trò của challenge, origin, RP ID và chữ ký trong việc chống phishing của WebAuthn ra sao?
Bạn sẽ xác định cách server kiểm tra challenge chưa dùng, origin đúng và RP ID hash hợp lệ khi xác minh assertion như thế nào?
Bạn sẽ phân biệt user presence với user verification trong một lần xác thực passkey ra sao?
Bạn sẽ so sánh passkey đồng bộ qua hệ sinh thái thiết bị với credential gắn thiết bị về khả năng phục hồi và rủi ro ra sao?
Bạn sẽ thiết kế quy trình đăng ký nhiều passkey và quản lý danh sách authenticator cho một tài khoản như thế nào?
Bạn sẽ xử lý mất thiết bị chứa passkey và thu hồi credential không còn kiểm soát được ra sao?
Bạn sẽ đánh giá vai trò của attestation trong WebAuthn và xác định khi nào ứng dụng thực sự cần kiểm tra loại authenticator như thế nào?
Bạn sẽ phân biệt xác thực dựa trên certificate với xác thực bằng password hoặc shared secret trong môi trường doanh nghiệp ra sao?
Bạn sẽ mô tả PKI, certificate chain, trust anchor và quá trình xác minh chứng chỉ client như thế nào?
Bạn sẽ thiết kế mTLS để xác thực workload giữa các service và quản lý certificate lifecycle ra sao?
Bạn sẽ kiểm tra subject, SAN, EKU, issuer và thời hạn chứng chỉ khi xác thực client certificate như thế nào?
Bạn sẽ phân biệt thu hồi chứng chỉ bằng CRL và OCSP cùng các giới hạn khi trạng thái thu hồi không truy cập được ra sao?
Bạn sẽ tổ chức cấp mới, gia hạn và xoay vòng certificate tự động để tránh gián đoạn dịch vụ như thế nào?
Bạn sẽ giải thích session cookie duy trì trạng thái xác thực sau đăng nhập và các thuộc tính Secure, HttpOnly, SameSite bảo vệ nó ra sao?
Bạn sẽ phân biệt session ID với access token và lựa chọn mô hình stateful hoặc stateless theo yêu cầu nào?
Bạn sẽ ngăn session fixation bằng cách thay session identifier sau khi xác thực hoặc nâng quyền như thế nào?
Bạn sẽ thiết kế idle timeout và absolute timeout để giới hạn thời gian sử dụng phiên bị bỏ quên ra sao?
Bạn sẽ xử lý logout, revoke session và đăng xuất toàn bộ thiết bị khi credential bị xâm phạm như thế nào?
Bạn sẽ giải thích CSRF có thể khai thác cookie xác thực được trình duyệt tự động gửi và cách phòng vệ phù hợp ra sao?
Bạn sẽ bảo vệ token trong ứng dụng web và mobile để giảm rủi ro XSS, malware hoặc backup không an toàn như thế nào?
Bạn sẽ phân biệt access token và refresh token về quyền hạn, thời hạn và nơi lưu trữ như thế nào?
Bạn sẽ lựa chọn opaque token với introspection hoặc JWT tự xác minh theo yêu cầu thu hồi và độ trễ ra sao?
Bạn sẽ xác minh JWT bằng cách kiểm tra chữ ký, thuật toán, issuer, audience, expiration và not-before như thế nào?
Bạn sẽ thiết kế refresh token rotation và phát hiện reuse để nhận biết token family có thể đã bị đánh cắp ra sao?
Bạn sẽ giảm nguy cơ token replay bằng nonce, DPoP hoặc mTLS-bound access token theo bối cảnh nào?
Bạn sẽ xác định rủi ro khi token xuất hiện trong URL, log, crash report hoặc referrer và cách loại bỏ chúng như thế nào?
Bạn sẽ phân biệt OpenID Connect với OAuth 2.0 và giải thích ID token không phải access token như thế nào?
Bạn sẽ mô tả Authorization Code Flow với PKCE và vai trò của state, nonce trong bảo vệ luồng đăng nhập ra sao?
Bạn sẽ thiết kế Single Sign-On qua OIDC hoặc SAML giữa identity provider và nhiều ứng dụng relying party như thế nào?
Bạn sẽ liên kết tài khoản cục bộ với danh tính liên kết dựa trên issuer và subject ổn định để tránh account takeover ra sao?
Bạn sẽ xử lý trường hợp hai identity provider trả cùng email nhưng không chứng minh cùng một chủ thể như thế nào?
Bạn sẽ thiết kế Just-in-Time provisioning và đồng bộ vòng đời tài khoản bằng SCIM mà không cấp quyền quá mức ra sao?
Bạn sẽ phân biệt đăng nhập bằng IdP với việc ứng dụng tự quản lý mật khẩu và session về trách nhiệm bảo mật như thế nào?
Bạn sẽ xây dựng quy trình khôi phục tài khoản khi người dùng mất password, email, điện thoại và toàn bộ yếu tố MFA ra sao?
Bạn sẽ thiết kế password reset link với token ngẫu nhiên, thời hạn ngắn, one-time use và ràng buộc đúng tài khoản như thế nào?
Bạn sẽ ngăn reset token bị lộ qua referrer, analytics, browser history hoặc log của reverse proxy ra sao?
Bạn sẽ đánh giá email recovery và SMS recovery có thể làm suy yếu MFA mạnh đến mức nào khi chính kênh khôi phục bị chiếm quyền?
Bạn sẽ thiết kế quy trình hỗ trợ viên khôi phục tài khoản để chống social engineering và lạm dụng quyền nội bộ ra sao?
Bạn sẽ yêu cầu xác minh lại hoặc thông báo cho các kênh liên hệ cũ khi thay đổi yếu tố khôi phục như thế nào?
Bạn sẽ quản lý recovery code, backup authenticator và trusted device để người dùng phục hồi nhưng kẻ tấn công khó lợi dụng ra sao?
Bạn sẽ thiết kế quy trình xử lý tài khoản nghi bị chiếm gồm revoke session, reset credential, kiểm tra thiết bị và audit activity như thế nào?
Bạn sẽ phân biệt phishing, adversary-in-the-middle và replay attack trong các luồng xác thực phổ biến ra sao?
Bạn sẽ giải thích vì sao passkey có khả năng chống phishing theo origin trong khi OTP có thể bị chuyển tiếp như thế nào?
Bạn sẽ phát hiện MFA fatigue, push bombing và hành vi chấp thuận đăng nhập bất thường bằng tín hiệu nào?
Bạn sẽ đánh giá nguy cơ SIM swap, malware trên thiết bị và đánh cắp cookie session trong threat model xác thực ra sao?
Bạn sẽ thiết kế risk-based authentication dựa trên thiết bị, vị trí, IP, hành vi và lịch sử đăng nhập mà không phụ thuộc một tín hiệu đơn lẻ như thế nào?
Bạn sẽ lựa chọn step-up authentication khi phát hiện thay đổi thiết bị, địa chỉ thanh toán hoặc thao tác chuyển tiền ra sao?
Bạn sẽ thiết kế workload identity cho service-to-service để tránh chia sẻ password hoặc secret dài hạn giữa các ứng dụng như thế nào?
Bạn sẽ kiểm soát vòng đời credential, token, session và certificate khi nhân sự nghỉ việc hoặc workload bị xóa ra sao?
Bạn sẽ kiểm thử authentication bằng các kịch bản brute force, replay, session fixation, token theft, recovery abuse và phishing simulation như thế nào?
Bạn sẽ xây dựng audit log và cảnh báo cho đăng nhập thất bại, MFA reset, credential change, session revoke và đăng nhập rủi ro ra sao?
Bạn sẽ thiết kế chương trình xác thực đầu cuối cho hệ thống đa nền tảng gồm password, MFA, passkey, certificate, token, session, federation và account recovery như thế nào?
