# Đăng nhập liên kết với SameSite, redirect và các token giao thức

## Mục tiêu học tập

Sau bài học trong chương **Tích hợp ứng dụng** thuộc module **SPRING_SECURITY_HTTP_PROTECTION**, người học có thể:

- Giải thích đăng nhập liên kết (*federated login*) khi ứng dụng Spring Security sử dụng **OAuth 2.0 Authorization Code** và **OpenID Connect (OIDC)** với Identity Provider (IdP), và phân biệt với việc ứng dụng tự xác thực username/password.
- Đọc được đường đi của **redirect** từ ứng dụng đến IdP và callback trở về; xác định lúc nào browser gửi/không gửi session cookie theo **`SameSite=Strict`, `Lax`, `None; Secure`**.
- Phân biệt **origin** với **site**, cross-origin với cross-site, **top-level navigation** với iframe/fetch và **GET callback `response_mode=query`** với **POST callback `response_mode=form_post`**.
- Giải thích mục đích và khả năng bảo vệ khác nhau của **OAuth `state`**, **OIDC `nonce`**, **PKCE `code_verifier/code_challenge`**, **authorization code**, **ID token**, **access token**, **refresh token** và **CSRF token** của Spring Security.
- Cấu hình **`oauth2Login()`, `ClientRegistration`, callback URI, HttpSession/WebSession**, login/logout và CSRF cho **Servlet/Spring MVC** lẫn **Reactive/WebFlux**.
- Chẩn đoán `authorization_request_not_found`, state mismatch, correlation/session lost, invalid redirect URI, cookie blocked, invalid issuer/audience/nonce, login loop và xung đột CORS/CSP/HSTS tại reverse proxy.
- Thiết kế đăng xuất an toàn gồm **local logout**, **OIDC RP-initiated logout** và phân biệt **front-channel/back-channel logout** khi nhà cung cấp hỗ trợ.
- Đánh giá kịch bản SAML POST binding và các rủi ro tương tự về SameSite/CSRF, đồng thời **không đánh đồng SAML RelayState với OAuth state**.
- Kiểm thử bằng **MockMvc**, **WebTestClient**, HTTP integration với IdP thử nghiệm và browser E2E để xác minh cả token giao thức lẫn cookie policy thực tế.

## 1. Đăng nhập liên kết thay đổi ranh giới tin cậy ở đâu?

Trong form login nội bộ, browser thường gửi credentials tới chính ứng dụng. Với đăng nhập liên kết, ứng dụng dựa vào một **Identity Provider/Authorization Server** bên ngoài để xác thực người dùng, sau đó tạo phiên đăng nhập cục bộ sau khi **kiểm tra phản hồi giao thức**.

Ví dụ:

~~~text
Ứng dụng/Relying Party (RP): https://app.example.com
Identity Provider (IdP):      https://login.identity.example
Browser của người dùng:       trình duyệt có cookie jar riêng cho mỗi site
~~~

Người dùng bấm “Đăng nhập qua công ty” tại `app.example.com`. Browser chuyển tới `login.identity.example`, đăng nhập tại IdP, rồi trở về **callback** của app. Mỗi bước đi qua một site/origin khác nhau, và browser quyết định gửi cookie nào dựa trên domain, path, `Secure`, `SameSite` và chính sách ngăn cookie bên thứ ba.

~~~mermaid
flowchart LR
    U[Người dùng] --> B[Browser]
    B -->|GET bắt đầu login| RP[Spring app - RP]
    RP -->|302 redirect| B
    B -->|Top-level GET| IDP[Identity Provider]
    IDP -->|302 callback với code + state| B
    B -->|GET callback + app session cookie nếu hợp policy| RP
    RP -->|POST token endpoint backend-to-backend| IDP
    RP -->|Tạo phiên đã đăng nhập sau validation| B
~~~

**Lớp phòng vệ không được bỏ qua** chỉ vì IdP đã xác thực user:

1. RP phải biết response đến từ **authorization request chính nó đã khởi tạo**.
2. RP phải liên kết response đúng với **session/browser instance**, không nhầm người dùng hoặc provider.
3. RP phải xác minh các token/claims theo giao thức.
4. RP phải thiết lập phiên application mới và kiểm soát cookie, CSRF, logout, authorization.
5. Redirect và các header/proxy phải dẫn đến **đúng URI đã đăng ký**, không cho attacker lựa chọn tùy ý.

**Spring Security OAuth2 Login** giúp thực thi nhiều bước giao thức, nhưng developer vẫn phải chọn policy cookie, trusted provider, scopes, callback, proxy config và authorization theo vai trò/tenant phù hợp.

## 2. Các vai trò: RP, Authorization Server, browser và Resource Server

| Vai trò | Chức năng | Ranh giới bảo mật |
|---|---|---|
| **End user** | Quyết định đăng nhập | Không nên nhập mật khẩu ứng dụng vào form giả mạo IdP |
| **Browser/user agent** | Theo redirect, giữ cookie, áp SameSite/CORS/CSP | Cookie RP có thể bị loại trên cross-site callback |
| **Relying Party/OIDC Client** | Tạo authorization request, lưu state/nonce, trao đổi code, tạo session ứng dụng | Không tin callback nếu không có correlation/validation |
| **Authorization Server/IdP** | Xác thực user, phát code/tokens, publish metadata/JWKs | Phải được RP tin cậy qua issuer/keys/client registration |
| **Resource Server** | Xác minh access token cho API | Không được nhận ID token như access token không phù hợp |
| **Reverse proxy/ingress** | TLS, public host/scheme, routing, cookies/headers | Không để forwarded headers không tin cậy làm sai callback URL |

Trong bài này, kịch bản chính là **server-side Spring OAuth2 Login**: RP nhận authorization code rồi gọi token endpoint **từ backend**, tạo **session cookie của ứng dụng** cho browser. Nó khác **SPA tự là public OAuth client**, tự thực hiện code+PKCE và sử dụng access token để gọi API.

### 2.1. ID token không phải session cookie

OIDC ID token xác nhận một sự kiện authentication và các claims về chủ thể cho OIDC Client. Nó được RP kiểm tra theo **issuer, audience/client ID, timestamps, nonce khi áp dụng, chữ ký/JWK/thuật toán**. Sau đó Spring có thể thiết lập **SecurityContext trong phiên web** và browser nhận `JSESSIONID`/`SESSION`.

- **ID token**: do IdP phát, RP xác minh.
- **Access token**: dùng để gọi protected resources theo audience/scope, không phải mặc định dùng cho login API của riêng RP.
- **Session ID**: cookie của RP, browser tự gửi để khôi phục authentication.
- **Refresh token**: xin access token mới theo policy của provider; không đưa trực tiếp vào browser một cách tùy tiện.

Do đó **OIDC login thành công không làm browser session tự miễn CSRF**: các POST/PUT/PATCH/DELETE của RP vẫn cần anti-CSRF khi dùng session cookie.

## 3. Toàn bộ Authorization Code + OIDC flow

Giả định ứng dụng dùng authorization code flow với OIDC scope `openid`; provider hỗ trợ PKCE. Trình tự:

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant RP as Spring Security RP
    participant IDP as OIDC Provider

    U->>B: Bấm Đăng nhập qua công ty
    B->>RP: GET /oauth2/authorization/corporate
    RP->>RP: Tạo state, (nonce OIDC), PKCE nếu cấu hình
    RP->>RP: Lưu authorization request liên kết session
    RP-->>B: 302 Location: provider/authorize?...state=...
    B->>IDP: Top-level GET /authorize
    IDP->>IDP: Xác thực user, xin consent nếu cần
    IDP-->>B: 302 về /login/oauth2/code/corporate?code=...&state=...
    B->>RP: GET callback + cookie RP khi SameSite cho phép
    RP->>RP: Lấy expected request từ session, so state
    RP->>IDP: POST token endpoint + code + client authentication + PKCE verifier
    IDP-->>RP: ID token, access token, metadata theo flow
    RP->>RP: Kiểm tra token/nonce/issuer/audience/times
    RP->>RP: Tạo authentication, session fixation protection
    RP-->>B: 302 tới trang nội bộ + session cookie
    B->>RP: GET /dashboard với phiên đã xác thực
~~~

### 3.1. Khởi tạo đăng nhập

Spring Security Servlet mặc định có đường **authorization request** kiểu:

~~~http
GET /oauth2/authorization/corporate HTTP/1.1
Host: app.example.com
~~~

`corporate` là `registrationId` của một `ClientRegistration` tin cậy. Spring tạo một authorization request chứa `client_id`, `redirect_uri`, `response_type=code`, scope, state và các tham số provider cần thiết.

**Không tự dựng URL provider từ user input không có allowlist**. Nếu hỗ trợ nhiều provider, chỉ cho chọn registration IDs đã cấu hình và hiển thị nhãn rõ ràng để giảm nhầm IdP.

### 3.2. Redirect qua provider

Response có thể trông như:

~~~http
HTTP/1.1 302 Found
Location: https://login.identity.example/oauth2/authorize?response_type=code&client_id=app-web&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fcorporate&scope=openid%20profile&state=RANDOM_STATE
Cache-Control: no-store
~~~

`state` là giá trị khó đoán; **không dùng ví dụ `RANDOM_STATE` trong thực tế**. Không in toàn bộ query authorization URL vào logs nếu chứa các giá trị giao thức nhạy cảm, và bảo vệ code challenge/nonce theo chính sách logging.

### 3.3. Browser callback

Với authorization code và response mode `query`, IdP có thể redirect browser về:

~~~http
GET /login/oauth2/code/corporate?code=ONE_TIME_CODE&state=RANDOM_STATE HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=PRE_LOGIN_SESSION
~~~

RP tra lại **expected authorization request** trong session/correlation storage, đối chiếu state và các thông tin liên quan. Nếu cookie RP không được browser gửi, Spring có thể **không tìm lại authorization request** dù query có code/state trông hợp lệ.

### 3.4. Code exchange không cần browser CORS

Với server-side Spring OAuth2 Login, backend RP gửi HTTPS POST tới token endpoint. Đây là **server-to-server** request:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.identity.example
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=ONE_TIME_CODE&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fcorporate&code_verifier=STORED_VERIFIER
~~~

Client authentication (client secret, private_key_jwt, mTLS hoặc none) phụ thuộc `ClientRegistration`/provider. Ví dụ đã lược bỏ các chi tiết credential. **Token endpoint backend-to-backend không bị browser CORS chi phối**; không cần mở CORS ở IdP chỉ vì login server-side dùng redirect.

### 3.5. Callback thành công mới tạo phiên ứng dụng

Sau khi code exchange và token validation thành công, Spring Security tạo principal/authentication của ứng dụng. Session ID có thể được đổi để chống **session fixation**. Spring có thể điều hướng về saved request hoặc URL mặc định của app.

Không cho business controller tự coi `?code=...` là bằng chứng login, tự decode payload ID token mà không xác minh chữ ký/claims hoặc tự lưu `SecurityContext` thiếu lifecycle protections.

## 4. Origin, site và SameSite: ba khái niệm dễ nhầm

**Origin** gồm **scheme + hostname + port**. Hai URL sau là cross-origin vì hostname khác nhau:

~~~text
https://app.example.com
https://api.example.com
~~~

**Site** trong cách browser áp `SameSite` hiện đại thường là **schemeful site**: scheme và registrable domain (eTLD+1 theo Public Suffix List; với host đặc biệt có quy tắc tương ứng). Vì vậy hai origin trên vẫn có thể **same-site** nếu cùng HTTPS và thuộc cùng registrable domain.

Trong khi đó:

~~~text
https://app.example.com
https://login.identity.example
~~~

là **cross-site**. Đường redirect từ IdP về RP thuộc một **navigation cross-site**, dù callback sẽ hiển thị tài liệu tại origin RP.

### 4.1. Bảng phân loại

| A → B | Quan hệ origin | Quan hệ site | Ý nghĩa |
|---|---|---|---|
| `https://app.example.com` → `https://app.example.com` | Same-origin | Same-site | Cookie mặc định theo scope, không cần CORS |
| `https://app.example.com` → `https://api.example.com` | Cross-origin | Thường same-site | JavaScript fetch cần CORS; SameSite không cấm chỉ vì subdomain khác |
| `https://app.example.com` → `https://login.identity.example` | Cross-origin | Cross-site | IdP navigation và RP callback chịu chính sách SameSite tương ứng |
| `http://app.example.com` → `https://app.example.com` | Cross-origin | Cross-site theo schemeful site | HTTP→HTTPS có thể khác site dù cùng host |
| `https://app.example.com:443` → `https://app.example.com:8443` | Cross-origin | Same-site | Port đổi origin, không đổi site |

**Lưu ý:** Cookie `Domain`/`Path` có phạm vi riêng. `SameSite=Lax` không ép cookie của `app.example.com` tự gửi sang `api.example.com` nếu cookie là **host-only** cho app; mọi điều kiện scope vẫn phải đúng.

### 4.2. Top-level navigation khác fetch/iframe

- **Top-level navigation**: browser điều hướng tab/cửa sổ tới một URL, ví dụ HTTP 302 hoặc bấm link.
- **Subresource/fetch**: JavaScript từ trang A gọi API B, iframe tải document khác site, image/script request; thường bị chính sách cookie/cross-origin khác.
- **Form POST navigation**: browser submit HTML form, **không phải safe GET** dù nó có thể điều hướng cả tab.

Điều này quan trọng vì `SameSite=Lax` thông thường **cho cookie trên top-level cross-site navigation với safe method như GET**, nhưng **không** cho cookie trên cross-site POST form callback. `SameSite=Strict` chặt hơn; `SameSite=None` cần `Secure` và phụ thuộc browser privacy policy.

## 5. Ma trận SameSite cho OAuth/OIDC callback

Giả sử RP phát cookie `JSESSIONID` phù hợp `Domain`/`Path`/`Secure`, và IdP ở **site khác** quay lại RP:

| Cookie RP | GET callback top-level từ IdP | POST `form_post` callback từ IdP | Embedded iframe/subresource cross-site | Ghi chú |
|---|---|---|---|---|
| **`SameSite=Strict`** | Thường **không gửi** | Không gửi | Không gửi | Dễ mất correlation session ở callback |
| **`SameSite=Lax`** | **Có thể gửi** nếu scope/Secure hợp lệ | Thường **không gửi** | Thường không gửi | Phù hợp nhiều flow code+query redirect |
| **`SameSite=None; Secure`** | Có thể gửi | Có thể gửi | Có thể gửi nếu browser cho phép | Cần HTTPS; privacy/third-party cookie restrictions vẫn áp dụng |
| **Không đặt SameSite** | Tùy default/browser | Tùy default/browser; một số ngoại lệ tạm | Tùy browser | **Không dựa vào default khác nhau** |

Điều kiện “có thể gửi” còn phụ thuộc cookie `Domain`, `Path`, `Expires/Max-Age`, `Secure`, trình duyệt và cách navigation thật được kích hoạt. Không dùng một kết quả trên một bản Chrome làm kết luận cho mọi browser.

### 5.1. Code + query và `SameSite=Lax`

Nếu callback là top-level GET:

~~~text
IdP → 302 Location:
https://app.example.com/login/oauth2/code/corporate?code=...&state=...

Browser → GET tới app.example.com
  Cookie SameSite=Lax của RP có thể được gửi
  → Spring tìm authorization request đã lưu trong phiên
  → kiểm state và đổi code
~~~

Đây là lý do **Lax thường là lựa chọn tự nhiên** cho session cookie của RP khi dùng Authorization Code flow có query response và không phụ thuộc iframe.

### 5.2. Form POST callback và `SameSite=Lax`

Một IdP có thể trả một HTML form tự submit:

~~~html
<form method="post"
      action="https://app.example.com/login/oauth2/code/corporate">
  <input type="hidden" name="code" value="ONE_TIME_CODE">
  <input type="hidden" name="state" value="RANDOM_STATE">
</form>
<script>document.forms[0].submit()</script>
~~~

Form được gửi từ **site IdP** qua cross-site POST. Với `SameSite=Lax`, browser thông thường **không gửi session cookie của RP** trong cross-site unsafe POST, dẫn đến expected authorization request trong `HttpSession`/`WebSession` không được tìm thấy.

**Thay `Lax` thành `None; Secure` chưa phải toàn bộ giải pháp**: phải bảo đảm callback handler chấp nhận **POST form response**, CSRF filter không từ chối phản hồi giao thức hợp lệ, kiểm state/nonce/PKCE/issuer đầy đủ và đánh giá chính sách cookie browser. Không được bật `csrf.disable()` toàn bộ ứng dụng chỉ để form_post callback hoạt động.

### 5.3. Không dựa vào ngoại lệ “Lax + POST trong hai phút”

Một số browser có hành vi tương thích kiểu **Lax-by-default với ngoại lệ POST ngắn sau khi cookie vừa được tạo**, nhưng không phải cơ sở thiết kế đáng tin cậy cho explicit `SameSite=Lax` hoặc cho mọi browser/version. Khi login “lúc được lúc không”, xác minh cookie attributes/chính sách browser thật thay vì mặc định cơ chế ngoại lệ này ổn định.

### 5.4. SameSite=Strict cũng có thể ảnh hưởng post-login UX

`Strict` có thể ngăn cookie RP được gửi trong top-level navigation đến từ website khác, bao gồm OAuth callback, deep link hoặc một liên kết ngoài. Vì vậy chỉ tăng từ `Lax` lên `Strict` mà không kiểm kịch bản liên kết/SSO có thể gây login loop, lost saved request hoặc người dùng phải đăng nhập lại.

### 5.5. Cookie IdP và cookie RP là hai bộ độc lập

RP có cookie `JSESSIONID`/`SESSION`. IdP có cookie riêng cho phiên SSO tại **domain IdP**. Khi browser thực hiện top-level navigation đến IdP, IdP thường có thể dùng **first-party cookie context của chính nó**. Nhưng **silent login trong iframe** có thể bị browser chặn third-party cookie.

Không sửa `SameSite` của RP rồi cho rằng đã khắc phục mọi cookie bị chặn bên IdP/iframe.

## 6. Các token giao thức: state, nonce, PKCE, code, ID token và CSRF

Các chuỗi ngẫu nhiên có thể cùng xuất hiện trong một lần login nhưng **không thể dùng thay nhau**.

| Giá trị | Ai tạo? | Đi đâu? | Bảo vệ điều gì? |
|---|---|---|---|
| **OAuth `state`** | OAuth client/RP | Authorization request và callback | Ràng buộc authorization response với request **do client khởi tạo**; chống login CSRF/response injection |
| **OIDC `nonce`** | OIDC client/RP | Authorization request và `nonce` claim trong ID token theo flow | Ràng buộc ID token với authentication request, giảm replay/token substitution |
| **PKCE `code_verifier`** | Client | Lưu phía client; gửi **token endpoint** khi đổi code | Chứng minh bên đổi code biết verifier ứng với challenge đã gửi |
| **PKCE `code_challenge`** | Tính từ verifier | Authorization request | Gắn authorization code với verifier; ưu tiên `S256` |
| **Authorization code** | Authorization Server | Redirect callback rồi được đổi ở token endpoint | Quyền đổi lấy token **ngắn hạn, một lần**, không là API access token |
| **ID token (OIDC)** | IdP | Token response/flow OIDC | Claims authentication/user identity cho RP; phải validate |
| **Access token** | Authorization Server | RP/client gọi Resource Server | Quyền API, audience/scope/expiry; không thay ID token |
| **Refresh token** | Authorization Server | Token refresh endpoint theo policy | Lấy access token mới, phải bảo vệ storage/rotation |
| **Spring CSRF token** | RP/Spring Security | Hidden form field/header ở unsafe browser requests | Bảo vệ POST/PUT/PATCH/DELETE khi browser **tự gửi session cookie** |
| **SAML RelayState** | SP hoặc bên gửi flow | SAML request/response theo binding | Correlation/navigation theo SAML; cần đi cùng validation SAML signature/InResponseTo |

### 6.1. `state` là bằng chứng tương quan, không phải access token

Khi RP bắt đầu một lần đăng nhập, nó thường tạo state entropy cao và lưu authorization request liên kết với session/context. Callback phải mang state khớp đúng request đã lưu:

~~~text
RP session A:
  expected state = R_A
  client/provider = corporate
  redirect_uri = /login/oauth2/code/corporate

RP session B:
  expected state = R_B

Callback mang state R_A nhưng session B
  -> không có expected request phù hợp
  -> từ chối, không login nhầm theo response.
~~~

Không dùng một state cố định hoặc chỉ so `state` với query parameter khác do attacker cũng kiểm soát. Nếu viết custom repository, phải quản lý **single-use, expiry, binding tới browser/client/provider và replay**.

**Chỗ dễ nhầm:** OAuth state có tác dụng chống CSRF **trong authorization redirect/callback protocol**; nó không thay `_csrf` token trên `POST /web/profile` sau login khi browser đang dùng session cookie.

### 6.2. `nonce` bảo vệ ID token, không thay state

Trong OIDC, client có thể gửi một giá trị nonce trong authorization request. ID token phát ra chứa `nonce` phù hợp theo flow và validation contract. Client so nonce dự kiến với nonce trong ID token, cùng các điều kiện `iss`, `aud`, `exp`, `iat`/`auth_time` khi áp dụng, signature/JWKS và các claims bắt buộc khác.

`nonce` không phải secret để API dùng như Bearer header, không là session ID, không được đem đặt vào CSRF form field thay `_csrf`.

**OIDC vs OAuth:** Nếu chỉ thực hiện OAuth2 client flow không có scope `openid`, không mặc nhiên có ID token/nonce theo OIDC.

### 6.3. PKCE chống code interception và code injection theo điều kiện flow

Client tạo ngẫu nhiên:

~~~text
code_verifier = RANDOM_HIGH_ENTROPY_SECRET
code_challenge = BASE64URL(SHA256(code_verifier))
code_challenge_method = S256
~~~

Authorization request gửi `code_challenge`; token request gửi **`code_verifier`**. Authorization Server đối chiếu trước khi cấp token. Người biết **authorization code** mà không biết verifier tương ứng khó đổi được code.

PKCE đặc biệt quan trọng với **public clients** (SPA/native app); cũng là lớp tăng cường tốt cho confidential clients khi provider hỗ trợ. **PKCE không tự xác minh OIDC issuer/audience**, và không có nghĩa CSRF token sau login có thể bị tắt.

### 6.4. Authorization code có thể xuất hiện trong URL callback

Code trong query string của `response_mode=query` là phần thiết kế flow, nhưng vẫn phải:

- Có TTL ngắn, dùng một lần; issuer ràng buộc code với client/redirect URI và PKCE khi dùng.
- Dùng HTTPS và redirect URI chính xác; không chuyển code sang site ngoài hoặc thêm vào analytics/log.
- Đặt `Referrer-Policy` phù hợp, không chèn third-party script vào callback page có thể lấy URL.
- Không cấp access token/ID token trực tiếp qua URL query nếu flow không được thiết kế và bảo vệ tương ứng.
- Không trả chi tiết code, ID token hoặc refresh token trong error body, trace hay ticket hỗ trợ.

### 6.5. CSRF token của RP có vòng đời khác state

Với Spring Security session + form, `CsrfTokenRepository` quản lý expected token, browser gửi submitted token qua field/header. Sau authentication/logout, session và CSRF token có thể được làm mới hoặc xóa, nên **form mở từ trước login** có thể bị từ chối sau login.

Bảng đối chiếu:

| Trường hợp | Bằng chứng bắt buộc |
|---|---|
| Callback OAuth từ IdP | OAuth state + code/PKCE, OIDC token checks, correlation session |
| POST cập nhật hồ sơ của user | Session auth + Spring CSRF token + authorization |
| OAuth token endpoint | Client authentication + authorization code + PKCE verifier theo flow |
| M2M API Bearer-only | Bearer access token validation + scope/tenant authorization |
| SAML POST callback | SAML response signature, conditions, `InResponseTo`/RelayState theo binding, replay protection |
| OIDC logout callback | Validation tương ứng từng logout flow (state/id_token_hint/logout token, v.v.) |

## 7. Cookie session: thuộc tính nào làm flow thành công/thất bại?

### 7.1. Ví dụ cookie do RP phát

~~~http
Set-Cookie: JSESSIONID=opaque-random-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- **`Secure`:** cookie chỉ gửi qua ngữ cảnh HTTPS đủ điều kiện; yêu cầu production TLS end-to-end tới edge.
- **`HttpOnly`:** JS không thể đọc trực tiếp cookie, nhưng browser vẫn tự gửi; do đó không thay CSRF.
- **`SameSite=Lax`:** có thể cho callback top-level GET cross-site; chặn nhiều cross-site POST/iframe contexts.
- **`Domain`:** nếu không có Domain, cookie thường host-only; app callback phải về đúng host được cookie áp dụng.
- **`Path`:** callback `/login/oauth2/code/...` phải nằm trong cookie Path; cookie `Path=/web` sẽ **không** tới callback `/login/...`.
- **`Max-Age/Expires`:** cookie có thể hết hạn giữa khi user ở IdP và quay về RP.
- **Cookie name:** `JSESSIONID` thường trên Servlet; với WebFlux/Spring Session có thể là `SESSION` hoặc tên khác do resolver/serializer cấu hình.

### 7.2. Vì sao không bỏ `HttpOnly` để “debug login”?

State correlation thường nằm **phía server**, được tìm lại thông qua session ID mà browser gửi. JavaScript không cần đọc `JSESSIONID` để OAuth2 callback hoạt động. Nếu thiếu cookie callback, phải kiểm `SameSite`, `Domain`, `Path`, `Secure`, expiry, browser policy và public redirect URL, **không chuyển HttpOnly=false**.

### 7.3. Một callback sai host làm mất session

RP tạo authorization request tại `https://app.example.com` nhưng IdP được cấu hình callback tới `https://www.app.example.com`. Nếu cookie là **host-only** cho `app.example.com`, browser không gửi nó tới `www.app.example.com`, dù hai host có thể same-site.

Tương tự, callback sang HTTP `http://app.example.com` có thể không nhận cookie `Secure` và bị browser chặn/mixed policy. Sửa **public URL/redirect-uri/proxy forwarded host/scheme**, không mở Domain quá rộng một cách mặc định.

### 7.4. Cookie rotation sau login là hành vi bảo vệ

Session fixation protection có thể đổi session ID khi user chuyển từ anonymous/pre-login sang authenticated. Đừng so cookie ID “trước và sau login phải giống nhau” như một điều kiện pass. Thứ cần giữ là **authorization request được tìm lại trước khi xác thực**, sau đó **SecurityContext đã được lưu và cookie mới hoạt động**.

Kiểm tra logout phải xác minh session cũ không còn authenticated. Với nhiều tab, form có CSRF token cũ có thể trả `403`; không tắt CSRF để cho form cũ hoạt động.

### 7.5. Cookie SameSite không tự quyết định third-party cookie blocking

Một số browser chặn/partition third-party cookies trong iframe dù cookie được đặt `SameSite=None; Secure`. Top-level redirect flow thường chịu hạn chế khác so với silent authentication iframe.

Với SSO đa ứng dụng, phải kiểm cả:

- Top-level navigation đến IdP (phiên IdP khi là top-level site).
- Redirect callback về RP (cookie RP được phép trên GET/POST tùy SameSite).
- Silent token renewal/SSO check qua iframe (có thể bị chặn).
- Front-channel logout qua iframe (phụ thuộc cookie/context có thể không ổn định).

## 8. `response_mode=query` và `response_mode=form_post`

### 8.1. GET callback kiểu query

~~~http
HTTP/1.1 302 Found
Location: https://app.example.com/login/oauth2/code/corporate?code=C&state=S
~~~

Browser điều hướng **top-level GET** tới RP. Với cookie `SameSite=Lax` và scope hợp lệ, browser thường có thể gửi cookie của RP; Spring lấy lại authorization request từ session, kiểm state và trao đổi code.

**Không yêu cầu CORS ở callback**, vì đây là navigation, không phải JavaScript fetch từ IdP đọc response RP. Không cần “cho tất cả IdP origins vào CORS để redirect hoạt động”.

### 8.2. POST callback kiểu form_post

~~~http
POST /login/oauth2/code/corporate HTTP/1.1
Host: app.example.com
Content-Type: application/x-www-form-urlencoded
Origin: https://login.identity.example

code=C&state=S
~~~

Với RP cookie `SameSite=Lax`, browser thường không gửi session cookie trên **cross-site POST**. Nếu RP dùng session-backed authorization request, correlation bị mất.

Nếu IdP bắt buộc `form_post`, cần thiết kế đồng thời **ba** vấn đề:

1. **Cookie correlation**: lựa chọn `SameSite=None; Secure` có thể cần cho session cookie callback, hoặc triển khai một cơ chế correlation khác bảo mật tương đương theo kiến trúc.
2. **CSRF filter**: callback POST có thể bị Spring CSRF filter chặn trước khi OAuth2 handler chạy; cần cơ chế chấp nhận **chỉ callback protocol đã định nghĩa**, không disable CSRF rộng.
3. **Protocol handler**: phiên bản/client implementation phải hỗ trợ nhận code/state qua **POST form data** và validate state/nonce/PKCE. Đổi SameSite không tự bổ sung hỗ trợ `form_post` vào OAuth2 Login filter.

### 8.3. Nếu cần miễn CSRF ở callback POST, giới hạn chính xác

Ví dụ **mẫu matcher, chỉ áp nếu đã xác minh handler hỗ trợ form_post**:

~~~java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

RequestMatcher oidcPostCallback =
    new AntPathRequestMatcher(
        "/login/oauth2/code/corporate", "POST");

// Khi kết hợp với HttpSecurity:
// .csrf(csrf -> csrf.ignoringRequestMatchers(oidcPostCallback))
~~~

Đây là **đoạn minh họa lựa chọn điểm ngoại lệ**, không phải cấu hình hoàn chỉnh đủ để OAuth2 form_post hoạt động. Phải kiểm handler, supported response mode, method, content type, client registration, session correlation và token validation.

**Không làm:**

~~~java
.csrf(csrf -> csrf.disable())  // Sai khi app còn browser session forms
~~~

**Không làm:** `ignoringRequestMatchers("/login/**")` bao trùm mọi POST login/logout/browser endpoint. Chỉ những thông điệp được giao thức bảo vệ **thay thế bằng state và validation nghiêm ngặt** mới được xem là ngoại lệ thích hợp.

### 8.4. SAML POST binding: cùng vấn đề cookie nhưng giao thức khác

SAML2 Web Browser SSO thường dùng IdP POST SAML Response tới **Assertion Consumer Service (ACS)** của Service Provider. Nếu browser gửi cross-site POST và cookie SP là `SameSite=Lax`, SP có thể không lấy được state/request correlation trong session.

Với SAML, các kiểm chứng **không phải OIDC nonce/PKCE**:

- Chữ ký SAML Response/Assertion từ IdP được tin cậy;
- `Issuer`, `AudienceRestriction`, `Destination`, `Recipient`;
- `InResponseTo` với AuthnRequest đã gửi khi flow yêu cầu;
- `NotBefore/NotOnOrAfter`, replay cache/assertion ID;
- `RelayState` và SP-initiated correlation theo binding/policy.

SAML POST callback cũng có thể cần CSRF exception **hẹp** vì một SAML Response hợp lệ có xác minh giao thức riêng. Spring Security SAML2 login cần endpoint/filter phù hợp, **không dùng OAuth2 state repository để kiểm SAML**. Nếu ứng dụng chỉ dùng OIDC, không cần bật SAML để “sửa SameSite”.

## 9. Login CSRF, account confusion và redirect poisoning

### 9.1. Login CSRF không chỉ xảy ra ở form password

Attacker có thể tìm cách ép browser user đăng nhập RP dưới **tài khoản của attacker**, rồi khiến user tiếp tục nhập dữ liệu vào tài khoản đó. Đây là **login CSRF/session swapping**: rủi ro không nằm ở việc lấy cookie nạn nhân trực tiếp, mà ở việc nhầm **identity gắn với browser**.

Trong OAuth2/OIDC login, state/correlation và các điều kiện bảo vệ callback là nền tảng chống login CSRF. Nếu custom callback **bỏ state** để “sửa authorization_request_not_found”, attacker có thể tiêm authorization response thuộc một phiên/identity khác.

### 9.2. Exact redirect URI và open redirect

Provider cần kiểm **redirect URI đã đăng ký chính xác** theo giao thức và loại client, thay vì chấp nhận host do client tùy ý đưa. RP cũng không nên lấy `returnTo`/`next` từ query rồi chuyển user tới URL attacker:

~~~text
Không an toàn:
  GET /login?returnTo=https://attacker.example/phishing
  -> login success -> redirect ra host ngoài

An toàn hơn:
  returnTo là local path allowlist như /dashboard hoặc /orders
  -> canonicalize, reject scheme/host/protocol-relative URL
~~~

Với saved request, phải xem cơ chế redirect success handler và proxy Host/Forwarded trust. Không dùng `Referer` hoặc `Origin` thay thế state để xác minh callback.

### 9.3. Multiple IdPs và issuer mix-up

Ứng dụng hỗ trợ `corporate` và `partner` registration có nguy cơ nhận response từ provider A nhưng nhầm xử lý như provider B, hoặc dùng issuer discovery URL không tin cậy do client gửi.

Cần:

- Chỉ dùng **ClientRegistration allowlist** do server quản lý.
- Correlate response với **đúng registrationId, state, redirect URI và issuer**.
- Xác minh ID token `iss`, `aud`, signature, `nonce`/time claims theo flow.
- Không dùng claim email chưa xác minh như khóa ghép tài khoản tự động.
- Không đồng nhất user từ hai issuers chỉ vì `sub` chuỗi giống nhau: danh tính chuẩn nên là cặp **issuer + subject**, kết hợp account linking policy rõ.
- Với flows phức tạp, xem xét authorization response issuer identification/JARM/PAR theo hỗ trợ của provider; không tự chế protocol validation.

## 10. Servlet Spring Security: cấu hình OAuth2 Login cơ sở

### 10.1. Dependency theo vai trò

Một Spring Boot Servlet RP điển hình cần:

~~~text
spring-boot-starter-web
spring-boot-starter-security
spring-boot-starter-oauth2-client
spring-boot-starter-thymeleaf          (nếu render HTML)
spring-boot-starter-test              (test)
spring-security-test                  (test)
~~~

`spring-boot-starter-oauth2-client` và `oauth2Login()` dành cho **client/RP**. Nếu ứng dụng còn làm **Resource Server** cho Bearer API, đó là một trách nhiệm khác và có thể cần `spring-boot-starter-oauth2-resource-server` với security chain riêng.

### 10.2. ClientRegistration cho OIDC

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-idp
            client-id: ${CORPORATE_OIDC_CLIENT_ID}
            client-secret: ${CORPORATE_OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corporate-idp:
            issuer-uri: https://login.identity.example/realms/corporate
~~~

- Đường dẫn/issuer là ví dụ; phải thay bằng IdP tin cậy đã đăng ký redirect URI phù hợp.
- `client-secret` chỉ dùng cho confidential client và phải lấy từ **secret manager/environment**, không commit Git. Public client có phương thức authentication khác và PKCE.
- Scope `openid` kích hoạt OIDC; việc claim email đã verified hay chưa và quyền cho app phải theo provider/mapping policy.
- `{baseUrl}` phải được tính từ **public HTTPS host/scheme** chính xác sau proxy, không bị attacker điều khiển qua forwarded headers.
- Một registration dùng `response_type=code` ở flow này; đừng bật implicit/hybrid flow ngoài nhu cầu.
- Với `client_credentials` của M2M, dùng registration/policy riêng; nó không tạo browser login session.

### 10.3. HttpSecurity và browser session CSRF

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OidcServletLoginSecurity {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/login", "/assets/**", "/error").permitAll()
                .requestMatchers("/dashboard", "/profile/**")
                    .authenticated()
                .anyRequest().authenticated()
            )
            .oauth2Login(login -> login
                .loginPage("/login")
                .defaultSuccessUrl("/dashboard", false))
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout"))
            // Browser session còn nhận cookie: giữ CSRF.
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

Ví dụ chọn **top-level GET callback mặc định** và CSRF mặc định cho unsafe browser requests. Để bắt đầu login, trang custom có thể đưa link tới `/oauth2/authorization/corporate`. Spring Security tự đăng ký redirect/callback filters theo OAuth2 Login mặc định; không viết controller tự đổi code.

**Chú ý:** Nếu đổi `loginPage("/login")` thì phải cung cấp GET `/login`. Nếu để default login page, Spring có thể tự render lựa chọn login, tùy registration/context.

### 10.4. Trang login tùy chỉnh

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
class LoginPageController {
    @GetMapping("/login")
    String login() {
        return "auth/login";
    }
}
~~~

~~~html
<!-- templates/auth/login.html -->
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Đăng nhập</title>
</head>
<body>
  <h1>Đăng nhập</h1>
  <a href="/oauth2/authorization/corporate">
    Tiếp tục bằng tài khoản công ty
  </a>
</body>
</html>
~~~

Khởi tạo login với **GET link** không phải POST thay đổi nghiệp vụ. Callback code/state do OAuth2 Login filter xử lý; link chỉ trỏ đến registrationId **đã cấu hình**.

### 10.5. Phân quyền sau login không chỉ kiểm “đã xác thực”

Một OIDC principal có thể chứa tên, email, groups/roles. Không mặc định mọi user login thành công được phép truy cập mọi tenant/tài nguyên.

- Map `issuer+sub` tới tài khoản nội bộ theo policy.
- Kiểm trạng thái user, tenant, domain/group claim đáng tin và provision/deprovision.
- Không cấp role admin chỉ vì `email` giống một chuỗi hay IdP trả claim tự khai.
- Dùng service/method authorization cho object ID, không chỉ `authenticated()`.
- Khi logout/IdP vô hiệu hóa tài khoản, xem xét session lifetime/revalidation và back-channel logout, không giả định phiên RP lập tức biến mất.

## 11. Servlet: cookie SameSite, CSRF và authorization request repository

### 11.1. Spring Boot session cookie policy

Với ứng dụng Servlet dùng session cookie do container/Spring Boot cấu hình, ví dụ:

~~~yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        secure: true
        http-only: true
        same-site: lax
        path: /
~~~

**Đây là ví dụ cho flow code+query callback**. Cần xác minh `Set-Cookie` được browser thật nhận, vì Spring Session/custom cookie serializer, reverse proxy hoặc container có thể là lớp quyết định cookie cuối cùng. Không dựa vào properties nếu deployment dùng cơ chế cookie ngoài Spring Boot.

Các điểm cần kiểm tra:

- Cookie được tạo **trước khi chuyển đến IdP**, để RP có nơi giữ expected OAuth2 authorization request.
- Cookie có `Path=/` để browser gửi tới `/login/oauth2/code/corporate`.
- Cookie host/domain trùng public host callback.
- `Secure` chỉ hoạt động đúng khi client gọi RP qua HTTPS.
- `SameSite=Lax` phù hợp **top-level GET callback**; không tự phù hợp cross-site POST `form_post`.
- Session TTL phải đủ cho người dùng đăng nhập/chọn MFA/consent ở IdP, nhưng không kéo quá dài vô hạn.
- Sau login, chống session fixation và CSRF token lifecycle vẫn phải hoạt động.

### 11.2. Authorization request repository mặc định

Spring Security Servlet OAuth2 Login thường lưu authorization request trong **HttpSession** thông qua `HttpSessionOAuth2AuthorizationRequestRepository` (trừ khi bạn tùy chỉnh).

Nó giữ những gì cần thiết để xác minh callback, ví dụ `state` và các tham số của authorization request; PKCE verifier/nonce có thể được gắn với request/attributes theo cấu hình client/flow.

~~~text
GET /oauth2/authorization/corporate
   -> HttpSession S được dùng để lưu expected authorization request
   -> browser chuyển đến IdP
   -> GET callback quay về với Cookie của S
   -> filter tìm đúng request của S
   -> đối chiếu state, tiếp tục token exchange
~~~

Nếu chuyển chain sang `SessionCreationPolicy.STATELESS` khi vẫn dùng repository session-based, bạn có thể làm hỏng việc lưu/khôi phục correlation hoặc lưu SecurityContext sau login. **Không copy cấu hình bearer-only API vào RP session login chain**.

### 11.3. Khi muốn tùy biến repository

Spring có API repository dành cho authorization request, chẳng hạn:

~~~java
import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

AuthorizationRequestRepository<OAuth2AuthorizationRequest> repository =
    new HttpSessionOAuth2AuthorizationRequestRepository();
~~~

Tích hợp vào `HttpSecurity` ở **authorization endpoint**:

~~~java
.oauth2Login(login -> login
    .authorizationEndpoint(auth -> auth
        .authorizationRequestRepository(repository)))
~~~

Đây là **trích đoạn cấu hình**; trong code thật, truyền instance/bản repository có lifecycle phù hợp vào chain và kiểm tra version APIs.

Một custom cookie-based/stateless repository phải xử lý **ký/mã hóa nếu cần, expiry ngắn, nonce/state randomness, binding với browser/client/provider, một lần sử dụng và replay**. Không lấy `state` từ query rồi dùng nó để tìm bản ghi authorization request và tin phản hồi mà không có ràng buộc tới browser đã khởi tạo flow.

### 11.4. Browser form sau login vẫn cần Spring CSRF token

Sau OIDC login, app có thể trả HTML:

~~~html
<form method="post" action="/profile">
  <input name="displayName" value="Alice">

  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">

  <button type="submit">Cập nhật</button>
</form>
~~~

`state` của OAuth callback **không** thay `_csrf`; callback login thành công không chứng minh một POST nghiệp vụ sau này do chính trang RP khởi tạo. Ngay cả khi browser session cookie đặt `SameSite=Strict`, một số kịch bản same-site cross-origin và XSS vẫn khiến SameSite không đủ làm lớp CSRF duy nhất.

### 11.5. Cookie path khác callback path

Ví dụ sai:

~~~http
Set-Cookie: JSESSIONID=S; Path=/web; Secure; HttpOnly; SameSite=Lax
~~~

Khi callback là `/login/oauth2/code/corporate`, cookie `Path=/web` **không được gửi**, nên repository có thể báo authorization request not found.

Khắc phục: cấu hình cookie Path theo **toàn bộ RP auth lifecycle** hoặc tách cookie/authorization request storage theo kiến trúc đã phân tích; không mở rộng cookie Domain tới mọi subdomain khi vấn đề chỉ là Path.

## 12. Redirect URI, reverse proxy và các lỗi Host/Scheme

### 12.1. Một public origin phải nhất quán

Kịch bản triển khai:

~~~text
Browser public URL: https://app.example.com
Ingress:            TLS terminate và forward HTTP nội bộ
Spring backend:     http://spring-app:8080
OIDC redirect-uri:  https://app.example.com/login/oauth2/code/corporate
~~~

IdP yêu cầu redirect URI khớp URI đã đăng ký. Nếu Spring tính `{baseUrl}` thành `http://spring-app:8080`, login có thể thất bại do `redirect_uri_mismatch`, chuyển sang host nội bộ không truy cập được hoặc session cookie không gửi đúng scope.

Với Spring Boot, có thể cân nhắc property theo môi trường:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Cấu hình chỉ an toàn khi **reverse proxy tin cậy** đã strip/overwrite forwarded headers do Internet client đưa vào. Nếu backend có thể được gọi trực tiếp từ Internet với `Forwarded`/`X-Forwarded-Host` tùy ý, base URL/redirect có thể bị thao túng.

### 12.2. Luồng Header qua proxy

~~~mermaid
flowchart LR
    B[Browser https://app.example.com] --> P[TLS reverse proxy]
    P -->|Host và trusted X-Forwarded-Proto=https| A[Spring app]
    A -->|302 provider authorize redirect_uri=https://app.example.com/...| B
    B --> I[IdP]
    I -->|302 callback HTTPS public host| B
    B --> P
    P --> A
~~~

**Checklist**:

1. URL mở trang login và URL callback sử dụng **cùng public host** theo cookie scope.
2. Callback đúng `scheme=https` và đường `/login/oauth2/code/{registrationId}` thực tế.
3. Context path, prefix, trailing slash và URL encoding được đăng ký đúng với IdP.
4. Proxy không strip `Cookie` trên callback.
5. Không có redirect từ HTTPS sang HTTP gây mất Secure cookie.
6. Không forward `Authorization`/code/tokens ra upstream không tin cậy.
7. Header `Location` không chứa host do attacker điều khiển.
8. Nếu multi-node, tất cả node có khả năng đọc cùng authorization request/session store hoặc có session affinity đúng.

### 12.3. Không nên sửa `redirect_uri_mismatch` bằng wildcard

Một redirect URI có origin/path quá rộng có thể dẫn authorization code đến endpoint không do client quản lý. Hãy đăng ký **public redirect URIs chính xác** theo provider, một registration rõ cho mỗi môi trường:

~~~text
Production:
  https://app.example.com/login/oauth2/code/corporate

Development:
  https://dev-app.example.test/login/oauth2/code/corporate

Không nên:
  https://*.example.com/*
  https://app.example.com/**
  http://arbitrary-host/...
~~~

Redirect URI matching do Authorization Server thực thi theo chuẩn/profile; application không nên giả định provider cho wildcard hay dùng redirect query để lái về bất kỳ nơi nào.

### 12.4. Load balancer và session correlation

Nếu GET bắt đầu login vào **node A**, nhưng callback đến **node B**, và authorization request chỉ nằm trong local `HttpSession` node A, node B có thể báo không tìm thấy request.

Giải pháp cần chọn có chủ đích:

- Shared session store được hỗ trợ (ví dụ Spring Session với store phù hợp);
- Session affinity khi chấp nhận tradeoff vận hành và failover;
- Repository correlation được thiết kế riêng bảo đảm an toàn/replay/expiry;
- Định nghĩa TTL, serializer, cookie scope và key rotation đồng nhất.

Không tắt state validation hoặc chuyển correlation thành một map toàn cục không kiểm owner để chữa lỗi multi-node.

## 13. Đăng xuất liên kết: local, RP-initiated và back-channel

### 13.1. Local logout trước hết là thao tác ghi của RP

Khi browser dùng session cookie, **POST /logout** thông thường cần **Spring CSRF token**. Local logout xử lý SecurityContext/session/cookie phía RP theo cấu hình. Ví dụ HTML:

~~~html
<form method="post" action="/logout">
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Đăng xuất</button>
</form>
~~~

**GET /logout** khi CSRF bảo vệ bật có thể hiển thị trang xác nhận thay vì xóa phiên ngay. Không chuyển logout thành GET có side effect chỉ để dễ tạo link: cross-site navigation/prefetch có thể gây forced logout.

Local logout **không bảo đảm** phiên tại IdP bị xóa. User có thể đăng nhập lại RP gần như ngay lập tức vì phiên SSO của IdP vẫn còn.

### 13.2. RP-initiated logout theo OIDC

OIDC RP-Initiated Logout cho phép RP điều hướng browser đến end-session endpoint của provider với các tham số phù hợp, ví dụ `id_token_hint` và `post_logout_redirect_uri` nếu được hỗ trợ.

Spring Security Servlet có handler:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;

LogoutSuccessHandler oidcLogoutSuccessHandler(
        ClientRegistrationRepository registrations) {

    OidcClientInitiatedLogoutSuccessHandler handler =
        new OidcClientInitiatedLogoutSuccessHandler(registrations);

    handler.setPostLogoutRedirectUri("{baseUrl}");
    return handler;
}
~~~

Dùng handler này trong cấu hình `.logout(logout -> logout.logoutSuccessHandler(...))` sau khi đã có `ClientRegistrationRepository`, IdP metadata/end-session endpoint và application logout form bảo vệ CSRF.

**Điều kiện thực tế:**

- IdP phải công bố/hỗ trợ RP-initiated logout tương thích.
- `post_logout_redirect_uri` thường phải được provider đăng ký/cho phép chính xác.
- RP phải xử lý local session invalidation và UX khi IdP logout thất bại/timeout.
- Cookie SameSite của IdP và RP ảnh hưởng navigation trở về; browser privacy policy có thể thay đổi.
- Không log hoặc đưa `id_token_hint` vào analytics/support URL. Handler/protocol quyết định cách đưa tham số.
- RP-initiated logout không tự giải quyết mọi phiên ở **những RP khác** đã dùng chung IdP.

### 13.3. Front-channel logout và iframe

Một IdP có thể phát thông báo front-channel bằng cách dùng browser truy cập logout URI của RP, có thể qua **iframe**. Trong cross-site iframe, browser thường không gửi cookie `SameSite=Lax`/`Strict` của RP; third-party cookie blocking có thể chặn cả một số `None; Secure` contexts.

Do đó **không giả định front-channel logout luôn truy cập được session cookie**. Cần kiểm hỗ trợ provider, browser target, cơ chế ràng buộc phiên và mô hình bảo vệ request.

### 13.4. Back-channel logout không phải browser CSRF form

OIDC Back-Channel Logout gửi thông điệp **server-to-server** từ IdP tới RP. Nó có thể mang **logout token JWT**, không phải người dùng submit form với `_csrf`.

RP phải kiểm protocol logout token: signature, `iss`, `aud`, `iat`, `events` đúng event URI, `sid` hoặc `sub`, replay/`jti` khi có, và điều kiện profile yêu cầu; xác định phiên cần vô hiệu hóa theo mapping tin cậy. **Không** bỏ authentication/validation trên endpoint back-channel chỉ vì không có browser cookie/CSRF.

Nếu cấu hình CSRF exception cho endpoint server-to-server nhận POST, chỉ miễn matcher chính xác **và thay bằng protocol token validation**, không tắt CSRF cho toàn `/logout/**`.

### 13.5. Không nhầm logout token với CSRF/state/ID token

- **CSRF token** bảo vệ form POST logout của người dùng tại RP.
- **OIDC state** bảo vệ authorization response correlation; không dùng làm logout token.
- **ID token** xác nhận authentication, có thể được dùng làm `id_token_hint` cho RP-initiated logout.
- **Back-channel logout token** là JWT thông báo logout có claims/events riêng, không phải access token.
- **Refresh token** có vòng đời/thu hồi riêng, không mặc nhiên bị RP local logout thu hồi nếu provider không hỗ trợ/chưa gọi revocation policy.

## 14. HTTP security headers và chính sách browser trong login

### 14.1. CSP bảo vệ HTML của RP, không thay token validation

CSP được đặt trên **HTML login/dashboard** thực sự được browser render, ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; form-action 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

Policy chỉ là **định hướng**; nếu app có form phải submit tới IdP hoặc scripts từ domain khác, cần thiết kế các directives phù hợp. `form-action 'self'` không tự chặn **top-level redirect 302** tới IdP; nhưng nó có thể ảnh hưởng form submit nếu dùng form cross-origin. `connect-src` liên quan fetch/XHR, không phải mọi redirect navigation.

Đừng thêm `unsafe-inline` hoặc mở toàn bộ script origins chỉ để đăng nhập không lỗi; cân nhắc nonce/hash và kiểm định thư viện frontend.

### 14.2. HSTS và HTTPS

RP và IdP phải có HTTPS với certificate hợp lệ. `Strict-Transport-Security` giúp browser ưu tiên HTTPS cho host theo chính sách; nhưng:

- `includeSubDomains`/preload có thể ảnh hưởng mọi subdomain, chỉ bật khi hạ tầng sẵn sàng.
- Reverse proxy có thể là nơi phát HSTS; kiểm response HTML **qua public edge**, không chỉ Spring backend.
- HSTS không thay CSRF, state/nonce/PKCE hoặc OAuth token validation.
- M2M HTTP client không được giả định tuân theo mọi hành vi HSTS của browser; luôn kiểm chứng TLS.

### 14.3. Referrer-Policy, cache và logging

Callback URL có **authorization code + state** ở query. Các lớp edge/log/analytics cần tránh vô tình ghi hoặc chuyển chúng tới bên ngoài.

Có thể áp `Referrer-Policy: no-referrer` trên callback/HTML nhạy cảm, hạn chế third-party scripts trên callback page và không để callback response cache công khai. `Cache-Control: no-store` phù hợp với login/token-related sensitive responses.

Trong logging:

- Không ghi raw authorization code, code verifier, ID/access/refresh tokens, cookie session, CSRF token hoặc client secret.
- Có thể ghi correlation ID, registrationId đã được allowlist, loại lỗi, status, IdP issuer identifier và thời gian xử lý.
- Redact query parameters `code`, `state`, `id_token` và các URL chứa signed values trong proxy/access logs, tracing và error-reporting.
- Không trả full exception hoặc token claims nhạy cảm cho browser khi login thất bại.

### 14.4. Security headers không sửa được SameSite POST callback

Một CSP hoàn hảo trên RP không khiến browser gửi cookie `SameSite=Lax` trong cross-site POST form callback. Một `Access-Control-Allow-Origin` rộng cũng **không** làm session cookie hiện ra trong navigation. Phải xác định **cookie policy, response mode, client repository và callback handler** đúng gốc nguyên nhân.

## 15. Khi hệ thống có cả browser login và Resource Server API

Ứng dụng có thể vừa dùng OAuth2 Login session cho `/web/**`, vừa nhận Bearer JWT cho `/api/m2m/**`. Hãy tách security chains theo credential contract:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain m2m(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/m2m/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.POST, "/api/m2m/jobs")
                .hasAuthority("SCOPE_jobs:write")
            .anyRequest().authenticated())
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .formLogin(AbstractHttpConfigurer::disable)
        .httpBasic(AbstractHttpConfigurer::disable)
        .oauth2ResourceServer(oauth -> oauth
            .jwt(Customizer.withDefaults()))
        .csrf(AbstractHttpConfigurer::disable)
        .build();
}

@Bean
@Order(2)
SecurityFilterChain browser(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/assets/**").permitAll()
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .csrf(Customizer.withDefaults())
        .build();
}
~~~

Đây là **đoạn ví dụ thay thế** cho một ứng dụng hỗn hợp, không đặt cạnh một cấu hình khác tạo hai chains y hệt mà không xác định bean order. Browser chain vẫn giữ session/state/CSRF; M2M chỉ được miễn CSRF **sau khi test cookie-only không xác thực được trên chain**. Callback `/login/oauth2/code/**` phải đi vào **browser chain** có OAuth2 Login filter.

**Sai lầm thường gặp:** Đặt `SessionCreationPolicy.STATELESS` toàn ứng dụng rồi hỏi vì sao `state`/authorization request mất; hoặc đặt security matcher bearer rộng khiến OAuth callback chạy qua entry point `401` thay vì OAuth2 Login.

## 16. Reactive/WebFlux: OAuth2 Login và WebSession

### 16.1. Mô hình bảo mật không đổi khi backend dùng Reactor

Từ góc nhìn browser, SameSite/cross-site GET/POST callback, IdP cookie, CORS và XSS **không thay đổi**. Các class bảo mật/phản ứng ở backend khác:

| Vai trò | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| Security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Session | `HttpSession` | `WebSession` |
| Session ID cookie | Servlet/container/Spring Session | `CookieWebSessionIdResolver` hoặc Spring Session |
| OAuth2 authorization request | `HttpSessionOAuth2AuthorizationRequestRepository` mặc định | `WebSessionOAuth2ServerAuthorizationRequestRepository` theo mặc định tương ứng |
| OAuth2 login filter | OAuth2 Login Servlet filters | Reactive OAuth2 Login WebFilters |
| CSRF filter | `CsrfFilter` | `CsrfWebFilter` |
| CSRF repository | `HttpSessionCsrfTokenRepository` | `WebSessionServerCsrfTokenRepository` |
| Client registration repository | `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| JWT/ID token validation | OAuth2/OIDC login clients | Reactive OAuth2/OIDC login clients |
| HTTP test | `MockMvc` | `WebTestClient` |

**Sai lầm thường gặp:** Cấu hình WebFlux `NoOpServerSecurityContextRepository`/stateless cho RP rồi mong `WebSession` correlation và browser login session hoạt động như trước. Hãy chỉ dùng no-op cho **bearer-only API chain** nếu thật sự cần, không mặc định cho OIDC Login chain.

### 16.2. Reactive security chain cho login browser

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class OidcReactiveLoginSecurity {

    @Bean
    SecurityWebFilterChain web(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/login", "/assets/**", "/error")
                    .permitAll()
                .pathMatchers("/dashboard", "/profile/**")
                    .authenticated()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            // Còn WebSession cookie: CSRF phải bật cho POST.
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

Phần `ClientRegistration` trong `application.yml` có thể sử dụng cùng cấu trúc `spring.security.oauth2.client.registration...` khi Boot auto-config cho reactive stack.

**Điều kiện:** IdP thực sự hỗ trợ OIDC authorization code flow; WebFlux OAuth2 Login repository/callback filter được cấu hình đúng; flow đủ state/nonce/PKCE validation theo version. Nếu tùy chỉnh login page/redirect endpoint phải cập nhật cả login links, filter matcher và IdP redirect registration.

### 16.3. WebSession cookie policy với CookieWebSessionIdResolver

Với Spring Framework version hỗ trợ `addCookieInitializer`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration
class OidcReactiveSessionCookieConfig {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
            new CookieWebSessionIdResolver();

        resolver.setCookieName("SESSION");
        resolver.addCookieInitializer(cookie -> cookie
            .path("/")
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax"));

        return resolver;
    }
}
~~~

Đây là ví dụ cho **top-level GET callback**. Nếu Spring Session cung cấp cookie serializer hoặc một `WebSessionIdResolver` khác, cấu hình thực tế có thể nằm ở thành phần khác. Kiểm tra `Set-Cookie` ở public HTTPS URL.

Khi IDP dùng cross-site POST callback `form_post`, cookie `SameSite=Lax` của RP có thể vắng mặt, khiến reactive authorization request trong WebSession không được tìm thấy. Không tắt `CsrfWebFilter` toàn app để che lỗi.

### 16.4. WebSession authorization request repository và publisher

Reactive OAuth2 login có thể lưu authorization request trong **WebSession**. Callback phải truy xuất đúng expected state và các attributes liên quan qua reactive repository. Không tự gọi blocking `HttpSession` hoặc dùng Servlet OAuth2 filters trong WebFlux.

Nếu viết custom repository cho flow phức tạp, phải đảm bảo:

- Độc lập giữa các browser/các phiên;
- State entropy/expiry và single-use;
- Correlation tới đúng issuer/registrationId/redirect URI;
- Bảo vệ code verifier và OIDC nonce;
- Replay/race handling trong reactive storage;
- Không block event loop khi gọi DB/network.

### 16.5. Reactive controller bảo vệ route sau login

Ví dụ route chỉ trả user hiện hành, không tiết lộ token:

~~~java
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
class ReactiveUserInfoController {

    @GetMapping("/profile/me")
    Mono<Map<String, String>> me(ServerWebExchange exchange) {
        return exchange.getPrincipal()
            .map(p -> Map.of("username", p.getName()));
    }
}
~~~

Endpoint chỉ trả tên để minh họa. Trong sản phẩm, cần quyết định attributes nào được phép trả, tránh phơi toàn bộ OIDC ID token/claims nhạy cảm và kiểm object-level permissions ở service.

## 17. Reactive OIDC logout và những điểm khác Servlet

### 17.1. Local logout vẫn là thao tác có tác động

Khi user dùng `WebSession` cookie, POST logout thông thường cần CSRF token từ `CsrfWebFilter`. Một SPA có thể gửi token qua header; form dùng hidden field do view model trả về. Việc logout có xóa toàn `WebSession` hay chỉ clear SecurityContext phụ thuộc cấu hình logout handlers. **Kiểm thử authenticated state sau logout**, không suy đoán chỉ từ redirect thành công.

### 17.2. RP-initiated logout handler Reactive

Spring Security Reactive có handler tương ứng:

~~~java
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.server.logout.OidcClientInitiatedServerLogoutSuccessHandler;
import org.springframework.security.web.server.authentication.logout.ServerLogoutSuccessHandler;

ServerLogoutSuccessHandler oidcLogoutSuccessHandler(
        ReactiveClientRegistrationRepository registrations) {

    OidcClientInitiatedServerLogoutSuccessHandler handler =
        new OidcClientInitiatedServerLogoutSuccessHandler(registrations);

    handler.setPostLogoutRedirectUri("{baseUrl}");
    return handler;
}
~~~

Tích hợp với `ServerHttpSecurity.logout(logout -> logout.logoutSuccessHandler(handler))` theo version/security configuration. Đây là **trích đoạn helper**, không phải một Java class có đủ dependency injection.

Provider phải có end-session endpoint và post-logout redirect URI được phép. Sau khi redirect về RP, browser session cũ không được phục hồi; nếu người dùng đăng nhập lại ngay vì phiên IdP còn hoạt động, cần phân biệt local logout với federated logout hoàn tất.

### 17.3. Back-channel logout Reactive

Nếu triển khai OIDC back-channel logout, nhận server-to-server POST phải qua handler/filter **có xác minh logout token theo specification**, map `sid/sub` tới WebSession của người dùng và invalidate. Không tự dùng `@PostMapping("/logout")` nhận một JSON `userId` do client gửi rồi xóa session.

Nếu callback back-channel được miễn CSRF, chỉ miễn **protocol endpoint** này và thực hiện token validation đầy đủ. Các form POST của browser vẫn cần `CsrfWebFilter`.

## 18. SPA, BFF và silent SSO: lựa chọn kiến trúc làm thay cookie flow

### 18.1. Spring RP server-side và SPA public client khác nhau

**Mô hình A — Server-side RP/Backend for Frontend (BFF):**

~~~text
Browser -- session cookie --> Spring RP/BFF
Spring RP/BFF -- code exchange + client auth --> IdP
Spring RP/BFF -- access token (server-side) --> Resource API
~~~

Browser thường chỉ giữ session cookie của BFF, nên unsafe browser requests **cần CSRF**. Authorization code/ID token/refresh token có thể được giữ khỏi JavaScript theo thiết kế, giảm một số rủi ro lộ token trực tiếp.

**Mô hình B — SPA là OAuth public client:**

~~~text
Browser SPA -- authorization code + PKCE --> IdP
Browser SPA -- Authorization: Bearer access token --> Resource API
~~~

SPA tự quản lý PKCE/state/token lifecycle theo SDK phù hợp; Resource API có thể bearer-only và miễn CSRF **nếu không nhận cookie fallback**. Tuy nhiên JS-held token chịu rủi ro XSS/token theft; không chỉ vì dùng localStorage hay memory mà trở nên an toàn.

### 18.2. CORS dùng ở đâu?

| Request | Có browser CORS không? | Vì sao? |
|---|---|---|
| RP top-level redirect 302 đến IdP | **Không cần CORS** | Navigation, không phải JS fetch đọc response |
| IdP top-level GET callback về RP | **Không cần CORS** | Navigation về RP |
| IdP `form_post` callback qua HTML form | **Không cần CORS để form navigation** | Nhưng chịu SameSite và CSRF filter/protocol handler |
| Spring RP backend gọi token endpoint | **Không cần browser CORS** | Server-to-server |
| SPA JS gọi API khác origin | **Có** | Browser fetch/XHR cross-origin |
| SPA JS gọi token endpoint IdP | **Có nếu provider hỗ trợ flow này** | Browser CORS trên token endpoint; thiết kế public client |
| M2M service dùng HTTP client | **Không cần browser CORS** | Client không áp browser SOP/CORS |
| Front-channel logout iframe | Có browser embedding/cookie policies | Vấn đề chính là iframe/cookie/headers, không đơn thuần API CORS |

Không mở `Access-Control-Allow-Origin: *` cho RP callback với hy vọng sửa một cookie `SameSite` bị loại. Hai lớp giải quyết vấn đề khác nhau.

### 18.3. Silent authentication trong iframe và third-party cookies

Một SDK SPA cũ có thể âm thầm gọi authorize endpoint qua hidden iframe để thử SSO, thường dựa vào IdP session cookie khi IdP đang là third-party.

Khi browser chặn third-party cookies/iframe, silent SSO có thể thất bại dù **top-level redirect login vẫn thành công**. Không tắt state/nonce hoặc hạ `SameSite` không phù hợp để chữa lỗi. Xem lại khả năng dùng top-level navigation, refresh rotation hợp pháp hoặc BFF theo kiến trúc hỗ trợ của IdP và privacy controls hiện hành.

### 18.4. Login popup và callback

Nếu đăng nhập qua popup, response mode, popup opener/origin messaging và cookie policy cần kiểm thêm:

- Không dùng `postMessage(..., "*")` để gửi code/token cho bất kỳ origin; xác định origin đích và kiểm `event.origin`.
- Không đưa access/refresh token vào window URL/fragment không kiểm soát.
- Đóng popup theo trạng thái xác thực chính xác và chống race.
- Cookie session/`SameSite` vẫn do browser xử lý; popup không phải cách đảm bảo cross-site POST callback có cookie.
- Popup blockers, mobile UX và IdP policies có thể khiến top-level redirect đơn giản đáng tin hơn.

## 19. Nhận diện lỗi giao thức hay cookie bị mất

### 19.1. Các triệu chứng điển hình

| Tín hiệu | Nguyên nhân có thể | Kiểm tra trước |
|---|---|---|
| `authorization_request_not_found` | Callback không tìm expected request trong session | Cookie RP có được gửi? SameSite/Domain/Path? Shared session store? |
| `invalid_state_parameter`/state mismatch | State sai/đã dùng/hết hạn hoặc correlation sai | Session context, replay, multiple tabs, provider/registration |
| `redirect_uri_mismatch` ở IdP | URI Spring tạo khác URI đăng ký | HTTPS public host/scheme/port/path, forwarded headers |
| `invalid_grant` khi đổi code | Code hết hạn, dùng lại, redirect URI/PKCE verifier không khớp | Token endpoint response/error, code age và session |
| `invalid_client` | Client authentication sai/missing secret hoặc method | Registration, secret rotation, token endpoint auth |
| `invalid_id_token` | Signature/issuer/audience/nonce/time không hợp lệ | Trusted issuer/JWKs, claim validation, clock |
| Login trả về rồi lại redirect IdP | Session không persist sau success | Set-Cookie sau login, cookie Path/SameSite/Secure, SecurityContext |
| Chỉ `form_post` fail, query callback pass | Lax cookie không gửi cross-site POST; handler/CSRF POST | Response mode + Network Cookie + CSRF exception hẹp |
| Chỉ iframe silent SSO fail | Third-party cookies bị chặn, frame policy của IdP | Browser privacy policy/CSP/frame headers |
| Chỉ một browser fail | Cookie defaults/partitioning hoặc SameSite khác nhau | Cùng HAR/request chain theo từng browser, không giả định default |
| Chỉ fail sau MFA mất thời gian | Pre-login session/authorization request hết TTL | Session TTL, store eviction, long IdP flow |
| Fail ngẫu nhiên giữa nodes | Expected authorization request chỉ ở node khác | Shared session store/affinity, serializer, cookie |
| Callback host thiếu www hoặc sai scheme | Cookie host-only/Secure không đi callback | Public redirect URI, proxy rewriting |
| POST cập nhật hồ sơ sau login `403` | CSRF token cũ/missing, không phải OAuth state | Lấy token mới theo phiên sau login |
| GET logout khiến mất phiên đột ngột | Tùy chỉnh logout GET có side effect | Chuyển POST CSRF hoặc GET confirmation |
| Local logout rồi login lại ngay không nhập mật khẩu | IdP session vẫn sống | RP vs IdP logout scope, RP-initiated logout |
| Front-channel logout không đồng bộ | Iframe không gửi cookie RP | SameSite/3PC, provider support, back-channel alternative |
| Back-channel logout bị 403 CSRF | POST protocol endpoint bị CSRF filter chặn | Exception đúng matcher + verified logout token |
| `state` hiển thị trong access logs | Proxy ghi query redirect/callback đầy đủ | Redaction code/state/tokens; no sensitive telemetry |
| Login của provider A map vào account provider B | Account linking/issuer-sub confusion | Định danh theo issuer+sub, registration correlation |
| Browser phản hồi CORS error tại API sau login | SPA fetch API khác origin, không phải callback | Preflight/credentials/CORS, không đổi OAuth state |
| `invalid_nonce` | Nonce kỳ vọng và ID token không khớp | OIDC flow, replay/sessions/provider config |

### 19.2. Cách phân biệt state lỗi và CSRF lỗi

~~~text
Tình huống A — Callback:
  GET /login/oauth2/code/corporate?code=...&state=...
  -> OAuth login filter tìm expected authorization request
  -> state sai/không có -> authentication failure
  -> không phải POST business CSRF failure

Tình huống B — Form update:
  POST /profile Cookie: JSESSIONID=S
  thiếu X-CSRF-TOKEN/_csrf
  -> Spring CsrfFilter/CsrfWebFilter có thể trả 403
  -> không phải OAuth state mismatch

Tình huống C — IdP form_post:
  POST callback từ IdP
  -> browser có thể không gửi SameSite=Lax cookie
  -> CSRF filter có thể trả 403 hoặc repository không có expected request
  -> cần xử lý đúng CẢ browser cookie, callback matcher và protocol validation
~~~

**Đừng giải quyết cả ba bằng một lệnh `csrf.disable()` hoặc bỏ state validation.** Lỗi ở tầng nào phải sửa đúng tầng đó.

## 20. Ma trận kiểm thử bảo mật đăng nhập liên kết

Để kiểm thử đúng, phải tách **giao thức OAuth/OIDC**, **cookie/browser**, **ứng dụng sau login**, **logout** và **hạ tầng**. Một test pass riêng lẻ không chứng minh toàn bộ flow.

| ID | Thử nghiệm | Kết quả cần chứng minh |
|---|---|---|
| **SSO-01** | GET `/oauth2/authorization/corporate` | Redirect tới trusted issuer, có state ngẫu nhiên và redirect URI chính xác |
| **SSO-02** | RP khởi tạo login | Expected authorization request liên kết đúng browser/session |
| **SSO-03** | IdP trả code+state đúng qua GET | Callback nhận cookie, so state và đổi code thành công |
| **SSO-04** | Callback thiếu state | Bị từ chối, không tạo authenticated session |
| **SSO-05** | Callback state khác expected | Từ chối, không login |
| **SSO-06** | Callback replay code/state đã dùng | Từ chối, không login lần hai |
| **SSO-07** | State của session A đi cùng cookie session B | Từ chối, không session swapping |
| **SSO-08** | Authorization code hết hạn/đã dùng | Token endpoint từ chối, RP không login |
| **SSO-09** | PKCE verifier sai | Code exchange bị từ chối |
| **SSO-10** | OIDC ID token sai nonce | RP từ chối |
| **SSO-11** | ID token sai `iss` | RP từ chối |
| **SSO-12** | ID token sai `aud`/`azp` khi áp dụng | RP từ chối |
| **SSO-13** | ID token signature sai/khóa không tin cậy | RP từ chối |
| **SSO-14** | ID token hết hạn/`nbf` chưa đến | RP từ chối |
| **SSO-15** | Callback URI sai scheme/host/path | Provider/RP từ chối hoặc correlation không tìm thấy |
| **SSO-16** | Cookie Lax với top-level cross-site GET callback | Cookie đến RP nếu scope/Secure hợp lệ |
| **SSO-17** | Cookie Strict với cross-site GET callback | Không dựa vào cookie được gửi trong navigation |
| **SSO-18** | Cookie Lax với cross-site `form_post` | Cookie thường không gửi, flow fail an toàn |
| **SSO-19** | `form_post` với cookie/handler được hỗ trợ | State/nonce/PKCE đầy đủ, CSRF exemption chỉ hẹp |
| **SSO-20** | Cookie vắng do sai Path/host | Không bypass state, báo lỗi correlation |
| **SSO-21** | Callback sau khi session hết TTL | Từ chối nếu expected request không còn |
| **SSO-22** | Callback sang node khác | Shared session/affinity hoạt động đúng |
| **SSO-23** | Hai IdPs cùng ứng dụng | State/issuer/registration/account linking không lẫn |
| **SSO-24** | Hai flow trong hai tab | Không nhầm identity, xử lý concurrency/replay an toàn |
| **SSO-25** | Session rotation sau login | Cookie mới được dùng; session cũ không authenticated |
| **SSO-26** | POST nghiệp vụ thiếu CSRF | Bị từ chối, không side effect |
| **SSO-27** | POST CSRF sai/cũ | Bị từ chối, không side effect |
| **SSO-28** | POST CSRF đúng | Còn phải kiểm user/tenant authorization |
| **SSO-29** | Callback OAuth của attacker được ép vào browser khác | Không login do state/correlation mismatch |
| **SSO-30** | Silent login trong iframe khi chặn 3PC | Thất bại an toàn, UX fallback |
| **SSO-31** | POST local logout thiếu CSRF | Không bị forced logout |
| **SSO-32** | POST local logout đúng CSRF | RP session không authenticated |
| **SSO-33** | RP-initiated logout | Provider/redirect được allowlist, xử lý đúng |
| **SSO-34** | Front-channel logout thiếu third-party cookie | Không giả định phiên đã xóa hoàn toàn |
| **SSO-35** | Back-channel logout JWT giả | Từ chối, không xóa phiên người khác |
| **SSO-36** | Proxy log query callback | Code/state/tokens được redact |
| **SSO-37** | RP sau HTTPS proxy | Redirect đúng public HTTPS scheme/host/path |
| **SSO-38** | Forged Forwarded headers | Không lái redirect tới attacker host |
| **SSO-39** | API Bearer M2M nhận cookie browser đơn lẻ | Không xác thực qua cookie-only nếu chain bearer-only |
| **SSO-40** | Login success returnTo ngoài allowlist | Không open redirect |

**Với negative cases**, assert thêm không tạo phiên xác thực, không liên kết account sai, không ghi dữ liệu nghiệp vụ, không lộ code/ID token và không xóa nhầm phiên của người khác.

## 21. Servlet MockMvc: test UI security và authorization initiation

### 21.1. `oidcLogin()` giúp test hậu-login, không phải toàn protocol

Giả định ứng dụng có `GET /dashboard` trả 200 và `POST /profile` cập nhật hợp lệ rồi redirect:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OidcServletUiTests {

    @Autowired MockMvc mvc;

    @Test
    void unauthenticatedDashboardRedirects() throws Exception {
        mvc.perform(get("/dashboard"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void mockOidcUserCanViewDashboard() throws Exception {
        mvc.perform(get("/dashboard").with(oidcLogin()))
            .andExpect(status().isOk());
    }

    @Test
    void businessPostStillNeedsCsrf() throws Exception {
        mvc.perform(post("/profile")
                .with(oidcLogin())
                .param("displayName", "Must Not Save"))
            .andExpect(status().isForbidden());
    }

    @Test
    void businessPostWithCsrfCanProceed() throws Exception {
        mvc.perform(post("/profile")
                .with(oidcLogin())
                .with(csrf())
                .param("displayName", "Alice New"))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

`oidcLogin()` tạo principal/authentication giả trong test. Nó **không chạy OIDC redirect qua provider, state/nonce/PKCE, ID token signature validation, SameSite hoặc session persistence**. Controller/service test cần fixture và quyền phù hợp; 200/302 là hợp đồng ứng dụng giả định.

### 21.2. GET bắt đầu authorization redirect và tạo correlation

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OidcAuthorizationRedirectTests {

    @Autowired MockMvc mvc;

    @Test
    void authorizationEndpointCreatesSessionAndRedirects()
            throws Exception {

        MvcResult result = mvc.perform(
                get("/oauth2/authorization/corporate"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String location =
            result.getResponse().getHeader("Location");

        assertNotNull(location);
        assertTrue(location.startsWith(
            "https://login.identity.example/"));
        assertTrue(location.contains("state="));
        assertTrue(location.contains("redirect_uri="));

        MockHttpSession session = (MockHttpSession)
            result.getRequest().getSession(false);
        assertNotNull(session);
    }
}
~~~

**Giả định:** Test profile dùng `ClientRegistration corporate` với authorization endpoint tại URL ví dụ; có thể cần stub IdP discovery/JWKs để chạy không truy cập production. Nếu sử dụng custom cookie/stateless authorization request repository, assertion HttpSession phải thay bằng test store phù hợp.

Test này **chỉ kiểm initiation**. Nó chưa thực hiện callback và không xác minh token signature.

### 21.3. HTTP integration với IdP thử nghiệm mới kiểm đầy đủ protocol

Một bộ integration đầy đủ:

1. Có test IdP/issuer, authorize endpoint, token endpoint và JWKS test keys.
2. Gọi GET `/oauth2/authorization/corporate`, giữ **session cookie**, lấy state/PKCE challenge từ `Location` trong test, không ghi secrets ra logs.
3. Tạo authorization code **một lần sử dụng**, ràng buộc đúng client, redirect URI và challenge.
4. Callback GET `/login/oauth2/code/corporate?code=...&state=...` với **cùng session**.
5. Token endpoint trả ID token ký bằng test key với `iss/aud/nonce/exp` đúng.
6. Kiểm session RP trở thành authenticated và redirect vào app.
7. Thử callback sai state/nonce/issuer/audience/key/expiry, code replay, verifier sai, session A/B và thiếu cookie.
8. Negative cases phải **không tạo login session** và không có business side effects.

**Không** dùng `with(oidcLogin())` để chứng minh dòng 3–6 vì helper bỏ qua các lớp giao thức mà test cần đánh giá.

### 21.4. MockMvc không mô phỏng SameSite algorithm

`MockMvc` cho phép gửi cookie thủ công trên mọi request. Nó **không tự quyết định** browser sẽ loại cookie `SameSite=Lax` khỏi cross-site POST hoặc giữ trên top-level GET. Vì vậy test SameSite bắt buộc dùng **browser engine thật** với HTTPS RP/IdP origins, hoặc một bộ test browser tương đương. MockMvc có thể kiểm kết quả server-side **khi cookie vắng mặt**, nhưng không chứng minh tại sao browser loại cookie.

## 22. Reactive WebTestClient: OIDC principal và WebSession correlation

### 22.1. mockOidcLogin giúp test security sau login

Dùng `spring-security-test` cho WebFlux và endpoint `GET /profile/me` ở phần Reactive:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class OidcReactiveUiTests {

    @Autowired ApplicationContext context;

    WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void mockOidcPrincipalCanReadProfile() {
        client().mutateWith(mockOidcLogin())
            .get().uri("/profile/me")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void anonymousPrincipalCannotReadProfile() {
        client()
            .get().uri("/profile/me")
            .exchange()
            .expectStatus().is3xxRedirection();
    }
}
~~~

`mockOidcLogin()` tạo principal giả cho test sau login, **không chứng minh** callback state, chữ ký ID token, PKCE, nonce, redirect URI, WebSession persistence hay SameSite browser.

### 22.2. Reactive POST nghiệp vụ vẫn chịu CSRF

Giả định có fixture `POST /profile` trả 204 khi user đủ quyền:

~~~java
import org.springframework.http.MediaType;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@Test
void postWithoutCsrfFailsEvenWithOidcPrincipal() {
    client().mutateWith(mockOidcLogin())
        .post().uri("/profile")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("{\"displayName\":\"Must Not Save\"}")
        .exchange()
        .expectStatus().isForbidden();
}

@Test
void postWithCsrfCanReachController() {
    client().mutateWith(mockOidcLogin())
        .mutateWith(csrf())
        .post().uri("/profile")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("{\"displayName\":\"Alice New\"}")
        .exchange()
        .expectStatus().isNoContent();
}
~~~

Đây là **test methods để thêm vào class có `client()`/imports**, và `POST /profile` là **endpoint fixture giả định**. Positive test còn phụ thuộc authorization và validation nghiệp vụ; negative test cần kiểm database không đổi.

### 22.3. WebSession callback với hai clients

~~~text
Client A:
  GET /oauth2/authorization/corporate
    -> authorization request A, WebSession cookie SESSION=A
  GET /login/oauth2/code/corporate?code=C_A&state=S_A
    + Cookie SESSION=A
    -> login nếu test provider và validation hợp lệ

Client B:
  GET callback với cookie SESSION=B + state=S_A + code C_A
    -> không tìm expected authorization request A, từ chối

Client A:
  Reuse code C_A/state S_A
    -> không thể login lần nữa vì code/state single-use

Client A:
  POST form_post khi browser không gửi SameSite=Lax cookie
    -> không thể giả định expected request vẫn tồn tại
~~~

`WebTestClient` có thể gửi cookie thủ công, nhưng **không áp thuật toán SameSite/third-party cookie**. Browser automation là lớp khác.

### 22.4. Integration cần kiểm storage và non-blocking behavior

- Authorization request ở node A, callback node B với WebSession store chung;
- Session hết hạn trong lúc IdP thực hiện MFA/consent;
- ID token thật sai issuer/audience/nonce/expiry/signature;
- Hai flows song song không được trộn state/provider;
- Custom reactive handler không được gọi blocking HTTP client trên event loop;
- Logout đúng WebSession, back-channel logout token giả không được xóa phiên khác.

## 23. Browser E2E: SameSite và redirect bằng HTTPS thật

### 23.1. Thiết lập hai site thực sự khác nhau

~~~text
Relying Party: https://app.example.test
Test IdP:      https://login.other.test
~~~

Các hostname trên là ví dụ; cần DNS/hosts và certificate hợp lệ trong môi trường test. Để đánh giá cross-site, IdP/RP phải thuộc **hai schemeful sites khác nhau**, không chỉ đổi port.

Hai browser tabs cùng profile thường **chia sẻ cookie**; để test hai sessions khác nhau, dùng **hai browser contexts/cookie jars**.

### 23.2. Top-level GET callback với Lax

1. Mở RP HTTPS, xem DevTools Network/Storage.
2. GET `/oauth2/authorization/corporate`: xác minh redirect tới đúng IdP, expected state được tạo.
3. Xem cookie RP (nếu cấp) có `Secure; HttpOnly; SameSite=Lax; Path=/` và đúng Domain/expiry.
4. Đi qua IdP bằng top-level navigation rồi nhận `302` GET callback.
5. Trong Network của **request callback**, xem browser gửi cookie RP hay không.
6. Xác minh RP so state, token validation và tạo phiên user đã login.
7. POST nghiệp vụ với CSRF token: thành công theo quyền; thiếu token: từ chối và không ghi dữ liệu.
8. Kiểm cookie rotation sau authentication; đừng yêu cầu ID trước/sau login luôn bằng nhau.

**Không** dựa vào `document.cookie` để kiểm `HttpOnly` session cookie vì JS không đọc được.

### 23.3. Lax + `form_post` phải thất bại an toàn khi cookie mất

1. Test IdP sử dụng `response_mode=form_post`.
2. RP vẫn đặt `SameSite=Lax`.
3. Browser gửi cross-site POST callback; quan sát Cookie header/DevTools excluded cookie reason.
4. Nếu repository session-based, RP có thể báo `authorization_request_not_found` hoặc CSRF filter trả 403.
5. **Tuyệt đối không** bypass state/correlation để biến callback thành login success.
6. Nếu bắt buộc form_post, cấu hình callback handler và cookie policy phù hợp, xem xét `None; Secure`, CSRF exception hẹp và test state/nonce/PKCE/issuer/scope lại đầy đủ.

### 23.4. Strict + top-level GET

1. Đặt cookie RP `SameSite=Strict` trong test profile.
2. Bắt đầu login tại RP, chuyển IdP rồi quay lại bằng top-level GET.
3. Quan sát cookie Strict có thể bị browser loại trong navigation cross-site.
4. RP không tìm được expected request thì phải fail closed; không tự “chấp nhận state” chỉ bằng query.
5. Cân nhắc tác động của Strict tới deep links và post-login UX, không chọn chỉ vì tên nghe “an toàn hơn”.

### 23.5. Những biến thể URL cần thử

- Khởi tạo từ `app.example.test`, callback tới `www.app.example.test`;
- Cookie `Path=/web` nhưng callback `/login/oauth2/code/...`;
- Proxy HTTPS bên ngoài nhưng redirect_uri bị tính thành HTTP upstream;
- Callback port/trailing slash/URL encoding khác URI đăng ký;
- Cookie pre-login hết hạn khi user làm MFA/consent lâu;
- Session store không đồng nhất giữa nodes;
- Multi-tab bắt đầu hai flows, quay về thứ tự đảo.

Các trường hợp thiếu correlation **không được tự trở thành authenticated session**.

### 23.6. Iframe, front-channel logout và third-party cookies

Dùng browser contexts với chính sách chặn third-party cookies theo browser được hỗ trợ:

- Login top-level có thể vẫn chạy dù iframe silent login fail;
- Front-channel logout iframe có thể không gửi cookie RP, không nên kết luận đã invalidated;
- Back-channel logout server-to-server không phụ thuộc cookie browser, nhưng phải xác minh logout token đúng;
- Nếu dùng popup/postMessage, kiểm origin đích và origin nguồn, không gửi tokens với wildcard targetOrigin.

### 23.7. Bảo vệ test artifacts

HAR, trace, log CI hoặc video có thể chứa `code`, `state`, cookies và redirect URLs. Dùng test identities/tokens, lọc secrets, giới hạn retention và không đưa HAR production chưa được redact vào issue công khai.

## 24. Chọn kiến trúc theo nhu cầu thực tế

| Nhu cầu | Lựa chọn thường hợp lý | Rủi ro/điều kiện |
|---|---|---|
| Web SSR dùng OIDC SSO | Server-side code flow, GET callback, session Lax | State, nonce/PKCE, CSRF và proxy public URI |
| SPA muốn giữ token khỏi JavaScript | BFF/RP giữ token server-side | Cookie BFF vẫn cần CSRF, session/CSP/XSS |
| SPA làm OAuth public client | Authorization Code + PKCE qua SDK tin cậy | State, token storage, XSS, CORS API/token endpoint |
| IdP chỉ hỗ trợ form_post | POST callback + cookie correlation design | Handler phải hỗ trợ và ngoại lệ CSRF rất hẹp |
| SAML2 POST binding | SP SAML ACS handler có SAML validation | Signature/RelayState/InResponseTo/replay, SameSite POST |
| Silent SSO qua iframe | Đánh giá lại khi browser chặn third-party cookies | Top-level redirect/BFF có thể đáng tin hơn |
| Nhiều IdPs/tenant | Registration allowlist, identity theo issuer+sub | Chống mix-up, account linking sai |
| Logout nhiều RP | RP-initiated hoặc back-channel theo provider | Mapping session, logout JWT validation, browser limitations |
| M2M API cùng hệ thống | Chain Bearer-only tách browser chain | Không cookie fallback, issuer/audience/scope |
| RP scale nhiều node | Shared session store hoặc affinity | Correlation TTL/replay và key/version consistency |

### 24.1. Chọn SameSite theo luồng, không theo khẩu hiệu

- **`Lax`** thường thích hợp với **top-level GET callback** của RP session-based.
- **`Strict`** có thể làm mất session trên callback/deep links cross-site.
- **`None; Secure`** có thể cần khi **cross-site POST/iframe** thực sự yêu cầu cookie, nhưng mở rộng tình huống cookie được browser tự gửi nên CSRF/Origin/Fetch Metadata phải được đánh giá, và 3PC rules vẫn có thể ảnh hưởng.
- Có thể thiết kế **cookie correlation chuyên biệt**, nhưng phải có browser binding, cryptographic integrity khi cần, TTL, one-time use, replay protection và repository tương ứng; không dùng state parameter không ràng buộc làm thay session.
- Không dựa vào SameSite browser defaults hoặc ngoại lệ POST ngắn hạn làm nền tảng bảo mật.

### 24.2. Origin/Fetch Metadata filters có thể chặn login hợp lệ

Một ứng dụng có thể áp `Origin`, `Referer`, `Sec-Fetch-Site` như defense-in-depth cho POST. Nhưng callback OIDC/SAML là **cross-site hợp lệ**, và OAuth2 GET callback có thể không chứa Origin như fetch.

Thiết kế theo endpoint:

- Business POST dùng cookie: CSRF token + authz, bổ sung Origin/Fetch Metadata khi phù hợp.
- OAuth GET callback: state/nonce/PKCE và session correlation.
- OIDC/SAML POST callback: chỉ ngoại lệ CSRF hẹp nếu đủ protocol validation và cookie design.
- Back-channel logout: verify JWT logout token/server trust.
- M2M Bearer API: Bearer validation + scope/tenant, không xem Origin là authentication.

Không sử dụng `Origin` hoặc `Sec-Fetch-Site` làm bằng chứng thay thế OAuth state.

## 25. Checklist triển khai đăng nhập liên kết

| Kiểm tra | Tiêu chí đạt |
|---|---|
| **OIDC provider** | Issuer URL được allowlist, metadata/JWKS từ nguồn tin cậy |
| **ClientRegistration** | `client_id`, authentication method, scopes và grant type đúng |
| **Redirect URI** | Chính xác public HTTPS scheme, host, port/path, registrationId |
| **Proxy trust** | Forwarded headers chỉ từ proxy quản lý, direct backend được hạn chế |
| **Authorization request** | State entropy cao, được lưu ràng buộc browser/session |
| **State validation** | State callback phải khớp expected request, one-time/replay protection |
| **Nonce** | OIDC nonce phát/so đúng theo flow, không dùng thay CSRF token |
| **PKCE** | `S256` được dùng khi cần, code verifier bảo mật và khớp challenge |
| **Authorization code** | Đổi một lần tại token endpoint đúng client/redirect URI |
| **ID token** | Signature, issuer, audience/client ID, time, nonce và required claims được xác minh |
| **Access token** | Không dùng ID token thay access token Resource API; audience/scope đúng |
| **Identity linking** | Mapping theo issuer+subject, không chỉ email/username không verify |
| **Cookie Session** | `Secure; HttpOnly; SameSite`, Domain/Path/expiry đúng callback |
| **GET callback** | `SameSite=Lax` được test với top-level cross-site GET |
| **POST callback** | Nếu có `form_post`, handler/cookie/protocol/CSRF exception hẹp đều được test |
| **Pre-login session** | TTL đủ cho MFA/consent nhưng có giới hạn, cleanup sau expiry |
| **Post-login session** | Session fixation protection/rotation và security context persistence |
| **Browser CSRF** | POST nghiệp vụ/logout có token; OAuth state không thay nó |
| **CORS** | Chỉ mở khi SPA fetch khác origin; callback navigation không đòi CORS |
| **CSP** | Đặt trên HTML RP thật, bảo vệ script/form/embedding theo UX |
| **HSTS/TLS** | HTTPS end-to-end tới public RP/IdP, proxy headers nhất quán |
| **Referrer/cache** | Code/state/tokens không được lộ qua Referrer/log/shared cache |
| **Logout** | Phân biệt local, RP-initiated, front-channel và back-channel |
| **Logout token** | Back-channel JWT được validate đúng events/iss/aud/sid/sub và replay |
| **Multi-node** | Session store/affinity và key/serializer consistent |
| **Multi-tab** | Hai flows không nhầm state hoặc principal, có UX khi correlation hết hạn |
| **Multi-provider** | Registration/issuer correlation và account mapping chống mix-up |
| **M2M isolation** | Callback ở browser chain; bearer-only API không chấp nhận session fallback |
| **Unit/integration** | Tests có positive/negative state, nonce, PKCE, issuer, scope và CSRF |
| **Browser E2E** | Test SameSite trên browser được hỗ trợ, không chỉ MockMvc/WebTestClient |
| **Logging** | Redact code/state, cookies, ID/access/refresh tokens, client secret |
| **Change review** | Khi thay response_mode, domain, proxy, IdP, browser SDK, SameSite hoặc logout phải chạy regression suite |

### 25.1. Phiếu kiểm tra một lần login

Dùng khi điều tra một sự cố:

~~~text
Registration ID: corporate
Expected issuer: https://login.identity.example/realms/corporate
RP public origin: https://app.example.com
Authorization URL: /oauth2/authorization/corporate
Callback URL: /login/oauth2/code/corporate
Response mode: query (GET) / form_post (POST)
RP cookie: JSESSIONID hoặc SESSION
Cookie SameSite: Lax/Strict/None
Cookie Domain/Path/Secure/expiry:
Security chain: browser oauth2Login
Correlation repository: HttpSession/WebSession/custom
Node/session store: local/shared
State error: missing/mismatch/replay/none
Token validation error: iss/aud/nonce/signature/exp/none
Login result: authenticated/denied
POST business CSRF after login: pass/denied
Logout model: local/RP-initiated/front-channel/back-channel
~~~

**Không điền giá trị thực** của `state`, code, cookie ID, token hoặc secret vào phiếu hỗ trợ. Chỉ ghi **loại lỗi** và correlation ID an toàn.

### 25.2. Quy trình chẩn đoán khi login loop

~~~mermaid
flowchart TD
    A[RP bắt đầu OAuth2 login] --> B{Location tới IdP đúng không?}
    B -->|Không| C[Kiểm ClientRegistration, redirect URI, trusted proxy]
    B -->|Có| D{IdP trả callback method/path đúng không?}
    D -->|Không| E[Kiểm response_mode và registered redirect URI]
    D -->|Có| F{Cookie RP có trong callback không?}
    F -->|Không| G[Kiểm SameSite, Domain, Path, Secure, TTL, browser policy]
    F -->|Có| H{Authorization request còn trong session không?}
    H -->|Không| I[Session store, node affinity, timeout, concurrent flows]
    H -->|Có| J{State/PKCE/ID token checks pass?}
    J -->|Không| K[State, code, nonce, issuer, audience, JWKs, time]
    J -->|Có| L{Authenticated session sau redirect hoạt động?}
    L -->|Không| M[Session rotation, Set-Cookie, proxy, SecurityContext]
    L -->|Có| N[Kiểm authorization nghiệp vụ và CSRF sau login]
~~~

Sơ đồ chỉ là cây chẩn đoán; browser có thể đồng thời bị nhiều lỗi. Khi callback là cross-site POST, phải kiểm **CSRF filter và handler có hỗ trợ method** trước cả bước tìm state.

## 26. Bài tập thực hành

### Bài 1 — IdP callback form_post và session cookie Lax

**Bối cảnh:** RP giữ expected authorization request trong HttpSession, dùng `SameSite=Lax`. IdP trả code/state bằng POST form từ site khác. Spring báo `authorization_request_not_found`.

**Nhiệm vụ:** Nêu ít nhất bốn điều cần kiểm trước khi chỉnh CSRF.

**Đáp án gợi ý:** Browser không gửi Lax cookie trên cross-site POST; kiểm `Set-Cookie`, Path/Domain/Secure/expiry và POST Network. Tiếp theo kiểm authorization request repo/session store, callback filter hỗ trợ form_post, CSRF filter có chặn POST và state/nonce/PKCE validation. Chỉ cân nhắc None/Secure/correlation redesign và ngoại lệ CSRF hẹp khi đã đánh giá đầy đủ, không tắt toàn app.

### Bài 2 — State và CSRF token có dùng chung được không?

**Bối cảnh:** Developer dùng OAuth state thành hidden `_csrf` trên form đổi mật khẩu sau login.

**Đáp án gợi ý:** Không. `state` bảo vệ authorization response của một OAuth flow; `_csrf` được Spring repository đối chiếu cho unsafe browser business requests. Vòng đời/điểm tin cậy khác nhau.

### Bài 3 — Session mất vì đổi hostname

**Bối cảnh:** GET khởi tạo từ `https://app.example.com`, callback được IdP gửi tới `https://www.app.example.com`. Cookie `JSESSIONID` là host-only.

**Đáp án gợi ý:** Cookie không gửi tới hostname mới, nên repository không tìm expected request. Đăng ký redirect đúng host, cấu hình proxy/baseUrl nhất quán; không mở Domain rộng nếu không cần.

### Bài 4 — Hai IdPs cùng claim subject

**Bối cảnh:** `corporate` phát `sub=123` cho Alice, `partner` cũng phát `sub=123` cho Bob; ứng dụng map user chỉ bằng `sub`.

**Đáp án gợi ý:** Đó là account confusion; subject có scope theo issuer. Lưu identity mapping theo **issuer+sub** và account linking có kiểm soát. Kiểm state/registration/issuer không trộn provider.

### Bài 5 — Login pass, POST business bị 403

**Bối cảnh:** Sau OIDC login và session rotation, tab cũ dùng CSRF token trước login để gửi `POST /profile`.

**Đáp án gợi ý:** Token/session đã đổi vòng đời; lấy token mới theo phiên authenticated. 403 có thể đúng; không bỏ CSRF vì OAuth state đã kiểm trong callback.

### Bài 6 — CORS wildcard để “sửa callback”

**Bối cảnh:** GET callback từ IdP lỗi, nhóm triển khai mở `Access-Control-Allow-Origin: *` và `Allow-Credentials: true` cho tất cả endpoint.

**Đáp án gợi ý:** Callback là top-level navigation, CORS không phải rào cản đó; wildcard+credentials không hợp lệ trong credentialed CORS. Điều tra session cookie, SameSite, state repository, redirect URI, không mở CORS bừa bãi.

### Bài 7 — Logout RP thành công nhưng IdP còn phiên

**Bối cảnh:** User POST logout với CSRF, RP xóa session. User bấm login và được vào thẳng vì IdP SSO session vẫn còn.

**Đáp án gợi ý:** Local logout không đồng nghĩa federated logout ở IdP. Nếu business cần IdP logout, tích hợp RP-initiated logout được provider hỗ trợ; không giả định mọi RP khác cũng logout. Với đồng bộ nhiều RP, đánh giá back-channel và ràng buộc phiên.

### Bài 8 — Back-channel logout bị triển khai thiếu kiểm chứng

**Bối cảnh:** Developer cho phép POST `/oidc/backchannel-logout` với JSON `userId` bất kỳ và xóa session user đó.

**Đáp án gợi ý:** Đây là endpoint xóa phiên không xác thực giao thức; attacker có thể forced logout nhiều user. Cần logout token JWT signature/issuer/audience/events/sid-sub/replay validation và session mapping, ngoại lệ CSRF chỉ dành cho endpoint protocol được bảo vệ thích hợp.

### Bài 9 — Redirect URI bị host poisoning

**Bối cảnh:** RP sau reverse proxy dùng `X-Forwarded-Host` từ client để tạo `{baseUrl}`, và attacker đặt host ngoài.

**Đáp án gợi ý:** Strip/overwrite forwarded headers tại trusted proxy, hạn chế direct backend access, validate Host/public domain allowlist và đăng ký redirect URI chính xác. Không dựa vào forwarded headers chưa tin cậy.

### Bài 10 — Silent login iframe chỉ fail trên một browser

**Bối cảnh:** Top-level OIDC login chạy ổn, hidden iframe login thất bại khi privacy settings chặn third-party cookies.

**Đáp án gợi ý:** Đây có thể là hạn chế cookie của IdP trong third-party context, không phải callback state trên top-level flow. Dùng top-level navigation hoặc kiến trúc BFF/refresh strategy được IdP hỗ trợ; không disable nonce/PKCE/state.

## 27. Câu hỏi tự đánh giá

**Câu 1.** Vì sao `SameSite=Lax` thường phù hợp hơn `Strict` với OIDC top-level GET callback?

**Đáp án:** Browser có thể gửi cookie Lax trên top-level cross-site navigation bằng safe GET, giúp RP tìm session/correlation của authorization request. Strict thường không gửi cookie trong navigation đến từ site khác.

**Câu 2.** Vì sao `response_mode=form_post` có thể làm RP mất state khi dùng cookie Lax?

**Đáp án:** Đây là cross-site unsafe POST từ trang IdP về RP; browser thường không gửi Lax cookie, nên session-backed authorization request không được tìm lại. Handler và CSRF filter còn phải được cấu hình phù hợp.

**Câu 3.** Có thể thay `state` bằng `nonce` được không?

**Đáp án:** Không. State liên kết authorization response với request do client khởi tạo; nonce ràng buộc ID token OIDC với authentication request theo flow. Chúng giải quyết các nguy cơ giao thức liên quan nhưng khác nhau.

**Câu 4.** PKCE `code_verifier` có phải access token không?

**Đáp án:** Không. Nó là secret do client tạo để chứng minh quyền đổi authorization code gắn với `code_challenge`. Access token do Authorization Server phát sau khi code exchange hợp lệ.

**Câu 5.** Sau login OIDC, browser POST đổi mật khẩu có còn cần CSRF token?

**Đáp án:** Có nếu authentication của RP dựa vào session cookie browser tự gửi. OAuth state chỉ bảo vệ login protocol, không thay CSRF cho POST nghiệp vụ.

**Câu 6.** GET callback qua IdP có cần `Access-Control-Allow-Origin` để redirect chạy không?

**Đáp án:** Không. Đây là top-level browser navigation. CORS chủ yếu áp dụng khi JavaScript fetch/XHR cross-origin, không phải khi browser theo 302 tới callback.

**Câu 7.** Nếu cookie `HttpOnly` không xuất hiện trong `document.cookie`, có phải session không tồn tại?

**Đáp án:** Không. HttpOnly cố ý ngăn JS đọc; browser vẫn có thể gửi cookie trong request khi scope/SameSite/Secure cho phép. Kiểm ở Network/Storage, không giảm HttpOnly.

**Câu 8.** Tại sao `redirect_uri_mismatch` phải được sửa ở public base URL/IdP registration chứ không dùng wildcard?

**Đáp án:** Authorization code phải chỉ trở về endpoint được cấp phép. URI quá rộng tạo nguy cơ lộ code và open redirect. RP/IdP cần URL chính xác, forwarded headers tin cậy.

**Câu 9.** `oidcLogin()`/`mockOidcLogin()` test helper có chứng minh chữ ký ID token đúng không?

**Đáp án:** Không. Helper mô phỏng authenticated OIDC principal, bỏ qua code exchange, ID token cryptographic validation, nonce/state và browser cookie policy. Cần IdP test issuer và browser/integration tests.

**Câu 10.** Nếu callback state sai nhưng ID token có chữ ký đúng thì RP có nên login không?

**Đáp án:** Không. State/correlation sai có thể là login CSRF/response injection hoặc nhầm flow. Không tạo authenticated session chỉ vì token ở bước khác có chữ ký hợp lệ.

**Câu 11.** Vì sao identity mapping chỉ theo `sub` không đủ khi dùng nhiều IdPs?

**Đáp án:** `sub` có phạm vi theo issuer; hai IdPs có thể phát cùng subject string cho hai người khác nhau. Mapping theo issuer+sub và account linking policy mới tránh nhầm.

**Câu 12.** Local logout của RP có buộc logout tại IdP và mọi RP khác không?

**Đáp án:** Không. Local logout dọn phiên RP. RP-initiated/front-/back-channel logout là các cơ chế riêng, cần hỗ trợ provider và validation/UX phù hợp.

**Câu 13.** Tại sao iframe silent SSO có thể fail dù top-level login pass?

**Đáp án:** Trong iframe, IdP cookie có thể bị chặn như third-party cookie, còn top-level navigation tới IdP có cookie context khác. Không suy từ một flow sang flow còn lại.

**Câu 14.** Spring Security Servlet và Reactive dùng cùng session repository mặc định không?

**Đáp án:** Không. Servlet thường dùng HttpSession-backed OAuth2 authorization request repository; WebFlux thường dùng WebSession-backed reactive repository. Cookie/CSRF/security chain APIs cũng khác.

**Câu 15.** Một back-channel logout POST không có Spring CSRF token có thể được chấp nhận dựa trên điều gì?

**Đáp án:** Chỉ khi endpoint giao thức có ngoại lệ hẹp và xác minh đầy đủ **logout token**/issuer/audience/events/sid-sub/replay, mapping session và quyền server-to-server. Không biến endpoint thành POST unauthenticated tùy ý.

**Câu 16.** Nếu GET authorization request bắt đầu ở node A và callback đến node B, có thể tắt state validation để khắc phục không?

**Đáp án:** Không. Phải dùng shared session/correlation store hoặc affinity có thiết kế, TTL và replay safety. Bỏ state làm mất phòng vệ login CSRF.

**Câu 17.** `SameSite=None; Secure` có bảo đảm iframe SSO chạy trên mọi browser không?

**Đáp án:** Không. Browser privacy controls có thể chặn/partition third-party cookies; None/Secure chỉ đáp ứng một điều kiện cho cookie cross-site.

**Câu 18.** Có thể cho `GET /logout` trực tiếp xóa phiên thay POST không?

**Đáp án:** Không nên trong session browser app vì GET có thể bị kích hoạt từ site khác, link/prefetch. POST logout kèm CSRF giúp tránh forced logout; GET có thể hiển thị trang xác nhận.

**Câu 19.** Vì sao một callback redirect từ IdP được phép cross-site trong Fetch Metadata policy?

**Đáp án:** Vì federated login yêu cầu browser đi từ IdP về RP. Chặn toàn bộ `Sec-Fetch-Site: cross-site` có thể phá protocol; thay vào đó cho đúng callback path và thực hiện state/nonce/PKCE/token validation nghiêm ngặt.

**Câu 20.** Điều gì phải được bảo vệ trong logs khi login OIDC qua query callback?

**Đáp án:** Authorization code, state, session cookie, ID/access/refresh tokens, client secret, PKCE verifier và signed URLs/query nhạy cảm. Chỉ ghi metadata lỗi/correlation ID an toàn.

## Kết luận

**Đăng nhập liên kết với SameSite, redirect và các token giao thức** là bài toán phối hợp **browser cookie policy** với **OAuth2/OIDC protocol validation** và **Spring Security session lifecycle**. Với server-side RP, top-level Authorization Code flow đưa browser từ ứng dụng sang IdP rồi trở lại callback; RP phải tìm đúng authorization request đã lưu và kiểm state, code/PKCE, ID token issuer/audience/nonce/signature/timestamps trước khi tạo phiên đã xác thực.

**`SameSite=Lax` thường phù hợp với cross-site top-level GET callback**, nhưng không nên được kỳ vọng gửi cookie RP trên cross-site POST `form_post`; `Strict` có thể làm mất phiên ngay cả ở GET redirect, còn `None; Secure` không tự khắc phục handler/CSRF hoặc giới hạn third-party cookies. Khi dùng SAML POST binding, các vấn đề cookie có thể tương tự nhưng **SAML signature, RelayState và InResponseTo** phải được xác minh theo **giao thức SAML**, không dùng OAuth state/nonce thay thế.

Một khi RP tạo **session cookie** cho browser, mọi unsafe business request và local logout **vẫn cần CSRF token**, dù OIDC login trước đó đã chống login CSRF bằng state. CORS không phải điều kiện cho top-level redirect/token endpoint server-to-server; CSP, HSTS, HTTP firewall và reverse proxy phải đúng nơi phát response và trust boundary. Trên **Servlet** dùng `HttpSecurity/oauth2Login/HttpSession`; trên **Reactive/WebFlux** dùng `ServerHttpSecurity/oauth2Login/WebSession`, với kiểm thử callback/cookie thực tế trên browser.

**Bằng chứng cần có** không chỉ là đăng nhập thành công, mà là callback thiếu/sai state/nonce/PKCE/issuer bị từ chối, cookie tương quan không bị bỏ qua khi thiếu, session rotation/login/logout đúng, CSRF của POST nghiệp vụ vẫn hiệu lực, và không lộ code/tokens qua URL logs. Đây là cách vận dụng nhất quán các lớp phòng vệ của **SPRING_SECURITY_HTTP_PROTECTION** trong **Tích hợp ứng dụng**.

## Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Login Core (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): `oauth2Login` và ClientRegistration.
- [Spring Security — Advanced OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): authorization endpoint, redirect endpoint, request repository và tùy biến.
- [Spring Security — OAuth 2.0 Login Core (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html): Reactive OAuth2 Login và WebSession.
- [Spring Security — Advanced OAuth 2.0 Login (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html): Reactive client/repository/callback.
- [Spring Security — Servlet CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): token cho unsafe browser requests và login/logout.
- [Spring Security — Reactive CSRF Protection](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): WebSession/`CsrfWebFilter`.
- [Spring Security — Servlet Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): local logout, CSRF và logout handlers.
- [Spring Security — Servlet SAML2 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SAML response, ACS và SP login.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, nonce, authorization code flow và response modes.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): end-session flow.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): logout token và session identifiers.
- [OAuth 2.0 RFC 6749](https://www.rfc-editor.org/rfc/rfc6749): authorization code, state và redirect URI.
- [PKCE RFC 7636](https://www.rfc-editor.org/rfc/rfc7636): `code_verifier` và `S256` challenge.
- [OAuth 2.0 Security Best Current Practice RFC 9700](https://www.rfc-editor.org/rfc/rfc9700): authorization security, mix-up, code handling và redirect protections.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): giảm nguy cơ issuer mix-up.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): `SameSite`/`Secure`/`HttpOnly`/`Domain`/`Path`.
- [MDN — Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy): ranh giới origin.
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): top-level navigation so với cross-origin JavaScript requests.
- [OWASP — OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): OAuth client security, state/PKCE và redirect practices.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF, SameSite và defense-in-depth.
