# OAuth2TokenValidator và giữ nguyên kiểm tra nền tảng khi tùy chỉnh

## 1. Vì sao phải giữ các kiểm tra mặc định khi mở rộng JWT validation?

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, một ứng dụng **WebFlux** nhận Bearer access token rồi xác minh token trước khi cấp `Authentication` cho người gọi. Với JWT access token, thành phần quan trọng là **`ReactiveJwtDecoder`**. Decoder không chỉ đọc payload; nó còn tham gia quá trình xác minh chữ ký JWS và áp dụng các quy tắc kiểm tra claim.

Một yêu cầu nghiệp vụ phổ biến: Resource Server chỉ chấp nhận access token dành cho API `orders-api`. Nhà phát triển thêm một audience validator:

```java
OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
        jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Invalid audience",
                                null));
```

Đoạn validator trên chỉ kiểm tra **`aud`**. Nếu gắn nó bằng:

```java
decoder.setJwtValidator(audienceValidator);
```

thì ở các phiên bản/implementation decoder dùng setter này, lệnh **thay thế validator hiện hành**, **không tự nối** quy tắc mới vào mọi kiểm tra có sẵn. Kết quả có thể là những kiểm tra đã được tạo trước đó, chẳng hạn **`exp`, `nbf` hoặc `iss`**, không còn nằm trong chuỗi validator mà ứng dụng mong đợi.

Điều này khác với kiểm tra chữ ký JWS. Chữ ký thường vẫn được decoder xác minh ở lớp JOSE, nhưng **JWT có chữ ký hợp lệ không có nghĩa còn hạn hoặc dành đúng issuer/resource**.

**Cách tổ chức an toàn** là tạo bộ validator nền tảng rồi kết hợp validator mới:

```java
OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(issuer);

decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                defaults,
                audienceValidator));
```

Bài học này giải thích chính xác trách nhiệm của `OAuth2TokenValidator` trong **WebFlux**, cách giữ kiểm tra nền tảng, phương pháp bổ sung quy tắc tùy chỉnh mà không làm mất an toàn, và cách kiểm thử bằng JUnit, StepVerifier, WebTestClient.

> **Thông điệp cốt lõi:** Khi thêm một quy tắc bảo mật, hãy **mở rộng** hợp đồng đã được bảo đảm, **không thay thế vô ý** các kiểm tra bảo mật đang tồn tại. Đặc biệt, `setJwtValidator(...)` không có nghĩa “append validator mới”.

## 2. JWT validation nằm ở đâu trong kiến trúc WebFlux?

Một request:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6...
```

Đường xử lý Servlet và WebFlux khác nhau. Trong **WebFlux**, mô hình điển hình là:

```mermaid
flowchart TD
    CLIENT["HTTP client<br/>Authorization: Bearer JWT"] --> FILTER["AuthenticationWebFilter"]
    FILTER --> EXTRACT["ServerBearerTokenAuthenticationConverter"]
    EXTRACT --> MANAGER["JwtReactiveAuthenticationManager"]
    MANAGER --> DECODER["ReactiveJwtDecoder / NimbusReactiveJwtDecoder"]
    DECODER --> JOSE{"JWS hợp lệ?<br/>alg, key, chữ ký"}
    JOSE -->|"Không"| BAD["Authentication failure<br/>thường 401 invalid_token"]
    JOSE -->|"Có"| CLAIMS["OAuth2TokenValidator&lt;Jwt&gt;<br/>defaults + custom validators"]
    CLAIMS -->|"Không đạt"| BAD
    CLAIMS -->|"Đạt"| AUTH["JwtAuthenticationToken + SCOPE_ authorities"]
    AUTH --> CONTEXT["Reactor SecurityContext"]
    CONTEXT --> POLICY["AuthorizationWebFilter / Method Security"]
    POLICY -->|"Thiếu quyền"| FORBIDDEN["Thường 403 Forbidden"]
    POLICY -->|"Đủ quyền"| CONTROLLER["Handler / Service / Domain policy"]
```

Sơ đồ khái niệm trên nhấn mạnh ba lớp khác nhau:

| Lớp | Thành phần điển hình | Điều được bảo vệ |
| --- | --- | --- |
| **JOSE / chữ ký / khóa tin cậy** | `NimbusReactiveJwtDecoder`, JWKS/public key được cấu hình, thuật toán cho phép | Token có được ký bởi khóa mà API tin trong đúng thuật toán và định dạng không? |
| **JWT claim validation** | `OAuth2TokenValidator<Jwt>`, `JwtValidators`, `DelegatingOAuth2TokenValidator` | `iss`, `exp`, `nbf`, `aud`, các claim nghiệp vụ/profile có thỏa hợp đồng không? |
| **Authorization** | `JwtAuthenticationConverter`, `SecurityWebFilterChain`, `@PreAuthorize`, domain policy | Principal đã xác thực có đủ scope/authority và quyền trên tài nguyên cụ thể không? |

**Một custom claim validator không tự kiểm tra chữ ký**, và **một chữ ký hợp lệ không tự thay thế claim validation**. Ba lớp phải cùng đúng.

### 2.1. Những lớp WebFlux cần dùng, tránh nhầm Servlet

| WebFlux | Servlet tương ứng | Ghi chú |
| --- | --- | --- |
| `SecurityWebFilterChain` | `SecurityFilterChain` | Chuỗi bảo mật reactive HTTP. |
| `ServerHttpSecurity` | `HttpSecurity` | DSL cấu hình bảo mật. |
| `JwtReactiveAuthenticationManager` | `JwtAuthenticationProvider` trong luồng thường gặp | Biến Bearer JWT thành Authentication. |
| `ReactiveJwtDecoder` | `JwtDecoder` | `decode(String)` trả `Mono<Jwt>`. |
| `NimbusReactiveJwtDecoder` | `NimbusJwtDecoder` | Decoder JWT dùng Nimbus theo API reactive. |
| `ReactiveSecurityContextHolder` | `SecurityContextHolder` | Security context theo Reactor Context. |

Điểm thú vị: **`OAuth2TokenValidator<Jwt>` không phải một interface reactive**. Dù decoder trả `Mono<Jwt>`, validator claim thường được viết **đồng bộ**, nhận `Jwt` và trả một `OAuth2TokenValidatorResult`. Chính `ReactiveJwtDecoder` tích hợp bước validation vào pipeline.

## 3. OAuth2TokenValidator và OAuth2TokenValidatorResult

Một validator thực hiện **một chính sách**:

```java
public interface OAuth2TokenValidator<T extends OAuth2Token> {

    OAuth2TokenValidatorResult validate(T token);
}
```

Với JWT, dùng:

```java
OAuth2TokenValidator<Jwt> validator = jwt -> {
    // Kiểm tra claims/metadata của Jwt đã đến tầng validator.
    return OAuth2TokenValidatorResult.success();
};
```

Khi lỗi:

```java
return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
                "invalid_token",
                "Access token violates API contract",
                null));
```

`OAuth2TokenValidatorResult` có hai dạng:

- **Success**: token vượt qua **quy tắc cụ thể của validator này**.
- **Failure**: trả về một hay nhiều `OAuth2Error`, giúp decoder từ chối token qua cơ chế lỗi phù hợp.

Success **không chứng minh token hoàn toàn hợp lệ** nếu các lớp xác minh khác bị bỏ qua.

### 3.1. OAuth2Error không nên chứa thông tin nhạy cảm

Tránh:

```java
// SAI: đưa raw token hoặc chi tiết hạ tầng vào error description.
new OAuth2Error(
        "invalid_token",
        "Signature failed for token=" + rawToken
                + "; jwks=https://internal-idp/keys",
        null);
```

Thay bằng mô tả có tính phân loại:

```java
new OAuth2Error(
        "invalid_token",
        "Access token does not satisfy API requirements",
        null);
```

Tùy handler và phiên bản Spring Security, mô tả từ `OAuth2Error` có thể xuất hiện trong `WWW-Authenticate`. Với dữ liệu nội bộ, dùng mã lỗi/metric riêng, correlation ID và logging đã redaction.

### 3.2. Đừng dùng validator để “sửa” token

Validator **đánh giá**, không nên tự:

- Chuyển issuer chưa được tin cậy thành issuer hợp lệ.
- Ghi đè `aud` để khớp API hiện tại.
- Nâng `exp` hay bỏ `nbf` nếu token đã hết hạn/chưa có hiệu lực.
- Thêm scope `orders:admin` từ claim do client kiểm soát.
- Thay public key hoặc chấp nhận `alg=none` để token đi qua.

Nếu không đạt hợp đồng, **trả failure**. Nếu cần chuyển đổi định dạng claim hợp lệ theo profile của issuer, thiết kế một bước claim conversion riêng có giới hạn và phải giữ toàn bộ trust checks; không biến validation thành cơ chế cấp quyền tùy tiện.

## 4. Những kiểm tra nền tảng gồm những gì?

Trong Resource Server JWT thông dụng, có nhiều điều kiện tối thiểu:

| Điều kiện | Ví dụ hợp lệ | Nếu không đạt | Ai thường thực hiện? |
| --- | --- | --- | --- |
| Định dạng JWT/JWS | Compact JWS có header/payload/signature hợp lệ | Từ chối | Decoder / JOSE processor. |
| Chữ ký mật mã | JWS đúng với trusted key | Từ chối | Decoder. |
| Thuật toán phù hợp | Thuật toán JWS được cho phép rõ ràng | Từ chối | Decoder configuration. |
| Nguồn khóa | JWKS/public key từ issuer/trust config | Từ chối | Decoder/key selector. |
| `exp` | Token chưa quá thời hạn | Từ chối nếu đã hết hạn | Timestamp validator. |
| `nbf` | Token đã tới thời điểm có hiệu lực | Từ chối nếu chưa có hiệu lực | Timestamp validator. |
| `iss` | Trùng issuer được cấu hình | Từ chối | Issuer validator. |
| `aud` | Chứa identifier của Resource Server | Từ chối nếu sai | Audience validator/Boot config nếu được hỗ trợ. |
| Token type / profile | Access token phù hợp, không nhầm ID token | Từ chối theo profile | JOSE header validation và/hoặc token-profile validators. |
| Claims đặc thù | `tenant_id`, `client_id`, `scope` nếu hợp đồng yêu cầu | Từ chối theo contract | Custom validators. |

**Không phải tất cả mục trong bảng đều được tự động kiểm tra chỉ bằng một lệnh `createDefaultWithIssuer`.** Lệnh đó là nền tảng cho **các JWT claim checks mặc định và issuer**, nhưng không thay thế:

- Lựa chọn public key/JWKS và thuật toán ở decoder.
- Audience phù hợp Resource Server nếu chưa cấu hình.
- Bắt buộc phải có `exp`, `sub`, `client_id` hoặc `tenant_id` khi token profile riêng yêu cầu.
- Kiểm tra loại token (ví dụ OIDC ID token vs OAuth access token) theo phiên bản và chính sách.
- Policy về scope, owner/tenant và quyền nghiệp vụ.

### 4.1. Thời hạn: exp và nbf khác nhau

`exp` là thời điểm **không còn chấp nhận** token; `nbf` là thời điểm **chưa được phép sử dụng trước mốc đó**.

Ví dụ:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893456000
}
```

Các timestamp là **Unix epoch seconds**. Token có thể hợp lệ về chữ ký nhưng không hợp lệ theo thời gian.

`JwtTimestampValidator` cho phép **clock skew** hợp lý để xử lý lệch đồng hồ. Không tự thêm skew lớn tùy tiện vì sẽ làm tăng cửa sổ token quá hạn hoặc dùng trước thời điểm.

### 4.2. Issuer cần so sánh chính xác

Issuer identifier:

```text
https://login.example.test/realms/shop
```

Không coi các issuer sau là mặc nhiên tương đương:

```text
https://login.example.test/realms/shop/
https://login.example.test/realms/shop-admin
http://login.example.test/realms/shop
```

`iss` là một claim có ý nghĩa trust domain, không phải URL để API tùy ý chuẩn hóa, làm prefix matching hoặc gọi discovery tới bất kỳ host nào do token gửi lên.

### 4.3. Audience cần so khớp resource identifier

`aud` có thể là string hoặc array theo RFC 7519. Khi sử dụng Spring `Jwt.getAudience()`, ứng dụng có danh sách audience theo API của `Jwt`.

Ví dụ:

```json
{"aud": ["orders-api", "reporting-api"]}
```

Nếu API mong đợi `orders-api`, một chính sách **membership** có thể chấp nhận token này; một chính sách **single-audience** có thể từ chối token có nhiều resource. Chọn chính sách theo contract phát hành token, không theo cảm tính.

**Không dùng `String.contains("orders-api")` trên raw `aud`** vì `orders-api-admin` có thể gây nhầm, và JSON array không tương đương một chuỗi tùy ý.

## 5. JwtValidators.createDefault và createDefaultWithIssuer

Spring Security cung cấp những factory methods ở `JwtValidators`:

```java
OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefault();

OAuth2TokenValidator<Jwt> defaultsWithIssuer =
        JwtValidators.createDefaultWithIssuer(
                "https://login.example.test/realms/shop");
```

Khác biệt theo ý nghĩa:

| Factory | Mục đích | Khi dùng |
| --- | --- | --- |
| `JwtValidators.createDefault()` | Tạo tập JWT validators mặc định theo phiên bản Spring Security. | Khi issuer được kiểm tra ở lớp riêng **đã được thiết kế** hoặc khi ghép thêm issuer validator rõ ràng. |
| `JwtValidators.createDefaultWithIssuer(issuer)` | Giữ validators mặc định và bổ sung kiểm tra `iss` bằng issuer được tin cậy. | Lựa chọn thường phù hợp nhất khi Resource Server chỉ nhận token từ **một issuer xác định**. |

Trong các bản Spring Security thông dụng, validators mặc định bao gồm kiểm tra thời gian `exp`/`nbf` thông qua `JwtTimestampValidator`; thành phần mặc định khác có thể thay đổi theo phiên bản/token profile. Vì vậy, **không nên viết lại thủ công “đúng hai validation” rồi gọi đó là toàn bộ defaults**.

### 5.1. Vì sao cần chú ý version?

Tập mặc định trong `JwtValidators` có thể được mở rộng khi Spring Security hỗ trợ token-type validation hoặc quy tắc bảo mật mới. Nếu dự án tự viết:

```java
new DelegatingOAuth2TokenValidator<>(
        new JwtTimestampValidator(),
        new JwtIssuerValidator(issuer))
```

thì mặc dù hai validator có ích, nó không hứa tự đồng bộ mọi thay đổi của **`JwtValidators.createDefaultWithIssuer`** trong phiên bản framework bạn nâng cấp.

**Ưu tiên composition từ factory mặc định**, rồi thêm điều kiện đặc thù. Nếu tổ chức yêu cầu profile khác hoàn toàn, phải chứng minh các validation đã được thay thế tương đương và có test bao phủ.

### 5.2. Điều `createDefaultWithIssuer` không làm

Nó không:

- Ký access token.
- Lấy private key của Authorization Server.
- Biến JWT sai chữ ký thành hợp lệ.
- Bảo đảm token có audience của API nếu thiếu audience validator phù hợp.
- Xác minh quyền sở hữu đơn hàng, tenant membership hoặc scope nghiệp vụ.
- Chứng minh mọi token là **OAuth 2.0 access token** thay vì OIDC ID token nếu token-type/profile validation chưa được thiết lập.

Mỗi điều thuộc một trust boundary khác nhau.

## 6. Lỗi phổ biến: setJwtValidator làm mất nền tảng

Giả sử ứng dụng đã xây decoder:

```java
NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder
                .withIssuerLocation(ISSUER)
                .build();
```

Sau đó thêm custom audience:

```java
// CÓ RỦI RO: Thay validator hiện hành bằng đúng audience validator.
decoder.setJwtValidator(jwt ->
        jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Audience mismatch",
                                null)));
```

Nếu decoder không còn chạy timestamp/issuer validators do setter thay thế, một JWT:

```json
{
  "iss": "https://evil.example.test",
  "aud": ["orders-api"],
  "exp": 1609459200,
  "scope": "orders:read"
}
```

có thể vượt qua **riêng audience validator**, dù issuer sai hoặc expiry ở quá khứ. Một chữ ký giả vẫn phải bị JOSE layer từ chối, nhưng token được ký bởi key nằm trong trust config sai hoặc một token cũ được ký hợp lệ có thể trở thành vấn đề bảo mật nghiêm trọng.

**Không kết luận từ ví dụ rằng bất kỳ token `iss=evil.example.test` nào cũng được xác thực**: kết quả thực còn phụ thuộc trusted JWKS, thuật toán, token type và các validation khác của decoder. Vấn đề được minh họa là **đánh mất điều kiện claim cần thiết khi thay validator**, không phải khả năng tự tạo chữ ký hợp lệ.

### 6.1. Sửa bằng DelegatingOAuth2TokenValidator

```java
OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(ISSUER);

OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
        jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Access token is not for this API",
                                null));

decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                defaults,
                audienceValidator));
```

Như vậy, audience chỉ là một **điều kiện bổ sung**. Token phải qua **cả default/issuer validators và audience validator**.

### 6.2. Vì sao không tự gọi oldValidator.validate(...)?

Ví dụ custom:

```java
OAuth2TokenValidator<Jwt> composite = jwt -> {
    OAuth2TokenValidatorResult base = defaults.validate(jwt);
    if (base.hasErrors()) {
        return base;
    }
    return audienceValidator.validate(jwt);
};
```

Về ý tưởng có thể đúng nếu được cài đặt cẩn thận, nhưng `DelegatingOAuth2TokenValidator` đã là thành phần của Spring Security để tổng hợp validators và kết quả lỗi. Không cần viết thêm control flow, exception semantics hoặc cách gom errors khi không có yêu cầu đặc biệt.

## 7. Ví dụ WebFlux đầy đủ: ReactiveJwtDecoder giữ defaults, thêm audience và tenant

Giả sử hợp đồng của `orders-api`:

1. Chỉ chấp nhận token được cấp bởi issuer `https://login.example.test/realms/shop`.
2. JWT phải có chữ ký đáng tin, thuật toán nằm trong chính sách decoder.
3. Token không bị hết hạn và chưa vượt giới hạn `nbf`.
4. `aud` phải **chứa đúng** `orders-api`.
5. API multi-tenant yêu cầu `tenant_id` là chuỗi không rỗng có cú pháp dự kiến.
6. Những endpoint riêng yêu cầu scopes như `orders:read` và `orders:write`.

### 7.1. Cấu hình properties

```yaml
security:
  orders:
    issuer: https://login.example.test/realms/shop
    jwk-set-uri: https://login.example.test/realms/shop/protocol/openid-connect/certs
    audience: orders-api
```

Đây là các **application-specific properties minh họa**, không phải default keys `spring.security.*`. JWKS URL chỉ mang tính ví dụ; lấy đúng URL từ issuer metadata/tài liệu AS và kiểm soát TLS/trust.

### 7.2. Decoder và các validators

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class OrdersJwtDecoderConfiguration {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(
            @Value("${security.orders.issuer}") String issuer,
            @Value("${security.orders.jwk-set-uri}") String jwksUri,
            @Value("${security.orders.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder
                        .withJwkSetUri(jwksUri)
                        .build();

        OAuth2TokenValidator<Jwt> defaults =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> expectedAudience = jwt ->
                jwt.getAudience().contains(audience)
                        ? OAuth2TokenValidatorResult.success()
                        : failure("Unexpected audience");

        OAuth2TokenValidator<Jwt> tenantClaim = jwt -> {
            Object raw = jwt.getClaims().get("tenant_id");

            if (raw instanceof String value
                    && !value.isBlank()
                    && value.matches("[a-zA-Z0-9_-]{1,64}")) {
                return OAuth2TokenValidatorResult.success();
            }

            return failure("Invalid tenant claim");
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        defaults,
                        expectedAudience,
                        tenantClaim));

        return decoder;
    }

    private static OAuth2TokenValidatorResult failure(String reason) {
        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                        "invalid_token",
                        reason,
                        null));
    }
}
```

Trong ví dụ:

- `withJwkSetUri(jwksUri)` xác định trusted JWKS endpoint cho signature verification; riêng URI này **không có nghĩa đã bật issuer claim validator**.
- `JwtValidators.createDefaultWithIssuer(issuer)` giữ nhóm kiểm tra mặc định và yêu cầu `iss` khớp issuer.
- `expectedAudience` bổ sung kiểm tra `aud` chính xác bằng `List.contains`.
- `tenantClaim` là rule **đặc thù của ứng dụng**, không phải tiêu chuẩn JWT. Nếu workload token không có `tenant_id` theo hợp đồng, phải tạo policy khác thay vì bắt tất cả token có claim này.
- `DelegatingOAuth2TokenValidator` thực hiện tổng hợp các điều kiện.
- `setJwtValidator(...)` được gọi **một lần**, với **toàn bộ** validator chain dự kiến.

**Ví dụ không triển khai** kiểm tra ownership của từng đơn hàng; điều đó thuộc domain authorization.

### 7.3. Kết nối decoder vào SecurityWebFilterChain

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class OrdersSecurityConfiguration {

    @Bean
    SecurityWebFilterChain api(
            ServerHttpSecurity http,
            ReactiveJwtDecoder reactiveJwtDecoder) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:write")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
                        jwt.jwtDecoder(reactiveJwtDecoder)))
                .build();
    }
}
```

Hai cấu hình trên được dùng **cùng nhau**: bean decoder và WebFlux security chain. Khi API đã có bean `ReactiveJwtDecoder`, có thể để DSL dùng decoder bean được tự động phát hiện thay vì truyền tường minh; ở đây code explicit để người đọc thấy validator chain nào được sử dụng.

### 7.4. Nếu dùng Boot issuer-uri tự động thì sao?

Một cách ngắn gọn khi không cần decoder custom:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
```

Boot/Spring Security có thể auto-configure `ReactiveJwtDecoder` với validation phù hợp `issuer-uri`. Nhưng khi bạn **tạo bean decoder riêng**, cơ chế auto-configuration có thể **back off**; từ lúc đó, chính ứng dụng phải bảo đảm các validator được cấu hình đầy đủ.

Một số dòng Spring Boot có property hỗ trợ cấu hình JWT audience. Khi sử dụng property đó, phải xác nhận version và tác dụng khi decoder bean tùy chỉnh xuất hiện. **Không giả định properties issuer/audience sẽ được Boot “bí mật cộng thêm” vào custom decoder**.

## 8. Tổ chức validators thành factory dùng lại

Trong dự án lớn, logic validation không nhất thiết phải nằm toàn bộ trong `@Bean` method. Có thể định nghĩa một factory rõ hợp đồng:

```java
public final class OrdersJwtValidationPolicy {

    private OrdersJwtValidationPolicy() {
    }

    public static OAuth2TokenValidator<Jwt> build(
            String issuer,
            String audience) {

        OAuth2TokenValidator<Jwt> defaults =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> apiAudience = jwt ->
                jwt.getAudience().contains(audience)
                        ? OAuth2TokenValidatorResult.success()
                        : invalid();

        OAuth2TokenValidator<Jwt> subjectRequired = jwt ->
                jwt.getSubject() != null
                        && !jwt.getSubject().isBlank()
                        ? OAuth2TokenValidatorResult.success()
                        : invalid();

        return new DelegatingOAuth2TokenValidator<>(
                defaults,
                apiAudience,
                subjectRequired);
    }

    private static OAuth2TokenValidatorResult invalid() {
        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                        "invalid_token",
                        "JWT does not match the resource contract",
                        null));
    }
}
```

Sử dụng:

```java
decoder.setJwtValidator(
        OrdersJwtValidationPolicy.build(ISSUER, "orders-api"));
```

Ưu điểm:

- Mỗi decoder được tạo bằng **một chuỗi validator đã được định nghĩa tập trung**.
- Không ai vô tình gọi `setJwtValidator(audienceOnly)` trong một nhánh config khác.
- Unit test validation policy được tách khỏi network/JWKS.
- Multi-issuer/multi-resource có thể khởi tạo policy khác nhau theo trust domain.

**Không dùng một global static mutable validator/allowlist** mà tenant hoặc client HTTP có thể thay đổi. Policy phải nhận trusted configuration và không tin issuer/audience do token chưa xác minh đề nghị.

## 9. Nếu cần bắt buộc exp, sub hoặc một claim khác thì làm sao?

**“Kiểm tra timestamp mặc định” và “bắt buộc claim phải tồn tại” không phải luôn là cùng yêu cầu.** Theo token profile, một validator có thể kiểm tra `exp` khi claim hiện diện, nhưng profile riêng như JWT access token yêu cầu `exp` bắt buộc.

Ví dụ tạo validator yêu cầu `exp`:

```java
OAuth2TokenValidator<Jwt> expirationRequired = jwt ->
        jwt.getExpiresAt() != null
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Expiration is required",
                                null));
```

Nếu thêm yêu cầu `exp`, vẫn phải giữ `JwtValidators.createDefaultWithIssuer(...)` để **kiểm tra giá trị thời gian**. Chỉ thấy `exp` tồn tại không có nghĩa token chưa hết hạn.

Tương tự, có thể yêu cầu `sub`:

```java
OAuth2TokenValidator<Jwt> subjectRequired = jwt ->
        jwt.getSubject() != null
                && !jwt.getSubject().isBlank()
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Missing subject",
                                null));
```

### 9.1. Đừng bắt sub cho mọi client credentials token một cách máy móc

Trong OAuth 2.0, token dành cho **machine-to-machine (M2M)** có thể mang subject/actor theo hợp đồng khác với token đại diện người dùng. Một số profile JWT access token vẫn có `sub` nhưng ý nghĩa chủ thể phụ thuộc grant/client.

Trước khi yêu cầu `sub`, `tenant_id` hoặc `email_verified`, hãy xác định:

- Đây là token **đại diện end-user** hay **service/workload**?
- `sub` định danh user, client hay một thực thể trung gian?
- Issuer và token profile của token là gì?
- API có cho phép nhiều actor types trên cùng endpoint không?
- Claim cần thiết để cấp quyền ở resource này là gì?

**Validator sai contract có thể từ chối token hợp lệ**, còn validator quá lỏng có thể tạo privilege escalation. Hai rủi ro đều cần được quản lý qua test.

### 9.2. Không yêu cầu email để thay thế subject

Claim `email`, `name` và `preferred_username` thường có thể thay đổi. Không dùng email làm khóa user ổn định nếu chưa có hợp đồng. Với nhiều issuers, external identity thường cần được ràng buộc với **issuer đã xác minh và subject**, rồi ánh xạ sang internal user ID.

## 10. JwtClaimValidator: tiện nhưng phải dùng đúng

Spring Security cung cấp `JwtClaimValidator<T>` để kiểm tra một claim bằng predicate.

Ví dụ:

```java
JwtClaimValidator<String> tenantValidator =
        new JwtClaimValidator<>(
                "tenant_id",
                tenant -> tenant != null
                        && !tenant.isBlank()
                        && tenant.matches("[a-zA-Z0-9_-]{1,64}"));
```

Mẫu này thuận tiện khi bạn **biết kiểu dữ liệu claim** đã được decoder/claim conversion chuyển thành và có contract rõ. Trong hệ thống cần từ chối JSON number/object/list ở claim `tenant_id`, custom validator kiểm tra `raw instanceof String` có thể dễ quan sát hơn.

### 10.1. Không nới lỏng types tùy tiện

Ví dụ issuer cam kết:

```json
{
  "tenant_id": "tenant-a"
}
```

Không mặc định nhận:

```json
{"tenant_id": 123}
```

hoặc:

```json
{"tenant_id": {"value": "tenant-a"}}
```

rồi gọi `toString()` để tạo một định danh tenant hợp lệ. Với claims dùng để phân quyền, **kiểu JSON là một phần contract**.

### 10.2. Claim conversion là một bước riêng

Một `JwtDecoder` có thể sử dụng claim set converter để chuẩn hóa kiểu claim tiêu chuẩn như timestamp hoặc audience. Nếu application tự tùy chỉnh claim conversion, cần giữ các quy tắc an toàn:

- Không thay `iss`/`aud` bằng giá trị mà API mong đợi.
- Không biến user-supplied claim không tin cậy thành role có quyền cao.
- Không xóa `exp`/`nbf` trước khi validator đánh giá.
- Không gộp claims từ nhiều nguồn mà chưa có precedence rõ ràng.

**Chuyển kiểu dữ liệu có hợp đồng** khác với **tự sửa token để vượt validation**.

## 11. Cẩn thận với clock skew

Đồng hồ của Resource Server và Authorization Server có thể lệch một ít. `JwtTimestampValidator` hỗ trợ **clock skew**, mặc định thông dụng khoảng **60 giây** trong một số dòng Spring Security. Việc dùng lệch đồng hồ phải dựa vào **version và policy**.

Ví dụ nếu có yêu cầu tùy chỉnh skew:

```java
JwtTimestampValidator timestamps =
        new JwtTimestampValidator(Duration.ofSeconds(30));
```

Không làm:

```java
// SAI: skew quá rộng có thể chấp nhận token hết hạn lâu.
new JwtTimestampValidator(Duration.ofDays(365));
```

### 11.1. Thay clock skew nhưng vẫn giữ mặc định có mâu thuẫn không?

Nếu dùng:

```java
new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        new JwtTimestampValidator(Duration.ofSeconds(30)))
```

thì có thể đang chạy **hai timestamp validators**: một của defaults và một với skew 30 giây. Nếu hai validator khác threshold, token phải vượt **cả hai**. Điều này **không có nghĩa bạn đã thay cấu hình skew của default validator**.

Khi thực sự cần thay clock skew, phải thiết kế bộ nền tảng **tương đương và nhất quán theo framework version**, hoặc sử dụng configuration/extension point được version đó hỗ trợ. Đừng bỏ defaults chỉ vì muốn thay một thông số; nếu bắt buộc thay, phải nhận diện rõ các validators nền tảng nào cần giữ và kiểm thử đầy đủ.

### 11.2. Không tự dựa vào thời gian của client

`exp`, `iat` và `nbf` là claims do issuer phát hành. Không cho HTTP client gửi `X-Current-Time` để Resource Server tin là thời gian thực khi validation. Trong test, có thể dùng fixed `Clock` hoặc token có timestamps được tính tương đối, nhưng production phải dựa trên clock đáng tin của hệ thống.

## 12. JWT access token khác OIDC ID token

Trong một hệ thống dùng OpenID Connect:

- **ID token** chứng minh sự kiện xác thực user đối với **OIDC client**, thường có `aud` là **client ID**.
- **OAuth 2.0 access token** là credential được **Resource Server** kiểm tra để cho phép truy cập API, với issuer/resource/scope contract khác.

Chỉ xác minh chữ ký và `iss` là **chưa đủ** để biến ID token thành access token hợp lệ cho API. Ví dụ:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "aud": "web-client-id",
  "sub": "user-123",
  "exp": 1893456000
}
```

Token trên có thể đúng là ID token dành cho OIDC client. `orders-api` cần kiểm tra `aud` hoặc cơ chế resource binding theo hợp đồng để từ chối.

### 12.1. typ và RFC 9068

Nếu issuer áp dụng **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens**, token thường có JOSE header `typ` chỉ ra access-token profile, chẳng hạn `at+jwt` theo quy tắc chuẩn. Type validation liên quan đến **header và decoder**, không chỉ claim payload.

Điểm cần nhớ:

- Cách Spring Security/Nimbus kiểm tra `typ` mặc định **phụ thuộc phiên bản và decoder builder**.
- Có các API/validators hỗ trợ type validation ở một số phiên bản mới; phải đối chiếu Javadoc của version thực tế.
- Nếu phiên bản cho phép tắt type verification tại JOSE layer để dùng validator profile riêng, **chỉ làm khi validator thay thế được cấu hình tường minh**, có test đúng/sai loại token; không đơn giản tắt kiểm tra rồi bỏ qua.
- `JwtValidators.createDefaultWithIssuer` không thay cho một **token-profile policy đầy đủ** trong mọi hệ thống.

**Không nên đặt `typ=JWT`, `typ=at+jwt` hoặc không có `typ` ngang nhau** nếu issuer contract yêu cầu phân biệt access token với ID token.

### 12.2. Profile yêu cầu claim nào?

RFC 9068 có các điều kiện về issuer, subject, audience, expiry, client ID và scope trong ngữ cảnh thích hợp. Nhưng không phải JWT access token nào cũng tuyên bố tuân theo RFC 9068. Trước khi áp đặt validator:

1. Xác nhận AS phát token theo profile nào.
2. Xác nhận Resource Server chấp nhận token profile nào.
3. Xác định những claims nào là bắt buộc.
4. Chọn decoder/header validators tương ứng.
5. Dùng negative test với ID token, token sai `typ`, sai `aud` và thiếu mandatory claim.

## 13. Các failure modes khi thay decoder bean hoặc cấu hình DSL

### 13.1. Bean tùy chỉnh làm Boot lùi bước

Khi dự án chỉ có:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
```

Boot có thể tạo decoder theo issuer metadata. Nhưng khi thêm:

```java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    return NimbusReactiveJwtDecoder
            .withJwkSetUri("https://login.example.test/keys")
            .build();
}
```

ứng dụng đã tự sở hữu cấu hình decoder. Nếu thiếu `JwtValidators.createDefaultWithIssuer(...)`, validator issuer mà bạn tưởng từ properties có thể **không được áp dụng** cho bean này.

### 13.2. DSL ghi đè decoder của bean

Một chain có thể gọi tường minh:

```java
.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(jwt -> jwt.jwtDecoder(customDecoder)))
```

Trong trường hợp đó, phải kiểm tra **customDecoder** có đúng validator chain hay không; chỉ kiểm tra một bean `ReactiveJwtDecoder` khác trong context không chứng minh chain đang sử dụng nó.

### 13.3. Sai JWKS URI

Sử dụng `withJwkSetUri(uri)` chỉ xác định nguồn khóa, không chứng minh issuer claim đúng. Có thể có nhiều tenants/issuers dùng chung một endpoint hoặc cùng public key material. Luôn ràng buộc trust domain theo issuer **và** audience khi contract yêu cầu.

### 13.4. Tạo decoder theo iss do token chưa xác minh

Không làm:

```java
// SAI: attacker tự đưa URL issuer vào payload chưa được xác minh.
String iss = parseUnverifiedPayload(token).get("iss").toString();
ReactiveJwtDecoder decoder =
        ReactiveJwtDecoders.fromIssuerLocation(iss);
```

Điều này có nguy cơ SSRF và nhận keys từ bên không tin cậy. Với multi-issuer, dùng allowlist issuer rõ ràng và resolver được thiết kế đúng; sau khi chọn decoder, **vẫn phải xác minh chữ ký, issuer và audience**.

## 14. Multi-issuer trong WebFlux: mỗi issuer cần defaults và policy riêng

Giả sử API chấp nhận:

```text
Issuer A = https://idp-a.example.test/issuer
Issuer B = https://idp-b.example.test/issuer
```

Spring Security có `JwtIssuerReactiveAuthenticationManagerResolver` để chọn reactive authentication manager từ tập issuers được tin cậy:

```java
JwtIssuerReactiveAuthenticationManagerResolver resolver =
        JwtIssuerReactiveAuthenticationManagerResolver
                .fromTrustedIssuers(
                        "https://idp-a.example.test/issuer",
                        "https://idp-b.example.test/issuer");
```

Resolver có thể đọc `iss` trước khi token được xác minh để **chọn ứng viên**, nhưng dữ liệu chưa xác minh **không phải bằng chứng về issuer**. Sau khi chọn, decoder cần xác minh chữ ký và issuer tương ứng.

### 14.1. Audience khác nhau theo issuer

Nếu:

```text
Issuer A -> aud = orders-api
Issuer B -> aud = https://api.example.test/orders
```

thì không thể mặc định dùng một audience literal cho mọi issuer. Cần policy theo từng issuer/resource:

```text
Trusted issuer A
    -> trusted JWKS A
    -> JwtValidators.createDefaultWithIssuer(A)
    -> audience validator "orders-api"

Trusted issuer B
    -> trusted JWKS B
    -> JwtValidators.createDefaultWithIssuer(B)
    -> audience validator "https://api.example.test/orders"
```

Một resolver mặc định chỉ chọn issuer đáng tin **không có nghĩa nó đã tự thêm audience validators tùy chỉnh**. Nếu có yêu cầu nhiều audience, phải kiểm tra cách cấu hình managers/decoders mà resolver thực sự tạo và bổ sung chính sách riêng theo extension point phù hợp.

### 14.2. Không “union” quyền từ các nguồn khác nhau

Issuer A có `scope="orders:read"`, issuer B có `scp=["orders.read"]`. Không tự coi `orders.read` là `orders:read` hoặc cấp `ROLE_ADMIN` nếu chưa có hợp đồng ánh xạ. Validator kiểm tra token profile, converter ánh xạ authorities theo issuer/client contract, còn domain authorization kiểm tra owner/tenant.

## 15. Negative tests: những token phải bị từ chối

Một **test matrix** giúp phát hiện việc setter làm mất validator nền tảng:

| Test token | Chữ ký JWS | Claims quan trọng | Kỳ vọng authentication |
| --- | --- | --- | --- |
| Token hợp lệ | Đúng, trusted key | `iss` đúng, `aud` đúng, `exp` tương lai, `nbf` hợp lệ | Thành công. |
| Token hết hạn | Đúng, trusted key | `exp` quá khứ đủ xa ngoài clock skew | **Từ chối**. |
| Token chưa có hiệu lực | Đúng, trusted key | `nbf` ở tương lai đủ xa ngoài clock skew | **Từ chối**. |
| Token sai issuer | Đúng theo trust test setup | `iss` không khớp issuer cho API | **Từ chối**. |
| Token sai audience | Đúng | `aud=["payments-api"]` | **Từ chối**. |
| Token thiếu audience khi contract bắt buộc | Đúng | Không có `aud` | **Từ chối**. |
| Token có audience gần giống | Đúng | `aud=["orders-api-admin"]` | **Từ chối**. |
| Token sai chữ ký | Sai hoặc key không trusted | Các claims khác đúng | **Từ chối ở decoder**. |
| Token `alg=none` | Không có JWS signature hợp lệ | Các claims trông đúng | **Từ chối**. |
| Token thiếu mandatory `exp` theo profile | Đúng | Không có `exp` | **Từ chối nếu contract yêu cầu**. |
| Token sai tenant | Đúng | `tenant_id` sai kiểu/format | **Từ chối theo custom policy**. |
| OIDC ID token gửi thay access token | Có thể đúng | `aud=client-id`, type/profile không đúng | **Từ chối**. |
| Token đúng auth nhưng thiếu scope | Đúng | Không có `orders:read` | Authentication có thể thành công; endpoint **403**. |

Một test negative chỉ có giá trị khi biết **đường nào đang được thử**:

- Unit test validator chứng minh hàm kiểm tra claims.
- Unit test decoder chứng minh wiring validator/JOSE signature với decoder thật hoặc test double có kiểm soát.
- WebFlux integration test chứng minh HTTP Bearer filter, decoder, authorization và response.

Không dùng `mockJwt()` rồi tuyên bố đã kiểm tra chữ ký, `exp` hoặc `iss`.

## 16. Unit test validator bằng JUnit: kết hợp defaults với audience

Có thể kiểm thử policy factory **không cần** HTTP server hay Spring context.

Ví dụ JUnit Jupiter (giả định `OrdersJwtValidationPolicy` từ mục 8):

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;

class OrdersJwtValidationPolicyTest {

    private static final String ISSUER =
            "https://login.example.test/realms/shop";

    private final OAuth2TokenValidator<Jwt> policy =
            OrdersJwtValidationPolicy.build(
                    ISSUER, "orders-api");

    private Jwt jwt(
            String issuer,
            String audience,
            Instant expiration,
            Instant notBefore) {

        Instant now = Instant.now();
        return Jwt.withTokenValue("unit-test-only")
                .header("alg", "RS256")
                .issuer(issuer)
                .subject("user-123")
                .audience(List.of(audience))
                .issuedAt(now.minusSeconds(10))
                .notBefore(notBefore)
                .expiresAt(expiration)
                .build();
    }

    @Test
    void acceptsValidClaims() {
        Instant now = Instant.now();
        assertTrue(policy.validate(jwt(
                ISSUER, "orders-api",
                now.plusSeconds(300),
                now.minusSeconds(10))).getErrors().isEmpty());
    }

    @Test
    void rejectsExpiredTokenEvenWhenAudienceMatches() {
        Instant now = Instant.now();
        assertFalse(policy.validate(jwt(
                ISSUER, "orders-api",
                now.minusSeconds(3600),
                now.minusSeconds(7200))).getErrors().isEmpty());
    }

    @Test
    void rejectsNotYetValidToken() {
        Instant now = Instant.now();
        assertFalse(policy.validate(jwt(
                ISSUER, "orders-api",
                now.plusSeconds(7200),
                now.plusSeconds(3600))).getErrors().isEmpty());
    }

    @Test
    void rejectsWrongIssuerEvenWhenAudienceMatches() {
        Instant now = Instant.now();
        assertFalse(policy.validate(jwt(
                "https://another.example.test/issuer", "orders-api",
                now.plusSeconds(3600),
                now.minusSeconds(10))).getErrors().isEmpty());
    }

    @Test
    void rejectsWrongAudienceEvenWithValidTimeAndIssuer() {
        Instant now = Instant.now();
        assertFalse(policy.validate(jwt(
                ISSUER, "payments-api",
                now.plusSeconds(3600),
                now.minusSeconds(10))).getErrors().isEmpty());
    }
}
```

Đây là **unit test của `OAuth2TokenValidator`**. Token `unit-test-only` không có JWS signature; `Jwt.withTokenValue(...)` chỉ tạo object trong bộ nhớ. Unit test không chứng minh `NimbusReactiveJwtDecoder` đã xác minh chữ ký hoặc đã được cấu hình `setJwtValidator(policy)`.

### 16.1. Một test “bắt lỗi mất defaults”

Nếu ai đó sửa factory thành:

```java
return audienceValidator; // SAI: bỏ defaults và issuer.
```

thì test `rejectsExpiredTokenEvenWhenAudienceMatches`, `rejectsNotYetValidToken` và `rejectsWrongIssuerEvenWhenAudienceMatches` sẽ thất bại. Đây là giá trị của **negative tests bảo vệ invariants**, không chỉ test token hợp lệ.

### 16.2. Dùng clock cố định nếu test đòi ranh giới giây

Test ở ví dụ dùng `Instant.now()` và độ lệch vài phút/giờ để tránh phụ thuộc sát clock skew. Khi phải kiểm thử đúng ranh giới `exp`/`nbf`, dùng `Clock.fixed(...)` với timestamp validator có extension point phù hợp phiên bản, hoặc thiết kế test fixture tiêm clock. Không assert một token hết hạn **1 mili-giây** luôn bị từ chối khi validator cho phép clock skew.

## 17. Test reactive decoder bằng StepVerifier

`ReactiveJwtDecoder.decode(String)` trả `Mono<Jwt>`. `StepVerifier` giúp kiểm tra kết quả hoặc lỗi:

```java
Mono<Jwt> decoded = reactiveJwtDecoder.decode(signedTestJwt);

StepVerifier.create(decoded)
        .expectNextMatches(jwt ->
                "user-123".equals(jwt.getSubject())
                && jwt.getAudience().contains("orders-api"))
        .verifyComplete();
```

Với token không hợp lệ:

```java
StepVerifier.create(
        reactiveJwtDecoder.decode(signedExpiredTestJwt))
        .expectError(JwtException.class)
        .verify();
```

Để test có ý nghĩa bảo mật, `signedTestJwt` và `signedExpiredTestJwt` phải là JWS được ký bằng **test private key** tương ứng trusted public key/JWKS của decoder test. Không dùng token production/private key production.

### 17.1. Tạo decoder test với trusted public key

Ví dụ khung:

```java
RSAPublicKey publicKey = /* public key của test key pair */;

NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder
                .withPublicKey(publicKey)
                .build();

decoder.setJwtValidator(
        OrdersJwtValidationPolicy.build(
                "https://issuer.test", "orders-api"));
```

Ở đây key pair chỉ dành cho test; JWT test phải được ký bằng private key tương ứng. Khi `JwtDecoder` dùng public key trực tiếp, test loại bỏ biến số HTTP/JWKS, tập trung vào **chữ ký + claims + validator wiring**.

### 17.2. Kiểm tra một lỗi chữ ký khác lỗi claims

Hai trường hợp cần tách:

1. JWS signature sai nhưng `iss`/`aud`/`exp` trong payload trông hợp lệ → bị từ chối ở JOSE verification.
2. JWS signature đúng nhưng `exp` hết hạn hoặc `aud` sai → bị từ chối ở claim validation.

Nếu chỉ test nhóm thứ nhất, ứng dụng vẫn có thể mắc lỗi **setJwtValidator(audienceOnly)** mà không bị phát hiện.

### 17.3. Đừng test bằng decoder lambda luôn thành công

```java
ReactiveJwtDecoder fake = token ->
        Mono.just(jwtFixture);
```

Fake có thể hữu ích khi kiểm tra `JwtReactiveAuthenticationManager` chuyển `Jwt` thành `Authentication`, nhưng nó **bỏ qua tất cả cơ chế decoder thật**, gồm signature và validators. Không thể dùng fake đó để kết luận JWT security cấu hình đúng.

## 18. WebTestClient: kiểm tra HTTP 401 và 403

Một ứng dụng WebFlux có endpoint:

```java
@RestController
class OrderController {

    @GetMapping("/api/orders")
    public Flux<OrderDto> listOrders() {
        return orderService.listVisibleOrders();
    }
}
```

Giả sử `SecurityWebFilterChain` yêu cầu `SCOPE_orders:read`. Kiểm thử cần phân biệt:

| Điều kiện | Authentication | Authorization | HTTP thường gặp |
| --- | --- | --- | --- |
| Không có token | Không có principal được xác thực | Endpoint cần quyền | **401**. |
| Token JWT sai chữ ký | Thất bại | Không vào domain | **401 invalid_token**. |
| Token JWT hết hạn | Thất bại nếu defaults còn được áp dụng | Không vào domain | **401 invalid_token**. |
| Token JWT sai issuer | Thất bại | Không vào domain | **401 invalid_token**. |
| Token JWT sai audience | Thất bại | Không vào domain | **401 invalid_token**. |
| Token JWT đúng issuer/aud/time nhưng thiếu scope `orders:read` | Thành công | Thiếu authority | **403 Forbidden**. |
| Token JWT hợp lệ, có scope `orders:read` | Thành công | Qua URL rule | 2xx nếu domain xử lý thành công. |
| Token hợp lệ, đủ scope nhưng khác owner/tenant | Thành công | Domain policy từ chối | **403/404** theo API contract. |

### 18.1. Unit HTTP authorization với mockJwt()

Spring Security Test hỗ trợ:

```java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

webTestClient.mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders:read")))
        .get().uri("/api/orders")
        .exchange()
        .expectStatus().isOk();

webTestClient.mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders:write")))
        .get().uri("/api/orders")
        .exchange()
        .expectStatus().isForbidden();
```

Đây là **test authorization**: `mockJwt()` tạo Authentication mô phỏng. Nó **không chứng minh** `ReactiveJwtDecoder` hoặc `OAuth2TokenValidator` đã chạy.

### 18.2. Full integration qua Bearer JWS thật

Để xác minh việc giữ defaults:

1. Tạo RSA/EC test keys và JWT encoder test.
2. Cấu hình `NimbusReactiveJwtDecoder` thật dùng test public key/JWKS.
3. Gắn composite `JwtValidators.createDefaultWithIssuer + audience + custom` như production.
4. Gửi HTTP `Authorization: Bearer <signed-test-JWS>` qua WebTestClient với WebFlux security filters.
5. Test **JWS đúng nhưng expired** → 401.
6. Test **JWS đúng nhưng `nbf` tương lai** → 401.
7. Test **JWS đúng nhưng `iss` sai** → 401.
8. Test **JWS đúng nhưng `aud` sai** → 401.
9. Test **JWS đúng nhưng thiếu `SCOPE_orders:read`** → 403.
10. Test **JWS đúng, tất cả claims hợp lệ, đủ scope** → endpoint xử lý thành công.

Nếu dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)`, hãy sử dụng WebTestClient/live HTTP đúng mode test. Với `bindToApplicationContext` cần apply `springSecurity()` theo hướng dẫn Spring Security Test. Không nhầm HTTP mock user/JWT với test đi qua decoder thật.

## 19. Lỗi 401, 403 và thông tin nên công khai

Với Bearer Resource Server:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

hoặc:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Các header là ví dụ điển hình; Spring Security handler, realm và trường hợp error cụ thể có thể tạo kết quả hơi khác.

**Không trả toàn bộ validator errors** ra client. Một lỗi issuer mismatch không cần tiết lộ danh sách issuer nội bộ. Lỗi audience mismatch không cần tiết lộ tenant/resource khác. Một `JwtValidationException` có thể chứa nhiều errors; telemetry nội bộ nên phân loại nguyên nhân với redaction.

### 19.1. Lỗi JWKS unavailable khác token hết hạn

Khi JWKS endpoint lỗi network/TLS hoặc key cache không chứa `kid` mới, Resource Server có thể không xác minh được token. **Không fail-open**. Tuy nhiên cần phân biệt trong vận hành:

- `JWT_EXPIRED`: token có chữ ký hợp lệ nhưng hết hạn.
- `JWT_ISSUER_INVALID`: claims không khớp issuer.
- `JWT_AUDIENCE_INVALID`: resource mismatch.
- `JWKS_DEPENDENCY_UNAVAILABLE`: không lấy được metadata/keys đáng tin.
- `JWT_SIGNATURE_INVALID`: chữ ký không hợp lệ.

Đừng coi mọi lỗi network là hành vi người dùng gửi token giả. Mã HTTP cụ thể khi dependency unavailable phụ thuộc handler; có thể cần thiết kế phản hồi 5xx/503 an toàn mà vẫn fail-closed.

### 19.2. Không echo raw token, kid hoặc JWKS URI

Tránh:

```java
new OAuth2Error(
        "invalid_token",
        "Invalid " + jwt.getTokenValue()
                + " at jwks=" + internalJwksUrl,
        null);
```

Nếu lỗi cần theo dõi, dùng correlation ID và category đã chuẩn hóa. `kid` từ JOSE header trước verify là dữ liệu caller có thể kiểm soát; không dùng tự do làm metric label vì nguy cơ tăng cardinality.

## 20. Vấn đề hiệu năng riêng của WebFlux

`OAuth2TokenValidator<Jwt>` là contract đồng bộ. Khi áp dụng trong `ReactiveJwtDecoder`, logic của validator cần **nhanh, deterministic và không blocking**.

### 20.1. Không truy vấn database trong validate()

```java
// SAI: synchronous DB call trong validator WebFlux.
OAuth2TokenValidator<Jwt> validator = jwt -> {
    boolean allowed =
            jdbcTemplate.queryForObject(
                    "select ...", Boolean.class);
    return allowed
            ? OAuth2TokenValidatorResult.success()
            : failure();
};
```

Đoạn này có thể chặn thread thực thi reactive pipeline. Không nên truy vấn DB, gọi HTTP, đọc file secrets lớn hoặc dùng `Thread.sleep` trong `validate`.

### 20.2. Nếu cần quyền động theo tenant hoặc user

Tách hai nhiệm vụ:

1. **JWT validation**: các quy tắc ổn định như chữ ký, issuer, audience, exp/nbf, token type/profile, cú pháp claim.
2. **Reactive authorization**: truy vấn actor/tenant permissions qua reactive repository hoặc custom reactive authorization manager/service policy.

Ví dụ:

```java
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
public Mono<OrderDto> getOrder(UUID orderId) {
    return currentActorReactiveService.getActor()
            .flatMap(actor -> orders
                    .findByIdAndOwnerIdAndTenantId(
                            orderId,
                            actor.userId(),
                            actor.tenantId()))
            .map(OrderDto::from);
}
```

Các kiểu domain trong ví dụ phải do ứng dụng định nghĩa; `@PreAuthorize` trong WebFlux cần **`@EnableReactiveMethodSecurity`** và method invocation đi qua Spring proxy. Quyền truy cập đối tượng nên giới hạn ngay trong query, không tin `tenant_id` từ HTTP request.

**Không đặt I/O blocking trong `JwtClaimValidator` rồi nghĩ `Mono` ở phía ngoài sẽ tự biến thành non-blocking.**

## 21. Khi nào cần thay một kiểm tra nền tảng thực sự?

Đôi khi doanh nghiệp có chính sách đặc biệt:

- Clock skew phải nhỏ hơn default.
- Chỉ nhận token có `exp` bắt buộc.
- Cấm token phát hành với thời hạn hiệu lực quá dài.
- Yêu cầu `iat` không được nằm quá xa trong tương lai.
- Profile access token phải có `typ` và `client_id` phù hợp.
- Chỉ cho phép một số issuer/resource audiences theo migration.

Nhưng **tùy chỉnh khác với vô hiệu hóa bảo mật**.

### 21.1. Ví dụ giới hạn lifetime

Một token có `exp` trong tương lai rất xa có thể vẫn qua timestamp validator, nhưng API có hợp đồng access token chỉ tồn tại tối đa một giờ.

```java
OAuth2TokenValidator<Jwt> maxLifetime = jwt -> {
    Instant issuedAt = jwt.getIssuedAt();
    Instant expiresAt = jwt.getExpiresAt();

    if (issuedAt == null || expiresAt == null) {
        return failure("Missing token lifetime");
    }

    Duration lifetime = Duration.between(issuedAt, expiresAt);

    if (lifetime.isNegative()
            || lifetime.compareTo(Duration.ofHours(1)) > 0) {
        return failure("Token lifetime violates API policy");
    }

    return OAuth2TokenValidatorResult.success();
};
```

Đây là **custom policy tùy chọn**. Nếu AS có chính sách lifetime khác, không áp đặt một giờ một cách máy móc. Điều quan trọng là dùng nó **cùng** defaults:

```java
decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audience,
                maxLifetime));
```

Ngay cả lifetime đúng vẫn không đủ nếu JWS signature hoặc audience sai.

### 21.2. Custom nbf/exp không được xóa kiểm tra khác

Nếu cần thiết kế lại timestamp validation do policy khác, phải liệt kê **toàn bộ các bảo đảm đang có** và cách tái tạo chúng trong phiên bản framework. Không làm:

```java
// SAI: chỉ giữ iat custom và mất default temporal/issuer checks.
decoder.setJwtValidator(customIssuedAtValidator);
```

Thiết kế lại một baseline validator là quyết định security architecture, không phải một thay đổi nhỏ để “fix test expired token”.

## 22. Troubleshooting các lỗi JWT validation trong WebFlux

| Triệu chứng | Nguyên nhân có thể | Hướng xác định |
| --- | --- | --- |
| JWT có `aud` đúng nhưng đã hết hạn vẫn được nhận | `setJwtValidator(audienceOnly)` làm mất timestamp defaults. | Kiểm tra composite validator đã gắn; thêm negative test expired. |
| JWT đúng chữ ký, `iss` sai vẫn pass | Dùng `withJwkSetUri` nhưng quên issuer validator, hoặc custom validator thay defaults. | Xác nhận `createDefaultWithIssuer` và decoder mà chain thực sự dùng. |
| Token không hết hạn nhưng bị 401 | Sai audience, issuer, typ/profile, `nbf` hoặc key/algorithm. | Kiểm tra từng phase ở logs nội bộ, không đổ lỗi mặc định cho `exp`. |
| JWT có `aud=["orders-api"]` nhưng API vẫn 401 | Audience literal cấu hình khác, role/scope không liên quan đến authentication, hoặc decoder chưa trust signature. | So contract chính xác, verify JWS và audience validation. |
| Token còn hạn 30 giây nhưng không pass test | Clock skew/clock timing không như dự đoán hoặc token có claim khác sai. | Dùng test clock và test claims tách biệt. |
| Test `mockJwt()` pass nhưng production 401 | Mock bypass decoder và validators. | Gửi signed JWT thật qua WebTestClient. |
| Custom `ReactiveJwtDecoder` bean làm issuer-uri property “không còn tác dụng” | Boot back off; app phải tự cấu hình issuer validator. | Kiểm tra bean/DSL, không chỉ nhìn YAML. |
| Có hai decoders trong context, cấu hình nào chạy? | DSL chọn decoder khác bean đã kiểm thử. | Xác định `jwtDecoder(...)` và security chain matcher thực tế. |
| JWT sai `kid` gây nhiều calls tới JWKS | Cache miss, key rotation hoặc đầu vào độc hại. | Kiểm tra trusted JWKS, refresh policy, rate limiting, metrics. |
| Authenticated nhưng request 403 | Scope/authority không đủ hoặc domain policy từ chối. | Kiểm tra `SCOPE_...` mapping và ownership; đừng sửa JwtValidator để cấp quyền. |
| Validator có JDBC call làm API chậm | Blocking I/O trong reactive request path. | Chuyển kiểm tra quyền động sang reactive authorization/service. |
| ID token được API chấp nhận như access token | Thiếu audience/type/profile validation. | Phân biệt OIDC client audience và Resource Server audience, test typ/token profile. |

### 22.1. Kiểm tra đúng đường chạy, không chỉ đúng code

Khi gặp lỗi, cần xác định:

1. Request thực vào **SecurityWebFilterChain** nào?
2. Chain dùng **ReactiveJwtDecoder** bean nào?
3. Decoder lấy keys từ issuer/JWKS nào?
4. `setJwtValidator` được gọi bao nhiêu lần, và với validator composite nào?
5. Các defaults/issuer checks có nằm trong composite không?
6. Audience/token type/profile có được kiểm tra không?
7. Sau authentication, authorities được map thành gì?
8. Endpoint/method/domain policy yêu cầu những quyền nào?

Không sửa bảo mật theo triệu chứng HTTP 401 mà chưa biết đã fail ở chữ ký, claim hay dependency.

## 23. Một số tình huống thiết kế

### A. Chỉ thêm audience cho API mới

API trước đây xác minh token qua `issuer-uri`. Khi bổ sung `aud=orders-api`, cấu hình validator phải **giữ defaults + issuer**, rồi thêm audience. Test expired/nbf/iss vẫn phải pass theo nghĩa **bị từ chối**.

### B. Một issuer có nhiều APIs

Issuer cấp token cho `orders-api` hoặc `payments-api`. Hai APIs có thể dùng cùng JWKS nhưng phải kiểm tra **audience riêng**. Không vì chữ ký hợp lệ từ cùng issuer mà chấp nhận token của API khác.

### C. M2M token không có tenant_id

Custom tenant validator bắt `tenant_id` cho mọi JWT có thể từ chối một workload token hợp lệ. Giải pháp không phải xóa issuer/exp validators; cần **token profile hoặc authentication/authorization policy riêng cho service actor** và bảo đảm không có đường leo thang quyền.

### D. OIDC ID token bị nhầm thành access token

ID token có thể đúng chữ ký, issuer và thời hạn, nhưng `aud` là `web-client-id`. Resource Server phải kiểm tra audience/typ/profile để không dùng ID token cấp quyền API.

### E. JWT hết hạn lọt qua sau một refactor

Developer thay `setJwtValidator(composite)` bằng `setJwtValidator(custom)` để giảm code. Token expired có chữ ký hợp lệ có thể không còn bị timestamp validator chặn. Negative tests ở unit và decoder integration cần phát hiện regression.

### F. Sai issuer khi có multi-tenant Identity Provider

JWT từ tenant A không thể dùng ở tenant B chỉ vì có cùng public key hoặc audience giống. Decoder cho mỗi tenant cần kiểm tra issuer đúng trust domain và policy tenant/account linking.

### G. JWKS server tạm thời mất mạng

Token mới cần key chưa có trong cache, decoder không xác minh được JWS. Không bỏ signature verification hoặc tạo principal tạm thời. Quan sát lỗi dependency, có cache key metadata và runbook key rotation an toàn.

### H. Token hợp lệ nhưng user không có quyền đọc order

JwtValidators đều success, token có `SCOPE_orders:read`, nhưng `orderId` thuộc người khác. Domain authorization vẫn phải từ chối; validator chỉ kiểm tra access-token contract, không thay quyền trên từng object.

## 24. Câu hỏi tự kiểm tra

**1. `OAuth2TokenValidator<Jwt>` có xác minh chữ ký JWS không?** Không. Chữ ký/thuật toán/khóa tin cậy thuộc decoder/JOSE layer.

**2. `ReactiveJwtDecoder.decode(...)` trả gì?** `Mono<Jwt>` với token đã được decoder chấp nhận, hoặc error khi không hợp lệ.

**3. Vì sao `setJwtValidator(customAudience)` có thể nguy hiểm?** Setter thay thế validator hiện hành, làm mất các kiểm tra claim mặc định nếu không tự ghép lại.

**4. Factory nào thường phù hợp để giữ kiểm tra nền tảng và issuer?** `JwtValidators.createDefaultWithIssuer(trustedIssuer)`.

**5. Dùng gì để ghép nhiều validators?** `DelegatingOAuth2TokenValidator<Jwt>`.

**6. `JwtValidators.createDefaultWithIssuer` có tự kiểm tra audience `orders-api` không?** Không nên giả định. Cấu hình audience validator theo contract của API.

**7. `withJwkSetUri(...)` có tự chứng minh `iss` đúng không?** Không. Phải bảo đảm issuer validation được thêm vào decoder.

**8. `exp` còn tồn tại có đủ để chứng minh token chưa hết hạn không?** Không. Cần kiểm tra thời gian hiệu lực và clock skew; claim presence khác validation giá trị.

**9. Vì sao không kiểm tra `aud` bằng substring?** Vì `orders-api-admin` không giống `orders-api`; cần exact membership theo danh sách audience.

**10. Vì sao test `Jwt.withTokenValue` không kiểm tra chữ ký?** Nó chỉ dựng đối tượng `Jwt` trong bộ nhớ, không tạo/xác minh JWS.

**11. StepVerifier có kiểm tra được default issuer/expiry validators không?** Có khi chạy **decoder thật đã cấu hình đúng**, không phải decoder lambda trả Jwt cố định.

**12. WebTestClient `mockJwt()` có chứng minh full JWT validation không?** Không. Nó thường inject authentication giả lập để test authorization.

**13. Token hợp lệ nhưng thiếu `SCOPE_orders:read` nên HTTP gì?** Thường 403 do authorization, khác 401 khi JWT bị từ chối ở authentication.

**14. Multi-issuer có được tự tải metadata/JWKS từ `iss` chưa xác minh không?** Không. Chỉ chọn issuer trong allowlist, rồi vẫn xác minh chữ ký và issuer.

**15. Nếu cần kiểm tra membership trong database, có nên query blocking trong validator không?** Không ở WebFlux request path. Tách sang reactive authorization/service policy.

**16. Vì sao không tự xây defaults bằng đúng một `JwtTimestampValidator`?** Có thể làm mất issuer/type/những kiểm tra nền tảng khác theo version.

**17. Nếu muốn thay default clock skew thì chỉ cần add một JwtTimestampValidator khác không?** Không hẳn; có thể tạo hai timestamp validators với threshold khác nhau. Cần thiết kế thay thế chính sách nền tảng có kiểm soát.

**18. Khi lỗi validator xảy ra, có nên trả raw JWT và JWKS URL cho client không?** Không. Chỉ trả Bearer error phù hợp, giữ chi tiết trong telemetry an toàn.

## 25. Tài liệu tham khảo

- **Spring Security Reference — Reactive OAuth 2.0 Resource Server JWT:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **Spring Security Reference — Reactive OAuth 2.0 Resource Server Multi-tenancy:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html
- **Spring Security API — JwtValidators:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html
- **Spring Security API — NimbusReactiveJwtDecoder:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html
- **Spring Security API — JwtTimestampValidator:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html
- **Spring Security API — JwtClaimValidator:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtClaimValidator.html
- **Spring Security API — DelegatingOAuth2TokenValidator:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/DelegatingOAuth2TokenValidator.html
- **Spring Security Reference — WebFlux Security Testing:** https://docs.spring.io/spring-security/reference/reactive/test/index.html
- **RFC 7519 — JSON Web Token (JWT):** https://www.rfc-editor.org/rfc/rfc7519
- **RFC 8725 — JSON Web Token Best Current Practices:** https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** https://www.rfc-editor.org/rfc/rfc9068
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** https://www.rfc-editor.org/rfc/rfc6750

## 26. Kết luận

Trong **Spring Security WebFlux Resource Server**, `OAuth2TokenValidator<Jwt>` là lớp đánh giá **JWT claims/token contract** sau bước JOSE verification. Khi bổ sung audience, tenant, subject, thời hạn hay token profile, không được vô tình thay mất những kiểm tra nền tảng như `exp`, `nbf` và `iss`.

Cách thông dụng và dễ kiểm soát là dùng:

```java
decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator,
                customContractValidator));
```

Song song, hãy bảo đảm decoder vẫn xác minh **chữ ký, thuật toán và nguồn khóa tin cậy**, URL/issuer được lựa chọn từ cấu hình đáng tin, audience trùng resource identifier, token không nhầm ID token, và phân quyền truy cập dữ liệu được kiểm tra ở tầng authorization. **Unit test validators**, **StepVerifier với decoder thật** và **WebTestClient qua Bearer filter chain** là những tầng kiểm thử bổ trợ nhau. Một validator mới chỉ có ích khi nó làm ràng buộc **chặt hơn theo hợp đồng**, không làm mất những điều kiện đã giữ cho API an toàn.
