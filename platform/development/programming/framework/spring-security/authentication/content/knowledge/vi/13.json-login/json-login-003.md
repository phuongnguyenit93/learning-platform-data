# Giới hạn HTTP method, Content-Type và kích thước dữ liệu đầu vào khi đăng nhập JSON

> Phạm vi: **Spring Security - authentication → Đăng nhập JSON**, **Spring Boot 3.x / Spring Security 6.x trên Servlet**, Java 17+. Bài hướng dẫn chặn request đăng nhập sai phương thức, sai media type hoặc quá lớn *trước khi* xử lý credential. Ví dụ minh họa endpoint stateful `POST /api/login` có bảo vệ CSRF. Không áp dụng trực tiếp chính sách session này cho WebFlux, JWT/bearer token hoặc OAuth2.

## 1. Hợp đồng đầu vào: định nghĩa trước khi viết code

Đăng nhập JSON phải có hợp đồng HTTP rõ ràng:

| Điều kiện | Giá trị chấp nhận | Lỗi mong đợi |
| --- | --- | --- |
| Đường dẫn | `/api/login` | Các đường dẫn khác không được coi là endpoint đăng nhập |
| HTTP method | **Chỉ `POST`** | `405 Method Not Allowed` và header `Allow: POST` |
| Media type | `application/json` hoặc `application/json; charset=UTF-8` | `415 Unsupported Media Type` nếu thiếu/sai `Content-Type` |
| Content-Encoding | Không nén hoặc `identity` | `415` với encoding khác trong hợp đồng ví dụ |
| Body size | **Tối đa 8192 byte UTF-8 (8 KiB)** | `413 Content Too Large` / `Payload Too Large` |
| JSON structure | Object có `username` và `password` hợp lệ | `400 Bad Request` |
| Credential | Tài khoản và mật khẩu đúng | `401 Unauthorized` nếu xác thực thất bại |
| CSRF đối với login sử dụng cookie session | CSRF token hợp lệ | `403 Forbidden` nếu thiếu/sai token |
| Thành công | Body hợp lệ, CSRF và credential đúng | `204 No Content` |

Mốc **8192 byte là lựa chọn minh họa**, không phải giới hạn mặc định của Spring Security. Hãy chọn ngưỡng dựa trên payload thật và thay đổi đồng bộ ở gateway, app và test.

**Cần phân biệt:** `Content-Type` mô tả định dạng request body mà client khai báo; JSON parser mới xác nhận cú pháp JSON. `Accept` nói về định dạng **response** mong muốn, không thay thế `Content-Type`. `Content-Length` là số byte client khai báo, không phải bằng chứng chắc chắn về kích thước nội dung ứng dụng thực nhận.

Vì sao chỉ dùng POST? Username/password nằm trong URL của `GET` dễ lọt vào browser history, logs, analytics, proxy và telemetry. GET còn có ngữ nghĩa đọc, dễ bị prefetch/cache/crawler gọi ngoài ý muốn. POST và JSON không mã hóa đường truyền: vẫn **bắt buộc HTTPS** khi truyền credential.

## 2. Ràng buộc được thực thi ở những lớp nào?

Trong Spring MVC, `@PostMapping(path="/api/login", consumes="application/json")` ràng buộc **method** và **media type**. Nó **không tự giới hạn số byte nhận từ HTTP request**. Nếu ứng dụng dùng `@RequestBody String` hoặc `@RequestBody byte[]` rồi kiểm tra `length`, MVC có thể đã cấp phát bộ nhớ và đọc body quá lớn trước khi chặn.

Một mô hình đúng cho Servlet MVC đồng bộ:

```text
Client
  |
  v
Gateway / reverse proxy / Servlet container
  | giới hạn body, timeouts, số kết nối từ phía hạ tầng
  v
Spring Security filter chain
  |
  v
JsonLoginRequestGuardFilter
  |-- method khác POST --------------------> 405 + Allow: POST
  |-- Content-Type hoặc encoding sai ------> 415
  |-- Content-Length >8192 ----------------> 413 ngay
  |-- đọc tối đa 8193 byte từ stream
  |    '-- nếu thấy byte thứ 8193 ---------> 413
  |-- đưa lại đúng body <=8192 byte
  v
CsrfFilter -------------------------------> 403 nếu CSRF sai
  v
Spring MVC / Jackson ---------------------> 400 nếu JSON không hợp lệ
  v
AuthenticationManager -------------------> 401 nếu credential sai
  |-- thành công: lưu SecurityContext
  '-- response ----------------------------> 204
```

Trong ví dụ, guard chạy **trước `CsrfFilter`**. Vì vậy request có method/media/size sai nhận đúng mã từ guard trước khi kiểm tra CSRF. Nếu triển khai filter theo thứ tự khác, một request thiếu token có thể bị `403` trước khi đạt tới `415`; hãy quyết định thứ tự và kiểm thử có chủ ý.

**Bắt buộc có hai bước kiểm tra kích thước:** từ chối sớm khi `Content-Length` đã vượt ngưỡng và **đếm số byte thực đọc** với giới hạn `MAX+1`. Body chunked có thể không có `Content-Length`. Số ký tự Java (`String.length()`) không tương đương số byte UTF-8: dấu tiếng Việt hoặc emoji thường cần nhiều byte.

## 3. Ví dụ Spring Boot / Spring Security có thể chạy

Trong dự án **Spring Boot 3.x** đã thiết lập plugin Gradle và Java 17+, bổ sung:

```groovy
// build.gradle - phần dependencies
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tạo các file cùng package `example.jsonlogin`.

### 3.1. Khởi động ứng dụng

**`src/main/java/example/jsonlogin/JsonLoginApplication.java`**

```java
package example.jsonlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonLoginApplication.class, args);
    }
}
```

### 3.2. Cấu hình SecurityFilterChain

**`src/main/java/example/jsonlogin/SecurityConfig.java`**

```java
package example.jsonlogin;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.Customizer;
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
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfFilter;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            AuthenticationConfiguration config) throws Exception {
        return config.getAuthenticationManager();
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            SecurityContextRepository repository) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/login").permitAll()
                .anyRequest().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .securityContext(context -> context
                .securityContextRepository(repository))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .addFilterBefore(new JsonLoginRequestGuardFilter(), CsrfFilter.class);

        return http.build();
    }
}
```

Cấu hình này tắt form login mặc định vì controller riêng sẽ nhận JSON. Nó **vẫn bật CSRF**, vì xác thực sử dụng session cookie. `JsonLoginRequestGuardFilter` được đăng ký **một lần** thông qua `addFilterBefore`; không đồng thời thêm `@Component` hoặc `FilterRegistrationBean` cho cùng filter. Demo dùng BCrypt để mã hóa mật khẩu lưu trong bộ nhớ; thông tin demo không được dùng trong production.

### 3.3. Bộ lọc kiểm tra method, Content-Type và số byte thực đọc

**`src/main/java/example/jsonlogin/JsonLoginRequestGuardFilter.java`**

```java
package example.jsonlogin;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

final class JsonLoginRequestGuardFilter extends OncePerRequestFilter {
    static final int MAX_BODY_BYTES = 8192;

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String relativePath = request.getRequestURI()
                .substring(request.getContextPath().length());
        return !"/api/login".equals(relativePath);
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        if (!"POST".equals(request.getMethod())) {
            response.setHeader("Allow", "POST");
            response.sendError(405);
            return;
        }

        if (!isUtf8Json(request.getContentType()) ||
                !isIdentityEncoding(request.getHeader("Content-Encoding"))) {
            response.sendError(415);
            return;
        }

        // Từ chối sớm nếu client đã khai báo vượt ngưỡng.
        if (request.getContentLengthLong() > MAX_BODY_BYTES) {
            response.sendError(413);
            return;
        }

        // Giới hạn theo byte thực đọc, kể cả Content-Length không có.
        // MAX+1 chỉ đọc thêm một byte để biết đã vượt ngưỡng.
        byte[] body = request.getInputStream().readNBytes(MAX_BODY_BYTES + 1);
        if (body.length > MAX_BODY_BYTES) {
            response.sendError(413);
            return;
        }

        // Stream gốc đã được đọc: bọc lại để Jackson có thể đọc đúng body.
        chain.doFilter(new BufferedRequest(request, body), response);
    }

    private static boolean isUtf8Json(String header) {
        if (header == null) {
            return false;
        }
        try {
            MediaType type = MediaType.parseMediaType(header);
            return "application".equalsIgnoreCase(type.getType())
                    && "json".equalsIgnoreCase(type.getSubtype())
                    && (type.getCharset() == null
                    || StandardCharsets.UTF_8.equals(type.getCharset()));
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    private static boolean isIdentityEncoding(String encoding) {
        return encoding == null || "identity".equalsIgnoreCase(encoding.trim());
    }

    // Minh họa cho Servlet MVC đồng bộ; không dùng như wrapper async.
    private static final class BufferedRequest extends HttpServletRequestWrapper {
        private final byte[] body;

        BufferedRequest(HttpServletRequest request, byte[] body) {
            super(request);
            this.body = body;
        }

        @Override
        public int getContentLength() {
            return body.length;
        }

        @Override
        public long getContentLengthLong() {
            return body.length;
        }

        @Override
        public ServletInputStream getInputStream() {
            ByteArrayInputStream input = new ByteArrayInputStream(body);
            return new ServletInputStream() {
                @Override
                public int read() {
                    return input.read();
                }

                @Override
                public boolean isFinished() {
                    return input.available() == 0;
                }

                @Override
                public boolean isReady() {
                    return true;
                }

                @Override
                public void setReadListener(ReadListener listener) {
                    throw new UnsupportedOperationException(
                        "Only synchronous Servlet reads are supported");
                }
            };
        }

        @Override
        public BufferedReader getReader() {
            return new BufferedReader(new InputStreamReader(
                getInputStream(), StandardCharsets.UTF_8));
        }
    }
}
```

**Giải thích các chốt quan trọng:**

- `"POST".equals(request.getMethod())` từ chối method khác trước khi request tới logic xác thực; trả thêm `Allow: POST` theo hợp đồng `405`.
- `MediaType.parseMediaType` phân tích media type và tham số, thay vì so sánh chuỗi nguyên văn `"application/json"` (sẽ từ chối nhầm `application/json;charset=UTF-8`). Ví dụ cố ý **không nhận** `text/plain`, `application/x-www-form-urlencoded`, `application/problem+json` hoặc charset không phải UTF-8.
- Giới hạn `Content-Encoding` trong demo tránh nhầm số byte nén với body JSON. Nếu ứng dụng có giải nén request thực sự, phải giới hạn **kích thước sau giải nén** ở đúng lớp thực hiện giải nén.
- `getContentLengthLong()` giúp chặn nhanh body lớn đã khai báo; `readNBytes(8193)` bảo vệ khi header thiếu hoặc thấp hơn dữ liệu mà Servlet cung cấp. Bộ lọc **không đọc toàn bộ request không giới hạn**.
- Wrapper giữ nguyên `byte[]` đã được xác minh để Jackson vẫn thấy body. Nếu filter đọc stream rồi gọi `chain.doFilter(request, response)` với request cũ, controller có thể thấy EOF.
- Ví dụ xử lý **Servlet sync**. Với async/non-blocking I/O phải có wrapper `ReadListener` đúng giao thức, hoặc chọn giải pháp giới hạn ingress/stream chuyên dụng. `setReadListener` ném exception trong đoạn minh họa này để tránh giả vờ hỗ trợ async.

**Kiểm tra tính nhất quán của URL:** `shouldNotFilter` so với URI đã bỏ context path. Nếu proxy rewrite, trailing slash, matrix parameters, URL encoding hay method override làm MVC coi một URL khác cũng là endpoint login, cần chuẩn hóa/từ chối những biến thể ấy hoặc đồng bộ matcher với router. Không để một URL vào được login controller mà bỏ qua kiểm soát kích thước.

### 3.4. Controller xác thực sau khi vượt qua bộ lọc

**`src/main/java/example/jsonlogin/JsonLoginController.java`**

```java
package example.jsonlogin;

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
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class JsonLoginController {
    private final AuthenticationManager manager;
    private final SecurityContextRepository repository;
    private final SessionAuthenticationStrategy sessionStrategy =
            new ChangeSessionIdAuthenticationStrategy();

    public JsonLoginController(AuthenticationManager manager,
                               SecurityContextRepository repository) {
        this.manager = manager;
        this.repository = repository;
    }

    public record LoginPayload(String username, String password) {}

    @PostMapping(path = "/login", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Void> login(@RequestBody LoginPayload payload,
                                      HttpServletRequest request,
                                      HttpServletResponse response) {
        if (payload == null
                || payload.username() == null
                || payload.password() == null
                || payload.username().isBlank()
                || payload.password().isBlank()
                || payload.username().length() > 128
                || payload.password().length() > 1024) {
            return ResponseEntity.badRequest().build();
        }

        Authentication authenticated;
        try {
            authenticated = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    payload.username(), payload.password()));
        } catch (AuthenticationException ex) {
            // Không tiết lộ username hay password nào là phần sai.
            SecurityContextHolder.clearContext();
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }

        // Với custom controller, cần áp dụng chiến lược session và lưu context.
        sessionStrategy.onAuthentication(authenticated, request, response);
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authenticated);
        SecurityContextHolder.setContext(context);
        repository.saveContext(context, request, response);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }
}
```

`@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)` là ràng buộc thứ hai ở MVC; `@RequestBody` chỉ parse sau khi guard đã giới hạn byte. Controller kiểm tra null/blank và độ dài từng trường, một **lớp validation độc lập** với trần kích thước tổng thể.

Vì đây là custom login stateful trong Spring Security 6, code minh họa gọi `SessionAuthenticationStrategy` và `SecurityContextRepository.saveContext` một cách tường minh. Production cần xem xét đầy đủ vòng đời CSRF token, login/logout, session fixation, session concurrency, audit và các hook authentication chuẩn; không tự nhận đoạn controller tối giản này bao phủ toàn bộ chính sách quản lý phiên.

## 4. Kiểm thử bằng MockMvc

Các bài test sau dùng **Spring Security filter chain thật**: không dùng `@WithMockUser` để giả lập đã đăng nhập, vì làm vậy không kiểm tra được luồng nhận credential JSON.

**`src/test/java/example/jsonlogin/JsonLoginBoundaryTest.java`**

```java
package example.jsonlogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class JsonLoginBoundaryTest {
    @Autowired
    MockMvc mvc;

    private static final String VALID_JSON =
        "{\"username\":\"alice\",\"password\":\"demo-pass\"}";

    @Test
    void wrongMethodsReturn405AndAllowHeader() throws Exception {
        mvc.perform(get("/api/login"))
            .andExpect(status().is(405))
            .andExpect(header().string("Allow", "POST"));

        mvc.perform(put("/api/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_JSON))
            .andExpect(status().is(405))
            .andExpect(header().string("Allow", "POST"));

        mvc.perform(delete("/api/login"))
            .andExpect(status().is(405));
    }

    @Test
    void missingOrWrongContentTypeReturns415() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf().asHeader())
                .content(VALID_JSON))
            .andExpect(status().is(415));

        mvc.perform(post("/api/login")
                .with(csrf().asHeader())
                .contentType(MediaType.TEXT_PLAIN)
                .content(VALID_JSON))
            .andExpect(status().is(415));

        mvc.perform(post("/api/login")
                .with(csrf().asHeader())
                .contentType("application/json; charset=ISO-8859-1")
                .content(VALID_JSON))
            .andExpect(status().is(415));
    }

    @Test
    void unsupportedContentEncodingReturns415() throws Exception {
        mvc.perform(post("/api/login")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Content-Encoding", "gzip")
                .content(VALID_JSON))
            .andExpect(status().is(415));
    }

    @Test
    void oversizedBodyReturns413() throws Exception {
        String oversized = VALID_JSON + " ".repeat(8193);

        mvc.perform(post("/api/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(oversized))
            .andExpect(status().is(413));
    }

    @Test
    void sizeIsMeasuredInUtf8Bytes() throws Exception {
        String json = "{\"username\":\"alice\",\"password\":\"demo-pass\","
                + "\"pad\":\"" + "ộ".repeat(3000) + "\"}";
        assertTrue(json.length() < 8192);
        assertTrue(json.getBytes(StandardCharsets.UTF_8).length > 8192);

        mvc.perform(post("/api/login")
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
            .andExpect(status().is(413));
    }

    @Test
    void exactly8192BytesIsAccepted() throws Exception {
        int padding = 8192
                - VALID_JSON.getBytes(StandardCharsets.UTF_8).length;
        String exact = VALID_JSON + " ".repeat(padding);
        assertEquals(8192, exact.getBytes(StandardCharsets.UTF_8).length);

        mvc.perform(post("/api/login")
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON)
                .content(exact))
            .andExpect(status().isNoContent());
    }

    @Test
    void utf8JsonWithParameterCanAuthenticateAndPersistSession()
            throws Exception {
        MvcResult result = mvc.perform(post("/api/login")
                .with(csrf().asHeader())
                .contentType("application/json; charset=UTF-8")
                .content(VALID_JSON))
            .andExpect(status().isNoContent())
            .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void missingCsrfStillReturns403() throws Exception {
        mvc.perform(post("/api/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_JSON))
            .andExpect(status().isForbidden());
    }

    @Test
    void badJsonIs400AndBadCredentialIs401() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{not-json"))
            .andExpect(status().isBadRequest());

        mvc.perform(post("/api/login")
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"alice\",\"password\":\"wrong\"}"))
            .andExpect(status().isUnauthorized());
    }
}
```

Chạy từ **dự án ví dụ Spring Boot**:

```bash
./gradlew test --tests example.jsonlogin.JsonLoginBoundaryTest
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat`. Khi thành công, lớp trên có **9 phương thức `@Test` đạt**. Đây là **kỳ vọng dựa trên code**, không phải khẳng định đã chạy trong môi trường này.

### Ý nghĩa của các assertion

- `405` chứng minh sai method bị từ chối ngay cả khi URI là `/api/login`.
- `415` phân biệt thiếu/sai `Content-Type` với JSON sai cú pháp. JSON-looking text gắn `text/plain` vẫn phải bị chặn.
- `413` ở ngưỡng trên và `204` ở đúng 8192 byte kiểm tra lỗi **off-by-one**. Test ký tự `ộ` minh họa sự khác biệt giữa code units Java và UTF-8 bytes.
- `400` xảy ra sau khi vượt qua method/media/size nhưng Jackson không parse được; `401` xảy ra khi JSON hợp lệ nhưng authentication thất bại.
- `csrf().asHeader()` là tiện ích cho test. Client web thực phải có cơ chế lấy token CSRF và gửi trong header; dùng JSON **không phải lý do tắt CSRF** với cookie session.
- Request `GET /api/me` sau login dùng chính session vừa được tạo, giúp xác nhận body đã replay và xác thực được lưu. Chỉ nhìn mã `204` của POST chưa đủ để đánh giá toàn luồng.

**Giới hạn kiểm thử:** `MockMvc` không mô phỏng hoàn hảo HTTP client gửi chunked body thực, truyền chậm, đóng kết nối giữa chừng, behavior của Tomcat hay reverse proxy. Cần thêm kiểm thử trên đường HTTP thật sau khi cấu hình hạ tầng.

## 5. Quan sát HTTP và phản hồi thực tế

Có thể kiểm tra từ DevTools Network hoặc HTTP client (trên HTTPS), với CSRF token và cookie được cấp hợp lệ.

**Đúng method + Content-Type + JSON + CSRF:**

```http
POST /api/login HTTP/1.1
Host: example.test
Content-Type: application/json; charset=UTF-8
X-CSRF-TOKEN: <token-hop-le>
Cookie: JSESSIONID=<session-id>

{"username":"alice","password":"demo-pass"}
```

Ký hiệu trong ngoặc nhọn chỉ là chỗ điền trong tài liệu. Thực tế client tính `Content-Length` tự động. Thành công trả `204 No Content`; request tiếp theo gửi cookie session và `GET /api/me` có body:

```text
alice
```

**Sai method:** `GET /api/login` trả `405`, có `Allow: POST`. **Sai media:** `POST /api/login` với `Content-Type: text/plain` dù body nhìn giống JSON sẽ trả `415`. **Body vượt ngưỡng:** request có 8193 byte sẽ trả `413`. Khi kiểm thử, dùng dữ liệu demo và không log mật khẩu thật, CSRF token hoặc session ID đang hoạt động.

## 6. Các lỗi thiết kế dễ gặp

| Cách làm chưa đủ | Vì sao có vấn đề | Cách sửa |
| --- | --- | --- |
| Chỉ so sánh `Content-Length <= 8192` | Body chunked có thể thiếu header; dữ liệu stream chưa được đếm | Dùng header để chặn sớm **và** giới hạn byte thực đọc |
| `@RequestBody String` rồi kiểm tra `String.length()` | MVC có thể đã đọc body lớn; Java UTF-16 code units không phải byte UTF-8 | Chặn trước parse; đo byte |
| `@RequestBody byte[]` rồi kiểm tra | Toàn bộ body đã có thể được cấp phát trước kiểm tra | Đọc tối đa `MAX+1` byte hoặc chặn ở ingress |
| Chỉ gắn `@PostMapping(consumes="application/json")` | Ràng buộc method/media, chưa giới hạn body | Thêm body guard và giới hạn hạ tầng |
| `server.tomcat.max-http-form-post-size=8KB` | Chủ yếu dành cho **form POST**, không phải giới hạn toàn diện JSON body | Kiểm soát Servlet JSON body riêng |
| `server.max-http-request-header-size` | Giới hạn header, không phải body | Tách body limit |
| Body có `Content-Type: application/json` thì chắc chắn đúng JSON | Header là lời khai của client, không phải kết quả parse | Jackson kiểm tra và trả `400` |
| Đọc stream để đo rồi cho request gốc đi tiếp | Stream đã bị tiêu thụ, Jackson nhận EOF | Replay đúng các byte đã được giới hạn |
| Chỉ dựa vào `Accept` hoặc tên đường dẫn `.json` | Không xác định format request body | Kiểm tra `Content-Type` |
| Tắt CSRF vì ứng dụng dùng JSON | Session cookie vẫn tự gửi trong browser | Giữ CSRF cho login stateful và cung cấp token đúng cách |
| Đăng ký guard hai lần | Thứ tự filter có thể sai và body bị đọc nhiều lần | Đăng ký duy nhất một lần |
| Chỉ chặn body trong application | Proxy/container vẫn có thể nhận/giữ body lớn trước đó | Đồng bộ giới hạn tại gateway/ingress |
| Đặt byte limit trước giải nén và tin rằng đã đủ | Body nén nhỏ có thể giải nén thành dữ liệu rất lớn | Giới hạn byte sau giải nén tại lớp xử lý giải nén |

**Body limit không thay thế data validation.** Dù body chỉ 8 KiB, vẫn cần kiểm tra null/blank, độ dài từng trường, schema JSON, số trường/độ sâu JSON khi thích hợp. Bên cạnh đó, cần rate limit, login attempt monitoring, timeout, connection cap, không ghi request body chứa mật khẩu và chính sách account phù hợp. Không nên dùng body limit như biện pháp duy nhất để chống credential stuffing hay denial-of-service.

**CORS/OPTIONS:** mẫu trên dành cho **same-origin**. Browser của SPA cross-origin có thể cần `OPTIONS` preflight trước `POST`. Nếu triển khai cross-origin, cấu hình CORS đúng lớp **trước guard**, chỉ cho phép origin/headers/methods cần thiết, xử lý preflight riêng rồi vẫn yêu cầu POST cho login. Không coi OPTIONS là một lần đăng nhập và không mở `Access-Control-Allow-Origin: *` cho request cookie có credentials.

**Compressed request:** mẫu từ chối `Content-Encoding: gzip`. Nếu proxy hoặc ứng dụng chủ động giải nén, cần xét body limit trên kích thước **sau giải nén** và tránh decompression bomb. **Đường dẫn:** matcher trong filter phải nhất quán với cách MVC/ingress xử lý path rewrite, slash, semicolon parameters và URL-encoded characters để tránh đi vòng giới hạn.

## 7. Phân biệt trách nhiệm giữa các tầng

```text
Gateway / reverse proxy: max body, connection count, request timeout
Servlet container: HTTP framing, parser, header limits
Spring Security filter: method/media/byte guard, CSRF, authorization
Spring MVC + Jackson: route, consumes, JSON parse, binding, validation
AuthenticationManager: xác thực danh tính và chính sách tài khoản
```

Giới hạn do hạ tầng áp trước có thể khiến request nhận status/body khác với ứng dụng. Ví dụ, `server.tomcat.max-http-form-post-size` là cấu hình form data của Tomcat; `server.tomcat.max-swallow-size` là giới hạn lượng request body bị nuốt bỏ trong các tình huống xử lý lỗi; `spring.codec.max-in-memory-size` là cấu hình thường gắn với **WebFlux**, không tự bảo vệ một controller Servlet `@RequestBody` theo giới hạn JSON 8 KiB này.

Với `Transfer-Encoding: chunked` hoặc request không có Content-Length, **phần đếm byte thực tế** là yêu cầu bắt buộc. Với request bị hạ tầng giải nén, phải xác định rõ lớp nào chịu trách nhiệm giới hạn số byte cuối cùng ứng dụng sử dụng. Trong hệ thống production, ưu tiên hạn chế body ngay sát mạng để tránh tiêu tốn băng thông/connection trước khi request tới code Java.

## 8. Checklist xác nhận hoàn thành

- [ ] `POST /api/login` là method duy nhất cho login; request method khác trả `405` và `Allow: POST`.
- [ ] Chỉ `application/json` (có thể kèm `charset=UTF-8`) được nhận; thiếu/sai `Content-Type` trả `415`.
- [ ] Mỗi request login được giới hạn theo **byte thực đọc**, kể cả `Content-Length` không có.
- [ ] Body **8192 byte** được phép đi tiếp, **8193 byte** bị `413`, kể cả với Unicode nhiều byte.
- [ ] Body vượt qua guard vẫn được Jackson đọc nguyên vẹn.
- [ ] JSON lỗi cú pháp nhận `400`; credential sai nhận `401`; thiếu CSRF nhận `403`.
- [ ] Không có đường dẫn/HTTP method biến thể nào vào được login controller mà bỏ qua guard.
- [ ] CSRF, HTTPS, cookie/session, ingress body limit, timeout và rate limit được kiểm tra độc lập.
- [ ] Đã phân biệt kết quả MockMvc với kiểm thử HTTP thật sau reverse proxy.
- [ ] Không log, echo hoặc lưu trữ body chứa mật khẩu, CSRF token hay session ID thật.

### Tài liệu tham khảo

- [Spring Framework — Mapping Requests (Servlet MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security — CSRF cho JavaScript applications](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security — MockMvc CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Boot — Common Application Properties (Tomcat)](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [MDN — HTTP 405](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/405), [HTTP 413](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/413), [HTTP 415](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/415)
