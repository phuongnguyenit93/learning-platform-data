# Trace context của producer

Trong một hệ thống Spring Kafka, một thao tác nghiệp vụ hiếm khi chỉ đi qua một phương thức Java. Ví dụ, HTTP request tạo đơn hàng được xử lý ở service A, service này ghi database và publish sự kiện `OrderCreated` vào Kafka. Service B tiêu thụ sự kiện, gọi API thanh toán rồi tiếp tục publish `PaymentRequested`. Nếu tất cả những thành phần đó chỉ ghi log theo timestamp, đội vận hành sẽ rất khó trả lời: **record Kafka này được tạo bởi request nào, mất thời gian ở producer bao lâu, và lỗi ở consumer downstream có cùng nguyên nhân với request ban đầu không?**

**Trace context của producer** là thông tin dùng để nối bước **gửi Kafka record** vào một distributed trace đã có, đồng thời cung cấp dữ liệu cho consumer tiếp tục trace ở service nhận. Với Spring Kafka và Micrometer Observation/Tracing, context thường được truyền bằng **Kafka record headers** theo propagator được cấu hình, ví dụ W3C Trace Context gồm `traceparent` và có thể có `tracestate`.

Chủ đề này không chỉ là “thêm trace ID vào log”. Cần phân biệt **context đang active trong producer thread**, **producer span**, **Kafka headers được inject khi send**, **context được extract ở consumer**, và **trạng thái thực của record** (send thành công, transaction commit, retry hoặc DLT). Trace giúp quan sát dòng chảy, nhưng không thay thế offset commit, idempotency hay kiểm soát lỗi.

Bài học trình bày khái niệm, cấu hình producer observation, luồng context từ HTTP/Kafka listener sang KafkaTemplate, những vấn đề ở thread bất đồng bộ, retry/transaction, testing, bảo mật và runbook vận hành.

## 1. Trace context trả lời câu hỏi gì?

Distributed tracing mô tả một hoạt động xuyên nhiều thành phần bằng tập hợp các **span** có quan hệ nhân quả. Mỗi span biểu diễn một thao tác, ví dụ HTTP server request, database query, Kafka producer send hoặc Kafka listener processing.

Những trường hợp thường cần trace context:

- Điều tra một HTTP request nào đã publish event bị lỗi.
- Nối Kafka producer span của service A với Kafka consumer processing span của service B.
- Xác định latency phát sinh ở publish Kafka hay ở consumer/downstream.
- Quan sát các service theo một đường xử lý khi nhiều message trộn lẫn trên cùng topic.
- Liên hệ retry hoặc DLT record với lần phát đầu tiên.
- Phân biệt cùng một sự kiện nghiệp vụ được xử lý lại nhiều lần với nhiều sự kiện mới.

Ví dụ topology:

~~~text
Trace T1

HTTP POST /orders   (service orders)
        |
        v
createOrder span
        |
        v
Kafka producer span: orders.events
        |
        | Kafka record + trace headers
        v
Kafka topic: orders.events
        |
        v
Kafka consumer span: billing listener
        |
        v
chargePayment span
        |
        v
Kafka producer span: billing.results
        |
        | Kafka record + trace headers
        v
Kafka topic: billing.results
~~~

Nếu propagation hoạt động đúng, các span có thể được liên hệ trong một trace hoặc bằng span links theo tracing model và công cụ sử dụng. Quan hệ cụ thể giữa producer và consumer spans phụ thuộc instrumentation, propagator và phiên bản thư viện; không nên giả định mọi tracing backend luôn hiển thị chính xác cùng một cây parent-child.

## 2. Trace ID, span ID và trace context khác nhau thế nào?

| Thuật ngữ | Ý nghĩa | Ví dụ mục đích |
|---|---|---|
| **Trace ID** | Định danh trace xuyên nhiều spans | Tìm toàn bộ request/event flow |
| **Span ID** | Định danh một thao tác trong trace | Tìm lần Kafka send cụ thể |
| **Parent context** | Context mà span mới dựa vào | Nối producer span với bước trước |
| **Sampling flag** | Tín hiệu chính sách sampling | Quyết định span có được ghi/export |
| **Trace state** | Metadata nhà cung cấp tracing theo chuẩn tương ứng | Hỗ trợ propagation qua nhiều hệ thống |
| **Baggage** | Metadata được phép truyền kèm context | Trường correlation phi nhạy cảm, nếu thực sự cần |

Trace ID **không** phải Kafka record key. Span ID **không** phải offset. Một trace có thể chứa nhiều sends, nhiều records, thậm chí nhiều topics. Ngược lại, cùng một event có thể được xử lý lại trong nhiều trace mới nếu retry/replay không giữ hoặc không liên kết context ban đầu.

### 2.1. Hai lớp context

Trong một ứng dụng producer, có thể chia thành:

1. **Local/current context**: context tracing đang active trong thread hoặc execution scope tại lúc gọi `KafkaTemplate.send(...)`.
2. **Propagated context**: metadata được inject vào headers của Kafka record để tiến trình khác khôi phục hoặc liên kết trace.

Nếu có local span nhưng không inject headers, trace thường bị đứt ở ranh giới Kafka. Nếu Kafka record có headers nhưng consumer không extract hoặc không có tracing bridge, phía nhận có thể không tạo được quan hệ tracing mong muốn.

### 2.2. Producer span và record headers

Producer span là dữ liệu của hệ thống quan sát, có thể chứa thời gian bắt đầu/kết thúc, topic, trạng thái send và các thuộc tính cho phép truy vết. Kafka headers chỉ mang **ngữ cảnh đủ để nối trace**, không chứa toàn bộ span, không chứa toàn bộ thời gian xử lý và không phải bằng chứng record đã được broker commit thành công.

## 3. W3C Trace Context trong Kafka headers

Với propagator W3C được cấu hình, metadata thông dụng là:

- `traceparent`: version, trace ID, parent span ID, flags.
- `tracestate`: metadata mở rộng theo chuẩn, có thể vắng mặt.

Mô hình giá trị:

~~~text
Kafka record headers:
  traceparent = "00-<32 hex trace-id>-<16 hex parent-id>-01"
  tracestate  = "<provider-specific entries>"   (nếu có)
~~~

Đây là biểu diễn **cấu trúc minh họa**, không phải giá trị header hợp lệ để copy trực tiếp: các dấu ngoặc nhọn phải được thay bằng định danh thực, với độ dài/định dạng chuẩn.

Kafka headers là các cặp tên và `byte[]`, không phải HTTP headers. Tracing propagator chịu trách nhiệm encode và decode giá trị cần thiết. Không nên tự viết string `traceparent` bằng cách ghép trace ID và span ID nếu instrumentation đã cung cấp cơ chế inject, vì có thể tạo context sai quan hệ hoặc không hợp chuẩn.

### 3.1. Trace propagation không giới hạn ở W3C

Một hệ thống khác có thể dùng B3 hoặc định dạng propagation khác. Hai service cần **propagator tương thích** để hiểu headers. Producer ghi `traceparent` theo W3C trong khi consumer chỉ tìm B3 có thể khiến phía nhận bắt đầu một trace mới.

Trong quá trình di chuyển từ B3 sang W3C, cần kế hoạch thống nhất propagation config cho tất cả producers và consumers liên quan. Không nên để từng service tự tạo header tên riêng mà không có hợp đồng rõ.

### 3.2. Kafka headers có thể trùng tên

Kafka cho phép nhiều headers cùng key. Một custom producer hoặc middleware vô tình inject `traceparent` thêm lần nữa có thể tạo nhiều bản:

~~~text
traceparent = context cũ
traceparent = context mới
~~~

Consumer và propagator có thể có cách chọn giá trị khác nhau. Tránh inject thủ công chồng lên instrumentation tự động; nếu phải xử lý record đi qua nhiều lớp republish, kiểm tra chính sách replace/preserve headers và bảo đảm context đúng với lần send hiện tại.

## 4. Luồng context từ producer tới consumer

Một luồng điển hình:

~~~text
Thread xử lý request/service
        |
        | Có Observation/Trace context hiện hành
        v
KafkaTemplate.send(...)
        |
        +--> Tạo hoặc ghi nhận producer observation/span
        |
        +--> Propagator inject trace context vào headers
        |
        v
Kafka ProducerRecord<K,V>
        |
        v
Kafka broker lưu record + headers
        |
        v
Kafka consumer nhận record
        |
        +--> Instrumentation extract headers
        |
        +--> Khởi tạo consumer observation/span
        |
        v
@KafkaListener xử lý nghiệp vụ
~~~

Để trace xuyên hai service, cần đủ cả hai bên:

1. Producer được instrument và có ObservationRegistry/tracing bridge phù hợp.
2. Propagator được cấu hình để inject context vào Kafka headers.
3. Consumer nhận được headers đó và có instrumentation/extractor tương thích.
4. Tracing backend nhận được spans được sampled/exported.

Thành phần nào thiếu sẽ dẫn đến trace thiếu một đoạn, dù Kafka send và Kafka consumption vẫn hoạt động bình thường.

## 5. Micrometer Observation và Micrometer Tracing khác nhau

Spring Kafka các phiên bản hiện đại tích hợp **Micrometer Observation** cho các thao tác Kafka. Observation cung cấp API instrument hoạt động, có thể kết nối với metrics và tracing.

| Thành phần | Vai trò |
|---|---|
| `ObservationRegistry` | Nơi đăng ký handlers và quản lý observations |
| Micrometer Observation | Mô hình hóa thao tác gửi/nhận Kafka như observation |
| Micrometer Tracing bridge | Kết nối observation với tracer như OpenTelemetry hoặc Brave |
| Propagator | Inject/extract trace context qua Kafka headers |
| Tracing exporter/collector | Nhận spans và chuyển đến tracing backend |
| Spring Kafka producer observation | Instrument `KafkaTemplate` sends khi được bật |
| Spring Kafka listener observation | Instrument listener/consumer processing khi được bật |

**Bật Observation không tự động bảo đảm có distributed trace.** Nếu ứng dụng chỉ có ObservationRegistry nhưng không có tracing bridge hoặc tracing handlers, bạn có thể có observation/metrics mà không có trace headers hoặc spans xuất ra backend.

### 5.1. Những điều kiện thực tế

Một ứng dụng Spring Boot/Spring Kafka sử dụng tracing thường cần:

- Spring Kafka version hỗ trợ producer observation.
- Micrometer Observation/tracing dependencies phù hợp.
- Một tracing bridge (chẳng hạn OpenTelemetry).
- Một exporter hoặc integration với tracing backend.
- Cấu hình propagation và sampling.
- Bật observation cho producer/listener cần theo dõi.

Không coi việc thấy library `micrometer-core` trong dependency graph là bằng chứng tracing đã bật đầy đủ.

## 6. Bật producer observation trên KafkaTemplate

Với Spring Kafka 3.x và các phiên bản có API tương ứng, `KafkaTemplate` có phương thức:

~~~java
kafkaTemplate.setObservationEnabled(true);
~~~

Ví dụ tạo template với `ObservationRegistry`:

~~~java
@Configuration
public class TracedKafkaProducerConfig {

    @Bean
    KafkaTemplate<String, OrderEvent> ordersKafkaTemplate(
            ProducerFactory<String, OrderEvent> producerFactory,
            ObservationRegistry observationRegistry) {

        KafkaTemplate<String, OrderEvent> template =
                new KafkaTemplate<>(producerFactory);

        template.setObservationRegistry(observationRegistry);
        template.setObservationEnabled(true);

        return template;
    }
}
~~~

Các kiểu generic và serializer/producer factory phải khớp với ứng dụng thực tế. `ObservationRegistry` cần được cấu hình với tracing handlers/propagators phù hợp; một registry trống hoặc NOOP không mang lại trace end-to-end.

### 6.1. Khi Spring Boot tự cấu hình KafkaTemplate

Nếu Spring Boot tạo `KafkaTemplate` theo auto-configuration, ứng dụng có thể cần bật Observation thông qua bean customization hoặc cấu hình hỗ trợ đúng phiên bản. Khi định nghĩa KafkaTemplate riêng, hãy bảo đảm template thực sự dùng trong service là template đã bật observation.

Không giả định một property YAML được giới thiệu ở bản Spring Boot khác luôn tồn tại ở phiên bản đang chạy. Thay vì suy đoán tên property, hãy xác nhận giá trị thực tế bằng bean configuration và integration test.

### 6.2. Có nhiều KafkaTemplate

Một service có thể có:

- Template dùng JSON cho topic `orders.events`.
- Template dùng `byte[]` cho DLT.
- Template cho một cluster Kafka thứ hai.
- Template dùng trong transaction.

Bật observation cho một template không tự bật cho mọi template khác. Cần lập bảng ownership và kiểm tra từng đường publish, đặc biệt các tác vụ error recovery/DLT.

## 7. Dependencies và tracing backend

Trong ứng dụng Spring Boot 3.x, cấu hình tracing thường dựa trên Actuator, Micrometer Tracing bridge và exporter phù hợp. Ví dụ Gradle tham khảo:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
}
~~~

Các dependencies/versions phải theo dependency management của Spring Boot và tracing backend đang sử dụng. Đây là ví dụ định hướng, không phải danh sách áp dụng cứng cho mọi phiên bản Spring Boot.

Ví dụ cấu hình sampling/export endpoint thường gặp ở các phiên bản Boot 3:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Giá trị 0.1 nghĩa là chính sách sampling dự kiến lấy khoảng một phần mười traces trong điều kiện phù hợp, không phải cam kết chính xác từng tập 10 records sẽ có một trace. Tên properties và cấu hình OTLP có thể thay đổi theo phiên bản Boot, nên cần kiểm tra tài liệu của dependency đang triển khai.

### 7.1. Trace exporter có thể lỗi mà Kafka vẫn hoạt động

Tracing backend không phải Kafka broker. Nếu exporter/collector tạm thời unavailable, business send vẫn có thể thành công, tùy tracing configuration. Không biến exporter unavailable thành nguyên nhân làm mất Kafka record hoặc retry nghiệp vụ vô hạn.

Cần giám sát exporter queue/drop/errors riêng, vì thiếu spans có thể do hạ tầng observability chứ không phải producer không inject headers.

## 8. Ví dụ producer gửi event trong một trace hiện hành

Giả sử HTTP controller gọi một service tạo đơn hàng. Tracing cho HTTP server đã tạo context hiện hành. KafkaTemplate observation sẽ dựa trên context đó để instrument send và truyền context qua Kafka headers nếu cấu hình hoàn chỉnh.

~~~java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderEvent>>
    publish(OrderEvent event) {

        return kafkaTemplate.send(
                "orders.events",
                event.orderId(),
                event);
    }
}
~~~

Không cần tự gắn `traceparent` ở đây nếu KafkaTemplate observation và propagator đã hoạt động. Producer trace context được hình thành từ active observation khi `send(...)` được gọi.

Nếu request thread **không có active tracing context**, instrumentation có thể tạo trace mới cho producer operation (tùy tracing handlers và sampling). Điều này hợp lệ nhưng sẽ không nối với request upstream mà ứng dụng không biết.

### 8.1. Theo dõi kết quả send

`KafkaTemplate.send(...)` trả về một future trên các phiên bản Spring Kafka hiện đại. Producer cần quan sát kết quả:

~~~java
publisher.publish(event).whenComplete((result, error) -> {
    if (error != null) {
        log.error(
                "Kafka publish failed: eventType=OrderEvent",
                error);
        return;
    }

    log.debug(
            "Kafka publish acknowledged: topic={}, partition={}, offset={}",
            result.getRecordMetadata().topic(),
            result.getRecordMetadata().partition(),
            result.getRecordMetadata().offset());
});
~~~

Đoạn code minh họa logging callback; trong ứng dụng thực tế phải thiết kế nơi lưu lỗi/retry theo yêu cầu durability. Callback có thể chạy trên một thread khác nên **không được mặc định trace context của request thread vẫn active tại callback**. Nếu callback cần tạo span hoặc gửi event tiếp, cần context propagation riêng.

### 8.2. Producer span không thay thế send acknowledgment

Thấy producer span trên tracing backend không chứng minh broker đã xác nhận record và càng không chứng minh transaction chứa record đã commit. Một send có thể khởi tạo span rồi thất bại. Vì vậy phải kết hợp:

- Future success/failure.
- Producer error metrics.
- Kafka transaction commit/abort khi có transactions.
- Downstream consumption hoặc business completion metrics.

## 9. Tạo observation nghiệp vụ bao quanh publish

Nếu cần thể hiện hoạt động “xử lý lệnh tạo đơn” trong cùng trace, có thể tạo một observation nghiệp vụ bao ngoài Kafka send:

~~~java
@Service
public class ObservedOrderCommandService {

    private final ObservationRegistry observationRegistry;
    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public ObservedOrderCommandService(
            ObservationRegistry observationRegistry,
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.observationRegistry = observationRegistry;
        this.kafkaTemplate = kafkaTemplate;
    }

    public void submit(OrderEvent event) {
        Observation.createNotStarted(
                "orders.submit",
                observationRegistry)
                .observe(() -> {
                    kafkaTemplate.send(
                            "orders.events",
                            event.orderId(),
                            event).join();
                });
    }
}
~~~

Ví dụ chờ future hoàn tất để minh họa scope và lỗi; production cần deadline/timeout phù hợp, không chờ vô hạn. Observation nghiệp vụ `orders.submit` là một span/observation khác producer observation; nếu tracing handlers được cấu hình đúng, Kafka producer span sẽ được nối với hoạt động hiện hành.

Không tạo vô hạn nested observations cho mọi helper nhỏ. Chọn các ranh giới nghiệp vụ có ích để trace đọc được và sampling/overhead phù hợp.

## 10. Truyền trace context từ @KafkaListener sang KafkaTemplate

Một chuỗi Kafka-to-Kafka thường có:

~~~text
orders.events
     |
     v
@KafkaListener (service billing)
     |
     v
BillingService.process()
     |
     v
KafkaTemplate.send("billing.results", ...)
~~~

Muốn producer span của lần send thứ hai liên hệ với record tiêu thụ, cần instrument **consumer** và **producer**.

Ví dụ factory listener bật observation:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
observedOrdersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        ObservationRegistry observationRegistry) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setObservationRegistry(observationRegistry);
    factory.getContainerProperties()
            .setObservationEnabled(true);

    return factory;
}
~~~

Method:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "billing",
        containerFactory = "observedOrdersListenerFactory")
public void onOrder(OrderEvent event) {
    BillingResult result = billingService.process(event);
    billingKafkaTemplate.send(
            "billing.results", event.orderId(), result);
}
~~~

Ví dụ là skeleton minh họa, cần các bean và serializers tương ứng. Spring Kafka tracing integration sẽ cố extract context từ input headers khi consumer observation được bật, rồi producer observation có thể inject context của lần send tiếp theo.

### 10.1. Cùng JVM không có nghĩa cùng trace

Kafka listener, HTTP controller và scheduled job có thể chạy trên các threads và scopes khác nhau. Chỉ vì chúng thuộc cùng ứng dụng không có nghĩa có parent context chung. Một scheduled job publish Kafka thường bắt đầu một trace mới; một listener được instrument có thể tiếp tục trace context từ record đầu vào.

## 11. Thread boundary: nguồn phổ biến làm đứt trace

Micrometer Tracing thường dựa trên context scope gắn với execution/thread. Khi producer send được gọi ở một thread khác, context không nhất thiết tự đi theo.

Ví dụ:

~~~java
@KafkaListener(topics = "orders.events")
public void handle(OrderEvent event) {
    executor.submit(() -> {
        kafkaTemplate.send("orders.audit", event.orderId(), event);
    });
}
~~~

Trong ví dụ, task được submit ở consumer thread nhưng chạy ở executor thread. Nếu không có context propagation, producer observation bên worker có thể không có parent trace, tạo một trace mới.

**Cảnh báo về reliability:** Ngoài vấn đề tracing, listener trả về trước khi worker hoàn tất có thể khiến offset được acknowledge/commit trong khi Kafka send chưa bền vững. Sửa trace context **không đủ** để bảo vệ dữ liệu; cần xử lý acknowledgment, transaction và task durability riêng.

### 11.1. Dùng Micrometer Context Propagation khi phù hợp

Trong một số phiên bản Micrometer Context Propagation, có thể capture và restore context để chuyển thread:

~~~java
ContextSnapshot snapshot =
        ContextSnapshotFactory.builder()
                .build()
                .captureAll();

executor.submit(() -> {
    try (ContextSnapshot.Scope ignored =
                 snapshot.setThreadLocals()) {
        kafkaTemplate.send(
                "orders.audit",
                event.orderId(),
                event);
    }
});
~~~

Ví dụ chỉ minh họa **context propagation**, không phải luồng xử lý Kafka đáng tin cậy đầy đủ. Để hoạt động cần context-propagation library, accessors và registry phù hợp. API chính xác và mức tự động hóa thay đổi theo Micrometer/Spring Boot version.

### 11.2. Không giữ scope vô hạn

Mỗi task cần đóng scope bằng `try-with-resources` hoặc pattern an toàn tương đương. Nếu quên đóng scope trên thread pool, context của request trước có thể rò sang task sau, tạo trace sai và nguy cơ lẫn metadata giữa các tenant.

### 11.3. CompletableFuture và callback

`whenComplete(...)` có thể chạy trên thread hoàn tất future, không phải thread gốc. Nếu callback tạo span mới hoặc publish một record khác, phải cân nhắc capture/restoration context theo API phù hợp. Không dùng `ThreadLocal` lấy thủ công trace ID và tự truyền qua mọi callback nếu framework đã có context propagation chuẩn.

## 12. Trace context từ scheduled producer và batch job

Một producer có thể không bắt đầu từ HTTP hay Kafka consumer. Ví dụ job định kỳ quét outbox và publish events.

~~~text
@Scheduled / outbox publisher
             |
             v
        KafkaTemplate.send()
             |
             v
         Kafka topic
~~~

Vì không có parent request, producer observation có thể bắt đầu trace mới. Điều này hợp lệ; không cần phát minh một trace ID cố định cho cả phiên chạy job.

Nên dùng:

- Một observation cho batch/job execution nếu hữu ích.
- Event ID hoặc outbox ID ổn định để đối soát nghiệp vụ.
- Producer observation cho từng send hoặc phạm vi phù hợp.
- Link giữa logs và event state khi record bị replay.

Không dùng cùng trace ID cho mọi event của một cron job kéo dài nhiều giờ chỉ vì muốn dashboard hiện một trace duy nhất. Traces có giới hạn kích thước, độ dài và sampling; các quan hệ công việc dài hạn nên dựa vào business correlation ID và state store.

## 13. Trace context của ProducerRecord và KafkaHeaders

KafkaTemplate hỗ trợ gửi record với key, value và headers. Ví dụ khi cần metadata nghiệp vụ:

~~~java
ProducerRecord<String, OrderEvent> record =
        new ProducerRecord<>(
                "orders.events",
                event.orderId(),
                event);

record.headers().add(
        "event-id",
        event.eventId().getBytes(StandardCharsets.UTF_8));

kafkaTemplate.send(record);
~~~

Nếu producer observation đang bật, context tracing có thể được inject khi gửi. `event-id` là metadata nghiệp vụ do ứng dụng quản lý; nó khác `traceparent` do propagator quản lý.

### 13.1. Không tự thêm traceparent khi đã auto-inject

Mẫu nên tránh:

~~~java
record.headers().add(
        "traceparent",
        myManualTraceparent.getBytes(StandardCharsets.UTF_8));
kafkaTemplate.send(record); // template cũng tự inject context.
~~~

Điều này có thể tạo duplicated hoặc stale propagation metadata. Chỉ quản lý thủ công nếu hệ thống thật sự không có instrumentation, và khi đó phải tuân thủ chuẩn propagation/encoding và các quy tắc trust boundary.

### 13.2. Trace context khác KafkaHeaders.CORRELATION_ID

Spring Kafka có những headers như `KafkaHeaders.CORRELATION_ID` dành cho request-reply/correlation trong một số luồng. Chúng **không thay thế** `traceparent`.

| Dữ liệu | Mục tiêu |
|---|---|
| `traceparent` | Distributed trace propagation |
| `KafkaHeaders.CORRELATION_ID` | Ghép một request với reply theo contract cụ thể |
| `event-id` do ứng dụng quy định | Idempotency/deduplication nghiệp vụ |
| Kafka record key | Partition routing và ordering |
| Kafka topic/partition/offset | Vị trí vật lý của record |

Một event có thể có cả trace context lẫn correlation ID và event ID. Không trộn các vai trò.

## 14. Kafka header names và encoding

Kafka header key là chuỗi, value là byte array. Propagators có thể encode text context sang bytes phù hợp. Để kiểm tra bằng tool, chỉ cần biết tên và loại dữ liệu; không cần log toàn bộ headers trong production.

Ví dụ đọc `traceparent` từ ConsumerRecord khi debugging:

~~~java
private static String traceparentOrNull(
        ConsumerRecord<?, ?> record) {

    Header header = record.headers().lastHeader("traceparent");
    if (header == null || header.value() == null) {
        return null;
    }

    return new String(
            header.value(),
            StandardCharsets.US_ASCII);
}
~~~

Đoạn code là **debug utility**, không phải implementation để tự extract và activate trace context. Propagator của tracing library cần xử lý validation, sampling flags, relation và baggage một cách nhất quán.

### 14.1. Tránh log toàn bộ header

Một số headers có thể chứa token, user metadata, stack traces hoặc payload khác. Dùng allowlist cho diagnostics, ví dụ chỉ ghi “traceparent present=true”, topic và event ID đã được bảo vệ.

### 14.2. Kiểm tra độ dài và dữ liệu đầu vào

Producer và middleware có thể nhận thông tin trace từ upstream không đáng tin. Không dùng một header quá dài/không hợp lệ làm input cho metric tags hoặc database field không giới hạn. Thư viện propagator nên được dùng để parse/validate theo chuẩn; ứng dụng thêm giới hạn cho headers tùy trust boundary và policy bảo mật.

## 15. Sampling và vì sao một số events không có trace

Traces thường được sampling để giảm chi phí lưu trữ:

- Một số request được sampled và xuất spans.
- Một số request không sampled nên không có span trong backend.
- Một số spans bị mất vì exporter/collector lỗi.
- Một số records không có parent trace ngay từ đầu.

**Không tìm thấy trace trong backend không nhất thiết có nghĩa record thiếu trace context hoặc producer không gửi Kafka.** Trace propagation và span export là hai khâu khác nhau.

### 15.1. Sampling flag trong traceparent

W3C `traceparent` chứa flags, trong đó sampled bit thường cho biết quyết định sampling. Propagators/tracing bridges xử lý việc diễn giải này. Không nên tự sửa sampled flag trên Kafka header để ép mọi trace xuất hiện; quyết định thực tế còn phụ thuộc sampler, remote parent và tracing policy.

### 15.2. Tốc độ Kafka cao và chi phí tracing

Một producer gửi hàng trăm nghìn messages/giây có thể tạo số lượng spans rất lớn nếu sampling 100%.

Cân nhắc:

- Sampling phù hợp theo service/luồng nghiệp vụ.
- Head-based hoặc tail-based sampling tùy stack đang dùng.
- Giữ đủ metrics ở mức tổng hợp để quan sát throughput/error dù trace bị sample.
- Tăng sampling tạm thời khi điều tra có kiểm soát.
- Theo dõi exporter drops và chi phí lưu trữ.

Không dựa duy nhất vào traces để đo **tổng số Kafka records đã gửi**; metrics/counters phù hợp hơn cho thống kê đầy đủ.

## 16. Low-cardinality và high-cardinality attributes

Observation có thể được gắn attributes/tags phục vụ tracing và metrics. Cần phân biệt:

| Attribute | Cardinality | Nên dùng ở đâu? |
|---|---|---|
| Service name | Thấp | Metrics/traces |
| Kafka topic (tập giới hạn) | Thường thấp-vừa | Metrics/traces nếu kiểm soát |
| Operation type | Thấp | Metrics/traces |
| Result success/failure | Thấp | Metrics/traces |
| Exception class đã chuẩn hóa | Giới hạn | Metrics/traces tùy nhu cầu |
| Trace ID | Rất cao | Logs/traces, không dùng metric label |
| Event ID/order ID/customer ID | Rất cao | Correlation logs/state, không dùng metric label |
| Kafka offset | Rất cao | Debug logs/traces chọn lọc, không dùng metric label |
| Exception message/raw header | Không giới hạn và có thể nhạy cảm | Tránh metrics; logs phải lọc |

Một custom observation convention có thể thêm metadata hữu ích, nhưng nếu đưa event ID hoặc trace ID vào low-cardinality tags, số lượng time series có thể bùng nổ.

### 16.1. Tracing baggage phải được xem là dữ liệu có thể lan rộng

Baggage có thể đi từ producer qua Kafka, consumer và nhiều downstream services. Không đặt:

- Password, access token, API key.
- Email, số điện thoại, địa chỉ cá nhân.
- Full customer profile hoặc dữ liệu thẻ.
- Nội dung payload nghiệp vụ nhạy cảm.

Nếu cần correlation theo tenant, chọn ID đã được phân loại bảo mật, có giới hạn, có allowlist và không tự động export vào mọi span/metric. Quan trọng: **baggage propagation có thể bị giới hạn hoặc không được bật mặc định**, tùy cấu hình library.

## 17. Trace context và Kafka transaction

Trong Spring Kafka, một KafkaTemplate transactional có thể thực hiện nhiều sends rồi commit hoặc abort cùng một Kafka transaction.

~~~text
BEGIN Kafka transaction
       |
       +-- KafkaTemplate.send(record A)
       |       producer observation/span A
       |
       +-- KafkaTemplate.send(record B)
       |       producer observation/span B
       |
       v
COMMIT hoặc ABORT Kafka transaction
~~~

Trace context của A và B có thể cùng trace hoặc cùng parent observation, nhưng **span của từng send không phải là xác nhận cuối cùng của transaction**.

### 17.1. Record gửi thành công chưa chắc được commit

Một `send()` future có thể xác nhận record đã được broker nhận trong transaction, rồi transaction sau đó bị abort. Consumer dùng `read_committed` sẽ không xử lý record thuộc transaction đã abort. Tracing backend vẫn có thể chứa producer span của lần send đã xảy ra.

Vì vậy, khi điều tra “traces cho thấy producer gửi mà consumer không thấy”, hãy kiểm tra:

- Kafka transaction đã commit hay abort?
- Consumer downstream có `read_committed`?
- Transaction timeout hoặc fencing?
- Producer/transaction coordinator logs?
- Topic, partition, event ID và offset?

### 17.2. Exactly-once Kafka không đồng nghĩa trace được xuất đúng một lần

Kafka read-process-write EOS bảo vệ kết quả output Kafka và consumed offsets. Listener có thể được gọi lại sau abort, tạo thêm traces và producer spans của attempts thất bại. Không deduplicate traces chỉ dựa vào Kafka offset.

Tracing phản ánh **nỗ lực thực thi**, kể cả attempt thất bại; dữ liệu Kafka committed và trạng thái nghiệp vụ cần được kiểm tra riêng.

## 18. Trace context khi producer retry

Kafka producer có cơ chế retry gửi request nội bộ khi gặp lỗi tạm thời. Ở tầng Spring Kafka, `KafkaTemplate.send(...)` thường đại diện một thao tác publish logic, nhưng Kafka client có thể thực hiện nhiều network attempts.

Không mặc định:

- Mỗi network retry tạo một producer span mới.
- Một producer span có nghĩa có đúng một network request.
- Trace duration bằng broker processing time.
- Thấy một span nghĩa Kafka đã nhận đúng một business event.

Để phân tích retry nội bộ, dùng Kafka producer metrics (retry rate, request latency, record error metrics) bên cạnh tracing spans.

### 18.1. Application-level retry tạo operation mới

Nếu service chủ động gọi `send(...)` lại sau failure, đó có thể là một producer observation mới. Hai sends có thể cùng trace nếu parent context còn active, hoặc khác trace nếu tác vụ retry diễn ra sau một khoảng dài trong job mới.

Event ID phải **giữ nguyên** để downstream deduplicate. Trace ID không phải idempotency key và có thể thay đổi sau replay.

## 19. Trace context qua retry topics và DLT

Một record lỗi có thể được Spring Kafka infrastructure publish sang retry topic hoặc dead-letter topic:

~~~text
orders.events
      |
      | listener thất bại
      v
orders.events-retry-...
      |
      | vẫn thất bại
      v
orders.events-dlt
~~~

Những record republish có thể được giữ một số headers ban đầu và thêm retry/DLT metadata. **Trace headers có được giữ nguyên, thay mới hay được instrument thành span mới** phụ thuộc recoverer, template, custom header logic, observation config và Spring Kafka version.

Không giả định mọi retry/DLT message đều có traceparent mới hoặc nhất thiết cùng trace ID với record gốc. Hãy kiểm tra thực tế trong integration test.

### 19.1. Lưu event ID ngoài trace ID

Khi record được đưa tới retry/DLT, nên giữ:

- Event ID ổn định.
- Source topic/partition/offset khi có.
- Retry attempt và failure reason theo format được framework hỗ trợ.
- Trace context nếu policy cho phép và propagation thích hợp.

Event ID phục vụ đối soát/replay, trace ID phục vụ quan sát nỗ lực xử lý. Một trace có thể biến mất do sampling/retention trong khi event vẫn cần được phục hồi sau nhiều ngày.

### 19.2. DLT không đồng nghĩa tracing system

DLT giữ record lỗi theo retention của Kafka. Trace backend lưu spans theo retention/sampling riêng. Không dựa vào việc “có trace” thay cho lưu DLT/recovery state, và không dựa vào Kafka DLT làm nơi giữ toàn bộ logs/traces.

## 20. Producer interceptor và custom KafkaProducer

Spring Kafka observation tích hợp với đường gửi của `KafkaTemplate`. Nếu một phần ứng dụng sử dụng trực tiếp `org.apache.kafka.clients.producer.KafkaProducer` hoặc thư viện producer khác, không thể mặc nhiên cho rằng nó được instrument giống KafkaTemplate.

Các lựa chọn:

1. Chuẩn hóa publish qua `KafkaTemplate` đã bật Observation.
2. Dùng instrumentation tương thích cho native producer.
3. Nếu dùng manual propagation, tuân thủ protocol và tránh duplicate inject.
4. Kiểm thử headers và spans trên từng đường gửi.

### 20.1. Thứ tự headers quan trọng khi dùng interceptors

Producer interceptors/custom serializers có thể thay đổi record headers. Một interceptor xóa hoặc thay headers sau khi instrumentation inject có thể làm mất trace context. Ngược lại, interceptor tự inject có thể chồng lên headers do template thêm.

Vì vậy, khi debug propagation:

- Ghi rõ những thành phần can thiệp ProducerRecord.
- Quan sát headers thực tế mà consumer nhận.
- Tránh mutate record headers không kiểm soát.
- Kiểm tra serializer và framework integration theo version.

Không sửa sự cố bằng cách copy trace headers từ một record khác không liên quan; sẽ tạo quan hệ trace sai.

## 21. Quan hệ producer span và consumer span không luôn là “một cây”

Trong messaging, một record có thể được:

- Consume bởi nhiều consumer groups.
- Republish tới nhiều topics.
- Batch cùng nhiều records.
- Aggregate với events khác.
- Replay sau nhiều giờ hoặc ngày.

Khi một operation xử lý nhiều message với các trace contexts khác nhau, mô hình parent-child đơn giản có thể không đủ. Tracing systems có khái niệm **span links** để liên hệ với nhiều contexts. Instrumentation cụ thể quyết định khi nào dùng parent-child và khi nào dùng links.

Đừng ép tất cả messages của một batch vào một trace duy nhất bằng cách chọn traceparent của record đầu tiên. Điều đó có thể biến những requests độc lập thành một trace sai và làm mất khả năng truy vết sự kiện gốc.

### 21.1. Batch producer

Nếu ứng dụng publish hàng nghìn records trong một loop, mỗi send có thể có producer observation riêng. Chọn parent observation cho batch nếu điều đó giúp hiểu công việc, nhưng không nên tạo một trace vô hạn chứa hàng triệu spans.

### 21.2. Consumer group fan-out

Một Kafka record có thể được nhiều consumer groups xử lý độc lập. Mỗi consumer processing operation có thể tạo spans riêng liên hệ cùng producer context. Kafka không bảo đảm chỉ có đúng một consumer span cho mỗi record trên toàn cluster.

## 22. Một test tích hợp kiểm tra header propagation

Unit test chỉ verify `kafkaTemplate.send(...)` được gọi chưa đủ chứng minh headers thực sự được inject. Một integration test nên gửi record qua Kafka và quan sát headers ở consumer.

Kịch bản:

1. Cấu hình KafkaTemplate có ObservationRegistry và tracing bridge.
2. Chọn W3C propagator thống nhất.
3. Tạo một parent observation/tracing scope trong test.
4. Gửi Kafka record bằng template.
5. Chờ send future thành công.
6. Consumer test đọc record ở topic.
7. Xác nhận Kafka headers chứa trace context hợp lệ theo propagator.
8. Xác nhận consumer observation có thể extract/link với context.
9. Đối chiếu trace IDs/spans qua in-memory span exporter nếu stack hỗ trợ.

Đừng chỉ assert raw header không null mà bỏ qua giá trị sai format. Cần test extraction bởi chính propagator ứng dụng dùng.

### 22.1. Ví dụ kiểm tra header ở consumer test

~~~java
ConsumerRecord<String, OrderEvent> received =
        KafkaTestUtils.getSingleRecord(
                consumer,
                "orders.events",
                Duration.ofSeconds(10));

Header traceHeader =
        received.headers().lastHeader("traceparent");

assertThat(traceHeader)
        .as("W3C trace context must propagate")
        .isNotNull();

String traceparent = new String(
        traceHeader.value(),
        StandardCharsets.US_ASCII);

assertThat(traceparent).startsWith("00-");
~~~

Đây là ví dụ test định hướng, không phải class hoàn chỉnh; API helper/assertion phải khớp version thư viện test. Prefix `00-` chỉ kiểm tra rất sơ bộ với W3C version 00, **không thay thế validate đầy đủ**. Trong test tin cậy hơn, dùng propagator để extract và kiểm tra trace ID/parent relationship.

### 22.2. Test không có active parent

Gửi record từ scheduled context không có parent span, xác nhận instrumentation tạo context hợp lệ theo config hoặc hành vi NOOP được dự kiến. Đừng yêu cầu trace ID phải trùng một HTTP request không tồn tại.

### 22.3. Test producer callback bất đồng bộ

Cho send chạy và xử lý `whenComplete` trên thread khác. Nếu callback tạo operation mới, kiểm tra context propagation đúng và scope được đóng. Đồng thời xác nhận send failure không bị nuốt.

### 22.4. Test sampling

Chạy test với sampler quyết định không ghi spans và xác nhận nghiệp vụ Kafka vẫn đúng. Sau đó dùng sampler lấy mẫu đầy đủ cho kiểm thử trace relationships. Tách hai bài toán “record delivery” và “span export” để test không thất bại chỉ vì sampling policy.

## 23. Test xuyên hai microservices

Một bài test end-to-end có thể triển khai:

~~~text
Service A
  HTTP request có trace context
    |
    v
  KafkaTemplate.send("orders.events")
    |
    v
Kafka broker
    |
    v
Service B
  @KafkaListener nhận record
    |
    v
  KafkaTemplate.send("billing.results")
    |
    v
Consumer test hoặc Service C
~~~

Test cần kiểm tra:

- Producer A gửi headers phù hợp propagator.
- Consumer B extract được context.
- Producer B inject context có quan hệ với active processing operation.
- Traces trong backend/in-memory exporter phản ánh causal flow.
- Event IDs/record keys giữ nguyên theo contract.
- Khi B retry, không có side effect trùng nếu nghiệp vụ đòi hỏi.

Không coi trace UI là oracle duy nhất. Dù trace có đủ spans, vẫn phải kiểm tra Kafka send/commit và business state.

## 24. Troubleshooting: producer span có nhưng consumer trace mới

Triệu chứng: trace backend thấy Kafka producer span ở service A, nhưng consumer span của service B dùng trace ID khác.

Các bước:

1. Kiểm tra KafkaTemplate A có bật observation không.
2. Kiểm tra Micrometer Tracing bridge và propagator của A.
3. Đọc headers thực tế của một record test an toàn ở topic.
4. Xác nhận `traceparent` hoặc format propagation đã chọn có mặt và hợp lệ.
5. Kiểm tra consumer B bật observation/extraction ở listener container không.
6. Kiểm tra B dùng cùng propagation format hay đang dùng B3.
7. Xem consumer B có xử lý record qua custom adapter không extract context không.
8. Kiểm tra event có đi qua retry/DLT/custom republisher đã thay headers không.
9. Xem async worker trong B có làm mất active context trước khi tạo span mới không.
10. Kiểm tra sampling/exporter trước khi kết luận trace đứt.

Không sửa bằng cách copy một trace ID tĩnh cho mọi record. Cần nối đúng context của từng operation.

## 25. Troubleshooting: record có traceparent nhưng không có trace trên backend

Có header chưa chắc có span được export.

1. Kiểm tra sampling probability và sampled flag.
2. Kiểm tra tracing bridge và ObservationHandlers.
3. Kiểm tra exporter/collector endpoint, auth và network.
4. Kiểm tra exporter queue/dropped spans/errors.
5. Kiểm tra service name/resource attributes.
6. Kiểm tra thời gian trace backend ingestion và retention.
7. Xác nhận backend query đúng trace ID và time window.
8. Kiểm tra record có chứa trace context từ producer cũ nhưng service hiện tại đã tắt tracing không.

Kafka record và headers có thể tồn tại lâu hơn tracing backend retention. Một event replay sau vài ngày có thể chứa trace ID gốc nhưng không còn trace cũ trong UI; đây không nhất thiết là lỗi Kafka.

## 26. Troubleshooting: callback producer xuất hiện trace khác

Khi `KafkaTemplate.send(...)` hoàn tất, future callback có thể chạy trên thread của producer network hoặc executor khác.

Các bước:

1. Ghi nhận thread gửi ban đầu và thread chạy callback trong môi trường test.
2. Kiểm tra callback có tạo observation/span mới không.
3. Kiểm tra context propagation của executor/callback.
4. Đảm bảo context snapshot được capture đúng trước khi rời scope gốc.
5. Restore context trong scope ngắn và đóng scope đúng cách.
6. Không giữ hoặc truyền toàn bộ ThreadLocal state tùy tiện qua shared thread pool.
7. Xác nhận output send success/failure được xử lý độc lập với tracing.

Nếu callback chỉ ghi log send result, có thể không cần tạo span mới; cần structured log hoặc correlation identifier phù hợp, không nhất thiết kéo cả trace scope sang mọi log statement.

## 27. Troubleshooting: traces “báo gửi thành công” nhưng consumer không nhận

Đừng bắt đầu từ tracing header. Kiểm tra correctness của Kafka delivery:

1. Xem future send đã thành công chưa, hay chỉ có producer span start.
2. Nếu producer transactional, transaction đã commit hay abort?
3. Kiểm tra topic, partition, key, ACL và serialization.
4. Xem consumer group subscription/assignment.
5. Kiểm tra committed offsets và consumer lag.
6. Kiểm tra consumer `read_committed` và open transaction/LSO.
7. Kiểm tra deserialization/conversion errors.
8. Xem retry/DLT recovery paths.
9. Đối soát event ID trong business store.

Trace chỉ giúp định vị lần send, không thay thế broker metadata hoặc consumer group offsets.

## 28. Troubleshooting: trace context bị nhân đôi hoặc trỏ sai request

Các dấu hiệu:

- Nhiều `traceparent` headers trên cùng record.
- Consumer hiển thị parent span thuộc request không liên quan.
- Một worker xử lý event B nhưng log chứa trace ID từ event A.
- Trace dữ liệu giữa các tenant bị trộn.

Cần kiểm tra:

1. Có manual injection cùng lúc KafkaTemplate auto instrumentation không?
2. Có tái sử dụng mutable `ProducerRecord` hoặc headers không?
3. Có interceptor/custom republisher copy stale tracing headers không?
4. Context scope trong thread pool có được đóng sau mỗi task không?
5. Propagators của producer/consumer có chọn giá trị header nhất quán không?
6. Có framework library kép cùng instrument một send không?
7. Có async callback retain/capture context sai thời điểm không?

Nếu trace context bị rò giữa tenants, xem đây là vấn đề bảo mật/correlation nghiêm trọng, không chỉ là UI hiển thị sai.

## 29. Tracing và idempotency là hai việc khác nhau

Một producer có thể gửi event A hai lần vì retry ngoài Kafka transaction:

~~~text
event-id = evt-100

Attempt 1: KafkaTemplate.send(...) -> outcome không rõ
Attempt 2: KafkaTemplate.send(...) -> success
~~~

Hai attempts có thể mang cùng trace ID hoặc khác trace ID, tùy thời điểm và execution context. Downstream không nên dùng trace ID để quyết định đây là duplicate.

Idempotency phải dựa vào:

- Event ID ổn định.
- Business command ID/idempotency key.
- Unique constraint hoặc inbox state.
- Transaction/offset handling đúng semantics.

Trace ID phục vụ quan sát một dòng công việc, không phải định danh business event duy nhất. Một trace có thể bao gồm nhiều events và một event có thể xuất hiện ở nhiều traces sau replay.

## 30. Quy tắc bảo mật khi propagate context qua Kafka

Kafka topics có thể được đọc bởi nhiều consumer groups, lưu retention dài và có quyền truy cập khác nhau. Khi inject context:

- Chỉ truyền những fields cần cho tracing.
- Không tự đưa PII/secret vào `tracestate` hoặc baggage.
- Coi headers đến từ producer ngoài trust boundary là dữ liệu đầu vào không đáng tin.
- Giới hạn kích thước/số lượng headers, tránh header amplification.
- Kiểm tra ACL, TLS, retention và quyền truy cập topics.
- Không export raw payload hoặc secret trong span attributes.
- Dùng allowlist cho tenant/correlation metadata.
- Không dùng trace IDs/event IDs làm metrics labels.
- Không dựa vào traceparent như chữ ký xác thực hoặc bằng chứng nguồn gốc.

W3C trace context là metadata để liên kết hoạt động, **không phải cơ chế authentication hoặc authorization**. Một producer không đáng tin có thể tự tạo một traceparent hợp lệ về mặt cú pháp.

### 30.1. Cross-tenant boundary

Nếu hệ thống đa tenant, cần quyết định có cho phép tiếp tục trace context từ một tenant/source bên ngoài hay không. Trong một số ranh giới bảo mật, việc tạo trace mới và lưu một liên kết có kiểm soát có thể phù hợp hơn là tin toàn bộ remote context.

Không tự động đưa tenant ID, customer ID hoặc request body vào baggage chỉ để tìm kiếm trace tiện hơn.

## 31. Dashboard và metrics đi cùng trace

Trace tốt cho điều tra một hành trình cụ thể; metrics tốt cho xu hướng tổng thể.

| Câu hỏi vận hành | Tín hiệu phù hợp |
|---|---|
 Producer gửi bao nhiêu records/s? | Kafka producer send/record metrics |
| Tỷ lệ gửi lỗi tăng không? | Producer error counters, send failures |
| Send latency thay đổi thế nào? | Kafka client request metrics, observation duration |
| Request nào tạo record lỗi? | Trace context + structured logs/event ID |
| Consumer group có bắt kịp không? | Committed lag, fetch lag, completion rate |
| Transaction đã commit hay abort? | Transaction metrics/logs |
| Retry/DLT có backlog? | Retry topic lag, DLT rate và recovery state |
| Tracing collector có mất spans? | Exporter/collector drops/errors |

Không tạo alert chỉ vì một span không xuất hiện. Hãy kiểm tra sampling và exporter health. Trong incident nghiêm trọng, dùng metrics/logs/offsets để xác nhận impact, còn trace giúp tìm causal path.

### 31.1. Dùng exemplar khi stack hỗ trợ

Một số hệ thống observability hỗ trợ liên kết metric samples với trace IDs qua exemplars. Đây là cách hữu ích để đi từ latency spike đến một trace cụ thể mà không đưa trace ID thành label cardinality cao của mọi time series.

Khả năng hiển thị phụ thuộc backend, exporter và sampling; không giả định mọi Grafana/Prometheus setup đều có exemplars tự động.

## 32. Checklist triển khai producer trace context

### Instrumentation

- [ ] Spring Kafka version hỗ trợ producer observation.
- [ ] KafkaTemplate sử dụng thực tế có `setObservationEnabled(true)`.
- [ ] ObservationRegistry phù hợp đã được gắn vào template.
- [ ] Có Micrometer Tracing bridge và tracer backend/exporter theo kiến trúc.
- [ ] Producer và consumer thống nhất propagation format (ví dụ W3C).
- [ ] Có sampling policy đủ phù hợp throughput và mục tiêu điều tra.

### Kafka headers

- [ ] Integration test chứng minh trace context được inject vào record.
- [ ] Consumer extract được context qua propagator tương ứng.
- [ ] Không inject `traceparent` thủ công trùng với auto instrumentation.
- [ ] Không mutate/copy stale tracing headers giữa records.
- [ ] Có policy cho headers nhận từ nguồn không đáng tin.
- [ ] Không truyền token, PII hoặc secret qua baggage.

### Threading và lifecycle

- [ ] Async tasks/callbacks được thiết kế context propagation rõ ràng.
- [ ] Context scopes được đóng đúng để tránh lẫn thread pool.
- [ ] Không commit Kafka offset quá sớm khi chuyển async chỉ vì tracing đã hoạt động.
- [ ] Transaction commit/abort được quan sát riêng với producer spans.
- [ ] Retry/DLT/replay giữ event ID và metadata nguồn theo contract.

### Vận hành

- [ ] Metrics cho Kafka send success/failure, latency và consumer lag.
- [ ] Logs có correlation metadata phù hợp nhưng không lộ dữ liệu nhạy cảm.
- [ ] Tracing exporter/collector có health metrics.
- [ ] Có runbook trace thiếu, trace tách và duplicate headers.
- [ ] Đã test sampling, broker send failure và Kafka transaction abort.
- [ ] Không coi một trace ID là idempotency key hoặc chứng nhận Kafka delivery.

## Kết luận

**Trace context của producer** cho phép một thao tác `KafkaTemplate.send(...)` liên hệ với hoạt động upstream và mang ngữ cảnh sang consumer qua Kafka record headers. Trong Spring Kafka hiện đại, cách triển khai thường là bật **Micrometer Observation** trên KafkaTemplate, kết hợp `ObservationRegistry`, Micrometer Tracing bridge và một propagator thống nhất như W3C Trace Context. Producer và consumer đều cần instrumentation phù hợp, đặc biệt khi có nhiều service, thread pools, retry topics hoặc DLT.

Tracing giúp trả lời **“message này đến từ luồng xử lý nào?”**, nhưng không trả lời đầy đủ **“record đã được Kafka commit và nghiệp vụ hoàn tất chưa?”**. Send futures, transaction commits, committed offsets, consumer lag, idempotency và recovery state vẫn là nguồn dữ liệu cần thiết cho reliability. Hãy giữ trace context đúng ranh giới, tránh nhân đôi headers, xử lý async context cẩn thận, kiểm soát baggage và sampling, đồng thời dùng integration tests để xác nhận context thật sự đi qua Kafka trước khi dựa vào tracing khi có sự cố.
