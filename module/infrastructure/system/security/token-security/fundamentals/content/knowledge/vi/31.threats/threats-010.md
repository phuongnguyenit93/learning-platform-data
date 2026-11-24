# Phishing redirect

Người dùng nhận một liên kết “Đăng nhập SSO để xác nhận phiên”. Liên kết bắt đầu bằng tên miền ứng dụng quen thuộc nhưng chuyển tiếp qua một endpoint có tham số `next`, rồi tới một trang đăng nhập giả. Ở một kịch bản khác, kẻ tấn công tìm cách khiến **Authorization Server (AS)** chuyển **authorization code** đến một callback không thuộc OAuth client. Cả hai cùng khai thác **sự tin tưởng vào redirect**, nhưng điều kiện tấn công và biện pháp phòng vệ khác nhau.

Trong **OAuth 2.0**, browser redirect là chức năng hợp lệ: AS xác thực người dùng, xử lý consent và đưa authorization response về **redirect URI đã đăng ký cho client**. Trong **OpenID Connect (OIDC)**, client còn xác minh ID token trước khi thiết lập phiên đăng nhập. Nếu một redirect không ràng buộc đúng **client identity, origin, callback URI, transaction state và issuer**, kẻ tấn công có thể tạo phishing link, đưa user sang trang giả, làm lộ code, tráo phiên hoặc lừa user cấp scopes cho ứng dụng khác. **Đọc được authorization code không tự có access token** nếu AS ràng buộc PKCE/client/redirect URI đúng; tuy vậy đây vẫn là rủi ro cần xử lý.

Bài thuộc chương **Threats** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**: mô hình tin cậy và vòng đời JWT/opaque token, access/refresh token, OAuth 2.0/OIDC; các bước phát hành, kiểm claims, scope, audience, lưu trữ, thu hồi và chống token bị đánh cắp hoặc phát lại. **Phạm vi bài:** nhận diện và phòng chống *phishing redirect* và các lỗ hổng redirect liên quan, không tạo trang giả để chiếm tài khoản.

> **Quy tắc:** Một URL có chứa tên miền quen thuộc **không chứng minh điểm đến cuối an toàn**. Kiểm chính xác redirect URI ở AS, xử lý callback theo phiên và giao dịch một lần, không dùng `next`/`returnUrl` tùy ý; kết hợp **PKCE, `state`, `nonce` và issuer validation** theo đúng vai trò của từng cơ chế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Diễn giải redirect trong Authorization Code Flow + PKCE, vị trí của AS, client/BFF, browser và Resource Server.
2. Phân biệt **phishing login**, **consent phishing**, **redirect URI manipulation**, **open redirector**, **authorization response leakage**, **login CSRF** và **AS mix-up**.
3. Nêu được rủi ro của các tham số `redirect_uri`, `next`, `returnUrl`, `continue` và deep links.
4. Thiết kế **exact matching redirect URI** với ràng buộc client registration; tránh prefix/suffix/substring validation.
5. Giải thích vì sao PKCE S256, client authentication, `state`, OIDC `nonce`, issuer binding và HTTPS **bổ sung nhau**.
6. Bảo vệ callback, code exchange và browser navigation; tránh ghi code/token vào history, `Referer`, logs và analytics.
7. Đánh giá các kênh BFF, SPA, native apps, verified app links, loopback redirects và reverse proxy.
8. Phân biệt authorization code, access token, ID token, refresh token và các dạng JWT/opaque; hiểu audience/scope, revocation, DPoP/mTLS.
9. Xem ví dụ Java/Spring Security về return URL allowlist và validation bằng server-side OAuth transaction.
10. Xây dựng test matrix, signals phát hiện và incident response cho phishing redirect.

## 2. Redirect hợp lệ trong OAuth 2.0/OIDC

### 2.1. Authorization Code Flow + PKCE

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User Browser
    participant C as OAuth Client or BFF
    participant AS as Trusted Authorization Server
    participant RS as Resource Server
    U->>C: Open protected page
    C->>C: Create state and code_verifier; nonce if OIDC
    C-->>U: Navigate to trusted AS authorize endpoint
    U->>AS: client_id, registered redirect_uri, code_challenge, state
    AS->>AS: Check client, redirect URI, authenticate, consent/scope policy
    AS-->>U: Redirect to registered client callback with code and state
    U->>C: Callback code and state
    C->>C: Validate state against browser transaction; consume once
    C->>AS: POST token: code, redirect_uri, code_verifier, client auth if needed
    AS-->>C: Access token; optional ID/refresh tokens by profile
    C->>C: Validate issuer, OIDC ID token nonce/audience, establish session
    C->>RS: Access token for allowed audience/scope
    RS-->>C: Resource after token and object authorization
~~~

AS có thể tận dụng SSO/consent hiện tại nên không nhất thiết hiện form đăng nhập mỗi lần. Nhưng **redirect registration**, OAuth transaction và client/issuer validation vẫn bắt buộc.

### 2.2. Trust boundaries

| Bên | Điều đáng tin | Điều không tự đáng tin |
|---|---|---|
| Browser | Thực thi navigation và cookie origin rules. | Link từ email/chat/QR, tab khác hoặc browser extension. |
| OAuth client | Trusted AS config, registered client ID/callback, phiên người dùng. | URL `next`/`returnUrl` do request tùy ý đưa. |
| AS | Client registration/redirect URI, grant và consent state. | Callback chỉ vì chứa chuỗi `example.com`. |
| Resource Server | Trusted issuer/AS introspection, token validation. | ID token, authorization code hoặc token sai `aud`. |
| User | Authenticated origin/RP của SSO và UI consent được hiểu đúng. | Logo, tiêu đề email hoặc URL rút gọn. |

### 2.3. Code khác access token

Authorization Code Flow trả **code** ở front channel, token endpoint mới đổi code lấy access token:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.com/login/oauth2/code/company?code=EXAMPLE_CODE&state=EXAMPLE_STATE
Cache-Control: no-store
~~~

Code phải **ngắn hạn, dùng một lần, ràng buộc client/redirect URI và PKCE**. Code rò không mặc nhiên đổi thành access token nếu các ràng buộc đúng, nhưng vẫn là dấu hiệu nghiêm trọng về redirect hoặc telemetry và có thể kết hợp lỗ hổng khác.

### 2.4. OIDC login khác API authorization

OIDC client phải xác minh ID token: `iss`, `aud`, `exp`, `nonce` theo transaction/profile, và subject. Không gửi ID token thay access token tới RS. Access token JWT/opaque phải được RS kiểm đúng issuer, audience, scope, expiration và quyền object/tenant hiện tại.

## 3. Phân loại mối đe dọa redirect

| Kiểu | Lỗ hổng/cơ chế | Hậu quả có thể có | Phòng vệ chính |
|---|---|---|---|
| **Trang login giả** | Browser chuyển đến origin AS giả. | Phishing password/MFA. | Origin awareness, passkeys/WebAuthn, URL handling. |
| **Malicious consent** | Ứng dụng attacker dùng **AS thật** xin scopes. | User cấp quyền cho client không tin cậy. | Client governance, consent clarity, scope minimization. |
| **Redirect URI manipulation** | AS cho phép callback ngoài registration. | Code/token front-channel bị đưa sai host. | Exact redirect URI comparison. |
| **Open redirector ở client** | `/redirect?next=...` chuyển đến arbitrary site. | Link phishing bắt đầu ở host thật; có thể leakage. | Strict relative return allowlist và safe callback. |
| **Login CSRF/session swapping** | Callback thiếu `state` bound transaction. | Victim gắn với session/tài khoản không mong muốn. | State random, session-binding, one-time consume. |
| **Authorization code interception** | Code lộ qua app/link/log/deep link. | Kẻ gian cố đổi code lấy token. | PKCE S256, client auth, short-lived single-use code. |
| **Authorization server mix-up** | Client nhầm issuer/token endpoint. | Code có thể bị gửi tới AS sai. | Issuer binding/RFC 9207 and trusted configuration. |
| **Referer/history leakage** | Callback còn code/token trong URL. | Third-party logs/analytics nhận credential. | Callback hygiene, Referrer-Policy, no-store, redaction. |
| **Native URI interception** | Custom scheme/deep link bị app khác nhận. | App trái phép nhận redirect response. | RFC 8252, verified app links, PKCE. |
| **Subdomain takeover** | Callback hostname cũ không còn kiểm soát. | Attacker nhận redirect tại domain được đăng ký. | Domain inventory, ownership validation, remove stale URIs. |

Đừng đồng nhất **người dùng mở website giả** với **OAuth code đã bị đánh cắp**: một phishing site có thể hoạt động ngay cả khi AS implement OAuth chuẩn. Ngược lại, open redirect có thể là vấn đề kỹ thuật dù không ai nhập password.

## 4. Kịch bản A — Chuyển hướng đến trang login giả

### 4.1. Điểm đến cuối mới quan trọng

Người dùng nhấp liên kết từ tin nhắn “SSO đã hết hạn”. Trang đầu là `app.example.com`, nhưng `/go?next=...` dẫn tới một origin khác có UI đăng nhập giả.

~~~text
Expected identity provider:
  https://login.example.com

Untrusted destination:
  https://signin-example.security-check.invalid
~~~

Đây là các địa chỉ minh họa. Cần xác minh **origin cuối cùng trên browser** và policy SSO đã cấu hình, không chỉ một đoạn URL trong email hoặc biểu tượng khóa HTTPS: HTTPS trên domain giả **không chứng nhận đó là AS của tổ chức**.

### 4.2. Open redirect làm link phishing đáng tin giả tạo

~~~text
https://app.example.com/leave?next=https://signin-example.security-check.invalid
~~~

Nếu endpoint `/leave` trả HTTP 302 đến `next` tùy ý, link bắt đầu bằng host thật nhưng kết thúc ở trang attacker. **Không chọn external URL trực tiếp từ `next`**. HTTPS hoặc cookie của host ban đầu không làm site tiếp theo đáng tin.

### 4.3. MFA và passkeys

Passkeys/WebAuthn ràng buộc cryptographic proof với RP ID/origin có thể giảm phishing trên domain giả. OTP/MFA thông thường vẫn có thể bị lừa hoặc relay trong một số kịch bản. Phối hợp **origin checks, passkeys, chống redirect tùy ý, consent governance và incident handling**, thay vì quảng bá “có MFA là hết phishing”.

### 4.4. Nếu user bị lừa thì token có thể bị ảnh hưởng

Lộ password có thể cho attacker khởi tạo đăng nhập thật rồi nhận access/refresh token. Consent phishing với malicious OAuth client có thể tạo **token hợp lệ cho attacker client** mà không cần lấy mật khẩu. Cần kiểm grants/sessions, revoke token/consent, không chỉ đổi password một cách máy móc.

## 5. Kịch bản B — AS chấp nhận `redirect_uri` sai

### 5.1. Authorization request đáng ngờ

~~~http
GET /authorize?response_type=code&client_id=shop-bff&redirect_uri=https%3A%2F%2Fattacker.invalid%2Foauth%2Fcallback&scope=orders%3Aread&state=EXAMPLE_STATE&code_challenge=EXAMPLE_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: login.example.com
~~~

AS phải so `redirect_uri` với registration của **đúng `client_id`**. Nếu URI khác, **không phát code/token** và không redirect lỗi tới URI chưa kiểm. Hiển thị error trên AS-controlled page hoặc cơ chế lỗi an toàn.

### 5.2. Exact matching thay cho prefix/contains

Ví dụ registration:

~~~text
client_id: shop-bff
allowed callback:
  https://app.example.com/login/oauth2/code/company
~~~

Không chấp nhận các địa chỉ chỉ “trông giống”:

~~~text
https://app.example.com.attacker.invalid/callback
https://app.example.com@attacker.invalid/callback
https://app.example.com/callback?next=https://attacker.invalid
https://app.example.com.evil.invalid/path
~~~

`startsWith("https://app.example.com")`, `endsWith("example.com")` hay `contains("example.com")` không đủ. OAuth Security BCP ưu tiên **exact string matching registered redirect URI**, với ngoại lệ cụ thể đối với cổng loopback native app theo RFC 8252. Không nới lỏng bằng wildcard/open registration hoặc tự “canonicalize gần đúng” rồi chấp nhận.

### 5.3. Token endpoint phải ràng buộc code

Authorization code gắn với **client, redirect URI và PKCE challenge**. Token endpoint kiểm code single-use/expiry, client authentication nếu áp dụng, `redirect_uri` theo protocol và `code_verifier`. Điều này giảm khả năng một code lộ đổi được thành tokens ở client/redirect khác. Tuy nhiên đừng coi PKCE là lý do cho phép `redirect_uri` tùy ý.

### 5.4. Registration và domain ownership

Quy trình đăng ký/sửa redirect URI phải được bảo vệ bằng quyền quản trị, approval/audit khi cần, và ownership verification đối với host được cho phép. Khi xóa app/subdomain hoặc đổi domain, phải thu hồi callback cũ; **subdomain takeover** của một redirect URI đã đăng ký có thể khiến AS gửi code về nơi kẻ gian kiểm soát.

## 6. Kịch bản C — Open redirect ngay tại callback hoặc route của client

### 6.1. Callback hợp lệ chưa đủ

AS được cấu hình chính xác:

~~~text
https://app.example.com/oauth/callback
~~~

Client xử lý code rồi lấy `next`/`returnUrl` từ query, cookie, session state không bảo vệ hoặc request body và trả `Location` ra ngoài. Đây là nơi attacker có thể lợi dụng **domain client hợp lệ làm bước trung gian phishing**, hoặc khai thác sự tồn tại của code trên URL nếu callback leak qua `Referer`/logs/analytics.

### 6.2. URL tricky values

~~~text
/redirect?next=https://attacker.invalid
/redirect?next=//attacker.invalid
/redirect?next=%2F%2Fattacker.invalid
/redirect?next=\attacker.invalid
/redirect?next=/safe%0d%0aLocation:%20https://attacker.invalid
~~~

Chúng minh họa class lỗi parser/canonicalization/HTTP header handling, **không phải payload để thử trên website khác**. Một rule “chỉ check path bắt đầu bằng `/`” vẫn sai với `//`, backslash và encoded separators. Dùng server-owned route ID hoặc **strict normalized relative path**; không đưa raw user data vào `Location`.

### 6.3. Callback bảo mật theo thứ tự

1. Xác minh `state` thuộc session/transaction đang chờ, có TTL và one-time consume.
2. Kiểm return path đã được lưu server-side sau khi **validate relative**.
3. Đổi code với AS theo client/redirect URI/PKCE đúng.
4. Với OIDC, validate `iss`, `aud`, `nonce`, `exp` của ID token; thiết lập session an toàn.
5. Không chuyển `code`, `state`, access/refresh token hay ID token sang URL tiếp theo.
6. Trả redirect đến **internal route** đã được kiểm, ví dụ `/orders`.

~~~http
HTTP/1.1 303 See Other
Location: /orders
Cache-Control: no-store
Referrer-Policy: no-referrer
~~~

### 6.4. `state` không phải external return URL

Nên dùng `state` ngẫu nhiên như key lookup tới server-side authorization transaction đã gắn browser session, issuer/client config, nonce/PKCE và **safe internal return route**. Nếu đưa URL trực tiếp trong `state`, phải chống sửa và validate destination; **không đọc state rồi redirect bừa**. Session-binding, TTL và one-time use ngăn login CSRF/replay.

### 6.5. Tránh leak qua browser và logs

Callback URL chứa code có thể lọt vào reverse-proxy logs, APM, analytics, browser history, third-party resources hoặc `Referer`. Dùng server-side callback, `Cache-Control: no-store`, `Referrer-Policy: no-referrer`/header policy thích hợp, không nhúng third-party resources trên callback, consume code nhanh, redirect clean URL và **log allowlist** thay vì ghi nguyên URL/body/headers.

## 7. Login CSRF và tráo phiên qua callback

### 7.1. Không phải mọi tấn công đều cần lấy token

**Login CSRF** có thể khiến browser của nạn nhân hoàn thành một phiên đăng nhập **không do browser đó chủ động khởi tạo**, ví dụ gắn session của nạn nhân vào tài khoản attacker. Đây là vấn đề **ràng buộc giữa authorization request, browser session và callback**, khác với ăn cắp access token hay dụ nhập mật khẩu vào trang giả.

~~~text
Legitimate flow:
  Browser session S1 creates OAuth transaction T1 with state ST1
  Callback containing state ST1 is accepted only by S1 / T1

Vulnerable flow:
  Client accepts callback with any state or without matching transaction
  An unrelated authorization response may be bound to victim browser
~~~

### 7.2. `state` bảo vệ điều gì?

`state` thường là **giá trị ngẫu nhiên khó đoán, dùng cho từng authorization transaction**. Client lưu nó trong server-side session/transaction store hoặc phương thức bảo đảm integrity và session binding tương đương. Callback cần:

- Bắt buộc có đúng state được client phát cho browser/transaction đó.
- One-time consume và hết hạn; callback lặp không được tạo login thứ hai.
- Ràng buộc với issuer đã chọn, client registration, redirect URI, PKCE verifier, OIDC nonce và return path.
- Không dùng state attacker tự cung cấp để quyết định nơi redirect sau login.
- Không ghi `state` kèm `code` vào logs, ticket, analytics hoặc third-party resources.

### 7.3. `state` không phải user authentication

Một state đúng **không chứng minh code do đúng AS phát**, không chứng minh user đã login thành công và không kiểm scope/audience. Nó chỉ giúp correlate phản hồi với giao dịch phía client. Ở multi-AS client, state phải gắn với issuer/endpoint để chống mix-up.

### 7.4. OIDC `nonce` có vai trò khác

`nonce` được client đưa vào authentication request rồi xác minh trong ID token theo OIDC profile, giúp ràng buộc ID token với request và chống ID token replay/substitution. **State bảo vệ request–response correlation/CSRF, nonce ràng buộc ID token, PKCE ràng buộc authorization code với verifier**. Không cái nào thay exact redirect URI matching hoặc API authorization.

### 7.5. Nhiều tab, session fixation, race

Mỗi tab/authorization attempt cần transaction riêng. Không lưu một biến global `lastState` hoặc `lastCodeVerifier` khiến tab A ghi đè tab B. Sau login, BFF cần session fixation defenses, thường rotate session ID, dùng cookies `HttpOnly`, `Secure`, `SameSite` thích hợp và CSRF controls.

## 8. PKCE và authorization code interception

### 8.1. PKCE S256 theo RFC 7636

Nếu code bị đọc trong front channel, **Proof Key for Code Exchange** đòi người đổi code tại token endpoint chứng minh biết `code_verifier` được tạo trước đó.

~~~text
Per transaction:
  code_verifier = high entropy random value
  code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
  code_challenge_method = S256

Authorization request:
  code_challenge; code_challenge_method=S256

Token request:
  code; original code_verifier

AS:
  Compare derived challenge to stored challenge for that code
~~~

Code verifier cần có entropy và encoding đúng spec, không được log. **Không dùng `plain` khi S256 khả dụng**; cấu hình AS phải kiểm PKCE với authorization code theo policy/BCP.

### 8.2. PKCE không hợp thức hóa redirect sai

Nếu AS gửi code tới host attacker, PKCE có thể làm code **khó redeem**, nhưng browser vẫn được chuyển sai origin, attacker có thể lừa tiếp người dùng hoặc kết hợp XSS/compromise để lấy verifier. Root cause vẫn là **AS cấp redirect URI ngoài registration**. Chặn nó ở AS, đừng viện PKCE để nới validation.

### 8.3. Confidential client authentication là lớp bổ sung

Một BFF/confidential client có thể xác thực token endpoint bằng client secret, `private_key_jwt` hoặc mTLS. Nó chứng minh **client identity**, còn PKCE chứng minh **code verifier của giao dịch**; không thay nhau. SPA/native public client **không thể bảo vệ static client secret** như backend.

### 8.4. Token endpoint phải ràng buộc code

- Code có TTL ngắn, dùng một lần.
- Ràng buộc code với đúng `client_id` và redirect URI theo protocol.
- Kiểm PKCE `code_verifier`/`code_challenge`.
- Kiểm client authentication khi áp dụng.
- Không dùng GET hoặc log raw code/PKCE verifier.
- Phát scopes/audience từ grant/consent đã được phép, không lấy từ query callback.

**Lưu ý:** PKCE không chống được người dùng tự nhập password vào phishing site, và không ngăn XSS chạy trong origin dùng quyền app. Consent phishing trên AS thật cũng vẫn có thể xảy ra.

## 9. Authorization Server mix-up và issuer binding

### 9.1. Multi-AS client cần ràng buộc nguồn phát

Một ứng dụng hỗ trợ login từ hai identity providers/Authorization Servers. Nếu callback handler chọn token endpoint bằng query hoặc dựa vào prefix URL thay vì transaction đã khởi tạo, code của AS-A có thể bị gửi nhầm đến AS-B. Đây là lớp **authorization server mix-up**.

~~~text
Transaction T1:
  selected AS = https://login-a.example.com
  expected token endpoint = AS-A/token
  registered client = Client-A
  state = ST1

Unsafe callback:
  chooses token endpoint using untrusted issuer query
~~~

### 9.2. Cấu hình issuer/server-owned

Khi bắt đầu authorization request, client lưu issuer đã chọn, authorization/token endpoints, client ID, callback, PKCE verifier và state theo trusted configuration. Callback phải kiểm nó đúng transaction, **không cho user-controlled query điều khiển token endpoint**.

### 9.3. RFC 9207 và OIDC validation

- **RFC 9207** định nghĩa thông tin nhận diện issuer trong OAuth authorization response để client phát hiện mix-up khi được áp dụng.
- **OIDC** yêu cầu kiểm `iss` trong ID token tương ứng OP đã chọn, cùng `aud` và nonce theo profile.
- **RFC 8414 / OIDC Discovery** có issuer metadata/endpoint; chỉ lấy từ nguồn trusted/validated.
- `state` đúng **chưa đủ** nếu transaction không bind issuer và endpoint.

### 9.4. Cảnh báo về URL trong token header

Client/RS không được lấy `jku`/`x5u`/`kid` do JWT attacker gửi để tùy ý fetch JWKS hoặc chọn một issuer mới. AS mix-up xảy ra trước/trong authorization response, còn JWT key confusion có thể xuất hiện ở token validation; **cả hai đều đòi trusted configuration**.

## 10. Consent phishing: Authorization Server thật vẫn có thể bị lạm dụng

### 10.1. App attacker có thể xin token hợp lệ

Trong consent phishing, user thực sự được redirect tới **AS thật** và xác thực đúng domain. Nhưng OAuth client yêu cầu grant là **ứng dụng không đáng tin** hoặc giả danh tên/nhãn của ứng dụng hợp pháp; user không nhận ra phạm vi quyền khi đồng ý.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant M as Untrusted OAuth Client
    participant AS as Real Authorization Server
    participant RS as Resource Server
    M-->>U: Link requesting OAuth authorization
    U->>AS: Visit true AS endpoint for client M
    AS->>AS: Authenticate, show requesting client and scopes
    U->>AS: Gives consent without recognizing risk
    AS-->>U: Redirect to registered callback of client M
    U->>M: Authorization response for M
    M->>AS: Token request with valid client/PKCE
    AS-->>M: Token within approved grant
    M->>RS: Calls API using granted token
~~~

Trong trường hợp này, **exact callback matching và PKCE có thể đều đúng**. Vấn đề là **người dùng bị dẫn dụ cấp quyền cho client của attacker**. Không giải quyết bằng cách chỉ sửa `state` hoặc redirect URI.

### 10.2. Rủi ro trong màn hình consent

- Client display name/logo có thể bị giả mạo không?
- Publisher/redirect domain có được xác minh?
- Scopes có rộng hơn nhu cầu tác vụ không?
- `offline_access`/refresh token có được yêu cầu không, vì sao?
- Có bước admin approval/organization verified app cho quyền nhạy cảm?
- User có biết cách xem và thu hồi grants đã cấp?

### 10.3. Phòng vệ ở AS/tổ chức

- Giới hạn third-party app consent và scopes nhạy cảm khi chính sách yêu cầu.
- Review/verify client identity, redirect domain ownership và publisher.
- Least-privilege scopes, resource indicators/audience restrictions.
- Minh bạch thông tin publisher, client và quyền truy cập trong consent UI.
- Audit registration, consent, token issuance, refresh token grants.
- Cơ chế revoke quyền và tokens nhanh khi phát hiện ứng dụng lừa đảo.

### 10.4. Ứng cứu không chỉ là đổi password

Malicious OAuth client có thể nắm **access/refresh tokens được cấp hợp lệ**. Cần revoke grants/refresh families, vô hiệu client nếu được phép, kiểm resource access và sessions theo incident policy. Đổi mật khẩu user **không mặc nhiên** thu hồi mọi OAuth grant đã cấp.

## 11. Rò authorization code và token qua URL, log, Referer

### 11.1. Front channel không phải kênh bảo mật tuyệt đối

Authorization Code Flow chuyển code qua browser. Tùy cấu hình, callback URL có thể lọt vào:

~~~text
browser history, screenshots, shared URLs
reverse proxy/load balancer access logs
application request logs and exception traces
APM telemetry and URL analytics
third-party images, scripts or outbound Referer
support tickets and diagnostic captures
~~~

Modern browsers có chính sách Referrer nhất định, nhưng không coi mặc định browser là đủ. **Không nhúng third-party scripts/images vào callback page trước khi code được tiêu thụ và URL được làm sạch.**

### 11.2. Tác động khác nhau tùy credential

| Rò rỉ | Tác động | Phòng vệ |
|---|---|---|
| Authorization code | Có thể thử redeem, còn cần vượt client/PKCE/redirect binding. | PKCE S256, short TTL, one-time code, no logs. |
| Bearer access token (JWT/opaque/JWE) | Attacker có thể replay nếu còn hạn/active. | TLS, storage hygiene, TTL/aud/scope, revoke, sender binding. |
| Refresh token | Có thể xin access token mới theo grant. | AS-only usage, rotation/reuse detection, revoke family. |
| OIDC ID token | Lộ identity claims hoặc bị client dùng sai. | Nonce/issuer/audience/time/purpose validation. |
| PKCE verifier | Nếu lấy cùng code, có thể vượt PKCE layer. | Giữ riêng server/client transaction, không log. |
| Client secret/private key | Có thể giả OAuth client theo chính sách. | Secret Manager/KMS, client auth và rotate. |

JWT JWS có payload đọc được bằng Base64URL decode, không phải encryption. Token opaque không lộ claims trong string nhưng vẫn là bearer credential. **JWE cũng bị replay nguyên ciphertext nếu không sender-bound.**

### 11.3. Callback hygiene

- `Cache-Control: no-store` và `Referrer-Policy: no-referrer`/CSP phù hợp.
- Không có third-party tracking trên callback.
- Exchange code nhanh qua token endpoint tin cậy, không forward code tới URL `next`.
- Không đặt access/refresh/ID tokens trong URL tiếp theo.
- Redirect sang clean internal route sau khi tạo session.
- Redact query, Authorization/Cookie headers và token endpoint bodies ở proxy/APM/logs.
- Dùng structured event chứa route template, status, transaction ref nội bộ; không raw code/state/token.

~~~json
{
  "event": "oauth.callback.completed",
  "route": "/login/oauth2/code/{registrationId}",
  "trusted_registration": "company",
  "transaction_ref": "internal-tx-18",
  "result": "STATE_AND_ISSUER_VERIFIED"
}
~~~

### 11.4. Form POST response mode không miễn validation

OIDC `form_post` response mode (khi profile hỗ trợ) đưa response qua HTML form POST thay query URL, giảm một số dạng URL leakage. Nhưng request body vẫn có thể bị log, và **state/PKCE/issuer/nonce/cookie/session validation** vẫn bắt buộc. Chọn response mode theo contract AS/client, không coi POST tự động an toàn tuyệt đối.

## 12. Redirect trên BFF, SPA và native application

### 12.1. BFF/confidential client

BFF nhận code qua HTTPS callback, đổi code server-to-server và giữ access/refresh tokens server-side. Browser giữ cookie session `HttpOnly`, `Secure`, `SameSite` thích hợp; thêm CSRF/session fixation controls. BFF cần **trusted external URL, state/PKCE/nonce transaction, session ID rotation và safe internal return route**. Cookie HttpOnly không ngăn người dùng bị dẫn tới phishing website ngoài origin.

### 12.2. SPA/public browser client

SPA dùng Authorization Code + PKCE, **không nhúng client secret** trong frontend. Client-side callback phải chú ý third-party JS, XSS, browser storage, clean URL, state/nonce. PKCE không ngăn script attacker đã chạy trong app origin sử dụng các quyền của app. Khi phù hợp, dùng BFF để tránh đưa access/refresh token tới JavaScript.

### 12.3. Native apps và RFC 8252

Native apps nên dùng **external system browser** thay embedded webview cho OAuth authorization. Redirect types theo registration/platform có thể gồm:

~~~text
Loopback redirect with dynamically chosen port:
  http://127.0.0.1:{port}/oauth2redirect/app
  http://[::1]:{port}/oauth2redirect/app

Claimed HTTPS / verified app link:
  https://mobile.example.com/oauth2redirect/app

Private-use URI scheme:
  com.example.shop:/oauth2redirect/app
~~~

**RFC 8252 loopback exception** cho phép thay đổi port trong điều kiện cụ thể, không có nghĩa wildcard mọi host/path. Client cần bind loopback listener phù hợp, consume code một lần và dùng PKCE S256.

### 12.4. URI interception và deep links

Custom schemes có thể bị app khác nhận/đăng ký tùy hệ điều hành. Verified app links/claimed HTTPS giúp ràng buộc domain–app khi platform hỗ trợ, nhưng phải test association, intent filters và fallback browser behavior. PKCE giảm khả năng redeem code bị chặn, không loại bỏ mọi phishing/session mix-up. App nhắn tin/link previews có thể quan sát URLs, vì vậy tránh redirect trung gian chứa code/token.

## 13. Reverse proxy, CDN và callback origin spoofing

### 13.1. Host header injection

BFF đằng sau ingress có thể xây callback URL từ HTTP `Host`, `X-Forwarded-Host` hay `X-Forwarded-Proto`. Nếu proxy không **drop/overwrite headers từ untrusted caller**, attacker có thể tác động external origin mà app tưởng được cấu hình; từ đó phát sinh callback/redirect confusion.

Đừng xây OAuth redirect URI từ giá trị attacker tùy ý. Dùng **trusted external base URL** từ deployment configuration hoặc chỉ tin forwarded headers do **proxy đã được xác thực/kiểm soát**.

~~~yaml
# Policy minh họa, không phải Spring properties tự hoạt động.
oauth:
  external-base-url: https://app.example.com
  redirect-path: /login/oauth2/code/company
  reject-unrecognized-host: true
  trust-forwarded-headers-only-from-controlled-proxies: true
~~~

### 13.2. Subdomain takeover

~~~text
Registered:
  https://old-login.example.com/oauth/callback

Later:
  DNS/CNAME remains but hosting ownership expires

Risk:
  The registered redirect endpoint may be controlled by another party
~~~

Exact AS redirect matching chưa đủ nếu endpoint đúng URI đó **không còn thuộc tổ chức**. Duy trì domain/redirect inventory, CNAME ownership monitor, remove stale registrations và audit changes.

### 13.3. Reverse-proxy logs và redirects

Không ghi nguyên callback `?code=...&state=...` vào access log. Cân nhắc HTTP 302/303 cache headers, không dùng 301 permanent redirect cho callback một cách bất cẩn. CDN/middlewares không được lưu shared cache chứa authorization response hoặc chuyển code tới origin khác do cấu hình sai.

### 13.4. Exact URI chưa đủ khi callback yếu

Ngay cả khi AS chỉ tin `https://app.example.com/oauth/callback`, endpoint đó có thể bị XSS, open redirect, host takeover hoặc unsafe forwarding. **AS registration + client callback implementation + domain lifecycle + browser/session policy** phải cùng an toàn.

## 14. Java: dùng route ID thay arbitrary return URL

### 14.1. Mapping phía server

Cách giảm đáng kể lỗi URL parser là **không cho caller quyết định arbitrary destination**. App chỉ nhận route ID nằm trong allowlist:

~~~java
import java.util.Map;
import java.util.Optional;

public final class SafeReturnRoutes {
    private static final Map<String, String> ROUTES = Map.of(
        "home", "/",
        "orders", "/orders",
        "settings", "/settings",
        "help", "/help"
    );

    private SafeReturnRoutes() {}

    public static String resolve(String requestedRouteId) {
        return Optional.ofNullable(ROUTES.get(requestedRouteId))
            .orElse("/");
    }
}
~~~

`requestedRouteId=https://attacker.invalid` hay `//attacker.invalid` không có key trong map, trả fallback `/`. App **không phản chiếu raw input** vào `Location`. Với dynamic URLs `/orders/{id}`, dùng route builder và kiểm quyền trên ID; không ghép chuỗi tùy ý vào path.

### 14.2. Gắn route vào OAuth transaction

~~~text
Before navigating to AS:
    routeId = validateRequestRouteId()
    safeReturnPath = SafeReturnRoutes.resolve(routeId)
    create server-side transaction:
      stateRandom, pkceVerifier, oidcNonce,
      trustedIssuer, clientRegistration, registeredRedirectUri,
      browserSessionRef, safeReturnPath, expiresAt, consumed=false

On callback:
    transaction = lookupAndConsume(state, browserSessionRef)
    verify expected issuer/client/callback context
    redeem code with correct PKCE, redirectUri and client auth
    validate token response and OIDC ID token as required
    establish rotated application session
    HTTP 303 Location: transaction.safeReturnPath
~~~

Không dùng `request.query.next`/`returnUrl` lúc callback. Transaction cần có TTL, session binding, one-time consume và integrity. State có thể là opaque random lookup key; không dùng nó làm external redirect URL.

### 14.3. Trường hợp cần external navigation

Nếu business thật sự cần external URL, phải có **approved destinations/origins** và review, URI parsing + canonicalization nhất quán, kiểm scheme/host/userinfo/port/IDNA/trailing-dot/encoding/fragment cùng policy. Một URL chỉ “startsWith domain công ty” không đủ. Khi không cần external URL, **return route ID** là phương án đơn giản và chắc chắn hơn.

## 15. Spring Security OAuth2 Login: callback và success redirect

### 15.1. Client registration với callback cố định

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            client-id: shop-bff
            client-secret: INJECT_FROM_SECRET_MANAGER
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: https://login.example.com
~~~

Đây là cấu hình minh họa cho **confidential web client**, không chứa secret thật. `client-secret` chỉ là placeholder, phải được inject từ secret provider/deployment. `issuer-uri` là cấu hình OP/AS tin cậy, không lấy từ query callback.

**Chú ý:** `{baseUrl}` có thể được framework dựng từ HTTP request/reverse proxy. Nếu proxy tin `Host`, `Forwarded`, `X-Forwarded-Host` từ public client, attacker có thể tác động callback URL. Dùng trusted external origin và proxy header policy đúng; kiểm **URL redirect thực sinh ra** khớp registration.

### 15.2. OAuth login success handler không nhận external `next`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebLoginSecurity {
    @Bean
    SecurityFilterChain webLogin(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .successHandler((request, response, authentication) -> {
                    response.setHeader("Cache-Control", "no-store");
                    response.setHeader("Referrer-Policy", "no-referrer");
                    response.sendRedirect(request.getContextPath() + "/app");
                }))
            .build();
    }
}
~~~

Handler chỉ redirect đến internal path `/app`, không phản chiếu `request.getParameter("next")`. Mẫu không thay cấu hình state/PKCE/nonce/issuer validation, CSRF, BFF session store và logout theo Spring version. Cần kiểm chính xác security filters và token/OIDC flow profile.

### 15.3. Mẫu lỗi cần tránh

~~~java
// KHONG AN TOAN: attacker can control nextUrl.
response.sendRedirect(request.getParameter("nextUrl"));
~~~

Khi cần quay lại trang trước login, lưu **route ID** đã allowlist trong transaction server-side; callback dùng safe return path trong transaction, không đọc `nextUrl` trực tiếp.

### 15.4. Không mặc định PKCE đã bật

Thư viện Spring có cơ chế quản lý state và hỗ trợ PKCE, nhưng **đừng tuyên bố S256 được bật ở mọi confidential-client setup**. Kiểm request authorization có `code_challenge_method=S256` và token exchange có verifier tương ứng; AS phải reject sai/missing verifier theo policy. Nếu custom authorization request resolver hoặc login handler, test lại request binding và failure scenarios.

### 15.5. Các việc framework không thay bạn làm

- Restrict registered client/redirect URI tại AS.
- Trusted issuer/provider metadata và key source.
- External base URL/proxy headers.
- State/nonce/PKCE per-transaction, anti-session-fixation.
- Return path allowlist trong custom handler.
- OAuth token audience/scope và object-level authorization ở APIs.
- Redaction secrets/query trong logs và incident monitoring.

## 16. Authorization Server: chính sách redirect URI

### 16.1. AS xử lý authorization request

~~~text
Input:
    client_id, redirect_uri, response_type=code,
    requested scope/resource,
    state, code_challenge, code_challenge_method

AS:
    lookup trusted client registration
    check permitted grant and response type
    compare registered redirect_uri exactly
    validate PKCE challenge and requested grants
    authenticate user; check consent if needed
    issue short-lived code bound to client, redirect and PKCE
~~~

Nếu redirect URI không hợp lệ, **đừng trả authorization code hoặc redirect OAuth error về URI đó**. Sử dụng AS-controlled error handling.

### 16.2. Java minh họa exact-match cho web HTTPS callback

~~~java
import java.net.URI;
import java.util.Set;

public final class RegisteredWebRedirect {
    private RegisteredWebRedirect() {}

    public static boolean permitted(
            String requested,
            Set<String> registeredUris) {

        if (requested == null || registeredUris == null
                || !registeredUris.contains(requested)) {
            return false;
        }

        try {
            URI uri = URI.create(requested);
            return "https".equals(uri.getScheme())
                && uri.getHost() != null
                && uri.getUserInfo() == null
                && uri.getFragment() == null;
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }
}
~~~

Đây là **minh họa policy riêng cho HTTPS web callbacks**, không phải OAuth AS implementation hoàn chỉnh. Native loopback port exception/custom schemes phải tuân RFC 8252 và kiểm khác. Nên dùng framework AS chuẩn được bảo trì thay vì tự viết toàn bộ validation/redirection/token endpoint.

### 16.3. Những gì so sánh bằng prefix bỏ sót

- Hostname `app.example.com.attacker.invalid`.
- Userinfo `app.example.com@attacker.invalid`.
- Path `/callback-open-redirect` trông giống `/callback`.
- Query `next` trỏ ra ngoài.
- Percent-encoding, backslash, IDNA Unicode/trailing-dot, ports hoặc path normalization bất nhất.
- Callback có fragment (redirect URI registration trong OAuth không nên bao gồm fragment).

**Exact registered URI string matching** theo OAuth Security BCP giảm lớp confusion này. Khi cần ngoại lệ RFC 8252 loopback port, dùng logic riêng có kiểm thay vì wildcard chung.

### 16.4. JAR/PAR là lớp bổ sung, không thay registration

**PAR (RFC 9126)** và **JAR (RFC 9101)** có thể bảo vệ authorization request ở mức profile khỏi tampering/parameter injection. Nhưng:

- Không miễn kiểm redirect URI/client registration.
- Không ngăn consent phishing nếu client attacker được phép xin grant.
- Không thay `state`, PKCE, issuer identification và OIDC nonce.
- Cần client authentication, key custody/alg allowlist và interoperability theo profile.

### 16.5. Bảo vệ thay đổi callback registration

Cập nhật allowed redirect URIs nên yêu cầu role phù hợp, ownership verification, change audit và giới hạn wildcard/third-party domains. Khi domain cũ bị bỏ, xóa callback đó. **Một redirect URI đúng chuỗi nhưng domain bị takeover vẫn là mục tiêu tấn công**.

## 17. Kết nối phishing redirect với token security

### 17.1. Redirect sai có thể gây những hậu quả khác nhau

| Sự cố đã xảy ra | Tài sản có nguy cơ | Cần xác minh và xử lý |
|---|---|---|
| User nhập password/MFA ở fake AS. | Credentials, phiên SSO. | Auth events, reset/recovery, revoke sessions/tokens khi cần. |
| AS redirect code đến callback không hợp lệ. | Authorization code/front-channel data. | Client/redirect/PKCE binding, code usage, AS configuration. |
| Open redirect ở client sau callback. | User bị đưa tới phishing site; code/URL có thể lộ. | Callback/return route logs và referrer policy. |
| Consent cho malicious OAuth app. | Access/refresh tokens hợp lệ của attacker client. | Revoke grant/client, review scopes và resource access. |
| ID token được nhận từ issuer sai. | Account/session confusion. | `iss`, `aud`, `nonce`, transaction binding. |
| Access token bị log trong callback. | JWT/opaque/JWE bearer credential. | Redact logs, revoke token, sender binding và blast radius. |

### 17.2. JWT, opaque và JWE không làm redirect đúng tự động

- **Signed JWT (JWS):** chữ ký chứng minh tính toàn vẹn và signer trong trusted key context; **không che claims**. Khi bị lấy, Bearer JWT có thể được replay nếu còn hạn và không sender-bound.
- **Opaque access token:** một reference credential cần AS/introspection; không tự lộ claims, nhưng attacker vẫn có thể replay raw token nếu còn `active=true`.
- **JWE:** ciphertext che payload khỏi người không có key, nhưng **gửi lại nguyên JWE Bearer** có thể đủ để gọi RS; decrypt success không thay issuer/authorization checks.
- **Refresh token:** dùng ở token endpoint, không gửi cho RS; nếu attacker client được cấp hoặc lấy trộm, có thể xin access tokens mới. Cần revoke/family rotation và client binding.
- **OIDC ID token:** dùng client validation/identity, `aud` thường là client ID; không gửi thay access token tới API.

### 17.3. AS cấp token hợp lệ sai người vẫn là rủi ro

Trong consent phishing, AS thật có thể phát access token **đúng chuẩn** cho client attacker theo grant mà user vô tình đồng ý. Signature/issuer/`aud`/`exp` đều có thể hợp lệ. Vì vậy **chỉ kiểm JWT signature ở RS không phân biệt được “consent có thật nhưng bị lừa”**. Phòng vệ cần client verification, scope minimization, consent policy và khả năng revoke.

### 17.4. Audience/scope và business authorization

Ngay cả sau login thành công, RS phải kiểm:

~~~text
token.issuer matches configured AS
token.audience includes this resource
token.expiration and nbf valid
token.type is access-token (not ID/refresh/code)
token.scope permits requested operation
principal/tenant/object authorization still holds
sender-constrained proof valid if required
~~~

Đối với opaque token, RS dùng authenticated introspection và metadata hợp đồng; đối với JWT, verify chữ ký/claims bằng trusted issuer key. Nếu client bị lừa đưa token Orders sang Payments, **`aud=orders-api` phải khiến Payments từ chối**, không “tin vì vừa login”.

### 17.5. DPoP/mTLS giảm replay, không giải quyết phishing origin

**DPoP (RFC 9449)** và **mTLS-bound tokens (RFC 8705)** có thể giảm giá trị của **token string bị đánh cắp đơn lẻ**. Nhưng:

- Nếu attacker kiểm được holder private key hoặc cùng browser origin/process, có thể vẫn misuse.
- Phishing login bằng fake domain không được tự động ngăn nhờ token binding.
- Consent phishing có thể cấp token bound với **chính key của malicious client**.
- RS phải kiểm `cnf` binding và DPoP proof/mTLS certificate, không chỉ introspection `active=true`.
- Redirect registration và state/issuer checks vẫn là điều kiện độc lập.

### 17.6. Thu hồi quyền theo đúng đối tượng

- Một stolen access token → revoke/deny token hoặc dựa TTL phù hợp, investigate usage.
- Lộ refresh token → revoke family/grant và xử lý reuse detection.
- Consent phishing → revoke app grant/scopes, potentially client registration.
- Lộ AS private signing key → emergency key trust cutoff/reissue trên mọi RS.
- User bị phishing password → account/session recovery và review grants/tokens.

Không dùng **rotate JWT signing key** như biện pháp mặc định cho mọi redirect incident; nó có blast radius lớn và không tự thu hồi refresh family hoặc access opaque tokens.

## 18. Quan sát và phát hiện phishing redirect

### 18.1. Những event có giá trị

~~~text
OAUTH_AUTHORIZE_REQUEST_RECEIVED
OAUTH_REDIRECT_URI_REJECTED
OAUTH_CLIENT_REGISTRATION_CHANGED
OAUTH_AUTHORIZATION_CODE_ISSUED
OAUTH_TOKEN_EXCHANGE_DENIED
OAUTH_PKCE_VERIFIER_MISMATCH
OAUTH_STATE_MISMATCH_OR_REPLAY
OIDC_NONCE_OR_ISSUER_MISMATCH
OAUTH_CONSENT_GRANTED
OAUTH_SUSPICIOUS_SCOPE_REQUEST
OAUTH_LOGIN_CALLBACK_SUCCESS_OR_FAILURE
OAUTH_RETURN_DESTINATION_REJECTED
OAUTH_TOKEN_OR_GRANT_REVOKED
PROXY_UNTRUSTED_FORWARDED_HEADER_REJECTED
~~~

Không phải tất cả là event names có sẵn của Spring/AS; đây là **taxonomy minh họa** cho telemetry. Không làm lộ raw code, state, PKCE verifier, client secret, access/refresh token hoặc raw authorization URL.

### 18.2. Structured event minh họa

~~~json
{
  "event": "oauth.redirect_uri.rejected",
  "occurred_at": "2026-11-23T03:30:00Z",
  "issuer_ref": "company-login",
  "client_ref": "shop-bff",
  "attempt_ref": "auth-tx-opaque-32",
  "reason_code": "UNREGISTERED_REDIRECT_URI",
  "redirect_destination_category": "EXTERNAL_UNREGISTERED",
  "result": "DENIED"
}
~~~

`attempt_ref` phải là internal correlation ID có TTL/retention; không dùng full `redirect_uri` chứa secrets/query làm metric label. Nếu cần lưu URI bị từ chối để forensic, lưu ở **restricted, redacted log** với size limits và đánh giá privacy/security; không in nguyên trong exception trả user.

### 18.3. Detection signals

| Signal | Vì sao đáng quan tâm | Đối chiếu trước kết luận |
|---|---|---|
| Nhiều redirect URI rejections theo client. | Có thể đang thử bypass URI registration. | Client rollout/config error hay traffic bất thường? |
| Login callback `state` mismatches tăng. | Login CSRF/session swapping, cookies bị chặn hoặc race. | SameSite/proxy changes, tab parallel flows. |
| PKCE mismatch/code reuse tăng. | Code interception, replay hoặc client bug. | SDK deploy, device/native callback issue. |
| Issuer mismatch ở multi-AS client. | Mix-up/misrouting hoặc attack. | Trusted AS metadata, callback mapping. |
| Client consent nhiều scopes nhạy cảm. | Possible malicious OAuth client. | Approved app status, user tasks, admin policy. |
| Callback domain registration đổi. | New redirect host có thể bị chiếm/giả. | Change ID, ownership/DNS validation. |
| Open redirect requests tới `next`. | Link phishing dùng domain thật làm trung gian. | Gateway log categories, known integrations. |
| Tokens issued cho client lạ. | Consent phishing/malicious registration. | Client review, allowed scopes, grants. |
| New login sessions sau phishing URLs. | Credentials có thể bị lộ. | Authentication source/risk signals, affected users. |
| Access/refresh token leakage trong logs. | Replay/long-lived session abuse. | Canaries, redaction testing và log access. |

### 18.4. Tránh high-cardinality/PII trong metrics

~~~text
oauth_authorization_redirect_reject_total{issuer,client_group,reason}
oauth_login_state_mismatch_total{issuer,registration}
oauth_token_exchange_denied_total{issuer,reason}
oauth_consent_grant_total{issuer,scope_risk_tier}
oauth_callback_latency_seconds{registration,result}
oauth_open_redirect_denied_total{route}
oauth_redirect_domain_change_total{environment,result}
~~~

Không đặt attacker URL, user email, raw `state`, code, token hoặc custom `redirect_uri` làm labels. Với investigation thật có thể dùng masked/hardened logs theo quyền, tách khỏi public dashboards.

### 18.5. Gắn actor vào đúng tầng

- AS `redirect_uri` rejection → provider/service và `client_id` đã khai, **không tự xác định attacker user**.
- Client callback mismatch → browser session/internal tx, có thể chưa authenticated user.
- Consent event → user đã xác thực, client được cấp và scopes đã phê duyệt theo policy.
- RS denied access → resource/client/subject context đã verify.
- Phishing email/report → nguồn báo cáo có thể chưa xác minh, không coi URL/claim bên ngoài là trusted facts.

**Audit giúp điều tra, không thay authorization enforcement**. Một cơ chế alert cần xác định false positives và có approval trước khi tự vô hiệu client/grants.

## 19. Phòng thủ nhiều lớp theo vị trí kiểm soát

| Lớp | Bắt buộc kiểm gì? | Nếu thiếu |
|---|---|---|
| **Client registration** | Quyền đăng ký, trusted redirect URIs/domain ownership. | Thay callback sang host attacker. |
| **AS authorization endpoint** | Exact URI, grant type, PKCE challenge, scope/resource/consent. | Phát code đến nơi không đáng tin. |
| **Browser/user awareness** | Trusted login origin, clear consent client/scopes, phishing-resistant login. | User login/consent trên site/app giả. |
| **Client callback** | State/session/issuer binding, one-time, safe route return. | Login CSRF/open redirect. |
| **Token endpoint** | Code client/redirect/PKCE binding, client authentication. | Code rò đổi được thành tokens. |
| **OIDC validation** | ID token `iss`/`aud`/`exp`/`nonce`. | Session confused với issuer/user khác. |
| **Resource Server** | Token issuer/audience/scope/purpose, tenant/object policy. | Cross-service/cross-tenant misuse. |
| **Transport/proxy** | HTTPS, trusted forwarded headers, cookie policy, logs. | Host poisoning/leak/tampering. |
| **Token lifecycle** | TTL, refresh family, revoke/grants, sender binding khi yêu cầu. | Token đã lộ còn được replay. |
| **Security operations** | Telemetry, allowlist/redaction, anomaly response. | Phishing/redirect incident không được phát hiện. |

### 19.1. Tham số `next` không phải một OAuth security standard

`next`, `continue`, `returnUrl` thường là application-level convenience parameters. **Không chuyển chính sách security về redirect URI của AS sang việc “tin `next` của client”**. Chúng phải được allowlist trước và không tạo external navigation ngoài business policy.

### 19.2. Browser navigation là một ranh giới dữ liệu

Phản hồi `Location` làm browser rời origin; bất kỳ code/token/PII nào vô tình nằm trong URL có thể đi theo. Đối với API hoặc UI, dùng internal route IDs, controlled external links và không nhúng credentials vào redirect destination. Có `302 Found` không nghĩa AS/browser đã kiểm site đích là an toàn.

## 20. Ma trận kiểm thử phishing redirect và token safety

### 20.1. Test fixtures và ranh giới

~~~text
Trusted AS:
  https://login.test.example
Trusted web client:
  client_id = shop-bff
  registered redirect = https://shop.test.example/login/oauth2/code/company
Test user:
  user-test-742
Test scope and audience:
  scope = orders:read
  audience = orders-api
Other AS:
  https://login-other.test.example
Untrusted destination:
  https://landing.attacker.invalid

Data:
  random per-flow state, nonce, S256 code_verifier
  dummy OAuth codes and test tokens only
~~~

Sử dụng **test AS, test client registration, test keys và users giả lập**, không copy production codes, tokens, client secrets hoặc user credentials vào fixtures.

### 20.2. Redirect URI matching ở AS

| Thử nghiệm | Thao tác | Kết quả mong đợi |
|---|---|---|
| Redirect URI exact | `shop-bff` dùng đúng registered callback. | Authorization request tiếp tục theo grant/consent policy. |
| Callback host attacker | Thay `redirect_uri` bằng host ngoài registration. | AS reject, không phát code đến URI đó. |
| Host prefix trick | `shop.test.example.attacker.invalid`. | Reject. |
| Userinfo trick | `shop.test.example@attacker.invalid`. | Reject. |
| Prefix path | `/login/oauth2/code/company-extra`. | Reject nếu không registered chính xác. |
| Extra query redirect | URI đúng path nhưng thêm `next` không registered. | Reject theo exact-match policy. |
| Fragment | URI đăng ký/yêu cầu có `#token`. | Reject theo web redirect registration/profile. |
| HTTP downgrade | `http://shop.test.example/callback` ngoài policy. | Reject; ngoại lệ loopback native được xét riêng. |
| Unicode/trailing-dot host | Host nhìn tương tự hoặc có trailing dot. | Không tự normalize thành registered URI. |
| Percent-encoded host/path ambiguity | URI có encoding khác registration. | Reject nếu không exact, không lenient parse. |
| Wildcard callback | Thử `https://*.test.example`. | Không chấp nhận wildcard cho web client. |
| Invalid redirect error | AS nhận URI sai. | AS-controlled error, **không redirect lỗi về attacker**. |
| Stale callback domain | Domain cũ không thuộc tổ chức. | Registration review/removal; không để AS phát code. |
| Loopback dynamic port | Native RFC 8252 client đổi port hợp lệ. | Chấp nhận đúng ngoại lệ định nghĩa, vẫn kiểm host/path/client. |
| Native arbitrary callback | Port/host/path không thuộc profile. | Reject. |
| Client A callback cho client B | Đổi client ID hoặc URI. | Reject client–redirect association. |

### 20.3. Open redirect ở client và callback

| Thử nghiệm | Input/tình huống | Kết quả |
|---|---|---|
| Route ID known | `routeId=orders`. | Redirect internal `/orders`. |
| External URL | `routeId=https://attacker.invalid`. | Fallback safe path hoặc reject; không external redirect. |
| Protocol-relative | `next=//attacker.invalid`. | Không tạo `Location` ngoại domain. |
| Encoded protocol-relative | `next=%2F%2Fattacker.invalid`. | Không tạo external redirect. |
| Backslash/encoded separators | `next=\attacker.invalid`. | Không bypass URI policy. |
| CRLF/header injection | Encoded newline trong `next`. | Không tạo header injection, request bị reject/sanitize. |
| Unsafe return path in `state` | State metadata bị sửa. | Invalid state/integrity, safe controlled error. |
| Callback trước code exchange redirect ngoài | Handler nhận query attacker. | Không forward code/state/PII. |
| Missing state | Callback chỉ có code. | Reject, không login. |
| Wrong browser session | State thuộc session khác. | Reject. |
| Reused state | Callback bị gửi lại sau consume. | Reject một lần nữa, không tạo session mới. |
| Expired state | Callback sau TTL. | Reject, start new auth flow. |
| Parallel tabs | Hai auth transactions khác nhau. | State/PKCE/nonce không bị ghi đè. |
| Clean success redirect | Login thành công. | HTTP 303 tới internal route không chứa code/token. |
| Third-party resources callback | Callback page thử tải analytics. | Không phát code/token qua Referer; ideally callback không nhúng resources. |
| Browser URL/log leak | Kiểm AS/proxy/app/APM logs. | Không có raw code/state/token/PKCE verifier. |

### 20.4. PKCE, token endpoint và client authentication

| Thử nghiệm | Điều kiện | Kết quả |
|---|---|---|
| S256 đúng | Code gắn verifier. | Redeem đúng một lần, cấp token theo grant. |
| Wrong verifier | Gửi verifier khác. | Token endpoint reject. |
| Missing verifier | Client cần PKCE nhưng không gửi. | Reject. |
| Verifier reused từ transaction khác | Code của tab A, verifier tab B. | Reject. |
| Authorization code dùng hai lần | Redeem lần thứ hai. | Reject; audit code reuse. |
| Expired code | Token request sau TTL. | Reject. |
| Client mismatch | Code client A redeem bởi B. | Reject. |
| Redirect mismatch | Code bound callback A, token request callback B. | Reject theo protocol. |
| Confidential auth missing | Client phải auth nhưng không gửi. | Reject. |
| Public client secret in SPA | App bundle có hardcoded secret. | Security review/test fail. |
| Untrusted token endpoint | Client callback lấy token URL từ query. | Không gọi, dùng trusted registered endpoint. |
| Unsafe scope upgrade | Token request thêm scope không được grant. | Không cấp scope trái policy. |

### 20.5. OIDC issuer, nonce, session protection

| Thử nghiệm | Điều kiện | Kết quả |
|---|---|---|
| Valid issuer | ID token `iss` trùng OP đã chọn. | Tiếp tục validation các claims khác. |
| Wrong issuer | ID token từ AS khác. | Reject. |
| Wrong audience | `aud` ID token không chứa client ID hợp lệ. | Reject. |
| Wrong nonce | ID token `nonce` không khớp transaction. | Reject theo OIDC profile. |
| Missing nonce | Authentication request yêu cầu nonce. | Reject token khi thiếu. |
| Expired ID token | `exp` hết hiệu lực. | Reject. |
| AS mix-up response | Response issuer không khớp stored AS. | Reject, không gửi code tới endpoint sai. |
| AS token endpoint injection | Callback có `issuer=https://attacker.invalid`. | Ignore/reject input, trusted AS binding. |
| Session fixation | Session ID trước login được gán lại sau login. | Session rotation theo policy; không cho fixation. |
| Login CSRF | Callback của attacker transaction ở victim browser. | State/browser binding reject. |

### 20.6. Consent phishing và resource authorization

| Thử nghiệm | Điều kiện | Kết quả |
|---|---|---|
| Unverified client yêu cầu scope nhạy cảm | Client không được admin-approved. | AS từ chối hoặc yêu cầu approval theo policy. |
| Client name/logo mạo danh | Client registration cố giả publisher. | Verification/review phát hiện, không tin display name. |
| `offline_access` không được phép | Malicious client yêu cầu refresh capability. | Deny ngoài consent/client permissions. |
| User rút consent | Grant được revoke. | Refresh/token issuance bị chặn theo policy. |
| Stolen access token | Bearer được phát lại. | Revocation/sender binding/TTL hạn chế; RS luôn kiểm. |
| ID token gọi Orders API | Sai token purpose/audience. | Reject. |
| Access token sai audience | `aud=payments-api` gọi Orders. | Reject. |
| Access token thiếu scope | `orders:write` gọi read endpoint. | Reject. |
| Token đúng scope sai tenant | User Beta đọc Order Anpha. | Object-level ACL reject. |
| DPoP-bound token thiếu proof | No proof or wrong `ath`/key. | Reject. |
| mTLS-bound token sai certificate | Peer cert không match `cnf`. | Reject. |
| Refresh token gửi tới RS | Client dùng refresh token như Bearer. | Reject, không introspect như access credential. |

### 20.7. Proxy, deployment và monitoring

| Thử nghiệm | Input/sự cố | Kết quả |
|---|---|---|
| Forged `Host` | Public request khai host attacker. | External callback vẫn từ trusted config hoặc reject. |
| Forged `X-Forwarded-Host` | Public request khai forwarded host. | Proxy strips/overwrites; BFF không dùng untrusted value. |
| TLS termination | Header `X-Forwarded-Proto=http` bị giả. | Không tạo insecure callback, cookies đúng policy. |
| Callback domain DNS takeover | Domain đăng ký hết sở hữu. | Inventory/monitoring alert, registration bị gỡ. |
| Redirect registration change | Operator đổi host. | RBAC, approval/audit và domain ownership review. |
| Rejected URI storm | Nhiều unregistered callbacks. | Alert/rate limiting; logs không chứa secrets. |
| Client consent anomaly | Client mới có nhiều grants nhạy cảm. | Alert, triage publisher/approval. |
| Unexpected PKCE failure spike | Sai verifier sau deploy. | Detection phân biệt bug vs interception. |
| Safe incident log | Token/code nằm trong HTTP header/query. | Redaction/secret scanner fail nếu raw value xuất hiện. |
| Cross-origin callback script | Third-party script chạy trên callback. | Security test tìm và chặn risky resources. |

### 20.8. Pseudocode test các ràng buộc quan trọng

~~~text
test "authorization server rejects unregistered redirect":
    registered = "https://shop.test.example/login/oauth2/code/company"
    attackerUri = "https://landing.attacker.invalid/callback"

    response = testAS.authorize(
        clientId="shop-bff",
        redirectUri=attackerUri,
        pkceChallenge=testChallenge,
        state=testState
    )
    assert response.didNotIssueAuthorizationCode()
    assert response.didNotRedirectTo(attackerUri)

test "callback consumes exact state and keeps user on app":
    tx = client.startLogin(browserSession="S1", returnRouteId="orders")
    callback = testAS.issueTestCode(tx)
    response = client.handleCallback(
        session="S1",
        code=callback.code,
        state=tx.state
    )
    assert response.redirectLocation == "/orders"
    assert response.redirectLocation not contains callback.code
    assert client.rejectsRepeatedCallback(tx.state)

test "wrong browser session cannot consume callback":
    tx = client.startLogin(browserSession="S1", returnRouteId="orders")
    assert client.rejectsCallback(
        browserSession="S2",
        state=tx.state,
        code=testCode
    )

test "audience and object ACL survive valid OAuth login":
    token = AS.issueToken(client="shop-bff", audience="orders-api",
                          scope="orders:read", sub="user-beta")
    assert ordersRS.rejectsReadOfAnphaTenantOrder(token)
    assert paymentsRS.rejects(token)
~~~

**Pseudocode không chạy nguyên văn.** Integration tests phải dùng AS/client/RS test deployment, test keys và token dummy; không dùng production code/token, không gửi payload thử tới hệ thống ngoài phạm vi cho phép.

## 21. Ứng cứu sự cố: khi xuất hiện phishing redirect

### 21.1. Cần phân loại đúng trước khi hành động

SOC nhận báo cáo một liên kết “SSO session expired” bắt đầu từ domain ứng dụng nhưng kết thúc tại domain đăng nhập khác. Gần thời gian đó, AS log nhiều `redirect_uri` rejections và có vài consent grants cho clients mới.

**Không đủ căn cứ để kết luận mọi user đã mất password hoặc attacker đã đổi mọi code thành tokens.** Điều tra cần phân biệt:

- **Fake login page:** user có thể nhập password/MFA vào site giả.
- **Open redirect at client:** host hợp pháp làm trung gian cho phishing link.
- **AS redirect URI vulnerability:** authorization code có thể được gửi sai host.
- **OAuth consent phishing:** AS thật cấp quyền cho malicious client.
- **Callback leak:** code/token xuất hiện trong logs/Referer/browser.
- **Login CSRF/AS mix-up:** callback gắn sai transaction hoặc issuer.

Một campaign có thể kết hợp nhiều kỹ thuật; đánh giá nguồn bằng chứng và blast radius riêng.

### 21.2. Playbook phòng thủ

1. **Triage:** nhận incident ID, URL patterns đã redact, timestamps, reports và nguồn cần xác minh; đừng khuyến khích người dùng mở lại phishing URL hoặc gửi passwords.
2. **Xác minh source/destination:** trusted AS/client origins, final browser origin, DNS ownership và redirect chain bằng công cụ/môi trường điều tra được phép.
3. **Kiểm AS:** client registration, allowed redirect URIs, changes, exact-match rejections, code issuance và token exchange results.
4. **Kiểm callback:** `state`/PKCE/nonce/issuer failures, returnUrl/next redirects, Host/Forwarded handling, proxy logs đã redaction.
5. **Định lượng tác động:** những users đã click, authenticate, consent, codes đã cấp/đổi, access/refresh tokens đã cấp, API resources đã truy cập.
6. **Contain redirect:** chặn open redirect route, loại callback host không sở hữu, cập nhật safe return routes, vô hiệu malicious links/domain theo chính sách.
7. **Contain OAuth grants:** revoke consent/grants/refresh families/tokens khi có bằng chứng; disable/unregister malicious client nếu thích hợp.
8. **Account recovery:** với users nhập credentials, xử lý password/MFA/passkey, revoke sessions và đánh giá login/token use.
9. **Kiểm Resource Servers:** audience/scope/tenant, sender-binding enforcement, suspicious access và token revocation propagation.
10. **Bảo tồn evidence:** giữ provider audit, AS/client logs, DNS/client-registration history và affected-grant IDs ở kho có RBAC/retention.
11. **Khắc phục root cause:** registration exact match, state/PKCE/nonce/issuer checks, route ID allowlist, trusted proxies, consent governance.
12. **Post-incident:** bổ sung negative tests, log redaction checks, attack-surface inventory và metrics time-to-detect/time-to-revoke.

### 21.3. Blast radius theo loại tài sản bị lộ

| Bằng chứng | Vùng ảnh hưởng | Hành động thường xem xét |
|---|---|---|
| User nhập password ở AS giả. | Account/login sessions, grants. | Account recovery, revoke active sessions, audit authentication. |
| Code đã được redirect đến unregistered host. | Authorization transaction/client, code lifetime. | Fix AS config, invalidate transaction, kiểm PKCE/client auth/code redemption. |
| Access token xuất hiện trong proxy log. | Audience/scope/TTL của token, log readers. | Redact, restrict logs, revoke token theo incident policy. |
| Refresh token bị lấy. | Token family/grant, future access tokens. | Revoke family, reuse detection, client binding. |
| Malicious client được consent. | Approved scopes/grants của client, possibly offline access. | Revoke grants/client, review API access. |
| AS private signing key lộ. | Mọi RS trust key có khả năng nhận token giả. | Emergency trust cutoff/key replacement, reissue. |
| Callback hostname bị takeover. | Mọi client registrations trỏ host đó. | Remove callbacks, recover domain, review issuance. |

### 21.4. Code rò không đồng nghĩa token đã bị redeem

Một code có thể tới host không đáng tin nhưng vẫn **không redeem được** nếu PKCE/client authentication/code/redirect binding được thực thi. Dựa trên token endpoint results, code consumption, AS grants và logs để xác định đã cấp tokens hay chưa. Không gọi code “vô hại” vì attacker vẫn có thể khai thác phishing/combined vulnerabilities.

### 21.5. Evidence an toàn

Cần ưu tiên **event IDs và internal refs**, không raw credentials:

- AS authorization requests accepted/rejected và registration changes.
- Code issuance/consumption status, **không raw code**.
- `state`/PKCE/issuer/nonce failure categories, **không raw verifier/nonce**.
- Callback/proxy access event đã scrub query/token values.
- OAuth client consent and scope/resource grants.
- Token/grant revocation events, API access/authorization decisions.
- DNS/certificate/domain ownership history, owner/change records.

Original evidence có thể chứa dữ liệu nhạy cảm: giữ ở restricted storage, audit forensic access và chain of custody theo policy. Không copy authorization URLs chứa code/token vào email/ticket công khai.

### 21.6. Không tắt bảo vệ để chữa outage

Nếu một deployment làm `state` hoặc PKCE fail hàng loạt, **không tắt chúng** để login “chạy lại”. Rollback về cấu hình/callback đã được trust, sửa SameSite cookie/proxy/transaction race và test lại. Nếu issuer signing key thực sự lộ, xử lý emergency cutoff thay vì giữ key cũ chỉ vì sợ nhiều 401.

## 22. Bài tập tình huống và đáp án

### 22.1. Link bắt đầu bằng host thật

Một email có URL `https://app.example.com/leave?next=https://signin-example.security-check.invalid`. Người dùng tin vì URL bắt đầu bằng `app.example.com`.

**Đáp án:** Endpoint `/leave` có thể là open redirector. Phải xem **điểm đến cuối cùng**, không chỉ host trung gian. Ứng dụng dùng route ID/internal path allowlist và xử lý phishing origin theo policy.

### 22.2. Callback host chỉ giống tiền tố

Client đã đăng ký `https://app.example.com/oauth/callback`, request dùng `https://app.example.com.attacker.invalid/oauth/callback`.

**Đáp án:** AS phải từ chối: hostname không đúng registration. `startsWith` và `contains` không đủ. Không phát code hoặc redirect OAuth error đến URL invalid; dùng AS-controlled error page.

### 22.3. Client nhận code mà không kiểm `state`

Ứng dụng nhận callback `code` và đổi token dù browser/session chưa tạo transaction tương ứng.

**Đáp án:** Có nguy cơ login CSRF/session swapping. State phải random, bound session/transaction, có expiry và dùng một lần. PKCE/nonce/issuer là lớp bổ sung, không thay state.

### 22.4. PKCE có chặn được login phishing không?

SPA dùng `code_challenge_method=S256`, nhưng user nhập password trên site SSO giả.

**Đáp án:** PKCE giúp chống đổi authorization code bị chặn khi attacker không có verifier; nó không ngăn user gửi password vào fake origin. Cần trusted login origin, phishing-resistant MFA/passkeys khi phù hợp và xử lý phishing redirect.

### 22.5. Code A với verifier B

Token endpoint nhận authorization code của transaction A nhưng `code_verifier` thuộc transaction B.

**Đáp án:** AS phải reject. PKCE bind verifier với đúng code/challenge; đây là negative test thiết yếu cùng code single-use, expiry và client/redirect URI binding.

### 22.6. `state` đúng nhưng issuer sai

Multi-AS client có state đúng, nhưng callback query điều khiển client chọn token endpoint khác với AS đã khởi tạo.

**Đáp án:** Có AS mix-up. State phải bind trusted issuer/client registration/token endpoint; kiểm issuer identification (RFC 9207) và OIDC ID token `iss`/`aud`/`nonce` theo profile. Không tin query chọn issuer.

### 22.7. AS thật cấp token cho client lừa đảo

Client mới có tên “Company HR Official” yêu cầu `files.read`, `profile.read` và `offline_access`; user bấm consent trên AS thật.

**Đáp án:** Đây có thể là consent phishing. Exact redirect URI và PKCE vẫn đúng. Cần publisher/client verification, admin consent/high-risk scope policy, review grant/refresh tokens và revoke malicious grants/client khi cần.

### 22.8. `next=//attacker.invalid`

Ứng dụng chấp nhận mọi `next` bắt đầu bằng `/` vì cho rằng relative path.

**Đáp án:** `//attacker.invalid` có thể được browser hiểu là network-path reference dẫn ra ngoài origin. Chỉ dùng server-owned route ID → internal path hoặc strict normalization/allowlist với tests encoding/backslashes.

### 22.9. Analytics nhận code từ callback

Callback page tải third-party analytics trước khi xử lý `code` và gửi pageview URL.

**Đáp án:** Đây là credential exposure. Loại third-party resources khỏi callback, dùng no-store/referrer policy, server-side exchange khi phù hợp, clean redirect URL và redaction logs; điều tra code redemption/token issuance.

### 22.10. Native loopback port thay đổi

Một native app dùng redirect `http://127.0.0.1:54123/oauth2redirect/app` hôm nay, port khác ngày mai.

**Đáp án:** RFC 8252 có ngoại lệ cho **dynamic loopback port** trong điều kiện profile native app. Vẫn kiểm đúng client, loopback host/path, state, PKCE; không dùng ngoại lệ wildcard cho web callback.

### 22.11. Reverse proxy tin `X-Forwarded-Host` từ public request

BFF suy callback `{baseUrl}` từ header do caller tự đưa.

**Đáp án:** Host-header/callback-origin injection risk. Proxy strip/overwrite headers, app dùng trusted external base URL và exact registered callback, negative test forged Host/Forwarded.

### 22.12. Token đúng chữ ký nhưng sai audience

JWT access token `aud=orders-api` được gửi đến Payments API, nơi chỉ kiểm signature.

**Đáp án:** Payments phải reject: `aud` không dành cho resource. Cần `iss`, `aud`, `exp`, scope, token purpose và tenant/object authorization. Redirect security không thay resource policy.

### 22.13. JWE có ngăn attacker replay token không?

Attacker copy encrypted JWT Bearer từ proxy logs, không có private decryption key, rồi gửi lại nguyên token.

**Đáp án:** Không. Bearer ciphertext vẫn có thể được RS chấp nhận khi còn hạn. Cần TLS/redaction, TTL/audience, revoke, sender binding DPoP/mTLS đúng profile. Encryption che claims, không chứng minh sender.

### 22.14. Logout xóa cookie có thu hồi refresh token?

BFF xóa cookie session sau cảnh báo phishing, nhưng refresh family ở AS còn active.

**Đáp án:** Không mặc định. Cookie session, access token, refresh token/grant và consent có lifecycle khác nhau. Cần revoke family/grants khi có risk; rotate issuer JWT signing key không tự thu hồi refresh state.

### 22.15. `form_post` có thay `state` được không?

Client dùng OIDC `response_mode=form_post` rồi bỏ session-bound state validation.

**Đáp án:** Sai. POST có thể giảm một số URL leakage nhưng callback vẫn cần transaction binding, PKCE, nonce/issuer validation và cookie/CSRF protections.

### 22.16. Code lộ nhưng AS đã từ chối redemption

Điều tra thấy AS redirect code về host không registered, nhưng token endpoint từ chối tất cả requests thiếu đúng PKCE verifier.

**Đáp án:** Không tuyên bố attacker có access token khi chưa có evidence issuance; nhưng AS vẫn có **lỗ hổng redirect URI** và trang đích có thể phishing. Phân loại root cause, khắc phục registration, kiểm code/client bindings và các báo cáo người dùng.

## 23. Checklist phòng chống phishing redirect

### 23.1. Authorization Server và client registration

- [ ] Trusted AS/OP issuers và client registrations được quản lý riêng theo environment.
- [ ] AS kiểm **exact registered redirect URI** theo OAuth Security BCP; không dùng prefix, substring hoặc wildcard cho web callbacks.
- [ ] Native loopback dynamic-port exception chỉ dùng theo RFC 8252, không mở wildcard host/path.
- [ ] Web redirect URI dùng HTTPS và không có fragment; callback domain còn thuộc quyền kiểm soát.
- [ ] Invalid redirect URI bị từ chối **không redirect OAuth error hoặc code** tới URI đó.
- [ ] Code gắn với client, redirect URI, PKCE và grant, ngắn hạn/dùng một lần.
- [ ] Authorization Code Flow dùng PKCE S256 theo security policy; token endpoint reject wrong/missing verifier.
- [ ] Client authentication áp đúng registration, không nhúng confidential secret trong SPA/mobile.
- [ ] Scope/resource/consent được AS kiểm trước khi cấp code/token.
- [ ] Thay registered redirect URI có RBAC, domain ownership verification, audit và stale-URI cleanup.
- [ ] PAR/JAR được xem xét nếu profile đòi request integrity, không thay redirect registration hoặc state/PKCE.

### 23.2. Client callback, transaction và browser

- [ ] Mỗi authorization attempt có random `state` riêng, bound browser session/transaction, TTL và one-time consume.
- [ ] Missing/reused/mismatched `state` khiến callback bị từ chối, không silently create session.
- [ ] Parallel tab logins không dùng một global `lastState`/`lastCodeVerifier`.
- [ ] OIDC `nonce` được kiểm trong ID token cùng `iss`/`aud`/`exp` theo profile.
- [ ] Multi-AS transaction bind issuer/token endpoint/client registration, kiểm issuer theo RFC 9207 khi áp dụng.
- [ ] Callback không lấy issuer/token endpoint/redirect URI từ query chưa đáng tin.
- [ ] Callback dùng server-side code exchange nếu phù hợp; không redirect đi ngoài trước khi xử lý code/state.
- [ ] Return destination dựa vào **route ID/internal path allowlist**, không phản chiếu raw `next`/`returnUrl`.
- [ ] `//host`, encoded slash, backslash, URL parser ambiguity và CRLF/header injection bị kiểm/reject.
- [ ] State/transaction chứa safe return path có integrity và session binding.
- [ ] Sau login có clean internal redirect, không đưa code/state/access/refresh token vào `Location`.
- [ ] Session rotation/fixation defense, cookie `HttpOnly`/`Secure`/`SameSite` và CSRF controls đã test.
- [ ] Callback có no-store/referrer policy phù hợp, tránh third-party resources/analytics.
- [ ] Gateway/proxy/APM không ghi raw code, state, verifier, Authorization, Cookie hoặc token response.

### 23.3. Hạ tầng, SPA/native apps và quyền API

- [ ] External base URL dùng trusted deployment config; không phụ thuộc untrusted Host/Forwarded headers.
- [ ] Proxy strip/overwrite forwarded headers từ public callers; kiểm HTTPS termination và cookies.
- [ ] Không giữ callback trên subdomain/CNAME không còn kiểm soát.
- [ ] Native apps dùng external user agent/PKCE và claimed HTTPS/app links khi platform phù hợp.
- [ ] Custom URI schemes được threat-model interception; link association/intent filters đã test.
- [ ] SPA/mobile không chứa client secret; browser XSS/token storage risk đã đánh giá; BFF khi phù hợp.
- [ ] OAuth client display name, publisher, scopes và consent permissions được review theo risk.
- [ ] `offline_access`/refresh token grant không tự cấp cho untrusted client.
- [ ] Có cơ chế revoke consent/client/grants/refresh family khi phát hiện malicious app.
- [ ] RS kiểm issuer, audience, expiry, scope, token purpose, tenant/object policy sau khi token được cấp.
- [ ] OIDC ID token, authorization code và refresh token không được dùng thay access token tại RS.
- [ ] DPoP/mTLS token binding được RS verify khi có, không coi nó thay redirect controls.

### 23.4. Kiểm thử và vận hành

- [ ] Có negative tests redirect URI: prefix host, userinfo, wrong path/query, fragment, HTTP downgrade, Unicode, native exceptions.
- [ ] Có tests open redirect: arbitrary external URL, protocol-relative, encoded separators, unsafe `state` return.
- [ ] Có tests state/PKCE/nonce/issuer: missing, wrong, reused, expired, cross-session và parallel tabs.
- [ ] Có tests forged Host/Forwarded headers và client registration/domain ownership changes.
- [ ] Có tests consent phishing policy, dangerous scopes, malicious/renamed client và grant revocation.
- [ ] Có tests callback log/referrer leakage, token theft/replay, audience/scope/tenant/ACL and token purpose.
- [ ] Có monitoring invalid redirect URI, unusual consent, state/PKCE/issuer mismatch và callback DNS changes.
- [ ] SOC/on-call có playbook phân biệt fake login, open redirect, code-only leakage, malicious consent và signing-key compromise.
- [ ] Bằng chứng điều tra được giữ có RBAC/retention, không gửi raw credentials vào ticket/chat.
- [ ] Không tắt state/PKCE/issuer checks hoặc chấp nhận invalid redirect để khắc phục lỗi login tạm thời.

**Ghi nhớ:** *Phishing redirect* có thể là link giả mạo đi qua domain thật, open redirect ở client, AS chấp nhận callback sai, hoặc consent phishing trên **AS thật**. Để phòng vệ, cần **exact redirect registration, state bound với phiên, PKCE S256, OIDC nonce, trusted issuer, consent governance, callback không rò credential và token lifecycle controls**. Đánh giá tác động theo đúng loại tài sản bị lộ: **authorization code, access token, refresh token, account credentials hay issuer key**, thay vì coi chúng là một.

## 24. Tài liệu chuẩn và tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** roles, authorization endpoint, redirect URI, authorization code và token endpoint.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** exact redirect matching, PKCE, front-channel risks, mix-up và token replay.
- **RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients (PKCE):** S256, code challenge/verifier và chống code interception.
- **RFC 8252 — OAuth 2.0 for Native Apps:** external user agent, loopback port, claimed HTTPS và private-use URI schemes.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification:** issuer trong authorization response và mix-up defense.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata:** trusted issuer/endpoint metadata.
- **RFC 9126 — OAuth 2.0 Pushed Authorization Requests (PAR):** request parameter integrity/hardening theo profile.
- **RFC 9101 — The OAuth 2.0 Authorization Framework: JWT-Secured Authorization Request (JAR):** authenticated/protected request objects.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** resource/audience restriction khi xin token.
- **RFC 7009 — OAuth 2.0 Token Revocation:** revoke tokens/grants và lifecycle khác logout.
- **RFC 7662 — OAuth 2.0 Token Introspection:** opaque token state và authorized Resource Server checks.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** bearer credential protection, replay và HTTP error behavior.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** issuer/audience/scope/purpose validation.
- **RFC 8725 — JSON Web Token Best Current Practices:** issuer/key trust, token substitution/algorithm confusion.
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `aud`, `exp`, `nbf` và claims.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** mTLS sender binding.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** proof signature, `ath`/`htu`/`htm` và replay checks.
- **RFC 8693 — OAuth 2.0 Token Exchange:** delegation, audience-specific/downstream tokens.
- **OpenID Connect Core 1.0:** Authorization Code Flow, ID token issuer/audience/nonce, login/session binding.
- **OpenID Connect Discovery 1.0:** trusted OP configuration and issuer metadata.
- **NIST SP 800-63B — Digital Identity Guidelines: Authentication and Lifecycle Management:** phishing-resistant authentication controls.
- **OWASP Unvalidated Redirects and Forwards Cheat Sheet:** safe redirects, destination allowlists và open redirect prevention.
- **OWASP OAuth 2.0 Cheat Sheet:** OAuth client/AS checks, PKCE, redirects và token lifecycle.
- **OWASP CSRF Prevention Cheat Sheet:** session binding và CSRF defense.
- **OWASP Authentication Cheat Sheet / Session Management Cheat Sheet:** secure login, phishing resistance, session fixation và cookies.
- **OWASP JSON Web Token Cheat Sheet:** JWT token purpose, validation, storage và replay risks.
- **OWASP API Security Top 10 — Broken Object Level Authorization:** object/tenant authorization không được bỏ qua sau token validation.
- **Spring Security Reference — OAuth2 Login/OAuth2 Client:** client registration, authorization request handling, callback và success handlers.
- **Spring Security Reference — OAuth2 Resource Server JWT/Opaque Token:** issuer/JWKS/introspection, scope/audience policies.
- **Spring Authorization Server Reference:** redirect URI registration, token issuance, grants và OAuth/OIDC configuration.








