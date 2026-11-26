# Mobile client cùng backend phục vụ trình duyệt

## Mục tiêu và phạm vi

Trong chương **CSRF cho SPA và API** của module **SPRING_SECURITY_HTTP_PROTECTION**, cùng một backend Spring Security có thể phục vụ **website/SPA trong trình duyệt**, **ứng dụng mobile native (Android/iOS)** và đôi khi **WebView** trong ứng dụng di động. Ba môi trường này không nhất thiết dùng cùng một loại credential hoặc có cùng nguy cơ Cross-Site Request Forgery (CSRF).

Một quyết định thường gặp nhưng sai là “mobile không cần CSRF nên tắt CSRF trên toàn bộ REST API”. Điều đó có thể khiến các endpoint **đăng nhập bằng cookie, cập nhật tài khoản, thanh toán, logout hoặc refresh session trong trình duyệt** mất lớp bảo vệ trước request giả mạo. Ngược lại, áp CSRF token dựa trên cookie phiên cho một mobile native client chỉ gửi **Authorization: Bearer** cũng có thể tạo lỗi 403 không cần thiết.

Mục tiêu là xác định **cơ chế xác thực được server chấp nhận ở từng đường request**, rồi tổ chức SecurityFilterChain, CSRF, CORS, session và thử nghiệm phù hợp. Bài đi qua cả **Servlet** và **Reactive/WebFlux**, liên hệ với security headers, CSP, HSTS, HTTP firewall và bảo vệ session.

Sau bài học, người học có thể:

1. Phân biệt **mobile native**, **mobile browser**, **WebView** và **SPA web**, không suy luận an toàn chỉ từ tên thiết bị.
2. Giải thích vì sao cookie/browser-managed authentication tạo điều kiện cho CSRF, còn API **Bearer-only** do client chủ động thêm token có mô hình khác.
3. Tách **mobile Bearer API** và **browser cookie API** bằng security chain/routing có quy tắc rõ ràng, vẫn tái sử dụng business service backend.
4. Dùng **OAuth 2.0 Authorization Code + PKCE** cho native app khi có hệ thống ủy quyền phù hợp; lưu token bằng kho bí mật của hệ điều hành thay vì hardcode.
5. Thiết kế GET bootstrap CSRF cho browser và xử lý token khi login/logout hoặc session thay đổi.
6. Cấu hình **HttpSecurity** trên Servlet và **ServerHttpSecurity** trên WebFlux mà không áp dụng nhầm class hai stack.
7. Kiểm thử mobile POST không yêu cầu CSRF khi Bearer hợp lệ, trong khi browser POST thiếu CSRF vẫn bị từ chối.
8. Đánh giá trường hợp **WebView, cookie jar trong thư viện HTTP, CORS, session fallback và endpoint refresh/logout** là các ngoại lệ cần chính sách riêng.

## 1. Bài toán kiến trúc: một backend, nhiều môi trường client

Giả sử một hệ thống thương mại điện tử có:

- **Web SPA** tại https://shop.example.com, đăng nhập qua cookie session **JSESSIONID** và gọi https://api.example.com.
- **Ứng dụng mobile native** trên iOS/Android, lấy access token từ nhà cung cấp OAuth/OIDC và gửi **Authorization: Bearer** tới https://api.example.com.
- **Backend Spring Security** với business service dùng chung cho tài khoản, giỏ hàng, đơn hàng và thanh toán.
- **WebView** đôi khi mở trang thanh toán hoặc trang hỗ trợ; nội dung HTML trong WebView có thể có cookie/session, không được mặc nhiên coi là “native”.

Hai request có thể cùng tạo đơn hàng nhưng mang credential khác nhau:

~~~http
POST /api/mobile/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOi...
Content-Type: application/json

{"sku":"P100","quantity":1}
~~~

~~~http
POST /api/web/orders HTTP/1.1
Host: api.example.com
Origin: https://shop.example.com
Cookie: JSESSIONID=session-abc
X-CSRF-TOKEN: token-from-this-session
Content-Type: application/json

{"sku":"P100","quantity":1}
~~~

Hai endpoint có thể gọi cùng một **OrderApplicationService.placeOrder(...)**. Điều cần tách là **lớp HTTP security boundary**, không phải nhất thiết nhân đôi logic nghiệp vụ.

~~~mermaid
flowchart TD
    W["Web SPA trong browser"] -->|Cookie session + CSRF header| WB["/api/web/**"]
    M["Mobile native HTTP client"] -->|Authorization Bearer| MB["/api/mobile/**"]
    V["Mobile WebView hoặc browser"] -->|Cookie và hành vi trình duyệt| WB
    WB --> WC["Browser SecurityFilterChain: CSRF + CORS + session"]
    MB --> MC["Mobile SecurityFilterChain: Bearer-only + stateless"]
    WC --> S["Application services dùng chung"]
    MC --> S
    S --> D["Repository và dữ liệu nghiệp vụ"]
~~~

Đây là **một phương án phân tuyến rõ ràng**, không phải yêu cầu mọi ứng dụng bắt buộc tạo hai URL cho cùng nghiệp vụ. Với hệ thống muốn một URL duy nhất, phải thiết kế cẩn thận cách lựa chọn authentication mechanism và policy trước khi bỏ kiểm tra CSRF. Đường URL tách biệt thường dễ kiểm tra, audit và hạn chế nhầm lẫn hơn.

### 1.1. Bảng xác định CSRF theo cách gửi credential

| Client thực tế | Credential mà API chấp nhận | Browser có tự gắn credential không? | Đánh giá CSRF |
| --- | --- | --- | --- |
| Desktop/mobile browser, SPA cookie session | Cookie session | Có trong request phù hợp | **Cần CSRF** cho thao tác không an toàn |
| Browser dùng JWT trong HttpOnly cookie | JWT cookie | Có | **Cần đánh giá CSRF**, dù server stateless |
| Native iOS/Android qua HTTP library, chỉ Bearer | Authorization do ứng dụng gắn | Không có trình duyệt tự gửi token theo request của website khác | **Thường không cần synchronizer CSRF token** trên Bearer-only API |
| Native HTTP library tự quản lý session cookie | Cookie jar tự gửi trong request phù hợp | Có thể tự gửi ở tầng library; không đồng nghĩa browser có thể điều khiển library | Đánh giá threat model thực tế, nhất là WebView và deep links |
| WebView đăng nhập bằng cookie | Cookie trong WebView | Có thể do môi trường web tự gửi | **Bảo vệ như website** |
| Native app dùng system browser cho đăng nhập OAuth | Cookie của trang authorization server trong browser | Có trong trang web authorization | Authorization server vẫn cần cơ chế CSRF/state; client native sử dụng PKCE/state đúng luồng |
| Mobile app mở website qua trình duyệt hệ thống | Cookie browser | Có | Website đích giữ CSRF bình thường |
| SPA chỉ gửi Bearer do JavaScript chủ động thêm, backend tuyệt đối không nhận cookie fallback | Authorization Bearer | Không tự xuất hiện trong HTML form cross-site | CSRF truyền thống thường không áp dụng cho route ấy; **XSS vẫn nguy hiểm** |

**Không dựa vào User-Agent, tên app, header X-Mobile-App hoặc Origin vắng mặt để quyết định bỏ CSRF.** Tất cả có thể bị giả mạo bởi HTTP client; một website độc hại có thể gửi các request đơn giản và browser có thể gửi cookie. Ranh giới bảo vệ nên đến từ **routing + authentication contract** mà server thực sự xác minh.

## 2. CSRF thuộc về cơ chế credential, không thuộc về loại thiết bị

CSRF xuất hiện khi một website tấn công có thể khiến browser của nạn nhân gửi request đến website đích và **browser tự đính kèm credential được server chấp nhận**. Kẻ tấn công không cần biết giá trị session cookie để tạo một HTML form POST; việc browser có gửi cookie hay không còn tùy SameSite và request context.

### 2.1. Browser cookie session

Ví dụ, người dùng đang đăng nhập shop.example.com. Một trang khác có thể cố tạo form POST đến API của shop. Nếu endpoint dựa vào cookie phiên và không kiểm tra CSRF, browser có thể gửi credential hợp lệ trong một số ngữ cảnh. **CORS không thay thế CSRF**, vì request form đơn giản có thể tới server ngay cả khi JavaScript không đọc được response.

Các lớp bảo vệ nên phối hợp:

- Cookie phiên **HttpOnly, Secure, SameSite** theo deployment.
- **CsrfFilter** (Servlet) hoặc **CsrfWebFilter** (Reactive) cho phương thức thay đổi trạng thái.
- **Authentication và authorization** độc lập với token CSRF.
- **CORS allowlist** khi SPA chạy khác origin và cần cookie.
- **CSP/encoding chống XSS**, bởi XSS cùng origin có thể sử dụng CSRF token.
- **HTTPS/HSTS**, kiểm tra Origin/Fetch Metadata nếu có chính sách bổ sung, và HTTP firewall để giảm request bất thường.

### 2.2. Mobile Bearer-only

Trên native app, request thông thường được tạo bởi HTTP library, không do trang web tùy ý có thể buộc library của ứng dụng thêm access token. Nếu resource server **chỉ** chấp nhận Bearer token trong Authorization header, một HTML form tấn công trong browser không tự biết Bearer token của mobile.

Vì vậy **không bắt mobile native gửi CSRF cookie + header chỉ để gọi một Bearer-only API**. Thay vào đó, mobile API cần:

- Xác minh chữ ký, issuer, audience, thời hạn và scope của token tùy kiểu token/JWT hay opaque token.
- Giới hạn quyền theo user và nghiệp vụ; token Bearer đúng không đồng nghĩa được sửa mọi đơn hàng.
- TLS và certificate validation chuẩn; không vô hiệu hóa kiểm tra chứng chỉ production.
- Bảo vệ token khỏi lộ trên thiết bị, log, screenshot, analytics và URL.
- Refresh/revocation và token lifecycle theo hệ thống phát token.

**Bearer-only là điều kiện bắt buộc của quyết định này.** Nếu cùng route còn nhận **cookie session** hoặc HTTP Basic làm fallback, việc nhìn thấy Authorization header không đủ để bỏ CSRF: browser vẫn có thể xác thực request theo đường khác.

### 2.3. WebView và trình duyệt trên mobile không phải native HTTP

**Android WebView**, **WKWebView**, browser tab và HTML page dùng browser engine nên mang nhiều đặc tính web:

- Có cookie jar, navigation, same-origin/CORS và khả năng gửi form hoặc fetch theo chính sách browser.
- Khi API nhận cookie của WebView, **CSRF vẫn có ý nghĩa**.
- Một màn hình HTML nằm trong app không tự trở thành “trusted native request”.
- JavaScript bridge nếu có cần kiểm soát origin/content, không phát token/native credential cho trang không tin cậy.
- Việc chia sẻ cookie giữa WebView, system browser và native HTTP client **phụ thuộc nền tảng và API**; không mặc định mọi kho cookie được chia sẻ.

Đăng nhập OAuth cho native app nên ưu tiên **external user-agent/system browser** theo hướng dẫn ứng dụng native thay vì thu thập mật khẩu trong WebView nhúng. Nhưng nếu sau đó một website được mở, website vẫn phải giữ các lớp phòng vệ riêng.

## 3. Thiết kế hai hợp đồng API trên cùng backend

Một hướng có tính kiểm thử cao là tách tuyến browser và mobile:

| Nhóm endpoint | Authentication | CSRF | CORS | Session |
| --- | --- | --- | --- | --- |
| **/api/mobile/** | Resource server Bearer-only | Không yêu cầu token CSRF truyền thống **nếu bảo đảm không nhận cookie** | Native HTTP không cần CORS; browser gọi nhóm này cần đánh giá riêng | Stateless |
| **/api/web/** | Cookie session | Bật CSRF cho request không an toàn | Allowlist origin SPA, có credentials | Session browser |
| **GET /api/csrf** | Cho anonymous hoặc authenticated tùy hợp đồng | Là GET cấp token | Chỉ origin tin cậy được đọc JSON token | Gắn với session |
| **POST /login và POST /logout** | Form/session browser | Thường cần CSRF | CORS nếu SPA gọi cross-origin | Cookie auth lifecycle |
| **/oauth2/** hoặc endpoint auth server | Theo OAuth/OIDC | Các cơ chế state/PKCE/CSRF riêng của luồng | Không coi cùng chính sách với business API | Theo authorization server |

**Nếu dùng /api/mobile/** để tắt CSRF mà chính endpoint đó vẫn tự động nhận cookie session, thiết kế đã phá điều kiện Bearer-only. Cần chặn cookie fallback ở authentication chain và kiểm thử rõ ràng. Không coi URL prefix tự nó là bằng chứng an toàn.

### 3.1. Điểm chung nên giữ trong application service

Ví dụ cấu trúc ứng dụng:

~~~text
HTTP /api/web/orders
    -> Spring Security browser chain (session + CSRF)
    -> WebOrderController
    -> OrderApplicationService.placeOrder(currentUser, request)

HTTP /api/mobile/orders
    -> Spring Security mobile chain (Bearer JWT, stateless)
    -> MobileOrderController
    -> OrderApplicationService.placeOrder(currentUser, request)

Cả hai luồng:
    -> Domain validation, ownership checks, transaction, audit, rate limits
~~~

Controller hoặc adapter phải lấy **principal của request đã xác thực**, không tin userId do client tự gửi trong JSON. Cùng một service phải áp dụng invariant nghiệp vụ và object-level authorization, bất kể caller là website hay mobile.

### 3.2. Không tắt CSRF theo User-Agent hoặc header tự khai báo

Một anti-pattern nguy hiểm:

~~~java
// KHÔNG DÙNG: User-Agent/Header có thể bị giả mạo.
// Nếu backend vẫn nhận cookie, rule này làm thủng CSRF.
.csrf(csrf -> csrf.ignoringRequestMatchers(request ->
    "mobile".equals(request.getHeader("X-Client-Type"))
))
~~~

Tương tự, không bỏ CSRF chỉ vì request có **Authorization header**, nếu chain đó có thể xác thực bằng cookie khi Authorization rỗng, sai hoặc bị xử lý bởi authentication provider khác.

Điều cần chứng minh bằng test là **mỗi route chỉ có authentication mechanism đúng với CSRF policy của nó**.

## 4. Client native: token và vòng đời đăng nhập an toàn

Một native app là **public OAuth client**: mã chạy trên thiết bị người dùng không thể giữ client secret tĩnh như một backend server. Khi có nhà cung cấp OAuth/OIDC, lựa chọn thông dụng là **Authorization Code Flow với Proof Key for Code Exchange (PKCE)** và system browser.

### 4.1. Luồng minh họa OAuth2 Authorization Code + PKCE

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Native app
    participant Browser as System browser
    participant AS as Authorization server
    participant API as Resource server Spring
    App->>App: Sinh code_verifier, code_challenge và state
    App->>Browser: Mở authorization request + challenge + state
    Browser->>AS: Đăng nhập và phê duyệt
    AS-->>App: Redirect URI được đăng ký, code và state
    App->>App: Xác minh state và redirect URI
    App->>AS: Đổi code + code_verifier lấy token
    AS-->>App: Access token; refresh token nếu được cấp
    App->>API: Authorization Bearer access_token
    API->>API: Xác minh token, scope, quyền
    API-->>App: Dữ liệu được phép
~~~

Ở đây:

- **PKCE** liên kết authorization code với thiết bị/client đã bắt đầu giao dịch, giảm rủi ro đánh cắp code.
- **state** giúp liên kết response với request và phòng ngừa authorization response injection/CSRF trong luồng OAuth.
- Dùng **redirect URI** được đăng ký đúng loại native app (app-claimed HTTPS link/universal link/app link hoặc custom scheme có biện pháp bảo vệ phù hợp).
- **OIDC nonce** khi dùng ID token cần xử lý theo giao thức tương ứng; đừng dùng ID token thay access token để gọi API nếu API không thiết kế như vậy.
- Browser authorization server có cookie và lớp phòng vệ web riêng; native resource API Bearer-only không vì thế cần XSRF cookie.

**Không nhúng client secret cố định vào file APK/IPA** với kỳ vọng nó được bảo mật. Không tự phát JWT từ ứng dụng; access token phải được cấp và xác minh bởi hệ thống tin cậy.

### 4.2. Lưu credential trong native app

Nên dùng **iOS Keychain** hoặc **Android Keystore kết hợp cơ chế lưu trữ credential an toàn** theo nền tảng/thư viện được hỗ trợ. Tránh lưu refresh token thô trong SharedPreferences thông thường, localStorage của WebView, logcat hoặc crash reports.

Token nên có scope tối thiểu, access token ngắn hạn phù hợp, refresh token rotation/revocation theo chính sách của authorization server. Khi logout trên mobile, xóa credential cục bộ **và** gọi endpoint thu hồi token hoặc sign-out tương ứng nếu kiến trúc cung cấp; xóa UI state không tự làm token đã cấp vô hiệu.

### 4.3. Native HTTP request chỉ gắn credential có chủ đích

Ví dụ Retrofit/OkHttp hoặc URLSession trên native tạo request HTTPS và tự thêm Authorization từ một token manager:

~~~http
PATCH /api/mobile/profile HTTP/1.1
Host: api.example.com
Authorization: Bearer access-token-issued-for-mobile
Content-Type: application/json

{"displayName":"Nguyen A"}
~~~

Một native HTTP client thông thường **không bị browser CORS chặn**. Không nên thêm Access-Control-Allow-Origin: * hoặc cho credentials=true chỉ để “hỗ trợ mobile”; CORS là cơ chế browser, không cấp quyền API.

Tuy nhiên native app phải bảo vệ credential, xác minh TLS và xử lý lỗi **401** khi token hết hạn. Request trả **403** có thể do thiếu scope/role, không mặc định là thiếu CSRF.

## 5. Browser: cookie tự gửi và vòng đời CSRF token

Với browser app dùng session cookie, trình duyệt có thể tự đính kèm cookie cho các request phù hợp. CSRF token được lấy từ response HTML/JSON hoặc cookie JS-readable theo repository và request handler đã chọn.

~~~http
GET /api/csrf HTTP/1.1
Host: api.example.com
Origin: https://shop.example.com
Cookie: JSESSIONID=browser-session
~~~

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://shop.example.com
Access-Control-Allow-Credentials: true
Cache-Control: no-store
Content-Type: application/json

{"headerName":"X-CSRF-TOKEN","token":"masked-or-raw-per-handler"}
~~~

Khi POST:

~~~http
POST /api/web/orders HTTP/1.1
Host: api.example.com
Origin: https://shop.example.com
Cookie: JSESSIONID=browser-session
X-CSRF-TOKEN: masked-or-raw-per-handler
Content-Type: application/json

{"sku":"P100","quantity":1}
~~~

**HeaderName và token phải khớp request handler đang sử dụng.** Ở Spring Security 6 Servlet, request attribute có thể xuất token XOR-masked để giảm BREACH. Nếu frontend GET token JSON, hãy gửi nguyên giá trị JSON qua handler biết giải masked header; không ghép với handler giả định mọi header là raw token lấy từ XSRF cookie.

### 5.1. Login/logout trong browser có thể xóa CSRF token

Trên Servlet, **CsrfAuthenticationStrategy** và **CsrfLogoutHandler** có thể xóa token CSRF cũ khi authentication hoặc logout thành công. Token mới có thể được materialize ở GET tiếp theo do deferred loading.

Chu trình nên là:

~~~text
GET /api/csrf lúc anonymous -> token A
POST /login với A và cookie phiên anonymous
Login thành công -> session có thể đổi, A có thể bị xóa
GET /api/csrf với cookie hiện tại -> token B
POST /api/web/orders với B
POST /logout với token B hiện hành
Logout thành công -> lấy token C cho anonymous nếu cần
~~~

**Đừng xóa CSRF token phía frontend trước khi gửi POST logout.** Logout cookie-based có thể được CSRF bảo vệ; xóa token trước khiến chính request logout bị chặn.

### 5.2. SPA khác origin phải phối hợp credentials và CORS

Nếu SPA ở **https://shop.example.com**, API ở **https://api.example.com**, chúng khác origin dù có thể cùng site. Với cookie-based API:

~~~javascript
const API = "https://api.example.com";

async function fetchCsrf() {
  const response = await fetch(API + "/api/csrf", {
    credentials: "include",
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error("CSRF bootstrap failed: " + response.status);
  }
  return response.json();
}

async function createOrder(order) {
  const csrf = await fetchCsrf();

  const response = await fetch(API + "/api/web/orders", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify(order)
  });

  if (!response.ok) throw new Error("Request denied: " + response.status);
  return response.status === 204 ? null : response.json();
}
~~~

**credentials include không cho JavaScript đọc cookie host-only thuộc api.example.com** qua document.cookie ở shop.example.com. Vì vậy endpoint JSON cấp token có CORS allowlist thường phù hợp hơn việc mở rộng Domain cookie XSRF chỉ để frontend đọc.

GET token và POST phải dùng cùng session/cookie. CORS response cần **Access-Control-Allow-Origin: https://shop.example.com** (không wildcard) và **Access-Control-Allow-Credentials: true**. Preflight OPTIONS thường không mang session cookie nên phải được CORS xử lý trước authentication.

## 6. Ma trận quyết định trước khi viết cấu hình

Trước khi quyết định tắt CSRF cho một nhóm API, trả lời đủ:

| Câu hỏi | Nếu có | Hành động |
| --- | --- | --- |
| Browser có thể gửi credential được server chấp nhận mà không cần biết bí mật? | Cookie/session/Basic | CSRF cần được đánh giá/bật cho unsafe methods |
| Route chỉ nhận Bearer được client chủ động thêm, không có fallback cookie? | Bearer-only | Có thể tắt CSRF trên chain giới hạn route đó, vẫn giữ authz/token validation |
| Native app dùng WebView/embedded HTML đăng nhập bằng cookie? | Web credential | Đối xử với route theo chính sách browser |
| Mobile HTTP client có cookie jar nhưng không có browser-origin interaction? | Cookie riêng native | Phân tích threat model, đừng suy luận từ chữ mobile |
| Refresh/logout dùng cookie? | Browser-managed refresh | Bảo vệ endpoint đó theo policy cookie, kể cả khi access API dùng Bearer |
| API dùng cùng path cho cookie và Bearer? | Mixed credential | Cần thiết kế tách/ràng buộc cơ chế; không chỉ bỏ CSRF theo header |
| SPA khác origin gọi API cookie-auth? | Cross-origin browser | Credentials include + exact CORS allowlist + CSRF |
| App yêu cầu chức năng offline/deep link? | External input vào native app | Validate link/intent và hành động, không tự gửi request nhạy cảm dựa trên link |

Bài học tiếp theo triển khai chính sách này bằng **hai SecurityFilterChain** trong Servlet và **hai SecurityWebFilterChain** trong WebFlux. Logic nghiệp vụ vẫn được dùng chung.

## 7. Servlet: hai SecurityFilterChain với authentication policy khác nhau

Đây là phương án tham khảo cho **Spring Boot 3, Spring Security 6.x và Java 17+**. Giả định:

- **/api/mobile/** là API chỉ chấp nhận JWT Bearer access token.
- **/api/web/** là API nhận session cookie browser và bật CSRF.
- GET **/api/csrf** cấp token cho browser.
- Web formLogin/logout mặc định xử lý tại **/login** và **/logout** theo cấu hình demo.
- Chức năng nghiệp vụ có thể do một service dùng chung thực hiện.

### 7.1. Filter chain ưu tiên cho mobile Bearer-only

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class MultiClientSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain mobileApiSecurity(HttpSecurity http)
            throws Exception {
        return http
            .securityMatcher("/api/mobile/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .requestCache(cache -> cache.disable())
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .logout(logout -> logout.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/api/mobile/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserSecurity(HttpSecurity http)
            throws Exception {
        return http
            // Chain này catch-all: cả /api/web/**, /api/csrf,
            // /login và /logout đều được nó xử lý.
            .cors(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers("/api/web/**").authenticated()
                .anyRequest().permitAll())
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .build();
    }
}
~~~

**Tại sao hai filter chain?**

1. Spring Security chọn **chain đầu tiên có securityMatcher phù hợp**. Vì thế **@Order(1)** bắt mobile path trước chain browser catch-all.
2. Mobile chain chỉ cấu hình **JWT resource server**, tắt formLogin và HTTP Basic, dùng stateless session policy và không tạo CSRF yêu cầu trên chính nhóm Bearer-only.
3. Browser chain giữ CSRF mặc định cho unsafe methods, đồng thời hỗ trợ session login và logout.
4. Browser chain **không** có securityMatcher giới hạn /api/web/**, vì trong ví dụ cần bảo vệ cả **POST /login** và **POST /logout** ở path mặc định. Nếu giới hạn chain không đúng, login/logout có thể rơi ngoài security filter chain dự định.
5. Mobile scope **SCOPE_orders.write** được kiểm tra cho POST tạo đơn; scope đơn thuần chưa đủ để bỏ kiểm tra ownership và business authorization trong service.
6. Chỉ phần mobile chain có **csrf.disable()**. Không diễn giải đoạn này thành “REST API luôn tắt CSRF”.

**Giới hạn bắt buộc của thiết kế:** Resource server phải được cấu hình **issuer-uri**, **jwk-set-uri** hoặc decoder/introspection phù hợp để xác minh access token, và phải kiểm tra issuer/audience/scope theo hệ thống. Đoạn Java trên **không tự cấp access token**. Không dùng ID token làm API access token.

### 7.2. Tại sao không tắt CSRF theo Authorization header?

Anti-pattern:

~~~java
// KHÔNG DÙNG khi cùng chain còn chấp nhận cookie session.
.csrf(csrf -> csrf.ignoringRequestMatchers(request ->
    request.getHeader("Authorization") != null
))
~~~

Một request có header Authorization không chứng minh backend cuối cùng xác thực **bằng Bearer**. Nếu có cookie fallback hoặc nhiều authentication provider, có thể tồn tại đường đi khác vẫn chấp nhận cookie. **User-Agent**, Origin rỗng hay header X-Client-Type cũng không phải tín hiệu bảo mật đáng tin.

Trong mẫu tách path, mobile chain được giới hạn route và cơ chế nhận credential. Điều này giúp code review, kiểm thử và giới hạn tác động của thay đổi.

### 7.3. CORS nguồn browser, không phải quyền mobile

Nếu browser SPA tại https://shop.example.com gọi API tại https://api.example.com bằng cookie, cần CORS cho browser chain. Native HTTP client không chịu CORS browser; không có lý do cho phép mọi Origin chỉ để mobile chạy.

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://shop.example.com"));
    cors.setAllowedMethods(List.of(
        "GET", "POST", "PUT", "PATCH", "DELETE"));
    cors.setAllowedHeaders(List.of(
        "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
    cors.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/web/**", cors);
    source.registerCorsConfiguration("/api/csrf", cors);
    source.registerCorsConfiguration("/login", cors);
    source.registerCorsConfiguration("/logout", cors);
    return source;
}
~~~

**CORS phải bao phủ đường login/logout nếu SPA gọi chúng khác origin**, không chỉ các business API. Preflight OPTIONS thường không mang JSESSIONID, vì vậy CORS processor phải xử lý nó trước bước authentication.

Không dùng **allowedOrigins("*")** cùng credentials, không phản chiếu tùy tiện mọi Origin. Nếu mobile API không dành cho JavaScript browser, không tự mở CORS cho /api/mobile/**.

### 7.4. Browser CSRF bootstrap controller Servlet

Với HttpSessionCsrfTokenRepository và request handler mặc định của Servlet 6.x, browser có thể GET token JSON:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class BrowserCsrfBootstrapController {

    record CsrfPayload(String headerName, String token) {}

    @GetMapping("/api/csrf")
    ResponseEntity<CsrfPayload> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        if (token == null) {
            throw new IllegalStateException(
                "Browser CSRF filter is not active");
        }

        // Deferred token được materialize tại đây.
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new CsrfPayload(
                token.getHeaderName(), token.getToken()));
    }
}
~~~

Với **Spring Security 6**, request attribute có thể chứa token **XOR-masked** để giảm BREACH. JavaScript gửi nguyên token JSON trong đúng header; handler tương ứng phải giải giá trị đó. Không ghép response JSON masked với handler chỉ nhận raw token từ cookie.

### 7.5. Cùng business service, hai HTTP adapters

Hai controller sau là **khung tích hợp**, cần OrderService và DTO thực của dự án:

~~~java
import java.security.Principal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderEndpoints {

    private final OrderApplicationService orders;

    OrderEndpoints(OrderApplicationService orders) {
        this.orders = orders;
    }

    record CreateOrder(String sku, int quantity) {}

    @PostMapping("/api/mobile/orders")
    Object createFromMobile(
            Principal principal,
            @RequestBody CreateOrder input) {
        return orders.placeOrder(principal.getName(), input);
    }

    @PostMapping("/api/web/orders")
    Object createFromBrowser(
            Principal principal,
            @RequestBody CreateOrder input) {
        return orders.placeOrder(principal.getName(), input);
    }
}
~~~

**OrderApplicationService là interface/service ứng dụng cần triển khai**, không phải class của Spring Security. Dùng cùng logic không có nghĩa chỉ cần check principal có mặt. Service phải kiểm tra ownership, tồn kho, idempotency, rate limit và các quy tắc nghiệp vụ; không tin userId tùy ý trong request body.

### 7.6. Lỗi thường gặp với thứ tự filter chain

| Lỗi | Nguyên nhân khả dĩ |
| --- | --- |
| Mobile POST có Bearer đúng nhưng bị yêu cầu CSRF | Request mobile rơi vào browser chain hoặc có rule CSRF khác |
| Browser POST thiếu CSRF vẫn thành công | Browser path vô tình khớp chain mobile đã disable CSRF |
| Form login không hoạt động | Browser chain chỉ match /api/web/** nhưng /login nằm ngoài |
| Mobile token được chấp nhận qua cookie | Có cấu hình authentication fallback ngoài dự kiến |
| OPTIONS nhận 401 | CORS bị xử lý sau authentication hoặc path không có CORS policy |
| Browser có token nhưng POST 403 | Session cookie lệch, token raw/XOR sai hoặc thiếu quyền |

**Không khắc phục sai chain bằng cách disable CSRF trên cả hai.** Sửa matcher, thứ tự, auth mechanism và regression test.

## 8. Reactive/WebFlux: tách SecurityWebFilterChain tương đương

Ứng dụng **WebFlux** dùng **ServerHttpSecurity**, **SecurityWebFilterChain**, **CsrfWebFilter**, **ServerWebExchange**, **WebSession**, không copy nguyên HttpSecurity hoặc HttpServletRequest từ Servlet.

### 8.1. Mobile resource server Reactive

Ví dụ Spring Security 6.x WebFlux:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Bean
@Order(1)
SecurityWebFilterChain mobileReactiveSecurity(
        ServerHttpSecurity http) {
    return http
        .securityMatcher(new PathPatternParserServerWebExchangeMatcher(
            "/api/mobile/**"))
        .securityContextRepository(
            NoOpServerSecurityContextRepository.getInstance())
        .csrf(csrf -> csrf.disable())
        .httpBasic(basic -> basic.disable())
        .formLogin(form -> form.disable())
        .authorizeExchange(auth -> auth
            .pathMatchers(HttpMethod.POST, "/api/mobile/orders")
                .hasAuthority("SCOPE_orders.write")
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        .build();
}
~~~

Ở đây không dùng WebSession để lưu principal cho mobile. Cấu hình JWT decoder/issuer/audience và business authorization vẫn cần tồn tại. Không tự coi prefix /api/mobile là đủ an toàn nếu chain hoặc custom authentication vẫn chấp nhận cookie.

### 8.2. Browser chain Reactive

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.reactive.CorsConfigurationSource;

@Bean
@Order(2)
SecurityWebFilterChain browserReactiveSecurity(
        ServerHttpSecurity http,
        CorsConfigurationSource browserCorsSource) {
    return http
        .cors(cors -> cors.configurationSource(browserCorsSource))
        .csrf(Customizer.withDefaults())
        .authorizeExchange(auth -> auth
            .pathMatchers(HttpMethod.GET, "/api/csrf").permitAll()
            .pathMatchers("/api/web/**").authenticated()
            .anyExchange().permitAll())
        .formLogin(Customizer.withDefaults())
        .logout(Customizer.withDefaults())
        .build();
}
~~~

Cũng như Servlet, browser chain ở đây **catch-all sau mobile chain**, giúp login/logout mặc định đi qua chính chain có CSRF và session. **CorsConfigurationSource phải thuộc package reactive**, và policy chỉ cấp credentialed response cho origin browser tin cậy.

### 8.3. CORS source Reactive

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Bean
UrlBasedCorsConfigurationSource browserCorsSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://shop.example.com"));
    cors.setAllowedMethods(List.of(
        "GET", "POST", "PUT", "PATCH", "DELETE"));
    cors.setAllowedHeaders(List.of(
        "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
    cors.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/web/**", cors);
    source.registerCorsConfiguration("/api/csrf", cors);
    source.registerCorsConfiguration("/login", cors);
    source.registerCorsConfiguration("/logout", cors);
    return source;
}
~~~

Không import nhầm **org.springframework.web.cors.UrlBasedCorsConfigurationSource** của Servlet. Hạn chế cấu hình hai CORS filter chồng nhau, đặc biệt khi đã có gateway hoặc CorsWebFilter riêng.

### 8.4. GET CSRF token Reactive

~~~java
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
class BrowserReactiveCsrfController {

    @GetMapping("/api/csrf")
    Mono<ResponseEntity<Map<String, String>>> csrf(
            ServerWebExchange exchange) {

        Mono<CsrfToken> tokenMono =
            exchange.getAttribute(CsrfToken.class.getName());

        if (tokenMono == null) {
            return Mono.error(new IllegalStateException(
                "Browser CSRF WebFilter is not configured"));
        }

        return tokenMono.map(token -> ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken())));
    }
}
~~~

Token được nạp trong **Mono pipeline**; không gọi block() trong reactive controller. Với WebSessionServerCsrfTokenRepository và XOR handler của WebFlux 6.x, token JSON cần được client gửi theo hợp đồng với handler thực tế.

### 8.5. Phân biệt Reactive và Servlet khi tổ chức routes

| Tác vụ | Servlet | WebFlux |
| --- | --- | --- |
| Tách chain ưu tiên | SecurityFilterChain, securityMatcher, @Order | SecurityWebFilterChain, securityMatcher, @Order |
| JWT bearer resource server | HttpSecurity.oauth2ResourceServer | ServerHttpSecurity.oauth2ResourceServer |
| CSRF browser | CsrfFilter + HttpSession/Cookie repo | CsrfWebFilter + WebSession/Cookie repo |
| Đọc CSRF token | HttpServletRequest attribute | ServerWebExchange attribute Mono |
| CORS | CorsConfigurationSource Servlet | CorsConfigurationSource Reactive |
| Test bảo mật | MockMvc | WebTestClient |

Không cố sử dụng **CsrfAuthenticationStrategy** hoặc **CsrfLogoutHandler** Servlet trong WebFlux; authentication và logout Reactive có implementation riêng. Tình huống cần chứng minh là **token/session nào thực sự còn hiệu lực sau auth transition**.

## 9. Endpoint dùng chung URL: có thể làm, nhưng không đơn giản

Một số hệ thống muốn cùng POST **/api/orders** cho mobile và browser. Khi đó việc gắn CSRF policy vào một route chung phức tạp hơn:

- Nếu cho phép cả **Bearer và cookie session** trên cùng route, không được bỏ CSRF chỉ vì request có header Authorization.
- CsrfFilter chạy tại một vị trí trong filter chain; một matcher dựa vào “đã authentication thành công bằng cơ chế nào” cần được thiết kế theo thứ tự và implementation thực tế, không suy đoán từ tên header.
- Nếu áp CSRF cho mọi POST, native Bearer-only client có thể cần đáp ứng token không cần thiết; điều này thường thúc đẩy việc chia rõ ranh giới API thay vì bypass không an toàn.
- Nếu backend đặt một **gateway/BFF** giữa client và service, nên giữ policy ở browser-facing boundary; service nội bộ có thể dùng token service-to-service và authorization riêng.
- Nếu hai loại client thực sự có auth policy giống nhau, không cần tách theo loại thiết bị. **Tách theo cơ chế credential**, không tách chỉ để đặt tên.

**Cách an toàn dễ chứng minh nhất cho bài học là hai route/chain riêng nhưng dùng chung service.** Chỉ thay đổi khi có bài toán kỹ thuật thực sự và có integration test cho mọi tổ hợp credential.

## 10. Refresh token, logout và các ngoại lệ bảo mật

### 10.1. Mobile refresh token

Native app dùng refresh token do OAuth/OIDC authorization server cấp có thể gọi token endpoint theo protocol thích hợp. Refresh token cần lưu an toàn, rotation và revocation nếu supported; không đưa token vào URL, deep link hoặc web analytics. Token endpoint của authorization server có cơ chế phòng vệ riêng, không phải GET /api/csrf của web session.

Một **resource server Bearer-only** không bắt buộc nhận cookie XSRF khi mobile refresh được thực hiện theo OAuth protocol độc lập. Nhưng nếu backend tự viết refresh endpoint đọc cookie HttpOnly do browser tự gửi, endpoint đó cần **đánh giá CSRF** như một browser cookie action.

### 10.2. Browser refresh token trong cookie

Một SPA có thể giữ access token ngắn hạn trong memory nhưng dùng **refresh cookie HttpOnly** ở /auth/refresh. Dù các business API sử dụng Bearer header, **POST refresh** vẫn nhận browser-managed credential, nên phải xem xét CSRF, Origin/Fetch Metadata, SameSite và CORS chính xác.

Không suy luận “vì business API dùng Bearer nên mọi endpoint ở /auth đều bỏ CSRF”. Cần policy riêng cho refresh và logout sử dụng cookie.

### 10.3. Logout phải phù hợp cơ chế thực tế

| Loại client | Logout thường bao gồm | Điều không nên giả định |
| --- | --- | --- |
| Browser session | POST logout có CSRF + xóa session/SecurityContext/cookie | Không cần token CSRF vì đây là API JSON |
| Mobile Bearer-only | Xóa token trên device, revoke refresh/token hoặc phiên server nếu hệ thống hỗ trợ | Xóa UI đồng nghĩa access token lập tức bị revoke |
| WebView cookie session | Logout qua browser/web security flow | WebView tự được miễn CSRF vì nằm trong native app |
| BFF | Logout session browser ở BFF và xử lý token server-side | Token của backend có thể được gửi trực tiếp cho JS/mobile |

### 10.4. Deep link, callback và WebView

Một URI callback OAuth hoặc deep link vào native app là **dữ liệu đầu vào từ bên ngoài**. App phải xác minh state, redirect target và parameter, không tự động tạo giao dịch nhạy cảm chỉ vì một deep link có vẻ hợp lệ.

Không truyền access token/refresh token qua URL cho một WebView không tin cậy. Nếu native app mở trang HTML có authentication cookie, trang đó vẫn cần bảo vệ CSRF như browser và chống XSS, kiểm soát JavaScript bridge và navigation.

## 11. Kiểm thử Servlet: tách đúng mobile Bearer và browser CSRF

Đừng chỉ kiểm tra mobile gọi API thành công. Cần chứng minh mobile route **chỉ nhận Bearer**, không dùng cookie browser làm authentication fallback; browser route phải **từ chối POST thiếu CSRF**, dù đã đăng nhập.

### 11.1. Mobile POST có JWT mock, không cần token CSRF

Ví dụ dưới đây dùng **spring-security-test**, giả định endpoint /api/mobile/orders có thật và trả 2xx khi dữ liệu hợp lệ:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MobileBearerOnlyTests {

    @Autowired MockMvc mvc;

    @Test
    void mobileBearerWithScopeDoesNotNeedCsrf() throws Exception {
        mvc.perform(post("/api/mobile/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write")))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().is2xxSuccessful());
    }

    @Test
    void mobileRequestWithoutBearerIsDenied() throws Exception {
        mvc.perform(post("/api/mobile/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**Giới hạn:** Helper **jwt()** mô phỏng Authentication đã thành công, **không kiểm chứng JWT signature, issuer, audience, JWKS hoặc hết hạn**. Cần test resource server với token phát từ một authorization server kiểm thử. Status 401/403 tùy entry point và scope, nhưng phải bảo đảm không có side effect khi request không hợp lệ.

### 11.2. Browser POST thiếu CSRF vẫn bị chặn

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BrowserCsrfIsolationTests {

    @Autowired MockMvc mvc;

    @Test
    void browserPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/web/orders")
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void browserPostWithCsrfCanPassFilter() throws Exception {
        mvc.perform(post("/api/web/orders")
                .with(user("alice"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

Helper **user()** và **csrf()** chỉ giả lập principal/CSRF trong test, không mô phỏng browser cookie và login thật. Tách kiểm thử chain khỏi kiểm thử cookie jar và login/logout end-to-end.

### 11.3. Browser GET token JSON rồi POST cùng session

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class BrowserSessionTokenTests {

    @Autowired MockMvc mvc;

    @Test
    void getTokenMustMatchCurrentSession() throws Exception {
        MvcResult bootstrap = mvc.perform(get("/api/csrf"))
            .andExpect(status().isOk())
            .andReturn();

        String body = bootstrap.getResponse().getContentAsString();
        String header = JsonPath.read(body, "$.headerName");
        String token = JsonPath.read(body, "$.token");
        MockHttpSession session =
            (MockHttpSession) bootstrap.getRequest().getSession(false);

        if (session == null) {
            throw new AssertionError("Session-backed CSRF expected");
        }

        mvc.perform(post("/api/web/orders")
                .session(session)
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/web/orders")
                .session(session)
                .with(user("alice"))
                .header(header, token)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

Với **HttpSessionCsrfTokenRepository**, GET có thể tạo session để lưu token anonymous. Cần assert dữ liệu **không thay đổi** ở request 403. Mẫu trên giả định controller POST thật có tồn tại và dữ liệu hợp lệ.

### 11.4. Integration test bắt buộc: cookie browser không xác thực mobile

Không dùng mock helper cho test này:

1. Thực hiện login browser thật, lấy JSESSIONID hợp lệ.
2. POST /api/mobile/orders **chỉ với cookie JSESSIONID**, không có Authorization Bearer.
3. Xác minh bị từ chối và không tạo đơn hàng.
4. POST mobile route với Bearer JWT hợp lệ và scope đủ, **không** có CSRF header; được xử lý.
5. POST browser route có cookie nhưng không CSRF header; phải bị từ chối.
6. Thử gửi cookie vào mobile route cùng một Bearer JWT bị hết hạn; cookie không được khiến request được chấp nhận.
7. Nếu dùng custom authentication, HTTP Basic hoặc remember-me, kiểm tra chúng không vô tình trở thành credential fallback trên mobile route.

Mục đích là kiểm tra giả định **Bearer-only** bằng hành vi, không chỉ đọc cấu hình.

## 12. WebTestClient: kiểm thử hai SecurityWebFilterChain

### 12.1. Mobile với mockJwt không gửi CSRF

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Đoạn thân test với WebTestClient và endpoint thật.
webTestClient.mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.write")))
    .post().uri("/api/mobile/orders")
    .bodyValue(Map.of("sku", "P100", "quantity", 1))
    .exchange()
    .expectStatus().is2xxSuccessful();
~~~

Cần import **java.util.Map** và spring-security-test. **mockJwt()** không xác minh token thực; test JWT decoder và authorization server integration riêng.

### 12.2. Browser với mockUser phải có CSRF

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

// Đoạn thân test; cần browser route thực tế.
webTestClient.mutateWith(mockUser("alice"))
    .post().uri("/api/web/orders")
    .bodyValue(Map.of("sku", "P100", "quantity", 1))
    .exchange()
    .expectStatus().isForbidden();

webTestClient.mutateWith(mockUser("alice")).mutateWith(csrf())
    .post().uri("/api/web/orders")
    .bodyValue(Map.of("sku", "P100", "quantity", 1))
    .exchange()
    .expectStatus().is2xxSuccessful();
~~~

Test helper không chứng minh WebSession cookie đã được browser lưu hay JSON token được cấp đúng. Với Reactive, cần integration test **GET /api/csrf → giữ WebSession cookie → POST thiếu/sai/đúng token → login/logout → GET token mới**.

Một hệ thống có cả gateway WebFlux và service Servlet phải xác định **lớp browser-facing**. BFF/gateway xử lý cookie và CSRF; service-to-service có thể dùng JWT/mtls/authorization riêng, không tự copy CSRF policy của browser vào mọi request nội bộ.

## 13. Ma trận kiểm thử end-to-end theo client và credential

| Kịch bản | Kết quả bảo mật phải chứng minh |
| --- | --- |
| Native POST /api/mobile/orders với JWT đúng và scope đủ | Được xử lý, không yêu cầu CSRF token |
| Native POST không Bearer | Bị từ chối, không có side effect |
| Native POST với JWT hết hạn/sai chữ ký/issuer/audience | Resource server từ chối |
| Native POST có JWT hợp lệ nhưng thiếu scope | Authorization từ chối |
| Native POST chỉ mang JSESSIONID của browser | **Không được xác thực trên mobile route** |
| Native POST mang cookie hợp lệ và Bearer sai | Cookie không được dùng để vượt Bearer verification |
| Browser POST /api/web/orders có session nhưng không CSRF | CSRF filter từ chối, dữ liệu không thay đổi |
| Browser POST có token đúng nhưng chưa đăng nhập | Không được quyền thao tác |
| Browser POST có CSRF đúng nhưng user thiếu quyền | Authorization từ chối |
| Browser GET /api/csrf và POST dùng cùng session | Token JSON được chấp nhận theo handler thực tế |
| Browser GET token session A, POST session B | Không được dùng token của session cũ |
| Browser login/logout làm CSRF token cũ mất hiệu lực | Lấy token mới khi chuyển trạng thái |
| OPTIONS preflight từ origin được phép nhưng không cookie | CORS xử lý trước authentication |
| CORS request từ origin ngoài allowlist | Không được cấp quyền đọc response credentialed |
| WebView gửi cookie/session | Được bảo vệ CSRF như browser |
| WebView cố POST mobile route chỉ bằng cookie | Không được nhận diện là mobile Bearer |
| Native library có cookie jar | Không tự coi là browser; kiểm tra đúng auth mechanism được backend chấp nhận |
| Mobile refresh token bị revoke | Authorization server/resource server áp dụng revocation theo thiết kế |
| Browser refresh token bằng cookie HttpOnly | Có policy CSRF/Origin/CORS riêng |
| Callback OAuth/deep link | Kiểm tra state, PKCE, redirect URI và dữ liệu đầu vào |
| Nhiều tab browser thay đổi login/logout | Token cũ không tự động được tái sử dụng |
| Gateway chuyển identity qua header | Downstream chỉ tin header từ kênh tin cậy, không từ client tùy ý |
| XSS trên trang web/WebView | CSRF không thay CSP, output encoding và giới hạn bridge |

**Đừng kết luận từ status code một mình.** Với request bị từ chối, kiểm tra audit trail và dữ liệu không đổi; với thao tác nhạy cảm, kiểm tra cả authorization theo đối tượng (order ownership) và transaction.

### 13.1. Kiểm thử trình duyệt thực để phát hiện lỗi bị MockMvc che khuất

Mở DevTools ở SPA hoặc WebView được phép thử:

1. Xác minh GET /api/csrf dùng **credentials: include** nếu khác origin, được CORS allowlist và có Cache-Control: no-store.
2. Kiểm tra **OPTIONS preflight** cho JSON + custom CSRF header không bị yêu cầu JSESSIONID.
3. Kiểm tra Cookie session thuộc API vẫn HttpOnly; JavaScript không cần đọc nó để browser gửi request.
4. Kiểm tra POST /api/web/orders chủ động gắn CSRF header đúng format, session cookie đúng scope.
5. Cố ý bỏ header CSRF: server phải chặn và không tạo đơn.
6. Kiểm tra mobile native thực: request chỉ có Authorization Bearer; không cần cookies XSRF hoặc browser CORS response.
7. Khi WebView gọi API, xác định origin, cookie jar và trang HTML thực thay vì gán nhãn tất cả là mobile.
8. Xác minh login/logout, timeout, nhiều tab và refresh token không mở đường cookie-auth bypass trên mobile route.

Browser có thể báo CORS error dù server đã xử lý một simple request trước khi chặn response. **CSRF filter phải hoạt động độc lập với CORS**.

## 14. Chẩn đoán lỗi triển khai nhiều client

### “Mobile POST trả 403 MissingCsrfTokenException”

Request rất có thể đã đi qua **browser chain**, route mapping không khớp hoặc gateway rewrite URL khiến matcher không còn đúng. Kiểm tra SecurityFilterChain thực tế, @Order, URL sau proxy và rule csrf. **Không disable CSRF trên toàn backend** chỉ để mobile hết lỗi.

### “Browser POST không có CSRF vẫn tạo được đơn hàng”

Đây là rủi ro cần xử lý trước triển khai. Browser route có thể bị bắt bởi chain mobile đã tắt CSRF, hoặc có **ignoringRequestMatchers** quá rộng. Xác minh path, filter chain và tất cả các route cũ có cùng side effect. Viết regression test chứng minh dữ liệu không đổi khi request thiếu token.

### “Mobile gửi Bearer token nhưng bị 401”

Đây thường là **authentication failure**, không phải CSRF. Kiểm tra JWT decoder, issuer, audience, chữ ký, thời hạn, authorization server, gateway có loại bỏ Authorization header hay không và ứng dụng có dùng ID token thay access token không.

### “Mobile được phép gọi API bằng cookie JSESSIONID thay vì Bearer”

Chain mobile không thực sự **Bearer-only**, hoặc browser chain xử lý nhầm URL. Kiểm tra SecurityContext repository, remember-me, Basic, formLogin và custom filter. **Nếu cookie vẫn là credential hợp lệ cho unsafe request**, quyết định bỏ CSRF theo mobile path cần được xem lại ngay.

### “WebView bị 403 CSRF nhưng cùng thao tác qua native HTTP thành công”

Đây có thể là đúng chính sách: WebView là môi trường browser có cookie, còn native Bearer-only không tự gửi cookie cho website khác. Cấp CSRF token cho WebView qua HTML/JSON và bảo vệ như web; không tắt CSRF chỉ vì WebView nằm trong app.

### “Mobile cần Access-Control-Allow-Origin: * mới gọi được API”

HTTP client native như URLSession/OkHttp **không thực thi browser CORS**. Lỗi có thể đến từ WebView hoặc website gọi API, không phải native network stack. Giữ CORS exact allowlist cho browser, không cấp credentialed CORS wildcard.

### “Đăng nhập trong system browser nhưng API mobile đòi CSRF”

Trang **authorization server** có cookie và các cơ chế state/PKCE của OAuth. Sau khi app native nhận access token và gọi **resource server Bearer-only**, route đó không cần đồng bộ token CSRF web. Phân biệt đúng hai bên của giao thức.

### “Browser business API dùng Bearer, tại sao /auth/refresh vẫn cần CSRF?”

Nếu **refresh endpoint đọc cookie HttpOnly**, browser tự gửi credential ấy. Dù business API không dùng cookie, refresh vẫn cần đánh giá CSRF/Origin/CORS và chính sách session phù hợp. Có thể chia filter chain theo nhóm endpoint, không đưa tất cả vào một whitelist.

### “Android/iOS đã login mà trang mở trong WebView vẫn anonymous”

Cookie store của native HTTP library, system browser và WebView có thể **không chia sẻ** theo nền tảng/thiết lập. Không copy refresh token vào WebView như cách sửa nhanh. Nếu thật sự cần SSO giữa các môi trường, thiết kế token exchange/handshake được bảo vệ riêng.

### “Deep link từ bên ngoài khiến mobile gửi giao dịch nhạy cảm”

Đó là vấn đề **untrusted intent/deep-link input và confused-deputy**, không được giải thích đơn giản là CSRF web. Xác minh source, state, thông tin giao dịch và sự chấp thuận của user trước thao tác nhạy cảm; không để một URI tự kích hoạt chuyển tiền hoặc thay đổi mật khẩu.

### “Access token mobile xuất hiện trong log”

Đây là sự cố rò rỉ credential. Không log Authorization header, JWT, refresh token, CSRF token hoặc session ID. Dùng correlation ID, loại lỗi và metadata không nhạy cảm khi chẩn đoán; thu hồi token nếu bị lộ theo khả năng hệ thống.

## 15. Bài tập thực hành

**Bài tập A — Threat model:** Vẽ mobile native, Web SPA và WebView gọi cùng backend. Với từng request, ghi rõ credential nào được server chấp nhận, trình duyệt có tự đính kèm credential không, và server có yêu cầu CSRF token không.

**Bài tập B — Hai chain Servlet:** Triển khai mobile Bearer-only và browser cookie/CSRF theo phần 7. Chứng minh mobile Bearer đúng không cần CSRF nhưng browser cookie thiếu CSRF luôn bị từ chối.

**Bài tập C — Sai thứ tự chain:** Cố ý thay @Order hoặc matcher trong môi trường test để gây lỗi. Sửa bằng scope rõ ràng, không bằng cách tắt CSRF ở mọi route.

**Bài tập D — Test cookie fallback:** Đăng nhập browser thật, gửi cookie JSESSIONID tới mobile route không Authorization. Xác minh bị từ chối và không tạo đơn hàng.

**Bài tập E — Native OAuth:** Mô tả Authorization Code + PKCE, state, redirect URI, Keychain/Keystore, rotation và revocation; giải thích tại sao native app không thể giữ client secret tĩnh an toàn.

**Bài tập F — WebView:** Mở một trang HTML dùng cookie trong WebView và thử POST thiếu/có CSRF token. So sánh với URLSession/OkHttp gọi mobile route bằng Bearer; xem cookie jar và CORS khi trang khác origin.

**Bài tập G — WebFlux:** Tạo hai SecurityWebFilterChain, MockJwt cho mobile và WebTestClient mockUser/csrf cho browser. Thêm integration test WebSession thật.

**Bài tập H — Cookie refresh:** Giả lập browser business API dùng Bearer nhưng refresh qua HttpOnly cookie. Thiết kế security policy riêng cho refresh/logout, test CSRF và SameSite.

**Bài tập I — BFF/gateway:** Cho gateway nhận browser cookie và chuyển service token xuống backend. Xác định nơi phải có CSRF, nơi phải xác minh service identity và cách ngăn client tự giả mạo identity header.

## 16. Nguyên tắc cần nhớ

1. **CSRF phụ thuộc vào authentication mechanism mà server chấp nhận**, không phụ thuộc nhãn mobile, REST, SPA hoặc stateless.
2. **Native Bearer-only API thường không cần token CSRF truyền thống**, nhưng phải kiểm tra token, scope, issuer/audience, quyền và bảo vệ credential trên thiết bị.
3. **Browser và WebView sử dụng cookie vẫn cần CSRF**, kể cả dùng chung một backend với native app.
4. **Tách chain theo route và credential contract** giúp giới hạn phạm vi csrf.disable(); không bỏ CSRF bằng User-Agent hoặc header tự khai báo.
5. **Có thể dùng chung application/domain service** nhưng HTTP authentication, token lifecycle và CORS/CSRF policy có thể khác nhau.
6. **Native OAuth sử dụng Authorization Code + PKCE**, state, system browser và secure storage; không hardcode client secret.
7. **CORS phục vụ browser và WebView**, không phải cơ chế cấp quyền cho native HTTP client.
8. **Refresh/login/logout dùng cookie** cần được đánh giá CSRF riêng dù một số business API dùng Bearer.
9. **WebFlux dùng ServerHttpSecurity/WebSession/Mono riêng**, không copy class Servlet vào Reactive.
10. **Kiểm thử cả trường hợp thành công và bypass**: browser cookie không thể truy cập mobile route, browser thiếu CSRF không tạo side effect, mobile Bearer cần scope và authz đúng.

**Kết luận:** Khi một backend phục vụ cả mobile native và trình duyệt, không cần áp một chính sách CSRF máy móc cho mọi request. Hãy **xác định credential được server tin ở từng ranh giới**, giữ Bearer-only và stateless cho tuyến native phù hợp, đồng thời duy trì CSRF, CORS, session và cookie protection cho browser/WebView. Đặt test bảo mật vào từng tuyến giúp tránh “sửa lỗi mobile” bằng cách vô tình làm yếu website.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Servlet CSRF và SPA](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Servlet OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — CORS Servlet](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html)
- [Spring Security 6.5 — CSRF Reactive/WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — CORS WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html)
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252.html)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636.html)
- [MDN — Fetch credentials](https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials)
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — Set-Cookie và SameSite](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)


