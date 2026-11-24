# Web login

> **Chương:** Authentication trong web  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Thiết kế luồng đăng nhập web an toàn từ lúc người dùng mở trang, gửi credential, xác thực, tạo session đến khi đăng xuất hoặc khôi phục tài khoản.

## 1. Web login là gì?

**Web login (đăng nhập web)** là quy trình một ứng dụng web xác minh danh tính người dùng và tạo trạng thái xác thực để các request tiếp theo được xử lý theo quyền của người đó. Quy trình thường bắt đầu trong browser, đi qua frontend và backend, có thể tích hợp identity provider (IdP), MFA hoặc passkey, rồi tạo session hoặc token cho những lần truy cập tiếp theo.

Ví dụ, nhân viên mở cổng quản lý nội bộ, nhập tài khoản và mật khẩu, hoàn tất MFA, rồi được chuyển tới trang công việc. Browser nhận một session cookie. Những request sau gửi cookie này; server tra cứu session, xác định principal và kiểm tra quyền trên từng tài nguyên.

Một màn hình có hai ô username/password chưa phải là một thiết kế đăng nhập hoàn chỉnh. Hệ thống còn phải bảo vệ credential khi truyền và lưu, xác minh đúng origin, chống giả mạo request, chống dò mật khẩu, quản lý session, xử lý MFA, logout và recovery. Nếu một mắt xích yếu, attacker có thể chiếm tài khoản dù mật khẩu được hash tốt.

### Kết quả học tập

Sau bài này, người học có thể:

- Mô tả các bước của web login và ranh giới tin cậy giữa browser, frontend, backend và IdP.
- Phân biệt xác thực bằng mật khẩu, passkey và đăng nhập liên kết OIDC.
- Chọn session cookie hoặc mô hình token phù hợp với kiến trúc web.
- Bảo vệ session bằng cookie attributes, rotation, timeout và revocation.
- Ngăn CSRF, login CSRF, session fixation, open redirect và credential leakage.
- Thiết kế MFA, rate limit, thông báo đăng nhập và recovery.
- Kiểm thử luồng đăng nhập, đăng xuất và các lỗi bảo mật thường gặp.

## 2. Các thành phần trong luồng đăng nhập

Một ứng dụng web có thể gồm:

| Thành phần | Vai trò |
|---|---|
| Browser | Hiển thị form, chạy frontend và lưu cookie theo chính sách |
| Login page | Thu thập username, password hoặc khởi tạo passkey/federation |
| Web frontend | Gửi request và hiển thị kết quả; không nên giữ secret dùng chung |
| Backend/authentication service | Kiểm tra credential, MFA, risk và trạng thái tài khoản |
| Identity provider (IdP) | Xác thực người dùng và phát hành kết quả đăng nhập liên kết |
| Session store | Lưu trạng thái phiên phía server nếu dùng session cookie |
| Authorization layer | Quyết định principal có quyền thực hiện action trên resource |
| Audit/monitoring | Ghi sự kiện đăng nhập, lỗi và thay đổi bảo mật mà không lộ secret |

Không phải ứng dụng nào cũng có frontend/backend tách riêng. Ứng dụng server-rendered có thể xử lý form và session trong cùng backend; SPA có thể dùng backend-for-frontend (BFF); ứng dụng có thể chuyển sang IdP qua OpenID Connect. Dù kiến trúc khác nhau, browser và mọi thành phần trung gian đều phải được xem là ranh giới bảo mật cần kiểm soát.

## 3. Luồng đăng nhập cơ bản bằng mật khẩu

Luồng phổ biến:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant W as Web application
    participant A as Authentication service
    participant S as Session store
    U->>B: Mở trang login qua HTTPS
    B->>W: GET /login
    W-->>B: Form + CSRF token
    U->>B: Nhập username/password
    B->>W: POST /login + form + CSRF token
    W->>A: Kiểm tra credential và chính sách
    A->>A: Verify password hash / MFA / risk
    A->>S: Tạo session ID mới
    S-->>A: Session active
    A-->>W: Principal + session
    W-->>B: Set-Cookie session; redirect an toàn
    B->>W: Request tiếp theo + session cookie
    W->>S: Tra session và kiểm tra trạng thái
    S-->>W: Principal và session context
    W-->>B: Protected page
~~~

Các bước quan trọng:

1. Browser truy cập trang login qua HTTPS và nhận form.
2. Server tạo CSRF token hoặc cơ chế bảo vệ tương đương cho thao tác đăng nhập.
3. Người dùng gửi credential bằng POST qua HTTPS.
4. Server chuẩn hóa identifier theo chính sách, tra tài khoản và verify password hash.
5. Nếu tài khoản yêu cầu MFA hoặc step-up, server hoàn tất challenge trước khi tạo session đầy đủ.
6. Sau xác thực thành công, server tạo session ID mới, gắn với principal và phát cookie bảo vệ.
7. Request tiếp theo được xác minh session trước khi authorization.
8. Server ghi audit event và thông báo theo chính sách.

Không tạo session đã xác thực chỉ vì người dùng đã tải trang login hoặc nhập username. Session trước xác thực, nếu có, phải được nâng cấp bằng cách thay session ID sau khi xác thực thành công.

## 4. Trang login và form credential

Trang login là một bề mặt tấn công quan trọng vì nó nhận dữ liệu nhạy cảm và thường được người dùng tin tưởng.

### Form an toàn

- Dùng HTTPS cho toàn bộ trang và request chứa credential.
- Dùng POST cho việc gửi password; không đưa password vào URL hoặc query string.
- Dùng CSRF token cho thao tác thay đổi trạng thái và đánh giá riêng login CSRF.
- Dùng input phù hợp như autocomplete username và autocomplete current-password để hỗ trợ password manager.
- Không chặn paste hoặc tự tạo quy tắc khiến password manager không hoạt động.
- Không ghi password, OTP hoặc recovery code vào log, analytics hay error reporting.
- Tránh tải script bên thứ ba không cần thiết trên trang login.
- Dùng Content Security Policy (CSP), output encoding và dependency hygiene để giảm nguy cơ XSS.
- Hiển thị lỗi dễ hiểu nhưng không tiết lộ tài khoản có tồn tại hay không.

Ví dụ form minh họa:

~~~html
<form method="post" action="/login">
  <input type="hidden" name="csrf_token" value="SERVER_GENERATED_TOKEN">
  <label for="username">Tài khoản</label>
  <input id="username" name="username" autocomplete="username" required>
  <label for="password">Mật khẩu</label>
  <input id="password" name="password"
         type="password" autocomplete="current-password" required>
  <button type="submit">Đăng nhập</button>
</form>
~~~

Đây chỉ là cấu trúc giao diện. Backend vẫn phải xác minh CSRF token, credential, trạng thái tài khoản, rate limit và session policy. Không dùng hidden field để tin role, user ID hoặc tenant do browser gửi.

### Thông báo lỗi

Tránh phản hồi khác biệt quá rõ như “email không tồn tại” và “mật khẩu sai”. Có thể dùng thông báo chung: “Thông tin đăng nhập không hợp lệ hoặc bạn không thể đăng nhập lúc này.” Thông tin hỗ trợ chi tiết có thể hiển thị sau khi người dùng chứng minh quyền kiểm soát tài khoản.

Không làm phản hồi quá mơ hồ đến mức người dùng không biết cách khôi phục. Cân bằng giữa chống account enumeration và trải nghiệm: hướng dẫn recovery chung, liên kết trợ giúp chính thức và thông báo bảo mật phù hợp.

## 5. Bảo vệ password ở phía server

Password phải được gửi qua TLS và lưu dưới dạng password verifier bằng password hashing scheme chuyên dụng. Không lưu password bằng mã hóa có thể giải mã và không dùng hash nhanh tổng quát như SHA-256 đơn thuần làm password storage.

### Lưu password

- Dùng Argon2id hoặc password hashing scheme được nền tảng/tiêu chuẩn hiện hành khuyến nghị; bcrypt hoặc PBKDF2 có thể cần cho hệ thống tương thích theo cấu hình phù hợp.
- Mỗi password có salt ngẫu nhiên riêng.
- Chọn tham số memory/time/cost phù hợp với năng lực server và kiểm tra định kỳ.
- Có thể dùng pepper được bảo vệ riêng trong secret manager/HSM nếu kiến trúc hỗ trợ.
- Không log password, request body nhạy cảm hoặc verifier.
- Kiểm tra password mới với blocklist password phổ biến/bị lộ.

### Xác minh

Server lấy verifier theo account record và gọi hàm verify an toàn. Không tự so sánh hash bằng chuỗi đơn giản nếu thư viện có hàm constant-time verify. Nếu account không tồn tại, có thể chạy đường xử lý tương đương về mặt thời gian ở mức phù hợp để giảm account enumeration.

### Chính sách password

Ưu tiên password đủ dài, duy nhất, cho phép password manager và paste. Không ép thay ký tự theo mẫu máy móc hoặc thay đổi định kỳ tùy tiện khi không có bằng chứng compromise hay yêu cầu chính sách cụ thể. Khi password bị lộ, cần đổi password và đánh giá session, refresh token, MFA và recovery method liên quan.

## 6. Session cookie sau khi đăng nhập

Trong ứng dụng web server-side, mô hình phổ biến là server tạo session record và browser giữ một session identifier ngẫu nhiên trong cookie. Cookie là bearer credential: ai lấy được giá trị hợp lệ có thể cố sử dụng phiên.

Ví dụ:

~~~http
Set-Cookie: __Host-session=<RANDOM_SESSION_ID>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Các thuộc tính:

- **Secure:** browser chỉ gửi cookie qua HTTPS.
- **HttpOnly:** JavaScript không đọc trực tiếp cookie.
- **SameSite:** giới hạn một số request cross-site; Lax/Strict/None phải được chọn theo luồng thực tế.
- **Path=/:** cookie áp dụng cho toàn host.
- **__Host- prefix:** yêu cầu Secure, Path=/ và không có Domain, giúp giới hạn cookie ở host đã tạo.
- **Không đặt Domain:** giảm việc cookie bị chia sẻ tới subdomain khác.

Không dựa vào cookie expiry phía browser để thay thế kiểm tra session phía server. Server phải kiểm tra trạng thái, idle timeout, absolute timeout và revocation.

### Session ID

- Sinh bằng CSPRNG, đủ entropy và không chứa user ID hoặc dữ liệu đoán được.
- Không dùng session ID từ URL.
- Không đặt session ID trong localStorage nếu mô hình cookie server-side đáp ứng nhu cầu.
- Không log giá trị cookie/session ID.
- Chỉ phát cookie sau khi response đi qua HTTPS.

## 7. Session fixation và rotation

Session fixation xảy ra khi attacker khiến nạn nhân sử dụng một session identifier mà attacker đã biết hoặc kiểm soát. Nếu ứng dụng giữ nguyên session ID đó sau khi đăng nhập, attacker có thể dùng cùng ID để chiếm phiên đã xác thực.

### Phòng vệ

1. Tạo session ID mới sau khi xác thực thành công.
2. Rotation thêm lần nữa khi nâng quyền hoặc hoàn tất step-up quan trọng.
3. Vô hiệu hóa session ID cũ ở server.
4. Không chấp nhận session ID do client tự chọn làm phiên xác thực.
5. Không đưa session ID vào URL, referrer hoặc log.
6. Kiểm tra framework session middleware có rotate đúng thời điểm.

Chỉ đổi cookie ở browser mà không vô hiệu hóa session cũ phía server không đủ. Ngược lại, xóa session cũ trước khi tạo session mới có thể gây lockout nếu luồng cập nhật thất bại; cần xử lý nguyên tử và có kiểm thử.

## 8. Idle timeout, absolute timeout và concurrent sessions

Session cần thời hạn phù hợp với mức rủi ro và trải nghiệm.

- **Idle timeout:** hết hạn sau một khoảng không có hoạt động đủ điều kiện.
- **Absolute timeout:** giới hạn tổng thời gian sống, kể cả khi session vẫn hoạt động.
- **Reauthentication:** yêu cầu xác thực lại trước hành động nhạy cảm hoặc sau một khoảng thời gian.
- **Concurrent session policy:** quyết định có cho phép nhiều thiết bị/phiên cùng lúc và cách người dùng quản lý chúng.

Không cập nhật idle timeout chỉ vì một request nền, polling hoặc tab bỏ quên nếu điều đó kéo dài session vô hạn. Hành động nhạy cảm như đổi email khôi phục, thêm passkey, xem dữ liệu nhạy cảm hoặc thao tác quản trị có thể cần step-up authentication.

### Thu hồi session

Server nên hỗ trợ:

- Logout một session.
- Logout tất cả session của tài khoản.
- Thu hồi session sau đổi password do compromise hoặc recovery.
- Thu hồi khi admin khóa tài khoản/offboard.
- Thu hồi khi phát hiện session theft hoặc rủi ro cao.
- Xem danh sách session/thiết bị và cho người dùng thu hồi thiết bị không nhận ra.

Nếu session được lưu server-side, việc revoke có thể vô hiệu hóa ngay khi mọi request tra trạng thái hiện tại. Nếu dùng token tự chứa, cần tính đến cache, expiry, denylist hoặc introspection.

## 9. CSRF và login CSRF

Cross-Site Request Forgery (CSRF) lợi dụng việc browser tự gửi cookie tới website mà người dùng đã đăng nhập. Attacker có thể khiến browser gửi request thay đổi trạng thái mà người dùng không chủ ý.

### Phòng vệ CSRF

- Dùng CSRF token gắn với session/form cho request thay đổi trạng thái.
- Kiểm tra Origin hoặc Referer theo chính sách phù hợp.
- Cấu hình SameSite cookie như một lớp phòng vệ bổ sung.
- Không dùng GET cho thao tác thay đổi trạng thái.
- Không xem CORS là biện pháp thay thế CSRF token.
- Yêu cầu reauthentication/step-up cho thao tác nhạy cảm.

### Login CSRF

Login CSRF xảy ra khi attacker khiến browser nạn nhân đăng nhập vào tài khoản do attacker kiểm soát. Nạn nhân có thể tải lên dữ liệu, lưu thông tin hoặc thực hiện thao tác mà attacker sau đó truy cập trong tài khoản đó.

Phòng vệ:

- Bảo vệ POST login bằng CSRF token hoặc cơ chế chống login CSRF phù hợp.
- Ràng buộc luồng login với browser/session state được tạo từ trang login.
- Với OIDC, xác minh state và nonce theo protocol.
- Sau login, hiển thị rõ tài khoản đang đăng nhập, nhất là khi browser dùng chung.
- Tránh tự động đăng nhập bằng tài khoản được nhúng trong link không đáng tin.

SameSite cookie hữu ích nhưng không nên là lớp bảo vệ duy nhất, đặc biệt khi ứng dụng có luồng cross-site, subdomain hoặc callback liên kết.

## 10. XSS, cookie theft và bảo vệ browser

HttpOnly ngăn JavaScript đọc cookie trực tiếp nhưng không làm ứng dụng miễn nhiễm XSS. Script độc hại chạy cùng origin vẫn có thể gửi request bằng cookie của người dùng và đọc dữ liệu mà browser cho phép.

Biện pháp:

- Output encoding theo ngữ cảnh và dùng template an toàn.
- CSP với nonce/hash và chính sách chặt chẽ.
- Hạn chế third-party script trên trang login và trang nhạy cảm.
- Kiểm soát dependency, tag manager và script supply chain.
- Không render HTML không tin cậy trực tiếp.
- Dùng CSRF protection cho request thay đổi trạng thái.
- Bảo vệ thiết bị và browser extension theo chính sách endpoint.

### Không để credential rơi vào telemetry

Không ghi cookie, Authorization header, password, OTP, recovery code hoặc token vào console, analytics, trace, crash report và error monitoring. Cấu hình redaction tại frontend, gateway, backend và nhà cung cấp quan sát.

## 11. MFA và step-up trong web login

MFA thêm một hoặc nhiều yếu tố xác minh ngoài password. Sau khi password đúng, hệ thống có thể yêu cầu:

- TOTP từ authenticator.
- Push approval với context/number matching.
- Security key hoặc passkey.
- Certificate hoặc yếu tố được tổ chức quản lý.
- Recovery code trong luồng recovery đã được kiểm soát.

### Không tạo full session quá sớm

Nếu password đúng nhưng MFA chưa hoàn tất, hệ thống chỉ nên tạo trạng thái challenge giới hạn. Challenge đó không được truy cập tài nguyên bảo vệ hoặc thực hiện thao tác nhạy cảm. Sau khi MFA thành công, server tạo/rotate session đầy đủ và ghi authentication context.

### Step-up authentication

Người dùng đã đăng nhập có thể cần xác thực mạnh hơn cho:

- Thay đổi password, email hoặc số điện thoại khôi phục.
- Thêm/xóa passkey, authenticator hoặc API credential.
- Xem hoặc xuất dữ liệu nhạy cảm.
- Giao dịch giá trị cao hoặc hành động quản trị.
- Thay đổi quyền và mời người dùng mới.

Step-up phải ràng buộc với hành động và session hiện tại. Không chấp nhận một challenge MFA cũ hoặc không liên quan để phê duyệt hành động mới.

## 12. Passkey trong web login

Passkey dùng WebAuthn/FIDO để xác thực bằng public-key credential. Browser và authenticator tạo chữ ký cho challenge của server, gắn với RP ID/origin. Private key không được gửi lên website.

### Luồng khái quát

1. Browser yêu cầu server tạo challenge ngẫu nhiên.
2. Server trả challenge và WebAuthn request options phù hợp.
3. Browser gọi WebAuthn API và authenticator xác minh user presence/verification theo cấu hình.
4. Authenticator ký challenge và context.
5. Browser gửi assertion về server.
6. Server xác minh challenge, origin, RP ID hash, chữ ký, credential ID và trạng thái.
7. Server tạo/rotate session mới sau khi xác thực thành công.

### Lợi ích và giới hạn

- Passkey chống phishing tốt hơn password vì credential gắn với RP ID/origin.
- Giảm credential stuffing do không dùng password tái sử dụng.
- Có thể hỗ trợ đồng bộ passkey theo hệ sinh thái hoặc security key vật lý.
- Cần quản lý thiết bị mất, credential bị xóa, passkey đồng bộ và recovery.
- Passkey không ngăn malware chiếm thiết bị, session theft sau đăng nhập hoặc recovery abuse.

Không tự xây giao thức WebAuthn. Dùng thư viện và hướng dẫn nền tảng đã được kiểm chứng; kiểm tra đầy đủ challenge, origin, RP ID, user verification và credential ownership.

## 13. Đăng nhập liên kết bằng OpenID Connect

Web app có thể chuyển người dùng tới Identity Provider để đăng nhập thay vì tự thu thập password. OpenID Connect (OIDC) thêm lớp xác thực danh tính trên OAuth 2.0.

### Authorization Code Flow với PKCE

Với web app, một luồng thường dùng:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant R as Relying Party / Web App
    participant I as OpenID Provider
    B->>R: GET protected page
    R-->>B: Redirect tới OP + state + nonce + PKCE challenge
    B->>I: Authorization request
    I->>B: Đăng nhập / MFA / consent
    I-->>B: Redirect về callback + authorization code + state
    B->>R: Callback
    R->>R: Kiểm tra state
    R->>I: Đổi code + PKCE verifier qua back channel
    I-->>R: ID token + access token (theo request)
    R->>R: Verify ID token, nonce, issuer, audience, signature
    R-->>B: Tạo session cookie mới
~~~

Các kiểm tra quan trọng:

- Dùng Authorization Code Flow và PKCE theo profile phù hợp.
- Tạo và kiểm tra state để chống callback CSRF.
- Tạo và kiểm tra nonce trong ID token.
- Chỉ dùng redirect URI đã đăng ký chính xác.
- Xác minh chữ ký, issuer, audience, thời hạn và các claim bắt buộc.
- Đổi authorization code qua back channel và dùng PKCE verifier.
- Không dùng ID token thay access token để gọi API.
- Không chuyển token qua URL ngoài code/response mode được protocol cho phép.

### Sau callback

Web app tạo session nội bộ mới, không dùng nguyên authorization code hoặc ID token làm session ID. Liên kết subject theo issuer và subject ổn định, không tự động hợp nhất tài khoản chỉ dựa vào email.

## 14. Redirect sau đăng nhập và open redirect

Ứng dụng thường chuyển người dùng về trang họ định mở trước khi login. Nếu tham số return URL không được kiểm tra, attacker có thể dùng website thật để chuyển nạn nhân tới trang phishing.

Ví dụ nguy hiểm:

~~~text
/login?returnUrl=https://attacker.example/phishing
~~~

Biện pháp:

- Chỉ cho phép relative path nội bộ hoặc allowlist origin cụ thể.
- Chuẩn hóa URL trước khi kiểm tra.
- Từ chối scheme lạ, protocol-relative URL và host không được phép.
- Không tin return URL do client cung cấp chỉ vì nó được encode.
- Với OIDC, redirect URI phải khớp chính xác giá trị đã đăng ký.
- Sau login, có thể dùng route ID hoặc server-side state thay vì URL tùy ý.

## 15. Rate limit, brute force và account enumeration

Login endpoint thường bị credential stuffing, password spraying, brute force và bot abuse.

### Kiểm soát

- Rate limit theo nhiều tín hiệu: account identifier, IP/network, device/session, ASN hoặc risk signal.
- Dùng progressive delay và challenge bổ sung khi rủi ro tăng.
- Phát hiện password spraying trên nhiều tài khoản.
- Dùng breached-password detection và MFA.
- Không dựa duy nhất vào IP vì NAT/VPN có thể khiến nhiều người chung nguồn.
- Tránh khóa tài khoản vĩnh viễn chỉ vì nhiều lần nhập sai; attacker có thể dùng lockout gây denial of service.
- Giới hạn thử MFA/recovery riêng với login password.
- Theo dõi credential stuffing và tự động hóa bất thường.

### Chống account enumeration

Đối với tài khoản không tồn tại, password sai hoặc trạng thái bị hạn chế, phản hồi công khai nên tương đối nhất quán về nội dung và thời gian. Không tiết lộ email có đăng ký hay không qua thông báo khác biệt rõ.

Tuy nhiên, khi người dùng đã xác thực hoặc qua recovery proof phù hợp, có thể cung cấp thông tin chi tiết hơn để hỗ trợ. Không hy sinh hoàn toàn khả năng khôi phục chỉ để làm thông báo chung chung.

## 16. Logout và thu hồi session

Logout phải làm session không còn được chấp nhận ở server. Chỉ xóa cookie trên browser không đủ nếu session record vẫn active.

### Luồng logout

1. Browser gửi POST logout với CSRF protection.
2. Server xác định session hiện tại.
3. Server invalidate session record và token liên quan theo policy.
4. Server gửi Set-Cookie để xóa cookie với cùng name/path/domain attributes.
5. Browser chuyển về trang công khai hoặc login.
6. Server ghi audit event không chứa session secret.

Logout nên là thao tác POST hoặc cơ chế thay đổi trạng thái có bảo vệ; không dùng link GET mà một trang bên ngoài có thể kích hoạt tự động.

### Logout ở IdP và RP

Đăng xuất khỏi web app (Relying Party) không nhất thiết đăng xuất khỏi Identity Provider. Ngược lại, logout khỏi IdP không tự động kết thúc mọi session của các ứng dụng đã đăng nhập liên kết. Nếu cần single logout, phải triển khai theo protocol và kiểm tra trạng thái session ở từng RP.

## 17. Password reset và account recovery từ trang login

Link “Quên mật khẩu” là một phần của ranh giới xác thực. Attacker có thể lạm dụng recovery để chiếm tài khoản hoặc dò danh tính.

### Recovery an toàn

- Không tiết lộ tài khoản có tồn tại trong phản hồi công khai.
- Gửi hướng dẫn tới kênh đã xác minh trước đó.
- Recovery token ngẫu nhiên, một lần, thời hạn ngắn và lưu verifier nếu phù hợp.
- Token chỉ có quyền reset cụ thể, không tự tạo full session.
- Sau reset, vô hiệu hóa token đã dùng và xử lý session theo chính sách.
- Gửi notification về yêu cầu và thay đổi credential.
- Yêu cầu xác thực bổ sung khi đổi recovery method hoặc đăng ký MFA mới.
- Không gửi password, OTP, seed hoặc recovery code qua email.

Nếu người dùng vừa reset password, hệ thống có thể yêu cầu đăng nhập lại và hoàn tất MFA. Đừng tự động đăng nhập bằng một recovery link có bearer token dài hạn.

## 18. Bảo vệ trang login và cấu hình ứng dụng

Các lớp bảo vệ bổ sung:

- HTTPS toàn site và HSTS khi đã sẵn sàng triển khai đúng.
- Cookie Secure, HttpOnly, SameSite và scope phù hợp.
- CSP, output encoding và bảo vệ dependency.
- Cache-Control: no-store cho response nhạy cảm khi phù hợp.
- Không cho phép clickjacking trên trang đăng nhập bằng frame policy phù hợp.
- Giới hạn third-party script và analytics trên luồng credential.
- Không để debug mode hoặc stack trace lộ thông tin xác thực.
- Cấu hình reverse proxy để không log Authorization/Cookie.
- Đồng bộ thời gian để kiểm tra token/challenge đúng.
- Tách quyền của authentication service, session store và application backend.

Không dùng User-Agent, IP, geolocation hoặc browser fingerprint làm bằng chứng xác thực duy nhất. Chúng có thể là risk signal nhưng có thể sai, bị giả mạo hoặc xâm phạm quyền riêng tư.

## 19. Tình huống thực hành: thiết kế login cho cổng nhân viên

**Bối cảnh:** Công ty có web portal cho nhân viên. Người dùng đăng nhập bằng IdP doanh nghiệp; một số ứng dụng nội bộ vẫn hỗ trợ password login trong giai đoạn chuyển đổi. Portal cần bảo vệ thông tin nhân sự và thao tác quản trị.

### Thiết kế đề xuất

1. Ưu tiên OIDC Authorization Code Flow với PKCE và IdP doanh nghiệp.
2. Xác minh issuer, audience, signature, state, nonce và redirect URI.
3. Tạo session cookie host-only, Secure, HttpOnly, SameSite phù hợp.
4. Rotate session ID sau login và step-up.
5. Yêu cầu MFA chống phishing cho admin và hành động nhạy cảm.
6. Kiểm tra authorization theo role, tenant và resource ở backend.
7. Dùng idle/absolute timeout theo phân loại dữ liệu.
8. Có danh sách session và nút revoke thiết bị không nhận ra.
9. Logout invalidates RP session; xử lý IdP logout theo nhu cầu SSO.
10. Recovery gửi notification tới kênh đã xác minh và thu hồi session liên quan.

### Nếu IdP không khả dụng?

Không tự động bỏ qua xác thực hoặc dùng một tài khoản admin dự phòng chung. Dùng phương án break-glass được quản lý riêng, credential cá nhân, thời hạn ngắn, phê duyệt và audit. Nếu không có phương án hợp lệ, từ chối hành động bảo vệ cho tới khi hệ thống xác thực hoạt động.

### Nếu nhân viên mất thiết bị MFA?

Thực hiện recovery theo assurance đã định, kiểm tra kênh đã xác minh, thu hồi authenticator cũ và session đáng ngờ, đăng ký yếu tố mới rồi thông báo. Helpdesk không được reset MFA chỉ dựa trên thông tin dễ đoán hoặc lời gọi tự xưng.

## 20. Kiểm thử web login

Kiểm thử trong môi trường được phép với tài khoản và credential giả lập:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Login bằng credential hợp lệ | Session mới được tạo và principal đúng |
| Password sai hoặc account không tồn tại | Phản hồi công khai không dễ enumeration |
| Login POST thiếu/sai CSRF token | Bị từ chối |
| Login CSRF từ site khác | Không thể đăng nhập browser vào tài khoản attacker |
| Session ID trước login được tái sử dụng | Bị rotate và session cũ bị vô hiệu hóa |
| Cookie thiếu Secure/HttpOnly hoặc scope sai | Kiểm thử cấu hình phát hiện |
| Session hết idle timeout | Request bị yêu cầu đăng nhập lại |
| Session vượt absolute timeout | Bị hết hạn dù có request nền |
| Logout | Session server-side bị invalidate |
| Logout bằng GET hoặc CSRF | Không thể logout người dùng tùy ý qua request cross-site |
| Cookie bị xóa ở browser nhưng session còn | Server policy và session expiry vẫn kiểm soát trạng thái |
| Token hết hạn hoặc sai audience | Bị từ chối |
| OIDC state không khớp | Callback bị từ chối |
| OIDC nonce không khớp | ID token bị từ chối |
| Redirect URI không khớp | IdP từ chối hoặc callback không được xử lý |
| Return URL trỏ domain ngoài | Bị chặn |
| MFA chưa hoàn tất | Chỉ có challenge session giới hạn, không có full access |
| MFA push không do user khởi tạo | Không được chấp thuận; có đường báo cáo |
| Passkey assertion sai origin/challenge | Bị từ chối |
| Password reset token đã dùng/hết hạn | Không thể sử dụng lại |
| Recovery request lặp | Rate limit và thông báo được kiểm soát |
| Brute force/password spraying | Phát hiện, delay/challenge và bảo vệ tài khoản |
| XSS trên trang login | CSP/output encoding và kiểm soát script giảm tác động |
| Token/cookie xuất hiện trong log | Redaction ngăn lộ secret |
| IdP/session store không khả dụng | Hành động bảo vệ không fail-open |

### Chỉ số vận hành

- Tỷ lệ login thành công/thất bại theo reason code an toàn.
- Tỷ lệ MFA challenge và step-up.
- Số session bị revoke và thời gian thu hồi có hiệu lực.
- Tỷ lệ login bị rate limit hoặc phát hiện automation.
- Số lần phát hiện login CSRF, session fixation và open redirect.
- Thời gian từ báo cáo credential compromise đến revoke session.
- Tỷ lệ recovery hoàn tất và recovery bị báo cáo không nhận ra.
- Số secret bị phát hiện trong log, trace hoặc analytics.

## 21. Checklist thiết kế web login

- [ ] Toàn bộ trang và request chứa credential chạy qua HTTPS.
- [ ] Form dùng POST, CSRF protection và hỗ trợ password manager.
- [ ] Password được hash bằng password hashing scheme chuyên dụng.
- [ ] Phản hồi login hạn chế account enumeration và có recovery guidance.
- [ ] Rate limit chống brute force, stuffing và password spraying.
- [ ] MFA/passkey được tích hợp theo policy; challenge chưa hoàn tất không có full access.
- [ ] Session ID ngẫu nhiên và được rotate sau login/step-up.
- [ ] Cookie có Secure, HttpOnly, SameSite và scope phù hợp.
- [ ] Có idle timeout, absolute timeout và reauthentication cho hành động nhạy cảm.
- [ ] Logout invalidate session phía server và có CSRF protection.
- [ ] Có bảo vệ CSRF, login CSRF, XSS, clickjacking và open redirect.
- [ ] OIDC dùng flow phù hợp, PKCE, state, nonce và redirect URI chính xác.
- [ ] ID token không được dùng thay access token.
- [ ] Không lưu credential/token trong URL, localStorage hoặc log ngoài nhu cầu đã đánh giá.
- [ ] Recovery dùng kênh đã xác minh, token một lần và notification.
- [ ] Có khả năng xem/thu hồi session và thiết bị.
- [ ] Authorization được kiểm tra ở backend trên action/resource/tenant.
- [ ] Có audit và monitoring mà không ghi secret.
- [ ] Kiểm thử login, MFA, callback, timeout, logout, recovery và failure mode.

## Ghi nhớ

Web login là một quy trình xuyên suốt: thu thập credential an toàn, xác minh danh tính, hoàn tất MFA/passkey hoặc OIDC, tạo session mới, bảo vệ cookie và kiểm tra authorization ở mỗi request. Hãy rotate session ID sau login, dùng cookie Secure/HttpOnly/SameSite, bảo vệ CSRF và login CSRF, kiểm soát redirect, rate limit và không để secret vào URL hoặc log.

Logout và recovery phải vô hiệu hóa trạng thái phía server, gửi thông báo qua kênh đã xác minh và hỗ trợ thu hồi session/credential. Một màn hình login chỉ an toàn khi toàn bộ vòng đời từ browser đến backend, IdP và session store được thiết kế và kiểm thử như một ranh giới tin cậy.
