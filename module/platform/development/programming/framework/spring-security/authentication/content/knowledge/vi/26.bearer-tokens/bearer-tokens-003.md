# JwtAuthenticationProvider, JwtDecoder và Authentication kết quả

## 1. Bài toán: từ Bearer JWT đến người dùng được xác thực trong Spring Security

Một HTTP API nhận request:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
```

Bên trong Spring Security Servlet Resource Server, nhận được token **chưa đồng nghĩa** xác thực thành công. Request phải đi qua chuỗi xác minh Bearer token, giải mã JWT, kiểm tra chữ ký/claims, chuyển claims hợp lệ thành `Authentication`, rồi kiểm tra quyền truy cập đối với endpoint hoặc tài nguyên nghiệp vụ.

Ba đối tượng trọng tâm:

- **`JwtDecoder`:** nhận chuỗi JWT, xác minh và tạo `Jwt`; những điều kiện như chữ ký, thời gian, issuer và audience phải được áp dụng bằng decoder/validators thích hợp.
- **`JwtAuthenticationProvider`:** triển khai `AuthenticationProvider` cho JWT Bearer. Nó gọi decoder và converter, tạo ra `Authentication` đã xác thực hoặc báo thất bại.
- **`JwtAuthenticationToken`:** kiểu `Authentication` kết quả mặc định, giữ `Jwt`, tên principal, danh sách `GrantedAuthority` và trạng thái authenticated.

Thành phần quan trọng thứ tư là **`JwtAuthenticationConverter`**, giúp quyết định claim nào tạo tên principal và claim nào tạo authorities. Cùng một JWT có thể chứa `sub=user-42`, `preferred_username=alice` và `scope=orders.read`; những giá trị này có ý nghĩa khác nhau.

Bài học tập trung vào **Spring Security Servlet (MVC), Java 17+, Spring Boot 3.x / Spring Security 6.x**. Phần WebFlux dùng `ReactiveJwtDecoder` và `JwtReactiveAuthenticationManager` nên không sử dụng trực tiếp cùng bộ filter/provider như Servlet.

Sau bài này, bạn cần trả lời được:

1. Bearer header đi qua thành phần nào, và bước nào là xác thực thật?
2. `JwtDecoder` khác `JwtAuthenticationProvider` ở trách nhiệm gì?
3. `JwtAuthenticationToken.getPrincipal()`, `getName()` và `getAuthorities()` là gì?
4. Khi chữ ký đúng nhưng audience sai hoặc scope thiếu, phản hồi cần là gì?
5. Tùy chỉnh converter và kiểm thử thế nào để không biến unit test giả lập thành bằng chứng JWT đã xác minh ngoài thực tế?

## 2. Luồng xử lý toàn phần

```text
Client -> Authorization: Bearer <jwt>
                 |
                 v
       SecurityFilterChain (Servlet)
                 |
                 v
       BearerTokenAuthenticationFilter
         - BearerTokenResolver lấy chuỗi token
         - tạo BearerTokenAuthenticationToken (chưa xác thực)
                 |
                 v
       AuthenticationManager / ProviderManager
                 |
                 v
       JwtAuthenticationProvider
                 |
                 +------> JwtDecoder.decode(rawToken)
                 |          |
                 |          +-- verify chữ ký/thuật toán/khóa tin cậy
                 |          +-- validate exp/nbf/iss/aud... theo cấu hình
                 |          +-- trả Jwt hoặc ném JwtException
                 |
                 +------> JwtAuthenticationConverter
                            |
                            +-- name từ sub (mặc định)
                            +-- authorities từ scope/scp (mặc định)
                            |
                            v
                     JwtAuthenticationToken
                 |
                 v
       SecurityContextHolder / SecurityContext của request
                 |
                 v
       AuthorizationFilter, @PreAuthorize, business ACL
                 |
           allow hoặc deny
```

**BearerTokenAuthenticationToken là đầu vào; JwtAuthenticationToken là kết quả.** `BearerTokenAuthenticationToken` chỉ chứa credential chưa được tin; không bao giờ lấy claims trực tiếp từ nó để cấp quyền.

`JwtDecoder` chỉ trả `Jwt` sau khi token vượt qua các bước xác minh đã cấu hình. Điều này khác với thao tác Base64URL-decode JWT: decode payload có thể đọc được `role=ADMIN` do kẻ tấn công tự ghi nhưng **không chứng minh** role hay chữ ký hợp lệ.

`JwtAuthenticationProvider` nhận kết quả decoder, chuyển nó thành `Authentication` qua converter và giao lại cho manager/filter. Provider không sở hữu HTTP endpoint và không quyết định người dùng có quyền đọc đơn hàng số 42 hay không. Quyết định cuối thuộc authorization.

### Phân biệt dữ liệu ở từng giai đoạn

| Lớp | Kiểu giá trị | Có thể tin đến đâu? |
| --- | --- | --- |
| HTTP request | Chuỗi trong `Authorization` | Chưa tin |
| Filter/manager | `BearerTokenAuthenticationToken` | Authentication request, chưa được xác minh |
| Decoder | `Jwt` | Đã qua signature/validators thực sự được cấu hình |
| Provider/converter | `JwtAuthenticationToken` | Authentication đã xác thực, mang principal/authorities |
| Authorization | Kết quả policy cho resource | Có hoặc không được truy cập thao tác này |

Luồng trên là cho JWT. Nếu access token là chuỗi **opaque**, dùng introspection (`OpaqueTokenIntrospector`) và cơ chế authentication tương ứng; không đưa opaque token vào `JwtDecoder` rồi thử parse tùy tiện.

## 3. JwtDecoder: kiểm tra tính hợp lệ trước khi tin claims

Giao diện chính có phương thức `Jwt decode(String token) throws JwtException`. Với JWT ký bằng JWS và cấu hình thông thường, Spring Security dùng `NimbusJwtDecoder` để xử lý chữ ký, thuật toán, khóa công khai/JWKS và validators. `Jwt` trả về chứa token, header, claims và các accessor cho thời gian, issuer, subject, audience.

Một payload minh họa:

```json
{
  "iss": "https://idp.example.test/realms/demo",
  "sub": "user-42",
  "aud": ["orders-api"],
  "exp": 1796205600,
  "iat": 1796202000,
  "scope": "orders.read orders.write",
  "preferred_username": "alice"
}
```

**Đây chỉ là JSON minh họa; không phải JWT đã được ký.** Decoder thực phải xác minh trước khi ứng dụng được phép tin các claims.

### Những điều cần xác minh

**Chữ ký và thuật toán.** Decoder chỉ được chấp nhận các thuật toán ký trong allowlist theo thiết kế và khóa từ issuer/JWKS đáng tin. Không dùng `alg` do token tự khai báo để tự động bỏ qua chữ ký hoặc chọn thuật toán tùy ý. Với JWT sử dụng RS256/ES256, resource server xác minh bằng khóa công khai tương ứng và cần xử lý key rotation an toàn.

**Issuer (`iss`).** Token phải do issuer mà API tin cậy phát hành. Dù hai tenant sử dụng cùng domain/JWKS, `iss` không được đánh đồng nếu chính sách không cho phép.

**Thời gian (`exp` và `nbf`).** Token hết hạn hoặc chưa đến thời điểm có hiệu lực phải bị từ chối theo các validator và clock skew hợp lý. `iat` là thời điểm phát hành; nếu yêu cầu token không quá cũ, cần kiểm tra chính sách tuổi token riêng.

**Audience (`aud`).** Chữ ký hợp lệ và issuer đúng vẫn chưa đủ: token có thể dành cho API khác. Với một số cấu hình `issuer-uri`, kiểm tra issuer/thời gian có sẵn, nhưng ứng dụng cần **bảo đảm có validator audience tương ứng**; không mặc định `aud` luôn được kiểm tra theo kỳ vọng.

**Token type và profile.** OAuth2 access token cho API khác OIDC ID token cho client. Khi áp dụng JWT access token profile (ví dụ RFC 9068), cần kiểm tra profile/`typ`, issuer/audience/claim yêu cầu theo hệ thống. Một JWT “ký đúng” chưa phải bearer access token cho mọi resource.

**Thu hồi.** Chữ ký, `exp` và `aud` đúng không tự phản ánh việc người dùng đã logout hay token bị revoke ở authorization server. Nếu cần thu hồi gần như ngay lập tức, cân nhắc TTL ngắn, introspection, denylist hoặc event/version phù hợp. `JwtDecoder` mặc định không hỏi IdP về mọi session người dùng.

### Ví dụ về kết hợp validators

Không nên viết:

```java
// NGUY HIỂM: chỉ còn validator tự thêm, có thể làm mất kiểm tra
// issuer/thời gian vốn tồn tại trước đó.
decoder.setJwtValidator(
    new JwtClaimValidator<java.util.List<String>>(
        "aud", audiences -> audiences.contains("orders-api")));
```

Nên kết hợp cả validator mặc định và validator ứng dụng:

```java
OAuth2TokenValidator<Jwt> issuerAndTime =
    JwtValidators.createDefaultWithIssuer(issuer);

OAuth2TokenValidator<Jwt> audience =
    new JwtClaimValidator<java.util.List<String>>(
        JwtClaimNames.AUD,
        aud -> aud != null && aud.contains("orders-api"));

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
```

Các đoạn này là **snippet** nằm trong phương thức cấu hình `JwtDecoder`, cần imports và biến `issuer` thích hợp. `setJwtValidator(...)` ghi đè validator hiện có; kết hợp đúng để giữ kiểm tra issuer/time.

## 4. JwtAuthenticationProvider: cầu nối đến AuthenticationManager

`JwtAuthenticationProvider` implements `AuthenticationProvider`, nhận decoder qua constructor:

```java
JwtAuthenticationProvider provider =
    new JwtAuthenticationProvider(jwtDecoder);
```

Provider hỗ trợ `BearerTokenAuthenticationToken`, gọi decoder và converter. Nếu decoder ném `BadJwtException`, provider chuyển lỗi thành thất bại xác thực, không tạo kết quả success. Các lỗi hạ tầng/`JwtException` khác có thể có loại exception khác, nên không mặc định mọi lỗi đều trả chính xác cùng status HTTP mà không kiểm tra cấu hình xử lý exception.

Nếu decoder trả `Jwt` hợp lệ, `JwtAuthenticationProvider` dùng `JwtAuthenticationConverter` mặc định (hoặc converter được cấu hình) để tạo `AbstractAuthenticationToken`, thường là `JwtAuthenticationToken`. Kết quả này đã có `isAuthenticated()==true`.

Với cấu hình `http.oauth2ResourceServer(oauth2 -> oauth2.jwt(...))`, Spring Security tự tổ chức filter và provider. **Không cần tự đăng ký provider** chỉ để ứng dụng nhận JWT; việc tạo provider thủ công thường dành cho kiểm thử riêng hoặc cấu hình đặc thù.

### Trách nhiệm không thuộc JwtAuthenticationProvider

- Không phát hành JWT và không làm OAuth2 authorization code/token exchange.
- Không làm mới refresh token.
- Không truy vấn quyền dữ liệu của từng đơn hàng nếu bạn chưa viết authorization tương ứng.
- Không tạo phiên đăng nhập web từ ID token; đó là cơ chế OIDC login khác.
- Không tự định nghĩa chính sách issuer, audience, algorithm hay khóa đúng; nguồn chính sách nằm ở decoder và cấu hình.
- Không tự ngăn token còn hiệu lực nhưng đã bị thu hồi trừ khi decoder/authorization có cơ chế bổ sung.

## 5. Authentication kết quả: JwtAuthenticationToken

Với payload ở mục 3 và converter mặc định, ví dụ `Authentication` sau khi xác thực có:

| Phương thức | Giá trị minh họa | Nguồn |
| --- | --- | --- |
| `auth.getClass().getSimpleName()` | `JwtAuthenticationToken` | Kết quả converter |
| `auth.isAuthenticated()` | `true` | Provider xử lý thành công |
| `auth.getName()` | `user-42` | `sub` mặc định |
| `((JwtAuthenticationToken)auth).getToken().getSubject()` | `user-42` | Jwt subject |
| `auth.getAuthorities()` | `SCOPE_orders.read`, `SCOPE_orders.write` | Từ claim `scope` |
| `((JwtAuthenticationToken)auth).getTokenAttributes()` | Map claims JWT | Thông tin token đã xác minh |

Mặc định `JwtGrantedAuthoritiesConverter` đọc `scope` hoặc `scp`, tách chuỗi scope theo khoảng trắng hoặc xử lý collection khi phù hợp, rồi thêm prefix `SCOPE_`.

```text
scope = "orders.read orders.write"
              |
              v
SCOPE_orders.read
SCOPE_orders.write

hasAuthority("SCOPE_orders.read")  -> có thể đúng
hasRole("ADMIN")                    -> không được suy ra
```

`getName()` có thể đổi theo converter, nhưng `getToken().getSubject()` vẫn phản ánh `sub`. Ví dụ `setPrincipalClaimName("preferred_username")` cho tên “alice” thay vì “user-42”. Để nối tài khoản trong hệ thống nhiều issuer/tenant, thường cần khóa ổn định `(iss,sub)`, tránh dùng email/tên hiển thị dễ thay đổi hoặc tái sử dụng.

**Authentication thành công không đồng nghĩa Authorization thành công.** Token có authority `SCOPE_orders.read` có thể cho phép gọi endpoint đọc, nhưng vẫn không được đọc đơn hàng thuộc người dùng khác. Kiểm tra quyền tài nguyên (ownership/tenant/ACL) phải được thiết kế riêng.

## 6. Cấu hình Spring Boot API dùng JwtDecoder thật

Ví dụ sau dành cho **Spring Boot 3.x, Spring Security 6.x và Java 17+**. Ứng dụng yêu cầu access token do issuer đáng tin phát hành; placeholder `example.test` chỉ để minh họa và cần thay bằng IdP thật trước khi chạy qua mạng.

### 6.1. Dependencies

Trong dự án Spring Boot Gradle đã có plugin, BOM và JUnit Platform:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

`application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo

app:
  security:
    audience: orders-api
```

Issuer được cấu hình trước, không chọn tùy ý từ `iss` do một token chưa xác thực tự khai báo.

### 6.2. Java code

Tạo `src/main/java/example/JwtResourceApplication.java`:

```java
package example;

import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimNames;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JwtResourceApplication {
    public static void main(String[] args) {
        SpringApplication.run(JwtResourceApplication.class, args);
    }
}

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            JwtAuthenticationConverter converter) throws Exception {
        return http
            .authorizeHttpRequests(requests -> requests
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // Chỉ áp dụng cho API thuần Bearer header, không dựa
            // vào cookie để chứng thực request đổi trạng thái.
            .csrf(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(converter)))
            .build();
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
                String issuer,
            @Value("${app.security.audience}") String audience) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> correctAudience =
            new JwtClaimValidator<List<String>>(
                JwtClaimNames.AUD,
                aud -> aud != null && aud.contains(audience));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, correctAudience));
        return decoder;
    }

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        return new JwtAuthenticationConverter();
    }
}

@RestController
class IdentityController {
    @GetMapping("/api/whoami")
    Map<String, Object> whoami(Authentication auth) {
        // Hợp lệ trong ví dụ chỉ dùng JWT Resource Server.
        JwtAuthenticationToken jwt = (JwtAuthenticationToken) auth;

        List<String> authorities = jwt.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "type", jwt.getClass().getSimpleName(),
            "principalName", jwt.getName(),
            "subject", jwt.getToken().getSubject(),
            "authorities", authorities
        );
    }
}
```

**Lưu ý trước khi chạy:** phải có authorization server với discovery/JWKS truy cập được và access token ký đúng, issuer/audience đúng. Khi app có nhiều phương thức authentication, controller phải kiểm tra kiểu Authentication trước khi cast; ví dụ chỉ minh họa một chain JWT thuần.

Giải thích:

1. DSL `oauth2ResourceServer(...jwt(...))` đăng ký Bearer processing, decoder/provider và cơ chế tích hợp vào filter chain.
2. `NimbusJwtDecoder.withIssuerLocation(issuer)` dùng issuer metadata và khóa phù hợp. `JwtValidators.createDefaultWithIssuer(issuer)` cùng custom audience validator bảo đảm không thay mất phần kiểm tra issuer/time khi gọi `setJwtValidator`.
3. `JwtAuthenticationConverter` mặc định cho `getName()=sub` và `SCOPE_...`. Controller nhận `JwtAuthenticationToken`, không trực tiếp decode token do client gửi.
4. `SessionCreationPolicy.STATELESS` tránh dựa vào `HttpSession` cho authentication của API. Điều này khác login OIDC sử dụng session web; token được kiểm chứng theo request.
5. Ví dụ disable CSRF chỉ phù hợp với API sử dụng Bearer header và không dùng browser cookie làm chứng thực. Nếu dùng chung form/session, tách security chain và giữ CSRF policy tương ứng.

Giả sử một **JWT đã được ký thật** với claims `sub=user-42`, `scope=orders.read orders.write` và `aud=["orders-api"]` thì `GET /api/whoami` có thể trả:

```json
{
  "type": "JwtAuthenticationToken",
  "principalName": "user-42",
  "subject": "user-42",
  "authorities": [
    "SCOPE_orders.read",
    "SCOPE_orders.write"
  ]
}
```

Đây là **response minh họa theo claims**, không phải output đã thử với IdP `example.test`.

### 6.3. Custom role và username claim

Nếu JWT đến từ issuer tin cậy có:

```json
{
  "sub": "user-42",
  "preferred_username": "alice",
  "roles": ["READER", "AUDITOR"]
}
```

Có thể **thay thế** bean converter trong mục 6.2 bằng:

```java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter roles =
        new JwtGrantedAuthoritiesConverter();
    roles.setAuthoritiesClaimName("roles");
    roles.setAuthorityPrefix("ROLE_");

    JwtAuthenticationConverter result =
        new JwtAuthenticationConverter();
    result.setPrincipalClaimName("preferred_username");
    result.setJwtGrantedAuthoritiesConverter(roles);
    return result;
}
```

Import `JwtGrantedAuthoritiesConverter` từ `org.springframework.security.oauth2.server.resource.authentication`. Kết quả sẽ có `getName()="alice"` nhưng `getToken().getSubject()="user-42"`; các authorities là `ROLE_READER` và `ROLE_AUDITOR`.

Tùy chỉnh trên **thay** ánh xạ scope mặc định, do đó `SCOPE_orders.read` sẽ không tự động xuất hiện nếu chỉ dùng converter roles. Để giữ cả scope và role, ghép các converter bằng `DelegatingJwtGrantedAuthoritiesConverter`, và kiểm tra rõ cấu trúc claim.

Converter **không xác minh chữ ký/nguồn tin cậy**. Chỉ ánh xạ claims sau decoder đã xác minh theo policy; không tin `roles` ở token từ issuer/audience không đúng.

## 7. JUnit 5: kiểm tra JwtAuthenticationProvider thật, JwtDecoder giả

Bộ unit test sau cố ý dùng **fake `JwtDecoder`** để kiểm tra chính xác **mối quan hệ provider → converter → Authentication**. Fake decoder không kiểm tra mật mã JWT; test không được dùng để khẳng định chữ ký JWT production hợp lệ.

Tạo `src/test/java/example/JwtProviderUnitTest.java`:

```java
package example;

import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JwtProviderUnitTest {

    private static Jwt exampleJwt() {
        Instant now = Instant.now();
        return Jwt.withTokenValue("example-token")
            .header("alg", "RS256")
            .claim("iss", "https://idp.example.test/realms/demo")
            .claim("sub", "user-42")
            .claim("preferred_username", "alice")
            .claim("scope", "orders.read orders.write")
            .claim("roles", List.of("AUDITOR"))
            .issuedAt(now.minusSeconds(10))
            .expiresAt(now.plusSeconds(600))
            .build();
    }

    @Test
    void providerProducesJwtAuthenticationToken() {
        JwtDecoder fakeDecoder = raw -> {
            assertEquals("example-token", raw);
            return exampleJwt();
        };
        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(fakeDecoder);

        Authentication auth = provider.authenticate(
            new BearerTokenAuthenticationToken("example-token"));

        JwtAuthenticationToken result =
            assertInstanceOf(JwtAuthenticationToken.class, auth);

        assertTrue(result.isAuthenticated());
        assertEquals("user-42", result.getName());
        assertEquals("user-42", result.getToken().getSubject());

        Set<String> names = result.getAuthorities().stream()
            .map(granted -> granted.getAuthority())
            .collect(Collectors.toSet());

        assertEquals(Set.of(
            "SCOPE_orders.read", "SCOPE_orders.write"), names);
    }

    @Test
    void decoderFailureDoesNotAuthenticate() {
        JwtDecoder rejectingDecoder = raw -> {
            throw new BadJwtException("rejected in unit test");
        };
        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(rejectingDecoder);

        assertThrows(AuthenticationException.class, () ->
            provider.authenticate(
                new BearerTokenAuthenticationToken("invalid-token")));
    }

    @Test
    void customNameAndAuthoritiesCanDifferFromSubject() {
        JwtGrantedAuthoritiesConverter roles =
            new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setPrincipalClaimName("preferred_username");
        converter.setJwtGrantedAuthoritiesConverter(roles);

        JwtAuthenticationToken result =
            assertInstanceOf(JwtAuthenticationToken.class,
                converter.convert(exampleJwt()));

        assertEquals("alice", result.getName());
        assertEquals("user-42", result.getToken().getSubject());
        assertTrue(result.getAuthorities().contains(
            new SimpleGrantedAuthority("ROLE_AUDITOR")));
        assertFalse(result.getAuthorities().contains(
            new SimpleGrantedAuthority("SCOPE_orders.read")));
    }

    @Test
    void providerSupportsBearerNotPasswordAuthentication() {
        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(raw -> exampleJwt());

        assertTrue(provider.supports(
            BearerTokenAuthenticationToken.class));
        assertFalse(provider.supports(
            UsernamePasswordAuthenticationToken.class));
    }
}
```

Chạy trong dự án có Gradle wrapper và dependencies ở trên:

```bash
./gradlew test --tests "example.JwtProviderUnitTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.JwtProviderUnitTest"
```

Bốn phương thức test không gọi `System.out.println`, nên **không có stdout nghiệp vụ cố định**; Gradle/JUnit thông báo pass/fail tùy cấu hình. Các chuỗi trong `assertEquals` mới là kỳ vọng kiểm tra. Mã test này độc lập với IdP, nhưng nó **không chạy decoder thật**.

## 8. Kiểm thử JWT thật khác MockMvc jwt() thế nào?

Trong Spring Security Test, `SecurityMockMvcRequestPostProcessors.jwt()` giúp gắn JWT Authentication giả lập cho request. Dùng nó để test controller hoặc authorization là hợp lý; **nó không chứng minh `JwtDecoder` đã xác minh signature, issuer, audience**.

Ví dụ minh họa phương thức đặt trong lớp `@SpringBootTest`/`@AutoConfigureMockMvc` có `MockMvc mvc` và endpoint GET `/api/orders/{id}` tồn tại:

```java
@Test
void scopeReadAllowsGetButNotWrite() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isOk());

    mvc.perform(post("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isForbidden());
}
```

Đây là **snippet**, cần các import `jwt`, `get`, `post`, `status`, `SimpleGrantedAuthority` và các endpoint/handler tương ứng. Nó không phải chương trình chạy độc lập.

Để test decoder thật, có thể tạo JWT **được ký bằng khóa test**, cấu hình `NimbusJwtDecoder` với khóa công khai hoặc JWK Set test, rồi gửi qua HTTP header thực đến Resource Server. Test ít nhất:

| Trường hợp | Kỳ vọng |
| --- | --- |
| JWT có chữ ký/issuer/audience/thời hạn hợp lệ | Decoder chấp nhận; converter tạo Authentication; authorization tiếp tục kiểm tra quyền |
| Chữ ký không khớp khóa tin cậy | Không tạo Authentication thành công; thường 401 |
| `alg` không được phép | Từ chối JWT |
| `iss` sai dù khóa ký hợp lệ | Từ chối JWT |
| `aud` không chứa API dù `iss` đúng | Từ chối JWT, nếu đã cấu hình audience validator |
| Token đã hết `exp` hoặc chưa tới `nbf` | Từ chối JWT |
| Token đúng nhưng thiếu `SCOPE_orders.read` | Authentication thành công, authorization từ chối; thường 403 |
| Token có scope nhưng tài nguyên thuộc người dùng/tenant khác | Từ chối theo business ACL |
| JWK endpoint lỗi/timeout | Fail closed, không cấp quyền chỉ vì không thể kiểm tra chữ ký |
| Token có `scope` thay vì `scp`, hoặc claim roles tùy biến | Converter phải tạo đúng authorities theo policy |

**401 khác 403:** 401 thường báo chưa có hoặc không có credential xác thực hợp lệ; 403 thường là credential đã được chấp nhận nhưng thiếu quyền. Ở môi trường có gateway/entrypoint tùy chỉnh, status cụ thể cần được test, không suy đoán từ exception class.

## 9. Mười lỗi phổ biến khi ghép JwtDecoder và JwtAuthenticationProvider

1. **Tự parse payload rồi đặt `SecurityContextHolder`.** Kẻ tấn công có thể sửa `role` nếu ứng dụng không kiểm tra chữ ký. Dùng decoder thật và validators.
2. **Tin token chỉ vì JWT được ký hợp lệ.** Token có thể dành cho resource khác. Kiểm tra `iss`, `aud`, token type và chính sách client.
3. **Đưa ID token OIDC vào API.** ID token có audience dành cho OIDC client; API cần access token cho resource của mình.
4. **Thay mất các validators.** Gọi `setJwtValidator` với mỗi audience validator có thể vô tình mất issuer/time validation. Kết hợp đúng validator mặc định.
5. **Dùng `roles` mà tưởng role được tự ánh xạ.** Mặc định chuyển `scope`/`scp` thành `SCOPE_`. Cần converter riêng cho `ROLE_`.
6. **Đổi `getName()` thành email và coi email là ID bất biến.** Dùng `(iss,sub)` hoặc ID ổn định theo nghiệp vụ.
7. **Coi Authentication thành công là được phép mọi thao tác.** Cần authorization theo endpoint, scope và ownership từng resource.
8. **Log nguyên token.** Không log `Authorization` header hoặc `Jwt.getTokenValue()` vì đó là credential bearer.
9. **Test chỉ bằng `jwt()` hoặc fake decoder rồi kết luận mật mã an toàn.** Thêm test qua decoder thực với token ký thật và token sai.
10. **Nhầm Servlet với Reactive.** Servlet dùng `JwtAuthenticationProvider`/`JwtDecoder`; WebFlux dùng `JwtReactiveAuthenticationManager`/`ReactiveJwtDecoder`. Cấu hình filter chain khác nhau.

Ngoài ra, truyền Bearer token qua query parameter có nguy cơ lọt vào log, referrer và browser history; ưu tiên `Authorization` header trên HTTPS. Việc API ở chế độ stateless không thay thế các bước kiểm tra JWT hoặc quyền theo resource.

## 10. Checklist hoàn thành

- [ ] Hiểu chuỗi `BearerTokenAuthenticationFilter → BearerTokenAuthenticationToken → JwtAuthenticationProvider → JwtDecoder → JwtAuthenticationConverter → JwtAuthenticationToken`.
- [ ] Decoder dùng khóa/thuật toán đáng tin và có validator `iss`, `exp`, `nbf`, `aud`, token profile tương ứng.
- [ ] Token không hợp lệ bị từ chối trước khi tạo `Authentication` thành công.
- [ ] `getName()`, `getToken().getSubject()`, `getAuthorities()` phản ánh đúng claim và converter đã chọn.
- [ ] Phân quyền bằng scope/authority và kiểm tra dữ liệu theo user/tenant, không chỉ nhìn `isAuthenticated()`.
- [ ] Resource Server không chấp nhận ID token, opaque token hoặc token phát hành cho API khác khi chưa có cơ chế xác minh phù hợp.
- [ ] Test provider/converter bằng fake decoder **và** test xác minh thực với token ký thật cho các trường hợp sai chữ ký/issuer/audience/expiry.
- [ ] Không log credential, không dùng session cũ để bỏ qua bước kiểm chứng token mới.

## 11. Tài liệu chính thống

- Spring Security — Resource Server JWT (Servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — Resource Server tổng quan: https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html
- Spring Security API — `JwtAuthenticationProvider`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationProvider.html
- Spring Security API — `JwtAuthenticationConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html
- Spring Security API — `JwtGrantedAuthoritiesConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html
- Spring Security — OAuth2 Resource Server Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html
- RFC 6750 — Bearer Token Usage: https://datatracker.ietf.org/doc/html/rfc6750
- RFC 9068 — JWT Profile for Access Tokens: https://datatracker.ietf.org/doc/html/rfc9068
