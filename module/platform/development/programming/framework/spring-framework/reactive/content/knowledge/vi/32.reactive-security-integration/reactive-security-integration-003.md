# Truy cập Principal và ReactiveSecurityContextHolder trong Spring WebFlux

## 1. Mục tiêu

Trong Spring WebFlux, một yêu cầu HTTP thường cần biết **ai đang gửi yêu cầu**, người đó đã được xác thực hay chưa và được phép thực hiện những thao tác nào. Spring Security cung cấp các abstraction `Principal`, `Authentication` và `SecurityContext`, đồng thời tích hợp với **Reactor Context** để danh tính hiện tại được truy cập đúng trong pipeline bất đồng bộ.

Bài học tập trung vào hai con đường lấy danh tính:

1. **Ở controller hoặc request handler:** nhận trực tiếp `java.security.Principal`, `Mono<Principal>`, `@AuthenticationPrincipal` hoặc gọi `ServerWebExchange.getPrincipal()`/`ServerRequest.principal()`.
2. **Trong service và chuỗi Reactor:** đọc `ReactiveSecurityContextHolder.getContext()`, lấy `Authentication`, dùng `getName()`, `getAuthorities()` rồi compose qua `map`, `flatMap`, `switchIfEmpty`.

Ta cũng tìm hiểu cách SecurityWebFilterChain đưa context vào subscriber, phân biệt authentication/authorization, xử lý anonymous, `contextWrite`, đổi thread/scheduler, bảo vệ method-level, kiểm thử bằng WebTestClient và StepVerifier, giới hạn truyền security context sang request HTTP khác, cùng một dự án Java 17+ chạy được.

**Điểm quan trọng nhất:** Trong WebFlux, **đừng coi `SecurityContextHolder` dùng ThreadLocal như nguồn danh tính đáng tin cậy cho mọi reactive callback**. Đối với một reactive sequence, dùng `ReactiveSecurityContextHolder` hoặc API lấy principal từ request; tuyệt đối không dùng tên người dùng do client tự gửi như bằng chứng authentication.

## 2. Phân biệt Principal, Authentication và SecurityContext

### 2.1. Principal: danh tính

`java.security.Principal` là interface đơn giản:

```java
public interface Principal {
    String getName();
}
```

Trong Spring WebFlux, `Principal` thường đại diện cho đối tượng đã được cơ chế security nhận diện. Tên trả bởi `getName()` có thể là username, subject của JWT hoặc một định danh khác, tùy authentication mechanism. Không nên tự giả định nó luôn là email hoặc database user ID.

### 2.2. Authentication: danh tính kèm trạng thái và quyền

Spring Security `Authentication` extends `Principal`. Nó bổ sung:

- `getPrincipal()`: đối tượng danh tính gốc, ví dụ `UserDetails`, `Jwt` hoặc `OAuth2User`.
- `getName()`: tên được tính theo token/principal hiện hành.
- `getAuthorities()`: tập `GrantedAuthority` đã được cấp.
- `isAuthenticated()`: trạng thái token đã qua bước authentication theo implementation.
- `getCredentials()`: credential liên quan; không ghi log, không trả vào JSON.
- `getDetails()`: thông tin phụ do provider lưu; không tự cho rằng an toàn để trả client.

Ví dụ bảng:

| Giá trị | Với HTTP Basic user alice | Với OAuth2 Resource Server |
| --- | --- | --- |
| Authentication | UsernamePasswordAuthenticationToken | Thường là JwtAuthenticationToken |
| Authentication.getName() | alice | Thường là sub của JWT, hoặc claim được cấu hình |
| Authentication.getPrincipal() | UserDetails implementation | Thường là Jwt |
| Authorities | ROLE_USER, ROLE_ADMIN nếu được cấp | Có thể là SCOPE_read, SCOPE_write hoặc authorities được map |
| Credentials | Credential/token nội bộ, có thể bị xóa | Không đưa credentials/bearer token vào response |

Một số hệ thống cấu hình custom principal. Do đó, cast `authentication.getPrincipal()` thành `UserDetails` chỉ đúng khi đã biết rõ authentication provider tạo kiểu đó.

### 2.3. SecurityContext: chứa Authentication

`SecurityContext` là container chứa `Authentication` hiện tại:

```java
SecurityContext context = ...;
Authentication authentication = context.getAuthentication();
```

`context.getAuthentication()` có thể là null. Context không tự cấp quyền; việc cho phép request/method phải do Spring Security authorization rules hoặc business authorization code có kiểm soát thực hiện.

### 2.4. Anonymous và “đã xác thực”

Trên endpoint công khai, có thể **không có context/authentication** hoặc có `AnonymousAuthenticationToken` do cơ chế anonymous của Spring Security tạo ra. Token anonymous có thể báo `isAuthenticated() == true` theo implementation; vì vậy không dùng mỗi `isAuthenticated()` để quyết định một người dùng thật đã đăng nhập.

Để quyết định quyền truy cập, ưu tiên:
- `authorizeExchange(...).authenticated()` tại SecurityWebFilterChain.
- `@PreAuthorize("isAuthenticated()")` hoặc biểu thức role/authority ở tầng method.
- `AuthenticationTrustResolver` nếu cần phân biệt anonymous/remember-me/full auth trong code.
- Quy tắc nghiệp vụ kiểm tra ownership/tenant, không chỉ tên principal.

Khi lấy danh tính để hiển thị, có thể chọn xử lý publisher rỗng bằng `switchIfEmpty`. Không tạo anonymous bằng một String “guest” rồi coi đó là user đã được xác thực.

## 3. Dòng chảy SecurityContext trong WebFlux

Spring Security dùng một chuỗi `WebFilter`; trong đó `SecurityWebFilterChain` định nghĩa authentication/authorization cho các HTTP exchanges.

Mô hình tổng quát:

```text
HTTP request
      |
      v
Spring Security WebFilter chain
      |
      +-- Lấy credentials / session / bearer token
      +-- Thực hiện authentication nếu có
      +-- Thi hành authorization theo URL/authority
      +-- Đưa SecurityContext vào Reactor Context
      |
      v
DispatcherHandler / Controller / HandlerFunction
      |
      +-- Principal / Mono<Principal>
      +-- @AuthenticationPrincipal
      +-- ServerWebExchange.getPrincipal()
      |
      v
Service reactive pipeline
      |
      +-- ReactiveSecurityContextHolder.getContext()
      +-- Authentication.getName()/getAuthorities()
      +-- @PreAuthorize trong reactive method security
      |
      v
Reactive publisher hoàn tất / response
```

Với ứng dụng WebFlux Security cấu hình đúng, `ReactorContextWebFilter` đóng vai trò cầu nối giúp SecurityContext được đọc theo subscriber/reactive pipeline. Nguồn xác thực có thể là HTTP Basic, form login, session, bearer JWT hoặc một authentication mechanism khác.

**Phân biệt lưu trữ và truy cập:**

- `ReactiveSecurityContextHolder` là API truy cập SecurityContext trong **Reactor Context**, không phải repository bền vững.
- `ServerSecurityContextRepository` quyết định load/save context giữa các request khi cơ chế ứng dụng yêu cầu. Ví dụ có repository dựa trên WebSession hoặc NoOp repository cho mô hình không lưu session.
- HTTP Basic thường gửi credential ở mỗi request; JWT resource server thường xác minh bearer token mỗi request. Dùng Context không tự tạo một phiên đăng nhập được giữ lâu dài.

**Thời điểm truy cập:** Reactor Context thuộc subscriber; code cần đọc nó khi pipeline được subscribe. Với các thao tác tạo publisher qua `flatMap`, `defer` hoặc operator khác, context đúng được truyền nếu chuỗi được compose và không bị tách subscription tùy tiện.

## 4. Cách 1 — Nhận Principal ngay tại WebFlux controller

Spring Framework WebFlux hỗ trợ `java.security.Principal` như một method argument. Vì có thể cần lấy danh tính bất đồng bộ, argument này cũng hỗ trợ reactive wrapper.

### 4.1. Principal trực tiếp

```java
@RestController
public class PrincipalController {

    @GetMapping("/me")
    public String me(Principal principal) {
        return principal.getName();
    }
}
```

Đây là **snippet minh họa controller**. Khi endpoint được cấu hình authenticated, principal tồn tại và getName() phù hợp để hiển thị username/subject. Tuy nhiên, principal không tự mang mọi authority hay custom claim.

### 4.2. Mono<Principal> để compose reactive

```java
@GetMapping("/me")
public Mono<String> me(Mono<Principal> principal) {
    return principal.map(Principal::getName);
}
```

Cách này phù hợp khi muốn giữ publisher trong reactive flow, không cần block() và không buộc phải đọc Reactor Context thủ công ngay trong controller.

Với route yêu cầu `authenticated()`, filter bảo vệ sẽ từ chối request thiếu credential trước khi controller xử lý. Ở route `permitAll()`, principal có thể không có; một Mono rỗng khác với lỗi đăng nhập. Đừng giả định Publisher luôn có một value.

### 4.3. Nhận Principal qua ServerWebExchange

```java
@GetMapping("/me/exchange")
public Mono<String> fromExchange(ServerWebExchange exchange) {
    return exchange.getPrincipal()
            .map(Principal::getName);
}
```

`ServerWebExchange.getPrincipal()` trả một Mono của Principal, có thể rỗng. Ưu điểm là method có thể đồng thời truy cập request attributes, request URL và response metadata. Nếu controller chỉ cần tên user, truyền trực tiếp `Mono<Principal>` đơn giản hơn.

### 4.4. Functional routing

Trong WebFlux functional endpoint, `ServerRequest.principal()` cũng trả publisher:

```java
@Bean
RouterFunction<ServerResponse> routes() {
    return RouterFunctions.route(
            RequestPredicates.GET("/functional/me"),
            request -> request.principal()
                    .flatMap(principal ->
                            ServerResponse.ok()
                                    .contentType(MediaType.TEXT_PLAIN)
                                    .bodyValue(principal.getName()))
    );
}
```

Đây là **snippet khai báo router bean**; project cần import các kiểu `RouterFunction`, `ServerResponse`, `RouterFunctions`, `RequestPredicates` và `MediaType`, đồng thời cấu hình security cho /functional/me.

### 4.5. Chọn API nào?

| Nhu cầu | Nên dùng |
| --- | --- |
| Chỉ lấy tên trong controller | Principal hoặc Mono<Principal> |
| Cần nhiều thông tin HTTP exchange | ServerWebExchange.getPrincipal() |
| Functional handler | ServerRequest.principal() |
| Muốn nhận chính Authentication.getPrincipal() | @AuthenticationPrincipal |
| Cần authorities/token ở controller | Authentication qua Reactor Context hoặc loại principal/token phù hợp |
| Cần identity trong service không phụ thuộc HTTP | ReactiveSecurityContextHolder |

Controller có thể lấy Principal, nhưng business service không nên phụ thuộc vào ServerWebExchange nếu không cần. Khi service cần danh tính ở nhiều nguồn gọi (HTTP, message listener, tests), `ReactiveSecurityContextHolder` hoặc truyền tham số identity đã xác minh là lựa chọn rõ ràng hơn.

## 5. Cách 2 — @AuthenticationPrincipal

Spring Security cung cấp `@AuthenticationPrincipal` để resolve **Authentication.getPrincipal()**, không phải toàn bộ `Authentication`.

Ví dụ với HTTP Basic và Spring Security `UserDetails`:

```java
@GetMapping("/me/annotation")
public Mono<String> annotated(
        @AuthenticationPrincipal UserDetails userDetails) {
    return Mono.just(userDetails.getUsername());
}
```

Ưu điểm: chữ ký method nói rõ cần domain principal type thay vì nhiều thao tác cast ở thân method.

### 5.1. Không nhầm với Authentication

Trong mặc định `UsernamePasswordAuthenticationToken`:

- `Authentication.getPrincipal()` có thể là `UserDetails`.
- `Authentication.getName()` là tên user.
- `Authentication.getAuthorities()` mới là nơi lấy granted authorities.

Nếu cần authorities, đừng suy ra chúng chỉ từ `UserDetails.getUsername()` hoặc một string role trong URL. Dùng Authentication/authorization policy.

### 5.2. JwtAuthenticationToken và OAuth2User

Khi dùng JWT resource server, principal thường là `Jwt`, không phải `UserDetails`:

```java
@GetMapping("/me/jwt")
public Mono<String> currentJwtSubject(
        @AuthenticationPrincipal Jwt jwt) {
    return Mono.just(jwt.getSubject());
}
```

Đây là **snippet chỉ dùng khi endpoint được bảo vệ bằng OAuth2 Resource Server JWT**. Cần starter và decoder/issuer configuration tương ứng; chỉ thêm annotation không biến HTTP Basic thành JWT auth.

Với OAuth2 Login, principal có thể là `OAuth2User` hoặc `OidcUser`. Hãy thiết kế code theo authentication mechanism thực tế, không giả định một kiểu principal duy nhất cho mọi môi trường.

### 5.3. Type mismatch và custom principal

Nếu `@AuthenticationPrincipal` khai báo kiểu không khớp với object thật, thông thường resolver trả null; có thể bật `errorOnInvalidType = true` để fail fast khi cấu hình sai:

```java
@GetMapping("/me/strict")
public Mono<String> strict(
        @AuthenticationPrincipal(errorOnInvalidType = true)
        UserDetails user) {
    return Mono.just(user.getUsername());
}
```

Ở route bảo vệ bằng HTTP Basic cùng UserDetails provider, ví dụ hoạt động. Nếu đổi sang JWT nhưng chưa đổi chữ ký, đoạn này giúp phát hiện sai kiểu thay vì null khó tìm nguyên nhân.

**Quan trọng:** Principal được Spring Security tạo từ cơ chế xác thực. Không đọc header `X-Username` do client gửi rồi cast hoặc tự coi đó là @AuthenticationPrincipal.

## 6. Cách 3 — ReactiveSecurityContextHolder trong service

Trong service phản ứng, không có ServerRequest hay Controller argument. Spring Security cung cấp:

```java
ReactiveSecurityContextHolder.getContext()
```

API trả `Mono<SecurityContext>` được truy xuất từ Reactor Context của subscriber.

### 6.1. Đọc Authentication và tên user

```java
public Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Objects::nonNull)
            .map(Authentication::getName);
}
```

Đây là snippet cần import `Objects`, `Mono`, `Authentication`, `SecurityContext` và `ReactiveSecurityContextHolder`.

- `getContext()` có thể hoàn tất rỗng nếu không có context.
- `getAuthentication()` có thể trả null; `filter(Objects::nonNull)` chỉ áp dụng sau map, nhưng Reactor `Mono.map` không cho emit null: nếu mapper trả null, Mono kết thúc rỗng theo hợp đồng Reactor. Do đó có thể dùng `flatMap(context -> Mono.justOrEmpty(context.getAuthentication()))` để diễn đạt rõ nullable semantics.
- `getName()` không đồng nghĩa user id của database và không phải giấy phép truy cập một record bất kỳ.

Phiên bản minh bạch hơn:

```java
public Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .flatMap(context ->
                    Mono.justOrEmpty(context.getAuthentication()))
            .map(Authentication::getName);
}
```

Nếu thiếu authentication, kết quả là Mono.empty(). Route bảo vệ bằng authenticated() phải được cấu hình để yêu cầu thật sự có user; service không tự thay thế authentication/authorization rules.

### 6.2. Lấy authorities

```java
public Mono<List<String>> currentAuthorities() {
    return ReactiveSecurityContextHolder.getContext()
            .flatMap(context ->
                    Mono.justOrEmpty(context.getAuthentication()))
            .map(auth -> auth.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList());
}
```

Cần import `List` và `GrantedAuthority`. Khi kiểm tra role, hãy phân biệt:
- `hasRole("ADMIN")` thường tìm authority `ROLE_ADMIN`.
- `hasAuthority("ROLE_ADMIN")` tìm đúng chuỗi `ROLE_ADMIN`.
- OAuth2 resource server có thể dùng `SCOPE_reports.read` theo authority mapping.

Không tạo role từ `getName()`, claim chưa xác minh, request body hoặc header không tin cậy.

### 6.3. Xử lý trường hợp thiếu context

```java
public Mono<String> requireUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .flatMap(context ->
                    Mono.justOrEmpty(context.getAuthentication()))
            .filter(auth -> auth.isAuthenticated()
                    && !(auth instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName)
            .switchIfEmpty(Mono.error(
                    new AccessDeniedException("Authenticated user required")));
}
```

Đoạn này **không thay thế SecurityWebFilterChain**: Spring Security xử lý 401/403 ở HTTP boundary dựa trên authentication, entry point và access denied handler. Trong business service, lỗi thể hiện yêu cầu không có danh tính hợp lệ; HTTP mapping thuộc security layer.

### 6.4. Tại sao không gọi block()?

Sai trong request reactive:

```java
String user = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .block();
```

`block()` tạo subscription độc lập, có thể không kế thừa Reactor Context của request và gây blocking trên event-loop. Đọc Context phải được compose bên trong pipeline:

```java
return ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .map(Authentication::getName)
        .flatMap(user -> orderService.findForOwner(user));
```

Đó là **snippet minh họa**, trong đó orderService.findForOwner trả Mono kết quả. Nếu có authorization phức tạp, vẫn cần xác minh ownership tại data access/query layer.

## 7. Vì sao Reactor Context quan trọng?

### 7.1. ThreadLocal không phải security context của reactive chain

Trong servlet imperative, `SecurityContextHolder` thường dùng ThreadLocal. Nhưng WebFlux có thể chạy nhiều request trên cùng event-loop, chuyển thread sau I/O, `publishOn` hoặc `subscribeOn`, và sử dụng worker pool.

Khi đó:

```java
Authentication auth = SecurityContextHolder
        .getContext()
        .getAuthentication();
```

không phải phương án đáng tin cậy để lấy đúng Authentication cho subscriber hiện tại của WebFlux. Giá trị có thể thiếu hoặc đến từ một thread context không như dự kiến.

Reactor Context gắn với subscriber/sequence. Spring Security reactive dùng context đó để danh tính tiếp tục đúng khi operator chạy trên scheduler khác.

### 7.2. Context đi từ subscriber về phía upstream

Reactor Context được cung cấp trong subscription; các `contextWrite(...)` áp dụng cho những operator ở phía upstream theo chiều subscribe. Ví dụ test ngoài HTTP:

```java
Authentication authentication =
        UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                "not-a-real-password",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));

Mono<String> pipeline = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        authentication));
```

Khi subscribe, pipeline emit `alice`. Đặt contextWrite ở cuối chain giúp phần getContext phía upstream đọc được Authentication.

**Không dùng withAuthentication để tự giả danh user trong production.** Đây là API hỗ trợ thiết lập context cho một subscriber đã tin cậy, có thể dùng trong test hoặc nơi framework đã xác thực danh tính. Tạo Authentication từ username client tự khai báo rồi đặt vào Context là lỗ hổng security.

### 7.3. Các API của ReactiveSecurityContextHolder

| API | Đầu ra | Ý nghĩa |
| --- | --- | --- |
| getContext() | Mono<SecurityContext> | Đọc security context từ Reactor Context |
| withAuthentication(Authentication) | Context | Tạo context chứa Authentication |
| withSecurityContext(Mono<? extends SecurityContext>) | Context | Tạo context chứa Mono của SecurityContext |
| clearContext() | Function<Context, Context> | Xóa security context trong phạm vi Reactor Context được áp dụng |

Ví dụ ngoài HTTP, khi có một Authentication đã xác minh:

```java
SecurityContext context = new SecurityContextImpl(authentication);

Mono<String> task = readCurrentUser()
        .contextWrite(ReactiveSecurityContextHolder
                .withSecurityContext(Mono.just(context)));
```

`readCurrentUser()` là publisher minh họa. `withAuthentication` là shortcut cho việc cung cấp Authentication; không cần tự tạo SecurityContextImpl trong trường hợp đơn giản.

### 7.4. clearContext không đồng nghĩa logout

```java
Mono<String> taskWithoutContext = readCurrentUser()
        .contextWrite(ReactiveSecurityContextHolder.clearContext());
```

Cách này xóa security context khỏi phạm vi của subscription ở upstream, không tự:
- Thu hồi access token JWT.
- Xóa cookie/session đang lưu.
- Gọi logout handler.
- Vô hiệu user ở identity provider.
- Ngăn request tiếp theo xác thực lại bằng HTTP Basic.

Logout/session/token revocation có quy trình và cấu hình riêng trong Spring Security.

## 8. Truyền context qua operator, nested publishers và scheduler

### 8.1. publishOn và subscribeOn

Trong pipeline Reactor được compose bình thường, context đi theo subscriber, không phụ thuộc một ThreadLocal cụ thể:

```java
Mono<String> result = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .publishOn(Schedulers.parallel())
        .map(String::toUpperCase)
        .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        authentication));
```

Đây là **snippet ngoài HTTP/test** cần imports tương ứng. Nó tạo kết quả `ALICE` với authentication trong ví dụ trước. Trong ứng dụng thật, context do Spring Security cung cấp; không nên chèn Authentication thủ công từ dữ liệu chưa xác thực.

### 8.2. Nested flatMap

```java
public Mono<String> loadForCurrentUser() {
    return Mono.just("start")
            .flatMap(ignored ->
                    ReactiveSecurityContextHolder.getContext())
            .flatMap(context ->
                    Mono.justOrEmpty(context.getAuthentication()))
            .map(Authentication::getName);
}
```

Do các inner publishers được compose bằng `flatMap` nên có thể truy cập subscriber Context. Quy tắc này khác với việc gọi subscribe() thủ công.

### 8.3. Lỗi mất context vì subscribe riêng

Sai:

```java
public Mono<String> bad() {
    ReactiveSecurityContextHolder.getContext()
            .subscribe(context -> audit(context));

    return Mono.just("ok");
}
```

`subscribe()` tạo một subscription riêng, không gắn trực tiếp với reactive chain của caller. Context, cancellation, error handling và lifecycle có thể không như mong muốn. Ngoài ra callback chạy lúc nào không được await.

Nên compose:

```java
public Mono<String> better() {
    return ReactiveSecurityContextHolder.getContext()
            .flatMap(context -> auditReactive(context))
            .thenReturn("ok");
}
```

Ở đây auditReactive(context) được giả định trả Mono<Void>. Trong production, audit cần reliability phù hợp; không dùng fire-and-forget tùy tiện cho yêu cầu audit quan trọng.

### 8.4. Những ranh giới cần chủ động xử lý

- Manual subscribe, CompletableFuture không được compose/bridge, callback từ SDK không hỗ trợ Reactor Context và công việc chạy ở executor ngoài Reactor có thể làm mất context.
- Reactor Context **không tự truyền qua network** sang WebClient, Kafka hay RSocket server khác.
- Reactor hỗ trợ Micrometer Context Propagation để bridge một số ThreadLocal khi cần; phải đăng ký accessor và chọn propagation mode đúng phiên bản. Không biến nó thành cách thay thế authorization.
- Khi cần danh tính ở một background job chạy sau request, hãy truyền **business identity đã được xác minh và dữ liệu cần thiết** dưới một contract rõ ràng; không giữ nguyên Authentication object tùy tiện qua thời gian dài.

## 9. Cấu hình Spring Security reactive đúng cách

Spring WebFlux có cấu hình tương ứng với Servlet stack nhưng dùng các API khác.

| Servlet/MVC | Reactive/WebFlux |
| --- | --- |
| HttpSecurity | ServerHttpSecurity |
| SecurityFilterChain | SecurityWebFilterChain |
| SecurityContextHolder ThreadLocal | ReactiveSecurityContextHolder |
| UserDetailsService | ReactiveUserDetailsService |
| AuthenticationManager | ReactiveAuthenticationManager |
| Servlet Filter chain | WebFilter chain |
| @EnableMethodSecurity | @EnableReactiveMethodSecurity |

Không dùng `HttpSecurity`/`SecurityFilterChain` của Servlet để cấu hình một ứng dụng WebFlux thuần. Khi dự án có cả MVC và WebFlux starter, Spring Boot có thể chọn servlet web application type; kiểm tra classpath và web-application-type trước khi chẩn đoán lỗi context.

### 9.1. SecurityWebFilterChain

Ví dụ quy tắc:
- GET /public không cần đăng nhập.
- /admin/** yêu cầu ROLE_ADMIN.
- Mọi route khác yêu cầu authenticated.
- HTTP Basic dùng cho demo.
- Form login tắt để những request không có credentials nhận 401 thay vì redirect về trang login.

```java
@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/public").permitAll()
                    .pathMatchers("/admin/**").hasRole("ADMIN")
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
}
```

Trong thực tế, thứ tự matcher quan trọng: các rule cụ thể nên đứng trước fallback. Trên route public, đừng kỳ vọng luôn tồn tại Authentication của user.

### 9.2. Method security

Bật `@EnableReactiveMethodSecurity` rồi annotate Spring-managed service:

```java
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> adminMessage() {
    return currentUsername().map(name -> "admin:" + name);
}
```

Reactive method security dùng Reactor Context. Với method được bảo vệ, trả `Mono`/`Flux` hoặc reactive Publisher tương thích để authorization gắn với subscription. Tránh nghĩ annotation tự hoạt động ở private method hoặc self-invocation không qua Spring proxy.

Khi method có tác dụng phụ, bố trí authorization **trước** thao tác ghi dữ liệu trong pipeline. Không thực thi side effect trước khi có quyết định authorization.

### 9.3. Trách nhiệm của code

Bảo vệ endpoint bằng `authenticated()` chỉ chứng minh user đã qua authentication. Nó **không bảo đảm user đó được phép xem bản ghi có ID X**. Ví dụ:

```java
@GetMapping("/orders/{id}")
public Mono<OrderDto> order(@PathVariable long id) {
    return identityService.currentUsername()
            .flatMap(name -> orderService.findOwnedBy(id, name));
}
```

Đây là snippet: findOwnedBy phải kiểm tra ownership từ nguồn dữ liệu đáng tin cậy và không trả record của tenant khác. Nếu JWT có tenant claim, claim phải được xác thực qua token validation/claim mapping; không lấy tenant ID không tin cậy rồi dùng làm quyền.

## 10. Ví dụ hoàn chỉnh: Java 17+ Spring Boot WebFlux Security

Dự án này cho thấy 3 cách lấy user:

1. `Mono<Principal>` trong WebFlux controller.
2. `@AuthenticationPrincipal UserDetails` trong controller.
3. `ReactiveSecurityContextHolder` trong service.

Dự án dùng HTTP Basic với hai user demo. Đối với production, thay bằng identity provider/OIDC, user store, TLS và quản lý secret an toàn.

### 10.1. Cấu trúc

```text
reactive-security-identity/
  settings.gradle
  build.gradle
  src/main/java/demo/security/
    IdentityApplication.java
    SecurityConfiguration.java
    IdentityView.java
    IdentityService.java
    IdentityController.java
  src/test/java/demo/security/
    IdentityServiceTest.java
    IdentityHttpTest.java
```

### 10.2. settings.gradle

```groovy
rootProject.name = 'reactive-security-identity'
```

### 10.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot quản lý Spring Framework, Spring Security và Reactor thông qua dependency management. Không trộn tùy ý version major Spring Security 7 vào ứng dụng Boot 3.5/Security 6.5.

### 10.4. IdentityApplication.java

```java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IdentityApplication {

    public static void main(String[] args) {
        SpringApplication.run(IdentityApplication.class, args);
    }
}
```

### 10.5. SecurityConfiguration.java

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin/**").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }
}
```

Trong ví dụ, `User.withUsername(...).roles("ADMIN")` tạo authority `ROLE_ADMIN`; `hasRole("ADMIN")` tìm cùng authority đó. Password được encoder xử lý, khác với việc lưu raw password bằng {noop}. Tuy nhiên demo credentials hardcode **không phù hợp production**.

Không tắt CSRF mặc định chỉ vì demo HTTP Basic. Các endpoint minh họa đều là GET; nếu thêm POST/PUT/DELETE trong ứng dụng browser có cookie/session, phải thiết kế CSRF đúng.

### 10.6. IdentityView.java

```java
package demo.security;

import java.util.List;

public record IdentityView(
        String name,
        List<String> authorities) {
}
```

DTO chỉ chứa tên và danh sách authorities phục vụ demo. Không trả raw Authentication hoặc SecurityContext cho client vì chúng có thể chứa credentials, token và dữ liệu nội bộ.

### 10.7. IdentityService.java

```java
package demo.security;

import java.util.List;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class IdentityService {

    public Mono<IdentityView> currentIdentity() {
        return ReactiveSecurityContextHolder.getContext()
                .flatMap(context ->
                        Mono.justOrEmpty(context.getAuthentication()))
                .filter(authentication ->
                        authentication.isAuthenticated()
                                && !(authentication
                                    instanceof AnonymousAuthenticationToken))
                .map(authentication ->
                        new IdentityView(
                                authentication.getName(),
                                authentication.getAuthorities()
                                        .stream()
                                        .map(GrantedAuthority::getAuthority)
                                        .sorted()
                                        .toList()))
                .switchIfEmpty(Mono.error(
                        new AccessDeniedException(
                                "Authenticated user required")));
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> adminGreeting() {
        return currentIdentity()
                .map(identity -> "admin:" + identity.name());
    }
}
```

Điểm chính:
- `getContext()` đọc Reactor Context theo subscriber.
- `flatMap(Mono.justOrEmpty(...))` xử lý `Authentication` có thể null.
- Filter loại token anonymous để tránh xem guest là authenticated user.
- `getAuthorities()` được chuyển sang danh sách string đã sắp xếp, không trả cả token.
- Method adminGreeting có `@PreAuthorize`, chạy qua Spring proxy vì được controller gọi từ bean khác.

`AccessDeniedException` ở service cho biết không có danh tính hợp lệ. Quy tắc trả 401 hay 403 ở HTTP là trách nhiệm security chain/entry point/handler.

### 10.8. IdentityController.java

```java
package demo.security;

import java.security.Principal;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class IdentityController {

    private final IdentityService identityService;

    public IdentityController(IdentityService identityService) {
        this.identityService = identityService;
    }

    @GetMapping("/public")
    public Mono<String> publicMessage() {
        return Mono.just("public");
    }

    @GetMapping("/me/principal")
    public Mono<String> principal(Mono<Principal> principal) {
        return principal.map(Principal::getName);
    }

    @GetMapping("/me/annotation")
    public Mono<String> annotation(
            @AuthenticationPrincipal UserDetails userDetails) {
        return Mono.just(userDetails.getUsername());
    }

    @GetMapping("/me/context")
    public Mono<IdentityView> context() {
        return identityService.currentIdentity();
    }

    @GetMapping("/admin/greeting")
    public Mono<String> adminGreeting() {
        return identityService.adminGreeting();
    }
}
```

`/me/principal` lấy tên từ method argument; `/me/annotation` chỉ chạy đúng với provider tạo UserDetails; `/me/context` đi qua service để đọc SecurityContext. Route `/admin/greeting` đồng thời được bảo vệ bởi URL security rule và reactive method security.

### 10.9. Chạy thử

Chạy qua Gradle wrapper nếu project đã tạo wrapper:

```bash
./gradlew bootRun
```

Hoặc `gradle bootRun` nếu máy đã cài Gradle. Nếu chỉ có hai tệp Gradle trong ví dụ, có thể tạo wrapper bằng `gradle wrapper` trước.

Các lệnh HTTP:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me/principal
curl -i -u alice:demo-pass http://localhost:8080/me/principal
curl -i -u alice:demo-pass http://localhost:8080/me/annotation
curl -i -u alice:demo-pass http://localhost:8080/me/context
curl -i -u alice:demo-pass http://localhost:8080/admin/greeting
curl -i -u admin:admin-pass http://localhost:8080/admin/greeting
```

Kết quả chính:

| Request | Status mong đợi | Response body nếu thành công |
| --- | --- | --- |
| GET /public không credentials | 200 | public |
| GET /me/principal không credentials | 401 | Unauthorized |
| GET /me/principal với alice | 200 | alice |
| GET /me/annotation với alice | 200 | alice |
| GET /me/context với alice | 200 | JSON với name=alice và authorities chứa ROLE_USER |
| GET /admin/greeting với alice | 403 | Forbidden |
| GET /admin/greeting với admin | 200 | admin:admin |

Lưu ý: HTTP Basic truyền username/password theo header Authorization đã mã hóa Base64, **không phải mã hóa bí mật**. Luôn dùng HTTPS trong production. Không ghi log raw Authorization header hoặc credentials.

## 11. Kiểm thử ReactiveSecurityContextHolder bằng StepVerifier

Có thể kiểm thử service mà không chạy HTTP server. Trong unit test, sử dụng một Authentication **do test tạo** rồi đặt vào Reactor Context.

Tệp `src/test/java/demo/security/IdentityServiceTest.java`:

```java
package demo.security;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class IdentityServiceTest {

    private final IdentityService service = new IdentityService();

    private Authentication user() {
        return UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                "test-credential",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Test
    void currentIdentityReadsReactorContext() {
        Mono<IdentityView> result = service.currentIdentity()
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                user()));

        StepVerifier.create(result)
                .expectNext(new IdentityView(
                        "alice",
                        List.of("ROLE_USER")))
                .verifyComplete();
    }

    @Test
    void missingContextDoesNotFabricatePrincipal() {
        StepVerifier.create(service.currentIdentity())
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void identitySurvivesSchedulerHandoff() {
        Mono<String> result = Mono.just("start")
                .publishOn(Schedulers.parallel())
                .flatMap(ignored -> service.currentIdentity())
                .map(identity -> identity.name().toUpperCase())
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                user()));

        StepVerifier.create(result)
                .expectNext("ALICE")
                .verifyComplete();
    }

    @Test
    void clearContextIsNotLogoutButHidesContextHere() {
        Mono<IdentityView> result = service.currentIdentity()
                .contextWrite(ReactiveSecurityContextHolder.clearContext())
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                user()));

        StepVerifier.create(result)
                .expectError(AccessDeniedException.class)
                .verify();
    }
}
```

Giải thích thứ tự `contextWrite` trong test cuối: context chứa user được cung cấp ở downstream, rồi `clearContext` gần `currentIdentity` hơn theo chiều subscription nên phần upstream không thấy key. Test không hề thực hiện HTTP logout hoặc hủy token.

**Giới hạn của unit test:** Những test trên xác minh Reactor Context, không chứng minh HTTP Basic được parse đúng, SecurityWebFilterChain được áp dụng, hoặc Spring AOP method security đã được bật. Cần thêm HTTP integration test.

## 12. Kiểm thử HTTP và authorization bằng WebTestClient

Tệp `src/test/java/demo/security/IdentityHttpTest.java`:

```java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class IdentityHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicRouteNeedsNoAuthentication() {
        client.get()
                .uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void protectedRouteRejectsAnonymousRequest() {
        client.get()
                .uri("/me/principal")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void principalAndAnnotationResolveBasicUser() {
        client.get()
                .uri("/me/principal")
                .headers(h -> h.setBasicAuth("alice", "demo-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("alice");

        client.get()
                .uri("/me/annotation")
                .headers(h -> h.setBasicAuth("alice", "demo-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("alice");
    }

    @Test
    void reactiveServiceReadsAuthenticatedContext() {
        client.get()
                .uri("/me/context")
                .headers(h -> h.setBasicAuth("alice", "demo-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("alice")
                .jsonPath("$.authorities[0]")
                    .isEqualTo("ROLE_USER");
    }

    @Test
    void nonAdminCannotAccessAdminRoute() {
        client.get()
                .uri("/admin/greeting")
                .headers(h -> h.setBasicAuth("alice", "demo-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdminRoute() {
        client.get()
                .uri("/admin/greeting")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin:admin");
    }
}
```

Chạy:

```bash
./gradlew test
```

Với `RANDOM_PORT`, test mở HTTP server thật và gửi credential Basic ở mỗi request. Nó kiểm tra danh tính đi qua authentication filter tới controller, service và method security. Không cần giả định test thread chia sẻ Reactor Context với server thread.

### 12.1. Khi nào dùng mockUser?

Spring Security Test có thể dùng:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

WebTestClient mockClient = WebTestClient
        .bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();

mockClient.mutateWith(mockUser("alice").roles("USER"))
        .get()
        .uri("/me/principal")
        .exchange()
        .expectStatus().isOk();
```

Đây là snippet mock-bound test, cần `ApplicationContext context` được inject từ Spring test. Khi dùng `@SpringBootTest(RANDOM_PORT)` gửi request tới một server thực, `@WithMockUser` trên test thread **không thay thế** HTTP authentication trên server thread. Trong live HTTP integration test, gửi Authorization header hoặc token thật/test issuer như ví dụ trên.

### 12.2. Test JWT/OAuth2 khác với Basic

Khi chuyển sang resource server, nên dùng `mockJwt()` cho test mock-bound hoặc JWT test token hợp lệ với issuer/decoder thử nghiệm cho HTTP end-to-end. `mockUser()` không tạo được đầy đủ JwtAuthenticationToken/claims nếu code đang dùng `@AuthenticationPrincipal Jwt`.

Đừng dùng `@WithMockUser` để “chứng minh” JWT signature validation đã thành công: nó bỏ qua xác minh chữ ký thật.

## 13. Authenticated, authority và business authorization

Đọc username không tự động chứng minh người đó được phép xem dữ liệu.

### 13.1. Authentication

Trả lời “ai đang yêu cầu?” và “credentials có hợp lệ không?”. Spring Security thực hiện qua filter, AuthenticationManager, ReactiveUserDetailsService, JWT decoder hoặc provider khác.

### 13.2. Request-level authorization

Quy tắc security ở `SecurityWebFilterChain` quyết định path/method có được phép hay không:

```java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/public").permitAll()
        .pathMatchers("/admin/**").hasRole("ADMIN")
        .anyExchange().authenticated())
```

`authenticated()` không đủ cho các API đọc dữ liệu nhạy cảm theo từng owner.

### 13.3. Method-level authorization

`@PreAuthorize` trên Spring bean (đã bật reactive method security) giới hạn quyền theo vai trò/authority:

```java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public Mono<Report> readReport(String reportId) {
    return repository.findById(reportId);
}
```

Đây là snippet OAuth2 resource server (giả sử đã map scope thành authority đúng); không phải mọi token đều có SCOPE_reports.read.

### 13.4. Object-level authorization

Ví dụ user alice truy cập `/users/bob/orders/1`. Dù alice đã authenticated, quyền của alice không được suy từ việc đã đăng nhập. Repository/service phải so sánh owner/tenant được tin cậy:

```java
public Mono<Order> currentUsersOrder(long orderId) {
    return currentUsername()
            .flatMap(username ->
                    repository.findByIdAndOwner(
                            orderId, username));
}
```

Đây là snippet phụ thuộc repository, không phải project demo đầy đủ. Nếu username có thể đổi, nên dùng stable subject/userId đã xác minh thay vì name hiển thị.

## 14. SecurityContext và outbound WebClient

Một call từ server A tới server B có hai phạm vi security khác nhau:

```text
Client ----Bearer/Basic----> Service A
             |
             v
    Authentication trong Reactor Context của A
             |
             v
       WebClient gọi Service B
             |
             v
    HTTP headers/token mới tại B
             |
             v
    B tự xác thực và tạo SecurityContext của B
```

**Reactor Context không tự truyền qua HTTP.** Service B không thể đọc SecurityContextHolder của A từ bộ nhớ của A. Nếu cần **on-behalf-of** user, dùng OAuth2 client token relay/delegation hoặc token exchange với phạm vi và audience đúng. Đừng lấy `Authentication.toString()`/raw credentials rồi gửi qua header tùy ý.

Một WebClient filter có thể đọc reactive Context nếu được compose trong cùng subscription, nhưng việc đặt Authorization header phải tuân thủ hệ thống identity và trust boundaries:

```java
Mono<String> result = identityService.currentIdentity()
        .flatMap(identity ->
                webClient.get()
                        .uri("/reports")
                        .retrieve()
                        .bodyToMono(String.class));
```

Snippet minh họa cho thấy Reactor Context của caller có thể truy cập trong nested chain. Dữ liệu từ `identity` **không tự trở thành header** gửi sang /reports. Không dùng tên user do code đọc được để giả danh user ở downstream; phải xác thực thông qua credential/token do hệ thống tin cậy cấp.

## 15. Anonymous, permitAll và xử lý Mono.empty()

### 15.1. Trang public

Route `permitAll()` cho phép không cần authentication. Khi đó `ReactiveSecurityContextHolder.getContext()` có thể empty, hoặc chứa anonymous Authentication. Tránh:

```java
return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .defaultIfEmpty("anonymous");
```

Nếu dùng giá trị “anonymous” để **hiển thị** thì có thể được, nhưng không dùng nó để phân quyền hoặc truy cập dữ liệu riêng. Nếu cần xác định đúng anonymous, dùng Spring Security trust resolver hoặc loại token, và policy rõ ràng.

### 15.2. Protected route

Route bắt buộc authenticated thường được filter từ chối trước controller; đừng viết code kỳ vọng `getContext()` tự phát lỗi 401. `Mono.empty()` chỉ là publisher không có giá trị; HTTP status phụ thuộc nơi bạn xử lý nó và SecurityWebFilterChain.

### 15.3. Principal có thể là một kiểu khác

Nếu dùng JWT, OIDC, pre-authentication hoặc custom principal, `getName()` và `getPrincipal()` có thể khác nhau về ngữ nghĩa. Chọn một **stable user key** rõ ràng từ nguồn xác thực đáng tin cậy. Không parse tên khỏi token bằng Base64 mà không verify signature, issuer, audience, expiry và các yêu cầu khác.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi SecurityContextHolder.getContext() trong reactive callback | Thiếu/sai user do ThreadLocal | Dùng ReactiveSecurityContextHolder |
| Gọi block() để lấy context | Blocking hoặc subscription riêng không có context | Compose map/flatMap |
| Gọi subscribe() thủ công trong service | Context/lỗi/cancel bị tách | Return publisher, compose chain |
| Dùng username từ HTTP header làm Principal | Có thể giả danh user | Chỉ tin Authentication đã được xác minh |
| Cast getPrincipal() thành UserDetails cho JWT | ClassCastException hoặc null | Dùng loại principal thực tế |
| Nhầm @AuthenticationPrincipal với Authentication | Không lấy được authorities | Đọc Authentication/ReactiveSecurityContextHolder |
| Nghĩ isAuthenticated() loại anonymous | Có thể chấp nhận anonymous sai | Dùng trust resolver hoặc security authorization |
| Nghĩ Mono.empty() tự thành 401 | Không có HTTP authentication flow | Đặt authenticated() trong SecurityWebFilterChain |
| Đặt contextWrite sai vị trí | Upstream không đọc thấy context | Kiểm tra chiều subscriber và operator scope |
| Nghĩ contextWrite tự đăng nhập user | Có thể tự giả danh sai | Chỉ dùng withAuthentication với identity tin cậy/test |
| Nghĩ clearContext() logout | Cookie/token vẫn còn hiệu lực | Dùng security logout/session/token revocation |
| @PreAuthorize ở private/self method | Không đi qua proxy | Đặt method public ở Spring bean, gọi qua proxy |
| Dùng method security synchronous cho publisher | Authorization không gắn đúng lifecycle | Dùng @EnableReactiveMethodSecurity và Mono/Flux |
| Dùng HttpSecurity trong WebFlux thuần | Cấu hình sai stack | Dùng ServerHttpSecurity |
| Nghĩ SecurityContext tự gửi qua WebClient | Service B không có identity của A | Dùng token relay/delegation hợp lệ |
| Expose raw Authentication trong JSON/log | Rò credentials/token/details | DTO giới hạn field |
| Chỉ test @WithMockUser trên live server | Không xác thực HTTP request thật | Gửi Basic/JWT test token |
| Chỉ có authenticated(), không kiểm tra owner | IDOR/BOLA | Kiểm tra record ownership/tenant trong service |
| Tự set ROLE_ADMIN dựa vào input user | Privilege escalation | Authorities phải đến từ nguồn xác thực/authorization đáng tin |
| Token hết hạn nhưng job giữ Authentication cũ | Dùng thông tin quyền không còn cập nhật | Thiết kế auth context và job boundary riêng |

## 17. Vấn đề an toàn và production

### 17.1. Không ghi credentials, token hoặc principal object đầy đủ vào log

Authentication.getCredentials(), JWT token value, cookie/session ID và đôi khi getDetails() chứa thông tin nhạy cảm. Log nên ưu tiên request ID, route, status và stable subject đã pseudonymize khi cần. Tránh `log.info("auth={}", authentication)` nếu chưa có chính sách redaction.

### 17.2. TLS là bắt buộc cho credential thực

HTTP Basic gửi credentials theo Base64, không bảo mật khi không có HTTPS. Browser session/OAuth2 cũng yêu cầu secure cookies, redirect URI, issuer/audience validation và các cơ chế bảo vệ thích hợp.

### 17.3. CSRF, CORS và authentication là các quyết định khác nhau

CSRF bảo vệ các yêu cầu browser có credential tự gửi (như cookies). CORS quyết định cross-origin reads trong browser. Không tắt CSRF/CORS hoặc coi CORS là authentication; chọn policy theo client/credential thực tế.

### 17.4. Tách identity và authorization

Identity là “người này là ai”; authority/role là quyền được cấp; ownership/tenant policy là quy tắc ứng dụng. Không đủ an toàn khi chỉ check đã authenticated.

### 17.5. Không đẩy mutable Authentication vào static field

Bean singleton phục vụ nhiều request đồng thời. Nếu lưu current user vào field mutable, request A có thể đọc user của request B. Context phải gắn với subscription và không rò giữa các request.

### 17.6. Không tin yêu cầu có header X-User

Proxy có thể thêm header identity trong một trust boundary đã được xác minh, nhưng backend phải đảm bảo header chỉ có thể được gateway tin cậy đặt và incoming value từ bên ngoài bị loại bỏ. Trong kiến trúc thông thường, dùng Bearer token/JWT hoặc authenticated session do Spring Security quản lý.

## 18. Checklist triển khai

1. Ứng dụng chạy WebFlux reactive hay MVC servlet? Có cấu hình SecurityWebFilterChain đúng stack không?
2. Authentication mechanism là Basic, session, OAuth2 login, JWT resource server hay custom?
3. Controller chỉ cần getName()? Dùng Principal/Mono<Principal> đơn giản nhất chưa?
4. Có cần actual Authentication.getPrincipal() không? Dùng @AuthenticationPrincipal và khai báo đúng kiểu chưa?
5. Service cần context? Dùng ReactiveSecurityContextHolder.getContext() trong publisher chưa?
6. Đã xử lý context empty, authentication null và anonymous đúng chưa?
7. Có dùng SecurityContextHolder ThreadLocal, block() hoặc subscribe() trong reactive path không?
8. contextWrite nằm ở vị trí đúng để publisher upstream đọc được context không?
9. Có manual executor/background job cần explicit propagation/identity contract không?
10. Request security rules có deny unknown routes hoặc authenticated() hợp lý không?
11. Method security có bật và các method chạy qua proxy với Mono/Flux không?
12. Route có kiểm tra role/authority và object-level ownership/tenant không?
13. Principal từ JWT/OIDC có đúng kiểu và stable ID được xác minh không?
14. Outbound WebClient có dùng token relay/delegation đúng thay vì chuyển raw identity header không?
15. Tests có cả missing auth, wrong authority, correct authority, context propagation, anonymous cases không?
16. Không trả credentials/token/raw Authentication qua API hoặc log?
17. TLS, secure session, CSRF/CORS, logout/revocation đã được thiết kế riêng theo threat model?

## 19. Tóm tắt API

| Nhu cầu | API phù hợp |
| --- | --- |
| Danh tính trong annotated WebFlux controller | Principal / Mono<Principal> |
| Principal gốc trong controller | @AuthenticationPrincipal |
| Danh tính trong ServerWebExchange | exchange.getPrincipal() |
| Danh tính trong functional handler | request.principal() |
| Đọc SecurityContext của subscriber | ReactiveSecurityContextHolder.getContext() |
| Gắn Authentication cho subscriber đáng tin cậy/test | ReactiveSecurityContextHolder.withAuthentication(auth) |
| Gắn Mono<SecurityContext> | withSecurityContext(mono) |
| Xóa context cho upstream của một subscription | clearContext() + contextWrite |
| Đặt security rules cho HTTP routes | SecurityWebFilterChain, ServerHttpSecurity |
| Phân quyền theo method reactive | @EnableReactiveMethodSecurity, @PreAuthorize |
| Lấy username | Authentication.getName() |
| Lấy authorities | Authentication.getAuthorities() |
| Nhận raw principal object | Authentication.getPrincipal() |
| Test reactor context | StepVerifier + withAuthentication |
| Test HTTP authentication | WebTestClient + Basic/JWT test credential |
| Mock authentication trong mock WebFlux tests | springSecurity() + mockUser()/mockJwt() |

## 20. Tài liệu tham khảo chính thức

- [Spring Framework – WebFlux Controller Method Arguments](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html): hỗ trợ Principal và reactive wrappers trong annotated controller.
- [Spring Security – ReactiveSecurityContextHolder Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): getContext, withSecurityContext, withAuthentication và clearContext.
- [Spring Security – Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context và @EnableReactiveMethodSecurity, @PreAuthorize.
- [Spring Security – Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): authorizeExchange, authenticated, hasRole và security rules.
- [Spring Security – WebTestClient Testing Authentication](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): mockUser, WithMockUser, test authentication.
- [Spring Security – WebTestClient Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): bindToApplicationContext, springSecurity().
- [Spring Security – @AuthenticationPrincipal](https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html#mvc-authentication-principal): giải thích annotation và access Authentication.getPrincipal(), lưu ý tài liệu minh họa ở servlet nhưng annotation cũng dùng trong WebFlux.
- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): RANDOM_PORT, mock environment và WebTestClient.
- [Project Reactor – Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Context, ContextView, deferContextual, contextWrite và subscriber lifecycle.

## 21. Ghi nhớ

**Principal cho biết tên danh tính; Authentication chứa principal và quyền; SecurityContext chứa Authentication.** Trong WebFlux, controller có thể nhận `Principal`/`Mono<Principal>` hoặc `@AuthenticationPrincipal`. Trong reactive service, cách đúng để đọc Authentication của subscriber là `ReactiveSecurityContextHolder.getContext()`.

SecurityContext được truyền bằng Reactor Context, không phụ thuộc vào một ThreadLocal đơn lẻ; nó không tự lan qua HTTP, không biến username do client gửi thành danh tính đã xác thực, và không thay thế authorization. Bảo vệ route bằng SecurityWebFilterChain, bảo vệ method bằng reactive method security khi cần, kiểm tra quyền sở hữu dữ liệu ở business layer và xác nhận hành vi bằng WebTestClient cùng StepVerifier.
