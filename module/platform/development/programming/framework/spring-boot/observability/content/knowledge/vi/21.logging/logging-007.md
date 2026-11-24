# Mask dữ liệu nhạy cảm

Trong chương **Logging** của mô-đun **SPRING_BOOT_OBSERVABILITY**, log là bằng chứng quan trọng để điều tra lỗi, độ trễ và hành vi ứng dụng. Tuy nhiên, log thường đi qua nhiều thành phần: ứng dụng Spring Boot, SLF4J/Logback, appender hoặc agent, OpenTelemetry Collector và hệ thống lưu trữ. Nếu log chứa mật khẩu, access token, session cookie, dữ liệu cá nhân hoặc thông tin thanh toán, mỗi bản sao có thể trở thành một điểm rò rỉ.

**Mask dữ liệu nhạy cảm** là biến đổi hoặc loại bỏ những phần dữ liệu không được phép xuất hiện trong log trước khi chúng đến nơi có thể lưu trữ hoặc truy vấn. Chiến lược tốt kết hợp ngăn ghi ở nguồn, structured logging, allowlist attributes, bộ lọc/redaction có kiểm thử và kiểm soát quyền truy cập/retention. Không nên dựa vào một regex duy nhất ở cuối pipeline để bảo vệ toàn bộ dữ liệu.

Mô-đun **SPRING_BOOT_OBSERVABILITY** tập trung vào Micrometer Observation, metrics, logs và distributed tracing. Vì vậy, bài này cũng chỉ ra cách bảo vệ dữ liệu trong MDC, trace/span attributes, baggage và exception logs để correlation vẫn hữu ích mà không sao chép secrets hoặc PII sang telemetry.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện secrets, PII, dữ liệu thanh toán và dữ liệu nội bộ không nên ghi log.
2. Phân biệt masking, redaction, hashing, tokenization và encryption.
3. Thiết kế allowlist cho structured logging thay vì ghi toàn bộ object/request.
4. Ngăn dữ liệu nhạy cảm xuất hiện trong message, arguments, exception, MDC và HTTP/gRPC metadata.
5. Chọn vị trí xử lý phù hợp trong ứng dụng, logging framework và telemetry pipeline.
6. Cấu hình bộ lọc Logback/SLF4J dễ kiểm thử, tránh phụ thuộc regex mong manh.
7. Bảo vệ logs, traces và baggage khi tích hợp Micrometer Tracing/OpenTelemetry.
8. Viết kiểm thử xác nhận dữ liệu nhạy cảm không xuất hiện ở output.
9. Xây dựng runbook khi phát hiện dữ liệu nhạy cảm đã bị ghi.
10. Cân bằng khả năng điều tra với quyền riêng tư, chi phí và chính sách lưu trữ.

## 2. Vì sao log cần được bảo vệ?

Một log record có thể chứa nhiều nguồn dữ liệu:

- Message do lập trình viên viết.
- Arguments được truyền vào logger.
- Object được serialize thành JSON.
- Exception message, cause và stack trace.
- MDC hoặc logging context như user, tenant, request ID.
- HTTP request/response headers và body.
- gRPC metadata và message fields.
- Trace/span attributes hoặc baggage được copy vào log.
- Dữ liệu do thư viện bên thứ ba tự ghi.

Ngay cả khi code không chủ động log mật khẩu, exception từ HTTP client, ORM, authentication library hoặc request decoder vẫn có thể chứa URL, query parameters, headers hoặc payload.

| Rủi ro | Tác động |
| --- | --- |
| Lộ password, API key, access token hoặc cookie | Người có quyền đọc logs có thể dùng credential để truy cập hệ thống. |
| Lộ email, số điện thoại, địa chỉ hoặc định danh | Ảnh hưởng quyền riêng tư, chính sách nội bộ hoặc quy định áp dụng. |
| Lộ dữ liệu thanh toán nhạy cảm | Tăng phạm vi ảnh hưởng và nghĩa vụ xử lý sự cố. |
| Log chứa session ID hoặc reset token | Có thể chiếm phiên hoặc hành động dưới danh nghĩa người dùng. |
| Dữ liệu được gắn vào trace/baggage | Telemetry lan sang nhiều service và backend khác nhau. |
| Ghi toàn bộ payload lớn | Tăng chi phí lưu trữ/index và nguy cơ lộ dữ liệu. |

Logs thường có phạm vi truy cập rộng: developer, operator, support, hệ thống SIEM, nhà cung cấp APM hoặc người có quyền truy vấn. Không giả định rằng vì log nằm trong hệ thống nội bộ nên dữ liệu có thể được ghi tự do.

## 3. Phân loại dữ liệu trước khi ghi

Một policy cần xác định dữ liệu nào được ghi, loại nào phải biến đổi và loại nào bị cấm.

| Nhóm dữ liệu | Ví dụ | Hướng xử lý mặc định |
| --- | --- | --- |
| Secrets/credentials | Password, API key, bearer token, private key, session cookie | Không ghi; nếu vô tình xuất hiện thì redaction và xử lý như sự cố. |
| Dữ liệu thanh toán nhạy cảm | Security code, magnetic-stripe data, authentication data | Không ghi. |
| PII | Email, số điện thoại, địa chỉ, ngày sinh, định danh cá nhân | Loại bỏ hoặc mask theo mục đích và policy. |
| Định danh giao dịch | Order ID, payment reference, request ID | Chỉ ghi khi cần; kiểm soát quyền truy cập, cardinality và retention. |
| Metadata vận hành | Service, route template, operation, status, duration | Thường có thể ghi nếu không tiết lộ dữ liệu riêng tư. |
| Dữ liệu cấu hình công khai | Tên feature flag, loại operation | Có thể ghi sau khi rà soát nội dung. |

Phân loại thực tế phải theo data classification policy của tổ chức và yêu cầu pháp lý/ngành áp dụng. Không tự kết luận một giá trị được phép log chỉ vì nó không giống password.

### Thiết kế theo allowlist

Đối với log có cấu trúc, chỉ chọn field đã được duyệt:

~~~java
log.atInfo()
        .addKeyValue("operation", "payment.authorize")
        .addKeyValue("outcome", "rejected")
        .addKeyValue("payment.reference", safeReference)
        .log("Payment authorization completed");
~~~

Ví dụ này không serialize toàn bộ PaymentRequest. Chỉ những field có mục đích điều tra cụ thể mới được chọn.

Không dùng:

~~~java
log.info("Payment request: {}", request);
log.debug("Headers: {}", allHeaders);
log.info("User: {}", user);
~~~

Những lời gọi trên có thể kích hoạt toString() hoặc serializer chứa fields nhạy cảm, kể cả khi người viết chỉ định log mức DEBUG. Tắt DEBUG ở production không phải biện pháp bảo vệ duy nhất: log level có thể đổi, exception hoặc logger khác vẫn có thể ghi cùng object.

## 4. Phân biệt masking, redaction, hashing, tokenization và encryption

| Kỹ thuật | Cách hoạt động | Ví dụ | Giới hạn |
| --- | --- | --- | --- |
| **Masking** | Che một phần giá trị nhưng giữ một phần để nhận diện. | a***@example.com | Phần còn lại vẫn có thể là PII; không phù hợp cho secrets. |
| **Redaction** | Loại bỏ giá trị hoặc thay bằng dấu đại diện. | Authorization: [REDACTED] | Mất khả năng xem giá trị gốc; phải áp dụng trên mọi đường ghi. |
| **Hashing** | Biến đổi một chiều thành digest. | Hash của reference. | Giá trị entropy thấp có thể bị dò; hash ổn định vẫn liên kết hoạt động. |
| **Tokenization** | Thay giá trị bằng token; mapping được bảo vệ ở hệ thống khác. | Card reference thành token. | Cần token vault và kiểm soát quyền truy cập mapping. |
| **Encryption** | Mã hóa có thể giải mã bằng key. | Field được mã hóa trong storage. | Người có key vẫn giải mã; không thay thế data minimization. |

### Khi nào dùng kỹ thuật nào?

- Password, access token, API key và private key: **không log**. Nếu đã đi vào pipeline, loại bỏ giá trị và cân nhắc rotate/revoke credential.
- Email hoặc số điện thoại: thường nên redaction hoặc mask theo yêu cầu. Chỉ dùng hash khi có mục đích liên kết rõ, kiểm soát phù hợp và đánh giá nguy cơ dò ngược.
- Payment/card data: không log dữ liệu nhạy cảm; dùng reference/token được hệ thống thanh toán thiết kế để xuất hiện trong log.
- Request ID do hệ thống tạo: có thể ghi nếu không chứa dữ liệu định danh và retention phù hợp.
- Password: không hash rồi ghi log. Hash password phục vụ lưu trữ xác thực là quy trình riêng; log không phải nơi lưu verifier.

Masking không biến dữ liệu thành vô danh tự động. Email bị che một phần vẫn có thể nhận diện người dùng khi kết hợp timestamp, tenant và địa chỉ IP. Đánh giá toàn bộ ngữ cảnh có thể tái nhận diện.

## 5. Ưu tiên ngăn ghi ở nguồn

Biện pháp hiệu quả nhất là không đưa dữ liệu nhạy cảm vào log event ngay từ đầu. Cách này giảm phụ thuộc vào regex, appender và pipeline downstream.

### Không log toàn bộ request/response

Thay vì serialize request, chọn thông tin vận hành:

~~~java
log.atInfo()
        .addKeyValue("operation", "order.create")
        .addKeyValue("http.route", "/orders")
        .addKeyValue("http.status_code", 201)
        .addKeyValue("order.item_count", request.items().size())
        .log("Order created");
~~~

Không ghi request body chỉ để biết request đi qua endpoint nào. Nếu cần điều tra payload lỗi, tạo bản mô tả đã lọc với schema rõ ràng, giới hạn kích thước và quyền truy cập.

### Không log credential hoặc header nguyên bản

~~~java
// Không nên: header map có thể chứa Authorization và Cookie.
log.debug("Outbound headers: {}", headers);

// Nên: chỉ ghi thuộc tính an toàn đã chọn.
log.debug("Calling inventory service, method={}, route={}",
        "POST", "/inventory/reserve");
~~~

Nếu cần biết authentication scheme, chỉ ghi giá trị đã phân loại như auth.scheme=bearer; không log raw Authorization header.

### Không dựa vào toString()

Không ghi trực tiếp DTO, entity hoặc object từ thư viện nếu chưa kiểm tra implementation toString(), JSON annotations và custom serializer. Thay đổi model trong tương lai có thể thêm field mới khiến log bắt đầu chứa dữ liệu nhạy cảm mà code logging không đổi.

Tạo một log view/record riêng chỉ bao gồm field cho phép. Không tái sử dụng request DTO như log schema.

## 6. Masking trong SLF4J và Logback

Spring Boot thường sử dụng SLF4J facade với Logback làm logging backend mặc định. Có thể dùng structured logging và một lớp xử lý/filter trước appender hoặc trước khi forward sang telemetry.

Ví dụ một bộ chuyển đổi giá trị ở tầng ứng dụng:

~~~java
public final class SensitiveDataMasker {

    private SensitiveDataMasker() {
    }

    public static String maskEmail(String email) {
        if (email == null || email.isBlank()) {
            return email;
        }

        int at = email.indexOf('@');
        if (at <= 1 || at == email.length() - 1) {
            return "[REDACTED]";
        }

        return email.charAt(0) + "***" + email.substring(at);
    }

    public static String redactSecret(String value) {
        return value == null ? null : "[REDACTED]";
    }
}
~~~

Hàm trên chỉ minh họa masking một loại field. Nó không phải bộ lọc tổng quát cho arbitrary log text. Không dùng hàm email đơn giản làm biện pháp duy nhất vì email có định dạng phức tạp và dữ liệu có thể nằm trong JSON, exception hoặc header.

Cách gọi:

~~~java
log.atInfo()
        .addKeyValue("customer.email",
                SensitiveDataMasker.maskEmail(customer.email()))
        .addKeyValue("operation", "profile.lookup")
        .log("Customer profile lookup");
~~~

Với secrets, ưu tiên không đưa vào event. Nếu cần xác nhận header đã tồn tại, chỉ ghi boolean hoặc loại authentication:

~~~java
log.atDebug()
        .addKeyValue("authorization.present", authorizationHeader != null)
        .log("Outbound authentication metadata prepared");
~~~

### Filter ở Logback

Logback filter hoặc converter có thể áp dụng biến đổi ở logging backend. Tuy nhiên, vị trí cụ thể rất quan trọng:

- Filter chỉ quyết định event được chấp nhận/từ chối; không phải mọi filter đều sửa body/arguments.
- Converter thường biến đổi phần trình bày trong layout; nếu OTel appender hoặc file appender đọc raw event/structured arguments thì layout masking có thể không bảo vệ các đường đó.
- TurboFilter có thể ngăn event trước khi tạo output nhưng không tự đảm bảo redact mọi field.
- Appender riêng có thể chuẩn hóa event thành schema an toàn trước khi export.

Nếu dùng Logback masking, hãy xác định raw event được đọc ở đâu và kiểm thử tất cả appenders. Mask một chuỗi trong console layout không chứng minh JSON appender, file appender, async appender hoặc OpenTelemetry appender cũng đã được bảo vệ.

## 7. Structured logging và schema an toàn

Structured logging làm rõ field nào được phép ghi, giảm việc parse message text bằng regex.

~~~json
{
  "event.name": "payment.authorization",
  "operation": "authorize",
  "outcome": "rejected",
  "payment.reference": "pay_ref_7f31",
  "error.type": "LimitExceededException"
}
~~~

Schema không chứa PAN, security code, bearer token, customer email hoặc payload thanh toán. Các field nên có kiểu và ngữ nghĩa ổn định để truy vấn giữa nhiều service.

### Dùng safe event object

~~~java
public record PaymentLogEvent(
        String operation,
        String outcome,
        String paymentReference,
        String errorType) {
}
~~~

~~~java
PaymentLogEvent event = new PaymentLogEvent(
        "authorize",
        "rejected",
        paymentReference,
        "LimitExceededException");

log.atWarn()
        .addKeyValue("operation", event.operation())
        .addKeyValue("outcome", event.outcome())
        .addKeyValue("payment.reference", event.paymentReference())
        .addKeyValue("error.type", event.errorType())
        .log("Payment authorization rejected");
~~~

Payment reference phải là identifier được phép log theo policy, không phải số thẻ hoặc token xác thực. Không lấy toàn bộ exception message làm error.type; dùng class/category ổn định và message đã được kiểm soát.

## 8. Exception và stack trace cũng có thể lộ dữ liệu

Lỗi từ downstream có thể chứa URL đầy đủ, query string, request body hoặc response body. Exception có thể nhúng giá trị đầu vào trong message. Ghi nguyên exception hữu ích ở nhiều trường hợp để điều tra, nhưng phải đánh giá nội dung và đường truyền.

Không nên:

~~~java
log.error("Payment failed for request {}", request, exception);
~~~

Cách an toàn hơn là log operation, safe reference, error category và exception theo policy:

~~~java
log.atError()
        .addKeyValue("operation", "payment.authorize")
        .addKeyValue("payment.reference", safePaymentReference)
        .addKeyValue("error.type", exception.getClass().getSimpleName())
        .log("Payment authorization failed");
~~~

Nếu cần stack trace, kiểm tra cause/message của exception trước khi forward. Có thể dùng exception mapping tại boundary để chuyển thành error type ổn định; đồng thời giữ exception gốc trong kênh debug hạn chế quyền nếu policy cho phép. Không bỏ mọi stack trace vì điều đó có thể làm mất bằng chứng quan trọng.

Chỉ thay message không đảm bảo throwable không bị đính kèm bởi overload logger khác. Kiểm tra chữ ký log call thực tế và output cuối cùng.

## 9. MDC, trace context và baggage

MDC thường lưu các trường correlation như request ID, tenant class hoặc trace ID để chúng xuất hiện trong log pattern. Dữ liệu nhạy cảm đặt vào đây có thể được thêm vào rất nhiều log events.

Không đưa raw email hoặc token vào MDC:

~~~java
MDC.put("user.email", user.email());
MDC.put("authorization", bearerToken);
~~~

Chỉ thêm field cần thiết và đã được duyệt:

~~~java
MDC.put("request.id", requestId);
MDC.put("tenant.tier", verifiedTenantTier);
try {
    orderService.create(request);
} finally {
    MDC.remove("request.id");
    MDC.remove("tenant.tier");
}
~~~

Dùng try/finally để tránh context rò sang request tiếp theo trên cùng thread. Với async/reactive, dùng cơ chế context propagation tương ứng; không giả định MDC tự truyền đúng qua mọi executor.

Micrometer Tracing có thể đưa trace ID/span ID vào MDC. Điều này hỗ trợ correlation nhưng không biến mọi baggage fields thành an toàn. Chỉ đưa baggage field đã allowlist vào logging correlation. Tránh ghi raw baggage map hoặc toàn bộ HTTP/gRPC metadata.

## 10. Bảo vệ traces và OpenTelemetry attributes

Dữ liệu nhạy cảm có thể rò qua trace/span attributes dù log statements đã được mask. Instrumentation tự động có thể thu thập URL, route, database statement, exception event hoặc request attributes.

Các điểm cần kiểm tra:

- URL có query parameters chứa token/email không.
- Database statement có literal dữ liệu khách hàng không.
- Exception event/message có payload nhạy cảm không.
- Baggage có được propagate tới các service không cần biết dữ liệu đó không.
- Span attributes có chứa user ID, account ID hoặc dữ liệu định danh không.
- Collector có processor/filter để xóa hoặc transform attributes trước khi export backend không.

Ưu tiên không tạo attribute nhạy cảm ở nguồn. Collector filtering là lớp phòng vệ bổ sung nhưng không thay thế ngăn ghi dữ liệu trong ứng dụng. Khi gửi dữ liệu tới Collector, một số thông tin đã đi qua network và có thể được ghi nhận ở agent/proxy trước khi processor lọc.

Micrometer Observation low-cardinality/high-cardinality key-values cũng cần quy tắc phân loại tương tự. Không gắn email, bearer token hoặc raw payload vào observation context. High-cardinality không có nghĩa là field an toàn để export.

## 11. Masking headers và metadata trong HTTP/gRPC

HTTP headers và gRPC metadata thường chứa thông tin xác thực hoặc session. Không log toàn bộ collection.

Các key cần loại bỏ hoặc xử lý đặc biệt:
- Authorization
- Proxy-Authorization
- Cookie và Set-Cookie
- X-Api-Key hoặc header API key riêng
- Session, CSRF và password reset headers
- Header tùy chỉnh chứa identity/credential

Ví dụ allowlist header:

~~~java
private static final Set<String> SAFE_HEADERS = Set.of(
        "content-type",
        "accept",
        "user-agent",
        "x-request-id"
);

public static Map<String, String> safeHeaders(
        Map<String, String> headers) {
    Map<String, String> safe = new LinkedHashMap<>();
    headers.forEach((name, value) -> {
        String normalized = name.toLowerCase(Locale.ROOT);
        if (SAFE_HEADERS.contains(normalized)) {
            safe.put(normalized, value);
        }
    });
    return safe;
}
~~~

Đây là ví dụ allowlist cho map đơn giản; ứng dụng thật cần xử lý nhiều header values, case-insensitivity và dữ liệu từ proxy. Không thêm header vào allowlist chỉ vì tên quen thuộc; hãy kiểm tra nội dung và nguồn của nó.

Đối với gRPC, áp dụng nguyên tắc tương tự với Metadata. Không serialize toàn bộ metadata vì có thể chứa authorization, binary entries và propagation fields. W3C trace context/baggage chỉ nên được chuyển vào log theo policy riêng; raw baggage không mặc định an toàn.

## 12. Redaction ở Collector và backend

Collector có thể là lớp kiểm soát tập trung cho telemetry đến từ nhiều service. Tùy phiên bản và distribution, có thể sử dụng processors để xóa/transform attributes hoặc lọc logs trước khi export.

~~~mermaid
flowchart LR
    App["Spring Boot app"]
    App --> Source["Safe logging tại nguồn"]
    Source --> Agent["Agent / Collector receiver"]
    Agent --> Filter["Redaction / allowlist processor"]
    Filter --> Backend["Logs / traces backend"]
    Backend --> Access["RBAC, retention, audit"]
~~~

Không dùng một Collector processor config chung mà chưa kiểm tra version/distribution. Xác minh processor có trong binary không, áp dụng cho logs hay traces, và hỗ trợ xóa nested attributes/body ở mức nào.

Nguyên tắc:
- Đặt filter trước exporter ra backend.
- Bảo vệ queue, debug exporter và internal telemetry; chúng cũng có thể giữ dữ liệu nhạy cảm.
- Không bật debug logging của Collector trong production nếu nó có thể in raw payload.
- Kiểm tra cả logs pipeline và traces pipeline.
- Giữ audit cho thay đổi policy/processor.
- Xác nhận bản đã lọc là bản duy nhất đến hệ thống lưu trữ được phép.

Redaction tại Collector không che dữ liệu đã đi vào file appender, container stdout, sidecar hoặc network proxy trước đó. Kiểm kê tất cả đích nhận telemetry.

## 13. Regex masking: dùng có giới hạn

Regex có thể giúp nhận diện pattern đơn giản trong text, nhưng không phải bộ phân loại dữ liệu hoàn chỉnh.

Regex dễ thất bại khi:
- Token được chia qua nhiều dòng hoặc encode URL/base64.
- JSON có escape characters hoặc nested objects.
- Authorization header viết hoa/thường khác nhau.
- Exception message có URL/query parameters.
- Giá trị xuất hiện trong field có tên bất ngờ.
- PII có định dạng quốc tế hoặc dấu phân cách khác nhau.

Nếu dùng regex:
1. Áp dụng trên field cụ thể thay vì quét toàn bộ message khi có thể.
2. Test valid, invalid, null, Unicode, multiline và adversarial inputs.
3. Giới hạn input và tránh regex có nguy cơ backtracking tốn CPU.
4. Không dựa vào regex để phát hiện mọi secrets.
5. Đo false positives/false negatives.
6. Vẫn dùng allowlist và ngăn ghi ở nguồn làm lớp chính.

Không mask mọi chuỗi trông giống số thẻ bằng regex chung nếu chưa hiểu false positives; cũng không để regex thay thế việc không log dữ liệu đó.

## 14. Kiểm thử bảo đảm dữ liệu không lọt vào output

Kiểm thử phải xem **output thực tế của appender/pipeline**, không chỉ assert hàm masker trả về một chuỗi.

### Unit test cho masker

~~~java
class SensitiveDataMaskerTest {

    @Test
    void masksEmailLocalPart() {
        assertEquals(
                "a***@example.com",
                SensitiveDataMasker.maskEmail("alice@example.com"));
    }

    @Test
    void redactsSecretCompletely() {
        assertEquals(
                "[REDACTED]",
                SensitiveDataMasker.redactSecret("top-secret-token"));
    }
}
~~~

### Test output của logger

Dùng appender test hoặc OutputCaptureExtension của Spring Boot để ghi event rồi kiểm tra:
- Giá trị secret giả định không xuất hiện.
- Placeholder hoặc field đã mask xuất hiện đúng.
- Exception message/cause không vô tình ghi raw input.
- MDC được xóa sau request.
- Async event không nhận context của request trước.
- JSON appender và OpenTelemetry appender cùng tuân thủ policy.

Test dùng canary strings dễ tìm, ví dụ CANARY_PASSWORD_91 hoặc CANARY_TOKEN_72, không dùng secrets thật. Assert cả output được phép và việc chuỗi gốc không xuất hiện trong toàn bộ logs capture.

### Test negative cases

Kiểm thử header thiếu/null hoặc viết hoa/thường khác nhau; nhiều giá trị header; baggage field lạ; exception có URL query parameter; JSON lồng nhau và multiline; Unicode và giá trị rất dài; dữ liệu encoded hoặc có dấu phân cách khác.

Masker có unit test pass vẫn có thể bị bypass bởi appender khác, toString(), error handler hoặc agent. Integration test cần bao phủ các đường ghi thật của ứng dụng.

## 15. Quyền truy cập, retention và xử lý sự cố

Masking giảm rủi ro nhưng không thay thế các biện pháp bảo vệ logs:

- Dùng RBAC với quyền tối thiểu; developer không mặc định cần truy cập production logs toàn bộ.
- Chia tenant/environment và giới hạn truy vấn theo vai trò.
- Thiết lập retention phù hợp mục đích và yêu cầu áp dụng.
- Mã hóa khi truyền và khi lưu; quản lý key độc lập với dữ liệu.
- Audit hoạt động export, query, download và thay đổi retention.
- Giới hạn dữ liệu trong alert/notification vì alert có thể gửi ra email/chat.
- Kiểm soát backup, archive và log shipping; xóa ở backend chính không đồng nghĩa mọi bản sao đã bị xóa.

### Khi phát hiện secret hoặc PII trong logs

1. Xác định field, khoảng thời gian, service và tất cả destinations đã nhận dữ liệu.
2. Ngăn log tiếp tục chứa field đó bằng source fix/filter đã kiểm chứng.
3. Nếu đó là credential, phối hợp rotate/revoke theo incident policy.
4. Xác định bản sao ở stdout, files, sidecars, Collector queues, backend, backups và exports.
5. Hạn chế truy cập và retention theo quy trình sự cố; không tự ý xóa bằng chứng cần bảo toàn.
6. Phối hợp security/privacy owner để quyết định purge, notification và nghĩa vụ báo cáo.
7. Thêm test hồi quy và kiểm tra lại toàn bộ logging paths.

Đừng đưa chính giá trị bị lộ vào ticket/chat để minh họa. Dùng tên field, loại dữ liệu, service và thời điểm; giữ giá trị cụ thể trong kênh incident được phê duyệt nếu thật sự cần.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Console đã mask nhưng backend vẫn có secret | Mask chỉ ở console layout, OTel/file appender đọc raw event. | Kiểm thử từng appender và exporter độc lập. |
| Token xuất hiện trong exception | HTTP client hoặc thư viện nhúng request headers/URL vào message. | Kiểm tra exception message/cause và dùng error mapping an toàn. |
| MDC rò dữ liệu sang request khác | Không clear context trong finally hoặc async propagation sai. | Kiểm tra cleanup và executor/reactive lifecycle. |
| PII xuất hiện trong trace nhưng không có trong log | Auto-instrumentation tạo span attributes hoặc exception events. | Kiểm tra raw spans và Collector trace processors. |
| Regex không che hết dữ liệu | Encoding, nested JSON, field name khác hoặc multiline. | Bổ sung schema allowlist và test negative cases. |
| Field bị mask quá rộng | Regex false positive hoặc mask toàn message. | Chỉ xử lý field nhạy cảm cụ thể, dùng safe attributes. |
| Log vẫn chứa password dù không ghi trực tiếp | Object toString/serializer hoặc request dump. | Tránh serialize object; dùng log event schema riêng. |
| Collector đã redaction nhưng sidecar file còn raw | Lọc sau khi log đã được ghi ở destination khác. | Kiểm kê destinations và đặt ngăn chặn ở nguồn. |
| Hash vẫn cho phép liên kết người dùng | Hash ổn định hoặc dữ liệu đầu vào dễ đoán. | Đánh giá entropy/linkability; cân nhắc tokenization hoặc loại bỏ. |
| Alert gửi kèm PII | Notification template copy message/attributes nguyên bản. | Áp dụng allowlist/redaction cho alert payload. |

## 17. Runbook: xác minh masking trong Spring Boot

1. **Lập danh sách dữ liệu:** secrets, PII, payment data, identifiers và fields nội bộ theo policy.
2. **Lập bản đồ logging paths:** SLF4J/Logback appenders, stdout, files, agent, OTel bridge, Collector và backend.
3. **Tìm điểm tạo dữ liệu:** request/response logging, object serialization, exception mapping, MDC, baggage và instrumentation.
4. **Thiết kế schema allowlist:** liệt kê field được ghi, kiểu dữ liệu, owner và mục đích.
5. **Ngăn ghi ở nguồn:** thay raw object/header/body bằng safe event fields.
6. **Thêm redaction bổ sung:** filter/appender/Collector cho dữ liệu không thể loại bỏ hoàn toàn tại nguồn.
7. **Test canary values:** tạo dữ liệu giả dễ tìm và kiểm tra toàn bộ output destinations.
8. **Test lỗi và async:** exception chains, thread pools, Reactor, HTTP/gRPC metadata và shutdown.
9. **Đo chi phí:** xác nhận redaction không tạo CPU spike, log volume lớn hoặc regex backtracking.
10. **Xác minh backend:** tìm canary raw value và masked value; raw value không được tồn tại ở bất kỳ index/destination nào trong test.
11. **Kiểm tra quyền và retention:** xác minh RBAC, audit, backup và log shipping.
12. **Lưu bằng chứng:** policy version, test results, owners và ngày review.

## 18. Bài tập tự kiểm tra

### Bài 1 — Mask ở console có đủ không?

Ứng dụng mask Authorization trong Logback console pattern nhưng vẫn có JSON file appender và OpenTelemetry appender. Có thể kết luận secret đã được bảo vệ không?

**Đáp án:** Không. Layout console chỉ ảnh hưởng cách trình bày tại appender đó. Các appender khác có thể đọc raw event/arguments. Phải kiểm thử từng destination hoặc chuẩn hóa thành safe event schema trước khi fan-out.

### Bài 2 — Hash email trước khi log

Một nhóm hash email SHA-256 rồi ghi vào log để tìm các request của cùng người dùng. Cách này có an toàn tuyệt đối không?

**Đáp án:** Không. Email có entropy thấp và có thể bị dò bằng dictionary; hash ổn định còn cho phép liên kết các hoạt động. Đánh giá mục tiêu, quyền truy cập và linkability; cân nhắc tokenization hoặc reference do hệ thống tin cậy cấp.

### Bài 3 — Exception chứa token

Log không ghi Authorization header trực tiếp nhưng HTTP client exception chứa URL có query parameter access_token. Cần sửa ở đâu?

**Đáp án:** Kiểm soát URL/credential ở nguồn, không đưa secret vào query string nếu giao thức cho phép header an toàn hơn, và xử lý exception message/cause trước khi log/export. Không chỉ dựa vào filter header.

### Bài 4 — MDC bị rò

Một request đặt user identifier vào MDC, sau đó request tiếp theo trên cùng thread nhìn thấy giá trị cũ. Nguyên nhân và cách sửa?

**Đáp án:** MDC không được clear khi request trước hoàn tất. Đặt và xóa field trong try/finally hoặc dùng cơ chế request/context scope phù hợp; kiểm tra thêm async propagation.

### Bài 5 — Collector redaction

Collector loại bỏ field customer.email trước khi export backend. Điều này có bảo đảm file log trong container không có email?

**Đáp án:** Không. File/stdout có thể được ghi trước khi telemetry đến Collector. Cần ngăn ghi ở nguồn và kiểm tra mọi destination đã nhận dữ liệu.

### Bài 6 — Baggage thành log fields

Ứng dụng copy tất cả baggage vào MDC để tiện debug. Rủi ro là gì?

**Đáp án:** Baggage inbound có thể do caller kiểm soát, chứa PII/secret hoặc giá trị cardinality cao. Chỉ copy field allowlist, đã xác minh và có mục đích; không log toàn bộ baggage map.

## 19. Checklist triển khai

- [ ] Có data classification policy cho secrets, PII, payment data và identifiers.
- [ ] Log statements ưu tiên allowlist fields và safe event objects.
- [ ] Không serialize trực tiếp request/response, entity hoặc object chưa rà soát.
- [ ] Không ghi password, access token, API key, cookie, private key hoặc security code.
- [ ] Email/phone/PII được loại bỏ hoặc mask theo policy; đánh giá nguy cơ tái nhận diện.
- [ ] Hashing/tokenization chỉ dùng khi có mục đích, entropy và access policy phù hợp.
- [ ] Exception messages, causes và stack traces được kiểm tra trước khi export.
- [ ] MDC chỉ chứa correlation fields được phép và được cleanup đúng lifecycle.
- [ ] Baggage, trace/span attributes và HTTP/gRPC metadata có allowlist riêng.
- [ ] Mọi appender, agent và Collector pipeline đều được kiểm tra; console masking không đủ.
- [ ] Collector redaction là lớp bổ sung, không phải lớp bảo vệ duy nhất.
- [ ] Regex có test adversarial, giới hạn input và không thay thế schema allowlist.
- [ ] Integration tests dùng canary strings xác nhận raw value không xuất hiện ở output.
- [ ] RBAC, retention, encryption, audit và backup policy đã được rà soát.
- [ ] Có incident runbook và quy trình rotate/revoke credential nếu bị lộ.
- [ ] Alert/notification templates không sao chép dữ liệu nhạy cảm.

**Ghi nhớ:** Bảo vệ log hiệu quả bắt đầu bằng việc **không ghi dữ liệu nhạy cảm**. Dùng schema allowlist và safe event fields tại nguồn, bổ sung masking/redaction ở logging pipeline và Collector, rồi kiểm thử mọi destination gồm file, stdout, traces và backend. Masking, hashing hay encryption không tự động làm dữ liệu vô danh hoặc an toàn; policy phải xét cả khả năng liên kết, quyền truy cập, retention và toàn bộ đường đi của telemetry.
