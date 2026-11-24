# Credential trong log

## 1. Vì sao credential trong log là rủi ro nghiêm trọng?

Log giúp vận hành và bảo vệ hệ thống: điều tra lỗi đăng nhập, phát hiện credential stuffing, theo dõi token refresh, phân tích sự cố và chứng minh hành động quản trị. Nhưng log thường được sao chép qua nhiều thành phần: application logger, agent, queue, collector, search index, SIEM, data warehouse, backup và nhà cung cấp bên ngoài. Nếu password, OTP, recovery code, session cookie, access token hoặc private key lọt vào một event, credential có thể tồn tại ở nhiều nơi lâu hơn thời hạn của chính nó.

**Credential trong log** là mọi trường hợp dữ liệu có thể xác thực, cấp quyền, khôi phục hoặc giúp chiếm phiên xuất hiện trong log, trace, metric label, crash report, analytics event, audit payload hoặc công cụ support. Rủi ro không chỉ là ghi nguyên password. Một URL chứa reset token, header Authorization, QR code TOTP, WebAuthn challenge response, cookie session hay exception có nhúng request object đều có thể làm lộ credential.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, chủ đề này kết nối password, MFA, passkey, certificate, token, session, account recovery, privacy và incident response. Thiết kế tốt phải ngăn secret đi vào telemetry ngay tại nguồn, chỉ ghi những thuộc tính cần cho quan sát và điều tra, kiểm soát mọi bản sao đã thu thập và có quy trình xử lý khi phát hiện rò rỉ.

Sau bài học, người học có thể:

- Nhận diện credential và dữ liệu có khả năng cấp quyền trong log.
- Phân biệt credential secret, identifier, metadata và correlation reference.
- Thiết kế structured logging theo allowlist.
- Redact header, URL, request body, exception và trace attribute.
- Tránh ghi password, OTP, token, cookie, recovery code và private key.
- Tạo reference phục vụ correlation mà không tạo bearer credential mới.
- Bảo vệ log pipeline, crash reporting, analytics và support tooling.
- Thiết lập access control, retention, deletion và audit cho log.
- Xử lý incident khi credential đã lọt vào log hoặc vendor.
- Viết test xác nhận secret không xuất hiện trong bất kỳ telemetry output nào.

## 2. Credential nào tuyệt đối không được ghi?

Một nguyên tắc an toàn là coi mọi giá trị có thể được dùng trực tiếp hoặc gián tiếp để xác thực, ký, giải mã hay khôi phục tài khoản là secret. Không cần biết credential có thời hạn ngắn hay chỉ dùng một lần; trong thời gian còn hiệu lực, nó vẫn có thể bị lạm dụng.

| Credential hoặc dữ liệu | Vì sao nhạy cảm | Cách xử lý trong log |
| --- | --- | --- |
| Password và password confirmation | Có thể đăng nhập trực tiếp; người dùng thường tái sử dụng | Không ghi; redact body ngay tại ingress |
| OTP, TOTP code | Có thể hoàn tất MFA trong cửa sổ hiệu lực | Không ghi giá trị; chỉ ghi factor type và result |
| TOTP seed/provisioning URI | Tạo được mã TOTP trong tương lai | Không ghi, không chụp QR enrollment |
| Recovery/backup code | Có thể khôi phục hoặc vượt MFA | Không ghi; chỉ ghi event và code reference nếu cần |
| Session cookie/session ID | Có thể hoạt động như bearer credential | Không ghi raw value; dùng reference không thể replay |
| Access token | Có thể truy cập API theo scope/audience | Không ghi token; chỉ ghi issuer/client/audience và token reference phù hợp |
| Refresh token | Có thể cấp access token mới hoặc duy trì session | Không ghi; xử lý như credential cấp cao |
| ID token | Có thể chứa identity claims và được dùng sai ngữ cảnh | Không ghi raw token; chỉ ghi claim tối thiểu đã xác minh nếu cần |
| Client secret/API key | Có thể xác thực client hoặc integration | Không ghi; dùng key ID/reference |
| Private key/HMAC secret | Có thể ký hoặc tạo MAC hợp lệ | Không ghi dưới bất kỳ dạng nào |
| Certificate keystore export/password | Có thể mở khóa private key hoặc kho khóa | Không ghi |
| Reset/activation/magic link token | Có thể chiếm account hoặc kích hoạt credential | Không ghi URL đầy đủ hoặc token |
| OAuth authorization code/state/verifier | Có thể hoàn tất hoặc chiếm flow nếu bị lộ | Không ghi giá trị; ghi transaction reference |
| WebAuthn assertion/response | Có thể chứa dữ liệu xác thực và signature | Không ghi raw payload mặc định; chỉ ghi kết quả/metadata cần thiết |
| Biometric template/ảnh | Dữ liệu nhạy cảm khó thay đổi | Không thu thập hoặc ghi; OS quản lý cục bộ |
| Signed request hoặc webhook secret | Có thể tái tạo request được tin cậy | Không ghi key hoặc signature payload đầy đủ nếu không cần |

### 2.1. Secret khác identifier

Email, username, account ID hoặc client ID thường không phải credential có thể dùng trực tiếp để đăng nhập, nhưng vẫn có thể là dữ liệu cá nhân hoặc thông tin nhạy cảm. Không nên log rộng rãi chỉ vì chúng không phải secret.

Cần phân biệt:
- **Secret:** nếu lộ có thể dùng để xác thực, cấp quyền, giải mã hoặc khôi phục.
- **Identifier:** giúp tìm hoặc liên kết một account, người dùng, thiết bị hay integration.
- **Metadata:** mô tả loại credential, issuer, expiry, factor type hoặc kết quả.
- **Correlation reference:** giá trị giả danh để nối các event mà không cho phép dùng lại credential.
- **Public cryptographic material:** public key/certificate có thể không bí mật, nhưng mapping với người dùng hoặc thiết bị vẫn cần bảo vệ.

### 2.2. Credential ngắn hạn vẫn là secret

OTP 30 giây, authorization code dùng một lần hoặc reset token có thời hạn ngắn vẫn có thể bị khai thác trong cửa sổ hiệu lực. Log thường được truy cập sau sự kiện và có thể giữ lâu hơn nhiều. Không ghi credential với lý do “nó sắp hết hạn”.

### 2.3. Hash không tự động làm dữ liệu an toàn

Hash password verifier vẫn là dữ liệu bảo mật có giá trị cao vì có thể hỗ trợ offline guessing. Hash email có thể bị dò từ danh sách phổ biến. Hash session ID không keyed có thể tạo correlation ổn định và có rủi ro nếu entropy thấp.

Nếu cần correlation, chọn cơ chế phù hợp như HMAC với key riêng, version hóa key và access control. Đây vẫn là pseudonymous data nếu tổ chức có khả năng liên kết lại.

## 3. Nguyên tắc thiết kế: ngăn từ nguồn

Redaction tại dashboard hoặc search UI không đủ. Secret có thể đã được gửi tới log collector, message queue, vendor hoặc backup trước khi người vận hành nhìn thấy nó.

Một pipeline an toàn nên theo các nguyên tắc:

1. **Allowlist fields:** chỉ ghi các field đã được phê duyệt.
2. **Redact at source:** loại secret trước khi serialize hoặc gửi event ra process.
3. **Structured logging:** dùng field có schema thay vì nối nguyên request/exception thành chuỗi.
4. **No raw request/response dump:** không ghi toàn bộ body, headers, cookies hoặc environment.
5. **Safe correlation:** dùng request ID và pseudonymous references, không dùng credential làm ID.
6. **Pipeline controls:** giới hạn quyền đọc, export, retention và vendor access.
7. **Regression tests:** kiểm tra secret không lọt qua log, trace, metric, crash report và telemetry.

### 3.1. Allowlist tốt hơn denylist

Denylist thường bắt đầu bằng việc loại một vài tên field như password hoặc token. Nó dễ bỏ sót tên khác như passwd, secretValue, otpCode, refresh, authorization, cookie, credential, resetKey hoặc dữ liệu lồng sâu trong object.

Allowlist xác định chính xác field nào được phép ghi, ví dụ event_type, timestamp, result, reason_code, client_type và correlation_id. Field mới không tự động xuất hiện trong log cho đến khi được review.

### 3.2. Không serialize object tùy tiện

Các anti-pattern thường gặp:
- Ghi toàn bộ request object.
- Ghi toàn bộ response object.
- Gọi toString() trên authentication context.
- Ghi exception có nhúng URL hoặc header.
- Ghi toàn bộ environment variables.
- Ghi toàn bộ HTTP headers để debug.
- Ghi object ORM có password hash hoặc recovery metadata.

Tạo log event riêng với field rõ ràng. Không để logger tự phản chiếu toàn bộ object hoặc gọi getter có side effect.

## 4. Xác định điểm credential có thể lọt vào log

Credential có thể xuất hiện ở nhiều lớp, không chỉ trong code login.

| Điểm phát sinh | Ví dụ rò rỉ | Kiểm soát |
| --- | --- | --- |
| Reverse proxy/load balancer | Authorization, Cookie, query string | Header/query redaction tại edge |
| API gateway | Request dump, token validation error | Allowlist fields, không log raw token |
| Application middleware | Body logging, debug filter | Bỏ qua/redact authentication routes |
| Authentication service | Password/OTP trong exception | Không truyền secret vào message |
| Database driver | Query parameter logging | Disable bind parameter logging cho secret |
| HTTP client | URL có reset token, request headers | Safe URL và header filter |
| Distributed tracing | Span attribute chứa token hoặc email | Attribute allowlist và processor redaction |
| Metrics | Label chứa user ID, email hoặc session ID | Bounded-cardinality labels |
| Crash reporting | Memory/context/request snapshot | Mask field và disable capture ở màn hình nhạy cảm |
| Analytics/session replay | Input, DOM, screenshot | Disable hoặc mask authentication flow |
| CI/CD | Secret in command output | Secret masking và tránh echo |
| Support tool | Ticket chứa reset link hoặc OTP | Không yêu cầu secret; redact attachment |
| Browser console | Token hoặc form data trong debug | Không console.log credential |
| Mobile diagnostics | Keychain/Keystore values hoặc request dump | Safe diagnostic schema |

### 4.1. Request body

Không bật body logging trên endpoint:
- Login/password verification.
- Password reset/change.
- MFA enrollment/verification.
- Recovery code.
- Passkey registration/authentication.
- OAuth token endpoint.
- Client credential exchange.
- API key creation/rotation.
- Certificate enrollment.

Nếu cần debug lỗi validation, chỉ log tên field hoặc reason code tổng quát, không log giá trị.

### 4.2. Header

Các header thường chứa credential:
- Authorization.
- Cookie.
- Set-Cookie.
- Proxy-Authorization.
- X-API-Key hoặc header API key riêng.
- Signature hoặc request authentication header.
- Header chứa CSRF token.
- Header custom mang assertion hoặc identity context nhạy cảm.

Redaction phải không phân biệt chữ hoa/thường của tên header và cần xử lý header lặp. Không chỉ che Authorization ở application logger nếu proxy trước đó vẫn ghi raw header.

### 4.3. URL và query string

Không đặt credential trong URL. URL thường được ghi ở access log, browser history, proxy, analytics và Referer. Những giá trị cần tránh:
- reset token.
- magic login token.
- authorization code.
- API key.
- session ID.
- email hoặc phone khi không cần.
- query parameter có chứa assertion.

Nếu một flow hiện tại bắt buộc có token trong URL, cần dùng one-time short-lived token, giảm exposure, hạn chế Referer, không tải third-party resource trên trang landing và redact query tại mọi hop. Ưu tiên thiết kế lại để token được gửi qua POST/body hoặc cơ chế protocol an toàn hơn.

### 4.4. Exception và stack trace

Exception message có thể chứa URL, SQL bind parameter, request headers hoặc object state. Không nối secret vào exception text. Ghi reason code an toàn và correlation ID; giữ diagnostic detail trong memory hoặc kênh kiểm soát riêng nếu thật sự cần.

Stack trace thường hữu ích nhưng không nên kèm raw request, token hoặc toàn bộ local variables. Crash dump có thể chứa dữ liệu trong memory; đặt access, encryption, retention và capture policy riêng.

## 5. Structured logging cho authentication

Structured logging lưu event dưới dạng field có kiểu dữ liệu, giúp truy vấn chính xác và áp dụng schema validation. Với authentication, schema cần cố định và giới hạn dữ liệu.

Một event login thất bại có thể ghi:

~~~json
{
  "event_type": "auth.login",
  "event_time": "2026-11-22T08:45:12Z",
  "result": "failure",
  "reason_code": "credential_rejected",
  "client_type": "web",
  "auth_method": "password",
  "principal_ref": "pseud:v2:8f31...",
  "correlation_id": "req-2d91...",
  "environment": "production"
}
~~~

Ví dụ trên không chứa password, email, raw session ID hoặc token. Schema cụ thể cần được đội vận hành và privacy owner review.

### 5.1. Field nên có

Tùy event, có thể cân nhắc:
- event_type.
- event_time UTC.
- event_id.
- result: success/failure/challenge/denied.
- reason_code thuộc enum đã định nghĩa.
- auth_method category.
- client/application reference.
- issuer reference.
- principal reference đã pseudonymize.
- tenant reference nếu thực sự cần.
- correlation_id/trace_id.
- region/environment.
- policy version hoặc authentication context category.

Không cần mọi event đều có mọi field. Ghi tối thiểu đủ để vận hành và điều tra.

### 5.2. Field không nên có

Không đưa vào schema:
- password/password confirmation.
- OTP/TOTP/recovery code.
- session cookie hoặc bearer token.
- refresh token.
- private key hoặc secret.
- raw WebAuthn response mặc định.
- raw biometric result/template.
- reset URL đầy đủ.
- toàn bộ request body/header.
- full IP/device fingerprint nếu không có purpose rõ ràng.

Schema validator có thể từ chối event nếu xuất hiện key nhạy cảm hoặc field ngoài allowlist.

### 5.3. Reason code thay cho exception detail

Thay vì log “password abc... for user x failed because ...”, dùng reason code như credential_rejected, account_policy_denied, factor_timeout, token_expired hoặc session_revoked. Chi tiết nội bộ cần thiết có thể nằm trong audit system có quyền hạn chặt hơn, nhưng vẫn không chứa secret.

Reason code bên ngoài và bên trong có thể khác nhau. Client chỉ cần thông tin an toàn; security operator có thể cần category chi tiết hơn.

## 6. Redaction và masking

Redaction loại bỏ giá trị nhạy cảm trước khi lưu. Masking thay một phần giá trị bằng ký tự che, nhưng không phải lúc nào cũng an toàn.

Ví dụ:
- Email có thể hiển thị dạng đã mask trong UI support nếu cần nhận diện.
- Token nên bị loại hoàn toàn, không chỉ che vài ký tự.
- Session ID không nên log prefix/suffix có thể hỗ trợ replay hoặc correlation ngoài ý muốn.
- Password và OTP không bao giờ nên được mask một phần trong log; không ghi chúng.

### 6.1. Redact trước khi serialize

Luồng an toàn:

~~~text
request arrives
    -> identify sensitive route and fields
    -> build allowlisted event
    -> redact approved sensitive metadata
    -> schema validation
    -> serialize event
    -> send to collector
~~~

Không serialize toàn bộ object rồi dùng regex thay secret trong chuỗi đã tạo. Regex có thể bỏ sót encoding, nested JSON, multiline value hoặc tên field mới.

### 6.2. Redaction theo schema

Redaction nên hiểu cấu trúc dữ liệu:
- Header names không phân biệt hoa thường.
- JSON nested fields.
- Form field names.
- URL query parameters.
- Multipart upload metadata.
- Exception attributes.
- Trace span attributes.
- Mobile crash breadcrumbs.

Với field có tên bất thường hoặc không được biết, allowlist nên loại khỏi event. Không cố đoán mọi tên secret.

### 6.3. Masking không thay thế minimization

Nếu event không cần email, đừng ghi email dạng a***@example.test. Nếu không cần token, đừng ghi eyJ...***. Giữ ít dữ liệu nhất có thể sẽ giảm rủi ro tốt hơn việc che một phần.

## 7. Correlation an toàn

Điều tra incident cần liên kết các event của cùng request, session hoặc principal. Nhưng dùng raw credential làm correlation key tạo thêm đường lộ.

### 7.1. Request ID và trace ID

Sinh request ID/trace ID ngẫu nhiên, không chứa user ID, token hoặc session ID. Truyền qua các service theo quy tắc tin cậy. Không cho client tự chọn giá trị tùy ý làm identity proof; có thể nhận traceparent theo chuẩn nhưng cần kiểm tra kích thước/format và không dùng nó làm quyền.

### 7.2. Pseudonymous principal reference

Nếu cần nối nhiều event của một principal, có thể tạo keyed HMAC trên stable internal identifier bằng key dành riêng cho telemetry:

~~~text
principal_ref = HMAC(telemetry_key_version, internal_principal_id)
~~~

Key telemetry phải khác password pepper, token signing key hoặc application secret. Cần version hóa để có thể rotate và kiểm soát ai có thể tạo/tra mapping. HMAC reference vẫn là dữ liệu giả danh, không phải anonymous tuyệt đối.

### 7.3. Session reference

Có thể tạo session reference riêng cho audit bằng HMAC của session identifier với key telemetry. Không dùng raw session ID, cookie value hoặc hash không keyed. Reference không được chấp nhận ở bất kỳ endpoint xác thực nào.

Không dùng cùng một reference cho mọi hệ thống nếu điều đó tạo khả năng theo dõi người dùng xuyên dịch vụ ngoài mục đích cần thiết.

### 7.4. Token reference

Với JWT, claim jti hoặc token fingerprint có thể giúp điều tra nhưng cần đánh giá privacy và correlation. Không log toàn bộ token để lấy jti. Nếu cần reference, parse token sau khi validation và chỉ ghi claim/reference cần thiết theo policy. Opaque token có thể dùng keyed digest của token ở hệ thống nội bộ, không lưu raw bearer value.

## 8. Password, MFA và recovery logging

### 8.1. Password

Không log password kể cả khi:
- Login thất bại.
- Password policy validation thất bại.
- Password reset thành công.
- Password bị từ chối vì breached password list.
- Người dùng nhập password mới hai lần không khớp.

Chỉ ghi event type, result, reason code và correlation reference. Password verifier hash cũng không nên xuất hiện trong application log hoặc support export.

### 8.2. OTP và TOTP

Không log OTP nhập vào, TOTP seed, provisioning URI hoặc QR image. Có thể ghi:
- factor type.
- challenge issued/verified/expired.
- result category.
- attempt count theo aggregate.
- challenge reference.
- throttling/lockout event.

Không ghi mã OTP ngay cả khi đã hết hạn; log có thể được truy cập sau đó và mã có thể trùng với một mã mới trong cửa sổ khác.

### 8.3. Push MFA

Không log push approval secret, deep link có token hoặc payload chứa challenge secret. Có thể ghi challenge ID, device reference, sent/delivered/approved/denied/timeout và thời điểm.

Push notification content nên tối thiểu. Không đưa dữ liệu giao dịch, account recovery detail hoặc thông tin cá nhân vào lock-screen notification nếu không cần.

### 8.4. Recovery code và password reset

Recovery code và reset token phải được coi như credential. Không log link đầy đủ, request body hoặc email template chứa token. Với email delivery, chỉ log message ID, destination reference đã mask theo policy, template ID và delivery status.

Khi reset password, event có thể ghi password_reset.completed và session_revoke_count, nhưng không ghi password cũ/mới hoặc reset token.

## 9. Token, cookie và certificate logging

### 9.1. Access và refresh token

Không log Authorization header hoặc raw token trong bất kỳ layer nào. Khi validation thất bại, ghi reason code như expired, invalid_signature, wrong_audience hoặc revoked mà không kèm token.

Không gửi token vào metric label, trace baggage, URL hoặc support ticket. Bảo đảm reverse proxy và WAF cũng redact.

### 9.2. Session cookie

Không log Cookie hoặc Set-Cookie header. Session ID có thể là bearer credential. Khi cần audit, dùng session reference không thể dùng để xác thực và lưu mapping trong hệ thống hạn chế quyền.

### 9.3. Certificate

Certificate public có thể được chia sẻ trong giao thức, nhưng log vẫn nên tối thiểu:
- issuer reference.
- certificate serial hoặc fingerprint nếu cần điều tra.
- subject/SAN đã giảm nhạy cảm.
- expiry và validation result.
- trust chain result.

Không log private key, keystore password, PFX/P12 content hoặc enrollment secret. Certificate serial/fingerprint liên kết với một thiết bị/service vẫn có thể là identifier.

### 9.4. Private key operation

Khi ký thất bại, ghi key reference, algorithm category, operation result và error code. Không dump private key object, keystore content hoặc HSM response chứa material nhạy cảm.

## 10. Trace, metric và crash reporting

Credential có thể lọt vào telemetry ngoài log truyền thống.

### 10.1. Distributed trace

Span attributes có thể chứa:
- HTTP URL đầy đủ.
- Request/response headers.
- Query string.
- User ID/email.
- Authorization result.
- Error message.
- Database statement và bind values.

Cấu hình instrumentation để loại Authorization, Cookie, Set-Cookie, password fields và query parameters nhạy cảm. Dùng URL template/route name thay URL đầy đủ. Không đặt token hoặc email vào span name.

### 10.2. Metric labels

Không dùng password/token/session ID/email/user ID/IP raw làm label. Những giá trị này vừa tạo cardinality cao vừa tăng rủi ro privacy. Dùng enum như auth_method, result, reason_class, client_type và environment.

Không tạo metric riêng cho mỗi principal hoặc session. Điều tra cá nhân qua audit store có kiểm soát.

### 10.3. Crash report và memory dump

Crash reporter có thể thu:
- Breadcrumb.
- Screenshot.
- Network request.
- Local variables.
- Memory snapshot.
- Device metadata.
- URL hiện tại.

Tắt hoặc mask capture trên login, MFA, recovery và credential management screens. Không gửi memory dump chứa token/private key tới vendor nếu chưa có kiểm soát phù hợp. Crash report vẫn là telemetry có retention và access policy.

### 10.4. Browser console và mobile diagnostics

Không console.log form values, headers hoặc token. Không đưa secret vào debug menu, clipboard history hoặc diagnostic bundle. Build production nên tắt verbose authentication debugging; nếu cần debug tạm thời, dùng synthetic credential trong môi trường test.

## 11. Log pipeline và third-party provider

Một event có thể đi qua nhiều hệ thống. Mỗi hop cần được xem là một trust boundary:

~~~mermaid
flowchart LR
    A[Application / Gateway] --> B[Source redaction + schema]
    B --> C[Agent / Collector]
    C --> D[Queue]
    D --> E[Log store / SIEM]
    E --> F[Dashboard / Alert]
    E --> G[Archive / Backup]
    E --> H[Approved vendor]
~~~

### 11.1. Redaction tại nhiều lớp

Redaction tại source là bắt buộc. Có thể bổ sung filter ở proxy, collector và storage để phòng lỗi, nhưng không dùng downstream filter làm biện pháp duy nhất.

Nếu proxy access log đã ghi query string trước khi application redaction chạy, secret đã bị lộ. Cần kiểm tra toàn bộ đường đi từ edge tới archive.

### 11.2. Vendor và data processing

Trước khi gửi log ra ngoài tổ chức, đánh giá:
- Vendor nhận field nào.
- Data location và transfer.
- Subprocessor.
- Retention/deletion.
- Access control và support access.
- Encryption in transit/at rest.
- Incident notification.
- Export/API access.
- Model training hoặc secondary use nếu dịch vụ có tính năng đó.

Không gửi raw authentication event tới vendor analytics chỉ vì họ cung cấp dashboard tiện lợi. Dùng event đã tối thiểu hóa và có hợp đồng xử lý phù hợp.

### 11.3. Queue và dead-letter queue

Message queue và dead-letter queue có thể giữ event lỗi lâu hơn log store. Kiểm tra payload trước khi enqueue, quyền đọc queue, retry policy, retention và cách xóa. Không giả định message chưa được consumer xử lý là không ai có thể đọc.

### 11.4. Backup và export

Log export, CSV download, archive và backup đều là bản sao dữ liệu. Đặt quyền, encryption, retention và deletion tương ứng. Không cho phép operator tải raw authentication logs về laptop cá nhân để điều tra.

## 12. Access control, integrity và retention

Log bảo mật có thể chứa identifier, IP, device metadata và thông tin sự kiện nhạy cảm dù đã loại secret. Cần bảo vệ theo least privilege.

### 12.1. Role-based access

Ví dụ phân quyền:
- Developer xem log môi trường dev/test với dữ liệu tổng hợp.
- On-call xem event production đã giảm nhạy cảm.
- Security analyst truy cập audit detail theo case.
- Support xem trạng thái account và reason tổng quát.
- Privacy/legal xử lý yêu cầu dữ liệu theo workflow.
- Platform admin quản lý pipeline nhưng không mặc định đọc secret.

Tách quyền xem log, export, sửa retention, quản trị collector và xóa archive. Không để một role vừa sửa authentication policy vừa xóa audit evidence mà không có kiểm soát.

### 12.2. Audit access vào log

Ghi lại ai truy vấn, export hoặc thay đổi cấu hình log. Audit log access không được chứa query nhạy cảm hoặc raw token. Với thao tác export lớn, yêu cầu approval hoặc reason code.

### 12.3. Retention

Đặt retention theo mục đích:
- Operational metrics có thể giữ dạng aggregate dài hơn.
- Authentication event detail giữ theo security investigation need.
- High-risk incident evidence có thể có legal hold.
- Raw network/device signal cần retention ngắn hơn nếu không cần lâu.
- Secret bị ghi nhầm cần purge khẩn cấp theo incident plan.

Không giữ raw login logs vô thời hạn. Đặt owner và automation để xóa ở primary store, replica, index, archive, queue, vendor và backup theo khả năng.

### 12.4. Tamper resistance

Audit evidence quan trọng cần chống sửa/xóa trái phép:
- Quyền ghi một chiều hoặc append-only.
- Storage retention lock/WORM khi phù hợp.
- Integrity checksum hoặc signing chain theo threat model.
- Đồng bộ thời gian.
- Tách quyền quản trị audit store.
- Alert khi log gap hoặc pipeline bị tắt.

Không dùng hash chain như một biện pháp thay thế access control và backup. Integrity mechanism cần key management và kiểm tra độc lập.

## 13. Incident response khi credential đã lọt vào log

Khi phát hiện credential trong log, coi đây là một sự cố bảo mật. Việc xóa dòng log trên dashboard không thu hồi credential và không xóa bản sao khác.

Quy trình:
1. Xác định loại credential, account/client, issuer, audience và phạm vi quyền.
2. Xác định thời điểm credential bị ghi và thời gian log đã được lưu/chia sẻ.
3. Tìm tất cả bản sao: application log, proxy, collector, queue, SIEM, trace, crash report, export, archive, backup và vendor.
4. Đánh giá credential còn hiệu lực không và có dấu hiệu đã bị truy cập không.
5. Revoke/rotate credential hoặc session theo mức rủi ro.
6. Nếu là password, yêu cầu đổi password và xử lý session/token liên quan theo policy.
7. Nếu là refresh token, revoke token family; nếu là API key/certificate, disable hoặc rotate key.
8. Hạn chế quyền truy cập log và export liên quan.
9. Purge hoặc quarantine bản sao theo incident/legal policy; ghi nhận những nơi không thể xóa ngay.
10. Kiểm tra access audit, download và query history.
11. Sửa nguồn phát sinh và pipeline redaction.
12. Thêm regression test bằng synthetic secret.
13. Thông báo stakeholder/người dùng theo incident policy và nghĩa vụ áp dụng.

Không copy credential bị lộ vào ticket hoặc chat để minh họa. Chỉ chia sẻ loại credential, reference đã bảo vệ và thời gian/scope cần điều tra.

### 13.1. Revoke trước, purge sau theo rủi ro

Nếu credential còn hiệu lực và có thể bị lạm dụng, ưu tiên thu hồi/rotate nhanh. Purge log quan trọng nhưng có thể mất thời gian do backup hoặc vendor. Ghi nhận chính xác phạm vi còn tồn tại và bảo đảm credential cũ không còn giá trị.

### 13.2. Password đã lọt vào log

Nếu password plaintext xuất hiện:
- Coi password là compromised.
- Yêu cầu reset theo incident policy.
- Revoke session và refresh token có liên quan.
- Kiểm tra password reuse risk nếu có dữ liệu hợp pháp/được phép.
- Xóa hoặc quarantine các log copy.
- Không giữ password trong incident report.
- Kiểm tra log pipeline có ghi các lần reset tiếp theo hay không.

### 13.3. Token hoặc private key đã lọt vào log

Với access/refresh token, đánh giá audience, scope, expiry và revoke strategy. Với private key/HMAC secret, cần rotate key và cập nhật mọi consumer. Nếu key không thể rotate ngay, hạn chế trust, revoke certificate/grant và lên kế hoạch migration khẩn cấp.

## 14. Threat model và lỗi thường gặp

| Mối đe dọa/lỗi | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Raw request logging** | Middleware ghi toàn bộ body/header | Allowlist event và disable body dump |
| **Authorization header leak** | Proxy/app ghi bearer token | Header redaction tại mọi hop |
| **Cookie leak** | Access log ghi Cookie/Set-Cookie | Loại header và dùng session reference |
| **URL token leak** | Reset/magic token nằm trong query | Không đặt secret trong URL; redact query |
| **Exception leakage** | Exception chứa request/SQL/credential | Reason code và safe exception |
| **Trace leakage** | Auto instrumentation ghi header/query | Span attribute allowlist |
| **Metric cardinality/privacy** | Label dùng user/session/IP | Enum và aggregate |
| **Crash dump leakage** | Memory snapshot chứa token/key | Capture controls, encryption và retention |
| **Third-party SDK capture** | Session replay ghi input hoặc screenshot | Disable/mask auth screens và vendor review |
| **Queue/DLQ persistence** | Event nhạy cảm tồn tại trong queue | Source validation, queue ACL và TTL |
| **Support disclosure** | Ticket chứa OTP/reset link | Support workflow không yêu cầu secret |
| **Over-retention** | Log giữ vô thời hạn | Retention automation và deletion verification |
| **Insider misuse** | Operator export log tùy tiện | Least privilege, approval và access audit |
| **False sense from masking** | Token chỉ bị che một phần | Loại hoàn toàn bearer value |
| **Weak correlation hash** | Hash identifier/session không keyed | HMAC key riêng và versioning |
| **Incomplete incident purge** | Chỉ xóa primary log | Inventory toàn bộ replica/vendor/archive/backup |

## 15. Ví dụ: login event an toàn

Một hệ thống login cần theo dõi password login và MFA nhưng không được ghi secret.

Event an toàn có thể:

~~~json
{
  "event_type": "auth.login",
  "event_id": "evt-91f3",
  "event_time": "2026-11-22T09:00:00Z",
  "result": "challenge_required",
  "reason_code": "risk_policy_step_up",
  "auth_method": "password",
  "next_factor": "totp",
  "principal_ref": "pseud:v2:3a71...",
  "client_type": "web",
  "correlation_id": "req-8c10...",
  "region": "ap-southeast",
  "environment": "production"
}
~~~

Khi MFA hoàn tất, event khác có thể ghi factor verification success và challenge reference. Không ghi OTP, TOTP seed, QR, password hoặc raw session cookie.

Một event audit cho session revoke có thể ghi actor reference, target session reference, reason code và result. Không cần lưu session bearer value để chứng minh hành động đã xảy ra.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Auth Service
    participant L as Safe Logger
    participant S as Log Pipeline
    C->>A: Login request + credential
    A->>A: Verify credential
    A->>L: Emit allowlisted event fields
    L->>L: Schema validation and redaction
    L->>S: Safe structured event
    A-->>C: Generic response / MFA challenge
    Note over L,S: Password, OTP, cookie and token are never emitted
~~~

## 16. Kiểm thử credential leakage

Kiểm thử phải bao phủ toàn bộ telemetry pipeline, không chỉ kiểm tra logger function.

| Test case | Kết quả mong đợi |
| --- | --- |
| Password login success/failure | Password không xuất hiện ở log/trace |
| Password reset/change | Password cũ/mới và reset token không xuất hiện |
| OTP/TOTP verify | Code và seed không xuất hiện |
| MFA enrollment | QR/provisioning URI không xuất hiện |
| Recovery code use | Code không xuất hiện |
| Authorization header | Bearer token bị loại ở proxy/app/trace |
| Cookie/Set-Cookie | Session cookie không xuất hiện |
| Refresh token rotation | Raw refresh token không xuất hiện |
| API key creation | Key chỉ hiển thị theo UX an toàn, không vào log |
| Certificate/private key operation | Private key/keystore secret không xuất hiện |
| OAuth callback | Authorization code, state/verifier không vào log |
| WebAuthn assertion | Raw assertion không bị log ngoài policy |
| URL query | Reset/magic token bị loại hoặc endpoint không dùng token trong URL |
| Exception path | Exception không chứa request body/header |
| Database query logging | Bind parameter nhạy cảm không xuất hiện |
| Trace instrumentation | Header/query/body nhạy cảm bị loại |
| Metric labels | Không có email, user ID, token, session ID hoặc IP raw |
| Crash reporting | Auth screen và memory snapshot được mask/disable |
| Session replay | Password/OTP/credential field không bị capture |
| Queue/dead-letter queue | Payload không chứa secret |
| Vendor export | Chỉ nhận schema đã tối thiểu hóa |
| Support ticket | Không chứa OTP, reset link hoặc token |
| Synthetic canary | Canary secret không xuất hiện ở bất kỳ sink nào |
| Redaction regression | Field mới không được log nếu chưa allowlist |
| Incident purge | Có inventory và xác nhận xử lý mọi bản sao |

### 16.1. Synthetic secret/canary testing

Dùng chuỗi giả lập riêng cho test, ví dụ:

~~~text
TEST_PASSWORD_NEVER_LOG_7f3a
TEST_BEARER_TOKEN_NEVER_LOG_91bc
TEST_OTP_NEVER_LOG_246810
TEST_PRIVATE_KEY_NEVER_LOG_4d20
~~~

Gửi các giá trị này qua test route trong môi trường cô lập. Sau đó tìm trong:
- stdout/stderr.
- Application logs.
- Reverse proxy logs.
- Trace backend.
- Metrics exposition.
- Crash reports.
- Queue và dead-letter queue.
- Search index/SIEM.
- Analytics events.
- Test artifacts.

Bài test chỉ PASS khi không tìm thấy canary ở sink không được phép. Không dùng credential thật để thử redaction.

### 16.2. Kiểm tra schema drift

Khi thêm field vào authentication event, CI cần kiểm tra schema và allowlist. Field không biết phải bị reject hoặc bỏ qua, không tự động ghi. Review cả nested object và exception attributes.

## 17. Checklist review

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Credential inventory có đầy đủ? | Password, OTP, token, cookie, key, reset code đã được liệt kê |
| Log có allowlist? | Field mới không tự động được ghi |
| Redaction thực hiện tại nguồn? | Secret bị loại trước serialize/enqueue |
| Proxy/gateway được kiểm tra? | Authorization, Cookie và query được bảo vệ |
| Request body có bị dump? | Authentication route không ghi raw body |
| Exception có safe? | Reason code thay vì secret/request object |
| Trace có attribute allowlist? | Không ghi header/query/token nhạy cảm |
| Metric labels có bounded cardinality? | Không có user/session/email/IP raw |
| Crash/analytics/session replay được kiểm soát? | Login/MFA/recovery được mask hoặc disable |
| Correlation có an toàn? | Request ID và HMAC reference không thể replay |
| HMAC key telemetry tách biệt? | Không dùng signing key/password pepper |
| Queue/DLQ/vendor được kiểm soát? | ACL, TTL, retention và deletion rõ |
| Log access được phân quyền? | Least privilege, export approval và access audit |
| Retention có owner? | Tự động xóa và kiểm tra backup/archive |
| Audit có integrity? | Append-only hoặc tamper-evident theo risk |
| Incident response có sẵn? | Revoke/rotate, purge, notify và regression test |
| Synthetic secret tests chạy? | Canary không xuất hiện ở bất kỳ sink nào |
| Schema drift được kiểm soát? | Unknown field bị reject hoặc bỏ qua |

### Tình huống tự kiểm tra

**Tình huống 1:** Application logger đã redact password, nhưng reverse proxy vẫn ghi Authorization header. Hệ thống đã an toàn chưa?

**Trả lời:** Chưa. Credential có thể lọt ở bất kỳ hop nào. Cần cấu hình redaction tại proxy, gateway, application, collector và các sink liên quan.

**Tình huống 2:** Access token chỉ được log 8 ký tự đầu và 4 ký tự cuối. Có thể coi là an toàn không?

**Trả lời:** Không mặc định. Một phần token vẫn tạo correlation hoặc hỗ trợ dò đoán trong một số định dạng. Nếu không cần, loại hoàn toàn; nếu cần correlation, dùng keyed reference riêng.

**Tình huống 3:** Log chỉ được giữ 24 giờ. Có thể ghi OTP vì nó hết hạn sau 30 giây không?

**Trả lời:** Không. Log có thể bị đọc ngay trong cửa sổ hiệu lực và vẫn có thể chứa dữ liệu nhạy cảm. Không ghi OTP ở bất kỳ thời điểm nào.

**Tình huống 4:** Logger nhận object LoginRequest và tự serialize. Có an toàn nếu developer hiện tại biết object không có password?

**Trả lời:** Không bền vững. Schema có thể thay đổi và field nhạy cảm có thể được thêm sau này. Dùng allowlist event tường minh và schema validation.

**Tình huống 5:** Một session ID được SHA-256 rồi đưa vào log để correlation. Có phải reference an toàn không?

**Trả lời:** Không nhất thiết. Hash không keyed có thể tạo correlation ổn định và có rủi ro nếu giá trị đầu vào có thể đoán. Dùng HMAC với key telemetry riêng và không dùng reference như credential.

**Tình huống 6:** Reset token đã lọt vào SIEM nhưng đã hết hạn. Có cần incident response không?

**Trả lời:** Có. Cần xác định các bản sao, access history, thời điểm và phạm vi. Token hết hạn giảm khả năng sử dụng hiện tại nhưng log vẫn có thể tiết lộ account identifier và có thể chỉ ra lỗi pipeline làm lộ credential khác.

**Tình huống 7:** Team xóa event khỏi dashboard. Có thể kết luận credential đã được xóa không?

**Trả lời:** Không. Cần kiểm tra index, replica, queue, archive, backup, vendor và export. Việc ẩn khỏi dashboard không đồng nghĩa xóa khỏi storage.

**Tình huống 8:** Hệ thống cần đếm MFA failure theo user. Có nên tạo metric label user_id không?

**Trả lời:** Không. Dùng aggregate metric theo factor/result và truy vấn audit detail với quyền kiểm soát khi cần điều tra một principal.

## 18. Ghi nhớ

**Credential không được xuất hiện trong log, trace, metric, crash report, analytics hoặc support artifact.** Password, OTP, recovery code, session cookie, access/refresh token, API key, private key và reset link đều có thể cấp quyền trực tiếp hoặc gián tiếp. Secret ngắn hạn vẫn là secret; việc che một phần không thay thế loại bỏ hoàn toàn.

Thiết kế structured logging theo allowlist, redact tại nguồn trước khi serialize, tránh dump request/response và dùng reason code cùng correlation reference an toàn. Bảo vệ mọi hop từ proxy tới queue, SIEM, vendor, archive và backup bằng access control, retention, deletion và audit. Khi credential đã lọt vào log, đánh giá và revoke/rotate trước khi xử lý mọi bản sao; sau đó sửa nguồn phát sinh và thêm synthetic canary tests.
