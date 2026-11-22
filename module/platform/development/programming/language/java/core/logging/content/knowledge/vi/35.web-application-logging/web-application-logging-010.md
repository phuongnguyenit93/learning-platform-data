# Filter endpoint nhạy cảm trong Java Web Logging

## 1. Mục tiêu của việc lọc endpoint nhạy cảm

Trong ứng dụng web Java, **filter endpoint nhạy cảm** là cách nhận diện các tuyến HTTP chứa hoặc xử lý dữ liệu cần bảo vệ, rồi **giới hạn dữ liệu được ghi vào log**. Đây chủ yếu là **privacy-aware logging policy**, không phải cơ chế chặn request hoặc thay thế Spring Security.

Các endpoint điển hình gồm đăng nhập, xác thực đa yếu tố, cấp/refresh token, reset mật khẩu, thanh toán, hồ sơ người dùng, tài liệu riêng tư, webhook có chữ ký và chức năng quản trị khóa bí mật. Mỗi endpoint có thể tạo nhiều nguồn log: access log ở reverse proxy, HTTP server, Servlet filter, application logger, exception handler, tracing và collector.

Một chính sách đúng cần đạt ba mục tiêu cùng lúc:

1. **Không thu bí mật:** password, OTP, bearer token, cookie, session ID, API key, mã reset, PAN/CVV, response body hoặc hồ sơ không cần thiết.
2. **Giữ đủ thông tin vận hành:** method được kiểm soát, route class/template an toàn, status, duration, service, request ID hoặc trace ID hợp lệ.
3. **Giữ sự kiện an ninh bắt buộc:** login failed, authorization denied, token issued, thay đổi quyền hoặc thao tác dữ liệu nhạy cảm vẫn phải có event phù hợp, không bị xóa chỉ vì đã cấm log payload.

Một quy tắc kiểu `logging.level.root=WARN` **không đủ**: lỗi ERROR vẫn có thể chứa body hoặc token; Tomcat/gateway có thể ghi access log hoàn toàn độc lập với SLF4J. “Tắt log nhạy cảm” cũng không có nghĩa tắt mọi bằng chứng của hoạt động xác thực.

## 2. Phân loại endpoint theo rủi ro dữ liệu

| Loại endpoint | Tuyến minh họa | Không nên ghi |
| --- | --- | --- |
| Xác thực | `POST /auth/login`, `POST /auth/mfa/verify` | Password, OTP, request body |
| Token/session | `POST /oauth/token`, `POST /auth/refresh` | Access token, refresh token, session cookie |
| Khôi phục | `POST /password/reset`, `GET /reset/{token}` | Reset code, link có token, email thô |
| Thanh toán | `POST /payments`, `POST /billing/cards` | PAN, CVV, payload thanh toán |
| Dữ liệu cá nhân | `GET /users/{id}`, `PATCH /patients/{id}` | Hồ sơ, định danh trong path, response body |
| Secret/admin | `/admin/keys`, `/internal/secrets` | API key, private key, kết quả nhạy cảm |
| Webhook | `POST /webhooks/payment` | Signature header, payload có PII |
| File upload/download | `POST /documents`, `GET /documents/{id}` | Binary body, tài liệu, tên file nhạy cảm |
| GraphQL hoặc gRPC | `POST /graphql`, RPC xác thực | Variables, operation payload, metadata nhạy cảm |

Không chỉ tìm chuỗi “login” hoặc “token” trong raw path. Các biến thể version, prefix, trailing slash, URL encoding, route aliases hoặc endpoint GraphQL dùng một path chung có thể làm bộ lọc theo chuỗi thất bại.

**Cách tốt:** phân loại theo **API contract và route metadata do server/router xác định**, có nhãn như `AUTH`, `PAYMENT`, `PERSONAL_DATA`, `SECRET`, `PUBLIC_SAFE` và `UNKNOWN`. Khi không biết endpoint thuộc loại nào, **không tự động dump raw path/query/body** để “tiện debug”.

## 3. Lọc dữ liệu và lọc cả sự kiện là hai quyết định khác nhau

| Phương án | Ý nghĩa | Phù hợp khi |
| --- | --- | --- |
| Không ghi body/header/query | Vẫn có access event tối giản | Login, token, payment và hầu hết API xử lý dữ liệu riêng tư |
| Thay raw path bằng route template | `/users/42` thành `/users/{id}` | Cần nhóm latency/error mà không lộ ID |
| Thay route bằng nhãn class | `/auth/login` thành `AUTH_ENDPOINT` | Muốn giảm chi tiết truy cập ở nhóm đặc biệt |
| Allowlist trường an toàn | Chỉ đưa các field được phê duyệt vào event | Structured logging có schema rõ |
| Mask/pseudonymize có kiểm soát | Che một trường thực sự cần lưu | Yêu cầu nghiệp vụ được phê duyệt, có retention |
| Tách stream/index | Security event vào kho có quyền riêng | Audit/security logging và giám sát |
| Bỏ hoàn toàn một access event | Không lưu event ở một nguồn cụ thể | Chỉ khi policy cho phép và đã xem nhu cầu điều tra |

Ví dụ với login thất bại, giữ access event mà không lộ credential:

```json
{"kind":"http_access","route_class":"AUTH_ENDPOINT","method":"POST","status":401,"duration_ms":12,"request_id":"req_01","payload_logged":false}
```

Một event khác **do authentication subsystem phát** khi đã biết kết quả:

```json
{"kind":"security_event","event":"authentication_failed","outcome":"DENY","request_id":"req_01"}
```

Không suy diễn lý do xác thực chỉ từ HTTP 401; 401 có thể do thiếu token, token hết hạn hoặc nhiều nguyên nhân khác. Tương tự, username do client thử đăng nhập không phải actor đã xác thực.

## 4. Sơ đồ các nguồn phát log phải kiểm soát

```text
Client / Browser
    │
    ▼
CDN / WAF / Reverse Proxy ─────► Edge access log
    │
    ▼
API Gateway ───────────────────► Gateway access log
    │
    ▼
Tomcat / Jetty / Netty ────────► HTTP server access log
    │
    ▼
Servlet Filter / WebFilter ────► Request diagnostic log
    │
    ▼
Security Filter / Auth Handler ► Security / audit event
    │
    ▼
Controller / Service / Client ─► Application / exception log
    │
    ▼
Tracing / MDC / APM ───────────► Telemetry / span attributes
    │
    ▼
Collector / SIEM / Export ─────► Index / dashboard / backup
```

Sửa `OncePerRequestFilter` trong Spring không làm thay đổi pattern của Tomcat `AccessLogValve` hoặc gateway. Đặt `additivity=false` ở Logback không che được message chứa password. Đổi logger level không tự loại dữ liệu nhạy cảm trong trace span hay file log đã được tạo từ trước.

**Kiểm tra toàn pipeline** thay vì chỉ kiểm tra một nguồn ứng dụng.

## 5. Dữ liệu HTTP nào có thể đi vào log?

| Thành phần | Rủi ro | Chính sách mặc định |
| --- | --- | --- |
| Method | Có thể có chuỗi lạ do client gửi | Allowlist tên method và giới hạn ký tự |
| Matched route template | Thường an toàn hơn raw path | Chỉ dùng metadata tin cậy từ router |
| Raw path/URI | ID, email, reset token | Không ghi mặc định ở tuyến nhạy cảm |
| Query string | `code`, `token`, email, mật khẩu | Không ghi mặc định |
| Request headers | Authorization, Cookie, API key, signature | Không dump map; chỉ allowlist nếu cần |
| Response headers | Set-Cookie, redirect URL mang code | Không dump map |
| Request/response body | Password, PII, PAN/CVV, token | Không log mặc định |
| Status | HTTP 2xx/4xx/5xx | Thường phù hợp cho metadata-only |
| Duration | Thời gian đo tại một hop | Ghi đơn vị và điểm bắt đầu/kết thúc |
| Request/trace ID | Giúp correlation | Validate định dạng/độ dài; không coi là danh tính actor |
| Client IP | Có thể là PII hoặc IP của proxy | Chỉ ghi theo mục đích, chính sách và trust boundary |
| User-Agent/Referer | Dữ liệu do client chọn, có thể chứa query/điều khiển | Không ghi nguyên mặc định |

**Path không phải lúc nào cũng an toàn dù đã bỏ query.** `/reset/{token}` hoặc `/users/{email}` chứa dữ liệu nhạy cảm trong path variable. Vì vậy raw `getRequestURI()` vẫn có nguy cơ. Tránh cả `%r`/request line của proxy nếu nó chứa query.

## 6. Dùng route metadata đáng tin, không tự ghép URL

Một policy dễ sai:

```java
// KHÔNG NÊN: so khớp raw path đơn giản và log toàn bộ phần còn lại.
if (!request.getRequestURI().contains("login")) {
    logger.debug("request={}", request);
}
```

Đây chỉ là trích đoạn minh họa rủi ro, không phải chương trình độc lập. Cách làm này bỏ sót endpoint version mới, refresh token, phương thức upload hoặc encoding lạ; nó còn có thể gọi `toString()` trên object chứa dữ liệu bí mật.

Thay vào đó:

1. **Ở route registry/controller metadata**, gắn mức nhạy cảm cho từng operation.
2. **Lúc log**, lấy matched route template của framework nếu có; không lấy chuỗi path tự nhận từ header/body.
3. **UNKNOWN/404** phải mặc định an toàn: ghi `UNMATCHED`, không dump raw URL.
4. **API version mới** chưa được phân loại phải có default metadata-only hoặc fail-safe.
5. Cần test HTTP method, route aliases, prefix reverse proxy, trailing slash, percent-encoded path và URL normalization.
6. Với `/graphql`, gắn policy theo operation hoặc không log variables/body trên toàn route chung.

Nên quản lý chính sách trong một lớp trung tâm để bộ lọc request, audit event builder và collector dùng cách phân loại thống nhất. Tuy vậy, việc route metadata có nhãn `PUBLIC` không có nghĩa có thể ghi body bất kỳ; từng **field** vẫn cần kiểm tra.

## 7. Ví dụ Java 17 chạy độc lập: giữ access log an toàn

Ví dụ sau mô phỏng **matched route đã được router đáng tin cấp**. Event được phân loại và chỉ chứa các trường an toàn; query, Authorization header và body có chứa canary giả **không được đưa vào output**. Đối với tuyến nhạy cảm, cả route chi tiết được thay bằng nhãn tổng quát.

Đây là chương trình Java thuần, không chạy HTTP server. Trong ứng dụng thật, không nhận `matchedRoute` do client tùy ý khai mà phải lấy nó từ router/framework.

Lưu thành **`SensitiveEndpointLoggingDemo.java`**:

```java
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

public final class SensitiveEndpointLoggingDemo {
    enum Category { GENERAL, AUTH, PAYMENT, SECRET, UNKNOWN }

    record Exchange(
            String method,
            String matchedRoute,
            int status,
            long durationMs,
            String requestId,
            String query,
            String authorization,
            String body) {}

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private static final Set<String> SAFE_METHODS =
            Set.of("GET", "POST", "PUT", "PATCH", "DELETE");

    private static final Set<String> ROUTES = Set.of(
            "/auth/login",
            "/oauth/token",
            "/payments/{id}/confirm",
            "/orders/{id}",
            "/internal/keys");

    private static Category category(String route) {
        return switch (route) {
            case "/auth/login", "/oauth/token" -> Category.AUTH;
            case "/payments/{id}/confirm" -> Category.PAYMENT;
            case "/internal/keys" -> Category.SECRET;
            case "/orders/{id}" -> Category.GENERAL;
            default -> Category.UNKNOWN;
        };
    }

    private static String safeRoute(Category category, String route) {
        return switch (category) {
            case AUTH -> "AUTH_ENDPOINT";
            case PAYMENT -> "PAYMENT_ENDPOINT";
            case SECRET -> "SENSITIVE_ENDPOINT";
            case GENERAL -> route;
            case UNKNOWN -> "UNMATCHED";
        };
    }

    private static String safeId(String value) {
        return value != null && SAFE_ID.matcher(value).matches()
                ? value : "invalid";
    }

    private static String accessLine(Exchange e) {
        String route = ROUTES.contains(e.matchedRoute())
                ? e.matchedRoute() : "UNMATCHED";
        Category type = category(route);
        String method = SAFE_METHODS.contains(e.method())
                ? e.method() : "OTHER";
        int status = e.status() >= 100 && e.status() <= 599
                ? e.status() : 0;
        long duration = Math.max(0L, e.durationMs());

        // Không dùng e.query(), e.authorization(), e.body().
        return "kind=http_access"
                + " method=" + method
                + " route=" + safeRoute(type, route)
                + " status=" + status
                + " duration_ms=" + duration
                + " category=" + type
                + " request_id=" + safeId(e.requestId());
    }

    public static void main(String[] args) {
        List<Exchange> data = List.of(
                new Exchange(
                    "POST", "/auth/login", 401, 12, "req_01",
                    "code=SENSITIVE_CANARY_314",
                    "Bearer SENSITIVE_CANARY_314",
                    "password=SENSITIVE_CANARY_314"),
                new Exchange(
                    "GET", "/orders/{id}", 200, 8, "req_02",
                    "token=SENSITIVE_CANARY_314",
                    "Bearer SENSITIVE_CANARY_314",
                    "SENSITIVE_CANARY_314"),
                new Exchange(
                    "POST", "/payments/{id}/confirm", 200, 26, "req_03",
                    "card=SENSITIVE_CANARY_314",
                    "Bearer SENSITIVE_CANARY_314",
                    "SENSITIVE_CANARY_314"),
                new Exchange(
                    "GET", "/bad/path", 404, 3, "req_04",
                    "token=SENSITIVE_CANARY_314",
                    "Bearer SENSITIVE_CANARY_314",
                    "SENSITIVE_CANARY_314"));

        for (Exchange e : data) {
            System.out.println(accessLine(e));
        }

        // Sự kiện này giả định authentication subsystem đã xác định outcome.
        System.out.println(
                "kind=security_event event=authentication_failed"
                + " outcome=DENY request_id=req_01");
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 SensitiveEndpointLoggingDemo.java
java SensitiveEndpointLoggingDemo
```

**Stdout chính xác:**

```text
kind=http_access method=POST route=AUTH_ENDPOINT status=401 duration_ms=12 category=AUTH request_id=req_01
kind=http_access method=GET route=/orders/{id} status=200 duration_ms=8 category=GENERAL request_id=req_02
kind=http_access method=POST route=PAYMENT_ENDPOINT status=200 duration_ms=26 category=PAYMENT request_id=req_03
kind=http_access method=GET route=UNMATCHED status=404 duration_ms=3 category=UNKNOWN request_id=req_04
kind=security_event event=authentication_failed outcome=DENY request_id=req_01
```

**Giải thích:** canary `SENSITIVE_CANARY_314` có mặt trong mọi mẫu query/header/body nhưng không xuất hiện trên stdout. Route payment/auth chỉ được in dưới dạng class. Đường dẫn chưa match không được in thô. Request ID được kiểm tra theo định dạng cố định; event an ninh được phát riêng chứ không suy ra kết quả xác thực chỉ từ status.

**Giới hạn:** chương trình không tự xác thực client, phân loại route dựa trên một giá trị mà ví dụ giả định đã được router cấp, không xử lý async, không lưu file và không bảo đảm audit. Nó chứng minh **chọn trường log an toàn**, không chứng minh toàn bộ pipeline đã không lộ canary.

## 8. Spring MVC Servlet: ví dụ filter chỉ ghi metadata

Đối với ứng dụng **Spring Boot 3+ / Spring MVC / Jakarta Servlet**, một `OncePerRequestFilter` có thể ghi metadata sau một lượt xử lý đồng bộ. Đoạn sau là **mã tích hợp**, cần Spring Web, SLF4J và cấu hình ứng dụng; không phải Java độc lập:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

@Component
public class MinimalWebAccessLogFilter extends OncePerRequestFilter {
    private static final Logger LOG =
            LoggerFactory.getLogger("http.access.safe");
    private static final Set<String> METHODS =
            Set.of("GET", "POST", "PUT", "PATCH", "DELETE");

    private static String safeMethod(String raw) {
        return METHODS.contains(raw) ? raw : "OTHER";
    }

    private static String safeRoute(Object matched) {
        if (!(matched instanceof String route)) {
            return "UNMATCHED";
        }
        return switch (route) {
            case "/auth/login", "/oauth/token" -> "AUTH_ENDPOINT";
            case "/payments/{id}/confirm" -> "PAYMENT_ENDPOINT";
            case "/orders/{id}" -> "/orders/{id}";
            default -> "OTHER_ENDPOINT";
        };
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        long started = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            // Chỉ minh họa request hoàn tất đồng bộ.
            if (!request.isAsyncStarted()) {
                Object route = request.getAttribute(
                        HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
                long ms = TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - started);

                LOG.info(
                    "kind=http_access method={} route={} status={} duration_ms={}",
                    safeMethod(request.getMethod()),
                    safeRoute(route), response.getStatus(), ms);
            }
        }
    }
}
```

Trong ví dụ, logger không đọc `getQueryString()`, `getHeader("Authorization")`, `getCookies()`, request body, response body hoặc raw `getRequestURI()`. Khi route chưa có matched pattern, nó ghi nhãn generic.

**Không dùng nguyên xi nếu cần một event chính xác cho mọi request:**

- `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` có thể chưa có khi request bị chặn trước MVC hoặc không match.
- Với async dispatch, SSE, streaming hoặc WebSocket, request có thể tiếp tục sau khi `finally` chạy. Code trên bỏ qua khi `isAsyncStarted()` và **chưa có completion hook**, vì vậy một số request async sẽ không có event từ filter này.
- Error handler có thể thay status sau thời điểm filter `finally`. Cần đo ở điểm hoàn tất được chọn (server access log hoặc lifecycle listener đã kiểm thử).
- Thứ tự các filter khác, authentication filter và exception handling có thể tạo log độc lập.
- Route mới mặc định `OTHER_ENDPOINT`; cần review chính sách và test khi thêm API.

Nếu thực sự cần access event đầy đủ cho async/error, dùng cơ chế lifecycle/`AsyncListener`, server instrumentation hoặc framework observability phù hợp, có bảo vệ chống log trùng.

## 9. `shouldNotFilter` không tắt mọi logging

`OncePerRequestFilter` hỗ trợ `shouldNotFilter(HttpServletRequest)`. Khi trả true, **filter đó** bỏ qua request; controller vẫn nhận request bình thường nếu security/route khác cho phép.

Cơ chế này hợp lý cho **filter chuyên log payload để debug**, không phải lý do xóa luôn security event hoặc access metadata cần giữ. Một số hiểu nhầm:

- `shouldNotFilter` không tắt Tomcat AccessLogValve, Nginx access log hoặc HTTP client interceptor.
- Nếu một request đi qua nhiều dispatch, không thể tự suy “once” nghĩa là một event duy nhất cho toàn vòng đời. `shouldNotFilterAsyncDispatch` và `shouldNotFilterErrorDispatch` có mặc định riêng.
- Filter chạy trước routing thường **chưa biết route template**; match chuỗi URI ở đây cần cực kỳ thận trọng và không thay thế chính sách route registry.
- `ContentCachingRequestWrapper` không bảo đảm request body luôn có đủ dữ liệu để log, và caching payload tăng RAM. Đối với endpoint nhạy cảm, đừng cố đọc body rồi redact nếu có thể **không thu body ngay từ đầu**.

**Spring WebFlux dùng `WebFilter` hoặc instrumentation của reactive stack**, không dùng nguyên `OncePerRequestFilter`. Khi inspect body của reactive request, việc subscribe/wrap sai có thể tiêu thụ stream hoặc thay đổi backpressure.

## 10. CommonsRequestLoggingFilter: cấu hình thiên về privacy

Spring Framework cung cấp `CommonsRequestLoggingFilter` với các lựa chọn include metadata. Khi không có yêu cầu log payload, có thể cấu hình ví dụ:

```java
// Trích đoạn Spring: cần imports cho @Bean và CommonsRequestLoggingFilter.
@Bean
CommonsRequestLoggingFilter safeRequestLoggingFilter() {
    CommonsRequestLoggingFilter filter = new CommonsRequestLoggingFilter();
    filter.setIncludeClientInfo(false);
    filter.setIncludeQueryString(false);
    filter.setIncludeHeaders(false);
    filter.setIncludePayload(false);
    return filter;
}
```

Đoạn này không phải chương trình độc lập, chỉ cho thấy các lựa chọn cấu hình. Việc `CommonsRequestLoggingFilter` có thực sự phát log còn phụ thuộc logger level và backend.

**Lưu ý:** bật `setIncludePayload(true)` không đồng nghĩa chắc chắn nhìn được toàn bộ body: phần payload có thể chỉ gồm các byte đã được tiêu thụ/cached tại thời điểm framework ghi log. `maxPayloadLength` và wrapper có giới hạn riêng. Với login, token, payment, tài liệu nhạy cảm, tránh dùng body logging mặc định rồi tin rằng regex có thể che hết.

## 11. Logback và Log4j2: routing khác với redaction

Logback có thể tách một logger riêng `http.access.safe` để hạn chế việc event access đi lẫn với application stream:

```xml
<configuration>
    <appender name="ACCESS" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>
    <logger name="http.access.safe" level="INFO" additivity="false">
        <appender-ref ref="ACCESS"/>
    </logger>
    <root level="INFO"/>
</configuration>
```

Đây là **mẫu tối giản của routing**, không phải cấu hình production hoàn chỉnh. `additivity="false"` ngăn logger access forward lên root appenders của Logback. Nó **không** bảo vệ nếu code đã đưa password vào message. Trong production cần định nghĩa appender application, retention, quyền ghi và log shipper rõ ràng.

`ThresholdFilter`, `LevelFilter` hoặc level INFO/WARN chọn event theo severity, **không hiểu nội dung nào là secret**. Với Log4j2, RegexFilter cũng không thay thế field allowlist; regex khó bắt mọi nested JSON, exception, nhiều encoding và token format mới.

Quy tắc triển khai nên là: **giới hạn field trước khi tạo event → encode có cấu trúc → routing đúng sink → masking bổ sung → RBAC/retention**.

## 12. Embedded Tomcat access log cần cấu hình riêng

Ứng dụng Spring Boot dùng embedded Tomcat có thể bật access log:

```properties
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.pattern=%m %U %s %D
```

Pattern minh họa ghi method, raw URL path, status, duration (mili giây theo Tomcat AccessLogValve). Nó không chủ động ghi query string hay header, nhưng **`%U` vẫn là path thực**, có thể chứa reset token hoặc email. Đừng gọi pattern này là “an toàn cho mọi endpoint”.

Nếu app không bảo đảm path không chứa secret, cân nhắc pattern tối giản hơn như `%m %s %D` hoặc cơ chế access log metadata dựa trên route class, rồi kiểm tra nhu cầu điều tra. Gateway/reverse proxy phải được cấu hình tương tự.

Theo tài liệu Tomcat, `AccessLogValve` có:

- `conditionIf="marker"`: chỉ log khi request attribute `marker` không null.
- `conditionUnless="marker"`: chỉ log khi request attribute `marker` null.

Ví dụ **cấu hình Valve trích đoạn** khi tự quản lý Tomcat, không phải đoạn có thể dán nguyên vào `application.properties`:

```xml
<Valve className="org.apache.catalina.valves.AccessLogValve"
       directory="logs"
       prefix="access"
       suffix=".log"
       pattern="%m %s %D"
       conditionUnless="omitContainerAccessLog"/>
```

Một Servlet Filter có thể đặt attribute `omitContainerAccessLog` khi tổ chức đã quyết định **không ghi container access event** ở một nhóm request nhất định, chẳng hạn health probe gây nhiễu. **Không mặc định bỏ toàn bộ login failures hoặc token issuance:** security/audit event tối thiểu vẫn cần được phát theo policy. Nếu request bị chặn trước filter, marker có thể chưa được đặt; async/error dispatch phải được kiểm thử.

Cơ chế Valve này **chỉ áp dụng cho Tomcat**, không tự dùng được cho Jetty, Undertow, Reactor Netty hoặc gateway. Không trộn lẫn quyền điều khiển log ứng dụng với log container.

## 13. Security event và audit phải sống sót sau lọc payload

Các sự kiện an toàn cần được tạo từ **security/business logic** ở đúng điểm biết outcome:

| Hoạt động | Security event gợi ý | Không được ghi |
| --- | --- | --- |
| Login không thành công | `authentication_failed` và reason code an toàn | Password, OTP, tên tự khai như actor đã xác thực |
| Token được cấp | `token_issued` với client/actor đã xác thực | Token/JWT/refresh token thật |
| Yêu cầu reset | `password_reset_requested` | Reset code/link, email thô nếu không cần |
| Truy cập bị từ chối | `authorization_denied` | Raw resource secret, header tự khai danh tính |
| Thay đổi MFA | `security_setting_changed` | MFA seed, recovery codes |
| Thanh toán | `payment_attempted` / `payment_completed` | Card data, payload bí mật |

Không suy `outcome=SUCCESS` chỉ từ HTTP 200 khi API trả job ID cho xử lý async. Không gán actor từ `X-User-ID`/body. Nếu sự kiện audit có yêu cầu bền vững, không để nó bị drop theo queue policy của debug logging mà không đánh giá trước.

**Privacy filtering không được trở thành “xóa bằng chứng”.** Có thể chặn payload ở mọi logger nhưng vẫn giữ event bảo mật tối thiểu trong sink phù hợp và có phân quyền/retention riêng.

## 14. Những nguồn rò rỉ khó thấy: exception, HTTP client, APM

Đoạn sau là ví dụ **không an toàn**:

```java
// Trích đoạn KHÔNG AN TOÀN; không dùng với dữ liệu có secret.
logger.error("Request failed: {}", request);
logger.debug("headers={} body={}", requestHeaders, requestBody);
logger.error("External service failed", exceptionContainingBody);
```

Rủi ro:

- `request.toString()` hoặc DTO `toString()` có thể chứa password/token.
- Exception của SDK/HTTP client có thể mang URL kèm query, response body, headers.
- `@ControllerAdvice` và error handling có thể log nguyên exception/message.
- Client debugging trong HTTP library có thể bật khi đổi level DEBUG/TRACE.
- APM/tracing có thể thu request parameters, raw URL, span attributes hoặc baggage.
- MDC chứa user ID/tenant/request ID chưa xác minh có thể bị copy sang mọi log.
- Collector/dashboard/CSV export có thể hiển thị hoặc lưu raw data nếu redaction chỉ nằm ở tầng UI.

Giải pháp là **safe event fields**, error code, route template, status và duration; kiểm thử cả tình huống thành công lẫn thất bại. Nếu cần stack trace, kiểm tra nó có chứa data từ request/dependency và phân quyền sink thích hợp.

## 15. HTTP URL, proxy và dữ liệu điều khiển

Một URL khôi phục tài khoản có thể chứa token trong path:

```text
GET /reset/sensitive-reset-token?email=user@example.com
```

Ngay cả khi không ghi query, `getRequestURI()` vẫn chứa token. Hãy dùng route `/reset/{token}` hoặc nhãn `PASSWORD_RESET_ENDPOINT` khi framework có matched route đáng tin.

Các trường `Referer` và `User-Agent` cũng có thể chứa query secret hoặc ký tự điều khiển. `X-Forwarded-For` chỉ đáng tin sau khi qua proxy đã được cấu hình làm nguồn tin cậy và edge đã strip forwarded headers do client tự gửi. IP không phải danh tính người đã xác thực.

`X-Request-ID` và `traceparent` là metadata tương quan, không chứng minh actor. Validate format/độ dài, tránh log injection; không dùng các ID có cardinality cao làm metric label. Với async/thread pool, MDC phải được quản lý theo scope để không lẫn context giữa request.

## 16. Tracing, metrics và actuator cũng là nguồn dữ liệu

Ngoài logger ứng dụng:

- OpenTelemetry/APM có thể chứa `http.url`, query, span attributes hoặc exception details, cần cấu hình riêng.
- Metrics nên có `http.route` dạng template thay vì raw URI/user ID/trace ID có cardinality vô hạn.
- Spring Boot Actuator `httpexchanges` có thể ghi dữ liệu trao đổi HTTP nếu được cấu hình repository. Cần xem schema, retention, trường được ghi và phân quyền.
- Các management endpoints như `/actuator/env`, `/actuator/configprops`, `/actuator/logfile` hoặc `/actuator/heapdump` có thể chứa dữ liệu nhạy cảm; **hạn chế quyền truy cập/exposure** là yêu cầu khác với việc lọc logging của chúng.
- HTTP gateway, cloud load balancer và CDN có hệ thống access log riêng; phải review từng source.
- Bản export/backups của log cũng phải có chính sách retention và quyền truy cập; masking trên dashboard không xóa dữ liệu đã được lưu ở index.

Một tổ chức không thể tuyên bố “đã lọc token khỏi log” chỉ vì không thấy token trong một file của ứng dụng. Phải có kiểm chứng theo **mọi nơi có khả năng thu dữ liệu**.

## 17. Redaction và field allowlist: chọn giải pháp nào?

**Field allowlist** thường đáng tin cậy hơn regex blacklist toàn bộ message. Với hệ thống thanh toán, có thể cho phép event chứa mã phương thức và status mà không ghi card number:

```text
event=payment_attempted
payment.method=CARD
route=PAYMENT_ENDPOINT
status=DECLINED
duration_ms=34
request_id=req_04
```

Nếu chính sách cho phép chỉ lưu last4, phải xác định nguồn last4 đáng tin, cách lưu và quyền truy cập, không lấy nguyên PAN vào log rồi regex trích. Dữ liệu đã hash không tự trở nên vô danh nếu miền giá trị nhỏ hoặc có thể liên kết với nhiều nguồn khác.

Các trường cần có giới hạn: loại, độ dài, tập ký tự, Unicode control, nested objects, schema version, retention và nơi sử dụng. JSON structured encoder giúp escape đúng cú pháp, nhưng không tự thay thế HTML/CSV escaping khi export.

## 18. Fail-safe cho endpoint chưa được biết

Cách blacklist có nguy cơ:

```text
Nếu path chứa login hoặc token → không log body
Các path khác                   → log nguyên body
```

Một endpoint mới `/api/v3/credentials/rotate` sẽ lọt qua. **Fail-safe logging** nên đặt mặc định:

- Route mới/chưa match → metadata-only, không raw path/query/body/headers.
- Các nhóm AUTH/PAYMENT/SECRET → metadata-only và security event khi cần.
- Chỉ field có policy rõ mới được ghi, ngay cả với route được coi là public.
- Nếu collector parser lỗi → báo metric, quarantine theo quy trình, không fallback dump raw payload ra stdout.
- Nếu audit sink hỏng → ứng xử theo chính sách độ bền đã được phê duyệt.
- Không cho request tự chọn tên logger, file, index hoặc event type.

Quy tắc fail-safe này **không phải chặn request**. Nó chỉ tránh xuất dữ liệu có nguy cơ khi policy chưa biết.

## 19. Kiểm thử bằng canary giả end-to-end

Dùng chuỗi giả, không phải secret thật:

```text
SENSITIVE_CANARY_314
```

Đưa canary vào password, query, raw path, Authorization, Cookie, response body thử và exception test. Sau đó tìm tại:

1. File/stdout/stderr của ứng dụng và server access log.
2. Gateway, proxy, WAF hoặc CDN access log.
3. HTTP client debug log, Spring security/application exception log.
4. APM/tracing spans và MDC-enriched events.
5. Collector buffer, index backend, dashboard.
6. Export/snapshot/backup trong phạm vi test có quyền truy cập.

**Kỳ vọng:** canary **không xuất hiện** trong bất cứ sink nào không được phép chứa dữ liệu đó. Đồng thời login failed vẫn có security event an toàn nếu yêu cầu hệ thống cần nó.

Test thêm:

- 200/400/401/403/500, method khác nhau, route aliases và URL encoding.
- Request async, SSE, error dispatch, streaming, 404 và request bị chặn trước filter.
- Bật DEBUG của HTTP client/framework để xem dữ liệu nhạy cảm có phát sinh thêm không.
- Payload JSON nested, multipart, GraphQL variables, body lớn, header có CRLF/control chars.
- Nhiều tenant, MDC không bị rò; collector không cho người tenant A xem log của tenant B.
- Queue đầy, disk full, collector lỗi, log bị drop và chính sách alert.

Đừng coi “không thấy access log” là PASS nếu security event quan trọng cũng mất. Đếm event theo nguồn và đối chiếu trạng thái thật, không chỉ theo số dòng toàn pipeline vì cùng request có thể có log ở nhiều hop.

## 20. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Đã lọc Spring log nhưng reset token vẫn xuất hiện | Tomcat/gateway ghi raw path | Rà pattern từng tầng, dùng class/template |
| `shouldNotFilter` true mà vẫn có request log | Một filter/server/proxy khác phát | Inventory từng source |
| Bật DEBUG lộ password | HTTP client, exception hoặc DTO `toString()` | Safe fields, tắt payload capture |
| Chỉ bỏ query vẫn lộ token | Token nằm trong path | Không log raw request URI |
| GraphQL vẫn lộ secret | Variables nằm trong body ở một route chung | Không dump GraphQL body mặc định |
| Không có security alert khi login thất bại | Bỏ cả security event cùng payload log | Tách security event từ auth handler |
| Async request không có access log | `finally` chạy sớm, không có completion hook | Dùng lifecycle instrumentation |
| Pattern có `%U` mà được gọi là “đã ẩn path” | `%U` là raw path trong Tomcat | Loại trường đó hoặc xử lý an toàn ở nguồn |
| Actor bị ghi sai | Tin header user ID/client-provided data | Security principal được xác minh |
| Lộ secret trong export dù dashboard đã mask | Dữ liệu gốc còn ở index/snapshot | Không thu từ nguồn, bảo vệ bản sao |
| Bật logger level WARN vẫn có token | ERROR log chứa credential hoặc access log riêng | Lọc field, không chỉ level |
| Logging chậm khi tăng DEBUG | Queue/encoder/I/O quá tải | Giới hạn phạm vi debug và đo drop/latency |
| Endpoint mới không được bảo vệ | Blacklist theo path thiếu route mới | Fail-safe policy và contract test |

## 21. Quy trình triển khai

1. **Inventory các nguồn phát log** và nơi lưu: gateway, server, app, client, APM, collector, export.
2. **Phân loại endpoint** theo route/operation metadata và review owner.
3. **Định nghĩa event schema tối thiểu** gồm safe method, route class, status, duration, correlation đã validate.
4. **Loại body/query/headers nhạy cảm tại nguồn**; không dựa vào regex backend.
5. **Giữ security/audit event riêng** với actor/outcome từ logic đã xác thực.
6. **Triển khai đúng stack**: Servlet/OncePerRequestFilter, WebFlux/WebFilter, Tomcat AccessLogValve, proxy tương ứng.
7. **Kiểm tra async/error/404** và trường hợp request bị chặn trước MVC.
8. **Kiểm thử canary toàn pipeline**, bao gồm khi bật DEBUG và tình huống exception.
9. **Bảo vệ kho log** bằng RBAC, encryption, retention, tách quyền export/delete và theo dõi truy cập.
10. **Giám sát logging queue/collector** để phát hiện drop, backlog hoặc hỏng sink.

## 22. Checklist hoàn thành

- [ ] Danh sách endpoint nhạy cảm có owner và policy rõ, không chỉ so tên path.
- [ ] Route UNKNOWN/mới có mặc định metadata-only.
- [ ] Login/token/reset/payment/upload không dump request hoặc response body.
- [ ] Không ghi token, cookie, Authorization, OTP, API key hoặc query nhạy cảm.
- [ ] Raw path có thể chứa reset token/PII; đã dùng route template/class phù hợp.
- [ ] Security event bắt buộc vẫn được tạo từ auth/business handler.
- [ ] Tomcat/proxy/gateway access log được kiểm soát riêng với SLF4J.
- [ ] Spring Servlet filter không bị nhầm với WebFlux, async/error dispatch được xử lý đúng.
- [ ] Exception, HTTP client, tracing, APM, MDC và actuator đã được review.
- [ ] Bật DEBUG không làm secret quay lại log.
- [ ] Canary kiểm thử không xuất hiện ở các sink không được phép.
- [ ] Có RBAC, retention, secure export và giám sát log drop/sink failure.

**Ghi nhớ:** filter endpoint nhạy cảm **không phải xóa sạch log của endpoint**. Hãy **không thu dữ liệu bí mật**, vẫn giữ **metadata và security event an toàn**, kiểm soát **mọi nguồn log** và xác minh bằng test canary. Level hoặc một `OncePerRequestFilter` riêng lẻ không bảo vệ được toàn bộ luồng.

### Tài liệu tham khảo

- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [MITRE — CWE-117](https://cwe.mitre.org/data/definitions/117.html)
- [Spring Framework — OncePerRequestFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html)
- [Spring Framework — Servlet async request processing](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Framework — CommonsRequestLoggingFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/CommonsRequestLoggingFilter.html)
- [Tomcat — AccessLogValve](https://tomcat.apache.org/tomcat-10.1-doc/config/valve.html#Access_Logging)
- [Spring Boot — HTTP exchange recording](https://docs.spring.io/spring-boot/reference/actuator/http-exchanges.html)
