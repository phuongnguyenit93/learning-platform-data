# Structured log và correlation ID

Trong module `SECURITY_API_SECURITY`, log API là một phần của kiểm soát bảo mật: nó giúp phát hiện truy cập bất thường, điều tra lỗi authorization, theo dõi lạm dụng tài nguyên và xác định phạm vi sự cố. Log cần đủ cấu trúc để máy có thể tìm kiếm và tổng hợp, đồng thời phải giới hạn dữ liệu được ghi để không biến hệ thống quan sát thành nơi tập trung token, PII hoặc payload nhạy cảm.

**Structured logging** ghi mỗi sự kiện thành các field có tên và kiểu ổn định, thay vì chỉ ghép một chuỗi văn bản tự do. **Correlation ID** là mã opaque giúp liên kết log của cùng request hoặc workflow qua gateway, service và worker. Hai kỹ thuật này bổ trợ nhau: structured log giúp lọc theo field; correlation ID giúp nối các sự kiện liên quan. Cả hai chỉ phục vụ observability, không phải bằng chứng xác thực hoặc quyền truy cập.

## 1. Vì sao API cần structured logging?

Một dòng log tự do như:

```text
User 42 failed to update order 912 for tenant acme from 10.0.0.8
```

có vẻ dễ đọc nhưng khó phân tích ổn định. Hệ thống tìm kiếm phải đoán vị trí user, order, tenant và outcome trong câu. Khi format thay đổi, dashboard hoặc alert có thể hỏng. Dòng log cũng có thể làm lộ định danh và thông tin mạng nội bộ không cần thiết.

Structured log biểu diễn cùng sự kiện bằng field rõ ràng:

```json
{
  "timestamp": "2026-11-18T10:15:30.123Z",
  "severity": "WARN",
  "service_name": "order-api",
  "event_name": "order_update_denied",
  "request_id": "7b2a3d4e-5f60-4a71-8b92-1c3d4e5f6071",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "http_method": "PATCH",
  "http_route": "/v1/orders/{orderId}",
  "http_status": 403,
  "error_code": "ORDER_WRITE_FORBIDDEN",
  "duration_ms": 18
}
```

Log mẫu dùng route template thay vì URL đầy đủ, không chứa token, email hoặc raw payload. Các field có thể được lọc, tổng hợp và liên kết mà không cần parse câu văn.

### 1.1. Lợi ích cho bảo mật API

- **Phát hiện hành vi bất thường:** nhiều lần `401/403`, thử ID hàng loạt, gọi endpoint nhạy cảm hoặc tăng đột biến request tốn chi phí.
- **Điều tra authorization:** biết operation nào bị từ chối, policy code nào áp dụng và request thuộc trace nào.
- **Theo dõi resource abuse:** đo request size, số item, latency, quota decision và downstream failure theo operation.
- **Điều tra SSRF:** ghi policy decision, destination category và lý do chặn mà không log signed URL hoặc query secret.
- **Đối soát vận hành:** nối log API với message consumer, retry, DLQ và provider request bằng ID riêng có kiểm soát.
- **Tự động hóa cảnh báo:** dashboard và alert dựa trên event name, status class, error code và service.

Log không thay thế audit trail, metric, distributed trace hoặc security control. Mỗi loại dữ liệu có mục đích, retention và quyền truy cập khác nhau.

### 1.2. Log khác audit, metric và trace

| Loại dữ liệu | Câu hỏi chính | Ví dụ |
|---|---|---|
| Application log | Điều gì đã xảy ra trong code? | Validation failed, provider timeout |
| Security/audit event | Ai đã thực hiện hành động nào và quyết định ra sao? | Operator cấp role cho user |
| Metric | Sự kiện xảy ra bao nhiêu lần, xu hướng thế nào? | Tỷ lệ 403, p95 latency, queue depth |
| Distributed trace | Request đi qua những service/span nào và mất bao lâu? | Gateway → Order → Payment |
| Correlation ID | Các bản ghi thuộc cùng request/workflow nào? | `request_id` opaque được propagate |

Một sự kiện quan trọng có thể xuất hiện ở nhiều hệ thống, nhưng không nên sao chép toàn bộ payload vào từng nơi. Audit cần tính toàn vẹn, quyền truy cập và retention riêng; metric cần label cardinality thấp; trace cần sampling và context propagation; log cần schema ổn định và redaction.

## 2. Thiết kế schema cho structured log

Schema log nên được định nghĩa như một contract nội bộ. Mỗi service có thể bổ sung field domain-specific, nhưng field chung cần giữ tên, kiểu và semantics nhất quán để dashboard hoạt động xuyên hệ thống.

### 2.1. Các field nền tảng

Một event log có thể gồm:

| Field | Ý nghĩa | Ví dụ |
|---|---|---|
| `timestamp` | Thời điểm phát sinh, UTC và có độ chính xác thống nhất | `2026-11-18T10:15:30.123Z` |
| `severity` | Mức độ log | `INFO`, `WARN`, `ERROR` |
| `service_name` | Tên service ổn định | `order-api` |
| `service_version` | Phiên bản build/release | `2.8.1` |
| `deployment_environment` | Môi trường | `production` |
| `event_name` | Tên sự kiện ổn định | `order_update_denied` |
| `message` | Mô tả ngắn cho con người | `Order update denied by policy` |
| `request_id` | Request ID opaque | UUID ngẫu nhiên |
| `trace_id` | Trace ID theo tracing standard | 32 ký tự hex theo W3C Trace Context |
| `span_id` | Span ID hiện tại nếu có | 16 ký tự hex |
| `http_method` | HTTP method | `PATCH` |
| `http_route` | Route template | `/v1/orders/{orderId}` |
| `http_status` | HTTP status | `403` |
| `duration_ms` | Thời gian xử lý | `18` |
| `error_code` | Mã lỗi ổn định | `ORDER_WRITE_FORBIDDEN` |
| `outcome` | Kết quả chuẩn hóa | `success`, `denied`, `failure` |

Ví dụ trong bài dùng schema nội bộ `snake_case` để nhất quán giữa JSON và code. Có thể chọn OpenTelemetry semantic conventions với tên field chuẩn của chúng, nhưng cần mapping rõ ở collector/index và không trộn hai kiểu tên trong cùng một event family. Tránh mỗi service dùng `requestId`, `req_id`, `correlation`, `xid` với semantics khác nhau.

### 2.2. Tên event phải ổn định

Ưu tiên `event_name` mô tả sự kiện bằng dạng chuẩn như `authentication_failed`, `authorization_denied`, `input_validation_failed`, `rate_limit_exceeded`, `ssrf_destination_rejected` hoặc `payment_provider_timeout`.

Không tạo event name từ dữ liệu động, ví dụ `user_12345_failed` hoặc `order_9876_denied`. Giá trị động nên nằm trong field có giới hạn và quyền truy cập phù hợp; event name phải có tập giá trị nhỏ để truy vấn và tổng hợp.

### 2.3. Giữ kiểu dữ liệu nhất quán

- Timestamp dùng định dạng thời gian chuẩn và UTC.
- Duration, body size, item count và retry count dùng numeric type.
- Status code dùng integer.
- Outcome/severity/error code dùng enum hoặc string có tập giá trị được quản lý.
- Field không có giá trị nên được bỏ qua hoặc biểu diễn `null` theo schema; không dùng chuỗi `"null"`, `"unknown"` và số `0` thay thế lẫn nhau.

Không ghi toàn bộ object Java vào một field `toString()`. Serializer có thể vô tình đưa thêm password, token, lazy-loaded entity hoặc dữ liệu không dự kiến vào log.

### 2.4. Route template thay cho raw URL

Ghi `http_route: "/v1/orders/{orderId}"` thay vì URL thực như `/v1/orders/12345?access_token=...`. Route template giúp metric cardinality thấp và tránh lộ resource ID/query parameter. Nếu cần tra cứu resource cụ thể cho audit, dùng field riêng đã phân loại dữ liệu, được mask/pseudonymize và giới hạn quyền truy cập.

Không log query string mặc định. Query có thể chứa search term, email, reset token, signed URL hoặc filter nhạy cảm. Nếu một query parameter thực sự cần cho điều tra, allowlist từng key và chuẩn hóa giá trị trước khi ghi.

## 3. Chọn log level và event semantics

Log level cần phản ánh ý nghĩa vận hành, không chỉ mức độ khó chịu của exception. Nếu mọi request bị từ chối đều ghi `ERROR`, hệ thống có thể tạo noise và che khuất lỗi thực sự.

| Level | Dùng khi | Ví dụ |
|---|---|---|
| `TRACE` | Chi tiết rất nhỏ, chỉ bật có kiểm soát | Bước nội bộ của parser trong môi trường debug |
| `DEBUG` | Chẩn đoán phát triển, không bật rộng ở production | Mapping DTO hoặc cache branch đã loại dữ liệu nhạy cảm |
| `INFO` | Sự kiện vận hành bình thường hoặc thay đổi trạng thái đáng chú ý | Request hoàn tất, job bắt đầu/kết thúc |
| `WARN` | Điều kiện bất thường nhưng được xử lý an toàn | Authorization denied, quota gần ngưỡng, retry scheduled |
| `ERROR` | Operation thất bại do lỗi hệ thống cần điều tra | Database unavailable, unhandled exception |

Một `403` do user thiếu quyền có thể là `WARN` hoặc security event theo policy; không nhất thiết là `ERROR`. Một lỗi validation thông thường có thể được ghi ở `INFO` hoặc `WARN` tùy mức độ abuse và tần suất. Cần tránh để attacker tạo hàng triệu log `ERROR` bằng cách gửi request sai.

### 3.1. Tách request summary khỏi event chi tiết

Không nhất thiết log cả một dòng cho mọi bước xử lý. Một request summary ở cuối request có thể chứa method, route, status, duration, request ID và outcome. Các event chi tiết chỉ phát sinh ở điểm cần điều tra như authentication failure, policy denial, quota rejection hoặc provider timeout.

Tránh ghi trùng cùng một exception ở controller, service, filter và global exception handler. Chọn một nơi sở hữu log cho mỗi failure path; các lớp khác có thể thêm context vào exception hoặc trace mà không log lại toàn bộ stack.

### 3.2. Không dùng log level làm thay thế severity của security event

Một số event cần được đưa vào audit/security pipeline với category và priority riêng. Ví dụ grant role, rotate key, thay đổi MFA hoặc export dữ liệu nhiều tenant cần audit dù operation thành công và application log chỉ ở `INFO`.

Không suy ra rằng mọi `WARN` là sự kiện bảo mật hoặc mọi `ERROR` là incident. Event type, policy decision và alert rule cần được thiết kế riêng.

## 4. Correlation ID và request ID

Correlation ID liên kết các log thuộc cùng request hoặc workflow. Request ID thường đại diện cho một lần request tới một edge/service. Kiến trúc có thể dùng cùng một ID cho cả hai ở một luồng đồng bộ đơn giản, nhưng phải ghi rõ semantics; với hệ thống bất đồng bộ hoặc fan-out, chúng có thể khác nhau.

### 4.1. ID phải opaque và không chứa dữ liệu nhạy cảm

Không tạo ID từ email, phone, user ID, tenant ID, order ID, timestamp nghiệp vụ, token hoặc session. Không dùng hash của PII như một cách che dữ liệu; hash ổn định vẫn có thể bị dò và liên kết.

Ưu tiên UUIDv4 hoặc random identifier có entropy phù hợp. Correlation ID không phải credential và không được dùng làm authorization key, idempotency key hoặc capability URL.

### 4.2. Tạo ID tại trust boundary

Gateway public nên xóa hoặc ghi đè header request ID do client gửi rồi phát hành ID canonical. Nếu cần giữ mã tham chiếu do client cung cấp, lưu riêng như `client_request_reference`, giới hạn độ dài/ký tự và đánh dấu là untrusted. Không phản chiếu chuỗi thô vào response hoặc log.

Nếu service có thể được gọi trực tiếp, service phải tự tạo ID hoặc chỉ chấp nhận upstream ID khi xác minh được kết nối và proxy ghi đè header. Không tin `X-Request-ID` chỉ vì header có tên nội bộ.

### 4.3. Phân biệt correlation ID với trace context

W3C Trace Context sử dụng `traceparent` và `tracestate`; tracing SDK quản lý trace ID và span ID. Correlation ID có thể giúp nối workflow qua nhiều trace hoặc message. Không tự parse/sửa traceparent bằng regex và không dùng trace ID làm user identity.

`baggage` có thể được truyền qua nhiều service. Chỉ cho phép key/value không nhạy cảm, giới hạn kích thước và loại bỏ field không được phép tại trust boundary. Không nhét JWT, email, tenant secret hoặc toàn bộ principal vào baggage.

### 4.4. Truyền correlation metadata có kiểm soát

Propagate ID qua HTTP header hoặc message metadata theo allowlist. Không sao chép toàn bộ header inbound xuống downstream vì có thể làm lộ `Authorization`, `Cookie`, forwarded headers hoặc client-supplied metadata. Không gửi correlation header nội bộ tới host ngoài do user cung cấp.

Với message queue, giữ correlation reference trong metadata riêng; consumer xác thực producer và kiểm tra tenant bằng policy độc lập. Không dùng correlation ID làm bằng chứng rằng message thuộc tenant nào.

## 5. Những dữ liệu không được ghi vào log

Log thường được truy cập bởi nhiều nhóm hơn database nghiệp vụ và có thể được chuyển tới nhà cung cấp telemetry. Áp dụng nguyên tắc **log allowlist**: chỉ ghi field cần cho vận hành và bảo mật, không log toàn bộ request/response rồi cố redaction sau.

### 5.1. Secret và credential

Không ghi:

- `Authorization`, bearer token, refresh token, API key hoặc client secret.
- Cookie, session ID, CSRF token hoặc reset-password token.
- Password, OTP, private key, chữ ký hoặc credential database.
- Signed URL có token trong query string.
- Secret provider, webhook signing secret hoặc nội dung key rotation.

Nếu credential xuất hiện trong log, coi đó là một sự cố dữ liệu: xác định phạm vi, thu hồi/rotate credential, giới hạn truy cập log và xử lý bản sao theo incident/retention policy. Xóa dòng log không làm credential mất hiệu lực.

### 5.2. PII và dữ liệu nghiệp vụ nhạy cảm

Không log raw email, phone, địa chỉ, tên thật, số tài khoản, số thẻ, nội dung message, tài liệu upload hoặc dữ liệu sức khỏe/tài chính nếu không có nhu cầu được phê duyệt. Nếu cần phân tích theo user/tenant, dùng pseudonymous identifier hoặc field được mask với quyền truy cập và retention riêng; không nhúng vào correlation ID.

Việc hash một giá trị không tự động làm nó vô danh. Giá trị có thể đối chiếu được với danh sách nguồn vẫn có rủi ro tái nhận diện.

### 5.3. Request/response body và exception message

Không bật log toàn bộ body trong production như một mặc định. Body có thể chứa credential, PII, file content hoặc payload độc hại. Nếu cần debug một schema cụ thể, log field allowlist đã sanitize, giới hạn kích thước và bật trong thời gian có kiểm soát.

Exception message từ driver hoặc provider có thể chứa SQL, connection string, URL, request fragment hoặc secret. Log error code, exception class và stack trace ở nơi có quyền phù hợp; không đưa raw exception message vào response cho client.

### 5.4. URL, header và IP address

Tránh log URL đầy đủ với query string và fragment. Với header, dùng allowlist; không log toàn bộ inbound headers. IP address có thể là dữ liệu cá nhân theo bối cảnh pháp lý và sản phẩm; chỉ thu thập khi có mục đích, retention và quyền truy cập rõ. Khi đứng sau proxy, chỉ dùng forwarded IP từ proxy đã xác minh; không tin `X-Forwarded-For` do client tự gửi.

### 5.5. Log injection và control characters

Input do client kiểm soát có thể chứa CR/LF, tab, ANSI escape hoặc ký tự điều khiển để tạo log line giả, làm hỏng parser hoặc gây nhầm lẫn khi điều tra. Dùng structured logger/serializer an toàn, giới hạn độ dài và không nối input thô vào log line. Nếu cần ghi external reference, chuẩn hóa hoặc encode theo định dạng log.

## 6. Redaction và data minimization

Redaction là lớp phòng thủ bổ sung; cách an toàn hơn là không đưa dữ liệu nhạy cảm vào log ngay từ đầu. Thiết kế log event nên chỉ lấy field từ DTO/metadata đã phân loại, thay vì serialize toàn bộ object.

### 6.1. Allowlist trước, redact sau

Ví dụ event validation failure chỉ cần:

```json
{
  "event_name": "input_validation_failed",
  "request_id": "7b2a3d4e-5f60-4a71-8b92-1c3d4e5f6071",
  "route": "/v1/users",
  "error_code": "FIELD_TOO_LONG",
  "field_path": "displayName",
  "limit": 120
}
```

Không cần log giá trị thực mà user đã gửi. Với SSRF rejection, có thể log destination category như `private_ipv4` hoặc `link_local`, policy decision và hostname đã mask nếu cần; không log signed URL hay query secret.

### 6.2. Redaction ở nhiều lớp

Áp dụng policy tại:

- Application logger và exception handler.
- API gateway/reverse proxy access log.
- HTTP client/downstream instrumentation.
- Distributed tracing attributes và baggage.
- Message broker headers, DLQ metadata và consumer log.
- Audit export, support dashboard và log forwarding pipeline.

Nếu chỉ redact ở application, gateway hoặc tracing agent vẫn có thể ghi header nhạy cảm trước khi request tới app. Kiểm thử end-to-end toàn đường dữ liệu.

### 6.3. Masking có thể vẫn để lộ dữ liệu

Mask email thành `a***@example.com` hoặc phone thành `******4567` vẫn có thể nhận diện người trong tập nhỏ. Chỉ dùng khi thật sự cần cho support và kiểm soát quyền. Với analytics, ưu tiên aggregate hoặc tokenization/pseudonymization có quản lý key và retention.

### 6.4. Giới hạn kích thước log event

Một request có thể tạo hàng nghìn validation errors hoặc exception lặp. Giới hạn số field, độ dài message và tổng event bytes. Không để payload do client gửi quyết định kích thước log không giới hạn. Có thể đếm số lỗi tổng và ghi một mẫu field path đã allowlist.

## 7. Ghi log API theo lifecycle request

Một request có nhiều giai đoạn: nhận request, authentication, authorization, validation, nghiệp vụ, downstream call và response. Log nên thể hiện các quyết định quan trọng mà không tạo quá nhiều event trùng lặp.

### 7.1. Request summary

Một request summary ở cuối lifecycle có thể chứa:

- Request ID và trace/span ID nếu có.
- Service, environment, version.
- HTTP method và route template.
- Status code, outcome và duration.
- Request size hoặc response size nếu có giới hạn và cần giám sát.
- Error code chuẩn hóa.

Không ghi full URL, body hoặc toàn bộ headers. Nếu request bị reject trước khi route được resolve, dùng route category hoặc `unmatched` thay vì log raw path có thể chứa dữ liệu do client kiểm soát.

### 7.2. Authentication event

Log event như `authentication_failed` nên có reason code có kiểm soát (`TOKEN_EXPIRED`, `INVALID_AUDIENCE`, `MISSING_CREDENTIAL`) và operation context. Không log token, signature hoặc claim đầy đủ. Không trả thông tin chi tiết giúp attacker phân biệt tài khoản tồn tại nếu chính sách yêu cầu che giấu.

### 7.3. Authorization event

Với `authorization_denied`, ghi operation, policy code, resource type và outcome. Nếu cần resource reference hoặc actor reference, dùng field riêng được bảo vệ, pseudonymize/mask và có quyền truy cập phù hợp. Không nhét chúng vào correlation ID.

Không ghi toàn bộ policy expression, role graph hoặc dữ liệu resource nếu chúng tiết lộ cấu hình nội bộ. Tách security audit event cho thao tác nhạy cảm và đảm bảo event được lưu bền vững.

### 7.4. Validation và rate-limit event

Validation log nên dùng `field_path`, `error_code`, giới hạn và kích thước tổng; tránh ghi raw value. Rate-limit event có thể ghi bucket type, policy ID, limit và retry-after; không ghi API key hoặc token. Với abuse pattern, aggregate theo principal reference đã pseudonymize hoặc tenant scope có kiểm soát.

### 7.5. Downstream và SSRF event

Log timeout/provider error bằng dependency name, operation, status category và duration. Với URL fetcher, ghi decision (`allowed`/`rejected`), destination class và policy version; không ghi full URL hoặc header credential. Nếu cần điều tra hostname, dùng field được mask và giới hạn retention.

## 8. Correlation ID trong Java/Spring

Correlation metadata cần được tạo và truyền theo một quy tắc nhất quán. Ví dụ dưới đây dùng UUIDv4 cho request ID local, đặt vào SLF4J MDC và trả trong response header.

### 8.1. Filter tạo request ID

```java
@Component
public class RequestIdFilter extends OncePerRequestFilter {
    private static final String HEADER = "X-Request-ID";
    private static final String MDC_KEY = "request_id";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String previous = MDC.get(MDC_KEY);
        String requestId = UUID.randomUUID().toString();
        try {
            MDC.put(MDC_KEY, requestId);
            response.setHeader(HEADER, requestId);
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove(MDC_KEY);
            } else {
                MDC.put(MDC_KEY, previous);
            }
        }
    }
}
```

Ví dụ chủ động tạo ID mới và không tin `X-Request-ID` từ Internet. Trong kiến trúc gateway tin cậy, application có thể dùng ID do gateway phát hành nếu proxy đã ghi đè header, kết nối upstream được xác minh và format hợp lệ. Nếu không, tạo ID local.

Filter cần được đặt đúng vị trí trong servlet filter chain để request ID có mặt cả khi authentication/authorization thất bại. Với async servlet dispatch hoặc filter lồng nhau, kiểm tra lifecycle và semantics restore context. Không để MDC của request trước rò sang request sau trong thread pool.

### 8.2. Structured logging với SLF4J

Với SLF4J 2.x, có thể ghi key-value event:

```java
log.atWarn()
    .addKeyValue("event_name", "authorization_denied")
    .addKeyValue("request_id", MDC.get("request_id"))
    .addKeyValue("operation", "order.update")
    .addKeyValue("error_code", "ORDER_WRITE_FORBIDDEN")
    .log("Request denied by authorization policy");
```

Để output thành JSON, cấu hình logging backend/encoder tương ứng và kiểm tra field được serialize thành JSON thật. Key-value API không tự bảo đảm output JSON nếu backend đang dùng pattern text. Không nối dữ liệu động vào message và không thêm raw request object.

### 8.3. Không log exception nhiều lần

Global exception handler nên là nơi chuẩn hóa lỗi và ghi một event có request ID/error code. Controller/service không nên log lại cùng exception rồi ném tiếp, trừ khi đang ghi một event khác có ý nghĩa riêng. Tránh ghi stack trace cho lỗi validation hoặc authorization thông thường.

Ví dụ:

```java
@RestControllerAdvice
public class ApiExceptionHandler {
    private static final Logger log = LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(AccessDeniedException.class)
    ResponseEntity<ProblemDetail> handleDenied(AccessDeniedException ex) {
        log.atWarn()
            .addKeyValue("event_name", "authorization_denied")
            .addKeyValue("request_id", MDC.get("request_id"))
            .addKeyValue("error_code", "ACCESS_DENIED")
            .log("Request denied by policy");

        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.FORBIDDEN);
        problem.setTitle("Không có quyền thực hiện thao tác");
        problem.setProperty("code", "ACCESS_DENIED");
        problem.setProperty("requestId", MDC.get("request_id"));
        return ResponseEntity.status(HttpStatus.FORBIDDEN).body(problem);
    }
}
```

Đoạn code minh họa; cần xử lý các loại exception theo contract thực tế và bảo đảm request ID đã được tạo trước exception handler. Trong Spring Security, lỗi authorization phát sinh ở filter chain thường được xử lý bởi `AccessDeniedHandler` thông qua `ExceptionTranslationFilter`, không nhất thiết đi qua `@RestControllerAdvice`; hãy đặt structured event ở handler thực sự sở hữu failure path đó để không bỏ sót hoặc log trùng. Không đưa `ex.getMessage()` vào response hoặc log nếu message có thể chứa input/secret. Với lỗi hệ thống cần stack trace, ghi tại một nơi có quyền truy cập và retention phù hợp.

### 8.4. MDC và async context propagation

SLF4J MDC thường gắn với thread hiện tại và không tự động được truyền an toàn qua mọi `@Async`, executor, `CompletableFuture` hoặc reactive pipeline. Dùng `TaskDecorator`, Micrometer Context Propagation, OpenTelemetry instrumentation hoặc Reactor Context theo stack ứng dụng.

Chỉ propagate field allowlist như request ID và trace context. Không sao chép toàn bộ security principal, access token hoặc request headers vào MDC. Luôn restore/clear context trong `finally` để thread tái sử dụng không mang metadata của task trước.

Với message consumer chạy lâu sau khi HTTP request kết thúc, giữ workflow/correlation reference theo semantics nhưng tạo span mới cho consumer. Không giữ thread-local của request ban đầu qua thời gian dài.

## 9. Distributed tracing và propagation

Correlation ID có thể đi cùng distributed trace nhưng không thay thế chuẩn trace context.

### 9.1. W3C Trace Context

`traceparent` chứa version, trace ID, parent span ID và trace flags. Dùng OpenTelemetry hoặc tracing SDK tương thích để inject/extract context. Không tự tạo traceparent bằng cách nối chuỗi và không tin giá trị trace context để cấp quyền.

### 9.2. Baggage phải có allowlist

Baggage lan qua nhiều service và có thể tới exporter bên ngoài. Chỉ cho phép thuộc tính không nhạy cảm, có kích thước nhỏ và có mục đích rõ. Không đưa email, phone, user token, tenant secret hoặc payload vào baggage.

### 9.3. Tạo trace mới tại trust boundary khi cần

Context từ client hoặc partner có thể được tiếp tục theo policy hoặc được thay bằng trace mới tại ingress. Nếu tạo trace mới, có thể giữ liên kết tới context gốc theo tracing link nếu cần điều tra; không để external trace ID làm canonical identity của hệ thống.

### 9.4. Async trace và correlation

Khi publish message, inject trace context vào message headers theo instrumentation/broker convention. Consumer extract context và tạo consumer span. Nếu message được retry hoặc redrive, giữ message ID/correlation reference và tạo span mới cho mỗi attempt để quan sát retry behavior.

## 10. Bảo vệ log pipeline và nền tảng quan sát

Log có thể chứa dữ liệu vận hành nhạy cảm ngay cả khi ứng dụng đã redaction. Hệ thống thu thập, vận chuyển, lưu trữ và truy vấn log cần được bảo vệ như một production data system.

### 10.1. Transport và storage

- Dùng TLS hoặc kênh truyền được bảo vệ khi gửi log tới collector.
- Mã hóa log storage và backup theo chính sách dữ liệu.
- Xác thực agent/collector; không cho workload bất kỳ ghi vào index của service khác.
- Tách môi trường production, staging và development khi cần.
- Giới hạn quyền export/download và truy vấn diện rộng.

### 10.2. Access control

Quyền đọc log nên theo vai trò và nhu cầu công việc. Developer có thể cần log application của service mình; support có thể chỉ cần event đã mask; security team có thể cần audit event và truy vấn điều tra rộng hơn. Không cấp quyền quản trị log cho mọi người chỉ vì họ có quyền deploy application.

Nếu log có tenant reference hoặc pseudonymous user field, đảm bảo người dùng tenant này không thể truy vấn log tenant khác bằng cách đoán correlation ID. Tra cứu theo ID vẫn cần authentication, authorization và audit.

### 10.3. Retention và deletion

Đặt retention theo mục đích vận hành, mức nhạy cảm và nghĩa vụ pháp lý. Không giữ debug log vô thời hạn. Log chứa dữ liệu nhạy cảm cần retention ngắn hơn hoặc quy trình xóa riêng. Backup, export, ticket đính kèm và bản tải về cũng phải nằm trong phạm vi quản lý.

### 10.4. Integrity và auditability

Với security/audit event quan trọng, cần hạn chế khả năng actor bị giám sát tự xóa hoặc sửa log. Dùng storage/permission riêng, append-only hoặc tamper-evident mechanism khi yêu cầu. Ghi nhận việc thay đổi logging policy, retention và quyền truy cập.

### 10.5. Sampling và loss

Sampling có thể phù hợp với debug/trace volume lớn, nhưng không nên làm mất audit event bắt buộc hoặc security event có mức độ cao. Phân biệt telemetry sampling với audit durability. Theo dõi collector drop, buffer saturation và exporter failure; log không được coi là đã lưu chỉ vì application đã gọi logger.

## 11. Logging không được tạo thêm denial of service

Attacker có thể cố ý tạo lượng lớn lỗi authentication, validation hoặc route miss để làm đầy log storage và tăng chi phí ingest. Logging phải có giới hạn và khả năng chịu tải.

### 11.1. Giới hạn event và message size

- Giới hạn độ dài field và tổng kích thước event.
- Không ghi payload hoặc stack trace cho mọi request lỗi.
- Rate limit hoặc sample các event lặp lại có rủi ro thấp, nhưng giữ aggregate counter.
- Dùng async appender/buffer có giới hạn và chính sách khi đầy.
- Không block request vô thời hạn vì log backend chậm.

### 11.2. Không bỏ mất event bảo mật quan trọng

Có thể sample request summary hoặc debug log, nhưng các event như grant/revoke privilege, secret access, policy change hoặc export dữ liệu nhạy cảm có thể cần audit bền vững. Nếu audit store không khả dụng, behavior của operation nhạy cảm cần được xác định: từ chối thao tác, lưu qua durable outbox hoặc chuyển sang cơ chế fail-safe phù hợp.

### 11.3. Metric label cardinality

Không dùng request ID, trace ID, user ID, order ID hoặc raw URL làm metric label. Mỗi giá trị duy nhất có thể tạo một time series mới. Metric nên dùng service, route template, status class, event name và error category có tập giá trị hữu hạn.

### 11.4. Tách logging failure khỏi business exception

Không để logger failure làm lặp lại side effect hoặc che mất exception gốc. Xác định appender có thể fail-open hay fail-closed theo loại event. Application log thông thường thường không nên làm request business thất bại chỉ vì collector tạm chậm; audit bắt buộc có thể cần outbox/durable write riêng.

## 12. Kiểm thử structured logging và correlation

Không chỉ kiểm tra log “có xuất hiện”. Test cần xác minh schema, redaction, propagation và không có dữ liệu nhạy cảm.

### 12.1. Schema test

- Event output parse được thành JSON hợp lệ.
- Field chung có tên và kiểu ổn định.
- Timestamp UTC và severity đúng.
- Event name/error code thuộc tập giá trị đã định nghĩa.
- Route template được ghi thay raw URL.
- Event size không vượt giới hạn.

### 12.2. Redaction test

Gửi request chứa giá trị canary giả lập cho token, password, email, phone và signed URL. Sau khi xử lý, tìm toàn bộ log/trace/test appender và xác minh canary không xuất hiện trong field bị cấm. Không dùng credential thật làm test fixture.

Kiểm tra cả exception message, header, query, body, MDC, baggage, gateway access log và downstream instrumentation. Redaction chỉ ở một logger không đủ.

### 12.3. Correlation propagation test

- Request không có ID tạo ra ID opaque.
- Header client gửi bị ghi đè hoặc lưu riêng theo policy.
- Downstream nhận ID canonical qua trust boundary.
- Message consumer nối được correlation reference và tạo span mới.
- Async executor không làm mất hoặc rò MDC.
- Request kế tiếp trên cùng thread không mang ID cũ.

### 12.4. Abuse và failure test

- Gửi CR/LF và chuỗi rất dài để kiểm tra log injection/size limit.
- Tạo lượng lớn `401/403` để kiểm tra rate limit, sampling và log storage.
- Làm collector chậm hoặc unavailable để xác minh request không block vô hạn.
- Xác minh audit event quan trọng vẫn được lưu theo durability policy.
- Kiểm tra metric không tạo label cardinality theo request/resource ID.

### 12.5. Ma trận kiểm thử đề xuất

| Trường hợp | Kết quả mong đợi |
|---|---|
| Request thành công | Có request summary với ID, route template, status và duration |
| Authorization denied | Có event code, operation và outcome; không log payload nhạy cảm |
| Validation failed | Có field path/error code; không ghi raw value |
| Token/cookie canary | Không xuất hiện trong log/trace/export |
| Client request ID giả | Canonical ID do server tạo; external reference tách riêng |
| CR/LF trong external ID | Không tạo log line giả |
| Async worker | Context được propagate có kiểm soát và được dọn |
| Collector unavailable | Không block vô hạn; audit path theo durability policy |
| Nhiều request lỗi | Event volume được kiểm soát, aggregate vẫn chính xác |
| Metric scrape | Không có ID duy nhất làm label |

## 13. Monitoring và alert từ structured event

Structured event giúp tạo alert chính xác hơn log text search. Ví dụ:

- Tỷ lệ `authentication_failed` tăng theo route/client.
- `authorization_denied` tăng trên một tenant hoặc operation family.
- `rate_limit_exceeded` tăng đột biến theo principal bucket.
- `ssrf_destination_rejected` tăng sau khi có thay đổi URL fetcher.
- `input_validation_failed` tăng sau release có thể báo contract mismatch hoặc probing.
- `downstream_timeout` và retry event tăng đồng thời có thể báo dependency outage.
- Log collector drop hoặc audit outbox backlog tăng.

Alert nên dựa trên rate, ratio, baseline và mức độ nhạy cảm của operation; không cảnh báo chỉ vì một request bình thường bị `403`. Với operation nhạy cảm, một lần truy cập trái phép hoặc thay đổi quyền bất thường có thể cần cảnh báo ngay.

Không tạo dashboard chứa raw token, PII hoặc request body. Dashboard nên dùng aggregate và field đã phân loại.

## 14. Lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ log text tự do | Khó query, schema dễ vỡ | Structured event với field ổn định |
| Log toàn bộ request/response | Lộ token, PII và payload | Allowlist field, redaction và size limit |
| Dùng raw URL | Lộ query secret, cardinality cao | Route template và query allowlist |
| Correlation ID chứa user/tenant ID | Liên kết và rò dữ liệu qua mọi hệ thống | ID opaque ngẫu nhiên |
| Tin request ID từ client | Spoof log và làm nhiễu điều tra | Tạo/ghi đè tại trust boundary |
| Dùng trace ID làm identity | Sai ranh giới bảo mật | Principal riêng, trace chỉ là telemetry |
| Log mọi lỗi ở ERROR | Alert noise và log flooding | Level theo semantics và aggregate |
| Ghi cùng exception ở nhiều lớp | Log trùng, tăng chi phí | Một owner cho mỗi failure path |
| Không dọn MDC | Context request cũ rò sang request mới | Restore/remove trong `finally` |
| Propagate toàn bộ headers/baggage | Lộ credential và PII | Allowlist metadata |
| Metric label chứa ID duy nhất | High cardinality và tăng chi phí | Label có tập giá trị hữu hạn |
| Chỉ redact application log | Gateway/trace vẫn lộ dữ liệu | End-to-end data flow review và test |
| Không giám sát collector drop | Mất dấu vết mà không biết | Theo dõi buffer/exporter/audit backlog |

## 15. Checklist review trước khi phát hành

- [ ] Log schema có timestamp, severity, service, version, environment và event name ổn định.
- [ ] HTTP log dùng method, route template, status, outcome và duration.
- [ ] Correlation/request ID opaque, không chứa PII, tenant/resource ID hoặc secret.
- [ ] Gateway tạo/ghi đè ID canonical; client reference được tách riêng.
- [ ] Trace ID/span ID/baggage tuân theo tracing standard và không dùng làm identity.
- [ ] Event name, error code và outcome có tập giá trị được quản lý.
- [ ] Không log Authorization, Cookie, password, OTP, API key, private key hoặc signed URL.
- [ ] Không log raw body/query/header hoặc serialize entity tùy tiện.
- [ ] Log input không tin cậy được giới hạn và chống CR/LF injection.
- [ ] Redaction được kiểm tra ở gateway, application, trace, broker và exporter.
- [ ] MDC/context được restore và propagate đúng qua async/reactive execution.
- [ ] Exception không bị log trùng ở nhiều lớp; response không lộ stack trace.
- [ ] Log pipeline có TLS, encryption, access control, retention và audit.
- [ ] Audit event quan trọng có durability policy riêng, không bị sampling mất.
- [ ] Log size, event rate, buffer và collector failure có giới hạn/monitoring.
- [ ] Metric không dùng request/trace/user/resource ID làm label.
- [ ] Có schema, redaction, spoofing, async propagation và log flood tests.
- [ ] Alert dựa trên event/error code và baseline phù hợp với rủi ro operation.

## Kết luận

Structured logging biến log API thành dữ liệu có thể truy vấn và tự động hóa, còn correlation ID giúp nối sự kiện qua nhiều service mà không cần nhúng danh tính hoặc dữ liệu nghiệp vụ. Hãy chuẩn hóa schema và event name, dùng route template, tạo ID opaque tại trust boundary, propagate metadata theo allowlist và áp dụng redaction xuyên suốt log pipeline. Bảo vệ log bằng access control, encryption, retention và audit; giới hạn event volume để logging không trở thành nguồn denial of service. Kết hợp schema test, canary redaction test và monitoring giúp log vừa hữu ích cho điều tra vừa giảm nguy cơ rò dữ liệu.
