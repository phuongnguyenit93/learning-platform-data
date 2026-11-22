# Phản hồi thành công và thất bại nhất quán cho API đăng nhập JSON

> **Mục tiêu:** Thiết kế và triển khai phản hồi cho đăng nhập bằng JSON trong Spring Security để frontend luôn hiểu được **kết quả**, **mã HTTP**, **mã lỗi ổn định**, **thông điệp hiển thị** và **dữ liệu trả về**. Cùng một quy ước phải áp dụng cho cả lỗi phát sinh trong controller, Spring MVC và chuỗi lọc Spring Security.

## 1. Vì sao API đăng nhập JSON cần một hợp đồng phản hồi?

Khi frontend gọi **POST /api/auth/login** với username/password dạng JSON, kết quả có thể rơi vào nhiều nhánh: đăng nhập hợp lệ, JSON bị lỗi cú pháp, thiếu trường bắt buộc, sai mật khẩu, chưa đăng nhập khi gọi API được bảo vệ, đã đăng nhập nhưng thiếu quyền, token CSRF không hợp lệ hoặc server gặp sự cố.

Một hệ thống thiếu quy ước có thể trả **200** kèm **{"error":"Sai mật khẩu"}** khi đăng nhập thất bại; nhánh khác lại trả **302** tới trang HTML đăng nhập, còn lỗi từ filter chỉ có status **403** và body HTML. Frontend phải đoán từng trường hợp, khó kiểm thử và dễ xử lý sai.

**Nguyên tắc:** status HTTP nói đúng nhóm kết quả; body JSON có một cấu trúc được thống nhất; code là khóa ổn định cho máy; message là thông điệp cho người dùng; dữ liệu nhạy cảm và chi tiết nội bộ không bị tiết lộ.

Trong bài này, ví dụ dùng **Spring Boot 3.x, Spring Security 6.x, Java 17+, Spring MVC/Servlet** và **đăng nhập JSON bằng session cookie**. Đây là một mô hình cụ thể để minh họa đầy đủ các nhánh phản hồi. Nếu ứng dụng dùng JWT/OAuth2 và không lưu session, giữ nguyên nguyên tắc response nhưng phải thay cách duy trì xác thực.

## 2. Chọn một định dạng JSON nhất quán

Ví dụ quy ước cho mọi phản hồi API:

~~~json
{
  "success": true,
  "code": "LOGIN_SUCCESS",
  "message": "Đăng nhập thành công",
  "data": {
    "username": "alice"
  }
}
~~~

Khi thất bại:

~~~json
{
  "success": false,
  "code": "INVALID_CREDENTIALS",
  "message": "Tên đăng nhập hoặc mật khẩu không đúng",
  "data": null
}
~~~

Ý nghĩa từng trường:

| Trường | Kiểu dữ liệu | Quy tắc |
| --- | --- | --- |
| **success** | boolean | true cho thao tác thành công; false cho thao tác thất bại |
| **code** | string | Mã ổn định, phục vụ xử lý logic và i18n; không dùng message làm khóa |
| **message** | string | Thông điệp dễ hiểu, không lộ stack trace hay việc tài khoản có tồn tại |
| **data** | object / array / null | Dữ liệu có ích khi thành công; null cho lỗi trong ví dụ này |

Cấu trúc nhất quán **không có nghĩa mọi trường hợp đều trả 200**. HTTP status vẫn là tín hiệu chuẩn cho trình duyệt, công cụ quan sát, API gateway, retry logic và ứng dụng khách. Phần body bổ sung thông tin theo hợp đồng.

### 2.1. Bảng trạng thái cần thống nhất

| Tình huống | HTTP status | code minh họa | Ý nghĩa |
| --- | --- | --- | --- |
| Đăng nhập thành công | **200 OK** | LOGIN_SUCCESS | Xác thực đúng, session đã được thiết lập |
| Thiếu username/password hoặc JSON sai | **400 Bad Request** | INVALID_REQUEST / INVALID_JSON | Dữ liệu client không hợp lệ |
| Gửi sai Content-Type | **415 Unsupported Media Type** | UNSUPPORTED_MEDIA_TYPE | Endpoint yêu cầu application/json |
| Username không tồn tại hoặc sai mật khẩu | **401 Unauthorized** | INVALID_CREDENTIALS | Không xác thực được; thông điệp chung |
| Gọi tài nguyên cần đăng nhập nhưng chưa xác thực | **401 Unauthorized** | UNAUTHENTICATED | Client cần đăng nhập |
| Đã đăng nhập nhưng thiếu quyền | **403 Forbidden** | FORBIDDEN | Client không đủ quyền |
| CSRF token thiếu, hết hạn hoặc sai | **403 Forbidden** | CSRF_INVALID | Yêu cầu bị từ chối ở lớp bảo vệ CSRF |
| Đường dẫn không tồn tại | **404 Not Found** | NOT_FOUND | Tài nguyên hoặc route không tồn tại |
| HTTP method không được hỗ trợ | **405 Method Not Allowed** | METHOD_NOT_ALLOWED | Dùng sai phương thức |
| Quá số lần đăng nhập cho phép, nếu có rate limit | **429 Too Many Requests** | RATE_LIMITED | Chỉ trả khi chính sách giới hạn thực sự kích hoạt |
| Lỗi server không mong đợi | **500 Internal Server Error** | INTERNAL_ERROR | Không tiết lộ chi tiết hệ thống |

Phân biệt **401** (chưa xác thực hợp lệ) và **403** (đã xác thực nhưng không được phép) là đặc biệt quan trọng. Thiếu hoặc sai CSRF token cũng có thể bị chặn bằng 403 trước khi yêu cầu đi tới controller. Trường hợp này không được nhầm thành “sai mật khẩu”.

Một API có thể chọn **RFC 9457 Problem Details** cho lỗi thay vì cấu trúc minh họa ở trên. Cả hai cách đều hợp lý nếu nhóm thống nhất rõ hợp đồng, status và hành vi client; đừng ngẫu nhiên trộn nhiều kiểu body trong cùng một giao diện API.

## 3. Dòng xử lý thực tế của JSON login

~~~text
Client
  |
  | POST /api/auth/login, Content-Type: application/json
  | Cookie phiên + CSRF token (nếu đăng nhập bằng session)
  v
Spring Security Filter Chain
  |-- CSRF sai/thiếu ----------> 403 JSON (CSRF_INVALID)
  |-- Điều kiện truy cập ------> cho phép request tới login
  v
Spring MVC / JSON deserialization
  |-- Body JSON không hợp lệ --> 400 JSON (INVALID_JSON)
  |-- Thiếu trường -----------> 400 JSON (INVALID_REQUEST)
  v
AuthenticationManager
  |-- Sai thông tin ----------> 401 JSON (INVALID_CREDENTIALS)
  |-- Đúng -------------------> tạo SecurityContext
  v
Lưu SecurityContext vào session
  |
  v
200 JSON (LOGIN_SUCCESS) + cookie phiên
~~~

Các lỗi ở **filter chain** thường xảy ra trước khi Spring MVC tìm controller. Vì thế, một **@RestControllerAdvice** đơn lẻ không thể bảo đảm toàn bộ lỗi 401/403 đều trả JSON. Cần cấu hình **AuthenticationEntryPoint** và **AccessDeniedHandler** trong Spring Security, đồng thời xử lý lỗi parse/validation trong Spring MVC.

Đăng nhập thành công mới chỉ có nghĩa **AuthenticationManager** đã chấp nhận credential. Để yêu cầu sau tiếp tục nhận diện user trong mô hình session, phải lưu **SecurityContext** qua **SecurityContextRepository**; chỉ trả JSON 200 mà không lưu context thì lần gọi sau vẫn có thể bị 401.

## 4. Ví dụ Spring Boot thực hành với một hợp đồng phản hồi

### 4.1. Chuẩn bị dự án

Dùng Spring Initializr tạo project **Spring Boot 3.x**, Java **17 hoặc mới hơn**, với các dependency **Spring Web** và **Spring Security**. Ví dụ dưới đây dùng namespace **com.example.demo** và các class tương ứng trong **src/main/java/com/example/demo/**. Dự án Spring Initializr đã có class **DemoApplication** chứa **@SpringBootApplication** và phương thức main; không cần thay đổi bootstrap.

Thêm vào **src/main/resources/application.properties**:

~~~properties
server.port=8080
demo.user.password=${DEMO_USER_PASSWORD}
~~~

Ở local, cung cấp giá trị **DEMO_USER_PASSWORD=demo-pass** trước khi chạy. Không đưa mật khẩu thật vào file source. HTTP ở localhost trong ví dụ chỉ để thực hành; **production phải dùng HTTPS**, xác minh certificate và đặt cookie **Secure**, **HttpOnly**, **SameSite** phù hợp với kiến trúc.

### 4.2. Tạo một kiểu response dùng chung

Tệp **ApiResponse.java**:

~~~java
package com.example.demo;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.ALWAYS)
public record ApiResponse<T>(
        boolean success,
        String code,
        String message,
        T data) {

    public static <T> ApiResponse<T> ok(
            String code, String message, T data) {
        return new ApiResponse<>(true, code, message, data);
    }

    public static <T> ApiResponse<T> fail(
            String code, String message) {
        return new ApiResponse<>(false, code, message, null);
    }
}
~~~

Bản ghi **record** của Java 17 được Jackson trong Spring Boot hỗ trợ serialize sang JSON. Annotation **@JsonInclude(ALWAYS)** bảo đảm trường **data** xuất hiện kể cả khi null, ngay cả khi ứng dụng có cấu hình loại bỏ trường null toàn cục. Với mọi nhánh thất bại, **ApiResponse.fail(...)** tạo ra cùng một hình dạng.

### 4.3. Ghi JSON từ filter hoặc handler trước Spring MVC

Các xử lý bảo mật ở tầng filter không trả **ResponseEntity** như controller. Ta dùng **ObjectMapper** để ghi trực tiếp body JSON.

Tệp **JsonHttp.java**:

~~~java
package com.example.demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;

public final class JsonHttp {
    private JsonHttp() {}

    public static void write(
            ObjectMapper mapper,
            HttpServletResponse response,
            int status,
            ApiResponse<?> body) throws IOException {
        response.setStatus(status);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setHeader("Cache-Control", "no-store");
        mapper.writeValue(response.getOutputStream(), body);
    }
}
~~~

Dùng chung **ApiResponse** và **JsonHttp** cho các nhánh bảo mật giúp tránh trường hợp **401** có HTML trong khi **400** lại có JSON. Header **Cache-Control: no-store** hạn chế cache phản hồi chứa thông tin tài khoản. Response đăng nhập không trả về password, password hash hay toàn bộ principal nội bộ.

### 4.4. Cấu hình Spring Security: 401/403 JSON, login JSON và session

Tệp **SecurityConfig.java**:

~~~java
package com.example.demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
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
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.csrf.InvalidCsrfTokenException;
import org.springframework.security.web.csrf.MissingCsrfTokenException;
import jakarta.servlet.DispatcherType;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String rawPassword) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode(rawPassword))
                        .roles("USER")
                        .build());
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
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
            CsrfTokenRepository csrfTokens) {
        return new CompositeSessionAuthenticationStrategy(List.of(
                new ChangeSessionIdAuthenticationStrategy(),
                new CsrfAuthenticationStrategy(csrfTokens)));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ObjectMapper mapper,
            SecurityContextRepository contexts,
            CsrfTokenRepository csrfTokens) throws Exception {

        http
            .csrf(csrf -> csrf.csrfTokenRepository(csrfTokens))
            .securityContext(s -> s.securityContextRepository(contexts))
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers("/error").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/auth/csrf").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/auth/login").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint((req, res, ex) ->
                    JsonHttp.write(mapper, res, 401,
                        ApiResponse.fail("UNAUTHENTICATED",
                            "Vui lòng đăng nhập")))
                .accessDeniedHandler((req, res, ex) -> {
                    boolean csrfProblem =
                        ex instanceof MissingCsrfTokenException
                        || ex instanceof InvalidCsrfTokenException;
                    JsonHttp.write(mapper, res, 403,
                        ApiResponse.fail(
                            csrfProblem ? "CSRF_INVALID" : "FORBIDDEN",
                            csrfProblem
                                ? "CSRF token không hợp lệ"
                                : "Bạn không có quyền thực hiện thao tác này"));
                }))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .requestCache(AbstractHttpConfigurer::disable)
            .logout(logout -> logout
                .logoutUrl("/api/auth/logout")
                .logoutSuccessHandler((req, res, auth) ->
                    JsonHttp.write(mapper, res, 200,
                        ApiResponse.ok(
                            "LOGOUT_SUCCESS",
                            "Đăng xuất thành công", null))));

        return http.build();
    }
}
~~~

Cấu hình thể hiện các quyết định quan trọng:

1. **formLogin** và **httpBasic** bị tắt để không sinh redirect tới trang HTML hay lời thách thức Basic ngoài hợp đồng JSON.
2. **AuthenticationEntryPoint** trả **401 JSON** khi chưa đăng nhập. **AccessDeniedHandler** trả **403 JSON** khi thiếu quyền hoặc CSRF sai. Spring Security dùng handler này cho **CsrfFilter** khi cấu hình trên áp dụng.
3. **HttpSessionSecurityContextRepository** lưu Authentication giữa các request theo cookie phiên. Vì ví dụ không phát hành JWT, **không** bật chính sách **STATELESS**.
4. **ChangeSessionIdAuthenticationStrategy** đổi session ID khi đăng nhập, giúp chống session fixation. **CsrfAuthenticationStrategy** hủy CSRF token cũ sau đăng nhập; client phải lấy token mới cho các POST tiếp theo.
5. **DaoAuthenticationProvider** đối chiếu password qua **BCryptPasswordEncoder**. User trong bộ nhớ phục vụ bài học, không phải mô hình quản lý tài khoản production.
6. Endpoint **/api/admin** yêu cầu quyền **ROLE_ADMIN**. User mẫu chỉ có **ROLE_USER**, giúp minh họa phản hồi **403** sau khi xác thực.
7. Spring Security xử lý logout tại **POST /api/auth/logout** và trả **200 JSON** qua logoutSuccessHandler. Yêu cầu logout cũng phải có CSRF token hợp lệ.

Lưu ý: đăng nhập JSON thực hiện ở controller tự viết, do đó ví dụ gọi thủ công **SessionAuthenticationStrategy** và lưu **SecurityContext**. Các filter đăng nhập do Spring Security cung cấp thường tự làm những bước này theo cấu hình của chúng.

### 4.5. Controller: JSON login, CSRF và API được bảo vệ

Tệp **AuthController.java**:

~~~java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
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
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class AuthController {
    private final AuthenticationManager authenticationManager;
    private final SecurityContextRepository contexts;
    private final SessionAuthenticationStrategy sessions;

    public AuthController(
            AuthenticationManager authenticationManager,
            SecurityContextRepository contexts,
            SessionAuthenticationStrategy sessions) {
        this.authenticationManager = authenticationManager;
        this.contexts = contexts;
        this.sessions = sessions;
    }

    public record LoginRequest(String username, String password) {}
    public record LoginView(String username) {}
    public record CsrfView(String headerName, String token) {}

    @GetMapping("/csrf")
    public ApiResponse<CsrfView> csrf(
            @RequestAttribute("_csrf") CsrfToken token) {
        return ApiResponse.ok("CSRF_READY", "CSRF token đã sẵn sàng",
                new CsrfView(token.getHeaderName(), token.getToken()));
    }

    @PostMapping("/login")
    public ResponseEntity<ApiResponse<?>> login(
            @RequestBody LoginRequest body,
            HttpServletRequest request,
            HttpServletResponse response) {

        if (body == null
                || body.username() == null || body.username().isBlank()
                || body.password() == null || body.password().isBlank()) {
            return ResponseEntity.badRequest().body(
                    ApiResponse.fail("INVALID_REQUEST",
                            "Cần nhập username và password"));
        }

        Authentication authenticated;
        try {
            authenticated = authenticationManager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            body.username(), body.password()));
        } catch (AuthenticationException ex) {
            return ResponseEntity.status(401).body(
                    ApiResponse.fail("INVALID_CREDENTIALS",
                            "Tên đăng nhập hoặc mật khẩu không đúng"));
        }

        sessions.onAuthentication(authenticated, request, response);
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authenticated);
        SecurityContextHolder.setContext(context);
        contexts.saveContext(context, request, response);

        return ResponseEntity.ok(
                ApiResponse.ok("LOGIN_SUCCESS", "Đăng nhập thành công",
                        new LoginView(authenticated.getName())));
    }
}
~~~

Controller thực hiện tuần tự: kiểm tra input; gọi **AuthenticationManager**; chuẩn hóa lỗi đăng nhập thành **401**; áp dụng bảo vệ session; tạo và lưu **SecurityContext**; sau đó trả **200 JSON**. Hai trường username/password sai không được trả thông điệp khác nhau, nhằm hạn chế việc dò tài khoản tồn tại.

Tệp **PrivateController.java**:

~~~java
package com.example.demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PrivateController {

    public record ProfileView(String username) {}

    @GetMapping("/api/me")
    public ApiResponse<ProfileView> me(Authentication authentication) {
        return ApiResponse.ok("PROFILE_OK", "Đọc hồ sơ thành công",
                new ProfileView(authentication.getName()));
    }

    @GetMapping("/api/admin")
    public ApiResponse<String> admin() {
        return ApiResponse.ok("ADMIN_OK", "Đã truy cập API quản trị",
                "admin");
    }
}
~~~

Client chưa đăng nhập gọi **GET /api/me** sẽ bị chặn trong Spring Security với **401 JSON**, chưa tới controller. User **alice** sau khi đăng nhập gọi **GET /api/me** sẽ nhận **200 JSON**; gọi **GET /api/admin** sẽ bị **403 JSON** do thiếu role, cũng chưa tới controller.

### 4.6. Chuẩn hóa lỗi JSON sai ở Spring MVC

Tệp **ApiExceptionHandler.java**:

~~~java
package com.example.demo;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiResponse<Void>> invalidJson(
            HttpMessageNotReadableException ex) {
        return ResponseEntity.badRequest().body(
                ApiResponse.fail("INVALID_JSON",
                        "Body phải là JSON hợp lệ"));
    }

    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    public ResponseEntity<ApiResponse<Void>> unsupportedMedia(
            HttpMediaTypeNotSupportedException ex) {
        return ResponseEntity.status(415).body(
                ApiResponse.fail("UNSUPPORTED_MEDIA_TYPE",
                        "Hãy gửi Content-Type: application/json"));
    }
}
~~~

**@RestControllerAdvice** xử lý lỗi Spring MVC, đặc biệt là lỗi JSON parse xảy ra **trước khi phương thức login() được gọi**. Nếu thêm Bean Validation (**@Valid**, **@NotBlank**, ...) cho DTO, cần bổ sung handler **MethodArgumentNotValidException** để trả **400** cùng cấu trúc. Việc bắt lỗi không nên đổi một lỗi server thành **200** hoặc trả nguyên thông báo exception chứa dữ liệu nhạy cảm.

### 4.7. Chuẩn hóa các lỗi điều hướng còn lại

Một số lỗi như **404**, **405** hoặc lỗi bất ngờ có thể đi qua cơ chế **/error** của Spring Boot thay vì controller advice. Tệp **ApiErrorController.java** minh họa cách biến các lỗi do servlet container chuyển vào **/error** thành cùng định dạng:

~~~java
package com.example.demo;

import jakarta.servlet.RequestDispatcher;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.web.servlet.error.ErrorController;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiErrorController implements ErrorController {

    @RequestMapping("/error")
    public ResponseEntity<ApiResponse<Void>> error(
            HttpServletRequest request) {
        Object raw = request.getAttribute(
                RequestDispatcher.ERROR_STATUS_CODE);
        int status = raw instanceof Integer value ? value : 500;

        String code = switch (status) {
            case 400 -> "INVALID_REQUEST";
            case 404 -> "NOT_FOUND";
            case 405 -> "METHOD_NOT_ALLOWED";
            case 415 -> "UNSUPPORTED_MEDIA_TYPE";
            default -> "INTERNAL_ERROR";
        };
        String message = switch (status) {
            case 400 -> "Yêu cầu không hợp lệ";
            case 404 -> "Không tìm thấy tài nguyên";
            case 405 -> "Phương thức HTTP không được hỗ trợ";
            case 415 -> "Kiểu dữ liệu không được hỗ trợ";
            default -> "Máy chủ không thể xử lý yêu cầu";
        };

        return ResponseEntity.status(status).body(
                ApiResponse.fail(code, message));
    }
}
~~~

Cách này dành cho demo API thuần JSON. Trong ứng dụng vừa có trang HTML vừa có REST, cần giới hạn chính sách JSON theo namespace API, path hoặc content negotiation để không thay đổi trang lỗi dành cho trình duyệt. Không phải mọi ngoại lệ đều được forward tới **/error**; các nhánh do framework hoặc middleware khác xử lý phải được kiểm tra riêng.

## 5. Gọi thử API và xác minh HTTP status + body

### 5.1. Khởi động

Với shell Linux/macOS và Maven wrapper do Spring Initializr tạo:

~~~bash
export DEMO_USER_PASSWORD=demo-pass
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
$env:DEMO_USER_PASSWORD = "demo-pass"
.\mvnw.cmd spring-boot:run
~~~

### 5.2. Lấy CSRF token trước khi đăng nhập

Vì ví dụ lưu xác thực trong session cookie, **POST /api/auth/login phải có CSRF token**. Endpoint GET cung cấp token qua JSON; client phải giữ nguyên cookie/session giữa các request.

~~~bash
curl -i -c cookies.txt -b cookies.txt http://localhost:8080/api/auth/csrf
~~~

Body minh họa (token thực tế thay đổi):

~~~json
{
  "success": true,
  "code": "CSRF_READY",
  "message": "CSRF token đã sẵn sàng",
  "data": {
    "headerName": "X-CSRF-TOKEN",
    "token": "<token-thực-tế>"
  }
}
~~~

Sao chép giá trị **data.token** thực tế. **Không** sao chép nguyên chuỗi minh họa trong dấu ngoặc nhọn hoặc ngoặc nhọn góc; nó không phải token hợp lệ.

### 5.3. Đăng nhập thành công và thất bại

Trên shell có **jq**, có thể trích token tự động:

~~~bash
TOKEN=$(curl -sS -c cookies.txt -b cookies.txt http://localhost:8080/api/auth/csrf | jq -r '.data.token')
curl -i -c cookies.txt -b cookies.txt -H "Content-Type: application/json" -H "X-CSRF-TOKEN: $TOKEN" --data '{"username":"alice","password":"demo-pass"}' http://localhost:8080/api/auth/login
~~~

Kỳ vọng **HTTP 200**:

~~~json
{
  "success": true,
  "code": "LOGIN_SUCCESS",
  "message": "Đăng nhập thành công",
  "data": {
    "username": "alice"
  }
}
~~~

Để minh họa **401** do sai password, lấy CSRF token hợp lệ (sau lần login thành công token đã được làm mới), rồi gửi sai mật khẩu:

~~~bash
TOKEN=$(curl -sS -c cookies.txt -b cookies.txt http://localhost:8080/api/auth/csrf | jq -r '.data.token')
curl -i -c cookies.txt -b cookies.txt -H "Content-Type: application/json" -H "X-CSRF-TOKEN: $TOKEN" --data '{"username":"alice","password":"wrong"}' http://localhost:8080/api/auth/login
~~~

Kỳ vọng **HTTP 401** và body:

~~~json
{
  "success": false,
  "code": "INVALID_CREDENTIALS",
  "message": "Tên đăng nhập hoặc mật khẩu không đúng",
  "data": null
}
~~~

Bài thử phía trên dùng cùng session đang đăng nhập; một lần đăng nhập thất bại không mặc nhiên xóa session trước đó. Trong bài kiểm thử thực tế, dùng cookie jar mới cho từng kịch bản độc lập để tránh kết quả bị ảnh hưởng bởi trạng thái đăng nhập trước.

### 5.4. Kiểm tra API được bảo vệ và phân quyền

Dùng session cookie vừa đăng nhập thành công:

~~~bash
curl -i -b cookies.txt http://localhost:8080/api/me
curl -i -b cookies.txt http://localhost:8080/api/admin
~~~

Dự kiến:

- **GET /api/me** trả **200**, **code=PROFILE_OK**, **data.username=alice**.
- **GET /api/admin** trả **403**, **code=FORBIDDEN**, vì tài khoản mẫu chỉ có **ROLE_USER**.
- Nếu dùng cookie jar mới, **GET /api/me** trả **401**, **code=UNAUTHENTICATED**.

### 5.5. Kiểm tra JSON hỏng và CSRF thất bại

Body JSON lỗi cú pháp nhưng có token hợp lệ:

~~~bash
TOKEN=$(curl -sS -c cookies.txt -b cookies.txt http://localhost:8080/api/auth/csrf | jq -r '.data.token')
curl -i -c cookies.txt -b cookies.txt -H "Content-Type: application/json" -H "X-CSRF-TOKEN: $TOKEN" --data '{"username":' http://localhost:8080/api/auth/login
~~~

Kỳ vọng **400**, **code=INVALID_JSON**. Nếu bỏ header CSRF mà vẫn gửi POST, **CsrfFilter** sẽ chặn trước khi parse JSON; khi đó thường nhận **403**, **code=CSRF_INVALID**. Đây là hành vi đúng: muốn thử riêng lỗi JSON cần trước hết gửi request vượt qua lớp CSRF.

### 5.6. Đăng xuất

Sau khi có session hợp lệ, lấy token mới rồi gọi:

~~~bash
TOKEN=$(curl -sS -c cookies.txt -b cookies.txt http://localhost:8080/api/auth/csrf | jq -r '.data.token')
curl -i -c cookies.txt -b cookies.txt -H "X-CSRF-TOKEN: $TOKEN" -X POST http://localhost:8080/api/auth/logout
curl -i -b cookies.txt http://localhost:8080/api/me
~~~

Kỳ vọng request logout trả **200** với **code=LOGOUT_SUCCESS** và **data=null**; yêu cầu **/api/me** tiếp theo trả **401** vì session đã bị vô hiệu hóa. Kiểm thử logout cần dùng cùng cookie jar và token được cấp cho session đó.

Các lệnh curl dùng HTTP tại **localhost** cho bài học. Không vận hành endpoint nhận mật khẩu trên HTTP ở môi trường triển khai; luôn dùng HTTPS. Lệnh có password minh họa không nên thay bằng mật khẩu thật vì process list, shell history hoặc công cụ giám sát có thể lưu lại.

## 6. Kiểm thử tự động cần xác nhận điều gì?

Một bài kiểm thử tốt phải kiểm tra **cả status lẫn body**, không chỉ “request chạy được”. Với Spring Security, **MockMvc** và **spring-security-test** là cách phổ biến để kiểm tra phản hồi; nếu kiểm tra end-to-end, cần chú ý cookie jar/session và CSRF như phần trên.

Bảng ca kiểm thử gợi ý:

| Test | Đầu vào | Status mong đợi | code mong đợi |
| --- | --- | --- | --- |
| Login hợp lệ | JSON đúng, CSRF đúng | 200 | LOGIN_SUCCESS |
| Sai password | JSON hợp lệ, credential sai, CSRF đúng | 401 | INVALID_CREDENTIALS |
| User không tồn tại | JSON hợp lệ, username lạ, CSRF đúng | 401 | INVALID_CREDENTIALS |
| Thiếu username | JSON thiếu trường, CSRF đúng | 400 | INVALID_REQUEST |
| JSON sai cú pháp | Body lỗi, CSRF đúng | 400 | INVALID_JSON |
| Thiếu CSRF | POST login không có CSRF hợp lệ | 403 | CSRF_INVALID |
| Chưa login gọi /api/me | GET không có session hợp lệ | 401 | UNAUTHENTICATED |
| User thiếu role gọi /api/admin | GET có session ROLE_USER | 403 | FORBIDDEN |
| Không có đường dẫn | GET route không tồn tại | 404 | NOT_FOUND |
| Logout hợp lệ | POST có session và CSRF | 200 | LOGOUT_SUCCESS |
| Gọi /api/me sau logout | GET với session đã bị vô hiệu | 401 | UNAUTHENTICATED |

Các assert hữu ích: header **Content-Type: application/json**, giá trị **success**, **code**, **message** và sự hiện diện của **data**; bảo đảm không có body HTML, redirect bất ngờ hoặc password trong response. Với lỗi nội bộ, kiểm tra body chỉ có thông điệp chung và chi tiết lỗi nằm trong log nội bộ theo trace/request ID.

Cần test độc lập từng ca để tránh session trước làm ảnh hưởng test sau. Riêng request POST, nếu đang kiểm tra lỗi dữ liệu, phải gửi CSRF hợp lệ trước; nếu đang kiểm tra CSRF, cố tình bỏ hoặc làm sai token.

## 7. Những lỗi phổ biến và cách sửa

### 7.1. Luôn trả HTTP 200 rồi đặt success=false

Cách này khiến client, API gateway và các dashboard vận hành khó phân biệt thành công/thất bại; retry hoặc analytics dễ sai. **Sửa:** dùng **400/401/403/429/500** đúng nguyên nhân, đồng thời giữ code lỗi trong body.

### 7.2. Dựa vào nội dung message để điều khiển frontend

Message có thể đổi ngôn ngữ hoặc cách viết. **Sửa:** xử lý theo **status** và **code** ổn định, ví dụ **INVALID_CREDENTIALS**; message chỉ để hiển thị hoặc hỗ trợ người dùng.

### 7.3. Chỉ viết @RestControllerAdvice rồi cho rằng đã xử lý 401/403

**AuthenticationEntryPoint** và **AccessDeniedHandler** có thể phát sinh phản hồi trước Spring MVC; thiếu cấu hình thường dẫn đến body khác kiểu hoặc redirect. **Sửa:** thống nhất response writer ở cả filter và controller.

### 7.4. Phân biệt “tài khoản không tồn tại” với “mật khẩu sai”

Trả hai thông báo riêng tạo tín hiệu để kẻ tấn công dò username. **Sửa:** cùng một mã **INVALID_CREDENTIALS** và cùng thông điệp chung; áp dụng giới hạn thử sai, logging và giám sát thích hợp.

### 7.5. Trả 200 thành công nhưng lần gọi kế tiếp luôn 401

Trong Spring Security 6, code tự xác thực bằng controller phải chủ động lưu **SecurityContext** nếu muốn session duy trì xác thực. **Sửa:** dùng **SecurityContextRepository.saveContext(...)** và cấu hình session tương ứng. Nếu chọn API stateless/token, thay thế bằng việc phát hành và xác minh credential/token theo thiết kế, không trộn hai mô hình.

### 7.6. Tắt CSRF vì POST /login bị 403

Khi ứng dụng dùng session cookie để xác thực trình duyệt, CSRF là rủi ro thực sự. **Sửa:** phát hành token, gửi token trong header cùng session và lấy token mới sau đăng nhập/đăng xuất theo cấu hình. Chỉ cân nhắc bỏ CSRF khi mô hình xác thực không dùng credential được trình duyệt tự động gửi và đã đánh giá mối đe dọa.

### 7.7. Trả lỗi kỹ thuật nội bộ trong message

Không nên đẩy exception, stack trace, query SQL, password, security token hoặc tên class nội bộ sang client. **Sửa:** body dùng mã lỗi công khai và thông điệp chung; chi tiết kỹ thuật để ở log/trace có kiểm soát.

### 7.8. Đồng nhất body mà bỏ quên 404/405/415 và lỗi từ proxy

Lỗi có thể phát sinh ở router, servlet container, security filter hoặc gateway. **Sửa:** lập bảng tình huống, kiểm tra bằng công cụ thực tế và chuẩn hóa ở đúng lớp phát sinh; tài liệu hóa các ngoại lệ do reverse proxy hoặc bên thứ ba trả về.

## 8. Quy tắc thiết kế để dùng trong dự án thật

1. **Chốt hợp đồng API**: chọn một response envelope hoặc Problem Details; xác định code, message, data và versioning.
2. **Dùng HTTP status chính xác**: 200 cho đăng nhập thành công; 400 cho dữ liệu lỗi; 401 cho xác thực lỗi; 403 cho thiếu quyền/CSRF; 429 chỉ khi rate limit áp dụng.
3. **Bảo vệ thông tin**: không trả mật khẩu, hash, stack trace, thông tin tồn tại tài khoản; không ghi credential vào log.
4. **Phân định các lớp**: filter xử lý Security 401/403, MVC advice xử lý parse/validation, error handling xử lý lỗi điều hướng hoặc lỗi container.
5. **Có hành vi xác thực sau login**: session được lưu, cookie được cấu hình an toàn hoặc token được phát hành theo mô hình được chọn.
6. **Thiết kế cho frontend**: kiểm tra code để hiển thị thông báo, điều hướng tới login khi UNAUTHENTICATED, báo thiếu quyền khi FORBIDDEN và không tự retry vô hạn khi INVALID_CREDENTIALS.
7. **Bảo vệ production**: dùng HTTPS, kiểm tra certificate, cookie Secure/HttpOnly/SameSite, CSRF cho xác thực bằng cookie, rate limiting và kiểm tra CORS cho đúng origin.
8. **Kiểm thử mọi đường lỗi**: xác nhận status/body cho success, failure trong controller, failure do Security, lỗi request và lỗi server.

## 9. Tài liệu tham khảo

- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/): AuthenticationManager, DaoAuthenticationProvider, UserDetailsService và PasswordEncoder.
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): lưu SecurityContext khi controller tự xác thực; quản lý session.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): yêu cầu CSRF đối với POST và cách dùng token với ứng dụng JavaScript.
- [Spring Security — Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html): thứ tự filter và xử lý lỗi xác thực/phân quyền.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): định dạng lỗi HTTP chuẩn có thể dùng thay envelope tùy hợp đồng của dự án.
