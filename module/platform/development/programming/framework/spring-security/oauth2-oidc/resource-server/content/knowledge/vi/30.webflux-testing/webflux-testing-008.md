# Kiểm thử multi-tenant và lựa chọn reactive authentication manager

Một **Spring Security WebFlux Resource Server multi-tenant** có thể xác minh access token theo nhiều bộ quy tắc: mỗi tenant có Authorization Server, issuer, signing keys, introspection endpoint, audience hoặc permission model riêng. Ứng dụng cần giải quyết hai việc: **resolve tenant** để chọn chiến lược xác thực, và **propagate tenant** đã xác minh tới authorization cùng tầng dữ liệu.

Trong WebFlux, thành phần điều phối chính là **ReactiveAuthenticationManagerResolver<ServerWebExchange>**. Resolver nhận ServerWebExchange và trả về một **ReactiveAuthenticationManager** phù hợp dưới dạng Mono. Manager đó mới xác minh token.

Khi kiểm thử, cần tách hai mục tiêu:

- Kiểm tra authorization sau khi Authentication đã có: dùng **WebTestClient** với **mockJwt()**, **mockOpaqueToken()** hoặc Authentication test phù hợp.
- Kiểm tra việc lựa chọn manager thực sự: gửi **Authorization: Bearer** qua SecurityWebFilterChain để Bearer authentication filter gọi resolver; dùng manager test double hoặc decoder/introspector stub.

Nếu chỉ dùng mockJwt() hoặc mockOpaqueToken(), test có thể chứng minh tenant policy sau authentication nhưng không chứng minh resolver đã chọn đúng manager.

## 1. Multi-tenancy ở Resource Server nghĩa là gì?

Spring Security xem Resource Server là multi-tenant khi có **nhiều chiến lược xác minh Bearer token**, được lựa chọn dựa trên một tenant identifier.

Ví dụ:

| Tenant | Issuer / Authorization Server | Token strategy | Audience |
|---|---|---|---|
| tenant-a | https://id-a.example.com | JWT/JWKS | orders-api-a |
| tenant-b | https://id-b.example.com | JWT/JWKS | orders-api-b |
| partner-c | https://partner.example.com | Opaque/introspection | partner-api |

Một hệ thống cũng có thể có nhiều tenants cùng issuer, nhưng mỗi tenant có tenant claim, client policy hoặc audience khác nhau.

**Multi-tenant không chỉ là thêm claim tenant_id vào JWT.** Resource Server cần chọn đúng validator/manager, xác minh token theo đúng trust contract, sau đó bảo đảm request chỉ truy cập dữ liệu thuộc tenant đã được xác thực.

### 1.1. Hai giai đoạn: resolve và propagate

~~~mermaid
flowchart TD
    R[HTTP request + Bearer token] --> T[Resolve tenant / strategy]
    T --> M[ReactiveAuthenticationManager phù hợp]
    M --> V[Verify token: signature hoặc introspection]
    V -->|Không hợp lệ| DENY[Authentication failure]
    V -->|Hợp lệ| A[Authentication đã xác thực]
    A --> P[Propagate tenant từ claims/principal đã xác minh]
    P --> Z[Authorization: scope, role, tenant, ownership]
    Z -->|Đủ quyền| DATA[Repository query giới hạn tenant]
    Z -->|Thiếu quyền| FORBID[403 hoặc policy 404]
~~~

**Resolve tenant** chọn manager nào được gọi. **Propagate tenant** bảo đảm kết quả xác thực mang theo tenant identity đã được xác minh để các tầng sau dùng đúng.

Một resolver chọn manager tenant-a nhưng controller lại lấy tenant từ query parameter do client gửi thì hệ thống vẫn có nguy cơ cross-tenant access.

### 1.2. Những gì cần tách biệt

| Thành phần | Trả lời câu hỏi |
|---|---|
| Tenant resolver | Request thuộc tenant/strategy nào? |
| ReactiveAuthenticationManager | Token có hợp lệ theo strategy đó không? |
| ReactiveJwtDecoder | JWT signature và claims có hợp lệ không? |
| ReactiveOpaqueTokenIntrospector | Opaque token có active và attributes nào? |
| Authentication principal | Ai đang gọi, thuộc tenant nào? |
| Authorization | Principal có quyền trên endpoint/resource này không? |
| Repository/domain policy | Dữ liệu trả về có giới hạn đúng tenant/owner không? |

Không coi việc resolver trả manager là bằng chứng token đã hợp lệ. Resolver chỉ định tuyến; manager xác minh credential.

## 2. ReactiveAuthenticationManagerResolver hoạt động thế nào?

Interface tổng quát:

~~~java
public interface ReactiveAuthenticationManagerResolver<C> {
    Mono<ReactiveAuthenticationManager> resolve(C context);
}
~~~

Với WebFlux Resource Server, context thường là **ServerWebExchange**:

~~~java
ReactiveAuthenticationManagerResolver<ServerWebExchange>
~~~

Resolver trả về một ReactiveAuthenticationManager trong Mono. Manager có phương thức authenticate nhận Authentication request và trả Mono<Authentication>:

~~~java
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
~~~

Với Bearer authentication, request object được tạo từ HTTP Bearer token thường là **BearerTokenAuthenticationToken**.

Luồng xử lý khái niệm:

~~~text
HTTP request
  -> BearerTokenAuthenticationWebFilter
  -> AuthenticationConverter tạo BearerTokenAuthenticationToken
  -> ReactiveAuthenticationManagerResolver.resolve(exchange)
  -> Mono<ReactiveAuthenticationManager>
  -> manager.authenticate(authentication)
  -> Mono<Authentication>
  -> SecurityContext
  -> authorization
~~~

### 2.1. Vì sao resolver nhận ServerWebExchange?

ServerWebExchange cung cấp ngữ cảnh của request:

- HTTP method và path.
- Host và request headers.
- Query parameters.
- Server request/response.
- Attributes do các web filters đáng tin cậy đặt vào exchange.

Resolver có thể dùng route, host hoặc metadata được gateway xác minh để chọn manager. Tuy nhiên, **không phải mọi thông tin trong request đều đáng tin**. Header do client tự gửi không được trở thành nguồn xác định tenant có quyền truy cập.

### 2.2. Chọn manager không đồng nghĩa xác minh token

Ví dụ resolver dựa trên path:

~~~text
/t/tenant-a/** -> manager tenant-a
/t/tenant-b/** -> manager tenant-b
~~~

Nếu request tới /t/tenant-a/orders mang token của tenant-b, manager tenant-a phải từ chối token hoặc policy phải từ chối tenant mismatch sau khi token được xác minh.

Không chuyển sang manager tenant-b để “thử xem token có hợp lệ không”. Việc fallback qua nhiều trust domains có thể làm token được chấp nhận ngoài chính sách endpoint.

## 3. Chọn tenant bằng issuer claim với JwtIssuerReactiveAuthenticationManagerResolver

Khi mỗi tenant có một issuer JWT riêng, cách trực tiếp là dùng **JwtIssuerReactiveAuthenticationManagerResolver**.

Ví dụ:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;

JwtIssuerReactiveAuthenticationManagerResolver resolver =
    JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(
        "https://id-a.example.com",
        "https://id-b.example.com"
    );

http
    .authorizeExchange(authorize -> authorize
        .anyExchange().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .authenticationManagerResolver(resolver)
    );
~~~

Resolver đọc claim **iss** trong Bearer JWT để xác định issuer, rồi chọn JWT-based ReactiveAuthenticationManager tương ứng.

### 3.1. Issuer phải nằm trong danh sách tin cậy

Một JWT chưa xác minh có thể tự khai:

~~~json
{
  "iss": "https://attacker.example.net",
  "sub": "admin",
  "tenant_id": "tenant-a"
}
~~~

Giá trị iss chưa được verify chỉ có thể làm **routing hint** tới một issuer đã được allowlist. Nó không chứng minh token do issuer đó phát hành.

Không được đọc iss tùy ý rồi tự tạo ReactiveJwtDecoder/JWKS client cho bất kỳ URL nào. Cách đó có thể mở trust boundary tới Authorization Server do attacker kiểm soát và gây SSRF.

Dùng:

~~~java
JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(
    "https://id-a.example.com",
    "https://id-b.example.com"
);
~~~

hoặc một registry do hệ thống quản trị kiểm soát.

### 3.2. Manager được tạo lazy

Spring Security có thể tạo manager cho issuer khi request đầu tiên mang issuer tương ứng xuất hiện. Điều này giúp ứng dụng khởi động mà không cần tất cả Authorization Servers phải sẵn sàng ngay tại startup.

Đổi lại, request đầu tiên có thể phải chờ discovery/JWKS initialization. Hãy kiểm:

- Timeout và network dependency khi khởi tạo.
- Cache decoder/manager.
- Issuer allowlist.
- Behavior khi issuer không khả dụng.
- Metrics cho lần resolve/initialize đầu tiên.

### 3.3. Audience vẫn phải được kiểm riêng

Issuer A đáng tin không có nghĩa mọi token của issuer A đều dùng được cho mọi Resource Server.

Ví dụ token:

~~~json
{
  "iss": "https://id-a.example.com",
  "aud": ["billing-api"],
  "tenant_id": "tenant-a",
  "scope": "billing.read"
}
~~~

không được chấp nhận ở orders-api chỉ vì issuer đúng. Decoder/validators của manager tenant-a phải kiểm audience, thời hạn và token profile phù hợp.

## 4. Dynamic tenant registry

Khi tenant có thể được thêm hoặc gỡ trong runtime, có thể duy trì một registry:

~~~java
Map<String, ReactiveAuthenticationManager> managers;
~~~

Với nhiều request đồng thời, dùng cấu trúc phù hợp như **ConcurrentHashMap** hoặc một registry bất biến được thay thế atomically.

Spring Security hỗ trợ khởi tạo **JwtIssuerReactiveAuthenticationManagerResolver** bằng một strategy resolve issuer thành manager. Ví dụ:

~~~java
import java.util.Map;

import reactor.core.publisher.Mono;

import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;

Map<String, ReactiveAuthenticationManager> managers = loadTrustedManagers();

ReactiveAuthenticationManagerResolver<String> issuerResolver =
    issuer -> Mono.justOrEmpty(managers.get(issuer));

JwtIssuerReactiveAuthenticationManagerResolver resolver =
    new JwtIssuerReactiveAuthenticationManagerResolver(issuerResolver);
~~~

Trong ví dụ, key của map là issuer đã được tin cậy. Issuer không có trong map sẽ không có manager.

### 4.1. Tạo manager cho tenant mới

Một quy trình quản trị có thể:

1. Kiểm tra tenant được phép onboard.
2. Xác nhận issuer URL từ cấu hình đã được quản trị.
3. Tải metadata/JWKS hoặc dựng introspector theo trust policy.
4. Tạo ReactiveAuthenticationManager.
5. Đăng ký manager vào registry.
6. Kiểm tra health/metrics trước khi mở traffic.
7. Có quy trình remove manager và cache khi tenant bị disable.

Nếu discovery API có thao tác blocking, không chạy nó trên Reactor event loop. Spring Security minh họa việc tạo ReactiveJwtDecoder từ issuer location trong Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic()).

~~~java
Mono<ReactiveAuthenticationManager> createJwtManager(String issuer) {
    return Mono.fromCallable(
            () -> ReactiveJwtDecoders.fromIssuerLocation(issuer)
        )
        .subscribeOn(Schedulers.boundedElastic())
        .map(JwtReactiveAuthenticationManager::new);
}
~~~

Chỉ gọi hàm này sau khi issuer đã được xác nhận từ tenant registry tin cậy. Không cho request đầu tiên tự đăng ký issuer mới.

### 4.2. Cập nhật registry an toàn

Khi thêm/xóa tenant:

- Dùng thread-safe registry.
- Tránh map mutable không đồng bộ giữa các request.
- Không xóa manager đang được request sử dụng theo cách gây lỗi giữa chừng.
- Có version/config revision cho tenant registry.
- Không để tenant đã disable được tái tạo manager qua lazy fallback.
- Audit ai thay đổi issuer, audience, introspection URI hoặc signing keys.

## 5. Chọn manager theo path, host hoặc trusted request metadata

Không phải mọi tenant đều có JWT issuer riêng. Một hệ thống có thể dùng cùng một gateway/issuer nhưng tách strategy theo route hoặc host.

Ví dụ:

~~~text
https://tenant-a.api.example.com/** -> manager A
https://tenant-b.api.example.com/** -> manager B
/api/partners/**                   -> opaque manager
/api/internal/**                   -> JWT manager
~~~

Có thể triển khai resolver riêng:

~~~java
import java.util.Map;

import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

class TenantPathAuthenticationManagerResolver
        implements ReactiveAuthenticationManagerResolver<ServerWebExchange> {

    private final Map<String, ReactiveAuthenticationManager> managers;

    TenantPathAuthenticationManagerResolver(
            Map<String, ReactiveAuthenticationManager> managers) {
        this.managers = Map.copyOf(managers);
    }

    @Override
    public Mono<ReactiveAuthenticationManager> resolve(
            ServerWebExchange exchange) {

        String path = exchange.getRequest().getPath().value();
        String tenant;

        if (path.startsWith("/t/tenant-a/")) {
            tenant = "tenant-a";
        }
        else if (path.startsWith("/t/tenant-b/")) {
            tenant = "tenant-b";
        }
        else {
            return Mono.error(unknownTenant());
        }

        ReactiveAuthenticationManager manager = this.managers.get(tenant);
        if (manager == null) {
            return Mono.error(unknownTenant());
        }

        return Mono.just(manager);
    }

    private OAuth2AuthenticationException unknownTenant() {
        OAuth2Error error = new OAuth2Error(
            OAuth2ErrorCodes.INVALID_TOKEN,
            "No authentication strategy is configured for this tenant",
            null
        );
        return new OAuth2AuthenticationException(error);
    }
}
~~~

Ví dụ trên dùng path để minh họa routing. Trong production, manager tương ứng vẫn phải kiểm token thuộc đúng tenant, issuer và audience. Path do client chọn không tự cấp quyền truy cập tenant.

### 5.1. Dùng host

Nếu dùng hostname để chọn tenant, phải kiểm host thuộc domain đã đăng ký. Cần xét:

- Host header do client gửi.
- TLS SNI và ingress host routing.
- Reverse proxy có ghi đè host hay không.
- Alias domain và custom domain.
- Host normalization.
- Request backend có thể được gọi trực tiếp không.

Không dùng host bất kỳ để tạo decoder hoặc introspection URL.

### 5.2. Dùng forwarded headers

Nếu gateway gửi X-Tenant-ID hoặc Forwarded, chỉ tin giá trị do gateway được quản lý xác lập sau khi gateway xóa header cùng tên do client gửi.

Không dùng header X-Tenant-ID tùy ý làm căn cứ authorization. Sau khi manager xác minh token, phải kiểm tenant trong principal/claims đã xác minh khớp tenant được chọn.

### 5.3. ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver

Spring Security có **ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver** để chọn manager dựa trên ServerWebExchange và request matchers.

Nó hữu ích khi có nhiều quy tắc path/host/header và cần cấu trúc resolver theo matcher. Với một vài route đơn giản, một lambda hoặc class triển khai ReactiveAuthenticationManagerResolver thường dễ đọc hơn.

Dù dùng builder hay custom resolver, vẫn cần default behavior rõ ràng. Request không match tenant nào phải bị từ chối, không rơi vào manager mặc định quá rộng.

## 6. Chọn giữa JWT manager và opaque manager

Một tenant có thể dùng JWT; tenant khác dùng opaque token.

| Token strategy | Thành phần xác minh | Manager |
|---|---|---|
| JWT | ReactiveJwtDecoder | JwtReactiveAuthenticationManager |
| Opaque token | ReactiveOpaqueTokenIntrospector | OpaqueTokenReactiveAuthenticationManager |

Ví dụ dựng hai managers:

~~~java
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.authentication.OpaqueTokenReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

ReactiveAuthenticationManager jwtManager(ReactiveJwtDecoder decoder) {
    return new JwtReactiveAuthenticationManager(decoder);
}

ReactiveAuthenticationManager opaqueManager(
        ReactiveOpaqueTokenIntrospector introspector) {
    return new OpaqueTokenReactiveAuthenticationManager(introspector);
}
~~~

Resolver có thể chọn manager theo route/tenant registry. Không nên cho cả hai manager cùng thử một Bearer token đến khi một cái thành công nếu không có trust contract rõ.

### 6.1. JWT manager

JwtReactiveAuthenticationManager dùng ReactiveJwtDecoder để:

- Decode JWT.
- Verify chữ ký theo key/algorithm được cấu hình.
- Chạy validators.
- Chuyển Jwt thành Authentication và authorities.

Tenant-specific decoder cần kiểm issuer, audience và những claims liên quan tenant.

### 6.2. Opaque manager

OpaqueTokenReactiveAuthenticationManager dùng ReactiveOpaqueTokenIntrospector để lấy OAuth2AuthenticatedPrincipal.

Mỗi tenant có thể có introspection endpoint và client authentication riêng. Không dùng introspection URI hoặc client credentials do request tự cung cấp.

Introspection timeout, AS 5xx hoặc token inactive phải dẫn tới authentication failure. Không tạo principal mặc định để giữ availability.

### 6.3. Không dùng JWT parsing để quyết định opaque strategy

Opaque token không có JWT issuer claim để resolver đáng tin cậy đọc. Không dựa vào số dấu chấm, độ dài hoặc hình thức chuỗi để quyết định token là JWT hay opaque.

Nếu tenant đã xác định loại token qua route/configuration, dùng manager tương ứng. Nếu tenant dùng nhiều token formats, cần một cơ chế phân loại được quản trị và kiểm thử rõ ràng, không fallback qua các trust domains.

## 7. Gắn resolver vào SecurityWebFilterChain

Ví dụ cấu hình WebFlux:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.server.ServerWebExchange;

@Configuration
class MultiTenantResourceServerConfiguration {

    @Bean
    SecurityWebFilterChain api(
            ServerHttpSecurity http,
            ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver) {

        return http
            .authorizeExchange(authorize -> authorize
                .pathMatchers("/public/**").permitAll()
                .pathMatchers("/t/**/admin/**")
                    .hasAuthority("SCOPE_admin")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(resolver)
            )
            .build();
    }
}
~~~

Đây là cấu hình minh họa. Cần định nghĩa tenant-specific authorization policy và validators ở các managers. permitAll() cho public routes không có nghĩa các route protected khác được bỏ qua.

### 7.1. Một SecurityWebFilterChain hay nhiều chains?

Nếu các tenant dùng cùng bộ filters và chỉ khác manager, một chain với AuthenticationManagerResolver có thể phù hợp.

Nếu các nhóm route có CSRF, CORS, session, entry point hoặc authorization policy khác nhau, nhiều SecurityWebFilterChain chuyên biệt có thể dễ kiểm soát hơn. Trong trường hợp nhiều chains, cần kiểm thứ tự match để chain rộng không chọn request trước chain tenant-specific.

### 7.2. Resolver không thay authorization

Manager tenant-a xác thực thành công token không có nghĩa token được phép gọi mọi endpoint tenant-a.

Sau authentication vẫn cần kiểm:

- Scope/role.
- Audience/resource.
- Tenant claim.
- User/client status.
- Ownership.
- HTTP method và domain operation.

## 8. Propagate tenant sau khi Authentication thành công

Tenant phải được lấy từ dữ liệu **đã xác minh**.

Với JWT, có thể có claim:

~~~json
{
  "iss": "https://id-a.example.com",
  "sub": "user-1001",
  "aud": ["orders-api-a"],
  "tenant_id": "tenant-a",
  "scope": "orders.read"
}
~~~

Với opaque token, introspection principal có thể có attributes tương ứng:

~~~json
{
  "active": true,
  "sub": "user-1001",
  "tenant_id": "tenant-a",
  "scope": "orders.read"
}
~~~

Sau khi xác minh, controller/service có thể lấy tenant từ principal. Không lấy tenant từ query parameter hoặc header chưa được trust.

### 8.1. Đọc tenant từ JWT principal

~~~java
@GetMapping("/api/orders")
Mono<OrderPage> orders(@AuthenticationPrincipal Jwt jwt) {
    String tenantId = jwt.getClaimAsString("tenant_id");
    String subject = jwt.getSubject();

    return orderService.findOrders(tenantId, subject);
}
~~~

Ví dụ giả định tenant_id là claim bắt buộc. Production cần xử lý trường hợp claim thiếu/sai kiểu và từ chối theo contract.

### 8.2. Đọc tenant từ opaque principal

~~~java
@GetMapping("/api/orders")
Mono<OrderPage> orders(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

    String tenantId = principal.getAttribute("tenant_id");
    String subject = principal.getAttribute("sub");

    return orderService.findOrders(tenantId, subject);
}
~~~

Principal của opaque token không phải Jwt. Không ép mọi OAuth2 principal thành JwtAuthenticationToken.

### 8.3. Tenant trong Reactor Context

WebFlux truyền SecurityContext qua Reactor Context. Khi cần lấy Authentication trong reactive service:

~~~java
Mono<String> tenantId =
    ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(authentication ->
            ((OAuth2AuthenticatedPrincipal) authentication.getPrincipal())
                .getAttribute("tenant_id")
        );
~~~

Ví dụ rút gọn giả định principal là OAuth2AuthenticatedPrincipal. Trong code production, nên có abstraction xử lý cả Jwt và opaque principal.

Không dùng ThreadLocal hoặc static mutable field để lưu tenant hiện tại. Các request reactive có thể đổi thread và chạy đồng thời.

### 8.4. Tenant route và tenant claim phải khớp

Nếu route đã chọn tenant-a, nhưng JWT sau khi xác minh mang tenant_id=tenant-b, phải từ chối.

~~~text
resolved tenant = tenant-a
verified token tenant_id = tenant-b

=> reject
~~~

Nếu chỉ kiểm tenant từ path và bỏ qua tenant trong token, client có thể đưa token của tenant khác tới route được chọn và gây cross-tenant confusion.

## 9. Kiểm thử multi-tenant: phân chia các mục tiêu

Không có một test duy nhất chứng minh toàn bộ multi-tenant behavior. Nên chia thành các lớp:

| Loại test | Câu hỏi |
|---|---|
| Resolver unit test | Request context có chọn đúng manager không? |
| Filter-chain routing test | Authorization Bearer có thực sự đi qua resolver không? |
| JWT integration test | Issuer, signature, audience và tenant claims có được verify không? |
| Opaque integration test | Introspection đúng tenant endpoint và attributes không? |
| Authorization test | Scope/role/tenant/owner có được kiểm không? |
| Concurrency test | Hai tenants có bị lẫn SecurityContext hoặc dữ liệu không? |
| Failure test | Unknown tenant, manager lỗi, timeout có fail-closed không? |

### 9.1. Gắn Spring Security vào WebTestClient

Để kiểm tra filter chain trong application context, có thể tạo client như sau:

~~~java
WebTestClient webTestClient = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

Test cần có dependency spring-security-test tương thích với Spring Security runtime. Nếu dùng WebFlux slice test, bảo đảm SecurityWebFilterChain và resolver thực sự được nạp vào test context.

### 9.2. Dùng mockJwt()/mockOpaqueToken() khi kiểm authorization

Spring Security Test cung cấp:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;
~~~

Ví dụ JWT tenant-a:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .claim("iss", "https://id-a.example.com")
        .claim("sub", "alice")
        .claim("tenant_id", "tenant-a")
        .claim("aud", List.of("orders-api-a"))
        .claim("scope", "orders.read")
    ))
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Ví dụ opaque principal tenant-a:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .attributes(attributes -> {
            attributes.put("sub", "alice");
            attributes.put("tenant_id", "tenant-a");
            attributes.put("scope", "orders.read");
        })
    )
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Những test này phù hợp để kiểm controller, method security và tenant authorization sau khi Authentication đã được cung cấp.

**Chúng không chứng minh AuthenticationManagerResolver đã chọn đúng manager.** Các mutators tạo Authentication trong test exchange; chúng không gửi Bearer credential qua resolver như một request production.

### 9.3. Dùng Bearer header thật để kiểm resolver

Để kiểm resolver được gọi qua Resource Server filter chain, gửi Authorization header bình thường:

~~~java
webTestClient
    .get()
    .uri("/t/tenant-a/orders")
    .headers(headers -> headers.setBearerAuth("test-token-a"))
    .exchange()
    .expectStatus().isOk();
~~~

Trong test này, SecurityWebFilterChain phải cấu hình oauth2ResourceServer với resolver. Resolver trả manager tương ứng, rồi manager test double xác thực token.

Không dùng mockJwt() hoặc mockOpaqueToken() trong test mục tiêu là kiểm lựa chọn manager.

## 10. Test resolver bằng ReactiveAuthenticationManager test doubles

Một cách đơn giản là dựng manager giả cho mỗi tenant. Manager trả Authentication có principal name thể hiện tenant đã chọn.

~~~java
import java.util.Map;

import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

Map<String, ReactiveAuthenticationManager> managers = Map.of(
    "tenant-a", managerFor("tenant-a"),
    "tenant-b", managerFor("tenant-b")
);

ReactiveAuthenticationManager managerFor(String tenant) {
    return authentication -> {
        if (!(authentication instanceof BearerTokenAuthenticationToken)) {
            return Mono.error(invalidToken());
        }

        return Mono.just(
            new UsernamePasswordAuthenticationToken(
                tenant,
                null,
                AuthorityUtils.createAuthorityList("SCOPE_orders.read")
            )
        );
    };
}

ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver =
    exchange -> {
        String path = exchange.getRequest().getPath().value();
        String tenant;
        if (path.startsWith("/t/tenant-a/")) {
            tenant = "tenant-a";
        }
        else if (path.startsWith("/t/tenant-b/")) {
            tenant = "tenant-b";
        }
        else {
            return Mono.error(unknownTenant());
        }

        return Mono.justOrEmpty(managers.get(tenant))
            .switchIfEmpty(Mono.error(unknownTenant()));
    };

OAuth2AuthenticationException invalidToken() {
    return new OAuth2AuthenticationException(
        new OAuth2Error(OAuth2ErrorCodes.INVALID_TOKEN, "Invalid test credential", null)
    );
}

OAuth2AuthenticationException unknownTenant() {
    return new OAuth2AuthenticationException(
        new OAuth2Error(OAuth2ErrorCodes.INVALID_TOKEN, "Unknown tenant route", null)
    );
}
~~~

Đây là **test double** để chứng minh routing. Manager trên không xác minh JWT signature, introspection, issuer hay tenant claim. Không dùng nó trong production.

Trong production, manager phải verify token theo tenant-specific trust contract. Nếu request không có tenant manager, resolver cần tạo authentication failure rõ ràng hoặc không resolve manager theo behavior đã được kiểm thử; không dùng một manager mặc định chấp nhận mọi token.

### 10.1. Gắn resolver vào test SecurityWebFilterChain

~~~java
@Bean
SecurityWebFilterChain testApi(
        ServerHttpSecurity http,
        ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver) {

    return http
        .authorizeExchange(authorize -> authorize
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .authenticationManagerResolver(resolver)
        )
        .build();
}
~~~

Controller test có thể trả Authentication name:

~~~java
@GetMapping("/whoami")
Mono<String> whoami(Authentication authentication) {
    return Mono.just(authentication.getName());
}
~~~

Gửi:

~~~java
webTestClient
    .get()
    .uri("/t/tenant-a/whoami")
    .headers(headers -> headers.setBearerAuth("test-token-a"))
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("tenant-a");
~~~

Test tenant-b tương tự. Như vậy test chứng minh request Bearer thực sự đi qua manager resolver và manager được chọn tạo ra principal tương ứng.

### 10.2. Kiểm token tenant-b trên route tenant-a

Manager test double nên từ chối token không thuộc tenant của nó. Ví dụ:

~~~java
ReactiveAuthenticationManager managerFor(String tenant) {
    return authentication -> {
        if (!(authentication instanceof BearerTokenAuthenticationToken bearer)) {
            return Mono.error(invalidToken());
        }

        if (!("token-" + tenant).equals(bearer.getToken())) {
            return Mono.error(invalidToken());
        }

        return Mono.just(
            new UsernamePasswordAuthenticationToken(
                tenant,
                null,
                AuthorityUtils.createAuthorityList("SCOPE_orders.read")
            )
        );
    };
}
~~~

Sau đó:

~~~java
webTestClient
    .get()
    .uri("/t/tenant-a/orders")
    .headers(headers -> headers.setBearerAuth("token-tenant-b"))
    .exchange()
    .expectStatus().isUnauthorized();
~~~

Đây vẫn chỉ là test routing/manager contract bằng token giả. JWT integration test phải kiểm chữ ký/issuer/audience/tenant claim thật bằng decoder và test keys.

## 11. Unit test resolver độc lập

Resolver có thể được kiểm trực tiếp với MockServerWebExchange mà không cần khởi động toàn bộ WebFlux application.

Ví dụ khái niệm:

~~~java
MockServerWebExchange exchange =
    MockServerWebExchange.from(
        MockServerHttpRequest.get("/t/tenant-a/orders").build()
    );

StepVerifier.create(resolver.resolve(exchange))
    .expectNext(tenantAManager)
    .verifyComplete();
~~~

Các trường hợp cần có:

- Path tenant-a trả manager A.
- Path tenant-b trả manager B.
- Path không thuộc tenant nào trả authentication failure.
- Host không nằm trong registry bị từ chối.
- Tenant đã disable không resolve được manager.
- Trusted forwarded tenant metadata được xử lý theo policy.
- Request không thể làm resolver tự tạo manager từ một tenant key tùy ý.

Unit test này kiểm logic resolver. Nó không chứng minh BearerTokenAuthenticationWebFilter đã gọi resolver đúng; cần thêm filter-chain test ở phần trước.

## 12. Kiểm thử JwtIssuerReactiveAuthenticationManagerResolver

Khi chọn manager theo issuer, nên có các tests:

1. JWT issuer A được route tới manager A.
2. JWT issuer B được route tới manager B.
3. Issuer không nằm trong trusted list bị từ chối.
4. JWT malformed hoặc thiếu issuer bị từ chối.
5. JWT issuer đúng nhưng signature sai bị từ chối.
6. JWT issuer đúng nhưng audience sai bị từ chối.
7. JWT issuer đúng nhưng tenant claim không khớp policy bị từ chối.

### 12.1. Test với signed JWT và test JWKS server

Một integration test có thể:

- Tạo test RSA/EC key pair cho issuer A và B.
- Dựng metadata/JWKS endpoint trong test server.
- Cấu hình resolver với trusted issuer URLs.
- Ký JWT cho từng issuer.
- Gửi Authorization Bearer qua WebTestClient.
- Xác nhận manager/decoder đúng được dùng.
- Gửi JWT có issuer lạ hoặc signature sai và xác nhận 401.

Không dùng mockJwt() để chứng minh issuer resolver đã đọc claim iss và tải đúng key. mockJwt() cung cấp Authentication giả lập thay cho luồng xác minh JWT thật.

### 12.2. Issuer claim chưa xác minh chỉ dùng để chọn candidate

Resolver có thể đọc iss từ Bearer JWT trước khi decoder xác minh chữ ký. Vì vậy, allowlist là bắt buộc.

Sau khi chọn manager, JwtReactiveAuthenticationManager/decoder phải xác minh signature và issuer. Không để iss chưa verify quyết định một URL tùy ý được gọi.

## 13. Kiểm thử opaque multi-tenant với ReactiveOpaqueTokenIntrospector

Với opaque token, tenant thường được chọn từ route/host/tenant registry vì token không có JWT claims để Resource Server tự đọc.

Mỗi manager có thể dùng một ReactiveOpaqueTokenIntrospector riêng:

~~~java
ReactiveAuthenticationManager tenantA =
    new OpaqueTokenReactiveAuthenticationManager(introspectorA);

ReactiveAuthenticationManager tenantB =
    new OpaqueTokenReactiveAuthenticationManager(introspectorB);
~~~

Test với introspector stub:

~~~java
ReactiveOpaqueTokenIntrospector introspectorA = token -> {
    if (!"token-a".equals(token)) {
        return Mono.error(new BadOpaqueTokenException("Invalid token"));
    }

    Map<String, Object> attributes = Map.of(
        "sub", "alice",
        "tenant_id", "tenant-a",
        "scope", "orders.read"
    );

    OAuth2AuthenticatedPrincipal principal =
        new DefaultOAuth2AuthenticatedPrincipal(
            "alice",
            attributes,
            AuthorityUtils.createAuthorityList("SCOPE_orders.read")
        );

    return Mono.just(principal);
};
~~~

Introspector B có contract riêng cho tenant-b.

### 13.1. Kiểm tra đúng introspector được gọi

Dùng spy/mock hoặc test introspector có counter để kiểm:

- Route tenant-a gọi introspector A.
- Route tenant-b gọi introspector B.
- Token tenant-b gửi vào tenant-a không được introspector B cứu.
- Unknown tenant không gọi bất kỳ introspector nào.
- Inactive token không tạo Authentication.
- Timeout/5xx không fail-open.

Khi dùng mockOpaqueToken(), những introspectors này không được gọi. Để test integration, gửi Authorization Bearer header thật qua filter chain.

### 13.2. Không chia sẻ client credentials sai tenant

Introspection client credentials là server-side secret. Không lấy client ID/secret từ header hoặc request parameter để chọn introspection endpoint.

Mỗi tenant manager phải dùng credential và TLS policy được quản trị cho tenant đó. Không log raw token hoặc introspection client secret.

## 14. Test tenant propagation và cross-tenant authorization

Resolver chọn manager đúng chưa đủ. Principal phải mang tenant đúng và repository phải lọc theo tenant.

Ví dụ policy:

~~~text
GET /t/tenant-a/orders
  token tenant-a + SCOPE_orders.read -> cho phép

GET /t/tenant-a/orders
  token tenant-b + SCOPE_orders.read -> từ chối

GET /t/tenant-a/orders/42
  token tenant-a nhưng không phải owner -> từ chối

GET /t/tenant-a/orders/42
  token tenant-a, đúng owner -> cho phép
~~~

### 14.1. Ma trận test

| Request route | Token tenant | Scope | Resource tenant | Kết quả |
|---|---|---|---|---|
| tenant-a | tenant-a | orders.read | tenant-a | Cho phép nếu đúng owner/policy |
| tenant-a | tenant-b | orders.read | tenant-a | Từ chối |
| tenant-b | tenant-b | orders.read | tenant-b | Cho phép nếu đúng owner/policy |
| tenant-b | tenant-a | orders.read | tenant-b | Từ chối |
| tenant-a | tenant-a | orders.write | tenant-a, GET-only | Từ chối nếu cần read |
| tenant-a | tenant-a | orders.read | tenant-b | Từ chối |
| tenant-a | unknown issuer | orders.read | tenant-a | Authentication failure |

### 14.2. Scope không thay thế tenant authorization

Một token có SCOPE_orders.read không được tự đọc mọi orders trên mọi tenants. Repository query nên giới hạn tenant và subject:

~~~java
Flux<Order> findByTenantIdAndOwnerSubject(
    String tenantId,
    String subject
);
~~~

Không tải dữ liệu toàn hệ thống rồi lọc trong controller. Điều đó có thể làm lộ dữ liệu qua pagination, logs, metrics hoặc một nhánh code quên lọc.

### 14.3. Tenant từ route phải khớp tenant từ principal

Nếu path là /t/tenant-a/orders, nhưng principal có tenant_id=tenant-b, reject. Không âm thầm thay tenant principal bằng path tenant.

Một cách triển khai là tạo domain identity object sau khi xác minh Authentication:

~~~java
record TenantIdentity(
    String tenantId,
    String subject,
    Collection<GrantedAuthority> authorities
) {}
~~~

Adapter chuyển JWT/opaque principal thành TenantIdentity và kiểm các trường bắt buộc. Các service dùng TenantIdentity thay vì tự đọc request headers.

## 15. Test tenant metadata từ gateway

Nếu gateway gửi:

~~~http
X-Verified-Tenant: tenant-a
~~~

thì test phải xác nhận:

1. Gateway xóa header cùng tên do client gửi.
2. Chỉ gateway tin cậy được phép kết nối backend hoặc backend xác thực nguồn gateway.
3. Backend dùng header này để chọn manager theo registry.
4. Manager xác minh token có issuer/audience/tenant claim đúng.
5. Principal sau xác minh mang tenant phù hợp.
6. Nếu header tenant-a nhưng token tenant-b, request bị từ chối.

Không chỉ test resolver nhận header và trả manager. Đó là test logic routing, chưa chứng minh header thực sự đáng tin.

Nếu không có gateway trust boundary được xác lập, dùng host/path đã được cấu hình và vẫn kiểm tenant trong token sau authentication.

## 16. Unknown tenant và fail-closed behavior

Các tình huống phải được định nghĩa:

| Tình huống | Hành vi mong muốn |
|---|---|
| Không có tenant route/host | Từ chối hoặc 404 theo API contract |
| Tenant chưa onboard | Không có manager, không tạo tự động |
| Tenant đã disabled | Từ chối |
| Issuer không trusted | Authentication failure |
| Manager không tồn tại | Authentication failure |
| JWT signature invalid | 401 |
| JWT audience/tenant sai | 401 hoặc policy denial theo contract |
| Opaque token inactive | 401 |
| Introspection timeout/5xx | Không tạo Authentication |
| Manager registry unavailable | Fail closed cho route cần xác thực |

**Không dùng default manager chấp nhận mọi token** khi resolver không tìm được tenant.

Nếu muốn trả 404 cho unknown tenant để không tiết lộ tenant registry, đó là API routing policy; authentication vẫn phải fail-closed.

### 16.1. Không fallback sang tenant khác

~~~text
Thử manager tenant-a
  token invalid
    -> thử tenant-b
      token active
        -> authenticated
~~~

Nếu tenant-a đã được chọn bởi route hoặc trusted issuer, lỗi xác minh phải kết thúc request. Fallback có thể khiến credential của tenant-b vượt qua ranh giới tenant-a.

### 16.2. Timeout và cancellation

Resolver/manager/introspector trả Mono. Nếu downstream AS chậm:

- Đặt timeout phù hợp ở HTTP client/introspection layer.
- Không block() trong resolver hoặc manager.
- Không tự subscribe() để chạy xác minh ở background.
- Propagate cancellation khi client ngắt request.
- Có giới hạn concurrency/connection pool.
- Không retry vô hạn.
- Không trả Authentication thành công khi upstream timeout.

## 17. Reactive context và isolation giữa tenants

WebFlux có thể xử lý nhiều requests đồng thời trên cùng event-loop threads. Không lưu tenant hoặc Authentication vào ThreadLocal/static mutable field.

Ví dụ:

~~~text
Request A:
  tenant-a
  subject=alice

Request B:
  tenant-b
  subject=bob
~~~

Mỗi request phải giữ SecurityContext và tenant identity riêng trong Reactor Context/request pipeline.

### 17.1. Test concurrency

Một integration test có thể gửi nhiều requests đồng thời:

~~~text
GET /t/tenant-a/whoami + token-a
GET /t/tenant-b/whoami + token-b
GET /t/tenant-a/orders + token-a
GET /t/tenant-b/orders + token-b
~~~

Kiểm:

- Response của tenant-a không chứa subject/tenant-b.
- Manager A không được gọi với token B.
- Authorities không bị chia sẻ giữa requests.
- Tenant cache/registry không giữ principal của request trước.
- Cancellation của một request không ảnh hưởng request khác.

Không dùng một mutable test principal hoặc singleton variable để lưu tenant hiện tại.

## 18. Test cache và lifecycle của tenant manager

Manager có thể được cache theo issuer/tenant để tránh dựng decoder hoặc introspector lặp lại.

Cần kiểm:

- Manager được tạo một lần theo registry policy.
- Hai request đồng thời đầu tiên không tạo duplicate managers ngoài ý muốn.
- Tenant disable làm manager không còn được resolve cho request mới.
- Manager đang xử lý request có lifecycle được kiểm soát.
- Key/JWKS refresh hoạt động khi issuer rotate key.
- Credential introspection được rotate theo secret lifecycle.
- Cache không giữ manager của tenant đã bị xóa.
- Không có cache key collision giữa issuers/tenants.

Nếu manager registry được cập nhật động, test cả cập nhật đồng thời và request đang chạy. Dùng immutable snapshot/atomic replacement hoặc concurrent map với semantics được hiểu rõ.

## 19. Phân biệt resolver test với mockJwt()/mockOpaqueToken()

| Công cụ | Mục tiêu phù hợp | Có kiểm resolver qua Bearer filter không? |
|---|---|---|
| mockJwt() | JWT principal/claims và authorization | Không |
| mockOpaqueToken() | Opaque principal/attributes và authorization | Không |
| mockAuthentication(...) | Một Authentication tùy chỉnh | Không |
| Direct resolver unit test | Logic chọn manager theo ServerWebExchange | Kiểm resolver, không kiểm filter chain |
| WebTestClient + Authorization Bearer + test managers | Manager selection qua Resource Server filter | Có |
| WebTestClient + signed JWT + ReactiveJwtDecoder/JWKS | JWT verification và issuer routing | Có |
| WebTestClient + introspector stub | Opaque manager/introspection selection | Có |

### 19.1. Vì sao mock mutators không kiểm resolver?

mockJwt() và mockOpaqueToken() tạo Authentication test trong exchange để controller/authorization sử dụng. Chúng hữu ích khi token cryptography không phải mục tiêu của test.

Nhưng khi đã có Authentication giả lập, test không cần đi qua Bearer token extraction và ReactiveAuthenticationManagerResolver. Do đó, nếu mục tiêu là chứng minh tenant-a route gọi manager A, phải gửi Authorization Bearer header bình thường qua filter chain.

### 19.2. Kết hợp các loại test

Một bộ test tốt thường có:

- Unit tests cho tenant registry và resolver.
- WebTestClient filter-chain tests với fake managers.
- Authorization tests với mockJwt()/mockOpaqueToken().
- JWT integration tests với test key/JWKS.
- Opaque integration tests với ReactiveOpaqueTokenIntrospector stub hoặc HTTP test server.
- Multi-node/consistency tests nếu manager/revocation state được phân tán.

Không cần một test dựng toàn bộ Authorization Server cho mọi scenario; chọn mức test theo điều cần chứng minh.

## 20. Ví dụ test ma trận tenant bằng WebTestClient

Giả sử test manager trả principal name là tenant được chọn và cấp SCOPE_orders.read.

Positive case:

~~~java
@Test
void tenantARequestUsesTenantAManager() {
    webTestClient
        .get()
        .uri("/t/tenant-a/whoami")
        .headers(headers -> headers.setBearerAuth("token-tenant-a"))
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("tenant-a");
}
~~~

Tenant B:

~~~java
@Test
void tenantBRequestUsesTenantBManager() {
    webTestClient
        .get()
        .uri("/t/tenant-b/whoami")
        .headers(headers -> headers.setBearerAuth("token-tenant-b"))
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("tenant-b");
}
~~~

Cross-tenant:

~~~java
@Test
void tenantBTokenIsRejectedOnTenantARoute() {
    webTestClient
        .get()
        .uri("/t/tenant-a/whoami")
        .headers(headers -> headers.setBearerAuth("token-tenant-b"))
        .exchange()
        .expectStatus().isUnauthorized();
}
~~~

Unknown route:

~~~java
@Test
void unknownTenantDoesNotFallBackToDefaultManager() {
    webTestClient
        .get()
        .uri("/t/tenant-unknown/whoami")
        .headers(headers -> headers.setBearerAuth("some-token"))
        .exchange()
        .expectStatus().isUnauthorized();
}
~~~

Status cụ thể phụ thuộc failure handler/entry point và route contract. Nếu unknown tenant được xử lý ở router trước security, API có thể chọn 404; điều quan trọng là không xác thực request bằng manager của tenant khác.

## 21. Những anti-pattern cần tránh

**Tin tenant header do client tự gửi.** Có thể chọn manager hoặc tenant dữ liệu trái phép.

**Đọc issuer chưa verify rồi tạo decoder cho URL bất kỳ.** Mở trust boundary và nguy cơ SSRF.

**Chọn manager bằng token string shape.** Số dấu chấm/độ dài không chứng minh token là JWT hay opaque.

**Fallback sang manager tenant khác khi authentication thất bại.** Có thể vượt ranh giới tenant.

**Chỉ kiểm route, không kiểm tenant claim.** Token của tenant khác có thể đi vào route đã chọn.

**Chỉ kiểm tenant claim, không kiểm audience.** Token dành cho resource khác có thể bị chấp nhận.

**Dùng mockJwt() để tuyên bố resolver đã chạy.** Test mutator inject Authentication thay vì đi qua Bearer manager resolution.

**Dùng mockOpaqueToken() để tuyên bố introspection đúng.** Nó không gọi ReactiveOpaqueTokenIntrospector.

**Dùng ThreadLocal lưu tenant trong WebFlux.** Context có thể bị lẫn giữa các requests.

**Dùng default manager rộng khi tenant không resolve được.** Unknown tenant không được phép trở thành authenticated.

**Dùng một manager/service principal cho mọi tenant mà không ràng buộc audience/tenant.** Có thể tạo cross-tenant privilege confusion.

**Lưu principal vào singleton mutable field.** Requests đồng thời có thể rò rỉ identity.

**Block event loop khi discovery/introspection.** Làm giảm throughput và có thể gây starvation.

**Fail-open khi introspection timeout hoặc registry lỗi.** Không có bằng chứng xác thực tin cậy.

**Chỉ test success case.** Cần cross-tenant, unknown issuer, wrong audience, inactive token và manager failure.

## 22. Quy trình triển khai và kiểm thử

**Bước 1 — Lập tenant registry.** Ghi tenant ID, trusted issuer, audience, token strategy, JWKS/introspection endpoint và trạng thái active.

**Bước 2 — Chọn nguồn tenant.** JWT issuer claim, route/host hoặc metadata từ trusted gateway. Ghi rõ nguồn nào chỉ dùng routing và nguồn nào được dùng authorization.

**Bước 3 — Dựng ReactiveAuthenticationManager riêng.** JwtReactiveAuthenticationManager hoặc OpaqueTokenReactiveAuthenticationManager với decoder/introspector tenant-specific.

**Bước 4 — Viết resolver.** Trả Mono<ReactiveAuthenticationManager>; unknown tenant/issuer phải bị từ chối.

**Bước 5 — Gắn vào SecurityWebFilterChain.** Dùng oauth2ResourceServer().authenticationManagerResolver(...).

**Bước 6 — Propagate tenant đã xác minh.** JWT claim hoặc introspection attributes được giữ trong principal/Authentication; so khớp với route tenant nếu có.

**Bước 7 — Áp authorization.** Scope, role, audience, tenant, subject và resource ownership.

**Bước 8 — Test resolver độc lập.** MockServerWebExchange cho path/host/registry mapping.

**Bước 9 — Test qua filter chain.** Authorization Bearer header thật với manager test doubles.

**Bước 10 — Test JWT/opaque thật ở mức integration.** Signed JWT/JWKS hoặc ReactiveOpaqueTokenIntrospector stub/HTTP server.

**Bước 11 — Test cross-tenant và failure modes.** Token tenant B trên route A, issuer lạ, audience sai, inactive token, timeout, disabled tenant.

**Bước 12 — Test concurrency và lifecycle.** Nhiều tenants đồng thời, registry update, manager cache, event-loop/context isolation.

## 23. Câu hỏi tự kiểm tra

**1. ReactiveAuthenticationManagerResolver nhận loại context nào trong WebFlux Resource Server?**

Thường là ServerWebExchange.

**2. resolve() trả về gì?**

Mono<ReactiveAuthenticationManager>.

**3. ReactiveAuthenticationManager làm gì?**

Nhận Authentication request và trả Mono<Authentication> sau khi xác minh.

**4. JwtIssuerReactiveAuthenticationManagerResolver chọn manager theo gì?**

Issuer claim iss trong Bearer JWT, nhưng issuer phải nằm trong tập tin cậy.

**5. Có thể tạo decoder cho issuer tùy ý từ token chưa verify không?**

Không. Chỉ dùng trusted issuer registry/allowlist.

**6. Khi nào dùng resolver theo path/host?**

Khi route hoặc host đã được cấu hình/quản lý xác định strategy cho tenant, đồng thời token vẫn được manager kiểm issuer/audience/tenant.

**7. mockJwt() có kiểm manager resolver không?**

Không. Nó cung cấp Authentication test trực tiếp để kiểm authorization.

**8. Cách test resolver qua filter chain là gì?**

Gửi Authorization Bearer header bình thường qua WebTestClient và dùng ReactiveAuthenticationManager test doubles.

**9. Opaque token multi-tenant chọn manager bằng gì?**

Thường dùng route/host/tenant registry đã được tin cậy để chọn ReactiveOpaqueTokenIntrospector tương ứng.

**10. Vì sao phải so tenant claim với route tenant?**

Để token của tenant khác không được sử dụng trên route tenant hiện tại.

**11. Tenant có nên được lưu trong ThreadLocal của WebFlux không?**

Không. Dùng principal/Authentication và Reactor Context.

**12. Nếu manager tenant-a từ chối token, có nên thử manager tenant-b không?**

Không. Authentication failure phải kết thúc theo trust policy đã chọn.

## Kết luận

Trong Spring Security WebFlux multi-tenant Resource Server, **ReactiveAuthenticationManagerResolver<ServerWebExchange>** chọn manager theo tenant/request context; **ReactiveAuthenticationManager** xác minh token theo trust policy tương ứng. Với nhiều JWT issuers, **JwtIssuerReactiveAuthenticationManagerResolver** cung cấp cách chọn manager theo iss trong tập issuer được tin cậy. Với tenant dùng opaque token hoặc định tuyến theo path/host, có thể xây resolver riêng dựa trên registry được quản trị.

Kiểm thử cần phân biệt rõ **manager selection**, **token validation** và **tenant authorization**. mockJwt()/mockOpaqueToken() phù hợp để kiểm principal, scope và policy sau authentication; muốn chứng minh resolver được gọi phải gửi Authorization Bearer qua WebTestClient và dùng manager test doubles hoặc decoder/introspector integration.

Cuối cùng, tenant phải được propagate từ claims/principal đã xác minh, so khớp với tenant được route chọn và dùng trong repository/domain authorization. **Unknown tenant, issuer lạ, token sai audience hoặc manager failure phải fail-closed; không fallback sang trust domain khác.**

### Tài liệu tham khảo

- [Spring Security — Reactive OAuth 2.0 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html)
- [Spring Security API — ReactiveAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManagerResolver.html)
- [Spring Security API — JwtIssuerReactiveAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html)
- [Spring Security API — ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver.html)
- [Spring Security — Reactive OAuth 2.0 Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Security — Reactive Authentication Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security API — JwtReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtReactiveAuthenticationManager.html)
- [Spring Security API — OpaqueTokenReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenReactiveAuthenticationManager.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
