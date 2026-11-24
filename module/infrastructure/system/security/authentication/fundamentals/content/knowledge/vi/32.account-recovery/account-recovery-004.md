# Recovery link — Thiết kế liên kết khôi phục tài khoản an toàn

Người dùng quên mật khẩu và yêu cầu gửi liên kết khôi phục tới email đã đăng ký. Email đến hộp thư, người dùng mở liên kết, xác nhận yêu cầu và đặt mật khẩu mới. Luồng này có vẻ đơn giản, nhưng liên kết trong email thực chất là một bearer credential: bất kỳ ai lấy được URL đều có thể thử sử dụng quyền khôi phục mà nó mang theo. Nếu token có entropy thấp, tồn tại quá lâu, dùng được nhiều lần, bị ghi vào log hoặc bị tiêu thụ bởi email scanner trước người dùng, attacker có thể chiếm tài khoản hoặc người dùng hợp lệ bị khóa khỏi quy trình.

**Recovery link** là một liên kết mang token hoặc tham chiếu bí mật để tiếp tục một quy trình khôi phục account. Nó thường được gửi qua email, đôi khi qua một kênh đã xác minh khác. Việc mở link chỉ chứng minh người đang thao tác nắm được liên kết tại thời điểm đó; nó không tự chứng minh danh tính pháp lý, quyền sở hữu account ở mức cao hoặc khả năng chống phishing của kênh email.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, bài học này giúp người học thiết kế recovery link theo ranh giới tin cậy, quản lý token một lần, chống enumeration và replay, xử lý link scanner, bảo vệ URL khỏi rò rỉ, ràng buộc giao dịch với đúng account và áp dụng assurance phù hợp. Mục tiêu là khôi phục quyền truy cập có kiểm soát, sau đó bảo vệ session, authenticator và các credential cũ.

## 1. Recovery link dùng để làm gì?

Recovery link thường được dùng cho:

- Đặt lại mật khẩu khi người dùng quên mật khẩu.
- Xác minh email trong một quy trình đăng ký hoặc thay đổi email.
- Khôi phục quyền truy cập khi người dùng mất một authenticator, nếu policy cho phép.
- Tiếp tục một quy trình account recovery đã được phê duyệt.
- Xác nhận một thao tác nhạy cảm được khởi tạo từ một session khác.

Không nên dùng cùng một loại token cho mọi mục đích. Token đặt lại mật khẩu, xác minh email và xác nhận thay đổi email cần có purpose riêng để token của luồng này không thể bị dùng ở luồng khác.

| Loại link | Mục đích | Quyền nên cấp |
| --- | --- | --- |
| Password reset | Cho phép đặt mật khẩu mới | Chỉ đổi mật khẩu của đúng account, sau khi xác minh transaction |
| Email verification | Xác minh quyền kiểm soát địa chỉ email | Chỉ xác minh địa chỉ đang chờ; không tự đăng nhập hoặc nâng quyền |
| Email change confirmation | Xác nhận thay đổi email | Chỉ xác nhận thay đổi đã được khởi tạo và ràng buộc với account |
| Account recovery continuation | Tiếp tục recovery đã qua bước kiểm tra trước | Chỉ hoàn tất các bước được policy cho phép |
| Sensitive action confirmation | Xác nhận một hành động cụ thể | Chỉ xác nhận đúng action, object và transaction |

Recovery link không phải session cookie tổng quát. Khi token được chấp nhận, server nên tạo một recovery transaction giới hạn quyền và thời gian. Người dùng chỉ được thực hiện thao tác recovery đã định nghĩa, không được dùng token để truy cập API thông thường.

## 2. Threat model và tài sản cần bảo vệ

Recovery là đường vòng quanh quy trình đăng nhập bình thường. Nếu password, passkey hoặc MFA được bảo vệ tốt nhưng recovery link yếu, attacker sẽ nhắm vào recovery thay vì phá credential chính.

### Tài sản

- Account identity và dữ liệu cá nhân.
- Password verifier, passkey public keys, MFA factors và recovery codes.
- Email/phone đã xác minh và các kênh khôi phục.
- Recovery token, pending transaction và trạng thái một lần.
- Session, refresh token và quyền đang hoạt động.
- Audit trail, thông báo bảo mật và bằng chứng phục vụ điều tra.

### Attacker có thể

1. Đoán hoặc thu thập email/username để tìm account tồn tại.
2. Gửi nhiều yêu cầu recovery nhằm spam hộp thư hoặc gây gián đoạn.
3. Chiếm hộp thư, session email hoặc thiết bị đã đăng nhập email.
4. Lấy link từ browser history, proxy log, analytics, screenshot, clipboard hoặc Referer.
5. Dùng malware, extension hoặc phishing page để đánh cắp URL.
6. Replay link đã sử dụng hoặc dùng link hết hạn nếu server kiểm tra không đầy đủ.
7. Lợi dụng email security scanner hoặc link preview tự động mở URL.
8. Lừa help desk đổi email/số điện thoại hoặc bỏ qua bước kiểm tra.
9. Khai thác open redirect, host header poisoning hoặc subdomain bị chiếm để nhận token.
10. Dùng link được forward hoặc gửi nhầm tới account email không còn thuộc người dùng.

### Mục tiêu bảo mật

- Token không thể đoán thực tế và không tiết lộ thông tin account.
- Token gắn với một account, một purpose và một transaction cụ thể.
- Token có thời hạn ngắn, chỉ dùng một lần và được consume nguyên tử.
- GET hoặc link preview không tự hoàn tất recovery.
- Token không bị gửi tới host ngoài trust boundary hoặc xuất hiện trong log.
- Recovery chỉ cấp quyền tối thiểu và không tự bỏ qua MFA/assurance policy.
- Sau khi khôi phục, credential/session cũ được xử lý theo chính sách và người dùng được thông báo.

## 3. Luồng recovery link an toàn

Một luồng password reset phổ biến:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant R as Recovery service
    participant M as Mail service
    participant D as Account / token store
    U->>B: Nhập email tại trang quên mật khẩu
    B->>R: POST recovery request
    R->>R: Validate, rate limit và chống enumeration
    R->>D: Tạo token hash gắn account/purpose/expiry
    R->>M: Gửi email chứa recovery link
    R-->>B: Response chung, không tiết lộ account tồn tại
    U->>B: Mở link trong email
    B->>R: GET landing URL có token
    R->>D: Kiểm tra token, chưa consume
    R-->>B: Landing page + recovery transaction tạm
    U->>B: Xác nhận tiếp tục / gửi mật khẩu mới
    B->>R: POST confirmation + CSRF + transaction
    R->>D: Consume token nguyên tử và cập nhật credential
    R->>D: Thu hồi session/factor theo policy
    R-->>B: Hoàn tất, yêu cầu đăng nhập lại
    R->>M: Gửi thông báo bảo mật
~~~

Điểm quan trọng là **GET link chỉ kiểm tra và chuẩn bị trang**, không tự tiêu thụ token hoặc đổi mật khẩu. Người dùng cần thực hiện một hành động xác nhận rõ ràng bằng POST. Cách này giảm nguy cơ scanner, preview bot hoặc crawler vô tình làm hỏng link trước khi người dùng mở.

### Các bước ở mức khái niệm

1. Người dùng yêu cầu recovery từ trang chính thức.
2. Server kiểm tra request, áp dụng rate limit và trả response chung.
3. Nếu account và policy cho phép, server tạo token ngẫu nhiên, lưu bản hash và gửi link.
4. Browser mở link; server kiểm tra token nhưng chưa hoàn tất thao tác.
5. Server tạo recovery transaction ngắn hạn và chuyển browser tới URL sạch.
6. Người dùng xác nhận hành động recovery qua POST, có CSRF protection.
7. Server kiểm tra lại transaction, token, purpose, expiry và trạng thái account.
8. Server consume token một lần theo thao tác nguyên tử và cập nhật credential.
9. Server thu hồi hoặc đánh giá lại session/authenticator theo policy.
10. Server thông báo hoàn tất qua kênh đã xác minh.

## 4. Tạo recovery token an toàn

Recovery token cần được tạo bằng cryptographically secure pseudorandom number generator (CSPRNG). Không dùng timestamp, UUID phiên bản không phù hợp, username, email, số tăng dần, hash của PII hoặc giá trị ngẫu nhiên từ thư viện không dành cho mật mã.

### 4.1. Entropy và định dạng

Token nên có entropy đủ lớn để brute force là không khả thi trong thời gian hiệu lực. Một lựa chọn thực tế là tạo 32 byte ngẫu nhiên (256 bit), rồi encode Base64url không padding hoặc hex. Token phải được giới hạn độ dài khi nhận để tránh request quá lớn.

Ví dụ định dạng minh họa:

~~~text
https://accounts.example.com/recovery/continue?token=<random-secret>
~~~

Token là bí mật bearer. Không đưa account ID, email, role hoặc thông tin nội bộ vào token dạng rõ. Nếu cần tra cứu record, có thể dùng token ngẫu nhiên làm lookup secret; account/purpose/expiry được lưu server-side.

### 4.2. Hash token trước khi lưu

Khác password, recovery token có entropy cao và được sinh ngẫu nhiên. Server có thể lưu hash mật mã nhanh như SHA-256 của token thay vì lưu token gốc. Khi nhận token, tính hash và so sánh với record.

Điều này giảm hậu quả nếu database token bị đọc: attacker không thể dùng trực tiếp giá trị hash như recovery link. Nếu thiết kế lookup cần bảo vệ thêm trước database correlation, có thể dùng HMAC với server-side pepper/key được giữ trong secret manager.

Không cần dùng password hashing chậm như Argon2 để hash một token ngẫu nhiên entropy cao; điều đó thường làm tăng chi phí kiểm tra mà không đem lại lợi ích tương ứng. Tuy nhiên, token vẫn phải có entropy cao, TTL ngắn và rate limit.

### 4.3. Token record

Một record server-side có thể có:

| Field | Mục đích |
| --- | --- |
| `token_hash` | Hash/HMAC của token bí mật |
| `account_id` | Account được phép recovery |
| `purpose` | Ví dụ `PASSWORD_RESET`, không tái sử dụng giữa luồng |
| `created_at` | Thời điểm phát hành |
| `expires_at` | Thời điểm hết hạn |
| `consumed_at` | Thời điểm sử dụng thành công |
| `revoked_at` | Thời điểm bị thu hồi trước hạn |
| `request_id` | Correlation reference cho audit |
| `tenant_id` | Ràng buộc tenant/realm nếu hệ thống đa tenant |
| `delivery_channel` | Kênh gửi và tham chiếu đã mask |
| `policy_version` | Policy recovery đã áp dụng |

Không lưu token gốc trong database, log hoặc telemetry. Không trả token hash cho client hoặc đưa vào email thay cho token gốc.

## 5. Ràng buộc token với account và purpose

Một token hợp lệ về mặt ngẫu nhiên vẫn có thể nguy hiểm nếu server dùng sai account hoặc mục đích. Token phải ràng buộc với:

- Account ID nội bộ đã xác định ở thời điểm yêu cầu.
- Tenant/realm hoặc namespace account.
- Purpose duy nhất.
- Thao tác cụ thể, ví dụ đặt lại password hoặc xác minh email đang chờ.
- Thời gian hết hạn.
- Trạng thái chưa dùng và chưa thu hồi.
- Policy hoặc assurance cần thiết để hoàn tất.

Không lấy account ID từ request POST cuối cùng rồi áp token lên account đó. Account đích phải được xác định từ token record phía server. Nếu người dùng nhập email ở bước cuối, giá trị đó không được phép ghi đè subject đã ràng buộc.

### Không dùng một token cho nhiều purpose

Ví dụ, token `EMAIL_VERIFY` không được chấp nhận ở endpoint `PASSWORD_RESET`. Nếu một hệ thống dùng cùng bảng token, field purpose phải được kiểm tra chính xác tại mọi endpoint. Không dựa vào tên URL hoặc client-side flow để xác định purpose.

### Token không phải quyền recovery vô hạn

Nếu policy yêu cầu MFA, proofing bổ sung hoặc manual review cho account đặc quyền, token email không được tự động nâng account lên trạng thái đã đáp ứng các điều kiện đó. Recovery link chỉ là một bằng chứng trong quy trình, thường là bằng chứng kiểm soát hộp thư tại thời điểm nhận link.

## 6. Thời hạn, một lần sử dụng và thu hồi

Recovery link nên có TTL ngắn và phù hợp với rủi ro, trải nghiệm người dùng và khả năng vận hành. Không có một con số phù hợp cho mọi dịch vụ. Link đặt lại password thường chỉ có hiệu lực trong một khoảng ngắn đủ để người dùng mở email và hoàn tất thao tác.

### 6.1. Hết hạn

- Lưu `expires_at` ở server và kiểm tra ở thời điểm consume, không tin client clock.
- Dùng UTC và đồng hồ hệ thống được đồng bộ.
- Không gia hạn token cũ chỉ vì người dùng mở landing page.
- Nếu cần link mới, phát hành token mới và áp dụng policy thu hồi token cũ.
- Không để token sống vô hạn hoặc dựa vào việc email còn trong hộp thư.

### 6.2. One-time use

Token chỉ được sử dụng thành công một lần. Kiểm tra và consume cần nguyên tử, tránh hai request đồng thời cùng vượt qua trạng thái chưa dùng.

~~~sql
UPDATE recovery_token
SET consumed_at = CURRENT_TIMESTAMP
WHERE token_hash = :tokenHash
  AND purpose = 'PASSWORD_RESET'
  AND consumed_at IS NULL
  AND revoked_at IS NULL
  AND expires_at > CURRENT_TIMESTAMP;
~~~

Chỉ khi số dòng cập nhật là đúng một, request mới được phép tiếp tục. Trong cùng transaction database, server cập nhật password verifier và các trạng thái liên quan. Nếu cập nhật password thất bại, transaction phải rollback hoặc dùng cơ chế nhất quán tương đương để tránh token bị consume nhưng password chưa đổi mà không có đường retry hợp lệ.

### 6.3. Nhiều link đang hoạt động

Khi người dùng yêu cầu nhiều link:

- Có thể thu hồi token cũ khi phát token mới cho cùng purpose/account.
- Hoặc chỉ cho phép một số lượng nhỏ token song song theo policy.
- Response và email phải làm rõ link mới nhất có thể vô hiệu link trước.
- Không để attacker spam recovery request khiến nạn nhân liên tục nhận link mới và vô tình dùng link hết hiệu lực.
- Áp dụng cooldown/rate limit và cảnh báo khi có hành vi bất thường.

### 6.4. Revoke trước hạn

Token có thể bị thu hồi khi:

- Người dùng hủy recovery.
- Password hoặc email đã được thay đổi qua một kênh khác.
- Account bị khóa, disable hoặc có incident.
- Một token mới thay thế token cũ.
- Risk policy phát hiện request đáng ngờ.
- Admin/reviewer hủy quy trình theo phê duyệt.

Revocation phải được kiểm tra ở bước consume, không chỉ ở bước GET landing page.

## 7. Email scanners, link previews và GET an toàn

Email gateway, antivirus, anti-phishing service, chat app và link preview có thể tự động mở URL để kiểm tra trước khi người dùng nhấn. Nếu endpoint GET lập tức tiêu thụ token hoặc đổi password, scanner có thể làm link mất hiệu lực.

### Thiết kế GET/POST

- `GET /recovery/continue?token=...` chỉ kiểm tra sơ bộ và hiển thị trang xác nhận; không thay đổi password, email hoặc authenticator.
- Không consume token chỉ vì có HTTP GET, HEAD hoặc request prefetch.
- Landing page tạo một recovery transaction ngắn hạn, ràng buộc với browser context và CSRF token.
- Người dùng bấm nút xác nhận; browser gửi POST.
- POST kiểm tra transaction, CSRF, token purpose, expiry và trạng thái one-time rồi consume nguyên tử.
- Không tự động submit form ngay khi trang tải; scanner có thể thực thi JavaScript.

Một scanner nâng cao có thể tương tác với trang hoặc thực hiện request nhiều loại. Vì vậy, GET/POST separation giảm rủi ro phổ biến nhưng không phải bảo đảm tuyệt đối. Với account có hậu quả cao, cần thêm bước xác nhận độc lập hoặc assurance mạnh hơn.

### Recovery transaction trong browser

Sau khi GET kiểm tra token, server có thể tạo một transaction tạm thời và đặt cookie ngắn hạn:

~~~http
Set-Cookie: __Host-recovery-tx=<opaque-reference>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=600
Cache-Control: no-store
Referrer-Policy: no-referrer
~~~

Cookie này chỉ tham chiếu recovery transaction, không phải session đăng nhập. Nó nên có TTL rất ngắn, scope host-only, không được gửi tới subdomain khác và chỉ được dùng tại endpoint recovery. POST cuối cần CSRF token hoặc cơ chế anti-CSRF phù hợp.

Không gắn transaction tạm với mọi session đăng nhập đang có theo cách có thể ghi đè login state. Nếu người dùng mở link trên thiết bị khác, transaction được tạo riêng trong browser đó.

## 8. URL leakage và bảo vệ landing page

Token trong query string hoặc path có thể bị lưu ở:

- Browser history và đồng bộ lịch sử.
- Reverse proxy, CDN, WAF, application access log.
- Analytics, monitoring, error reporting và session replay.
- HTTP Referer khi landing page tải tài nguyên bên thứ ba.
- Screenshot, clipboard, crash report hoặc extension độc hại.
- Email gateway, link scanner và hệ thống hỗ trợ.

### Biện pháp giảm rò rỉ

1. Chỉ dùng HTTPS và host recovery cố định, có chứng chỉ hợp lệ.
2. Dùng `Referrer-Policy: no-referrer`.
3. Đặt `Cache-Control: no-store` và tránh cache URL chứa token ở CDN/proxy/browser.
4. Không tải analytics, quảng cáo, font, image hoặc script bên thứ ba trên trang có token.
5. Redact query/path token ở access log, tracing, APM và error reporting.
6. Sau khi server xác nhận token và tạo recovery transaction tạm, redirect tới URL sạch không còn token.
7. Không hiển thị token trong HTML, DOM, JavaScript console hoặc thông báo lỗi.
8. Hạn chế extension/script trên trang recovery; dùng CSP nghiêm ngặt.
9. Không đưa token vào Referer hoặc liên kết điều hướng tới host khác.

Ví dụ header cho landing page:

~~~http
Cache-Control: no-store
Pragma: no-cache
Referrer-Policy: no-referrer
X-Content-Type-Options: nosniff
Content-Security-Policy: default-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'
~~~

Không ghi raw token vào audit. Có thể ghi token reference không bí mật, request ID và reason code. Khi cần đối chiếu token, dùng hash/HMAC hoặc ID record nội bộ đã được kiểm soát.

## 9. Host, domain và redirect trust

Không xây recovery URL bằng Host header tùy ý của request. Attacker có thể gửi Host giả hoặc khai thác cấu hình proxy để email recovery chứa link tới domain của attacker.

Ví dụ sai:

~~~java
String link = "https://" + request.getHeader("Host")
    + "/recovery?token=" + token;
~~~

Thiết kế an toàn hơn:

- Lấy origin từ cấu hình server đã triển khai, ví dụ `https://accounts.example.com`.
- Nếu multi-tenant, map tenant tới domain đã được xác minh và allowlist; không dùng domain tự khai trong request.
- Dùng URL builder để encode token đúng cách.
- Không cho phép return URL ngoài danh sách route/domain đã phê duyệt.
- Không redirect theo query parameter tùy ý sau recovery.
- Kiểm tra cookie scope và host-only; tránh đặt recovery cookie ở Domain cha nếu không cần.
- Bảo vệ subdomain recovery, DNS và certificate lifecycle; không để host cũ hoặc CNAME bị chiếm.

Email nên cho người dùng biết domain chính thức để kiểm tra. Nếu domain gửi mail hoặc link thay đổi, cần thông báo qua kênh đáng tin và kiểm soát chống phishing.

## 10. Account enumeration, spam và abuse controls

Endpoint yêu cầu recovery không nên tiết lộ account có tồn tại hay không. Với cùng một input công khai, response nên tương tự:

> Nếu thông tin phù hợp với một tài khoản, hướng dẫn khôi phục sẽ được gửi tới kênh đã đăng ký.

Không trả “email chưa đăng ký”, “account đã bị khóa” hoặc “không có số điện thoại này” nếu attacker có thể dùng endpoint để dò account.

### Kiểm soát abuse

- Rate limit theo identifier đã chuẩn hóa, IP/network, device/session, tenant và global.
- Giới hạn số email được gửi trong một khoảng thời gian.
- Cooldown giữa các lần gửi và chống spam vào hộp thư nạn nhân.
- Phát hiện nhiều identifier từ một nguồn hoặc nhiều nguồn cùng nhắm vào một account.
- Dùng CAPTCHA/bot challenge khi risk signal yêu cầu, có phương thức accessible thay thế.
- Không khóa account chỉ vì có nhiều recovery request; attacker có thể tạo denial of service.
- Ghi nhận request đáng ngờ và thông báo phù hợp mà không lộ trạng thái account.
- Giới hạn chi phí gọi email provider và bảo vệ queue khỏi flood.

Không chỉ rate limit endpoint công khai. Endpoint resend, verify, cancel, recovery status và help desk cũng có thể bị lạm dụng hoặc dùng để enumerate.

## 11. Recovery link và mức assurance

Email link chỉ chứng minh người dùng có thể truy cập hộp thư hoặc URL tại thời điểm đó. Hộp thư có thể bị compromise, forward, đồng bộ trên thiết bị chung hoặc bị chiếm qua recovery yếu hơn. Vì vậy, recovery link không mặc định đủ cho mọi account.

| Account / hành động | Cách dùng recovery link |
| --- | --- |
| Account cá nhân rủi ro thấp | Có thể cho phép reset password nếu email đã xác minh và các abuse controls đạt |
| Account chứa dữ liệu nhạy cảm | Cân nhắc thêm factor, thông báo, revoke session và risk review |
| Account tài chính hoặc có giao dịch giá trị cao | Email link có thể chỉ là một bước; yêu cầu assurance bổ sung theo policy |
| Admin/privileged account | Không nên chỉ dựa vào email link; cần credential dự phòng, phê duyệt độc lập hoặc quy trình mạnh hơn |
| Account mất toàn bộ authenticator | Dùng quy trình recovery riêng, có proofing/step-up và audit; link email không tự khôi phục MFA |

Policy nên phân biệt:

- **Mailbox control:** có quyền mở email/link.
- **Account continuity:** có bằng chứng liên tục kiểm soát account từ trước.
- **Identity proofing:** đã xác minh người với danh tính được tuyên bố.
- **Authentication assurance:** mức độ mạnh của lần xác thực hiện tại.
- **Authorization:** quyền được phép sau khi recovery.

Không gộp các khái niệm này thành một cờ `verified=true`.

## 12. Sau khi recovery: credential, session và thông báo

Đặt lại password thành công không tự động làm mọi credential bị đánh cắp mất hiệu lực. Server cần có policy rõ ràng:

### Password

- Lưu password mới bằng password hashing scheme phù hợp và salt riêng.
- Không gửi password mới qua email.
- Không log password hoặc giữ trong telemetry.
- Có thể yêu cầu đăng nhập lại thay vì tự động tạo session, đặc biệt khi recovery có assurance thấp.

### Sessions và tokens

- Thu hồi session hiện tại hoặc toàn bộ session theo mức rủi ro.
- Revoke refresh tokens và token family có liên quan.
- Với JWT access token tự chứa, dùng cơ chế revocation/version hoặc TTL ngắn; đổi password không tự làm chữ ký JWT mất hiệu lực.
- Không để recovery transaction trở thành session tổng quát.
- Yêu cầu reauthentication trên thiết bị mới trước thao tác nhạy cảm.

### Passkeys và MFA

- Không tự động xóa toàn bộ passkey/MFA nếu policy không yêu cầu; người dùng có thể cần credential còn kiểm soát.
- Nếu nghi ngờ attacker đã thêm authenticator, revoke credential đó và yêu cầu đăng ký lại bằng quy trình tin cậy.
- Khi mất MFA, không dùng email link đơn lẻ để âm thầm tắt MFA cho account đặc quyền.
- Thông báo khi thêm/xóa authenticator, đổi password hoặc thay đổi recovery channel.

### Email và audit

Gửi thông báo hoàn tất tới kênh đã xác minh, nêu account đã được cập nhật và cách báo cáo nếu không phải người dùng thực hiện. Thông báo không chứa token hoặc password. Lưu audit gồm request reference, token record ID, purpose, decision, timestamp, credential version và các session/token đã revoke.

## 13. Java/Spring: tạo và consume recovery token

Ví dụ dưới đây minh họa nguyên tắc. Cần dùng CSPRNG, transaction database, secret manager và framework bảo mật được hỗ trợ trong ứng dụng thực tế.

### 13.1. Tạo token

~~~java
String createRecoveryToken() {
    byte[] bytes = new byte[32]; // 256 bits
    secureRandom.nextBytes(bytes);
    return Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(bytes);
}

String tokenDigest(String rawToken) {
    return HexFormat.of().formatHex(
        MessageDigest.getInstance("SHA-256")
            .digest(rawToken.getBytes(StandardCharsets.US_ASCII))
    );
}
~~~

Tạo token xong, lưu digest cùng account, purpose, expiry và trạng thái. Gửi raw token một lần qua mail provider; không ghi token vào log hoặc database. Nếu dùng HMAC, key phải được quản lý riêng và có kế hoạch rotation.

### 13.2. Kiểm tra GET không consume

~~~java
RecoveryLandingResult openRecoveryLink(String rawToken) {
    if (rawToken == null || rawToken.length() > MAX_TOKEN_LENGTH) {
        return RecoveryLandingResult.invalid();
    }

    String digest = tokenDigest(rawToken);
    RecoveryToken record = tokenRepository.findActive(
        digest,
        RecoveryPurpose.PASSWORD_RESET,
        clock.instant()
    );
    if (record == null) {
        return RecoveryLandingResult.invalidOrExpired();
    }

    // Tạo transaction tạm có TTL ngắn; chưa consume token gốc.
    RecoveryBrowserTransaction browserTx =
        recoveryTransactions.create(record.id(), record.accountId());

    return RecoveryLandingResult.ready(browserTx.publicReference());
}
~~~

Landing response đặt cookie transaction `Secure`, `HttpOnly`, `SameSite` phù hợp, `Path=/`, host-only và `Cache-Control: no-store`. Sau đó redirect tới URL sạch. Không đưa raw token vào response HTML.

### 13.3. Consume nguyên tử khi người dùng xác nhận

~~~java
RecoveryResult confirmPasswordReset(
        String browserTransactionId,
        String csrfToken,
        char[] newPassword) {

    RecoveryBrowserTransaction tx =
        recoveryTransactions.loadActive(browserTransactionId);
    if (tx == null || tx.isExpired()) {
        return RecoveryResult.restart();
    }

    csrfValidator.requireValid(tx, csrfToken);
    passwordPolicy.requireAcceptable(newPassword);

    return database.inTransaction(() -> {
        int consumed = tokenRepository.consumeIfActive(
            tx.recoveryTokenId(),
            RecoveryPurpose.PASSWORD_RESET,
            clock.instant()
        );
        if (consumed != 1) {
            return RecoveryResult.invalidOrExpired();
        }

        Account account = accountRepository.lockById(tx.accountId());
        if (account == null || !account.canRecover()) {
            throw new RecoveryRejectedException();
        }

        passwordService.replacePassword(account, newPassword);
        sessionService.revokeAccordingToRecoveryPolicy(account);
        recoveryTransactions.consume(tx.id());
        audit.recordPasswordRecovery(account.id(), tx.id());
        return RecoveryResult.completed();
    });
}
~~~

Đây là pseudocode, không phải implementation hoàn chỉnh. Cần bảo đảm:

- Token record và browser transaction được ràng buộc với cùng account/purpose.
- Consume token, đổi password, revoke trạng thái và consume browser transaction có tính nhất quán.
- Xử lý rollback, retry và lỗi gửi thông báo sau commit.
- Không trả thông tin account tồn tại cho client.
- Password verifier dùng Argon2id, scrypt hoặc thuật toán chuyên dụng phù hợp với policy và benchmark.
- Xóa/ghi đè buffer password khi có thể; tránh giữ dữ liệu bí mật lâu hơn cần thiết.
- Kiểm tra account state và risk policy tại thời điểm consume, không chỉ lúc gửi email.

## 14. Các lỗi recovery link thường gặp

| Lỗi | Hậu quả | Kiểm soát |
| --- | --- | --- |
| Token dựa trên timestamp hoặc ID tăng dần | Attacker đoán link | CSPRNG, entropy cao |
| Lưu raw token trong database | Database leak dẫn tới account takeover | Lưu hash/HMAC |
| Token không gắn purpose | Token xác minh email có thể reset password | Purpose-specific validation |
| Token không gắn account phía server | Có thể áp token lên account do client chọn | Account ID lấy từ token record |
| Token không hết hạn | Link cũ tồn tại lâu | TTL server-side |
| Token dùng nhiều lần | Replay và nhiều lần đổi credential | Atomic one-time consume |
| GET lập tức consume token | Scanner/link preview làm hỏng link | GET không consume; POST xác nhận |
| Token xuất hiện trong access log | Lộ bearer credential | Redaction ở proxy, app, APM và analytics |
| Trang recovery tải script bên thứ ba | Token có thể rò qua Referer/JS | No-referrer, CSP, không third-party resources |
| Dùng Host header để tạo link | Email có thể trỏ tới domain attacker | Origin từ cấu hình allowlist |
| Return URL tùy ý | Open redirect/phishing | Internal route hoặc exact allowlist |
| Response phân biệt account tồn tại | Account enumeration | Response chung, rate limit |
| Rate limit chỉ theo IP | NAT bypass hoặc khóa nhầm nhiều người | Nhiều chiều giới hạn và risk policy |
| Email link tự động đăng nhập đầy đủ | Kênh email trở thành bypass MFA | Recovery scope tối thiểu, policy assurance |
| Đổi password nhưng giữ mọi session | Session attacker tiếp tục hoạt động | Revoke session/refresh theo policy |
| Link mới không thu hồi link cũ | Nhiều token cùng có hiệu lực ngoài ý muốn | Token replacement/revocation policy |
| Recovery cho admin chỉ dựa vào email | Bypass kiểm soát đặc quyền | Step-up, independent approval hoặc proofing |
| Không thông báo sau recovery | Người dùng không phát hiện takeover | Security notification và incident path |

## 15. Ma trận kiểm thử recovery link

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Token được tạo bằng CSPRNG | Đủ entropy, không suy ra từ account/time |
| Database token bị đọc | Chỉ có digest/HMAC, không dùng trực tiếp làm link |
| Token sai hoặc không tồn tại | Response chung, không tiết lộ account |
| Token đúng nhưng purpose sai | Từ chối |
| Token thuộc account A nhưng client gửi account B | Bỏ qua account client; chỉ xử lý subject đã ràng buộc hoặc từ chối |
| Token hết hạn | Từ chối theo server clock |
| Token đã revoke | Từ chối |
| Token đã consume | Từ chối replay |
| Hai POST consume đồng thời | Chỉ một request thành công |
| GET link từ email scanner | Không consume token, không đổi credential |
| HEAD hoặc preview request | Không làm thay đổi trạng thái recovery |
| User bấm xác nhận và POST hợp lệ | Consume một lần, cập nhật credential |
| POST thiếu/sai CSRF hoặc browser transaction | Từ chối |
| Token bị copy sang host ngoài | Host allowlist và browser transaction không cấp quyền ở host lạ |
| Host header giả khi tạo email | Link vẫn dùng origin từ cấu hình tin cậy |
| URL chứa token xuất hiện trong log | Redaction test phát hiện và loại bỏ |
| Landing page tải tài nguyên bên thứ ba | CSP/no-referrer policy ngăn rò rỉ |
| Return URL là domain ngoài | Từ chối hoặc dùng route nội bộ mặc định |
| Nhiều recovery request trong thời gian ngắn | Throttle/cooldown; không khóa account tùy tiện |
| Account đặc quyền chỉ có email link | Không tự động bỏ qua assurance bổ sung |
| Recovery thành công | Session/token được revoke theo policy và thông báo được gửi |
| Mail provider lỗi sau khi tạo token | Queue/retry có kiểm soát; không log raw token |
| Account bị disable giữa GET và POST | POST kiểm tra lại account state và từ chối |
| Người dùng yêu cầu link mới | Token cũ được thay thế hoặc xử lý theo concurrency policy |

### Tình huống thực hành

Một ứng dụng gửi email reset password với link có token ngẫu nhiên. Endpoint GET lập tức đánh dấu token đã dùng rồi chuyển tới form đặt mật khẩu. Người dùng báo link hết hạn ngay khi mở email. Access log lưu đầy đủ query string, và URL được tạo từ Host header của request. Sau khi reset, các session đang đăng nhập trên thiết bị khác vẫn hoạt động.

**Yêu cầu:** xác định các lỗi và thiết kế lại luồng.

**Hướng giải:**

1. Kiểm tra email gateway/link scanner; chuyển GET thành bước kiểm tra không consume và không đổi credential.
2. Tạo recovery browser transaction ngắn hạn, cookie host-only `Secure`, `HttpOnly`, `SameSite` phù hợp; người dùng xác nhận bằng POST có CSRF.
3. Lưu hash token, gắn account/purpose/expiry và consume nguyên tử khi POST hợp lệ.
4. Redact token khỏi access log, proxy, APM và analytics; đặt `no-store`, `no-referrer`, CSP và redirect tới URL sạch.
5. Tạo link từ origin cố định/allowlist, không lấy Host header; kiểm soát redirect đích.
6. Sau reset, thu hồi session và refresh token theo policy; với JWT access token, áp dụng TTL/version/denylist/introspection phù hợp.
7. Gửi thông báo bảo mật, ghi audit và theo dõi hoạt động sau recovery; yêu cầu assurance cao hơn với account đặc quyền.

## 16. Câu hỏi tự kiểm tra

1. **Recovery link chứng minh điều gì?** Chủ thể đang thao tác nắm được link hoặc hộp thư tại thời điểm đó; không tự chứng minh danh tính pháp lý hay assurance cao.
2. **Vì sao token cần được hash khi lưu?** Giảm hậu quả nếu database bị đọc; attacker không thể dùng digest như raw bearer token.
3. **Vì sao GET không nên consume token?** Email scanner, crawler và link preview có thể tự mở URL trước người dùng.
4. **Làm sao ngăn replay?** TTL, trạng thái một lần, atomic consume, purpose binding và kiểm tra server-side ở thời điểm xác nhận.
5. **Vì sao cần response chung cho recovery request?** Để attacker không dò được account tồn tại qua endpoint công khai.
6. **Vì sao không lấy host từ request để tạo recovery URL?** Host header có thể bị giả mạo hoặc proxy cấu hình sai, khiến link trỏ tới domain attacker.
7. **Recovery link có thay thế MFA không?** Không mặc định. Assurance của link phụ thuộc bảo mật hộp thư và policy của account; account nhạy cảm cần bước bổ sung.
8. **Sau reset password cần làm gì với session?** Revoke session/refresh token theo policy, đánh giá JWT còn hiệu lực, thông báo và audit.

**Ghi nhớ:** Recovery link là bearer credential có quyền rất nhạy cảm. Hãy tạo token entropy cao bằng CSPRNG, chỉ lưu hash, ràng buộc account/purpose/expiry, để GET không tiêu thụ link, yêu cầu POST xác nhận có CSRF và consume nguyên tử. Bảo vệ URL khỏi log/Referer, dùng host cố định, không tiết lộ account existence, và sau recovery xử lý session, authenticator cùng thông báo theo mức assurance của account.
