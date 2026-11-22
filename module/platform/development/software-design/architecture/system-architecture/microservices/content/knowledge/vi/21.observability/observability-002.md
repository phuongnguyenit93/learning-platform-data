# Nhật ký có cấu trúc và định danh yêu cầu nhất quán

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Quan sát hệ thống. Nội dung hướng dẫn thiết kế structured logging và cơ chế correlation ID/request ID để truy vết một yêu cầu đi qua nhiều dịch vụ, luồng bất đồng bộ và message broker; đồng thời liên kết log với distributed trace, bảo vệ dữ liệu nhạy cảm và giữ chi phí quan sát ở mức hợp lý.

## 1. Vì sao log thông thường không đủ cho microservices?

Trong ứng dụng đơn khối, một lỗi có thể được nhìn thấy trong cùng một log file. Trong microservices, một thao tác “đặt hàng” có thể lần lượt đi qua API Gateway, Order Service, Inventory Service, Payment Service, Kafka và Notification Service. Mỗi service có nhiều replica, xử lý đồng thời hàng nghìn request, triển khai độc lập và có thể phát log vào các hệ thống khác nhau.

Ví dụ các dòng log rời rạc:

~~~text
12:00:01 request received
12:00:01 calling payment
12:00:02 timeout
12:00:02 retry attempt
12:00:03 request completed
~~~

Những dòng trên không cho biết retry thuộc request nào, replica nào phát sinh lỗi, có cùng transaction với “request completed” hay không, và log ở service kế tiếp có liên quan hay không. Việc ghép log theo timestamp đơn thuần rất dễ sai khi có concurrency, clock skew, queue và retry.

Hai khả năng cần phối hợp:

1. **Structured logging:** mỗi sự kiện log được ghi bằng schema thống nhất, thường dạng một JSON object trên một dòng. Các trường timestamp, severity, service, event, request_id, trace_id, outcome… có kiểu dữ liệu và ý nghĩa rõ ràng, giúp lọc và tổng hợp tự động.
2. **Consistent request/correlation identity:** một định danh được tạo hoặc chấp nhận theo quy tắc tại điểm nhận tải, sau đó được truyền qua các hop thuộc cùng request. Người vận hành có thể lọc các log bằng cùng ID để dựng lại hành trình xử lý.

Đây là hai khả năng khác nhau nhưng bổ trợ nhau. Có JSON log mà thiếu ID thì vẫn khó nối các dịch vụ; có request ID nhưng mỗi service đặt tên field khác nhau hoặc log là text tự do thì vẫn khó tìm kiếm.

**Mục tiêu:** Khi có một request lỗi, đội vận hành có thể bắt đầu từ một mã được trả về cho client hoặc từ trace_id, tìm đúng các sự kiện liên quan, xác định điểm nghẽn và loại lỗi, kiểm tra kết quả nghiệp vụ, mà không phải truy cập tất cả container hay suy đoán bằng giờ phút.

## 2. Ba tín hiệu quan sát và vai trò của log

Observability thường sử dụng ba loại tín hiệu:

| Tín hiệu | Câu hỏi trả lời tốt | Ví dụ |
| --- | --- | --- |
| Metrics | Có bao nhiêu lỗi, độ trễ và tỷ lệ tăng ra sao? | HTTP 5xx rate, p99 latency, queue depth |
| Logs | Chính xác sự kiện gì xảy ra, trong ngữ cảnh nào? | payment authorization failed, provider error code |
| Traces | Request đi qua các span/service nào, chậm ở đâu? | Gateway 15 ms → Order 120 ms → Payment 450 ms |

Một hệ thống tốt cho phép đi từ metric cảnh báo → exemplar/trace → log liên quan. Ví dụ metric cho thấy p99 của POST /orders tăng; trace cho biết Payment Service chậm; log tại span đó chứa reason code đã được chuẩn hóa và thông tin retry đã được kiểm soát.

**Không dùng log để thay thế mọi metric:** mỗi request tạo nhiều log sẽ khiến việc đếm tần suất đắt và chậm. **Không dùng trace để thay thế mọi audit event:** sampling có thể làm mất trace của một giao dịch cần lưu vết bắt buộc. Và **audit log** có yêu cầu tính toàn vẹn, quyền truy cập và retention riêng, không nên trộn với debug log thông thường.

## 3. Định nghĩa rõ các loại định danh

| Định danh | Ý nghĩa | Vòng đời thường gặp |
| --- | --- | --- |
| request_id | Nhận diện một request được xử lý qua các hop, có thể hiển thị cho client | Từ edge đến khi request kết thúc |
| correlation_id | Gom các hoạt động thuộc một quy trình logic; có thể trải qua nhiều request/message | Một workflow, job, saga hoặc phiên xử lý |
| trace_id | Định danh một distributed trace theo hệ tracing | Nhiều span trong một trace |
| span_id | Định danh một đơn vị thao tác trong trace | Một span của service |
| parent_span_id | Quan hệ cha-con giữa các span | Từng đoạn trace |
| message_id | Định danh một message/envelope cụ thể | Một message tại broker |
| causation_id | Sự kiện hoặc message trực tiếp gây ra sự kiện hiện tại | Mỗi bước trong chuỗi event |
| job_id | Định danh job bất đồng bộ đã được chấp nhận | Đến khi job hoàn tất/hết hạn lưu |
| business_id | Order ID, payment ID, shipment ID… | Theo vòng đời entity nghiệp vụ |

**Không đồng nhất tất cả ID.** Một đơn hàng có thể phát nhiều request và nhiều trace; một HTTP request có thể khởi tạo nhiều message; một message được delivery lại có thể dẫn đến nhiều execution span. Nếu hệ thống chỉ có một field tên “id”, người đọc rất dễ ghép sai các sự kiện.

Quy tắc thông dụng:

- **request_id:** bảo toàn qua các service xử lý cùng request, để hỗ trợ support và truy vấn log.
- **trace_id:** để hệ tracing sinh/lan truyền theo tiêu chuẩn; giữ riêng với request_id. Khi có trace_id, mỗi log có thể đính kèm trace_id và span_id hiện tại.
- **correlation_id:** theo workflow nghiệp vụ kéo dài, được thiết kế rõ khi request ban đầu phát sinh job hoặc event. Nếu không có workflow riêng, hệ thống có thể sử dụng request_id làm giá trị khởi tạo nhưng phải giải thích lúc nào tách nhánh/tạo request mới.
- **business_id:** dùng như trường bổ sung khi được phép; không dựa vào nó để thay thế request ID vì một order có thể có nhiều lần thao tác và retry.

**Request ID không phải token xác thực.** Không cấp đặc quyền, không xác minh danh tính client và không cho phép xem dữ liệu chỉ vì người gửi biết request_id. Mã hỗ trợ hiển thị cho khách hàng cần không chứa PII và có thể bị lộ mà không gây lộ tài nguyên.

## 4. Thiết kế schema log thống nhất

Một log event lý tưởng là một JSON object trên một dòng, có trường cơ bản nhất quán:

~~~json
{
  "timestamp": "2026-11-12T02:17:31.841Z",
  "severity": "INFO",
  "service.name": "order-service",
  "service.version": "1.8.0",
  "deployment.environment": "production",
  "event.name": "http.server.request.completed",
  "message": "Request completed",
  "request_id": "7d2d33db-1235-4ed7-890a-15d0f74a52f2",
  "trace_id": "5b8aa5a0a3d9497db2d2d6af63a9f11e",
  "span_id": "014b4b5c6d7e8f90",
  "http.request.method": "POST",
  "http.route": "/orders/{orderId}/pay",
  "http.response.status_code": 202,
  "duration_ms": 84,
  "outcome": "accepted"
}
~~~

Giá trị trên chỉ là dữ liệu minh họa. Trường **http.route** nên là mẫu route ổn định thay vì URL thực tế chứa ID người dùng. Ví dụ trace_id theo W3C/OTel thường biểu diễn bằng 32 ký tự hex, span_id bằng 16 ký tự hex. Trường nào chưa có thông tin thì nên bỏ qua hoặc sử dụng null theo schema, **không tự tạo trace_id giả**.

### 4.1. Trường nền tảng đề xuất

| Trường | Kiểu | Mục đích |
| --- | --- | --- |
| timestamp | ISO 8601 UTC string hoặc timestamp chuẩn của collector | Sắp thứ tự và so sánh sự kiện |
| severity | Enum DEBUG/INFO/WARN/ERROR | Chọn mức quan trọng |
| service.name | String ổn định | Xác định service phát log |
| service.version | String hoặc digest được định nghĩa | Đối chiếu với release |
| deployment.environment | String | Phân biệt staging, production |
| event.name | String có cấu trúc, ít thay đổi | Phân loại sự kiện độc lập với câu chữ |
| message | String ngắn | Diễn giải cho người đọc |
| request_id | String hợp lệ | Gom log theo request |
| trace_id, span_id | String theo định dạng tracer | Liên kết distributed tracing |
| http.route / messaging.destination.name | String | Tìm endpoint hoặc topic liên quan |
| outcome | Enum accepted/succeeded/failed/rejected… | Tra cứu kết quả nhất quán |
| duration_ms | Number không âm | Phân tích độ trễ |
| error.type / error.code | String ổn định | Nhóm lỗi mà không phụ thuộc message |

Các trường optional khác: region, k8s.namespace.name, k8s.pod.name, instance ID, retry_attempt, dependency.name, queue_wait_ms, message_id, job_id, correlation_id, causation_id, payload_size_bytes. Chỉ thêm khi thực sự hỗ trợ điều tra hoặc vận hành.

Dùng **kiểu dữ liệu thật**: status code là số, duration là số hoặc histogram ở metrics, retry_attempt là số, outcome là chuỗi enum; không lưu mọi giá trị dưới dạng string chỉ vì thuận tiện cho logger.

### 4.2. Quy ước tên và version schema

Có thể dùng các thuộc tính được chuẩn hóa bởi **OpenTelemetry Semantic Conventions** khi phù hợp, ví dụ service.name, http.request.method, http.route. Nếu hệ thống muốn dùng camelCase hoặc snake_case cho field nghiệp vụ, hãy chọn một quy ước và viết mapping ở collector. Không để Order Service gọi requestId, Payment Service gọi correlationId và Gateway gọi req_id nếu cùng ý nghĩa.

Khi thay tên field hoặc đổi kiểu, cần tính tới dashboard, alert, detector, query và pipeline cũ. Có thể bổ sung **schema_version** nếu nhiều hệ thống cùng tiêu thụ log như dữ liệu hợp đồng. Trong giai đoạn migration, emit cả field cũ/mới có thời hạn, cập nhật consumer và sau đó loại bỏ dần.

## 5. Log event như dữ liệu, không phải một câu văn để parse

So sánh:

~~~text
INFO Payment failed for order 8381, error 502 from gateway after 3 retries
~~~

Với event structured:

~~~json
{
  "severity": "ERROR",
  "event.name": "payment.authorization.failed",
  "message": "Payment authorization failed",
  "order_id": "ord_8381",
  "dependency.name": "payment-provider",
  "http.response.status_code": 502,
  "retry_attempt": 3,
  "error.code": "UPSTREAM_BAD_GATEWAY",
  "outcome": "failed",
  "request_id": "b6e33821-fbc1-4bac-a353-9966e90b45e3"
}
~~~

Event name là loại sự kiện **có số lượng hữu hạn**, thay vì chuỗi chứa ID hoặc nội dung ngẫu nhiên. Ví dụ dùng payment.authorization.failed, order.created, inventory.reservation.rejected, http.server.request.completed. **Không dùng ID người dùng hay order ID trong event.name**, vì làm nổ số loại event và khó tổng hợp.

Thông điệp message nên ngắn, không phụ thuộc dấu câu hay ngôn ngữ để parse. Khi cần tìm nguyên nhân, query theo event.name, error.code, outcome, service.name, trace_id/request_id, thay vì regex trên chuỗi tự do. Dùng level nhất quán, chẳng hạn:

- **ERROR:** tác vụ/transaction lỗi hoặc service không hoàn thành nghĩa vụ; chứa error.type/code và một nguyên nhân xử lý hữu ích.
- **WARN:** điều kiện bất thường có thể phục hồi: retry gần hết budget, dependency degraded, queue quá ngưỡng; tránh WARN liên tục cho mỗi kết nối tạm thời.
- **INFO:** sự kiện vận hành quan trọng, lifecycle, request summary khi đã sampling và quyết định theo SLO.
- **DEBUG:** thông tin điều tra chi tiết, chỉ bật trong thời gian có kiểm soát, không chứa dữ liệu nhạy cảm.
- **TRACE:** mức kỹ thuật rất chi tiết, không bật rộng rãi ở production trừ khi có quota/thời hạn.

Đừng log ERROR ở mọi hop cho một exception rồi đồng thời ở Gateway, Order và Payment khiến một lỗi gốc xuất hiện thành 10 lỗi. Mỗi tầng log **ngữ cảnh mới có giá trị**; tầng chịu trách nhiệm cuối cùng ghi outcome, còn tracing giữ đường đi.

## 6. Vòng đời request ID và trách nhiệm của gateway

Một quy trình đơn giản, có tính nhất quán:

~~~text
Client
   |
   |  HTTP request
   v
Gateway / edge  -- tạo request_id mới (hoặc nhận theo policy)
   |
   |  X-Request-Id: req-...
   v
Order Service   -- giữ nguyên request_id đáng tin cậy
   |
   +--> Inventory Service -- giữ nguyên request_id
   |
   +--> Payment Service   -- giữ nguyên request_id
   |
   v
Gateway         -- trả X-Request-Id cho client
~~~

**Phải xác định trust boundary.** Header X-Request-Id là quy ước phổ biến nhưng không phải một chuẩn có bảo đảm về danh tính hoặc tính duy nhất. Client internet có thể tự gửi chuỗi tuỳ ý, trùng ID, ký tự control, newline hoặc hàng trăm KB. Vì vậy:

1. Gateway public nên **tạo canonical request ID** riêng, hoặc có quy tắc validate/normalize rõ ràng cho giá trị client gửi. Cách an toàn dễ vận hành là không tin inbound public ID và ghi mã client vào field riêng nếu thực sự cần.
2. Xóa/ghi đè header nội bộ khi traffic vào từ vùng không tin cậy. Service phía sau chỉ tiếp nhận request ID do gateway/mTLS-authenticated upstream cung cấp.
3. Giới hạn định dạng và độ dài trước khi đưa ID vào log, response header hay trace attribute.
4. Truyền **cùng giá trị canonical** qua các hop xử lý cùng request; không tạo mới ở mỗi service.
5. Trả request_id trong response header để support có điểm bắt đầu điều tra; có thể đưa vào error body có schema phù hợp.
6. Nếu request không đi qua gateway, entrypoint service phải có fallback tạo ID mới.

Dạng UUID ngẫu nhiên là một lựa chọn thực dụng (UUID v4); ID được sinh theo chuẩn khác cũng có thể sử dụng nếu đáp ứng entropy, độ dài và tính an toàn. Không dùng timestamp đơn lẻ, địa chỉ IP hoặc email để tạo request ID vì có thể trùng và lộ dữ liệu.

**Phân biệt ID truy vết với idempotency key.** Idempotency-Key giúp xử lý lại một thao tác mà không lặp tác động nghiệp vụ, còn request_id mô tả một lần đi qua hệ thống. Nhiều HTTP retry có thể dùng **cùng idempotency key nhưng các request_id khác nhau**, và đó là hành vi đúng.

## 7. HTTP propagation contract đề xuất

Tài liệu hóa hợp đồng giữa service:

| Thành phần | Header/field | Quy tắc |
| --- | --- | --- |
| Correlation nội bộ | X-Request-Id | Dùng một key nhất quán, validation, giới hạn độ dài |
| Distributed tracing | traceparent, tracestate | Theo W3C Trace Context, do tracing library quản lý |
| Business workflow | X-Correlation-Id nếu cần | Chỉ khi có hợp đồng và trust policy riêng |
| User-facing support | X-Request-Id trong response | Khách hàng cung cấp khi báo lỗi |
| Queue/message | Envelope headers | Giữ request_id, trace context và causation theo chính sách |

Một request minh họa:

~~~http
POST /orders/ord_823/pay HTTP/1.1
Host: orders.internal
X-Request-Id: 146ef21d-dc7a-41e4-8d65-25fbb7d5c1c9
traceparent: 00-5b8aa5a0a3d9497db2d2d6af63a9f11e-014b4b5c6d7e8f90-01
Content-Type: application/json

{"paymentMethodRef":"pm_test_ref"}
~~~

Khi Order Service gọi Payment Service, nó truyền request_id từ context đang xử lý và để tracing instrumentation inject traceparent hợp lệ với span hiện tại. Đừng copy một span_id cố định cho mọi outbound call; instrumentation tạo span con theo mỗi operation. Nếu ứng dụng không tham gia distributed tracing, chỉ truyền X-Request-Id thì vẫn truy vấn log được theo request, nhưng không có cây span hoặc phân tích critical path.

**Không nên tự sửa từng byte của traceparent bằng cách nối chuỗi.** Dùng SDK/instrumentation OpenTelemetry hoặc thư viện tracing tương thích, tuân thủ quy tắc trace context, sampled flag và trust boundary.

## 8. Ví dụ Java Spring Boot Servlet: tạo/giữ request_id và dọn MDC

Trong các ứng dụng Spring MVC/Servlet, **MDC (Mapped Diagnostic Context)** của SLF4J cho phép logger đọc giá trị ngữ cảnh theo luồng xử lý. Filter dưới đây giữ một request ID hợp lệ do upstream tin cậy chuyển tới, hoặc tạo UUID nếu không có/hỏng.

~~~java
package example.observability;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdFilter extends OncePerRequestFilter {
    public static final String HEADER = "X-Request-Id";

    private static final Pattern VALID_ID =
        Pattern.compile("[A-Za-z0-9_-]{1,64}");

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain
    ) throws ServletException, IOException {

        // In production, the public gateway must replace untrusted
        // client-provided X-Request-Id before forwarding.
        String incoming = request.getHeader(HEADER);
        String requestId = incoming != null &&
            VALID_ID.matcher(incoming).matches()
                ? incoming
                : UUID.randomUUID().toString();

        response.setHeader(HEADER, requestId);

        try (MDC.MDCCloseable ignored =
                 MDC.putCloseable("request_id", requestId)) {
            chain.doFilter(request, response);
        }
    }
}
~~~

**Điều kiện quan trọng:** Ví dụ trên tin một giá trị inbound đúng định dạng. Vì vậy nó phù hợp khi traffic đã qua gateway tin cậy có chính sách **ghi đè inbound client ID**. Nếu service trực tiếp public, không được xem một chuỗi “đúng regex” là trusted; tại edge tạo ID server-side và chỉ lưu client-supplied ID riêng nếu cần. Với service-to-service có nhiều đường vào, có thể dùng middleware thống nhất ở mesh/gateway, identity và chính sách riêng cho từng trust zone.

Không dùng request ID như bằng chứng rằng request là hợp lệ hoặc có quyền. Trong môi trường có proxy, load balancer và service mesh, thống nhất layer nào tạo ID, layer nào chỉ propagate và layer nào phản hồi header. Nếu có nhiều header khác nhau (X-Correlation-ID, X-Request-ID, request-id), mapping phải được khai báo, tránh việc mỗi service chọn một key.

**Dọn MDC là bắt buộc.** Servlet thread được thread pool tái sử dụng; nếu không cleanup trong finally/try-with-resources, ID cũ có thể xuất hiện trong log của request tiếp theo, làm sai toàn bộ truy vấn. Với async servlet dispatch, context cần được khôi phục ở luồng continuation; filter trên chỉ minh họa một luồng xử lý đồng bộ.

## 9. Ghi structured event bằng Java và SLF4J

SLF4J 2 cung cấp fluent API có thể đính kèm key-value khi logging backend hỗ trợ structured fields:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderController {
    private static final Logger log =
        LoggerFactory.getLogger(OrderController.class);

    public void onPaymentAccepted(
        String orderId,
        int statusCode,
        long elapsedMs
    ) {
        log.atInfo()
           .addKeyValue("event.name", "payment.request.accepted")
           .addKeyValue("order_id", orderId)
           .addKeyValue("http.response.status_code", statusCode)
           .addKeyValue("duration_ms", elapsedMs)
           .addKeyValue("outcome", "accepted")
           .log("Payment request accepted");
    }
}
~~~

**Lưu ý:** Việc dùng addKeyValue không tự đảm bảo stdout là JSON. Cần cấu hình **logging backend/encoder** thực sự serialize structured fields và MDC thành JSON. Tùy version Spring Boot/Logback/Log4j2, encoder, config và tên option khác nhau; kiểm tra phiên bản framework đang sử dụng trước khi viết cấu hình. Một pattern text có thể render các key-value ra chuỗi nhưng vẫn không phải JSON hợp lệ.

Ví dụ minh họa một JSON output mong muốn:

~~~json
{
  "timestamp": "2026-11-12T02:17:31.841Z",
  "severity": "INFO",
  "service.name": "order-service",
  "event.name": "payment.request.accepted",
  "message": "Payment request accepted",
  "request_id": "146ef21d-dc7a-41e4-8d65-25fbb7d5c1c9",
  "order_id": "ord_823",
  "http.response.status_code": 202,
  "duration_ms": 84,
  "outcome": "accepted"
}
~~~

Ở deployment, tất cả service nên dùng thư viện cấu hình logger hoặc starter observability chung có version, bộ field thống nhất và test contract. Không bắt buộc mọi service cùng ngôn ngữ; một service Go/Node.js cũng có thể xuất đúng schema JSON mà aggregator hiểu.

### 9.1. Xử lý exception

Ưu tiên log structured error tại nơi có quyết định xử lý và outcome:

~~~java
try {
    paymentClient.authorize(command);
} catch (PaymentTimeoutException ex) {
    log.atWarn()
       .addKeyValue("event.name", "payment.authorization.timeout")
       .addKeyValue("dependency.name", "payment-provider")
       .addKeyValue("error.type", "PaymentTimeoutException")
       .addKeyValue("retryable", true)
       .log("Payment authorization timed out");
    throw ex;
}
~~~

Nếu exception được ném tiếp, tầng trên chỉ nên log lại khi có thông tin mới (ví dụ request kết thúc 503), tránh ghi lặp stack trace y hệt. Với lỗi không mong đợi, ghi stack trace ở điểm chịu trách nhiệm phù hợp nhưng phải redaction các giá trị nhạy cảm từ exception và messages. Tránh log raw HTTP body, Authorization header, cookie hoặc dữ liệu card.

### 9.2. Event completion và lifecycle

Có thể log một **request summary** cuối request (method, route template, status, duration, request_id, trace_id), và thêm domain event quan trọng. Không cần log INFO mỗi khi bắt đầu vào từng class và kết thúc mọi private method. Với request lớn, tần suất log start + finish + mỗi downstream call có thể nhân lượng log lên hàng chục lần.

**Trường duration:** đo bằng đồng hồ đơn điệu (monotonic time) như System.nanoTime() để tính elapsed, rồi xuất milliseconds; không trừ hai timestamp wall-clock có thể bị NTP điều chỉnh. Timestamp log vẫn dùng UTC wall-clock để sắp sự kiện.

## 10. Distributed tracing: nối log với trace ID và span ID

Structured logging giải thích từng event; distributed tracing cho thấy quan hệ cha-con và critical path qua microservices. Nên dùng chuẩn **W3C Trace Context** với các header traceparent/tracestate và SDK/instrumentation tương thích.

~~~text
trace_id = T
  |
  +-- Gateway server span G
        |
        +-- Order Service server span O
              |
              +-- Inventory client/server spans I1/I2
              |
              +-- Payment client/server spans P1/P2
                    |
                    +-- Database span D
~~~

Mỗi span có **span_id riêng**, còn các span trong cùng trace chia sẻ trace_id. Khi ghi log ở trong span đang hoạt động, instrumentation có thể bổ sung trace_id và span_id. Trong log viewer, người vận hành lọc theo trace_id; từ tracing UI, có thể mở những log tương ứng với span cụ thể.

**Request ID và trace ID có thể khác nhau và nên giữ rõ hai trường.** Một public request có request_id do gateway tạo, trace_id do tracing SDK tạo hoặc tiếp nhận theo trace context policy. Nếu hệ thống chọn sử dụng trace_id làm correlation ID, cần đánh giá trường hợp trace không được tạo, trace sampling, retry và workflow bất đồng bộ; đừng ép hai ID thành một mà không có hợp đồng.

### 10.1. Sampling không đồng nghĩa bỏ log

Một hệ thống sampling 10% trace không có nghĩa 90% request mất request_id trong logs. Có thể tạo request_id cho mọi request, log summary theo ngân sách, giữ error logs và tracing sampling theo chính sách. Quy tắc logging và trace sampling cần độc lập nhưng tương thích để người điều tra không nhìn thấy ID mà không có khả năng tìm liên kết.

### 10.2. Baggage không phải chỗ truyền dữ liệu tùy ý

OpenTelemetry Baggage cho phép truyền key-value ngữ cảnh xuyên dịch vụ, nhưng baggage có thể được inject ra hệ thống ngoài, làm tăng header size, thậm chí lộ dữ liệu. Không đưa access token, email, địa chỉ, thông tin y tế, thanh toán hoặc toàn bộ user profile vào baggage. Với workflow ID cần truyền, quyết định dùng header riêng hay baggage theo trust policy rõ ràng; không dùng nó làm authorization context.

## 11. Propagation qua nhiều loại communication

### 11.1. HTTP REST

Tại outbound client, lấy request_id từ request context đã thiết lập; chèn X-Request-Id và để tracer inject trace context. Với retry cùng request đang xử lý, giữ request_id. Ở inbound service, validate header, đưa vào context của request, rồi clear khi hoàn tất. Không trông chờ vào thread-local cũ tồn tại khi request chuyển thread.

### 11.2. gRPC

gRPC hỗ trợ metadata. Tạo interceptor phía server/client để đọc, validate và inject request ID; tracing có interceptor/instrumentation tương ứng. Dùng key metadata hợp lệ, thường dạng chữ thường như x-request-id. Với streaming RPC, một stream có thể tồn tại lâu; có thể cần ID cho stream cùng message ID cho từng phần tử, tránh xem mọi message trong stream là cùng một thao tác nghiệp vụ.

### 11.3. Kafka, RabbitMQ và async messaging

Trong message broker, không còn HTTP request xuyên suốt theo nghĩa đồng bộ. Khi publish event, chọn các field metadata thích hợp:

~~~json
{
  "message_id": "msg_7b42",
  "event_name": "order.payment.requested",
  "correlation_id": "workflow_c938",
  "causation_id": "evt_7612",
  "origin_request_id": "146ef21d-dc7a-41e4-8d65-25fbb7d5c1c9",
  "trace_context": "in message headers",
  "event_version": 1
}
~~~

Thông thường nên đặt traceparent, correlation_id, causation_id và message_id trong **message headers/envelope** theo contract, để payload nghiệp vụ không phụ thuộc cơ chế quan sát. Các ví dụ JSON trên là biểu diễn khái niệm; trace context thực tế được inject vào header broker bằng propagator chuẩn, thay vì chuỗi placeholder.

Khi consumer nhận message:

1. Đọc và validate metadata, không tin mù quáng message từ nguồn ngoài.
2. Truy xuất message_id/correlation_id/origin_request_id; thiết lập context cho lần xử lý hiện tại.
3. Tạo hoặc tiếp tục span theo ngữ nghĩa messaging. Với nhiều producer/link, dùng span links khi phù hợp để tránh tạo quan hệ parent-child sai.
4. Ghi event nhận/xử lý/hoàn thành hoặc thất bại với cùng correlation_id và message_id.
5. Dọn context sau mỗi message, nhất là khi một worker xử lý lần lượt nhiều message.
6. Nếu sinh message mới, tạo **message_id mới** và giữ **causation_id** trỏ về event/message đã kích hoạt nó.

Một message được xử lý lại sau crash có thể giữ message_id và correlation_id nhưng có **retry_attempt**, consumer execution ID và span mới. Tránh gán mỗi lần retry một message_id khác nếu thực tế chỉ là redelivery của cùng envelope; nếu broker/retry topic tạo bản sao mới, ghi rõ original_message_id để nối hai phiên bản.

### 11.4. Scheduled jobs và batch

Scheduled task có thể không có HTTP request cha. Worker tự tạo **job_id** và **execution_id** cho mỗi lần chạy; giữ correlation_id theo workflow nếu phát message. Không dùng ID của “request gần nhất” từ MDC bị rò rỉ. Khi batch xử lý 10.000 record, một job_id bao quát toàn batch, còn record-level operation có ID riêng để tránh quá nhiều log không thể phân biệt.

## 12. MDC và lỗi mất context trong xử lý bất đồng bộ

**MDC là thread-local trong nhiều logging implementation.** Khi dùng CompletableFuture, ExecutorService, @Async, Reactor, coroutine hoặc callback, việc chuyển sang thread khác có thể làm request_id và trace_id biến mất hoặc bị trộn.

Ví dụ vấn đề:

~~~java
MDC.put("request_id", requestId);
CompletableFuture.runAsync(() -> {
    // Không được giả định MDC ở thread gốc còn ở đây.
    log.info("Async work started");
});
~~~

Có thể sử dụng một wrapper rõ ràng cho Executor ở ứng dụng dựa trên thread:

~~~java
import org.slf4j.MDC;
import java.util.Map;
import java.util.concurrent.Executor;

public final class MdcContextExecutor implements Executor {
    private final Executor delegate;

    public MdcContextExecutor(Executor delegate) {
        this.delegate = delegate;
    }

    @Override
    public void execute(Runnable command) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        delegate.execute(() -> {
            Map<String, String> old = MDC.getCopyOfContextMap();
            try {
                if (captured == null) MDC.clear();
                else MDC.setContextMap(captured);

                command.run();
            } finally {
                if (old == null) MDC.clear();
                else MDC.setContextMap(old);
            }
        });
    }
}
~~~

Wrapper minh họa **copy MDC map**, không tự propagate OpenTelemetry tracing context, security context hay transaction context. Với hệ thống dùng tracing, nên ưu tiên cơ chế context propagation được framework/instrumentation hỗ trợ, như context propagation library/task decorator tương ứng; tránh nhiều wrapper riêng độc lập xung đột nhau.

**Không sao chép credential hoặc dữ liệu cá nhân vào MDC.** MDC map cũng có thể được capture và giữ trong queue lâu hơn request; chỉ chứa ID/metadata tối thiểu.

Trong Spring WebFlux/Reactor, luồng thực thi có thể chuyển thread thường xuyên. Dùng **Reactor Context** hoặc cơ chế context propagation tích hợp framework thay vì phụ thuộc một ThreadLocal cố định. Phải test qua publishOn/subscribeOn, retry, timeout, merge/flatMap và kết thúc request để bảo đảm ID không mất hoặc lẫn giữa hai request đồng thời.

## 13. Retry, timeout, fan-out và quan hệ nhân quả

Một request có thể được retry bởi client, gateway hoặc service. Khi đó:

- **Retry trong cùng một inbound request:** giữ request_id, thêm retry_attempt; tracing có thể tạo span mới cho mỗi attempt.
- **Client gửi HTTP request mới sau timeout:** thông thường tạo request_id mới cho lần nhận mới. Để nối các lần thử cùng thao tác nghiệp vụ, dùng idempotency key và business_id phù hợp, hoặc correlation_id có quy tắc riêng.
- **Fan-out tới nhiều downstream:** mỗi branch giữ request_id; mỗi outbound call có span riêng. Nếu hai branch cùng ghi log một event, trace/span giúp phân biệt.
- **Fan-in từ nhiều message:** không ép hai trace độc lập thành một parent duy nhất; có thể dùng span links, job/workflow correlation_id và causation metadata.
- **Timeout:** việc client ngừng chờ không có nghĩa downstream đã dừng xử lý. Log cần phân biệt caller timeout, downstream completion và kết quả nghiệp vụ sau timeout.

Ví dụ log các lần thử:

~~~json
{
  "event.name": "payment.provider.call.failed",
  "request_id": "146ef21d-dc7a-41e4-8d65-25fbb7d5c1c9",
  "retry_attempt": 2,
  "max_attempts": 3,
  "error.code": "UPSTREAM_TIMEOUT",
  "dependency.name": "payment-provider",
  "duration_ms": 250,
  "outcome": "retrying"
}
~~~

Việc log retry_attempt hỗ trợ xác định retry storm, nhưng đừng đặt attempt number trong event.name. Nếu message đi qua retry topic, giữ original_message_id và correlation_id để điều tra không đứt đoạn; tránh xem một bản phát lại là giao dịch nghiệp vụ mới khi idempotency chưa rõ.

## 14. Quyền riêng tư và bảo mật trong log

Log thường được sao chép ra collector, object storage, SIEM và các dashboard có nhiều người sử dụng. Vì vậy nguyên tắc **không đưa dữ liệu nhạy cảm vào log ngay từ đầu** an toàn hơn chỉ redaction ở backend.

Không ghi:

- Password, access token, refresh token, API key, Authorization, Cookie, Set-Cookie.
- Full request/response body của thanh toán, giấy tờ định danh, dữ liệu sức khỏe, dữ liệu tài khoản.
- Thông tin thẻ thanh toán, CVV, private key, certificate private material.
- Connection URL chứa password, query string có token, DSN hoặc exception message có credential.
- Email, số điện thoại, địa chỉ, IP nếu không có nhu cầu và cơ sở lưu trữ rõ theo chính sách riêng tư.
- Session nội bộ hoặc ID có thể dùng làm bearer credential.

**Allowlist thay vì blacklist:** định nghĩa rõ từng event được phép chứa trường nào. Chẳng hạn payment.authorization.failed chỉ cần error.code, provider.name, attempt, duration và order reference được chấp thuận; không log body giao dịch.

**Redaction đa tầng:** mã ứng dụng lọc trước; logging encoder/collector áp dụng policy bổ sung để giảm thiểu lỗi; storage có access control, encryption, retention, audit. Không trông chờ regex duy nhất che mọi secret trong exception hoặc multiline stack trace.

**Header injection:** nếu request_id từ nguồn không tin cậy chứa newline/control character, nó có thể phá dòng log, tạo field giả hoặc làm hỏng JSON. Hãy validate theo allowlist ký tự, giới hạn length và bảo đảm JSON escaping qua serializer. Việc copy nguyên header vào log còn khiến attacker tạo key cardinality cực lớn.

**Correlation ID có thể là dữ liệu nhạy cảm gián tiếp:** dù bản thân không chứa PII, việc tra cứu nó có thể dẫn tới hành trình sử dụng của người dùng. Hạn chế quyền truy vấn log, xác định retention, và không cấp quyền xem log chỉ dựa vào ID.

## 15. Log pipeline từ application đến nơi tìm kiếm

Một kiến trúc phổ biến trên Kubernetes:

~~~text
Application replicas
   |
   | stdout/stderr: 1 JSON object per line
   v
Node agent / OpenTelemetry Collector / Fluent Bit
   |
   | parse, enrich metadata, redact, batch, retry
   v
Log backend / SIEM / data lake
   |
   +-- Search by request_id / trace_id / event.name
   +-- Dashboards / alerts / incident investigation
~~~

**Ứng dụng:** tạo log structured trên stdout/stderr, tránh mỗi Pod tự ghi log file local không có chiến lược thu thập. **Collector:** thêm service/namespace/pod metadata, parse JSON, chuẩn hóa timestamp/schema, lọc dữ liệu nhạy cảm, định tuyến. **Backend:** lưu trữ, index có chọn lọc, retention, quyền truy cập, truy vấn và nối với traces.

Không nên đồng thời vừa ứng dụng gửi trực tiếp ra backend vừa node agent thu thập stdout nếu không có cơ chế dedup; sẽ nhân đôi log. Nếu log quan trọng cần tính toàn vẹn, định nghĩa delivery guarantee rõ; pipeline observability thông thường có thể làm mất log khi network partition hoặc buffer đầy, không mặc nhiên đạt exactly-once.

Các điểm cần quan sát ngay trong log pipeline:

- **Dropped logs:** collector/input queue bị quá tải hoặc storage từ chối.
- **Parse errors:** application phát multiline hoặc JSON không hợp lệ.
- **Ingest lag:** timestamp event cách xa thời điểm ingest.
- **Queue/buffer usage:** collector sắp hết disk/memory.
- **Redaction failures:** phát hiện pattern credential hoặc field không có trong allowlist.
- **Indexing failures:** mapping conflict do cùng field lúc là số, lúc là string.
- **Clock sync:** NTP/UTC consistency để sắp sự kiện giữa các nút.

## 16. Giới hạn lượng log, sampling và chi phí

Một request có 12 service hop, mỗi service ghi 5 dòng INFO, ở 3.000 request/giây có thể tạo **180.000 log record/giây**, chưa kể retry và message processing. Với payload 1 KB/record, lượng thô xấp xỉ 180 MB/giây trước nén và replication. Một logging design tốt phải định nghĩa budget, không mặc định “càng nhiều càng tốt”.

Các biện pháp:

1. Ưu tiên **một log summary hữu ích cho request** ở biên; thêm domain event ở những quyết định quan trọng, bỏ log “đã vào hàm X” lặp lại.
2. INFO/DEBUG sampling theo route hoặc theo request đối với traffic thành công rất lớn, nhưng giữ metrics đầy đủ và một chính sách phù hợp với lỗi hiếm.
3. Ghi WARN/ERROR có chọn lọc, tránh một lỗi sinh stack trace ở mọi hop.
4. Rate-limit event lặp lại như dependency connection failure; ghi tổng hợp occurrence_count khi phù hợp.
5. Giới hạn field length và event size; không serialize body lớn, stack trace vô hạn hay object graph.
6. Giữ trace sampling và log sampling riêng; bảo đảm hệ thống vẫn điều tra được các request có lỗi theo retention và policy.
7. Thiết lập retention theo sensitivity, yêu cầu điều tra và chi phí; audit/security log thường có chính sách khác debug log.
8. Thử tình huống log backend không sẵn sàng; ứng dụng không được tự treo mọi request vì một logger/network sink chậm.

**Đừng biến log thành metrics bằng labels có cardinality cao.** request_id, trace_id, user_id và order_id phù hợp cho log search/tracing, nhưng **không dùng trực tiếp làm label của metric**. Metric nên dùng service, route template, outcome/error.code hữu hạn để tránh nổ số time series.

## 17. Các loại timestamp và thứ tự sự kiện

Khi trace một request qua nhiều máy, thứ tự timestamp có thể không tuyệt đối vì clock drift, asynchronous buffering và delayed ingestion. Nên:

- Dùng UTC và ISO 8601 với độ chính xác nhất quán; bật đồng bộ thời gian của host.
- Phân biệt event timestamp (lúc ứng dụng tạo log) và ingestion timestamp (lúc backend nhận log).
- Dùng duration tính bằng monotonic clock trong process, không lấy wall-clock subtraction cho latency.
- Dùng **trace relationships** và causation_id để diễn giải quan hệ nhân quả khi sự kiện gần nhau theo thời gian.
- Ghi retry_attempt, sequence number hoặc message offset nếu cần phân biệt thứ tự trong một partition.
- Không giả định Kafka offsets cho các partition khác nhau có thứ tự toàn cục.

Khi log được gửi theo batch, một event timestamp 12:00:01 có thể chỉ xuất hiện ở backend lúc 12:00:15; đây có thể là độ trễ pipeline, không phải hệ thống xử lý nghiệp vụ 14 giây.

## 18. Ví dụ điều tra sự cố end-to-end

Giả sử khách hàng nhận lỗi HTTP 503 khi thanh toán. API trả về:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
X-Request-Id: 146ef21d-dc7a-41e4-8d65-25fbb7d5c1c9

{
  "type": "https://errors.example.test/unavailable",
  "title": "Service temporarily unavailable",
  "status": 503,
  "requestId": "146ef21d-dc7a-41e4-8d65-25fbb7d5c1c9"
}
~~~

Mẫu URL error và ID chỉ để minh họa, không phải endpoint thật. Một luồng điều tra:

1. Từ request_id do client cung cấp, truy vấn tất cả log thuộc khoảng thời gian hợp lý và các service liên quan. Kiểm tra service.name, service.version, region, deployment và event.name.
2. Tìm entrypoint summary để xác định route template, status 503 và duration.
3. Lọc các event payment.provider.call.failed, retry_attempt, error.code để tìm nguyên nhân, không cần đọc payload nhạy cảm.
4. Lấy trace_id của request và mở distributed trace. Xác nhận bottleneck nằm ở network, payment provider, queue hay pool.
5. Đối chiếu metric của dependency: p99 latency, failure rate, connection saturation, circuit breaker state, retries.
6. Kiểm tra sự kiện release/config change cùng thời điểm: có đổi endpoint hoặc timeout không?
7. Xác minh tình trạng nghiệp vụ qua system-of-record bằng business_id và quyền phù hợp, vì HTTP 503 không chứng minh giao dịch đã thất bại hoàn toàn.
8. Ghi incident timeline bằng thời gian, error code, request_id/trace_id và kết luận; không copy secret hoặc dữ liệu cá nhân vào ticket.

Một truy vấn mang tính khái niệm:

~~~text
service.name IN ("gateway", "order-service", "payment-service")
AND request_id = "146ef21d-dc7a-41e4-8d65-25fbb7d5c1c9"
ORDER BY timestamp ASC
~~~

Cú pháp cụ thể phụ thuộc Elasticsearch/OpenSearch, Loki, Datadog, Splunk hay backend khác. Không nên dùng ví dụ trên làm cú pháp chuẩn cho mọi hệ thống.

## 19. Kiểm thử tính nhất quán của request ID

### 19.1. Test API entrypoint

Các kịch bản nên thực hiện:

- Request không có X-Request-Id → gateway tạo canonical ID; response trả đúng ID đó.
- Request có header hợp lệ từ upstream tin cậy → service giữ ID và log cùng ID.
- Request public tự gửi ID bất kỳ → gateway ghi đè hoặc xử lý theo trust policy đã công bố.
- Header quá dài, chứa newline/control hoặc ký tự lạ → không được đưa nguyên vẹn vào log/response.
- Nhiều request chạy song song → không có trường hợp log request A mang ID của request B.
- Request ném exception/timeout → MDC được dọn trong finally; request tiếp theo không nhiễm ID cũ.
- Async task chuyển thread → ID được propagate rõ ràng, không biến mất và không lẫn context.
- Kết quả 4xx/5xx cũng trả request_id để support có thể truy vết.

### 19.2. Integration test qua nhiều service

Ví dụ một test gọi Gateway → Order → Payment và ghi lại event vào collector test:

~~~text
Given: POST /orders/{id}/pay
When: gateway generates request_id = R
Then:
  gateway log.request_id = R
  order log.request_id = R
  payment log.request_id = R
  response X-Request-Id = R
  trace_id (when enabled) links appropriate spans
  all log lines parse as JSON using agreed schema
~~~

Với Kafka: sau khi Order tạo event, header/envelope chứa origin_request_id và correlation_id theo hợp đồng; consumer log giữ các ID đó. Khi replay event, message_id/correlation_id vẫn hỗ trợ nối lại lần xử lý, còn attempt/span có thể thay đổi.

### 19.3. Kiểm thử schema

Có thể kiểm tra log event bằng JSON Schema hoặc contract test cho các trường bắt buộc:

~~~json
{
  "type": "object",
  "required": ["timestamp", "severity", "service.name", "event.name"],
  "properties": {
    "timestamp": {"type": "string", "format": "date-time"},
    "severity": {
      "type": "string",
      "enum": ["TRACE", "DEBUG", "INFO", "WARN", "ERROR"]
    },
    "service.name": {"type": "string", "minLength": 1},
    "event.name": {"type": "string", "minLength": 1},
    "request_id": {"type": "string", "maxLength": 64},
    "duration_ms": {"type": "number", "minimum": 0}
  }
}
~~~

Schema minh họa không áp dụng cho mọi loại log. Ví dụ startup log có thể chưa có request_id, trong khi event HTTP completion nên bắt buộc có. Có thể định nghĩa schema nền chung và schema theo event.name hoặc category để kiểm tra đúng những field liên quan.

### 19.4. Kiểm thử bảo mật và vận hành

1. Chèn giá trị giả có dạng secret/test token vào inbound header/body, kiểm tra không xuất hiện trong logs hoặc collector output.
2. Gây exception chứa credential giả, xác minh redaction ở source và collector.
3. Tạo burst traffic lớn; đo application latency khi log pipeline bị chậm, queue drop và backpressure.
4. Kiểm tra quyền người dùng ở log backend; request ID không mở quyền truy cập dữ liệu.
5. Thử deployment đa replica và release rolling; các instance giữ schema, service version và correlation contract.
6. Thử log decoder sau khi đổi encoder/framework version; không phát multiline JSON không parse được.

## 20. Runbook khi ID không xuất hiện hoặc không khớp

**Triệu chứng: log Order có request_id nhưng Payment không có.**

Kiểm tra outbound client có inject header không; service mesh/proxy có strip header không; Filter/interceptor ở Payment có chạy trước logger không; async callback có mất MDC không; và Payment có tự ghi đè ID không.

**Triệu chứng: hai request đồng thời cùng request_id trong log.**

Kiểm tra gateway có vô tình dùng ID từ một singleton hay ThreadLocal không clear; client có gửi cố định request ID và gateway tin vào không; worker thread có rò MDC không; có dùng global variable cho context không.

**Triệu chứng: có trace_id nhưng không tìm được log.**

Kiểm tra logger có inject trace_id/span_id vào JSON thật không; filter của collector có drop field không; span chưa active tại thời điểm log không; trace đã sampled nhưng log event khác policy không; hoặc query sai time window/environment.

**Triệu chứng: log có request ID nhưng response không trả mã.**

Kiểm tra proxy có xóa response header, exception handler có trả response khác trước filter không, và error path có chạy qua middleware không. Với streaming response, header có thể đã được commit; phải set ID trước khi write body.

**Triệu chứng: log order theo timestamp bị đảo.**

Kiểm tra clock synchronization, event timestamp với ingestion timestamp, delayed batch, async queue và retry. Dùng span/causation_id để xác minh quan hệ trước khi kết luận điều kiện race.

**Triệu chứng: backend log tăng chi phí đột biến.**

Xem thay đổi log level, release mới ghi từng item/batch, stack trace lặp lại, collector retry, JSON payload dài và high-cardinality index. Giảm log quá chi tiết, deduplicate, sampling và đặt quota hợp lý, không xóa các audit event bắt buộc.

## 21. Hướng dẫn triển khai theo giai đoạn

**Giai đoạn 1 — Đặt contract:** chốt canonical header X-Request-Id, quy tắc trust boundary, định dạng/độ dài, cách trả response, schema field, service identity và event naming.

**Giai đoạn 2 — Instrument edge và một luồng trọng yếu:** gateway tạo canonical ID, Order/Payment giữ và propagate qua outbound HTTP. Logging encoder xuất JSON lên stdout; các event chính có request_id.

**Giai đoạn 3 — Bật distributed tracing:** triển khai W3C Trace Context và OpenTelemetry instrumentation cho HTTP/DB; ghi trace_id và span_id vào log context để nối log với trace.

**Giai đoạn 4 — Bao phủ async:** tạo hợp đồng header/envelope cho Kafka/RabbitMQ/job, quy tắc correlation_id/causation_id/message_id; xử lý MDC hoặc context propagation qua worker pools.

**Giai đoạn 5 — Chính sách bảo mật và chi phí:** event allowlist, redaction, index mapping, retention, RBAC, sampling, ingest budget; diễn tập khi backend log không sẵn sàng.

**Giai đoạn 6 — Kiểm thử và vận hành:** contract tests, concurrent request tests, async tests, dashboard, cảnh báo collector dropped logs, runbook tìm kiếm request_id và trace_id.

**Giai đoạn 7 — Chuẩn hóa liên service:** cung cấp starter/library/instrumentation được version hóa, onboarding các service còn lại, thống nhất event.name, schema_version và hướng dẫn migration field.

Một service dùng JSON nhưng không giữ ID không được coi là hoàn thành propagation; tương tự, có header ID nhưng logger không tự động đưa ID vào event thì quá trình điều tra vẫn đứt.

## 22. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Phương án phù hợp |
| --- | --- | --- |
| Mỗi service tự tạo request_id mới | Không ghép được request xuyên dịch vụ | Chỉ tạo tại entrypoint; downstream bảo toàn ID trusted |
| Tin nguyên X-Request-Id từ internet | Spoof, collisions, log injection | Gateway chuẩn hóa/ghi đè; validate length/charset |
| Dùng order_id làm request_id | Nhiều request trong cùng order khó phân biệt | Tách business_id với request_id |
| Dùng cùng một ID cho request, span, message | Sai quan hệ khi fan-out và retry | Phân biệt request/correlation/trace/span/message |
| Ghi log text tự do rồi parse bằng regex | Query mong manh khi message đổi | JSON fields có schema và event.name |
| Quên clear MDC | Log của request khác mang ID cũ | Try/finally hoặc putCloseable; test concurrency |
| Tin MDC tự lan qua @Async/Reactor | Mất ID hoặc context chéo | Context propagation có quản lý lifecycle |
| Tự nối chuỗi traceparent | Trace sai định dạng và quan hệ | Dùng tracing SDK/propagator |
| Log toàn bộ HTTP request/response | Rò secret/PII, payload và chi phí lớn | Allowlist field, redaction, event nhỏ |
| Đưa request_id vào metric label | Nổ cardinality và chi phí metric | Truy vấn ID ở logs/traces, metric dùng labels hữu hạn |
| Ghi ERROR ở tất cả tầng cho cùng một lỗi | Incident count nhiễu, log trùng | Ghi lỗi ở owner và ngữ cảnh mới khi cần |
| Dùng INFO cho mọi method call | Log volume cao, ít giá trị | Request summary + domain event có ý nghĩa |
| Coi timestamp là quan hệ nhân quả | Ghép nhầm log khi concurrent/async | Trace, message_id, causation_id |
| Không ghi service.version | Khó phân biệt lỗi trước/sau deploy | Enrich service/version/digest ở logger/collector |
| Bỏ qua log pipeline health | Mất log trong lúc sự cố | Theo dõi drop, parse errors, ingest lag |
| Dùng ID như bearer credential | Lộ quyền truy cập khi biết ID | Authorization độc lập với correlation ID |

## 23. Checklist áp dụng cho microservice

- [ ] Gateway có trách nhiệm rõ ràng để tạo/chuẩn hóa request_id ở trust boundary.
- [ ] Mọi request vào có ID hợp lệ; response có thể trả ID để hỗ trợ khách hàng.
- [ ] Outbound HTTP/gRPC giữ ID nhất quán; W3C trace context do instrumentation quản lý.
- [ ] Log có timestamp UTC, severity, service.name, event.name, message và các field ngữ cảnh có kiểu thống nhất.
- [ ] trace_id/span_id được bổ sung vào log khi có active span; không tạo giá trị giả.
- [ ] Có convention riêng cho correlation_id, message_id, causation_id, business_id và job_id.
- [ ] Các event quan trọng có outcome, error.code, dependency và duration phù hợp.
- [ ] Logger xuất JSON một dòng, collector parse đúng; không phải chỉ có key-value trong chuỗi text.
- [ ] MDC/context được clear sau mỗi request/message, truyền đúng qua async/worker pool/Reactor.
- [ ] Request ID từ client không được xem là trusted; validation chống log/header injection.
- [ ] Không log credential, token, body nhạy cảm hoặc payload lớn; redaction và RBAC đã cấu hình.
- [ ] request_id/trace_id dùng để search log/trace, không dùng làm metric labels.
- [ ] Chính sách severity, sampling, retention và log volume đã có owner và ngân sách.
- [ ] Collector có metric dropped records, parse errors, queue saturation và ingest lag.
- [ ] Contract/integration tests đi qua ít nhất hai service và một luồng async quan trọng.
- [ ] Runbook hỗ trợ truy vấn theo request_id → trace_id → service/span → error.code.
- [ ] Thay đổi schema log hoặc header có chiến lược tương thích/rollout liên service.
- [ ] Cơ chế authorization hoạt động độc lập với mọi identifier dùng để quan sát.

## 24. Câu hỏi thường gặp

**Có thể dùng trace_id thay request_id không?**

Có thể trong một kiến trúc tracing toàn diện, nhưng phải xác định rõ hành vi khi không có trace context, khi sampling, retry từ client và workflow bất đồng bộ. Nhiều tổ chức giữ cả request_id dễ cung cấp cho khách hàng và trace_id dành cho hệ tracing. Hai field rõ nghĩa thường giúp điều tra hơn một field bị dùng cho nhiều mục đích.

**MDC có tự lan truyền qua CompletableFuture hoặc WebFlux không?**

Không nên giả định. MDC thường là thread-local, trong khi CompletableFuture và reactive pipeline có thể chạy ở thread khác. Dùng context propagation được framework hỗ trợ hoặc wrapper bảo toàn ngữ cảnh; kiểm thử kỹ việc dọn context và hành vi khi đổi thread.

**Chỉ cần log JSON có phải đã đạt distributed tracing?**

Chưa. JSON là cấu trúc record, còn tracing cung cấp trace/span và mối quan hệ giữa chúng. Có thể search log theo request_id với JSON mà chưa có trace; khi cần phân tích critical path và downstream latency, nên thêm instrumentation.

**Có nên log mọi request ở INFO không?**

Tùy traffic, SLO, chi phí và yêu cầu điều tra. Với API lưu lượng cao, mỗi request nhiều log INFO có thể quá đắt; thường ưu tiên một request summary có kiểm soát, sampling cho thành công, sự kiện lỗi quan trọng và metrics đầy đủ. Audit bắt buộc có retention và guarantee riêng.

**Nếu client cung cấp X-Request-Id hợp lệ, có nên giữ lại?**

Không tự động. Hợp lệ về charset không có nghĩa đáng tin. Gateway internet có thể tạo ID mới và lưu client-provided ID ở field khác sau validation nếu cần. Service chỉ nên bảo toàn giá trị từ upstream trong trust boundary đã được quy định rõ.

**Một message Kafka được xử lý lại thì request_id có giữ nguyên không?**

Nếu metadata của message mang origin_request_id và correlation_id, consumer thường giữ chúng để truy vết nguồn. Mỗi execution retry có thể có span/attempt mới. message_id dùng để phân biệt cùng message được phát lại với message mới; idempotency và commit offset là bài toán riêng, không được giải quyết chỉ bằng log ID.

**Làm sao log được mà không rò dữ liệu?**

Thiết kế allowlist field theo event; không log body/header nhạy cảm; sử dụng encoder có JSON escaping, redaction ở code và collector, RBAC/encryption/retention ở backend, test bằng dữ liệu secret giả. ID dùng quan sát không được trở thành quyền truy cập.

**Làm sao biết correlation thật sự đúng?**

Test một request đi qua nhiều hop, kiểm tra ID trong response và log từng service; test nhiều request đồng thời; test async, retry, exception và message redelivery. Readiness của hệ thống quan sát cũng phải kiểm tra collector và tracing pipeline, không chỉ logic trong service.

---

**Nguyên lý quan trọng:** *Mỗi sự kiện log phải có cấu trúc để máy tìm được; mỗi lần xử lý phải có định danh rõ nghĩa; các định danh phải được lan truyền qua đúng ranh giới và dọn sau vòng đời xử lý. Nhờ vậy, một request trong hệ thống phân tán trở thành chuỗi sự kiện có thể tái dựng và kiểm chứng mà không đánh đổi quyền riêng tư hay tính ổn định của dịch vụ.*