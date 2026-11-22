# Trace khi retry topic

Trong **Spring Kafka Reliability Operations**, retry topic giúp consumer không phải giữ một record lỗi trên consumer thread trong toàn bộ thời gian backoff. Khi xử lý thất bại, Spring Kafka có thể forward record sang một Kafka retry topic; một listener khác nhận record sau khoảng chờ rồi thử lại. Sau khi hết số lần thử, record có thể được đưa vào dead-letter topic (DLT). Vì vậy, **một business event duy nhất** có thể đi qua nhiều topic, offset, listener container và application instance.

**Trace khi retry topic** là việc quan sát hành trình này theo các chặng bất đồng bộ, giúp trả lời: lần thử đầu tiên thất bại ở đâu, lần retry nào thành công, bao lâu là thời gian xử lý và bao lâu là thời gian chờ, record có được bàn giao sang DLT hay không, và có bị đứt trace context giữa các Kafka hops không.

Truy vết tốt cần kết hợp **distributed tracing**, **business event ID ổn định**, **structured logs**, **metrics retry/DLT** và thông tin Kafka `topic-partition-offset`. Một trace đẹp không tự chứng minh offset đã commit, business database đã cập nhật duy nhất hay producer đã ghi bền vững. Những bảo đảm đó phải được thiết kế riêng bằng retry/recovery policy, Kafka transaction thích hợp và idempotency.

## 1. Tại sao retry topic làm trace phức tạp?

Một lần gọi HTTP đồng bộ có thể tạo chuỗi span liền mạch trong vài trăm mili-giây. Retry topic tạo nhiều **giai đoạn độc lập**:

~~~text
Business event: evt-42

orders.events
  -> listener lần đầu: FAILURE
  -> publish sang orders.events-retry-2000
  -> record nằm trong retry topic trong lúc backoff
  -> retry listener: FAILURE
  -> publish sang orders.events-retry-10000
  -> chờ lần retry sau
  -> retry listener: SUCCESS

Hoặc nếu hết retry:
  -> orders.events-dlt
  -> operator phân loại và replay trong một thời điểm khác
~~~

Tên topic và delay chỉ là ví dụ; Spring Kafka có cấu hình naming, suffix và reuse retry topic tùy phiên bản. Trong mỗi chặng, Kafka tạo một **record mới ở topic đích**. Record đó có thể giữ event ID nhưng có topic, partition, offset và timestamp khác.

Nếu chỉ xem span của lần đầu, bạn thấy exception nhưng chưa biết event về sau thành công hay được chuyển DLT. Nếu chỉ xem DLT, bạn có thể không biết exception gốc và từng khoảng backoff. Distributed tracing cần nối các chặng đúng, hoặc ít nhất cho phép tra cứu chúng bằng ID nghiệp vụ ổn định.

## 2. Phân biệt các loại định danh

| Định danh | Ý nghĩa | Khi đi qua retry topic |
|---|---|---|
| `traceId` | Một distributed trace do tracer quản lý | Có thể giữ qua hops nếu propagation hoạt động; có thể khác sau replay. |
| `spanId` | Một operation được quan sát | Thường thay đổi ở mỗi consume, publish hoặc business operation. |
| Parent/child relationship | Quan hệ giữa các spans | Cần truyền trace context đúng để liên kết. |
| Span link | Quan hệ nhân quả không buộc là parent/child | Có thể hữu ích cho queue, batch và replay khi instrumentation hỗ trợ. |
| `eventId` | Định danh ổn định của business event | Nên giữ nguyên xuyên retries để chống duplicate và điều tra. |
| `correlationId` | Định danh workflow/request ứng dụng | Có thể nối nhiều events hoặc nhiều traces. |
| Topic/partition/offset | Vị trí một record Kafka | Thay đổi giữa source, retry topics và DLT. |
| Attempt index | Lần thử xử lý theo retry policy | Thay đổi theo chặng, cần lấy từ metadata chính xác. |
| Replay operation ID | Định danh đợt replay do hệ thống/người vận hành khởi tạo | Thường mới với mỗi chiến dịch replay. |

Một event có thể có nhiều trace IDs nếu context bị mất hoặc cố ý tạo trace mới khi replay. Một trace cũng có thể bao gồm nhiều event IDs nếu một request xuất nhiều message. **Không dùng traceId làm idempotency key**.

## 3. Trace xuyên retry hops nên trông như thế nào?

~~~mermaid
sequenceDiagram
    participant P as Source Producer
    participant S as Source Topic
    participant L1 as Source Listener
    participant R1 as Retry Topic 1
    participant L2 as Retry Listener
    participant R2 as Retry Topic 2
    participant L3 as Retry Listener
    participant D as DLT
    P->>S: Publish eventId=evt-42
    S-->>L1: Consumer poll
    Note over L1: Consumer span, attempt 1
    L1->>L1: Business failure
    L1->>R1: Forward retry record, producer span
    Note over R1: Chờ delay bất đồng bộ
    R1-->>L2: Consumer poll khi đủ điều kiện
    Note over L2: Consumer span, attempt 2
    L2->>L2: Failure lần tiếp
    L2->>R2: Forward retry record, producer span
    Note over R2: Chờ backoff tiếp
    R2-->>L3: Consumer poll
    alt Retry thành công
        L3->>L3: Business operation applied
    else Hết retry
        L3->>D: Publish DLT, producer span
    end
~~~

Một span nên phản ánh thời gian **thực sự thực thi** của chặng đó, không ôm trọn thời gian record chờ trong topic. Nếu retry sau 10 phút, không nên duy trì một active span trong 10 phút chỉ để tạo đường thời gian liền mạch.

Có thể đo thời gian chờ bằng event timestamps/headers và metrics; còn trace sẽ biểu diễn các consume/produce/business spans ở những thời điểm tách biệt.

## 4. Spring Kafka @RetryableTopic

Ví dụ một record listener dùng non-blocking retry:

~~~java
@Component
public class OrdersListener {

    private final OrdersService ordersService;

    public OrdersListener(OrdersService ordersService) {
        this.ordersService = ordersService;
    }

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(
                    delay = 2_000,
                    multiplier = 2.0,
                    maxDelay = 10_000))
    @KafkaListener(
            id = "orders-listener",
            topics = "orders.events",
            groupId = "orders-service")
    public void handle(ConsumerRecord<String, OrderEvent> record) {
        ordersService.applyIdempotently(record.value());
    }

    @DltHandler
    public void handleDlt(ConsumerRecord<String, OrderEvent> record) {
        // Quarantine/audit theo policy; không coi đây là business success.
    }
}
~~~

`OrdersService` và `OrderEvent` là các kiểu ứng dụng tự định nghĩa. Những import chính gồm `RetryableTopic`, `KafkaListener`, `DltHandler`, `Backoff`, `ConsumerRecord` và `Component`. Ví dụ không bao gồm cấu hình Kafka broker, serializers, DLT owner hay testing infrastructure.

Với mô hình phổ biến của Spring Kafka, `attempts` là **tổng số lần xử lý gồm lần đầu**; không nên tự suy ra tổng số retry topic theo tên topic. Spring Kafka có thể tạo nhiều retry topics hoặc tái sử dụng topic theo backoff policy/version.

**Lưu ý transaction:** `@RetryableTopic` non-blocking retry không được Spring Kafka hỗ trợ kết hợp trực tiếp với Kafka container transactions theo kiến trúc chuẩn. Nếu cần Kafka EOS, phải thiết kế lại transaction/retry boundary, không giả định annotation tự gộp forwarding và source offset vào một transaction.

## 5. Các lớp observability khác nhau

| Lớp | Tín hiệu chính | Điểm mạnh | Giới hạn |
|---|---|---|---|
| Kafka client metrics | Consumer fetch/lag, producer send | Biết Kafka client có hoạt động không | Không biết business event đã áp dụng. |
| Spring Kafka listener Observation | Listener operation span/metric | Biết attempt mất bao lâu, exception gì | Có thể không bao gồm DLT/retry producer template. |
| Kafka producer Observation | Send operation/span | Theo dõi publish source, retry, DLT | Send span không chứng minh offset nguồn đã commit. |
| Business spans | Database/API/application operations | Khoanh vùng bước chậm hoặc lỗi | Side effect ngoài Kafka không tự transactional. |
| Structured logs | Event ID, topic, offset, attempt, error | Tra cứu một record chính xác | Log retention và bảo mật. |
| Retry/DLT metrics | Attempts, forwarded, recovered, backlog | Đo toàn hệ thống | Không thể hiện đầy đủ hành trình một event. |
| Audit/business state | Outcome bền vững, idempotency | Đối soát kết quả nghiệp vụ | Có thể cần workflow/store riêng. |

Không cố dùng trace làm nguồn sự thật cho mọi chỉ số. Trace có thể bị sampling; metrics đếm lưu lượng; business state xác nhận kết quả.

## 6. Bật Micrometer Observation cho listener container

Trong dòng Spring Kafka hỗ trợ Micrometer Observation:

~~~java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setObservationEnabled(true);

        return factory;
    }
}
~~~

`setObservationEnabled(true)` yêu cầu phiên bản Spring Kafka có hỗ trợ Observation; cần kiểm tra API ở dependency thực tế. Spring Boot có thể cung cấp `ObservationRegistry`, nhưng chỉ bật observation của container không bảo đảm trace đã được export nếu tracing bridge và exporter chưa cấu hình.

Đối với retry, cần xác định **source listener, retry listeners và DLT listener đang dùng container factory nào**. Nếu ứng dụng định nghĩa factory riêng cho retry endpoints, phải bật observation trên đúng factory đó. Không giả định tên bean mặc định có thể bao phủ mọi endpoint do custom setup tạo.

### Timer truyền thống và Observation

Spring Kafka có Micrometer listener timers và Micrometer Observation theo các phiên bản tương ứng. Có thể gặp `setMicrometerEnabled(true)` hoặc `setObservationEnabled(true)`. Tên metrics, span attributes và cách bật hai tính năng này phụ thuộc version.

Không bật cả hai chỉ để “thu nhiều hơn” nếu tạo duplicate telemetry. Kiểm tra metrics xuất ra thực tế qua Actuator và traces trong backend.

## 7. Bật Observation cho KafkaTemplate

Producer send cần được instrument để truyền context từ một Kafka hop sang hop tiếp theo:

~~~java
@Bean
KafkaTemplate<String, OrderEvent> ordersKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory) {

    KafkaTemplate<String, OrderEvent> template =
            new KafkaTemplate<>(producerFactory);

    template.setObservationEnabled(true);
    return template;
}
~~~

Trong các phiên bản Spring Kafka hỗ trợ, khi KafkaTemplate được instrument và có active observation/tracing context, producer instrumentation có thể tạo span, inject trace context vào Kafka record headers. Consumer instrumentation ở hop sau có thể extract context.

**Cần kiểm tra KafkaTemplate thực sự được retry/DLT publisher sử dụng.** Hạ tầng retry có thể được wiring với template khác do bean selection, generic types, serializer hoặc recoverer riêng. Bật observation trên template publish message bình thường **không tự động chứng minh** forwarding retry/DLT cũng được instrument.

Đối với lỗi deserialize, DLT record có thể cần serialize raw bytes thay vì DTO; template/recoverer phải có serializer phù hợp. Tracing cấu hình đúng không sửa được serialization failure khi publish DLT.

## 8. Micrometer Tracing và OpenTelemetry

Một thiết lập Spring Boot có thể dùng Spring Boot Actuator, Micrometer Tracing bridge cho OpenTelemetry và exporter phù hợp:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>
<dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-exporter-otlp</artifactId>
</dependency>
~~~

Những dependency này là ví dụ cho dòng Spring Boot tương thích; dùng BOM của dự án và tránh trộn bridge OpenTelemetry/Brave không chủ đích.

Ví dụ cấu hình tracing trong dòng Spring Boot hỗ trợ các property tương ứng:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.2
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Path/property cấu hình exporter có thể thay đổi giữa các phiên bản Spring Boot; phải xác nhận theo hệ thống đang chạy. Endpoint là placeholder, không phải cấu hình production được phê duyệt. Collector cần kiểm soát bảo mật và giới hạn tài nguyên.

### Sampling và xuất trace

Sampling probability 0,2 không có nghĩa đúng 20% business events sẽ có trace đầy đủ. Sampling có thể được kế thừa từ upstream, context có thể mất ở retry hop, exporter có thể drop span, hoặc trace backend không còn lưu dữ liệu do retention.

Khi không thấy span, đừng lập tức kết luận record bị mất. Tra cứu event ID trong logs và Kafka offsets để phân biệt sampling với lỗi delivery.

## 9. Trace context trong Kafka headers

Thông tin distributed tracing thường được truyền qua **Kafka record headers**, không phải Kafka offset hay message key. Với W3C Trace Context, thường gặp các header `traceparent` và `tracestate`; một stack khác có thể dùng B3 hoặc định dạng propagation khác.

~~~text
Record ở source topic:
  topic      = orders.events
  partition  = 2
  offset     = 901

  headers:
    traceparent  = 00-<trace-id>-<span-id>-<flags>
    x-event-id   = evt-42
    x-flow-id    = order-flow-42
~~~

Các giá trị trong ví dụ là placeholder; không copy làm W3C header thực tế. Propagator của tracing library phải có trách nhiệm tạo/đọc format hợp lệ.

Khi forward sang retry topic, record mới cần được **inject/extract trace context phù hợp**. Không tự copy một `traceparent` cũ một cách máy móc để mọi retry attempt có cùng parent span; đó có thể là quan hệ nhân quả sai. Hãy để Kafka producer/consumer instrumentation và configured propagators xử lý nếu phiên bản/framework hỗ trợ.

### Nguyên nhân context có thể bị đứt

- Source producer không bật tracing instrumentation.
- Retry forwarder dùng KafkaTemplate không instrument.
- Custom recoverer tạo record mới nhưng drop/overwrite headers.
- Producer dùng W3C, consumer chỉ trích B3 hoặc ngược lại.
- Một asynchronous executor không giữ active context.
- Propagation headers bị trùng/ghi đè sai thứ tự.
- Sampling/exporter/retention khiến spans không hiện trong UI.
- Replay DLT dùng một workflow hoàn toàn mới và cố ý tạo trace ID mới.

Cần điều tra từng hop thay vì chỉ thay tracing probability.

## 10. Trace ID không thay thế event ID

`traceId` là định danh observability. `eventId` là định danh business event dùng để liên kết các attempts và bảo vệ idempotency.

Một event có thể tạo nhiều trace IDs:
- Propagation bị lỗi.
- Replay được thực hiện sau nhiều ngày.
- Operator tách workflow recovery.
- Sampling/trace root policy đổi giữa các lần xử lý.

Không tạo event ID mới ở mỗi lần retry chỉ để làm trace mới. Nếu consumer cần deduplicate, event ID phải giữ nguyên cho cùng business effect.

### Header event ID ổn định

~~~java
ProducerRecord<String, OrderEvent> record =
        new ProducerRecord<>("orders.events", orderId, event);

record.headers().add(
        "x-event-id",
        event.eventId().getBytes(StandardCharsets.UTF_8));

record.headers().add(
        "x-flow-id",
        event.flowId().getBytes(StandardCharsets.UTF_8));

kafkaTemplate.send(record);
~~~

`event` và `orderId` là dữ liệu ứng dụng. Chỉ tạo `eventId` một lần khi phát sinh event. Đừng dùng trace ID làm business deduplication key.

Để đọc header:

~~~java
private String readHeader(
        ConsumerRecord<?, ?> record,
        String headerName) {

    Header header = record.headers().lastHeader(headerName);

    if (header == null || header.value() == null) {
        return "missing";
    }

    return new String(
            header.value(),
            StandardCharsets.UTF_8);
}
~~~

Ví dụ sử dụng `org.apache.kafka.common.header.Header`. Khi nhận headers từ producer không tin cậy, cần giới hạn độ dài, kiểm tra encoding và tránh đưa nội dung tùy ý vào log/metric labels.

## 11. Log một attempt với metadata nào?

Một log có cấu trúc hữu ích:

~~~text
timestamp       = 2026-11-15T09:00:00Z
service         = orders-service
eventId         = evt-42
flowId          = order-flow-42
traceId         = current-trace-id
spanId          = current-span-id
listener        = orders-listener
topic           = orders.events-retry-2000
partition       = 1
offset          = 783
attempt         = 2
outcome         = failed
errorCategory   = dependency_timeout
nextDestination = orders.events-retry-10000
~~~

Giá trị chỉ minh họa. Nếu dùng Micrometer Tracing với logging correlation, traceId/spanId có thể được bổ sung vào MDC/structured logs khi observation active; cần kiểm tra logging pattern thực tế.

Không log full Kafka payload, token, password, PII hay stack trace lặp không kiểm soát. Error category nên là tập nhãn hữu hạn. Với sự cố nghiêm trọng, dùng correlation ID và log sampling phù hợp thay vì ghi mọi retry attempt ở mức DEBUG vĩnh viễn.

### Phân biệt topic offset ở từng hop

Record ở `orders.events` offset 901 và record ở `orders.events-retry-2000` offset 783 có cùng event ID nhưng **không phải cùng Kafka log position**. Khi xem trace/log cần giữ topic, partition, offset của từng hop; không lấy retry offset thay offset nguồn để reset consumer group.

## 12. Retry attempt metadata và delivery attempt

Spring Kafka có metadata retry trong headers/infra để tính attempt, timestamp và destination. Tuy nhiên, cần phân biệt:

- Blocking retry có thể sử dụng delivery-attempt metadata theo listener/error-handler policy.
- Non-blocking retry qua `@RetryableTopic` có attempt/retry-topic metadata riêng.
- Cách đặt headers và cách tính số lượt phụ thuộc Spring Kafka version.

Không giả định `KafkaHeaders.DELIVERY_ATTEMPT` luôn có mặt hoặc cùng semantics với số lần thử trên retry topics. Khi cần log attempt index, dùng API/header đúng với cơ chế retry trong phiên bản đang chạy và mô tả rõ lần đầu có được tính là attempt 1 hay không.

**Không suy ra attempt number từ topic suffix**. Một retry topic có thể được tái sử dụng cho nhiều attempt hoặc đặt tên theo delay, không phải theo số lần thử.

## 13. Tạo observation cho business operation

Kafka listener observation thường thể hiện một listener invocation. Nếu muốn thấy việc gọi database, tính toán hoặc HTTP dependency, có thể thêm business observation:

~~~java
@Service
public class OrdersService {

    private final ObservationRegistry observationRegistry;
    private final OrderRepository repository;

    public OrdersService(
            ObservationRegistry observationRegistry,
            OrderRepository repository) {
        this.observationRegistry = observationRegistry;
        this.repository = repository;
    }

    public void applyIdempotently(OrderEvent event) {
        Observation.createNotStarted(
                "orders.apply",
                observationRegistry)
                .lowCardinalityKeyValue(
                        "operation", "apply-order-event")
                .observe(() -> repository.applyOnce(event));
    }
}
~~~

`OrderRepository.applyOnce` là API nghiệp vụ giả định. Truy cập database, business transaction và idempotency phải được thiết kế trong repository/service thật.

`lowCardinalityKeyValue` nên dùng giá trị hữu hạn như tên operation. Không gắn event ID, order ID, email hoặc customer ID vào low-cardinality meter tags. Khi cần ID để tra cứu, dùng structured logs hoặc tracing attributes được kiểm soát; giới hạn dữ liệu nhạy cảm.

Để Spring Kafka retry khi business operation thất bại, listener cần **ném exception** ra cơ chế error handler. Không nuốt exception sau khi gắn span error tag rồi return bình thường, vì container có thể coi record hoàn tất và commit offset.

## 14. Context khi listener dùng executor bất đồng bộ

Micrometer tracing context thường sống trong scope/thread hiện tại. Nếu listener gửi công việc tới `ExecutorService` hoặc `CompletableFuture` mà không truyền context:

~~~text
Consumer thread:
  active traceId = T1
  submit task

Worker thread:
  không có active trace context
  span mới thành root trace T2
~~~

Trong những phiên bản hỗ trợ, có thể dùng Micrometer Context Propagation, `ContextSnapshot` hoặc executor được instrument để capture/restore context phù hợp. Không giả định thread-local tự xuyên thread boundary.

Không truyền `KafkaConsumer` sang worker thread để gọi `poll()`, `seek()` hoặc `commitSync()`; KafkaConsumer nói chung không thread-safe. Việc xử lý bất đồng bộ còn cần bảo đảm acknowledgement và partition ownership an toàn sau rebalance.

### Không giữ span mở trong khoảng retry

Nếu một record chờ trên retry topic 15 phút, active observation của lần thử trước phải kết thúc sau processing/forwarding. Khi retry consumer poll record, instrumentation tạo observation mới và trích xuất context từ headers nếu có. Không giữ span, request scope hoặc transaction mở suốt khoảng delay.

## 15. Đo processing latency và retry wait riêng

| Khoảng thời gian | Mốc bắt đầu/kết thúc | Ý nghĩa |
|---|---|---|
| Listener processing | Vào → ra listener invocation | Thời gian thực hiện một attempt. |
| Forwarding | Producer send retry → ack/result | Thời gian bàn giao sang Kafka. |
| Scheduled backoff | Lần forward → thời điểm đủ điều kiện retry | Delay theo policy. |
| Actual retry wait | Lần forward → lần retry consume | Bao gồm backoff, backlog và outage. |
| Extra retry delay | Due time → attempt start | Chậm thêm do consumer lag/pause/rebalance. |
| End-to-end completion | Business event created → outcome cuối | SLA hoàn tất workflow. |
| DLT unresolved age | DLT publication → resolution | SLA xử lý message lỗi. |

Timestamp Kafka record, source business timestamp và retry due-time headers có semantics khác nhau. Không mặc định mọi retry record timestamp bằng thời điểm message được publish sang retry topic. Kiểm tra cách framework đặt timestamp trong phiên bản đang sử dụng.

Một header như `x-first-seen-at` có thể giúp giữ thời điểm bắt đầu workflow, nhưng chỉ nên tạo một lần và cần validate timestamp từ nguồn không tin cậy. Tracing backend không phải kho lưu trữ SLA bắt buộc; metrics/audit có thể thích hợp hơn.

## 16. DLT publication là một chặng trace riêng

Khi hết retry, recoverer có thể publish sang DLT. Trên trace, nên tách:

~~~text
Source listener: FAILED
Retry attempt 2: FAILED
Retry attempt 3: FAILED
DLT publication: SUCCESS
Business outcome: UNRESOLVED
~~~

**DLT publication success không phải business success.** Offset nguồn có thể tiến sau recovery nhưng đơn hàng, thanh toán hoặc thao tác nghiệp vụ chưa được hoàn tất.

Nếu cần trace DLT, kiểm tra template được `DeadLetterPublishingRecoverer` hoặc retry infrastructure dùng. Với DLT listener có `@DltHandler`, nếu nó được instrument, sẽ có chặng consume DLT riêng.

DLT record có thể mang original topic, partition, offset, exception class hoặc stack trace trong headers do Spring Kafka thêm theo version/config. Không đưa nguyên bộ exception headers vào span attributes vì có thể lớn hoặc chứa dữ liệu nhạy cảm.

## 17. Retry dài và replay DLT: cùng trace hay trace mới?

Có hai chiến lược:

| Trường hợp | Chiến lược tracing | Lưu ý |
|---|---|---|
| Retry delay ngắn, cùng workflow | Propagate trace context để tạo chuỗi spans liên quan | Cần header injection/extraction và sampling nhất quán. |
| Retry delay dài, chờ nhiều giờ/ngày | Có thể duy trì context hoặc dùng trace mới liên kết bằng event ID | Trace backend retention có thể ngắn hơn workflow. |
| Operator replay DLT | Thường hợp lý khi tạo trace mới cho replay operation | Giữ event ID gốc và replay ID để tìm lịch sử. |
| Replay tạo business command mới | Trace mới với correlation đến event nguồn | Phân biệt semantic của command mới và duplicate cũ. |

OpenTelemetry có **span links** để biểu đạt quan hệ nhân quả không nhất thiết là parent-child. Chúng hữu ích trong messaging/batch/replay nếu instrumentation hỗ trợ. Không khẳng định Spring Kafka tự tạo span links cho mọi retry hop; muốn có link riêng cần kiểm tra thư viện hoặc bổ sung custom instrumentation.

Bất kể trace ID thay đổi thế nào, **event ID của cùng business effect phải ổn định** để tránh duplicate khi replay. Nếu tạo event ID mới cho cùng tác động, inbox/deduplication có thể không còn tác dụng.

## 18. Sampling và trace retention

Một trace qua nhiều Kafka hops có thể thiếu spans vì:

- Upstream sample decision không chọn trace.
- Một hop mất propagation headers.
- Retry producer không được instrument.
- Exporter/collector quá tải hoặc lỗi.
- Trace backend chỉ giữ dữ liệu trong một số ngày.
- Retry/DLT replay diễn ra sau retention của trace gốc.
- UI chỉ tìm trong một khoảng thời gian quá ngắn.

Sampling và retention chỉ điều khiển **telemetry**, không làm thay đổi số retry attempts hoặc logic Kafka. Khi cần đo toàn bộ lưu lượng, dùng counters/metrics; khi cần điều tra một event, dùng correlation ID và structured logs.

### Tail sampling

Một OpenTelemetry Collector có thể hỗ trợ tail sampling để ưu tiên trace lỗi hoặc latency cao. Tuy nhiên, retry kéo dài nhiều giờ có thể vượt khoảng collector giữ spans để đưa ra quyết định sampling. Không kỳ vọng một buffer tail-sampling nhớ một trace xuyên nhiều ngày; phải thiết kế policy theo giới hạn tài nguyên thực tế.

## 19. Baggage và bảo mật headers

Tracing baggage có thể truyền dữ liệu qua nhiều services/hops nếu được cấu hình. Baggage chỉ nên dùng cho metadata nhỏ, đã được phê duyệt và thực sự cần thiết.

Không lưu vào baggage, trace tags hoặc Kafka retry headers một cách tùy tiện:

- Mật khẩu, API key, access token, secret.
- Số điện thoại, email, địa chỉ hoặc thông tin thanh toán.
- Payload nguyên văn hay stack trace chứa PII.
- Thông tin định danh người dùng có thể khiến metrics cardinality cao.

Kafka retry/DLT có thể tích lũy exception headers. Header size lớn làm tăng network/storage overhead hoặc thậm chí khiến message vượt giới hạn kích thước. Nên giới hạn các trường trace/correlation và tuân thủ masking/retention policy.

## 20. Phân biệt trace visibility với delivery guarantee

Trace có thể chỉ ra đã gọi producer send, nhưng điều đó không chứng minh record đã được broker xác nhận và source offset đã commit.

| Thấy trong trace | Có thể suy luận | Không thể tự kết luận |
|---|---|---|
| Retry producer send span bắt đầu | Có nỗ lực forward record | Broker đã lưu retry record. |
| Producer send span success | Send operation được instrument đánh dấu thành công | Transaction/offset nguồn đã commit. |
| Retry consume span | Có retry listener nhận record | Business effect đã áp dụng duy nhất. |
| DLT publication span | Có chặng bàn giao DLT | Ticket DLT đã xử lý xong. |
| Listener span success | Listener invocation hoàn tất | Kafka transaction chắc chắn đã commit. |
| Không thấy span | Không có trace hiển thị trong window | Record đã bị mất khỏi Kafka. |

Xác minh delivery bằng producer send result, Kafka topic/partition/offset, committed offsets và recovery policy. Dùng event ID/business audit để kiểm tra kết quả nghiệp vụ. Tracing là **tín hiệu điều tra**, không phải cơ chế commit, retry hay idempotency.

## 21. Metrics bổ sung cho trace retry

Một bộ metric logic hữu ích:

| Metric | Ý nghĩa |
|---|---|
| `listener_attempts_total` | Số listener invocations gồm lần đầu và retry. |
| `listener_failed_attempts_total` | Số lần listener ném exception. |
| `retry_forwarded_total` | Số lần record được bàn giao thành công sang retry topic theo contract. |
| `retry_success_total` | Số lần retry attempt hoàn tất nghiệp vụ. |
| `dlt_published_total` | Record DLT được xác nhận publish. |
| `business_applied_total` | Business event mới được áp dụng, cần idempotency. |
| `retry_wait_seconds` | Độ trễ từ forward đến retry attempt. |
| `retry_topic_lag` | Backlog của retry consumer group. |
| `dlt_unresolved_age` | Tuổi record DLT chưa được xử lý. |

Các tên trên chỉ là **đề xuất custom instrumentation**, không phải Spring Kafka metrics mặc định. Trong Prometheus, Counter có thể được export với hậu tố `_total` và Timer/histogram với `_seconds` theo registry naming convention.

Đừng dùng `traceId` hoặc `eventId` làm metric label. Nên chọn service, environment, logical pipeline, retry stage, error category và outcome có tập giá trị hữu hạn.

## 22. Ví dụ query Prometheus

Giả sử đã tự instrument counters với labels `pipeline` và `stage`:

~~~promql
sum by (pipeline) (
  rate(app_kafka_listener_failed_attempts_total[5m])
)
~~~

Tốc độ retry forward:

~~~promql
sum by (pipeline) (
  rate(app_kafka_retry_forwarded_total[5m])
)
~~~

Số records được xác nhận vào DLT trong một giờ:

~~~promql
sum by (pipeline) (
  increase(app_kafka_dlt_published_total[1h])
)
~~~

Tỷ lệ failed attempts trên retry stage:

~~~promql
sum by (pipeline) (
  rate(app_kafka_listener_failed_attempts_total{stage="retry"}[5m])
)
/
clamp_min(
  sum by (pipeline) (
    rate(app_kafka_listener_attempts_total{stage="retry"}[5m])
  ),
  0.001
)
~~~

Những query chỉ hợp lệ khi instrumentation ghi counters theo cùng contract. Không cộng mọi attempts ở source/retry topics rồi gọi đó là số **unique business events**. Một event có thể tạo nhiều attempts.

Để đo retry backlog, dùng lag theo retry topic/consumer group và thời gian record đã chờ; chênh lệch forward/consume counters trong hai cửa sổ thời gian khác nhau không cho một kết quả backlog chính xác.

## 23. Dashboard tối thiểu

| Dashboard panel | Câu hỏi trả lời |
|---|---|
| Source listener failure rate | Bao nhiêu attempts ở nguồn thất bại? |
| Retry topic forwarded rate | Bao nhiêu record được chuyển sang retry? |
| Retry listener success/failure | Retry có giúp phục hồi không? |
| Retry topic lag | Có backlog ở retry consumer không? |
| Expected vs actual retry delay | Consumer xử lý muộn vì backoff hay vì nghẽn? |
| DLT publication count | Bao nhiêu record hết retry và chuyển recovery? |
| Business applied rate | Bao nhiêu event nghiệp vụ mới thực sự được áp dụng? |
| Trace exporter errors | Có mất telemetry vì exporter/collector không? |
| Consumer rebalance/poll health | Có mất assignment hoặc consumer bị chặn không? |
| DLT unresolved age | Bao lâu trước khi record phải được xử lý/archived? |

Panel trace cho một event hữu ích khi mở từ log/error exemplar hoặc liên kết event ID, nhưng không nên là cách duy nhất biết toàn hệ thống bị lỗi.

## 24. Kiểm thử trace propagation trên retry topology

Nên kiểm thử với Kafka broker tích hợp thực tế hoặc môi trường test tương ứng, có tracing exporter/in-memory span collector và cấu hình `@RetryableTopic` đúng như service.

Kịch bản lỗi tạm thời rồi thành công:

1. Bật Observation trên source/retry listener containers.
2. Bật Observation trên KafkaTemplate của source publisher và retry forwarder.
3. Cấu hình sampling deterministic trong test để không mất spans ngẫu nhiên.
4. Publish event có `eventId` cố định và trace context hợp lệ.
5. Cho listener lần đầu ném exception có kiểm soát.
6. Đợi record được forward sang retry topic.
7. Cho retry attempt sau thành công.
8. Xác nhận record giữ event ID, listener attempts đúng policy.
9. Xác nhận các consume/send spans liên quan được thu và parent/link relationship theo propagation strategy.
10. Đối chiếu Kafka coordinates, outcome và committed offset theo policy.

Kịch bản terminal DLT:

1. Cho mọi attempts thất bại.
2. Chờ record được chuyển sang DLT.
3. Xác minh origin metadata và event ID còn dùng để truy vết.
4. Kiểm tra DLT publication được instrument bằng template đúng.
5. Xác minh outcome là terminal recovery, không phải business success.
6. Nếu DLT replay có chủ đích, kiểm tra replay trace và event ID correlation.

Không test bằng cách cố ý phá ACL, retry topics hoặc message headers trên Kafka production.

### Test context bị đứt

Trong một test riêng, cố ý dùng retry publisher không instrument rồi quan sát việc trace chain bị tách. Sau khi bật Observation đúng template, xác nhận context được inject/extract. Điều này kiểm tra **đúng producer thực tế**, không chỉ việc source listener có span.

## 25. Runbook: Trace dừng sau listener đầu tiên

1. Lấy event ID và Kafka source topic/partition/offset từ logs.
2. Kiểm tra record thực tế đã được forward đến retry topic chưa.
3. Xác định KafkaTemplate/recoverer đã publish retry record.
4. Kiểm tra Observation trên template forward và retry container.
5. Kiểm tra propagation headers ở retry record theo cách an toàn.
6. So sánh format W3C/B3 giữa producer và consumer.
7. Kiểm tra sampling/exporter/collector/backend retention.
8. Kiểm tra retry consumer có assignment, đã đến due time và có lag không.
9. Nếu chưa nối được trace, truy hồi bằng event ID/logs; không coi trace missing là message missing.

## 26. Runbook: Retry wait lớn hơn backoff

1. Xác định thời điểm forward record, due time và retry listener start.
2. Kiểm tra lag trên retry topic/partition.
3. Kiểm tra consumer group member count, assignment và pause.
4. Kiểm tra `max.poll.interval.ms`, rebalance và nonresponsive consumer events.
5. Đo processing duration của retry listener; có poison pill hoặc dependency timeout không.
6. Kiểm tra timestamp/retry metadata theo phiên bản Spring Kafka.
7. Phân biệt delay có chủ đích với delay thêm do backlog/outage.
8. Khắc phục nghẽn, theo dõi retry wait và business outcomes.

## 27. Runbook: Cùng event ID xuất hiện nhiều traces

1. Xác định event đang retry tự động, replay DLT hay một command mới.
2. So sánh event ID và correlation ID xuyên các topics.
3. Kiểm tra `traceparent` ở từng Kafka hop và quan hệ producer/consumer instrumentation.
4. Xác định có custom recoverer drop headers không.
5. Kiểm tra async executor và context propagation.
6. Kiểm tra sampling, tracer format và exporter.
7. Nếu replay sau nhiều ngày, có thể chấp nhận trace mới và liên kết bằng event ID.
8. Không đổi event ID để ép các trace thành một; bảo vệ idempotency trước.

## 28. Runbook: DLT có record nhưng không thấy DLT span

1. Xác nhận DLT topic/partition/offset thực tế.
2. Xác định producer template/recoverer đã thực hiện DLT publication.
3. Kiểm tra Observation của template đó.
4. Kiểm tra send result và error handling, phân biệt send attempted với send acknowledged.
5. Kiểm tra DLT headers, original Kafka metadata và event ID.
6. Đối chiếu trace sampling/exporter status.
7. Tìm lỗi terminal trong source/retry listener logs.
8. Khi DLT được replay, giữ correlation với event nguồn.

## 29. Runbook: Trace đầy đủ nhưng business bị áp dụng trùng

1. Lấy event ID và toàn bộ attempts theo trace/logs.
2. Đối chiếu offset nguồn, crash/rebalance và commit Kafka.
3. Kiểm tra database đã commit trước khi Kafka offset commit không.
4. Kiểm tra inbox/unique event ID trong cùng transaction với tác động nghiệp vụ.
5. Kiểm tra HTTP/external system có idempotency key không.
6. Nếu replay đã tạo event ID mới, xác định có phá deduplication contract không.
7. Dừng replay hàng loạt nếu duplicate gây hại; xử lý bù theo policy.
8. Sửa transaction/idempotency boundary rồi kiểm thử lại. Tracing chỉ chứng minh đường đi quan sát được, không tạo exactly-once.

## 30. Bảng kiểm soát Trace khi retry topic

| Điểm kiểm soát | Câu hỏi | Bằng chứng |
|---|---|---|
| Source listener | Đã bật Observation đúng container chưa? | Effective container config, consume spans. |
| Retry listener | Retry/DLT container có Observation không? | Retry consume spans. |
| Producer forwarder | Retry/DLT KafkaTemplate có Observation không? | Producer spans và template wiring. |
| Propagation | Headers được inject/extract đúng format không? | Kafka headers, trace relationships. |
| Event identity | Event ID ổn định qua retries không? | Application headers, structured logs. |
| Retry metadata | Attempt number có đúng semantics version không? | Retry topic API/headers và logs. |
| Timing | Tách processing duration khỏi retry wait chưa? | Timer, due time, consume timestamps. |
| Failure outcomes | Phân biệt attempt failed, forwarded, DLT và business applied không? | Counters, recoverer result và state nghiệp vụ. |
| Kafka coordinates | Mỗi hop có topic/partition/offset riêng? | Structured logs, broker metadata. |
| Sampling | Có thể mất spans do sampler/exporter/retention không? | Tracing config và collector metrics. |
| Context async | Executor có propagate context khi cần không? | Trace integration test. |
| Security | Headers/tags/logs có tránh token, PII, payload không? | Data policy và redaction. |
| Delivery | Không dùng trace thay offset/send confirmation? | Ack, committed offsets, DLT records. |
| Replay | Replay có correlation và idempotency? | Replay operation ID, inbox/business audit. |
| Diagnosis | Khi trace đứt có cách tìm record bằng event ID không? | Logs, metrics và Kafka coordinates. |

**Kết luận:** Retry topic tạo nhiều **Kafka hops bất đồng bộ** cho cùng một business event. Để trace các hops này, cần bật Micrometer Observation trên **listener containers và đúng KafkaTemplate thực sự publish retry/DLT**, bảo đảm trace context được propagate qua Kafka headers và duy trì **event ID ổn định** xuyên retries. Mỗi attempt nên có span riêng, thời gian chờ retry cần đo bằng timestamp/metrics, và DLT publication phải được phân biệt với business success. Khi trace bị sampling hoặc mất context, dùng event ID, logs, offsets và retry metrics để tìm sự thật; khi trace đầy đủ, vẫn cần idempotency và delivery/recovery policy để bảo đảm tính đúng đắn nghiệp vụ.
