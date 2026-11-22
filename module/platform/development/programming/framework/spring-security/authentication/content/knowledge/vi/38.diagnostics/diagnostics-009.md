# Bộ lọc chạy hai lần hoặc xử lý kết quả ở sai vị trí trong Spring Security

## 1. Mục tiêu: chẩn đoán đúng “hai lần” và “sai vị trí”

Trong Spring Security, một request đi qua **Servlet container filter chain**, `DelegatingFilterProxy`, `FilterChainProxy` và một `SecurityFilterChain` phù hợp. Một custom filter có thể xác thực API key, đọc bearer token, gắn correlation ID, kiểm tra tenant hoặc ghi log. Chỉ cần đăng ký filter ở hai nơi hoặc đặt nó sai thứ tự, hệ thống có thể biểu hiện rất khó hiểu:

- Log kiểm chứng credential xuất hiện hai lần cho cùng một request.
- Một API key hợp lệ vẫn nhận 401 vì filter chạy trước nơi cần có `SecurityContext` hoặc context bị ghi đè.
- Login đúng mật khẩu nhưng handler trả sai JSON/redirect; response đã bị commit rồi lại bị ghi tiếp.
- Một request chạy filter ở `REQUEST` rồi lần nữa ở `ERROR` hoặc `ASYNC` dispatch.
- Controller chạy một lần nhưng filter log hai lần; hoặc một lần user bấm nút tạo ra `OPTIONS` + `POST`.
- `AuthenticationException` bị biến thành 500 vì custom filter ném nó **trước** `ExceptionTranslationFilter`.
- Một filter xử lý xong request nhưng vẫn gọi `chain.doFilter(...)`, khiến controller và những filter phía sau chạy tiếp.
- Một lần authentication thành công bị hiểu nhầm là authorization thành công; kết quả 403 cuối cùng khiến developer tưởng filter xác thực thất bại.

Bài này thuộc mục **Chẩn đoán** của module **Spring Security - authentication**, nhằm chỉ ra **nguyên nhân, bằng chứng cần thu thập, sửa cấu hình, và cách kiểm thử**. Nội dung dành cho Spring Security **Servlet/MVC** (Spring Boot 3.5.x, Java 17+) và có chú thích riêng khi dùng WebFlux.

Sau bài, bạn có thể phân biệt ba trường hợp:

1. **Đăng ký trùng thực sự:** filter vừa được servlet container đăng ký, vừa được Security chain gọi.
2. **Nhiều lượt dispatch/request hợp lệ:** một browser action có thể sinh nhiều HTTP requests hoặc một request có `ERROR/ASYNC/FORWARD` dispatch, chưa chắc là lỗi filter.
3. **Xử lý sai vị trí:** authentication, authorization, exception translation, failure/success handler và response commit không được tổ chức đúng.

**Nguyên tắc đầu tiên:** đừng “sửa” bằng cách xóa một log hoặc thêm cờ boolean toàn cục. Phải xác định **bao nhiêu HTTP requests, bao nhiêu dispatches, bao nhiêu filter instances, bao nhiêu lần authentication và một response được commit ở đâu**.

## 2. Đường đi của request: container filter và SecurityFilterChain

Sơ đồ khái niệm cho một HTTP request Servlet:

```text
HTTP client
    |
    v
Servlet container
    |
    |  Filter A (nếu container đăng ký)
    |
    v
DelegatingFilterProxy("springSecurityFilterChain")
    |
    v
FilterChainProxy
    |
    +--> chọn SecurityFilterChain ĐẦU TIÊN khớp request
             |
             +--> SecurityContextHolderFilter
             +--> HeaderWriterFilter / CsrfFilter / CorsFilter ...
             +--> LogoutFilter
             +--> authentication filters
             +--> AnonymousAuthenticationFilter
             +--> ExceptionTranslationFilter
             +--> AuthorizationFilter
             +--> custom filters đặt theo anchor/order
             |
             v
         DispatcherServlet
             |
             v
       MVC Controller / Handler
```

Thứ tự thực tế phụ thuộc phiên bản, DSL và các filter được bật. Sơ đồ không phải danh sách đầy đủ hay cam kết mọi filter luôn có mặt. Điều bất biến hữu ích:

- **Servlet container** có thể có những filter không thuộc Spring Security.
- `DelegatingFilterProxy` là cầu nối tới bean `FilterChainProxy` thường có tên `springSecurityFilterChain`.
- `FilterChainProxy` chọn **một SecurityFilterChain khớp đầu tiên** trong danh sách; không tự chạy liên tiếp tất cả chains khớp.
- Trong chain đã chọn, filter ordering quyết định context có sẵn, CSRF/CORS có được xử lý và exception được bắt ở đâu.
- `chain.doFilter(request, response)` chuyển quyền thực thi sang **đối tượng phía sau**. Filter có thể dừng request bằng cách trả response mà **không** gọi tiếp.

### 2.1. Hai hệ thống đăng ký khác nhau

Đây là lỗi cực phổ biến:

```java
@Component
class DemoTokenFilter extends OncePerRequestFilter {
    // ...
}

@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        DemoTokenFilter tokenFilter) throws Exception {
    return http
        // ...
        .addFilterAfter(tokenFilter, LogoutFilter.class)
        .build();
}
```

**Vấn đề:** filter là Spring bean `@Component`. Spring Boot có thể **auto-register** bean implements `jakarta.servlet.Filter` vào embedded servlet container. Sau đó bạn cũng đăng ký **cùng filter instance** trong Spring Security. Một request có thể đi qua hai đường gọi filter, với thứ tự không như mong muốn.

Tài liệu Spring Security về *Declaring Your Filter as a Bean* cảnh báo chính xác tình huống này. Khi xảy ra, bạn không thể kết luận chắc “bộ lọc thực thi chính xác hai lần” chỉ bằng nhìn code: `OncePerRequestFilter` có cơ chế already-filtered marker, thứ tự container filters và dispatch types có thể khiến `doFilterInternal` chỉ chạy một lần dù vẫn **bị đăng ký ở hai nơi**. Vấn đề nghiêm trọng hơn là nó có thể chạy **ngoài SecurityFilterChain**, nơi context/exception handling không như thiết kế.

### 2.2. Hai cách sửa được tài liệu Spring hỗ trợ

**Cách A — ưu tiên khi filter chỉ dùng bên trong Spring Security:** không khai báo filter là `@Component`/`@Bean`; tạo một instance nội bộ trong `SecurityFilterChain`, inject **các dependency khác** qua method `@Bean`.

```java
@Bean
SecurityFilterChain apiChain(
        HttpSecurity http, AuthenticationManager manager)
        throws Exception {

    DemoTokenFilter tokenFilter = new DemoTokenFilter(manager);

    return http
        .securityMatcher("/api/**")
        // ...
        .addFilterAfter(tokenFilter, LogoutFilter.class)
        .build();
}
```

**Cách B — khi filter thật sự cần là Spring bean:** ngăn **container** auto-registration, nhưng vẫn dùng bean đó trong Spring Security.

```java
@Bean
FilterRegistrationBean<DemoTokenFilter> filterRegistration(
        DemoTokenFilter filter) {

    FilterRegistrationBean<DemoTokenFilter> registration =
        new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
```

Thêm import `org.springframework.boot.web.servlet.FilterRegistrationBean`. Ví dụ B là **trích đoạn**, giả định có bean `DemoTokenFilter` và chain đã đăng ký nó. `setEnabled(false)` ở đây chỉ cấm **servlet container auto-registration**, **không** tắt instance trong `SecurityFilterChain`.

**Không áp dụng cả hai cách lẫn nhau tùy tiện.** Một instance local không phải bean thì không cần `FilterRegistrationBean` để disable auto-registration.

## 3. “Bộ lọc chạy hai lần” có ít nhất sáu nguyên nhân

| Nguyên nhân | Dấu hiệu | Cần kiểm chứng |
| --- | --- | --- |
| Bean filter + `addFilterBefore/After` | Cùng class nằm cả trong container và security chain | Filter registrations + security chain composition |
| Hai instance cùng loại được thêm ở một chain | Hai log `doFilterInternal` cho một `REQUEST` | Instance ID, filter name, chain order |
| Container và security tự bật **cùng chức năng** | Ví dụ CORS/encoding/security headers xử lý hai tầng | Nguồn cấu hình ở MVC, Boot, proxy, Security |
| `REQUEST` rồi `ERROR/ASYNC/FORWARD` dispatch | Cùng correlation ID nhưng dispatcher type khác | `request.getDispatcherType()`, URI và trace |
| Browser sinh `OPTIONS` + request chính | Hai HTTP methods khác nhau | Network tab và request ID riêng |
| Client/gateway gửi lại HTTP request | Hai HTTP request IDs thật; có thể cùng payload | Retry headers/traces, gateway policy, idempotency |

Ngoài ra một frontend SPA có thể gọi API hai lần vì event listener gắn trùng, component re-render, dev Strict Mode/side effects hoặc user double-click. Trước khi sửa Spring Security phải nhìn **Network**: có thật chỉ một request tới server không?

### 3.1. Những thứ không chứng minh filter chạy hai lần

- Hai dòng log từ **hai logger khác nhau** ở cùng một filter invocation.
- Một dòng “Securing GET ...” và một dòng “Secured GET ...” từ Spring Security.
- CORS preflight OPTIONS và POST thật: là **hai requests**, không phải cùng filter xử lý cùng request hai lần.
- Hai application events, ví dụ `AuthenticationSuccessEvent` và `InteractiveAuthenticationSuccessEvent`: không chứng minh login filter chạy hai lần.
- Response 401 sau một log “Authenticated”: authentication có thể đã thành công nhưng authorization, session persistence hoặc response handler phía sau thất bại.
- Controller được gọi một lần: không loại trừ filter registration trùng ở phần trước hoặc sau controller.

**Luôn đối chiếu request ID + dispatcher type + filter instance ID + chain đã chọn + điểm log trước/sau `chain.doFilter`.**

## 4. OncePerRequestFilter đảm bảo điều gì — và không đảm bảo điều gì?

`OncePerRequestFilter` của Spring Framework giúp filter chạy **một lần cho một lượt dispatch/thực thi phù hợp trên request thread**, thông qua request attribute có hậu tố `.FILTERED` (theo constant `ALREADY_FILTERED_SUFFIX`). Nó cung cấp `doFilterInternal(...)` thay cho việc tự viết toàn bộ `doFilter(...)`.

Một class chuẩn:

```java
final class TraceFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        // Một lần chạy cho lượt dispatch được filter hỗ trợ.
        chain.doFilter(request, response);
    }
}
```

**Điều không được suy luận:**

- Không có nghĩa một user click chỉ tạo một HTTP request.
- Không có nghĩa một request không thể tạo `ASYNC` hoặc `ERROR` dispatch.
- Không thay việc đăng ký filter **chỉ một nơi**; already-filtered marker có thể làm sai thứ tự hiệu ứng khi filter bị auto-register hai đường.
- Không deduplicate hai **instances khác nhau**, nhất là khi tên/filter attribute khác nhau.
- Không giữ marker vĩnh viễn: request khác cần được xử lý lại; marker được dùng trong quá trình thực thi.
- Không đảm bảo auth result/session/token là idempotent.
- Không biến filter thành Spring Security authentication/authorization mechanism chính xác nếu nó ở sai chain.

### 4.1. Async và error dispatch

Servlet có thể dùng `DispatcherType.REQUEST`, `ASYNC`, `ERROR`, `FORWARD` hoặc `INCLUDE`. `OncePerRequestFilter` có hooks:

```java
@Override
protected boolean shouldNotFilterAsyncDispatch() {
    return true;  // Không lọc lại ASYNC dispatch.
}

@Override
protected boolean shouldNotFilterErrorDispatch() {
    return true;  // Không lọc lại ERROR dispatch.
}
```

Những method trên là **trích đoạn** trong một subclass. Default của `OncePerRequestFilter` thường tránh async/error dispatch; tuy nhiên còn phụ thuộc **Servlet filter registration dispatcherTypes** và code custom. Đọc Javadoc của phiên bản Spring Framework đang chạy.

Trường hợp response gọi `sendError(...)` có thể dẫn tới **nested ERROR dispatch**; Spring Framework có `doFilterNestedErrorDispatch(...)` để xử lý wrapper khi xảy ra nested dispatch. Dòng log cùng URI mà `DispatcherType=ERROR` không phải bằng chứng tự động rằng có bug đăng ký trùng.

### 4.2. shouldNotFilter theo path

Với filter chỉ dành cho API:

```java
@Override
protected boolean shouldNotFilter(HttpServletRequest request) {
    return !request.getServletPath().startsWith("/api/");
}
```

Cách này hữu ích khi một filter instance được dùng trên một chain rộng. Nhưng **đường bảo vệ chính** tốt hơn vẫn là `securityMatcher("/api/**")` ở `SecurityFilterChain` riêng nếu các route có auth model khác nhau. Đừng dùng `shouldNotFilter` làm thay cho authorization policy.

**Cẩn thận context path**: `getRequestURI()` có thể chứa context path, còn `getServletPath()` có semantics khác. Test với deployed context path và reverse proxy, không chỉ trên localhost root.

## 5. Nhiều SecurityFilterChain không tự có nghĩa chạy nhiều lần

Spring Security chọn **chain đầu tiên khớp**. Ví dụ:

```java
@Bean
@Order(1)
SecurityFilterChain machineApi(HttpSecurity http) throws Exception {
    return http.securityMatcher("/api/**")
        // API authentication config ...
        .build();
}

@Bean
@Order(2)
SecurityFilterChain browser(HttpSecurity http) throws Exception {
    return http
        // Form login/session config ...
        .build();
}
```

Với request `GET /api/whoami`, chain `@Order(1)` được chọn; chain thứ hai không chạy tiếp, dù một matcher rộng ở chain thứ hai cũng có thể khớp. **Thứ tự rất quan trọng**:

- Nếu chain catch-all đứng trước `/api/**`, API chain có thể **không bao giờ chạy**.
- Nếu filter chỉ gắn web chain mà request khớp API chain, nó không được gọi.
- Nếu bạn copy cùng filter vào hai chain, mỗi request vẫn chỉ chọn một chain; tuy vậy hai chains có thể dùng instances khác nhau và có lỗi cấu hình khác.
- Filter nằm **ngoài** `FilterChainProxy` trong servlet container có thể chạy bất kể chain nào Spring Security chọn.
- `web.ignoring()` khác `permitAll()`: ignore thường bỏ qua security chain cho request; public endpoint qua permitAll vẫn nhận security headers và các filters tương ứng. Không dùng ignore để “sửa” login lỗi trừ khi hiểu hệ quả.

### 5.1. securityMatcher và requestMatchers không giống nhau

`securityMatcher("/api/**")` chọn **toàn bộ SecurityFilterChain** áp dụng cho requests nào. `authorizeHttpRequests(auth -> auth.requestMatchers(...))` xác định quyền **bên trong chain đã được chọn**.

Nếu một chain chỉ `securityMatcher("/api/**")` thì các request `/web/**` không đi vào chain đó. Nếu quên chain cuối cùng bao phủ `/web/**`, có thể xuất hiện đường **không được Spring Security bảo vệ**. Luôn có một chain phù hợp cho mọi endpoint cần bảo mật, và test negative paths.

## 6. Vị trí filter: xác thực, phân quyền, audit và response

Spring Security docs gợi ý thứ tự dựa vào những bước đã xảy ra:

| Loại custom filter | Cần chạy sau điều gì? | Rủi ro nếu sai |
| --- | --- | --- |
| Authentication filter đọc API key | Security context nền và exploit protection phù hợp; thường sau `LogoutFilter` | Thiếu context, CSRF/CORS, logout hoặc duplicate auth |
| Authorization/tenant check | Authentication đã có; thường sau `AnonymousAuthenticationFilter` | Principal null/anonymous, deny sai hoặc bypass |
| Logging/correlation | Theo nhu cầu trước/sau request | Mất context nếu đặt quá sớm; log status sai nếu đặt trước commit |
| Response header decoration | Trước khi response commit, hoặc wrapper phù hợp | `IllegalStateException`, missing header, double-write |
| Metrics về kết quả HTTP | Khi downstream hoàn tất, kể cả exception/async phù hợp | Đếm sai khi response chưa xong hoặc dispatch khác |
| Handler login success/failure | Trong authentication mechanism của filter | Bị bỏ qua nếu chỉ gắn vào MVC controller |
| Access denied response | Qua authorization manager/`AccessDeniedHandler` | Mọi 403 bị nhầm với bad credentials |

**Không dựa vào số thứ tự hard-code của filters giữa các major versions.** Dùng DSL chuẩn như `httpBasic()`, `formLogin()`, `oauth2ResourceServer()`, hoặc `addFilterBefore/After(..., KnownFilter.class)` với anchor phù hợp.

### 6.1. addFilterBefore, addFilterAfter, addFilterAt

```java
http
    .addFilterBefore(myFilter, UsernamePasswordAuthenticationFilter.class);
// Hoặc:
http
    .addFilterAfter(myFilter, LogoutFilter.class);
```

Đây là **hai ví dụ thay thế**, không nên gọi cả hai cho cùng instance khi không có lý do. `addFilterAt(custom, BasicAuthenticationFilter.class)` liên quan việc đặt filter tại vị trí của filter đó; **đừng đồng thời bật `httpBasic()` và tự thêm một BasicAuthenticationFilter tại cùng vị trí**. Tài liệu Spring Security 7 chỉ ra cấu hình này gây xung đột/exception khi các filter cùng vị trí.

Nếu chỉ cần HTTP Basic authentication, cấu hình `http.httpBasic(Customizer.withDefaults())` đã đủ. Nếu cần thay implementation, xem tài liệu API của phiên bản và tắt DSL builtin tương ứng khi cần; đừng tự “chồng” hai mechanisms không chủ đích.

## 7. AuthenticationResult và HTTP response là hai thứ khác nhau

Một manager có thể trả `Authentication` hợp lệ, nhưng sau đó request vẫn có thể thất bại:

```text
ApiKeyFilter
    |
    | AuthenticationManager.authenticate(...) -> SUCCESS
    | SecurityContextHolder <- authenticated principal
    v
AnonymousAuthenticationFilter  (thường bỏ qua nếu đã authenticated)
    |
    v
AuthorizationFilter
    |
    | hasAuthority("API_READ")?
    |   YES -> Controller
    |   NO  -> AccessDeniedException
    v
ExceptionTranslationFilter / AccessDeniedHandler
    |
    v
HTTP 200 hoặc 403
```

Thành công của **authentication** không phải **authorization**. Việc filter log “authenticated principal=alice” trước `chain.doFilter` rồi phía sau trả 403 **không đủ chứng minh filter bị gọi hai lần**.

Tương tự, Spring Security form login mặc định có thể trả HTTP 302 redirect sau khi credentials đúng. API client chờ JSON 200 có thể hiểu nhầm “authentication failure”, trong khi đây là **success handler mặc định** không khớp API contract.

Ba ranh giới:

1. **Authentication filter/provider:** kiểm chứng credential và tạo authenticated principal.
2. **AuthorizationManager/AuthorizationFilter:** quyết định principal có quyền vào resource/action không.
3. **AuthenticationSuccessHandler/FailureHandler/AuthenticationEntryPoint/AccessDeniedHandler:** quyết định phản hồi HTTP tại điểm tương ứng.

Không dùng một custom filter gom tất cả: tự check password, cấp role, ghi DB, quyết định JSON, set cookie, redirect và log kết quả trong một hàm nếu các phần có thể dùng Spring Security DSL chuẩn.

## 8. Kết quả bị xử lý sai vị trí: năm lỗi đặc biệt nguy hiểm

### 8.1. Ghi response rồi vẫn gọi chain

```java
// SAI: response đã báo lỗi nhưng downstream vẫn chạy.
if (invalidCredential) {
    response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
}
chain.doFilter(request, response);
```

Điều đúng:

```java
if (invalidCredential) {
    response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
    return; // DỪNG, không cho request vào controller.
}
chain.doFilter(request, response);
```

Tương tự, nếu controller đã ghi JSON/response stream, một filter phía ngoài cố `sendRedirect(...)` sau `chain.doFilter` có thể gặp `response.isCommitted() == true`. Khi đó sửa ở **handler chịu trách nhiệm response** hoặc dùng wrapper đã thiết kế, không ghi thêm tùy tiện.

### 8.2. Gọi chain hai lần

```java
// SAI: có thể khiến downstream/Controller được gọi hai lần.
chain.doFilter(request, response);
if (shouldContinueAgain) {
    chain.doFilter(request, response);
}
```

Một filter chỉ nên gọi `chain.doFilter` **một lần trên nhánh tiếp tục**; nếu từ chối thì **không gọi**. Việc gọi nhiều lần có thể tạo side effects trùng, mất tính toàn vẹn transaction và response đã commit.

### 8.3. Catch cả lỗi downstream và biến thành 401

```java
// SAI: catch chứa cả controller và authorization ở phía sau.
try {
    Authentication result = manager.authenticate(token);
    SecurityContextHolder.getContext()
        .setAuthentication(result);
    chain.doFilter(request, response);
} catch (AuthenticationException ex) {
    response.sendError(401);
}
```

Nếu downstream ném `AuthenticationException` hoặc có cơ chế khác xử lý lỗi, catch rộng khiến lỗi của **toàn chain** bị diễn giải thành “API key sai”, thậm chí response đã commit. Tách catch đúng phần **manager invocation**:

```java
Authentication accepted;
try {
    accepted = manager.authenticate(token);
} catch (AuthenticationException ex) {
    response.sendError(401);
    return;
}

SecurityContext context =
    SecurityContextHolder.createEmptyContext();
context.setAuthentication(accepted);
SecurityContextHolder.setContext(context);

try {
    chain.doFilter(request, response);
} finally {
    SecurityContextHolder.clearContext();
}
```

Đây là trích đoạn trong custom stateless authentication filter; nó không tự định nghĩa `manager`, `token`, context repository, session strategy, success handler hoặc request variables. Ở ứng dụng chạy thật, dùng thiết kế hoàn chỉnh trong phần 11.

### 8.4. Ném AuthenticationException ở filter quá sớm rồi mong ExceptionTranslationFilter bắt

`ExceptionTranslationFilter` gọi `chain.doFilter(...)` và bắt exception do **downstream** ném. Nếu custom authentication filter đứng **trước** filter này và ném exception ra ngoài không bắt, exception không nhất thiết được dịch thành 401 như mong muốn; có thể trở thành servlet 500.

**Xử lý đúng:** custom authentication filter tự catch `AuthenticationException` từ `AuthenticationManager` rồi gọi failure handler/entry point phù hợp, hoặc dùng cơ chế DSL chuẩn. Với custom authorization check, ưu tiên `AuthorizationManager`/thứ tự sau authentication và tương thích ExceptionTranslationFilter.

Không bắt `Exception` rồi trả 401 cho mọi thứ: lỗi lập trình, DB unavailable, serialization và `NullPointerException` không đồng nghĩa credential sai.

### 8.5. Set SecurityContext nhưng không lưu khi muốn session

Spring Security 6.x có mô hình `SecurityContextHolderFilter` với **explicit save**. Nếu custom login filter muốn session-based authentication qua request sau, không thể chỉ:

```java
SecurityContextHolder.getContext().setAuthentication(accepted);
// response trả 200, nhưng request sau có thể lại anonymous.
```

Cần dùng `SecurityContextRepository.saveContext(...)` cùng session strategy và lifecycle đã thiết kế; hoặc sử dụng authentication filters chuẩn như formLogin. Với API key stateless, **không** được lưu vào HttpSession chỉ vì muốn giảm việc xác thực ở request sau.

**Đừng biến vấn đề thiếu saveContext thành “filter chạy hai lần”**. Dấu hiệu khác nhau: request A xác thực thành công, request B mới bị anonymous, dù request A chỉ chạy filter một lần.

## 9. Phân biệt các HTTP status và handler chịu trách nhiệm

| Tình huống | Điểm xảy ra | Thành phần nên xử lý |
| --- | --- | --- |
| `POST /login` sai mật khẩu, CSRF hợp lệ | `UsernamePasswordAuthenticationFilter` thử authentication và thất bại | `AuthenticationFailureHandler` |
| `GET /web/profile` anonymous | Authorization cần authentication | `AuthenticationEntryPoint` (browser có thể redirect login) |
| `GET /api/private` thiếu API key | Authorization hoặc authentication filter | Entry point / custom auth rejection có hợp đồng 401 |
| `GET /admin` đã login nhưng thiếu role | `AuthorizationFilter` | `AccessDeniedHandler`, thường 403 |
| `POST /login` thiếu CSRF | `CsrfFilter` | CSRF/access-denied handling, thường 403 |
| JSON input lỗi ở controller | MVC input binding | `@ControllerAdvice`/MVC exception resolution |
| OAuth2 callback invalid state | OAuth2 authentication filter | OAuth2 failure handler |
| Bearer token không hợp lệ | Resource server bearer filter | Bearer challenge, thường 401 `WWW-Authenticate` |
| CORS preflight bị từ chối | CORS processor | CORS response, không phải login failure |
| Exception ở custom filter trước `ExceptionTranslationFilter` | Custom filter | Catch đúng AuthException và gửi response/entry point phù hợp |

### 9.1. AuthenticationFailureHandler không bắt mọi 401

`formLogin().failureHandler(...)` được gắn với form authentication mechanism. Nó không tự chạy khi:
- user chưa login vào một resource protected;
- JWT bearer signature invalid ở resource server;
- CSRF token thiếu ở login;
- controller ném validation exception;
- custom API-key filter xử lý request khác.

### 9.2. AuthenticationSuccessHandler không được gọi thay controller

Một lần form login thành công có thể đi vào `AuthenticationSuccessHandler` và redirect tới saved request. Nếu frontend cần JSON, cấu hình handler phù hợp. Không gọi `chain.doFilter(...)` sau khi success handler đã phát response/redirect nếu cơ chế login hoàn tất. Với machine-to-machine API-key filter, thường không cần interactive login redirect; filter thiết lập Authentication rồi **cho request chính tiếp tục** để authorization/controller xử lý.

**Chọn theo request type và threat model**, không dùng cùng handler HTML cho mọi client.

## 10. Phân biệt double registration với CORS, frontend retry và dispatch

### 10.1. CORS preflight là request riêng

Browser có thể gửi:

```http
OPTIONS /api/items HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
```

Rồi mới gửi:

```http
POST /api/items HTTP/1.1
Origin: https://app.example.com
Authorization: Bearer <redacted-token>
Content-Type: application/json

{"name":"item"}
```

Đây là **hai HTTP requests khác nhau**. Preflight không phải “API key filter chạy hai lần cho POST”; nếu custom filter đòi cookie/header của request thực trong OPTIONS, nó có thể gây 401 và browser báo CORS error.

Cấu hình `http.cors(...)` đúng thứ tự với allowlist origin và xử lý preflight riêng. **Không tắt authentication cho mọi request chính** chỉ để OPTIONS qua được. CORS không thay authentication hay CSRF.

### 10.2. Redirect tạo requests tiếp theo

Form login thường:
```text
POST /login -> 302 Location: /web/profile
GET  /web/profile -> 200
```

Một lần user bấm login sinh hai requests. Log filter trên cả POST và GET có thể đúng, dù user chỉ thấy một lần click. Dựa vào method/path/request ID để phân biệt.

### 10.3. HTTP retries

Client/gateway có thể retry khi timeout/502/network failure. Nếu request có side effect, hai requests thật có thể thực thi hai lần. Filter không phải nơi duy nhất xử lý idempotency; cần nghiệp vụ sử dụng idempotency key, unique constraint hoặc transaction design. Tuyệt đối không “skip authentication” cho request retry chỉ vì idempotency key đã xuất hiện.

### 10.4. Error dispatch

Một controller ném lỗi hoặc `sendError` có thể trigger `ERROR` dispatch tới `/error`. Nếu logging filter chạy ở nhiều dispatcher types, hai log cùng correlation ID có thể phản ánh một request lifecycle có nhiều dispatches. Chú ý request attributes `jakarta.servlet.error.request_uri` và dispatcher type, không kết luận filter loop trước khi xem.

## 11. Ví dụ Spring Boot 3.5.16 / Java 17: đăng ký filter đúng một nơi

Ví dụ này cố tình có hai đường xác thực độc lập:

- `/api/**` dùng **header API key**, stateless. Một `DemoApiKeyFilter` được tạo **cục bộ** trong `SecurityFilterChain`, **không** đánh dấu `@Component` và không khai báo `@Bean`.
- `/web/**` dùng **form login + session** với user demo; không đi qua API-key filter.
- `/health` public trong web chain.
- `FilterProbe` là một **bean chỉ đếm**, không implements `Filter`, để MockMvc kiểm chứng mỗi request đơn giản chỉ vào `doFilterInternal` một lần.
- Filter bắt lỗi chỉ quanh `manager.authenticate(...)`, không catch toàn bộ downstream.
- Response 401 được ghi **một lần** rồi return; khi authentication đúng, filter tạo context và gọi chain **một lần**.
- Authorization ở `authorizeHttpRequests`, không tự quyết định role trong filter.

Giá trị API key và password chỉ được đưa từ biến môi trường vào **local lab**. Không có production secret trong mã nguồn.

### 11.1. Cấu trúc project

```text
filter-diagnostics-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/filters/FilterDiagnosticsApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/demo/filters/FilterDiagnosticsApplicationTests.java
```

### 11.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>filter-diagnostics-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
```

### 11.3. application.yml

```yaml
server:
  port: 8080

app:
  demo:
    api-key: "${DEMO_API_KEY}"
    login-password: "${DEMO_LOGIN_PASSWORD}"
```

Không có default credential. API key phải là **64 ký tự hex lowercase** do CSPRNG tạo. Password lab có thể là một chuỗi đủ dài không dùng lại ở nơi khác. Các biến thiếu khiến startup fail thay vì tự bật bypass.

### 11.4. FilterDiagnosticsApplication.java

```java
package demo.filters;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Principal;
import java.util.Collection;
import java.util.Enumeration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.logout.LogoutFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class FilterDiagnosticsApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterDiagnosticsApplication.class, args);
    }
}

/** Không implements Filter, nên Boot không auto-register vào container. */
final class FilterProbe {
    private final AtomicInteger executions = new AtomicInteger();

    void markExecution() {
        executions.incrementAndGet();
    }

    int count() {
        return executions.get();
    }
}

/** Authentication riêng: chỉ chứa API key trước khi kiểm chứng. */
final class DemoApiKeyToken extends AbstractAuthenticationToken {
    private final String principal;
    private String rawKey;

    private DemoApiKeyToken(
            String principal,
            String rawKey,
            Collection<? extends GrantedAuthority> roles,
            boolean authenticated) {
        super(roles);
        this.principal = principal;
        this.rawKey = rawKey;
        super.setAuthenticated(authenticated);
    }

    static DemoApiKeyToken requested(String rawKey) {
        return new DemoApiKeyToken(null, rawKey, null, false);
    }

    static DemoApiKeyToken verified() {
        return new DemoApiKeyToken(
            "integration-reader", null,
            List.of(new SimpleGrantedAuthority("API_READ")), true);
    }

    @Override
    public String getPrincipal() {
        return principal;
    }

    @Override
    public Object getCredentials() {
        return rawKey;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        rawKey = null;
    }

    @Override
    public void setAuthenticated(boolean authenticated) {
        if (authenticated) {
            throw new IllegalArgumentException(
                "Use verified() after checking the key");
        }
        super.setAuthenticated(false);
    }
}

/** Chỉ xác thực key có entropy cao; không lấy role từ client. */
final class DemoApiKeyProvider implements AuthenticationProvider {
    private static final Pattern KEY_FORMAT =
        Pattern.compile("[0-9a-f]{64}");

    private final byte[] expectedHash;

    DemoApiKeyProvider(String secret) {
        if (secret == null ||
                !KEY_FORMAT.matcher(secret).matches()) {
            throw new IllegalArgumentException(
                "DEMO_API_KEY must be 64 lowercase hex chars");
        }
        this.expectedHash = sha256(secret);
    }

    @Override
    public boolean supports(Class<?> type) {
        return DemoApiKeyToken.class.isAssignableFrom(type);
    }

    @Override
    public Authentication authenticate(Authentication request)
            throws AuthenticationException {
        if (!(request instanceof DemoApiKeyToken token)
                || token.isAuthenticated()) {
            return null;
        }

        Object value = token.getCredentials();

        if (!(value instanceof String key)
                || !KEY_FORMAT.matcher(key).matches()
                || !MessageDigest.isEqual(
                    expectedHash, sha256(key))) {
            throw new BadCredentialsException("Invalid API key");
        }

        return DemoApiKeyToken.verified();
    }

    private static byte[] sha256(String text) {
        try {
            return MessageDigest.getInstance("SHA-256")
                .digest(text.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("Missing SHA-256", ex);
        }
    }
}

/**
 * Custom API authentication filter, chỉ nằm trong API security chain.
 * Không @Component, không @Bean Filter, không container auto-registration.
 */
final class DemoApiKeyFilter extends OncePerRequestFilter {
    private final AuthenticationManager manager;
    private final FilterProbe probe;

    DemoApiKeyFilter(AuthenticationManager manager, FilterProbe probe) {
        this.manager = manager;
        this.probe = probe;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        probe.markExecution();

        Enumeration<String> headers =
            request.getHeaders("X-Demo-Key");

        // Để authorization/entry point trả 401 khi thiếu key.
        if (!headers.hasMoreElements()) {
            chain.doFilter(request, response);
            return;
        }

        String rawKey = headers.nextElement();

        if (headers.hasMoreElements()) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        Authentication accepted;

        try {
            // CHỈ catch AuthenticationException của manager.
            // Không bọc chain.doFilter() trong try/catch này!
            accepted = manager.authenticate(
                DemoApiKeyToken.requested(rawKey));
        } catch (AuthenticationException failed) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(accepted);
        SecurityContextHolder.setContext(context);

        try {
            // Chỉ một lần sau khi authentication thành công.
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    FilterProbe filterProbe() {
        return new FilterProbe();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${app.demo.login-password}") String password) {
        if (password == null || password.length() < 20) {
            throw new IllegalStateException(
                "DEMO_LOGIN_PASSWORD is missing or short");
        }
        UserDetails user = User.withUsername("learner")
            .password(encoder.encode(password))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(
            HttpSecurity http,
            FilterProbe probe,
            @Value("${app.demo.api-key}") String apiKey)
            throws Exception {

        AuthenticationManager apiManager =
            new ProviderManager(
                List.of(new DemoApiKeyProvider(apiKey)));

        // Local filter: Boot không tự đăng ký ở servlet container.
        DemoApiKeyFilter keyFilter =
            new DemoApiKeyFilter(apiManager, probe);

        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(s -> s.sessionCreationPolicy(
                SessionCreationPolicy.STATELESS))
            .securityContext(s -> s.securityContextRepository(
                new NullSecurityContextRepository()))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/whoami")
                    .hasAuthority("API_READ")
                .anyRequest().denyAll())
            .exceptionHandling(e -> e.authenticationEntryPoint(
                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            // Auth filter sau LogoutFilter theo vị trí gợi ý
            // của tài liệu Spring Security.
            .addFilterAfter(keyFilter, LogoutFilter.class)
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/web/**").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}

@RestController
class DemoEndpoints {

    @GetMapping("/health")
    Map<String, String> health() {
        return Map.of("status", "up");
    }

    @GetMapping("/api/whoami")
    Map<String, String> apiWhoami(Principal principal) {
        return Map.of(
            "principal", principal.getName(),
            "mechanism", "api-key");
    }

    @GetMapping("/web/profile")
    Map<String, String> webProfile(Principal principal) {
        return Map.of(
            "principal", principal.getName(),
            "mechanism", "form-login");
    }
}
```

### 11.5. Vì sao cấu hình này đúng chỗ?

1. `DemoApiKeyFilter` được tạo bằng `new ...` trong `apiChain`, không phải bean; Boot **không auto-register** nó ở container.
2. `@Order(1)` + `securityMatcher("/api/**")` chỉ chọn API chain cho machine endpoints.
3. `@Order(2)` bảo vệ web endpoints bằng session form login, không áp API-key filter lên `/login`.
4. `FilterProbe` là bean thường; nó chỉ chứa `AtomicInteger` nên không bị servlet auto-register.
5. Authentication failure của API key được catch trong filter và **return**. Không ném `BadCredentialsException` vượt qua filter sớm rồi trông chờ `ExceptionTranslationFilter`.
6. Không cần dùng `AuthenticationFailureHandler` của form login cho API key. Cấu hình API trả 401; form login có success/failure redirects do Spring quản lý.
7. `SecurityContext` được tạo mới khi key hợp lệ, xóa ở finally sau downstream. API chain dùng `NullSecurityContextRepository` và stateless session policy.
8. Business authorization là `hasAuthority("API_READ")`; provider tạo authority từ server, không dựa header.
9. `csrf.disable()` chỉ nằm trên **header API-key stateless chain** không dùng browser auto-attached session credential. Browser chain giữ CSRF mặc định.
10. Code không ghi raw API key, không trả secret qua JSON. Mã demo dùng SHA-256 digest và `MessageDigest.isEqual` với key có entropy cao; production cần key ID/rotation/revoke store và rate limits.

**Giới hạn:** ví dụ không có database để lưu key verifier, không hỗ trợ nhiều khóa, expiration hoặc tenant, và không đưa audit vào store bền vững. Không đưa thẳng khóa demo vào production.

## 12. Chạy local và quan sát đường đi

Chuẩn bị Maven, Java 17+ và OpenSSL; tạo key ngẫu nhiên cho một **lab local**:

```bash
export DEMO_API_KEY="$(openssl rand -hex 32)"
export DEMO_LOGIN_PASSWORD="$(openssl rand -hex 24)"
mvn spring-boot:run
```

Nếu sử dụng PowerShell trên Windows, thay cú pháp export bằng `$env:...` và cách sinh secret phù hợp. Không chụp màn hình, copy key vào ticket hoặc commit nó vào Git.

Thử API:

```bash
curl -i http://localhost:8080/health

curl -i http://localhost:8080/api/whoami \
  -H "X-Demo-Key: $DEMO_API_KEY"

curl -i http://localhost:8080/api/whoami

curl -i http://localhost:8080/api/whoami \
  -H "X-Demo-Key: invalid"
```

Kỳ vọng:

| Request | Authentication | Kết quả |
| --- | --- | --- |
| `GET /health` | Không bắt buộc | 200 + JSON `{"status":"up"}` |
| `GET /api/whoami` với đúng key | API provider thành công | 200 + `{"principal":"integration-reader","mechanism":"api-key"}` |
| `GET /api/whoami` thiếu header | Filter cho chain tiếp tục; authorization yêu cầu authenticated | 401 |
| `GET /api/whoami` key sai | Provider `BadCredentialsException`, filter trả 401 và dừng | 401 |
| `GET /web/profile` anonymous | Web chain + entry point | 302 tới trang login |
| Login browser learner bằng password lab rồi GET `/web/profile` | Form login/session | 200, JSON user learner |

Bản thân request tới `/health` và `/web/**` **không vào DemoApiKeyFilter**, vì API filter chỉ thuộc API chain. Với mỗi `GET /api/whoami` đơn giản trong một lượt `REQUEST`, `probe.markExecution()` dự kiến tăng **1**; hai HTTP requests thật làm tăng **2**.

**Cẩn thận:** app dùng Spring Security form login và random password qua env. Để login browser, password là giá trị chỉ có trong terminal lab. Không đặt nó vào URL query hoặc log. Với test tự động, dùng synthetic password fixture cố định không phải secret thật.

## 13. MockMvc: test một lần filter cho một request đơn giản

Tạo file `src/test/java/demo/filters/FilterDiagnosticsApplicationTests.java`:

```java
package demo.filters;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "app.demo.api-key=" +
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "app.demo.login-password=synthetic-local-test-password-123456"
})
@AutoConfigureMockMvc
class FilterDiagnosticsApplicationTests {

    private static final String VALID_KEY =
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

    @Autowired MockMvc mvc;
    @Autowired FilterProbe probe;

    @Test
    void validApiKeyIsAuthenticatedExactlyOnceForSingleRequest()
            throws Exception {
        int before = probe.count();

        mvc.perform(get("/api/whoami")
                .header("X-Demo-Key", VALID_KEY))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.principal")
                .value("integration-reader"));

        assertThat(probe.count()).isEqualTo(before + 1);
    }

    @Test
    void twoApiRequestsAreNotAFilterDuplicate() throws Exception {
        int before = probe.count();

        mvc.perform(get("/api/whoami")
                .header("X-Demo-Key", VALID_KEY))
            .andExpect(status().isOk());

        mvc.perform(get("/api/whoami")
                .header("X-Demo-Key", VALID_KEY))
            .andExpect(status().isOk());

        assertThat(probe.count()).isEqualTo(before + 2);
    }

    @Test
    void missingKeyIsRejectedByApiChain() throws Exception {
        int before = probe.count();

        mvc.perform(get("/api/whoami"))
            .andExpect(status().isUnauthorized());

        assertThat(probe.count()).isEqualTo(before + 1);
    }

    @Test
    void invalidKeyReturns401WithoutEnteringController()
            throws Exception {
        int before = probe.count();

        mvc.perform(get("/api/whoami")
                .header("X-Demo-Key", "not-a-valid-key"))
            .andExpect(status().isUnauthorized());

        assertThat(probe.count()).isEqualTo(before + 1);
    }

    @Test
    void webRequestDoesNotUseApiKeyFilter() throws Exception {
        int before = probe.count();

        mvc.perform(get("/web/profile"))
            .andExpect(status().is3xxRedirection());

        assertThat(probe.count()).isEqualTo(before);
    }

    @Test
    void formLoginAndFollowingSessionGetUseWebChain()
            throws Exception {
        int before = probe.count();

        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password",
                    "synthetic-local-test-password-123456"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
            login.getRequest().getSession(false);

        assertThat(session).isNotNull();

        mvc.perform(get("/web/profile").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.principal").value("learner"));

        assertThat(probe.count()).isEqualTo(before);
    }
}
```

Chạy:

```bash
mvn test
```

Kỳ vọng **6 test pass** nếu môi trường và dependencies phù hợp. Đây là kiểm tra **tĩnh** của ví dụ, không phải khẳng định đã thực thi Maven trong tác vụ Sheet.

**Quan trọng:** MockMvc là test mô phỏng Servlet request/filter chain trong Spring test context. Nó **không đủ để chứng minh** embedded container ngoài đời đã không auto-register cùng filter bean. Trong ví dụ, filter API không phải bean, vì vậy nguy cơ Boot auto-registration không có ngay từ thiết kế. Để test một app thực có bean filter, cần thêm integration test khởi động embedded server và inspect filter registrations thực tế.

**Hạn chế của counter:** `FilterProbe` tăng ở `doFilterInternal`. Nếu cùng một `OncePerRequestFilter` instance được gọi hai lần theo hai registration **lồng nhau**, already-filtered marker có thể khiến chỉ một `doFilterInternal` chạy, trong khi vẫn có **hai registrations**. Vì vậy counter xanh **không thay** kiểm tra container registration.

Nếu chạy test song song, probe là bean dùng chung; so sánh delta trước/sau có thể bị test khác xen vào. Fixture này giả định test không chạy parallel, hoặc cần probe/request-ID collector có scope riêng.

## 14. Integration diagnostics: kiểm tra instance, filter registration và dispatch

Một kế hoạch debug production-safe cần quan sát **từng lớp**, không chỉ thông điệp lỗi:

1. **Network:** có bao nhiêu HTTP requests? `OPTIONS`/`POST`, redirect, retries? Correlation ID có khác nhau không?
2. **Servlet container:** danh sách filter registrations có bean filter của app ngoài `springSecurityFilterChain` không?
3. **Spring Security:** có bao nhiêu `SecurityFilterChain`, matcher nào chọn request, filter list trong chain đó là gì?
4. **Custom filter:** filter instance identity, dispatch type, request method/path, thời điểm trước/sau chain.
5. **Authentication:** manager/provider có được gọi một lần hay nhiều lần? Có authentication success nhưng thiếu authority không?
6. **Authorization:** resource cần role/authority gì? Exception phát sinh ở đâu?
7. **HTTP response:** status cuối, response committed khi nào, ai gọi `sendError/sendRedirect/getWriter`?
8. **Async/error:** có request dispatch lại dưới `ERROR/ASYNC` không?
9. **Runtime:** một số app nodes có cùng registration/config/version không?
10. **Client:** frontend có double submit, retry, stale cookie hoặc token refresh race không?

### 14.1. Logging có kiểm soát

Ở local/dev, có thể thử:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.FilterChainProxy: TRACE
```

Tùy Spring Security release, TRACE có thể hiển thị danh sách và lượt gọi security filters. Chỉ bật trong môi trường **không log raw credentials**; giảm cấp log sau khi xử lý xong. Không bật HTTP wire tracing toàn bộ ở production.

**Log nên có:** request ID do server sinh, chain name/matcher, method, sanitized path, dispatcher type, filter class/identity và event category. **Không log:** `Authorization`, `Cookie`, `X-API-Key`, password, raw token, CSRF token, session ID hoặc full principal object.

Ví dụ log **minh họa**, không phải mặc định của Spring:

```text
request_id=req-319 method=GET path=/api/whoami dispatcher=REQUEST
chain=apiKey filter=DemoApiKeyFilter instance=0x5f11 phase=before
request_id=req-319 auth=SUCCESS principal_ref=integration-reader
request_id=req-319 phase=after status=200 committed=true
```

Nếu cùng request ID có **hai instance IDs**, nghi ngờ có hai instances cùng loại. Nếu một instance ID nhưng **hai registration paths**, cần inspect container và FilterChainProxy. Nếu cùng correlation ID nhưng dispatcher type khác, phân tích error/async lifecycle. Nếu hai **request IDs khác nhau**, có thể là client/gateway retry.

### 14.2. Liệt kê Servlet filter registrations

Trong một test/application được quản lý, có thể inspect `ServletContext.getFilterRegistrations()`:

```java
// Trích đoạn chạy trong Servlet application/integration test.
Map<String, ? extends FilterRegistration> registrations =
    servletContext.getFilterRegistrations();

registrations.forEach((name, registration) ->
    logger.debug("containerFilterName={} className={}",
        name, registration.getClassName()));
```

Imports: `jakarta.servlet.FilterRegistration`, `jakarta.servlet.ServletContext`, `java.util.Map`. Cần chú ý rằng registrations từ ServletContext cung cấp **container registrations**, còn danh sách Spring Security filters được lấy từ `FilterChainProxy`; hai danh sách này **không đồng nhất**. Đừng diễn giải mọi container filter là duplicate.

Trong integration test của app có bean filter, assert nó **không** nằm trong container registrations khi bạn đã chủ động disable auto-registration.

### 14.3. Inspect FilterChainProxy có kiểm soát

```java
// Trích đoạn trong integration test/tool chẩn đoán nội bộ.
@Autowired
FilterChainProxy proxy;

@Test
void listSecurityChainsForDiagnostics() {
    for (SecurityFilterChain chain : proxy.getFilterChains()) {
        System.out.println(chain);
    }
}
```

Imports: `org.springframework.security.web.FilterChainProxy` và `SecurityFilterChain`. Đoạn code là **trích đoạn riêng**, không nằm trong file test chính. Không exposed danh sách security configuration qua public endpoint.

### 14.4. Đặt log trước và sau chain đúng nghĩa

```java
long start = System.nanoTime();
try {
    logger.debug("filter before path={} dispatcher={}",
        request.getServletPath(), request.getDispatcherType());
    chain.doFilter(request, response);
} finally {
    logger.debug("filter after status={} committed={} tookNs={}",
        response.getStatus(), response.isCommitted(),
        System.nanoTime() - start);
}
```

Mã trích đoạn trên hữu ích cho request đồng bộ. Với async dispatch, `chain.doFilter` ở lượt đầu có thể kết thúc trước khi response của task hoàn tất; muốn đo toàn lifecycle phải dùng Servlet async listener/observability integration phù hợp. Đừng coi log “after” là confirmation đã gửi response tới client trong mọi trường hợp.

## 15. Bảng chẩn đoán triệu chứng → gốc rễ → cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Sửa đúng |
| --- | --- | --- |
| Custom filter log hai lần trên một REQUEST | `@Component` + `addFilter...` hoặc hai instances | Một registration owner; local filter hoặc disable Boot registration |
| Filter log một lần nhưng context sai | Filter thật ra chạy ngoài Security chain; already-filtered marker che double registration | Inspect container registration và security ordering |
| Filter chạy trên /login dù chỉ dành API key | Auto-registration container toàn servlet app | Tạo local filter trong API chain hoặc disable registration |
| Filter không chạy trên /api/** | Catch-all chain `@Order(1)` che API chain | Đặt specific chain trước, test matcher |
| API key đúng nhưng 403 | Thiếu authority/tenant permission | Kiểm tra authorization; không nhầm với authentication |
| API key đúng mà request sau anonymous | Stateless hoặc context không được save | Nếu muốn session, dùng repository explicit save; nếu stateless, authenticate từng request |
| Missing key trả 302 /login HTML | EntryPoint form login được áp vào API chain | JSON/HTTP 401 entry point hoặc đúng API chain |
| Invalid token làm 500 | Exception thoát khỏi custom filter nằm trước translation | Catch auth exception quanh manager hoặc dùng standard filter |
| POST /login sai password trả 403 | CSRF thiếu/sai, chưa tới login filter | Lấy/đính CSRF token; không sửa FailureHandler |
| CORS preflight OPTIONS trả 401 | Custom filter hoặc auth chặn OPTIONS trước CORS | Tích hợp CORS đúng thứ tự, không bỏ bảo vệ request thực |
| Controller chạy hai lần | `chain.doFilter` hai lần hoặc client retry | Review control flow + request IDs |
| JSON response sau đó lại redirect | Handler ghi response rồi code tiếp tục | Return ngay, chỉ một owner response |
| `IllegalStateException: response already committed` | Ghi response quá muộn sau downstream | Quyết định response trước commit hoặc wrapper được thiết kế |
| Filter chạy ở /error lần nữa | ERROR dispatch, sendError | Kiểm tra dispatcher types và OncePerRequestFilter hooks |
| Filter chạy lại trong async completion | ASYNC redispatch | Quy định shouldNotFilterAsyncDispatch/dispatcher mapping |
| User login một lần nhưng nhiều auth events | Multiple providers/parent managers, token reauth, client retries | Trace manager/outcomes; không kết luận filter duplicate |
| AOP/metrics log hai lần | Hai instrumentation paths hoặc duplicated events | Phân biệt filter invocation và metrics instrumentation |
| Filter không nhận session sau login | Chain order/NullSecurityContextRepository sai scope | Tách stateless API chain với stateful form chain |
| TenantFilter không thấy principal | Đặt trước authentication | Chuyển sau `AnonymousAuthenticationFilter` hoặc authorization layer |
| Service throws AccessDenied nhưng nhận 500 | Exception được ném trước ExceptionTranslationFilter hoặc outside security chain | Đặt policy đúng downstream/AuthorizationManager hoặc handler phù hợp |
| Development test pass, production fail | Embedded container registration, proxy path, error dispatch, Boot config khác | Embedded-server integration test, audit runtime setup |

## 16. Khi nào nên dùng filter, khi nào nên dùng framework extension?

**Một custom Servlet filter phù hợp** cho công việc thật sự liên quan request transport/authentication, ví dụ đọc một header API key và gọi `AuthenticationManager`. Nhưng không phải mọi logic phải đặt trong filter.

| Nhu cầu | Extension được ưu tiên |
| --- | --- |
| Đọc username/password và login browser | `formLogin()` / `UsernamePasswordAuthenticationFilter` |
| HTTP Basic | `httpBasic()` |
| Bearer JWT | `oauth2ResourceServer().jwt()`, `BearerTokenAuthenticationFilter` |
| OAuth2/OIDC login | `oauth2Login()` |
| Xác minh credentials tùy biến | `AuthenticationProvider` + filter/manager phù hợp |
| Yêu cầu role/permission theo resource | `AuthorizationManager` / `authorizeHttpRequests` / method security |
| Mở login khi anonymous | `AuthenticationEntryPoint` |
| Trả lỗi login attempt | `AuthenticationFailureHandler` |
| Trả lỗi thiếu quyền sau login | `AccessDeniedHandler` |
| Xử lý validation lỗi JSON trong controller | `@ControllerAdvice` / MVC exception resolver |
| Ghi audit sau authentication outcome | `AuthenticationEventPublisher` / listener phù hợp |
| Quan sát HTTP request lifecycle | Servlet filter/observability + async handling |

Càng ít custom filters, càng ít điểm có thể đăng ký trùng hoặc xử lý kết quả sai thứ tự. Nhưng **không thay thế kiểm chứng credentials bằng đọc header rồi gán role**. Nếu dùng custom filter, vẫn phải có verifier/provider tin cậy.

## 17. Điều kiện bảo mật của bản sửa

Một bản sửa “không còn chạy hai lần” **chưa đủ** nếu có những tác động sau:

1. **Không còn kiểm tra credential** trên một số endpoints vì matcher không bao phủ.
2. Thay 401 thành 200 bằng cách bỏ `chain.doFilter` hoặc `permitAll` rộng.
3. Tắt CSRF của formLogin chain để sửa lỗi POST/login.
4. Ghi API key/plaintext token vào log để debug.
5. Không xóa `SecurityContextHolder` trên thread pool sau custom stateless authentication.
6. Lưu Authentication của API key vào session dù policy yêu cầu stateless/revocation từng request.
7. Cho phép client cung cấp role/authority trực tiếp trong header.
8. Bỏ `AccessDeniedHandler` hoặc catch mọi exception rồi trả “bad key”.
9. Không xử lý CORS preflight nhưng chuyển security filter ra ngoài chain để né lỗi.
10. Dùng `ThreadLocal<Boolean> alreadyProcessed` tự tạo không clear trong finally, gây rò request state giữa các users.
11. Gán static boolean global để “chỉ chạy một lần” trên toàn JVM; sau request đầu, những request khác có thể bypass auth.
12. Phát 2 response bodies trên cùng request do code tiếp tục sau error/redirect.

**Một test âm tính tối thiểu:** key sai → 401; thiếu key → 401; key đúng nhưng thiếu quyền → 403; web anonymous → login redirect; web login đúng → vào protected endpoint; không có request path nào ngoài policy được trả 200.

## 18. Quy trình sửa lỗi theo thứ tự an toàn

### Bước 1 — Thu thập chứng cứ

Ghi nhận một request thực với ID riêng, method, normalized path, dispatcher type và status. Xác minh frontend có gửi bao nhiêu requests; có OPTIONS/redirect/retry/error dispatch không. Không log secrets.

### Bước 2 — Kiểm tra filter registrations

Tìm filter là `@Component`/`@Bean implements Filter` và có mặt trong `addFilterBefore/After/At` hay không. Nếu có, chọn **một owner**: local filter trong chain hoặc disable auto registration bằng `FilterRegistrationBean.setEnabled(false)`. Không sửa formatting/timeout để che dấu.

### Bước 3 — Xác định SecurityFilterChain được chọn

Kiểm tra `@Order`, `securityMatcher` và fallback chain. Đảm bảo API chain đặc thù đứng trước web catch-all; không để endpoint bảo mật thiếu chain.

### Bước 4 — Kiểm tra vị trí tương đối

Auth filter sau điểm thiết lập context/exploit protection phù hợp; authorization/tenant check sau khi authentication đã hoàn tất. Đừng đặt auth logic trong MVC controller nếu đã có Spring Security providers.

### Bước 5 — Kiểm tra control flow

Mỗi nhánh:
- Nếu reject: ghi một response theo contract rồi **return**.
- Nếu accept: thiết lập context đúng, gọi `chain.doFilter` **đúng một lần**, cleanup finally.
- Catch `AuthenticationException` chỉ quanh authentication work.
- Không ghi thêm response sau khi downstream commit.

### Bước 6 — Kiểm tra persistence đúng loại

Stateful login: session strategy và `SecurityContextRepository`. Stateless API: mỗi request tự xác thực, không để context của request trước sống sang request sau.

### Bước 7 — Viết regression tests

Unit tests cho provider/filter, MockMvc cho 401/403/login/chain; embedded-container integration test cho auto-registration; browser e2e cho preflight, redirect, cookies và retry; load test cho async/concurrency. Dùng negative-path tests để chắc sửa duplication không mở bypass.

### Bước 8 — Giám sát khi rollout

Theo dõi số calls tới provider, 401/403/5xx, duplicate request IDs, auth latency, filter invocation và bất thường session. So sánh trước/sau theo **HTTP request counts**, không chỉ nhìn log volume.

## 19. Câu hỏi tự kiểm tra

1. Vì sao `@Component` filter + `addFilterAfter` có thể tạo duplicate registration?
2. Nếu dùng `OncePerRequestFilter` thì có thể bỏ kiểm tra container registration không? **Không.**
3. Khi hai request `OPTIONS` và `POST` xuất hiện, đó có phải một request bị xử lý hai lần không? **Không.**
4. `FilterChainProxy` chạy tất cả SecurityFilterChains cùng khớp không? **Không, chọn chain khớp đầu tiên.**
5. `securityMatcher` khác `authorizeHttpRequests.requestMatchers` thế nào?
6. Vì sao catch bao quanh cả `chain.doFilter` có thể biến lỗi downstream thành “bad credentials”?
7. Vì sao sau `response.sendError(401)` thường phải `return`?
8. Hậu quả của việc gọi `chain.doFilter` hai lần trên nhánh success là gì?
9. Một Authentication thành công có đảm bảo endpoint trả 200 không? **Không; authorization có thể từ chối.**
10. Vì sao filter trước `ExceptionTranslationFilter` ném AuthException có thể ra 500?
11. Lỗi `POST /login` thiếu CSRF có thuộc `AuthenticationFailureHandler` không? **Thông thường không.**
12. Nếu user có session hợp lệ, GET /web/profile có cần gọi lại provider password không? **Thường không.**
13. Vì sao API key stateless filter cần xóa SecurityContext trong finally?
14. Khi nào nên dùng `FilterRegistrationBean.setEnabled(false)`?
15. Một log ở `REQUEST` và một log ở `ERROR` có chắc là duplicate filter bug không?
16. MockMvc count doFilterInternal = 1 có chứng minh embedded-container filter không bị auto-register không? **Không.**
17. Test nào giúp phát hiện catch-all chain đứng trước API chain?
18. Vì sao callback success của form login khác với cho API-key request đi tiếp vào controller?
19. Khi thiếu role admin, sửa auth filter để cấp role có phải giải pháp không? **Không; kiểm tra authorization policy và server-side authorities.**
20. Khi frontend retry request POST, nên xử lý idempotency ở đâu? **Ở hợp đồng/transaction nghiệp vụ, không bỏ auth ở filter.**

## 20. Tài liệu chính thức

- Spring Security 6.5 – Servlet Architecture, FilterChainProxy, custom filters và registration: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security – Current Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Framework 6.2 – OncePerRequestFilter Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Security – Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security – Form Login: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security – SecurityContext Persistence: https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html
- Spring Security – CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security – CORS: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security – MockMvc Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Boot – Servlet Web Applications and Filters: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Security – FilterChainProxy Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/FilterChainProxy.html
- Spring Security – ExceptionTranslationFilter Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html
