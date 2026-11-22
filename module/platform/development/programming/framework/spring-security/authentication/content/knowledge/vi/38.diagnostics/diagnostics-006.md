# Mất cookie, sai SameSite hoặc URL công khai không khớp proxy — chẩn đoán Spring Security

## 1. Tình huống và mục tiêu

Ứng dụng Spring Boot/Spring Security chạy bình thường trên localhost nhưng sau khi deploy sau Nginx, ingress hoặc load balancer lại gặp một trong các triệu chứng:

- Người dùng đăng nhập thành công rồi ngay lập tức bị chuyển về trang login.
- Browser nhận `302` nhiều lần giữa `/login`, trang chủ và Identity Provider (IdP).
- OAuth2/OIDC đăng nhập báo `redirect_uri_mismatch`, `invalid_state_parameter` hoặc không tìm thấy authorization request.
- Session cookie được gửi trong response nhưng request kế tiếp không mang `Cookie` header.
- Cookie vẫn có trong Browser Storage nhưng không được gửi ở một callback cross-site `POST`.
- Ứng dụng phát `Location: http://app:8080/login/oauth2/code/...` hoặc path `/login/...` trong khi người dùng truy cập qua `https://login.example.test/auth/...`.
- Trong môi trường nhiều pod, đăng nhập lúc được lúc không, dù browser đã gửi cookie đúng.

Mục tiêu bài **không phải đoán rồi tắt bảo mật**. Ta cần tìm đúng điểm đứt trong chuỗi:

```text
Browser nhận Set-Cookie?
   |
   +-- KHÔNG -> login chưa thành công / session chưa tạo /
   |            response bị proxy sửa / thuộc tính bị browser từ chối
   |
   +-- CÓ -> Browser đã lưu cookie?
                |
                +-- KHÔNG -> Secure/HTTPS, Domain, Path,
                |            __Host- prefix, SameSite=None thiếu Secure,
                |            third-party policy, quota...
                |
                +-- CÓ -> Request tiếp theo có gửi Cookie không?
                             |
                             +-- KHÔNG -> host/path/scheme/SameSite,
                             |            CORS credentials, cross-site POST,
                             |            iframe/third-party restrictions
                             |
                             +-- CÓ -> Backend còn nhận ra session không?
                                          |
                                          +-- KHÔNG -> expired/invalidated,
                                          |            đổi session ID sau login,
                                          |            sai cookie name,
                                          |            pod khác/session store,
                                          |            SecurityContext không lưu
                                          |
                                          +-- CÓ -> Xem authorization/CSRF/
                                                   OAuth state/redirect URI
```

Với proxy và OAuth2, còn một câu hỏi **độc lập**: backend có biết URL công khai bên ngoài và tạo đúng callback/redirect hay không? Cookie hợp lệ **không sửa được** một `redirect_uri` sinh từ host/scheme/prefix nội bộ.

Ngữ cảnh chính là **Spring Boot 3.x / Spring Security 6.x Servlet, Spring MVC, Java 17+**. Những ví dụ dùng tên miền `example.test` giả lập, không phải tài khoản hoặc dịch vụ có thật. Với WebFlux hoặc Spring Boot 4/Spring Security 7, cần đối chiếu các thuộc tính và API đúng phiên bản.

## 2. Xác định ba loại vấn đề dễ bị trộn lẫn

| Nhóm | Dấu hiệu cụ thể | Thường liên quan |
| --- | --- | --- |
| **Cookie không được lưu** | Response có `Set-Cookie` nhưng Application > Cookies không có | `Secure` trên HTTP, `SameSite=None` thiếu `Secure`, `Domain` không hợp lệ, prefix `__Host-` sai, browser policy |
| **Cookie không được gửi** | Browser có cookie nhưng request không có `Cookie` tương ứng | Domain/host, Path, HTTPS, SameSite, cross-site `POST`/iframe, `fetch(credentials)` |
| **Cookie gửi nhưng không có phiên** | Request có Cookie nhưng server thấy anonymous/không có `SecurityContext` | Session hết hạn, logout/rotation, shared store thiếu, Spring Security session policy hoặc custom save |
| **Public URL sai** | `Location`/`redirect_uri` dùng `http`, host internal, port `8080` hoặc mất `/auth` | Trusted forwarded headers và reverse proxy path rewriting |
| **CSRF hoặc OAuth state lỗi** | `403` CSRF, OAuth callback báo state missing | Cookie không được gửi, state session mất, cross-site POST, hoặc request flow sai |
| **Đăng nhập xong lại redirect** | Browser lặp `302 /login`, mặc dù credentials đúng | Session không persist, cookie không gửi, callback path mismatch hoặc rule bảo vệ sai |

**Thứ tự điều tra đúng:** quan sát **response chứa Set-Cookie → quyết định lưu của browser → request Cookie → backend session lookup → redirect_uri/state/CSRF**. Không bắt đầu bằng việc đặt `SameSite=None` hoặc tắt CSRF trong toàn ứng dụng.

## 3. Hiểu đúng từng ranh giới và thông tin cần ghi nhận

Một deployment có TLS termination và public prefix:

```text
Browser
  https://login.example.test/auth/login
    |
    | TLS, Host: login.example.test
    v
Nginx / Ingress / Load Balancer
    |  public prefix /auth có thể được strip theo cấu hình
    |  X-Forwarded-Proto: https
    |  X-Forwarded-Host: login.example.test
    |  X-Forwarded-Port: 443
    |  X-Forwarded-Prefix: /auth
    v
Spring Boot app
  http://app:8080/login
    |
    +-- Spring Security: Authentication + session context
    +-- Servlet container: Set-Cookie/HttpSession
    +-- OAuth2 client: tạo redirect_uri/callback
    v
Response qua proxy về browser
  Set-Cookie: __Host-SESSION=...; Path=/; Secure; HttpOnly; SameSite=Lax
  Location: https://login.example.test/auth/...
```

Ở ví dụ này, **public base URL** là `https://login.example.test/auth`, trong khi backend tự nhìn thấy `http://app:8080` nếu không xử lý thông tin proxy. Nếu dùng cùng lúc `server.servlet.context-path=/auth` **và** proxy đã strip prefix/cấu hình `X-Forwarded-Prefix=/auth`, có thể vô tình nhân đôi `/auth/auth` hoặc sai mapping. Luôn vẽ rõ đường đi và cách rewrite thực tế.

### Năm giá trị nên xác minh

1. **Browser public URL** trong address bar: scheme, host, port và path.
2. **URL backend thực** mà proxy gọi: scheme, host, port và path sau rewrite.
3. **Forwarded headers đã được proxy tin cậy ghi đè**: `Forwarded` hoặc `X-Forwarded-Proto`/`Host`/`Port`/`Prefix`.
4. **Headers browser thực nhận**: `Set-Cookie`, `Location`, HSTS/CORS và HTTP status.
5. **URI mà Spring OAuth2 client dùng**: `redirect_uri` gửi đến Authorization Server và callback được IdP đăng ký.

Không in raw session ID, authorization code, `state`, CSRF token, password, cookie hoặc access token vào logs để “chẩn đoán”. Khi cần so sánh phiên, dùng chỉ báo boolean, correlation ID và thông tin đã redact.

## 4. Browser có thực sự nhận Set-Cookie không?

Với browser Developer Tools:

1. Mở **Network**, bật Preserve log.
2. Đăng nhập từ trạng thái incognito/test profile; tìm **response** bắt đầu/hoàn tất authentication (có thể là nhiều lần `302`).
3. Kiểm tra `Response Headers → Set-Cookie` ở **từng response**, không chỉ response cuối.
4. Xem tab **Cookies** của request và phần cảnh báo **Blocked/Excluded Reasons** nếu browser cung cấp.
5. Mở **Application/Storage → Cookies** theo đúng host.
6. Theo dõi **request tiếp theo** và tab Request Cookies để xem cookie có thực sự được gửi.

### Vì sao không thấy Set-Cookie ở response cuối?

Một login thành công thường gồm:

```text
POST /login
   <- 302, Set-Cookie: SESSION=...  (ID có thể đổi sau login)
GET /home
   <- 200, không bắt buộc có Set-Cookie
```

Nếu chỉ inspect `GET /home`, bạn có thể nhầm “server không tạo cookie”. **Preserve log** giúp nhìn thấy Set-Cookie trên response ở giữa chuỗi redirects.

`Set-Cookie` là **forbidden response header** đối với JavaScript Fetch API, nên `response.headers.get("set-cookie")` trên frontend thường trả null dù Network tab có thấy cookie. Đây là cơ chế browser bảo vệ header, không phải bằng chứng server không phát cookie.

### Nếu response không có Set-Cookie

- Đăng nhập có thật sự thành công không? Kiểm tra HTTP status, `Location` và authentication failure handler.
- Session có được tạo không? `SessionCreationPolicy.STATELESS`, `NullSecurityContextRepository` hoặc filter custom có thể khiến không có server session.
- Với Spring Security 6.x, **custom authentication flow** nếu tự đặt `SecurityContextHolder` có thể cần gọi `SecurityContextRepository.saveContext(...)`; chỉ gán ThreadLocal không bảo đảm request kế tiếp authenticated.
- Proxy/CDN có thay đổi/xóa `Set-Cookie` hoặc cache response có authentication không?
- Browser có nhận response đúng endpoint không, hay redirect sang host khác rồi cookie xuất hiện ở host mới?
- Session ID thay đổi sau login là bình thường theo **session fixation protection**. So sánh cookie mới sau login, không dùng ID anonymous cũ.

**Không đề xuất sửa bằng cách tắt session fixation protection.** Mục đích của rotation là chống attacker biết ID từ trước khi nạn nhân login.

## 5. Vì sao Set-Cookie có mặt mà browser vẫn không lưu?

Một cookie mẫu **không chia sẻ cho subdomains**:

```http
Set-Cookie: __Host-SESSION=redacted; Path=/; Secure; HttpOnly; SameSite=Lax
```

`redacted` là chuỗi mô tả đã ẩn bí mật, không phải giá trị session để dùng thật.

### Thuộc tính và lỗi chính

| Thuộc tính | Quy tắc | Lỗi chẩn đoán |
| --- | --- | --- |
| `Secure` | Cookie chỉ được gửi trên HTTPS (browser có ngoại lệ localhost) | Phát cookie secure từ origin HTTP công khai hoặc truy cập URL HTTP |
| `HttpOnly` | JavaScript không truy cập cookie qua `document.cookie` | Người phát triển tưởng cookie mất khi JS không thấy |
| `SameSite=Lax` | Gửi trong same-site; một số top-level cross-site safe navigation, ví dụ GET | OIDC callback dùng cross-site POST không mang cookie |
| `SameSite=Strict` | Chỉ gửi khi ngữ cảnh same-site | Từ email/external site nhấp top-level link rồi không gửi cookie |
| `SameSite=None` | Cho phép theo SameSite cả same-site và cross-site | Phải có `Secure`; vẫn chịu third-party cookie policy |
| `Domain` | Nếu không có: cookie host-only | Đặt `Domain=internal.local` khi browser ở `login.example.test` sẽ bị từ chối |
| `Path` | Browser chỉ gửi cho các path tương ứng | Cookie có Path=/api nhưng callback ở /auth |
| `Max-Age` / `Expires` | Browser có thể xóa cookie khi hết hạn hoặc `Max-Age=0` | Cookie bị xóa bởi response logout/redirect hoặc clock/policy |
| Prefix `__Host-` | `Secure`, origin HTTPS, `Path=/`, **không có Domain** | Có `Domain` hoặc `Path=/auth` khiến browser từ chối |

**Browser quyết định** có chấp nhận cookie không. Header Set-Cookie nhìn hợp lý trong `curl` không đủ để chứng minh browser đã lưu; phải xem DevTools và browser policy.

### Host-only và Domain

- Cookie phát từ `login.example.test` **không có `Domain`** thuộc riêng host ấy.
- `Domain=example.test` có thể làm cookie được gửi tới các subdomain đủ điều kiện, mở rộng bề mặt tấn công; không nên dùng để “sửa đăng nhập” nếu không thật sự cần.
- `Domain=app:8080` không đúng: thuộc tính Domain **không bao gồm port**. Browser dùng hostname ngoài, không dùng hostname backend nội bộ.
- Hai cookie trùng tên nhưng khác Path/Domain có thể cùng xuất hiện; server nhận `Cookie` header không có các attribute Path/Domain kèm theo, dễ gây đọc sai ID. Xem cookie store và loại bỏ duplicate cũ một cách có kiểm soát.
- Cookie phát từ `login.example.test` không tự chạy sang `api.another.test`; nếu dùng nhiều domain, cần thiết kế authentication/cross-origin, không mở rộng `Domain` vượt registrable domain.

### Prefix __Host-

Với `__Host-SESSION`, browser hỗ trợ prefix sẽ từ chối:

```http
# SAI: có Domain
Set-Cookie: __Host-SESSION=redacted; Path=/; Domain=example.test; Secure

# SAI: Path khác "/"
Set-Cookie: __Host-SESSION=redacted; Path=/auth; Secure

# ĐÚNG VỀ RULE PREFIX:
Set-Cookie: __Host-SESSION=redacted; Path=/; Secure; HttpOnly; SameSite=Lax
```

Cookie prefix chỉ ràng buộc **cách trình duyệt nhận cookie**, không xác nhận người dùng đã authenticated hay session trên server còn hợp lệ. Nếu app chạy dưới public prefix `/auth`, `Path=/` vẫn là một lựa chọn hợp lệ cho prefix nhưng gửi cookie trên toàn host; cần đánh giá phạm vi host và không trộn nhiều ứng dụng độc lập cùng hostname một cách thiếu kiểm soát.

## 6. Phân biệt SameSite, same-origin, cross-origin và cross-site

**Origin** thường là `scheme + host + port`. **Site** trong SameSite dùng khái niệm *schemeful site* (scheme và registrable domain phù hợp), nên hai origin khác nhau vẫn có thể cùng site.

| Tình huống | Cross-origin? | Cross-site? | Hệ quả |
| --- | --- | --- | --- |
| `https://app.example.test` → `https://api.example.test` | Có | Thường **không**, nếu cùng registrable domain | Cần CORS nếu JavaScript fetch, SameSite=Lax có thể gửi |
| `https://app.example.test` → `https://other.test` | Có | Có | SameSite=Lax ngăn nhiều request |
| `http://app.example.test` → `https://app.example.test` | Có | Schemeful site có thể khác | `Secure` và SameSite phải xét cả scheme |
| `https://login.example.test` → `https://login.example.test` | Không | Không | Cookie Path/TTL/session state vẫn có thể lỗi |

**CORS không thay SameSite**, và **SameSite không thay CSRF protection**. Một subdomain bị compromise có thể là same-site dù khác origin. Khi dùng cookie-authenticated APIs, cần giữ CSRF token/Origin checks theo threat model.

### SameSite=Lax với redirect OIDC

- Top-level navigation `GET` từ IdP về ứng dụng thường được cookie `SameSite=Lax` cho phép.
- Cross-site `POST`, ví dụ OIDC response mode `form_post`, **không** được gửi cookie có **SameSite=Lax explicit** theo quy tắc chuẩn.
- Nếu **không khai báo** SameSite, một số browser áp dụng Lax-by-default với ngoại lệ POST rất ngắn cho cookie mới. Không dựa vào ngoại lệ browser này để thiết kế authentication.
- Với `SameSite=Strict`, callback/điều hướng từ IdP có thể mất cookie ngay cả ở GET top-level.
- `SameSite=None; Secure` cho phép theo quy tắc SameSite nhưng **không đảm bảo** cookie luôn được gửi: browser có thể hạn chế third-party cookies, tracking protection hoặc iframe.

**Không áp dụng `SameSite=None` cho mọi cookie một cách vô điều kiện.** Khi flow thực sự cần cross-site POST/iframe, đánh giá cookie scope cụ thể và giữ CSRF, OAuth `state`, OIDC `nonce`, PKCE khi phù hợp cùng security headers. Với nhiều hệ thống, chuyển sang top-level GET callback hoặc thiết kế OAuth state storage đúng là phương án đáng cân nhắc.

## 7. Cookie được lưu nhưng không xuất hiện trong request

Kiểm tra **request cụ thể**, không chỉ tab Storage. Ví dụ cookie `Secure` cho `login.example.test`:

```text
Browser Storage:
  __Host-SESSION
    Host = login.example.test
    Path = /
    Secure = true
    SameSite = Lax

Request A: https://login.example.test/auth/home
  Cookie được gửi nếu hợp lệ và không bị chính sách khác chặn.

Request B: http://login.example.test/auth/home
  Cookie Secure không được gửi qua HTTP công khai.

Request C: https://other.example.test/auth/home
  Cookie host-only cho login.example.test không được gửi.

Request D: cross-site POST callback tới login.example.test
  SameSite=Lax explicit thường ngăn gửi cookie.
```

### Những nguyên nhân không thuộc SameSite

- Cookie Path là `/portal` nhưng request đi vào `/auth`.
- Response logout gửi `Set-Cookie` với `Max-Age=0`, browser xóa cookie ngay.
- Hai ứng dụng dùng chung cookie name và host, mỗi app ghi đè ID của app kia.
- Browser ở chế độ privacy/third-party restriction hoặc extension chặn cookies.
- `fetch()`/Axios cross-origin không bật credentials; CORS response không cho phép credentials.
- Browser truy cập URL với host thay đổi liên tục, ví dụ `www.example.test` và `example.test`.
- Có redirect từ HTTPS sang HTTP, nên cookie Secure không được gửi ở bước sau.
- Cookie mới sau session fixation rotation thay ID cũ; client tự giữ hoặc gửi lại giá trị cũ.
- Session cookie đã hết Max-Age/expires hoặc browser policy đã xóa.
- Server sử dụng khác cookie name so với cookie client gửi (ví dụ `JSESSIONID` vs `SESSION`, Spring Session hay custom setup).

**Không lấy `document.cookie` làm kiểm tra có session cookie hay không** khi cookie có `HttpOnly`: JavaScript không được nhìn thấy nó là hành vi đúng.

## 8. SPA, fetch credentials, CORS và cookie

Đối với frontend `https://app.example.test` gọi API `https://api.example.test`, request là **cross-origin** dù có thể same-site. Browser Fetch API mặc định dùng credentials mode `same-origin`; vì vậy cần opt-in rõ cho cross-origin cookies.

Ví dụ **trên frontend thực sự được phép gọi API**:

```javascript
const response = await fetch(
  "https://api.example.test/account",
  {
    method: "GET",
    credentials: "include"
  }
);
```

Ở backend/API và gateway cần xét:

- `Access-Control-Allow-Origin` phải khớp **origin đã cho phép cụ thể** khi dùng credentials, không phải wildcard `*`.
- `Access-Control-Allow-Credentials: true` khi đáp ứng CORS credentialed request đúng.
- Các preflight `OPTIONS` nếu có không nên bị authentication chặn sai quy trình; vẫn cần CORS allowlist đúng.
- Cookie phải có host/path/secure/samesite tương thích **request đích**, không phải chỉ origin nơi JavaScript chạy.
- Với cross-site thực sự, `SameSite=None; Secure` có thể cần nhưng browser third-party restrictions vẫn có thể chặn.
- Với POST/PUT/DELETE dựa cookie authentication, **CSRF protection vẫn cần**. CORS policy không thay được anti-CSRF.

**Nếu frontend và backend cùng origin**, không cần nới CORS hoặc SameSite để chữa một lỗi không liên quan. Đọc Network request để biết chính xác HTTP request hiện có mang cookie hay chưa.

## 9. Public URL không khớp proxy: lỗi khác với cookie

Spring Boot chạy tại `http://app:8080`, nhưng người dùng truy cập qua `https://login.example.test/auth`. OAuth2 login có thể tạo authorization request:

```text
Sai (backend-internal):
  redirect_uri=http://app:8080/login/oauth2/code/demo

Đúng (public):
  redirect_uri=https://login.example.test/auth/login/oauth2/code/demo
```

IdP thường yêu cầu `redirect_uri` trùng **đúng giá trị đã đăng ký** về scheme/host/port/path; mismatch dẫn đến lỗi trước khi callback đến được app. Một hostname khác, port sai hoặc thiếu public prefix đều đủ gây lỗi.

Cần kiểm tra hai giá trị riêng biệt:

1. `redirect_uri` **thực được gửi** trong authorization request đến IdP; có thể nhìn thấy URL đã percent-encode trong Network (giữ bí mật `state`/nonce khi chia sẻ logs).
2. Redirect URI **đã đăng ký** tại IdP (application/client registration).

Nếu hai giá trị không trùng, chỉnh forwarded headers/context-prefix/config registration. **Không** dùng wildcard redirect URIs hoặc tắt kiểm tra redirect URI ở IdP chỉ để login “chạy lại”.

### Ý nghĩa của baseUrl trong oauth2Login

Spring Security OAuth2 Client hỗ trợ các mẫu có biến như:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            client-id: "registered-demo-client"
            client-secret: "read-from-secret-manager-in-real-deployments"
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          demo:
            issuer-uri: "https://idp.example.test/realms/demo"
```

**Đây là phần cấu hình minh họa**, không phải OIDC app có thể chạy ngay: client registration, secret, issuer metadata, user store/certificates phải được cung cấp thật qua secret manager. Trong production không để plaintext client-secret trong repository, kể cả khi hướng dẫn có chuỗi minh họa.

`{baseUrl}` phụ thuộc thông tin request bên ngoài mà Spring nhìn thấy sau xử lý proxy. Nếu không có forwarded headers, nó có thể là HTTP/backend hostname thay vì HTTPS/public domain. `{registrationId}` phải tương ứng với route callback và client registration.

Cũng phải khớp callback xử lý bởi Spring Security `/login/oauth2/code/{registrationId}`, hoặc nếu tùy biến redirect endpoint thì phải cấu hình cùng đường vào `oauth2Login().redirectionEndpoint(...)`. Không sửa một bên rồi quên bên còn lại.

## 10. Spring Boot 3.5: cấu hình forwarded headers và cookie

Một cấu hình **Servlet app sau reverse proxy đáng tin**:

```yaml
server:
  # Spring Framework ForwardedHeaderFilter / forwarded info:
  forward-headers-strategy: framework

  # Với Tomcat và SSL termination tại proxy, tránh context-root
  # redirect xảy ra trước khi X-Forwarded-Proto được xem xét:
  tomcat:
    redirect-context-root: false

  servlet:
    session:
      tracking-modes: cookie
      timeout: 20m
      cookie:
        name: "__Host-SESSION"
        path: /
        secure: true
        http-only: true
        same-site: lax
```

**Tác dụng và điều kiện:**

- `server.forward-headers-strategy=framework` để framework xử lý `Forwarded`/`X-Forwarded-*`, gồm public scheme, host, port và prefix trong bối cảnh phù hợp.
- `native` sử dụng tính năng container, có thể đủ cho `X-Forwarded-Proto`/`X-Forwarded-For` nhưng không nhất thiết xử lý mọi kiểu public prefix. Chọn theo proxy/container thực tế, **không bật đồng thời nhiều lớp xử lý forwarded headers chồng nhau** mà không kiểm chứng.
- `server.tomcat.redirect-context-root=false` được Spring Boot khuyến nghị khi Tomcat đứng sau proxy kết thúc SSL để không redirect context root trước khi tin đúng `X-Forwarded-Proto`.
- Cookie `secure=true` giúp phát `Secure` dù kết nối **proxy → backend** là HTTP; URL client thật vẫn phải là HTTPS.
- `http-only=true` bảo vệ session cookie khỏi việc đọc trực tiếp từ JavaScript.
- `name="__Host-SESSION"` và `path=/` **chỉ hợp lệ khi không đặt Domain**, request browser đến từ HTTPS; nếu container/proxy vẫn thêm Domain hoặc đổi Path, prefix sẽ bị browser từ chối.
- `same-site=lax` là **lựa chọn cho flow top-level GET thông thường**, chưa chắc hợp với form-post callback/iframe; chỉ đổi sau khi xác định flow thực tế.
- `tracking-modes=cookie` tránh dùng `;jsessionid=...` trong URL. Cần test container/link generation thực tế.

**Quy tắc tin tưởng số một:** nếu edge proxy **không loại bỏ các inbound forwarded headers do client tự gửi và ghi đè giá trị đáng tin**, việc bật `server.forward-headers-strategy=framework` có thể gây host-header/redirect poisoning. Đừng để backend public port bị gọi trực tiếp bởi attacker trong khi app mặc định tin forwarded headers.

### Nếu public prefix và servlet context khác nhau

Hai mô hình cần phân biệt:

**A. Proxy strip `/auth`**:

```text
Public:  https://login.example.test/auth/login
Proxy:   /auth/login  ->  http://app:8080/login
Header:  X-Forwarded-Prefix: /auth
App:     server.servlet.context-path mặc định /
```

**B. Backend tự mount tại `/auth`**:

```text
Public:  https://login.example.test/auth/login
Proxy:   /auth/login  ->  http://app:8080/auth/login
App:     server.servlet.context-path: /auth
Header:  X-Forwarded-Prefix không cần dùng để thêm /auth lần nữa
```

Hai cách đều có thể hoạt động, nhưng **không trộn** cấu hình dẫn tới double prefix hoặc sai mapping. Khi có nhiều proxy layers, ghi lại từng lần rewrite path và các headers đi kèm.

## 11. Nginx TLS termination: ví dụ path strip có kiểm soát

Giả sử Nginx là edge proxy **duy nhất** nhận request công khai, app thực chạy backend ở `http://app:8080` với context path `/`. Một mảnh cấu hình minh họa:

```nginx
server {
    listen 443 ssl;
    server_name login.example.test;

    # ssl_certificate, ssl_certificate_key, TLS policy và HSTS
    # phải cấu hình theo hệ thống thực.

    location /auth/ {
        # Dấu / ở cuối proxy_pass khiến prefix /auth/ được rewrite
        # thành / ở backend với kiểu location prefix này.
        proxy_pass http://app:8080/;

        # Không cho client quyết định scheme/host/port/prefix:
        proxy_set_header Host login.example.test;
        proxy_set_header X-Forwarded-Host login.example.test;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-Prefix /auth;

        # Loại bỏ header Forwarded gốc để tránh xung đột/spoof:
        proxy_set_header Forwarded "";

        # Với edge duy nhất, không kế thừa chuỗi IP client tự cung cấp.
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
```

**Đây là mảnh cấu hình Nginx, không phải file triển khai đầy đủ.** Chứng thư/cipher, redirect HTTP → HTTPS, HSTS, `location = /auth` (chuẩn hóa trailing slash), health routes, timeouts, headers khác và topology nhiều proxy cần được cấu hình/test riêng. Không áp dụng y nguyên `proxy_pass` path stripping nếu backend thật đã mount `/auth`.

Điểm cần kiểm tra khi deploy:

- Browser `https://login.example.test/auth/login` được backend map thành đúng `/login`.
- App sau xử lý `X-Forwarded-Prefix` tạo URL công khai **có đúng một `/auth`**.
- Mọi `Location` ngoài cùng dùng HTTPS/public host, không lộ `http://app:8080`.
- Cookie trả browser có Domain/Path đúng. `__Host-SESSION` yêu cầu Path=/ và không Domain.
- Edge không tin giá trị `Forwarded` hay `X-Forwarded-*` do client gửi từ Internet; nếu có các proxy tin cậy khác, xác định rõ ai là nơi sanitize.
- Cổng backend không public và bảo vệ network giữa proxy/backend theo threat model.

### Vì sao chỉ thêm X-Forwarded-Proto có thể chưa đủ?

`X-Forwarded-Proto=https` chỉ giải quyết scheme. App vẫn có thể thấy:

```text
host = app:8080          (sai host)
port = 8080             (sai port)
contextPath = ""        (thiếu /auth)
```

Cần xử lý **cùng lúc public host, port và prefix** theo kiến trúc. Có thể dùng `Forwarded: proto=https;host=login.example.test` hoặc các `X-Forwarded-*` do proxy tin cậy cung cấp; đừng truyền cả hai bộ headers mâu thuẫn.

**Không bật wildcard Host/redirect logic** và không xây absolute URLs từ `Host` hoặc `X-Forwarded-Host` chưa kiểm chứng. Sử dụng allowlist public origins và proxy sanitization.

## 12. OAuth2/OIDC: khi cookie mất, state và nonce cũng có thể mất

Trong một OAuth2 Authorization Code flow thường gặp:

```text
Browser -> /auth/oauth2/authorization/demo
    |
    +-- Spring tạo OAuth2AuthorizationRequest
    |   và lưu correlation state vào repository (thường HttpSession)
    |
    v
302 -> https://idp.example.test/authorize?...&state=...
    |
    v
User xác thực với IdP
    |
    v
Callback -> https://login.example.test/auth/login/oauth2/code/demo
               |
               +-- Browser có gửi SAME session cookie không?
               +-- Application có tìm lại authorization request không?
               +-- Request state có khớp không?
               +-- Redirect URI có đúng đăng ký IdP không?
               +-- OIDC validation (issuer/signature/nonce...) đạt không?
```

Nếu cookie session không đến callback, backend có thể không tìm thấy `OAuth2AuthorizationRequest` gốc. Từ góc người dùng, lỗi này rất dễ bị chẩn đoán nhầm là “sai client secret” hoặc “IdP lỗi”.

### Hai kiểu lỗi cần phân biệt

| Lỗi | Xuất hiện khi nào | Cần kiểm tra |
| --- | --- | --- |
| `redirect_uri_mismatch` | IdP từ chối authorize request trước callback | Giá trị `redirect_uri` đã gửi vs client registration, proxy scheme/host/prefix |
| `authorization_request_not_found` hoặc correlation/state missing | Callback về app nhưng không còn request state | Cookie, session store, SameSite, session rotation, callback host/path, state repository |
| `invalid_state_parameter` | `state` callback không khớp hoặc thiếu | Login initiation/callback cùng session, CSRF/state tampering, expired session |
| Callback `404`/`403` | Route/proxy/security matcher sai hoặc CSRF/method mismatch | Rewrite path, callback route, SecurityFilterChain, CSRF policy |
| Login loop sau callback | Authentication có thể đã thành công nhưng session không persist | Set-Cookie sau login, Request Cookie, SecurityContextRepository, multiple pods |

Tùy version, handler và IdP, tên mã lỗi có thể khác. Không kết luận chỉ từ một chuỗi exception; kiểm tra Network trace và server metrics an toàn.

### Tại sao form_post khác GET?

`response_mode=form_post` khiến IdP **POST** callback cross-site. Nếu ứng dụng lưu authorization request trong `HttpSession` nhưng browser không gửi session cookie `SameSite=Lax`, Spring không thể lấy lại state; callback có thể fail. Cách sửa cần thỏa cả cookie policy, CSRF/callback handling và OIDC correlation; không nên disable state validation hoặc bật mọi cookie cross-site vô điều kiện.

## 13. Cookie vẫn gửi nhưng Spring thấy anonymous

Đây là nhánh **server-side**, không còn là “SameSite mất cookie”. Kiểm tra:

1. Session cookie name backend đọc có khớp tên browser gửi không?
2. Servlet container có tìm thấy `HttpSession` dựa ID hiện tại không?
3. Session đã expired do idle timeout/absolute policy hoặc logout chưa?
4. Sau authentication, context có được lưu ở `SecurityContextRepository` đúng không?
5. Session fixation protection đã đổi ID: client gửi ID **mới** hay ID cũ?
6. Một request vào pod A, request sau vào pod B: có Spring Session/shared store hoặc sticky routing đúng không?
7. Các pod có cùng cookie name/path và session serializer/schema compatible không?
8. Nếu dùng `SessionCreationPolicy.STATELESS` hoặc bearer resource server, có thật mong đợi HttpSession hay không?
9. SecurityFilterChain matcher có thay đổi giữa login và protected API, dẫn tới một chain stateless bỏ qua session không?
10. Có custom filter ghi authentication vào `SecurityContextHolder` mà không persist context không?

### Spring Security 6: explicit save trong custom flow

`SecurityContextHolderFilter` của Spring Security 6 mặc định **đọc** context từ repository và không tự động lưu mọi thay đổi do ứng dụng đặt thủ công. Nếu custom controller gọi `AuthenticationManager.authenticate` rồi chỉ:

```java
SecurityContextHolder.getContext().setAuthentication(authentication);
```

thì request tiếp theo có thể vẫn anonymous. Với custom flow, cần tạo/đặt context và gọi repository save khi phù hợp:

```java
// Fragment Servlet Spring Security 6.x, nằm trong flow auth đã xác minh:
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
```

`securityContextRepository` phải là instance được cấu hình nhất quán với SecurityFilterChain; `request`/`response` là Servlet objects đúng lifecycle. Đây **không phải** một controller login đầy đủ, còn cần credential verification, session strategy, CSRF và failure handling. Form login tiêu chuẩn của Spring Security xử lý phần này theo framework; đừng tự thêm save 2 lần nếu không cần.

### Multi-instance

```text
Request 1: Pod A -> tạo session S123 lưu RAM Pod A
Request 2: Pod B -> nhận Cookie S123 nhưng RAM Pod B không có S123
=> Pod B xem như anonymous; User thấy login chập chờn
```

Khắc phục bằng Spring Session (Redis/JDBC) hoặc kiến trúc session sharing phù hợp; sticky session chỉ là một phương án routing có giới hạn, không thay thế cơ chế revoke/failover khi sản phẩm cần scale. **Không cố sửa bằng cách mở rộng Domain cookie sang các pod**: pod là backend servers, không phải hostname của browser.

## 14. Checklist browser/proxy/backend trong 15 phút điều tra

### Bước 1 — chụp một flow tối thiểu

- Dùng test account và browser profile riêng.
- Bật **Preserve log** trong Network.
- Thực hiện đúng một login: record URL phương thức và các HTTP status/Location qua từng redirect.
- Ghi **có/không có** Set-Cookie và Request Cookie; không copy giá trị cookie bí mật.
- Xác định request đầu tiên làm mất session hoặc rời public origin.

### Bước 2 — kiểm tra cookie được browser chấp nhận

- Xem DevTools Cookies/Application và blocked reasons.
- Xác minh `Secure` cùng HTTPS, `HttpOnly`, `SameSite`, Domain, Path, Expires/Max-Age, `__Host-` rules.
- Có cookie cùng tên ở hai path/domain không? Có response nào xóa cookie bằng Max-Age=0 không?
- Nếu cookie thuộc third-party context/iframe, xem browser privacy restrictions.

### Bước 3 — kiểm tra request cookies

- Đúng host? Ví dụ login.example.test vs app.example.test.
- Đúng scheme HTTPS? Có redirect vô tình sang HTTP?
- Path cookie có chứa request path không?
- Cross-site POST/iframe/fetch có bị SameSite hoặc credentials/CORS ngăn không?
- Có thay session ID sau login mà frontend giữ ID cũ không?

### Bước 4 — kiểm tra public URL và forwarded headers

- Xem `Location` và OAuth `redirect_uri` có chứa internal `app:8080`, HTTP hoặc thiếu prefix?
- Đối chiếu `Forwarded` hoặc `X-Forwarded-Proto/Host/Port/Prefix` **do proxy trusted ghi đè**, không đọc raw header giả mạo như bằng chứng.
- Kiểm tra `server.forward-headers-strategy` và Tomcat context-root redirect.
- Xác định reverse proxy có strip/mount prefix mấy lần.

### Bước 5 — kiểm tra session và callback

- Nếu browser **đã gửi cookie**, backend có thấy session hợp lệ không?
- State repository, CSRF, session persistence, expired/logout/session store/shared Redis có khớp không?
- IdP client registration có exact redirect URI phù hợp không?
- Nhiều pods có session consistency và đúng security chain không?

**Bằng chứng tối thiểu đủ kết luận:** một trace request–response có status + Location đã scrub, cookie attributes đã scrub, browser blocked reason và public/internal path mapping. Không cần gửi secrets cho đồng nghiệp hoặc bên hỗ trợ.

## 15. Dùng curl đúng cách, và giới hạn của curl

Trên máy có TLS trust đúng, inspect response headers:

```bash
curl -sS -D - -o /dev/null https://login.example.test/auth/login
```

Để theo dõi redirects **mà không lộ secrets**, có thể inspect các URL public GET trong môi trường test; tránh in token/OAuth authorization code/`state` vào logs hoặc chat. Nếu cần gửi POST login, không đưa password vào command history hay chia sẻ trace raw.

**Đừng dùng `curl -k` như cách sửa TLS**: nó tắt xác minh certificate và có thể che lỗi thật. Tương tự, `curl` có cookie jar nhưng **không phải browser**, nên không mô phỏng đầy đủ SameSite, browser third-party cookie blocking, cookie prefix enforcement hoặc user-gesture restrictions.

Trên Windows PowerShell 5.1, dùng `curl.exe` thay vì alias `curl` nếu muốn cú pháp curl chuẩn.

### Bẫy khi thử trực tiếp backend

Gọi `http://app:8080/login` qua internal network sẽ khác browser public flow. Nó không có TLS, public Host/prefix hoặc cookie policy của browser. Kết quả “backend trả 200” **không chứng minh** public OAuth/cookie vận hành đúng. Để debug, so sánh traffic ở edge và backend với metadata được scrub, không bypass network trust boundary.

## 16. Java 17 thuần: mô phỏng lý do cookie bị từ chối hoặc không được gửi

Ví dụ có thể chạy độc lập bằng **JDK 17+**. Nó **không** phải implementation RFC 6265 đầy đủ và không thay thế browser DevTools. Nó mô phỏng các quy tắc dễ sai nhất: `__Host-`, Secure, host/path, SameSite explicit Lax và public callback URL.

Tạo file **`CookieProxyDiagnosisDemo.java`**:

```java
import java.util.*;

public class CookieProxyDiagnosisDemo {
    enum SameSite { STRICT, LAX, NONE }

    record Cookie(String name, String originHost, String path,
                  boolean secure, boolean httpOnly, boolean hasDomain,
                  SameSite sameSite) {}

    record Request(String scheme, String host, String path,
                   boolean crossSite, boolean topLevelNavigation,
                   String method) {}

    static boolean canStore(Cookie c, boolean httpsOrigin) {
        if (c.secure() && !httpsOrigin) return false;
        if (c.sameSite() == SameSite.NONE && !c.secure()) return false;
        if (c.name().startsWith("__Host-")) {
            if (!httpsOrigin || !c.secure()
                    || !"/".equals(c.path()) || c.hasDomain()) {
                return false;
            }
        }
        return true;
    }

    static boolean pathMatches(String cookiePath, String requestPath) {
        if (cookiePath.equals(requestPath)) return true;
        if (!requestPath.startsWith(cookiePath)) return false;
        return cookiePath.endsWith("/")
                || requestPath.charAt(cookiePath.length()) == '/';
    }

    static boolean sends(Cookie c, Request r) {
        if (c.secure() && !"https".equals(r.scheme())) return false;
        if (!c.originHost().equalsIgnoreCase(r.host())) return false;
        if (!pathMatches(c.path(), r.path())) return false;

        if (!r.crossSite()) return true;
        if (c.sameSite() == SameSite.STRICT) return false;
        if (c.sameSite() == SameSite.LAX) {
            return r.topLevelNavigation()
                    && ("GET".equals(r.method())
                        || "HEAD".equals(r.method()));
        }
        return true; // NONE, giả sử browser privacy policy cho phép
    }

    static String publicCallback(String proto, String host, String prefix,
                                 String callbackPath) {
        if (!"https".equals(proto)
                || !"login.example.test".equals(host)) {
            throw new SecurityException("Untrusted public origin");
        }
        String safePrefix = prefix.endsWith("/")
                ? prefix.substring(0, prefix.length() - 1) : prefix;
        return proto + "://" + host + safePrefix + callbackPath;
    }

    public static void main(String[] args) {
        Cookie session = new Cookie(
                "__Host-SESSION", "login.example.test",
                "/", true, true, false, SameSite.LAX);

        System.out.println("validHostCookie="
                + canStore(session, true));

        System.out.println("sameSiteHttps=" + sends(session,
                new Request("https", "login.example.test", "/auth/home",
                        false, false, "GET")));

        System.out.println("httpBlocked=" + !sends(session,
                new Request("http", "login.example.test", "/auth/home",
                        false, false, "GET")));

        System.out.println("crossSitePostBlocked=" + !sends(session,
                new Request("https", "login.example.test",
                        "/auth/login/oauth2/code/demo",
                        true, true, "POST")));

        System.out.println("crossSiteTopGetAllowed=" + sends(session,
                new Request("https", "login.example.test",
                        "/auth/login/oauth2/code/demo",
                        true, true, "GET")));

        System.out.println("wrongHostBlocked=" + !sends(session,
                new Request("https", "other.example.test", "/auth/home",
                        false, false, "GET")));

        Cookie pathCookie = new Cookie(
                "SESSION", "login.example.test",
                "/auth", true, true, false, SameSite.LAX);

        System.out.println("wrongPathBlocked=" + !sends(pathCookie,
                new Request("https", "login.example.test", "/portal/home",
                        false, false, "GET")));

        Cookie badPrefix = new Cookie(
                "__Host-SESSION", "login.example.test",
                "/", true, true, true, SameSite.LAX);

        System.out.println("hostPrefixRejectsDomain="
                + !canStore(badPrefix, true));

        Cookie badNone = new Cookie(
                "SESSION", "login.example.test",
                "/", false, true, false, SameSite.NONE);

        System.out.println("noneNeedsSecure="
                + !canStore(badNone, true));

        String external = publicCallback(
                "https", "login.example.test",
                "/auth", "/login/oauth2/code/demo");
        String internal =
                "http://app:8080/login/oauth2/code/demo";

        System.out.println("publicCallback=" + external);
        System.out.println("internalDoesNotMatch="
                + !external.equals(internal));
    }
}
```

Biên dịch và chạy:

```bash
javac CookieProxyDiagnosisDemo.java
java CookieProxyDiagnosisDemo
```

**Stdout xác định:**

```text
validHostCookie=true
sameSiteHttps=true
httpBlocked=true
crossSitePostBlocked=true
crossSiteTopGetAllowed=true
wrongHostBlocked=true
wrongPathBlocked=true
hostPrefixRejectsDomain=true
noneNeedsSecure=true
publicCallback=https://login.example.test/auth/login/oauth2/code/demo
internalDoesNotMatch=true
```

### Ý nghĩa và giới hạn mô phỏng

- `validHostCookie=true` vì cookie `__Host-` có Secure, Path=/, không Domain, được set từ HTTPS.
- `httpBlocked=true` vì Secure cookie không theo HTTP công khai.
- `crossSitePostBlocked=true` chỉ mô phỏng **SameSite=Lax được khai báo rõ** với cross-site POST; không mô phỏng ngoại lệ Lax-by-default của một số browser hoặc redirect chains phức tạp.
- `crossSiteTopGetAllowed=true` minh họa top-level cross-site GET có thể mang Lax cookie.
- `wrongHostBlocked` và `wrongPathBlocked` giúp nhớ host-only/Path được kiểm tra **ở browser trước khi gửi**.
- `hostPrefixRejectsDomain=true` minh họa prefix `__Host-` không chấp nhận Domain.
- `noneNeedsSecure=true` minh họa SameSite=None không có Secure sẽ bị từ chối.
- `publicCallback` là URL muốn đăng ký IdP khi proxy strip prefix. Nó không thực sự đọc forwarded headers.
- Code cố ý **không** mô phỏng public suffix list, schemeful site calculation, expires/max-age, full cookie Domain matching, Set-Cookie parser, third-party blockers, CORS, HTTPOnly, cookie jar hoặc OAuth2 protocol. `crossSite` là input do test cung cấp, không phải phân loại tự động.
- Kết quả chương trình **không chứng minh** cấu hình Spring Boot hay Nginx của bạn đúng; cần browser/HTTP integration tests.

## 17. Test với Spring Boot và browser: kiểm tra từng lớp, không nhầm MockMvc là browser

### Unit test cho URL generation

Nếu ứng dụng tự tạo absolute URLs, kiểm thử một **public origin allowlist** và đúng public prefix. Với Spring Boot và forwarded headers, cần integration test có request ở proxy thật hoặc trong test environment có `ForwardedHeaderFilter`. Chỉ truyền header `X-Forwarded-Host` giả vào unit test khi code test gọi trực tiếp không chứng minh môi trường production chống header spoofing.

Một mảnh kiểm thử kiến trúc:

```text
Given public URL:
    https://login.example.test/auth/login
And backend URL:
    http://app:8080/login
And trusted proxy headers:
    X-Forwarded-Proto: https
    X-Forwarded-Host: login.example.test
    X-Forwarded-Prefix: /auth

When OAuth authorization request is issued:
    redirect_uri must be
    https://login.example.test/auth/login/oauth2/code/demo
And response Location must contain no internal host/port.
```

### Browser test cho cookies

MockMvc không enforce đầy đủ SameSite/third-party browser privacy rules; vì vậy cần Playwright/Selenium hoặc trình duyệt thật để kiểm tra:

- Set-Cookie có được browser chấp nhận?
- Cookie Secure/Domain/Path đúng với public URL?
- `SameSite=Lax` có gửi trên top-level GET callback?
- `SameSite=Lax` có bị bỏ trên cross-site POST callback?
- Browser có từ chối `SameSite=None` thiếu Secure?
- Cross-origin fetch có gửi credentials và backend trả CORS allowlist hợp lệ?
- SSO cookie và app session cookie có scope riêng?
- Host/prefix sau proxy có tạo redirect URI đúng không?

### Integration test cho server session

Trong Spring Security Servlet, `MockMvc` và `spring-security-test` có thể xác minh state request với `MockHttpSession` nhưng không nên khẳng định browser cookie store từ MockMvc alone:

```java
// Mảnh test trong lớp @SpringBootTest + @AutoConfigureMockMvc
// với MockMvc được inject và login form/users đã cấu hình.
MvcResult result = mvc.perform(formLogin()
        .user("alice").password("test-password"))
        .andExpect(authenticated())
        .andReturn();

MockHttpSession session =
        (MockHttpSession) result.getRequest().getSession(false);

assertNotNull(session);

mvc.perform(get("/private")
        .session(session))
        .andExpect(authenticated());
```

Imports theo project: `org.springframework.test.web.servlet.MvcResult`, `org.springframework.mock.web.MockHttpSession`, `org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin`, `org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated`, `org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get` và JUnit `assertNotNull`. Đây là **test fragment**, không phải ứng dụng độc lập; đường `/private` và test user phải tồn tại trong fixture.

**Cẩn trọng:** MockMvc test session không chứng minh cookie `SameSite` được browser gửi trên IdP callback; cần E2E public URL test. Ngược lại, chỉ test browser login không đủ phát hiện backend session store không nhất quán khi chuyển pod.

## 18. Những cấu hình “chữa nhanh” thường làm giảm bảo mật

**1. Đặt tất cả cookie `SameSite=None`.** Có thể làm CSRF risk tăng và vẫn bị third-party cookie blocking. Chỉ thay theo flow, giữ CSRF/state/nonce và đo kiểm browser.

**2. Tắt `csrf()` hoàn toàn.** Login/session cookie vẫn có CSRF risk, đặc biệt form POST/cross-origin request. Sửa đúng csrf repository, token transport hoặc callback matcher theo giao thức thay vì disable bừa bãi.

**3. Bỏ `Secure` để cookie chạy qua HTTP sau proxy.** Nhầm đường **proxy→backend** với **browser→public edge**. Browser public phải qua HTTPS; cấu hình Secure đúng ngay cả khi backend HTTP trusted.

**4. Bỏ `HttpOnly` để frontend nhìn thấy SESSION.** `HttpOnly` chặn đọc cookie qua JavaScript đúng thiết kế. Frontend xác định login state qua API server; không cần raw session secret.

**5. Bật `server.forward-headers-strategy=framework` nhưng không sanitize headers từ Internet.** Attacker có thể ép app tạo redirect/absolute URL sang host giả; cần edge strip/rewrite và đóng cổng backend.

**6. Sửa IdP redirect_uri thành wildcard.** Phá ranh giới redirect/callback. Đăng ký exact public URL và sửa proxy/request scheme.

**7. Đặt `Domain=example.test` để mọi app chia sẻ session.** Mở rộng scope và nguy cơ session fixation/subdomain compromise; ưu tiên host-only.

**8. Giữ `__Host-SESSION` nhưng đặt `Path=/auth`.** Browser từ chối prefix. Dùng Path=/ và không Domain, hoặc đổi cookie naming/policy có chủ đích.

**9. Cấu hình cả context-path=/auth và forwarded-prefix=/auth sau khi proxy strip.** Dễ tạo `/auth/auth`/404. Chọn một mô hình path và test.

**10. Disable session fixation protection để giữ JSESSIONID không đổi.** Có thể che symptom tạm thời nhưng mở lỗ hổng fixation. Kiểm tra cookie mới sau login.

**11. Dùng `SessionCreationPolicy.STATELESS` với form login kỳ vọng session tự lưu.** Cần chọn kiến trúc stateful vs stateless; sửa security chain/context persistence.

**12. Tăng session timeout vô hạn.** Không sửa cookie bị browser từ chối hoặc public URL sai, lại tăng rủi ro session theft.

**13. Tin `Host`/`X-Forwarded-Host` từ client.** Dễ host-header poisoning; allowlist và trusted proxy rewrite.

**14. Coi `curl -k` thành công là TLS đã chuẩn.** `-k` tắt cert validation. Browser và IdP vẫn có thể từ chối.

**15. Chỉ test một pod.** Session in-memory có thể hoạt động với một pod nhưng fail khi load balancer gửi request sang pod khác.

**16. Bật CORS wildcard với credentials.** Browser có thể reject và cấu hình mở rộng trust không cần thiết. Allowlist origin chính xác.

**17. Ghi Cookie/authorization code/state vào log.** Tạo rủi ro đánh cắp phiên hoặc replay OAuth. Redact từ edge tới app/observability.

**18. Đặt cookie trên hostname backend nội bộ.** Browser không truy cập backend hostname; phải phát cookie từ response public host hợp lệ.

**19. Tưởng cookie HttpOnly không tồn tại vì `document.cookie` rỗng.** Kiểm tra Network/Application, không dùng JS.

**20. Tưởng OAuth `state` lỗi luôn do IdP.** State có thể mất vì session cookie không tới callback hoặc state repository nằm ở pod khác.

## 19. Ma trận kiểm thử chẩn đoán

| Case | Input/bối cảnh | Kết quả mong đợi |
| --- | --- | --- |
| Cookie Secure qua HTTPS | Public URL HTTPS | Browser chấp nhận/sent theo scope |
| Cookie Secure qua HTTP công khai | HTTP URL | Không gửi Secure cookie |
| Cookie `__Host-` có Domain | Set-Cookie sai prefix | Browser từ chối |
| Cookie `__Host-` Path=/auth | Sai Path với prefix | Browser từ chối |
| SameSite=None thiếu Secure | Response header sai | Browser từ chối |
| SameSite=Lax explicit, cross-site GET top-level | IdP GET callback | Có thể gửi session nếu scope khác hợp lệ |
| SameSite=Lax explicit, cross-site POST | IdP form_post | Thường không gửi session |
| SameSite=Strict, điều hướng từ site ngoài | Top-level navigation | Không gửi trong cross-site context |
| Cookie host-only sai host | login.example.test → other.example.test | Không gửi |
| Cookie Path=/auth nhưng request /portal | Sai path | Không gửi |
| Cookie expired/Max-Age=0 | Response logout/expiry | Browser xóa hoặc không gửi |
| Cross-origin fetch thiếu credentials | SPA → API khác origin | Không mang cookie theo fetch mặc định |
| CORS credentials và wildcard origin | Response policy sai | Browser không chấp nhận credentialed CORS response |
| Proxy chỉ có X-Forwarded-Proto | Internal host/prefix còn sai | Redirect URI vẫn sai; bổ sung mapping tin cậy |
| Proxy strip /auth, app nhận prefix | OAuth authorization redirect | URI public có một lần /auth |
| Proxy không strip, app context=/auth | OAuth callback | Không double-prefix |
| Attacker tự đưa X-Forwarded-Host | Internet request | Edge strip/rewrite; URL không bị poisoned |
| IdP registered URL khác computed URL | OAuth login | Phát hiện exact mismatch |
| Cookie gửi nhưng session hết hạn | Request protected | Anonymous/redirect theo policy |
| Custom login không save context | Login xong request kế tiếp | Phát hiện/thiết kế explicit save |
| 2 pods chỉ giữ in-memory sessions | Request xen kẽ pod | Phát hiện inconsistency; dùng shared store |
| Spring Session Redis | 2+ pods và logout | Session tồn tại/revoked nhất quán |
| Header Set-Cookie chỉ có trên 302 | Preserve log | Tìm thấy set-cookie ở response trung gian |
| Logout xoay/xóa session | GET request sau logout | Cookie cũ không xác thực |
| Browser third-party restriction | OIDC in iframe | Có thể bị block dù None; dùng flow phù hợp |
| CSRF POST session-cookie | Thiếu/sai CSRF token | Từ chối đúng policy, không disable CSRF |
| Logs/metrics/trace | Security QA | Không lộ cookie, code, token, password |

## 20. Checklist cuối cho người trực vận hành

1. Đã xác định **request đầu tiên** mất authenticated state, không chỉ nhìn “login loop” chung chung?
2. Network Preserve log có nhìn đủ mọi `302`, `Set-Cookie`, `Location` không?
3. Browser có lưu cookie? Nếu không, DevTools blocked reason là gì?
4. Cookie đã lưu có đúng Domain/host, Path, Secure, SameSite, prefix `__Host-` và Expires không?
5. Browser có gửi cookie trên request quan trọng hay chỉ còn trong Storage?
6. Flow là cross-site GET, cross-site POST, iframe hay cross-origin fetch?
7. Có hiểu khác biệt giữa **origin** và **site**, và không dùng CORS làm thay CSRF?
8. `SameSite=None` (nếu cần) có `Secure` và còn phù hợp browser privacy policy không?
9. App có được cấu hình forwarded headers **sau edge trusted/sanitized** không?
10. Scheme/host/port/prefix bên ngoài có khớp URL thực dùng trong `redirect_uri` không?
11. Proxy strip path hay backend context-path? Có duplicate/missing prefix không?
12. Cookie gửi đến backend có truy ra session ở **mọi pod** không?
13. Spring Security 6 custom login có persist `SecurityContext` đúng repository không?
14. Session ID sau login có đổi theo chống fixation, và browser có dùng ID mới không?
15. OAuth `state`/authorization request có được lưu và đọc lại cùng session không?
16. Client registration ở IdP dùng exact public redirect URI, không wildcard?
17. User login flow có được test trong browser thật + proxy thật, không chỉ MockMvc/curl?
18. Tất cả debug logs/headers đã scrub session IDs, code, password, tokens?
19. Các thay đổi cookie/forwarded headers đã được security review để tránh CSRF/host poisoning?
20. Đã test logout, session expiry, multiple tabs, mobile browsers và multi-instance routing?

### Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Running Behind a Front-end Proxy Server: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5 — Servlet SameSite cookies: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Framework 6.2 — ForwardedHeaderFilter and security: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html
- Spring Security 6.5 — Session Management, SecurityContext persistence: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 — Session Management FAQ: https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/faq.html
- Spring Security 6.5 — OAuth2 Login: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html
- MDN — Set-Cookie, Secure/SameSite/__Host- rules: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie
- MDN — Using HTTP Cookies: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — Cross-Site Request Forgery Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

**Kết luận:** khi login “mất phiên”, hãy chứng minh **cookie được phát, được browser lưu, được gửi, và server còn nhận ra session** theo thứ tự. Song song, kiểm tra **public scheme/host/port/prefix** do proxy cung cấp cho OAuth2 callback và redirect. Chỉ sửa đúng đoạn pipeline đã có bằng chứng; không tắt Secure, HttpOnly, CSRF, OAuth state validation hoặc mở trust headers để che triệu chứng.
