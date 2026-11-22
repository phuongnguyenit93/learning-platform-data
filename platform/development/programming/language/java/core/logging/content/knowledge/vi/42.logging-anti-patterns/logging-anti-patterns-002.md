# Log bí mật trong Java: anti-pattern, cách phòng tránh và kiểm thử

## 1. Mục tiêu

**Log bí mật** là một anti-pattern bảo mật: ứng dụng vô tình ghi **password, access token, refresh token, session cookie, API key, private key, signing key, connection string chứa mật khẩu hoặc giá trị nhạy cảm khác** vào logging pipeline. Các dữ liệu này có thể bị nhân bản qua console/file, container runtime, log collector, dashboard, backup, file export và ticket hỗ trợ.

Vấn đề thuộc nhóm **Anti-pattern logging** của Java Core Logging. Nó không phải chỉ là vấn đề mức DEBUG hay format log. Một người được phép đọc log thông thường có thể không được phép đọc secret từ vault; nếu secret lọt vào log, ranh giới quyền này bị phá vỡ.

Bài học hướng tới những khả năng:

1. Nhận diện đường rò trực tiếp và gián tiếp từ **SLF4J, Logback, Log4j2, JUL, exception, DTO.toString(), Java record, HTTP filter, MDC và cấu hình startup**.
2. Phân biệt **secret, PII và metadata** để biết dữ liệu nào cần loại bỏ và dữ liệu nào có thể ghi phục vụ điều tra.
3. Thiết kế safe logging dựa trên **allowlist fields**, event name, safe error code, correlation ID và output encoding.
4. Biết vì sao **tắt DEBUG, mã hóa log hoặc che dữ liệu ở dashboard** không giải quyết hết nguy cơ.
5. Chạy ví dụ **Java 17 độc lập** dùng JUL, chứng minh giá trị secret giả không xuất hiện trong log đã capture.
6. Viết test tự động và quy trình ứng phó khi secret thật đã được ghi.

## 2. Tại sao log chứa secret nguy hiểm?

Một ứng dụng có thể lấy token từ hệ xác thực hoặc secrets manager với quyền hẹp. Nhưng hệ log tập trung thường có nhiều đối tượng sử dụng hơn: developer, support, SRE, security analyst, CI/CD, collector service account và bên xử lý sự cố.

Một event như sau là anti-pattern:

~~~text
DEBUG outbound request Authorization: Bearer <ACCESS_TOKEN>
INFO  db connected with url=jdbc:postgresql://db.local/shop?user=svc&password=<PASSWORD>
~~~

Các chuỗi trong dấu ngoặc chỉ là placeholder giả minh họa vị trí dữ liệu nhạy cảm; chúng **không phải credential thật**.

Hậu quả có thể bao gồm:

- Người đọc log dùng token để gọi API hoặc giả mạo session trong thời gian token còn hiệu lực.
- API key của đối tác bị lộ và có thể bị sử dụng ngoài ý muốn.
- Connection string giúp truy cập database nếu credential còn hiệu lực.
- Private key có thể bị dùng để ký dữ liệu hoặc giải mã tùy mục đích key.
- Log được index/back up trong nhiều ngày, kể cả sau khi ứng dụng đã sửa code.
- Người tải CSV, đính kèm log vào ticket hoặc gửi chat tạo thêm bản sao không còn nằm trong quyền kiểm soát của vault.

MITRE phân loại lỗi đưa dữ liệu nhạy cảm vào log là **CWE-532**. OWASP khuyến nghị không ghi trực tiếp password, session identifier, access token, encryption key, connection string và nhiều loại dữ liệu nhạy cảm khác.

## 3. Phân loại: secret khác gì dữ liệu cá nhân?

| Nhóm | Ví dụ | Cách xử lý đề xuất |
| --- | --- | --- |
| **Credential** | Password, access token, refresh token, API key, session cookie | Không log giá trị thô. |
| **Cryptographic secret** | Private key, HMAC key, signing key, encryption key | Không log giá trị; xem cả bản backup/export là tài sản nhạy cảm. |
| **Credential cấu hình** | JDBC URL có password, DSN, cloud service account JSON | Chỉ log tên dependency và error code đã chuẩn hóa. |
| **One-time secret** | OTP, password reset token, magic login link | Không log; thời gian sống ngắn không làm mất rủi ro. |
| **PII** | Email, số điện thoại, user ID, địa chỉ, thông tin sức khỏe | Tối thiểu hóa, mask/pseudonymize theo chính sách, phân quyền đọc. |
| **Business confidential** | Số liệu kinh doanh, hợp đồng, giao dịch | Phân loại dữ liệu và mục đích ghi trước khi phát event. |
| **Safe diagnostic** | Event name, status, route template, error code, duration | Thường hữu ích hơn raw payload; vẫn validate input và giới hạn phạm vi. |

Không mặc định mọi user ID là secret xác thực, nhưng nhiều định danh vẫn có thể là **dữ liệu cá nhân**. Hash cũng không tự biến một giá trị thành vô hại: hash có thể bị dò nếu giá trị gốc ít entropy hoặc bị dùng để liên kết hoạt động nhiều lần.

Thực hành tốt là **ghi sự kiện dùng secret** thay vì **giá trị secret**:

~~~text
INFO event=secret.accessed workload=orders-service secret_ref=db-primary result=ALLOW
INFO event=secret.rotated secret_ref=payment-provider-key result=SUCCESS
WARN event=secret.access.denied workload=unknown-service reason=POLICY_DENIED
~~~

Đây là event mẫu. **secret_ref** là tên logic được phép công khai trong phạm vi log, không phải key. Ngay cả secret name hoặc vault path đôi khi cũng cần kiểm soát theo chính sách nội bộ.

## 4. Anti-pattern: log password/token trực tiếp

Mẫu Java không an toàn:

~~~java
// SAI: snippet minh họa trong ứng dụng có SLF4J.
log.info("Login username={} password={}", username, password);
log.debug("Outbound Authorization={}", bearerToken);
log.error("Payment API key={}", paymentApiKey);
~~~

**Placeholder của SLF4J không tự che secret.** Nó chỉ giúp định dạng message và thường tránh một số công việc string concatenation khi level bị tắt. Khi event được ghi, giá trị truyền vào vẫn có thể xuất ra console, file hoặc structured encoder.

Mẫu thay thế:

~~~java
// Minh họa; requestId đã được validate ở boundary.
log.info("event=auth.attempt request_id={}", requestId);
log.warn("event=auth.result request_id={} result={} reason={}",
        requestId, "DENIED", "BAD_CREDENTIALS");
~~~

Điều cần biết là **một lần xác thực bị từ chối**, chứ không phải người dùng đã gửi password/token gì. Nếu muốn phân tích cơ chế xác thực, ghi **auth_method=PASSWORD/OAUTH2** theo enum an toàn.

**Không dùng cách ghi bốn ký tự đầu/cuối API key như mặc định.** Prefix/suffix có thể tiết lộ nhà cung cấp, tenant hoặc hỗ trợ tấn công trên một giá trị có cấu trúc. Nếu thực sự cần định danh key, dùng **opaque secret ID** do hệ thống quản lý cấp hoặc một fingerprint được thiết kế, phê duyệt và bảo vệ riêng. Không tự băm password bằng SHA-256 rồi log hash với giả định rằng nó không còn nhạy cảm.

## 5. Anti-pattern: log toàn bộ HTTP headers

Các header thường chứa bí mật:

- **Authorization** và **Proxy-Authorization**.
- **Cookie**, **Set-Cookie**, session identifiers.
- **X-API-Key** và các custom credential headers.
- Header chứa chữ ký, bearer token, one-time code hoặc partner secret.

Ví dụ không an toàn:

~~~java
// SAI: minh họa trong một Servlet Filter.
request.getHeaderNames().asIterator().forEachRemaining(name ->
        log.debug("header {}={}", name, request.getHeader(name)));
~~~

Nếu DEBUG bật, đoạn trên có thể ghi raw cookie/token. Denylist chỉ che tên **Authorization** không đủ: một đối tác có thể đưa credential vào header riêng.

**Ưu tiên allowlist** các trường thật sự phục vụ vận hành:

~~~text
event=http.request.received
method=POST
route=/orders
request_id=req-204
content_type=application/json
~~~

Ngay cả requestId và các field tưởng an toàn vẫn cần validation và size limit. Không log raw body, toàn bộ header map hoặc các giá trị do client khai khi chưa kiểm soát.

### 5.1. Body và response

Body có thể chứa password, OTP, client_secret, refresh token hoặc dữ liệu cá nhân. Response cũng có thể chứa token mới cấp sau đăng nhập hoặc link reset password. Một filter tự động log toàn bộ request và response ở DEBUG là rủi ro lớn.

**Truncate body không tương đương redaction.** Nếu secret nằm trong 100 byte đầu, việc chỉ in 100 byte đầu vẫn lộ. Chọn metadata hữu ích như method, route template, status, payload size và safe validation error code thay vì body.

## 6. Anti-pattern: log raw URL/query string

Ví dụ những URL cần thận trọng:

~~~text
GET /password-reset?token=<ONE_TIME_SECRET>
GET /callback?code=<AUTH_CODE>
GET /download?signature=<SIGNED_VALUE>
~~~

Một số thư viện hoặc error handler tự thêm full URL vào exception message. Reverse proxy/gateway access log cũng có thể ghi query string dù ứng dụng Java không trực tiếp log.

**Phương án tốt:** dùng route template:

~~~text
method=GET route=/password-reset status=400
method=GET route=/download status=200
~~~

Không coi URL encoding, base64 hoặc JWT encoding là mã hóa bảo vệ. Chúng không làm credential mất giá trị sử dụng.

Với kết nối database, không log trọn JDBC URL hoặc **DataSource.toString()** nếu chưa biết có credential nào trong đó:

~~~text
WARN event=db.connection.failed datasource=orders-primary error_type=SQLTransientConnectionException
~~~

Đây là event minh họa: datasource là tên logic, error_type là loại lỗi được duyệt, không phải raw connection string.

## 7. Anti-pattern: log nguyên DTO, Map hoặc Java record

Một ví dụ dễ gây lỗi:

~~~java
// Minh họa kiểu record nhạy cảm.
record LoginRequest(
        String username,
        String password,
        String accessToken) {
}

// SAI nếu LoginRequest chứa credential:
log.debug("request={}", loginRequest);
~~~

Java record có **toString() sinh tự động** mô tả các components. Khi logger format object, password/accessToken có thể đi vào message. POJO với Lombok **@Data/@ToString**, collections, Map và nested objects cũng có rủi ro tương tự.

Tránh:

~~~java
// SAI: request thường chứa nested dữ liệu nhạy cảm.
log.info("incomingRequest={}", requestDto);
log.debug("context={}", requestAttributes);
~~~

Thay bằng event có allowlisted fields:

~~~java
// Minh họa: operationId đã được validate.
log.info("event=login.request.received operation_id={}", operationId);
~~~

**Annotation dùng để ẩn trường khi Jackson serialize JSON không bảo đảm Java toString hoặc một logging backend khác cũng ẩn trường đó.** Nếu cấu hình toString safe cho DTO, coi đó là biện pháp bổ sung chứ không phải lý do để log toàn bộ DTO.

Nested maps/objects rất khó rà soát khi schema thay đổi. Allowlist các fields được phép ghi thường an toàn hơn "log hết rồi dùng denylist xóa một số tên".

## 8. Anti-pattern: exception message và stack trace

Nhiều Throwable từ thư viện HTTP/database có message chứa URL, response body, request parameter hoặc credential. Một đoạn tưởng đúng:

~~~java
// RỦI RO nếu Throwable chứa secret trong message hoặc cause chain.
catch (RuntimeException ex) {
    log.error("Remote dependency failed", ex);
    throw ex;
}
~~~

Khi backend ghi Throwable, message và cause chain có thể xuất hiện trong stack trace. Nếu dữ liệu nhạy cảm nằm ở đó, nó có thể bị lộ. Ngoài ra, log rồi rethrow ở nhiều tầng gây **stack trace trùng**, tăng phạm vi phát tán.

Không phải mọi stack trace đều nguy hiểm hay cần tắt. Mục tiêu là:

1. Không đưa secret vào exception **ở nơi exception được tạo**.
2. Tránh truyền URL/header/body thô vào exception message.
3. Dùng safe **error code, dependency name, error type, trace ID** để gỡ lỗi.
4. Chỉ log Throwable tới nơi đã kiểm soát dữ liệu và quyền truy cập.
5. Dùng redaction ở encoder/collector như lớp bổ sung.
6. Chọn **một boundary sở hữu terminal error log**, tránh log-and-rethrow lặp.

Nếu nguyên nhân lỗi chứa raw token chưa thể bảo đảm an toàn, có thể ghi:

~~~text
ERROR event=payment.dependency.failed dependency=payment-gateway error_type=SocketTimeoutException request_id=req-17
~~~

thay vì nguyên văn Throwable message. Với hệ thống thực, để giữ thông tin điều tra, hãy sửa nguồn tạo exception hoặc thiết kế safe exception/wrapper; đừng xóa hết stack trace của mọi lỗi chỉ vì sợ bị leak.

## 9. Anti-pattern: MDC và structured logging mang secret

SLF4J MDC và Log4j2 ThreadContext có thể được đưa vào mọi log event bằng pattern hoặc JSON layout.

~~~java
// SAI: minh họa trong ứng dụng dùng SLF4J.
MDC.put("accessToken", accessToken);
~~~

Từ đây, một log đơn giản như "Service started" có thể chứa accessToken nếu layout xuất MDC. Không đặt password, bearer token, cookie hoặc raw request body vào MDC.

Chỉ đưa context an toàn và được kiểm soát:

~~~java
// Minh họa: cần SLF4J, service và requestId hợp lệ.
try {
    MDC.put("requestId", requestId);
    service.process();
} finally {
    MDC.remove("requestId");
}
~~~

Trong xử lý async, MDC có thể không được propagate qua ExecutorService/CompletableFuture/Reactor hoặc có thể bị sót trên thread được tái sử dụng. Cần kiểm thử context propagation và cleanup đúng cơ chế framework.

**Structured logging cũng có thể chứa secret.** Một JSON field có tên token mà value là raw token vẫn là lỗi, dù JSON escaping hoàn hảo.

## 10. Anti-pattern: dump config hoặc environment

Khi startup lỗi, đôi khi developer in toàn bộ config:

~~~java
// SAI khi môi trường có bí mật.
System.out.println(System.getenv());
System.out.println(System.getProperties());
~~~

Environment variables, Java system properties, startup arguments và cấu hình dependency có thể chứa API keys, database passwords, signing keys hoặc auth tokens. CI logs, deploy logs, crash diagnostics và service startup logs đều có thể trở thành nơi phát tán.

Ví dụ tốt hơn:

~~~text
INFO event=service.started profile=prod config_version=v42
WARN event=config.invalid component=datasource reason=MISSING_REQUIRED_PROPERTY
~~~

Ghi **component và loại lỗi**, không ghi raw value của secret. Ngay cả một property key hoặc secret path cũng cần được phân loại theo môi trường.

### 10.1. Debug/trace của thư viện

Bật DEBUG/TRACE cho Spring Security, HTTP client, SQL/JDBC driver, ORM, OAuth SDK hoặc RPC library có thể phát ra header, URL, payload hoặc câu truy vấn kèm tham số. Không mặc định mọi thư viện đều an toàn khi bật verbose logging.

Kiểm tra cả những đường gián tiếp:

- Request/response logging filters.
- HTTP wire logging.
- SQL parameter binding logs.
- OAuth token exchange diagnostics.
- Message broker body logs.
- Framework validation/binding errors.
- Third-party SDK exception handlers.

Tắt DEBUG production là một **lớp giảm phơi bày**, không thay cho việc bảo vệ ngay tại source.

## 11. Thiết kế safe log event

Thay vì đưa object/request thô vào logger, tạo event từ **allowlist**:

~~~text
Request có username/password/token
            |
            v
        Business logic
            |
            v
Safe event:
    event=auth.login.result
    request_id=req-17
    auth_method=PASSWORD
    outcome=DENIED
    reason_code=BAD_CREDENTIALS
            |
            v
Encoder có cấu trúc + escaping
            |
            v
Appender / collector
            |
            v
Storage có RBAC, retention, audit
~~~

Các trường tốt để cân nhắc:

| Trường | Lợi ích | Điều kiện |
| --- | --- | --- |
| **event** | Dễ truy vấn và alert. | Tên cố định, không lấy từ input tùy ý. |
| **request_id / trace_id** | Liên kết các event. | Đã validate, không dùng secret làm ID. |
| **outcome** | SUCCESS, DENIED, ERROR. | Dựa vào kết quả thật, không đoán trước. |
| **error_code** | Phân loại lỗi ổn định. | Không dùng raw exception message. |
| **dependency** | Định vị nguồn lỗi. | Tên logic được phép chia sẻ. |
| **duration_ms** | Phân tích độ trễ. | Đo thời lượng bằng monotonic clock khi phù hợp. |
| **http.route / status** | Phân tích HTTP. | Dùng route template, status thật ở boundary. |

Nếu cần correlation một key, dùng **secret ID do vault cấp** hoặc cơ chế định danh đã được thiết kế và phê duyệt, không log key prefix hoặc hash tùy ý.

### 11.1. Allowlist tốt hơn chỉ dùng denylist

Denylist có thể xóa các field tên password/token nhưng bỏ sót tên mới như client_secret, x-api-key, auth_assertion, credential, signedUrl, refreshToken. Regex redaction có thể bỏ sót secret được encode hoặc nằm trong message không theo schema.

Allowlist giúp kiểm soát số field được phép đi vào log. Có thể bổ sung **redaction ở encoder/collector** để giảm rủi ro từ những code paths bên ngoài, nhưng không thể bảo đảm chỉ bằng một regex.

### 11.2. Encode và chống log injection

Dữ liệu không tin cậy có thể chứa CR/LF, dấu phân cách hoặc ký tự điều khiển, gây **log forging** ở text layout. Dùng structured JSON encoder và validate các ID; không tự nối chuỗi JSON bằng tay.

Bảo vệ secret và chống log injection là hai mối quan tâm khác nhau, đều cần kiểm tra trên đường từ Java tới backend.

## 12. Java 17 chạy độc lập: kiểm tra rằng secret không xuất hiện trong log

Ví dụ dưới đây dùng **java.util.logging (JUL)** có sẵn trong JDK 17. Chương trình tạo một LoginAttempt chứa password/token giả nhưng **không log object, message exception hoặc giá trị credential**. Nó dùng **CaptureHandler** lưu các LogRecord, kiểm tra điều kiện bảo mật rồi mới in các safe events ra stdout.

Không có network, file hay dependency ngoài; đây là **mô phỏng logging**, không phải một hệ thống authentication thật.

### 12.1. File SafeSecretLoggingDemo.java

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class SafeSecretLoggingDemo {

    private static final Logger LOG =
            Logger.getLogger("demo.security.AuthService");

    record LoginAttempt(
            String requestId,
            String username,
            String password,
            String accessToken) {
    }

    static final class CaptureHandler extends Handler {
        private final List<String> events = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                events.add(record.getLevel().getName()
                        + " " + record.getMessage());
            }
        }

        @Override
        public void flush() {
            // Khong can I/O trong demo.
        }

        @Override
        public void close() {
            // Khong co tai nguyen ngoai.
        }

        List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    static String safeRequestId(String raw) {
        if (raw != null && raw.matches("[A-Za-z0-9_-]{1,36}")) {
            return raw;
        }
        return "invalid";
    }

    static void authenticationResult(
            LoginAttempt attempt, boolean authenticated) {
        String requestId = safeRequestId(attempt.requestId());
        LOG.info("event=auth.attempt request_id=" + requestId);
        LOG.info("event=auth.result request_id=" + requestId
                + " outcome="
                + (authenticated ? "SUCCESS" : "DENIED"));
    }

    static void dependencyFailed(
            LoginAttempt attempt, RuntimeException error) {
        // Khong log exception message vi co the chua token.
        LOG.warning("event=auth.dependency_failed request_id="
                + safeRequestId(attempt.requestId())
                + " error_type="
                + error.getClass().getSimpleName());
    }

    public static void main(String[] args) {
        CaptureHandler capture = new CaptureHandler();
        capture.setLevel(Level.ALL);

        Level oldLevel = LOG.getLevel();
        boolean oldParent = LOG.getUseParentHandlers();

        LOG.setLevel(Level.INFO);
        LOG.setUseParentHandlers(false);
        LOG.addHandler(capture);

        try {
            LoginAttempt attempt = new LoginAttempt(
                    "req-17",
                    "test-user@example.invalid",
                    "DUMMY_PASSWORD_DO_NOT_LOG",
                    "DUMMY_TOKEN_DO_NOT_LOG");

            authenticationResult(attempt, false);
            dependencyFailed(attempt,
                    new IllegalStateException(
                            "Bearer DUMMY_TOKEN_DO_NOT_LOG"));

            List<String> events = capture.snapshot();
            String rendered = String.join("\n", events);

            for (String forbidden : List.of(
                    attempt.username(),
                    attempt.password(),
                    attempt.accessToken(),
                    "Bearer")) {
                if (rendered.contains(forbidden)) {
                    throw new AssertionError(
                            "Sensitive value appeared in logs");
                }
            }

            if (events.size() != 3) {
                throw new AssertionError(
                        "Unexpected number of log events");
            }

            for (String event : events) {
                System.out.println(event);
            }
            System.out.println(
                    "PASS: no sensitive values in captured events");
        } finally {
            LOG.removeHandler(capture);
            capture.close();
            LOG.setUseParentHandlers(oldParent);
            LOG.setLevel(oldLevel);
        }
    }
}
~~~

### 12.2. Biên dịch và chạy

~~~bash
javac SafeSecretLoggingDemo.java
java SafeSecretLoggingDemo
~~~

**Stdout dự kiến:**

~~~text
INFO event=auth.attempt request_id=req-17
INFO event=auth.result request_id=req-17 outcome=DENIED
WARNING event=auth.dependency_failed request_id=req-17 error_type=IllegalStateException
PASS: no sensitive values in captured events
~~~

### 12.3. Giải thích

- LoginAttempt giữ password/accessToken giả nhưng logger chỉ dùng **requestId đã validate**.
- Java record có toString mặc định chứa tên và giá trị components; không gọi log.info trên toàn object.
- Exception thử có token giả trong message. Phương thức dependencyFailed chỉ log **exception class**, không log message hay Throwable thô.
- CaptureHandler lưu những event thực sự đến JUL Handler và dùng level/name/message. Chương trình so sánh output với chuỗi giả, không in raw secret khi assertion fail.
- **setUseParentHandlers(false)** ngăn event từ logger demo tiếp tục sang root ConsoleHandler.
- Code chạy tuần tự một thread, không có timestamp hoặc random trong output nên kết quả ổn định.
- **finally** tháo Handler và restore logger level/parent settings để không làm ảnh hưởng các đoạn code khác.

### 12.4. Giới hạn

Ví dụ chỉ test **JUL CaptureHandler trong RAM**. Nó không xác nhận log đã qua JSON encoder, async queue, file, Logback/Log4j2 hay collector; cũng không thực hiện authentication thực. Một backend khác có thể lưu thêm arguments, MDC, Throwable hoặc structured attributes không xuất hiện trong chuỗi getMessage.

Trong production, chỉ log exception type có thể không đủ để debug. Cần ưu tiên **loại bỏ secret khỏi nguồn exception**, hoặc tạo safe error type/cause được kiểm soát, rồi ghi diagnostics tại boundary thích hợp. Không cắt mọi stack trace một cách mù quáng.

**Không dùng credential thật trong bài test**. Sentinel values chỉ dùng để đảm bảo các đường log không làm lộ dữ liệu theo schema và sinks đã biết.

## 13. Kiểm thử chống secret leak trong dự án thực

Một bộ test tốt cần kiểm tra nhiều nguồn:

| Nguồn | Giá trị giả | Kỳ vọng |
| --- | --- | --- |
| Login DTO | DUMMY_PASSWORD_DO_NOT_LOG | Không xuất hiện trong output. |
| Authorization header | DUMMY_TOKEN_DO_NOT_LOG | Không xuất hiện ở INFO/DEBUG/TRACE. |
| Custom API-key header | DUMMY_API_KEY_DO_NOT_LOG | Không bị ghi qua header dump. |
| Session cookie | DUMMY_COOKIE_DO_NOT_LOG | Không xuất hiện ở request/response logs. |
| URL query | DUMMY_RESET_TOKEN_DO_NOT_LOG | Chỉ có route template, không raw URL. |
| Java record.toString() | DUMMY_RECORD_SECRET_DO_NOT_LOG | Không log nguyên record. |
| Exception message | DUMMY_EXCEPTION_SECRET_DO_NOT_LOG | Không xuất hiện trong rendered Throwable. |
| MDC/ThreadContext | DUMMY_MDC_SECRET_DO_NOT_LOG | Không có trong structured fields. |
| JDBC datasource | DUMMY_DB_PASSWORD_DO_NOT_LOG | Không có trong startup/error logs. |
| Debug của thư viện | DUMMY_REMOTE_TOKEN_DO_NOT_LOG | Không lộ khi bật verbose test config. |

Bật mức DEBUG/TRACE **trong môi trường thử nghiệm riêng** để test những đường có thể được operator bật khi có sự cố. Một test chỉ chạy root INFO có thể che dấu các câu lệnh debug nguy hiểm.

### 13.1. Kiểm tra positive control

Nếu logging bị tắt hoàn toàn, một test "secret không xuất hiện" có thể PASS nhưng vô nghĩa. Bắt buộc kiểm tra có ít nhất một **safe event** được ghi, như auth.result=DENIED. Demo phần 12 kiểm tra **events.size() == 3** vì lý do đó.

### 13.2. Kiểm tra nhiều phần của event

Với SLF4J + Logback, một event có thể lưu:

- Formatted message.
- Argument array.
- MDC properties.
- ThrowableProxy.
- Marker/key-value pairs.
- Các fields từ JSON encoder.

Vì vậy test chỉ kiểm tra **getFormattedMessage()** chưa chắc đủ. Cần kiểm tra **representation thực sau encoder** và các sink phù hợp. Với **Log4j2**, test ThreadContext và message/Throwable/layout tương ứng.

### 13.3. Cẩn thận với test failure message

Đừng đưa nguyên credential vào assertion expected/actual hay báo cáo CI. Nếu test phát hiện sentinel, log lỗi test nên ghi **loại dữ liệu bị lộ và vị trí event** mà không lặp lại giá trị thật.

### 13.4. Static analysis và code review

Nên kiểm tra pattern nguy hiểm:

~~~text
log.info("password={}", password)
log.debug("headers={}", requestHeaders)
log.info("dto={}", dto)
log.error("request failed: " + exception.getMessage())
MDC.put("accessToken", value)
System.out.println(System.getenv())
~~~

Một regex hoặc rule đơn giản có thể có false positive/false negative, đặc biệt khi dữ liệu đi qua helper methods. Kết hợp **code review theo data flow, CI scanning, safe logging API và integration tests**. Không khẳng định "scan không thấy key" là bằng chứng hệ thống không có CWE-532.

## 14. Lưu ý riêng theo công nghệ

### 14.1. SLF4J

- Placeholder **{}** không tự mask.
- Fluent key-value API của SLF4J 2.x cũng có thể chứa secret, chỉ khác cách tạo event.
- Logger level không đảm bảo security: DEBUG có thể được bật qua config runtime.
- Nếu dùng provider không phù hợp, output khác kỳ vọng; test trên provider thật.

### 14.2. Logback

- PatternLayout có thể in toàn bộ MDC qua **%X**.
- JSON encoder có thể serialize fields/arguments không hiện trong formatted message.
- Một masking encoder/filter ở một appender không có nghĩa mọi appender khác cũng được bảo vệ.
- AsyncAppender có thể giữ dữ liệu trong queue trước khi collector đọc.
- Cần test cả file/console/centralized layout thực.

### 14.3. Log4j2

- ThreadContext cũng có thể lưu secret.
- Message templates, custom layouts và structured logging không tự phân loại field nhạy cảm.
- Rewrite/filter/regex replacement có thể là lớp bổ sung, nhưng có giới hạn.
- Nếu có nhiều AppenderRefs, bảo đảm raw message không bypass redaction.

### 14.4. JUL

- **Logger.log(Level, String, Throwable)** gửi Throwable cho Handler/Formatter xử lý. Nếu message/cause chứa secret, formatter có thể xuất.
- ConsoleHandler thường ghi stderr, nên test chỉ chặn stdout có thể bỏ sót.
- FileHandler có rotation, nhưng dữ liệu đã ghi vào file/collector sẽ không biến mất chỉ vì ứng dụng đóng Handler.

### 14.5. Spring Boot

- Kiểm tra request/response logging filters, Spring Security debug, WebClient/HTTP client wire logging và JDBC/ORM debug.
- Không tự in request body, object.toString, environment hoặc cấu hình có credentials trong @Service.
- Bảo vệ endpoint quản trị logging nếu được bật (ví dụ Actuator loggers); việc đổi level có thể mở rộng thông tin xuất ra.
- Kiểm tra các profile dev/test/staging/prod và overrides từ env/command line.
- Không dùng việc framework che một số property trên management endpoint làm bằng chứng mọi logging path đều an toàn.

## 15. Log pipeline và nơi secret có thể bị nhân bản

~~~text
Java application
       |
       +-- stdout/stderr hoặc file
       |
       +-- container runtime logs
       |
       +-- log shipper/collector buffers
       |
       +-- centralized log index
       |
       +-- dashboard / saved query
       |
       +-- CSV export / backup / archive
       |
       +-- ticket / chat / local download
~~~

Nếu secret đã ghi ở tầng nguồn, một collector redact dữ liệu trước khi export **không tự xóa bản raw trong file/stdout**. Che dữ liệu ở viewer không chứng minh raw API/export đã được che. Mã hóa at-rest và TLS bảo vệ disk/network, nhưng người có quyền query plaintext vẫn có thể đọc và sao chép.

Nên quản lý:

- **VIEW/QUERY/EXPORT/SHARE** như những quyền riêng.
- Tenant/environment isolation và least privilege.
- Retention phù hợp và xử lý backup.
- Audit truy cập/export dữ liệu nhạy cảm.
- Chỉ sử dụng debug exporter trong môi trường an toàn.
- Không gửi raw secret qua support ticket hoặc chat.

## 16. Khi đã lộ secret trong log: quy trình xử lý

Không chỉ sửa code rồi coi sự cố kết thúc. Secret có thể đã được đọc và nhân bản.

### Bước 1 — Khoanh vùng

Xác định loại credential, application, version, environment, timestamp, những sinks đã nhận log và quyền truy cập liên quan. Ghi mã sự cố và metadata; **không copy nguyên secret vào ticket hoặc thông báo nhóm**.

### Bước 2 — Giảm rủi ro hiện tại

Đánh giá **revoke/rotate** token, API key, session hoặc private key theo chính sách sự cố. Với session cookie có thể cần invalidate session; với API key có thể phải phát hành key mới và cập nhật các workloads an toàn; với private key cần đánh giá downstream trust/signatures.

Không mặc định credential đã hết hạn nghĩa là chưa ai dùng nó trong cửa sổ trước đó.

### Bước 3 — Chặn nguồn phát mới

Sửa logging ở nguồn, kiểm soát debug flags/SDK, thêm allowlist, loại DTO raw và exception message có secret. Test với sentinel ở những code paths tương ứng.

### Bước 4 — Kiểm soát bản sao

Kiểm tra local file, container logs, collector, index, backup, archive, CSV export, ticket/chat attachments. Hạn chế quyền đọc khi cần và thực hiện redaction/purge theo quy trình được phê duyệt; lưu ý **legal hold, audit integrity và retention**.

**Không xóa bừa audit trail hoặc chứng cứ** làm mất khả năng điều tra. Một số bản sao không thể xóa ngay phải được ghi nhận và có biện pháp giảm rủi ro.

### Bước 5 — Đánh giá sử dụng và tái diễn

Đối chiếu audit truy cập log với audit sử dụng credential trong khoảng thời gian liên quan. Xác định người dùng/tenant bị ảnh hưởng, áp dụng quy trình thông báo/tuân thủ nếu cần. Thêm regression tests và review chính sách log ở những thư viện tương tự.

## 17. Các sai lầm thường gặp

1. **Placeholder SLF4J tự che token** — sai, nếu argument là token thì vẫn có thể được in.
2. **Chỉ DEBUG mới có secret** — sai; INFO/WARN/ERROR cũng có thể lộ.
3. **Tắt DEBUG production là đủ** — sai, level có thể bật khi debug sự cố.
4. **Log toàn bộ headers cho tiện** — Authorization/Cookie/custom API keys có thể bị lộ.
5. **Truncate body là đã bảo vệ** — secret có thể nằm ở đầu body.
6. **URL chỉ là metadata** — query có thể chứa signed URL/reset token.
7. **Java record.toString() luôn an toàn** — nó có thể liệt kê toàn bộ components.
8. **JSON annotation che luôn Lombok/toString** — mỗi serializer có cơ chế riêng.
9. **Exception.getMessage() luôn vô hại** — nó có thể chứa URL, headers, SQL parameters.
10. **Có MDC thì cứ đặt token để dễ tìm** — token có thể bị xuất trong mọi event.
11. **Logback JSON encoder tự redact** — structured format không đảm bảo chính sách bảo mật.
12. **Regex masking tìm được mọi secret** — không thể bảo đảm với biến thể mới.
13. **Hash token rồi log là chắc an toàn** — có thể có nguy cơ dò/ liên kết dữ liệu.
14. **Đã redact ở collector thì file nguồn sạch** — raw data có thể tồn tại trước collector.
15. **Đã mã hóa log thì người đọc dashboard không thấy** — API có thể giải mã cho họ.
16. **Xóa một dòng log là đủ xử lý incident** — secret cần revoke/rotate và xử lý bản sao.
17. **Test không thấy token khi logger tắt nghĩa là PASS** — phải có positive control.
18. **Dùng secret thật để test** — chính CI log/artifacts có thể thành nơi lộ.
19. **Không kiểm tra exception cause chain** — một secret có thể nằm ở nested Throwable.
20. **Chỉ test console** — file, collector và export có thể chứa bản khác.

## 18. Checklist review trước release

- [ ] Event name, purpose, severity và field allowlist rõ ràng.
- [ ] Không có password, API key, token, cookie, key material, OTP trong message/attributes/MDC.
- [ ] Không ghi raw headers/body/URL/query trừ khi được phân loại và bảo vệ đặc biệt.
- [ ] Không log nguyên DTO, Java record, map hoặc nested object chứa credentials.
- [ ] Exception message/cause chain từ thư viện đã được đánh giá.
- [ ] Configuration dump và library DEBUG/TRACE đã được kiểm soát.
- [ ] Structured encoder và escaping được test với CR/LF, Unicode, input dài.
- [ ] Test dùng sentinel fake secrets, có positive control và kiểm tra mọi level liên quan.
- [ ] Test kiểm tra JSON formatted output, MDC, arguments, Throwable và sinks quan trọng.
- [ ] Không dùng credential thật và không đưa secret vào test failure reports.
- [ ] Log storage có RBAC/ABAC, TLS, retention, audit và quyền export riêng.
- [ ] Nếu từng có leak, có quy trình revoke/rotate, quản lý bản sao và hậu kiểm.

## 19. Bài tập tự luyện

1. Chạy **SafeSecretLoggingDemo.java**, giải thích vì sao LoginAttempt chứa token nhưng log không chứa token.
2. Dự đoán rủi ro nếu thêm **LOG.info(attempt.toString())** vào chương trình thử nghiệm; giải thích Java record toString.
3. Mở rộng safeRequestId để chỉ cho phép tiền tố req- và các ký tự hợp lệ, rồi test input CR/LF.
4. Thiết kế safe event cho một lỗi gọi OAuth provider mà exception message có access token.
5. Một filter log tất cả HTTP headers ở DEBUG: xây dựng allowlist metadata được phép.
6. Tạo integration test cho Logback JSON encoder, kiểm tra cả formatted message, MDC, structured arguments và Throwable.
7. Một URL reset password có token trong query: thiết kế log route template thay thế.
8. Một API key thật bị log trong production: xây dựng runbook revoke/rotate, xử lý backup, audit và thông báo.
9. Giải thích vì sao masking ở dashboard không bảo vệ raw export/API.
10. Đưa ra test bật DEBUG/TRACE trong môi trường cô lập mà vẫn chứng minh không lộ sentinel secret.

## 20. Kết luận

**Log bí mật là lỗi thiết kế logging, không đơn thuần là lựa chọn format hay mức log.** Secret có thể lọt vào log trực tiếp hoặc gián tiếp qua headers, URL, DTO.toString, Java record, exception, MDC, config dump và thư viện bên thứ ba. Sau khi event phát ra, nó có thể được sao chép tới nhiều nơi với quyền đọc rộng hơn quyền secret gốc.

Biện pháp ưu tiên là **không ghi secret tại nguồn**, sử dụng **safe events và allowlist fields**, test với **dummy sentinel values** ở các mức logging có thể được bật, và quản trị quyền đọc/vận chuyển/lưu giữ. Redaction, TLS, encryption và RBAC là các lớp hỗ trợ chứ không thay thế data minimization.

Khi secret thật đã xuất hiện trong log, hãy xử lý như sự cố có khả năng lộ credential: **khoanh vùng, revoke/rotate theo rủi ro, xử lý các bản sao, kiểm tra audit và bổ sung regression tests**.

### Tài liệu tham khảo chính thức

- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- MITRE CWE-532 — Insertion of Sensitive Information into Log File: https://cwe.mitre.org/data/definitions/532.html
- OWASP DevSecOps — Logging and Monitoring: https://owasp.github.io/DevSecOpsGuideline/2-Process/2-7-Operate/2-7-2-Logging-and-Monitoring/
- Oracle Java 17 Record Classes: https://docs.oracle.com/en/java/javase/17/language/records.html
- Oracle Java 17 Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Oracle Java 17 Handler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html
- SLF4J Manual: https://www.slf4j.org/manual.html
- Spring Boot Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- Logback Manual: https://logback.qos.ch/manual/index.html
- OpenTelemetry Logs Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/