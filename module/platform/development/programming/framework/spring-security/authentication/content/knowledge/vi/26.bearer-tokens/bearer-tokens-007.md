# Chuyển claims hoặc scope thành `GrantedAuthority` trong Bearer token

## 1. Mục tiêu bài học

Khi một API Spring Security nhận `Authorization: Bearer <access-token>`, **xác thực token** trả lời câu hỏi “token này có hợp lệ và được phát cho API này không?”, còn **phân quyền** cần biết token hoặc dữ liệu phía server cho phép làm gì. Cầu nối giữa hai bước là tập `GrantedAuthority` trong đối tượng `Authentication`.

Bài này hướng dẫn:

1. Hiểu quan hệ giữa `scope`/`scp`, các custom claims (`roles`, `authorities`, `realm_access`) và `GrantedAuthority`.
2. Dùng `JwtGrantedAuthoritiesConverter`, `JwtAuthenticationConverter` để chuyển claim JWT thành authority.
3. Phân biệt `SCOPE_messages:read`, `ROLE_ADMIN`, `hasAuthority(...)`, `hasRole(...)` và quyền nghiệp vụ.
4. Kết hợp scope với roles có kiểm soát, xử lý claim lồng nhau và dữ liệu sai kiểu, ngăn mở rộng quyền không chủ đích.
5. Tùy biến authority cho opaque token qua `OpaqueTokenIntrospector`; nhận biết khác biệt trong WebFlux.
6. Tạo cấu hình Spring Boot 3.x / Spring Security 6.x và unit test Java 17+, phân biệt test converter với test xác minh token thật.

**Bối cảnh:** OAuth 2.0 Resource Server trong Spring Security Servlet; phần WebFlux và thay đổi phiên bản ở cuối bài. JWT và opaque token cùng có thể dùng `Bearer`, nhưng **đường đọc thông tin và cơ chế tùy biến không giống nhau**.

## 2. Từ access token đến `Authentication`

`GrantedAuthority` là hợp đồng Java nhỏ của Spring Security:

```java
package org.springframework.security.core;

public interface GrantedAuthority extends java.io.Serializable {
    String getAuthority();
}
```

Implementation phổ biến là `SimpleGrantedAuthority`, nhận một chuỗi như `SCOPE_orders:read` hoặc `ROLE_OPERATOR`.

Ví dụ payload **minh họa** của một access token JWT (đã bỏ chữ ký và các trường thời gian để dễ đọc):

```json
{
  "iss": "https://idp.example.org/realms/training",
  "sub": "user-7392",
  "aud": ["api://training"],
  "scope": "messages:read messages:write",
  "roles": ["OPERATOR"]
}
```

Sau **khi JWT đã được `JwtDecoder` xác minh và kiểm tra điều kiện**, một converter có thể tạo:

```text
Authentication type: JwtAuthenticationToken
Authentication name: user-7392
Granted authorities:
  SCOPE_messages:read
  SCOPE_messages:write
  ROLE_OPERATOR
```

Chuỗi `SCOPE_` và `ROLE_` là quy ước của **Spring Security**, không phải trường bắt buộc trong JWT hay một câu lệnh quyền từ OAuth 2.0. Converter có thể đổi prefix, nhưng các rule authorization phải dùng đúng giá trị sau chuyển đổi.

Luồng Servlet thường gặp:

```text
HTTP Authorization: Bearer eyJ...
             |
             v
BearerTokenAuthenticationFilter
             |
             v
AuthenticationManager / JwtAuthenticationProvider
             |
             +--> JwtDecoder:
             |    xác minh signature, issuer, lifetime, audience theo cấu hình
             |
             +--> JwtAuthenticationConverter:
                  JwtGrantedAuthoritiesConverter và mapping tùy chỉnh
             |
             v
JwtAuthenticationToken đã xác thực
  principal = Jwt
  authorities = [...]
             |
             v
SecurityContextHolder -> AuthorizationFilter / @PreAuthorize
```

**Nguyên tắc:** converter không phải lớp kiểm tra mật mã. Một JSON payload tự decode hoặc `Jwt` tự dựng từ text **chưa** là bằng chứng được cấp quyền; kiểm tra chữ ký/thuật toán/issuer/audience/time/tenant phải xảy ra trước khi tin claims.

## 3. Mặc định của Spring Security: `scope` và `scp`

`JwtGrantedAuthoritiesConverter` (package `org.springframework.security.oauth2.server.resource.authentication`) đọc một trong các well-known authority claims, điển hình là:

- `scope`: thường là chuỗi **các scope cách nhau bởi khoảng trắng**, ví dụ `"messages:read messages:write"`.
- `scp`: có thể là collection chuỗi, ví dụ `["messages:read", "messages:write"]` tùy authorization server.

Mỗi scope được chuyển thành một `SimpleGrantedAuthority` với prefix **`SCOPE_`**.

| Claim nhận được | Mapping mặc định | Ghi chú |
| --- | --- | --- |
| `"scope": "profile email"` | `SCOPE_profile`, `SCOPE_email` | Hai scope độc lập |
| `"scp": ["orders:read", "orders:write"]` | `SCOPE_orders:read`, `SCOPE_orders:write` | Collection |
| `"scope": "orders:read"` | `SCOPE_orders:read` | Không tạo `ROLE_...` |
| `"roles": ["ADMIN"]` | Không tự tạo `ROLE_ADMIN` | Custom claim cần converter riêng |
| Không có `scope`/`scp` | Không có scope-derived authorities | Token có thể hợp lệ nhưng thiếu quyền |
| Có đồng thời `scope` và `scp` | Default converter chọn claim theo logic well-known | **Không** tự hợp nhất cả hai trường |

Tên scope và authority **phân biệt hoa/thường**: `SCOPE_Orders:Read` và `SCOPE_orders:read` khác nhau. Không nên tự `toUpperCase()` hay `toLowerCase()` một cách tùy tiện khi chưa có contract của issuer.

Trong ứng dụng:

```java
.requestMatchers("/api/messages/**")
.hasAuthority("SCOPE_messages:read")
```

hoặc trong method security:

```java
@PreAuthorize("hasAuthority('SCOPE_messages:read')")
```

đều kiểm tra **chuỗi authority đã mapping**, không nhìn trực tiếp vào `scope` JSON. Một endpoint cần write phải kiểm tra `SCOPE_messages:write` chứ không suy từ `messages:read`.

### `hasAuthority` và `hasRole`

| API | Kiểm tra thực tế | Dùng với |
| --- | --- | --- |
| `hasAuthority("SCOPE_messages:read")` | Có authority đúng chuỗi `SCOPE_messages:read` | OAuth2 scope |
| `hasAuthority("ROLE_OPERATOR")` | Có authority đúng chuỗi `ROLE_OPERATOR` | Role được ánh xạ |
| `hasRole("OPERATOR")` | Theo role prefix mặc định, yêu cầu `ROLE_OPERATOR` | Role kiểu Spring |
| `hasRole("SCOPE_messages:read")` | Theo prefix mặc định, kiểm tra `ROLE_SCOPE_messages:read` | Không phù hợp cho scope |
| `authenticated()` | Authentication đã xác thực | Không đòi hỏi scope/role cụ thể |

Vì thế, **JWT được xác thực thành công không đồng nghĩa có quyền truy cập endpoint**. Một resource server có thể trả **401** khi token thiếu/sai/hết hạn và **403** khi token hợp lệ nhưng thiếu authority; kết quả cụ thể còn tùy entry point và cấu hình filter chain.

## 4. Cấu hình Spring Boot 3.x để nhận và kiểm tra JWT

Với project Gradle Spring Boot 3.x có Java 17+, dependency tối thiểu cho Servlet API resource server:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Starter resource server đưa vào phần xử lý bearer token và thư viện xác minh JWT (`spring-security-oauth2-jose`) tương thích. Không cần thêm `spring-boot-starter-oauth2-client` chỉ vì API nhận Bearer token.

`src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/training
          audiences: api://training
```

- `issuer-uri` giúp cấu hình `JwtDecoder` tìm metadata/JWKs của issuer được tin cậy và kiểm tra `iss`.
- `audiences` (được Spring Boot 3.x hỗ trợ theo bản tương ứng) giúp kiểm tra `aud` có chứa resource server này. Không chấp nhận một access token được phát cho API khác.
- Resource server còn kiểm tra chữ ký, thời gian `exp`/`nbf` và các điều kiện theo validator thực tế. Khi có nhiều issuer/tenant hoặc JWK URL tùy chỉnh, phải xác định rõ `JwtDecoder` và validation tương ứng.
- URL `idp.example.org` là **minh họa**. Cần issuer thật và token hợp lệ được phát cho audience `api://training` trước khi request chạy thành công.

Không đưa token, private key hoặc thông tin đăng nhập vào Git. Một token giả trong các unit test dưới đây chỉ dùng để test converter; không đi qua `JwtDecoder`.

## 5. Dùng default mapping trong `SecurityFilterChain`

Với JWT chứa `scope=messages:read`, cấu hình đơn giản:

```java
package example.authority;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class DefaultJwtSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/messages/**")
                    .hasAuthority("SCOPE_messages:read")
                .requestMatchers(HttpMethod.POST, "/api/messages/**")
                    .hasAuthority("SCOPE_messages:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()));
        return http.build();
    }
}
```

Đây là một **cấu hình Spring Security Servlet độc lập** khi đặt vào project Spring Boot có controller, dependencies và decoder properties nêu trên. Không đăng ký đồng thời bean `SecurityFilterChain` ở mục này và ở mục 7 nếu hai bean đó không có `securityMatcher`/`@Order` để định tuyến rõ ràng: hãy **chọn một biến thể** cho ứng dụng.

Ví dụ giả định app có các endpoint tương ứng. Nếu cần public health check, phải khai báo matcher được phép trước `anyRequest().denyAll()`.

Với API chỉ dùng Bearer token từ header, có thể cân nhắc session policy `STATELESS` và CSRF theo mô hình thực tế. Không tắt CSRF toàn ứng dụng nếu vẫn có login bằng cookie/session; CSRF và token validation là hai khía cạnh khác nhau.

## 6. Tùy chỉnh claim, prefix và dấu tách

`JwtGrantedAuthoritiesConverter` có các cấu hình chủ chốt:

| API | Công dụng | Phạm vi |
| --- | --- | --- |
| `setAuthoritiesClaimName("permissions")` | Chuyển claim `permissions` thay cho well-known `scope`/`scp` | Một claim được chọn |
| `setAuthorityPrefix("ROLE_")` | Đổi prefix authorities sinh ra | Phải đồng bộ với authorization rule |
| `setAuthorityPrefix("")` | Không thêm prefix | Chỉ dùng khi rule đã được thiết kế chính xác |
| `setAuthoritiesClaimDelimiter(",")` | Regex tách chuỗi claim, ví dụ `read,write` | Có từ Spring Security **6.1** |
| `JwtAuthenticationConverter#setJwtGrantedAuthoritiesConverter(...)` | Cắm converter vào JWT authentication | Servlet resource server |
| `JwtAuthenticationConverter#setPrincipalClaimName("preferred_username")` | Đổi claim làm tên hiển thị của Authentication | **Không** tự thay đổi quyền |

Ví dụ muốn claim `permissions` là chuỗi phân tách bằng dấu phẩy:

```json
{
  "permissions": "orders:read,orders:write"
}
```

Cấu hình **Spring Security 6.1+**:

```java
JwtGrantedAuthoritiesConverter permissions = new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERMISSION_");
permissions.setAuthoritiesClaimDelimiter(",");

JwtAuthenticationConverter authentication = new JwtAuthenticationConverter();
authentication.setJwtGrantedAuthoritiesConverter(permissions);
```

Kết quả:

```text
PERMISSION_orders:read
PERMISSION_orders:write
```

Đây là **snippet nằm trong một method Java** có các import:

```java
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
```

`setAuthoritiesClaimName` **thay** claim mặc định; nếu cần lấy `scope` **và** `roles`, hãy kết hợp converter tường minh như mục 7. Tránh việc đổi toàn bộ scope thành `ROLE_`: `SCOPE_` biểu diễn quyền ủy quyền OAuth2, còn role thường là quyền nghiệp vụ do ứng dụng quản lý.

## 7. Ví dụ đầy đủ: hợp nhất scope và claim `roles`

Một IdP có thể cấp:

```json
{
  "scope": "messages:read messages:write",
  "roles": ["OPERATOR"]
}
```

Yêu cầu nghiệp vụ:
- `scope` thành `SCOPE_messages:read` / `SCOPE_messages:write`.
- `roles` thành `ROLE_OPERATOR`.
- Không cấp role nếu token không có trường `roles`, cũng không nâng `SCOPE_...` lên role.
- Không trùng authority khi một token chứa các giá trị lặp.

### 7.1. Security config Java 17+ có thể biên dịch

`src/main/java/example/authority/MappedJwtSecurityConfig.java`:

```java
package example.authority;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MappedJwtSecurityConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        // Giữ ánh xạ mặc định scope/scp -> SCOPE_...
        JwtGrantedAuthoritiesConverter scopes = new JwtGrantedAuthoritiesConverter();

        // Claim roles do issuer có quyền phát hành đã quy định.
        JwtGrantedAuthoritiesConverter roles = new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");

        Converter<Jwt, Collection<GrantedAuthority>> merged = jwt -> {
            Set<GrantedAuthority> authorities = new LinkedHashSet<>();
            authorities.addAll(scopes.convert(jwt));
            authorities.addAll(roles.convert(jwt));
            return authorities;
        };

        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(merged);
        return converter;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JwtAuthenticationConverter jwtConverter) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/messages/**")
                    .hasAuthority("SCOPE_messages:read")
                .requestMatchers(HttpMethod.POST, "/api/messages/**")
                    .hasAuthority("SCOPE_messages:write")
                .requestMatchers("/api/operations/**")
                    .hasRole("OPERATOR")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtConverter)));
        return http.build();
    }
}
```

`LinkedHashSet` loại bỏ các `GrantedAuthority` trùng chuỗi đồng thời giữ thứ tự ổn định. Tập authority sau merge là kết quả cho một lần xử lý JWT; code **không** sửa payload JWT và không cấp lại access token.

**Lưu ý về niềm tin:** ví dụ cho phép `roles` ảnh hưởng đến quyền vì **giả định IdP được tin cậy phát hành claim này cho audience API**. Nếu issuer không cam kết ý nghĩa/nguồn dữ liệu của `roles`, hoặc token chứa roles dành cho ứng dụng khác, không nên map thẳng. Áp dụng allowlist, kiểm tra client/tenant/audience, hoặc tra quyền tại ứng dụng. Một access token từ đối tác khác không thể tự trở thành quản trị viên chỉ nhờ chứa `"roles":["OPERATOR"]`.

### 7.2. Controller để quan sát authorization

File `src/main/java/example/authority/MessagesController.java`:

```java
package example.authority;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/messages")
public class MessagesController {

    @GetMapping
    public String list() {
        return "messages:read accepted";
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public String create() {
        return "messages:write accepted";
    }
}
```

File `src/main/java/example/authority/OperationsController.java`:

```java
package example.authority;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/operations")
public class OperationsController {

    @GetMapping
    public String status() {
        return "operator accepted";
    }
}
```

File `src/main/java/example/authority/AuthorityDemoApplication.java`:

```java
package example.authority;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorityDemoApplication.class, args);
    }
}
```

Đặt **duy nhất** cấu hình `MappedJwtSecurityConfig` hoặc cấu hình đơn giản ở mục 5 trong cùng demo để tránh bean filter chain bị trùng.

Chạy trong project Spring Boot đã kết nối IdP thật:

```bash
./gradlew bootRun
```

Trên PowerShell Windows dùng `.\gradlew.bat bootRun`. Các request chỉ thành công khi người dùng có access token được **issuer thật** ký, hợp lệ với audience của API và có scope/role tương ứng.

Ví dụ gọi API trong môi trường thử nghiệm đã có token hợp lệ được lưu vào biến môi trường `ACCESS_TOKEN`:

```bash
curl -i -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  https://api.example.org/api/messages
```

Không dùng token giả trong phần JSON phía trên để gọi API thật. Nếu API không chạy sau HTTPS hoặc không có token thực, không thể đưa ra stdout/HTTP response thực tế có tính xác định.

## 8. Mapping claim lồng nhau, ví dụ `realm_access.roles`

Một số authorization server đặt role trong object lồng nhau:

```json
{
  "realm_access": {
    "roles": ["REPORT_VIEWER", "OPERATOR"]
  }
}
```

`setAuthoritiesClaimName("realm_access.roles")` **không phải trình duyệt JSON path**: converter mặc định tìm một claim **cấp cao nhất** tên literal `realm_access.roles`, nên thường không thấy dữ liệu.

Muốn trích claim lồng nhau, viết converter tự xử lý kiểu. Ví dụ bên trong một utility class, code Java 17 sau nhận `Jwt` đã xác minh:

```java
package example.authority;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

public final class RealmRoleMapper {
    private static final Set<String> ALLOWED =
        Set.of("REPORT_VIEWER", "OPERATOR");

    private RealmRoleMapper() {}

    public static Collection<GrantedAuthority> convert(Jwt jwt) {
        Set<GrantedAuthority> result = new LinkedHashSet<>();
        Object rawRealm = jwt.getClaim("realm_access");

        if (!(rawRealm instanceof Map<?, ?> realm)) {
            return result;
        }

        Object rawRoles = realm.get("roles");
        if (!(rawRoles instanceof Collection<?> roles)) {
            return result;
        }

        for (Object value : roles) {
            if (value instanceof String role && ALLOWED.contains(role)) {
                result.add(new SimpleGrantedAuthority("ROLE_" + role));
            }
        }
        return result;
    }
}
```

Tích hợp với scope converter trong method `jwtAuthenticationConverter()`:

```java
JwtGrantedAuthoritiesConverter scopes = new JwtGrantedAuthoritiesConverter();
Converter<Jwt, Collection<GrantedAuthority>> merged = jwt -> {
    Set<GrantedAuthority> result = new LinkedHashSet<>(scopes.convert(jwt));
    result.addAll(RealmRoleMapper.convert(jwt));
    return result;
};
JwtAuthenticationConverter authentication = new JwtAuthenticationConverter();
authentication.setJwtGrantedAuthoritiesConverter(merged);
```

Các import `Jwt`, `GrantedAuthority`, `LinkedHashSet`, `Set`, `Collection`, `Converter`, `JwtAuthenticationConverter`, `JwtGrantedAuthoritiesConverter` tương tự ở mục 7. Đây là **đoạn ghép trong class cấu hình**, không phải một chương trình độc lập.

Ở ví dụ, chỉ hai role trong `ALLOWED` mới được nhập. Role khác bị bỏ qua (fail closed cho role không được biết). Cần kiểm tra **issuer/tenant/audience/ứng dụng đích** trước khi tin `realm_access`; với nhiều IdP, cùng chuỗi `OPERATOR` có thể mang ý nghĩa khác nhau. Nếu một role không hợp lệ là lỗi giao thức cần từ chối token thay vì bỏ qua, hãy đưa chính sách đó vào validation và test.

## 9. Principal name khác authority

Trong JWT, `sub` thường làm tên mặc định cho `Authentication#getName()`; danh tính hiển thị có thể đến từ `preferred_username`, `email` hoặc trường khác. `JwtAuthenticationConverter` cho phép:

```java
JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
converter.setPrincipalClaimName("preferred_username");
```

Dòng trên chỉ chọn **tên principal**, không cấp `ROLE_...`, không thay đổi scope và không đổi cách `JwtDecoder` xác minh token. Nếu muốn giữ merged converter, phải cấu hình cả hai thuộc tính trên **cùng** bean `JwtAuthenticationConverter`, không tạo hai bean riêng rồi mong Spring tự ghép.

Trong hệ thống đa tenant, nên dùng khóa danh tính ổn định như `(issuer, sub)` để liên kết account. Email/username có thể đổi hoặc trùng giữa issuers; không dùng tên hiển thị làm khóa duy nhất cho phân quyền có rủi ro cao.

## 10. Opaque Bearer token: quyền đến từ introspection

Với **opaque token**, API không tự đọc JWT payload. Thay vào đó nó gọi authorization server qua endpoint introspection, xác minh trạng thái token (`active`) rồi dùng attributes được server tin cậy trả về.

```text
Authorization: Bearer <opaque-token>
             |
             v
BearerTokenAuthenticationFilter
             |
             v
OpaqueTokenAuthenticationProvider
             |
             v
OpaqueTokenIntrospector.introspect(token)
   -> xác thực active và trả OAuth2AuthenticatedPrincipal
   -> attributes + authorities (thường scope -> SCOPE_...)
             |
             v
BearerTokenAuthentication -> SecurityContext
```

Mặc định Spring Security ánh xạ scope trong introspection response sang `SCOPE_...`. Đây là đường xử lý **khác** với `JwtGrantedAuthoritiesConverter`; nếu API đang cấu hình `.opaqueToken(...)`, việc chỉ đăng ký một `JwtAuthenticationConverter` **không làm đổi** authorities của opaque token.

Cấu hình Spring Boot 3.x:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.org/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Trong application Servlet dùng opaque token, chọn:

```java
http.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(withDefaults()));
```

`withDefaults()` import từ `org.springframework.security.config.Customizer`. Đây là **thay thế** cho `.jwt(...)` ở trường hợp token được xác minh qua introspection. Một JWT cũng có thể được xử lý bằng introspection thay vì JWK signature nếu đó là policy của Resource Server, nhưng phải hiểu kết quả authentication theo **opaque path**.

### 10.1. Tùy chỉnh opaque authorities bằng một introspector wrapper

Ví dụ chỉ thêm role `OPERATOR` nếu introspection response của issuer tin cậy có claim `roles` chứa role đó; vẫn giữ tất cả scope authorities đã được Spring Security nạp. File `src/main/java/example/authority/OpaqueAuthorityConfig.java`:

```java
package example.authority;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringOpaqueTokenIntrospector;

@Configuration
public class OpaqueAuthorityConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}") String uri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}") String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}") String secret) {

        OpaqueTokenIntrospector delegate = SpringOpaqueTokenIntrospector
            .withIntrospectionUri(uri)
            .clientId(clientId)
            .clientSecret(secret)
            .build();

        return token -> {
            OAuth2AuthenticatedPrincipal principal = delegate.introspect(token);
            Set<GrantedAuthority> authorities =
                new LinkedHashSet<>(principal.getAuthorities());

            Object rawRoles = principal.getAttribute("roles");
            if (rawRoles instanceof Collection<?> roles) {
                for (Object value : roles) {
                    if ("OPERATOR".equals(value)) {
                        authorities.add(new SimpleGrantedAuthority("ROLE_OPERATOR"));
                    }
                }
            }

            return new DefaultOAuth2AuthenticatedPrincipal(
                principal.getName(), principal.getAttributes(), authorities);
        };
    }
}
```

Các lưu ý:

- Ví dụ dựa trên kiểu response `roles` là collection; mỗi IdP có thể trả kiểu khác. Không cast mù hoặc coi một chuỗi bất kỳ là nhóm quyền.
- `delegate.introspect(token)` phải xảy ra **trước** khi gán authority; nếu token inactive/sai credential, introspection ném lỗi và không có principal đáng tin.
- Mã giữ scope authorities từ `principal.getAuthorities()` và thêm duy nhất role được allowlist. Nếu authorization server trả claims không đại diện role ứng dụng, hãy tra cứu quyền từ policy store phía API.
- Giá trị `client-secret` là secret máy chủ dùng cho introspection; phải lấy từ secret manager/môi trường, không commit.
- Chỉ bật `OpaqueAuthorityConfig` trong profile dùng **opaque token**; với JWT profile và nhiều `SecurityFilterChain`, bố trí các bean/matcher tường minh. Code này không phải custom JWT converter.

## 11. Kiểm thử converter bằng JUnit 5 (không cần access token thật)

File `src/test/java/example/authority/JwtAuthorityMappingTest.java`. Đây là **unit test chuyển dữ liệu claims**; `Jwt.withTokenValue(...)` xây fixture trong bộ nhớ, không xác minh chữ ký:

```java
package example.authority;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class JwtAuthorityMappingTest {

    private static Jwt fixture() {
        return Jwt.withTokenValue("fixture-only")
            .header("alg", "RS256")
            .claim("sub", "user-7392")
            .claim("scope", "messages:read messages:write")
            .claim("roles", List.of("OPERATOR"))
            .build();
    }

    private static Set<String> names(
            java.util.Collection<? extends GrantedAuthority> authorities) {
        return authorities.stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());
    }

    @Test
    void defaultConverterAddsScopePrefixOnly() {
        JwtGrantedAuthoritiesConverter converter =
            new JwtGrantedAuthoritiesConverter();

        assertEquals(
            Set.of("SCOPE_messages:read", "SCOPE_messages:write"),
            names(converter.convert(fixture()))
        );
    }

    @Test
    void customConverterCombinesScopeAndRoles() {
        JwtAuthenticationConverter converter =
            new MappedJwtSecurityConfig().jwtAuthenticationConverter();

        var auth = converter.convert(fixture());
        assertNotNull(auth);
        assertEquals("user-7392", auth.getName());
        assertEquals(
            Set.of(
                "SCOPE_messages:read",
                "SCOPE_messages:write",
                "ROLE_OPERATOR"
            ),
            names(auth.getAuthorities())
        );
    }

    @Test
    void absentScopeMeansNoDefaultScopeAuthority() {
        Jwt withoutScope = Jwt.withTokenValue("fixture-without-scope")
            .header("alg", "RS256")
            .claim("sub", "user-2")
            .claim("roles", List.of("OPERATOR"))
            .build();

        JwtGrantedAuthoritiesConverter converter =
            new JwtGrantedAuthoritiesConverter();
        assertEquals(Set.of(), names(converter.convert(withoutScope)));
    }
}
```

Chạy:

```bash
./gradlew test --tests example.authority.JwtAuthorityMappingTest
```

Khi các dependencies tương thích và project Gradle được cấu hình đúng, cả **3 test** phải pass. Không có stdout ứng dụng cố định: output Gradle phụ thuộc project và phiên bản. Test thứ hai kiểm tra mapping `ROLE_OPERATOR` của class config trong mục 7, không cần mạng hoặc access token thật.

### 11.1. Phân biệt converter test và security integration test

`spring-security-test` cung cấp `jwt()` request post processor cho MockMvc. Ví dụ:

```java
mvc.perform(get("/api/messages")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_messages:read")
        )))
   .andExpect(status().isOk());
```

Đoạn trên thuộc một `@Test` có `MockMvc mvc`, static import `SecurityMockMvcRequestPostProcessors.jwt`, `MockMvcRequestBuilders.get`, `MockMvcResultMatchers.status` và import `SimpleGrantedAuthority`. `jwt()` tạo Authentication **giả lập đã xác thực** cho test authorization; nó **không** thử chữ ký JWT hay chạy converter thật nếu bạn tự chỉ định authorities.

Nếu cần kiểm thử đường `JwtDecoder → JwtAuthenticationConverter`, dùng `@MockBean`/test bean decoder trong Spring Boot phiên bản tương thích hoặc một IdP/JWKs test server phù hợp và gửi Bearer token qua HTTP. Tách các test sau:

| Bài test | Xác minh điều gì? |
| --- | --- |
| Unit `JwtGrantedAuthoritiesConverter` | Cách chuyển `scope`, `scp`, `roles`, claim vắng/sai kiểu |
| Unit custom mapping | Allowlist, prefix, kết hợp và không trùng |
| MockMvc với `jwt()` | Authorization rule yêu cầu authority cụ thể |
| Integration với JWT thật | Signature/JWK, issuer, audience, expiration, decoder và mapping |
| Integration với opaque introspection | `active`, scope, timeout, introspector, mapping và quyền |

Không tin `jwt()` trong MockMvc là bằng chứng cấu hình xác minh chữ ký của production đúng.

## 12. Các lỗi hay gặp

| Dấu hiệu | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Token hợp lệ nhưng HTTP 403 | Endpoint đòi `ROLE_ADMIN`, token chỉ tạo `SCOPE_...` | Kiểm tra `Authentication.getAuthorities()` và matcher; chọn policy đúng |
| `hasRole("messages:read")` không thành công | `hasRole` thêm `ROLE_`, trong khi scope dùng `SCOPE_` | Dùng `hasAuthority("SCOPE_messages:read")` |
| JWT có `"roles"` nhưng ứng dụng không nhận role | Default converter chỉ đọc well-known scope claims | Cấu hình custom claim converter/merge |
| Mất scope khi đổi sang claim `roles` | `setAuthoritiesClaimName("roles")` **thay** nguồn claim cũ | Tạo converter cho scope và roles rồi hợp nhất |
| `scope` và `scp` tồn tại mà chỉ thấy một bộ authority | Default converter không merge hai claim cùng lúc | Định nghĩa contract claim với issuer, mapping explicit nếu cần |
| `realm_access.roles` luôn rỗng | Truyền tên claim lồng nhau như một tên flat | Đọc `Map<?, ?>` và validate collection bên trong |
| Roles thay đổi nhưng JWT cũ vẫn giữ quyền | JWT self-contained còn hạn; không tự nhận thay đổi account tức thì | Token TTL hợp lý, revocation/introspection hoặc tra quyền server |
| ID token đăng nhập vào API vẫn được chấp nhận | API thiếu audience/token-type validation | Resource server chỉ tin **access token** dành cho API, kiểm tra aud/iss |
| `401 invalid_token` | JWT sai chữ ký/issuer/audience/hết hạn hoặc token sai | Kiểm tra decoder, JWKS/clock; không sửa converter để vượt qua validation |
| Claim `roles` sai kiểu gây `ClassCastException` | Ép kiểu `List<String>` không kiểm tra | Xử lý `instanceof`, reject hoặc bỏ quyền theo policy |
| Case khác nhau (`read`/`READ`) gây 403 | Authority string so khớp chính xác | Chuẩn hóa contract tại IdP và kiểm tra rule |
| Opaque token không áp dụng JwtGrantedAuthoritiesConverter | Đi qua introspection, không qua JwtAuthenticationConverter | Tùy biến `OpaqueTokenIntrospector` hoặc opaque authentication converter theo version |
| `@PreAuthorize` không có hiệu lực | Chưa bật method security hoặc lời gọi nội bộ bỏ qua proxy | Bật `@EnableMethodSecurity`, gọi qua managed bean |
| Một test `jwt()` pass nhưng token thật fail | Test mock bỏ qua decoder/converter | Thêm integration test với token thật và IdP test |

Báo lỗi an toàn: cung cấp phản hồi 401/403 phù hợp, log nội bộ chỉ ghi request correlation ID, loại lỗi và authority cần thiết. Tránh log nguyên Bearer token hoặc toàn bộ claims có dữ liệu cá nhân.

## 13. Quyền và claim không thay thế security policy

Một hệ thống production cần thống nhất **ai phát hành** token, **token dành cho ai** và **nguồn authority nào được tin**:

1. **Issuer:** giới hạn `iss` và tập JWKs tin cậy. Tránh decoder chấp nhận `alg=none`, key do token tự cung cấp, hoặc issuer tùy ý.
2. **Audience:** kiểm tra `aud` chứa API này; một token từ cùng issuer nhưng cấp cho frontend/API khác chưa được dùng.
3. **Token type:** phân biệt access token với ID token; OAuth 2.0 Bearer Resource Server dùng access token.
4. **Tenant/client boundary:** role `ADMIN` của tenant A hoặc client X không mặc nhiên có hiệu lực tại tenant B/API Y.
5. **Source of authority:** scopes do authorization server cấp theo consent/client policy; role nghiệp vụ có thể cần allowlist, principal lookup hoặc server-side entitlement store.
6. **Giới hạn thời gian:** kiểm tra `exp`, `nbf`, clock skew, key rotation; nếu cần thu hồi nhanh, cân nhắc token TTL ngắn hoặc introspection.
7. **Không tự cấp quyền từ input request:** client không được chọn `roles` bằng query param, HTTP header hay JWT chưa được xác thực.
8. **Tránh lẫn danh tính và quyền:** `preferred_username`, `email`, `sub` là identity claims; không tự tạo `ROLE_...` chỉ vì chuỗi trùng từ khóa.
9. **Kiểm thử negative cases:** token không scope, scope dư nhưng thiếu role, role sai kiểu, issuer khác, audience sai, tenant khác, revoked/expired token.

Chuyển claim thành authority là **một chính sách có chủ đích**, được thực hiện sau khi dữ liệu đã được xác thực và trước authorization. Cùng một claim `roles` trong hai hệ thống phát token có thể mang ý nghĩa khác nhau; vì vậy mapping nên đặt ở biên resource server và có test bảo đảm không nâng quyền.

## 14. Servlet, WebFlux và khác biệt phiên bản

### Servlet

Trong Spring MVC/Servlet, `JwtAuthenticationConverter` triển khai `Converter<Jwt, AbstractAuthenticationToken>` và được gắn qua:

```java
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtConverter)));
```

`SecurityContextHolder` quản lý Authentication theo ngữ cảnh request Servlet; application rule được đánh giá trên `Authentication.getAuthorities()`.

### WebFlux

WebFlux không dùng `HttpSecurity` hay `SecurityFilterChain` Servlet. Nó dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và reactive authentication. Nếu đã có converter đồng bộ để ánh xạ claim:

```java
package example.authority;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveAuthoritySecurityConfig {

    @Bean
    SecurityWebFilterChain webFluxChain(
            ServerHttpSecurity http,
            JwtAuthenticationConverter converter) {
        return http
            .authorizeExchange(authorize -> authorize
                .pathMatchers("/api/messages/**")
                    .hasAuthority("SCOPE_messages:read")
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt -> jwt
                .jwtAuthenticationConverter(
                    new ReactiveJwtAuthenticationConverterAdapter(converter)
                )))
            .build();
    }
}
```

Đây là **một biến thể dành riêng cho ứng dụng Spring WebFlux** có bean converter như mục 7. `ReactiveJwtAuthenticationConverterAdapter` chuyển converter đồng bộ thành giao diện reactive, không có nghĩa có thể dùng `HttpSecurity` trong WebFlux. Nếu mapping cần gọi DB/network bất đồng bộ, triển khai converter reactive không chặn event loop; không gọi `.block()` trong chuỗi reactive.

### Phiên bản

| Dòng Spring Security | Điểm cần nhớ |
| --- | --- |
| **5.2+** | `JwtGrantedAuthoritiesConverter` có trong Resource Server JWT; mặc định scope → `SCOPE_...` |
| **5.7–5.8** | `WebSecurityConfigurerAdapter` deprecated; nên chuyển cấu hình sang bean `SecurityFilterChain` |
| **6.0+** | Yêu cầu Java 17, Jakarta API cho Servlet; dùng DSL lambda và bean |
| **6.1+** | `setAuthoritiesClaimDelimiter(...)` hỗ trợ tách string claim bằng regex tùy chỉnh |
| **6.x / Boot 3.x** | `JwtAuthenticationConverter`, `JwtGrantedAuthoritiesConverter`, `jwtAuthenticationConverter(...)` vẫn là đường thông dụng |
| **7.x / Boot 4.x** | Kiểm tra DSL, OAuth2 authorization helpers và dependency baseline theo migration guide; cơ chế authority mapping JWT/opaque vẫn tách biệt |

Một số tài liệu Spring Security 7.x còn đề cập authority đánh dấu **authentication factor** như `FACTOR_BEARER`. Đây là thông tin về cơ chế xác thực, **không phải** quyền nghiệp vụ như `ROLE_ADMIN` hoặc scope `SCOPE_messages:read`. Đừng coi nó là permission cho endpoint.

## 15. Bài tập thực hành và tiêu chí hoàn thành

**Bài 1:** JWT có:

```json
{"scp":["invoices:read","invoices:approve"],"roles":["FINANCE"]}
```

Nếu dùng default JWT converter, các authority scope là:

```text
SCOPE_invoices:read
SCOPE_invoices:approve
```

`ROLE_FINANCE` chỉ xuất hiện sau khi khai báo converter phù hợp và xác định issuer thực sự có quyền phát hành role đó.

**Bài 2:** Endpoint `POST /invoices/approve` yêu cầu đồng thời scope phê duyệt và role tài chính. Chỉ `hasAuthority("SCOPE_invoices:approve")` chưa đủ; kết hợp policy, ví dụ trong Spring method security:

```java
@PreAuthorize("hasAuthority('SCOPE_invoices:approve') and hasRole('FINANCE')")
```

Nhớ bật `@EnableMethodSecurity`. Với token thiếu một trong hai authority, phải bị từ chối ngay cả khi có authority còn lại.

**Bài 3:** API chuyển từ JWT sang opaque token nhưng vẫn dùng rule `hasAuthority("SCOPE_invoices:read")`. Kiểm thử introspection response có `scope`, trường `active=true`, issuer endpoint đúng, và mapper opaque có tạo `SCOPE_invoices:read` hay không. Đừng giữ JWT converter rồi mặc định nghĩ nó còn được gọi.

Một triển khai đạt yêu cầu khi: token sai bị từ chối bởi decoder/introspector; token hợp lệ có quyền đúng được truy cập; token hợp lệ thiếu scope/role bị 403; mapping không trao quyền từ claims không có contract rõ ràng; unit và integration tests phản ánh chính xác các trường hợp đó.

## 16. Tài liệu tham khảo

- Spring Security 6.5 — OAuth 2.0 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security 6.5 — OAuth 2.0 Resource Server Opaque Token: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html
- Spring Security API — `JwtGrantedAuthoritiesConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html
- Spring Security API — `JwtAuthenticationConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Reactive Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
