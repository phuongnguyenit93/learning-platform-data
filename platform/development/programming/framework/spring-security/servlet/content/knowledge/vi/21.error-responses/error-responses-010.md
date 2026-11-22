# Phản hồi lỗi nhất quán, không lộ credentials, token hoặc dữ liệu nội bộ

> **Phạm vi:** Spring Security trên **Servlet stack** (Spring Boot 3.x, Spring Security 6.x, Java 17+). Bài học tập trung vào phản hồi lỗi HTTP khi xác thực hoặc phân quyền thất bại, cách chuẩn hóa hợp đồng JSON và cách bảo vệ thông tin nhạy cảm.

## 1. Mục tiêu và nguyên tắc

Một API an toàn cần trả lời được ba câu hỏi: **yêu cầu thất bại theo loại nào, phía gọi nên xử lý thế nào và người vận hành tra cứu sự kiện bằng cách nào**. Phản hồi công khai không cần chứa nguyên nhân kỹ thuật chi tiết, dữ liệu đăng nhập hoặc nội dung token.

Các quy tắc thực hành:

1. **Giữ đúng HTTP status.** `401 Unauthorized` cho yêu cầu chưa được xác thực hoặc xác thực không hợp lệ; `403 Forbidden` cho người dùng đã xác thực nhưng không đủ quyền. Không trả `200` kèm cờ `success: false` cho lỗi bảo mật.
2. **Giữ hợp đồng phản hồi ổn định.** Ví dụ mọi lỗi truy cập API dùng ba trường `code` (mã máy đọc được), `message` (thông điệp an toàn), `requestId` (mã tra cứu). Giá trị `message` có thể bản địa hóa nhưng `code` cần ổn định.
3. **Dùng thông điệp tổng quát.** Không đưa `exception.getMessage()`, stack trace, user id nội bộ, query SQL, mật khẩu, API key, access/refresh token, cookie phiên hay toàn bộ header `Authorization` vào response.
4. **Tách tín hiệu công khai và chẩn đoán nội bộ.** Response chỉ cung cấp thông tin cần thiết; hệ thống log/trace ghi mã sự kiện, trạng thái, `requestId` và các thuộc tính đã lọc nhạy cảm. Chi tiết lỗi nội bộ, nếu cần, chỉ nằm trong kênh quan sát có kiểm soát truy cập.
5. **Không nới lỏng bảo mật để chuẩn hóa JSON.** Giữ chính sách phân quyền, CSRF, CORS, cache và các chuẩn xác thực mà ứng dụng đang dùng.

Ví dụ hợp đồng JSON cho request chưa đăng nhập:

```json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "Cần xác thực để truy cập tài nguyên này.",
  "requestId": "d13d7fb3-32be-4ee8-b9c4-5b4808ebbd7a"
}
```

`requestId` là giá trị minh họa; mỗi phản hồi trong ví dụ bên dưới sinh UUID mới. Mã này **không** thay thế ID người dùng và không được dùng làm bằng chứng xác thực.

## 2. Phân biệt lỗi đúng để tránh lộ thông tin

| Tình huống | HTTP | `code` công khai | Thông điệp an toàn |
|---|---:|---|---|
| Chưa gửi thông tin xác thực tới API cần đăng nhập | 401 | `AUTHENTICATION_REQUIRED` | Cần xác thực để truy cập tài nguyên này. |
| Sai mật khẩu hoặc thông tin xác thực không hợp lệ | 401 | `AUTHENTICATION_REQUIRED` | Cần xác thực để truy cập tài nguyên này. |
| Đã đăng nhập nhưng thiếu quyền với thao tác | 403 | `ACCESS_DENIED` | Bạn không có quyền thực hiện thao tác này. |
| Yêu cầu bị từ chối do kiểm tra CSRF | 403 | `ACCESS_DENIED` | Bạn không có quyền thực hiện thao tác này. |
| Dữ liệu đầu vào sai cú pháp/vi phạm ràng buộc | 400 | `BAD_REQUEST` | Yêu cầu không hợp lệ. |
| Lỗi ứng dụng không dự kiến | 500 | `INTERNAL_ERROR` | Không thể xử lý yêu cầu lúc này. |

Phần mã ví dụ ở mục 4 thực hiện trực tiếp **hai loại lỗi bảo mật 401/403**. Các mã 400/500 cần cơ chế xử lý lỗi MVC tương ứng, không tự xuất hiện từ hai handler đó. Trạng thái 404 thay vì 403 để che giấu sự tồn tại tài nguyên chỉ phù hợp nếu chính sách nghiệp vụ được thiết kế nhất quán; tuyệt đối không dùng thông báo “Bạn không sở hữu tài khoản X” để vô tình xác nhận tài khoản X tồn tại.

Riêng API đăng nhập, nên dùng thông điệp thất bại **giống nhau** dù tài khoản không tồn tại, mật khẩu sai hoặc trạng thái tài khoản không thể công khai. Không trả “Email đã đăng ký nhưng sai mật khẩu”, “User bị khóa”, “Token của tài khoản 123 đã hết hạn” nếu chúng làm lộ thông tin cho người không được phép biết. Việc giới hạn tốc độ yêu cầu, chống dò mật khẩu và kiểm soát logging vẫn cần thiết; thông điệp tổng quát không tự giải quyết được các tấn công này.

## 3. Cơ chế xử lý trong Spring Security Servlet

Luồng khái quát:

```text
HTTP request
  -> Servlet Filter Chain
  -> Spring Security FilterChainProxy
     -> các filter xác thực / AuthorizationFilter
     -> ExceptionTranslationFilter (đổi một số security exception thành HTTP response)
        -> AuthenticationEntryPoint (đường 401, cần xác thực)
        -> AccessDeniedHandler (đường 403, đã xác thực nhưng bị từ chối)
  -> HTTP response
```

`ExceptionTranslationFilter` nhận các `AuthenticationException` hoặc `AccessDeniedException` từ phần chain phía sau nó. Khi người gọi chưa xác thực đầy đủ, một `AccessDeniedException` cũng có thể dẫn đến `AuthenticationEntryPoint` để bắt đầu xác thực. Khi đã xác thực mà thiếu quyền, `AccessDeniedHandler` xử lý 403.

Một số cơ chế xác thực có nhánh báo lỗi **ngay tại filter xác thực**; ví dụ HTTP Basic cần cấu hình entry point ở cả `httpBasic` và `exceptionHandling` để hợp đồng 401 nhất quán. Form login có `AuthenticationFailureHandler` riêng. `@RestControllerAdvice` của Spring MVC thường **không** bắt được lỗi phát sinh trước khi request vào controller trong security filter chain: chỉ cấu hình global MVC exception handler là chưa đủ.

Với OAuth2 Resource Server/Bearer token, header `WWW-Authenticate` và mã lỗi tiêu chuẩn có ý nghĩa giao thức (RFC 6750). Cần giữ quy ước challenge mà client dựa vào, chẳng hạn dùng các thành phần xử lý Bearer do Spring Security cung cấp, đồng thời giới hạn nội dung mô tả và không bao giờ trả token thực. Ví dụ dùng **HTTP Basic cho môi trường demo** bên dưới không được sao chép nguyên header Basic sang API Bearer.

## 4. Ví dụ hoàn chỉnh trên Spring Boot 3.x / Java 17+

Giả định dự án đã có `spring-boot-starter-web` và `spring-boot-starter-security`; Jackson có sẵn qua Web starter. Ví dụ gồm hai tệp trong package `demo.security`. Chỉ dùng tài khoản giả lập với mật khẩu lấy từ biến môi trường để kiểm thử tại máy cá nhân. Trong ứng dụng thực tế, giữ `UserDetailsService` / nhà cung cấp định danh đang sử dụng và tích hợp hai handler vào cấu hình bảo mật hiện hữu.

**Tệp `src/main/java/demo/security/SecurityErrorConfig.java`:**

```java
package demo.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;

@Configuration
public class SecurityErrorConfig {
    private static final Logger LOG =
            LoggerFactory.getLogger(SecurityErrorConfig.class);

    public record ErrorBody(String code, String message, String requestId) {}

    private static void writeError(HttpServletResponse response,
                                   ObjectMapper mapper,
                                   int status,
                                   String code,
                                   String publicMessage) throws IOException {
        if (response.isCommitted()) {
            LOG.warn("Cannot write security error: response already committed");
            return;
        }

        String requestId = UUID.randomUUID().toString();
        response.setStatus(status);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        response.setHeader("X-Request-Id", requestId);
        mapper.writeValue(response.getOutputStream(),
                new ErrorBody(code, publicMessage, requestId));

        // Log loại lỗi và mã tra cứu, không log exception hay credential.
        LOG.info("security_rejection code={} status={} requestId={}",
                code, status, requestId);
    }

    @Bean
    AuthenticationEntryPoint apiEntryPoint(ObjectMapper mapper) {
        return (request, response, exception) -> {
            // HTTP Basic cần challenge; không chứa mật khẩu hay token.
            response.setHeader(HttpHeaders.WWW_AUTHENTICATE,
                    "Basic realm=\"demo\"");
            writeError(response, mapper, 401,
                    "AUTHENTICATION_REQUIRED",
                    "Cần xác thực để truy cập tài nguyên này.");
        };
    }

    @Bean
    AccessDeniedHandler apiDeniedHandler(ObjectMapper mapper) {
        return (request, response, exception) ->
                writeError(response, mapper, 403,
                        "ACCESS_DENIED",
                        "Bạn không có quyền thực hiện thao tác này.");
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUser(PasswordEncoder encoder) {
        String password = System.getenv("APP_DEMO_PASSWORD");
        if (password == null || password.isBlank()) {
            throw new IllegalStateException(
                    "Set APP_DEMO_PASSWORD before starting the demo");
        }
        return new InMemoryUserDetailsManager(
                User.withUsername("learner")
                        .password(encoder.encode(password))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationEntryPoint apiEntryPoint,
            AccessDeniedHandler apiDeniedHandler) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                    .requestMatchers(HttpMethod.GET, "/api/admin")
                        .hasRole("ADMIN")
                    .anyRequest().authenticated())
            .exceptionHandling(errors -> errors
                    .authenticationEntryPoint(apiEntryPoint)
                    .accessDeniedHandler(apiDeniedHandler))
            .httpBasic(basic ->
                    basic.authenticationEntryPoint(apiEntryPoint))
            .formLogin(AbstractHttpConfigurer::disable);
        return http.build();
    }
}
```

**Tệp `src/main/java/demo/security/DemoApplication.java`:**

```java
package demo.security;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/api/public")
    public Map<String, String> publicResource() {
        return Map.of("data", "public");
    }

    @GetMapping("/api/private")
    public Map<String, String> privateResource() {
        return Map.of("data", "private");
    }

    @GetMapping("/api/admin")
    public Map<String, String> adminResource() {
        return Map.of("data", "admin");
    }
}
```

Chạy từ dự án Spring Boot đã cấu hình Gradle; nhập mật khẩu demo qua terminal, không ghi mật khẩu vào mã nguồn hoặc lệnh `curl`:

```bash
read -rs APP_DEMO_PASSWORD
export APP_DEMO_PASSWORD
./gradlew bootRun
```

Mở terminal thứ hai:

```bash
curl -i http://localhost:8080/api/private
curl -i --user learner http://localhost:8080/api/admin
curl -i --user learner http://localhost:8080/api/private
```

Với `--user learner`, `curl` sẽ yêu cầu nhập mật khẩu. Kết quả dự kiến: lệnh 1 **401** với `AUTHENTICATION_REQUIRED`; lệnh 2 **403** với `ACCESS_DENIED` vì `learner` chỉ có role `USER`; lệnh 3 **200** với JSON `{"data":"private"}`. Hai response lỗi có `Content-Type: application/json`, `Cache-Control: no-store`, cùng `requestId` ở body và header `X-Request-Id`. Với Basic, 401 còn có `WWW-Authenticate: Basic realm="demo"`. UUID và thời gian xử lý mỗi lần chạy có thể khác nhau. Khi chạy ngoài localhost, HTTP Basic **bắt buộc dùng HTTPS**; không dùng tài khoản demo trong production.

**Vì sao cách này tránh lộ thông tin?** Cả hai handler cố ý bỏ qua nội dung của `exception` trong phản hồi; message là hằng đã duyệt, cùng cấu trúc JSON từ một hàm chung. Logging chỉ ghi mã lỗi, status, requestId. `Cache-Control: no-store` giảm nguy cơ cache lại nội dung lỗi liên quan tới truy cập. `BCryptPasswordEncoder` chỉ phục vụ tài khoản demo; ứng dụng thật vẫn cần cơ chế quản lý mật khẩu/định danh chuẩn.

## 5. Áp dụng vào hệ thống thực tế

### Giữ hợp đồng nhất quán nhưng không làm hỏng giao thức

- Đặt `AuthenticationEntryPoint` và `AccessDeniedHandler` ở **đúng `SecurityFilterChain`** bảo vệ route mục tiêu. Nếu có nhiều chain dùng `securityMatcher`, kiểm tra chain nào khớp request, vì cấu hình của chain khác không tự áp dụng.
- Với HTTP Basic, status 401 nên có header `WWW-Authenticate` hợp lệ. Với OAuth2 Bearer, giữ semantics của `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler`; client có thể cần thông tin chuẩn về trạng thái xác thực/scope. Không thay chuỗi challenge bằng một chuỗi Basic hoặc đưa token gốc vào `error_description`.
- Với form login, failure handler mặc định có thể redirect tới trang login; nếu xây dựng API JSON đăng nhập, cần cấu hình `AuthenticationFailureHandler` tương ứng. Với Spring MVC, dùng `@RestControllerAdvice` cho lỗi validation/nghiệp vụ/500 để giữ cùng envelope nhưng không tiết lộ exception; không hy vọng nó thay thế security handlers.
- Không tùy tiện vô hiệu hóa CSRF chỉ để được body JSON. Nếu ứng dụng dùng cookie/session cho các request thay đổi trạng thái, giữ bảo vệ CSRF và kiểm thử lỗi 403 của nhánh này.
- Nếu hệ thống đã có trace id từ request filter/tracing, **tái sử dụng ID do server kiểm soát** thay vì luôn tạo UUID mới trong writer. Header request id do client gửi cần được kiểm tra định dạng, chiều dài và mức độ tin cậy trước khi dùng trong log; tránh log injection.

### Dữ liệu tuyệt đối không công khai

Kiểm tra đồng thời **body, headers và log**. Không phản hồi hoặc log nguyên bản: `Authorization`, `Cookie`, `Set-Cookie`, mật khẩu, `client_secret`, OTP, session id, access token, refresh token, private key, connection string, câu SQL, stack trace, path hệ thống, toàn bộ request body hoặc thông tin người dùng thuộc phạm vi riêng tư. Một dòng như `LOG.error("Authentication failed", exception)` đôi khi cần cho điều tra nội bộ nhưng phải đi qua chính sách lọc nhạy cảm và quyền truy cập log; ví dụ hiện tại tránh ghi exception trực tiếp.

Không nên tự động trả `exception.getMessage()` ngay cả khi exception hiện tại có vẻ vô hại: nội dung từ thư viện, nhà cung cấp danh tính hoặc cấu hình tương lai có thể chứa chi tiết nhạy cảm. Không tạo thông điệp khác biệt quá mức giữa tài khoản hợp lệ/không hợp lệ, token tồn tại/không tồn tại hoặc resource có/không có quyền; những khác biệt này tạo kênh suy đoán thông tin.

## 6. Checklist kiểm thử và các lỗi thường gặp

| Ca kiểm thử | Kết quả cần đạt |
|---|---|
| Anonymous GET route bảo vệ | 401; `code` ổn định; không redirect HTML trong API |
| Sai HTTP Basic password | 401; cùng envelope, không phản ánh username/password |
| User thường truy cập route quản trị | 403; không nêu role nội bộ hoặc quyền thiếu cụ thể |
| User có quyền truy cập route hợp lệ | 200; không bị handler lỗi can thiệp |
| Lỗi CSRF trên endpoint thay đổi dữ liệu | 403; không công khai token CSRF |
| Yêu cầu có token/chữ ký/header chứa dữ liệu giả nhạy cảm | Không xuất hiện chuỗi nhạy cảm trong body, header phản hồi hay log |
| Các lỗi liên tiếp | Mỗi phản hồi có `requestId` hợp lệ; body/header khớp; server có dấu vết tra cứu tương ứng |
| Lỗi nội bộ 500 từ controller | Thông điệp tổng quát; không lộ stack trace/SQL/path máy chủ |
| Request đi qua các `SecurityFilterChain` khác nhau | Mỗi chain có đúng handler và đúng chuẩn xác thực của nó |

Các lỗi triển khai hay gặp:

1. Chỉ thêm `@RestControllerAdvice` rồi thấy 401/403 vẫn trả HTML hoặc redirect: nguyên nhân là lỗi đến từ **filter chain**, cần cấu hình entry point/denied handler.
2. Cấu hình 403 đúng nhưng HTTP Basic sai mật khẩu vẫn trả kiểu khác: cần cài cùng entry point cho `httpBasic`.
3. Lấy `exception.getMessage()` làm `message` hoặc serialize đối tượng `Exception`: có thể lộ thông tin nội bộ.
4. Nuốt mọi lỗi thành 401 hoặc 500: client phân biệt sai thiếu đăng nhập, thiếu quyền, sai đầu vào và lỗi server; metrics cũng sai.
5. Bỏ challenge `WWW-Authenticate` hoặc thay sai scheme: client tiêu chuẩn có thể không thực hiện lại xác thực đúng cách.
6. Ghi request body, token hoặc toàn bộ header khi debug; hoặc tin nguyên vẹn vào request id do client cấp: có thể lộ bí mật và làm ô nhiễm log.
7. Tắt CSRF/CORS hoặc sửa toàn bộ rule truy cập nhằm “fix lỗi trả JSON”: phản hồi đúng không được đánh đổi bằng mất kiểm soát truy cập.

**Tiêu chí hoàn thành:** với cùng một loại lỗi, client nhận status và `code` ổn định, thông điệp an toàn, `requestId` tra cứu được; lỗi 401/403 đi đúng handler trong Servlet Security; toàn bộ đường response/log không phơi lộ credential, token hoặc dữ liệu nội bộ.