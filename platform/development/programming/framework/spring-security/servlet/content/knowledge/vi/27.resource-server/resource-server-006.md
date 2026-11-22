# `JwtAuthenticationConverter` và `JwtGrantedAuthoritiesConverter` trong Spring Security Servlet

## 1. Mục tiêu của hai converter

Trong **OAuth2 Resource Server dùng JWT** của Spring Security Servlet, hệ thống nhận bearer access token, kiểm tra token rồi tạo `Authentication` để các rule như `hasAuthority(...)`, `hasRole(...)` và `@PreAuthorize(...)` quyết định quyền truy cập.

Hai lớp phục vụ hai tầng biến đổi khác nhau:

- **`JwtGrantedAuthoritiesConverter`**: đọc các claim của một `Jwt` đã được giải mã, chuyển dữ liệu như `scope`/`scp` thành `Collection<GrantedAuthority>`. Mặc định mỗi scope có tiền tố **`SCOPE_`**.
- **`JwtAuthenticationConverter`**: chuyển một `Jwt` thành `AbstractAuthenticationToken` (thực tế thường là `JwtAuthenticationToken`), gắn authorities từ converter con và chọn claim làm tên principal. Mặc định tên principal lấy từ claim `sub`.

Đây là **bước ánh xạ danh tính và quyền**, không phải bước xác minh chữ ký của token. Phần xác minh chữ ký, hạn sử dụng, issuer và các validator khác thuộc `JwtDecoder`/`OAuth2TokenValidator`. Không được dùng converter để “tin” một JWT chưa được kiểm chứng.

Ví dụ token của user:

```json
{
  "iss": "https://auth.example.com/realms/demo",
  "sub": "user-42",
  "preferred_username": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "roles": ["ADMIN", "REVIEWER"],
  "exp": 1893456000
}
```

Với converter **mặc định**, tập authorities thường là:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Claim `roles` **không tự động** trở thành `ROLE_ADMIN` hoặc `ROLE_REVIEWER`. Để dùng `hasRole("ADMIN")`, ứng dụng cần ánh xạ rõ claim role sang `GrantedAuthority("ROLE_ADMIN")`, với điều kiện claim đó do issuer đáng tin cấp và có semantics phù hợp.

## 2. Converter nằm ở đâu trong luồng authentication?

Một request Servlet tới endpoint đã được cấu hình `oauth2ResourceServer().jwt()` trải qua luồng khái niệm:

```text
Client -> GET /api/orders
          Authorization: Bearer eyJ...

  Spring Security filter chain (Servlet)
          |
          v
  BearerTokenAuthenticationFilter
          | lấy bearer token từ request
          v
  JwtAuthenticationProvider
          |
          +-- JwtDecoder
          |     kiểm chữ ký, thuật toán được phép, các claim
          |     thời gian và issuer theo cấu hình/validators
          |
          v
  Jwt (đã được decoder xác nhận)
          |
          v
  JwtAuthenticationConverter
          |
          +-- JwtGrantedAuthoritiesConverter
          |       scope/scp -> SCOPE_...
          |
          v
  JwtAuthenticationToken
          | Jwt principal, name, authorities
          v
  SecurityContext / AuthorizationFilter / method security
          |
          +-- đủ authority -> gọi Controller
          +-- thiếu authority -> 403 (thông thường)
```

Trường hợp bearer token vắng hoặc không hợp lệ, Spring Security có thể trả `401 Unauthorized` với `WWW-Authenticate` thích hợp. Nếu token đã xác thực nhưng thiếu authority, thường là `403 Forbidden`. Status cuối phụ thuộc security entry point/handlers và các lớp phía trước, nên hãy kiểm tra response thực tế.

`JwtAuthenticationConverter` **không tự cấp thêm quyền** cho token. Nó chỉ chuyển dữ liệu **được issuer cung cấp và đã đi qua decoder** sang dạng mà Spring Security hiểu. Sai converter có thể khiến user hợp lệ bị `403`, hoặc tệ hơn, cấp quyền quá rộng.

## 3. `JwtGrantedAuthoritiesConverter` mặc định

Spring Security 6.x biết các well-known authority claims như `scope` và `scp`. Dữ liệu có thể là chuỗi các scope phân cách bằng dấu cách:

```json
{
  "sub": "alice",
  "scope": "orders.read orders.write"
}
```

Hoặc collection:

```json
{
  "sub": "alice",
  "scp": ["orders.read", "orders.write"]
}
```

Mặc định converter đọc **một claim scope được nhận diện** và phát sinh:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Vì vậy endpoint có thể khai báo:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
.hasAuthority("SCOPE_orders.read")
```

**Không viết `hasRole("orders.read")`** nếu bạn đang dùng mapping scope mặc định: `hasRole` sẽ tìm `ROLE_orders.read`, không phải `SCOPE_orders.read`.

Nếu JWT vừa có `scope` vừa có `scp`, không nên mặc định rằng framework luôn hợp nhất cả hai. Muốn quy tắc hợp nhất/ưu tiên rõ ràng, hãy chuẩn hóa token ở authorization server hoặc tự viết converter phù hợp.

Nếu claim chỉ có một chuỗi `"orders.read,orders.write"` phân cách bằng dấu phẩy, cấu hình delimiter phải phù hợp. `setAuthoritiesClaimDelimiter(...)` có trong các phiên bản Spring Security 6.1+; default phù hợp với scope dạng phân cách khoảng trắng. Đừng đổi delimiter tùy tiện nếu issuer tuân theo chuẩn OAuth2 scope.

## 4. Cấu hình claim, prefix và delimiter

`JwtGrantedAuthoritiesConverter` có các tùy chọn quan trọng:

```java
JwtGrantedAuthoritiesConverter authorities =
        new JwtGrantedAuthoritiesConverter();

authorities.setAuthoritiesClaimName("permissions");
authorities.setAuthorityPrefix("PERM_");
```

Khi token có:

```json
{
  "permissions": ["invoices.read", "invoices.approve"]
}
```

Tập authorities sẽ có:

```text
PERM_invoices.read
PERM_invoices.approve
```

Các setter hoạt động như sau:

| Setter | Mục đích | Ví dụ |
| --- | --- | --- |
| `setAuthoritiesClaimName("roles")` | Chọn claim **top-level** chứa quyền | `roles: ["ADMIN"]` |
| `setAuthorityPrefix("ROLE_")` | Tiền tố cho mỗi giá trị của claim | `ADMIN` → `ROLE_ADMIN` |
| `setAuthorityPrefix("")` | Giữ nguyên giá trị, không thêm tiền tố | `ROLE_ADMIN` → `ROLE_ADMIN` |
| `setAuthoritiesClaimDelimiter(",")` | Quy tắc tách **chuỗi** quyền, nếu issuer dùng dấu phẩy | `"a,b"` → `"a"`, `"b"` |

Một `JwtGrantedAuthoritiesConverter` đọc claim được cấu hình và dùng một prefix cho kết quả. Nếu bạn thay authorities claim từ `scope` sang `roles`, **bạn có thể làm mất toàn bộ `SCOPE_*` mặc định** trừ khi chủ động kết hợp cả hai converter. Đó là một trong những lỗi cấu hình phổ biến nhất.

Claim name `"realm_access.roles"` **không được hiểu mặc nhiên là đường dẫn JSON** đến object lồng nhau. Với payload nested, cần converter riêng lấy map/collection và chỉ chấp nhận kiểu dữ liệu được mong đợi.

## 5. `JwtAuthenticationConverter`: authorities và tên principal

`JwtAuthenticationConverter` cho phép tùy chỉnh:

```java
JwtAuthenticationConverter authenticationConverter =
        new JwtAuthenticationConverter();

authenticationConverter.setJwtGrantedAuthoritiesConverter(authorities);
authenticationConverter.setPrincipalClaimName("preferred_username");
```

`setJwtGrantedAuthoritiesConverter` quyết định **quyền**; `setPrincipalClaimName` quyết định tên `Authentication#getName()`.

Ví dụ JWT có:

```json
{
  "sub": "user-42",
  "preferred_username": "alice",
  "roles": ["ADMIN"]
}
```

Nếu converter authority lấy `roles` với prefix `ROLE_`, `hasRole("ADMIN")` sẽ khớp. Nếu principal claim đổi thành `"preferred_username"`, `getName()` có thể là `"alice"` thay vì `"user-42"`.

Tuy nhiên:

- `getName()` là tên được chọn để sử dụng trong ứng dụng; đổi tên claim **không làm tăng độ tin cậy** của token.
- `Authentication#getPrincipal()` trong trường hợp `JwtAuthenticationToken` thường là chính đối tượng `Jwt`, không phải một `UserDetails` tự được tải từ database.
- `preferred_username` có thể thay đổi theo thời gian; nếu cần một định danh ổn định để liên kết user nội bộ, cân nhắc kết hợp `iss + sub`, tùy hợp đồng của identity provider.
- Nếu claim được chọn không tồn tại hoặc không mang kiểu phù hợp, kết quả tên principal có thể không đúng kỳ vọng. Hãy kiểm thử token có claim thiếu/sai kiểu.

Không dùng `preferred_username` hay email làm bằng chứng user đã có vai trò ADMIN. Quyền phải lấy từ claim authority được cấp đúng mục đích, sau khi xác thực issuer/audience và kiểm tra cách provider quản lý roles.

## 6. Ví dụ Java 17+ độc lập, chạy không cần identity provider

Ví dụ xác định chính xác authorities do converter tạo. Chương trình **tự dựng `Jwt` chỉ để minh họa mapping**, không đọc bearer token thật, không kiểm chứng chữ ký và không thực hiện HTTP request. Nó không thay thế cấu hình Resource Server production.

Tạo một dự án Gradle có `build.gradle` như sau:

```groovy
plugins {
    id 'java'
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.security:spring-security-oauth2-resource-server'
    implementation 'org.springframework.security:spring-security-oauth2-jose'
}

application {
    mainClass = 'demo.jwt.JwtConverterDemo'
}
```

Tạo `src/main/java/demo/jwt/JwtConverterDemo.java`:

```java
package demo.jwt;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public final class JwtConverterDemo {
    private JwtConverterDemo() {}

    public static void main(String[] args) {
        Instant issuedAt = Instant.parse("2026-01-01T00:00:00Z");

        // Jwt giả lập phục vụ mapping, KHÔNG phải token có chữ ký hợp lệ.
        Jwt jwt = Jwt.withTokenValue("demo-not-a-real-token")
                .header("alg", "RS256")
                .claim("sub", "user-42")
                .claim("preferred_username", "alice")
                .claim("scope", "orders.read orders.write")
                .claim("roles", List.of("ADMIN", "REVIEWER"))
                .issuedAt(issuedAt)
                .expiresAt(issuedAt.plusSeconds(3600))
                .build();

        JwtAuthenticationConverter defaults =
                new JwtAuthenticationConverter();
        AbstractAuthenticationToken defaultAuth = defaults.convert(jwt);

        System.out.println("default.name=" + defaultAuth.getName());
        System.out.println("default.authorities=" + names(defaultAuth));

        // Tách hai tập scope và role.
        JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();

        JwtGrantedAuthoritiesConverter roles =
                new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");

        JwtAuthenticationConverter combined =
                new JwtAuthenticationConverter();
        combined.setPrincipalClaimName("preferred_username");

        combined.setJwtGrantedAuthoritiesConverter(token -> {
            List<GrantedAuthority> granted = new ArrayList<>();
            granted.addAll(scopes.convert(token));
            granted.addAll(roles.convert(token));
            return granted;
        });

        AbstractAuthenticationToken combinedAuth = combined.convert(jwt);

        System.out.println("combined.name=" + combinedAuth.getName());
        System.out.println("combined.authorities=" + names(combinedAuth));
        System.out.println("canReadOrders=" +
                names(combinedAuth).contains("SCOPE_orders.read"));
        System.out.println("hasAdminRole=" +
                names(combinedAuth).contains("ROLE_ADMIN"));
    }

    private static List<String> names(AbstractAuthenticationToken auth) {
        return auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();
    }
}
```

Chạy từ thư mục dự án có Gradle wrapper:

```bash
./gradlew run
```

Windows PowerShell:

```powershell
.\gradlew.bat run
```

**Stdout của chương trình Java** (không tính các dòng Gradle):

```text
default.name=user-42
default.authorities=[SCOPE_orders.read, SCOPE_orders.write]
combined.name=alice
combined.authorities=[ROLE_ADMIN, ROLE_REVIEWER, SCOPE_orders.read, SCOPE_orders.write]
canReadOrders=true
hasAdminRole=true
```

Giải thích: mặc định chỉ lấy scope; converter kết hợp lấy scope **và** roles, đồng thời đổi tên principal sang `preferred_username`. `sorted()` bảo đảm thứ tự stdout ổn định để học và kiểm thử. Không có `JwtDecoder` trong chương trình: việc tự tạo `Jwt` là **một cách test ánh xạ**, không chứng minh token hợp lệ theo bảo mật.

## 7. Cấu hình trong Spring Boot 3.3.x Resource Server (Servlet)

Ứng dụng thực tế có Spring MVC và JWT Resource Server cần các dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Cấu hình `application.yml` minh họa:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/demo
```

Đây là **URI ví dụ**. Khi triển khai thật, `issuer-uri` phải chỉ đúng issuer mà API tin cậy, có tài liệu metadata/JWK hỗ trợ và các thuật toán/chính sách phù hợp. Cấu hình này giúp framework thiết lập `JwtDecoder` nhưng **không tự biến claim `roles` thành `ROLE_*`**.

Tạo file `src/main/java/demo/security/JwtSecurityConfig.java` trong Spring Boot application đã có main class và các API tương ứng:

```java
package demo.security;

import java.util.ArrayList;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
public class JwtSecurityConfig {
    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();

        JwtGrantedAuthoritiesConverter roles =
                new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setPrincipalClaimName("sub");
        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            List<GrantedAuthority> granted = new ArrayList<>();
            granted.addAll(scopes.convert(jwt));
            granted.addAll(roles.convert(jwt));
            return granted;
        });
        return converter;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JwtAuthenticationConverter jwtConverter) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/actuator/health").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                                .hasAuthority("SCOPE_orders.read")
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(resource -> resource.jwt(jwt ->
                        jwt.jwtAuthenticationConverter(jwtConverter)))
                .build();
    }
}
```

**Những điểm phải hiểu trước khi áp dụng:**

1. `JwtDecoder` chịu trách nhiệm xử lý token; `JwtAuthenticationConverter` chỉ quyết định principal/authorities sau decode.
2. `scopes` dùng default `scope`/`scp` và prefix `SCOPE_`; `roles` dùng claim `roles` và prefix `ROLE_`.
3. `hasAuthority("SCOPE_orders.read")` so khớp chuỗi authority chính xác.
4. `hasRole("ADMIN")` so khớp `ROLE_ADMIN` theo prefix role mặc định của Spring Security.
5. `/api/admin/**` đang được yêu cầu `ROLE_ADMIN`, nên `roles: ["ADMIN"]` chỉ được tin nếu issuer và audience được xác minh đúng.
6. Đây là **một cấu hình cho application demo**, không phải class thêm song song khi dự án đã có filter chain hoặc converter khác mà chưa phân tích thứ tự/matcher.
7. Ví dụ không tự tắt CSRF. Với API stateless chỉ nhận bearer token trong `Authorization` header, phải xác định chính sách session và CSRF theo cách client thực sự gửi credential; nếu còn cookie/session thì không tắt CSRF tùy tiện.

### Một endpoint chỉ đọc claims an toàn

Tạo controller trong application có Bean Security ở trên:

```java
package demo.security;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {
    @GetMapping("/api/me")
    public Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
                "subject", jwt.getSubject(),
                "issuer", String.valueOf(jwt.getIssuer()));
    }
}
```

`@AuthenticationPrincipal Jwt` truy cập `Jwt` đã xác thực trong Resource Server. Tránh trả toàn bộ `getClaims()` hoặc raw JWT vào response: claims có thể chứa dữ liệu nhạy cảm. `jwt.getSubject()` cần tồn tại nếu app dùng nó làm identity; kiểm tra hợp đồng claim ở issuer.

Để gọi HTTP thực:

```bash
curl -i https://api.example.com/api/me \
  -H "Authorization: Bearer <access-token-do-issuer-cap>"
```

Kết quả thành công phụ thuộc API thật, issuer, JWT hợp lệ và cấu hình decoder; ví dụ không có token thật nên **không đưa ra output HTTP giả định**.

## 8. Kiểm soát tên claim và chuẩn hóa role

Không có chuẩn OAuth2 bắt buộc mọi issuer đều cấp claim `roles` dưới đúng một schema. Một số provider có:

```json
{
  "roles": ["ADMIN", "USER"]
}
```

Một số khác:

```json
{
  "realm_access": {
    "roles": ["ADMIN", "USER"]
  }
}
```

Hoặc:

```json
{
  "resource_access": {
    "orders-api": {
      "roles": ["ORDER_REVIEWER"]
    }
  }
}
```

`setAuthoritiesClaimName("realm_access.roles")` không tự duyệt nested JSON theo dấu chấm. Đối với các object lồng, viết `Converter<Jwt, Collection<GrantedAuthority>>` riêng để lấy đúng path và validate kiểu dữ liệu.

Đoạn minh họa cho claim nested `realm_access.roles`:

```java
// Đặt trong method/cấu hình có biến jwt kiểu Jwt.
Map<String, Object> realm = jwt.getClaimAsMap("realm_access");
Object rawRoles = realm == null ? null : realm.get("roles");
List<GrantedAuthority> out = new ArrayList<>();

if (rawRoles instanceof Collection<?> items) {
    for (Object item : items) {
        if (item instanceof String role
                && role.matches("[A-Z][A-Z0-9_]{0,40}")) {
            out.add(new SimpleGrantedAuthority("ROLE_" + role));
        }
    }
}
```

Đây là **đoạn minh họa, không độc lập**. Cần import `Map`, `Collection`, `List`, `ArrayList`, `GrantedAuthority`, `SimpleGrantedAuthority`. Regex chỉ là ví dụ ràng buộc định dạng nội bộ, **không thay thế danh sách role được công nhận**. Với claims từ nhiều issuers, không tự coi cùng một chuỗi `"ADMIN"` có ý nghĩa quyền ngang nhau. Nên phân tách issuer/audience và ánh xạ vào tập permission nội bộ được thiết kế rõ.

### Chống cấp quyền quá rộng

Giả sử developer viết:

```java
roles.setAuthorityPrefix("");
```

trong khi rule dùng `hasRole("ADMIN")`. Converter sẽ tạo authority `"ADMIN"` nhưng `hasRole("ADMIN")` yêu cầu `"ROLE_ADMIN"`; kết quả là `403`. Nếu token đã chứa `"ROLE_ADMIN"` và bạn lại để prefix `"ROLE_"`, authority thành `"ROLE_ROLE_ADMIN"`.

Hãy chọn **một contract chuẩn**: hoặc token chứa `ADMIN` và converter thêm `ROLE_`, hoặc token đã có `ROLE_ADMIN` và converter giữ nguyên. Không sửa role prefix trên diện rộng để qua một bài test khi chưa hiểu schema của issuer.

## 9. Test converter mà không cần JWT ký thật

Tách việc kiểm thử **mapping** khỏi việc kiểm thử **decode/validate**. Với unit test mapping, có thể tạo một `Jwt` giả trong memory như chương trình ở mục 6.

Ví dụ JUnit 5, thêm vào project demo ở mục 6:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tạo `src/test/java/demo/jwt/JwtConverterTest.java`:

```java
package demo.jwt;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

import static org.assertj.core.api.Assertions.assertThat;

class JwtConverterTest {
    private Jwt jwt(String scope, List<String> roles) {
        Instant issued = Instant.parse("2026-01-01T00:00:00Z");
        return Jwt.withTokenValue("fake-for-test")
                .header("alg", "RS256")
                .claim("sub", "alice")
                .claim("scope", scope)
                .claim("roles", roles)
                .issuedAt(issued)
                .expiresAt(issued.plusSeconds(600))
                .build();
    }

    @Test
    void defaultMappingAddsScopePrefix() {
        var auth = new JwtAuthenticationConverter()
                .convert(jwt("orders.read orders.write", List.of("ADMIN")));

        assertThat(auth.getAuthorities())
                .extracting("authority")
                .containsExactlyInAnyOrder(
                        "SCOPE_orders.read", "SCOPE_orders.write");
    }

    @Test
    void rolesMappingUsesRolePrefix() {
        JwtGrantedAuthoritiesConverter roles =
                new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(roles);

        var auth = converter.convert(jwt("orders.read", List.of("ADMIN")));
        assertThat(auth.getAuthorities())
                .extracting("authority")
                .containsExactly("ROLE_ADMIN");
    }

    @Test
    void absentRoleClaimDoesNotCreateAdminRole() {
        JwtGrantedAuthoritiesConverter roles =
                new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");

        Instant issued = Instant.parse("2026-01-01T00:00:00Z");
        Jwt token = Jwt.withTokenValue("fake-for-test")
                .header("alg", "RS256")
                .claim("sub", "bob")
                .claim("scope", "orders.read")
                .issuedAt(issued)
                .expiresAt(issued.plusSeconds(600))
                .build();

        assertThat(roles.convert(token)).isEmpty();
    }
}
```

Chạy:

```bash
./gradlew test
```

Các test này chỉ tạo `Jwt` trong bộ nhớ để chứng minh converter không tự suy ra quyền ngoài claim. Chúng **không** chứng minh chữ ký JWT hợp lệ hoặc Spring Security filter chain phân quyền đúng ở HTTP. Cần test tích hợp với `MockMvc` và Spring Security test support (ví dụ JWT post-processor hoặc cấu hình JwtDecoder stub), rồi test `401`/`403`/`200` theo endpoint. Với môi trường thật, thử token sai issuer/audience/chữ ký, hết hạn, thiếu scope, hoặc claim sai kiểu.

## 10. Điều gì xảy ra khi claim thiếu hoặc sai kiểu?

`JwtGrantedAuthoritiesConverter` không phải trình phân tích cú pháp JWT tổng quát và không phải nơi sửa mọi claim bất thường. Các trường hợp nên được chủ động kiểm thử:

| JWT / cấu hình | Authority mong đợi | Hệ quả |
| --- | --- | --- |
| `scope: "orders.read"` | `SCOPE_orders.read` | `hasAuthority("SCOPE_orders.read")` có thể khớp |
| `scp: ["orders.read"]` | `SCOPE_orders.read` (mặc định) | Hữu ích khi issuer dùng array |
| `roles: ["ADMIN"]` + roles converter `ROLE_` | `ROLE_ADMIN` | `hasRole("ADMIN")` có thể khớp |
| `roles` không tồn tại | Không có `ROLE_ADMIN` từ converter đó | Không tự cấp role |
| `roles: ["ROLE_ADMIN"]` + prefix `ROLE_` | `ROLE_ROLE_ADMIN` | Sai contract, thường dẫn đến 403 |
| Custom converter chỉ đọc `roles` | Không còn `SCOPE_orders.read` trừ khi tự gộp | Rule dựa vào scope có thể thất bại |
| `realm_access.roles` nằm trong object nested | Không tự giải qua dotted path | Cần converter nested |
| `"scope": "orders.read,orders.write"` | Cần delimiter phù hợp nếu issuer dùng comma | Tránh tạo một authority chứa cả chuỗi |

Với claim sai kiểu, đừng âm thầm biến object bất kỳ thành role `"ADMIN"` bằng `toString()` hoặc chuyển mọi chuỗi thành authority. Nên thất bại theo policy rõ ràng, ghi log đã loại bỏ thông tin nhạy cảm và yêu cầu provider phát token đúng schema.

## 11. Decoder, issuer và audience vẫn là hàng rào bảo mật chính

Giả sử một attacker tự tạo JWT có:

```json
{
  "sub": "attacker",
  "roles": ["ADMIN"],
  "scope": "orders.read"
}
```

Nếu application chỉ chạy converter lên object này mà không xác minh token, nó sẽ thấy `ROLE_ADMIN`. Điều đó **không chứng minh attacker đã xác thực**. Chỉ được tin role/scope khi token đã qua decoder với chữ ký, thuật toán, thời gian và issuer hợp lệ, đồng thời audience/scope đáp ứng yêu cầu API.

Cấu hình `issuer-uri` giúp framework định danh nhà phát hành đáng tin và sử dụng JWK/metadata phù hợp, nhưng API vẫn cần quyết định xem JWT **có dành cho chính API này** không. Việc kiểm tra audience (`aud`) cần được xem xét/cấu hình rõ theo provider và phiên bản framework; không giả định mọi cấu hình issuer mặc định đã buộc audience bằng API của mình.

Bảo mật đầy đủ gồm:

1. **Signature/algorithm:** chỉ chấp nhận thuật toán/keys mong đợi, không tin header `alg` từ input theo cách bỏ kiểm.
2. **Issuer:** token do đúng authorization server phát hành.
3. **Audience:** token dành cho Resource Server của bạn.
4. **Time:** `exp`, `nbf` và clock skew, có thể thêm policy về token lifetime.
5. **Scopes/roles:** converter ánh xạ claim và `AuthorizationManager` kiểm tra quyền của endpoint.
6. **Token handling:** chỉ dùng HTTPS, không ghi bearer token ra log, không đưa token sang downstream service không thuộc audience.
7. **Revocation:** với JWT tự chứa, tính tức thời của revocation khác opaque token introspection; thiết kế lifetime và revocation strategy theo yêu cầu.

Đừng coi `setAuthorityPrefix("ROLE_")` là một biện pháp kiểm tra vai trò thực sự tồn tại ở hệ thống nghiệp vụ. Nó chỉ tạo một chuỗi authority từ dữ liệu JWT đã được xác minh.

## 12. Authorities, permissions và kiểm tra ở phương thức

Trong Spring Security, `GrantedAuthority#getAuthority()` là một chuỗi quyền mà authorization logic có thể kiểm tra.

```java
.hasAuthority("SCOPE_orders.read")
.hasRole("ADMIN")
```

`hasRole("ADMIN")` mặc định tương đương tìm authority `"ROLE_ADMIN"`. `hasAuthority("ADMIN")` lại tìm chính xác `"ADMIN"`. Hai biểu thức không đồng nghĩa.

Nếu dùng method security trong Spring Security 6.x, cần kích hoạt:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {}
```

Sau đó có thể dùng trong service/controller phù hợp:

```java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Order findOrder(String id) {
    // Phần nghiệp vụ minh họa; đây không phải method độc lập.
    return orderRepository.findById(id).orElseThrow();
}
```

Đoạn method giả định `Order`, `orderRepository` và cấu hình method security đã tồn tại. `JwtAuthenticationConverter` cung cấp authorities cho `Authentication` mà method security kiểm tra, nhưng việc dùng quyền còn cần xem object-level authorization: `orders.read` có thể cho phép đọc danh sách, **không đồng nghĩa user được đọc mọi order của tenant khác**.

Với tài nguyên đa tenant, luôn đối chiếu tenant/resource ownership ở tầng nghiệp vụ. Không suy ra quyền theo path hoặc chỉ role `"ADMIN"` khi admin thực tế chỉ được quản lý trong tenant của họ.

## 13. Lỗi thường gặp và cách tìm nguyên nhân

| Triệu chứng | Nguyên nhân khả dĩ | Cách xác minh |
| --- | --- | --- |
| JWT hợp lệ nhưng endpoint trả `403` | Claim role không được map, thiếu prefix hoặc scope | Kiểm tra authorities sau converter (không log raw JWT) |
| `hasRole("ADMIN")` luôn sai | Có `"ADMIN"` thay vì `"ROLE_ADMIN"`, hoặc `"ROLE_ROLE_ADMIN"` | Xem chính xác chuỗi authority |
| Có `roles`, mất `SCOPE_*` | Đã thay default converter bằng role-only converter | Gộp role + scope nếu API cần cả hai |
| Token dùng `scp` nhưng converter tìm `permissions` | Claim name sai | Xác minh payload schema và cấu hình |
| Token có nested roles nhưng converter không thấy | `setAuthoritiesClaimName` không phải JSONPath | Viết converter cho nested structure |
| Authentication name không như kỳ vọng | `sub` khác `preferred_username`; thiếu principal claim | Kiểm tra `setPrincipalClaimName` và hợp đồng issuer |
| `401` trước khi vào controller | Token thiếu/hỏng, signature, issuer, expiration, Bearer parse | Kiểm tra decoder, `WWW-Authenticate` và security debug an toàn |
| Có authority nhưng user vẫn không đọc được object | Authorization của nghiệp vụ/tenant bổ sung | Kiểm tra quyền trên resource, không tắt kiểm tra |
| API chấp nhận token từ hệ thống khác | Validation issuer/audience không đủ chặt | Cố định decoder, issuer, audience và thử negative tests |
| Request bị `403` với POST nhưng GET chạy | Có thể là CSRF trong app dùng cookie, không chỉ role | Phân biệt CSRF với thiếu authority |
| Authority rác xuất hiện từ claim | Converter tùy chỉnh dùng `toString()`/prefix quá rộng | Chỉ nhận kiểu claim đúng, có allowlist quyền |

Trong production, muốn chẩn đoán quyền, có thể tạm ghi **registration/issuer đã chuẩn hóa, user ID an toàn và danh sách authority được giới hạn** ở log nội bộ với quyền truy cập chặt. Không log access token, JWT raw, token claims chứa PII hoặc private key.

## 14. Thiết kế mapping nhất quán cho nhiều issuer

Khi API nhận token từ nhiều identity providers, `"ADMIN"` của provider A có thể mang nghĩa khác provider B. Đừng gộp cả hai vào `ROLE_ADMIN` toàn cục nếu không có hợp đồng rõ.

Các câu hỏi kiến trúc quan trọng:

- API chấp nhận những issuer nào, audience của mỗi issuer có giống nhau không?
- `scope`, `scp`, `roles` hay nested `resource_access` là claim chuẩn của từng provider?
- Role là **global**, **client-level** hay **tenant-level**?
- Issuer có được quyền cấp role `"ADMIN"` của chính API này hay chỉ cấp role trong hệ thống của họ?
- Nếu muốn dùng một bộ authority nội bộ, ai quản lý bảng ánh xạ provider role → permission và ai phê duyệt thay đổi?
- Token thiếu claim quan trọng có bị từ chối hay được xem là authenticated nhưng không có quyền?

Spring Security có thể dùng custom `JwtAuthenticationConverter`, `AuthenticationManagerResolver` hoặc decoder/validator phù hợp cho nhiều issuer. Phải xác minh token thuộc issuer tin cậy **trước** khi diễn giải role. Không dùng claim `iss` do token chưa xác minh để trao quyền cao hơn.

## 15. Các bước kiểm thử end-to-end

Một kế hoạch kiểm thử có giá trị học tập và vận hành:

1. **Mapping mặc định:** JWT giả có `"scope": "orders.read"` phải tạo `SCOPE_orders.read`.
2. **Mapping role:** `"roles": ["ADMIN"]` phải tạo `ROLE_ADMIN` khi contract định nghĩa như vậy.
3. **Kết hợp:** JWT có cả `scope` và `roles` phải giữ đủ hai nhóm, không tự nhân đôi hoặc thêm quyền ngoài danh sách.
4. **Claim thiếu/sai:** không có roles hoặc roles sai kiểu phải không tạo `ROLE_ADMIN`.
5. **Principal:** kiểm tra `getName()` là `sub` hoặc claim đã chọn; tránh dùng username thay cho immutable user ID khi liên kết dữ liệu.
6. **HTTP authentication:** không có token hoặc token sai chữ ký/issuer/expiration trả response lỗi xác thực; token hợp lệ đúng scope đi vào endpoint.
7. **HTTP authorization:** token hợp lệ nhưng thiếu `ROLE_ADMIN` không được gọi admin API, thường nhận 403.
8. **Audience:** token hợp lệ về chữ ký nhưng dành cho API khác phải bị từ chối theo validator đã cấu hình.
9. **Method/object security:** quyền cấp cao vẫn phải chịu kiểm tra tenant ownership khi nghiệp vụ yêu cầu.
10. **Logging:** mọi thử nghiệm không để lộ bearer token và private claims trong response/log.

Có thể tạo JWT test qua `MockMvc` + `spring-security-test` để kiểm tra authorization rules, và test riêng `JwtDecoder`/JWK với key thật hoặc stub. Lưu ý: một test dùng `jwt()` post-processor để gắn sẵn authorities **có thể bỏ qua chính converter đang kiểm tra**. Hãy unit test converter trực tiếp như mục 9, hoặc tạo test thực sự đi qua resource server filter/decoder nếu mục tiêu là xác nhận toàn bộ đường đi.

## 16. Checklist cấu hình

Trước khi đưa converter tùy chỉnh lên production, kiểm tra:

- `JwtDecoder` xác minh chữ ký/issuer, thời gian, audience theo hợp đồng token.
- Claim scope/role đến từ issuer đáng tin và có semantics đúng cho API.
- `JwtAuthenticationConverter` được gắn vào **đúng** `SecurityFilterChain` và resource server JWT configuration.
- `setAuthoritiesClaimName`, prefix và delimiter khớp dạng dữ liệu thực tế.
- Khi thêm roles, không vô tình bỏ `SCOPE_*` nếu rule vẫn phụ thuộc scopes.
- `hasRole("X")` và `hasAuthority("ROLE_X")` được sử dụng nhất quán.
- Với claim nested, dùng converter có kiểm tra type/path; không coi dấu chấm trong claim name là JSONPath.
- Tên principal ổn định cho nghiệp vụ; không mặc định username/email là định danh vĩnh viễn.
- Có negative tests cho token không quyền, issuer/audience sai, claim rỗng/sai kiểu.
- Không đưa JWT raw/secret vào logs, response hoặc metrics.

## Ghi nhớ

`JwtGrantedAuthoritiesConverter` trả lời câu hỏi **“JWT này cho ra các `GrantedAuthority` nào?”**. `JwtAuthenticationConverter` trả lời **“từ JWT đã được xác minh, tạo `Authentication` với principal và authorities ra sao?”**. Mặc định Spring Security ánh xạ `scope`/`scp` thành `SCOPE_*` và `sub` thành tên principal. Với role/permission tùy chỉnh, hãy khai báo claim và prefix rõ ràng, gộp converter đúng nhu cầu, đồng thời để `JwtDecoder` và authorization rules tiếp tục đảm nhiệm phần kiểm tra bảo mật thực sự.