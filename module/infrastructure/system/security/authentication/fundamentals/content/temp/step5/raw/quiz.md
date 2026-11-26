1. Cách lưu mật khẩu nào phù hợp nhất để giảm thiệt hại khi cơ sở dữ liệu xác thực bị lộ?
A. Mã hóa mật khẩu bằng AES với một khóa chung đặt trong cùng cơ sở dữ liệu.
B. Dùng Argon2id với salt ngẫu nhiên riêng và tham số chi phí phù hợp.
C. Tính SHA-256 nhiều lần trên mật khẩu rồi lưu kết quả cuối cùng.
D. Dùng một salt cố định cho toàn bộ tài khoản và hash bằng SHA-256.
Đáp án đúng: B

2. Pepper bổ sung cho password hashing nên được quản lý như thế nào?
A. Lưu riêng khỏi password database trong secret manager hoặc HSM.
B. Nối pepper vào cột salt để mọi dịch vụ xác thực đọc cùng một bản ghi.
C. Công khai pepper trong cấu hình ứng dụng để đơn giản hóa triển khai.
D. Tạo pepper mới mỗi lần đăng nhập rồi ghi đè hash của người dùng.
Đáp án đúng: A

3. Một tài khoản dùng hash cũ với work factor thấp đăng nhập thành công. Ứng dụng nên làm gì?
A. Giữ nguyên hash cho tới khi người dùng tự đổi mật khẩu.
B. Khóa tài khoản để buộc quản trị viên tạo lại credential.
C. Rehash mật khẩu đã xác minh theo tham số hiện hành.
D. Chuyển hash cũ sang mã hóa đối xứng để tăng khả năng phục hồi.
Đáp án đúng: C

4. Cách nào giảm nguy cơ attacker dò tên tài khoản hợp lệ qua phản hồi đăng nhập?
A. Trả thông báo khác nhau nhưng giới hạn số lần thử theo IP.
B. Chỉ ẩn tên tài khoản trong giao diện, còn API trả mã lỗi chi tiết.
C. Dùng CAPTCHA sau đăng nhập thành công để che phản hồi lỗi.
D. Dùng phản hồi chung và giảm khác biệt thời gian xử lý giữa các trường hợp.
Đáp án đúng: D

5. Một đợt credential stuffing đến từ nhiều IP và thiết bị khác nhau. Biện pháp nào phù hợp nhất?
A. Khóa vĩnh viễn mọi tài khoản có ít nhất một lần đăng nhập sai.
B. Kết hợp tín hiệu tài khoản, thiết bị, IP và rate limit.
C. Chỉ chặn IP gửi nhiều request trong một phút.
D. Tăng độ dài session để người dùng không phải đăng nhập lại.
Đáp án đúng: B

6. Vì sao khóa tài khoản cứng sau vài lần đăng nhập sai có thể tạo thêm rủi ro?
A. Khóa tài khoản khiến password hash dễ bị đảo ngược hơn.
B. Cơ chế khóa làm access token tự động mất chữ ký.
C. Khóa tài khoản ngăn hệ thống ghi nhận sự kiện đăng nhập.
D. Kẻ tấn công có thể làm người dùng hợp lệ bị từ chối dịch vụ.
Đáp án đúng: D

7. Làm thế nào để ngăn một mã TOTP hợp lệ bị chấp nhận nhiều lần trong cùng cửa sổ thời gian?
A. Tăng số chữ số của mã nhưng cho phép dùng lại trong cùng time step.
B. Chỉ xác minh mã ở phía trình duyệt trước khi gửi lên máy chủ.
C. Ghi nhận time step đã chấp nhận cho credential và từ chối replay.
D. Cho phép nhiều lần dùng mã nếu địa chỉ IP của người dùng không đổi.
Đáp án đúng: C

8. Người dùng liên tục gặp lỗi TOTP do đồng hồ thiết bị lệch. Cách xử lý nào phù hợp?
A. Mở rộng cửa sổ chấp nhận tới nhiều giờ để mọi mã đều hợp lệ.
B. Tắt kiểm tra thời gian và chỉ xác minh số bí mật của tài khoản.
C. Tạo lại password hash mỗi khi TOTP không khớp.
D. Đồng bộ thời gian máy chủ và cho phép sai lệch nhỏ có giới hạn.
Đáp án đúng: D

9. Rủi ro nổi bật của SMS OTP đối với tài khoản giá trị cao là gì?
A. SIM swap có thể chuyển OTP tới kẻ chiếm số điện thoại.
B. Mã SMS luôn được mã hóa đầu cuối bằng khóa riêng của người nhận.
C. SMS OTP không thể bị phishing vì mã chỉ dùng trong một lần đăng nhập.
D. Mã SMS không phụ thuộc vào nhà mạng hoặc thiết bị nhận.
Đáp án đúng: A

10. Biện pháp nào giúp giảm MFA fatigue khi attacker liên tục gửi push request?
A. Tự động phê duyệt yêu cầu đầu tiên từ thiết bị từng đăng nhập.
B. Kéo dài thời gian chờ nhưng không giới hạn số push request.
C. Chỉ gửi push khi người dùng nhập mật khẩu sai.
D. Dùng number matching và hiển thị ngữ cảnh đăng nhập cần xác nhận.
Đáp án đúng: D

11. Vì sao WebAuthn/passkey có khả năng chống phishing tốt hơn mật khẩu dùng chung giữa các website?
A. Credential gắn với RP ID/origin, không ký challenge cho domain giả.
B. Mọi passkey đều được lưu trên máy chủ website dưới dạng mật khẩu có thể đọc.
C. Người dùng phải nhập OTP thủ công sau mỗi lần ký challenge.
D. Passkey loại bỏ nhu cầu kiểm tra danh tính máy chủ khi kết nối.
Đáp án đúng: A

12. Một WebAuthn assertion được gửi tới server. Điều gì cần được xác minh để chống replay?
A. Chỉ kiểm tra chữ ký của authenticator và bỏ qua trạng thái phiên.
B. Chỉ so sánh username trong assertion với username trên giao diện.
C. Kiểm tra challenge dùng một lần, gắn với phiên và đúng origin/RP ID.
D. Chấp nhận challenge cũ nếu chữ ký vẫn hợp lệ và thiết bị quen thuộc.
Đáp án đúng: C

13. Phát biểu nào chính xác về passkey được đồng bộ qua hệ sinh thái thiết bị?
A. Passkey đồng bộ vẫn chống phishing, nhưng không đồng nghĩa khóa phần cứng.
B. Passkey đồng bộ luôn kém an toàn hơn mật khẩu vì private key được công khai.
C. Mọi passkey đồng bộ đều chứng minh thiết bị có phần cứng chống giả mạo.
D. Đồng bộ passkey khiến relying party không cần kiểm tra origin.
Đáp án đúng: A

14. Recovery code cho MFA nên được quản lý như thế nào?
A. Hiển thị một lần, lưu an toàn và đánh dấu từng mã đã dùng để không thể replay.
B. Lưu plaintext trong hồ sơ người dùng để help desk có thể đọc lại.
C. Dùng chung một mã cho mọi thiết bị để đơn giản hóa khôi phục.
D. Cho phép mã đã dùng hoạt động lại sau khi người dùng đổi mật khẩu.
Đáp án đúng: A

15. Người dùng mất thiết bị MFA và gọi help desk yêu cầu tắt yếu tố xác thực. Quy trình nào an toàn hơn?
A. Tắt MFA ngay khi người gọi cung cấp email đăng nhập.
B. Xác minh danh tính bằng quy trình recovery độc lập, mạnh và có audit.
C. Chỉ hỏi ngày sinh và tên quản lý trực tiếp của người dùng.
D. Gửi mã khôi phục tới địa chỉ email mới do người gọi cung cấp.
Đáp án đúng: B

16. Khi dùng mTLS để xác thực client, cách ánh xạ chứng chỉ sang principal nào phù hợp?
A. Xác minh chain rồi ánh xạ SAN/subject duy nhất theo policy.
B. Chấp nhận mọi chứng chỉ do CA công khai cấp như cùng một tài khoản.
C. Dùng common name không kiểm tra tính duy nhất làm user ID.
D. Bỏ kiểm tra chain nếu chứng chỉ còn trong thời hạn hiệu lực.
Đáp án đúng: A

17. Một chứng chỉ client đã bị thu hồi nhưng vẫn được chấp nhận. Kiểm soát nào cần xem xét?
A. Cơ chế kiểm tra trạng thái thu hồi và độ mới của CRL/OCSP response.
B. Tăng thời hạn chứng chỉ để tránh lỗi kết nối từ thiết bị cũ.
C. Chỉ kiểm tra hostname của server trước khi nhận chứng chỉ client.
D. Lưu chứng chỉ đã thu hồi vào trust store để tăng tốc xác minh.
Đáp án đúng: A

18. Khi xác minh ID token OIDC, nhóm claim nào cần được kiểm tra?
A. Chỉ kiểm tra email và preferred_username do giao diện hiển thị.
B. Chữ ký, issuer, audience, nonce và exp theo ngữ cảnh đăng nhập.
C. Chỉ kiểm tra thời điểm token được tạo và thuật toán nêu trong header.
D. Chỉ kiểm tra subject vì subject luôn duy nhất trên mọi issuer.
Đáp án đúng: B

19. Tham số state trong OAuth/OIDC chủ yếu giúp bảo vệ luồng nào?
A. Ngăn resource server đọc claim trong access token.
B. Mã hóa authorization code bằng khóa riêng của trình duyệt.
C. Xác minh chứng chỉ TLS của identity provider.
D. Liên kết callback với phiên khởi tạo để giảm login CSRF.
Đáp án đúng: D

20. Public client triển khai Authorization Code Flow nên dùng biện pháp nào?
A. Lưu client secret trong mã ứng dụng để đổi authorization code.
B. Dùng Implicit Flow để bỏ qua bước trao đổi code.
C. Dùng PKCE để ràng buộc việc đổi code với client khởi tạo.
D. Cho phép redirect URI wildcard để tránh lỗi cấu hình.
Đáp án đúng: C

21. Khác biệt quan trọng giữa ID token và access token là gì?
A. ID token dùng gọi mọi API; access token chỉ hiển thị thông tin đăng nhập.
B. ID token xác thực người dùng với client; access token cấp quyền cho resource.
C. Hai token có cùng mục đích và có thể thay thế nhau trong mọi request.
D. Access token luôn chứa mật khẩu người dùng để resource server xác minh.
Đáp án đúng: B

22. Một API xác minh JWT an toàn nên xử lý thuật toán trong header như thế nào?
A. Chấp nhận mọi thuật toán token tự khai báo nếu JSON parse thành công.
B. Dùng allowlist thuật toán và ràng buộc key phù hợp với issuer.
C. Bỏ kiểm tra chữ ký khi token có claim audience đúng.
D. Chỉ giải mã payload Base64 rồi tin các claim bên trong.
Đáp án đúng: B

23. Ngoài chữ ký JWT, API cần kiểm tra điều kiện thời gian nào?
A. exp, nbf và clock skew nhỏ theo chính sách.
B. Chỉ iat vì token được phát hành thì không thể hết hạn.
C. Chỉ thời gian hệ điều hành khởi động gần nhất.
D. Chỉ thời gian tạo tài khoản của subject trong token.
Đáp án đúng: A

24. Refresh token rotation nên phản ứng thế nào khi phát hiện token cũ đã bị dùng lại?
A. Thu hồi token family hoặc phiên và yêu cầu xác thực lại.
B. Cấp thêm refresh token mới nhưng giữ nguyên token cũ.
C. Kéo dài thời hạn token cũ để tránh làm gián đoạn người dùng.
D. Chỉ ghi log reuse rồi tiếp tục cấp access token bình thường.
Đáp án đúng: A

25. Người dùng logout nhưng access token bearer còn hạn. Cách xử lý nào phản ánh đúng giới hạn của logout?
A. Xóa cookie trình duyệt sẽ tự động vô hiệu hóa mọi bản sao access token.
B. Logout luôn làm chữ ký JWT cũ không còn hợp lệ ở mọi API.
C. Cần cơ chế thu hồi/introspection phù hợp hoặc access token sống ngắn.
D. Chỉ cần xóa ID token vì access token phụ thuộc vào nó.
Đáp án đúng: C

26. Biện pháp chính để ngăn session fixation sau khi đăng nhập thành công là gì?
A. Giữ nguyên session ID để không làm mất trạng thái giỏ hàng.
B. Tạo session ID mới sau xác thực và sau thay đổi đặc quyền.
C. Đưa session ID vào URL để trình duyệt tự cập nhật.
D. Tăng thời hạn session cũ thay vì thay định danh phiên.
Đáp án đúng: B

27. Bộ thuộc tính cookie nào thường phù hợp để bảo vệ session cookie?
A. Chỉ đặt SameSite=None để trình duyệt luôn gửi cookie.
B. Domain wildcard, Path rộng và không giới hạn thời hạn.
C. Secure, HttpOnly và SameSite phù hợp với luồng liên miền.
D. HttpOnly tắt để mã ứng dụng có thể tự xác minh phiên.
Đáp án đúng: C

28. Khi cookie cần dùng trong ngữ cảnh cross-site với SameSite=None, điều kiện nào cần có?
A. Bỏ Secure để trình duyệt có thể gửi cookie qua HTTP.
B. Đặt HttpOnly=false để cho phép script quản lý cookie.
C. Bật Domain wildcard để cookie tự chia sẻ giữa mọi site.
D. Đặt Secure để cookie chỉ được gửi qua kết nối bảo mật.
Đáp án đúng: D

29. Vì sao thao tác đổi email hoặc bật MFA vẫn cần chống CSRF?
A. Vì access token luôn hết hạn trước khi người dùng gửi form.
B. Request đổi trạng thái có thể bị browser gửi ngoài ý muốn.
C. Vì CSRF chỉ ảnh hưởng tới người dùng chưa đăng nhập.
D. Vì cookie HttpOnly tự động kiểm tra nguồn gốc mọi request.
Đáp án đúng: B

30. Password reset token nên có đặc tính nào?
A. Dùng chung một token cho mọi lần yêu cầu trong ngày.
B. Là username được mã hóa Base64 để người dùng dễ nhớ.
C. Ngẫu nhiên đủ mạnh, ràng buộc mục đích/tài khoản, hết hạn và dùng một lần.
D. Không hết hạn để người dùng có thể khôi phục bất cứ lúc nào.
Đáp án đúng: C

31. Khi liên kết tài khoản OIDC bên ngoài với tài khoản hiện có, định danh nào đáng tin cậy hơn?
A. Chỉ so sánh email hiển thị, không cần biết issuer phát hành.
B. So sánh username sau khi chuyển thành chữ thường.
C. Dùng địa chỉ IP đăng nhập gần nhất làm khóa liên kết.
D. Dùng issuer/subject đã xác minh và chứng minh quyền sở hữu.
Đáp án đúng: D

32. Service provider xác minh SAML response nên kiểm tra những gì?
A. Chỉ kiểm tra chữ ký assertion và bỏ qua ngữ cảnh request.
B. Chỉ kiểm tra email trong assertion trùng với email nội bộ.
C. Chỉ kiểm tra thời gian nhận response ở phía trình duyệt.
D. Chữ ký, issuer, audience, recipient, InResponseTo và điều kiện thời gian.
Đáp án đúng: D

33. JIT provisioning từ SAML group claim cần kiểm soát nào để tránh cấp quyền ngoài dự kiến?
A. Tự động tin mọi group name do identity provider gửi.
B. Cấp role admin mặc định rồi để người dùng tự bỏ quyền.
C. Allowlist group theo policy đã duyệt.
D. Bỏ qua issuer vì group claim đã được ký.
Đáp án đúng: C

34. Khi nào nên yêu cầu step-up authentication?
A. Mỗi lần người dùng mở trang công khai không chứa dữ liệu.
B. Trước hành động nhạy cảm như chuyển tiền hoặc đổi yếu tố khôi phục.
C. Chỉ khi người dùng đăng xuất rồi đăng nhập lại từ đầu.
D. Chỉ khi trình duyệt thay đổi kích thước cửa sổ.
Đáp án đúng: B

35. Log xác thực nào hữu ích nhất để điều tra account takeover mà vẫn tránh ghi bí mật?
A. Chỉ ghi mật khẩu người dùng và toàn bộ OTP đã nhập.
B. Chỉ ghi số lần đăng nhập thành công theo ngày.
C. Ghi cookie phiên và refresh token để nhóm điều tra tái sử dụng.
D. Ghi subject, outcome, MFA, IP, risk và correlation ID.
Đáp án đúng: D

36. Access token bearer bị đánh cắp có thể bị dùng lại từ thiết bị khác. Cơ chế nào giảm rủi ro này?
A. Tăng thời hạn token để client không phải refresh thường xuyên.
B. Đưa token vào query string để API dễ ghi nhận mọi request.
C. Dùng sender-constrained token như mTLS-bound token hoặc DPoP khi phù hợp.
D. Chỉ kiểm tra username trong payload mà không ràng buộc người gửi.
Đáp án đúng: C
