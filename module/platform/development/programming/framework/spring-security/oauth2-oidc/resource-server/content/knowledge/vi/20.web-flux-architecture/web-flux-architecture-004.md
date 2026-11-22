# ReactiveAuthenticationManager cho JWT hoặc opaque token

## 1. Mục tiêu của bài học

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, WebFlux xử lý HTTP request theo mô hình **Reactive Streams** dựa trên Project Reactor. Khi client gọi một API bằng Bearer access token, Spring Security phải xác thực token rồi tạo `Authentication` trước khi kiểm tra quyền.

Trong Servlet stack, lập trình viên thường gặp `AuthenticationManager`, `ProviderManager`, `JwtAuthenticationProvider` hoặc `OpaqueTokenAuthenticationProvider`. Trong **WebFlux stack**, điểm mở rộng tương ứng là **`ReactiveAuthenticationManager`**, trả về một `Mono<Authentication>` thay vì một `Authentication` đồng bộ.

Hai triển khai quan trọng:

- **`JwtReactiveAuthenticationManager`**: dùng `ReactiveJwtDecoder` để xác minh JWT access token (JWS, khóa/thuật toán, issuer, audience, thời gian và các validation theo hợp đồng), sau đó tạo `JwtAuthenticationToken`.
- **`OpaqueTokenReactiveAuthenticationManager`**: dùng `ReactiveOpaqueTokenIntrospector` để hỏi Authorization Server về trạng thái/metadata token, rồi tạo Authentication (thường là `BearerTokenAuthentication`) theo principal và authorities trả về.

Ví dụ HTTP:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6...
```

hoặc:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer 8pDQyU4Xopaque...
```

Cả hai là **Bearer credentials**, nhưng cách thẩm định khác nhau. **Bearer không tự hàm ý JWT**; cũng không phải token không có dấu chấm thì có thể tin là opaque token hợp lệ.

> **Nguyên tắc chính:** `ReactiveAuthenticationManager` là một **hợp đồng reactive để xác thực credential**. Nó không tự quyết định nguồn khóa JWT hoặc endpoint introspection có đáng tin, không tự cấp quyền sở hữu bản ghi và không thay thế chính sách `AuthorizationManager`. Hãy dùng implementation phù hợp **access-token contract và trust boundary** của API.

## 2. ReactiveAuthenticationManager là gì?

Interface thuộc package `org.springframework.security.authentication`:

```java
@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
```

Ba kết quả có ý nghĩa khác nhau:

| Tín hiệu Reactor | Ý nghĩa theo interface | Ứng xử khi làm bảo mật |
| --- | --- | --- |
| `Mono.just(authentication)` | Xác thực thành công; Authentication chứa principal/authorities đã được chấp nhận. | Tiếp tục xử lý authorization trong Security WebFilterChain. |
| `Mono.empty()` | Manager **không xác định được** cách xử lý Authentication đầu vào. | Không được biến thành “xác thực thành công”; có thể để manager khác xử lý theo composition được thiết kế. |
| `Mono.error(authenticationException)` | Xác thực thất bại. | Dừng đường xác thực; filter/entry point xử lý lỗi phù hợp, không tạo principal. |

Phải phân biệt **`Mono.empty()` vì manager không hỗ trợ kiểu credential** với **token đã bị xác định không hợp lệ**. Với token sai chữ ký, đã hết hạn hoặc introspection `active=false`, đường xác thực phải thất bại; không được trả empty rồi coi như user anonymous hoặc tự dùng một cơ chế yếu hơn.

Một implementation minh họa cho credential riêng:

```java
public final class ExampleReactiveAuthenticationManager
        implements ReactiveAuthenticationManager {

    @Override
    public Mono<Authentication> authenticate(Authentication authentication) {
        if (!(authentication instanceof ExampleAuthenticationToken token)) {
            return Mono.empty(); // Không hỗ trợ loại credential này.
        }

        return validateTrustedCredential(token)
                .switchIfEmpty(Mono.error(
                        new BadCredentialsException("Invalid credential")))
                .map(principal -> new ExampleAuthenticatedToken(principal));
    }
}
```

`ExampleAuthenticationToken`, `ExampleAuthenticatedToken` và `validateTrustedCredential` là **kiểu/phương thức giả định**, không có sẵn trong Spring Security. Ví dụ chỉ thể hiện hợp đồng Reactor và trách nhiệm fail-closed. Với JWT/opaque token thực tế, **không cần viết lại manager** khi Spring Security đã cung cấp implementation chuẩn.

### 2.1. Mono là mô tả công việc, không phải kết quả ngay lập tức

Trong Reactor, `Mono<Authentication>` biểu diễn một pipeline bất đồng bộ. Kết quả hoặc lỗi được phát tới subscriber theo quy tắc Reactive Streams. Spring Security WebFlux đảm nhiệm việc subscribe thông qua filter chain.

Đừng làm:

```java
// SAI trong request path WebFlux: chặn thread bằng blocking call.
Authentication authentication =
        reactiveAuthenticationManager.authenticate(input).block();
```

Blocking trên Netty event-loop có thể gây nghẽn xử lý request hoặc lỗi runtime. Thay vào đó dùng `flatMap`, `map`, `switchIfEmpty`, `onErrorResume` một cách có kiểm soát. Đặc biệt, **`onErrorResume(error -> Mono.just(adminAuthentication))` là lỗ hổng nghiêm trọng** vì biến authentication failure thành quyền cao.

## 3. So sánh JWT và opaque theo đường reactive

| Khía cạnh | JWT Resource Server | Opaque Resource Server |
| --- | --- | --- |
| Manager | `JwtReactiveAuthenticationManager` | `OpaqueTokenReactiveAuthenticationManager` |
| Thành phần xác minh | `ReactiveJwtDecoder` | `ReactiveOpaqueTokenIntrospector` |
| Nguồn tin cậy | Issuer/JWKS/public key được cấu hình; JWT validators. | Authorization Server introspection endpoint và credential/tin cậy dành cho Resource Server. |
| Giao thức/định dạng | Thường là signed JWT JWS. | Token string được AS kiểm tra qua OAuth 2.0 Token Introspection (RFC 7662). |
| I/O thường gặp | Fetch JWKS/discovery và cache; xác minh chữ ký cục bộ sau khi có key. | HTTP introspection cho mỗi token/request hoặc theo chiến lược cache được phê duyệt. |
| Hủy token trước `exp` | Không tự thấy revocation khi chỉ kiểm tra JWT ngoại tuyến. | Có thể hỏi AS về trạng thái token; mức kịp thời tùy cache và chính sách AS. |
| Principal thông dụng | `JwtAuthenticationToken` có `Jwt`. | `BearerTokenAuthentication` với `OAuth2AuthenticatedPrincipal`. |
| Scopes | Thường từ `scope` hoặc `scp`, map thành `SCOPE_...`. | Thường từ introspection `scope`, map thành `SCOPE_...`. |
| Lỗi token | Signature/claims/algorithm/key validation thất bại. | Response `active=false` hoặc lỗi theo introspection contract. |
| Lỗi hạ tầng | JWKS/issuer metadata unavailable, key cache vấn đề. | Introspection timeout/AS unavailable/client secret sai. |

**Không nên hiểu JWT là “an toàn hơn” hay opaque là “an toàn hơn” trong mọi tình huống.** Mỗi lựa chọn có trade-off về latency, thu hồi, trust boundary và vận hành. Token được kiểm tra theo chuẩn nào phải do **Authorization Server và API contract** quyết định.

### 3.1. JWT có thể dùng introspection

Một Authorization Server có thể phát access token là JWT nhưng yêu cầu Resource Server **introspect chuỗi JWT** để biết token đã bị thu hồi hay chưa. Trong trường hợp đó, Spring Security WebFlux có thể dùng **opaque/introspection path** dù token có ba đoạn giống JWS.

“JWT manager” và “opaque manager” là **hai cơ chế xác minh**, không phải một phép phân loại tự động dựa trên ký tự dấu chấm.

## 4. Luồng WebFlux: từ HTTP Bearer đến Reactor SecurityContext

```mermaid
sequenceDiagram
    participant Client as OAuth Client
    participant Filter as AuthenticationWebFilter
    participant Conv as ServerBearerTokenAuthenticationConverter
    participant Mgr as ReactiveAuthenticationManager
    participant Val as Decoder / Introspector
    participant Ctx as Reactor SecurityContext
    participant Authz as AuthorizationWebFilter
    Client->>Filter: HTTP request + Authorization: Bearer ...
    Filter->>Conv: convert(ServerWebExchange)
    Conv-->>Filter: Mono<BearerTokenAuthenticationToken>
    Filter->>Mgr: authenticate(token)
    Mgr->>Val: decode JWT hoặc introspect token
    alt Token không hợp lệ
        Val-->>Mgr: Mono.error(...)
        Mgr-->>Filter: Authentication failure
        Filter-->>Client: 401 / Bearer challenge
    else Xác thực thành công
        Val-->>Mgr: Jwt / OAuth2AuthenticatedPrincipal
        Mgr-->>Filter: Mono<Authentication>
        Filter->>Ctx: SecurityContext trong Reactor Context
        Ctx->>Authz: Authentication + authorities
        Authz-->>Client: Cho phép hoặc 403
    end
```

Đây là sơ đồ khái niệm cho luồng OAuth 2.0 Resource Server trong **Spring WebFlux**, không phải sơ đồ Servlet. Tên filter và converter có thể khác trong các phiên bản tùy chỉnh nhưng contract cốt lõi vẫn là **đọc Bearer token → reactive authentication → Reactor SecurityContext → reactive authorization**.

### 4.1. Các vai trò thường gặp

| Thành phần | Công việc |
| --- | --- |
| `ServerWebExchange` | Context request/response của WebFlux. |
| `SecurityWebFilterChain` | Chuỗi bảo mật cho WebFlux, tương ứng khái niệm với Servlet `SecurityFilterChain` nhưng khác API. |
| `ServerHttpSecurity` | DSL để cấu hình WebFlux security. |
| `AuthenticationWebFilter` | Đọc Authentication bằng converter và gọi reactive manager. |
| `ServerBearerTokenAuthenticationConverter` | Chuyển HTTP Bearer credential thành Authentication token chưa xác thực. |
| `ReactiveAuthenticationManager` | Kiểm tra credential, phát success/empty/error. |
| `ReactiveJwtDecoder` / `ReactiveOpaqueTokenIntrospector` | Lớp chuyên trách thẩm định access token. |
| `ReactiveSecurityContextHolder` | Truy cập SecurityContext qua Reactor Context, không dựa vào ThreadLocal đơn thuần. |
| `AuthorizationWebFilter` | Áp dụng authorization rules lên exchange đã có security context. |

**Không dùng nhầm Servlet classes**: `HttpSecurity`, `SecurityFilterChain`, `BearerTokenAuthenticationFilter`, `JwtDecoder` và `OpaqueTokenIntrospector` đồng bộ thuộc Servlet pathway. WebFlux cần `ServerHttpSecurity`, `SecurityWebFilterChain`, reactive decoder/introspector và reactive manager.

## 5. Chuẩn bị một Spring Boot WebFlux Resource Server

Khi ứng dụng là WebFlux API, dependency Gradle có thể là:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
    testImplementation("io.projectreactor:reactor-test")
}
```

Đây là đoạn **Groovy DSL**. Với Maven hoặc Gradle Kotlin DSL cú pháp khác. Spring Boot quản lý version tương thích cho Spring Security/Reactor.

Với JWT validation, thư viện `spring-security-oauth2-jose` cần có trên classpath (thường được starter Resource Server kéo vào theo dependency management). Nếu khai báo module Spring Security thủ công, phải bảo đảm dependencies cần thiết có mặt.

**Không thêm `spring-boot-starter-web` chỉ để lấy Servlet API** nếu mục tiêu là WebFlux chạy trên Reactor Netty. Khi cả Spring MVC và WebFlux cùng có trong dự án Boot, quy tắc lựa chọn web application type có thể khiến ứng dụng chạy Servlet thay vì reactive; hãy chốt kiến trúc rõ ràng và kiểm tra `SecurityWebFilterChain` thực sự được áp dụng.

## 6. Cấu hình JWT trên WebFlux: lựa chọn thông dụng nhất

Giả sử API `orders-api` chấp nhận JWT access token từ issuer tin cậy.

### 6.1. application.yml

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
```

Issuer URI dùng cho việc cấu hình decoder/discovery và xác minh `iss`. Đường JWT không tự động chứng minh API đã kiểm tra audience theo **hợp đồng riêng của API**; cần bảo đảm `aud` được validate.

### 6.2. SecurityWebFilterChain

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class JwtWebFluxSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:write")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Khi Boot thấy cấu hình JWT phù hợp và chain không ghi đè decoder, Spring Security có thể tạo/use `ReactiveJwtDecoder`, kết nối nó với `JwtReactiveAuthenticationManager` trong cấu hình Resource Server.

Với API chỉ xử lý Bearer token do client chủ động gửi trong `Authorization` và không dùng browser cookie/session, chính sách CSRF có thể khác một ứng dụng web có session; **đánh giá mô hình credential thực tế** trước khi cấu hình CSRF. `hasAuthority` cũng không thay thế object/tenant authorization trong service.

### 6.3. Bean ReactiveJwtDecoder có audience validator

Ví dụ dùng decoder theo issuer nhưng thêm yêu cầu `aud=orders-api`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;

@Configuration
class JwtDecoderConfig {
    private static final String ISSUER =
            "https://login.example.test/realms/shop";

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder
                        .withIssuerLocation(ISSUER)
                        .build();

        OAuth2TokenValidator<Jwt> defaults =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains("orders-api")
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Audience does not match orders-api",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        defaults, audience));
        return decoder;
    }
}
```

Điểm kỹ thuật quan trọng: **`ReactiveJwtDecoder.decode(token)` là reactive**, nhưng validator `OAuth2TokenValidator<Jwt>` ở trên vẫn là một hàm kiểm tra đối tượng `Jwt` theo contract Spring Security. Không cần tự tạo `Mono` trong validator đơn giản. Spring Security phối hợp validation vào đường decoder.

Khi API yêu cầu profile JWT access token cụ thể như **RFC 9068**, cần kiểm tra `typ`/token type, `iss`, `aud`, `exp` và các claim khác theo profile, không chỉ chữ ký. Tùy Spring Security version có validator/builder hỗ trợ RFC 9068; kiểm tra Javadoc đúng dependency.

### 6.4. JWKS, khóa ký và thuật toán

JWT manager dựa vào decoder để:

- Lấy public keys từ một **JWKS endpoint đáng tin cậy** hoặc khóa được cấu hình.
- Chọn khóa phù hợp `kid`/`alg` nhưng không tin một endpoint `jku` chưa được cấp quyền trong token.
- Xác minh chữ ký JWS và chỉ chấp nhận thuật toán được policy cho phép.
- Kiểm tra thời gian `exp`/`nbf` và issuer.
- Kiểm tra audience/token profile và các claims ràng buộc API.

`kid` chỉ là hint chọn key, **không phải nguồn tin cậy**. JWT từ issuer A có signature hợp lệ nhưng `aud=payments-api` vẫn phải bị `orders-api` từ chối.

### 6.5. Startup và discovery

Với cấu hình `issuer-uri`, Spring Security/Boot có khả năng discovery metadata và JWKS. Một số phiên bản hoặc cách tạo decoder có **lazy initialization**, trong khi việc tự khởi tạo decoder từ issuer trong `@Bean` có thể kết nối tới issuer sớm. Khi cần ứng dụng khởi động độc lập với AS, hãy dùng cấu hình Boot hỗ trợ deferred discovery hoặc cấu hình `jwk-set-uri` tin cậy cùng issuer validator, và kiểm tra đặc tính startup trong version dùng thực tế.

Không giải quyết AS unavailable bằng cách tắt chữ ký hoặc chấp nhận bất kỳ JWT nào có `iss` gần giống giá trị mong muốn.

## 7. JwtReactiveAuthenticationManager: tạo trực tiếp khi nào?

Thông thường DSL `.oauth2ResourceServer(...jwt(...))` đã kết nối các thành phần; **không phải dự án nào cũng cần khai báo manager bằng tay**.

Nhưng nếu cần quản lý nhiều issuers, custom resolver hoặc kiểm thử manager độc lập, có thể tạo:

```java
ReactiveAuthenticationManager jwtAuthenticationManager(
        ReactiveJwtDecoder decoder) {
    return new JwtReactiveAuthenticationManager(decoder);
}
```

Constructor `JwtReactiveAuthenticationManager(ReactiveJwtDecoder)` là API được Spring Security cung cấp. Manager thường nhận một `BearerTokenAuthenticationToken` từ WebFlux Bearer converter, gọi decoder, rồi chuyển `Jwt` đã xác minh thành `JwtAuthenticationToken`.

Luồng nội bộ khái niệm:

```text
BearerTokenAuthenticationToken(rawValue)
    ↓
JwtReactiveAuthenticationManager.authenticate(...)
    ↓
ReactiveJwtDecoder.decode(rawValue)
    ↓
Jwt đã xác minh hoặc Mono.error(...)
    ↓
Jwt -> authorities + JwtAuthenticationToken
    ↓
Mono<Authentication> thành công
```

Nếu token sai signature hoặc expiry, manager không nên trả một `JwtAuthenticationToken` đã authenticated. Nó phát authentication failure phù hợp để WebFlux handler trả Bearer error. **Không tự dùng Base64URL decode payload làm thay thế `ReactiveJwtDecoder`**.

### 7.1. Converter quyền JWT

JWT:

```json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders:read orders:write",
  "exp": 1893456000
}
```

Với mapping thông dụng, tạo:

```text
SCOPE_orders:read
SCOPE_orders:write
```

`scope` là phạm vi được issuer cấp, không tự chứng minh chủ thể được xem mọi tài nguyên. Trong WebFlux, JWT converter cũng có **reactive contract**. Có thể cấu hình:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication
        .ReactiveJwtAuthenticationConverterAdapter;
import reactor.core.publisher.Mono;

Converter<Jwt, Mono<AbstractAuthenticationToken>>
        jwtAuthenticationConverter() {

    JwtGrantedAuthoritiesConverter authorities =
            new JwtGrantedAuthoritiesConverter();
    authorities.setAuthoritiesClaimName("scope");
    authorities.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter servletStyleConverter =
            new JwtAuthenticationConverter();
    servletStyleConverter.setJwtGrantedAuthoritiesConverter(authorities);

    return new ReactiveJwtAuthenticationConverterAdapter(
            servletStyleConverter);
}
```

Tên `servletStyleConverter` chỉ giúp nhắc rằng `JwtAuthenticationConverter` được thiết kế theo interface đồng bộ; adapter biến kết quả để dùng trong WebFlux. Nó không yêu cầu ứng dụng chạy Servlet stack. Dù converter trả `Mono`, **công việc blocking trong converter đồng bộ không tự hóa thành non-blocking** chỉ vì bọc bằng adapter.

Đưa converter vào DSL:

```java
.oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
        jwt.jwtAuthenticationConverter(jwtAuthenticationConverter())))
```

Hoặc khi tự dùng manager:

```java
JwtReactiveAuthenticationManager manager =
        new JwtReactiveAuthenticationManager(decoder);
manager.setJwtAuthenticationConverter(jwtAuthenticationConverter());
```

**Hai cách wiring là những lựa chọn tùy kiến trúc**, không cần cấu hình song song nếu đường DSL đã dùng bean/decoder/converter đúng. Cần quan sát manager nào thực sự được filter sử dụng.

### 7.2. Khi cần làm I/O để tính authorities

Ví dụ ứng dụng muốn tra cứu tenant membership từ database reactive:

```text
Validated Jwt -> external identity
             -> reactive identity repository
             -> authorities theo tenant
             -> Authentication
```

Không đặt một JDBC query blocking bên trong `JwtGrantedAuthoritiesConverter.convert` rồi nghĩ reactive adapter tự giải quyết. Thay vào đó, xây `Converter<Jwt, Mono<AbstractAuthenticationToken>>` thực hiện những truy vấn bằng **driver reactive** hoặc chuyển blocking work qua scheduler thích hợp có giới hạn/monitoring.

Ngay cả khi JWT có `role=admin`, policy phải xác định claim đó có đáng tin và thuộc API/tenant nào; không tự cấp quyền tối cao từ dữ liệu chưa có hợp đồng.

## 8. Opaque Resource Server trên WebFlux

Opaque token dựa vào OAuth 2.0 introspection endpoint của AS.

### 8.1. application.yml

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

`INTROSPECTION_CLIENT_ID` và `INTROSPECTION_CLIENT_SECRET` là credential **Resource Server dùng để gọi AS**, khác Bearer access token của client. Secret phải được lấy từ secret manager/deployment channel đáng tin cậy, không commit vào Git.

### 8.2. SecurityWebFilterChain dùng opaqueToken

```java
@Configuration
@EnableWebFluxSecurity
public class OpaqueWebFluxSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }
}
```

Đây là **lựa chọn thay thế** cho JWT chain ở mục 6, không phải cấu hình cả hai bean cùng matcher `/**` song song rồi mong Spring tự nhìn token và chọn. Với WebFlux, Boot có thể tự tạo `ReactiveOpaqueTokenIntrospector` dựa trên `opaquetoken.*` khi không có bean/custom DSL ghi đè.

### 8.3. ReactiveOpaqueTokenIntrospector

Interface:

```java
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

Một implementation phổ biến:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.introspection
        .ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection
        .SpringReactiveOpaqueTokenIntrospector;

@Bean
ReactiveOpaqueTokenIntrospector introspector(
        @Value("${introspection.uri}") String uri,
        @Value("${introspection.client-id}") String id,
        @Value("${introspection.client-secret}") String secret) {

    return SpringReactiveOpaqueTokenIntrospector
            .withIntrospectionUri(uri)
            .clientId(id)
            .clientSecret(secret)
            .build();
}
```

Ví dụ builder phản ánh API được mô tả trong tài liệu Spring Security WebFlux hiện hành; nếu dự án cũ không có builder, phải dùng constructor/HTTP client API được phiên bản đó hỗ trợ.

### 8.4. Response của introspection

Ví dụ AS trả:

```json
{
  "active": true,
  "sub": "user-123",
  "client_id": "web-client",
  "aud": ["orders-api"],
  "scope": "orders:read orders:export",
  "exp": 1893456000
}
```

Các metadata từ AS là input để tạo principal và authorities, thường:

```text
principal = OAuth2AuthenticatedPrincipal
authorities = [SCOPE_orders:read, SCOPE_orders:export]
Authentication = BearerTokenAuthentication
```

**HTTP 200 không đủ**. AS có thể trả:

```json
{"active": false}
```

khi token đã hết hạn, bị thu hồi hoặc không được chấp nhận. Introspector phải từ chối, không tạo principal tin cậy.

## 9. OpaqueTokenReactiveAuthenticationManager

Manager reactive cho opaque token:

```java
ReactiveAuthenticationManager opaqueAuthenticationManager(
        ReactiveOpaqueTokenIntrospector introspector) {
    return new OpaqueTokenReactiveAuthenticationManager(introspector);
}
```

`OpaqueTokenReactiveAuthenticationManager(ReactiveOpaqueTokenIntrospector)` là constructor chính; manager gọi `introspect(rawToken)` và chuyển kết quả thành `Authentication`.

Pipeline:

```text
BearerTokenAuthenticationToken(rawValue)
    ↓
OpaqueTokenReactiveAuthenticationManager.authenticate(...)
    ↓
ReactiveOpaqueTokenIntrospector.introspect(rawValue)
    ↓
AS xác minh introspection client credential
    ↓
AS xác nhận active hoặc inactive
    ↓
active=true -> principal + authorities -> BearerTokenAuthentication
active=false / timeout / auth error -> không có authenticated principal
```

Khác với JWT manager, opaque manager **không tự xác minh chữ ký JWS**. Nó tin kết quả từ introspection endpoint đã cấu hình và phải tuân thủ hợp đồng của endpoint đó.

### 9.1. Client credentials bị lỗi khác token inactive

Đừng nhầm:

| Tình huống | Điểm phát sinh | Ý nghĩa |
| --- | --- | --- |
| AS trả `{"active":false}` với HTTP 200 | Trạng thái access token. | Token của caller không active. |
| AS trả HTTP 401 khi Resource Server gọi introspection | Credential Resource Server–AS. | Introspection client secret/certificate/quyền có thể sai. |
| HTTP timeout, TLS failure, 503 | Hạ tầng AS/network. | Chưa xác minh được token; fail-closed. |
| Token active=true nhưng scope không đủ | Authorization trong Resource Server. | Authentication có thể thành công, rồi endpoint trả 403. |

Trong reactive manager, **không bao giờ** dùng `onErrorResume(error -> Mono.just(adminAuthentication))`. Nếu AS không thể xác nhận token thì API không được tự cấp principal.

### 9.2. Resource-binding và audience

`active: true` không mặc nhiên có nghĩa access token được dùng cho **mọi API**. Nếu AS trả `aud`, Resource Server có thể thêm policy `orders-api` bằng decorator:

```java
import java.util.Collection;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection
        .BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection
        .ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class AudienceCheckingReactiveIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;

    public AudienceCheckingReactiveIntrospector(
            ReactiveOpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token).flatMap(principal -> {
            Object raw = principal.getAttribute("aud");

            boolean allowed =
                    (raw instanceof String aud
                            && "orders-api".equals(aud))
                    || (raw instanceof Collection<?> audience
                            && audience.contains("orders-api"));

            return allowed
                    ? Mono.just(principal)
                    : Mono.error(new BadOpaqueTokenException(
                            "Access token is not for orders-api"));
        });
    }
}
```

Wrapper không tự gửi HTTP và không tạo principal khi delegate ném lỗi. Nó **fail-closed** khi thiếu audience. Nếu AS không cung cấp `aud` nhưng cam kết introspection credential chỉ được phép kiểm tra token cho resource tương ứng, phải tài liệu hóa bảo đảm đó; không tự bỏ audience policy vì “token active rồi”.

### 9.3. Tùy chỉnh authentication conversion

Một số phiên bản Spring Security hỗ trợ `ReactiveOpaqueTokenAuthenticationConverter` cho `OpaqueTokenReactiveAuthenticationManager`:

```java
OpaqueTokenReactiveAuthenticationManager manager =
        new OpaqueTokenReactiveAuthenticationManager(introspector);

manager.setAuthenticationConverter(customConverter);
```

`customConverter` phải đúng interface và method signature của phiên bản Spring Security đang sử dụng. Nó chuyển principal/attributes đã introspect thành `Authentication`, có thể ánh xạ authorities từ metadata. Nếu chỉ muốn kiểm tra `aud` hoặc issuer, **decorator trên introspector** như ví dụ ở trên dễ hiểu hơn việc biến đổi authentication.

Không dùng converter để tự cấp `ROLE_ADMIN` từ một claim chưa được hợp đồng Authorization Server đảm bảo.

## 10. Chọn giữa hai manager: không căn cứ vào “dấu chấm” trong token

Một số hệ thống chỉ nhận JWT, một số chỉ opaque. Một hệ thống khác có thể nhận **cả hai** trong giai đoạn migration hoặc cho hai loại resource khác nhau.

**Không an toàn:**

```java
// Không nên đoán cơ chế tin cậy chỉ từ hình thức Bearer token.
boolean seemsJwt = rawToken.chars().filter(c -> c == '.').count() == 2;
return seemsJwt ? jwtManager : opaqueManager;
```

Vì:

- Attacker kiểm soát chuỗi token gửi vào.
- JWT cũng có thể được kiểm tra qua introspection.
- Opaque token có thể chứa dấu chấm.
- Một token sai JWT signature **không được tự fallback** sang một kênh có chính sách xác minh yếu hơn.
- Cách chọn manager phải phản ánh **trust domain** và **token profile** đã được thỏa thuận.

Có thể chọn cơ chế theo **đường API riêng**, **issuer allowlist** hoặc policy rõ ràng, thay vì sniff chuỗi input.

## 11. ReactiveAuthenticationManagerResolver cho JWT và opaque

Spring Security WebFlux hỗ trợ `ReactiveAuthenticationManagerResolver<ServerWebExchange>` khi cần chọn manager ở request time.

Ví dụ giả định API có hai nhóm endpoint:

```text
/api/v2/**      → JWT access tokens
/api/legacy/**  → opaque access tokens
```

Xây một resolver theo **đường dẫn đã định nghĩa trong API contract**:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication
        .ReactiveAuthenticationManagerResolver;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.authentication
        .OpaqueTokenReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.introspection
        .ReactiveOpaqueTokenIntrospector;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Bean
ReactiveAuthenticationManagerResolver<ServerWebExchange> tokenManagerResolver(
        ReactiveJwtDecoder jwtDecoder,
        ReactiveOpaqueTokenIntrospector introspector) {

    ReactiveAuthenticationManager jwtManager =
            new JwtReactiveAuthenticationManager(jwtDecoder);

    ReactiveAuthenticationManager opaqueManager =
            new OpaqueTokenReactiveAuthenticationManager(introspector);

    return exchange -> {
        String path = exchange.getRequest()
                .getPath()
                .pathWithinApplication()
                .value();

        if (path.startsWith("/api/legacy/")) {
            return Mono.just(opaqueManager);
        }
        return Mono.just(jwtManager);
    };
}
```

Áp dụng trong một chain:

```java
@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http,
        ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver) {

    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/api/legacy/**")
                        .hasAuthority("SCOPE_legacy:read")
                    .pathMatchers("/api/v2/**")
                        .hasAuthority("SCOPE_orders:read")
                    .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.authenticationManagerResolver(resolver))
            .build();
}
```

**Đây là cấu hình minh họa cho trường hợp thật sự có hai token contracts độc lập.** Cần bảo đảm các route còn lại không được vô tình mở và hai manager đều có **issuer/resource/authority validators** đúng.

### 11.1. Cẩn thận khi chọn theo path

- Path phải có ý nghĩa **server-controlled** và mapping rõ với API; không tin header `X-Token-Type` do caller tự gán.
- Với gateway/rewrite rules, kiểm tra `pathWithinApplication` và matcher của chain có hiểu cùng một URL hay không.
- Đừng để `/api/legacy/` được dùng để gọi API nhạy cảm yêu cầu JWT policy mới.
- Nếu cần cả JWT và opaque **trên cùng endpoint**, thiết kế một resolver chặt chẽ theo trusted issuer, client registration hoặc migration policy; không đơn giản fallback sau một lỗi authentication.
- Test request vào route không được hỗ trợ nhận deny, không chỉ test đường thành công.

### 11.2. Vì sao không kết hợp hai manager bằng fallback bất cẩn?

Ví dụ sai:

```java
return jwtManager.authenticate(authentication)
        .onErrorResume(error ->
                opaqueManager.authenticate(authentication));
```

Một JWT sai chữ ký hoặc sai issuer có thể bị thử tiếp ở opaque endpoint với ràng buộc khác. Trong một số provider, token tồn tại và active nhưng có audience dành cho resource khác; fallback như vậy dễ làm yếu security boundary.

Nếu migration thực sự yêu cầu kiểm tra hai loại token, phải có **trusted discriminant và allowlist**, ràng buộc resource/issuer/audience cho từng manager, policy chống confusion và bộ test tiêu cực cho token sai loại.

## 12. Multi-issuer JWT: resolver chỉ được tin issuer trong allowlist

Khi API nhận JWT từ hai Authorization Servers, Spring Security hỗ trợ `JwtIssuerReactiveAuthenticationManagerResolver`.

```java
JwtIssuerReactiveAuthenticationManagerResolver resolver =
        JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(
                "https://idp-a.example.test/issuer",
                "https://idp-b.example.test/issuer");
```

Đưa resolver vào WebFlux DSL:

```java
@Bean
SecurityWebFilterChain multiIssuerApi(ServerHttpSecurity http) {
    JwtIssuerReactiveAuthenticationManagerResolver resolver =
            JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(
                    "https://idp-a.example.test/issuer",
                    "https://idp-b.example.test/issuer");

    return http
            .authorizeExchange(exchanges -> exchanges
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.authenticationManagerResolver(resolver))
            .build();
}
```

Khi chọn manager, hệ thống có thể phải đọc `iss` **chưa được xác thực** từ token để tìm ứng viên trong allowlist. Giá trị này chỉ là **gợi ý để định tuyến**, không phải bằng chứng tin cậy. Manager/decoder được chọn vẫn phải xác minh chữ ký, issuer, audience và claims.

**Không làm:**

```java
// SAI: tạo JWKS/issuer decoder cho URL tùy ý từ token chưa xác minh.
String issuerFromUnverifiedPayload = ...;
return ReactiveJwtDecoders.fromIssuerLocation(
        issuerFromUnverifiedPayload);
```

Nguy cơ gồm SSRF, tải metadata/key từ attacker-controlled server, memory resource exhaustion và nhận token của issuer không được phê duyệt.

### 12.1. Các issuer khác nhau có thể có profile khác nhau

Ví dụ:

```text
Issuer A:
  aud = orders-api
  scope = orders:read

Issuer B:
  aud = https://api.example.test/orders
  scp = ["orders.read"]
```

Không tự gộp scope hoặc audience bằng substring. Mỗi manager/decoder phải áp dụng đúng hợp đồng, rồi ánh xạ sang domain authorities theo allowlist. Nếu hai issuer có ý nghĩa role khác nhau, cần ngăn cross-issuer privilege escalation.

## 13. Reactive SecurityContext: không mặc định nằm trong ThreadLocal

Đây là một khác biệt nền tảng giữa WebFlux và Servlet.

Trong Servlet, code thường gặp:

```java
SecurityContextHolder.getContext().getAuthentication();
```

Với WebFlux, Reactor có thể chuyển execution giữa threads và sử dụng **Reactor Context** để mang security context theo subscription. Code reactive nên lấy:

```java
Mono<Authentication> currentAuthentication =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication);
```

Ví dụ service:

```java
public Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
}
```

Nếu cần subject và issuer từ JWT:

```java
public Mono<String> currentJwtSubject() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMap(auth -> {
                Object principal = auth.getPrincipal();
                if (principal instanceof Jwt jwt) {
                    return Mono.justOrEmpty(jwt.getSubject());
                }
                return Mono.empty();
            });
}
```

Đoạn code thứ hai chỉ có ý nghĩa khi pipeline có `JwtAuthenticationToken` và `principal` là `Jwt`; với opaque token, principal thường là `OAuth2AuthenticatedPrincipal`. Ứng dụng dùng chung hai cơ chế nên định nghĩa abstraction `CurrentActor` rõ ràng thay vì cast tất cả principals sang JWT.

### 13.1. Lưu ý với subscribe thủ công và @Async

Đừng tách security-sensitive operation thành `subscribe()` thủ công từ controller rồi kỳ vọng `SecurityContext` chắc chắn đi theo subscription đó. Một subscription mới có thể không có Reactor Context/transaction context giống luồng request.

Ví dụ không nên dùng:

```java
// SAI: fire-and-forget, mất kiểm soát context/lỗi/hành động bảo mật.
orderService.deleteOrder(orderId).subscribe();
return Mono.just(ResponseEntity.accepted().build());
```

Thay vào đó, **trả Mono/Flux đã kết hợp các bước** cho framework:

```java
return orderService.deleteOrder(orderId)
        .thenReturn(ResponseEntity.noContent().build());
```

Với background jobs/queues, cần actor/service identity, propagation và authorization độc lập; không tự tái sử dụng access token của HTTP request sau khi hết hạn.

### 13.2. Security context không biến token thành quyền dữ liệu

`Authentication.getName()` là tên principal theo converter, thường liên quan `sub` hoặc metadata trả về. Nó không mặc nhiên là **khóa nội bộ ổn định** cho mọi issuer. Khi đọc đơn hàng, nên ánh xạ external identity đã xác minh sang internal user/service ID, kiểm tra tenant/ownership trong query.

## 14. Phân quyền reactive: scope, roles và object ownership

Trong `SecurityWebFilterChain`, kiểm tra:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders:read")
    .pathMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders:write")
    .anyExchange().authenticated())
```

Nhưng `SCOPE_orders:read` chỉ là quyền thực hiện thao tác đọc theo contract, không mặc nhiên cấp quyền đọc mọi order. Một service reactive có thể kết hợp scope ở method security và query:

```java
@Service
public class OrderService {
    private final ReactiveOrderRepository repository;
    private final ReactiveCurrentActor currentActor;

    public OrderService(ReactiveOrderRepository repository,
                        ReactiveCurrentActor currentActor) {
        this.repository = repository;
        this.currentActor = currentActor;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders:read')")
    public Mono<OrderDto> getOrder(UUID orderId) {
        return currentActor.getAuthorizedActor()
                .flatMap(actor -> repository
                        .findByIdAndOwnerIdAndTenantId(
                                orderId,
                                actor.userId(),
                                actor.tenantId()))
                .map(OrderDto::from);
    }
}
```

`ReactiveOrderRepository`, `ReactiveCurrentActor`, `OrderDto` và `getAuthorizedActor` là **kiểu/phương thức domain giả định**, cần triển khai riêng. Annotation `@PreAuthorize` trong WebFlux yêu cầu **`@EnableReactiveMethodSecurity`** và bean đi qua proxy; method security không tự bật chỉ vì có `SecurityWebFilterChain`.

**Query-level filtering là ranh giới quan trọng** cho dữ liệu multi-tenant. Không trả `Flux<Order>` của mọi tenant rồi chỉ lọc bằng `@PostFilter` nếu có thể giới hạn ngay trong database.

## 15. Lỗi trong reactive pipeline và phản hồi Bearer

Từ góc nhìn HTTP, JWT/opaque đều tuân theo mô hình Bearer error, nhưng lý do nội bộ khác nhau.

| Tình huống | Ở tầng nào? | Kết quả HTTP thông dụng |
| --- | --- | --- |
| Không gửi Bearer token vào API cần auth | Chưa có credential. | **401 Unauthorized**, Bearer challenge. |
| Header Bearer malformed | Credential extraction. | **400 invalid_request** hoặc lỗi phù hợp theo resolver. |
| JWT sai chữ ký/thuật toán, hết hạn, issuer/aud sai | `ReactiveJwtDecoder`. | **401 invalid_token**. |
| Opaque token introspection trả `active=false` | `ReactiveOpaqueTokenIntrospector`. | **401 invalid_token**. |
| JWT hoặc opaque hợp lệ nhưng thiếu authority | Authorization WebFilter/method. | **403 Forbidden**, có thể `insufficient_scope`. |
| Token hợp lệ, user không sở hữu tài nguyên | Domain policy. | **403 hoặc 404** theo contract của API. |
| JWKS service hoặc introspection AS không truy cập được | Dependency/network. | **Fail-closed**; HTTP status tùy handler/chính sách, có thể 5xx/503. |
| Introspection client secret sai | AS từ chối Resource Server. | Không tạo principal; phân loại lỗi vận hành, không kết luận user token bị revoke. |

Ví dụ với JWT không hợp lệ:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Với token hợp lệ nhưng thiếu scope:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Đây là mẫu thường gặp, không phải cam kết mọi handler/custom gateway đều tạo header giống hệt. Trong WebFlux, các handler như `ServerBearerTokenAuthenticationEntryPoint` và `ServerBearerTokenAccessDeniedHandler` hỗ trợ Bearer responses. Không trộn chúng với các handler Servlet có API/namespace khác.

### 15.1. Không dùng onErrorResume để “nâng quyền”

Ví dụ cực kỳ nguy hiểm:

```java
return authenticationManager.authenticate(token)
        .onErrorResume(ex -> Mono.just(
                new UsernamePasswordAuthenticationToken(
                        "anonymous", "n/a",
                        AuthorityUtils.createAuthorityList("ROLE_ADMIN"))));
```

Đây là **fail-open**, biến token sai chữ ký hoặc introspection timeout thành admin. Đường xác thực phải fail-closed; nếu muốn fallback sang cơ chế khác, đó phải là thiết kế có trust contract và phân biệt credential type rõ, **không phải** tự thử manager thứ hai cho mọi lỗi.

### 15.2. Không lộ token và lỗi nội bộ

Khi authentication thất bại, phản hồi không nên chứa raw JWT, Bearer header, `client-secret` introspection, JWKS URI nội bộ, `kid` inventory hoặc stack trace. Logging cần dùng category thấp cardinality và correlation ID. Đừng thêm `exception.getMessage()` trực tiếp vào `WWW-Authenticate error_description`.

## 16. Reactive không đồng nghĩa tất cả thư viện đều non-blocking

Spring WebFlux sử dụng non-blocking I/O, nhưng custom code có thể phá đặc tính này.

### 16.1. Các anti-pattern

```java
// 1. Chặn Netty event loop.
Jwt jwt = reactiveJwtDecoder.decode(rawToken).block();

// 2. Gọi RestTemplate đồng bộ bên trong reactive authentication.
return Mono.just(restTemplate.postForObject(url, request, Response.class));

// 3. Thực hiện JDBC blocking trực tiếp trong map().
return tokenMono.map(token -> jdbcTemplate.queryForObject(...));

// 4. Tự subscribe rồi bỏ lỗi / context.
reactiveIntrospector.introspect(rawToken).subscribe();
```

Đoạn 2 còn có vấn đề: biểu thức `restTemplate.postForObject(...)` được đánh giá **trước** `Mono.just(...)`, tức là blocking call diễn ra ngay khi tạo Mono.

### 16.2. Khi bất khả kháng phải gọi thư viện blocking

Nếu một hệ thống legacy chỉ cung cấp `OpaqueTokenIntrospector` đồng bộ, có thể tạo adapter **có chủ đích**, ví dụ:

```java
ReactiveOpaqueTokenIntrospector adapter =
        token -> Mono.fromCallable(() -> blockingIntrospector.introspect(token))
                .subscribeOn(Schedulers.boundedElastic());
```

Đây chỉ là **giải pháp chuyển tiếp**, không phải non-blocking thật:

- Bounded elastic scheduler có giới hạn số threads/queue; tải cao có thể làm tăng latency.
- Cần timeout, capacity planning, tracing và circuit breaker phù hợp.
- Không cho executor tăng vô hạn hoặc dùng `Schedulers.parallel()` để chạy blocking I/O.
- Không để thread phụ nắm giữ HTTP request secrets lâu hơn cần thiết.
- Nên chuyển sang **`SpringReactiveOpaqueTokenIntrospector`/WebClient** hoặc reactive API chính thức khi có thể.

Với database, ưu tiên R2DBC hoặc reactive driver phù hợp, nhưng không nhất thiết thay toàn bộ hệ thống chỉ để viết một converter.

## 17. Chọn đúng loại Authentication và principal

Sau khi manager xác thực thành công:

| Đường xác thực | Authentication thông dụng | Principal thông dụng |
| --- | --- | --- |
| JWT | `JwtAuthenticationToken` | `Jwt` |
| Opaque | `BearerTokenAuthentication` | `OAuth2AuthenticatedPrincipal` |

Ví dụ controller WebFlux:

```java
@RestController
class ProfileController {

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            Mono<Authentication> authentication) {

        return authentication.map(auth -> Map.of(
                "authenticationType", auth.getClass().getSimpleName(),
                "principalName", auth.getName()));
    }
}
```

Ví dụ chủ yếu minh họa việc lấy principal theo kiểu reactive, không phải hướng dẫn trả full principal/claims. Trong Spring WebFlux, cũng có thể lấy `Principal` hoặc dùng `@AuthenticationPrincipal` theo controller argument resolver.

### 17.1. Cùng một tên không có nghĩa cùng một user

`Authentication.getName()` ở JWT thường dựa vào `sub`; ở opaque path thường dựa trên attributes của AS. Cách lấy/chuẩn hóa tên có thể thay đổi với converters. Với multi-issuer và account linking, khóa ngoại nghiệp vụ nên là **internal user ID** ánh xạ từ external identity `(verified iss, verified sub)` hoặc hợp đồng service identity tương ứng.

Không gộp account bằng email hoặc `preferred_username` nếu chưa có hợp đồng duy nhất và không tái sử dụng.

## 18. Kiểm thử trực tiếp JwtReactiveAuthenticationManager với StepVerifier

Để phân biệt **manager behavior** và HTTP filter chain, có thể unit test manager bằng decoder test double. Mục tiêu là xác định `Mono<Authentication>` thành công hoặc lỗi như mong đợi.

```java
import static org.junit.jupiter.api.Assertions.assertTrue;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource
        .BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtReactiveAuthenticationManager;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class JwtReactiveAuthenticationManagerTest {

    @Test
    void successfulDecoderProducesAuthenticatedJwtPrincipal() {
        Jwt jwt = Jwt.withTokenValue("signed-test-token")
                .header("alg", "RS256")
                .subject("user-123")
                .claim("scope", "orders:read")
                .issuedAt(Instant.parse("2030-01-01T00:00:00Z"))
                .expiresAt(Instant.parse("2030-01-01T01:00:00Z"))
                .build();

        ReactiveJwtDecoder decoder = token -> Mono.just(jwt);
        JwtReactiveAuthenticationManager manager =
                new JwtReactiveAuthenticationManager(decoder);

        Mono<Authentication> result = manager.authenticate(
                new BearerTokenAuthenticationToken("signed-test-token"));

        StepVerifier.create(result)
                .expectNextMatches(auth ->
                        auth.isAuthenticated()
                        && "user-123".equals(auth.getName())
                        && auth.getAuthorities().stream().anyMatch(
                                a -> "SCOPE_orders:read"
                                        .equals(a.getAuthority())))
                .verifyComplete();
    }
}
```

**Quan trọng:** `ReactiveJwtDecoder` trong test này là lambda **luôn trả Jwt đã dựng trong bộ nhớ**; nó **không thực sự xác minh chữ ký**, ngày hết hạn hay issuer. Đây là unit test việc manager tạo authentication và ánh xạ authority. Để chứng minh bảo mật, cần test **`NimbusReactiveJwtDecoder` thật** với JWT JWS ký bằng key thử nghiệm và validators production-like.

### 18.1. Test decoder thất bại

```java
@Test
void failedJwtDecodeNeverProducesAuthentication() {
    ReactiveJwtDecoder decoder = token ->
            Mono.error(new BadJwtException("JWT is invalid"));

    JwtReactiveAuthenticationManager manager =
            new JwtReactiveAuthenticationManager(decoder);

    StepVerifier.create(manager.authenticate(
                    new BearerTokenAuthenticationToken("bad-token")))
            .expectError(AuthenticationException.class)
            .verify();
}
```

Đoạn trên giả định imports `BadJwtException` và `AuthenticationException`. Trong các phiên bản Spring Security thông dụng, manager ánh xạ lỗi decoder sang authentication failure. Test nên assert **không có Authentication** và exception type phù hợp version; không cần ghi raw token vào exception response.

### 18.2. Không giả định manager test chứng minh HTTP status

`StepVerifier` xác minh reactive signal, không tự chạy:

- `AuthenticationWebFilter`.
- `SecurityWebFilterChain`.
- `AuthorizationWebFilter`.
- HTTP challenge/`WWW-Authenticate`.

Test 401/403 cần thêm **WebTestClient integration test**.

## 19. Kiểm thử trực tiếp OpaqueTokenReactiveAuthenticationManager

Sử dụng fake introspector:

```java
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core
        .DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource
        .BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication
        .OpaqueTokenReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.introspection
        .ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class OpaqueTokenReactiveAuthenticationManagerTest {

    @Test
    void activeResponseProducesAuthentication() {
        ReactiveOpaqueTokenIntrospector introspector = token ->
                Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
                        "user-123",
                        Map.of("sub", "user-123",
                               "scope", List.of("orders:read")),
                        List.of(new SimpleGrantedAuthority(
                                "SCOPE_orders:read"))));

        var manager =
                new OpaqueTokenReactiveAuthenticationManager(introspector);

        StepVerifier.create(manager.authenticate(
                        new BearerTokenAuthenticationToken("opaque-test")))
                .expectNextMatches(auth ->
                        auth.isAuthenticated()
                        && "user-123".equals(auth.getName())
                        && auth.getAuthorities().stream().anyMatch(
                                a -> "SCOPE_orders:read"
                                        .equals(a.getAuthority())))
                .verifyComplete();
    }
}
```

Fake introspector đã trả một principal có `SCOPE_orders:read`. Test này **không chứng minh** Spring HTTP introspector có thực sự gọi AS, xác thực client credential, kiểm tra `active` hay parse `scope` như production. Những hành vi đó cần test với mock HTTP introspection server.

### 19.1. Test inactive/error

```java
ReactiveOpaqueTokenIntrospector inactive = token ->
        Mono.error(new BadOpaqueTokenException("inactive"));

OpaqueTokenReactiveAuthenticationManager manager =
        new OpaqueTokenReactiveAuthenticationManager(inactive);

StepVerifier.create(manager.authenticate(
                new BearerTokenAuthenticationToken("inactive-token")))
        .expectError(AuthenticationException.class)
        .verify();
```

Giả định `BadOpaqueTokenException` và `AuthenticationException` được import đúng. Mục tiêu là bảo đảm **không có authenticated principal** khi introspector từ chối token, không phải dựa vào chuỗi error message cố định của một minor version.

### 19.2. Test timeout và cơ chế retry

Một fake introspector có thể trả:

```java
ReactiveOpaqueTokenIntrospector unavailable = token ->
        Mono.error(new OAuth2IntrospectionException(
                "AS introspection unavailable"));
```

Ứng dụng phải fail-closed và phân loại dependency error. Nếu có retry, giới hạn số lần/thời gian, tránh gửi credential lặp vô hạn, và không tự fallback sang user có quyền cao khi `Mono` lỗi.

## 20. WebTestClient: kiểm tra HTTP behavior và filter chain

`WebTestClient` là công cụ phù hợp để kiểm tra WebFlux HTTP response. Khi kết hợp Spring Security Test, `SecurityMockServerConfigurers.mockJwt()` tạo JWT Authentication **giả lập**, hữu ích cho kiểm thử **authorization**.

Ví dụ:

```java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
        .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrdersWebFluxAuthorizationTest {

    @Autowired
    WebTestClient client;

    @Test
    void readScopeMayAccessReadEndpoint() {
        client.mutateWith(mockJwt()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_orders:read")))
                .get().uri("/api/orders")
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void missingReadScopeIsForbidden() {
        client.mutateWith(mockJwt()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_orders:write")))
                .get().uri("/api/orders")
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Test giả định controller `GET /api/orders` trả 200 nếu đủ quyền, và `WebTestClient` được cấu hình với Spring Security test support (trong nhiều thiết lập cần `springSecurity()` khi bind client trực tiếp vào application context). `mockJwt()` **không chứng minh decoder/introspection path** vì đã mock authentication. Khi dùng `RANDOM_PORT` qua live server, cấu hình test security mutators có thể khác client bind tới application context; cần chọn đúng WebTestClient mode và áp dụng springSecurity test integration theo phiên bản dự án.

### 20.1. Test trực tiếp Bearer JWT thật

Để kiểm tra chữ ký/JWKS/issuer/audience và `ReactiveAuthenticationManager` trong chain:

1. Tạo RSA/EC test key pair, không dùng production private key.
2. Dựng JWKS mock endpoint hoặc decoder dựa trên trusted public key test.
3. Cấu hình issuer/audience validators như production.
4. Ký JWT hợp lệ với `scope=orders:read`.
5. Gửi `Authorization: Bearer <signed-test-JWS>` bằng WebTestClient (không sử dụng `mockJwt()`).
6. Test JWT chữ ký sai, `exp` quá hạn, `iss`/`aud` sai, scope thiếu và format không hợp lệ.
7. Xác nhận 401 khi authentication failure, 403 khi authenticated nhưng thiếu quyền và 2xx khi policy cho phép.

### 20.2. Test opaque thật qua mock AS

Với opaque path:

1. Cấu hình `SpringReactiveOpaqueTokenIntrospector` trỏ vào mock introspection server tin cậy.
2. Fake AS trả `active=true` cho `test-active-read`, `active=false` cho `test-inactive`.
3. Fake AS trả HTTP 401 khi introspection client credential test sai.
4. Kiểm tra request POST, Content-Type, Basic/client authentication và form parameter `token`.
5. Test timeout/503/malformed response không tạo principal và không lộ token/secret trong lỗi.
6. Test Bearer request thực đi qua WebFlux SecurityWebFilterChain.

Không chỉ dựng `OAuth2AuthenticatedPrincipal` mock rồi tuyên bố đã kiểm tra RFC 7662 HTTP behavior.

### 20.3. Ma trận integration test

| Đầu vào | Manager phải dùng | Kết quả thông dụng |
| --- | --- | --- |
| `/api/v2/orders` + JWT đúng chữ ký, issuer, audience, scope | JWT | API xử lý bình thường. |
| `/api/v2/orders` + JWT signature sai | JWT | 401, không fallback sang opaque. |
| `/api/v2/orders` + JWT sai audience | JWT | 401. |
| `/api/legacy/orders` + opaque active=true, đúng scope | Opaque | API xử lý bình thường. |
| `/api/legacy/orders` + opaque active=false | Opaque | 401. |
| `/api/legacy/orders` + introspection timeout | Opaque | Fail-closed; lỗi dependency theo handler. |
| JWT hợp lệ nhưng thiếu `orders:read` | JWT | 403 trên endpoint cần read. |
| Opaque active=true nhưng thiếu `legacy:read` | Opaque | 403 trên endpoint cần read. |
| JWT dùng trên route chỉ nhận opaque | Opaque path | Chỉ chấp nhận nếu AS introspection và contract thực sự cho phép; không auto-switch. |
| Opaque token gửi tới route JWT | JWT path | Từ chối nếu không phải JWT hợp lệ theo decoder; không auto-switch. |
| Issuer JWT chưa nằm trong allowlist | JWT resolver | Từ chối, không tải key tùy ý. |
| Cùng issuer nhưng sai `aud` của API | Cả hai đường theo contract | Từ chối token. |
| Token hợp lệ, user không sở hữu order | Authorization/domain | 403 hoặc 404 theo policy. |

## 21. Hiệu năng và độ ổn định

Reactive authentication giúp không giữ thread trong lúc đợi I/O nếu các thành phần bên dưới cũng hỗ trợ non-blocking. Tuy nhiên:

| Hoạt động | Lưu ý vận hành |
| --- | --- |
| JWT signature verification | Tốn CPU, có thể xảy ra trên scheduler/thread do library triển khai; cần đo throughput và giới hạn token size. |
| JWKS fetch/cache | Phụ thuộc mạng khi cache miss/key rotation; không tải `jku` tùy ý. |
| Opaque introspection | Có thể phát HTTP call cho mỗi request; cần timeout, connection pool và AS capacity. |
| Revocation | Introspection có thể phản ánh revocation nhanh hơn JWT offline, nhưng cache làm tăng độ trễ nhận biết. |
| Custom converter gọi database | Dùng reactive repository hoặc schedule blocking legacy có kiểm soát. |
| Reactive context | Truyền qua Reactor chain; tránh subscribe thủ công và ThreadLocal assumptions. |
| Metrics | Đếm success/invalid/dependency error, không log raw token/secret. |

### 21.1. Chọn caching có chủ đích

Một opaque token được introspect thành công có thể được cache kết quả theo policy:

- TTL không vượt `exp` hoặc revocation SLA.
- Cache key bảo vệ raw token, không đưa token vào log/metrics.
- Phải phân biệt issuer/resource/client registration khi cache cho multi-tenant.
- AS outage không phải lý do tự động chấp nhận token chưa từng được kiểm tra.

Với JWT, JWKS cache là cache **public key metadata**, khác với cache một quyết định authentication cho một token cụ thể. Không nhầm hai loại cache khi đánh giá rủi ro thu hồi.

### 21.2. Circuit breaker không được cấp quyền

Nếu introspection AS lỗi, circuit breaker có thể làm giảm tải. Nó **không thể** tự tạo `Authentication` hợp lệ. Một phản hồi HTTP 503 an toàn có thể phù hợp hơn việc khiến mọi request tạo stack trace và retry storm. Việc map exception sang 503 phải tuân chính sách Spring Security/HTTP handler của ứng dụng, không làm lộ introspection client credentials.

## 22. Các sai lầm phổ biến

### Sai lầm 1 — Dùng Servlet AuthenticationManager trong WebFlux

`AuthenticationManager` trả `Authentication` đồng bộ; WebFlux cần `ReactiveAuthenticationManager` trả `Mono<Authentication>`. Không dùng `.block()` làm cầu nối chính cho mọi request.

### Sai lầm 2 — Nhầm ReactiveJwtDecoder với JwtDecoder

`ReactiveJwtDecoder` khác `JwtDecoder` của Servlet. Nếu bean loại sai, WebFlux DSL không sử dụng như mong đợi; phải kiểm tra version và đúng WebFlux auto-configuration.

### Sai lầm 3 — Dùng OpaqueTokenIntrospector đồng bộ trên event loop

Nếu không thể dùng reactive introspector, chuyển blocking call sang bounded elastic theo chính sách hoặc thay implementation. Không gọi blocking HTTP client trực tiếp trong `map()`.

### Sai lầm 4 — Khi JWT manager báo lỗi, tự thử opaque manager

Đây có thể là cách tạo **token confusion** giữa hai trust domains. Chỉ dùng manager được chọn theo contract hoặc resolver có policy an toàn.

### Sai lầm 5 — Dùng iss chưa xác thực để tải JWKS bất kỳ

`iss` trong JWT chưa verify là attacker-controlled. Dùng allowlist issuer, sau đó decoder được chọn phải xác thực lại issuer/chữ ký/audience.

### Sai lầm 6 — Nghĩ Mono.empty() nghĩa là authentication thành công

Theo interface, empty nghĩa là manager không đưa ra quyết định; không được cấp anonymous principal có quyền chỉ vì không có error.

### Sai lầm 7 — Bọc một JDBC/RestTemplate call bằng Mono.just()

`Mono.just(restTemplate.exchange(...))` đã chạy blocking call trước khi phát Mono. Nếu cần thích nghi legacy, dùng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` với giới hạn và kiểm thử tải.

### Sai lầm 8 — Đọc SecurityContextHolder ở bất kỳ reactive operator nào

ThreadLocal không bảo đảm giữ principal khi Reactor chuyển thread. Dùng `ReactiveSecurityContextHolder` hoặc inject principal qua WebFlux controller.

### Sai lầm 9 — Chỉ dùng scope, bỏ object/tenant authorization

`SCOPE_orders:read` không cho phép user đọc đơn của người khác. Query phải ràng buộc owner/tenant và policy.

### Sai lầm 10 — Mock JWT rồi kết luận introspection/JWKS đã hoạt động

`mockJwt()` và unit stub có thể bypass xác minh chữ ký/AS HTTP call. Cần integration test với signed JWT hoặc mock introspection endpoint.

### Sai lầm 11 — JWT decoder dựa vào kid như proof of trust

`kid` chỉ chọn candidate key trong trusted JWKS. Không tải khóa từ host do token tự đề nghị và không bỏ signature validation.

### Sai lầm 12 — Gộp nhiều SecurityWebFilterChain cùng matcher mà không hiểu order

Khi có nhiều chains, Spring Security sử dụng chain phù hợp theo matcher/order; chain rộng có thể che chain hẹp. Test endpoint JWT/opaque thực sự dùng đúng resolver/manager.

## 23. Tình huống thực hành

### Tình huống A — API đơn hàng chỉ nhận JWT

Authorization Server phát JWT JWS access token `aud=orders-api`. WebFlux chain dùng `.jwt()`, decoder xác minh chữ ký/issuer/audience, manager tạo `JwtAuthenticationToken`, `hasAuthority("SCOPE_orders:read")` kiểm tra quyền trước khi service đọc order thuộc user.

### Tình huống B — API legacy chỉ nhận opaque token

Authorization Server phát random access token, Resource Server dùng `.opaqueToken()`, introspector gửi request RFC 7662 bằng credential của Resource Server. `active=false` bị từ chối; `active=true` với scope hợp lệ tạo principal rồi authorization chạy.

### Tình huống C — Migration chia route JWT và opaque

`/api/v2/**` dùng JWT manager, `/api/legacy/**` dùng opaque manager. Resolver chọn theo path policy rõ, không sniff token. Test token sai type trên từng route để bảo đảm không fallback ngoài contract.

### Tình huống D — Hai issuers JWT

API tin `https://idp-a.example.test` và `https://idp-b.example.test`. `JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(...)` chọn manager trong allowlist; mỗi decoder phải kiểm tra token và authorities riêng, không tạo decoder cho issuer do attacker tự cung cấp.

### Tình huống E — JWKS key rotation làm JWT 401

Token dùng `kid` mới; JWKS cache chưa cập nhật hoặc AS key publication chậm. Resource Server cần refresh trusted JWKS theo policy và quan sát lỗi, không cho token đi qua trước khi xác minh signature.

### Tình huống F — Introspection timeout

AS chưa trả kết quả. Reactive pipeline phải fail-closed, tránh `onErrorResume` cấp principal mặc định. Đội vận hành kiểm tra latency/HTTP errors/client credentials, không chẩn đoán nhầm là mọi token đều bị revoke.

### Tình huống G — Context mất khi subscribe thủ công

Controller tự `subscribe()` để chạy công việc sau khi trả 202, security context có thể mất và lỗi không có người xử lý. Thiết kế background workflow với actor identity riêng và queue; không kéo dài quyền của Bearer token request vô thời hạn.

### Tình huống H — JWT có scope nhưng không đúng tenant

Authentication thành công và tạo `SCOPE_orders:read`, nhưng service phải kiểm tra `tenant_id`/owner mapping. Một token đúng scope không thể đọc đơn của tenant khác; query-level isolation ngăn rò rỉ dữ liệu.

## 24. Câu hỏi tự kiểm tra

**1. `ReactiveAuthenticationManager.authenticate(...)` trả gì?** `Mono<Authentication>`: success phát Authentication, unsupported có thể là empty, failure là error.

**2. Manager reactive cho JWT tên gì?** `JwtReactiveAuthenticationManager`, dùng `ReactiveJwtDecoder`.

**3. Manager reactive cho opaque token tên gì?** `OpaqueTokenReactiveAuthenticationManager`, dùng `ReactiveOpaqueTokenIntrospector`.

**4. Opaque manager có bắt buộc nhận một chuỗi không có dấu chấm không?** Không. Nó introspect token theo contract, kể cả khi token có hình thức JWT.

**5. Vì sao không gọi `.block()` trong WebFlux request path?** Có thể chặn event-loop, làm giảm throughput và phá reactive behavior.

**6. `ReactiveSecurityContextHolder` khác `SecurityContextHolder` thế nào?** Nó truy cập security context từ Reactor Context của reactive subscription thay vì giả định ThreadLocal của Servlet luôn đúng.

**7. `JWT chữ ký hợp lệ` đã đủ để API nhận token chưa?** Chưa. Phải kiểm tra issuer, audience, thời hạn, token profile và quyền.

**8. Opaque introspection trả `active=true` có tự động cho mọi endpoint không?** Không. Còn resource/audience binding, scope và nghiệp vụ.

**9. Có nên fallback từ JWT failure sang opaque manager không?** Không mặc định; phải có trust contract và cơ chế chọn manager an toàn, không dùng fallback để bỏ qua failure.

**10. Multi-issuer resolver có thể tin bất kỳ `iss` lấy từ token không?** Không. Dùng allowlist issuers và decoder xác minh lại token.

**11. `Mono.empty()` có nghĩa credentials hợp lệ không?** Không; nó chỉ báo manager không xác định được authentication.

**12. Khi token hợp lệ nhưng scope thiếu, HTTP thường là gì?** Thường 403; token bị từ chối ở authentication thường 401.

**13. Vì sao `StepVerifier` manager unit test chưa đủ?** Nó không chạy WebFlux filter chain, Bearer challenge hay JWT signature/HTTP introspection thật.

**14. `mockJwt()` của WebTestClient có tự xác minh JWT không?** Không; nó mô phỏng authentication phục vụ kiểm thử authorization.

**15. Nếu custom converter cần tra DB blocking thì sao?** Ưu tiên reactive repository; nếu legacy blocking thì chuyển qua boundedElastic có giới hạn và theo dõi hiệu năng.

## 25. Tài liệu tham khảo chính thức

- **Spring Security Reference — Reactive OAuth 2.0 Resource Server JWT:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **Spring Security Reference — Reactive OAuth 2.0 Resource Server Opaque Token:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- **Spring Security Reference — Reactive Resource Server Multi-tenancy:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html
- **Spring Security Javadoc — ReactiveAuthenticationManager:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html
- **Spring Security Javadoc — JwtReactiveAuthenticationManager:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtReactiveAuthenticationManager.html
- **Spring Security Javadoc — OpaqueTokenReactiveAuthenticationManager:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenReactiveAuthenticationManager.html
- **Spring Security Reference — Reactive Security / Reactor Context:** https://docs.spring.io/spring-security/reference/reactive/integrations/concurrency.html
- **Spring Security Reference — WebFlux Testing:** https://docs.spring.io/spring-security/reference/reactive/test/index.html
- **RFC 6749 — OAuth 2.0 Authorization Framework:** https://www.rfc-editor.org/rfc/rfc6749
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** https://www.rfc-editor.org/rfc/rfc6750
- **RFC 7519 — JSON Web Token (JWT):** https://www.rfc-editor.org/rfc/rfc7519
- **RFC 7662 — OAuth 2.0 Token Introspection:** https://www.rfc-editor.org/rfc/rfc7662
- **RFC 8725 — JWT Best Current Practices:** https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** https://www.rfc-editor.org/rfc/rfc9068

**Kết luận:** WebFlux Resource Server sử dụng `ReactiveAuthenticationManager` để biến một Bearer credential thành `Mono<Authentication>` trong **reactive pipeline**. `JwtReactiveAuthenticationManager` dựa vào `ReactiveJwtDecoder` để xác minh JWT; `OpaqueTokenReactiveAuthenticationManager` dựa vào `ReactiveOpaqueTokenIntrospector` để hỏi Authorization Server. Chọn manager bằng **hợp đồng token và trust boundary**, không đoán từ hình dạng chuỗi hay fallback sau khi token bị từ chối. Giữ pipeline **non-blocking và fail-closed**, truyền identity qua **Reactor SecurityContext**, kiểm tra audience/scope/tenant/ownership và test cả reactive signal lẫn HTTP filter chain để bảo vệ API đầy đủ.
