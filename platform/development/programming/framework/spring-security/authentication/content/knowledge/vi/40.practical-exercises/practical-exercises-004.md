# Xây endpoint đăng nhập JSON dùng phiên và lưu SecurityContext đúng cách

## 1. Mục tiêu của bài thực hành tổng hợp

Ứng dụng Spring Boot có thể dùng trang đăng nhập HTML truyền thống, nhưng một frontend SPA hoặc client dùng `fetch` thường muốn gửi JSON:

```http
POST /api/auth/login HTTP/1.1
Content-Type: application/json
X-CSRF-TOKEN: <token-issued-for-this-session>
Cookie: JSESSIONID=<session-id>

{"username":"learner","password":"correct-password"}
```

Nếu username/password đúng, backend trả JSON và duy trì phiên. Một request tiếp theo, ví dụ `GET /api/auth/me`, phải nhận được cùng principal mà không yêu cầu gửi lại password.

**Điểm mấu chốt của Spring Security 6.x:** khi tự xác thực trong **Spring MVC controller hoặc custom filter**, chỉ gọi `AuthenticationManager.authenticate(...)` rồi `SecurityContextHolder.setContext(...)` **chưa đủ để đăng nhập qua nhiều request**. Phải gọi `SecurityContextRepository.saveContext(context, request, response)` nếu muốn context được khôi phục từ phiên HTTP sau đó.

Bài thực hành thuộc nhóm **Thực hành tổng hợp** trong module **Spring Security - authentication**. Bạn sẽ có thể:

1. Xây đúng contract JSON cho `POST /api/auth/login`, `GET /api/auth/me`, `GET /csrf` và `POST /api/auth/logout`.
2. Tự cấu hình `AuthenticationManager`/`DaoAuthenticationProvider` và `PasswordEncoder`, không giả định JSON được `UsernamePasswordAuthenticationFilter` mặc định đọc.
3. Phân biệt Authentication token **chưa xác thực** và Authentication **đã được provider kiểm chứng**.
4. Tạo `SecurityContext` mới, đặt vào `SecurityContextHolder`, **save explicit** với `HttpSessionSecurityContextRepository`.
5. Gọi `SessionAuthenticationStrategy` để bảo vệ **session fixation**, và xóa CSRF token cũ sau login.
6. Giữ CSRF cho JSON login/logout chạy bằng session cookie; lấy token trước login và lấy token mới sau login.
7. Dùng Spring Security `LogoutFilter` để vô hiệu session/clear context/clear CSRF rồi trả JSON.
8. Kiểm thử multi-request stateful flow bằng MockMvc và một cookie jar: anonymous, token thiếu, credential sai, login đúng, session được giữ, quyền sai, logout.
9. Phân biệt failure status `400/401/403`, session expiration, CORS và các tình huống reverse proxy.
10. Nêu rõ các phần demo chưa đủ production: rate limiting, user store, multi-node sessions, audit, TLS, validation và secrets.

Phạm vi là **Servlet/MVC, Java 17+, Spring Boot 3.5.16 và Spring Security 6.5.x**. Spring Boot 4/Spring Security 7 và WebFlux có một số API/configuration khác, phải đối chiếu docs của chính phiên bản triển khai.

## 2. Vì sao không thể chỉ return JSON sau authenticate?

Giả sử code chưa đúng:

```java
@PostMapping("/api/auth/login")
public Map<String, Object> login(@RequestBody LoginRequest body) {
    Authentication accepted = manager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            body.username(), body.password()));

    SecurityContextHolder.getContext().setAuthentication(accepted);

    return Map.of("authenticated", true);
}
```

Request đầu có thể trả `200 {"authenticated":true}`. Nhưng khi browser gửi `GET /api/auth/me` ở **request khác**, Spring Security đọc repository để lấy SecurityContext. Nếu chưa lưu:

```text
Request 1 POST /api/auth/login
  -> manager.authenticate(...) thành công
  -> SecurityContextHolder đã có principal
  -> controller trả 200
  -> KHÔNG gọi repository.saveContext(...)
  -> request kết thúc, context thread-local bị clear

Request 2 GET /api/auth/me
  -> SecurityContextHolderFilter lấy context từ repository
  -> repository không có authentication đã lưu
  -> anonymous / 401
```

Tài liệu Spring Security 6.5 nói rõ custom controller/filter cần `SecurityContextRepository` để lưu context giữa requests. Đừng “sửa” bằng cách để một `static Authentication` trong JVM, disable security filter hoặc tự đặt cookie `JSESSIONID` ngẫu nhiên.

**Đúng:** sau khi authentication thành công, tạo mới `SecurityContext`, đặt Authentication đã được xác minh, đặt context trên holder và lưu bằng **cùng repository** được cấu hình cho Spring Security chain.

## 3. Phân biệt năm thành phần chủ đạo

| Thành phần | Vai trò | Không làm thay cho |
| --- | --- | --- |
| `UsernamePasswordAuthenticationToken.unauthenticated(...)` | Gói username/password thành một yêu cầu xác thực | Không chứng minh mật khẩu đúng |
| `AuthenticationManager.authenticate(...)` | Chuyển yêu cầu sang provider, trả Authentication hợp lệ hoặc ném AuthenticationException | Không tự định nghĩa response JSON |
| `SecurityContextHolder` | Giữ Authentication cho request/thread hiện tại | Không mặc nhiên lưu qua các request |
| `SecurityContextRepository` | Đọc/lưu SecurityContext giữa request, có thể qua session | Không xác thực password |
| `SessionAuthenticationStrategy` | Xử lý các bước liên quan một login mới: session fixation, CSRF invalidation, session concurrency nếu cấu hình | Không thay AuthorizationManager |

Ở tầng HTTP còn các thành phần:

- `SecurityFilterChain`: thực thi security filters, CSRF và authorization.
- `SecurityContextHolderFilter`: trong Spring Security 6, thường **đọc** repository và khôi phục SecurityContext. Với custom authentication, bạn phải save.
- `HttpSessionSecurityContextRepository`: lưu/đọc context trong HttpSession, thường dưới `SPRING_SECURITY_CONTEXT`.
- `CsrfFilter` và `CsrfTokenRepository`: kiểm tra unsafe methods như POST và lưu CSRF token.
- `LogoutFilter` / `SecurityContextLogoutHandler` / `CsrfLogoutHandler`: cleanup session, context và token khi logout.
- `AuthenticationEntryPoint`: phản hồi khi chưa authenticated mà cố truy cập tài nguyên bảo vệ.
- `AccessDeniedHandler`: phản hồi khi user đã xác thực nhưng không đủ quyền, thường 403.

**Một JSON login endpoint đúng không được tự giả lập toàn bộ SecurityFilterChain.** Chỉ viết logic xác thực và lưu kết quả ở controller; để Spring filters xử lý các lớp bảo vệ phù hợp.

## 4. Luồng request hoàn chỉnh với session cookie

```text
Browser                         Spring Security + MVC
   |                                      |
   | GET /csrf                            |
   |------------------------------------->|
   |                CsrfFilter exposes token;
   |                HttpSessionCsrfTokenRepository
   |                stores token with session
   |<------------- CSRF token + JSESSIONID --|
   |                                      |
   | POST /api/auth/login                 |
   | Cookie: JSESSIONID                  |
   | X-CSRF-TOKEN: <valid>                |
   | JSON username/password              |
   |------------------------------------->|
   |             CsrfFilter checks token |
   |             Controller parse JSON   |
   |             AuthenticationManager   |
   |             -> DaoAuthenticationProvider
   |             -> PasswordEncoder      |
   |             SessionAuthenticationStrategy:
   |               change session ID      |
   |               clear old CSRF token   |
   |             SecurityContext.createEmpty
   |             setAuthentication       |
   |             SecurityContextHolder.set
   |             repository.saveContext  |
   |<--------- 200 JSON + session cookie-|
   |                                      |
   | GET /api/auth/me                    |
   | Cookie: JSESSIONID (new)            |
   |------------------------------------->|
   |             SecurityContextHolderFilter
   |             repository loads context|
   |             AuthorizationFilter     |
   |<------------- 200 {"username":...}--|
   |                                      |
   | GET /csrf (new CSRF token)          |
   |<------------- new token ------------|
   |                                      |
   | POST /api/auth/logout + new CSRF    |
   |------------------------------------->|
   |             LogoutFilter clears session,
   |             SecurityContext + CSRF   |
   |<------------- 200 JSON -------------|
   |                                      |
   | GET /api/auth/me                    |
   |<------------- 401 ------------------|
```

Trong **cùng-origin demo** bên dưới, browser mặc định gửi cookie cho cùng origin; khi dùng `fetch` hãy chỉ định `credentials: "same-origin"` để hợp đồng rõ ràng. Với frontend khác origin, cần cấu hình `credentials: "include"`, CORS allowlist có credentials, TLS và cookie SameSite/third-party policies đúng; CORS **không thay xác thực hoặc CSRF**.

## 5. Thiết kế API contract và mã phản hồi

| Request | Trạng thái | Response mẫu | Điều kiện |
| --- | --- | --- | --- |
| `GET /csrf` | 200 | JSON `token/headerName/parameterName` | Có thể anonymous, tạo/lấy session CSRF |
| `POST /api/auth/login` | 200 | `{"username":"learner","authenticated":true}` | JSON hợp lệ, CSRF hợp lệ, password đúng |
| `POST /api/auth/login` | 400 | `{"code":"invalid_request",...}` | Username/password blank (controller validation) hoặc malformed JSON |
| `POST /api/auth/login` | 401 | `{"code":"invalid_credentials",...}` | Provider từ chối credentials; response cố ý chung |
| `POST /api/auth/login` | 403 | Response của CSRF filter | Thiếu/sai CSRF token, **chưa vào controller** |
| `GET /api/auth/me` | 200 | JSON user | Session chứa SecurityContext hợp lệ |
| `GET /api/auth/me` | 401 | Có thể body trống trong demo | Chưa login hoặc session đã hết hạn |
| `GET /api/admin` | 403 | Response access denied | User có `ROLE_USER` nhưng thiếu `ROLE_ADMIN` |
| `POST /api/auth/logout` | 200 | `{"status":"logged_out"}` | CSRF token hợp lệ, logout filter cleanup |
| `POST /api/auth/logout` | 403 | CSRF rejection | Thiếu/sai CSRF token |

HTTP status không phải chứng minh duy nhất. Login failure thuộc controller/authentication manager; CSRF 403 xảy ra **trước controller**; protected GET 401 do entry point; quyền không đủ 403 do authorization. Với `formLogin` mặc định, nhiều trường hợp sẽ redirect tới HTML login thay vì JSON: vì vậy demo **tắt formLogin và httpBasic** để hợp đồng API rõ ràng.

**Không trả password, raw `AuthenticationException.getMessage()`, session ID hoặc CSRF token trong response login thành công.** CSRF token được cung cấp qua endpoint riêng có `Cache-Control: no-store`.

## 6. Cấu trúc project có thể chạy

```text
json-session-login-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/jsonlogin/JsonSessionLoginApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/demo/jsonlogin/JsonSessionLoginApplicationTests.java
```

Đây là một project Servlet/MVC đầy đủ để thực hành. Không có database hay IdP production; dùng user memory với **password giả do environment cấp**. Vì authentication được xây bằng Spring Security provider thật, mã kiểm tra được đường lưu context qua session.

### 6.1. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>json-session-login-demo</artifactId>
    <version>1.0.0</version>

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
            <groupId>org.springframework.security</groupId>
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

**Dependency note:** `spring-boot-starter-security` cung cấp `spring-security-web`, `spring-security-config` và password/provider APIs; không cần dependency riêng cho `SecurityContextRepository`. `spring-security-test` cung cấp test request post-processors, còn `starter-test` cung cấp JUnit/MockMvc/JSON testing.

### 6.2. application.yml

```yaml
server:
  port: 8080
  servlet:
    session:
      timeout: 20m
      cookie:
        http-only: true
        same-site: lax

app:
  demo:
    login-password: "${DEMO_LOGIN_PASSWORD}"
```

Không có default password hard-coded. `SameSite=Lax` chỉ là lớp giảm rủi ro cookie, **không thay CSRF token**. Với deployment HTTPS production, session cookie cần `Secure`, proxy forwarded-header trust phù hợp và HSTS; demo localhost HTTP không bật Secure bắt buộc để trình duyệt lab vẫn hoạt động.

**Quan trọng:** nếu chạy frontend trên origin khác (nhất là khác site), SameSite/third-party cookie rules có thể khiến session không được gửi. Bài lấy **same-origin** làm baseline để cô lập bài toán SecurityContext persistence, rồi hướng dẫn mở rộng đúng trong phần riêng.

## 7. Mã Java chính: SecurityFilterChain + AuthenticationManager + repository

Tạo **một file** `src/main/java/demo/jsonlogin/JsonSessionLoginApplication.java`:

```java
package demo.jsonlogin;

import java.nio.charset.StandardCharsets;
import java.util.List;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JsonSessionLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonSessionLoginApplication.class, args);
    }
}

@Configuration
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${app.demo.login-password}") String password) {

        // Secret giả dành cho local lab, không dùng production.
        if (password == null || password.length() < 20) {
            throw new IllegalStateException(
                "DEMO_LOGIN_PASSWORD must be set and sufficiently long");
        }

        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode(password))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder) {

        // Provider thực sự kiểm tra password qua PasswordEncoder.
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        // Controller bên dưới dùng chính manager này.
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        // Đọc và ghi context trong HttpSession.
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        // Token kỳ vọng nằm trong session; X-CSRF-TOKEN gửi từ client.
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SessionAuthenticationStrategy loginSessionStrategy(
            CsrfTokenRepository csrfRepository) {

        // Trong Spring Security 6, MVC login tự viết phải gọi
        // session strategy trực tiếp; SessionManagementFilter
        // không mặc định tự phát hiện một login mới.
        return new CompositeSessionAuthenticationStrategy(List.of(
            new ChangeSessionIdAuthenticationStrategy(),
            new CsrfAuthenticationStrategy(csrfRepository)
        ));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository contextRepository,
            CsrfTokenRepository csrfRepository) throws Exception {

        return http
            .securityContext(context -> context
                .securityContextRepository(contextRepository))

            // Đây là API dùng session; không cấu hình STATELESS.
            .sessionManagement(session -> session
                .sessionCreationPolicy(
                    SessionCreationPolicy.IF_REQUIRED))

            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/", "/csrf").permitAll()
                .requestMatchers(HttpMethod.POST,
                    "/api/auth/login").permitAll()
                .requestMatchers(HttpMethod.GET,
                    "/api/auth/me").authenticated()
                .requestMatchers(HttpMethod.GET,
                    "/api/admin").hasRole("ADMIN")
                .anyRequest().denyAll())

            // POST login và POST logout vẫn phải có CSRF token.
            .csrf(csrf -> csrf
                .csrfTokenRepository(csrfRepository))

            // Không dùng form processing filter / HTML redirect
            // vì controller xử lý JSON POST /api/auth/login.
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)

            // Protected GET anonymous -> 401 (không redirect).
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))

            // Dùng LogoutFilter chuẩn để cleanup context/session/CSRF.
            .logout(logout -> logout
                .logoutUrl("/api/auth/logout")
                .logoutSuccessHandler((request, response, auth) -> {
                    response.setStatus(HttpServletResponse.SC_OK);
                    response.setContentType(
                        MediaType.APPLICATION_JSON_VALUE);
                    response.setCharacterEncoding(
                        StandardCharsets.UTF_8.name());
                    response.setHeader("Cache-Control", "no-store");
                    response.getWriter().write(
                        "{\"status\":\"logged_out\"}");
                })
                .permitAll())
            .build();
    }
}

record LoginRequest(String username, String password) {}

record LoginResult(String username, boolean authenticated) {}

record ErrorBody(String code, String message) {}

@RestController
class AuthController {

    private final AuthenticationManager manager;
    private final SecurityContextRepository contextRepository;
    private final SessionAuthenticationStrategy sessionStrategy;

    AuthController(
            AuthenticationManager manager,
            SecurityContextRepository contextRepository,
            SessionAuthenticationStrategy sessionStrategy) {
        this.manager = manager;
        this.contextRepository = contextRepository;
        this.sessionStrategy = sessionStrategy;
    }

    @GetMapping(value = "/", produces = MediaType.APPLICATION_JSON_VALUE)
    java.util.Map<String, String> index() {
        return java.util.Map.of(
            "csrf", "/csrf",
            "login", "/api/auth/login",
            "me", "/api/auth/me",
            "logout", "/api/auth/logout");
    }

    @GetMapping(value = "/csrf",
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<CsrfToken> csrf(CsrfToken token) {
        // Access token value để deferred token được load/lưu.
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(token);
    }

    @PostMapping(value = "/api/auth/login",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<?> login(
            @RequestBody LoginRequest body,
            HttpServletRequest request,
            HttpServletResponse response) {

        if (body == null || body.username() == null
                || body.username().isBlank()
                || body.password() == null
                || body.password().isBlank()) {
            return ResponseEntity.badRequest()
                .cacheControl(CacheControl.noStore())
                .body(new ErrorBody(
                    "invalid_request", "Username and password required"));
        }

        try {
            // 1. Chưa xác thực: không gọi authenticated factory
            //    hoặc setAuthenticated(true) bằng dữ liệu client.
            UsernamePasswordAuthenticationToken candidate =
                UsernamePasswordAuthenticationToken.unauthenticated(
                    body.username(), body.password());

            // 2. Provider kiểm tra password, trạng thái account.
            Authentication accepted = manager.authenticate(candidate);

            // 3. Session fixation: đổi session ID.
            //    CSRF strategy: xóa token trước login, GET /csrf
            //    ở request sau sẽ sinh token mới.
            sessionStrategy.onAuthentication(
                accepted, request, response);

            // 4. Tạo context mới, không mutate global singleton.
            SecurityContext context =
                SecurityContextHolder.createEmptyContext();
            context.setAuthentication(accepted);
            SecurityContextHolder.setContext(context);

            // 5. BẮT BUỘC với JSON login tự viết dùng session.
            //    Repository này cũng được dùng bởi filter chain.
            contextRepository.saveContext(context, request, response);

            // 6. Chỉ trả data công khai, không trả credentials.
            return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(new LoginResult(accepted.getName(), true));

        } catch (AuthenticationException rejected) {
            // Đừng trả rejected.getMessage() hoặc loại lỗi
            // locked/user-not-found cho người gọi công khai.
            SecurityContextHolder.clearContext();

            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .cacheControl(CacheControl.noStore())
                .body(new ErrorBody(
                    "invalid_credentials", "Sign-in failed"));
        }
    }

    @GetMapping(value = "/api/auth/me",
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<LoginResult> currentUser(Authentication authentication) {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new LoginResult(
                authentication.getName(), authentication.isAuthenticated()));
    }
}
```

### 7.1. Phân tích code theo đúng thứ tự

**A — `AuthenticationManager` và provider:**

`new ProviderManager(List.of(provider))` có một `DaoAuthenticationProvider` sử dụng `UserDetailsService` và BCrypt. Controller chỉ gọi `manager.authenticate(candidate)`. Với password sai, manager ném `AuthenticationException`; controller trả 401 chung. Không dùng username string hoặc `Origin` làm bằng chứng rằng user đã đăng nhập.

**B — `HttpSessionSecurityContextRepository`:**

Đây là repository **được chia sẻ** giữa `SecurityFilterChain` và controller. Nếu tạo một repository ở controller khác với repository của chain hoặc cấu hình chain stateless, request sau có thể không đọc được trạng thái đã lưu. Trong project, cả hai nhận cùng Spring bean.

**C — SessionAuthenticationStrategy được gọi tường minh:**

Spring Security 6 không mặc định dùng `SessionManagementFilter` để phát hiện một `Authentication` mới do controller tự set. Do đó controller gọi `CompositeSessionAuthenticationStrategy` **trước khi saveContext**, gồm:
- `ChangeSessionIdAuthenticationStrategy`: đổi session ID nếu đã có session, giảm nguy cơ session fixation.
- `CsrfAuthenticationStrategy`: xóa CSRF token đã dùng trước authentication; request sau cần token mới.

Ở hệ thống production còn có thể cần concurrent-session registry, maximumSessions, event publisher, MFA reauthentication và remember-me logic; những thứ đó **không tự được tích hợp đầy đủ chỉ vì controller gọi authenticate**.

**D — Tạo và lưu SecurityContext:**

`SecurityContextHolder.createEmptyContext()` tránh dùng chung mutable context giữa các request/thread. `setAuthentication(accepted)` gắn đối tượng từ provider đã xác minh. `SecurityContextHolder.setContext(context)` làm controller/service trong cùng request nhìn thấy principal; **`saveContext`** làm request sau đọc được từ HttpSession.

**E — Dùng `LogoutFilter` thay vì tự xóa vài biến:**

Spring Security logout chuẩn đã có `SecurityContextLogoutHandler` và `CsrfLogoutHandler`. Nó xử lý cleanup phiên, context và CSRF token; ta chỉ thay response success thành JSON. Nếu tự viết `@PostMapping("/api/auth/logout")` mà chỉ gọi `SecurityContextHolder.clearContext()`, phiên có thể vẫn lưu Authentication ở repository và request sau vẫn đăng nhập.

**F — CSRF mặc định được bật:**

`.csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))` vẫn chặn POST thiếu token. Không đặt `csrf.disable()` để “thử login JSON cho dễ”; nếu làm vậy, một browser đang có session cookie có thể bị dụ thực hiện các thao tác không mong muốn.

### 7.2. Vì sao không thêm annotation @Transactional cho login?

Authentication và HttpSession persistence không mặc nhiên là một transaction JDBC duy nhất. Nếu bạn ghi audit, login counters, refresh token hoặc tenant state, cần xác định ranh giới transaction và điều kiện rollback. Không đánh đồng `saveContext` vào HttpSession với commit dữ liệu business; nếu sử dụng distributed session store, hệ thống còn chịu các đặc điểm cache/network consistency.

### 7.3. Điều gì xảy ra khi lỗi xác thực?

Controller bắt `AuthenticationException` và trả một thông điệp chung. Không cho người gọi biết “username không tồn tại” hay “account bị khóa”, vì có thể hỗ trợ user enumeration. Trong production, **cần** phân loại nội bộ `BadCredentialsException` khác `AuthenticationServiceException` (outage hệ thống), theo dõi lỗi, rate limit và tránh biến hỏng DB/LDAP thành “mật khẩu sai” kéo dài. Ví dụ giữ response public đơn giản để tập trung vào session persistence.

## 8. Dùng fetch với cookie và CSRF đúng cách

Các đoạn sau giả định frontend **cùng origin** với backend (ví dụ trang được phục vụ từ `http://localhost:8080`). Cross-origin cần cấu hình bổ sung ở phần 15.

### 8.1. Lấy token đầu tiên

```javascript
const BASE = ""; // same origin

async function obtainCsrfToken() {
  const response = await fetch(BASE + "/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error("Cannot obtain CSRF token");
  }
  return response.json(); // { token, headerName, parameterName }
}
```

Request `GET /csrf` có thể tạo HttpSession để lưu expected CSRF token. Browser nhận session cookie; sau đó **POST phải dùng cùng cookie**, không tạo jar mới giữa hai request.

### 8.2. Login bằng JSON

```javascript
async function jsonLogin(username, password) {
  const csrf = await obtainCsrfToken();

  const response = await fetch(BASE + "/api/auth/login", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify({ username, password })
  });

  const data = await response.json();

  if (!response.ok) {
    // Không ghi password hoặc token vào logger.
    throw new Error(data.code || "login_failed");
  }

  // Session được lưu ở server. Browser giữ cookie tự động.
  // Login đã xóa CSRF token cũ; request sau dùng token mới.
  await obtainCsrfToken();

  return data; // {username:"learner",authenticated:true}
}
```

**Đừng coi HTTP 200 một mình là chứng minh login thành công trong mọi ứng dụng.** Ở đây contract JSON có `authenticated:true` do controller chỉ trả sau khi manager đã verify và save context. Nếu bạn trộn formLogin mặc định, fetch có thể tự follow redirect đến HTML login page và cuối cùng nhận 200 không liên quan đăng nhập.

### 8.3. Kiểm tra phiên mới bằng request khác

```javascript
async function currentUser() {
  const response = await fetch(BASE + "/api/auth/me", {
    credentials: "same-origin",
    cache: "no-store"
  });

  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw new Error("Unexpected response " + response.status);
  }
  return response.json();
}
```

Browser **không cần gửi username/password lần nữa**. Nó gửi session cookie; Spring `SecurityContextHolderFilter` đọc Authentication từ session repository. Cũng không được đặt Authentication vào localStorage làm “bằng chứng login” thay server: localStorage do JS sửa được và không được Spring Security mặc nhiên tin cậy.

### 8.4. Logout qua Spring Security

```javascript
async function jsonLogout() {
  const csrf = await obtainCsrfToken();

  const response = await fetch(BASE + "/api/auth/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      [csrf.headerName]: csrf.token
    }
  });

  if (!response.ok) {
    throw new Error("Logout rejected " + response.status);
  }

  return response.json(); // {status:"logged_out"}
}
```

Logout **không được gửi qua GET chỉ vì tiện**. Với CSRF protection enabled, POST logout cần CSRF token hợp lệ. Sau logout, frontend phải xóa client-side state và không dùng lại token/session cũ.

### 8.5. Không lưu token ở đâu?

- Đừng đặt password, raw session ID hoặc CSRF token trong URL query.
- Không log toàn bộ request/response ở các endpoint login/logout.
- Không lưu username/password để tự động replay vô hạn ở frontend.
- Không gửi JWT trong ví dụ này: đây là session-cookie authentication, không phải JWT resource server.
- CSRF token không phải “bearer access token”. Nó chống giả mạo unsafe methods trong ngữ cảnh session, không đủ để chứng minh user đã login.

## 9. Thử nghiệm với curl: cùng một cookie jar từ đầu đến cuối

Chạy server local:

```bash
export DEMO_LOGIN_PASSWORD="$(openssl rand -hex 24)"
mvn spring-boot:run
```

Một phiên shell khác có thể dùng `curl` để kiểm tra từng bước. Với curl, **cookie jar phải được giữ nguyên**. Nếu muốn trích JSON tự động, dùng tool có JSON parser; dưới đây ghi rõ quy trình để không hard-code một giá trị token giả.

### Bước 1: GET /csrf, lưu cookie

```bash
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf
```

Response dự kiến:

```json
{
  "parameterName": "_csrf",
  "token": "<generated-CSRF-token>",
  "headerName": "X-CSRF-TOKEN"
}
```

**Đây là cấu trúc ví dụ; token thực do server sinh ngẫu nhiên và cần được lấy từ response đúng phiên.** Cookie jar chứa session identifier, phải bảo vệ file đó, không commit.

### Bước 2: POST JSON login có cookie và token

```bash
# Thay <csrf-from-step-1> bằng token được trả từ bước 1.
# Không đưa password thật trong shell history ở production.
curl -i -c cookies.txt -b cookies.txt \
  -X POST http://localhost:8080/api/auth/login \
  -H 'Content-Type: application/json' \
  -H 'X-CSRF-TOKEN: <csrf-from-step-1>' \
  --data '{"username":"learner","password":"<local-lab-password>"}'
```

**Chú ý về mẫu lệnh:** hai giá trị trong dấu `<...>` là minh họa, không phải giá trị chạy nguyên văn. Khi thực hành ở môi trường an toàn, dùng secret lab đã cấp và token thật cùng cookie; tránh paste password vào shell history bằng cách dùng script đọc từ secret store/biến phiên phù hợp. Đoạn JSON literal được đưa vào tài liệu để minh họa protocol, không phải automation không cần sửa.

Kỳ vọng: `200 {"username":"learner","authenticated":true}`; session cookie có thể được đổi ID trong phản hồi. Cookie jar cần dùng giá trị **mới nhất**, không cố giữ lại ID trước login.

### Bước 3: GET /api/auth/me chỉ với cookie

```bash
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/api/auth/me
```

Nếu lưu SecurityContext đúng, response dự kiến 200 JSON với user `learner`, không cần password. Nếu 401, xem phần troubleshooting: request có cookie mới chưa, repository có save context không, session có bị invalidated hoặc cấu hình stateless không.

### Bước 4: GET /csrf mới, sau đó POST logout

```bash
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf
```

Ghi nhận **token mới**. Sau đó:

```bash
curl -i -c cookies.txt -b cookies.txt \
  -X POST http://localhost:8080/api/auth/logout \
  -H 'X-CSRF-TOKEN: <new-CSRF-token>'
```

Kỳ vọng 200 `{"status":"logged_out"}`. GET `/api/auth/me` sau đó phải không còn quyền authenticated. Dùng cookie jar riêng cho mỗi kịch bản/test để không trộn session.

**Không dùng `curl -v` hoặc lưu request dump chứa raw password/session/CSRF trong logs chia sẻ.**

## 10. MockMvc: kiểm tra stateful login xuyên nhiều requests

Đây là phần quan trọng nhất để tránh bài thực hành chỉ “trả 200 là xong”. Chúng ta cần **cùng một MockHttpSession** từ lúc lấy CSRF token đến lúc kiểm tra request sau.

File: `src/test/java/demo/jsonlogin/JsonSessionLoginApplicationTests.java`

```java
package demo.jsonlogin;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "app.demo.login-password=synthetic-test-password-only-123456"
})
@AutoConfigureMockMvc
class JsonSessionLoginApplicationTests {

    private static final String PASSWORD =
        "synthetic-test-password-only-123456";

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    record SessionCsrf(
        MockHttpSession session,
        String headerName,
        String token) {}

    private SessionCsrf getCsrf(MockHttpSession existing)
            throws Exception {
        var builder = get("/csrf");
        if (existing != null) {
            builder.session(existing);
        }

        MvcResult result = mvc.perform(builder)
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.token").isString())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
            result.getRequest().getSession(false);
        assertThat(session).isNotNull();

        JsonNode json = mapper.readTree(
            result.getResponse().getContentAsString());

        return new SessionCsrf(
            session,
            json.get("headerName").asText(),
            json.get("token").asText());
    }

    private MvcResult login(SessionCsrf csrf, String password)
            throws Exception {
        String json = mapper.writeValueAsString(
            new LoginRequest("learner", password));

        return mvc.perform(post("/api/auth/login")
                .session(csrf.session())
                .header(csrf.headerName(), csrf.token())
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
            .andReturn();
    }

    @Test
    void anonymousCannotReadMe() throws Exception {
        mvc.perform(get("/api/auth/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCsrfIs403BeforePasswordIsChecked()
            throws Exception {
        mvc.perform(post("/api/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"username\":\"learner\","
                    + "\"password\":\"" + PASSWORD + "\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void incorrectPasswordReturnsGeneric401() throws Exception {
        SessionCsrf csrf = getCsrf(null);

        MvcResult response = login(csrf, "incorrect");

        assertThat(response.getResponse().getStatus())
            .isEqualTo(401);
        assertThat(response.getResponse().getContentAsString())
            .contains("invalid_credentials")
            .doesNotContain("BadCredentialsException");

        mvc.perform(get("/api/auth/me")
                .session(csrf.session()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void successfulJsonLoginPersistsAcrossSecondRequest()
            throws Exception {
        SessionCsrf csrf = getCsrf(null);

        MvcResult success = login(csrf, PASSWORD);
        assertThat(success.getResponse().getStatus()).isEqualTo(200);

        MockHttpSession loggedIn = (MockHttpSession)
            success.getRequest().getSession(false);

        assertThat(loggedIn).isNotNull();

        mvc.perform(get("/api/auth/me")
                .session(loggedIn))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"))
            .andExpect(jsonPath("$.authenticated").value(true));

        // Cùng session, request thứ ba vẫn authenticated.
        mvc.perform(get("/api/auth/me")
                .session(loggedIn))
            .andExpect(status().isOk());
    }

    @Test
    void successfulLoginChangesSessionId() throws Exception {
        SessionCsrf csrf = getCsrf(null);
        String beforeId = csrf.session().getId();

        MvcResult response = login(csrf, PASSWORD);
        assertThat(response.getResponse().getStatus()).isEqualTo(200);

        MockHttpSession after = (MockHttpSession)
            response.getRequest().getSession(false);

        assertThat(after).isNotNull();
        assertThat(after.getId()).isNotEqualTo(beforeId);
    }

    @Test
    void stalePreLoginCsrfTokenIsNotReusableAfterLogin()
            throws Exception {
        SessionCsrf first = getCsrf(null);

        MvcResult response = login(first, PASSWORD);
        assertThat(response.getResponse().getStatus()).isEqualTo(200);

        MockHttpSession session = (MockHttpSession)
            response.getRequest().getSession(false);

        // Login strategy đã clear CSRF token cũ.
        mvc.perform(post("/api/auth/logout")
                .session(session)
                .header(first.headerName(), first.token()))
            .andExpect(status().isForbidden());

        // Lấy token mới trước khi logout.
        SessionCsrf second = getCsrf(session);
        assertThat(second.token()).isNotEmpty();

        mvc.perform(post("/api/auth/logout")
                .session(session)
                .header(second.headerName(), second.token()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("logged_out"));
    }

    @Test
    void loggedInUserCannotUseAdminEndpoint()
            throws Exception {
        SessionCsrf csrf = getCsrf(null);
        MvcResult response = login(csrf, PASSWORD);
        assertThat(response.getResponse().getStatus()).isEqualTo(200);

        MockHttpSession loggedIn = (MockHttpSession)
            response.getRequest().getSession(false);

        mvc.perform(get("/api/admin")
                .session(loggedIn))
            .andExpect(status().isForbidden());
    }

    @Test
    void blankPasswordIs400WhenCsrfIsValid()
            throws Exception {
        SessionCsrf csrf = getCsrf(null);

        mvc.perform(post("/api/auth/login")
                .session(csrf.session())
                .header(csrf.headerName(), csrf.token())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"username\":\"learner\",\"password\":\"\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("invalid_request"));
    }
}
```

Chạy:

```bash
mvn test
```

**Kỳ vọng 8 test pass** nếu máy có Java 17+, Maven và tải được dependencies. Đây là dự kiến từ thiết kế, **không phải báo cáo đã thực thi Maven**. Bộ test xác minh:

- Protected GET không session → 401.
- POST login thiếu CSRF → 403 trước controller.
- Login password sai → 401 JSON, không tạo quyền authenticated.
- Login đúng → 200, request sau chỉ cần same session.
- Login đổi session ID để giảm session fixation.
- Token CSRF trước login không còn dùng được cho POST logout sau login.
- User authenticated nhưng thiếu role ADMIN → 403.
- JSON body thiếu password hợp lệ → 400.

**Chú ý MockMvc/đồng thời:** tests sử dụng session riêng cho từng method; tránh test parallel dùng state chung chưa được cô lập. `MockMvc` không chứng minh browser cookie policies, reverse proxy/session affinity hoặc multi-node store ngoài thực tế. Cần integration test qua embedded server và browser cho các vấn đề đó.

## 11. Tại sao phải gọi SessionAuthenticationStrategy trước saveContext?

Một filter login chuẩn như `UsernamePasswordAuthenticationFilter` thường làm nhiều việc sau provider success:

1. Chạy `SessionAuthenticationStrategy`.
2. Tạo và lưu SecurityContext.
3. Thực thi remember-me success nếu cấu hình.
4. Phát một số sự kiện interactive authentication.
5. Gọi `AuthenticationSuccessHandler`.
6. Kết thúc request bằng redirect hoặc response phù hợp.

Một MVC login controller **không tự nhiên được miễn** các bước session security quan trọng. Nếu bỏ `SessionAuthenticationStrategy`, có thể không được session fixation protection; nếu bỏ `saveContext`, request sau mất auth; nếu tự xử lý logout không đúng, session vẫn authenticated.

Trong ví dụ:

```java
Authentication accepted = manager.authenticate(candidate);

sessionStrategy.onAuthentication(accepted, request, response);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(accepted);
SecurityContextHolder.setContext(context);
contextRepository.saveContext(context, request, response);
```

**Thứ tự có ý nghĩa:** chỉ gọi session strategy sau khi provider xác thực thành công; đổi session ID và xóa CSRF token cũ trước khi lưu context; sau đó phản hồi JSON. Không dùng `session.getId()` làm proof người dùng hay tự set session attribute dưới tên tùy ý thay Spring Security repository.

### 11.1. Session fixation và request.setSessionId

Session fixation xảy ra khi attacker khiến nạn nhân sử dụng trước một session ID mà attacker biết, sau đó nạn nhân login, ID không thay và attacker có thể hijack. `ChangeSessionIdAuthenticationStrategy` gọi cơ chế Servlet `HttpServletRequest.changeSessionId()` khi có session; với Servlet container hiện đại, đây là lựa chọn mặc định của Spring Security.

Không viết một `Set-Cookie: JSESSIONID=<random string>` thủ công. Container quản lý session, cookie Path, HttpOnly, Secure, SameSite và ID store.

### 11.2. Session concurrency

Nếu sản phẩm yêu cầu mỗi user tối đa một session, Spring có `maximumSessions(1)`/`SessionRegistry`. Nhưng **custom controller tự viết phải tích hợp concurrent session strategy** và registry lifecycle đúng; không chỉ thêm một DSL rồi mặc định controller sẽ bị giới hạn. Cần test với hai browser sessions và nhiều nodes.

### 11.3. SecurityContextHolderStrategy

Ví dụ dùng `SecurityContextHolder` static, đủ cho project một ApplicationContext. Spring Security cũng cho phép inject `SecurityContextHolderStrategy` để tránh race cấu hình strategy trong môi trường nhiều application contexts. Tránh lưu `SecurityContext` vào singleton mutable field hoặc truyền ThreadLocal qua worker thread không có context propagation.

## 12. CsrfTokenRepository: token chưa login và token sau login

Trong Spring Security 6, CSRF protection được bật mặc định cho unsafe methods, và token có **deferred loading** và **BREACH protection** (giá trị được encode ngẫu nhiên theo request). Vì vậy không nên so sánh hai token text nhận ở hai GET rồi kết luận underlying persisted token đã được rotate; hai giá trị text có thể khác vì masking, ngay cả khi repository token không đổi.

**Bài học quan trọng hơn:** `CsrfAuthenticationStrategy` xóa token cũ khỏi repository sau login. Sau đó frontend phải GET `/csrf` mới; request POST với token pre-login phải bị từ chối.

### 12.1. Tại sao GET /csrf có thể tạo HttpSession?

`HttpSessionCsrfTokenRepository` cần lưu expected token để so request POST. Khi controller truy cập `CsrfToken.token` để trả JSON, token deferred có thể được generate/load và lưu trong HttpSession. Điều này tạo session **trước khi user đăng nhập**, hoàn toàn bình thường: có session ID **không có nghĩa authenticated**.

### 12.2. XorCsrfTokenRequestAttributeHandler và SPA

Theo Spring Security 6.5, request attribute handler mặc định là `XorCsrfTokenRequestAttributeHandler` để chống BREACH, còn `HttpSessionCsrfTokenRepository` là repository mặc định. Khi trả token bằng `/csrf`, mã frontend có thể dùng giá trị/header name được trả. Nếu frontend đọc unmasked token trực tiếp từ `CookieCsrfTokenRepository`, cần cấu hình request handler cho SPA theo tài liệu chính thức, tránh gửi unmasked token vào handler mong encoded token mà không hiểu cơ chế.

Ví dụ bài này **không sử dụng CookieCsrfTokenRepository**; token trong JSON và expected token trong session, không có thêm XSRF-TOKEN cookie riêng.

### 12.3. Vì sao không tắt CSRF để POST login dễ hơn?

Trong session browser app, cookie có thể được browser tự gửi theo cookie policy. Attacker có thể lợi dụng login CSRF, session swapping hoặc state-changing requests nếu server thiếu protection. CSRF và session auth giải quyết hai câu hỏi khác nhau:
- Session: client đang mang phiên đã xác thực của user nào?
- CSRF: unsafe request có thực sự được phát sinh với token/intent hợp lệ không?

CORS preflight thành công **không** thay CSRF token, kể cả frontend JSON. Cookie SameSite giúp giảm một số rủi ro cross-site nhưng không thay kiểm tra server-side trong threat model dùng cookie.

## 13. Các lỗi sai thường gặp khi tự viết login JSON

### 13.1. Không gọi saveContext

**Sai:**

```java
SecurityContextHolder.setContext(context);
return ResponseEntity.ok(Map.of("authenticated", true));
```

**Đúng:** gọi `contextRepository.saveContext(context, request, response)` trước khi response commit. Ưu tiên dùng repository **cùng bean** với security filter chain.

### 13.2. Chỉ set Authentication lên context cũ

```java
SecurityContextHolder.getContext()
    .setAuthentication(authenticated);
```

Mã trên không tự lưu qua request. Khi mutable context có thể được chia sẻ/reference, Spring Security khuyến nghị `createEmptyContext()` rồi set để tránh race/unintended shared mutation. Dùng accepted Authentication từ manager, không tự gọi `setAuthenticated(true)` trên token lấy từ user.

### 13.3. Đặt SessionCreationPolicy.STATELESS

```java
http.sessionManagement(s ->
    s.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
```

Policy này phù hợp cho một số bearer/API key architectures nhưng **mâu thuẫn** với yêu cầu giữ login qua HttpSession. Có thể cấu hình repository khác hoặc nhiều chains có chủ đích, nhưng không copy stateless config từ một resource-server tutorial vào session-login chain rồi mong `JSESSIONID` hoạt động.

### 13.4. Trả 200 khi password sai

Sai nghiêm trọng:

```java
try {
    manager.authenticate(candidate);
} catch (AuthenticationException ex) {
    // SAI: chỉ ghi warning và tiếp tục tạo session authenticated
}
return ResponseEntity.ok(Map.of("authenticated", true));
```

Nếu manager từ chối, phải dừng nhánh success, không lưu context authenticated. Public response nên chung để chống enumeration; internal telemetry phải phân biệt credential failure với hạ tầng outage.

### 13.5. POST /login là 403 nhưng nghĩ password sai

Nếu thiếu CSRF token, `CsrfFilter` từ chối **trước controller**. Cần GET /csrf, giữ đúng cookie jar, gửi header đúng. Không sửa `AuthenticationManager` khi lỗi là CSRF.

### 13.6. Login thành công nhưng /me vẫn 401

Lý do phổ biến: không saveContext, repository của controller và chain không trùng, cookie mới không được gửi, session mất ở load balancer, session store không được chia sẻ, session timeout hoặc client request mới không gửi `credentials`.

### 13.7. Logout chỉ gọi SecurityContextHolder.clearContext()

Clear holder trên thread hiện tại không nhất thiết xóa Authentication đã lưu ở session repository. Dùng `LogoutFilter`, vì nó xử lý invalidation, context persistence, CSRF và các `LogoutHandler` khác.

### 13.8. Gửi raw password trong URL

Không gửi `GET /api/auth/login?username=...&password=...`; URL có thể vào browser history, reverse proxy logs, analytics, referrer và caches. Dùng POST JSON body qua HTTPS và không log body.

### 13.9. Tin cookie ID như user ID

Cookie/session ID là opaque credential của phiên. Không biến client-supplied `userId`, `role` hoặc `X-User` thành Authentication nếu không có trusted pre-auth gateway và verification boundary. Principal/roles phải đến từ provider/user store đáng tin.

### 13.10. Lỗi HTTP Basic hoặc formLogin bất ngờ chiếm endpoint

Nếu vừa bật `formLogin`, vừa có controller `POST /login`, `UsernamePasswordAuthenticationFilter` có thể xử lý request trước MVC (theo matcher) và tạo redirect. Bài dùng `/api/auth/login` riêng và tắt `formLogin/httpBasic` để kết quả nhất quán.

## 14. Cấu hình cookie, TLS, session lifetime

Một session-based web app production nên áp dụng:

- HTTPS và HSTS; không gửi session cookie hoặc password qua HTTP public.
- Session cookie `HttpOnly` để giảm khả năng JS truy cập cookie trực tiếp.
- Cookie `Secure` cho HTTPS; reverse proxy phải truyền đúng scheme đã được tin cậy.
- `SameSite=Lax/Strict/None` theo kiến trúc frontend/backend. `None` thường cần `Secure` và còn phụ thuộc third-party cookie policies.
- Host-only cookie nếu có thể, hạn chế `Domain` quá rộng; cân nhắc tiền tố `__Host-` nếu hạ tầng hỗ trợ.
- Không truyền session ID qua URL rewriting hoặc logs.
- Session idle timeout và absolute timeout/reauthentication cho tác vụ nhạy cảm.
- Invalidate và làm sạch state sau logout; tránh giữ session cũ trong frontend cache.
- Session fixation protection tại login, và có policy step-up/MFA nếu nghiệp vụ cần.
- Quản lý concurrent sessions, revocation/password reset và role changes.
- Session repository/distributed backing store phù hợp nhiều pods/instances.

**Chú ý:** `server.servlet.session.cookie.secure=true` có thể gây khác biệt khi test localhost HTTP; chỉ bật rõ trong môi trường đã có HTTPS. Nhưng không được dùng thiết lập dev không-Secure ngoài Internet.

## 15. Frontend khác origin: CORS, credentials và cookie policy

Ví dụ:

```text
Frontend: https://app.example.com
Backend:  https://api.example.com
```

Hai host này **khác origin** nhưng thường **cùng site** nếu đều HTTPS và cùng registrable domain. Browser JS muốn đọc response từ backend cần CORS đúng allowlist, và credentialed requests cần:

```javascript
fetch("https://api.example.com/api/auth/me", {
  credentials: "include"
});
```

Backend cần CORS headers chính xác cho frontend origin; không dùng `Access-Control-Allow-Origin: *` với credentials. Cần chính sách `Access-Control-Allow-Credentials: true`, allowed methods/headers tương ứng với `Content-Type` và `X-CSRF-TOKEN`, xử lý OPTIONS preflight trước Spring authentication.

**CORS không xác minh identity và không bảo vệ CSRF.** Một preflight 200 chỉ xác nhận browser cross-origin policy, không có nghĩa đã login. Một browser có thể chặn JS đọc response, nhưng request simple khác có thể được server thực thi; vì vậy session-based mutations vẫn phải xác minh CSRF.

Nếu frontend và API nằm ở **hai site khác nhau**, SameSite cookie/third-party cookie blocking có thể khiến flow không bền vững. Cân nhắc BFF/reverse proxy cùng site hoặc kiến trúc OAuth2/OIDC phù hợp, không mở CORS mọi origin để “sửa” cookie.

## 16. Stateless API có nên dùng cách này không?

**Không** nếu yêu cầu thực sự là token-based stateless API. Trong stateless flow:
- mỗi request gửi bearer token hoặc API key được kiểm chứng;
- `SecurityContextRepository` có thể là `NullSecurityContextRepository`;
- không dựa vào HttpSession;
- `SessionCreationPolicy.STATELESS` phù hợp;
- client cần token expiry/revocation/refresh flow tương ứng.

Trong **session JSON login** của bài này:
- password chỉ gửi ở login;
- backend cấp HttpSession (JSESSIONID);
- browser tự gửi cookie sau login;
- context được lưu ở session repo;
- CSRF cần được đánh giá và trong ví dụ giữ bật;
- logout invalidate session.

**JWT nằm trong cookie tự gửi** không tự biến ứng dụng thành “không có CSRF risk”; cookie vẫn là ambient credential. Đừng chọn bật/tắt CSRF chỉ theo tên endpoint bắt đầu bằng `/api/`.

## 17. Nhiều SecurityFilterChain: bảo đảm request dùng đúng repository

Một hệ thống hỗn hợp có thể có:

```text
@Order(1): /api/token/**
  Stateless bearer JWT
  NullSecurityContextRepository
  CSRF policy dựa trên bearer header và threat model

@Order(2): /api/auth/**, /web/**
  Stateful JSON login + session cookie
  HttpSessionSecurityContextRepository
  CsrfTokenRepository session
```

Spring Security chọn **chain đầu tiên phù hợp**, không chạy mọi chain. Nếu catch-all stateless chain đứng trước stateful login chain, request có thể đi vào repository sai, khiến login response 200 nhưng /me anonymous. Cần test matcher, precedence, request cache, CSRF và session policy của **từng chain**.

Không đặt `csrf.disable()` ở chain session chỉ vì một bearer endpoint khác không cần CSRF. Không dùng cookie-based login làm fallback cho API bearer mà không phân tích ambient credentials.

## 18. Vấn đề concurrency và lưu context

Một `HttpSession` có thể phục vụ nhiều requests đồng thời. Việc `SecurityContextHolder` theo thread chỉ mô tả **request đang chạy**, còn session repository giữ trạng thái đọc/lưu. Khi logout xảy ra trong lúc request khác đang xử lý, request cũ có thể đã có Authentication snapshot trước khi session invalidated.

Nếu nghiệp vụ cực kỳ nhạy cảm, nên revalidate authorization/token revocation ngay gần điểm commit theo threat model; không nghĩ một logout response có thể thu hồi hồi tố mọi tác vụ đã chạy.

Một số nguyên tắc:

- Không cất SecurityContext trong static field để “chia sẻ” giữa requests.
- Không tự sao chép ThreadLocal sang async executor bằng shared global variables.
- Với asynchronous code, sử dụng Spring Security context propagation phù hợp hoặc truyền identity đã xác minh, kiểm tra lại quyền khi cần.
- Hạn chế simultaneous login/submission races, session fixation, session timeout và session reuse.
- Trong cluster, dùng Spring Session/Redis hoặc giải pháp shared session tùy kiến trúc; không mặc định HttpSession in-memory của pod A có sẵn ở pod B.
- Đảm bảo session serialization/compatibility nếu repository lưu ở Redis, đặc biệt khi thay principal class giữa releases.

### 18.1. Sự kiện xác thực và audit

Một controller tự viết gọi `AuthenticationManager` trực tiếp, nên audit event do manager/publisher và interactive events từ framework filters có thể khác với form login mặc định. Nếu tự tạo `ProviderManager` và cần Spring `AuthenticationSuccessEvent` / failure events, gắn `AuthenticationEventPublisher` một cách tường minh; không đoán manager custom mặc định luôn publish. Tránh log raw password hoặc toàn bộ Authentication.

Khi audit phục vụ compliance, cần lưu bền vững và dedup/replay thích hợp; một Spring application event trong process không tự bảo đảm exactly-once durability.

## 19. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân hay gặp | Cách kiểm tra |
| --- | --- | --- |
| POST JSON login trả 403 | Thiếu/sai CSRF token | GET /csrf, cùng cookie jar, CSRF header |
| POST login 415 | Content-Type không phải application/json | Gửi `Content-Type: application/json` |
| POST login 400 | JSON malformed/username hoặc password blank | Kiểm tra body binding/validation |
| POST login 401 | Credential không hợp lệ hoặc auth exception | Kiểm tra manager/provider ở server, không log password |
| POST login trả 200 nhưng GET /me 401 | Quên `saveContext`, session/repo mismatch, cookie không gửi | Đọc session, repository, response Set-Cookie và next request Cookie |
| Login đúng nhưng session ID không đổi | Không gọi session strategy hoặc không có session trước đó | GET /csrf tạo session trước login, kiểm tra changeSessionId |
| POST sau login trả 403 | Dùng CSRF token trước login đã bị clear/rotate | GET /csrf mới sau login |
| POST logout 403 | Thiếu token mới hoặc sai session | GET /csrf trong session hiện tại, gửi header |
| Logout JSON trả 200 nhưng /me vẫn 200 | Không invalidated session/repo | Dùng LogoutFilter; kiểm tra session store/cache |
| GET /me trả 302 HTML | Đang bật formLogin entry point | Dùng API entry point 401 và chain đúng |
| User login rồi /api/admin 403 | Role USER không phải ADMIN | Kiểm tra authorization, không sửa password verification |
| Browser không có cookie dù backend 200 | SameSite/Secure/Domain/Path/proxy/third-party policies | Inspect Set-Cookie và browser DevTools |
| Postman/curl gọi được nhưng browser lỗi CORS | CORS chỉ áp dụng browser, preflight/credential policy sai | Kiểm tra OPTIONS, Origin và response headers |
| Session mất giữa hai pods | Local session store không chia sẻ | Session replication/Spring Session/affinity |
| Multi-node request gặp ClassCast/serialization error | Custom principal/session data không tương thích giữa releases | Versioning/rolling deployments |
| AccessDeniedException thành 500 | Custom filter đặt trước exception translation hoặc controller sai boundary | Filter order và handler trách nhiệm |
| Session cũ còn quyền sau đổi role | Persisted authorities stale | Session revocation/reauth/permission refresh |
| Duplicated login actions | Frontend retry, double-click, gateway retry | Request ID, anti-brute-force, idempotency policy |

### 19.1. Quy trình debug 8 bước

1. Xác nhận **SecurityFilterChain** nào bắt `/api/auth/login` và `/api/auth/me`.
2. Xem POST có CSRF header và **cùng JSESSIONID cookie** từ GET /csrf không.
3. Kiểm tra `manager.authenticate(...)` trả Authentication hay ném exception, không in password.
4. Kiểm tra `sessionStrategy.onAuthentication(...)` có chạy sau success không.
5. Xác nhận controller gọi `SecurityContextHolder.setContext(...)` và `repository.saveContext(...)` **trước response commit**.
6. Kiểm tra client nhận session cookie mới khi ID đổi, rồi gửi cookie đó ở GET /me.
7. Xem GET /me có load Authentication từ **đúng repository**, session chưa expired và role có đúng không.
8. Với logout, kiểm tra CSRF token mới, session invalidation và GET /me trả 401.

Trong môi trường dev riêng có thể tăng Spring Security DEBUG logs, nhưng không bật wire logging ghi `Authorization`, `Cookie`, raw passwords hoặc CSRF token ở production.

## 20. Mở rộng production: những gì demo cố tình không làm

| Hạng mục | Demo | Yêu cầu production |
| --- | --- | --- |
| User store | InMemoryUserDetailsManager | Database/directory/IdP và migration an toàn |
| Password | Biến môi trường lab, BCrypt | Password policy, reset, breach check, encoder upgrades |
| Credential errors | Generic 401 | Monitoring riêng bad credentials và outage |
| Anti-brute force | Chưa có | Rate limiting, adaptive controls, lockout phù hợp |
| Session | HttpSession local | Secure cookies, rotation, multi-node repository, expiry |
| CSRF | Session token | SPA integration/BREACH handling, token lifecycle tests |
| MFA/passkey | Chưa có | Step-up theo rủi ro và assurance |
| Auth events | Tối giản | Event publisher, audit, safe logging, incident response |
| Logout | Spring LogoutFilter | Revoke remember-me/sessions/devices tùy policy |
| Account disabled/locked | In-memory enabled demo | Account state checks, admin actions, recovery |
| CORS | Same-origin | Explicit allowlist nếu cross-origin |
| TLS | localhost HTTP lab | HTTPS, proxy trust, HSTS, secure cookies |
| Session concurrency | Chưa giới hạn | SessionRegistry/distributed strategy |
| Error schema | JSON/HTTP status tối thiểu | API versioning, content negotiation, Problem Details |
| Tests | MockMvc | Embedded server/browser/e2e, proxy, concurrency, chaos |

**Không copy sample password, session cookie settings hoặc CORS dev vào môi trường thật.** Các thông số bảo mật phải đến từ policy/operational requirements.

## 21. Bài tập tự kiểm tra

1. **Vì sao controller gọi authenticate rồi trả 200 vẫn có thể mất login ở request sau?** Vì chưa saveContext vào repository.
2. **Authentication object nào được lưu?** Đối tượng **đã được manager xác thực**, không phải candidate có password từ client.
3. **Trong Spring Security 6, SecurityContextHolderFilter làm gì?** Chủ yếu đọc/khôi phục context; custom code muốn persist phải lưu tường minh.
4. **Khi nào gọi SessionAuthenticationStrategy?** Sau khi manager xác thực thành công, trước khi lưu context/trả response.
5. **ChangeSessionIdAuthenticationStrategy chống gì?** Session fixation; không thay password verification.
6. **Tại sao GET /csrf có thể tạo session dù chưa login?** CSRF repo cần lưu expected token; session không có nghĩa authenticated.
7. **Tại sao cần token CSRF mới sau login?** CsrfAuthenticationStrategy xóa token cũ.
8. **Vì sao hai text CSRF tokens khác nhau chưa chắc chứng minh rotate persisted token?** Vì XorCsrfTokenRequestAttributeHandler tạo masked value ngẫu nhiên mỗi request.
9. **POST login thiếu CSRF trả 403 là lỗi mật khẩu?** Không; request bị chặn trước controller.
10. **POST login sai password trả 401 nhưng GET /me trả 401 có nghĩa gì?** Không có Authentication hợp lệ được lưu.
11. **POST login đúng trả 200 và GET /me trả 200 với cùng cookie chứng minh gì?** Session persistence của SecurityContext hoạt động ở mức flow.
12. **Vì sao không dùng SessionCreationPolicy.STATELESS cho bài này?** Nó mâu thuẫn với lưu authentication trong HttpSession.
13. **Vì sao tắt formLogin trong demo?** Để tránh filter HTML/form processing can thiệp JSON contract.
14. **Vì sao logout nên dùng LogoutFilter?** Nó xử lý session/context/CSRF/remember-me và cleanup phù hợp.
15. **JWT lưu trong cookie có chắc không cần CSRF không?** Không; cookie có thể được browser tự đính kèm.
16. **Frontend khác origin cần gì ngoài session?** CORS allowlist, credentialed fetch, cookies SameSite/Secure/Domain và CSRF.
17. **Một user có quyền USER nhưng không có ADMIN thì /api/admin nên trả gì?** 403, không phải 401 bad password.
18. **Có nên dùng Session ID từ cookie làm user ID?** Không; session opaque và phải được lookup/validate server-side.
19. **Nếu app chạy hai pods không chia sẻ session, chuyện gì xảy ra?** Request chuyển pod có thể thành anonymous dù login trước đó thành công.
20. **Test MockMvc có đủ bảo đảm cookie production an toàn không?** Không; cần browser/TLS/reverse proxy testing.

## 22. Checklist nghiệm thu và tài liệu chính thức

### Checklist

- [ ] `POST /api/auth/login` nhận JSON, credentials được provider kiểm tra.
- [ ] Login sai không tạo authenticated context, trả public 401 chung.
- [ ] Login đúng tạo SecurityContext mới, set holder và **saveContext** cùng repository được filter chain sử dụng.
- [ ] Session strategy xử lý session fixation; ID đổi khi có session pre-login.
- [ ] CSRF bật cho POST login và logout; token cũ vô hiệu sau login.
- [ ] `GET /csrf` có `Cache-Control: no-store` và không coi token là bằng chứng login.
- [ ] Request thứ hai chỉ có cookie vẫn lấy được principal từ repository.
- [ ] `/api/auth/me` anonymous nhận 401, user authenticated nhận 200.
- [ ] Protected action thiếu role nhận 403.
- [ ] Logout chuẩn invalidate session, clear context/CSRF, không chỉ xóa biến trong controller.
- [ ] JSON responses không chứa password, raw exception, token hay session ID.
- [ ] Không dùng static Authentication hoặc stateless chain để giả vờ duy trì phiên.
- [ ] Session cookie/TLS/proxy/CORS/SameSite có kiểm thử browser trong môi trường triển khai.
- [ ] Rate limit, audit, MFA/step-up và session revocation theo policy sản phẩm.
- [ ] Test đã chạy ở phiên bản Spring Boot/Security thực tế trước khi deploy.

### Tài liệu đối chiếu

- Spring Security 6.5 – Authentication Persistence and Session Management (manual save): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 – Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 – CSRF, deferred token and SPA handling: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security 6.5 – Handling Logouts: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security 6.5 – Servlet Security Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security 6.5 – SecurityContextRepository API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html
- Spring Security 6.5 – HttpSessionSecurityContextRepository API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/HttpSessionSecurityContextRepository.html
- Spring Security 6.5 – CsrfAuthenticationStrategy API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/CsrfAuthenticationStrategy.html
- Spring Security 6.5 – ChangeSessionIdAuthenticationStrategy API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/ChangeSessionIdAuthenticationStrategy.html
- Spring Security 6.5 – MockMvc Security Testing: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html
- Spring Boot 3.5 – Servlet Web Applications: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- OWASP – Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP – CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP – Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
