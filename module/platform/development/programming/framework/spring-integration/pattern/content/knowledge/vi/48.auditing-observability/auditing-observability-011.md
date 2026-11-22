# Liên kết log, metric và trace bằng correlation ID trong Spring Integration

## 1. Vì sao cần liên kết ba loại tín hiệu?

Một luồng Enterprise Integration Patterns (EIP) có thể đi qua **Gateway → Router → Transformer → QueueChannel → Service Activator → Aggregator**. Khi xử lý lỗi, ba loại dữ liệu quan sát thường cung cấp những mảnh thông tin khác nhau:

- **Log:** Message nào đã đi qua nhánh nào? Lỗi xảy ra tại bước nào?
- **Metric:** Tỷ lệ lỗi, độ trễ và lưu lượng của cả hệ thống thay đổi ra sao?
- **Distributed trace:** Một lần xử lý cụ thể đã đi qua những span nào, ở dịch vụ hoặc thread nào?

Nếu log, metric và trace không liên kết được với nhau, người vận hành thấy metric báo lỗi tăng nhưng không biết request nào bị ảnh hưởng; thấy log lỗi nhưng không biết nó thuộc lần gọi hoặc nhánh Router nào.

**Correlation ID** giúp theo dõi *một hành trình nghiệp vụ* qua các bước khác nhau. Tuy nhiên, **không phải cứ gắn correlation ID vào mọi nơi là đúng**: nhãn metric có cardinality quá cao sẽ làm hệ thống đo lường phình to, còn ID do client gửi tới phải được kiểm soát để tránh giả mạo hoặc lộ thông tin.

Bài học thuộc chương **Audit và observability** của module **SPRING_INTEGRATION_PATTERN**. Module hướng đến việc triển khai Enterprise Integration Patterns bằng Spring Integration để tạo các luồng thông điệp ít phụ thuộc, dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và theo dõi các nhánh xử lý. Tại đây, chúng ta thiết kế một **hợp đồng định danh xuyên flow** và sử dụng nó một cách có chủ đích ở log, metric, trace và audit trail.

Sau bài, bạn có thể:

1. Phân biệt correlation ID nghiệp vụ với correlation header của Spring Integration và với \`traceId\`/\`spanId\`.
2. Thiết lập và giữ nguyên ID ở các ranh giới thông điệp.
3. Ghi correlation ID vào structured log/MDC mà không làm rò rỉ context giữa các thread.
4. Gắn correlation ID vào trace dưới dạng thuộc tính thích hợp, nhưng **không** dùng nó làm nhãn metric.
5. Lần từ một cảnh báo metric tới trace, log và audit record của yêu cầu liên quan.
6. Kiểm thử việc truyền ID, phân tách request, khôi phục MDC và xử lý retry/async.

## 2. Bốn loại ID thường bị nhầm

Trong Spring Integration, từ “correlation” có thể chỉ nhiều mục đích khác nhau. Nên đặt tên rõ ràng ngay từ đầu.

| Định danh | Phạm vi | Mục đích | Có thể thay đổi khi nào? |
| --- | --- | --- | --- |
| **Business correlation ID** | Một thao tác/hành trình nghiệp vụ | Nối các log, trace, audit event của một yêu cầu | Thường giữ nguyên qua các bước, có thể qua nhiều lần retry |
| **EIP \`correlationId\`** | Một message group của Splitter/Aggregator/Barrier | Ghép đúng các fragment hoặc tín hiệu | Có thể khác khi tách nhóm hoặc tạo attempt mới |
| **\`traceId\`** | Một distributed trace được tạo bởi tracing | Tìm toàn bộ span của một trace | Có thể đổi khi workflow tách thành trace mới, trace cũ hết hoặc không truyền context |
| **\`spanId\`** | Một đoạn công việc trong trace | Phân biệt Router/handler/HTTP call cụ thể | Thay đổi theo từng span |

Trong Spring Integration, header EIP thường có tên:

~~~java
IntegrationMessageHeaderAccessor.CORRELATION_ID
~~~

Nó thường được biểu diễn qua header \`correlationId\`. **Không nên ghi đè header này chỉ để phục vụ logging** nếu flow có Splitter, Aggregator, Barrier hoặc các thành phần phụ thuộc grouping; làm vậy có thể thay đổi hành vi ghép message.

Để tránh xung đột, ví dụ trong bài dùng header ứng dụng:

~~~text
obsCorrelationId = "c-76e6f41c"
~~~

Đây chính là **correlation ID nghiệp vụ dùng cho observability**. Tên \`obsCorrelationId\` chỉ là quy ước của ứng dụng, không phải một header Spring Integration bắt buộc. Một hệ thống có thể dùng \`requestId\`, \`workflowId\` hoặc \`businessCorrelationId\` nếu các producer và consumer thống nhất.

### Ví dụ hai lần thử của cùng một đơn hàng

~~~text
orderId               = order-17
obsCorrelationId      = corr-order-17          (giữ qua retry)
attemptId             = attempt-2             (đổi ở lần thử mới)
EIP correlationId     = order-17/attempt-2    (khóa một nhóm Barrier)
traceId               = 7c6e...               (tracing context)
spanId                = a9f1...               (span cụ thể)
~~~

Sử dụng **\`obsCorrelationId\`** để tìm toàn bộ diễn biến nghiệp vụ, **\`attemptId\`** để phân biệt lần thử, **\`correlationId\` của EIP** để nhóm chính xác và **\`traceId\`** để đi theo quan hệ cha–con của các span.

## 3. Bức tranh liên kết log → metric → trace

~~~mermaid
flowchart TD
    IN["Gateway nhận request\nobsCorrelationId=c-123"] --> R["Router"]
    R --> T["Transformer"]
    T --> Q["Queue / Async Worker"]
    Q --> H["Handler"]
    H --> OUT["Output / Reply"]
    R -. "Log có obsCorrelationId" .-> LOG["Structured logs"]
    T -. "Log có obsCorrelationId" .-> LOG
    H -. "Log có obsCorrelationId" .-> LOG
    R -. "Metric: flow, route, outcome" .-> MET["Metrics: low-cardinality"]
    H -. "Metric: duration, outcome" .-> MET
    IN -. "Trace context" .-> TRACE["Traces: traceId/spanId"]
    Q -. "Spans, nếu instrumentation bật" .-> TRACE
    H -. "Span attribute: obsCorrelationId" .-> TRACE
    TRACE -. "traceId" .-> LOG
    MET -. "Exemplar hoặc time + route" .-> TRACE
    LOG -. "obsCorrelationId" .-> AUDIT["Audit store khi cần lưu bền vững"]
~~~

Cách liên kết hợp lý:

1. **Log** chứa \`obsCorrelationId\`; khi tracing/MDC được bật, log có thể có thêm \`traceId\` và \`spanId\`.
2. **Trace** có thể chứa \`obsCorrelationId\` như **span attribute có cardinality cao**; \`traceId\` và \`spanId\` do tracing framework quản lý.
3. **Metric** chỉ dùng những chiều phân nhóm hữu hạn như \`flow\`, \`pattern\`, \`route\`, \`outcome\`, \`exceptionType\` đã chuẩn hóa.
4. **Metric → trace** dùng exemplar nếu backend hỗ trợ và đã bật, hoặc khoanh vùng bằng khoảng thời gian/service/route rồi tìm trace/log; **không** gắn từng correlation ID vào label metric.
5. **Audit trail** khi có yêu cầu đối soát phải được lưu bằng cơ chế bền vững, không chỉ dựa vào debug log hoặc các span có thể bị sampling.

**Điểm cốt lõi:** Correlation ID là khóa để *truy vấn từng trường hợp*, còn metric là dữ liệu *tổng hợp trên rất nhiều trường hợp*.

## 4. Thiết kế hợp đồng ID tại ranh giới vào

Một quy tắc mẫu cho Gateway hoặc inbound adapter:

| Tình huống | Cách xử lý đề xuất |
| --- | --- |
| Request chưa có ID | Tạo ID mới tại điểm ingress |
| Request có ID từ nguồn đáng tin | Xác thực kiểu, kích thước, định dạng rồi giữ ID |
| ID do client bất kỳ gửi | Không tin mặc định; có thể tạo ID nội bộ và lưu ID bên ngoài ở field riêng |
| ID quá dài hoặc chứa ký tự xuống dòng | Từ chối hoặc chuẩn hóa để tránh log injection |
| Có ID nghiệp vụ nhưng EIP cần correlation khác | Dùng hai header riêng, không ghi đè |
| Chạy retry cho cùng operation | Giữ business correlation ID, tăng \`attemptId\` |

Ví dụ tạo message đầu vào, sử dụng \`obsCorrelationId\`:

~~~java
package example;

import java.util.UUID;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class CorrelationHeaders {

    public static final String OBS_CORRELATION_ID = "obsCorrelationId";

    private CorrelationHeaders() {
    }

    public static <T> Message<T> ensureAtIngress(Message<T> source) {
        Object raw = source.getHeaders().get(OBS_CORRELATION_ID);

        if (raw == null) {
            return MessageBuilder.fromMessage(source)
                    .setHeader(
                            OBS_CORRELATION_ID,
                            UUID.randomUUID().toString())
                    .build();
        }

        if (!(raw instanceof String value)
                || !value.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException(
                    "obsCorrelationId is invalid");
        }

        return source;
    }
}
~~~

Hàm này minh họa *một hợp đồng mẫu*, không phải một validator chung cho mọi doanh nghiệp. Trong hệ thống có giao tiếp với dịch vụ khác, cần thống nhất định dạng, độ dài và nguồn phát ID. Một số tổ chức ưu tiên dùng UUID mới do backend tạo, đồng thời lưu \`externalRequestId\` đã xác thực để phục vụ đối soát.

**Không lấy email, số điện thoại, token hoặc toàn bộ payload làm correlation ID.** ID sẽ xuất hiện rộng trong log và trace; nó nên là giá trị không nhạy cảm, khó đoán trong bối cảnh truy cập của hệ thống.

## 5. Correlation ID cần tồn tại ở những ranh giới nào?

Spring Integration hỗ trợ header propagation qua nhiều endpoint. Tuy nhiên, **không nên mặc định mọi thành phần giữ mọi header**: adapter ngoài JVM, mapping của broker, custom Transformer hoặc Aggregator có thể thay đổi cách đóng gói message.

| Ranh giới | Rủi ro | Assertion cần kiểm tra |
| --- | --- | --- |
| Gateway → Flow | Gateway tạo message mới | Có \`obsCorrelationId\` sau ingress |
| Router → Nhánh được chọn | Nhánh phụ thiếu header | Header có ở đúng output route |
| Transformer | Tạo message mới, quên copy headers | ID nghiệp vụ còn nguyên |
| Filter → Discard | Chỉ log success branch | Nhánh discard vẫn có ID để chẩn đoán |
| Splitter | Một request thành nhiều fragment | Mọi fragment giữ business correlation ID |
| Aggregator | Output group có thể dùng headers của message đại diện | ID đúng ở kết quả cuối, EIP \`correlationId\` vẫn dùng để nhóm |
| QueueChannel/ExecutorChannel | Đổi thread | Header còn; MDC phải thiết lập lại tại consumer |
| Kafka/JMS/HTTP adapter | Đổi process/protocol | Header mapping và tracing propagation thực sự hoạt động |
| Retry/Error channel | Exception hoặc redelivery | Correlation, \`attemptId\`, nguyên nhân lỗi truy vết được |
| Gateway reply | Response message mới | Có thể gắn ID vào reply nếu hợp đồng caller cần |

### Ví dụ headers trước và sau Splitter

~~~text
Request:
  obsCorrelationId = c-123
  payload = [item-A, item-B]

Splitter output 1:
  obsCorrelationId = c-123
  correlationId = <group-X>
  sequenceNumber = 1
  sequenceSize = 2

Splitter output 2:
  obsCorrelationId = c-123
  correlationId = <group-X>
  sequenceNumber = 2
  sequenceSize = 2
~~~

Đây là cách tách trách nhiệm: **\`obsCorrelationId\`** giúp xem cả hành trình đơn hàng, còn **\`correlationId\`** do EIP xử lý để Aggregator ghép đúng nhóm. Không nên sửa \`sequenceNumber\` hoặc \`correlationId\` chỉ vì muốn làm đẹp log.

## 6. Structured logging: ghi những field nào?

Log văn bản không có cấu trúc gây khó truy vấn khi flow đi qua nhiều thành phần. Một log JSON minh họa:

~~~json
{
  "timestamp": "2026-11-21T08:00:00Z",
  "level": "INFO",
  "service": "order-integration",
  "flow": "checkout",
  "stage": "router.vip",
  "event": "message.routed",
  "obsCorrelationId": "c-123",
  "traceId": "9d4a6e8b1fc2a310e5db87c64311df09",
  "spanId": "184ef19a56b90dc1",
  "attemptId": 1,
  "outcome": "success",
  "durationMs": 7
}
~~~

Các giá trị là **dữ liệu giả minh họa**, không đại diện cho log do Spring Integration tự động phát sinh. Thực tế, \`traceId\`/\`spanId\` chỉ sẵn có khi tracing được cấu hình và context hiện diện trong thread xử lý.

Nên phân biệt:

- **Các field dùng để lọc thường xuyên:** \`service\`, \`flow\`, \`stage\`, \`route\`, \`outcome\`.
- **Các field dùng để truy nguyên trường hợp riêng:** \`obsCorrelationId\`, \`traceId\`, \`spanId\`, \`attemptId\`.
- **Các field cần thận trọng:** Payload, header chứa token, thông tin khách hàng, địa chỉ, URL query string.

Không phải mọi thao tác đều cần log \`INFO\`. Log ở ranh giới quan trọng (received, routed, retried, rejected, completed, timed out) và dùng metrics cho lưu lượng lớn, tránh tạo hàng triệu dòng log “đã nhận message” không có giá trị.

## 7. MDC: làm correlation ID xuất hiện trong log của handler

Với SLF4J và một logging backend hỗ trợ MDC, có thể đưa \`obsCorrelationId\` vào **Mapped Diagnostic Context (MDC)** khi xử lý một message:

~~~java
package example;

import java.util.function.Supplier;
import org.slf4j.MDC;
import org.springframework.messaging.Message;

public final class CorrelationLogContext {

    private static final String KEY = "obsCorrelationId";

    private CorrelationLogContext() {
    }

    public static <T> T within(
            Message<?> message, Supplier<T> work) {
        Object raw = message.getHeaders().get(KEY);
        if (!(raw instanceof String id) || id.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing obsCorrelationId header");
        }

        String previous = MDC.get(KEY);
        try {
            MDC.put(KEY, id);
            return work.get();
        } finally {
            if (previous == null) {
                MDC.remove(KEY);
            } else {
                MDC.put(KEY, previous);
            }
        }
    }
}
~~~

Trong một handler:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.Message;

public final class OrderHandler {
    private static final Logger log =
            LoggerFactory.getLogger(OrderHandler.class);

    public String process(Message<String> message) {
        return CorrelationLogContext.within(message, () -> {
            log.info("Processing order");
            // Log ở các method cùng thread cũng có MDC.
            return "accepted:" + message.getPayload();
        });
    }
}
~~~

Ví dụ log pattern với Logback/Spring Boot (điều chỉnh theo cấu hình logging thực tế):

~~~properties
logging.pattern.level=%5p [corr:%X{obsCorrelationId:-}] [trace:%X{traceId:-},span:%X{spanId:-}]
~~~

**Vì sao phải khôi phục MDC trong \`finally\`?** Worker thread thường được tái sử dụng. Nếu xử lý message A để lại ID trong thread, log của message B có thể mang nhầm ID của A. Đoạn code trên khôi phục giá trị cũ nếu trước đó đã có một scope khác; chỉ \`MDC.clear()\` không phân biệt những khóa được một thành phần khác thiết lập.

MDC là **trạng thái cục bộ theo thread**, không phải message header và không phải phương tiện truyền context qua broker. Trong một \`ExecutorChannel\`, \`QueueChannel\` hoặc handler async, hãy thiết lập MDC lại dựa trên **message header** tại ranh giới worker. Tracing context (\`traceId\`/\`spanId\`) cần cơ chế propagation của tracing framework riêng.

## 8. Micrometer Observation và tracing: gắn thuộc tính đúng chỗ

Trong ứng dụng Spring Boot/Spring Integration có cấu hình **Micrometer Observation**, có thể tạo một observation bao quanh handler. Observation hỗ trợ metadata:

- **Low-cardinality key values:** Ít giá trị có thể lặp lại, phù hợp dùng làm nhãn metric.
- **High-cardinality key values:** Nhiều giá trị khác nhau, phù hợp cho trace/span và điều tra trường hợp riêng, **không** nên thành metric tags.

Ví dụ:

~~~java
package example;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.messaging.Message;

public final class ObservedOrderHandler {

    private final ObservationRegistry observations;

    public ObservedOrderHandler(ObservationRegistry observations) {
        this.observations = observations;
    }

    public String handle(Message<String> message) {
        String correlationId = (String) message.getHeaders()
                .get(CorrelationHeaders.OBS_CORRELATION_ID);

        Observation observation = Observation.createNotStarted(
                        "integration.orders.handle", observations)
                .lowCardinalityKeyValue("flow", "orders")
                .lowCardinalityKeyValue("stage", "handler")
                .highCardinalityKeyValue(
                        "app.obs_correlation_id", correlationId);

        observation.start();
        try (Observation.Scope ignored = observation.openScope()) {
            return CorrelationLogContext.within(message, () -> {
                // Chỗ gọi service/Transformer thật.
                return "processed:" + message.getPayload();
            });
        } catch (RuntimeException error) {
            observation.error(error);
            throw error;
        } finally {
            observation.stop();
        }
    }
}
~~~

Ở ví dụ này, \`flow=orders\` và \`stage=handler\` là **ít giá trị** nên phù hợp để tổng hợp metrics. \`app.obs_correlation_id\` là **giá trị riêng của từng yêu cầu**, vì vậy được đưa vào high-cardinality key value.

**Lưu ý cấu hình:** Tạo một \`Observation\` không tự bảo đảm có distributed trace xuất hiện ở hệ thống theo dõi. Cần cấu hình \`ObservationRegistry\`, \`ObservationHandler\` thích hợp, Micrometer Tracing bridge và exporter/backend. Tùy phiên bản, cần bật instrumentation của Spring Integration hoặc chủ động quan sát endpoint; kiểm tra thực tế qua test và trace backend. Nếu không có tracing bridge, observation vẫn có thể phục vụ metrics hoặc handler khác nhưng không nhất thiết tạo span.

### traceId không phải correlation ID nghiệp vụ

Hãy để tracer tạo và quản lý \`traceId\`/\`spanId\`. Không nên dùng \`obsCorrelationId\` làm \`traceId\` bằng cách ép chuỗi tùy ý: trace ID có định dạng và ngữ nghĩa riêng; tracing còn có thể thực hiện sampling hoặc khởi tạo trace mới theo giao thức.

Với tác vụ bất đồng bộ dài hạn, có thể có **nhiều trace** cùng thuộc một business correlation ID. Khi đó, \`obsCorrelationId\` liên kết chúng trong log và audit, còn trace context hoặc span links mô tả quan hệ kỹ thuật nếu instrumentation hỗ trợ.

## 9. Metric cardinality: vì sao không thêm correlation ID làm nhãn?

Metric thường được lưu theo các time series phân biệt bởi tên metric và **tổ hợp các label**. Nếu gắn một correlation ID mới cho từng message, mỗi request có thể tạo thêm một tổ hợp nhãn mới.

Ví dụ **không nên**:

~~~text
integration_messages_total{
  flow="checkout",
  outcome="success",
  obsCorrelationId="c-123"
} 1
~~~

Và ví dụ **nên**:

~~~text
integration_messages_total{
  flow="checkout",
  route="vip",
  outcome="success"
} 1734
~~~

Hai giá trị chỉ là minh họa, không phải metric mặc định do Spring Integration tự xuất ra. Khi cần điều tra request \`c-123\`, hãy tìm **log** hoặc **span attribute**, không cố tìm một chuỗi thời gian metric riêng của \`c-123\`.

### Bảng chọn nhãn metric

| Field | Có nên là label metric? | Lý do |
| --- | --- | --- |
| \`flow\` | Có, nếu là tập cố định | Giúp nhóm theo integration flow |
| \`route\` | Có, nếu giới hạn các route đã biết | Theo dõi Router |
| \`outcome\` | Có: success/error/timeout | Tính tỷ lệ lỗi |
| \`exceptionType\` | Có điều kiện, chuẩn hóa nhóm lỗi | Tránh exception message vô hạn |
| \`tenantTier\` | Có điều kiện: vài nhóm đã biết | Không dùng raw tenant ID nếu nhiều tenant |
| \`obsCorrelationId\` | **Không** | Gần như mỗi request một giá trị |
| \`traceId\`, \`spanId\` | **Không** | Mỗi trace/span có ID khác nhau |
| \`messageId\`, \`orderId\`, \`userId\` | **Không** | Cardinality lớn, có thể nhạy cảm |

Nếu hệ thống xử lý \(N\) correlation ID khác nhau và dùng ID làm một label, riêng nhãn đó có thể tạo tối đa **\(N\) tổ hợp chuỗi thời gian** cho mỗi bộ label còn lại. Khi thêm \`route\`, \`stage\` và \`outcome\`, số tổ hợp còn có thể tăng đáng kể. Đây là lý do nên đặt trần cardinality trước khi triển khai dashboard và alert.

### Làm sao đi từ metric tới trace khi không có correlation label?

Sử dụng một trong hai đường:

1. **Exemplar**: hệ thống metric có hỗ trợ gắn mẫu \`traceId\` lên một điểm đo, và backend/dashboard hỗ trợ mở trace tương ứng; điều này phải được cấu hình và không bảo đảm xuất hiện trên mọi mẫu.
2. **Khoanh vùng**: từ metric biết thời gian, service, route và outcome → tìm trace/log liên quan trong cửa sổ thời gian đó → lấy \`traceId\` hoặc \`obsCorrelationId\` để điều tra.

Metric alert thường khởi đầu việc điều tra bằng dấu hiệu thống kê; **không hứa rằng mọi metric sample có thể mở được đúng một trace**.

## 10. Audit khác log, metric và trace ở điểm nào?

**Audit trail** trả lời: *Ai hoặc thành phần nào đã thực hiện thao tác gì, trên đối tượng nào, vào thời điểm nào, với kết quả gì?* Nhiều hệ thống cần audit bền vững, có chính sách giữ dữ liệu và bảo vệ tính toàn vẹn; log, metric và trace thường phục vụ vận hành, có thể bị sampling hoặc hết hạn lưu sớm hơn.

Ví dụ audit event nghiệp vụ:

~~~json
{
  "auditEventId": "evt-0024",
  "occurredAt": "2026-11-21T08:00:01Z",
  "operation": "order.confirm",
  "entityType": "order",
  "entityReference": "opaque-order-reference",
  "obsCorrelationId": "c-123",
  "attemptId": 2,
  "outcome": "accepted",
  "sourceService": "order-integration",
  "traceId": "9d4a6e8b1fc2a310e5db87c64311df09"
}
~~~

Đây là dữ liệu giả. Nếu audit event chứa định danh hoặc thông tin cá nhân, cần chính sách phân quyền, masking, retention và kiểm soát truy cập phù hợp.

Những điều phải làm rõ:

- Khi nào audit event được xem là **đã commit**?
- Nếu nghiệp vụ thành công nhưng ghi audit thất bại, có recovery hoặc outbox nào?
- Nếu retry dẫn tới cùng một kết quả, có ghi lại mỗi attempt hay chỉ một business event?
- Ai được tra cứu audit, có lưu dấu việc truy cập audit không?
- Làm sao chứng minh thứ tự và tính toàn vẹn nếu nhiều service phát event?

**Chỉ log correlation ID không đủ để bảo đảm audit.** Khi có yêu cầu đối soát nghiêm ngặt, dùng một cơ chế lưu sự kiện/transaction/outbox có tính bền vững, schema version và khóa idempotency phù hợp.

## 11. Kiểm thử Spring Integration Flow có giữ correlation ID không?

Ví dụ JUnit 5 sau dùng **Java 17, Spring Integration Java DSL 6.x, Spring Test và AssertJ**. Mục tiêu là chứng minh một Transformer giữ **business correlation header** và không ghi đè **EIP correlation header**.

Với Spring Boot có thể dùng dependency tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Tạo \`src/test/java/example/CorrelationPropagationTest.java\`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(CorrelationPropagationTest.TestFlow.class)
class CorrelationPropagationTest {

    @Autowired
    @Qualifier("orders.input")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.output")
    QueueChannel output;

    @Test
    void transformer_preserves_business_and_eip_correlation_ids() {
        Message<String> original = MessageBuilder
                .withPayload("  order-17 ")
                .setHeader("obsCorrelationId", "c-order-17")
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        "group-17")
                .build();

        assertThat(input.send(original)).isTrue();
        Message<?> processed = output.receive(1_000);

        assertThat(processed).isNotNull();
        assertThat(processed.getPayload())
                .isEqualTo("normalized:order-17");
        assertThat(processed.getHeaders().get("obsCorrelationId"))
                .isEqualTo("c-order-17");
        assertThat(processed.getHeaders().get(
                IntegrationMessageHeaderAccessor.CORRELATION_ID))
                .isEqualTo("group-17");
        assertThat(output.receive(0)).isNull();
    }

    @Test
    void two_requests_do_not_share_business_correlation() {
        input.send(MessageBuilder.withPayload(" A ")
                .setHeader("obsCorrelationId", "c-A")
                .build());
        input.send(MessageBuilder.withPayload(" B ")
                .setHeader("obsCorrelationId", "c-B")
                .build());

        Message<?> first = output.receive(1_000);
        Message<?> second = output.receive(1_000);
        assertThat(first).isNotNull();
        assertThat(second).isNotNull();
        assertThat(first.getHeaders().get("obsCorrelationId"))
                .isEqualTo("c-A");
        assertThat(second.getHeaders().get("obsCorrelationId"))
                .isEqualTo("c-B");
        assertThat(output.receive(0)).isNull();
    }

    @Configuration
    @EnableIntegration
    static class TestFlow {

        @Bean("orders.output")
        QueueChannel output() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow orderFlow() {
            return IntegrationFlow.from("orders.input")
                    .transform(String.class,
                            value -> "normalized:" + value.trim())
                    .channel("orders.output")
                    .get();
        }
    }
}
~~~

**Test này chứng minh điều gì?** Với Transformer mặc định được dùng trong ví dụ, các headers cần thiết vẫn có ở output; hai request có business correlation ID khác nhau không bị trộn. Test **không** khẳng định rằng mọi custom Transformer hoặc mọi broker adapter đều tự giữ mọi header. Những ranh giới đó cần test riêng.

Nếu một endpoint tự tạo \`Message\` mới, hãy dùng \`MessageBuilder.fromMessage(original)\` hoặc copy **những header được phép** theo hợp đồng ứng dụng, đồng thời tránh sao chép bừa bãi thông tin tracing hoặc reply channel sang hệ thống khác.

## 12. Kiểm thử MDC không rò rỉ giữa các message

Một worker thread thường phục vụ liên tiếp nhiều message. Vì vậy, cần test **khôi phục MDC ngay cả khi handler ném exception**.

Thêm lớp test cho \`CorrelationLogContext\`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class CorrelationLogContextTest {

    static Message<String> request(String id) {
        return MessageBuilder.withPayload("payload")
                .setHeader("obsCorrelationId", id)
                .build();
    }

    @Test
    void restores_previous_mdc_after_normal_processing() {
        String previous = MDC.get("obsCorrelationId");
        try {
            MDC.put("obsCorrelationId", "outer");
            String result = CorrelationLogContext.within(
                    request("c-A"),
                    () -> {
                        assertThat(MDC.get("obsCorrelationId"))
                                .isEqualTo("c-A");
                        return "ok";
                    });

            assertThat(result).isEqualTo("ok");
            assertThat(MDC.get("obsCorrelationId"))
                    .isEqualTo("outer");
        } finally {
            restore(previous);
        }
    }

    @Test
    void restores_previous_mdc_after_exception() {
        String previous = MDC.get("obsCorrelationId");
        try {
            MDC.put("obsCorrelationId", "outer");
            assertThatThrownBy(() -> CorrelationLogContext.within(
                    request("c-B"), () -> {
                        assertThat(MDC.get("obsCorrelationId"))
                                .isEqualTo("c-B");
                        throw new IllegalStateException("test failure");
                    })).isInstanceOf(IllegalStateException.class);

            assertThat(MDC.get("obsCorrelationId"))
                    .isEqualTo("outer");
        } finally {
            restore(previous);
        }
    }

    private static void restore(String value) {
        if (value == null) {
            MDC.remove("obsCorrelationId");
        } else {
            MDC.put("obsCorrelationId", value);
        }
    }
}
~~~

Test cần một SLF4J logging backend hỗ trợ MDC (ví dụ Logback trong cấu hình test Spring Boot thông thường). Nếu môi trường chỉ dùng **no-op MDC adapter**, việc assert MDC sẽ không có ý nghĩa; cần cấu hình logging backend thực trước khi kiểm tra.

### Kiểm thử ranh giới bất đồng bộ

Để test \`ExecutorChannel\` hoặc poller, bổ sung tình huống một worker xử lý A rồi B:

1. A có \`obsCorrelationId=c-A\`, B có \`obsCorrelationId=c-B\`.
2. Mỗi lần vào handler, gọi \`CorrelationLogContext.within\` với **message hiện tại**.
3. Ghi nhận ID trong handler, xác minh \`[c-A, c-B]\`.
4. Sau mỗi handler, kiểm tra context của thread không còn sót ID từ message trước.
5. Dùng \`CountDownLatch\` hoặc queue quan sát với timeout hữu hạn; không dùng \`Thread.sleep\` để đoán thread đã chạy xong.

**Không truyền MDC bằng cách dùng \`InheritableThreadLocal\` cho mọi worker thread** rồi cho rằng broker/process cũng sẽ giữ context. Message header và propagation của tracing framework mới là ranh giới truyền thông tin phù hợp.

## 13. Kiểm thử metric và trace được liên kết đúng

Các test header/MDC ở trên chưa chứng minh trace thật sự được export. Cần tách thêm hai lớp kiểm thử:

### Test metric

Đăng ký \`ObservationRegistry\`/meter registry test phù hợp. Gửi nhiều request khác ID qua cùng route, rồi kiểm tra:

- Counter hoặc timer của \`flow=orders\`, \`outcome=success\` tăng đúng số lần.
- Không có label \`obsCorrelationId\`, \`traceId\`, \`spanId\`, \`orderId\` hoặc \`userId\`.
- Lỗi của một request được ghi vào nhóm \`outcome=error\`, không làm tăng nhóm \`success\`.
- \`route\` chỉ nhận các giá trị đã khai báo, không đọc raw path hoặc payload động.

### Test trace

Với tracing bridge và tracer test/in-memory exporter:

- Flow tạo/tiếp tục span đúng theo cấu hình instrumentation.
- \`traceId\` có thể liên kết các span cùng trace khi context propagation hoạt động.
- Span có attribute \`app.obs_correlation_id=c-123\` nếu code chủ động gắn.
- Không tự sinh \`traceId\` từ \`obsCorrelationId\`.
- Khi trace sampling không giữ một span, vẫn truy vấn được audit/log theo business correlation ID nếu đó là yêu cầu vận hành.

### Test tích hợp với broker hoặc HTTP

Khi message đi qua Kafka/JMS/HTTP, kiểm thử end-to-end:

1. Header \`obsCorrelationId\` có được serialize/map đến consumer không?
2. Trace context có được đưa vào carrier theo cơ chế propagation của Micrometer/OTel đã cấu hình không?
3. Worker ở process khác có tạo log đúng business correlation ID không?
4. Retry/redelivery có giữ ID nghiệp vụ nhưng phân biệt attempt không?
5. Không có header nhạy cảm hoặc ID giả mạo được tin tưởng chỉ vì client gửi lên?

Không nên dựa vào unit test với \`DirectChannel\` để tuyên bố tracing xuyên service đã hoạt động.

## 14. Quy trình điều tra: từ cảnh báo metric tới một message lỗi

Giả sử dashboard hiển thị tỷ lệ lỗi của route \`vip\` tăng bất thường:

~~~text
Metric alert:
  integration_messages_total{flow="checkout", route="vip", outcome="error"}
  tăng trong cửa sổ quan sát
~~~

Một quy trình điều tra có thể thực hiện:

1. **Xác định phạm vi:** Service, flow, route, outcome và khoảng thời gian có sự cố.
2. **Tìm trace liên quan:** Dùng exemplar \`traceId\` nếu backend hỗ trợ; nếu không, tìm trace theo service/route trong khoảng thời gian đó.
3. **Mở trace:** Xem span Gateway → Router → Handler → downstream call; xác định span lỗi hoặc thời gian đợi kéo dài.
4. **Lấy \`obsCorrelationId\`:** Từ span attribute nếu có, hoặc từ log được gắn \`traceId\`.
5. **Tìm log theo correlation ID:** Kết hợp log của nhánh xử lý, retry, error channel và reply để dựng lại hành trình nghiệp vụ.
6. **Đối chiếu audit:** Kiểm tra trạng thái nghiệp vụ cuối cùng, \`attemptId\`, kết quả retry hoặc bù trừ nếu cần.
7. **Khắc phục và xác minh:** Kiểm tra metric sau khi sửa, dùng correlation mới để xác nhận flow hoạt động; không đánh đồng sự biến mất của lỗi trên dashboard với việc đã xử lý mọi request cũ.

Nếu trace bị sampling hoặc mất propagation tại một bước, **business correlation ID xuyên message** vẫn là một cầu nối hữu ích giữa log và audit. Nhưng nếu ID bị mất tại adapter hoặc custom Transformer, mối liên kết cũng bị đứt — đó là lý do cần test từng ranh giới.

## 15. Những sai sót thường gặp

| Sai sót | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng \`IntegrationMessageHeaderAccessor.CORRELATION_ID\` làm mọi loại ID | Có thể phá grouping của Splitter/Aggregator | Tách \`obsCorrelationId\` khỏi EIP \`correlationId\` |
| Cố gắng dùng \`obsCorrelationId\` làm \`traceId\` | Sai semantics của tracing | Để tracer quản lý traceId; gắn business ID như attribute |
| Gắn correlation ID làm metric label | Cardinality rất cao, tốn tài nguyên | Chỉ dùng label ít giá trị; dùng logs/traces để tra ID |
| Ghi vào MDC rồi quên xóa | Log của message B mang ID của A | Khôi phục trong \`finally\` |
| Nghĩ MDC tự đi qua ExecutorChannel/broker | Đứt context khi đổi thread/process | Truyền header và thiết lập MDC ở consumer |
| Nghĩ trace context tự qua mọi adapter | Trace bị chia đoạn | Cấu hình/test propagation ở từng giao thức |
| Ghi payload đầy đủ vào log | Rò rỉ dữ liệu, log quá lớn | Structured log có schema và masking |
| Chỉ dựa vào trace đã sampling để audit | Mất bằng chứng nghiệp vụ | Dùng audit store bền vững riêng |
| Copy mọi header sang downstream | Rò rỉ token hoặc reply channel nội bộ | Chỉ truyền các header theo contract |
| Retry tạo correlation ID mới không kiểm soát | Khó ghép các attempt của cùng operation | Giữ business ID, thêm attempt ID |
| Chỉ kiểm tra happy path | Không thấy ID mất ở Filter/Error channel | Test nhánh lỗi, discard và timeout |
| Dùng \`requestId\` làm metric label | Bùng nổ số chuỗi thời gian | Group theo flow, route, outcome |

## 16. Bài thực hành

### Bài A — Propagate qua Router và Transformer

Tạo một luồng \`Gateway → Router(VIP/STANDARD) → Transformer → Output\`. Tại ingress gắn \`obsCorrelationId\`; viết JUnit test với hai request khác ID. Kiểm tra cả hai nhánh giữ nguyên ID và EIP correlation header không bị ghi đè.

### Bài B — MDC không rò rỉ giữa message

Tạo một handler dùng \`CorrelationLogContext.within\` để log \`obsCorrelationId\`. Gửi A rồi B trên cùng executor một thread, thêm một case handler ném exception. Chứng minh B không nhận ID của A và MDC được khôi phục sau khi exception.

### Bài C — Metric label an toàn

Tạo 100 request giả, mỗi request một \`obsCorrelationId\`, nhưng chỉ có hai route và hai outcome. Đếm số time series của metric nếu dùng correlation ID làm label rồi so với metric chỉ dùng \`route\` và \`outcome\`. Giải thích vì sao metric nên tổng hợp, còn ID riêng dùng ở log/trace.

### Bài D — Trace qua QueueChannel hoặc broker

Gắn \`obsCorrelationId=c-123\` tại ingress, đưa message qua ranh giới bất đồng bộ. Bật tracing phù hợp với dự án và quan sát trace trong test exporter. Chứng minh span downstream có thể được liên kết khi trace context được truyền đúng, còn business correlation ID vẫn nằm trong header message.

### Bài E — Retry, error channel và audit

Giả lập một request thất bại ở lần đầu, retry thành công ở lần hai. Giữ \`obsCorrelationId\`, thay \`attemptId\`, ghi log lỗi và audit event theo schema. Kiểm tra metric lỗi/thành công theo route, tìm được cả hai attempt bằng correlation ID nhưng không tạo metric label theo từng request.

### Bài F — Điều tra lỗi từ một dashboard

Tạo một lỗi có kiểm soát trên route VIP. Bắt đầu từ metric \`outcome=error\`, xác định khoảng thời gian, tìm trace theo service/route hoặc exemplar (nếu có), tìm log theo \`traceId\` rồi \`obsCorrelationId\`, cuối cùng kiểm tra audit record. Ghi lại bước nào làm mối liên kết bị đứt nếu không thấy dữ liệu.

## 17. Checklist trước khi triển khai

1. Business correlation ID có được tạo/xác thực tại ingress và giữ qua các bước flow không?
2. Có phân biệt rõ business ID với EIP \`correlationId\`, \`traceId\` và \`spanId\` không?
3. Router, Transformer, Splitter, Aggregator, Gateway và ErrorChannel có hợp đồng propagation rõ ràng không?
4. Các ranh giới QueueChannel/ExecutorChannel/broker có truyền ID và thiết lập lại MDC không?
5. Structured logs có \`obsCorrelationId\`, stage, route, outcome, attempt và trace IDs khi có tracing không?
6. Metric chỉ dùng low-cardinality labels và có giới hạn cardinality không?
7. Trace có span attribute cho business ID và tracing propagation đã được kiểm tra bằng test tích hợp không?
8. Dashboard có cách đi từ metric đến trace bằng exemplar hoặc lọc theo thời gian/service không?
9. Nếu trace không được thu thập do sampling, có thể điều tra bằng log/audit mà không mất khóa liên kết không?
10. Audit trail có tính bền vững, kiểm soát truy cập và idempotency phù hợp yêu cầu không?
11. Retry/late reply có giữ business ID và phân biệt \`attemptId\` không?
12. Test có xác minh MDC được khôi phục khi handler hoàn tất hoặc thất bại không?
13. Header và log có được lọc để tránh token, dữ liệu riêng tư và log injection không?
14. Có tài liệu vận hành hướng dẫn truy vấn \`obsCorrelationId\` từ cảnh báo metric tới kết quả nghiệp vụ không?

**Kết luận:** Muốn liên kết log, metric và trace trong Spring Integration, hãy giữ một **business correlation ID xuyên các message**, dùng nó trong **log và span attribute**, nhưng **không dùng làm metric label**. Tracing cung cấp quan hệ kỹ thuật qua \`traceId\`/\`spanId\`; metrics cho biết xu hướng; audit lưu lại những sự kiện nghiệp vụ cần đối soát. Thiết kế đúng ranh giới propagation, MDC và cardinality — cùng các bài test cho cả nhánh thành công, lỗi và bất đồng bộ — sẽ giúp truy nguyên một message từ cảnh báo toàn hệ thống đến đúng hành trình xử lý.

### Tài liệu tham khảo

- [Spring Integration Reference — Message Headers](https://docs.spring.io/spring-integration/reference/message.html): cấu trúc message và metadata qua integration flow.
- [Spring Integration Reference — Micrometer Observation](https://docs.spring.io/spring-integration/reference/metrics.html): khả năng quan sát/metrics của các thành phần Spring Integration, tùy phiên bản và cấu hình.
- [Micrometer Observation Documentation](https://docs.micrometer.io/micrometer/reference/observation.html): low-cardinality/high-cardinality key values và observation handlers.
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/): tracing, propagation và span context.
