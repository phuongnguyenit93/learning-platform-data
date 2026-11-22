# Đọc username, password từ JSON bằng AuthenticationConverter trong Spring Security

## 1. Bài toán: đăng nhập JSON trên ứng dụng Servlet

Khi xây dựng REST API hoặc frontend gửi dữ liệu bằng `fetch`/Axios, thông tin đăng nhập thường nằm trong **HTTP request body dạng JSON** thay vì form-urlencoded:

~~~http
POST /api/login HTTP/1.1
Host: localhost:8080
Content-Type: application/json
X-CSRF-TOKEN: <csrf-token-cua-phien>
Cookie: JSESSIONID=<session-cookie>

{"username":"student","password":"demo-password"}
~~~

Mục tiêu của bước **đọc dữ liệu** là biến nội dung request thành một `Authentication` **chưa xác thực**, sau đó đưa cho `AuthenticationManager` kiểm tra. Thành phần phù hợp trong **Spring Security Servlet** là `org.springframework.security.web.authentication.AuthenticationConverter`. Có thể kết hợp nó với `AuthenticationFilter` để xử lý POST đăng nhập.

Cần phân biệt ngay:
- `AuthenticationConverter` **trích xuất, kiểm tra cấu trúc đầu vào** và tạo yêu cầu xác thực. Nó **không đối chiếu mật khẩu** với cơ sở dữ liệu, **không mã hóa mật khẩu**, **không phát JWT** và **không tự lưu session**.
- `AuthenticationManager` chuyển yêu cầu xác thực đến provider thích hợp, ví dụ `DaoAuthenticationProvider` sử dụng `UserDetailsService` và `PasswordEncoder`.
- `AuthenticationFilter` phối hợp matcher, converter, manager, success/failure handler và khả năng lưu `SecurityContext`.
- Với JSON gửi vào `SecurityFilterChain`, `@RequestBody`/`HttpMessageConverter` của Spring MVC **không tự áp dụng cho authentication filter**. Nếu chọn hướng `@RestController` thì có thể dùng `@RequestBody`, nhưng người triển khai phải chủ động xử lý xác thực, `SecurityContext` và phiên sau đăng nhập.

Bài thực hành dùng **Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet MVC và session cookie**. Đăng nhập thành công trả JSON, không redirect. Phiên/cookie là một lựa chọn kiến trúc riêng; nếu muốn JWT hay xác thực stateless, cần xây dựng luồng phát và kiểm tra token độc lập.

## 2. Spring Security xử lý một lần đăng nhập JSON thế nào?

~~~text
POST /api/login, Content-Type: application/json
              |
              v
       SecurityFilterChain
       (CsrfFilter kiểm tra CSRF khi dùng session cookie)
              |
              v
  AuthenticationFilter: URL + HTTP method có khớp?
              |
              v
  JsonLoginAuthenticationConverter.convert(request)
       - kiểm tra Content-Type
       - đọc request.getInputStream() đúng một lần
       - Jackson ánh xạ JSON -> LoginJson
       - kiểm tra username/password
              |
              v
  UsernamePasswordAuthenticationToken.unauthenticated(...)
              |
              v
  AuthenticationManager (ProviderManager)
              |
              v
  DaoAuthenticationProvider
       UserDetailsService + PasswordEncoder
              |
        +-----+-----+
        |           |
     thất bại    thành công
        |           |
        v           v
  FailureHandler  SecurityContextHolder / SecurityContextRepository
        |           |
        v           v
   400/401/415   SuccessHandler: cập nhật session/CSRF, trả 200 JSON
~~~

Dùng `UsernamePasswordAuthenticationToken.unauthenticated(username, password)` để thể hiện rằng credentials mới được client cung cấp và **chưa được kiểm chứng**. Không tự tạo token có `authenticated=true` chỉ vì JSON hợp lệ.

Giao diện `AuthenticationConverter`:

~~~java
public interface AuthenticationConverter {
    Authentication convert(HttpServletRequest request);
}
~~~

Phương thức này có thể:
- Trả một `Authentication` chưa xác thực nếu request hợp lệ.
- Trả `null` khi converter không xử lý được request theo giao thức thiết kế; với endpoint login đã khớp matcher mà body sai, thường nên ném lỗi đầu vào rõ ràng để không cho request trôi sang filter/controller khác.
- Ném một `AuthenticationException` nếu cú pháp hoặc dữ liệu xác thực không hợp lệ; failure handler sẽ quyết định HTTP status và nội dung lỗi.

`AuthenticationConverter` khác `Converter<String, ...>` của Spring Core và `HttpMessageConverter` của Spring MVC. Với WebFlux, API tương ứng là `ServerAuthenticationConverter` nhận `ServerWebExchange`; không dùng trực tiếp ví dụ Servlet dưới đây trong ứng dụng reactive.

## 3. Các cách lấy username/password: chọn đúng lớp

| Thành phần | Nguồn dữ liệu thường dùng | Dùng khi nào |
| --- | --- | --- |
| `UsernamePasswordAuthenticationFilter` mặc định | `request.getParameter("username")` và `getParameter("password")`, thường từ form-urlencoded | Form login HTML truyền thống |
| `AuthenticationConverter` + `AuthenticationFilter` | Đọc `HttpServletRequest` và tạo `Authentication` tùy ý | Endpoint JSON login đi qua Spring Security filter chain |
| Spring MVC `@RequestBody LoginRequest` | Jackson đọc JSON sau khi tới controller | API login triển khai ở controller, có trách nhiệm xác thực/lưu context riêng |
| `ServerAuthenticationConverter` + `AuthenticationWebFilter` | Đọc `ServerWebExchange` (reactive) | Spring Security WebFlux |

Chỉ đổi `usernameParameter`/`passwordParameter` trong cấu hình form login **không** làm `UsernamePasswordAuthenticationFilter` mặc định tự parse JSON. `request.getParameter` không phải API để lấy hai thuộc tính trong JSON body. Tránh xử lý `HttpServletRequest.getInputStream()` trong nhiều filter; body thường chỉ đọc được một lần nếu không có wrapper cache phù hợp.

## 4. Ví dụ hoàn chỉnh: converter JSON + AuthenticationFilter + session

Ví dụ sau dùng tài khoản nội bộ để học, đồng thời trình bày các phần tối thiểu của một **JSON login có phiên dùng được ở request tiếp theo**.

Tạo dự án Spring Boot 3.5 / Spring Security 6.5 với Java 17, các dependency Maven:

~~~xml
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
~~~

Giữ phần parent/BOM và build plugin do Spring Initializr sinh ra. Đây là **đoạn dependencies** để thêm vào dự án Boot, không phải một file `pom.xml` độc lập.

File `src/main/java/com/example/jsonlogin/JsonLoginApplication.java`:

~~~java
package com.example.jsonlogin;

import java.io.IOException;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationConverter;
import org.springframework.security.web.authentication.AuthenticationFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

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
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        // Chỉ để minh họa; ứng dụng thật dùng kho người dùng phù hợp.
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager authenticationManager,
            ObjectMapper objectMapper) throws Exception {

        // Repository được dùng đồng thời để LƯU sau login
        // và ĐỌC ở các request dùng session tiếp theo.
        SecurityContextRepository contextRepository =
            new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository()
            );

        // Vì dùng cookie/session, POST login vẫn cần CSRF token.
        CsrfTokenRepository csrfRepository = new HttpSessionCsrfTokenRepository();

        AuthenticationFilter jsonLoginFilter = new AuthenticationFilter(
            authenticationManager,
            new JsonLoginAuthenticationConverter(objectMapper)
        );

        // Chỉ xử lý POST /api/login; GET /api/me không đọc JSON login.
        jsonLoginFilter.setRequestMatcher(
            new AntPathRequestMatcher("/api/login", "POST")
        );

        // AuthenticationFilter không tự lưu context trừ khi được cấu hình.
        jsonLoginFilter.setSecurityContextRepository(contextRepository);

        // AuthenticationFilter không có setter SessionAuthenticationStrategy.
        // Demo gọi các strategy phù hợp khi authentication thành công:
        SessionAuthenticationStrategy onLogin = new CompositeSessionAuthenticationStrategy(
            List.of(
                new ChangeSessionIdAuthenticationStrategy(),
                new CsrfAuthenticationStrategy(csrfRepository)
            )
        );

        jsonLoginFilter.setSuccessHandler((request, response, authentication) -> {
            onLogin.onAuthentication(authentication, request, response);
            response.setStatus(HttpServletResponse.SC_OK);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write("{\"status\":\"ok\"}");
        });

        jsonLoginFilter.setFailureHandler((request, response, failure) -> {
            int status = (failure instanceof InvalidLoginRequest bad)
                ? bad.httpStatus()
                : HttpServletResponse.SC_UNAUTHORIZED;
            // Không công khai password hoặc lý do username không tồn tại.
            response.setStatus(status);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write("{\"error\":\"login_failed\"}");
        });

        http
            .csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))
            .securityContext(security ->
                security.securityContextRepository(contextRepository))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/login").permitAll()
                .anyRequest().authenticated()
            )
            .exceptionHandling(ex -> ex.authenticationEntryPoint(
                (request, response, reason) ->
                    response.sendError(HttpServletResponse.SC_UNAUTHORIZED)
            ))
            .requestCache(cache -> cache.requestCache(new NullRequestCache()))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            // Gắn filter vào vị trí login mặc định trong filter chain.
            .addFilterAt(jsonLoginFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    // Hợp đồng JSON: {"username":"...","password":"..."}
    public record LoginJson(String username, String password) {
    }

    static final class JsonLoginAuthenticationConverter implements AuthenticationConverter {
        private final ObjectMapper objectMapper;

        JsonLoginAuthenticationConverter(ObjectMapper objectMapper) {
            this.objectMapper = objectMapper;
        }

        @Override
        public Authentication convert(HttpServletRequest request) {
            String rawType = request.getContentType();
            if (rawType == null) {
                throw new InvalidLoginRequest(415, "Content-Type required");
            }

            MediaType type;
            try {
                type = MediaType.parseMediaType(rawType);
            } catch (IllegalArgumentException ex) {
                throw new InvalidLoginRequest(415, "Unsupported Content-Type", ex);
            }
            if (!MediaType.APPLICATION_JSON.isCompatibleWith(type)) {
                throw new InvalidLoginRequest(415, "Expected application/json");
            }

            LoginJson credentials;
            try {
                credentials = objectMapper.readerFor(LoginJson.class)
                    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                    .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
                    .readValue(request.getInputStream());
            } catch (IOException ex) {
                throw new InvalidLoginRequest(400, "Malformed login JSON", ex);
            }

            if (credentials == null
                    || credentials.username() == null
                    || credentials.username().isBlank()
                    || credentials.username().length() > 128
                    || credentials.password() == null
                    || credentials.password().isEmpty()
                    || credentials.password().length() > 1024) {
                throw new InvalidLoginRequest(400, "Missing or invalid credentials");
            }

            // TUYỆT ĐỐI không tạo token authenticated=true ở đây.
            // Không trim hay sửa mật khẩu; giữ nguyên cho PasswordEncoder so khớp.
            return UsernamePasswordAuthenticationToken.unauthenticated(
                credentials.username(), credentials.password()
            );
        }
    }

    static final class InvalidLoginRequest extends AuthenticationException {
        private final int httpStatus;

        InvalidLoginRequest(int httpStatus, String message) {
            super(message);
            this.httpStatus = httpStatus;
        }

        InvalidLoginRequest(int httpStatus, String message, Throwable cause) {
            super(message, cause);
            this.httpStatus = httpStatus;
        }

        int httpStatus() {
            return httpStatus;
        }
    }

    @RestController
    static class ApiController {

        @GetMapping("/api/csrf")
        Map<String, String> csrf(HttpServletRequest request) {
            // CsrfFilter đưa CsrfToken vào request attribute.
            CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName()
            );
            return Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken()
            );
        }

        @GetMapping("/api/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("username", authentication.getName());
        }
    }
}
~~~

### Phân tích những điểm quan trọng trong ví dụ

**1. Converter chỉ nhận dữ liệu cấu trúc hợp lệ.** `MediaType.parseMediaType` xử lý `application/json` kèm tham số `charset`. Jackson đọc stream của request, ánh xạ đúng hai trường của record, từ chối các trường JSON không khai báo và token JSON thừa. Nếu thiếu giá trị hoặc body sai dạng, converter ném `InvalidLoginRequest`; failure handler trả 400. Media type không phải JSON trả 415.

**2. Token chưa xác thực đi đến manager.** Tại đây `DaoAuthenticationProvider` mới lấy mật khẩu mã hóa từ `UserDetailsService` và dùng `BCryptPasswordEncoder` để so khớp. Client không được gửi hoặc chọn cờ `authenticated` hay danh sách quyền. Thông báo khi sai username/password cố ý giống nhau, trả 401.

**3. Matcher bảo vệ phạm vi xử lý.** `AuthenticationFilter` chỉ chạy converter trên `POST /api/login`. JSON login không được “ngẫu nhiên” đọc từ mọi request. `.addFilterAt(...)` dùng vị trí được Spring Security biết; filter được tạo cục bộ trong `SecurityFilterChain`, tránh tình trạng đăng ký thêm một servlet filter ngoài security chain bằng `@Bean`.

**4. Session cần cấu hình hai phía.** `AuthenticationFilter` có thể đặt kết quả vào `SecurityContextHolder` cho request hiện tại; để request tiếp theo nhận lại phiên, đặt cùng một `SecurityContextRepository` vào filter (nơi lưu) và cấu hình `HttpSecurity.securityContext` (nơi đọc). Ví dụ dùng `DelegatingSecurityContextRepository` kết hợp request attribute và HTTP session.

**5. Session fixation và CSRF không biến mất khi đổi sang JSON.** Vì ví dụ dùng cookie/session, `CsrfFilter` vẫn bật. `ChangeSessionIdAuthenticationStrategy` thay session ID sau xác thực; `CsrfAuthenticationStrategy` xóa CSRF token cũ để token mới được cấp trong luồng tiếp theo. Trong `AuthenticationFilter` của Spring Security 6.x, các strategy này được gọi trong success handler của ví dụ; nếu dùng filter tùy biến khác, hãy cấu hình đúng vòng đời của nó. Sau login, frontend phải lấy CSRF token mới trước lần POST tiếp theo.

**6. Phản hồi 200 không phải JWT.** JSON `{"status":"ok"}` chỉ báo rằng việc xác thực thành công; ứng dụng tiếp tục nhận diện người dùng bằng session cookie. Nếu không giữ cookie, `GET /api/me` sau đó sẽ trả 401. Muốn stateless JWT cần thêm cơ chế cấp token, ký, hết hạn và resource-server kiểm tra token; không nên giả định JSON login tự động tạo JWT.

**7. Mã mẫu giới hạn theo phạm vi học tập.** User/password in-memory, thiếu rate limiting, giám sát, MFA, quản lý nhiều phiên và policy độ dài theo nghiệp vụ. Ứng dụng thực phải thay bằng kho user/identity provider, cấu hình cookie đúng môi trường (Secure/HttpOnly/SameSite), HTTPS và bảo vệ chống brute-force. Nếu thiết kế kiểm soát session đồng thời, dùng `SessionRegistry` và strategy tương ứng nhất quán, thay vì chỉ thêm `maximumSessions` và nghĩ filter tự nhận cấu hình.

## 5. Thử thủ công từ client

Chạy Maven wrapper ở thư mục dự án:

~~~bash
./mvnw spring-boot:run
~~~

Windows: `mvnw.cmd spring-boot:run`. Vì đây là ứng dụng Spring Boot có dependency, không dùng `javac JsonLoginApplication.java` độc lập.

Đầu tiên lấy cookie session và CSRF token:

~~~bash
curl -i -c cookies.txt http://localhost:8080/api/csrf
~~~

Ví dụ **hình dạng** phản hồi (token và cookie thay đổi mỗi lần):

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"headerName":"X-CSRF-TOKEN","token":"<token-duoc-cap>"}
~~~

Tiếp theo, dùng **giá trị token thực tế** vừa nhận, gửi cùng cookie, không điền nguyên văn placeholder:

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H 'Content-Type: application/json' \
  -H 'X-CSRF-TOKEN: <token-duoc-cap>' \
  -d '{"username":"student","password":"demo-password"}' \
  http://localhost:8080/api/login
~~~

Kỳ vọng `200 OK` và body:

~~~json
{"status":"ok"}
~~~

Dùng session cookie đã cập nhật sau login:

~~~bash
curl -i -b cookies.txt http://localhost:8080/api/me
~~~

Kỳ vọng `200 OK` và body:

~~~json
{"username":"student"}
~~~

Thử gửi mật khẩu sai với CSRF token hợp lệ thì nhận `401 Unauthorized`. Nếu thiếu CSRF token trên POST login, `CsrfFilter` chặn trước converter và nhận `403 Forbidden`. Nếu Content-Type là `text/plain` nhưng CSRF hợp lệ thì nhận `415 Unsupported Media Type`. Gửi JSON sai cú pháp hoặc thiếu trường thì nhận `400 Bad Request`. Sau đăng nhập thành công, CSRF token cũ bị xóa; trước POST ghi dữ liệu, gọi lại `GET /api/csrf` để lấy token mới.

Đối với frontend trình duyệt, phải giữ cookie ở các request cùng origin (hoặc cấu hình `credentials`/CORS/SameSite phù hợp trong thiết kế nhiều origin). **Không** lưu password trong localStorage, log request, URL/query string hoặc thông báo lỗi.

## 6. Kiểm thử bằng Spring Security Test và MockMvc

Trong cùng dự án, file `src/test/java/com/example/jsonlogin/JsonLoginApplicationTests.java`:

~~~java
package com.example.jsonlogin;

import jakarta.servlet.http.HttpSession;
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

    @Autowired
    MockMvc mvc;

    @Test
    void loginJsonSucceedsAndIsRememberedBySession() throws Exception {
        MvcResult result = mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"student\",\"password\":\"demo-password\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andReturn();

        HttpSession session = result.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session((MockHttpSession) session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("student"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"student\",\"password\":\"wrong\"}"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("login_failed"));
    }

    @Test
    void malformedJsonIsBadRequest() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void missingPasswordIsBadRequest() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"student\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void formEncodedInputIsNotAcceptedAsJsonLogin() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("username", "student")
                .param("password", "demo-password"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void missingCsrfIsForbiddenBeforeAuthentication() throws Exception {
        mvc.perform(post("/api/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"student\",\"password\":\"demo-password\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void protectedResourceNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

**Kỳ vọng khi môi trường và dependency được thiết lập đúng:** các test đi qua. Test thành công xác nhận ba việc riêng biệt: parse JSON, xác thực bằng provider và khôi phục authentication qua session. Đây là kiểm thử tích hợp mẫu cần **thực thi trong dự án thật**; việc đọc tài liệu không thay thế kết quả chạy test. Test CSRF và login thất bại đảm bảo không có nhánh bypass khi converter nhận request không hợp lệ.

Nếu ứng dụng có nhiều `SecurityFilterChain`, hãy kiểm tra đúng chain nhận `/api/login`; một `securityMatcher` quá hẹp có thể làm endpoint do filter cung cấp không bao giờ chạy.

## 7. Những lỗi thường gặp khi đọc JSON login

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `request.getParameter("username")` với body JSON | Trả null hoặc không nhận credentials | Dùng Jackson đọc `getInputStream()` trong `AuthenticationConverter` |
| Tự tin rằng `@RequestBody` chạy trong `AuthenticationFilter` | Filter chạy trước Spring MVC controller | Dùng converter cho filter; `@RequestBody` chỉ trong handler MVC |
| Tạo `UsernamePasswordAuthenticationToken` ở trạng thái authenticated | Client chưa được kiểm chứng nhưng bị xem là đăng nhập | Gọi `unauthenticated(username,password)` rồi `AuthenticationManager.authenticate` |
| Converter tự tra DB và so password bằng `equals` | Bỏ qua cơ chế provider/encoder và khó kiểm toán | Chỉ tạo token; giao kiểm chứng cho `DaoAuthenticationProvider` và `PasswordEncoder` |
| Không đặt `setRequestMatcher` | AuthenticationFilter có thể được áp dụng quá rộng | Chỉ khớp phương thức/path đăng nhập |
| Đọc body ở nhiều filter rồi parse tiếp | InputStream đã tiêu thụ | Chỉ đọc ở một vị trí, hoặc có wrapper cache có kiểm soát |
| Không phân biệt lỗi JSON và mật khẩu sai | Khó vận hành API; có thể lộ thông tin người dùng | 400/415 cho cấu trúc/media không hợp lệ, 401 chung cho credentials sai |
| Không lưu `SecurityContext` sau xác thực | Request kế tiếp trở lại 401 dù login trả 200 | Cấu hình `SecurityContextRepository` cho cả save và load |
| Dùng session cookie nhưng vô hiệu CSRF toàn cục | Tạo bề mặt CSRF cho API | Duy trì CSRF token, kiểm soát CORS/cookie, xoay token khi login |
| Bỏ qua session fixation và kiểm soát phiên | Tăng rủi ro khi dùng phiên có sẵn | Dùng session strategy phù hợp; áp dụng policy concurrency nếu cần |
| Log toàn bộ JSON login | Rò password | Redact credentials; log trạng thái và metadata an toàn |
| Coi JWT là kết quả tự động của JSON login | Frontend tưởng có token dù server chỉ tạo session | Thiết kế rõ session-based và token-based là hai luồng khác nhau |

## 8. Tăng độ vững chắc khi đưa vào production

- **Giới hạn đầu vào:** ràng buộc kích thước HTTP body ở proxy/servlet container; đặt giới hạn dài username/password theo sản phẩm; từ chối JSON thừa trường hoặc có cấu trúc bất thường; không đọc vô hạn từ request.
- **Giữ nguyên mật khẩu:** không gọi `trim()`, chuyển lowercase hoặc chuẩn hóa Unicode cho password trước khi so sánh trừ khi giao thức của sản phẩm có quy tắc nhất quán đã công bố. Không in exception/cause chứa raw body vào log.
- **HTTPS và cookie:** dùng HTTPS, cookie `HttpOnly` và `Secure` trong production, `SameSite` theo threat model, CORS allowlist chính xác; không cho mọi origin gửi credential.
- **Chống dò mật khẩu:** rate-limit theo tài khoản/IP theo quy tắc phù hợp, có giám sát và cảnh báo; cân nhắc MFA cho tài khoản nhạy cảm; không phân biệt lỗi “user không tồn tại” với “sai mật khẩu” trong phản hồi public.
- **CSRF đúng kiến trúc:** nếu frontend dùng session cookie (tự động đính kèm), giữ CSRF. Nếu API hoàn toàn stateless dùng bearer token trong header và không có cookie làm thông tin xác thực, chính sách CSRF có thể khác; cần đánh giá mọi auth mechanism trước khi tắt.
- **Không lẫn authorization:** login chỉ xác minh danh tính; mỗi endpoint vẫn cần `authorizeHttpRequests` hoặc method security. Không tin các trường `roles`, `isAdmin` nếu client tự gửi.
- **Thử nghiệm end-to-end:** kiểm tra Content-Type, JSON null, JSON array, trường thiếu/thừa, encoding, request quá lớn, mật khẩu sai, CSRF, session fixation, cookie sau login, hết hạn phiên và logout.
- **Phiên bản thư viện:** các API ví dụ nhắm Spring Security 6.x. Khi nâng lên Spring Security 7.x, kiểm tra lại matcher và API authentication/session theo tài liệu phiên bản tương ứng.

## 9. Câu hỏi tự kiểm tra

1. Vì sao `UsernamePasswordAuthenticationFilter` mặc định thường không đọc được `{"username":"..."}` từ HTTP JSON body?
2. Trong `AuthenticationConverter`, vì sao phải trả `UsernamePasswordAuthenticationToken.unauthenticated`?
3. `AuthenticationConverter` khác `DaoAuthenticationProvider` ở bước nào?
4. Vì sao JSON login trả 200 chưa đủ chứng minh request kế tiếp đã được đăng nhập?
5. Nếu dùng session cookie, vì sao `POST /api/login` vẫn có thể yêu cầu CSRF token?
6. Trường hợp nào dùng `@RequestBody` trong controller là phù hợp, và cần thêm bước gì để duy trì `SecurityContext`?
7. Vì sao không đăng ký cùng một `AuthenticationFilter` đồng thời làm servlet filter độc lập và filter bên trong Spring Security?

## 10. Nguồn tham khảo

1. Spring Security 6.5 — Servlet authentication architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
2. Spring Security 6.5 API — `AuthenticationConverter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AuthenticationConverter.html
3. Spring Security 6.5 API — `AuthenticationFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AuthenticationFilter.html
4. Spring Security 6.5 — Username/password authentication and `DaoAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/
5. Spring Security 6.5 — Session management / context persistence: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
6. Spring Security 6.5 — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
7. Spring Security — Testing with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html

**Ghi nhớ:** Khi endpoint đăng nhập nhận JSON trong **Servlet SecurityFilterChain**, hãy đặt việc parse request tại `AuthenticationConverter`, gửi token **chưa xác thực** cho `AuthenticationManager`, và cấu hình rõ success/failure, SecurityContext, session và CSRF theo cơ chế xác thực đã chọn.