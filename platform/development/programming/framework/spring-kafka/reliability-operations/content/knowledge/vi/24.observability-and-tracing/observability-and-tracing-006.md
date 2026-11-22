# Liên kết trace giữa topic và listener

Trong một hệ thống dùng Spring Kafka, một yêu cầu có thể bắt đầu từ HTTP API, tạo sự kiện trên Kafka, đi qua vài consumer group rồi mới hoàn tất nghiệp vụ. Các service có thể hoạt động đúng nhưng việc điều tra sự cố vẫn rất khó nếu mỗi thành phần chỉ ghi log độc lập: khi đơn hàng chậm, ta không biết độ trễ nằm ở producer, broker, listener, database hay một lần retry.

**Liên kết trace giữa topic và listener** là quá trình truyền ngữ cảnh truy vết (trace context) từ bên gửi record qua **Kafka headers**, rồi khôi phục ngữ cảnh ở bên nhận để các span quan sát được có thể được liên kết trong hệ thống distributed tracing. Trong Spring Kafka hiện đại, mô hình chủ yếu dựa trên **Micrometer Observation**, **Micrometer Tracing** và một tracer implementation như OpenTelemetry hoặc Brave.

Mục tiêu là thấy một hành trình liên tục ở mức logic:

    HTTP POST /orders
         |
         v
    order-api: HTTP server span
         |
         +--> validate command span
         |
         +--> Kafka producer span: orders.created
                      |
                      v
                 Kafka topic
                      |
                      v
    inventory-worker: Kafka listener span
         |
         +--> inventory DB span
         |
         +--> Kafka producer span: inventory.reserved
                      |
                      v
                 Kafka topic
                      |
                      v
    billing-worker: Kafka listener span
         |
         +--> payment API span

Một trace giúp xác định các đoạn công việc liên quan, nhưng **trace không phải cơ chế giao nhận message**, không bảo đảm exactly-once, và không thay thế offset, consumer lag hoặc event ID. Tracing cần được triển khai cùng các biện pháp reliability vốn có của Kafka.

## 1. Trace, span, trace context là gì?

**Trace** biểu diễn một luồng công việc logic xuyên nhiều thành phần. Nó được định danh bằng trace ID.

**Span** biểu diễn một thao tác trong trace, ví dụ một HTTP request, việc gửi record Kafka hoặc việc xử lý record trong @KafkaListener. Span có span ID, thời điểm bắt đầu/kết thúc, parent/link theo mô hình tracer, tags/attributes và có thể có error status.

**Trace context** là thông tin đủ để bên nhận biết record thuộc chuỗi truy vết nào. Context thường bao gồm trace ID, span ID của thao tác liên quan, sampling flag và một số trường phụ khác theo định dạng propagation.

Ví dụ khái niệm:

    TraceId = 8c0e...d742

    Span A: HTTP POST /orders
       |
       +-- Span B: kafka send orders.created
             |
             +-- Span C: consume orders.created
                    |
                    +-- Span D: SQL INSERT inventory

Một hệ thống truy vết có thể hiển thị quan hệ parent-child hoặc span links tùy instrumentation và quy ước tracing đối với messaging bất đồng bộ. Không nên bắt mọi span messaging phải nằm trong cùng một cây parent-child nếu thư viện hoặc mô hình xử lý dùng liên kết khác.

## 2. Trace context đi qua Kafka bằng cách nào?

Kafka record chứa **key**, **value**, metadata topic/partition/offset và **headers**. Kafka không tự hiểu trace ID, nhưng headers cho phép producer đính kèm context mà consumer có thể đọc.

    Producer JVM
        |
        | current tracing context
        v
    Trace propagator INJECT vào Kafka Headers
        |
        v
    Kafka ProducerRecord
      topic: orders.created
      key: O-100
      value: {...}
      headers:
        traceparent: ...
        tracestate: ...
        baggage: ...       (nếu bật)
        event-id: evt-100  (header nghiệp vụ riêng)
        |
        v
    Broker lưu record và headers
        |
        v
    ConsumerRecord
        |
        v
    Trace propagator EXTRACT từ headers
        |
        v
    Spring Kafka listener Observation / Span
        |
        v
    @KafkaListener business code

Broker **không tạo span cho mỗi record bằng mặc định** chỉ vì record có tracing headers. Broker chỉ lưu/trả record. Instrumentation ở producer, consumer và các service liên quan mới tạo các span tương ứng.

Nếu producer không inject tracing context, consumer có thể bắt đầu một trace mới. Nếu consumer không extract được context, hai service có thể tạo span thành công nhưng không liên kết được với nhau.

## 3. Topic không phải là span và không phải là trace ID

Một topic có hàng triệu message từ nhiều request/nghiệp vụ. Topic name chỉ là nơi vận chuyển, không đủ để định danh một hành trình cụ thể.

Phân biệt:

| Khái niệm | Ví dụ | Mục đích |
|---|---|---|
| Topic | orders.created | Kênh message |
| Partition | 3 | Thứ tự/parallelism cục bộ |
| Offset | 7281 | Vị trí record trong partition |
| Event ID | evt-100 | Định danh sự kiện nghiệp vụ |
| Correlation ID | cmd-987 | Ghép các bước của một workflow |
| Trace ID | 4bf9...4736 | Định danh chuỗi truy vết |
| Span ID | 00f0...e0e1 | Định danh một thao tác trong trace |
| Consumer group | inventory-worker | Đơn vị tiêu thụ độc lập |

Event ID nên bền vững qua retry/re-drive để hỗ trợ idempotency. Trace ID phục vụ quan sát và có thể khác giữa các lượt replay tách biệt, tùy chính sách tracing.

Không dùng trace ID thay cho event ID làm khóa deduplication: sampling, root trace mới hoặc tái phát sự kiện có thể thay đổi tracing context.

## 4. Trường hợp cần liên kết trace

Có nhiều dạng giao tiếp:

1. **HTTP → Kafka → Listener:** ghi nhận từ request đầu vào tới consumer xử lý.
2. **Listener → Kafka → Listener khác:** theo dõi chuỗi pipeline xử lý sự kiện.
3. **Scheduler → Kafka → Listener:** không có HTTP parent; scheduler có thể tạo root observation.
4. **Một record → nhiều topic:** một listener phát nhiều sự kiện downstream với context riêng phù hợp.
5. **Một topic → nhiều consumer groups:** cùng record được nhiều group xử lý độc lập.
6. **Retry/DLT/re-drive:** record được xử lý nhiều lần, cần quan sát từng attempt và nguyên nhân.
7. **Batch/aggregate:** một output phụ thuộc nhiều input; quan hệ trace không còn là một parent duy nhất.

Mục tiêu tracing khác nhau giữa luồng synchronous và asynchronous. Không nên giả định một trace luôn biểu diễn toàn bộ workflow kéo dài nhiều ngày; với processing rất lâu, có thể dùng trace mới kèm span links hoặc business correlation ID.

## 5. Micrometer Observation và Micrometer Tracing

Trong Spring Kafka hiện đại, các thành phần liên quan:

**Micrometer Observation** cung cấp API tạo observation cho một thao tác, gắn key-values, lỗi và lifecycle. Observation có thể được quan sát thành metric, trace hoặc cả hai tùy handlers đã cấu hình.

**Micrometer Tracing** kết nối Observation với tracer implementation. Khi có tracing handler, một observation có thể tạo span và tham gia context propagation.

**OpenTelemetry/Brave bridge** cung cấp implementation tracer và liên kết với exporter hoặc tracing backend.

**Spring Kafka instrumentation** tạo observation cho các đường gửi/nhận message khi được bật ở KafkaTemplate và listener container.

Luồng khái quát:

    KafkaTemplate.send()
       |
       v
    Micrometer Observation
       |
       v
    Tracing handler / Tracer
       |
       v
    Context propagator -> Kafka Headers
       |
       v
    Broker

    ConsumerRecord.Headers
       |
       v
    Context propagator extract
       |
       v
    Listener Observation
       |
       v
    Tracer span + @KafkaListener execution

Chỉ thêm dependency OpenTelemetry vào classpath **không bảo đảm** KafkaTemplate và container tự động truyền context; cần xác nhận instrumentation và ObservationRegistry thực sự được cấu hình.

## 6. Các dependency thường dùng

Ví dụ Gradle với Spring Boot 3.x, giả định sử dụng dependency management của Spring Boot:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'

    // Actuator + Observation/metrics integration.
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Chọn một bridge tracing phù hợp; ví dụ OpenTelemetry.
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'

    // Nếu muốn xuất traces qua OTLP tới collector/backend.
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    // Optional: nếu scrape metrics bằng Prometheus.
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Dùng version do BOM của framework quản lý, tránh tự trộn các phiên bản Micrometer/OTel không tương thích.

Một dự án khác có thể chọn bridge Brave thay vì OpenTelemetry:

~~~gradle
implementation 'io.micrometer:micrometer-tracing-bridge-brave'
~~~

Thông thường **không nên bật đồng thời hai tracer bridges** nếu không có thiết kế tường minh. Việc có exporter không đồng nghĩa collector đang nhận dữ liệu; cần endpoint, sampling, networking và backend hoạt động.

Spring Boot 4 và các bản Spring Kafka mới có thể thay đổi tên starter/property và mặc định. Khi nâng version, đối chiếu tài liệu đúng dependency thay vì sao chép nguyên dependency list của bản trước.

## 7. Bật observation cho KafkaTemplate và listener

Một ví dụ Spring Kafka 3.x cấu hình chủ động ở Java:

~~~java
@Configuration
public class KafkaObservationConfiguration {

    @Bean
    KafkaTemplate<String, OrderEvent> observedKafkaTemplate(
            ProducerFactory<String, OrderEvent> producerFactory) {

        KafkaTemplate<String, OrderEvent> template =
                new KafkaTemplate<>(producerFactory);

        // Bật producer observation/tracing cho send().
        template.setObservationEnabled(true);

        return template;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);

        // Bật listener observation cho record listener.
        factory.getContainerProperties()
                .setObservationEnabled(true);

        return factory;
    }
}
~~~

Các import chính:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
~~~

OrderEvent là DTO ứng dụng. Phần ví dụ giả định đã có ConsumerFactory, ProducerFactory, serializers và ObservationRegistry/tracing infrastructure phù hợp trong Spring context.

Trong nhiều ứng dụng Spring Boot, template/factory do Boot auto-configure có thể được điều khiển qua properties tương ứng. Nếu tự định nghĩa bean, cần xác nhận custom bean thực sự được instrument. Đừng tạo một observed KafkaTemplate nhưng lại inject template khác vào service gửi message.

## 8. Cấu hình Spring Boot quan sát Kafka

Một ví dụ mang tính định hướng cho các dòng Spring Boot 3.x có hỗ trợ properties sau:

~~~yaml
spring:
  application:
    name: order-service
  kafka:
    bootstrap-servers: localhost:9092
    template:
      observation-enabled: true
    listener:
      observation-enabled: true
    consumer:
      group-id: order-workers
      enable-auto-commit: false

management:
  tracing:
    sampling:
      probability: 1.0
~~~

Giá trị sampling 1.0 thường phù hợp để học hoặc test, **không mặc định phù hợp production** vì số lượng spans của hệ thống nhiều record có thể rất lớn.

Các property thực tế được bind và những bean auto-configured phụ thuộc Spring Boot version; nếu dự án dùng custom listener factory hoặc custom KafkaTemplate, nên kiểm tra Java configuration và runtime observation thay vì chỉ tin YAML đã được áp dụng.

Nếu muốn xuất trace tới OpenTelemetry Collector, cần thêm exporter/tracing endpoint đúng theo version của Boot và hạ tầng đang dùng. Không đặt endpoint tracing vào Kafka bootstrap-servers: collector/exporter và broker Kafka là hai đích khác nhau.

## 9. Producer: context hiện tại được inject khi send

Giả sử API nhận CreateOrderCommand và phát event:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderEvent event) {
        kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
        );
    }
}
~~~

Nếu HTTP server request đang có một Observation/tracing context và KafkaTemplate đã bật observation, instrumentation có thể tạo producer span rồi inject context vào headers của record được gửi.

    HTTP trace context
           |
           v
    Controller -> Service -> observed KafkaTemplate
                                |
                                v
                  Producer observation/span
                                |
                                v
                      Kafka record headers

Không cần tự set traceparent bằng cách lấy một trace ID rồi ghi thành header chuỗi tùy ý. Một trace context hợp lệ cần format, span ID, sampling flags và propagator nhất quán; nên để tracing instrumentation quản lý.

Để liên kết chính xác, producer phải chạy ở scope có tracing context đang active. Nếu send() chạy trên thread khác mà context không được chuyển qua, record có thể bắt đầu trace mới.

## 10. Consumer: extract context trước khi chạy listener

Record listener:

~~~java
@Component
public class OrderEventListener {

    private final OrderService orderService;

    public OrderEventListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "ordersListener",
        topics = "orders.created",
        groupId = "order-workers",
        containerFactory = "ordersListenerFactory"
    )
    public void onOrder(ConsumerRecord<String, OrderEvent> record) {
        orderService.process(record.value());
    }
}
~~~

Khi listener container có observation và propagator khớp với producer, Spring Kafka có thể extract context từ ConsumerRecord.headers() để khởi tạo observation/span cho lần xử lý.

Khi tracer export dữ liệu, hệ thống truy vết có thể hiển thị thao tác tiêu thụ record liên quan với producer span, theo quan hệ mà instrumentation và semantic conventions hiện hành quy định.

Nếu không có context từ producer, listener observation vẫn hữu ích: nó có thể khởi tạo span gốc mới cho lần nhận record đó. Điều cần kiểm tra là **trace liên kết đúng khi headers tồn tại**, thay vì chỉ kiểm tra consumer có một span bất kỳ.

## 11. Một ví dụ end-to-end qua hai topic

Giả sử service A nhận đơn hàng, service B kiểm tra tồn kho, service C gửi thông báo.

    Service A:
      HTTP POST /orders
      |
      +-- send orders.created
              |
              v
           Topic 1
              |
              v
    Service B:
      @KafkaListener orders.created
      |
      +-- inventoryService.reserve(...)
      |
      +-- send inventory.reserved
              |
              v
           Topic 2
              |
              v
    Service C:
      @KafkaListener inventory.reserved
      |
      +-- notificationService.notify(...)

Muốn nối trace qua hai topic, cần có instrumentation phù hợp ở **cả hai nơi gửi** và **cả hai nơi nhận**:

| Thành phần | Cần gì? |
|---|---|
| Service A KafkaTemplate | Inject tracing headers |
| Topic orders.created | Giữ nguyên Kafka headers của record |
| Service B listener container | Extract tracing headers |
| Service B KafkaTemplate | Inject context hiện tại sang record mới |
| Topic inventory.reserved | Vận chuyển headers mới |
| Service C listener container | Extract tracing headers |
| Tracing backends | Nhận spans từ cả ba service |
| Sampling policy | Không loại bỏ toàn bộ spans cần so sánh |

Lỗi thường gặp: Service B có observed listener nhưng gửi output bằng KafkaTemplate không bật observation. Khi đó Service C có thể tạo span của riêng mình nhưng không có context từ producer B để nối tiếp.

## 12. Header propagation phổ biến: W3C Trace Context

Một format truyền context phổ biến là **W3C Trace Context**, gồm các header như:

- **traceparent:** mô tả version, trace ID, parent span ID và flags.
- **tracestate:** metadata bổ sung phục vụ vendor/tracer khi được sử dụng.
- **baggage:** có thể truyền một số thông tin ngữ cảnh bổ sung nếu hệ thống bật propagation tương ứng.

Ví dụ giá trị traceparent về mặt hình thức:

~~~text
traceparent:
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Đây là một ví dụ đúng dạng W3C, không phải ID sinh cho sự kiện thực tế. Kafka header values là byte arrays; instrumentation sẽ encode/decode chúng theo propagator.

Một deployment khác có thể dùng B3 propagation hoặc nhiều propagation formats cùng lúc. Nếu producer dùng B3 mà consumer chỉ hiểu W3C, context có thể không được extract thành công dù Kafka record vẫn còn headers.

**Cần thống nhất propagation format giữa các service** hoặc cấu hình propagation bridge phù hợp trong giai đoạn migration. Đừng giải quyết bằng cách tự sao chép text trace ID vào một custom header rồi gọi đó là distributed tracing hoàn chỉnh.

## 13. Không có tracing headers thì điều gì xảy ra?

Một record có thể do legacy producer, CLI, batch import hoặc connector không tích hợp tracing tạo ra:

~~~text
topic: orders.created
key: O-100
value: {...}
headers:
  event-id: evt-100
~~~

Listener vẫn có thể đọc và xử lý record. Nếu observation bật, hệ thống có thể tạo consumer span mới nhưng không liên kết về một producer span trước đó.

Đây không nhất thiết là lỗi dữ liệu. Các cách xử lý:

1. Giữ consumer logic hoạt động khi không có traceparent.
2. Ghi nhận tỷ lệ record có/không có tracing context nếu cần.
3. Triển khai propagation dần cho producer.
4. Dùng eventId/correlationId để truy vết nghiệp vụ khi distributed trace không có.
5. Không từ chối record chỉ vì thiếu tracing header trừ khi contract riêng có quy định rất đặc biệt.

Tracing phục vụ quan sát, không nên trở thành điều kiện bắt buộc làm ngừng pipeline giao nhận sự kiện khi hệ thống observability lỗi.

## 14. Sampling và vì sao một trace có thể bị thiếu span

Tracing có thể tạo lượng dữ liệu lớn khi Kafka throughput cao. Sampling chọn những trace được ghi/export để kiểm soát chi phí.

Ví dụ:

    Input: 10.000 records/s
    Producer + consumer: ít nhất 2 spans mỗi record
    Nếu sample 100%:
      >= 20.000 spans/s, chưa tính HTTP/DB/other spans

Ở production, sampling thấp hơn thường giúp giảm storage và network, nhưng có thể khiến một số event không có trace đầy đủ trong backend.

Một số nguyên nhân khiến trace không hiện đầy đủ:

- Parent được sample hoặc không sample theo chính sách của tracer.
- Consumer không đọc đúng propagation header.
- Span được tạo nhưng exporter không gửi được.
- Tracing backend lọc hoặc giới hạn ingest.
- Một số service không bật observation.
- Root trace quá lâu hoặc chạm giới hạn giữ dữ liệu.
- Consumer dùng format propagation khác producer.

Không được xem “không tìm thấy trace” là bằng chứng message bị mất. Hãy kiểm tra eventId, topic/partition/offset, group committed offset và processing logs song song.

## 15. Baggage không phải nơi chứa payload nghiệp vụ

**Baggage** cho phép truyền một số key-value cùng tracing context giữa các service. Nó có thể hữu ích cho thông tin rất nhỏ và phù hợp chính sách, ví dụ một mã phân nhóm workload đã được làm sạch.

Tuy nhiên:

- Baggage có thể được propagation xuyên nhiều service và hệ thống.
- Một số header/baggage có thể xuất hiện trong log hoặc exporter.
- Baggage làm tăng kích thước Kafka headers.
- Baggage có thể bị người ngoài lợi dụng nếu nhận từ nguồn không đáng tin cậy.
- Không phải mọi baggage field đều tự xuất hiện thành span attribute hoặc log field.

Không đưa password, access token, email cá nhân, số thẻ, toàn bộ customer profile hay payload nhạy cảm vào baggage. Với dữ liệu nghiệp vụ, dùng event payload và chính sách schema/authorization phù hợp.

Nếu cần định danh tenant, cân nhắc dùng tenant ID đã được kiểm soát dưới dạng metadata nghiệp vụ riêng, và chỉ đưa nó vào trace theo chính sách bảo mật/retention rõ ràng.

## 16. Trace ID, correlation ID và event ID phục vụ những việc khác nhau

Một hệ thống tốt thường cần cả ba.

Ví dụ:

    eventId = evt-100
    correlationId = order-flow-99
    traceId = 9a2b...17de

**eventId** giữ nguyên qua retry và re-drive của cùng sự kiện. Consumer dùng eventId để deduplicate hoặc tra audit.

**correlationId** có thể liên kết nhiều sự kiện trong cùng một workflow nghiệp vụ kéo dài nhiều phút hoặc ngày, ví dụ toàn bộ quá trình tạo đơn và thanh toán.

**traceId** mô tả đường thực thi được quan sát. Một retry thực hiện nhiều giờ sau có thể được thể hiện như trace mới, liên kết qua eventId/correlationId hoặc span links.

Không dùng trace ID để quyết định chuyển tiền, xác nhận thanh toán hoặc bảo đảm idempotency. Một event có thể được xử lý thành công khi sampling tắt hoặc tracing backend không sẵn sàng.

## 17. Thêm span nghiệp vụ bên trong listener

Khi consumer observation đang active, có thể tạo một observation con cho bước nghiệp vụ tốn thời gian để biết độ trễ cụ thể nằm ở đâu.

~~~java
@Service
public class InventoryService {

    private final ObservationRegistry observationRegistry;
    private final InventoryRepository repository;

    public InventoryService(
            ObservationRegistry observationRegistry,
            InventoryRepository repository) {

        this.observationRegistry = observationRegistry;
        this.repository = repository;
    }

    public void reserve(OrderEvent event) {
        Observation.createNotStarted(
                "inventory.reserve",
                observationRegistry)
            .lowCardinalityKeyValue("operation", "reserve")
            .observe(() -> repository.reserve(event.orderId()));
    }
}
~~~

Các import cần thiết:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;
~~~

Ví dụ giả định repository.reserve() là thao tác đồng bộ; đoạn lambda được quan sát có lifecycle bắt đầu/kết thúc trong cùng thread.

Tùy ObservationRegistry handlers và tracing configuration, observation này có thể tạo một span con, một metric hoặc cả hai. Dùng tên observation ổn định; không gắn orderId, eventId hoặc Kafka offset vào **low-cardinality metric tags**.

Nếu cần tìm một event cụ thể, thêm thông tin định danh vào structured logs hoặc trace attributes theo chính sách bảo mật, chứ không đưa ID ngẫu nhiên vào metric labels.

## 18. Quan sát một lần gửi Kafka bất đồng bộ

KafkaTemplate.send() thường trả về CompletableFuture với kết quả gửi. Lời gọi trả future không đồng nghĩa broker đã xác nhận hoặc producer transaction đã commit.

Ví dụ:

~~~java
CompletableFuture<SendResult<String, OrderEvent>> future =
        kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
        );

future.whenComplete((result, error) -> {
    if (error != null) {
        log.error("Kafka send failed for eventId={}",
                event.eventId(), error);
    }
});
~~~

KafkaTemplate observation giúp mô tả hoạt động send theo instrumentation của framework. Tuy nhiên, callback khi future hoàn tất có thể chạy trên thread khác, nơi thread-local tracing context của HTTP request ban đầu không còn active.

Không mặc định log trong whenComplete sẽ có cùng traceId/spanId chỉ vì callback được tạo trong request thread. Nếu ứng dụng cần tracing cho logic callback, cần **context propagation** qua executor/callback theo cơ chế framework đang dùng.

Nếu dùng Kafka transaction, send success/observation success cũng không tự chứng minh transaction đã commit. Khi phân tích delivery, vẫn cần transaction commit outcome và broker confirmation.

## 19. Thread-local context và async executor

Phần lớn tracing context được gắn với scope hiện hành, thường dựa trên thread-local hoặc context abstraction của framework.

Một listener đồng bộ:

    Consumer thread
       |
       +-- Listener Observation active
       |
       +-- inventoryService.reserve()
       |
       +-- kafkaTemplate.send()
       |
       v
    Listener Observation closes

Trace context được truyền thuận lợi qua những method đồng bộ trên cùng thread.

Với async:

    Consumer thread
       |
       +-- executor.submit(task)
       |
       v
    Listener returns

    Worker thread
       |
       +-- task sends another Kafka event

Nếu không chuyển context, worker thread có thể tạo trace mới. Quan trọng hơn, nếu listener trả về trước khi task hoàn tất, **container có thể commit offset quá sớm**. Context propagation giải quyết việc nối trace, nhưng **không giải quyết độ bền nghiệp vụ**.

Ở Spring Framework 6.1+ có ContextPropagatingTaskDecorator dành cho executor phù hợp; ví dụ:

~~~java
@Bean
ThreadPoolTaskExecutor observedTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setTaskDecorator(
        new ContextPropagatingTaskDecorator()
    );

    executor.initialize();
    return executor;
}
~~~

Cần dependency và import của Spring Core/Task Executor phù hợp version. Đây là một cơ chế truyền context, không phải authorization cho việc acknowledge sớm. Khi offload Kafka record, phải có completion/ack handling, bounded queue và fencing khi rebalance.

## 20. Liên kết log với trace qua MDC

Trên những cấu hình Micrometer Tracing/Spring Boot phù hợp, tracing integration có thể bổ sung traceId và spanId vào MDC của thread đang xử lý. Khi log pattern hoặc JSON layout hỗ trợ, các log của producer/consumer có thể tra cứu cùng trace.

Ví dụ log dạng cấu trúc:

~~~text
timestamp=2026-11-15T10:00:00Z
service=inventory-worker
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=00f067aa0ba902b7
topic=orders.created
partition=2
offset=178
eventId=evt-100
message="Reservation processed"
~~~

Không bảo đảm mọi logging layout tự hiển thị MDC khi chỉ thêm tracing dependency. Cần kiểm tra cấu hình logback/log4j, correlation pattern và context propagation trên thread thực thi.

Nếu log do worker thread tạo ra mà không truyền context, traceId có thể rỗng. Khi xử lý debug, kiểm tra nơi Observation scope mở/đóng và thread chuyển đổi, thay vì tự sao chép một traceId cũ vào MDC rồi quên xóa nó. MDC bị rò rỉ giữa các task có thể làm log của hai khách hàng khác nhau mang sai traceId.

## 21. Dùng trace ID làm tiêu chí tìm lỗi như thế nào?

Một quy trình điều tra thực tế:

1. Từ HTTP response hoặc application log, lấy traceId nếu đã ghi nhận hợp lệ.
2. Mở tracing backend, tìm trace chứa HTTP server span.
3. Kiểm tra producer span ứng với topic được gửi.
4. Xác định consumer span liên quan tới record đó.
5. So sánh khoảng thời gian giữa producer và consumer.
6. Xem các span database/HTTP bên trong listener.
7. Nếu không có consumer span, kiểm tra sampling, propagation, exporter và listener observation.
8. Dùng eventId để đối chiếu record và logs ngay cả khi trace không đầy đủ.
9. Kiểm tra consumer lag và retry/DLT nếu độ trễ chủ yếu nằm trong Kafka.
10. Phân biệt producer send/transaction completion với listener processing completion.

Trace giúp thấy các bước ứng dụng đã instrument. Nếu không có broker-level telemetry hoặc event enqueue timestamp, khoảng cách giữa producer span và consumer span chỉ là **ước lượng** thời gian chờ hàng đợi, không phải một metric chính xác về Kafka broker latency.

## 22. Topic-to-listener latency khác processing latency

Nên phân biệt ba thước đo:

**Produce/send latency:** thời gian producer gửi và được broker xác nhận theo API/instrumentation đang dùng.

**Queue/transport wait:** khoảng cách từ khi record sẵn sàng trên Kafka đến khi một consumer bắt đầu xử lý. Khoảng này chịu ảnh hưởng consumer lag, partition ordering, pause, retries và scheduling.

**Listener processing latency:** thời gian business code xử lý record.

Ví dụ:

    Producer ACK at T0
    Consumer listener starts T0 + 25 s
    Listener finishes T0 + 25.040 s

Ở đây listener chỉ mất 40 ms, nhưng toàn bộ đường đi có độ trễ khoảng 25 giây. Tối ưu business method từ 40 ms xuống 20 ms không giúp nhiều nếu bottleneck là backlog.

Một trace có thể hiển thị producer/consumer spans nhưng **không luôn có một span kéo dài qua thời gian lưu record trong Kafka**. Để giám sát queue age, nên dùng timestamp trong record cùng metadata phù hợp và hệ thống metrics, không tạo một span nhân tạo kéo dài nhiều giờ.

## 23. Kiểm soát timestamp khi đo queue age

Kafka record có timestamp; timestamp có thể là CreateTime hoặc LogAppendTime tùy cấu hình broker/topic. Timestamp này không phải lúc producer tracing span kết thúc.

Một phép đo gần đúng:

    QueueAge = ConsumerStartTime - RecordTimestamp

Ví dụ listener đọc ConsumerRecord:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(ConsumerRecord<String, OrderEvent> record) {
    long ageMillis =
            System.currentTimeMillis() - record.timestamp();

    // Metric độ tuổi; không dùng eventId làm metric tag.
    queueAgeRecorder.record(
        record.topic(),
        Math.max(ageMillis, 0L)
    );

    orderService.process(record.value());
}
~~~

queueAgeRecorder là thành phần đo metric do ứng dụng tự định nghĩa. Giá trị có thể không hoàn toàn chính xác do clock skew, timestamp policy, delay producer/broker và replay record cũ. Không coi giá trị này là “broker processing time”.

Đối với message được phát lại sau nhiều ngày, queueAge có thể rất lớn dù consumer hiện xử lý nhanh. Cần phân biệt event age gốc, replay age và delay của từng retry topic.

## 24. Retrying một record ảnh hưởng trace như thế nào?

Một record có thể được listener xử lý nhiều lần:

    orders.created offset 90
        |
        +-- attempt 1 -> database timeout
        |
        +-- attempt 2 -> database timeout
        |
        +-- attempt 3 -> success

Nếu mỗi attempt được instrument, có thể có nhiều consumer/listener observations tương ứng những lần xử lý. Cấu trúc trace phụ thuộc framework, error handler, sampling và cách context được sử dụng.

Không nên suy ra rằng ba listener attempts phải có **cùng span ID**. Mỗi thao tác xử lý là một lần thực thi khác nhau, nên các spans hợp lý sẽ có identity riêng, dù có thể liên quan cùng record/tracing context.

Để quan sát retry đáng tin cậy, nên ghi nhận:

- Event ID ổn định.
- Topic, partition, offset nguồn.
- Delivery attempt hoặc retry stage khi API hỗ trợ.
- Exception class.
- Delay/backoff và lần recovery.
- Trace/span IDs của lần xử lý đã instrument.
- Offset commit hoặc DLT outcome.

Trace không thay thế retry counter. Sampling có thể loại bỏ một số attempts, nên không đếm số lần xử lý thực tế chỉ từ số spans nhìn thấy.

## 25. Retry topic và trace propagation

Với non-blocking retry, record có thể đi qua retry topics:

    orders.created
         |
         v
    orders.created-retry-1000
         |
         v
    orders.created-retry-5000
         |
         v
    orders.created-dlt

Các producer/recoverer tham gia chuyển record sang retry topic hoặc DLT có thể giữ hoặc tái tạo headers. Tracing chỉ liên tục nếu các đường publish/consume có instrumentation hoặc preserve context theo contract đang dùng.

Trong Spring Kafka, @RetryableTopic và infrastructure retry/DLT có thể tự tạo các listener containers và producer components. Bật observation trên một factory/template tự tạo **không mặc nhiên bảo đảm** mọi internal retry publisher cũng được instrument giống nhau.

Cần kiểm tra phiên bản Spring Kafka và thực tế record headers tại từng chặng. Nếu retry topic producer không inject tracing context mới nhưng giữ traceparent cũ, downstream có thể vẫn liên kết về upstream cũ; tuy nhiên không có nghĩa retry publish span đã được ghi nhận.

Thiết kế tracing cần phản ánh đường đi thực tế thay vì ép tất cả retries vào một span kéo dài qua nhiều khoảng backoff.

## 26. Dead-letter topic và khả năng điều tra

Khi xử lý không thành công sau retry, record thường được chuyển sang DLT với thông tin nguồn và exception.

Ví dụ:

    Input:
      topic=orders.created
      partition=2
      offset=90
      eventId=evt-100
      tracing headers=...

    DLT:
      topic=orders.created.DLT
      eventId=evt-100
      original topic/partition/offset
      exception metadata
      tracing headers tùy recovery path

DLT metadata và tracing context phục vụ hai nhiệm vụ:

- **DLT original headers:** định vị record lỗi và nguyên nhân.
- **Tracing headers:** giúp tìm spans/logs liên quan trong trace backend.

Không nên xóa tất cả headers khi republish lỗi vì có thể làm mất trace context lẫn eventId. Ngược lại, không giữ vô hạn mọi exception stacktrace hoặc baggage nhạy cảm ở nhiều tầng DLT.

Nếu dùng DeadLetterPublishingRecoverer, cần kiểm tra serializer/template, header propagation và chính sách strip exception headers của framework. Trace có thể giúp điều tra nhưng chính DLT record và eventId vẫn là bằng chứng dữ liệu bền vững.

## 27. Re-drive DLT: tiếp tục trace cũ hay bắt đầu trace mới?

Một sự kiện được phát lại sau nhiều giờ hoặc nhiều ngày không nhất thiết nên tiếp tục cùng trace ID như lần thất bại đầu tiên.

Ví dụ:

    Ngày 1:
      Trace A: producer -> listener -> error -> DLT

    Ngày 3:
      Operator sửa schema
      Re-drive DLT record
      Trace B: re-drive job -> listener -> success

Về mặt điều tra, thường hữu ích khi trace B là một hoạt động mới, có thể liên kết với trace A thông qua:

- Event ID.
- Replay ID.
- Correlation ID.
- DLT original topic/partition/offset.
- Span links nếu tracing API/runtime hỗ trợ.
- Audit record hoặc log theo eventId.

Nếu re-drive copy nguyên tracing headers của DLT, consumer có thể trích xuất parent từ trace cũ. Điều này không phải lúc nào cũng sai, nhưng có thể tạo một trace sống rất lâu và khó diễn giải. Hãy chọn chính sách có chủ đích: giữ lịch sử qua business correlation hoặc trace links, hay tiếp tục parent context khi recovery diễn ra ngắn.

**Không sửa traceparent bằng cách thay một phần trace ID thủ công.** Nếu muốn bắt đầu trace mới hoặc tạo span link, dùng tracing API và propagator của framework để giữ đúng semantic conventions.

## 28. Fan-out: một record được nhiều consumer group đọc

Kafka cho phép nhiều consumer groups xử lý cùng một record:

    Topic: orders.created
          |
          +--> Group inventory-service
          |
          +--> Group fraud-service
          |
          +--> Group notification-service

Ba nhóm có thể đọc cùng tracing headers và mỗi nhóm tạo consumer span riêng. Chúng đều liên quan đến record gốc nhưng chạy ở những thời điểm và môi trường khác nhau.

Điều này có nghĩa:

- Cùng một producer event có thể dẫn tới nhiều consumer spans.
- Không xem một consumer span duy nhất là bằng chứng mọi group đã xử lý.
- Mỗi group có committed offset và retry policy riêng.
- Một group có thể thất bại/DLT trong khi nhóm khác thành công.
- Sampling ở từng service có thể khác, làm trace hiển thị không đầy đủ.

Nếu cần xác nhận mọi consumer group đã hoàn tất nghiệp vụ, phải có workflow tracking hoặc application-level acknowledgment, không suy luận chỉ từ trace topology.

## 29. Fan-in: nhiều record tạo một output

Một service có thể chờ ba sự kiện trước khi tạo một output:

    payment.approved (trace A) ----+
                                  |
    stock.reserved (trace B) ------+--> order.completed (trace ?)
                                  |
    shipment.ready (trace C) ------+

Không có một parent span duy nhất mô tả hoàn toàn ba nguồn. Nếu lấy context cuối cùng và đặt làm parent, trace viewer có thể gây hiểu nhầm rằng output chỉ phụ thuộc vào nguồn đó.

Các lựa chọn:

1. Tạo một trace mới cho thao tác aggregation, sử dụng business correlation IDs.
2. Nếu tracer hỗ trợ, thêm **span links** tới contexts của những input đã tham gia.
3. Ghi event IDs của các input trong audit có cấu trúc.
4. Không nhồi toàn bộ danh sách trace contexts vào một Kafka header tùy ý không có giới hạn.

Trong các luồng batch/aggregate, span links và workflow audit thường diễn đạt đúng hơn một cây parent-child đơn giản.

## 30. Batch listener có những giới hạn riêng

Record listener có ngữ cảnh từng ConsumerRecord rõ ràng. Batch listener nhận nhiều record có thể chứa **nhiều tracing contexts khác nhau**.

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "batchOrdersFactory"
)
public void consume(List<ConsumerRecord<String, OrderEvent>> records) {
    for (ConsumerRecord<String, OrderEvent> record : records) {
        orderService.process(record.value());
    }
}
~~~

Nếu batch có 200 records từ 200 HTTP requests, không thể tùy tiện chọn tracing context của record đầu làm parent cho toàn batch rồi tuyên bố tất cả 200 thuộc cùng trace.

Các phiên bản Spring Kafka khác nhau có mức hỗ trợ Observation trên batch listener khác nhau; cần kiểm tra rõ chức năng và giới hạn của bản đang chạy. Nếu yêu cầu per-record trace continuity cao, record listener thường có mô hình tracing đơn giản hơn.

Nếu vẫn cần batch throughput:

- Giữ event ID của từng record.
- Đo batch processing duration riêng.
- Không giả định một consumer span tự liên kết với tất cả trace contexts.
- Dùng span links hoặc per-record instrumentation phù hợp khi được hỗ trợ.
- Tránh tạo hàng nghìn span/record trên một thread mà không đánh giá performance.

## 31. Transactions và dấu hiệu “send thành công”

Trong Kafka transaction, một producer có thể gửi output rồi transaction bị abort:

    Listener bắt đầu Kafka transaction
       |
       v
    KafkaTemplate.send()
       |
       v
    Producer nhận ACK
       |
       v
    Business exception
       |
       v
    abortTransaction()
       |
       v
    Output không visible với read_committed consumer

Producer span có thể cho thấy lệnh send đã hoàn tất, nhưng điều đó **không đủ để kết luận Kafka transaction đã commit**.

Để điều tra EOS cần theo dõi thêm:

- Producer transaction begin/commit/abort.
- Transaction duration và errors.
- Input consumer offsets committed.
- Output visibility qua read_committed.
- DLT/recovery transaction outcome nếu có.

Tương tự, một consumer span kết thúc không bảo đảm side effect DB đã được commit nếu listener triển khai async work và trả về trước completion. Distributed tracing mô tả đường chạy code đã instrument, không thay thế bằng chứng giao dịch bền vững.

## 32. Trace propagation và lỗi deserialization

Lỗi deserialize có thể xảy ra **trước khi @KafkaListener nhận được object**. Khi dùng ErrorHandlingDeserializer, Spring Kafka có thể đưa thông tin lỗi vào headers để container/error handler xử lý.

~~~yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderEvent
        spring.json.trusted.packages: com.example.events
~~~

Trong lỗi deserialize:

- Tracing headers của record gốc vẫn có thể tồn tại ở ConsumerRecord nếu không bị xóa bởi một bước trung gian.
- Business listener có thể không được gọi.
- Một recoverer có thể gửi raw bytes sang DLT.
- Listener observation và spans cụ thể phụ thuộc đường error handling của version/framework.

Nếu trace thiếu listener business span trong khi DLT có record lỗi, cần xem exception xảy ra trước listener hay không. Không xem thiếu listener span là dấu hiệu record chưa từng được consumer poll.

## 33. Header size, dữ liệu nhạy cảm và mức tải

Tracing headers thường nhỏ so với payload nhưng không miễn phí. Khi record đi qua retry/DLT nhiều lần hoặc ứng dụng thêm baggage quá nhiều, header size có thể tăng.

Tác động:

- Record lớn hơn, tăng network và storage.
- Producer/broker có thể từ chối record vượt giới hạn kích thước.
- Headers có thể được đọc bởi mọi consumer có quyền trên topic.
- Tracing baggage có thể bị đưa vào log/telemetry.
- Kích thước và cardinality tăng nếu tạo custom header không có quy tắc.

Các nguyên tắc:

1. Chỉ truyền context cần cho tracing.
2. Không tự serialize cả observation/span object vào Kafka header.
3. Không lưu token/secrets/PII trong baggage.
4. Không nhân bản traceparent ở mỗi retry bằng cơ chế append vô hạn.
5. Giữ eventId/correlationId ở hợp đồng nghiệp vụ riêng.
6. Kiểm soát ACL và retention cho DLT chứa exception context.
7. Quan sát header bytes khi nghi ngờ record tăng kích thước.

Với Kafka headers, có thể tồn tại nhiều header cùng tên. Khi debug, kiểm tra cả danh sách headers(name) thay vì chỉ lastHeader() nếu nghi ngờ producer/recoverer đã nối lặp.

## 34. Xem tracing headers trong ConsumerRecord

Để debug ở môi trường test, có thể kiểm tra những header propagation thực tế mà consumer nhận:

~~~java
@KafkaListener(topics = "orders.debug")
public void inspect(ConsumerRecord<String, byte[]> record) {

    for (Header header : record.headers()) {
        String name = header.key();

        if ("traceparent".equals(name)) {
            String value = new String(
                header.value(),
                StandardCharsets.US_ASCII
            );

            log.debug("traceparent present: {}", value);
        }
    }
}
~~~

Imports:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
~~~

Đây là đoạn **debug minh họa**; trong production không nhất thiết log nguyên traceparent trên mọi record. Có thể chỉ ghi metric context present/missing và trace ID qua tracing/MDC phù hợp.

Nếu ứng dụng dùng B3 propagation, việc chỉ tìm header traceparent sẽ không cho kết luận đầy đủ. Kiểm tra propagation formats và header names thực sự được tracer cấu hình.

## 35. Vì sao trace producer và consumer không nối được?

Một bảng chẩn đoán:

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Có producer span nhưng consumer mở trace mới | Consumer không extract context | Listener observation, propagator, headers |
| Có consumer span nhưng không có producer span | Producer chưa bật observation hoặc span không export | Template configuration, sampling, exporter |
| Có headers nhưng không có trace trên backend | Sampling hoặc export/collector lỗi | Trace sampling, OTLP metrics/logs |
| Chỉ mất context khi qua service trung gian | Service dùng producer khác hoặc tạo record không giữ context | KafkaTemplate thực tế, header injection |
| Chỉ mất context với async worker | Thread context không được propagate | Executor/decorator/callback |
| Retry topic không nối span | Internal retry publisher/consumer có instrumentation khác | Retry infrastructure, actual headers |
| DLT có eventId nhưng không có trace | DLT được republish bằng path chưa instrument | Recoverer KafkaTemplate, header policy |
| Có một trace khổng lồ qua nhiều ngày | Re-drive giữ remote parent context cũ | Replay policy, span links/correlation |
| Log không có traceId dù trace backend có span | MDC/log pattern hoặc thread context thiếu | Logging config và scope |
| Trace nối sai giữa hai request | Thread-local/MDC scope bị rò rỉ | Executor reuse, manual MDC changes |

Nên xác minh từng hop: **record có header? → consumer có trích xuất? → span có được tạo? → exporter có gửi? → backend có lưu?**. Điều tra theo trình tự này nhanh hơn việc chỉ thay sampling hoặc restart Kafka.

## 36. Quan sát trace ở môi trường nhiều instance

Ví dụ consumer group có ba pod và nhiều partition:

    orders.created P0/P1 -> pod A
                   P2/P3 -> pod B
                   P4/P5 -> pod C

Cùng một trace có thể đi qua pod A rồi pod C nếu các bước ở những topic khác nhau. Để hiểu route:

- Gắn tên service ổn định (service.name) cho từng ứng dụng.
- Thu thập instance/pod identity vào resource attributes phù hợp.
- Ghi topic/destination và operation ở messaging spans theo instrumentation.
- Dùng eventId để tra log cụ thể theo partition/offset.
- Không dùng pod IP làm business correlation ID.
- Khi consumer rebalance, một record có thể được xử lý lại ở pod khác.

Nếu chỉ xuất trace từ một pod mà không xuất từ các pod còn lại, trace viewer sẽ hiển thị khoảng trống dù pipeline hoạt động đúng.

Với high-cardinality resource identity như pod UID, cần tuân thủ chính sách exporter/backend để tránh tạo chi phí telemetry bất thường.

## 37. Sampling trong retry và high-volume topic

Một consumer 50.000 record/giây không nhất thiết nên xuất mọi producer/consumer span. Cần chọn sampling policy theo nhu cầu.

Một số hướng:

**Head-based sampling:** quyết định lấy mẫu từ đầu trace; có thể dễ truyền quyết định qua headers, nhưng những lỗi chỉ xuất hiện về sau có thể không được sample nếu trace đã bị bỏ.

**Tail-based sampling:** collector/backend lựa chọn sau khi nhìn thấy spans, hữu ích nếu muốn ưu tiên error/latency; cần tài nguyên và thời gian giữ trace trong collector.

**Sampling theo service/workload:** ưu tiên một số topic nhạy cảm hoặc luồng lỗi; phải đảm bảo không làm sai propagation contract.

Không dùng eventId như metric label hoặc gửi toàn bộ payload vào span để bù việc sampling thấp. Với DLT/incident, log và audit có cấu trúc thường đáng tin cậy hơn vì được giữ theo chính sách riêng.

Nếu backend không hỗ trợ tail sampling hoặc links tốt, không giả định có thể truy xuất mọi attempt trong một trace liên tục.

## 38. Một hợp đồng tracing tối thiểu giữa các team

Trong tổ chức có nhiều producer/consumer khác nhau, nên thỏa thuận:

- Propagation format: W3C traceparent/tracestate hoặc format đã chọn.
- Cơ chế instrumentation ở producer và consumer.
- Bật observation trong những factory/template được dùng thực tế.
- Tên service và quy tắc đặt tên span/observation.
- Sampling policy production.
- Event ID và correlation ID thuộc contract nghiệp vụ, không phụ thuộc tracer.
- Chính sách tracing khi retry, DLT và re-drive.
- Chính sách không truyền secrets/PII qua baggage/headers.
- Cách theo dõi exporter và missing spans.
- Runbook kiểm tra trace qua Kafka topic/partition/offset.

Nếu có producer bằng Java/Spring và consumer bằng Go/Python/Node.js, phải kiểm tra instrumentation ở cả hai bên. Việc cùng sử dụng OpenTelemetry không tự bảo đảm propagation giống nhau nếu một service dùng W3C còn service khác dùng format khác.

## 39. Integration test: HTTP → Kafka → listener

Một integration test có ý nghĩa cần xác nhận **propagation**, không chỉ có span.

Kịch bản:

1. Chạy ứng dụng với tracing/test ObservationRegistry phù hợp.
2. Tạo một inbound HTTP request có trace context kiểm soát được.
3. Service gọi observed KafkaTemplate để publish event có eventId cố định.
4. Consumer test đọc record gốc và kiểm tra có tracing header phù hợp.
5. Listener container được bật observation, xử lý event.
6. Thu thập spans bằng in-memory exporter/test tracer phù hợp.
7. Xác nhận có producer và consumer observations/spans.
8. Xác nhận trace relationship phù hợp instrumentation version.
9. Xác nhận topic, eventId, source offset và business side effect như kỳ vọng.
10. Kiểm tra xử lý vẫn thành công khi tracing exporter không sẵn sàng.

Trong test, có thể cấu hình sampling 100% và một collector/in-memory span exporter để tránh mất spans ngẫu nhiên. Không dùng sampling 100% trong test để suy ra production sẽ có đủ mọi trace.

Nếu chỉ test rằng ConsumerRecord có traceparent, ta mới chứng minh producer đã inject header; chưa chứng minh consumer đã extract và liên kết span.

## 40. Integration test: consumer gửi tiếp sang topic thứ hai

Test nhiều hop:

    HTTP trace -> Topic A -> Listener A
                       |
                       v
                     Topic B -> Listener B

Các bước:

1. Gửi event vào Topic A bằng observed producer.
2. Listener A xử lý trong active observation.
3. Listener A gọi observed KafkaTemplate để gửi Topic B.
4. Đọc Topic B, kiểm tra propagation headers mới.
5. Listener B extract context và xử lý.
6. Thu thập spans từ cả hai listener và hai producer operations.
7. Đối chiếu trace context, parent/link relationship theo version.
8. Kiểm tra kết quả vẫn đúng khi listener A retry một lần.

Nếu hop thứ hai bị tách trace, kiểm tra template được inject trong Listener A và việc gửi Topic B có thực sự chạy dưới scope của listener observation không. Nếu gửi bất đồng bộ, kiểm tra context propagation qua executor.

## 41. Integration test: DLT/replay

Một bài test recovery cần xác minh:

1. Record đầu vào có eventId, correlationId và tracing header hợp lệ.
2. Listener xử lý lỗi và error handler retry theo giới hạn.
3. Record được recover sang DLT.
4. DLT vẫn chứa eventId và metadata nguồn cần cho điều tra.
5. Tracing header được giữ/thay đổi theo **chính sách đã chọn**.
6. Re-drive record sau khi sửa dữ liệu.
7. Nếu bắt đầu trace mới, log/audit vẫn liên kết với eventId cũ.
8. Nếu dùng span links, xác nhận links được export đúng.
9. Nếu sampling khác nhau, business outcome/offset vẫn không bị ảnh hưởng.
10. Nếu DLT producer hoặc exporter lỗi, hệ thống không coi hai lỗi đó là cùng bản chất.

Tracing không nên làm record DLT không thể publish vì một exporter tracing tạm thời down. Sự cố telemetry và sự cố giao nhận Kafka cần được cô lập tối đa.

## 42. Test mất context khi async

Một test cụ thể:

1. Listener nhận record với traceparent.
2. Listener submit một task sang executor.
3. Task gọi HTTP client hoặc observed KafkaTemplate.
4. Thu spans và log trong worker thread.
5. Với executor không propagate context, quan sát nguy cơ xuất hiện root span mới.
6. Bật context propagation/decorator thích hợp.
7. Xác nhận trace relationship được giữ đúng.
8. Đồng thời kiểm tra listener không acknowledge record trước khi task hoàn tất bền vững.

Bước 8 rất quan trọng. Một test tracing có thể pass nhưng hệ thống vẫn mất dữ liệu nếu Kafka offset đã commit trong khi task còn ở queue RAM.

## 43. Dashboard kết hợp trace với metrics

Một dashboard giám sát Kafka reliability nên liên kết:

| Nhóm metric | Vai trò |
|---|---|
| Producer send rate/latency/errors | Record được gửi với tốc độ và lỗi ra sao |
| Consumer records consumed rate | Tốc độ đọc topic |
| Listener processing duration | Thời gian thực thi nghiệp vụ |
| Consumer lag / record age | Chờ bao lâu trước khi được xử lý |
| Retry/backoff/DLT count | Số lần xử lý lỗi và recovery |
| Commit latency / commit failures | Độ bền tiến độ offset |
| Observation spans/traces | Đường đi liên service |
| Exporter dropped spans | Có mất telemetry không |
| JVM/CPU/network | Tài nguyên gây chậm |
| Downstream DB/HTTP latency | Bottleneck sau listener |

Trace viewer hữu ích khi điều tra một event cụ thể; metric hữu ích để phát hiện xu hướng trên hàng triệu records. Không lấy số spans làm throughput metric trừ khi instrumentation/sampling được kiểm soát đúng, vì sampling khiến số spans khác số messages.

Một dashboard có thể cung cấp link từ structured log chứa traceId sang tracing backend và từ trace sang logs lọc eventId. Đó là trải nghiệm hiệu quả hơn việc cố đưa mọi dữ liệu nghiệp vụ vào span attributes.

## 44. Runbook: mất liên kết trace qua topic

Khi một luồng producer → Kafka → listener bỗng tách trace:

1. **Xác định hop lỗi:** trace đứt giữa service nào và topic nào?
2. **Xác nhận record:** producer có phát đúng topic/key/eventId không?
3. **Đọc tracing headers:** record có traceparent/B3 theo format đã chọn không?
4. **Kiểm tra producer config:** template thực tế có observation enabled không?
5. **Kiểm tra consumer config:** listener factory thực tế có observation enabled không?
6. **Kiểm tra tracer bridge:** các service có Micrometer Tracing và tracer compatible không?
7. **Kiểm tra propagator:** W3C/B3 settings có khớp nhau không?
8. **Kiểm tra sampling/export:** span có bị drop hoặc exporter lỗi không?
9. **Kiểm tra async hop:** context có bị mất khi chuyển thread không?
10. **Kiểm tra retry/DLT:** recoverer có tạo/copy headers theo policy không?
11. **Kiểm tra version:** Spring Kafka, Boot, Micrometer và OpenTelemetry có tương thích không?
12. **Kiểm tra security:** proxy hoặc custom serializer có xóa/đổi headers không?
13. **Chạy test nhỏ:** gửi một event có trace context xác định.
14. **Theo dõi sau sửa:** tỷ lệ records có context và span linkage, không chỉ số trace xuất hiện.

Không tự sửa dữ liệu Kafka production chỉ vì trace bị đứt. Trước tiên xác minh đường giao nhận nghiệp vụ vẫn an toàn rồi xử lý instrumentation riêng.

## 45. Những lỗi thiết kế thường gặp

| Sai sót | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ bật Observation ở producer | Consumer có thể mở trace mới | Bật ở listener factory |
| Chỉ bật ở consumer | Không có context đầu vào | Bật ở KafkaTemplate gửi |
| Không có tracer bridge/exporter | Có observation nhưng không thấy span ở backend | Kiểm tra tracing pipeline |
| Producer W3C, consumer B3-only | Không extract được context | Đồng bộ propagator |
| Tự ghi trace ID làm header text | Thiếu span ID, flags và semantic context | Dùng propagator |
| Dùng traceId làm dedup key | Replay/trace mới khiến duplicate không được phát hiện | Dùng eventId |
| Dùng baggage chứa PII/token | Rò rỉ dữ liệu, header bloat | Giới hạn baggage an toàn |
| Gửi trong async thread không propagate context | Trace tách ở hop sau | Context propagation |
| Acknowledge trước async completion | Có thể mất công việc sau crash | Ack theo completion bền vững |
| Copy mọi tracing header qua DLT mãi mãi | Trace khó diễn giải, header lớn | Chính sách retry/replay rõ |
| Dùng một parent cho 200 records batch | Trace sai quan hệ | Span links/per-record policy |
| Đếm spans thành số messages | Sai vì sampling | Dùng Kafka/client metrics |
| Xem Kafka send span thành transaction commit | Kết luận EOS sai | Theo dõi commit/abort riêng |
| Nhầm listener latency với queue wait | Tối ưu sai bottleneck | Đo event age/lag riêng |
| Tắt Kafka xử lý khi exporter down | Mất khả dụng do telemetry | Tách observability khỏi processing |
| Gắn eventId làm metric tag | Cardinality tăng | Đưa vào log/trace theo policy |
| Coi trace là audit vĩnh viễn | Trace sample/expire | Lưu audit/event ID độc lập |

## 46. Checklist triển khai production

- Đã xác định propagation format thống nhất giữa producer/consumer chưa?
- KafkaTemplate được dùng thực tế có bật observation?
- Listener container factory được dùng thực tế có bật observation?
- Có ObservationRegistry, Micrometer Tracing bridge và exporter hoạt động?
- Sampling có phù hợp với throughput và chi phí lưu trữ?
- Topic/record có giữ tracing headers qua các bước trung gian?
- Có thể xử lý record không có tracing context mà không mất dữ liệu?
- Log có traceId/spanId trong scope phù hợp?
- Async executor có propagate context khi cần?
- Offset acknowledgement có chờ side effect hoàn tất bền vững?
- Event ID và correlation ID có tách khỏi trace ID?
- Retry/DLT/re-drive có chính sách giữ hoặc tạo context mới rõ ràng?
- Có giới hạn baggage và ngăn dữ liệu nhạy cảm vào headers?
- Có hỗ trợ tracing hợp lý cho batch/fan-in nếu ứng dụng dùng những mô hình đó?
- Có đo queue age và consumer lag độc lập với trace?
- Có test multi-hop, retry, DLT, async và exporter outage?
- Có runbook tìm trace đứt giữa topic và listener?
- Có monitor exporter drop rate/collector health để không nhầm mất trace với mất message?

## 47. Kết luận

**Liên kết trace giữa topic và listener** là quá trình truyền ngữ cảnh truy vết qua Kafka headers và khôi phục nó trong Spring Kafka listener observation. KafkaTemplate được bật observation giúp tạo/inject producer context; listener container được bật observation giúp extract context và quan sát lần xử lý. Micrometer Tracing và một tracer/exporter phù hợp biến các observations đó thành distributed traces có thể tìm trong backend.

Tracing giúp theo dõi đường đi qua nhiều topic và service, nhưng không thay thế consumer lag, offset commit, Kafka transactions, retry, DLT hay idempotency. Khi triển khai production, cần xử lý đúng sampling, async context propagation, retry/replay semantics, header security và quan hệ giữa event ID, correlation ID và trace ID.

Một hệ thống Kafka đáng tin cậy không chỉ biết **record đã đi đến đâu**, mà còn biết **vì sao nó chậm, lần nào nó thất bại, đâu là bottleneck và việc recovery có hoàn tất an toàn hay chưa**. Distributed tracing đóng góp một phần quan trọng cho câu trả lời đó khi được kết hợp với metrics, logs và dữ liệu nghiệp vụ bền vững.
