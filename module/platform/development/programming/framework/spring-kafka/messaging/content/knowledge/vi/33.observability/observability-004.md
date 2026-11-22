# Micrometer metrics cho Kafka

Micrometer cung cấp API thống nhất để thu thập metrics trong ứng dụng Spring. Khi kết hợp với Spring Kafka, ứng dụng có thể đo thời gian gửi record qua `KafkaTemplate`, thời gian xử lý của `@KafkaListener`, trạng thái producer/consumer Kafka client và các chỉ số nghiệp vụ do chính ứng dụng tạo ra.

Metrics giúp trả lời những câu hỏi vận hành như: producer gửi được bao nhiêu record mỗi giây, listener xử lý mất bao lâu, consumer có bị lag không, lỗi tăng ở topic nào và throughput có giảm sau một lần deploy không. Spring Kafka còn hỗ trợ Micrometer Observation để kết hợp metrics với tracing khi ứng dụng có `ObservationRegistry` và tracing bridge phù hợp.

## 1. Observability gồm metrics, logs và traces

Ba loại tín hiệu bổ trợ nhau:

| Tín hiệu | Trả lời câu hỏi | Ví dụ trong Kafka |
| --- | --- | --- |
| Metrics | Hệ thống đang hoạt động ở mức tổng thể ra sao? | Records sent/consumed rate, listener latency, consumer lag, error rate |
| Logs | Một lần xử lý cụ thể đã xảy ra điều gì? | Event ID, topic, partition, offset, exception |
| Traces | Một request/event đi qua những service nào và mất thời gian ở đâu? | HTTP request → publish Kafka → consume → database call |

Micrometer chủ yếu cung cấp metrics API và Observation API. Nó không thay thế log nghiệp vụ hoặc distributed tracing backend. Khi bật Observation, ứng dụng có thể tạo span và metrics từ cùng một observation nếu có registry/bridge được cấu hình.

Ví dụ: consumer lag tăng là tín hiệu metrics; log theo `eventId` giúp tìm record lỗi; trace giúp xác định thời gian bị tiêu tốn ở listener, database hay một service downstream.

## 2. Những nguồn metrics trong Spring Kafka

Có thể chia metrics thành ba nhóm:

1. **Spring Kafka operation metrics/observations:** thời gian và kết quả gửi qua `KafkaTemplate`, thời gian listener xử lý record hoặc batch.
2. **Kafka client metrics:** các chỉ số nội bộ do Kafka producer/consumer client cung cấp, như request latency, fetch rate, records consumed, rebalance và lag theo partition.
3. **Business metrics:** số đơn hàng được xử lý, số event bị từ chối, thời gian nghiệp vụ, số lần retry hoặc số record được đưa vào DLT.

```mermaid
flowchart TD
    A[Spring Kafka application] --> B[KafkaTemplate]
    A --> C[@KafkaListener containers]
    A --> D[Business code]
    B --> E[Template metrics / Observation]
    C --> F[Listener metrics / Observation]
    B --> G[Kafka producer client metrics]
    C --> H[Kafka consumer client metrics]
    D --> I[Custom Counter / Timer / Gauge]
    E --> J[Micrometer MeterRegistry]
    F --> J
    G --> J
    H --> J
    I --> J
    J --> K[Prometheus / OTLP / monitoring backend]
```

Không phải mọi phiên bản Spring Kafka đều bật cùng một loại instrumentation theo cùng một cách. Phiên bản framework, Micrometer trên classpath và cấu hình timer/observation quyết định bộ metrics nào được tạo. Hãy kiểm tra phiên bản thực tế và danh sách meter đã đăng ký thay vì giả định tên metric giống nhau giữa các ứng dụng.

## 3. Thêm Micrometer và Actuator

Trong ứng dụng Spring Boot, thường dùng Actuator để quản lý endpoint health/metrics và một registry để xuất dữ liệu đến backend.

Ví dụ Maven dependencies:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Spring Boot dependency management nên quản lý phiên bản Micrometer tương thích với Boot. Tránh tự ghim một phiên bản `micrometer-core` khác với phiên bản do Spring Boot quản lý nếu không có lý do cụ thể.

Nếu không dùng Spring Boot, cần khai báo `MeterRegistry` phù hợp và cấu hình exporter/registry tương ứng. Spring Kafka có thể tích hợp với Micrometer khi các dependency và registry cần thiết có mặt.

## 4. Expose metrics cho Prometheus

Với Prometheus registry, có thể expose endpoint `/actuator/prometheus`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
  prometheus:
    metrics:
      export:
        enabled: true
```

Sau khi ứng dụng khởi động, kiểm tra các endpoint:

```text
GET /actuator/health
GET /actuator/metrics
GET /actuator/metrics/{metric-name}
GET /actuator/prometheus
```

`/actuator/metrics` liệt kê meter name; `/actuator/metrics/{metric-name}` hiển thị meter và các tag hiện có; `/actuator/prometheus` xuất dữ liệu ở định dạng Prometheus scrape. Chỉ expose endpoint cần thiết và bảo vệ chúng bằng network policy, authentication hoặc management port riêng.

Ví dụ Prometheus scrape config:

```yaml
scrape_configs:
  - job_name: spring-kafka-messaging
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - orders-service:8080
          - billing-service:8080
```

Trong production, dùng service discovery thay vì danh sách host tĩnh nếu môi trường có autoscaling. Endpoint metrics có thể chứa thông tin vận hành nội bộ; không mở công khai trên Internet.

## 5. Metrics và Observation cho KafkaTemplate

`KafkaTemplate` gửi record và có thể cung cấp thời gian gửi, kết quả gửi và exception. Ở các phiên bản Spring Kafka hỗ trợ Micrometer timers, template có thể ghi timer cho thao tác send. Các phiên bản hỗ trợ Observation cho phép bật observation trên template để tích hợp với `ObservationRegistry`.

Với Spring Boot phiên bản hỗ trợ property này, có thể bật observation cho template:

```yaml
spring:
  kafka:
    template:
      observation-enabled: true
```

Khi tự tạo `KafkaTemplate`, có thể bật bằng API tương ứng:

```java
import com.example.messaging.event.OrderEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Bean
public KafkaTemplate<String, OrderEvent> orderKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory
) {
    KafkaTemplate<String, OrderEvent> template =
            new KafkaTemplate<>(producerFactory);
    template.setObservationEnabled(true);
    return template;
}
```

Observation cho phép thu thập thời gian và kết quả publish, đồng thời tạo tracing span nếu ứng dụng cấu hình tracing bridge/exporter. Tên observation mặc định của Spring Kafka có thể được dùng để tìm timer tương ứng trong registry; tên meter Prometheus là tên đã được registry chuẩn hóa.

Nếu dùng Micrometer timer API kiểu cũ thay vì Observation, kiểm tra `micrometerEnabled` và các API `setMicrometerEnabled`/tags tương ứng của phiên bản Spring Kafka. Không bật instrumentation trùng lặp một cách vô ý; chọn cơ chế phù hợp với version và kiểm tra meter thực tế.

## 6. Metrics và Observation cho @KafkaListener

Listener container có thể ghi thời gian xử lý và kết quả listener. Với Spring Boot phiên bản hỗ trợ cấu hình listener observation:

```yaml
spring:
  kafka:
    listener:
      observation-enabled: true
```

Với container factory tự cấu hình, bật observation trên `ContainerProperties`:

```java
import com.example.messaging.event.OrderEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory
        ) {
    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties().setObservationEnabled(true);
    return factory;
}
```

Với record listener, instrumentation đo thời gian xử lý listener invocation. Với batch listener, thời gian thường phản ánh lần xử lý batch; hãy diễn giải metric theo loại listener đã cấu hình.

Khi bật Observation, listener có thể tạo span gắn với message processing. Việc truyền trace context qua Kafka headers phụ thuộc observation/tracing instrumentation và cấu hình propagator; không nên tự giả định trace context luôn có mặt nếu chỉ thêm Actuator.

## 7. Native Kafka client metrics

Kafka producer và consumer có bộ metrics riêng do Kafka client cung cấp. Chúng giúp quan sát các hoạt động thấp hơn mức listener như fetch, request, network, batch và rebalance.

Producer metrics thường quan tâm:

| Metric Kafka client | Ý nghĩa |
| --- | --- |
| `record-send-rate` | Tốc độ record được gửi |
| `record-error-rate` | Tốc độ gửi record gặp lỗi |
| `request-latency-avg` / `request-latency-max` | Độ trễ request đến broker |
| `record-queue-time-avg` | Thời gian record chờ trong producer trước khi gửi |
| `batch-size-avg` | Kích thước batch gửi trung bình |
| `buffer-available-bytes` | Dung lượng buffer producer còn khả dụng |
| `bufferpool-wait-time-total` | Thời gian producer chờ buffer pool |
| `outgoing-byte-rate` | Tốc độ byte gửi ra |

Consumer metrics thường quan tâm:

| Metric Kafka client | Ý nghĩa |
| --- | --- |
| `records-consumed-rate` | Tốc độ record được consume |
| `bytes-consumed-rate` | Tốc độ byte nhận về |
| `fetch-rate` / `fetch-latency-avg` | Tốc độ và độ trễ fetch |
| `records-lag-max` | Lag lớn nhất theo partition trong tập metric tương ứng |
| `assigned-partitions` | Số partition được assign cho consumer |
| `commit-latency-avg` | Độ trễ commit offset |
| `heartbeat-rate` | Tần suất heartbeat |
| `rebalance-total` | Số lần rebalance đã xảy ra |

Tên metric gốc ở Kafka client có thể được đổi format/tag khi export qua Micrometer. Một số metric được ghi ở mức producer/consumer instance hoặc partition; không cộng chúng tùy tiện nếu chưa hiểu phạm vi đo.

## 8. Đăng ký KafkaClientMetrics cho producer và consumer

Micrometer cung cấp `KafkaClientMetrics` binder để bind metrics của Kafka client vào `MeterRegistry`. Spring Kafka cũng có các listener hỗ trợ tự động bind/unbind metrics khi factory tạo và đóng producer/consumer.

Ví dụ với `MicrometerConsumerListener` và `MicrometerProducerListener`:

```java
package com.example.messaging.config;

import com.example.messaging.event.OrderEvent;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.MicrometerConsumerListener;
import org.springframework.kafka.core.MicrometerProducerListener;

@Configuration
public class KafkaClientMetricsConfiguration {

    @Bean
    public MicrometerConsumerListener<String, OrderEvent>
            consumerMetricsListener(MeterRegistry registry) {
        return new MicrometerConsumerListener<>(registry);
    }

    @Bean
    public MicrometerProducerListener<String, OrderEvent>
            producerMetricsListener(MeterRegistry registry) {
        return new MicrometerProducerListener<>(registry);
    }
}
```

Các listener cần được gắn vào đúng factory:

```java
consumerFactory.addListener(consumerMetricsListener);
producerFactory.addListener(producerMetricsListener);
```

Nếu Spring Boot đã tự động gắn Micrometer listeners cho các factory auto-configured trong phiên bản đang dùng, không đăng ký trùng. Với factory tự tạo, kiểm tra integration hiện có và gắn listener nếu cần. Các class/API cụ thể cần khớp Spring Kafka/Micrometer version của ứng dụng.

Một cách khác là tạo `KafkaClientMetrics` từ Kafka `Producer`/`Consumer` instance rồi gọi `bindTo(registry)`. Nếu tự bind trực tiếp, phải quản lý vòng đời binder và unbind/close khi client đóng; tránh tạo binder cho client đã bị đóng hoặc bind nhiều lần cùng một client.

## 9. Đo thời gian xử lý nghiệp vụ bằng Timer

Metrics mặc định cho biết thời gian listener invocation, nhưng đôi khi cần đo riêng một bước nghiệp vụ như ghi invoice hoặc gọi Pricing service.

```java
package com.example.orders.service;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.function.Supplier;
import org.springframework.stereotype.Service;

@Service
public class OrderProcessingMetrics {

    private final MeterRegistry registry;

    public OrderProcessingMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T recordProcessing(String result, Supplier<T> operation) {
        return Timer.builder("orders.kafka.processing")
                .description("Thời gian xử lý nghiệp vụ Order event")
                .tag("result", result)
                .register(registry)
                .record(operation);
    }
}
```

`Timer.record(Supplier<T>)` đo thời gian thực thi operation và trả kết quả của supplier. Với code có exception, timer vẫn ghi thời gian của lần gọi; hãy thiết kế tag result để phân biệt success/error mà không đưa exception message động vào tag.

Ví dụ sử dụng:

```java
package com.example.orders.service;

import com.example.orders.metrics.OrderProcessingMetrics;

OrderResult result = metrics.recordProcessing(
        "success",
        () -> orderService.apply(event)
);
```

Nếu cần đo cả success và failure chính xác, dùng `Timer.Sample` rồi dừng timer trong `finally` với tag kết quả đã xác định. Không tạo một Timer mới cho từng event; `Timer.builder(...).register(registry)` trả lại meter đã đăng ký với cùng bộ tên/tag.

## 10. Counter cho số lượng event và lỗi

Counter phù hợp để đếm sự kiện tích lũy như số event xử lý thành công, số event bị từ chối hoặc số lần gửi vào DLT.

```java
package com.example.orders.metrics;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class OrderEventMetrics {

    private final Counter processed;
    private final Counter failed;

    public OrderEventMetrics(MeterRegistry registry) {
        this.processed = Counter.builder("orders.kafka.processed")
                .description("Số Order event xử lý thành công")
                .register(registry);
        this.failed = Counter.builder("orders.kafka.failed")
                .description("Số Order event xử lý thất bại")
                .register(registry);
    }

    public void markProcessed() {
        processed.increment();
    }

    public void markFailed() {
        failed.increment();
    }
}
```

Counter tăng đơn điệu trong vòng đời process; khi process restart, giá trị trong memory có thể bắt đầu lại. Prometheus lưu chuỗi thời gian và xử lý counter reset khi query `rate()`/`increase()`.

Nên tăng counter tại đúng ranh giới nghiệp vụ: ví dụ chỉ tăng `processed` sau khi side effect thành công. Nếu listener có thể nhận lại cùng record, counter invocation và counter event unique là hai khái niệm khác nhau. Dùng tên metric rõ ràng để tránh diễn giải số lần listener chạy như số event duy nhất.

## 11. Gauge cho trạng thái đang chờ

Gauge đo một giá trị có thể tăng hoặc giảm, ví dụ số công việc đang nằm trong queue nội bộ hoặc số request-reply đang chờ.

```java
package com.example.orders.metrics;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class PendingWorkMetrics {

    private final AtomicInteger pending = new AtomicInteger();

    public PendingWorkMetrics(MeterRegistry registry) {
        Gauge.builder("orders.kafka.pending", pending, AtomicInteger::get)
                .description("Số công việc đang chờ xử lý trong ứng dụng")
                .register(registry);
    }

    public void started() {
        pending.incrementAndGet();
    }

    public void completed() {
        pending.decrementAndGet();
    }
}
```

Giữ reference đến object mà Gauge quan sát; nếu object bị garbage collected, Gauge có thể không còn cung cấp giá trị như mong đợi. Cập nhật gauge trong mọi đường kết thúc, kể cả exception/cancel, để tránh số pending bị tăng mãi.

Không dùng Gauge để đếm tổng event đã xử lý; Counter phù hợp hơn cho giá trị tích lũy.

## 12. DistributionSummary cho batch size

Nếu listener nhận batch, `DistributionSummary` giúp đo phân phối số record trong mỗi batch:

```java
package com.example.audit.metrics;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class AuditBatchMetrics {

    private final DistributionSummary batchSize;

    public AuditBatchMetrics(MeterRegistry registry) {
        this.batchSize = DistributionSummary.builder("audit.kafka.batch.size")
                .description("Số record trong mỗi batch listener")
                .baseUnit("records")
                .register(registry);
    }

    public void recordBatch(int size) {
        batchSize.record(size);
    }
}
```

Từ distribution có thể quan sát batch size trung bình, max và histogram nếu registry được cấu hình. Kết hợp với listener processing timer để xem batch lớn có làm tăng latency hay không.

## 13. Consumer lag và partition-level metrics

Consumer lag là khoảng cách giữa vị trí record mới nhất của partition và tiến độ consumer group. Lag tăng liên tục có thể cho biết consumer không theo kịp producer.

Lag cần được quan sát theo partition và theo consumer group. Kafka client có metric lag ở cấp consumer/partition trong một số phiên bản, nhưng không phải lúc nào cũng thay thế được metric group lag tổng hợp. Có thể dùng Kafka exporter, JMX exporter hoặc công cụ monitoring của Kafka platform để thu thập group lag và log end offset.

CLI giúp kiểm tra khi điều tra:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service
```

Các cột `CURRENT-OFFSET`, `LOG-END-OFFSET` và `LAG` giúp thấy partition nào đang chậm. Hãy kết hợp với metrics ứng dụng như processing time, records consumed rate và downstream latency để tìm nguyên nhân.

Lag không phải lúc nào cũng là lỗi. Một đợt traffic burst có thể làm lag tăng ngắn hạn rồi giảm. Cần theo dõi xu hướng, tốc độ tăng lag và thời gian phục hồi thay vì alert chỉ vì lag khác 0.

## 14. Tags và cardinality

Tag cho phép phân nhóm metric theo thuộc tính có tập giá trị giới hạn, ví dụ topic, listener ID, group ID, result hoặc exception class.

Tag phù hợp:

- `topic=orders.events`
- `group=orders-service`
- `listener=ordersListener`
- `result=success|failure`
- `exception=TimeoutException`

Không nên dùng giá trị thay đổi theo từng record làm tag:

- `eventId`
- `orderId`
- `customerId`
- `correlationId`
- email hoặc user ID
- exception message có nội dung động

Mỗi tổ hợp tag tạo một time series. Nếu gắn `orderId` làm tag, số series có thể tăng theo số đơn hàng và làm Prometheus/Micrometer tiêu tốn nhiều RAM, CPU và storage.

Chỉ dùng exception class hoặc nhóm lỗi đã chuẩn hóa; không dùng stack trace/message làm tag. Với topic động hoặc tenant lớn, hãy đánh giá cardinality trước khi đưa vào metric tags.

## 15. Custom Observation convention và trace context

Observation cho phép gắn thông tin ngữ cảnh vào một operation. Spring Kafka cung cấp convention mặc định và API để thay đổi convention/tag theo nhu cầu.

Ví dụ minh họa một custom convention ở mức ý tưởng:

```java
template.setObservationConvention(customKafkaTemplateObservationConvention);
```

Convention nên bổ sung low-cardinality key-value như tên luồng nghiệp vụ hoặc loại event đã chuẩn hóa. Không đưa `eventId` hoặc `orderId` vào low-cardinality tags. Nếu cần giá trị duy nhất để điều tra, đặt chúng trong log hoặc trace span event/attribute có chính sách giới hạn phù hợp, không biến thành metric label.

Khi tracing được cấu hình, trace context có thể được truyền qua Kafka headers để nối producer span và consumer span. Hãy kiểm tra propagation trên đúng phiên bản Spring Kafka, Micrometer Observation và tracing bridge; nếu tự sửa headers, không ghi đè trace context do framework quản lý.

## 16. PromQL cơ bản cho Kafka application metrics

Với custom Counter `orders.kafka.processed`, Prometheus thường chuẩn hóa tên thành `orders_kafka_processed_total`. Có thể dùng:

```promql
sum(rate(orders_kafka_processed_total[5m]))
```

Để xem tốc độ xử lý lỗi:

```promql
sum(rate(orders_kafka_failed_total[5m]))
```

Nếu Timer `orders.kafka.processing` được export thành histogram, có thể tính p95:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(orders_kafka_processing_seconds_bucket[5m])
  )
)
```

Tên metric cuối cùng phụ thuộc registry, naming convention và cấu hình histogram. Kiểm tra `/actuator/prometheus` để xác nhận metric name thực tế trước khi viết dashboard/alert.

Để xuất histogram bucket cho Timer trong Spring Boot, có thể bật percentile histogram theo tên meter:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        orders.kafka.processing: true
```

Nếu không bật histogram (hoặc không cấu hình percentile phù hợp), metric `_bucket` có thể không được export và truy vấn `histogram_quantile` ở trên sẽ không có dữ liệu. Histogram tạo thêm time series; chỉ bật cho các timer cần phân tích percentile và kiểm soát số lượng tag.

Ví dụ cảnh báo đơn giản cho error rate:

```promql
sum(rate(orders_kafka_failed_total[5m])) > 1
```

Trong production, nên so sánh error rate với throughput hoặc dùng tỷ lệ lỗi thay vì ngưỡng tuyệt đối khi tải thay đổi lớn.

## 17. Dashboard nên có gì?

Một dashboard Kafka service có thể chia thành các hàng:

| Nhóm | Panel gợi ý |
| --- | --- |
| Producer | Send rate, send error rate, request latency, outgoing bytes |
| Consumer | Records consumed rate, fetch latency, assigned partitions, rebalance |
| Listener | Processing duration p50/p95/p99, success/failure count, batch size |
| Lag | Consumer group lag tổng và lag theo partition |
| Retry/DLT | Retry rate, DLT publish rate, DLT backlog |
| Business | Orders processed, payment rejected, inventory update failures |
| Runtime | CPU, heap, GC pause, thread count, connection pool usage |

Dashboard cần có bộ lọc theo service, environment, topic và consumer group. Tránh tạo dashboard với hàng nghìn series theo event ID hoặc entity ID.

## 18. Lỗi thường gặp khi dùng Micrometer với Kafka

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không thấy metric Kafka | Chưa có registry/Micrometer dependency hoặc instrumentation chưa bật | Kiểm tra dependency, MeterRegistry và config template/container |
| Có listener timer nhưng không có client metrics | Chưa bind `KafkaClientMetrics`/factory listener hoặc Boot version không tự cấu hình | Kiểm tra producer/consumer factory và Micrometer listener |
| Metric trùng lặp | Bật cả legacy timers và Observation/custom timer cho cùng operation | Kiểm tra meter name và chọn instrumentation phù hợp |
| Prometheus không scrape được | Endpoint chưa expose, sai port/path hoặc network policy | Kiểm tra Actuator exposure và scrape target |
| Cardinality tăng bất thường | Dùng ID động làm tag | Bỏ event/entity ID khỏi tags; dùng logs/traces |
| Consumer lag không hiển thị | Chỉ bật listener timer, chưa có group lag exporter/client metric | Bổ sung Kafka exporter/JMX hoặc nguồn group lag |
| Timer không có histogram | Chưa bật percentile histogram hoặc registry không xuất bucket | Cấu hình histogram theo nhu cầu và kiểm tra endpoint |
| Gauge luôn bằng 0 | Gauge quan sát object không còn reference hoặc cập nhật sai | Giữ object sống và kiểm tra increment/decrement |
| Metrics không khớp record unique | Counter tăng theo invocation, bao gồm redelivery | Phân biệt invocation count và business event unique |
| Tracing không nối producer-consumer | Observation/tracing bridge hoặc propagation chưa cấu hình | Kiểm tra registry, propagator và Kafka headers |

## 19. Kiểm thử metrics

Không cần chạy Kafka broker thật cho mọi unit test metrics. Có thể dùng `SimpleMeterRegistry` để kiểm tra custom Counter, Timer, Gauge và DistributionSummary.

Ví dụ:

```java
package com.example.orders.metrics;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class OrderEventMetricsTest {

    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();
    private final OrderEventMetrics metrics = new OrderEventMetrics(registry);

    @Test
    void incrementsProcessedCounter() {
        metrics.markProcessed();
        metrics.markProcessed();

        assertThat(registry.get("orders.kafka.processed")
                .counter().count()).isEqualTo(2.0);
    }
}
```

Với integration test Spring Kafka, có thể xác minh template/listener observation hoặc timer được đăng ký khi gửi/nhận record. Dùng `MeterRegistry` thật trong test context và chờ listener xử lý hoàn tất trước khi assert.

Những điểm nên kiểm tra:

1. Gửi record thành công làm tăng send/processed metrics theo kỳ vọng.
2. Producer failure hoặc listener exception tạo result/error metric phù hợp.
3. Timer có count và total time sau operation.
4. Tags chỉ chứa giá trị có cardinality kiểm soát.
5. Consumer metrics được unbind khi factory đóng client nếu dùng factory listeners.
6. Prometheus endpoint xuất đúng metric name và labels.
7. Observation/tracing không tạo span thiếu context hoặc tag nhạy cảm.

Không assert thời gian chính xác đến millisecond trong test; chỉ kiểm tra timer được ghi nhận và có count hợp lý.

## 20. Checklist triển khai

Trước khi đưa Micrometer metrics cho Kafka vào production, hãy xác nhận:

1. Spring Boot, Spring Kafka và Micrometer versions tương thích.
2. Actuator và registry/exporter cần thiết đã được khai báo.
3. Endpoint metrics/Prometheus chỉ expose trong phạm vi được bảo vệ.
4. Đã quyết định dùng Micrometer timers hay Observation theo khả năng version.
5. `KafkaTemplate` và listener container được instrument đúng.
6. Native Kafka producer/consumer metrics được bind nếu cần theo dõi client internals.
7. Custom Counter/Timer/Gauge đo đúng ranh giới nghiệp vụ.
8. Consumer lag có nguồn đo phù hợp ở cấp group/partition.
9. Tags có cardinality thấp; không dùng event ID hoặc entity ID.
10. Dashboard hiển thị throughput, latency, errors, lag, retry/DLT và runtime.
11. Alert phân biệt lỗi kéo dài với traffic burst ngắn.
12. Có test cho custom metrics và integration metrics.
13. Có log/traces để điều tra từng event khi metrics phát hiện bất thường.

Micrometer giúp Spring Kafka đưa hoạt động gửi, nhận và xử lý event vào cùng hệ thống metrics của ứng dụng. Kết hợp timer/observation của Spring Kafka, metrics gốc của Kafka client và business metrics, đội vận hành có thể quan sát throughput, latency, lỗi, rebalance và consumer lag. Hãy giữ tag cardinality thấp, chọn instrumentation phù hợp phiên bản và kết hợp metrics với log/tracing để điều tra được cả xu hướng tổng thể lẫn một event cụ thể.

## 21. Tự kiểm tra

1. Metrics, logs và traces trả lời những câu hỏi khác nhau nào khi vận hành Kafka?
2. Spring Kafka operation metrics khác native Kafka client metrics ở điểm nào?
3. Khi nào nên bật Observation cho `KafkaTemplate` và listener container?
4. `KafkaClientMetrics` hoặc Micrometer factory listeners giúp thu thập những thông tin nào?
5. Khi nào nên dùng Counter, Timer, Gauge và DistributionSummary?
6. Vì sao không nên dùng `eventId` hoặc `orderId` làm metric tag?
7. Listener processing time khác consumer lag như thế nào?
8. Vì sao consumer lag cần được xem theo group và partition?
9. Làm thế nào để kiểm tra metric name thực tế được export sang Prometheus?
10. Vì sao metrics cần được kết hợp với logs và traces khi điều tra một event lỗi?
