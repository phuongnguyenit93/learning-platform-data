# Kiểm thử không chặn và truyền ngữ cảnh xác thực đến lớp xử lý

Trong **Spring Security OAuth 2.0/OIDC Resource Server chạy trên Spring WebFlux**, opaque access token thường được xác thực bằng cách gọi **OAuth 2.0 Token Introspection Endpoint** của Authorization Server. Điều quan trọng không chỉ là token được xác thực đúng mà còn là toàn bộ luồng xử lý **thực sự không chặn** (*non-blocking*) và danh tính đã xác thực được **truyền đúng qua Reactor Context** tới controller, service, repository hoặc các thành phần xử lý reactive khác.

Một đoạn code trả về `Mono<OAuth2AuthenticatedPrincipal>` **không tự động chứng minh nó không chặn**. Nếu nội bộ gọi `RestTemplate`, `Thread.sleep`, JDBC đồng bộ hoặc `.block()` trên event-loop thread thì pipeline vẫn có thể nghẽn. Tương tự, việc xác thực token thành công **không bảo đảm** service nhận đúng `Authentication` nếu developer tự gọi `subscribe()`, rời khỏi subscriber chain hoặc dựa vào Servlet `ThreadLocal` theo cách không tương thích WebFlux.

Bài học tập trung vào hai mục tiêu có thể kiểm chứng:

1. **Non-blocking introspection:** Một bearer request dẫn tới `ReactiveOpaqueTokenIntrospector.introspect(String)`, thực hiện HTTP I/O phù hợp với WebFlux, trả thành công hoặc thất bại thông qua `Mono`, không chặn Reactor event loops và không tự tạo principal khi AS lỗi.
2. **Authentication context propagation:** Sau introspection thành công, `Authentication` được đặt trong **reactive security context** và service có thể truy xuất hoặc nhận tường minh actor đã xác thực; không mất context khi dùng `flatMap`, `publishOn`, bất đồng bộ hoặc lớp repository reactive.

Các ví dụ sử dụng Java, Spring Boot với **spring-boot-starter-webflux**, **spring-boot-starter-security**, **spring-boot-starter-oauth2-resource-server**, Spring Security Test, Reactor Test và WebTestClient. Tên miền, token, secrets và IDs chỉ để minh họa.

> **Thông điệp cốt lõi:** Kiểm thử opaque introspection cần tách ít nhất **ba tầng**: (1) kết quả và tính không chặn của introspector, (2) việc WebFlux filter chain tạo/truyền Authentication, và (3) quyền business đối với đối tượng cụ thể. `mockOpaqueToken()` kiểm tra tầng (2)/(3) thuận tiện, nhưng **bỏ qua lời gọi HTTP introspection thật**, nên không được xem là bằng chứng cho tầng (1).

## 1. Vị trí của introspection trong WebFlux Resource Server

Một request:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer 8NqVx2pLmZ_some_opaque_token
Accept: application/json
```

Không cung cấp thông tin tự xác minh từ chính chuỗi opaque. Resource Server sử dụng endpoint introspection của AS:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <RESOURCE_SERVER_INTROSPECTION_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<OPAQUE_ACCESS_TOKEN>
```

Ví dụ response token active:

```json
{
  "active": true,
  "sub": "user-123",
  "client_id": "shop-web",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "tenant_id": "shop-a",
  "exp": 1900000000
}
```

Với token inactive:

```json
{
  "active": false
}
```

Theo RFC 7662, `active` là thông tin trung tâm của introspection. Các claims khác có thể tồn tại tùy AS và hợp đồng. Không giả định mọi AS trả `aud`, `tenant_id` hay `exp` trong mọi response. Nếu ứng dụng bắt buộc những thông tin đó, cần có contract với AS và validation tương ứng.

### 1.1. Luồng xác thực reactive

```mermaid
flowchart TD
    A["Client gửi Bearer token"] --> B["SecurityWebFilterChain"]
    B --> C["Bearer extraction / AuthenticationWebFilter"]
    C --> D["ReactiveOpaqueTokenAuthenticationManager"]
    D --> E["ReactiveOpaqueTokenIntrospector.introspect(token)"]
    E --> F["HTTP introspection bất đồng bộ với AS"]
    F --> G{"active và hợp đồng token hợp lệ?"}
    G -- "Không" --> H["Mono.error → authentication thất bại"]
    G -- "Có" --> I["OAuth2AuthenticatedPrincipal"]
    I --> J["BearerTokenAuthentication + GrantedAuthority"]
    J --> K["Reactive SecurityContext trong Reactor Context"]
    K --> L["AuthorizationWebFilter / reactive method security"]
    L --> M{"Có scope/quyền endpoint?"}
    M -- "Không" --> N["Thường 403"]
    M -- "Có" --> O["Controller → Mono/Flux service"]
    O --> P["Repository và object-level authorization"]
    P --> Q["Response theo quyền business"]
    H --> R["Bearer authentication response, thường 401"]
```

Sơ đồ mang tính logic; tên các lớp/filter cụ thể và cách ghép chúng có thể khác giữa các phiên bản Spring Security. Điểm cần giữ là **không có principal đáng tin trước khi introspection thành công**.

### 1.2. Phân biệt với Servlet và JWT

| Chủ đề | Spring MVC Servlet opaque | Spring WebFlux opaque | Spring WebFlux JWT |
|---|---|---|---|
| Interface xác thực token | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` | `ReactiveJwtDecoder` |
| Kết quả chính | `OAuth2AuthenticatedPrincipal` | `Mono<OAuth2AuthenticatedPrincipal>` | `Mono<Jwt>` |
| HTTP introspection | Phụ thuộc implementation, thường synchronous | Reactive HTTP theo implementation được chọn | Thường không cần introspection cho mỗi token |
| Security builder | `HttpSecurity` | `ServerHttpSecurity` | `ServerHttpSecurity` |
| Chain type | `SecurityFilterChain` | `SecurityWebFilterChain` | `SecurityWebFilterChain` |
| Security context | Servlet-oriented `SecurityContextHolder` | `ReactiveSecurityContextHolder` / Reactor Context | Tương tự WebFlux |
| HTTP tests | MockMvc | WebTestClient | WebTestClient |
| Token test support | Servlet `opaqueToken()` | Reactive `mockOpaqueToken()` | Reactive `mockJwt()` |

Trong bài này, không sử dụng `OpaqueTokenIntrospector` đồng bộ làm implementation chính cho WebFlux.

## 2. “Reactive” không đồng nghĩa “non-blocking”

Chữ ký interface:

```java
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

là một **hợp đồng publisher**, không tự bảo đảm rằng mọi thao tác bên trong đều dùng non-blocking I/O.

Ví dụ **sai**:

```java
@Override
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    // blockingClient có thể gửi HTTP request ngay trên thread gọi hàm.
    OAuth2AuthenticatedPrincipal principal =
        blockingClient.introspect(token);

    return Mono.just(principal);
}
```

Mặc dù trả `Mono`, lời gọi HTTP đồng bộ đã xảy ra **trước khi có publisher để subscribe**. Nếu chạy trên WebFlux event loop, toàn bộ event loop có thể bị chặn.

Một lỗi tương đương:

```java
@Override
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    return Mono.just(
        blockingIntrospector.introspect(token)
    );
}
```

`Mono.just(...)` đánh giá đối số trước. Đoạn này không trở thành non-blocking chỉ nhờ tên `Mono`.

### 2.1. Ba tính chất cần kiểm tra riêng

| Tính chất | Điều cần chứng minh | Ví dụ tiêu chí |
|---|---|---|
| **Lazy/deferred** | Chưa subscribe thì không gửi HTTP introspection | Counter/stub chưa nhận request trước subscription |
| **Non-blocking** | Không giữ event loop trong lúc chờ network | Dùng client I/O bất đồng bộ; không có `block()`, `Thread.sleep` |
| **Correct context** | Sau xác thực, subscriber chain đọc đúng Authentication | Service nhận đúng subject, tenant và authority cho từng request |

**Kiểm tra laziness bằng StepVerifier không đủ để chứng minh non-blocking.** Một publisher có thể lazy nhưng vẫn chặn khi được subscribe. Bài sẽ tách hai loại test này.

### 2.2. Reactor cũng có tác vụ CPU

Ngay cả khi introspection dùng non-blocking WebClient, JSON parsing, mapping và authorization checks vẫn tiêu thụ CPU. Non-blocking chủ yếu giúp không chiếm thread khi chờ I/O; nó không làm mọi việc “không tốn thread” hoặc tự động nhanh hơn.

## 3. Cấu hình opaque Resource Server bằng Spring Boot

Dependencies chính trong Maven:

```xml
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
</dependencies>
```

Cấu hình introspection:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: orders-api-introspection
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Giá trị `client-id` và `client-secret` ở đây là **credentials của Resource Server khi gọi introspection endpoint**, không phải client ID của SPA đã xin bearer token. Secrets production cần được lấy từ secret manager hoặc cấu hình bảo mật, không viết thẳng vào repository.

### 3.1. SecurityWebFilterChain

```java
@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/public/catalog")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults())
            )
            .build();
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
```

Đây là **WebFlux** nên dùng `ServerHttpSecurity` và `authorizeExchange`, không dùng Servlet `HttpSecurity`/`authorizeHttpRequests`. Khi cấu hình opaque token hợp lệ, Spring Security dùng một `ReactiveOpaqueTokenIntrospector` tương ứng.

Ở authorization layer, Spring Security thường chuyển scopes từ introspection response thành `GrantedAuthority` với tiền tố `SCOPE_`:

```text
scope = "orders.read orders.write"

GrantedAuthority:
  SCOPE_orders.read
  SCOPE_orders.write
```

**Token active không đồng nghĩa có quyền gọi endpoint**. `active=true` chỉ đi qua authentication; sau đó `hasAuthority("SCOPE_orders.read")` và quyền trên order ID vẫn có thể từ chối.

### 3.2. CORS/CSRF không phải nội dung introspection

Nếu API được gọi từ SPA browser, cấu hình CORS preflight phải đúng; OPTIONS preflight thường không có Bearer token. Nếu ứng dụng dùng cookie/session bên cạnh Bearer, cần đánh giá CSRF policy riêng. Không tắt CSRF toàn bộ vì “ứng dụng có JWT/opaque token” khi vẫn dùng credentials tự gửi của browser.

## 4. Delegate `SpringReactiveOpaqueTokenIntrospector`

Với Spring Security hiện đại, một cách tạo reactive introspector được tài liệu chính thức minh họa:

```java
@Bean
ReactiveOpaqueTokenIntrospector introspector(
        @Value("${app.security.introspection-uri}")
            String introspectionUri,
        @Value("${app.security.introspection-client-id}")
            String clientId,
        @Value("${app.security.introspection-client-secret}")
            String clientSecret) {

    return SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(introspectionUri)
        .clientId(clientId)
        .clientSecret(clientSecret)
        .build();
}
```

Imports:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
```

Các keys `app.security.*` là ví dụ application properties riêng, cần khai báo khi dùng đoạn này. Nếu dự án chỉ cần cấu hình mặc định, thường có thể **để Spring Boot tự tạo introspector** từ properties `spring.security.oauth2.resourceserver.opaquetoken.*` thay vì tự tạo bean.

**Khác biệt phiên bản:** API constructor/builder của implementation có thể thay đổi giữa các bản Spring Security; hãy theo tài liệu dependency version thực tế. Interface `ReactiveOpaqueTokenIntrospector` vẫn là điểm mở rộng chính.

### 4.1. Vì sao nên ưu tiên implementation reactive chuẩn?

Implementation như `SpringReactiveOpaqueTokenIntrospector` phù hợp với mô hình Spring WebFlux, xử lý introspection qua HTTP reactive theo cấu hình của thư viện. Nó giảm nhu cầu tự viết:

- HTTP request tới token introspection endpoint.
- Authentication của Resource Server với AS.
- Xử lý response `active`.
- Ánh xạ claims và scopes.
- Chuyển lỗi introspection thành lỗi xác thực.

Tự viết HTTP client chỉ để hỗ trợ opaque token dễ bỏ sót TLS verification, Basic authentication, content type, error handling, response encoding và giới hạn mạng.

### 4.2. Bean custom có thể thay auto-configuration

Khi bạn khai báo `ReactiveOpaqueTokenIntrospector` bean riêng, Spring Boot có thể **back off** khỏi cấu hình mặc định. Vì thế không mặc định nghĩ mọi properties Boot sẽ tự được áp vào bean mới.

Nếu ứng dụng có nhiều beans/processing chains, có thể chọn introspector tường minh trong DSL:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(opaque ->
        opaque.introspector(myReactiveIntrospector)
    )
)
```

`myReactiveIntrospector` phải là object đã được tạo và inject hợp lệ. Trong đa chain/multi-issuer, cần bảo đảm request được xử lý bằng đúng introspector.

## 5. Tùy chỉnh introspector không chặn bằng decorator

Một yêu cầu phổ biến là ngoài `active=true`, Orders API muốn kiểm tra token có audience `orders-api`. Resource Server có thể **bọc delegate** thay vì tự phát Authentication.

Ví dụ:

```java
public final class AudienceCheckingReactiveIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final String expectedAudience;

    public AudienceCheckingReactiveIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            String expectedAudience) {
        this.delegate = Objects.requireNonNull(delegate);
        this.expectedAudience = Objects.requireNonNull(expectedAudience);
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return Mono.defer(() -> delegate.introspect(token))
            .switchIfEmpty(Mono.error(
                new BadOpaqueTokenException("No principal")
            ))
            .flatMap(principal -> {
                Object audience = principal.getAttribute("aud");

                boolean accepted =
                    audience instanceof String text
                        && expectedAudience.equals(text);

                if (audience instanceof Collection<?> values) {
                    accepted = values.stream()
                        .anyMatch(expectedAudience::equals);
                }

                if (!accepted) {
                    return Mono.error(new BadOpaqueTokenException(
                        "Token not intended for orders-api"
                    ));
                }

                return Mono.just(principal);
            });
    }
}
```

Imports:

```java
import java.util.Collection;
import java.util.Objects;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;
```

Điểm cần chú ý:

- `Mono.defer(...)` trì hoãn việc gọi delegate đến lúc subscription, tránh introspection bị kích hoạt ngoài pipeline.
- Delegate vẫn phải kiểm tra token active; wrapper **không tự đoán** trạng thái token.
- `switchIfEmpty(...)` biến tình huống bất thường không có principal thành authentication error, không coi empty publisher là success.
- `flatMap(...)` kiểm tra audience mà không cần blocking.
- `Mono.error(...)` giữ nguyên phản hồi thất bại qua reactive error signal.
- `return Mono.just(principal)` giữ nguyên attributes và authorities đã được delegate tạo.
- Không chuyển lỗi mạng thành principal giả.

### 5.1. Không phải AS nào cũng trả `aud`

RFC 7662 không bắt buộc mọi introspection response phải có audience. Nếu Orders API cần ràng buộc audience, AS phải cam kết trả `aud` (hoặc có cơ chế tin cậy tương đương). Với wrapper này, thiếu audience sẽ bị từ chối đúng nguyên tắc *fail closed*.

### 5.2. Validation không phải authorization bản ghi

Token có `aud=orders-api` và `scope=orders.read` vẫn không chứng minh caller được xem order 42 của tenant khác. Object-level policy thuộc service/repository; không đưa mỗi request order ID vào một validator token-wide.

### 5.3. Khi có check phải gọi database

Một check vào database có thể thuộc **business authorization** hơn là token contract. Nếu nó thực sự cần trong introspector, phải dùng **reactive repository/client** và `flatMap`, không dùng JDBC blocking trong `map`. Đối với quyền chủ sở hữu bản ghi, nên truyền actor xuống service để kiểm tra theo object.

## 6. Hai ví dụ sai vẫn chặn Reactor event loop

**Ví dụ sai thứ nhất — gọi `block()`:**

```java
@Override
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    OAuth2AuthenticatedPrincipal principal =
        reactiveDelegate.introspect(token).block();

    return Mono.just(principal);
}
```

Trong thread không cho phép block, đoạn này có thể ném lỗi. Trong môi trường khác, nó có thể giữ một thread trong lúc chờ network và làm giảm khả năng mở rộng.

**Ví dụ sai thứ hai — sleep khi chờ:**

```java
@Override
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    return Mono.fromCallable(() -> {
        Thread.sleep(1000);
        return blockingDelegate.introspect(token);
    });
}
```

`Mono.fromCallable(...)` trì hoãn thao tác nhưng **không tự chuyển blocking work ra scheduler khác**. Khi được subscribe trên event-loop, code có thể chặn event-loop.

### 6.1. Nếu bắt buộc tích hợp blocking SDK

Trong giai đoạn chuyển đổi một SDK cũ, có thể cô lập blocking operation:

```java
Mono<OAuth2AuthenticatedPrincipal> result =
    Mono.fromCallable(() ->
        legacyBlockingIntrospector.introspect(token))
    .subscribeOn(Schedulers.boundedElastic());
```

Import:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
```

Đây là một **biện pháp cách ly blocking**, không phải non-blocking network I/O thật sự. Nó có giới hạn thread/queue, cần timeout, giới hạn concurrency và phải được quan sát dưới tải. Khi có implementation reactive chính thức, ưu tiên dùng nó.

### 6.2. Không tự `subscribe()` trong authentication

Sai:

```java
reactiveDelegate.introspect(token)
    .subscribe(principal -> {
        // Tạo một Authentication ở callback không cùng luồng request.
    });

return Mono.empty();
```

Subscription tách rời có thể chạy sau khi request authorization đã đi tiếp; context và lỗi không còn được gắn với security pipeline đúng cách.

**Cách đúng:** Trả về `Mono` đã compose để Spring Security subscribe trong authentication chain.

## 7. Ngữ cảnh xác thực trong WebFlux: Reactor Context

Trong Servlet, nhiều developer quen với:

```java
SecurityContextHolder.getContext().getAuthentication();
```

Nhưng trong WebFlux, một request reactive không gắn cố định với một thread từ đầu đến cuối. Một pipeline có thể chuyển thread khi xử lý I/O, `publishOn`, `subscribeOn` hoặc composition phức tạp.

Spring Security lưu ngữ cảnh xác thực vào **Reactor Context**, được truy cập qua **`ReactiveSecurityContextHolder`**:

```java
Mono<Authentication> currentAuthentication =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication);
```

Imports:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;
```

Một Authentication được tạo sau opaque introspection thường là `BearerTokenAuthentication`, với principal là `OAuth2AuthenticatedPrincipal` và authorities được ánh xạ từ scopes.

### 7.1. Reactor Context khác ThreadLocal

| Khía cạnh | Servlet ThreadLocal giả định | Reactor Context |
|---|---|---|
| Liên hệ với đơn vị thực thi | Thread | Subscription/subscriber chain |
| Chuyển thread | Có thể mất ThreadLocal nếu không propagate | Reactor Context thường theo reactive chain |
| Truy cập | `SecurityContextHolder.getContext()` | `ReactiveSecurityContextHolder.getContext()` |
| Ghi context trong test | Cấu hình SecurityContextHolder | `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` |
| Tách pipeline qua `subscribe()` thủ công | Có thể mất | Có nguy cơ mất subscriber context |
| Chuyển actor tới service | Qua security context | Qua Reactor Context hoặc truyền tường minh |

**Không khẳng định mọi callback, CompletableFuture hoặc thư viện third-party tự động nhận Reactor Context.** Nó được gắn với subscriber chain và các operator/cơ chế propagation phù hợp.

### 7.2. Context không phải mutable map toàn cục

Reactor `Context` là một cấu trúc gắn theo subscription, được bổ sung/thay thế qua `contextWrite` và cơ chế propagation. Nó không giống một `static Map<String, Authentication>` dùng chung mọi requests.

Không nên lưu Authentication vào một biến `static` hoặc instance field dùng chung:

```java
// Không an toàn: dữ liệu có thể bị chồng giữa các requests.
private Authentication lastAuthentication;
```

Các requests concurrent có thể ghi đè principal của nhau, dẫn tới lộ dữ liệu nghiêm trọng.

## 8. Đọc actor từ `ReactiveSecurityContextHolder`

Một service có thể cần principal đã xác thực để áp ownership/tenant policy. Có thể tạo một adapter nội bộ:

```java
public record AuthenticatedActor(
    String subject,
    String tenantId
) {}
```

Và provider:

```java
@Component
public class CurrentActorProvider {

    public Mono<AuthenticatedActor> currentActor() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("No authentication")
            ))
            .flatMap(authentication -> {
                Object rawPrincipal = authentication.getPrincipal();

                if (!(rawPrincipal
                        instanceof OAuth2AuthenticatedPrincipal principal)) {
                    return Mono.error(new AccessDeniedException(
                        "Unsupported principal type"
                    ));
                }

                Object rawSubject = principal.getAttribute("sub");
                Object rawTenant = principal.getAttribute("tenant_id");

                if (!(rawSubject instanceof String subject)
                        || subject.isBlank()
                        || !(rawTenant instanceof String tenant)
                        || tenant.isBlank()) {

                    return Mono.error(new AccessDeniedException(
                        "Missing actor identity"
                    ));
                }

                return Mono.just(new AuthenticatedActor(
                    subject, tenant));
            });
    }
}
```

Imports:

```java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;
```

**Giới hạn của ví dụ:** `tenant_id` là claim riêng, chỉ có ý nghĩa nếu AS trả theo hợp đồng đáng tin; code này chủ đích từ chối khi thiếu. Nếu API không có tenant concept hoặc dùng opaque principal dạng khác, adapter cần được thiết kế tương ứng.

### 8.1. Định danh không nên dựa vào `getName()` một cách mù quáng

Trong opaque token support, name có thể dựa trên `sub` hoặc thuộc tính khác theo cấu hình. Nếu hệ thống chấp nhận nhiều issuers, hai issuers có thể cùng phát hành `sub=user-123` cho hai người khác nhau.

Một identity an toàn trong multi-issuer có thể cần **(issuer, subject)** hoặc mapping account nội bộ đáng tin. Không dùng email/username dễ đổi như một owner ID bất biến khi contract không bảo đảm.

### 8.2. Làm gì khi context không có Authentication?

Không tạo actor mặc định là admin hoặc gán tenant từ request path. `Mono.empty()` từ context có thể là request ngoài security chain, endpoint public, test setup thiếu context hoặc một publisher đã tách khỏi pipeline. Dự án cần xử lý theo chính sách: từ chối ở endpoint protected, hoặc có actor anonymous tách biệt khi nghiệp vụ thật sự public.

## 9. Truyền actor tường minh xuống service

Một lựa chọn dễ kiểm tra và ít coupling hơn là:

1. WebFlux security xác thực Bearer token.
2. Controller/adapter lấy principal.
3. Chuyển thành `AuthenticatedActor` nội bộ.
4. Truyền actor vào service bằng tham số Java.
5. Service không cần tự biết lớp Spring Security.

Ví dụ controller:

```java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;
    private final ActorMapper actorMapper;

    public OrderController(
            OrderService service,
            ActorMapper actorMapper) {
        this.service = service;
        this.actorMapper = actorMapper;
    }

    @GetMapping("/{orderId}")
    public Mono<OrderDto> readOrder(
            @PathVariable String orderId,
            @AuthenticationPrincipal
                OAuth2AuthenticatedPrincipal principal) {

        AuthenticatedActor actor =
            actorMapper.fromTrustedPrincipal(principal);

        return service.readVisibleOrder(orderId, actor);
    }
}
```

Các kiểu `OrderService`, `ActorMapper`, `AuthenticatedActor`, `OrderDto` là thành phần domain mà dự án cần triển khai. `@AuthenticationPrincipal` được Spring Security giải quyết sau khi Authentication thành công; không lấy principal từ JSON body hoặc query parameter.

Imports liên quan:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
```

### 9.1. Ưu điểm truyền actor tường minh

- Service signature mô tả rõ actor thuộc use case.
- Dễ unit test policy mà không cần tự dựng Reactor SecurityContext.
- Dễ tránh việc một background job tự chạy mà không có authenticated HTTP context.
- Dễ áp data filters theo tenant/owner.
- Dễ truyền actor qua các abstraction reactive mà không phụ thuộc thread.

Nhưng phải bảo đảm actor được tạo từ **principal đã xác thực**, không phải do caller gửi tùy ý:

```json
{
  "subject": "admin",
  "tenantId": "shop-b"
}
```

Nếu service nhận object như trên do client tùy ý tạo, kiểm tra quyền sẽ không đáng tin.

### 9.2. Khi không muốn controller phụ thuộc Spring Security type

Một lựa chọn khác là dùng `ServerWebExchange.getPrincipal()` hoặc một application adapter trả `Mono<AuthenticatedActor>`. Ví dụ:

```java
@GetMapping("/{orderId}")
public Mono<OrderDto> readOrder(@PathVariable String orderId) {
    return currentActorProvider.currentActor()
        .flatMap(actor ->
            service.readVisibleOrder(orderId, actor));
}
```

Cách này vẫn nằm trong Reactor subscriber chain và không cần `block()` để lấy principal.

## 10. Reactive service giữ quyền dữ liệu đúng phạm vi

Một service có thể nhận actor rồi truy vấn reactive repository:

```java
@Service
public class OrderService {

    private final ReactiveOrderRepository repository;

    public OrderService(ReactiveOrderRepository repository) {
        this.repository = repository;
    }

    public Mono<OrderDto> readVisibleOrder(
            String orderId,
            AuthenticatedActor actor) {

        return repository
            .findOwnedByTenantAndSubject(
                orderId,
                actor.tenantId(),
                actor.subject()
            )
            .switchIfEmpty(
                Mono.error(new OrderNotFoundException())
            )
            .map(OrderDto::from);
    }
}
```

Ý tưởng truy vấn:

```sql
SELECT *
FROM orders
WHERE id = :orderId
  AND tenant_id = :trustedTenant
  AND owner_subject = :trustedSubject;
```

Trong Spring Data R2DBC, repository thực thi bất đồng bộ theo driver/database reactive phù hợp. Không dùng một repository JDBC blocking rồi tự wrap nó trong `Mono.just(...)` nếu kỳ vọng non-blocking.

### 10.1. Quyền thao tác khác quyền đối tượng

HTTP rule:

```java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

chỉ nói token được cấp quyền **loại thao tác đọc**. Service vẫn phải kiểm tra:

```text
order.tenant == actor.allowedTenant
AND (
    order.owner == actor.subject
    OR shareACL permits
    OR assignedSupportPolicy permits
)
```

Một token đúng `scope` không phải quyền đọc mọi order.

### 10.2. List, count và export cũng cần lọc quyền

Không chỉ `GET /api/orders/{id}`. Các endpoints như:

```text
GET /api/orders
GET /api/orders/search
GET /api/orders/count
GET /api/orders/export
```

đều có thể tiết lộ object-level data nếu query bỏ `tenant_id` hoặc owner/share filter. Việc truyền actor tới service có ích vì cùng một ranh giới quyền áp cho detail, list, search và report.

## 11. Context truyền qua `flatMap`, `map` và `publishOn` như thế nào?

Trong Reactor, `Context` gắn với subscription. Những operators chuẩn trong cùng chuỗi thường giữ context đúng, dù publisher chuyển scheduler.

Ví dụ:

```java
Mono<String> currentSubject =
    ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(Authentication::getName)
        .publishOn(Schedulers.parallel())
        .flatMap(name ->
            ReactiveSecurityContextHolder.getContext()
                .map(ctx -> name + ":" +
                    ctx.getAuthentication().getName())
        );
```

Nếu Authentication đã được đưa vào Reactor Context trước khi subscribe, cả hai lần đọc trong pipeline phù hợp có thể thấy cùng principal, kể cả sau `publishOn`.

Imports:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
```

**Đừng hiểu lầm:** `publishOn` đổi scheduler của một phần chuỗi; nó không tự nhân đôi request hoặc tạo authorization mới. Reactive Context không phải ThreadLocal và không cần “copy biến Authentication sang ThreadLocal” thủ công cho từng operator.

### 11.1. `contextWrite` được áp tại subscription time

Reactor Context truyền từ **subscriber tới upstream** của chuỗi. Vì vậy test đặt:

```java
Mono<String> result =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());

Mono<String> authenticatedResult =
    result.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication)
    );
```

Publisher `result` upstream có thể đọc Authentication khi `authenticatedResult` được subscribe.

**Không nghĩ `contextWrite` là một lệnh gán biến global.** Nó có phạm vi đối với chuỗi publisher liên quan và được áp theo quy tắc Reactor.

### 11.2. `subscribeOn` cũng không tự làm mất context

Nếu code compose một publisher bình thường:

```java
return serviceCall()
    .subscribeOn(Schedulers.boundedElastic());
```

Reactor Context vẫn gắn với subscriber chain theo semantics của Reactor. Tuy nhiên, `subscribeOn` **không phải giải pháp cho blocking không có giới hạn**. Nó chỉ điều khiển scheduler subscription, và việc I/O đồng bộ vẫn tiêu tốn thread.

### 11.3. Tránh tách chuỗi bằng `subscribe()` thủ công

Ví dụ không an toàn:

```java
public Mono<OrderDto> readOrder(String id) {
    currentActorProvider.currentActor()
        .subscribe(actor ->
            auditService.record(actor.subject(), id).subscribe()
        );

    return repository.findById(id).map(OrderDto::from);
}
```

Có ít nhất ba vấn đề:

1. Audit chạy trong một subscription khác, có thể không được chờ và bị bỏ lỗi.
2. Security context có thể không được propagate vào các subscriptions tách rời như kỳ vọng.
3. Repository query không dùng actor để lọc object.

Một cách compose:

```java
public Mono<OrderDto> readOrder(String id) {
    return currentActorProvider.currentActor()
        .flatMap(actor ->
            service.readVisibleOrder(id, actor)
                .flatMap(order ->
                    auditService.record(actor.subject(), id)
                        .thenReturn(order)
                )
        );
}
```

Đây là mô hình chỉ khi audit event phải nằm trong request pipeline; với audit phát qua message broker, cần thiết kế reliability/idempotency riêng thay vì tự `subscribe()` bất đồng bộ và bỏ kết quả.

## 12. HTTP handlers và Reactor Context: hai cách lấy principal

Trong WebFlux có nhiều cách đọc principal ở handler:

| Cách | Đặc điểm | Khi dùng |
|---|---|---|
| `@AuthenticationPrincipal OAuth2AuthenticatedPrincipal` | Injection vào annotated controller | Handler MVC-style trên WebFlux |
| `ServerWebExchange.getPrincipal()` | `Mono<Principal>` trên exchange | Functional handlers/web filters |
| `ReactiveSecurityContextHolder.getContext()` | Đọc Authentication từ Reactor Context | Adapter/service trong cùng reactive chain |
| Actor tham số domain | Không phụ thuộc Spring Security trực tiếp | Service/repository policy |
| `SecurityContextHolder.getContext()` ThreadLocal | Không nên giả định trong reactive chain | Chỉ ở bối cảnh được hỗ trợ rõ và propagation đúng |

### 12.1. Dùng `ServerWebExchange.getPrincipal()`

Ví dụ trong functional handler:

```java
public Mono<ServerResponse> handler(ServerRequest request) {
    return request.principal()
        .cast(Authentication.class)
        .flatMap(authentication -> {
            OAuth2AuthenticatedPrincipal principal =
                (OAuth2AuthenticatedPrincipal)
                    authentication.getPrincipal();

            String subject = principal.getAttribute("sub");

            return ServerResponse.ok()
                .bodyValue(Map.of("subject", subject));
        });
}
```

Imports minh họa:

```java
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;
```

Code giả định endpoint được Resource Server bảo vệ và principal đúng kiểu; production nên kiểm tra type/null và tránh tiết lộ subject nếu không cần. Một handler public hoặc có authentication type khác không được phép ép kiểu vô điều kiện.

### 12.2. Khi dùng handler function hoặc filter tùy chỉnh

Đừng tự tạo principal từ `X-User-Id` hoặc `X-Tenant-Id` do client gửi. Nếu hệ thống sử dụng identity headers từ gateway, cần trust boundary riêng như mTLS, header stripping và chính sách xác thực cụ thể.

Opaque Resource Server nên lấy actor từ `Authentication` **đã qua introspection** và không coi input headers là nguồn sự thật.

## 13. Unit test reactive introspector bằng StepVerifier

Trước khi chạy HTTP tests, có thể kiểm thử trực tiếp `ReactiveOpaqueTokenIntrospector` với delegate giả. Điểm này giúp kiểm tra contract, error signals và lazy subscription **không cần Authorization Server thật**.

Ví dụ dựng principal:

```java
private static OAuth2AuthenticatedPrincipal principal(
        String subject,
        String tenant,
        String authority) {

    return new DefaultOAuth2AuthenticatedPrincipal(
        subject,
        Map.of(
            "sub", subject,
            "tenant_id", tenant,
            "aud", List.of("orders-api")
        ),
        List.of(new SimpleGrantedAuthority(authority))
    );
}
```

Imports:

```java
import java.util.List;
import java.util.Map;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
```

### 13.1. Kiểm tra case thành công

```java
@Test
void acceptsValidAudienceWithoutBlockingTestThread() {
    ReactiveOpaqueTokenIntrospector delegate = token ->
        Mono.just(principal(
            "user-123",
            "shop-a",
            "SCOPE_orders.read"
        ));

    ReactiveOpaqueTokenIntrospector introspector =
        new AudienceCheckingReactiveIntrospector(
            delegate, "orders-api");

    StepVerifier.create(
            introspector.introspect("opaque-test-token"))
        .assertNext(p -> {
            assertEquals("user-123", p.getName());
            assertEquals("shop-a",
                p.getAttribute("tenant_id"));
        })
        .verifyComplete();
}
```

Imports:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
```

**Chính xác về phạm vi test:** Ví dụ kiểm tra publisher trả principal đúng và hoàn tất, **không đủ chứng minh non-blocking**. Delegate `Mono.just(...)` không có HTTP I/O; tên test nên phản ánh test behavior thay vì kết luận hiệu năng.

### 13.2. Kiểm tra audience sai

```java
@Test
void rejectsWrongAudience() {
    OAuth2AuthenticatedPrincipal wrongAudience =
        new DefaultOAuth2AuthenticatedPrincipal(
            "user-123",
            Map.of("sub", "user-123",
                   "aud", List.of("payments-api")),
            List.of(new SimpleGrantedAuthority(
                "SCOPE_orders.read"))
        );

    ReactiveOpaqueTokenIntrospector delegate =
        token -> Mono.just(wrongAudience);

    ReactiveOpaqueTokenIntrospector introspector =
        new AudienceCheckingReactiveIntrospector(
            delegate, "orders-api");

    StepVerifier.create(introspector.introspect("test-token"))
        .expectError(BadOpaqueTokenException.class)
        .verify();
}
```

Nếu AS đã introspect token active nhưng audience dành cho API khác, wrapper phải từ chối; không sửa `aud` trong principal để hợp thức hóa token.

### 13.3. Kiểm tra delegate error vẫn fail-closed

```java
@Test
void preservesInactiveTokenFailure() {
    ReactiveOpaqueTokenIntrospector delegate =
        token -> Mono.error(
            new BadOpaqueTokenException("inactive")
        );

    ReactiveOpaqueTokenIntrospector introspector =
        new AudienceCheckingReactiveIntrospector(
            delegate, "orders-api");

    StepVerifier.create(
            introspector.introspect("inactive-token"))
        .expectError(BadOpaqueTokenException.class)
        .verify();
}
```

Không dùng:

```java
.onErrorResume(error ->
    Mono.just(principal(
        "admin", "all-tenants", "ROLE_ADMIN"))
)
```

để làm tests xanh. Điều đó là *fail open*.

## 14. Test lazy subscription: không introspect trước khi subscribe

Một tính chất quan trọng của reactive I/O là công việc có thể được trì hoãn đến lúc subscription.

```java
@Test
void delegatesOnlyAfterSubscription() {
    AtomicInteger subscriptions = new AtomicInteger();

    ReactiveOpaqueTokenIntrospector delegate =
        token -> Mono.defer(() -> {
            subscriptions.incrementAndGet();
            return Mono.just(principal(
                "user-123",
                "shop-a",
                "SCOPE_orders.read"
            ));
        });

    ReactiveOpaqueTokenIntrospector introspector =
        new AudienceCheckingReactiveIntrospector(
            delegate, "orders-api");

    Mono<OAuth2AuthenticatedPrincipal> result =
        introspector.introspect("test-token");

    assertEquals(0, subscriptions.get());

    StepVerifier.create(result)
        .expectNextCount(1)
        .verifyComplete();

    assertEquals(1, subscriptions.get());
}
```

Import:

```java
import java.util.concurrent.atomic.AtomicInteger;
```

Test này chứng minh **test delegate subscription chưa chạy trước khi subscriber subscribe**. Nó không đo I/O blocking, event-loop starvation hoặc thread allocation.

### 14.1. Vì sao `Mono.defer` giúp test chắc hơn?

Khi delegate được khởi tạo bằng:

```java
token -> Mono.defer(() -> realAsyncCall(token))
```

nội dung callback không chạy trước subscription. Nếu wrapper viết `Mono.defer(() -> delegate.introspect(token))`, ngay cả việc gọi method delegate cũng được trì hoãn. Nhưng nếu `realAsyncCall` tự blocking khi subscribe, publisher vẫn blocking. Phải kiểm tra I/O implementation riêng.

## 15. Test non-blocking khác kiểm tra laziness

Một ứng dụng có thể qua mọi `StepVerifier` unit test nhưng vẫn chặn event loop trong production.

Ví dụ:

```java
return Mono.defer(() -> {
    blockingHttpClient.callIntrospection(token); // vẫn blocking
    return Mono.just(principal);
});
```

Test laziness sẽ pass vì callback chưa chạy trước subscription. Nhưng khi subscribe, request thread vẫn có thể bị chặn.

### 15.1. Dấu hiệu blocking trong code

- `.block()` hoặc `.blockOptional()` trong filter/introspector/service.
- `Thread.sleep(...)` hoặc chờ `Future.get()`.
- `RestTemplate`, `HttpURLConnection` hoặc HTTP SDK synchronous gọi ngay trong event loop.
- JDBC/JPA repository được gọi trực tiếp từ reactive handler.
- File I/O blocking dài hoặc lock chặn thread.
- `Mono.just(blockingMethod())`.
- `Mono.fromCallable(blockingMethod)` nhưng không được scheduling/cô lập đúng.
- Gọi `subscribe()` thủ công để “chờ” callback xác thực.

### 15.2. BlockHound và công cụ phát hiện blocking

Trong môi trường test, **BlockHound** có thể giúp phát hiện một số blocking operations khi chúng chạy trên thread được nhận diện là non-blocking. Ví dụ concept:

```java
// Setup test framework, nếu dependency/JDK tương thích:
BlockHound.install();
```

Sau đó thực thi flow thật qua WebFlux/Reactor Netty hoặc một test scheduling có chủ đích. Khi `Thread.sleep` hoặc blocking call được phát hiện trong event-loop, test có thể thất bại.

**Giới hạn:**

- BlockHound không bắt được mọi loại blocking I/O hay mọi thư viện.
- Cần chọn phiên bản tương thích JVM/agent và tránh cài đặt lặp.
- Một unit test chạy trên JUnit thread bình thường có thể không kích hoạt detection tương đương event-loop.
- Instrumentation overhead hoặc false positives cần được đánh giá.
- Test “không thấy lỗi BlockHound” không thay kiểm thử latency/tải.

Không lấy riêng một phép kiểm tra `Thread.currentThread().getName()` để chứng minh non-blocking; tên thread chỉ là quan sát, không nói method có blocking hay không.

### 15.3. Integration test với AS stub có delay

Một bài test có giá trị:

1. Dùng test HTTP server mô phỏng introspection endpoint.
2. Cho response `active=true` sau một khoảng delay bất đồng bộ.
3. Gửi nhiều bearer requests qua WebTestClient tới WebFlux Resource Server.
4. Quan sát không có hàng loạt event-loop threads bị giữ do blocking.
5. Xác nhận tất cả requests nhận đúng identity/authorization results.
6. Đo latency và throughput trong điều kiện giới hạn đã đặt.

Không cần benchmark tối đa trong STEP unit tests, nhưng nên có test/monitoring dưới tải ở hệ thống thật. **Một request đơn lẻ có response đúng chưa chứng minh concurrency behavior an toàn.**

## 16. Timeout và lỗi mạng: non-blocking không được biến thành fail-open

HTTP introspection có thể gặp:

```text
DNS failure
TLS handshake failure
Authorization Server timeout
503 from introspection endpoint
Malformed introspection response
active=false
Invalid introspection credentials
```

Trường hợp `active=false` chứng minh token không active theo AS. Trường hợp network timeout nghĩa Resource Server **không thể xác minh token**, chứ không nhất thiết token đã bị thu hồi. Nhưng cả hai đều **không được coi là authenticated success**.

### 16.1. Timeout cho publisher

Một decorator có thể giới hạn thời gian chờ introspection:

```java
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    return delegate.introspect(token)
        .timeout(Duration.ofSeconds(2));
}
```

Imports:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;
```

Đây là timeout ở tầng publisher; HTTP client vẫn cần connect/read/response timeouts và resource limits phù hợp. Timeout có thể tạo `TimeoutException`; exception mapping sẽ ảnh hưởng HTTP response cuối cùng.

Nếu muốn phân loại timeout thành lỗi introspection hạ tầng:

```java
return delegate.introspect(token)
    .timeout(Duration.ofSeconds(2))
    .onErrorMap(
        TimeoutException.class,
        error -> new OAuth2IntrospectionException(
            "Introspection temporarily unavailable", error)
    );
```

Imports:

```java
import java.util.concurrent.TimeoutException;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
```

Không convert mọi lỗi thành `BadOpaqueTokenException` theo kiểu “token bị thu hồi”; lỗi network và token inactive là những sự kiện khác nhau. Dù HTTP status có thể phụ thuộc exception handlers, tất cả failure cases phải giữ **fail-closed authentication**.

### 16.2. Retry có giới hạn

Một lỗi network thoáng qua đôi khi có thể được retry, nhưng:

- Không retry vô hạn.
- Không retry lỗi token inactive/contract mismatch.
- Cần time budget cho cả request, không chỉ mỗi attempt.
- Cần giới hạn concurrency, backoff và jitter để tránh thổi bùng tải lên AS.
- Cần đo tỷ lệ retries/timeouts.
- Không kéo dài cache của token quá hạn chỉ vì AS đang lỗi.

### 16.3. Không sử dụng `onErrorResume` để tạo principal “tạm thời”

Sai nghiêm trọng:

```java
return delegate.introspect(token)
    .onErrorResume(ex ->
        Mono.just(defaultAdminPrincipal)
    );
```

Điều này cho phép authentication thành công ngay khi AS hoặc mạng gặp sự cố. Một error handler có thể thay **loại lỗi/hướng observability**, nhưng không được cấp quyền không được chứng minh.

## 17. Test timeout bằng StepVerifier và virtual time

Nếu kiểm tra một publisher có timeouts, Reactor Test có `StepVerifier.withVirtualTime(...)` để không phải chờ thời gian thật trong unit test (với điều kiện scheduler/time operations được tạo đúng trong lambda).

Ví dụ:

```java
@Test
void timesOutWhenDelegateNeverResponds() {
    ReactiveOpaqueTokenIntrospector delegate =
        token -> Mono.never();

    ReactiveOpaqueTokenIntrospector timed =
        token -> delegate.introspect(token)
            .timeout(Duration.ofSeconds(3));

    StepVerifier.withVirtualTime(
            () -> timed.introspect("test-token"))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(3))
        .expectError(TimeoutException.class)
        .verify();
}
```

Imports:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
```

Test này chứng minh **logic Reactor timeout** theo virtual scheduler. Nó không chứng minh HTTP client sử dụng non-blocking transport, cũng không kiểm tra TLS, DNS hoặc server socket timeout. Các vấn đề đó cần integration tests và vận hành.

### 17.1. Không sử dụng `Thread.sleep` để thử timeout

Một test:

```java
Thread.sleep(3000);
```

chỉ chặn test thread, làm test chậm/flaky. Virtual time phù hợp với các Reactor operators có scheduler hỗ trợ; còn HTTP I/O thật cần kiểm tra bằng test server và timeout client.

## 18. Test truyền context với `ReactiveSecurityContextHolder.withAuthentication`

Có thể unit test một pipeline đọc Authentication mà không cần chạy HTTP server. Chuẩn bị `Authentication` giả lập:

```java
Authentication authentication =
    new TestingAuthenticationToken(
        "user-123",
        "not-a-real-secret",
        "SCOPE_orders.read"
    );
```

Với test này, mục tiêu là Reactor Context propagation chứ không phải kiểm tra opaque token introspection thật. `TestingAuthenticationToken` là test helper, không được dùng làm principal production để bypass introspection.

### 18.1. Test cùng principal trước và sau `publishOn`

```java
@Test
void keepsAuthenticationAcrossPublishOn() {
    Authentication authentication =
        new TestingAuthenticationToken(
            "user-123",
            "test-credential",
            "SCOPE_orders.read"
        );

    Mono<String> pipeline =
        ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .publishOn(Schedulers.parallel())
            .flatMap(name ->
                ReactiveSecurityContextHolder.getContext()
                    .map(ctx ->
                        name + ":" +
                        ctx.getAuthentication().getName()
                    )
            );

    StepVerifier.create(
            pipeline.contextWrite(
                ReactiveSecurityContextHolder
                    .withAuthentication(authentication)
            )
        )
        .expectNext("user-123:user-123")
        .verifyComplete();
}
```

Imports:

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
```

Test này đánh giá khả năng Reactor Context đi qua các operators đã dùng. Nó **không** chứng minh BearerTokenAuthentication được dựng từ introspection thật, vì Authentication do test tạo.

### 18.2. Test khi không có context

```java
@Test
void noContextDoesNotCreateAnAdmin() {
    Mono<String> currentName =
        ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName());

    StepVerifier.create(currentName)
        .verifyComplete();
}
```

Thông thường, không có security context trong subscriber chain thì publisher trên không tạo tên user. Service protected nên xử lý trường hợp đó theo policy, thường bằng lỗi từ chối, thay vì gán “admin mặc định”.

### 18.3. Test nhầm vị trí `contextWrite`

Reactor Context được áp cho upstream của vị trí `contextWrite` trong subscription chain. Nếu bạn tách thành một subscription độc lập, context mới có thể không tới publisher đó. Trong unit tests, nên kiểm tra đúng chuỗi mà request thật subscribe thay vì gọi phương thức riêng rồi tự subscribe ngoài pipeline.

## 19. Test opaque authentication tại HTTP layer bằng WebTestClient

Spring Security Test có hỗ trợ **`mockOpaqueToken()`** cho WebFlux. Nó dựng một Authentication đã xác thực cho request test, nhờ vậy ta kiểm tra routes và method security mà **không cần AS introspection endpoint**.

Ví dụ:

```java
@SpringBootTest
@AutoConfigureWebTestClient
class OrdersAuthorizationTests {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void readScopeCanAccessVisibleOrder() {
        webTestClient
            .mutateWith(
                mockOpaqueToken()
                    .attributes(attrs -> {
                        attrs.put("sub", "user-123");
                        attrs.put("tenant_id", "shop-a");
                    })
                    .authorities(
                        new SimpleGrantedAuthority(
                            "SCOPE_orders.read")
                    )
            )
            .get()
            .uri("/api/orders/order-1")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void missingReadScopeIsForbidden() {
        webTestClient
            .mutateWith(
                mockOpaqueToken()
                    .authorities(
                        new SimpleGrantedAuthority(
                            "SCOPE_profile")
                    )
            )
            .get()
            .uri("/api/orders/order-1")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Imports:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;
```

**Điều kiện:** Controller, repository và test fixtures phải được chuẩn bị để trả 200 cho order-1 của user-123. Nếu order không tồn tại hoặc service còn policy khác, status sau HTTP authorization có thể là 404/403, không phải 200.

### 19.1. `mockOpaqueToken()` thực sự làm gì?

Nó đưa một `BearerTokenAuthentication` tương ứng principal, attributes và authorities giả lập vào WebFlux test security context. Nó hữu ích để kiểm tra:

- Phân quyền `SCOPE_...` theo route.
- Controller có nhận Authentication/principal không.
- Object-level policy với subject/tenant đã mô phỏng.
- Reactive service có giữ context trong request chain không.
- HTTP responses 2xx/403/404 với quyền khác nhau.

**Nó không kiểm tra:**

- Token có `active=true` từ AS thật không.
- HTTP call introspection có non-blocking không.
- Basic/mTLS credentials tới AS có đúng không.
- AS timeout/revocation có được xử lý không.
- Custom `ReactiveOpaqueTokenIntrospector` có chạy không.
- Caller gửi Bearer token thật có được parse/validate đúng không.

Không dùng một HTTP test với `mockOpaqueToken()` làm bằng chứng integration của introspection endpoint.

### 19.2. Vì sao thay đổi authorities trong test quan trọng?

Trong Spring Security opaque support, scope claim từ AS thường được ánh xạ thành `SCOPE_...`. Khi test bằng `mockOpaqueToken()`, bạn có thể cấp authorities tường minh:

```java
mockOpaqueToken()
    .authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read"))
```

Nếu route yêu cầu `SCOPE_orders.export`, request này phải bị từ chối dù có `orders.read`. Quyền export là contract khác, không mặc định suy ra từ read.

### 19.3. Gắn principal tùy chỉnh cho test

Nếu object policy cần một principal có name/attributes đặc biệt:

```java
OAuth2AuthenticatedPrincipal testPrincipal =
    new DefaultOAuth2AuthenticatedPrincipal(
        "user-123",
        Map.of(
            "sub", "user-123",
            "tenant_id", "shop-a"
        ),
        List.of(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )
    );

webTestClient
    .mutateWith(
        mockOpaqueToken().principal(testPrincipal)
    )
    .get()
    .uri("/api/orders/order-1")
    .exchange();
```

Đây là mô phỏng identity cho test authorization, không là token đã được AS xác nhận.

## 20. Integration test với introspection HTTP thật

Để kiểm tra **toàn bộ từ Bearer header tới delegate HTTP**, không dùng `mockOpaqueToken()`. Thay vào đó:

1. Khởi động WebFlux Resource Server trong test context.
2. Dùng một HTTP stub server làm **fake Authorization Server introspection endpoint**.
3. Cấu hình `spring.security.oauth2.resourceserver.opaquetoken.introspection-uri` tới stub.
4. Cấu hình introspection client credentials test.
5. Gửi request bằng WebTestClient với header `Authorization: Bearer test-opaque-token`.
6. Stub xác nhận đã nhận HTTP introspection request và thông tin auth đúng.
7. Stub trả `active=true` + scopes/claims.
8. WebTestClient xác nhận response/actor propagation/authorization.
9. Lặp lại với `active=false`, timeout, malformed JSON, 401/500 từ AS.

### 20.1. Mẫu test HTTP request

```java
webTestClient.get()
    .uri("/api/orders/order-1")
    .headers(headers ->
        headers.setBearerAuth("test-opaque-token"))
    .exchange()
    .expectStatus().isOk();
```

Ở test này, **không gắn `mockOpaqueToken()`**, vì nó có thể bypass authentication manager/introspector mà bạn cần kiểm tra.

### 20.2. Response của fake Authorization Server

Case active:

```json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "tenant_id": "shop-a"
}
```

Case inactive:

```json
{
  "active": false
}
```

Case contract sai:

```json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders.read",
  "aud": ["payments-api"],
  "tenant_id": "shop-a"
}
```

Nếu có wrapper audience, case cuối phải bị từ chối **trong authentication**, trước khi controller chạy.

### 20.3. Vì sao cần stub AS thay vì gọi AS production?

- Test không phụ thuộc network production.
- Không dùng client secrets thật.
- Có thể kiểm soát `active=false` và lỗi hạ tầng.
- Có thể thử delay/timeouts deterministically.
- Không tạo/thu hồi tokens ngoài ý muốn.
- Có thể đo số lần introspection và retry.

WireMock, MockWebServer hoặc một reactive test server đều có thể dùng tùy stack; điều quan trọng là test **thực sự đi qua HTTP introspection**, không chỉ tạo principal giả.

## 21. Test end-to-end rằng actor đi tới service đúng

Một HTTP test có thể dùng test service lưu actor vào một thread-safe sink hoặc tạo response gồm thông tin không nhạy cảm để xác minh principal. Ví dụ endpoint dành cho test:

```java
@GetMapping("/test/whoami")
public Mono<Map<String, String>> whoAmI() {
    return currentActorProvider.currentActor()
        .map(actor -> Map.of(
            "subject", actor.subject(),
            "tenant", actor.tenantId()
        ));
}
```

Với introspection stub trả:

```json
{
  "active": true,
  "sub": "user-123",
  "tenant_id": "shop-a",
  "scope": "orders.read"
}
```

test kỳ vọng:

```json
{
  "subject": "user-123",
  "tenant": "shop-a"
}
```

**Không để endpoint `/test/whoami` công khai trong production** chỉ để debug. Có thể triển khai bằng `@TestConfiguration`/test-only controller hoặc kiểm tra gián tiếp qua service spy/test fixtures.

### 21.1. Test hai requests đồng thời

Một bài test ranh giới hữu ích:

```text
Request A:
  token-a → sub=user-123, tenant=shop-a

Request B:
  token-b → sub=user-456, tenant=shop-b

Cả hai cùng lúc gọi service reactive.
```

Kỳ vọng:

- Response A chỉ chứa dữ liệu thuộc user-123/shop-a.
- Response B chỉ chứa dữ liệu thuộc user-456/shop-b.
- Không có lẫn subject/tenant giữa requests.
- Không có shared mutable field giữ “current user”.
- Không có blocking event-loop dưới tải đã định.

Nếu test chỉ có một user, một bug về static Authentication hoặc thiếu tenant filter có thể khó bị phát hiện.

### 21.2. Đừng dùng ThreadLocal làm “test oracle”

Đọc `SecurityContextHolder.getContext()` trong một ThreadLocal ở callback bất kỳ rồi kết luận context bị mất là không chính xác với WebFlux. Test nên dùng `ReactiveSecurityContextHolder.getContext()` trong pipeline hoặc truyền actor tường minh.

## 22. Method security trong reactive service

Nếu service cần chặn theo scope, WebFlux hỗ trợ reactive method security:

```java
@Configuration
@EnableReactiveMethodSecurity
public class MethodSecurityConfiguration {
}
```

Ví dụ:

```java
@Service
public class OrderService {

    private final ReactiveOrderRepository repository;

    public OrderService(ReactiveOrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Mono<OrderDto> getVisibleOrder(
            String id,
            AuthenticatedActor actor) {

        return repository.findVisibleOrder(
                id, actor.tenantId(), actor.subject())
            .map(OrderDto::from)
            .switchIfEmpty(
                Mono.error(new OrderNotFoundException())
            );
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
```

`@PreAuthorize` kiểm tra scope khi method security proxy được áp. Repository query kiểm tra resource-level owner/tenant. Không đồng nhất hai quyền.

### 22.1. Method security cũng cần Reactor Context

Reactive method security đọc Authentication từ Reactor Context. Nếu developer gọi service dưới một subscription ngoài request context hoặc bằng self-invocation làm bypass proxy, annotation có thể không chạy như kỳ vọng.

**Thử qua entrypoint/proxy thực tế** khi muốn chứng minh method security hoạt động, và test object policy ở service/repository riêng.

### 22.2. Reactive authorization khi phải hỏi DB

Một policy cần database I/O nên dùng reactive repository và một authorization mechanism hỗ trợ `Mono<Boolean>` hoặc `ReactiveAuthorizationManager` theo phiên bản Spring Security. Đừng viết `@PreAuthorize` expression gọi một blocking JDBC method để suy ra quyền.

Có thể chọn mô hình:

```text
@PreAuthorize: kiểm tra authority thao tác (không I/O)
Service: reactive policy/repository kiểm tra tenant/owner/ACL
Mutation: conditional update / transaction phù hợp
```

Điều này thường dễ suy luận hơn.

## 23. Kiểm thử negative cases: 401, 403 và lỗi nghiệp vụ

Một ma trận:

| Tình huống | Authentication | Authorization | HTTP thường gặp |
|---|---|---|---|
| Không gửi Bearer token vào protected API | Chưa xác thực | Không cấp quyền | `401` |
| Token opaque inactive | Introspection từ chối | Chưa xét scope | `401 invalid_token` |
| AS trả malformed response | Introspection failure | Chưa xét quyền | Lỗi auth/hạ tầng tùy mapping |
| Token active, audience sai contract | Wrapper từ chối | Chưa xét quyền | Thường `401` |
| Token active, scope `profile` | Đã xác thực | GET Orders đòi `orders.read` | `403` |
| Token active, scope read, order ngoài tenant | Đã xác thực | Object policy từ chối | `403` hoặc `404` |
| Token active, đủ scope, order không có | Đã xác thực | Không có tài nguyên | `404` |
| Token active, đủ quyền, order sai trạng thái | Đã xác thực | Business state không hợp lệ | `409` hoặc mã domain |
| AS timeout | Không xác thực được | Không cho đi tiếp | Fail closed; status phụ thuộc exception flow |

`401` và `403` không nên bị dùng thay nhau tùy tiện. Một token active nhưng thiếu scope có thể dùng tại endpoint khác; không được coi nó là token bị thu hồi.

### 23.1. Không gửi error details nhạy cảm cho client

Không trả raw introspection response, client secret, bearer token, internal network topology hoặc principal của object người khác. Có thể log loại lỗi tổng quát và request ID; chi tiết chẩn đoán đặt ở logs được kiểm soát.

### 23.2. CORS trên browser request

Một SPA gọi cross-origin cần CORS headers đúng trên cả success và 401/403 responses, nếu frontend cần đọc status. Preflight thường không mang Bearer token; nếu bị chặn do yêu cầu authentication sớm, browser có thể báo CORS error trước khi gửi request thật.

## 24. Trace/correlation context không phải Authentication context

Một số ứng dụng dùng:

- Reactor Context: Authentication/trace metadata.
- MDC/SLF4J: logging key-value theo thread.
- OpenTelemetry tracing context.
- ServerWebExchange attributes.
- HTTP header `X-Request-Id`.

Các cơ chế này có thể được tích hợp, nhưng **không tự đồng nhất**.

### 24.1. MDC truyền theo thread khác Reactor Context

Một đoạn:

```java
MDC.put("userId", "user-123");
```

gắn thông tin vào thread hiện tại theo MDC implementation. Khi reactive pipeline chuyển thread, giá trị có thể không được giữ nếu chưa cấu hình context propagation phù hợp. Ngược lại, `ReactiveSecurityContextHolder.getContext()` dùng Reactor Context chứ không đọc MDC.

Không dùng MDC như nguồn principal cho authorization.

### 24.2. Correlation ID an toàn

Một log có thể chứa:

```text
request_id=req-123
route=GET /api/orders/{id}
token_introspection=SUCCESS
authorization=DENIED
reason=ORDER_NOT_VISIBLE
```

Hãy tránh:

```text
Authorization: Bearer <RAW_ACCESS_TOKEN>
Introspection-Client-Secret: <SECRET>
Cookie: SESSION=<SECRET>
```

Nếu correlation ID do client cung cấp, validate/sanitize nó trước khi log. Không coi `X-Request-Id` là identity hoặc bằng chứng token hợp lệ.

## 25. Background jobs, messages và mất ngữ cảnh HTTP

Một HTTP request có thể tạo background job:

```http
POST /api/reports/export
Authorization: Bearer <OPAQUE_TOKEN>
```

Khi job chạy sau vài phút trong scheduler khác hoặc một service khác, Reactor SecurityContext của **HTTP request gốc** không tự tồn tại ở đó.

Cần thiết kế:

- Actor ID/issuer/tenant và phạm vi được phép được ghi nhận từ principal đã xác thực.
- Re-check quyền tại thời điểm thực thi khi business yêu cầu.
- Không lưu raw bearer token không cần thiết vào job payload.
- Không để service account có quyền DB rộng bypass object-level limits của actor ban đầu.
- Có lifecycle/idempotency/audit rõ cho job.
- Nếu cần delegation downstream, dùng cơ chế token exchange/delegated access theo hợp đồng.

**Đừng cố đọc `ReactiveSecurityContextHolder.getContext()` trong job và “phát minh” actor mặc định nếu nó rỗng.** Job cần identity/authorization contract riêng.

## 26. Kiểm tra cache introspection và tính cập nhật của quyền

Opaque introspection hữu ích khi cần hỏi AS token còn active hay không. Nếu ứng dụng cache kết quả:

- Độ trễ/lượng HTTP introspection giảm.
- Nhưng token revoked có thể vẫn được chấp nhận đến khi cache hết hạn.
- Scope, tenant hoặc membership thay đổi có thể chưa được phản ánh.
- Key cache phải không làm lộ raw bearer credentials.
- TTL cần phù hợp với expiration và yêu cầu revocation.
- Thay đổi policy của wrapper có thể yêu cầu invalidation.

### 26.1. Cache trước hay sau wrapper?

```text
Bearer token
    │
    ├── delegate introspection
    │        └── active + claims
    │
    ├── contract wrapper
    │        └── aud/issuer/client/tenant validation
    │
    └── principal được chấp nhận
```

Nếu cache **sau wrapper**, cache chứa kết quả đã qua contract nhưng phải cập nhật khi policy thay đổi. Nếu cache **trước wrapper**, mỗi cache hit vẫn cần chạy contract checks. Dù cache ở đâu, **không lưu kết quả authentication lỗi thành success**.

### 26.2. Test caching như thế nào?

Có thể dùng delegate giả đếm số subscriptions:

```java
AtomicInteger calls = new AtomicInteger();

ReactiveOpaqueTokenIntrospector delegate = token ->
    Mono.defer(() -> {
        calls.incrementAndGet();
        return Mono.just(testPrincipal);
    });
```

Sau đó thử nhiều lần gọi token giống nhau để kiểm tra cache hit/miss, TTL và invalidation. Cần lưu ý test này chỉ kiểm tra cache logic, không chứng minh revocation behavior của AS production.

### 26.3. Lỗi cache theo principal

Không cache business response chỉ theo `orderId` nếu dữ liệu được phép trả phụ thuộc subject/tenant/scope. Cache hit không phải bằng chứng quyền. Cần chạy object authorization trước khi trả data cached hoặc thiết kế cache isolation phù hợp.

## 27. Multi-tenant và multi-issuer trong reactive introspection

Một Resource Server có thể chấp nhận tokens từ nhiều AS/realms:

```text
AS shop:
  https://login.example.test/realms/shop/introspect

AS partners:
  https://login.example.test/realms/partners/introspect
```

Mỗi issuer có thể có:

- Introspection URL và client credentials khác nhau.
- Scope claim/authority naming khác nhau.
- Tenant claim semantics khác nhau.
- Quy tắc audience và client ID khác nhau.
- Subject namespaces khác nhau.

Nếu cần multi-issuer, dùng một resolver/mapping **allowlist** các authentication managers/introspectors đáng tin. Không đọc URL từ chuỗi token chưa xác thực rồi gọi endpoint tùy ý; làm vậy có thể gây SSRF hoặc nhận principal từ AS do attacker kiểm soát.

### 27.1. Truyền issuer-qualified identity

Nếu cả hai issuers cùng có `sub=user-123`, chúng có thể đại diện hai người khác nhau. Actor dùng cho object authorization thường cần cặp **(issuer, subject)** hoặc mapping account nội bộ.

Không ghép người dùng chỉ bằng principal name hoặc email nếu contract không đảm bảo tính duy nhất.

### 27.2. Test nhiều issuers

Tối thiểu:

| Token | AS trả response | Policy của Orders API | Kết quả |
|---|---|---|---|
| Shop token cho Orders | active, aud đúng, tenant shop | Cho phép | Qua authentication |
| Partner token trong allowlist | active, đúng contract partners | Cho phép có điều kiện | Qua authentication |
| Token issuer không được tin | URL/realm ngoài allowlist | Từ chối | Không introspect endpoint tùy ý |
| Token AS Payments | active, aud=payments | Từ chối | Không dùng ở Orders |
| Token thiếu tenant bắt buộc | active, thiếu claim | Từ chối theo contract | Không tự điền tenant |
| Token từ AS outage | Không xác minh được | Fail closed | Không tạo Authentication |

## 28. Đo hiệu năng mà không đánh đổi bảo mật

Những chỉ số có thể theo dõi:

| Metric | Câu hỏi |
|---|---|
| Introspection latency p50/p95/p99 | AS trả lời nhanh và ổn định không? |
| Active/inactive token rate | Bao nhiêu token không hợp lệ? |
| Timeout/network/TLS errors | AS hay network đang có sự cố? |
| In-flight introspection requests | Có quá nhiều request đang chờ không? |
| Event-loop blocking detections | Có blocking code trong reactive pipeline không? |
| WebFlux event-loop utilization | I/O threads có bị giữ bất thường không? |
| 401 vs 403 counts | Authentication failure hay thiếu quyền? |
| Request-to-service identity mismatches | Có nguy cơ mất/trộn security context không? |
| Cache hit/miss, revoked token window | Cache có làm quyền cũ tồn tại lâu không? |
| Reactive repository latency | Object-level policy có gây nghẽn không? |

### 28.1. Đo dưới tải concurrent

Một HTTP test đơn lẻ thành công không đủ. Nên thử hàng chục/hàng trăm requests concurrent phù hợp môi trường test, với AS stub có response delay kiểm soát. Quan sát:

- Latency có tăng tuyến tính bất thường theo số event-loop threads không.
- Có `block()`/ThreadLocal assumptions gây lỗi ngẫu nhiên không.
- User A/B có bị trộn tenant không.
- Khi một request introspection fail, requests khác có tiếp tục hoạt động không.
- Khi timeout, connection resources có được giải phóng không.

Không dùng một phép benchmark thiếu kiểm soát rồi kết luận “WebFlux nhanh hơn Servlet trong mọi trường hợp”. Kết quả phụ thuộc AS, TLS, HTTP pooling, CPU, DB và kiến trúc.

### 28.2. Bounded concurrency và backpressure

Một API có thể bị tấn công bằng hàng loạt bearer tokens ngẫu nhiên buộc introspection endpoint xử lý nhiều requests. Cần:

- Rate limiting theo nguồn/caller như có thể áp trước auth.
- Connection pool, concurrency caps và queue limits.
- Timeouts và circuit breaking phù hợp.
- Không retry invalid tokens.
- Giới hạn kích thước Authorization header/token.
- Monitoring tỷ lệ request token sai.
- Không cho AS outage biến thành việc cấp principal giả.

## 29. Bảng phân loại các cấp kiểm thử

| Loại test | Công cụ | Kiểm tra gì | Không chứng minh gì |
|---|---|---|---|
| Unit introspector | StepVerifier + fake delegate | Success/error, contract, lazy subscription | HTTP AS/network non-blocking thực |
| Reactive time behavior | StepVerifier virtual time | Timeout/retry operators | TLS/socket behavior |
| Context test | ReactiveSecurityContextHolder.withAuthentication | Reactor context đi qua operators | Token đã introspect thật |
| HTTP authorization | WebTestClient + mockOpaqueToken | 401/403/role/scope/actor access ở web layer | AS introspection thật |
| Integration introspection | WebTestClient + HTTP AS stub + real Bearer header | WebFilter → HTTP delegate → principal → service | Production AS availability |
| Non-blocking instrumentation | BlockHound/tracing/under-load test | Một số blocking calls/event-loop starvation | Mọi lỗi concurrency/không blocking |
| Business object policy | Reactive repository/service tests | Tenant/owner/ACL/list/export | Signature/introspection đúng |
| Load/performance | Reactive traffic + AS stub/test AS | Throughput, latency, saturation, timeouts | Chính sách quyền đúng nếu không test data |

Không cần dồn mọi assertion vào một test lớn. Chia test rõ ràng giúp tìm ra lớp lỗi.

## 30. Ma trận hành vi end-to-end cần có

| Input | Expected introspection | Authentication context | API expected |
|---|---|---|---|
| Không Bearer token | Không gọi AS cho request này | Không có authenticated bearer principal | Protected route thường 401 |
| Opaque token inactive | Trả `active=false` | Không tạo trusted principal | Thường 401 |
| Opaque token active, `orders.read` | Success | Actor đúng `sub`/tenant | GET visible order thành công |
| Token active, thiếu `orders.read` | Success | Actor có quyền khác | GET Orders thường 403 |
| Token active, wrong audience | Delegate active, wrapper từ chối | Không trusted principal | Authentication failure |
| Token active, order của user khác | Success | Actor đúng user | Object policy 403/404 |
| Token active, tenant không phù hợp | Theo token contract hoặc service | Không được truy cập tenant ngoài phạm vi | Deny |
| AS timeout | Publisher error/timeout | Không Authentication | Fail closed |
| AS trả malformed JSON | Introspection error | Không Authentication | Fail closed |
| Hai users đồng thời | Hai kết quả introspection | Context tách biệt A/B | Không lộ dữ liệu chéo |
| `publishOn` trong service | Introspection success | Reactor Context tiếp tục qua chain | Subject vẫn đúng |
| Job tách subscription khỏi request | Không còn HTTP context mặc định | Không tự giả actor | Dùng explicit delegated actor/policy |

## 31. Những sai lầm phổ biến

### Sai lầm 1 — Dùng Servlet `OpaqueTokenIntrospector` cho WebFlux

Dễ dẫn tới I/O đồng bộ trong reactive path. Dùng `ReactiveOpaqueTokenIntrospector` và implementation reactive phù hợp.

### Sai lầm 2 — Nghĩ trả `Mono` tức không chặn

`Mono.just(blockingCall())` vẫn gọi blocking trước; `Mono.defer(blockingCall)` vẫn có thể block khi subscribe. Kiểm tra transport và thread thực.

### Sai lầm 3 — Gọi `block()` để lấy principal trong controller

Làm event-loop bị chặn hoặc ném exception. Dùng reactive composition, `@AuthenticationPrincipal` hoặc actor adapter.

### Sai lầm 4 — Tự `subscribe()` để “khởi động” authentication

Tạo subscription tách rời, lỗi và context có thể không propagate. Trả publisher cho Spring Security.

### Sai lầm 5 — Đọc `SecurityContextHolder` ThreadLocal như Servlet

Trong WebFlux dùng Reactor Context; test phải dùng `ReactiveSecurityContextHolder` hoặc actor tường minh.

### Sai lầm 6 — Dùng `mockOpaqueToken()` rồi kết luận AS introspection ổn

Mock bỏ qua HTTP introspection. Cần integration test real Bearer header + AS stub.

### Sai lầm 7 — Dùng StepVerifier một token hợp lệ rồi kết luận non-blocking

StepVerifier xác minh signals, không tự phát hiện blocking I/O. Cần instrumentation/load/client implementation review.

### Sai lầm 8 — Đổi lỗi AS thành `Mono.just(adminPrincipal)`

Đây là *fail open* nghiêm trọng, tuyệt đối không làm.

### Sai lầm 9 — Nhầm `active=true` với đủ quyền

Endpoint read/write còn cần authority; bản ghi còn cần owner/tenant policy.

### Sai lầm 10 — Gán actor từ request body/header

Client có thể tự khai `tenantId` hoặc `sub`. Actor phải tạo từ principal AS đã xác thực hoặc server-side membership.

### Sai lầm 11 — Lưu Authentication vào static variable

Concurrent requests có thể trộn principal. Security context phải theo subscriber/request, không dùng shared mutable state.

### Sai lầm 12 — Mất context trong jobs hoặc callbacks ngoài pipeline

Không tự giả danh tính hoặc forward raw token không cần thiết. Truyền actor/delegation explicit theo contract.

### Sai lầm 13 — Kết nối blocking DB trong object policy

Một reactive authentication chain cũng có thể bị nghẽn vì repository blocking. Dùng reactive data access hoặc cách ly legacy operations có giới hạn.

### Sai lầm 14 — Bỏ CORS preflight vì thiếu token

Browser preflight thường không mang Bearer. CORS policy phải xử lý trước xác thực request thật.

### Sai lầm 15 — Cache introspection vô hạn

Có thể khiến token revoked vẫn được chấp nhận. TTL/invalidation phải phù hợp yêu cầu revocation.

### Sai lầm 16 — Log raw opaque token hoặc client secret

Token/secret là credentials. Log request ID, route và category lỗi, không log raw Authorization header.

### Sai lầm 17 — Đưa mọi database query vào introspector

Introspector nên kiểm tra token-wide contract. Quyền với order ID/tenant phải nằm trong service/authorization layer theo resource.

### Sai lầm 18 — Nhầm lỗi 401 và 403

Authentication failure thường 401; token được chấp nhận nhưng thiếu quyền thường 403; business object policy có thể trả 403/404. Giữ đúng semantics.

### Sai lầm 19 — Cho mọi issuer được tự chọn introspection endpoint

Nếu chọn URL từ token chưa xác thực, có nguy cơ SSRF hoặc tin AS của attacker. Dùng trusted allowlist/mapping.

### Sai lầm 20 — Không thử dữ liệu nhiều tenants/users

Một test với chỉ một user có thể bỏ sót context leakage, owner/tenant query thiếu điều kiện và static principal bugs.

## 32. Lộ trình triển khai một kiểm thử đáng tin

**Bước 1.** Xác định opaque-token contract của AS: `active`, `sub`, `scope`, `aud`, tenant fields, response/error semantics và introspection credentials.

**Bước 2.** Cấu hình đúng WebFlux `SecurityWebFilterChain` và `ReactiveOpaqueTokenIntrospector`. Không dùng Servlet configuration.

**Bước 3.** Ưu tiên implementation reactive của Spring Security để gọi AS. Nếu có custom wrapper, dùng `Mono.defer`, `flatMap`, `Mono.error` và fail closed.

**Bước 4.** Dùng StepVerifier để kiểm tra success, inactive, wrong audience, empty, exception propagation và timeout behavior.

**Bước 5.** Kiểm tra laziness bằng counter/stub; **không coi test này là bằng chứng non-blocking**.

**Bước 6.** Dùng BlockHound/instrumentation và AS stub có delay để kiểm tra event-loop blocking, concurrency và timeouts.

**Bước 7.** Dùng `ReactiveSecurityContextHolder.withAuthentication(...)` để test context qua `map`/`flatMap`/`publishOn`.

**Bước 8.** Dùng WebTestClient với `mockOpaqueToken()` để kiểm tra route, scope, 403, principal injection và object policy.

**Bước 9.** Dùng WebTestClient **không mockOpaqueToken**, gửi Bearer header thật tới AS stub để kiểm tra full introspection path.

**Bước 10.** Chuẩn bị fixtures hai users, hai tenants, ít nhất một order thuộc user khác, test cross-tenant denial và list filtering.

**Bước 11.** Kiểm tra error responses, CORS, no-token request, AS outage và không lộ token/secrets.

**Bước 12.** Đo under-load với nhiều requests concurrent, theo dõi p95/p99 latency, timeouts, event-loop saturation và context leakage.

## 33. Tài liệu tham khảo

- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token, Reactive](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): cấu hình introspection reactive, authorities và custom introspector.
- [Spring Security Reference — Testing OAuth 2.0 in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockOpaqueToken()`, `WebTestClient` và mô phỏng principal/authorities.
- [Spring Security Reference — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, reactive authorization và access decisions.
- [Spring Security API — ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): `getContext()`, `withAuthentication(...)` và Reactor Context.
- [Spring Security Reference — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `ServerHttpSecurity` và `SecurityWebFilterChain`.
- [Project Reactor Reference — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Context propagation, `contextWrite` và subscription semantics.
- [Project Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time và test reactive publishers.
- [BlockHound](https://github.com/reactor/BlockHound): công cụ phát hiện một số blocking calls trong reactive threads khi cấu hình tương thích.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection request/response và thuộc tính `active`.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): truyền bearer credentials, lỗi và HTTP authentication semantics.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): default deny, least privilege, object-level authorization.

**Kết luận:** Kiểm thử opaque-token Resource Server trong WebFlux phải chứng minh cả **token được introspect và xác thực đúng**, **publisher thật sự không chặn event loop**, và **Authentication được giữ đúng theo Reactor subscriber context tới lớp xử lý**. Dùng `ReactiveOpaqueTokenIntrospector` với implementation HTTP reactive đáng tin; dùng `StepVerifier` cho publisher/timeout, `ReactiveSecurityContextHolder.withAuthentication` cho context, `WebTestClient + mockOpaqueToken()` cho authorization, và **WebTestClient + introspection HTTP stub** cho luồng xác thực thật. Sau khi token active, scope và quyền owner/tenant vẫn phải được kiểm tra tại HTTP/service layers. Tránh `block()`, `subscribe()` thủ công, principal giả khi AS lỗi, shared mutable Authentication và logs chứa bearer tokens.
