# Thông báo nhất quán, mã tương quan và bảo vệ chi tiết nội bộ

## 1. Vì sao lỗi bảo mật phải có một hợp đồng phản hồi rõ ràng?

Khi một request bị từ chối, trình duyệt hoặc ứng dụng khách cần biết **có thể làm gì tiếp theo**: yêu cầu người dùng đăng nhập, thông báo thiếu quyền, sửa dữ liệu đầu vào hay thử lại sau. Đội vận hành cần biết **request nào đã thất bại** để tìm log. Nhưng một response gửi ra Internet không nên tiết lộ tên lớp Java, tên bảng SQL, cấu hình hệ thống, quy tắc phân quyền chi tiết, trạng thái tồn tại của tài khoản hoặc nội dung stack trace.

Ba mục tiêu cần đi cùng nhau:

1. **Nhất quán:** cùng loại lỗi có HTTP status, mã lỗi công khai (error code), cấu trúc JSON và cách hiển thị ổn định. Ứng dụng khách dựa vào `code` và status thay vì phân tích chuỗi ngoại lệ.
2. **Có thể truy vết:** mỗi request nhận một **mã tương quan (correlation ID)** để người dùng cung cấp cho bộ phận hỗ trợ, và để máy chủ liên kết các bản ghi log.
3. **Giữ kín chi tiết nội bộ:** response chỉ chứa thông tin cần thiết cho người gọi. Lý do kỹ thuật, stack trace và dữ liệu chẩn đoán nằm trong hệ thống log được bảo vệ, sau khi đã loại bỏ dữ liệu nhạy cảm.

Ví dụ, không trả cho người dùng:

```json
{
  "error": "org.postgresql.util.PSQLException",
  "message": "permission denied on relation customer_private",
  "sql": "select * from customer_private where email = ...",
  "stackTrace": ["demo.OrderService.load(OrderService.java:87)"]
}
```

Một phản hồi an toàn hơn:

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
Cache-Control: no-store
X-Correlation-ID: 82b9f5a3-a6aa-4ad5-8baf-61515d9e233a
```

```json
{
  "code": "INTERNAL_ERROR",
  "message": "Không thể xử lý yêu cầu lúc này.",
  "correlationId": "82b9f5a3-a6aa-4ad5-8baf-61515d9e233a"
}
```

Mã UUID trong ví dụ chỉ để minh họa cấu trúc; ở request thật máy chủ tạo giá trị riêng. Người dùng có thể báo mã đó cho đội hỗ trợ mà không cần gửi nội dung lỗi nhạy cảm.

Bài này áp dụng cho **Spring Security Servlet, Spring MVC, Java 17+ và Spring Boot 3.x/Spring Security 6.x**. Trên WebFlux phải dùng bộ lọc reactive và cách truyền ngữ cảnh khác; không sao chép `OncePerRequestFilter` hay `HttpSecurity` sang WebFlux.

## 2. Phân loại lỗi trước khi thiết kế thông báo

| Tình huống | HTTP status thường phù hợp | `code` công khai ví dụ | Thông điệp cho người dùng |
| --- | --- | --- | --- |
| Chưa xác thực, thiếu hoặc sai thông tin đăng nhập | `401 Unauthorized` cho API yêu cầu xác thực | `AUTHENTICATION_REQUIRED` | “Bạn cần đăng nhập để tiếp tục.” |
| Đã xác thực nhưng thiếu quyền | `403 Forbidden` | `ACCESS_DENIED` | “Bạn không có quyền truy cập tài nguyên này.” |
| Request không hợp lệ về cú pháp/đầu vào | `400 Bad Request` | `INVALID_REQUEST` | “Dữ liệu gửi lên chưa hợp lệ.” |
| Không tìm thấy tài nguyên, hoặc chính sách che giấu sự tồn tại của tài nguyên | `404 Not Found` | `RESOURCE_NOT_FOUND` | “Không tìm thấy tài nguyên.” |
| Thử quá nhiều lần trong thời gian ngắn | `429 Too Many Requests` | `RATE_LIMITED` | “Bạn đang gửi quá nhiều yêu cầu.” |
| Lỗi máy chủ ngoài dự kiến | `500 Internal Server Error` | `INTERNAL_ERROR` | “Không thể xử lý yêu cầu lúc này.” |
| Dịch vụ phụ thuộc tạm thời không dùng được | `503 Service Unavailable` | `SERVICE_UNAVAILABLE` | “Dịch vụ đang tạm thời gián đoạn.” |

Đây là bảng **chính sách đề xuất**, không phải mọi tình huống đều có status mặc định như trên. Ví dụ: ứng dụng web dùng form login thường chuyển hướng `302` sang trang đăng nhập; API JSON có thể chọn `401`. Nếu dùng HTTP Basic hoặc Bearer, phản hồi `401` cần giữ header `WWW-Authenticate` đúng cơ chế; không được xóa challenge để đổi lấy JSON đẹp. Trên OAuth 2 Resource Server, tuân theo quy tắc Bearer token và tránh tự tạo phản hồi sai chuẩn.

**Phân biệt ba trường hợp dễ nhầm:**

- **401:** request chưa được xác thực theo cơ chế mà tài nguyên yêu cầu. Tại phía client, nên yêu cầu đăng nhập hoặc làm mới phiên/token theo thiết kế.
- **403:** danh tính hiện tại đã được xác thực nhưng không có quyền với thao tác. Client không nên lặp vô hạn việc đăng nhập để “sửa” 403.
- **500:** lỗi không mong đợi từ phía máy chủ. Client không được thấy `NullPointerException`, chuỗi kết nối, tên máy chủ nội bộ hay SQL, dù log nội bộ có ghi sự kiện để điều tra.

Có trường hợp một `AccessDeniedException` từ người dùng anonymous được Spring Security đưa tới `AuthenticationEntryPoint`, còn người dùng đã xác thực được đưa tới `AccessDeniedHandler`. Bởi vậy **không thể chỉ lấy tên exception rồi suy ra status**; phải hiểu trạng thái xác thực và nơi exception được xử lý.

Đối với lỗi đăng nhập, quên mật khẩu và kiểm tra email, hãy tránh phản hồi tiết lộ “tài khoản này tồn tại” hay “email không có trong hệ thống” nếu người lạ có thể lợi dụng để dò danh sách tài khoản. Có thể dùng thông báo trung tính như “Nếu thông tin phù hợp, chúng tôi sẽ gửi hướng dẫn” và áp dụng giới hạn tốc độ.

## 3. Quy ước một phản hồi lỗi dùng được lâu dài

Chọn một hợp đồng JSON thống nhất cho các endpoint thuộc cùng nhóm client:

```json
{
  "code": "ACCESS_DENIED",
  "message": "Bạn không có quyền truy cập tài nguyên này.",
  "correlationId": "82b9f5a3-a6aa-4ad5-8baf-61515d9e233a"
}
```

- `code` là **mã lỗi ổn định** dành cho xử lý bằng chương trình; không dùng tên exception làm mã công khai. Khi thay đổi ngôn ngữ hiển thị, `code` vẫn giữ nguyên.
- `message` là câu dễ hiểu, ngắn, đủ hướng dẫn bước tiếp theo và **không phụ thuộc vào nội dung `Exception.getMessage()`**.
- `correlationId` là mã ngẫu nhiên không mang PII, dùng để đối chiếu request và log. Nó không chứng minh quyền truy cập, không phải mật khẩu/token và không được dùng làm nguồn xác thực.
- HTTP status truyền qua status line; không nhất thiết lặp trong JSON. Nếu tổ chức áp dụng RFC 9457 `ProblemDetail`, hãy giữ một định dạng thống nhất với các thuộc tính như `type`, `title`, `status`, `detail` và trường mở rộng `correlationId`; đừng trộn lẫn hai cấu trúc tùy tiện giữa các endpoint.

Với lỗi nhập liệu, có thể bổ sung danh sách tên trường và mã kiểm tra đã được phép công khai, chẳng hạn `{"field":"quantity","code":"MUST_BE_POSITIVE"}`. **Không trả giá trị người dùng vừa nhập** nếu nó có thể chứa password, access token, email riêng tư hoặc dữ liệu nhạy cảm. Cần có quy tắc rõ ràng cho trường nào được phép xuất hiện.

Đừng đặt một `200 OK` bao quanh `{"success": false}` cho tất cả lỗi. Làm vậy sẽ phá cách hoạt động của HTTP client, proxy, cache, metrics, retry và thông báo giám sát.

## 4. Lỗi đi qua đâu trong ứng dụng Spring Security Servlet?

Luồng điển hình:

```text
Request
  ↓
CorrelationIdFilter (gắn ID, response header, MDC cho log)
  ↓
Spring Security FilterChain
  ├─ xác thực thất bại / chưa xác thực → AuthenticationEntryPoint
  ├─ đã xác thực nhưng thiếu quyền → AccessDeniedHandler
  ├─ một số filter bảo vệ (ví dụ CSRF) có đường xử lý lỗi riêng
  ↓
DispatcherServlet / Controller
  ├─ exception trong Spring MVC → @RestControllerAdvice / MVC error handling
  └─ xử lý thành công → response bình thường
  ↓
Response có X-Correlation-ID, không chứa thông tin nội bộ
```

`@RestControllerAdvice` thông thường **không phải** điểm duy nhất để chuẩn hóa lỗi Spring Security: yêu cầu có thể đã bị chặn ở filter trước khi đến controller. Ngược lại, chỉ cấu hình `exceptionHandling(...)` trong Spring Security cũng không tự chuẩn hóa lỗi parse JSON, validation hay exception nghiệp vụ bên trong MVC.

Phân công trách nhiệm hợp lý:

- `AuthenticationEntryPoint` tạo phản hồi cho lỗi yêu cầu xác thực ở nơi Spring Security gọi entry point.
- `AccessDeniedHandler` tạo phản hồi khi quyền bị từ chối trong đường xử lý tương ứng.
- Bộ xử lý ngoại lệ MVC xử lý lỗi ứng dụng, validation và lỗi không mong đợi ở controller.
- Các điểm chặn khác như filter tự viết, CSRF, OAuth 2, servlet container và error dispatch phải có phép thử riêng, vì không phải mọi lỗi đều đi qua ba điểm trên.
- Một bộ viết response dùng chung giúp các đường đi nhất quán về cấu trúc JSON, header, thông điệp công khai.

## 5. Ví dụ hoạt động với Java 17 và Spring Boot 3.x

Ví dụ nhỏ dưới đây tạo một API dùng HTTP Basic để minh họa dễ kiểm thử. Nó có ba tình huống: chưa xác thực trả 401, tài khoản đã xác thực thiếu vai trò trả 403, controller lỗi trả 500. Mọi phản hồi lỗi có cùng JSON và mã tương quan. **Tài khoản demo chỉ dùng cho máy phát triển; HTTP Basic trong môi trường thật phải dùng HTTPS và chính sách quản lý thông tin xác thực phù hợp.**

Dự án Spring Boot cần có `spring-boot-starter-web`, `spring-boot-starter-security`; phần kiểm thử thêm `spring-boot-starter-test` và `spring-security-test`. Với Gradle Groovy DSL, các dependency trong `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Các lớp Java cùng package `demo.safeerror`. Đây là mã cho ứng dụng Spring Boot (chạy bằng công cụ build và classpath dependency), **không phải** các lớp độc lập chỉ cần lệnh `javac` không có thư viện.

### 5.1. Ứng dụng khởi động

Tệp `src/main/java/demo/safeerror/SafeApiErrorApplication.java`:

```java
package demo.safeerror;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeApiErrorApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeApiErrorApplication.class, args);
    }
}
```

### 5.2. Lấy mã tương quan ở đầu request

Tệp `src/main/java/demo/safeerror/CorrelationIdFilter.java`:

```java
package demo.safeerror;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class CorrelationIdFilter extends OncePerRequestFilter {
    public static final String HEADER = "X-Correlation-ID";
    private static final String ATTRIBUTE =
            CorrelationIdFilter.class.getName() + ".id";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {
        // Sinh ID mới ở ranh giới tin cậy, tránh bị client giả mạo mã của request khác.
        String id = UUID.randomUUID().toString();
        request.setAttribute(ATTRIBUTE, id);
        response.setHeader(HEADER, id);

        // MDC giúp mọi log cùng thread mang mã tương quan.
        try (MDC.MDCCloseable ignored = MDC.putCloseable("correlationId", id)) {
            chain.doFilter(request, response);
        }
    }

    public static String id(HttpServletRequest request) {
        return (String) request.getAttribute(ATTRIBUTE);
    }
}
```

Giải thích:

- Filter chạy trước phần xử lý bảo mật để cả 401/403 từ Spring Security cũng có `X-Correlation-ID`. Với Spring Boot, `@Order` đặt thứ tự của Servlet filter được tự động đăng ký.
- Mã được sinh tại ranh giới ứng dụng, không tin chuỗi `X-Correlation-ID` tùy ý mà client cung cấp. Trong kiến trúc có API gateway tin cậy, có thể xây dựng quy tắc tiếp nhận/propagate ID khác, với kiểm tra độ dài, ký tự, nguồn và quy ước toàn hệ thống.
- `request.setAttribute(...)` cho phép entry point, handler và controller sử dụng cùng ID; response header giúp client truy vấn/ghi nhận mã.
- `MDC.putCloseable(...)` dọn giá trị sau request, tránh log của request khác bị gắn nhầm ID khi thread được tái sử dụng. Trong xử lý bất đồng bộ hoặc qua service khác cần truyền ngữ cảnh theo cơ chế thích hợp; MDC dạng ThreadLocal không tự lan truyền qua mọi thread.

Nếu frontend chạy khác origin và cần đọc header này bằng JavaScript, CORS phải cho phép đọc `X-Correlation-ID` qua `Access-Control-Expose-Headers` cho những origin đã được cho phép. Điều đó không tự mở CORS hay quyền truy cập API.

### 5.3. Một bộ viết lỗi dùng chung

Tệp `src/main/java/demo/safeerror/ApiErrorWriter.java`:

```java
package demo.safeerror;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

@Component
public class ApiErrorWriter {
    private final ObjectMapper mapper;

    public ApiErrorWriter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public void write(
            HttpServletRequest request,
            HttpServletResponse response,
            int status,
            String code,
            String publicMessage
    ) throws IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader("Cache-Control", "no-store");

        String id = CorrelationIdFilter.id(request);
        mapper.writeValue(
                response.getWriter(),
                new PublicError(code, publicMessage, id)
        );
    }

    public record PublicError(
            String code,
            String message,
            String correlationId
    ) {}
}
```

Không truyền nguyên văn `exception.getMessage()` vào tham số `publicMessage`. Bộ viết chỉ nhận thông điệp đã được lựa chọn theo chính sách. `ObjectMapper` do Spring Boot cấu hình giúp JSON được escape đúng cách; không tự nối chuỗi JSON từ thông tin nhập vào.

Lưu ý: ví dụ giả định response chưa được commit. Nếu exception xuất hiện **sau khi** máy chủ đã gửi header hoặc một phần body, không thể bảo đảm thay status/body thành JSON mới; cần ghi log, quan sát và xử lý tại ranh giới streaming/async tương ứng.

### 5.4. Tạo 401 và 403 nhất quán tại Spring Security

Tệp `src/main/java/demo/safeerror/SecurityConfig.java`:

```java
package demo.safeerror;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ApiErrorWriter errors
    ) throws Exception {
        AuthenticationEntryPoint unauthorized = (request, response, ex) -> {
            // Với HTTP Basic, giữ challenge cần thiết cho client.
            response.setHeader(
                    HttpHeaders.WWW_AUTHENTICATE,
                    "Basic realm=\"demo-api\""
            );
            errors.write(
                    request, response, 401,
                    "AUTHENTICATION_REQUIRED",
                    "Bạn cần đăng nhập để tiếp tục."
            );
        };

        AccessDeniedHandler forbidden = (request, response, ex) ->
                errors.write(
                        request, response, 403,
                        "ACCESS_DENIED",
                        "Bạn không có quyền truy cập tài nguyên này."
                );

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/fail").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(basic -> basic.authenticationEntryPoint(unauthorized))
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(unauthorized)
                .accessDeniedHandler(forbidden)
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo-reader")
                .password(encoder.encode("demo-only-password"))
                .roles("READER")
                .build()
        );
    }
}
```

Đây là cấu hình phục vụ **API JSON**. Phần role `READER` không có quyền `ADMIN`, nên `GET /api/admin` sẽ trả 403 khi đã xác thực. Chưa xác thực trả 401. Đường dẫn `/api/fail` chỉ mở công khai trong ví dụ để tái hiện lỗi 500 mà không cần xác thực.

Cấu hình trên **không tắt CSRF**. Ví dụ chỉ dùng `GET` để tập trung vào hợp đồng lỗi. Nếu bổ sung `POST` bằng cookie hoặc HTTP Basic trong trình duyệt, vẫn phải xem xét bảo vệ CSRF; phản hồi từ `CsrfFilter` có thể đi qua đường xử lý riêng, nên cần kiểm thử và tích hợp định dạng lỗi tương ứng. Không suy ra rằng mọi lỗi của filter sẽ tự chạy qua `exceptionHandling(...).accessDeniedHandler(...)`.

Khi thay HTTP Basic bằng Bearer/JWT, phải dùng entry point và access-denied handler tương thích OAuth2 Resource Server; bảo đảm `WWW-Authenticate: Bearer ...` đúng quy tắc. Không giữ challenge `Basic` như trong demo.

### 5.5. Controller và phản hồi 500 có kiểm soát

Tệp `src/main/java/demo/safeerror/DemoController.java`:

```java
package demo.safeerror;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {
    @GetMapping("/private")
    public String privateResource() {
        return "private";
    }

    @GetMapping("/admin")
    public String adminResource() {
        return "admin";
    }

    @GetMapping("/fail")
    public String failure() {
        // Chỉ dùng để minh họa lỗi kỹ thuật không được trả cho client.
        throw new IllegalStateException("internal-only: db-node=cluster-a");
    }
}
```

Tệp `src/main/java/demo/safeerror/ApiExceptionAdvice.java`:

```java
package demo.safeerror;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.io.IOException;

@RestControllerAdvice
public class ApiExceptionAdvice {
    private static final Logger log =
            LoggerFactory.getLogger(ApiExceptionAdvice.class);

    private final ApiErrorWriter errors;

    public ApiExceptionAdvice(ApiErrorWriter errors) {
        this.errors = errors;
    }

    @ExceptionHandler(IllegalStateException.class)
    public void handleUnexpected(
            IllegalStateException ex,
            HttpServletRequest request,
            HttpServletResponse response
    ) throws IOException {
        String id = CorrelationIdFilter.id(request);
        log.error("Unexpected application error; correlationId={}", id, ex);

        errors.write(
                request, response, 500,
                "INTERNAL_ERROR",
                "Không thể xử lý yêu cầu lúc này."
        );
    }
}
```

Đoạn `@ExceptionHandler(IllegalStateException.class)` chỉ xử lý **một loại exception được tạo để kiểm thử**. Nó không tuyên bố đã chuẩn hóa toàn bộ lỗi MVC. Với ứng dụng thật, cần chính sách cho validation 400, resource 404, unsupported method 405, lỗi chuyển đổi dữ liệu và lỗi không dự kiến; có thể sử dụng `ResponseEntityExceptionHandler` / `ProblemDetail` và bộ chuyển đổi lỗi chung.

**Không bắt bừa mọi `Exception` rồi trả 500**: cách đó dễ nuốt `AuthenticationException`/`AccessDeniedException` phát sinh ở phần MVC hoặc biến lỗi 400/404 hợp lệ thành 500. Chỉ bắt theo phạm vi có chủ đích; nếu dùng handler toàn cục, phải phân loại và chuyển tiếp exception bảo mật đúng đường xử lý của Spring Security.

Trong ví dụ, stack trace được chuyển vào log nội bộ, còn response gửi ra chỉ chứa mã lỗi trung tính. Log phải có phân quyền và thời hạn lưu phù hợp; trước khi ghi exception hoặc request, tránh log thông tin đăng nhập, `Authorization`, `Cookie`, token, secret, dữ liệu thanh toán hay thông tin riêng tư. Một exception có thể chứa dữ liệu nhạy cảm ngay trong message, nên việc ghi toàn bộ exception cũng cần được đánh giá theo chính sách log của hệ thống.

## 6. Kiểm thử tự động: 401, 403, 500 và mã tương quan

Tệp `src/test/java/demo/safeerror/ApiSecurityErrorTests.java`:

```java
package demo.safeerror;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.io.IOException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiSecurityErrorTests {
    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void missingAuthenticationReturnsSafe401() throws Exception {
        MvcResult result = mvc.perform(get("/api/private"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate", "Basic realm=\"demo-api\""
            ))
            .andExpect(jsonPath("$.code").value("AUTHENTICATION_REQUIRED"))
            .andExpect(jsonPath("$.message")
                .value("Bạn cần đăng nhập để tiếp tục."))
            .andReturn();

        assertCorrelationMatches(result);
    }

    @Test
    void wrongPasswordDoesNotRevealWhyAuthenticationFailed()
            throws Exception {
        MvcResult result = mvc.perform(
                get("/api/private").with(httpBasic("demo-reader", "wrong"))
            )
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value("AUTHENTICATION_REQUIRED"))
            .andExpect(jsonPath("$.message")
                .value("Bạn cần đăng nhập để tiếp tục."))
            .andReturn();

        assertCorrelationMatches(result);
        assertFalse(result.getResponse().getContentAsString()
                .contains("BadCredentialsException"));
    }

    @Test
    void authenticatedUserWithoutAdminRoleGets403() throws Exception {
        MvcResult result = mvc.perform(
                get("/api/admin").with(user("demo-reader").roles("READER"))
            )
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"))
            .andExpect(jsonPath("$.message")
                .value("Bạn không có quyền truy cập tài nguyên này."))
            .andReturn();

        assertCorrelationMatches(result);
    }

    @Test
    void internalExceptionIsMaskedFromClient() throws Exception {
        MvcResult result = mvc.perform(
                get("/api/fail")
                    .header(CorrelationIdFilter.HEADER, "user-supplied-id")
            )
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
            .andExpect(jsonPath("$.message")
                .value("Không thể xử lý yêu cầu lúc này."))
            .andExpect(header().string("Cache-Control", "no-store"))
            .andReturn();

        assertCorrelationMatches(result);
        String body = result.getResponse().getContentAsString();
        assertFalse(body.contains("internal-only"));
        assertFalse(body.contains("cluster-a"));
        assertFalse(body.contains("IllegalStateException"));
        assertNotEquals(
                "user-supplied-id",
                result.getResponse().getHeader(CorrelationIdFilter.HEADER)
        );
    }

    @Test
    void validCredentialsStillAccessNormalResource() throws Exception {
        mvc.perform(
                get("/api/private")
                    .with(httpBasic("demo-reader", "demo-only-password"))
            )
            .andExpect(status().isOk())
            .andExpect(content().string("private"))
            .andExpect(header().exists(CorrelationIdFilter.HEADER));
    }

    private void assertCorrelationMatches(MvcResult result)
            throws IOException {
        String id = result.getResponse()
                .getHeader(CorrelationIdFilter.HEADER);
        assertNotNull(id);
        assertTrue(id.matches("[0-9a-f-]{36}"));

        String inBody = mapper.readTree(
                result.getResponse().getContentAsString()
        ).path("correlationId").asText();

        assertEquals(id, inBody);
    }
}
```

Chạy tại gốc dự án Boot có Gradle wrapper:

```bash
./gradlew test --tests demo.safeerror.ApiSecurityErrorTests
```

Nếu các lớp được đặt đúng package/đường dẫn và dependency đúng, năm phép thử kiểm tra những hành vi sau:

1. **401 thiếu xác thực:** có status 401, mã lỗi trung tính, challenge HTTP Basic và correlation ID nhất quán giữa header/body.
2. **401 sai mật khẩu:** cùng thông điệp công khai như trường hợp chưa có credentials; không lộ tên exception.
3. **403 thiếu quyền:** với user đã xác thực, thiếu role `ADMIN` thì nhận 403 (không bị nhầm thành 401).
4. **500 lỗi nội bộ:** không thấy tên exception hoặc chi tiết nội bộ trong body; mã do server sinh, không nhận nguyên header ID từ client.
5. **Luồng thành công:** tài khoản hợp lệ vẫn có thể truy cập; thay đổi cách thông báo lỗi không làm hỏng nhánh được cho phép.

Những bài kiểm thử này kiểm tra đúng phiên bản API JSON của ví dụ; **không tự chứng minh mọi đường lỗi của hệ thống thật đã thống nhất**. Khi ứng dụng dùng CSRF, form login, Bearer token, OAuth2, exception trong filter riêng, streaming, async hay error dispatch, phải thêm ca kiểm thử tương ứng.

Đối với ứng dụng web, còn cần thử qua trình duyệt thật: màn hình hiện thông báo gì, có vô tình hiển thị response kỹ thuật trong console/UI không, đường chuyển hướng đăng nhập có hợp lý không, và người dùng có nhìn thấy đúng correlation ID cần cung cấp khi báo lỗi không.

## 7. Phân tích mã tương quan và log đúng cách

Giả sử có ba request gần nhau. Mỗi request nhận ID riêng:

```text
Request A -> X-Correlation-ID: 1b22... -> 401
Request B -> X-Correlation-ID: 94ac... -> 403
Request C -> X-Correlation-ID: 6f41... -> 500
```

Trong log của request C, có thể cấu hình pattern để hiện giá trị MDC `correlationId`. Ví dụ đoạn cấu hình Spring Boot trong `application.yml`:

```yaml
logging:
  pattern:
    level: "%5p [cid:%X{correlationId:-}]"
```

Khi request thất bại, nhân viên hỗ trợ chỉ cần tra `correlationId`, thời điểm và môi trường triển khai. ID phải được đánh chỉ mục hoặc có thể tìm trong hệ thống log. Nếu request qua nhiều service, một ID ở gateway chỉ có ích khi quy tắc propagate được triển khai nhất quán; trong hệ thống dùng OpenTelemetry nên sử dụng **trace ID**/W3C Trace Context làm nền tảng truy vết, và xác định rõ quan hệ giữa `correlationId` công khai với `traceId` nội bộ.

**Giới hạn cần nhớ:**

- ID không phải bằng chứng danh tính hoặc quyền sở hữu request. Không cung cấp log cho bất kỳ ai chỉ vì họ có ID.
- Không nhúng email, số điện thoại, access token, địa chỉ IP hay ID tài khoản trực tiếp vào correlation ID. Mã ngẫu nhiên thường an toàn hơn.
- Không nhận nguyên vẹn ID từ Internet nếu chưa có quy tắc tin cậy; cần tránh giả mạo, độ dài bất thường, ký tự xuống dòng (log injection) và trùng mã giữa các request.
- Khi thread thay đổi, `MDC` kiểu ThreadLocal không tự truyền sang `@Async`, `CompletableFuture` hay message consumer; phải dùng cơ chế truyền ngữ cảnh thích hợp.
- Một request có thể thất bại trước khi chạm tới filter của ứng dụng (ví dụ proxy/ingress từ chối ngay). Khi đó gateway phải có chiến lược ID và log riêng; mã do Servlet filter sinh không thể bao phủ điểm chặn nằm bên ngoài nó.
- Log nội bộ vẫn có thể rò rỉ dữ liệu nếu quyền truy cập, retention, redaction hoặc hệ thống thu thập không an toàn. “Ẩn khỏi response” chỉ là một lớp bảo vệ.

## 8. Quy tắc chống rò rỉ chi tiết bảo mật

**Nội dung thường không nên trả trong response công khai:**

| Loại thông tin | Ví dụ không nên xuất hiện | Cách thay thế |
| --- | --- | --- |
| Stack trace / loại exception | `SQLException`, `ClassNotFoundException`, đường dẫn và số dòng Java | `INTERNAL_ERROR` + thông báo trung tính |
| Hạ tầng | Hostname DB, địa chỉ mạng nội bộ, bucket, bảng SQL, câu truy vấn | Correlation ID để tìm log nội bộ |
| Thông tin đăng nhập | Tên tài khoản có tồn tại, lý do chính xác khi sai password | Thông báo xác thực trung tính |
| Quy tắc phân quyền | Tên vai trò nội bộ, tên permission bí mật, chi tiết ACL | `ACCESS_DENIED` mà không liệt kê chính sách |
| Token/secret | `Authorization`, `Cookie`, API key, JWT đầy đủ, session ID | Không xuất ra response và phải lọc khỏi log |
| Dữ liệu người dùng | Email, hồ sơ, tài khoản, bản ghi của người khác | Chỉ trả thông tin đã được cho phép và tối thiểu |
| Debug/stack trong HTML | Trang Whitelabel/error HTML chứa nhiều thông tin kỹ thuật | Error page có kiểm soát hoặc JSON API đã chuẩn hóa |

Không phải mọi chi tiết đều phải bị ẩn: một lỗi 400 có thể cho biết `quantity` cần lớn hơn 0, vì đây là thông tin hành động được. Câu hỏi chính là liệu người gọi **đã được phép biết chi tiết đó chưa**, và việc trả về có tạo điều kiện dò dữ liệu hay chính sách bảo mật không.

Một số cơ chế thường bị bỏ sót:

- **404/403 và khả năng suy đoán tồn tại tài nguyên:** với đường dẫn `/users/{id}/...`, một 403 có thể cho người lạ biết tài khoản hoặc tài liệu tồn tại. Có thể sử dụng 404 theo chính sách bảo mật, nhưng phải nhất quán để không tạo kênh suy đoán qua status, nội dung, kích thước hay thời gian phản hồi.
- **Đăng nhập và khôi phục tài khoản:** nên tránh mã lỗi phân biệt email tồn tại/không tồn tại đối với người chưa được xác minh; kết hợp rate limit và giám sát.
- **Response debug của framework:** không bật hiển thị exception message/stack trace trong lỗi công khai của môi trường production. Kiểm tra trang `/error`, endpoint Actuator, cấu hình exception serialization và thông báo lỗi mặc định.
- **Chuyển hướng chứa dữ liệu nhạy cảm:** đừng đặt access token, session ID hay lỗi kỹ thuật đầy đủ trong query string của trang lỗi; URL có thể vào history, Referer và log.
- **Log ghi toàn bộ request:** tránh middleware log mặc định tất cả header/body, nhất là Authorization, cookie, password và dữ liệu cá nhân. Redact tại nguồn tốt hơn chỉ lọc ở dashboard.
- **Độ dài và cấu trúc phản hồi:** đảm bảo người dùng luôn nhận mã lỗi phù hợp, không lộ stack trace, header chuẩn và mã tương quan; thông điệp chính xác nội bộ nằm trong hệ thống truy vết an toàn.

## 9. Checklist kiểm thử cho một API thực tế

| Bài kiểm thử | Tiêu chí chấp nhận |
| --- | --- |
| Chưa đăng nhập gọi tài nguyên được bảo vệ | Đúng chính sách 401 hoặc redirect; với API JSON có `code` công khai; challenge hợp lệ nếu dùng Basic/Bearer. |
| Đã đăng nhập nhưng thiếu quyền | 403 hoặc 404 theo chính sách, không lộ tên role/permission nội bộ. |
| Thông tin đăng nhập sai / người dùng không tồn tại | Không tạo thông điệp hoặc mã lỗi giúp dò tài khoản; rate limit phù hợp. |
| Lỗi nghiệp vụ / validation | Status đúng; chỉ công khai trường và quy tắc không nhạy cảm; không echo dữ liệu bí mật. |
| Lỗi từ controller | Response 500 sạch; chi tiết kỹ thuật nằm trong log có bảo vệ. |
| Lỗi từ Spring Security filter | Cấu trúc/thông điệp phù hợp; không giả định sẽ đi qua `@RestControllerAdvice`. |
| Lỗi CSRF và xác thực OAuth2 | Xác minh status, challenge và định dạng theo từng filter/cơ chế; không làm sai chuẩn giao thức. |
| Mã tương quan | Header/body cùng ID; ID hợp lệ, ngẫu nhiên và không chứa PII; log tìm được ID tương ứng. |
| Header ID do client tự gửi | Không cho phép người lạ chiếm quyền gắn ID của request khác hoặc chèn ký tự vào log. |
| Request thành công | Response bình thường không bị thay đổi logic; vẫn có correlation ID khi hệ thống yêu cầu. |
| Streaming, async, xử lý lỗi ngoài MVC | Mã truy vết và chính sách lỗi được kiểm thử đúng ở ranh giới thực tế. |
| Production | Không có debug stack/error page nội bộ; log, metrics và alert không chứa secret. |

Để đánh giá một thay đổi, hãy thực hiện cả **kiểm thử dương tính** (người được phép vẫn hoạt động) và **kiểm thử âm tính** (người không được phép không nhận thêm chi tiết nào). Có thể kết hợp MockMvc, kiểm thử tích hợp với proxy thật, kiểm tra response trong DevTools và tìm kiếm log theo correlation ID.

## 10. Lỗi triển khai thường gặp

1. **Trả `ex.getMessage()` cho client.** Message có thể chứa mật khẩu, tên bảng, dữ liệu truy vấn hoặc đường dẫn nội bộ. Chọn thông điệp công khai bằng mã lỗi đã định nghĩa.
2. **Dùng HTTP 200 cho mọi lỗi.** Client và hệ thống giám sát mất khả năng phân loại lỗi đúng.
3. **Dùng chung status 403 cho mọi lỗi bảo mật.** Mất phân biệt 401/403; client không biết có cần xác thực hay không.
4. **Chỉ dùng `@ControllerAdvice`.** Lỗi ở Spring Security filter có thể không được chuẩn hóa.
5. **Chỉ dùng `exceptionHandling(...)`.** Lỗi MVC/validation có thể có định dạng khác.
6. **Thay response nhưng xóa header `WWW-Authenticate`.** Làm hỏng hợp đồng của HTTP Basic/Bearer.
7. **Dùng correlation ID do client tùy ý gửi và ghi thẳng vào log.** Có thể gây giả mạo, trùng mã hoặc log injection.
8. **Không xóa MDC khi thread kết thúc request.** Log của request khác có thể mang nhầm mã cũ.
9. **Có correlation ID nhưng không thể tra log bằng ID đó.** Mã chỉ còn là chuỗi trang trí; cần cấu hình log/search và kế hoạch truyền ngữ cảnh.
10. **Ẩn chi tiết khỏi response rồi ghi toàn bộ secret vào log.** Bảo vệ dữ liệu phải áp dụng cả log, monitoring và trace.
11. **Bắt toàn bộ exception rồi chuyển thành 500.** Có thể vô hiệu hóa quy tắc xử lý 400/404 và bảo mật ở phía MVC.
12. **Tưởng MockMvc đã bao phủ proxy, browser, async và tất cả filter.** Cần kiểm thử tại những ranh giới thực tế tương ứng.

Một thiết kế đạt yêu cầu khi người dùng nhận **thông điệp ngắn và đúng hành động**, client có **status/mã lỗi ổn định**, đội vận hành tìm được **request liên quan**, và kẻ tấn công **không thu thêm thông tin nội bộ** từ cùng một lỗi.

## Tài liệu tham khảo

- Spring Security — [Servlet Architecture / Security Filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html).
- Spring Security — [Authentication Architecture và AuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html).
- Spring Security — [Authorize HTTP Requests và AccessDeniedException](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- Spring Security — [Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/).
- Spring Framework — [Error Responses, ProblemDetail và RFC 9457](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html).
- IETF — [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457).