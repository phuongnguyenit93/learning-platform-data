# micrometerTags

Trong vận hành Spring Kafka, câu hỏi “listener xử lý chậm ở đâu?” thường không thể trả lời chỉ bằng một con số consumer lag. Cùng một ứng dụng có thể có nhiều listener, consumer group, luồng nghiệp vụ và kiểu workload. Nếu mọi thời gian xử lý chỉ được ghi vào một metric chung, dashboard khó xác định **luồng nào đang chậm, lỗi xảy ra ở đâu và bản phát hành nào bị ảnh hưởng**.

Spring Kafka tích hợp Micrometer để đo thời gian thực thi listener. Thuộc tính **`micrometerTags`** cho phép thêm các **nhãn (tags) tĩnh** vào timer do listener container ghi nhận. Các nhãn như `service=order-processing`, `pipeline=orders`, `workload=consumer` giúp lọc và tổng hợp dữ liệu trong Micrometer, Prometheus hoặc hệ thống monitoring khác. Bên cạnh đó, một số phiên bản Spring Kafka hỗ trợ `micrometerTagsProvider` để xác định tags theo từng `ConsumerRecord`.

Điểm quan trọng: `micrometerTags` là **cấu hình telemetry**, không thay đổi Kafka consumer group, offset commit, retry, dead letter hoặc semantics xử lý. Đặt tag đúng làm cho metric dễ quan sát; đặt tag tùy ý theo `eventId`, `orderId` hoặc payload có thể làm số lượng time series tăng mất kiểm soát. Bài học tập trung vào cấu hình, phạm vi tác động và cách vận hành an toàn.

## 1. Micrometer timer của Spring Kafka đo điều gì?

Khi Micrometer có trên classpath và listener container được cấu hình phù hợp, Spring Kafka có thể ghi timer cho thời gian gọi listener. Tên meter thường gặp là **`spring.kafka.listener`**. Timer cung cấp các thông tin như số lần gọi, tổng thời gian, thời gian tối đa trong cửa sổ đo và, khi được cấu hình, histogram/percentile.

```text
Kafka topic orders
        |
        v
KafkaConsumer.poll()
        |
        v
Spring Kafka listener container
        |
        +--> @KafkaListener.process(record)
        |                |
        |                +--> business logic / DB / HTTP
        |                |
        |                v
        |          trả về hoặc ném exception
        |
        +--> Micrometer timer
                   |
                   +--> duration
                   +--> result/exception tags do framework cung cấp
                   +--> micrometerTags do ứng dụng cấu hình
```

**Timer listener không đồng nghĩa thời gian end-to-end của một record.** Nó thường đo phần thực thi listener, không bao gồm toàn bộ thời gian nằm trong Kafka log trước khi được poll, thời gian chờ ở retry topic, thời gian producer gửi tới broker, hay mọi thao tác commit offset sau đó. Phạm vi chính xác phụ thuộc phiên bản Spring Kafka và listener mode.

Các nhãn do framework tự thêm có thể gồm định danh listener/container, kết quả thành công/thất bại và thông tin exception; tên và tập nhãn cụ thể cần kiểm tra trên meter thực tế của phiên bản đang dùng. `micrometerTags` bổ sung nhãn mang ý nghĩa vận hành của **ứng dụng**, không thay thế việc framework tự phân biệt thành công và thất bại.

## 2. `micrometerTags` là map nhãn tĩnh

`ContainerProperties` của Spring Kafka có setter để khai báo một map `String -> String` cho Micrometer timers:

```java
factory.getContainerProperties().setMicrometerTags(
        Map.of(
                "service", "order-processing",
                "pipeline", "orders",
                "environment", "production"));
```

Những giá trị này **không thay đổi theo từng record**. Mọi lần gọi listener thuộc container sử dụng cấu hình này đều có thể được gắn chung những nhãn bổ sung, trong trường hợp Micrometer timer đang được bật.

| Tag tĩnh | Ví dụ | Tại sao hữu ích? |
|---|---|---|
| `service` | `order-processing` | Lọc metric theo service chịu trách nhiệm |
| `pipeline` | `orders` | Tách nghiệp vụ orders khỏi payments hoặc inventory |
| `environment` | `production` | Phân biệt môi trường nếu metrics được tổng hợp tập trung |
| `team` | `fulfillment` | Ánh xạ ownership và cảnh báo |
| `component` | `kafka-listener` | Phân biệt listener latency với HTTP handler latency |

Những tag này có số giá trị tương đối nhỏ và ổn định, nên thường phù hợp cho metric. Một tag `service` có 15 giá trị có thể chấp nhận được; một tag `order_id` có hàng triệu giá trị sẽ tạo rất nhiều time series và là một sai lầm thiết kế.

Không đặt các key trùng với **tag nội bộ của listener timer** như tag kết quả hoặc định danh meter mà không hiểu rõ quy tắc merge. Một tên tag ứng dụng có thể làm mất khả năng phân tích hoặc tạo kết quả khó dự đoán nếu xung đột với tag framework.

## 3. Điều kiện để `micrometerTags` xuất hiện trên metric

Chỉ thêm `setMicrometerTags(...)` chưa bảo đảm monitoring backend có dữ liệu. Cần cả cơ chế tạo timer và một `MeterRegistry` phù hợp.

Trong các dòng Spring Kafka có Micrometer timer support, listener container có thuộc tính `micrometerEnabled`. Timer thường được bật mặc định khi Micrometer hiện diện và có `MeterRegistry` phù hợp, nhưng behavior còn phụ thuộc framework version, cấu hình context và chế độ Observation. Có thể đặt tường minh:

```java
ContainerProperties properties = factory.getContainerProperties();
properties.setMicrometerEnabled(true);
properties.setMicrometerTags(Map.of("pipeline", "orders"));
```

Một ứng dụng Spring Boot muốn xuất Prometheus metrics thường cần các dependency và cấu hình quan sát tương ứng, ví dụ Micrometer registry Prometheus và Spring Boot Actuator. Cần cấu hình endpoint exposure và cơ chế xác thực theo chính sách vận hành. Không mở public metrics endpoint chứa thông tin topology hoặc nội dung nhạy cảm mà không có kiểm soát truy cập.

Khi listener chưa nhận record, timer có thể **chưa có mẫu để thống kê**. Không thấy một series cụ thể ngay sau khi khởi động chưa đủ kết luận `micrometerTags` đã bị bỏ qua. Cần phát record thử hoặc quan sát listener có traffic thực tế.

## 4. Ví dụ cấu hình container factory đầy đủ

Giả sử service xử lý sự kiện đơn hàng bằng `@KafkaListener`. Cấu hình dưới đây minh họa tags tĩnh trên một factory dành riêng cho luồng này:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;

@Configuration
public class OrdersListenerConfiguration {

    @Bean("ordersKafkaListenerContainerFactory")
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        ContainerProperties properties = factory.getContainerProperties();
        properties.setAckMode(ContainerProperties.AckMode.RECORD);
        properties.setMicrometerEnabled(true);
        properties.setMicrometerTags(Map.of(
                "service", "order-processing",
                "pipeline", "orders",
                "component", "kafka-listener"));

        return factory;
    }
}
```

Listener chỉ định factory tương ứng:

```java
@Component
public class OrdersListener {

    private final OrderService orderService;

    public OrdersListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders",
            groupId = "order-service",
            containerFactory = "ordersKafkaListenerContainerFactory")
    public void onOrder(OrderEvent event) {
        orderService.processIdempotently(event);
    }
}
```

`OrderEvent` và `OrderService` là class ứng dụng giả định; consumer factory phải được cấu hình serializer/deserializer, Kafka bootstrap, authentication và các thuộc tính cần thiết. Ví dụ chỉ làm rõ cấu hình `micrometerTags`; nó không tự cung cấp retry/error handler, idempotency hoặc quy tắc DLT.

Với `concurrency=3`, factory có thể tạo nhiều child consumer containers. Tags tĩnh được dùng cho các listener containers tạo từ factory; muốn phân tích từng child cần dựa vào các nhãn/identifier do framework cung cấp và cấu hình runtime. Không tạo tag tùy ý dựa trên random thread ID cho mỗi record.

## 5. Scope: một factory có thể phục vụ nhiều listener

Một điểm vận hành dễ nhầm là **tags đặt trên factory được dùng cho các container do factory tạo ra**. Nếu cùng `ordersKafkaListenerContainerFactory` được sử dụng cho cả listener orders và payments, tất cả có thể nhận tag `pipeline=orders`, khiến số liệu payments bị gắn nhãn sai.

Ví dụ cấu hình không nên dùng:

```java
// Một factory có tag pipeline=orders
@KafkaListener(
        topics = "orders",
        containerFactory = "ordersKafkaListenerContainerFactory")
public void processOrder(OrderEvent event) { /* ... */ }

// Không nên dùng factory đó cho một nghiệp vụ khác
@KafkaListener(
        topics = "payments",
        containerFactory = "ordersKafkaListenerContainerFactory")
public void processPayment(PaymentEvent event) { /* ... */ }
```

Ví dụ bỏ qua chi tiết kiểu generic để làm rõ nguy cơ gắn nhãn. Nếu nhiều listener có nghiệp vụ độc lập, có thể tạo **factory riêng** cho mỗi nhóm workload hoặc dùng nhãn tĩnh ở mức service chung và dựa vào container identifier để phân biệt listener. Không lạm dụng factory riêng chỉ để thêm một tag khi điều đó khiến hàng loạt cấu hình consumer không còn đồng bộ; hãy chọn mô hình phù hợp với quy mô codebase.

Các bước triển khai ổn định thường là: xác định ranh giới quan sát (service, listener, pipeline); định nghĩa tag vocabulary; đặt tags ở scope không khiến dữ liệu bị gắn nhãn sai; xác minh metric sau khi traffic chạy qua listener.

## 6. `micrometerTagsProvider`: tags dựa trên từng record

Ngoài map tĩnh, các phiên bản Spring Kafka hỗ trợ `micrometerTagsProvider` cho phép cung cấp tags dựa trên **`ConsumerRecord` đang được xử lý**. Khác với `micrometerTags`, provider có thể đọc header, topic, key hoặc metadata record để quyết định nhãn. Tính linh hoạt này cũng tạo rủi ro **cardinality explosion**.

Một cách dùng hợp lý là chuẩn hóa event type thành một tập nhỏ như `created`, `cancelled`, `updated`, `other`. Không xuất toàn bộ giá trị header tùy ý thành tag.

```java
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;

public final class SafeKafkaTags {

    private SafeKafkaTags() { }

    public static Map<String, String> fromRecord(
            ConsumerRecord<?, ?> record) {

        Header header = record.headers().lastHeader("event-type");
        if (header == null || header.value() == null) {
            return Map.of("event_family", "other");
        }

        String value = new String(
                header.value(), StandardCharsets.UTF_8);

        String family;
        switch (value) {
            case "OrderCreated":
                family = "created";
                break;
            case "OrderCancelled":
                family = "cancelled";
                break;
            case "OrderUpdated":
                family = "updated";
                break;
            default:
                family = "other";
        }

        return Map.of("event_family", family);
    }
}
```

Gắn provider vào container factory trong phiên bản hỗ trợ API này:

```java
ContainerProperties properties = factory.getContainerProperties();

properties.setMicrometerTags(
        Map.of("service", "order-processing", "pipeline", "orders"));

properties.setMicrometerTagsProvider(SafeKafkaTags::fromRecord);
```

Provider trên luôn trả về một giá trị trong tập nhỏ, kể cả khi producer gửi giá trị bất thường. Đây là cơ chế **allowlist**, không phải chỉ escape ký tự header. Nếu code trả thẳng `new String(header.value())`, một producer lỗi có thể tạo hàng triệu tag values và khiến hệ thống monitoring bị quá tải.

Tính năng tags theo từng record và phạm vi áp dụng cho record/batch listeners cần kiểm tra theo phiên bản Spring Kafka đang dùng. Với batch listener, đừng giả định một callback provider được gọi riêng cho từng record trong batch nếu chưa xác nhận behavior và API. Nếu cần metric theo record trong batch, có thể instrument tại application layer theo thiết kế riêng.

## 7. Nhãn tĩnh và nhãn động nên được chọn khác nhau

| Đặc tính | `micrometerTags` | `micrometerTagsProvider` |
|---|---|---|
| Nguồn giá trị | Cấu hình container/factory | Metadata của `ConsumerRecord` |
| Thời điểm biết giá trị | Khi xây dựng container | Khi xử lý record |
| Ví dụ phù hợp | `service=orders`, `team=checkout` | `event_family=created` từ allowlist |
| Rủi ro cardinality | Thường thấp nếu map có giá trị cố định | Cao nếu lấy key/header/payload không kiểm soát |
| Chi phí | Tương đối ổn định | Có thể tạo nhiều series/timer theo tổ hợp tag |
| Scope | Các record do container xử lý | Từng record thuộc listener support tương ứng |

**Ưu tiên tag tĩnh** khi cùng một nhãn mô tả toàn bộ listener. Chỉ dùng provider nếu câu hỏi vận hành thật sự cần phân tích theo một thuộc tính record có **số giá trị nhỏ, ổn định và không nhạy cảm**. Những trường như tenant ID, user ID hoặc order ID thường nên nằm trong structured log/trace, không nằm trong metric tags.

Khi `micrometerTagsProvider` thay đổi tập tag values theo thời gian, mỗi tổ hợp có thể tương ứng một meter/time series. Kể cả nếu các record chỉ xuất hiện một lần, series vẫn có thể tồn tại trong registry/backend trong một khoảng thời gian; việc không thấy biến cố ngay trong JVM không bảo đảm hệ thống monitoring không bị tăng chi phí lưu trữ.

## 8. Cardinality explosion: một ví dụ cụ thể

Giả sử service xử lý 100.000 đơn hàng mỗi giờ và thêm tag `order_id` lấy từ Kafka key:

```java
// KHÔNG NÊN: mỗi record có thể tạo một tag value khác nhau.
properties.setMicrometerTagsProvider(record ->
        Map.of("order_id", String.valueOf(record.key())));
```

Nếu mỗi `order_id` khác nhau, đã có thể có 100.000 tổ hợp tag chỉ trong một giờ. Khi timer còn có các nhãn như container, `result`, `exception`, môi trường hoặc replica, số series có thể tăng thêm theo tích số các chiều đó. Metric backend có thể phải lưu hàng triệu time series, làm query chậm, tăng bộ nhớ, chi phí và nguy cơ mất dữ liệu monitoring.

```text
Số series tiềm năng ≈
  số container/instance
  × số result/exception combinations
  × số tag values event family
  × các tag dimensions bổ sung
```

Ước lượng này là cận thiết kế, không phải lời khẳng định mọi tổ hợp chắc chắn sẽ được tạo. Nhưng nó giúp thấy tại sao **mỗi nhãn mới phải được review về cardinality**.

Những tag sau thường **không phù hợp**:

- `order_id`, `payment_id`, `event_id`, `request_id`, `correlation_id`.
- Kafka offset hoặc message timestamp thô.
- Payload JSON, exception message, SQL query có tham số.
- Full URL với path parameter hoặc query string chứa ID.
- Tenant/user ID không có số lượng được giới hạn rõ.

Khi cần truy vết một đơn hàng cụ thể, hãy đưa ID vào **structured logs/traces** cùng topic-partition-offset, không phải vào metric labels.

## 9. Tag nào có thể dựa trên metadata Kafka?

Các thuộc tính Kafka có nhiều mức cardinality khác nhau:

| Thuộc tính | Có phù hợp làm metric tag? | Ghi chú |
|---|---|---|
| Service/application name | Thường có | Giá trị hữu hạn trong một hệ thống |
| Listener ID | Thường có, nếu giới hạn | Có thể đã được framework gắn qua tag nội bộ |
| Topic name | Có điều kiện | Có thể hợp lý với tập topic hữu hạn; dynamic topic name cần kiểm soát |
| Partition number | Có điều kiện | Số lượng hữu hạn nhưng nhân series theo nhiều dimension |
| Consumer group | Có điều kiện | Group theo deploy/tenant động dễ tăng cardinality |
| Event type từ enum hữu hạn | Thường có | Dùng allowlist; map unknown về `other` |
| Event key | Thường không | Thường chính là business identifier |
| Offset | Không | Tăng liên tục, cực kỳ high cardinality |
| Exception class | Có điều kiện | Framework có thể đã cung cấp; không đưa exception message |

Không nên sao chép các tag như `topic`, `partition`, `name`, `result` nếu Micrometer timer đã ghi cùng ý nghĩa. Hãy quan sát tag hiện có bằng registry hoặc endpoint metrics trước khi thiết kế map bổ sung. Tên tag và cách chuẩn hóa label có thể khác theo phiên bản hoặc monitoring exporter.

## 10. Cùng một tên metric, nhiều time series

Micrometer mô hình hóa meter bằng **tên + tập tags**. Hai listener cùng ghi `spring.kafka.listener` nhưng có tag khác nhau sẽ tạo các time series riêng. Điều này là chủ đích để quan sát độc lập, nhưng cũng có nghĩa tag vocabulary phải nhất quán.

Ví dụ:

```text
spring.kafka.listener
  service=order-processing
  pipeline=orders
  result=success

spring.kafka.listener
  service=order-processing
  pipeline=orders
  result=failure

spring.kafka.listener
  service=payment-processing
  pipeline=payments
  result=success
```

Đây là mô hình minh họa tag values; các tags mặc định thực tế của Spring Kafka có thể thêm `name`, `exception` hoặc nhãn khác. Khi tạo dashboard, không chỉ query `spring.kafka.listener` rồi cộng mọi thứ mà quên filter pipeline: tổng thể có thể che lấp một listener bị timeout.

Nếu bản triển khai đổi tag `pipeline` thành `flow` một cách tùy tiện, dashboard cũ có thể mất dữ liệu hoặc hiển thị hai tập series khác nhau. Xem metric tags như **một hợp đồng vận hành**: có naming convention, review thay đổi và kế hoạch dashboard migration.

## 11. Spring Kafka Micrometer timer khác Kafka client metrics

`micrometerTags` đang bàn trong bài chủ yếu liên quan tới instrumentation **listener container**. Nó không tự thêm nhãn vào mọi metric do Kafka client, broker hoặc producer exporter phát ra.

| Nguồn metric | Đo điều gì? | Ví dụ |
|---|---|---|
| Spring Kafka listener timer | Thời gian gọi listener/handler | `spring.kafka.listener` |
| Kafka consumer client metrics | Poll, fetch, records-lag, request latency, commit, rebalance | Metrics do Kafka client xuất qua JMX/Micrometer binder |
| Kafka producer client metrics | Batch, request, retries, error rate, buffer | Kafka producer metrics |
| Broker metrics | Under-replicated partitions, request queue, bytes in/out | Kafka broker/JMX exporter |
| Application custom metrics | DLT count, business throughput, inbox duplicate | Counter/timer/gauge do ứng dụng định nghĩa |

Nếu câu hỏi là “listener dành bao nhiêu thời gian gọi database?”, listener timer với tag pipeline có ích. Nếu câu hỏi là “consumer bị kẹt giữa hai lần `poll()`?”, cần Kafka client metrics, listener duration và lifecycle logs. Nếu câu hỏi là “DLT backlog đang tăng?”, cần DLT topic/group metrics hoặc application counter riêng.

Không coi `setMicrometerTags` là API để cấu hình broker metric tags hay native Kafka client `client.id`. Những đối tượng đó có đường cấu hình quan sát riêng.

## 12. Quan hệ với Micrometer Observation và tracing

Các phiên bản Spring Kafka mới hỗ trợ **Micrometer Observation** để kết hợp metrics và distributed tracing. `ContainerProperties` có thể có tùy chọn `observationEnabled`; với Observation được bật, instrumentation sử dụng observation conventions và thường thay thế việc tạo listener Micrometer timers kiểu cũ.

```java
ContainerProperties properties = factory.getContainerProperties();

// Lựa chọn instrumentation dựa trên version và thiết kế tracing.
properties.setObservationEnabled(true);
```

Điểm quan trọng: **`micrometerTags` của timer cũ không phải cơ chế tổng quát để thêm tags cho mọi Observation/span**. Nếu service bật Observation, cần kiểm tra metric name, tags và tracing context do observation convention hiện hành cung cấp. Việc tùy biến low-cardinality observation keys thường thực hiện bằng observation convention phù hợp, không chỉ tiếp tục thêm `setMicrometerTags` rồi kỳ vọng exporter nhận tất cả.

Do tên meter/tag và hỗ trợ Observation thay đổi theo Spring Kafka/Micrometer versions, hãy xác nhận thực tế trên `/actuator/metrics`, registry test hoặc monitoring backend. Không đồng thời bật nhiều cách instrument cùng một listener mà không kiểm tra trùng lặp hoặc thay đổi nhãn.

### Metrics không phải tracing

Metric trả lời những câu hỏi tổng hợp như tỷ lệ lỗi hoặc latency p95 theo service. Trace giúp theo dõi một request/event riêng qua các service. Khi cần biết một `event_id` cụ thể bị chậm ở đâu, dùng trace/span links và logs chứa event ID, không tạo `event_id` thành metric label.

## 13. Producer-side Micrometer tags có phạm vi khác

Spring Kafka cũng có cơ chế Micrometer timer cho hoạt động send của `KafkaTemplate` ở các phiên bản hỗ trợ, với cấu hình tags phía producer riêng. Không nên nhầm `ContainerProperties.setMicrometerTags` với cấu hình tags của producer template.

```text
KafkaTemplate.send()  --> producer send timer / observation
                              |
                              +--> producer-side tags

@KafkaListener method --> listener container timer / observation
                              |
                              +--> ContainerProperties.micrometerTags
```

Một event đi qua cả producer và consumer có thể được đo ở hai đầu, nhưng hai timers không cộng lại thành end-to-end latency vì còn broker storage, network, consumer polling và các hàng đợi. Khi cần đo age của record hoặc end-to-end latency, hãy thiết kế timestamp và telemetry riêng với đồng hồ/clock skew được kiểm soát.

Nếu ứng dụng tùy biến `KafkaTemplate` metrics, hãy kiểm tra API thực tế của phiên bản Spring Kafka và tránh đưa key/payload động thành tags. Vẫn ưu tiên tag hữu hạn như `pipeline` hoặc `message_family`.

## 14. Xuất metrics ra Prometheus và đọc đúng timer

Với Micrometer Prometheus registry, timer `spring.kafka.listener` có thể được xuất dưới dạng series theo quy ước tên của Prometheus, ví dụ một họ metric có hậu tố `_seconds_count`, `_seconds_sum` và các series liên quan. Tên chính xác phụ thuộc Micrometer/registry/exporter và cấu hình histogram.

Ví dụ biểu thức PromQL **minh họa**, cần xác nhận tên đã xuất trên môi trường:

```promql
# Số lần gọi listener thành công mỗi giây, gom theo pipeline
sum by (pipeline) (
  rate(spring_kafka_listener_seconds_count{result="success"}[5m])
)
```

```promql
# Thời gian trung bình của listener (giây/lần) theo pipeline
sum by (pipeline) (
  rate(spring_kafka_listener_seconds_sum[5m])
)
/
sum by (pipeline) (
  rate(spring_kafka_listener_seconds_count[5m])
)
```

Biểu thức thời gian trung bình cần xử lý trường hợp mẫu số bằng 0 trong dashboard. Nó không phải p95 hoặc p99. Nếu muốn phân vị đáng tin cậy trên nhiều instance, cần cấu hình distribution histogram/SLO buckets phù hợp và dùng histogram queries thay vì tổng hợp trực tiếp local percentile đã tính trên từng pod.

```promql
# Ví dụ p95 chỉ dùng được nếu histogram bucket tương ứng tồn tại
histogram_quantile(
  0.95,
  sum by (le, pipeline) (
    rate(spring_kafka_listener_seconds_bucket[5m])
  )
)
```

Không mặc định `_bucket` xuất hiện chỉ vì timer tồn tại: histogram buckets phải được cấu hình trong Micrometer/Spring Boot distribution settings. Với lỗi nghiệp vụ, cũng cần dùng metric rõ nghĩa cho số record được recover/DLT, thay vì suy luận toàn bộ từ timer `result=failure`.

## 15. Micrometer tags nên phục vụ những câu hỏi vận hành nào?

Một thiết kế tags tốt bắt đầu từ câu hỏi mà đội vận hành phải trả lời trong ca trực:

| Câu hỏi | Tags có thể cần | Metric bổ sung |
|---|---|---|
| Luồng nghiệp vụ nào chậm nhất? | `service`, `pipeline` | Listener p95/p99 latency |
| Sau deploy, lỗi tăng ở service nào? | `service`, `environment`, version hữu hạn | Error rate, deploy timeline |
| Event family nào gây latency cao? | `event_family` từ allowlist | Record count, processing duration |
| Một dependency chậm có làm consumer lag tăng? | `pipeline` | DB/HTTP latency, consumer lag |
| Retry storm ảnh hưởng nghiệp vụ nào? | `pipeline`, `service` | Retry attempts, retry-topic lag, DLT rate |

Nên chọn số lượng tag nhỏ vừa đủ cho dashboard và alert. Việc đưa mọi chiều phân tích vào một timer có thể tạo cross-product lớn. Nếu muốn phân tích chi tiết hàng trăm trạng thái nghiệp vụ, có thể cân nhắc metrics ở mức domain với các enum được chuẩn hóa hoặc dùng log analytics thay vì đẩy toàn bộ vào `micrometerTagsProvider`.

## 16. Multi-instance và aggregation

Một service Spring Kafka có thể chạy nhiều replicas, mỗi replica có listener concurrency khác nhau. Khi tất cả dùng cùng `pipeline=orders`, metrics backend có thể tổng hợp theo pipeline; tags hạ tầng như `instance`, `pod` thường do registry hoặc exporter gắn, không nhất thiết phải tự thêm vào `micrometerTags`.

```text
orders-service replica A  --> spring.kafka.listener, pipeline=orders
orders-service replica B  --> spring.kafka.listener, pipeline=orders
orders-service replica C  --> spring.kafka.listener, pipeline=orders
                                         |
                                         v
                                    Prometheus
                                         |
                                         v
                             sum by (pipeline) (...)
```

**Tính nhất quán quan trọng hơn độ chi tiết.** Nếu mỗi replica dùng một cách viết tag khác nhau như `orders`, `order`, `order-service`, dashboard sẽ phân tách sai một pipeline thành nhiều nhóm. Tag values nên đến từ cấu hình chuẩn hoặc enumeration được kiểm soát.

Không gắn container thread name ngẫu nhiên hoặc Kubernetes pod UID vào custom `micrometerTags` nếu backend đã có nhãn instance đủ dùng. Tag pod có thể có cardinality được quản lý ở tầng infrastructure nhưng trùng lặp nhiều cấp tag không giúp chẩn đoán tốt hơn.

## 17. Hiệu năng và các rủi ro khi dùng provider

`micrometerTagsProvider` được gọi trên đường xử lý telemetry của record listener. Vì vậy, hàm provider nên **thuần, nhanh và không blocking**:

```java
// NÊN: O(1), đọc một header và ánh xạ sang tập giá trị nhỏ.
properties.setMicrometerTagsProvider(SafeKafkaTags::fromRecord);

// KHÔNG NÊN: gọi database để quyết định metric label.
// properties.setMicrometerTagsProvider(record -> database.findTenant(...));
```

Không parse toàn bộ payload JSON cỡ lớn chỉ để tạo một tag, vì việc này làm tăng CPU và có thể phát sinh lỗi khi payload không hợp lệ. Không gọi network service từ provider. Không để một exception của telemetry làm hỏng listener nghiệp vụ; provider cần phòng ngừa input thiếu header, byte không phù hợp hoặc value ngoài allowlist.

Nếu record đến từ producer không đáng tin hoặc có headers tùy ý, giới hạn kích thước và giá trị được đưa vào metric. Nên xem mọi header là dữ liệu đầu vào chưa được kiểm chứng trước khi biến nó thành một label.

## 18. Kiểm thử Micrometer tags bằng `MeterRegistry`

Thay vì chỉ xem cấu hình, có thể kiểm tra **meter thực tế sau khi listener xử lý record**. Với môi trường kiểm thử Spring Boot, `SimpleMeterRegistry` là một registry gọn để quan sát metrics mà không cần backend ngoài.

Ý tưởng cấu hình trong test:

```java
@TestConfiguration
static class MetricsTestConfiguration {

    @Bean
    MeterRegistry testMeterRegistry() {
        return new SimpleMeterRegistry();
    }
}
```

Sau khi gửi một record hợp lệ và xác nhận listener đã xử lý xong, có thể lấy timer theo tên cùng tag ứng dụng:

```java
Collection<Timer> timers = registry
        .find("spring.kafka.listener")
        .tags("service", "order-processing")
        .tags("pipeline", "orders")
        .timers();

long invocations = timers.stream()
        .mapToLong(Timer::count)
        .sum();

assertThat(invocations).isGreaterThan(0);
```

Đây là phần kiểm thử minh họa: cần inject `MeterRegistry`, tạo Kafka test broker/producer, chờ listener xử lý bằng latch hoặc Awaitility, và bảo đảm application context không có registry khác làm thay đổi điều kiện instrumentation. Nếu Observation đang được bật, kiểm tra meter/tracing name thực tế thay vì cố khẳng định timer cũ luôn tồn tại.

Những trường hợp nên kiểm thử:

1. Record xử lý thành công: listener timer xuất hiện và có tags tĩnh đúng.
2. Listener ném exception: timer hoặc observation theo kết quả lỗi được ghi nhận theo cơ chế framework/version.
3. Hai listener khác pipeline: metrics không bị gắn nhãn nhầm do dùng chung factory.
4. Provider gặp header không xác định: trả `event_family=other`, không tạo tag raw header mới.
5. Batch listener: xác nhận chính xác cách ghi timer và phạm vi provider được phiên bản sử dụng.
6. Application Observation enabled: xác nhận metric name và labels trong pipeline telemetry đang dùng.
7. Restart/rebalance: số meter/tags không tăng bất thường do gắn nhãn runtime ID không ổn định.

Không chạy một test chỉ để khẳng định timer có mặt rồi bỏ qua `result`, `name` hoặc tag values thực tế. Cần đọc các meter IDs và tags do registry ghi nhận để biết instrumentation đã được cấu hình đúng.

## 19. Troubleshooting: `micrometerTags` không có tác dụng

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không thấy `spring.kafka.listener` | Micrometer chưa có registry phù hợp, timer bị tắt, chưa có record hoặc Observation thay thế timer cũ | Kiểm tra dependencies, registry, `micrometerEnabled`, `observationEnabled`, traffic |
| Có timer nhưng thiếu tags tùy chỉnh | Listener dùng container factory khác hoặc tags chưa được áp dụng | Kiểm tra annotation `containerFactory` và bean wiring |
| Tất cả listener đều có `pipeline=orders` | Dùng chung một factory có tags riêng của orders | Chọn scope tag phù hợp hoặc tách factory |
| Prometheus thấy hàng trăm nghìn series | Provider dùng event ID/key/tenant không giới hạn | Dừng phát sinh tags mới, dùng allowlist, xử lý stale series/retention theo monitoring backend |
| Metric chỉ có success, không có failure | Chưa tạo failure tương ứng hoặc error handling semantics khác | Kiểm tra kết quả listener/error handler và meter thực tế |
| Grafana query trả kết quả rỗng | Sai tên metric exporter, sai labels, histogram chưa bật hoặc filter không khớp | Dò tên series xuất thực tế trước khi viết PromQL |
| Tăng latency sau khi bật provider | Provider parse payload hoặc gọi IO, tạo meter liên tục | Chuyển sang map hằng/enum, bỏ IO, đo CPU và meter count |
| Tags không xuất hiện trong trace | `micrometerTags` dành cho timer, Observation có convention riêng | Kiểm tra observation configuration và low-cardinality keys |
| Sau deploy xuất hiện hai tập series | Đổi tên key/value hoặc mode Observation | Đặt chuẩn naming, cập nhật dashboard và migration plan |

Đối với sự cố “metric biến mất”, cần phân biệt ba tầng: **listener có xử lý record không**, **MeterRegistry có được cập nhật không**, và **exporter/backend có nhận được series không**. Nếu registry đã có timer và tags nhưng Prometheus không thấy, vấn đề nằm ở export/scrape/label filtering, không phải chỉ ở `setMicrometerTags`.

## 20. Quy trình triển khai tags an toàn

Đưa `micrometerTags` vào production nên theo một luồng có kiểm soát:

1. Xác định dashboard/alert cần trả lời câu hỏi gì; chọn tags tối thiểu cho đúng phạm vi.
2. Kiểm tra instrumentation hiện tại: Micrometer timer truyền thống hay Micrometer Observation, phiên bản Spring Kafka và registry.
3. Định nghĩa key naming convention thống nhất, ví dụ `service`, `pipeline`, `component`.
4. Đặt tags tĩnh ở container factory phù hợp; tránh gắn nhầm nhiều listener vào cùng pipeline.
5. Chỉ dùng provider khi thực sự cần dữ liệu theo record, và luôn chuẩn hóa sang một tập giá trị hữu hạn.
6. Kiểm thử record success/failure, đọc meter IDs và xác nhận tags trong registry.
7. Xem số lượng time series trước và sau thay đổi; đặt cảnh báo cardinality/memory cho monitoring backend.
8. Xuất metrics qua Actuator/Prometheus theo cơ chế được bảo vệ; xác nhận tên metric thực tế.
9. Triển khai dashboard/alert có filter và aggregation đúng, tránh label filtering gây mất dữ liệu.
10. Theo dõi hiệu năng listener, meter count, scrape latency và chi phí lưu trữ sau rollout.

Nếu một custom tag cần thay đổi tên hoặc semantics, coi đó là thay đổi hợp đồng monitoring. Cập nhật dashboard, recording rules, alert rules và runbook cùng với release ứng dụng, không chỉ đổi một chuỗi trong code.

## 21. Nguyên tắc cốt lõi

1. `micrometerTags` là **map tags tĩnh** bổ sung cho metrics listener container của Spring Kafka, không phải cấu hình Kafka broker hay consumer offset.
2. Khi dùng listener timers, tên meter thường gặp là `spring.kafka.listener`; xác minh tên/tags thực tế theo phiên bản.
3. Bật và nối đúng Micrometer registry; chỉ có setter tags không đảm bảo exporter xuất dữ liệu.
4. Đặt tags ở đúng **container factory** để tránh dán nhãn nhầm nhiều luồng nghiệp vụ.
5. `micrometerTagsProvider` cho phép tags theo record khi API được hỗ trợ, nhưng phải giới hạn giá trị bằng enum/allowlist.
6. Không đưa order ID, event ID, offset, payload hoặc exception message vào tags vì cardinality và quyền riêng tư.
7. Listener timer không thay thế Kafka client metrics, consumer lag, DLT metrics hay end-to-end tracing.
8. Khi bật Micrometer Observation, kiểm tra observation conventions và metric name; không giả định tags timer cũ tự chuyển sang trace.
9. Ưu tiên metric tags nhất quán trên mọi replica, có schema và quy trình migration rõ ràng.
10. Kiểm thử bằng `MeterRegistry`, quan sát series thực tế trên backend và theo dõi chi phí cardinality sau rollout.

**Kết luận:** `micrometerTags` giúp biến các listener timers chung thành thông tin có ngữ cảnh vận hành: service nào chậm, pipeline nào lỗi và nhóm nào chịu trách nhiệm. Giá trị thực sự đến từ một bộ tags **ít, ổn định, có ý nghĩa** và được đặt đúng scope. Kết hợp chúng với Kafka client metrics, consumer lag, retry/DLT monitoring và tracing sẽ cung cấp bức tranh reliability đầy đủ hơn mà không làm nổ số lượng time series hoặc ảnh hưởng tới đường xử lý record.
