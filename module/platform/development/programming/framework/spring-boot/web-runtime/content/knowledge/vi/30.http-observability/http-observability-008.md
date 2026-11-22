# Che Authorization, cookie, dữ liệu cá nhân và nội dung nhạy cảm khi quan sát HTTP trong Spring Boot

## 1. Mục tiêu và tình huống thực tế

Quan sát HTTP giúp trả lời “dịch vụ nào chậm?”, “request thất bại ở đâu?”, “bao nhiêu lỗi 401/500?” và “lần triển khai này có làm tỷ lệ lỗi tăng không?”. Nhưng log, trace, metric, access log và Actuator cũng là **một kênh có thể làm rò rỉ dữ liệu**. Một dòng tưởng như vô hại có thể chứa bearer token, session cookie, mã xác thực, email, số điện thoại, địa chỉ giao hàng, dữ liệu thanh toán, hồ sơ cá nhân hoặc đường dẫn tới tài liệu riêng tư.

Ví dụ yêu cầu (chỉ dùng dữ liệu giả):

```http
GET /api/orders/customer-42?access_token=TEST_TOKEN_DO_NOT_USE HTTP/1.1
Host: api.example.test
Authorization: Bearer TEST_ACCESS_TOKEN
Cookie: SESSION=TEST_SESSION_ID; preference=dark
Referer: https://app.example.test/reset?code=TEST_RESET_CODE
X-Request-Id: TEST_USER_CONTROLLED_ID
```

**Sai** khi log toàn bộ request:

```text
GET /api/orders/customer-42?access_token=TEST_TOKEN_DO_NOT_USE
Authorization: Bearer TEST_ACCESS_TOKEN
Cookie: SESSION=TEST_SESSION_ID; preference=dark
```

**Tốt hơn**, nếu việc vận hành chỉ cần đường xử lý và thời gian:

```text
http_exchange method=GET route=/api/orders/{id} status=200 durationMs=18
```

Dòng thứ hai đủ cho việc phân tích throughput/latency theo route mà không lưu giá trị từ `Authorization`, `Cookie`, path variable hay query string. Nếu cần phân tích request nào thuộc cùng một trace, hãy dùng trace/correlation ID được tạo hoặc xác minh theo chính sách; **không sử dụng token hay session ID làm correlation key**.

Bài này áp dụng cho **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+**, các hệ thống Spring MVC, WebFlux và HTTP clients. Ví dụ chạy được dùng Java 21/Gradle/Spring Boot 3.3.13. Trọng tâm là **ngăn dữ liệu nhạy cảm đi vào hệ thống quan sát**; regex thay chuỗi sau khi sự kiện đã gửi đi chỉ là lớp phòng thủ phụ, không phải thiết kế an toàn chính.

## 2. Bốn nguyên tắc: tối thiểu hóa, cho phép theo danh sách, che trước khi ghi, và kiểm thử

Một chính sách quan sát HTTP an toàn bắt đầu từ những câu hỏi:

1. **Có thực sự cần dữ liệu này không?** Nếu chỉ cần đếm lỗi theo HTTP status thì không cần đọc request body, query string, cookies hoặc `Authorization`.
2. **Dữ liệu nào được phép xuất hiện?** Dùng danh sách được cho phép (allowlist) cho các fields của log/trace/metric, không dựa hoàn toàn vào danh sách tên nhạy cảm (denylist) luôn có thể thiếu.
3. **Che ở đâu?** Che hoặc loại bỏ **trước khi ghi vào appender/exporter/collector**, không chờ người đọc dashboard tự giấu giá trị.
4. **Làm sao chứng minh?** Dùng request với các canary giả có tên dễ nhận biết; kiểm tra logs, tracing backend, metrics labels, access log, Actuator và responses rằng các canaries không xuất hiện.

Định nghĩa mức xử lý:

| Cách xử lý | Mô tả | Ví dụ |
| --- | --- | --- |
| **Không thu thập** | Không truy cập hoặc đưa field vào telemetry | Không log `Authorization`, `Cookie`, body |
| **Thay giá trị** | Giữ tên field nếu cần audit cấu trúc, thay dữ liệu | `authorization=[REDACTED]` |
| **Phân loại** | Chuyển sang category hữu hạn | `auth_scheme=bearer`, `payload_type=json` |
| **Ẩn một phần** | Chỉ lộ phần rất hạn chế theo policy | Không phù hợp với access token/password; chỉ cân nhắc với dữ liệu ít nhạy cảm đã được duyệt |
| **Pseudonymization** | Tạo định danh thay thế có kiểm soát | HMAC của business ID khi thực sự cần correlating |
| **Mã hóa hạn chế truy cập** | Dữ liệu vẫn có thể khôi phục bởi người có khóa | Chỉ trong hệ thống audit đặc biệt có căn cứ pháp lý/kiểm soát quyền |

**Quan trọng:** “Mask” không nhất thiết phải giữ bốn chữ số cuối. Với bearer token, refresh token, password, session cookie, private key và one-time code, tốt nhất **không ghi bất kỳ phần nào**. Phần giá trị còn lại có thể tạo bề mặt tấn công hoặc trợ giúp correlation không được phép.

## 3. Phân loại dữ liệu HTTP trước khi bật logging

| Nguồn dữ liệu | Ví dụ | Rủi ro | Chính sách gợi ý |
| --- | --- | --- | --- |
| Header xác thực | `Authorization`, `Proxy-Authorization` | Chiếm quyền sử dụng API/session | Không log giá trị |
| Header cookie | `Cookie`, `Set-Cookie` | Lộ session, CSRF, remember-me token | Không log giá trị |
| API keys tùy biến | `X-API-Key`, `X-Auth-Token` | Truy cập hệ thống trái phép | Không log giá trị |
| Query parameters | `token`, `code`, `password`, `email`, `phone` | Lộ bí mật/PII qua URL | Không log raw query; ưu tiên route |
| Path variables | `/users/{email}`, `/orders/{id}` | Có thể định danh người/công việc | Log **route pattern**, không log path instance |
| Request body | Password, thông tin cá nhân, JSON lồng nhau | Dữ liệu nhạy cảm tùy nghiệp vụ | Không log body mặc định |
| Response body | Hồ sơ, đơn hàng, thông tin sức khỏe | Lộ dữ liệu mà API được bảo vệ | Không log body mặc định |
| `Referer` | URL chuyển đến có token hoặc query | Rò dữ liệu từ màn hình khác | Không log raw value |
| `User-Agent` | Có thể đóng góp fingerprint | Theo dõi/nhận dạng, cardinality lớn | Chỉ lưu category nếu được duyệt |
| IP và geo | `remoteAddr`, `X-Forwarded-For` | Dữ liệu cá nhân trong nhiều bối cảnh; spoofing | Giới hạn mục đích, nguồn đáng tin và retention |
| Session/principal | Session ID, username, subject ID | Liên kết hoạt động của cá nhân | Không log session ID; dùng pseudonym chỉ khi cần |
| HTTP method/status | `GET`, `POST`, `200`, `403` | Thường thấp | Phù hợp cho telemetry |
| Route template | `/api/orders/{id}` | Ít lộ hơn raw path | Tốt cho logging, metrics |
| Duration / outcome | `durationMs=18`, `outcome=SUCCESS` | Thường thấp | Phù hợp cho telemetry |

Một field không có tên “password” vẫn có thể chứa bí mật. `payload`, `metadata`, `debug`, `data`, `description`, `comment`, `state`, `assertion` hoặc một URL trong `Location`/`Referer` cũng có thể mang token. **Danh sách tên nhạy cảm là lớp phụ, không phải bảo đảm.**

Phân loại phải được cập nhật khi thêm endpoint mới, thay nhà cung cấp identity, thay gateway, hoặc chuyển sang GraphQL/SSE/WebSocket.

## 4. Vì sao `Authorization` không bao giờ được đưa vào log thông thường?

`Authorization` có thể mang:

```http
Authorization: Bearer eyJ... (token giả)
Authorization: Basic dGVzdDp0ZXN0 (thông tin giả)
Authorization: Digest ...
```

Bearer token thường là **credential có thể sử dụng trực tiếp**: người cầm token có thể được phép gọi API trong phạm vi/thời hạn của token mà không cần biết mật khẩu. Với Basic Authentication, nội dung là encoding, không phải mã hóa bí mật. **Không log toàn bộ token, không log base64, không log JWT payload, không log chữ ký hoặc một prefix dài.**

Ngay cả khi JWT “chỉ là ba đoạn text”, phần payload có thể chứa claims cá nhân; còn token đầy đủ có thể bị replay. `log.debug("token={}", token)` là lỗi nghiêm trọng dù logger ở DEBUG vì config có thể thay đổi lúc production incident.

Thay vì:

```java
// Không làm:
log.info("request Authorization={}",
        request.getHeader("Authorization"));
```

Nếu **thực sự** cần biết loại cơ chế auth, ghi giá trị hữu hạn do ứng dụng tin cậy xác định:

```text
auth_mechanism=oauth2
auth_result=authenticated
auth_failure_reason=expired
```

Lấy `auth_mechanism` từ cấu hình/security result thích hợp, không tự echo nguyên giá trị header. Với lỗi 401, thường chỉ cần route template, outcome, error category và correlation ID. Một failure message như `"Invalid token: <giá trị>"` cũng có thể làm rò token qua exception/log.

## 5. Cookie và `Set-Cookie` còn dễ bị bỏ sót hơn

Browser gửi `Cookie`, server trả `Set-Cookie`:

```http
Cookie: SESSION=DEMO_SESSION; rememberMe=DEMO_REMEMBER; theme=dark
Set-Cookie: SESSION=NEW_DEMO_SESSION; HttpOnly; Secure; SameSite=Lax
```

`SESSION`, `JSESSIONID`, refresh/session cookies và CSRF-related cookies có thể được dùng để theo dõi hoặc tái sử dụng phiên. Không log nguyên **cả header** chỉ vì một cookie trong đó có vẻ vô hại như `theme=dark`.

Không dựa vào việc tách cookies bằng dấu `;` rồi chỉ che những tên biết trước: ứng dụng có thể thêm cookie mới, giá trị có thể URL-encode hoặc chứa cấu trúc phức tạp. Chính sách an toàn cho quan sát chung là **không log giá trị `Cookie` và `Set-Cookie`**.

Không bật:

```text
Cookie=SESSION=...
Set-Cookie=...
```

chỉ để debug logout/SSO. Thay bằng event đã cấu trúc:

```text
session_event=CREATED auth_method=oidc outcome=SUCCESS
session_event=REVOKED reason=LOGOUT outcome=SUCCESS
```

Nếu cần correlating một vòng đời session cho security audit, hãy thiết kế một định danh phụ không sử dụng trực tiếp session credential. Theo OWASP, session IDs không nên được ghi thô vào logs. Ngay cả “hash session ID” cũng cần đánh giá khả năng liên kết danh tính, chính sách khóa và retention.

## 6. Dữ liệu cá nhân nằm trong path, query và `Referer`, không chỉ trong body

Một URL có thể chứa dữ liệu riêng tư:

```text
/api/users/alice@example.test
/api/orders/customer-42
/reset?code=DEMO_ONE_TIME_CODE
/callback?code=DEMO_OAUTH_CODE&state=DEMO_STATE
/search?q=benh-an-nhay-cam
/download?signature=DEMO_SIGNED_URL
```

Nhiều access logs in **request line đầy đủ** (method, path, query) hoặc `Referer`. Do đó việc không log header/body **chưa đủ**.

Ưu tiên:

```text
method=GET route=/api/users/{email} status=200
method=GET route=/reset status=302
method=GET route=/download status=200
```

trong đó route lấy từ **handler mapping do server định nghĩa**, không phải raw request path do client gửi.

Lưu ý:

- `request.getRequestURI()` **không có query string**, nhưng vẫn có thể chứa email, phone, account ID trong **path**.
- `request.getQueryString()` chứa các giá trị tự do, thường đặc biệt nguy hiểm.
- `request.getRequestURL()` trả URL với path thực, không phải route template.
- HTTP client `URI.toString()`, `HttpRequest.getURI()` và exception từ client library có thể chứa signed URLs và query tokens.
- `Referer` có thể chứa URL của trang trước đó với các tham số nhạy cảm.
- Response `Location` trên redirect cũng có thể chứa authorization code, nonce hoặc identifier.

Với route không được Spring MVC match, dùng nhãn cố định như `UNMAPPED` hoặc `OTHER`, **không fallback sang raw URI** khi cần log. Với file server hoặc wildcard routes, cân nhắc ghi một category logic (`STATIC_RESOURCE`) thay vì raw path.

## 7. Request và response body: nguồn nhạy cảm khó che nhất

Body có thể là JSON, form-urlencoded, XML, multipart, protobuf, GraphQL variables, binary file hoặc một stream SSE. Mỗi kiểu dữ liệu có những rủi ro riêng:

| Loại body | Dữ liệu có thể bị lộ |
| --- | --- |
| `application/json` | `password`, email, phone, customerId, hồ sơ, dữ liệu lồng nhau |
| `application/x-www-form-urlencoded` | Mật khẩu, OTP, callback code, thông tin form |
| `multipart/form-data` | File cá nhân, tài liệu định danh, ảnh, metadata |
| GraphQL | Variables, query literals, customer fields, lỗi nested |
| XML/SOAP | Credentials, identifiers, dữ liệu y tế/thanh toán |
| Binary/protobuf | Payload không đọc được nhưng vẫn chứa dữ liệu nhạy cảm |
| Response JSON | User profile, auth token, refresh token, danh sách đơn hàng |
| SSE/WebSocket | Tin nhắn, realtime payload, thông tin cá nhân theo phiên |

Trong Spring MVC, wrapper như `ContentCachingRequestWrapper`/`ContentCachingResponseWrapper` có thể cache body bytes để log. Chúng hữu ích trong các use cases kỹ thuật có kiểm soát nhưng **không tự sanitize**. Cache body còn thêm footprint bộ nhớ và nguy cơ giữ dữ liệu nhạy cảm trong heap. Với response wrapper, triển khai sai còn có thể quên copy response body cho client.

Không bật global body logging để debug một endpoint lỗi. Nếu cần điều tra dữ liệu thực sự, dùng **một kênh diagnostic riêng** với quyền chấp thuận, giới hạn mục đích, mã hóa, sampling, retention ngắn và redaction đã kiểm thử; ưu tiên **synthetic test data** trước.

Đừng ngây thơ cho rằng regex `"password":"..."` có thể bắt mọi secrets: JSON nested, escaped quotes, encoding, key aliases, arrays, compressed bodies, multipart và những fields không đặt tên rõ khiến regex bỏ sót.

## 8. Mô hình quan sát HTTP: mỗi tầng có thể làm lộ dữ liệu

```text
Client
  |
  +-- Browser devtools / client SDK debug logs
  v
CDN / WAF / Load Balancer / API Gateway
  |       access logs, request mirroring, security event dumps
  v
Embedded Tomcat / Reactor Netty / HTTP wire logging
  |       request line, headers, bytes
  v
Servlet Filter / WebFlux WebFilter / Spring Security
  |       logs, exceptions, auth failure reports
  v
Controller / service / outbound HTTP client
  |       domain events, request/response debugging
  v
Micrometer Observation / Tracing / Actuator
  |       spans, tags, HTTP exchanges, env/configprops
  v
Agent / Collector / message queue / log platform
  |       transport and storage copies, indexes, retention
  v
Dashboards / alerts / exports / support tickets
```

**Che log trong một Spring filter không bảo vệ được các bản sao đã được tạo tại gateway, web server access log, agent wiretap hoặc collector.** Cần inventory đầy đủ các điểm ghi và ai có thể bật lại DEBUG/TRACE.

Ưu tiên thực hiện chính sách **tại nguồn phát telemetry**. Collector-side redaction là defense-in-depth, không hợp lệ khi secret đã tới một sink hoặc network hop không được phép.

## 9. Chọn metadata đủ hữu ích nhưng không vượt mục đích

Một log HTTP được khuyến nghị cho nhu cầu SRE thông thường:

```json
{
  "event": "http_exchange",
  "method": "GET",
  "route": "/api/orders/{id}",
  "status": 200,
  "duration_ms": 18,
  "service": "orders-api",
  "trace_id": "synthetic_trace_id"
}
```

Chú thích: JSON trên là **minh họa định dạng**, không phải output tự động mặc định của Spring Boot. `trace_id` cần lấy qua tracing pipeline đáng tin, không lấy raw bearer token hay session cookie.

Các trường nên cân nhắc:

- `event` là một tên category hữu hạn.
- `method` là HTTP method đã phân loại.
- `route` là template do application định nghĩa.
- `status` và `duration_ms` đo hiệu năng.
- `service`/`environment` là metadata deployment đã kiểm soát.
- `trace_id` để liên kết logs/traces theo policy.
- `error_code` là mã lỗi hữu hạn do hệ thống kiểm soát, **không** là exception message raw.
- `downstream_service` là tên logic không nhúng full URI/credentials.

Dữ liệu không nên đưa vào telemetry mặc định: `Authorization`, cookies, raw path, raw query, raw body, raw headers, signed URL, GraphQL variables, SQL literals, user profile, số thẻ, tên file người dùng, bí mật từ config và raw error dumps.

Một log chứa ít thông tin hơn có thể **hữu ích hơn** vì dễ tổng hợp, search và chia sẻ trong đúng phạm vi vận hành.

## 10. Demo Spring Boot 3.3: ghi access metadata an toàn bằng route template

Ví dụ dùng Java 21, Spring Boot 3.3.13 và Gradle. Ứng dụng có một endpoint `/api/orders/{id}`, nhưng filter chỉ log **route pattern**; không đọc path variable, query, headers hoặc body.

Cấu trúc project:

```text
build.gradle
src/main/java/com/example/safelog/
    SafeLogApplication.java
    OrderController.java
    SafeHttpAccessLogFilter.java
src/main/resources/application.properties
src/test/java/com/example/safelog/SafeHttpAccessLogFilterTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/java/com/example/safelog/SafeLogApplication.java`:**

```java
package com.example.safelog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeLogApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeLogApplication.class, args);
    }
}
```

**`src/main/java/com/example/safelog/OrderController.java`:**

```java
package com.example.safelog;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @GetMapping("/api/orders/{id}")
    public String readOrder(@PathVariable("id") String ignoredId) {
        // Bài học về observability; không dùng ID cho xử lý dữ liệu.
        return "order-ok";
    }
}
```

Controller trả body cố định để test. Trong production, route này phải được bảo vệ bằng Spring Security và phân quyền theo order/user/tenant. Đừng diễn giải code demo không có authentication là production sample an toàn.

## 11. `SafeHttpAccessLogFilter`: chỉ lấy method, template, status, duration

**`src/main/java/com/example/safelog/SafeHttpAccessLogFilter.java`:**

```java
package com.example.safelog;

import java.io.IOException;
import java.util.Set;
import java.util.concurrent.TimeUnit;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

@Component
public class SafeHttpAccessLogFilter extends OncePerRequestFilter {

    private static final Logger LOG =
            LoggerFactory.getLogger(SafeHttpAccessLogFilter.class);

    private static final Set<String> KNOWN_METHODS = Set.of(
            "GET", "HEAD", "POST", "PUT",
            "PATCH", "DELETE", "OPTIONS");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        long startNanos = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            Object mapped = request.getAttribute(
                    HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);

            String route = mapped instanceof String template
                    ? template
                    : "UNMAPPED";

            String method = request.getMethod();
            if (!KNOWN_METHODS.contains(method)) {
                method = "OTHER";
            }

            long durationMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startNanos);

            LOG.info(
                    "http_exchange method={} route={} status={} durationMs={}",
                    method, route, response.getStatus(), durationMs);
        }
    }
}
```

**Vì sao filter này an toàn hơn việc in request toàn bộ?**

- `request.getHeader("Authorization")`, `getCookies()`, `getQueryString()`, `getRequestURI()` và `getInputStream()` **không được gọi**.
- `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` đến từ Spring MVC route matching. Ví dụ `/api/orders/customer-42` được thể hiện dưới dạng `/api/orders/{id}`.
- Nếu request không match một handler, route thành `UNMAPPED` — không lộ raw path.
- Method chỉ được ghi nếu nằm trong tập chuẩn do code cho phép; không echo HTTP method lạ do client gửi.
- Status là số nguyên, thời lượng là số đo không nhạy cảm theo mục đích demo.
- Format string là literal cố định, không chứa user-supplied text nên giảm nguy cơ log forging/CRLF injection.

**Ranh giới ví dụ:** `OncePerRequestFilter` trong đoạn này phù hợp để minh họa **request đồng bộ**. Với async Servlet, SSE/streaming hoặc exception được container xử lý sau khi filter chain quay về, `finally` có thể chạy trước response hoàn tất; status/duration lúc ấy chưa phản ánh toàn bộ vòng đời request. Trong production dùng Spring HTTP observations đã cấu hình an toàn, hoặc servlet async listener/instrumentation có hiểu async lifecycle. **Không quảng bá filter này là công cụ đo latency tổng đúng cho mọi stream**.

Một route pattern do app tự định nghĩa không tự bảo đảm vô hại nếu developer cố nhúng thông tin nhạy cảm vào literal path, hoặc custom handler mapping trả một pattern có dữ liệu người dùng. Cần review router conventions khi đưa vào production.

## 12. Cấu hình mẫu: chỉ mở Actuator tối thiểu

**`src/main/resources/application.properties`:**

```properties
server.address=127.0.0.1
server.port=8080

# Không bật access log raw của Tomcat cho demo.
server.tomcat.accesslog.enabled=false

# Không bật request/header/body debug logging.
logging.level.org.springframework.web=INFO
logging.level.org.springframework.security=INFO

# Actuator: chỉ công khai health trong môi trường demo.
management.endpoints.web.exposure.include=health

# Giữ các giá trị config/env luôn bị che nếu endpoint được mở.
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never

# Không đưa dữ liệu ứng dụng vào error response.
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-stacktrace=never
```

`server.address=127.0.0.1` cho demo chỉ nghe loopback. Khi triển khai thật, vẫn cần network boundary, authn/authz và TLS phù hợp. Không sử dụng cấu hình này làm “bảo mật đầy đủ” cho API.

`management.endpoint.env.show-values=never` và `configprops.show-values=never` là các tùy chọn **của Actuator Spring Boot 3.3**; endpoint khác, custom endpoint, log/trace khác không tự được bảo vệ bởi hai property này.

**Không dùng:**

```properties
management.endpoints.web.exposure.include=*
management.endpoint.env.show-values=always
```

cho một service có thể tiếp cận từ Internet. Việc Actuator chỉ expose `health` theo mẫu là defense-in-depth; Spring Security/access control vẫn cần khi expose nhiều endpoints nội bộ.

Chạy ứng dụng qua Gradle Wrapper:

```bash
./gradlew bootRun
```

Thử bằng curl:

```bash
curl -i \
  -H 'Authorization: Bearer DEMO_ACCESS_CANARY' \
  -H 'Cookie: SESSION=DEMO_COOKIE_CANARY' \
  'http://127.0.0.1:8080/api/orders/DEMO_PRIVATE_ID?code=DEMO_CODE_CANARY'
```

Response body dự kiến **chính xác**:

```text
order-ok
```

Log do **SafeHttpAccessLogFilter** tạo sẽ có dạng:

```text
http_exchange method=GET route=/api/orders/{id} status=200 durationMs=...
```

`durationMs` phụ thuộc runtime và không có stdout byte-exact. **Không** được xuất hiện `DEMO_ACCESS_CANARY`, `DEMO_COOKIE_CANARY`, `DEMO_PRIVATE_ID` hay `DEMO_CODE_CANARY` trong **dòng của filter**.

## 13. Kiểm thử canary bằng MockMvc và `OutputCaptureExtension`

Dù người lập trình tin rằng không log header, một thay đổi tưởng nhỏ như `log.debug("request={}", request)` có thể làm rò secret sau này. Hãy duy trì regression test sử dụng **synthetic sentinels**.

**`src/test/java/com/example/safelog/SafeHttpAccessLogFilterTest.java`:**

```java
package com.example.safelog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ExtendWith(OutputCaptureExtension.class)
class SafeHttpAccessLogFilterTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void doesNotLogSensitivePathQueryOrHeaders(
            CapturedOutput output) throws Exception {

        mvc.perform(get("/api/orders/PRIVATE_ORDER_CANARY")
                        .header("Authorization", "Bearer AUTH_CANARY")
                        .header("Cookie", "SESSION=COOKIE_CANARY")
                        .param("access_token", "QUERY_CANARY")
                        .param("email", "PII_CANARY"))
                .andExpect(status().isOk())
                .andExpect(content().string("order-ok"));

        String recorded = output.getOut() + output.getErr();

        assertThat(recorded)
                .contains("route=/api/orders/{id}")
                .doesNotContain("PRIVATE_ORDER_CANARY")
                .doesNotContain("AUTH_CANARY")
                .doesNotContain("COOKIE_CANARY")
                .doesNotContain("QUERY_CANARY")
                .doesNotContain("PII_CANARY");
    }
}
```

Chạy:

```bash
./gradlew test
```

Test kiểm tra **log console được capture trong Spring Boot test**, không chứng minh CDN, NGINX, reverse proxy hay external tracing backend an toàn. Tùy hệ thống logback/appender, cần viết thêm test **trực tiếp với ListAppender của logger** hoặc integration test end-to-end để đo đúng sink.

Không dùng **token hoặc dữ liệu cá nhân thật** làm test fixtures. Nên dùng canary đủ khác biệt, đặt tên thể hiện **loại rủi ro**, và không đưa canary vào text của `log.info` hay test reporting nếu test pass.

Nếu thêm controller/log khác mà ghi raw request, test này có thể phát hiện khi output được capture đúng. Nhưng một exporter chạy ngoài process không nhất thiết xuất hiện trong captured stdout; kiểm thử trên từng sink là bắt buộc.

## 14. Một bài kiểm tra Java 17 độc lập về chính sách header

Ví dụ tự chạy không cần Spring, minh họa nguyên tắc **không phản chiếu bất kỳ header value nào**. Khi cần biết header có thuộc nhóm sensitive, chỉ phân loại tên:

**`HeaderPolicyDemo.java`:**

```java
import java.util.Locale;
import java.util.Set;

public class HeaderPolicyDemo {
    private static final Set<String> SENSITIVE = Set.of(
            "authorization",
            "proxy-authorization",
            "cookie",
            "set-cookie",
            "x-api-key",
            "x-auth-token");

    public static String display(String name, String value) {
        String normalized = name.toLowerCase(Locale.ROOT);
        if (SENSITIVE.contains(normalized)) {
            return "[REDACTED]";
        }
        return "[OMITTED]";
    }

    public static void main(String[] args) {
        System.out.println(display(
                "AUTHORIZATION", "Bearer DEMO_SECRET"));
        System.out.println(display(
                "Set-Cookie", "SESSION=DEMO_ID"));
        System.out.println(display(
                "Referer", "https://example.test/?code=DEMO_CODE"));
    }
}
```

Biên dịch và chạy:

```bash
javac HeaderPolicyDemo.java
java HeaderPolicyDemo
```

**Stdout chính xác:**

```text
[REDACTED]
[REDACTED]
[OMITTED]
```

Phương pháp cố ý **không log cả “header được cho là bình thường”**. `Referer` bị loại bỏ dù không có trong danh sách SENSITIVE, vì một URL có thể chứa dữ liệu nhạy cảm. Tham số `value` tồn tại để minh họa signature của API, nhưng method không sử dụng nó: trong ứng dụng thật nên **tránh đọc value ngay từ đầu** khi chỉ cần status/route.

Đừng mở rộng snippet thành danh sách đen chứa vài header names rồi ghi nguyên mọi header còn lại. Những headers custom, tracing baggage hoặc cookie aliases mới có thể mang secrets không thể dự đoán trước.

## 15. `CommonsRequestLoggingFilter`: một cấu hình tưởng an toàn vẫn có thể lộ path

Spring Framework có `CommonsRequestLoggingFilter`, thường được bật để xem requests. Các tùy chọn gồm include query string, headers, payload và độ dài payload. Một số ví dụ trên Internet dùng:

```java
// Không áp dụng cho production nếu chưa đánh giá dữ liệu thực tế:
CommonsRequestLoggingFilter filter =
        new CommonsRequestLoggingFilter();
filter.setIncludeQueryString(true);
filter.setIncludeHeaders(true);
filter.setIncludePayload(true);
```

Cấu hình này có thể đưa query secrets, cookies và body vào logs. Đặt `setMaxPayloadLength(1024)` **không đồng nghĩa đã che secrets**; token nằm ở 200 bytes đầu vẫn có thể bị lộ.

Ngay cả khi đặt cả ba `include...` thành `false`, filter vẫn có thể ghi **request URI chứa PII trong path**. Vì vậy các endpoints có path variables nhạy cảm nên ưu tiên **route-template logging** như ví dụ trước, thay vì chỉ tắt headers/body trong filter.

Nếu thư viện có khả năng chọn các header được phép ghi, vẫn phải xác minh version, trust policy, encoding và custom headers; cách an toàn nhất cho HTTP access summary thường là **không cần header values**.

Đừng chỉ kiểm tra `application.properties`: một `CommonsRequestLoggingFilter` bean hoặc FilterRegistrationBean do thư viện nội bộ đăng ký cũng có thể ghi dữ liệu khi logger level được bật.

## 16. Tomcat access log: request line và query có thể lộ bí mật

Spring Boot MVC thường dùng embedded Tomcat. Có cấu hình access log riêng:

```properties
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.pattern=common
```

Trong nhiều servlet containers, “common” access log format có request line, tức có thể ghi URL/path/query chứa dữ liệu nhạy cảm. **Không bật một pattern có `%r`, `%q` hoặc `%U` mà chưa kiểm tra nội dung và quy tắc bảo vệ PII.** Ngay cả `%U` (URI path) cũng có thể chứa email/account ID trong dynamic segments.

Nếu yêu cầu vận hành chỉ cần phương thức và HTTP status, một pattern rất hạn chế có thể dùng làm **bước phòng thủ**:

```properties
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.pattern=%m %s
```

Pattern trên minh họa log HTTP method và response status; **không có route template** vì Tomcat access logger hoạt động ở tầng container, trước/sau MVC routing theo cách riêng. Không thay thế các HTTP metrics và log từ `HandlerMapping` đã được chuẩn hóa.

Trong môi trường cần forensic access log (IP, URL) theo yêu cầu hợp pháp/vận hành, phải thiết kế phân vùng và policy riêng, thay vì vô tình thu tất cả thông tin rồi cho mọi nhân viên đọc. Kiểm tra pattern thực tế ở startup, access log output directory và quyền file/container volume.

**Lưu ý:** `server.tomcat.accesslog.enabled=false` chỉ tắt Tomcat access logger do Boot cấu hình; NGINX/CDN/load balancer ở ngoài vẫn có access logs của riêng chúng.

## 17. Reactor Netty, WebFlux và HTTP wiretap: không bật bừa trong production

Spring WebFlux có thể chạy trên Reactor Netty. `wiretap`/HTTP client debug có thể quan sát network channel và tùy chế độ hiển thị **headers/body bytes**. Việc bật chúng để tìm một lỗi TLS/HTTP không nên diễn ra trên traffic thật không được kiểm soát.

Các nguồn có thể tạo logs:

- Reactor Netty `HttpServer` hoặc `HttpClient` wiretap.
- Netty logging handlers.
- Spring WebFlux `WebFilter` có code tự đọc headers và body.
- Codec/encoder/decoder debug logs khi bật request-details.
- Spring Security DEBUG/TRACE.
- HTTP client wire logs của Apache HttpClient, JDK client hoặc thư viện khác.

**Đừng suy rằng chỉ có `log.info` của controller mới tạo logs**. Một agent/tracing library có thể tạo HTTP attributes ngay cả khi ứng dụng không viết một dòng log request.

Mẫu ý tưởng an toàn với WebFlux:

```java
// Mẫu thiết kế, cần project WebFlux phù hợp:
return chain.filter(exchange)
        .doFinally(signal -> {
            // Ghi status/outcome và route đã chuẩn hóa.
            // Không ghi exchange.getRequest().getURI().toString().
            // Không ghi request headers/body.
        });
```

Đây không phải source file độc lập; WebFlux dùng `WebFilter`, `ServerWebExchange`, `WebFilterChain` và Reactor. **Cancellation/streaming** có vòng đời khác synchronous MVC: `doFinally` có thể chạy khi cancel/error/complete, cần test status và timing phù hợp. Lỗi xảy ra trước khi handler mapping có route thì dùng `UNMAPPED`, không echo raw request URI.

Để debug Netty thật, chỉ bật wiretap với synthetic requests, môi trường được cô lập, thời gian ngắn, giới hạn quyền và xác minh pipeline **không xuất secrets** trước khi cho dữ liệu thực chảy qua.

## 18. Outbound HTTP clients cũng là nguồn rò rỉ

Ứng dụng Spring Boot thường gọi dịch vụ khác qua `RestClient`, `RestTemplate`, `WebClient`, Feign hoặc Apache HttpClient. Headers gửi đi có thể chứa bearer token, `Cookie`, API key, signed URL; response có thể chứa dữ liệu khách hàng.

Anti-pattern:

```java
// Không làm: full URI và headers có thể chứa bí mật.
log.debug("calling {} headers={}",
        request.getURI(), request.getHeaders());
```

Thay bằng metadata logic:

```text
outbound_call peer=inventory-api operation=get-stock status=200 durationMs=43
```

`peer` và `operation` là **tên service/operation hữu hạn do code cấu hình**, không phải hostname tùy ý từ user input. Nếu dùng OpenTelemetry/Micrometer tracing, kiểm tra HTTP client instrumentation tạo attributes nào, nhất là `url.full`, query và header capture.

Khi gọi API gặp lỗi, exception message từ HTTP client có thể chứa **URL đầy đủ**, thậm chí signed query. Không log stack trace bất kỳ một cách vô điều kiện cho public exceptions nếu chưa đánh giá `getMessage()` và các cause bên trong.

Một REST response trả 400 với validation errors đôi khi chứa **rejectedValue**; không đưa toàn bộ binding result ra log/error response. Giải pháp là tạo error category/correlation ID an toàn và giữ thông tin nhạy cảm trong luồng xử lý đã được cấp quyền.

## 19. Error handling: không leak qua exception message, stack trace hoặc HTML error page

Một exception có thể phát sinh vì:

- Invalid credential.
- SQL constraint/binding.
- JWT parser failure.
- HTTP client request tới URL có signed query.
- File upload có tên nhạy cảm.
- Validation exception chứa rejected value.
- XML/JSON parser đưa một đoạn payload vào message.
- Template rendering lỗi và in path/context.

Nếu ghi:

```java
// Rủi ro: Throwable message/cause có thể chứa request details.
log.error("Request failed: {}", exception.getMessage(), exception);
```

thì cả exception message và stack trace có thể chứa secrets. Cần phân loại lỗi theo **mã đã kiểm soát**, quan sát trace ID và thông tin vận hành tối thiểu. Có thể dùng exception diagnostics chi tiết trong kho được bảo vệ nghiêm ngặt **sau** khi đánh giá, không coi `Throwable.toString()` là luôn vô hại.

Một handler mẫu:

```java
package com.example.safelog;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class PublicErrorHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    public ProblemDetail badRequest(IllegalArgumentException ignored) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Invalid request");
    }
}
```

Đây là **mẫu tích hợp**, có thể thêm như file `PublicErrorHandler.java` vào demo. Nó không ghi exception detail và không echo submitted values. Trong production, phân loại lỗi nên cụ thể hơn; `IllegalArgumentException` quá rộng chỉ thích hợp minh họa. Không trả lỗi `200 OK` rồi bỏ qua việc phân quyền thực tế.

`server.error.include-stacktrace=never`, `server.error.include-message=never` hỗ trợ giảm thông tin lỗi trong một số cơ chế Spring Boot mặc định, **không tự làm custom exceptions/handlers/GraphQL errors an toàn**. Kiểm thử response JSON và HTML error với nhiều loại lỗi.

## 20. Metrics: route template thay vì path thực và user ID

Spring Boot Actuator + Micrometer Observation cung cấp HTTP metrics, thường là `http.server.requests`; `uri` tag của instrumentation được thiết kế để dùng **URI template trước khi thay biến** khi có thể.

Tốt:

```text
http.server.requests{method="GET",uri="/api/orders/{id}",status="200"}
```

Không tốt:

```text
http.server.requests{uri="/api/orders/PRIVATE_ORDER_123"}
http.server.requests{email="alice@example.test"}
http.server.requests{authorization="Bearer ..."}
```

Raw paths, email, userId, sessionId, access tokens và traceId tạo **high cardinality** hoặc chứa PII; nếu đưa làm tag mỗi request, backend metrics có thể sinh hàng triệu time series, tăng chi phí và làm rò dữ liệu qua dashboard.

Một điểm dễ nhầm: high-cardinality key-values trong Micrometer Observation có thể không được xuất thành metrics labels, nhưng vẫn có thể **được xuất vào trace attributes**. **Không đặt PII vào high-cardinality attributes rồi cho rằng đã được che** chỉ vì nó không nằm trong Prometheus metric.

Khi cần phân loại người dùng, chọn labels hữu hạn như `auth_result=SUCCESS|FAILURE`, `plan_tier=FREE|PAID` nếu được phép và không nhạy cảm, `route`, `method`, `status`, `outcome`. Không dùng free-text exception message hay query text làm dimension.

## 21. Traces: baggage, span attributes và sampling không thay thế redaction

Một trace giúp theo dõi request qua services. Dữ liệu có thể xuất hiện ở:

- Span name.
- Span attributes (HTTP URL, query, user ID, status, error message).
- Span events và exception events.
- Context propagation headers.
- **Baggage** được truyền giữa các services.
- Custom annotations hoặc business tags.
- Database and HTTP client instrumentation.

W3C `traceparent` chứa các định danh trace/span và flags, **không phải credential**. Nhưng vẫn phải validate input và áp dụng trust policy nếu nhận từ môi trường không đáng tin. `baggage` có thể chứa **nội dung tùy ý**, do đó tuyệt đối không đặt email, token, session ID hoặc dữ liệu y tế vào baggage để “tiện debug”.

**Sampling giảm số bản ghi, không giảm mức nhạy cảm của một bản ghi.** Sampling 1% nghĩa là vẫn có thể lưu 1% tokens nếu instrumentation thu token. Tracing không được phép ghi một full Authorization header chỉ vì “khả năng xuất hiện rất nhỏ”.

Khi tự tạo custom spans/observations, chỉ dùng attributes thuộc allowlist. Tránh:

```java
// Sai: thuộc tính nhạy cảm có thể lên tracing exporter.
observation.highCardinalityKeyValue(
        "access_token", request.getHeader("Authorization"));
```

Nếu cần correlation theo người dùng vì nghiệp vụ/audit, phải có policy riêng, chọn pseudonymization hoặc business audit store và retention phù hợp. **Không dùng trace tags như một kho hồ sơ cá nhân.**

## 22. Actuator `httpexchanges`: không phải một cơ chế ẩn dữ liệu tự động

Spring Boot 3.3 có endpoint `httpexchanges` để xem các request-response exchanges gần đây khi được cấu hình với **`HttpExchangeRepository` bean**. Dữ liệu có thể bao gồm URI, method, headers, status, principal, session information và elapsed time, tùy recording configuration. Đây là dữ liệu có khả năng nhạy cảm.

Những điểm cần hiểu:

1. Chỉ thêm `spring-boot-starter-actuator` **không đủ** để endpoint có dữ liệu HTTP exchanges; cần repository phù hợp.
2. Endpoint này **không được expose qua HTTP mặc định**, và chỉ được bật/cho phép truy cập khi vận hành có lý do rõ.
3. Raw exchange URI có thể chứa query/path private; headers có thể chứa credentials tùy cấu hình recording. Không coi đây là “log an toàn” chỉ vì nó đến từ Actuator.
4. Principal/session metadata cũng có thể là dữ liệu cá nhân hoặc identifier nhạy cảm.
5. `management.endpoint.env.show-values=never` **không che dữ liệu của `httpexchanges`**; đây là endpoint khác.
6. `HttpExchangeRepository` dạng in-memory phù hợp demo nhưng không thay thế logging/metrics/tracing được thiết kế và bảo vệ cho production.

Nếu tổ chức cần HTTP exchange audit, hãy ghi metadata đã lọc/chuẩn hóa vào repository custom theo chính sách, hoặc dùng nguồn telemetry đã thiết kế an toàn, chứ không bật full capture rồi phụ thuộc vào network firewall đơn thuần.

`/actuator/logfile`, `/actuator/env`, `/actuator/configprops`, `/actuator/heapdump`, `/actuator/threaddump` và `loggers` cũng có bề mặt riêng. Heap dumps có thể chứa secrets đang ở memory; logger management có thể bị lạm dụng để bật DEBUG/TRACE. **Hạn chế quyền truy cập và tách management port/network** khi cần.

## 23. `env` và `configprops` được che mặc định nhưng không phải tất cả Actuator

Theo Spring Boot 3.3, `/env`, `/configprops` và `/quartz` được sanitization mặc định: giá trị thường bị thay bằng `******`. Các lựa chọn `show-values` là:

```properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
```

`never` che giá trị ngay cả với user đã xác thực, phù hợp chính sách conservative cho một production HTTP API.

Không dùng `always` chỉ để debug vì nó có thể tiết lộ connection strings, secrets, feature flags hoặc thông tin nhạy cảm khác. `when-authorized` cho phép xem giá trị với quyền phù hợp, nhưng vẫn phải có review: secret có thể không được che nếu policy/sanitizer cho phép hiển thị.

`SanitizingFunction` có thể tham gia quy trình che của một số Actuator endpoints; nó không phải bộ lọc toàn hệ thống cho application logs, Tomcat access log hoặc OpenTelemetry span attributes.

**Tối thiểu hóa exposure** quan trọng không kém masking. Đừng public Actuator toàn bộ và kỳ vọng mọi endpoint đều được che bởi cùng một cấu hình.

## 24. Reverse proxy, ingress, WAF và CDN cần cùng chính sách

Một yêu cầu HTTP có thể được ghi tại NGINX trước khi Java process nhận request:

```text
Browser -> CDN access log -> WAF log -> Gateway log
                                 -> Tomcat access log
                                 -> App log / tracer
```

Ngay cả khi Spring filter không log raw URI, NGINX có thể ghi `$request` (request line có path/query), `$request_uri` (bao gồm query), `$http_authorization`, `$http_cookie` hoặc response `Set-Cookie` qua log_format tùy chỉnh.

Khuyến nghị: một log_format **allowlist** dùng method/status, upstream response time, tên route/route key đã chuẩn hóa nếu gateway có hỗ trợ; không ghi raw URI/query và header values. Một proxy không biết Spring MVC route template có thể chỉ ghi **service route category** hoặc status, không nên đoán `/orders/{id}` bằng regex không đáng tin.

Các nơi cần kiểm tra:

- NGINX `access_log`/`log_format` và error logging.
- Ingress annotations hoặc gateway plugins thêm HTTP header capture.
- API Gateway policies và external access logs.
- CDN/WAF request samples, blocked-request diagnostic payload.
- Load balancer access logs và correlation IDs.
- Service mesh sidecars và eBPF agents.
- APM auto-instrumentation/HTTP capture do platform cài.
- Request mirroring/shadow traffic tới môi trường khác.

Không để môi trường staging “rẻ bảo mật hơn” chứa bản sao traffic production với PII. Synthetic traffic có thể dùng để debug mà không sao chép dữ liệu thật.

## 25. Phân biệt sự kiện bảo mật cần audit với bí mật không được ghi

Không ghi credential raw **không có nghĩa tắt security audit**. Những sự kiện hữu ích:

| Sự kiện | Metadata nên cân nhắc | Dữ liệu không cần lưu |
| --- | --- | --- |
| Login thành công | Timestamp, outcome, auth method, pseudonym nếu có căn cứ | Password, token, cookie |
| Login thất bại | Failure category hữu hạn, route, rate-limit bucket | Password vừa nhập, full username/email mặc định |
| Permission bị từ chối | Operation/role category, resource type, status | Full resource content, bearer token |
| Token hết hạn | `auth_failure=EXPIRED` | JWT raw, refresh token |
| Session logout | Event type, status, correlation phù hợp | Session ID raw |
| Access dữ liệu nhạy cảm | Resource category, hành động, audit principal theo policy | Bản sao record/dữ liệu y tế |
| API key rotation | Key identifier nội bộ được duyệt, action/outcome | API key value hoặc private key |

Với audit bắt buộc phải gắn danh tính thực, cần một **audit store có quyền truy cập nghiêm ngặt**, chính sách retention/mã hóa/kiểm toán và rationale hợp pháp; không nhúng tất cả thông tin vào generic application logs hoặc metrics. Dùng role-based access cho người xem audit.

Sự kiện audit phải bảo đảm integrity và tránh log forging. Chuẩn hóa dữ liệu từ client, giới hạn độ dài, không in CR/LF điều khiển log format, ưu tiên structured fields đã validate.

## 26. Masking bằng regex: hữu ích như “lưới an toàn”, không phải bảo đảm

Có thể tồn tại yêu cầu “mask tất cả chỗ xuất hiện `Bearer ...` trong logback”. Nhưng regex appender/layout có nhiều nhược điểm:

- Secret có thể không đúng pattern (Basic, API key custom, signed URL).
- JWT/token có thể bị bẻ dòng hoặc encode nhiều lớp.
- JSON có thể chứa escaped characters, nesting.
- Payload nén, binary, multipart không thể redaction bằng text regex đơn giản.
- Secret có thể đã đi tới appender/agent khác trước khi regex chạy.
- Masking dựa trên tên field sẽ bỏ sót `data` chứa PII.
- Regex phức tạp trên log lớn có thể tốn CPU hoặc bị khai thác gây độ trễ.

Nếu cần dùng regex làm lớp defense-in-depth, hãy test với canaries của nhiều dạng, giới hạn kích thước logs và có monitoring khi redaction engine lỗi. Nhưng chính sách gốc vẫn phải là **allowlist các field hợp lệ trước khi log call xảy ra**.

**Sai tư duy:** “Chúng ta log body đầy đủ rồi mask vài key nhạy cảm.”

**Đúng tư duy:** “Chúng ta không thu body. Nếu một use case nghiệp vụ yêu cầu audit một số trường, tạo **audit DTO riêng chỉ chứa trường đã được phê duyệt**.”

## 27. Audit DTO thay vì ghi nguyên request object

Giả sử API cập nhật profile nhận:

```java
public record UpdateProfileRequest(
        String fullName,
        String email,
        String phone,
        String address) {
}
```

Không làm:

```java
// Sai: record.toString() thường in toàn bộ các trường.
log.info("Updating profile {}", request);
```

Dùng một **event model tối giản**, không chứa object nhạy cảm:

```java
public record ProfileAuditEvent(
        String action,
        String outcome,
        String source,
        long durationMillis) {
}
```

Lúc ghi:

```java
// Mẫu tích hợp: chỉ dùng metadata được kiểm soát.
ProfileAuditEvent event = new ProfileAuditEvent(
        "PROFILE_UPDATED", "SUCCESS", "SELF_SERVICE", 35L);
log.info("profile_audit action={} outcome={} source={} durationMs={}",
        event.action(), event.outcome(),
        event.source(), event.durationMillis());
```

Đây là snippet tích hợp, cần logger và business logic thực. `durationMillis=35L` chỉ là giá trị minh họa, không phải measurement runtime.

Dữ liệu cá nhân có thể vẫn cần được xử lý bởi service để lưu/cập nhật; nguyên tắc là **không chuyển nó sang sink quan sát**, không phải xóa khỏi nghiệp vụ. Nếu event cần liên kết user, chọn một identifier phù hợp policy audit và tránh tags tùy ý trong metrics.

## 28. Pseudonymization: HMAC có thể phù hợp, nhưng không biến dữ liệu thành vô hại

Nếu cần correlating logs của cùng một customer mà không công khai customer ID, một lựa chọn là tạo **HMAC** từ ID bằng khóa riêng cho observability, ví dụ:

```text
user_ref = HMAC-SHA256(observability_key, canonical_customer_id)
```

HMAC giúp giảm rủi ro dò theo dictionary so với SHA-256 trần trên email hoặc số điện thoại. Nhưng kết quả vẫn **liên kết các events của cùng một người**, có thể vẫn được xem là dữ liệu cá nhân/pseudonymous data và phải tuân theo privacy policy.

Ràng buộc:

- Khóa HMAC được lưu trong secret manager, tách với JWT signing key hoặc encryption key nghiệp vụ.
- Không ghi HMAC key vào log, trace, metrics hoặc configuration endpoint.
- Xác định rotation strategy; đổi key làm correlation giữa các giai đoạn khó khăn.
- Giới hạn ai có thể tái định danh bằng lookup/khóa, retention và mục đích.
- Không HMAC toàn bộ bearer token rồi log “token fingerprint” theo mặc định: việc theo dõi token cũng có thể nhạy cảm và làm tăng khả năng phân tích phiên.

Khi không có nhu cầu truy vết một cá nhân, **không cần pseudonymization; đơn giản bỏ identifier** là phương án ít rủi ro nhất.

## 29. Tránh log forging và injection từ dữ liệu client

Nếu client gửi một header chứa xuống dòng hoặc ký tự điều khiển và logger in trực tiếp:

```text
X-Client-Tag: ok\nWARN Security bypassed
```

kết quả text log có thể tạo cảm giác một dòng bảo mật giả. Container hiện đại có thể chặn nhiều ký tự HTTP không hợp lệ, nhưng **không được dựa hoàn toàn vào điều đó** cho mọi nơi (JSON body, query, DB text và các nguồn khác vẫn có control characters).

Giảm rủi ro:

1. Không log raw client-controlled strings.
2. Nếu bắt buộc log category, validate theo allowlist ký tự/độ dài.
3. Dùng structured logging và encoding phù hợp sink.
4. Loại CR/LF/control characters theo policy trước khi cho dữ liệu vào log.
5. Tách error category khỏi exception message và user-submitted values.
6. Giới hạn log size per event và tránh attacker gây log amplification.

**Đừng nhầm** việc escape một chuỗi thành JSON với việc che dữ liệu nhạy cảm: encoding làm dữ liệu dễ parse, **không làm nó bớt nhạy cảm**.

## 30. Khi có Spring Security, không log `Authentication` hoặc principal nguyên vẹn

Spring Security có object chứa principal, credentials, authorities, authentication details và đôi khi các thông tin khác tùy authentication provider. Việc `log.info("auth={}", authentication)` có thể in dữ liệu cá nhân hoặc thông tin nhạy cảm trong `toString` của custom principal.

Không làm:

```java
log.debug("securityContext={}",
        SecurityContextHolder.getContext());
```

Chỉ log category từ kết quả đã kiểm soát:

```text
auth_result=SUCCESS auth_method=OIDC
auth_result=DENIED reason=INSUFFICIENT_SCOPE
auth_result=FAILURE reason=BAD_CREDENTIALS
```

Các `reason` phải là enum/allowlist nội bộ, không lấy trực tiếp exception message. Khi ứng dụng sử dụng custom JWT claims, các claims như email, phone, address hoặc custom scopes có thể nhạy cảm; không tự đem claims vào trace baggage/metrics.

Bật Spring Security DEBUG/TRACE để điều tra phải có procedure, thời hạn, traffic cô lập, quyền truy cập hạn chế và kiểm tra xem logs phát sinh cụ thể những gì ở version/libraries đang dùng. Không public logs trong ticket hoặc chat cho bên không có quyền.

## 31. GraphQL và streaming: query/variables/events cũng có thể nhạy cảm

Một GraphQL request gửi vào `/graphql` có thể chứa:

```json
{
  "query": "query($email: String!){ customer(email:$email){ id address } }",
  "variables": {"email":"private@example.test"}
}
```

Log `operationName` đã qua validate và danh sách error codes có thể hữu ích; log **full `query` và `variables`** dễ làm lộ PII. Không nghĩ rằng một endpoint URL `/graphql` cố định nghĩa là request không mang dữ liệu cá nhân.

Với SSE/WebSocket, mỗi event payload có thể là thông báo đơn hàng, tin nhắn, vị trí, hoặc dữ liệu nhạy cảm khác. Một lớp network wiretap/stream logger có thể xuất toàn bộ payload trong thời gian dài. Hãy chọn metrics như number of active streams, event count, close reason category, duration và bytes, thay vì log nội dung từng message.

Khi lỗi streaming xảy ra, không in nguyên payload cuối cùng để “reproduce”. Dùng synthetic event ID, trace ID và service-side metrics đã chuẩn hóa.

## 32. Multipart, file names và binary payload

File uploads là trường hợp đặc biệt: `Content-Disposition` có `filename`, tên file có thể chứa tên người, mã số hồ sơ hoặc thông tin nội bộ. `Content-Type` không cho biết body có nhạy cảm hay không.

Không log:

```text
uploaded file="passport_alice_2026.jpg" body=<binary bytes>
```

Thay bằng:

```text
upload_attempt route=/api/uploads status=201 size_bucket=1MiB-5MiB type=image
```

`size_bucket` và `type` phải được tạo/chuẩn hóa theo policy; không ghi raw file path, original filename hoặc nội dung file. Giới hạn upload size, malware scanning và path traversal protection là vấn đề riêng, không được giải quyết bởi masking.

Một error từ storage SDK có thể chứa bucket/key/path hoặc presigned URL; đừng log `exception.getMessage()` rồi cho rằng ứng dụng đã che HTTP Authorization.

## 33. Response redaction và `Set-Cookie` trong error paths

Một request có thể thất bại sau khi server đã gửi một số response headers, gồm `Set-Cookie`. Nếu proxy hoặc custom filter chụp toàn bộ response để debug, session credentials vẫn có thể bị leak dù request headers đã được che.

Checklist response:

- Không log `Set-Cookie`, `WWW-Authenticate` nếu chứa chi tiết nhạy cảm, custom auth headers.
- Không log response body chứa customer records, bank data, session tokens.
- Không log raw `Location` header với OAuth code/signed URL.
- Không log rejected validation values trong 400 response.
- Không expose stack trace hoặc raw exception detail trong 500 response.
- Không lưu error response vào hệ thống support công khai nếu có PII.
- Nếu cần audit error class, dùng `error_code` enum và HTTP status.

Error handling của gateway/WAF có thể tạo response trước khi app nhận request; phải kiểm tra từng tầng. Việc app log sanitized không có ý nghĩa nếu proxy đã ghi request/response headers của lỗi.

## 34. Vòng đời logs: thu thập, chuyển, lưu, hiển thị, xóa

Quản trị dữ liệu nhạy cảm không kết thúc tại source code:

```text
Application / proxy
  -> stdout/file/journald
  -> container log collector
  -> broker/queue
  -> central logging/APM vendor
  -> index/search/dashboard
  -> exported CSV/support ticket
  -> backup/retention/deletion
```

Một secret bị ghi vào stdout có thể được nhân bản vào nhiều nền tảng với thời gian lưu khác nhau. Che dữ liệu trong dashboard **không xóa raw bytes** ở storage/queue/backup.

Các kiểm soát vận hành cần thiết:

- TLS khi chuyển telemetry và encryption at rest theo policy.
- Least-privilege roles cho người xem logs/traces.
- Phân tách audit store nhạy cảm khỏi generic application logs.
- Retention giới hạn theo mục đích và quy định áp dụng.
- Audit ai đã truy cập/export dữ liệu nhạy cảm.
- Secret scanning trên log samples và alerts.
- Xóa/rotate credentials ngay nếu token thật bị lộ.
- Quy trình incident response và kiểm kê những destinations đã nhận bản sao.
- Không gửi raw production logs tới bên thứ ba khi chưa kiểm tra hợp đồng và quyền xử lý dữ liệu.

Theo OWASP Logging Cheat Sheet, access tokens, session IDs, passwords, encryption keys, dữ liệu cá nhân nhạy cảm và payment data thông thường không nên ghi trực tiếp vào logs.

## 35. Cách xác minh trên tất cả telemetry sinks

Một kiểm thử đạt yêu cầu không chỉ là `grep` console log. Cần gắn canary giả theo từng bề mặt:

| Bề mặt | Canary giả | Nơi kiểm tra |
| --- | --- | --- |
| `Authorization` | `AUTH_CANARY_A` | App logs, tracing, gateway, outbound logs |
| `Cookie` | `COOKIE_CANARY_B` | App/access log, HTTP exchange repository |
| `Set-Cookie` | `COOKIE_CANARY_C` | Reverse proxy, response capture |
| Raw path | `PRIVATE_ORDER_CANARY_D` | Tomcat/NGINX access logs, route tags |
| Query | `QUERY_CANARY_E` | Access logs, span attributes, exception URLs |
| `Referer` | `REFERER_CANARY_F` | Gateway, custom filters, APM |
| JSON body | `BODY_CANARY_G` | Request logging, cache wrappers, traces |
| Response body | `RESPONSE_CANARY_H` | Debug/HTTP client logs, gateway |
| Multipart filename | `FILE_CANARY_I` | Upload audit, exception logs |
| GraphQL variables | `GQL_CANARY_J` | GraphQL execution errors, trace attributes |

Chỉ dùng **dữ liệu tổng hợp**, tránh kích hoạt thực sự các luồng auth/payment với credentials thật. Test gồm 2xx, 4xx, 5xx, timeouts, redirects, retries, async/streaming, cache hits và response từ gateway khi backend không hoạt động.

Cần kiểm tra **không xuất hiện** canary ở các destinations bị cấm, đồng thời các trường cho phép (`route`, `method`, `status`, `duration`, `traceId` hợp lệ) vẫn hiện đủ để vận hành.

Test chỉ chứng minh các code paths đã đi qua trong điều kiện đã biết. Khi thêm thư viện instrumentation hoặc đổi profile/proxy config, phải chạy lại regression suite.

## 36. Những anti-pattern nguy hiểm nhất

**“Chúng ta chỉ log ở DEBUG.”** Sai tư duy. DEBUG có thể được bật tự động hoặc bởi operator; dữ liệu vẫn có thể được lưu ở log sinks.

**“Che password là đủ.”** Sai. Authorization, cookies, OAuth codes, signed URLs, PII và response payload cũng nhạy cảm.

**“Mặc định Actuator đã sanitize hết.”** Sai. Sanitization của một số endpoints không tự bảo vệ `httpexchanges`, logfile, heapdump, custom endpoints hay custom tracing.

**“Chỉ đọc `getRequestURI()` thì không có token.”** Không chắc. Path có thể chứa email/order IDs hoặc thông tin định danh.

**“Bật `CommonsRequestLoggingFilter` và tắt payload là an toàn.”** Không bảo đảm. Query, headers hoặc path thực vẫn có thể bị log tùy config.

**“Có regex logback sẽ xóa mọi secret.”** Không. Regex có thể bỏ sót encodings, nested payloads và sinks khác.

**“Hash email bằng SHA-256 nghĩa là ẩn danh hoàn toàn.”** Sai. Email có thể bị thử dictionary; pseudonym vẫn cần privacy controls.

**“Sampling 0.1% nghĩa là không có rủi ro.”** Sai. Bất kỳ bản ghi sampled nào có thể chứa secret đầy đủ.

**“Cho traceId bằng session cookie để dễ điều tra.”** Sai. Trace/correlation IDs phải tách khỏi credentials.

**“Bật `server.tomcat.accesslog.enabled=true` với `common` là vô hại.”** Cần kiểm tra request line chứa raw URL/query.

**“Có HTTP 500 thì log toàn bộ exception chắc chắn cần thiết.”** Không phải mọi `Throwable.getMessage()` đều an toàn; log error category trước, dùng diagnostics có kiểm soát nếu cần.

**“Frontend gửi header `Access-Control-Allow-Origin` để che dữ liệu.”** Sai loại vấn đề. CORS không phải masking/logging control.

## 37. Quy trình rà soát codebase và cấu hình triển khai

Khi audit một Spring Boot service, kiểm tra theo nhóm:

**Application code:**

```text
getHeader("Authorization")
getHeaders()
getCookies()
getQueryString()
getRequestURI()
getRequestURL()
request.toString()
response.toString()
log.*(request)
log.*(response)
log.*(exception)
ContentCachingRequestWrapper
ContentCachingResponseWrapper
@ExceptionHandler
```

**Framework/HTTP clients:**

```text
CommonsRequestLoggingFilter
OncePerRequestFilter
WebFilter
WebClient ExchangeFilterFunction
RestTemplate ClientHttpRequestInterceptor
RestClient request interceptor
Reactor Netty wiretap
Apache HttpClient wire logging
Spring Security DEBUG/TRACE
```

**Observability/platform:**

```text
http.server.requests
http.client.requests
ObservationConvention
ObservationFilter
OpenTelemetry attributes
W3C baggage
Actuator httpexchanges/env/configprops/logfile
Tomcat accesslog.pattern
NGINX log_format
Ingress/Gateway/CDN log rules
Logback appenders, encoders and masking patterns
```

Không coi mọi text match là một lỗ hổng; phải xác định code path active, logger levels, profile, byte content, destination và quyền truy cập. Đồng thời không bỏ qua custom libraries và auto-instrumentation agents nằm ngoài Java source.

**Ưu tiên sửa theo thứ tự:** nguồn phát raw data → allowlist telemetry → test canaries → collector filters (phòng thủ phụ) → quyền/retention → monitoring liên tục.

## 38. Bài tập kiểm tra hiểu biết

1. Vì sao `Authorization: Bearer ...` là credential chứ không chỉ metadata debug?
2. Tại sao `Cookie` và `Set-Cookie` cần được loại ở cả request lẫn response capture?
3. `request.getRequestURI()` khác `request.getQueryString()` như thế nào, và vì sao cả hai đều có thể chứa PII?
4. Vì sao route template `/api/orders/{id}` tốt hơn `/api/orders/customer-42` trong logs và metric labels?
5. `CommonsRequestLoggingFilter.setIncludePayload(false)` có tự xóa nguy cơ từ dynamic path không?
6. `ContentCachingRequestWrapper` có tự sanitize body và giải phóng mọi rủi ro memory không?
7. Vì sao `server.tomcat.accesslog.enabled=false` không bảo đảm NGINX/CDN không ghi raw URL?
8. Khi custom Micrometer high-cardinality field chứa email, nó có thể rò qua đâu dù không là metric label?
9. Sampling thấp giúp giảm số bản ghi nhưng có che credentials không?
10. `management.endpoint.env.show-values=never` có áp dụng cho `httpexchanges` không?
11. Vì sao `Throwable.getMessage()` hoặc stack trace có thể gây rò signed URL?
12. Kịch bản nào đòi pseudonymization theo policy, và vì sao HMAC không đồng nghĩa anonymous?
13. Làm sao thiết kế test canary để phát hiện leakage ở app logs **và** gateway logs?
14. Vì sao token hết hạn vẫn nên không được log?
15. Khi phát hiện production access token đã vào logs, cần xử lý các destinations/bản sao và credential thế nào?
16. Ranh giới giữa business audit cần identity và metrics HTTP tổng hợp là gì?
17. Với asynchronous SSE, vì sao `finally` của một Servlet filter có thể chạy trước response kết thúc?
18. Khi thêm endpoint mới có path email, test nào nên được cập nhật để bảo đảm route normalization?

**Thực hành A:** Chạy Spring Boot demo, gửi request với 4 canaries ở header/path/query. Kiểm tra stdout, filter log và Actuator exposure; xác nhận chỉ route template/status/duration được ghi.

**Thực hành B:** Trong môi trường test cô lập, tạm bật một access log pattern ghi request line; quan sát raw path/query bị lộ và sửa pattern hoặc tắt log. Không thử bằng dữ liệu thật và khôi phục cấu hình an toàn ngay sau thí nghiệm.

**Thực hành C:** Tạo hai GET requests khác path variables cùng một route, kiểm tra Micrometer `uri` tag được chuẩn hóa; không thêm raw path thành custom tag.

**Thực hành D:** Viết một audit DTO chỉ cho phép `action`, `outcome`, `errorCode`, `durationMs` rồi dùng unit test khẳng định không có password/email/token fields. Kiểm tra cả error path.

## 39. Kết luận: không thu thập là lớp bảo vệ tốt nhất

**Một công thức triển khai đáng tin cậy:**

```text
1. Phân loại dữ liệu cần bảo vệ
2. Chỉ cho phép HTTP metadata tối thiểu
3. Ghi route template, method, status, latency, outcome
4. Không ghi auth headers, cookies, query, body, raw path
5. Giới hạn và kiểm soát Actuator, wiretap, gateway, access logs
6. Traces/metrics chỉ dùng fields/labels được phê duyệt
7. Kiểm thử synthetic canaries ở từng telemetry sink
8. Bảo vệ pipeline, retention, quyền truy cập và incident response
```

Với Spring Boot, **không có một property thần kỳ** che mọi thông tin nhạy cảm trong tất cả HTTP logs, metrics, traces, Actuator, proxies và HTTP clients. Phải bảo vệ ở **mọi nguồn tạo telemetry**. Dùng allowlist metadata, không log `Authorization`, `Cookie`/`Set-Cookie`, dữ liệu cá nhân, raw path/query/body; khi cần audit nhạy cảm thì có kho dữ liệu riêng và policy rõ ràng. Bảo mật observability tốt phải chứng minh được bằng canary tests, chứ không dựa vào lời hứa rằng “chúng ta đã bật masking”.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Actuator Endpoints, Security và Sanitize Sensitive Values: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — Observability: https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html
- Spring Boot 3.3 — HTTP Metrics/URI Template: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
- Spring Boot 3.3 — Common Application Properties (`server.tomcat.accesslog.*`, `management.endpoint.*`): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework 6.1 — `OncePerRequestFilter`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Framework 6.1 — `AbstractRequestLoggingFilter`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/filter/AbstractRequestLoggingFilter.html
- Spring Framework — HTTP Observations: https://docs.spring.io/spring-framework/reference/integration/observability.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OpenTelemetry Semantic Conventions — HTTP: https://opentelemetry.io/docs/specs/semconv/http/