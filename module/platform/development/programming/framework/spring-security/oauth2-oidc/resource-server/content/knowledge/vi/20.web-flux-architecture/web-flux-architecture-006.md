# SecurityContext trong chuỗi phản ứng khác với ThreadLocal của Servlet

Trong ứng dụng **Spring MVC Servlet**, developer thường đọc caller đang đăng nhập qua `SecurityContextHolder.getContext().getAuthentication()`. Cách viết này có thể hoạt động vì một request đồng bộ thường được xử lý trong một thread, còn Spring Security giữ ngữ cảnh bảo mật theo chiến lược `ThreadLocal` mặc định. Khi chuyển sang **Spring WebFlux + Reactor**, cùng một giả định dễ dẫn đến lỗi: một request có thể tiếp tục thực thi trên nhiều thread, nhiều publisher có thể được kết hợp, và việc xử lý diễn ra **khi có subscription**, không nhất thiết tại lúc controller tạo `Mono`/`Flux`.

WebFlux sử dụng **Reactor Context** để mang `SecurityContext` xuyên qua một *reactive chain*. API chính để truy cập là **`ReactiveSecurityContextHolder`**, không phải `SecurityContextHolder` imperative. Reactor Context gắn với **subscription và chuỗi toán tử**, không gắn cố định vào một thread. Nếu đặt sai `contextWrite`, tự gọi `subscribe()`, tách khỏi chuỗi hoặc đưa công việc sang cơ chế không giữ Reactor Context, danh tính có thể không còn ở nơi cần kiểm tra quyền.

Bài học giải thích cách phân biệt hai mô hình, cách Spring Security xác thực Bearer JWT/opaque token trong WebFlux, cách đọc và truyền principal an toàn trong `Mono`/`Flux`, những lỗi do ranh giới subscription, cách quản lý `WebSession`, method security reactive và kỹ thuật kiểm thử context propagation. Các ví dụ dùng **Spring Boot 3, Spring Security 6, Reactor và Spring WebFlux**. Một số bean/phương thức phụ thuộc phiên bản, vì vậy cần chọn dependency nhất quán với Spring Boot đang chạy.

## 1. Mục tiêu của bài học

Sau bài này, người học cần phân biệt được:

1. `ThreadLocal` mặc định của Servlet và **subscriber context** của Reactor.
2. `SecurityContextHolder` và **`ReactiveSecurityContextHolder`**.
3. `SecurityFilterChain` / `HttpSecurity` với **`SecurityWebFilterChain` / `ServerHttpSecurity`**.
4. `JwtDecoder` với **`ReactiveJwtDecoder`**, `OpaqueTokenIntrospector` với **`ReactiveOpaqueTokenIntrospector`**.
5. `HttpSession` và **`WebSession`**, cũng như sự khác biệt giữa session và context của một subscription.
6. Việc `publishOn`/`subscribeOn` **không mặc nhiên làm mất Reactor Context**, còn việc tự tạo subscription hoặc rời Reactor pipeline có thể làm mất nó.
7. Cách kiểm thử authority, principal, publisher composition và JWT validation mà không nhầm JWT giả lập với JWT ký thật.

**Nguyên tắc xuyên suốt:** WebFlux không “không có SecurityContext”; nó có SecurityContext nhưng **cơ chế mang context khác Servlet**, nên code imperative quen thuộc không phải cách đọc principal mặc định trong pipeline reactive.

## 2. Servlet: vì sao `ThreadLocal` có vẻ tự nhiên?

Luồng Servlet truyền thống có thể hình dung:

```text
HTTP request
    |
Servlet Filter Chain
    |
Spring Security thiết lập SecurityContext
    |
Thread xử lý request
    |
Controller -> Service -> Repository
    |
Spring Security dọn SecurityContext
```

Trong cấu hình phổ biến, `SecurityContextHolder` lưu context theo thread. Vì vậy:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
```

có thể truy cập principal ở nhiều tầng xử lý **đang chạy cùng request thread**. Nhưng ngay cả trong Servlet, `@Async` hoặc một executor riêng cũng có thể làm thread-local context biến mất nếu không có cơ chế propagation.

`ThreadLocal` hoạt động theo mô hình **thread là đơn vị giữ ngữ cảnh**. Nó không tự hiểu rằng nhiều thread khác nhau cùng tham gia một request.

## 3. WebFlux: một request không cố định ở một thread

Reactor tổ chức xử lý thành các publisher `Mono<T>` (tối đa một phần tử) và `Flux<T>` (nhiều phần tử). Khi một client subscription được thiết lập, toán tử có thể chạy trên event-loop thread hoặc scheduler khác tùy cách kết hợp.

```mermaid
flowchart LR
    A["HTTP WebFlux request"] --> B["WebFilter chain"]
    B --> C["Reactive Authentication"]
    C --> D["Mono/Flux pipeline"]
    D --> E["WebClient / reactive DB"]
    E --> F["Response publisher"]
    G["Reactor Context của subscription"] -.-> C
    G -.-> D
    G -.-> E
```

Ví dụ:

```java
return orderRepository.findById(orderId)
    .publishOn(Schedulers.boundedElastic())
    .map(this::toDto);
```

`publishOn` chuyển phần xử lý downstream sang scheduler khác. Nếu code chỉ dựa vào một `ThreadLocal` được gán ở thread HTTP ban đầu, nó **không bảo đảm** sẽ thấy cùng Authentication. Còn Reactor Context được thiết kế để đi theo subscription và các toán tử Reactor tương ứng, kể cả khi thread thay đổi.

**“Đổi thread” và “đổi subscription hoặc rời pipeline” là hai vấn đề khác nhau.** Chính điểm này quyết định lựa chọn API nào để lấy danh tính.

## 4. So sánh `ThreadLocal` và Reactor Context

| Đặc điểm | Servlet `SecurityContextHolder` thường gặp | Reactor `ReactiveSecurityContextHolder` |
| --- | --- | --- |
| Nơi giữ ngữ cảnh | `ThreadLocal` theo strategy mặc định. | Reactor `Context` gắn với subscriber/subscription. |
| Cách đọc | Lệnh đồng bộ `SecurityContextHolder.getContext()`. | Publisher `ReactiveSecurityContextHolder.getContext()` trả `Mono<SecurityContext>`. |
| Cách truyền qua thread khác | Cần propagation phù hợp, không tự đảm bảo. | Reactor operators giữ context qua scheduler chuyển thread trong cùng chuỗi. |
| Khi tạo `Mono` chưa subscribe | Không có khái niệm này ở API imperative. | Chưa nhất thiết thực hiện truy cập context hay I/O. |
| Khi `.subscribe()` thủ công | Không áp dụng cùng kiểu. | Có thể tạo subscription tách rời, mất context/error lifecycle mong đợi. |
| Khi qua callback/`CompletableFuture` bên ngoài Reactor | Phụ thuộc bridge riêng. | Không được bảo đảm nếu không nối context/adapter đúng. |
| Nơi ghi context | `SecurityContextHolder.setContext(...)` trong scope có kiểm soát. | `contextWrite(...)` với context cung cấp bởi `ReactiveSecurityContextHolder`. |
| Dọn context | Security filter lifecycle quản lý. | Context theo subscription/lifecycle, không cần dọn một biến thread-local toàn cục cho mỗi response. |

Reactor Context có ngữ nghĩa **bất biến theo phép biến đổi**: gọi `contextWrite` tạo ngữ cảnh mới cho đoạn upstream tương ứng, không mutate một map global để các request khác cùng dùng. Context là metadata kỹ thuật gắn subscription; không nên biến nó thành nơi lưu toàn bộ entity/session state tùy tiện.

## 5. `ReactiveSecurityContextHolder` trả về gì?

Spring Security reactive cung cấp:

```java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
```

API trọng tâm:

```java
Mono<SecurityContext> context =
    ReactiveSecurityContextHolder.getContext();
```

Khác với:

```java
SecurityContext context =
    SecurityContextHolder.getContext();
```

`getContext()` của reactive **trả `Mono`**, vì việc đọc context xảy ra khi một subscription có Reactor Context tương ứng. Do đó không được:

```java
// Phản ví dụ: tránh block trong WebFlux request.
SecurityContext context =
    ReactiveSecurityContextHolder.getContext().block();
```

Thay vào đó, dùng toán tử:

```java
Mono<Authentication> currentAuthentication =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication);
```

Với endpoint không có security context, `getContext()` có thể là publisher rỗng. Nếu ứng dụng có anonymous Authentication, context có thể tồn tại nhưng principal **không phải JWT đã xác thực**. Khi use case cần JWT, phải kiểm tra kiểu Authentication và policy, không chỉ “context không null”.

## 6. Luồng Bearer JWT trong Spring Security WebFlux

Trong Resource Server reactive, HTTP request mang:

```http
GET /api/orders/101 HTTP/1.1
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Một luồng khái niệm:

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant F as Reactive Spring Security WebFilters
    participant M as ReactiveAuthenticationManager
    participant D as ReactiveJwtDecoder
    participant R as Reactor Context
    participant A as WebFlux Handler
    C->>F: Authorization: Bearer access token
    F->>M: Xác thực credential
    M->>D: Xác minh JWT và validator
    alt Token không hợp lệ
        D-->>M: Authentication failure
        M-->>C: 401 / Bearer error theo policy
    else Token hợp lệ
        D-->>M: Jwt đã xác minh
        M-->>F: Authentication + authorities
        F->>R: SecurityContext cho reactive chain
        R->>A: Mono/Flux có principal theo subscription
        A-->>C: Response hoặc 403 theo authorization
    end
```

Trong WebFlux, Spring Security sử dụng **`WebFilter` chain** thay vì Servlet Filter chain; các thành phần như `AuthenticationWebFilter` và context propagation web filters tham gia xác thực/phục hồi context theo cấu hình. Không cần để controller tự tạo Authentication từ HTTP header.

Với JWT Resource Server, provider/manager dùng `ReactiveJwtDecoder` để xác minh token. `Jwt` sau khi được chấp nhận có thể được gắn vào `JwtAuthenticationToken`. Với opaque token, reactive introspector cung cấp principal; cách diễn giải scope phụ thuộc authentication converter.

### Một điểm quan trọng về “reactive”

JWT signature verification có thể cần CPU, đọc khóa đã cache hoặc tải JWKS. Một API reactive **không có nghĩa mọi phép tính mật mã đều không tốn thời gian**, nhưng network/resource operations phải được triển khai với API và scheduler phù hợp, không vô tư gọi một HTTP client blocking trên event loop.

## 7. Dependency và cấu hình tối thiểu cho WebFlux Resource Server

Gradle:

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Cấu hình:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/shop
```

Ví dụ chỉ định Spring Boot tạo `ReactiveJwtDecoder` theo issuer nếu không có decoder bean do ứng dụng tự cung cấp. Validator mặc định theo issuer/đồng hồ và các cấu hình bổ sung cần được hiểu theo phiên bản; **audience của orders-api phải được kiểm tra nếu đó là yêu cầu bảo mật của API**, không chỉ kiểm chữ ký rồi chấp nhận token dành cho dịch vụ khác.

Nếu dùng WebFlux, nên tránh vô tình thêm `spring-boot-starter-web` vào classpath mà không hiểu việc Spring Boot lựa chọn loại web application. Với cả MVC và WebFlux starter, mặc định Spring Boot thường ưu tiên Servlet MVC. Nếu chuyển sang reactive thực, hãy kiểm tra application type và dependency tree, không chỉ nhìn thấy class `Mono`.

## 8. `SecurityWebFilterChain` thay cho `SecurityFilterChain`

Một cấu hình WebFlux JWT API:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
public class ReactiveApiSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {

        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/actuator/health/liveness")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Ý nghĩa:

- **`ServerHttpSecurity`** là DSL reactive, không phải Servlet `HttpSecurity`.
- **`SecurityWebFilterChain`** chứa các WebFilter security tương ứng.
- `authorizeExchange`/`pathMatchers` là cách xác định HTTP access rules trong WebFlux.
- `oauth2ResourceServer().jwt()` nhận access token Bearer bằng JWT authentication reactive.
- `NoOpServerSecurityContextRepository` tránh lưu/tải SecurityContext qua một session repository; Bearer API xác thực credential theo request.
- `anyExchange().denyAll()` đóng những endpoint không được khai báo theo chain này.
- `csrf.disable()` chỉ phù hợp khi API thuần Bearer trong **Authorization header**, không dùng cookie tự đính kèm làm credential. Web/BFF cookie route cần CSRF riêng.

Đây là **một chain toàn cục**, không phải chain hẹp chỉ khớp `/api/**`. Ứng dụng phải thêm rule cho các endpoint thực tế như readiness, OpenAPI, internal admin... hoặc tách chain có thứ tự và fallback bảo vệ rõ ràng.

## 9. Các cặp class dễ nhầm khi chuyển MVC sang WebFlux

| Mục đích | Servlet/MVC | Reactive/WebFlux |
| --- | --- | --- |
| HTTP security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Bật web security | `@EnableWebSecurity` khi cần | `@EnableWebFluxSecurity` khi cần |
| HTTP rule | `authorizeHttpRequests`, `requestMatchers` | `authorizeExchange`, `pathMatchers` |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| Opaque introspection | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| Lấy SecurityContext | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| Security context persistence | `SecurityContextRepository` | `ServerSecurityContextRepository` |
| Session | `HttpSession` | `WebSession` |
| Method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |
| HTTP integration test | `MockMvc` | `WebTestClient` |

Không có nghĩa tất cả class ở cột MVC bị cấm tồn tại trong ứng dụng WebFlux, nhưng **chúng không phải API mặc định cho request reactive**. Ví dụ thêm `@EnableMethodSecurity` thay vì `@EnableReactiveMethodSecurity` có thể dẫn đến method security không hoạt động như developer mong muốn trên publishers.

## 10. Đọc principal trong một reactive controller

Với endpoint đã được Spring Security bảo vệ bằng JWT, có thể lấy Authentication từ Reactor Context:

```java
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class CallerController {

    @GetMapping("/api/caller")
    public Mono<String> callerName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "Authentication required")))
            .map(Authentication::getName);
    }
}
```

Đoạn này giả định URL `/api/caller` **đã được cho phép** bởi `SecurityWebFilterChain`; nếu chain ở phần 8 vẫn dùng `anyExchange().denyAll()` mà không thêm matcher, request sẽ bị chặn trước controller.

Để lấy danh tính **JWT cụ thể**, phải phân biệt:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .flatMap(authentication -> {
        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)
                || !jwtAuth.isAuthenticated()) {
            return Mono.error(new AccessDeniedException(
                "Verified JWT caller required"));
        }
        Jwt jwt = jwtAuth.getToken();
        return Mono.just(jwt.getSubject());
    });
```

Ví dụ thứ hai cần import `JwtAuthenticationToken`, `Jwt`, `AccessDeniedException`, `Mono`. Đối với endpoint JWT-only có principal do framework cung cấp, controller cũng có thể dùng `@AuthenticationPrincipal Jwt jwt` nếu cơ chế argument resolver phù hợp; nó hữu ích cho việc đọc claim ngắn gọn nhưng **không thay authorization rule của API**.

## 11. `ReactiveSecurityContextHolder.getContext()` là một publisher

Thay vì đọc context ngay khi method được gọi:

```java
Mono<SecurityContext> securityContext =
    ReactiveSecurityContextHolder.getContext();
```

`Mono` này được **subscribe bởi WebFlux runtime** khi xử lý response. Reactor Context tại thời điểm subscription cung cấp dữ liệu.

Một cách viết sai:

```java
// PHẢN VÍ DỤ: không làm trong WebFlux request handler.
SecurityContext context =
    ReactiveSecurityContextHolder.getContext().block();
```

`block()` trên event-loop có thể gây exception hoặc làm nghẽn luồng, và có thể tạo một subscription tách khỏi chuỗi chính nên không nhận context mong đợi. Tương tự:

```java
ReactiveSecurityContextHolder.getContext()
    .subscribe(context -> someField = context);
```

không phải cách lấy caller để trả response: nó tạo một công việc phụ, khó kiểm soát lifecycle và lỗi, đồng thời `someField` có thể là trạng thái chia sẻ giữa requests.

**Hãy trả lại và kết hợp publisher**, không tự subscribe hoặc dùng biến mutable để “lấy giá trị ra khỏi Mono”.

## 12. Dùng `flatMap` để giữ cùng subscription

Một pattern đúng:

```java
@GetMapping("/api/me/orders")
public Flux<OrderDto> myOrders() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMapMany(authentication ->
            orderService.findVisibleOrders(authentication));
}
```

`flatMapMany` kết nối publisher của service vào **cùng pipeline**. Bên trong service, các phép gọi reactive repository/WebClient có thể sử dụng context của subscription nếu cần.

Một phản ví dụ:

```java
@GetMapping("/api/me/orders")
public Flux<OrderDto> myOrders() {
    ReactiveSecurityContextHolder.getContext()
        .subscribe(ctx -> auditCaller(ctx));
    return orderService.findAllOrders();
}
```

Đoạn này **không đợi audit**, có thể không nhìn thấy cùng context, và `findAllOrders()` lại không giới hạn theo caller. Việc test HTTP trả 200 không chứng minh owner/tenant authorization tồn tại.

Nếu cần audit và truy vấn:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .flatMapMany(auth ->
        auditService.recordAccess(auth)
            .thenMany(orderService.findVisibleOrders(auth)));
```

Nếu audit thất bại thì có cho tiếp tục hay không phải theo business/security policy, nhưng phải là **một lựa chọn explicit**, không do `subscribe()` fire-and-forget vô tình quyết định.

## 13. `contextWrite(...)` truyền ngữ cảnh theo subscription

Reactor có cơ chế:

```java
Mono<String> source = Mono.deferContextual(view ->
    Mono.just(view.getOrDefault("traceId", "missing")));

Mono<String> pipeline =
    source.contextWrite(context ->
        context.put("traceId", "trace-123"));
```

Trong pipeline này, toán tử `source` có thể đọc `traceId` qua Reactor Context. Context không phải `ThreadLocal`, và `contextWrite` không cập nhật một map toàn cục.

**Ngữ nghĩa thứ tự quan trọng:** `contextWrite` bổ sung/sửa context được nhìn thấy bởi **các operator phía upstream của vị trí đó** trong subscription. Đừng giả định nó tương đương với “đặt biến toàn cục cho mọi đoạn code viết phía sau”.

Ví dụ:

```java
Mono<String> first =
    Mono.deferContextual(ctx -> Mono.just(
        ctx.getOrDefault("flag", "none")))
        .contextWrite(ctx -> ctx.put("flag", "A"));

Mono<String> second =
    Mono.deferContextual(ctx -> Mono.just(
        ctx.getOrDefault("flag", "none")));
```

`first` có `flag = A`; `second` không tự có `flag = A` chỉ vì nó nằm trong cùng method Java. Mỗi pipeline/subscription có context boundary riêng.

Trong ứng dụng Spring Security thực, **framework thiết lập SecurityContext** sau khi xác thực request. Controller bình thường chỉ đọc nó; không nên tự sửa context để “tạo user” từ dữ liệu request.

## 14. `ReactiveSecurityContextHolder.withAuthentication(...)`

Spring Security cung cấp một cách đưa Authentication vào Reactor Context:

```java
ReactiveSecurityContextHolder.withAuthentication(authentication)
```

Sử dụng với `contextWrite`:

```java
Mono<String> task =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(testAuth));
```

`testAuth` là Authentication **đã được chuẩn bị trong một unit test tin cậy**. Đoạn này hữu ích cho việc test reactive service **không cần chạy toàn bộ HTTP filter chain**.

Trong production, không bao giờ làm:

```java
// PHẢN VÍ DỤ: tạo principal từ input chưa xác thực.
Authentication auth = new TestingAuthenticationToken(
    requestUserName, "ignored", "ROLE_ADMIN");

return businessService.run()
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));
```

Một caller tự chọn `requestUserName` không được trở thành authenticated user chỉ nhờ một helper. **Nguồn Authentication phải đáng tin**, ví dụ Spring Security WebFlux đã xác minh Bearer token. `contextWrite` là cơ chế truyền, **không phải cơ chế xác thực**.

## 15. `withSecurityContext(...)` và `clearContext()`

Các API khác:

```java
ReactiveSecurityContextHolder.withSecurityContext(
    Mono.just(securityContext));
```

và:

```java
ReactiveSecurityContextHolder.clearContext();
```

được dùng trong `contextWrite(...)` khi một đoạn code **được tin cậy và có quyền thiết lập/loại bỏ** SecurityContext. `withSecurityContext(...)` nhận một `Mono<? extends SecurityContext>`, không phải một `SecurityContext` imperative trần.

Trong controller bình thường, bạn **không cần gọi** những method này: framework đã làm việc tại web security boundary. Chúng hữu ích trong test, adapter đặc biệt hoặc custom authentication/filter được review.

Xóa Reactor Context trong một đoạn publisher không đồng nghĩa revoke JWT hoặc logout mọi client; cũng như `SecurityContextHolder.clearContext()` của Servlet, nó chỉ thay đổi ngữ cảnh hiện tại, **không làm một Bearer token đã phát hành trở nên hết hiệu lực**.

## 16. `publishOn` và `subscribeOn` không tự làm mất Reactor Context

Ví dụ có switch scheduler:

```java
Mono<String> callerName =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .publishOn(Schedulers.parallel());
```

Nếu `callerName` được subscribe như một phần **cùng reactive chain có security context**, thì context vẫn có thể được truy cập theo cơ chế của Reactor dù processing thread thay đổi.

`publishOn(scheduler)` ảnh hưởng thread của các toán tử downstream. `subscribeOn(scheduler)` ảnh hưởng nơi subscription/source được lên lịch. **Không operator nào mặc định chuyển `SecurityContext` sang ThreadLocal**, nhưng Reactor Context được truyền qua subscription đúng cách.

Một lập luận sai:

> Vì publisher chuyển qua thread khác nên Reactor SecurityContext chắc chắn biến mất.

Phát biểu đúng hơn:

> Khi tiếp tục sử dụng các toán tử Reactor thuộc cùng chain/subscription, Reactor Context được truyền theo subscription; khi tự tách công việc hoặc đi qua API không tham gia Reactor, cần kiểm tra propagation riêng.

Lưu ý custom operators, third-party libraries hoặc interop không đúng có thể làm context propagation phức tạp. Test các adapter thực tế khi identity ảnh hưởng phân quyền.

## 17. Cách làm mất context: tự `subscribe()` trong service

Anti-pattern:

```java
public Mono<Void> processOrder(long orderId) {
    updateAuditTrail(orderId).subscribe();
    return orderRepository.process(orderId);
}
```

Lời gọi `.subscribe()` tạo subscription độc lập, chạy ngoài lifecycle response publisher, dễ mất Reactor Context, không xử lý lỗi theo luồng HTTP, và có thể xảy ra side effect **sau khi API đã trả response**.

Cách ghép đúng:

```java
public Mono<Void> processOrder(long orderId) {
    return updateAuditTrail(orderId)
        .then(orderRepository.process(orderId));
}
```

Ở đây hai thao tác nằm trong pipeline được trả về. Nếu cần bảo đảm atomicity cho database hoặc outbox/event, dùng reactive transaction và thiết kế side effect phù hợp; chỉ ghép `then` không tự biến hai hệ thống độc lập thành distributed transaction.

**Quy tắc:** Ở service/controller reactive, không tự `subscribe()` để làm “chạy cho chắc”. Framework ở boundary thích hợp sẽ subscribe vào response publisher.

## 18. Rời khỏi Reactor qua callback, thread hoặc `CompletableFuture`

Ví dụ:

```java
new Thread(() -> {
    // Không được giả định có Reactor SecurityContext ở đây.
    callExternalSystem();
}).start();
```

Đây là một execution path mới không tự thừa hưởng Reactor Context. Tương tự, callback của một thư viện imperative hoặc executor ngoài Reactor **không nhất thiết có** context subscription.

Nếu phải gọi API blocking từ WebFlux, cân nhắc adapter hợp lệ:

```java
Mono<Result> result =
    Mono.fromCallable(() -> legacyClient.fetch())
        .subscribeOn(Schedulers.boundedElastic());
```

Cách này tránh blocking event loop bằng cách chuyển thao tác blocking sang scheduler phù hợp. Nhưng **đừng dùng `SecurityContextHolder.getContext()` bên trong `legacyClient.fetch()` rồi mặc định nó là người gọi hiện tại**: đó vẫn là ThreadLocal trên worker thread.

Hướng ít phụ thuộc cơ chế hơn:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .flatMap(auth ->
        Mono.fromCallable(() ->
                legacyClient.fetchFor(auth.getName()))
            .subscribeOn(Schedulers.boundedElastic()));
```

Truyền dữ liệu identity tối thiểu **đã xác thực** vào adapter rõ ràng, thay vì yêu cầu một thư viện blocking tự tra Reactor Context.

## 19. ThreadLocal bridging không phải cách thay thế chính cho Reactor Context

Hệ sinh thái Reactor/Micrometer có các khả năng **context propagation** để liên kết một số `ThreadLocal` (như tracing/MDC) với Reactor Context khi được cấu hình. Điều này có thể giúp logging/tracing, nhưng không nên dựa vào nó làm lý do đọc principal bằng `SecurityContextHolder` imperative ở mọi nơi trong WebFlux.

Các lý do:

- Không phải ThreadLocal nào cũng được đăng ký propagation.
- Phạm vi và timing của context snapshot phụ thuộc adapter và configuration.
- Một callback ngoài chuỗi hoặc một custom executor vẫn cần propagation rõ ràng.
- Đọc nhầm ThreadLocal stale trong môi trường nhiều request đồng thời có thể gây lỗi dữ liệu hoặc authorization.

**API chính cho reactive security identity vẫn là `ReactiveSecurityContextHolder` hoặc principal được framework inject vào handler**, không phải một bridge ngầm.

## 20. Reactor Context không phải nơi lưu một web login session

Trong WebFlux, có thể có `WebSession` khi ứng dụng cần nhớ trạng thái đăng nhập giữa requests. Nhưng Reactor Context được dùng để **truyền SecurityContext trong chuỗi phản ứng của một request/subscription**; đây không phải cùng khái niệm với session cookie.

| Thành phần | Vai trò |
| --- | --- |
| **Reactor Context** | Metadata gắn subscription, có thể chứa publisher SecurityContext. |
| **`SecurityContext`** | Authentication và principal đã được xác thực. |
| **`WebSession`** | Trạng thái web giữa nhiều request khi ứng dụng cần session. |
| **`ServerSecurityContextRepository`** | Cách tải/lưu SecurityContext cho request reactive. |
| **`NoOpServerSecurityContextRepository`** | Không sử dụng repository để lưu/khôi phục context. |
| **`WebSessionServerSecurityContextRepository`** | Repository có thể dùng WebSession để lưu/khôi phục SecurityContext. |

Một JWT Resource Server WebFlux có thể dùng `NoOpServerSecurityContextRepository` và xác thực token theo từng request. WebFlux web login/OIDC Client có thể cần web session và repository thích hợp. **Reactive không đồng nghĩa stateless**; WebFlux hỗ trợ cả API Bearer và web session, nhưng API tạo/phục hồi context khác Servlet.

### Đừng tìm `SessionCreationPolicy` ở chỗ sai

`SessionCreationPolicy` thuộc DSL Servlet `HttpSecurity`. Đối với WebFlux, cấu hình session/context thông qua **`ServerHttpSecurity` và `ServerSecurityContextRepository`**; không sao chép `HttpSecurity.sessionManagement(...SessionCreationPolicy.STATELESS)` vào một WebFlux security chain.

## 21. Đọc SecurityContext từ functional WebFlux handler

WebFlux không bắt buộc dùng annotation controller. Với functional endpoint, `ServerRequest.principal()` trả `Mono<Principal>`:

```java
public Mono<ServerResponse> caller(ServerRequest request) {
    return request.principal()
        .cast(Authentication.class)
        .flatMap(auth ->
            ServerResponse.ok()
                .bodyValue(auth.getName()));
}
```

Đoạn ví dụ cần imports `ServerRequest`, `ServerResponse`, `Authentication`, `Mono`. Nó giả định path được bảo vệ và principal thực là Spring Security `Authentication`; nếu có nhiều authentication mechanisms hoặc public route, nên kiểm tra kiểu và trường hợp rỗng.

Một cách khác là đọc qua `ReactiveSecurityContextHolder.getContext()`, không cố lấy `SecurityContextHolder.getContext()` từ thread hiện tại.

Lưu ý `ServerRequest.principal()` **không mặc nhiên bảo đảm caller có scope phù hợp**. Phân quyền tại `SecurityWebFilterChain`, method security và domain policy vẫn cần đầy đủ.

## 22. Mẫu service lấy identity rồi truy vấn dữ liệu có scope

Giả sử chỉ chủ sở hữu được đọc một order. Repo reactive có API minh họa:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    Mono<Order> findByIdAndTenantIdAndOwnerIssuerAndOwnerSubject(
        Long id,
        String tenantId,
        String ownerIssuer,
        String ownerSubject
    );
}
```

Một service membership:

```java
public interface TenantMemberships {
    Mono<Boolean> canReadOrders(
        String issuer,
        String subject,
        String tenantId
    );
}
```

Use case:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Service
public class OrderQueryService {

    private final TenantMemberships memberships;
    private final OrderRepository orders;

    public OrderQueryService(
            TenantMemberships memberships,
            OrderRepository orders) {
        this.memberships = memberships;
        this.orders = orders;
    }

    public Mono<OrderDto> getVisibleOrder(
            String tenantId,
            Long orderId) {

        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "JWT authentication required")))
            .flatMap(auth -> {
                if (!(auth instanceof JwtAuthenticationToken jwtAuth)
                        || !jwtAuth.isAuthenticated()) {
                    return Mono.error(new AccessDeniedException(
                        "JWT authentication required"));
                }

                boolean canRead = jwtAuth.getAuthorities().stream()
                    .anyMatch(a ->
                        "SCOPE_orders.read".equals(a.getAuthority()));
                if (!canRead) {
                    return Mono.error(new AccessDeniedException(
                        "Missing orders.read"));
                }

                Jwt jwt = jwtAuth.getToken();
                if (jwt.getIssuer() == null
                        || jwt.getSubject() == null) {
                    return Mono.error(new AccessDeniedException(
                        "Invalid caller identity"));
                }

                String issuer = jwt.getIssuer().toString();
                String subject = jwt.getSubject();

                return memberships.canReadOrders(
                        issuer, subject, tenantId)
                    .flatMap(allowed -> {
                        if (!allowed) {
                            return Mono.error(
                                new AccessDeniedException(
                                    "Tenant denied"));
                        }
                        return orders
                            .findByIdAndTenantIdAndOwnerIssuerAndOwnerSubject(
                                orderId, tenantId, issuer, subject)
                            .map(OrderDto::from)
                            .switchIfEmpty(Mono.error(
                                new ResponseStatusException(
                                    HttpStatus.NOT_FOUND)));
                    });
            });
    }
}
```

`Order`, `OrderDto` và repository schema là các kiểu minh họa cần triển khai; ví dụ giả định `canReadOrders` trả `Mono<Boolean>` không rỗng và đã thực thi membership policy từ nguồn đáng tin.

Ở đây:

1. Service lấy trusted Authentication từ **Reactor Context của subscription hiện tại**.
2. Kiểm tra `JwtAuthenticationToken`, scope và issuer/subject.
3. Kiểm tra membership tenant qua một **publisher reactive**.
4. Query order có điều kiện **tenant + owner issuer + owner subject**.
5. Không trả order của tenant/owner khác chỉ vì token có `orders.read`.

Điều kiện owner-only này cần thay bằng ACL/sharing/admin policy rõ ràng nếu nghiệp vụ có các ngoại lệ được phép. Không tự lấy `tenantId` từ header do client gửi rồi coi đó là membership.

## 23. Vì sao đọc context ở subscription time quan trọng?

Một controller có thể tạo:

```java
Mono<OrderDto> pending =
    orderQueryService.getVisibleOrder(tenantId, orderId);
```

Khi method `getVisibleOrder` được gọi, những bước `flatMap` bên trong **chưa nhất thiết chạy**. Pipeline thường chạy khi WebFlux subscribe để phát HTTP response. Chính lúc đó Reactor Context chứa Authentication của request phải được đưa vào pipeline.

Một cách làm sai là lưu context vào field singleton:

```java
@Service
public class UnsafeCallerHolder {
    private Authentication lastCaller;

    public Mono<Void> save() {
        return ReactiveSecurityContextHolder.getContext()
            .doOnNext(ctx ->
                lastCaller = ctx.getAuthentication())
            .then();
    }
}
```

Vì service bean có thể được dùng chung cho nhiều requests, field `lastCaller` có thể bị request khác ghi đè và gây **cross-user identity leak**. Dùng Reactor Context hoặc truyền một DTO identity bất biến đến các publisher cần nó, **không dùng mutable singleton state**.

## 24. `Mono.cache()` và cache kết quả theo người dùng

Reactor `Mono.cache()` có ích để memoize một publisher, nhưng nếu cùng instance publisher được **chia sẻ qua requests**, có nguy cơ nhớ kết quả của subscriber đầu và phát lại cho subscriber sau mà không chạy lại kiểm tra principal.

Ví dụ phản diện:

```java
// Không lưu một Mono theo caller làm field singleton toàn ứng dụng.
private final Mono<OrderDto> cachedOrder =
    loadOrderForCurrentCaller().cache();
```

Caller Alice subscribe đầu, publisher lấy đơn của Alice và cache `OrderDto`. Caller Bob subscribe cùng publisher có thể nhận dữ liệu đã cache mà không chạy lại lookup authorization, tùy thiết kế.

Phân biệt:

- `cache()` **trong scope một request/publisher không chia sẻ** thường là tối ưu nội bộ hợp lệ.
- `cache()` được giữ ở **singleton hoặc shared registry** cần phân tích scope principal/tenant/policy.
- Cache application như Redis/Caffeine cũng phải namespace theo identity và policy khi dữ liệu phụ thuộc quyền.
- Cache result từ `ReactiveSecurityContextHolder.getContext()` trên một publisher chia sẻ có thể **đóng băng Authentication** của một subscription nếu thiết kế sai.

Mọi optimization memoization cần kiểm thử với **hai người dùng khác nhau** và dữ liệu owner/tenant khác nhau.

## 25. Reactive method security dùng Reactor Context

Để bật method security trong WebFlux:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {}
```

Một service:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import reactor.core.publisher.Mono;

@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public Mono<ReportDto> report(String reportId) {
    return reportRepository.findById(reportId)
        .map(ReportDto::from);
}
```

Với **reactive method security**, Spring Security lấy Authentication từ Reactor Context thông qua tích hợp với `ReactiveSecurityContextHolder`, chứ không đòi controller gọi `SecurityContextHolder.getContext()` trên thread.

Các lưu ý:

- Các method được bảo vệ thường cần trả `Mono`, `Flux` hoặc kiểu Publisher được hỗ trợ để security checks xảy ra trong reactive context phù hợp.
- Cần dùng **Spring-managed bean/proxy**; self-invocation có thể bỏ qua interceptor của method security như các tình huống Spring AOP khác.
- Scope `reports.read` **không tự chứng minh quyền trên từng báo cáo**; vẫn cần kiểm tra tenant/owner/ACL.
- Một unit test `new Service(...)` không tự kích hoạt `@PreAuthorize`; cần test qua Spring context để kiểm tra annotation, và test domain policy riêng.

Nếu service phải hỗ trợ cả HTTP JWT và machine-initiated work, cần định nghĩa cách truyền identity đáng tin. Không tự đặt user admin vào Reactor Context để vượt qua annotation.

## 26. Reactive transaction cũng phụ thuộc subscription context

WebFlux thường kết hợp R2DBC hoặc reactive database driver. Trong reactive transaction, Spring có thể dùng **Reactor Context** để duy trì thông tin transaction thay vì ràng buộc toàn bộ trạng thái với một ThreadLocal của JDBC.

Ví dụ `@Transactional` trên một method trả `Mono`:

```java
@Transactional
public Mono<Void> updateOrder(...) {
    return repository.findById(...)
        .flatMap(order -> repository.save(order))
        .then();
}
```

Đây chỉ là ví dụ lược giản, không có authorization đầy đủ; cần một **ReactiveTransactionManager** phù hợp với database reactive. Không dùng `@Transactional` với JDBC/JPA blocking rồi mặc định đó là reactive transaction chỉ vì method trả `Mono`.

Reactor Context có thể đồng thời mang metadata của security và transaction theo **các khóa khác nhau**, nhưng điều này không có nghĩa một transaction tự bao bọc tất cả side effect ngoài DB hoặc tự đảm bảo owner authorization.

Nếu code tách `subscribe()` ở giữa, thao tác con có thể chạy ngoài transaction/context của pipeline chính; đó là lỗi vừa về correctness vừa về bảo mật khi quyền/owner check và ghi dữ liệu phải gắn với cùng use case.

## 27. WebFlux không cho phép gọi blocking vô tội vạ

Một phản ví dụ:

```java
@GetMapping("/api/reports")
public Mono<ReportDto> reports() {
    ReportDto dto = jdbcRepository.findBigReport();
    return Mono.just(dto);
}
```

Đoạn trên thực hiện JDBC blocking **ngay trong method**, có thể giữ event-loop thread và làm chậm các request khác. Dù SecurityContext lấy đúng cách, ứng dụng vẫn dễ bị cạn tài nguyên.

Nếu chưa thể chuyển sang R2DBC/reactive driver, cần cô lập thao tác blocking vào scheduler thích hợp, có giới hạn concurrency:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .flatMap(authentication ->
        Mono.fromCallable(() ->
                legacyService.reportFor(authentication.getName()))
            .subscribeOn(Schedulers.boundedElastic()));
```

Lưu ý `authentication.getName()` không tự là ID người dùng nghiệp vụ: khi cần owner/tenant, nên sử dụng identity mapping đáng tin và domain policy. `boundedElastic` giúp không chặn event loop, **không biến JDBC thành non-blocking** và không loại bỏ nhu cầu backpressure, connection limits hay timeout.

## 28. Custom WebFilter cần truy cập context đúng giai đoạn

Nếu cần log/tracing hoặc một policy filter tùy chỉnh, một WebFilter có thể nhìn context trong pipeline:

```java
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    return chain.filter(exchange)
        .doOnEach(signal -> {
            // Dùng tín hiệu/context đúng contract của Reactor.
            // Không đọc một ThreadLocal rồi mặc định là JWT caller.
        });
}
```

Đây là **phác thảo ý tưởng**, không phải custom filter hoàn chỉnh: cần định nghĩa imports, ordering, error path, context access và tránh logging sensitive data. Một `WebFilter` thêm vào thứ tự quá sớm có thể được gọi **trước authentication**, nên không tự thấy Authentication đã xác thực.

Khi cần lấy caller sau authentication, thường dễ hơn khi thực hiện ở controller/service qua `ReactiveSecurityContextHolder` hoặc trong một filter có ordering được hiểu rõ. Không tự viết một WebFilter dùng `Authorization` header để parse JWT rồi dựng Authentication, trừ khi thực sự triển khai custom authentication có kiểm chứng đầy đủ.

## 29. Tracing và MDC không phải nguồn thẩm quyền identity

Một pipeline có thể có trace ID hoặc tenant hint trong MDC/Reactor Context phục vụ logging:

```text
traceId = 1234
tenantHint = tenant-a
```

Nhưng `tenantHint` do gateway/header thêm không tự chứng minh user có quyền tenant-a. Tracing context và security context có mục đích khác nhau:

- Trace context giúp liên kết logs/spans.
- SecurityContext chứa Authentication từ cơ chế xác thực đã được tin cậy.
- Domain policy kiểm tra tenant/owner từ nguồn thẩm quyền phù hợp.

Nếu ứng dụng đồng bộ trace ID qua ThreadLocal/MDC, nó không vì vậy được phép đồng bộ “isAdmin” hoặc “ownerId” từ một header chưa xác minh thành Authentication.

Khi log reactive code, phải tránh raw access token, cookies, client secrets và toàn bộ JWT claims. Nếu dùng username/subject trong log, cân nhắc privacy và namespace issuer.

## 30. Kiểm thử `ReactiveSecurityContextHolder` bằng `StepVerifier`

Một unit test không cần HTTP có thể chứng minh context đi theo Reactor pipeline kể cả sau khi đổi scheduler:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class ReactiveContextTest {

    @Test
    void authenticationIsReadAcrossSchedulerSwitch() {
        Authentication alice = new TestingAuthenticationToken(
            "alice", "unused", "SCOPE_orders.read");

        Mono<String> result =
            ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName())
                .publishOn(Schedulers.parallel())
                .contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(alice));

        StepVerifier.create(result)
            .expectNext("alice")
            .verifyComplete();
    }
}
```

Test cần `reactor-test` và dependency Spring Security Test phù hợp. `TestingAuthenticationToken` chỉ dành cho test, không chứng minh access token thật đã được xác minh chữ ký. Điểm test chứng minh là **context đi theo Reactor subscription**, không phải Authentication nằm sẵn trong ThreadLocal của một event-loop thread.

Có thể thêm test:

```java
Mono<Boolean> missing =
    ReactiveSecurityContextHolder.getContext()
        .hasElement();

StepVerifier.create(missing)
    .expectNext(false)
    .verifyComplete();
```

Test trên giả định pipeline **không có `contextWrite` cung cấp SecurityContext**. Nó cho thấy publisher không tự nhận principal từ một field global hoặc test trước đó.

## 31. `WebTestClient`: kiểm tra WebFlux authorization

Spring Security Test cung cấp `mockJwt()` cho WebFlux. Ví dụ tạo client gắn với application context và security filters:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();

client.mutateWith(mockJwt()
        .authorities(new SimpleGrantedAuthority(
            "SCOPE_orders.read")))
    .get()
    .uri("/api/orders/101")
    .exchange()
    .expectStatus().isOk();
```

Các import static trong Markdown có thể được format trên hai dòng để dễ đọc; **trong source Java, mỗi `import` phải viết thành một dòng hợp lệ**. Cần thêm imports `WebTestClient`, `ApplicationContext` và `SimpleGrantedAuthority`, đồng thời fixture/controller/service cho order 101 phải tạo được kết quả 200 cho caller kiểm thử.

`mockJwt()` là **mock authentication**, thường không chạy `ReactiveJwtDecoder` production để kiểm tra chữ ký JWT thật. Khi `.authorities(...)` được gán trực tiếp, test cũng không xác nhận scope converter thật được cấu hình đúng. Nó phù hợp để kiểm tra policy HTTP/method service, không phải bằng chứng cho JWT cryptography.

## 32. Ma trận kiểm thử context và authorization

| Ca | Test | Điều cần chứng minh |
| --- | --- | --- |
| JWT hợp lệ có `orders.read` | WebFlux integration + mockJwt hoặc JWT thật | Route đọc đi tiếp, còn domain policy. |
| Không có Bearer | WebTestClient trên protected route | Không có verified principal, thường 401. |
| JWT hợp lệ thiếu scope | WebTestClient với authorities thiếu | Authorization từ chối, thường 403. |
| Cùng token nhưng sai audience | JWT ký thật, ReactiveJwtDecoder thật | Authentication từ chối. |
| Publisher chuyển `publishOn` | StepVerifier + `withAuthentication` | Reactor Context vẫn đọc được sau scheduler switch. |
| Truy cập `SecurityContextHolder` imperative | Unit/integration trong pipeline | Không dựa vào ThreadLocal để tìm caller. |
| `getContext()` không có context | StepVerifier | Publisher rỗng/không có identity mong đợi. |
| Direct service call với `withAuthentication` | StepVerifier + mock repo | Service đọc principal từ subscription context. |
| Sai tenant, cùng tenant khác owner | Service + reactive repo fixture | Không rò rỉ object. |
| Two-user shared `Mono.cache()` | Test hai subscriptions với hai principals | Không dùng lại kết quả được phép của user đầu. |
| Có `WebSession` cũ nhưng không Bearer | Integration test HTTP | API Bearer-only không lấy login session làm quyền. |
| `@PreAuthorize` reactive | Spring context + reactive method security | Method bị chặn theo authorities trong Reactor Context. |
| `subscribe()` tách rời | Test có kiểm soát/pipeline review | Không dựa vào side effect ngoài subscription chính. |

Đối với JWT end-to-end, dùng test issuer/JWK Set, JWT ký bằng private key test, `ReactiveJwtDecoder` thật và HTTP request thật. Một `mockJwt()` trả 200 **không chứng minh signature, issuer, audience hoặc expiry đã được kiểm tra**.

## 33. Kiểm thử quyền tại service reactive, không chỉ HTTP filter

Một lỗi phổ biến:

```text
GET /api/orders/101 -> HTTP security kiểm tra scope đúng
Controller -> repository.findById(orderId)
```

Với JWT đúng scope nhưng order thuộc người khác, API có thể mắc BOLA/IDOR. WebFlux không tự xử lý object authorization.

Test service trực tiếp:

```java
Mono<OrderDto> result =
    service.getVisibleOrder("tenant-b", 201L)
        .contextWrite(
            ReactiveSecurityContextHolder
                .withAuthentication(aliceJwtAuthentication));

StepVerifier.create(result)
    .expectError(AccessDeniedException.class)
    .verify();
```

`aliceJwtAuthentication` trong test phải đại diện JWT principal Alice đã chuẩn bị đúng issuer/subject/authority; repository/membership fixtures xác định Alice không được quyền ở tenant-b. Test này **không cần một HTTP controller** và giúp khẳng định service vẫn kiểm tra tenant trong chuỗi reactive.

Tiếp tục test owner mismatch trong cùng tenant, cùng `sub` khác issuer, mất membership khi token còn hạn, và cache result theo identity. Khi `@PreAuthorize` là lớp bảo vệ, cần test **qua Spring-managed proxy** vì gọi `new Service(...)` không kích hoạt AOP; đồng thời domain policy vẫn nên có test trực tiếp.

## 34. WebSession và API Bearer theo từng yêu cầu

Trong WebFlux, nếu client authentication cần lưu giữa requests (ví dụ OAuth2/OIDC web login), `WebSession` có thể giữ security context thông qua `WebSessionServerSecurityContextRepository`. Trong Bearer API thuần, ta thường chọn không sử dụng session repository cho authentication:

```java
.securityContextRepository(
    NoOpServerSecurityContextRepository.getInstance())
```

Một request đến API mang Bearer token được xác thực, context gắn vào chain. Request tiếp theo **không Bearer** không nên được cho phép chỉ vì browser mang `SESSION` cookie của một web login khác.

**WebFlux reactive không bắt buộc stateless.** Ứng dụng có web session vẫn có Reactor Context cho từng request. Sự khác biệt:

```text
WebSession = trạng thái được phục hồi qua nhiều request
Reactor Context = ngữ cảnh mang Authentication trong subscriber chain hiện tại
```

Nếu dùng nhiều `SecurityWebFilterChain`, phải kiểm tra matcher/order và fallback để API không vô tình dùng session auth của web route. Với cookie-based login hoặc BFF, vẫn cần CSRF, cookie security, logout và session fixation protection theo threat model.

## 35. Những anti-pattern cần nhớ khi chuyển MVC sang WebFlux

### 35.1. Dùng `SecurityContextHolder` như trong MVC

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
```

Trong WebFlux reactive chain, đây **không phải cách tin cậy** để lấy principal. Dùng `ReactiveSecurityContextHolder.getContext()` hoặc argument resolver reactive phù hợp.

### 35.2. Gọi `.block()` để lấy Authentication

```java
Authentication auth =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .block();
```

Có thể block event-loop/tạo subscription riêng, làm mất ngữ cảnh và phá mô hình non-blocking.

### 35.3. Gọi `.subscribe()` trong controller/service

```java
saveAudit().subscribe();
return updateOrder();
```

Tạo công việc tách rời, lifecycle và context không còn gắn với response. Nối các publisher bằng `flatMap`, `then`, `concatMap` theo semantics.

### 35.4. Coi `publishOn` là lỗi bảo mật tự thân

Reactor Context được truyền theo subscription; đổi scheduler không tự mất SecurityContext. Nguy cơ là tách khỏi chain, unsafe interop hoặc bridge thiếu kiểm soát.

### 35.5. Giữ Authentication trong field singleton

`private Authentication currentCaller;` có nguy cơ lẫn caller giữa requests. Dùng Reactor Context hoặc explicit immutable identity.

### 35.6. Dùng `Mono.cache()` cho dữ liệu phụ thuộc principal ở scope global

Publisher share qua requests có thể phát lại kết quả của người đầu cho người sau. Cache phải có identity/tenant/policy scope và invalidation phù hợp.

### 35.7. Tự đặt `withAuthentication` từ HTTP header chưa xác thực

`contextWrite` không xác minh chữ ký/token; chỉ nên đặt context từ trusted authentication boundary hoặc test.

### 35.8. Sao chép `HttpSecurity.sessionManagement` vào WebFlux

WebFlux dùng `ServerHttpSecurity` và `ServerSecurityContextRepository`. `SessionCreationPolicy` là API của Servlet stack.

### 35.9. Gọi JDBC/JPA blocking trực tiếp trên event-loop

Phá lợi ích non-blocking, dễ cạn thread. Dùng reactive driver hoặc isolate blocking có kiểm soát.

### 35.10. Coi scope đủ để đọc mọi bản ghi

Reactive JWT có `SCOPE_orders.read` chưa đủ xem order của mọi tenant/owner. Cần query scoped và domain policy.

## 36. Runbook khi WebFlux báo thiếu SecurityContext

Nếu service reactive báo không thấy principal hoặc authorization bất thường:

1. **Xác định stack**: ứng dụng thực sự chạy WebFlux hay MVC do dependency `spring-boot-starter-web` được đưa vào?
2. **Kiểm tra chain**: `SecurityWebFilterChain` có khớp route và bật JWT/opaque Resource Server chưa?
3. **Kiểm tra Bearer credential**: request thực có `Authorization: Bearer` đúng không? Không log raw token.
4. **Kiểm tra decoder/introspector**: issuer, audience, expiry, JWKS/introspection response có hợp lệ không?
5. **Kiểm tra access point**: code có dùng `SecurityContextHolder` imperative hoặc `ThreadLocal` không?
6. **Tìm `.block()` và `.subscribe()`**: có tạo subscription tách rời hoặc phá error/transaction lifecycle không?
7. **Xem adapter ngoài Reactor**: executor, `CompletableFuture`, callback, legacy client có cần explicit identity không?
8. **Xem `contextWrite` placement**: context được thêm vào đoạn upstream cần đọc hay chỉ một nhánh khác?
9. **Xem `Mono.cache()` và static fields**: có giữ result/principal qua nhiều callers không?
10. **Kiểm tra method security**: có `@EnableReactiveMethodSecurity` và lời gọi qua proxy không?
11. **Kiểm tra WebSession**: route Bearer-only có vô tình dùng authentication từ session web không?
12. **Viết StepVerifier/WebTestClient test cụ thể** cho subscriber context, scheduler switching, no-token, scope, tenant và caller khác nhau.

Khi log phục vụ chẩn đoán, dùng request/trace ID, type of authentication, route và kết quả authorization. Tránh raw token, client secrets, session IDs hoặc toàn bộ JWT claims.

## 37. Sơ đồ lựa chọn API khi viết code

```mermaid
flowchart TD
    A["Cần truy cập caller trong Spring WebFlux"] --> B{"Đang ở handler/service reactive?"}
    B -- "Có" --> C["ReactiveSecurityContextHolder.getContext()"]
    C --> D["map / flatMap / flatMapMany trong cùng pipeline"]
    D --> E["Kiểm tra Authentication + scope + tenant/owner"]
    B -- "Functional ServerRequest" --> F["request.principal()"]
    F --> E
    B -- "Unit test publisher" --> G["contextWrite(withAuthentication(testAuth))"]
    G --> H["StepVerifier"]
    B -- "Custom auth filter" --> I["Trusted authentication + Reactor context theo framework"]
    I --> E
    E --> J{"Có blocking legacy API?"}
    J -- "Có" --> K["Explicit identity + boundedElastic + giới hạn"]
    J -- "Không" --> L["Reactive repository/WebClient"]
```

Đây là sơ đồ quyết định về lập trình, **không thay thế cấu hình Spring Security xác thực Bearer access token**. `withAuthentication` ở nhánh unit test là một trợ giúp kiểm thử, không phải cách tự nâng quyền request chưa xác thực.

## 38. Tóm tắt những điểm cốt lõi

1. **Servlet mặc định truyền SecurityContext qua ThreadLocal; WebFlux truyền qua Reactor Context theo subscription.**
2. **`ReactiveSecurityContextHolder.getContext()` trả `Mono<SecurityContext>`**, nên dùng `map`/`flatMap`, không `.block()` để đọc đồng bộ.
3. `publishOn`/`subscribeOn` không tự đánh mất Reactor Context khi publisher vẫn nằm trong cùng chain; `.subscribe()` thủ công hay rời Reactor API mới là các ranh giới cần đề phòng.
4. `contextWrite` áp context cho **upstream của vị trí đặt**, không biến nó thành dữ liệu global; không tự dựng Authentication từ input không đáng tin.
5. WebFlux Resource Server cấu hình bằng **`ServerHttpSecurity` và `SecurityWebFilterChain`**, dùng `ReactiveJwtDecoder` hoặc `ReactiveOpaqueTokenIntrospector`.
6. **WebSession khác Reactor Context**. API Bearer có thể dùng `NoOpServerSecurityContextRepository` và xác thực từng request; web login vẫn có thể dùng session theo thiết kế.
7. `@EnableReactiveMethodSecurity` hỗ trợ kiểm tra method dùng Reactor Context nhưng không thay thế domain owner/tenant authorization và vẫn chịu các giới hạn Spring proxy.
8. Các publisher phụ thuộc danh tính không được cache/chia sẻ global thiếu scope, vì có thể gây **cross-user data leak**.
9. Đừng block event-loop hoặc dựa vào `ThreadLocal` trong adapter blocking; truyền danh tính đã xác thực một cách tường minh.
10. Kiểm thử với **`StepVerifier` và `WebTestClient`**, phân biệt `mockJwt()` dùng cho authorization với JWT ký thật đi qua decoder production.

**Điểm cốt lõi:** Trong Spring Security WebFlux, `SecurityContext` không “đi theo thread”, mà **đi theo subscription trong Reactor Context**. Vì thế cách viết đúng là **giữ luồng reactive liên tục, đọc identity qua `ReactiveSecurityContextHolder`, tránh `block()`/`subscribe()` tự phát, và bảo vệ use case theo scope/tenant/owner trong chính publisher**. Đây là nền tảng để Bearer Resource Server vừa xác thực đúng mỗi request vừa không làm lẫn danh tính giữa các chuỗi phản ứng chạy đồng thời.
