# Kiểm tra Reactor Context và principal tại lớp xử lý

Trong **Spring Security WebFlux Resource Server**, xác thực và phân quyền diễn ra trong một pipeline reactive. Vì vậy, `SecurityContext` và principal phải được đọc trong đúng **Reactor Context** của subscription hiện tại. Đây là điểm khác biệt quan trọng so với Spring Security Servlet, vốn thường dùng `SecurityContextHolder` dựa trên `ThreadLocal`.

Một request WebFlux có thể chuyển qua nhiều thread khi dùng `publishOn`, `subscribeOn` hoặc các scheduler khác. Reactor Context đi theo subscriber và được truyền xuyên suốt pipeline; thread hiện tại không phải danh tính bảo mật. Nếu service đọc `SecurityContextHolder.getContext()` như trong ứng dụng Servlet, kết quả có thể rỗng hoặc không phản ánh request đang xử lý.

Bài học tập trung vào các câu hỏi thực tế:

- Spring Security đưa authentication vào Reactor Context bằng cách nào?
- Controller lấy principal từ `@AuthenticationPrincipal` hoặc `ServerWebExchange` ra sao?
- Service lấy `Authentication` trong `ReactiveSecurityContextHolder` như thế nào?
- Làm sao kiểm tra context qua `flatMap`, `publishOn` và các service reactive?
- Vì sao không được gọi `block()` hoặc tự `subscribe()` trong service?
- Cách viết test bằng `WebTestClient`, `mockJwt()`, `mockOpaqueToken()` và token Bearer thật?
- Làm thế nào phát hiện rò rỉ context giữa requests hoặc giữa các subscribers?

> **Nguyên tắc:** trong WebFlux, hãy truyền dữ liệu và đọc security principal bên trong reactive chain. Dùng `ReactiveSecurityContextHolder` để lấy `SecurityContext`; dùng `@AuthenticationPrincipal` hoặc `ServerWebExchange.getPrincipal()` ở lớp web. Không dựa vào `ThreadLocal` để nhận diện caller.

Các ví dụ sử dụng **Spring Security Servlet-independent WebFlux**, Spring WebFlux, Reactor, Java 17+, JUnit 5 và `WebTestClient`. Nếu ứng dụng dùng Spring MVC/Servlet, các API reactive trong bài không áp dụng trực tiếp.

## 1. Vì sao WebFlux cần Reactor Context?

### 1.1. ThreadLocal phù hợp với mô hình Servlet truyền thống

Trong một ứng dụng Servlet điển hình, request thường được xử lý trên một thread trong phần lớn vòng đời request. Spring Security có thể đặt `SecurityContext` vào `SecurityContextHolder`, nơi mặc định sử dụng `ThreadLocal`:

~~~text
Servlet request
      |
      v
Servlet thread-17
      |
      +-- SecurityContextHolder.setContext(...)
      |
      +-- Controller
      |
      +-- Service
      |
      +-- SecurityContextHolder.getContext()
      |
      +-- Clear context
~~~

Mô hình này dựa trên thread-bound context. Nếu ứng dụng đổi thread mà không có cơ chế truyền context, thông tin bảo mật có thể không đi theo.

### 1.2. WebFlux không gắn request với một thread cố định

WebFlux được thiết kế cho xử lý non-blocking. Một request có thể chạy trên nhiều thread:

~~~text
HTTP request
    |
    v
event-loop thread A
    |
    +-- decode bearer token
    |
    +-- publishOn(scheduler B)
    |
    v
worker thread B
    |
    +-- gọi service
    |
    +-- flatMap(...)
    |
    v
event-loop thread C
    |
    +-- ghi response
~~~

Nếu identity chỉ nằm trong `ThreadLocal` của thread A, code chạy ở thread B/C có thể không thấy identity đó. Việc cố giữ request trên cùng một thread sẽ đi ngược thiết kế reactive và có thể làm giảm khả năng mở rộng.

Reactor cung cấp **Context** gắn với subscription. Spring Security sử dụng nó để truyền `SecurityContext` qua reactive pipeline.

### 1.3. So sánh hai mô hình

| Khía cạnh | Servlet | WebFlux |
|---|---|---|
| Security holder thường dùng | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| Cơ chế context mặc định | `ThreadLocal` | Reactor `Context` |
| Đơn vị gắn context | Thread | Subscriber/subscription |
| Cách lấy context | Đồng bộ | Reactive, trả `Mono` |
| API xử lý | `SecurityFilterChain`, Servlet filters | `SecurityWebFilterChain`, WebFilters |
| Test web | `MockMvc` | `WebTestClient` |
| Authentication API | `AuthenticationManager` | `ReactiveAuthenticationManager` |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| Opaque introspector | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |

Không chuyển code từ Servlet sang WebFlux chỉ bằng cách đổi controller trả `Mono`. Security configuration, authentication providers và context access cũng phải dùng reactive APIs.

## 2. Reactor Context hoạt động như thế nào?

Reactor `Context` là một cấu trúc key-value bất biến gắn với subscriber. Một operator có thể đọc context trong quá trình subscription và operator `contextWrite` có thể thêm hoặc thay đổi giá trị cho các operator upstream.

Ví dụ:

~~~java
Mono<String> result =
    Mono.deferContextual(context ->
        Mono.just(context.get("requestId"))
    )
    .contextWrite(context ->
        context.put("requestId", "req-123")
    );
~~~

Khi subscribe:

1. `contextWrite` tạo Context có `requestId=req-123`.
2. Context được truyền về phía upstream.
3. `deferContextual` đọc Context tại subscription.
4. Publisher phát ra `req-123`.

Kết quả:

~~~text
Mono source
   |
   v
deferContextual(read requestId)
   |
   v
contextWrite(put requestId)
   |
   v
subscribe
~~~

### 2.1. Context không phải một Map dùng chung toàn ứng dụng

Context thuộc subscription. Hai requests đồng thời có thể có hai giá trị khác nhau:

~~~java
Mono<String> requestA =
    readRequestId()
        .contextWrite(context -> context.put("requestId", "A"));

Mono<String> requestB =
    readRequestId()
        .contextWrite(context -> context.put("requestId", "B"));
~~~

Mỗi subscription nhìn thấy context riêng. Không dùng một biến static hoặc mutable singleton để lưu username/current tenant của request.

### 2.2. Context được đọc trong lúc subscribe

`Mono.just(...)` thường tạo giá trị ngay khi publisher được xây dựng. Nếu cần đọc context, dùng `deferContextual` hoặc API reactive được thiết kế để đọc context khi subscribe.

Ví dụ không phù hợp:

~~~java
// Không thể đọc Reactor Context ở thời điểm tạo publisher theo cách này.
String requestId = "giá trị cần đọc từ Context";
return Mono.just(requestId);
~~~

Cách phù hợp:

~~~java
Mono<String> requestId() {
    return Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("requestId", "unknown"))
    );
}
~~~

Không giữ một giá trị request-specific trong field của singleton service. Service Spring thường được dùng đồng thời bởi nhiều requests.

### 2.3. `contextWrite` tác động theo hướng upstream

Điểm dễ nhầm là `contextWrite` thường được đặt ở phía cuối chuỗi nhưng làm Context có sẵn cho các operator ở phía trước nó:

~~~java
Mono<String> pipeline =
    Mono.deferContextual(context ->
        Mono.just(context.get("caller"))
    )
    .map(String::toUpperCase)
    .contextWrite(context -> context.put("caller", "user-42"));
~~~

Context được ghi ở subscription boundary và các operator upstream có thể đọc. Nếu đặt `contextWrite` ở một nhánh không nằm trong subscription path cần thiết, operator khác có thể không thấy giá trị đó.

## 3. Spring Security đặt SecurityContext vào Reactor Context ra sao?

Trong WebFlux, Spring Security sử dụng các thành phần reactive:

- `WebFilterChainProxy`: điểm vào để chọn `SecurityWebFilterChain`.
- `SecurityWebFilterChain`: tập hợp các WebFilters cho request.
- `AuthenticationWebFilter`: chuyển credential thành authentication thông qua reactive manager.
- `ReactiveAuthenticationManager`: xác minh credential bất đồng bộ.
- `ServerSecurityContextRepository`: lưu/tải `SecurityContext` theo policy của ứng dụng.
- `ReactorContextWebFilter`: đưa context từ repository vào Reactor Context.
- `ReactiveSecurityContextHolder`: API để đọc SecurityContext trong reactive pipeline.
- `SecurityContextServerWebExchangeWebFilter`: cung cấp principal của exchange dựa trên security context.

Sơ đồ khái niệm:

~~~text
HTTP request
    |
    v
WebFilterChainProxy
    |
    v
SecurityWebFilterChain
    |
    v
Bearer token authentication
    |
    +-- JWT -> ReactiveJwtDecoder
    |
    +-- Opaque -> ReactiveOpaqueTokenIntrospector
    |
    v
Authentication thành công
    |
    v
ServerSecurityContextRepository
    |
    v
ReactorContextWebFilter
    |
    v
ReactiveSecurityContextHolder
    |
    +-- Controller
    +-- Service
    +-- Reactive method security
    |
    v
HTTP response
~~~

Tên và thứ tự filter nội bộ có thể thay đổi theo version/cấu hình. Điều cần hiểu là `SecurityContext` được cung cấp trong reactive execution context, không phải một `ThreadLocal` mà service phải tự quản lý.

### 3.1. Authentication thành công mới có principal đáng tin

Trước khi JWT/opaque token được xác minh, bearer string chỉ là credential chưa được xác thực. Sau khi:

- JWT signature và claims validators thành công; hoặc
- Introspection xác nhận opaque token active theo contract;

Spring Security tạo `Authentication` đã xác thực và đặt nó vào security context của pipeline.

Không decode payload JWT bằng Base64 rồi tự đưa `sub` vào Reactor Context. Không lấy `X-User-Id` hoặc `X-Tenant-Id` từ request rồi dùng làm principal.

### 3.2. `SecurityContext` được đọc qua `ReactiveSecurityContextHolder`

API chính:

~~~java
ReactiveSecurityContextHolder.getContext()
~~~

Nó trả về `Mono<SecurityContext>`, không trả `SecurityContext` đồng bộ.

Ví dụ:

~~~java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
~~~

Nếu không có context, `Mono` có thể hoàn tất rỗng. Có thể dùng `switchIfEmpty` hoặc `defaultIfEmpty` theo policy, nhưng không tự tạo authenticated principal giả để che việc thiếu authentication.

## 4. Cấu hình WebFlux Resource Server

Một cấu hình JWT cơ bản:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            ReactiveJwtDecoder jwtDecoder) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtDecoder(jwtDecoder))
            )
            .build();
    }
}
~~~

Các điểm cần chú ý:

- WebFlux dùng `ServerHttpSecurity`, không phải Servlet `HttpSecurity`.
- Bean chain có kiểu `SecurityWebFilterChain`.
- JWT decoder có kiểu `ReactiveJwtDecoder`.
- Authorization được cấu hình qua `authorizeExchange`.
- Token authentication chạy reactive; không gọi decoder đồng bộ trong controller.
- `SCOPE_*` được tạo theo converter/configuration của JWT resource server.

Nếu API chỉ dùng bearer header và không dùng cookie/session tự động gửi từ browser, có thể cân nhắc CSRF policy riêng. Không tắt CSRF chỉ vì token là JWT; hãy đánh giá credential model trước.

### 4.1. Cấu hình issuer và audience

Ví dụ properties cho Reactive Resource Server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/orders
          audiences:
            - orders-api
~~~

Tên và khả năng của properties phụ thuộc Spring Boot version. Nếu tự tạo `ReactiveJwtDecoder`, phải đảm bảo issuer, audience, timestamp, signature algorithm và token profile validators vẫn được áp dụng.

Không dùng `JwtDecoder` Servlet thay cho `ReactiveJwtDecoder`. Nếu phải dùng một thư viện blocking để xác minh token trong WebFlux, cần hiểu tác động lên event loop và chuyển công việc blocking sang scheduler phù hợp; ưu tiên reactive decoder được framework hỗ trợ.

### 4.2. Opaque token

Với opaque token, WebFlux dùng reactive introspection:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(opaque -> opaque
        .introspector(reactiveOpaqueTokenIntrospector)
    )
)
~~~

`ReactiveOpaqueTokenIntrospector` trả `Mono<OAuth2AuthenticatedPrincipal>`. Không gọi Servlet `OpaqueTokenIntrospector` đồng bộ trong reactive request path nếu điều đó tạo blocking network call trên event loop.

## 5. Lấy principal ở controller

Có một số cách hợp lệ tùy dữ liệu controller cần.

### 5.1. Dùng `@AuthenticationPrincipal`

Khi JWT authentication thành công, principal thường là `Jwt`:

~~~java
package com.example.orders.api;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import java.util.Map;

@RestController
public class ProfileController {

    @GetMapping("/api/me")
    Mono<Map<String, Object>> me(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of(
            "subject", jwt.getSubject(),
            "issuer", jwt.getIssuer().toString()
        ));
    }
}
~~~

`@AuthenticationPrincipal` lấy principal từ `Authentication` hiện tại. Trong JWT Resource Server, principal thường là `Jwt`; không phải mọi loại authentication đều có principal kiểu này.

Nếu route có thể nhận JWT và opaque token, không nên cố cast mọi principal thành `Jwt`. Hãy dùng một abstraction phù hợp hoặc nhận `Authentication`.

### 5.2. Dùng `ServerWebExchange.getPrincipal()`

`ServerWebExchange#getPrincipal()` trả về `Mono<P extends Principal>`:

~~~java
@GetMapping("/api/whoami")
Mono<String> whoAmI(ServerWebExchange exchange) {
    return exchange.getPrincipal()
        .map(Principal::getName);
}
~~~

Cách này hữu ích khi controller cần principal chung mà không phụ thuộc trực tiếp vào `Jwt`.

Trong WebFlux, principal là reactive value. Không gọi `.block()` để biến nó thành object đồng bộ trong controller.

### 5.3. Nhận Authentication trong reactive chain

Có thể đọc toàn bộ authentication:

~~~java
@GetMapping("/api/authentication")
Mono<Map<String, Object>> authentication() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(authentication -> Map.of(
            "name", authentication.getName(),
            "authenticated", authentication.isAuthenticated(),
            "authorities", authentication.getAuthorities()
                .stream()
                .map(GrantedAuthority::getAuthority)
                .toList()
        ));
}
~~~

Cách này phù hợp khi cần `Authentication#getName()`, authorities hoặc loại authentication. Không trả toàn bộ token/claims nhạy cảm ra API chỉ để debug.

### 5.4. JWT principal và opaque principal khác nhau

| Resource Server mode | Authentication thường gặp | Principal |
|---|---|---|
| JWT | `JwtAuthenticationToken` | `Jwt` |
| Opaque | `BearerTokenAuthentication` | `OAuth2AuthenticatedPrincipal` |

Với JWT:

~~~java
JwtAuthenticationToken authentication
```

Có thể lấy:

- `authentication.getToken().getSubject()`
- `authentication.getToken().getIssuer()`
- `authentication.getAuthorities()`

Với opaque:

~~~java
BearerTokenAuthentication authentication
```

Principal có thể là `OAuth2AuthenticatedPrincipal` với attributes do introspection response cung cấp.

Không dùng `@AuthenticationPrincipal Jwt` cho endpoint hỗ trợ opaque token nếu controller không có cách xử lý principal khác. Một DTO `CallerIdentity` do ứng dụng định nghĩa có thể chuẩn hóa `(issuer/source, subject, clientId, authorities)` sau khi authentication đã thành công.

## 6. Lấy SecurityContext ở service layer

Controller thường biết route và HTTP input. Service cần identity để thực hiện nghiệp vụ theo user/service caller, tenant hoặc ownership. Trong WebFlux, service nên trả `Mono`/`Flux` và đọc security context bên trong publisher.

### 6.1. Một service lấy current caller

~~~java
package com.example.orders.service;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CurrentCallerService {

    public Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }

    public Mono<Authentication> currentAuthentication() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication);
    }
}
~~~

Các method trả publisher thay vì lấy identity đồng bộ. Khi method được gọi trong request pipeline, context của subscription hiện tại được đọc khi publisher chạy.

### 6.2. Kết hợp principal với truy vấn dữ liệu

~~~java
@Service
public class OrderQueryService {

    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    public Flux<Order> findMyOrders() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .flatMapMany(repository::findByOwnerSubject);
    }
}
~~~

Giả định `OrderRepository#findByOwnerSubject` trả `Flux<Order>`. Query nên giới hạn dữ liệu theo identity đã xác thực. Nếu hệ thống nhiều issuer, chỉ dùng `Authentication#getName()`/`sub` có thể chưa đủ; cần namespace issuer hoặc canonical internal user ID.

### 6.3. Truyền principal rõ ràng hay đọc từ context?

Có hai cách thiết kế:

**Đọc context trong service:**

~~~java
public Flux<Order> findMyOrders() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMapMany(repository::findByOwnerSubject);
}
~~~

Phù hợp khi service thực sự phụ thuộc security context hiện tại và được gọi trong request pipeline.

**Truyền domain identity rõ ràng:**

~~~java
public Flux<Order> findOrdersFor(CallerIdentity caller) {
    return repository.findVisibleTo(caller);
}
~~~

Controller/adapter lấy principal đã xác thực, chuyển thành `CallerIdentity`, rồi truyền vào service. Cách này làm dependency rõ ràng và giúp service dễ unit test hơn. Với domain service dùng trong nhiều context (HTTP, message consumer, scheduled job), truyền identity tường minh thường dễ kiểm soát hơn.

Không truyền raw bearer token xuống business service nếu service chỉ cần subject/tenant/permissions.

### 6.4. Domain identity adapter

Ví dụ một kiểu dữ liệu do ứng dụng định nghĩa:

~~~java
public record CallerIdentity(
    String issuer,
    String subject,
    String clientId,
    CallerKind kind
) {}

public enum CallerKind {
    USER,
    SERVICE
}
~~~

Adapter nhận `Authentication` đã xác thực và tạo domain identity theo token contract:

~~~java
public Mono<CallerIdentity> currentCaller() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(authentication -> {
            if (authentication instanceof JwtAuthenticationToken jwtAuth) {
                Jwt jwt = jwtAuth.getToken();

                return new CallerIdentity(
                    jwt.getIssuer().toString(),
                    jwt.getSubject(),
                    jwt.getClaimAsString("client_id"),
                    CallerKind.USER
                );
            }

            throw new AccessDeniedException(
                "Unsupported authentication type");
        });
}
~~~

Đây chỉ là skeleton cho JWT và giả định issuer/client/caller kind đã được validator kiểm tra. Nếu endpoint nhận service token hoặc opaque token, adapter cần xử lý tương ứng. Không gán mọi JWT thành `USER`; token machine có thể đại diện service.

## 7. Principal trong `flatMap`, `map` và `publishOn`

Một lợi ích quan trọng của Reactor Context là context không gắn với thread hiện tại. Các operator reactive chuẩn giữ context của subscriber qua chuỗi xử lý.

Ví dụ:

~~~java
public Mono<String> loadCallerName() {
    return Mono.defer(() ->
            ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
        )
        .publishOn(Schedulers.parallel())
        .map(String::toUpperCase);
}
~~~

`publishOn` có thể chuyển downstream processing sang scheduler khác. Security context vẫn được truy cập qua Reactor Context của subscription.

### 7.1. Dùng `deferContextual` để kiểm tra Context

Có thể đọc context trực tiếp:

~~~java
Mono<String> debugCaller() {
    return Mono.deferContextual(contextView ->
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .defaultIfEmpty("anonymous")
    );
}
~~~

Trong thực tế, `ReactiveSecurityContextHolder.getContext()` đã là abstraction nên service không cần đọc key nội bộ của Spring Security từ `ContextView`.

### 7.2. `flatMap` giữ context trong inner publisher

~~~java
public Mono<Order> findOrder(String id) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(subject ->
            repository.findById(id)
                .filter(order -> order.getOwnerSubject().equals(subject))
        );
}
~~~

Inner publisher trong cùng reactive chain có thể đọc context theo subscription. Tuy nhiên, khi viết service, truyền `subject` rõ ràng vào repository/policy thường giúp logic dễ đọc và dễ kiểm thử hơn.

### 7.3. Tránh imperative callback không có context

Ví dụ rủi ro:

~~~java
return Mono.fromRunnable(() -> {
    // Không nên giả định ThreadLocal SecurityContext có mặt ở đây.
    String name = SecurityContextHolder.getContext()
        .getAuthentication().getName();
});
~~~

Code trong callback có thể chạy trên thread khác và không có `ThreadLocal` tương ứng. Hãy lấy dữ liệu qua `ReactiveSecurityContextHolder` trong chain rồi truyền giá trị vào callback:

~~~java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .flatMap(name ->
        Mono.fromRunnable(() -> audit(name))
            .thenReturn(name)
    );
~~~

Nếu `audit(...)` là blocking I/O, hãy chuyển nó sang scheduler dành cho blocking work hoặc dùng reactive client/repository. Không chặn event-loop thread.

## 8. Những thao tác làm mất hoặc tách khỏi reactive context

### 8.1. Không dùng `block()` trong request pipeline

Sai:

~~~java
public String currentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName())
        .block();
}
~~~

Vấn đề:

- Tạo blocking boundary trong ứng dụng non-blocking.
- Có thể deadlock hoặc gây lỗi khi gọi trên Reactor non-blocking thread.
- Tạo subscription khác, không còn nằm trong context/lifecycle mong muốn.
- Làm mất backpressure và error propagation.
- Khó kiểm soát cancellation.

Đúng:

~~~java
public Mono<String> currentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
}
~~~

### 8.2. Không tự `subscribe()` trong service

Sai:

~~~java
public Mono<Void> createOrder(Order order) {
    repository.save(order).subscribe();
    return Mono.empty();
}
~~~

`subscribe()` tạo một subscription độc lập. Nó có thể chạy ngoài lifecycle request, không giữ đúng cancellation/error handling và có thể không nhìn thấy context mong đợi.

Đúng:

~~~java
public Mono<Order> createOrder(Order order) {
    return repository.save(order);
}
~~~

Controller/WebFlux runtime sẽ subscribe ở boundary phù hợp. Service nên trả publisher cho caller kết hợp bằng `flatMap`, `then`, `zip` hoặc operator phù hợp.

### 8.3. Không tạo thread tùy ý rồi đọc security context

Sai:

~~~java
new Thread(() -> {
    Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
}).start();
~~~

Thread mới không tự có Reactor Context của request. Nếu phải gửi công việc sang message queue hoặc executor, hãy truyền identity cần thiết dưới dạng message metadata có xác thực và policy rõ; không dựa vào thread-local.

### 8.4. Context không tự biến thành MDC

Reactor Context và logging MDC là hai cơ chế khác nhau. Nếu muốn đưa request ID hoặc caller ID vào MDC khi log, cần context propagation/bridge được cấu hình rõ, chẳng hạn Micrometer Context Propagation theo phiên bản ứng dụng.

Không coi việc MDC có username là bằng chứng security context đang hợp lệ; authorization phải dùng `Authentication` đã xác thực, không dùng log context.

## 9. Reactive method security và principal

WebFlux service có thể dùng method security:

~~~java
@Configuration
@EnableReactiveMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Ví dụ:

~~~java
@Service
public class OrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Flux<Order> findOrders() {
        return repository.findAll();
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    public Mono<Order> create(Order order) {
        return repository.save(order);
    }
}
~~~

Reactive method security dùng Reactor Context để tìm authentication. Method được bảo vệ cần trả kiểu reactive như `Mono` hoặc `Flux` để authorization được thực thi trong reactive flow.

Không dùng annotation reactive method security như thể nó là Servlet method security trên một method trả object đồng bộ rồi kỳ vọng context propagation tự hoạt động.

### 9.1. Kiểm tra cả HTTP authorization và method authorization

Một request có thể qua `authorizeExchange` nhưng bị `@PreAuthorize` từ chối ở service. Test nên xác định rõ policy nằm ở tầng nào:

- HTTP rule: path, method, authority.
- Method rule: quyền gọi business operation.
- Object-level rule: caller có thể đọc/sửa đúng order/tenant đó không.

Không bỏ method security chỉ vì route đã yêu cầu scope. Business service có thể được gọi từ message consumer hoặc một route khác.

### 9.2. Object-level authorization

Ví dụ:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Mono<Order> findOrder(String orderId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(subject ->
            repository.findByIdAndOwnerSubject(orderId, subject)
        );
}
~~~

Ví dụ này kiểm tra scope ở method boundary và ràng buộc truy vấn với subject. Trong hệ thống multi-issuer, nên dùng identity namespace `(issuer, subject)` hoặc internal ID; trong hệ thống multi-tenant, thêm tenant membership/ACL.

## 10. Kiểm thử Reactor Context độc lập bằng StepVerifier

Không phải mọi test đều cần khởi động WebFlux server. Có thể test service đọc context bằng Reactor `StepVerifier`.

### 10.1. Tạo Authentication cho test

~~~java
Authentication authentication =
    new UsernamePasswordAuthenticationToken(
        "user-42",
        "n/a",
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    );
~~~

Đây là authentication test được dựng trực tiếp, không phải kết quả từ OAuth token. Nó chỉ dùng để xác nhận service đọc context.

### 10.2. Đưa authentication vào Reactor Context trong test

~~~java
@Test
void serviceReadsAuthenticationFromReactorContext() {
    Authentication authentication =
        new UsernamePasswordAuthenticationToken(
            "user-42",
            "n/a",
            List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
        );

    Mono<String> result = currentCallerService.currentName()
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(authentication)
        );

    StepVerifier.create(result)
        .expectNext("user-42")
        .verifyComplete();
}
~~~

`ReactiveSecurityContextHolder.withAuthentication(authentication)` tạo `Context` chứa authentication. Test đặt nó vào subscription bằng `contextWrite`.

Không gọi `SecurityContextHolder.setContext(...)` trong test reactive để giả lập cách WebFlux hoạt động; như vậy sẽ kiểm tra sai cơ chế.

### 10.3. Kiểm tra khi context vắng mặt

~~~java
@Test
void serviceCompletesEmptyWhenNoSecurityContextExists() {
    StepVerifier.create(currentCallerService.currentName())
        .verifyComplete();
}
~~~

Nếu service contract yêu cầu caller bắt buộc, có thể chuyển trạng thái rỗng thành lỗi domain/authentication phù hợp:

~~~java
public Mono<String> requiredCallerName() {
    return currentName()
        .switchIfEmpty(Mono.error(
            new IllegalStateException("No authenticated caller")));
}
~~~

Không mặc định `defaultIfEmpty("admin")` hoặc tạo principal fallback có quyền.

### 10.4. Kiểm tra context qua scheduler

~~~java
@Test
void contextIsAvailableAfterPublishOn() {
    Authentication authentication =
        new UsernamePasswordAuthenticationToken(
            "user-42",
            "n/a",
            List.of()
        );

    Mono<String> result = currentCallerService.currentName()
        .publishOn(Schedulers.parallel())
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(authentication)
        );

    StepVerifier.create(result)
        .expectNext("user-42")
        .verifyComplete();
}
~~~

Test này xác nhận context gắn với subscription thay vì thread cụ thể. Không dùng `Thread.sleep` để đợi scheduler; `StepVerifier` điều phối subscription và signal.

## 11. Kiểm tra context không rò rỉ giữa subscribers

Một service singleton có thể phục vụ nhiều requests đồng thời. Security context của một request không được xuất hiện trong request khác.

Ví dụ unit test:

~~~java
@Test
void concurrentSubscribersSeeTheirOwnAuthentication() {
    Authentication userA =
        new UsernamePasswordAuthenticationToken("user-A", "n/a", List.of());

    Authentication userB =
        new UsernamePasswordAuthenticationToken("user-B", "n/a", List.of());

    Mono<String> requestA = currentCallerService.currentName()
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(userA)
        );

    Mono<String> requestB = currentCallerService.currentName()
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(userB)
        );

    StepVerifier.create(Mono.zip(requestA, requestB))
        .assertNext(tuple -> {
            assertThat(tuple.getT1()).isEqualTo("user-A");
            assertThat(tuple.getT2()).isEqualTo("user-B");
        })
        .verifyComplete();
}
~~~

Mỗi publisher nhận context riêng. Không dùng mutable field `currentUser` trong service; nếu làm vậy, hai requests có thể ghi đè dữ liệu của nhau.

### 11.1. Test một request anonymous sau request authenticated

Ở lớp HTTP, gửi lần lượt:

1. Request có JWT mock hoặc Bearer token hợp lệ.
2. Request tiếp theo không có token.
3. Xác nhận request thứ hai bị từ chối ở endpoint private và không nhận principal của request thứ nhất.

Đây là cách phát hiện context persistence sai hoặc test client đã bị mutate với authentication áp dụng cho mọi request.

## 12. Kiểm thử WebFlux bằng WebTestClient và Spring Security

WebFlux sử dụng `WebTestClient`, không dùng MockMvc.

### 12.1. Gắn SecurityWebFilterChain thật

Với application context:

~~~java
@BeforeEach
void setUp() {
    webTestClient = WebTestClient
        .bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();
}
~~~

`springSecurity()` tích hợp Spring Security WebFlux filters vào WebTestClient. Khi dùng `bindToApplicationContext`, test có thể chạy `WebFilterChainProxy` và `SecurityWebFilterChain` của application.

### 12.2. Spring Boot integration test

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class OrdersWebFluxSecurityTests {

    @Autowired
    WebTestClient webTestClient;
}
~~~

Cấu hình này dùng application context thật của Spring Boot. Khi cần kiểm soát filter chain rõ ràng, có thể tự tạo client từ context và áp `springSecurity()`; không áp dụng hai cấu hình trùng lặp mà không hiểu filter registration.

### 12.3. WebFlux slice test

~~~java
@WebFluxTest(controllers = OrdersController.class)
@Import(ApiSecurityConfiguration.class)
class OrdersControllerWebTests {

    @Autowired
    WebTestClient webTestClient;

    @MockitoBean
    OrdersService ordersService;
}
~~~

`@WebFluxTest` chỉ tải MVC/WebFlux slice cần thiết. Import security configuration đúng của ứng dụng và mock các dependency ngoài phạm vi. Với Spring Boot/Spring Framework cũ, dự án có thể dùng `@MockBean` thay cho `@MockitoBean`.

### 12.4. `bindToController` không tự đại diện toàn application security

`WebTestClient.bindToController(...)` thuận tiện cho controller-focused test, nhưng không tự tải toàn bộ `SecurityWebFilterChain` của ứng dụng. Nếu mục tiêu là security integration, dùng `bindToApplicationContext(...).apply(springSecurity())` hoặc Boot test context có security filters được cấu hình.

## 13. Mock principal bằng `mockJwt()` và `mockOpaqueToken()`

Spring Security Test có các request mutators cho WebTestClient:

- `mockUser()`
- `mockJwt()`
- `mockOpaqueToken()`

Chúng giúp test authorization nhanh mà không cần cấp token thật.

### 13.1. `mockJwt()`

~~~java
webTestClient
    .mutateWith(mockJwt()
        .jwt(jwt -> jwt
            .subject("user-42")
            .claim("scope", "orders.read")
        )
        .authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )
    )
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

`mockJwt()` tạo JWT authentication giả lập cho test. Nó không gọi `ReactiveJwtDecoder` và không xác minh chữ ký JWT, issuer hoặc audience theo production decoder.

Nếu test muốn xác nhận converter production map scope từ claims, đừng chỉ truyền authorities trực tiếp; hãy test converter riêng hoặc gửi signed bearer token qua decoder.

### 13.2. `mockOpaqueToken()`

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .attributes(attributes -> {
            attributes.put("sub", "user-42");
            attributes.put("client_id", "web-client");
        })
        .authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )
    )
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

`mockOpaqueToken()` tạo authentication/principal opaque mẫu. Nó không gọi `ReactiveOpaqueTokenIntrospector` và không kiểm tra introspection HTTP client.

### 13.3. `mockUser()`

~~~java
webTestClient
    .mutateWith(mockUser("mai"))
    .get()
    .uri("/api/profile")
    .exchange()
    .expectStatus().isOk();
~~~

Đây là mock user authentication, không phải OAuth2 access token. Dùng cho authorization rule cần một principal đã xác thực, không dùng để chứng minh Resource Server chấp nhận JWT/opaque token.

### 13.4. Những điều mock authentication không chứng minh

| Test helper | Có kiểm tra filter chain? | Có xác minh token thật? | Có gọi decoder/introspector? |
|---|---:|---:|---:|
| `mockUser()` | Có, nếu security WebFilters được gắn | Không | Không |
| `mockJwt()` | Có, nếu security WebFilters được gắn | Không | Không |
| `mockOpaqueToken()` | Có, nếu security WebFilters được gắn | Không | Không |
| `Authorization: Bearer ...` | Có | Có, nếu decoder/introspector thật | Có |
| Bearer header + decoder mock | Có | Không xác minh crypto | Gọi decoder mock |
| Bearer header + test key decoder | Có | Có, bằng test key | Có |
| Bearer header + introspector HTTP stub | Có | Theo contract stub | Có |

## 14. Gửi Bearer token thật qua WebTestClient

Để test authentication pipeline, không dùng `mockJwt()`. Gửi token trong header:

~~~java
webTestClient
    .get()
    .uri("/api/orders")
    .headers(headers ->
        headers.setBearerAuth("test-access-token")
    )
    .exchange()
    .expectStatus().isOk();
~~~

Nếu Resource Server dùng JWT, request đi qua:

~~~text
WebTestClient
   |
   v
WebFilterChainProxy
   |
   v
Bearer authentication WebFilter
   |
   v
ReactiveAuthenticationManager
   |
   v
ReactiveJwtDecoder
   |
   v
SecurityContext / Reactor Context
   |
   v
Authorization
   |
   v
Controller
~~~

### 14.1. Test bearer filter và provider bằng decoder mock

Có thể mock `ReactiveJwtDecoder` để xác nhận bearer token được chuyển tới decoder:

~~~java
given(reactiveJwtDecoder.decode("test-access-token"))
    .willReturn(Mono.just(testJwt));

webTestClient
    .get()
    .uri("/api/orders")
    .headers(headers ->
        headers.setBearerAuth("test-access-token")
    )
    .exchange()
    .expectStatus().isOk();

verify(reactiveJwtDecoder).decode("test-access-token");
~~~

Test này kiểm tra bearer extraction, authentication provider và wiring tới decoder. Vì decoder là mock, nó **không chứng minh chữ ký JWT** được xác minh.

### 14.2. Test chữ ký JWT bằng test key

Để kiểm tra cryptographic validation:

1. Sinh RSA key pair riêng cho test.
2. Tạo JWT bằng private test key.
3. Cấu hình `NimbusReactiveJwtDecoder` dùng public test key.
4. Cấu hình issuer/audience validators.
5. Gửi token qua `Authorization: Bearer`.
6. Xác nhận token ký đúng được chấp nhận.
7. Ký token bằng key pair khác và xác nhận token bị từ chối.
8. Thử issuer, audience và thời hạn sai.

Ví dụ khởi tạo decoder với public key:

~~~java
@Bean
ReactiveJwtDecoder reactiveJwtDecoder(RSAPublicKey publicKey) {
    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder
            .withPublicKey(publicKey)
            .signatureAlgorithm(SignatureAlgorithm.RS256)
            .build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(
            "https://idp.test.example"
        )
    );

    return decoder;
}
~~~

Tùy Spring Security version, có thể bổ sung audience validator bằng `DelegatingOAuth2TokenValidator`. Không dùng private production key trong test.

### 14.3. Test JWKS endpoint qua mock HTTP server

Nếu cần xác nhận reactive decoder tải key qua HTTP:

- Chạy JWKS stub/test server.
- Trả JWK Set chỉ chứa public test key.
- Cấu hình `NimbusReactiveJwtDecoder.withJwkSetUri(testJwksUri)`.
- Gửi signed JWT với `kid` tương ứng.
- Xác nhận token được verify.
- Cập nhật JWKS để test key rotation.
- Cho endpoint timeout/5xx và xác nhận không fail open.

Test bằng public key trực tiếp kiểm tra signature; test JWKS stub kiểm tra cả network retrieval và key selection.

## 15. Kiểm thử opaque introspection trong WebFlux

Với opaque token, cấu hình dùng `ReactiveOpaqueTokenIntrospector`.

### 15.1. Introspector mock cho bearer flow

Một test có thể mock introspector:

~~~java
given(reactiveOpaqueTokenIntrospector.introspect("opaque-test-token"))
    .willReturn(Mono.just(testPrincipal));

webTestClient
    .get()
    .uri("/api/orders")
    .headers(headers ->
        headers.setBearerAuth("opaque-test-token")
    )
    .exchange()
    .expectStatus().isOk();

verify(reactiveOpaqueTokenIntrospector)
    .introspect("opaque-test-token");
~~~

Khác với `.mutateWith(mockOpaqueToken())`, test này gửi bearer header nên filter/provider gọi introspector dependency đã mock.

### 15.2. Test introspection server thật hoặc stub

Để kiểm tra HTTP request và response parsing, dùng test Authorization Server hoặc HTTP stub:

- `active=true` và scope đúng.
- `active=false`.
- Token hết hạn/revoked.
- Client credentials sai.
- Response malformed.
- Timeout/5xx.
- Audience/resource context không đúng.
- Authority mapping từ `scope`/`permissions`.

Đảm bảo `ReactiveOpaqueTokenIntrospector` thật được cấu hình tới test endpoint. Không dùng production introspection credentials.

## 16. Test endpoint đọc principal từ Reactor Context

Giả sử controller:

~~~java
@RestController
public class ContextController {

    @GetMapping("/api/context-name")
    Mono<String> contextName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }
}
~~~

Test với mock JWT:

~~~java
@Test
void controllerReadsJwtPrincipalFromReactiveSecurityContext() {
    webTestClient
        .mutateWith(mockJwt()
            .jwt(jwt -> jwt.subject("user-42"))
        )
        .get()
        .uri("/api/context-name")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("user-42");
}
~~~

Test này xác nhận mock authentication được đưa vào reactive security context và controller đọc được principal. Nó chưa xác minh JWT signature.

### 16.1. Test qua scheduler trong service

Tạo service:

~~~java
@Service
public class ReactiveCallerService {

    public Mono<String> currentNameAcrossScheduler() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .publishOn(Schedulers.parallel())
            .map(String::toUpperCase);
    }
}
~~~

Trong một test WebFlux integration, gọi endpoint sử dụng method này với `mockJwt()` và xác nhận tên principal vẫn có mặt sau scheduler hop.

### 16.2. Test `ServerWebExchange.getPrincipal()`

Controller:

~~~java
@GetMapping("/api/exchange-principal")
Mono<String> principal(ServerWebExchange exchange) {
    return exchange.getPrincipal()
        .map(Principal::getName);
}
~~~

Test tương tự bằng `mockJwt()` hoặc `mockUser()`. Nếu request không authenticated và route không permit anonymous, security layer có thể từ chối trước khi controller được gọi.

## 17. Test `@AuthenticationPrincipal` với JWT

Controller:

~~~java
@GetMapping("/api/jwt-subject")
Mono<String> subject(@AuthenticationPrincipal Jwt jwt) {
    return Mono.just(jwt.getSubject());
}
~~~

Test:

~~~java
webTestClient
    .mutateWith(mockJwt()
        .jwt(jwt -> jwt.subject("user-42"))
    )
    .get()
    .uri("/api/jwt-subject")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class)
    .isEqualTo("user-42");
~~~

Nếu controller nhận opaque token, principal mặc định không phải `Jwt`. Hãy viết controller/adapter nhận kiểu abstraction phù hợp thay vì cast mù quáng.

Một controller hỗ trợ cả hai có thể nhận `Authentication` qua cơ chế argument resolution phù hợp hoặc đọc `ReactiveSecurityContextHolder`, sau đó chuẩn hóa các principal đã xác thực thành domain caller.

## 18. Test reactive method security

Ví dụ service:

~~~java
@Service
public class SecureOrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Flux<Order> findAll() {
        return repository.findAll();
    }
}
~~~

Cấu hình method security:

~~~java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

WebTestClient test:

- Gọi endpoint dùng service bằng `mockJwt()` có `SCOPE_orders.read`: được phép.
- Gọi cùng endpoint bằng `mockJwt()` không có scope: bị từ chối.
- Gửi signed bearer token với scope đúng: kiểm tra decoder + method security.
- Xác nhận repository không được gọi nếu method security từ chối.

Reactive method security cần return publisher để authorization nằm trong reactive execution. Nếu method trả `Order` đồng bộ, đừng giả định `ReactiveSecurityContextHolder` được xử lý giống method trả `Mono<Order>`.

## 19. Test 401, 403 và principal absence

Các tình huống phổ biến:

| Request | Kết quả thường gặp | Ý nghĩa |
|---|---:|---|
| Không token vào private route | 401 | Chưa authenticated |
| JWT malformed/invalid | 401 | Authentication thất bại |
| Opaque inactive | 401 | Introspection từ chối |
| JWT hợp lệ, thiếu scope | 403 | Authorization thất bại |
| JWT hợp lệ, tenant sai | 403/404 theo policy | Business authorization |
| `permitAll` route không token | 200 nếu controller thành công | Authentication không bắt buộc |
| Anonymous principal gọi service đòi context | Theo service contract | Context có thể vắng hoặc là anonymous |
| Mock JWT có scope đúng | 200 nếu rule cho phép | Authorization test, không verify token |
| Bearer token thật có scope đúng | 200 nếu decoder và policy đúng | Authentication + authorization pipeline |

Trong WebFlux, lỗi authentication/authorization được xử lý bởi các reactive entry points/handlers. Không dùng Servlet `AuthenticationEntryPoint` hoặc `AccessDeniedHandler` trực tiếp; các API tương ứng thường là `ServerAuthenticationEntryPoint` và `ServerAccessDeniedHandler`.

## 20. Context và principal khi dùng nhiều loại token

Một Resource Server có thể hỗ trợ JWT và opaque token. Controller không nên giả định:

~~~java
Jwt jwt = (Jwt) authentication.getPrincipal();
~~~

Opaque token thường có `OAuth2AuthenticatedPrincipal`. Có thể tạo adapter:

~~~java
public Mono<CallerIdentity> currentCaller() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(authentication -> {
            Object principal = authentication.getPrincipal();

            if (principal instanceof Jwt jwt) {
                return new CallerIdentity(
                    jwt.getIssuer().toString(),
                    jwt.getSubject()
                );
            }

            if (principal instanceof OAuth2AuthenticatedPrincipal opaque) {
                return new CallerIdentity(
                    "trusted-introspection-source",
                    opaque.getName()
                );
            }

            throw new AccessDeniedException(
                "Unsupported principal type");
        });
}
~~~

`CallerIdentity` và `"trusted-introspection-source"` là ví dụ domain mapping. Trong production, identity source phải lấy từ issuer/introspection configuration đáng tin, không phải chuỗi tùy ý do request gửi.

Nếu dùng multi-issuer, canonical identity thường cần `(issuer, subject)`. Hai token có cùng `sub` nhưng khác issuer không tự đại diện cùng người.

## 21. Reactor Context không phải nơi lưu business state tùy tiện

Có thể lưu request-scoped metadata trong Reactor Context, nhưng không nên biến nó thành một kho dữ liệu mutable:

- Không lưu entity lớn hoặc toàn bộ request body.
- Không lưu raw access token nếu chỉ cần subject.
- Không lưu mutable map dùng chung.
- Không dùng Context thay database/cache.
- Không dùng custom context key làm bằng chứng authentication.
- Không đặt `isAdmin=true` từ request header rồi tin ở service.

Security identity phải đến từ Spring Security authentication đã xác minh. Các giá trị như trace ID/correlation ID có thể nằm trong Reactor Context nhưng phải có nguồn và semantics riêng.

## 22. Những lỗi thường gặp khi đọc principal trong WebFlux

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `ReactiveSecurityContextHolder.getContext()` hoàn tất rỗng | Request không authenticated hoặc code chạy ngoài security subscription | Kiểm tra chain, bearer token và subscription boundary |
| `SecurityContextHolder.getContext()` rỗng | Dùng Servlet ThreadLocal API trong reactive code | Dùng `ReactiveSecurityContextHolder` |
| Controller thấy JWT nhưng service không thấy | Service tạo subscription độc lập hoặc gọi `subscribe()` | Kết hợp publisher trong cùng chain |
| Context mất sau `publishOn` | Đọc ThreadLocal hoặc custom callback không reactive | Đọc bằng reactive holder; truyền value rõ ràng |
| Principal null trong controller | Endpoint anonymous/permitAll hoặc security chain không áp dụng | Kiểm tra matcher và authentication |
| Cast `Jwt` thất bại | Request dùng opaque token hoặc authentication type khác | Dùng abstraction/adapter |
| Test pass nhưng production decoder không chạy | Dùng `mockJwt()` | Gửi Bearer header thật |
| Test principal từ request trước xuất hiện | Dùng mutable singleton/thread-local state hoặc test client bị mutate dùng chung | Dùng subscriber-scoped context và client riêng |
| `block()` gây lỗi event-loop | Blocking trong reactive pipeline | Trả `Mono`/`Flux` và compose operators |
| Method security không hoạt động | Chưa bật `@EnableReactiveMethodSecurity` hoặc method không trả Publisher | Cấu hình reactive method security và return `Mono`/`Flux` |
| `exchange.getPrincipal()` không có giá trị | Không có authentication trong exchange context | Kiểm tra authentication filter/repository |
| Opaque token gọi blocking introspection | Dùng Servlet introspector trong WebFlux | Dùng `ReactiveOpaqueTokenIntrospector` |

## 23. Anti-pattern cần tránh

### 23.1. Dùng `SecurityContextHolder` trong WebFlux

~~~java
// Sai cho reactive request context.
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

Dùng:

~~~java
ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication);
~~~

### 23.2. Gọi `block()` để lấy username

~~~java
String name = ReactiveSecurityContextHolder.getContext()
    .map(context -> context.getAuthentication().getName())
    .block();
~~~

Đây là blocking boundary và có thể tách subscription. Hãy trả `Mono<String>`.

### 23.3. Tự subscribe trong service

~~~java
repository.findAll().subscribe();
return Mono.empty();
~~~

Không để service tự tạo subscription không được quản lý. Trả publisher để caller điều khiển lifecycle.

### 23.4. Lưu current user vào field của singleton

~~~java
@Service
class BadCallerService {
    private String currentUser;
}
~~~

Nhiều requests đồng thời sẽ ghi đè giá trị. Dùng Reactor Context hoặc truyền `CallerIdentity` rõ ràng.

### 23.5. Đưa principal vào custom Context mà không xác minh

Không tạo custom `Context` từ header `X-User`, JWT payload chưa verify hoặc query parameter rồi coi đó là authenticated principal.

### 23.6. Dùng `mockJwt()` để chứng minh chữ ký token

Mock JWT chỉ phục vụ authorization test. Dùng signed JWT và `ReactiveJwtDecoder` thật khi cần kiểm tra token validation.

### 23.7. Dùng Servlet security classes trong WebFlux

Không dùng `HttpSecurity`, `SecurityFilterChain`, `JwtDecoder`, `OpaqueTokenIntrospector` hoặc `MockMvc` cho reactive security path. Dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveJwtDecoder`, `ReactiveOpaqueTokenIntrospector` và `WebTestClient`.

### 23.8. Dùng context như biến global

Không dùng `Hooks.onEachOperator` hoặc custom global mutable state để lưu current principal nếu chưa có thiết kế context propagation rõ ràng. Security context đã có abstraction chuẩn.

## 24. Test matrix cho Reactor Context và principal

| Test | Setup | Kỳ vọng |
|---|---|---|
| Principal trong controller | WebTestClient + `mockJwt()` | Controller đọc được subject |
| Principal qua exchange | `exchange.getPrincipal()` | `Mono<Principal>` có name |
| SecurityContext trong service | `contextWrite(withAuthentication(...))` + StepVerifier | Service đọc đúng name |
| Không có context | StepVerifier không gắn context | Publisher rỗng hoặc lỗi theo contract |
| Scheduler hop | `publishOn` rồi đọc context | Principal vẫn đúng |
| Concurrent subscribers | Hai contexts khác nhau | Không rò user A sang B |
| Mock JWT authorization | `mockJwt()` + authority | HTTP rule hoạt động |
| Mock opaque authorization | `mockOpaqueToken()` | Opaque principal mapping/authority rule hoạt động |
| JWT bearer thật | Header Bearer + test decoder | Decoder được gọi |
| JWT chữ ký thật | Signed token + reactive decoder/test key | Signature và validators được kiểm tra |
| Opaque bearer flow | Header Bearer + reactive introspector | Introspector được gọi |
| Method security | `@EnableReactiveMethodSecurity` + publisher method | Scope đúng qua, scope thiếu bị từ chối |
| Missing token | Private route, không Authorization | 401 |
| Wrong scope | Authentication mock/token hợp lệ thiếu authority | 403 |
| Context isolation | Auth request rồi anonymous request | Không có context cũ |
| No blocking | Reactor pipeline không gọi block | Không block event loop |

## 25. Debug theo thứ tự

Khi principal không xuất hiện ở service layer, hãy kiểm tra theo trình tự:

1. Request có đi vào đúng `SecurityWebFilterChain` không?
2. `securityMatcher`/`pathMatchers` có chọn chain khác không?
3. Request có gửi đúng `Authorization: Bearer ...` không?
4. JWT decoder hoặc opaque introspector có thành công không?
5. `Authentication` đã được tạo với principal mong đợi chưa?
6. Code service có chạy trong cùng reactive subscription với request không?
7. Có `block()`, nested `subscribe()` hoặc thread/executor tự tạo không?
8. Code có dùng nhầm `SecurityContextHolder` Servlet không?
9. Có custom `ServerSecurityContextRepository` làm thay đổi context persistence không?
10. Method security có được bật và method có return `Publisher` không?
11. Controller có dùng đúng principal type cho JWT/opaque không?
12. Test có đang dùng mock authentication nên bỏ qua decoder không?

Có thể tạm quan sát `authentication.getClass().getSimpleName()`, principal type và authority names trong test logs. Tránh log raw token, toàn bộ claims PII hoặc credentials.

## 26. Câu hỏi tự kiểm tra

**1.** Vì sao WebFlux không nên dùng `SecurityContextHolder` như Servlet?

> Vì WebFlux không gắn request với một thread cố định; `SecurityContextHolder` mặc định dựa trên ThreadLocal, còn WebFlux dùng Reactor Context.

**2.** API nào đọc SecurityContext trong reactive pipeline?

> `ReactiveSecurityContextHolder.getContext()`, trả về `Mono<SecurityContext>`.

**3.** Reactor Context gắn với thread hay subscriber?

> Subscriber/subscription; context đi theo reactive execution thay vì thread cụ thể.

**4.** `publishOn` có tự làm mất Reactor Context không?

> Không. Reactor Context được thiết kế để đi theo subscription qua các operator reactive chuẩn; vấn đề thường đến từ ThreadLocal hoặc subscription tách rời.

**5.** Vì sao không gọi `block()` để lấy principal?

> Vì nó tạo blocking boundary và có thể tạo subscription tách khỏi request pipeline; hãy trả `Mono` và compose reactive operators.

**6.** Vì sao không tự `subscribe()` trong service?

> Vì service tách lifecycle/error/cancellation khỏi caller và có thể không giữ context mong đợi.

**7.** Controller lấy JWT principal bằng cách nào?

> Có thể dùng `@AuthenticationPrincipal Jwt` khi route chỉ nhận JWT, hoặc đọc `Authentication` qua `ReactiveSecurityContextHolder`.

**8.** `ServerWebExchange.getPrincipal()` trả gì?

> Một `Mono<Principal>`.

**9.** Principal của opaque token có luôn là `Jwt` không?

> Không. Thường là `OAuth2AuthenticatedPrincipal`; authentication thường là `BearerTokenAuthentication`.

**10.** `mockJwt()` có xác minh chữ ký JWT không?

> Không. Nó tạo mock authentication cho test authorization.

**11.** Muốn test reactive bearer filter và decoder cần làm gì?

> Gửi `Authorization: Bearer ...` qua WebTestClient và cấu hình decoder test thật hoặc mock theo mục tiêu test.

**12.** `@EnableReactiveMethodSecurity` dùng để làm gì?

> Bật method security theo reactive context, ví dụ `@PreAuthorize` trên method trả `Mono`/`Flux`.

**13.** Làm sao test service đọc SecurityContext mà không chạy WebFlux server?

> Dùng `StepVerifier` và `contextWrite(ReactiveSecurityContextHolder.withAuthentication(authentication))`.

**14.** Vì sao singleton service không được lưu `currentUser` trong field?

> Vì nhiều subscribers/requests đồng thời có thể ghi đè giá trị của nhau.

**15.** Context của user A có thể tự động sang request user B không?

> Không khi dùng Reactor Context đúng cách; mỗi subscription có context riêng. Rò rỉ thường do mutable global state, ThreadLocal hoặc test wiring sai.

**16.** `Reactor Context` có tự đồng bộ dữ liệu sang MDC không?

> Không. Logging MDC là cơ chế khác; cần context propagation bridge riêng nếu muốn.

## 27. Tài liệu tham khảo

- [Spring Security — Reactive Applications](https://docs.spring.io/spring-security/reference/reactive/index.html): kiến trúc Spring Security WebFlux và reactive security context.
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder`, JWT bearer authentication và authorities.
- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): `ReactiveOpaqueTokenIntrospector` và opaque authentication.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, `@PreAuthorize` và Publisher return types.
- [Spring Security — Reactive Test Support](https://docs.spring.io/spring-security/reference/reactive/test/index.html): WebTestClient và reactive security testing.
- [Spring Security — Testing OAuth 2.0 with WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()`, `mockOpaqueToken()` và OAuth test support.
- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): đọc/ghi SecurityContext trong Reactor Context.
- [Spring Security — ReactorContextWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ReactorContextWebFilter.html): đưa security context từ repository vào reactive context.
- [Spring Security — SecurityContextServerWebExchangeWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/SecurityContextServerWebExchangeWebFilter.html): principal access qua `ServerWebExchange`.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): context semantics, `contextWrite`, `deferContextual`.
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): `publishOn`, `subscribeOn` và scheduler behavior.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): WebFlux integration test và client binding modes.

**Kết luận:** Spring Security WebFlux đưa authentication vào **Reactor Context** để principal theo đúng subscriber của request. Controller có thể dùng `@AuthenticationPrincipal` hoặc `ServerWebExchange.getPrincipal()`; service nên đọc bằng `ReactiveSecurityContextHolder` hoặc nhận domain identity được truyền tường minh. Reactor Context tiếp tục hoạt động qua các operator reactive và scheduler hops, nhưng không tự bảo vệ code tạo subscription mới hoặc dùng ThreadLocal. Hãy dùng `StepVerifier` để kiểm tra context isolation, `WebTestClient` với security filters thật để kiểm tra pipeline, và phân biệt `mockJwt()`/`mockOpaqueToken()` với Bearer token thực cần decoder/introspector xác minh.
