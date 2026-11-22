# Micrometer consumer timers

Trong hệ thống Spring Kafka, consumer không chỉ cần đọc được records mà còn phải xử lý chúng **đúng thời hạn, với tỷ lệ lỗi chấp nhận được**. Một Kafka consumer group có thể có lag thấp nhưng listener xử lý từng record chậm bất thường; ngược lại, listener thực thi rất nhanh mà vẫn có lag cao vì thiếu partition concurrency, broker fetch chậm hoặc producer gửi quá nhanh. Vì vậy, monitoring phải phân biệt **thời gian xử lý listener** với **consumer lag, tốc độ poll, thời gian chờ retry và độ trễ end-to-end**.

**Micrometer consumer timers** của Spring Kafka đo thời gian gọi business listener thông qua các `Timer` có tên `spring.kafka.listener`. Framework cung cấp khả năng này tự động khi đáp ứng điều kiện tích hợp Micrometer. Các timer được tách theo kết quả **thành công** và **thất bại**, giúp đội vận hành quan sát thời gian xử lý, số lượt gọi listener và xu hướng lỗi.

Bài học hướng dẫn cách bật, tắt và gắn tags cho timer; tích hợp Spring Boot Actuator/Prometheus; viết truy vấn; nhận diện giới hạn đo lường; phân biệt Micrometer timers với Observation/Tracing và Kafka client metrics; đồng thời xây runbook khi số liệu bất thường.

## 1. Timer đo chính xác điều gì?

Một pipeline cơ bản:

~~~text
Kafka broker
    |
    v
KafkaConsumer.poll() ------> Records đã fetch
                                  |
                                  v
                         Spring listener container
                                  |
                                  v
                       @KafkaListener invocation
                                  |
                         +--------+--------+
                         |                 |
                       Success           Exception
                         |                 |
                         v                 v
                 success Timer        failure Timer
                                  |
                                  v
                        Error handler / retry / DLT
~~~

`spring.kafka.listener` ghi nhận **thời gian cho mỗi lần gọi listener** theo phạm vi mà Spring Kafka instrumentation bao bọc. Nó không phải phép đo cho toàn bộ thời gian một record nằm trong Kafka, không tự tính thời gian chờ trong retry topic, và không thay thế đo lường Kafka client `poll()`/fetch.

Một cách hiểu vận hành:

| Câu hỏi | Micrometer listener timer trả lời? |
|---|---|
| Listener thường mất bao lâu để chạy? | Có |
| Mỗi lần listener được gọi có thành công hay ném exception? | Có, theo tag `result` |
| Số lần gọi listener trong một khoảng thời gian? | Có thể suy ra từ `count` |
| Consumer có bao nhiêu records tồn đọng? | Không; cần consumer lag |
| Record đã chờ bao lâu từ lúc producer gửi? | Không; cần end-to-end latency |
| `poll()` đang bị kẹt? | Không trực tiếp; cần consumer/client metrics và monitor event |
| Một record đã qua bao nhiêu lần retry? | Không trực tiếp; cần retry metrics/headers |
| Database đã commit an toàn? | Không; timer chỉ phản ánh kết quả gọi listener mà framework quan sát |

Một listener trả về bình thường nhưng đã âm thầm bỏ qua lỗi nghiệp vụ có thể được ghi vào nhóm **success**. Vì vậy, metric success của listener **không tự động bằng** tỷ lệ thành công của toàn bộ business workflow.

## 2. Điều kiện tạo Micrometer timers

Theo Spring Kafka Reference, tính năng timer listener được hỗ trợ từ **Spring Kafka 2.3**. Container tự động tạo và cập nhật `Timer` khi:

1. Micrometer hiện diện trong classpath.
2. Có một `MeterRegistry` thích hợp trong Spring application context; tài liệu mô tả điều kiện một registry.
3. Container property `micrometerEnabled` được bật.
4. Ứng dụng không chuyển sang chế độ Observation thay thế timer truyền thống cho listener tương ứng.

Trong nhiều phiên bản hiện hành, `ContainerProperties.micrometerEnabled` mặc định là `true`, còn `observationEnabled` mặc định `false`. Tuy nhiên, “mặc định true” **không có nghĩa chắc chắn timer xuất hiện**, nếu registry không sẵn sàng hoặc container không được tạo theo factory mà bạn nghĩ.

Ví dụ sự phụ thuộc:

~~~text
Micrometer API trên classpath
            +
MeterRegistry có thể ghi metrics
            +
ContainerProperties.micrometerEnabled = true
            +
Listener thực sự được gọi
            |
            v
Spring Kafka đăng ký/cập nhật spring.kafka.listener Timer
~~~

Nếu listener đang idle hoàn toàn, series có thể chưa xuất hiện dưới dạng metric sample tùy thời điểm container tạo meter và registry/exporter. Không vội kết luận monitoring hỏng chỉ vì topic vừa khởi động chưa có traffic.

## 3. Timer name và tags mặc định

Timer listener của Spring Kafka có tên:

~~~text
spring.kafka.listener
~~~

Tài liệu framework mô tả các tags mặc định:

| Tag | Ví dụ | Ý nghĩa |
|---|---|---|
| `name` | `orders-consumer-0` | Tên container/child consumer |
| `result` | `success` hoặc `failure` | Kết quả invocation của listener |
| `exception` | `none` hoặc `ListenerExecutionFailedException` | Exception label ở tầng listener |

Hai nhóm timers được duy trì cho kết quả `success` và `failure`. Ở nhiều phiên bản Spring Kafka, tag `exception` của failure timer phản ánh wrapper `ListenerExecutionFailedException`, **không nhất thiết là class exception nghiệp vụ sâu nhất**.

Ví dụ dữ liệu khái niệm:

~~~text
spring.kafka.listener{
    name="orders-consumer-0",
    result="success",
    exception="none"
}

spring.kafka.listener{
    name="orders-consumer-0",
    result="failure",
    exception="ListenerExecutionFailedException"
}
~~~

Nếu muốn thống kê `DatabaseUnavailableException` và `InvalidOrderEventException` riêng biệt, nên bổ sung error-handler metrics, application logs, tracing hoặc các counters có phân loại exception chủ đích. Đừng giả định tag `exception` trên timer luôn chứa root cause.

## 4. Concurrent container tạo timers cho từng consumer thread

Với `ConcurrentMessageListenerContainer`, Spring Kafka duy trì timers cho từng child consumer. Tài liệu nêu rằng tag `name` được thêm hậu tố `-n`, với `n` từ 0 đến `concurrency - 1`.

~~~text
@KafkaListener(id="orders-consumer", concurrency="3")
              |
              v
Concurrent container
   +-- orders-consumer-0 -> success/failure timers
   +-- orders-consumer-1 -> success/failure timers
   +-- orders-consumer-2 -> success/failure timers
~~~

Điều này giúp tìm consumer thread có latency cao hơn các threads còn lại. Nhưng khi tính tỷ lệ lỗi **toàn listener**, phải aggregate qua các child names, không chỉ chọn `orders-consumer-0`.

Các chỉ số có thể thay đổi khi scale concurrency, thay cấu hình listener ID hoặc restart. Hãy chọn tên logical listener ổn định để dashboard không phụ thuộc một child index duy nhất.

Ví dụ listener:

~~~java
@KafkaListener(
    id = "orders-consumer",
    topics = "orders",
    groupId = "order-projection",
    concurrency = "3")
public void handle(OrderEvent event) {
    orderProjectionService.apply(event);
}
~~~

Listener ID và `name` timer có liên hệ nhưng không nhất thiết giống hệt trong mọi cấu hình container/bean name. Nên kiểm tra các series thực tế xuất hiện trong registry.

## 5. Bật và tắt timer ở ContainerProperties

Khi sử dụng Spring Java configuration:

~~~java
@Configuration
public class OrderConsumerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setMicrometerEnabled(true);

        return factory;
    }
}
~~~

`setMicrometerEnabled(true)` làm rõ ý định mặc dù giá trị mặc định của các phiên bản Spring Kafka hiện hành là `true`.

Để tắt legacy listener timers khi có lý do rõ ràng:

~~~java
factory.getContainerProperties().setMicrometerEnabled(false);
~~~

Lưu ý:

- Cấu hình trên tác động tới containers được tạo từ factory đó, không tự đổi mọi Kafka listeners trong application.
- Nếu có nhiều `ConcurrentKafkaListenerContainerFactory`, cần kiểm tra listener được gắn với factory nào.
- Bật timer làm phát sinh chi phí instrumentation và meter series, thường nhỏ so với công việc nghiệp vụ nhưng vẫn cần đo trên hệ thống lớn.
- Không tắt metrics chỉ để giảm alert; nếu alert sai, cần sửa alert/query/cardinality.
- Nếu `observationEnabled=true`, Micrometer Observation sẽ thay thế cách ghi legacy timers; phải xác định đường telemetry chủ động sử dụng.

## 6. Cấu hình listener factory đúng với @KafkaListener

Ví dụ listener sử dụng factory vừa khai báo:

~~~java
@Component
public class OrdersConsumer {

    private final OrderProjectionService projection;

    public OrdersConsumer(OrderProjectionService projection) {
        this.projection = projection;
    }

    @KafkaListener(
        id = "orders-consumer",
        topics = "orders",
        groupId = "order-projection",
        containerFactory = "ordersListenerFactory")
    public void onOrder(OrderEvent event) {
        projection.apply(event);
    }
}
~~~

Không phải chỉ cần có bean factory trong Spring context là listener sẽ dùng nó; nếu `containerFactory` không được chỉ định, Spring Kafka có thể chọn factory mặc định theo tên `kafkaListenerContainerFactory` hoặc cấu hình của application.

Khi một số listeners có timer còn các listeners khác không có, việc đầu tiên là kiểm tra **factory wiring**, `micrometerEnabled`, `observationEnabled` và MeterRegistry hiện hữu của từng path.

## 7. Micrometer Timer cung cấp những số liệu nào?

`Timer` trong Micrometer lưu số lượt đo và tổng thời gian, cùng các thống kê phân phối tùy registry/cấu hình.

| Statistic | Diễn giải |
|---|---|
| `count` | Số lần listener invocation được ghi nhận vào timer |
| `totalTime` / `sum` | Tổng thời gian các invocations |
| `max` | Giá trị lớn nhất theo cửa sổ/statistics backend phù hợp |
| Histogram buckets | Phân phối latency theo các bucket, nếu được bật/exporter hỗ trợ |
| Percentile | Phân vị p50/p95/p99 nếu có cấu hình và backend hỗ trợ |

Nếu một Timer ghi nhận 100 invocations với tổng thời gian 12,5 giây, **thời gian xử lý trung bình** là:

~~~text
Average invocation duration
= totalTime / count
= 12,5 giây / 100
= 125 milliseconds
~~~

Đây là trung bình thời gian invocation, **không** phải tổng latency từ Kafka publish đến database projection commit. Một record có thể chờ trên broker 10 phút rồi được listener xử lý trong 20 ms; timer ghi nhận khoảng 20 ms cho invocation đó.

Với một listener batch, một invocation có thể xử lý nhiều records. `count` của Timer có thể là **số lần gọi batch listener**, không phải số records. Muốn đo record throughput trong batch, cần bổ sung record counter hoặc Kafka client metrics.

## 8. Tích hợp Spring Boot Actuator và Prometheus

Trong Spring Boot, có thể sử dụng Actuator cùng Micrometer Prometheus registry để xuất dữ liệu timer.

Ví dụ Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.kafka:spring-kafka")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Với Maven, có thể khai báo các dependency tương đương. Không cần tự tạo Kafka event producer riêng để gửi timer data; MeterRegistry tích hợp với exporter.

Một cấu hình endpoint minh họa:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-projection
    distribution:
      percentiles-histogram:
        spring.kafka.listener: true
~~~

Trong cấu hình này:

- `management.endpoints.web.exposure.include` quyết định endpoint Actuator nào có thể truy cập qua web.
- `management.metrics.tags.application` gắn application tag chung.
- `percentiles-histogram.spring.kafka.listener` yêu cầu xuất histogram cho timer cùng tên theo khả năng Micrometer registry.
- Prometheus endpoint thường là `/actuator/prometheus` khi setup đúng.

**Bảo mật:** endpoint metrics có thể chứa thông tin nội bộ về service, listener names và exception labels. Nên giới hạn truy cập bằng network policy, authentication hoặc scrape infrastructure phù hợp; không mở public không kiểm soát.

Không cấu hình histogram cho hàng nghìn tag combinations mà chưa tính cardinality và chi phí lưu trữ.

## 9. Timer được xuất sang Prometheus như thế nào?

Khi Prometheus registry xuất Micrometer Timer `spring.kafka.listener`, tên metric thường được chuyển sang dạng snake_case với đơn vị seconds. Ví dụ:

~~~text
spring_kafka_listener_seconds_count
spring_kafka_listener_seconds_sum
spring_kafka_listener_seconds_max
~~~

Nếu histogram được bật và backend hỗ trợ, có thể có:

~~~text
spring_kafka_listener_seconds_bucket
~~~

Ví dụ series minh họa:

~~~text
spring_kafka_listener_seconds_count{
  name="orders-consumer-0",
  result="success",
  exception="none",
  application="order-projection"
} 12430
~~~

Các series thực tế phụ thuộc phiên bản Micrometer/Prometheus registry, tag keys, custom tags, Observation mode và scrape configuration. Không mặc định các meter xuất hiện trước khi listener chạy và registry tạo sample tương ứng.

`_count` là counter tăng theo mỗi lần timer được ghi nhận; dùng `rate(...)` để tính tốc độ trong một cửa sổ thời gian. `_sum` là tổng seconds và cho phép tính average duration.

## 10. Truy vấn throughput từ listener timers

Ví dụ PromQL ước lượng số invocation mỗi giây theo listener child:

~~~promql
sum by (name) (
  rate(spring_kafka_listener_seconds_count[5m])
)
~~~

Nếu muốn gộp success và failure cho cùng listener logic, cần biết tên children và quy tắc đặt tên. Một cách là thêm static tag `pipeline` và aggregate theo tag này thay vì gộp tên bằng regex khi cấu hình nhiều listeners.

Với batch listener, tốc độ invocation **không bằng record throughput**. Ví dụ một lần gọi batch xử lý 200 records, timer count chỉ tăng một lần cho invocation; muốn records/second cần đo lượng records hoặc client fetch/consumer counters.

Với record listener thông thường, invocation count thường gần số lần listener được gọi; khi retry, số lần gọi có thể nhiều hơn số unique business events. Timer count không tự deduplicate events.

## 11. Truy vấn tỷ lệ lỗi từ tag result

Prometheus query minh họa tỷ lệ listener invocations thất bại trong 5 phút:

~~~promql
sum by (name) (
  rate(spring_kafka_listener_seconds_count{result="failure"}[5m])
)
/
clamp_min(
  sum by (name) (
    rate(spring_kafka_listener_seconds_count[5m])
  ),
  0.000000001
)
~~~

Ý nghĩa:

- Tử số: tốc độ invocation gắn `result="failure"`.
- Mẫu số: tốc độ tất cả invocations của cùng `name`.
- `clamp_min` tránh chia cho 0 khi có sample rất nhỏ hoặc không có traffic đủ lâu.

Khi không tồn tại failure series trong cửa sổ, phép chia có thể trả về kết quả không có sample thay vì 0. Dashboard/alert có thể cần thêm xử lý missing-series phù hợp. Không suy luận “không có metric failure” = “không có lỗi” nếu toàn bộ instrumentation bị tắt.

Lưu ý thêm: framework ghi nhận failure khi listener invocation ném lỗi theo cách nó quan sát. Nếu listener bắt exception rồi trả bình thường, kết quả có thể được gắn success. Một business rejection được xử lý có chủ đích có thể được coi thành công về mặt Kafka listener, dù đơn hàng bị từ chối về mặt nghiệp vụ.

## 12. Truy vấn latency trung bình

Từ Timer `_sum` và `_count`, average processing duration có thể được tính:

~~~promql
sum by (name) (
  rate(spring_kafka_listener_seconds_sum[5m])
)
/
clamp_min(
  sum by (name) (
    rate(spring_kafka_listener_seconds_count[5m])
  ),
  0.000000001
)
~~~

Kết quả tính bằng **seconds**. Nhân với 1000 nếu dashboard hiển thị milliseconds.

Ví dụ:

~~~text
Timer count tăng: 2.000 invocations trong 5 phút
Timer sum tăng:  100 seconds

Average = 100 / 2.000 = 0,05 seconds = 50 ms
~~~

Số liệu này thể hiện trung bình của các invocation đã được Timer ghi nhận trong cửa sổ, không phản ánh record vẫn đang bị treo trước khi invocation kết thúc.

Nếu một request duy nhất kéo dài 30 giây trong khi 99 requests khác chỉ 10 ms, average có thể bị kéo lên nhưng không giải thích rõ tail latency. Khi cần SLO về tail latency, cân nhắc histogram p95/p99.

## 13. p95/p99 từ histogram

Khi đã bật histogram và Prometheus nhận các bucket, có thể tính p95 như sau:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, name) (
    rate(spring_kafka_listener_seconds_bucket[5m])
  )
)
~~~

Để đo p99, thay `0.95` bằng `0.99`. Truy vấn histogram của Micrometer Timer chỉ hợp lệ nếu:

1. Histogram thực sự được bật và registry xuất `_bucket`.
2. Các tag cần aggregate có định nghĩa nhất quán.
3. Cửa sổ đủ số samples để percentile có ý nghĩa.
4. Số lượng bucket và tag combinations nằm trong ngân sách cardinality.

Không dùng một `_max` đơn lẻ thay cho p99. Maximum chịu ảnh hưởng outlier và window semantics, còn p99 là phân vị dựa trên phân phối dữ liệu.

Trong hệ thống ít traffic, p99 một phút có thể dao động mạnh; cần cân nhắc cửa sổ đo và ngưỡng alert.

## 14. Tách success latency và failure latency

Hai nhóm Timer success/failure giúp phát hiện vấn đề khác nhau.

Một failure có thể **rất nhanh** nếu listener phát hiện dữ liệu không hợp lệ ngay đầu method. Ngược lại, failure có thể **rất chậm** nếu listener gọi database hoặc HTTP API tới timeout.

Ví dụ giả định:

| Result | Count/5m | Average duration | Diễn giải có thể |
|---|---:|---:|---|
| success | 8.000 | 25 ms | Nhiều records hoàn tất bình thường |
| failure | 60 | 1.800 ms | Dependency timeout hoặc retry trước khi ném exception |
| failure | 900 | 3 ms | Data validation lỗi hàng loạt, fail fast |

Cùng “failure rate cao” nhưng runbook khác nhau. Metrics cần được liên hệ với exception logs, DLT, dependency latency và release changes.

PromQL latency trung bình cho lỗi:

~~~promql
sum by (name) (
  rate(spring_kafka_listener_seconds_sum{result="failure"}[5m])
)
/
clamp_min(
  sum by (name) (
    rate(spring_kafka_listener_seconds_count{result="failure"}[5m])
  ),
  0.000000001
)
~~~

Nếu listener lỗi do schema mismatch, tăng retry/backoff có thể không giúp; cần phân loại lỗi vĩnh viễn, xử lý DLT và sửa contract.

## 15. Static Micrometer tags

Spring Kafka cho phép gắn các tags cố định vào listener timers qua `ContainerProperties.micrometerTags`.

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setMicrometerEnabled(true);
    factory.getContainerProperties().setMicrometerTags(Map.of(
        "pipeline", "order-projection",
        "domain", "orders",
        "environment", "production"
    ));

    return factory;
}
~~~

Các tags thích hợp là các thông tin **ít thay đổi**:

- `pipeline` hoặc `service`: tên luồng xử lý.
- `domain`: nhóm nghiệp vụ.
- `environment`: dev/staging/production.
- `region`: vùng triển khai nếu phù hợp.
- `team`: ownership có số lượng giới hạn.

Không nên dùng event ID, order ID, UUID, offset, request URL chứa ID hoặc raw Kafka key làm tag. Mỗi giá trị tag mới có thể tạo một meter/time series mới. Trên hệ thống lưu lượng lớn, cardinality quá cao làm tăng memory của `MeterRegistry`, số series Prometheus và chi phí lưu trữ.

## 16. Dynamic tags từ ConsumerRecord

Từ các phiên bản Spring Kafka **2.9.8 và 3.0.6**, Spring Kafka hỗ trợ `ContainerProperties.micrometerTagsProvider`. Đây là một function nhận `ConsumerRecord<?, ?>` để trả về map tags động, kết hợp với các static tags.

Ví dụ chỉ phân loại một tập nhỏ event type:

~~~java
private static String eventKind(ConsumerRecord<?, ?> record) {
    Header header = record.headers().lastHeader("event-type");

    if (header == null || header.value() == null) {
        return "unknown";
    }

    String raw = new String(
        header.value(),
        StandardCharsets.UTF_8
    );

    return switch (raw) {
        case "OrderCreated" -> "order_created";
        case "OrderPaid" -> "order_paid";
        case "OrderCancelled" -> "order_cancelled";
        default -> "other";
    };
}
~~~

Gắn function vào factory:

~~~java
factory.getContainerProperties().setMicrometerTagsProvider(
    record -> Map.of("event_kind", eventKind(record))
);
~~~

Các import bổ sung có thể gồm:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
~~~

**Quan trọng:** function này được thiết kế dựa trên `ConsumerRecord`, thích hợp với record listener; hỗ trợ ở batch listener có giới hạn. Cần đối chiếu phiên bản Spring Kafka thực tế nếu dùng batch.

Dùng enum/whitelist như ví dụ để khống chế số tag values. Không lấy nguyên header `trace-id` hay `event-id` làm dynamic tag. Nếu cần truy vết một event cụ thể, dùng tracing/logging với correlation ID, không phải một metric series riêng cho từng event.

## 17. Static tags và dynamic tags có thể gây conflict

Khi kết hợp `micrometerTags` với `micrometerTagsProvider`, framework merge các tags theo cơ chế của phiên bản đang dùng. Nếu static map và dynamic function cùng tạo key `domain` hoặc `pipeline`, có thể có vấn đề ghi đè hoặc semantics khó hiểu.

Ví dụ không nên thiết kế:

~~~text
Static:  domain=orders
Dynamic: domain=untrusted-header-value
~~~

Hãy định nghĩa contract tags:

| Tag | Loại | Allowed values |
|---|---|---|
| `pipeline` | Static | `order-projection`, `payment-projection` |
| `environment` | Static | `production`, `staging` |
| `event_kind` | Dynamic, whitelist | `order_created`, `order_paid`, `other` |
| `name` | Framework | Container/child name |
| `result` | Framework | `success`, `failure` |
| `exception` | Framework | Các exception labels được framework xác định |

Không tự đặt custom tag trùng các keys của framework như `name`, `result` hoặc `exception`. Làm như vậy có thể gây xung đột hoặc khiến dashboard đọc sai series.

## 18. Micrometer Timer và Observation khác nhau

Spring Kafka hỗ trợ **Micrometer Observation** từ phiên bản 3.0. Khi bật:

~~~java
factory.getContainerProperties().setObservationEnabled(true);
~~~

Spring Kafka chuyển sang cơ chế Observation, cung cấp metrics và khả năng tích hợp tracing theo instrumentation Observation. Tài liệu nêu rằng bật Observation sẽ **tắt legacy Micrometer Timers** cho listener được quan sát, vì Observation tự quản lý timer tương ứng.

Bảng so sánh:

| Khía cạnh | Legacy Micrometer Timers | Micrometer Observation |
|---|---|---|
| Bật bằng | `micrometerEnabled=true` | `observationEnabled=true` |
| Mục tiêu chính | Thời gian và kết quả listener invocation | Instrumentation thống nhất metrics/tracing |
| Timer name | `spring.kafka.listener` | Có thể cũng là `spring.kafka.listener` theo convention |
| Tags mặc định | `name`, `result`, `exception` | Observation low-cardinality keys theo convention/version |
| Tags tùy chỉnh | `micrometerTags`, `micrometerTagsProvider` | `KafkaListenerObservationConvention`/context |
| Tracing | Không tự tạo span chỉ bởi Timer | Có thể tích hợp Micrometer Tracing |
| Batch listener | Timer truyền thống đo invocation | Hỗ trợ Observation cho batch phụ thuộc phiên bản/cấu hình |

**Lưu ý về phiên bản:** Một số bản Spring Kafka 3.x đầu tiên chưa hỗ trợ Observation cho batch listener nên dùng Timer thay thế; tài liệu các bản mới hơn có thêm batch-level Observation. Khi nâng cấp, cần kiểm tra release cụ thể và cấu hình batch thay vì áp dụng một kết luận cố định cho mọi version.

Một dashboard đang filter `result="failure"` từ legacy timers có thể bị ảnh hưởng khi chuyển sang Observation vì **tag names và conventions không hoàn toàn giống nhau**. Migration phải đi cùng kiểm tra Prometheus series và cập nhật alert rules.

## 19. Tùy chỉnh Observation tags khác với micrometerTagsProvider

Với Observation, Spring Kafka cung cấp `KafkaListenerObservationConvention` và default convention tương ứng. Tùy biến tags dùng conventions/context chứ không mặc định tiếp tục xử lý `micrometerTagsProvider` như legacy Timer.

Ý tưởng:

~~~text
Legacy timers:
  ContainerProperties.micrometerTags
  ContainerProperties.micrometerTagsProvider

Observation:
  ContainerProperties.observationEnabled = true
  ContainerProperties.observationConvention
  KafkaListenerObservationConvention
~~~

Trong Observation model, cần tách:

- **Low-cardinality tags:** các giá trị có số lượng hữu hạn, thích hợp cho metrics.
- **High-cardinality attributes:** event ID, key, offset hoặc request ID; chỉ phù hợp với tracing/logging nếu có quyền truy cập và quản trị dữ liệu.

Nếu đưa event ID vào low-cardinality observation tags, hậu quả cardinality vẫn giống như khi dùng Timer tags.

Đừng bật song song custom Timer tự viết và Observation cho cùng invocation mà không có lý do, bởi số liệu có thể bị ghi đúp dưới các metric names khác nhau, làm dashboard hiểu sai.

## 20. Micrometer consumer timers khác Kafka client metrics

Spring Kafka cũng hỗ trợ tích hợp **Micrometer Kafka client metrics** để quan sát metrics của chính KafkaConsumer/producer client.

| Nhóm metrics | Đo điều gì? |
|---|---|
| `spring.kafka.listener` Timer | Thời gian gọi listener, result success/failure |
| Kafka consumer fetch metrics | Fetch latency, fetch rate, records consumption |
| Kafka consumer group/coordinator metrics | Rebalance, commit, heartbeat theo metrics client |
| Consumer lag | Chênh lệch giữa vị trí xử lý và log-end offsets |
| `spring.kafka.template` Timer | Hoạt động gửi record qua KafkaTemplate |
| Retry/DLT application metrics | Lượt retry, recoveries, DLT volume |
| Business metrics | Số đơn hàng được áp dụng, số thanh toán thành công |

Spring Kafka cung cấp `MicrometerConsumerListener` và `MicrometerProducerListener` cho producer/consumer factories, giúp bind Kafka client metrics vào MeterRegistry theo lifecycle clients.

Ví dụ cấu hình consumer factory có listener metrics riêng:

~~~java
@Bean
ConsumerFactory<String, OrderEvent> consumerFactory(
        KafkaProperties kafkaProperties,
        MeterRegistry registry) {

    Map<String, Object> config =
            kafkaProperties.buildConsumerProperties();

    var factory =
        new DefaultKafkaConsumerFactory<String, OrderEvent>(config);

    factory.addListener(
        new MicrometerConsumerListener<String, OrderEvent>(registry)
    );

    return factory;
}
~~~

Ví dụ này minh họa hướng wiring với Spring Boot; method `buildConsumerProperties`/constructor overload có thể thay đổi theo phiên bản Boot/Spring Kafka. Trong ứng dụng thật, nếu Boot đã cấu hình consumer factory và các listeners, nên tái sử dụng factory hiện có thay vì tạo factory mới làm mất các tùy chỉnh SerDe, auth hoặc error handling.

**Listener timers không thay thế Kafka client metrics.** Một listener chạy 20 ms nhưng poll/fetch bị nghẽn 10 giây sẽ trông nhanh trong Timer nhưng pipeline vẫn có throughput thấp.

## 21. Timer không đo end-to-end latency

Ví dụ timeline cho một event:

~~~text
12:00:00 Producer publish event
12:00:01 Kafka broker lưu record
12:02:31 Consumer nhận record do backlog
12:02:31.020 Listener xử lý xong
12:02:31.040 Offset commit hoàn tất
~~~

Timer listener có thể ghi khoảng **20 ms**, trong khi độ trễ từ publish đến business completion vào khoảng **151 giây**.

Để giám sát end-to-end latency:

1. Producer gắn event timestamp hoặc business `occurredAt` có semantics rõ.
2. Consumer đo thời gian từ timestamp đó đến khi business work đã hoàn tất.
3. Phân biệt event timestamp với Kafka `CreateTime` và `LogAppendTime`.
4. Theo dõi clock skew và timestamp không tin cậy từ upstream.
5. Nếu record đi qua retry topic, giữ original event timestamp và event ID.
6. Không dùng end-to-end latency này thay cho listener Timer; hai phép đo phục vụ các chẩn đoán khác nhau.

Nếu listener có downstream async task trả về trước khi task hoàn tất, Timer có thể phản ánh thời gian invocation chứ không phản ánh toàn bộ side effect. Hành vi của async listener instrumentation cần kiểm tra theo phiên bản và API sử dụng.

## 22. Timer với DefaultErrorHandler và retries

Một record lỗi có thể được gọi listener nhiều lần:

~~~text
Record A, attempt 1 -> listener throws -> failure timer +1
        |
        v
Backoff
        |
Record A, attempt 2 -> listener throws -> failure timer +1
        |
        v
Backoff
        |
Record A, attempt 3 -> listener success -> success timer +1
~~~

Khi đó Timer count có **3 listener invocations** cho **một business event**. Tỷ lệ success/failure ở đây tính theo invocations, không phải tỷ lệ event cuối cùng thành công sau retry.

Nếu record bị gửi DLT sau hết attempts, các failure invocations vẫn có thể làm failure Timer tăng; việc DLT publish thành công không biến những invocation đã ném exception thành success timer.

Để đo retry một cách chính xác cần thêm:

- Retry attempt count theo exception class.
- Số unique events được recover thành công.
- Số events vào DLT.
- Tổng thời gian hoàn tất từ original event đến terminal outcome.
- Số duplicate/re-delivery phát hiện bởi idempotency.
- Delay và backlog của retry topics nếu dùng non-blocking retry.

Với `DefaultErrorHandler`, một số thời gian backoff nằm **ngoài** listener method invocation, nên đừng cộng Timer duration như thể đã bao trùm toàn bộ retry delay.

## 23. Timer trong non-blocking retry topics

Khi dùng `@RetryableTopic`, record được forward qua original topic và retry topics. Mỗi retry listener/container có thể tạo timers riêng.

~~~text
orders (original listener timer)
    |
    +-- failure --> orders-retry-1000 (retry listener timer)
                       |
                       +-- failure --> orders-retry-2000 (retry listener timer)
                                          |
                                          +-- DLT
~~~

Một business event xuất hiện trên nhiều topic sẽ có nhiều listener invocations ở các stages khác nhau. Timer metric đo từng invocation, không liên kết các records đó thành một workflow end-to-end.

Các hệ quả:

- Dashboard chỉ xem timer của topic gốc có thể bỏ sót retry stage đang lỗi.
- Timer ở retry listener có thể nhanh nhưng backlog cao vì delay chưa đến hạn.
- Một record sau retry có thể chạy sau record mới, ảnh hưởng ordering; Timer không thể phát hiện sai thứ tự nghiệp vụ.
- DLT consumer có timers riêng nếu được đăng ký listener container.
- Nếu cùng logical listener ID và nhiều child containers, cần xác định chính xác tag names để không aggregate sai.

Có thể bổ sung static tag `stage` hoặc tách dashboard theo container name, nhưng phải hiểu Spring Kafka tạo retry topic listeners như thế nào trong phiên bản đang triển khai.

## 24. Timer trong batch listener

Với batch listener:

~~~java
@KafkaListener(
    id = "batch-importer",
    topics = "import-events",
    containerFactory = "batchListenerFactory")
public void onBatch(List<ConsumerRecord<String, ImportEvent>> records) {
    importService.applyBatch(records);
}
~~~

Một invocation có thể chứa hàng chục đến hàng trăm Kafka records. Vì vậy:

~~~text
10 batch invocations x 200 records/batch
= 2.000 records được đưa vào listener

Timer count tăng khoảng 10, không phải 2.000
(nếu timer ghi theo lần gọi batch listener).
~~~

Không so sánh trực tiếp `spring.kafka.listener` invocation rate của record listener với batch listener mà xem đó là records/second. Có thể đo `batch.size`, batch processing duration và record throughput ở application level.

Nếu một batch chỉ một record lỗi và toàn method ném exception, failure Timer phản ánh **batch invocation thất bại**; không cho biết bao nhiêu records trong batch đã áp dụng side effect. Cần `BatchListenerFailedException`, transaction design và per-record metrics phù hợp để chẩn đoán.

## 25. Chọn tags không làm nổ cardinality

Một lỗi observability phổ biến là đưa mọi ID vào Timer tags:

~~~java
// KHÔNG NÊN: mỗi orderId tạo một tag value mới.
factory.getContainerProperties().setMicrometerTagsProvider(
    record -> Map.of("order_id", String.valueOf(record.key()))
);
~~~

Giả sử service xử lý một triệu order IDs, mỗi order tạo tag `order_id` khác nhau. Nếu nhân thêm result, exception, listener name, pod và histogram buckets, số time series có thể bùng nổ.

Nên:

~~~java
// Tag có tập giá trị được kiểm soát.
factory.getContainerProperties().setMicrometerTagsProvider(
    record -> Map.of("event_kind", eventKind(record))
);
~~~

Đề xuất tag policy:

| Loại | Ví dụ | Nên dùng làm metric tag? |
|---|---|---|
| Ổn định | `environment=prod` | Có |
| Nhóm nhỏ | `event_kind=order_paid` | Có |
| Listener | `name=orders-consumer-0` | Có, theo framework |
| Exception label | `exception=ListenerExecutionFailedException` | Có, theo framework |
| Kafka key | `order-912838` | Không |
| Event ID | UUID riêng mỗi event | Không |
| Offset | `topic-1@12345` | Không |
| Correlation ID | ID riêng mỗi request | Không |
| Raw exception message | Tự do, có thể chứa PII | Không |

Với thông tin cần truy vết một record, dùng log/tracing có correlation ID và giới hạn quyền truy cập, không dùng metrics high cardinality.

## 26. Các nguyên nhân không thấy spring.kafka.listener

Khi không thấy metric trong Prometheus hoặc Actuator:

1. **Không có Micrometer registry phù hợp** trong application context.
2. `micrometerEnabled=false` trong container factory đang thực sự dùng.
3. `observationEnabled=true`, khiến instrumentation chuyển sang Observation với tag conventions khác.
4. Listener chưa được gọi hoặc topic chưa có data.
5. `@KafkaListener` đang dùng factory khác do `containerFactory`/bean name.
6. Prometheus registry dependency hoặc Actuator endpoint chưa được cấu hình.
7. Endpoint `/actuator/prometheus` bị chặn/bị authentication hoặc Prometheus scrape lỗi.
8. Meter filters đã deny metric hoặc rename tags.
9. Metric name khác sau naming conversion, ví dụ `spring_kafka_listener_seconds_count`.
10. `MeterRegistry` không được app tạo hoặc có nhiều registries không khớp điều kiện auto instrumentation.
11. App chạy trong profile khác và metrics export bị disabled.
12. Timer của một child consumer có tag `name` khác expected query.

Đừng tạo Timer thủ công cùng tên ngay khi chưa xác định nguyên nhân; có thể làm hai nguồn cùng ghi metric hoặc tạo các tag sets không tương thích.

## 27. Phân biệt listener timer và CPU/GC latency

Latency của listener tăng không luôn có nghĩa Kafka broker chậm. Một listener bao gồm code Java và các lời gọi service/DB, nên cần đối chiếu:

| Quan sát | Nguyên nhân có thể |
|---|---|
| Timer p99 tăng, DB latency tăng | Database connection/queries chậm |
| Timer p99 tăng, CPU 100% | CPU saturation hoặc thuật toán nặng |
| Timer p99 tăng, GC pauses tăng | Memory pressure/GC |
| Timer failure rate tăng, latency rất ngắn | Fail-fast validation/schema bug |
| Timer failure rate tăng, latency gần timeout | API/DB timeout |
| Timer ổn định nhưng lag tăng | Consumer concurrency/fetch/throughput không đủ |
| Timer thấp, record e2e latency cao | Backlog lớn, retry delay hoặc pause |
| Timer không có sample, containers stopped | Lifecycle/startup problem |
| Timer có success nhưng DB data thiếu | Exception bị nuốt hoặc xử lý async chưa hoàn tất |

Không dùng một metric đơn lẻ để kết luận root cause. Timer là mảnh ghép của bức tranh reliability.

## 28. Ví dụ dashboard thực dụng

Một dashboard cho `order-projection` có thể gồm:

| Panel | Dữ liệu |
|---|---|
| Listener invocations/sec | `spring_kafka_listener_seconds_count` rate |
| Listener success/failure rate | Filter `result` |
| Average listener duration | `_sum / _count` |
| p95/p99 latency | `histogram_quantile` nếu histogram enabled |
| Consumer lag per partition | Client/exporter lag metric |
| Error handler retry count | Application metric/observability |
| DLT volume | DLT producer/consumer counter |
| DB pool utilization | Hikari/DB metrics |
| Consumer rebalance count | Kafka client metrics |
| Idle/non-responsive events | Spring Kafka application event counters |
| End-to-end processing latency | Timestamp-based custom metric |

Các panel cần có thời gian quan sát và dimensionality phù hợp. Một listener có p99 thấp nhưng consumer lag tăng nhanh vẫn có thể cần thêm concurrency/partition capacity. Một listener có lag thấp nhưng failure rate cao có thể đang đưa record vào DLT và khiến topic gốc trông “đã xử lý” dù nghiệp vụ chưa hoàn tất.

## 29. Cảnh báo latency và failure rate

Một alert có thể dựa trên **đồng thời**:

- Failure rate tăng trên một ngưỡng đáng kể.
- Số invocations tối thiểu trong cửa sổ đủ lớn.
- Latency p95/p99 vượt SLO.
- Consumer lag hoặc oldest-record age tăng.
- DLT volume tăng bất thường.

Ví dụ logic quy tắc (khái niệm):

~~~text
IF listener failure ratio > 5%
AND invocation rate >= 10 invocations/s
FOR 5 minutes
THEN alert order-projection owner
~~~

Ngưỡng 5%, 10/s và 5 phút chỉ minh họa, cần chọn dựa trên SLO và lưu lượng thật.

Tránh alert khi traffic quá ít: một lỗi trong tổng hai invocations tạo failure ratio 50% nhưng chưa chắc là sự cố diện rộng. Đồng thời, không bỏ qua một event duy nhất rất quan trọng như thanh toán; lúc đó cần business alert hoặc DLT alarm riêng.

Với histogram percentiles, cần xem kích thước sample và cách bucket được cấu hình trước khi đặt ngưỡng p99.

## 30. Runbook: timer failure tăng sau deploy

1. Xác định `name`, `result`, version/pod và khoảng thời gian tăng lỗi.
2. So sánh các child consumers, topics và partition assignment.
3. Xem exception logs/cause chain vì timer tag `exception` có thể chỉ là wrapper.
4. Kiểm tra schema/serde, DB/API latency, auth và release thay đổi.
5. Xem retry attempts, DLT publishing và số unique events chưa hoàn tất.
6. Kiểm tra listener có bắt exception và đổi semantics success/failure không.
7. Nếu lỗi transient, xác nhận backoff/circuit breaker giảm tải dependency.
8. Nếu payload lỗi permanent, dùng non-retryable classification và DLT đúng policy.
9. Kiểm tra consumer lag có tăng hoặc giảm bất thường.
10. Sau rollback/fix, theo dõi failure rate, end-to-end latency và DLT recovery.

Đừng chỉ giảm timer instrumentation hoặc tắt exception tag để làm dashboard hết đỏ; cần xác định đúng nguyên nhân nghiệp vụ.

## 31. Runbook: timer latency tăng nhưng lag thấp

1. Xác nhận duration tăng ở success hay failure timer.
2. So sánh p95, p99 và average; có nhiều slow invocations hay vài outlier?
3. Kiểm tra DB pool, slow query, lock wait và transaction duration.
4. Kiểm tra HTTP client timeout, retry nội bộ và rate limits.
5. Kiểm tra CPU, GC, memory và thread pool saturation.
6. Kiểm tra batch size/record size có thay đổi không.
7. Kiểm tra metrics có đổi tag/Observation convention sau deploy không.
8. Nếu lag thấp do traffic thấp, đừng kết luận throughput capacity tốt.
9. Kiểm tra business end-to-end latency để phát hiện chờ broker/retry khác.
10. Điều chỉnh concurrency, timeout hoặc code theo nguyên nhân đã xác định.

Cần phân biệt “listener invocation chậm” với “Kafka broker đưa record chậm”. Timer chỉ bao trùm một đoạn trong pipeline.

## 32. Runbook: lag tăng nhưng timer vẫn đẹp

1. Xác định producer ingress rate và consumer record throughput.
2. Kiểm tra số partitions và listener concurrency.
3. Đo poll/fetch latency và Kafka client metrics.
4. Kiểm tra có partition bị hot key/skew không.
5. Kiểm tra consumer paused hoặc error-handler backoff dài.
6. Xem retry topics/DLT có backlog riêng không.
7. Xác nhận listener timer count phản ánh record invocations hay batch invocations.
8. Kiểm tra offset commit latency và rebalance count.
9. Kiểm tra oldest record age và retention budget.
10. Nâng capacity hoặc thay đổi partitioning có kiểm soát thay vì chỉ tối ưu listener method vốn đã nhanh.

Ví dụ: listener xử lý 2 ms/record nhưng chỉ có một partition và ingress quá cao; timer p99 tốt không giúp consumer vượt giới hạn xử lý tuần tự của partition.

## 33. Đo riêng bước nghiệp vụ khi cần chi tiết

Listener timer cho biết thời gian bao trùm một invocation; nếu cần biết chậm ở bước nào, có thể thêm custom Timer cho database/API:

~~~java
@Service
public class OrderProjectionService {

    private final Timer databaseWriteTimer;
    private final OrderRepository repository;

    public OrderProjectionService(
            MeterRegistry registry,
            OrderRepository repository) {

        this.repository = repository;
        this.databaseWriteTimer = Timer.builder("business.order.db.write")
                .description("Duration of order projection DB writes")
                .tag("operation", "upsert")
                .register(registry);
    }

    public void apply(OrderEvent event) {
        databaseWriteTimer.record(() -> repository.apply(event));
    }
}
~~~

Ví dụ đo riêng database write. Nó **không thay thế** `spring.kafka.listener`:

- Listener timer đo toàn method xử lý event.
- Custom Timer đo một bước bên trong method.
- Tổng của các bước không nhất thiết bằng listener duration vì còn serialization, validation, business logic và orchestration.
- Nếu method gọi async và không chờ kết quả, timer có thể chỉ đo thời gian submit task.
- Các tags của custom Timer cũng phải giữ low cardinality.

Nếu đo lường quan trọng liên quan tới database transaction, phải quyết định Timer có đo tới lúc transaction commit hay chỉ thời gian thực thi repository method; proxy transaction boundary có thể ảnh hưởng kết quả.

## 34. Sự khác nhau giữa Timer, Counter và LongTaskTimer

| Instrument | Khi nào dùng? | Ví dụ |
|---|---|---|
| `Timer` | Đếm invocation và đo duration cho tác vụ kết thúc | `spring.kafka.listener` |
| `Counter` | Đếm sự kiện không cần đo duration | Số record vào DLT |
| `Gauge` | Trạng thái tại thời điểm scrape | Queue depth, consumer lag |
| `LongTaskTimer` | Quan sát tác vụ đang chạy lâu, kể cả trước khi kết thúc | Long-running workflow/Observation active timer |
| `DistributionSummary` | Đo phân phối giá trị không phải thời gian | Batch size hoặc payload size |

Micrometer Timer chỉ ghi nhận duration khi sample kết thúc. Nếu listener bị kẹt vô thời hạn, invocation đó có thể chưa được ghi vào Timer; lúc này thread/health/long-task monitoring quan trọng hơn.

Không dùng Timer để đo consumer lag bằng cách ghi “offset difference” dưới đơn vị seconds; dùng công cụ/instrument đúng loại để tránh báo cáo sai.

## 35. Vận hành metrics với nhiều pods và consumer groups

Trong deployment nhiều replicas:

~~~text
order-projection pod-A: orders-consumer-0, orders-consumer-1
order-projection pod-B: orders-consumer-0, orders-consumer-1
order-projection pod-C: orders-consumer-0, orders-consumer-1
~~~

Các pods có thể cùng `name` tag, nhưng Prometheus gắn thêm target labels như `instance`, `job`, `pod`. Khi aggregate, xác định rõ mục tiêu:

- Theo pod: phát hiện một instance chậm hơn instance khác.
- Theo logical listener: đo tổng invocations/failure across replicas.
- Theo consumer child: phát hiện hot partition/thread.
- Theo business domain: so sánh các pipelines có SLO khác nhau.

Không xóa bỏ `instance` quá sớm khi điều tra một pod. Ngược lại, khi xây error ratio cấp service, cần aggregate đúng các instances và tags để không tính trung bình của các tỷ lệ một cách sai lệch.

Nếu có thay đổi số lượng pods trong cửa sổ Prometheus, rate phải được tính trên counter riêng từng series rồi mới sum. Không cộng raw counter trước rồi mới lấy rate khi replicas restart ở những thời điểm khác nhau.

## 36. Bảo mật và chi phí của metrics

Mặc dù Timer không mang business payload, tag names có thể tiết lộ tên domain, service, listener và exception. Vì vậy:

- Bảo vệ Actuator/Prometheus endpoint bằng network policy và quyền truy cập.
- Không đưa PII, event ID, order ID, auth token hoặc raw exception message vào tags.
- Kiểm soát histogram buckets, number of series và retention Prometheus.
- Dùng sampling hoặc aggregation phù hợp khi cần tracing chi tiết.
- Quan sát overhead khi tăng số dynamic tag values.
- Quản lý dashboard và alert rules như code/config có review.
- Khi migration sang Observation, kiểm tra các tag names thay vì chỉ so sánh metric names.

Một hệ thống monitoring quá nhiều series có thể tiêu tốn memory của chính consumer và gây pressure lên metrics backend, đi ngược mục tiêu reliability.

## 37. Checklist triển khai Micrometer consumer timers

- [ ] Có Micrometer và `MeterRegistry` phù hợp trong application context.
- [ ] Container đang dùng `micrometerEnabled=true` hoặc đã chọn Observation mode rõ ràng.
- [ ] Biết timer name `spring.kafka.listener` và các tags `name`, `result`, `exception`.
- [ ] Hiểu một concurrent listener có timers theo từng child thread.
- [ ] Phân biệt listener invocation count với unique business events và batch record count.
- [ ] Có static tags ổn định; dynamic tags chỉ lấy từ tập giá trị đã whitelist.
- [ ] Không dùng event ID, offset, Kafka key hoặc message text làm metric label.
- [ ] Actuator/Prometheus có registry/exporter và endpoint scrape an toàn.
- [ ] Histogram chỉ bật khi cần p95/p99 và đã tính chi phí cardinality.
- [ ] Dashboard có invocation rate, failure rate, average và tail latency.
- [ ] Có consumer lag, Kafka client metrics, retry/DLT và business success metrics bổ sung.
- [ ] Không gọi Timer duration là end-to-end latency.
- [ ] Không coi timer success là bằng chứng DB/HTTP side effect đã commit.
- [ ] Nếu dùng Observation, kiểm tra conventions và phiên bản cho batch listener.
- [ ] Alert có minimum traffic, duration window và runbook tương ứng.
- [ ] Có quy trình xác minh metrics khi upgrade Spring Kafka hoặc Micrometer.

## 38. Nguồn tham khảo

- [Spring Kafka Reference — Monitoring](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring Kafka Reference — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring Kafka Reference — Micrometer Observation Documentation](https://docs.spring.io/spring-kafka/reference/appendix/micrometer.html)
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)

**Kết luận:** Micrometer consumer timers của Spring Kafka cung cấp một phép đo chuẩn, chi phí vận hành hợp lý về **thời gian và kết quả mỗi lần gọi listener**. Dùng `spring.kafka.listener` cùng các tags `name`, `result` và `exception` để quan sát success/failure và latency; bổ sung static/dynamic tags có kiểm soát khi cần phân nhóm. Tuy nhiên, timer không đo consumer lag, thời gian chờ retry, hiệu quả exactly-once hoặc end-to-end business latency. Với hệ thống reliability, cần kết hợp listener timers với Kafka client metrics, retry/DLT, consumer group state, dependency health và business telemetry; đồng thời thống nhất lựa chọn giữa legacy timers và Micrometer Observation theo phiên bản Spring Kafka đang triển khai.
