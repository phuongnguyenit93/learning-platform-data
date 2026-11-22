# Token và credential trong Java Logging — bảo vệ bí mật và quyền riêng tư

## 1. Vì sao đây là một chủ đề quan trọng?

Trong Java Logging, log giúp điều tra đăng nhập lỗi, quyền truy cập bị từ chối, kết nối database thất bại, token hết hạn hoặc thao tác quản trị. Nhưng **token và credential** có thể cho phép người sở hữu thực hiện hành động thay mặt người dùng, service hoặc hệ thống. Nếu ghi chúng vào log, quyền *đọc log* có thể vô tình trở thành quyền *sử dụng credential*.

Bài này thuộc nhóm **Quyền riêng tư**: cần giữ đủ thông tin vận hành và audit mà **không phát tán bí mật, session identifier hay dữ liệu cá nhân không cần thiết**.

So sánh hai cách ghi log:

```text
KHÔNG NÊN:
INFO Login failed: Authorization=Bearer TEST_SECRET_VALUE
ERROR Database connection failed: jdbc:postgresql://db/app?password=TEST_SECRET_VALUE

NÊN:
WARN event=auth.denied method=Bearer reason=INVALID_CREDENTIAL request_id=req-42
ERROR event=db.connection_failed datasource=orders-db error_type=SQLTransientConnectionException
```

Các giá trị trong ví dụ là **chuỗi giả**, không phải credential có hiệu lực. Cách ghi an toàn vẫn cho biết loại thao tác, lỗi và request liên quan, nhưng không đưa secret vào nơi người khác có thể tìm kiếm hoặc tải xuống.

**Nguyên tắc cốt lõi:** thiết kế dữ liệu log an toàn ngay **trước** khi gọi logger. Masking ở appender/Collector là phòng vệ thứ hai, không phải lý do để log bí mật ở nguồn.

## 2. Phân biệt token, credential và dữ liệu định danh

**Credential** là bằng chứng phục vụ xác thực/ủy quyền, ví dụ password, API key, client secret, private key. **Token** thường là giá trị do hệ thống phát hành, dùng để đại diện một phiên, danh tính, quyền truy cập hoặc một hành động. Bearer token là credential: ai nắm giữ token có thể được chấp nhận theo phạm vi và điều kiện hiệu lực của nó.

| Dữ liệu | Nguy cơ nếu log giá trị gốc | Thông tin có thể log thay thế |
| --- | --- | --- |
| Password, PIN, OTP | Lộ quyền truy cập hoặc mã dùng một lần | `auth_method`, `outcome`, lý do chuẩn hóa |
| API key, OAuth client secret | Giả mạo ứng dụng, gọi API | Tên tích hợp, key alias/version được phép |
| Bearer/access token | Dùng lại quyền đã cấp cho người khác | `credential_present`, `auth_method`, kết quả |
| Refresh token | Xin access token mới | `refresh_attempt`, result, error category |
| Session ID và `Cookie` | Chiếm phiên đăng nhập | `session_started`/`session_expired`, request ID |
| `Set-Cookie` response | Lộ cookie có quyền | Kết quả tạo phiên, không ghi giá trị cookie |
| JWT | Lộ claims và có thể dùng token còn hiệu lực | Claim **được allowlist** nếu thực sự cần |
| OAuth authorization code | Có thể trao đổi lấy token trong điều kiện nhất định | `flow=AUTHORIZATION_CODE` và outcome |
| PKCE verifier, magic/reset token | Lộ thông tin xác minh/khôi phục | Route template, event type và outcome |
| Private key, signing key, keystore password | Xâm phạm mật mã hoặc định danh service | Key ID/alias không nhạy cảm, rotation event |
| JDBC URI chứa password | Lộ tài khoản DB | Tên datasource, loại lỗi, retry count |
| Cloud temporary credentials | Truy cập tài nguyên cloud | Role/service identity danh định được duyệt |
| Webhook signing secret | Giả mạo webhook | `signature_valid=false` và provider |

**JWT ký không đồng nghĩa JWT được mã hóa.** Với định dạng JWS thường gặp, header/payload mã hóa Base64URL có thể đọc được mà không cần biết signing key. Không log toàn bộ JWT, không in payload đã decode chỉ vì muốn debug. Claim như `sub`, `email`, `jti` cũng có thể là dữ liệu nhận dạng hoặc liên kết hành vi.

Không phải field có tên “ID” nào cũng an toàn. `client_id` đôi khi là public identifier, nhưng `session_id` thường là secret; `trace_id` có thể phục vụ correlation trong khi `token` không được phép. Mọi metadata còn phải qua chính sách riêng tư và retention của hệ thống.

## 3. Vì sao một dòng log có thể lan ra rất nhiều nơi?

Một event Java có thể đi qua chuỗi:

```text
HTTP Authorization / Cookie / credentials
                 |
          Java application
                 |
          SLF4J / JUL / Log4j 2
                 |
      Console / File / Async / OTLP
            /              \
       Log shipper      Collector
            \              /
           Central log backend
                  |
          Dashboard / Alert
                  |
       Export / Ticket / Backup
```

Một token được ghi tại `log.debug` có thể được lưu ở console, file xoay vòng, agent, hệ thống search, alert email, bản chụp màn hình, ticket hỗ trợ và backup. Xóa ở một nguồn **không xóa các bản sao downstream**. Quyền đọc dashboard cũng có thể rộng hơn quyền truy cập secret manager hoặc tài khoản dịch vụ.

Tác hại tùy loại token và thời hạn hiệu lực, gồm chiếm phiên, truy cập API, truy vấn dữ liệu, tăng quyền hoặc vi phạm privacy. Ngay cả token đã hết hạn vẫn có thể tiết lộ claims, metadata hoặc mẫu hoạt động. Vì thế vấn đề không chỉ là “token còn dùng được không” mà còn là **thu thập vượt nhu cầu và mở rộng phạm vi người có thể đọc**.

## 4. Những đường rò rỉ thường gặp trong Java

| Nguồn | Ví dụ có rủi ro | Cách phòng |
| --- | --- | --- |
| Logging trực tiếp | `log.info("token={}", token)` | Không truyền token vào logging API |
| DTO / record | `log.debug("login={}", loginRequest)` | Không in object chứa password; tạo safe view |
| HTTP request headers | Dump `Authorization`, `Cookie`, `X-API-Key` | Chỉ log tên trường/loại auth đã phê duyệt |
| HTTP response headers | Dump `Set-Cookie` | Loại giá trị cookie |
| HTTP body | Login/refresh JSON chứa secret | Không dump body xác thực |
| URL/query string | `/reset?token=...`, `?code=...` | Log route template, không raw URI/query |
| Exception | `ex.getMessage()` kèm URL/header/password | Log error category, type; sanitize toàn bộ cause |
| Stack trace | Throwable chứa thông điệp có secret | Không tự động in Throwable từ nguồn không tin cậy |
| MDC / ThreadContext | `MDC.put("access_token", token)` | Chỉ đưa correlation metadata hợp lệ |
| SQL/ORM logging | JDBC bind value, DSN có password | Không log bind values nhạy cảm |
| HTTP client wire log | DEBUG request/response OAuth | Tắt raw wire payload hoặc kiểm soát chặt |
| Reverse proxy/gateway | Access log toàn bộ query/header | Cấu hình privacy độc lập ở từng lớp |
| Telemetry | Span attributes, baggage chứa token | Không đặt secret vào signal observability |
| CI/CD / startup | Echo env vars, config, command line | Không in secret ở log build/deploy |

Đặc biệt, `Authorization: Basic ...` là Base64 của thông tin xác thực, **không phải một dạng mã hóa bí mật**. Nó cũng cần được loại khỏi log. Với bearer token, giá trị `Authorization` có thể truy cập được trong code nhưng **không được trở thành tham số logger**.

URL nguy hiểm ngay cả khi không có query: đường dẫn `/reset/ACTUAL_TOKEN` có thể chứa mã khôi phục. Vì thế chỉ bỏ query string rồi log `request.getRequestURI()` chưa chắc an toàn.

## 5. Phòng vệ mạnh nhất: allowlist log fields

Thay vì chờ encoder tìm các khóa “trông giống secret”, định nghĩa **danh sách field được phép ghi** cho từng loại sự kiện.

Ví dụ event xác thực:

| Field | Giá trị minh họa | Chính sách |
| --- | --- | --- |
| `event` | `auth.denied` | Được log |
| `auth_method` | `Bearer` | Được log |
| `credential_present` | `true` | Được log nếu cần |
| `outcome` | `DENIED` | Được log |
| `reason` | `INVALID_CREDENTIAL` | Được log theo enum |
| `request_id` | `req-42` | Được log nếu ID được tạo an toàn |
| `route` | `/api/orders/{id}` | Được log ở dạng template |
| `service` | `account-service` | Được log |
| `client_id` | `client-demo` | Chỉ theo chính sách |
| `authorization` | Bearer token thô | **Cấm** |
| `password` / `otp` | Giá trị bí mật | **Cấm** |
| `refresh_token` / `api_key` | Giá trị bí mật | **Cấm** |
| `cookie` / `session_id` | Session credential | **Cấm** |
| `exception_message` | Text chưa phân loại | Không log mặc định |

**Allowlist khác blocklist:** nếu developer thêm field `sessionProof` vào DTO, allowlist không tự in nó. Blocklist chỉ biết `password` và `token` có thể bỏ sót alias mới.

Không dùng `request.toString()`, `Map.toString()` hoặc serialize toàn bộ object như một shortcut. Bản thân Java `record` tự sinh `toString()` với các component, nên một record chứa `password` có thể lộ khi được log trực tiếp.

### 5.1. Structured logging an toàn

Ví dụ bản ghi JSON không chứa secret:

```json
{
  "event": "auth.denied",
  "service": "account-service",
  "auth_method": "Bearer",
  "credential_present": true,
  "reason": "INVALID_CREDENTIAL",
  "route": "/api/orders/{id}",
  "request_id": "req-42"
}
```

Đây là **schema minh họa**; không tự nhận là schema bắt buộc của OpenTelemetry hay framework. Khi chuyển sang JSON encoder, phải kiểm tra các thuộc tính **message, structured fields, MDC, marker và exception**. Một encoder ghi JSON không có nghĩa tự loại bí mật.

## 6. Ví dụ Java 17+ có thể chạy độc lập

Ví dụ dùng `java.util.logging` (JUL) từ JDK, không cần thư viện ngoài. Nó tạo **token giả chỉ dùng trong bài kiểm thử**, nhưng log chỉ chứa loại xác thực, cờ có credential và kết quả. `CaptureHandler` giữ output trong bộ nhớ để kiểm tra chính xác rằng chuỗi token giả không xuất hiện.

Tạo file `SafeCredentialLoggingDemo.java`:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class SafeCredentialLoggingDemo {
    private static final class CaptureHandler extends Handler {
        private final StringBuilder output = new StringBuilder();

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            output.append(record.getLevel().getName())
                  .append(" ")
                  .append(record.getMessage())
                  .append("\n");
        }

        @Override public void flush() { }
        @Override public void close() { }

        String content() {
            return output.toString();
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.auth");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        CaptureHandler handler = new CaptureHandler();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        try {
            // Chỉ là fixture tổng hợp, không phải token thật.
            String syntheticToken = "test-only-not-a-real-secret";
            boolean credentialPresent = !syntheticToken.isBlank();

            logger.info("event=auth.attempt method=Bearer "
                    + "credential_present=" + credentialPresent
                    + " request_id=req-42");
            logger.warning("event=auth.denied "
                    + "reason=INVALID_CREDENTIAL request_id=req-42");

            String loggedText = handler.content();
            if (loggedText.contains(syntheticToken)) {
                throw new AssertionError("Secret leaked to log");
            }
            System.out.print(loggedText);
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 SafeCredentialLoggingDemo.java
java SafeCredentialLoggingDemo
```

Stdout **chính xác**:

```text
INFO event=auth.attempt method=Bearer credential_present=true request_id=req-42
WARNING event=auth.denied reason=INVALID_CREDENTIAL request_id=req-42
```

Vì `setUseParentHandlers(false)`, handler của logger cha không tạo thêm bản. `CaptureHandler` cố tình không in timestamp, chỉ ghi hai event đã tạo, nên kết quả xác định.

**Giới hạn bài demo:** `CaptureHandler` không phải hệ thống log bảo mật production. Nó vẫn nối nguyên `record.getMessage()`; nếu developer sau này log secret ở nguồn, handler vẫn ghi secret. Phép test `contains(...)` không phát hiện mọi biến thể encode/escape của credential. Trên ứng dụng thật phải kiểm thử **tất cả** appender và exporter.

### 6.1. Parameterized logging không tự mask secret

Các lời gọi dưới đây **không an toàn** dù dùng placeholder:

```java
log.debug("Authorization={}", authorizationHeader);
log.info("loginRequest={}", loginRequest);
log.error("Authentication failed", exceptionWithTokenInMessage);
```

Đây là **đoạn code minh họa SLF4J**, không phải class độc lập. Placeholder `{}` hỗ trợ formatting theo cơ chế của logger, nhưng không tự che dữ liệu. `toString()` của DTO hoặc exception message/cause có thể tiết lộ secret.

Thay bằng metadata:

```java
log.warn("event=auth.denied method={} reason={} request_id={}",
        "Bearer", "INVALID_CREDENTIAL", safeRequestId);
```

`safeRequestId` phải là correlation ID được tạo/kiểm soát, **không phải session ID hoặc token**. Nếu cần log client/actor, chỉ dùng identifier đã qua đánh giá privacy.

## 7. Exception và stack trace thường chứa nhiều hơn ta nghĩ

Trong Logback/Log4j 2, `log.error("Request failed", ex)` có thể đưa stack trace, cause chain và suppressed exceptions ra output. Các đối tượng exception có thể chứa URL, HTTP headers, response body, JDBC connection URI hoặc token trong message.

Một số nguồn:
- HTTP client thông báo request thất bại và kèm URI chứa token.
- Driver in database connection string chứa user/password.
- Parse JWT thất bại, exception lặp lại toàn bộ input.
- Lỗi OAuth endpoint có response body chứa token/secret.
- Validation error hiển thị giá trị của field password/OTP.

Không cần bỏ mọi stack trace bằng mọi giá. Cần **chủ động ngăn secret đi vào exception từ đầu**, dùng error code và exception type an toàn ở log chung, sau đó chỉ in stack trace khi đã kiểm tra nguồn dữ liệu đáng tin cậy.

Ví dụ snippet SLF4J tích hợp:

```java
log.error("event=auth.provider_failed provider={} error_type={} request_id={}",
        "identity-provider",
        ex.getClass().getSimpleName(),
        safeRequestId);
```

Nó không đưa `ex` hay `ex.getMessage()` vào logger. Khi thật sự cần traceback, phải đánh giá cả cause và các thông điệp lồng nhau; tránh gắn exception nguy hiểm vào argument cuối của logger một cách vô thức.

## 8. Bảo vệ HTTP headers, URL và body

### 8.1. Request headers và cookies

Không dump giá trị của:
- `Authorization`, `Proxy-Authorization`;
- `Cookie`, `Set-Cookie`;
- `X-API-Key`, `X-Auth-Token` hoặc các header custom chứa credentials;
- headers mang signature, CSRF/session proof hoặc secret trong giao thức nội bộ.

Tên header có thể khác giữa các SDK. Vì vậy một danh sách denylist vài tên **không đủ** để bảo vệ một chức năng “log all headers”. Nếu chỉ cần biết request có Authorization hay không, có thể dùng Boolean đã được cho phép và không giữ bản sao header trong event.

### 8.2. Query string và path segment

Có thể thấy token trong `?access_token=...`, `?code=...`, `?signature=...`, password-reset link hoặc signed URL. Khi log route, dùng **route template** như `/reset/{token}`, không dùng raw URL. Tránh log redirect `Location` có code/token. Các hệ thống reverse proxy và ingress cũng cần cấu hình riêng.

### 8.3. Request body

Login và refresh-token endpoints thường có `password`, `otp`, `client_secret` hoặc `refresh_token`. Tránh in raw body khi validation exception. Nếu muốn biết field thiếu, log tên field **từ allowlist**, không log giá trị. Không tự serialize POJO/record chứa secret chỉ để kiểm tra JSON.

## 9. Spring Boot 3: minh họa log request không in credential

Đây là **một class tích hợp** trong dự án Spring Boot 3 sử dụng Spring MVC, SLF4J và Jakarta Servlet; cần dependencies của framework. Nó không phải chương trình chỉ dùng `javac`.

File `src/main/java/com/example/logging/SafeRequestLogFilter.java`:

```java
package com.example.logging;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

@Component
public final class SafeRequestLogFilter extends OncePerRequestFilter {
    private static final Logger LOG =
            LoggerFactory.getLogger(SafeRequestLogFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        try {
            chain.doFilter(request, response);
        } finally {
            Object mapped = request.getAttribute(
                    HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
            String route = mapped instanceof String s
                    ? s : "unmatched";
            LOG.info("event=http.request method={} route={} status={}",
                    request.getMethod(), route, response.getStatus());
        }
    }
}
```

`HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` thường chứa route pattern sau khi handler đã được map. Nếu request bị chặn trước MVC, dùng `unmatched` thay vì raw URI/query. Ví dụ chỉ log method, route và status; không đụng tới Authorization, Cookie, principal, body hay raw URL.

**Cần xem toàn bộ pipeline:** Spring Security, servlet container access log, HTTP client interceptors, ingress và reverse proxy có thể ghi request theo đường khác. Filter trong ứng dụng **không** tự bảo vệ chúng. Nếu route pattern hoặc method không tuân thủ allowlist nội bộ, tiếp tục chuẩn hóa theo chính sách của hệ thống.

### 9.1. Debug HTTP client phải có giới hạn

Bật DEBUG/TRACE hoặc wire logging trên HTTP client, ORM, Security SDK hoặc OAuth SDK có thể tạo các bản dump chứa headers và body. Nên:
1. Dùng môi trường với credential tổng hợp khi tái hiện.
2. Chọn logger package cụ thể, không bật TRACE toàn bộ hệ thống.
3. Chỉ log method, endpoint template, status, latency và error category.
4. Kiểm tra console, file và Collector trước khi chia sẻ log.
5. Tắt debug chi tiết sau khi điều tra.

Đặc biệt, token endpoint trả JSON có `access_token`/`refresh_token`: không log nguyên response để “xem token có cấp hay không”. Log `issued=true`, loại token và TTL bucket nếu được duyệt.

## 10. MDC, ThreadContext và tracing không phải secret store

MDC của SLF4J/Logback và ThreadContext của Log4j 2 dùng để gắn metadata cho log. Đây là công cụ correlation, không phải chỗ lưu token.

Không làm:

```java
MDC.put("access_token", token);
log.info("request started");
```

Đoạn này là snippet SLF4J trong một class đã có logger. Nếu pattern dùng `%X` hoặc JSON encoder serialize toàn bộ MDC, token có thể bị nhân vào **mọi log** phát từ thread đó. Khi thread pool tái sử dụng thread, MDC không được dọn còn có thể lẫn context giữa request.

Nên làm:

```java
try {
    MDC.put("request_id", safeRequestId);
    log.info("event=request.started");
} finally {
    MDC.remove("request_id");
}
```

`safeRequestId` phải là ID không cấp quyền, được phát hành/kiểm soát phù hợp chính sách. Với async logging, framework có thể snapshot MDC để mang qua queue; **đừng đặt secret vào MDC rồi nghĩ worker khác sẽ không thấy**.

Với OpenTelemetry, không đưa access token, cookie hay private key vào **span attribute, resource attribute hoặc baggage**. Baggage có thể được propagate tới service khác. `trace_id` giúp liên hệ log với trace, nhưng không phải một nơi chứa chứng cứ xác thực.

## 11. Masking/redaction là phòng vệ thứ hai

Một số cách áp dụng bổ sung:
- Structured log encoder cho phép tạo output từ allowlisted fields.
- Redaction theo trường JSON (kể cả nested field), có kiểm tra tên alias/case.
- Filter riêng ở appender để loại một số dạng thông tin không mong muốn.
- Sanitization tại Collector trước khi dữ liệu vào backend.
- Secret scanning định kỳ để phát hiện format mới bị bỏ sót.

**Giới hạn:** filter ở appender console không kiểm soát appender file; filter ở Collector chạy **sau khi bí mật đã ra khỏi JVM**. Regex đối chiếu một pattern không bao quát URL, JSON escaped, Base64, multiline exception và biến thể từ SDK.

Log4j 2 có `%replace` trong Pattern Layout. Ví dụ *chỉ minh họa* một lớp thay thế chuỗi kiểu Authorization header trong text:

```xml
<PatternLayout
    pattern="%d %-5p %c - %replace{%msg}{(?i)(authorization:\s*bearer\s+)\S+}{$1[REDACTED]}%n"/>
```

Cú pháp thuộc **Log4j 2 PatternLayout**, không được copy nguyên sang Logback. Pattern này chỉ áp dụng nơi layout được gắn và chỉ tìm **một dạng text**; nó không phải chính sách production hoàn chỉnh. Đừng chủ động đưa token vào logger chỉ để thử xem regex có che được hay không. Với một hệ thống thật, dùng allowlist và kiểm tra nhiều sink tốt hơn.

### 11.1. Chỉ hiển thị vài ký tự token có đủ không?

Không tự mặc định rằng `token_prefix=abc` hoặc `last4=1234` là an toàn. Nó vẫn tiết lộ một phần secret, có thể hỗ trợ liên kết truy cập hoặc thử đoán với credential yếu. Nếu cần phân biệt key/token, ưu tiên **key ID hoặc version riêng không cấp quyền** được hệ thống phát hành và cho phép log; không lấy substring từ credential làm định danh.

## 12. Hash, fingerprint và HMAC

Một số hệ thống muốn biết nhiều request có dùng cùng một credential hay không. **Không dùng log raw token** để thực hiện correlation.

Hash thuần `SHA-256(token)` có thể bị dò với token/OTP có entropy thấp, và một hash ổn định có thể trở thành mã theo dõi lâu dài. Nếu cần thiết và đã được security/privacy review, có thể xem xét **HMAC-SHA-256 dùng key bí mật riêng**, quản lý tại secret manager, để tạo fingerprint phục vụ correlation.

Điều kiện:
- HMAC key không được ghi vào log, source hay môi trường hiển thị rộng.
- Fingerprint **vẫn có tính liên kết** và cần retention/ACL riêng.
- Key rotation ảnh hưởng khả năng đối chiếu lịch sử.
- Không dùng fingerprint làm credential hoặc truyền cho hệ thống xác thực.
- Đánh giá xác suất collision nếu cắt ngắn fingerprint.
- Nếu request ID hoặc key alias đủ dùng, **không cần tạo fingerprint**.

HMAC không cho phép giữ nguyên quyền riêng tư chỉ bằng cách “băm cho xong”. Lưu cả mã liên kết và audit trail phải có mục đích hợp lệ.

## 13. Quyền truy cập và retention của logs

Logging có thiết kế data minimization vẫn cần kiểm soát:
- **Least privilege:** role nào được search/export log? Có cần tách audit/security log và application log không?
- **Encryption in transit:** TLS/xác thực giữa appender, agent, Collector và backend.
- **Encryption at rest:** bảo vệ storage, snapshots và backups.
- **Retention:** giới hạn thời gian giữ phù hợp mục đích/pháp lý; không để mọi log tồn tại vô thời hạn.
- **Access audit:** theo dõi người xem/tải/xuất log khi hệ thống hỗ trợ.
- **Tách môi trường:** tránh chuyển credential thử nghiệm hoặc log production nhạy cảm sang workspace có quyền rộng.
- **Third-party vendors:** biết nhà cung cấp log, telemetry, support nào nhận dữ liệu.
- **Báo cáo sự cố:** tránh copy nguyên credential vào alert, ticket hay chat của đội điều tra.

Mã hóa không biến việc log raw token thành an toàn: người có quyền xem nội dung sau giải mã vẫn có thể sử dụng token. Cần kết hợp data minimization và quyền truy cập.

## 14. Kiểm thử không rò bí mật qua nhiều sink

Nên dùng **synthetic canary token**: chuỗi giả dễ nhận diện nhưng không có hiệu lực xác thực. Tạo request kiểm thử chứa canary ở Authorization header, Cookie, JSON body, URL, exception message giả lập và nested DTO. Sau đó kiểm tra:

1. Logger trong code **không nhận** secret như tham số.
2. Structured message, MDC, marker và exception không chứa secret.
3. Console/stdout và stderr không phát canary.
4. File, rolling archives và async appender không ghi canary.
5. OTLP/Collector/backend không ingest canary.
6. Alert/ticket/webhook/export của pipeline không đính canary.
7. Không có log duplicate do nhiều pipeline khiến sự cố lan rộng.
8. Những security events cần thiết vẫn còn để điều tra.

Ví dụ ma trận:

| Trường hợp | Kỳ vọng |
| --- | --- |
| HTTP Authorization Bearer | Chỉ log method/outcome, không giá trị |
| HTTP Basic | Không log Base64 credential |
| Login DTO có password/OTP | Không log toàn DTO |
| OAuth refresh fail | Log reason enum, không refresh token |
| JWT validation error | Không log JWT nguyên chuỗi hoặc payload decoded |
| OAuth redirect có `code` | Log route template, không raw URL |
| Exception mang secret trong message | Không để text nguy hiểm qua Throwable formatter |
| MDC nhận nhầm token | Test phát hiện, không serialize sang sink |
| HTTP wire DEBUG | Không có raw headers/body |
| Structured JSON nested field | Áp allowlist cả nested fields |
| Token giả ở collector | Không có canary trong backend |
| Request auth bị từ chối | Có event, outcome, request ID và thời gian |

Secret scanner dựa trên regex/entropy giúp tìm một số vấn đề nhưng có false positive/false negative. Kết quả scanner không phát hiện secret **không phải bằng chứng tuyệt đối**. Cần kiểm thử cả khi framework được nâng phiên bản và khi thay đổi HTTP SDK, encoder hoặc collector config.

## 15. Khi đã lỡ log credential: quy trình ứng phó

Nếu phát hiện token, password, API key hoặc private key trong log:

1. **Đánh giá phạm vi**: loại credential, thời điểm xuất hiện, đích log, ai có quyền đọc và các bản sao có thể tồn tại. Không paste giá trị gốc vào ticket mới.
2. **Containment:** hạn chế truy cập vào các log liên quan và thực hiện **revoke/rotate** credential bị ảnh hưởng theo quy trình.
3. **Thay thế nơi sử dụng:** cập nhật service/config/deployment để không còn phụ thuộc secret cũ; xác minh ứng dụng vẫn hoạt động.
4. **Sửa nguồn rò:** bỏ log input nhạy cảm, sửa DTO `toString()`/wire logging/exception/MDC và thêm safe event fields.
5. **Xử lý dữ liệu đã lưu:** phối hợp quản trị backend để xóa/hạn chế theo khả năng, chính sách và yêu cầu bảo toàn audit; kiểm tra export, alert và backups.
6. **Điều tra lạm dụng:** đối chiếu thời điểm secret còn hiệu lực với sự kiện sử dụng đáng ngờ.
7. **Kiểm thử hồi quy:** phát canary tổng hợp, xác minh không còn được ghi trong các sink.
8. **Đánh giá nghĩa vụ privacy/security** theo chính sách tổ chức và pháp luật áp dụng.

Rotation không xóa secret đã bị chụp lại hoặc các thông tin nhận dạng đi kèm; xóa dòng log cũng không thu hồi token còn hiệu lực. Hai hướng xử lý phải diễn ra phù hợp.

## 16. Những ngộ nhận dễ gây lỗi

| Ngộ nhận | Thực tế |
| --- | --- |
| “Chỉ log DEBUG nên bí mật không lộ.” | DEBUG có thể bật trong production hoặc môi trường debug, và dữ liệu đã được lưu. |
| “Tham số `{}` của SLF4J tự che token.” | Placeholder không phải redaction. |
| “JWT trông như mã hóa nên an toàn.” | JWT ký thường có payload đọc được; token còn là bearer credential. |
| “Chỉ log 4 ký tự cuối là ổn.” | Vẫn có thể tiết lộ/làm liên kết; cần chính sách cụ thể. |
| “Chỉ mask console là đủ.” | File, async, OTLP và Collector có thể là tuyến độc lập. |
| “Đã dùng JSON logging thì không leak.” | JSON encoder vẫn có thể serialize raw token, MDC và Throwable. |
| “Exception chỉ in stack trace kỹ thuật.” | Cause/message có thể chứa URL, headers và response body. |
| “SHA-256(token) là dữ liệu công khai.” | Với credential yếu có thể bị dò và fingerprint vẫn là identifier. |
| “Có TLS là được phép log mật khẩu.” | TLS bảo vệ đường truyền, không giảm việc ai có thể đọc dữ liệu sau lưu. |
| “Xóa ở file là đủ.” | Bản sao có thể ở backend, export, alert và backup. |
| “Tắt hết auth log sẽ an toàn.” | Vẫn cần ghi sự kiện bảo mật **không chứa credential**. |

## 17. Checklist trước khi triển khai

1. Phân loại tất cả secret và trường chứa secret (password, OTP, token, cookie, API key, private key, DB URL).
2. Định nghĩa security event schema với **allowlist field** và outcome/reason chuẩn.
3. Không truyền secret cho logger, `toString()`, throwable hoặc MDC.
4. Không log raw Authorization/Cookie headers, body xác thực, URL/query và signed links.
5. Log endpoint theo route template; dùng correlation ID được cấp an toàn.
6. Kiểm soát HTTP client wire logs, security framework DEBUG, ORM bind-value logging.
7. Kiểm tra riêng Logback/Log4j 2/JUL, console/file/async/OTLP, Collector và backend.
8. Dùng masking ở sink như lớp phụ, kiểm thử case/alias/encoding/nested field.
9. Quản lý quyền đọc/export, retention, TLS, encryption và vendor access.
10. Chạy synthetic canary test trong CI/integration và kiểm tra mọi output.
11. Có runbook revoke/rotate và xử lý log đã chứa credential.
12. Giữ lại sự kiện auth quan trọng mà không giữ credential gốc.

**Tóm lại:** log nên cho biết một credential **đã được trình bày, kiểm tra và chấp nhận/từ chối như thế nào**, không được cung cấp chính credential cho người đọc log. Thiết kế field an toàn ngay tại nguồn là biện pháp mạnh nhất; encoding, redaction, kiểm soát truy cập và incident response là các lớp bảo vệ bổ sung.

## Tài liệu tham khảo

- [OWASP Logging Cheat Sheet – Data to exclude và sanitization](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
- [OWASP Secrets Management Cheat Sheet – Rotation, revocation và logging](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html).
- [OWASP DevSecOps Logging and Monitoring](https://owasp.github.io/DevSecOpsGuideline/2-Process/2-7-Operate/2-7-2-Logging-and-Monitoring/).
- [Oracle Java – java.util.logging.Logger](https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/Logger.html).
- [Oracle Java – java.util.logging.Handler](https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/Handler.html).
- [Apache Log4j 2 – Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html).
- [Logback – Logging architecture](https://logback.qos.ch/manual/architecture.html).
- [OpenTelemetry – Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/).