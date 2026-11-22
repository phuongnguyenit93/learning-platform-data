# Che thông tin mật và liên kết log bằng mã tương quan trong Spring Security

> **Bối cảnh:** Spring Security 6.x, Spring Boot 3.x, Spring MVC/Servlet, Java 17+. Bài học hướng dẫn ghi log phục vụ quan sát và gỡ lỗi mà **không phát tán mật khẩu, token, session ID, cookie hoặc dữ liệu cá nhân**, đồng thời gắn một mã tương quan (`correlation ID`) cho các log thuộc cùng HTTP request. Ví dụ sử dụng SLF4J, Logback, `MDC`, `OncePerRequestFilter`, HTTP Basic và MockMvc. Mã tương quan là công cụ truy tìm sự kiện, **không phải credential, cơ chế phân quyền hay bảo đảm toàn bộ dữ liệu trong log đã an toàn**.

## 1. Bài toán thực tế: tìm đúng sự kiện mà không lộ secret

Một người dùng gọi API bảo vệ:

```http
GET /api/me HTTP/1.1
Authorization: Basic <credential>
X-Correlation-ID: <gia-tri-tu-client>
```

Ứng dụng có thể trả 401 do xác thực sai, 403 do thiếu quyền, 500 do lỗi server hoặc 200 thành công. Khi điều tra, ta muốn trả lời:

1. Request nào gây lỗi và request ấy xảy ra lúc nào?
2. Endpoint **loại nào** được xử lý? Phương thức HTTP và mã trạng thái là gì?
3. Sự kiện ở filter, controller, service và handler nào cùng thuộc một request?
4. Một lỗi 401 là thất bại authentication hay 403 là thiếu quyền/CSRF?
5. Làm thế nào chia sẻ cho bộ phận hỗ trợ một mã tra cứu mà **không cần chia sẻ password, bearer token, cookie hay stack trace nhạy cảm**?

Cách ghi log nguy hiểm là in nguyên toàn bộ request: headers, query string, form body hoặc DTO. `Authorization` và `Cookie` có thể chứa thông tin giúp chiếm phiên; `password`, `apiKey`, `refreshToken`, `client_secret` và mã xác thực một lần cũng là secret. Ngay cả username, email, số điện thoại, IP hoặc đường dẫn chứa ID người dùng cũng có thể là dữ liệu cá nhân cần giới hạn quyền truy cập.

Thay vì log request tùy ý, định nghĩa **event schema cho phép một tập trường tối thiểu**:

| Trường log | Ví dụ an toàn | Vì sao hữu ích |
| --- | --- | --- |
| `timestamp` | Thời điểm do hệ thống logging ghi | Xác định trình tự và cửa sổ sự cố |
| `level` | `INFO`, `WARN`, `ERROR` | Phân biệt thông tin/ngoại lệ vận hành |
| `event` | `http.completed`, `app.failure` | Tìm sự kiện theo loại, không cần đọc body |
| `correlationId` | UUID mới tạo, ví dụ `9d9e...` | Ghép log của cùng request |
| `method` | `GET`, `POST`, `OTHER` | Phân tích đường xử lý |
| `route` | `public`, `profile`, `admin`, `other` | Phân loại endpoint mà không log raw path |
| `httpStatus` | `200`, `401`, `403`, `500` | Đối chiếu bước lỗi |
| `durationMs` | `12` | Đánh giá độ trễ |
| `errorCode` | `DEMO_FAILURE` hoặc mã đã phê duyệt | Phân loại lỗi mà không in nội dung nhạy cảm |

Dữ liệu cần bảo vệ không nhất thiết chỉ là giá trị giống mật khẩu. Hãy coi những gì đến từ network, URL, exception message, payload, database và dịch vụ khác là **có thể chứa dữ liệu nhạy cảm hoặc nội dung điều khiển log** cho tới khi được phân loại.

**Nguyên tắc gốc:** *Chọn trường an toàn để ghi log* (`allowlist logging`) tốt hơn *ghi mọi thứ rồi cố che vài chuỗi nhạy cảm*. Cơ chế redaction/masking vẫn hữu ích như phòng thủ bổ sung, nhưng không sửa được mọi trường hợp dữ liệu bị ghi từ trước.

## 2. Phân biệt correlation ID, trace ID, span ID và session ID

Các thuật ngữ thường xuất hiện cạnh nhau nhưng không đồng nghĩa:

| Khái niệm | Chức năng | Nguồn tạo trong bài | Có phải bí mật xác thực? |
| --- | --- | --- | --- |
| **Correlation ID / request ID** | Nhãn tra cứu kết nối các event liên quan request | UUID sinh phía server cho mỗi inbound HTTP request | Không. Không dùng làm bằng chứng danh tính |
| **Trace ID** | Kết nối những span của một trace qua các service | Hệ thống distributed tracing, ví dụ Micrometer Tracing/OpenTelemetry | Không dùng làm credential; có thể là dữ liệu vận hành cần hạn chế công khai |
| **Span ID** | Định danh một đơn vị công việc bên trong trace | Hệ thống tracing | Không phải token truy cập |
| **Session ID** | Chỉ tới một phiên đăng nhập/phiên ứng dụng | Servlet/session store | **Nhạy cảm**; không ghi thẳng vào log |
| **Bearer/access/refresh token** | Mang bằng chứng quyền truy cập hoặc gia hạn truy cập | Identity provider / hệ thống xác thực | **Rất nhạy cảm**; không ghi vào log |
| **User ID/email** | Định danh người dùng | Hệ thống dữ liệu | Có thể là PII; log theo chính sách và mục đích được phép |

Có thể dùng một UUID request ID để tìm các event của **một request** trong một service. Để tương quan các bước *giữa nhiều microservice*, cần đưa context qua HTTP client, message queue hoặc tracing instrumentation phù hợp. Chỉ tạo mã trên server A **không làm** log của server B tự có cùng mã.

Trong hệ thống đã dùng **Micrometer Tracing/OpenTelemetry**, thường nên tái sử dụng trace/span context và propagation do thư viện cung cấp thay vì tự tạo một hệ thống distributed tracing thứ hai. Spring Boot có cơ chế correlation trong log khi tracing được bật. Bài này cố tình xây một request ID đơn giản để hiểu MDC và giới hạn an toàn; nó **không thay thế distributed tracing**.

## 3. Threat model: điều gì không nên lọt vào log?

### 3.1. Các loại dữ liệu thường phải loại khỏi log

- `Authorization` header, Basic credential, Bearer token, OAuth2 authorization code, refresh token, JWT nguyên văn.
- Mật khẩu, password reset token, mã OTP, secret questions, khóa API, private key, connection string có secret.
- `Cookie`, `Set-Cookie`, `JSESSIONID` hoặc session identifier nguyên bản.
- Request/response body chứa thông tin thanh toán, dữ liệu sức khỏe, định danh cá nhân hoặc tài liệu nội bộ.
- URL/query string có `?token=...`, `?password=...`, email, số giấy tờ; path parameter có thể cũng là PII.
- Giá trị từ `exception.getMessage()`, DTO `toString()` hoặc exception cause do thư viện sinh ra: có thể bao gồm SQL, đường dẫn file, tên user hoặc secret.
- Toàn bộ cấu hình môi trường, environment variables, private certificate, dữ liệu truy vấn database và stack trace đầy đủ khi chưa kiểm soát nguồn phát sinh.

Không nên mặc định “hash là dữ liệu công khai”. Hash SHA-256 trực tiếp của password, số điện thoại hoặc email có thể bị dò từ từ điển vì không gian giá trị nhỏ hoặc lặp lại. Nếu thực sự cần liên kết danh tính giả danh giữa event, cân nhắc **HMAC với khóa quản lý riêng, mục đích và thời hạn rõ ràng**; pseudonym vẫn có thể là dữ liệu cá nhân. Trong ví dụ này không cần ghi cả username đã hash.

### 3.2. Log injection và giả mạo correlation ID

Giá trị do client cung cấp có thể chứa newline, ký tự điều khiển hoặc nội dung giống một dòng log mới. Ví dụ nếu ứng dụng viết `log.info("cid={}", request.getHeader("X-Correlation-ID"))`, một client có thể gửi header nhiều ký tự lạ để tạo log khó đọc, hoặc chọn mã của người khác để **ghép nhầm** những request độc lập.

Vì vậy, ví dụ **không tin** `X-Correlation-ID` từ client. Nó **luôn tự tạo UUID mới** và chỉ ghi UUID ấy. Nếu kiến trúc cần nhận request ID từ API gateway đáng tin, phải định nghĩa ranh giới trust: gateway xóa header do client tự khai, sinh/chuẩn hóa ID, dùng allowlist độ dài/ký tự và phân biệt rõ **external request ID** với **internal trusted ID**. Validation hình thức một ID không chứng minh nguồn gốc của nó.

Response header `X-Correlation-ID` trong ví dụ chỉ là mã tra cứu để báo lỗi. Nó không mở quyền, không cấp session và không thể dùng làm login token. Đừng lưu các secret trong chính correlation ID.

### 3.3. Log level không phải ranh giới bảo mật

`DEBUG` hoặc `TRACE` có thể hữu ích khi phân tích `FilterChainProxy`, `AuthenticationManager` và `AuthorizationFilter`, nhưng bật chúng không bảo đảm log được redaction. Một số framework/library/custom code có thể ghi thêm dữ liệu. Chỉ bật mức chi tiết trong môi trường được phê duyệt, với retention ngắn và quyền truy cập log phù hợp. Không bật `@EnableWebSecurity(debug = true)` rộng rãi ở production chỉ để “xem request”.

## 4. Thiết kế luồng log an toàn của một request

Ta muốn cấu trúc như sau:

```text
HTTP request
   |
   v
Servlet CorrelationIdFilter (ưu tiên cao)
  - tạo UUID mới phía server
  - ghi request attribute: correlationId
  - đặt response header X-Correlation-ID
  - put MDC["cid"] = UUID
  - log sự kiện http.started với route được phân loại
   |
   v
Spring Security / FilterChainProxy
  - nếu Basic sai hoặc chưa có credential -> 401
  - nếu đăng nhập đúng nhưng thiếu role -> 403
   |
   v
@RestController / Service
  - log sự kiện nghiệp vụ bằng event code, không kèm secret
  - có thể ném exception
   |
   v
@RestControllerAdvice (cho lỗi domain do MVC xử lý)
  - phản hồi lỗi công khai không chứa stack trace
  - có thể kèm correlation ID của request
   |
   v
finally trong CorrelationIdFilter
  - log http.completed status + duration
  - xóa/khôi phục MDC để không nhiễm request kế tiếp
   |
   v
HTTP response + X-Correlation-ID
```

**MDC (`Mapped Diagnostic Context`)** là một tập các cặp key/value gắn với ngữ cảnh logging của thread, được SLF4J/Logback hỗ trợ. Khi `MDC.put("cid", id)`, các lệnh `log.info(...)` sau đó trên **cùng thread** có thể in `cid` qua pattern. `MDC` không tự truyền giữa threads. Request thread thường được tái sử dụng; vì vậy **bắt buộc dọn trong `finally`**.

Không chỉ set MDC mà quên khôi phục: request sau có thể mang mã của request trước, gây nhầm sự cố và rò rỉ mối liên kết giữa người dùng. Bài dùng `String previous = MDC.get("cid")` để khôi phục giá trị cũ nếu có, thay vì mặc định xóa dữ liệu MDC vốn thuộc ngữ cảnh khác.

## 5. Ví dụ chạy được trên Spring Boot 3 và Security 6

### 5.1. Các endpoint và hành vi kỳ vọng

| Endpoint | Ai được truy cập? | Hành vi |
| --- | --- | --- |
| `GET /public` | Mọi người | Trả body `public`, HTTP 200 |
| `GET /api/me` | Người đăng nhập đúng | Trả `hello reader` hoặc `hello admin` |
| `GET /api/admin` | Chỉ `ROLE_ADMIN` | Người khác đã xác thực nhận 403 |
| `GET /api/fail` | Người đã xác thực | Minh họa lỗi có kiểm soát: 500 với JSON mã lỗi + correlation ID |

Hai tài khoản **demo**: `reader / reader-pass` có role USER và `admin / admin-pass` có role ADMIN. Không sử dụng những credentials hard-code này ngoài môi trường học tập.

Các điểm thiết kế quan trọng:

1. Filter correlation được đăng ký như **Servlet Filter** ở thứ tự cao, chạy trước Spring Security servlet filter; nhờ vậy cả response 401/403 phát sinh từ security cũng có mã tra cứu.
2. Không copy `X-Correlation-ID`/`X-Request-ID` từ client; UUID được sinh mới.
3. Log route theo **tập nhãn cố định** (`public`, `me`, `admin`, `fail`, `other`); không log raw path hay query string.
4. Log method sau khi phân loại; không log headers, body, credentials, username hoặc token.
5. Dùng `MDC.put` / khôi phục trong `finally` để gắn ID vào log xuyên các lớp đồng bộ trong cùng thread.
6. Handler trả mã lỗi công khai, không trả `exception.getMessage()`, stack trace hoặc request details.
7. Chỉ dùng GET cho các endpoint demo; không cần tắt CSRF. Với API ghi dữ liệu, vẫn cần thiết kế CSRF theo mô hình authentication và caller.

### 5.2. Dependencies

Tạo dự án Spring Boot 3.x với Java 17+ và Gradle. Trong `build.gradle` đã có Spring Boot plugin/repositories, phần `dependencies` cần:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây là **khối dependencies**, không phải toàn bộ file `build.gradle`. Các starter phổ biến đi kèm SLF4J/Logback theo cấu hình logging mặc định của Spring Boot. Nếu dự án thay bằng Log4j2 hoặc hệ thống logging khác, cú pháp pattern cần theo backend tương ứng.

### 5.3. File Java đầy đủ

Tạo đúng file **`src/main/java/demo/DemoApplication.java`**:

```java
package demo;

import java.io.IOException;
import java.util.Map;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                        .password(encoder.encode("reader-pass"))
                        .roles("USER").build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-pass"))
                        .roles("ADMIN").build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
class CorrelationIdFilter extends OncePerRequestFilter {
    static final String ATTRIBUTE = "demo.correlationId";
    static final String HEADER = "X-Correlation-ID";

    private static final Logger log =
            LoggerFactory.getLogger(CorrelationIdFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String cid = UUID.randomUUID().toString();
        String previous = MDC.get("cid");
        long started = System.nanoTime();

        request.setAttribute(ATTRIBUTE, cid);
        response.setHeader(HEADER, cid);
        MDC.put("cid", cid);

        String route = safeRoute(request.getServletPath());
        String method = safeMethod(request.getMethod());

        try {
            log.info("http.started method={} route={}", method, route);
            filterChain.doFilter(request, response);
        } finally {
            long durationMs =
                    (System.nanoTime() - started) / 1_000_000;

            log.info(
                    "http.completed method={} route={} status={} durationMs={}",
                    method, route, response.getStatus(), durationMs);

            if (previous == null) {
                MDC.remove("cid");
            } else {
                MDC.put("cid", previous);
            }
        }
    }

    private static String safeRoute(String servletPath) {
        return switch (servletPath) {
            case "/public" -> "public";
            case "/api/me" -> "me";
            case "/api/admin" -> "admin";
            case "/api/fail" -> "fail";
            default -> "other";
        };
    }

    private static String safeMethod(String requestMethod) {
        return switch (requestMethod) {
            case "GET" -> "GET";
            case "POST" -> "POST";
            case "PUT" -> "PUT";
            case "PATCH" -> "PATCH";
            case "DELETE" -> "DELETE";
            default -> "OTHER";
        };
    }
}

class DemoFailure extends RuntimeException {
}

record ApiError(String code, String correlationId) {
}

@RestController
class DemoController {
    private static final Logger log =
            LoggerFactory.getLogger(DemoController.class);

    @GetMapping("/public")
    String publicPage() {
        log.info("public.page.viewed");
        return "public";
    }

    @GetMapping("/api/me")
    String me(Authentication authentication) {
        log.info("profile.viewed");
        return "hello " + authentication.getName();
    }

    @GetMapping("/api/admin")
    String adminPage() {
        log.info("admin.page.viewed");
        return "admin";
    }

    @GetMapping("/api/fail")
    String fail() {
        log.warn("operation.failed code=DEMO_FAILURE");
        throw new DemoFailure();
    }
}

@RestControllerAdvice
class ApiFailureHandler {
    private static final Logger log =
            LoggerFactory.getLogger(ApiFailureHandler.class);

    @ExceptionHandler(DemoFailure.class)
    ResponseEntity<ApiError> fail(HttpServletRequest request) {
        log.warn("http.error.translated code=DEMO_FAILURE");

        String cid = (String) request.getAttribute(
                CorrelationIdFilter.ATTRIBUTE);

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ApiError("operation_failed", cid));
    }
}
```

**Vì sao ví dụ chạy được:** chỉ `DemoApplication` là lớp `public`; `SecurityConfig`, `CorrelationIdFilter`, `DemoController`, `ApiFailureHandler` và các kiểu phụ trợ đều là top-level package-private cùng package `demo`. `@SpringBootApplication` component-scan các bean, `@Order(Ordered.HIGHEST_PRECEDENCE)` cho filter ưu tiên trước filter bảo mật mặc định trong ứng dụng Spring Boot thông thường. `record`, switch expression và Java import phù hợp với Java 17+.

**Lưu ý vị trí filter:** `CorrelationIdFilter` trong ví dụ là **Servlet filter được Spring Boot đăng ký**, không phải `SecurityFilterChain` được thêm qua `http.addFilterBefore(...)`. Không tự ý đăng ký **cùng một instance** hai lần ở cả servlet container và Spring Security chain vì có thể gây chạy lặp và khó hiểu thứ tự. Kiểm tra Filter registration/ordering thực tế khi dự án có filter đặc biệt hoặc `spring.security.filter.order` được tùy chỉnh.

### 5.4. Cấu hình format để log thật sự hiện CID

Tạo file **`src/main/resources/application.properties`**:

```properties
spring.application.name=security-log-demo

# Thêm MDC cid vào phần level của log console Logback.
logging.pattern.level=%5p [cid:%X{cid}]

# Không bật toàn bộ DEBUG/TRACE trong ví dụ.
logging.level.root=INFO
```

Ở đây `%X{cid}` đọc giá trị MDC `cid` trong **thread đang ghi log**. Một event từ filter hoặc controller cùng request sẽ có `[cid:...]` tương ứng; log startup hoặc nền không có CID có thể hiện `[cid:]`. Với cấu hình logging khác, hãy chỉnh pattern/appender tương đương. Tạo UUID và đặt MDC **không tự làm log có mã** nếu pattern/JSON encoder chưa xuất giá trị ấy.

**Đừng log nguyên CID lấy từ client:** ví dụ sinh UUID nội bộ và trả về header `X-Correlation-ID`; nếu client gửi bất cứ `X-Correlation-ID` nào, chương trình vẫn tạo mã mới. Điều này tránh log injection và nhầm liên kết request do header bị giả mạo trong demo.

### 5.5. Chạy ứng dụng

Dùng Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Mặc định nếu chưa thay `server.port`, ứng dụng lắng nghe tại `http://localhost:8080`. Dùng terminal khác:

```bash
# Request public: 200 và X-Correlation-ID.
curl -i http://localhost:8080/public

# Không có credentials: thường 401, vẫn có X-Correlation-ID.
curl -i http://localhost:8080/api/me

# Sai credentials: 401; password không được xuất vào app log.
curl -i -u reader:wrong-password http://localhost:8080/api/me

# Đúng credentials: 200, body "hello reader".
curl -i -u reader:reader-pass http://localhost:8080/api/me

# Đã xác thực nhưng thiếu role ADMIN: 403.
curl -i -u reader:reader-pass http://localhost:8080/api/admin

# Đủ role: 200, body "admin".
curl -i -u admin:admin-pass http://localhost:8080/api/admin

# Lỗi có kiểm soát: 500, JSON chứa code + CID.
curl -i -u reader:reader-pass http://localhost:8080/api/fail

# Client cố gửi CID riêng: server vẫn tạo CID mới.
curl -i -H "X-Correlation-ID: client-picked-value" \
  http://localhost:8080/public
```

Nếu `curl` trong PowerShell là alias của `Invoke-WebRequest`, dùng `curl.exe`. Dấu `\` cuối dòng là cú pháp tiếp dòng của Bash; trên PowerShell, đặt lệnh `curl.exe` trên một dòng hoặc dùng ký hiệu tiếp dòng đúng của PowerShell.

Kết quả kỳ vọng:

| Trường hợp | HTTP | CID trả cho client | App log an toàn |
| --- | --- | --- | --- |
| `/public` | 200 | UUID mới | `http.started`, `public.page.viewed`, `http.completed status=200` |
| `/api/me` không credential | 401 | UUID mới | Event filter, trạng thái 401; không log header |
| `/api/me` password sai | 401 | UUID mới | Event filter, trạng thái 401; không log password |
| `/api/me` reader đúng | 200 | UUID mới | `profile.viewed` và status 200 |
| `/api/admin` reader đúng | 403 | UUID mới | Event filter, status 403; không in token |
| `/api/admin` admin đúng | 200 | UUID mới | `admin.page.viewed` |
| `/api/fail` reader đúng | 500 | Cùng CID trong header và JSON | `operation.failed`, `http.error.translated`, `http.completed status=500` |
| Client gửi `X-Correlation-ID` tự chọn | 200 | **UUID do server tạo, không phải giá trị client** | Không in giá trị client gửi |

Một chuỗi log **minh họa hình thức** (UUID, thời điểm và duration thay đổi ở mỗi lần chạy):

```text
INFO [cid:6ccfaef0-e0f0-4935-9900-60ffb66d2e4c] http.started method=GET route=fail
WARN [cid:6ccfaef0-e0f0-4935-9900-60ffb66d2e4c] operation.failed code=DEMO_FAILURE
WARN [cid:6ccfaef0-e0f0-4935-9900-60ffb66d2e4c] http.error.translated code=DEMO_FAILURE
INFO [cid:6ccfaef0-e0f0-4935-9900-60ffb66d2e4c] http.completed method=GET route=fail status=500 durationMs=7
```

Đây là **các message và phần MDC minh họa**, không phải toàn bộ định dạng mặc định Spring Boot; logger, thread, timestamp và thời gian xử lý sẽ khác. Không khẳng định duration cố định hay một UUID cố định.

## 6. Vì sao code tránh lộ credential?

### 6.1. Chọn log field trước khi đưa dữ liệu vào logger

Lệnh an toàn trong filter:

```java
log.info(
        "http.completed method={} route={} status={} durationMs={}",
        method, route, response.getStatus(), durationMs);
```

Bốn trường trên là: method đã chuẩn hóa thành lựa chọn cố định, route label từ `switch` literal, status từ response và duration bằng monotonic clock. Không có `request.getHeader("Authorization")`, `request.getQueryString()`, `request.getParameterMap()`, raw URI, request body hoặc password.

**Phản ví dụ không nên dùng trong sản phẩm:**

```java
// KHÔNG NÊN: làm lộ giá trị bí mật.
log.info("login username={} password={}", username, password);
log.debug("raw Authorization={}", request.getHeader("Authorization"));
log.info("all request params={}", request.getParameterMap());
```

Đây là **mảnh phản ví dụ**, không thuộc chương trình runnable. Ngay cả khi log level là DEBUG, log có thể được bật lại, gửi tới aggregator, lưu lâu hoặc được hỗ trợ viên đọc. Không nên dựa vào “bây giờ DEBUG đang tắt” để biện minh cho việc để secret trong statement.

Cẩn thận với `@Data`/`@ToString` (Lombok), Java record chứa password, log entity và `log.error("{}", exception)`: một `toString()` hoặc exception message có thể đính kèm body/secret mà người viết log không nhận ra.

### 6.2. CID xuất hiện ngay cả khi Spring Security chặn

Vì filter correlation chạy ở mức servlet **trước Spring Security** trong cấu hình demo, nó gắn CID rồi mới cho `FilterChainProxy` xử lý. Nếu `BasicAuthenticationFilter` trả 401 hoặc `AuthorizationFilter` từ chối 403, request vẫn đi qua khối `finally` của filter correlation, nên có log hoàn tất với cùng CID và response header CID.

Đây là lý do ví dụ không đặt CID chỉ trong `@RestControllerAdvice` hay controller: security filter có thể chặn trước khi MVC chạy, khiến controller/advice không có cơ hội gắn mã cho một số lỗi. Với method security/MVC exception, request vẫn nằm dưới filter nên MDC và request attribute có sẵn.

**Giới hạn:** các lỗi bị chặn **trước khi request tới servlet filter** (gateway, load balancer, TLS handshake, upstream WAF) không có mã CID này. Hệ thống upstream cần correlation/tracing riêng.

### 6.3. Dọn MDC đúng cách

Giá trị `MDC` trong bài chỉ phù hợp với thread đang thực thi. Với servlet thread pool, request A và request B có thể dùng lại cùng worker thread vào các thời điểm khác nhau:

```text
Thread "http-nio-8080-exec-3"
  Request A -> MDC cid=A -> logs(A) -> finally restore/remove A
  Request B -> MDC cid=B -> logs(B) -> finally restore/remove B
```

Nếu quên `finally`, log request B có thể vô tình mang CID của A. Nếu ghi đè MDC của một tracing framework hoặc component khác mà không khôi phục, log có thể mất context. Mẫu `previous` và `finally` trong code tránh làm mất giá trị `cid` cũ ở **cùng thread**; khi không có giá trị trước đó, `MDC.remove("cid")` làm sạch key.

Không dùng `ThreadLocal` tự viết để thay MDC nếu hệ thống logging đã hỗ trợ MDC, trừ khi có lý do cụ thể và quản lý vòng đời cẩn thận.

## 7. Kiểm thử correlation và không rò credential

`MockMvc` cho phép gửi request qua cấu hình MVC + servlet filters của ứng dụng test mà không cần server mạng. Các test dưới đây kiểm tra:

- Header `X-Correlation-ID` xuất hiện trong cả response thành công và response bị Spring Security từ chối.
- CID đúng cú pháp UUID; hai request độc lập có ID khác nhau.
- Header `X-Correlation-ID` do client giả không được server dùng lại.
- Log của một request có CID, nhưng **không chứa password test**.
- Handler lỗi trả JSON chứa cùng CID với response header, không lộ chi tiết exception.
- Principal hợp lệ bị từ chối `/api/admin` do thiếu role, không bị nhầm thành lỗi password.

Tạo file `src/test/java/demo/CorrelationLoggingTest.java`:

```java
package demo;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ExtendWith(OutputCaptureExtension.class)
class CorrelationLoggingTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicRequestsReceiveFreshServerGeneratedIds()
            throws Exception {
        MvcResult first = mvc.perform(get("/public")
                        .header("X-Correlation-ID", "client-forged-id"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"))
                .andReturn();

        MvcResult second = mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andReturn();

        String a = first.getResponse().getHeader("X-Correlation-ID");
        String b = second.getResponse().getHeader("X-Correlation-ID");

        assertNotNull(a);
        assertNotNull(b);
        UUID.fromString(a);
        UUID.fromString(b);
        assertNotEquals(a, b);
        assertNotEquals("client-forged-id", a);
    }

    @Test
    void unauthenticatedRequestStillHasId() throws Exception {
        MvcResult result = mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized())
                .andReturn();

        String cid = result.getResponse().getHeader("X-Correlation-ID");
        assertNotNull(cid);
        UUID.fromString(cid);
    }

    @Test
    void successfulUserRequestHasIdAndSafeBody() throws Exception {
        MvcResult result = mvc.perform(get("/api/me")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("hello reader"))
                .andReturn();

        assertNotNull(result.getResponse().getHeader("X-Correlation-ID"));
    }

    @Test
    void forbiddenAdminRequestStillHasId() throws Exception {
        MvcResult result = mvc.perform(get("/api/admin")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isForbidden())
                .andReturn();

        assertNotNull(result.getResponse().getHeader("X-Correlation-ID"));
    }

    @Test
    void appErrorUsesSameIdInBodyAndHeader() throws Exception {
        MvcResult result = mvc.perform(get("/api/fail")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isInternalServerError())
                .andReturn();

        String cid = result.getResponse().getHeader("X-Correlation-ID");
        assertNotNull(cid);
        assertThat(result.getResponse().getContentAsString())
                .contains("\"code\":\"operation_failed\"")
                .contains("\"correlationId\":\"" + cid + "\"")
                .doesNotContain("DemoFailure")
                .doesNotContain("reader-pass");
    }

    @Test
    void logsLinkByIdWithoutEchoingWrongPassword(
            CapturedOutput output) throws Exception {
        String secretFromClient = "DO_NOT_LOG_bad-password_7271";

        MvcResult result = mvc.perform(get("/api/me")
                        .with(httpBasic("reader", secretFromClient)))
                .andExpect(status().isUnauthorized())
                .andReturn();

        String cid = result.getResponse().getHeader("X-Correlation-ID");
        assertNotNull(cid);
        assertThat(output.getOut())
                .contains("cid:" + cid)
                .contains("http.completed")
                .doesNotContain(secretFromClient)
                .doesNotContain("Authorization: Basic");
    }
}
```

**Ghi chú kiểm thử:** mã thử dùng `OutputCaptureExtension` của `spring-boot-starter-test` để thu console log trong JVM. Assertion `cid:...` dựa trên `logging.pattern.level` của file properties bên trên; nếu đổi appender sang JSON hoặc đường log khác, cập nhật test theo event schema thực tế, **không xóa assertion kiểm tra sự hiện diện của CID**.

Test `doesNotContain(secretFromClient)` chỉ kiểm chứng đường log và môi trường test hiện tại; không chứng minh mọi logger, mọi profile hoặc mọi dependency đều không thể ghi credential. Khi ứng dụng lớn, thêm kiểm tra logging policy bằng code review, regression tests cho body/header/exception, rà soát log aggregation, DLP/redaction trong pipeline và kiểm tra quyền truy cập thực tế.

Chạy tests:

```bash
./gradlew test
```

Chỉ chạy class này:

```bash
./gradlew test --tests demo.CorrelationLoggingTest
```

Lệnh tương ứng trên Windows:

```powershell
.\gradlew.bat test --tests demo.CorrelationLoggingTest
```

**Kết quả kỳ vọng:** các assertions pass với đúng project, files và cấu hình của ví dụ. Không có UUID, timing hay stdout cố định cần hard-code; các mã sẽ thay đổi qua từng request.

## 8. Gỡ lỗi lỗi xác thực và phân quyền bằng mã tương quan

Giả sử người dùng báo: “API trả 403, mã tương quan `8a7...`”. Quy trình điều tra an toàn:

1. **Xác nhận mã** đến từ header do server phát, không phải chuỗi tùy ý được client gửi. Trong demo, server luôn sinh UUID. Hệ thống thực có thể tạo/đánh dấu mã từ trusted gateway.
2. **Tra log theo CID** trong khoảng thời gian và environment phù hợp. Không yêu cầu người dùng gửi password, token hoặc session cookie để “kiểm tra”.
3. Xem `event=http.completed` hoặc message tương đương để biết method/route category/status/duration; không cần raw URL chứa PII.
4. Nếu HTTP 401, kiểm tra cơ chế authentication (Basic/form/Bearer), nhưng **không log credential**. Có thể dùng một error code chung như `AUTH_FAILURE` và một nguyên nhân nội bộ đã được phân loại, giới hạn người xem.
5. Nếu HTTP 403, kiểm tra authorization, CSRF, request matcher, role/authority và method security; đừng kết luận “thiếu role” chỉ từ status.
6. Nếu 500, tra `app.failure` và mã lỗi, xem metrics/trace có quyền phù hợp; không gửi stack trace nhạy cảm cho client.
7. Nếu request đi qua nhiều service, tra trace ID/span ID hoặc propagation ID đã được bảo đảm đúng trust boundary; đừng mong CID của một service tự tồn tại ở service khác.
8. Khi kết luận, ghi lại mã lỗi và hành động khắc phục, tắt tạm mức TRACE/DEBUG và xóa bản log không cần giữ theo chính sách retention.

### Log sự kiện bảo mật cần có cấu trúc

Một hệ thống thực có thể cần audit events như `authentication.succeeded`, `authentication.failed`, `authorization.denied`, `account.locked` hoặc `token.revoked`. Mỗi sự kiện cần xác định **schema**, severity, lý do nội bộ được phép ghi, correlation ID và cách bảo vệ actor identifier.

Không đưa thông tin nhạy cảm vào event detail để giúp debug nhanh. Ví dụ, mã `BAD_CREDENTIALS` là khác với việc log nguyên password. Cũng không bỏ qua hoàn toàn những sự kiện từ “user nội bộ đáng tin” — insider và tích hợp bên thứ ba vẫn cần audit phù hợp.

Các sự kiện security từ filter có thể được xuất qua event handlers/listeners hoặc observer của Spring Security theo cơ chế được hỗ trợ, thay vì tự bắt mọi `AuthenticationException` và log raw exception. Lưu ý nhiều kiểu lỗi authentication thường được xử lý **trước MVC controller**, nên `@RestControllerAdvice` không bao phủ toàn bộ.

## 9. MDC trong async, task pool và microservices

### 9.1. Vì sao MDC có thể mất khi đổi thread?

`MDC` thường gắn theo thread. Nếu controller tạo `@Async` task, dùng `CompletableFuture`, thread pool hoặc publish message, tác vụ có thể chạy ở thread khác. Request ID bạn đặt trong servlet filter **không mặc nhiên xuất hiện ở thread async**. Thread pool cũng tái sử dụng threads nên nếu tự copy MDC mà không dọn, có thể gắn nhầm CID sang nhiệm vụ khác.

Cách triển khai đúng phụ thuộc executor/framework. Nếu tự dùng Spring `TaskDecorator`, có thể copy và **khôi phục** context trong phạm vi task. Mảnh code sau minh họa nguyên tắc, **không phải cấu hình mặc định được tự lắp vào ứng dụng demo**:

```java
@Bean
TaskDecorator copyMdcForTask() {
    return task -> {
        Map<String, String> captured = MDC.getCopyOfContextMap();
        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    };
}
```

Đoạn này cần import `java.util.Map`, `org.slf4j.MDC`, `org.springframework.core.task.TaskDecorator` và `org.springframework.context.annotation.Bean`, đặt trong một class `@Configuration`. Để nó có tác dụng với một executor cụ thể, bạn phải **cấu hình executor đó thật sự sử dụng TaskDecorator**. Không thêm đoạn này một cách máy móc nếu hệ thống đã có context propagation/tracing instrumentation hoặc nhiều loại executor.

### 9.2. Propagation qua HTTP và message

Đối với microservices, một request có thể gọi A → B → C. Có hai hướng:

- Dùng **Micrometer Tracing/OpenTelemetry** và chuẩn W3C Trace Context với `traceparent`/`tracestate`, để hệ thống instrumentation tạo và truyền trace/span IDs đúng cách.
- Dùng request ID riêng có **quy tắc propagation chặt chẽ**: phân biệt client-provided, gateway-generated và nội bộ; validate kích thước/tập ký tự, ghi nguồn, giới hạn độ tin cậy, tránh cho client tự gắn vào log của request khác.

Không nên dùng correlation ID làm khóa cache/bằng chứng ủy quyền hoặc cho người dùng truy xuất thông tin nội bộ chỉ vì họ biết ID. Khi đưa CID vào error response, endpoint hỗ trợ tra cứu vẫn cần authentication/authorization riêng.

### 9.3. Error dispatch, async dispatch và filter ordering

`OncePerRequestFilter` bảo đảm logic filter chạy một lần **theo mỗi dispatch thuộc phạm vi được cấu hình**; nó không có nghĩa “mọi thread và mọi dispatch của request đều chắc chắn có cùng MDC”. Mặc định `shouldNotFilterAsyncDispatch()` và `shouldNotFilterErrorDispatch()` có thể bỏ qua các dispatch phụ thuộc cấu hình servlet/container.

Ví dụ này chỉ xử lý các **request đồng bộ** với controller return string hoặc MVC handler return `ResponseEntity`; CID được gắn trong REQUEST dispatch, rồi log hoàn tất. Với async controller, streaming response, ERROR dispatch hay gateway-side error, cần kiểm thử lifecycle thực tế, chú ý thời điểm response hoàn tất và cách propagate CID. Nếu cấu hình filter cho nhiều dispatch, không vô tình tạo **một CID mới** cho mỗi bước của cùng logical request; có thể tái sử dụng request attribute đã tồn tại khi đó.

## 10. Redaction/masking trong hệ thống lớn

### 10.1. Ưu tiên thiết kế log an toàn ngay tại nguồn

Định nghĩa một **schema rõ ràng** cho security/app events, dùng key cố định như `event`, `cid`, `status`, `durationMs`, `errorCode`. Không log đối tượng `HttpServletRequest` hoặc toàn bộ DTO. Nếu bắt buộc cần thông tin liên quan user, hãy phân loại PII, quy định ai được xem, mức độ chi tiết, thời gian giữ và cơ chế kiểm tra hợp pháp.

**Structured logging** (JSON) giúp tìm kiếm theo trường và có thể hỗ trợ loại bỏ key nhạy cảm tại logging pipeline. Nhưng structured logging **không tự an toàn**: `log.atInfo().addKeyValue("password", password)` vẫn phát tán bí mật. Quy tắc quan trọng là **không đưa secret vào log event**.

### 10.2. Khi cần mask dữ liệu hiển thị

Một số hệ thống có yêu cầu audit đã được phê duyệt, ví dụ hiển thị bốn ký tự cuối của một mã giao dịch *không phải secret* hoặc ghi một mã lỗi chuẩn. Hãy áp dụng quy tắc mask có hiểu **kiểu dữ liệu**, không chỉ regex mơ hồ trên toàn bộ text. Regex dựa vào từ khóa `password` có thể bỏ sót `pwd`, `clientSecret`, nested JSON, encoding hoặc nội dung do thư viện log.

Đối với token/session/password, lựa chọn mặc định là **không ghi**, thay vì ghi rồi che ba ký tự cuối. Một phần token bị lộ có thể vẫn đủ để gây nguy hiểm hoặc hỗ trợ liên kết hoạt động.

### 10.3. Các lớp kiểm soát bổ sung

1. **Least privilege:** tài khoản xem log không mặc nhiên có quyền xem mọi môi trường/tenant.
2. **Retention:** chỉ giữ log trong thời hạn theo nhu cầu vận hành và chính sách; thiết lập xóa dữ liệu quá hạn.
3. **Mã hóa và truyền tải:** bảo vệ log trên đường truyền và ở nơi lưu.
4. **Access audit:** ghi nhận ai đã truy cập/tải/xuất log quan trọng.
5. **Redaction ở aggregator:** là lớp dự phòng nếu có log từ dependency ngoài kiểm soát, nhưng không thay thế việc chặn secret ở nguồn.
6. **DLP/secret scanning:** quét mẫu log, phát hiện những format mới bị lọt.
7. **Không log mọi response body:** có thể chứa token, dữ liệu khách hàng, nội dung tài liệu hoặc thông tin ngân hàng.
8. **Chuẩn hóa event codes:** giúp truy vấn trong sự cố mà không cần lưu raw exception message.
9. **Rate limit/sampling cho log:** phòng tránh log flooding và chi phí lưu trữ tăng đột biến; không làm mất audit events bắt buộc.
10. **Tách audit log và debug log:** mục tiêu, retention và quyền xem có thể khác; đừng để một bản TRACE tạm thời trở thành nhật ký lưu vĩnh viễn.

## 11. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Log toàn bộ headers/body “để tiện debug” | Lộ `Authorization`, `Cookie`, PII, password | Chỉ log trường được phép; không ghi headers/body nhạy cảm |
| Log `request.getRequestURI()` nguyên văn | Path có thể chứa PII hoặc input điều khiển log | Log route template/nhãn cố định, có phân loại |
| Tin thẳng `X-Request-ID` từ mọi client | Client có thể giả CID, ghép nhầm log, chèn ký tự điều khiển | Sinh mã nội bộ; chỉ tiếp nhận từ gateway đáng tin với kiểm soát |
| Coi CID là credential | Truy cập trái phép nếu API tra cứu chỉ dựa vào CID | CID chỉ để tra cứu; endpoint vẫn phải kiểm tra quyền |
| Đặt MDC nhưng không format logger | Log không hiện CID dù code đã put | Chỉnh pattern hoặc JSON layout để xuất MDC |
| Quên xóa MDC | CID từ request trước xuất hiện ở request sau | `finally` với restore/remove, test lặp nhiều request |
| Chỉ gắn CID trong controller | Lỗi 401/403 từ SecurityFilterChain thiếu mã | Đặt filter quan sát ở tầng phù hợp trước security |
| Gắn cùng filter ở servlet và Spring Security chain | Chạy lặp, khó đoán thứ tự hoặc lifecycle | Chọn một cơ chế đăng ký phù hợp và test |
| Log exception message vô điều kiện | Nội dung user input/SQL/secret có thể lọt | Dùng error code và exception đã phân loại |
| Bật `TRACE` lâu dài cho tất cả package | Nhiều log, rò rỉ và tăng chi phí | Bật scoped tạm thời, giới hạn truy cập/retention |
| Nghĩ MDC tự truyền qua `@Async` | Mất CID hoặc dính CID sai | Propagate bằng executor/tracing context và dọn trong finally |
| Dùng MD5/SHA-256(password) để “ẩn password” | Hash có thể bị dò, vẫn là dữ liệu nhạy cảm | Không log password, cả plaintext lẫn hash |
| Trả raw stack trace trong JSON lỗi | Tiết lộ implementation/data | Trả mã lỗi chung + CID; xem chi tiết ở log đã bảo vệ |
| Chỉ test HTTP 200 có CID | Không biết 401/403/500 có mã hay không | Test đủ nhánh, cả filter-level failure |
| Nghĩ correlation ID tự nối log toàn bộ microservices | Không có propagation context giữa service | Dùng Micrometer Tracing/OpenTelemetry hoặc propagation đáng tin |

## 12. Checklist triển khai và bài tập tự luyện

### Checklist trước khi production

1. Schema log có event code, CID, method/route/status/duration và **không chứa credential/PII thừa**.
2. Servlet filter/middleware được đặt đủ sớm để request bị security từ chối vẫn có mã; tránh đăng ký trùng.
3. CID sinh từ nguồn tin cậy; header client không được tin tùy tiện; ID giới hạn kích thước và ký tự.
4. MDC có vòng đời rõ, được khôi phục/xóa trong `finally` và propagate qua async khi cần.
5. Pattern hoặc structured log encoder thật sự xuất CID; chỉ định tên field/định dạng nhất quán.
6. HTTP response có correlation ID phù hợp để hỗ trợ tra cứu; không bao gồm internal exception/stack trace.
7. Tất cả HTTP status quan trọng (200, 401, 403, 500) có test xác minh CID; credential sai không xuất trong log.
8. Authn/authz event codes phân loại hợp lý; không giả định mọi 403 là role denial.
9. Phân tách/kiểm soát debugging, audit, tracing; hạn chế TRACE trong production.
10. Log storage và pipeline có ACL, retention, encryption, access auditing, secret scanning và kiểm tra tuân thủ.
11. Trong microservice, trace propagation và trust boundary được thiết kế rõ; không dùng CID làm bảo mật.
12. Có hướng dẫn cho support: yêu cầu khách hàng cung cấp **CID và thời gian**, không yêu cầu password, access token, session cookie hoặc screenshot có secret.

### Câu hỏi tự kiểm tra

1. Vì sao `Authorization` header không nên log kể cả khi user được xác thực?
2. `correlationId` có thay thế được token đăng nhập hay `SecurityContext` không?
3. Vì sao giá trị `X-Correlation-ID` do client chọn có thể làm hỏng liên kết log?
4. Trong ví dụ, tại sao request không có credential vẫn nhận `X-Correlation-ID` dù controller không chạy?
5. Nếu log có CID trong controller nhưng không thấy ở file output, cấu hình nào cần kiểm tra?
6. Vì sao mã được đặt trong MDC nhưng biến mất khi gọi `@Async`?
7. Nếu request A và B cùng chạy trên một thread của servlet pool, điều gì xảy ra khi không dọn MDC?
8. Khi người dùng báo 403, tại sao không thể chắc chắn nguyên nhân là `hasRole("ADMIN")`?
9. Tại sao chỉ dùng regex che `password=...` không chứng minh dữ liệu log đã an toàn?
10. Vì sao `doesNotContain(secret)` trong một test chưa chứng minh mọi profile/dependency đều an toàn?
11. Nếu hệ thống bật Micrometer Tracing, bạn nên liên kết CID với `traceId/spanId` theo cách nào?
12. Khi trả HTTP 500, vì sao code lỗi công khai + CID có thể tốt hơn stack trace nguyên văn?
13. Làm thế nào kiểm tra CID không bị spoof khi đi qua gateway?
14. Có nên ghi nguyên `JSESSIONID` để nối log của nhiều request cùng người dùng không?
15. Những bảo vệ nào cần áp dụng cho log aggregator và bộ phận hỗ trợ?

**Đáp án định hướng:** (1) có thể chứa credential; (2) không, chỉ là nhãn tra cứu; (3) client có thể giả mã người khác hoặc log injection; (4) filter servlet chạy trước security; (5) MDC pattern/appender; (6) MDC gắn thread, cần propagation; (7) log request sau bị nhiễm CID cũ; (8) có thể CSRF, method security hoặc custom filter; (9) blacklist không bao quát mọi tên trường/encoding; (10) chỉ chứng minh nhánh đã test; (11) ưu tiên tracing instrumentation, không tự dùng CID để xác thực; (12) giảm lộ implementation, giữ khả năng điều tra; (13) xác lập trust boundary, loại header client giả, kiểm tra propagation; (14) không, session ID nhạy cảm; (15) ACL, retention, encryption và audit.

## Tài liệu tham khảo

- [OWASP — Logging Cheat Sheet: dữ liệu cần loại khỏi log, log injection, monitoring](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Spring Boot 3.5 — Logging và cấu hình MDC trong logging.pattern.level](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html)
- [Spring Boot 3.5 — Micrometer Tracing và correlation IDs](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html)
- [Spring Framework 6.2 — OncePerRequestFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html)
- [Spring Security 6.5 — Servlet Architecture và filter chain](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html)
- [W3C — Trace Context (traceparent/tracestate)](https://www.w3.org/TR/trace-context/)