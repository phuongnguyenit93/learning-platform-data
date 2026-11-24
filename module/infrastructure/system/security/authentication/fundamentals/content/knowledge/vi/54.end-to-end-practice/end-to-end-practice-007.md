# Thực hành tổng hợp: Chống phishing và replay

## 1. Bối cảnh

Một doanh nghiệp có cổng nhân viên, ứng dụng quản trị và API nội bộ. Nhân viên đăng nhập bằng password và OTP; nhóm quản trị dùng thêm MFA. Một số ứng dụng đã hỗ trợ passkey nhưng chưa đồng nhất. Đội vận hành phát hiện:

- Nhân viên nhận trang đăng nhập giả có giao diện gần giống cổng chính thức.
- Một số tài khoản bị đăng nhập ngay sau khi người dùng nhập password và OTP vào trang giả.
- OAuth callback bị gửi lại nhiều lần và một số API nhận request trùng.
- Người dùng nhận push MFA mà họ không khởi tạo.
- Help desk có thể thay đổi factor sau khi xác minh bằng thông tin cá nhân dễ đoán.

Nhóm bảo mật cần thiết kế lại luồng xác thực để giảm phishing và replay từ lúc người dùng bắt đầu login đến khi session hoặc API request được chấp nhận.

Hai mục tiêu của bài:

1. **Chống phishing:** ràng buộc bằng chứng xác thực với đúng website/service mà người dùng định truy cập, giảm khả năng attacker chuyển tiếp credential sang domain giả.
2. **Chống replay:** ràng buộc challenge, code, assertion, token hoặc request với đúng transaction, principal, mục đích và thời hạn.

Trong SECURITY_AUTHENTICATION_FUNDAMENTALS, hai mục tiêu này gắn với password, MFA, passkey/WebAuthn, OAuth/OIDC, token, session, API authentication và account recovery. Không có một control đơn lẻ giải quyết tất cả; cần bảo vệ toàn bộ chuỗi trust boundary.

## 2. Mục tiêu và phạm vi

Sau bài thực hành, người học có thể:

- Phân biệt phishing, credential relay, session theft, CSRF và replay.
- Xác định trust boundary, attacker capability và asset cần bảo vệ.
- Chọn phương thức xác thực phù hợp với rủi ro phishing.
- Giải thích vì sao passkey/WebAuthn chống phishing tốt hơn password và OTP.
- Thiết kế challenge-response có nonce, expiry, audience/origin binding và one-time use.
- Bảo vệ OAuth/OIDC callback bằng state, nonce, PKCE và issuer binding.
- Bảo vệ session, recovery flow và API request khỏi replay.
- Xây dựng negative test và kế hoạch ứng phó khi credential/session bị lộ.

Phạm vi gồm browser login, MFA, WebAuthn/passkey, OAuth/OIDC callback, session cookie, account recovery và một API có request signing. Cấu hình cụ thể phải theo protocol profile, nền tảng và policy thực tế.

## 3. Threat model

### 3.1. Tài sản

| Asset | Rủi ro |
| --- | --- |
| Password | Bị nhập vào domain giả, tái sử dụng hoặc đánh cắp từ malware. |
| OTP/TOTP hoặc push approval | Bị relay theo thời gian thực hoặc lạm dụng do MFA fatigue. |
| Passkey credential | Bị lạm dụng nếu origin/RP ID hoặc account mapping kiểm tra sai. |
| OAuth authorization code | Bị chặn, tráo hoặc phát lại nếu không gắn với client, redirect URI và PKCE. |
| ID Token/access token | Bị dùng sai issuer, audience, purpose hoặc phát lại. |
| Session cookie | Bị đánh cắp, cố định hoặc sử dụng lại từ thiết bị khác. |
| Recovery token/factor | Bị chiếm để thay password hoặc đăng ký authenticator của attacker. |
| API request signature | Bị phát lại nếu thiếu timestamp, nonce, body binding hoặc replay state. |

### 3.2. Attacker capability

Giả định attacker có thể:

- Đăng ký domain gần giống domain thật và gửi link qua email/chat.
- Dựng reverse proxy để chuyển tiếp tương tác giữa nạn nhân và dịch vụ thật.
- Thu thập password, OTP hoặc mã xác nhận mà người dùng nhập vào trang giả.
- Quan sát hoặc lấy một số request/response từ endpoint bị kiểm soát, log sai cấu hình hoặc thiết bị nhiễm malware.
- Gửi lại message hợp lệ đã thu thập trong thời gian token/challenge còn hiệu lực.
- Gửi request song song để khai thác race condition khi tiêu thụ one-time code.
- Lạm dụng recovery/help desk hoặc MFA fallback.

Không giả định attacker phá được TLS đúng cấu hình hoặc tính private key của authenticator. Nếu endpoint hay thiết bị người dùng đã bị chiếm hoàn toàn, cần thêm endpoint security, session protection và incident response.

### 3.3. Trust boundary

~~~mermaid
flowchart LR
    U["Người dùng và authenticator"] -->|"HTTPS / WebAuthn"| RP["Browser và Relying Party"]
    RP -->|"OIDC / federation"| IDP["Identity Provider"]
    RP -->|"Access token"| API["Resource Server"]
    API --> DATA["Dữ liệu nghiệp vụ"]
    U -->|"Email / support recovery"| REC["Recovery service"]
    REC --> IDP
    A["Attacker: phishing proxy / replay client"] -.->|"Domain giả / relay"| U
    A -.->|"Replay request"| RP
    A -.->|"Replay request"| API
~~~

Mỗi mũi tên là một ranh giới cần kiểm tra peer identity, integrity, freshness, audience/purpose và quyền truy cập. TLS bảo vệ kênh truyền nhưng không tự chứng minh người dùng đang ở đúng domain, cũng không ngăn mọi message hợp lệ bị gửi lại trong một transaction khác.

## 4. Phân biệt phishing, relay, replay, CSRF và session theft

| Kiểu tấn công | Cơ chế | Ví dụ | Kiểm soát trọng tâm |
| --- | --- | --- | --- |
| Phishing | Dụ người dùng cung cấp credential hoặc chấp thuận hành động trên giao diện giả. | Link dẫn tới trang login gần giống domain thật. | Origin-bound authentication, passkey, domain controls và education. |
| Real-time relay | Proxy chuyển tiếp tương tác của nạn nhân tới dịch vụ thật rồi lấy kết quả. | Nạn nhân nhập password và TOTP vào reverse proxy. | Phishing-resistant MFA, WebAuthn origin/RP ID binding. |
| Replay | Gửi lại message/challenge/token/request đã hợp lệ trước đó. | Dùng lại OTP, authorization code hoặc signed request. | Nonce, expiry, one-time use, audience và atomic consume. |
| CSRF | Ép browser đã có session gửi request mà user không chủ ý. | Trang độc hại kích hoạt thao tác đổi email bằng cookie tự gửi. | CSRF token, SameSite, Origin/Fetch Metadata và re-auth. |
| Session theft | Lấy cookie hoặc token sau login. | Malware đọc session hoặc token rò trong log. | Secure storage, cookie controls, XSS prevention, short lifetime và revocation. |
| MFA fatigue | Gửi nhiều prompt để người dùng bấm approve nhầm. | Push notification liên tục vào điện thoại. | Number matching, transaction context, rate limit và deny/report. |

Các kiểu tấn công có thể nối tiếp nhau. Phishing proxy có thể lấy OTP rồi relay để tạo session; sau đó attacker đánh cắp session và phát lại cookie. Cần phân tích từng bước thay vì gọi mọi sự cố là phishing.

## 5. Chọn phương thức xác thực theo khả năng chống phishing

| Phương thức | Khả năng chống phishing/relay | Ghi chú |
| --- | --- | --- |
| Password | Thấp | Người dùng có thể nhập vào domain giả; password reuse làm tăng tác động. |
| SMS OTP | Thấp | Có thể bị phishing, relay và SIM swap. |
| Email OTP | Thấp đến trung bình tùy kênh | Email account có thể bị chiếm; mã vẫn có thể bị relay. |
| TOTP | Không chống phishing | Attacker có thể lấy và relay mã trước khi hết hạn. |
| Push approval thông thường | Phụ thuộc UX/policy | Có thể bị MFA fatigue và approve nhầm. |
| Push với number matching/context | Tốt hơn push đơn giản | Giảm approve nhầm nhưng không tương đương origin-bound public-key authentication. |
| FIDO2/WebAuthn security key | Phishing-resistant khi triển khai đúng | Challenge được ký và credential gắn với RP ID/origin. |
| Passkey | Phishing-resistant theo WebAuthn origin binding | Cần quản lý sync, device, recovery và account binding. |
| Client certificate | Có thể chống phishing ở kênh được quản lý | Phụ thuộc PKI, private key protection, mapping và revocation. |

Password manager có thể giảm nguy cơ nhập password vào domain khác vì autofill thường dựa trên origin, nhưng không thay thế phương thức phishing-resistant. Đào tạo người dùng hữu ích nhưng không nên là lớp phòng thủ duy nhất.

## 6. Thiết kế WebAuthn/passkey chống phishing

WebAuthn ràng buộc assertion với relying party thông qua RP ID và origin. Authenticator ký challenge bằng private key tương ứng với credential đã đăng ký. Website giả ở domain khác không thể sử dụng credential của RP thật theo cách hợp lệ.

### 6.1. Registration ceremony

1. Người dùng đã đăng nhập hoặc hoàn tất identity proofing phù hợp trước khi thêm passkey.
2. Server tạo challenge ngẫu nhiên bằng CSPRNG, gắn với account, transaction và thời hạn.
3. Browser gọi WebAuthn API với RP ID/origin chính thức và tùy chọn đã cấu hình.
4. Authenticator tạo hoặc sử dụng credential key pair; private key ở phía authenticator.
5. Server xác minh challenge, ceremony type, origin, RP ID hash và yêu cầu user presence/user verification.
6. Server lưu credential ID, public key và metadata cần thiết cho account đã xác minh.
7. Server tiêu thụ challenge và ghi audit event.

Không liên kết credential mới với account chỉ dựa vào email do client gửi. Enrollment cần session đã xác minh và re-authentication/step-up theo policy.

### 6.2. Authentication ceremony

1. Server tạo challenge mới, ngẫu nhiên, ngắn hạn và chưa dùng.
2. Challenge được lưu cùng transaction ID, RP ID, account hint nếu có và trạng thái pending.
3. Browser yêu cầu authenticator tạo assertion.
4. Authenticator ký dữ liệu assertion bằng private key của credential.
5. Server xác minh chữ ký bằng public key đã đăng ký.
6. Server kiểm tra challenge, origin, RP ID hash, ceremony type, user handle/credential mapping và user verification policy.
7. Server tiêu thụ challenge nguyên tử; một challenge chỉ hoàn tất một lần.
8. Server tạo session ID mới sau khi authentication và policy checks hoàn tất.

### 6.3. Những điều passkey không tự giải quyết

- Thiết bị đã bị malware hoặc attacker kiểm soát có thể làm lộ session sau login.
- Recovery yếu có thể cho phép attacker đăng ký passkey mới.
- RP có thể cấu hình origin/RP ID sai hoặc kiểm tra assertion không đầy đủ.
- Phishing vẫn có thể dụ người dùng vào luồng hỗ trợ giả để thay đổi account/recovery.
- Passkey đồng bộ có cân nhắc riêng về account hệ sinh thái và khả năng khôi phục.
- Ứng dụng có thể lỗi authorization dù authentication passkey đúng.

Passkey là lớp chống phishing mạnh cho authentication ceremony, không thay thế session security, authorization, recovery assurance và endpoint protection.

## 7. Chống phishing ngoài giao thức

Các kiểm soát vận hành và giao diện cần đi cùng:

- Dùng domain đăng nhập chính thức, dễ nhận biết và được quản lý.
- Bật HTTPS và HSTS phù hợp; bảo vệ DNS, registrar và certificate lifecycle.
- Không gửi link đăng nhập từ domain không được kiểm soát.
- Tránh redirect qua domain trung gian không cần thiết.
- Không yêu cầu người dùng đọc hoặc gửi OTP/password cho support.
- Hiển thị rõ hành động đang được phê duyệt, đặc biệt với push MFA.
- Có chức năng deny/report prompt không do người dùng khởi tạo.
- Gửi cảnh báo khi password, factor hoặc recovery method thay đổi.
- Theo dõi domain giả/lookalike theo quy trình của tổ chức.
- Hướng dẫn truy cập portal qua bookmark hoặc địa chỉ đã biết; không chỉ dựa vào logo/giao diện.

HSTS giúp trình duyệt dùng HTTPS cho domain đã được ghi nhận, nhưng không ngăn người dùng truy cập domain giả có tên gần giống. Domain protection, origin-bound authentication và quy trình phản hồi phishing vẫn cần thiết.

## 8. OAuth/OIDC: state, nonce, PKCE và issuer binding

Trong Authorization Code Flow, các giá trị này có mục đích khác nhau:

| Giá trị | Vai trò | Kiểm tra ở đâu |
| --- | --- | --- |
| State | Gắn callback với authorization transaction do client khởi tạo; giảm login CSRF. | Client so sánh state callback với state đã lưu và gắn với browser transaction. |
| Nonce | Gắn ID Token với authentication request trong OIDC; giảm token substitution/replay giữa transaction. | Client xác minh nonce trong ID Token. |
| PKCE verifier/challenge | Ràng buộc authorization code với client đã khởi tạo request, giảm code interception. | Authorization Server kiểm tra verifier khi token exchange. |
| Issuer binding | Ngăn response từ authorization server này bị nhầm với server khác trong multi-issuer client. | Client kiểm tra issuer/authorization server của transaction và response. |
| Redirect URI | Giới hạn nơi authorization response được gửi tới. | Authorization Server so khớp URI theo đăng ký. |

Không coi state, nonce và PKCE là ba tên gọi cho cùng một kiểm soát. Chúng giải quyết rủi ro khác nhau và cần được kiểm tra độc lập.

### 8.1. Luồng minh họa

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant C as OAuth/OIDC Client
    participant AS as Authorization Server
    B->>C: Bắt đầu login
    C->>C: Sinh state, nonce, verifier
    C->>B: Redirect với state, nonce, challenge
    B->>AS: Authorization request
    AS->>AS: Authentication và consent
    AS-->>B: Callback code + state
    B->>C: Callback
    C->>C: Kiểm tra state và issuer transaction
    C->>AS: Code + PKCE verifier
    AS->>AS: Kiểm tra code, client, redirect URI, PKCE
    AS-->>C: Token response
    C->>C: Verify ID Token và nonce
    C->>B: Tạo session mới
~~~

Client phải lưu transaction state an toàn và tiêu thụ một lần. Không chấp nhận callback chỉ vì có code. Authorization code phải ngắn hạn, dùng một lần, gắn với client và redirect URI; token validation phải kiểm tra signature, issuer, audience, expiry và claim OIDC bắt buộc.

## 9. Chống replay cho challenge và OTP

Challenge-response chỉ chống replay nếu server quản lý state đúng cách.

Một challenge an toàn cần:

- Được sinh bằng CSPRNG.
- Có entropy phù hợp.
- Gắn với principal hoặc account transaction.
- Gắn với purpose cụ thể: login, enrollment hay recovery.
- Có expiry ngắn.
- Chỉ được chấp nhận một lần.
- Được tiêu thụ nguyên tử để chống hai request đồng thời.

OTP/TOTP có thời hạn nhưng không tự động one-time. Nếu cùng một mã còn trong time window và server chấp nhận lặp lại, attacker có thể replay mã vừa lấy được. Server nên lưu trạng thái đã dùng theo account/factor/time-step hoặc áp dụng cơ chế replay prevention tương đương.

Với push MFA, approval cần gắn với challenge/transaction cụ thể. Callback cũ, duplicate hoặc đến sau expiry không được hoàn tất login mới.

Không dùng một challenge chung cho nhiều user hoặc ceremony. Không chấp nhận challenge do client tự tạo nếu server không có transaction state tương ứng.

## 10. Chống replay cho authorization code, assertion và token

| Artifact | Rủi ro replay | Kiểm soát |
| --- | --- | --- |
| OAuth authorization code | Code bị gửi lại hoặc đổi ở client khác. | One-time code, expiry, client/redirect binding và PKCE. |
| OIDC ID Token | Token cũ bị dùng trong transaction khác. | Verify issuer/audience/expiry/nonce và transaction context. |
| SAML assertion | Assertion hợp lệ bị gửi lại. | Conditions, audience, recipient, InResponseTo và replay cache theo ID. |
| WebAuthn assertion | Assertion/challenge cũ được gửi lại. | Challenge mới, origin/RP binding và atomic one-time consume. |
| Recovery token | Link reset bị dùng lại. | Purpose-bound, short-lived, verifier storage và atomic consume. |
| Access token | Bearer token bị phát lại ở resource khác hoặc sau khi bị lộ. | Audience/scope hẹp, TTL, sender-constraining nếu phù hợp và revocation strategy. |
| Refresh token | Token cũ bị tái sử dụng sau rotation. | Rotation, reuse detection và revoke token family theo policy. |

JWT tự chứa không có replay protection chỉ vì có claim exp. Trong thời hạn, bearer token có thể được gửi nhiều lần; đây thường là semantics của access token. Nếu cần chống replay ở mức request, phải dùng sender-constrained token hoặc cơ chế request-level freshness phù hợp.

## 11. Session và cookie sau authentication

Phishing-resistant login không bảo vệ session nếu cookie bị đánh cắp. Sau khi xác thực:

1. Sinh session ID mới bằng CSPRNG.
2. Lưu session server-side trước khi gửi cookie.
3. Vô hiệu hóa pre-authentication session ID.
4. Dùng cookie Secure, HttpOnly, SameSite phù hợp và host-only khi có thể.
5. Đặt idle timeout và absolute lifetime theo rủi ro.
6. Yêu cầu re-authentication/step-up trước thao tác nhạy cảm.
7. Thu hồi session khi password/factor thay đổi, account bị khóa hoặc có incident.
8. Không đưa session ID vào URL, log, analytics hoặc support ticket.

CSRF và replay không đồng nghĩa. CSRF lợi dụng browser tự gửi credential/session; replay là gửi lại một message đã thu thập. Một request có thể cần cả CSRF token và replay protection tùy protocol/action.

## 12. Chống replay cho API request

Với API dùng HMAC hoặc request signing, chữ ký nên bao phủ các thành phần xác định request:

- HTTP method.
- Canonical path và query theo quy tắc thống nhất.
- Hash của request body.
- Timestamp.
- Nonce duy nhất.
- Key ID hoặc principal.
- Audience/service đích nếu profile hỗ trợ.

Server xác minh chữ ký, kiểm tra timestamp trong cửa sổ cho phép, kiểm tra nonce chưa dùng và ghi nhận nonce nguyên tử trước side effect. Nonce store phải có TTL ít nhất bao phủ replay window.

~~~text
signature = HMAC(
  clientSecret,
  method || canonicalPath || bodyHash || timestamp || nonce || audience
)
~~~

Đây là mô hình khái niệm; canonicalization, encoding, key derivation và signing format cần dùng profile được chuẩn hóa. Không tự phát minh giao thức HMAC production nếu có giải pháp đã được kiểm chứng phù hợp.

### 12.1. Timestamp và nonce

- Timestamp giới hạn khoảng thời gian request có thể được chấp nhận.
- Nonce phân biệt từng request trong khoảng thời gian đó.
- Timestamp đơn lẻ không ngăn hai request giống nhau được phát lại trong cùng cửa sổ.
- Nonce đơn lẻ không đủ nếu không có expiry và state cleanup.
- Đồng hồ các node cần đồng bộ; clock skew tolerance phải nhỏ và có giám sát.
- Nonce check/insert cần atomic để hai request song song không cùng vượt qua.

### 12.2. Idempotency không giống replay protection

Idempotency key giúp operation có side effect không bị thực hiện nhiều lần khi client retry sau timeout. Replay protection xác định request có phải message cũ bị phát lại hay không.

Một API thanh toán có thể cần cả hai:

- Request signature, timestamp và nonce để xác thực freshness và nguồn gửi.
- Idempotency key để retry cùng thao tác nghiệp vụ trả lại kết quả trước đó thay vì tạo giao dịch mới.

Không dùng idempotency key làm bằng chứng authentication. Không cho phép cùng key được dùng lại với body hoặc principal khác.

## 13. Account recovery không được trở thành đường bypass

Attacker có thể không phá được passkey nhưng chiếm account qua recovery. Vì vậy:

- Recovery proofing phải tương xứng với assurance của account.
- Không chỉ dựa vào thông tin cá nhân công khai hoặc câu hỏi bảo mật dễ đoán.
- Thay đổi email/phone recovery hoặc thêm factor cần xác minh mạnh và audit.
- Thông báo qua kênh hiện hữu khi factor/recovery method thay đổi.
- Có cooldown hoặc review cho thay đổi nhạy cảm theo risk policy.
- Reset token ngắn hạn, purpose-bound, dùng một lần và lưu verifier an toàn.
- Recovery operator không được xem password, OTP hoặc private key.
- Sau recovery, xem xét revoke session/token cũ và yêu cầu re-enrollment theo policy.

Recovery flow cần chống phishing và replay giống login: challenge gắn với đúng account, purpose, thời hạn và chỉ tiêu thụ một lần.

## 14. Race condition và atomic consume

Một lỗi phổ biến là kiểm tra token chưa dùng rồi mới cập nhật trạng thái ở hai thao tác riêng:

1. Request A đọc token: unused.
2. Request B đọc cùng token: unused.
3. Cả A và B cùng thực hiện hành động.
4. Cả hai mới ghi trạng thái used.

Kết quả là one-time token được chấp nhận hai lần. Cần dùng transaction, compare-and-swap hoặc thao tác atomic tương đương để chỉ một request chuyển trạng thái pending sang consumed.

Điều này áp dụng cho OTP/recovery code, WebAuthn challenge, OAuth authorization code, SAML assertion replay cache, API nonce, password reset token và push MFA callback.

Kiểm thử cần gửi hai request song song với cùng artifact và xác nhận tối đa một request thành công.

## 15. Failure mode và retry

Timeout không cho biết server đã tiêu thụ artifact hay chưa. Authorization server có thể đã đổi code thành token nhưng response bị mất; API có thể đã thực hiện thanh toán nhưng client timeout trước khi nhận kết quả.

Thiết kế cần:

- Deadline rõ ràng cho từng dependency.
- Không retry vô hạn hoặc song song một authorization code/OTP đã gửi.
- Dùng idempotency cho operation có side effect.
- Có trạng thái transaction để truy vấn kết quả không xác định khi cần.
- Không trả success nếu session/token chưa được ghi bền vững.
- Khi revoke timeout, kiểm tra trạng thái thực tế và reconciliation.
- Không hạ MFA hoặc bỏ kiểm tra chữ ký khi dependency lỗi.
- Dùng backoff/jitter và rate limit để tránh retry storm.

Khi callback đến sau expiry hoặc transaction đã bị hủy, từ chối callback. Không ghép callback cũ với login transaction mới chỉ vì account giống nhau.

## 16. Monitoring và phát hiện phishing/replay

Các tín hiệu nên theo dõi:

- Login failure tăng từ domain/referrer hoặc nguồn bất thường.
- Người dùng nhận nhiều MFA push nhưng không có login transaction tương ứng.
- OTP được chấp nhận sau nhiều lần gửi hoặc từ thiết bị/ngữ cảnh bất thường.
- Challenge, authorization code hoặc recovery token bị sử dụng lặp.
- Callback state/nonce/issuer mismatch.
- WebAuthn origin/RP ID validation failure.
- API nonce duplicate hoặc timestamp ngoài cửa sổ.
- Refresh token reuse sau rotation.
- Factor/recovery method được thêm ngay sau login rủi ro.
- Session mới xuất hiện ngay sau sự kiện phishing report.

Audit event nên có timestamp, transaction reference, principal reference giả danh, client/issuer, factor type, result và reason category. Không log password, OTP, authorization code, access/refresh token, cookie, private key hoặc recovery secret.

Một cảnh báo riêng lẻ chưa chứng minh compromise. Kết hợp tín hiệu, kiểm tra correlation và dùng quy trình incident response đã phê duyệt.

## 17. Ứng phó khi nghi ngờ phishing hoặc replay

Khi người dùng báo đã nhập password/OTP vào trang giả hoặc hệ thống phát hiện replay:

1. Ghi nhận thời điểm, domain, thiết bị và account bị ảnh hưởng; yêu cầu người dùng không tiếp tục tương tác với trang giả.
2. Tạm dừng hoặc giới hạn account theo incident policy nếu có dấu hiệu compromise.
3. Thu hồi session và refresh token; đánh giá access token còn hiệu lực và thời gian hết hạn.
4. Reset password từ domain chính thức và thiết bị sạch nếu password có thể đã bị lộ.
5. Kiểm tra factor, passkey, recovery email/phone và authenticator mới được thêm.
6. Thu hồi factor/session/token không nhận diện và kiểm tra account linking.
7. Kiểm tra OAuth grants, app consent, API keys và certificate nếu account có quyền tương ứng.
8. Tìm request trùng, nonce reuse, authorization code reuse hoặc callback bất thường trong audit.
9. Kiểm tra hành động sau login: export dữ liệu, thay đổi quyền, tạo account hoặc thay đổi recovery.
10. Bảo toàn evidence, thông báo theo incident/privacy policy và theo dõi tăng cường sau khôi phục.

Chỉ đổi password là chưa đủ nếu attacker đã đăng ký factor mới, tạo OAuth grant hoặc giữ session còn hiệu lực.

## 18. Bộ kiểm thử end-to-end

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| P01 | Người dùng mở domain giả và nhập password/TOTP | Phương thức phishing-resistant không ký cho origin giả; có kênh report và cảnh báo phù hợp. |
| P02 | Reverse proxy relay password và OTP trong thời gian thực | MFA phish-resistant chặn việc dùng credential tại origin giả. |
| P03 | WebAuthn assertion có origin không nằm trong allowlist | Server từ chối. |
| P04 | WebAuthn assertion dùng RP ID hash sai | Server từ chối. |
| P05 | Challenge WebAuthn đã dùng được gửi lại | Request thứ hai bị từ chối. |
| P06 | Hai request đồng thời dùng cùng challenge | Tối đa một request được chấp nhận. |
| P07 | OAuth callback có state sai/thiếu/hết hạn | Client từ chối callback. |
| P08 | ID Token nonce không khớp | Client từ chối token. |
| P09 | Authorization code đổi lần thứ hai | Authorization Server từ chối code đã dùng. |
| P10 | PKCE verifier sai | Token exchange thất bại. |
| P11 | Callback từ issuer khác transaction | Client từ chối issuer mix-up. |
| P12 | SAML assertion ID được phát lại | SP từ chối theo replay cache. |
| P13 | OTP đúng được gửi lại trong cùng time window | Server từ chối nếu đã tiêu thụ theo replay policy. |
| P14 | API request có nonce trùng | Server từ chối request replay. |
| P15 | API request timestamp quá cũ hoặc quá xa tương lai | Server từ chối. |
| P16 | Cùng idempotency key và cùng operation được retry | Trả kết quả đã ghi nhận, không lặp side effect. |
| P17 | Recovery token đã dùng hoặc hết hạn | Không cho đổi password/factor lần nữa. |
| P18 | Session cookie bị replay sau revoke | Server từ chối session. |
| P19 | MFA provider timeout | Không tự động downgrade sang password-only. |
| P20 | Log login/callback/API request | Không chứa password, OTP, token, cookie hoặc private key. |

Chạy negative test trong staging hoặc môi trường được phép, dùng account và credential synthetic. Không thử phishing hoặc replay trên tài khoản thật khi chưa có authorization.

## 19. Kế hoạch triển khai theo giai đoạn

1. **Inventory:** liệt kê login method, MFA, IdP, callback, session, API signing và recovery path.
2. **Baseline:** đo login success/failure, MFA denial, callback mismatch, duplicate request và session revoke lag.
3. **Domain controls:** chuẩn hóa domain login, TLS/HSTS, redirect allowlist và thông báo bảo mật.
4. **Phishing-resistant rollout:** triển khai passkey/security key cho admin và nhóm rủi ro cao; hỗ trợ enrollment và recovery an toàn.
5. **OAuth/OIDC hardening:** kiểm tra PKCE, state, nonce, issuer binding, redirect URI và token validation.
6. **Replay controls:** one-time challenge/code, atomic consume, replay cache, timestamp/nonce cho API theo profile.
7. **Session/recovery hardening:** session rotation/revocation, CSRF controls, recovery proofing và factor change alerts.
8. **Monitoring:** cảnh báo phishing report, challenge reuse, callback mismatch, token reuse và factor changes.
9. **Exercise:** chạy negative test, race test, incident tabletop và recovery drill.
10. **Review:** kiểm tra false positive, usability, latency và fallback trước khi mở rộng toàn tổ chức.

Triển khai theo nhóm và có rollback plan. Không bật fallback yếu hơn chỉ để tăng adoption; cần đo tỷ lệ enrollment và xử lý người dùng chưa thể dùng factor mới theo policy rõ ràng.

## 20. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ đào tạo người dùng nhận diện phishing | Người dùng vẫn có thể bị lừa hoặc nhầm domain. | Dùng origin-bound authentication và domain controls. |
| Coi TOTP là phishing-resistant vì mã hết hạn nhanh | Attacker có thể relay mã trước expiry. | Ưu tiên passkey/security key và transaction binding. |
| Dùng push approve một chạm | MFA fatigue dẫn tới approve nhầm. | Number matching/context, rate limit và deny/report. |
| Chỉ kiểm tra chữ ký WebAuthn | Assertion có thể sai challenge, origin hoặc RP ID. | Kiểm tra đầy đủ ceremony và atomic challenge consume. |
| Chỉ kiểm tra timestamp để chống replay | Message có thể phát lại nhiều lần trong cửa sổ. | Timestamp + nonce/replay state và atomic check. |
| Coi JWT exp là replay prevention | Bearer token vẫn dùng lại được trước expiry. | Audience/scope/TTL, sender constraint hoặc request-level replay control. |
| Không ràng buộc state/nonce/PKCE đúng mục đích | CSRF, code interception hoặc token substitution. | Kiểm tra độc lập từng cơ chế theo OIDC profile. |
| Không có issuer binding trong multi-IdP client | Authorization server mix-up. | Gắn issuer với transaction và kiểm tra callback. |
| Kiểm tra token rồi mới lưu trạng thái used ở bước riêng | Race condition cho phép hai request thành công. | Atomic consume/transaction/CAS. |
| Recovery yếu hơn login | Attacker thêm factor hoặc reset password để chiếm account. | Recovery assurance tương xứng, approval và audit. |
| Không revoke session sau compromise | Attacker tiếp tục dùng cookie/token đã lấy. | Revoke session/token family và xác minh trạng thái. |
| Dùng idempotency key thay authentication | Caller không hợp lệ có thể gửi operation nếu thiếu auth. | Xác thực request riêng; idempotency chỉ kiểm soát side effect trùng. |

## 21. Bài tập thực hành

1. Vẽ login flow hiện tại của một ứng dụng và đánh dấu nơi password, OTP, code, token hoặc cookie đi qua.
2. Chọn ba trust boundary có rủi ro cao nhất và ghi peer authentication, integrity, freshness, audience và logging control cho mỗi boundary.
3. Mô tả cách reverse proxy phishing lấy password/TOTP và giải thích tại sao WebAuthn origin binding thay đổi kết quả.
4. Thiết kế state, nonce và PKCE transaction cho OIDC; nêu nơi tạo, lưu, kiểm tra và tiêu thụ từng giá trị.
5. Đề xuất cách lưu và tiêu thụ WebAuthn challenge để hai request song song không cùng thành công.
6. Thiết kế request signing có method, path, body hash, timestamp, nonce và audience; mô tả replay cache.
7. Viết negative test cho recovery token, refresh token rotation và API nonce reuse.
8. Lập runbook khi một nhân viên báo đã nhập password/OTP vào domain giả.

## 22. Checklist tổng kết

Trước khi phê duyệt một luồng authentication:

- [ ] Đã mô hình hóa attacker, asset, actor và trust boundary.
- [ ] Đã phân biệt phishing, relay, replay, CSRF và session theft.
- [ ] Nhóm rủi ro cao dùng phương thức phishing-resistant theo policy.
- [ ] WebAuthn kiểm tra challenge, origin, RP ID, signature và user verification.
- [ ] Challenge được gắn với principal, purpose, transaction và expiry.
- [ ] Challenge/OTP/code/assertion được tiêu thụ một lần theo thao tác atomic.
- [ ] OAuth/OIDC kiểm tra state, nonce, PKCE, redirect URI và issuer binding.
- [ ] Token kiểm tra signature, issuer, audience, type, expiry và scope.
- [ ] SAML assertion có audience/recipient/time validation và replay protection.
- [ ] Session ID được xoay, cookie được bảo vệ và CSRF được xử lý.
- [ ] API signing ràng buộc method/path/body/timestamp/nonce/audience.
- [ ] Idempotency và replay protection được phân biệt và áp dụng đúng.
- [ ] Recovery không tạo đường bypass MFA hoặc factor enrollment yếu.
- [ ] Timeout, retry và callback trễ không hoàn tất transaction đã hết hạn.
- [ ] Monitoring phát hiện challenge reuse, callback mismatch, token reuse và factor change.
- [ ] Incident response có thể revoke session/token, credential và recovery mapping.
- [ ] Negative/race tests được chạy trong môi trường được phép.

**Kết luận:** Chống phishing đòi hỏi bằng chứng xác thực được ràng buộc với đúng origin hoặc relying party; passkey/WebAuthn cung cấp cơ chế này tốt hơn password và OTP có thể bị relay. Chống replay đòi hỏi mỗi challenge/message được ràng buộc với đúng principal, transaction, purpose, audience và thời hạn, đồng thời được tiêu thụ nguyên tử khi chỉ được dùng một lần. Session, token, recovery và API request đều phải được bảo vệ sau bước login. Hãy kiểm thử happy path, negative path và race condition để xác nhận attacker không thể chuyển tiếp hoặc tái sử dụng bằng chứng hợp lệ ngoài ngữ cảnh ban đầu.
