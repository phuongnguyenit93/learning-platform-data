Câu 1. Passkey trong hệ thống đăng nhập hiện đại là gì?
A. Một mật khẩu dài được lưu trong secure cookie và tự đồng bộ giữa các trình duyệt.
B. Credential khóa công khai gắn RP, dùng xác thực không cần password.
C. Một mã OTP cố định do authenticator tạo và gửi cho máy chủ mỗi lần đăng nhập.
D. Một chứng chỉ TLS của website được cài trên thiết bị người dùng.
Đáp án đúng: B

Câu 2. Trong xác thực bằng public-key, máy chủ thường lưu thành phần nào của credential?
A. Credential ID và public key tương ứng để xác minh assertion.
B. Private key của authenticator để máy chủ tự ký challenge về sau.
C. Mã PIN hoặc dữ liệu sinh trắc học dùng để mở khóa authenticator.
D. Bản sao toàn bộ secure element để có thể khôi phục credential.
Đáp án đúng: A

Câu 3. FIDO2 gồm những thành phần tiêu chuẩn chính nào?
A. TLS cho trình duyệt và OAuth cho giao tiếp giữa authenticator với máy chủ.
B. JWT cho credential và TOTP cho giao tiếp giữa client với authenticator.
C. SAML đảm nhiệm web API còn LDAP truyền dữ liệu giữa client và authenticator.
D. WebAuthn cho tương tác web và CTAP cho giao tiếp client với authenticator.
Đáp án đúng: D

Câu 4. RP ID trong WebAuthn xác định phạm vi nào?
A. Tên miền định danh của relying party mà credential được ràng buộc.
B. URL đầy đủ gồm scheme, port và path của từng trang đăng nhập.
C. Địa chỉ IP của authenticator được dùng trong lần đăng ký đầu tiên.
D. Tên hiển thị của ứng dụng mà người dùng chọn khi tạo passkey.
Đáp án đúng: A

Câu 5. Origin của một WebAuthn request được biểu diễn bằng thông tin nào?
A. Scheme, hostname và port của trang khởi tạo WebAuthn.
B. Chỉ hostname đã bỏ scheme, port và mọi subdomain.
C. RP ID, credential ID và public key được lưu ở máy chủ.
D. Địa chỉ IP của máy chủ DNS phân giải tên relying party.
Đáp án đúng: A

Câu 6. Challenge trong registration hoặc authentication ceremony nên được tạo và quản lý ra sao?
A. Dùng một chuỗi cố định cho mỗi tài khoản để client dễ ghi nhớ.
B. Lấy timestamp hiện tại làm challenge và chấp nhận nhiều lần.
C. Để authenticator tự chọn challenge mà server không cần lưu.
D. Challenge ngẫu nhiên, gắn phiên, ngắn hạn và dùng một lần.
Đáp án đúng: D

Câu 7. Trong registration ceremony, authenticator thực hiện thao tác cốt lõi nào?
A. Tạo mật khẩu ngẫu nhiên, mã hóa bằng public key của máy chủ rồi gửi lại.
B. Tạo session cookie và đồng bộ cookie với mọi authenticator của người dùng.
C. Tạo chứng chỉ CA cho RP rồi cài root certificate lên trình duyệt.
D. Tạo cặp khóa gắn với RP và trả credential public key cùng dữ liệu registration.
Đáp án đúng: D

Câu 8. clientDataJSON trong phản hồi WebAuthn thường chứa những trường nào?
A. Type, challenge, origin và các thông tin ngữ cảnh client liên quan.
B. Private key, mã PIN, dữ liệu vân tay và khóa bí mật của RP.
C. Credential ID, public key đã lưu và trạng thái thu hồi của tài khoản.
D. RP ID hash, sign counter và toàn bộ attested credential data.
Đáp án đúng: A

Câu 9. authenticatorData có thể chứa nhóm thông tin nào?
A. Chỉ username, password, email và trạng thái đăng nhập của người dùng.
B. RP ID hash, flags, counter và credential data khi đăng ký.
C. Origin, HTTP cookie, access token và địa chỉ IP của client.
D. Private key, PIN và dữ liệu sinh trắc học của authenticator.
Đáp án đúng: B

Câu 10. Vì sao relying party cần kiểm tra `rpIdHash` trong authenticatorData?
A. Dùng hash để tìm lại private key của authenticator trong server database.
B. Xác minh hash của origin thay cho kiểm tra origin trong client data.
C. So sánh hash với địa chỉ IP để phát hiện thiết bị giả mạo.
D. Đối chiếu hash của RP ID mong đợi để ràng buộc response với relying party.
Đáp án đúng: D

Câu 11. User Presence (UP) và User Verification (UV) khác nhau thế nào?
A. UP xác minh danh tính bằng sinh trắc học; UV chỉ kiểm tra chạm nút.
B. UP cho biết có tương tác hiện diện; UV cho biết đã xác minh người dùng cục bộ.
C. UP và UV đều là bằng chứng máy chủ đã xác minh tài khoản.
D. UP áp dụng cho đăng ký; UV chỉ được dùng cho TLS client authentication.
Đáp án đúng: B

Câu 12. Trong authentication assertion, dữ liệu nào được ký để tạo chữ ký xác thực?
A. Chỉ `clientDataJSON` được ký trực tiếp, không kèm authenticator data.
B. Credential ID nối với RP ID rồi mã hóa bằng public key của server.
C. `authenticatorData` nối với hash của `clientDataJSON`.
D. Toàn bộ HTTP request và response body được ký bằng private key.
Đáp án đúng: C

Câu 13. Credential ID và public key có vai trò khác nhau ra sao?
A. Credential ID là public key; public key chỉ dùng để tìm tài khoản.
B. Credential ID định danh credential; public key dùng xác minh chữ ký assertion.
C. Credential ID mã hóa private key; public key giải mã challenge.
D. Hai giá trị giống nhau và có thể dùng thay thế trong mọi bước.
Đáp án đúng: B

Câu 14. Platform authenticator khác roaming authenticator ở đặc điểm nào?
A. Platform authenticator luôn đồng bộ cloud; roaming authenticator không thể backup.
B. Platform authenticator chỉ dùng PIN; roaming authenticator chỉ dùng sinh trắc học.
C. Platform authenticator tích hợp thiết bị; roaming authenticator là thiết bị ngoài có thể di chuyển.
D. Platform authenticator xác thực server; roaming authenticator xác thực user.
Đáp án đúng: C

Câu 15. Discoverable credential hỗ trợ kiểu đăng nhập nào?
A. Đăng nhập bằng mật khẩu được lưu trong authenticator để tự điền.
B. Đăng nhập chỉ bằng chứng chỉ TLS của thiết bị, không cần RP ID.
C. Đăng nhập bằng OTP được authenticator gửi qua SMS.
D. Đăng nhập không cần nhập username trước khi chọn credential phù hợp.
Đáp án đúng: D

Câu 16. Với credential không discoverable, client thường cần dữ liệu nào để chọn credential?
A. Private key của credential để client chọn đúng khóa bí mật.
B. Credential ID được relying party cung cấp qua `allowCredentials`.
C. Mã PIN của authenticator để tìm credential trong mọi RP.
D. Toàn bộ danh sách credential của mọi website trên thiết bị.
Đáp án đúng: B

Câu 17. CTAP2 đảm nhiệm vai trò nào trong kiến trúc FIDO2?
A. Giao thức giữa relying party và CA để phát hành certificate.
B. Giao thức giữa trình duyệt và DNS để xác minh RP ID.
C. Giao thức client-to-authenticator cho security key.
D. Giao thức đồng bộ credential giữa cloud account và máy chủ RP.
Đáp án đúng: C

Câu 18. Attestation trong registration có thể cung cấp thông tin gì?
A. Mật khẩu gốc và danh tính dân sự đã xác minh của người dùng.
B. Quyền truy cập nghiệp vụ mà relying party phải cấp cho tài khoản.
C. Bằng chứng về loại hoặc nguồn authenticator theo mô hình attestation.
D. Private key thô để relying party sao lưu và dùng lại.
Đáp án đúng: C

Câu 19. Vì sao nhiều hệ thống chọn attestation `none` hoặc hạn chế thu thập attestation?
A. Vì attestation luôn làm mất khả năng xác minh chữ ký assertion.
B. Vì attestation bắt buộc tiết lộ private key của authenticator.
C. Vì `none` khiến trình duyệt tự bỏ qua origin và challenge validation.
D. Bảo vệ riêng tư bằng cách hạn chế attestation.
Đáp án đúng: D

Câu 20. Cờ Backup Eligibility (BE) và Backup State (BS) biểu thị điều gì?
A. BE cho biết user đã xác minh; BS cho biết user đang hiện diện.
B. BE cho biết credential hết hạn; BS cho biết credential đã bị thu hồi.
C. BE báo khả năng backup; BS báo trạng thái backup.
D. BE và BS lần lượt biểu thị thuật toán và độ dài khóa công khai.
Đáp án đúng: C

Câu 21. Passkey đồng bộ giữa thiết bị thường được nhận diện qua thuộc tính nào?
A. Mọi passkey đều gắn duy nhất một thiết bị và không thể đồng bộ.
B. Credential ID thay đổi theo từng lần assertion để xác định bản backup.
C. Backup flags biểu thị credential có thể backup và đang backup.
D. RP ID hash cho biết passkey đã được lưu trên cloud provider nào.
Đáp án đúng: C

Câu 22. Với passkey đồng bộ, nhận định nào về private key là chính xác?
A. Khóa có thể được đồng bộ an toàn giữa thiết bị qua hệ sinh thái provider, tùy chính sách và triển khai.
B. Private key luôn bị khóa vĩnh viễn trong một secure element và không thể đồng bộ.
C. Máy chủ RP nhận private key từ từng thiết bị để lưu trữ và đồng bộ credential.
D. Mọi passkey đồng bộ đều dùng chung một private key công khai cho tất cả RP.
Đáp án đúng: A

Câu 23. Đăng nhập liên thiết bị bằng điện thoại thường dùng luồng nào?
A. Gửi passkey qua email để thiết bị mới nhập lại credential.
B. Hybrid flow để điện thoại xác thực cho thiết bị khác.
C. Sao chép cookie đăng nhập từ điện thoại sang máy tính bằng QR.
D. Chuyển private key qua Bluetooth dưới dạng file để máy tính lưu.
Đáp án đúng: B

Câu 24. QR code và Bluetooth trong hybrid authentication hỗ trợ mục đích gì?
A. Thiết lập và hỗ trợ kênh liên thiết bị có xác minh proximity.
B. Thay thế challenge server bằng mã QR tĩnh không hết hạn.
C. Gửi credential private key qua Bluetooth để server xác minh.
D. Đồng bộ password và session cookie giữa hai thiết bị.
Đáp án đúng: A

Câu 25. Điều gì tạo nên khả năng chống phishing của WebAuthn?
A. Passkey luôn yêu cầu OTP thứ hai nên phishing không thể thành công.
B. Credential gắn RP ID và phản hồi xác thực được ràng buộc với origin hợp lệ.
C. TLS bảo vệ đường truyền nên mọi trang giả mạo đều bị trình duyệt chặn.
D. Authenticator xác minh tên miền bằng cách đọc nội dung HTML của website.
Đáp án đúng: B

Câu 26. Relying party cần xác minh gì ở phía server trước khi chấp nhận assertion?
A. Kiểm challenge, origin, RP hash, signature và credential state.
B. Chỉ HTTP status, username hiển thị và địa chỉ IP của client.
C. Chỉ cờ UP vì chạm authenticator chứng minh mọi thông tin khác.
D. Chỉ credential ID vì ID đã được tạo trong registration ceremony.
Đáp án đúng: A

Câu 27. Sign counter trong authenticatorData nên được diễn giải thế nào?
A. Bắt buộc tăng đơn điệu trên mọi lần dùng, nếu không phải từ chối ngay.
B. Dùng counter như dấu hiệu bổ sung, không tuyệt đối.
C. Là số lần người dùng nhập sai PIN và phải reset khi đạt ngưỡng.
D. Là số lần credential được backup giữa các thiết bị.
Đáp án đúng: B

Câu 28. Khi một người dùng có nhiều thiết bị, cách quản lý credential nào phù hợp?
A. Dùng một credential chung cho mọi thiết bị để giảm chi phí quản lý.
B. Ghi đè public key cũ mỗi khi người dùng đăng ký thiết bị mới.
C. Quản lý nhiều credential và thu hồi riêng từng thiết bị.
D. Chỉ lưu credential ID mới nhất và bỏ qua các credential còn lại.
Đáp án đúng: C

Câu 29. Khi người dùng báo mất một thiết bị có passkey, hành động nào nên được ưu tiên?
A. Chỉ đổi RP ID để passkey trên thiết bị mất tự mất hiệu lực.
B. Thu hồi key của thiết bị và kiểm soát session.
C. Xóa tài khoản người dùng vì credential không thể được thu hồi riêng.
D. Giữ nguyên credential và chỉ đổi mật khẩu dự phòng.
Đáp án đúng: B

Câu 30. Khôi phục tài khoản có thể làm suy yếu bảo mật passkey trong trường hợp nào?
A. Khi passkey dùng public-key cryptography thay vì shared secret.
B. Khi relying party kiểm tra challenge một lần và có thời hạn.
C. Fallback recovery yếu có thể bị khai thác chiếm tài khoản.
D. Khi thiết bị mới có platform authenticator thay vì roaming key.
Đáp án đúng: C

Câu 31. Vì sao backup passkey không đồng nghĩa với quy trình account recovery?
A. Backup credential khác quy trình xác minh lại quyền tài khoản.
B. Backup và recovery đều là sao lưu private key vào máy chủ RP.
C. Recovery tự động xảy ra khi browser xóa cookie đăng nhập.
D. Backup là bước xác minh danh tính bằng giấy tờ do CA thực hiện.
Đáp án đúng: A

Câu 32. Khi yêu cầu UV cho thao tác nhạy cảm, relying party nên cấu hình thế nào?
A. Yêu cầu cờ UV theo policy cho thao tác đó và kiểm tra flag phía server.
B. Chỉ yêu cầu UP vì mọi thao tác chạm authenticator đều xác minh danh tính.
C. Bỏ qua UV nếu credential ID đã tồn tại trong database.
D. Chỉ bật UV ở trình duyệt; server không cần kiểm tra authenticator data.
Đáp án đúng: A

Câu 33. WebAuthn được gọi trong cross-origin iframe cần lưu ý kiểm soát nào?
A. Chỉ cần CORS wildcard vì iframe có thể dùng mọi RP ID.
B. Chỉ kiểm tra cookie third-party vì WebAuthn không chịu giới hạn iframe.
C. Permissions Policy và điều kiện cho phép WebAuthn trong embedded context.
D. Cho phép mọi iframe gọi WebAuthn nếu trang cha đã dùng HTTPS.
Đáp án đúng: C

Câu 34. Vì sao relying party cần allowlist thuật toán chữ ký được hỗ trợ?
A. Để server tự chọn bất kỳ thuật toán nào client khai báo trong response.
B. Đảm bảo credential ID luôn có cùng độ dài trên mọi authenticator.
C. Giúp origin và RP ID được mã hóa cùng một thuật toán.
D. Ngăn thuật toán không mong đợi hoặc yếu được chấp nhận khi xác minh chữ ký.
Đáp án đúng: D

Câu 35. Challenge đã dùng trong một ceremony cần được xử lý thế nào?
A. Giữ challenge dùng lại được đến khi session đăng nhập hết hạn.
B. Chấp nhận lại nếu chữ ký assertion hợp lệ và credential chưa thu hồi.
C. Đánh dấu đã tiêu thụ và từ chối replay trong các ceremony tiếp theo.
D. Lưu challenge ở client và không cần kiểm tra phía server.
Đáp án đúng: C

Câu 36. Kiểm soát nào giúp giảm rủi ro từ việc dò credential hoặc lạm dụng login endpoint?
A. Tắt rate limit để không ảnh hưởng người dùng có nhiều thiết bị.
B. Dùng cùng challenge cho mọi tài khoản để giảm số lần tạo ngẫu nhiên.
C. Trả thông báo khác nhau cho từng username để dễ chẩn đoán.
D. Giới hạn tốc độ, phát hiện bất thường và tránh tiết lộ tài khoản tồn tại.
Đáp án đúng: D

Câu 37. Attestation có chứng minh người dùng là người thật hoặc đã được định danh không?
A. Có; attestation luôn chứa danh tính pháp lý đã xác minh của chủ thể.
B. Attestation mô tả authenticator, không định danh dân sự user.
C. Có; CA attestation chịu trách nhiệm cấp quyền nghiệp vụ cho user.
D. Không; attestation chỉ chứng minh website đã có chứng chỉ TLS.
Đáp án đúng: B

Câu 38. Vì sao kiểm tra origin chính xác vẫn quan trọng khi RP ID là domain cha?
A. RP ID và origin luôn là hai chuỗi giống nhau ở mọi deployment.
B. RP ID cha cho phép mọi origin con được chấp nhận mà không cần allowlist.
C. Origin chỉ cần kiểm tra khi RP ID là địa chỉ IP thay vì domain.
D. RP ID scope credential; origin xác định chính xác nguồn.
Đáp án đúng: D

Câu 39. Những sự kiện nào nên được giám sát trong vận hành passkey?
A. Theo dõi credential lifecycle, verification và recovery.
B. Chỉ số lần người dùng tải trang đăng nhập và thời gian phản hồi HTML.
C. Chỉ số lần challenge được tạo, không cần biết kết quả ceremony.
D. Chỉ phiên bản hệ điều hành và kích thước màn hình của client.
Đáp án đúng: A

Câu 40. Kiểm thử bảo mật passkey nên bao gồm trường hợp nào?
A. Chỉ thử đăng nhập thành công với một authenticator trên một trình duyệt.
B. Chỉ thử giao diện autofill và đo tốc độ hiển thị danh sách passkey.
C. Chỉ thử TLS certificate của website mà không kiểm tra assertion.
D. Replay challenge, origin/RP mismatch, credential bị thu hồi và recovery yếu.
Đáp án đúng: D
