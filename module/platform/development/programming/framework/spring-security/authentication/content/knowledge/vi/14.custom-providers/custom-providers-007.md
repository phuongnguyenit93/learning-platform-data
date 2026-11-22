# Không nhận quyền hoặc trạng thái đã xác thực trực tiếp từ client

> **Chủ đề:** Provider tùy chỉnh — Spring Security Authentication (Servlet). Ví dụ dùng **Java 17+, Spring Boot 3.3.5 và Spring Security 6.x**. Trọng tâm là ranh giới tin cậy khi hiện thực `AuthenticationProvider`: credential do client gửi là **dữ liệu chưa được xác thực**; danh tính đã kiểm chứng, `GrantedAuthority` và `isAuthenticated()` phải xuất phát từ xử lý đáng tin cậy phía server.

## 1. Ranh giới tin cậy: client được gửi bằng chứng, không được tự cấp quyền

HTTP request có thể chứa bất kỳ dữ liệu nào do client kiểm soát: JSON body, query parameter, cookie tùy ý, header, kể cả các trường tên là `role`, `authorities`, `isAuthenticated` hoặc `authenticated`. Kẻ tấn công cũng có thể bỏ qua giao diện frontend và tự viết request bằng `curl`.

Ví dụ một request **không đáng tin**:

```http
GET /api/admin?role=ADMIN&authenticated=true HTTP/1.1
Host: localhost:8080
X-Api-Key: wrong-key
X-Role: ROLE_ADMIN
X-Authenticated: true
```

Hoặc một JSON body có thể được kẻ tấn công tự tạo:

```json
{
  "apiKey": "wrong-key",
  "username": "administrator",
  "authenticated": true,
  "roles": ["ROLE_ADMIN"],
  "authorities": ["accounts:write"]
}
```

Các trường trên **không phải bằng chứng** rằng người gửi là administrator. `authenticated: true` chỉ là boolean do người gửi khai. `ROLE_ADMIN` cũng chỉ là chuỗi do người gửi khai. Nếu code sao chép chúng vào `Authentication` rồi cho Spring Security xử lý, ứng dụng có nguy cơ **leo thang đặc quyền** (privilege escalation).

Ranh giới cần giữ:

- **Client chỉ trình credential hoặc bằng chứng cần xác minh**: password, API key, OAuth2 access token, chữ ký request, mã dùng một lần...
- **Server xác minh bằng chứng**: qua `AuthenticationManager`, `AuthenticationProvider`, `PasswordEncoder`, dịch vụ xác minh chữ ký/token hoặc nguồn dữ liệu tin cậy.
- **Server xác định danh tính và quyền**: lấy user/role từ nguồn đã được xác minh; không nhận danh sách quyền được gửi tùy ý bên cạnh credential.
- **Authentication mechanism đặt kết quả đáng tin vào `SecurityContext`**: kết quả này là token do provider trả về sau xác minh, không phải token nguyên bản tạo từ request.

**Điều cần nhớ:** một username, email, userId hoặc claim chưa được xác minh cũng chỉ là dữ liệu. Nó không trở nên đáng tin chỉ vì tên trường giống một khái niệm nội bộ của Spring Security.

## 2. Hiểu đúng `Authentication` và `isAuthenticated()`

`Authentication` phục vụ hai giai đoạn khác nhau:

| Giai đoạn | `principal` | `credentials` | `authorities` | `isAuthenticated()` |
| --- | --- | --- | --- | --- |
| **Yêu cầu đầu vào**, được tạo từ dữ liệu client | Có thể là username/key id chưa xác minh, hoặc null | Credential thô cần kiểm chứng | Không lấy từ client; thường rỗng | `false` |
| **Kết quả thành công** do manager/provider trả về | Danh tính được xác minh từ server | Nên bỏ/che/xóa credential thô | Quyền được server xác định | `true` |
| **Thất bại** | Không tạo kết quả được tin cậy | Không đưa ra log/response | Không cấp quyền | Ném `AuthenticationException` |

Đối với username/password, đoạn minh họa trong một phương thức xử lý:

```java
Authentication requestToken =
        UsernamePasswordAuthenticationToken.unauthenticated(
                usernameFromRequest,
                rawPasswordFromRequest
        );

Authentication verified = authenticationManager.authenticate(requestToken);
```

Đây là **đoạn mã minh họa**, chưa phải chương trình độc lập. Factory `unauthenticated` tạo yêu cầu chưa được tin. `AuthenticationManager.authenticate(...)` trả một `Authentication` đã được xác minh hoặc ném `AuthenticationException`. Nó **không trả boolean** để code tự quyết định tăng đặc quyền.

**Phản ví dụ nguy hiểm:**

```java
// Sai: danh tính/quyền/trạng thái đều lấy từ client.
Authentication forged = UsernamePasswordAuthenticationToken.authenticated(
        request.username(),
        null,
        request.roles().stream()
                .map(SimpleGrantedAuthority::new)
                .toList()
);
SecurityContextHolder.getContext().setAuthentication(forged);
```

Đoạn này cũng là minh họa lỗi thiết kế; kiểu `request` chỉ biểu diễn dữ liệu do client cung cấp. Với cách này, kẻ tấn công nhập `ROLE_ADMIN` và ứng dụng tự công nhận quyền đó. Tương tự, không được gán thẳng `SecurityContextHolder.getContext().setAuthentication(authenticationFromJson)` hay cho Spring MVC/Jackson deserialize đối tượng `Authentication` tin cậy trực tiếp từ JSON.

### Vì sao `setAuthenticated(true)` đặc biệt nhạy cảm?

Theo hợp đồng `Authentication`, `isAuthenticated()==true` có thể khiến các lớp bảo mật xem token như đã qua xác thực. Đó là **khẳng định về trạng thái tin cậy**. Một `Authentication` tùy chỉnh không được cho phép bất kỳ code xử lý request nào tùy ý gọi `setAuthenticated(true)` với dữ liệu chưa kiểm chứng.

Thiết kế an toàn cho custom token thường có:
1. Factory/constructor tạo **request token** với `isAuthenticated=false`, không có quyền client khai.
2. Factory/constructor tạo **verified token** chỉ được gọi sau khi provider kiểm chứng credential.
3. Override `setAuthenticated(true)` để ném `IllegalArgumentException`, ngăn việc đổi trạng thái trực tiếp.
4. Cho phép `setAuthenticated(false)` theo hợp đồng Spring Security; không cất credential thô trong verified token.
5. Không cung cấp setter cho principal/authorities sau khi đã xác thực.

Đây là lý do nên dùng các factory như `UsernamePasswordAuthenticationToken.unauthenticated(...)` và `authenticated(...)` có kiểm soát, thay vì chuyển nguyên token do client có thể thao túng vào context.

## 3. Vai trò của custom `AuthenticationProvider`

Provider tùy chỉnh dùng khi cơ chế credential của ứng dụng không được hỗ trợ sẵn, ví dụ API key nội bộ, chữ ký request hoặc mã xác thực riêng. Provider phải trả lời: **credential này có hợp lệ, thuộc về danh tính nào và được quyền gì theo chính sách server?**

Luồng mong đợi:

```text
Untrusted HTTP request
  |
  | X-Api-Key: <raw credential>
  | X-Role: ROLE_ADMIN       (bỏ qua)
  | X-Authenticated: true    (bỏ qua)
  v
API-key authentication filter
  |
  |-- Tạo ApiKeyAuthenticationToken.unauthenticated(key)
  v
AuthenticationManager.authenticate(...)
  |
  v
ProviderManager
  |
  |-- Chọn provider mà supports(ApiKeyAuthenticationToken.class) là true
  v
ApiKeyAuthenticationProvider
  |
  |-- Kiểm tra credential với nguồn tin cậy phía server
  |-- Kiểm tra account còn hiệu lực, tenant và chính sách nếu cần
  |-- Xác định username + GrantedAuthority TỪ SERVER
  |-- Sai -> BadCredentialsException
  |-- Đúng -> tạo verified token, credentials=null, authenticated=true
  v
Filter tạo SecurityContext mới và set verified token
  |
  v
AuthorizationFilter
  |-- /api/whoami cần authenticated() -> cho phép
  |-- /api/admin cần ROLE_ADMIN -> 403 nếu server chỉ cấp ROLE_READER
```

Hai phương thức của `AuthenticationProvider`:

```java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;

boolean supports(Class<?> authentication);
```

- `supports` trả `true` khi provider biết xử lý **kiểu** token này. Nó không khẳng định credential đúng.
- `authenticate` phải **kiểm chứng** credential trước khi trả token đã xác thực. Nó có thể trả `null` nếu không thể quyết định và muốn thử provider khác; khi **credential đã được xử lý nhưng sai**, nên ném `AuthenticationException` thích hợp (ví dụ `BadCredentialsException`), không mặc nhiên chấp nhận.
- `ProviderManager` điều phối các provider; tránh một provider quá rộng vô tình chấp nhận token của cơ chế khác.
- Quyền của tài khoản có thể là role, scope, permission hoặc ánh xạ theo tenant; tất cả cần lấy từ dữ liệu server được kiểm tra ở thời điểm thích hợp. Nếu thực sự có delegated authorization, phải xác minh chữ ký, issuer, audience, expiry và phạm vi ủy quyền trước khi sử dụng claim.

## 4. Ví dụ chạy được: custom API-key provider với quyền do server cấp

Để nhìn rõ trust boundary, ví dụ dùng **API key gửi tường minh qua header** `X-Api-Key`. Đây là một cơ chế xác thực stateless: mỗi request phải tự trình key, không dựa vào cookie/session. Demo chỉ chấp nhận key `demo-reader-key-123` và ánh xạ nó phía server thành principal `service-reader` với **duy nhất** `ROLE_READER`.

Một client cố gửi thêm `X-Role: ROLE_ADMIN` hoặc `X-Authenticated: true` sẽ không thay đổi kết quả. Dùng hard-coded key ở đây **chỉ để học**. Trong production cần key có entropy cao, cấp phát và lưu hash/secret qua kho bí mật, rotation/revocation, TLS, rate limit, audit và giám sát lạm dụng.

### 4.1. Cấu trúc dự án

```text
api-key-trust-demo/
├── pom.xml
├── src/main/java/com/example/apikey/ApiKeyTrustDemoApplication.java
└── src/test/java/com/example/apikey/ApiKeyTrustDemoApplicationTests.java
```

**`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>api-key-trust-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/com/example/apikey/ApiKeyTrustDemoApplication.java`**:

```java
package com.example.apikey;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Collection;
import java.util.List;

@SpringBootApplication
public class ApiKeyTrustDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ApiKeyTrustDemoApplication.class, args);
    }

    @Bean
    AuthenticationManager authenticationManager() {
        return new ProviderManager(List.of(new DemoApiKeyProvider()));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager authenticationManager) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/whoami").authenticated()
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .securityContext(context -> context
                .securityContextRepository(new NullSecurityContextRepository())
            )
            .csrf(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint((request, response, exception) ->
                    response.sendError(HttpServletResponse.SC_UNAUTHORIZED)
                )
            )
            // Chỉ đưa filter này vào Spring Security chain, không @Component.
            .addFilterBefore(
                new ApiKeyFilter(authenticationManager),
                UsernamePasswordAuthenticationFilter.class
            );

        return http.build();
    }

    // Token đầu vào và token đã xác thực có các constructor tách biệt.
    static final class ApiKeyAuthenticationToken extends AbstractAuthenticationToken {
        private final Object principal;
        private String apiKey;

        private ApiKeyAuthenticationToken(String rawKey) {
            super(List.of());
            this.principal = null;
            this.apiKey = rawKey;
            super.setAuthenticated(false);
        }

        private ApiKeyAuthenticationToken(
                String verifiedPrincipal,
                Collection<? extends GrantedAuthority> authorities) {
            super(authorities);
            this.principal = verifiedPrincipal;
            this.apiKey = null;
            // Chỉ constructor này được phép gắn trạng thái trusted.
            super.setAuthenticated(true);
        }

        static ApiKeyAuthenticationToken unauthenticated(String rawKey) {
            return new ApiKeyAuthenticationToken(rawKey);
        }

        static ApiKeyAuthenticationToken verified(
                String serverPrincipal,
                Collection<? extends GrantedAuthority> serverAuthorities) {
            return new ApiKeyAuthenticationToken(serverPrincipal, serverAuthorities);
        }

        @Override
        public Object getPrincipal() {
            return principal;
        }

        @Override
        public Object getCredentials() {
            return apiKey;
        }

        @Override
        public void eraseCredentials() {
            super.eraseCredentials();
            apiKey = null;
        }

        @Override
        public void setAuthenticated(boolean value) {
            if (value) {
                throw new IllegalArgumentException(
                        "Không thể tin token bằng setAuthenticated(true)"
                );
            }
            super.setAuthenticated(false);
        }
    }

    static final class DemoApiKeyProvider implements AuthenticationProvider {
        private static final byte[] EXPECTED_HASH = sha256("demo-reader-key-123");

        @Override
        public Authentication authenticate(Authentication authentication) {
            String presented = (String) authentication.getCredentials();
            if (presented == null || presented.isBlank()
                    || !MessageDigest.isEqual(sha256(presented), EXPECTED_HASH)) {
                throw new BadCredentialsException("Invalid API key");
            }

            // QUAN TRỌNG: username + authority đến từ phía server.
            return ApiKeyAuthenticationToken.verified(
                    "service-reader",
                    List.of(new SimpleGrantedAuthority("ROLE_READER"))
            );
        }

        @Override
        public boolean supports(Class<?> authentication) {
            return ApiKeyAuthenticationToken.class.isAssignableFrom(authentication);
        }

        private static byte[] sha256(String value) {
            try {
                return MessageDigest.getInstance("SHA-256")
                        .digest(value.getBytes(StandardCharsets.UTF_8));
            } catch (NoSuchAlgorithmException ex) {
                throw new IllegalStateException("SHA-256 unavailable", ex);
            }
        }
    }

    static final class ApiKeyFilter extends OncePerRequestFilter {
        private final AuthenticationManager authenticationManager;

        ApiKeyFilter(AuthenticationManager authenticationManager) {
            this.authenticationManager = authenticationManager;
        }

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain) throws ServletException, IOException {

            String rawKey = request.getHeader("X-Api-Key");
            if (rawKey == null || rawKey.isBlank()) {
                chain.doFilter(request, response);
                return;
            }

            try {
                Authentication pending =
                        ApiKeyAuthenticationToken.unauthenticated(rawKey);
                Authentication verified =
                        authenticationManager.authenticate(pending);

                SecurityContext context = SecurityContextHolder.createEmptyContext();
                context.setAuthentication(verified);
                SecurityContextHolder.setContext(context);
                chain.doFilter(request, response);
            } catch (org.springframework.security.core.AuthenticationException ex) {
                SecurityContextHolder.clearContext();
                response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            }
        }
    }

    @RestController
    static class DemoController {
        record IdentityResponse(
                String username,
                boolean authenticated,
                List<String> authorities
        ) {}

        @GetMapping("/public")
        String publicPage() {
            return "public";
        }

        @GetMapping("/api/whoami")
        IdentityResponse whoAmI(Authentication authentication) {
            List<String> authorities = authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList();
            return new IdentityResponse(
                    authentication.getName(),
                    authentication.isAuthenticated(),
                    authorities
            );
        }

        @GetMapping("/api/admin")
        String adminOnly() {
            return "admin-only";
        }
    }
}
```

### 4.2. Vì sao thiết kế này không tin quyền từ client?

**Một:** `ApiKeyFilter` chỉ đọc `X-Api-Key`. Nó không đọc `X-Role`, `X-Authenticated`, `role` hoặc `authenticated` từ query. Những trường do client tự khai không thể trở thành `GrantedAuthority`.

**Hai:** Filter tạo `ApiKeyAuthenticationToken.unauthenticated(rawKey)`, trong đó `isAuthenticated=false`, principal = `null` và authorities rỗng. Nó chuyển token qua `AuthenticationManager.authenticate(...)`; không gọi `setAuthenticated(true)`.

**Ba:** `DemoApiKeyProvider` so hash của key do client trình với hash tin cậy được server cấu hình. Chỉ khi key đúng, provider mới tạo verified token với principal `service-reader` và **ROLE_READER từ server**, không nhận role từ request. Ví dụ dùng hash SHA-256 cho key demo có entropy thấp nên **không phải thiết kế kho API key production**: ngoài thực tế phải phát hành key ngẫu nhiên dài, có key ID, kho hash/HMAC phù hợp, rotation và revocation.

**Bốn:** `ApiKeyAuthenticationToken#setAuthenticated(true)` bị chặn. Constructor verified có thể gọi `super.setAuthenticated(true)` sau xác minh; chính class token chỉ có đường tạo request chưa xác thực ở filter. Nếu một developer khác cố nâng trạng thái trên request token bằng setter, code ném exception.

**Năm:** `getAuthorities()` của verified token là collection do constructor nhận từ server và `AbstractAuthenticationToken` bảo quản theo hợp đồng. Đừng cung cấp setter mutable cho authorities hoặc trả về collection có thể bị sửa sau xác thực.

**Sáu:** Filter chỉ gắn **kết quả `verified`** vào `SecurityContextHolder`. Nó không chép `pending` hoặc header request thành authenticated token. `AuthorizationFilter` xem `ROLE_READER` và từ chối `/api/admin` vì endpoint yêu cầu `ROLE_ADMIN`.

**Bảy:** Ví dụ stateless: `NullSecurityContextRepository` và `SessionCreationPolicy.STATELESS` có nghĩa context không được dùng để thiết lập login lâu dài. Mỗi request phải mang credential hợp lệ. CSRF được tắt **trong phạm vi demo header-only không sử dụng cookie tự động gửi**; không áp dụng vô điều kiện cho web login dùng session/cookie.

**Tám:** Filter được tạo trực tiếp trong `addFilterBefore` thay vì khai báo là servlet `@Component`/`@Bean Filter`, tránh trường hợp Spring Boot tự đăng ký một filter ngoài `SecurityFilterChain` rồi lại đăng ký lần nữa trong chain.

### 4.3. Chạy và thử bằng curl

Từ thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Ở terminal khác:

```bash
# Public endpoint không cần credential.
curl -i http://localhost:8080/public

# Không có key -> 401 ở endpoint protected.
curl -i http://localhost:8080/api/whoami

# Key sai, dù tự xưng là admin -> 401.
curl -i \
    -H 'X-Api-Key: wrong-key' \
    -H 'X-Role: ROLE_ADMIN' \
    -H 'X-Authenticated: true' \
    'http://localhost:8080/api/admin?role=ADMIN&authenticated=true'

# Key đúng -> 200, chỉ nhận quyền ROLE_READER từ server.
curl -i \
    -H 'X-Api-Key: demo-reader-key-123' \
    -H 'X-Role: ROLE_ADMIN' \
    -H 'X-Authenticated: true' \
    http://localhost:8080/api/whoami

# Cùng key đúng nhưng không có ROLE_ADMIN -> 403.
curl -i \
    -H 'X-Api-Key: demo-reader-key-123' \
    -H 'X-Role: ROLE_ADMIN' \
    'http://localhost:8080/api/admin?role=ADMIN'
```

Kết quả dự kiến theo thứ tự: **200**, **401**, **401**, **200**, **403**. Body của `GET /public` là chuỗi `public`. Body JSON của `/api/whoami` thể hiện danh tính server cấp; minh họa:

```json
{
  "username": "service-reader",
  "authenticated": true,
  "authorities": ["ROLE_READER"]
}
```

Thứ tự field/headers và body lỗi có thể khác tùy cấu hình Spring Boot/Servlet container; ví dụ JSON ở trên mô tả giá trị, không đòi thứ tự byte tuyệt đối. Dòng `authenticated: true` trong **response** là trạng thái do server xác minh, khác hoàn toàn một boolean do client tự gửi.

## 5. Test chống giả mạo role và trạng thái authenticated

Tạo **`src/test/java/com/example/apikey/ApiKeyTrustDemoApplicationTests.java`**:

```java
package com.example.apikey;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiKeyTrustDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void validKeyProducesOnlyServerAssignedIdentityAndRole() throws Exception {
        mvc.perform(get("/api/whoami")
                    .header("X-Api-Key", "demo-reader-key-123")
                    .header("X-Role", "ROLE_ADMIN")
                    .header("X-Authenticated", "true")
                    .param("role", "ADMIN")
                    .param("authenticated", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("service-reader"))
                .andExpect(jsonPath("$.authenticated").value(true))
                .andExpect(jsonPath("$.authorities[0]").value("ROLE_READER"));
    }

    @Test
    void forgedRoleDoesNotBypassAuthorization() throws Exception {
        mvc.perform(get("/api/admin")
                    .header("X-Api-Key", "demo-reader-key-123")
                    .header("X-Role", "ROLE_ADMIN")
                    .header("X-Authenticated", "true")
                    .param("role", "ADMIN"))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidOrMissingKeyCannotBeAuthenticatedByHeaders() throws Exception {
        mvc.perform(get("/api/whoami")
                    .header("X-Api-Key", "wrong-key")
                    .header("X-Role", "ROLE_ADMIN")
                    .header("X-Authenticated", "true"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/whoami")
                    .header("X-Authenticated", "true"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void inputTokenCannotBePromotedBySetter() {
        var token = ApiKeyTrustDemoApplication.ApiKeyAuthenticationToken
                .unauthenticated("wrong-key");

        assertFalse(token.isAuthenticated());
        assertThrows(IllegalArgumentException.class,
                () -> token.setAuthenticated(true));
        assertFalse(token.isAuthenticated());
    }
}
```

Chạy:

```bash
mvn test
```

Các test kiểm chứng bằng behavior:
1. Credential đúng nhưng header/query tự nhận admin không thay đổi principal/authority phía server.
2. Credential đúng nhưng **không đủ role** trả 403.
3. Credential sai hoặc vắng mặt không thể biến thành login bằng `X-Authenticated: true`, trả 401.
4. Một request token chưa xác thực không thể chuyển thành trusted token bằng `setAuthenticated(true)`.
5. Public endpoint vẫn hoạt động, kiểm tra ứng dụng chạy được qua filter chain.

`MockMvc` chạy Spring Security filter chain và controller trong test, không cần mở cổng HTTP thật.

## 6. Những bẫy khác trong custom provider

### 6.1. Quyền phải được xác định dựa trên bằng chứng đáng tin

Một user có thể gửi `userId=42` hoặc `tenant=acme`, nhưng provider phải chứng minh key/token thuộc đúng user và tenant trước khi truy vấn quyền. **Không dùng `request.userId` hay `request.tenantId` làm kết quả xác thực** nếu chúng chỉ là chuỗi client tự nhập. Với multi-tenant, danh tính và role thường được định danh bằng cặp account/tenant và chính sách server; chỉ tin vào một tenant selector sau khi kiểm tra quan hệ ràng buộc với credential.

Nếu external identity provider gửi JWT, phải xác minh chữ ký, thuật toán được phép, issuer, audience, thời gian `exp`/`nbf` và ngữ cảnh token trước khi dùng `scope`/`roles`. Chỉ Base64-decode JWT rồi đọc JSON claims là **không xác thực**.

### 6.2. Không tự tạo authenticated token trước khi provider kiểm tra

**Sai:**

```java
// Sai: client gửi authorities, code lập tức coi là trusted.
Authentication authentication =
        UsernamePasswordAuthenticationToken.authenticated(
                input.username(), null,
                input.roles().stream().map(SimpleGrantedAuthority::new).toList()
        );
SecurityContextHolder.getContext().setAuthentication(authentication);
```

**Đúng về mặt trách nhiệm:**

```java
// Chỉ minh họa luồng, các biến thuộc code thực tế bên ngoài.
Authentication pending = ApiKeyAuthenticationToken.unauthenticated(rawKey);
Authentication verified = authenticationManager.authenticate(pending);
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
```

Hai đoạn này là minh họa, không phải tệp Java độc lập. Mã thực tế đầy đủ nằm ở mục 4; `verified` chỉ được provider tạo **sau khi** kiểm tra credential và gán quyền từ server.

### 6.3. Phân biệt 401 và 403

| Tình huống | Thành phần quyết định | Kết quả thường gặp |
| --- | --- | --- |
| Không có credential, URL yêu cầu xác thực | Authorization + authentication entry point | **401 Unauthorized** |
| Credential sai, provider ném `BadCredentialsException` | Authentication filter/entry point | **401 Unauthorized** |
| Credential đúng, user chỉ có `ROLE_READER` nhưng URL yêu cầu `ROLE_ADMIN` | `AuthorizationFilter`/`AccessDeniedHandler` | **403 Forbidden** |
| Header `X-Role` giả mạo role admin | Không có hiệu lực | Theo credential/role **server** xác minh |
| Boolean `authenticated=true` trong JSON/query/header | Không có hiệu lực | Theo credential **server** xác minh |

`401` không có nghĩa là thiếu role; `403` không đồng nghĩa password/API key sai. Phản hồi có thể thay đổi nếu ứng dụng cấu hình entry point/handler khác, nhưng phân biệt xác thực và phân quyền vẫn rất quan trọng.

### 6.4. Không lưu credential thô và không lộ dữ liệu nhạy cảm

- API key/password là secret. Không ghi raw key vào log, exception, `toString`, response body hoặc metrics tag.
- Verified token trong ví dụ có `getCredentials()==null`; provider giữ key thô chỉ trong thời gian cần kiểm tra.
- Với các credential có vòng đời dài, nên dùng key có entropy mạnh, lưu bản hash/HMAC phù hợp, gắn owner/scope/expiry/revocation và so sánh an toàn; demo fixed key không đủ.
- Dùng HTTPS/TLS, kiểm soát access log/trace, cấu hình secret rotation và giới hạn số lần thử.
- Đừng lưu `Authentication` client gửi dưới dạng JSON vào session/cache. Chỉ có server mới tạo kết quả trusted.

### 6.5. Không dùng chỉ `isAuthenticated()` để kết luận quyền

`Authentication.isAuthenticated()` trả trạng thái xác thực, **không nói user có quyền admin**. `authorizeHttpRequests(...hasRole("ADMIN"))` kiểm tra authority từ verified token. Khi custom provider tự đặt `ROLE_ADMIN` cho tất cả token đúng, lỗi nằm ở ánh xạ quyền **server**, dù client không gửi role. Vì vậy còn phải kiểm toán mapping identity → permissions.

Trong các cơ chế sử dụng `AnonymousAuthenticationToken`, thuộc tính `isAuthenticated()` có thể là true trong ngữ cảnh nhất định. Để nhận biết đã đăng nhập, nên dùng biểu thức `authenticated()` và cách giải thích của `AuthenticationTrustResolver` thay vì tự viết `if (authentication.isAuthenticated())` như một tiêu chí phân quyền duy nhất.

### 6.6. Provider hỗ trợ đúng loại token

`supports(ApiKeyAuthenticationToken.class)` phải trả true, nhưng không nên hỗ trợ tất cả token của hệ thống. Nếu nhiều provider được đăng ký cùng một manager, một provider cần trả đúng loại token đã hỗ trợ; nếu credential sai, ném exception phù hợp. `ProviderManager` có thể chuyển sang provider tiếp theo tùy loại exception/cấu hình, vì thế thiết kế thứ tự provider và fallback không được vô tình cho phép cơ chế yếu hơn nâng quyền.

### 6.7. Vì sao demo không dùng session?

Để dễ quan sát, API key gửi ở mỗi request: filter verify lại rồi set context chỉ cho request hiện tại; `SecurityContextHolderFilter` thu dọn context sau request. `NullSecurityContextRepository` không giữ context giữa request. Nếu chuyển sang session login, phải chọn repository phù hợp, lưu context sau thành công bằng `saveContext(...)`, xử lý session fixation và CSRF. Nếu dùng JWT Resource Server, ưu tiên cơ chế sẵn có để verify chữ ký/claims, không viết lại một provider chỉ đọc JSON claim do client khai.

## 7. Checklist khi review code custom authentication

- [ ] DTO đầu vào chỉ chứa credential/evidence cần thiết, không nhận `authenticated`/`authorities` làm quyền được tin.
- [ ] Mọi token tạo từ request bắt đầu `isAuthenticated=false`, authority rỗng.
- [ ] Manager/provider kiểm chứng credential bằng nguồn tin cậy hoặc chữ ký hợp lệ trước khi tạo verified token.
- [ ] `principal` và `GrantedAuthority` của kết quả được server xác định theo identity/tenant/policy đã kiểm tra.
- [ ] Token custom chống `setAuthenticated(true)` tùy tiện và không lộ setter mutable cho quyền.
- [ ] Verified token không giữ raw credential; không lộ credential trong response/log.
- [ ] Filter đưa **kết quả** manager trả về vào `SecurityContext`, xử lý exception và xóa context khi thất bại.
- [ ] `supports` chỉ chấp nhận đúng kiểu token; không có fallback yếu vô tình nâng quyền.
- [ ] Test có request giả mạo `ROLE_ADMIN`, `authenticated=true`, credential sai, credential vắng và quyền không đủ.
- [ ] Bảo vệ TLS, secret rotation, tenant isolation, rate limit và auditing theo mức độ rủi ro.

## 8. Tự kiểm tra kiến thức

1. Vì sao `"ROLE_ADMIN"` trong JSON/header không được chuyển trực tiếp thành `SimpleGrantedAuthority`?
2. Khi client gửi `authenticated=true` nhưng key sai, trạng thái của `ApiKeyAuthenticationToken.unauthenticated` là gì?
3. Component nào xác minh key và component nào cấp `ROLE_READER` trong demo?
4. Vì sao cùng một valid key gọi `/api/whoami` trả 200 nhưng `/api/admin` trả 403?
5. Trong constructor verified token, vì sao chỉ dùng `super.setAuthenticated(true)` sau khi credential đã được provider kiểm chứng?
6. Nếu một JWT không được xác minh chữ ký, vì sao không được dùng `roles` trong payload cho phân quyền?
7. Vì sao `isAuthenticated()` riêng lẻ không thay thế `hasRole(...)` và `AuthenticationTrustResolver`?
8. Khi thay demo bằng API key production, cần thêm những biện pháp gì về secret, expiry và quyền theo tenant?

**Đáp án trọng tâm:** (1) client có thể tự khai; (2) false, manager/provider phải kiểm tra; (3) `DemoApiKeyProvider`, dựa trên dữ liệu server; (4) server chỉ cấp `ROLE_READER`; (5) true là tín hiệu đã xác thực; (6) payload chưa đáng tin; (7) xác thực khác phân quyền và anonymous có quy tắc riêng; (8) key ngẫu nhiên mạnh, kho hash/secret, expiry, rotation/revocation, quyền server, TLS và kiểm tra tenant.

## 9. Tài liệu chính thức

- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security — `Authentication` interface API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/Authentication.html
- Spring Security — `AuthenticationProvider` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html
- Spring Security — `AbstractAuthenticationToken` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AbstractAuthenticationToken.html
- Spring Security — Authorization: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — SecurityContext persistence: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html
