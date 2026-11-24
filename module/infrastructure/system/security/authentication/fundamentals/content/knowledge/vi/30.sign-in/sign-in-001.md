# Login request — Thiết kế yêu cầu đăng nhập an toàn

Khi người dùng bấm **Đăng nhập**, trình duyệt gửi một yêu cầu tới hệ thống xác thực. Yêu cầu có thể chứa định danh tài khoản, lựa chọn phương thức xác thực, challenge hoặc dữ liệu để tiếp tục một giao dịch đăng nhập đang chờ. Tuy nhiên, việc nhận được request không chứng minh người gửi là chủ tài khoản. Request chỉ khởi tạo hoặc tiếp tục một quy trình; hệ thống phải xác minh bằng chứng, ràng buộc request với đúng trình duyệt/giao dịch và chỉ tạo phiên sau khi mọi kiểm tra đạt.

Ví dụ, một ứng dụng web có form email và mật khẩu. Kẻ tấn công có thể gửi hàng nghìn request để dò mật khẩu, kiểm tra email nào tồn tại, thử credential bị rò rỉ hoặc ép nạn nhân đăng nhập vào account do attacker kiểm soát. Một luồng passkey cũng có thể bị lạm dụng nếu challenge bị dùng lại hoặc không kiểm tra origin. Vì vậy, thiết kế login request cần bao gồm bảo vệ giao thức, chống tự động hóa, kiểm tra đầu vào, quản lý trạng thái và xử lý lỗi.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, bài học này kết nối credential, mật khẩu, MFA, passkey, token, phiên và ranh giới tin cậy. Người học sẽ biết cách mô hình hóa một login transaction, chọn phương thức phù hợp, ràng buộc state/challenge/redirect, hạn chế enumeration và brute force, xử lý retry an toàn, ghi audit tối thiểu và tránh tạo session trước khi xác thực hoàn tất.

## 1. Login request là gì?

**Login request** là thông điệp mà client gửi tới hệ thống để bắt đầu hoặc tiếp tục quy trình đăng nhập. Nó có thể là:

- Request hiển thị trang đăng nhập hoặc lấy cấu hình phương thức.
- Request gửi identifier và password.
- Request yêu cầu WebAuthn challenge cho passkey.
- Request gửi assertion từ authenticator.
- Request bắt đầu MFA hoặc gửi mã/challenge response.
- Request khởi tạo federation redirect tới Identity Provider.
- Request tiếp tục transaction sau khi người dùng hoàn tất một bước xác thực.

Một login request không đồng nghĩa với một lần xác thực thành công. Cần phân biệt:

| Thành phần | Vai trò |
| --- | --- |
| **Login request** | Khởi tạo hoặc tiếp tục một giao dịch đăng nhập |
| **Credential/assertion** | Bằng chứng được gửi hoặc tạo để chứng minh quyền kiểm soát authenticator |
| **Authentication decision** | Kết quả server xác minh bằng chứng và policy |
| **Session/token issuance** | Cấp credential phiên sau khi xác thực thành công |
| **Authorization** | Quyết định chủ thể được phép truy cập tài nguyên hoặc thực hiện hành động |

Client có thể yêu cầu phương thức password, passkey hoặc MFA, nhưng server phải quyết định phương thức nào được phép cho account, tenant, client và mức assurance cần thiết. Không tin một trường do client tự gửi như **isAdmin**, **mfaPassed** hoặc **authenticated=true**.

## 2. Các thành phần và ranh giới tin cậy

Một luồng đăng nhập thông thường có các thành phần:

- **User agent:** trình duyệt hoặc ứng dụng đang tương tác với người dùng.
- **Login UI/client:** hiển thị form, bắt đầu transaction và gửi request.
- **Authentication service:** quản lý transaction, tra account, xác minh credential và áp dụng policy.
- **Credential store:** lưu password verifier, public key passkey, authenticator metadata hoặc tham chiếu tới hệ thống credential.
- **Risk/abuse controls:** rate limit, phát hiện automation, tín hiệu thiết bị và đánh giá rủi ro.
- **Session/token service:** tạo session cookie hoặc token sau khi xác thực.
- **Audit/monitoring:** ghi nhận sự kiện phục vụ vận hành và điều tra.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser / Client
    participant L as Login endpoint
    participant A as Authentication service
    participant C as Credential store
    participant S as Session service
    U->>B: Mở trang đăng nhập
    B->>L: Yêu cầu login transaction
    L->>A: Validate request và tạo transaction
    A-->>B: Transaction ID / phương thức được phép
    U->>B: Gửi credential hoặc assertion
    B->>L: Authentication response + transaction
    L->>A: Xác minh bằng chứng và risk policy
    A->>C: Kiểm tra credential
    C-->>A: Kết quả xác minh
    A->>A: Quyết định xác thực / step-up
    A->>S: Tạo session nếu thành công
    S-->>B: Session cookie hoặc token
~~~

Ranh giới tin cậy quan trọng:

1. Request từ browser là dữ liệu không tin cậy, kể cả khi đến từ trang login chính thức.
2. Header như Host, Origin, Referer và forwarded headers cần được xử lý theo cấu hình proxy tin cậy; không để client tự xác định host/scheme nội bộ.
3. Credential store và signing/session keys là tài sản nhạy cảm; login endpoint không được trả hoặc log chúng.
4. Client chỉ nhận kết quả cần thiết; quyết định principal, assurance và session phải được tạo phía server.
5. Mọi callback, challenge response và MFA response phải gắn với đúng transaction và subject.

## 3. Vòng đời của login transaction

Không nên xử lý login như các request rời rạc không có quan hệ. Hãy tạo một **login transaction** phía server với ID khó đoán, TTL ngắn và trạng thái được kiểm soát.

~~~mermaid
stateDiagram-v2
    [*] --> CREATED: User bắt đầu login
    CREATED --> METHOD_SELECTED: Chọn phương thức hợp lệ
    METHOD_SELECTED --> CHALLENGE_ISSUED: Server phát challenge
    CHALLENGE_ISSUED --> PRIMARY_VERIFIED: Credential chính hợp lệ
    PRIMARY_VERIFIED --> STEP_UP_REQUIRED: Policy yêu cầu thêm yếu tố
    PRIMARY_VERIFIED --> AUTHENTICATED: Không cần step-up
    STEP_UP_REQUIRED --> AUTHENTICATED: Step-up hợp lệ
    AUTHENTICATED --> SESSION_ISSUED: Tạo session mới
    CREATED --> EXPIRED: Quá TTL
    CHALLENGE_ISSUED --> FAILED: Credential sai / quá số lần
    STEP_UP_REQUIRED --> FAILED: Step-up thất bại
    AUTHENTICATED --> FAILED: Session issuance thất bại
    CREATED --> CANCELLED: Người dùng hủy
    SESSION_ISSUED --> [*]
    FAILED --> [*]
    EXPIRED --> [*]
    CANCELLED --> [*]
~~~

Một transaction nên lưu các thuộc tính cần thiết:

| Thuộc tính | Mục đích |
| --- | --- |
| Transaction ID | Tham chiếu ngẫu nhiên, không chứa thông tin cá nhân |
| Created/expiry time | Giới hạn thời gian hoàn thành |
| Client/application | Ràng buộc transaction với đúng ứng dụng |
| Tenant/realm | Ràng buộc phạm vi danh tính |
| Expected origin/redirect | Kiểm tra callback và nguồn request |
| Selected authentication method | Phương thức đã được server cho phép |
| Subject reference | Account đã được xác định, nếu bước đó đã diễn ra |
| State/nonce/challenge | Ràng buộc protocol và chống replay |
| Attempt counter | Giới hạn số lần thử |
| Risk context | Các tín hiệu và policy version cần thiết |
| Status/version | Ngăn xử lý đồng thời hoặc tiêu thụ transaction nhiều lần |

Transaction phải được tiêu thụ hoặc chuyển trạng thái bằng thao tác nguyên tử. Nếu hai request cùng gửi một challenge, chỉ một request được phép hoàn tất transaction. Retry do mạng chập chờn cần có quy tắc rõ ràng; không để một challenge đã dùng được chấp nhận lần nữa.

### 3.1. Transaction ID không phải credential đăng nhập

Transaction ID chỉ giúp tham chiếu một quy trình. Nó không được tự nó cấp quyền đăng nhập. Cần có entropy đủ cao, TTL ngắn, ràng buộc với browser/session context và kiểm tra trạng thái phía server. Không đưa dữ liệu nhạy cảm hoặc quyền vào transaction ID.

### 3.2. Một account, nhiều tab và nhiều thiết bị

Người dùng có thể mở nhiều tab hoặc bắt đầu đăng nhập trên nhiều thiết bị. Không dùng một biến session toàn cục kiểu “current challenge” có thể bị request mới ghi đè request cũ. Mỗi transaction cần định danh riêng, ràng buộc đúng browser context và có giới hạn số transaction đang hoạt động. Khi một transaction hoàn tất, transaction khác không được tự động nhận kết quả đó.

## 4. Thiết kế request và kiểm tra đầu vào

Login endpoint nên có contract rõ ràng: method, content type, trường bắt buộc, kích thước tối đa, encoding, trạng thái lỗi và giới hạn tốc độ.

Ví dụ một API bắt đầu login:

~~~http
POST /auth/login-transactions HTTP/1.1
Host: auth.example.com
Content-Type: application/json
Accept: application/json
Origin: https://app.example.com
X-CSRF-Token: <csrf-token>

{
  "client_id": "web-portal",
  "tenant_hint": "org-a",
  "return_path": "/dashboard"
}
~~~

Response có thể trả transaction ID và danh sách phương thức được phép:

~~~json
{
  "transaction_id": "opaque-random-reference",
  "expires_in": 300,
  "methods": ["passkey", "password"]
}
~~~

Đây là ví dụ contract minh họa; tên endpoint và field cần thống nhất trong hệ thống thực tế. Không đưa password, OTP hoặc access token vào request khởi tạo transaction.

### Kiểm tra cú pháp và giới hạn

- Chỉ chấp nhận HTTP method và content type được định nghĩa.
- Giới hạn body size, số trường, độ dài identifier và kích thước assertion.
- Từ chối JSON sai cấu trúc, duplicate key mơ hồ và encoding không hợp lệ.
- Validate kiểu dữ liệu, enum, charset và định dạng trước khi xử lý credential.
- Không cho phép client gửi thuật toán hash, role, assurance level hoặc trạng thái xác thực tùy ý.
- Áp dụng timeout cho truy vấn database, external IdP và fraud/risk service.
- Không phản chiếu trực tiếp input vào HTML hoặc log; escape dữ liệu hiển thị để tránh injection.

### Chuẩn hóa identifier

Email, username, số điện thoại và mã nhân viên có quy tắc chuẩn hóa khác nhau. Server nên có một quy tắc canonicalization nhất quán với quy trình đăng ký và khôi phục:

- Email domain có thể chuẩn hóa theo quy tắc domain; không tự ý thay đổi local-part nếu hệ thống không có policy tương ứng.
- Username có thể case-sensitive hoặc case-insensitive; phải giữ đúng contract đã công bố.
- Số điện thoại nên được parse theo vùng/quốc gia và chuẩn hóa theo format thống nhất.
- Unicode cần xử lý theo một policy nhất quán để tránh hai biểu diễn được hiểu thành cùng hoặc khác account ngoài ý muốn.
- Không trim hoặc normalize password một cách tùy tiện; password phải được xử lý nhất quán với lúc đăng ký và đổi mật khẩu.
- Không dùng giá trị identifier thô làm cache key hoặc metric label nếu có nguy cơ lộ PII; cân nhắc keyed hash/pseudonymous reference.

## 5. CSRF, login CSRF và ràng buộc nguồn request

CSRF thường được nhắc tới khi attacker khiến browser gửi request thay đổi trạng thái bằng cookie của nạn nhân. Đăng nhập cũng có thể bị CSRF: attacker khiến nạn nhân đăng nhập vào account do attacker kiểm soát. Sau đó nạn nhân có thể vô tình lưu dữ liệu cá nhân, địa chỉ hoặc phương thức thanh toán vào account của attacker.

Với browser flow dùng cookie:

- Bảo vệ request khởi tạo và submit login bằng CSRF token hoặc cơ chế ràng buộc transaction phù hợp.
- Kiểm tra Origin theo allowlist cho endpoint nhạy cảm; Referer có thể là tín hiệu bổ sung theo policy.
- Dùng cookie Secure, HttpOnly và SameSite phù hợp.
- Ràng buộc CSRF token với browser session/transaction, không chấp nhận token do client tự tạo.
- Không dùng GET để gửi password, OTP hoặc thực hiện thao tác thay đổi trạng thái.
- Sau khi xác thực thành công, rotate session ID để ngăn session fixation.

Origin/Referer check không thay thế CSRF token trong mọi kiến trúc. Một số client native không gửi Origin như browser; cần contract riêng, client authentication hoặc proof-of-possession phù hợp. Không bật CORS rộng và cho credentials chỉ để sửa lỗi login request.

### OIDC state, nonce và PKCE

Nếu login request khởi tạo OIDC Authorization Code Flow:

- **state** ràng buộc callback với transaction do RP tạo và giúp chống login CSRF.
- **nonce** ràng buộc ID token với authentication request và chống token replay theo OIDC.
- **PKCE** ràng buộc authorization code với client đã tạo verifier.
- Redirect URI phải được đăng ký và khớp chính xác theo client registration.

Các giá trị này có vai trò khác nhau; không thay thế lẫn nhau. Lưu state/nonce/verifier phía server hoặc trong cơ chế bảo vệ phù hợp, dùng giá trị khó đoán, TTL ngắn và chỉ tiêu thụ một lần.

## 6. Redirect an toàn sau đăng nhập

Login request thường mang thông tin nơi người dùng muốn quay lại sau khi đăng nhập. Nếu server chấp nhận URL tùy ý, attacker có thể biến trang login đáng tin thành open redirect để đưa nạn nhân tới trang phishing.

Không chấp nhận return URL tùy ý như:

~~~text
https://evil.example/collect
//evil.example/path
https://trusted.example@evil.example/
~~~

Các quy tắc:

1. Ưu tiên lưu một route/path nội bộ đã được server xác nhận thay vì URL đầy đủ do client gửi.
2. Nếu cần redirect URI đầy đủ, dùng allowlist chính xác gắn với client/tenant.
3. Reject scheme, host, port hoặc path ngoài policy; không chỉ kiểm tra chuỗi bắt đầu bằng domain đáng tin.
4. Xử lý percent-encoding, backslash, userinfo và scheme-relative URL nhất quán.
5. Không tạo redirect từ Host hoặc X-Forwarded-Host chưa được proxy tin cậy xác thực.
6. Không cho phép redirect tới HTTP hoặc domain không nằm trong trust configuration.

Với OIDC, redirect URI phải khớp client registration. Với login nội bộ, route đích nên được ánh xạ bằng server-side identifier hoặc allowlist. Sau login, chỉ redirect khi transaction đã được xác minh và session được tạo thành công.

## 7. Password login request

Password login gửi identifier và password qua HTTPS bằng POST. Server tra account, lấy password verifier và dùng password hashing scheme phù hợp để xác minh. Không gửi password trong URL, không lưu plaintext và không ghi password vào log.

### 7.1. Xử lý phía server

1. Validate request size, encoding và required fields.
2. Chuẩn hóa identifier theo policy.
3. Áp dụng rate limit/abuse controls trước khi thực hiện phép hash tốn tài nguyên.
4. Tra account trong đúng tenant/realm.
5. Nếu account tồn tại, verify password bằng password hashing algorithm đã cấu hình; nếu không tồn tại, có thể chạy một phép kiểm tra giả có chi phí tương đương để giảm timing enumeration.
6. Kiểm tra account state, credential state và policy.
7. Nếu password đúng nhưng cần MFA/step-up, chuyển transaction sang trạng thái chờ yếu tố tiếp theo.
8. Chỉ tạo session sau khi tất cả yếu tố bắt buộc hoàn tất.

### 7.2. Không để lộ account enumeration

Thông báo cho identifier không tồn tại và password sai nên tương tự nhau, ví dụ: “Không thể đăng nhập với thông tin đã cung cấp.” Tránh trả lỗi “email không tồn tại” hoặc “tài khoản bị khóa” cho request công khai nếu điều đó làm lộ account state.

Ngoài nội dung response, cần xem:

- Timing khác biệt do một nhánh tra account nhanh hơn nhánh verify password.
- Response size hoặc HTTP status khác nhau.
- CAPTCHA/challenge chỉ xuất hiện với account tồn tại.
- Forgot-password, resend code và account recovery có thể trở thành kênh enumeration.
- Log và analytics có thể vô tình hiển thị identifier hoặc account existence.

Không thể đảm bảo thời gian phản hồi giống hệt tuyệt đối trong hệ thống phân tán; mục tiêu là giảm tín hiệu rõ ràng, áp dụng kiểm soát tốc độ và không cung cấp thông tin account không cần thiết.

### 7.3. Không khóa account theo cách tạo DoS

Khóa cứng account sau một số lần sai cố định có thể cho attacker khóa account của nạn nhân. Dùng kiểm soát nhiều lớp:

- Rate limit theo account identifier, IP/network, device/session và phạm vi toàn hệ thống.
- Progressive delay hoặc temporary throttling thay vì permanent lockout tự động.
- Phát hiện credential stuffing và password spraying theo nhiều account.
- Giới hạn song song và kiểm soát phân tán để nhiều node không vượt ngưỡng.
- Cảnh báo và step-up khi có dấu hiệu rủi ro; không dùng IP làm tín hiệu duy nhất.
- Có quy trình mở khóa/recovery an toàn và không để help desk trở thành bypass.

## 8. Passkey login request

Với passkey/WebAuthn, client không gửi password. RP tạo challenge ngẫu nhiên và gửi options cho browser; authenticator ký dữ liệu liên quan tới challenge và RP. Server xác minh assertion rồi mới xác thực.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant RP as Relying Party
    participant A as Authenticator
    B->>RP: POST bắt đầu passkey login
    RP->>RP: Tạo challenge, lưu transaction và policy
    RP-->>B: PublicKeyCredentialRequestOptions
    B->>A: navigator.credentials.get()
    A-->>B: Assertion được ký
    B->>RP: POST assertion + transaction reference
    RP->>RP: Kiểm tra challenge, origin, RP ID và chữ ký
    RP->>RP: Kiểm tra credential/account state và policy
    RP-->>B: Tạo session nếu hợp lệ
~~~

### Các kiểm tra bắt buộc

- Challenge được tạo bằng CSPRNG, có entropy đủ, TTL ngắn và dùng một lần.
- Transaction ràng buộc challenge với đúng RP, browser context và login attempt.
- Kiểm tra client data type là WebAuthn authentication assertion.
- So sánh challenge trong client data với challenge lưu server-side.
- Kiểm tra origin chính xác theo allowlist của RP.
- Kiểm tra RP ID hash khớp RP ID được cấu hình.
- Xác minh chữ ký bằng public key đã đăng ký cho credential ID.
- Kiểm tra userHandle/credential mapping theo account discovery policy.
- Kiểm tra user presence và user verification theo assurance policy.
- Xử lý sign counter theo đặc tính authenticator; không giả định mọi passkey sync đều có counter tăng đơn điệu.
- Tiêu thụ challenge nguyên tử để ngăn replay.

Không tin credential ID, userHandle, origin hoặc trạng thái user verification do client tự khai nếu chưa được xác minh từ assertion. Với discoverable credential, server vẫn phải ánh xạ credential tới đúng account và kiểm tra account state.

### Usernameless và username-first

Passkey flow có thể bắt đầu bằng username hoặc cho phép authenticator tìm discoverable credential. Hai mô hình có khác biệt về privacy và UX:

- Username-first có thể tiết lộ account existence nếu server trả phương thức hoặc lỗi khác nhau.
- Usernameless có thể giảm việc nhập identifier nhưng cần xử lý account discovery, userHandle và lựa chọn credential đúng.
- Không hiển thị thông tin cá nhân hoặc account metadata trước khi assertion được xác minh.
- Với account có nhiều passkey, policy cần xử lý credential bị thu hồi, credential cũ và thông báo khi đăng ký mới.

## 9. MFA và step-up request

Nếu password hoặc passkey đầu tiên hợp lệ nhưng policy yêu cầu thêm yếu tố, server chuyển transaction sang step-up. MFA request phải được gắn với cùng subject và login transaction; không được dùng mã từ transaction khác.

Các kiểm soát:

- Challenge/MFA transaction có TTL ngắn, attempt limit và one-time use.
- TOTP kiểm tra time window nhỏ, chống reuse mã trong cùng timestep theo policy.
- Push approval hiển thị rõ thông tin đăng nhập; chống push fatigue bằng number matching hoặc context phù hợp.
- SMS/voice OTP cần xét rủi ro SIM swap, interception và phishing; không xem là phishing-resistant.
- WebAuthn/security key có thể cung cấp khả năng chống phishing tốt hơn nếu được cấu hình đúng.
- Khi step-up thất bại hoặc hết hạn, không phát session có assurance thấp hơn yêu cầu.
- Thay đổi MFA hoặc recovery factor cần reauthentication và audit riêng.

Không gửi mã OTP qua log, URL, analytics hoặc thông báo không được bảo vệ. Không để request step-up chỉ chứa account ID mà thiếu transaction binding; attacker có thể thử gắn yếu tố của mình vào login của nạn nhân.

## 10. Rate limiting và chống tự động hóa

Login endpoint là mục tiêu phổ biến của brute force, password spraying, credential stuffing, account enumeration và denial of service. Rate limiting phải phối hợp nhiều chiều:

| Chiều giới hạn | Mục đích | Hạn chế nếu dùng riêng |
| --- | --- | --- |
| Account/identifier | Hạn chế thử nhiều password vào một account | Attacker có thể khóa hoặc làm chậm nạn nhân |
| IP/network/ASN | Giảm automation từ một nguồn | NAT, carrier, VPN và proxy khiến nhiều người dùng chung IP |
| Device/session | Phát hiện hành vi lặp trên một client | Fingerprint có thể giả mạo hoặc thay đổi |
| Tenant/client | Bảo vệ một tổ chức hoặc ứng dụng khỏi burst | Cần tránh một tenant làm ảnh hưởng tenant khác |
| Global/service | Bảo vệ hạ tầng và credential store | Ngưỡng toàn cục quá thấp gây ảnh hưởng diện rộng |
| Credential pair / risk cluster | Phát hiện password spraying hoặc credential stuffing | Cần bảo vệ dữ liệu và tránh lưu password thô |

Rate limit cần phân tán và nhất quán đủ để nhiều instance không vượt ngưỡng. Có thể kết hợp token bucket, sliding window, concurrency limit và progressive delay. Ngưỡng cần dựa trên traffic thật và có khả năng điều chỉnh theo tenant/endpoint.

### CAPTCHA và bot challenge

CAPTCHA hoặc bot challenge có thể tăng chi phí automation nhưng không phải xác thực danh tính. Nó có thể bị giải tự động, gây khó tiếp cận hoặc chặn người dùng hợp lệ. Chỉ áp dụng khi risk policy cần, có phương thức thay thế accessible và không dùng kết quả CAPTCHA thay cho credential verification.

## 11. Error handling và response contract

Response nên giúp client tiếp tục đúng bước mà không tiết lộ dữ liệu nội bộ hoặc trạng thái account nhạy cảm.

| Tình huống | Phản hồi công khai gợi ý | Hành vi server |
| --- | --- | --- |
| Request sai cấu trúc | 400 Bad Request | Không gọi credential verifier |
| Thiếu CSRF/state hoặc transaction không hợp lệ | Lỗi request chung | Không xử lý credential; ghi reason code nội bộ |
| Credential không hợp lệ | Thông báo đăng nhập chung | Tăng attempt/risk counter |
| Cần MFA/step-up | Trả trạng thái transaction cần bước tiếp | Chưa tạo session hoàn chỉnh |
| Transaction hết hạn/đã dùng | Yêu cầu bắt đầu lại | Từ chối replay |
| Rate limit | 429 Too Many Requests và Retry-After nếu phù hợp | Throttle theo policy |
| Account disabled/policy denied | Thông báo chung hoặc hướng dẫn hỗ trợ phù hợp | Không tạo session; không tiết lộ account state không cần thiết |
| Backend/IdP tạm lỗi | Thông báo thử lại sau | Không fail-open; giữ trạng thái nhất quán |
| Thành công | Redirect an toàn hoặc trả session/token | Rotate session ID, ghi audit |

Không trả stack trace, SQL error, password hash, MFA state, public key metadata nội bộ hoặc chi tiết risk score cho client. Dùng error code nội bộ ổn định để hỗ trợ vận hành; response công khai có thể được gom nhóm để chống enumeration.

## 12. Session issuance sau login

Sau khi authentication decision thành công, server tạo session mới. Không tạo session authenticated khi mới nhận identifier, khi password đúng nhưng MFA chưa xong, hoặc khi passkey assertion chưa được xác minh đầy đủ.

Đối với browser session:

- Rotate session ID sau login và sau khi tăng privilege/assurance.
- Cookie session dùng Secure, HttpOnly, Path phù hợp và SameSite theo flow.
- Đặt idle timeout và absolute timeout.
- Gắn session với subject, tenant, authentication time và assurance context cần thiết.
- Hủy hoặc giới hạn session pre-authentication sau khi login hoàn tất.
- Có CSRF protection cho request dùng cookie tự động gửi.
- Không đặt session ID hoặc bearer token trong URL.

Đối với API/native client:

- Cấp token qua flow phù hợp, không tạo token từ response của login endpoint tùy tiện nếu kiến trúc dùng OAuth/OIDC.
- Giới hạn audience, scope và lifetime.
- Lưu token theo khả năng bảo vệ của nền tảng.
- Có refresh/revocation policy và xử lý logout.

Sau khi đăng nhập, authentication context cần được lưu đủ để quyết định step-up cho hành động nhạy cảm. Một phiên được xác thực bằng password đơn lẻ không nhất thiết đáp ứng yêu cầu của thao tác quản trị hoặc chuyển tiền.

## 13. Java/Spring: mô hình hóa login transaction

Ví dụ sau minh họa cách tách request DTO, transaction service và authentication service. Đây là pseudocode Java/Spring để giải thích trách nhiệm; cần điều chỉnh theo framework, session architecture và credential provider của ứng dụng.

~~~java
record StartLoginRequest(
    String clientId,
    String tenantHint,
    String returnPath
) {}

record StartLoginResponse(
    String transactionId,
    long expiresIn,
    List<String> methods
) {}

@RestController
class LoginController {
    private final LoginTransactionService transactions;
    private final LoginPolicy policy;

    @PostMapping("/auth/login-transactions")
    StartLoginResponse start(
            @Valid @RequestBody StartLoginRequest request,
            HttpServletRequest httpRequest) {

        policy.requireAllowedClient(request.clientId());
        policy.validateTenantHint(request.tenantHint());
        policy.validateReturnPath(request.returnPath());
        policy.validateBrowserRequest(httpRequest);

        LoginTransaction tx = transactions.create(
            request.clientId(),
            request.tenantHint(),
            request.returnPath(),
            policy.allowedMethods(request.clientId())
        );

        return new StartLoginResponse(
            tx.publicReference(),
            tx.remainingSeconds(),
            tx.allowedMethods()
        );
    }
}
~~~

Khi nhận credential:

~~~java
AuthenticationResult submitPassword(
        String transactionId,
        String identifier,
        char[] password) {

    LoginTransaction tx = transactions.loadActive(transactionId);
    if (tx == null || tx.isExpired()) return AuthenticationResult.restart();

    if (!tx.allowsMethod("password")) {
        return AuthenticationResult.reject();
    }

    rateLimiter.check(tx, identifier, requestContext());
    Account account = accountLookup.findForAuthentication(
        tx.tenantId(), normalizeIdentifier(identifier)
    );

    PasswordVerification verification =
        passwordVerifier.verify(account, password);

    if (!verification.matches() || !accountPolicy.canSignIn(account)) {
        transactions.recordFailedAttemptAtomically(tx.id());
        return AuthenticationResult.genericFailure();
    }

    if (accountPolicy.requiresStepUp(account, tx.riskContext())) {
        transactions.advanceToStepUpAtomically(tx.id(), account.id());
        return AuthenticationResult.stepUpRequired();
    }

    transactions.consumeAndAuthenticateAtomically(tx.id(), account.id());
    return sessionIssuer.issueFreshSession(account, tx);
}
~~~

Đoạn minh họa không bao gồm mọi chi tiết production. Cần bổ sung:

- Xử lý account không tồn tại với password verifier giả có chi phí phù hợp để giảm timing enumeration.
- Xóa password khỏi bộ nhớ sớm nhất có thể; không ghi vào log, exception hoặc telemetry.
- Đảm bảo transaction consume và session issuance có tính nhất quán; tránh hai request cùng tạo hai session không mong muốn.
- Xác minh CSRF/Origin, content length, request rate và client/tenant policy ở filter hoặc gateway phù hợp.
- Dùng password hashing algorithm chuyên dụng và tham số đã benchmark; không dùng SHA-256 thuần cho password.
- Xử lý lỗi dependency, retry và timeout mà không chuyển sang fail-open.
- Dùng secret manager và session store được bảo vệ; không hardcode secret.
- Phân quyền sau authentication vẫn là bước riêng.

## 14. Logging, audit và monitoring

Login request cần observability để phát hiện tấn công và chẩn đoán lỗi, nhưng log cũng là nơi dễ rò rỉ credential.

### Trường audit phù hợp

| Trường | Mục đích |
| --- | --- |
| Request/correlation ID | Liên kết các bước của cùng transaction |
| Transaction reference | Tham chiếu login flow mà không chứa credential |
| Client/tenant reference | Xác định ứng dụng và phạm vi |
| Authentication method | Password, passkey, MFA hoặc federation |
| Outcome/reason code | Success, invalid credential, expired, throttled, step-up |
| Timestamp/latency | Phân tích thời gian và clock issues |
| Risk/policy version | Giải thích policy đã áp dụng |
| Network/device signal reference | Điều tra ở mức cần thiết, có giới hạn retention |
| Session reference | Nối login với session được cấp mà không log session secret |

Không ghi password, OTP, recovery code, raw passkey assertion, access/refresh token, session cookie hoặc full Authorization header. Identifier có thể là PII; mask hoặc pseudonymize theo policy. Log truy cập phải được kiểm soát, bảo vệ integrity và có thời hạn lưu.

### Chỉ số nên theo dõi

- Login success/failure theo client, tenant, method và thời gian.
- Invalid credential, unknown identifier pattern và account enumeration signal.
- Password spraying/credential stuffing, rate-limit hit và bot challenge rate.
- Passkey challenge expiry, origin mismatch, RP ID mismatch và signature failure.
- MFA failure, push denial, OTP reuse và step-up completion.
- Transaction abandoned, expired, duplicate consume và concurrent request.
- Session issuance, session rotation failure và token/session revocation.
- Latency/error rate của credential store, IdP, risk engine và session store.

Không tạo metric label có giá trị identifier thô hoặc transaction ID không giới hạn; điều đó có thể gây lộ PII và cardinality explosion.

## 15. Ma trận kiểm thử login request

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Request hợp lệ khởi tạo transaction | Tạo transaction ngẫu nhiên, TTL rõ và phương thức theo server policy |
| Client gửi client ID không được đăng ký | Từ chối, không tạo transaction |
| Tenant hint không thuộc client | Từ chối hoặc yêu cầu chọn tenant theo policy |
| Return path là URL ngoài allowlist | Từ chối hoặc thay bằng route mặc định an toàn |
| Thiếu CSRF token hoặc Origin không hợp lệ trong browser flow | Từ chối trước khi xử lý credential |
| Login transaction hết hạn | Yêu cầu bắt đầu lại |
| Challenge đã tiêu thụ được gửi lại | Từ chối replay |
| Hai request cùng transaction tới đồng thời | Chỉ một request được phép chuyển trạng thái |
| Password sai hoặc identifier không tồn tại | Response công khai tương tự, không tiết lộ account existence |
| Password đúng nhưng account cần MFA | Step-up; chưa tạo authenticated session |
| Password request body quá lớn hoặc encoding sai | Từ chối trước credential verification |
| Password xuất hiện trong log/trace | Redaction test phát hiện và ngăn ghi |
| Passkey assertion có challenge sai/hết hạn | Từ chối |
| Passkey assertion có origin hoặc RP ID sai | Từ chối |
| Passkey signature sai hoặc credential đã thu hồi | Từ chối |
| MFA code đã dùng hoặc transaction khác | Từ chối replay/cross-transaction |
| Password spraying từ nhiều IP | Phát hiện theo account/cluster và throttle phù hợp |
| Một IP dùng chung bởi nhiều người hợp lệ | Không khóa toàn bộ người dùng chỉ vì IP |
| Backend credential store timeout | Không fail-open; response lỗi có kiểm soát |
| Login thành công | Rotate session ID và cấp session theo policy |
| Login thất bại | Không tạo session authenticated |
| Session cookie thiếu Secure/HttpOnly theo policy | Security test thất bại |
| Client gửi role hoặc mfaPassed giả | Không ảnh hưởng quyết định server |

### Tình huống thực hành

Một cổng nhân viên dùng endpoint POST đăng nhập với email và mật khẩu. API trả lỗi “email không tồn tại” nếu không tìm thấy account và “sai mật khẩu” nếu account tồn tại. Không có rate limit theo account; chỉ giới hạn theo IP. Sau khi password đúng, server tạo session ngay, rồi frontend mới yêu cầu OTP. Tham số return URL được nhận trực tiếp từ query và redirect sau login.

**Yêu cầu:** chỉ ra rủi ro và thiết kế lại luồng.

**Hướng giải:**

1. Gom lỗi identifier không tồn tại và password sai thành phản hồi công khai chung; cân bằng timing bằng verifier giả khi account không tồn tại.
2. Thêm rate limit đa chiều: account/identifier, IP/network, device/session, tenant và global; dùng progressive delay, không khóa account vĩnh viễn chỉ vì số lần sai.
3. Tạo login transaction có ID khó đoán, TTL ngắn, CSRF binding và trạng thái one-time.
4. Sau password đúng, chuyển transaction sang step-up; chỉ tạo session authenticated khi OTP/MFA hợp lệ và được ràng buộc cùng subject/transaction.
5. Thay return URL tùy ý bằng route nội bộ hoặc allowlist redirect URI chính xác; xác minh trước khi redirect.
6. Bảo vệ password bằng HTTPS, không log credential, giới hạn body và dùng password hashing phù hợp.
7. Rotate session ID sau login, đặt cookie Secure/HttpOnly/SameSite và giữ CSRF protection cho request dựa trên cookie.
8. Ghi audit reason code, theo dõi password spraying, enumeration, MFA abuse và session issuance.

## 16. Câu hỏi tự kiểm tra

1. **Login request có chứng minh người gửi là chủ account không?** Không. Nó chỉ khởi tạo/tiếp tục transaction; server phải xác minh credential hoặc assertion.
2. **Vì sao cần login transaction?** Để ràng buộc challenge, state, subject, client và thời hạn; ngăn replay, trộn tab hoặc dùng kết quả của request khác.
3. **Login CSRF là gì?** Attacker khiến nạn nhân đăng nhập vào account của attacker, làm nạn nhân vô tình thao tác hoặc lưu dữ liệu trong account đó.
4. **state, nonce và PKCE có thay thế nhau không?** Không. Chúng bảo vệ các ràng buộc khác nhau trong OIDC authorization flow.
5. **Vì sao response password sai và account không tồn tại nên tương tự?** Để giảm account enumeration qua nội dung, status, kích thước hoặc timing.
6. **Có nên khóa account vĩnh viễn sau nhiều lần sai?** Không nên dùng như kiểm soát duy nhất vì attacker có thể gây DoS; kết hợp rate limit, delay, risk và recovery.
7. **Khi nào tạo session authenticated?** Chỉ sau khi tất cả credential, MFA/step-up và policy bắt buộc hoàn tất.
8. **Passkey login cần kiểm tra gì?** Challenge, origin, RP ID hash, chữ ký, credential mapping, user presence/verification và one-time transaction.

**Ghi nhớ:** Login request là điểm bắt đầu của một giao dịch xác thực. Hãy tạo transaction có TTL và one-time state, xác minh nguồn request và redirect, kiểm tra credential theo đúng phương thức, chống enumeration/brute force/replay, gắn MFA với cùng subject và chỉ cấp session sau khi policy hoàn tất. Mọi quyết định tin cậy phải được tạo ở server; dữ liệu do client tự khai không thể thay thế bằng chứng xác thực.
