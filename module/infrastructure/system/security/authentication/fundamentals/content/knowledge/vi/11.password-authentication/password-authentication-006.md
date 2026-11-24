# Password change — Thay đổi mật khẩu an toàn

> **Chương:** Password authentication  
> **Chủ đề:** Password change

**Password change** là quy trình thay password hiện tại bằng một password mới cho cùng một tài khoản. Đây là thao tác thay đổi credential có ảnh hưởng trực tiếp đến khả năng đăng nhập, phiên đang hoạt động, thiết bị đã tin cậy và các quy trình khôi phục. Một quy trình tốt phải chứng minh người yêu cầu có quyền thay đổi credential, kiểm tra password mới theo chính sách, cập nhật verifier an toàn và xử lý những phiên/token có thể đã bị kẻ khác chiếm.

Không nên gộp mọi trường hợp “đổi mật khẩu” thành một endpoint duy nhất. Người dùng đang đăng nhập và biết password hiện tại có một luồng **change password**; người quên password cần **password reset/recovery** với bằng chứng khác; quản trị viên hoặc IdP doanh nghiệp có thể có chính sách riêng. Mỗi luồng có ranh giới tin cậy và mức bảo đảm khác nhau.

Bài học đặt password change trong phạm vi **SECURITY_AUTHENTICATION_FUNDAMENTALS**: credential, MFA, phiên/token, liên kết danh tính, khôi phục tài khoản, chống phishing và lạm dụng đăng nhập. Trọng tâm là thiết kế thay đổi password an toàn xuyên suốt từ client đến verifier và các hệ thống tiêu thụ trạng thái xác thực.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Phân biệt **change password**, **password reset**, **recovery** và thay đổi credential do quản trị/IdP thực hiện.
2. Thiết kế bước xác thực lại trước khi thay password, kể cả khi người dùng đã có session.
3. Định nghĩa chính sách password mới dựa trên độ dài, tính khó đoán và mật khẩu đã lộ; hỗ trợ password manager.
4. Cập nhật password verifier bằng thuật toán chuyên dụng, salt riêng và tham số chi phí phù hợp.
5. Xử lý CSRF, session fixation, request đồng thời, thông báo bảo mật và thu hồi session/token.
6. Xây dựng luồng reset/recovery không biến email, SMS hoặc helpdesk thành đường vòng yếu hơn.
7. Viết test case cho thay đổi thành công, thất bại, replay, phiên cũ, token cũ và các tình huống race condition.

## 2. Change password khác reset password thế nào?

Hai quy trình đều có thể tạo password mới, nhưng bằng chứng cần thiết khác nhau.

| Quy trình | Bối cảnh | Bằng chứng chính | Rủi ro cần xử lý |
| --- | --- | --- | --- |
| **Change password** | Người dùng đã đăng nhập và muốn thay password | Session hợp lệ và thường cần xác thực lại bằng password hiện tại hoặc phương thức đủ mạnh | Session bị đánh cắp, CSRF, kẻ tấn công đổi password để khóa chủ tài khoản |
| **Password reset** | Người dùng quên password hoặc password cần được đặt lại | Recovery token, passkey/MFA dự phòng hoặc quy trình xác minh được phê duyệt | Chiếm email/điện thoại, token đoán được, reset link bị lộ |
| **Account recovery** | Mất nhiều hoặc tất cả phương thức xác thực | Bằng chứng phục hồi theo mức rủi ro, có thể cần kiểm tra thủ công | Social engineering, helpdesk bypass, liên kết sai danh tính |
| **Administrative reset** | Tổ chức yêu cầu đặt lại credential | Quyền quản trị được ủy quyền và quy trình audit | Lạm dụng quyền nội bộ, reset sai tài khoản, không thông báo |
| **Federated password change** | Tài khoản dùng SSO/IdP bên ngoài | Quy trình đổi password của IdP | Ứng dụng RP tự thu password IdP hoặc làm sai lệch nguồn quản lý |

Một session đăng nhập thành công trước đó chỉ chứng minh đã có một lần xác thực. Với thao tác thay credential có ảnh hưởng cao, hệ thống nên yêu cầu **recent authentication** (xác thực gần đây) và mức bảo đảm phù hợp. Nếu tài khoản chỉ dùng SSO và không có password nội bộ, ứng dụng không nên tự tạo một password cục bộ ngoài chính sách danh tính.

### 2.1. Khi nào cần xác thực lại?

Các trường hợp thường cần xác thực lại hoặc step-up:

- Đổi password, email khôi phục hoặc số điện thoại khôi phục;
- Thêm/xóa passkey, TOTP authenticator hoặc phương thức đăng nhập;
- Tắt MFA hoặc thay đổi cấu hình bảo mật tài khoản;
- Liên kết/gỡ liên kết IdP;
- Thao tác quản trị, xuất dữ liệu nhạy cảm hoặc nâng quyền;
- Tín hiệu rủi ro cho thấy session hiện tại có thể bị chiếm.

Việc xác thực lại nên dựa vào phương thức server tin cậy và chính sách theo rủi ro. Không nhận cờ do client gửi như **recently_authenticated = true** để bỏ qua bước kiểm chứng.

## 3. Luồng thay đổi password chuẩn

Một luồng điển hình gồm: bắt đầu từ session hợp lệ → xác thực lại → kiểm tra password mới → cập nhật verifier → xử lý phiên và thông báo.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser / App
    participant A as Authentication Service
    participant V as Credential Store
    participant S as Session / Token Store
    U->>B: Mở thay đổi mật khẩu
    B->>A: Yêu cầu change password + session
    A->>A: Kiểm tra session, CSRF, account state
    A-->>B: Yêu cầu xác thực lại nếu cần
    B->>A: Password hiện tại / step-up proof + password mới
    A->>V: Kiểm tra password hiện tại
    V-->>A: Kết quả xác minh
    A->>A: Kiểm tra policy password mới
    A->>V: Tạo hash mới và cập nhật nguyên tử
    A->>S: Thu hồi/giữ phiên theo policy, tạo lại phiên hiện tại
    A-->>B: Kết quả thành công
    A-->>U: Thông báo thay đổi bảo mật
~~~

Sơ đồ mô tả logic, không quy định một thứ tự giao thức duy nhất. Ví dụ, server có thể xác thực lại trước khi hiển thị form hoặc yêu cầu password hiện tại cùng password mới trong một request; điều quan trọng là **mọi điều kiện đều được kiểm tra phía server**, và thay đổi verifier chỉ diễn ra sau khi yêu cầu được chấp nhận.

### 3.1. Các bước bắt buộc ở phía server

1. Xác minh session, trạng thái tài khoản, tenant và quyền thay đổi credential.
2. Kiểm tra CSRF/origin theo mô hình cookie và browser; xác định giao dịch thay đổi có còn hiệu lực không.
3. Xác thực lại bằng password hiện tại hoặc phương thức được policy cho phép; với tài khoản rủi ro cao có thể cần MFA/passkey.
4. Kiểm tra password mới và xác nhận nhập lại (nếu giao diện yêu cầu) theo cùng một quy tắc server-side.
5. Tạo password verifier mới bằng thuật toán phù hợp và salt mới.
6. Cập nhật verifier cùng metadata liên quan trong một thao tác nhất quán; xử lý các request đồng thời.
7. Thu hồi hoặc duy trì session/token theo chính sách, tạo lại session hiện tại nếu cần.
8. Ghi audit event không chứa bí mật và gửi thông báo bảo mật.

Không nên cập nhật password trước khi xác thực lại hoặc lưu password mới vào một hàng đợi/log để xử lý sau. Một request thay đổi credential cần được xử lý như thao tác bảo mật có trạng thái rõ ràng.

## 4. Xác thực lại và bảo vệ yêu cầu đổi mật khẩu

### 4.1. Vì sao không chỉ dựa vào session?

Session cookie có thể bị đánh cắp qua XSS, malware, thiết bị dùng chung hoặc các lỗi lưu trữ. Nếu chỉ cần session hiện tại để đổi password, kẻ chiếm phiên có thể đặt password mới, khiến chủ tài khoản mất quyền truy cập và tạo persistence.

Xác thực lại giảm rủi ro này bằng cách yêu cầu một bằng chứng bổ sung có liên quan tới credential hiện tại. Tuy nhiên, password hiện tại cũng có thể bị phishing; với tài khoản quản trị hoặc rủi ro cao, ưu tiên step-up bằng passkey/khóa bảo mật chống phishing hoặc phương thức được tổ chức phê duyệt.

### 4.2. Ràng buộc xác thực lại với hành động

Kết quả xác thực lại nên gắn với:

- Đúng **subject/account** và tenant;
- Mục đích cụ thể, ví dụ **CHANGE_PASSWORD**;
- Thời điểm xác thực và thời hạn hiệu lực ngắn;
- Phương thức và mức bảo đảm đạt được;
- Phiên hoặc giao dịch khởi tạo thao tác;
- Trạng thái chưa sử dụng/đã tiêu thụ khi cần đảm bảo một lần.

Không tái sử dụng kết quả xác thực lại cho hành động khác như thêm recovery email hoặc cấp quyền admin nếu policy yêu cầu bằng chứng mới.

### 4.3. Chống CSRF và session fixation

Trong ứng dụng web dùng cookie:

- Đặt cookie phiên với **Secure**, **HttpOnly** và **SameSite** phù hợp; phạm vi domain/path hẹp.
- Dùng CSRF token và/hoặc kiểm tra Origin theo kiến trúc; không coi CORS là biện pháp chống CSRF đầy đủ.
- Không cho phép một trang bên ngoài gửi request đổi password bằng cookie tự động đính kèm mà thiếu kiểm soát.
- Sau khi thay đổi credential hoặc mức bảo đảm, cân nhắc cấp session ID mới để ngăn session fixation và giới hạn tác động của phiên cũ.
- Không đặt password, token xác thực lại hoặc recovery code trong URL.

Nếu endpoint là API cho native app, cần thiết kế bảo vệ request phù hợp nền tảng và không giả định browser CSRF token là giải pháp duy nhất. Dù client nào, server vẫn phải kiểm tra authorization và trạng thái giao dịch.

## 5. Chính sách lựa chọn password mới

Mục tiêu là giúp người dùng chọn password khó đoán và dễ quản lý, thay vì buộc họ tạo một chuỗi phức tạp nhưng theo mẫu dễ đoán.

### 5.1. Độ dài và tính khó đoán

- Ưu tiên hỗ trợ password dài và passphrase; đặt giới hạn tối đa đủ rộng để không cắt cụt âm thầm.
- Không áp đặt các quy tắc thành phần cứng nhắc nếu chúng khiến người dùng chọn mẫu có thể đoán như tên + năm + ký tự đặc biệt.
- Cho phép paste, autofill và password manager; không chặn các chuỗi dài chỉ vì không giống password do con người gõ.
- Chặn password phổ biến, đã bị lộ hoặc nằm trong danh sách không được phép theo chính sách.
- Không dùng tên, email, ngày sinh, mã nhân viên hoặc dữ liệu hồ sơ làm câu hỏi bảo mật thay thế.

### 5.2. So sánh password mới với password cũ

Nếu hệ thống lưu verifier của password hiện tại, có thể kiểm tra password mới không trùng password cũ bằng cách xác minh candidate với verifier cũ. Không cần lưu password cũ dạng plaintext để so sánh. Nếu có chính sách cấm tái sử dụng một số password trước đây, việc triển khai phải cân nhắc quyền riêng tư, chi phí lưu verifier và mức độ cần thiết; không giữ vô hạn lịch sử password thô.

### 5.3. Chuẩn hóa và Unicode

Quy tắc xử lý chuỗi phải nhất quán giữa lúc tạo và lúc xác thực. Không tự cắt password theo độ dài byte mà không thông báo; tránh chuẩn hóa Unicode không nhất quán khiến người dùng nhập cùng ký tự nhưng server xử lý khác nhau. Cần định nghĩa giới hạn theo số ký tự/code point hoặc byte, hỗ trợ Unicode theo policy và kiểm thử các chuỗi dài.

Không loại bỏ khoảng trắng hoặc đổi chữ hoa/thường tùy tiện. Nếu hệ thống có chuẩn hóa cụ thể, phải áp dụng cùng một quy tắc trong đăng ký, thay đổi và đăng nhập, đồng thời tránh làm hai password khác nhau trở thành một ngoài ý muốn.

## 6. Tạo và lưu password verifier mới

Server không nên lưu password mới để sử dụng về sau. Nó cần tạo **password verifier** từ password người dùng gửi và lưu verifier đó.

### 6.1. Password hashing

Ưu tiên thuật toán password hashing chuyên dụng như **Argon2id** nếu môi trường hỗ trợ. Các lựa chọn khác như scrypt, bcrypt hoặc PBKDF2 có thể phù hợp theo nền tảng và chính sách; phải chọn tham số chi phí dựa trên đo đạc và khả năng vận hành.

Một verifier cần có:

- Thuật toán và phiên bản;
- Tham số chi phí;
- Salt ngẫu nhiên riêng cho từng password;
- Hash kết quả;
- Thông tin phiên bản/metadata cần để nâng cấp sau này.

Không dùng SHA-256/SHA-1 đơn thuần làm password hashing; đây là các hàm hash nhanh và không được thiết kế để làm chậm việc đoán password. Không dùng một salt cố định chung cho mọi người dùng.

### 6.2. Pepper và quản lý secret

Một số kiến trúc thêm **pepper** như bí mật server-side bên ngoài database, ví dụ trong secret manager hoặc HSM. Pepper có thể giảm rủi ro nếu chỉ kho hash bị lộ, nhưng cần thiết kế rotation, backup và khả năng phục hồi. Nếu pepper mất, hệ thống có thể không xác minh được verifier hiện tại; nếu pepper lộ, cần kế hoạch xử lý toàn bộ credential phụ thuộc.

Không đưa pepper vào source code, container image, database cùng với hash hoặc log. Chỉ tiến trình xác thực cần quyền sử dụng secret này.

### 6.3. Ví dụ luồng xử lý

~~~text
change_password(session, current_proof, new_password):
    principal = validate_session_and_account(session)
    require_csrf_and_recent_authentication(session, purpose="CHANGE_PASSWORD")

    verify_current_credential(principal, current_proof)
    validate_new_password_policy(new_password)
    reject_if_compromised_or_reused(new_password, principal)

    new_verifier = password_kdf(
        password = new_password,
        unique_random_salt = generate_salt(),
        approved_parameters = current_password_hash_policy
    )

    transaction:
        confirm_credential_version_is_unchanged(principal)
        replace_password_verifier(principal, new_verifier)
        increment_credential_version(principal)
        record_password_changed_at(principal)

    apply_session_revocation_policy(principal, current_session=session)
    record_redacted_audit_event("password_changed", principal)
    notify_account_owner()
~~~

Đây là **pseudocode** giải thích trách nhiệm, không phải thư viện triển khai. Hàm xác thực lại phải kiểm tra bằng chứng thật; transaction cần bảo vệ request đồng thời; session policy cần được thực thi bởi hệ thống quản lý phiên/token.

## 7. Cập nhật nguyên tử và xử lý request đồng thời

Hai tab hoặc hai thiết bị có thể gửi yêu cầu đổi password gần như cùng lúc. Nếu server chỉ đọc verifier cũ, kiểm tra rồi ghi mà không phát hiện thay đổi ở giữa, một request có thể ghi đè kết quả của request khác hoặc để trạng thái session không nhất quán.

Các cách kiểm soát:

- Dùng transaction database hoặc compare-and-swap dựa trên **credential version**;
- Kiểm tra verifier/version hiện tại chưa thay đổi trước khi ghi;
- Mỗi yêu cầu đổi password có transaction ID/idempotency semantics phù hợp;
- Không xử lý một request đã tiêu thụ hoặc hết hạn như một request mới;
- Nếu hai request cạnh tranh, chỉ một request được chấp nhận theo chính sách; request còn lại phải xác thực lại.

Không ghi password vào event bus để xử lý bất đồng bộ. Nếu cần event “password changed”, chỉ gửi metadata đã loại bí mật sau khi transaction thành công.

## 8. Phiên, token và thiết bị sau khi đổi password

Đổi password có thể là dấu hiệu người dùng đang phản ứng với nghi ngờ bị xâm nhập. Vì vậy cần xác định rõ **những phiên nào còn được phép tiếp tục**.

### 8.1. Các chính sách thường gặp

| Chính sách | Hành vi | Khi phù hợp |
| --- | --- | --- |
| Giữ phiên hiện tại, thu hồi phiên khác | Người dùng tiếp tục trên thiết bị đang thao tác; thiết bị khác phải đăng nhập lại | UX thuận tiện khi xác thực lại mạnh và không có dấu hiệu compromise |
| Thu hồi mọi phiên, kể cả phiên hiện tại | Yêu cầu đăng nhập lại sau khi password thay đổi | Khi nghi ngờ chiếm tài khoản hoặc policy yêu cầu |
| Thu hồi refresh token và session, access token chờ hết hạn | Giảm khả năng cấp token mới; token tự chứa còn hạn có thể vẫn dùng được | Kiến trúc token có TTL ngắn và cơ chế kiểm tra trạng thái |
| Thu hồi ngay theo credential version/introspection | API kiểm tra phiên bản/trạng thái hoặc trạng thái token hiện tại | Khi yêu cầu thu hồi nhanh và hệ thống hỗ trợ kiểm tra trực tuyến |

**Không mặc định đổi password tự động thu hồi mọi bearer access token.** JWT tự chứa đã phát hành có thể tiếp tục hợp lệ đến exp nếu resource server không kiểm tra revocation/version hoặc không có denylist. Cần ghi rõ mức hiệu lực thu hồi trong kiến trúc.

### 8.2. Đổi session ID và cookie

Sau khi xác thực lại và đổi password, cấp session ID mới nếu session hiện tại được giữ. Cookie mới cần thuộc tính Secure/HttpOnly/SameSite phù hợp. Xóa cookie cũ ở client không đủ nếu server vẫn chấp nhận session cũ; trạng thái phía server phải được cập nhật.

Với native app, xử lý refresh token và kho lưu trữ an toàn theo nền tảng. Không yêu cầu người dùng nhập lại password trong background nếu không có tương tác và chính sách rõ ràng.

### 8.3. Thiết bị đã tin cậy và credential khác

Đổi password không tự động xóa passkey, TOTP, chứng chỉ thiết bị hoặc liên kết IdP. Nếu có dấu hiệu tài khoản bị chiếm, cần kiểm tra:

- Authenticator nào được thêm gần đây?
- Có recovery channel hoặc email/điện thoại nào vừa thay?
- Có phiên lạ, refresh token hoặc thiết bị lạ nào đang hoạt động?
- Có API key, app password hoặc credential tích hợp nào cần rotate?
- Có liên kết IdP nào không còn được tin cậy?

Quy trình xử lý compromise có thể cần thu hồi các credential liên quan, nhưng không nên xóa bừa mọi phương thức nếu người dùng cần chúng để khôi phục tài khoản.

## 9. Thông báo và audit sau thay đổi

Sau khi password thay đổi thành công, nên gửi thông báo tới kênh liên hệ đã đăng ký trước đó hoặc kênh phù hợp theo policy. Thông báo nên nói rõ sự kiện, thời điểm và cách báo cáo nếu người dùng không thực hiện; **không gửi password mới hoặc password cũ**.

Audit event có thể chứa:

- Subject nội bộ và tenant;
- Thời gian, kết quả, loại thao tác (change/reset/admin reset);
- Phương thức xác thực lại và mức bảo đảm;
- Actor (chính người dùng hoặc quản trị viên được ủy quyền);
- Credential version trước/sau hoặc correlation ID;
- Kết quả thu hồi session/token ở mức metadata.

Không ghi password, password hash, OTP, recovery code, reset token, session cookie hoặc access/refresh token nguyên dạng. Không ghi toàn bộ request body chỉ để thuận tiện debug.

Nếu thông báo qua email, email chỉ là **cảnh báo**, không phải một bằng chứng mới để đổi password. Không đính kèm link đăng nhập tự động hoặc password. Với thay đổi do admin thực hiện, thông báo và audit cần xác định rõ actor để người dùng có thể phát hiện lạm dụng quyền nội bộ.

## 10. Password reset và recovery an toàn

Reset password là đường thay credential khi người dùng không thể chứng minh password hiện tại. Đây là entry point riêng và thường yếu hơn login nếu không được thiết kế cẩn thận.

### 10.1. Luồng reset qua email minh họa

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant R as Recovery Service
    participant M as Mail Provider
    participant A as Auth Service
    U->>B: Yêu cầu reset
    B->>R: Gửi identifier
    R->>R: Phản hồi chung, áp dụng rate limit
    R->>M: Gửi link có token một lần nếu phù hợp
    M-->>U: Nhận thông báo
    U->>B: Mở trang reset
    B->>R: Xác nhận token và password mới
    R->>R: Kiểm tra subject, purpose, TTL, chưa dùng
    R->>A: Cập nhật verifier nguyên tử
    A->>A: Thu hồi session/token theo policy
    A-->>U: Thông báo hoàn tất
~~~

Token reset cần ngẫu nhiên đủ mạnh, gắn với subject và mục đích, có TTL, dùng một lần và không bị lộ qua log/referrer. Không dùng mã ngắn dễ đoán hoặc token tồn tại vô thời hạn. Endpoint reset phải chống enumeration, rate limit và không cho phép đổi password chỉ vì một request GET được email scanner/preview bot mở.

### 10.2. Kênh email/SMS không phải danh tính vĩnh viễn

Email và số điện thoại có thể đổi chủ, bị chiếm hoặc tái cấp. Việc kiểm soát hộp thư/điện thoại tại một thời điểm không chứng minh người đó là chủ sở hữu vĩnh viễn của account. Tài khoản có mức rủi ro cao cần phương thức recovery mạnh hơn, hoặc kết hợp nhiều bằng chứng độc lập.

Nếu email vừa được thay, không nên lập tức cho phép nó trở thành kênh recovery duy nhất mà không có xác minh và thời gian/biện pháp bảo vệ phù hợp. Có thể thông báo kênh cũ, yêu cầu step-up, áp dụng delay cho thao tác nhạy cảm và cung cấp đường báo cáo.

### 10.3. Recovery thủ công và helpdesk

Helpdesk không được yêu cầu người dùng đọc password, OTP hoặc recovery code. Nhân viên cần quy trình xác minh và phân quyền rõ, audit đầy đủ, kiểm soát hành động rủi ro cao và cơ chế phê duyệt bổ sung nếu cần. Thông tin công khai như ngày sinh, tên trường, chức vụ hoặc email không đủ làm bằng chứng duy nhất.

## 11. Tài khoản dùng SSO và mật khẩu do IdP quản lý

Với tài khoản liên kết OIDC/SAML, ứng dụng relying party thường không lưu password của IdP. Người dùng cần đổi password ở **IdP có thẩm quyền**. RP có thể hiển thị đường dẫn hoặc hướng dẫn tới cổng quản lý tài khoản của IdP, nhưng không nên thu password IdP trong form nội bộ hoặc tự cập nhật một password cục bộ gây nhầm lẫn.

Nếu ứng dụng hỗ trợ cả local password và SSO, cần mô hình hóa rõ:

- Account có local credential, federated identity hay cả hai?
- Chính sách cho phép dùng phương thức nào để đăng nhập?
- Việc đổi local password có ảnh hưởng đến SSO không? Thông thường không.
- Khi IdP thay đổi password, RP nhận tín hiệu nào và có cần xử lý session hiện tại không?
- Khi gỡ liên kết IdP, account còn phương thức đăng nhập/recovery hợp lệ nào?

Ánh xạ liên kết nên dựa trên issuer + subject và phạm vi tenant phù hợp, không chỉ email. Đổi password ở IdP không làm thay đổi identity key nội bộ.

## 12. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ cần session là đổi được password | Session bị đánh cắp có thể chiếm tài khoản lâu dài | Recent authentication/step-up cho thao tác nhạy cảm |
| Chỉ kiểm tra ở frontend | Request trực tiếp có thể bỏ qua policy | Validate và authorize toàn bộ ở server |
| Lưu password mới plaintext hoặc hash nhanh | Rủi ro lộ dữ liệu và offline guessing | Argon2id hoặc KDF chuyên dụng, salt riêng |
| Đổi password qua GET hoặc URL | Lộ dữ liệu qua log/history/referrer, CSRF | POST/API phù hợp, TLS, CSRF protection |
| Không xử lý session cũ | Kẻ tấn công giữ phiên sau khi password đổi | Thu hồi phiên/token theo policy rõ |
| Reset token không hết hạn/không dùng một lần | Có thể replay hoặc chiếm account về sau | Token entropy cao, TTL, purpose binding, atomic consume |
| Đổi email rồi lập tức dùng làm recovery | Kênh vừa bị chiếm có thể tiếp quản account | Step-up, thông báo kênh cũ, kiểm soát thay đổi |
| Bắt đổi password định kỳ vô điều kiện | Người dùng dễ tạo biến thể yếu và ghi chép kém an toàn | Đổi khi có bằng chứng compromise, password lộ hoặc yêu cầu cụ thể |
| Không audit thay đổi credential | Khó điều tra account takeover | Event tối thiểu, không log secret |
| Tự xử lý password của IdP | Mở rộng bề mặt thu thập credential và phá trust boundary | Chuyển người dùng tới IdP quản lý password |
| Hai request đồng thời ghi đè | Trạng thái verifier/session không nhất quán | Transaction, credential version, concurrency control |

## 13. Ví dụ xuyên suốt: nền tảng học tập

Một học viên dùng password + TOTP để đăng nhập. Họ đang có session trên laptop và muốn đổi password vì nghi ngờ password cũ đã bị lộ ở một dịch vụ khác.

### 13.1. Luồng đổi bình thường

1. Học viên vào trang bảo mật qua HTTPS.
2. Server xác minh session và yêu cầu xác thực lại bằng password hiện tại; do policy của tài khoản, hệ thống yêu cầu TOTP bổ sung.
3. Server tạo transaction **CHANGE_PASSWORD** gắn subject, tenant, session, hạn và phương thức cần thiết.
4. Người dùng hoàn tất xác thực lại; server đánh dấu transaction đã đạt assurance.
5. Người dùng gửi password mới; server kiểm tra chính sách, kiểm tra password đã lộ và tạo verifier mới.
6. Transaction database thay verifier và tăng credential version; session khác bị thu hồi theo policy, session hiện tại được cấp ID mới.
7. Hệ thống ghi audit event, thông báo tới email đã đăng ký và hiển thị thời điểm thay đổi.

### 13.2. Nếu session đã bị chiếm

Nếu kẻ tấn công chỉ có session cookie nhưng không có password hiện tại hoặc yếu tố step-up, họ không thể tự thay password. Nếu họ đã chiếm cả email/điện thoại recovery hoặc authenticator, threat model cần xử lý như account recovery compromise: xác minh thêm, thu hồi phiên, kiểm tra credential mới được thêm và có thể yêu cầu hỗ trợ theo quy trình mạnh hơn.

### 13.3. Nếu người dùng quên password

Họ chuyển sang recovery flow. Server không yêu cầu password hiện tại; thay vào đó xác minh token/method khôi phục, gắn đúng account và purpose, giới hạn số lần thử, tiêu thụ token một lần, cập nhật verifier và xử lý session/token hiện hữu. Đây là **password reset**, không phải change password thông thường.

## 14. Kiểm thử password change

Test plan cần bao gồm cả trạng thái hợp lệ và hành vi tấn công trong môi trường thử nghiệm.

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Authentication | Session hết hạn hoặc account bị khóa | Từ chối đổi password, không thay verifier |
| Reauthentication | Password hiện tại sai | Từ chối; không tiết lộ verifier hoặc account detail |
| Step-up | Gửi cờ client nói MFA đã qua nhưng server chưa xác minh | Từ chối |
| CSRF | Request đổi password từ origin không được phép | Bị chặn theo policy |
| Policy | Password mới phổ biến/đã lộ hoặc quá giới hạn | Từ chối với thông báo hữu ích, không log password |
| Hashing | Kiểm tra verifier sau khi đổi | Có salt mới, KDF và tham số đúng policy; không có plaintext |
| Concurrency | Hai request đổi password đồng thời | Xử lý nhất quán; không có ghi đè ngoài ý muốn |
| Session | Password đổi thành công | Session/token khác bị xử lý đúng policy |
| Replay | Dùng lại reauthentication transaction đã tiêu thụ | Từ chối |
| Reset | Reset token hết hạn/sai account/sai purpose/đã dùng | Từ chối |
| Recovery | Đổi email rồi dùng ngay làm recovery không qua policy | Bị giới hạn/step-up theo policy |
| Notification | Password thay đổi | Thông báo được gửi; không chứa password hoặc token |
| Audit | Bật log, trace và crash reporting | Không xuất hiện password/hash/token/cookie nguyên dạng |
| Federated | User chỉ có SSO yêu cầu đổi local password | Hướng tới IdP hoặc xử lý theo chính sách; không tự tạo credential trái phép |

### 14.1. Kiểm tra bất biến bảo mật

Sau mọi test thất bại, phải bảo đảm:

- Password verifier cũ vẫn còn hiệu lực;
- Không phát hành session mới;
- Không thu hồi session hợp lệ ngoài ý muốn;
- Không tiêu thụ nhầm challenge hoặc recovery token;
- Không phát sinh audit event “password changed” giả;
- Không rò rỉ bí mật vào log hoặc response.

Sau test thành công, xác minh password mới đăng nhập được, password cũ không còn được chấp nhận, trạng thái phiên/token đúng policy và thông báo/audit có mặt.

## 15. Checklist đưa password change vào production

1. **Đúng loại luồng:** change, reset, recovery, admin reset và federated password change có được phân biệt không?
2. **Xác thực lại:** thao tác có recent authentication hoặc step-up phù hợp với mức rủi ro không?
3. **Request:** TLS/hostname đúng, POST/API phù hợp, chống CSRF, không có secret trong URL?
4. **Policy password:** đủ dài, hỗ trợ password manager, kiểm tra mật khẩu phổ biến/đã lộ, giới hạn và Unicode nhất quán?
5. **Verifier:** KDF chuyên dụng, salt riêng, tham số phù hợp, pepper được quản lý nếu dùng?
6. **Atomicity:** transaction/version ngăn request đồng thời và retry gây ghi đè không?
7. **Session/token:** phiên khác, refresh token, access token và session hiện tại được xử lý với hiệu lực thu hồi rõ ràng?
8. **Credential khác:** passkey, MFA, certificate, API key và linked IdP có được đánh giá khi nghi ngờ compromise?
9. **Recovery:** reset token có entropy, TTL, purpose binding, một lần; helpdesk không thể bỏ qua MFA tùy tiện?
10. **Notification/audit:** người dùng được thông báo; event không chứa password, hash, OTP, cookie hay token?
11. **Federation:** password do IdP quản lý có được đổi đúng tại IdP?
12. **Testing/operations:** có test thất bại, replay, CSRF, concurrency, thu hồi session và quy trình incident response?

## 16. Bài tập vận dụng

Một ứng dụng cho phép người dùng đổi password khi đang có session. API chỉ kiểm tra cookie, nhận currentPassword và newPassword, sau đó lưu SHA-256(newPassword) trong database. Hệ thống không có CSRF token, không thu hồi session khác và không gửi thông báo. Nếu người dùng quên password, support agent có thể cập nhật password trực tiếp sau khi hỏi ngày sinh và tên trường.

**Yêu cầu:**

1. Chỉ ra ít nhất **tám rủi ro** trong hai luồng change và recovery.
2. Vẽ lại sequence diagram cho change password có xác thực lại và step-up.
3. Đề xuất cách lưu verifier và cập nhật nguyên tử.
4. Thiết kế chính sách thu hồi session/token và thông báo sau thay đổi.
5. Thiết kế recovery/helpdesk để không dựa vào dữ liệu dễ đoán và không trở thành đường vòng MFA.
6. Viết test chứng minh session bị chiếm không thể tự đổi password, CSRF bị chặn và token recovery không dùng lại được.

**Gợi ý đối chiếu:** cần recent authentication; password hash bằng KDF chuyên dụng có salt riêng; chống CSRF; session/token revocation; audit và thông báo; recovery token một lần có hạn, ràng buộc account/purpose; helpdesk có quy trình xác minh và phê duyệt; không yêu cầu người dùng tiết lộ password/OTP cho nhân viên.

## 17. Ghi nhớ

- **Password change** là thay credential trong một tài khoản đang truy cập; **password reset/recovery** là luồng riêng dành cho trường hợp không thể chứng minh password hiện tại.
- Session hợp lệ không luôn đủ cho thao tác nhạy cảm. Cần **xác thực lại gần đây** và gắn kết quả với đúng subject, mục đích, thời điểm và giao dịch.
- Password mới phải được kiểm tra theo chính sách và lưu dưới dạng **password verifier** bằng KDF chuyên dụng, salt riêng; không lưu plaintext hoặc hash nhanh.
- Đổi password cần quyết định rõ về **session, refresh token, access token và các credential khác**; thay password không tự động thu hồi mọi thứ.
- Recovery, email/SMS, helpdesk và liên kết IdP đều có thể trở thành đường vòng. Bảo vệ chúng tương xứng với giá trị tài khoản.
- Audit và thông báo giúp phát hiện thay đổi trái phép, nhưng không được chứa password, OTP, recovery code hoặc token nguyên dạng.

Một quy trình password change an toàn chứng minh đúng người có quyền thay đổi, lưu verifier mới đúng cách, xử lý phiên nhất quán và giúp chủ tài khoản nhận biết thay đổi bất thường. Những điều kiện này giữ cho thao tác tưởng như đơn giản không trở thành điểm chiếm quyền trong vòng đời xác thực.
