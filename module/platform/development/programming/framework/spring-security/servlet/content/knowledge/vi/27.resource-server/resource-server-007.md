# Resource Server: ánh xạ scope sang authority và tùy chỉnh claims về quyền trong Spring Security Servlet

## 1. Mục tiêu: từ access token tới quyết định cho phép hay từ chối

Một **OAuth2 Resource Server** là API nhận **access token** (thường được gửi qua `Authorization: Bearer ...`) rồi xác minh token và quyết định người gọi có được truy cập tài nguyên hay không. Trong ứng dụng **Spring Boot 3.x + Spring Security 6.x, Servlet/Spring MVC, Java 17+**, quyết định này thường sử dụng **`GrantedAuthority`** được đưa vào `Authentication`.

Đề bài này tập trung vào hai việc:

1. Hiểu và dùng ánh xạ mặc định từ các scope trong access token sang authority có tiền tố **`SCOPE_`**.
2. Khi IdP phát thêm các claims chứa vai trò hoặc quyền nghiệp vụ, viết **converter tùy chỉnh** để đưa claims tin cậy thành các authority như `ROLE_ADMIN` và `PERM_orders:approve`, rồi kiểm tra quyền đúng cách ở URL và method.

Cần phân biệt rõ:

- **Scope**: phạm vi được cấp cho token/client, ví dụ `orders:read`, `orders:write`. Scope không tự đồng nghĩa với vai trò người dùng.
- **Role**: vai trò của chủ thể trong một ngữ cảnh, ví dụ `ADMIN`, `SUPPORT`; thường có tiền tố `ROLE_` khi dùng `hasRole`.
- **Permission**: quyền nghiệp vụ cụ thể, ví dụ `orders:approve`; có thể ánh xạ thành `PERM_orders:approve`.
- **Claim**: trường dữ liệu trong JWT, chẳng hạn `scope`, `scp`, `sub`, `aud`, `realm_access`, `permissions`. Một claim chỉ được tin cậy **sau khi token được xác minh hợp lệ** và đúng ngữ cảnh API.

**Không biến một string do request header/query/body tùy ý cung cấp thành authority.** Quyền phải xuất phát từ token đã qua xác minh, từ một kho quyền được tin cậy hoặc từ một quyết định phân quyền có kiểm soát.

## 2. Luồng xử lý ở Spring Security Servlet

Với JWT Bearer access token, luồng xử lý điển hình:

```text
HTTP GET /api/orders
  Authorization: Bearer eyJ...

        |
        v
BearerTokenAuthenticationFilter
        |
        v
JwtDecoder
  - kiểm tra chữ ký bằng khóa phù hợp (JWK)
  - kiểm tra thời hạn và issuer (iss)
  - kiểm tra audience (aud) nếu cấu hình
  - các validator nghiệp vụ bổ sung
        |
        v
JwtAuthenticationConverter
  - đọc scope / scp
  - đọc các claim roles / permissions đã được tin cậy
  - tạo Collection<GrantedAuthority>
        |
        v
JwtAuthenticationToken trong SecurityContext
        |
        v
AuthorizationFilter / method security
  - hasAuthority("SCOPE_orders:read")
  - hasRole("ADMIN") ~ cần ROLE_ADMIN
  - hasAuthority("PERM_orders:approve")
        |
        v
Controller / service (nếu được cho phép)
```

Các bước có trách nhiệm riêng. **`JwtDecoder`/validator xác minh tính hợp lệ và đích của token; converter ánh xạ dữ liệu đã xác minh thành authorities; authorization policy quyết định endpoint nào cần quyền gì.** Thay converter không biến token chưa được ký đúng thành hợp lệ và không tự bổ sung kiểm tra `aud`.

Tùy token format, Resource Server cũng có thể dùng **opaque token introspection** thay vì JWT. Khi đó `JwtAuthenticationConverter` không chạy; phần tùy chỉnh authority phải được áp dụng vào luồng introspection tương ứng (xem mục 12).

## 3. Mặc định: `scope`/`scp` → `SCOPE_...`

Spring Security Resource Server JWT sử dụng `JwtGrantedAuthoritiesConverter` theo mặc định để tìm các claim scope phổ biến (`scope`, `scp`). Nó đọc các giá trị scope rồi tạo các `SimpleGrantedAuthority` có tiền tố **`SCOPE_`**.

Ví dụ JWT payload minh họa (đã giải mã để học; **không phải JWT ký hợp lệ**):

```json
{
  "iss": "https://idp.example.test/realms/learning",
  "sub": "user-42",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "scope": "orders:read orders:write"
}
```

Hai scope cách nhau bằng khoảng trắng cho ra hai authority:

```text
SCOPE_orders:read
SCOPE_orders:write
```

Một nhà cung cấp khác có thể dùng mảng:

```json
{
  "sub": "user-42",
  "scp": ["orders:read", "orders:write"]
}
```

Điểm quan trọng là converter mặc định tìm **một** claim scope phù hợp theo thứ tự nội bộ, không nên giả định nó sẽ tự gộp tất cả `scope` và `scp` nếu cả hai tồn tại. Hãy thống nhất hợp đồng claim với IdP. Nếu token dùng tên claim khác, cấu hình `JwtGrantedAuthoritiesConverter#setAuthoritiesClaimName(...)`.

### 3.1. Dùng đúng `hasAuthority` và `hasRole`

| Authority thực có trong Authentication | Điều kiện đúng | Điều kiện sai hoặc dễ nhầm |
| --- | --- | --- |
| `SCOPE_orders:read` | `hasAuthority("SCOPE_orders:read")` | `hasRole("orders:read")` |
| `SCOPE_orders:write` | `hasAuthority("SCOPE_orders:write")` | `hasAuthority("orders:write")` |
| `ROLE_ADMIN` | `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` | `hasRole("ROLE_ADMIN")` theo cách dùng mặc định |
| `PERM_orders:approve` | `hasAuthority("PERM_orders:approve")` | `hasRole("orders:approve")` |

`hasRole("ADMIN")` trong cách cấu hình thông thường kiểm tra **`ROLE_ADMIN`**; còn `hasAuthority("...")` so **đúng chuỗi authority**. Tiền tố được đặt trong converter và biểu thức phải nhất quán. Tránh tự đổi tiền tố `SCOPE_` sang `ROLE_` nếu scope không thật sự là vai trò.

### 3.2. Khi chỉ cần đổi tên claim hoặc prefix

Nếu API chỉ cần một claim `permissions` có danh sách quyền, một converter scope đơn giản có thể đủ:

```java
JwtGrantedAuthoritiesConverter custom = new JwtGrantedAuthoritiesConverter();
custom.setAuthoritiesClaimName("permissions");
custom.setAuthorityPrefix("PERM_");

JwtAuthenticationConverter authenticationConverter =
    new JwtAuthenticationConverter();
authenticationConverter.setJwtGrantedAuthoritiesConverter(custom);
```

**Lưu ý:** cách thay thế này khiến converter lấy `permissions` thay vì tự động giữ **cả** `scope` mặc định. Nếu cần **gộp scope + role + permission**, dùng converter kết hợp như ở mục 7. Từ Spring Security 6.1 trở lên, `setAuthoritiesClaimDelimiter(...)` còn có thể tùy chỉnh cách tách claim dạng chuỗi; không nên dựa vào API đó khi dùng bản 6.0.

## 4. Claim roles và permissions không có một chuẩn chung cho mọi IdP

Một token minh họa có thể chứa:

```json
{
  "iss": "https://idp.example.test/realms/learning",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders:read orders:write",
  "realm_access": {
    "roles": ["ADMIN", "SUPPORT"]
  },
  "permissions": ["orders:approve", "orders:refund"]
}
```

Trong ví dụ này, ứng dụng muốn ánh xạ thành:

```text
SCOPE_orders:read
SCOPE_orders:write
ROLE_ADMIN
ROLE_SUPPORT
PERM_orders:approve
PERM_orders:refund
```

**Đây là hợp đồng claim do ứng dụng/IdP thỏa thuận, không phải định dạng token bắt buộc của OAuth2.** Một IdP có thể dùng `roles`, `groups`, `realm_access.roles`, `resource_access.<client>.roles`, `permissions` hoặc chỉ phát scope. Không tự áp dụng cấu trúc của IdP A cho IdP B.

Ngoài tên claim, cần làm rõ **phạm vi hiệu lực** của role. `realm_access.roles` có thể là vai trò cấp realm dùng cho nhiều ứng dụng. Nếu chỉ muốn role của API `orders-api`, lựa chọn an toàn hơn có thể là claim riêng cho API hoặc vai trò theo resource/client (`resource_access`) cùng audience check, thay vì trao mọi global role cho mọi API.

### 4.1. Vì sao cần whitelist?

Giả sử IdP bổ sung role `SUPERUSER` trong tương lai. Nếu converter mặc định tạo `ROLE_` cho mọi string xuất hiện, policy mới hoặc policy bị nhập sai có thể vô tình trao quyền quá rộng. Vì vậy converter ví dụ bên dưới chỉ chấp nhận role/permission nằm trong danh sách ứng dụng đã công nhận.

Whitelist giúp kiểm soát **tên quyền** nhưng **không đủ** nếu issuer/audience không được xác minh. Các role/permission còn phải do một IdP có thẩm quyền cho API đó phát hành; nếu có nhiều tenant, ràng buộc role/permission với tenant/tài nguyên tương ứng.

### 4.2. JWT có chữ ký đúng vẫn có thể không dùng được cho API này

Một JWT có thể hợp lệ về chữ ký nhưng:

- `iss` là nhà phát hành khác với nhà phát hành được API tin cậy.
- `aud` không chứa audience của Resource Server.
- `exp` đã quá hạn hoặc `nbf` ở tương lai.
- Là **ID Token** cấp cho OAuth2 Client để đăng nhập, không phải access token cấp cho API.
- Có claim `roles` cấp cho ứng dụng khác, không mang ý nghĩa phân quyền ở API hiện tại.

Do đó phải tách **validity** (chữ ký, thời gian, issuer), **intended recipient** (audience, loại token khi cần) và **authorization** (scope/role/permission). Việc chuyển tên claim thành authorities không được bỏ qua bất kỳ bước nào.

## 5. Thiết kế policy: scope, role hay permission?

Ví dụ API quản lý đơn hàng:

| Hành động | Đề xuất policy | Lý do |
| --- | --- | --- |
| `GET /api/orders` | `SCOPE_orders:read` | Token đã được cấp phạm vi đọc |
| `POST /api/orders/approve` | `PERM_orders:approve` | Quyền duyệt là nghiệp vụ, không chỉ quyền truy cập chung |
| `GET /api/admin/audit` | `ROLE_ADMIN` | Chỉ nhân sự có vai trò quản trị mới truy cập |
| `GET /api/me` | Người gọi được xác thực | Xem thông tin principal đã xác thực, không cần scope nghiệp vụ riêng |

Không bắt buộc mọi hệ thống phải dùng cả ba lớp; nhiều API chỉ dùng scopes đã đủ. Nếu sử dụng cùng lúc, ghi rõ **vai trò nào có quyền nghiệp vụ nào**, ai phát hành token và lúc nào thu hồi. Đừng tự xem `ADMIN` là đương nhiên có mọi scope: nếu policy yêu cầu cả scope lẫn role, dùng biểu thức **AND** hoặc một AuthorizationManager rõ ràng.

**Phân biệt bảo vệ URL và dữ liệu:** Có authority `orders:read` không có nghĩa người dùng được đọc **mọi** đơn hàng. Dữ liệu còn phải được lọc theo tenant, owner, trạng thái hoặc quy tắc row-level/object-level authorization. Một user có `ROLE_SUPPORT` ở tenant A không mặc nhiên được thao tác tenant B.

## 6. Dự án Spring Boot 3.x / Java 17+ minh họa

Ví dụ hoàn chỉnh sau là **JWT Resource Server thuần**, không có login form hoặc cookie session. API đọc Bearer access token, kiểm tra issuer/audience/JWK, tạo scopes + roles + permissions, rồi xét quyền tại endpoint. Nó chạy được khi có **IdP thật phát JWT access token phù hợp**; ví dụ `idp.example.test` là giá trị minh họa, không phải dịch vụ thật.

### 6.1. Phụ thuộc Gradle

Tạo Spring Boot 3.x project Java 17 với các dependency trong `build.gradle` (Groovy DSL). Phần plugin, version và dependency management do Spring Initializr tạo sẵn:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Không thêm OAuth2 Client starter chỉ để API xác minh Bearer token. **OAuth2 Client** là bên lấy/giữ token để gọi API hoặc đăng nhập người dùng; **Resource Server** là bên nhận và kiểm tra access token. Một ứng dụng có thể đảm nhiệm cả hai vai trò, nhưng các filter và trách nhiệm khác nhau.

### 6.2. `application.yml`

Tập tin `src/main/resources/application.yml`:

```yaml
app:
  security:
    jwt:
      issuer: https://idp.example.test/realms/learning
      jwk-set-uri: https://idp.example.test/realms/learning/protocol/openid-connect/certs
      audience: orders-api
```

Phải thay các URL và audience theo IdP thực. Trong ví dụ này, `JwtDecoder` được tạo tường minh ở mục 8 để cùng lúc xác minh issuer và audience. Nếu chỉ cấu hình `spring.security.oauth2.resourceserver.jwt.issuer-uri` mà không có audience validator, đừng mặc định cho rằng mọi token cùng issuer đều được phép dùng tại API.

Trong production, endpoint JWK cần được cung cấp qua HTTPS; kiểm soát network trust, cache/rotation khóa và lỗi không truy cập được IdP. Không tắt xác minh chữ ký để thử converter.

### 6.3. Main class

Tập tin `src/main/java/com/example/orders/OrdersResourceServerApplication.java`:

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersResourceServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersResourceServerApplication.class, args);
    }
}
```

## 7. Converter kết hợp: giữ scope mặc định và thêm claims quyền

Tập tin **`src/main/java/com/example/orders/ApiAuthoritiesConverter.java`**:

```java
package com.example.orders;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public final class ApiAuthoritiesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private static final Set<String> TRUSTED_ROLES =
        Set.of("ADMIN", "SUPPORT");

    private static final Set<String> TRUSTED_PERMISSIONS =
        Set.of("orders:approve", "orders:refund");

    private final JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        Set<GrantedAuthority> result = new LinkedHashSet<>();

        // 1. Giữ hành vi Spring Security mặc định: scope/scp -> SCOPE_...
        Collection<GrantedAuthority> scopeAuthorities = scopes.convert(jwt);
        if (scopeAuthorities != null) {
            result.addAll(scopeAuthorities);
        }

        // 2. Đọc cấu trúc realm_access.roles khi IdP quy định như vậy.
        Object realmAccessClaim = jwt.getClaim("realm_access");
        if (realmAccessClaim instanceof Map<?, ?> realmAccess) {
            Object rolesClaim = realmAccess.get("roles");
            if (rolesClaim instanceof Collection<?> roles) {
                for (Object rawRole : roles) {
                    if (rawRole instanceof String role
                            && TRUSTED_ROLES.contains(role)) {
                        result.add(
                            new SimpleGrantedAuthority("ROLE_" + role));
                    }
                }
            }
        }

        // 3. Quyền nghiệp vụ có prefix riêng, không nhập nhằng với role.
        Object permissionsClaim = jwt.getClaim("permissions");
        if (permissionsClaim instanceof Collection<?> permissions) {
            for (Object rawPermission : permissions) {
                if (rawPermission instanceof String permission
                        && TRUSTED_PERMISSIONS.contains(permission)) {
                    result.add(new SimpleGrantedAuthority(
                        "PERM_" + permission));
                }
            }
        }

        return result;
    }
}
```

### 7.1. Tại sao implementation này có các lựa chọn đó?

- Dùng `JwtGrantedAuthoritiesConverter` thay vì tự viết tách scope, vì converter của Spring đã xử lý claim scope quen thuộc và tiền tố `SCOPE_`.
- Dùng `LinkedHashSet` để loại trùng authority và giữ thứ tự xuất hiện tương đối ổn định; **thứ tự authority không quyết định quyền**.
- Kiểm tra kiểu `Map`, `Collection`, `String` trước khi xử lý claim. Nếu IdP phát claim không đúng hợp đồng, không chuyển object tùy tiện thành tên quyền.
- Chỉ phát `ROLE_ADMIN`, `ROLE_SUPPORT` và hai quyền nghiệp vụ đã đăng ký. Nếu muốn thêm role khác, sửa whitelist **cùng policy và test**.
- Prefix `PERM_` tách quyền nghiệp vụ khỏi scope và vai trò, giúp biểu thức kiểm tra khó bị hiểu nhầm.
- Không thêm quyền từ `sub`, `email`, username, các HTTP header hay tên nhóm tùy ý chưa được phân tích nguồn và phạm vi tin cậy.

**Hợp đồng claim phải rõ ràng.** Nếu IdP phát `roles: ["admin"]` (chữ thường) thay cho `realm_access.roles: ["ADMIN"]`, converter này **không** tự gán `ROLE_ADMIN`. Hãy sửa extractor theo định dạng IdP thực và viết test tương ứng; tránh `toUpperCase()` trên mọi string để “đoán” một vai trò đặc quyền.

### 7.2. Nếu roles nằm trong `resource_access.<client>.roles`

Một số IdP phân biệt realm roles và client/resource roles. Ví dụ:

```json
{
  "resource_access": {
    "orders-api": {
      "roles": ["SUPPORT"]
    },
    "unrelated-client": {
      "roles": ["ADMIN"]
    }
  }
}
```

Nếu policy của Resource Server chỉ dùng role dành cho `orders-api`, phải đọc **nhánh `resource_access.orders-api.roles`**, không quét tất cả nhánh và không lấy `ADMIN` của `unrelated-client`. Chọn **một hợp đồng role**: nếu chuyển sang resource roles, thay phần đọc `realm_access` trong converter bằng truy cập map lồng nhau có kiểm tra kiểu; không cộng cả hai nguồn nếu chưa có lý do phân quyền rõ ràng. Audience check vẫn bắt buộc.

## 8. Bảo vệ endpoint và xác minh JWT

Tập tin **`src/main/java/com/example/orders/SecurityConfig.java`**:

```java
package com.example.orders;

import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimNames;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(
            new ApiAuthoritiesConverter());
        return converter;
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

        OAuth2TokenValidator<Jwt> issuerAndLifetime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> requiredAudience =
            new JwtClaimValidator<List<String>>(
                JwtClaimNames.AUD,
                audiences -> audiences != null
                    && audiences.contains(audience));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            issuerAndLifetime, requiredAudience));

        return decoder;
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtAuthenticationConverter converter) throws Exception {

        http
            // Ví dụ ứng dụng API-only: chỉ Bearer token, không cookie auth.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/api/orders/approve")
                    .hasAuthority("PERM_orders:approve")
                .requestMatchers(HttpMethod.GET, "/api/admin/audit")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
                jwt.jwtAuthenticationConverter(converter)
            ));

        return http.build();
    }
}
```

Các điểm cần đọc kỹ:

1. **`JwtDecoder` không phải authority converter**. Nó xác minh chữ ký với JWKS, thời gian/issuer và **audience `orders-api`** rồi mới cung cấp JWT đã giải mã cho cơ chế authentication.
2. **`JwtAuthenticationConverter`** nhận một `Converter<Jwt, Collection<GrantedAuthority>>`, ở đây là `ApiAuthoritiesConverter`, để gộp ba nhóm authorities.
3. **`hasAuthority("SCOPE_orders:read")`** kiểm tra scope do converter mặc định tạo, còn **`hasRole("ADMIN")`** kiểm tra `ROLE_ADMIN`, và **`hasAuthority("PERM_orders:approve")`** kiểm tra quyền nghiệp vụ.
4. **`anyRequest().denyAll()`** là nguyên tắc mặc định từ chối endpoint chưa được policy khai báo.
5. `.csrf(AbstractHttpConfigurer::disable)` ở ví dụ **chỉ phù hợp với API-only dùng Bearer token trong header và không phụ thuộc cookie tự gửi**. Nếu ứng dụng kết hợp form login/session cookie, không copy việc tắt CSRF toàn ứng dụng; hãy thiết kế riêng SecurityFilterChain cho `/api/**` và giữ CSRF ở khu vực dùng cookie.
6. `SessionCreationPolicy.STATELESS` giúp Resource Server không tạo/dùng session để lưu SecurityContext cho request API; nó **không tự xác minh** token và cũng không thay thế chính sách cookie/CSRF khi tồn tại cơ chế khác.
7. `aud` phải đúng recipient API, không chỉ đúng với OAuth2 client frontend. ID Token có audience là client đăng nhập không trở thành access token hợp lệ của API chỉ vì claim `sub` tồn tại.

**Về `JwtClaimValidator<List<String>>`:** JWT audience theo chuẩn có thể biểu diễn dưới dạng string hoặc array, nhưng JWT decoder của Spring thường chuẩn hóa claim `aud` thành `List<String>`. Nếu sử dụng decoder/custom claim mapping khác, kiểm tra kiểu thực tế và viết test cho `aud` một phần tử và nhiều phần tử; không bỏ validator để tránh lỗi kiểu.

### 8.1. Controller để nhìn thấy quyền đã ánh xạ

Tập tin **`src/main/java/com/example/orders/OrdersController.java`**:

```java
package com.example.orders;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {

    @GetMapping("/api/orders")
    public Map<String, String> orders() {
        return Map.of("result", "orders-visible");
    }

    @PostMapping("/api/orders/approve")
    @PreAuthorize("hasAuthority('PERM_orders:approve')")
    public Map<String, String> approve() {
        return Map.of("result", "approved");
    }

    @GetMapping("/api/admin/audit")
    public Map<String, String> audit() {
        return Map.of("result", "audit-visible");
    }

    @GetMapping("/api/me")
    public Map<String, Object> me(Authentication authentication) {
        return Map.of(
            "subject", authentication.getName(),
            "authorities", authentication.getAuthorities()
                .stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList()
        );
    }
}
```

Vì `@EnableMethodSecurity` được bật, `@PreAuthorize` sẽ bảo vệ method `approve` thêm một lớp. Trong ứng dụng lớn, quy tắc method security nên tập trung ở service nghiệp vụ được gọi từ mọi entrypoint, để hạn chế chuyện một controller khác bỏ qua endpoint policy.

**`/api/me` là endpoint demo chẩn đoán**: nó trả danh sách authorities để bạn thấy mapping đã chạy. Trong production, không nhất thiết công khai toàn bộ quyền nội bộ cho mọi client; trả nội dung này chỉ khi có nhu cầu sản phẩm và kiểm soát thông tin phù hợp.

### 8.2. Chạy project và gọi API

Trong project Gradle có Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell: `.\gradlew.bat bootRun`.

Khi có **JWT access token thật**, đã được IdP ký và có `iss`, `aud=orders-api`, `exp` phù hợp:

```bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/orders
```

`ACCESS_TOKEN` là biến môi trường shell chứa JWT do IdP thử nghiệm cấp. Đây là lệnh minh họa cho Bash; trên PowerShell dùng `$env:ACCESS_TOKEN` với cách ghép chuỗi tương ứng.

**Kết quả kỳ vọng tùy token và cấu hình:**

- Không gửi token / token sai → thường **401 Unauthorized**.
- Token hợp lệ nhưng không có `SCOPE_orders:read` → **403 Forbidden**.
- Token hợp lệ có `orders:read` → **200 OK** với JSON `{"result":"orders-visible"}`.
- Gọi `POST /api/orders/approve` cần `PERM_orders:approve`; chỉ có scope `orders:write` **không tự được duyệt đơn**.
- `/api/admin/audit` cần `ROLE_ADMIN`, có nghĩa token phải chứa role được converter chấp nhận.

HTTP status thực tế còn phụ thuộc exception handling, proxy và security chain; đừng chẩn đoán 403 bằng cách ngừng validate JWT. Với API Bearer-only, **401** thường là thiếu/không xác thực được token; **403** thường là đã xác thực nhưng thiếu authority cần thiết.

## 9. Kiểm thử converter bằng JUnit — không phụ thuộc IdP

Test quan trọng nhất của bài này là kiểm tra **claim cụ thể** tạo ra **đúng tập authorities**, không tự sinh thêm quyền. Test sau sử dụng `Jwt` object giả dựng trong JVM để kiểm tra phép ánh xạ, **không phải JWT có chữ ký hay test của decoder**.

Tập tin **`src/test/java/com/example/orders/ApiAuthoritiesConverterTest.java`**:

```java
package com.example.orders;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ApiAuthoritiesConverterTest {

    private final ApiAuthoritiesConverter converter =
        new ApiAuthoritiesConverter();

    @Test
    void combinesScopesApprovedRolesAndPermissions() {
        Jwt jwt = Jwt.withTokenValue("test-value")
            .header("alg", "RS256")
            .claim("sub", "user-42")
            .claim("scope", "orders:read orders:write")
            .claim("realm_access", Map.of(
                "roles", List.of("ADMIN", "NOT_APPROVED")))
            .claim("permissions", List.of(
                "orders:approve", "unrecognized:permission"))
            .build();

        Set<String> actual = converter.convert(jwt)
            .stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());

        assertEquals(Set.of(
            "SCOPE_orders:read",
            "SCOPE_orders:write",
            "ROLE_ADMIN",
            "PERM_orders:approve"
        ), actual);
    }

    @Test
    void missingCustomClaimsDoNotCreateExtraAuthorities() {
        Jwt jwt = Jwt.withTokenValue("test-value")
            .header("alg", "RS256")
            .claim("sub", "user-99")
            .claim("scp", List.of("orders:read"))
            .build();

        Set<String> actual = converter.convert(jwt)
            .stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());

        assertEquals(Set.of("SCOPE_orders:read"), actual);
    }
}
```

Chạy:

```bash
./gradlew test
```

Với đúng code mẫu và dependency Spring Boot 3, hai test **dự kiến PASS**. Thứ tự trong `Set` không dùng để so sánh, nên test không phụ thuộc thứ tự Spring trả authorities. `Jwt.withTokenValue(...)` xây JWT object để test mapping; nó **không** kiểm tra chữ ký, audience, issuer hay thời hạn.

### 9.1. Test filter chain qua MockMvc với JwtDecoder mock

Để xác minh HTTP endpoint nhận authorities qua **BearerTokenAuthenticationFilter → JwtAuthenticationConverter**, có thể dùng `@SpringBootTest` và `@AutoConfigureMockMvc`, mock JwtDecoder rồi gửi `Authorization: Bearer demo-reader`. Ví dụ phù hợp Spring Boot 3.x, trong đó `@MockBean` vẫn được hỗ trợ (ở các bản mới hơn nó có thể được cảnh báo deprecated):

Tập tin **`src/test/java/com/example/orders/ApiPolicyTest.java`**:

```java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiPolicyTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    JwtDecoder decoder;

    @Test
    void bearerScopesAllowReadButNotApprove() throws Exception {
        Jwt reader = Jwt.withTokenValue("demo-reader")
            .header("alg", "RS256")
            .claim("sub", "user-42")
            .claim("scope", "orders:read")
            .build();

        when(decoder.decode("demo-reader")).thenReturn(reader);

        mvc.perform(get("/api/orders")
                .header("Authorization", "Bearer demo-reader"))
            .andExpect(status().isOk());

        mvc.perform(post("/api/orders/approve")
                .header("Authorization", "Bearer demo-reader"))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin/audit")
                .header("Authorization", "Bearer demo-reader"))
            .andExpect(status().isForbidden());
    }
}
```

Tại test này, **decoder được mock** nên test cho thấy policy/filter converter xử lý authority như mong đợi, chứ không chứng minh signature/issuer/audience validation của NimbusJwtDecoder. Cần test integration riêng với JWT được ký bởi test key/IdP thử nghiệm để kiểm tra `JwtDecoder` từ chối token sai issuer, sai audience, hết hạn hoặc ký sai.

Nếu dùng `SecurityMockMvcRequestPostProcessors.jwt()` trực tiếp, lưu ý helper này thường tạo sẵn `JwtAuthenticationToken` và có thể **bỏ qua custom JwtDecoder/JwtAuthenticationConverter**, nên test đó không đủ chứng minh converter cấu hình thật đã chạy. Dùng converter unit test và HTTP integration test có decoder mock như ở trên để bao phủ hai khâu riêng.

## 10. Method security, biểu thức quyền và quy tắc AND/OR

Với `@EnableMethodSecurity`, method nghiệp vụ có thể khai báo:

```java
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
public OrderDto getOrder(long orderId) {
    // Kiểm tra quyền xem đơn hàng và quyền sở hữu/tenant trong service.
    return loadAuthorizedOrder(orderId);
}
```

Đây là **đoạn minh họa method**, không phải class độc lập có thể biên dịch vì `OrderDto` và `loadAuthorizedOrder` phụ thuộc ứng dụng. Ví dụ full runnable ở mục 8 dùng controller `@PreAuthorize` và không cần các kiểu đó.

Nếu cả scope lẫn role đều bắt buộc:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_orders:write') and hasRole('ADMIN')")
```

Nếu một trong hai loại quyền là đủ (phải có lý do nghiệp vụ cụ thể):

```java
@PreAuthorize(
    "hasAuthority('PERM_orders:approve') or hasRole('ADMIN')")
```

`and` chặt hơn `or`; chọn theo policy, không mặc định admin luôn override mọi scope. **Một bước kiểm tra authority không thay cho kiểm tra chủ thể có quyền với từng object cụ thể.** Ví dụ update order phải đảm bảo `order.tenantId` bằng tenant được phép, chứ không chỉ kiểm tra `SCOPE_orders:write`.

Khi policy trải qua nhiều controller/service, nên lưu các tên authority thành constant hoặc định nghĩa một lớp policy dùng chung để tránh lệch `SCOPE_`, `ROLE_`, `PERM_` giữa nơi map và nơi kiểm tra. Tuy nhiên đừng dùng một constant tên `ADMIN` chung cho tất cả tenant nếu quyền thực tế cần gắn tenant.

## 11. Tùy chỉnh claim ở decoder và việc ánh xạ kiểu dữ liệu

Spring Security có thể chuyển kiểu của một số JWT claims như `exp` (thời gian), `aud` (audience list), trong khi **claim tùy chỉnh** có thể là string, list, map hoặc null tùy nhà cung cấp. Converter cần thận trọng với:

- **Thiếu claim:** không cộng thêm quyền; ghi log an toàn có thể giúp phát hiện token không đúng hợp đồng.
- **Claim sai kiểu:** không ép `"ADMIN,SUPPORT"` thành list trừ khi hợp đồng quy định và parser được test.
- **Role chữ hoa/chữ thường:** giữ hợp đồng cụ thể; tránh tự “nâng cấp” một string bất kỳ thành `ADMIN`.
- **Claim lồng nhau:** kiểm tra kiểu từng map; không dùng cast thẳng có thể ném `ClassCastException`.
- **Nhiều nguồn quyền:** quyết định thứ tự ưu tiên, merge hay chọn một nguồn. Tránh một authority từ realm A vô tình áp cho realm B.
- **Nhiều tenant:** token phải gắn tenant vào claim tin cậy, và policy phải kiểm tra quyền *trong tenant hiện hành*, không chỉ một danh sách roles toàn cục.

Nếu IdP chỉ phát quyền trong `resource_access.orders-api.roles`, sửa converter theo claim đó. Nếu chỉ phát permission từ backend DB, không tin role trong JWT như nguồn sự thật cho permission biến động nhanh: dùng custom `AuthorizationManager` hoặc service kiểm tra quyền, có chiến lược caching/invalidation và audit rõ ràng. Access token là snapshot; thay role ở IdP không tự thu hồi token đã cấp cho đến khi token hết hạn hoặc có cơ chế thu hồi/kiểm tra thích hợp.

### 11.1. Ví dụ cấu hình chỉ một claim khác tên

Trường hợp token dùng `scp` dạng chuỗi hoặc danh sách thông thường, mặc định đã có thể xử lý. Nếu IdP dùng claim `custom_scopes`:

```java
JwtGrantedAuthoritiesConverter scopes =
    new JwtGrantedAuthoritiesConverter();
scopes.setAuthoritiesClaimName("custom_scopes");
scopes.setAuthorityPrefix("SCOPE_");
```

Tuy nhiên, dùng đoạn này **thay** converter scope trong mục 7 nếu hợp đồng đổi, không thêm cả hai cùng đọc các claim không đồng nhất khi chưa định nghĩa merge. Khi claim chứa delimiter đặc biệt thay vì khoảng trắng, hãy cấu hình bằng API tương ứng với phiên bản Spring Security đang sử dụng hoặc chuẩn hóa claim tại IdP.

## 12. Opaque access token: cùng mục tiêu nhưng điểm tùy chỉnh khác

JWT Resource Server kiểm tra chữ ký/token claims bằng `JwtDecoder`, rồi dùng `JwtAuthenticationConverter`. Ngược lại, **opaque access token** không có payload JWT để API tự đọc; Resource Server thường gọi **introspection endpoint** của Authorization Server, nhận `active` và attributes rồi tạo `Authentication`.

Với opaque token:

- Cấu hình `.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(...))` cùng introspector/credentials tin cậy.
- Kiểm tra kết quả introspection `active=true` và các ràng buộc issuer/audience/resource cần thiết theo thiết kế IdP.
- Muốn đổi role/permission thành GrantedAuthority thì tùy biến **introspection principal/authentication converter**, chứ không gắn `JwtAuthenticationConverter` vào token opaque.
- Phân quyền endpoint bằng `hasAuthority(...)` vẫn có thể giữ nguyên nếu cả hai nhánh JWT và opaque cùng chuẩn hóa về tên authority thống nhất.

Không cố tự Base64-decode một opaque token rồi coi nó là JWT. Và cũng không tự gán authority bằng client metadata không được xác thực thay cho introspection result.

## 13. Kiểm tra sự cố khi scope hoặc permission không hoạt động

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Token hợp lệ nhưng `GET /api/orders` 403 | Không có `SCOPE_orders:read` trong Authentication | Xem claim `scope`/`scp`, prefix, audience và policy |
| `hasRole("ADMIN")` luôn 403 | Converter chưa tạo `ROLE_ADMIN`, hoặc claim roles sai đường dẫn/kiểu/case | Kiểm tra contract claim và authorities thật sau converter |
| Token có `roles=["ADMIN"]` nhưng không ra ROLE_ADMIN | Ví dụ converter đọc `realm_access.roles`, không đọc top-level `roles` | Sửa extractor theo IdP và thêm test |
| Token chứa permission nhưng `hasAuthority("orders:approve")` 403 | Converter tạo `PERM_orders:approve` | Dùng đúng prefix hoặc chỉnh chính sách nhất quán |
| Thay `setAuthoritiesClaimName("permissions")` khiến scope mất | Custom converter đã thay thế scope converter | Gộp nhiều nguồn bằng converter kết hợp |
| 401 với JWT tưởng đúng | Sai signature/JWK, `iss`, `aud`, `exp` hoặc token format | Đọc log xác minh token, không nới permission để chữa lỗi 401 |
| Token là ID Token thay vì access token | Client gửi token dành cho đăng nhập, audience/semantics sai | API yêu cầu access token cấp đúng audience, từ chối ID Token |
| Admin của client khác truy cập được | Converter lấy role global/nhiều app mà không giới hạn | Ràng buộc audience và claim role theo API/client |
| Đăng xuất/thu hồi role nhưng token cũ vẫn có quyền | JWT là snapshot và chưa hết hạn | Dùng TTL phù hợp, revocation/introspection hoặc kiểm tra quyền động |
| Token có scope read nhưng sửa được dữ liệu | Policy `anyRequest().authenticated()` quá rộng hoặc sai matcher | Dùng method-specific matchers, deny-by-default, test 403 |
| User có scope nhưng đọc được tenant khác | Chỉ kiểm tra authority mà không kiểm tra resource/tenant | Bổ sung object-level authorization và test cross-tenant |
| `@PreAuthorize` không chạy | Thiếu `@EnableMethodSecurity`, call nội bộ không qua proxy hoặc gọi sai bean | Bật method security và đặt guard ở service được gọi qua Spring proxy |
| Test `.with(jwt())` pass nhưng production 403 | Test cấp authorities trực tiếp, bỏ qua converter thật | Test converter riêng + HTTP qua decoder mock/IdP test |
| Lỗi chỉ ở endpoint POST | Có thể là CSRF hoặc policy method, không nhất thiết scope | Xem cơ chế credential và từng SecurityFilterChain |

### 13.1. Quan sát quyền mà không lộ token

Khi debug, **không in nguyên Bearer token, client secret hoặc claim nhạy cảm vào log**. Nên log ở mức tối thiểu các thông tin không nhạy cảm như request ID, tên endpoint, authentication thành công/thất bại, mã reason đã chuẩn hóa, authority names nếu chính sách nội bộ cho phép và correlation ID, kèm redaction và quyền truy cập log.

Một endpoint demo `/api/me` giúp kiểm tra danh sách authorities sau converter ở môi trường test; không dùng nó thay cho kiểm tra dữ liệu ở service. Để so sánh token, chỉ dùng decoded claims trong môi trường bảo mật phù hợp, tránh dán token thực lên website bên ngoài.

## 14. Checklist nghiệm thu Resource Server

1. **Đúng loại token:** API nhận access token, không nhầm với ID Token hoặc refresh token.
2. **Đúng trust boundary:** signature/algorithm/JWK phù hợp, issuer, thời hạn, audience và các validator token-type/tenant nếu cần.
3. **Đúng ánh xạ mặc định:** `scope` hoặc `scp` chuyển thành `SCOPE_<scope>`, và `hasAuthority` dùng đúng tên đó.
4. **Đúng hợp đồng custom claims:** roles/permissions được IdP cấp cho **API này**, đúng đường dẫn, kiểu dữ liệu và chữ hoa/thường.
5. **Đúng custom converter:** giữ scope khi cần, whitelist roles/permissions, tránh cấp quyền từ string chưa tin cậy hoặc claim sai kiểu.
6. **Đúng authorization policy:** GET read cần `SCOPE_orders:read`; approve cần `PERM_orders:approve`; admin cần `ROLE_ADMIN`; các route chưa khai báo bị từ chối.
7. **Đúng object-level policy:** tenant/owner/resource relationship được kiểm tra ngoài scope hoặc role.
8. **Đúng kiểm thử:** converter unit test, HTTP policy integration test, JWT validation test với key/IdP thử nghiệm; bao phủ 401, 403, 200 và claim không hợp lệ.
9. **Đúng vận hành:** rotation key, token TTL, thu hồi quyền, log redaction và việc tách cookie/CSRF khỏi Bearer-only APIs.

**Tóm lại:** `scope`/`scp` trong JWT hợp lệ được Spring Security chuyển thành `SCOPE_...` theo mặc định. Khi cần thêm role và permission từ custom claims, sử dụng `JwtAuthenticationConverter` với một converter kết hợp, **không đánh mất scope**, thống nhất các prefix `SCOPE_`, `ROLE_`, `PERM_` và bảo vệ API bằng `hasAuthority`/`hasRole` đúng nghĩa. Việc cấp quyền chỉ an toàn nếu token đã được xác minh issuer, audience, chữ ký và thời hạn, và các quyền thực tế còn gắn với tài nguyên/tenant cần bảo vệ.
