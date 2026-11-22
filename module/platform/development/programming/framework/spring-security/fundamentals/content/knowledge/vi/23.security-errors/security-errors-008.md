# Phản hồi JSON cho API và trang lỗi cho ứng dụng trình duyệt

## 1. Cùng một lỗi bảo mật, hai cách giao tiếp với người dùng

Một ứng dụng Spring Security có thể phục vụ đồng thời **REST API** và **trang web dùng trình duyệt**. Khi truy cập bị từ chối, cả hai phải tuân thủ cùng quy tắc xác thực (authentication) và phân quyền (authorization), nhưng **cách biểu diễn phản hồi** cần phù hợp với người nhận:

- **API** được chương trình khác gọi: trả **đúng mã HTTP**, `Content-Type` có thể xử lý bằng máy và một **JSON có cấu trúc ổn định**. Client phải phân biệt được chưa xác thực, không đủ quyền và lỗi hệ thống mà không cần phân tích HTML.
- **Trang web trình duyệt**: có thể **chuyển hướng tới trang đăng nhập** khi chưa có phiên đăng nhập; khi người dùng đã đăng nhập nhưng thiếu quyền, nên trả **403 cùng trang HTML giải thích lỗi**. Trình duyệt hiển thị nội dung cho người dùng, còn mã trạng thái vẫn phải chính xác.

Điểm mấu chốt: **mã HTTP thể hiện kết quả xử lý**, còn JSON hay HTML là **định dạng nội dung**. Không được biến một lỗi 403 thành 200 chỉ vì trang lỗi đã hiển thị thành công.

| Trường hợp | API điển hình | Website dùng form login |
| --- | --- | --- |
| Chưa gửi hoặc gửi sai thông tin xác thực | `401 Unauthorized`, JSON; với HTTP Basic kèm `WWW-Authenticate` | `302 Found` + `Location: /login` để người dùng đăng nhập |
| Đã xác thực nhưng thiếu quyền | `403 Forbidden`, JSON | `403 Forbidden`, trang HTML “Không có quyền truy cập” |
| Đăng nhập form thất bại | Không áp dụng nếu API dùng Basic/Bearer; endpoint login JSON riêng tùy thiết kế | Thường `302` tới `/login?error`, hiển thị thông báo trên trang login |
| Endpoint không tồn tại | `404 Not Found`, JSON theo hợp đồng API | Trang lỗi 404 HTML |
| Lỗi máy chủ chưa xử lý | `500 Internal Server Error`, JSON đã lược bỏ dữ liệu nhạy cảm | Trang lỗi 500 HTML |

Bảng mô tả **một thiết kế thường dùng**, không phải hành vi mặc định bắt buộc của mọi cấu hình Spring Security. Một endpoint API có thể chuyển hướng HTML nếu vô tình dùng `formLogin`; một trang web được cấu hình thuần API cũng có thể trả JSON. Ta phải cấu hình cụ thể cho từng nhóm URL.

### Ví dụ HTTP: API bị thiếu quyền

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "You do not have permission to access this resource",
  "instance": "/api/admin"
}
```

`application/problem+json` là định dạng **Problem Details** được chuẩn hóa trong RFC 9457. Các trường trên có nghĩa:

- `type`: định danh loại lỗi; `about:blank` dùng cho lỗi HTTP thông thường.
- `title`: tên ngắn gọn của loại lỗi, ví dụ `Forbidden`.
- `status`: mã HTTP tương ứng; phải khớp với status thực tế trong phản hồi.
- `detail`: giải thích an toàn cho client, không tiết lộ chính sách quyền nội bộ.
- `instance`: tài nguyên/yêu cầu cụ thể xảy ra lỗi; chỉ đưa thông tin đủ an toàn để công bố.

Cấu trúc có thể bổ sung `requestId` hoặc một mã lỗi ổn định của ứng dụng nếu client cần hỗ trợ theo dõi. Không nhét stack trace, token, session ID, mật khẩu hoặc nội dung nhạy cảm của principal vào JSON lỗi.

### Ví dụ HTTP: trình duyệt gặp lỗi 403

```http
HTTP/1.1 403 Forbidden
Content-Type: text/html;charset=UTF-8

<!doctype html>
<html lang="vi">
<head><meta charset="UTF-8"><title>403 - Không có quyền</title></head>
<body>
  <h1>Không có quyền truy cập</h1>
  <p>Tài khoản của bạn không được phép mở trang này.</p>
  <a href="/web/open">Về trang công khai</a>
</body>
</html>
```

Đây là **trang lỗi 403 thực sự**: browser nhận mã 403 và render HTML, dù người dùng nhìn thấy một trang hoàn chỉnh. Ngược lại, khi chưa đăng nhập và dùng form login, trình duyệt có thể nhận **302 → /login → 200**; mã 200 cuối là của **trang đăng nhập**, không phải của tài nguyên ban đầu.

## 2. Những thành phần xử lý lỗi trong Spring Security Servlet

Đối với ứng dụng Spring Boot 3.x / Spring Security 6.x dùng Servlet, cần phân biệt hai tầng:

1. **Tầng Spring Security filter** xử lý xác thực và phân quyền, nhiều khi trước khi yêu cầu chạm tới controller.
2. **Tầng Spring MVC và cơ chế trang lỗi Spring Boot** xử lý lỗi trong controller, quy trình MVC và các lỗi khác của ứng dụng.

Ở tầng Security:

- `AuthenticationEntryPoint` quyết định **cách bắt đầu xác thực** khi yêu cầu chưa đáp ứng điều kiện xác thực. API thường trả 401; web dùng form login thường chuyển hướng tới `/login`.
- `AccessDeniedHandler` quyết định **cách phản hồi khi quyền truy cập bị từ chối**. API có thể trả JSON 403; web có thể trả 403 và forward nội bộ tới trang HTML.
- `ExceptionTranslationFilter` chuyển những `AuthenticationException` và `AccessDeniedException` phát sinh ở các bộ lọc phía sau sang entry point hoặc access-denied handler phù hợp. Nó không tự kiểm tra mật khẩu hay cấp role.
- `BasicAuthenticationFilter` có đường xử lý thất bại xác thực riêng: nếu cấu hình HTTP Basic, nên chỉ định entry point cho `httpBasic(...)` **và** luồng `exceptionHandling(...)` để cả credentials sai lẫn yêu cầu không có credentials tạo phản hồi API dự kiến.
- `CsrfFilter` cũng có cách xử lý lỗi CSRF riêng. Một POST thiếu CSRF token có thể nhận 403 trước khi tới controller; cần kiểm tra luồng này nếu muốn mọi lỗi 403 của API đồng nhất.

Ở tầng MVC:

- `@RestControllerAdvice` / `@ExceptionHandler` thích hợp để chuẩn hóa lỗi ném từ **controller, service hoặc MVC**. Chúng **không thay thế** `AuthenticationEntryPoint` và `AccessDeniedHandler` cho ngoại lệ đã được xử lý trong security filter.
- Spring Boot có cơ chế xử lý lỗi chung (`/error`) và hỗ trợ trang lỗi HTML/template. Không nên xem cấu hình JSON tại MVC là đủ để bảo đảm lỗi bảo mật của API cũng trả JSON.

### Phân luồng theo URL thay vì suy đoán từ header

Một cách rõ ràng là định nghĩa **hai `SecurityFilterChain`**:

- `/api/**`: HTTP Basic hoặc Bearer token, trả JSON khi lỗi xác thực/phân quyền; không điều hướng đến giao diện đăng nhập.
- Các URL web: form login, redirect tới login khi chưa xác thực, HTML cho 403 sau khi xác thực.

Dùng `securityMatcher("/api/**")` để giới hạn **toàn bộ chuỗi lọc API**, sau đó dùng `requestMatchers(...)` bên trong để định nghĩa **quyền** cho từng endpoint. Phân biệt hai matcher này rất quan trọng: `requestMatchers("/api/**")` một mình không nhất thiết tách được cơ chế phản hồi JSON khỏi luồng form login.

Không dựa duy nhất vào `Accept: application/json`: không phải client nào cũng gửi header này; `fetch` có thể gửi `*/*` và một trang web hiện đại cũng có thể gọi API. Hợp đồng theo đường dẫn hoặc chuỗi bảo mật thường dễ kiểm chứng hơn. Nếu cần dùng nội dung thương lượng (content negotiation), phải quy định rõ precedence và kiểm thử các header thực tế.

## 3. Ví dụ thực hành Spring Boot: JSON Problem Details và trang HTML 403

Ví dụ dùng **Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet**. Tạo một dự án bằng Spring Initializr với `Spring Web` và `Spring Security`, chọn Gradle, Java 17 hoặc mới hơn. Trong `src/main/java/demo/security/SecurityResponseDemoApplication.java`, đặt lớp sau. Đây là **một chương trình Spring Boot hoàn chỉnh khi chạy trong dự án có các dependency nói trên**; không thể biên dịch bằng `javac` độc lập nếu chưa có thư viện Spring/Jackson.

```java
package demo.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityResponseDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityResponseDemoApplication.class, args);
    }

    @Bean
    AuthenticationEntryPoint apiEntryPoint(ObjectMapper mapper) {
        return (request, response, exception) -> {
            response.setHeader(
                "WWW-Authenticate",
                "Basic realm=\"demo-api\""
            );
            writeProblem(
                request, response, mapper, 401,
                "Unauthorized", "Authentication is required"
            );
        };
    }

    @Bean
    AccessDeniedHandler apiDeniedHandler(ObjectMapper mapper) {
        return (request, response, exception) ->
            writeProblem(
                request, response, mapper, 403,
                "Forbidden",
                "You do not have permission to access this resource"
            );
    }

    private static void writeProblem(
            HttpServletRequest request,
            HttpServletResponse response,
            ObjectMapper mapper,
            int status,
            String title,
            String detail) throws IOException {

        response.setStatus(status);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/problem+json");
        response.setHeader("Cache-Control", "no-store");

        Map<String, Object> problem = new LinkedHashMap<>();
        problem.put("type", "about:blank");
        problem.put("title", title);
        problem.put("status", status);
        problem.put("detail", detail);
        problem.put("instance", request.getRequestURI());

        mapper.writeValue(response.getWriter(), problem);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(
            HttpSecurity http,
            AuthenticationEntryPoint apiEntryPoint,
            AccessDeniedHandler apiDeniedHandler) throws Exception {

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/open").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(basic ->
                basic.authenticationEntryPoint(apiEntryPoint)
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(apiEntryPoint)
                .accessDeniedHandler(apiDeniedHandler)
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/web/open", "/access-denied")
                    .permitAll()
                .requestMatchers("/web/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .exceptionHandling(errors ->
                errors.accessDeniedPage("/access-denied")
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @RestController
    public static class DemoEndpoints {

        @GetMapping("/api/open")
        public Map<String, String> openApi() {
            return Map.of("message", "public api");
        }

        @GetMapping("/api/admin")
        public Map<String, String> adminApi() {
            return Map.of("message", "admin api");
        }

        @GetMapping(
            value = "/web/open",
            produces = MediaType.TEXT_HTML_VALUE
        )
        public String openWeb() {
            return "<!doctype html><html lang=\"vi\">"
                + "<meta charset=\"UTF-8\"><title>Trang công khai</title>"
                + "<body><h1>Trang công khai</h1>"
                + "<a href=\"/web/profile\">Hồ sơ</a></body></html>";
        }

        @GetMapping(
            value = "/web/profile",
            produces = MediaType.TEXT_HTML_VALUE
        )
        public String profile() {
            return "<!doctype html><html lang=\"vi\">"
                + "<meta charset=\"UTF-8\"><title>Hồ sơ</title>"
                + "<body><h1>Đã đăng nhập</h1></body></html>";
        }

        @GetMapping(
            value = "/web/admin",
            produces = MediaType.TEXT_HTML_VALUE
        )
        public String adminWeb() {
            return "<!doctype html><html lang=\"vi\">"
                + "<meta charset=\"UTF-8\"><title>Quản trị</title>"
                + "<body><h1>Trang quản trị</h1></body></html>";
        }

        @RequestMapping(
            value = "/access-denied",
            produces = MediaType.TEXT_HTML_VALUE
        )
        public ResponseEntity<String> deniedPage() {
            String html = """
                <!doctype html>
                <html lang="vi">
                <head>
                  <meta charset="UTF-8">
                  <title>403 - Không có quyền</title>
                </head>
                <body>
                  <h1>Không có quyền truy cập</h1>
                  <p>Tài khoản của bạn không được phép mở trang này.</p>
                  <a href="/web/open">Về trang công khai</a>
                </body>
                </html>
                """;

            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .contentType(MediaType.TEXT_HTML)
                .body(html);
        }
    }
}
```

### Tại sao cấu hình theo cách này?

**Chuỗi API** có `@Order(1)` và `securityMatcher("/api/**")` nên xử lý trước những URL dưới `/api/`. Chuỗi web có `@Order(2)` xử lý các URL còn lại. Quy tắc `hasRole("ADMIN")` đòi authority thực tế `ROLE_ADMIN`; người dùng `reader` chỉ có `ROLE_USER`, vì vậy đã xác thực nhưng gọi `/api/admin` vẫn bị 403.

Hai điểm của lỗi API cần cấu hình tường minh:

1. `.exceptionHandling(...authenticationEntryPoint(apiEntryPoint).accessDeniedHandler(apiDeniedHandler))` xử lý yêu cầu chưa xác thực và từ chối phân quyền trong luồng exception translation.
2. `.httpBasic(basic -> basic.authenticationEntryPoint(apiEntryPoint))` bảo đảm **credentials Basic không hợp lệ** được xử lý bằng entry point JSON của API. Chỉ cài handler trong `@RestControllerAdvice` không đạt mục tiêu đó.

`writeProblem(...)` dùng `response.setStatus(...)` rồi ghi JSON trực tiếp thay vì gọi `sendError(...)`. Cách này tránh một lần chuyển xử lý ngoài ý muốn tới cơ chế trang lỗi mặc định có thể đổi body. `ObjectMapper` tạo JSON với escape hợp lệ; chương trình không ghép chuỗi JSON bằng tay. Khi API yêu cầu xác thực bằng Basic, `401` phải có challenge `WWW-Authenticate`; mã đã đặt header này trong entry point. Lời giải thích lỗi giữ chung chung để không tiết lộ cấu trúc phân quyền.

**Chuỗi web** dùng `formLogin` để người chưa đăng nhập được hướng tới trang login mặc định. Khi người dùng đã xác thực nhưng không có quyền vào `/web/admin`, `accessDeniedPage("/access-denied")` dùng **forward nội bộ** đến nội dung HTML; mã HTTP vẫn là 403. Đây khác với `sendRedirect(...)`, bởi redirect tạo một yêu cầu mới và dễ dẫn đến 200 trên trang cuối cùng nếu lập trình viên không chủ động xử lý.

`/access-denied` được `permitAll()` để trang thông báo lỗi không bị chính quy tắc bảo mật chặn. Trong ứng dụng thực tế, có thể thay HTML hard-code bằng template Thymeleaf, Freemarker hoặc trang tĩnh được bố cục theo thiết kế; ví dụ cố ý dùng HTML trực tiếp để chỉ cần hai dependency và tập trung vào cơ chế status/định dạng.

**Không tắt CSRF trong ví dụ.** Các lệnh thử bên dưới đều là GET. Với ứng dụng dùng session, cookie hoặc HTTP Basic mà trình duyệt có thể tự đính kèm, vô hiệu hóa CSRF bừa bãi tạo rủi ro. Nếu triển khai API Bearer thực sự stateless, hãy đánh giá và cấu hình CSRF riêng theo mô hình xác thực. Mặc định CSRF có thể từ chối POST/PUT/DELETE thiếu token trước khi MVC chạy, và cách tạo JSON cho lỗi này cần được kiểm thử riêng.

### Chạy và kiểm thử API

Ở thư mục gốc dự án đã sinh Gradle Wrapper:

```bash
./gradlew bootRun
# Trên Windows:
# .\gradlew.bat bootRun
```

Gọi các endpoint bằng terminal khác:

```bash
curl -i http://localhost:8080/api/open

curl -i http://localhost:8080/api/admin

curl -i -u reader:reader123 http://localhost:8080/api/admin

curl -i -u admin:admin123 http://localhost:8080/api/admin
```

Kết quả cần kiểm tra:

| Yêu cầu | Status | `Content-Type` | Nội dung chính |
| --- | --- | --- | --- |
| `GET /api/open`, không credentials | **200** | `application/json` | `{"message":"public api"}` |
| `GET /api/admin`, không credentials | **401** | `application/problem+json` | `title: Unauthorized`; có `WWW-Authenticate: Basic ...` |
| `GET /api/admin`, credentials `reader` hợp lệ | **403** | `application/problem+json` | `title: Forbidden` |
| `GET /api/admin`, credentials `admin` hợp lệ | **200** | `application/json` | `{"message":"admin api"}` |
| `GET /api/admin`, mật khẩu Basic sai | **401** | `application/problem+json` | `title: Unauthorized`; có Basic challenge |

Ví dụ body cho trường hợp `reader` thiếu quyền (JSON được ghi với thứ tự trường ổn định trong bản minh họa nhờ `LinkedHashMap`, nhưng client **không được phụ thuộc vào thứ tự key**):

```json
{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "You do not have permission to access this resource",
  "instance": "/api/admin"
}
```

Nội dung phần header khác như `Date`, `Content-Length`, các header bảo mật và địa chỉ tuyệt đối/tương đối có thể khác theo phiên bản, middleware hoặc cấu hình. Đừng viết bài kiểm thử dựa vào thứ tự header hay chi tiết không thuộc hợp đồng API.

### Chạy và kiểm thử trình duyệt

Trên một **trình duyệt mới hoặc cửa sổ riêng tư**:

1. Mở `http://localhost:8080/web/open` khi chưa đăng nhập: trang HTML công khai hiện với **200**.
2. Mở `http://localhost:8080/web/profile`: yêu cầu ban đầu nhận **302** với `Location` dẫn tới `/login`; trình duyệt theo redirect và hiển thị trang login.
3. Đăng nhập bằng `reader / reader123`: yêu cầu trang hồ sơ đã lưu có thể được khôi phục, nhận HTML **200**.
4. Mở `http://localhost:8080/web/admin` trong phiên `reader`: nhận **403** và thấy trang HTML “Không có quyền truy cập”.
5. Đăng nhập bằng tài khoản `admin / admin123` trong phiên mới: mở `/web/admin` nhận **200** và nội dung quản trị.

Để xem phản hồi **302 đầu tiên** bằng terminal, dùng:

```bash
curl -i http://localhost:8080/web/profile
```

Đừng dùng `curl -L` khi muốn quan sát status ban đầu, vì `-L` tự theo redirect và có thể chỉ cho thấy kết quả sau cùng. Trong DevTools của trình duyệt, xem tab **Network**, bật giữ log qua các chuyển hướng nếu cần, rồi đối chiếu URL với status. Với `/web/admin` sau khi đăng nhập bằng `reader`, status phải là 403 ngay cả khi trang HTML đã render.

Tài khoản và mật khẩu chỉ phục vụ học tập trên `localhost`; `HTTP Basic` truyền chuỗi credentials theo Base64, **không phải mã hóa**. Trên mạng thật phải dùng HTTPS và cơ chế quản lý danh tính, secrets phù hợp; không đưa mật khẩu mẫu này vào production.

## 4. Các lựa chọn trang lỗi trên ứng dụng trình duyệt

Ví dụ trên tạo trang 403 bằng `@RequestMapping("/access-denied")` và `ResponseEntity` để dễ chạy. Với hệ thống có giao diện lớn, thường dùng template và tách nội dung khỏi Java:

- **Forward tới trang 403**: cấu hình `exceptionHandling(ex -> ex.accessDeniedPage("/access-denied"))`. Controller/view nhận forward, trả HTML với status **403**. Cho phép truy cập đường dẫn trang lỗi và bảo đảm có template/resource thực tế.
- **Viết HTML trực tiếp trong `AccessDeniedHandler`**: kiểm soát ngay status, headers, layout đơn giản; phù hợp trang thông báo nhỏ, nhưng không tiện bảo trì giao diện phức tạp.
- **Trang lỗi Spring Boot/MVC**: dùng các trang/template xử lý `404`/`500` của tầng MVC. Đây là nhóm lỗi khác với xác thực/phân quyền; cần cấu hình tránh lộ stack trace và chi tiết hệ thống.

Một ứng dụng web không nên tùy tiện chuyển mọi 403 tới `/login`: người đã đăng nhập nhưng thiếu quyền không cần bị yêu cầu đăng nhập lại mãi. Thông điệp trang 403 nên giải thích hành động bị từ chối, đưa điều hướng an toàn hoặc cách yêu cầu quyền, không công bố danh sách quyền nội bộ chi tiết.

Với form login tùy chỉnh, phải phục vụ được `GET /login` (hoặc URL đã cấu hình), cho phép truy cập những tài nguyên cần để hiển thị trang và giữ cơ chế gửi CSRF token trên form. Nếu trang login cũng bị bảo vệ, người dùng có thể gặp redirect lặp. Khi đăng nhập sai, `AuthenticationFailureHandler` xử lý kết quả của thao tác login; không nhầm nó với việc thiếu quyền truy cập sau khi đã đăng nhập.

## 5. Lỗi do MVC và lỗi do Security: chọn đúng vị trí định dạng phản hồi

Nếu dịch vụ Java ném lỗi trong controller/service, có thể dùng `@RestControllerAdvice` để chuẩn hóa mã và body JSON. Ví dụ sau là **minh họa một phần**, thêm vào dự án khi có lỗi nghiệp vụ `ResourceNotFoundException` của riêng ứng dụng:

```java
@RestControllerAdvice(assignableTypes = ApiResourceController.class)
class ApiErrorAdvice {

    @ExceptionHandler(ResourceNotFoundException.class)
    ResponseEntity<ProblemDetail> notFound(
            ResourceNotFoundException exception) {

        ProblemDetail body = ProblemDetail.forStatus(
            HttpStatus.NOT_FOUND
        );
        body.setTitle("Not Found");
        body.setDetail("The requested resource was not found");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .contentType(MediaType.parseMediaType(
                "application/problem+json"
            ))
            .body(body);
    }
}
```

`ApiResourceController` và `ResourceNotFoundException` trong đoạn này là **kiểu minh họa** của một API khác, không nằm trong ví dụ runnable `SecurityResponseDemoApplication` ở trên. Mục đích của đoạn mã là chỉ ra **ranh giới xử lý exception**: lỗi từ MVC/controller có thể chuẩn hóa tại advice, còn lỗi 401/403 của security filter cần cấu hình security handler riêng. Không áp dụng `catch (Exception)` rồi biến mọi lỗi thành 200 JSON.

Trong hệ thống thật, có thể chuẩn hóa một contract lỗi toàn API theo Problem Details:

| Loại lỗi | Nơi xử lý phù hợp | Gợi ý |
| --- | --- | --- |
| Chưa xác thực / sai Basic credentials | `AuthenticationEntryPoint` của API | 401 JSON + Basic challenge |
| Đã xác thực nhưng không đủ quyền | `AccessDeniedHandler` của API | 403 JSON, không lộ chính sách quyền |
| Thiếu/sai CSRF token | Xử lý CSRF và access-denied riêng theo luồng của ứng dụng | 403, kiểm thử body thực tế |
| Thiếu tài nguyên trong controller | `@ExceptionHandler` / `@RestControllerAdvice` | 404 JSON |
| Dữ liệu đầu vào sai trong MVC | Xử lý validation/MVC | 400 JSON với mã lỗi có thể dùng |
| Lỗi máy chủ | Xử lý lỗi tổng quát Boot/MVC | 500 JSON/HTML không lộ stack trace |
| Trình duyệt thiếu quyền | `AccessDeniedHandler` web, forward đến view | 403 HTML |
| Trình duyệt chưa đăng nhập | `AuthenticationEntryPoint` web | 302 tới login |

**Chú ý về tính đồng nhất:** định dạng JSON cho 401/403 ở ví dụ đảm bảo ở **các trường hợp GET được minh họa**. Nếu ứng dụng thêm CSRF, CORS, custom filter, method security, lỗi đường dẫn không khớp hoặc reverse proxy, từng lớp có thể tạo phản hồi riêng. Muốn cam kết “mọi lỗi `/api/**` luôn là JSON”, phải kiểm thử toàn bộ các điểm tạo lỗi, bao gồm các filter chạy trước controller và error dispatch. Không kết luận chỉ từ một handler.

## 6. Hành vi client phù hợp với loại phản hồi

Với client JavaScript gọi `/api/**`:

- **401**: kiểm tra lại trạng thái xác thực; trong hệ thống token có thể kích hoạt một lần làm mới token nếu cơ chế cho phép, hoặc đưa người dùng tới bước đăng nhập. Không lặp làm mới token vô hạn. Với Basic, 401 có challenge và client quyết định cung cấp credentials.
- **403**: phiên/credentials có thể hợp lệ nhưng thiếu quyền. Hiển thị thông báo từ thông điệp an toàn; không tự động coi 403 là “token hết hạn”.
- **302/HTML bất thường**: nếu API được thiết kế trả JSON mà client nhận trang login, kiểm tra có bị chuỗi web hoặc proxy chuyển hướng không. Một số `fetch` tự theo redirect và cuối cùng nhận `200 text/html`; `response.ok` lúc đó có thể là true dù body hoàn toàn sai contract.
- **5xx**: thông báo lỗi chung, ghi mã theo dõi, tránh đưa stack trace xuống UI. Retry chỉ khi phù hợp tính chất thao tác/idempotency.

Một nguyên tắc thực tế khi viết client:

```javascript
async function getAdminData() {
  const response = await fetch("/api/admin", {
    headers: { Accept: "application/problem+json, application/json" }
  });

  const mediaType = response.headers.get("Content-Type") ?? "";
  const isJson = mediaType.includes("json");

  if (response.status === 401) {
    throw new Error("Cần xác thực");
  }
  if (response.status === 403) {
    throw new Error("Không có quyền truy cập");
  }
  if (!response.ok) {
    throw new Error("Yêu cầu thất bại: " + response.status);
  }
  if (!isJson) {
    throw new Error("API trả về định dạng không mong đợi");
  }

  return response.json();
}
```

Đây là ví dụ **client của một API được thiết kế trả JSON**, không phải thành phần Java để biên dịch trong dự án Spring. Trong ví dụ HTTP Basic, trình duyệt chưa có credentials có thể hiển thị challenge và `fetch` có thể chịu ràng buộc CORS/cookie/authentication của trình duyệt. Ở ứng dụng production, cách lưu token/cookie, xử lý credential, CSRF và điều hướng phải được thiết kế rõ ràng; đoạn này chỉ tập trung vào **phân loại phản hồi**.

## 7. Cách kiểm tra và lỗi phổ biến

1. **Xem status đầu tiên**: request `/web/profile` không có phiên là 302; trang login sau khi redirect là 200. `/api/admin` không có Basic auth là 401, không phải 302.
2. **Xem `Content-Type`**: lỗi API phải có kiểu JSON đã cam kết, ví dụ `application/problem+json`; trang lỗi web dùng `text/html`. Đừng parse HTML như JSON.
3. **Xem các header quan trọng**: 401 Basic cần `WWW-Authenticate`; 302 login cần `Location`. Với phản hồi lỗi có thể chứa nội dung nhạy cảm, cân nhắc `Cache-Control: no-store`.
4. **Xem chuỗi lọc được chọn**: cấu hình `@Order`/`securityMatcher` sai có thể khiến API nhận form login và HTML; kiểm tra các URL có nằm trong matcher nào.
5. **Xem principal và authorities**: “đã đăng nhập” chưa chứng minh “đủ quyền”. `hasRole("ADMIN")` kiểm tra `ROLE_ADMIN`; `hasAuthority("ADMIN")` là phép kiểm tra chuỗi khác.
6. **Xem CSRF khi có POST/PUT/DELETE**: 403 có thể do thiếu token, không phải role. Không sửa bằng cách tắt CSRF toàn bộ ứng dụng.
7. **Xem điểm ném lỗi**: lỗi từ filter không được giải quyết chỉ bằng `@RestControllerAdvice`; lỗi MVC 404/validation lại cần cách xử lý ở MVC hoặc cơ chế `/error`.
8. **Đảm bảo trang lỗi có thể truy cập**: URL dùng để forward/hiển thị lỗi phải tồn tại và được cho phép; không tạo redirect/forward lặp.
9. **Giữ contract ổn định và an toàn**: status trong body khớp HTTP status, JSON escape đúng, không lộ stack trace, thông tin tài khoản hoặc bí mật nội bộ. Có thể dùng request ID để đối chiếu log máy chủ.

### Gợi ý kiểm thử tự động

Ở mức HTTP integration test với `MockMvc` hoặc test client, nên kiểm tra **status + Content-Type + trường JSON/HTML có ý nghĩa**, không so sánh toàn bộ HTML hoặc mọi header thay đổi theo phiên bản. Các kịch bản cốt lõi:

- `GET /api/admin` không xác thực → 401, `application/problem+json`, có Basic challenge.
- `GET /api/admin` với `reader` → 403, `application/problem+json`, `status` trong body bằng 403.
- `GET /api/admin` với `admin` → 200, body JSON dữ liệu.
- `GET /web/profile` chưa có phiên → 302 tới login.
- `GET /web/admin` với phiên `reader` → 403 và HTML.
- `GET /web/admin` với phiên `admin` → 200 và HTML.

Bổ sung test cho POST thiếu CSRF token, lỗi đường dẫn không tồn tại, exception từ MVC và trang lỗi tùy chỉnh khi sản phẩm có những trường hợp đó.

## 8. Kết luận thực hành

Khi xây dựng ứng dụng kết hợp API và giao diện trình duyệt, hãy đặt **quy tắc bảo mật** trong Spring Security và định nghĩa **cách biểu diễn phản hồi** theo nhóm client:

- **API:** 401/403 có JSON lỗi nhất quán (có thể theo Problem Details), không để redirect login HTML lọt vào client API.
- **Trình duyệt:** người chưa đăng nhập có thể nhận 302 tới login; người đã đăng nhập nhưng không có quyền nên thấy trang HTML 403 và status vẫn là 403.
- **MVC/ứng dụng:** xử lý 400/404/500 riêng ở `@RestControllerAdvice` hoặc cơ chế trang lỗi, không kỳ vọng chúng thay thế entry point/access-denied handler của security filter.
- **Kiểm chứng bằng HTTP thật:** status, Content-Type, WWW-Authenticate/Location, body và chuỗi redirect là những bằng chứng quyết định.

### Tài liệu tham khảo

- [Spring Security — Servlet Architecture và ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — SecurityFilterChain và securityMatcher](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Exception Handling](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
