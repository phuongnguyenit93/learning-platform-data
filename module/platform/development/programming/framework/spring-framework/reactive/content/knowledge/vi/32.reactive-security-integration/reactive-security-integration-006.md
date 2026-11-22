# CSRF, session và lựa chọn theo cách xác thực thực tế trong Spring WebFlux

## 1. Câu hỏi quan trọng nhất: trình duyệt gửi credential như thế nào?

Khi xây dựng bảo mật cho Spring WebFlux, nhiều người đặt câu hỏi: "Ứng dụng dùng JWT thì có thể tắt CSRF không?", hoặc "Dùng session thì có nhất thiết bật CSRF?". Cách hỏi đó chưa đủ chính xác.

**Rủi ro Cross-Site Request Forgery (CSRF) phụ thuộc chủ yếu vào việc browser có tự động gắn thông tin xác thực vào một request do website khác khởi tạo hay không.** Loại dữ liệu được dùng làm credential (session ID, JWT, opaque token) chỉ là một phần của câu trả lời.

Ba tình huống:

1. **Form login + session cookie:** browser tự gửi cookie của domain đích. Một trang độc hại có thể cố tạo request thay đổi dữ liệu với cookie của người dùng. Cần CSRF protection.
2. **API chỉ nhận Authorization: Bearer và client chủ động gắn token:** một form cross-site thông thường không thể tự lấy token rồi thêm Authorization header của người dùng. Nếu API thực sự không chấp nhận credential tự gửi như cookie, có thể vô hiệu CSRF cho đúng vùng API, đồng thời vẫn cần xác thực token, authorization, CORS và chống XSS.
3. **JWT hoặc bearer token nằm trong cookie:** browser vẫn tự gửi cookie. Hình thức "JWT" hoặc "stateless" không làm CSRF biến mất; vẫn cần cơ chế bảo vệ tương ứng.

Spring Security cho WebFlux có CSRF protection mặc định. Việc tắt phải dựa trên **authentication flow thực tế của từng nhóm endpoint**, không dựa trên tên công nghệ.

## 2. CSRF là gì? Một kịch bản cụ thể

Giả sử người dùng đăng nhập vào bank.example và browser lưu session cookie:

~~~http
Set-Cookie: SESSION=<opaque-session-id>; HttpOnly; Secure; SameSite=Lax; Path=/
~~~

Trang ngân hàng cung cấp:

~~~http
POST /transfer HTTP/1.1
Host: bank.example
Cookie: SESSION=<opaque-session-id>
Content-Type: application/x-www-form-urlencoded

to=attacker&amount=1000
~~~

Nếu endpoint chỉ kiểm tra session cookie mà không yêu cầu bằng chứng rằng request xuất phát từ giao diện hợp lệ, một website khác có thể cố dụ browser gửi request tương tự. Browser tự gửi cookie theo các quy tắc cookie hiện hành; trang độc hại không nhất thiết phải biết giá trị cookie.

Trong mô hình phòng vệ CSRF bằng synchronizer token:

1. Server sinh token bí mật khó đoán và gắn với session/ngữ cảnh bảo mật.
2. Giao diện hợp lệ lấy token qua form/meta tag hoặc endpoint cùng origin được bảo vệ.
3. Khi thực hiện POST, PUT, PATCH, DELETE, client đặt token vào **form parameter** hoặc **HTTP header**.
4. Browser **không tự thêm** header/parameter CSRF như cách tự thêm cookie.
5. Server so sánh token nhận được với token mong đợi; thiếu hoặc sai sẽ bị từ chối.

Ví dụ POST hợp lệ:

~~~http
POST /transfer HTTP/1.1
Host: bank.example
Cookie: SESSION=<opaque-session-id>
Content-Type: application/json
X-CSRF-TOKEN: <csrf-token>

{"to":"friend","amount":100}
~~~

Cookie và CSRF token có vai trò khác nhau: cookie chứng minh session của người dùng; CSRF token chứng minh request được tạo từ một luồng tương tác có quyền truy cập token.

CSRF không phải lỗi "đọc trộm dữ liệu" trực tiếp. Kẻ tấn công có thể không đọc được HTTP response do same-origin policy, nhưng vẫn có thể làm thay đổi trạng thái nếu server chấp nhận request giả mạo. CORS không phải giải pháp thay thế toàn diện cho CSRF.

## 3. Same-Origin Policy, CORS, SameSite và CSRF khác nhau

| Cơ chế | Mục tiêu chính | Có thay CSRF token? |
| --- | --- | --- |
| Same-Origin Policy | Hạn chế JavaScript ở origin khác đọc response/dữ liệu của origin đích | Không |
| CORS | Quy định khi nào browser cho phép cross-origin JavaScript access và một số request có preflight | Không |
| SameSite cookie | Hạn chế cookie được gửi trong ngữ cảnh cross-site | Là một lớp phòng vệ bổ sung, không nên là duy nhất |
| HttpOnly cookie | Ngăn JavaScript đọc giá trị cookie trực tiếp | Không; browser vẫn có thể gửi cookie |
| Secure cookie | Chỉ gửi cookie qua kết nối HTTPS | Không |
| CSRF token | Yêu cầu bằng chứng mà browser không tự gắn vào request | Là phòng vệ trực tiếp |
| XSS protection | Ngăn script độc hại chạy trong origin của ứng dụng | Cần thiết riêng; XSS có thể phá nhiều lớp bảo vệ |

Các lưu ý quan trọng:

- CORS chặn khả năng đọc response hoặc chặn một số cross-origin request có preflight, nhưng **HTML form** và các request đơn giản vẫn có thể gửi trong những tình huống nhất định.
- Content-Type application/json không phải chính sách chống CSRF đủ tin cậy cho mọi endpoint hoặc mọi proxy.
- SameSite=Lax thường cho phép cookie trong một số top-level navigation sử dụng method an toàn. Không tạo side effect qua GET.
- SameSite=None thường cần Secure; SameSite=Strict hạn chế nhiều cross-site navigation hơn nhưng có thể ảnh hưởng UX.
- Một lỗ hổng XSS cùng origin có thể đọc CSRF token được hiển thị cho JavaScript và tạo request hợp lệ. CSRF defense không thay thế CSP, output encoding và chống XSS.

## 4. WebSession trong Spring WebFlux

### 4.1. WebSession không phải HttpSession

Ứng dụng Servlet/Spring MVC thường dùng HttpSession. Ứng dụng reactive Spring WebFlux dùng abstraction **WebSession** và WebSessionManager.

Một WebSession có thể giữ state phía server, ví dụ:

- SecurityContext sau form login.
- Expected CSRF token khi dùng WebSessionServerCsrfTokenRepository.
- OAuth2 authorization request hoặc dữ liệu flow tùy cấu hình.
- Một số dữ liệu ứng dụng có chủ đích.

Browser thường giữ **session identifier** trong cookie. Cookie không mặc nhiên chứa toàn bộ user profile hoặc SecurityContext; server dùng ID để lấy session state.

Không nên nhầm "có cookie session" với "WebSession lưu mọi thứ". Cũng không nên nhầm "API dùng bearer token" với "chắc chắn không có WebSession": một component khác vẫn có thể tạo session nếu cấu hình cho phép.

### 4.2. Security context repository

Spring Security reactive có các ServerSecurityContextRepository:

- **WebSessionServerSecurityContextRepository:** lưu/tải SecurityContext qua WebSession, phù hợp cho interactive login khi muốn giữ trạng thái đăng nhập qua nhiều request.
- **NoOpServerSecurityContextRepository:** không lưu SecurityContext qua repository đó; thường dùng cho nhóm request xác thực độc lập như stateless bearer API.

NoOpServerSecurityContextRepository **không** tự bảo đảm toàn ứng dụng hoàn toàn không tạo WebSession. Nó chỉ nói về cách một security context repository xử lý context. Cần xem thêm form login, OAuth2 flow, session manager và code ứng dụng.

### 4.3. Session fixation, timeout và lưu trữ phân tán

Với browser login:

- Tạo/đổi session identifier phù hợp sau authentication để giảm rủi ro session fixation; đánh giá cơ chế session fixation protection mà framework cung cấp.
- Bảo vệ session cookie bằng Secure và HttpOnly, đặt SameSite phù hợp.
- Giới hạn session timeout; hỗ trợ logout và session invalidation đúng cách.
- Nếu chạy nhiều application instances, cân nhắc Spring Session + Redis hoặc session store chung khi thật sự cần state chia sẻ.
- Không giữ session vô thời hạn hoặc lưu dữ liệu lớn/nhạy cảm không cần thiết vào session.
- Trong cụm nhiều node, cookie là định danh; session store phải có tính nhất quán phù hợp.

Một hệ thống có thể đồng thời dùng WebSession cho web UI và xác thực bearer stateless cho API, nếu phân tách filter chain và credential policy rõ ràng.

## 5. CSRF trong Spring Security WebFlux

### 5.1. Mặc định

Với Spring Security cho WebFlux, CSRF protection được bật mặc định. Spring Security dùng:

- **CsrfWebFilter** để bảo vệ request phù hợp.
- **WebSessionServerCsrfTokenRepository** mặc định để giữ expected token trong WebSession.
- **ServerCsrfTokenRequestHandler** để đưa token ra request và phân tích token được gửi lại.
- Từ Spring Security 6, **XorServerCsrfTokenRequestAttributeHandler** được dùng mặc định, bổ sung masking nhằm giảm rủi ro BREACH khi token được render vào response.

Không cần thêm một bộ lọc CSRF thủ công nếu đã dùng Spring Security đúng cách.

Các method "safe" như GET, HEAD, TRACE, OPTIONS được xem là read-only trong mô hình CSRF mặc định. Những method thay đổi trạng thái như POST, PUT, PATCH, DELETE phải gửi token khi chain có CSRF enabled.

**Quan trọng:** đây là cơ sở để thiết kế HTTP API. Không được cập nhật dữ liệu, xóa tài khoản hoặc logout bằng GET rồi dựa vào việc "CSRF chỉ áp dụng POST".

### 5.2. Repository WebSession

Có thể ghi cấu hình tường minh:

~~~java
@Bean
SecurityWebFilterChain webChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/login", "/error").permitAll()
                    .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf.csrfTokenRepository(
                    new WebSessionServerCsrfTokenRepository()))
            .build();
}
~~~

Đây là snippet minh họa một chain; trong ứng dụng có nhiều chain phải thêm matcher/order. WebSessionServerCsrfTokenRepository phù hợp với browser interactive login khi server có session state.

### 5.3. Cung cấp token cho HTML form

Một form POST hợp lệ cần hidden field:

~~~html
<form action="/web/preferences" method="post">
  <input type="hidden" name="_csrf" value="token-from-server">
  <input type="text" name="theme" value="dark">
  <button type="submit">Save</button>
</form>
~~~

Trong ứng dụng dùng Thymeleaf có tích hợp Spring Security, token có thể được đưa vào form tự động khi view template được cấu hình đúng. Ví dụ HTML trên chỉ minh họa cấu trúc; không hardcode token.

### 5.4. Cung cấp token cho JavaScript fetch

CsrfWebFilter đưa một **Mono<CsrfToken>** vào ServerWebExchange attribute có tên CsrfToken.class.getName(). Controller có thể chủ động phát token về client đã authenticated:

~~~java
@GetMapping("/web/csrf")
Mono<CsrfView> csrf(ServerWebExchange exchange) {
    Mono<CsrfToken> token =
            exchange.getAttribute(CsrfToken.class.getName());

    if (token == null) {
        return Mono.error(new IllegalStateException(
                "CSRF token unavailable"));
    }

    return token.map(value -> new CsrfView(
            value.getHeaderName(), value.getToken()));
}
~~~

Đây là snippet trong controller với CsrfView là record do ứng dụng định nghĩa. Controller chỉ trả token cho request thuộc chain được CSRF bảo vệ và đã đáp ứng authentication/authorization.

Browser cùng origin gửi:

~~~javascript
async function saveTheme(theme) {
  const csrfResponse = await fetch("/web/csrf", {
    credentials: "same-origin"
  });

  if (!csrfResponse.ok) {
    throw new Error("Unable to obtain CSRF token");
  }

  const csrf = await csrfResponse.json();

  const response = await fetch("/web/preferences", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify({ theme })
  });

  if (!response.ok) {
    throw new Error("Update failed: " + response.status);
  }

  return response.json();
}
~~~

Sau login/logout hoặc thay đổi session, token cũ có thể không còn hợp lệ; client phải lấy token mới khi flow yêu cầu. Không cache response token công khai, không log token và không cho một origin không được tin cậy đọc endpoint này.

### 5.5. CookieServerCsrfTokenRepository cho SPA

Nếu framework JavaScript cần đọc CSRF token từ cookie, Spring Security có CookieServerCsrfTokenRepository:

~~~java
.csrf(csrf -> csrf.csrfTokenRepository(
        CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
~~~

Theo mặc định repository này dùng cookie **XSRF-TOKEN**, header **X-XSRF-TOKEN** hoặc parameter _csrf.

withHttpOnlyFalse() cho phép JavaScript đọc cookie. Chỉ dùng nếu frontend thật sự cần đọc cookie bằng JavaScript; nếu không, giữ cookie HttpOnly. Cần cấu hình Secure, SameSite, path, domain và CORS phù hợp với deployment.

**Lưu ý Spring Security 6+:** cơ chế masking/XOR của CSRF token có thể yêu cầu cấu hình ServerCsrfTokenRequestHandler phù hợp nếu SPA lấy **raw token** từ cookie rồi gửi thẳng qua header. Không mặc nhiên cho rằng chỉ đổi repository là hoạt động trong mọi phiên bản/cấu hình. Không tắt BREACH protection tùy tiện; hãy tuân theo hướng dẫn chính thức về SPA CSRF và kiểm thử request thật.

### 5.6. Không dùng CSRF cookie như credential

CSRF token không phải access token, không phải session ID và không xác thực user. Một request không có authentication hợp lệ không được chấp nhận chỉ vì mang CSRF token hợp lệ.

Cookie chứa CSRF token tự động được browser gửi đi; vì thế chỉ **kiểm tra cookie có tồn tại** không bảo vệ được trước CSRF. Cần token được submit qua phần mà attacker không thể tự khiến browser gắn vào như header hoặc form parameter và được server xác minh.

## 6. Khi nào có thể tắt CSRF?

### 6.1. API bearer-only thực sự

Ví dụ service chỉ nhận:

~~~http
POST /api/commands HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json

{"action":"sync"}
~~~

Browser không tự thêm một Bearer token của ứng dụng vào Authorization header trên request được khởi tạo từ website khác. Vì vậy, nếu API:

- Chỉ chấp nhận Authorization: Bearer explicit header.
- Không dùng cookie hoặc HTTP Basic ambient credentials để xác thực cùng endpoint.
- Không cho phép fallback sang session login khi thiếu bearer.
- Xác minh chữ ký/issuer/audience/expiry của JWT hoặc introspection token.
- Kiểm tra authorization và chống XSS.
- Áp dụng CORS và credential policy đúng mục đích.

thì việc disable CSRF **chỉ cho nhóm API đó** thường hợp lý.

Không cần gửi CSRF token ở mỗi API call bearer-only. Điều đó không làm bearer API "ít bảo mật": CSRF token ngăn một loại tấn công cụ thể, không thay thế authentication.

### 6.2. JWT trong cookie vẫn có CSRF

Nếu một JWT được đặt trong HttpOnly cookie và server tự đọc cookie để authenticate request, browser vẫn tự gửi cookie. Dùng JWT không làm mất rủi ro CSRF.

BFF (Backend for Frontend) dùng session cookie hoặc HttpOnly cookie để giữ credential cho browser cũng thuộc nhóm cần đánh giá CSRF, dù backend của BFF có thể gọi API downstream bằng bearer token. Luồng browser → BFF và BFF → API là hai security boundaries khác nhau.

### 6.3. HTTP Basic trong browser

HTTP Basic dùng Authorization header, nhưng browser có thể cache credentials và tự gửi lại trong những điều kiện nhất định. Vì vậy không tự động kết luận HTTP Basic browser-facing an toàn trước CSRF.

Với service-to-service Basic do code chủ động gắn credentials, đánh giá rủi ro khác; nhưng nên ưu tiên OAuth2/mTLS phù hợp khi ứng dụng cần authorization mạnh. Không dùng "mọi Authorization header đều chống CSRF" như quy tắc tuyệt đối.

### 6.4. CORS không thay CSRF

CORS kiểm soát khả năng JavaScript từ origin khác đọc response và các cơ chế preflight, không phải hệ thống chứng minh mỗi thay đổi trạng thái được người dùng chủ ý.

Trình duyệt có thể gửi form POST cross-site trong một số điều kiện dù JavaScript không đọc được response. Từ chối preflight không đủ để bảo vệ các endpoint chấp nhận request "simple". Ngay cả khi API chỉ trả JSON, hãy kiểm tra authentication flow, content negotiation và tất cả loại request được chấp nhận.

### 6.5. SameSite là defense-in-depth

Với cookie session nên cấu hình SameSite (Lax/Strict/None theo use case), Secure, HttpOnly và session expiry. SameSite giúp hạn chế cookie gửi cross-site, nhưng không nên là lý do duy nhất để tắt CSRF cho luồng có ambient credentials.

Các yếu tố như same-site subdomain, embedded iframe, OAuth login redirects, browser compatibility và những method được phép có thể làm thay đổi hiệu quả của SameSite.

## 7. Bảng quyết định theo cách xác thực thực tế

| Kiến trúc | Credential được gửi ra sao? | CSRF cho unsafe methods | Lưu ý |
| --- | --- | --- | --- |
| Web app form login + WebSession cookie | Browser tự gửi cookie | Bật | WebSessionServerCsrfTokenRepository mặc định |
| OAuth2 Login/OIDC browser web app | Browser thường giữ session login bằng cookie | Bật cho hành động sau login | OAuth2 state/nonce không thay CSRF của các POST nghiệp vụ |
| SPA gọi BFF bằng session cookie | Browser tự gửi cookie | Bật | Truyền token qua form/header, CORS chặt |
| API Authorization: Bearer riêng biệt | JS/app chủ động gắn token vào header | Có thể tắt ở chain API | Không fallback sang cookie/basic; xác minh bearer |
| JWT lưu trong HttpOnly cookie | Browser tự gửi JWT cookie | Bật | Stateless JWT không đồng nghĩa CSRF-safe |
| REST API đồng thời chấp nhận cookie và Bearer | Có ít nhất một credential ambient | Bật hoặc tách endpoint/chain | Tránh tắt toàn bộ chỉ vì có Bearer |
| HTTP Basic được browser dùng | Browser có thể tự gửi credential đã nhớ | Cần đánh giá/ưu tiên giữ bảo vệ | Không suy luận từ tên header |
| Public webhook ký HMAC | Service gửi chữ ký do code tạo | Thường không cần CSRF | Dùng signature, timestamp, replay protection |
| WebSocket browser với cookie auth | Cookie có thể đi trong handshake | CSRF HTTP filter không đủ sau upgrade | Kiểm tra Origin, auth và quyền từng message |
| SSE dùng cookie để đọc events | Browser tự gửi cookie trên GET | GET phải read-only, CORS/authorization | Thao tác thay đổi trạng thái vẫn cần bảo vệ |

Quy tắc: **Bắt đầu từ credential thực tế, xác định browser có tự gắn credential hay không, sau đó mới quyết định CSRF policy của từng endpoint.**

## 8. Tách nhiều SecurityWebFilterChain trong WebFlux

### 8.1. Vì sao tách?

Một ứng dụng có thể có:

- /web/**: giao diện browser đăng nhập bằng form, lưu SecurityContext vào WebSession, có CSRF.
- /api/**: machine/API client gửi Authorization: Bearer, không chấp nhận session, không cần CSRF.
- /login: form login cho browser.

Spring Security WebFlux cho phép đăng ký nhiều SecurityWebFilterChain; mỗi request được chọn chain theo securityMatcher và @Order. Chain chuyên biệt phải đứng trước chain catch-all.

Không viết một chain bao trùm cả hai kiểu rồi gọi .csrf(disable) chỉ để API bearer không bị 403. Điều đó làm vô hiệu phòng vệ của những endpoint browser session.

### 8.2. Chain bearer và chain session

~~~java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .securityContextRepository(
                    NoOpServerSecurityContextRepository.getInstance())
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers(HttpMethod.POST, "/api/commands")
                    .hasAuthority("SCOPE_write")
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
}

@Bean
@Order(2)
SecurityWebFilterChain webChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/login", "/error").permitAll()
                    .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .csrf(csrf -> csrf.csrfTokenRepository(
                    new WebSessionServerCsrfTokenRepository()))
            .build();
}
~~~

Đây là hai method trong cùng @Configuration, imports và bean xác thực sẽ được trình bày ở project chạy được phía dưới.

Từng API request phải mang Bearer token đã được xác minh; cookie của web session không phải fallback authentication tại /api/**. Chain web giữ CSRF enabled theo mô hình browser login.

### 8.3. Sự khác nhau giữa securityMatcher và pathMatchers

- securityMatcher chọn **toàn bộ SecurityWebFilterChain** áp dụng cho request.
- authorizeExchange().pathMatchers quyết định **quyền** bên trong chain đã được chọn.

Nếu chỉ đặt permitAll hoặc authenticated bằng pathMatchers trong một chain nhưng disable CSRF ở cấp chain, cấu hình CSRF vẫn áp dụng cho phạm vi chain đó. Vì vậy tách đúng securityMatcher là quan trọng.

### 8.4. NoOpSecurityContext không phải chính sách CSRF

NoOpServerSecurityContextRepository không save/load SecurityContext. Nó không thay thế CSRF filter và cũng không có nghĩa mọi request không bao giờ tạo WebSession.

Trong bearer-only API, mục tiêu là tránh session-based authentication và credential fallback. Khi áp dụng no-op repository, cần kiểm tra cả các filter/handler khác có tạo session hay không.

## 9. Demo chạy được Java 17+ / Spring Boot 3.5.16

Ví dụ minh họa hai security boundaries trong **cùng một WebFlux application**:

1. /web/** dùng form login + WebSession và CSRF bắt buộc khi POST.
2. /api/** chỉ dùng Bearer token qua Authorization header; CSRF disabled cho chain này.
3. Token bearer demo chỉ hợp lệ khi ứng dụng chạy bằng profile "demo", tuyệt đối không dùng introspector cố định trong production.
4. Test dùng WebTestClient + spring-security-test để mô phỏng user và CSRF, đồng thời kiểm tra Bearer request thật đi qua resource server chain.

Project sử dụng opaque token introspection interface để giữ ví dụ offline, không cần Identity Provider khi chạy tests. Trong production, thay token verifier demo bằng Authorization Server introspection endpoint hoặc JWT validation chính thức.

### 9.1. Cấu trúc thư mục

~~~text
webflux-csrf-session-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/security/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── BrowserController.java
    │   │   └── ApiController.java
    │   └── resources/application.yml
    └── test/java/example/security/
        └── SecurityIntegrationTest.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-csrf-session-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.3. DemoApplication.java

~~~java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 9.4. SecurityConfig.java

~~~java
package example.security;

import java.util.List;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher("/api/**"))
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.POST, "/api/commands")
                        .hasAuthority("SCOPE_write")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain webChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/login", "/error").permitAll()
                        .anyExchange().authenticated())
                .formLogin(Customizer.withDefaults())
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .csrf(csrf -> csrf.csrfTokenRepository(
                        new WebSessionServerCsrfTokenRepository()))
                .build();
    }

    // Chỉ phục vụ demo; không dùng password và in-memory user này ở production.
    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails demo = User.withUsername("student")
                .password("{noop}demo-pass")
                .roles("USER")
                .build();

        return new MapReactiveUserDetailsService(demo);
    }

    // Chỉ có khi profile demo được bật. KHÔNG deploy demo profile.
    @Bean
    @Profile("demo")
    ReactiveOpaqueTokenIntrospector demoTokenIntrospector() {
        return token -> {
            if (!"demo-token".equals(token)) {
                return Mono.error(
                        new BadOpaqueTokenException("Invalid demo token"));
            }

            return Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
                    "demo-service",
                    Map.of("sub", "demo-service"),
                    List.of(new SimpleGrantedAuthority("SCOPE_write"))));
        };
    }
}
~~~

**Phân tích:**

- @Order(1) giúp chain /api/** được xét trước.
- API chain vô hiệu form login và HTTP Basic, chỉ dùng OAuth2 Resource Server opaque bearer.
- NoOpServerSecurityContextRepository tránh lưu/tải SecurityContext qua session repository cho API.
- .csrf(disable) chỉ áp dụng cho API chain đó.
- webChain bảo vệ tất cả path còn lại bằng form login và WebSessionServerCsrfTokenRepository.
- Noop password encoder và demo-token là dữ liệu kiểm thử, **không phải cơ chế bảo mật chấp nhận được ở production**.
- Nếu không chạy profile demo và cũng không có cấu hình OAuth2 introspection production hợp lệ, ứng dụng cần được cấu hình thêm cho resource server; không tự động chấp nhận token không được kiểm tra.

### 9.5. BrowserController.java

~~~java
package example.security;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class BrowserController {

    public record PreferenceRequest(String theme) {
    }

    public record SavedPreference(boolean saved, String theme) {
    }

    public record CsrfView(String headerName, String token) {
    }

    @GetMapping("/web/ping")
    public Mono<String> ping() {
        return Mono.just("web-session-ok");
    }

    @GetMapping("/web/csrf")
    public Mono<CsrfView> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> csrf =
                exchange.getAttribute(CsrfToken.class.getName());

        if (csrf == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF token unavailable"));
        }

        return csrf.map(token -> new CsrfView(
                token.getHeaderName(), token.getToken()));
    }

    @PostMapping(
            path = "/web/preferences",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<SavedPreference> save(
            @RequestBody PreferenceRequest request) {
        return Mono.just(new SavedPreference(true, request.theme()));
    }
}
~~~

/web/csrf là endpoint đọc token dành cho ứng dụng browser đã đăng nhập. Trong một ứng dụng thực tế, cần bảo đảm token không được cache công khai hoặc xuất hiện trong logs, và cần CSRF token mới khi phiên đăng nhập thay đổi.

### 9.6. ApiController.java

~~~java
package example.security;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    public record CommandRequest(String action) {
    }

    public record CommandResult(boolean accepted, String action) {
    }

    @PostMapping(
            path = "/api/commands",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<CommandResult> command(
            @RequestBody CommandRequest request) {
        return Mono.just(new CommandResult(true, request.action()));
    }
}
~~~

API không tự đọc session cookie. Quyền SCOPE_write được kiểm tra ở resource server security chain trước khi controller nhận request.

### 9.7. application.yml

~~~yaml
spring:
  application:
    name: webflux-csrf-session-demo
  webflux:
    base-path: ""
~~~

Profile demo không tự kích hoạt. Muốn chạy môi trường học tập, phải chủ động bật profile demo. Điều này tránh vô tình dùng verifier "demo-token" trong môi trường không được phép.

### 9.8. SecurityIntegrationTest.java

~~~java
package example.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

@SpringBootTest
@ActiveProfiles("demo")
class SecurityIntegrationTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        this.client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void webPostWithoutCsrfIsForbiddenEvenWhenAuthenticated() {
        client.mutateWith(mockUser("student"))
                .post()
                .uri("/web/preferences")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new BrowserController.PreferenceRequest("dark"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void webPostWithCsrfIsAccepted() {
        client.mutateWith(mockUser("student"))
                .mutateWith(csrf())
                .post()
                .uri("/web/preferences")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new BrowserController.PreferenceRequest("dark"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.saved").isEqualTo(true)
                .jsonPath("$.theme").isEqualTo("dark");
    }

    @Test
    void authenticatedGetDoesNotRequireCsrf() {
        client.mutateWith(mockUser("student"))
                .get()
                .uri("/web/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("web-session-ok");
    }

    @Test
    void csrfEndpointExposesTokenForSameOriginClient() {
        client.mutateWith(mockUser("student"))
                .get()
                .uri("/web/csrf")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.headerName").isEqualTo("X-CSRF-TOKEN")
                .jsonPath("$.token").isNotEmpty();
    }

    @Test
    void bearerApiRequiresAuthentication() {
        client.post()
                .uri("/api/commands")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiController.CommandRequest("sync"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void bearerApiPostSucceedsWithoutCsrfForValidBearer() {
        client.post()
                .uri("/api/commands")
                .header(HttpHeaders.AUTHORIZATION, "Bearer demo-token")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiController.CommandRequest("sync"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.accepted").isEqualTo(true)
                .jsonPath("$.action").isEqualTo("sync");
    }

    @Test
    void bearerApiRejectsInvalidToken() {
        client.post()
                .uri("/api/commands")
                .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-token")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiController.CommandRequest("sync"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
~~~

WebTestClient được bind vào ApplicationContext và apply(springSecurity()) nên có thể dùng mockUser() cùng csrf(). Test mockUser chứng minh authorization + CSRF behavior của chain, **không** phải integration test đầy đủ của browser session cookie sau form login. Bearer request đi qua resource-server filter với demo introspector. Không suy luận từ test này rằng production token verification đã an toàn.

### 9.9. Chạy tests và ứng dụng

Trong thư mục chứa pom.xml:

~~~bash
mvn test
~~~

Để khởi động demo với profile có token cố định:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=demo
~~~

Gọi bearer API (chỉ dùng token này trong môi trường demo):

~~~bash
curl -i -X POST http://localhost:8080/api/commands \
  -H "Authorization: Bearer demo-token" \
  -H "Content-Type: application/json" \
  -d '{"action":"sync"}'
~~~

Response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"accepted":true,"action":"sync"}
~~~

Nếu bỏ Bearer header, API trả 401 Unauthorized. Nếu gọi /web/preferences mà không có login session hợp lệ và CSRF token, request không được chấp nhận. Browser truy cập /login để dùng form login được Spring Security tạo.

Muốn thao tác browser session thật bằng JavaScript, đăng nhập qua form trước rồi gọi /web/csrf và dùng token nhận được trong header cho POST /web/preferences.

### 9.10. Thay demo token verifier bằng hệ thống thật

Production không được giữ demo profile, user password noop hoặc introspector cố định.

Ví dụ resource server opaque token gọi Authorization Server introspection:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example/introspect
          client-id: my-resource-server
          client-secret: from-secure-config
~~~

Ở production, giá trị client-secret phải đến từ secret manager hoặc biến môi trường an toàn, không commit secret vào repository. Khi không có bean ReactiveOpaqueTokenIntrospector demo, Spring Boot có thể tạo introspector từ các properties này.

Nếu dùng JWT, thay opaqueToken configuration bằng jwt() và cung cấp issuer-uri hoặc JWK Set URI phù hợp. Validator phải kiểm tra signature, issuer, audience, expiry và các claim/quyền cần thiết; không chấp nhận token chỉ vì decode được JSON.

## 10. Trạng thái và session trong những kiểu login khác nhau

### 10.1. Form login

Với form login:

1. Browser GET /login để nhận form, có CSRF token.
2. Browser POST username/password cùng CSRF token.
3. Spring Security xác thực; SecurityContext được lưu theo cấu hình session.
4. Browser gửi session cookie trong các request tiếp theo.
5. GET đọc dữ liệu thường không cần CSRF.
6. POST/PUT/PATCH/DELETE mang cookie phải có CSRF token hợp lệ.
7. Logout nên là POST được bảo vệ CSRF, không phải GET làm thay đổi trạng thái.

Chống login CSRF cũng quan trọng: một request login giả mạo có thể đưa browser của nạn nhân vào một tài khoản do attacker kiểm soát. Spring Security bảo vệ POST login bằng CSRF trong cấu hình phù hợp.

### 10.2. OAuth2 Login/OIDC

OAuth2 Authorization Code flow có tham số state để bảo vệ luồng callback authorization, cùng PKCE và nonce theo loại flow. Các cơ chế này không thay thế CSRF protection của những POST nghiệp vụ sau khi người dùng đã login.

WebFlux OAuth2 Login thường có trạng thái phiên được quản lý qua request/session tùy config. Nếu browser dùng cookie để giữ login, các unsafe actions vẫn phải được bảo vệ.

### 10.3. Stateless bearer resource server

Resource server xác thực mỗi request từ bearer token do client chủ động gửi. Không cần lưu SecurityContext vào WebSession để nhớ login. Tuy nhiên:

- Token hết hạn, bị thu hồi hoặc sai audience vẫn phải bị từ chối.
- Cần authorization dựa trên scope/role/claim.
- CORS cần giới hạn origin được phép truy cập.
- Nếu token ở JavaScript storage, XSS có thể đánh cắp token.
- Một API hỗ trợ bearer lẫn session fallback phải được đánh giá như endpoint có cookie, không mặc nhiên CSRF-safe.

### 10.4. Hybrid: BFF, SPA và backend API

Một kiến trúc thường gặp:

~~~text
Browser
  |
  | Cookie SESSION + CSRF header
  v
BFF / WebFlux app
  |
  | Authorization: Bearer explicit header
  v
Downstream Resource API
~~~

Browser → BFF cần CSRF vì cookie tự gửi. BFF → downstream API không phải một form/browser ambient request; xác thực Bearer riêng và kiểm tra token phù hợp. Ranh giới này giải thích vì sao cùng một hệ thống có thể bật CSRF ở frontend-facing chain và tắt ở machine-facing chain mà không mâu thuẫn.

## 11. Phân biệt lỗi 401, 403 và lỗi CSRF

| Tình huống | Kết quả thường gặp | Diễn giải |
| --- | --- | --- |
| API bearer không có token | 401 Unauthorized | Chưa authenticated |
| API bearer token sai/hết hạn | 401 Unauthorized | Authentication thất bại |
| API bearer token hợp lệ nhưng thiếu scope | 403 Forbidden | Không được phép thực hiện thao tác |
| Web session đã authenticated, POST thiếu/sai CSRF | 403 Forbidden | CSRF protection từ chối |
| Web page chưa login | 302 về login hoặc behavior do entry point cấu hình | Cần interactive authentication |
| Session hết hạn và token CSRF cũ | Có thể 403 CSRF hoặc redirect/login tùy flow | Lấy token/session mới đúng quy trình |

Không nên xây client chỉ dựa trên status 403 để kết luận chắc chắn lỗi CSRF. 403 cũng có thể do authorization. Quan sát exception/log và error contract đã chuẩn hóa của ứng dụng.

Không trả CSRF token, credential, cookie hoặc stack trace trong error message. Tránh log nguyên HTTP headers có Authorization.

## 12. Chọn CSRF token repository nào?

| Repository | Lưu token | Khi phù hợp | Cần lưu ý |
| --- | --- | --- | --- |
| WebSessionServerCsrfTokenRepository | Expected token ở WebSession | Browser server-rendered, form login, BFF có session | Có session state; cần session store/cookie policy đúng |
| CookieServerCsrfTokenRepository | Token ở cookie | SPA đọc token cookie và gửi lại header | HttpOnly false chỉ khi cần; masking/XOR handler, XSS/CORS |
| Custom ServerCsrfTokenRepository | Theo cơ chế ứng dụng | Yêu cầu store riêng | Phải bảo toàn khả năng kiểm tra token và lifecycle |

Nếu không có lý do đặc biệt, ưu tiên mặc định WebSessionServerCsrfTokenRepository cho browser session. Không chọn Cookie repository chỉ để "tránh session" trong khi authentication vẫn dùng cookie/session và chưa có kế hoạch quản lý token an toàn.

Một số SPA dùng double-submit cookie pattern. Đừng hiểu nhầm rằng "cookie có token" đã đủ; server phải kiểm tra token được trình bày bằng header/parameter hợp lệ, không tự coi cookie đó là bằng chứng.

## 13. Cookie policy, CORS và session store

### 13.1. Cookie

Trong production, nên kiểm tra:

- Secure: chỉ gửi cookie qua HTTPS.
- HttpOnly: JavaScript không đọc session cookie trực tiếp.
- SameSite: chọn Lax/Strict/None phù hợp với OAuth redirect, iframe, cross-site use case.
- Path và Domain: không mở phạm vi rộng hơn cần.
- Cookie name và session expiry.
- Session ID rotation/invalidation sau login/logout theo chính sách.
- Reverse proxy có chuyển đúng scheme HTTPS để app thiết lập cookie Secure hay không.

### 13.2. CORS

Với SPA khác origin gọi API sử dụng cookie:

- Cho phép origin cụ thể, không wildcard khi allow credentials.
- Chỉ cho phép method/header thực sự cần.
- Dùng HTTPS và policy credentials rõ ràng.
- Vẫn cần CSRF nếu browser auto-send cookie cho unsafe operations.
- Không mở endpoint phát CSRF token cho mọi origin hoặc cache public.

Với Bearer API, CORS phải phản ánh frontend được phép gọi API; "CSRF disabled" không đồng nghĩa CORS wildcard là an toàn.

### 13.3. Session trong hệ thống nhiều node

Nếu dùng WebSession mặc định và chạy nhiều instances, session không tự động chia sẻ giữa mọi instance. Với yêu cầu horizontal scaling và không muốn sticky-session dependence, có thể dùng Spring Session với Redis. Cần bảo vệ Redis và dữ liệu session, cấu hình TTL, failover và xử lý logout/session invalidation.

Nếu browser lưu phiên qua cookie ở domain của BFF, đừng chia sẻ session cookie không cần thiết sang mọi microservice; giới hạn domain/path và trust boundary.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| "Dùng JWT nên tắt CSRF" | JWT trong cookie vẫn auto-send | Xem credential được truyền bằng cookie hay explicit header |
| "Stateless nên không cần CSRF" | Stateless cookie authentication vẫn bị CSRF | Đánh giá ambient credentials |
| Disable CSRF cho toàn ứng dụng vì có một REST API | Form/session endpoints mất bảo vệ | Tách SecurityWebFilterChain theo securityMatcher |
| Cho /api/** fallback vào session cookie | Cookie có thể authenticate API khi CSRF đã tắt | Bearer-only chain, no session/basic fallback |
| Nghĩ NoOpServerSecurityContextRepository tắt mọi WebSession | Component khác vẫn có thể tạo session | Kiểm tra toàn authentication/session flow |
| Dùng HTTP Basic trên browser và mặc định bỏ CSRF | Browser có thể tự gửi Basic credential | Đánh giá như ambient auth nếu phù hợp |
| Nghĩ CORS thay CSRF | Form/request đơn giản vẫn có thể gây side effect | Dùng CSRF token cho cookie-backed unsafe endpoints |
| Xử lý thay đổi dữ liệu qua GET | Bỏ qua bảo vệ unsafe method | Chuyển sang POST/PUT/PATCH/DELETE |
| Chỉ kiểm tra cookie XSRF-TOKEN | Browser tự gửi cookie | Yêu cầu token ở header/parameter và verify |
| SPA copy raw cookie token nhưng quên XOR handler | Có thể nhận 403 dù có token | Cấu hình SPA CSRF đúng phiên bản và test |
| Trả CSRF token qua endpoint public/cross-origin | Lộ khả năng tạo request hợp lệ | Auth + same-origin policy + no public cache |
| Log Authorization, session cookie hoặc CSRF token | Lộ credential | Redact/sanitize logs |
| Quên CSRF ở login/logout | Login/logout CSRF | Bảo vệ POST login và logout |
| Dùng SameSite như phòng vệ duy nhất | Vẫn còn cấu hình/flow rủi ro | CSRF token và các lớp bảo vệ khác |
| Một chain catch-all đứng trước chain API | API nhận nhầm formLogin/csrf policy | @Order và securityMatcher rõ ràng |
| Không test không token/có token | Lỗ hổng hoặc 403 production | Test WebTestClient + spring-security-test |
| Giữ demo introspector ở production | Mọi request dùng token cố định có thể được chấp nhận | Demo profile duy nhất; dùng IdP production |
| Dùng JWT decode mà không verify | Chấp nhận token giả mạo | Kiểm tra cryptographic signature, issuer, audience, exp |

## 15. Checklist review bảo mật

Trước khi quyết định bật/tắt CSRF cho một endpoint hoặc nhóm endpoint:

1. Client là browser, mobile app hay service-to-service?
2. Credential nằm trong session cookie, JWT cookie, Authorization header, Basic auth hay mTLS?
3. Browser có tự động thêm credential vào cross-site request không?
4. API có bao giờ chấp nhận session hoặc cookie fallback không?
5. Unsafe HTTP methods có được dùng đúng cho mọi state changes không?
6. Chain chọn bằng securityMatcher có đúng thứ tự không?
7. CSRF repository và request handler có khớp cách frontend gửi token không?
8. Token được lấy/đọc chỉ bởi origin được tin cậy và không bị public cache/log?
9. Session cookie có Secure, HttpOnly, SameSite, path/domain hợp lý không?
10. OAuth2 login có state/nonce/PKCE phù hợp và vẫn bảo vệ POST nghiệp vụ không?
11. Bearer resource server có verify token, scope và authorization không?
12. API JWT-in-cookie đã bật CSRF dù token stateless chưa?
13. SPA có xử lý CSRF token rotation và session expiry không?
14. CORS có explicit trusted origins và không mở credentials rộng không?
15. Security integration tests bao phủ 401, 403, POST thiếu token và POST hợp lệ không?
16. Có kiểm tra session fixation, logout, invalidation và Redis/session store khi chạy nhiều instance không?

## 16. Ghi nhớ

- **CSRF không phụ thuộc đơn giản vào "JWT hay Session".** Nó phụ thuộc browser có tự động gửi credential hay không.
- Form login, OAuth2 login hoặc BFF dùng session cookie cần CSRF protection cho unsafe requests.
- JWT/opaque bearer trong Authorization header do client gắn chủ động thường cho phép disable CSRF ở đúng bearer-only API chain.
- JWT trong cookie vẫn chịu CSRF. HTTP Basic trong browser có thể là ambient credential.
- WebFlux dùng WebSession và WebSessionServerCsrfTokenRepository; Spring Security bật CSRF mặc định.
- CsrfWebFilter đưa Mono<CsrfToken> vào ServerWebExchange; có thể render token trong form hoặc trả token qua endpoint cùng origin.
- Spring Security 6 dùng XorServerCsrfTokenRequestAttributeHandler mặc định; SPA cookie token có thể cần request-handler phù hợp.
- NoOpServerSecurityContextRepository không bảo đảm toàn bộ ứng dụng hoàn toàn stateless.
- Multiple SecurityWebFilterChain với @Order và securityMatcher giúp giữ session+CSRF cho web UI, bearer-only cho /api/**.
- SameSite, HttpOnly, Secure, CORS, CSP và XSS prevention là phòng vệ bổ sung, không thay token CSRF khi cần.
- Test cả cookie-backed POST thiếu token (403), có token (2xx), bearer API thiếu token (401), token hợp lệ (2xx).
- Chỉ disable CSRF sau khi đã xác nhận không còn authentication tự động từ browser trên phạm vi endpoint đó.

**Tài liệu chính thức:**
- [Spring Security 6.5 — CSRF trong WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — WebFlux Security, multiple SecurityWebFilterChain](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — CSRF cơ chế tấn công và phòng vệ](https://docs.spring.io/spring-security/reference/6.5/features/exploits/csrf.html)
- [Spring Security 6.5 — Opaque token resource server cho WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security 6.5 — Testing with CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html)
- [Spring Security 6.5 — Testing authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Framework — WebSession và WebFlux session handling](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html)
