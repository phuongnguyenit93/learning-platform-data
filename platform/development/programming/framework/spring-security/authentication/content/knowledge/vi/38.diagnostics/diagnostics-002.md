# ProviderManager chọn sai provider hoặc cơ chế xác thực không chạy: quy trình chẩn đoán Spring Security

## 1. Mục tiêu và cách nhìn vấn đề

Khi Spring Security không đăng nhập như mong đợi, thông báo như **“ProviderManager chọn sai provider”**, **“AuthenticationProvider của tôi không được gọi”**, **“form login không chạy”**, **“JWT hợp lệ nhưng request vẫn 401”** hoặc **“POST /login trả 404/403”** thường bị quy cho cùng một lỗi. Trên thực tế, yêu cầu HTTP phải vượt qua nhiều tầng trước khi đến `ProviderManager`.

Bài này thuộc nhóm **Chẩn đoán** của module **Spring Security - authentication**. Trọng tâm không phải xây thêm một cơ chế xác thực mới, mà là **xác định chính xác tầng nào không được thực thi, vì sao và cách chứng minh đã sửa đúng**.

Kết thúc bài, bạn có thể:

1. Phân biệt **không chọn SecurityFilterChain**, **chain không có authentication filter**, **filter không match request**, **filter tạo sai Authentication token**, **provider không supports**, **provider trả null/exception**, **parent manager fallback**, và **authentication có nhưng context/session không được lưu**.
2. Đọc startup logs/TRACE và inspect `FilterChainProxy` để biết **request đã chọn chain nào, filters nào đang hiện diện**.
3. Phân biệt `http.securityMatcher(...)`, `authorizeHttpRequests(...).requestMatchers(...)` và matcher của **authentication filter**.
4. Chẩn đoán cụ thể form login, HTTP Basic, Bearer JWT/opaque, OIDC login, remember-me và custom filter.
5. Hiểu quy tắc **first-success-wins** trong `ProviderManager`, exception precedence và ý nghĩa của parent `AuthenticationManager`.
6. Tránh các “cách sửa” nguy hiểm như tắt CSRF toàn ứng dụng, `permitAll()` toàn bộ, chuyển sang password encoder `{noop}`, bỏ signature verification hoặc thêm fallback provider yếu hơn.
7. Dựng một cấu hình Servlet minh bạch, viết **MockMvc HTTP test** và **JUnit/Mockito ProviderManager test** để bắt lỗi hồi quy.
8. Phân biệt **Servlet `HttpSecurity`** với **WebFlux `ServerHttpSecurity`** để không tìm nhầm provider/filter.

**Baseline:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x **Servlet stack**. Các cấu hình có thể thay đổi khi lên Spring Security 7.x; hãy đối chiếu tài liệu đúng artifact/version. Ví dụ về token, password và URL chỉ dành cho môi trường local/test.

## 2. Câu hỏi đầu tiên: request đã đến ProviderManager chưa?

Trước khi sửa một bean `AuthenticationProvider`, hãy vẽ hành trình thực sự:

```text
HTTP request
   |
   v
Servlet container -> DelegatingFilterProxy
   |
   v
springSecurityFilterChain (FilterChainProxy)
   |
   +-- Select FIRST matching SecurityFilterChain by request matcher/order
   |       |
   |       +-- no chain matched? Spring Security may not protect the request
   |       |
   |       v
   |    Chain's security filters
   |       |
   |       +-- CsrfFilter / CORS / logout / custom filters may stop early
   |       |
   |       v
   |    Authentication filter present?
   |       |
   |       +-- no: nothing invokes an AuthenticationManager for this flow
   |       |
   |       +-- yes, but its RequestMatcher doesn't match:
   |       |        authentication filter skips request
   |       |
   |       v
   |    Build unauthenticated Authentication token (concrete Java class)
   |       |
   |       v
   |    AuthenticationManager.authenticate(token)
   |       |
   |       v
   |    ProviderManager: provider.supports(token.getClass())
   |       |
   |       +-- skips, null, exception, success
   |       +-- optional parent fallback
   |       |
   |       v
   |    Authenticated Authentication result
   |       |
   |       v
   |    Filter stores SecurityContext / saves if required
   |       |
   |       v
   +-- AuthorizationFilter / controller / response
```

**Nếu filter chưa match, ProviderManager không thể “chọn sai provider”** vì nó còn chưa được gọi. Nếu provider đã trả authenticated result nhưng request sau vẫn anonymous, lỗi có thể nằm ở **SecurityContextRepository/session**, không phải `supports`.

### 2.1. Bảng khoanh vùng trong 60 giây

| Triệu chứng | Tầng nghi ngờ trước | Bằng chứng cần thu |
| --- | --- | --- |
| `GET /api/me` trả 200 dù anonymous | Chain coverage / `permitAll` | Chain nào match; authorization rules có yêu cầu auth không |
| `POST /login` trả 404 | Sai processing URL, method hoặc chain | Login filter có mặt? Path/method trùng filter matcher? Có controller trùng path không |
| `POST /login` trả 403 trước khi tra user | CSRF / upstream filter | Log `CsrfFilter`; CSRF token có hợp lệ không |
| Không hề có log provider | Filter/matcher/manager wiring | TRACE filter chain; breakpoint ở filter và manager |
| `ProviderNotFoundException` | Token class vs `supports`, thiếu provider | In **class name** của request authentication; kiểm danh sách providers |
| Username/password đúng vẫn `BadCredentials` | DAO/encoder/realm or another provider | Provider nào nhận token; user source; password encoder; fallback |
| JWT có `Authorization: Bearer ...` nhưng 401 | Bearer filter/token decoder/issuer | Đúng chain? BearerTokenAuthenticationFilter? Decoder/introspection error |
| Login trả 302 nhưng request sau anonymous | Context persistence/cookie/session | SecurityContextRepository, cookie jar, session policy |
| Browser được redirect tới login khi API gọi | Entry point / selected chain | Response ban đầu 302 hay client follow redirect; API chain có auth mechanism nào |
| User đúng nhưng 403 | Authorization khác Authentication | `Authentication` đã tồn tại? Authorities/roles/scopes là gì |
| Custom filter bị gọi hai lần | Servlet auto-registration ngoài Spring Security | Filter bean có đăng ký cả container và security chain không |
| Test `with(user("alice"))` pass nhưng login thật fail | Test đang bypass authentication | Thử `formLogin()`/HTTP Basic/JWT route thật |

Đừng suy nguyên nhân chỉ từ HTTP status. **Một 401/403/302 có thể được tạo ở nhiều lớp khác nhau**.

## 3. Dụng cụ thu thập bằng chứng an toàn

Trước tiên tạo một HTTP request **có thể tái hiện**, giữ nguyên URL, method, headers (không chứa secret trong báo cáo), body type, cookies/session và correlation ID. Ví dụ:

```bash
# Không tự follow redirect: nhìn status và Location ban đầu.
curl -i -H 'Accept: text/html' http://localhost:8080/private

# Basic: username/password demo local, không dùng với mạng production không TLS.
curl -i -u alice:demo-password http://localhost:8080/api/me

# Chỉ kiểm tra form-login route GET.
curl -i http://localhost:8080/login
```

Với Bearer token, tránh đưa raw token trong shell history hoặc CI logs. Dùng HTTP client được quản lý secrets hoặc biến môi trường an toàn; nếu cần debug, ghi “Bearer header present, token length X, issuer Y” thay vì toàn bộ token.

### 3.1. Bật Spring Security logs trong môi trường test

Trong `application-local.yml` hoặc config test:

```yaml
logging:
  level:
    org.springframework.security: TRACE
```

Hoặc `application.properties`:

```properties
logging.level.org.springframework.security=TRACE
```

TRACE có thể hiển thị **mỗi filter được gọi**; DEBUG ở lúc khởi động thường liệt kê filter chain. Đây là bằng chứng hữu ích để phân biệt “filter không tồn tại” với “filter có nhưng không match request”. **Chỉ bật trong môi trường kiểm soát và tắt sau khi chẩn đoán**, vì logs có thể chứa thông tin request/identity và làm lộ dữ liệu không cần thiết.

Trong logs, tìm theo thứ tự:

1. `DefaultSecurityFilterChain : Will secure ... with [...]` khi app khởi động.
2. `FilterChainProxy : Securing POST /login` và `Invoking ...Filter` cho request gây lỗi.
3. `CsrfFilter` hoặc filter trước authentication có chặn không.
4. `UsernamePasswordAuthenticationFilter`, `BasicAuthenticationFilter`, `BearerTokenAuthenticationFilter`, `OAuth2LoginAuthenticationFilter` hoặc custom filter có mặt và thực sự chạy không.
5. Dấu vết `ProviderManager`/`AuthenticationProvider`/`DaoAuthenticationProvider`, loại exception và failure handler.
6. `AuthorizationFilter`/`ExceptionTranslationFilter` chọn redirect/401/403 thế nào.

**Lưu ý:** log nói filter được invoke không đồng nghĩa filter **thực hiện authentication**. Filter có thể chạy `doFilter` nhưng bỏ qua vì request matcher không phù hợp hoặc không có credential.

### 3.2. Debug có chọn lọc, không log credential

Không đặt:

```java
// ANTI-PATTERN: không log raw password/access token/cookie.
log.debug("authentication=" + authentication);
log.debug("password=" + request.getParameter("password"));
log.debug("Authorization=" + request.getHeader("Authorization"));
```

Thay bằng metadata không nhạy cảm: `authentication.getClass().getName()`, tên provider, thứ tự provider, matcher result, correlation ID, issuer đã xác minh, error code. Không ghi password, raw token, session ID, cookie, private key hoặc nguyên văn login assertions.

## 4. SecurityFilterChain: lỗi đầu tiên hay bị bỏ qua

Một ứng dụng có thể khai báo nhiều `SecurityFilterChain`:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(a -> a
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(a -> a
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Đoạn trên là **trích đoạn cấu hình**; import, datasource/user provider và chính sách CSRF/session chưa được biểu diễn. Điểm cốt lõi: `FilterChainProxy` thử chains theo `@Order` và **chỉ dùng chain đầu tiên match**. Nó không ghép filters của API chain với web chain.

### 4.1. `securityMatcher` khác `requestMatchers`

| DSL | Quyết định | Hậu quả khi cấu hình sai |
| --- | --- | --- |
| `http.securityMatcher("/api/**")` | **Chain này có áp dụng cho request hay không?** | Request không vào chain; filters bên trong không chạy |
| `authorizeHttpRequests(a -> a.requestMatchers(...))` | **Trong chain đã chọn**, URL cần quyền gì? | Có thể cho/không cho truy cập sai, nhưng không thêm authentication filter |
| `formLogin().loginProcessingUrl("/auth")` | Form-login filter nhận **POST endpoint nào** | POST sai path sẽ bỏ qua filter |
| `httpBasic()` | Thêm Basic auth mechanism vào chain | Không có BasicAuthenticationFilter nếu chưa cấu hình cơ chế tương ứng |
| `oauth2ResourceServer().jwt()` | Thêm Bearer token resource-server flow | Không tự biến một form login thành JWT resource server |
| `@Order` | Thứ tự ưu tiên chains | Chain catch-all đứng trước nuốt mọi request của chain hẹp |

**Bug 1 — Catch-all đứng trước:**

```java
// SAI: nếu chain này được ưu tiên cao nhất, /api/** có thể bị
// xử lý theo web form login, không phải API Basic/Bearer.
@Bean
@Order(1)
SecurityFilterChain everything(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Sửa bằng việc đặt chain chuyên biệt `/api/**` trước và chain catch-all cuối. Không chỉ đổi `401`/`302`: **cần chắc chắn đúng authentication filter** đã được gắn vào chain.

**Bug 2 — Chain coverage bị hở:**

```java
// CẢNH BÁO: chỉ bảo vệ /api/**; mọi path khác không match
// bất kỳ chain nào nếu không có chain catch-all.
http.securityMatcher("/api/**");
```

Nếu không có filter chain nào match một request, request đó có thể **không được Spring Security bảo vệ**. Đừng sửa bằng `permitAll()` mọi URL; hãy định nghĩa chain catch-all rõ ràng và kiểm tra endpoint coverage.

### 4.2. Cần xét context path, servlet mapping và proxy

Các path `/api`, `/api/`, `/api/items`, `/apiary` và `/myapp/api/items` có thể được Spring nhìn khác nhau tùy `server.servlet.context-path`, Servlet registration, proxy rewriting và matcher implementation. Kiểm tra **đúng request nhìn từ Servlet**; đừng ghép raw `requestURI` bằng phép `startsWith("/api")` vì dễ match nhầm `/apiary`.

Nếu Spring MVC có nhiều Servlet, chọn matcher tương thích với mapping; Spring Security 6.5 hỗ trợ lựa chọn request matcher tùy các thành phần hiện diện, Spring Security 7 có API path-pattern phù hợp hơn. Thử với cả trailing slash, URL encoded characters, forwarded prefixes và method POST.

## 5. Chain đúng nhưng authentication filter không có

`ProviderManager` thường không tự theo dõi mọi HTTP request. **Một authentication filter phải nhận credential và gọi manager**. Trong Spring Security Servlet:

| Mechanism | Filter tiêu biểu | Cách bật thường gặp |
| --- | --- | --- |
| Form username/password | `UsernamePasswordAuthenticationFilter` | `http.formLogin(...)` |
| HTTP Basic | `BasicAuthenticationFilter` | `http.httpBasic(...)` |
| OAuth Bearer JWT/opaque | `BearerTokenAuthenticationFilter` | `http.oauth2ResourceServer(...)` |
| OAuth2 login/OIDC | `OAuth2LoginAuthenticationFilter` | `http.oauth2Login(...)` |
| Remember-me | `RememberMeAuthenticationFilter` | `http.rememberMe(...)` |
| X.509 client certificate | `X509AuthenticationFilter` | `http.x509(...)` |
| Custom API key | Filter do ứng dụng thêm | `http.addFilterBefore/After(...)` ở vị trí phù hợp |

Việc có `AuthenticationProvider` bean **không tự tạo ra filter** tương ứng. Một provider biết xác thực `ApiKeyAuthenticationToken` là vô dụng nếu chưa có filter lấy API key từ request, tạo token đúng loại và gọi manager.

Ngược lại, có filter nhưng nó không liên kết với manager chứa provider bạn mong muốn cũng gây lỗi. Do đó cần chứng minh **cả filter presence và manager/provider wiring**.

### 5.1. Khi tạo SecurityFilterChain thủ công, đừng ngầm chờ form login tự xuất hiện

Nếu đã tự khai báo `SecurityFilterChain` bean, hãy bật các cơ chế mong muốn một cách tường minh:

```java
http
    .authorizeHttpRequests(a -> a.anyRequest().authenticated())
    .formLogin(Customizer.withDefaults())
    .httpBasic(Customizer.withDefaults());
```

Đây là **trích đoạn**, không phải khuyến nghị bắt buộc bật cả hai cho mọi endpoint. Đối với API stateless JWT, không nên vô tình bật form login với session; đối với web browser, không nên kỳ vọng bearer filter xuất hiện chỉ vì thêm dependency `spring-security-oauth2-resource-server`.

### 5.2. Custom filter bị bỏ qua

Nếu custom filter viết `shouldNotFilter(...)`, tự kiểm tra path, hoặc có `RequestMatcher` nội bộ, kiểm tra tất cả điều kiện đó. Với `OncePerRequestFilter`, hãy xác minh URL/method/header **đúng** theo request thực tế và filter được thêm vào đúng chain.

Đặt `addFilterBefore(custom, UsernamePasswordAuthenticationFilter.class)` hay `addFilterAfter(custom, LogoutFilter.class)` không đảm bảo nó được gọi ở chain khác hoặc request nằm ngoài `securityMatcher`. Điều quan trọng hơn vị trí là **filter thực sự đang ở chain đã match**, có gọi `chain.doFilter(...)` đúng đường, và không tự nuốt response.

### 5.3. Filter bean chạy hai lần

Nếu custom `Filter` đồng thời được khai báo là Spring bean và thêm vào `HttpSecurity`, Spring Boot có thể tự đăng ký filter vào **Servlet container chain**, khiến nó chạy **hai lần** hoặc thứ tự khác dự kiến. Nếu cần bean cho DI nhưng chỉ muốn chạy trong security chain, vô hiệu auto-registration:

```java
@Bean
FilterRegistrationBean<MyAuthenticationFilter> disableContainerRegistration(
        MyAuthenticationFilter filter) {
    FilterRegistrationBean<MyAuthenticationFilter> bean =
            new FilterRegistrationBean<>(filter);
    bean.setEnabled(false);
    return bean;
}
```

Đây là **trích đoạn**: `MyAuthenticationFilter` phải do project định nghĩa và đã được thêm vào `HttpSecurity`. Không áp dụng mù quáng cho mọi filter của ứng dụng; mục tiêu là tránh đăng ký hai vị trí.

## 6. Authentication filter có mặt nhưng không xử lý request

### 6.1. Form login: `POST /login`, không phải mọi GET/POST

Theo cấu hình form-login mặc định, `UsernamePasswordAuthenticationFilter` xử lý:

```http
POST /login
Content-Type: application/x-www-form-urlencoded

username=alice&password=demo-password&_csrf=<valid-token>
```

Nếu người dùng gọi `GET /login`, đó là yêu cầu **render login page**, không phải submit credential. Nếu frontend submit JSON `POST /login` nhưng backend chỉ có `UsernamePasswordAuthenticationFilter` mặc định, filter thường đọc `request.getParameter("username")`/`password`, **không tự parse JSON body**. Kết quả có thể là credential rỗng, không phải provider “chọn sai”.

Tùy chỉnh URL và field:

```java
http.formLogin(form -> form
        .loginPage("/signin")
        .loginProcessingUrl("/signin/process")
        .usernameParameter("email")
        .passwordParameter("password")
        .permitAll());
```

Khi đó form phải POST **`/signin/process`**, field là `email`, không còn dùng `POST /login`. `GET /signin` phải do controller/template của bạn render; không được mặc định Spring tạo trang custom ấy.

### 6.2. CSRF chặn trước khi login filter gọi manager

Spring Security bảo vệ POST với CSRF theo default Servlet settings. Nếu `POST /login` trả **403** vì thiếu token CSRF, `UsernamePasswordAuthenticationFilter` có thể **chưa hề xác thực**. Chứng cứ là `CsrfFilter` trong TRACE/DEBUG.

Cách sửa đúng: form HTML chứa CSRF token, hoặc test dùng `.with(csrf())`. **Không tắt CSRF toàn ứng dụng chỉ để POST login “chạy”**; với browser cookie-authenticated application, điều đó mở ra rủi ro CSRF cho các thao tác thay đổi trạng thái.

### 6.3. Basic: không có `Authorization: Basic` thì filter có thể đi qua

`BasicAuthenticationFilter` nhận header Basic hợp lệ. Một request không có Basic header có thể đi tới authorization, rồi `ExceptionTranslationFilter` tạo Basic challenge 401. Trong tình huống này **không nhất thiết có lời gọi `ProviderManager`**, vì chưa có credential để xác thực.

Tương tự Bearer: thiếu Bearer token không chứng minh JwtAuthenticationProvider bị lỗi. Trước tiên kiểm tra header và bearer token resolver.

### 6.4. CORS preflight

Browser gửi `OPTIONS` preflight thường không chứa credentials. Nếu CORS/CSRF/authorization chặn preflight, API request thực sẽ không xảy ra. Kết quả giống như “authentication filter không chạy”, nhưng nguyên nhân là **CORS handshake**. Cấu hình CORS ở lớp thích hợp, dùng allowed origins/methods/headers cụ thể; không chuyển API business thành `permitAll` để làm preflight pass.

## 7. Kiểu Authentication token được tạo quyết định provider có thể xử lý

`ProviderManager` nhận một object implement `Authentication`. Mỗi provider có:

```java
boolean supports(Class<?> authentication);
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
```

Provider **không được chọn theo tên bean**, username, URI hay thứ tự `@ComponentScan` một cách ma thuật. Nó được xét theo **thứ tự danh sách providers** và `supports(authentication.getClass())`.

Ví dụ:

| Request token class | Provider thường hỗ trợ |
| --- | --- |
| `UsernamePasswordAuthenticationToken` | `DaoAuthenticationProvider`, custom username/password provider |
| `JwtAuthenticationToken` sau xác thực | Là result JWT, không phải mọi trường hợp input cho `JwtAuthenticationProvider` |
| `BearerTokenAuthenticationToken` ở resource-server JWT pipeline | `JwtAuthenticationProvider`, tùy manager resolver |
| `BearerTokenAuthenticationToken` trong opaque pipeline | `OpaqueTokenAuthenticationProvider` |
| `RememberMeAuthenticationToken` | `RememberMeAuthenticationProvider` |
| `PreAuthenticatedAuthenticationToken` | `PreAuthenticatedAuthenticationProvider` |
| `OAuth2LoginAuthenticationToken` trong oauth2Login flow | Provider hỗ trợ OAuth2 authorization-code login theo configuration |
| Custom `ApiKeyAuthenticationToken` | Custom provider `supports` đúng class |
| `OneTimeTokenAuthenticationToken` | Provider/service One-Time Token khi bật OTT mechanism |

**Cẩn thận với JWT:** `BearerTokenAuthenticationFilter` thường tạo **`BearerTokenAuthenticationToken`** (unauthenticated input), `JwtAuthenticationProvider` trả **`JwtAuthenticationToken`** đã authenticated. Nếu custom provider `supports(JwtAuthenticationToken.class)` rồi mong xử lý raw Bearer input, bạn đã nhầm **kiểu vào** với **kiểu ra**.

### 7.1. `supports` nên kiểm như thế nào?

Với custom token `ApiKeyAuthenticationToken`:

```java
@Override
public boolean supports(Class<?> authentication) {
    return ApiKeyAuthenticationToken.class
            .isAssignableFrom(authentication);
}
```

Đây là **trích đoạn nằm trong custom AuthenticationProvider**; class token tự định nghĩa riêng. `supports=true` chỉ nói provider **có thể xét** loại token đó. `authenticate` vẫn có thể trả `null` khi request không thuộc phạm vi của provider.

Đừng viết:

```java
// SAI cho provider chỉ xử lý API key: nuốt mọi loại token.
@Override
public boolean supports(Class<?> authentication) {
    return true;
}
```

Một provider supports quá rộng và đứng trước có thể ngăn cơ chế khác được dùng hoặc tạo authenticated result sai. Mặt khác, viết `authentication.equals(ApiKeyAuthenticationToken.class)` bỏ qua subclasses khi bạn định hỗ trợ chúng; phải test type hierarchy theo thiết kế.

### 7.2. Đừng tự đặt isAuthenticated=true trong request input

`UsernamePasswordAuthenticationToken.authenticated(...)` hoặc `new ...(..., authorities)` biểu diễn một result đã được xác thực **khi trusted provider tạo**, không phải cách frontend/controller hợp thức hóa credential chưa kiểm chứng.

Một custom filter nên tạo token **unauthenticated**, rồi đưa vào `AuthenticationManager.authenticate(...)`. Nếu controller tự set một principal authenticated mà không xác minh secret, ProviderManager không có cơ hội thực hiện chính sách.

## 8. ProviderManager chọn provider như thế nào?

Quy tắc Spring Security 6.5:

```text
ProviderManager.authenticate(token)
    lastException = null
    for provider in orderedProviders:
        if not provider.supports(token.class): continue
        try:
            result = provider.authenticate(token)
            if result != null: SUCCESS; stop local traversal
            if result == null: continue
        catch AccountStatusException:
            STOP immediately
        catch InternalAuthenticationServiceException:
            STOP immediately
        catch other AuthenticationException ex:
            lastException = ex; continue
    if no local success and parent exists:
        try parent.authenticate(token)
    if success:
        erase credentials if applicable, publish event as configured
    else:
        throw appropriate last exception or ProviderNotFoundException
```

Sơ đồ là **pseudocode học thuật**, không thay thế source code chính xác của từng phiên bản hoặc logic event handling. Điểm quan trọng là **không phải cứ gặp provider `supports=true` là dừng**.

### 8.1. Bảng trạng thái và ý nghĩa debug

| P1 | P2 | Parent | Kết quả/nghiên cứu |
| --- | --- | --- | --- |
| `supports=false` | success | không gọi | P1 không được authenticate, P2 thắng |
| `supports=true`, returns `null` | success | không gọi | P1 decline, P2 thắng |
| `BadCredentialsException` | success | không gọi | P2 có thể khắc phục lỗi P1; cần rà soát downgrade |
| success | không gọi | không gọi | First-success-wins |
| `BadCredentialsException` | `null` | success | Parent **có thể** thành công |
| `LockedException` | không gọi | không gọi | AccountStatusException dừng chain |
| `InternalAuthenticationServiceException` | không gọi | không gọi | Lỗi backend nội bộ dừng chain |
| hai providers không supports | — | không parent | `ProviderNotFoundException` |
| tất cả providers trả `null` | — | không parent | `ProviderNotFoundException` nếu không có lỗi khác |
| P1 BadCredentials, P2 BadCredentials | — | không parent | Exception cuối được ném |
| child BadCredentials | — | parent ProviderNotFound | Lỗi child có thể được giữ thay vì lỗi parent |

Đặc biệt: **`BadCredentialsException` không mặc nhiên dừng chuỗi**. Nếu một legacy provider nằm sau xác thực bằng password yếu hơn, tài khoản có thể đăng nhập dù provider chính đã từ chối. Ngược lại, không nên lạm dụng `LockedException` chỉ để ép dừng mọi password sai: đó là exception cho trạng thái account thực sự bị khóa, không phải một primitive “break” tùy tiện.

### 8.2. Ý nghĩa của `ProviderNotFoundException`

`ProviderNotFoundException: No AuthenticationProvider found for ...` thường nghĩa là:

- Filter tạo request token class không được bất kỳ provider nào supports.
- Provider bean bạn tạo không được đưa vào **manager dùng bởi filter**.
- Sai chain/manager (API chain dùng manager A, provider ở manager B).
- Custom provider supports sai class/package hoặc thiếu inheritance.
- Parent không có hoặc cũng không xử lý được.
- Sai lệch giữa Servlet và Reactive types.

Nó **không** nói password chắc chắn sai. Muốn hiểu, lấy concrete class của input authentication và danh sách providers **thực sự nằm trong manager đang xử lý**.

### 8.3. Đọc kết quả xác thực không nên tin mọi Authentication

`Authentication.isAuthenticated()`, `getPrincipal()`, `getAuthorities()` và `getCredentials()` là dữ liệu kiểm chứng bên trong trusted layer. `ProviderManager` mặc định xóa credentials khỏi result nếu result implement `CredentialsContainer`, nên việc `getCredentials()==null` sau thành công **không có nghĩa provider “không nhận password”**.

Một `Authentication` có thể là anonymous/remember-me/fully authenticated. `isAuthenticated()==true` không tự chứng minh recent MFA hoặc WebAuthn UV. Authorization phải dùng đúng mức bảo đảm và quyền phù hợp.

## 9. Parent AuthenticationManager: ranh giới fallback dễ bị hiểu sai

Có thể khai báo:

```java
AuthenticationManager parent =
        new ProviderManager(List.of(sharedProvider));

AuthenticationManager child =
        new ProviderManager(List.of(localProvider), parent);
```

`parent` là **manager xác thực dự phòng**, không phải BeanFactory parent, parent class hay cache. Khi child không có thành công từ local providers (trừ những exception dừng sớm), parent có thể thử token.

### 9.1. Debug manager cha

Hãy ghi an toàn:

- Manager nào được filter gọi đầu tiên? Dùng bean ID/identity hoặc một wrapper test, không log credentials.
- Danh sách providers trong child là gì, theo đúng thứ tự?
- Parent có thực sự được gắn trong constructor/DSL hay chỉ tồn tại như một bean?
- `supports` của parent có xử lý cùng token type không?
- Local provider có trả `null`/`BadCredentialsException`, hay đã trả authenticated result?
- Có `AccountStatusException`/`InternalAuthenticationServiceException` chặn trước parent không?

### 9.2. Fallback có thể là lỗ hổng

Nếu child là policy mới cho nhân viên, parent là password provider cũ:

```text
Child: username alice + wrong/expired corporate password
    -> BadCredentialsException
    -> Parent legacy provider chấp nhận một password cũ
    -> LOGIN SUCCESS (SECURITY DOWNGRADE)
```

Đó không nhất thiết là bug của Spring Security; là **chính sách manager composition sai**. Muốn tách realm, hãy dùng token types khác, explicit identity routing hoặc authoritative backend policy, không dựa vào `BadCredentials` để dừng chain.

### 9.3. Không tạo vòng parent-child

Đừng để manager A có parent B rồi B lại gọi A. Vòng lặp có thể dẫn tới recursion vô hạn/StackOverflowError. Nếu nhiều SecurityFilterChain dùng chung parent, mô tả graph và unit test riêng từng child.

## 10. Chẩn đoán bean/wiring: provider tồn tại nhưng manager không biết

Một trong những nguyên nhân phổ biến nhất là **nhầm giữa bean trong Spring ApplicationContext và cấu hình của AuthenticationManager thực sự gắn với filter**.

### 10.1. Những cách cấu hình có ý nghĩa khác nhau

```java
// 1. Provider được tham chiếu rõ trong HttpSecurity của chain hiện tại.
http.authenticationProvider(customProvider);

// 2. Manager được gắn trực tiếp cho HttpSecurity của chain hiện tại.
http.authenticationManager(explicitManager);

// 3. Tự tạo manager độc lập.
AuthenticationManager explicitManager =
        new ProviderManager(List.of(customProvider));

// 4. Bean provider sống trong ApplicationContext:
// @Bean AuthenticationProvider customProvider() { ... }
```

**Không đồng nhất cả bốn.** Spring Security có auto-configuration/global manager và local per-`HttpSecurity` contexts; cách kết hợp beans/configurers có thể khác theo version và số lượng providers. Để chẩn đoán, **đừng chỉ thấy bean đã được tạo rồi kết luận filter đang dùng nó**. Ghi/inspect **actual manager được gắn với filter chain của request**.

### 10.2. `AuthenticationConfiguration.getAuthenticationManager()`

Spring Security có `AuthenticationConfiguration#getAuthenticationManager()` để lấy manager từ configuration scope phù hợp trong nhiều trường hợp. Nhưng nó không có nghĩa mọi per-chain custom manager đều là **cùng một singleton global**.

Nếu project có nhiều `SecurityFilterChain` và gọi:

```java
http.authenticationManager(childManager);
```

thì hãy test flow của **chính chain đó**. Không lấy manager từ application context để viết unit test rồi giả định HTTP filter cũng gọi instance ấy. Ưu tiên cấu hình explicit và test filter-chain integration.

### 10.3. `@Bean` / `@Component` nhiều provider và thứ tự

`ProviderManager` dựa trên danh sách có thứ tự. Đừng suy thứ tự xác thực từ tên class, tên bean hoặc filesystem scanning. Nếu order bảo mật quan trọng, tạo danh sách một cách tường minh:

```java
ProviderManager manager =
        new ProviderManager(List.of(primaryProvider, fallbackProvider));
```

Với fallback provider, chỉ cho phép khi domain/policy thiết kế rõ. Nếu `ProviderManager.getProviders()` cho phép đọc danh sách, có thể inspect tên class/ID **trong test/diagnostic mode**; không dùng API này để đổi provider list động từ client.

## 11. DaoAuthenticationProvider: nhìn đúng lỗi password/identity source

`DaoAuthenticationProvider` xử lý `UsernamePasswordAuthenticationToken` thông qua `UserDetailsService` và `PasswordEncoder`.

```text
UsernamePasswordAuthenticationFilter
   -> UsernamePasswordAuthenticationToken
   -> ProviderManager
   -> DaoAuthenticationProvider
       -> UserDetailsService.loadUserByUsername
       -> account prechecks (locked, enabled, account expired)
       -> PasswordEncoder.matches(raw, encoded)
       -> credentials/account postchecks
       -> authenticated UsernamePasswordAuthenticationToken
```

Nếu provider DAO thực sự chạy nhưng login vẫn thất bại, kiểm tra:

1. `UserDetailsService` đang dùng **database/schema/tenant nào**, có load đúng user không?
2. `PasswordEncoder` có khớp format hash lưu trong DB không? Đặc biệt `DelegatingPasswordEncoder` thường mong prefix như `{bcrypt}` hoặc `{pbkdf2}` nếu configured phù hợp.
3. Raw password từ form đã được parse đúng chưa? `POST` vs JSON form, field names, Unicode normalization.
4. UserDetails trả đúng `getPassword()` hash không; có disabled/locked/expired flags không?
5. Password đã đổi nhưng cache `UserDetails` còn stale không?
6. Provider có mang realm policy đúng không; một provider khác cùng token class có chấp nhận credential yếu hơn không?
7. Hệ thống có dùng LDAP bind, OIDC hay passkey thay vì local password không? Nếu thế, **DAO không nhất thiết được gọi**.

**Không sửa lỗi bằng `{noop}` trong production** hoặc đổi PasswordEncoder thành loại không xác minh password. Một lỗi prefix/hash là vấn đề migration/encoder config, cần giải quyết theo chính sách bảo mật.

### 11.1. Spring Security 6.5 API thực tế

`DaoAuthenticationProvider` có constructor nhận `UserDetailsService`:

```java
DaoAuthenticationProvider dao =
        new DaoAuthenticationProvider(userDetailsService);
dao.setPasswordEncoder(passwordEncoder);
```

Đây là trích đoạn trong class cấu hình có variables bean hợp lệ. Constructor no-arg/setUserDetailsService cũ đã bị deprecate ở 6.5; ưu tiên constructor dependency rõ ràng. Một ví dụ Spring Boot có thể chạy được ở mục 16.

### 11.2. UsernameNotFound không nhất thiết lộ ra ngoài

`AbstractUserDetailsAuthenticationProvider` có thể ẩn `UsernameNotFoundException` thành `BadCredentialsException` để hạn chế user enumeration. Vì vậy **“Bad credentials” không phải bằng chứng user đã tồn tại**. Trong tests, xác minh repository/identity lookup an toàn và status ngoài trình duyệt thống nhất, tránh log username/PII quá chi tiết.

## 12. Phân biệt authentication failure, authorization failure và HTTP response

Cần trả lời trước khi tiếp tục debug:

| Tình huống | Lớp phản hồi thông thường | Ví dụ |
| --- | --- | --- |
| POST form login sai password | `AuthenticationFailureHandler` của form filter | Redirect `/login?error`, không phải luôn 401 |
| Request resource anonymous | `ExceptionTranslationFilter` → `AuthenticationEntryPoint` | 302 login hoặc 401 Basic/Bearer |
| Đã authenticated nhưng thiếu role/scope | `AccessDeniedHandler` | 403 |
| POST thiếu CSRF | `CsrfFilter` / AccessDeniedHandler | 403 trước login provider |
| Bearer header invalid | Bearer filter/failure handler, decoder | 401 `WWW-Authenticate` theo RFC 6750 |
| Browser không gửi session cookie | Context repository/remember-me/entry point | 302 login dù lần trước đã thành công |
| API route 404 | Servlet routing, security matcher/filter endpoint | Có thể request không tới auth filter; không suy ra ProviderNotFound |

**Sai lầm hay gặp:** chỉ thấy 401 rồi thêm `.formLogin(...)` vào API Bearer. Điều này có thể làm API trả HTML redirect và thêm session không mong muốn mà **không giải quyết** decoder/manager đang thiếu.

### 12.1. Khác nhau giữa “đã xác thực” và “có quyền”

Một `Authentication` thành công nhưng thiếu `ROLE_ADMIN` vẫn bị `authorizeHttpRequests(...).hasRole("ADMIN")` chặn. Khi đó **không** phải ProviderManager chọn sai. Kiểm tra `getAuthorities()`, mapping scope/role và object-level authorization.

### 12.2. Cách debug response không follow redirect

Nếu `curl -L` tự theo redirect, trang login cuối có thể trả 200 khiến bạn tưởng API đã success. Dùng:

```bash
curl -i http://localhost:8080/private
```

và đọc `HTTP/1.1 302` cùng `Location` ở response đầu. Với REST API, cần xem `WWW-Authenticate`, `Content-Type` và status nguyên thủy chứ không chỉ body cuối.

## 13. JWT/opaque/OIDC: cơ chế có thể không dùng DAO

### 13.1. Bearer JWT

Một cấu hình resource server:

```java
http.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
```

Khi hoạt động, `BearerTokenAuthenticationFilter` lấy token từ header, manager JWT decoder/`JwtAuthenticationProvider` xác minh signature, issuer, expiry và các validators đã cấu hình; sau đó trả `JwtAuthenticationToken`. `DaoAuthenticationProvider` không phải backend dành cho JWT trong flow thông thường.

Nếu Bearer auth “không chạy”, hỏi:

- `/api/**` có match API chain đã bật oauth2ResourceServer không?
- Authorization header thực sự có `Bearer <token>` đúng chuẩn không?
- `BearerTokenAuthenticationFilter` có trong chain?
- Issuer/JWKS/`JwtDecoder`, audience validator có cấu hình đúng không?
- `AuthenticationManagerResolver` có chọn đúng issuer/tenant manager không?
- `JwtAuthenticationConverter` có map authorities/scopes đúng không?
- Error là 401 **authentication** hay 403 **authorization**?

**Không** “sửa” JWT sai issuer bằng cách tắt issuer/signature check hoặc tin payload JWT chưa verified.

### 13.2. Opaque token và introspection

Với opaque token, `OpaqueTokenAuthenticationProvider`/introspector liên hệ Authorization Server theo config. 401 có thể do token inactive, AS timeout, client auth sai hoặc introspection endpoint không phù hợp. Kiểm tra loại manager và introspector; **đừng chờ `UserDetailsService` được gọi** nếu architecture không dùng nó.

### 13.3. OAuth2 Login / OpenID Connect

`oauth2Login(...)` dùng authorization-code flow, redirect/callback như `/login/oauth2/code/{registrationId}`. Cấu hình sai redirect URI/client registration, proxy baseURL hoặc state cookie/session có thể khiến **callback không được filter nhận**. `AuthenticationProvider` dành cho password không giúp sửa OIDC callback.

Các câu hỏi:

- Login initiation endpoint có được phép truy cập không?
- Callback URL (path, scheme, host) có khớp configuration ở IdP không?
- Request có đúng `code`/`state`, session chứa authorization request không?
- Chain có `OAuth2LoginAuthenticationFilter` không?
- OIDC ID token validation/nonce/issuer đúng không?
- Sau successful callback, account mapping/local status check có được chạy không?

Không dùng email claim chưa xác minh như một identifier đủ để tự tạo account có đặc quyền.

### 13.4. Remember-me, One-Time Token và passkey

Các cơ chế này có filter/token/provider riêng. Nếu bạn thêm service hoặc repository bean nhưng **chưa bật DSL** (`rememberMe`, `oneTimeTokenLogin`, `webAuthn`), cơ chế tương ứng có thể không được đưa vào filter chain. Một remembered user có thể được xem là authenticated nhưng không **fullyAuthenticated**; đừng hiểu redirect yêu cầu reauth là provider không chạy.

## 14. SecurityContext: provider thành công mà request sau vẫn mất login

Giả sử logs xác nhận `DaoAuthenticationProvider` đã trả authenticated token. Nếu browser gọi request kế tiếp mà lại bị redirect login, hãy chuyển sang chẩn đoán **persistence**, không tiếp tục thay providers.

### 14.1. Session vs stateless

- Form login thường lưu security context vào HTTP session, trình duyệt phải gửi đúng `JSESSIONID`/`SESSION` cookie.
- API JWT/Basic stateless thường cần xác thực trên mỗi request, không tự lưu result vào HTTP session.
- `SessionCreationPolicy.STATELESS` có ý nghĩa khác với browser session login. Đừng đặt stateless cho cùng web chain rồi mong form-login session tồn tại qua requests.
- Reverse proxy, cookie `Secure`/`SameSite`/`Domain`/`Path` và load balancer/session store có thể khiến session không quay về cùng dữ liệu.

### 14.2. Spring Security 6: explicit save khi tự xác thực trong controller/filter

Nếu bạn tự gọi `AuthenticationManager.authenticate(...)` bên ngoài built-in authentication filter và muốn duy trì login qua requests, cần lưu `SecurityContext` vào `SecurityContextRepository` phù hợp:

```java
// Trích đoạn Servlet: nằm trong trusted login controller/filter,
// cần bean manager, strategy và repository đã cấu hình.
Authentication result = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password));

SecurityContext context = securityContextHolderStrategy
        .createEmptyContext();
context.setAuthentication(result);
securityContextHolderStrategy.setContext(context);
securityContextRepository.saveContext(context, request, response);
```

Các biến là dependencies có thực của app; đây **không** phải standalone class. Với Spring Security 6, `SecurityContextHolderFilter` thường chỉ **đọc** context từ repository; custom code cần save tường minh. Đừng kết luận “provider không chạy” vì request thứ hai lại anonymous sau khi custom login thành công.

### 14.3. Async/reactive context

`SecurityContextHolder` mặc định dựa trên ThreadLocal ở Servlet. Nếu authentication được tạo trong một thread nhưng business logic chạy ở executor khác, context có thể không tự lan truyền. Dùng `DelegatingSecurityContextRunnable/Executor` hoặc cơ chế context propagation tương ứng, không bật `MODE_GLOBAL` cho web app nhiều users.

Ở WebFlux, dùng Reactor Context/`ReactiveSecurityContextHolder`, không sao chép assumptions ThreadLocal. Câu hỏi cần chẩn đoán là **context nằm ở đâu**, không chỉ manager nào được gọi.

## 15. Quy trình debug theo từng mốc có thể chứng minh

Thực hiện theo thứ tự từ ngoài vào, dừng ở **mốc đầu tiên không đạt**.

| Bước | Kiểm tra | Nếu fail |
| --- | --- | --- |
| 1 | URL/method/headers/body/cookies đã đúng request reproduce? | Fix HTTP client/route trước |
| 2 | `springSecurityFilterChain` đang được đăng ký trong container? | Fix Security config/test setup |
| 3 | `FilterChainProxy` chọn đúng SecurityFilterChain? | Fix `securityMatcher`/`@Order`/context path |
| 4 | Chain chứa authentication filter mong muốn? | Bật DSL/cấu hình filter |
| 5 | Filter được invoke và internal matcher chấp nhận request? | Fix loginProcessingUrl/method/Bearer header/CSRF/CORS |
| 6 | Filter tạo đúng concrete `Authentication` type? | Fix token factory/converter |
| 7 | Filter gọi đúng `AuthenticationManager`? | Fix per-chain manager binding |
| 8 | Manager chứa đúng providers và thứ tự? | Fix explicit list/parent wiring |
| 9 | `supports(token.class)` nhận đúng? | Fix supports; test type/subclass |
| 10 | Provider trả null/exception/success theo policy? | Fix provider logic/DB/decoder |
| 11 | Parent được gọi đúng luật? | Rà soát fallback/downgrade/short circuit |
| 12 | Authenticated result được lưu vào context khi cần? | Fix saveContext/cookie/session |
| 13 | Authorization vẫn chặn? | Fix role/scope/ownership mapping |
| 14 | HTTP response đúng protocol? | Fix failure handler/entry point/CSRF/CORS |

Giữ mỗi bước một bằng chứng (log line, test assertion, config snapshot đã được redact). Chỉ sau khi tìm được **first failing boundary** mới sửa code/config. Đừng cùng lúc tắt CSRF, thay ProviderManager, đổi user details và chuyển filter order; như vậy không biết thay đổi nào giải quyết vấn đề.

## 16. Demo Spring Boot Java 17: hai chain, một manager rõ ràng

Demo dưới đây cho thấy cùng một `DaoAuthenticationProvider` được dùng tường minh bởi **hai chain khác nhau**: `/api/**` dùng HTTP Basic stateless; web dùng form login session. Mục đích là xác nhận **tách request matcher/filter** trước khi điều tra providers.

### 16.1. Dependencies

Trong project Spring Boot 3.5.x Java 17 đã có Gradle plugin:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 16.2. Class main và SecurityFilterChains

Lưu `src/main/java/demo/diagnosis/DiagnosticApplication.java`:

```java
package demo.diagnosis;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DiagnosticApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiagnosticApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    DaoAuthenticationProvider passwordProvider(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider dao =
                new DaoAuthenticationProvider(users);
        dao.setPasswordEncoder(encoder);
        return dao;
    }

    @Bean
    AuthenticationManager passwordManager(
            DaoAuthenticationProvider dao) {
        return new ProviderManager(List.of(dao));
    }

    @Bean
    @Order(1)
    SecurityFilterChain api(
            HttpSecurity http, AuthenticationManager passwordManager)
            throws Exception {
        return http
                .securityMatcher("/api/**")
                .authenticationManager(passwordManager)
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(
            HttpSecurity http, AuthenticationManager passwordManager)
            throws Exception {
        return http
                .authenticationManager(passwordManager)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class Pages {
        @GetMapping("/")
        String home() {
            return "Public";
        }

        @GetMapping("/api/me")
        String api(Authentication authentication) {
            return "API:" + authentication.getName();
        }

        @GetMapping("/private")
        String privatePage(Authentication authentication) {
            return "WEB:" + authentication.getName();
        }
    }
}
```

**Các điểm cố ý tường minh:**

- `@Order(1)` và `securityMatcher("/api/**")`: API chain được xét trước.
- API chain chỉ bật `httpBasic`, không bật `formLogin`. Không có Bearer JWT ở demo.
- Web chain catch-all có `formLogin`, không nhận request `/api/me` do chain API đã thắng.
- Hai chain cùng được gắn **đúng bean `passwordManager`**, và bean này chỉ có `DaoAuthenticationProvider` với constructor/API Spring Security 6.5 phù hợp.
- `PasswordEncoder` dùng BCrypt để minh họa; password local chỉ là test fixture, không đưa vào production.
- API GET stateless; với những API có write operations cần thiết kế CSRF riêng theo cách client mang credential. **Đừng tự tắt CSRF bằng `csrf.disable()` trên cả ứng dụng**.
- App không có JWT decoder, LDAP, OIDC client hay custom filter — nếu cần những cơ chế đó, phải thêm filter/manager đúng loại, không thêm password provider.
- Chỉ demo login/route; chưa có user database, rate limiting, audit, persistent session store, HTTPS hoặc advanced account lifecycle.

### 16.3. Chạy và đọc phản hồi

```bash
./gradlew bootRun
```

Windows dùng `gradlew.bat bootRun`. Với server port mặc định 8080:

```bash
# API không có credentials: HTTP 401 + Basic challenge.
curl -i http://localhost:8080/api/me

# API có Basic đúng: HTTP 200, body "API:alice".
curl -i -u alice:demo-password http://localhost:8080/api/me

# Browser route khi anonymous: HTTP 302 -> /login.
curl -i -H 'Accept: text/html' http://localhost:8080/private

# Public route: HTTP 200, body "Public".
curl -i http://localhost:8080/
```

Kết quả mong đợi:

| Request | Status | Đặc trưng |
| --- | --- | --- |
| `GET /api/me` không Authorization | 401 | `WWW-Authenticate: Basic...` |
| `GET /api/me` với Basic đúng | 200 | Body `API:alice` |
| `GET /api/me` với Basic sai | 401 | Không tạo authenticated principal |
| `GET /private` anonymous | 302 | `Location` đến `/login` |
| `GET /` anonymous | 200 | `Public` |
| `POST /login` qua form với CSRF, credential đúng | 302 hoặc redirect success theo form config | Browser có phiên đăng nhập |

Dùng `curl -i` thay vì `curl -L` để nhìn redirect đầu tiên. Không nhầm `HTTP 401` với `ProviderNotFoundException` khi chỉ thiếu Basic header: trường hợp không credentials có thể chưa gọi manager.

## 17. MockMvc integration test: chứng minh chain và authentication filter thật

Tạo file `src/test/java/demo/diagnosis/DiagnosticWebTest.java`:

```java
package demo.diagnosis;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class DiagnosticWebTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiHasBasicChallengeWithoutCredentials() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string("WWW-Authenticate",
                        containsString("Basic")));
    }

    @Test
    void apiAuthenticatesBasicCredential() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "demo-password")))
                .andExpect(status().isOk())
                .andExpect(content().string("API:alice"));
    }

    @Test
    void apiRejectsBadBasicPassword() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "wrong-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void browserRedirectsToLogin() throws Exception {
        mvc.perform(get("/private"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location",
                        containsString("/login")));
    }

    @Test
    void interactiveFormLoginAuthenticatesAlice() throws Exception {
        mvc.perform(formLogin()
                        .user("alice")
                        .password("demo-password"))
                .andExpect(authenticated().withUsername("alice"));
    }

    @Test
    void publicPageIsAllowed() throws Exception {
        mvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(content().string("Public"));
    }
}
```

Chạy:

```bash
./gradlew test --tests demo.diagnosis.DiagnosticWebTest
```

Kỳ vọng **6 bài test PASS** nếu chạy trên phiên bản/stack đúng với demo. MockMvc đi qua Spring Security filter chain nhờ `@AutoConfigureMockMvc`/`spring-security-test`; nếu tự dùng `MockMvcBuilders.standaloneSetup(...)`, phải gắn `springSecurity()` hoặc `FilterChainProxy` đúng cách.

**Cảnh báo:** `.with(user("alice"))` là test fixture đặt principal đã authenticated, **bypass quy trình kiểm tra password/provider**. Nó tốt cho authorization test, nhưng không chứng minh ProviderManager/DaoAuthenticationProvider đã chạy. Vì vậy ví dụ dùng `httpBasic(...)` và `formLogin()` để test các login mechanisms thật.

### 17.1. Lưu ý để không tạo false positive

Một test chỉ gọi `GET /private` rồi nhận 302 có thể PASS dù filter login **không hoạt động**. Cần có ít nhất một test gửi **credential đúng** và chứng minh kết quả authenticated. Tương tự, test API nhận 401 khi thiếu Authorization chỉ chứng minh protected resource/entry point hoạt động, chưa chứng minh `DaoAuthenticationProvider` đã được dùng.

Dùng session/cookie từ request login thành công nếu bạn muốn kiểm tra request tiếp theo. Nếu frontend gửi cookie sai path hoặc load balancer không giữ session, unit test provider vẫn PASS — lúc ấy là lỗi context/session, không phải manager.

## 18. Unit test ProviderManager: tìm rõ provider nào nhận token

Khi HTTP test vẫn không lý giải được hành vi, tách manager ra một **JUnit/Mockito test** để kiểm tra `supports`, thứ tự, return `null`, exception và parent. Đây là test component, **không kiểm tra HTTP filter**.

Tạo file `src/test/java/demo/diagnosis/ProviderSelectionTest.java`:

```java
package demo.diagnosis;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.InternalAuthenticationServiceException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class ProviderSelectionTest {

    private static final Class<UsernamePasswordAuthenticationToken> TYPE =
            UsernamePasswordAuthenticationToken.class;

    private Authentication request() {
        return UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-password");
    }

    private Authentication accepted(String name) {
        return UsernamePasswordAuthenticationToken.authenticated(
                name, "test-secret",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private AuthenticationProvider provider(boolean supports) {
        AuthenticationProvider p = mock(AuthenticationProvider.class);
        when(p.supports(TYPE)).thenReturn(supports);
        return p;
    }

    @Test
    void supportsFalseMeansProviderIsSkipped() {
        AuthenticationProvider p1 = provider(false);
        AuthenticationProvider p2 = provider(true);
        when(p2.authenticate(any(Authentication.class)))
                .thenReturn(accepted("p2"));

        var manager = new ProviderManager(List.of(p1, p2));
        assertEquals("p2", manager.authenticate(request()).getName());

        verify(p1, never()).authenticate(any(Authentication.class));
        verify(p2).authenticate(any(Authentication.class));
    }

    @Test
    void nullMeansTryNextProviderInOrder() {
        AuthenticationProvider p1 = provider(true);
        AuthenticationProvider p2 = provider(true);
        when(p1.authenticate(any(Authentication.class))).thenReturn(null);
        when(p2.authenticate(any(Authentication.class)))
                .thenReturn(accepted("p2"));

        var manager = new ProviderManager(List.of(p1, p2));
        assertEquals("p2", manager.authenticate(request()).getName());

        InOrder order = inOrder(p1, p2);
        order.verify(p1).supports(TYPE);
        order.verify(p1).authenticate(any(Authentication.class));
        order.verify(p2).supports(TYPE);
        order.verify(p2).authenticate(any(Authentication.class));
    }

    @Test
    void firstAuthenticatedResultStopsTraversal() {
        AuthenticationProvider p1 = provider(true);
        AuthenticationProvider p2 = provider(true);
        when(p1.authenticate(any(Authentication.class)))
                .thenReturn(accepted("first"));

        var manager = new ProviderManager(List.of(p1, p2));
        assertEquals("first", manager.authenticate(request()).getName());

        verify(p2, never()).supports(any());
        verify(p2, never()).authenticate(any(Authentication.class));
    }

    @Test
    void ordinaryBadCredentialsMayFallThrough() {
        AuthenticationProvider p1 = provider(true);
        AuthenticationProvider p2 = provider(true);
        when(p1.authenticate(any(Authentication.class)))
                .thenThrow(new BadCredentialsException("rejected"));
        when(p2.authenticate(any(Authentication.class)))
                .thenReturn(accepted("second"));

        var manager = new ProviderManager(List.of(p1, p2));
        assertEquals("second", manager.authenticate(request()).getName());
    }

    @Test
    void lockedStopsNextProviderAndParent() {
        AuthenticationProvider p1 = provider(true);
        AuthenticationProvider p2 = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);
        when(p1.authenticate(any(Authentication.class)))
                .thenThrow(new LockedException("locked"));

        var manager = new ProviderManager(List.of(p1, p2), parent);

        assertThrows(LockedException.class,
                () -> manager.authenticate(request()));
        verify(p2, never()).supports(any());
        verifyNoInteractions(parent);
    }

    @Test
    void internalServiceFailureStopsFallback() {
        AuthenticationProvider p1 = provider(true);
        AuthenticationProvider p2 = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);
        when(p1.authenticate(any(Authentication.class)))
                .thenThrow(new InternalAuthenticationServiceException(
                        "backend unavailable"));

        var manager = new ProviderManager(List.of(p1, p2), parent);

        assertThrows(InternalAuthenticationServiceException.class,
                () -> manager.authenticate(request()));
        verify(p2, never()).authenticate(any(Authentication.class));
        verifyNoInteractions(parent);
    }

    @Test
    void childDeclinesSoParentIsUsed() {
        AuthenticationProvider child = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);
        when(child.authenticate(any(Authentication.class)))
                .thenReturn(null);
        when(parent.authenticate(any(Authentication.class)))
                .thenReturn(accepted("parent"));

        var manager = new ProviderManager(List.of(child), parent);

        assertEquals("parent", manager.authenticate(request()).getName());
        verify(parent).authenticate(any(Authentication.class));
    }

    @Test
    void noSupportedProviderYieldsProviderNotFound() {
        AuthenticationProvider child = provider(false);
        var manager = new ProviderManager(List.of(child));

        assertThrows(ProviderNotFoundException.class,
                () -> manager.authenticate(request()));
        verify(child, never()).authenticate(any(Authentication.class));
    }
}
```

Chạy:

```bash
./gradlew test --tests demo.diagnosis.ProviderSelectionTest
```

Kỳ vọng **8 tests PASS**. Bộ test chứng minh ngữ nghĩa của manager. Nó không chạy LDAP, password encoder, JWT decoder hay filters. Để xác minh wiring của ứng dụng, cần thêm integration tests ở mục 17 hoặc test riêng bean/manager thực sự gắn vào chain.

### 18.1. Dấu hiệu quan trọng trong test

- `verify(p1, never()).authenticate(...)` xác minh `supports=false` dẫn tới skip.
- `InOrder` xác minh **thứ tự**, tránh chỉ dựa vào status success.
- `verifyNoInteractions(parent)` xác minh exceptions dừng sớm.
- Test `BadCredentials` + success của provider 2 nêu rõ rủi ro fallback nếu hai providers có chính sách mật khẩu khác nhau.
- `ProviderNotFoundException` là lỗi type support/config, không nhất thiết là password sai.
- Một test mock provider có `supports=true` nhưng `authenticate=null` là test **manager traversal**, không phải provider bug.

## 19. Trường hợp custom API-key filter: bốn điểm phải khớp

Khi thiết kế một cơ chế API key riêng, phải kiểm chứng đồng thời:

1. `ApiKeyAuthenticationFilter` có trong đúng chain.
2. Nó đọc credential đúng nguồn (header/query/body theo policy) và **chỉ hoạt động trên đúng URL/method**.
3. Nó tạo đúng `ApiKeyAuthenticationToken` unauthenticated và gọi **manager chứa ApiKeyAuthenticationProvider**.
4. Provider `supports(ApiKeyAuthenticationToken.class)` và thực sự kiểm tra token hash, expiry, revocation, account/tenant status trước khi trả Authentication đã xác thực.

Ví dụ chỉ để thấy ranh giới:

```java
// Trích đoạn trong custom authentication filter:
String apiKey = request.getHeader("X-Api-Key");
if (apiKey != null && !apiKey.isBlank()) {
    Authentication unauthenticated =
            new ApiKeyAuthenticationToken(apiKey);
    Authentication accepted =
            authenticationManager.authenticate(unauthenticated);
    // Phải dùng success strategy/context repository đúng contract.
}
// Nếu request không có header, policy phải quyết định skip hay 401.
```

`ApiKeyAuthenticationToken`, filter và authenticationManager là **custom application abstractions**; snippet không compile độc lập. Không tự thêm `SecurityContextHolder.getContext().setAuthentication(...)` rồi bỏ qua saving/clearing và failure handling. Dùng `AuthenticationFilter`, converter + success/failure handlers khi phù hợp sẽ giảm lỗi.

### 19.1. Đừng tự đăng ký filter ở mọi chain

Nếu API key chỉ hợp lệ cho `/service/**`, filter nên được gắn đúng chain; khi path không match, không xử lý. Một custom filter có mặt ở browser chain có thể vô tình chấp nhận API key trên trang quản trị, làm sai trust boundary.

### 19.2. Testing custom token

Viết test:

```java
assertTrue(apiKeyProvider.supports(ApiKeyAuthenticationToken.class));
assertFalse(apiKeyProvider.supports(
        UsernamePasswordAuthenticationToken.class));
```

Đây là trích đoạn bên trong JUnit class có `apiKeyProvider` và `ApiKeyAuthenticationToken` được định nghĩa. Sau đó tạo filter integration test không có header, header sai, header hợp lệ, key bị revoke, tenant khác, concurrent requests và context logout. **Đừng** test bằng cách tự chèn một authenticated principal rồi gọi là đã xác minh API key.

## 20. Các bẫy cấu hình thường gặp và cách sửa

### 20.1. “Provider bean có trong context nhưng không chạy”

**Khả năng cao:** filter dùng AuthenticationManager khác hoặc thiếu filter/matcher. Kiểm logs để biết manager thực, rồi gắn provider qua `http.authenticationProvider(provider)` hay tạo `ProviderManager` explicit cho chain. Không sửa bằng cách thêm `@Primary` một cách mù quáng khi có nhiều manager scopes.

### 20.2. “Không chạy form login sau khi thêm SecurityFilterChain”

Custom chain cần `formLogin(...)` một cách tường minh nếu muốn dùng form. Kiểm tra `UsernamePasswordAuthenticationFilter` hiện diện; nếu không, thêm formLogin vào **web chain**, không vào API stateless Bearer chain.

### 20.3. “POST /login 404”

Có thể bạn đã đổi `loginProcessingUrl` hoặc web chain không match `/login`. `UsernamePasswordAuthenticationFilter` chỉ xử lý matching request; nếu không có controller/route nhận POST, Spring MVC có thể trả 404/405. Đừng tự viết controller nhận password rồi tạo authenticated token giả chỉ để hết 404.

### 20.4. “POST /login 403 và không có provider logs”

`CsrfFilter` có thể từ chối request trước khi filter login chạy. Gửi CSRF token hợp lệ. Với `spring-security-test`, dùng `formLogin()` hoặc `.with(csrf())`. Không disable CSRF toàn bộ để làm test xanh.

### 20.5. “Dùng POST JSON /login nhưng provider thấy password null”

Mặc định form filter đọc form parameters, không parse arbitrary JSON. Chọn đúng `Content-Type: application/x-www-form-urlencoded` hoặc thiết kế `AuthenticationConverter`/filter JSON có CSRF và failure handler hợp lệ. Không tự log password để debug.

### 20.6. “Mọi request API bị 302 tới /login”

API có thể đang vào catch-all web chain vì `@Order` hoặc matcher sai, hoặc chỉ bật formLogin. Với resource server/Bearer, gắn đúng API chain và `oauth2ResourceServer`. Phân biệt response 302 ban đầu với 200 cuối khi client theo redirect.

### 20.7. “JWT đúng mà BadCredentialsException từ DAO?”

Nếu raw Bearer bị biến thành `UsernamePasswordAuthenticationToken` hoặc app dùng Basic/password chain, đó là sai mechanism/token type. Kiểm API chain, bearer filter/decoder và request converter. DAO không có trách nhiệm verify JWT.

### 20.8. “ProviderNotFoundException với custom OTP”

Kiểm concrete token class ở input, `supports`, provider list của manager đúng chain, và custom filter có thật sự gọi manager đó. Tránh đăng ký bean provider mà quên gắn manager.

### 20.9. “BadCredentials từ provider đầu nhưng login vẫn thành công”

Provider sau hoặc parent có thể thành công. Rà soát security downgrade/legacy fallback. Không cố “fix” bằng cách ném `LockedException` giả, mà tách token realms hoặc authoritative checks.

### 20.10. “Lỗi LDAP timeout nhưng fallback password local vẫn chạy”

Nếu lỗi hạ tầng bị chuyển thành `BadCredentialsException`, `ProviderManager` có thể thử fallback. Khi backend xác thực không thể xác minh credential, phải áp chính sách **fail closed** và ném loại lỗi service phù hợp (`InternalAuthenticationServiceException` khi thuộc trường hợp này). Không mở đường bypass trong sự cố.

### 20.11. “Đã login nhưng request kế vẫn anonymous”

Kiểm response `Set-Cookie`, trình duyệt có gửi cookie không, `SessionCreationPolicy`, `SecurityContextRepository.saveContext` khi custom login, load balancer, Redis/Spring Session và context propagation. Đừng đổi provider nếu request trước đã xác thực thành công.

### 20.12. “Custom filter chạy hai lần”

Kiểm servlet auto-registration của Filter bean bên cạnh `HttpSecurity.addFilter...`. Vô hiệu container registration khi filter chỉ thuộc security chain. Kiểm tránh double-event, double-consume OTP và log lặp.

### 20.13. “MockMvc.with(user()) pass, production login fail”

`with(user())` tạo principal test, bypass manager. Thử `formLogin()`, `httpBasic()` hoặc request Bearer thật; dùng Spring Security Test/FilterChainProxy đúng setup. Không suy từ authorization test sang authentication test.

### 20.14. “User có role USER nhưng 403 ở /admin”

Manager đã có thể xác thực đúng, nhưng `hasRole("ADMIN")` yêu cầu `ROLE_ADMIN`. Đây là **authorization**, không phải provider selection. Kiểm granted authorities và mapping scope/role.

### 20.15. “Anonymous /login bị redirect lặp”

Custom login page bị protected, hoặc login page URL không có route. Đảm bảo login page/processing endpoint thuộc đúng chain và `permitAll` cho resource cần thiết. Không để chain API với matcher quá rộng bắt login callback.

### 20.16. “OIDC redirect_uri mismatch”

Đó có thể là client registration/callback chain/proxy URL, không phải DaoAuthenticationProvider. Kiểm `/login/oauth2/code/{registrationId}`, issuer, authorization request session, allowed redirect URI và HTTPS forwarded headers.

### 20.17. “Basic header đúng mà vẫn 401 sau khi đổi BCrypt”

UserDetails source/encoder/hash có thể sai. Xác minh `PasswordEncoder.matches(raw, encoded)` bằng fixture có kiểm soát; không chuyển sang plaintext encoder để chữa lỗi. Kiểm provider nào đang thực sự xử lý Basic token.

### 20.18. “Không thấy security logs”

Kiểm logging config profile đang chạy, có `springSecurityFilterChain`, request đi qua application nào/reverse proxy nào và test setup có attach filters không. Nếu app nằm sau gateway, gateway có thể chặn trước khi request đến service; thu HTTP/network traces đã redact từ đúng hop.

## 21. Ma trận kiểm thử chẩn đoán và bảo mật

| ID | Tình huống | Kết quả cần kiểm chứng |
| --- | --- | --- |
| D01 | `/api/**` trước web catch-all | Chọn API chain đầu |
| D02 | Web catch-all ưu tiên hơn API (negative test) | Bắt được lỗi order, không lặng lẽ redirect HTML |
| D03 | Không chain match path | Cảnh báo coverage; security policy fail closed qua fallback |
| D04 | API Basic request không header | 401 Basic challenge, không giả provider error |
| D05 | API Basic đúng password | 200, principal/role đúng |
| D06 | API Basic sai password | 401, không authenticated result |
| D07 | Browser `GET /private` anonymous | Redirect login, không đổi quyền |
| D08 | Form `POST /login` + CSRF đúng | Gọi authentication manager, login success |
| D09 | Form `POST /login` thiếu CSRF | 403, provider không cần được gọi |
| D10 | Form JSON body thay vì form params | Phát hiện converter/field mismatch |
| D11 | Đổi `loginProcessingUrl` | Filter chỉ xử lý URL mới |
| D12 | Custom filter bean ở 2 registrations | Phát hiện double invocation |
| D13 | Token type không được hỗ trợ | `ProviderNotFoundException` |
| D14 | Provider `supports=false` | Không gọi authenticate của provider đó |
| D15 | Provider trả `null` | Thử provider tiếp theo |
| D16 | Provider 1 success | Không gọi provider 2/parent |
| D17 | Provider 1 BadCredentials, P2 success | P2 thắng; đánh giá downgrade policy |
| D18 | Provider ném `LockedException` | Không fallback |
| D19 | Provider ném `InternalAuthenticationServiceException` | Không fallback |
| D20 | Child declines, parent success | Parent được gọi đúng lúc |
| D21 | Child + parent fail | Exception precedence đúng version |
| D22 | Circular parent config | Không cho phép cấu hình vòng lặp |
| D23 | Dao user disabled/locked | Không login qua password và các auth paths khác |
| D24 | Encoder/hash prefix mismatch | Fail closed, có lỗi config rõ trong test |
| D25 | Bearer JWT missing | 401 Bearer challenge theo resource-server policy |
| D26 | Bearer JWT invalid signature/issuer | Từ chối, không quay sang password fallback |
| D27 | Bearer authenticated nhưng thiếu scope | 403 thay vì sửa provider |
| D28 | OIDC callback URL sai | Bắt được filter/redirect mismatch |
| D29 | Successful custom login không save context | Request tiếp anonymous (negative test) |
| D30 | Correct context save/session cookie | Request sau dùng session được |
| D31 | Stateless API request sau không token | Không vô tình giữ principal qua session |
| D32 | Multiple webapp replicas | Manager/provider/key/shared-store consistent |
| D33 | Method-security denial | 403 đúng branch, không phải login failure |
| D34 | MockMvc.with(user()) vs formLogin() | Chứng minh first bypasses provider |
| D35 | Filter logs ở TRACE local | Đúng chain, filter order, không lộ secrets |
| D36 | CORS preflight | Preflight theo policy, không bị redirect login sai |
| D37 | Context path/proxy forwarding | Matcher đúng với path thực |
| D38 | Regression Spring Security version upgrade | Constructor/DSL/provider wiring và errors được test lại |

Để giảm thời gian sửa lỗi, biến các tình huống D01–D20 thành **automated regression tests** ở đúng tầng: unit tests `ProviderManager`, MockMvc filter chain tests, và integration tests database/AS/IdP. Một test chỉ assert status 401 không chứng minh provider selection đúng.

## 22. Cách ghi phiếu điều tra sự cố

Một báo cáo chẩn đoán tốt cần đủ dữ liệu để người khác tái hiện mà không lộ secrets:

```text
Symptom: POST /login returns 403; DaoAuthenticationProvider is never called
Environment: Spring Boot 3.5.x / Spring Security 6.5.x / Servlet
Request: POST /login, form-urlencoded, no csrf token, test account only
Selected chain: web SecurityFilterChain
Observed filters: CsrfFilter before UsernamePasswordAuthenticationFilter
First failing boundary: CSRF validation
Evidence: DEBUG "Invalid CSRF token" (redacted), MockMvc test reproduces
Root cause: frontend omitted CSRF field/header
Fix: include framework-issued CSRF token in form/POST
Validation: formLogin() test passes; POST without CSRF remains 403
Risk review: CSRF remains enabled; no authentication bypass or secret logs
```

Báo cáo tương tự cho `ProviderNotFoundException` nên ghi **tên class token input**, tên manager, danh sách provider class names và `supports` result theo thứ tự; không in token value. Với missing OAuth callback, ghi matcher chain/filter presence, không chia sẻ `code` hoặc `state` thật.

### 22.1. Tiêu chí đóng sự cố

Chỉ coi vấn đề được xử lý khi:

1. Request dùng đúng credential type đi qua chain/filter/manager mà kiến trúc quy định.
2. Credential hợp lệ có thể được xác thực, credential sai bị từ chối.
3. Account locked/disabled không bypass qua provider sau/parent.
4. Authorization vẫn bảo vệ endpoint đúng role/scope.
5. Session/context persistence đúng ý định (web có session, API stateless không tự tạo persistent login).
6. Không tắt CSRF/issuer verification/password hashing hoặc mở anonymous access để “sửa 401”.
7. Regression tests bao gồm negative cases và log không lộ credential.

## 23. Bài tập Java 17 thuần: tìm ranh giới đầu tiên bị sai

Để nhớ quy trình chẩn đoán, chương trình dưới đây mô phỏng **bốn cổng kiểm tra**: chain match, filter match, token class supports và result provider. Đây **không phải** Spring Security thật; nó là mô hình học để hiểu vì sao một manager chưa chắc đã được gọi.

Lưu `AuthPipelineDiagnosis.java`:

```java
import java.util.List;

public class AuthPipelineDiagnosis {

    record Request(String path, String method, String tokenType) {}

    interface Provider {
        boolean supports(String type);
        boolean accepts(Request request);
    }

    static String diagnose(Request request, List<Provider> providers) {
        boolean chainMatches = request.path().startsWith("/secure/");
        if (!chainMatches) {
            return "NO_CHAIN";
        }

        boolean loginFilterMatches =
                "/secure/login".equals(request.path())
                && "POST".equals(request.method());
        if (!loginFilterMatches) {
            return "FILTER_SKIPPED";
        }

        for (Provider provider : providers) {
            if (!provider.supports(request.tokenType())) {
                continue;
            }
            if (provider.accepts(request)) {
                return "AUTHENTICATED";
            }
        }
        return "NO_PROVIDER_SUCCESS";
    }

    public static void main(String[] args) {
        Provider passwordProvider = new Provider() {
            public boolean supports(String type) {
                return "PASSWORD".equals(type);
            }

            public boolean accepts(Request request) {
                return true; // mô phỏng fixture hợp lệ, KHÔNG verify password.
            }
        };

        List<Provider> providers = List.of(passwordProvider);

        System.out.println(diagnose(
                new Request("/open", "POST", "PASSWORD"), providers));
        System.out.println(diagnose(
                new Request("/secure/login", "GET", "PASSWORD"), providers));
        System.out.println(diagnose(
                new Request("/secure/login", "POST", "API_KEY"), providers));
        System.out.println(diagnose(
                new Request("/secure/login", "POST", "PASSWORD"), providers));
    }
}
```

Chạy JDK 17+:

```bash
javac AuthPipelineDiagnosis.java
java AuthPipelineDiagnosis
```

**Stdout chính xác:**

```text
NO_CHAIN
FILTER_SKIPPED
NO_PROVIDER_SUCCESS
AUTHENTICATED
```

Các kết quả lần lượt đại diện cho:

- `NO_CHAIN`: request chưa được Spring Security chain mong đợi bảo vệ.
- `FILTER_SKIPPED`: chain đã có nhưng request không phải login processing POST.
- `NO_PROVIDER_SUCCESS`: filter đã giả định gửi token nhưng không provider nào chấp nhận loại token.
- `AUTHENTICATED`: token type đúng và mô hình trả kết quả thành công.

**Không dùng mã này để xác thực người dùng thật.** Nó không kiểm password, CSRF, sessions, OAuth signature, account status hoặc exception precedence; phần đó phải được kiểm bằng Spring Security unit/integration tests ở mục 17–18.

## 24. Checklist production và quy tắc chống sửa nhầm

1. **Bằng chứng HTTP:** lưu method, path, headers đã redact, content type, cookie presence và status ban đầu, không dựa browser auto-follow.
2. **Chain:** `@Order` + `securityMatcher` rõ; API matcher trước web catch-all, có fallback bảo vệ tất cả path cần thiết.
3. **Filter:** xác nhận đúng filter tồn tại và nhận request; form default xử lý POST form-urlencoded, Basic/Bearer cần Authorization header.
4. **CSRF/CORS:** không vô hiệu bảo vệ chỉ vì login POST trả 403; kiểm CSRF và OPTIONS ở đúng layer.
5. **Token type:** trace class của unauthenticated `Authentication`, không nhầm với result class; mọi custom provider supports đúng class.
6. **Provider order:** danh sách tường minh khi bảo mật phụ thuộc order; không để legacy password fallback yếu hơn.
7. **Parent:** chỉ gắn parent khi policy cho phép; tránh circular references và surprise fallback sau BadCredentials.
8. **Error semantics:** Locked/Disabled/InternalAuthenticationServiceException không bị biến thành BadCredentials tùy tiện.
9. **DAO:** xác nhận UserDetailsService, encoder, hash format, account status và cache từ source of truth.
10. **Other mechanisms:** JWT/OIDC/opaque/OTT/passkey có filter/provider riêng; không buộc DAO xử lý request sai loại.
11. **Context:** custom successful authentication phải được lưu theo Spring Security 6 explicit-save contract nếu cần persistence; API stateless là ý định khác.
12. **Authorization:** 403 thiếu role/authority không phải authentication provider bug.
13. **Tests:** HTTP/MockMvc test login thực và unit test ProviderManager; `with(user())` chỉ dùng khi cần bypass authentication để test authorization.
14. **Observability:** DEBUG/TRACE có thời hạn, audit correlation ID và error category, không log credentials/JWT/session IDs.
15. **Regression:** test nhiều chains, provider order, exception precedence, callback URLs, proxy paths, stateless/session modes và version upgrades.

**Tóm tắt:** Nếu “`ProviderManager` chọn sai provider”, trước tiên phải chứng minh **request đã tới đúng manager**. Truy vết từ `FilterChainProxy` qua `SecurityFilterChain`, authentication filter, input token class, `supports`, provider order, parent fallback, rồi mới tới context/session và authorization. Sửa ở **ranh giới lỗi đầu tiên** sẽ chính xác và an toàn hơn mọi cách thử tắt cơ chế bảo vệ cho đến khi request trả 200.

## 25. Tài liệu chính thức

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, `ProviderManager`, `AuthenticationProvider`, filters và context.
- [Spring Security 6.5.11 — ProviderManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html): provider iteration, exception precedence, parent, credential erasure và events.
- [Spring Security 6.5.11 — AuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html): `supports`/`authenticate` và return `null`.
- [Spring Security 6.5 — Multiple HttpSecurity and matchers](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): `@Order`, `securityMatcher`, `requestMatchers`, chain coverage.
- [Spring Security — Servlet Architecture / Logging](https://docs.spring.io/spring-security/reference/servlet/architecture.html): FilterChainProxy, filter order, DEBUG/TRACE logging, custom filter registration.
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): login page/POST processing, success/failure handler.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): UserDetailsService, PasswordEncoder, username/password token flow.
- [Spring Security 6.5.11 — DaoAuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html): constructor `DaoAuthenticationProvider(UserDetailsService)`, `setPasswordEncoder`.
- [Spring Security 6.5 — MockMvc setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): `springSecurity()` và FilterChainProxy.
- [Spring Security — Testing form login](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html): `formLogin()` và CSRF.
- [Spring Security — MockMvc user fixture](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `with(user(...))` và khác biệt với kiểm thử authentication.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): `SecurityContextRepository`, explicit save và stateless sessions.
- [Spring Security — OAuth2 Resource Server/JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): BearerTokenAuthenticationFilter, JwtDecoder, JWT/authorities.
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): authorization-code flow và callback.
- [RFC 6750 — OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization: Bearer`, `WWW-Authenticate`, 401/403 semantics.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): phân loại authentication failure, chống user enumeration và bảo vệ credentials.
