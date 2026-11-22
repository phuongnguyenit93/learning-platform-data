# observationEnabled

Trong Spring Kafka, một Kafka record có thể đi qua nhiều service, nhiều topic và các lần retry trước khi đạt trạng thái nghiệp vụ cuối cùng. Khi có sự cố, chỉ xem log của một `@KafkaListener` thường chưa đủ để trả lời: record xuất phát từ đâu, đã được publish bởi service nào, khâu nào chậm, và lỗi xảy ra trong thao tác Kafka hay trong database/HTTP downstream. **Micrometer Observation** cung cấp một mô hình instrumentation chung cho **metrics và distributed tracing**, giúp kết nối các giai đoạn của luồng xử lý.

Thuộc tính **`observationEnabled`** của Spring Kafka bật Micrometer Observation cho **listener container** và/hoặc **`KafkaTemplate`**. Khi đã được cấu hình đúng cùng `ObservationRegistry`, metrics registry và tracing bridge phù hợp, ứng dụng có thể thu thập thời gian xử lý listener, thời gian gửi Kafka, trace/span context và các tag giúp điều tra sự cố.

Cần hiểu ranh giới: bật `observationEnabled` **không tự tạo Kafka transactions, không bảo đảm exactly-once, không sửa lỗi serialization, không tự đẩy record vào DLT và không tự biến mọi HTTP/database call thành một span hoàn chỉnh**. Nó chỉ kích hoạt đường instrumentation tương ứng. Để thu được trace xuyên service, cần có tracing implementation, exporter, sampling, header propagation và instrumentation ở các thành phần liên quan.

## 1. Observation khác log, metric và trace ở đâu?

Một pipeline đơn giản:

~~~text
HTTP request
    |
    v
Order API
    |
    +-- KafkaTemplate.send("orders.created")
             |
             v
         Kafka topic
             |
             v
        @KafkaListener
             |
             +-- Database write
             +-- KafkaTemplate.send("billing.requested")
                            |
                            v
                      Billing consumer
~~~

Ba loại tín hiệu giải quyết ba câu hỏi khác nhau:

| Tín hiệu | Câu hỏi chính | Ví dụ |
|---|---|---|
| Log | Điều gì đã xảy ra tại một thời điểm? | `OrderCreated processing failed` |
| Metric | Tần suất, độ trễ, tỷ lệ lỗi có xu hướng như thế nào? | Listener p95 = 180 ms |
| Trace/span | Các thao tác liên quan trong một luồng diễn ra theo quan hệ nào? | HTTP → Kafka send → Kafka listener → DB |

Micrometer Observation cung cấp **Observation API**, một abstraction cho phép các handlers cùng phản ứng khi observation bắt đầu, kết thúc hoặc bị lỗi. Có handler chuyên tạo Timer metrics, handler chuyên tạo tracing spans, hoặc handler tùy biến.

Một ứng dụng có thể bật Observation mà chỉ nhận được **metrics** nếu chưa cấu hình tracing bridge/exporter. Ngược lại, một trace backend có thể không thấy span do sampling, network hoặc collector configuration dù Observation đã hoạt động.

## 2. Tác dụng chính của observationEnabled

Spring Kafka hỗ trợ Micrometer Observation cho `KafkaTemplate` và listener containers từ **Spring Kafka 3.0**.

Hai nơi cấu hình là độc lập:

~~~java
// Listener container:
factory.getContainerProperties().setObservationEnabled(true);

// Kafka producer template:
kafkaTemplate.setObservationEnabled(true);
~~~

Ý nghĩa:

- **Listener container observation:** tạo observation bao quanh quá trình xử lý Kafka listener ở phạm vi framework hỗ trợ; cho phép tạo metrics và tracing span cho consumer-side work.
- **KafkaTemplate observation:** tạo observation khi gửi record qua template; cho phép metrics/span cho producer-side send.
- **Khi bật cả hai:** trace context có thể được đưa vào record headers và tiếp tục ở consumer tiếp theo nếu các tracing handlers/propagators được cấu hình tương thích.

Bật một phía **không tự bật phía còn lại**. Nếu producer dùng `KafkaTemplate` nhưng chưa enable Observation, có thể không tạo span send và không chèn tracing headers theo đường instrumentation đó. Nếu consumer chưa enable Observation, nó có thể đọc value bình thường nhưng không sinh consumer-side span theo cơ chế này.

## 3. Sơ đồ Observation trong consume–process–produce

~~~mermaid
sequenceDiagram
    participant A as Service A
    participant K1 as Kafka topic orders
    participant B as Service B
    participant K2 as Kafka topic billing
    participant C as Service C
    A->>A: KafkaTemplate Observation / producer span
    A->>K1: Produce record + trace context headers
    K1-->>B: ConsumerRecord + headers
    B->>B: Listener Observation / consumer span
    B->>B: Business processing
    B->>B: KafkaTemplate Observation / producer span
    B->>K2: Produce next record + context headers
    K2-->>C: ConsumerRecord + headers
    C->>C: Listener Observation / consumer span
~~~

Nếu service dùng cùng trace propagator và một trace backend, người vận hành có thể liên kết các spans trong cùng một trace. Cách spans biểu diễn parent-child hay messaging links phụ thuộc implementation và semantic conventions; không nên ép mọi hệ thống thành một sơ đồ cây duy nhất.

Dòng dữ liệu Kafka vẫn có đặc điểm **bất đồng bộ**. Trace cho thấy quan hệ giữa các thao tác, nhưng không chứng minh producer đã commit mọi DB change, offset đã được xác nhận hoặc business event đã hoàn tất.

## 4. Mặc định của observationEnabled

Trong các phiên bản Spring Kafka gần đây, `ContainerProperties.observationEnabled` mặc định là **`false`**. Do đó chỉ có Spring Boot Actuator và Micrometer trên classpath thường **chưa đủ** để kết luận listener container đang dùng Observation.

~~~java
ContainerProperties properties = factory.getContainerProperties();

properties.setObservationEnabled(true);
~~~

Đối với `KafkaTemplate`:

~~~java
template.setObservationEnabled(true);
~~~

Bảng phân biệt:

| Thiết lập | Trạng thái/mục đích |
|---|---|
| `observationEnabled=false` | Không bật Micrometer Observation ở component đó |
| `observationEnabled=true` | Bật đường Observation cho component đó |
| `micrometerEnabled=true` | Bật legacy Micrometer Timers khi được framework dùng và có registry |
| `ObservationRegistry` | Nơi đăng ký và điều phối Observation handlers |
| Micrometer Tracing bridge | Chuyển Observation thành spans theo implementation |
| Trace exporter | Gửi spans tới collector/backend |
| MeterRegistry/Prometheus | Thu thập và xuất metrics |

**Bật Observation sẽ thay thế legacy Micrometer Timer instrumentation** cho đường xử lý được Observation hỗ trợ, vì Observation tự quản lý Timer tương ứng. Điều này quan trọng khi migrate dashboards dựa trên tags cũ.

Với batch listener, hành vi Observation thay đổi theo phiên bản và cần xem riêng; không suy luận từ record listener.

## 5. Cấu hình Spring Boot cơ bản

Ví dụ với Spring Boot 3.x/Spring Kafka 3.x, có thể thêm các dependencies:

~~~kotlin
dependencies {
    implementation("org.springframework.kafka:spring-kafka")
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    // Metrics qua Prometheus:
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")

    // Tracing với OpenTelemetry:
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
}
~~~

Spring Boot phiên bản mới có thể cung cấp **tracing starters** với dependency coordinates và configuration properties khác. Ví dụ trên minh họa kiến trúc dependency cho Boot 3.x; khi triển khai cần dùng bộ versions do BOM của Boot quản lý, không ghép tùy tiện Micrometer, OpenTelemetry và Spring Kafka versions.

Một phần cấu hình metrics/tracing cho Boot 3.x:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-processing
  tracing:
    sampling:
      probability: 0.20
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

`sampling.probability: 0.20` là cấu hình minh họa lấy mẫu một phần traces; không có nghĩa 20% Kafka records được xử lý, mà ảnh hưởng việc spans được ghi/xuất theo tracer configuration. Metrics thường được ghi nhận độc lập với trace sampling.

Đối với Spring Boot 4.x, tracing dependencies và namespace properties đã phát triển; hãy dùng tài liệu tương ứng với version được triển khai thay vì copy configuration Boot 3.x máy móc.

## 6. Bật Observation cho listener container bằng Java configuration

Một listener factory được cấu hình cụ thể:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaObservationConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    observedOrdersListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setObservationEnabled(true);

        return factory;
    }
}
~~~

Listener sử dụng đúng factory đó:

~~~java
@Component
public class OrdersConsumer {

    private final OrderProjectionService projection;

    public OrdersConsumer(OrderProjectionService projection) {
        this.projection = projection;
    }

    @KafkaListener(
        id = "orders-observed-consumer",
        topics = "orders.created",
        groupId = "order-projection",
        containerFactory = "observedOrdersListenerFactory")
    public void onOrder(OrderCreated event) {
        projection.apply(event);
    }
}
~~~

Nếu không chỉ định `containerFactory`, Spring Kafka có thể chọn factory mặc định có bean name `kafkaListenerContainerFactory`. Khi có nhiều listener factories, không nên bật Observation trong một factory rồi kỳ vọng tất cả listeners đều được instrument.

Container properties được dùng như template cho containers được tạo. Cấu hình trước khi listener container start giúp tránh tình huống một số records đầu tiên không được quan sát.

## 7. Bật Observation cho KafkaTemplate

Một KafkaTemplate được tạo và cấu hình tường minh:

~~~java
@Bean
KafkaTemplate<String, BillingRequested> observedBillingTemplate(
        ProducerFactory<String, BillingRequested> producerFactory) {

    var template =
        new KafkaTemplate<String, BillingRequested>(producerFactory);

    template.setObservationEnabled(true);
    return template;
}
~~~

Một service gửi record:

~~~java
@Service
public class BillingPublisher {

    private final KafkaTemplate<String, BillingRequested> template;

    public BillingPublisher(
            KafkaTemplate<String, BillingRequested> observedBillingTemplate) {
        this.template = observedBillingTemplate;
    }

    public void publish(BillingRequested event) {
        template.send(
            "billing.requested",
            event.orderId(),
            event
        );
    }
}
~~~

Khi chạy trong ứng dụng Spring Boot đã auto-configure KafkaTemplate, cần kiểm tra có template nào đang được inject. Việc tạo thêm một template có thể khiến qualifier/primary bean trở nên mơ hồ. Một lựa chọn khác là tùy biến template đã tồn tại khi wiring bean, bảo đảm thực hiện **trước khi nó được dùng để gửi records**.

Observation chỉ áp dụng cho send đi qua KafkaTemplate đã bật cấu hình. Nếu một module khác sử dụng KafkaProducer raw hoặc một KafkaTemplate khác không instrument, không thể dựa vào settings ở template này để quan sát các send đó.

## 8. ObservationRegistry là trung tâm điều phối

Micrometer Observation sử dụng `ObservationRegistry` để đăng ký handlers và điều phối vòng đời một observation. Với Spring Boot Actuator được cấu hình phù hợp, registry thường được auto-configure.

Vòng đời ý tưởng:

~~~text
Observation started
        |
        +-- Meter observation handler bắt đầu timing
        |
        +-- Tracing handler tạo span/context (nếu được cấu hình)
        |
        +-- Business operation
        |
        +-- Ghi error nếu có
        |
Observation stopped
        |
        +-- Timer sample được ghi nhận
        +-- Span được kết thúc và có thể export theo sampling
~~~

Nếu ObservationRegistry chỉ có no-op behavior hoặc không có handlers thích hợp, `observationEnabled=true` có thể không tạo ra dữ liệu hữu ích trong backend.

Có thể dùng Observation API cho bước nghiệp vụ riêng:

~~~java
@Service
public class OrderProjectionService {

    private final ObservationRegistry observationRegistry;
    private final OrderRepository repository;

    public OrderProjectionService(
            ObservationRegistry observationRegistry,
            OrderRepository repository) {

        this.observationRegistry = observationRegistry;
        this.repository = repository;
    }

    public void apply(OrderCreated event) {
        Observation
            .createNotStarted("business.order.persist", observationRegistry)
            .lowCardinalityKeyValue("operation", "upsert")
            .observe(() -> repository.apply(event));
    }
}
~~~

Instrumentation này đo riêng phần persistence. Nếu đang chạy bên trong một listener observation scope trên cùng thread, trace handler phù hợp có thể liên kết business span với listener span. Không nhồi `eventId` hoặc `orderId` vào **low-cardinality** metric tag.

## 9. Observation không đồng nghĩa exporter tracing đã hoạt động

Ba mức hoạt động thường bị nhầm:

| Mức | Cấu hình | Quan sát được |
|---|---|---|
| Observation chỉ có registry/metrics handler | Bật Observation, có MeterRegistry | Timer metrics |
| Observation có tracing bridge | Có Micrometer Tracing implementation và handler | Có thể tạo spans/trace context |
| Observation có exporter/backend | Cấu hình OTLP/Zipkin collector, network và sampling | Spans xuất hiện trong hệ thống truy vết |

Vì vậy, một người thấy `spring.kafka.listener` trong Prometheus nhưng không có spans ở Jaeger/Tempo không nên kết luận ngay `observationEnabled` không hoạt động. Có thể metrics đang hoạt động còn tracing exporter chưa được cài hoặc cấu hình sai.

Ngược lại, một trace sampling thấp có thể làm nhiều operations không xuất hiện trong tracing UI, dù application thực sự xử lý mọi records như bình thường.

## 10. Context propagation qua Kafka headers

Một trace xuyên Kafka cần liên kết ngữ cảnh giữa producer và consumer. Với Kafka messaging, thông tin context propagation thường được chèn vào **record headers**, không phải payload business JSON.

~~~text
Producer:
  Current trace context
       |
       v
  KafkaTemplate observation
       |
       +-- inject propagation headers
       |
       v
  ProducerRecord(topic, key, value, headers)

Kafka broker:
  Giữ record và headers

Consumer:
  ConsumerRecord với headers
       |
       v
  Listener observation
       |
       +-- extract trace context
       |
       v
  Span/context phục vụ listener processing
~~~

Tùy tracing implementation và propagator được chọn, headers có thể sử dụng W3C Trace Context, ví dụ `traceparent`, hoặc chuẩn propagation khác. Không hardcode tên header khi framework đã hỗ trợ inject/extract qua tracing context.

Kafka broker **không tự tạo distributed trace** và không hiểu nghiệp vụ của trace headers. Nó lưu và chuyển headers cùng record.

## 11. Sơ đồ trace context xuyên hai service

Ví dụ:

~~~text
Service A
  HTTP request trace=abc
    |
    +-- KafkaTemplate sends OrderCreated
          -> trace context trong record headers

orders.created topic
    |
    v
Service B
  @KafkaListener receives OrderCreated
    |
    +-- Listener observation nối trace context
    |
    +-- DB call (nếu được instrument)
    |
    +-- KafkaTemplate sends BillingRequested
          -> propagation headers cho bước kế tiếp

billing.requested topic
    |
    v
Service C
  @KafkaListener receives BillingRequested
~~~

Với instrumentation và propagation phù hợp, trace có thể hiển thị quá trình giao tiếp bất đồng bộ giữa các services. Tuy nhiên:

- Producer có thể publish một event nhiều lần do retry/recovery.
- Một record có thể được nhiều consumer groups xử lý độc lập.
- Listener có thể rollback Kafka transaction sau khi span đã được tạo.
- Span “send attempted” không tự chứng minh output đã được commit trong Kafka transaction.
- Trace không phải nguồn chân lý cho kế toán, idempotency hoặc consumer offset audit.

Trace dùng để **giải thích hành vi**; tính đúng đắn của state vẫn cần database transaction, Kafka delivery semantics và application invariants.

## 12. Tại sao cần bật cả producer và consumer observation?

Giả sử service A bật `KafkaTemplate.observationEnabled`, còn service B chưa bật listener observation:

~~~text
Service A:
  Kafka send span + headers   -> OK

Service B:
  Consumer vẫn deserialize và xử lý records
  nhưng không có listener observation span theo đường này
~~~

Ngược lại, nếu service B bật listener observation nhưng producer không gắn trace headers, B vẫn có thể sinh một observation/span cục bộ. Tuy nhiên, context upstream có thể không được nối tự động vào cùng trace.

Vì thế, với một pipeline cần distributed tracing, hãy:

1. Bật observation cho `KafkaTemplate` ở các producer gửi record.
2. Bật observation cho listener containers ở các consumers.
3. Cấu hình cùng hệ tracing/propagation conventions phù hợp giữa services.
4. Đảm bảo Kafka headers được chuyển tiếp nguyên vẹn qua broker/proxy.
5. Kiểm tra một record thực đi từ producer tới consumer và xem spans trong backend.
6. Với retry/DLT, xác định mong muốn giữ hay tạo trace context mới.
7. Kiểm tra sampling và exporter ở mọi service liên quan.

Không cần bật tracing cho các service không tham gia luồng; nhưng phải hiểu rằng một chặng không instrument có thể tạo đoạn đứt trong trace.

## 13. Default observation names

Spring Kafka định nghĩa các observation names:

| Thành phần | Observation name | Metric/Span chủ yếu |
|---|---|---|
| Listener | `spring.kafka.listener` | Timer + listener span |
| KafkaTemplate | `spring.kafka.template` | Timer + template/send span |

Ngoài Timer, Micrometer Observation documentation còn mô tả các long task timers như:

~~~text
spring.kafka.listener.active
spring.kafka.template.active
~~~

Một `Timer` truyền thống chủ yếu ghi nhận duration khi invocation kết thúc. Long task timer giúp quan sát tác vụ đang diễn ra tùy registry và instrumentation. Không nên xem long task timer là consumer lag hoặc số Kafka transactions mở; đây là metric thuộc Observation lifecycle.

Khi export qua Prometheus, metric names có thể đổi dấu chấm thành dấu gạch dưới và thêm unit suffix. Cần xem endpoint thực tế chứ không tự giả định chính xác tên mọi time series.

## 14. Low-cardinality và high-cardinality tags

Micrometer phân biệt thông tin có thể dùng cho metrics với thông tin chỉ nên lưu trong traces/logs.

**Low-cardinality key values** có tập giá trị tương đối nhỏ và ổn định. Chúng phù hợp cho Prometheus dimensions.

**High-cardinality key values** có rất nhiều giá trị, ví dụ offset, request ID hoặc business event ID; nếu biến chúng thành metric labels, số time series sẽ phình to.

| Tag/attribute | Loại khuyến nghị | Vì sao |
|---|---|---|
| `spring.kafka.listener.id` | Low cardinality | Tập listener IDs hữu hạn |
| `messaging.system=kafka` | Low cardinality | Giá trị ổn định |
| `messaging.source.name` | Low cardinality nếu topics có quản lý | Tập topics hữu hạn |
| Consumer group | Low cardinality nếu được kiểm soát | Số groups thường giới hạn |
| `event.kind=order_paid` | Low cardinality nếu whitelist | Số event types hữu hạn |
| `messaging.kafka.message.offset` | High cardinality | Thay đổi với mỗi record |
| Event ID/UUID | High cardinality | Gần như unique mỗi event |
| Kafka key/order ID | High cardinality | Số lượng tăng theo nghiệp vụ |
| Trace ID/span ID | High cardinality | Unique theo trace/span |
| Raw exception message | Không nên làm metric label | Dữ liệu tự do, có thể nhạy cảm |

Không đưa Kafka payload, access token, email, payment data hoặc customer ID vào low-cardinality tags. Dữ liệu tracing cũng cần tuân thủ phân quyền và data retention, vì span attributes có thể chứa thông tin nhạy cảm nếu ứng dụng tự thêm.

## 15. Default tags và metadata của listener observation

Theo Micrometer Observation documentation của Spring Kafka, listener observation có một số low-cardinality keys:

| Low-cardinality key | Ý nghĩa |
|---|---|
| `spring.kafka.listener.id` | Listener ID/container bean name |
| `messaging.system` | Hệ messaging, thường Kafka |
| `messaging.operation` | Loại thao tác messaging |
| `messaging.source.name` | Topic nguồn |
| `messaging.source.kind` | Kiểu nguồn |
| `messaging.kafka.consumer.group` | Consumer group |

Các span attributes có thể bổ sung:

- `messaging.kafka.client_id`.
- `messaging.kafka.message.offset`.
- `messaging.kafka.source.partition`.
- `messaging.consumer.id`.

Danh sách và tên có thể thay đổi khi Spring Kafka/Micrometer cập nhật semantic conventions. Với dashboard production, hãy kiểm tra tag keys thực sự trong `/actuator/prometheus` và traces backend tương ứng với **version đang chạy**, thay vì sao chép trực tiếp từ một bản tài liệu khác.

Đừng nhầm low-cardinality observation tags với legacy timer tags `name`, `result` và `exception`; hai cơ chế có conventions khác nhau.

## 16. Legacy Micrometer Timer và Observation không giống nhau

Trước Observation, Spring Kafka listener tạo Micrometer Timers trực tiếp khi có Micrometer và MeterRegistry. Timer `spring.kafka.listener` thường có:

~~~text
name=<container name>
result=success|failure
exception=none|ListenerExecutionFailedException
~~~

Khi bật `observationEnabled=true`, Spring Kafka chuyển instrumentation sang Micrometer Observation cho đường được hỗ trợ. Mặc dù Timer có thể vẫn mang tên `spring.kafka.listener`, **các tags có thể khác**.

| Yếu tố | Legacy Micrometer Timers | Micrometer Observation |
|---|---|---|
| Bật | `micrometerEnabled` | `observationEnabled` |
| Instrument | Timer trực tiếp | Observation, tạo Timer và có thể tạo span |
| Listener identifier | `name` | `spring.kafka.listener.id` theo convention |
| Failure dimension | `result` và `exception` | Có `error`/convention khác tùy version |
| Tùy biến tags | `micrometerTags` / `micrometerTagsProvider` | `KafkaListenerObservationConvention` |
| Trace spans | Không tự sinh chỉ từ Timer | Có thể sinh spans khi tracing handlers sẵn sàng |
| Batch behavior | Đo batch invocation theo legacy | Phụ thuộc version và batch observation policy |

Nếu dashboards dùng:

~~~promql
spring_kafka_listener_seconds_count{result="failure"}
~~~

sau khi bật Observation mà tag `result` không còn được xuất theo cách cũ, panel có thể rỗng. Đây là **migration dashboard/tag convention**, không nhất thiết là metrics bị tắt.

Kế hoạch nâng cấp phải bao gồm đổi PromQL, Grafana panel, alert rule và any business metrics aggregate phụ thuộc tag names.

## 17. Custom listener ObservationConvention

Để thêm tags phục vụ phân tích theo pipeline, sử dụng `KafkaListenerObservationConvention` thay vì `micrometerTagsProvider` của Timer legacy.

Một ví dụ ở Spring Kafka 3.x/4.x hỗ trợ API liên quan:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.kafka.support.micrometer.KafkaListenerObservation;
import org.springframework.kafka.support.micrometer.KafkaRecordReceiverContext;

public class OrderListenerObservationConvention
        extends KafkaListenerObservation.DefaultKafkaListenerObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            KafkaRecordReceiverContext context) {

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("pipeline", "order-projection"));
    }
}
~~~

Áp dụng cho listener factory:

~~~java
factory.getContainerProperties()
       .setObservationConvention(new OrderListenerObservationConvention());
factory.getContainerProperties().setObservationEnabled(true);
~~~

Ví dụ trên sử dụng một tag cố định `pipeline` với cardinality nhỏ. Việc subclass default convention có lợi vì giữ những tags chuẩn mà Spring Kafka cung cấp, rồi bổ sung field nghiệp vụ cần thiết.

Tùy phiên bản, `getLowCardinalityKeyValues` có annotation nullability khác nhau. Nên dựa vào API của dependency đã pin khi biên dịch.

## 18. Dynamic tags từ ConsumerRecord theo cách an toàn

Từ Spring Kafka 3.0.6, observation contexts có reference tới Kafka record, cho phép tạo tags dựa trên key/header/value.

Tuy nhiên, **không** đưa nguyên mọi Kafka header hoặc business ID vào metric tags. Một cách an toàn là whitelist event types:

~~~java
public class OrderListenerObservationConvention
        extends KafkaListenerObservation.DefaultKafkaListenerObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            KafkaRecordReceiverContext context) {

        var record = context.getRecord();

        var header = record.headers().lastHeader("event-type");

        String kind = "other";
        if (header != null && header.value() != null) {
            String raw = new String(
                header.value(),
                StandardCharsets.UTF_8
            );

            kind = switch (raw) {
                case "OrderCreated" -> "order_created";
                case "OrderPaid" -> "order_paid";
                case "OrderCancelled" -> "order_cancelled";
                default -> "other";
            };
        }

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("event.kind", kind));
    }
}
~~~

Code dùng Java switch expression và `StandardCharsets.UTF_8`; cần import các lớp tương ứng. Nếu application dùng Java thấp hơn phiên bản hỗ trợ switch expression, thay bằng `if/else` hoặc enum mapping.

Tại sao whitelist cần thiết:

- Một producer lỗi có thể gửi hàng triệu giá trị event type lạ.
- Nếu dùng raw event type làm tag, mỗi giá trị mới tạo một time series.
- Tập tags nhỏ giúp dashboard và alert ổn định.
- High-cardinality fields vẫn có thể xuất hiện trong log/span attributes nếu phù hợp chính sách bảo mật.

Nếu nhiều topics có contract khác nhau, hãy dùng conventions riêng theo factory hoặc phân nhánh theo source topic, tránh áp một classifier tùy tiện lên mọi consumer.

## 19. Custom KafkaTemplateObservationConvention

Đường producer có interface riêng `KafkaTemplateObservationConvention` và default implementation tương ứng.

Một ví dụ:

~~~java
public class BillingTemplateObservationConvention
        extends KafkaTemplateObservation.DefaultKafkaTemplateObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            KafkaRecordSenderContext context) {

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("pipeline", "billing"));
    }
}
~~~

Gắn vào KafkaTemplate đã bật Observation:

~~~java
template.setObservationConvention(
    new BillingTemplateObservationConvention()
);
template.setObservationEnabled(true);
~~~

Những imports tương ứng nằm trong package:

~~~java
org.springframework.kafka.support.micrometer.KafkaTemplateObservation
org.springframework.kafka.support.micrometer.KafkaRecordSenderContext
~~~

Đối với producer, observation context chứa `ProducerRecord`. Nếu muốn thêm thông tin message type, hãy whitelist headers/metadata tương tự consumer. Không đưa raw key, UUID, customer ID hoặc payment reference vào low-cardinality keys.

## 20. Batch listener là ngoại lệ cần kiểm tra theo phiên bản

**Không được giả định `observationEnabled=true` có cùng semantics trên record listener và batch listener.**

Tài liệu Spring Kafka 3.1 nêu batch listener chưa được hỗ trợ bởi Observation theo cách của record listener, nên legacy Micrometer Timers được dùng. Trong Spring Kafka 4.1.x, tài liệu mô tả khi batch listener bật `observationEnabled`, **mặc định không tạo observations cho từng record**; có thể bật `recordObservationsInBatch=true` để tạo per-record observations, nhưng observation đó **không tự propagate vào batch listener method**.

Trong tài liệu nhánh 4.2 đang phát triển, behavior mới có batch-level observation mặc định khi `recordObservationsInBatch=false`. Vì vậy phải xác nhận **release cụ thể** đang triển khai.

Bảng định hướng:

| Phiên bản/luồng | Cần lưu ý |
|---|---|
| Spring Kafka 3.0–3.1 | Batch Observation có giới hạn; xem fallback Timer |
| Spring Kafka 4.1.x | Hỗ trợ `recordObservationsInBatch`, mặc định không tạo per-record observations |
| Spring Kafka 4.2 development | Có mô tả batch-level observation mặc định; cần kiểm tra bản stable trước áp dụng |
| Record listener | Observation bao quanh từng listener invocation theo cơ chế framework |

Không viết một tracing policy dựa trên `recordObservationsInBatch` mà chưa kiểm tra khả năng tương thích và ngữ cảnh span bên trong batch method.

## 21. Cấu hình recordObservationsInBatch

Với phiên bản Spring Kafka hỗ trợ:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
observedBatchFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);

    factory.getContainerProperties().setObservationEnabled(true);
    factory.getContainerProperties()
           .setRecordObservationsInBatch(true);

    return factory;
}
~~~

Khi bật per-record batch observations, framework có thể tạo observation cho từng record của batch, nhưng trong một số phiên bản các observation **không được đặt làm current scope** khi gọi một batch listener method chung. Vì vậy lời gọi HTTP/DB bên trong batch method không tự trở thành child của một trong nhiều per-record spans.

Nếu cần trace từng record của batch với business steps, application phải thiết kế manual observation scopes hoặc chuyển sang record listener nếu semantics phù hợp. Không tự tạo một current span ngẫu nhiên cho toàn batch rồi gán tất cả records vào nó nếu cần attribution chính xác.

## 22. Observation và Kafka client metrics là hai nhóm khác nhau

Listener observation chủ yếu đo **invocation của ứng dụng**, còn Kafka client metrics đo hành vi KafkaConsumer/KafkaProducer.

| Loại | Ví dụ | Câu hỏi |
|---|---|---|
| Listener Observation Timer | `spring.kafka.listener` | Listener xử lý chậm không? |
| KafkaTemplate Observation Timer | `spring.kafka.template` | Gửi record qua template chậm không? |
| Kafka client fetch metrics | Fetch latency/rate | Consumer lấy dữ liệu từ broker có chậm? |
| Kafka coordinator metrics | Commit/rebalance/heartbeat | Group có ổn định? |
| Consumer lag | Committed offset so với log-end | Backlog bao nhiêu? |
| Retry/DLT metrics | Retry count, DLT volume | Có record không xử lý được? |
| Business event metrics | Orders applied, payments confirmed | Nghiệp vụ thực sự hoàn tất? |

Một listener mất 10 ms xử lý nhưng consumer lag cao có thể do thiếu concurrency, hot partition, pause hoặc producer rate quá lớn. Observation Timer không tự đo hết những trường hợp đó.

Spring Kafka cung cấp `MicrometerConsumerListener` và `MicrometerProducerListener` để bind Kafka client metrics vào Micrometer MeterRegistry. Chúng bổ sung chứ không thay thế `observationEnabled`.

## 23. Khi nào trace bị đứt giữa Kafka producer và consumer?

Một trace đi từ Service A sang B có thể bị mất liên kết nếu:

1. Producer `KafkaTemplate` chưa bật observation.
2. Consumer listener container chưa bật observation.
3. Không có tracing bridge hoặc tracing handlers trong `ObservationRegistry`.
4. Producer và consumer dùng propagation format không tương thích.
5. Một custom Kafka interceptor/forwarder vô tình xóa trace headers.
6. Record được republish bằng producer không preserve/carry context.
7. Async thread boundary làm mất observation scope.
8. Sampling hoặc exporter khiến một số spans không xuất hiện ở backend.
9. Một component dùng Kafka client trực tiếp, không đi qua instrumented template/container.
10. Hệ thống retry/DLT tạo record mới nhưng tracing policy chưa được xác định.

Trước khi thêm custom headers bằng tay, hãy xem Spring Kafka và Micrometer Tracing đã inject/extract ngữ cảnh đúng chưa. Việc tự chèn `traceparent` sai định dạng có thể làm hỏng propagation hoặc tạo parent context không hợp lệ.

## 24. Async thread boundaries và Observation scope

Micrometer Observation scope thường được gắn với **thread hiện tại**. Nếu listener đưa công việc sang executor:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "observedOrdersListenerFactory")
public void onOrder(OrderCreated event) {

    CompletableFuture.runAsync(() -> {
        orderProjectionService.apply(event);
    });

    // Listener trả về trước khi task thật hoàn tất.
}
~~~

Thao tác bên trong `runAsync` có thể mất current observation/tracing context nếu executor không được instrument hoặc không có context propagation phù hợp. Đồng thời, Kafka container có thể coi listener đã thành công dù DB task chưa hoàn tất — đây là lỗi semantics nghiêm trọng hơn việc thiếu span.

Nếu cần async:

- Bảo đảm listener không báo success trước khi side effect bắt buộc hoàn tất.
- Dùng executor được instrument bằng Micrometer Context Propagation hoặc cơ chế tracing của framework phiên bản tương ứng.
- Cân nhắc dùng `ContextSnapshot`/`ContextExecutorService` hoặc task decorator khi được hỗ trợ.
- Không truyền raw Kafka `Consumer` qua thread khác.
- Xác định rõ span nào sở hữu nghiệp vụ, timeout, failure và retries.

Observation có thể giúp nhìn thấy khoảng thời gian thiếu instrumentation, nhưng không tự chuyển transaction context và không giải quyết thread safety.

## 25. Trace propagation với HTTP clients

Trong listener có thể gọi một downstream HTTP API:

~~~text
Kafka listener observation
      |
      v
OrderValidationService
      |
      v
RestClient / WebClient / RestTemplate
      |
      v
Validation API
~~~

Để HTTP call tiếp tục trace context, client cũng cần instrumentation và propagation phù hợp. Với Spring Boot, nên sử dụng **auto-configured builders** hoặc các cơ chế được framework hỗ trợ; nếu tạo HTTP client trực tiếp mà bỏ qua configuration, trace headers có thể không được chèn.

Không suy luận rằng `observationEnabled=true` trên Kafka listener sẽ tự instrument mọi JDBC driver, HTTP client hoặc third-party SDK. Mỗi integration có khả năng và cấu hình Observation/Tracing riêng.

## 26. Retry, DLT và trace lineage

Một record có thể qua chuỗi:

~~~text
orders.created
    |
    +-- listener failure
          |
          v
orders-retry-1000
    |
    +-- failure
          |
          v
orders-retry-2000
    |
    +-- terminal
          |
          v
orders.DLT
~~~

Mỗi lần consumer nhận record có thể tạo một observation/span mới. Không nên gộp mọi attempt vào cùng một span kéo dài nhiều phút hoặc nhiều ngày; asynchronous boundaries và retry delay thường được biểu diễn bằng spans riêng liên kết qua trace/context hoặc business correlation ID theo chính sách.

Những điều cần xác định:

- Retry producer có bật observation không?
- Retry topic consumer có bật observation không?
- Khi forward record, trace headers nào được giữ/chuyển tiếp?
- DLT publish có được instrument và có success/failure không?
- Một replay thủ công sau vài ngày nên tiếp tục trace cũ hay bắt đầu trace mới và giữ `eventId`/`replayId` để correlation?
- DLT event metadata có thông tin original topic/partition/offset không?

**Trace ID không phải idempotency key.** Một business event có thể được xử lý dưới nhiều traces khác nhau qua replay; ngược lại một trace có thể chứa nhiều business events. Dùng `eventId` hoặc operation ID bền vững để deduplicate nghiệp vụ.

## 27. Kafka transactions và observationEnabled

Kafka transaction có thể đưa Kafka output records và input offsets vào cùng transaction khi container được cấu hình phù hợp. `observationEnabled` không thay đổi transaction boundary.

Ví dụ:

~~~text
Consumer record
     |
     v
Listener observation starts
     |
     v
Kafka transaction begins/participates theo container configuration
     |
     v
Listener sends output via observed KafkaTemplate
     |
     v
Listener returns success
     |
     v
Container attempts commit transaction + offsets
~~~

Quan sát caveats:

- Listener span success có thể phản ánh việc listener method trả về, chưa chứng minh **toàn bộ transaction đã commit**.
- KafkaTemplate send span success không nhất thiết chứng minh record đang visible đối với downstream `read_committed` nếu transaction chưa commit.
- Nếu transaction rollback, record có thể được xử lý lại và sinh thêm spans.
- Database side effects không tự rollback cùng Kafka transaction.
- Nếu output được gửi qua template không transactional, Observation vẫn có thể tạo span nhưng semantics delivery khác.

Muốn theo dõi commit/rollback, cần bổ sung Kafka transaction metrics, logs, error events và business state indicators; không dựa vào `spring.kafka.listener` Timer một mình.

## 28. KafkaAdmin clusterId và remoteServiceName

Spring Kafka observation contexts có thể đặt `remoteServiceName` theo Kafka cluster ID. Để lấy ID, framework sử dụng `KafkaAdmin` và thao tác `describeCluster` khi cần.

Nếu KafkaAdmin không có quyền hoặc network chặn admin call, việc lấy cluster ID có thể thất bại hoặc gây chậm nếu ứng dụng liên tục thử lại. Tài liệu từ Spring Kafka 3.1 cho phép cấu hình **manual clusterId** trong các tình huống phù hợp; Spring Kafka 4.1.1 bổ sung cơ chế ghi nhớ lỗi và retry sau `clusterIdRetryInterval` (mặc định 5 phút) để giảm overhead khi describeCluster thất bại.

Trong vận hành:

1. Kiểm tra service có quyền thực hiện `describeCluster` không.
2. Xem KafkaAdmin operation timeout và network path.
3. Nếu không thể đọc cluster ID, xem khả năng cung cấp giá trị ổn định theo version.
4. Tránh đặt cluster ID giả không tương ứng với cluster thực tế.
5. Nếu observation khiến send/receive latency tăng sau deploy, kiểm tra cluster ID lookup failures trong logs.

Không nhầm `clusterId` với bootstrap server hostname hay consumer group ID: chúng đại diện cho các khái niệm khác nhau.

## 29. Sampling và chi phí distributed tracing

Nếu ứng dụng xử lý 20.000 Kafka messages/giây và tạo spans cho cả producer lẫn consumer ở mỗi chặng, 100% tracing có thể tạo chi phí lớn ở CPU, memory, exporter network và trace backend.

Sampling là công cụ kiểm soát chi phí:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
~~~

Ví dụ này lấy mẫu 10% theo tracer/sampler policy của Spring Boot phù hợp; không có nghĩa mọi trace có đúng một phần mười spans ngẫu nhiên trong cùng một trace.

Cân nhắc:

- Metrics nên tiếp tục đủ đại diện cho mọi invocations, không gắn chặt vào sampling của traces.
- Trace sampling thấp khiến một số request không thấy trong backend; không coi đó là record loss.
- Khi điều tra sự cố hiếm, có thể cần sampling policy nâng cao hoặc ghi log correlation.
- Không bật 100% tracing toàn bộ production vô thời hạn chỉ để tìm một lỗi nếu chi phí không chịu được.
- Không log raw payload/key dưới dạng span attribute để tránh PII và storage tăng.

Nếu cần điều tra một event cụ thể, event ID trong structured logs và trace ID có thể hỗ trợ correlation mà không phải biến event ID thành metric label.

## 30. Metrics xuất ra Prometheus

Observation tạo metrics qua observation handlers và `MeterRegistry` khi cấu hình đầy đủ. Ví dụ các tên metric có thể được export theo dạng:

~~~text
spring_kafka_listener_seconds_count
spring_kafka_listener_seconds_sum
spring_kafka_template_seconds_count
spring_kafka_template_seconds_sum
~~~

Tên/tag series thực tế phụ thuộc Spring Kafka, Micrometer, Prometheus registry version và Observation convention. Để xem metrics qua Actuator:

~~~text
GET /actuator/metrics
GET /actuator/metrics/spring.kafka.listener
GET /actuator/prometheus
~~~

Các endpoints chỉ hoạt động khi có Actuator, registry, exposure/security phù hợp.

Không hardcode PromQL filter bằng legacy `result`/`exception` khi đã chuyển sang Observation convention; hãy xem dữ liệu thực tế và dùng những keys hiện có như `spring.kafka.listener.id`, `messaging.source.name` và `error` nếu backend xuất ra.

## 31. Truy vấn latency từ Observation Timer

Ví dụ tính duration trung bình của listener trong 5 phút:

~~~promql
sum by (spring_kafka_listener_id) (
  rate(spring_kafka_listener_seconds_sum[5m])
)
/
clamp_min(
  sum by (spring_kafka_listener_id) (
    rate(spring_kafka_listener_seconds_count[5m])
  ),
  0.000000001
)
~~~

Lưu ý: Prometheus exporter có thể chuẩn hóa dấu chấm của tag key thành dấu gạch dưới. `spring_kafka_listener_id` ở đây chỉ là **tên label thường gặp sau normalization**, phải kiểm tra output thực tế.

Để có p95/p99, cần histogram buckets được bật:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, spring_kafka_listener_id) (
    rate(spring_kafka_listener_seconds_bucket[5m])
  )
)
~~~

Nếu histogram không được bật, `_bucket` có thể không xuất hiện; đừng tạo alert dựa vào một metric không tồn tại. Chọn histogram boundaries và retention theo SLO.

Observation Timer đo thời gian instrumentation của framework, **không tự đo thời gian record nằm trong broker**, retry delay hay toàn bộ thời gian từ producer publish đến business completion.

## 32. Consumer lag và tracing cần được kết hợp

Một pipeline có thể có listener spans rất ngắn nhưng consumer lag lớn:

~~~text
Producer ingress = 5.000 records/s
Consumer throughput = 3.000 records/s
Listener p95 = 20 ms

=> Lag tăng xấp xỉ 2.000 records/s dù mỗi invocation nhìn khá nhanh.
~~~

Nguyên nhân có thể là số partitions giới hạn concurrency, hot key, poll/fetch latency, downstream queue, pause hoặc consumer group rebalance. Observation không thay thế:

- Consumer group lag metrics.
- Kafka client fetch/poll metrics.
- `NonResponsiveConsumerEvent` và idle events.
- Retry topic backlog, DLT volume.
- Business success/failure counters.
- Database/HTTP dependency metrics.

Trace hữu ích để xem *một lần xử lý cụ thể chậm ở đâu*, trong khi metrics trả lời *bao nhiêu lần xử lý đang chậm và ảnh hưởng rộng tới đâu*.

## 33. Log correlation với traceId và spanId

Khi Micrometer Tracing được cấu hình với logging integration, MDC có thể chứa `traceId` và `spanId` để structured logs liên kết với spans. Ví dụ log:

~~~text
2026-11-15T10:00:00Z INFO traceId=4f5a... spanId=a7c2...
  listener=orders-observed-consumer
  eventId=evt-205
  result=ORDER_APPLIED
~~~

Trace ID giúp điều tra các thao tác trong một flow. Event ID giúp xác định business operation ngay cả khi retry sau nhiều giờ tạo trace mới.

Các lưu ý:

- Không đảm bảo MDC tự propagate sang mọi async executor thread.
- Không dựa vào trace ID để deduplicate DB writes.
- Không log token, PII hoặc raw message payload chỉ vì tracing được bật.
- Nếu tracing sampling bỏ span, log correlation behavior có thể khác tùy implementation; cần kiểm tra môi trường thực.
- Một event đi qua DLT replay có thể cần thêm `replayId` để phân biệt lần xử lý.

## 34. Kiểm chứng propagation bằng một luồng mẫu

Một kế hoạch kiểm chứng trong môi trường test:

1. Bật Observation cho KafkaTemplate ở Service A.
2. Bật Observation cho listener container ở Service B.
3. Cấu hình Micrometer Tracing bridge và exporter ở cả hai service.
4. Dùng chung propagation format và kiểm tra headers.
5. Gửi một record với event ID xác định từ A.
6. Xác nhận B nhận record và xử lý thành công.
7. Tìm spans send/receive trong trace backend.
8. Xem trace IDs, parent/links và topic metadata.
9. Kiểm tra listener exception tạo error telemetry theo convention.
10. Kiểm tra record retry/republish và trace context theo policy dự kiến.
11. Thử async processing để xác định context có được giữ không.
12. Kiểm tra metrics vẫn có samples dù tracing sampling được cấu hình thấp.

Đây là **kế hoạch kiểm chứng** để người học áp dụng; không phải kết quả kiểm thử trong bài viết này. Mỗi application cần xác định rõ thành phần nào chịu trách nhiệm propagation.

## 35. Runbook: Bật observationEnabled nhưng không có metrics

1. Kiểm tra container factory thực sự dùng `setObservationEnabled(true)`.
2. Kiểm tra KafkaTemplate nào đang gửi và nó đã bật Observation chưa.
3. Xác nhận `ObservationRegistry` hiện diện trong application context.
4. Xác nhận metrics handler và `MeterRegistry`/Prometheus registry được cấu hình.
5. Kiểm tra Actuator endpoint exposure và quyền truy cập.
6. Xác nhận listener thực sự có invocation; một topic trống có thể chưa có samples.
7. Kiểm tra MeterFilter có chặn hoặc rename meters không.
8. Tìm metric bằng tên `spring.kafka.listener`/`spring.kafka.template`, không chỉ legacy tags.
9. Xem container đang record/batch và chính sách batch observation của phiên bản.
10. Kiểm tra có nhiều registries/child containers/factories không.
11. Kiểm tra startup logs và dependency versions Micrometer/Kafka.
12. Sau sửa, kiểm tra time series cụ thể trước khi đổi alert rule.

Nếu metrics không xuất hiện, không nên tự tạo thêm Timer cùng tên ngay; có thể làm duplicated instrumentation khi lỗi config được khắc phục.

## 36. Runbook: Có metrics nhưng không có traces

1. Xác nhận Micrometer Tracing bridge được thêm vào dependencies.
2. Xác nhận tracing handler/implementation kết nối với ObservationRegistry.
3. Kiểm tra sampling probability và sampler policy.
4. Kiểm tra exporter, collector endpoint, TLS/auth và network.
5. Kiểm tra trace backend ingest/logs.
6. Kiểm tra producer/consumer đều bật Observation.
7. Xác nhận record có trace context headers đúng format.
8. Kiểm tra custom Kafka interceptors có xóa headers không.
9. Kiểm tra async thread context propagation.
10. Kiểm tra batch listener limitation theo Spring Kafka version.
11. Xem application logs có trace ID/span ID hay không.
12. Thử một record mẫu với sampling phù hợp trong môi trường test.

Không bật 100% tracing trên toàn production như phản ứng mặc định. Chọn một environment hoặc sampling window an toàn để khoanh vùng.

## 37. Runbook: Trace có span rời rạc hoặc parent sai

Tình huống: Service A có producer span, Service B có consumer span nhưng chúng không cùng trace.

Các hướng điều tra:

- Tracing propagator của A và B có cùng W3C/B3/format không?
- KafkaTemplate của A có observationEnabled và gửi record qua đúng template?
- B có listener observationEnabled và đúng factory?
- Record headers có bị custom forwarder/serializer/interceptor loại bỏ?
- B có tạo một root observation thủ công thay vì tiếp nhận extracted context?
- Retry/DLT có tạo producer record mới mà không chuyển headers?
- Async executor có đánh mất current observation scope?
- Có sampling/exporter khiến một phần spans không hiển thị?
- Có dùng hai collector/backend khác nhau trong cùng environment?

Sau khi tìm được nguyên nhân, xác định trace structure mong muốn: messaging chain không nhất thiết phải là một parent-child tree giống synchronous HTTP. Span links hoặc trace correlation có thể phù hợp hơn trong các workflow fan-out.

## 38. Runbook: Metrics/trace overhead tăng sau khi bật Observation

1. So sánh CPU, memory, GC, container processing duration trước/sau deploy.
2. Kiểm tra số spans/giây và exporter queue capacity.
3. Kiểm tra sampling strategy và số services được instrument.
4. Kiểm tra low-cardinality tag values có vô tình chứa event ID hoặc Kafka key không.
5. Kiểm tra histogram buckets và number of time series.
6. Kiểm tra tracing backend ingest throttling hoặc OTLP exporter retries.
7. Kiểm tra KafkaAdmin `describeCluster` failures, timeout và cluster ID lookup behavior.
8. Kiểm tra custom observation convention có parse JSON payload nặng trên mỗi record không.
9. Kiểm tra logging/alerting trong observation handlers có synchronous blocking I/O không.
10. Giảm chi phí bằng whitelist tags, sampling và exporter batching phù hợp.
11. Không hy sinh quan sát lỗi quan trọng chỉ để tối ưu một phần chi phí nhỏ.
12. Theo dõi throughput, consumer lag và error rates sau mọi thay đổi.

Observation phải hỗ trợ reliability, không được làm chính consumer trở thành bottleneck vì tag cardinality hoặc collector chậm.

## 39. Bảo mật, privacy và trace data

Kafka headers và span attributes có thể chứa nhiều thông tin về hệ thống. Tracing sẽ nhân bản một phần metadata sang backend lưu trữ khác Kafka nên cần kiểm soát:

- Chỉ dùng low-cardinality tags được cho phép.
- Tránh customer ID, email, token, payment data trong metric tags.
- Không gắn raw event payload vào span.
- Nếu cần event ID làm high-cardinality attribute, đánh giá retention và quyền truy cập.
- Bảo vệ `/actuator/prometheus` và tracing collector endpoints.
- Kiểm tra trace backend lưu dữ liệu bao lâu và ai có quyền xem.
- Không dùng `traceparent` như credential hoặc dấu xác thực.
- Không tự tin rằng mọi header từ upstream đều đáng tin; tracing context là metadata quan sát, không phải bằng chứng danh tính.

Một trace ID có thể giúp correlation nhưng không chứng minh user authorization. Security checks phải tiếp tục độc lập.

## 40. Checklist triển khai observationEnabled

- [ ] Đã kiểm tra version Spring Kafka hỗ trợ Micrometer Observation (từ 3.0).
- [ ] Đã bật `ContainerProperties.observationEnabled=true` trên đúng listener factory.
- [ ] Đã bật `KafkaTemplate.observationEnabled=true` ở các producer cần trace propagation.
- [ ] Có `ObservationRegistry` và metrics handlers hoạt động.
- [ ] Có MeterRegistry/Prometheus nếu cần metrics.
- [ ] Có Micrometer Tracing bridge và exporter nếu cần distributed spans.
- [ ] Hai phía producer/consumer dùng propagation format tương thích.
- [ ] Đã xác minh trace headers không bị xóa khi forward/retry/DLT.
- [ ] Đã phân biệt legacy Timer tags và Observation convention tags.
- [ ] Đã kiểm tra batch listener semantics theo version cụ thể.
- [ ] Có custom `KafkaListenerObservationConvention`/`KafkaTemplateObservationConvention` khi cần thêm tags.
- [ ] Low-cardinality tags được whitelist; không dùng event ID/offset làm metric labels.
- [ ] Có chiến lược sampling và ngân sách exporter/backend.
- [ ] Có giải pháp context propagation qua async threads nếu cần.
- [ ] Dashboard kết hợp listener timers với consumer lag, Kafka client metrics, retries và DLT.
- [ ] Không dùng spans làm bằng chứng Kafka transaction/DB commit thành công.
- [ ] Có runbook cho thiếu metrics, thiếu spans, context đứt và overhead tăng.
- [ ] Có chính sách bảo mật, retention và quyền xem trace data.

## 41. Nguồn tham khảo

- [Spring Kafka Reference — Monitoring & Micrometer Observation](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring Kafka Reference — Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring Kafka Reference — Micrometer Observation conventions](https://docs.spring.io/spring-kafka/reference/appendix/micrometer.html)
- [Spring Kafka API — DefaultKafkaListenerObservationConvention](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/micrometer/KafkaListenerObservation.DefaultKafkaListenerObservationConvention.html)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Micrometer Reference — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)

**Kết luận:** `observationEnabled` giúp Spring Kafka đưa listener và KafkaTemplate vào hệ thống Micrometer Observation để thu thập **metrics và tracing** theo một mô hình thống nhất. Hãy bật đúng cả đường producer và consumer, cấu hình ObservationRegistry cùng tracing exporter, và quản lý trace context propagation qua Kafka headers. Khi migrate từ legacy Micrometer Timers, phải kiểm tra metric tags và dashboard; khi dùng batch listener, cần theo sát khác biệt theo phiên bản. Với reliability, Observation là lớp **quan sát và chẩn đoán**, không thay thế offset management, retries, Kafka transactions, idempotency hay business-state validation.
