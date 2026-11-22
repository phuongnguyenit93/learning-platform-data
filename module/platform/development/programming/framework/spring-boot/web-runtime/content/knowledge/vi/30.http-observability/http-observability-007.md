# Phân biệt log request body với quan sát an toàn metadata

Một API Spring Boot trả HTTP 400, 500 hoặc chạy chậm khiến người phát triển muốn bật log toàn bộ request body để biết client đã gửi gì. Cách này có thể vô tình tạo ra một kho dữ liệu thứ hai gồm mật khẩu, OTP, bearer token, session cookie, email, địa chỉ, dữ liệu thanh toán, nội dung trao đổi, tài liệu và thông tin nhạy cảm. Log không dừng ở console: nó thường đi qua agent, hệ thống phân tích tập trung, alert, ticket, backup và các tài khoản vận hành khác nhau.

**Quan sát an toàn metadata** có mục đích khác: giúp trả lời **request loại gì, đến endpoint nào, trả mã gì, mất bao lâu, gặp nhóm lỗi nào, liên hệ với trace nào** mà không cần đọc hay lưu nội dung request. Trong phần lớn bài toán giám sát HTTP, metrics và logs metadata có ích hơn việc sao chép body.

Bài này thuộc nhóm **Quan sát HTTP**, tập trung **Spring Boot 3.x, Spring MVC/Servlet, Java 17+, Micrometer Observation và Actuator**. Ví dụ chạy được có `OncePerRequestFilter` ghi method, route template, status, duration và ID do server tạo, **không đọc body**. Test tự động xác minh một request có email, ghi chú và token giả không làm chúng lọt vào log. Cuối bài phân biệt WebFlux, async dispatch, reverse proxy, quyền truy cập log và quy trình debug an toàn.

**Nguyên tắc:** không thu thập dữ liệu nhạy cảm ngay từ đầu tốt hơn việc thu thập tất cả rồi cố ẩn bằng regex. Ngay cả metadata cũng phải được chọn theo allowlist, không phải ghi hết những gì HTTP request chứa.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt request-body logging với HTTP access logs, application metadata logs, metrics, traces và audit events.
- Phân loại request body, query, URL path, headers và thông tin nào có thể chứa bí mật hoặc PII.
- Chọn trường metadata hữu ích: method, route pattern, status, latency, outcome và correlation ID đáng tin.
- Hiểu `ContentCachingRequestWrapper` chỉ cache bytes **đã được đọc**, không tự đọc body và không tự redaction.
- Viết `OncePerRequestFilter` tạo UUID, dùng `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` và dọn MDC đúng cách.
- Biết tại sao `request.getRequestURI()` và `getQueryString()` không phải phương án dự phòng an toàn cho route.
- Cấu hình `spring.mvc.log-request-details=false`, xem xét Tomcat access logs và log của proxy.
- Dùng `http.server.requests` của Micrometer để theo dõi HTTP error rate và latency theo labels ít giá trị.
- Test với `MockMvc` + `OutputCaptureExtension` rằng secrets giả không xuất hiện trong log.
- Nhận biết khác biệt khi có error/async dispatch, upload, SSE, WebSocket hoặc WebFlux.
- Thiết kế quy trình điều tra sự cố không yêu cầu thu thập raw body của người dùng.

## 2. Body logging và metadata logging là hai lựa chọn khác nhau

Một HTTP request:

```http
POST /api/orders?source=checkout HTTP/1.1
Host: shop.example.test
Content-Type: application/json
Authorization: Bearer <REDACTED>
Cookie: SESSION=<REDACTED>

{
  "sku": "BOOK-001",
  "quantity": 2,
  "contactEmail": "fake.user@example.test",
  "deliveryNote": "Example only"
}
```

**Body log** ghi JSON hay các bytes của request thành text hoặc binary log. Nó có thể thu thập các trường ứng dụng chưa biết hoặc fields chỉ xuất hiện về sau, kể cả secret. **Metadata log** chỉ ghi một danh sách trường đã xét duyệt như:

```text
http_request method=POST route=/api/orders status=200 durationMs=12 requestId=550e8400-e29b-41d4-a716-446655440000
```

UUID và 12 ms trong ví dụ là giá trị giả; runtime sẽ tạo ID/thời gian khác nhau. Log này giúp liên hệ request với một lỗi mà không tiết lộ email hoặc ghi chú.

### 2.1. Bảng phân loại

| Thành phần | Ví dụ | Quyết định khởi đầu |
| --- | --- | --- |
| HTTP method | GET, POST, PUT | Thường log được sau khi giới hạn tập giá trị |
| Route template | `/api/orders/{id}` | Thường phù hợp cho logs/metrics |
| Raw URI | `/api/orders/user@example.test` | Tránh, có thể lộ định danh |
| Query | `?token=...` | Không log mặc định |
| Authorization/Cookie | Bearer token, session ID | Không log trực tiếp |
| Body | JSON, XML, form, multipart, binary | Không log mặc định |
| Content-Length | Độ dài do client khai báo | Chỉ dùng nếu cần và hiểu giới hạn |
| Content-Type | application/json | Có thể hợp lý nếu chuẩn hóa, không lấy raw parameters tùy ý |
| User-Agent/Referer | Header do client gửi | Cẩn trọng, chứa dữ liệu không đáng tin |
| X-Forwarded-For/IP | Địa chỉ của client/proxy | Cần trust boundary và privacy policy |
| Status | 200, 400, 500 | Thường log được |
| Latency | durationMs | Có ích, cần đo đúng lifecycle |
| Request/trace ID | Server/gateway tạo | Hữu ích cho correlation |
| Error category | VALIDATION_FAILED | Hữu ích nếu danh mục được giới hạn |

**Metadata không có nghĩa là 100% an toàn.** Một URI có email, query string có API key, Referer có mã xác thực hoặc IP có thể là dữ liệu nhạy cảm. Phải chọn trường theo mục đích thay vì log mọi thông tin không nằm trong body.

### 2.2. Một trường hợp thường bị hiểu sai

Request:

```http
GET /users/alice@example.test/reset?token=abc HTTP/1.1
```

Nếu logger chỉ in path/query mà không in body, nó vẫn làm lộ email và token. Thay bằng route template `/users/{id}/reset`, requestId và mã outcome. Hệ thống cũng nên tránh thiết kế API đưa secrets vào URL ngay từ đầu vì browser history, proxy và access logs vẫn có thể ghi.

## 3. Vì sao log body là rủi ro bảo mật và vận hành?

### 3.1. Secret và PII xuất hiện ở rất nhiều dạng

Payload có thể chứa mật khẩu, OTP, recovery code, access token, API key, thông tin thanh toán, địa chỉ, email, số điện thoại, dữ liệu sức khỏe, hồ sơ nhân sự, tài liệu upload và nội dung trao đổi. Thậm chí một field tên đơn giản như `note` hoặc `metadata` có thể chứa dữ liệu nhạy cảm mà người lập trình filter không dự đoán.

Theo OWASP Logging Cheat Sheet, session identifiers, access tokens, passwords, thông tin cá nhân nhạy cảm, encryption keys và các dữ liệu phân loại bảo mật cao thường **không nên ghi trực tiếp** vào log. Việc log không đúng có thể tạo bản sao khó thu hồi trong log centralization, backup hoặc support cases.

### 3.2. Log injection

Raw body hoặc User-Agent do client điều khiển có thể chứa newline/control characters:

```text
note=ok
ERROR privileged.admin.event
```

Nếu in nguyên chuỗi, hệ thống log có thể bị giả một dòng thông điệp độc lập, khiến phân tích sai và cảnh báo nhiễu. Cần ưu tiên **không log raw input**, và với thông tin được phép thì dùng chuẩn encoding/escaping, structured logging và validation.

### 3.3. Lỗi đúng đắn HTTP

Một Servlet filter tự gọi `request.getInputStream().readAllBytes()` trước controller có thể tiêu thụ request body. Khi `@RequestBody`/Jackson cần đọc, nó có thể nhận EOF hoặc lỗi parse. Giữ toàn bộ body trong RAM để log làm tăng CPU, GC, upload latency và memory; tệp multipart/streaming lớn còn nguy hiểm hơn.

### 3.4. Truncation và sampling không chữa vấn đề riêng tư

Log 1 KB đầu JSON vẫn có thể chứa token hoặc email. Log chỉ 1% requests vẫn lộ dữ liệu thật của 1% mẫu. Dùng DEBUG thay INFO vẫn ghi dữ liệu khi debug được bật; log storage vẫn cần quyền truy cập và retention. Vì vậy mặc định phải là **không thu thập raw body**.

## 4. Những hình thức quan sát HTTP

| Hình thức | Dữ liệu | Mục đích | Lưu ý |
| --- | --- | --- | --- |
| Tomcat/NGINX access log | Timestamp, request line, status, size, latency, IP | Traffic và gateway issues | Raw path/query có thể nhạy cảm |
| Application metadata log | Method, route, status, error category, requestId | Tìm request flow | Không in DTO/headers/body |
| Metrics | Counts, histograms, latency, status, route | Alert, dashboard, SLO | Tránh high-cardinality labels |
| Distributed trace | Span, trace ID, dependency latency | Tìm hop chậm/lỗi | Không đưa secrets vào span attributes |
| Audit event | Actor, action, resource type, outcome | Điều tra hành động nghiệp vụ | Quyền xem và retention riêng |
| Full request log | Raw HTTP request body | Debug input đặc biệt | Rủi ro cao, tránh trong production |

### 4.1. Access log không phải body log

Tomcat/NGINX access logs thường theo request line/status thay vì body, nhưng format có thể bị tùy chỉnh để ghi headers hoặc body. `%r`, `$request_uri`, `$http_referer` và `$http_user_agent` có thể chứa query, token hoặc text do attacker nhập. Tránh `$request_body`, `$http_authorization`, `$http_cookie` ở production nếu không có thiết kế đặc biệt.

Trong Boot 3.3, `server.tomcat.accesslog.enabled` mặc định `false`. Một app chỉ tắt Tomcat access log **không** tắt được NGINX, CDN, WAF hoặc API gateway logs.

### 4.2. Audit event không giống request dump

Muốn trả lời “ai thay đổi quyền tài khoản và kết quả là gì?”, hãy thiết kế một sự kiện audit với actor đã xác thực, action enum, outcome, timestamp, requestId và resource type, có thể thêm subject ID khi có căn cứ. Không lưu raw POST body chứa thông tin cá nhân rồi gọi đó là audit. Audit storage có thể cần chống sửa đổi, audit người xem và quy định giữ/xóa riêng.

## 5. Chọn metadata theo allowlist

Một tập field có ích:

- `service`, `environment`: giá trị cấu hình ổn định.
- `method`: GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS/OTHER.
- `route`: `/api/orders` hay `/api/orders/{id}` do framework match.
- `status`: HTTP code, cùng outcome 2xx/4xx/5xx nếu cần.
- `durationMs`: dùng đồng hồ monotonic hoặc Micrometer timer.
- `requestId`: UUID hoặc ID do gateway tin cậy tạo.
- `traceId/spanId`: từ Micrometer Tracing/OpenTelemetry nếu có.
- `errorCategory`: một enum đã xét duyệt, không raw exception message.

Không mặc định ghi raw `request.getRequestURI()`, `getQueryString()`, `getHeader("Authorization")`, `getHeader("Cookie")`, `getHeader("Referer")` hay `getParameterMap()`. Cả `BindingResult` và DTO `toString()` cũng có thể in rejected values/PII.

### 5.1. Route template, không phải path values

Controller có:

```java
@GetMapping("/api/orders/{id}")
public Map<String, String> get(@PathVariable String id) {
    return Map.of("state", "demo");
}
```

Đây là snippet trong controller đầy đủ ở mục sau. Với GET `/api/orders/customer-123?token=unsafe`, Spring MVC có thể đặt `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` thành `/api/orders/{id}` sau khi chọn handler.

Attribute này **không bảo đảm có trong mọi request**: request bị chặn trước MVC, 404, error dispatch hoặc custom handler mapping có thể không đặt. Nếu thiếu, log `UNMATCHED`; không fallback raw URI/query.

### 5.2. Cardinality

Metrics labels nên có số giá trị hữu hạn: method, route template, status, service, outcome. Gắn requestId hay userId thành label tạo một time series gần như cho mỗi request; điều đó làm metrics storage lớn và có nguy cơ lộ định danh. RequestId phù hợp logs/traces, **không** phải nhãn của `http.server.requests`.

## 6. ContentCachingRequestWrapper: đọc đúng bản chất

Spring Framework cung cấp `org.springframework.web.util.ContentCachingRequestWrapper` cho Servlet request. Javadoc Spring 6.1 nói rõ:

1. Wrapper chỉ **cache những bytes đã được downstream đọc** từ input stream/reader.
2. Nó **không tự đọc request content** khi được khởi tạo.
3. `getContentAsByteArray()` có thể trả mảng rỗng nếu chưa ai đọc.
4. Cache chỉ chứa bytes đã đọc tới thời điểm gọi, có thể partial.
5. `contentCacheLimit` giới hạn bytes lưu lại, không ngăn nội dung đã lưu chứa credentials.
6. Multipart, binary và streaming không phù hợp để coi là String log.

**Phản ví dụ đọc body trước controller:**

```java
// KHÔNG DÙNG: vừa consume stream vừa có thể lộ PII.
String rawBody = new String(
    request.getInputStream().readAllBytes(),
    StandardCharsets.UTF_8
);
log.info("payload={}", rawBody);
filterChain.doFilter(request, response);
```

Đây là snippet **không an toàn**, không phải chương trình đầy đủ. Nó có thể khiến `@RequestBody` bị lỗi do body đã hết.

**Phản ví dụ dùng cache limit nhưng vẫn lộ payload:**

```java
ContentCachingRequestWrapper wrapper =
        new ContentCachingRequestWrapper(request, 4096);

filterChain.doFilter(wrapper, response);

log.debug("payload={}",
    new String(wrapper.getContentAsByteArray(),
               StandardCharsets.UTF_8));
```

Đây vẫn là **phản ví dụ**, dù cache tối đa 4096 bytes. Những bytes đầu có thể chứa access token; wrapper không có chức năng redaction. Không nghĩ rằng limit hoặc DEBUG khiến log an toàn.

`ContentCachingResponseWrapper` phục vụ việc khác: nếu dùng để wrap/đọc response body phải xử lý `copyBodyToResponse()` đúng vòng đời; dùng sai có thể làm client không nhận được response. Trong bài này **không có nhu cầu wrap body**, nên không thêm wrappers.

### 6.1. Vì sao regex redaction không đáng tin?

Denylist tìm `password` dễ bỏ sót `pwd`, `session`, `otp`, field mới, nested JSON, XML, form, Unicode escape, gzip, binary hoặc dữ liệu tùy ý ở `note`. Không nên thu raw payload vào logger rồi hy vọng filter của log collector che đủ. Khi cần vài thông tin nghiệp vụ, hãy parse theo schema, map sang enum/nhóm đã được phép rồi log **kết quả**, không log DTO.

## 7. Spring Boot Java 17+ chạy được: filter metadata-only

Dự án có một API nhận JSON chứa email/note giả, một route với path variable và một filter không hề đọc input body. Demo dùng **Spring Boot 3.3.x + Spring MVC Servlet**, chạy đồng bộ. Không lưu database hay triển khai authentication; production phải bổ sung security và validation thích hợp.

### 7.1. Tạo project

Tạo project bằng [Spring Initializr](https://start.spring.io/), chọn Gradle/Groovy, Java 17+, Spring Boot 3.3.x, dependencies **Spring Web** và **Spring Boot Actuator**.

Trong `build.gradle` do Initializr tạo, khối dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đây chỉ là snippet dependencies, không phải file Gradle đầy đủ. Initializr tạo plugins, BOM/dependency management, repositories và Gradle Wrapper.

Cấu trúc:

```text
src/
  main/
    java/demo/
      SafeHttpObservabilityApplication.java
      SafeRequestMetadataFilter.java
      OrderController.java
    resources/
      application.properties
  test/
    java/demo/
      SafeRequestMetadataFilterTest.java
```

### 7.2. SafeHttpObservabilityApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeHttpObservabilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                SafeHttpObservabilityApplication.class, args);
    }
}
```

Lưu tại `src/main/java/demo/SafeHttpObservabilityApplication.java`. Package `demo` giúp component scanning tìm filter và controller.

### 7.3. SafeRequestMetadataFilter.java

```java
package demo;

import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 20)
public class SafeRequestMetadataFilter
        extends OncePerRequestFilter {

    private static final Logger log =
            LoggerFactory.getLogger(
                    SafeRequestMetadataFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();
        long startNanos = System.nanoTime();

        response.setHeader("X-Request-ID", requestId);

        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("requestId", requestId)) {
            try {
                chain.doFilter(request, response);
            } finally {
                long elapsed = System.nanoTime() - startNanos;
                long durationMs =
                        TimeUnit.NANOSECONDS.toMillis(elapsed);

                Object matched = request.getAttribute(
                    HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);

                // Không fallback sang raw URI.
                String route = matched instanceof String pattern
                        ? pattern : "UNMATCHED";

                String method = normalizeMethod(
                        request.getMethod());

                log.info(
                    "http_request method={} route={} " +
                    "status={} durationMs={} requestId={}",
                    method,
                    route,
                    response.getStatus(),
                    durationMs,
                    requestId);
            }
        }
    }

    private static String normalizeMethod(String method) {
        return switch (method) {
            case "GET", "POST", "PUT", "PATCH",
                 "DELETE", "HEAD", "OPTIONS" -> method;
            default -> "OTHER";
        };
    }
}
```

Lưu tại `src/main/java/demo/SafeRequestMetadataFilter.java`.

**Giải thích:**

- `@Component` cho Spring Boot đăng ký Servlet filter; không cần đăng ký thêm lần nữa qua `FilterRegistrationBean`.
- `OncePerRequestFilter` chạy theo semantics của request dispatch; **không** có nghĩa mọi async request chỉ có một dispatch.
- `UUID.randomUUID()` tạo request ID trên server. Không tin raw header `X-Request-ID` do client tự đặt.
- `response.setHeader("X-Request-ID", requestId)` trả một ID để khách hàng gửi lại khi hỗ trợ.
- `MDC.putCloseable` bảo đảm dọn ThreadLocal khi request thread được tái sử dụng.
- `System.nanoTime()` đo duration monotonic thay vì wall clock.
- `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` lấy route template sau khi MVC match; nếu thiếu, dùng `UNMATCHED`.
- `normalizeMethod` giới hạn method vào tập cố định, tránh string bất thường trong log.
- `response.getStatus()` là status tại **thời điểm filter kết thúc dispatch đồng bộ**, chưa chắc là trạng thái cuối khi còn error/async processing.
- **Không có dòng nào đọc body, cookie, Authorization, query hay raw URI.** Đây là đặc tính cần kiểm tra.

Trong production, nếu chỉ cần latency/error metrics, có thể bỏ filter custom và dùng Micrometer auto-instrumentation. Filter này dành cho học cách ghi metadata log và request ID.

### 7.4. OrderController.java

```java
package demo;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class OrderController {

    public record PlaceOrderRequest(
            String sku,
            int quantity,
            String contactEmail,
            String deliveryNote) {
    }

    public record PlaceOrderResponse(String state) {
    }

    @PostMapping("/api/orders")
    public ResponseEntity<PlaceOrderResponse> create(
            @RequestBody PlaceOrderRequest body) {

        if (body.sku() == null || body.sku().isBlank()
                || body.quantity() <= 0) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Invalid order request");
        }

        // Không log hoặc echo dữ liệu email/note.
        return ResponseEntity.ok(
                new PlaceOrderResponse("received"));
    }

    @GetMapping("/api/orders/{id}")
    public Map<String, String> get(
            @PathVariable("id") String id) {
        // Demo không tiết lộ order của user cụ thể.
        return Map.of("state", "demo");
    }
}
```

Lưu tại `src/main/java/demo/OrderController.java`. Java record có thể được Jackson bind từ JSON; `@RequestBody` đọc body bình thường vì filter không consume. Đừng thêm `log.info("body={}", body)` vì Java record `toString()` sẽ in các fields, gồm email/note. `GET /api/orders/{id}` chỉ là route mẫu; production phải có kiểm tra ownership/tenant và authentication.

### 7.5. application.properties

```properties
server.port=8080
server.address=127.0.0.1

# Spring MVC request details thường mặc định không được log.
spring.mvc.log-request-details=false

# Không tạo access log Tomcat riêng cho lab.
server.tomcat.accesslog.enabled=false

logging.level.org.springframework.web=INFO

# Metrics chỉ xem trên localhost trong lab.
management.endpoints.web.exposure.include=health,metrics
management.endpoint.health.show-details=never

server.error.include-stacktrace=never
server.error.include-message=never
```

Lưu tại `src/main/resources/application.properties`.

`spring.mvc.log-request-details=false` kiểm soát một số logging details ở DEBUG/TRACE trong Spring MVC; nó **không** ngăn custom app loggers, third-party interceptors, NGINX/WAF/CDN hoặc WireTap. `server.tomcat.accesslog.enabled=false` không tắt access log của proxy.

`management.endpoints.web.exposure.include=health,metrics` chỉ phù hợp cho lab bind loopback. Khi mở management endpoint trong production phải có network restrictions/authentication hoặc không expose ra public ingress.

### 7.6. Chạy

Từ thư mục root có Gradle Wrapper:

```bash
./gradlew bootRun
```

PowerShell:

```powershell
.\gradlew.bat bootRun
```

Do cần Spring/Jakarta libraries, các file Java không thể compile độc lập bằng `javac OrderController.java` với classpath mặc định; dùng Gradle Wrapper do Initializr tạo.

### 7.7. POST với dữ liệu hoàn toàn giả

```bash
curl -i -X POST http://127.0.0.1:8080/api/orders \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer DEMO-NOT-A-REAL-TOKEN' \
  --data '{"sku":"BOOK-001","quantity":2,"contactEmail":"fake.user@example.test","deliveryNote":"SYNTHETIC-PRIVATE-NOTE"}'
```

Response tương đương:

```http
HTTP/1.1 200
X-Request-ID: <generated-uuid>
Content-Type: application/json

{"state":"received"}
```

Đây là **format minh họa**, thứ tự headers, reason phrase và UUID thay đổi. Log metadata tương đương:

```text
http_request method=POST route=/api/orders status=200 durationMs=8 requestId=550e8400-e29b-41d4-a716-446655440000
```

8 ms và UUID chỉ minh họa. Filter **không** in `fake.user@example.test`, `SYNTHETIC-PRIVATE-NOTE` hoặc `DEMO-NOT-A-REAL-TOKEN`.

### 7.8. GET path variable và query

```bash
curl -i 'http://127.0.0.1:8080/api/orders/customer-123?token=DEMO-DO-NOT-LOG'
```

Body controller là:

```json
{"state":"demo"}
```

Log có `method=GET route=/api/orders/{id} status=200`, không có `customer-123` hay `DEMO-DO-NOT-LOG`. Dù app không log URI, browser/proxy có thể vẫn thấy URL; đừng dùng query để chuyển token thật.

### 7.9. Windows PowerShell

Dùng `curl.exe`. Với JSON quoting trên PowerShell 5.1, có thể tạo file `order-demo.json` chứa payload giả rồi gửi:

```powershell
curl.exe -i -X POST http://127.0.0.1:8080/api/orders -H "Content-Type: application/json" --data-binary "@order-demo.json"
```

Không lưu secrets thật vào file sample hoặc shell history.

## 8. Kiểm thử tự động bằng MockMvc và CapturedOutput

`spring-boot-starter-test` cung cấp Boot test utilities và `MockMvc`. Tạo `src/test/java/demo/SafeRequestMetadataFilterTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ExtendWith(OutputCaptureExtension.class)
class SafeRequestMetadataFilterTest {

    @Autowired
    MockMvc mvc;

    @Test
    void logsOnlyApprovedMetadata(CapturedOutput output)
            throws Exception {

        String body = """
            {
              "sku":"BOOK-001",
              "quantity":2,
              "contactEmail":"fake.user@example.test",
              "deliveryNote":"SYNTHETIC-PRIVATE-NOTE"
            }
            """;

        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer DEMO-NOT-A-REAL-TOKEN")
                .content(body))
            .andExpect(status().isOk())
            .andExpect(header().exists("X-Request-ID"));

        assertThat(output.getOut())
            .contains("http_request method=POST")
            .contains("route=/api/orders")
            .contains("status=200")
            .doesNotContain("fake.user@example.test")
            .doesNotContain("SYNTHETIC-PRIVATE-NOTE")
            .doesNotContain("DEMO-NOT-A-REAL-TOKEN");
    }

    @Test
    void routePatternHidesPathAndQuery(
            CapturedOutput output) throws Exception {

        mvc.perform(get(
                "/api/orders/customer-123?token=DEMO-QUERY-TOKEN"))
            .andExpect(status().isOk());

        assertThat(output.getOut())
            .contains("route=/api/orders/{id}")
            .doesNotContain("customer-123")
            .doesNotContain("DEMO-QUERY-TOKEN");
    }
}
```

Test 1 xác minh request body vẫn được JSON deserialize, status 200 và request ID hiện diện, nhưng chuỗi nhạy cảm giả không xuất hiện trong log. Test 2 xác minh path variable và query không bị in. Nếu một thư viện khác bật logging raw payload, test có thể fail: đó là regression có giá trị.

**Giới hạn:** test chỉ capture app logs trong test runtime; không kiểm chứng NGINX, WAF, CDN, access log hay APM agent nằm ngoài JVM. Cần review staging/production separately.

Chạy:

```bash
./gradlew test
```

Với Spring Boot 3.3.x và không có middleware ghi raw input, hai test dự kiến pass. Output Gradle không cố định theo version/console mode.

## 9. Micrometer Observation: quan sát hiệu năng không cần body

Spring Boot 3.3 Actuator tích hợp Micrometer cho HTTP server requests, thường có meter:

```text
http.server.requests
```

Các thông tin thường gồm method, route/URI pattern, status/outcome, latency và exception category theo web stack/observation conventions. Dùng metric này thay vì tự log từng request khi mục tiêu chỉ là throughput, error rate, p95/p99 latency hoặc SLO.

Trong demo đã expose `metrics` trên loopback. Sau khi gọi vài request:

```bash
curl -sS http://127.0.0.1:8080/actuator/metrics

curl -sS http://127.0.0.1:8080/actuator/metrics/http.server.requests

curl -sS 'http://127.0.0.1:8080/actuator/metrics/http.server.requests?tag=method:POST'
```

JSON measurements và available tags phụ thuộc runtime/registry/số request. Production cần hạn chế Actuator management endpoint bằng network/RBAC/mTLS hoặc không expose qua public ingress.

### 9.1. Tags cardinality thấp

Nên dùng `method=POST`, `uri=/api/orders`, `status=200`, `service=order-api`, `outcome=SUCCESS`. Không gắn requestId, email, userId, token, query hoặc raw URI vào metric labels vì làm bùng nổ time series.

### 9.2. Metrics khác trace khác log

- Metrics: “bao nhiêu requests chậm/lỗi?”.
- Logs metadata: “request với ID này có status/error category gì?”.
- Traces: “request mất thời gian ở DB, HTTP downstream hay một service nào?”.

Micrometer Tracing/OpenTelemetry giúp propagate trace/span context; sampling có thể khiến một số requests không có trace. Span attributes cũng phải được kiểm soát, không đưa raw body, token hoặc secrets vào tracing. Request ID do server tạo khác session ID và khác access token.

## 10. Error 400, 401, 403 và 500: log category thay vì raw values

Một số error categories:

| Category | Ví dụ | Log đủ dùng |
| --- | --- | --- |
| INVALID_JSON | JSON parse lỗi | route, status, requestId, category |
| VALIDATION_FAILED | `quantity<=0` | field name và constraint code, không rejectedValue |
| UNAUTHENTICATED | Thiếu credentials | route, HTTP 401, auth category |
| FORBIDDEN | Thiếu role/object permission | resource/action type, status |
| DEPENDENCY_TIMEOUT | DB hoặc HTTP downstream quá hạn | dependency/span category, duration |
| INTERNAL_ERROR | Lỗi app chưa phân loại | trace ID, exception class được kiểm soát |

Không `log.warn("errors={}", bindingResult.getAllErrors())` bừa bãi: rejected values có thể chứa email/password/PII. Không log nguyên `exception.getMessage()` khi parser/thư viện có thể đưa JSON fragments hoặc SQL parameters vào error message.

Nếu chỉ biết bug xuất hiện với một giá trị đặc biệt, hãy dựng **synthetic fixture** trong staging và mô tả điều kiện gây lỗi. Không chuyển request của khách hàng vào log production chỉ để tái hiện.

### 10.1. DTO.toString() cũng là body logging

Java record `PlaceOrderRequest` có `toString()` thường in field values. Một dòng:

```java
log.info("request={}", body);
```

có thể vô tình ghi email, note dù không gọi serializer JSON. Đây là **phản ví dụ**. Lombok `@ToString` và entity logging cũng cần kiểm soát tương tự.

## 11. Async Servlet, error dispatch và streaming

`OncePerRequestFilter` hoạt động theo request dispatch, không phải một phép đo trọn đời mọi logical request. Với `DeferredResult`, `Callable`, `StreamingResponseBody` hoặc `SseEmitter`:

- Request thread ban đầu có thể return trước response hoàn tất.
- `isAsyncStarted(request)` có thể true.
- `ASYNC` dispatch có thể chạy trên thread khác.
- `ERROR` dispatch có thể xử lý status sau khi filter ban đầu đã log.
- MDC từ request thread không tự propagate đến executor.
- Dễ log hai lần nếu tham gia cả async/error dispatch mà không quản lý lifecycle.

Vì vậy status/duration của filter demo được trình bày là **thời điểm dispatch đồng bộ**. Đối với production SLO và kết nối dài, dùng Spring Boot Observation theo lifecycle hoặc instrument Servlet async listeners và cleanup đúng. Không xem một `SseEmitter` 30 phút là request 5 ms chỉ vì filter return sớm.

### 11.1. Exceptions xử lý sau filter

Controller ném exception chưa được handle có thể dẫn đến container error dispatch sau lần `finally` đầu. Khi đó filter log `status=200` trong khi browser thấy 500. Không tự kết luận filter có lỗi ghi hoặc client sai; xem lifecycle và dùng observability instrumentation phù hợp.

### 11.2. MDC và thread pools

`MDC` thường dựa trên ThreadLocal. Dùng `MDC.putCloseable`/finally tránh request trước làm bẩn log request sau trên reused thread. Với `@Async`, CompletableFuture hoặc Reactor, cần context propagation/task decorator/tracing chính thức; không tự copy MDC mà quên cleanup.

## 12. WebFlux: WebFilter và DataBuffer khác Servlet

Spring WebFlux dùng `ServerWebExchange`/`WebFilter`, body là `Flux<DataBuffer>`. `OncePerRequestFilter` của Servlet **không** phải cách viết cho reactive WebFlux.

Nếu một `WebFilter` tự `subscribe()` vào `exchange.getRequest().getBody()` chỉ để log:

- Có thể consume stream trước controller;
- Có thể buffering quá nhiều gây memory pressure;
- Netty pooled DataBuffer cần retain/release đúng để tránh leak/double-release;
- Blocking decode/logging có thể chặn event loop;
- Reactor context và MDC không tự đồng nhất với Servlet ThreadLocal.

**Ưu tiên WebFlux HTTP Observation**. Khi phải xử lý payload thật, dùng request decorators, bounded memory, cleanup khi cancel và test stream lifecycle; đừng làm điều đó chỉ vì muốn logging.

Multipart/file upload, gzip/protobuf/binary và SSE/WebSocket messages cũng không phù hợp để log thành một String. Với SSE/WebSocket, theo dõi connection count, event rate, close codes và drops, không ghi nội dung chat/user-specific events.

## 13. Nhiều lớp có thể ghi log request

```text
Client
  |
  v
CDN/WAF           security events, request sampling
  |
  v
Load balancer     access logs
  |
  v
NGINX/Ingress    raw URI/headers nếu cấu hình sai
  |
  v
Spring Boot      filters, MVC, app logs
  |
  v
RestClient       outbound HTTP logging/wiretap
  |
  v
Log collector    stdout/file processing
  |
  v
Central logs     search, export, retention, backup
```

Filter an toàn trong JVM **không xóa được** body/query đã bị WAF, proxy hoặc agent khác ghi. Cần review inbound và outbound HTTP logs, logging levels, proxy access patterns và APM instrumentation.

`spring.mvc.log-request-details=false` hạn chế một số logging details của Spring MVC ở DEBUG/TRACE, nhưng không chặn custom logger. `server.tomcat.accesslog.enabled=false` chỉ áp dụng Tomcat access log, không áp dụng CDN/NGINX/WAF. Đặc biệt tránh `$request_body`/`$http_authorization`/`$http_cookie` trong NGINX log formats và tránh raw prepared SQL parameters trong database diagnostics.

### 13.1. Log platform cũng là hệ thống dữ liệu

Cần encryption-in-transit/at-rest, RBAC, audit người xem/export, retention và quy trình xóa. Hash email đơn thuần không tự làm dữ liệu vô danh: miền giá trị có thể đoán được. Nếu cần pseudonymization, phải đánh giá keyed HMAC/rotating keys và quyền truy cập theo chính sách, thay vì ghi user identity vào mọi metric/log.

## 14. Debug đặc biệt mà không bật full-body logging

Khi metadata chưa đủ, ưu tiên quy trình:

1. Nêu giả thuyết cụ thể: parse error, invalid enum, missing field, downstream timeout hay authorization?
2. Tạo request synthetic tối giản trong staging/local để tái hiện.
3. Thu route, status, error category, field name từ allowlist, requestId và trace.
4. Nếu cần một field đầu vào, xác định schema/field nào được phép, làm categorical bucket/validation code, không in raw value.
5. Chỉ bật diagnostic có phê duyệt, scope hẹp, giới hạn thời gian và số samples, không dùng chung full log sink.
6. Giới hạn payload size, tránh multipart/binary, kiểm thử malformed input, nested JSON, Unicode escaping và log injection.
7. Mã hóa dữ liệu, kiểm soát người xem, audit access, tự động tắt feature flag và xóa theo retention.
8. Nếu lỡ có token/PII vào logs, xử lý như một security/privacy incident, bao gồm hạn chế quyền truy cập và thu hồi secrets khi cần.

Sampling hoặc regex masking không thay căn cứ pháp lý, chính sách nội bộ hoặc đánh giá rủi ro.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `@RequestBody` nhận EOF | Filter đọc input stream trước controller | Không consume body chỉ để logging |
| ContentCachingRequestWrapper trả empty | Chưa có ai đọc body | Đây là semantics của wrapper |
| Cache chỉ có 4 KB đầu | Content cache limit | Không tưởng đó là toàn request; không log |
| Log chứa email/token | DTO.toString, body, header hoặc raw URI | Dùng allowlist metadata |
| Query token vẫn trong access log | Proxy ghi raw request line | Review proxy access log policy |
| Metrics nổ số lượng series | label là requestId/userId/raw path | Low-cardinality tags |
| 404 có route=UNMATCHED | MVC không cung cấp pattern | Fallback cố định, không raw path |
| Filter log 200 nhưng client 500 | Error dispatch xảy ra sau finally | Observation theo lifecycle |
| RequestId bị lẫn | MDC không clear | try-with-resources/finally |
| Async không có MDC | Thread context không propagate | Tracing/context propagation |
| SSE latency quá nhỏ | Đo initial dispatch | Async completion/stream metrics |
| WAF vẫn ghi body | App filter không ảnh hưởng upstream | Review WAF/request sampling |
| Log bị giả dòng ERROR | Raw string newline/log injection | Không log raw input, structured escaping |
| Multipart log gây tăng heap | Buffer/copy file upload | Metadata only, upload limits |
| Debug mask sót field mới | Regex denylist | Schema allowlist, regression tests |
| Metrics bị expose Internet | Actuator mở trên public port | Private management/RBAC/network |

## 16. Bài tập ôn luyện

**1.** Có thể bật DEBUG để log `POST /login` body tạm thời không?  
**Đáp án:** Không mặc định. Mật khẩu vẫn có thể bị lưu vào log/backup; dùng status/category/trace và fixture giả.

**2.** Log raw `/users/alice@example.test?token=abc` có an toàn nếu không log body?  
**Đáp án:** Không. Path/query chứa email/token. Dùng route template và không ghi query.

**3.** `ContentCachingRequestWrapper` có tự đọc body không?  
**Đáp án:** Không, nó chỉ cache bytes downstream đã đọc; có thể rỗng hoặc partial.

**4.** Giới hạn cache 1024 bytes có bảo đảm không lộ secrets?  
**Đáp án:** Không. Secrets có thể nằm trong bytes đầu.

**5.** Vì sao không thêm requestId thành Micrometer tag?  
**Đáp án:** UUID gần như duy nhất tạo high cardinality time series.

**6.** `BEST_MATCHING_PATTERN_ATTRIBUTE` luôn hiện diện không?  
**Đáp án:** Không; khi thiếu dùng nhãn cố định, không raw URI.

**7.** `System.nanoTime()` có ưu điểm gì so với `currentTimeMillis()` cho latency?  
**Đáp án:** Nó là đồng hồ monotonic phù hợp đo khoảng thời gian.

**8.** Vì sao filter có thể thấy 200 còn browser nhận 500?  
**Đáp án:** Error dispatch/status có thể được cập nhật sau khi filter ban đầu hoàn thành.

**9.** `BindingResult.getAllErrors()` có nguy cơ gì khi log?  
**Đáp án:** Có thể chứa rejected values như password/email; ghi field/constraint codes đã được phép.

**10.** `spring.mvc.log-request-details=false` có chặn log tại CDN không?  
**Đáp án:** Không. Cấu hình Spring MVC không điều khiển log của CDN/WAF/NGINX.

**11.** Dùng `@Async` có đảm bảo MDC tự propagate sang thread khác không?  
**Đáp án:** Không; cần context propagation và cleanup phù hợp.

**12.** Cần điều tra một request fail theo nhiều services, ưu tiên gì?  
**Đáp án:** Request/trace ID, route/status/error category và distributed spans; không cần raw body.

## 17. Checklist production

- [ ] Không log request/response bodies, Authorization, Cookie, session IDs hoặc credentials theo mặc định.
- [ ] Raw URL/query và user-provided headers không được coi là metadata an toàn tự động.
- [ ] Chỉ ghi allowlisted method, route template, status, duration, error category và correlation IDs.
- [ ] Route được lấy từ HandlerMapping pattern hoặc framework conventions; thiếu thì dùng nhãn cố định.
- [ ] Filter không đọc input stream/reader chỉ để logging.
- [ ] Không dùng ContentCachingRequestWrapper như cơ chế redaction hoặc cắt body để log.
- [ ] DTO.toString, validation errors và exception messages không in rejected values.
- [ ] Request ID được tạo/validate ở trust boundary, không tái dùng raw token.
- [ ] MDC dọn đúng vòng đời và async/reactive contexts được instrument riêng.
- [ ] Micrometer metrics dùng route/method/status cardinality thấp, không userId/requestId labels.
- [ ] `spring.mvc.log-request-details=false` và mọi DEBUG/TRACE/wiretap đã được review.
- [ ] Access log Tomcat/NGINX/CDN/WAF và HTTP client outbound logs được kiểm tra.
- [ ] Unit tests gửi data giả và assert body, token, path variable, query không xuất hiện.
- [ ] Actuator/log platform có RBAC, network restrictions, encryption, audit và retention.
- [ ] Có quy trình debug ngoại lệ scope hẹp, có thời hạn và dữ liệu synthetic.
- [ ] Có security incident process nếu token/PII đã lọt vào log.

## 18. Tài liệu tham khảo

1. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
2. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
3. [Spring Framework 6.1 — ContentCachingRequestWrapper Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/util/ContentCachingRequestWrapper.html)
4. [Spring Framework 6.1 — OncePerRequestFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html)
5. [Spring Framework 6.1 — HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/HandlerMapping.html)
6. [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
7. [Spring Boot 3.3 — Actuator Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
8. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
9. [Spring Boot 3.3 — Embedded Web Server Access Logging](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html)
10. [Micrometer — Observation Concepts](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
11. [OpenTelemetry — HTTP Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/http/)
12. [Spring Framework — MVC Async Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)

**Kết luận:** Không phải log càng nhiều thì quan sát càng tốt. **Method, route template, status, latency, request/trace ID và error category đã kiểm soát** giải quyết phần lớn câu hỏi vận hành. Mặc định **không đọc và không ghi body**, đồng thời kiểm soát raw URL/headers và các tầng proxy, giúp ứng dụng vẫn quan sát được mà không tạo thêm kho dữ liệu nhạy cảm.
