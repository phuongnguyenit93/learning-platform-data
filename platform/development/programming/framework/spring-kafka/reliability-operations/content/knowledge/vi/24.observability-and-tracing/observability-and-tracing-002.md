# ObservationConvention

Trong Spring Kafka, khả năng quan sát (observability) không dừng ở việc biết một Kafka consumer đang chạy hay một producer đã gọi send(). Đội vận hành cần liên kết một sự kiện đi qua nhiều service, đo thời gian xử lý, phân loại lỗi, xác định topic nào bị chậm, đồng thời không làm hệ thống metrics quá tải bởi hàng triệu giá trị tag khác nhau.

**ObservationConvention** của **Micrometer Observation** là cơ chế quy định cách đặt **tên observation**, **contextual name** và các **KeyValues (tags)** từ một Observation Context. Spring Kafka cung cấp hai chuyên biệt quan trọng:

- **KafkaListenerObservationConvention**: tùy biến observation của listener nhận Kafka records.
- **KafkaTemplateObservationConvention**: tùy biến observation của KafkaTemplate gửi records.

Hai interface này dựa trên Micrometer ObservationConvention và cho phép một ứng dụng thêm các thuộc tính nghiệp vụ có kiểm soát vào metrics/traces, ví dụ app.pipeline=orders-projection hoặc app.domain=payments. Chúng không làm thay đổi payload Kafka, không tự tạo retry, và không thay thế cơ chế tracing propagation.

Bài học thuộc chương **Observation và tracing** của **Spring Kafka Reliability Operations**, đi từ mô hình Observation tới cách viết convention, gắn vào container và KafkaTemplate, quản lý low/high cardinality, kiểm thử, migration theo version và runbook production.

## 1. Mục tiêu của ObservationConvention

Giả sử một order event đi qua chuỗi:

~~~text
checkout-api
    -> Kafka topic orders.created
    -> orders-projection consumer
    -> PostgreSQL orders_read_model
    -> Kafka topic orders.projected
    -> notification-service
~~~

Nếu chỉ có log rời rạc, khi một đơn hàng xử lý chậm, operator phải tìm thủ công từng service. Nếu chỉ có một timer mà không phân biệt listener hoặc domain, dashboard cũng khó biết thành phần nào đang tạo tail latency.

Một observation có thể cung cấp:

1. **Tên ổn định** của operation được đo, ví dụ spring.kafka.listener.
2. **Low-cardinality tags**, dùng để phân nhóm metrics có số giá trị hữu hạn.
3. **High-cardinality tags**, có thể hữu ích cho trace/span nhưng không nên đưa vào metric dimensions.
4. **Contextual name**, giúp span dễ đọc trong tracing UI.
5. **Context của operation**, như Kafka topic, listener ID, group ID hoặc record metadata mà convention có thể truy cập theo version.

**ObservationConvention** quyết định một phần cách những metadata này được ánh xạ thành tên và tags. Nó không tự bật Micrometer Observation, không tạo exporter và không bảo đảm dữ liệu tới Prometheus/Jaeger/Tempo nếu registry, handlers hoặc tracing backend chưa được cấu hình.

### 1.1 Sơ đồ tổng thể

~~~mermaid
flowchart TD
    A["Kafka ProducerRecord / ConsumerRecord"] --> C["Spring Kafka observation context"]
    C --> V["ObservationConvention"]
    V --> N["Observation name + KeyValues"]
    N --> R["ObservationRegistry"]
    R --> M["Metrics ObservationHandler"]
    R --> T["Tracing ObservationHandler"]
    M --> P["MeterRegistry / Prometheus"]
    T --> X["Tracer / OTLP / tracing backend"]
~~~

Nhìn vào sơ đồ, convention là **lớp đặt tên và phân loại thông tin**, còn ObservationRegistry cùng ObservationHandlers quyết định cách observation được xử lý thành metrics/tracing.

## 2. Vì sao cần phân biệt Observation với Timer?

Spring Kafka có hai cơ chế thường gặp:

| Cơ chế | Công tắc | Mục tiêu |
|---|---|---|
| Micrometer listener timers truyền thống | ContainerProperties.micrometerEnabled | Đo listener invocation bằng Micrometer Timer |
| Micrometer Observation | ContainerProperties.observationEnabled | Tạo Observation có thể dẫn tới metrics và tracing |
| Micrometer template timers truyền thống | KafkaTemplate.micrometerEnabled | Đo Kafka send operations |
| KafkaTemplate Observation | KafkaTemplate.observationEnabled | Observation cho producer send flow |

Trong Spring Kafka **3.0 trở lên**, Micrometer Observation được hỗ trợ cho KafkaTemplate và listener containers. Khi Observation được bật, cơ chế Micrometer timers truyền thống tương ứng được vô hiệu hóa để Observation đảm trách instrumentation, theo framework semantics. Các tài liệu Spring Kafka khác nhau có khác biệt về batch listener support, cần đọc phần phiên bản ở cuối bài.

### 2.1 ObservationConvention không đồng nghĩa bật Observation

Đoạn sau chỉ đặt convention:

~~~java
factory.getContainerProperties()
       .setObservationConvention(customConvention);
~~~

Nếu observationEnabled vẫn false, convention có thể không được sử dụng cho listener path đó.

Cần cả hai:

~~~java
factory.getContainerProperties()
       .setObservationEnabled(true);

factory.getContainerProperties()
       .setObservationConvention(customConvention);
~~~

Tương tự với KafkaTemplate:

~~~java
kafkaTemplate.setObservationEnabled(true);
kafkaTemplate.setObservationConvention(templateConvention);
~~~

Một lỗi phổ biến là khai báo một bean convention rồi giả định Spring Kafka tự dùng bean đó trên tất cả listener containers. Không nên suy luận như vậy nếu chưa biết auto-configuration và factory wiring thực tế: **hãy gắn convention tường minh vào đúng KafkaTemplate hoặc ContainerProperties**.

## 3. Các interface chuyên biệt trong Spring Kafka

Micrometer cung cấp interface tổng quát:

~~~java
ObservationConvention<T extends Observation.Context>
~~~

Spring Kafka giới thiệu hai interface chuyên biệt:

~~~java
KafkaListenerObservationConvention
KafkaTemplateObservationConvention
~~~

Bảng đối chiếu:

| Interface | Context type | Nơi cấu hình |
|---|---|---|
| KafkaListenerObservationConvention | KafkaRecordReceiverContext | ContainerProperties.setObservationConvention(...) |
| KafkaTemplateObservationConvention | KafkaRecordSenderContext | KafkaTemplate.setObservationConvention(...) |

Các class này thuộc package Spring Kafka:

~~~java
org.springframework.kafka.support.micrometer
~~~

Các context tương ứng cũng thuộc package đó.

### 3.1 Default convention của listener

Spring Kafka cung cấp:

~~~java
KafkaListenerObservation.DefaultKafkaListenerObservationConvention
~~~

Đây là default implementation của KafkaListenerObservationConvention. Có thể **kế thừa class mặc định** rồi bổ sung tags, thay vì tự viết lại toàn bộ.

### 3.2 Default convention của template

Spring Kafka cung cấp:

~~~java
KafkaTemplateObservation.DefaultKafkaTemplateObservationConvention
~~~

Tương tự, class này tạo các tên/tags mặc định cho producer observation. Với yêu cầu bổ sung vài thuộc tính ứng dụng, kế thừa default thường an toàn hơn việc thay thế hoàn toàn contract.

### 3.3 Context receiver và sender

**KafkaRecordReceiverContext** biểu diễn ngữ cảnh nhận ConsumerRecord. Trong các phiên bản phù hợp, nó có các accessor như:

~~~java
context.getListenerId();
context.getSource();      // Source topic
context.getRecord();      // ConsumerRecord
~~~

Các version mới hơn có thể bổ sung:

~~~java
context.getGroupId();
context.getClientId();
context.getPartition();
context.getOffset();
~~~

**KafkaRecordSenderContext** biểu diễn ngữ cảnh gửi ProducerRecord:

~~~java
context.getBeanName();
context.getDestination(); // Destination topic
context.getRecord();      // ProducerRecord
~~~

Không dùng getRecord() trong code target một Spring Kafka version quá cũ: method này được thêm cho dynamic tags trong các bản Spring Kafka **3.0.6** trở lên. Một số accessor receiver như getGroupId/getClientId có lịch sử bổ sung ở phiên bản sau. Cần đối chiếu API chính xác với dependency của dự án.

## 4. Bốn phương thức của một ObservationConvention

Một custom ObservationConvention có thể tùy biến các khía cạnh:

### 4.1 getName()

**getName()** trả về tên operation observation ổn định. Spring Kafka default dùng các tên phổ biến:

~~~text
spring.kafka.listener
spring.kafka.template
~~~

Tên này thường được dùng trong metrics/tracing instrumentation. Đổi getName() một cách tùy tiện có thể làm dashboards, alerts và semantic conventions mất liên tục.

### 4.2 getContextualName(context)

**getContextualName()** cho tên dễ đọc của một operation cụ thể trong tracing UI. Ví dụ tên gắn với topic hoặc hành động consume/publish:

~~~text
orders.created receive
orders.projected publish
~~~

Contextual name không phải metric label để phân nhóm mọi business record. Tránh đưa UUID/order ID vào tên span của mọi event nếu không cần.

### 4.3 getLowCardinalityKeyValues(context)

Phương thức này trả về **low-cardinality tags** — những nhãn có số lượng giá trị hữu hạn và phù hợp với dimensions của metrics.

Ví dụ:

~~~text
app.domain=orders
app.pipeline=projection
app.stage=consume
messaging.system=kafka
~~~

Low-cardinality tags có thể xuất hiện trên cả metrics và traces. Chúng cần cực kỳ ổn định, có danh sách giá trị dự kiến và tránh chứa dữ liệu cá nhân.

### 4.4 getHighCardinalityKeyValues(context)

Phương thức này trả về **high-cardinality tags**, thường có ý nghĩa trong tracing. Ví dụ có thể là metadata offset, partition, client ID hoặc những thuộc tính chi tiết hơn, tùy version và default convention.

High-cardinality không có nghĩa “được phép đưa mọi nội dung nhạy cảm vào trace”. Các tracing backends cũng có giới hạn ingestion, retention, sampling, access control và privacy.

### 4.5 supportsContext(context)

Interface ObservationConvention có cơ chế xác định convention có hỗ trợ Observation.Context cụ thể hay không. Khi dùng KafkaListenerObservationConvention/KafkaTemplateObservationConvention, interface chuyên biệt có semantics mặc định hỗ trợ context tương ứng.

Chỉ nên override supportsContext() khi có lý do thực sự và hiểu cơ chế chọn convention. Một predicate sai có thể khiến custom convention không được áp dụng.

## 5. Low-cardinality và high-cardinality khác nhau thế nào?

Đây là quyết định thiết kế quan trọng nhất khi triển khai ObservationConvention.

| Thuộc tính | Low-cardinality | High-cardinality |
|---|---|---|
| Tập giá trị | Hữu hạn, tương đối nhỏ | Có thể thay đổi theo từng event |
| Ví dụ an toàn | app.domain=orders | Kafka offset nếu cần cho trace |
| Mục tiêu chính | Metrics aggregation và trace classification | Trace detail/correlation |
| Rủi ro | Explosion của metric series khi dùng sai | Tracing storage/cost, privacy |
| Thường dùng ở Prometheus labels | Có | Không nên |
| Nên chứa orderId/eventId | Không | Chỉ nếu thật sự cần, đã kiểm tra policy dữ liệu |
| Có thể thay đổi sau mỗi message | Không nên | Có thể, nhưng phải kiểm soát |

### 5.1 Vì sao một tag sai có thể phá monitoring?

Giả sử một timer có:

- 10 listener IDs.
- 2 results.
- 5 error categories.
- 3 environments.
- 20 pod instances.

Tổ hợp lý thuyết đã có thể là:

~~~text
10 x 2 x 5 x 3 x 20 = 6,000 series
~~~

Nếu thêm app.order_id với 1 triệu giá trị, số series có thể bùng nổ. Với histogram buckets, chi phí có thể còn lớn hơn.

**Không đặt Kafka offset, event ID, user ID, order ID, request ID, token hoặc raw key vào low-cardinality KeyValues.**

### 5.2 High-cardinality cũng cần ngân sách

Traces không phải “nơi miễn phí cho mọi dữ liệu”. Một trace có thể được export sang hệ thống của nhà cung cấp khác, phục vụ tìm kiếm toàn tổ chức và có retention dài.

Trước khi thêm high-cardinality field:

1. Có cần field đó để debug không?
2. Nó có chứa PII hoặc secret không?
3. Có thể dùng hash hoặc correlation ID an toàn hơn không?
4. Có sampling/retention phù hợp không?
5. Có giới hạn độ dài value không?
6. Ai có quyền xem và export traces?
7. Có trùng dữ liệu đã được default convention cung cấp không?

Một cách an toàn là chỉ thêm tags nghiệp vụ **phân loại** và dùng structured logs để lưu chi tiết record với quyền truy cập phù hợp.

## 6. Mẫu custom KafkaListenerObservationConvention

Cách ít rủi ro là kế thừa default convention và **bổ sung tags**, giữ lại các semantic tags của framework.

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.kafka.support.micrometer.KafkaListenerObservation;
import org.springframework.kafka.support.micrometer.KafkaRecordReceiverContext;

public class OrdersListenerObservationConvention
    extends KafkaListenerObservation.DefaultKafkaListenerObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            KafkaRecordReceiverContext context) {

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("app.domain", "orders"))
            .and(KeyValue.of("app.pipeline", "projection"));
    }
}
~~~

Ví dụ này không tự đặt một metric name mới; nó giữ tên mặc định và thêm hai low-cardinality tags có số lượng giá trị thấp.

### 6.1 Vì sao gọi super?

Default convention có thể đã gắn các semantic KeyValues do Spring Kafka định nghĩa, như listener identity, messaging system, source topic hoặc group metadata theo version.

Nếu override và trả về:

~~~java
return KeyValues.of(
    KeyValue.of("app.domain", "orders")
);
~~~

thì có thể vô tình **loại bỏ các default tags** quan trọng khỏi metrics/traces. Điều này làm dashboard đã dùng default tags bị mất dữ liệu hoặc tracing bị thiếu thông tin.

Do đó, khi chỉ cần thêm tags, ưu tiên:

~~~java
return super.getLowCardinalityKeyValues(context)
    .and(KeyValue.of("app.domain", "orders"));
~~~

Chỉ thay thế hoàn toàn convention khi có một thiết kế semantic convention chủ đích, đã kiểm tra metric schema và tracing backend.

### 6.2 Đặt key names có namespace

Tên app.domain và app.pipeline tránh đụng trực tiếp các semantic keys chuẩn của Kafka/Micrometer.

Không tái sử dụng một key chuẩn, ví dụ messaging.system, để ghi giá trị domain riêng. Nếu add trùng key với value khác, behavior downstream có thể khó hiểu, bị deduplicate hoặc tạo labels bất nhất.

### 6.3 Không đặt topic vào custom tag nếu default đã có

Trong các version hiện đại, default Kafka listener observation thường đã có các messaging semantic attributes, như source topic. Nếu chỉ muốn nhóm theo topic, trước hết kiểm tra default tags.

Thêm app.topic và messaging.source.name cùng giá trị có thể khiến dữ liệu trùng lặp và tăng chi phí. Chỉ bổ sung khi cần một grouping business-level khác.

## 7. Gắn convention vào listener container factory

Ví dụ khai báo bean:

~~~java
@Configuration
public class OrdersListenerObservationConfiguration {

    @Bean
    OrdersListenerObservationConvention ordersObservationConvention() {
        return new OrdersListenerObservationConvention();
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            OrdersListenerObservationConvention convention) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties()
               .setObservationEnabled(true);

        factory.getContainerProperties()
               .setObservationConvention(convention);

        return factory;
    }
}
~~~

Listener tham chiếu đúng factory:

~~~java
@Component
public class OrderProjectionListener {

    private final OrderProjectionService service;

    public OrderProjectionListener(OrderProjectionService service) {
        this.service = service;
    }

    @KafkaListener(
        id = "orders-projection",
        groupId = "orders-projection-prod",
        topics = "orders.created",
        containerFactory = "ordersListenerFactory"
    )
    public void handle(OrderEvent event) {
        service.apply(event);
    }
}
~~~

OrderEvent và OrderProjectionService là ví dụ minh họa. ConsumerFactory phải có Kafka bootstrap/security, deserializer, error handler và cấu hình concurrency phù hợp môi trường thực tế.

### 7.1 Custom factory phải giữ các cấu hình reliability khác

Nếu ứng dụng đã có factory với DefaultErrorHandler, AckMode, transaction manager, interceptors hoặc message converter, đừng thay nó bằng một factory tối giản chỉ để bật Observation.

Các thay đổi về observability không được vô tình làm thay đổi:

- Consumer group ID hoặc assignment.
- Deserializer/ErrorHandlingDeserializer.
- Retry và DLT policy.
- AckMode hoặc manual acknowledgment.
- Transaction boundary.
- Threading/concurrency.
- Pause/resume behavior.

Nên đưa Observation settings vào factory hiện có hoặc một factory customizer được kiểm soát rõ.

### 7.2 Convention gắn vào factory, không mặc định toàn deployment

Một project có thể có:

~~~text
ordersListenerFactory  -> OrdersListenerObservationConvention
paymentsListenerFactory -> PaymentsListenerObservationConvention
auditListenerFactory    -> Default convention
~~~

Mỗi factory có policy khác nhau. Nếu có nhiều pods, convention bean bên trong một pod chỉ ảnh hưởng instance đang chạy trong pod đó. Metrics/tracing toàn deployment được tổng hợp bởi monitoring backend.

## 8. Dynamic tags theo ConsumerRecord

Kể từ các phiên bản Spring Kafka **3.0.6** trở lên, observation context cung cấp record cho custom convention để xây dynamic tags.

Ví dụ phân nhóm source topic vào một **enum-like route** có số giá trị giới hạn:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.support.micrometer.KafkaListenerObservation;
import org.springframework.kafka.support.micrometer.KafkaRecordReceiverContext;

public class RoutedListenerObservationConvention
    extends KafkaListenerObservation.DefaultKafkaListenerObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            KafkaRecordReceiverContext context) {

        ConsumerRecord<?, ?> record = context.getRecord();

        String route = switch (record.topic()) {
            case "orders.created" -> "orders";
            case "payments.completed" -> "payments";
            default -> "other";
        };

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("app.route", route));
    }
}
~~~

Đoạn code dùng Java switch expression; nếu project đang ở Java version cũ, thay bằng switch statement/if-else.

**Điểm cốt lõi:** route chỉ có ba giá trị, bất kể record key, offset hay event ID thay đổi. Đây là dynamic tag dựa trên record nhưng vẫn **low cardinality**.

### 8.1 Không làm việc nặng trong convention

getLowCardinalityKeyValues có thể được gọi trong flow xử lý mỗi record. Không sử dụng convention để:

- Query database.
- Gọi HTTP API.
- Parse JSON payload dung lượng lớn chỉ để tìm tag.
- Đọc secret service.
- Tăng/giảm business counters.
- Thay đổi Kafka record headers hoặc offset.
- Throw exception do dữ liệu business không hợp lệ.

Nếu cần phân loại event type từ payload, nên có contract/header metadata đơn giản với whitelist hoặc instrument tại service layer riêng.

### 8.2 Header có thể thiếu hoặc không hợp lệ

Nếu muốn lấy event type từ header, cần:

1. Kiểm tra header null.
2. Giải mã UTF-8 theo contract.
3. Validate độ dài.
4. Chuyển mapping vào whitelist có số giá trị cố định.
5. Với value lạ, trả "other" thay vì tạo một tag mới từ raw header.
6. Không ném lỗi từ convention để phá toàn bộ consumer vì một header lỗi.

Một observation convention **không được trở thành parser hay validator bắt buộc của business payload**. Độ tin cậy của listener quan trọng hơn độ chi tiết của nhãn metrics.

## 9. High-cardinality KeyValues cho listener

Một custom convention có thể bổ sung high-cardinality metadata:

~~~java
@Override
public KeyValues getHighCardinalityKeyValues(
        KafkaRecordReceiverContext context) {

    return super.getHighCardinalityKeyValues(context);
}
~~~

Ví dụ cố ý không thêm gì vì Spring Kafka default có thể đã cung cấp Kafka offset, partition, client ID hoặc những semantic attributes khác tùy version.

Khi cần thêm một correlation attribute đã được kiểm duyệt, có thể tạo KeyValue phù hợp từ context hoặc application metadata. Nhưng không nên sao chép raw key/value hay customer information vào trace một cách mặc định.

### 9.1 Vì sao high tags không nên dùng để tính metrics?

Micrometer metrics handlers thường quan tâm low-cardinality KeyValues để tạo time series. High-cardinality KeyValues phù hợp hơn với trace tags, nhưng chúng không được dùng làm một metric dimension per-record.

Nếu cố đặt offset vào low-cardinality tags để query offset trong Prometheus, mọi message có offset mới có thể tạo một series mới. Chỉ dùng offset trong logs hoặc traces có kiểm soát.

### 9.2 Sampling và truy tìm một event

Traces thường được sampling. Không thể bảo đảm một record cụ thể có span chỉ vì Observation được bật, trừ khi sampling policy ghi lại trace đó.

Khi cần điều tra một event ID chính xác, nên có structured logs với event ID, topic, partition, offset, và sử dụng trace/span IDs để liên kết khi trace tồn tại. ObservationConvention chỉ giúp chuẩn hóa context tags, không phải hệ thống audit bền vững.

## 10. KafkaTemplateObservationConvention

Phía producer có interface chuyên biệt **KafkaTemplateObservationConvention**, context là **KafkaRecordSenderContext**.

Cách tùy biến an toàn tương tự listener:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.kafka.support.micrometer.KafkaRecordSenderContext;
import org.springframework.kafka.support.micrometer.KafkaTemplateObservation;

public class OrdersTemplateObservationConvention
    extends KafkaTemplateObservation.DefaultKafkaTemplateObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            KafkaRecordSenderContext context) {

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("app.domain", "orders"))
            .and(KeyValue.of("app.pipeline", "publication"));
    }
}
~~~

Nếu producer gửi nhiều topics, có thể dùng context.getDestination() hoặc context.getRecord().topic() trong các phiên bản hỗ trợ để chọn một loại route có whitelist.

### 10.1 Cấu hình KafkaTemplate

~~~java
@Bean
KafkaTemplate<String, OrderConfirmed> orderKafkaTemplate(
        ProducerFactory<String, OrderConfirmed> producerFactory,
        OrdersTemplateObservationConvention convention) {

    KafkaTemplate<String, OrderConfirmed> template =
        new KafkaTemplate<>(producerFactory);

    template.setObservationEnabled(true);
    template.setObservationConvention(convention);

    return template;
}
~~~

Với Spring Boot auto-configuration, có thể đã có KafkaTemplate bean. Không tạo một template khác chỉ để observability nếu việc này làm mất transactional ProducerFactory, producer listener, security hoặc serializers đang dùng.

### 10.2 Template bean name khác consumer listener ID

Producer context có thể cung cấp **getBeanName()**, còn consumer context cung cấp **getListenerId()**. Đây là các định danh khác nhau.

Ví dụ:

~~~text
Producer KafkaTemplate bean: orderKafkaTemplate
Destination topic: orders.created

Consumer @KafkaListener id: orders-projection
Source topic: orders.created
Consumer group: orders-projection-prod
~~~

ObservationConvention có thể giữ những thông tin này trong semantic tags để phân biệt send và receive spans. Đừng dùng cùng app.role tag giá trị "consumer" cho cả template và listener nếu muốn dashboard phân biệt hướng xử lý.

## 11. End-to-end tracing qua Kafka

Một producer service gửi event; consumer service nhận event. Muốn tracing liên tục qua hai service, cần truyền **trace context** qua Kafka record headers và trích xuất ở consumer.

~~~mermaid
sequenceDiagram
    participant A as checkout-api
    participant P as KafkaTemplate
    participant K as Kafka broker
    participant C as orders listener
    participant T as Tracing backend
    A->>P: send OrderCreated
    P->>K: ProducerRecord + trace headers
    K->>C: ConsumerRecord + trace headers
    C->>T: Receiver span / child work
    P->>T: Sender span
~~~

Trong Spring Kafka hỗ trợ Micrometer Observation:

- Bật Observation ở KafkaTemplate để tạo sender observation.
- Bật Observation ở listener container để tạo receiver observation.
- Cấu hình ObservationRegistry, tracing bridge, propagators và exporter phù hợp.
- Đảm bảo headers không bị producer/interceptor làm mất trong quá trình publish.
- Với non-Spring producers/consumers, đảm bảo propagation format tương thích.

**ObservationConvention không tự cài tracer hoặc exporter**, cũng không tự viết mọi trace headers nếu Observation/Tracing infrastructure chưa hoạt động.

### 11.1 Tên và tags không phải trace propagation

Một custom convention chỉ thêm app.domain=orders không làm trace bên consumer tự trở thành child của producer span.

Việc tiếp nối trace đòi hỏi:

1. Sender context có khả năng inject propagation headers.
2. Producer record thật sự mang headers.
3. Receiver context extract đúng headers.
4. Tracer và ObservationHandlers được cấu hình.
5. Sampling policy cho phép lưu dữ liệu nếu muốn thấy trace trên backend.

Nếu trace bị đứt giữa producer và consumer, cần kiểm tra propagation path trước khi sửa convention.

### 11.2 Tracing không thay exactly-once

Trace có thể ghi nhận một record được xử lý nhiều lần sau rollback hoặc rebalance. Điều này là tín hiệu quan sát, không phải cơ chế deduplication.

Kafka EOS vẫn cần transactional producer, listener container transactions, offset-in-transaction và read_committed downstream phù hợp. Không gắn trace ID rồi coi nó là business event idempotency key.

### 11.3 Header trace cũng cần security

Trace headers thường chứa correlation identifiers, không phải full payload. Tuy nhiên, không nên mở rộng propagation bằng cách nhúng JWT, email, session secret hoặc thông tin cá nhân vào baggage.

Baggage có thể lan qua nhiều services và Kafka topics; mọi field phải có justification, giới hạn kích thước và data classification phù hợp.

## 12. Default semantic tags của Spring Kafka

Theo tài liệu Micrometer Observation của Spring Kafka hiện đại, listener và template observations có semantic naming riêng:

~~~text
spring.kafka.listener
spring.kafka.template
~~~

Ví dụ các semantic attributes được tài liệu hóa:

| Nhóm | Ví dụ tag | Ý nghĩa |
|---|---|---|
| Listener | messaging.system | Hệ thống messaging, ví dụ Kafka |
| Listener | messaging.operation | Hoạt động receive/process |
| Listener | messaging.source.name | Source topic |
| Listener | messaging.kafka.consumer.group | Consumer group |
| Listener | spring.kafka.listener.id | Listener/container identity |
| Producer | messaging.destination.name | Destination topic |
| Producer | spring.kafka.template.name | KafkaTemplate bean name |
| Producer | messaging.operation | Send/publish operation |
| Kafka metadata | messaging.kafka.source.partition | Partition metadata |
| Kafka metadata | messaging.kafka.message.offset | Kafka offset metadata |

Tập low/high-cardinality keys và names cụ thể có thể thay đổi giữa Spring Kafka 3.0, 3.3, 4.x và các phiên bản Micrometer semantic conventions. Không xây dashboard dài hạn chỉ dựa trên một bài blog không khớp version.

### 12.1 Giữ default tags khi thêm tags ứng dụng

Nếu thêm app.domain mà làm mất messaging.system hoặc listener.id, một số dashboards có thể không còn phân nhóm đúng.

Kế thừa default conventions và gọi super là cách đơn giản để giữ semantic tags mặc định. Nếu muốn thay đổi semantic schema sâu hơn, cần:

- Thiết kế schema phiên bản mới.
- Liệt kê metrics/traces bị ảnh hưởng.
- Kiểm tra tất cả dashboards/alerts.
- Thử trên canary.
- Có kế hoạch rollback.

### 12.2 Contextual name khác metric name

Contextual name là tên hiển thị của một observation cụ thể trong trace:

~~~text
orders.created receive
orders.projected publish
~~~

Metric name ổn định là:

~~~text
spring.kafka.listener
spring.kafka.template
~~~

Đổi contextual name có thể cải thiện readability trong trace UI; đổi metric name có thể làm query cũ mất data. Không biến metric name thành một chuỗi gồm order ID hoặc offset.

## 13. Custom contextual name

Khi cần span dễ đọc theo topic:

~~~java
public class OrdersListenerObservationConvention
    extends KafkaListenerObservation.DefaultKafkaListenerObservationConvention {

    @Override
    public String getContextualName(KafkaRecordReceiverContext context) {
        return context.getSource() + " receive";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(
            KafkaRecordReceiverContext context) {

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("app.domain", "orders"));
    }
}
~~~

Nếu listener subscribe hàng nghìn dynamically created topics, contextual names có thể rất nhiều giá trị. Điều này không giống high-cardinality metric labels nhưng vẫn ảnh hưởng trace analysis và search.

Nên dùng topic names theo naming convention hữu hạn khi có thể. Không xây contextual name từ eventId, raw message key hoặc PII.

### 13.1 Không đổi getName() tùy tiện

Nếu override getName() và đổi spring.kafka.listener thành một tên custom theo mỗi domain, metrics/traces có thể phân mảnh.

Chỉ làm điều này nếu có kế hoạch semantic metric schema rõ, vì dashboards có thể phụ thuộc tên cũ. Khi chỉ thêm thông tin app-specific, **giữ getName() mặc định** và thêm low-cardinality KeyValues.

## 14. Dynamic key-values theo header: whitelist, không raw value

Giả sử producer cung cấp header event-type, có các giá trị hợp lệ:

~~~text
OrderCreated
OrderConfirmed
OrderCancelled
~~~

Nếu muốn phân nhóm app.event.type trong metrics, phải tránh nhận mọi giá trị tùy ý từ producer.

Quy trình an toàn:

1. Đọc header theo contract được chuẩn hóa.
2. Giới hạn kích thước tối đa.
3. Decode đúng charset.
4. Mapping về enum/tập cho phép.
5. Nếu header null/malformed hoặc ngoài whitelist, map thành other.
6. Không ném exception từ convention.
7. Không thêm raw header vào low-cardinality tags.
8. Không log raw header nếu nó có thể chứa dữ liệu nhạy cảm.

Ví dụ mapping function:

~~~java
private static String knownEventType(String raw) {

    if ("OrderCreated".equals(raw)) {
        return "created";
    }
    if ("OrderConfirmed".equals(raw)) {
        return "confirmed";
    }
    if ("OrderCancelled".equals(raw)) {
        return "cancelled";
    }
    return "other";
}
~~~

Nếu header chứa event UUID, không bao giờ lấy raw UUID làm low-cardinality label để “dễ tìm từng event”.

## 15. ObservationConvention so với các extension points khác

Để tránh đặt sai logic, cần phân biệt:

| Extension point | Mục tiêu | Khi nào dùng |
|---|---|---|
| ObservationConvention | Tên và low/high KeyValues từ context | Chuẩn hóa metrics/tracing semantic tags |
| ObservationRegistry | Registry quản lý observations/handlers | Kết nối metrics/tracing lifecycle |
| ObservationHandler | Xử lý start/stop/error observation | Ghi metrics hoặc tạo tracing spans |
| ObservationFilter | Điều chỉnh observation context theo chính sách | Thay đổi tags chung ở registry layer |
| ObservationPredicate | Chọn observation có được ghi nhận không | Giảm instrumentation cho operation không cần |
| Micrometer MeterFilter | Chặn/chuyển đổi meters/tags | Kiểm soát metrics cardinality |
| Spring Kafka RecordFilterStrategy | Lọc Kafka ConsumerRecord trước listener | Bỏ qua một số business records |
| Kafka ProducerInterceptor / ConsumerInterceptor | Can thiệp record flow ở Kafka client | Metadata/serialization logic có chủ đích |
| Spring Kafka CommonErrorHandler | Retry/recover errors | Reliability khi xử lý record thất bại |

ObservationConvention **không nên** là nơi:

- Bỏ qua record không hợp lệ.
- Commit offset.
- Publish DLT.
- Điều khiển pause/resume.
- Gọi external service để enrich payload.
- Quyết định Kafka transaction commit.

Những hành động đó thuộc các lớp khác và có semantics khác.

### 15.1 Convention khác business validation

Nếu một OrderCreated có amount âm, convention không nên ném InvalidOrderException chỉ vì muốn gắn tag valid=false. Validation phải ở schema/business layer.

Convention có thể thêm app.event.type=created nếu thông tin này được phép, nhưng không được trở thành bước xử lý dữ liệu có side effect.

## 16. Tác động đến latency và tài nguyên

ObservationConvention được gọi trên đường xử lý Kafka records. Một convention chậm có thể tăng listener overhead.

Các thao tác nên làm:

- Đọc topic/listener ID từ context.
- Map giá trị về enum/tập hữu hạn.
- Trả KeyValues nhỏ.
- Reuse constant KeyValues khi có thể.
- Tránh regex nặng/JSON parsing lặp theo record.
- Tránh network và disk I/O.

Các thao tác không nên làm:

- Query PostgreSQL lấy domain.
- Gọi feature flag server mỗi record.
- Serialize toàn bộ Kafka payload để đưa vào tag.
- Đọc file cấu hình mỗi invocation.
- Gửi log cấp INFO cho mỗi KeyValue.
- Tạo chuỗi hàng megabytes từ raw record.

### 16.1 Lỗi trong convention có thể ảnh hưởng business flow

Một convention không phải process riêng tách khỏi listener. Nếu convention ném exception trên thread instrument Kafka operation, kết quả có thể ảnh hưởng flow, logging, lỗi hoặc xử lý record theo implementation/version.

Do đó, custom convention cần:

- Null-safety.
- Whitelisted values.
- Không phụ thuộc external systems.
- Không parse payload không đáng tin cậy nếu chưa cần.
- Không làm lộ secrets.
- Unit test các input đặc biệt.

Quan sát không nên trở thành nguyên nhân làm đứng consumer hoặc gây retry storm.

## 17. Micrometer Observation và batch listeners

Cơ chế batch observation **có khác biệt theo phiên bản**.

Trong tài liệu Spring Kafka các phiên bản 3.x, Micrometer Observation từng được mô tả là **không hỗ trợ batch listener**, và listener timers truyền thống được dùng thay thế trong batch mode.

Trong tài liệu Spring Kafka mới hơn (ví dụ dòng 4.2), có batch-level observation khi cấu hình phù hợp; thuộc tính như **recordObservationsInBatch** điều khiển liệu observation được tạo cho cả batch hay ở mức records. Semantics mặc định và support có thể thay đổi.

**Không áp dụng một quy tắc duy nhất cho mọi phiên bản.**

### 17.1 Hệ quả với một custom listener convention

Nếu batch listener không dùng Observation ở Spring Kafka version đang chạy, custom KafkaListenerObservationConvention có thể không được gọi cho batch invocation. Khi đó:

- Listener timer truyền thống có thể vẫn được ghi.
- Custom convention tags có thể không xuất hiện.
- Tracing context theo record có thể không có như record listener.
- Không thể xác nhận bằng một test chỉ gọi record listener.

### 17.2 Trong phiên bản có batch observation

Cần xem:

- Observation context là record-level hay batch-level.
- Default low-cardinality tags có tương thích tên meter dùng cho record listeners không.
- Có nhận được ConsumerRecord trong context hay không.
- Một observation đại diện một batch hay một record.
- Có thêm tags làm cardinality tăng theo batch/partition không.

Với metric throughput, **batch invocation count không bằng số records được xử lý**. Nếu cần business record rate, instrument batch size riêng.

## 18. Kafka client metrics khác ObservationConvention

Spring Kafka còn hỗ trợ Kafka client metrics qua cơ chế MicrometerConsumerListener/MicrometerProducerListener hoặc binder tương ứng. Những metrics này có thể mô tả:

- Records consumed rate.
- Fetch latency.
- Producer request latency.
- Bytes in/out.
- Retry hoặc network information.
- Consumer coordinator/rebalance metrics.

Các metrics client đó **không tự sinh ra chỉ vì** đặt một KafkaListenerObservationConvention.

Nếu cần consumer lag theo topic/partition/group, phải sử dụng metrics Kafka client/broker/admin phù hợp. Listener Observation có thể giúp giải thích listener chậm nhưng không thay thế lag monitoring.

### 18.1 Dashboard reliability đầy đủ

Một dashboard production cần kết hợp:

1. Listener observation duration và failure.
2. Kafka consumer lag và throughput.
3. Producer send success/failure.
4. Retry/DLT recovery metrics.
5. Kafka transaction commit/abort nếu dùng EOS.
6. Business completion và duplicate detection.
7. End-to-end event age.
8. Trace sampling và propagation health.

Convention chỉ giúp chuẩn hóa cách những quan sát tương ứng được phân loại.

## 19. ObservationRegistry và tracing backend

Bật observationEnabled chưa đủ để thấy trace trên backend. Cần đảm bảo:

- Có Micrometer Observation trên classpath.
- Có ObservationRegistry được Spring Boot/Micrometer cấu hình.
- Có handler để ghi metrics.
- Có Micrometer Tracing bridge tới tracer implementation.
- Có exporter/sender tới tracing backend.
- Propagation format thống nhất giữa các services.
- Sampling cho phép giữ những traces cần thiết.

Một dependency setup Spring Boot minh họa:

~~~groovy
dependencies {
    implementation("org.springframework.kafka:spring-kafka")
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    implementation("io.micrometer:micrometer-registry-prometheus")

    // Chọn một tracing bridge/exporter tương thích với BOM dự án.
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    implementation("io.opentelemetry:opentelemetry-exporter-otlp")
}
~~~

Dependencies thực tế phụ thuộc Spring Boot/Spring Kafka version. Nên dùng Spring Boot dependency management/BOM để đồng bộ Micrometer, tracing bridge, OpenTelemetry SDK/exporter.

### 19.1 Đường metrics và traces có thể khác nhau

~~~mermaid
flowchart TD
    O["Kafka Observation"] --> R["ObservationRegistry"]
    R --> H1["Metrics handler"]
    R --> H2["Tracing handler"]
    H1 --> M["MeterRegistry / Prometheus"]
    H2 --> T["Tracer / OTLP collector"]
    M --> G["Metrics dashboard"]
    T --> Z["Trace UI"]
~~~

Nếu metrics có nhưng traces không có, convention có thể vẫn hoạt động; vấn đề có thể là tracing handler, sampler, exporter, backend hoặc Kafka trace headers.

Nếu traces có nhưng metrics không có, cần kiểm tra MeterRegistry/metrics handler và exporter. Đừng sửa low-cardinality tags trước khi xác định pipeline bị đứt ở đâu.

### 19.2 Trace sampling

Nếu sampler chỉ giữ 10% traces, việc không thấy trace cho một message cụ thể có thể hoàn toàn bình thường. Không dùng sự vắng mặt của một trace làm bằng chứng message bị mất.

Khi cần forensic audit cho mọi event, dùng durable audit store/log có chính sách phù hợp thay vì kỳ vọng tracing backend luôn lưu toàn bộ records.

## 20. ObservationConvention và Kafka headers

Kafka headers thường được dùng để mang trace propagation context.

Ở producer:

~~~text
HTTP trace context
  -> KafkaTemplate sender observation
  -> inject propagation metadata vào ProducerRecord headers
  -> broker lưu Kafka record và headers
~~~

Ở consumer:

~~~text
Kafka ConsumerRecord headers
  -> listener receiver observation
  -> extract trace context
  -> span/child operations trong xử lý record
~~~

Convention chủ yếu quyết định **operation labels**; propagation do sender/receiver context và tracing handlers đảm trách.

### 20.1 Không ghi traceparent bằng code tự chế trong convention

Nếu muốn dùng W3C Trace Context hoặc một format tương ứng, hãy cấu hình Micrometer Tracing và propagators đúng.

Tự thêm một chuỗi traceparent vào headers từ convention có thể:

- Không đúng format.
- Không khớp sampled flags.
- Ghi đè metadata producer đã có.
- Bị thiếu parent/span semantics.
- Làm trace cross-service bị đứt hoặc sai.

ObservationConvention không phải Kafka ProducerInterceptor để sửa record headers.

### 20.2 Khi consumer nhận record không có trace headers

Hệ thống vẫn có thể tạo receiver observation/span mới không nối được với sender context ban đầu. Không nên reject message chỉ vì không có trace context; tracing là observability concern, không phải business schema bắt buộc.

Nếu upstream là một non-Spring producer, cần thống nhất propagation format để nối traces. Nếu không thống nhất được, có thể bắt đầu trace mới ở consumer và dùng event ID trong structured logs để hỗ trợ correlation.

## 21. Threading và Observation scope

Observation/tracing context có thể phụ thuộc thread-local scope hoặc context propagation mechanisms. Với synchronous record listener, framework có thể quản lý scope trong lúc gọi listener.

Nhưng nếu listener chuyển công việc sang executor:

~~~java
@KafkaListener(topics = "orders.created")
public void handle(OrderEvent event) {
    executor.submit(() -> service.process(event));
}
~~~

Child task có thể chạy ngoài observation scope ban đầu. Nó có thể mất trace context nếu không được propagate phù hợp; listener invocation cũng có thể kết thúc trước business work.

Để thiết kế an toàn:

- Không assume trace context tự đi qua mọi thread.
- Dùng context propagation API/executor integration phù hợp với Micrometer version.
- Giữ acknowledgment và transaction semantics của Kafka đúng.
- Đo business processing completion tách khỏi listener method return.
- Tránh sử dụng KafkaConsumer từ async thread.
- Test cả trace parent-child relationship và offset commit behavior.

### 21.1 Reactor/coroutines là đường khác

Nếu ứng dụng dùng Reactor, Kotlin coroutines hoặc reactive pipelines, scope propagation khác với Java imperative ThreadLocal thuần. Cần sử dụng integration phù hợp với runtime; không copy một mẫu ThreadLocal wrapper cho mọi môi trường.

ObservationConvention vẫn dùng để định nghĩa tags/name, nhưng propagation scope cần cơ chế riêng.

## 22. Kiểm thử unit một custom convention

Không cần Kafka broker thật để unit test logic ánh xạ context thành KeyValues. Có thể tạo KafkaRecordReceiverContext từ một ConsumerRecord mẫu nếu constructor của Spring Kafka version khớp.

Ví dụ ý tưởng dựa trên Spring Kafka 3.3 API:

~~~java
@Test
void addsBoundedDomainTag() {

    ConsumerRecord<String, String> record =
        new ConsumerRecord<>(
            "orders.created",
            0,
            42L,
            "order-1001",
            "payload"
        );

    KafkaRecordReceiverContext context =
        new KafkaRecordReceiverContext(
            record,
            "orders-projection",
            "orders-client-0",
            "orders-projection-prod",
            () -> "test-kafka-cluster"
        );

    var convention = new OrdersListenerObservationConvention();

    KeyValues tags =
        convention.getLowCardinalityKeyValues(context);

    assertThat(tags).contains(
        KeyValue.of("app.domain", "orders")
    );
}
~~~

Ví dụ giả định JUnit/AssertJ và các imports phù hợp. Constructor có tham số clientId/groupId được bổ sung trong các Spring Kafka versions mới hơn; nếu project ở 3.0.x, cần dùng constructor có trong version đó.

### 22.1 Những trường hợp unit test cần có

- Topic hợp lệ nằm trong whitelist.
- Topic ngoài whitelist được map thành other.
- Header null.
- Header quá dài.
- Header chứa UTF-8 lỗi hoặc ký tự bất thường.
- Dynamic tag không dùng raw event ID.
- Default KeyValues vẫn được giữ khi gọi super.
- Exception trong convention không phát sinh vì dữ liệu bất thường.
- getContextualName ổn định cho cùng logical operation.

### 22.2 Không chỉ assert tags bổ sung

Ví dụ test không nên chỉ xác nhận app.domain=orders, mà còn kiểm tra những default semantic keys quan trọng không bị vô tình loại bỏ. Điều này giúp phát hiện lỗi khi developer override mà quên gọi super.

Tuy nhiên, tên keys mặc định có thể đổi giữa framework versions. Test phải được gắn với version đã chọn, không hardcode một contract không được framework version hỗ trợ.

## 23. Integration test với KafkaTemplate và listener container thật

Unit test convention chỉ chứng minh mapping function. Nó không chứng minh observationEnabled và convention đã được gắn đúng vào Kafka listener factory hoặc KafkaTemplate.

Nên dùng Embedded Kafka hoặc Testcontainers Kafka, một Spring ApplicationContext và ObservationRegistry có thể quan sát.

### 23.1 Listener Observation test

1. Khởi tạo listener container factory với observationEnabled=true.
2. Gắn OrdersListenerObservationConvention.
3. Start Kafka broker và listener.
4. Gửi một record hợp lệ vào orders.created.
5. Đợi listener xử lý record thật.
6. Đọc metrics/tracing observations đã được registry handlers ghi nhận.
7. Xác nhận app.domain=orders và app.pipeline=projection.
8. Xác nhận operation name/contextual name theo chính sách.
9. Kiểm tra listener ID có suffix khi concurrency > 1.
10. Xác nhận không bị double-count vì timers truyền thống.

### 23.2 KafkaTemplate Observation test

1. Tạo KafkaTemplate bật observationEnabled.
2. Gắn OrdersTemplateObservationConvention.
3. Gửi một ProducerRecord.
4. Đợi send future và observation hoàn tất theo framework lifecycle.
5. Xác nhận app.pipeline=publication.
6. Xác nhận destination semantic tags vẫn tồn tại.
7. Kiểm tra trace headers nếu tracing được bật và phù hợp.
8. Kiểm tra producer errors/aborts trong các test riêng.

### 23.3 End-to-end trace propagation test

1. Tạo một parent observation hoặc HTTP trace ở producer.
2. Gửi Kafka message với template observation.
3. Consumer dùng listener observation nhận message.
4. Thu spans bằng một in-memory test tracer hoặc test exporter.
5. Xác nhận trace relationships được kết nối khi propagation/sampling cho phép.
6. Xác nhận consumer không phụ thuộc vào payload có trace ID.
7. Tắt tracing bridge thử nghiệm để xác nhận Kafka business processing không bị hỏng.

### 23.4 Test với concurrent listeners

- Bật concurrency=3 với topic có ít nhất ba partitions.
- Cho các child containers nhận messages.
- Xem listener identity tags được tạo theo runtime.
- Bảo đảm custom tags không làm thay đổi consumer assignment hoặc group IDs.
- Xác nhận timer/tracing cardinality không tăng theo event ID.
- Kiểm tra không mất span khi consumer retry hoặc group rebalance.

### 23.5 Test migration observationEnabled

Nếu trước đó dùng micrometerEnabled:

- Ghi nhận meter name/tags của hệ thống cũ.
- Bật Observation trên canary.
- So sánh data schema đầu ra.
- Xác nhận Prometheus queries/alerts hoạt động.
- Xác nhận không ghi trùng metrics.
- Kiểm tra batch behavior theo Spring Kafka version.
- Bảo đảm trace context propagation đúng.

## 24. Khi metric có nhưng không thấy custom tags

Runbook:

1. Xác định @KafkaListener đang dùng containerFactory nào.
2. Kiểm tra factory.getContainerProperties().isObservationEnabled() hoặc effective property tương ứng.
3. Xác nhận setObservationConvention đã được gọi trên **đúng** ContainerProperties.
4. Nếu là producer, kiểm tra KafkaTemplate thực sự dùng bean nào.
5. Xác nhận convention bean được Spring tạo và không bị customizer khác thay thế.
6. Kiểm tra version Spring Kafka có API tương ứng không.
7. Xác nhận Observations thực sự được tạo: listener nhận records và template gửi messages.
8. Kiểm tra MeterRegistry/ObservationRegistry, handlers và backend.
9. Inspect actual KeyValues và metric tags; không đoán tag names.
10. Nếu dùng batch listener, kiểm tra batch Observation support theo version.
11. Nếu custom getLowCardinalityKeyValues trả empty hoặc thiếu super, sửa convention.
12. Kiểm tra MeterFilter/ObservationFilter có xóa hoặc rename tags không.

**Đừng sửa Kafka group ID hay reset offsets** để giải quyết việc thiếu tags. Đây là vấn đề instrumentation/wiring, độc lập với Kafka committed offsets.

## 25. Khi trace bị đứt giữa producer và consumer

Nếu thấy producer span nhưng consumer span không phải child/không cùng trace:

1. Xác nhận producer KafkaTemplate.observationEnabled=true.
2. Xác nhận consumer ContainerProperties.observationEnabled=true.
3. Kiểm tra tracing bridge và ObservationHandlers.
4. Kiểm tra propagation format được hai services hỗ trợ.
5. Inspect Kafka record headers tại test environment phù hợp.
6. Xác nhận các serializers/interceptors không loại bỏ headers.
7. Kiểm tra consumer còn sử dụng cùng record headers khi converter chạy.
8. Kiểm tra sampler; span có thể không được export dù đã được tạo.
9. Kiểm tra context propagation qua async executor.
10. Kiểm tra exporter/collector/network.
11. Kiểm tra ObservationConvention có override sai getName/getContextualName không, nhưng không coi đó là nguyên nhân duy nhất.
12. Thử producer/consumer tối giản với in-memory tracing để cô lập lỗi.

Đừng tự chèn Kafka headers bằng mã tùy tiện để “sửa nhanh” tracing nếu chưa hiểu propagation contract.

## 26. Khi metrics backend quá tải do cardinality

Dấu hiệu:

- Số Prometheus series tăng mạnh sau rollout convention mới.
- Memory/CPU của metrics collector tăng.
- Scrape duration hoặc remote write latency tăng.
- Dashboard queries timeout.
- MeterRegistry heap tăng.
- Tracing backend nhận quá nhiều attributes khác nhau.

Quy trình xử lý:

1. Xác định convention vừa thay đổi.
2. Liệt kê tags và số giá trị distinct.
3. Tìm eventId, orderId, key, offset, client UUID hoặc exception message bị đặt nhầm vào low-cardinality.
4. Roll back convention hoặc thay giá trị thành một category whitelist.
5. Kiểm tra có duplicate metric schema do Observation và Timer configuration không.
6. Giảm histogram buckets hoặc phạm vi publish nếu cần.
7. Thêm Metric/MeterFilter guard phù hợp.
8. Theo dõi series count sau rollout lại.
9. Cập nhật checklist review cho mọi custom observation tags.

Không xem cardinality explosion là vấn đề chỉ của Prometheus; nó bắt đầu từ cách tạo KeyValues ở producer/consumer và còn ảnh hưởng memory của application.

## 27. Khi một listener thành công nhưng business operation thất bại

Một listener có thể nuốt exception và return bình thường:

~~~java
@KafkaListener(topics = "orders.created")
public void handle(OrderCreated event) {

    try {
        projectionService.apply(event);
    }
    catch (Exception ex) {
        log.error("Projection failed", ex);
        // Không rethrow.
    }
}
~~~

Observation có thể ghi invocation success vì framework không thấy exception. Điều này không chứng minh database đã commit hoặc Kafka offset đã commit chính xác.

Nếu lỗi cần retry/rollback:

- Để exception propagate theo policy.
- Dùng DefaultErrorHandler hoặc transactional rollback policy phù hợp.
- Ghi business completion/recovery metrics riêng.
- Không thay đổi convention để “giả” một failure tag nếu lỗi đã bị nuốt ở nghiệp vụ.

Một custom convention chỉ đọc context tags; nó không thay thế error classification/recovery semantics.

## 28. Sự khác biệt giữa tags và span links

Trong Kafka, một consumer có thể nhận nhiều records, một record có thể được retry hoặc một batch có nhiều parent trace contexts. Không phải mọi trường hợp đều biểu diễn tốt bằng một quan hệ parent-child đơn giản.

Micrometer Tracing, OpenTelemetry và Spring Kafka có thể có các cơ chế span context/links tùy phiên bản và mode. ObservationConvention không phải nơi tự quyết định span link topology.

Nếu dùng batch listener, fan-in/fan-out hoặc asynchronous processing, cần đối chiếu tài liệu tracing integration riêng và test context propagation thực tế.

### 28.1 Không lấy event ID làm trace identity duy nhất

Event ID phục vụ business identity/idempotency. Trace ID phục vụ quan sát một execution path. Một event có thể được xử lý nhiều lần, tạo nhiều traces hoặc spans; đó không tự động là duplicate business event.

Nên log cả event ID và trace/span IDs khi policy cho phép, nhưng giữ chúng là hai khái niệm độc lập.

## 29. Version compatibility và API migration

Spring Kafka Observation support phụ thuộc phiên bản:

| Mốc hoặc dòng phiên bản | Điều cần chú ý |
|---|---|
| Trước 3.0 | Không áp dụng trực tiếp KafkaTemplate/Listener Observation API như 3.x |
| Từ 3.0 | KafkaTemplate và listener container hỗ trợ Micrometer Observation |
| Từ 3.0.6 | Custom conventions có thể dùng record từ observation context cho dynamic tags |
| Spring Kafka 3.2+ | Một số receiver context accessors như groupId/clientId được bổ sung |
| Spring Kafka 3.x | Batch observation support từng bị giới hạn; có thể fallback về timers truyền thống |
| Spring Kafka 4.x mới | Batch observation capabilities và semantic conventions có thể thay đổi; xem docs đúng minor version |

Không chỉ nhìn code sample từ bản latest rồi copy vào một dự án đang dùng 3.0.x. Đặc biệt kiểm tra:

- Package và method signatures của context/convention.
- setObservationEnabled() và setObservationConvention().
- ContextualName behavior.
- Low/high-cardinality default keys.
- Batch mode.
- ObservationRegistry integration.
- Tracing propagation format.
- KafkaAdmin cluster ID lookup.

### 29.1 Kafka cluster ID trong observation

Spring Kafka có thể sử dụng KafkaAdmin để lấy cluster ID và đặt remoteServiceName cho sender/receiver observation contexts trong các phiên bản hỗ trợ. Nếu môi trường giới hạn quyền describeCluster, metadata này có thể không có hoặc cần cấu hình cluster ID thủ công theo API của version.

Điều này có thể ảnh hưởng cách tracing backend hiển thị remote service, nhưng không nên làm listener không xử lý business records chỉ vì một enrichment field không khả dụng.

Không dùng cluster ID làm user-facing business identifier. Đây là metadata của hạ tầng.

## 30. Checklist thiết kế ObservationConvention

**Chọn instrumentation**

- [ ] Đã xác định dùng Micrometer timers truyền thống hay Micrometer Observation.
- [ ] observationEnabled=true trên đúng KafkaTemplate hoặc listener factory.
- [ ] Có ObservationRegistry, metrics/tracing handlers và exporter phù hợp.
- [ ] Biết batch listener support theo Spring Kafka version.
- [ ] Không bỏ cấu hình reliability khi thêm instrumentation.

**Convention code**

- [ ] Dùng đúng KafkaListenerObservationConvention hoặc KafkaTemplateObservationConvention.
- [ ] Ưu tiên kế thừa default convention và gọi super.
- [ ] Giữ operation name ổn định.
- [ ] getContextualName ngắn gọn, không chứa per-record IDs.
- [ ] Low-cardinality tags có tập giá trị hữu hạn.
- [ ] High-cardinality tags tuân thủ privacy/security/retention.
- [ ] Không parse payload lớn hoặc gọi external systems trong convention.
- [ ] Có null-safe fallback và mapping whitelist.
- [ ] Không duplicate semantic keys của framework.
- [ ] Có policy chống tag collision và cardinality explosion.

**Tracing**

- [ ] KafkaTemplate sender observation hoạt động.
- [ ] Listener receiver observation hoạt động.
- [ ] Trace headers/propagators tương thích giữa services.
- [ ] Sampler và exporter phù hợp.
- [ ] Async work có context propagation khi cần.
- [ ] Không đưa PII/secrets vào baggage hoặc tags.
- [ ] Không coi trace là durable business audit.

**Verification và vận hành**

- [ ] Có unit test KeyValues/contextual name.
- [ ] Có integration test với KafkaTemplate và listener thật.
- [ ] Có test concurrency và retry.
- [ ] Có test header missing/invalid/unknown values.
- [ ] Có test batch flow nếu dự án dùng batch.
- [ ] Đã inspect actual metrics/traces trước khi đổi dashboard.
- [ ] Có monitoring series cardinality và tracing ingestion.
- [ ] Có runbook cho missing tags, broken propagation và high-cardinality incident.

## 31. Tài liệu tham khảo

Các tài liệu chính thức nên đối chiếu với **Spring Kafka version của dự án**:

- Spring Kafka — Monitoring / Micrometer Observation: https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html
- Spring Kafka — Micrometer Observation Documentation: https://docs.spring.io/spring-kafka/reference/appendix/micrometer.html
- Spring Kafka API — KafkaListenerObservationConvention: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/micrometer/KafkaListenerObservationConvention.html
- Spring Kafka API — KafkaTemplateObservationConvention: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/micrometer/KafkaTemplateObservationConvention.html
- Spring Kafka API — KafkaRecordReceiverContext: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/micrometer/KafkaRecordReceiverContext.html
- Spring Kafka API — KafkaRecordSenderContext: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/micrometer/KafkaRecordSenderContext.html
- Micrometer Documentation — Observation: https://docs.micrometer.io/micrometer/reference/observation.html

## 32. Kết luận

**ObservationConvention** là nơi chuẩn hóa cách một Kafka operation được **đặt tên và gắn KeyValues** trong Micrometer Observation. Với Spring Kafka, dùng **KafkaListenerObservationConvention** cho receiver và **KafkaTemplateObservationConvention** cho sender; custom convention nên ưu tiên kế thừa default implementations, giữ semantic tags sẵn có và chỉ bổ sung các attributes có cardinality phù hợp.

Điểm phân biệt sống còn là: **low-cardinality tags dùng để tổng hợp metrics**, còn **high-cardinality tags có thể phục vụ trace detail nhưng vẫn phải có privacy/cost policy**. ObservationConvention không tự bật observation, không tự thiết lập tracing propagation, không thực hiện Kafka error recovery và không thay thế business correctness metrics. Một triển khai production đáng tin cậy phải gắn convention đúng container/template, cấu hình ObservationRegistry và tracing bridge phù hợp, kiểm tra API theo version, đo cardinality và xác minh bằng integration test từ producer tới consumer.

