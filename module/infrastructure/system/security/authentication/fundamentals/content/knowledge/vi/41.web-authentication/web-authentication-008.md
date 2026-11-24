# Web authentication test (Kiểm thử xác thực web)

> **Chương:** Authentication trong web  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Xây dựng và thực hiện chiến lược kiểm thử xác thực cho ứng dụng web; xác minh các luồng đăng nhập, MFA, passkey, liên kết IdP, session, logout và recovery; kiểm tra các ranh giới tin cậy ở browser, server và API; đánh giá khả năng chống brute force, credential stuffing, phishing, CSRF, session fixation, replay và account enumeration.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Xác định phạm vi, tài sản, trust boundary và threat model của hệ thống xác thực web.
2. Chuyển yêu cầu bảo mật thành test case có precondition, bước thực hiện, expected result và evidence.
3. Kiểm thử đăng nhập bằng password, MFA, passkey/WebAuthn và identity federation.
4. Kiểm tra session cookie, session rotation, timeout, logout và thu hồi phiên.
5. Phát hiện lỗi CSRF, redirect validation, account enumeration, brute force và recovery bypass.
6. Kiểm thử OIDC/SAML callback, state, nonce, PKCE, issuer, audience và signature validation.
7. Xây dựng test tự động cho positive, negative, boundary, concurrency và failure scenarios.
8. Đánh giá security telemetry, audit, privacy và khả năng điều tra sự cố.
9. Tổ chức kiểm thử trong môi trường được phép, dùng tài khoản và dữ liệu giả, không thu thập secret thật của người dùng.
10. Báo cáo rủi ro theo mức độ ảnh hưởng, khả năng khai thác và bằng chứng có thể tái hiện.

## 1. Web authentication test là gì?

**Web authentication test (kiểm thử xác thực web)** là hoạt động xác minh rằng ứng dụng web nhận diện đúng người dùng, chấp nhận bằng chứng hợp lệ, từ chối bằng chứng không hợp lệ và quản lý trạng thái đăng nhập an toàn trong suốt vòng đời phiên.

Kiểm thử không chỉ gửi username/password đúng hoặc sai. Một hệ thống có thể đăng nhập đúng trong trường hợp thông thường nhưng vẫn có lỗi ở các bước phụ như:

- Tạo tài khoản, kích hoạt tài khoản và xác minh email.
- Đăng nhập từ browser hoặc thiết bị mới.
- Thực hiện MFA hoặc step-up authentication.
- Đăng ký, thay thế và xóa passkey.
- Password reset và account recovery.
- SSO qua OIDC hoặc SAML.
- Session renewal, logout và revoke.
- Xử lý request đồng thời, retry và lỗi mạng.
- Thông báo đăng nhập và thay đổi authenticator.

Mục tiêu là chứng minh các quy tắc xác thực được thực thi nhất quán ở server và các thành phần liên quan. Một giao diện ẩn nút hoặc chuyển về trang login không phải bằng chứng rằng session đã bị vô hiệu hóa ở backend.

### Authentication khác authorization

- **Authentication:** xác minh danh tính hoặc principal đang truy cập.
- **Authorization:** quyết định principal được phép làm gì trên resource cụ thể.
- **Session management:** duy trì và kết thúc trạng thái đã xác thực.
- **Identity lifecycle:** quản lý credential, liên kết danh tính, recovery, suspension và deprovisioning.

Web authentication test tập trung vào xác thực và session nhưng cần kiểm tra các điểm giao với authorization, vì một login thành công không được cấp quyền vượt quá policy.

## 2. Phạm vi, tài sản và trust boundary

Trước khi kiểm thử, hãy lập bản đồ những thành phần tham gia vào authentication flow.

~~~mermaid
flowchart LR
    U["Người dùng"] --> B["Browser / thiết bị"]
    B --> W["Web application / RP"]
    W --> I["Identity Provider"]
    W --> S["Session store"]
    W --> A["Authentication service"]
    A --> C["Credential store"]
    W --> API["Backend API"]
    I --> E["Email / SMS / authenticator"]
    B -. "Cookie / token" .-> W
~~~

### Tài sản cần bảo vệ

- Password hash, passkey public key và authenticator metadata.
- MFA seed, recovery code và enrollment secret.
- Session ID, refresh token, access token và authorization code.
- OIDC state/nonce/PKCE verifier và SAML request/response.
- Email/phone recovery channel.
- Account identifier, tenant membership và authentication history.
- Signing key, TLS certificate, IdP metadata và trust configuration.
- Audit log và security event.

### Trust boundary cần kiểm tra

- Browser không được coi là nguồn sự thật cho account status hoặc role.
- Server chỉ tin session/token sau khi xác minh.
- Callback chỉ tin issuer và endpoint đã đăng ký.
- Email/SMS delivery là kênh bên ngoài; nội dung không phải bằng chứng xác thực độc lập.
- Reverse proxy/gateway chỉ được tin header identity khi cấu hình và hop được xác thực.
- Session store, key store và credential database là thành phần có quyền cao.

### Xác định scope

Ghi rõ domain, subdomain, tenant, role, authentication method, browser/device, môi trường và endpoint nằm trong phạm vi. Không kiểm thử trên production hoặc tài khoản người dùng thật nếu chưa có phê duyệt và kế hoạch an toàn.

## 3. Threat model và loại kiểm thử

Một threat model hữu ích bắt đầu từ câu hỏi attacker có thể làm gì và thành phần nào đang tin dữ liệu nào.

| Threat | Mục tiêu | Nhóm kiểm thử |
| --- | --- | --- |
| Password guessing | Đoán hoặc thử lại mật khẩu. | Rate limit, throttling, lockout và alert. |
| Credential stuffing | Dùng credential bị lộ từ nơi khác. | Risk signals, MFA/passkey và detection. |
| Phishing/AiTM | Lừa người dùng cung cấp credential hoặc phiên. | Origin binding, passkey, UX và session response. |
| Account enumeration | Dò xem tài khoản có tồn tại hay không. | Response body, status, timing và recovery endpoint. |
| Session fixation/theft | Ép hoặc chiếm session ID. | Session rotation, cookie attributes và revocation. |
| CSRF | Dùng browser của nạn nhân gửi hành động ngoài ý muốn. | CSRF token, SameSite và Origin validation. |
| OAuth/OIDC flow abuse | Giả mạo callback hoặc trộn transaction. | state, nonce, PKCE, issuer, audience và redirect URI. |
| SAML response replay | Dùng lại assertion đã được chấp nhận. | Signature, InResponseTo, conditions và replay cache. |
| Recovery abuse | Chiếm tài khoản qua reset hoặc helpdesk. | One-time token, identity proof và recovery policy. |
| MFA downgrade | Chuyển sang phương thức yếu hơn. | Factor enrollment/removal và step-up policy. |

Không phải mọi test đều cần chạy trên mọi endpoint. Ưu tiên theo tài sản, độ nhạy cảm, mức assurance và hậu quả khi bị chiếm tài khoản.

## 4. Thiết kế môi trường kiểm thử an toàn

Một môi trường tốt cho phép kiểm tra lỗi mà không ảnh hưởng người dùng thật.

### Test fixtures

Chuẩn bị các tài khoản giả đại diện cho:

- User active đã xác minh email.
- User chưa kích hoạt.
- User bị suspended hoặc disabled.
- User có password nhưng chưa đăng ký MFA.
- User có TOTP hoặc push test authenticator.
- User có passkey test.
- User có nhiều session và thiết bị.
- User thuộc tenant khác.
- Administrator với quyền giới hạn.
- Client/IdP test dành cho federation.

Dùng email domain dành cho test, số điện thoại sandbox hoặc mailbox nội bộ đã phê duyệt. Không dùng OTP/recovery code thật của người dùng.

### Dữ liệu và trạng thái

Mỗi test cần biết trạng thái ban đầu, chẳng hạn password đã đặt hay chưa, MFA có bật không, session nào đang tồn tại và tài khoản thuộc tenant nào. Sau test, phải khôi phục fixture về trạng thái dự kiến hoặc tạo dữ liệu mới có thể xóa.

### Kiểm soát môi trường

- Dùng staging/local với IdP và email/SMS sandbox.
- Bảo vệ test credentials và không đưa vào repository.
- Tắt hoặc giới hạn gửi email/SMS ra ngoài.
- Có test tenant và test signing keys riêng.
- Đồng bộ đồng hồ để kiểm tra expiry và skew.
- Giới hạn tải và concurrency theo sức chứa môi trường.
- Ghi lại build, configuration và policy version.

## 5. Ma trận kiểm thử và bằng chứng

Một test case tốt có thể được thực hiện lại và kết quả được đánh giá khách quan.

| Thành phần | Nội dung cần ghi |
| --- | --- |
| Test ID | Định danh duy nhất, ổn định. |
| Requirement | Yêu cầu hoặc policy được kiểm tra. |
| Preconditions | Account state, browser, credential và session ban đầu. |
| Steps | Request/action theo thứ tự. |
| Expected result | Trạng thái và response được mong đợi. |
| Actual result | Kết quả quan sát được. |
| Evidence | Request ID, response đã redact, screenshot hoặc audit event. |
| Severity | Tác động nếu test thất bại. |
| Cleanup | Cách thu hồi session, reset fixture và xóa dữ liệu thử. |

### Positive và negative test

- **Positive:** bằng chứng hợp lệ, flow đúng, user đủ điều kiện.
- **Negative:** credential sai, token giả, issuer sai, state thiếu hoặc account bị disabled.
- **Boundary:** token sát expiry, clock skew, giới hạn số lần thử, cookie path/domain.
- **Concurrency:** hai callback, hai reset request hoặc hai lần consume challenge cùng lúc.
- **Failure:** IdP timeout, session store unavailable, email delay hoặc browser đóng giữa flow.
- **Regression:** kiểm tra lỗi đã sửa không quay lại.

Một test chỉ kiểm tra status 200 là chưa đủ. Cần xác minh session được tạo đúng, claim/identity được gán đúng và backend từ chối request sau khi session bị revoke.

## 6. Kiểm thử đăng nhập bằng password

### Positive cases

- Username và password đúng của account active.
- Identifier theo các định dạng được hỗ trợ.
- Password có Unicode, ký tự đặc biệt và độ dài biên.
- Login sau khi account đã hoàn tất activation.
- Login theo chính sách tenant và authentication method.

### Negative cases

- Password sai.
- Username không tồn tại.
- Account chưa kích hoạt.
- Account suspended/disabled.
- Password đã bị reset hoặc credential bị revoke.
- Request thiếu field, field sai kiểu hoặc quá dài.
- Encoding/normalization không nhất quán.
- Login qua endpoint legacy không áp dụng policy mới.

### Những điều phải xác minh

- Không tạo authenticated session khi xác thực thất bại.
- Response không tiết lộ quá nhiều trạng thái account.
- Password không xuất hiện trong log, URL, analytics hoặc error report.
- Không có SQL/stack trace hoặc thông tin nội bộ trong response.
- Server áp dụng password hashing và policy đã công bố.
- Authentication thành công tạo session mới hoặc xoay session ID.
- Login không tự cấp role/tenant do client gửi lên.

Không đưa password thật vào test report hoặc screenshot. Chỉ dùng fixture secret và redact mọi request body có credential.

## 7. Kiểm thử account enumeration và response consistency

Account enumeration xảy ra khi attacker phân biệt được account tồn tại qua response, status, timing hoặc hành vi phụ.

### Các endpoint cần so sánh

- Login.
- Forgot password.
- Password reset request.
- Resend activation.
- Email/phone verification.
- MFA enrollment hoặc recovery.
- Username lookup.

### Cách kiểm tra

Dùng một account test tồn tại và một identifier không tồn tại. Gửi request cùng cấu trúc, cùng trạng thái mạng và so sánh:

- HTTP status và response schema.
- Message, error code và response length.
- Redirect behavior.
- Thời gian phản hồi qua nhiều lần đo.
- Email/SMS side effect và cách UI thông báo.
- Rate limit behavior.

Expected result là thông tin trả cho người chưa xác thực không tiết lộ rõ account có tồn tại hay không. Các luồng hỗ trợ sau khi người dùng chứng minh danh tính có thể cung cấp hướng dẫn chi tiết hơn.

Timing không nhất thiết phải bằng tuyệt đối, nhưng không nên có chênh lệch ổn định, dễ khai thác để dò tài khoản.

## 8. Kiểm thử MFA và step-up authentication

MFA test cần kiểm tra cả việc yêu cầu yếu tố thứ hai lẫn vòng đời của yếu tố đó.

### TOTP/SMS/email OTP

- OTP đúng trong time window được chấp nhận.
- OTP sai hoặc hết hạn bị từ chối.
- OTP đã dùng không được dùng lại nếu policy one-time yêu cầu.
- Số lần nhập sai bị giới hạn.
- OTP được ràng buộc với đúng account và transaction.
- Không cho OTP của user A xác thực user B.
- Gửi lại OTP không làm mã cũ còn hiệu lực ngoài policy.
- Không ghi OTP vào log hoặc analytics.

### Push approval

- Push chỉ được tạo từ login transaction hợp lệ.
- Người dùng có thể từ chối và báo cáo request không nhận biết.
- Có rate limit chống MFA fatigue.
- Number matching/context được kiểm tra nếu triển khai.
- Push cũ hoặc transaction đã hết hạn không được phê duyệt thành công.
- Không cấp session khi push bị từ chối hoặc timeout.

### Step-up

- Thao tác nhạy cảm yêu cầu xác thực mới theo policy.
- Authentication context đủ mới và đủ assurance.
- Step-up cho tenant hoặc transaction này không tự cấp quyền cho tenant/transaction khác.
- Không bỏ qua step-up qua API phụ hoặc legacy route.
- Thay đổi authenticator cần xác minh theo mức rủi ro phù hợp.

## 9. Kiểm thử passkey và WebAuthn

Passkey test phải xác minh cả registration và authentication ceremony.

### Registration

- Challenge được server tạo ngẫu nhiên và có thời hạn.
- Registration được gắn với đúng account/session đã xác minh.
- RP ID và origin đúng.
- Attestation được xử lý theo policy; không mặc định mọi attestation phải được tin như nhau.
- Credential ID/public key được lưu đúng account.
- Duplicate credential hoặc credential format sai được xử lý.
- Người chưa xác thực không thể thêm passkey cho account khác.
- Notification/audit được tạo khi authenticator mới được đăng ký.

### Authentication

- Challenge hợp lệ, mới và chưa dùng.
- Origin và RP ID hash khớp.
- Credential thuộc đúng user hoặc discoverable credential được xử lý theo policy.
- Chữ ký assertion hợp lệ.
- User presence/user verification đáp ứng yêu cầu.
- Challenge bị replay hoặc hết hạn bị từ chối.
- Credential đã revoke không thể đăng nhập.
- User handle và account mapping không bị tráo.

### Recovery

- Mất thiết bị không làm lộ secret hoặc cho phép bỏ qua mọi xác minh.
- Xóa passkey cần xác thực đủ mạnh.
- Đăng ký passkey mới có thể thu hồi session cũ theo policy.
- Không coi signature counter bằng 0 là tự động chứng minh clone; diễn giải theo authenticator/profile.

## 10. Kiểm thử session cookie và session lifecycle

Sau khi login thành công, session là credential có thể bị đánh cắp hoặc tái sử dụng. Cần kiểm tra server và browser phối hợp đúng.

### Cookie attributes

Kiểm tra cookie session có thuộc tính phù hợp:

- Secure: chỉ gửi qua HTTPS.
- HttpOnly: JavaScript không đọc được cookie qua document.cookie.
- SameSite: giảm một số request cross-site; chọn Lax/Strict/None theo flow.
- Path/Domain: scope cookie tối thiểu.
- Prefix __Host- hoặc __Secure- nếu thiết kế hỗ trợ và đáp ứng điều kiện tương ứng.

Ví dụ header minh họa:

~~~http
Set-Cookie: __Host-session=TEST_SESSION_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Giá trị cookie trong test phải là giả. Không đưa session ID thật vào tài liệu, log hoặc báo cáo.

### Session behavior

- Session ID được rotate sau login và step-up phù hợp.
- Session ID cũ không còn được chấp nhận sau rotation.
- Session có idle timeout và absolute timeout.
- Session bị revoke được từ chối ở backend.
- Logout xóa cookie và vô hiệu hóa server-side session.
- Account suspension hoặc password reset xử lý session theo policy.
- Session không bị chia sẻ nhầm giữa tenant hoặc browser profile.
- Session cookie không xuất hiện trong URL hoặc Referer.

### Session fixation test

Tạo anonymous session trước login, sau đó đăng nhập. Kiểm tra authenticated session ID khác anonymous ID và session cũ không thể dùng để truy cập chức năng đã xác thực.

## 11. Kiểm thử CSRF, Origin và CORS

CSRF lợi dụng browser tự gửi cookie/session trong request do website khác khởi tạo. CORS là cơ chế kiểm soát việc JavaScript đọc response cross-origin; CORS không tự thay thế CSRF protection.

### Kiểm thử CSRF

- Request thay đổi trạng thái dùng CSRF token hoặc cơ chế tương đương.
- Token gắn với session/form và được xác minh server-side.
- Token thiếu, sai hoặc hết hạn bị từ chối.
- GET không thực hiện hành động thay đổi trạng thái nhạy cảm.
- Origin/Referer validation được áp dụng theo policy.
- SameSite cookie được cấu hình phù hợp nhưng không coi là lớp duy nhất.
- OAuth/SAML callback tuân theo state/correlation protocol thay vì bỏ qua kiểm tra vì đó là callback.

### Kiểm thử CORS

- Allowlist origin cụ thể, không phản chiếu mọi Origin tùy ý.
- Không kết hợp wildcard origin với credentials.
- Preflight chỉ cho phép method/header cần thiết.
- Origin null hoặc origin không mong đợi được xử lý theo policy.
- Không gửi access token hoặc dữ liệu nhạy cảm tới origin không tin cậy.

Nếu browser không cho JavaScript đọc response thì request vẫn có thể được gửi. Vì vậy phải kiểm tra CSRF ở server, không chỉ nhìn lỗi CORS trên console.

## 12. Kiểm thử redirect và login flow

Redirect sai có thể làm rò authorization code/token hoặc đưa người dùng tới trang giả.

- Chỉ chấp nhận redirect URI đã đăng ký hoặc allowlist chính xác.
- Không cho phép open redirect qua tham số returnUrl/next.
- Kiểm tra URL encoding và nested redirect.
- Không đưa secret hoặc token vào query string.
- Callback chỉ nhận response đúng flow và issuer.
- Sau logout, post-logout redirect cũng phải được kiểm soát.
- Không tự động đăng nhập lại sau khi logout nếu người dùng chưa khởi tạo flow mới.
- Error page không hiển thị authorization code, state hoặc token.

Test cả redirect tương đối, tuyệt đối, protocol-relative, URL encoded và trường hợp nhiều lần decode theo behavior của framework. Mục tiêu là xác minh allowlist ở server, không tìm cách khai thác hệ thống ngoài phạm vi.

## 13. Kiểm thử OIDC/OAuth web login

OIDC web login cần kiểm tra transaction từ lúc RP khởi tạo đến callback và token validation.

### Authorization request

- state ngẫu nhiên, có entropy, gắn với browser transaction.
- nonce được dùng và lưu khi flow yêu cầu.
- PKCE dùng S256 cho public client và theo policy cho client khác.
- redirect_uri khớp đăng ký.
- client_id và issuer thuộc cấu hình tin cậy.
- response_type, response_mode và scope đúng flow.

### Callback

- state sai, thiếu hoặc đã dùng bị từ chối.
- authorization code hết hạn hoặc đã đổi không được dùng lại.
- code chỉ đổi bởi đúng client và redirect URI theo protocol.
- PKCE verifier sai bị từ chối.
- ID token kiểm tra chữ ký, issuer, audience, thời gian và nonce khi áp dụng.
- Không chấp nhận token từ issuer ngoài allowlist.
- Không dùng ID token thay access token để gọi API.
- Callback lặp hoặc response không khớp transaction bị từ chối.

### JWKS và key rotation

- Key hợp lệ mới được chấp nhận sau refresh.
- Unknown kid không gây request storm.
- Token ký bằng key không tin cậy bị từ chối.
- Không tải jku/x5u tùy ý từ token header.
- Cache key và issuer metadata có TTL và refresh policy rõ.

### PKCE không thay thế state

PKCE bảo vệ authorization code khỏi bị đổi bởi client không có verifier. State ràng buộc callback với browser transaction và giúp chống login CSRF. Hai cơ chế giải quyết các rủi ro khác nhau; không bỏ một cơ chế chỉ vì đã bật cơ chế còn lại.

## 14. Kiểm thử SAML web SSO

Với SAML, cần xác minh message và assertion theo metadata/contract của IdP và SP.

- Chữ ký response/assertion hợp lệ theo policy.
- Issuer đúng IdP được tin cậy.
- AudienceRestriction đúng SP entity ID.
- Destination/Recipient đúng endpoint.
- Conditions và NotBefore/NotOnOrAfter hợp lệ.
- InResponseTo khớp AuthnRequest đang chờ.
- Assertion ID/Response ID chưa được sử dụng.
- SubjectConfirmationData và bearer confirmation hợp lệ.
- RelayState được ràng buộc và không trở thành open redirect.
- XML parser an toàn; kiểm thử XXE và XML Signature Wrapping bằng fixture/lab.
- Response sai chữ ký, sai audience, sai issuer hoặc replay đều bị từ chối.

Không tự viết XML signature validation. Dùng thư viện SAML đã được kiểm chứng và kiểm tra cấu hình signature, canonicalization, parser hardening.

## 15. Kiểm thử password reset và account recovery

Recovery thường là đường thay thế khi người dùng không còn credential. Nếu recovery yếu hơn login, attacker có thể bỏ qua toàn bộ MFA/passkey.

### Password reset

- Reset request không tiết lộ account tồn tại.
- Token reset đủ entropy, TTL ngắn và one-time.
- Token gắn với đúng account và purpose.
- Token đã dùng, hết hạn hoặc bị revoke không được chấp nhận.
- Token không xuất hiện trong referrer/log/analytics.
- Reset không tự đăng nhập user nếu policy không cho phép.
- Password mới tuân theo policy và được hash an toàn.
- Session/refresh token cũ được xử lý theo policy.
- Thông báo gửi qua recovery channel đã đăng ký trước.

### Account recovery

- Identity proof phù hợp với mức rủi ro.
- Không cho helpdesk yêu cầu password, OTP hoặc private key.
- Recovery code one-time, có khả năng rotate/revoke.
- Thay đổi email/phone cần kiểm tra và notification.
- Recovery không tự gỡ suspension hoặc risk hold.
- Mọi recovery event có audit và correlation ID.
- Kênh recovery bị chiếm không được dùng để tự xác nhận chính nó.

## 16. Kiểm thử rate limiting và chống lạm dụng đăng nhập

Kiểm thử phải xác minh hệ thống chống automation nhưng không biến lockout thành công cụ DoS.

### Các chiều cần quan sát

- Theo account/identifier.
- Theo IP và trusted proxy-derived client address.
- Theo ASN/network reputation nếu policy sử dụng.
- Theo device/browser signal.
- Theo tenant và endpoint.
- Theo toàn hệ thống.

### Test cases

- Nhiều lần nhập sai trên một account.
- Một nguồn thử nhiều account.
- Nhiều nguồn thử một account.
- Shared NAT với nhiều user hợp lệ.
- Login success sau nhiều failure.
- OTP resend và verification attempts.
- Password reset và recovery request flood.
- Challenge timeout, retry và accessibility fallback.

Expected result cần phù hợp policy: rate limit/challenge/delay, audit và alert; không khóa dài hạn tài khoản chỉ vì một bên thứ ba gửi nhiều password sai. Không thực hiện load test trên production nếu chưa có kế hoạch và phê duyệt.

## 17. Kiểm thử logout, revoke và concurrent session

Logout phải được kiểm tra ở server-side session store và các thành phần liên kết.

- Logout local làm session hiện tại mất hiệu lực.
- Cookie cũ không dùng được sau logout.
- Logout request có CSRF protection phù hợp.
- Logout callback kiểm tra state/correlation.
- RP-initiated logout dùng endpoint và redirect URI đã đăng ký.
- Back-channel logout token được xác minh nếu có hỗ trợ.
- Session trên thiết bị khác chỉ bị revoke theo phạm vi policy.
- Refresh token bị revoke/rotate theo yêu cầu.
- JWT access token cũ có thể còn hiệu lực tới exp nếu API không có trạng thái revoke; test phải xác minh behavior thực tế.
- Logout lặp là idempotent.
- Hai request đồng thời không tạo ra trạng thái session bất nhất.
- Account suspension hoặc credential compromise kích hoạt session response phù hợp.

Không báo “đăng xuất mọi nơi thành công” nếu hệ thống chỉ xóa cookie ở browser hiện tại.

## 18. Kiểm thử browser security và transport

Authentication phụ thuộc browser, TLS và cách ứng dụng xử lý origin.

### TLS và domain

- HTTPS được bắt buộc trên login, callback và authenticated pages.
- HSTS được cấu hình phù hợp với domain/subdomain policy.
- Certificate hợp lệ và hostname khớp.
- Không có mixed content làm lộ dữ liệu xác thực.
- Không chuyển credential qua HTTP.
- Redirect từ HTTP sang HTTPS không làm lộ query chứa secret.

### Browser storage

- Không lưu session bearer token dài hạn trong localStorage nếu kiến trúc có lựa chọn an toàn hơn.
- Không để secret trong URL, DOM attribute hoặc analytics event.
- Cookie HttpOnly được dùng cho session cookie phù hợp.
- JavaScript không thể đọc HttpOnly cookie.
- CSP và output encoding giảm nguy cơ XSS; XSS vẫn có thể thực hiện hành động trong origin dù không đọc được cookie.
- Không lưu password/OTP/recovery code trong browser storage.

### Tab, navigation và browser state

- Back button không làm trang authenticated cũ tiếp tục hoạt động nếu session đã revoke.
- Browser đóng/mở lại tuân theo remember-me policy.
- Tab cũ không giữ quyền sau logout hoặc suspension.
- Nhiều tab không gây race khi refresh/rotate token.
- Browser privacy settings không làm hệ thống bỏ qua state hoặc cookie security.

## 19. Kiểm thử audit, logging và privacy

Một authentication system cần đủ dữ liệu điều tra nhưng không ghi lại credential.

### Event nên có

- Login success/failure và phương thức xác thực.
- MFA challenge/approval/denial.
- Passkey registration/removal.
- Password reset và recovery.
- Session create/rotate/revoke/expire.
- SSO callback success/failure.
- Account lock/suspension và reinstatement.
- Risk decision và step-up outcome.
- Client/device context theo privacy policy.

### Không ghi

- Password hoặc password reset secret.
- OTP, TOTP seed, recovery code.
- Session cookie, bearer token hoặc refresh token nguyên vẹn.
- Private key, client secret và authorization code.
- Raw assertion nếu chứa dữ liệu cá nhân không cần thiết.

Dùng correlation ID, request ID, token identifier đã pseudonymize hoặc session reference đã bảo vệ. Hạn chế quyền truy cập log và đặt retention theo mục đích.

### Kiểm tra tính nhất quán

Một login thất bại không được ghi thành success. Session revoke phải có event tương ứng. Timestamp phải có timezone/định dạng thống nhất. Log từ gateway, IdP và ứng dụng cần có correlation để điều tra nhưng không chia sẻ raw secrets.

## 20. Tự động hóa kiểm thử

Nên kết hợp unit, integration, browser end-to-end và security regression test.

| Cấp độ | Phạm vi | Ví dụ |
| --- | --- | --- |
| Unit | Validator và policy logic. | Token expiry, issuer, audience, password rule. |
| Integration | App với database, session store và IdP test. | Login, reset, token rotation, logout. |
| Browser E2E | Hành vi thật của browser. | Cookie, redirect, MFA UI, passkey test fixture. |
| Protocol conformance | OIDC/SAML/WebAuthn contract. | state, nonce, signature, RP ID và assertion validation. |
| Abuse/security regression | Attack paths đã biết. | CSRF, replay, enumeration, session fixation. |
| Resilience | Dependency failure và concurrency. | IdP timeout, cache outage, duplicate callback. |

### Ví dụ Playwright với fixture test

~~~typescript
import { test, expect } from "@playwright/test";

test("login success rotates the session", async ({ page, context }) => {
  await page.goto("/login");

  const before = await context.cookies();
  const oldSession = before.find(cookie => cookie.name === "__Host-session");

  await page.getByLabel("Email").fill("learner-test@example.test");
  await page.getByLabel("Password").fill("TEST_ONLY_PASSWORD");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/dashboard/);

  const after = await context.cookies();
  const newSession = after.find(cookie => cookie.name === "__Host-session");

  expect(newSession).toBeTruthy();
  expect(newSession?.httpOnly).toBe(true);
  expect(newSession?.secure).toBe(true);
  expect(newSession?.sameSite).toBe("Lax");
  expect(newSession?.value).not.toBe(oldSession?.value);
});
~~~

Ví dụ minh họa cần điều chỉnh selector, route và cookie policy theo ứng dụng. Fixture credential chỉ dành cho môi trường test. Không in cookie value ra test report; chỉ so sánh trong bộ nhớ rồi loại bỏ context sau test.

### Ví dụ kiểm thử logout

~~~typescript
test("revoked session cannot access a protected page", async ({ page }) => {
  await signInWithTestAccount(page);
  await page.goto("/account");
  await expect(page.getByRole("heading", { name: "Account" })).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/login/);

  await page.goto("/account");
  await expect(page).toHaveURL(/login/);
});
~~~

Kiểm tra redirect ở browser chưa đủ. Integration test cần gọi protected endpoint bằng session cũ và xác nhận server trả unauthenticated/denied sau khi revoke.

## 21. Test matrix tổng hợp

| Nhóm | Kịch bản đại diện | Expected result |
| --- | --- | --- |
| Password | Sai password hoặc account disabled. | Không tạo authenticated session. |
| Enumeration | Account tồn tại và không tồn tại. | Response không tiết lộ trạng thái nhạy cảm. |
| MFA | OTP sai, hết hạn hoặc đã dùng. | Từ chối và áp giới hạn thử. |
| Passkey | Origin/RP ID/challenge sai. | Assertion bị từ chối. |
| Session | Session fixation hoặc cookie cũ sau logout. | Session cũ không còn quyền. |
| CSRF | Request thay đổi trạng thái thiếu token. | Server từ chối. |
| CORS | Origin ngoài allowlist. | Không được cấp quyền đọc response có credentials. |
| Redirect | returnUrl trỏ tới domain ngoài allowlist. | Không redirect tới đích không tin cậy. |
| OIDC | state/nonce/PKCE/audience sai. | Callback/token bị từ chối. |
| SAML | Signature, issuer, audience hoặc InResponseTo sai. | Assertion bị từ chối. |
| Recovery | Reset token replay hoặc hết hạn. | Token không thể dùng lại. |
| Rate limit | Login/recovery flood trong lab. | Throttle/challenge/alert theo policy. |
| Logout | Session revoke và callback lặp. | Idempotent, không tạo session mới. |
| Privacy | Scan log sau test. | Không có credential hoặc token nguyên vẹn. |
| Resilience | IdP/session store timeout. | Fail policy rõ; không bypass xác thực. |
| Concurrency | Hai callback hoặc hai lần consume challenge. | Chỉ một transaction hợp lệ được chấp nhận. |

## 22. Ví dụ thực tế: Learning Platform

Learning Platform có Learning Portal, Staff Console và IdP của trường. Người học đăng nhập bằng password kết hợp passkey hoặc MFA; nhân viên dùng SSO.

### Kế hoạch kiểm thử

1. Tạo fixture learner active, learner suspended, staff và admin test.
2. Xác minh login password đúng/sai và response consistency.
3. Kiểm tra MFA challenge, passkey registration và authentication.
4. Kiểm tra OIDC state, nonce, PKCE, issuer và audience.
5. Xác minh session ID rotate sau login và bị revoke sau logout.
6. Thử CSRF trên thay đổi email, thêm authenticator và cập nhật recovery.
7. Kiểm tra tenant isolation sau login.
8. Kiểm tra reset token one-time và recovery không vượt qua suspension.
9. Gửi callback/OTP test đã dùng lần thứ hai để kiểm tra replay.
10. Đối chiếu audit giữa IdP, Portal và session service.

### Ví dụ phát hiện lỗi

Test thấy người dùng logout ở Portal nhưng session cũ vẫn gọi được API profile. Đây là lỗi session revocation dù browser đã chuyển về trang login. Bằng chứng cần có request ID, trạng thái session trước/sau và response API khi dùng cookie test cũ.

Sau khi sửa, regression test phải xác minh session store đánh dấu revoked, mọi API node từ chối cookie cũ và logout lặp không tạo side effect sai.

## 23. Đánh giá kết quả và severity

Một finding nên mô tả điều kiện, tác động và phạm vi khai thác.

| Mức | Ví dụ tác động |
| --- | --- |
| Critical | Bypass xác thực rộng, chiếm nhiều tài khoản đặc quyền hoặc lộ signing key/session store. |
| High | Bypass MFA/recovery, takeover tài khoản quan trọng, token được chấp nhận sai audience trên API nhạy cảm. |
| Medium | Session timeout/revoke không nhất quán, account enumeration có giá trị, CSRF trên thao tác có tác động đáng kể. |
| Low | Thiếu audit field, thông báo lỗi chưa rõ hoặc cấu hình cookie chưa tối ưu nhưng có lớp bù. |
| Informational | Cải thiện UX, test coverage hoặc telemetry chưa tạo lỗ hổng trực tiếp. |

Severity cần dựa trên exploitability, quyền cần có, dữ liệu/tài sản bị ảnh hưởng, số lượng account và biện pháp bù. Không nâng mức chỉ vì tên kỹ thuật nghe nghiêm trọng; cũng không hạ mức nếu lỗi làm mất ranh giới xác thực.

### Cấu trúc báo cáo

- Title và test ID.
- Affected endpoint/component.
- Preconditions và account role.
- Steps to reproduce trong môi trường được phép.
- Expected vs actual behavior.
- Evidence đã redact.
- Impact và scope.
- Severity/rationale.
- Recommendation.
- Retest result và regression coverage.

## 24. Checklist kiểm thử web authentication

- [ ] Scope, domain, tenant, role và test accounts đã được xác định.
- [ ] Có threat model và trust-boundary diagram.
- [ ] Có test positive, negative, boundary, concurrency và failure.
- [ ] Password login không tạo session khi credential sai.
- [ ] Account enumeration được kiểm tra ở login, reset và activation.
- [ ] MFA OTP/push có expiry, rate limit và replay behavior đúng.
- [ ] Passkey/WebAuthn kiểm tra challenge, origin, RP ID và signature.
- [ ] Session ID được rotate; cookie có Secure, HttpOnly, SameSite phù hợp.
- [ ] Idle timeout, absolute timeout, logout và server-side revoke được kiểm tra.
- [ ] CSRF được kiểm tra độc lập với CORS.
- [ ] Redirect URI và return URL có allowlist.
- [ ] OIDC state, nonce, PKCE, issuer, audience và JWKS được kiểm tra.
- [ ] SAML signature, issuer, audience, destination, InResponseTo và replay được kiểm tra.
- [ ] Password reset/recovery token one-time, đúng purpose và không bypass suspension.
- [ ] Rate limit không tạo lockout DoS dễ khai thác.
- [ ] Logout và callback lặp được xử lý idempotent.
- [ ] Tenant isolation và role boundary được kiểm tra sau authentication.
- [ ] Audit đủ dùng nhưng không lưu password, OTP, cookie hoặc token.
- [ ] Có test IdP outage, session-store outage, clock skew và concurrent request.
- [ ] Test report có evidence đã redact, severity, cleanup và retest.

## 25. Tự kiểm tra

**Câu 1.** Web authentication test cần kiểm tra những gì ngoài password đúng/sai?

**Đáp án:** MFA, passkey, SSO, session lifecycle, logout, recovery, CSRF, redirect, rate limit, audit, privacy và hành vi khi dependency lỗi.

**Câu 2.** Vì sao phải kiểm tra session ở server sau logout?

**Đáp án:** Browser có thể xóa cookie hoặc chuyển trang nhưng session ID cũ có thể vẫn được backend chấp nhận. Cần xác minh server-side revocation.

**Câu 3.** CORS có thay thế CSRF protection không?

**Đáp án:** Không. CORS chủ yếu kiểm soát JavaScript đọc response cross-origin; request vẫn có thể được gửi. Server cần CSRF token/origin controls phù hợp.

**Câu 4.** OIDC state và PKCE có giống nhau không?

**Đáp án:** Không. State ràng buộc callback với browser transaction và chống login CSRF; PKCE ràng buộc authorization code với client giữ verifier.

**Câu 5.** Một WebAuthn assertion cần kiểm tra những thuộc tính nào?

**Đáp án:** Challenge, origin, RP ID hash, credential, chữ ký và user presence/user verification theo policy; challenge phải chưa dùng và còn hiệu lực.

**Câu 6.** Vì sao account enumeration cần test cả timing?

**Đáp án:** Response body có thể giống nhau nhưng thời gian xử lý ổn định khác biệt vẫn tiết lộ account tồn tại hoặc trạng thái account.

**Câu 7.** Password reset token cần đặc tính nào?

**Đáp án:** Đủ entropy, thời hạn ngắn, one-time, gắn đúng account/purpose và không xuất hiện trong log/referrer; sau reset cần xử lý session theo policy.

**Câu 8.** Vì sao test MFA phải bao gồm recovery?

**Đáp án:** Recovery là đường thay thế khi mất authenticator. Nếu recovery yếu hơn login, attacker có thể bypass MFA dù luồng MFA chính an toàn.

**Câu 9.** Nếu IdP timeout, ứng dụng có nên tự bỏ qua xác thực để giữ availability không?

**Đáp án:** Không. Cần fail policy rõ theo mức rủi ro, có thể dùng session đã xác minh còn hiệu lực theo policy, nhưng không tự tạo authenticated session khi chưa có bằng chứng hợp lệ.

**Câu 10.** Một test case tốt cần lưu những thông tin nào?

**Đáp án:** Test ID, requirement, preconditions, steps, expected/actual result, evidence đã redact, severity và cleanup/retest.

## Ghi nhớ

**Web authentication test** xác minh toàn bộ vòng đời xác thực trong browser và server: password, MFA, passkey, SSO, session, logout và recovery. Kiểm thử cần bao phủ trust boundary, CSRF, redirect, account enumeration, rate limit, token validation, replay, tenant isolation và xử lý khi IdP hoặc session store lỗi.

Hãy dùng fixture account và môi trường được phép; kết hợp unit, integration, protocol và browser end-to-end test; lưu evidence đã redact và xác minh trạng thái ở backend. Đặc biệt, không coi giao diện chuyển về login là bằng chứng session đã bị revoke, không coi CORS thay thế CSRF và không để recovery trở thành đường bypass MFA. **Một luồng xác thực chỉ đáng tin khi cả bằng chứng, transaction, session và quy trình khôi phục đều được kiểm tra ở đúng ranh giới tin cậy.**
