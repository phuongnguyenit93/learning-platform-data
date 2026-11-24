# Case study: Đăng nhập bằng password

## 1. Bối cảnh

Công ty giả định An Phú có một cổng nhân viên dùng trên trình duyệt để xem thông tin cá nhân, tra cứu tài liệu nội bộ và gửi yêu cầu nghiệp vụ. Nhân viên đăng nhập bằng email công ty và password. Một số nhóm, chẳng hạn quản trị viên hoặc nhân viên truy cập dữ liệu nhạy cảm, phải hoàn tất MFA theo policy sau khi password được xác minh.

Hệ thống hiện tại có ba vấn đề:

- Login endpoint trả lỗi khác nhau cho email không tồn tại và password sai, khiến người ngoài có thể dò tài khoản.
- Password được lưu bằng hash cũ với cost thấp; các request sai liên tục làm CPU tăng cao.
- Sau đăng nhập, session ID không được xoay và cookie chưa có đầy đủ thuộc tính bảo vệ.

Nhóm kỹ thuật cần thiết kế lại luồng đăng nhập password, giữ trải nghiệm quen thuộc cho nhân viên và giảm nguy cơ account takeover, enumeration, brute force, credential stuffing và session hijacking.

Case study này tập trung vào một ứng dụng web dùng password. Nó cũng chỉ ra vị trí cần nối với MFA, account recovery và session lifecycle trong module SECURITY_AUTHENTICATION_FUNDAMENTALS.

## 2. Mục tiêu và phạm vi

### Mục tiêu

1. Chỉ cấp session sau khi password được xác minh và mọi factor bắt buộc đã hoàn tất.
2. Không để response công khai tiết lộ email có tồn tại hay không.
3. Bảo vệ password verifier trước database disclosure.
4. Giới hạn tốc độ và concurrency trước các bước tốn tài nguyên.
5. Chống replay, session fixation và CSRF trong luồng browser.
6. Ghi đủ sự kiện bảo mật để phát hiện abuse nhưng không log bí mật.
7. Có quy trình password reset và thu hồi session an toàn.

### Phạm vi

- Browser-based employee portal.
- Email công ty làm account identifier.
- Password verification phía server.
- MFA step-up theo nhóm người dùng hoặc risk policy.
- Server-side session với cookie.
- Password reset qua kênh liên hệ đã xác minh.
- Audit, monitoring và rate limiting.

### Ngoài phạm vi

- Đăng nhập không mật khẩu bằng passkey.
- Federation SAML/OIDC với IdP bên ngoài.
- Workload identity và API key.
- Thiết kế chi tiết hệ thống HR hoặc provisioning tài khoản.

Các phần ngoài phạm vi có thể được tích hợp sau, nhưng phải giữ nguyên các ranh giới tin cậy và nguyên tắc bảo vệ session/credential được nêu trong case study.

## 3. Yêu cầu bảo mật và giả định

| Yêu cầu | Thiết kế được chọn | Lý do |
| --- | --- | --- |
| Confidentiality | TLS cho mọi request login/reset; không ghi password vào log. | Bảo vệ credential trên đường truyền và trong vận hành. |
| Password storage | Password hashing chuyên dụng, salt ngẫu nhiên riêng cho từng account. | Làm chậm offline guessing khi verifier bị lộ. |
| Authentication response | Generic error cho các trường hợp không xác thực được. | Giảm account enumeration. |
| Online abuse | Rate limit theo source, account hint, tenant và global capacity. | Giảm brute force, spraying và overload. |
| MFA | Bắt buộc theo policy; không tự downgrade khi provider lỗi. | Giữ assurance cho nhóm và thao tác rủi ro cao. |
| Session | Xoay session ID sau authentication, cookie bảo vệ và timeout. | Giảm session fixation và chiếm session kéo dài. |
| Recovery | Token ngẫu nhiên, ngắn hạn, dùng một lần và gửi qua kênh đã xác minh. | Tránh biến reset thành đường bypass login. |
| Audit | Ghi event và kết quả, không ghi secret. | Hỗ trợ phát hiện và điều tra. |

Giả định:

- Mỗi nhân viên có một account nội bộ với email đã được xác minh qua quy trình onboarding.
- Email là identifier để tìm account, không phải secret.
- Ứng dụng có HTTPS và domain chính thức được kiểm soát.
- Password verifier được truy cập qua authentication service; client không truy cập database.
- Policy engine hoặc cấu hình nội bộ xác định nhóm nào cần MFA.
- Đội vận hành có thể thu hồi session và vô hiệu hóa account khi phát hiện compromise.

## 4. Actor, asset và trust boundary

### Actor

| Actor | Trách nhiệm |
| --- | --- |
| Nhân viên | Nhập email và password; hoàn tất MFA nếu được yêu cầu. |
| Browser | Gửi login request và giữ session cookie. |
| Web application | Điều phối login, tạo session và phục vụ portal. |
| Authentication service | Tìm account, xác minh password và áp dụng login policy. |
| Credential database | Lưu account reference, password verifier và trạng thái account. |
| MFA service | Tạo và xác minh challenge/factor khi policy yêu cầu. |
| Session store | Lưu trạng thái session và hỗ trợ thu hồi. |
| Email provider | Gửi thông báo hoặc password reset link tới địa chỉ đã xác minh. |
| Security monitoring | Nhận event đã loại secret để phát hiện abuse. |

### Asset

- Email/account identifier và internal subject ID.
- Password do người dùng gửi trong request.
- Password verifier, salt và pepper reference nếu có.
- MFA seed hoặc factor reference, challenge và recovery metadata.
- Pre-authentication transaction và session ID.
- Session cookie, CSRF token và reset token.
- Audit event, login history và risk signal.

### Trust boundary

1. Browser và public network sang web application.
2. Web application sang authentication service.
3. Authentication service sang credential database.
4. Authentication service sang MFA provider.
5. Web application sang session store.
6. Recovery service sang email provider.
7. Các service nội bộ sang log/monitoring pipeline.

TLS bảo vệ kênh truyền nhưng không thay thế xác minh principal hoặc authorization. Request từ browser luôn là dữ liệu không đáng tin cho tới khi server xác minh.

## 5. Kiến trúc luồng đăng nhập

Thiết kế dùng password verification ở server. Browser không tự xác minh password và không nhận password verifier.

~~~mermaid
sequenceDiagram
    participant U as Nhân viên
    participant B as Browser
    participant W as Web App
    participant A as Auth Service
    participant DB as Credential DB
    participant M as MFA Service
    participant S as Session Store
    U->>B: Nhập email và password
    B->>W: POST /login qua TLS
    W->>A: Yêu cầu xác thực
    A->>A: Kiểm tra kích thước, định dạng và quota
    A->>DB: Tìm account theo identifier đã chuẩn hóa
    DB-->>A: Account + verifier hoặc không tìm thấy
    A->>A: Verify password thật hoặc dummy verifier
    A->>A: Kiểm tra account state và policy
    alt MFA bắt buộc
        A->>M: Tạo/kiểm tra MFA challenge
        M-->>A: Factor đã xác minh
    end
    A-->>W: Authentication result
    W->>S: Tạo session ID mới
    S-->>W: Session đã lưu
    W-->>B: Set-Cookie session
    B-->>U: Hiển thị portal
~~~

Sơ đồ mô tả luồng khái niệm. Trong triển khai, có thể tách bước MFA thành nhiều request và dùng pre-authentication transaction riêng. Session đầy đủ chỉ được tạo sau khi tất cả factor bắt buộc hoàn tất.

## 6. Account identifier và chuẩn hóa input

Email công ty được dùng làm account identifier. Hệ thống cần thống nhất quy tắc chuẩn hóa để cùng một địa chỉ không tạo ra nhiều account hoặc nhiều rate-limit key.

Các bước:

1. Kiểm tra content type và giới hạn kích thước request body.
2. Từ chối identifier rỗng, quá dài hoặc sai định dạng cơ bản.
3. Áp dụng quy tắc canonicalization thống nhất với quy trình provisioning.
4. Không tự ý thay đổi phần local-part theo quy tắc riêng của nhà cung cấp email nếu hệ thống chưa quy định.
5. Dùng internal subject ID làm khóa principal ổn định sau khi tìm thấy account.

Không dùng email làm secret hoặc bằng chứng danh tính. Việc biết email không đủ để reset password hay thay đổi MFA.

## 7. Lưu password an toàn

### 7.1. Password verifier

Khi nhân viên tạo hoặc đổi password, server tạo verifier bằng password hashing algorithm chuyên dụng, chẳng hạn Argon2id hoặc một lựa chọn phù hợp với nền tảng và policy hiện hành. Mỗi account có salt ngẫu nhiên riêng. Hệ thống lưu verifier cùng thuật toán và tham số để có thể xác minh và nâng cấp sau này.

Không lưu password plaintext, không mã hóa password bằng khóa có thể giải mã lại và không dùng hash nhanh tổng quát như SHA-256 đơn lẻ để lưu password.

### 7.2. Cost parameters

Cost cần được benchmark trên phần cứng production để chống offline guessing nhưng không làm login hợp lệ quá chậm. Tham số nên được cấu hình và version hóa. Khi đăng nhập thành công với verifier cũ, hệ thống có thể rehash bằng tham số mới rồi cập nhật có kiểm soát.

Không giảm cost tự động trong lúc overload. Điều đó giải quyết áp lực CPU bằng cách làm yếu password storage. Hãy dùng admission control và giới hạn concurrency.

### 7.3. Pepper và secret management

Một số kiến trúc có thể dùng pepper bổ sung được quản lý ngoài database, chẳng hạn trong KMS/HSM. Nếu áp dụng:

- Không lưu pepper cùng database verifier.
- Chỉ authentication service được quyền dùng key theo policy.
- Có kế hoạch rotation và xử lý verifier trong giai đoạn chuyển đổi.
- Không để pepper xuất hiện trong log, environment dump hoặc source control.

Pepper là lớp phòng thủ bổ sung, không thay salt riêng và password hashing chuyên dụng.

### 7.4. Password policy

- Cho phép passphrase dài và password manager.
- Cho phép paste/autofill để khuyến khích mật khẩu mạnh.
- Không cắt cụt password âm thầm.
- Chặn password phổ biến hoặc đã biết bị lộ theo nguồn dữ liệu được phê duyệt.
- Không áp dụng quy tắc thành phần ký tự phức tạp mà không có đánh giá usability/security.
- Không bắt buộc đổi password định kỳ nếu không có dấu hiệu compromise hoặc yêu cầu cụ thể.
- Hỗ trợ đổi password và thu hồi session khi người dùng nghi ngờ bị lộ.

## 8. Login request và phản hồi

Ví dụ request:

~~~http
POST /login
Content-Type: application/json

{
  "email": "employee@example.test",
  "password": "<password entered by the user>"
}
~~~

Ví dụ phản hồi khi không xác thực được:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "error": "authentication_failed",
  "message": "Thông tin đăng nhập không hợp lệ."
}
~~~

Không trả riêng các thông báo như “email không tồn tại”, “password sai”, “account bị khóa” hoặc “chưa đăng ký MFA” cho caller chưa xác thực. Các lý do chi tiết có thể được ghi vào audit nội bộ với quyền truy cập hạn chế.

Khi vượt quota, có thể trả 429 Too Many Requests hoặc phản hồi tạm thời phù hợp theo policy. Cần tránh để khác biệt này tiết lộ account tồn tại; quota nên áp dụng cả với account hint không tồn tại.

## 9. Password verification và timing protection

Nếu account không tồn tại, trả lỗi ngay sẽ nhanh hơn nhánh account tồn tại cần chạy password hash. Attacker có thể đo timing để dò email hợp lệ.

Thiết kế dùng dummy verifier:

1. Tìm account theo identifier đã chuẩn hóa.
2. Nếu tìm thấy, lấy verifier thật.
3. Nếu không tìm thấy, dùng dummy verifier đã tạo sẵn với cùng scheme và cost.
4. Chạy password verification trong cả hai trường hợp.
5. Chỉ chấp nhận nếu account tồn tại, password đúng và account state cho phép.
6. Trả cùng response cho các trường hợp không xác thực được.

~~~ts
async function verifyLogin(email: string, password: string) {
  const normalized = normalizeEmail(email);
  const account = await accountStore.findByEmail(normalized);
  const verifier = account?.passwordVerifier ?? DUMMY_PASSWORD_VERIFIER;

  const passwordMatches = await passwordHasher.verify(verifier, password);
  const accountAllowed = account?.status === "active";

  if (!account || !passwordMatches || !accountAllowed) {
    return { ok: false, reason: "generic_failure" };
  }

  return { ok: true, subjectId: account.subjectId };
}
~~~

Đây là pseudocode, không phải mã production. Dummy verifier phải được tạo sẵn với cùng thuật toán và cost tương đương verifier thật. Không ghi password, verifier hoặc giá trị secret vào log. Việc cân bằng password verification không làm mọi request có thời gian giống hệt nhau; cần kết hợp rate limit và kiểm thử phân phối latency.

## 10. Rate limiting và chống online guessing

Hệ thống phối hợp nhiều lớp quota:

| Chiều giới hạn | Mục đích |
| --- | --- |
| Source/network | Giảm burst từ một nguồn; lưu ý NAT/VPN có thể dùng chung. |
| Account hint | Giảm brute force vào một identifier; áp dụng cả account không tồn tại. |
| Tenant/client | Tránh một tổ chức hoặc ứng dụng chiếm hết capacity. |
| Device/pre-auth session | Bổ sung tín hiệu lạm dụng nhưng không coi fingerprint là định danh chắc chắn. |
| Global KDF concurrency | Giữ CPU/memory trong giới hạn đã benchmark. |
| MFA/recovery endpoint | Chống OTP guessing, push fatigue, SMS pumping và email bombing. |

Ưu tiên progressive throttling/cooldown thay vì khóa cứng account sau vài lần sai. Account lockout cứng có thể bị attacker lợi dụng để gây denial of service cho nạn nhân.

Quota phải được kiểm tra trước bước KDF tốn tài nguyên. KDF worker pool và queue cần giới hạn; không xếp request vô hạn để chờ password hashing.

## 11. Xử lý account state và MFA policy

Sau khi password đúng, hệ thống kiểm tra:

- Account active hay disabled.
- Có yêu cầu đổi password hoặc xử lý credential compromise không.
- Principal thuộc nhóm cần MFA bắt buộc không.
- Risk policy có yêu cầu step-up do thiết bị mới, vị trí bất thường hoặc thao tác nhạy cảm không.
- Pre-auth transaction còn hiệu lực và chưa được dùng không.

Nếu MFA bắt buộc, server tạo challenge gắn với principal, login transaction, purpose và thời hạn. Session đầy đủ chưa được cấp cho tới khi factor hợp lệ được xác minh.

Không tự động bỏ MFA nếu provider không khả dụng. Có thể dùng factor dự phòng đã đăng ký và được policy cho phép; nếu không có phương án phù hợp, từ chối tạm thời.

## 12. Pre-authentication transaction

Khi password đúng nhưng MFA còn chờ, hệ thống cần một trạng thái tạm thời:

- Transaction ID ngẫu nhiên, khó đoán.
- Gắn với browser/session khởi tạo login.
- Gắn với subject và mục đích đăng nhập.
- Có expiry ngắn.
- Có giới hạn số lần thử và số challenge.
- Không có quyền truy cập tài nguyên nghiệp vụ.
- Chỉ có thể chuyển sang authenticated state sau khi factor bắt buộc hoàn tất.

Không dùng session đầy đủ rồi chỉ đánh dấu MFA pending ở client. Server phải kiểm tra trạng thái transaction ở mọi endpoint được bảo vệ.

## 13. Tạo và bảo vệ session

Sau khi password và MFA policy hoàn tất:

1. Tạo session ID mới bằng CSPRNG.
2. Lưu session phía server trước khi gửi cookie.
3. Xoay hoặc vô hiệu hóa pre-authentication session ID.
4. Gắn session với subject, assurance level, thời điểm xác thực và expiry.
5. Gửi cookie với thuộc tính phù hợp.

Cookie minh họa:

~~~http
Set-Cookie: __Host-employee_session=<opaque-random-value>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Giải thích:

- Secure: chỉ gửi qua HTTPS.
- HttpOnly: JavaScript không đọc trực tiếp cookie.
- SameSite: giảm một số rủi ro CSRF; giá trị cần phù hợp luồng ứng dụng.
- Prefix __Host-: hỗ trợ ràng buộc cookie với host, yêu cầu Secure, Path=/ và không có Domain attribute trong trình duyệt hỗ trợ.

Cookie không thay thế CSRF protection cho mọi thiết kế. Với state-changing request, ứng dụng cần CSRF token hoặc cơ chế tương đương và kiểm tra Origin/Fetch Metadata theo kiến trúc.

## 14. Session lifecycle

Session cần có:

- Idle timeout và absolute lifetime.
- Session rotation sau login, MFA step-up và thay đổi quyền.
- Thu hồi khi logout, password reset, account disable hoặc phát hiện compromise.
- Giới hạn số session đồng thời theo policy.
- Cơ chế kiểm tra session version/revocation state nếu cần thu hồi diện rộng.
- Không ghi session ID/cookie vào log.

Logout phải xóa cookie phía browser và thu hồi record server-side. Chỉ xóa cookie không đảm bảo session đã bị vô hiệu hóa.

Khi password được đổi hoặc reset, policy có thể thu hồi toàn bộ session và refresh token hiện có, hoặc yêu cầu re-authentication. Quyết định phải nhất quán và được audit.

## 15. Password reset và recovery

Password reset là một phần của authentication protocol, không phải chức năng phụ. Nếu reset yếu hơn login, attacker sẽ đi qua recovery để chiếm account.

Luồng đề xuất:

1. Người dùng gửi email account identifier.
2. Server trả thông báo chung, không tiết lộ account có tồn tại.
3. Nếu account hợp lệ, tạo reset token ngẫu nhiên, purpose-bound và thời hạn ngắn.
4. Lưu verifier/hash của reset token, không lưu token plaintext nếu kiến trúc cho phép.
5. Gửi link qua email đã xác minh bằng queue/outbox.
6. Khi người dùng mở link, kiểm tra token, expiry, purpose và trạng thái chưa dùng.
7. Yêu cầu password mới theo policy và cập nhật verifier.
8. Tiêu thụ reset token nguyên tử.
9. Thu hồi session/token theo policy và gửi thông báo bảo mật.
10. Ghi audit event nhưng không ghi reset token hoặc password.

Không cho phép support agent hỏi password hoặc OTP. Thay đổi email recovery hoặc MFA factor phải có xác minh mạnh và audit riêng.

## 16. Threat analysis

| Threat | Cách khai thác | Kiểm soát |
| --- | --- | --- |
| Brute force | Thử nhiều password cho một account. | Per-account/source quota, progressive throttling, MFA và monitoring. |
| Credential stuffing | Dùng password/email từ breach khác. | Chặn password đã lộ theo policy, rate limit, risk signal và MFA. |
| Password spraying | Thử một số password phổ biến trên nhiều account. | Source/global detection, breached-password controls và anomaly monitoring. |
| Account enumeration | Phân biệt account tồn tại qua message/status/timing. | Generic response, dummy verifier, quota cho mọi account hint và timing tests. |
| Password database disclosure | Lấy verifier để crack offline. | Argon2id/scheme phù hợp, salt riêng, cost benchmark, least privilege và backup protection. |
| Phishing | Dụ người dùng nhập password vào site giả. | Domain education, password manager, MFA chống phishing/passkey theo roadmap. |
| Session fixation | Ép nạn nhân dùng session ID do attacker biết. | Xoay session ID sau login và step-up. |
| Session hijacking | Đánh cắp cookie/token. | TLS, Secure/HttpOnly, XSS prevention, short lifetime, revoke và endpoint protection. |
| CSRF | Dùng browser nạn nhân gửi request có cookie. | SameSite, CSRF token, Origin/Fetch Metadata và method policy. |
| Reset abuse | Dùng recovery để chiếm account hoặc spam email. | One-time token, verified channel, generic response, quota và audit. |
| KDF exhaustion | Gửi nhiều password sai để làm cạn CPU/memory. | Admission control trước KDF, bounded worker pool và load shedding. |
| MFA downgrade | Bỏ factor khi provider lỗi. | Không fail open; fallback chỉ theo policy và audit. |

Không một biện pháp đơn lẻ xử lý tất cả threat. Password hashing bảo vệ dữ liệu lưu trữ nhưng không ngăn phishing; MFA giảm tác động của password bị lộ nhưng session vẫn có thể bị chiếm; rate limit giảm guessing nhưng không thay authorization.

## 17. Monitoring và audit events

Các event cần ghi:

| Event | Trường nên ghi |
| --- | --- |
| Login attempt | Event ID, timestamp, principal reference giả danh, source category và outcome. |
| Password verification | Success/failure category, verifier version; không ghi password/verifier. |
| Rate limit decision | Endpoint, quota dimension, decision và retry window phù hợp. |
| MFA challenge | Factor type, challenge reference, outcome và expiry; không ghi OTP/seed. |
| Session creation | Session reference, subject, assurance, create time và expiry. |
| Session revoke | Session reference, actor/reason và timestamp. |
| Password reset | Request reference, verified channel category, outcome và session revocation result. |
| Account state change | Actor, target subject, reason/reference và before/after state theo policy. |

Monitoring nên phát hiện:

- Tỷ lệ password failure tăng bất thường.
- Nhiều account hint khác nhau từ một nguồn.
- Một account bị thử từ nhiều nguồn.
- KDF queue depth hoặc CPU/memory vượt ngưỡng.
- MFA challenge/resend tăng đột biến.
- Session được tạo từ thiết bị hoặc risk context bất thường.
- Reset request tăng hoặc tập trung vào một domain.
- Nhiều lần đổi password/factor sau một login mới.

Không log password, OTP, recovery code, raw session cookie, access token hoặc reset token. Dùng reference/pseudonymous identifier để liên kết event.

## 18. Bộ kiểm thử chấp nhận

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| T01 | Account hợp lệ, password đúng, không yêu cầu MFA | Session mới được tạo sau khi verifier thành công. |
| T02 | Account hợp lệ, password sai | Generic authentication failure; không có session. |
| T03 | Email không tồn tại | Response công khai tương đương nhánh password sai; dummy verifier được chạy. |
| T04 | Account disabled, password đúng | Không cấp session; response không tiết lộ trạng thái cho caller chưa xác thực. |
| T05 | Password đúng, MFA bắt buộc | Chỉ tạo pre-auth transaction; chưa truy cập portal. |
| T06 | MFA sai/hết hạn/replay | Không hoàn tất login; challenge được giới hạn và tiêu thụ đúng policy. |
| T07 | Rate limit bị vượt | Từ chối có kiểm soát; không chạy KDF không cần thiết. |
| T08 | KDF worker pool đầy | Early reject hoặc 503 phù hợp; queue không tăng vô hạn. |
| T09 | Login thành công với session ID cũ | Session ID được xoay; ID cũ không còn quyền. |
| T10 | Cookie bị gửi qua HTTP | Cookie Secure không được browser gửi qua kênh không an toàn. |
| T11 | CSRF request từ origin không tin cậy | Request thay đổi trạng thái bị từ chối. |
| T12 | Password reset token hết hạn hoặc đã dùng | Từ chối; token không thể replay. |
| T13 | Password reset thành công | Verifier mới được lưu; session/token cũ được thu hồi theo policy. |
| T14 | Login event được ghi log | Không có password, OTP, token hoặc cookie trong event. |
| T15 | Email không tồn tại và email tồn tại được đo timing | Không có khác biệt ổn định đủ để enumerate trong điều kiện test. |

Kiểm thử timing cần dùng nhiều mẫu, xen kẽ các nhóm input và so sánh phân phối latency trong staging. Không kết luận từ một request đơn lẻ.

## 19. Ví dụ policy đăng nhập

Một cấu hình khái niệm:

~~~json
{
  "login": {
    "identifier": "verified-work-email",
    "passwordVerifier": {
      "algorithm": "argon2id",
      "uniqueSaltPerAccount": true,
      "rehashOnSuccessfulLogin": true
    },
    "genericFailureResponse": true,
    "dummyVerificationForUnknownAccount": true
  },
  "abuseProtection": {
    "perSourceLimit": true,
    "perAccountHintLimit": true,
    "perTenantLimit": true,
    "globalKdfConcurrencyLimit": true,
    "boundedKdfQueue": true
  },
  "mfa": {
    "requiredForPrivilegedGroups": true,
    "stepUpForSensitiveActions": true,
    "noAutomaticDowngrade": true
  },
  "session": {
    "rotateAfterAuthentication": true,
    "serverSideStore": true,
    "secureCookie": true,
    "idleAndAbsoluteExpiry": true
  },
  "recovery": {
    "oneTimeShortLivedToken": true,
    "genericRequestResponse": true,
    "revokeExistingSessionsByPolicy": true
  }
}
~~~

Đây là ví dụ policy để thảo luận, không phải cấu hình copy trực tiếp. Thuật toán, cost, quota, session lifetime và yêu cầu MFA phải được benchmark, threat model và phê duyệt theo môi trường thật.

## 20. Triển khai theo giai đoạn

Để giảm rủi ro khi chuyển hệ thống đang chạy:

1. **Inventory:** xác định nơi lưu verifier, login endpoint, session, recovery và các consumer liên quan.
2. **Measure:** đo latency/cost KDF, login failure, database load và traffic theo tenant.
3. **Harden storage:** chuyển verifier sang scheme/cost được phê duyệt; hỗ trợ rehash sau login thành công.
4. **Normalize responses:** dùng generic error, dummy verifier và test account enumeration.
5. **Add abuse controls:** triển khai layered rate limit, bounded KDF pool và alert.
6. **Harden session:** xoay session ID, cookie attributes, timeout và revoke.
7. **Integrate MFA policy:** yêu cầu factor cho nhóm cần thiết, kiểm thử fallback và step-up.
8. **Harden recovery:** one-time token, verified channel, quota và session invalidation.
9. **Canary rollout:** triển khai theo nhóm nhỏ, theo dõi latency, false positive và login success.
10. **Review and tune:** điều chỉnh capacity/threshold theo dữ liệu, không giảm yêu cầu bảo mật để cải thiện số liệu ngắn hạn.

Mọi thay đổi cần có rollback plan. Không đổi đồng thời password hashing, session format và recovery semantics nếu chưa có migration path và khả năng tương thích được kiểm thử.

## 21. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Lưu password plaintext hoặc mã hóa có thể giải mã | Database breach làm lộ password trực tiếp. | Password hashing chuyên dụng, salt riêng và access control. |
| Dùng hash nhanh đơn lẻ | Offline guessing nhanh khi verifier bị lộ. | Dùng password hashing scheme có cost phù hợp. |
| Response khác nhau cho email miss/password sai | Account enumeration. | Generic response và dummy verifier. |
| Hash password trước rate limit | Bot có thể làm cạn KDF capacity. | Admission control và bounded worker pool trước KDF. |
| Khóa account vĩnh viễn sau vài lần sai | Attacker có thể khóa tài khoản nạn nhân. | Progressive throttling và recovery an toàn. |
| Cấp session trước khi MFA xong | User có thể truy cập khi factor bắt buộc chưa hoàn tất. | Pre-auth transaction không có quyền nghiệp vụ. |
| Không xoay session ID sau login | Session fixation. | Regenerate và revoke ID cũ. |
| Cookie thiếu Secure/HttpOnly/SameSite phù hợp | Tăng rủi ro lộ cookie hoặc CSRF. | Cookie hardening và CSRF protection theo kiến trúc. |
| Reset token sống lâu hoặc dùng nhiều lần | Token bị replay để chiếm account. | Token ngẫu nhiên, ngắn hạn, purpose-bound và atomic one-time use. |
| Log request body login/reset | Credential và token bị lưu trong telemetry. | Redaction trước ingestion và log schema allowlist. |
| Tự bỏ MFA khi provider lỗi | Downgrade assurance. | Factor dự phòng được phê duyệt hoặc từ chối tạm thời. |
| Không thu hồi session sau reset/compromise | Attacker giữ session cũ sau khi password đổi. | Session/token revocation theo policy và xác minh kết quả. |

## 22. Bài tập phân tích case study

1. Nếu attacker dùng 10.000 email ngẫu nhiên, những lớp nào ngăn account enumeration và KDF exhaustion?
2. Nếu một nhân viên dùng password đúng nhưng MFA provider đang lỗi, hệ thống nên trả trạng thái nào và vì sao?
3. Nếu password reset email bị gửi chậm, làm thế nào tránh response timing tiết lộ account tồn tại?
4. Nếu session store ghi thành công nhưng response Set-Cookie bị mất, lần retry tiếp theo cần xử lý thế nào để tránh session mồ côi hoặc session trùng?
5. Nếu password verifier cũ có cost thấp, làm sao nâng cấp mà không buộc toàn bộ nhân viên reset password cùng lúc?
6. Nếu một account bị credential stuffing nhưng người dùng hợp lệ cũng đăng nhập từ cùng NAT, quota cần kết hợp những chiều nào?
7. Những event nào cần có để điều tra login bất thường mà không lưu password, OTP hoặc session cookie?

## 23. Checklist tổng kết

Trước khi đưa password login vào production, nhóm triển khai cần xác nhận:

- [ ] Account identifier được chuẩn hóa nhất quán và không bị coi là secret.
- [ ] Password chỉ truyền qua TLS và không xuất hiện trong log/telemetry.
- [ ] Verifier dùng password hashing chuyên dụng, salt riêng và cost được benchmark.
- [ ] Có quy trình nâng cấp verifier khi password được xác minh thành công.
- [ ] Unknown account dùng dummy verifier và generic failure response.
- [ ] Rate limit nhiều chiều được áp dụng trước KDF.
- [ ] KDF concurrency/queue có giới hạn và overload được xử lý có kiểm soát.
- [ ] Account lockout không tạo ra denial of service dễ dàng.
- [ ] MFA policy được áp dụng ở server và không tự downgrade.
- [ ] Session chỉ được tạo sau khi mọi factor bắt buộc hoàn tất.
- [ ] Session ID được xoay; cookie được harden; CSRF được xử lý.
- [ ] Logout, password reset và account disable có cơ chế thu hồi session.
- [ ] Reset token ngẫu nhiên, ngắn hạn, purpose-bound và one-time.
- [ ] Audit đủ để điều tra nhưng không chứa credential/token/cookie.
- [ ] Có test cho brute force, stuffing, enumeration, timing, MFA failure, KDF overload, CSRF và session fixation.

**Kết luận:** Một luồng đăng nhập password an toàn không chỉ so sánh password với verifier. Nó phải bảo vệ credential khi truyền và lưu, cân bằng nhánh lỗi để tránh enumeration, giới hạn chi phí online guessing, áp dụng MFA theo policy, tạo session mới sau khi xác thực hoàn tất và thu hồi session khi account thay đổi trạng thái. Password reset, monitoring và overload control là một phần của cùng ranh giới bảo mật; nếu một mắt xích yếu, attacker có thể đi vòng qua login chính.
