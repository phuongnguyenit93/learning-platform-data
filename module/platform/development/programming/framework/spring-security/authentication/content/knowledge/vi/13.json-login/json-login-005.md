# Lưu SecurityContext khi endpoint JSON tạo phiên đăng nhập (Spring Security Servlet)

## 1. Bài toán: login JSON trả 200 nhưng request tiếp theo lại chưa đăng nhập

Trong một ứng dụng Spring MVC, client thường gửi JSON đến `POST /auth/login`:

```http
POST /auth/login HTTP/1.1
Content-Type: application/json

{"username":"alice","password":"alice-secret"}
```

Controller xác thực username/password thành công rồi trả JSON. Tuy nhiên, nếu chỉ làm:

```java
Authentication authentication = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(username, password)
);
SecurityContextHolder.getContext().setAuthentication(authentication);
```

thì **request hiện tại** có thể nhìn thấy user đã xác thực, nhưng request kế tiếp vẫn có thể bị từ chối. Nguyên nhân: `SecurityContextHolder` là nơi giữ context cho luồng xử lý hiện tại; nó **không tự bảo đảm** rằng context được ghi vào nơi lưu trữ có thể đọc lại ở request sau.

Bài này tập trung vào một **endpoint JSON tự xác thực và tạo phiên đăng nhập dựa trên HTTP session**, với Java 17+, Spring Boot 3.x/Spring Security 6.x ở Servlet stack. Đây là cơ chế **session login**: browser giữ cookie phiên, còn server giữ `SecurityContext`. Nó khác JWT/bearer-token stateless, HTTP Basic hay OAuth2 login được các filter dựng sẵn xử lý.

Kết thúc bài, bạn cần giải thích và triển khai được:

1. Tạo `Authentication` đã được kiểm chứng qua `AuthenticationManager`.
2. Tạo `SecurityContext` mới, đặt `Authentication` vào đó, rồi gắn vào `SecurityContextHolder`.
3. Gọi `SecurityContextRepository.saveContext(context, request, response)` **trước khi response được commit** để request kế tiếp khôi phục đăng nhập.
4. Bảo đảm client lưu và gửi lại cookie session; phân biệt với việc tự lưu password/token vào cookie.
5. Xử lý các vấn đề đi kèm login thủ công: session fixation, CSRF, login thất bại, logout, môi trường nhiều instance và kiểm thử.

## 2. Các thành phần giữ và phục hồi đăng nhập

| Thành phần | Trách nhiệm | Có giữ đăng nhập qua nhiều request? |
|---|---|---|
| `UsernamePasswordAuthenticationToken` chưa xác thực | Đưa username/password vào quy trình xác thực | Không |
| `AuthenticationManager` | Gọi nhà cung cấp xác thực để kiểm tra credentials | Không tự lưu phiên |
| `Authentication` đã xác thực | Chứa principal, authorities và trạng thái xác thực | Chưa đủ nếu không được lưu |
| `SecurityContext` | Bao bọc `Authentication` | Bản thân context chưa tạo session |
| `SecurityContextHolder` | Giữ context đang dùng trong request/thread | Không phải kho lưu liên request |
| `SecurityContextRepository` | Đọc/ghi `SecurityContext` qua vòng đời request | Có, nếu repo hỗ trợ persistence |
| `HttpSessionSecurityContextRepository` | Lưu context trong `HttpSession` của server | Có, dựa vào session ID |
| `RequestAttributeSecurityContextRepository` | Giữ context trong cùng request, kể cả một số dispatch | Chỉ trong request |
| `DelegatingSecurityContextRepository` | Phối hợp nhiều repository | Có thể kết hợp cả hai |
| `SecurityContextHolderFilter` | Đọc context từ repo, đưa vào holder và dọn holder sau request | **Không tự lưu** context mới trong Spring Security 6 |

Trong Spring Security 6, cơ chế mặc định sử dụng `SecurityContextHolderFilter` và yêu cầu **lưu tường minh** khi tự xác thực bên ngoài các authentication filter được Spring Security quản lý. `SecurityContextPersistenceFilter` đời cũ từng hỗ trợ lưu tự động; không xây giải pháp mới dựa vào kỳ vọng đó.

Thông thường, `DelegatingSecurityContextRepository` kết hợp:

- `RequestAttributeSecurityContextRepository` để phục vụ các dispatch trong một request.
- `HttpSessionSecurityContextRepository` để gắn context với session, phục hồi ở request sau.

**Điều kiện thiết yếu:** repository dùng để `saveContext(...)` trong controller phải tương thích với repository mà filter chain dùng để `load`. Dùng hai repository lưu ở hai chỗ khác nhau có thể gây hiện tượng “login thành công nhưng không nhớ phiên”.

### Luồng request theo thời gian

```mermaid
sequenceDiagram
    participant C as Client
    participant F as Security filters
    participant L as JSON login controller
    participant A as AuthenticationManager
    participant R as SecurityContextRepository

    C->>F: POST /auth/login + JSON + CSRF + cookie
    F->>L: Cho phép đi vào endpoint login
    L->>A: authenticate(username, password)
    A-->>L: Authentication đã xác thực
    L->>L: SessionAuthenticationStrategy.onAuthentication(...)
    L->>L: createEmptyContext + setAuthentication
    L->>R: saveContext(context, request, response)
    R-->>C: Lưu context vào session; trả/đổi session cookie nếu cần
    C->>F: GET /api/me + Cookie: JSESSIONID=...
    F->>R: load context từ session
    R-->>F: Authentication của alice
    F-->>C: 200 {"username":"alice"}
```

Cookie như `JSESSIONID` thông thường chỉ chứa **mã định danh phiên**. Nó không chứa password và không chứa toàn bộ `Authentication`. Context thực tế nằm phía server (hoặc kho session do server quản lý, chẳng hạn Spring Session).

## 3. Ví dụ hoàn chỉnh: JSON login lưu phiên trong Spring Boot

Giả sử một dự án Spring Boot 3.x dùng Java 17+ và có sẵn Gradle wrapper/Boot plugin. Các dependency cần thiết:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Ứng dụng có ba file dưới package `com.example.jsonlogin`. Đường dẫn/package/class bên dưới khớp nhau. Mật khẩu mẫu chỉ dùng local; production phải quản lý credentials bằng nguồn danh tính phù hợp.

### 3.1. Điểm khởi động

`src/main/java/com/example/jsonlogin/JsonLoginApplication.java`:

```java
package com.example.jsonlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonLoginApplication.class, args);
    }
}
```

### 3.2. SecurityFilterChain, SecurityContextRepository và session strategy

`src/main/java/com/example/jsonlogin/SecurityConfig.java`:

```java
package com.example.jsonlogin;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository()
        );
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy(
            CsrfTokenRepository csrfTokenRepository) {
        return new CompositeSessionAuthenticationStrategy(List.of(
            new ChangeSessionIdAuthenticationStrategy(),
            new CsrfAuthenticationStrategy(csrfTokenRepository)
        ));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository securityContextRepository,
            CsrfTokenRepository csrfTokenRepository) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/csrf", "/auth/login", "/error")
                    .permitAll()
                .anyRequest().authenticated()
            )
            .securityContext(context -> context
                .securityContextRepository(securityContextRepository)
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            )
            .csrf(csrf -> csrf
                .csrfTokenRepository(csrfTokenRepository)
            )
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED))
            )
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .logout(logout -> logout
                .logoutUrl("/auth/logout")
                .logoutSuccessHandler((request, response, authentication) ->
                    response.setStatus(204))
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-secret"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            AuthenticationConfiguration configuration) throws Exception {
        return configuration.getAuthenticationManager();
    }
}
```

Ý nghĩa những phần ảnh hưởng trực tiếp tới bài:

- `securityContextRepository()` tạo **một bean dùng chung**. Filter chain nhận bean này để đọc context; controller ở phần kế tiếp dùng chính bean đó để ghi context.
- `SessionCreationPolicy.IF_REQUIRED` cho phép tạo session khi cần. Không dùng `STATELESS` cho ví dụ session login: chế độ đó ngăn Spring Security dùng `HttpSession` để lấy `SecurityContext` và thường cấu hình repo không lưu.
- `.csrf(...)` giữ bảo vệ CSRF, dùng `HttpSessionCsrfTokenRepository`. Một endpoint login POST dựa trên cookie **cần** cân nhắc CSRF; JSON body tự nó không loại bỏ rủi ro.
- `.httpBasic(...disable)` và `.formLogin(...disable)` tránh cơ chế khác chiếm luồng login. `HttpStatusEntryPoint` giúp request chưa đăng nhập nhận `401` thay vì chuyển hướng sang trang form.
- `sessionAuthenticationStrategy()` cố ý ghép hai hành vi vốn có ở login filter tương ứng: thay session ID để chống session fixation và xóa CSRF token cũ sau login. **Controller tự xác thực phải tự gọi strategy này**; đừng cho rằng cấu hình chung tự gọi thay controller.
- `logout(...)` dùng hạ tầng logout của Spring Security cho `POST /auth/logout`; handler trả `204 No Content`. Vì CSRF bật, logout POST cũng phải gửi CSRF token hợp lệ.
- `UserDetailsService` và `BCryptPasswordEncoder` phục vụ demo. `AuthenticationManager` lấy manager đã được Spring Security cấu hình từ bean quản lý người dùng.
- Không dùng `request.getSession(true)` chỉ để cố tạo session ở mỗi request. `HttpSessionSecurityContextRepository` có thể tạo session khi lưu context đã xác thực nếu chính sách cho phép; session cũng có thể đã tồn tại vì CSRF.

### 3.3. Endpoint JSON: authenticate → session strategy → setContext → saveContext

`src/main/java/com/example/jsonlogin/LoginController.java`:

```java
package com.example.jsonlogin;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
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
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LoginController {

    private final AuthenticationManager authenticationManager;
    private final SecurityContextRepository securityContextRepository;
    private final SessionAuthenticationStrategy sessionAuthenticationStrategy;

    public LoginController(
            AuthenticationManager authenticationManager,
            SecurityContextRepository securityContextRepository,
            SessionAuthenticationStrategy sessionAuthenticationStrategy) {
        this.authenticationManager = authenticationManager;
        this.securityContextRepository = securityContextRepository;
        this.sessionAuthenticationStrategy = sessionAuthenticationStrategy;
    }

    public record LoginRequest(String username, String password) {}

    @GetMapping("/api/csrf")
    public CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }

    @PostMapping(
        path = "/auth/login",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<Map<String, String>> login(
            @RequestBody LoginRequest body,
            HttpServletRequest request,
            HttpServletResponse response) {

        Authentication authentication;
        try {
            authentication = authenticationManager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    body.username(), body.password()
                )
            );
        } catch (AuthenticationException ex) {
            SecurityContextHolder.clearContext();
            securityContextRepository.saveContext(
                SecurityContextHolder.createEmptyContext(), request, response
            );
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("error", "invalid_credentials"));
        }

        // Controller tự đăng nhập nên phải thực thi session strategy.
        sessionAuthenticationStrategy.onAuthentication(
            authentication, request, response
        );

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);

        // Bước quyết định khả năng đăng nhập tồn tại ở request tiếp theo.
        securityContextRepository.saveContext(context, request, response);

        return ResponseEntity.ok(Map.of(
            "username", authentication.getName()
        ));
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }
}
```

**Đọc lần lượt bảy thao tác quan trọng:**

1. Nhận JSON qua `@RequestBody LoginRequest`. Đây là DTO của request, không phải đối tượng `Authentication` đã đáng tin.
2. Gọi `UsernamePasswordAuthenticationToken.unauthenticated(...)`. Đừng tự đặt `authenticated=true` hoặc tự tạo token “đã đăng nhập” chỉ vì client gửi username.
3. `authenticationManager.authenticate(...)` kiểm tra credentials và trả một `Authentication` đã được nhà cung cấp xác thực chấp nhận. Khi sai, `AuthenticationException` được xử lý thành JSON `401` với thông báo chung, không làm lộ “user không tồn tại” hay “sai mật khẩu”.
4. `sessionAuthenticationStrategy.onAuthentication(...)` chạy các xử lý liên quan session trên **login thành công**. Với demo, nếu session tồn tại, ID được thay để giảm nguy cơ fixation; CSRF token cũ bị xóa.
5. `SecurityContextHolder.createEmptyContext()` tạo context mới; `context.setAuthentication(authentication)` gắn principal đã xác thực.
6. `SecurityContextHolder.setContext(context)` cho phép code trong **request hiện tại** nhìn thấy user vừa đăng nhập.
7. `securityContextRepository.saveContext(context, request, response)` **ghi context** xuống repository trước khi response hoàn thành. Request sau mới tải lại được user từ phiên.

Để kiểm soát login thất bại trong ví dụ, controller cũng xóa/saved empty context nếu `AuthenticationManager` từ chối credentials. Điều này giúp một request login thất bại không vô tình giữ lại phiên đăng nhập trước đó. Trong ứng dụng thật, xử lý phiên cũ khi người dùng thử đổi tài khoản phải theo chính sách sản phẩm.

Đoạn trên trình bày luồng chính; trước khi đưa vào production, cần thêm validation dữ liệu (username/password không null hoặc rỗng), rate limiting/throttle, xử lý `SessionAuthenticationException`, audit an toàn và quy tắc vòng đời session theo thiết kế hệ thống.

## 4. Vì sao phải gọi saveContext dù đã setAuthentication?

Cần tách **hai hướng dữ liệu**:

- `SecurityContextHolder.setContext(context)`: thay context của request đang chạy.
- `SecurityContextRepository.saveContext(context, request, response)`: ghi context đến nơi mà request sau có thể đọc được.

Khi xử lý request mới, `SecurityContextHolderFilter` lấy context từ repo. Cuối request, context trong holder được dọn. Vì thế chỉ set trong holder mà không save sẽ mất hiệu lực liên request trong cấu hình explicit-save.

`HttpSessionSecurityContextRepository` thường lưu context như một session attribute tên `SPRING_SECURITY_CONTEXT`. Tên attribute này là chi tiết triển khai hữu ích khi debug; code ứng dụng nên dùng interface `SecurityContextRepository` thay vì tự `session.setAttribute(...)`.

**Thứ tự sai thường gặp:**

```java
SecurityContextHolder.setContext(context);
response.getWriter().write("{\"ok\":true}");
response.flushBuffer();  // response có thể đã commit
securityContextRepository.saveContext(context, request, response);
```

Đoạn trên là ví dụ **không nên làm**: response đã commit khiến việc tạo/đổi session cookie muộn không đáng tin cậy. Hãy save context **trước** khi ghi hoặc flush response.

**Một cách sửa cũng chưa đủ:**

```java
request.getSession().setAttribute("loggedIn", true);
```

Một cờ tự tạo như vậy không biến request thành `Authentication` đã được Spring Security công nhận. `AuthorizationFilter` đọc security context, không tự hiểu attribute `loggedIn`.

## 5. Chạy thử bằng HTTP và quan sát cookie session

Từ thư mục dự án Boot đã có wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell dùng `.\gradlew.bat bootRun`. Các lệnh dưới đây minh họa trên **Bash có curl và jq** (để đọc JSON), sử dụng tài khoản demo trong `SecurityConfig`:

```bash
# 1. Lấy CSRF token; lưu session cookie vào file.
curl -s -c cookies.txt -b cookies.txt \
  http://localhost:8080/api/csrf > csrf.json

# 2. Đọc token do server trả về.
TOKEN=$(jq -r '.token' csrf.json)

# 3. Login JSON, gửi CSRF header, nhận/ghi lại cookie phiên.
curl -i -c cookies.txt -b cookies.txt \
  -H 'Content-Type: application/json' \
  -H "X-CSRF-TOKEN: $TOKEN" \
  --data '{"username":"alice","password":"alice-secret"}' \
  http://localhost:8080/auth/login

# 4. Request mới: không gửi username/password, chỉ gửi cookie.
curl -i -b cookies.txt http://localhost:8080/api/me
```

**Kết quả cần quan sát:**

- Bước 1: `200` với JSON chứa `headerName`, `parameterName` và `token`; token thực tế thay đổi theo phiên/request.
- Bước 3: `200` với JSON `{"username":"alice"}`. Header `Set-Cookie` có thể phát sinh hoặc cập nhật session ID, đặc biệt khi login đổi session ID.
- Bước 4: `200` với JSON `{"username":"alice"}` dù không gửi password ở request này. Đây là bằng chứng chính rằng repository đã lưu và phục hồi context.
- Nếu chạy bước 4 **không dùng cookie jar**, response dự kiến là `401` vì server không biết phiên vừa đăng nhập.
- Nếu gửi password sai với CSRF hợp lệ, login trả `401 {"error":"invalid_credentials"}`; request sau không nên nhận nhầm danh tính từ lần thử thất bại.

Tên cookie thường là `JSESSIONID` với Servlet container mặc định; khi tích hợp Spring Session hoặc một lớp gateway, tên có thể khác. Không suy luận user được xác thực chỉ vì có `Set-Cookie`: CSRF hoặc chức năng khác cũng có thể tạo session trước login.

**Mô phỏng failure do thiếu CSRF:**

```bash
curl -i -c cookies.txt -b cookies.txt \
  -H 'Content-Type: application/json' \
  --data '{"username":"alice","password":"alice-secret"}' \
  http://localhost:8080/auth/login
```

Với cấu hình trên, request POST này không có `X-CSRF-TOKEN` và sẽ bị CSRF filter chặn bằng `403` **trước khi** controller chạy. Không được chẩn đoán đó là password sai. Nếu test login bằng Postman/curl, nhớ thu thập token và gửi cookie của cùng phiên.

### Sau khi đăng nhập: token CSRF cũ bị vô hiệu

Trong demo, `CsrfAuthenticationStrategy` xóa token cũ khi login thành công. Nếu client còn thao tác POST/PUT/DELETE, client phải gọi lại `GET /api/csrf` để lấy token mới sau login rồi gửi token mới cho các request thay đổi trạng thái.

Logout mẫu dùng `POST /auth/logout` và CSRF token sau login:

```bash
NEW_TOKEN=$(curl -s -c cookies.txt -b cookies.txt \
  http://localhost:8080/api/csrf | jq -r '.token')

curl -i -c cookies.txt -b cookies.txt \
  -X POST -H "X-CSRF-TOKEN: $NEW_TOKEN" \
  http://localhost:8080/auth/logout

curl -i -b cookies.txt http://localhost:8080/api/me
```

Kết quả dự kiến: logout trả `204`, request `/api/me` sau logout trả `401`. Logout của Spring Security chịu trách nhiệm làm sạch context và vô hiệu hóa session theo cấu hình; chỉ xóa biến trong holder bằng tay không đủ để thu hồi phiên đã lưu.

## 6. Kiểm thử MockMvc: sự khác biệt giữa cùng request và request kế tiếp

Thêm file `src/test/java/com/example/jsonlogin/JsonLoginTest.java`:

```java
package com.example.jsonlogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
@AutoConfigureMockMvc
class JsonLoginTest {

    @Autowired
    MockMvc mvc;

    @Test
    void loginPersistsAuthenticationInSession() throws Exception {
        MvcResult loginResult = mvc.perform(post("/auth/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"alice\",\"password\":\"alice-secret\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) loginResult.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void loginSessionIsNotReusedWithoutSessionCookie() throws Exception {
        mvc.perform(post("/auth/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"alice\",\"password\":\"alice-secret\"}"))
            .andExpect(status().isOk());

        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordReturnsUnauthorized() throws Exception {
        mvc.perform(post("/auth/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"alice\",\"password\":\"wrong\"}"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_credentials"));
    }

    @Test
    void csrfIsRequiredForJsonLogin() throws Exception {
        mvc.perform(post("/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"alice\",\"password\":\"alice-secret\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void protectedApiRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }
}
```

Chạy:

```bash
./gradlew test
```

`.with(csrf())` là helper của `spring-security-test` dùng cho MockMvc, giúp tạo request POST có CSRF hợp lệ. Nó **không tự khởi tạo phiên đăng nhập**. Ca quan trọng nhất là `loginPersistsAuthenticationInSession`: lấy session từ response login rồi dùng session đó trong một request GET **khác**; nếu chỉ `SecurityContextHolder.setContext(...)` mà bỏ `saveContext(...)`, test này sẽ phơi bày lỗi mất authentication qua request.

MockMvc mô phỏng Servlet request/session trong process test; để xác nhận cookie thực tế do container/proxy phát và thuộc tính `Secure`/`SameSite`/`HttpOnly`, bổ sung integration test bằng HTTP thực hoặc kiểm tra trên môi trường triển khai.

## 7. Những ranh giới quan trọng của việc “lưu SecurityContext”

### 7.1. Session cookie khác access token

Ở ví dụ này, client nhận/giữ **cookie định danh session**. Server sử dụng cookie để tìm `HttpSession` và tải `SecurityContext`. Không cần phát JWT chỉ để chứng minh một request sau login; thêm JWT vào thiết kế sẽ đổi mô hình xác thực và không thuộc luồng lưu context bằng session này.

Tuy vậy, session cần chính sách timeout, vô hiệu hóa khi logout, storage khi scale ngang và cấu hình cookie đúng. Nếu cookie không được trình duyệt gửi lại vì khác domain/path, `SameSite`, `Secure`, CORS hay `credentials`, server không tìm được session dù bạn đã gọi `saveContext`.

### 7.2. Session fixation khi tự viết endpoint login

Các filter login chuẩn của Spring Security có thể thực thi `SessionAuthenticationStrategy` sau xác thực thành công. Với **controller thủ công**, bạn phải gọi nó trong luồng mình sở hữu. `ChangeSessionIdAuthenticationStrategy` thay session ID khi đã có session (Servlet 3.1+), tránh tái sử dụng identifier đã bị attacker cố định.

Không nhầm `sessionManagement(session -> session.sessionFixation(...))` với việc strategy chắc chắn được gọi trong controller tự viết. Nếu ứng dụng cần kiểm soát số phiên đồng thời, phải tích hợp các strategy liên quan (session registry, concurrent-session control, session registration) vào authentication flow; demo hiện chỉ minh họa session ID và CSRF.

### 7.3. CSRF và login JSON

Với xác thực dựa trên cookie, browser tự đính kèm cookie trên request phù hợp. Dù login dùng JSON, ứng dụng vẫn cần threat model cho CSRF, đặc biệt nếu được browser sử dụng.

- Spring Security bật CSRF cho các HTTP method không an toàn theo mặc định.
- `permitAll()` chỉ bỏ yêu cầu **đăng nhập** của endpoint; nó **không** tự bỏ CSRF cho POST.
- Demo mở `GET /api/csrf` trước login; frontend gửi token được trả lại ở `X-CSRF-TOKEN` cùng cookie tương ứng.
- Sau login/logout, strategy/handler có thể xóa token cũ; client lấy token mới.
- Với SPA cross-origin, cần cấu hình CORS/credentials và cookie đúng; `fetch` thường cần `credentials: "include"` cho request gửi cookie sang origin được phép. Không cấu hình bừa bãi origin wildcard cùng credentials.

Không tắt `csrf` toàn cục chỉ để “POST login hoạt động” khi ứng dụng dùng browser/cookie.

### 7.4. Lưu thành công nhưng request sau vẫn 401

Kiểm tra theo thứ tự:

| Hiện tượng | Nguyên nhân thường gặp | Cách xác minh |
|---|---|---|
| Login `200`, ngay sau đó `GET /api/me` là `401` | Quên `saveContext` | Quan sát có gọi `SecurityContextRepository.saveContext(...)` hay không |
| Đã save nhưng vẫn `401` | Controller và filter chain dùng repository khác, hoặc dùng `NullSecurityContextRepository` | So sánh cấu hình repository và chain trúng URL |
| Request khác không nhận session | Cookie không lưu/gửi lại, path/domain/SameSite/Secure/CORS | Kiểm tra `Set-Cookie` rồi `Cookie` ở request sau |
| Session không được tạo | `STATELESS`, repository không lưu, hoặc save xảy ra quá muộn | Kiểm tra `SessionCreationPolicy` và thời điểm response commit |
| Thỉnh thoảng mất login khi chuyển server | Session lưu local ở từng instance | Sử dụng session store chung/Spring Session hoặc routing phù hợp |
| `POST /auth/login` bị `403` ngay | Thiếu/sai CSRF token | Kiểm tra CSRF filter và token thuộc cùng cookie phiên |
| Password sai mà báo `403` | Request chưa tới controller do CSRF | Phân biệt lỗi CSRF với `AuthenticationException` |
| Đổi user nhưng session ID không đổi | Controller chưa gọi session strategy | Gọi strategy sau authentication và test session fixation |
| Logout xong nhưng vẫn được nhận diện | Chỉ xóa holder, chưa hủy session/saved context | Dùng cơ chế logout và kiểm tra request sau |
| Login thành công nhưng role không đúng | `AuthenticationManager` trả authorities không đúng hoặc bị mất | Kiểm tra `Authentication.getAuthorities()` đã xác thực và rule authorize |

**Đừng ghi log** raw `Authorization`, password JSON, session ID, CSRF token hoặc nguyên `SecurityContext`. Chỉ ghi metadata an toàn như correlation ID, username đã xác thực (nếu chính sách cho phép), loại kết quả và thời điểm.

### 7.5. SecurityContext lưu đâu nếu có nhiều ứng dụng?

`HttpSessionSecurityContextRepository` lưu trong HTTP session của môi trường Servlet. Một container đơn có thể dùng bộ nhớ cục bộ; khi chạy nhiều instance, cần bảo đảm request sau tìm được session tương ứng, thường bằng kho session chia sẻ như Spring Session với backend phù hợp hoặc hạ tầng sticky session được thiết kế nhất quán.

Đăng nhập session không tự giải quyết việc thu hồi mọi phiên của user, timeout, rotation, concurrent-login limits hay bảo mật cookie. Những chức năng đó cần chính sách và cấu hình riêng.

### 7.6. Không dùng “manual save” cho mọi cơ chế đăng nhập

Khi dùng `formLogin`, OAuth2 login hoặc filter xác thực do Spring Security cung cấp, framework thường đã quản lý context persistence và các bước thành công/thất bại liên quan. Bài này dành cho trường hợp **tự tạo một endpoint JSON gọi AuthenticationManager trong controller/custom filter**. Chỉ can thiệp vào repository khi bạn hiểu rõ trách nhiệm đang tự nhận.

## 8. Checklist triển khai

- [ ] `AuthenticationManager.authenticate(...)` tạo `Authentication` hợp lệ từ credentials do client gửi.
- [ ] Tạo `SecurityContext` mới và gắn `Authentication` vào đó.
- [ ] `SecurityContextHolder` được cập nhật cho request hiện tại.
- [ ] Dùng chung `SecurityContextRepository` giữa filter chain và controller.
- [ ] Gọi `saveContext(context, request, response)` trước khi response commit.
- [ ] Chính sách session cho phép ghi/đọc session (`IF_REQUIRED` trong demo); không cấu hình `STATELESS` trái mục tiêu.
- [ ] Login thủ công thực thi đúng `SessionAuthenticationStrategy`, gồm session fixation, CSRF và các strategy khác nếu hệ thống yêu cầu.
- [ ] Request tiếp theo dùng cùng cookie session nhận lại authentication; request không có cookie bị từ chối.
- [ ] POST login có CSRF protection phù hợp; client lấy lại CSRF token sau login/logout khi cần.
- [ ] Logout thu hồi phiên; cookie có `Secure`, `HttpOnly`, `SameSite` phù hợp và toàn bộ traffic đăng nhập chạy trên HTTPS.
- [ ] Có test cho login đúng, login sai, CSRF thiếu, request sau có session và request sau không có session.

**Tài liệu tham khảo:**

- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
