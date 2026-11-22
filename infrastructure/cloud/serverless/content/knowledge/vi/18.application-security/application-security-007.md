# Che dữ liệu nhạy cảm trong log, trace và thông báo lỗi

Log, distributed trace và thông báo lỗi giúp nhóm vận hành hiểu một Java function serverless đã nhận request nào, đi qua những service nào và thất bại ở đâu. Nhưng cùng các kênh đó cũng có thể làm lộ access token, cookie, connection string, dữ liệu cá nhân, nội dung message hoặc chi tiết nội bộ của hệ thống. Một dòng log thường được sao chép sang nhiều nơi như log aggregator, dashboard, alert, ticket và hệ thống phân tích; một trace có thể được chia sẻ với nhiều team hoặc nhà cung cấp quan sát.

Vì vậy, bảo mật telemetry cần được thiết kế ngay trong ứng dụng. Mục tiêu là giữ đủ thông tin để điều tra và đo độ tin cậy, đồng thời chỉ thu thập dữ liệu cần thiết, giới hạn người được xem và kiểm soát thời gian lưu. Việc chỉ xóa password khỏi một vài log statement là chưa đủ nếu framework tự động ghi header, exception message, request body hoặc span attribute.

Trong module **CLOUD_SERVERLESS**, người học xây dựng Java function kích hoạt bởi HTTP, message hoặc event và xử lý quyền truy cập, trạng thái, retry, idempotency, cold start, mở rộng và chi phí. Bài này tập trung vào cách bảo vệ dữ liệu nhạy cảm trong log, trace và error response của function cùng các dịch vụ mà function gọi.

## 1. Vì sao telemetry có thể trở thành kênh rò rỉ dữ liệu?

Một request đi qua serverless system có thể tạo ra nhiều bản ghi:

- API gateway ghi access log và một phần request metadata.
- Runtime ghi invocation ID, duration, memory và exception.
- Ứng dụng ghi log nghiệp vụ.
- OpenTelemetry tạo span và event cho từng dependency.
- HTTP client hoặc SDK ghi request/response khi bật debug.
- Queue consumer ghi metadata của message, retry count và dead-letter reason.
- Error handler trả thông báo cho client.
- Alerting system đưa một phần log hoặc exception vào email, chat hoặc ticket.

Một giá trị nhạy cảm có thể bị sao chép vào nhiều hệ thống mà lập trình viên không nhìn thấy trong source code. Ví dụ, một exception của HTTP client có thể chứa URL đầy đủ với query string; một lỗi database có thể chứa SQL hoặc tên schema; một webhook có thể chứa email và địa chỉ trong payload.

Telemetry thường có quyền truy cập rộng hơn database nghiệp vụ vì nhiều người cần xem để hỗ trợ production. Nếu dữ liệu nhạy cảm đi vào telemetry, phạm vi người có thể truy cập dữ liệu đó sẽ tăng lên và retention của dữ liệu có thể khác với chính sách của database.

~~~mermaid
flowchart TD
    A[HTTP request / queue message] --> B[Java function]
    B --> C[Application logs]
    B --> D[OpenTelemetry spans]
    B --> E[Exception handler]
    C --> F[Log platform]
    D --> G[Trace backend]
    E --> H[Client error response]
    F --> I[Search / alert / ticket]
    G --> I
    H --> J[Client and support record]
~~~

Log và trace là kho dữ liệu cần được bảo vệ. Error response cũng là đầu ra công khai của ứng dụng, nên phải được thiết kế theo nguyên tắc không tiết lộ chi tiết nội bộ.

## 2. Phân loại dữ liệu trước khi ghi

Trước khi chọn field nào được log, hãy phân loại dữ liệu theo mức độ nhạy cảm và mục đích sử dụng.

| Nhóm dữ liệu | Ví dụ | Cách xử lý telemetry |
|---|---|---|
| Public | Tên service, phiên bản API công khai | Có thể ghi nếu cần |
| Operational metadata | Function name, route template, status code, duration, region | Ghi theo allowlist |
| Internal identifiers | Invocation ID, correlation ID, resource ID | Chỉ ghi khi cần; kiểm soát khả năng liên kết |
| Personal data | Email, số điện thoại, địa chỉ, IP, user ID | Tránh ghi; nếu cần thì giảm định danh hoặc pseudonymize |
| Authentication data | Password, access token, refresh token, cookie, API key | Không ghi |
| Financial/regulated data | Số thẻ, tài khoản, hồ sơ nhạy cảm | Không ghi payload; chỉ ghi kết quả và mã tham chiếu an toàn |
| Infrastructure secrets | Connection string, private key, SAS/presigned URL | Không ghi |
| Business payload | Nội dung đơn hàng, webhook body, message body | Chỉ ghi metadata tối thiểu |

Phân loại phải bao gồm dữ liệu do người dùng gửi, dữ liệu do hệ thống tạo và dữ liệu provider tự thêm. Một header như X-Forwarded-For hoặc một field trong event có thể chứa thông tin định danh dù tên field không gợi ý điều đó.

Sensitive không chỉ là password. User ID hoặc tenant ID có thể liên kết hoạt động của một người; request path có thể chứa email hoặc order ID; query string có thể chứa reset token; trace ID có thể liên kết nhiều hành động; exception message có thể chứa hostname private hoặc dữ liệu đầu vào. Không nên mặc định một field an toàn chỉ vì nó không phải password.

## 3. Data minimization và allowlist

Cách đáng tin cậy nhất để tránh log nhạy cảm là không đưa dữ liệu đó vào telemetry ngay từ đầu. Chỉ ghi field có mục đích vận hành rõ ràng.

Allowlist xác định những field được phép ghi, ví dụ:

- service name, function name và deployment version.
- Invocation ID hoặc request ID do nền tảng cấp.
- HTTP method, route template, status code và duration.
- Error code ổn định.
- Event type, schema version và queue name.
- Region và dependency name.

Denylist cố gắng liệt kê field cần loại bỏ, ví dụ password, token và cookie. Denylist dễ bỏ sót tên field mới, nested payload hoặc secret được nhúng trong URL. Vì vậy, nên dùng allowlist làm lớp chính; denylist và secret scanner là lớp phòng vệ bổ sung.

Không log toàn bộ object chỉ vì logger có thể serialize nó:

~~~java
// Không an toàn: object có thể chứa email, token, địa chỉ hoặc dữ liệu thanh toán.
logger.info("Request received: {}", request);
~~~

Thay vào đó, ghi các trường vận hành đã chọn:

~~~java
logger.info(
    "order request accepted: requestId={}, route={}, method={}",
    safeRequestId,
    "/orders",
    "POST"
);
~~~

Nếu cần biết loại request, dùng enum hoặc schema version thay vì log raw body. Nếu cần đối chiếu một bản ghi, ưu tiên một reference ID ngẫu nhiên hoặc mã tham chiếu được tạo riêng cho mục đích hỗ trợ.

Ưu tiên request ID do gateway hoặc runtime tin cậy tạo. Nếu hệ thống nhận correlation ID từ client, hãy kiểm tra định dạng, giới hạn độ dài và thay bằng ID nội bộ khi giá trị không hợp lệ; không coi ID do client gửi là danh tính đã xác thực.

## 4. Structured logging trong Java

Structured logging ghi log dưới dạng field có cấu trúc, thường là JSON, thay vì ghép một chuỗi tự do. Cấu trúc giúp query, filter và dashboard dễ hơn; đồng thời tạo điểm kiểm soát rõ ràng cho dữ liệu nào được phép xuất hiện.

Ví dụ event JSON:

~~~json
{
  "timestamp": "2026-11-17T10:15:30Z",
  "level": "INFO",
  "service": "orders-function",
  "function": "CreateOrder",
  "request_id": "req-7f2c",
  "route": "/orders",
  "method": "POST",
  "status_code": 202,
  "duration_ms": 34,
  "event": "order_request_accepted"
}
~~~

Ví dụ này chỉ chứa metadata. Không có request body, Authorization header, cookie, email hay địa chỉ khách hàng.

### Dùng SLF4J với field an toàn

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderFunction {
    private static final Logger log =
            LoggerFactory.getLogger(OrderFunction.class);

    public Response handle(Request request) {
        String requestId = safeRequestId(request.requestId());

        log.info(
            "request accepted request_id={} route={} method={}",
            requestId,
            "/orders",
            "POST"
        );

        return process(request);
    }

    private static String safeRequestId(String value) {
        if (value == null || !value.matches("[A-Za-z0-9_-]{1,64}")) {
            return "unavailable";
        }
        return value;
    }
}
~~~

SLF4J placeholder giúp tránh nối chuỗi thủ công, nhưng không tự redaction dữ liệu. Nếu truyền object nhạy cảm vào placeholder, logger vẫn có thể gọi toString() và ghi toàn bộ nội dung.

### Tránh log injection

Khi ghi giá trị do client kiểm soát, kẻ tấn công có thể chèn ký tự xuống dòng hoặc control character để tạo log entry giả, làm sai lệch điều tra. Structured JSON encoder chuẩn sẽ escape ký tự theo định dạng, nhưng ứng dụng vẫn cần giới hạn độ dài và loại bỏ control character không cần thiết.

~~~java
static String safeSingleLine(String value, int maxLength) {
    if (value == null) {
        return "unavailable";
    }

    String normalized = value
            .replace('\r', ' ')
            .replace('\n', ' ')
            .replace('\t', ' ');

    StringBuilder result = new StringBuilder();
    normalized.codePoints()
            .filter(cp -> !Character.isISOControl(cp))
            .limit(maxLength)
            .forEach(result::appendCodePoint);

    return result.toString();
}
~~~

Hàm này chỉ làm sạch một giá trị text ngắn. Không dùng nó để biến payload tùy ý thành dữ liệu an toàn; payload phải được loại khỏi log hoặc xử lý theo schema riêng.

## 5. Không log header, query string và URL đầy đủ

HTTP request có thể chứa secret ở nhiều vị trí:

- Authorization bearer token.
- Cookie và Set-Cookie.
- X-Api-Key hoặc header do ứng dụng tự định nghĩa.
- Query parameter như token, code, sig hoặc password.
- Signed URL của object storage.
- URL có username/password hoặc query chứa credential.

Một URL đầy đủ đôi khi chứa SAS token, presigned signature hoặc reset token. Do đó, không ghi request URL kèm query string theo mặc định.

Hãy log route template và method:

~~~text
method=GET
route=/customers/{customerId}/orders
status=200
~~~

Thay vì ghi URL thực tế có path identifier hoặc query token. Nếu cần debug query, chỉ log tên parameter được allowlist và không log value nhạy cảm. Không log tất cả header rồi mới cố gắng che một số header bằng regex.

Forwarded headers như X-Forwarded-For, Forwarded và X-Real-IP có thể bị client giả mạo nếu request không đi qua proxy tin cậy hoặc proxy không ghi đè header. Không dùng chúng làm danh tính xác thực. Nếu IP cần cho security telemetry, lấy từ metadata do gateway tin cậy cung cấp, chuẩn hóa theo chuỗi proxy và áp dụng chính sách privacy/retention.

## 6. Masking, redaction và pseudonymization

Ba cách xử lý thường được dùng:

- **Masking:** thay một phần giá trị để người xem chỉ nhận ra một phần, ví dụ ***@example.com.
- **Redaction:** loại bỏ giá trị và thay bằng nhãn như [REDACTED].
- **Pseudonymization:** thay định danh bằng một giá trị giả ổn định để có thể liên kết bản ghi mà không lưu trực tiếp định danh gốc.

Redaction phù hợp với token, password, cookie và secret. Masking chỉ phù hợp khi phần còn lại vẫn không làm lộ danh tính ngoài mục đích được chấp thuận. Pseudonymization hữu ích khi cần điều tra chuỗi sự kiện của cùng một subject mà không ghi user ID/email thật.

### Hash không đồng nghĩa ẩn danh

Hash email hoặc số điện thoại bằng SHA-256 không tự động làm dữ liệu vô danh. Kẻ tấn công có thể thử từ điển các giá trị phổ biến rồi so sánh hash. Nếu cần correlation, dùng HMAC với secret key được quản lý riêng, có version và rotation:

~~~java
String pseudonym = hmacSha256(activeKey, normalizedCustomerId);
~~~

Đây là pseudocode: activeKey phải đến từ secret manager hoặc KMS-backed mechanism; không hardcode key trong source hoặc log. Không dùng cùng một key cho mọi mục đích. Nếu không cần correlation ổn định, tạo random reference ID theo request sẽ giảm khả năng liên kết giữa các hoạt động.

## 7. Tạo một lớp logging an toàn

Một cách thực tế là tạo API logging chỉ nhận những trường đã được duyệt, thay vì cho mọi handler tự log object bất kỳ.

~~~java
public record SafeRequestContext(
        String requestId,
        String route,
        String method,
        String functionName,
        String region) {
}

public final class SafeLog {
    private SafeLog() {}

    public static void requestAccepted(
            Logger logger,
            SafeRequestContext context) {

        logger.info(
            "request_accepted request_id={} route={} method={} function={} region={}",
            context.requestId(),
            context.route(),
            context.method(),
            context.functionName(),
            context.region()
        );
    }

    public static void operationFailed(
            Logger logger,
            SafeRequestContext context,
            String errorCode,
            String exceptionType) {

        logger.error(
            "operation_failed request_id={} route={} error_code={} exception_type={}",
            context.requestId(),
            context.route(),
            errorCode,
            exceptionType
        );
    }
}
~~~

Điểm quan trọng là SafeRequestContext không chứa request body, token hoặc dữ liệu khách hàng. Route nên là route template do router cung cấp, không phải path tùy ý từ request.

Một wrapper không thể bảo đảm an toàn nếu caller vẫn có thể truyền object tùy ý. Có thể tăng độ an toàn bằng cách dùng type riêng cho field đã được phê duyệt, code review logging helper, cấm log raw request/response và exception object trong production, dùng static analysis để tìm logger gọi với request/headers/payload/token, và chạy secret scanner trên log sample.

## 8. Quản lý MDC và context trong function

Mapped Diagnostic Context (MDC) của SLF4J/Logback cho phép gắn request ID hoặc trace ID vào nhiều log statement mà không truyền tham số lặp lại.

~~~java
import org.slf4j.MDC;

public Response handle(Request request) {
    String requestId = safeRequestId(request.requestId());
    String previousRequestId = MDC.get("request_id");
    String previousFunction = MDC.get("function");
    String previousRoute = MDC.get("route");

    try {
        MDC.put("request_id", requestId);
        MDC.put("function", "CreateOrder");
        MDC.put("route", "/orders");

        return process(request);
    } finally {
        restoreMdc("request_id", previousRequestId);
        restoreMdc("function", previousFunction);
        restoreMdc("route", previousRoute);
    }
}

private static void restoreMdc(String key, String previousValue) {
    if (previousValue == null) {
        MDC.remove(key);
    } else {
        MDC.put(key, previousValue);
    }
}
~~~

Trong serverless, thread có thể được tái sử dụng cho invocation tiếp theo. Nếu MDC không được dọn, context của request trước có thể xuất hiện trong log của request sau. Luôn dọn các key do function thêm trong finally, kể cả khi handler ném exception.

Nếu framework hoặc runtime xử lý invocation bất đồng bộ, MDC không nhất thiết tự truyền qua thread hoặc executor. Dùng context propagation được hỗ trợ, hoặc truyền context rõ ràng vào task. Không đưa token, email hoặc payload vào MDC vì các field này có thể tự động xuất hiện trong mọi log.

## 9. Exception có thể làm lộ dữ liệu

Exception message thường được tạo từ dữ liệu đầu vào hoặc dependency. Một vài ví dụ:

- HTTP client exception chứa URL có signed query.
- SQL exception chứa câu lệnh, schema, table hoặc giá trị bind.
- JSON parser exception trích một phần payload.
- Authentication exception chứa username hoặc token fragment.
- Storage SDK exception chứa object path hoặc request metadata.
- Validation exception phản chiếu giá trị client gửi.

Dòng sau có thể làm lộ message và stack trace:

~~~java
// Không dùng trong log phổ thông nếu exception có thể chứa dữ liệu nhạy cảm.
logger.error("Request failed", exception);
~~~

Với log vận hành có quyền truy cập rộng, ghi error code ổn định, loại exception và request ID:

~~~java
catch (Exception ex) {
    logger.error(
        "payment_authorization_failed request_id={} error_code={} exception_type={}",
        requestId,
        "PAYMENT_PROVIDER_UNAVAILABLE",
        ex.getClass().getSimpleName()
    );

    throw new ServiceUnavailableException("PAYMENT_PROVIDER_UNAVAILABLE");
}
~~~

Không ghi ex.getMessage() nếu chưa biết message có chứa secret hoặc PII hay không. Không serialize toàn bộ exception thành JSON rồi gửi đến log aggregator.

### Khi cần stack trace để điều tra

Stack trace có giá trị chẩn đoán, nhưng có thể chứa exception message trong cause chain. Nếu cần lưu chi tiết hơn, gửi vào diagnostic sink riêng có quyền truy cập hạn chế hơn; áp dụng redaction cho exception message, URL và dữ liệu provider; giới hạn retention và bật audit truy cập; không đưa stack trace vào response cho client; không gửi nguyên exception qua alert/chat/ticket.

Đừng cho rằng chỉ log exception class là đủ trong mọi tình huống. Error code và stack fingerprint cần đi kèm trace ID, deployment version và các metadata vận hành an toàn.

## 10. Thiết kế thông báo lỗi HTTP an toàn

Response lỗi là giao diện công khai. Nó nên cung cấp đủ thông tin để client hiểu cách xử lý, nhưng không tiết lộ stack trace, tên class nội bộ, đường dẫn file, package, hostname private, SQL query, table name, connection string, token, dữ liệu người dùng khác hoặc payload gốc.

Dùng error code ổn định và request/correlation ID để hỗ trợ điều tra:

~~~json
{
  "type": "https://api.example.com/problems/service-unavailable",
  "title": "Service temporarily unavailable",
  "status": 503,
  "detail": "The request could not be completed. Try again later.",
  "code": "PAYMENT_PROVIDER_UNAVAILABLE",
  "requestId": "req-7f2c"
}
~~~

Đây là ví dụ theo kiểu Problem Details. Detail phải là thông báo đã được duyệt, không phải exception message. Không đặt token, user ID hoặc dữ liệu nhạy cảm trong instance hay URL của problem response.

### Map exception sang response

~~~java
public ApiError toApiError(Throwable error, String requestId) {
    if (error instanceof InvalidInputException) {
        return new ApiError(
            400, "INVALID_REQUEST",
            "The request is invalid.", requestId);
    }

    if (error instanceof ServiceUnavailableException) {
        return new ApiError(
            503, "SERVICE_UNAVAILABLE",
            "The service is temporarily unavailable.", requestId);
    }

    return new ApiError(
        500, "INTERNAL_ERROR",
        "An unexpected error occurred.", requestId);
}

public record ApiError(
        int status,
        String code,
        String message,
        String requestId) {
}
~~~

Client nhận code và request ID; đội vận hành tìm log/trace bằng request ID. Đừng trả nguyên error.getMessage() chỉ vì đó là cách nhanh nhất để hiển thị lỗi.

### Phân biệt 4xx và 5xx

- 4xx: thông báo lỗi đầu vào có thể nói rõ field nào sai nếu field đó không nhạy cảm. Không phản chiếu raw input.
- 401/403: không tiết lộ tài khoản có tồn tại hay không nếu điều đó tạo rủi ro enumeration.
- 404: không xác nhận sự tồn tại của resource riêng tư nếu caller không có quyền.
- 429: có thể trả retry guidance và Retry-After phù hợp, không tiết lộ quota nội bộ nhạy cảm.
- 5xx: dùng thông báo tổng quát và error code; chi tiết nội bộ nằm trong telemetry được kiểm soát.

## 11. OpenTelemetry: trace và span cũng là dữ liệu nhạy cảm

Distributed tracing ghi lại đường đi của request qua function, API, database, queue và service ngoài. Một trace thường gồm trace ID, span ID, parent relationship, timing, status, event và attributes.

Các attribute có thể nhạy cảm:

- url.full có query chứa token hoặc signed URL.
- HTTP request header Authorization hoặc cookie.
- db.statement chứa SQL hoặc giá trị đầu vào.
- messaging.message.body chứa toàn bộ event.
- enduser.id, email hoặc tenant identifier.
- Exception message và stack trace.
- Baggage được truyền từ service này sang service khác.

Không bật capture tất cả header, body hoặc SQL statement trong production nếu chưa có policy và redaction rõ ràng.

### Dùng route template thay cho URL đầy đủ

Nên ghi method POST, route /orders/{orderId} và status code 202. Tránh ghi URL đầy đủ khi query string có thể chứa secret. Nếu cần host, chỉ ghi hostname đã allowlist; không ghi userinfo hoặc query.

### Thêm attribute có chọn lọc

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;

Span span = Span.current();
span.setAttribute("app.error_code", "ORDER_VALIDATION_FAILED");
span.setAttribute("app.operation", "create_order");
span.setAttribute("http.route", "/orders/{orderId}");
span.setStatus(StatusCode.ERROR);
~~~

Chỉ thêm giá trị đã được duyệt. Không thêm raw customer ID, email, token, request body hoặc exception message. Dùng semantic convention phù hợp với phiên bản OpenTelemetry SDK/instrumentation đang dùng.

### Exception recording

Một số instrumentation tự động ghi exception event, gồm exception.message và stack trace. Vì vậy, dù code không chủ động thêm exception attribute, agent hoặc auto-instrumentation vẫn có thể thu thập chúng.

Cần kiểm tra cấu hình OpenTelemetry Java agent, framework instrumentation và exporter. Tắt hoặc giới hạn capture exception message/stack nếu không thể redaction an toàn. Khi cần ghi lỗi, có thể chỉ ghi exception.type, app.error_code và span status ở telemetry phổ thông.

## 12. Baggage và context propagation

OpenTelemetry Baggage cho phép truyền key-value qua nhiều service cùng trace context. Baggage tiện để truyền thông tin như tenant tier hoặc operation class, nhưng nó có thể được gửi qua network và xuất hiện trong log/trace của downstream.

Không đưa access token, session ID, cookie, email, số điện thoại, địa chỉ, raw user/tenant identifier, payload hoặc secret vào baggage. Chỉ allowlist các giá trị nhỏ, ít nhạy cảm và thực sự cần cho routing/observability. Không tin baggage do client bên ngoài gửi; gateway nên loại bỏ hoặc thay thế các key không được phép trước khi propagate.

Correlation ID cũng không nên trở thành nơi chứa dữ liệu. Dùng một ID ngẫu nhiên, khó đoán, không mang ý nghĩa nghiệp vụ. Nếu cần map ID đó về user hoặc operation, giữ mapping trong hệ thống được bảo vệ riêng.

## 13. Metrics: tránh đưa định danh vào label

Metrics thường được lưu lâu và tổng hợp rộng. Nếu dùng user ID, email, order ID, request ID hoặc URL động làm label, hệ thống có thể tạo cardinality rất lớn, tăng chi phí và làm chậm truy vấn. Đồng thời, các label đó cũng tiết lộ dữ liệu định danh.

Ưu tiên dimension có cardinality giới hạn:

~~~text
function_name=CreateOrder
route=/orders/{orderId}
status_class=2xx
error_code=ORDER_VALIDATION_FAILED
region=ap-southeast-1
~~~

Tránh customer email, order ID, request ID và URL có giá trị động làm label. Dùng histogram cho duration, counter cho số lỗi và gauge cho backlog/concurrency. Khi cần phân tích theo tenant, có thể dùng nhóm tier hoặc loại tenant thay vì ID cụ thể. Nếu cần truy vết một request, trace/log phù hợp hơn metrics.

## 14. Không log toàn bộ message hoặc event payload

Queue và event trigger thường mang dữ liệu nghiệp vụ. Một message có thể chứa email, địa chỉ giao hàng, payment reference hoặc nội dung webhook. Khi consumer thất bại, việc log toàn bộ body có thể làm dữ liệu nhạy cảm đi vào log ở mọi lần retry.

Thay vào đó, ghi metadata tối thiểu:

~~~json
{
  "event": "message_processing_failed",
  "event_type": "OrderCreated",
  "schema_version": 3,
  "message_ref": "msg-6d12",
  "attempt": 2,
  "error_code": "ORDER_VALIDATION_FAILED",
  "function": "ProcessOrder"
}
~~~

message_ref nên là ID không nhạy cảm hoặc pseudonymous reference; không dùng raw payload làm identifier. Nếu message ID từ bên ngoài có thể chứa PII, hãy thay bằng ID nội bộ.

### Với dead-letter queue

DLQ cần lưu message để replay hoặc điều tra, nhưng quyền truy cập DLQ không nên rộng hơn cần thiết. Đừng copy message body vào log khi đưa vào DLQ. Cần kiểm soát encryption và quyền đọc queue, retention, ai có quyền peek/dequeue/redrive, có cần masking hoặc tokenization trước khi lưu payload không, cách xóa message và bản sao sau thời hạn, và audit khi message được export hoặc replay.

Replay cần giữ idempotency key và không tạo side effect trùng. Nếu sửa payload để redrive, lưu audit của bản sửa mà không log dữ liệu nhạy cảm.

## 15. Debug HTTP client và SDK an toàn

HTTP client, database driver và cloud SDK có thể có chế độ debug log request/response. Những log này thường hữu ích trong môi trường phát triển nhưng có thể làm lộ credential hoặc dữ liệu body trong production.

- Không bật wire logging hoặc body logging toàn cục trong production.
- Nếu cần debug, bật có thời hạn, giới hạn service/route và redaction trước khi export.
- Không ghi Authorization, Cookie, API key, signed URL hoặc request body.
- Tắt log header do thư viện tự động capture nếu chưa có allowlist.
- Với SQL, log query fingerprint hoặc operation name thay vì statement chứa bind value.
- Không ghi response body từ identity provider hoặc payment provider.

Ví dụ log an toàn cho dependency:

~~~java
logger.warn(
    "dependency_call_failed dependency={} operation={} status={} request_id={}",
    "payment-provider",
    "authorize",
    503,
    requestId
);
~~~

Nếu cần chẩn đoán lỗi, bổ sung error category hoặc provider error code đã được kiểm tra. Tránh log toàn bộ response body vì provider có thể trả token fragment hoặc thông tin tài khoản.

## 16. Log ở các giai đoạn retry và idempotency

Serverless function có thể được gọi lại khi timeout, runtime restart, queue redelivery hoặc upstream retry. Nếu mỗi lần retry ghi toàn bộ payload, dữ liệu nhạy cảm sẽ xuất hiện nhiều lần. Nếu log không có attempt/correlation metadata, việc phân biệt retry với một operation mới cũng khó hơn.

Một event log hữu ích:

~~~json
{
  "event": "operation_retry_scheduled",
  "operation_ref": "op-7a31",
  "attempt": 3,
  "max_attempts": 5,
  "error_code": "DEPENDENCY_TIMEOUT",
  "next_delay_ms": 4000,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
~~~

Không đưa idempotency key có chứa customer data hoặc raw message ID vào log. Dùng reference nội bộ đã được tạo riêng. Giữ cùng correlation/trace context khi retry nếu hệ thống hỗ trợ, nhưng không tái sử dụng trace context một cách sai lệch qua các operation độc lập.

Nếu log event thất bại trước khi commit, ghi trạng thái theo thứ tự phù hợp. Không để log chứa payload trở thành cách duy nhất để phục hồi nghiệp vụ; trạng thái bền vững phải nằm trong database/queue/workflow.

## 17. Kiểm soát log platform và quyền truy cập

Redaction ở ứng dụng là lớp đầu tiên. Nền tảng thu thập telemetry cần tiếp tục kiểm soát:

- Encryption in transit và at rest.
- Role-based access theo team/service/environment.
- Audit truy vấn, export, share dashboard và tải log.
- Masking hoặc field-level access nếu sản phẩm hỗ trợ.
- Retention theo loại dữ liệu và mục đích.
- Tách production log khỏi sandbox/test.
- Giới hạn quyền tạo alert có chứa log snippet.
- Không gửi log nhạy cảm sang workspace hoặc Region không được phép.

Log thường được sao chép sang nhiều đích. Khi thay đổi sink hoặc exporter, kiểm tra tất cả bản sao, bao gồm archive, SIEM, data lake, ticket integration và backup.

Không nên lưu tất cả log vô thời hạn. Xác định retention dựa trên yêu cầu bảo mật, pháp lý, vận hành và khả năng điều tra. Log có định danh cá nhân nên có thời gian lưu tối thiểu cần thiết. Có thể giữ metric tổng hợp lâu hơn log chi tiết.

## 18. Sampling trace và giới hạn dữ liệu thu thập

Distributed tracing có thể tạo nhiều span, nhất là khi một request gọi nhiều dependency hoặc queue consumer xử lý lượng message lớn. Sampling giảm dung lượng, chi phí và phạm vi dữ liệu thu thập.

- **Head sampling:** quyết định giữ trace từ đầu request, thường dựa trên tỷ lệ hoặc rule đơn giản.
- **Tail sampling:** quyết định sau khi đã quan sát trace, có thể ưu tiên trace lỗi hoặc latency cao.
- **Attribute filtering:** loại bỏ hoặc biến đổi attribute nhạy cảm trước exporter.
- **Span suppression:** bỏ span quá chi tiết không phục vụ mục đích vận hành.

Sampling không phải biện pháp redaction. Nếu trace được sample rồi mới lọc, dữ liệu nhạy cảm vẫn có thể tồn tại ở memory buffer hoặc exporter. Redact/allowlist trước khi export; sampling chỉ điều chỉnh số lượng trace giữ lại.

Không đặt sampling rule dựa trên user ID hoặc email. Nếu cần giữ trace lỗi, ưu tiên status, error code, service và duration.

## 19. Kiểm thử để phát hiện rò rỉ dữ liệu

Không chỉ review source code. Cần kiểm tra telemetry thực tế tạo ra bởi framework, runtime, SDK và auto-instrumentation.

Một bộ kiểm thử có thể dùng giá trị canary giả, không phải secret thật:

~~~java
@Test
void doesNotLogAuthorizationOrPayload() {
    String fakeToken = "CANARY_TOKEN_DO_NOT_LOG";
    String fakeEmail = "canary-user@example.invalid";

    invokeFunction(fakeToken, fakeEmail);

    String capturedLogs = testAppender.contents();

    assertFalse(capturedLogs.contains(fakeToken));
    assertFalse(capturedLogs.contains(fakeEmail));
}
~~~

Ví dụ này cần test appender phù hợp với logging framework. Mục tiêu là khẳng định giá trị nhạy cảm không xuất hiện trong log output.

| Ca kiểm thử | Dữ liệu canary | Kết quả mong đợi |
|---|---|---|
| HTTP Authorization | Bearer token giả | Không xuất hiện trong log hoặc span |
| Cookie | Session cookie giả | Không xuất hiện trong telemetry |
| Query string | Reset token giả | Chỉ route template được ghi |
| Request body | Email/địa chỉ giả | Không serialize toàn bộ body |
| Exception message | Chuỗi chứa canary | Error log phổ thông không chứa message |
| SQL error | Bind value giả | Không log SQL chứa giá trị |
| Trace baggage | PII giả | Không propagate hoặc export |
| Queue message | Payload chứa canary | Chỉ event metadata an toàn được ghi |
| DLQ redrive | Message lỗi giả | Audit có reference, không dump body |
| Error response | Stacktrace/hostname giả | Client chỉ nhận code và message công khai |
| CRLF injection | CRLF và control character | Không tạo log record giả |
| MDC reuse | Hai invocation khác nhau | Context invocation trước không xuất hiện ở invocation sau |

Nên chạy kiểm thử cả local và trong môi trường serverless test vì platform logger, extension và agent có thể thêm dữ liệu ngoài appender của unit test.

## 20. Quy trình xử lý khi phát hiện dữ liệu đã bị log

Nếu phát hiện token, password hoặc PII đã xuất hiện trong telemetry:

1. Xác định loại dữ liệu, hệ thống log/trace, khoảng thời gian và phạm vi bản sao.
2. Hạn chế quyền truy cập hoặc tạm dừng exporter/sink gây rò rỉ nếu cần.
3. Thu hồi/rotate credential nếu secret có thể bị sử dụng.
4. Xác định log đã được export, archive, đính kèm ticket hoặc gửi alert đến đâu.
5. Áp dụng quy trình xóa/retention phù hợp với từng sink và backup.
6. Sửa logging, instrumentation hoặc error handler tại nguồn.
7. Thêm test canary và rule phát hiện để ngăn tái diễn.
8. Ghi nhận incident, tác động và quyết định thông báo theo chính sách tổ chức.

Không xóa log một cách tùy tiện nếu nó là bằng chứng cần giữ cho điều tra. Cần phối hợp security/incident owner để cân bằng yêu cầu bảo toàn chứng cứ với việc hạn chế truy cập và xóa dữ liệu không được phép lưu.

## 21. Những sai lầm thường gặp

| Sai lầm | Rủi ro | Cách xử lý |
|---|---|---|
| Log toàn bộ request/response | Lộ token, cookie và PII | Allowlist field và log metadata |
| Chỉ che password bằng regex | Bỏ sót secret ở URL, nested JSON hoặc exception | Không log payload; redaction theo schema và allowlist |
| Log exception trực tiếp | Message/cause có thể chứa dữ liệu đầu vào | Error code, exception type và sink chẩn đoán riêng |
| Trả stack trace cho client | Lộ package, path, SQL và topology | Error response tổng quát kèm request ID |
| Ghi URL đầy đủ | Query có token/SAS/presigned signature | Route template và hostname allowlist |
| Ghi raw user ID vào metrics | Lộ định danh và cardinality cao | Dùng dimension tổng hợp |
| Đưa PII vào baggage | Dữ liệu lan sang nhiều service | Baggage allowlist và gateway sanitization |
| Bật debug HTTP/SQL ở production | Log body, header và bind value | Debug có thời hạn, scope hẹp và redaction |
| Không dọn MDC | Context request trước rò sang invocation sau | Remove key trong finally |
| Nghĩ structured JSON tự an toàn | Field nhạy cảm vẫn được serialize | Schema allowlist và kiểm thử output |
| Chỉ redaction ở dashboard | Secret vẫn nằm trong storage/index | Redact trước khi export và bảo vệ sink |
| Lưu log vô thời hạn | Tăng tác động của sự cố và chi phí | Retention theo mục đích |
| Log DLQ body để dễ debug | Payload nhạy cảm bị nhân bản | Message reference, error code và quyền DLQ riêng |
| Hash PII bằng SHA-256 đơn giản | Có thể dò ngược bằng từ điển | HMAC có key quản lý hoặc random reference |

## 22. Checklist production

Trước khi triển khai Java function, hãy xác nhận:

- **Data inventory:** đã xác định field nào là PII, secret, business payload và operational metadata chưa?
- **Allowlist:** log chỉ ghi field có mục đích rõ ràng; không serialize request, response hoặc event tùy tiện.
- **HTTP:** Authorization, Cookie, query token, signed URL và forwarded header không bị log.
- **Structured logs:** JSON encoder escape dữ liệu; input text được giới hạn và chống log injection.
- **Exceptions:** error code và exception type được ghi; exception message/stack chỉ đi vào sink phù hợp và đã được kiểm soát.
- **Error response:** client không nhận stack trace, SQL, hostname private hoặc secret; có request ID để hỗ trợ.
- **Trace:** URL, header, SQL, event body và exception attributes được allowlist/redact.
- **Baggage:** chỉ truyền key-value không nhạy cảm; loại bỏ baggage không tin cậy từ client.
- **Metrics:** không dùng user ID, email, request ID hoặc URL động làm label.
- **Queue/DLQ:** không dump payload; kiểm soát quyền đọc, retention, redrive và audit.
- **MDC/context:** context được dọn sau mỗi invocation và truyền đúng qua async task.
- **Storage:** log/trace được mã hóa, giới hạn quyền, audit và retention.
- **Testing:** có canary test cho log, trace, error response, CRLF và retry.
- **Incident response:** có quy trình rotate secret, tìm bản sao và xử lý xóa/retention.
- **Cost:** sampling, cardinality, log volume và retention được theo dõi để tránh chi phí không cần thiết.

## 23. Kết luận

Log, trace và thông báo lỗi là một phần của bề mặt bảo mật ứng dụng. Chúng cần cung cấp đủ context để tìm lỗi, nhưng không nên trở thành bản sao của request, event payload hoặc dữ liệu nghiệp vụ. Hãy phân loại dữ liệu, ưu tiên allowlist, dùng structured logging, giữ exception message và stack trace trong phạm vi được kiểm soát, đồng thời trả error code ổn định thay cho chi tiết nội bộ.

Với Java serverless, cần đặc biệt chú ý việc runtime và SDK tự ghi telemetry, thread/MDC được tái sử dụng, message bị retry và trace context được truyền qua nhiều service. Redaction phải diễn ra trước khi dữ liệu được export; quyền truy cập, retention, encryption và audit tiếp tục bảo vệ các bản ghi ở backend. Canary tests và quy trình incident giúp phát hiện và xử lý rò rỉ trước khi nó lặp lại.

Khi telemetry chỉ chứa dữ liệu cần thiết và có thể truy vết bằng request ID, error code cùng trace context an toàn, nhóm vẫn điều tra được cold start, dependency failure, retry và latency mà không làm tăng rủi ro lộ dữ liệu của người dùng.
