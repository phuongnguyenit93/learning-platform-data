# Login form — Thiết kế biểu mẫu đăng nhập web an toàn và dễ sử dụng

> **Chương:** Authentication trong web  
> **Chủ đề:** Login form  
> **Phạm vi:** Security Authentication Fundamentals — thiết kế biểu mẫu đăng nhập trên trình duyệt, xử lý credential an toàn, tích hợp session/MFA/passkey, chống CSRF và account enumeration, bảo vệ quyền riêng tư và khả năng tiếp cận.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả vai trò của login form trong toàn bộ authentication flow của ứng dụng web.
2. Thiết kế form HTML đúng ngữ nghĩa, tương thích password manager và browser autofill.
3. Gửi credential qua HTTPS bằng phương thức phù hợp, tránh đưa secret vào URL hoặc log.
4. Bảo vệ login form trước CSRF, XSS, clickjacking, brute force và account enumeration.
5. Xử lý lỗi đăng nhập, MFA và step-up mà không cấp session quá sớm.
6. Quản lý session cookie an toàn sau khi xác thực thành công.
7. Tích hợp passkey hoặc chuyển hướng tới identity provider mà không tự thu thập mật khẩu của IdP.
8. Bảo đảm form có label, keyboard navigation, thông báo lỗi và hỗ trợ công nghệ trợ năng.
9. Xây dựng bộ kiểm thử cho browser, server, session, security headers và các luồng lỗi.

## 1. Login form nằm ở đâu trong authentication flow?

**Login form** là giao diện web để người dùng bắt đầu một quy trình xác thực. Form thường thu thập username/email và password, hoặc khởi tạo một phương thức khác như passkey, security key, one-time code hay đăng nhập liên kết.

Form chỉ là một phần của authentication system. Việc người dùng nhập đúng dữ liệu vào giao diện chưa chứng minh danh tính. Server hoặc identity provider vẫn phải xác minh credential, áp dụng policy, hoàn tất MFA nếu cần và tạo session an toàn.

Một flow đơn giản:

`````````mermaid
flowchart TD
    A["Người dùng mở trang đăng nhập"] --> B["Browser tải form qua HTTPS"]
    B --> C["Người dùng nhập credential hoặc chọn passkey"]
    C --> D["Gửi request tới authentication endpoint"]
    D --> E{"Credential hợp lệ?"}
    E -- "Không" --> F["Trả lỗi an toàn và áp dụng risk controls"]
    F --> C
    E -- "Có" --> G{"Cần MFA/step-up?"}
    G -- "Có" --> H["Xác minh yếu tố bổ sung"]
    H --> I{"MFA thành công?"}
    I -- "Không" --> F
    I -- "Có" --> J["Tạo session mới"]
    G -- "Không" --> J
    J --> K["Đặt session cookie an toàn"]
    K --> L["Chuyển tới trang được phép"]
`````````

### Các thành phần tham gia

- **Browser:** hiển thị form, quản lý autofill và gửi request;
- **Web application:** render trang, xử lý CSRF và điều phối flow;
- **Authentication service:** xác minh password, passkey hoặc factor;
- **Identity provider:** có thể chịu trách nhiệm đăng nhập qua OIDC/SAML;
- **Session store:** lưu trạng thái session phía server;
- **Risk engine:** đánh giá hành vi, thiết bị và tín hiệu bất thường;
- **Audit pipeline:** ghi kết quả xác thực mà không ghi secret.

Form không được tự quyết định rằng người dùng đã xác thực chỉ vì JavaScript trả về thành công. Quyết định authentication phải được server xác minh và lưu bằng trạng thái có thẩm quyền.

## 2. Thiết kế HTML form đúng ngữ nghĩa

HTML form tiêu chuẩn thường tương thích tốt với browser, password manager, autofill, accessibility tool và các công cụ kiểm thử.

### Ví dụ form password cơ bản

`````````html
<form method="post" action="/login" autocomplete="on">
  <input type="hidden" name="csrf_token" value="SERVER_GENERATED_TOKEN">

  <div>
    <label for="username">Email hoặc tên đăng nhập</label>
    <input
      id="username"
      name="username"
      type="text"
      autocomplete="username"
      autocapitalize="none"
      spellcheck="false"
      required
    >
  </div>

  <div>
    <label for="password">Mật khẩu</label>
    <input
      id="password"
      name="password"
      type="password"
      autocomplete="current-password"
      required
    >
  </div>

  <button type="submit">Đăng nhập</button>
</form>
`````````

Đây là ví dụ cấu trúc. CSRF token phải được tạo và kiểm tra ở server, không dùng chuỗi minh họa trong production. Endpoint phải chạy qua HTTPS và xử lý request theo policy.

### Dùng đúng input type và autocomplete

| Trường | HTML gợi ý | Mục đích |
| --- | --- | --- |
| Username/email | type="text" hoặc type="email" theo định danh | Cho phép browser/password manager nhận diện username |
| Password đăng nhập | type="password" | Che ký tự trên giao diện |
| Password đăng ký/đổi | type="password" | Dùng autocomplete="new-password" |
| OTP | type="text" hoặc type="tel" theo UX | Dùng autocomplete="one-time-code" |
| Submit | button type="submit" | Kích hoạt submit form chuẩn |

Đối với username, autocomplete="username" giúp password manager ghép đúng credential. Với mật khẩu đăng nhập, dùng autocomplete="current-password"; khi tạo hoặc thay password, dùng autocomplete="new-password". OTP có thể dùng autocomplete="one-time-code" để hỗ trợ autofill trên nền tảng tương thích.

Không đặt autocomplete="off" một cách tùy tiện cho form đăng nhập. Chặn password manager thường làm người dùng chọn password yếu, tái sử dụng password hoặc lưu bí mật ở nơi kém an toàn hơn.

### Không chỉ dùng placeholder

Mỗi input cần label có thể truy cập bằng công nghệ trợ năng. Placeholder có thể cung cấp gợi ý ngắn nhưng không thay thế label vì nó biến mất khi người dùng nhập và thường có độ tương phản thấp.

### Không dùng JavaScript làm điều kiện duy nhất

Form nên submit được theo HTML chuẩn. JavaScript có thể tăng trải nghiệm như hiển thị trạng thái đang gửi hoặc xác thực định dạng nhẹ ở client, nhưng server vẫn phải kiểm tra mọi dữ liệu và quyết định kết quả.

## 3. Gửi credential an toàn

Credential là dữ liệu nhạy cảm. Cách form truyền dữ liệu và cách ứng dụng xử lý request có ảnh hưởng trực tiếp tới nguy cơ lộ password.

### Dùng HTTPS

- Chỉ phục vụ trang đăng nhập và endpoint xác thực qua HTTPS;
- Chuyển hướng HTTP sang HTTPS trước khi form được hiển thị;
- Bật HSTS theo kế hoạch triển khai domain;
- Dùng certificate hợp lệ và cấu hình TLS hiện đại;
- Không tải script, image hoặc stylesheet đăng nhập qua HTTP;
- Tránh mixed content.

HTTPS bảo vệ dữ liệu trên đường truyền giữa browser và endpoint, nhưng không bảo vệ password nếu browser, server, extension, script bên thứ ba hoặc log bị compromise.

### Dùng POST, không dùng GET

Password không được đưa vào query string hoặc URL. URL có thể xuất hiện trong browser history, proxy log, referrer, analytics và screenshot. Dùng POST body với content type phù hợp.

POST không tự mã hóa dữ liệu; TLS mới bảo vệ đường truyền. Server cũng không được log raw request body hoặc Authorization header.

### Không phản chiếu password

Khi trả lỗi, không echo username/password hoặc toàn bộ payload đã nhận. Không đưa credential vào:

- URL hoặc redirect parameter;
- HTML error page;
- JavaScript console;
- Application log/APM trace;
- Analytics event;
- Crash report;
- Support ticket tự động.

### Giới hạn request

Server nên giới hạn kích thước body, số field, độ dài username/password và thời gian xử lý. Giới hạn cần đủ rộng để chấp nhận passphrase dài hợp lệ và Unicode; không cắt ngắn password âm thầm.

## 4. CSRF và login CSRF

Cross-Site Request Forgery (CSRF) thường được nhắc tới với thao tác đã đăng nhập, nhưng login endpoint cũng có thể bị tấn công.

### Login CSRF là gì?

Attacker có thể khiến browser của nạn nhân gửi form đăng nhập bằng credential thuộc về attacker. Nếu đăng nhập thành công, browser nạn nhân bị gắn vào account của attacker. Nạn nhân có thể tải lên dữ liệu, lưu thông tin thanh toán hoặc tạo nội dung trong account mà attacker kiểm soát, rồi attacker truy cập lại dữ liệu đó.

### Kiểm soát

- Dùng synchronizer CSRF token hoặc cơ chế tương đương cho login transaction;
- Gắn token với session/pre-auth state và kiểm tra server-side;
- Kiểm tra Origin khi có và phù hợp;
- Dùng Fetch Metadata như tín hiệu bổ sung;
- Cấu hình SameSite cookie phù hợp;
- Không dựa duy nhất vào SameSite để chống mọi CSRF;
- Không cho phép login endpoint thay đổi account hoặc session theo tham số tùy ý.

### CSRF token

Token phải được tạo bằng nguồn ngẫu nhiên an toàn, gắn với transaction/session, có thời hạn và được kiểm tra ở server. Không dùng token cố định trong HTML tĩnh hoặc một giá trị chung cho mọi người dùng.

### SameSite

SameSite=Lax hoặc Strict có thể giảm một số request cookie cross-site. Tuy nhiên, lựa chọn phụ thuộc vào luồng SSO, redirect và yêu cầu sản phẩm. Cần kiểm tra hành vi browser thật và vẫn có CSRF protection phù hợp.

## 5. XSS, clickjacking và bảo vệ trang đăng nhập

Nếu attacker chạy được script trong origin của ứng dụng, họ có thể đọc dữ liệu người dùng nhập, thao tác DOM, gửi request hoặc đánh cắp session tùy cấu hình. Trang đăng nhập cần được bảo vệ như một trang nhạy cảm.

### Chống XSS

- Encode output theo ngữ cảnh HTML/attribute/JavaScript;
- Tránh đưa dữ liệu không tin cậy vào innerHTML;
- Dùng template engine có auto-escaping;
- Sanitize nội dung HTML nếu sản phẩm thực sự cho phép HTML;
- Dùng Content Security Policy phù hợp;
- Hạn chế script bên thứ ba trên trang đăng nhập;
- Tránh inline script hoặc giới hạn bằng nonce/hash CSP;
- Cập nhật dependency và kiểm soát supply chain.

### Content Security Policy

Một policy có thể giới hạn script, style, form destination và frame ancestor. Cấu hình phải dựa trên ứng dụng thật; không sao chép một policy mẫu rồi thêm unsafe-inline/unsafe-eval cho tới khi mọi thứ chạy.

### Clickjacking

Attacker có thể nhúng trang đăng nhập vào frame trong trang giả để dụ người dùng click. Dùng CSP frame-ancestors và/hoặc X-Frame-Options phù hợp với yêu cầu embedding. Nếu ứng dụng cần được nhúng bởi một domain tin cậy, chỉ allowlist domain cụ thể.

### Giảm script trên trang login

Không tải analytics, chat widget, advertising script hoặc tag manager không cần thiết trên trang thu thập password. Script bên thứ ba có thể đọc input hoặc can thiệp form nếu chạy cùng quyền trong origin.

## 6. Xác minh password ở server

Browser không phải nơi xác minh password cuối cùng. Client-side check chỉ giúp trải nghiệm; attacker có thể bỏ qua JavaScript và gửi request trực tiếp.

### Luồng server-side

1. Parse request và xác minh CSRF;
2. Chuẩn hóa username theo policy định danh;
3. Tra cứu account bằng cơ chế chống enumeration;
4. Lấy password hash và metadata từ credential store;
5. Dùng password hashing library chuẩn để verify;
6. Đánh giá rate limit, risk và trạng thái account;
7. Nếu cần, yêu cầu MFA/step-up;
8. Chỉ sau khi hoàn tất toàn bộ bước, tạo session authenticated;
9. Ghi audit outcome mà không lưu password.

### Password storage

Không lưu password plaintext hoặc dùng SHA-256 đơn lẻ. Dùng password hashing function chuyên dụng như Argon2id hoặc lựa chọn phù hợp theo nền tảng/chính sách; salt riêng cho từng password và tham số cost được benchmark.

Pepper có thể là lớp bổ sung nếu được lưu tách khỏi database trong secret manager/KMS/HSM. Không tự triển khai thuật toán mật mã.

### Không tin dữ liệu từ client

Các field như user_id, role, is_admin, authenticated=true hoặc account_status gửi từ browser không được dùng để quyết định danh tính/quyền. Server phải xác định principal từ credential đã xác minh và authorization policy.

## 7. Chống brute force, spraying và credential stuffing

Login form là mục tiêu tự nhiên của bot và automation. Bảo vệ cần nhiều chiều để tránh vừa bỏ lọt tấn công phân tán vừa khóa nhầm người dùng hợp lệ.

### Rate limiting nhiều chiều

- Theo account/subject;
- Theo IP hoặc network;
- Theo device/session signal;
- Theo tenant/application;
- Theo toàn bộ authentication service;
- Theo hành vi và risk.

Không dùng một ngưỡng IP duy nhất vì nhiều người có thể dùng chung NAT, VPN hoặc mạng di động. Không khóa account vô thời hạn chỉ vì người ngoài gửi password sai.

### Progressive delay và adaptive challenge

Có thể tăng delay, yêu cầu challenge bổ sung hoặc step-up khi có pattern đáng ngờ. CAPTCHA chỉ là lớp bổ sung; cần phương án accessibility và không dùng nó thay MFA hoặc rate limiting.

### Thông báo lỗi không tiết lộ account

Tránh trả message khác nhau cho username không tồn tại, password sai và account bị hạn chế nếu điều đó cho phép enumeration. Public response có thể chung; audit nội bộ giữ reason code chính xác.

### Breached-password screening

Khi tạo hoặc đổi password, kiểm tra password có phổ biến hoặc đã xuất hiện trong breach corpus hay không. Bảo vệ password candidate trong quá trình tra cứu; không gửi plaintext tới bên thứ ba hoặc ghi vào log.

## 8. Thông báo lỗi và trạng thái form

Form cần cho người dùng biết phải làm gì tiếp theo mà không tiết lộ thông tin giúp attacker.

### Message cho credential sai

Một thông báo chung có thể là:

`````````text
Không thể đăng nhập bằng thông tin đã cung cấp. Hãy kiểm tra lại và thử lần nữa.
`````````

Không nói rõ username có tồn tại hay account đang bị khóa nếu caller chưa được xác thực và việc tiết lộ có thể tạo rủi ro.

### Lỗi có thể khắc phục

Có thể cung cấp hướng dẫn phù hợp:

- Kết nối tạm thời không khả dụng: thử lại sau;
- Quá nhiều lần thử: chờ theo hướng dẫn, không tiếp tục gửi tự động;
- MFA cần thiết: hoàn tất bước xác minh tiếp theo;
- Password hết hạn theo policy hợp lệ: chuyển sang flow đổi password an toàn;
- Account cần hỗ trợ: cung cấp kênh liên hệ đã được công bố.

### Accessibility cho lỗi

- Đặt lỗi gần field liên quan;
- Dùng aria-describedby để liên kết input và mô tả lỗi;
- Dùng aria-invalid khi field có lỗi;
- Có summary lỗi dễ tìm khi submit thất bại;
- Đưa focus tới vùng lỗi hoặc field đầu tiên cần sửa theo thiết kế;
- Không chỉ dùng màu đỏ để báo lỗi;
- Không xóa dữ liệu username nếu không cần, nhưng luôn cân nhắc xóa password sau failure;
- Không tự động xóa nội dung người dùng đang nhập khi một request mạng thất bại.

### Tránh lỗi quá chung gây khó sử dụng

Không tiết lộ account state không có nghĩa là không thể giúp người dùng. Có thể đưa liên kết “Quên mật khẩu?”, hướng dẫn kiểm tra bàn phím, caps lock hoặc lựa chọn phương thức khác mà không xác nhận account có tồn tại.

## 9. MFA và step-up sau password

Nếu account yêu cầu MFA, password đúng mới chỉ hoàn thành một bước. Không tạo session có đầy đủ quyền trước khi yếu tố bổ sung được xác minh.

### Pre-authentication state

Sau khi password đúng, server có thể tạo một trạng thái pre-authentication ngắn hạn:

- Gắn với đúng account và login transaction;
- Có expiry ngắn;
- Chỉ cho phép gọi endpoint MFA;
- Không được dùng như session authenticated;
- Có rate limit và attempt limit;
- Được consume khi MFA thành công hoặc hết hạn.

### Flow minh họa

`````````mermaid
sequenceDiagram
    participant B as Browser
    participant W as Web app
    participant A as Auth service
    B->>W: POST username/password + CSRF
    W->>A: Verify password
    A-->>W: Password valid, MFA required
    W-->>B: Pre-auth state + MFA challenge
    B->>W: Submit OTP/passkey approval
    W->>A: Verify second factor
    A-->>W: MFA valid
    W->>W: Rotate session ID, create authenticated session
    W-->>B: Set-Cookie session
`````````

### MFA controls

- Không log OTP hoặc push approval secret;
- Giới hạn số lần thử;
- Gắn challenge với transaction;
- Không cho phép approve một challenge không do người dùng khởi tạo;
- Có context như ứng dụng, vị trí hoặc hành động khi phù hợp;
- Chống MFA fatigue bằng giới hạn prompt và cảnh báo;
- Ưu tiên phương thức phishing-resistant cho account nhạy cảm.

## 10. Passkey và passwordless login

Login form có thể hỗ trợ passkey song song với password hoặc trở thành passwordless.

### Passkey flow

1. Browser yêu cầu server tạo WebAuthn challenge;
2. Server lưu challenge gắn với login transaction;
3. Browser gọi WebAuthn API;
4. Authenticator thực hiện user verification và ký assertion;
5. Browser gửi assertion về server;
6. Server xác minh challenge, origin, RP ID, credential, chữ ký và trạng thái transaction;
7. Server consume challenge và tạo session mới.

### Không tự xác minh ở browser

Browser chỉ chuyển kết quả WebAuthn. Server phải kiểm tra chữ ký và toàn bộ điều kiện protocol. Không tin cờ JavaScript như passkeySuccess=true.

### UX

- Cho phép password manager/passkey autofill;
- Có thể cung cấp nút “Đăng nhập bằng passkey”;
- Dùng conditional mediation/autofill khi nền tảng hỗ trợ;
- Có hướng dẫn khi người dùng không có passkey trên thiết bị;
- Recovery/fallback phải có assurance phù hợp, không làm yếu toàn bộ hệ thống.

### Password fallback

Nếu vẫn giữ password fallback, nó phải có rate limit, password storage, MFA và recovery policy tương xứng. Một fallback yếu có thể trở thành con đường bỏ qua passkey.

## 11. Đăng nhập liên kết qua OIDC/SAML

Khi ứng dụng dùng identity provider bên ngoài hoặc IdP doanh nghiệp, browser nên được chuyển hướng tới endpoint đăng nhập của IdP. Ứng dụng không nên yêu cầu người dùng nhập password IdP vào form riêng của mình.

### OpenID Connect

Với Authorization Code Flow cho web application:

- Dùng state để liên kết callback với browser transaction;
- Dùng nonce để liên kết ID token với authentication request;
- Dùng PKCE để bảo vệ authorization code;
- Kiểm tra issuer, audience, signature, expiry và nonce;
- Chỉ redirect tới URI đã đăng ký;
- Không chấp nhận callback lặp hoặc state không khớp.

### SAML

SP cần kiểm tra chữ ký, issuer, audience, recipient/destination, điều kiện thời gian, InResponseTo khi phù hợp và assertion ID replay. Không tạo session chỉ vì browser gửi một XML assertion chưa được xác minh.

### Account linking

Không tự động liên kết account chỉ dựa vào email claim nếu trust policy chưa cho phép. Cần kiểm tra issuer/subject ổn định, verified email semantics và yêu cầu reauthentication/consent khi liên kết danh tính nhạy cảm.

## 12. Session cookie sau đăng nhập

Sau khi hoàn tất authentication và MFA, server tạo session mới. Cookie là bearer credential nên cần được bảo vệ cẩn thận.

### Session fixation

Attacker có thể cố khiến nạn nhân dùng session ID mà attacker đã biết. Sau khi đăng nhập thành công, server phải rotate/regenerate session ID và không nâng quyền cho session ID cũ.

### Cookie attributes

Ví dụ:

`````````http
Set-Cookie: __Host-session=OPAQUE_SESSION_ID; Path=/; Secure; HttpOnly; SameSite=Lax
`````````

Đây là ví dụ minh họa. Prefix __Host- yêu cầu Secure, Path=/ và không có Domain attribute theo quy tắc browser; cần xác minh tương thích với domain/deployment thực tế.

| Attribute | Mục đích |
| --- | --- |
| Secure | Chỉ gửi cookie qua HTTPS |
| HttpOnly | JavaScript không đọc trực tiếp cookie |
| SameSite | Giảm một số request cookie cross-site |
| Path | Giới hạn path gửi cookie |
| Domain | Không khai báo nếu không cần chia sẻ subdomain |
| Max-Age/Expires | Xác định thời hạn cookie |

Cookie nên chứa session identifier ngẫu nhiên, không chứa password hoặc toàn bộ profile/quyền nhạy cảm. Session state và authorization phải được kiểm tra phía server.

### Session lifecycle

- Idle timeout và absolute timeout;
- Logout thu hồi session phía server;
- Password change/recovery có thể revoke session khác;
- Step-up có thể rotate session ID;
- Theo dõi session bất thường;
- Không lưu session token trong URL hoặc log;
- Dùng CSRF protection cho thao tác thay đổi dữ liệu.

## 13. Remember me và thiết bị tin cậy

Remember me giúp người dùng duy trì trạng thái đăng nhập lâu hơn, nhưng làm tăng giá trị của credential bị đánh cắp.

### Không lưu password

Không lưu password vào localStorage, cookie hoặc browser database để tự điền lại. Dùng session/persistent token được thiết kế cho mục đích này và quản lý vòng đời ở server.

### Persistent session

- Token ngẫu nhiên, đủ entropy;
- Lưu verifier/hash phía server nếu phù hợp;
- Rotation khi sử dụng;
- Reuse detection;
- Có thể revoke từng thiết bị;
- Giới hạn thời gian và phạm vi;
- Bảo vệ cookie bằng Secure/HttpOnly/SameSite;
- Cho người dùng xem và thu hồi thiết bị/session.

Không đánh dấu một thiết bị là trusted chỉ vì nó từng đăng nhập. Device signal là một yếu tố risk, không tự thay thế authentication.

## 14. Redirect sau đăng nhập

Ứng dụng thường chuyển người dùng tới trang họ muốn truy cập trước khi login. Nếu tham số return URL không được kiểm tra, attacker có thể lợi dụng open redirect để lừa người dùng hoặc đưa authorization response tới nơi không tin cậy.

### Kiểm soát

- Ưu tiên lưu relative path đã được chuẩn hóa trong server-side transaction;
- Nếu cho phép absolute URL, dùng allowlist origin rõ ràng;
- Không chấp nhận javascript:, data: hoặc scheme không tin cậy;
- Kiểm tra host, port, path và encoding sau canonicalization;
- Không lấy redirect target trực tiếp từ hidden field mà không xác minh;
- Giữ state/correlation để ràng buộc login transaction.

### Ví dụ

Chấp nhận:

`````````text
/account
/orders?filter=open
`````````

Từ chối:

`````````text
https://attacker.example/collect
//attacker.example/path
javascript:alert(1)
`````````

Ví dụ chỉ minh họa. Quy tắc URL cần dựa trên router và deployment; canonicalization không đúng có thể làm allowlist bị bypass.

## 15. Accessibility và trải nghiệm người dùng

Một login form an toàn cần dùng được với nhiều thiết bị, phương thức nhập và công nghệ trợ năng. UX kém có thể khiến người dùng tạo password yếu, bỏ MFA hoặc tìm cách né kiểm soát.

### Checklist UX

- Label rõ cho mọi field;
- Có thể thao tác hoàn toàn bằng bàn phím;
- Focus indicator nhìn thấy được;
- Thứ tự tab hợp lý;
- Error summary và inline error có thể được screen reader đọc;
- Không chỉ dựa vào màu sắc;
- Hỗ trợ zoom và màn hình nhỏ;
- Password manager và autofill hoạt động;
- Cho phép paste password;
- Có nút show/hide password với accessible name và trạng thái rõ;
- Không tự động submit khi người dùng chưa chủ động xác nhận;
- Không yêu cầu câu đố hoặc thao tác không cần thiết;
- Cung cấp phương thức thay thế nếu CAPTCHA hoặc biometric không phù hợp.

### Show/hide password

Nút hiện/ẩn password có thể cải thiện trải nghiệm. Nó không được thay đổi giá trị input, gửi password tới server hoặc ghi vào log. Nút phải có type=button để không vô tình submit form và có trạng thái accessible.

### Không ép password policy gây hại

Cho phép passphrase dài, password manager, paste và Unicode theo policy. Tránh ép thay ký tự máy móc hoặc đổi password định kỳ không có lý do.

## 16. Privacy và data minimization

Login page thường xử lý username, password, IP, device signal, MFA context và đôi khi thông tin cá nhân khác. Chỉ thu thập dữ liệu cần thiết cho authentication, abuse prevention và audit.

### Nguyên tắc

- Không log password/OTP/recovery code;
- Giới hạn dữ liệu fingerprint và retention;
- Không gửi input field tới analytics;
- Không dùng session replay/heatmap script trên vùng nhập credential;
- Không để error page chứa PII không cần thiết;
- Giới hạn quyền truy cập audit;
- Công bố mục đích sử dụng device/risk signal;
- Bảo vệ backup, trace và support bundle.

### Third-party script

Mỗi script trên login origin có thể có khả năng quan sát DOM hoặc input. Rà soát dependency, pin/version policy, CSP, SRI khi phù hợp và chỉ tải thành phần cần thiết.

## 17. Logging và giám sát login form

Audit cần đủ để phát hiện tấn công và điều tra nhưng không được ghi credential thô.

### Event gợi ý

| Event | Trường an toàn gợi ý |
| --- | --- |
| auth.login.page_viewed | Request ID, route, coarse client context |
| auth.login.started | Interaction ID, subject reference nếu có, client |
| auth.login.failed | Reason code nội bộ, subject reference, source/device reference |
| auth.login.succeeded | Subject, method, session reference |
| auth.mfa.required | Transaction reference, factor type |
| auth.mfa.failed/succeeded | Factor reference, outcome, transaction |
| auth.passkey.started/completed | Credential reference, challenge transaction, outcome |
| auth.session.created | Session reference, subject, method |
| auth.session.revoked | Session reference, reason, actor |
| auth.rate_limited | Dimension, policy version, result |

Không ghi password, OTP, TOTP seed, private key, raw assertion, raw access token, refresh token, cookie hoặc CSRF token.

### Chỉ số cần theo dõi

- Login success/failure rate;
- Failure theo route, client, network và account cohort;
- MFA challenge completion/failure;
- Passkey adoption và fallback rate;
- Rate-limit activation;
- Login success sau chuỗi failure;
- Session creation/revocation latency;
- Error response distribution;
- Tỷ lệ request thiếu CSRF hoặc origin bất thường;
- Browser compatibility/accessibility issue.

Không dùng metrics để tự động khóa account hàng loạt nếu chưa phân tích NAT, VPN, mạng di động và baseline.

## 18. Threat model: lỗi phổ biến của login form

| Rủi ro | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| Credential interception | Form gửi qua HTTP hoặc mixed content | HTTPS, HSTS, không tải tài nguyên HTTP |
| Password in URL | Dùng GET hoặc redirect query | POST body, redaction |
| CSRF/login CSRF | Attacker ép browser submit login | CSRF token, Origin/Fetch Metadata, SameSite |
| XSS | Script độc hại đọc password hoặc session | Output encoding, CSP, dependency control |
| Clickjacking | Form bị nhúng trong trang giả | CSP frame-ancestors/X-Frame-Options |
| Brute force | Thử nhiều password | Multi-dimensional rate limit, progressive delay |
| Password spraying | Thử ít password trên nhiều account | Detection theo subject/source/campaign |
| Credential stuffing | Dùng cặp password bị lộ | Breach screening, MFA/passkey, detection |
| Account enumeration | Response tiết lộ account tồn tại | Generic public response và timing review |
| Session fixation | Giữ session ID trước login | Rotate session ID sau authentication |
| Premature session | Tạo full session trước MFA | Pre-auth state giới hạn và short-lived |
| Open redirect | return URL trỏ ra domain attacker | Relative path/allowlist và canonicalization |
| Token theft | Token lưu trong URL/localStorage/log | Secure cookie, short lifetime, rotation/revocation |
| MFA fatigue | Prompt lặp để dụ approve | Rate limit, number matching/context, alert |
| Weak fallback | Password/recovery yếu hơn passkey | Assurance nhất quán trên mọi entry path |
| Third-party script | Script bên ngoài đọc DOM/input | Minimize scripts, CSP, integrity/review |
| Cache leakage | Trang/response login bị cache sai | Cache-Control phù hợp, no-store cho nội dung nhạy cảm |
| Information leakage | Error trả stack trace hoặc account state | Response sanitization và request ID |

## 19. Tình huống thiết kế: login form cho cổng nhân viên

Một cổng nhân viên dùng username/password, TOTP và session cookie. Trang đăng nhập có analytics, nút nhớ mật khẩu, redirect parameter và thông báo lỗi riêng cho account không tồn tại.

### Thiết kế ban đầu có vấn đề

1. Form dùng GET nên password xuất hiện trong URL;
2. Browser bị chặn autofill vì autocomplete=off;
3. Endpoint không kiểm tra CSRF;
4. Error message tiết lộ account tồn tại;
5. Rate limit chỉ theo IP;
6. Session authenticated được tạo ngay sau password trước khi TOTP hoàn tất;
7. Session ID không đổi sau login;
8. returnUrl được redirect trực tiếp;
9. Analytics script chạy trên trang nhập password;
10. Cookie thiếu Secure và HttpOnly.

### Thiết kế lại

1. Form POST tới endpoint HTTPS, có CSRF token gắn với pre-auth transaction.
2. Dùng autocomplete=username/current-password và label đúng ngữ nghĩa.
3. Không tải analytics/session replay script trên vùng credential.
4. Response lỗi công khai nhất quán, audit nội bộ giữ reason code.
5. Rate limit theo account, source, device, tenant và service; có progressive delay.
6. Password được verify bằng password hash chuyên dụng phía server.
7. Sau password hợp lệ, tạo pre-auth state ngắn hạn chỉ cho phép TOTP.
8. Sau TOTP thành công, rotate session ID và tạo authenticated session.
9. Đặt cookie Secure, HttpOnly, SameSite phù hợp và host-only.
10. Validate return path bằng relative path hoặc allowlist.
11. Áp dụng CSP, frame-ancestors và cache policy phù hợp.
12. Ghi audit không có password/OTP/session cookie.

### Kết quả mong đợi

- Credential không xuất hiện trong URL hoặc log;
- Password manager/autofill hoạt động;
- Attacker khó dùng login CSRF hoặc enumeration;
- Không có session đầy đủ trước MFA;
- Session cũ không được nâng quyền;
- Redirect không thể đưa người dùng tới origin tùy ý;
- Có thể điều tra login failure/success bằng request ID và audit reference.

## 20. Bộ kiểm thử chấp nhận

| Trường hợp | Cách thử | Kết quả kỳ vọng |
| --- | --- | --- |
| HTTPS only | Mở login qua HTTP | Chuyển sang HTTPS trước khi gửi credential |
| HSTS | Kiểm tra response security header | HSTS đúng policy |
| POST method | Submit form | Password không xuất hiện trong URL |
| Autocomplete | Kiểm tra username/password fields | Dùng username/current-password đúng |
| Password manager | Thử autofill/paste | Hoạt động bình thường |
| Label | Dùng screen reader | Field có accessible name |
| Keyboard | Chỉ dùng bàn phím | Có thể hoàn tất flow và nhìn thấy focus |
| CSRF missing | Submit không có token | Server từ chối |
| CSRF replay | Dùng token transaction đã hết hạn/đã consume | Server từ chối theo policy |
| Login CSRF | Ép browser submit account attacker | Không tạo session gắn nạn nhân vào account attacker |
| Origin mismatch | Gửi request từ origin không được phép | Bị từ chối/đánh giá theo policy |
| XSS payload | Đưa payload vào username/error context | Không thực thi script |
| Clickjacking | Nhúng login trong frame không tin cậy | Bị chặn |
| Mixed content | Kiểm tra tài nguyên login | Không có tài nguyên HTTP |
| Account enumeration | So sánh account có/không tồn tại | Không có khác biệt công khai dễ khai thác |
| Brute force | Thử nhiều password | Rate limit/progressive delay hoạt động |
| Distributed attempts | Phân tán request qua nguồn | Detection đa chiều |
| Password hash | Kiểm tra credential store | Không có plaintext hoặc fast hash đơn lẻ |
| Password logging | Kiểm tra log/APM | Không có password candidate |
| MFA required | Nhập password đúng nhưng bỏ MFA | Không có authenticated session |
| MFA replay | Dùng lại OTP/challenge | Bị từ chối theo one-time policy |
| Session fixation | Giữ pre-login session ID rồi login | Session ID mới được cấp |
| Cookie flags | Kiểm tra Set-Cookie | Secure, HttpOnly, SameSite đúng policy |
| Logout | Logout rồi dùng lại cookie | Session bị revoke |
| Password reset | Reset password | Session/token bị xử lý theo policy |
| Passkey challenge | Gửi assertion hợp lệ | Server verify challenge/origin/RP ID |
| Passkey replay | Gửi lại assertion cũ | Bị từ chối |
| OIDC state mismatch | Gửi callback state khác | Client từ chối |
| OIDC nonce mismatch | ID token nonce không khớp | Client từ chối |
| Open redirect | Gửi returnUrl tới domain ngoài | Bị từ chối hoặc thay bằng safe destination |
| Third-party script | Kiểm tra login page requests | Không tải script không cần thiết |
| Cache | Kiểm tra response nhạy cảm | Cache-Control phù hợp |
| Error accessibility | Submit lỗi và dùng screen reader | Lỗi được thông báo rõ |
| Unicode/password length | Dùng passphrase dài/Unicode hợp lệ | Không cắt ngắn hoặc normalize không nhất quán |
| Rate-limit recovery | Thử endpoint quên mật khẩu | Cũng có rate limit và anti-enumeration |
| Audit redaction | Kiểm tra event | Không có OTP, password, cookie hoặc token |

Kiểm thử cần chạy trên browser thật, API, session store, identity provider và audit pipeline. Một unit test cho HTML không chứng minh CSRF, cookie, redirect hoặc session lifecycle an toàn trong production.

## 21. Checklist triển khai Login form

- **Transport:** Login page và endpoint chỉ dùng HTTPS?
- **HTML:** Form dùng POST, input type và autocomplete phù hợp?
- **Accessibility:** Có label, keyboard flow, focus, error summary và screen reader support?
- **Password manager:** Cho phép autofill và paste?
- **Credential handling:** Password không xuất hiện trong URL, log, analytics hoặc error body?
- **CSRF:** Login transaction có CSRF protection và Origin/Fetch Metadata policy phù hợp?
- **XSS:** Có output encoding, CSP và kiểm soát third-party script?
- **Clickjacking:** Có frame-ancestors/X-Frame-Options?
- **Abuse protection:** Rate limit đa chiều, progressive delay và detection?
- **Enumeration:** Response công khai không tiết lộ account state?
- **Password storage:** Password hash chuyên dụng, salt và parameters phù hợp?
- **MFA:** Không tạo full session trước khi factor bắt buộc hoàn tất?
- **Passkey:** Challenge được tạo/xác minh/consume ở server?
- **Federation:** OIDC/SAML được xử lý theo protocol, không thu thập password IdP?
- **Session:** Session ID rotate, cookie Secure/HttpOnly/SameSite và revocation?
- **Redirect:** return path được kiểm tra, không có open redirect?
- **Remember me:** Không lưu password; persistent token có rotation/revocation?
- **Privacy:** Không thu thập/log quá mức; login page giảm script bên thứ ba?
- **Cache:** Response nhạy cảm không bị cache sai?
- **Audit:** Event có request ID/reason code nhưng không có secret?
- **Testing:** Đã thử CSRF, XSS, brute force, MFA, session fixation, redirect và accessibility?

### Câu hỏi tự kiểm tra

1. Vì sao login form chỉ là giao diện bắt đầu authentication, không phải bằng chứng người dùng đã xác thực?
2. Tại sao password field nên dùng autocomplete=current-password?
3. Vì sao POST không đủ nếu trang không dùng HTTPS?
4. Login CSRF có thể khiến nạn nhân bị gắn vào account của attacker như thế nào?
5. Vì sao không nên tạo authenticated session trước khi MFA hoàn tất?
6. Session fixation được ngăn bằng cách nào?
7. Vì sao error message cần tránh account enumeration?
8. Tại sao không nên tải analytics hoặc session replay script trên trang nhập password?
9. OIDC state, nonce và PKCE bảo vệ những phần nào của login flow?
10. Vì sao password fallback yếu có thể làm giảm giá trị bảo vệ của passkey?
11. SameSite cookie có thay thế hoàn toàn CSRF token không?
12. Những kiểm thử nào cần chạy trên browser thật thay vì chỉ unit test HTML?

## Kết luận

**Login form an toàn kết hợp HTML đúng ngữ nghĩa, truyền credential qua HTTPS, xác minh hoàn toàn ở server và quản lý session sau khi mọi bước authentication hoàn tất.** Form cần hỗ trợ password manager, autofill và accessibility; bảo vệ CSRF/login CSRF, XSS, clickjacking, brute force và account enumeration; không đưa secret vào URL, log hoặc analytics. Khi có MFA, passkey hoặc federation, mỗi transaction phải được ràng buộc và xác minh theo giao thức trước khi cấp session. Session cookie cần được rotate và đặt thuộc tính phù hợp; redirect phải được kiểm tra; error response và audit phải cung cấp đủ thông tin vận hành mà không làm lộ credential hoặc trạng thái tài khoản. Trải nghiệm dễ sử dụng và kiểm soát bảo mật phải được thiết kế cùng nhau để người dùng có thể đăng nhập an toàn trên browser và thiết bị khác nhau.
