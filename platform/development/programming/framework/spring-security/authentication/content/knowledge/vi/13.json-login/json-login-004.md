# Xác thực qua AuthenticationManager thay vì tự so sánh mật khẩu trong Controller

> **Phạm vi:** Đăng nhập JSON trong **Spring Security Servlet 6.x**, minh họa bằng Spring Boot 3.3.5 và Java 17+. Đề bài chính là xây một endpoint nhận `username/password` qua JSON, gọi `AuthenticationManager.authenticate(...)` và xử lý thành công/thất bại đúng cách; phần session và CSRF giải thích điều kiện để đăng nhập thật sự tồn tại giữa nhiều HTTP request.

## 1. Tại sao không tự kiểm tra password trong Controller?

Một client gửi:

```http
POST /api/login HTTP/1.1
Content-Type: application/json

{"username":"alice","password":"secret123"}
```

**Phản ví dụ sai**, chỉ minh họa logic cần tránh, không phải mã Java độc lập:

```java
UserRecord user = userRepository.findByUsername(body.username());
if (user != null && user.password().equals(body.password())) {
    return "login success";
}
return "login failed";
```

Đoạn này vừa dễ dẫn tới lưu password plaintext, vừa bỏ qua các lớp bảo vệ mà Spring Security cung cấp. Mật khẩu phải lưu dưới dạng hash thích hợp (ví dụ BCrypt có salt), không dùng `equals` với raw password. Ngay cả khi tự gọi `passwordEncoder.matches(raw, hash)` trong Controller, ta vẫn có thể bỏ sót account disabled/locked/expired, logic của nhiều `AuthenticationProvider`, sự kiện xác thực và chuẩn hóa lỗi. Trả chuỗi `"login success"` cũng **không tạo** một `Authentication` đã xác thực trong `SecurityContext`.

Mục tiêu là phân vai rõ ràng:

| Thành phần | Vai trò chính |
| --- | --- |
| `@RestController` | Nhận JSON, kiểm tra input bắt buộc, tạo token yêu cầu, gọi manager và chọn HTTP response |
| `UsernamePasswordAuthenticationToken.unauthenticated(...)` | Gói username/password dưới dạng một `Authentication` **chưa xác thực** |
| `AuthenticationManager` | API xác thực credential; trả `Authentication` thành công hoặc ném `AuthenticationException` |
| `ProviderManager` | Triển khai manager thường dùng, lần lượt ủy quyền cho provider hỗ trợ token |
| `DaoAuthenticationProvider` | Lấy `UserDetails` và kiểm tra password bằng `PasswordEncoder.matches(...)`, xét trạng thái tài khoản |
| `SecurityContextHolder` | Giữ context và danh tính hiện tại trong request |
| `SecurityContextRepository` | Lưu/khôi phục danh tính qua các request nếu dùng session |
| `SessionAuthenticationStrategy` | Thực hiện bảo vệ phiên sau login, ví dụ đổi session ID, xoay CSRF token |
| `AuthorizationFilter` | Kiểm tra quyền truy cập dựa trên `Authentication` và authority |

Đừng để client gửi authority/role tùy ý trong JSON rồi tin rằng đó là quyền thực. Role phải được server lấy từ nguồn dữ liệu đã kiểm chứng.

## 2. AuthenticationManager thực sự được gọi ra sao?

```text
Client POST /api/login + JSON (+ cookie và CSRF token khi dùng session)
  |
  v
Servlet SecurityFilterChain
  |-- CsrfFilter bảo vệ POST
  |-- AuthorizationFilter cho /api/login: permitAll
  v
AuthController.login(LoginRequest)
  |
  |-- UsernamePasswordAuthenticationToken.unauthenticated(username, password)
  |-- AuthenticationManager.authenticate(requestToken)
  |     |
  |     v
  |     ProviderManager
  |        -> DaoAuthenticationProvider
  |              -> UserDetailsService.loadUserByUsername(username)
  |              -> PasswordEncoder.matches(rawPassword, storedHash)
  |              -> kiểm tra account flags và lấy authorities
  |        <- Authentication đã xác thực
  |
  |-- thất bại: AuthenticationException -> phản hồi HTTP 401 chung
  |
  |-- thành công:
        SessionAuthenticationStrategy.onAuthentication(...)
        SecurityContext context = SecurityContextHolder.createEmptyContext()
        context.setAuthentication(authenticated)
        SecurityContextHolder.setContext(context)
        SecurityContextRepository.saveContext(context, request, response)
        -> phản hồi HTTP 200 JSON (không chứa password)
  |
  v
Client lưu cookie session mới
  | GET /api/me + cookie
  v
SecurityContextRepository khôi phục context từ session
  -> AuthorizationFilter cho phép /api/me
  -> Controller trả thông tin danh tính
```

### 2.1. Token đưa vào manager chưa được xác thực

Trong Controller:

```java
Authentication requestToken =
        UsernamePasswordAuthenticationToken.unauthenticated(
                loginRequest.username(), loginRequest.password());

Authentication authenticated = authenticationManager.authenticate(requestToken);
```

Đây là đoạn trích trong method, không phải `main` chạy độc lập. `requestToken.isAuthenticated()` ban đầu là `false`. Khi thành công, manager thường trả token có `isAuthenticated() == true`, `principal` đã xác minh và các `GrantedAuthority`. **Không tự dùng** `UsernamePasswordAuthenticationToken.authenticated(...)` cho dữ liệu client gửi đến.

`AuthenticationManager.authenticate(Authentication)` **không trả boolean**. Nó trả `Authentication` thành công hoặc ném ngoại lệ như `BadCredentialsException`, `DisabledException`, `LockedException`. Không trả exception message nguyên gốc ra client; phản hồi 401 chung giảm khả năng liệt kê username.

### 2.2. Provider, UserDetailsService và PasswordEncoder

Với username/password, `ProviderManager` tìm provider phù hợp cho `UsernamePasswordAuthenticationToken`. `DaoAuthenticationProvider` tải `UserDetails` từ `UserDetailsService`, sau đó `PasswordEncoder.matches(rawPassword, storedHash)` xác minh password. Provider còn kiểm tra trạng thái enabled, non-locked, non-expired và credentials non-expired theo cơ chế Spring Security.

Ví dụ BCrypt: `encode("secret123")` có thể cho hash khác nhau ở mỗi lần gọi vì salt. Không dùng `encode(raw).equals(storedHash)`; dùng `matches(raw, storedHash)`. Khi chuyển sang database, LDAP hoặc provider khác, Controller vẫn làm việc với giao diện `AuthenticationManager`, không cần tự biết cách lưu hash.

### 2.3. Manager xác thực xong vẫn chưa tự đăng nhập bằng session

Nếu controller trực tiếp gọi manager, **chính controller phải đặt và lưu context**. Trong Spring Security 6, `SecurityContextHolderFilter` chủ yếu tải context; không tự ghi mọi thay đổi của controller vào session. Cần:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, servletRequest, servletResponse);
```

`SecurityContextHolder.setContext` có tác dụng trong request hiện tại; `saveContext` dùng repository để giữ context cho request sau. Filter chain và controller phải dùng cùng `SecurityContextRepository`.

Khi tự làm JSON login, ta cũng phải xem xét những việc authentication filter chuẩn vốn thực hiện: đổi session ID để chống **session fixation**, làm mới CSRF token và xử lý logout. Ví dụ runnable bên dưới minh họa session strategy tường minh.

## 3. Ví dụ hoàn chỉnh: JSON login + session + CSRF

Công nghệ: Spring Boot **3.3.5**, Java **17+**, Maven **3.9+**, Spring Security 6.x. Demo có user `alice` / password `secret123` / authority `ROLE_READER`. Password chỉ phục vụ ví dụ, được BCrypt-hash khi ứng dụng khởi động. Ứng dụng thực phải dùng HTTPS và nguồn user/secret an toàn.

Các endpoint:

| Endpoint | Vai trò | Kết quả thành công |
| --- | --- | --- |
| `GET /api/csrf` | Lấy CSRF token để client gửi trên POST | 200 JSON |
| `POST /api/login` | JSON username/password → manager → lưu session | 200 JSON |
| `GET /api/me` | Đọc danh tính từ SecurityContext đã lưu | 200 JSON |
| `POST /api/logout` | Logout do Spring Security `LogoutFilter` xử lý | 204 |

Cấu trúc thư mục:

```text
json-login-demo/
├── pom.xml
├── src/main/java/com/example/jsonlogin/JsonLoginApplication.java
└── src/test/java/com/example/jsonlogin/JsonLoginApplicationTests.java
```

### 3.1. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>json-login-demo</artifactId>
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

### 3.2. src/main/java/com/example/jsonlogin/JsonLoginApplication.java

```java
package com.example.jsonlogin;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
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

import java.util.List;

@SpringBootApplication
public class JsonLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonLoginApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("secret123"))
                .roles("READER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityContextRepository contextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy(
            CsrfTokenRepository csrfTokens) {
        return new CompositeSessionAuthenticationStrategy(List.of(
                new ChangeSessionIdAuthenticationStrategy(),
                new CsrfAuthenticationStrategy(csrfTokens)
        ));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository contextRepo,
            CsrfTokenRepository csrfTokens) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/csrf", "/api/login").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .securityContext(sc -> sc.securityContextRepository(contextRepo))
            .csrf(csrf -> csrf.csrfTokenRepository(csrfTokens))
            .exceptionHandling(ex -> ex.authenticationEntryPoint(
                (request, response, exception) ->
                    response.sendError(HttpServletResponse.SC_UNAUTHORIZED)
            ))
            .logout(logout -> logout
                .logoutUrl("/api/logout")
                .logoutSuccessHandler((request, response, auth) ->
                    response.setStatus(HttpServletResponse.SC_NO_CONTENT)
                )
            );

        return http.build();
    }

    public record LoginRequest(String username, String password) {}
    public record LoginResponse(String username, List<String> authorities) {}
    public record ErrorResponse(String message) {}

    @RestController
    public static class AuthController {
        private final AuthenticationManager authenticationManager;
        private final SecurityContextRepository contextRepository;
        private final SessionAuthenticationStrategy sessionStrategy;

        public AuthController(
                AuthenticationManager authenticationManager,
                SecurityContextRepository contextRepository,
                SessionAuthenticationStrategy sessionStrategy) {
            this.authenticationManager = authenticationManager;
            this.contextRepository = contextRepository;
            this.sessionStrategy = sessionStrategy;
        }

        @GetMapping("/api/csrf")
        public CsrfToken csrf(CsrfToken token) {
            return token;
        }

        @PostMapping("/api/login")
        public ResponseEntity<?> login(
                @RequestBody LoginRequest body,
                HttpServletRequest request,
                HttpServletResponse response) {

            if (body == null || body.username() == null || body.password() == null
                    || body.username().isBlank() || body.password().isBlank()) {
                return ResponseEntity.badRequest()
                        .body(new ErrorResponse("username/password bắt buộc"));
            }

            try {
                Authentication requestToken =
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                body.username(), body.password());

                // Kiểm tra password do provider xử lý, không do Controller.
                Authentication authenticated =
                        authenticationManager.authenticate(requestToken);

                sessionStrategy.onAuthentication(authenticated, request, response);

                SecurityContext context = SecurityContextHolder.createEmptyContext();
                context.setAuthentication(authenticated);
                SecurityContextHolder.setContext(context);

                contextRepository.saveContext(context, request, response);
                return ResponseEntity.ok(toResponse(authenticated));

            } catch (org.springframework.security.core.AuthenticationException ex) {
                SecurityContextHolder.clearContext();
                return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                        .body(new ErrorResponse("Thông tin đăng nhập không hợp lệ"));
            }
        }

        @GetMapping("/api/me")
        public LoginResponse me(Authentication auth) {
            return toResponse(auth);
        }

        private static LoginResponse toResponse(Authentication auth) {
            List<String> authorities = auth.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList();
            return new LoginResponse(auth.getName(), authorities);
        }
    }
}
```

### 3.3. Giải thích các quyết định quan trọng

1. `AuthenticationManager` được cấu hình tường minh qua `ProviderManager`/`DaoAuthenticationProvider` để thấy rõ credential được kiểm tra ở đâu. Controller chỉ biết manager interface, không lấy user/password hash.
2. Bean `SecurityContextRepository` được dùng **cùng một instance** trong Controller và `SecurityFilterChain`. Nếu hai bên lưu/đọc từ hai nơi khác nhau, request kế tiếp có thể mất danh tính.
3. `SessionAuthenticationStrategy` được gọi sau thành công, trước khi lưu context. `ChangeSessionIdAuthenticationStrategy` đổi session ID; `CsrfAuthenticationStrategy` xóa token cũ. Client phải gọi lại `GET /api/csrf` sau login.
4. `permitAll()` cho `/api/login` chỉ bỏ yêu cầu login trước, **không vô hiệu hóa** `CsrfFilter`. POST thiếu token CSRF hợp lệ trả 403 ngay cả khi password đúng.
5. `httpBasic` và `formLogin` được tắt để demo chỉ có luồng JSON. `@PostMapping("/api/login")` không tự trở thành một filter authentication có sẵn của Spring Security.
6. `exceptionHandling` đặt entry point trả 401 cho GET endpoint được bảo vệ khi chưa có session. Người dùng đã xác thực nhưng không đủ role ở endpoint khác thường nhận 403.
7. `LogoutFilter` xử lý `POST /api/logout`, vô hiệu hóa session theo cơ chế mặc định và trả 204. Không cần viết controller tự xóa session.
8. Response thành công chỉ có username và role lấy từ manager, không chứa password hoặc password hash.

## 4. Chạy và thử bằng HTTP

Trong thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

### 4.1. Bash/macOS/Linux: cookie jar + CSRF

Ví dụ dùng `curl` và `python3`, cùng file `cookies.txt` để giữ cookie `JSESSIONID`. Token được lấy từ JSON nên không có giá trị cố định.

```bash
# 1. Nhận CSRF token + session cookie trước khi POST.
csrf_token=$(curl -sS -c cookies.txt http://localhost:8080/api/csrf \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

# 2. Login bằng JSON, gửi cookie và CSRF thuộc cùng session.
curl -i -sS -b cookies.txt -c cookies.txt \
    -H "X-CSRF-TOKEN: $csrf_token" \
    -H 'Content-Type: application/json' \
    --data '{"username":"alice","password":"secret123"}' \
    http://localhost:8080/api/login

# 3. Request tiếp theo không gửi password: chỉ giữ cookie đã cập nhật.
curl -i -sS -b cookies.txt http://localhost:8080/api/me

# 4. Login đã xoay CSRF token; lấy token mới trước POST tiếp.
new_token=$(curl -sS -b cookies.txt -c cookies.txt http://localhost:8080/api/csrf \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

# 5. Logout qua LogoutFilter.
curl -i -sS -b cookies.txt -c cookies.txt \
    -H "X-CSRF-TOKEN: $new_token" \
    -X POST http://localhost:8080/api/logout

# 6. Sau logout, cookie cũ không còn đại diện user đã đăng nhập.
curl -i -sS -b cookies.txt http://localhost:8080/api/me
```

Kết quả điển hình:

| Request | HTTP status | Ghi chú |
| --- | --- | --- |
| GET `/api/csrf` | 200 | JSON có `headerName`, `parameterName`, `token` |
| POST `/api/login` đúng password/CSRF | 200 | Body `{"username":"alice","authorities":["ROLE_READER"]}` |
| GET `/api/me` với session sau login | 200 | Trả lại username/authorities của Alice |
| POST `/api/logout` với CSRF token mới | 204 | Không có body |
| GET `/api/me` sau logout | 401 | Nội dung lỗi có thể phụ thuộc Spring Boot |
| POST login thiếu hoặc sai CSRF | 403 | `CsrfFilter` từ chối trước Controller |
| POST login có CSRF nhưng sai password | 401 | `AuthenticationManager`/provider từ chối |
| POST login có CSRF nhưng username/password trống | 400 | Controller validation đơn giản |

Chạy local bằng HTTP phục vụ học tập. Khi truyền credential và cookie trên mạng thực cần **HTTPS/TLS**.

### 4.2. PowerShell Windows

Không cần Bash hay công cụ parse JSON riêng, dùng `WebRequestSession` để giữ cookie:

```powershell
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$csrf = Invoke-RestMethod -Method Get -Uri 'http://localhost:8080/api/csrf' -WebSession $session
$login = Invoke-RestMethod -Method Post -Uri 'http://localhost:8080/api/login' -WebSession $session -Headers @{ 'X-CSRF-TOKEN' = $csrf.token } -ContentType 'application/json' -Body '{"username":"alice","password":"secret123"}'
$login
Invoke-RestMethod -Method Get -Uri 'http://localhost:8080/api/me' -WebSession $session
```

`Invoke-RestMethod` trả đối tượng có `username = alice` và `authorities = ["ROLE_READER"]`. Nếu muốn gọi thêm POST sau login, lấy CSRF token mới trước.

## 5. Kiểm thử bằng MockMvc

Tạo `src/test/java/com/example/jsonlogin/JsonLoginApplicationTests.java`:

```java
package com.example.jsonlogin;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class JsonLoginApplicationTests {
    private static final String GOOD_LOGIN = """
            {"username":"alice","password":"secret123"}
            """;

    @Autowired
    MockMvc mvc;

    @Test
    void jsonLoginPersistsAuthenticationBetweenRequests() throws Exception {
        // Tạo CSRF token và session bằng GET không yêu cầu đăng nhập.
        MvcResult initial = mvc.perform(get("/api/csrf"))
                .andExpect(status().isOk())
                .andReturn();
        MockHttpSession session =
                (MockHttpSession) initial.getRequest().getSession(false);
        assertNotNull(session);
        String token = JsonPath.read(
                initial.getResponse().getContentAsString(), "$.token");

        MvcResult login = mvc.perform(post("/api/login")
                    .session(session)
                    .header("X-CSRF-TOKEN", token)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(GOOD_LOGIN))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.authorities[0]").value("ROLE_READER"))
                .andReturn();

        MockHttpSession authenticatedSession =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(authenticatedSession);

        // Request tiếp theo lấy Authentication qua repository từ session.
        mvc.perform(get("/api/me").session(authenticatedSession))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void csrfFailureAndBadCredentialsAreDifferent() throws Exception {
        mvc.perform(post("/api/login")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(GOOD_LOGIN))
                .andExpect(status().isForbidden());

        mvc.perform(post("/api/login")
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"username":"alice","password":"wrong"}
                            """))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.message")
                        .value("Thông tin đăng nhập không hợp lệ"));

        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }
}
```

Chạy test:

```bash
mvn test
```

Test đầu dùng **token CSRF thực trả về từ endpoint** để đăng nhập, rồi dùng cùng session đã cập nhật trong một HTTP request khác. Điều này kiểm chứng kết quả manager xác thực được lưu và request sau không cần gửi lại password. Test thứ hai phân biệt CSRF 403 với credential 401 và chưa đăng nhập 401.

`MockMvc` thực thi Servlet filter chain và controller trong môi trường test, không cần server mở port. `with(csrf())` là tiện ích của `spring-security-test`, không phải cấu hình tắt CSRF trong sản phẩm.

## 6. Những lưu ý bảo mật và thiết kế

### 6.1. Phân biệt xác thực, phân quyền, lưu phiên

- **Authentication:** `AuthenticationManager` kiểm tra danh tính/credential và trả `Authentication`.
- **Authorization:** rule như `hasRole("ADMIN")` dùng authority trong `Authentication` để cho phép/khước từ truy cập.
- **Persistence:** `SecurityContextRepository` giữ danh tính qua các request khi dùng session. Manager không tự làm phần này.
- **JWT:** Nếu chuyển sang Bearer token, cần phát hành token có chữ ký, thời hạn/claims thích hợp rồi xác minh token trên mỗi request. Chỉ gọi `authenticate` không tự tạo JWT.

| Kiểu ứng dụng | Sau khi authenticate | Request sau |
| --- | --- | --- |
| Session/cookie (demo) | `SecurityContextRepository.saveContext` vào session, rotate session ID | Client gửi cookie; server nạp context |
| Stateless token | Phát hành credential/token an toàn bằng thành phần phù hợp | Client gửi Bearer token; filter xác minh chữ ký/expiry |

Không cấu hình `SessionCreationPolicy.STATELESS` rồi kỳ vọng `HttpSessionSecurityContextRepository` vẫn giữ phiên đăng nhập.

### 6.2. CSRF vẫn quan trọng với JSON có cookie

CSRF phụ thuộc **credential mà browser tự gửi** như cookie, không phụ thuộc body là JSON hay form. `permitAll` không tắt `CsrfFilter`. Demo giữ `HttpSessionCsrfTokenRepository`; client lấy token qua `GET /api/csrf` và gửi trong header `X-CSRF-TOKEN` khi POST. Khi login thành công, `CsrfAuthenticationStrategy` xóa token cũ; client lấy lại token mới. Không dùng `csrf.disable()` tùy tiện cho API được browser gọi bằng session cookie.

Nếu frontend ở origin khác, cần cấu hình CORS, cookie `Secure`/`HttpOnly`/`SameSite` và chính sách gửi credential một cách đồng bộ. Login production phải dùng HTTPS; không ghi raw password, session ID hay CSRF token vào log.

### 6.3. Session fixation và logout

Custom Controller gọi manager **không tự kích hoạt** toàn bộ lifecycle của authentication filter tiêu chuẩn. Demo chủ động gọi `SessionAuthenticationStrategy` sau authenticate để đổi session ID, giảm nguy cơ session fixation, và làm mới CSRF token. `LogoutFilter` dùng `SecurityContextLogoutHandler` của Spring Security để xử lý phiên; không thay bằng việc chỉ xóa dữ liệu phía frontend.

### 6.4. Các lỗi thường gặp

1. Tự so sánh password trong Controller bằng `equals` hoặc `PasswordEncoder.matches`.
2. Dùng `UsernamePasswordAuthenticationToken.authenticated(...)` với credential chưa được kiểm chứng.
3. Cho rằng `AuthenticationManager.authenticate(...)` trả boolean.
4. Trả 200 JSON mà quên `SecurityContextRepository.saveContext`.
5. Dùng repository khác nhau giữa Controller và `SecurityFilterChain`.
6. Không gọi session authentication strategy khi tự tạo luồng login.
7. Quên làm mới CSRF token sau login trong cơ chế có `CsrfAuthenticationStrategy`.
8. Tắt CSRF chỉ vì API nhận JSON và dùng cookie.
9. Trả `AuthenticationException.getMessage()` ra client, làm lộ trạng thái account.
10. Để client tự khai roles/authorities trong `LoginRequest`.
11. Nghĩ rằng một login JSON thành công tự phát hành JWT.
12. Bỏ qua rate limiting, chống brute force, MFA khi cần và ghi nhận sự kiện bảo mật.
13. Không dùng HTTPS, hoặc ghi password/hash/cookie vào log.
14. Coi lỗi 401 (credential thiếu/sai) giống lỗi 403 (đã xác thực nhưng thiếu quyền hoặc CSRF bị từ chối).

## 7. Câu hỏi tự đánh giá

1. Vì sao `AuthenticationManager` tốt hơn tự `if (password.equals(...))` trong Controller?
2. Ai thực sự gọi `PasswordEncoder.matches` khi dùng `DaoAuthenticationProvider`?
3. `UsernamePasswordAuthenticationToken.unauthenticated` khác kết quả `Authentication` trả về ở điểm nào?
4. Vì sao chỉ `SecurityContextHolder.setContext` mà quên `saveContext` khiến request tiếp theo vẫn 401?
5. Vì sao POST `/api/login` có password đúng vẫn có thể bị `CsrfFilter` trả 403?
6. Vì sao session ID và CSRF token cần được xử lý khi custom Controller tự authenticate?
7. Nếu sau này dùng JWT thay session, những bước nào cần thay đổi bên cạnh `AuthenticationManager`?

**Đáp án chính:** (1) manager áp dụng provider/account policy nhất quán; (2) provider; (3) đầu vào chưa authenticated, kết quả đã xác minh; (4) context chỉ tồn tại trong request hiện tại; (5) CSRF là lớp bảo vệ trước Controller; (6) giảm session fixation và bảo vệ request dùng cookie; (7) phát hành và xác minh token có chữ ký/hạn dùng, không dùng session persistence.

## 8. Tài liệu chính thức

- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — Session Management / Storing Authentication Manually: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security — CSRF, token endpoint and JavaScript clients: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security — AuthenticationManager API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationManager.html
