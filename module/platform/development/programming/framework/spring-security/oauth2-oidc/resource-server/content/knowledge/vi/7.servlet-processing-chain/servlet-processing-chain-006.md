# Decoder hoặc introspector chuyển token thành dữ liệu đã được xác minh

Trong **Spring Security OAuth 2.0 Resource Server** chạy trên Servlet stack, một HTTP request thường mang access token dưới dạng chuỗi:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Chuỗi này chưa chứng minh được danh tính, quyền truy cập hay thậm chí nguồn phát hành. Spring Security phải đi qua một **ranh giới xác thực**: từ token do client gửi tới dữ liệu mà Resource Server có cơ sở tin cậy.

Có hai cơ chế phổ biến:

- **JWT:** `JwtDecoder` xác minh chữ ký số và các ràng buộc của JSON Web Token, sau đó trả một đối tượng `Jwt`.
- **Opaque token:** `OpaqueTokenIntrospector` tra token với Authorization Server thông qua introspection endpoint, kiểm tra trạng thái và nhận thuộc tính được xác nhận, sau đó trả `OAuth2AuthenticatedPrincipal`.

Kết quả từ decoder hoặc introspector được chuyển thành `Authentication` có principal và authorities. **Chỉ sau khi xác thực thành công**, Spring Security mới sử dụng các dữ liệu đó để phân quyền request.

Bài học đi theo luồng Servlet từ `Authorization` header đến `SecurityContext`, giải thích rõ điều gì đã được xác minh, điều gì cần cấu hình thêm và vì sao **token xác thực thành công vẫn chưa chắc được phép truy cập tài nguyên**.

## 1. Bản đồ chuỗi xử lý Servlet

Request đi vào ứng dụng Servlet sẽ đi qua `FilterChainProxy` và một `SecurityFilterChain` phù hợp trước controller.

Những thành phần liên quan đến bearer token:

| Thành phần | Trách nhiệm | Đầu vào / đầu ra |
|---|---|---|
| `BearerTokenAuthenticationFilter` | Tìm bearer token, yêu cầu xác thực | HTTP header → `BearerTokenAuthenticationToken` |
| `BearerTokenResolver` | Trích xuất token từ vị trí HTTP được phép | Mặc định chủ yếu là `Authorization: Bearer ...` |
| `AuthenticationManager` | Giao cho provider phù hợp | Yêu cầu xác thực chưa được tin cậy → kết quả/lỗi |
| `JwtAuthenticationProvider` | Xác thực token JWT | Gọi `JwtDecoder` |
| `JwtDecoder` | Kiểm tra chữ ký và JWT claims | Chuỗi JWT → `Jwt` |
| `OpaqueTokenAuthenticationProvider` | Xác thực token qua introspection | Gọi `OpaqueTokenIntrospector` |
| `OpaqueTokenIntrospector` | Xác nhận trạng thái/thuộc tính token từ AS | Chuỗi token → `OAuth2AuthenticatedPrincipal` |
| `JwtAuthenticationConverter` | Ánh xạ claims sang name/authorities | `Jwt` → `JwtAuthenticationToken` |
| `SecurityContextHolder` | Lưu kết quả xác thực cho request | `Authentication` đã xác thực |
| `AuthorizationFilter` | Đánh giá chính sách HTTP | Cho phép/từ chối theo `Authentication` |
| Method security/service | Kiểm tra quyền nghiệp vụ bổ sung | Scope, tenant, ownership, trạng thái tài nguyên |

```mermaid
flowchart TD
    A["HTTP request: Authorization Bearer TOKEN"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["BearerTokenAuthenticationToken chưa xác thực"]
    C --> D["AuthenticationManager"]
    D --> E{"Cấu hình Provider"}
    E -- "JWT" --> F["JwtAuthenticationProvider"]
    E -- "Opaque" --> G["OpaqueTokenAuthenticationProvider"]
    F --> H["JwtDecoder: chữ ký và validators"]
    G --> I["OpaqueTokenIntrospector: trạng thái và thuộc tính"]
    H --> J{"Token được chấp nhận?"}
    I --> J
    J -- "Không" --> K["Authentication failure: thường 401"]
    J -- "Có" --> L["Tạo Authentication và authorities"]
    L --> M["SecurityContext"]
    M --> N["AuthorizationFilter / method security"]
    N --> O{"Đủ quyền?"}
    O -- "Không" --> P["Thường 403"]
    O -- "Có" --> Q["Controller và service"]
```

Sơ đồ là luồng logic điển hình, không liệt kê toàn bộ filter. Một ứng dụng có thể cấu hình nhiều `SecurityFilterChain` hoặc nhiều phương thức xác thực; chuỗi được chọn quyết định cơ chế nào được sử dụng.

## 2. Trước khi decode: bearer token chỉ là dữ liệu chưa tin cậy

Client gửi:

```http
Authorization: Bearer <ACCESS_TOKEN>
```

`BearerTokenAuthenticationFilter` dùng `BearerTokenResolver` để lấy chuỗi token. Filter tạo `BearerTokenAuthenticationToken` và chuyển đến `AuthenticationManager`. Đây là **authentication request**, chưa phải kết quả xác thực thành công.

Ở thời điểm này:

- Client có thể gửi token hợp lệ, token hết hạn, token do issuer khác cấp, hoặc một chuỗi giả mạo.
- Việc HTTP header có từ `Bearer` không chứng minh token đáng tin.
- JWT có ba phần ngăn bằng dấu chấm chưa chắc được ký đúng.
- Một opaque token có hình dạng ngẫu nhiên không thể được suy ra là active từ cú pháp.
- Dữ liệu chưa được kiểm chứng **không được dùng** làm `GrantedAuthority` hoặc quyền thao tác.

Ví dụ sai:

```java
// Ví dụ KHÔNG an toàn: chỉ giải Base64URL JWT payload
// rồi sử dụng claim chưa xác minh để cấp quyền.
String role = unverifiedPayload.get("role").toString();
if ("ADMIN".equals(role)) {
    allowAdministration();
}
```

Kẻ tấn công có thể tự tạo payload chứa `role=ADMIN`. **Giải Base64URL là thao tác đọc dữ liệu, không phải kiểm tra chữ ký hay xác thực danh tính.**

## 3. Hai cơ chế xác thực access token

OAuth 2.0 không bắt buộc access token phải là JWT. Token có thể được phát hành dưới dạng JWT đã ký hoặc opaque token cần introspection.

| Tiêu chí | JWT với `JwtDecoder` | Opaque với `OpaqueTokenIntrospector` |
|---|---|---|
| Token được Resource Server đọc trực tiếp? | Có, về mặt cấu trúc; chỉ tin sau xác minh | Không, nội dung không được suy đoán từ chuỗi |
| Kiểm chứng chính | Chữ ký số và các token validators | Kết quả introspection từ AS tin cậy |
| Dữ liệu trả về | `Jwt` | `OAuth2AuthenticatedPrincipal` |
| Provider dùng dữ liệu | `JwtAuthenticationProvider` | `OpaqueTokenAuthenticationProvider` |
| Authentication thường tạo | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| Có cần gọi AS mỗi request? | Thường không sau khi có khóa công khai, trừ lúc cần refresh | Thường có nếu không áp dụng caching |
| Biết token bị thu hồi trước hạn? | Không tự biết chỉ bằng xác minh chữ ký | Có thể biết nếu AS trả `active=false` |
| Ràng buộc API cụ thể | Cần kiểm tra `aud` và policy | Cần introspection metadata/hợp đồng tài nguyên tương ứng |

Cấu hình chọn cơ chế phải dựa trên **hợp đồng access token với Authorization Server**. Không nên tự động đếm dấu chấm trong token do client gửi rồi tùy ý chọn cơ chế và nguồn tin cậy. Một JWT cũng có thể được kiểm tra qua introspection nếu thiết kế hệ thống quy định, nhưng điều đó khác với xác minh cục bộ bằng khóa ký.

## 4. Nhánh JWT: decoder không chỉ đọc payload

### 4.1. Cấu trúc một JWT access token

Một JWT được ký dạng JWS compact gồm:

```text
base64url(header).base64url(payload).base64url(signature)
```

Header minh họa:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "signing-key-2026-11"
}
```

Payload minh họa:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1794715200,
  "exp": 1794718800
}
```

Các giá trị này chỉ là ví dụ, không phải JWT thực có chữ ký. Client có thể đọc payload nhưng **không được tự coi payload là thông tin xác thực**.

### 4.2. `JwtDecoder` lấy khóa tin cậy ở đâu?

Trong nhánh JWT, `JwtAuthenticationProvider` gọi `JwtDecoder`. Implementation thông dụng là `NimbusJwtDecoder`.

Resource Server có thể lấy khóa từ:

- **Issuer discovery:** cấu hình `issuer-uri` cho phép Spring Security tìm metadata OIDC/OAuth và `jwks_uri` phù hợp, theo khả năng của phiên bản.
- **JWK Set URI cố định:** cấu hình `jwk-set-uri` để chỉ rõ nơi tải bộ public keys.
- **Khóa tin cậy cố định:** cấu hình decoder theo public key hoặc cơ chế tin cậy riêng, nếu hợp đồng token yêu cầu.

Với JWT ký bằng RSA/ECDSA, Authorization Server giữ **private key** để ký; Resource Server dùng **public key** để xác minh. JWKS thường chứa nhiều khóa công khai, hỗ trợ key rotation.

```text
Issuer đã được cấu hình
      │
      ▼
Metadata tin cậy → jwks_uri
      │
      ▼
JWKS: public keys (kid, kty, alg, n/e hoặc crv/x/y...)
      │
      ▼
JwtDecoder chọn khóa thích hợp và kiểm tra chữ ký
```

Trường `kid` chỉ là gợi ý chọn khóa, **không phải bằng chứng khóa đó đáng tin**. Không cho phép một JWT chưa xác thực tự chỉ định URL tải khóa tùy ý qua header như `jku`. Verifier phải lấy khóa từ nguồn đã được cho phép.

### 4.3. Các bước xác minh JWT

```mermaid
flowchart TD
    A["JWT string chưa tin"] --> B["Parse cấu trúc JWS"]
    B --> C["Kiểm tra thuật toán và chọn trusted public key"]
    C --> D{"Chữ ký hợp lệ?"}
    D -- "Không" --> X["JwtException / authentication failure"]
    D -- "Có" --> E["Chạy OAuth2TokenValidator trên Jwt"]
    E --> F{"exp, nbf, iss, aud và policy đạt?"}
    F -- "Không" --> X
    F -- "Có" --> G["Trả Jwt đã được decoder chấp nhận"]
```

Các điểm decoder cần bảo đảm theo cấu hình:

1. **Thuật toán ký:** Không chấp nhận `alg=none` hoặc thuật toán tùy ý do token yêu cầu; chỉ những thuật toán được Resource Server tin cậy.
2. **Chữ ký:** Public key được chọn phải xác minh được JWS signature.
3. **Issuer `iss`:** Token phải đến từ AS được tin cậy.
4. **Thời gian:** `exp`, `nbf` và các chính sách clock skew phù hợp.
5. **Audience `aud`:** Token phải dành cho API đang nhận, nếu hợp đồng yêu cầu.
6. **Loại token:** Không chấp nhận OIDC ID token làm access token; nếu AS theo RFC 9068, kiểm tra token type/profile tương ứng.
7. **Các ràng buộc đặc thù:** Tenant, client policy hoặc claim khác nếu hệ thống đặt yêu cầu.

Điểm quan trọng: **kiểm tra chữ ký không tự động đồng nghĩa kiểm tra audience**. Issuer có thể ký token cho nhiều API. Nếu Resource Server không cấu hình audience validator, token do đúng issuer cấp nhưng dành cho API khác có thể lọt qua lớp xác thực.

### 4.4. `Jwt` được trả về mang thông tin gì?

Interface `JwtDecoder` cung cấp:

```java
Jwt jwt = jwtDecoder.decode(tokenValue);
```

Sau khi decoder hoàn thành đúng các phép kiểm tra đã được cấu hình, `Jwt` cung cấp headers và claims:

```java
String subject = jwt.getSubject();
String issuer = jwt.getIssuer().toString();
List<String> audiences = jwt.getAudience();
Map<String, Object> headers = jwt.getHeaders();
Map<String, Object> claims = jwt.getClaims();
```

Ý nghĩa “đã xác minh” là dữ liệu **được decoder chấp nhận theo các validators thực tế**, không có nghĩa mọi claim đều đáp ứng mọi chính sách nghiệp vụ:

- `scope=orders.read` không chứng minh người dùng sở hữu tất cả đơn hàng.
- `email` có trong JWT không mặc định chứng minh email đã được xác thực theo chính sách ứng dụng.
- `aud` có trong JWT không được coi là “đúng API” nếu ứng dụng không so sánh với expected audience.
- `client_id` chỉ định OAuth client theo hợp đồng, không chứng minh caller hiện tại giữ private key.

Trong một request bình thường, controller **không cần gọi `JwtDecoder.decode(...)` lại**: Spring Security đã xác thực token ở lớp filter/provider.

## 5. Cấu hình JWT trong Spring Boot

### 5.1. Khai báo dependencies

Ví dụ Maven:

```xml
<dependencies>
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

### 5.2. Cấu hình issuer và audience

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

Trong cấu hình Spring Boot có hỗ trợ thuộc tính này:

- `issuer-uri` chỉ issuer tin cậy, giúp tìm metadata/JWKS theo cơ chế discovery phù hợp và kiểm tra claim `iss`.
- `audiences` yêu cầu token có audience `orders-api`.
- Decoder có thể tải và cache public keys, rồi kiểm tra chữ ký JWT bằng các khóa phù hợp.
- Quyền truy cập endpoint vẫn phải được thiết lập riêng bằng authorization rules.

Nếu cần biết trước JWKS endpoint mà không dùng discovery để tìm địa chỉ khóa:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
          jwk-set-uri: https://login.example.test/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
```

Giữ `issuer-uri` đồng thời chỉ định `jwk-set-uri` để còn kiểm tra issuer. Chỉ có JWKS URL **không bảo đảm** decoder tự kiểm tra `iss` nếu ứng dụng không cấu hình validator tương ứng.

Khả năng auto-configuration của `audiences` và thời điểm liên hệ AS có thể khác theo phiên bản Spring Boot/Spring Security, nhất là khi khai báo decoder bean tùy biến. Phải thiết lập các validator cần thiết tại decoder thực tế được sử dụng.

### 5.3. Tự định nghĩa audience validator

Ví dụ Spring Security:

```java
@Configuration
public class JwtDecoderConfig {

    private static final String ISSUER =
        "https://login.example.test/realms/shop";
    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> defaults =
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
                defaults,
                audienceValidator
            )
        );
        return decoder;
    }
}
```

Các import:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
```

`JwtValidators.createDefaultWithIssuer(...)` giữ những điều kiện chuẩn như issuer/thời gian theo phiên bản. Audience validator yêu cầu đúng Resource Server.

**Không thay validator mặc định bằng chỉ audience validator** vì có thể bỏ sót issuer hoặc kiểm tra thời gian. Đừng lấy expected audience từ Host header hoặc từ chính JWT do caller gửi; expected audience là cấu hình tin cậy phía server.

## 6. `JwtAuthenticationProvider` chuyển `Jwt` thành `Authentication`

Một decoder thành công trả dữ liệu `Jwt`; Spring Security cần tiếp tục xây dựng đối tượng xác thực.

```text
BearerTokenAuthenticationToken
        │
        ▼
JwtAuthenticationProvider
        │ gọi JwtDecoder.decode(...)
        ▼
Jwt {headers, claims đã qua validation}
        │
        ▼
JwtAuthenticationConverter
        │ ánh xạ name + GrantedAuthority
        ▼
JwtAuthenticationToken
        │
        ▼
SecurityContext → Authorization
```

Theo cấu hình mặc định thường gặp, `JwtGrantedAuthoritiesConverter` đọc `scope` hoặc `scp` và thêm tiền tố `SCOPE_`:

```text
JWT: "scope": "orders.read profile"
                 │
                 ▼
GrantedAuthority:
  - SCOPE_orders.read
  - SCOPE_profile
```

Vì thế:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

sẽ đòi authority `SCOPE_orders.read`. Trong khi đó `hasRole("ADMIN")` mặc định kiểm tra `ROLE_ADMIN`; claim `roles` không tự động trở thành role tương ứng nếu chưa cấu hình converter.

Phân biệt:

1. **Decode/validate:** Chứng minh token đáng tin theo những điều kiện xác thực đã cấu hình.
2. **Convert:** Biểu diễn claims đã chấp nhận thành principal và authorities.
3. **Authorize:** Kiểm tra caller có quyền thực hiện hành động với tài nguyên cụ thể.

Lẫn các bước này có thể khiến API tin rằng “JWT hợp lệ” đồng nghĩa “được phép thao tác mọi dữ liệu”.

## 7. Nhánh opaque: introspection thay cho việc tự giải JWT

Opaque token có thể trông như một chuỗi ngẫu nhiên:

```text
7R6aTmFoFm9XJkQ7p8V2QJcW...
```

Resource Server không biết bên trong chuỗi có claim gì. Cách phổ biến là gọi **OAuth 2.0 Token Introspection** theo RFC 7662.

Request minh họa:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <introspection-credentials>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<urlencoded-access-token>
```

AS có thể trả:

```json
{
  "active": true,
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "client_id": "web-portal",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1900000000
}
```

Nếu token không hợp lệ/không hoạt động:

```json
{
  "active": false
}
```

**`active=false` không phải dữ liệu để “thử lại rồi cấp quyền tạm”**. Resource Server không được tạo principal hợp lệ khi AS tuyên bố token inactive.

### 7.1. `OpaqueTokenIntrospector` kiểm tra điều gì?

Interface của Spring Security cung cấp phương thức:

```java
OAuth2AuthenticatedPrincipal principal =
    introspector.introspect(tokenValue);
```

Implementation được cấu hình thường:

1. Gửi chuỗi token đến introspection endpoint của AS qua kết nối được bảo vệ.
2. Xác thực phía Resource Server với endpoint theo phương thức mà AS yêu cầu.
3. Nhận response và xác nhận token active theo logic implementation.
4. Trả `OAuth2AuthenticatedPrincipal` chứa attributes và authorities.
5. Ném lỗi nếu token không hợp lệ hoặc introspection không thể chấp nhận kết quả.

Khi `introspect(...)` trả về principal, dữ liệu có thể được dùng cho những quyết định tiếp theo **theo hợp đồng và các điều kiện đã được kiểm tra**.

Ví dụ truy cập thông tin:

```java
String subject = principal.getAttribute("sub");
Object audience = principal.getAttribute("aud");
Object clientId = principal.getAttribute("client_id");
Collection<? extends GrantedAuthority> authorities =
    principal.getAuthorities();
```

Không suy luận một opaque token có toàn bộ claim nói trên. Theo RFC 7662, nhiều trường metadata là tùy chọn; AS có thể không trả `aud` hoặc `iss`, tùy cấu hình và hồ sơ token.

### 7.2. `active=true` không tự đồng nghĩa “đúng API”

Một introspection response có thể nói token đang active, nhưng AS có thể cấp token cho nhiều API. Resource Server cần hợp đồng rõ về **audience/resource binding**:

- AS trả `aud` và Resource Server kiểm tra `aud` chứa `orders-api`.
- Hoặc introspection được AS giới hạn theo tài nguyên nhận token, với cam kết rõ ràng rằng `active=true` chỉ dành cho resource hiện tại.
- Hoặc có một cơ chế tin cậy khác tương đương để xác định token dành cho API này.

Nếu ứng dụng yêu cầu audience mà introspection không cho biết và không có cơ chế thay thế, không nên bỏ qua điều kiện đó chỉ để request chạy được.

**`client_id` chỉ ứng dụng xin token, không phải audience của API**. Tương tự, `scope` mô tả quyền, nhưng không thay bằng chứng token được cấp cho API đích.

### 7.3. Introspection không phải UserInfo

Một OpenID Provider có thể công bố cả `userinfo_endpoint` và `introspection_endpoint`. Hai endpoint khác mục đích:

| Endpoint | Chủ yếu phục vụ | Dữ liệu |
|---|---|---|
| OIDC UserInfo | OIDC client lấy thông tin user theo flow và scope | Claims về end user |
| OAuth Token Introspection | Bên được phép kiểm tra trạng thái token | `active` và metadata token như scope, client, subject, audience |

Không nên gọi UserInfo rồi xem việc trả được tên người dùng là bằng chứng access token hợp lệ cho Resource Server.

## 8. Cấu hình opaque Resource Server

Ví dụ `application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: orders-resource-server
          client-secret: REPLACE_WITH_SECRET_FROM_SECRET_MANAGER
```

Lưu ý:

- `introspection-uri` phải là endpoint tin cậy của AS.
- `client-id` và `client-secret` ở đây là **credential của Resource Server khi gọi introspection**. Chúng **khác** `client_id` của OAuth client như `web-portal` đã xin token.
- Trong production, lấy secret từ biến môi trường hoặc secret manager; không lưu secret thật trong Git hay log.
- Một số AS hỗ trợ phương thức xác thực introspection khác; cấu hình phải theo hợp đồng thực tế.

Filter chain minh họa:

```java
@Configuration
public class OpaqueSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
```

Các import:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
```

Spring Security thường ánh xạ các scope được introspection trả về thành authorities `SCOPE_...`. Nếu AS sử dụng cấu trúc quyền tùy biến, cần ánh xạ dựa trên dữ liệu đã xác nhận, theo chính sách API.

Khi ứng dụng cần kiểm tra audience bổ sung mà introspector mặc định chưa thực thi, có thể **bọc `OpaqueTokenIntrospector` bằng một thành phần xác thực tùy biến**:

```text
OpaqueTokenIntrospector delegate = introspector được cấu hình tin cậy

introspect(token):
    principal = delegate.introspect(token)   // đã kiểm tra active
    aud = principal.attributes["aud"]
    if aud không chứa "orders-api":
        thất bại xác thực token
    return principal
```

Đây là **pseudocode**, không phải Java chạy trực tiếp. Thực thi thật phải xử lý đúng kiểu `aud` mà AS trả về (chuỗi hoặc danh sách), exception và contract của phiên bản Spring Security. Kiểm tra bổ sung phải diễn ra **trước** khi coi authentication thành công.

## 9. Từ introspection principal đến `BearerTokenAuthentication`

Luồng sau introspection:

```text
BearerTokenAuthenticationToken
        │
        ▼
OpaqueTokenAuthenticationProvider
        │ gọi introspector.introspect(...)
        ▼
OAuth2AuthenticatedPrincipal
  attributes: sub, client_id, aud, scope, exp, ...
  authorities: SCOPE_orders.read, ...
        │
        ▼
BearerTokenAuthentication
        │
        ▼
SecurityContext → Authorization
```

Đối chiếu với JWT:

| Đầu vào của provider | Dữ liệu trung gian | Authentication thường gặp | Principal |
|---|---|---|---|
| JWT bearer token | `Jwt` | `JwtAuthenticationToken` | Thường là `Jwt` |
| Opaque bearer token | `OAuth2AuthenticatedPrincipal` | `BearerTokenAuthentication` | Thường là `OAuth2AuthenticatedPrincipal` |

Vì kiểu principal khác nhau, code controller cần chọn kiểu phù hợp.

Với JWT:

```java
@GetMapping("/api/me")
public Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
    return Map.of(
        "subject", jwt.getSubject(),
        "issuer", jwt.getIssuer().toString()
    );
}
```

Với opaque:

```java
@GetMapping("/api/me")
public Map<String, Object> me(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    return Map.of(
        "name", principal.getName(),
        "authorities", principal.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .toList()
    );
}
```

Ví dụ dùng Java phiên bản có `Stream.toList()`; code thực tế cần xử lý các trường tùy chọn và hạn chế thông tin trả về. Đừng expose toàn bộ token hoặc claims nhạy cảm qua API debug.

Khi muốn controller độc lập với token format, có thể nhận `Authentication`:

```java
@GetMapping("/api/principal-name")
public Map<String, String> principal(Authentication authentication) {
    return Map.of("name", authentication.getName());
}
```

Một `Authentication` được xây dựng đúng cách chỉ xuất hiện sau bước xác thực; các HTTP authorization rules sử dụng authorities của nó, không tự gọi introspection hoặc decoder lại trong controller.

## 10. Ranh giới tin cậy: từng loại dữ liệu đáng tin đến mức nào?

Bảng sau giúp tránh dùng dữ liệu sai tầng:

| Giai đoạn | Dữ liệu có được | Có được coi là đã xác thực? |
|---|---|---|
| Header `Authorization` | Chuỗi token do caller gửi | **Chưa** |
| `BearerTokenAuthenticationToken` | Token đã được trích xuất | **Chưa** |
| JWT payload đọc bằng Base64URL | Claims tự khai báo | **Chưa** |
| `JwtDecoder` thành công | `Jwt` với chữ ký và validators đã áp dụng | **Có theo tập validation được cấu hình** |
| `OpaqueTokenIntrospector` thành công | `OAuth2AuthenticatedPrincipal` từ AS | **Có theo contract introspection và các ràng buộc đã kiểm tra** |
| Authentication provider thành công | `JwtAuthenticationToken` hoặc `BearerTokenAuthentication` | Có thể dùng làm input cho authorization |
| `AuthorizationFilter` thành công | Quyền HTTP phù hợp | Có thể tiếp tục đến controller/service |
| Method security và business policy | Quyền trên bản ghi cụ thể | Phụ thuộc policy nghiệp vụ được thực thi |

Ví dụ token có:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

Khi đã xác thực đúng, API có thể tin rằng **issuer đã cấp** subject/scope này cho API. Nhưng chưa có gì chứng minh `user-123` được phép xem **đơn hàng 42** của `user-456`. Quyền đó thường phải được kiểm tra tại service, repository hoặc method security.

### Xác thực và phân quyền không thể thay thế nhau

```text
Token string
   │
   ▼
Decoder / Introspector → Token identity và thuộc tính hợp lệ
   │
   ▼
AuthenticationProvider → Authentication có authorities
   │
   ▼
AuthorizationFilter / Method Security → Cho phép hay từ chối
```

**Không sử dụng `authenticated()` như chính sách duy nhất cho endpoint nhạy cảm** nếu API còn yêu cầu scope, role, tenant hoặc ownership. Một request có token hợp lệ vẫn có thể không được phép thực hiện thao tác.

## 11. Cấu hình quyền HTTP cho cả hai cơ chế

Sau khi chọn nhánh JWT hoặc opaque, các quy tắc authorization về mặt ý nghĩa có thể giống nhau.

Ví dụ JWT Resource Server:

```java
@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Để chuyển cấu hình này sang opaque theo hợp đồng AS, thay nhánh JWT bằng:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
```

Chỉ thay nhánh xác thực là **chưa đủ** nếu các thuộc tính/scope do introspection cung cấp có cấu trúc khác JWT; cần điều chỉnh converter hoặc introspector phù hợp.

Sự khác nhau nằm ở **cách xác minh token**. Phía sau, `AuthorizationFilter` vẫn nhìn các authorities đã được tạo. Với cả hai nhánh, người dùng có `SCOPE_orders.read` chưa được mặc định có quyền đọc mọi đơn hàng; service vẫn phải kiểm tra quyền dữ liệu nếu nghiệp vụ yêu cầu.

## 12. Lỗi ở decoder/introspector xuất hiện dưới dạng HTTP nào?

Trong Resource Server, các lỗi authentication khác với authorization.

| Tình huống | Tầng phát hiện | Kết quả thường gặp |
|---|---|---|
| Không gửi token tới endpoint được bảo vệ | Authorization nhận request chưa xác thực | `401 Unauthorized` |
| Header bearer sai định dạng | Bearer token resolution | Có thể `400 invalid_request` |
| JWT bị sửa chữ ký | Decoder/JWT provider | `401 invalid_token` |
| JWT hết hạn, sai issuer, sai audience | JWT validators | `401 invalid_token` |
| Opaque token introspection trả `active=false` | Introspector/provider | `401 invalid_token` |
| Introspection lỗi TLS/timeout/credential | Hạ tầng xác thực | Request không được xác thực; HTTP cụ thể phụ thuộc exception handling |
| Token đã được xác thực nhưng thiếu scope | Authorization | Thường `403 Forbidden` |
| Token hợp lệ, đủ scope nhưng sai ownership/tenant | Policy nghiệp vụ | `403` hoặc `404` theo chính sách bảo vệ dữ liệu |
| Token hợp lệ, đầy đủ quyền | Controller/service | HTTP thành công như `200` nếu nghiệp vụ thành công |

Ví dụ token không hợp lệ:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Ví dụ token hợp lệ nhưng scope không đủ:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Header chính xác phụ thuộc loại lỗi và cấu hình `BearerTokenAuthenticationEntryPoint`, `BearerTokenAccessDeniedHandler`, `ExceptionTranslationFilter` hoặc handler tùy biến. Lỗi hạ tầng introspection không nên được che giấu bằng việc **tự cho token qua**.

## 13. Cache, key rotation và khả năng sẵn sàng

### 13.1. JWT: xác minh cục bộ, nhưng phụ thuộc khóa công khai

Với JWT ký bất đối xứng:

- AS giữ private key và phát hành JWT đã ký.
- Resource Server dùng public key trong JWKS để xác minh.
- Các JWT có thể được xác minh cục bộ sau khi khóa đã được lấy.
- Khi AS xoay khóa, JWKS có thể chứa cả public key cũ và mới trong giai đoạn chuyển tiếp.
- Nếu decoder cache JWKS cũ quá lâu, một token mới có `kid` chưa biết có thể tạm thời không xác minh được.
- JWT ký hợp lệ không tự thể hiện việc token đã bị thu hồi trước hạn, trừ khi API áp dụng cơ chế trạng thái bổ sung.

Chọn thời hạn access token và chiến lược rotation theo yêu cầu vận hành. Không tắt kiểm tra chữ ký chỉ vì JWT mới không khớp khóa cũ.

### 13.2. Opaque: introspection có thể phản ánh trạng thái mới hơn

AS có thể trả `active=false` ngay khi token bị vô hiệu hóa. Đổi lại:

- Introspection có thể tạo request mạng cho mỗi lần xác thực.
- Latency, timeout và availability của AS ảnh hưởng đến API.
- Cache response giúp giảm tải nhưng có thể kéo dài thời gian chấp nhận token đã bị thu hồi.
- Không cache vô hạn kết quả `active=true`, bỏ qua `exp` hoặc coi cache stale là bằng chứng hợp lệ.
- Khi AS tạm thời không truy cập được, request bảo vệ cần **fail closed** theo chính sách xác thực an toàn.

### 13.3. Bảo vệ bearer token và credential introspection

Đừng ghi raw bearer token vào application log, proxy log, URL hoặc trace. Cả JWT lẫn opaque token có thể bị dùng lại nếu lộ. Credential dùng để gọi introspection endpoint cũng cần được giữ bí mật.

Cách ghi log hữu ích hơn:

```text
request_id=req-123
route=/api/orders/{id}
authentication=FAILED
reason=INVALID_AUDIENCE
expected_audience=orders-api
```

Thông tin log phải phù hợp chính sách bảo vệ dữ liệu; tránh đưa token, client secret hay dữ liệu nhận dạng nhạy cảm vào log.

## 14. Phân tích tình huống thực tế

Giả sử Orders API tin cậy issuer `https://login.example.test/realms/shop`, audience `orders-api`, và `GET /api/orders/**` cần `SCOPE_orders.read`.

### Tình huống A — JWT có chữ ký hợp lệ nhưng sai audience

```json
{
  "iss": "https://login.example.test/realms/shop",
  "aud": ["payments-api"],
  "scope": "orders.read",
  "exp": 1900000000
}
```

Nếu audience validator đã cấu hình, decoder phải từ chối vì token dành cho `payments-api`. Scope đúng **không sửa được** audience sai. Kết quả thường là `401`.

### Tình huống B — JWT đúng audience nhưng thiếu scope

```json
{
  "iss": "https://login.example.test/realms/shop",
  "aud": ["orders-api"],
  "scope": "profile",
  "exp": 1900000000
}
```

Decoder có thể chấp nhận JWT nếu chữ ký và các điều kiện hợp lệ. Converter tạo `SCOPE_profile`, còn `AuthorizationFilter` yêu cầu `SCOPE_orders.read` nên từ chối, thường `403`.

### Tình huống C — Opaque token inactive

Introspection trả:

```json
{"active": false}
```

Introspector không được trả principal đáng tin cho token inactive. Provider không có cơ sở xây dựng `Authentication` hợp lệ; request đến endpoint được bảo vệ thất bại.

### Tình huống D — Opaque token active nhưng thiếu audience

AS trả `active=true`, `scope=orders.read` nhưng không có `aud`. Nếu hợp đồng yêu cầu chứng minh token dành cho Orders API, cần kiểm tra ràng buộc tài nguyên qua cơ chế khác đã được AS cam kết hoặc yêu cầu AS cung cấp metadata. **Không tự coi client ID là audience**.

### Tình huống E — Token hợp lệ nhưng sai quyền sở hữu

Token có `sub=user-123`, `aud=orders-api` và `scope=orders.read`. Request lại muốn xem đơn hàng thuộc `user-456`. Authentication có thể thành công, nhưng service phải xác minh quyền sở hữu/tenant và từ chối nếu không được phép.

### Tình huống F — Key rotation

Token JWT mới có `kid=new-key`, JWKS đang cache chỉ chứa `old-key`. Decoder phải lấy được khóa phù hợp và xác minh chữ ký. Nếu chưa thể xác minh, **không được tự chấp nhận token**; cần xử lý cập nhật khóa và sự cố JWKS.

### Tình huống G — Introspection timeout

AS không trả trạng thái token do timeout. Resource Server không thể khẳng định token active, nên không được cấp quyền dựa trên suy đoán. Cần log nguyên nhân hạ tầng an toàn và áp dụng chính sách thất bại xác thực.

### Tình huống H — ID token gửi nhầm vào API

OIDC ID token có `aud=web-portal`, không phải `orders-api`. Dù được ký bởi cùng issuer/JWKS, nó không phải access token dành cho Orders API. Decoder và chính sách token type/audience phải từ chối.

## 15. Cách xác định lỗi thuộc bước nào

Khi nhận một báo cáo “API trả 401/403 dù token có vẻ đúng”, lần lượt xem:

1. **Bearer token có được lấy đúng từ header không?** Header có sai cấu trúc hoặc nhiều nguồn token mâu thuẫn không?
2. **Provider nào xử lý?** JWT decoder hay opaque introspector, theo cấu hình/hợp đồng token nào?
3. **Nguồn xác thực có tin cậy không?** Issuer/JWKS phù hợp hay introspection endpoint của AS đúng và kết nối HTTPS hợp lệ?
4. **Token đã được chứng minh hợp lệ chưa?** JWT có chữ ký đúng hoặc introspection trả `active=true`?
5. **Đã áp dụng đủ validators chưa?** Thời gian, issuer, audience, loại token và policy riêng?
6. **Dữ liệu trung gian là loại gì?** `Jwt` hay `OAuth2AuthenticatedPrincipal`, với những claim/attribute thực tế nào?
7. **Authorities được ánh xạ ra sao?** `scope`/`scp` biến thành `SCOPE_...` hay dùng converter tùy biến?
8. **Provider có xây dựng `Authentication` đã xác thực không?** Kết quả có được đặt vào `SecurityContext` chưa?
9. **Authorization nào chặn request?** HTTP matcher, method security, quyền ownership/tenant?
10. **Xử lý lỗi có an toàn không?** Không fail open và không lộ token hoặc introspection credentials?

Bằng cách phân tách các lớp này, ta có thể xác định khác biệt giữa **token chưa xác thực**, **token đã xác thực nhưng thiếu quyền**, và **request đã có quyền HTTP nhưng cần kiểm tra dữ liệu nghiệp vụ**.

## 16. Tài liệu kỹ thuật liên quan

- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): luồng Servlet Resource Server và security filters.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, `NimbusJwtDecoder`, validators, authority conversion.
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): `OpaqueTokenIntrospector` và introspection.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): quy tắc bearer HTTP và lỗi.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc và claims JWT.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS và khóa dùng xác minh chữ ký.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection endpoint, `active` và thuộc tính token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): đặc tả JWT access token profile và những điều kiện token phù hợp.

**Điểm nhớ cuối cùng:** `JwtDecoder` giúp Resource Server kiểm tra JWT bằng khóa và validators tin cậy. `OpaqueTokenIntrospector` xác nhận trạng thái/thuộc tính token với AS. Provider biến kết quả thành `Authentication` có principal/authorities; lớp authorization tiếp tục quyết định request có được phép sử dụng tài nguyên cụ thể không.
