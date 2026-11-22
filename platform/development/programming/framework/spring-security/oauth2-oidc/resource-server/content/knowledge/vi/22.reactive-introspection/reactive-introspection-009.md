# Phân biệt lỗi từ xa, token không hiệu lực và chính sách từ chối

Trong **Spring Security OAuth 2.0/OIDC Resource Server** chạy trên **Spring WebFlux**, access token có thể được kiểm tra bằng **reactive token introspection**. Resource Server gửi token tới Authorization Server (AS) qua introspection endpoint, sau đó dùng kết quả để tạo `Authentication` và kiểm tra quyền. Khác với việc xác minh JWT tại chỗ, mô hình này phụ thuộc thêm vào **đường gọi HTTP từ xa**.

Khi một request thất bại, ba tình huống quan trọng thường bị gộp nhầm thành “token sai”:

1. **Token không hiệu lực:** AS trả một kết luận introspection hợp lệ, ví dụ `"active": false`, hoặc token không đạt các yêu cầu xác thực/profile được hệ thống quy định.
2. **Lỗi từ xa:** Resource Server **chưa có kết luận tin cậy về token** vì timeout, lỗi DNS/TLS, HTTP 429/5xx, lỗi credentials introspection, hoặc response không đúng giao thức.
3. **Chính sách từ chối:** Token đã được chấp nhận, nhưng caller thiếu scope, role, tenant membership, ownership hoặc quan hệ cần thiết với một tài nguyên nghiệp vụ.

**Cả ba đều có thể khiến API không cấp quyền, nhưng chúng có nguyên nhân, phản hồi HTTP, hành vi retry, cache và cách điều tra khác nhau.** Một lỗi HTTP **401 từ introspection endpoint** có thể báo **client secret của Resource Server dùng để gọi AS bị từ chối**, chứ **không** có nghĩa access token do người dùng gửi bị thu hồi.

Bài học này phân tích đường đi của `ReactiveOpaqueTokenIntrospector`, **RFC 7662**, **RFC 6750**, cơ chế **fail closed**, phân loại lỗi bằng Reactor, thiết kế chính sách 401/403/5xx, giới hạn retry/cache và kiểm thử với **StepVerifier** cùng **WebTestClient**.

## 1. Hai HTTP request khác nhau: client → API và API → Authorization Server

OAuth2 Client gọi API:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer opaque-token-example
~~~

Để xác minh token, Resource Server gọi introspection endpoint bằng **credentials của chính Resource Server**:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <resource-server-introspection-credentials>
Content-Type: application/x-www-form-urlencoded

token=<opaque-token>
~~~

Các chuỗi token/credentials trong ví dụ chỉ là dữ liệu giả. Secret thật phải được bảo vệ, không xuất hiện trong source code, log hoặc tài liệu công khai.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant RS as WebFlux Resource Server
    participant AS as Authorization Server
    C->>RS: GET /api/orders/123 + Bearer T
    RS->>AS: POST /introspect với T + credentials của RS
    alt AS trả kết quả hợp lệ: active=false
        AS-->>RS: HTTP 200, {"active":false}
        RS-->>C: Thường 401 + Bearer invalid_token
    else AS trả kết quả hợp lệ: active=true
        AS-->>RS: HTTP 200, active, scope, aud, sub...
        RS->>RS: Kiểm tra token profile và authorities
        alt Thiếu quyền chức năng hoặc quyền bản ghi
            RS-->>C: Thường 403 hoặc 404 theo policy
        else Đủ quyền
            RS-->>C: Phản hồi nghiệp vụ
        end
    else Lỗi network, TLS, HTTP 429/5xx, schema...
        AS--xRS: Không có kết luận tin cậy
        RS->>RS: Fail closed, không tạo Authentication hợp lệ
        RS-->>C: Error response theo chính sách phụ thuộc
    end
~~~

**Tách biệt hai mã status:**

- **AS → RS:** HTTP status từ introspection endpoint phản ánh giao thức/khả năng phục vụ/quyền gọi endpoint của Resource Server.
- **RS → OAuth Client:** status API phản ánh authentication, authorization và failure policy đối với request ban đầu.

HTTP 401 ở **đường AS → RS** thường cần kiểm tra client credentials, mTLS hoặc quyền truy cập introspection; nó **không thể được diễn giải trực tiếp** như `invalid_token` ở đường **RS → client**.

## 2. Luồng xử lý của ReactiveOpaqueTokenIntrospector

Với WebFlux, Spring Security sử dụng `SecurityWebFilterChain`, `ServerHttpSecurity` và các thành phần xác thực reactive.

~~~mermaid
flowchart TD
    A["Authorization: Bearer T"] --> B["SecurityWebFilterChain"]
    B --> C["Bearer Authentication WebFilter"]
    C --> D["ReactiveAuthenticationManager"]
    D --> E["ReactiveOpaqueTokenIntrospector"]
    E --> F{"Kết quả introspection?"}
    F -- "Principal hợp lệ" --> G["BearerTokenAuthentication"]
    G --> H["SecurityContext trong Reactor Context"]
    H --> I["AuthorizationWebFilter / method security"]
    I --> J{"Có quyền?"}
    J -- "Không" --> K["403/404 theo policy"]
    J -- "Có" --> L["Controller / Service"]
    F -- "Token inactive" --> M["Authentication failure, thường 401"]
    F -- "Lỗi remote" --> N["Không tạo Authentication; failure policy"]
~~~

| Thành phần | Nhiệm vụ |
| --- | --- |
| `ReactiveOpaqueTokenIntrospector` | Trả principal hoặc error signal từ việc xác minh token |
| Remote introspection implementation | Gọi AS qua HTTP/TLS và xử lý response theo hợp đồng |
| `OAuth2AuthenticatedPrincipal` | Chứa `attributes`, `name` và `authorities` sau introspection |
| `BearerTokenAuthentication` | Authentication thường dùng khi opaque token được chấp nhận |
| `ReactiveSecurityContextHolder` | Đọc SecurityContext từ Reactor subscriber Context |
| `AuthorizationWebFilter` | Áp dụng HTTP rules như `authenticated()`, `hasAuthority(...)` |
| Reactive method security | Kiểm tra quyền ở service khi được cấu hình |
| Authentication entry point/failure handler | Tạo phản hồi khi authentication không đạt |
| Access-denied handler | Xử lý thiếu quyền sau authentication |

Interface reactive có hợp đồng dạng:

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

// Đối với một ReactiveOpaqueTokenIntrospector implementation:
Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
~~~

`Mono<OAuth2AuthenticatedPrincipal>` **thành công** mới cung cấp dữ liệu để authentication manager tạo Authentication. Một **`Mono.error(...)`** thể hiện quá trình không chấp nhận token hoặc không thể xác minh; không tự cấp quyền.

**Không dùng `Mono.empty()` tùy tiện để biểu diễn token inactive.** Nó không giống error signal tường minh; provider/handler có thể có hành vi khác nhau. Cần giữ đúng contract của implementation và lớp chuyển lỗi.

## 3. RFC 7662: active=false có ngữ nghĩa cụ thể

**OAuth 2.0 Token Introspection – RFC 7662** cho phép AS trả metadata về token.

Response thành công:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "client_id": "orders-web",
  "aud": ["orders-api"],
  "scope": "orders.read orders.export",
  "token_type": "Bearer",
  "exp": 1893456000
}
~~~

Response token không hoạt động:

~~~json
{
  "active": false
}
~~~

Một response hợp lệ với `active: false` có thể đại diện cho token hết hạn, bị thu hồi, không được AS công nhận hoặc một trường hợp AS không công bố thêm thông tin theo chính sách. API **không được đoán chính xác nguyên nhân** nếu AS chỉ cung cấp boolean.

### Phân biệt inactive với thiếu metadata

| Kết quả từ AS | Diễn giải |
| --- | --- |
| HTTP 200 + `active: false` | Token không hoạt động theo kết luận introspection |
| HTTP 200 + `active: true`, đúng contract | Có thể tiếp tục validation và mapping principal |
| HTTP 200 nhưng không có `active` | Response không đủ schema, **không được tự coi active** |
| HTTP 200 nhưng `active: "true"` string | Sai kiểu theo schema, phải fail closed |
| HTTP 200 + `active:true` nhưng `aud` sai | Token/profile không được API chấp nhận |
| HTTP 200 + `active:true`, `scope` thiếu | Không tự cấp authorities; authorization có thể từ chối |

Các trường khác thường phụ thuộc issuer:

- `sub` mô tả subject nếu có; không tự mặc định mọi token đại diện cho một human user.
- `client_id` mô tả OAuth client, không tự là owner của bản ghi.
- `scope` mang quyền chức năng đã cấp.
- `exp` có thể dùng kiểm tra thời hạn/cache; NumericDate thường là **epoch seconds**, nhưng kiểu Java trong principal có thể đã được introspector chuyển đổi.
- `aud` kiểm tra token có dành cho API này không.
- `tenant_id` là một claim tùy chỉnh; không thay thế membership/ownership hiện hành.

**`active:true` không tự đủ để được đọc mọi tài nguyên**. Phải kiểm tra issuer/audience/token purpose theo profile và tiếp tục authorization.

## 4. Lỗi từ xa: chưa có kết luận về token

Những failure trong lần gọi introspection cần được hiểu theo **vị trí xảy ra**:

| Remote signal | Nguyên nhân thường gặp | Không được suy diễn |
| --- | --- | --- |
| DNS hoặc TCP connect failure | Không tìm thấy host/kết nối AS | Token đã revoke |
| TLS handshake/certificate failure | Không thiết lập được kết nối tin cậy | Token của người dùng sai chữ ký |
| Read timeout | Chưa nhận được kết quả đúng hạn | `active:false` |
| HTTP 500/502/503/504 | AS hoặc proxy/gateway bị lỗi | Token hết hạn |
| HTTP 429 | RS introspection caller bị rate limited | Token thiếu scope |
| HTTP 401/403 từ AS | Client authentication/authorization của RS bị từ chối | Token của OAuth client invalid |
| HTTP 400 từ AS | Request introspection malformed hoặc không đạt protocol | JWT sai signature |
| HTTP 200 với JSON lỗi định dạng | Remote protocol/schema sai | Có thể cho token qua |
| HTTP 200 với `active` sai kiểu | Chưa có kết luận hợp lệ theo contract | Token chắc chắn active |

**Không gộp HTTP 401 từ introspection endpoint với HTTP 401 do Resource Server trả về.**

Ví dụ AS từ chối thông tin xác thực của Resource Server:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="introspection"
~~~

Lỗi này có thể cần xoay lại client secret, kiểm tra mTLS, quyền gọi endpoint hoặc cấu hình issuer. Nó không chứng minh điều gì về trạng thái của token T.

Ví dụ AS bị sự cố:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 10
~~~

Nếu chưa có response token hợp lệ, Resource Server **không thể xây Authentication đáng tin** từ lời gọi này. Nó phải từ chối truy cập tài nguyên bảo vệ, nhưng cần phân loại rõ sự cố dependency để vận hành và lựa chọn client-facing response.

## 5. Fail closed: quyết định bảo mật khác với mã HTTP

**Fail closed** nghĩa là khi cần authentication nhưng không xác minh được token theo chính sách, **không cấp quyền truy cập**.

~~~text
Không có kết quả introspection đáng tin
              |
              v
Không có Authentication đã được xác minh
              |
              v
Không được xem/sửa tài nguyên bảo vệ
              |
              v
HTTP response theo failure policy
~~~

Hai bước độc lập:

1. **Security decision:** Không cấp Authentication nếu token inactive, profile sai, hoặc dependency không thể xác minh.
2. **Error representation:** Trả response gì cho caller? Một token thực sự invalid có thể nhận **401 `invalid_token`**; một outage có thể nhận **503** nếu ứng dụng đã chủ động cấu hình điều đó.

Fail closed **không buộc** mọi lỗi remote phải mang `invalid_token`. Nếu API nói “token invalid” khi AS timeout, client có thể xóa token, đăng xuất người dùng hoặc chạy refresh vòng lặp, làm outage nặng hơn.

### Hai anti-pattern phải tránh

~~~java
// SAI: hạ lỗi introspection thành một principal được chấp nhận.
return delegate.introspect(token)
    .onErrorResume(error -> Mono.just(guestPrincipal));
~~~

~~~java
// SAI: nuốt lỗi thành empty mà không có hợp đồng rõ ràng.
return delegate.introspect(token)
    .onErrorResume(error -> Mono.empty());
~~~

Nhánh thứ nhất có thể **fail open** nếu principal có authority; nhánh thứ hai có thể làm authentication flow rơi vào trạng thái mơ hồ. Tốt hơn là **giữ error signal có loại rõ ràng** để các lớp bảo mật xử lý.

## 6. 401, 403 và 5xx: chính sách phản hồi cần phân biệt

| Trường hợp | Có kết luận token hợp lệ? | Security outcome | Response thông dụng hoặc mục tiêu policy |
| --- | --- | --- | --- |
| Không gửi Bearer tới endpoint bảo vệ | Không có token | Không xác thực | **401** + Bearer challenge |
| AS trả `active:false` | Không | Authentication failure | Thường **401** + `invalid_token` |
| Token sai audience/issuer/profile | Không được API chấp nhận | Authentication failure | Thường **401** |
| AS timeout/429/5xx | **Chưa biết** | Không cấp Authentication | Có thể **5xx** theo custom failure policy |
| Credentials introspection sai | **Chưa biết** | Không cấp Authentication | Có thể **5xx**, báo động vận hành |
| Response schema từ AS sai | **Chưa biết** | Không cấp Authentication | Có thể **5xx**, báo protocol/dependency error |
| Token hợp lệ, thiếu scope | Có | Authorization denied | Thường **403**, có thể `insufficient_scope` |
| Token hợp lệ, tenant/owner không hợp lệ | Có | Business authorization denied | **403 hoặc 404** theo chính sách |
| Token hợp lệ, đủ quyền | Có | Cho tiếp tục | Response nghiệp vụ |

**Bảng trên không mô tả một HTTP status được Spring Security bảo đảm cho mọi remote exception**. Một implementation có thể wrap remote exception thành `AuthenticationException`, dẫn tới response khác tùy handler. Để bảo đảm 503 cho upstream outage, ứng dụng cần tạo **phân loại lỗi và HTTP mapping tại boundary thực sự giữ được thông tin nguyên nhân**, sau đó kiểm thử end-to-end.

### 401 và 403 khác nhau về ý nghĩa OAuth 2.0

Theo **RFC 6750**, Resource Server có thể trả:

**Không gửi token:**

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

**Đã gửi token nhưng token không được chấp nhận:**

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

**Token được chấp nhận nhưng thiếu scope:**

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Header có thể thêm `realm`, `error_description` hoặc `scope`. Thứ tự tham số và body phụ thuộc cấu hình.

**Không phải mọi 401 đều bắt buộc chứa `invalid_token`.** Một request không gửi credentials có thể nhận Bearer challenge **không có error code**. Không được ghi raw access token, client secret hoặc private metadata vào `error_description`.

### 503 là ví dụ về policy cho dependency outage

Nếu API tự thiết kế contract này, một response có thể là:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Retry-After: 5

{
  "type": "https://api.example.com/problems/authentication-dependency",
  "title": "Authentication temporarily unavailable",
  "status": 503,
  "detail": "Please retry later"
}
~~~

Đây là **custom response minh họa, không phải Spring Security default**. Nếu client tự retry, cần xét thao tác có idempotent không; không tự động lặp một POST tạo thanh toán chỉ vì gặp lỗi dependency.

## 7. Khi nào một exception có nghĩa token inactive?

Các kiểu lỗi có thể gặp trong Spring Security và WebClient:

- `BadOpaqueTokenException`: được sử dụng để biểu diễn opaque token không được chấp nhận.
- `OAuth2IntrospectionException`: lỗi trong quy trình introspection, bao gồm các tình huống phụ thuộc implementation.
- `OAuth2AuthenticationException`: lỗi authentication OAuth2 có dữ liệu `OAuth2Error`.
- `AccessDeniedException`: quyền không đủ ở authorization, **không chứng minh token inactive**.
- WebClient/transport exceptions: lỗi HTTP, connect, TLS hoặc timeout; có thể bị framework wrap.

Không nên phân loại kiểu:

~~~java
// KHÔNG ĐÚNG: mọi runtime error đều là token invalid.
if (error instanceof RuntimeException) {
    return "invalid_token";
}
~~~

Nếu muốn taxonomy đáng tin, nên gắn **loại lỗi chuyên biệt ngay tại boundary có đủ bằng chứng**:

~~~java
enum IntrospectionFailureKind {
    INACTIVE_TOKEN,
    INVALID_TOKEN_PROFILE,
    UPSTREAM_UNAVAILABLE,
    UPSTREAM_AUTHENTICATION_FAILED,
    BAD_INTROSPECTION_RESPONSE,
    UNEXPECTED_FAILURE
}
~~~

Đây là **enum do ứng dụng định nghĩa**, không phải Spring Security API. Một error có thể bị wrap qua nhiều lớp, nên logic phân loại cần quan tâm **cause chain** và contract của implementation đang dùng, không dựa vào chuỗi message.

**Chú ý:** một `OAuth2IntrospectionException` chung không đủ để kết luận mọi trường hợp đều là `active:false`. Ngược lại, nếu introspection thực sự trả `active:false`, hãy giữ một tín hiệu token invalid riêng khi mapping.

## 8. Cấu hình cơ bản cho Reactive Opaque Token Resource Server

Dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Phải dùng endpoint tin cậy qua TLS và lưu credentials bằng secret manager/biến môi trường được bảo vệ.

Security config:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class OpaqueResourceServerSecurity {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

Ví dụ giả định API **stateless chỉ dùng Bearer token** và không dùng cookie authentication tự động từ browser. Với session/cookie, phải đánh giá CSRF thay vì vô hiệu hóa toàn cục.

**Khi sử dụng Spring WebFlux, cần `ReactiveOpaqueTokenIntrospector`**, không lấy một `OpaqueTokenIntrospector` Servlet synchronous rồi coi nó tự thành non-blocking. Cách cấu hình remote introspector, timeout và HTTP client phụ thuộc version Spring Security; cần dùng builder/implementation tương thích với dependency hiện tại.

### permitAll không tự bỏ qua token đã gửi

Nếu `/public/info` nằm trong cùng reactive security chain đã bật Resource Server:

~~~http
GET /public/info HTTP/1.1
Authorization: Bearer inactive-token
~~~

thì filter **vẫn có thể introspect token và trả 401 trước `permitAll()`**. Nếu route public phải bỏ qua mọi Bearer token do client gửi, cần thiết kế security chain riêng hoặc cơ chế token converter rõ ràng.

## 9. Custom policy: active nhưng audience sai cũng phải từ chối

Giả sử AS xác nhận:

~~~json
{
  "active": true,
  "sub": "user-42",
  "scope": "orders.read",
  "aud": ["payments-api"]
}
~~~

Token này có thể active, nhưng **không dành cho Orders API**. Một decorator có thể kiểm tra `aud` sau khi delegate introspector đã xác minh:

~~~java
import java.util.Collection;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class AudienceCheckingIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;

    public AudienceCheckingIntrospector(
            ReactiveOpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token)
            .flatMap(principal -> {
                Object aud = principal.getAttribute("aud");
                boolean allowed =
                    "orders-api".equals(aud)
                    || (aud instanceof Collection<?> values
                        && values.contains("orders-api"));

                if (!allowed) {
                    return Mono.error(new BadOpaqueTokenException(
                        "Token audience is not accepted"));
                }
                return Mono.just(principal);
            });
    }
}
~~~

Ở đây:

1. Delegate xử lý token và trả principal **sau khi introspection thành công**.
2. Policy kiểm tra audience theo hợp đồng.
3. Sai audience trở thành **token acceptance failure**, không phải lỗi từ xa.
4. `aud` thiếu bị từ chối nếu Orders API bắt buộc audience.
5. Các ràng buộc khác (issuer/client binding, exp, token purpose/profile) vẫn phải được kiểm tra tương ứng.

Đây là kiểm tra ở **authentication boundary**, nên hợp lý để từ chối như token không dành cho API. Khác với việc user có token hợp lệ nhưng không sở hữu order 123: tình huống sau là **authorization trên đối tượng**, không phải token inactive.

### Gắn introspector custom vào SecurityWebFilterChain

Nếu có sẵn một bean `ReactiveOpaqueTokenIntrospector` đã được bọc policy, có thể dùng:

~~~java
@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http,
        ReactiveOpaqueTokenIntrospector policyIntrospector) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/**").permitAll()
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.opaqueToken(opaque ->
                opaque.introspector(policyIntrospector)))
        .build();
}
~~~

Đây là **mẫu wiring**, không tự khởi tạo remote introspector. Ứng dụng phải tạo bean policy từ một remote introspector tin cậy và cấu hình phù hợp version; nếu có nhiều bean cùng interface cần qualifier. Không tạo bean tự inject chính nó làm phát sinh circular dependency.

## 10. Timeout bằng Reactor: phát lỗi riêng, không cấp principal

Các toán tử Reactor như `timeout(...)` và `onErrorMap(...)` cho phép giữ loại lỗi:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class TimedIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final Duration deadline;

    public TimedIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            Duration deadline) {
        this.delegate = delegate;
        this.deadline = deadline;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token)
            .timeout(deadline)
            .onErrorMap(TimeoutException.class,
                cause -> new IntrospectionUpstreamUnavailableException(
                    "Introspection deadline exceeded", cause));
    }
}

final class IntrospectionUpstreamUnavailableException
        extends RuntimeException {

    IntrospectionUpstreamUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

**Đoạn này chỉ đánh dấu timeout, không tự làm Spring Security trả 503.** Provider/failure handler có thể wrap exception hoặc chọn status khác. Muốn bảo đảm remote outage → 503, cần đường chuyển lỗi được thiết kế ở authentication boundary và test HTTP thật.

Các điều kiện quan trọng:

- `deadline` phải dương và phù hợp ngân sách độ trễ của API.
- Connect/read timeout của HTTP client có thể ném kiểu exception khác `TimeoutException` do operator Reactor.
- Đừng bắt mọi `Exception` rồi đổi thành `BadOpaqueTokenException`, vì như vậy network outage bị báo sai là invalid token.
- `timeout` cắt thời gian chờ; không bảo đảm Authorization Server dừng xử lý request tức thì.
- Hạn chế số kết nối/request đang chờ, tránh làm cạn event-loop/connection pool.

**Không dùng `block()` trong introspector reactive:**

~~~java
// KHÔNG NÊN:
OAuth2AuthenticatedPrincipal principal =
    delegate.introspect(token).block();
return Mono.just(principal);
~~~

Đó là blocking và tạo subscription riêng. Nên trả publisher trực tiếp để Spring Security quản lý subscription.

## 11. Retry: chỉ dành cho lỗi thực sự có khả năng hồi phục

| Tình huống | Retry ngay? | Lý do |
| --- | --- | --- |
| Token inactive theo response hợp lệ | **Không** | AS đã trả kết luận |
| Token sai audience/issuer/profile | **Không** | Policy không tự đổi khi retry |
| HTTP 401/403 do introspection client auth | Thường **không** | Cần sửa credential/quyền |
| HTTP 429 | Có thể theo Retry-After và budget | Tránh retry storm |
| HTTP 502/503/504 | Có thể giới hạn | Lỗi tạm thời có thể hồi phục |
| Connect/read timeout | Có thể giới hạn | Nhưng vẫn tốn tải và thời gian |
| Response sai schema | Không nên retry vô hạn | Cần xác định lỗi protocol |

Ví dụ chỉ retry error **đã được phân loại** là upstream unavailable:

~~~java
import java.time.Duration;
import reactor.util.retry.Retry;

return delegate.introspect(token)
    .retryWhen(Retry.backoff(1, Duration.ofMillis(100))
        .filter(error ->
            error instanceof IntrospectionUpstreamUnavailableException));
~~~

Đây là **đoạn minh họa bên trong phương thức trả Mono**, không phải nguyên một class Java. Nó giả định adapter đã thực sự ném `IntrospectionUpstreamUnavailableException` khi có lỗi transient; không có nghĩa mọi lỗi mạng đều được auto-convert.

Retry phải có **deadline tổng**, giới hạn attempt và jitter; không retry inactive token; không để nhiều tầng API/gateway/client cùng retry vô hạn khiến AS quá tải. Dù introspection thường là thao tác đọc trạng thái, cần kiểm tra contract idempotency trước khi retry một HTTP POST.

### Circuit breaker và bulkhead

Khi AS outage, circuit breaker có thể hạn chế lưu lượng tới dependency, và bulkhead giới hạn số request chờ. Nhưng trạng thái circuit breaker mở **không phải bằng chứng token inactive**. Request cần xác thực vẫn phải **fail closed**, với phản hồi hạ tầng được định nghĩa rõ.

## 12. Cache, exp và cửa sổ chậm thu hồi

Positive caching có thể giảm độ trễ introspection nhưng tạo **revocation lag**:

~~~text
t0:      AS trả active=true cho token T, RS cache 30s
t0+5s:   AS revoke T
t0+10s:  RS cache hit, có thể vẫn chấp nhận T
t0+30s:  cache hết hạn
t0+31s:  RS introspect lại, thấy active=false
~~~

Với `exp` đáng tin, giới hạn reuse:

~~~text
reuseUntil = min(timeOfVerification + maxCacheTtl,
                 tokenExpiresAt - safetyMargin)
~~~

**TTL cache không thay `exp` và không tự đảm bảo revoke tức thì.** Nếu không biết `exp` hoặc cần thu hồi gần thời gian thực, có thể không cache theo policy.

### Stale-on-error là đánh đổi bảo mật

Anti-pattern:

~~~java
// KHÔNG: lỗi AS thì sử dụng cached principal đã quá hạn.
return remote.introspect(token)
    .onErrorResume(error -> Mono.just(expiredCachedPrincipal));
~~~

Token có thể đã bị revoke hoặc giảm scope; dùng entry hết TTL thay đổi chính sách xác thực. Nếu hệ thống quyết định stale-on-error, cần phê duyệt rủi ro, tuổi stale tuyệt đối, không vượt `exp`, phân biệt endpoint nhạy cảm và có audit. **Mặc định thận trọng là không dùng stale expired result.**

### Negative caching cũng phải phân loại

Không nên:

~~~text
Timeout AS -> lưu "token invalid" trong cache 10 phút
~~~

Lỗi tạm thời từ xa không phải token inactive. Cache negative, nếu sử dụng, phải chỉ dành cho **kết luận token không hoạt động đáng tin**, TTL riêng ngắn, giới hạn dung lượng và không cache lỗi network như lỗi credentials.

Cache key là dữ liệu bảo mật: tránh log raw token; cân nhắc HMAC digest với secret riêng và phân vùng issuer/audience/policy, bảo vệ cả cached principal/authorities.

## 13. Token được chấp nhận không có nghĩa đủ quyền

Giả sử introspection trả:

~~~json
{
  "active": true,
  "sub": "user-42",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "tenant_id": "t-7"
}
~~~

Resource Server có thể tạo Authentication với authority `SCOPE_orders.read`. Nhưng điều đó **không** tự xác nhận user 42 được xem order 123.

~~~text
Introspection:
  Token active, profile đúng
          |
          v
HTTP authorization:
  Có SCOPE_orders.read?
          |
          v
Business object authorization:
  Actor còn membership ở tenant?
  Order có thuộc tenant được yêu cầu?
  Actor là owner/manager hoặc có share READ còn hạn?
          |
          v
Truy vấn được scope đúng và chỉ trả DTO được phép
~~~

| Tầng | Lỗi ví dụ | Phản hồi thường gặp |
| --- | --- | --- |
| Authentication | `active=false` | 401 |
| Token profile | `aud=payments-api` | 401/invalid token policy |
| Function authorization | Thiếu `SCOPE_orders.read` | 403 |
| Object authorization | Order thuộc tenant khác | 403 hoặc 404 |
| Business state | Không cho sửa order đã chốt | 403 hoặc response nghiệp vụ phù hợp |

**Không biến thiếu scope thành inactive token.** Nếu token còn hợp lệ nhưng thiếu quyền chức năng, trả `invalid_token` có thể khiến client refresh/login lại mà vẫn không có scope cần thiết.

### Scope khác quyền của bản ghi

Một token có `SCOPE_orders.read` cho phép dùng **chức năng đọc order** theo chính sách, nhưng service phải kiểm tra tenant, owner, sharing, assignment và parent-child relationship. Một số quyết định có thể thay đổi **khi access token vẫn còn hạn**; nếu cần thu hồi membership nhanh, phải xem nguồn dữ liệu hiện hành hoặc cache/invalidation riêng.

## 14. Reactor Context và lỗi trước controller

Sau khi introspection **thành công**, Resource Server có thể đặt `BearerTokenAuthentication` trong Reactor Context.

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import reactor.core.publisher.Mono;

Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .ofType(BearerTokenAuthentication.class)
        .map(BearerTokenAuthentication::getName);
}
~~~

Khi token inactive hoặc remote introspection thất bại, HTTP request có thể bị chặn **trước khi controller/service được chạy**. Vì vậy controller không phải nơi thích hợp để bắt mọi lỗi introspection.

Trong WebFlux, `ReactiveSecurityContextHolder` lấy SecurityContext theo **Reactor subscriber**, khác với `SecurityContextHolder` kiểu ThreadLocal. Không gọi `block()` hoặc tự `subscribe()` để tìm principal bên trong một reactive request pipeline.

### Vì sao ControllerAdvice chưa chắc xử lý được?

Lỗi authentication thường phát sinh trong **WebFilter chain** và được authentication entry point/failure handler xử lý. Một `@RestControllerAdvice` hoặc exception handler dành cho controller **không mặc định** bắt mọi exception xuất hiện trước handler. Muốn chuẩn hóa response 401/503, phải đặt mapping ở boundary đúng trong security/reactive HTTP error handling.

## 15. Thiết kế phân loại và HTTP mapping cho lỗi remote

Một failure taxonomy ứng dụng có thể gồm:

~~~java
enum IntrospectionFailureKind {
    INACTIVE_TOKEN,
    INVALID_TOKEN_PROFILE,
    UPSTREAM_UNAVAILABLE,
    UPSTREAM_AUTHENTICATION_FAILED,
    BAD_INTROSPECTION_RESPONSE,
    UNEXPECTED_FAILURE
}
~~~

Đây là enum **do ứng dụng định nghĩa**. Một implementation thật có thể dùng HTTP client adapter gắn loại lỗi khi thấy status/cause, rồi truyền tín hiệu qua authentication boundary.

Những nơi cần hiểu rõ trong WebFlux:

- `ServerAuthenticationEntryPoint` xử lý các tình huống bắt đầu/challenge authentication.
- Authentication failure handling của WebFilter xử lý lỗi xác thực.
- `ServerAccessDeniedHandler` xử lý denial sau authentication.
- Global reactive error handling có thể xử lý lỗi hạ tầng **nếu lỗi được truyền đến đó**.

**Không được giả định:** ném một `RuntimeException` từ introspector là Spring Security tự trả 503. Provider có thể wrap thành `AuthenticationException` và entry point có thể trả 401. Vì vậy muốn remote outage → 503, cần **giữ dấu hiệu remote error ở đúng boundary**, chọn handler phù hợp và test response HTTP thực tế.

Quy tắc thiết kế:

1. Chỉ dùng `invalid_token` khi có căn cứ token không được chấp nhận.
2. Không gọi outage là `insufficient_scope`, vì chưa xác minh xong token.
3. Không biến một lỗi credentials của RS thành lỗi user/password của người dùng cuối.
4. Không để 5xx dependency làm cho API cho request đi tiếp.
5. Không công bố internal hostnames, introspection client secret, raw access token hoặc stack trace.

## 16. Log, metric và cảnh báo theo nguyên nhân

| Metric/tín hiệu | Ý nghĩa |
| --- | --- |
| `introspection_active_total` | Các kết quả token active được chấp nhận |
| `introspection_inactive_total` | Token không hoạt động theo kết luận hợp lệ |
| `introspection_upstream_failure_total` | Timeout, TLS, 429/5xx, credential hoặc schema errors |
| `introspection_latency_seconds` | P50/P95/P99 của lời gọi AS |
| `authentication_rejected_total` | Request không tạo được Authentication |
| `authorization_denied_total` | Thiếu scope hoặc object policy sau authentication |
| `introspection_cache_hit_total` | Tỷ lệ tái sử dụng; theo dõi revocation lag |

Tên metric là **ví dụ thiết kế**, không phải metric tự có trong mọi bản Spring Security.

Một số quy tắc an toàn:

- Ghi request ID, loại failure, endpoint đã chuẩn hóa, alias issuer và thời điểm.
- Không ghi raw Bearer token, Authorization header hoặc client secret.
- Không đưa token/digest của token vào label metrics, tránh cardinality cao và rủi ro lộ dữ liệu.
- Không đưa toàn bộ introspection response vào log nếu có PII hoặc quyền nội bộ.
- Phân biệt 401 do token inactive với 401 từ AS khi RS không chứng thực được chính nó.

Những tín hiệu chẩn đoán thường gặp:

~~~text
API 401 tăng + active=false tăng:
  Kiểm tra token expired/revoked/không được issuer công nhận.

HTTP AS 401/403 tăng:
  Kiểm tra introspection client credentials và quyền truy cập AS.

Timeout/429/5xx AS tăng:
  Kiểm tra AS availability, network, retry storm, rate limit.

API 403 tăng nhưng introspection active:
  Kiểm tra scope mapping, role, method security, owner/tenant policy.
~~~

## 17. StepVerifier: kiểm tra ba nhánh error signal

Trong unit test, có thể tạo fake `ReactiveOpaqueTokenIntrospector`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeoutException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

ReactiveOpaqueTokenIntrospector fakeRemote = token -> {
    if ("inactive".equals(token)) {
        return Mono.error(new BadOpaqueTokenException("Token inactive"));
    }
    if ("timeout".equals(token)) {
        return Mono.error(new TimeoutException("Remote timeout"));
    }

    OAuth2AuthenticatedPrincipal principal =
        new DefaultOAuth2AuthenticatedPrincipal(
            "user-42",
            Map.of("sub", "user-42", "aud", List.of("orders-api")),
            List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
        );
    return Mono.just(principal);
};
~~~

Với `TimedIntrospector` ở mục 10:

~~~java
import java.time.Duration;
import reactor.test.StepVerifier;

TimedIntrospector timed = new TimedIntrospector(
    fakeRemote, Duration.ofSeconds(2));

StepVerifier.create(timed.introspect("inactive"))
    .expectError(BadOpaqueTokenException.class)
    .verify();

StepVerifier.create(timed.introspect("timeout"))
    .expectError(IntrospectionUpstreamUnavailableException.class)
    .verify();

StepVerifier.create(timed.introspect("active"))
    .assertNext(principal ->
        org.junit.jupiter.api.Assertions.assertEquals(
            "user-42", principal.getName()))
    .verifyComplete();
~~~

Đây là **các đoạn test minh họa với fake**, không phải một class JUnit đầy đủ. Mục tiêu là bảo đảm **token inactive và remote timeout phát hai tín hiệu khác nhau**. Không có HTTP thật, TLS hay AS credentials trong unit test này.

### Virtual time và timeout thực

Khi test `timeout(Duration)` với publisher chậm:

~~~java
ReactiveOpaqueTokenIntrospector delayed = token ->
    Mono.delay(Duration.ofSeconds(10))
        .then(Mono.error(new RuntimeException("Unreachable")));
~~~

có thể dùng `StepVerifier.withVirtualTime(...)` nếu publisher được tạo đúng thời điểm và các schedulers phù hợp được điều khiển bởi virtual time. Đây là **Reactor operator timeout**, không chứng minh connect/read timeout của HTTP client thật có cùng exception type.

## 18. WebTestClient: HTTP response từ WebFilter chain thật

Để kiểm tra đường đi Bearer, nên gửi header HTTP thực và giữ **SecurityWebFilterChain** thay vì chỉ dùng helper gắn Authentication mô phỏng.

Giả sử app có GET `/api/orders/123` trả 200 khi được phép, và WebFlux security chain yêu cầu `SCOPE_orders.read`.

~~~java
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveIntrospectionResponseTest {

    @Autowired WebTestClient client;

    @MockitoBean ReactiveOpaqueTokenIntrospector introspector;

    @Test
    void missingTokenReturns401() {
        client.get().uri("/api/orders/123")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, "Bearer.*");
    }

    @Test
    void inactiveTokenReturns401() {
        when(introspector.introspect("inactive-token"))
            .thenReturn(Mono.error(
                new BadOpaqueTokenException("Token inactive")));

        client.get().uri("/api/orders/123")
            .headers(h -> h.setBearerAuth("inactive-token"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void activeButMissingScopeReturns403() {
        when(introspector.introspect("only-profile"))
            .thenReturn(Mono.just(principal("profile.read")));

        client.get().uri("/api/orders/123")
            .headers(h -> h.setBearerAuth("only-profile"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void activeAndEnoughScopeReachesController() {
        when(introspector.introspect("has-orders-read"))
            .thenReturn(Mono.just(principal("orders.read")));

        client.get().uri("/api/orders/123")
            .headers(h -> h.setBearerAuth("has-orders-read"))
            .exchange()
            .expectStatus().isOk();
    }

    private static DefaultOAuth2AuthenticatedPrincipal principal(String scope) {
        return new DefaultOAuth2AuthenticatedPrincipal(
            "user-42",
            Map.of("sub", "user-42", "scope", scope),
            List.of(new SimpleGrantedAuthority("SCOPE_" + scope))
        );
    }
}
~~~

Test này giữ **filter/provider/authorization thật**, nhưng mock introspector. `principal(...)` dựng authorities trực tiếp, nên test **không chứng minh scope parsing từ response introspection thật**.

**Điều kiện:** app test phải dùng opaque Resource Server reactive, có endpoint fixture đúng. `@MockitoBean` được hỗ trợ bởi các dòng Spring Test mới (ví dụ Spring Framework 6.2+); các dự án cũ hơn có thể dùng `@MockBean` của Spring Boot khi phù hợp.

### Test remote outage không được tự đoán status

Ví dụ mock:

~~~java
when(introspector.introspect("upstream-timeout"))
    .thenReturn(Mono.error(
        new IntrospectionUpstreamUnavailableException(
            "Timeout", new TimeoutException("Deadline exceeded"))));
~~~

Test này **chưa tự bảo đảm response 503**. Để test contract đó:

1. Xác nhận introspector phát typed remote error, không trả principal.
2. Cấu hình một authentication/error mapping giữ được phân loại lỗi khi qua provider/filter.
3. Chọn client-facing 503/response body phù hợp.
4. Gửi Bearer request qua WebTestClient và assert status + body/header + controller không được gọi.

Chỉ khi hệ thống đã cấu hình 503, mới assert:

~~~java
client.get().uri("/api/orders/123")
    .headers(h -> h.setBearerAuth("upstream-timeout"))
    .exchange()
    .expectStatus().isEqualTo(503);
~~~

**Đoạn test 503 không thể mặc định pass chỉ với cấu hình Resource Server cơ bản ở mục 8.** Chúng ta không đánh đồng failure classification mong muốn với default runtime behavior.

## 19. HTTP stub kiểm tra đúng giao thức introspection

Một test với mock introspector **không chứng minh**:

- Remote client gửi đúng `POST` form body `token` và Basic/mTLS client credentials.
- TLS certificate được xác minh.
- HTTP 401/403 từ AS được phân loại khác với `active:false`.
- HTTP 429/5xx và timeout được phân loại, giới hạn retry.
- JSON `active:false` được remote implementation chuyển thành invalid-token signal.
- Response thiếu `active`/sai kiểu bị từ chối.
- Scope/audience/exp được chuẩn hóa và ánh xạ authorities đúng.

Cần test tích hợp dùng **HTTP stub introspection server** và giữ remote introspector thật:

| Stub AS trả về | Kỳ vọng |
| --- | --- |
| HTTP 200 + `{"active":true,"scope":"orders.read"}` | Principal/authority theo schema |
| HTTP 200 + `{"active":false}` | Từ chối token; thường 401 đối với client |
| HTTP 200 không có `active` | Không chấp nhận token, protocol failure |
| HTTP 200 JSON không hợp lệ | Không chấp nhận token |
| HTTP 401 từ AS | Lỗi introspection credentials/quyền; không kết luận token inactive |
| HTTP 429 | Chặn cấp quyền; retry/rate limit policy theo budget |
| HTTP 500/503 | Fail closed; phản hồi dependency theo contract |
| Network timeout | Fail closed; deadline được kiểm tra |
| `active:true`, `aud` sai | Token profile từ chối |
| `active:true`, thiếu scope | Authentication thành công rồi authorization 403 |

Các test HTTP nên đo **request được gửi đến AS test server**, response RS trả cho OAuth client và không có side effect nghiệp vụ khi authentication thất bại.

### mockOpaqueToken() chỉ test một lớp khác

Spring Security Test có helper như `mockOpaqueToken()` cho WebTestClient ở phiên bản thích hợp. Helper tạo Authentication thử nghiệm để test HTTP/method authorization, nhưng **thường không gọi remote introspection**. Đừng dùng một test `mockOpaqueToken()` pass làm bằng chứng AS HTTP 401/timeout/active=false được xử lý đúng.

## 20. Những nhầm lẫn phổ biến

**“AS trả HTTP 401 nghĩa là token người dùng đã hết hạn.”** Không. Có thể chính credentials dùng để gọi introspection bị từ chối.

**“AS timeout thì cứ trả invalid_token cho frontend refresh.”** Chưa có bằng chứng token invalid; có thể làm client logout/refresh vòng lặp và tăng tải lúc outage.

**“active=true nghĩa là API phải trả 200.”** Không. Còn audience, scope, owner, tenant, trạng thái nghiệp vụ và authorization.

**“Thiếu scope cũng giống active=false.”** Không. Đó là lỗi authorization sau khi token được xác thực, thường 403.

**“HTTP 200 introspection thiếu active là thành công.”** Không. Phải kiểm tra response theo schema và fail closed.

**“Có thể retry active=false để AS đổi ý.”** Không nên. Đó là kết luận token inactive tại thời điểm AS trả lời.

**“onErrorResume(Exception, cachedPrincipal) giữ availability và an toàn.”** Không. Nếu principal chưa được xác minh hoặc cached result đã hết TTL, đó là fail open.

**“Positive cache không ảnh hưởng revoke.”** Không. Nó tạo revocation lag và phải bị giới hạn bởi TTL/exp.

**“Mọi 403 là insufficient_scope.”** Không. CSRF, method security, owner/tenant policy hoặc filter tùy chỉnh cũng có thể dẫn đến 403.

**“permitAll không bao giờ introspect token.”** Sai. Bearer token được gửi tới public route trong cùng Resource Server chain vẫn có thể bị xử lý.

**“WebFlux tự động chuyển mọi remote exception thành 503.”** Không có bảo đảm phổ quát. Phải thiết kế mapping và xác nhận qua test.

**“Có thể lấy principal từ SecurityContextHolder ThreadLocal như Servlet.”** Trong WebFlux, cần dùng Reactor security context hoặc tham số principal phù hợp.

## 21. Khung thiết kế cho hệ thống thật

Trước khi đưa reactive introspection vào production, hãy trả lời:

1. **Ai cấp và xác minh token?** Chỉ dùng introspection endpoint của issuer tin cậy, cấu hình TLS và client credentials.
2. **Response nào là bằng chứng token inactive?** Kết luận `active:false` hợp lệ khác remote failure.
3. **Profile bắt buộc gồm gì?** Audience, issuer, expiration, token purpose, client binding và claim schema.
4. **Lỗi remote được phân loại ở đâu?** HTTP client/adapter nơi còn thấy status và cause; giữ thông tin qua authentication boundary.
5. **Fail closed được bảo đảm thế nào?** Không tạo principal khi token chưa được xác minh.
6. **Status được trả ra là gì?** 401 invalid token, 403 insufficient permissions, 5xx dependency nếu policy yêu cầu và đã có handler.
7. **Timeout/retry được giới hạn thế nào?** Deadline tổng, connection pool, rate limit, jitter và circuit breaker.
8. **Có cache không?** Nếu có, positive TTL không vượt exp, đo revocation lag và không stale-on-error vô hạn.
9. **Các quyền nghiệp vụ kiểm tra ở đâu?** Scope ở HTTP/method; tenant/owner/share ở service/repository.
10. **Monitoring có phân biệt nguyên nhân?** Inactive, upstream unavailable, credentials issue và authorization denied cần tín hiệu riêng.
11. **Test có đi qua các boundary không?** StepVerifier, WebTestClient với Bearer header và HTTP stub introspection.
12. **Thông tin nhạy cảm có được bảo vệ không?** Không log raw token, client secret, introspection payload hoặc stack trace nội bộ.

**Điểm cần nhớ:** Trong WebFlux Resource Server, `active:false` là **kết luận token không hoạt động**, timeout/429/5xx/401 từ introspection endpoint thường là **vấn đề xác minh từ xa**, còn thiếu scope/owner/tenant là **authorization denial sau khi token đã được chấp nhận**. Cả ba đều có thể dẫn tới **không cho truy cập**, nhưng **không được đánh đồng nguyên nhân**. Thiết kế đúng phải **fail closed, bảo toàn phân loại lỗi, trả response đúng hợp đồng và kiểm thử đủ cả Reactor pipeline lẫn HTTP filter chain**.
