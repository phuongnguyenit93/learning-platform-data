# Đăng nhập JSON dùng phiên, principal riêng và đăng xuất an toàn

## 1. Bài toán: API JSON nhưng vẫn sử dụng phiên đăng nhập

Một ứng dụng **Spring Boot + Spring Security Servlet** có thể cung cấp frontend JavaScript hoặc trang HTML muốn gửi thông tin đăng nhập qua JSON, dùng cookie phiên để duy trì trạng thái xác thực và gọi những API tiếp theo bằng cùng phiên. Mục tiêu khác với API thuần bearer token:

- Client gọi `GET /api/auth/csrf` để lấy token CSRF cùng một phiên vô danh.
- Client gửi `POST /api/auth/login` với body JSON `{"username":"alice","password":"..."}` và CSRF header hợp lệ.
- Backend dùng `AuthenticationManager` xác thực thông tin, xây dựng **principal riêng** chứa ID bất biến/tenant, chống **session fixation**, ghi `Authentication` vào `SecurityContext` và **lưu context vào HTTP session**.
- Browser giữ cookie `JSESSIONID` để các request sau được xác thực bởi session.
- `GET /api/me` chỉ cho user đã đăng nhập và trả một DTO an toàn (không trả password hash hay `SecurityContext`).
- `POST /api/auth/logout` yêu cầu CSRF token và chấm dứt phiên, xoá authentication. Sau đăng xuất, phiên cũ không được tiếp tục cấp quyền.

**Tư tưởng quan trọng:** trả `200 OK` sau `AuthenticationManager.authenticate(...)` **không tự đồng nghĩa** các request sau đã có đăng nhập. Với Spring Security 6, khi tự viết controller đăng nhập, bạn phải xử lý chính xác vòng đời `SecurityContextRepository` và `SessionAuthenticationStrategy`, thay vì trông chờ filter đăng nhập mặc định làm thay.

Bài thực hành sẽ dùng Spring Boot **3.3.5**, Spring MVC/Servlet, Java **17+**, Java records cho DTO, `DaoAuthenticationProvider`, BCrypt, session cookie, `HttpSessionCsrfTokenRepository`, `HttpSessionSecurityContextRepository` và MockMvc. Không dùng `csrf().disable()` để tiện login; đăng nhập dạng JSON và cookie session vẫn có nguy cơ CSRF.

## 2. Sơ đồ tổng quan luồng request

```text
BROWSER CÙNG ORIGIN                SPRING BOOT SERVLET
        |                                   |
        | GET /api/auth/csrf                |
        |---------------------------------->|
        |  CsrfFilter -> HttpSessionCsrfTokenRepository
        |<----------------------------------|
        | cookie JSESSIONID + CSRF token    |
        |                                   |
        | POST /api/auth/login              |
        | Cookie: JSESSIONID                |
        | X-CSRF-TOKEN: <token>             |
        | JSON {username,password}          |
        |---------------------------------->|
        | CsrfFilter kiểm token             |
        | AuthController                    |
        | AuthenticationManager             |
        |  -> DaoAuthenticationProvider     |
        |  -> PasswordEncoder.matches(...)  |
        |  -> UserDetailsService            |
        | SessionAuthenticationStrategy     |
        |  -> changeSessionId()             |
        |  -> xoá CSRF token đăng nhập cũ   |
        | SecurityContextRepository         |
        |  -> saveContext vào HTTP session  |
        |<----------------------------------|
        | 200 JSON user-safe DTO            |
        |                                   |
        | GET /api/me + session cookie      |
        |---------------------------------->|
        | SecurityContextHolderFilter       |
        |  -> load Authentication từ session|
        | AuthorizationFilter -> authenticated()
        |<----------------------------------|
        | 200 JSON user metadata            |
        |                                   |
        | GET /api/auth/csrf (token mới)    |
        |---------------------------------->|
        |<----------------------------------|
        | POST /api/auth/logout + CSRF      |
        |---------------------------------->|
        | CsrfFilter -> LogoutFilter        |
        | -> SecurityContextLogoutHandler   |
        | -> session.invalidate()           |
        | -> CsrfLogoutHandler              |
        |<----------------------------------|
        | 204 No Content; cookie hết hiệu lực
```

Một số điểm dễ nhầm:

1. **CSRF token khác session ID.** CSRF token chứng minh request ghi dữ liệu đến từ client có quyền dùng phiên hợp lệ theo contract chống CSRF; nó không dùng để xác thực mật khẩu.
2. **Session fixation protection** thay đổi session ID khi login thành công; không nên giữ ID session vô danh trước login như ID của session đã xác thực.
3. **Principal riêng** phải đến từ dữ liệu backend đã tin cậy **sau khi xác thực**. Client không tự gửi `role=ADMIN`, `userId`, `tenantId` để quyết định quyền.
4. **Logout** chấm dứt trạng thái xác thực phía server; chỉ xóa cookie phía frontend chưa đủ nếu session phía server vẫn hoạt động.
5. Khi cookie session được browser tự gửi, CSRF protection là vấn đề riêng với authentication/authorization, **không thể thay bằng CORS**.

## 3. Vì sao dùng HTTP session thay vì JWT?

Session cookie phù hợp khi trình duyệt và backend cùng origin hoặc có quan hệ cookie được kiểm soát:

| Khía cạnh | Session cookie | Bearer JWT |
| --- | --- | --- |
| Trạng thái đăng nhập | Server lưu `SecurityContext` trong session | Caller gửi bearer token và Resource Server kiểm chứng token |
| Thu hồi phiên | Server có thể `invalidate()` session, xóa session store | Cần expiry/revocation/token lifecycle phù hợp |
| Request browser | Browser tự gửi cookie theo domain/path/SameSite | Frontend hoặc client phải quản lý token |
| CSRF | Quan trọng khi cookie được tự động gửi | Không tự động biến mất nếu JWT cũng lưu trong cookie |
| Mở rộng nhiều instance | Cần sticky session hoặc shared store như Spring Session | Token validation có thể stateless tùy kiến trúc |
| Thông tin quyền thay đổi | Cần cập nhật/invalidate context trong session | Cần chiến lược cập nhật/revoke token/claim |

**Không có lựa chọn nào tự động an toàn hơn trong mọi trường hợp.** Nếu UI là ứng dụng browser cần logout tức thời và session backend, cookie session có thể đơn giản hơn. Nếu API phục vụ mobile/server-to-server hoặc cần tách identity provider, Resource Server phù hợp hơn.

Với bài này, ta chọn session vì muốn học đầy đủ việc **lưu và xóa authentication theo vòng đời Servlet**.

## 4. Các thành phần Spring Security cần nắm

| Thành phần | Công việc | Lưu ý |
| --- | --- | --- |
| `SecurityFilterChain` | Bảo vệ URL, cấu hình CSRF/logout/security context | Cần bao phủ route login, CSRF, API và logout |
| `AuthenticationManager` | Xử lý một yêu cầu authentication | Không tự sinh session cookie chỉ nhờ gọi `authenticate()` |
| `DaoAuthenticationProvider` | Tra `UserDetailsService`, kiểm password bằng `PasswordEncoder` | Demo dùng BCrypt, không dùng `{noop}` production |
| `UserDetailsService` | Lấy username/password hash/authorities từ backend | Không nhận `roles` từ JSON client |
| `SecurityContext` | Chứa `Authentication` đã xác thực của request | Được tạo mới sau login thành công |
| `SecurityContextHolder` | Giữ context trong request thread | ThreadLocal thông thường; không phải session storage |
| `SecurityContextRepository` | Nạp/lưu context giữa các request | Ví dụ dùng `HttpSessionSecurityContextRepository` |
| `SessionAuthenticationStrategy` | Thực thi chính sách khi login thành công | Demo gồm đổi session ID và làm mới CSRF |
| `CsrfFilter`/`CsrfTokenRepository` | Kiểm request có side effect đến từ client được phép | Login/logout dùng POST có CSRF token |
| `LogoutFilter` | Nhận yêu cầu logout và gọi các `LogoutHandler` | Không tự đặt endpoint GET logout công khai |

Một controller tự viết chỉ gọi:

```java
Authentication result = manager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password));
```

mới chỉ hoàn thành **kiểm tra credential**. Phần xử lý session, lưu context và logout không tự hoàn thiện nếu bạn bỏ qua cơ chế mặc định của Spring Security.

## 5. Nguyên tắc bảo mật trước khi viết code

Bài demo tuân theo các quyết định:

1. **Đăng nhập bằng POST JSON**, không đưa password vào URL, query string hoặc `GET`.
2. **Giữ CSRF bật** cho các request ghi dữ liệu khi dựa vào cookie session; cả login lẫn logout đều phải có token hợp lệ.
3. **BCryptPasswordEncoder** cho password hash; demo dùng một account cố định chỉ trên `127.0.0.1`, không lưu plaintext trong user store.
4. **Không trả mật khẩu/hash** trong JSON response hay `toString()` của principal.
5. **Principal riêng** chỉ chứa `userId`, `username`, `tenantId`; quyền lấy từ nguồn user đáng tin của backend.
6. **Đổi session ID sau authentication**, chống session fixation; nếu app cần concurrent session control thì bổ sung các session strategies liên quan.
7. **Lưu context tường minh** bằng `SecurityContextRepository.saveContext(...)` để request kế tiếp đọc được user; không coi `SecurityContextHolder.setContext(...)` là persistence.
8. **Đăng xuất bằng POST** do `LogoutFilter` xử lý, session bị vô hiệu hóa và cookie được yêu cầu xóa; CSRF token cũng bị loại khỏi phiên.
9. **Response auth không cache**, chỉ sử dụng same-origin client trong demo, không mở CORS `*` với credentials.
10. **Ràng buộc session/tenant/authorization** ở backend; đừng tin `tenantId` gửi từ browser như bằng chứng quyền dữ liệu.

## 6. Cấu trúc project Java 17+ có thể chạy

```text
json-session-login/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/jsonsession/
    │   │   ├── JsonSessionApplication.java
    │   │   ├── AppPrincipal.java
    │   │   ├── SecurityConfig.java
    │   │   └── AuthController.java
    │   └── resources/
    │       ├── application.yml
    │       └── application-prod.yml
    └── test/java/demo/jsonsession/
        └── JsonSessionIntegrationTest.java
```

Demo dùng Java 17 records và Jakarta Validation. Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Cần Gradle wrapper tương thích Java 17; nếu thư mục có `gradlew`/`gradlew.bat`, sử dụng wrapper; nếu chưa có, phải cài Gradle tương thích và tạo wrapper theo quy trình build dự án. Các file dưới đây thuộc project Java, không phải những đoạn chỉ để chèn vào một class không có imports.

Tạo `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080
  servlet:
    session:
      cookie:
        http-only: true
        same-site: lax
```

Local sử dụng HTTP **chỉ tại loopback** nên không bật `Secure` trong cấu hình phát triển để cookie hoạt động trên địa chỉ `http://127.0.0.1`. Production bắt buộc dùng HTTPS và `Secure=true` như phần triển khai cuối bài; không để credential thực đi qua HTTP thường.

Tạo `src/main/java/demo/jsonsession/JsonSessionApplication.java`:

```java
package demo.jsonsession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonSessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonSessionApplication.class, args);
    }
}
```

## 7. Principal riêng: chỉ chứa identity đã được backend xác minh

Tạo `src/main/java/demo/jsonsession/AppPrincipal.java`:

```java
package demo.jsonsession;

import java.io.Serial;
import java.io.Serializable;
import java.security.Principal;

public record AppPrincipal(
        String userId,
        String username,
        String tenantId) implements Principal, Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    @Override
    public String getName() {
        return username;
    }
}
```

Đây là **principal ứng dụng** không chứa password, hash, raw HTTP cookie, token hoặc quyền do client tự khai.

Tại sao record implements `Principal`?

- `Authentication#getPrincipal()` có thể là `AppPrincipal` để service/controller truy cập ID và tenant chính thức.
- `Principal#getName()` khiến Spring Security và Spring MVC có thể đọc `Authentication#getName()` rõ ràng.
- `Serializable` giúp principal tương thích với storage HTTP session có serialization. Với cluster, session serialization và schema migration vẫn phải được kiểm thử riêng.
- Immutable record tránh sửa `tenantId` của principal từ một worker thread khi session đang được dùng đồng thời.

Trong production, `userId` và `tenantId` phải được tra từ **account directory/server-side database** sau khi `AuthenticationManager` xác thực thành công. Demo tạo mapping cố định cho một account `alice` đã biết; tuyệt đối không dùng:

```java
// Không an toàn: client không có quyền tự cấp principal/tenant.
new AppPrincipal(json.userId(), json.username(), json.tenantId());
```

Hệ thống nhiều tenant phải kiểm tra user có quyền truy cập **từng resource thuộc tenant** ở tầng service, không chỉ dựa vào việc principal đang có tenant ID. Session có thể trở nên stale khi user bị khóa/chuyển tenant; cần cơ chế revoke hoặc revalidate phù hợp.

## 8. Security configuration: provider, session, CSRF và logout

Tạo `src/main/java/demo/jsonsession/SecurityConfig.java`:

```java
package demo.jsonsession;

import java.util.List;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // Mật khẩu cố định chỉ để học trên 127.0.0.1.
        // Store chỉ giữ hash BCrypt, không giữ plain password.
        String hash = encoder.encode("demo-only");

        return username -> {
            if (!"alice".equals(username)) {
                throw new UsernameNotFoundException("Unknown user");
            }
            return User.withUsername("alice")
                    .password(hash)
                    .roles("USER")
                    .build();
        };
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy(
            CsrfTokenRepository csrfRepository) {
        return new CompositeSessionAuthenticationStrategy(List.of(
                new ChangeSessionIdAuthenticationStrategy(),
                new CsrfAuthenticationStrategy(csrfRepository)));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository contextRepository,
            CsrfTokenRepository csrfRepository)
            throws Exception {

        return http
                .securityContext(context -> context
                        .securityContextRepository(contextRepository))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.IF_REQUIRED))
                .csrf(csrf -> csrf
                        .csrfTokenRepository(csrfRepository))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET,
                                "/api/auth/csrf").permitAll()
                        .requestMatchers(HttpMethod.POST,
                                "/api/auth/login").permitAll()
                        .requestMatchers(HttpMethod.GET,
                                "/api/me").authenticated()
                        .anyRequest().denyAll())
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint((request, response, error) -> {
                            response.setStatus(
                                    HttpServletResponse.SC_UNAUTHORIZED);
                            response.setContentType(
                                    MediaType.APPLICATION_JSON_VALUE);
                            response.getWriter()
                                    .write("{\"error\":\"unauthorized\"}");
                        }))
                .logout(logout -> logout
                        .logoutUrl("/api/auth/logout")
                        .invalidateHttpSession(true)
                        .clearAuthentication(true)
                        .deleteCookies("JSESSIONID")
                        .logoutSuccessHandler((request, response, auth) ->
                                response.setStatus(
                                        HttpServletResponse.SC_NO_CONTENT)))
                .build();
    }
}
```

### 8.1. Vì sao các bean được khai báo tường minh?

**`AuthenticationManager`:** demo dùng `DaoAuthenticationProvider` với `UserDetailsService` và `PasswordEncoder` cùng một contract. Không nhầm `ProviderNotFoundException` với sai password: provider được đăng ký đúng loại `UsernamePasswordAuthenticationToken`.

**`HttpSessionSecurityContextRepository`:** Spring Security 6 thường yêu cầu **explicit save** khi bạn tự tạo `Authentication`. Cùng một repository instance được dùng trong filter chain và controller, nên request tiếp theo có thể load đúng context từ session. Chỉ `SecurityContextHolder.setContext(context)` thì không đủ.

**`SessionAuthenticationStrategy`:** controller tự làm login nên phải gọi policy sau khi authentication thành công. Demo đổi session ID qua `ChangeSessionIdAuthenticationStrategy` và làm mới CSRF state qua `CsrfAuthenticationStrategy`. Với form login filter mặc định, framework thường thực hiện các bước này; khi tự dùng MVC controller thì không nên bỏ qua.

**`HttpSessionCsrfTokenRepository`:** CSRF token lưu trong session. API `/api/auth/csrf` sẽ công khai token cho cùng-origin browser đang sử dụng session đó. GET này có thể tạo một session vô danh để lưu token; không phải lỗi bảo mật tự thân, nhưng phải kiểm soát tài nguyên và cookie policy.

**`SessionCreationPolicy.IF_REQUIRED`:** cho phép tạo session khi thật sự cần login/CSRF. Không dùng `STATELESS` nếu mong `JSESSIONID` và `SecurityContext` được lưu giữa các request.

**Logout:** `.logoutUrl("/api/auth/logout")` được xử lý bởi `LogoutFilter` (trước controller), với CSRF bật thì dùng POST; handler mặc định xóa authentication, vô hiệu hóa session và xóa CSRF token theo lifecycle logout. `deleteCookies("JSESSIONID")` chỉ là hỗ trợ xóa cookie ở browser: hiệu lực thực tế tùy path/domain/flags; **session server-side bị invalidate** mới là điểm thu hồi quyết định.

### 8.2. Tại sao chưa có `formLogin` hoặc `httpBasic`?

Vì endpoint này muốn **nhận JSON**, không dùng form parameter hoặc Authorization Basic header. `AuthenticationManager` được gọi trong controller để xác thực. Không cần bật `formLogin()` cho API JSON nếu không muốn endpoint/redirect mặc định của nó. Tuy nhiên cũng chính vì tự viết login mà bạn phải xử lý session fixation, security context saving, CSRF và HTTP error contract tường minh.

**Lưu ý phiên bản:** các setter của `DaoAuthenticationProvider` được ví dụ hóa theo Spring Security 6.x đi cùng Boot 3.3.5; ở dòng framework mới hơn có thể cần constructor/configuration khác. Khi nâng cấp, dùng API tương ứng và chạy lại test thay vì giả định code này bất biến mãi.

## 9. Controller đăng nhập JSON, CSRF bootstrap và `/api/me`

Tạo `src/main/java/demo/jsonsession/AuthController.java`:

```java
package demo.jsonsession;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class AuthController {

    private final AuthenticationManager authManager;
    private final SessionAuthenticationStrategy sessionStrategy;
    private final SecurityContextRepository contextRepository;

    public AuthController(
            AuthenticationManager authManager,
            SessionAuthenticationStrategy sessionStrategy,
            SecurityContextRepository contextRepository) {
        this.authManager = authManager;
        this.sessionStrategy = sessionStrategy;
        this.contextRepository = contextRepository;
    }

    public record LoginRequest(
            @NotBlank @Size(max = 100) String username,
            @NotBlank String password) {

        // Tránh vô tình in password từ record.toString().
        @Override
        public String toString() {
            return "LoginRequest[REDACTED]";
        }
    }

    public record UserView(
            String userId, String username, String tenantId) {}

    @GetMapping("/auth/csrf")
    public ResponseEntity<Map<String, String>> csrf(
            HttpServletRequest request) {

        CsrfToken token = (CsrfToken)
                request.getAttribute(CsrfToken.class.getName());

        return ResponseEntity.ok()
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(Map.of(
                        "headerName", token.getHeaderName(),
                        "token", token.getToken()));
    }

    @PostMapping("/auth/login")
    public ResponseEntity<?> login(
            @Valid @RequestBody LoginRequest input,
            HttpServletRequest request,
            HttpServletResponse response) {

        Authentication verified;
        try {
            verified = authManager.authenticate(
                    UsernamePasswordAuthenticationToken
                            .unauthenticated(
                                    input.username(), input.password()));
        } catch (AuthenticationException failure) {
            // Thông điệp public không phân biệt user không tồn tại,
            // password sai hay account status. Không log secret.
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .header(HttpHeaders.CACHE_CONTROL, "no-store")
                    .body(Map.of("error", "invalid_credentials"));
        }

        // Chỉ tạo principal riêng sau xác thực. Demo có duy nhất alice.
        // Sản phẩm thật tra id/tenant từ account directory đáng tin.
        if (!"alice".equals(verified.getName())) {
            throw new IllegalStateException(
                    "Authenticated account mapping unavailable");
        }

        AppPrincipal principal = new AppPrincipal(
                "user-100", "alice", "tenant-a");

        Authentication forSession =
                UsernamePasswordAuthenticationToken.authenticated(
                        principal, null, verified.getAuthorities());

        // Chống session fixation và thay CSRF token cũ.
        sessionStrategy.onAuthentication(
                forSession, request, response);

        // Spring Security 6: tạo context mới và LƯU tường minh.
        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(forSession);
        SecurityContextHolder.setContext(context);
        contextRepository.saveContext(context, request, response);

        return ResponseEntity.ok()
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(new UserView(
                        principal.userId(),
                        principal.username(),
                        principal.tenantId()));
    }

    @GetMapping("/me")
    public ResponseEntity<UserView> me(Authentication authentication) {
        AppPrincipal principal =
                (AppPrincipal) authentication.getPrincipal();

        return ResponseEntity.ok()
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(new UserView(
                        principal.userId(),
                        principal.username(),
                        principal.tenantId()));
    }
}
```

**Giải thích hoạt động:**

- `LoginRequest` chỉ chứa username/password do client cung cấp; **không có role, tenant, user ID từ client**. `@Valid` và `@NotBlank` giúp loại input rỗng; production còn cần giới hạn body/request size ở reverse proxy và xử lý JSON malformed qua global error handler.
- `authManager.authenticate(...)` là nơi `DaoAuthenticationProvider` gọi password encoder. Chỉ khi phương thức này thành công mới dựng `AppPrincipal`.
- `UsernamePasswordAuthenticationToken.authenticated(principal, null, authorities)` giữ principal **không có password** trong session; authorities đến từ provider xác thực, không đến từ input JSON.
- `sessionStrategy.onAuthentication(...)` xảy ra **trước** `saveContext`, nên ID phiên được thay đổi trước khi ghi trạng thái xác thực.
- `SecurityContextHolder.createEmptyContext()` tránh sửa một context cũ dùng chung. `setContext` phục vụ phần còn lại của current request; `saveContext` là phần quyết định persistence giữa requests.
- `/api/me` nhận `Authentication` đã được SecurityFilterChain đưa vào request. Nếu không đăng nhập, request bị từ chối trước khi controller chạy.
- Sau login, CSRF token đã bị invalidated bởi `CsrfAuthenticationStrategy`; client nên gọi lại `/api/auth/csrf` trước thao tác ghi tiếp theo.
- `Map.of` và DTO được Jackson serialize thành JSON; thứ tự thuộc tính JSON không được đảm bảo và không nên được test theo chuỗi cứng.

### Không làm theo shortcut này

```java
// Sai ý tưởng: chỉ xác thực trong controller, không lưu session.
Authentication a = authManager.authenticate(inputToken);
SecurityContextHolder.getContext().setAuthentication(a);
return ResponseEntity.ok("logged in");
```

Đoạn này giả định có `authManager` và `inputToken`; nó không phải chương trình biên dịch riêng. Trên Spring Security 6 sử dụng explicit-save, request tiếp theo có thể không thấy authentication, và session fixation strategy có thể chưa chạy.

## 10. Vì sao logout nên dùng `LogoutFilter` thay vì tự xóa cookie?

Khi frontend gửi `POST /api/auth/logout`, Spring Security `LogoutFilter` xử lý trước MVC controller. Với cấu hình phần 8, logout flow bao gồm:

1. `CsrfFilter` xác thực token cho **POST**.
2. `LogoutFilter` nhận đúng endpoint/method logout.
3. `SecurityContextLogoutHandler` xóa authentication/context và invalidate session khi đã cấu hình.
4. `CsrfLogoutHandler` loại CSRF token liên quan đến phiên logout.
5. Cookie `JSESSIONID` được yêu cầu xóa với `deleteCookies`.
6. `LogoutSuccessHandler` trả HTTP **204 No Content**, không chuyển hướng tới HTML login page.

Không nên tạo:

```java
@GetMapping("/api/auth/logout")
public void logout() {
    // Chỉ xóa cookie phía client sẽ không thu hồi session ở server.
}
```

Một URL logout qua GET có thể bị kích hoạt bởi link/image/crawler hoặc hành vi ngoài ý muốn. Với cookie-based authentication, dùng **POST có CSRF token** giúp tránh tình huống cross-site ép người dùng logout. Nếu có SSO/OIDC hoặc refresh token phía server, logout còn cần xử lý token revoke/front-channel/back-channel phù hợp; xóa Spring session **không đồng nghĩa** đã đăng xuất khỏi toàn bộ identity provider.

Nếu dùng distributed session store, `invalidate()` phải xóa hoặc vô hiệu hóa record tương ứng. Nếu có nhiều session trên nhiều thiết bị, logout ở một thiết bị không tự đăng xuất tất cả thiết bị trừ khi có chính sách revoke-all.

## 11. Chạy ví dụ bằng Gradle và curl

Từ thư mục project có Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

### 11.1. Lấy CSRF token và cookie phiên

Dùng `curl` lưu cookie jar:

```bash
curl -i -c cookies.txt \
  http://127.0.0.1:8080/api/auth/csrf
```

Response JSON tương đương:

```json
{
  "headerName": "X-CSRF-TOKEN",
  "token": "<opaque-csrf-value>"
}
```

**`<opaque-csrf-value>` là ký hiệu minh họa**, không phải token thật. Mỗi lần GET có thể tạo giá trị token hiển thị khác do CSRF masking ở Spring Security 6. Đừng hardcode token trên ví dụ vào request sau; dùng **giá trị được server trả trong chính phiên cookie jar này**.

### 11.2. Đăng nhập JSON với đúng CSRF token

Giả sử biến `CSRF_TOKEN` đã được gán bằng trường `token` của JSON response vừa nhận, và cookie jar chứa phiên:

```bash
curl -i -b cookies.txt -c cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-TOKEN: $CSRF_TOKEN" \
  -d '{"username":"alice","password":"demo-only"}' \
  http://127.0.0.1:8080/api/auth/login
```

Kỳ vọng HTTP 200 với JSON tương đương:

```json
{
  "userId": "user-100",
  "username": "alice",
  "tenantId": "tenant-a"
}
```

Session ID có thể thay đổi khi login thành công; `curl -c cookies.txt` cập nhật cookie jar. Password `demo-only` chỉ là dữ liệu thử cho loopback; đừng dùng password thực trong command history. Cookie jar là dữ liệu nhạy cảm: hạn chế quyền truy cập và xóa sau thử nghiệm.

### 11.3. Gọi API dùng session

```bash
curl -i -b cookies.txt \
  http://127.0.0.1:8080/api/me
```

Mong đợi HTTP 200 với `userId/username/tenantId` như trên. Không có cookie phiên hợp lệ:

```bash
curl -i http://127.0.0.1:8080/api/me
```

Mong đợi HTTP **401 Unauthorized** với body JSON generic theo `AuthenticationEntryPoint` của demo. Nếu sai cookie nhưng controller vẫn được gọi, phải xem lại `SecurityFilterChain` và session repository.

### 11.4. Lấy CSRF token mới rồi POST logout

Vì login thành công làm mới CSRF state, hãy gọi lại:

```bash
curl -i -b cookies.txt -c cookies.txt \
  http://127.0.0.1:8080/api/auth/csrf
```

Gán `CSRF_TOKEN` bằng token **mới**, rồi:

```bash
curl -i -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $CSRF_TOKEN" \
  -X POST http://127.0.0.1:8080/api/auth/logout
```

Mong đợi **204 No Content**. Sau logout, phải kiểm tra session cũ không cấp quyền:

```bash
curl -i -b cookies.txt \
  http://127.0.0.1:8080/api/me
```

Mong đợi **401**. Kiểm thử bằng cookie jar có thể cập nhật/xóa cookie ở bước logout; để kiểm chứng thu hồi server-side, ở một bài test vận hành có kiểm soát hãy thử giữ **session ID cũ** trong client phụ và xác nhận nó cũng không còn hiệu lực. Không log hoặc chia sẻ session ID ra ngoài.

### 11.5. Kiểm tra nhánh lỗi

```bash
# Sai mật khẩu, nhưng có CSRF hợp lệ:
curl -i -b cookies.txt -c cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-TOKEN: $CSRF_TOKEN" \
  -d '{"username":"alice","password":"wrong"}' \
  http://127.0.0.1:8080/api/auth/login
```

Kỳ vọng 401 generic khi CSRF token còn hiệu lực. Nếu dùng token hết hạn hoặc không còn khớp session, request có thể bị chặn **403 bởi CSRF trước khi controller kiểm password**. Vì vậy trong chẩn đoán phải phân biệt CSRF failure với authentication failure, không tự kết luận mọi 403 là sai mật khẩu.

## 12. MockMvc integration test: cookie session, CSRF và logout

Tạo `src/test/java/demo/jsonsession/JsonSessionIntegrationTest.java`:

```java
package demo.jsonsession;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.http.MediaType;
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

@SpringBootTest
@AutoConfigureMockMvc
class JsonSessionIntegrationTest {

    @Autowired
    MockMvc mvc;

    private record CsrfSession(MockHttpSession session, String token) {}

    private CsrfSession bootstrap() throws Exception {
        MvcResult response = mvc.perform(get("/api/auth/csrf"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.headerName")
                        .value("X-CSRF-TOKEN"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) response.getRequest().getSession(false);
        String token = JsonPath.read(
                response.getResponse().getContentAsString(), "$.token");

        assertThat(session).isNotNull();
        assertThat(token).isNotBlank();
        return new CsrfSession(session, token);
    }

    private void login(CsrfSession csrf) throws Exception {
        mvc.perform(post("/api/auth/login")
                        .session(csrf.session())
                        .header("X-CSRF-TOKEN", csrf.token())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"alice","password":"demo-only"}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId")
                        .value("user-100"))
                .andExpect(jsonPath("$.tenantId")
                        .value("tenant-a"));
    }

    @Test
    void anonymousCannotReadCurrentPrincipal() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void loginWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"alice","password":"demo-only"}
                                """))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordDoesNotAuthenticateSession() throws Exception {
        CsrfSession csrf = bootstrap();

        mvc.perform(post("/api/auth/login")
                        .session(csrf.session())
                        .header("X-CSRF-TOKEN", csrf.token())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"alice","password":"wrong"}
                                """))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error")
                        .value("invalid_credentials"));

        mvc.perform(get("/api/me").session(csrf.session()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void loginRotatesIdAndPersistsCustomPrincipal() throws Exception {
        CsrfSession csrf = bootstrap();
        String oldId = csrf.session().getId();

        login(csrf);

        // Session fixation protection: ID của session cũ đổi.
        assertThat(csrf.session().getId()).isNotEqualTo(oldId);

        mvc.perform(get("/api/me").session(csrf.session()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId")
                        .value("user-100"))
                .andExpect(jsonPath("$.username")
                        .value("alice"))
                .andExpect(jsonPath("$.tenantId")
                        .value("tenant-a"));

        // Request khác không có cookie không thừa hưởng principal.
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void logoutMustHaveFreshCsrfAndInvalidatesSession()
            throws Exception {
        CsrfSession original = bootstrap();
        login(original);

        // Token trước login đã bị CsrfAuthenticationStrategy xóa.
        mvc.perform(post("/api/auth/logout")
                        .session(original.session())
                        .header("X-CSRF-TOKEN", original.token()))
                .andExpect(status().isForbidden());

        // Lấy token mới từ chính session sau login.
        MvcResult fresh = mvc.perform(
                        get("/api/auth/csrf")
                                .session(original.session()))
                .andExpect(status().isOk())
                .andReturn();
        String freshToken = JsonPath.read(
                fresh.getResponse().getContentAsString(), "$.token");

        mvc.perform(post("/api/auth/logout")
                        .session(original.session())
                        .header("X-CSRF-TOKEN", freshToken))
                .andExpect(status().isNoContent());

        assertThat(original.session().isInvalid()).isTrue();

        // Sau logout, một request mới không được xác thực.
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }
}
```

Các test này kiểm tra một số bất biến quan trọng:

1. Anonymous không được đọc `/api/me`.
2. POST login thiếu CSRF token bị từ chối **trước khi xác thực credential**.
3. Sai password với CSRF hợp lệ trả 401; không tạo session đã xác thực.
4. Đăng nhập thành công đổi session ID, lưu **principal riêng** vào context.
5. Request riêng không mang session không thừa hưởng authentication.
6. Token CSRF trước login không được tái dùng để logout sau login.
7. POST logout với token mới trả 204, invalidate phiên và request tiếp theo không còn được xác thực.

`MockMvc` có thể kiểm tra `MockHttpSession` nhưng không chứng minh cookie attributes trên trình duyệt thật, reverse proxy HTTPS, load balancer hay distributed session store. Cần thêm E2E tests ở môi trường triển khai.

Chạy:

```bash
./gradlew test
```

Ví dụ không khẳng định stdout cố định của Gradle; kết quả cần là **mọi JUnit/MockMvc test pass**. Khi lỗi, xem HTTP status và stack trace test trong môi trường kiểm soát, không tắt CSRF hoặc session fixation chỉ để làm test xanh.

## 13. JavaScript `fetch` cùng origin: không giữ mật khẩu trong storage

Frontend cùng origin có thể sử dụng `fetch`:

```javascript
async function csrfToken() {
  const response = await fetch("/api/auth/csrf", {
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!response.ok) throw new Error("Cannot get CSRF token");
  return response.json();
}

async function signIn(username, password) {
  const csrf = await csrfToken();
  const response = await fetch("/api/auth/login", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify({ username, password })
  });
  if (!response.ok) throw new Error("Login failed");
  return response.json();
}

async function signOut() {
  const csrf = await csrfToken();
  const response = await fetch("/api/auth/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: { [csrf.headerName]: csrf.token }
  });
  if (response.status !== 204) throw new Error("Logout failed");
}

// Đăng nhập cần gọi signIn(...) với dữ liệu form người dùng.
// Khi login xong, lấy token CSRF mới trước request ghi dữ liệu.
```

Đây là **module JavaScript dùng trong frontend cùng origin**, không chạy độc lập bằng Node. Các hàm ví dụ không lưu password vào `localStorage`, `sessionStorage` hoặc URL. Nếu UI có nhiều tab, mọi tab thường chia sẻ cookie session và cần xử lý logout/rotation state cùng nhau.

Không phải mọi API cross-origin nên dùng `credentials: "include"`; việc cho phép cookie cross-site cần phân tích SameSite, CSRF, CORS và domain, và không thể sửa bằng cách mở `Access-Control-Allow-Origin: *` cùng credentials.

**CSRF token là dữ liệu gắn với phiên:** nếu bạn giữ token cũ sau login/logout, request POST tiếp theo có thể bị 403. Nên bootstrap token mới sau authentication transition, và xử lý lỗi CSRF expiration bằng flow hợp lệ thay vì tự tắt validation.

## 14. `SecurityContextHolder` và lưu context giữa hai request

Trong Spring Security 6, `SecurityContextHolderFilter` có xu hướng **load** context từ repository và để app/filter chịu trách nhiệm **save** khi chủ động thay đổi authentication. Với login tự viết:

```java
SecurityContext newContext =
        SecurityContextHolder.createEmptyContext();
newContext.setAuthentication(authenticated);
SecurityContextHolder.setContext(newContext);
repository.saveContext(newContext, request, response);
```

Đây là **snippet** giả định các biến đã được tạo đúng kiểu, không phải một method Java độc lập.

Ba hành động khác nhau:

- `createEmptyContext()` bảo đảm có context mới, không vô tình thao tác trên object context cũ.
- `setContext(...)` cho phép các logic phía sau trong request hiện tại đọc authentication.
- `saveContext(...)` là thao tác đưa context vào repository để request kế tiếp dùng được.

`HttpSessionSecurityContextRepository` mặc định dùng một attribute do Spring Security quản lý trong `HttpSession`; **không tự đặt `session.setAttribute("user", ...)` rồi kỳ vọng Spring Security coi đó là đã authenticated**.

Không nên tự lưu nguyên `Authentication` vào một biến `static` hoặc `ThreadLocal` toàn cục. Trong servlet server, thread pool được tái sử dụng giữa user khác nhau; rò `SecurityContextHolder` giữa requests có thể gây cấp quyền nhầm.

Nếu dùng nhiều `SecurityFilterChain`, login endpoint và endpoint cần session phải được xử lý bởi chain/repository nhất quán. Một chain `STATELESS` cho `/api/**` có thể khiến login session không được đọc về sau, dù controller đã `saveContext`.

## 15. Session fixation: vì sao đổi ID khi login?

**Session fixation** xảy ra khi attacker tạo/biết một session ID chưa được xác thực và tìm cách khiến nạn nhân tiếp tục dùng cùng ID sau khi đăng nhập. Khi attacker còn biết ID ấy, họ có thể mạo danh nạn nhân nếu session được nâng cấp mà không đổi ID.

Ví dụ:

```text
Trước login:
  JSESSIONID = SID-OLD    (chưa xác thực)
                        |
                        v
Đăng nhập thành công:
  SessionAuthenticationStrategy đổi session ID
                        |
                        v
Sau login:
  JSESSIONID = SID-NEW    (có SecurityContext)
```

`ChangeSessionIdAuthenticationStrategy` gọi cơ chế đổi session ID của Servlet container khi có session hiện tại. Việc sử dụng `HttpSessionCsrfTokenRepository` khiến GET CSRF tạo một anonymous session, giúp test có thể quan sát session ID thay đổi sau login.

Đổi ID **không thay thế** kiểm soát cookie `Secure`, `HttpOnly`, SameSite, HTTPS, session expiration và audit. Nếu cookie bị đánh cắp sau login, attacker vẫn có thể thực hiện session hijacking; cần thêm bảo vệ transport, browser và server.

Nếu có yêu cầu đặc biệt về session concurrency, Spring Security cung cấp các chiến lược kiểm soát số session và `SessionRegistry`. Controller tự viết cần đảm bảo các chiến lược đó thực sự được gọi; chỉ `ChangeSessionIdAuthenticationStrategy` chưa xử lý được “chỉ một thiết bị đăng nhập” hay logout toàn cục.

## 16. CSRF cho cả login và logout

Một sai lầm phổ biến:

```java
http.csrf(csrf -> csrf.disable());
```

Cấu hình trên tắt CSRF cho toàn chuỗi, không phù hợp với sản phẩm **dùng cookie được browser tự gửi** nếu endpoint có side effect. Tương tự, miễn trừ `/api/auth/login` và `/api/auth/logout` mà không phân tích rủi ro có thể tạo lỗ hổng **login CSRF** hoặc **logout CSRF**.

Vì sao login cũng cần CSRF? Một website khác có thể cố gửi request khiến trình duyệt nạn nhân bị đăng nhập vào một tài khoản do attacker kiểm soát; sau đó hành vi của nạn nhân diễn ra trong account không mong muốn. CSRF token giúp đảm bảo flow login được khởi tạo trong đúng phiên/client được phép.

Vì sao logout cũng cần CSRF? Một request GET hoặc POST không kiểm CSRF có thể bị ép gửi từ trang khác, gây logout ngoài ý muốn. Chỉ có HTTP method POST **chưa đủ** chống CSRF nếu không có token/same-origin policy phù hợp.

Spring Security 6 có thể dùng **deferred CSRF tokens và BREACH masking** trong request attributes. Bởi vậy token `getToken()` trả cho client có thể không trùng chuỗi raw được lưu trong session. Client phải gửi **giá trị được server trả**, không tự decode/mutate token.

Khi authentication thành công, `CsrfAuthenticationStrategy` thay đổi/loại token hiện hành; khi logout, `CsrfLogoutHandler` cũng xử lý token. Việc frontend phải bootstrap token sau đổi trạng thái là thiết kế có chủ đích.

## 17. Trả 401, 403 và lỗi JSON an toàn

Trong demo:

| Tình huống | Status kỳ vọng | Nguyên nhân |
| --- | --- | --- |
| Anonymous `GET /api/me` | `401` | Không có authenticated session |
| POST login thiếu CSRF | `403` | `CsrfFilter` chặn trước MVC controller |
| POST login CSRF đúng, password sai | `401` | `AuthenticationManager` từ chối credential |
| POST login đúng | `200` | Đã đổi session ID và lưu context |
| GET `/api/me` với session đúng | `200` | Principal lấy từ saved context |
| POST logout CSRF cũ hoặc thiếu | `403` | Không được thực thi logout |
| POST logout CSRF hợp lệ | `204` | Session invalidated |
| GET `/api/me` sau logout | `401` | Không còn phiên xác thực |
| User đã login nhưng thiếu quyền resource | Thường `403` | Authorization thất bại, khác lỗi login |

Status là hợp đồng của cấu hình bài demo. Một hệ thống form login, API gateway hoặc custom handler có thể trả khác. **Không tiết lộ trong public response** rằng username không tồn tại, account bị khóa, password sai cụ thể hoặc user có tenant nào; ví dụ login trả cùng `invalid_credentials` cho các lỗi `AuthenticationException`.

Lỗi hệ thống như database không khả dụng cần được ghi nhận và phân loại nội bộ để không đánh đồng với người dùng nhập sai. Khi thiết kế production, có thể trả một lỗi hệ thống generic `503` cho outage thật mà không tiết lộ cấu trúc provider; nên có correlation ID/audit riêng.

Không log `@RequestBody LoginRequest` bằng cách in `toString()`: record mặc định có thể chứa password. Ví dụ đã override `toString()` để redacted, nhưng vẫn cần kiểm soát request body logging ở reverse proxy, APM và controller interceptor.

## 18. Cookie security: `HttpOnly`, `Secure`, `SameSite` và HTTPS

`JSESSIONID` là một **bearer credential dạng cookie**: ai sở hữu cookie hợp lệ có thể sử dụng phiên server nếu không có biện pháp bổ trợ.

Các thuộc tính:

- **`HttpOnly`**: JavaScript không thể đọc cookie qua `document.cookie` thông thường; không ngăn XSS tự phát request cùng origin.
- **`Secure`**: browser chỉ gửi cookie qua HTTPS theo policy (ngoại lệ browser/localhost có thể khác). Production phải dùng HTTPS.
- **`SameSite=Lax`**: hạn chế một số cross-site cookie request; không thay thế CSRF token, nhất là với cùng site khác origin hoặc edge cases.
- **`SameSite=Strict`**: chặt hơn nhưng có thể ảnh hưởng OAuth2 redirect/login link từ site khác.
- **Domain/Path**: giới hạn nơi cookie được gửi; đừng mở domain quá rộng để tiện dùng nhiều subdomain.

Production cùng một trusted TLS proxy có thể cấu hình:

```yaml
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
  forward-headers-strategy: framework
```

Đây là nội dung minh họa cho `application-prod.yml`; chỉ bật xử lý forwarded headers nếu **backend chỉ nhận dữ liệu từ reverse proxy đã được chỉ định** và proxy sanitize `Forwarded`/`X-Forwarded-*`. Nếu backend public, client có thể giả metadata HTTPS/host. Khi deploy production, phải cấu hình lại `server.address`/network topology thích hợp thay vì giữ `127.0.0.1` khi service nằm ở máy/container khác.

Không trả `JSESSIONID` bằng JSON để “frontend tự quản lý”; để browser cookie jar xử lý cookie đúng policy. `HttpOnly` có chủ đích ngăn JavaScript đọc session credential.

## 19. Dữ liệu principal riêng, session stale và quyền nhiều tenant

Trong demo:

```text
AppPrincipal:
  userId   = user-100
  username = alice
  tenantId = tenant-a

Authentication authorities:
  ROLE_USER
```

Các giá trị ID/tenant là dữ liệu sau xác thực từ account directory tin cậy. Trong ứng dụng nhiều tenant, service vẫn phải kiểm tra **resource ownership**, ví dụ report thuộc tenant `tenant-a`, thay vì chỉ nhìn `ROLE_USER`.

Một vấn đề vận hành: `SecurityContext` trong session có thể giữ authorities/tenant **ở thời điểm login**, trong khi admin đã khóa user hoặc thu hồi quyền sau đó. Cần chính sách:

1. Session timeout và absolute max age.
2. Invalidate sessions khi khóa user, đổi password hoặc reset MFA khi policy yêu cầu.
3. Revalidate quyền nhạy cảm ở thời điểm đọc/ghi dữ liệu.
4. Cân nhắc `SessionRegistry` hoặc session store để revoke theo user.
5. Không dùng `tenantId` trong request body để thay tenant thực tế nếu chưa kiểm quyền chuyển tenant.
6. Với session distributed, kiểm version và serialization compatibility của `AppPrincipal`.

Một JWT chứa claims cũng có vấn đề stale tương tự cho tới khi hết hạn/revoke; session không tự giải quyết mọi thay đổi quyền.

## 20. Những lỗi thường gặp khi tự viết đăng nhập JSON

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Login 200 nhưng `/api/me` 401 | Chỉ `setContext`, không `saveContext`, hoặc chain dùng `STATELESS` | Dùng session repository nhất quán và lưu context tường minh |
| Login 403 mặc dù password đúng | Chưa lấy/gửi CSRF token cùng session | GET CSRF, gửi header chính xác và giữ cookie |
| Logout 403 sau khi vừa login | Token CSRF trước login đã bị reset | Bootstrap token mới từ session đã xác thực |
| User A và B bị trộn context | Tự lưu auth trong static/ThreadLocal hoặc shared session | Dùng `SecurityContextRepository` per session, không dùng global |
| ID session không đổi sau login | Bỏ qua `SessionAuthenticationStrategy` | Gọi change-session-ID strategy sau auth thành công |
| Logout trả 204 nhưng session còn dùng được | Chỉ xóa cookie hoặc không invalidate server session | Dùng `LogoutFilter`/`SecurityContextLogoutHandler` và test session invalid |
| Login response lộ password/hash | Serialize nguyên `UserDetails` hoặc record request | Trả DTO tối thiểu, che log |
| Client tự nhận `ROLE_ADMIN` | Tin role trong JSON | Authorities từ provider/account store đáng tin |
| Cookie bị gửi qua HTTP | Thiếu HTTPS/`Secure` hoặc proxy cấu hình sai | HSTS/TLS/Secure cookie và trust boundary đúng |
| Session mất giữa các replicas | Session lưu local, LB chuyển node | Spring Session/shared store hoặc sticky routing có chính sách |
| UI không đăng xuất được trên tab khác | Cookie/session chung nhưng frontend giữ state cũ | Recheck `/api/me`, broadcast logout trong same-origin UI |
| 401 cho user bị vô hiệu hóa sau khi login cũ | Session chưa bị revoke khi trạng thái user thay đổi | Session invalidation/revalidation theo account lifecycle |
| Login liên tục bị brute-force | Chưa rate-limit/account lock/monitor | Giới hạn theo account/IP với policy không gây DoS |
| Login bị sai do JSON malformed | Controller không xử lý validation/body error | `@Valid`, 400 generic, body size limit |
| POST logout không vào controller | LogoutFilter xử lý URL trước MVC | Đây là thiết kế chủ đích; test qua filter chain |
| CSRF vẫn lỗi dù CORS đúng | CORS không thay CSRF | Giữ token cùng session và cấu hình origin policy phù hợp |

### Debug theo thứ tự

1. Xác nhận request match đúng `SecurityFilterChain` và method.
2. Kiểm tra POST login có cùng cookie session và header CSRF từ GET bootstrap không.
3. Kiểm tra `AuthenticationManager` thực sự dùng provider/password encoder nào.
4. Kiểm tra account directory đã xác minh principal ID/tenant chưa.
5. Kiểm tra session fixation strategy có thực sự đổi ID không.
6. Kiểm tra `HttpSessionSecurityContextRepository.saveContext` đã chạy.
7. Kiểm tra GET `/api/me` mang cookie mới và đúng session repository không.
8. Kiểm tra POST logout có CSRF token **sau login** và session bị invalidate.
9. Kiểm tra HTTPS, cookie path/domain/SameSite và reverse proxy.
10. Kiểm tra session timeout, revocation, concurrent logins và event audit.

## 21. Trường hợp thực tế: session concurrency và nhiều thiết bị

Ví dụ user đăng nhập trên laptop và điện thoại; mỗi thiết bị thường có session ID khác nhau. Logout ở laptop chỉ invalidate session của laptop nếu không có cơ chế revoke-all; session điện thoại vẫn có thể hoạt động.

Nếu yêu cầu **“chỉ một phiên cho mỗi user”**, Spring Security có cơ chế concurrent session control nhưng controller tự viết phải tích hợp đầy đủ:

- `ConcurrentSessionControlAuthenticationStrategy`
- `RegisterSessionAuthenticationStrategy`
- `SessionRegistry` hoặc repository theo dõi phiên
- `ConcurrentSessionFilter` / integration hỗ trợ session lifecycle phù hợp

Đừng chỉ thêm một `SessionRegistry` bean rồi tin rằng session cũ tự hết hiệu lực. Mô hình principal equality/hashCode và distributed session storage cũng ảnh hưởng tracking. Nếu user bị vô hiệu hóa, ứng dụng cần chính sách revoke tất cả sessions theo user ID thay vì chờ cookie hết hạn.

Khi dùng Spring Session với Redis/JDBC, đòi hỏi timeout, cleanup, session ID rotation, serialization, GDPR/PII policy và vận hành store. Đây là **phần mở rộng**, không có trong demo một user một process; không nên tuyên bố demo sẵn sàng production.

## 22. CORS và same-origin: thiết kế API dùng cookie

Frontend same-origin gọi:

```text
https://app.example.test/
https://app.example.test/api/auth/csrf
https://app.example.test/api/auth/login
https://app.example.test/api/me
https://app.example.test/api/auth/logout
```

có chính sách cookie/CSRF đơn giản hơn frontend ở origin khác. Nếu tách frontend sang domain khác, cần cấu hình CORS với allowlist origin cụ thể, `Access-Control-Allow-Credentials` thích hợp, `SameSite=None; Secure` khi thực sự cross-site và CSRF vẫn phải được đánh giá cẩn thận.

**Không** đặt `Access-Control-Allow-Origin: *` cùng credential và mong browser chấp nhận. Cũng không nhầm HTTP `Origin`/`Referer` hoặc CORS với authentication; browser policy không ngăn attacker gửi request bằng công cụ khác.

Login/logout session APIs có thể trở thành mục tiêu CSRF dù mọi request đều là JSON. Một số request cross-origin JSON bị preflight, nhưng **chỉ dựa vào preflight/CORS không thay thế CSRF token** và không xử lý tốt mọi biến thể/content type/proxy.

## 23. Tests nên bổ sung khi chuyển sang production

MockMvc demo kiểm các bất biến lõi. Ở hệ thống thật cần thêm kiểm thử:

1. **Tài khoản không tồn tại, bị khóa, disabled, password expired:** public response generic và không tạo authenticated session.
2. **Malformed JSON / body quá lớn / content type sai:** trả 400/413/415 theo contract, không stack trace.
3. **Brute force/rate-limit:** nhiều lần login sai bị hạn chế, event audit không tiết lộ password.
4. **Session fixation bằng browser thật:** session ID sau auth khác trước auth, cookie Path/Domain/Secure/HttpOnly/SameSite đúng.
5. **Session timeout và logout:** session ID cũ sau invalidate không truy cập được dù giữ cookie cũ.
6. **Race login/logout từ nhiều tab:** không tái sử dụng CSRF token cũ hoặc hồi sinh context.
7. **Multi-tenant isolation:** user không thể truy cập resource của tenant khác bằng cách đổi ID path.
8. **Distributed session:** request qua các replicas còn auth đúng, revoke hiệu lực, không rò context.
9. **User disabled giữa phiên:** session được revoke/revalidate theo policy thực tế.
10. **XSS và CSRF:** session cookie HttpOnly không loại trừ XSS-driven requests; kiểm CSP/output encoding/anti-CSRF.
11. **HTTPS / proxy:** không có direct HTTP bypass, cookie Secure và redirect đúng public host.
12. **Login/logout audit:** có correlation ID, outcome/actor nhưng không log secret/CSRF token/cookie.

Một test dùng `.with(user("alice"))` chỉ **gắn sẵn principal**; không kiểm session persistence hoặc password. Dùng request đăng nhập JSON thực sự như phần 12 để kiểm tra flow cần thiết.

## 24. Checklist triển khai

- SecurityFilterChain bao phủ login, CSRF bootstrap, authenticated API và logout, có fallback policy.
- JSON login thực sự gọi `AuthenticationManager`, provider có password encoder phù hợp.
- Principal chứa dữ liệu backend đã xác minh, không chứa raw secret.
- Login success gọi session authentication strategy, đổi session ID.
- CSRF token được cấp cho đúng phiên, được gửi ở POST login/logout, được rotate sau authentication.
- SecurityContext tạo mới, `setContext` và `saveContext` cùng session repository.
- Endpoint `/api/me` lấy authentication từ stored SecurityContext thay vì tự đọc session attribute tùy ý.
- Logout thông qua `LogoutFilter` bằng POST và invalidates server-side session.
- Cookie `Secure`, `HttpOnly`, `SameSite`, domain/path và HTTPS được thiết kế cho browser thật.
- Public errors generic; không phân biệt user existence hoặc lộ credentials.
- Có rate limiting, session timeout, revocation và audit theo product requirements.
- Role/tenant authorization kiểm ở backend, kể cả khi session principal đã chứa tenant.
- Có MockMvc tests cho CSRF, wrong credentials, session fixation, session persistence và logout.
- Với nhiều replicas, có session store/consistency và strategy phù hợp.
- Với SSO/OIDC, logout app/session và logout identity provider được thiết kế riêng.

## Ghi nhớ

**Đăng nhập JSON dùng phiên trong Spring Security Servlet** không đơn thuần là parse JSON rồi gọi `AuthenticationManager.authenticate`. Một flow an toàn phải **xác thực credential**, dựng **principal riêng từ dữ liệu backend đáng tin**, **đổi session ID**, **lưu `SecurityContext` tường minh vào session**, **giữ CSRF bật cho login/logout**, và **invalidate session khi đăng xuất**. Dùng JSON response DTO tối thiểu và cookie `HttpOnly`/`Secure` qua HTTPS. Khi chạy trong production, bổ sung account lifecycle, concurrency/revocation, rate limiting, audit và E2E kiểm thử cookie/proxy trên browser thật.