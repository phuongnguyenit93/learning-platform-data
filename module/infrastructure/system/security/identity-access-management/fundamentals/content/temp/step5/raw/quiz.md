Câu 1. Trong IAM, một digital identity thường đại diện cho điều gì?
A. Một bản ghi chỉ chứa mật khẩu đã băm và không gắn với principal.
B. Một quyền truy cập đơn lẻ được cấp cho mọi tài khoản trong hệ thống.
C. Một phiên mạng được mã hóa giữa client và máy chủ ứng dụng.
D. Một thực thể người, thiết bị hoặc dịch vụ được nhận diện trong hệ thống.
Đáp án đúng: D

Câu 2. Phân biệt authentication và authorization chính xác nhất là gì?
A. Authentication xác minh danh tính; authorization quyết định quyền được phép.
B. Authentication cấp quyền tài nguyên; authorization xác minh mật khẩu người dùng.
C. Authentication tạo session; authorization chỉ mã hóa dữ liệu truyền tải.
D. Hai khái niệm giống nhau và có thể dùng thay thế cho nhau.
Đáp án đúng: A

Câu 3. Điều kiện nào tạo thành MFA thực sự?
A. Dùng hai mật khẩu khác nhau được lưu trong cùng một password manager.
B. Dùng mật khẩu và câu hỏi bí mật vì cả hai đều là thông tin ghi nhớ.
C. Dùng hai thiết bị nhận cùng một OTP được gửi qua SMS.
D. Kết hợp ít nhất hai yếu tố độc lập thuộc nhóm biết, có, hoặc là.
Đáp án đúng: D

Câu 4. Yếu tố nào khiến passkey/WebAuthn có khả năng chống phishing tốt?
A. Mã OTP có thời hạn ngắn được nhập trên bất kỳ trang đăng nhập nào.
B. Mật khẩu dài được trình duyệt tự điền vào form có cùng logo.
C. Mật mã ràng buộc credential với RP ID và origin của website.
D. Push notification yêu cầu người dùng xác nhận tên ứng dụng.
Đáp án đúng: C

Câu 5. Một nhân viên liên tục nhận push MFA bất ngờ và cuối cùng bấm Approve; đây là kiểu tấn công nào?
A. Push bombing khai thác việc người dùng mệt mỏi với yêu cầu MFA.
B. Credential stuffing dùng mật khẩu rò rỉ để thử trên nhiều dịch vụ.
C. SIM swapping chiếm số điện thoại để nhận mã xác thực.
D. Kerberoasting trích xuất ticket dịch vụ để dò mật khẩu ngoại tuyến.
Đáp án đúng: A

Câu 6. Quy trình joiner-mover-leaver nhằm kiểm soát điều gì?
A. Quản lý cấp, đổi và thu hồi tài khoản/quyền theo vòng đời nhân sự.
B. Quy trình tạo bản sao lưu dữ liệu khi nhân viên đổi thiết bị làm việc.
C. Cơ chế mã hóa session cookie theo từng phòng ban của tổ chức.
D. Quy trình đổi mật khẩu định kỳ mà không xét vai trò công việc.
Đáp án đúng: A

Câu 7. Khi nhân viên nghỉ việc, hành động IAM nào cần được thực hiện kịp thời?
A. Chỉ xóa tài khoản khỏi danh bạ công ty sau khi bàn giao thiết bị.
B. Giữ nguyên token đến ngày hết hạn để tránh ảnh hưởng dịch vụ.
C. Vô hiệu hóa principal, phiên, token và credential liên quan.
D. Chuyển tài khoản sang nhóm khách để bảo toàn lịch sử truy cập.
Đáp án đúng: C

Câu 8. SCIM thường được dùng để giải quyết nhu cầu nào?
A. Mã hóa dữ liệu nhạy cảm trong database bằng khóa đối xứng.
B. Đồng bộ mật khẩu người dùng giữa các ứng dụng bằng giao thức TLS.
C. Phân tích lưu lượng mạng để phát hiện đăng nhập từ thiết bị lạ.
D. Provisioning tài khoản và nhóm giữa các hệ thống qua giao thức chuẩn.
Đáp án đúng: D

Câu 9. Trong mô hình SSO liên kết, IdP và Service Provider có vai trò gì?
A. IdP lưu dữ liệu ứng dụng; SP phát hành mật khẩu cho người dùng.
B. IdP quyết định mọi quyền nội bộ; SP chỉ chuyển tiếp lưu lượng mạng.
C. IdP mã hóa database; SP chịu trách nhiệm quản lý khóa bí mật.
D. IdP xác thực và phát assertion; SP tiêu thụ assertion để cấp phiên.
Đáp án đúng: D

Câu 10. SAML assertion được dùng chủ yếu để truyền thông tin nào?
A. Mật khẩu gốc và private key mà người dùng nhập vào trang đăng nhập.
B. Thông tin xác thực đã được IdP phát hành cho subject và audience xác định.
C. Danh sách mọi quyền quản trị được cấp trên các hệ thống liên kết.
D. Mã hóa toàn bộ request body để SP không đọc được nội dung.
Đáp án đúng: B

Câu 11. Trong OpenID Connect, ID Token khác OAuth access token ở mục đích nào?
A. ID Token cấp quyền gọi API; access token chứng minh danh tính người dùng.
B. ID Token mô tả lần đăng nhập; access token cấp quyền truy cập resource.
C. Cả hai token đều là refresh token và chỉ khác thời hạn hiệu lực.
D. ID Token dành cho client secret; access token dành cho browser cookie.
Đáp án đúng: B

Câu 12. Vì sao public client thường dùng Authorization Code Flow với PKCE?
A. PKCE mã hóa access token bằng mật khẩu người dùng trước khi gửi API.
B. PKCE thay thế redirect URI và cho phép mọi callback URL được chấp nhận.
C. PKCE giúp public client giữ client secret cố định trong ứng dụng.
D. Code verifier bảo vệ authorization code khỏi bị chặn dùng lại.
Đáp án đúng: D

Câu 13. Khi xác minh JWT, relying party nên kiểm tra tập điều kiện nào?
A. Xác minh signature, issuer, audience, thời hạn và thuật toán.
B. Chỉ kiểm tra chữ ký và subject vì issuer đã được chọn lúc cấu hình.
C. Chỉ kiểm tra thời hạn và audience, bỏ qua thuật toán chữ ký.
D. Giải mã JWT rồi tin payload vì token có cấu trúc JSON hợp lệ.
Đáp án đúng: A

Câu 14. Audience claim của access token giúp ngăn rủi ro nào?
A. Ngăn token được phát cho resource khác bị dùng tại API hiện tại.
B. Ngăn người dùng thay đổi claim role trong access token đã ký.
C. Ngăn refresh token bị tái sử dụng sau khi người dùng đăng xuất.
D. Ngăn client gửi request qua một mạng không được mã hóa TLS.
Đáp án đúng: A

Câu 15. Refresh token rotation kèm phát hiện reuse có tác dụng gì?
A. Cho phép nhiều client dùng chung refresh token mà không cần kiểm soát.
B. Tự gia hạn access token vô thời hạn mà không cần xác thực lại.
C. Thay thế hoàn toàn việc kiểm tra issuer và audience của access token.
D. Phát hiện reuse token cũ và thu hồi nhóm refresh token liên quan.
Đáp án đúng: D

Câu 16. OAuth scope có ý nghĩa gì đối với quyền truy cập API?
A. Private key của credential được gửi cho client để xác định đúng khóa cần dùng.
B. Mã PIN của authenticator được chuyển lên RP để tìm credential tương ứng.
C. RP cung cấp danh sách credential ID được phép để client đối chiếu và chọn.
D. Client tải toàn bộ credential ID từ mọi relying party đã đăng ký trên thiết bị.
Đáp án đúng: C

Câu 17. RBAC quyết định quyền truy cập dựa trên yếu tố nào?
A. Địa chỉ IP, thời gian truy cập và vị trí địa lý của principal.
B. Nội dung request, trạng thái thiết bị và nhãn dữ liệu đang truy cập.
C. Vai trò được gán cho principal và quyền gắn với từng vai trò.
D. Quan hệ sở hữu dữ liệu và mức độ rủi ro của từng phiên.
Đáp án đúng: C

Câu 18. ABAC đánh giá quyền truy cập dựa trên dữ liệu nào?
A. Chỉ role cố định được gán thủ công cho từng người dùng.
B. Chỉ nhóm người dùng và danh sách quyền đã định nghĩa trước.
C. Chỉ tên endpoint và phương thức HTTP mà client yêu cầu.
D. Policy xét nhiều thuộc tính thay vì role cố định.
Đáp án đúng: D

Câu 19. Khi policy có một rule Allow và một rule Deny cùng khớp, mô hình deny-overrides xử lý thế nào?
A. Cho phép truy cập nếu ít nhất một policy Allow khớp.
B. Chọn policy được tạo gần nhất và bỏ qua các policy còn lại.
C. Hỏi người dùng xác nhận để chọn policy có hiệu lực.
D. Từ chối truy cập nếu có bất kỳ policy Deny nào khớp.
Đáp án đúng: D

Câu 20. Least privilege yêu cầu tổ chức thực hiện điều gì?
A. Cấp quyền rộng trước để giảm yêu cầu hỗ trợ trong tương lai.
B. Chỉ cấp quyền cần thiết cho nhiệm vụ và thời gian cần thiết.
C. Giữ quyền cũ khi người dùng đổi vai trò để tránh gián đoạn.
D. Dùng một role quản trị chung cho các nhóm có cùng cấp bậc.
Đáp án đúng: B

Câu 21. Separation of duties giảm rủi ro nào?
A. Ngăn người dùng đăng nhập đồng thời từ nhiều thiết bị khác nhau.
B. Ngăn token được truyền qua nhiều dịch vụ trong một hệ thống.
C. Ngăn quản trị viên xem audit log về hành động của chính họ.
D. Ngăn một người tự kiểm soát toàn bộ quy trình nhạy cảm.
Đáp án đúng: D

Câu 22. Just-in-Time (JIT) access giúp bảo vệ quyền đặc quyền ra sao?
A. Cấp role quản trị vĩnh viễn để tránh gián đoạn khi trực sự cố.
B. Dùng tài khoản dùng chung để nhiều người thay phiên thao tác.
C. Cấp quyền đặc quyền trong khoảng thời gian ngắn sau khi được phê duyệt.
D. Chuyển quyền đặc quyền thành quyền thường và không cần ghi log.
Đáp án đúng: C

Câu 23. PAM thường bổ sung kiểm soát nào cho tài khoản quản trị?
A. Tự động chia sẻ mật khẩu quản trị cho mọi thành viên trong nhóm.
B. Vault credential, phê duyệt, session recording và kiểm soát lệnh đặc quyền.
C. Chỉ mã hóa ổ đĩa chứa tài khoản và bỏ qua giám sát phiên.
D. Thay MFA bằng whitelist địa chỉ IP cho mọi tài khoản quản trị.
Đáp án đúng: B

Câu 24. Break-glass account nên được quản lý theo cách nào?
A. Dùng hằng ngày cho tác vụ thường để chắc chắn tài khoản luôn hoạt động.
B. Chia sẻ mật khẩu cho đội trực để ai cũng có thể xử lý sự cố.
C. Loại khỏi audit log để tránh lộ thông tin tài khoản khẩn cấp.
D. Tách biệt, giám sát chặt, kiểm tra định kỳ và cảnh báo mọi lần sử dụng.
Đáp án đúng: D

Câu 25. Vì sao cần tạo session ID mới sau khi người dùng đăng nhập thành công?
A. Giữ nguyên session ID để các tab trình duyệt không bị đăng xuất.
B. Đổi session identifier sau khi authentication thành công.
C. Tạo session ID từ username để người dùng dễ khôi phục phiên.
D. Dùng lại session ID cũ nếu mật khẩu đã được xác minh qua MFA.
Đáp án đúng: B

Câu 26. Cookie phiên nhạy cảm nên được cấu hình thế nào?
A. Bật Secure, HttpOnly và SameSite phù hợp với luồng sử dụng.
B. Chỉ bật HttpOnly vì thuộc tính này đồng thời bật mã hóa TLS.
C. Đặt cookie accessible từ JavaScript để client tự kiểm tra session.
D. Bỏ Secure trên HTTPS để trình duyệt gửi cookie qua mọi kết nối.
Đáp án đúng: A

Câu 27. Session idle timeout và absolute timeout khác nhau ra sao?
A. Idle đo thời gian không hoạt động; absolute đo tổng tuổi phiên.
B. Idle timeout tính từ lúc đăng nhập; absolute timeout tính từ request gần nhất.
C. Hai timeout giống nhau và chỉ khác tên cấu hình theo hệ thống.
D. Absolute timeout chỉ áp dụng khi người dùng đăng nhập bằng password.
Đáp án đúng: A

Câu 28. CSRF token giúp bảo vệ request thay đổi trạng thái theo cách nào?
A. Token mã hóa response để trình duyệt không đọc được dữ liệu trả về.
B. Token chứng minh request có gắn với phiên hợp lệ của người dùng.
C. Token xác minh quyền của user trên object mà không cần authorization.
D. Token thay thế cookie SameSite và kiểm tra nguồn request.
Đáp án đúng: B

Câu 29. Access review định kỳ nên xác minh điều gì?
A. Xác minh owner, mục đích và quyền hiện tại còn cần thiết.
B. Chỉ kiểm tra tài khoản có đăng nhập trong 30 ngày gần nhất hay không.
C. Chỉ kiểm tra số lượng role mà người dùng đang sở hữu.
D. Chỉ kiểm tra người quản lý trực tiếp có còn trong tổ chức không.
Đáp án đúng: A

Câu 30. Kiểm soát nào ngăn BOLA khi người dùng truy cập object qua API?
A. Ẩn object ID tuần tự và dựa vào độ khó đoán để ngăn truy cập.
B. Kiểm tra quyền trên object cụ thể theo principal hiện tại ở mỗi request.
C. Chỉ kiểm tra quyền ở giao diện rồi tin client gửi object ID hợp lệ.
D. Dùng TLS để bảo đảm người dùng không thể thay object ID trong URL.
Đáp án đúng: B

Câu 31. Workload identity khác human identity ở đặc điểm nào?
A. Workload identity luôn có mật khẩu; human identity chỉ dùng certificate.
B. Workload identity đại diện tiến trình/dịch vụ; human identity đại diện con người.
C. Workload identity không cần authorization vì chạy trong hạ tầng nội bộ.
D. Human identity chỉ tồn tại trong directory; workload không có principal.
Đáp án đúng: B

Câu 32. Federation cho workload giúp giảm rủi ro nào so với static key?
A. Giảm số lần xác thực bằng cách cấp một API key không hết hạn.
B. Cho phép workload lưu private key trong image để triển khai nhanh.
C. Federation cấp credential ngắn hạn thay secret tĩnh dài hạn.
D. Chuyển mọi quyền workload thành role quản trị dùng chung.
Đáp án đúng: C

Câu 33. Service account dùng chung cho nhiều workload tạo ra vấn đề gì?
A. Shared identity làm mờ attribution và mở rộng blast radius.
B. Giúp audit rõ từng workload vì mọi request dùng cùng một principal.
C. Tự động giới hạn quyền theo namespace mà không cần policy.
D. Ngăn credential bị sao chép vì các workload chia sẻ cùng một secret.
Đáp án đúng: A

Câu 34. Credential rotation an toàn cần bảo đảm điều gì?
A. Xóa credential cũ trước khi cấp credential mới để không tồn tại hai khóa.
B. Chỉ đổi tên secret để workload tự nhận biết credential mới.
C. Chuyển đổi có overlap kiểm soát, cập nhật consumer và thu hồi credential cũ.
D. Giữ credential cũ vô thời hạn để rollback mà không cần đánh giá rủi ro.
Đáp án đúng: C

Câu 35. Identity proofing khác authentication như thế nào?
A. Proofing cấp quyền API; authentication quyết định role nghiệp vụ.
B. Proofing xác minh session cookie; authentication xác minh giấy tờ pháp lý.
C. Proofing xác minh danh tính; authentication xác minh claimant.
D. Hai hoạt động giống nhau và luôn diễn ra cùng một thời điểm.
Đáp án đúng: C

Câu 36. Vì sao account recovery là một phần quan trọng của IAM threat model?
A. Recovery chỉ ảnh hưởng trải nghiệm người dùng, không tác động bảo mật.
B. Kênh recovery yếu có thể bị lạm dụng để vượt qua MFA hoặc chiếm tài khoản.
C. Recovery luôn an toàn nếu tài khoản chính đã bật MFA trước đó.
D. Recovery chỉ cần xác minh email vì email không thể bị chiếm quyền.
Đáp án đúng: B

Câu 37. Audit log IAM hữu ích cần ghi nhận những thông tin nào?
A. Chỉ username và trạng thái thành công để tránh lưu dữ liệu quá nhiều.
B. Chỉ địa chỉ IP và user agent, không cần lưu hành động cụ thể.
C. Ghi principal, hành động, resource, thời gian và kết quả.
D. Chỉ role hiện tại và tổng số request trong ngày của principal.
Đáp án đúng: C

Câu 38. Conditional access nên đánh giá tín hiệu nào khi quyết định truy cập?
A. Kết hợp identity, device posture, risk và resource sensitivity.
B. Chỉ địa chỉ IP vì vị trí mạng đủ chứng minh danh tính người dùng.
C. Chỉ thời gian đăng nhập và loại trình duyệt của người dùng.
D. Chỉ role trong directory vì role đã phản ánh mọi rủi ro truy cập.
Đáp án đúng: A

Câu 39. Delegated authorization consent cần giới hạn theo nguyên tắc nào?
A. Cấp toàn bộ quyền API để tránh yêu cầu consent nhiều lần.
B. Giới hạn consent ở scope cần thiết và hỗ trợ revoke.
C. Dùng consent một lần cho mọi client và không cần rà soát lại.
D. Cho phép client tự khai báo scope sau khi access token đã phát hành.
Đáp án đúng: B

Câu 40. Khi phát hiện đăng nhập bất thường có nguy cơ chiếm tài khoản, phản ứng IAM nào phù hợp?
A. Chỉ đổi mật khẩu nhưng giữ nguyên mọi phiên và refresh token hiện có.
B. Tắt audit log để ngăn kẻ tấn công biết hệ thống đang điều tra.
C. Thu hồi phiên và refresh token, yêu cầu xác thực lại và điều tra hoạt động.
D. Chỉ chặn IP hiện tại mà không kiểm tra credential hoặc session bị lộ.
Đáp án đúng: C
