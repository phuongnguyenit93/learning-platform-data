# micrometerTagsProvider trong Spring Kafka

Trong môi trường production, Spring Kafka consumer cần được quan sát ở nhiều tầng: khả năng poll của Kafka client, số lần listener được gọi, thời gian xử lý từng record, tỷ lệ exception, consumer lag, retry/DLT và tốc độ xử lý nghiệp vụ. **micrometerTagsProvider** là một điểm mở rộng cho phép ứng dụng **gắn thêm các Micrometer tags động dựa trên ConsumerRecord** lên listener timer.

Ví dụ: một listener xử lý nhiều loại sự kiện OrderCreated, OrderCancelled và OrderShipped. Thời gian xử lý trung bình của từng nhóm có thể rất khác nhau. Nếu mọi invocation chỉ được ghi vào cùng một metric timer, dashboard khó chỉ ra loại nào đang chậm. Với tag động event_family=created, cancelled hoặc shipped, có thể phân nhóm số lần và latency ngay trên metric listener.

Tuy nhiên, mỗi giá trị tag có thể tạo thêm một time series mới. Nếu lấy orderId, eventId hoặc Kafka key làm tag, số series có thể tăng đến hàng triệu và gây quá tải monitoring backend. Do đó, micrometerTagsProvider vừa là công cụ hữu ích, vừa là nơi phải kiểm soát **cardinality, hiệu năng và quyền riêng tư** rất chặt.

Bài học nằm trong chương **Monitoring và metrics** của module Spring Kafka Reliability Operations. Nội dung tập trung vào cơ chế, API ContainerProperties, cấu hình Spring Boot, ví dụ thực tế, quan hệ với Micrometer Timer và Observation, cùng cách vận hành an toàn.

## 1. Vị trí của micrometerTagsProvider trong pipeline

Một record đi từ Kafka broker tới listener method:

~~~text
Kafka broker
    |
    v
KafkaConsumer.poll()
    |
    v
ConsumerRecord<K, V>
    |
    v
Spring Kafka listener container
    |
    +--> Timer instrumentation
    |       |
    |       +--> Built-in tags
    |       +--> Static micrometerTags
    |       +--> Dynamic micrometerTagsProvider(record)
    |
    v
@KafkaListener
    |
    +--> Success
    |       |
    |       v
    |   Ghi nhận listener timer thành công
    |
    +--> Exception
            |
            v
        Ghi nhận listener timer lỗi
            |
            v
      Error handler / retry / DLT
~~~

Sơ đồ diễn tả nhiệm vụ của các thành phần. Chi tiết nội bộ về thời điểm lấy tags và việc tạo meter có thể thay đổi theo Spring Kafka version.

Provider **không xử lý record thay cho listener**. Nó không commit offset, gửi record sang DLT, đổi partition, thay đổi RetryTopicConfiguration hay điều khiển KafkaConsumer. Nó chỉ cung cấp metadata bổ sung cho listener metrics.

## 2. API cốt lõi trên ContainerProperties

Trong các phiên bản Spring Kafka hỗ trợ, ContainerProperties có setter cho dynamic tags provider:

~~~java
setMicrometerTagsProvider(
        Function<ConsumerRecord<?, ?>, Map<String, String>> provider
)
~~~

Chữ ký minh họa kiểu dữ liệu mà API tiếp nhận:

- **Input:** ConsumerRecord của Kafka client.
- **Output:** Map với tag key và tag value dạng String.
- **Mục đích:** bổ sung tags cho Micrometer listener timer.
- **Thời điểm:** trong vòng đời xử lý record của listener container.
- **Phạm vi:** container hoặc các container được tạo từ factory đã cấu hình.

Ví dụ ngắn:

~~~java
factory.getContainerProperties()
        .setMicrometerTagsProvider(record -> Map.of(
                "event_family",
                classifyTopic(record.topic())
        ));
~~~

Phương thức classifyTopic có trách nhiệm quy đổi topic thành một tập giá trị nhỏ, có kiểm soát.

Không nên gán provider vào một factory rồi giả định mọi listener của ứng dụng đều nhận cấu hình đó. Mỗi @KafkaListener có thể dùng containerFactory riêng. Cấu hình phải áp dụng trên **factory thực tế được listener sử dụng**.

## 3. Khác biệt giữa tag tĩnh, tag động và built-in tags

Spring Kafka có thể cung cấp ba nguồn tag cho timer:

| Loại tag | Nguồn dữ liệu | Ví dụ | Mục đích |
|---|---|---|---|
| Built-in tags | Listener instrumentation của framework | name, result, exception | Nhận diện listener và kết quả xử lý |
| Static tags | ContainerProperties.micrometerTags | service_area=orders | Phân loại theo ứng dụng/container |
| Dynamic tags | ContainerProperties.micrometerTagsProvider | event_family=cancelled | Phân loại theo ConsumerRecord |

Ví dụ kết hợp:

~~~java
ContainerProperties props = factory.getContainerProperties();

props.setMicrometerEnabled(true);

props.setMicrometerTags(Map.of(
        "service_area", "orders",
        "processing_mode", "record"
));

props.setMicrometerTagsProvider(record -> Map.of(
        "event_family", classifyTopic(record.topic())
));
~~~

Các tag tĩnh service_area và processing_mode không đổi theo mỗi record. Tag event_family có thể thay đổi theo topic hiện tại.

Không dùng cùng tag key ở cả static và dynamic maps, hoặc dùng các keys framework đã sở hữu như result và exception. Nếu nhiều nguồn cung cấp cùng key, quy tắc merge/overwrite có thể phụ thuộc implementation/version; tốt hơn hết là thiết kế các key không va chạm.

## 4. Listener timer đang đo điều gì?

Spring Kafka có thể tạo Micrometer Timer cho thời gian xử lý listener, thường dùng tên meter **spring.kafka.listener**. Những tags thường thấy tùy version gồm:

- **name:** listener/container name.
- **result:** success hoặc failure.
- **exception:** exception type hoặc giá trị đại diện khi không có lỗi.
- Những custom tags do ứng dụng cung cấp.

Ví dụ một điểm dữ liệu minh họa:

~~~text
Meter: spring.kafka.listener

name=ordersListener
result=success
exception=none
service_area=orders
processing_mode=record
event_family=created
~~~

Timer phản ánh listener invocation theo instrumentation của framework. Nó không trực tiếp đo:

- Consumer lag.
- Kafka broker request latency.
- Thời gian record chờ trong topic.
- Số business events duy nhất.
- Thời gian producer đến end-to-end kết quả.
- Số database transactions đã commit.
- DLT publish outcome.

Ví dụ, record đã nằm 10 phút trên Kafka do backlog rồi listener xử lý trong 25 ms. Listener Timer có thể ghi 25 ms, nhưng end-to-end event age vượt 10 phút. Hai con số khác nhau hoàn toàn.

## 5. Cấu hình Java đầy đủ với @KafkaListener

Ví dụ ứng dụng xử lý orders events:

~~~java
@Configuration
public class OrderKafkaMetricsConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);

        ContainerProperties properties =
                factory.getContainerProperties();

        properties.setMicrometerEnabled(true);

        properties.setMicrometerTags(Map.of(
                "service_area", "orders",
                "listener_type", "business"
        ));

        properties.setMicrometerTagsProvider(record -> Map.of(
                "event_family", classifyTopic(record.topic())
        ));

        return factory;
    }

    private static String classifyTopic(String topic) {
        return switch (topic) {
            case "orders.created" -> "created";
            case "orders.cancelled" -> "cancelled";
            case "orders.shipped" -> "shipped";
            default -> "other";
        };
    }
}
~~~

Listener dùng đúng factory:

~~~java
@Component
public class OrderEventListener {

    private final OrderService orderService;

    public OrderEventListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = {
                    "orders.created",
                    "orders.cancelled",
                    "orders.shipped"
            },
            groupId = "orders-service",
            containerFactory = "ordersListenerFactory"
    )
    public void onOrderEvent(OrderEvent event) {
        orderService.process(event);
    }
}
~~~

Trong project thực tế, cần imports tương ứng của Spring Kafka, Spring Framework và java.util.Map; OrderEvent, OrderService và consumer deserializer là các thành phần ứng dụng cần triển khai.

Kết quả phân loại:

| Topic của record | event_family |
|---|---|
| orders.created | created |
| orders.cancelled | cancelled |
| orders.shipped | shipped |
| Topic không nằm trong allowlist | other |

Dùng other thay vì trả nguyên tên topic khi không biết topic giúp hạn chế số series.

## 6. Khi một topic chứa nhiều event types

Nếu mọi order events ở cùng topic:

~~~text
orders.events
   |
   +--> OrderCreated
   +--> OrderCancelled
   +--> OrderShipped
   +--> OrderAddressChanged
~~~

Chỉ dùng record.topic() sẽ không phân biệt được event type. Có thể đọc một header theo event contract rồi ánh xạ tới một danh sách nhỏ các loại được phép.

Ví dụ:

~~~java
private static String classifyEventType(
        ConsumerRecord<?, ?> record) {

    Header header =
            record.headers().lastHeader("event-type");

    if (header == null || header.value() == null) {
        return "unknown";
    }

    String value = new String(
            header.value(),
            StandardCharsets.UTF_8
    );

    return switch (value) {
        case "OrderCreated" -> "created";
        case "OrderCancelled" -> "cancelled";
        case "OrderShipped" -> "shipped";
        default -> "other";
    };
}
~~~

Provider:

~~~java
properties.setMicrometerTagsProvider(record -> Map.of(
        "event_type",
        classifyEventType(record)
));
~~~

Cách này có các đặc điểm:

1. Không đọc lại toàn bộ JSON/Avro payload chỉ để phân loại.
2. Có fallback nếu header thiếu.
3. Có fallback nếu producer gửi event type không được hỗ trợ.
4. Không đưa raw header vào metric.
5. Các giá trị đều hữu hạn.
6. Có thể xử lý value null mà không dựa vào object domain.

Header có thể đến từ một producer không hoàn toàn đáng tin. **Không gắn raw header value làm metric tag**, kể cả khi header có tên event-type. Luôn dùng allowlist hoặc bucket mapping.

## 7. Cấu hình provider với hai dimensions hữu hạn

Có thể muốn phân biệt event family và processing lane:

~~~text
Topic orders.live   -> processing_lane=live
Topic orders.replay -> processing_lane=replay
Topic orders.retry  -> processing_lane=retry
Topic khác          -> processing_lane=other
~~~

Ví dụ:

~~~java
properties.setMicrometerTagsProvider(record -> Map.of(
        "event_type",
        classifyEventType(record),
        "processing_lane",
        classifyLane(record.topic())
));
~~~

Helper:

~~~java
private static String classifyLane(String topic) {
    return switch (topic) {
        case "orders.live" -> "live";
        case "orders.replay" -> "replay";
        case "orders.retry" -> "retry";
        default -> "other";
    };
}
~~~

Các giá trị nên được quản trị như một **contract observability**. Nếu thay đổi tên một tag hoặc đổi ý nghĩa retry/replay, dashboard và alert queries cũng có thể cần chỉnh sửa.

Đặc biệt, với non-blocking retry, tên các retry topics thực tế phụ thuộc RetryTopicConfiguration và version. Không cố parse hậu tố tùy ý từ mọi tên topic nếu topology chưa được xác nhận; dùng mapping dựa trên cấu hình đã quản lý.

## 8. Cardinality là rủi ro lớn nhất của dynamic tags

Một metric time series được phân biệt bằng **meter name và bộ tag key/value**. Mỗi giá trị mới của một tag có thể làm sinh thêm series.

Giả sử:

~~~text
event_type:       5 giá trị
processing_lane:  3 giá trị
listener:         4 giá trị
result:           2 giá trị

Số tổ hợp tiềm năng:
5 × 3 × 4 × 2 = 120
~~~

Nếu thêm tenant_id có 10.000 giá trị:

~~~text
120 × 10.000 = 1.200.000 tổ hợp tiềm năng
~~~

Đây chỉ là phép nhân mô hình minh họa. Số series thực tế còn phụ thuộc những tổ hợp được quan sát và số series phụ do count, sum, max hoặc histogram buckets tạo ra.

Tag cardinality quá cao có thể gây:

- Tăng memory của Micrometer MeterRegistry.
- Tăng kích thước response scrape.
- Tăng số series trong Prometheus hoặc monitoring backend.
- Tăng ingestion rate và chi phí lưu trữ.
- Tăng thời gian xử lý dashboard queries.
- Metrics bị drop do rate limits.
- Cảnh báo chậm hoặc không đủ dữ liệu.
- Biến instrumentation thành một nguyên nhân tăng áp lực JVM.

**Không dùng micrometerTagsProvider như kho lưu dữ liệu chi tiết của mọi record.** Muốn tìm event cụ thể, dùng log hoặc trace correlation.

## 9. Các field nên tránh làm tags

| ConsumerRecord field hoặc metadata | Vấn đề | Thay thế |
|---|---|---|
| record.offset() | Mỗi record có offset khác nhau | Log có topic/partition/offset |
| record.timestamp() | Rất nhiều giá trị theo thời gian | Đo event age bằng histogram |
| record.key() | Thường chứa user/order/customer ID | Event category hoặc tier |
| eventId | Gần như unique cho từng event | Tracing/log correlation |
| orderId/paymentId | High cardinality, có thể nhạy cảm | Business domain |
| customerId/tenantId thô | Có thể hàng nghìn hoặc hàng triệu values | Customer/tenant tier hữu hạn |
| Raw exception message | Chứa identifier và text thay đổi | Exception category |
| Header tự do do producer gửi | Không kiểm soát được số values | Allowlist mapping |
| Full class name từ type header | Có thể thay đổi không kiểm soát | Schema/event family |
| Kafka topic per tenant | Số topic tăng theo tenant | Topic group |
| Pod UID biến động sau deploy | Series churn | Stable service identity |

Một số giá trị trông ít cardinality lúc đầu nhưng sẽ tăng cùng lượng khách hàng hoặc tenant. Cần thiết kế policy dựa trên quy mô tương lai, không chỉ dữ liệu phát triển ban đầu.

## 10. Provider nên chạy nhanh, thuần và không có side effect

Một provider phù hợp:

~~~java
properties.setMicrometerTagsProvider(record -> {
    String family = switch (record.topic()) {
        case "orders.created" -> "created";
        case "orders.cancelled" -> "cancelled";
        default -> "other";
    };

    return Map.of("event_family", family);
});
~~~

Một provider không phù hợp:

~~~java
properties.setMicrometerTagsProvider(record -> {
    Customer customer = customerRepository.findById(
            String.valueOf(record.key())
    );

    return Map.of(
            "customer_name",
            customer.getName()
    );
});
~~~

Vấn đề của ví dụ thứ hai:

- Mỗi record tạo thêm database query chỉ để tạo tag.
- Khi database chậm, instrumentation làm listener chậm thêm.
- Khi DB mất kết nối, provider có thể ném exception.
- Customer name tạo nhiều series và có thể chứa dữ liệu nhạy cảm.
- Metric thu thập hiệu năng lại làm thay đổi hiệu năng đang đo.

Nguyên tắc thực tế:

1. Chỉ đọc metadata đang có.
2. Không gọi DB, HTTP, Redis, schema registry hay object storage.
3. Không parse payload lớn.
4. Không sleep hoặc acquire một lock kéo dài.
5. Không mutate record, key, value hay headers.
6. Không giữ ConsumerRecord reference sau khi provider trả về.
7. Không tạo tag key động.
8. Không để null tag values.
9. Có fallback unknown/other.
10. Không để exception của provider phá hỏng luồng instrumentation.

Map.of phù hợp với một số lượng tag nhỏ và immutable values. Nếu dùng một map mutable, không chia sẻ và sửa cùng object map qua nhiều consumer threads.

## 11. Tương tác với null value, tombstone và deserialization error

Không phải record nào cũng có payload object đầy đủ.

- Kafka tombstone là record có value null hợp lệ theo contract compacted topics.
- Key hoặc value có thể bị lỗi deserialization.
- Header có thể không tồn tại.
- Header value có thể rỗng.
- Event type có thể mới hơn mapping.
- Value có thể không cùng Java class giữa các topics.

Một helper phòng thủ:

~~~java
private static Map<String, String> tagsFor(
        ConsumerRecord<?, ?> record) {

    if (record == null) {
        return Map.of("event_type", "unknown");
    }

    Header header =
            record.headers().lastHeader("event-type");

    if (header == null || header.value() == null) {
        return Map.of("event_type", "unknown");
    }

    String type = new String(
            header.value(),
            StandardCharsets.UTF_8
    );

    return Map.of(
            "event_type",
            switch (type) {
                case "OrderCreated" -> "created";
                case "OrderCancelled" -> "cancelled";
                default -> "other";
            }
    );
}
~~~

Trong luồng bình thường framework cung cấp ConsumerRecord theo contract; nhánh null thể hiện cách làm helper bền vững khi được dùng ở nhiều nơi.

**Không dùng record.value()==null để quyết định tag deserialize_error.** Tombstone là một giá trị null hợp lệ. Nếu muốn phân biệt deserialization failure, cần dựa vào ErrorHandlingDeserializer metadata và đường xử lý lỗi thực tế.

Một số lỗi xảy ra trong KafkaConsumer.poll() trước khi record được tạo phù hợp để gọi listener. Do đó, **listener timer và micrometerTagsProvider có thể không được chạy cho những lỗi đó**. Cần metrics từ error handler, DLT, logs hoặc consumer metrics bổ sung.

## 12. Provider không biết kết quả xử lý listener

Một lỗi tư duy phổ biến là tự thêm:

~~~java
properties.setMicrometerTagsProvider(record -> Map.of(
        "result", "success"
));
~~~

Đây là giá trị được quyết định khi record đến, không phải kết quả của business logic. Nếu listener ném exception sau đó, custom result=success sẽ gây sai nghĩa hoặc xung đột với built-in result tag.

Provider phù hợp hơn với đặc tính **đã có của input record**. Với kết quả nghiệp vụ sau xử lý, dùng:

- Built-in listener timer result/exception tags.
- Custom MeterRegistry counter trong business service.
- DefaultErrorHandler/recoverer instrumentation.
- Observation convention nếu mục tiêu là context khác với timer cũ.
- Structured logs/traces cho failure details.

Ví dụ một counter nhóm lỗi nghiệp vụ:

~~~java
@Service
public class OrderFailureMetrics {

    private final MeterRegistry registry;

    public OrderFailureMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void incrementFailure(String reasonCode) {
        registry.counter(
                "orders.processing.failures",
                "reason",
                normalize(reasonCode)
        ).increment();
    }

    private static String normalize(String reasonCode) {
        return switch (reasonCode) {
            case "DB_TIMEOUT" -> "database";
            case "INVALID_EVENT" -> "validation";
            case "PARTNER_UNAVAILABLE" -> "dependency";
            default -> "other";
        };
    }
}
~~~

Các reasons phải có tập giá trị hữu hạn. Không gắn raw exception message, SQL query hoặc Kafka key vào counter.

## 13. Cần bật Micrometer listener timer đúng cách

Ví dụ:

~~~java
ContainerProperties properties =
        factory.getContainerProperties();

properties.setMicrometerEnabled(true);

properties.setMicrometerTagsProvider(
        record -> Map.of("event_family", classifyTopic(record.topic()))
);
~~~

Nếu listener timers không được bật hoặc Micrometer không có trong classpath, provider có thể không tạo ra metrics mong muốn.

Trong Spring Boot, dependency thường liên quan đến Actuator và registry export:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Đây là ví dụ Maven. Với Gradle, dùng dependencies tương ứng và để Spring Boot BOM quản lý versions phù hợp.

Có Micrometer Timer trong process **không có nghĩa metrics đã ra Prometheus**. Còn cần:

- Registry phù hợp.
- Endpoint exposure.
- Security/network restrictions.
- Prometheus scrape configuration.
- Labels từ application/target.
- Data retention và alert rules.

Không mở actuator/prometheus endpoint công khai mà không có kiểm soát quyền truy cập.

## 14. Cách đọc listener Timer

Micrometer Timer có thể ghi:

- **count:** số lần invocation được đo.
- **total time:** tổng thời gian.
- **max:** maximum trong cửa sổ thống kê theo registry.
- **histogram/percentiles:** khi đã bật tính năng phù hợp.

Một meter minh họa:

~~~text
spring.kafka.listener
  name=ordersListener
  result=success
  exception=none
  service_area=orders
  event_family=cancelled
~~~

Nếu 100 invocation của event_family=cancelled mất tổng cộng 8 giây, average invocation time là 80 ms. Điều đó không nói record đã nằm bao lâu trên Kafka trước khi được poll.

Đừng nhầm Timer count với số unique orders. Một event có thể được xử lý ba lần do retry và được tính ba invocation nếu ba lần đều được instrumentation đo.

## 15. Tên metric trong Prometheus

Micrometer dùng tên abstraction như spring.kafka.listener. Khi xuất Prometheus, tên metric có thể được chuẩn hóa thành dạng như:

~~~text
spring_kafka_listener_seconds_count
spring_kafka_listener_seconds_sum
spring_kafka_listener_seconds_max
~~~

Tên thực tế tùy Micrometer/registry naming convention và Spring Kafka version. Cần kiểm tra endpoint/scrape data trước khi xây dashboard.

Ví dụ PromQL về tốc độ listener invocation theo event family:

~~~promql
sum by (event_family, result) (
  rate(spring_kafka_listener_seconds_count[5m])
)
~~~

Ví dụ average listener duration:

~~~promql
sum by (event_family) (
  rate(spring_kafka_listener_seconds_sum[5m])
)
/
sum by (event_family) (
  rate(spring_kafka_listener_seconds_count[5m])
)
~~~

Nếu query không trả dữ liệu, kiểm tra tên series và label đã được export, timer enabled, exporter configuration và việc listener có thật sự nhận record hay không.

## 16. Percentile cần histogram hoặc distribution statistics

Muốn xem P95/P99 listener latency, cần cấu hình Timer xuất histogram buckets hoặc distribution statistics phù hợp.

Nếu có Prometheus histogram buckets, query minh họa:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, event_family) (
    rate(spring_kafka_listener_seconds_bucket[5m])
  )
)
~~~

Nếu không xuất _bucket series, query không thể tính percentile từ dữ liệu không tồn tại.

Khi bật histogram:

- Số series tăng theo mỗi bucket và mỗi tổ hợp tags.
- Cần biết SLO latency để chọn buckets hữu ích.
- Nếu mỗi event_family ít samples, P99 có thể không ổn định.
- Tránh bật histogram trên mọi metrics có cardinality lớn.
- Cân nhắc cost của monitoring backend.

Một timer có P95 tốt trong khi backlog tăng rất nhanh vẫn có thể là hệ thống gặp vấn đề. Cần quan sát event age và consumer lag bổ sung.

## 17. MeterFilter giúp bảo vệ số tag values

Micrometer có MeterFilter để giới hạn một số tag values. Ví dụ minh họa:

~~~java
@Bean
MeterFilter kafkaEventFamilyGuard() {
    return MeterFilter.maximumAllowableTags(
            "spring.kafka.listener",
            "event_family",
            10,
            MeterFilter.deny()
    );
}
~~~

Mục tiêu là tránh số distinct event_family values vượt quá ngưỡng, theo khả năng API của Micrometer version được sử dụng.

**MeterFilter không thay thế allowlist trong provider.** Khi đạt giới hạn, meter mới có thể bị từ chối và metrics trở nên thiếu dữ liệu. Việc drop metric không sửa được nguồn sinh tag không giới hạn.

Thiết kế tốt có nhiều lớp:

1. Allowlist/bucket mapping tại provider.
2. Test những header không hợp lệ.
3. Giới hạn tag keys.
4. MeterFilter guardrail khi cần.
5. Alert theo series count/scrape size.
6. Log/meter về việc tag mapping bị đưa vào unknown/other quá nhiều.
7. Review tag contract khi business thêm event types.

## 18. Một provider dùng chung cho nhiều listeners

Một ConcurrentKafkaListenerContainerFactory có thể được nhiều @KafkaListener dùng chung.

~~~text
ordersListenerFactory
     |
     +--> ordersCreatedListener
     +--> ordersCancelledListener
     +--> ordersReplayListener
     |
     +--> micrometerTagsProvider chung
~~~

Ưu điểm:

- Mapping nhất quán.
- Ít code trùng lặp.
- Dashboard aggregation dễ hơn.
- Dễ áp chung policy về cardinality.

Nhưng nếu paymentListenerFactory là một bean khác, nó không tự nhận provider của ordersListenerFactory.

Ví dụ dùng hai factory với hai phạm vi event types khác nhau là hợp lý khi các domain có metric contract riêng. Đừng copy một provider quá tổng quát rồi đọc arbitrary headers của mọi domain để phân loại.

Một lỗi phổ biến là cấu hình bean kafkaListenerContainerFactory mặc định nhưng @KafkaListener lại chỉ rõ containerFactory="paymentsFactory". Khi đó metrics tagging phải được đặt trên paymentsFactory hoặc logic cấu hình chung được áp dụng cho nó.

## 19. Concurrency và multi-pod deployment

Khi container concurrency=3, Spring Kafka có thể tạo ba child Kafka consumers:

~~~text
ordersListener parent
    |
    +--> child 0: P0, P1
    +--> child 1: P2, P3
    +--> child 2: P4, P5
~~~

Các records đi qua nhiều child consumers vẫn có thể nhận cùng một mapping tag.

Nhưng số series còn có thể tăng theo listener name, exception/result, application instance và exporter labels. Để kiểm soát:

- Không thêm random instance UUID từ record vào tags.
- Không gắn partition nếu không có nhu cầu rõ.
- Dùng labels của Prometheus scrape target cho pod/namespace khi cần.
- Tránh trùng nghĩa giữa static service tag và exporter service label.
- Theo dõi series churn khi rolling deploy.
- Không coi một child consumer là một unique business event stream.

micrometerTagsProvider hoạt động cục bộ trong process. Các pods không chia sẻ một MeterRegistry trong bộ nhớ; hệ monitoring tập trung mới hợp nhất số liệu giữa pods.

## 20. Có nên tag topic và partition?

Topic và partition là các field dễ lấy:

~~~java
record.topic()
record.partition()
~~~

Nhưng mức độ phù hợp phụ thuộc quy mô:

| Tag | Khi có thể chấp nhận | Khi nên tránh |
|---|---|---|
| topic | 3-10 topics ổn định | Topic per tenant/day/job liên tục tăng |
| partition | Số partition nhỏ và thực sự cần chẩn đoán timer theo partition | Hàng trăm/hàng nghìn partitions nhân với nhiều tags khác |
| topic_group | Khi mapping topic về nhóm hữu hạn | Ít rủi ro hơn raw topic |
| event_type | Khi có allowlist | Header raw/free-form không giới hạn |
| tenant_tier | Khi có ít tiers hữu hạn | tenantId riêng từng khách hàng |

Ví dụ mapping topic group an toàn hơn:

~~~java
properties.setMicrometerTagsProvider(record -> Map.of(
        "topic_group",
        switch (record.topic()) {
            case "orders.created" -> "orders";
            case "payments.authorized" -> "payments";
            default -> "other";
        }
));
~~~

Nếu cần consumer lag theo partition, có thể dùng Kafka client/group metrics thay vì nhân tag partition vào mọi listener Timer. Listener latency và lag là hai khái niệm khác nhau.

## 21. Retry, DLT và số lần listener được đo

Một record có thể thất bại rồi retry:

~~~text
orders.events
     |
     +--> Listener attempt 1: thất bại
     |
     +--> Listener attempt 2: thất bại
     |
     +--> Listener attempt 3: thành công
~~~

Timer count có thể phản ánh ba lần gọi listener, không phải ba unique events. Nếu non-blocking retry dùng retry topics, record có thể đi qua một hoặc nhiều listener endpoints khác nhau và phát sinh nhiều metrics với name/topic khác nhau.

Không dùng micrometerTagsProvider để suy đoán attempt number từ Kafka offset hoặc topic suffix mà không có contract chắc chắn. Nếu cần retry metrics:

- Counter cho số attempts.
- Counter cho publish sang retry topic.
- Counter cho DLT publish.
- Consumer lag trên từng retry topic.
- End-to-end event completion latency.
- Duplicate detection metric ở business layer.

Phân nhóm processing_lane=source/retry/replay có thể hữu ích nếu mapping topology hữu hạn và rõ ràng.

## 22. Lỗi deserialization có thể không có listener timer

Một số lỗi xảy ra trước khi @KafkaListener method được gọi:

~~~text
KafkaConsumer.poll()
     |
     v
Deserializer thất bại
     |
     +--> Listener chưa nhận record
     |
     +--> Timer invocation không nhất thiết được tạo
     |
     +--> micrometerTagsProvider có thể không chạy
~~~

Vì vậy, số failure của listener Timer không phải luôn là số malformed records.

Với Spring Kafka, ErrorHandlingDeserializer có thể biến lỗi deserialize thành metadata/header để CommonErrorHandler xử lý. Tuy nhiên, thời điểm listener metrics được ghi phụ thuộc đường lỗi và phiên bản.

Cần quan sát kết hợp:

- Deserialization errors.
- Schema registry errors.
- DefaultErrorHandler/recovery metrics.
- DLT publish failures.
- Consumer lag.
- Kafka client poll errors.
- Logs có topic/partition/offset phù hợp.

Provider không nên đọc trực tiếp value với giả định nó luôn là một OrderEvent object. Nó có thể null hoặc lỗi chưa được convert.

## 23. Batch listener và giới hạn của per-record provider

micrometerTagsProvider nhận một ConsumerRecord, nên nó gắn tự nhiên với **record listener**.

Một batch listener có thể nhận:

~~~java
@KafkaListener(
        topics = "orders.events",
        containerFactory = "batchFactory"
)
public void onOrders(List<OrderEvent> batch) {
    orderService.processBatch(batch);
}
~~~

Một batch chứa nhiều event types và không nhất thiết có một event_type duy nhất đại diện toàn batch.

~~~text
Batch:
  OrderCreated
  OrderCancelled
  OrderCreated
  OrderShipped
~~~

Với batch listener, **không mặc định giả định provider tạo tag theo từng record hoặc timer riêng cho mỗi record**. Hỗ trợ cụ thể phụ thuộc Spring Kafka version và loại listener instrumentation.

Nếu cần metrics riêng cho từng item trong batch, có thể tự ghi counter theo event type trong business code với semantics rõ ràng, chẳng hạn item attempted hay item completed. Nếu một batch thất bại giữa chừng, hai metric đó có thể khác nhau.

Không lấy duration của cả batch chia cho số records rồi coi đó là latency của mỗi record nếu bulk operation có chi phí không tuyến tính.

## 24. Micrometer Timer và Micrometer Observation không tương đương

Spring Kafka hiện đại hỗ trợ Micrometer Observation, có thể tích hợp metrics và tracing.

| Tiêu chí | Micrometer Timer + micrometerTagsProvider | Micrometer Observation |
|---|---|---|
| Mục tiêu | Timer duration/count theo tags | Observation lifecycle, metrics và tracing |
| Điểm mở rộng | ContainerProperties.micrometerTagsProvider | Observation convention/handler |
| Input metadata | ConsumerRecord trong provider | Observation context tương ứng |
| Low-cardinality data | Phù hợp với metrics | Dùng để phân nhóm metrics |
| High-cardinality data | Không nên đưa vào tags | Có thể phù hợp với tracing sau khi xem xét privacy/sampling |
| Trace spans | Không tự tạo đầy đủ | Có thể tạo spans nếu được cấu hình |
| Bật tính năng | micrometerEnabled | observationEnabled |

Ví dụ bật Observation:

~~~java
factory.getContainerProperties()
        .setObservationEnabled(true);
~~~

Trong nhiều phiên bản Spring Kafka, khi Observation được bật, cơ chế listener Timer cũ không đồng thời hoạt động như trước. **Đừng giả định micrometerTagsProvider sẽ tự động được áp dụng cho observation metrics hoặc trace spans**.

Nếu project chuyển từ Micrometer Timer sang Observation, cần xem xét extension point Observation convention, tên metric, tags và dashboard tương ứng. Đây là thay đổi instrumentation, không chỉ thay đổi một boolean.

## 25. Low-cardinality tags và tracing attributes

**Low-cardinality** có số giá trị hữu hạn, thích hợp với metrics:

~~~text
event_family = created | cancelled | shipped | other
processing_lane = source | retry | replay
service_area = orders | payments | notifications
~~~

**High-cardinality** có số giá trị lớn hoặc gần như unique:

~~~text
event_id = evt-...
order_id = 983721
trace_id = 46fa...
user_id = 200348
~~~

High-cardinality attributes thường thích hợp hơn với log/traces, có kiểm soát sampling, retention và privacy. Không phải mọi dữ liệu cụ thể đều được phép ghi trong traces; secrets, PII và dữ liệu nhạy cảm phải được xử lý theo chính sách bảo vệ dữ liệu.

Ví dụ hai câu hỏi khác nhau:

- **Metrics:** P95 listener latency của nhóm cancelled trong 15 phút gần nhất?
- **Tracing:** Event evt-123 bị chậm ở bước database nào?

Câu hỏi đầu phù hợp với low-cardinality tags. Câu hỏi sau cần correlation ID ở logs/traces, không nên tạo một Timer series riêng cho evt-123.

## 26. Không nhầm Timer count với unique business events

Giả sử record E được giao lại:

~~~text
E attempt 1 --> DB timeout
E attempt 2 --> DB timeout
E attempt 3 --> success
~~~

Spring Kafka listener có thể được gọi ba lần. Business system có thể chỉ hoàn tất một logical operation.

| Metric | Điều được đếm |
|---|---|
| Listener Timer count | Số invocation được instrumentation đo |
| Retry count | Số lần thử lại theo policy |
| Unique business event count | Số event IDs duy nhất đã hoàn tất |
| Database mutation count | Số thay đổi DB thực sự được áp dụng |
| DLT publish count | Số record gửi sang DLT |
| Duplicate rejected count | Số redelivery được idempotency ngăn lặp |

Không kết luận producer đã tạo ba order mới chỉ vì Timer count tăng ba. Monitoring phải phân biệt attempt-based và logical-operation-based metrics.

## 27. Kết hợp listener metrics với consumer lag và database metrics

Một dashboard reliability nên kết hợp:

~~~text
Listener Timer p95
       |
       +--> Kafka consumer lag
       |
       +--> Listener failure rate
       |
       +--> Retry/DLT rate
       |
       +--> HikariCP active/waiting
       |
       +--> Database query p95/p99
       |
       +--> Pause/resume state
       |
       +--> Oldest unprocessed event age
~~~

Ví dụ listener bị pause vì database quá tải. Trong lúc pause, Timer count có thể không tăng vì không có invocation mới. Timer p95 có thể trông tốt nhưng consumer lag và event age tăng nhanh. Nếu chỉ nhìn Timer, operator có thể bỏ qua sự cố.

Ngược lại, Timer p95 cao nhưng consumer lag không tăng có thể chỉ là một nhóm event ít traffic và đắt hơn bình thường; cần dựa vào SLA thay vì chỉ nhìn một con số.

micrometerTagsProvider giúp **chia nhỏ listener metric theo nhóm record**, nhưng không biến nó thành bộ đo toàn bộ hệ thống.

## 28. Những lỗi cấu hình thường gặp

### Provider không tạo tag mới

Kiểm tra đúng container factory, micrometerEnabled, dependency Micrometer, Observation mode, exporter và việc listener có nhận record. Nếu listener dùng factory khác, sửa đúng factory.

### Tag nào cũng là other

Allowlist không khớp topic/header thực tế. Kiểm tra mapping contract, không sửa bằng cách trả raw header không giới hạn.

### Số series tăng mạnh

Tag có raw Kafka key, tenantId, eventId, offset, timestamp hoặc một header tự do. Thay bằng bounded mapping và bổ sung MeterFilter.

### Provider ném NullPointerException

Header/value/key có thể null hoặc map tạo với null. Trả unknown/other và không dùng Map.of với giá trị null.

### Listener latency tăng sau khi thêm tag provider

Provider đang parse payload lớn, gọi DB/API hoặc block. Chuyển sang mapping nhẹ trong bộ nhớ.

### Timer báo success dù DB operation chưa xong

Listener có thể dispatch async task rồi return sớm. Timer phản ánh callback, không biết work thực sự đã hoàn tất. Sửa completion/ack boundary và thêm business metrics.

### Query P95 không có dữ liệu

Có thể chưa bật histogram buckets hoặc tên series khác. Kiểm tra dữ liệu scrape thực tế.

### Metrics thiếu với deserialization failures

Lỗi có thể xảy ra trước khi listener method và timer chạy. Dùng error-handler/DLT/deserializer metrics bổ sung.

### Retry làm count lớn hơn số events

Count invocation không phải unique event count. Thêm idempotency/business counters và dashboard riêng.

### Nhiều pods tạo tag instance thay đổi liên tục

Không thêm random UUID vào provider tags. Dùng infrastructure labels ổn định hoặc scrape target metadata.

## 29. Test để xác nhận wiring và semantics

Kiểm thử logic mapping trước:

| Input | Expected tag |
|---|---|
| orders.created | event_family=created |
| orders.cancelled | event_family=cancelled |
| orders.shipped | event_family=shipped |
| Một topic không biết | event_family=other |
| Header event-type không có | event_type=unknown |
| Header event-type tùy ý | event_type=other |

Để xác nhận integration, cần có container factory với provider và MeterRegistry. Dùng Kafka test infrastructure phù hợp để gửi record rồi đọc listener meter đã ghi.

Các trường hợp nên quan sát:

1. Listener success.
2. Listener exception và retry.
3. Nhiều event types trên cùng topic.
4. Missing/null headers.
5. Concurrent child consumers.
6. Listener sử dụng factory khác.
7. Observation enabled thay Timer.
8. Batch listener.
9. Deserialization error trước method.
10. Exporter Prometheus thực tế có tag mới.

Một unit test chỉ gọi classifyTopic trực tiếp không chứng minh provider đã được gắn vào Spring Kafka listener container. Test integration giúp xác nhận wiring và tên metric thực tế.

## 30. Quy tắc thiết kế tag contract cho cả đội

Một service lớn thường có nhiều listeners; nhiều services cùng cần dashboard tập trung. Nên thống nhất:

| Tag key | Values mong đợi | Nguồn |
|---|---|---|
| service_area | orders, payments, notifications | Static config |
| event_family | created, cancelled, shipped, other | Topic/header allowlist |
| processing_lane | source, retry, replay, other | Topic mapping |
| schema_family | order_v1, order_v2, other | Schema contract |
| deployment_tier | dev, staging, prod | Static config |

Những nguyên tắc:

- Tag keys được đặt tên nhất quán.
- Không reuse cùng tag key với nghĩa khác nhau.
- Giá trị phải hữu hạn.
- Có fallback unknown/other.
- Không lưu PII hoặc secrets.
- Không đưa raw Kafka headers vào tags.
- Khi thay đổi allowed values, review dashboard/alert dependencies.
- Đặt series budget trước khi mở rộng tenant/topic.
- Theo dõi cardinality và scrape cost theo thời gian.

Nếu một team yêu cầu thêm tag customerId để debug, cần giải thích mục tiêu đó nên được giải quyết bằng log/tracing correlation, không phải bằng time series cho từng customer.

## 31. Checklist trước production

- Listener thực tế dùng đúng factory có cấu hình micrometerTagsProvider.
- Micrometer Timer mode đang được bật và version hỗ trợ API.
- Provider nhận ConsumerRecord và trả Map<String,String>.
- Static tags và dynamic tags có vai trò riêng, không trùng key.
- Mọi dynamic tag value được chuẩn hóa bằng allowlist.
- Không dùng eventId, orderId, offset, timestamp, Kafka key hoặc raw tenantId.
- Header thiếu/null/unknown không gây lỗi provider.
- Tombstone và deserialization failures được hiểu đúng.
- Provider không gọi DB, HTTP, Redis, schema registry hay storage.
- Provider không block hoặc thay đổi record.
- Map không chứa null keys/values.
- Đã ước lượng và theo dõi metric series cardinality.
- Có MeterFilter guardrail nếu monitoring backend cần.
- Tên metric và labels được xác nhận từ exporter thực tế.
- P95/P99 chỉ dùng khi histogram/distribution đã được cấu hình.
- Listener timer được phân biệt với Kafka client metrics và consumer lag.
- Invocation count không bị nhầm với unique business event count.
- Retry/DLT có metrics riêng, không phụ thuộc chỉ vào provider.
- Batch listener không bị mặc định coi là per-record timer.
- Observation mode được cấu hình bằng extension point phù hợp.
- Có dashboard/alert cho listener failure rate, latency, lag và downstream saturation.
- Đã kiểm tra multi-factory, concurrency, multiple replicas và unknown header.

**Kết luận:** micrometerTagsProvider cho phép Spring Kafka tạo **dynamic tags từ từng ConsumerRecord** để phân nhóm Micrometer listener timers theo những đặc điểm hữu ích như event family hoặc processing lane. Giá trị của nó nằm ở việc tìm ra nhóm record chậm, lỗi hoặc bị ảnh hưởng sau deploy mà không nhân bản listener code. Để an toàn, provider phải **nhanh, thuần, không side effect, xử lý null và dùng tập tag values hữu hạn**. Metrics này cần được kết hợp với Kafka lag, retry/DLT, database metrics và Observation/tracing, vì listener Timer không đại diện cho toàn bộ delivery guarantee hay end-to-end reliability.

