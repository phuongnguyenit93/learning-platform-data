# ReactiveJwtDecoder và NimbusReactiveJwtDecoder

Trong ứng dụng **Spring Security OAuth 2.0/OIDC Resource Server** sử dụng **Spring WebFlux**, access token thường được client gửi bằng HTTP header `Authorization: Bearer ...`. Nếu access token là **JWT** (JSON Web Token), Resource Server phải xác minh chữ ký JWS, chọn đúng khóa tin cậy, kiểm tra thời gian/issuer/audience và chuyển claims thành một `Authentication` trước khi quyết định quyền truy cập API.

Ở Servlet stack, phần giải mã JWT thường bắt đầu từ interface `JwtDecoder` với kết quả đồng bộ. Trong **WebFlux**, Spring Security cung cấp interface **`ReactiveJwtDecoder`**, trả kết quả bất đồng bộ qua Reactor `Mono<Jwt>`. Một implementation quan trọng là **`NimbusReactiveJwtDecoder`**: nó hỗ trợ xác minh JWT dựa trên Nimbus JOSE + JWT, dùng issuer metadata, JWK Set URI hoặc khóa được cấu hình và tích hợp validation theo hợp đồng Resource Server.

Bài học tập trung vào các câu hỏi:

- `ReactiveJwtDecoder` khác `JwtDecoder` như thế nào?
- `NimbusReactiveJwtDecoder` xác minh JWT và tải/đọc JWK Set ra sao?
- Khi nào nên dùng `issuer-uri`, khi nào dùng `jwk-set-uri` và khi nào tự tạo decoder bean?
- Cách kiểm tra issuer, audience, `exp`, `nbf`, thuật toán chữ ký và các claims tùy chỉnh.
- Cách gắn decoder vào `SecurityWebFilterChain` và ánh xạ JWT claims thành reactive authentication/authorities.
- Phân biệt JWT access token với OIDC ID token; phân biệt JWT decoder với opaque token introspection.
- Thiết kế WebFlux không chặn event loop, xử lý JWKS/key rotation và lỗi mạng.
- Kiểm tra HTTP authorization bằng `WebTestClient` và kiểm tra decoder bằng test có mục tiêu riêng.

> **Nguyên tắc:** `ReactiveJwtDecoder` giải mã và **xác thực tính hợp lệ của JWT theo cấu hình**; `NimbusReactiveJwtDecoder` là implementation thực tế. Việc decoder trả `Jwt` **không tự cho phép** người gọi xem mọi endpoint hoặc mọi bản ghi. Cần thêm authority checks và object-level authorization.

## 1. Vị trí trong kiến trúc WebFlux Resource Server

Một API WebFlux:

```text
Browser SPA / Mobile / Backend
             |
             | Authorization: Bearer <ACCESS_TOKEN>
             v
Spring WebFlux Orders API
             |
             +-- Reactive security web filters
             |       |
             |       +-- Bearer token extraction
             |       +-- ReactiveJwtDecoder
             |       +-- Jwt validation
             |       +-- Authentication + authorities
             |
             +-- Reactive authorization
             |       |
             |       +-- URL/action permissions
             |       +-- Method/domain permissions
             |
             +-- Reactive controller / service / repository
```

Ví dụ request:

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Accept: application/json
```

Token minh họa có payload:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "shop-a",
  "iat": 1794715200,
  "nbf": 1794715200,
  "exp": 1794718800
}
```

Payload chỉ là ví dụ dữ liệu: một JSON nhìn hợp lệ **không chứng minh JWT được ký bởi issuer đáng tin**. Spring Security phải xác minh chữ ký và các validators trước khi đưa claims vào security context.

### 1.1. Luồng reactive authentication

```mermaid
flowchart TD
    A["HTTP request / WebFlux ServerWebExchange"] --> B["SecurityWebFilterChain"]
    B --> C["AuthenticationWebFilter / Bearer extraction"]
    C --> D["JwtReactiveAuthenticationManager"]
    D --> E["ReactiveJwtDecoder.decode(token)"]
    E --> F["NimbusReactiveJwtDecoder"]
    F --> G["Đọc JWS header, chọn key và xác minh chữ ký"]
    G --> H{"Signature và key hợp lệ?"}
    H -- "Không" --> X["Authentication failure / thường 401"]
    H -- "Có" --> I["Claims -> Jwt"]
    I --> J["Jwt validators: issuer, timestamps, audience, custom claims"]
    J --> K{"Valid?"}
    K -- "Không" --> X
    K -- "Có" --> L["JWT authentication converter"]
    L --> M["Authentication + GrantedAuthority"]
    M --> N["Reactor security context"]
    N --> O["AuthorizationWebFilter / method security"]
    O --> P{"Có đủ quyền?"}
    P -- "Không" --> Q["Thường 403"]
    P -- "Có" --> R["Reactive handler / Mono hoặc Flux"]
```

Sơ đồ mô tả **các giai đoạn logic**, không phải thứ tự lớp nội bộ tuyệt đối ở mọi phiên bản. Điều bắt buộc là **chữ ký và claims được xác thực trước khi dùng chúng làm cơ sở cấp quyền**.

### 1.2. Phân biệt bốn tầng

| Tầng | Câu hỏi | Thành phần thường liên quan |
|---|---|---|
| Token decoding/signature | Chuỗi JWT có chữ ký và định dạng chấp nhận được không? | `ReactiveJwtDecoder`, `NimbusReactiveJwtDecoder` |
| JWT claim validation | Token có đúng issuer, audience, thời gian và contract không? | `OAuth2TokenValidator<Jwt>`, `JwtValidators` |
| Authentication conversion | Các claims tạo principal và authorities nào? | `ReactiveJwtAuthenticationConverter` / adapter |
| Authorization | Caller được gọi endpoint và đọc object nào? | `authorizeExchange`, `@PreAuthorize`, service policy |

Dù thuộc cùng luồng bảo vệ request, các trách nhiệm này **không thể thay thế nhau**.

## 2. JWT và JWS: decoder thực sự tin điều gì?

JWT thường có dạng compact:

```text
BASE64URL(protected header)
.
BASE64URL(payload)
.
BASE64URL(signature)
```

Ví dụ protected header:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "key-2026-11"
}
```

- `alg`: thuật toán JWS, chẳng hạn RS256.
- `kid`: key identifier giúp chọn khóa trong JWK Set.
- `typ`: token type/profile theo hợp đồng; không phải mọi issuer đều dùng cùng giá trị.
- Payload: `iss`, `sub`, `aud`, `exp`, `scope` và claims khác.
- Signature: bảo vệ tính toàn vẹn của protected header và payload đã ký.

Một application có thể **decode Base64URL** để nhìn thấy payload mà không cần khóa. Nhưng làm vậy **không xác minh** payload. Attacker có thể tự tạo một JWT giả:

```json
{
  "sub": "admin",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write admin"
}
```

Nếu backend tin payload chưa xác thực, hệ thống mất toàn bộ ranh giới security. `ReactiveJwtDecoder` là thành phần giúp Resource Server **không phải tự đọc token rồi tin claims**.

### 2.1. Những claim chính

| Claim | Chức năng | Điều cần xác minh |
|---|---|---|
| `iss` | Issuer của JWT | Khớp issuer tin cậy |
| `aud` | Audience, resource(s) được phép nhận JWT | Phải chứa định danh của Resource Server |
| `exp` | Expiration time | Không được quá hạn theo policy |
| `nbf` | Not-before | Không dùng trước thời điểm có hiệu lực |
| `iat` | Issued-at | Có thể dùng cho policy tuổi token, nếu được định nghĩa |
| `sub` | Subject | Làm identity theo hợp đồng issuer; không mặc định là email |
| `scope` / `scp` | Quyền được AS cấp | Chuyển thành authorities theo contract |
| `azp` / `client_id` | Client/requester theo token profile | Không thay audience |
| `tenant_id` | Claim riêng của hệ thống | Kiểm tra contract và tenant authorization |
| `jti` | Token ID | Có thể phục vụ audit/replay/revocation tùy kiến trúc |

JWT access token có thể chứa các trường khác tùy Authorization Server. **Không mặc định mọi claim là bắt buộc hoặc có cùng kiểu ở mọi issuer**.

## 3. Interface `ReactiveJwtDecoder`

Trong Spring Security reactive stack, interface có ý tưởng cơ bản:

```java
public interface ReactiveJwtDecoder {
    Mono<Jwt> decode(String token) throws JwtException;
}
```

Ở đây:

- Đầu vào: chuỗi compact JWT do Resource Server nhận.
- Đầu ra thành công: `Mono<Jwt>` phát ra một JWT đã qua decoder/validation.
- Đầu ra lỗi: publisher phát tín hiệu error, thường liên quan `JwtException`/validation, hoặc lỗi có thể phát sinh trước khi publisher được trả theo API contract.
- `Mono` biểu diễn 0–1 giá trị hoặc lỗi theo Reactor model; với một JWT hợp lệ, kết quả kỳ vọng là một `Jwt`.

### 3.1. Khác biệt với Servlet `JwtDecoder`

| Khía cạnh | Servlet stack | Reactive WebFlux |
|---|---|---|
| Interface | `JwtDecoder` | `ReactiveJwtDecoder` |
| Decode signature | `Jwt decode(String)` | `Mono<Jwt> decode(String)` |
| Decoder Nimbus | `NimbusJwtDecoder` | `NimbusReactiveJwtDecoder` |
| Security configuration | `HttpSecurity` | `ServerHttpSecurity` |
| Filter chain bean | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Authorization DSL | `authorizeHttpRequests` | `authorizeExchange` |
| Request security model | Servlet filters/context | WebFilters + Reactor context |
| Test HTTP | MockMvc | WebTestClient |
| Token type cho API | JWT access token | JWT access token |

**Không bê nguyên code Servlet sang WebFlux.** Một bean kiểu `JwtDecoder` không tự thay thế bean `ReactiveJwtDecoder` trong reactive Resource Server, cũng như `SecurityFilterChain` không thay `SecurityWebFilterChain`.

### 3.2. Tại sao kết quả là `Mono<Jwt>`?

Trong một số cấu hình, decoder cần truy vấn metadata hoặc JWK Set qua HTTP. Reactive API cho phép những thao tác I/O phù hợp với WebFlux và tích hợp với composition của Reactor, thay vì ứng dụng tự dùng blocking HTTP calls trên event-loop thread.

Ví dụ ứng dụng sử dụng decoder:

```java
Mono<Jwt> verified = reactiveJwtDecoder.decode(token);

return verified.map(jwt -> jwt.getSubject());
```

Đây là ví dụ một pipeline. **Không gọi decoder thủ công trong mọi controller** chỉ để đọc subject; Spring Security Resource Server đã thực hiện authentication và đưa principal vào security context.

### 3.3. Reactor context thay vì ThreadLocal assumptions

Security context trong WebFlux gắn với reactive execution context; nó không được dùng theo cách giả định ThreadLocal của một Servlet request truyền thống.

Ví dụ đọc Authentication trong reactive pipeline:

```java
Mono<String> currentPrincipalName =
    ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(Authentication::getName);
```

Imports:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
```

Đây là cách đọc context trong reactive flow, **không thay cho authorization**. Nếu chuyển sang một callback ngoài Reactor context hoặc dùng blocking threads không phù hợp, security context propagation có thể không giống kỳ vọng.

## 4. `NimbusReactiveJwtDecoder` là gì?

`NimbusReactiveJwtDecoder` là implementation của `ReactiveJwtDecoder` dựa trên khả năng xử lý JOSE/JWT của Nimbus, với tích hợp reactive của Spring Security.

Nó có thể được cấu hình từ:

1. **Issuer location**: dùng metadata của issuer để tìm thông tin liên quan đến keys.
2. **JWK Set URI**: biết trước URL JWKS đáng tin của issuer.
3. **Khóa công khai hoặc khóa bí mật được cấu hình**: khi hệ thống có hợp đồng quản lý khóa cụ thể, tùy builder/thuật toán và phiên bản Spring Security.

Thông dụng nhất với Authorization Server bên ngoài là **issuer location** hoặc **JWK Set URI**.

### 4.1. Decoder không tự tìm một issuer đáng tin từ token tùy ý

Sai về mặt kiến trúc:

```text
Đọc unverified JWT payload
  -> lấy iss bất kỳ do token tự khai
  -> tải JWK Set ở URL tùy ý
  -> tin token nếu chữ ký khớp khóa tự tải
```

Attacker có thể tạo token với issuer/JWKS do chính họ kiểm soát. Resource Server cần cấu hình **trusted issuer(s)** và key discovery policy từ trước; trường `iss` trong token chỉ được so với issuer đã cho phép.

### 4.2. `NimbusReactiveJwtDecoder` không cấp scopes

Decoder có thể tạo `Jwt` chứa claim `scope`, nhưng việc chuyển scope thành `SCOPE_...` thuộc authentication converter. Quyền đối với endpoint được kiểm tra sau đó ở `authorizeExchange`, còn quyền trên order/customer cụ thể thuộc service policy.

## 5. Cách đơn giản nhất: cấu hình Spring Boot bằng `issuer-uri`

Với Spring Boot WebFlux, một cấu hình thường gặp:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
```

Khi các dependencies và auto-configuration tương thích, Spring Security tạo reactive JWT decoder từ trusted issuer, đọc issuer metadata và khóa công khai cần thiết để xác thực JWT.

Đối với Resource Server, issuer URI là **định danh issuer mong đợi**, không phải URL request login và không phải audience của API.

### 5.1. Khi nào dùng `ReactiveJwtDecoders.fromIssuerLocation`?

Một cách dựng decoder bằng Java:

```java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    String issuer =
        "https://login.example.test/realms/shop";

    return ReactiveJwtDecoders.fromIssuerLocation(issuer);
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoders;
```

Hàm này là factory tạo `ReactiveJwtDecoder` dựa trên issuer discovery theo cơ chế Spring Security hỗ trợ. Nó hữu ích khi ứng dụng muốn tạo bean tường minh nhưng vẫn dùng issuer metadata.

Với ứng dụng chỉ cần cấu hình issuer và không có yêu cầu bổ sung, **cấu hình bằng property thường đơn giản hơn** so với tự viết bean.

### 5.2. Cấu hình audience nếu Spring Boot version hỗ trợ

Một số phiên bản Spring Boot hỗ trợ audience property:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
          audiences:
            - orders-api
```

Việc property audience có được áp dụng không phụ thuộc **phiên bản Spring Boot và cách bạn tự cấu hình decoder**. Nếu ứng dụng cung cấp `ReactiveJwtDecoder` bean riêng, không nên giả định Boot vẫn tự gắn toàn bộ validators mong muốn lên bean đó.

**Bất kể cấu hình theo cách nào, Orders API phải kiểm tra `aud` chứa `orders-api`.** Token dành cho Payments API không được chấp nhận chỉ vì chữ ký hợp lệ và issuer giống nhau.

## 6. Java configuration: WebFlux `SecurityWebFilterChain`

Một ví dụ hoàn chỉnh cho HTTP authorization ở Orders API:

```java
@Configuration
@EnableWebFluxSecurity
public class ReactiveApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers(HttpMethod.GET, "/public/catalog")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .pathMatchers(HttpMethod.POST, "/api/orders/*/cancel")
                    .hasAuthority("SCOPE_orders.cancel")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
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

Các điểm quan trọng:

- `ServerHttpSecurity` là builder dành cho **WebFlux**, không phải Servlet `HttpSecurity`.
- `SecurityWebFilterChain` thay `SecurityFilterChain`.
- `authorizeExchange` dùng `pathMatchers`/`anyExchange`; không phải `authorizeHttpRequests`.
- `oauth2ResourceServer(...jwt...)` kích hoạt JWT Bearer authentication bằng reactive decoder.
- `hasAuthority("SCOPE_orders.read")` kiểm tra authority được ánh xạ từ access token.
- `anyExchange().denyAll()` là fallback bảo vệ routes chưa được định nghĩa.

Đây là cấu hình minh họa về JWT và HTTP authorization. Với browser clients, vẫn cần CORS/CSRF policy phù hợp; với API đa tenant, service vẫn phải kiểm tra ownership và quyền trên từng order.

### 6.1. Khi cần tách GET/POST theo scope

Cùng URL path `/api/orders/42` có thể phục vụ GET và PATCH. Nếu chỉ viết:

```java
.pathMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

thì rule có thể bao gồm cả HTTP mutations. Hãy dùng HTTP method trong matcher nếu nghiệp vụ yêu cầu read/write/cancel permissions khác nhau.

### 6.2. Path matching không biết owner của order

Token user-123 có `orders.read` không chứng minh user được đọc order-42. Method/service cần kiểm tra:

```text
caller has orders.read
AND order.tenant is within allowed tenants
AND (
    caller is owner
    OR share ACL permits
    OR authorized support assignment permits
)
```

JWT decoder xác thực token; nó không truy vấn Orders database để cấp quyền trên bản ghi.

## 7. Tạo bean `NimbusReactiveJwtDecoder` từ issuer

Khi cần kiểm soát decoder trực tiếp:

```java
@Configuration
public class ReactiveJwtDecoderConfiguration {

    private static final String ISSUER =
        "https://login.example.test/realms/shop";

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder
                .withIssuerLocation(ISSUER)
                .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(ISSUER)
        );

        return decoder;
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
```

Ở các phiên bản Spring Security cung cấp builder `withIssuerLocation(...)`, cách này dùng issuer metadata để xác định cấu hình khóa/decoder. `setJwtValidator(...)` đặt validators mong muốn một cách tường minh.

**Đối chiếu version:** tên builder/options và hành vi discovery có thể thay đổi giữa các bản Spring Security. Với phiên bản không có builder này, dùng factory `ReactiveJwtDecoders.fromIssuerLocation(...)` hoặc builder API tương ứng được tài liệu phiên bản đó hỗ trợ. Không tự phát minh API khi triển khai.

### 7.1. Vì sao phải nói rõ `JwtValidators`?

Một decoder cần hai nhóm kiểm tra:

1. **JWS cryptography/key:** chữ ký được tạo bởi khóa được tin cậy và thuật toán được phép.
2. **Claims/contract:** issuer, audience, timestamps, token type hoặc các rules riêng.

Nếu ứng dụng tạo decoder tùy biến rồi chỉ dựa vào việc signature hợp lệ, có thể chấp nhận token từ đúng key nhưng sai audience, hết hạn hoặc không phù hợp hợp đồng.

`JwtValidators.createDefaultWithIssuer(ISSUER)` cung cấp validators mặc định cùng issuer theo phiên bản. Khi cần audience hoặc claim khác, phải **kết hợp** chúng thay vì thay thế kiểm tra cũ.

### 7.2. Decoder trả Mono nhưng validator có thể đồng bộ

Một `OAuth2TokenValidator<Jwt>` kiểm tra claims trên một `Jwt` đã được decoder tạo, thường là logic đồng bộ/CPU rất nhỏ. Điều đó không xung đột với reactive decoder.

Nhưng nếu một “validator” tự thực hiện blocking database query hoặc HTTP call, nó có thể làm hại WebFlux execution. Nếu kiểm tra cần I/O, cân nhắc đặt logic ở reactive authentication/authorization hoặc service layer phù hợp, không giấu blocking calls trong validator.

## 8. Tạo decoder bằng `jwk-set-uri`

Một issuer có JWK Set URL:

```text
https://login.example.test/realms/shop/protocol/openid-connect/certs
```

Có thể cấu hình:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
          jwk-set-uri: https://login.example.test/realms/shop/protocol/openid-connect/certs
```

Cách này cung cấp trực tiếp URL JWKS; tùy cách Spring Boot/Spring Security khởi tạo, ứng dụng có thể tránh việc phải discovery issuer metadata để tìm JWKS URI. **Nhưng giữ issuer validation là trách nhiệm riêng**, không được coi JWK Set URI là issuer check.

### 8.1. Java bean dùng JWK Set URI

```java
@Configuration
public class JwksDecoderConfiguration {

    private static final String ISSUER =
        "https://login.example.test/realms/shop";

    private static final String JWKS =
        "https://login.example.test/realms/shop/protocol/openid-connect/certs";

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder
                .withJwkSetUri(JWKS)
                .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(ISSUER)
        );

        return decoder;
    }
}
```

Import trọng tâm:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
```

**Nếu chỉ tạo decoder từ JWK Set URI mà không đặt issuer validator**, API có thể thiếu điều kiện `iss` khớp issuer mong đợi. JWK URI chứng minh khóa đến từ một nguồn được cấu hình, còn issuer/audience/purpose vẫn là claims phải được kiểm tra theo contract.

### 8.2. Chọn issuer URI hay JWK Set URI?

| Tình huống | Hướng cấu hình |
|---|---|
| AS có metadata chuẩn và bạn muốn cấu hình tối thiểu | `issuer-uri` |
| AS cung cấp JWKS URL ổn định nhưng discovery bị giới hạn | `jwk-set-uri` + validators issuer/audience |
| Cần giảm phụ thuộc startup vào discovery endpoint | Có thể cấu hình JWK Set URL tường minh; phân biệt startup với runtime fetch |
| AS phát hành khóa luân chuyển thường xuyên | Dùng JWKS và kế hoạch key rotation/cache hợp lý |
| Hệ thống không có mạng tới AS nhưng có khóa public cố định | Có thể dùng public-key builder theo contract, nhưng key rotation cần vận hành riêng |
| Nhiều issuers | Resolver và mỗi decoder/validator tin issuer tương ứng, không tự tin mọi `iss` của token |

Không “mở hết thuật toán”, bỏ issuer hoặc tắt HTTPS để xử lý một sự cố JWK tạm thời. Làm vậy biến vấn đề vận hành thành lỗ hổng xác thực.

## 9. Khám phá issuer metadata và sự phụ thuộc mạng

OIDC/OAuth Authorization Server có thể công bố metadata tại discovery endpoints, bao gồm `issuer` và `jwks_uri`.

Một luồng logic:

```mermaid
sequenceDiagram
    participant C as Client
    participant API as WebFlux Resource Server
    participant AS as Authorization Server
    C->>API: Authorization: Bearer JWT
    Note over API: Decoder cấu hình trusted issuer
    opt Cần discovery hoặc JWK refresh
        API->>AS: HTTPS metadata/JWKS request
        AS-->>API: Trusted metadata / JWK Set
    end
    Note over API: Chọn khóa theo kid/alg, xác minh chữ ký
    Note over API: Validate iss, aud, exp, nbf
    API-->>C: 2xx nếu đủ quyền / 401 hoặc 403 nếu bị từ chối
```

Chi tiết thời điểm discovery/fetch phụ thuộc phiên bản, Boot auto-configuration và caching. Có cấu hình cần truy vấn metadata khi khởi tạo bean; cấu hình khác trì hoãn công việc cho tới khi có JWT đầu tiên. **Không khẳng định một chiến lược startup cố định cho mọi phiên bản Spring Security.**

### 9.1. Trạng thái network không chứng minh token hợp lệ

Nếu metadata/JWKS endpoint lỗi DNS, TLS, timeout hoặc 5xx, decoder có thể không lấy được khóa cần thiết. Resource Server **không được chấp nhận token không kiểm tra chữ ký chỉ vì mạng lỗi**.

Một số requests vẫn có thể được xác thực nhờ cache khóa đã có, tùy thiết kế decoder; cần hiểu TTL/cache và failure behavior. Không tự fallback sang parse JWT payload hoặc chấp nhận token có `alg=none`.

### 9.2. Đối chiếu issuer metadata

Một issuer tin cậy được cấu hình:

```text
https://login.example.test/realms/shop
```

Nếu metadata đưa issuer khác hoặc JWT claim `iss` không khớp giá trị được thỏa thuận, Resource Server phải xử lý theo nguyên tắc từ chối, không tự chấp nhận mọi issuer mà máy chủ metadata trả về.

## 10. JWK Set, `kid` và luân chuyển khóa

JWK Set là tập các khóa công khai mà issuer công bố, có thể chứa nhiều khóa đang hoạt động để hỗ trợ rotation.

Ví dụ khái niệm:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-old",
      "use": "sig",
      "alg": "RS256",
      "n": "<MODULUS>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "key-new",
      "use": "sig",
      "alg": "RS256",
      "n": "<MODULUS>",
      "e": "AQAB"
    }
  ]
}
```

Các giá trị `n` ở đây là placeholders, không phải khóa thật.

Khi JWT header chứa:

```json
{"alg": "RS256", "kid": "key-new"}
```

decoder cần chọn khóa phù hợp với `kid`, thuật toán và key-use constraints để xác minh chữ ký.

### 10.1. Khi issuer thêm `kid` mới

Một rotation có thể gồm:

1. AS tạo key mới.
2. AS công bố public JWK mới trên JWKS endpoint, đồng thời giữ key cũ.
3. AS bắt đầu ký tokens mới bằng private key tương ứng `kid` mới.
4. Resource Servers refresh JWK Set theo cơ chế cache/fetch.
5. AS giữ khóa cũ đủ lâu để xác minh những tokens còn hiệu lực.
6. Sau cửa sổ chuyển đổi, AS gỡ khóa cũ.

**Không nên gỡ key cũ ngay** khi token ký bằng key đó vẫn còn hạn và cần được Resource Server xác thực. Ngược lại, giữ keys quá lâu không kiểm soát cũng có rủi ro nếu một private key đã bị lộ.

### 10.2. `kid` không phải URL để tự tải khóa

Một JWT attacker tạo có thể gắn các header parameters như `jku` hoặc `x5u`. Resource Server không nên tải khóa từ URL bất kỳ do token tự khai; trusted JWK Set URI phải đến từ cấu hình/issuer metadata được tin cậy.

`kid` chỉ là key identifier trong nguồn khóa cho phép, **không tự chứng minh key thuộc issuer**.

### 10.3. Cache JWKS không phải cache Authentication

Có thể cache public JWKs để tránh request AS mỗi lần xác minh chữ ký. Nhưng mỗi JWT vẫn cần signature/claim validation.

Không đồng nhất:

- JWK cache: cache tập public keys.
- Access token cache: cache kết quả token/authentication.
- HTTP response cache: cache dữ liệu API.
- Refresh token: credential OAuth client dùng tại token endpoint.

Chúng có vòng đời và rủi ro khác nhau.

## 11. Chỉ chấp nhận thuật toán ký được phép

JWT header có thể chứa:

```json
{"alg":"RS256"}
```

nhưng giá trị `alg` do token gửi **chưa được tin** trước xác thực. Decoder phải có danh sách thuật toán được cấu hình cho issuer/key type, không chọn bất kỳ thuật toán nào do caller yêu cầu.

Ví dụ cấu hình Nimbus builder cho thuật toán theo contract, trên phiên bản hỗ trợ option này:

```java
NimbusReactiveJwtDecoder decoder =
    NimbusReactiveJwtDecoder
        .withJwkSetUri(JWKS_URI)
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .build();
```

Import:

```java
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
```

Nếu issuer dùng ES256, RS512 hoặc các thuật toán khác, phải lựa chọn algorithm/key configuration **tương thích hợp đồng và phiên bản Spring Security**, không mặc nhiên tin mọi `alg`.

### 11.1. Những điều tránh

- Không chấp nhận `alg=none` cho bearer JWT access token.
- Không cho attacker chuyển từ asymmetric algorithm sang symmetric theo header tùy ý.
- Không dùng public key như HMAC shared secret.
- Không tắt JWS verification rồi tự đọc claims.
- Không tin URL khóa trong header của token.
- Không thêm mọi algorithms vào allowlist chỉ để một token lỗi đi qua.

### 11.2. Thuật toán và issuer là hai điều kiện

Một JWT có chữ ký RS256 hợp lệ theo một public key nào đó **chưa đủ** nếu token không được ký bằng khóa đến từ nguồn tin cậy, sai issuer hoặc sai audience. Cần hội đủ **trusted key + permitted algorithm + expected claims**.

## 12. Kết hợp issuer và audience validators

Một JWT access token hợp lệ về mật mã nhưng có:

```json
"aud": ["payments-api"]
```

không được dùng để gọi Orders API nếu Orders API yêu cầu audience `orders-api`.

Ví dụ đầy đủ sử dụng decoder bean:

```java
@Configuration
public class OrdersJwtDecoderConfiguration {

    private static final String ISSUER =
        "https://login.example.test/realms/shop";

    private static final String AUDIENCE =
        "orders-api";

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder
                .withIssuerLocation(ISSUER)
                .build();

        OAuth2TokenValidator<Jwt> defaultValidators =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token is not intended for orders-api",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                defaultValidators,
                audienceValidator
            )
        );

        return decoder;
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
```

**Đây là ví dụ quan trọng nhất của bài:** dùng `NimbusReactiveJwtDecoder` để giải mã/xác minh JWT và `setJwtValidator(...)` để gắn **toàn bộ** rule chấp nhận token của Orders API.

### 12.1. Tại sao không chỉ viết `decoder.setJwtValidator(audienceValidator)`?

Phương thức `setJwtValidator(...)` thiết lập validator cho decoder. Nếu chỉ đặt audience validator, ứng dụng có thể mất default validation issuer/timestamps tùy cách cấu hình ban đầu.

Chính vì vậy ví dụ dùng:

```java
new DelegatingOAuth2TokenValidator<>(
    JwtValidators.createDefaultWithIssuer(ISSUER),
    audienceValidator
)
```

Nó biểu diễn **AND**: token phải đạt các validations mặc định với issuer **và** audience của API.

### 12.2. Audience khác `client_id`

Một OAuth client `web-portal` có thể xin tokens cho nhiều APIs:

```text
Client ID: web-portal

Token A:
  aud = orders-api

Token B:
  aud = payments-api
```

Orders API phải nhận token A và từ chối token B, **dù client_id giống nhau**. Không dùng `client_id` thay audience chỉ vì client là caller quen thuộc.

### 12.3. Nếu issuer không có `aud`?

Không tự thêm `aud=orders-api` trong claim conversion. Cần sửa hợp đồng cấp token hoặc cấu hình AS để token dành cho Resource Server phù hợp.

Nếu hệ thống triển khai một token profile không có `aud` và có ràng buộc tài nguyên khác, phải thiết kế chính sách phù hợp với profile đó. Nhưng một ứng dụng cần audience **không nên fail open** chỉ vì issuer thiếu claim.

## 13. Timestamp validation và clock skew

JWT dùng NumericDate claims:

```json
{
  "iat": 1794715200,
  "nbf": 1794715200,
  "exp": 1794718800
}
```

Spring Security thường biểu diễn `exp`/`nbf` thành kiểu thời gian Java phù hợp khi tạo `Jwt`, chẳng hạn `Instant`.

Các API:

```java
jwt.getIssuedAt();
jwt.getNotBefore();
jwt.getExpiresAt();
```

Default validators thường kiểm tra hiệu lực thời gian theo contract và có thể áp dụng clock skew. Nếu muốn cấu hình skew rõ, có `JwtTimestampValidator`:

```java
JwtTimestampValidator timestampValidator =
    new JwtTimestampValidator(Duration.ofSeconds(60));
```

Imports:

```java
import java.time.Duration;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
```

Khi tự lắp bộ validator, vẫn phải giữ issuer và audience:

```java
OAuth2TokenValidator<Jwt> validators =
    new DelegatingOAuth2TokenValidator<>(
        new JwtTimestampValidator(Duration.ofSeconds(60)),
        new JwtIssuerValidator(ISSUER),
        audienceValidator
    );

decoder.setJwtValidator(validators);
```

Import:

```java
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
```

Đoạn này là cách **tự lắp chính sách timestamp/issuer/audience**; khi dùng default validator factory, không cần thêm timestamp validator trùng lặp trừ khi muốn thay logic skew một cách có chủ đích.

### 13.1. Skew nhỏ không có nghĩa bỏ expiration

Một issuer và Resource Server có thể chênh đồng hồ vài giây. Skew giúp giảm false rejection ở biên thời gian. Nhưng skew không nên lớn đến mức kéo dài token quá nhiều so với policy bảo mật.

**Không sửa `exp` hoặc xóa `nbf`** để chấp nhận token lỗi. Nếu đồng hồ sai đáng kể, hãy đồng bộ NTP hoặc sửa issuer clock.

### 13.2. Optional claims và hợp đồng token

Không phải mọi JWT profile đều yêu cầu `nbf`/`iat`. Một contract API có thể bắt buộc `exp` hoặc token type. Khi thêm validator, phải rõ claim nào **required**, claim nào **optional**, kiểu dữ liệu nào được chấp nhận.

Nếu API yêu cầu `exp` phải có, validator riêng có thể kiểm tra sự hiện diện của claim, không chỉ trông chờ hành vi mặc định.

## 14. Custom claim validation sau khi decode

Một hệ thống đa tenant có claim:

```json
{
  "tenant_id": "shop-a",
  "token_use": "access"
}
```

Có thể muốn từ chối token thiếu `tenant_id` hoặc `token_use` không đúng contract.

Ví dụ validator:

```java
OAuth2TokenValidator<Jwt> tenantClaimValidator = jwt -> {
    Object raw = jwt.getClaim("tenant_id");

    if (raw instanceof String tenant && !tenant.isBlank()) {
        return OAuth2TokenValidatorResult.success();
    }

    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Missing or invalid tenant_id",
            null
        )
    );
};
```

Có thể kết hợp:

```java
decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(ISSUER),
        audienceValidator,
        tenantClaimValidator
    )
);
```

### 14.1. Phân biệt token-wide contract với object-level authorization

Một tenant claim hợp lệ chỉ nói token gắn với một tenant theo hợp đồng. Nếu caller yêu cầu:

```http
GET /api/tenants/shop-b/orders/order-99
```

service cần kiểm tra principal có quyền với `shop-b` và order-99 không. JWT validator không nhìn thấy mọi quan hệ ownership/ACL và không nên biến thành một database policy tùy theo mỗi URL.

### 14.2. Không dùng claim tự tạo để cấp quyền

Một converter có thể chuẩn hóa kiểu dữ liệu hợp lệ do AS phát hành. Nó không được:

- Thêm `ROLE_ADMIN` cho mọi token.
- Tự sửa audience thành API hiện tại.
- Tự tăng `exp`.
- Thay `sub` bằng người dùng mục tiêu từ request.
- Điền tenant từ query parameter rồi coi là identity đã xác thực.

Những thay đổi ấy có thể phá vỡ ý nghĩa chữ ký và token contract.

## 15. JWT access token khác OIDC ID token

Trong OpenID Connect, một client có thể nhận **ID token** dùng để xác nhận authentication event cho OIDC client. Resource Server lại cần **access token** được cấp cho API.

Một OIDC ID token có thể trông giống JWT:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["web-portal"],
  "email": "user@example.test"
}
```

Nhưng audience `web-portal` là client, không phải Orders API. Nếu Orders API yêu cầu `aud=orders-api`, token này phải bị từ chối ngay cả khi chữ ký đúng.

### 15.1. Không dựa vào việc `sub` giống nhau

Một access token và ID token có thể cùng `sub=user-123`. Điều đó không biến chúng thành một token có cùng purpose.

Cần phân biệt:

| Loại token | Bên nhận chính | Mục đích |
|---|---|---|
| OIDC ID token | OIDC client | Chứng minh thông tin authentication của end user cho client |
| OAuth access token | Resource Server được nhắm đến | Cho API xác thực token và đánh giá quyền truy cập |
| Refresh token | Authorization Server/token endpoint qua OAuth client | Xin access token mới theo flow được hỗ trợ |

Không gửi refresh token hoặc ID token tới Orders API để dùng thay access token.

### 15.2. JWT type và profile

Một số token profiles dùng `typ=at+jwt` hoặc claims riêng. Nếu contract bắt buộc JWT access-token profile (ví dụ RFC 9068), cần thiết lập validation phù hợp. Không mặc định chỉ cần signature đúng là đủ để ngăn **cross-JWT confusion** giữa ID token, access token hoặc các loại JWT nội bộ khác.

## 16. Authorities và `JwtAuthenticationToken` trong WebFlux

Sau decoder, JWT chứa claims nhưng Spring Security còn cần một `Authentication` có principal và `GrantedAuthority`. Trong cấu hình thông thường, claim `scope`:

```json
{
  "scope": "orders.read orders.write"
}
```

được chuyển thành:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Sau đó authorization:

```java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

mới có ý nghĩa.

### 16.1. Không phải claim `roles` nào cũng tự có `ROLE_...`

Issuer có thể phát hành:

```json
{
  "roles": ["ORDER_MANAGER"],
  "scope": "orders.read"
}
```

Trong trường hợp mặc định, Spring Security thường xử lý scopes theo quy ước `SCOPE_`. Claim `roles` cần converter phù hợp nếu ứng dụng muốn ánh xạ thành authorities riêng.

Không dùng `hasRole("ORDER_MANAGER")` nếu token converter chưa tạo `ROLE_ORDER_MANAGER` từ nguồn đáng tin.

### 16.2. Authentication converter khác JWT decoder

| Công cụ | Vai trò |
|---|---|
| `ReactiveJwtDecoder` | Xác minh JWT và trả `Mono<Jwt>` |
| `OAuth2TokenValidator<Jwt>` | Kiểm tra issuer/audience/claims |
| `JwtGrantedAuthoritiesConverter` | Đọc claims quyền và tạo `GrantedAuthority` |
| `JwtAuthenticationConverter` | Chuyển `Jwt` thành Authentication trong mô hình sync |
| `ReactiveJwtAuthenticationConverterAdapter` | Adapter để dùng converter sync với reactive authentication |
| `ReactiveJwtAuthenticationConverter` | Converter reactive dành cho JWT trong WebFlux |
| `SecurityWebFilterChain` | Áp authentication/authorization cho request WebFlux |

JWT được xác minh mà không ánh xạ quyền thì client có thể authenticated nhưng vẫn bị 403 khi endpoint đòi một authority cụ thể.

## 17. Tùy chỉnh authorities bằng `ReactiveJwtAuthenticationConverterAdapter`

Giả sử AS cấp quyền trong claim riêng:

```json
{
  "permissions": ["orders:read", "orders:export"]
}
```

API muốn ánh xạ thành:

```text
PERM_orders:read
PERM_orders:export
```

Một cách cấu hình là tạo `JwtAuthenticationConverter` quen thuộc rồi đưa qua reactive adapter:

```java
@Bean
SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http) {

    JwtGrantedAuthoritiesConverter permissions =
        new JwtGrantedAuthoritiesConverter();

    permissions.setAuthoritiesClaimName("permissions");
    permissions.setAuthorityPrefix("PERM_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(permissions);
    converter.setPrincipalClaimName("sub");

    ReactiveJwtAuthenticationConverterAdapter reactiveConverter =
        new ReactiveJwtAuthenticationConverterAdapter(converter);

    return http
        .authorizeExchange(auth -> auth
            .pathMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("PERM_orders:read")
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(jwt ->
                jwt.jwtAuthenticationConverter(reactiveConverter)
            )
        )
        .build();
}
```

Imports liên quan:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;
import org.springframework.security.web.server.SecurityWebFilterChain;
```

**Điều kiện:** claim `permissions` phải được AS tin cậy phát hành và có contract rõ. Không ánh xạ bất kỳ chuỗi user tự gửi thành `ROLE_ADMIN`.

### 17.1. Adapter không làm converter blocking trở nên non-blocking

Adapter giúp tương thích kiểu API, không biến logic blocking database/HTTP thành reactive operation an toàn.

Phù hợp để chuyển **claims đã có trong JWT thành authorities** bằng phép toán in-memory nhanh. Nếu authority mapping cần gọi service, database hay network, nên dùng thiết kế reactive rõ ràng và kiểm soát latency/backpressure, không giấu `block()` trong converter.

### 17.2. Chọn principal name

Mặc định subject thường là tên principal phù hợp hơn username hiển thị. Nếu dùng:

```java
converter.setPrincipalClaimName("preferred_username");
```

thì `Authentication.getName()` có thể thành tên đăng nhập dễ đọc hơn, nhưng **có nguy cơ không ổn định hoặc trùng nhau**. Với ownership/tenant audit, dùng định danh từ issuer và subject đáng tin; khi nhiều issuers cần xét namespace issuer.

## 18. Reactive method security và quyền trên bản ghi

WebFlux có thể dùng reactive method security:

```java
@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {
}
```

Import:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
```

Ví dụ service:

```java
@Service
public class OrderService {

    private final ReactiveOrderRepository repository;

    public OrderService(ReactiveOrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Mono<OrderDto> getOrder(
            String orderId,
            AuthenticatedActor actor) {

        return repository.findVisibleOrder(
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

Các kiểu `ReactiveOrderRepository`, `AuthenticatedActor`, `OrderDto` và `OrderNotFoundException` là ví dụ domain, cần hiện thực theo ứng dụng. `AuthenticatedActor` phải được tạo từ **Authentication đã xác thực**, không lấy từ JSON body của caller.

Điểm quan trọng:

- `@PreAuthorize` kiểm tra quyền thao tác đọc.
- Repository truy vấn object **trong tenant và ownership được phép**.
- `Mono.error(...)` trả tín hiệu lỗi reactive nếu không tìm thấy bản ghi visible.
- Không gọi `repository.findById(...).block()` để rồi kiểm tra quyền.
- Không tin `tenantId` trong path/header là bằng chứng membership.

### 18.1. Method security không thay object policy

Một user có `SCOPE_orders.read` nhưng không sở hữu order-99 vẫn phải bị từ chối. `@PreAuthorize("hasAuthority(...)")` **không tự xác minh owner**.

Có thể kết hợp policy bean/Reactive AuthorizationManager khi cần logic phức tạp. Tuy nhiên nếu policy cần truy vấn reactive database, hãy thiết kế composition bất đồng bộ đúng tầng; tránh dùng blocking SpEL helper để truy cập DB.

### 18.2. Self-invocation và proxy semantics

Nếu dùng annotation-based method security, những lời gọi nội bộ cùng bean có thể không đi qua proxy như kỳ vọng. Với các use cases nhạy cảm, nên thiết kế service boundaries và các điều kiện truy vấn/mutation sao cho policy không bị bypass chỉ vì một lời gọi nội bộ.

## 19. Không gọi `block()` trong authentication path

Một lỗi điển hình khi chuyển từ Servlet sang WebFlux:

```java
// Không phù hợp trên WebFlux event-loop:
Jwt jwt = reactiveJwtDecoder.decode(token).block();
```

Hoặc:

```java
public Mono<Jwt> decode(String token) {
    Jwt jwt = blockingJwtDecoder.decode(token);
    return Mono.just(jwt);
}
```

Cách thứ hai thực hiện blocking work **trước khi** trả publisher. Nếu có I/O đồng bộ, nó có thể chặn event-loop thread và làm giảm throughput, gây latency hoặc timeout.

### 19.1. Composition phù hợp

Reactive style:

```java
return reactiveJwtDecoder.decode(token)
    .flatMap(jwt -> reactiveService.findOrderForActor(
        jwt.getSubject(),
        jwt.getClaimAsString("tenant_id"),
        orderId
    ));
```

Ở một controller Resource Server bình thường, việc tự gọi decoder lại là không cần thiết; ví dụ trên chỉ minh họa composition. Phần auth đã được Spring Security filter xử lý.

### 19.2. Nếu buộc phải tích hợp thư viện blocking

Một đoạn blocking legacy có thể được cô lập trên boundedElastic khi thực sự cần:

```java
Mono<LegacyResult> result =
    Mono.fromCallable(() -> legacyClient.call())
        .subscribeOn(Schedulers.boundedElastic());
```

Nhưng đây **không phải lý do thay reactive decoder bằng implementation blocking tùy tiện**. Dùng scheduler không sửa được các vấn đề về giới hạn concurrency, timeouts, bulkhead, memory hoặc resource exhaustion. Với JWKS/metadata, ưu tiên decoder và reactive HTTP integration của Spring Security.

### 19.3. Đừng tự `subscribe()` để “khởi chạy xác thực”

Ví dụ sai:

```java
reactiveJwtDecoder.decode(token)
    .subscribe(jwt -> securityContext.setAuthentication(...));

// Code tiếp tục ngay, authentication chưa chắc xong.
```

Một lời gọi `subscribe()` thủ công như trên tách luồng thực thi khỏi security pipeline, có thể tạo race condition và context không được propagate. Hãy để Spring Security quản lý authentication chain hoặc return publisher để pipeline chờ đúng kết quả.

## 20. Reactive error signals và HTTP response

Khi `ReactiveJwtDecoder.decode(...)` không thể xác thực token, publisher phát error (hoặc implementation có thể throw sớm theo contract). Spring Security authentication manager/filter chuyển thất bại thành HTTP error phù hợp.

Các trường hợp thông dụng:

| Tình huống | Lớp phát hiện | HTTP thường gặp |
|---|---|---|
| Không có Bearer token ở route protected | Security authentication/authorization | `401 Unauthorized` và Bearer challenge |
| JWT malformed | Decoder | `401 invalid_token` |
| JWT chữ ký sai/khóa không phù hợp | Decoder | `401 invalid_token` |
| JWT hết hạn | Timestamp validator | `401 invalid_token` |
| JWT sai issuer | Issuer validator | `401 invalid_token` |
| JWT không chứa expected audience | Audience validator | `401 invalid_token` |
| Token hợp lệ, không có authority đọc | Authorization | `403 Forbidden` |
| Token có scope, object ngoài tenant/ownership | Service policy | `403` hoặc `404` theo contract |
| JWKS/metadata endpoint lỗi | Decoder/network | Xác thực không thành công; HTTP có thể phụ thuộc exception handling |
| API logic xảy ra lỗi nghiệp vụ | Handler/service | Status domain riêng |

**Đừng trả `403` cho token chưa được xác thực và đừng trả `401 invalid_token` cho mọi object-level permission failure.**

### 20.1. Reactive security entry points

WebFlux dùng các component server-side dành riêng cho reactive authentication/authorization, không phải Servlet classes như `BearerTokenAuthenticationEntryPoint` dành cho `HttpServletResponse`.

Khi tùy chỉnh response JSON/Problem Details ở WebFlux, cần chọn extension point phù hợp của `ServerHttpSecurity` và giữ nguyên semantics HTTP Bearer `WWW-Authenticate`. Không redirect API client tới HTML login nếu kiến trúc yêu cầu Bearer token.

### 20.2. Không nuốt error rồi tạo `Jwt` giả

Sai:

```java
return delegate.decode(token)
    .onErrorResume(error ->
        Mono.just(fakeJwtWithAdminScope)
    );
```

Đoạn này là ví dụ **không an toàn**: khi chữ ký sai/JWKS lỗi, server tự dựng principal hợp lệ. Authentication phải **fail closed**. Không đưa người gọi vào SecurityContext khi decoder không xác thực được.

## 21. `Jwt` không tự cấp quyền truy cập mọi đối tượng

Một JWT có:

```json
{
  "sub": "user-123",
  "tenant_id": "shop-a",
  "scope": "orders.read"
}
```

và request:

```http
GET /api/orders/order-99
```

Chỉ vì token hợp lệ và có scope đọc không chứng minh order-99 thuộc user-123.

Một chính sách tốt thường là:

```text
canReadOrder(actor, order):
  valid access token for orders-api
  AND actor has orders.read authority
  AND order.tenant belongs to actor allowed tenants
  AND (
       actor owns order
       OR valid share ACL
       OR assigned support policy permits
  )
```

Một repository reactive nên truy vấn các records **visible** theo actor, thay vì load tất cả order rồi lọc sau hoặc trả dữ liệu trước khi kiểm tra.

### 21.1. List/export/count cũng cần filter

Không chỉ detail endpoint:

```text
GET /api/orders
GET /api/orders/search
GET /api/orders/count
GET /api/orders/export
```

đều phải giới hạn dữ liệu theo tenant/owner/share policy. Token có `SCOPE_orders.read` không phải quyền truy vấn toàn database.

## 22. WebFlux JWT decoder và opaque token là hai nhánh khác nhau

Một ứng dụng có thể nhận:

1. JWT access token: Resource Server dùng `ReactiveJwtDecoder` để xác minh JWS/claims.
2. Opaque access token: Resource Server gọi introspection endpoint qua `ReactiveOpaqueTokenIntrospector`.

Với opaque token, API cần cấu hình nhánh `opaqueToken(...)` phù hợp, không dùng `NimbusReactiveJwtDecoder` để cố parse một chuỗi opaque ngẫu nhiên.

### 22.1. Không chọn loại token chỉ dựa vào dấu chấm

Một token có dấu chấm không tự chứng minh nó là JWT access token hợp lệ; một AS có thể cấp token với profile khác. Chọn chế độ xử lý theo **hợp đồng Resource Server và AS**, không tự phân nhánh “có 3 phần thì tin JWT, không thì introspection” mà thiếu chính sách tin cậy.

### 22.2. Opaque introspection có khác biệt revocation

JWT self-contained thường có thể được Resource Server xác minh cục bộ trong thời hạn token, nhưng muốn thu hồi ngay cần giải pháp ngoài chữ ký như TTL ngắn, denylist, token status service hoặc introspection tùy kiến trúc.

Opaque introspection có thể kiểm tra trạng thái token trực tuyến nhưng tăng phụ thuộc latency/availability của Authorization Server. Việc chọn JWT hay opaque là quyết định kiến trúc; không có một lựa chọn tốt tuyệt đối cho mọi hệ thống.

## 23. Multi-issuer và multi-tenant trong WebFlux

Một hệ thống có thể chấp nhận tokens từ:

```text
Issuer A:
  https://login.example.test/realms/shop

Issuer B:
  https://login.example.test/realms/partners
```

Mỗi issuer có thể có:

- Trusted issuer URI khác nhau.
- JWKS URI/key rotation khác nhau.
- Audience mapping khác nhau.
- Algorithms/claim contract khác nhau.
- Ý nghĩa `sub` và `tenant_id` khác nhau.

Vì vậy một decoder chỉ tin issuer A không nên tự chấp nhận token issuer B. Nếu cần multi-issuer, dùng một **reactive authentication manager resolver** phù hợp để chọn những authentication managers/decoders đã allowlist, và kiểm tra issuer/contract của từng nhánh.

### 23.1. Không tin issuer từ JWT chưa xác thực một cách tùy tiện

Một resolver có thể cần đọc unverified issuer claim để chọn decoder **trong danh sách issuers đã được tin cậy**. Nếu issuer không có trong allowlist, phải từ chối, không xây decoder theo URL do token tự cung cấp.

Đặc biệt tránh logic:

```text
issuer = decodePayloadWithoutVerification(token).iss
decoder = NimbusReactiveJwtDecoder.withIssuerLocation(issuer).build()
accept if signature verifies
```

mà không kiểm tra issuer thuộc allowlist đã quản trị. Attacker có thể tự tạo issuer/keys và token, rồi buộc Resource Server tin nguồn của họ.

### 23.2. Identity thường phải xét `(iss, sub)`

Hai issuers có thể đều phát hành:

```json
"sub": "user-123"
```

Nhưng đây có thể là hai accounts độc lập. Khi dùng JWT subject để ánh xạ vào dữ liệu kinh doanh, cần xem xét issuer namespace, tenant và mapping nội bộ, không chỉ username hoặc subject trùng chuỗi.

## 24. Testing HTTP authorization bằng `WebTestClient`

Spring Security Test hỗ trợ cấu hình test JWT đã xác thực cho reactive WebFlux thông qua `mockJwt()`.

Ví dụ concept:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveOrderSecurityTests {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void readScopeCanReachGetOrderEndpoint() {
        webTestClient
            .mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            ))
            .get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void otherScopeCannotReachGetOrderEndpoint() {
        webTestClient
            .mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile")
            ))
            .get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Imports:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;
```

**Điều kiện của ví dụ:** Test context phải có WebFlux SecurityFilterChain, controller và data fixtures cho `/api/orders/42`; status 200 chỉ hợp lý khi business service thật sự thành công. Trong môi trường không có order 42, test có thể nhận 404 sau khi qua HTTP authorization.

### 24.1. `mockJwt()` không xác minh chữ ký thật

Một request test dùng:

```java
.mutateWith(mockJwt())
```

thường mô phỏng JWT Authentication phục vụ kiểm tra security/authorization. Nó **không chứng minh** `NimbusReactiveJwtDecoder` tải JWKS và xác minh JWS signature đúng.

Vì vậy cần tách:

- WebTestClient tests: HTTP routes, 401/403, authorities, method security.
- Decoder tests: issuer, audience, signature/key, expiry, JWK rotation.
- Integration tests: decoder thật với AS/JWKS test endpoint phù hợp.
- Business tests: tenant/ownership/object permissions.

### 24.2. Kiểm tra request thiếu token

Với route protected:

```java
webTestClient.get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isUnauthorized()
    .expectHeader().valueMatches(
        "WWW-Authenticate",
        "Bearer.*"
    );
```

Trạng thái/header thực tế phụ thuộc chain và entry-point configuration. Với WebFlux JWT Bearer Resource Server thông dụng, request không token tới protected endpoint thường nhận `401` và Bearer challenge.

### 24.3. Thử thiếu authority và sai object

Một token có scope read nhưng request lấy order của người khác có thể qua HTTP authorization rồi bị business policy từ chối. Để phát hiện Broken Object Level Authorization, cần fixtures của **ít nhất hai users, hai tenants** và kiểm tra cả detail/list/export.

## 25. Unit test decoder với key/JWT fixtures

Để kiểm tra signature/claim validation thật, cần một JWT test có:

- Header `alg` phù hợp.
- `kid` khớp public JWK được test server cung cấp.
- Chữ ký tạo bằng test private key tương ứng.
- `iss`, `aud`, `exp` và các claims kiểm soát được.

Một bảng test:

| JWT test | Key/signature | Claims | Kết quả decode mong đợi |
|---|---|---|---|
| Valid Orders access token | Đúng trusted key | Issuer/audience/time đúng | Success `Mono<Jwt>` |
| Sai chữ ký | Không đúng key | Claims nhìn hợp lệ | Error |
| Sai issuer | Trusted signature | Issuer khác | Error |
| Sai audience | Trusted signature | `aud=payments-api` | Error |
| Hết hạn | Trusted signature | `exp` quá khứ | Error |
| Chưa đến `nbf` | Trusted signature | Token chưa hiệu lực | Error |
| Thiếu tenant bắt buộc | Trusted signature | Không có `tenant_id` | Error theo custom policy |
| Thuật toán không được phép | Không phù hợp allowlist | Bất kỳ | Error |
| `kid` mới đã công bố | Đúng key mới | Claims hợp lệ | Success khi decoder cập nhật keys |
| `kid` không biết và không thể fetch key | Không có trusted key | Bất kỳ | Fail closed |

Không dùng base64-decoded payload để test signature. Phải có **token thật được ký trong môi trường test**, hoặc stub quá trình network/JWKS một cách có chủ đích để kiểm tra contract.

### 25.1. `StepVerifier` kiểm tra reactive result

Nếu đã có decoder và một token test được ký hợp lệ:

```java
StepVerifier.create(decoder.decode(validToken))
    .assertNext(jwt -> {
        assertEquals("user-123", jwt.getSubject());
        assertTrue(jwt.getAudience().contains("orders-api"));
    })
    .verifyComplete();
```

Với token không hợp lệ:

```java
StepVerifier.create(decoder.decode(invalidToken))
    .expectError(JwtException.class)
    .verify();
```

Imports:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.springframework.security.oauth2.jwt.JwtException;
import reactor.test.StepVerifier;
```

Các biến `decoder`, `validToken`, `invalidToken` là fixtures được test setup cung cấp. Với lỗi network đặc thù, loại exception có thể khác; hãy assert phù hợp phạm vi test.

### 25.2. Tránh phụ thuộc JWKS production trong unit test

Không nên gọi production AS từ unit tests vì:

- Gây flaky tests khi network gặp sự cố.
- Gửi traffic ngoài dự kiến.
- Khó kiểm soát key rotation và response.
- Có thể lộ environment secrets nếu setup sai.

Thay vào đó dùng test JWKS HTTP server hoặc test keys riêng không được dùng cho production.

## 26. Kiểm tra auto-configuration và bean selection

Một dự án có thể đồng thời có:

```yaml
spring.security.oauth2.resourceserver.jwt.issuer-uri: ...
```

và:

```java
@Bean
ReactiveJwtDecoder jwtDecoder() { ... }
```

Khi developer tạo bean decoder riêng, Spring Boot auto-configuration có thể **back off** và để bean đó quyết định behavior. Vì vậy:

- Không mặc nhiên nghĩ Boot vẫn tự áp `audiences` vào custom decoder.
- Không mặc nhiên nghĩ default issuer validation còn tồn tại sau `setJwtValidator(...)` tùy cấu hình.
- Không vô tình đăng ký nhiều `ReactiveJwtDecoder` beans mà không xác định bean nào được dùng.
- Nếu cần một decoder riêng cho một SecurityWebFilterChain, chỉ định rõ qua JWT DSL phù hợp với version.

### 26.1. Chỉ định decoder tường minh trong DSL

Một số cấu hình cho phép:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(jwt ->
        jwt.jwtDecoder(reactiveJwtDecoder)
    )
)
```

Ở đây `reactiveJwtDecoder` là bean/instance phù hợp được cung cấp qua dependency injection. Cách này hữu ích khi có nhiều decoders/issuers/chains, nhưng cần bảo đảm không tạo vòng phụ thuộc và không dùng decoder của API khác.

### 26.2. Nhiều SecurityWebFilterChains

Nếu ứng dụng có:

```text
/api/orders/**   JWT Orders Resource Server
/api/admin/**    JWT Admin API
/web/**          Session browser UI
```

hãy xác định chain matchers và thứ tự đúng. Một chain catch-all đứng trước API chain có thể khiến request API nhận form login/session auth thay Bearer JWT.

Các SecurityWebFilterChains có thể được phân biệt bằng `securityMatcher(...)` của `ServerHttpSecurity` và order; hãy dùng mapping rõ thay vì nghĩ `anyExchange().denyAll()` trong một chain sẽ tự bảo vệ mọi request của toàn ứng dụng.

## 27. CORS và CSRF trong JWT WebFlux Resource Server

Một SPA tại:

```text
https://app.example.test
```

gọi API:

```text
https://api.example.test
```

qua `Authorization: Bearer ...` sẽ chịu browser CORS policy dù backend dùng WebFlux.

Với browser client:

- Allowed origin phải đúng scheme/host/port.
- Allowed headers phải chứa `Authorization` nếu frontend chủ động gửi Bearer.
- JSON POST/PATCH có thể cần `Content-Type` trong allowed headers.
- CORS preflight `OPTIONS` thường không mang access token.
- WebFlux CORS cần được xử lý trước khi auth yêu cầu bearer cho request thực.
- `allowCredentials(true)` không tự động cần chỉ vì client có Bearer header; phụ thuộc cookie/session credentials behavior.
- CORS không thay CSRF hoặc OAuth authorization.

### 27.1. Một CORS cấu hình WebFlux minh họa

```java
@Bean
CorsWebFilter corsWebFilter() {
    CorsConfiguration cors = new CorsConfiguration();

    cors.setAllowedOrigins(List.of(
        "https://app.example.test"
    ));

    cors.setAllowedMethods(List.of(
        "GET", "POST", "PATCH"
    ));

    cors.setAllowedHeaders(List.of(
        "Authorization", "Content-Type"
    ));

    cors.setExposedHeaders(List.of(
        "WWW-Authenticate"
    ));

    cors.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();

    source.registerCorsConfiguration("/api/**", cors);

    return new CorsWebFilter(source);
}
```

Imports trong WebFlux:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
```

**Không nhầm** `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` với class Servlet có tên tương tự trong Spring MVC. Với dự án cụ thể, có thể chọn WebFlux CORS integration khác; tránh đăng ký hai filters xung đột.

### 27.2. JWT Bearer header và CSRF

Nếu API **chỉ** nhận Bearer token qua Authorization header do client chủ động gắn, threat model CSRF khác cookie session. Nhưng nếu cùng ứng dụng còn dùng cookie/session hoặc BFF login, không được tắt CSRF toàn cục chỉ vì một nhánh API dùng JWT.

CORS cho browser quyền đọc response; CSRF controls ngăn requests tự gắn credentials gây side effects. Hai cơ chế độc lập.

## 28. Khả năng mở rộng, latency và reactive I/O

Nimbus reactive decoder có thể gặp các chi phí:

1. Đọc compact JWT.
2. Lấy/chọn khóa công khai đáng tin, có thể cần cache/network.
3. Xác minh signature với thuật toán mật mã.
4. Tạo claim objects.
5. Chạy validators.
6. Chuyển authorities.

Không phải tất cả bước đều “miễn phí” chỉ vì API trả `Mono`. JWS verification là CPU work; JWKS fetch có latency network; claim conversion cũng dùng CPU/memory.

### 28.1. Đừng tin rằng “reactive” tự làm token verification nhanh hơn

Reactive phù hợp khi có nhiều I/O và cần không chiếm thread trong lúc chờ. Nó không làm biến mất chi phí RSA/ECDSA, JSON parsing hoặc policy checks.

Nếu API có traffic cao, cần quan sát:

- Thời gian decode JWT.
- Số lượng requests JWKS và cache hit/miss.
- JWKS HTTP failures/timeouts.
- CPU sử dụng cho signature verification.
- 401/403 theo route và issuer.
- Key rotation disruptions.
- Số token invalid/malformed.
- Memory/backpressure ở WebFlux pipelines.

### 28.2. Kết hợp timeout và retry cẩn trọng

Khi AS/JWKS không sẵn sàng, retry vô hạn có thể tăng tải và làm request treo. Cần chính sách timeout/backoff và cache thích hợp do decoder/HTTP client quản lý; **không bỏ security validation** để đạt throughput.

### 28.3. Không log raw JWT để debug

Một bearer token có thể bị dùng lại nếu lộ. Tránh log:

```text
Authorization: Bearer eyJ...
token=<FULL_JWT>
```

Thay vào đó log:

```text
request_id=req-123
route=GET /api/orders/{id}
authn=FAILED
reason=INVALID_AUDIENCE
issuer_alias=shop
http_status=401
```

Chỉ log issuer/subject/tenant khi cần và theo chính sách xử lý dữ liệu nhạy cảm; không log raw claims hay secrets.

## 29. Các lỗi thường gặp khi dùng `ReactiveJwtDecoder`

### Lỗi A — Cài Servlet starter rồi cấu hình WebFlux

Spring Security Servlet `JwtDecoder` và `SecurityFilterChain` không phải các types WebFlux mong đợi. Dùng đúng WebFlux starter và reactive security DSL, tránh phụ thuộc lẫn lộn làm ứng dụng chọn stack sai.

### Lỗi B — Dùng `NimbusJwtDecoder` thay `NimbusReactiveJwtDecoder`

Nếu ứng dụng phải chạy reactive auth, ưu tiên `ReactiveJwtDecoder`. Đừng tự wrap một decoder đồng bộ bằng `Mono.just(blockingDecode(...))` và nghĩ không còn blocking.

### Lỗi C — Chỉ cấu hình `jwk-set-uri` rồi quên issuer

Key URL chỉ định nguồn khóa, không tự kiểm tra `iss`. Đặt issuer validator nếu contract yêu cầu, đặc biệt khi tự tạo bean.

### Lỗi D — Chỉ kiểm tra chữ ký và `exp`

Một token có thể hợp lệ nhưng dành cho Payments API. Kiểm tra `aud` của Orders API.

### Lỗi E — Khi thêm audience validator lại làm mất defaults

`setJwtValidator(...)` thiết lập validator; cần combine `JwtValidators.createDefaultWithIssuer(...)` và audience custom check.

### Lỗi F — Tin thuật toán trong `alg` từ token

Chỉ cho algorithms đã được cấu hình và trust key material đúng, không chọn từ untrusted header.

### Lỗi G — Tin `iss` từ token rồi fetch JWKS tùy ý

Có thể cho attacker kiểm soát issuer/keys. Chỉ chấp nhận issuers nằm trong allowlist đáng tin.

### Lỗi H — Không phân biệt access token và ID token

ID token có thể đúng chữ ký nhưng audience là OAuth client. API phải yêu cầu access token dành cho chính Resource Server.

### Lỗi I — Tự giải mã Base64URL để lấy user/role

Claims có thể bị attacker thay đổi khi chưa xác minh chữ ký. Dùng `Jwt` từ authenticated principal của Spring Security.

### Lỗi J — Gán role từ mọi claim giống tên `roles`

Role/permission mapping cần đúng issuer contract, không cấp `ROLE_ADMIN` từ dữ liệu thiếu tin cậy.

### Lỗi K — `block()` hoặc JDBC blocking trong WebFlux authentication chain

Có thể gây nghẽn event-loop, giảm throughput và treo requests. Dùng reactive composition hoặc cô lập blocking I/O theo thiết kế.

### Lỗi L — Tự `subscribe()` rồi dùng SecurityContext

Tạo race và mất context. Hãy trả publishers và để Spring Security quản lý reactive flow.

### Lỗi M — Mặc định mọi 401 là token hết hạn

401 có thể do signature, issuer, audience, time, token type hoặc JWKS failures. Không refresh token vô hạn.

### Lỗi N — Token đúng scope là được xem mọi bản ghi

`orders.read` không chứng minh caller là owner của order 42. Kiểm tra tenant/ownership/ACL tại service.

### Lỗi O — Bỏ validation khi key rotation gặp sự cố

Nên vận hành AS JWKS rotation đúng, refresh/cache keys và giữ old public keys trong cửa sổ phù hợp. Không disable verification hoặc chấp nhận mọi `kid`.

### Lỗi P — Dùng `mockJwt()` làm bằng chứng signature verification

Mock JWT chỉ kiểm tra authorization flow, không kiểm tra decoder crypto. Cần test JWT thật được ký.

### Lỗi Q — Quên CORS trên các browser requests

Một API có JWT hợp lệ vẫn có thể bị browser che response khi frontend khác origin. CORS cần cấu hình riêng, không thay scope/security.

## 30. Ma trận tình huống thực tế

| Tình huống | Decoder | Validation/authorization | Kết quả dự kiến |
|---|---|---|---|
| JWT ký đúng, issuer/audience/time đúng, có scope read | Success | GET order đọc được nếu object policy cho phép | Cho qua |
| JWT ký đúng, thiếu read scope | Success | HTTP rule thiếu `SCOPE_orders.read` | Thường 403 |
| JWT ký đúng, sai audience | Success về mật mã | Audience validator thất bại | Thường 401 |
| JWT ký bằng key lạ | Signature verification thất bại | Không tạo Authentication | Thường 401 |
| JWT hết hạn | Timestamp validator thất bại | Không tạo Authentication | Thường 401 |
| JWT không có tenant khi contract bắt buộc | Custom validator thất bại | Không tạo Authentication | Thường 401 |
| Token hợp lệ, order khác tenant | Decoder success | Object policy từ chối | 403/404 |
| `kid` mới, JWKS đã cập nhật | Decoder chọn/fetch key mới | Claims hợp lệ | Thành công |
| `kid` mới nhưng JWKS outage | Không có trusted key | Fail closed | Authentication lỗi |
| Browser SPA gửi Authorization nhưng origin không được allow | Decoder có thể chưa chạy do preflight | Browser CORS từ chối | JS không được đọc response |
| Opaque token đưa vào JWT decoder | Không parse/verify được theo JWT contract | Fail closed | Authentication lỗi |
| Token có `alg=none` | Algorithm không cho phép | Fail closed | Authentication lỗi |
| ID token có audience web client | Chữ ký có thể đúng | Audience/profile API từ chối | Authentication lỗi |

Bảng cho thấy **decoder thành công** chỉ là một phần của yêu cầu cuối cùng. CORS, JWT claims contract, scope, object permissions và domain state đều có vai trò riêng.

## 31. Checklist thiết kế kiến trúc JWT Resource Server WebFlux

Trước khi triển khai, hãy trả lời:

1. **Stack có thật sự là WebFlux?** Dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và `ReactiveJwtDecoder`.
2. **Trusted issuer là gì?** Có một hay nhiều issuers được phép?
3. **Dùng issuer metadata hay JWK Set URL?** Có HTTPS, caching và key rotation plan không?
4. **Permitted signing algorithms là gì?** Có allowlist phù hợp issuer/key type không?
5. **Audience của API là gì?** Token phải chứa `orders-api` hay resource identifier nào?
6. **Expiry/nbf/skew policy là gì?** Có sử dụng validators đúng và đồng bộ đồng hồ không?
7. **Token type/profile là gì?** Có phân biệt JWT access token với OIDC ID token không?
8. **Custom claims nào bắt buộc?** Có kiểm tra kiểu/giá trị thay vì tự tạo defaults không?
9. **Authorities ánh xạ từ đâu?** Có quy ước `SCOPE_`, `ROLE_` hoặc claim `permissions` riêng không?
10. **Method/URL rules cụ thể chưa?** Có fallback deny-all và tránh wildcard quá rộng không?
11. **Object-level policy ở đâu?** List/detail/update/export đều ràng buộc tenant/owner/ACL chưa?
12. **Reactive execution sạch blocking?** Có `block()`, JDBC hoặc HTTP sync trong auth path không?
13. **CORS/CSRF theo browser client thực tế chưa?** Bearer SPA khác cookie BFF thế nào?
14. **JWKS outage/key rotation được vận hành ra sao?** Có metrics/timeouts/cache plan không?
15. **Test chia đúng lớp chưa?** MockJwt HTTP test khác decoder signature test?
16. **Secrets/logs được bảo vệ chưa?** Không log Authorization header, tokens hay private keys?

Những câu hỏi này liên hệ trực tiếp với kiến trúc, không nên chỉ được xem là cấu hình vài dòng `application.yml`.

## 32. Tài liệu tham khảo

- [Spring Security Reference — OAuth 2.0 Resource Server JWT (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): cấu hình WebFlux JWT, issuer/JWKS, key rotation và authorities.
- [Spring Security API — ReactiveJwtDecoder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html): hợp đồng reactive decode.
- [Spring Security API — NimbusReactiveJwtDecoder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html): Nimbus implementation và các builders.
- [Spring Security API — ReactiveJwtDecoders](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/ReactiveJwtDecoders.html): factories dựng decoder từ issuer.
- [Spring Security Reference — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `ServerHttpSecurity` và `SecurityWebFilterChain`.
- [Spring Security Reference — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): reactive authorization tại method/service.
- [Spring Security Reference — Testing Reactive Security](https://docs.spring.io/spring-security/reference/reactive/test/index.html): `WebTestClient` và test authentication/authorization.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): registered claims, compact JWT.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK và JWK Set.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515): JWS, protected header, signature.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thuật toán tin cậy, cross-JWT confusion và an toàn xử lý JWT.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token dành cho Resource Server.
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/): `Mono`, `Flux`, reactive composition và context.

**Kết luận:** `ReactiveJwtDecoder` là hợp đồng giải mã/xác thực JWT bằng Reactor `Mono<Jwt>` trong **WebFlux**; `NimbusReactiveJwtDecoder` là implementation phổ biến có khả năng dùng trusted issuer metadata, JWK Set và JWS verification. Cấu hình an toàn đòi **trusted keys và algorithms**, validators **issuer–audience–thời gian**, ánh xạ authorities theo claims đáng tin, cùng HTTP và object-level authorization. Hãy giữ security pipeline thực sự reactive, không gọi `block()` trong auth path, không dùng JWT payload chưa xác minh và không bỏ validation khi JWKS có sự cố. 
