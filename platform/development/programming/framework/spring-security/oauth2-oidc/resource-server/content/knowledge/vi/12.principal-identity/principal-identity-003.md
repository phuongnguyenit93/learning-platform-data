# `@AuthenticationPrincipal Jwt` và truy cập claims trong controller

## 1. Mục tiêu: lấy danh tính đã xác thực thay vì tự giải mã Bearer token

Trong một ứng dụng **Spring Boot + Spring Security OAuth 2.0 Resource Server**, client gọi API bằng **OAuth 2.0 access token**:

~~~http
GET /api/me HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...
~~~

Nếu access token là JWT đã ký, Spring Security có thể tự kiểm tra token và tạo đối tượng xác thực trước khi request đến controller. Khi đó controller chỉ cần khai báo:

~~~java
@GetMapping("/api/me")
public Map<String, String> me(@AuthenticationPrincipal Jwt jwt) {
    return Map.of("subject", jwt.getSubject());
}
~~~

Không cần tự đọc header `Authorization`, cắt chuỗi `Bearer `, Base64URL-decode payload hoặc tự xác minh chữ ký JWT trong controller.

**`@AuthenticationPrincipal Jwt`** là cách tiêm **JWT principal đã được Spring Security Resource Server xác thực** vào tham số của controller Spring MVC. Từ `Jwt`, chương trình có thể truy cập các claims như `sub`, `iss`, `aud`, `scope` và custom claims.

Điều quan trọng là phân biệt ba nhóm công việc:

1. **Authentication**: Spring Security xác minh access token, tạo principal.
2. **Lấy danh tính và claims**: controller/service đọc thông tin đã xác thực qua `Jwt` hoặc `Authentication`.
3. **Authorization**: kiểm tra principal có được thực hiện hành động hoặc truy cập bản ghi cụ thể không.

Đọc được một claim như `tenant_id` không tự động chứng minh caller có quyền xem mọi bản ghi trong tenant đó. Và một custom claim chỉ nên được tin trong ngữ cảnh **issuer, audience, JWT validation và hợp đồng token** đã được cấu hình đầy đủ.

## 2. `Jwt` ở đây là đối tượng gì?

### 2.1. JWT access token và Spring `Jwt`

Một access token JWT có thể chứa các claims:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read profile",
  "client_id": "shop-web",
  "tenant_id": "tenant-42",
  "preferred_username": "phuong",
  "iat": 1999999700,
  "exp": 2000000000
}
~~~

Đây là JSON minh họa **payload**, không phải token có chữ ký thật; giá trị thời gian chỉ mang tính ví dụ.

Khi Resource Server xác thực thành công, `org.springframework.security.oauth2.jwt.Jwt` là một đối tượng Java chứa:

- **Token value**: chuỗi access token gốc.
- **Headers**: JOSE/JWS headers như `alg`, `kid`, `typ`.
- **Claims**: các tên và giá trị được decoder đọc từ JWT.
- **Các accessor tiện dụng**: `getSubject()`, `getIssuer()`, `getAudience()`, `getExpiresAt()`, `getIssuedAt()`, `getClaimAsString(...)` và nhiều phương thức khác.

Đối tượng `Jwt` **không giống** `java.security.Principal` theo nghĩa interface Java đơn giản; nó được Spring Security sử dụng làm **principal nằm bên trong Authentication** cho trường hợp JWT Resource Server.

### 2.2. Quan hệ giữa `JwtAuthenticationToken` và `Jwt`

Ở luồng JWT Resource Server thông thường, Spring Security tạo **`JwtAuthenticationToken`**. Đối tượng này thực thi mô hình `Authentication` của Spring Security.

~~~text
SecurityContext
    |
    v
Authentication = JwtAuthenticationToken
    |
    +-- principal = Jwt
    |
    +-- name = sub theo cấu hình thông thường
    |
    +-- authorities = [SCOPE_orders.read, SCOPE_profile, ...]
    |
    +-- authenticated = true
~~~

Chẳng hạn:

~~~java
@GetMapping("/api/security-info")
public Map<String, Object> securityInfo(Authentication authentication) {
    Object principal = authentication.getPrincipal();

    return Map.of(
        "authenticationType",
        authentication.getClass().getSimpleName(),
        "principalType",
        principal.getClass().getSimpleName(),
        "name",
        authentication.getName()
    );
}
~~~

Ví dụ có thể trả những tên như `JwtAuthenticationToken`, `Jwt` và `user-123` khi request được xác thực qua JWT.

**Đừng nhầm**:

- `Jwt`: chứa dữ liệu token/claims sau decode và validation.
- `JwtAuthenticationToken`: mô tả một **Authentication** đã tạo từ JWT, có authorities và principal.
- `Authentication#getName()`: tên principal được Spring Security chọn; mặc định thường dựa trên `sub`, nhưng có thể tùy chỉnh.
- `@AuthenticationPrincipal`: lấy **`authentication.getPrincipal()`**, không lấy nguyên đối tượng Authentication.

### 2.3. Luồng từ Bearer token đến tham số controller

~~~mermaid
flowchart TD
    A["HTTP Authorization: Bearer JWT"] --> B["FilterChainProxy / SecurityFilterChain"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D["JwtAuthenticationProvider"]
    D --> E["JwtDecoder xác minh JWS và JWT validators"]
    E --> F{"Token hợp lệ?"}
    F -->|Không| G["Authentication failure / thường 401"]
    F -->|Có| H["JwtAuthenticationConverter"]
    H --> I["JwtAuthenticationToken"]
    I --> J["SecurityContextHolder"]
    J --> K["AuthorizationFilter kiểm tra authorities"]
    K --> L{"Được phép truy cập?"}
    L -->|Không| M["Thường 403"]
    L -->|Có| N["Spring MVC Controller"]
    N --> O["@AuthenticationPrincipal Jwt"]
    O --> P["Đọc claims và xử lý nghiệp vụ"]
~~~

Sơ đồ rút gọn; trong ứng dụng còn có filter khác như CORS, CSRF, anonymous authentication và exception handling. **Controller chỉ được gọi sau khi request vượt qua các filter và policy áp dụng.**

Việc chuyển từ `Authentication` sang tham số `@AuthenticationPrincipal` do cơ chế giải quyết tham số của Spring MVC với Spring Security thực hiện (ví dụ `AuthenticationPrincipalArgumentResolver`), không phải do Spring tự giải mã token một lần nữa tại mỗi method.

## 3. Thiết lập Resource Server JWT để dùng `@AuthenticationPrincipal Jwt`

### 3.1. Dependencies

Ví dụ Gradle với Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Sử dụng version Spring Boot/Spring Security tương thích trong dự án. Đường đi này dành cho **Servlet stack**; với WebFlux sẽ sử dụng APIs/configuration của reactive security.

### 3.2. Cấu hình issuer và audience

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          audiences:
            - orders-api
~~~

Các địa chỉ và tên audience là ví dụ. `issuer-uri` phải khớp `iss` thực tế của access token; `audiences` ràng buộc token với API theo những phiên bản Spring Boot hỗ trợ property này.

Một access token được ký hợp lệ bởi đúng issuer nhưng có `aud = billing-api` không phải access token dành cho Orders API. Kiểm tra chữ ký/issuer mà bỏ qua audience có thể dẫn đến **cross-service token confusion**.

### 3.3. `SecurityFilterChain`

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Để ví dụ `GET /api/orders` khớp rule trong mọi cấu hình path matcher, có thể dùng cả `"/api/orders"` và `"/api/orders/**"`. Ở bài này controller `/api/me` được bảo vệ bởi `anyRequest().authenticated()`.

Khi chain nhận JWT hợp lệ, Spring Security tạo principal kiểu `Jwt`. Nếu JWT sai chữ ký, hết hạn, sai issuer hoặc sai audience theo validator, request thường bị trả **401 Unauthorized** trước khi controller được gọi. Khi token hợp lệ nhưng thiếu `SCOPE_orders.read` cho endpoint cần quyền đó, thường nhận **403 Forbidden**.

**Lưu ý quan trọng:** Ví dụ không chủ động vô hiệu hóa CSRF vì không có yêu cầu đó trong bài. Khi thiết kế API stateless hoàn toàn chỉ dùng Bearer header và không có xác thực bằng cookie, có thể đánh giá cấu hình CSRF riêng theo threat model. Không nên tắt CSRF bừa bãi chỉ để một ví dụ POST chạy được.

## 4. Truy cập claims thông dụng với accessor chuyên dụng

Một controller có thể lấy các giá trị chuẩn từ `Jwt`:

~~~java
package com.example.orders.api;

import java.time.Instant;
import java.net.URL;
import java.util.List;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/api/me")
    public IdentityResponse me(@AuthenticationPrincipal Jwt jwt) {
        return new IdentityResponse(
            jwt.getSubject(),
            jwt.getIssuer() == null ? null : jwt.getIssuer().toString(),
            jwt.getAudience(),
            jwt.getIssuedAt(),
            jwt.getExpiresAt()
        );
    }

    public record IdentityResponse(
        String subject,
        String issuer,
        List<String> audiences,
        Instant issuedAt,
        Instant expiresAt
    ) {}
}
~~~

`Jwt#getIssuer()` trả về `java.net.URL` trong một số cách mô tả? **Trong API Spring Security `Jwt#getIssuer()` trả về `java.net.URL` hay `java.net.URI` theo phiên bản; đoạn ví dụ chỉ dùng `toString()`**, nên không phụ thuộc vào cách biểu diễn cụ thể trong method return của controller. Không cần import `URL` trong ví dụ nếu IDE báo không sử dụng.

Những accessor quan trọng:

| Accessor của `Jwt` | Claim | Kiểu Java thường gặp | Ý nghĩa |
|---|---|---|---|
| `getSubject()` | `sub` | `String` | Chủ thể token |
| `getIssuer()` | `iss` | `URL` | Issuer sau chuyển đổi |
| `getAudience()` | `aud` | `List<String>` | Các audience token hướng tới |
| `getExpiresAt()` | `exp` | `Instant` | Thời điểm hết hạn |
| `getNotBefore()` | `nbf` | `Instant` | Thời điểm bắt đầu hợp lệ |
| `getIssuedAt()` | `iat` | `Instant` | Thời điểm phát hành |
| `getId()` | `jti` | `String` | JWT ID nếu có |
| `getClaimAsString("client_id")` | `client_id` | `String` hoặc `null` | OAuth 2.0 client ID theo hợp đồng |

`Jwt` cũng hỗ trợ `getClaims()` để lấy map tên claim sang giá trị, `getClaim(String)` để lấy từng claim và một số accessor có chuyển kiểu (`getClaimAsStringList`, `getClaimAsInstant`, ...).

**Chú ý về kiểu:** sau `JwtDecoder`, claims chuẩn có thể được Spring Security **chuẩn hóa kiểu Java**. `exp`/`iat` thường là `Instant`; `aud` có thể được chuẩn hóa thành danh sách String. Đừng kỳ vọng kiểu JSON gốc còn nguyên trong mọi trường hợp.

### 4.1. Chỉ trả về dữ liệu API thực sự cần

Ví dụ trên trả metadata để dạy cách truy cập claims. Trong production, **không nên tạo endpoint tùy ý trả toàn bộ JWT claims** vì JWS payload có thể chứa thông tin người dùng, tenant hoặc metadata nội bộ.

Một response profile được rút gọn an toàn hơn:

~~~java
@GetMapping("/api/profile")
public ProfileResponse profile(@AuthenticationPrincipal Jwt jwt) {
    return new ProfileResponse(
        jwt.getSubject(),
        jwt.getClaimAsString("preferred_username")
    );
}

public record ProfileResponse(
    String id,
    String displayName
) {}
~~~

Endpoint profile có thể hiển thị `preferred_username`, nhưng khi thực hiện kiểm tra quyền hoặc tra cứu dữ liệu, **không nên dựa vào display name như định danh bất biến**.

## 5. Tên và kiểu claims: những điều cần phân biệt

### 5.1. `getClaim(...)` và `getClaimAsString(...)`

Giả sử issuer phát hành custom claim:

~~~json
{
  "tenant_id": "tenant-42",
  "account_tier": "enterprise",
  "feature_flags": ["orders-search", "exports"],
  "login_count": 12
}
~~~

Có thể đọc:

~~~java
Object rawTenant = jwt.getClaim("tenant_id");
String tenant = jwt.getClaimAsString("tenant_id");
List<String> features = jwt.getClaimAsStringList("feature_flags");
~~~

Các helper `getClaimAs...` thuận tiện khi contract của claim đã được xác định và decoder đã chuẩn hóa kiểu phù hợp. Tuy nhiên, khi claim **quyết định phạm vi dữ liệu/quyền truy cập**, không nên dựa vào ép kiểu ngầm để chữa một token sai contract.

Ví dụ nguy hiểm:

~~~java
// Không nên dùng cho claim bảo mật khi cần type contract nghiêm ngặt:
String tenant = String.valueOf(jwt.getClaim("tenant_id"));
~~~

Nếu issuer gửi `tenant_id: 42` hoặc `tenant_id: null`, `String.valueOf(...)` có thể tạo chuỗi `"42"` hoặc `"null"`, vô tình vượt qua logic nghiệp vụ vốn đòi String thực sự.

### 5.2. Đọc custom claim an toàn khi bắt buộc là String

Nếu hợp đồng bắt buộc `tenant_id` là String không rỗng, có thể viết helper:

~~~java
package com.example.orders.security;

import org.springframework.security.oauth2.jwt.Jwt;

public final class JwtClaims {

    private JwtClaims() {}

    public static String requiredTenantId(Jwt jwt) {
        Object value = jwt.getClaims().get("tenant_id");

        if (value instanceof String tenantId && !tenantId.isBlank()) {
            return tenantId;
        }

        throw new IllegalStateException(
            "A validated access token must have tenant_id");
    }
}
~~~

**Điều kiện ngữ cảnh:** helper chỉ nên được gọi **sau authentication**. Đối với claim bắt buộc dùng để quyết định quyền, phương án tốt hơn là **validator trong `JwtDecoder` từ chối token thiếu/sai kiểu trước khi controller chạy**. Khi đó, controller không phải tự quyết định lỗi xác thực.

Nếu helper ở trên ném `IllegalStateException` trong controller, response có thể thành **500** nếu không có handler. Vì vậy đoạn code trên minh họa **type-safe access và invariant** chứ không phải đầy đủ error-handling production. Phần dưới sẽ cho ví dụ kiểm tra `tenant_id` ngay ở JWT validation.

### 5.3. Đọc claim danh sách

Giả sử claim:

~~~json
{
  "groups": ["support", "orders-team"],
  "roles": ["ORDER_READER", "ORDER_EDITOR"]
}
~~~

Để biết một claim thực sự là collection String theo contract:

~~~java
public static List<String> roles(Jwt jwt) {
    Object raw = jwt.getClaims().get("roles");

    if (raw == null) {
        return List.of(); // Chỉ hợp lệ nếu roles là optional trong contract.
    }

    if (!(raw instanceof List<?> values)) {
        throw new IllegalArgumentException(
            "roles must be a JSON array");
    }

    for (Object value : values) {
        if (!(value instanceof String role) || role.isBlank()) {
            throw new IllegalArgumentException(
                "roles must contain non-empty strings");
        }
    }

    return values.stream()
        .map(String.class::cast)
        .toList();
}
~~~

Import `java.util.List`. Nếu hợp đồng coi `roles` là **claim bảo mật**, hãy chuyển kiểm tra này vào validator hoặc converter đã kiểm soát trước khi cấp Authentication/authorities. Code ở đây nhằm làm rõ phân biệt **array String** với **String đơn, array hỗn hợp hoặc Number**.

Không tự coi `"ROLE_ADMIN"` ở custom claim là quyền hợp lệ chỉ vì token có chữ ký đúng. Issuer và API phải thống nhất ý nghĩa role, tên role và cách ánh xạ sang Spring authorities.

### 5.4. Missing, null, empty và sai kiểu

Xét custom claim `tenant_id`:

| Payload | Điều gì xảy ra | Xử lý cho contract bắt buộc |
|---|---|---|
| Không có `tenant_id` | `jwt.getClaim("tenant_id")` thường là `null` | Từ chối token |
| `"tenant_id": null` | Giá trị null / có thể bị converter loại | Từ chối token |
| `"tenant_id": ""` | String rỗng | Từ chối token |
| `"tenant_id": 42` | Number | Từ chối token |
| `"tenant_id": ["tenant-42"]` | Array | Từ chối token |
| `"tenant_id": "tenant-42"` | String không rỗng | Có thể hợp lệ theo các điều kiện khác |

Đối với claim **không liên quan quyền**, ví dụ `locale` để định dạng ngôn ngữ, fallback có thể chấp nhận được:

~~~java
public static String localeForDisplay(Jwt jwt) {
    Object raw = jwt.getClaims().get("locale");

    if (raw instanceof String locale) {
        return switch (locale) {
            case "vi-VN", "en-US" -> locale;
            default -> "vi-VN";
        };
    }

    return "vi-VN";
}
~~~

Nguyên tắc là **fallback không được cấp thêm quyền**. Không tự thay tenant thiếu bằng `"global"`, thay subject thiếu bằng email hoặc tự thêm scope mặc định.

## 6. `@AuthenticationPrincipal` được resolve ra sao?

### 6.1. Spring MVC argument resolution

Khi controller khai báo:

~~~java
@GetMapping("/api/me")
public String me(@AuthenticationPrincipal Jwt jwt) {
    return jwt.getSubject();
}
~~~

Spring Security tích hợp Spring MVC thông qua một **argument resolver**. Về khái niệm, resolver lấy:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

Object principal = authentication == null
    ? null
    : authentication.getPrincipal();
~~~

Sau đó cố gắng cung cấp principal cho tham số kiểu `Jwt`.

Cách inject này **không tải token mới từ issuer**, không gọi JWKS lần nữa và không thực hiện xác thực JWT riêng trong controller. Authentication đã được xử lý trong security filters trước đó.

### 6.2. Nếu request chưa có principal thì sao?

Ở endpoint `permitAll`, request có thể không gửi Bearer token. Khi đó:

- `Authentication` có thể là anonymous authentication hoặc absent tùy cấu hình.
- Principal có thể không phải `Jwt` (chẳng hạn anonymous principal là String).
- `@AuthenticationPrincipal Jwt` có thể nhận `null` khi kiểu principal không khớp và thuộc tính mặc định không yêu cầu lỗi ngay.

Ví dụ một endpoint công khai muốn phản hồi khác nhau theo JWT:

~~~java
@GetMapping("/api/public/greeting")
public Map<String, String> greeting(
        @AuthenticationPrincipal Jwt jwt) {

    if (jwt == null) {
        return Map.of("message", "Hello, guest");
    }

    return Map.of("message", "Hello, " + jwt.getSubject());
}
~~~

Đây là ví dụ cho **tham số nullable** ở endpoint công khai. Không áp dụng logic “jwt null thì xem như khách, vẫn cho truy cập dữ liệu riêng” cho endpoint yêu cầu xác thực.

**Điểm tinh tế:** `permitAll` không tự bỏ qua `BearerTokenAuthenticationFilter`. Nếu request đến endpoint công khai nhưng gửi một Bearer token sai, filter có thể trả **401** trước khi controller được gọi. Trường hợp không token mới có thể đi tiếp theo chính sách `permitAll`.

### 6.3. `errorOnInvalidType`

Annotation hỗ trợ yêu cầu lỗi khi principal có kiểu không tương thích:

~~~java
@GetMapping("/api/strict-profile")
public String strictProfile(
        @AuthenticationPrincipal(errorOnInvalidType = true) Jwt jwt) {
    return jwt.getSubject();
}
~~~

Khi principal tồn tại nhưng không phải `Jwt`, thay vì trả `null` do type mismatch, resolver có thể ném exception (ví dụ `ClassCastException`). Thuộc tính này **không phải một cơ chế authentication** và không thay thế policy `authenticated()`/scope ở filter chain.

Thông thường nên để API protected đảm bảo đúng cơ chế JWT và dùng code rõ ràng thay vì kỳ vọng `errorOnInvalidType` là chốt chặn bảo mật.

### 6.4. Biểu thức `expression` trên annotation

`@AuthenticationPrincipal` hỗ trợ SpEL để lấy một thuộc tính của principal.

Ví dụ chỉ cần subject:

~~~java
@GetMapping("/api/subject")
public Map<String, String> subject(
        @AuthenticationPrincipal(expression = "subject") String subject) {

    return Map.of("subject", subject);
}
~~~

Hoặc lấy một custom claim từ `Jwt`:

~~~java
@GetMapping("/api/tenant-label")
public Map<String, String> tenantLabel(
        @AuthenticationPrincipal(
            expression = "claims['tenant_id']"
        ) String tenantId) {

    return Map.of("tenant", tenantId);
}
~~~

Các expression chạy trên **principal** được lấy từ Authentication. Với `Jwt`, property `subject` tương ứng `getSubject()`, còn `claims['tenant_id']` tra trong map claims.

**Lưu ý khi dùng expression:**

- Claim không có hoặc principal không phải `Jwt` có thể khiến giá trị null hoặc expression không áp dụng được.
- `Map.of(...)` không chấp nhận null; ví dụ chỉ phù hợp khi `sub`/`tenant_id` đã được bảo đảm bởi validator và endpoint protected.
- Với logic business phức tạp, **tiêm nguyên `Jwt` và kiểm tra typed claim trong service** thường rõ hơn SpEL dài trong annotation.
- Không dùng expression để tự cấp scope hay bỏ qua validator.

Ví dụ `@AuthenticationPrincipal(expression = "claims['tenant_id']")` chỉ **đọc claim**, không tự chứng minh rằng token hợp lệ với tenant đó và không kiểm tra tenant sở hữu bản ghi.

## 7. Dùng `Authentication` khi cần authorities thay vì chỉ claims

Một controller có thể nhận `Authentication` trực tiếp:

~~~java
@GetMapping("/api/access")
public AccessInfo access(Authentication authentication) {
    return new AccessInfo(
        authentication.getName(),
        authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList()
    );
}

public record AccessInfo(String name, List<String> authorities) {}
~~~

Imports:

~~~java
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
~~~

Đoạn này minh họa cách đọc **authorities đã được Spring Security gắn vào Authentication**, không đọc raw `scope` rồi tự suy quyền.

### 7.1. Claims và authorities khác nhau

Ví dụ JWT:

~~~json
{
  "scope": "orders.read orders.write",
  "roles": ["ORDER_ADMIN"]
}
~~~

Trong cấu hình JWT Resource Server thông thường, các scopes có thể thành:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Claim `roles` **không mặc nhiên** trở thành `ROLE_ORDER_ADMIN`. Muốn ánh xạ custom roles, ứng dụng cần cấu hình converter và chính sách tin cậy/allowlist phù hợp.

Bảo vệ endpoint bằng:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

an toàn hơn việc controller tự viết:

~~~java
// Không khuyến khích là lớp bảo vệ chính của endpoint:
if (jwt.getClaimAsString("scope").contains("orders.read")) {
    // ...
}
~~~

Vì so chuỗi bằng `contains` có thể có false positive (ví dụ `orders.read.all`), không thống nhất với authority mapping và dễ bỏ qua các trường hợp token sai schema.

### 7.2. `Authentication#getName()` không phải luôn là `sub`

`JwtAuthenticationConverter` có thể đặt claim nào được dùng làm principal name, ví dụ `preferred_username` thay cho `sub`. Khi đó:

~~~java
authentication.getName()
~~~

có thể khác:

~~~java
jwt.getSubject()
~~~

Nếu identity key cho cơ sở dữ liệu phải là `sub`, hãy nêu rõ trong hợp đồng và dùng `jwt.getSubject()` hoặc một identity abstraction có ràng buộc issuer phù hợp. Không suy ra tính bất biến của `preferred_username`.

### 7.3. Khi nào nên dùng `@AuthenticationPrincipal Jwt`?

| Mục tiêu controller | Tham số phù hợp |
|---|---|
| Đọc `sub`, `iss`, `tenant_id` từ JWT | `@AuthenticationPrincipal Jwt` |
| Đọc name và authorities của Authentication | `Authentication` |
| Đọc subject trực tiếp, method ngắn | `@AuthenticationPrincipal(expression = "subject") String` |
| Endpoint OIDC login/session, principal là OIDC user | `@AuthenticationPrincipal OidcUser` |
| Resource Server nhận opaque token | `@AuthenticationPrincipal OAuth2AuthenticatedPrincipal` hoặc `Authentication` |
| Nghiệp vụ không nên phụ thuộc trực tiếp Spring Security | Truyền identity DTO/context đã được service an toàn tạo từ principal |

Đừng ép một ứng dụng dùng nhiều hình thức authentication chỉ để có cùng `Jwt` parameter. Cần chọn abstraction phù hợp mỗi security chain.

## 8. Resource Server JWT khác OIDC Login và opaque token

### 8.1. JWT Resource Server

Với cấu hình:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
);
~~~

thường có:

~~~text
Authentication: JwtAuthenticationToken
Principal:      Jwt
~~~

Đây là trường hợp chính dùng `@AuthenticationPrincipal Jwt`.

### 8.2. OIDC Login

Khi ứng dụng là **OIDC Client** và dùng:

~~~java
http.oauth2Login(Customizer.withDefaults());
~~~

principal thường là **`OidcUser`** (ví dụ `DefaultOidcUser`), không phải `Jwt` trực tiếp. Controller có thể dùng:

~~~java
@GetMapping("/web/me")
public String webMe(
        @AuthenticationPrincipal OidcUser oidcUser) {

    return oidcUser.getSubject();
}
~~~

Import `org.springframework.security.oauth2.core.oidc.user.OidcUser`.

Một `OidcUser` có thể chứa ID Token và UserInfo, nhưng **OIDC ID Token không phải OAuth 2.0 access token dùng để gọi Resource Server API**. Không thiết kế endpoint nhận ID Token dưới dạng Bearer chỉ để có các claim danh tính giống login.

### 8.3. Opaque access token

Nếu API cấu hình:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults())
);
~~~

Spring Security dùng token introspection thay vì giải mã JWT. Principal thông thường thuộc **`OAuth2AuthenticatedPrincipal`**, không phải `Jwt`.

Có thể khai báo:

~~~java
@GetMapping("/api/opaque-me")
public Map<String, String> opaqueMe(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

    return Map.of(
        "name",
        principal.getName()
    );
}
~~~

Import `org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal`.

Claim và loại thuộc tính introspection phụ thuộc Authorization Server; không áp dụng máy móc các accessor `Jwt#getSubject()`, `getAudience()` lên opaque principal.

### 8.4. Nhiều SecurityFilterChain

Nếu cùng ứng dụng có chain `/api/**` dùng JWT và chain `/web/**` dùng OIDC login/session, principal có thể khác kiểu theo request. `FilterChainProxy` chọn chain theo `securityMatcher` và `@Order`; **đừng** dùng một controller giả định mọi request đều có `Jwt` nếu endpoint có thể được truy cập qua nhiều loại authentication.

Tách endpoint và service identity model giúp tránh lỗi type mismatch.

## 9. Xác minh claims trước controller: lỗi token thuộc authentication

### 9.1. Vì sao không chỉ kiểm tra `tenant_id` trong controller?

Giả sử Orders API là hệ thống đa tenant và mọi access token dành cho API đều phải có:

~~~json
{
  "tenant_id": "tenant-42"
}
~~~

Nếu chỉ đọc bằng:

~~~java
String tenant = jwt.getClaimAsString("tenant_id");
~~~

và cho phép tenant null tự chuyển thành tenant chung, ứng dụng có thể vô tình vượt phạm vi tenant. Nếu code ném exception chung khi thiếu claim, HTTP 500 có thể xuất hiện sau khi request đã được xác thực.

Hợp đồng **claim bắt buộc để định danh/phân vùng dữ liệu** nên được đưa vào **`OAuth2TokenValidator<Jwt>`** để từ chối token không hợp lệ **trước khi controller chạy**.

### 9.2. Validator bắt buộc `tenant_id`

Ví dụ tự cấu hình decoder với issuer và JWKS URI đã được tin cậy:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtContractConfig {

    private static final String ISSUER =
        "https://id.example.test/realms/shop";

    private static final String JWKS_URI =
        "https://id.example.test/realms/shop/protocol/openid-connect/certs";

    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS_URI)
            .build();

        OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return invalid("Access token audience is not orders-api");
        };

        OAuth2TokenValidator<Jwt> tenantValidator = jwt -> {
            Object raw = jwt.getClaims().get("tenant_id");
            if (raw instanceof String tenantId && !tenantId.isBlank()) {
                return OAuth2TokenValidatorResult.success();
            }
            return invalid("Missing or invalid tenant_id");
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                standard,
                audienceValidator,
                tenantValidator
            )
        );

        return decoder;
    }

    private static OAuth2TokenValidatorResult invalid(String reason) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", reason, null)
        );
    }
}
~~~

Đoạn này dùng `NimbusJwtDecoder.withJwkSetUri(...)`, nên chủ động giữ **`JwtValidators.createDefaultWithIssuer(ISSUER)`** cùng các validator audience và tenant. Nếu ứng dụng đang tự động cấu hình decoder bằng properties Spring Boot, tạo bean mới có thể khiến phần auto configuration decoder **nhường chỗ** cho bean tùy chỉnh; khi đó không được mặc định rằng property `audiences` hoặc custom validation cũ vẫn tự được áp dụng.

**Lưu ý về kiểu JSON gốc:** `OAuth2TokenValidator<Jwt>` nhận claims sau khi decoder có thể chuẩn hóa kiểu. Với custom `tenant_id` thông thường nó vẫn phản ánh kiểu String/Number/Array, nhưng nếu hợp đồng đòi kiểm tra tuyệt đối kiểu JSON gốc của registered claims, phải xem xét conversion/parser phù hợp. Không dùng ép kiểu chung để chữa token sai schema.

### 9.3. HTTP status khi validator thất bại

Nếu `tenant_id` là claim bắt buộc của hợp đồng token, token thiếu hoặc sai claim phải bị từ chối ở **authentication**, thường dẫn đến:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Nếu token hợp lệ nhưng không có authority cần thiết của endpoint, `AuthorizationFilter` từ chối và thường trả:

~~~http
HTTP/1.1 403 Forbidden
~~~

Không nên trả 403 cho một token thực tế chưa thỏa hợp đồng authentication mà controller tự phát hiện. Lỗi 403 phù hợp với **đã xác thực nhưng thiếu quyền**.

## 10. Dùng `Jwt` an toàn trong API đa tenant

### 10.1. Claims cung cấp identity context, không thay thế quyền tài nguyên

Giả sử JWT có:

~~~json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-42"
}
~~~

Và request:

~~~http
GET /api/orders/9001 HTTP/1.1
Authorization: Bearer <VALID_ACCESS_TOKEN>
~~~

Endpoint yêu cầu `SCOPE_orders.read`. Tuy nhiên, có scope này mới chỉ cho biết caller có quyền đọc đơn hàng theo **chính sách API tổng quát**.

Nếu order 9001 thuộc `tenant-99`, người dùng từ `tenant-42` không được xem nó, trừ khi hệ thống có một chính sách cross-tenant được thiết kế tường minh.

### 10.2. Mẫu controller + service ràng buộc tenant

~~~java
package com.example.orders.api;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/orders")
public class OrdersController {

    private final OrdersService ordersService;

    public OrdersController(OrdersService ordersService) {
        this.ordersService = ordersService;
    }

    @GetMapping("/{orderId}")
    public OrderResponse order(
            @PathVariable long orderId,
            @AuthenticationPrincipal Jwt jwt) {

        // Có validator bắt buộc tenant_id tại decoder.
        String tenantId =
            (String) jwt.getClaims().get("tenant_id");

        String subject = jwt.getSubject();

        return ordersService.findOrderForCaller(
            orderId, tenantId, subject
        );
    }
}
~~~

Service minh họa:

~~~java
public OrderResponse findOrderForCaller(
        long orderId,
        String tenantId,
        String subject) {

    Order order = repository.findByIdAndTenantId(orderId, tenantId)
        .orElseThrow(() ->
            new ResponseStatusException(HttpStatus.NOT_FOUND));

    // Nếu contract yêu cầu quyền theo từng người dùng,
    // kiểm tra owner/ACL ở đây, không dựa vào scope đơn thuần.
    if (!permissionService.canRead(subject, order)) {
        throw new ResponseStatusException(HttpStatus.FORBIDDEN);
    }

    return orderMapper.toResponse(order);
}
~~~

Các class `OrdersService`, `OrderResponse`, `Order`, `repository`, `permissionService` và `orderMapper` là những thành phần nghiệp vụ minh họa, cần được triển khai theo dữ liệu thực tế. Controller giả định `JwtDecoder` đã kiểm tra `tenant_id` là String không rỗng và `sub` phù hợp với hợp đồng; nếu chưa có các validators đó, cần xử lý null/sai kiểu trước khi gọi service.

**Điểm quan trọng:** repository truy vấn theo **cả order ID và tenant ID**. Không lấy một order bất kỳ bằng ID rồi chỉ dựa vào tên hiển thị của người dùng trong JWT để quyết định. Truy vấn theo tenant (và quyền owner/ACL) giúp giảm nguy cơ lộ dữ liệu qua ID có thể đoán.

### 10.3. Subject có phải luôn là người dùng không?

Không nhất thiết. Với **Authorization Code** token, `sub` thường đại diện người dùng. Với **Client Credentials** access token, `sub` có thể đại diện cho **client/service** theo profile của issuer.

Vì vậy, hãy xác định loại principal theo grant/token profile và hợp đồng API. Không tự gọi mọi `sub` là user ID hoặc tra bảng user với một machine principal nếu API nhận cả machine-to-machine token.

Khi tạo khóa định danh, tổ hợp **issuer + subject** có thể cần thiết để tránh trùng subject giữa nhiều issuer. Với single-issuer API, subject có thể được xem trong ngữ cảnh issuer đã xác minh; với multi-issuer, phải giữ ranh giới này.

## 11. Có nên truyền `Jwt` xuống mọi lớp service không?

### 11.1. Cách nhanh: controller dùng `Jwt`

Ở ứng dụng nhỏ, controller có thể:

~~~java
@GetMapping("/api/me")
public String subject(@AuthenticationPrincipal Jwt jwt) {
    return jwt.getSubject();
}
~~~

Đây là cách gọn để hiển thị hoặc sử dụng vài claims đơn giản, miễn các điều kiện xác thực và kiểu claim đã được bảo đảm.

### 11.2. Cách bền vững: chuyển thành identity abstraction

Ở ứng dụng nghiệp vụ lớn, truyền nguyên `Jwt` khắp service/repository có thể gây **coupling** vào Spring Security và cấu trúc token của issuer.

Có thể tạo một kiểu nhỏ chỉ chứa thông tin cần thiết:

~~~java
package com.example.orders.identity;

public record CallerIdentity(
    String issuer,
    String subject,
    String tenantId
) {}
~~~

Factory:

~~~java
package com.example.orders.identity;

import org.springframework.security.oauth2.jwt.Jwt;

public final class CallerIdentityFactory {

    private CallerIdentityFactory() {}

    public static CallerIdentity fromValidatedJwt(Jwt jwt) {
        // Contract validators đã bảo đảm iss, sub, tenant_id.
        return new CallerIdentity(
            jwt.getIssuer().toString(),
            jwt.getSubject(),
            (String) jwt.getClaims().get("tenant_id")
        );
    }
}
~~~

Controller:

~~~java
@GetMapping("/api/orders")
public List<OrderResponse> myOrders(
        @AuthenticationPrincipal Jwt jwt) {

    CallerIdentity caller =
        CallerIdentityFactory.fromValidatedJwt(jwt);

    return ordersService.findOrdersForCaller(caller);
}
~~~

Lợi ích:

- Service không phải tự parse JWT.
- Khi provider đổi tên custom claim, thay đổi tập trung ở adapter/factory.
- Unit test service có thể dùng identity DTO thay JWT token.
- Dễ phân biệt `subject`, `tenantId` và issuer hơn là truyền một `Map<String, Object>` không có kiểu.

Tuy vậy, identity abstraction **không tự cấp quyền**. Service vẫn phải thực hiện kiểm tra scope/authority ở controller/method security và quyền đối tượng theo policy.

### 11.3. Tránh dùng `SecurityContextHolder` khắp nơi

Có thể đọc:

~~~java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
~~~

Nhưng nếu service liên tục lấy global/thread-local context, code sẽ khó test và dễ sai khi có async processing. Truyền một `CallerIdentity` từ boundary đã xác thực vào service thường rõ ràng hơn.

Không giữ `Authentication` hoặc `Jwt` trong static mutable field, cache toàn cục cho “current user”, hoặc dùng chúng ngoài lifecycle request nếu không có cơ chế truyền context an toàn.

## 12. Xử lý anonymous/null và response đúng HTTP

### 12.1. Endpoint protected

Nếu `GET /api/me` yêu cầu `authenticated()` và API chỉ chấp nhận JWT Bearer, request không có hoặc token sai thường bị Spring Security từ chối **trước khi controller chạy**.

~~~http
GET /api/me HTTP/1.1
~~~

Thường nhận:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Vì vậy, code:

~~~java
@GetMapping("/api/me")
public String me(@AuthenticationPrincipal Jwt jwt) {
    return jwt.getSubject();
}
~~~

dựa trên giả định `SecurityFilterChain` đã bảo vệ endpoint và không có một cơ chế xác thực khác tạo principal kiểu khác. Khi có custom chain, multiple auth mechanisms hoặc public endpoint, cần xử lý kiểu/khả năng null rõ ràng.

### 12.2. Endpoint công khai nhưng hiển thị thông tin tùy token

Ở endpoint `permitAll`:

~~~java
@GetMapping("/api/public/welcome")
public String welcome(@AuthenticationPrincipal Jwt jwt) {
    return jwt == null
        ? "Welcome, guest"
        : "Welcome, " + jwt.getSubject();
}
~~~

Đây là logic hiển thị. Không dùng pattern này để cho anonymous caller xem dữ liệu riêng.

**Lưu ý:** Bearer token *có mặt nhưng sai* có thể dẫn đến 401 trước controller, kể cả endpoint `permitAll`.

### 12.3. Khi claim bắt buộc thiếu, xử lý ở đâu?

| Vấn đề | Tầng thích hợp | HTTP thường gặp |
|---|---|---|
| Không có token cho endpoint bảo vệ | Security filters / entry point | 401 |
| Token sai chữ ký/hết hạn/sai issuer/audience | JwtDecoder / validator | 401 |
| Thiếu custom claim bắt buộc cho token contract | `OAuth2TokenValidator<Jwt>` | 401 |
| Token hợp lệ nhưng thiếu `SCOPE_orders.read` | Authorization rules | 403 |
| Token hợp lệ, scope đủ nhưng không được xem order cụ thể | Service/ownership policy | 403 hoặc 404 |
| Claim UI tùy chọn thiếu như `locale` | Controller/presentation | Fallback an toàn |
| Principal không phải `Jwt` do đi nhầm auth chain | Kiểm tra security architecture | Sửa cấu hình/guard thích hợp |

Không nên đưa lỗi claim bắt buộc tới controller rồi trả 200 với dữ liệu rỗng hoặc global default. Nhưng cũng không cần biến mọi claim hiển thị tùy chọn thành điều kiện để JWT hợp lệ.

## 13. `@AuthenticationPrincipal` và method security

Các endpoint thường dùng `authorizeHttpRequests` để ràng buộc scope trước khi controller chạy:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().authenticated()
);
~~~

Ngoài ra, service có thể dùng method security khi đã bật:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {}
~~~

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderResponse loadOrder(long orderId, CallerIdentity caller) {
    return findOrderForCaller(orderId, caller.tenantId(), caller.subject());
}
~~~

Imports:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.access.prepost.PreAuthorize;
~~~

**Nhớ rằng `@AuthenticationPrincipal Jwt` chỉ cung cấp principal, không phải một quy tắc authorization.** Method security và URL security phải dùng các authorities/policy phù hợp. Nếu cần kiểm tra quyền theo tenant/owner, nên làm tại service hoặc một authorization manager chuyên dụng đã được thiết kế rõ.

Đừng lấy raw `scope` từ JWT rồi dùng `String.contains(...)` để quyết định phân quyền. Spring Security đã cung cấp authority mapping và `hasAuthority(...)`, tránh lỗi match chuỗi con hoặc token schema không thống nhất.

## 14. Kiểm thử controller có `@AuthenticationPrincipal Jwt`

### 14.1. Hai mức kiểm thử khác nhau

Có ít nhất hai phạm vi:

1. **Kiểm thử controller/authorization**: tạo mock principal `Jwt` để kiểm tra injection và response.
2. **Kiểm thử toàn bộ JWT Resource Server**: gửi Bearer header thật qua filter chain, xác minh decoder/issuer/JWKS/audience/claims.

Spring Security Test có helper `jwt()` để mock JWT authentication trong MockMvc. Nó rất hữu ích cho (1) nhưng **không tự chứng minh JWT signature, issuer, JWKS fetch và audience validator thực sự chạy**.

### 14.2. Ví dụ MockMvc với mock JWT

Dependency test:

~~~groovy
testImplementation 'org.springframework.security:spring-security-test'
~~~

Ví dụ phương thức test:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void returnsPrincipalSubject() throws Exception {
    mvc.perform(get("/api/me").with(jwt().jwt(token -> token
            .subject("user-123")
            .claim("tenant_id", "tenant-42")
        )))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject").value("user-123"));
}
~~~

Ví dụ giả định `mvc` là field `MockMvc` đã được thiết lập và endpoint `/api/me` trả JSON chứa `subject` như controller trước đó. Trong code thực tế, static imports có thể được viết trên một dòng nếu style checker yêu cầu.

### 14.3. Test scope/authorities

Nếu endpoint cần `SCOPE_orders.read`:

~~~java
mvc.perform(get("/api/orders/42").with(
    jwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")
    )
));
~~~

Import:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
~~~

Test này mô phỏng caller có authority. Nó không kiểm tra xem một access token với claim `scope` có thực sự được converter ánh xạ thành authority đó hay không.

Để kiểm tra **converter**, cần test `JwtAuthenticationConverter`. Để kiểm tra **JWT validation**, cần test decoder với JWT test được ký bằng khóa test và một JWKS source kiểm soát được hoặc test integration tương ứng.

### 14.4. Các trường hợp nên có

| Tình huống | Kết quả mong đợi |
|---|---|
| `/api/me` có JWT hợp lệ | Principal `Jwt` được tiêm, trả subject |
| Không token tại endpoint protected | 401 trước controller |
| Token sai chữ ký hoặc hết hạn | 401 trước controller |
| Token sai audience | 401 khi audience validator có cấu hình |
| JWT thiếu `tenant_id` bắt buộc | 401 tại validator, không tới service |
| JWT có `tenant_id` Number thay String | Từ chối theo contract |
| JWT hợp lệ thiếu scope cho order endpoint | 403 |
| JWT hợp lệ đủ scope nhưng khác tenant | 403/404 theo policy nghiệp vụ |
| Endpoint public không có JWT | `Jwt` nullable, response guest |
| Opaque token ở endpoint expecting `Jwt` | Thiết kế lại principal type, không ép kiểu |

Nếu chỉ dùng `@WithMockUser`, principal thường là `UserDetails`/String theo test setup, không phải `Jwt`. Với controller đòi `@AuthenticationPrincipal Jwt`, nên dùng mock JWT authentication thích hợp.

## 15. Những sai lầm thường gặp

### 15.1. Tự decode JWT trong controller

~~~java
String token = request.getHeader("Authorization");
String payload = new String(
    Base64.getUrlDecoder().decode(token.split("\\.")[1])
);
~~~

**Không an toàn khi dùng để xác thực**: payload Base64URL của JWS không được mã hóa bí mật; đọc được JSON không chứng minh chữ ký/issuer/audience hợp lệ. Đoạn trên còn không xử lý đúng scheme `Bearer ` và nhiều trường hợp token lỗi.

Hãy để `JwtDecoder` của Resource Server xác thực, rồi nhận `@AuthenticationPrincipal Jwt`.

### 15.2. Dùng `getClaimAsString` cho mọi dữ liệu bất kể contract

Claims có thể là String, Boolean, Number, Collection hoặc Object. Với claim bảo mật, kiểm tra đúng kiểu như hợp đồng, không ép tùy tiện và không tự cấp default mở rộng quyền.

### 15.3. Dùng `jwt.getTokenValue()` làm dữ liệu hiển thị/log

`getTokenValue()` trả về **access token thực**. Nó là bearer credential; ai sở hữu nó có thể thử gọi API theo quyền của token.

**Không** gửi lại token trong response `/api/me`, ghi vào log, message queue hoặc analytics chỉ để debug claims. Nếu cần quan sát lỗi, ưu tiên correlation ID và metadata không nhạy cảm.

### 15.4. Tưởng ID Token OIDC và JWT access token giống nhau

OIDC client có thể giữ `OidcUser` và ID Token, nhưng Resource Server cần **access token dành cho API**. Cùng một issuer và cùng định dạng JWT không khiến ID Token có thể dùng thay access token. Luôn kiểm tra audience và token type/profile.

### 15.5. Tưởng `@AuthenticationPrincipal Jwt` tự kiểm tra quyền

Annotation chỉ lấy principal từ `SecurityContext`. Nó không tự yêu cầu `orders.read`, không tra tenant và không đảm bảo người dùng được xem một bản ghi cụ thể.

### 15.6. Nhầm `Authentication#getName()` với identity key bất biến

Tên authentication có thể được converter lấy từ claim tùy chọn như `preferred_username`. Đối với key nghiệp vụ ổn định, dùng `sub` trong ngữ cảnh issuer đã tin cậy và theo hợp đồng token.

### 15.7. Mặc định claim nào cũng tồn tại

Không phải mọi JWT đều có `client_id`, `tenant_id`, `email`, `roles` hoặc `locale`. Một số claim là yêu cầu của profile RFC 9068 hoặc riêng của issuer, nhưng **đừng áp yêu cầu của một provider sang mọi token**. Hợp đồng của API phải định nghĩa chính xác claim bắt buộc/tùy chọn, giá trị và kiểu.

### 15.8. Tự cấp quyền vì custom `roles` xuất hiện

Claim `roles` chỉ có tác dụng phân quyền nếu hệ thống đã xây policy và converter/validator phù hợp. Không nhận những role string không được issuer/ứng dụng phê duyệt, cũng không tự động ánh xạ mọi role thành quyền admin.

### 15.9. Không xử lý nullable principal ở endpoint công khai

Ở `permitAll` không Bearer token, tham số `Jwt` có thể null. Code gọi thẳng `jwt.getSubject()` có thể gây 500. Nếu endpoint thật sự public, phải quyết định chính sách guest rõ ràng.

### 15.10. Dùng `SecurityContextHolder` trong background task tùy ý

SecurityContext thường gắn với lifecycle xử lý request/thread. Với asynchronous execution hoặc event processing, không giả định context của request tự tồn tại ở mọi thread. Hãy truyền identity context thích hợp và chỉ dùng context propagation được cấu hình chủ động.

## 16. Ví dụ thực hành: endpoint “Tôi là ai?”

### 16.1. Hợp đồng

Endpoint:

~~~http
GET /api/me
Authorization: Bearer <JWT_ACCESS_TOKEN>
~~~

Yêu cầu:

- Token phải được phát hành bởi `https://id.example.test/realms/shop`.
- `aud` phải chứa `orders-api`.
- `sub` là String không rỗng theo hợp đồng.
- `tenant_id` là String không rỗng.
- `preferred_username` là claim tùy chọn chỉ dùng hiển thị.
- Endpoint không trả nguyên JWT hoặc toàn bộ claims.

Response kỳ vọng:

~~~json
{
  "subject": "user-123",
  "tenantId": "tenant-42",
  "displayName": "phuong"
}
~~~

### 16.2. Controller

~~~java
package com.example.orders.api;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/api/me")
    public MeResponse me(@AuthenticationPrincipal Jwt jwt) {

        // Giả định JWT validators đã bảo đảm sub/tenant_id.
        String subject = jwt.getSubject();
        String tenantId = (String) jwt.getClaim("tenant_id");

        // Chỉ dùng cho UI; không dùng làm identity key.
        String displayName =
            jwt.getClaimAsString("preferred_username");

        return new MeResponse(subject, tenantId, displayName);
    }

    public record MeResponse(
        String subject,
        String tenantId,
        String displayName
    ) {}
}
~~~

Nếu `preferred_username` không có, `displayName` có thể null. Định dạng JSON null/omission phụ thuộc Jackson configuration; hợp đồng response cần ghi rõ nếu client quan tâm.

### 16.3. Gọi thử

~~~bash
curl -i \
  -H "Authorization: Bearer <VALID_ORDERS_ACCESS_TOKEN>" \
  https://api.example.test/api/me
~~~

Khi token hợp lệ và đủ claims, controller nhận `Jwt` và xây response. Các request sau bị từ chối trước controller theo cơ chế bảo mật thích hợp:

- Token giả hoặc chữ ký sai.
- Token hết hạn.
- Token có `iss` không khớp issuer tin cậy.
- Token có `aud` không chứa Orders API.
- Token thiếu `tenant_id` khi validator bắt buộc claim đó được bật.

Không nên test bằng cách lấy JWT production rồi sửa thẳng payload: việc sửa payload làm chữ ký sai; để test chính xác logic claims, dùng issuer test/keys test được quản lý.

## 17. Tóm lược các lựa chọn

| Nhu cầu | Giải pháp |
|---|---|
| Lấy `sub` của JWT đã xác thực | `@AuthenticationPrincipal Jwt jwt` rồi `jwt.getSubject()` |
| Lấy issuer, audience, thời hạn | `getIssuer()`, `getAudience()`, `getExpiresAt()` |
| Lấy custom claim | `getClaim("tenant_id")` hoặc helper phù hợp kiểu |
| Lấy một giá trị trực tiếp | `@AuthenticationPrincipal(expression = "subject")` |
| Lấy authorities/scope đã được chuyển đổi | Tiêm `Authentication`, dùng `getAuthorities()` |
| Custom claim bắt buộc với quyền/tenant | Validate bằng `OAuth2TokenValidator<Jwt>` trước controller |
| Endpoint public có thể không JWT | Xử lý `jwt == null` rõ ràng |
| OIDC login principal | `@AuthenticationPrincipal OidcUser` |
| Opaque token principal | `OAuth2AuthenticatedPrincipal` hoặc `Authentication` |
| Business logic dài, nhiều service | Chuyển `Jwt` sang `CallerIdentity`/context có kiểu |
| Quyền endpoint | `authorizeHttpRequests` hoặc method security |
| Quyền từng bản ghi | Service/repository kiểm tra owner/tenant/ACL |

**Điểm cốt lõi:** `@AuthenticationPrincipal Jwt` là cầu nối từ **JWT access token đã được Spring Security xác thực** đến **controller Spring MVC**. Nó làm cho code đọc claims đơn giản hơn, nhưng bản thân annotation **không thay thế JWT validation, không tự cấp quyền và không bảo đảm claims tùy chọn luôn tồn tại**.

### Tài liệu tham khảo

- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — Servlet MVC Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html)
- [Spring Security API — AuthenticationPrincipal](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/annotation/AuthenticationPrincipal.html)
- [Spring Security API — Jwt](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/Jwt.html)
- [Spring Security API — JwtAuthenticationToken](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationToken.html)
- [Spring Security API — JwtAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)

