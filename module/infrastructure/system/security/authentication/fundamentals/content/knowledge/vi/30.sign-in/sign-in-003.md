# Credential check — Kiểm tra credential trong quy trình đăng nhập

> **Chương:** Đăng nhập  
> **Chủ đề:** Credential check  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào bước kiểm tra credential trong luồng sign-in: tìm đúng account, xác minh bằng chứng theo loại credential, kiểm tra trạng thái và policy, chống dò thông tin đăng nhập và chỉ chuyển sang bước tiếp theo khi kết quả được xác minh.

## 1. Credential check là gì?

**Credential check** là bước verifier kiểm tra bằng chứng đăng nhập mà client gửi có hợp lệ đối với một account và một giao thức xác thực cụ thể hay không. Bằng chứng có thể là password, passkey assertion, OTP, certificate-based proof hoặc một credential khác được hệ thống hỗ trợ.

Ví dụ, Mai nhập email và password vào cổng học tập. Server dùng email đã chuẩn hóa theo quy tắc định danh để tìm account, lấy password hash đã lưu, rồi gọi password-hashing library để kiểm tra password vừa nhập. Nếu password hợp lệ, server vẫn phải kiểm tra account có active không, credential có bị thu hồi không và policy có yêu cầu MFA/step-up không. Chỉ khi toàn bộ điều kiện đăng nhập bắt buộc hoàn tất, hệ thống mới tạo phiên đã xác thực.

Credential check không chỉ là câu lệnh so sánh hai chuỗi. Đây là một bước trong chuỗi tin cậy: nhận request, xác định account, xác minh bằng chứng, áp dụng policy, ghi nhận kết quả và chuyển sang trạng thái xác thực phù hợp.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt identifier, credential, proof và authenticated principal.
2. Mô tả pipeline kiểm tra password, passkey, OTP và client certificate.
3. Giải thích vì sao password phải được hash bằng password-hashing function và không được lưu plaintext.
4. Thiết kế kiểm tra account/credential state, MFA gating và pre-authentication state.
5. Ngăn user enumeration, brute force, password spraying và credential stuffing.
6. Hiểu timing behavior, rate limiting, retry, audit và thông báo lỗi.
7. Phân biệt authentication thành công với authorization và session creation.
8. Xây dựng test cho credential hợp lệ, sai, bị thu hồi, hết hạn và các tình huống abuse.

## 2. Identifier, credential và proof

Ba khái niệm này cần được tách biệt:

- **Identifier:** thông tin giúp hệ thống tìm account hoặc credential record, ví dụ username, email, account handle hoặc credential ID.
- **Credential:** vật/secret hoặc khóa đã được đăng ký để chứng minh quyền kiểm soát, ví dụ password verifier, passkey public key, OTP seed, certificate hoặc khóa phần cứng.
- **Proof:** bằng chứng được tạo trong lần đăng nhập hiện tại, ví dụ password vừa nhập, WebAuthn assertion, OTP code hoặc chữ ký trong TLS handshake.

Identifier không phải bí mật xác thực. Biết email hoặc username của Mai không chứng minh người gửi request là Mai. Ngược lại, credential ID của một passkey có thể được dùng để tìm public key, nhưng verifier vẫn cần kiểm tra chữ ký challenge và các thuộc tính giao thức.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Identifier | Tìm account/credential | `mai@example.edu` |
| Credential record | Dữ liệu verifier dùng để xác minh | Argon2id hash, WebAuthn public key, OTP secret reference |
| Proof | Bằng chứng trong request hiện tại | Password input, authenticator assertion, OTP |
| Authentication result | Kết quả verifier theo policy | Password hợp lệ, passkey assertion hợp lệ |
| Principal | Chủ thể nội bộ được xác định sau xác thực | Account ID của Mai trong tenant phù hợp |

Không đưa identifier vào nơi yêu cầu proof. Không coi việc account tồn tại, email đã xác minh hoặc thiết bị đã biết là credential check thành công.

## 3. Vị trí credential check trong sign-in pipeline

Một luồng đăng nhập thường gồm nhiều bước. Credential check chỉ là một trong các bước; nó không tự cấp session hoặc quyền truy cập.

~~~mermaid
flowchart TD
    A["Nhận sign-in request"] --> B["Parse input và áp dụng rate limit"]
    B --> C["Chuẩn hóa identifier theo policy"]
    C --> D["Tìm account và credential record"]
    D --> E["Xác minh proof theo credential type"]
    E --> F{"Proof hợp lệ?"}
    F -- "Không" --> X["Từ chối chung + ghi nhận abuse signal"]
    F -- "Có" --> G["Kiểm tra account và credential state"]
    G --> H{"Account/credential được phép?"}
    H -- "Không" --> X
    H -- "Có" --> I{"Có yếu tố/policy bắt buộc khác?"}
    I -- "Có" --> J["Chuyển sang pre-auth / MFA challenge"]
    J --> K{"MFA/step-up đạt?"}
    K -- "Không" --> X
    K -- "Có" --> L["Tạo authenticated principal"]
    I -- "Không" --> L
    L --> M["Tạo session mới và áp dụng authorization"]
~~~

Thứ tự chi tiết có thể thay đổi theo credential type và kiến trúc, nhưng các nguyên tắc cần giữ:
- giới hạn request trước khi thực hiện thao tác tốn tài nguyên;
- xác minh proof bằng verifier phù hợp;
- không nâng trạng thái account khi chỉ có identifier;
- không bỏ qua account/credential status;
- không cấp session đầy đủ trước khi các yếu tố bắt buộc hoàn tất;
- authorization vẫn được thực hiện riêng cho từng resource/action.

## 4. Tra cứu account và credential record

Sau khi parse request, server dùng identifier để tìm account theo quy tắc đã định. Quy tắc chuẩn hóa identifier cần nhất quán giữa enrollment, login, recovery và account linking.

### Chuẩn hóa identifier

- Với username, định nghĩa rõ chữ hoa/chữ thường, ký tự Unicode và khoảng trắng.
- Với email, xử lý domain và local-part theo policy có chủ đích; không tự ý áp dụng các quy tắc riêng của một nhà cung cấp email cho mọi địa chỉ.
- Không dùng giá trị do client khai làm account ID nội bộ.
- Nếu một identifier có thể trỏ tới nhiều account/tenant, yêu cầu thêm tenant context đã được xác minh hoặc quy trình chọn account rõ ràng.
- Không tự động gộp account chỉ vì email trùng.

Password cần được xử lý riêng: không trim, không đổi chữ hoa/thường và không cắt ngắn âm thầm. Nếu hệ thống áp dụng Unicode normalization như NFC, phải định nghĩa và áp dụng nhất quán khi tạo credential và khi xác minh. Giới hạn độ dài/byte cần đủ lớn để hỗ trợ password manager và passphrase, đồng thời tránh input quá lớn gây DoS.

### Lookup không được tiết lộ account tồn tại

Response cho “account không tồn tại”, “password sai” hoặc “account bị khóa” thường nên có thông báo công khai tương tự, ví dụ: “Thông tin đăng nhập không hợp lệ hoặc không thể hoàn tất đăng nhập.” Internal log có thể ghi reason code riêng với quyền truy cập phù hợp.

Không trả thông báo “email này chưa đăng ký” ở màn hình đăng nhập nếu điều đó giúp attacker thu thập danh sách account. Các flow recovery có thể cần thông báo trung tính như “Nếu tài khoản tồn tại, hướng dẫn sẽ được gửi qua kênh đã đăng ký.”

## 5. Kiểm tra password an toàn

Password không được lưu plaintext và cũng không nên dùng hash nhanh như SHA-256 đơn thuần để lưu password. Server nên lưu password verifier được tạo bằng **password-hashing function** có salt riêng và cost có thể điều chỉnh, ví dụ Argon2id; bcrypt hoặc PBKDF2 có thể phù hợp trong một số môi trường theo policy và yêu cầu tương thích.

### Quy trình kiểm tra

1. Nhận password qua TLS; không ghi vào log, trace hoặc analytics.
2. Tra password verifier theo account.
3. Gọi thư viện password-hashing đã được kiểm chứng để verify password input với hash lưu trữ.
4. Thư viện đọc salt và parameters từ encoded verifier, tính lại và so sánh theo cách an toàn.
5. Nếu thành công, kiểm tra account/credential state và policy tiếp theo.
6. Nếu hash dùng parameters cũ, có thể rehash sau lần đăng nhập thành công theo policy.
7. Không bao giờ giải mã password từ database; thiết kế đúng không có ciphertext password để giải mã.

### Salt và work factor

- **Salt:** giá trị ngẫu nhiên riêng cho từng password verifier, giúp tránh hash giống nhau và rainbow-table reuse.
- **Work factor / parameters:** làm quá trình thử password tốn tài nguyên hơn đối với attacker; cần benchmark trên hạ tầng thật.
- **Pepper (nếu dùng):** secret bổ sung được lưu tách khỏi database, ví dụ secret manager/HSM; cần quy trình rotation và xử lý khi pepper bị lộ.

Ví dụ định dạng khái niệm:

~~~text
$argon2id$v=19$m=65536,t=3,p=1$<salt>$<derived-hash>
~~~

Thông số ở đây chỉ minh họa, không phải cấu hình bắt buộc. Hãy chọn parameters theo hướng dẫn hiện hành và benchmark để giữ thời gian verify chấp nhận được dưới tải hợp lệ. Work factor quá thấp làm giảm chi phí tấn công; quá cao có thể tạo cơ hội DoS khi server bị gửi nhiều request.

### Verify bằng thư viện, không tự viết thuật toán

Pseudocode:

~~~java
boolean verifyPassword(String submittedPassword, PasswordVerifier stored) {
    // Library parses algorithm, salt and parameters from stored verifier.
    return passwordHashingLibrary.verify(
        submittedPassword,
        stored.encodedHash());
}
~~~

Không dùng `MessageDigest.getInstance("SHA-256")` để tự hash password rồi so sánh. Không dùng phép so sánh string thông thường với hash tự xây dựng. Thư viện password-hashing chuyên dụng phải quản lý encoding, parameters và comparison đúng cách.

## 6. Password policy và xử lý input

Password policy ảnh hưởng trực tiếp tới credential check. Một số nguyên tắc:

- Cho phép password dài và hỗ trợ passphrase.
- Không cắt ngắn password âm thầm; nếu có giới hạn, phải công bố và xử lý nhất quán.
- Không ép đổi password định kỳ nếu không có dấu hiệu compromise hoặc yêu cầu phù hợp.
- Chặn password phổ biến, dễ đoán hoặc xuất hiện trong danh sách breached-password theo cách bảo vệ riêng tư.
- Không áp đặt quy tắc thành phần phức tạp khiến người dùng chọn mẫu dễ đoán hơn.
- Hỗ trợ password manager, paste và autofill.
- Không trim hoặc case-fold password.
- Giới hạn kích thước request để tránh tiêu thụ bộ nhớ/CPU quá mức.
- Dùng encoding và normalization policy rõ ràng cho Unicode.

Password đã nhập sai phải thất bại mà không làm lộ verifier, salt hoặc thông tin nội bộ. Password reset phải tạo verifier mới, tăng credential/session version hoặc thu hồi session/token cũ theo policy.

## 7. Passkey/WebAuthn credential check

Với passkey, client không gửi private key hoặc password cho server. RP lưu public key và credential metadata khi đăng ký. Trong lần đăng nhập, RP phát challenge ngẫu nhiên; authenticator ký dữ liệu assertion bằng private key.

Verifier thường kiểm tra:
- credential ID có thuộc account hoặc được discoverable theo flow đã cấu hình;
- challenge khớp và chưa hết hạn/chưa dùng;
- origin khớp origin được phép;
- RP ID hash khớp RP ID;
- chữ ký hợp lệ với public key đã đăng ký;
- user presence/user verification flags theo policy;
- loại credential, trạng thái và binding đúng account;
- sign counter nếu có, nhưng không dựa duy nhất vào counter vì một số authenticator đồng bộ hoặc không cung cấp counter tăng đơn điệu.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant RP as Relying Party
    participant A as Authenticator
    B->>RP: Bắt đầu sign-in
    RP->>RP: Tạo challenge + allowCredentials/policy
    RP-->>B: PublicKeyCredentialRequestOptions
    B->>A: navigator.credentials.get()
    A-->>B: Assertion + authenticator data + signature
    B->>RP: Gửi assertion
    RP->>RP: Verify challenge, origin, RP ID, signature, flags
    RP->>RP: Resolve credential -> account
    RP-->>B: Authentication result
~~~

WebAuthn assertion hợp lệ chứng minh authenticator đã ký challenge trong ngữ cảnh RP theo giao thức. Nó không tiết lộ biometric template cho server và không tự chứng minh mọi thuộc tính của thiết bị đều an toàn. Nếu policy yêu cầu User Verification, RP phải kiểm tra UV flag thay vì suy từ việc người dùng nhìn thấy màn hình biometric.

## 8. OTP và authenticator code check

OTP có thể là TOTP, HOTP hoặc mã gửi qua một kênh như SMS/email theo kiến trúc. Verifier phải xác định đúng loại credential và áp dụng quy tắc tương ứng.

Với TOTP:
- server lưu secret seed bảo vệ ở trạng thái nghỉ;
- tính mã theo thời gian và bước thời gian đã cấu hình;
- cho phép clock drift giới hạn;
- không chấp nhận mã đã dùng lại trong cửa sổ nếu policy yêu cầu chống replay;
- rate limit số lần thử;
- không log mã hoặc seed.

Với HOTP, verifier quản lý counter và cập nhật counter một cách nguyên tử để tránh một mã được chấp nhận nhiều lần do request đồng thời.

Với OTP qua SMS/email:
- mã có thời hạn ngắn, dùng một lần và gắn với đúng giao dịch;
- kiểm tra đúng account, purpose và challenge;
- giới hạn số lần gửi và nhập;
- không coi SMS là phương thức chống phishing;
- có biện pháp chống SIM swap, mailbox compromise và gửi mã hàng loạt.

Một OTP đúng không tự động đồng nghĩa toàn bộ MFA policy đã đạt. Cần kiểm tra yếu tố khác, giao dịch, trạng thái account và assurance cần thiết.

## 9. Client certificate credential check

Trong client-certificate authentication, client trình bày certificate chain và chứng minh quyền kiểm soát private key trong TLS handshake hoặc protocol tương ứng.

Verifier cần:
1. Xây dựng chain tới trust anchor được cấu hình.
2. Kiểm tra chữ ký, thời hạn và constraints của certificate path.
3. Kiểm tra Key Usage/Extended Key Usage phù hợp mục đích client authentication.
4. Kiểm tra SAN/subject và ánh xạ sang device/workload/account theo policy.
5. Kiểm tra trạng thái thu hồi theo policy (CRL/OCSP hoặc cơ chế được cấu hình).
6. Xác minh proof of possession của private key qua handshake/protocol.
7. Kiểm tra principal, account, tenant và authorization riêng.

Không tin một certificate chỉ vì client gửi file certificate; certificate chứa public key, không chứng minh client giữ private key nếu không có proof-of-possession. Certificate hợp lệ cũng không tự cấp mọi quyền API.

## 10. Kiểm tra trạng thái account và credential

Sau khi proof được xác minh, verifier cần kiểm tra account và credential có được phép dùng không.

Trạng thái có thể gồm:
- account active, suspended, disabled hoặc pending;
- credential active, expired, revoked hoặc pending replacement;
- password reset bắt buộc hoặc credential rotation cần hoàn tất;
- account yêu cầu MFA enrollment;
- membership tenant còn hiệu lực;
- account bị khóa tạm thời do abuse;
- credential bị đánh dấu compromised;
- user đã rời tổ chức hoặc bị deprovision.

Không nên kiểm tra mỗi password hash rồi bỏ qua account disabled. Ngược lại, không nên tiết lộ account bị khóa trong public error response. Internal policy cần phân biệt reason để audit, hỗ trợ và incident response.

### Credential version và revoke

Khi password đổi hoặc passkey bị gỡ, hệ thống có thể tăng credential/session version, revoke credential record hoặc thu hồi session/token liên quan. Mỗi verifier cần kiểm tra trạng thái hiện hành theo SLA. Nếu cache credential quá lâu, một credential đã revoke có thể vẫn được chấp nhận ở instance khác.

## 11. User enumeration và thông báo lỗi

User enumeration xảy ra khi attacker có thể phân biệt account tồn tại hay không thông qua response, timing hoặc hành vi khác.

Các nguồn rò rỉ:
- “Email không tồn tại” khác “password sai”.
- Account bị khóa có response khác account bình thường.
- Endpoint recovery chỉ gửi email khi account tồn tại nhưng trả thông báo khác nhau.
- Thời gian phản hồi quá khác nhau giữa account có hash và account không tồn tại.
- HTTP status, redirect, response size hoặc rate limit khác biệt.

Kiểm soát:
- dùng thông báo public chung cho lỗi credential;
- chuẩn hóa HTTP status/response shape khi phù hợp;
- với account không tồn tại, có thể thực hiện dummy password hash verification để giảm chênh lệch timing, sau khi rate limit và giới hạn tải;
- không tiết lộ trạng thái account trong log phía client;
- tránh CAPTCHA hoặc challenge chỉ xuất hiện cho một nhánh có thể làm lộ trạng thái;
- kiểm thử response và timing ở quy mô phù hợp.

Không thể bảo đảm timing hoàn toàn giống nhau trong hệ thống phân tán. Mục tiêu là giảm tín hiệu dễ khai thác, tránh khác biệt rõ ràng và kết hợp rate limiting, monitoring.

## 12. Chống brute force, password spraying và credential stuffing

Ba kiểu abuse thường gặp:

- **Brute force:** thử nhiều password cho một account.
- **Password spraying:** thử một số password phổ biến trên nhiều account.
- **Credential stuffing:** dùng cặp username/password bị lộ từ dịch vụ khác.

Không có một giới hạn theo IP nào đủ. Attacker có thể phân tán request qua nhiều IP hoặc proxy; nhiều người dùng hợp lệ cũng có thể chung NAT.

Các biện pháp:
- rate limit theo nhiều chiều: account, IP/network, device/session signal và toàn hệ thống;
- progressive delay hoặc cooldown có giới hạn;
- phát hiện password spraying qua nhiều account;
- kiểm tra breached-password tại enrollment/reset;
- MFA và passkey để giảm tác động password compromise;
- CAPTCHA hoặc proof-of-work chỉ như biện pháp bổ sung theo risk, không phải lớp duy nhất;
- phát hiện bot và bất thường với privacy safeguards;
- thông báo đăng nhập đáng ngờ và hỗ trợ revoke session;
- không khóa account vĩnh viễn chỉ sau vài lần sai vì attacker có thể gây DoS cho nạn nhân.

### Rate limit phải bảo vệ cả verifier

Password hashing có chủ đích tốn CPU/RAM. Nếu không rate limit trước khi verify, attacker có thể gửi lượng lớn request và làm cạn tài nguyên. Tuy nhiên, rate limit cần tránh cho attacker khóa account bằng cách cố tình gửi sai nhiều lần. Dùng kết hợp throttling theo account, network, global capacity và risk signals; thiết kế cooldown, queue hoặc adaptive challenge phù hợp.

## 13. Timing, constant-time comparison và side channels

Khi so sánh MAC, OTP hoặc secret-derived values, cần dùng primitive comparison constant-time phù hợp để tránh thời gian phản hồi phụ thuộc vị trí byte khác nhau. Với password, hãy dùng password-hashing library có cơ chế verify phù hợp thay vì tự so sánh hash.

Timing side channel có thể xuất hiện khi:
- account không tồn tại bị trả lời ngay, còn account có password hash phải tính Argon2id;
- account bị khóa được xử lý khác biệt rõ;
- passkey credential lookup có đường code khác nhau;
- certificate errors làm lộ thông tin chi tiết.

Các biện pháp:
- thực hiện dummy hash khi phù hợp để giảm account-existence timing gap;
- giới hạn tải trước thao tác tốn tài nguyên;
- giữ response công khai nhất quán;
- không gửi stack trace hoặc lý do verifier chi tiết cho client;
- ghi reason code nội bộ;
- kiểm tra constant-time cho các phép so sánh secret/MAC mà giao thức yêu cầu.

Constant-time không có nghĩa toàn bộ endpoint phải chạy đúng cùng số millisecond. Hãy dùng primitive phù hợp, giảm chênh lệch có ý nghĩa và bảo vệ các đường dữ liệu nhạy cảm.

## 14. MFA gating và pre-authentication state

Nếu policy yêu cầu password + MFA, password đúng chỉ chứng minh yếu tố đầu tiên. Server có thể tạo một pre-authentication transaction giới hạn để giữ trạng thái giữa các bước, nhưng chưa được cấp session có đầy đủ quyền.

Pre-auth state nên:
- có ID ngẫu nhiên, thời hạn ngắn và gắn với browser/client transaction;
- lưu account và kết quả yếu tố đã xác minh ở server;
- chỉ truy cập endpoint tiếp tục MFA, không truy cập API nghiệp vụ;
- giới hạn retry và chống replay;
- bị hủy khi hết hạn, thất bại hoặc người dùng hủy;
- được thay bằng session ID mới sau khi toàn bộ policy đạt.

Không tin `mfaCompleted=true` do client gửi. MFA result phải được verifier xác minh và gắn với đúng transaction/account. Nếu passkey đã đáp ứng policy, không cần ép một yếu tố bổ sung chỉ vì tên credential; nhưng RP phải kiểm tra flags và assurance theo policy.

## 15. Credential check không phải authorization

Credential check xác minh bằng chứng và xác định principal. Authorization quyết định principal có được phép thực hiện hành động cụ thể không.

Ví dụ:
- Password của nhân viên hợp lệ nhưng account đã bị deprovision: không được tạo session.
- Passkey assertion hợp lệ của sinh viên: có thể đăng nhập, nhưng không được xem hồ sơ của sinh viên khác.
- Client certificate hợp lệ của workload: chỉ được gọi API và scope đã cấp.
- OTP đúng: không tự cấp quyền quản trị hoặc xác nhận giao dịch chưa được hiển thị.

Sau authentication, mỗi request cần kiểm tra session/token, account status, tenant membership và quyền trên resource. Không nhúng role do client khai vào authentication result.

## 16. Logging và audit an toàn

Audit cần hỗ trợ điều tra mà không biến log thành kho credential.

Có thể ghi:
- correlation/request ID;
- account ID nội bộ sau khi xác định;
- credential type và credential reference opaque;
- thời điểm và kết quả authentication;
- reason code nội bộ (invalid proof, revoked credential, account disabled, throttled);
- IP/network/device risk signal theo policy;
- MFA challenge/result và assurance context;
- session ID reference không phải raw secret;
- thay đổi credential và sự kiện revoke.

Không log:
- password hoặc password hash;
- OTP, TOTP seed hoặc recovery code;
- private key, client secret hoặc raw authenticator response nếu chứa dữ liệu nhạy cảm;
- raw session cookie, access token hoặc refresh token;
- toàn bộ request body nếu có credential.

Dữ liệu audit cần access control, retention và integrity protection. Không dùng log reason chi tiết làm public error message.

## 17. Pseudocode credential check tổng quát

Ví dụ sau minh họa cấu trúc điều phối, không phải một verifier dùng chung cho mọi loại credential:

~~~java
SignInResult checkCredential(SignInRequest request) {
    rateLimiter.requireAllowed(
        request.identifier(),
        request.networkContext(),
        request.deviceRiskSignals());

    Identifier identifier = identifierPolicy.normalize(request.identifier());

    Account account = accountRepository.findForSignIn(identifier)
        .orElse(null);

    CredentialRecord credential =
        account == null ? null
                        : credentialRepository.findActiveForMethod(
                              account.id(), request.credentialType());

    boolean proofValid;
    if (credential == null) {
        // Unknown account/credential: keep the public result generic.
        // For password, perform a bounded dummy verification to reduce timing gaps.
        proofValid = request.credentialType() == CredentialType.PASSWORD
            && passwordLibrary.verify(
                request.password(), dummyPasswordVerifier().encodedValue());
    } else if (request.credentialType() == CredentialType.PASSWORD) {
        proofValid = passwordLibrary.verify(
            request.password(), credential.passwordVerifier().encodedValue());
    } else if (request.credentialType() == CredentialType.PASSKEY) {
        proofValid = webAuthnVerifier.verifyAssertion(
            request.passkeyAssertion(), credential);
    } else if (request.credentialType() == CredentialType.OTP) {
        proofValid = otpVerifier.verifyAndConsume(
            request.otp(), credential, request.transaction());
    } else {
        proofValid = certificateVerifier.verify(
            request.clientCertificate(), request.tlsContext(), credential);
    }

    if (account == null || credential == null || !proofValid) {
        audit.recordGenericFailure(request.correlationId());
        throw genericSignInFailure();
    }

    accountPolicy.requireActive(account);
    credentialPolicy.requireUsable(credential);

    AuthenticationResult result =
        authenticationPolicy.evaluate(account, credential, request);

    if (result.requiresAdditionalFactor()) {
        return preAuthService.createRestrictedTransaction(result);
    }

    return sessionService.createFreshAuthenticatedSession(result);
}
~~~

Đây là pseudocode khái niệm. Trong production:
- dùng endpoint và parser riêng cho từng credential type;
- không gọi password verifier với giá trị dummy không tương thích;
- xử lý passkey assertion theo đầy đủ WebAuthn rules;
- kiểm tra OTP counter/replay atomically;
- xác minh certificate chain và proof-of-possession ở TLS layer phù hợp;
- không dùng một `credential != null` check chung thay cho state/expiry/revocation;
- tránh timing và error behavior làm lộ account;
- bảo đảm account/credential status không thay đổi giữa verify và session commit mà không được phát hiện.

## 18. Kiểm thử credential check

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Identifier và password hợp lệ | Proof được xác minh; tiếp tục account/policy check. |
| Identifier đúng, password sai | Từ chối với thông báo công khai chung. |
| Account không tồn tại | Không lộ account existence; không tạo session. |
| Account disabled nhưng password đúng | Từ chối; internal reason được audit. |
| Credential revoked nhưng proof cũ hợp lệ | Từ chối theo credential status. |
| Password verifier parameters cũ | Verify theo metadata; rehash theo policy sau thành công. |
| Password cực dài vượt giới hạn request | Từ chối an toàn trước khi tiêu thụ tài nguyên lớn. |
| Password có Unicode | Xử lý đúng normalization policy đã định nghĩa. |
| Hash database bị lộ | Không thể dùng hash nhanh/plaintext; parameters phù hợp làm tăng chi phí offline guessing. |
| Password spraying trên nhiều account | Phát hiện/rate limit theo nhiều chiều. |
| Nhiều request sai từ nhiều IP | Global/account risk control vẫn áp dụng. |
| Unknown account timing | Dummy verification hoặc biện pháp tương đương giảm chênh lệch rõ. |
| WebAuthn challenge sai | Từ chối assertion. |
| WebAuthn origin hoặc RP ID sai | Từ chối assertion. |
| WebAuthn signature sai | Từ chối assertion. |
| UV bắt buộc nhưng UV flag không có | Từ chối theo policy. |
| WebAuthn credential bị revoke | Từ chối. |
| TOTP hợp lệ lần đầu | Chấp nhận nếu transaction/policy đạt. |
| TOTP replay trong cửa sổ đã dùng | Từ chối theo replay policy. |
| HOTP counter dùng đồng thời | Chỉ một lần tiêu thụ counter thành công. |
| OTP hết hạn hoặc sai purpose | Từ chối. |
| Certificate chain không tin cậy | Từ chối. |
| Certificate hết hạn hoặc EKU sai | Từ chối. |
| Certificate revoked | Từ chối theo revocation policy. |
| Certificate hợp lệ nhưng private key không được chứng minh | Từ chối proof-of-possession. |
| Password đúng nhưng MFA chưa hoàn tất | Chỉ pre-auth state giới hạn, không tạo session đầy đủ. |
| Client gửi `mfaCompleted=true` | Bỏ qua client assertion; yêu cầu verifier result. |
| Session store không khả dụng | Không phát session cookie nếu record chưa được lưu. |
| Hai request cùng OTP/challenge | Atomic consume ngăn chấp nhận trùng. |
| Credential bị revoke giữa verify và commit | Kiểm tra trạng thái/version trước khi tạo session theo policy. |

## 19. Vận hành và xử lý sự cố

Theo dõi:
- tỷ lệ sign-in success/failure theo credential type;
- số lần throttling, cooldown và risk challenge;
- password hash verification latency và tải CPU/RAM;
- passkey assertion failure theo reason code;
- OTP replay, TOTP clock drift và delivery abuse;
- certificate expiry/revocation và chain validation errors;
- số account/credential bị disable hoặc revoke;
- tỷ lệ MFA completion và pre-auth transaction expiry;
- session creation failure và credential version mismatch.

Khi phát hiện credential compromise:
1. Xác định account, credential record và thời gian bị ảnh hưởng.
2. Revoke hoặc reset credential theo quy trình.
3. Thu hồi session, refresh token và API credential liên quan theo policy.
4. Yêu cầu reauthentication hoặc recovery có assurance phù hợp.
5. Kiểm tra các lần đăng nhập và hành động trong cửa sổ rủi ro.
6. Thông báo qua kênh đã xác minh.
7. Ghi audit, bảo toàn log và khắc phục nguyên nhân.

Không chỉ đổi password mà để session/token cũ tiếp tục hoạt động nếu threat model yêu cầu thu hồi. Không xóa dấu vết audit cần thiết khi credential bị revoke.

## 20. Bài tập tình huống

Một cổng doanh nghiệp hỗ trợ đăng nhập bằng email/password và passkey. Khi login bằng password, API trả “email không tồn tại” nếu account không có, “password sai” nếu hash không khớp và “account bị khóa” nếu account suspended. Password được lưu bằng SHA-256(email + password). Hệ thống không rate limit trước khi verify. Sau khi password đúng, server tạo session đầy đủ rồi mới yêu cầu OTP ở trang tiếp theo.

**Yêu cầu phân tích:**

1. Vì sao SHA-256 trực tiếp không phù hợp để lưu password?
2. Những response nào tạo user enumeration?
3. Vì sao rate limit phải bảo vệ cả lookup và password hash verification?
4. Thiết kế lại password verifier và dummy verification thế nào?
5. Passkey assertion cần được kiểm tra những trường nào?
6. Vì sao session đầy đủ không được tạo trước MFA?
7. Khi account bị suspend hoặc credential bị revoke, session/token cũ được xử lý ra sao?

**Hướng phân tích:** Dùng Argon2id hoặc password-hashing scheme phù hợp có salt riêng và parameters được benchmark; không nối email với password rồi SHA-256. Dùng thông báo public chung, kiểm soát timing và rate limit đa chiều. Passkey kiểm tra challenge, origin, RP ID hash, signature, credential/account binding và UV theo policy. Password đúng chỉ tạo pre-auth transaction giới hạn nếu MFA còn pending. Account/credential state phải được kiểm tra trước session commit; revoke có thể kéo theo thu hồi session/token.

## 21. Checklist review

- [ ] Identifier được phân biệt với credential và proof.
- [ ] Identifier normalization nhất quán; password không bị trim/case-fold/truncate âm thầm.
- [ ] Password được lưu bằng password-hashing function phù hợp, salt riêng và parameters có thể điều chỉnh.
- [ ] Password verification dùng thư viện chuẩn; không lưu plaintext hoặc hash nhanh tự xây dựng.
- [ ] Password input và secret không xuất hiện trong log/trace.
- [ ] Unknown account và sai password không tạo khác biệt công khai rõ ràng.
- [ ] Rate limit áp dụng theo account, network và global capacity trước thao tác tốn tài nguyên.
- [ ] Có bảo vệ password spraying, credential stuffing và brute force mà không tạo account-lockout DoS.
- [ ] Passkey assertion kiểm tra challenge, origin, RP ID, signature, credential binding và flags theo policy.
- [ ] OTP có expiry, purpose binding, rate limit và replay protection.
- [ ] Certificate kiểm tra chain, EKU, identity mapping, revocation và proof-of-possession.
- [ ] Account/credential state được kiểm tra sau proof và trước session commit.
- [ ] MFA bắt buộc hoàn tất trước authenticated session; pre-auth state bị giới hạn.
- [ ] Authentication được tách khỏi authorization và transaction confirmation.
- [ ] Credential revoke/reset có xử lý session/token liên quan.
- [ ] Audit lưu reason code nội bộ nhưng public error không tiết lộ trạng thái account.
- [ ] Có kiểm thử timing, concurrency, replay, account enumeration và credential compromise.

## 22. Ghi nhớ

**Credential check là bước xác minh bằng chứng đăng nhập theo đúng loại credential và ràng buộc với account đã được xác định.** Identifier chỉ giúp tìm record; password cần được verify bằng password-hashing function, passkey cần xác minh assertion WebAuthn, OTP cần kiểm tra expiry/replay, còn certificate cần path validation và proof-of-possession. Sau đó hệ thống vẫn phải kiểm tra trạng thái account/credential, hoàn tất MFA nếu bắt buộc và chỉ tạo session khi policy đạt.

Khi review, hãy hỏi: **Server đang xác minh proof nào và bằng verifier nào? Credential có còn active không? Response có tiết lộ account tồn tại không? Rate limit có chống được spraying và DoS không? MFA đã hoàn tất trước khi tạo session chưa? Khi credential bị compromise hoặc revoke, mọi session/token liên quan bị xử lý ra sao?**
