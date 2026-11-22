# Cấu hình metrics và observation trong Spring Kafka

## 1. Metrics và observation giải quyết vấn đề gì?

Trong hệ thống Kafka, một service có thể vẫn đang chạy, không xuất hiện exception trong log, nhưng **consumer lag** tăng liên tục, producer gửi chậm hoặc listener lặp lại cùng một message do retry. Nếu chỉ nhìn log `"message received"` hoặc trạng thái HTTP health `UP`, rất khó xác định nguyên nhân và mức độ ảnh hưởng.

Với **Spring Kafka Reliability Operations**, việc cấu hình metrics và observation giúp trả lời các câu hỏi vận hành:

- Producer có gửi bản ghi đến broker thành công không? Độ trễ xác nhận và tỷ lệ lỗi có tăng?
- Consumer có đang đọc dữ liệu, nhận partition assignment và commit offset đúng không?
- Kafka broker, network hoặc client có đang tạo bottleneck?
- Listener mất bao lâu để xử lý một record? Có bao nhiêu record thất bại, được retry hoặc chuyển đến dead-letter topic?
- Một sự kiện mất thời gian ở bước nào trên đường đi từ HTTP/API → Kafka → database → Kafka tiếp theo?
- Khi ứng dụng được deploy lại, consumer có bị rebalance lâu, lag tăng bất thường hoặc mất khả năng xử lý?
- Khi metric báo xấu, làm sao đi từ dashboard tới trace và log cụ thể mà không tạo high-cardinality labels?

Một kiến trúc observability thực tế gồm **metrics, traces và logs**, nhưng ba loại tín hiệu này có mục đích khác nhau:

| Tín hiệu | Ví dụ | Mục đích |
|---|---|---|
| **Metrics** | Record rate, consumer lag, error count, processing latency | Xu hướng, cảnh báo, công suất |
| **Traces** | Span publish Kafka → consume Kafka → gọi database | Theo dõi một luồng xử lý xuyên dịch vụ |
| **Logs** | Event ID, exception type, topic/partition/offset | Điều tra trường hợp cụ thể |
| **Audit/business result** | Payment đã commit, event đã vào outbox, số duplicate | Chứng minh kết quả nghiệp vụ |

**Observation không đồng nghĩa business success.** Một span kết thúc không chứng minh database đã commit, Kafka offset đã được lưu, hay một sự kiện chỉ được xử lý đúng một lần. Muốn khẳng định các điều đó cần đọc thêm trạng thái giao dịch, offset, outbox/inbox và bộ đếm nghiệp vụ.

### Phạm vi kỹ thuật

Các đoạn ví dụ chủ yếu dựa trên **Spring Boot 3.x, Spring Kafka 3.x, Java 17+, Micrometer 1.x**. Spring Boot và Spring Kafka liên tục bổ sung tính năng; tên property, metric và tag cần được đối chiếu với **phiên bản thật** đang sử dụng. Ví dụ sử dụng Kafka producer/consumer dạng `String` để tập trung vào instrumentation thay vì serialization.

## 2. Ba lớp đo lường cần tách biệt

Có ba nguồn metric dễ bị gom chung dưới tên “Kafka metrics”:

| Lớp | Sinh dữ liệu ở đâu? | Ví dụ | Điểm mạnh và giới hạn |
|---|---|---|---|
| **Kafka client metrics** | `KafkaProducer` và `KafkaConsumer` | Bytes sent, request latency, records consumed rate, fetch/poll, retry rate | Thấy sức khỏe client/network, không biết business transaction có thành công |
| **Spring Kafka listener/template observations** | `KafkaTemplate` và listener container | Duration gửi qua template, thời gian callback listener, trace context | Gắn Kafka với luồng xử lý ứng dụng, không thay broker-level lag |
| **Kafka cluster/group metrics** | Broker, exporter, Kafka admin/consumer group tooling | Consumer-group lag, under-replicated partitions, request queue, ISR, broker errors | Thấy sức khỏe cluster và backlog chính xác hơn, nhưng không cho biết một item xử lý nghiệp vụ ra sao |

Bên cạnh đó, cần **business metrics** do ứng dụng tự định nghĩa, ví dụ:

```text
payment_event_received_total
payment_event_processed_total
payment_event_duplicate_total
payment_event_failed_total
payment_outbox_pending
payment_dlq_published_total
```

Những tên này là **metric ví dụ của ứng dụng**, không phải metric mặc định Spring Kafka tạo ra.

Sơ đồ:

```text
        Producer Service                     Consumer Service
  +-------------------------+          +------------------------------+
  | business method         |          | @KafkaListener               |
  |      |                  |          |       |                      |
  |      v                  |          |       v                      |
  | KafkaTemplate.send()    |          | validation / DB / outbox     |
  |      |                  |          |       |                      |
  |  Producer client        |          |   Consumer client            |
  +------+------------------+          +-------+----------------------+
         |                                     ^
         v                                     |
  +------+-------------------------------------+---------+
  |                       Kafka cluster                 |
  | Broker metrics / partitions / offsets / ISR / quota |
  +-----------------------------------------------------+

      Micrometer meters + observations + trace context
                         |
                         v
               Actuator / Prometheus
                         |
                    Grafana/Alerts
                         |
                   OTLP tracing
                         |
                 Jaeger/Tempo/other
```

**Quan trọng:** Khi consumer lag tăng, nguyên nhân có thể nằm ở consumer processing, số partition, database downstream, broker/network hoặc chính producer tăng đột biến. Một metric đơn lẻ không xác định nguyên nhân gốc.

## 3. Micrometer Metrics khác Micrometer Observation như thế nào?

**Micrometer Metrics** cung cấp API như `Counter`, `Timer`, `Gauge` và các registry để xuất số liệu sang Prometheus, Datadog, OTLP hoặc backend khác.

**Micrometer Observation** cung cấp một abstraction chung cho **một operation có bắt đầu và kết thúc**, với context, key-values và handler. Tùy các handler/bridge được cấu hình, một observation có thể tạo:

- Timer/metric đo thời lượng.
- Span để đưa vào distributed trace.
- Thông tin trace/span giúp liên kết log.
- Context propagation giữa các bước xử lý có hỗ trợ.

Nhưng có vài khác biệt cần nhớ:

1. **Có Micrometer registry** không có nghĩa distributed tracing tự hoạt động.
2. **Bật Observation trên KafkaTemplate** không làm Kafka broker metric phong phú hơn nếu thiếu Kafka client/broker instrumentation.
3. **Bật tracing exporter** không tự động đo consumer-group lag.
4. Một observation có thể được tạo nhưng không được ghi ra backend vì sampling, handler hoặc exporter chưa đúng.
5. Metrics là các phép đo tổng hợp, còn trace phục vụ từng request/event được lấy mẫu hoặc được ghi theo policy.

### 3.1. Dùng loại metric nào?

| Loại | Dữ liệu | Trường hợp phù hợp |
|---|---|---|
| `Counter` | Tổng số sự kiện tăng dần | Số retry, DLT publish, business failures |
| `Timer` | Số lượt và thời gian thực thi | Listener/process duration, publish latency |
| `Gauge` | Giá trị hiện tại | Queue size, outbox pending, consumer lag từ nguồn đo |
| `DistributionSummary` | Phân bố số lượng/kích thước | Payload bytes, batch record count |
| `LongTaskTimer` | Operation còn đang chạy | Công việc rất dài cần quan sát trước khi kết thúc |

Dùng `Counter` cho số lỗi và `Timer` cho duration thường dễ phân tích hơn tự tạo `Gauge` thay đổi liên tục chỉ để đo tổng lỗi. Ngược lại, backlog/outbox pending nên dùng dạng Gauge hoặc số liệu từ nguồn authoritative.

## 4. Dependency cần có trong Spring Boot

Một ứng dụng Spring Kafka muốn xuất metrics và traces thường cần những thành phần sau.

### 4.1. Ví dụ Gradle

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Registry cho endpoint /actuator/prometheus.
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    // Chọn một tracing bridge phù hợp với hệ quan sát.
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

Các phiên bản dependency thường do **Spring Boot dependency management/BOM** quản lý; tránh ép nhiều version Micrometer/OTel không tương thích chỉ để copy một đoạn Gradle.

Nếu dự án chỉ cần metrics mà chưa triển khai distributed tracing, có thể chưa thêm tracing bridge/exporter. Khi cần tracing, phải chọn đúng bridge tương thích với backend: ví dụ OpenTelemetry hoặc hệ khác được dự án sử dụng. Không nhất thiết phải cài đồng thời mọi bridge.

**Lưu ý:** Kafka client metrics có thể được Spring Boot Actuator/Micrometer auto-configure khi bean và dependency phù hợp. Tuy nhiên các bean tùy biến, nhiều client factory, hoặc phiên bản framework khác nhau có thể làm sự tự động đăng ký thay đổi. Luôn kiểm tra meter thực tế sau khi tạo producer/consumer.

### 4.2. Ví dụ Maven (các dependency chính)

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>

    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Đây là khung cho một dự án đã dùng Spring Boot parent/BOM; tùy môi trường cần thêm dependency HTTP, serialization, JDBC và các dependency nghiệp vụ khác.

## 5. Bật metrics endpoint và tracing exporter

Cấu hình ví dụ cho môi trường quan sát:

```yaml
spring:
  application:
    name: payment-worker

  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}

    consumer:
      group-id: payment-worker-v1
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer

    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer

    listener:
      ack-mode: record
      concurrency: 3
      observation-enabled: true

    template:
      observation-enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus

  metrics:
    tags:
      application: ${spring.application.name}

  tracing:
    sampling:
      probability: 0.10

  otlp:
    tracing:
      endpoint: ${OTEL_TRACES_ENDPOINT:http://localhost:4318/v1/traces}
```

Giải thích:

- `management.endpoints.web.exposure.include` mở các endpoint cần cho giám sát. Mở endpoint không đồng nghĩa endpoint được bảo vệ; cần authentication/network policy.
- `management.metrics.tags.application` gắn tag ứng dụng ổn định vào các metric mà configuration áp dụng.
- `spring.kafka.listener.observation-enabled=true` yêu cầu Spring Boot bật observation cho các listener container mà auto-configuration quản lý.
- `spring.kafka.template.observation-enabled=true` yêu cầu observation cho template được Boot cấu hình.
- `management.tracing.sampling.probability=0.10` minh họa lấy mẫu khoảng 10% traces ở cơ chế sampling tương ứng; không phải 10% Kafka records được xử lý.
- `management.otlp.tracing.endpoint` là ví dụ exporter OTLP/HTTP trên stack Spring Boot hỗ trợ property này. Trong hệ thống sử dụng Collector, endpoint và protocol phải khớp cấu hình thật.

**Lưu ý rất quan trọng:** Hai thuộc tính `observation-enabled` ở trên áp dụng theo đường cấu hình Spring Boot thích hợp. Nếu ứng dụng tạo custom `KafkaTemplate` hoặc custom `ConcurrentKafkaListenerContainerFactory` mà không cho Boot tùy chỉnh, phải bật observation/registry ở **chính bean tùy biến**. Chỉ có YAML không bảo đảm mọi custom bean được instrument.

### 5.1. Kiểm tra Actuator sau khi chạy

Ví dụ:

```text
GET /actuator/health
GET /actuator/metrics
GET /actuator/metrics/spring.kafka.listener
GET /actuator/prometheus
```

`/actuator/metrics` cho biết những meter đang được đăng ký trong process. Nếu chưa có listener nào xử lý record, một meter nhất định có thể chưa xuất hiện. Nếu consumer chỉ tạo bean nhưng chưa kết nối/hoạt động, Kafka client metrics cũng có thể chưa tồn tại.

**Không viết dashboard dựa hoàn toàn vào một tên Prometheus suy đoán.** Tên hiển thị trong `/actuator/metrics` và tên series sau khi Prometheus registry chuyển đổi có thể khác nhau: dấu chấm thành gạch dưới, Timer có hậu tố `_seconds_count`, `_seconds_sum` và tùy cấu hình còn có bucket.

## 6. Bật Observation trên KafkaTemplate

Ở Spring Kafka 3.x, `KafkaTemplate` hỗ trợ observation cho thao tác gửi. Với một template được tạo và cấu hình thủ công, có thể bật trực tiếp:

```java
import org.apache.kafka.common.serialization.StringSerializer;

import io.micrometer.observation.ObservationRegistry;

import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Configuration
class ObservedProducerConfiguration {

    @Bean
    ProducerFactory<String, String> paymentProducerFactory() {
        Map<String, Object> config = new HashMap<>();

        config.put(
                ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092");
        config.put(
                ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        config.put(
                ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        config.put(ProducerConfig.ACKS_CONFIG, "all");
        config.put(
                ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

        return new DefaultKafkaProducerFactory<>(config);
    }

    @Bean
    KafkaTemplate<String, String> paymentKafkaTemplate(
            ProducerFactory<String, String> paymentProducerFactory,
            ObservationRegistry observationRegistry) {

        KafkaTemplate<String, String> template =
                new KafkaTemplate<>(paymentProducerFactory);

        template.setObservationRegistry(observationRegistry);
        template.setObservationEnabled(true);

        return template;
    }
}
```

**Mã minh họa:** `localhost:9092` ở đây dành cho môi trường local. Trong production, lấy bootstrap từ cấu hình được validate. Nếu ứng dụng khai báo `KafkaTemplate` tùy biến, Spring Boot auto-config có thể không tạo template mặc định như trước. Cần xác nhận bean nào được inject vào publisher.

Việc tạo observation cần **registry có handler phù hợp**. `ObservationRegistry` có thể tồn tại nhưng nếu không có metrics/tracing handler nào đăng ký thì backend không nhận dữ liệu như mong đợi. Spring Boot Actuator/tracing auto-configuration thường lo phần registry/handler khi các dependency và điều kiện phù hợp.

### 6.1. Quan sát kết quả gửi bất đồng bộ

`KafkaTemplate.send(...)` trả `CompletableFuture` trên Spring Kafka 3.x:

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;

public final class PaymentPublisher {

    private final KafkaTemplate<String, String> template;

    public PaymentPublisher(
            KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public CompletableFuture<SendResult<String, String>> send(
            String paymentId,
            String eventJson) {

        return template.send(
                "payments-out.v1",
                paymentId,
                eventJson
        );
    }
}
```

Observation ở template có thể đo thao tác publish trong phạm vi Spring Kafka instrumentation. Nhưng **method return** không phải thời điểm broker đã ghi nhận kết quả thành công. Business logic cần xét completion của future và chính sách failure/retry/outbox.

Ví dụ callback:

```java
publisher.send(paymentId, eventJson)
        .whenComplete((result, error) -> {
            if (error != null) {
                // Báo lỗi hoặc đánh dấu outbox để thử lại.
                reportSendFailure(paymentId, error);
            } else {
                // Broker đã xác nhận theo chính sách acks tương ứng.
                recordAcknowledged(result.getRecordMetadata());
            }
        });
```

`reportSendFailure(...)` và `recordAcknowledged(...)` là các hàm nghiệp vụ minh họa, không phải API có sẵn của Spring Kafka.

**Không tự kết luận exact-once chỉ vì metric template báo thành công.** Producer idempotence, application retries và consumer processing là những lớp khác nhau.

## 7. Bật Observation trên listener container

Với `@KafkaListener`, phần công việc đọc và gọi callback do listener container quản lý. Nếu dùng custom `ConcurrentKafkaListenerContainerFactory`, bật observation trên `ContainerProperties`:

```java
import io.micrometer.observation.ObservationRegistry;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
class ObservedConsumerConfiguration {

    @Bean("observedListenerFactory")
    ConcurrentKafkaListenerContainerFactory<String, String>
    observedListenerFactory(
            ConsumerFactory<String, String> consumerFactory,
            ObservationRegistry observationRegistry) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.RECORD);

        factory.getContainerProperties()
                .setObservationRegistry(observationRegistry);

        factory.getContainerProperties()
                .setObservationEnabled(true);

        factory.setCommonErrorHandler(
                new DefaultErrorHandler(
                        new FixedBackOff(1_000L, 2L)
                )
        );

        return factory;
    }
}
```

`FixedBackOff(1_000L, 2L)` chỉ là ví dụ policy; nó không tạo DLT hoặc bảo đảm lỗi cuối cùng được giải quyết theo nghiệp vụ. Khi một lỗi cuối cùng được handler recover, cần giám sát **recovery outcome**, không chỉ listener exception.

### 7.1. Gắn đúng container factory

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public final class PaymentEventListener {

    private final PaymentService service;

    public PaymentEventListener(PaymentService service) {
        this.service = service;
    }

    @KafkaListener(
            topics = "payments-in.v1",
            groupId = "payment-worker-v1",
            containerFactory = "observedListenerFactory")
    public void handle(String payload) {
        service.process(payload);
    }
}
```

`PaymentService` là service nghiệp vụ do ứng dụng định nghĩa.

Nếu ứng dụng có nhiều listener factories mà không chỉ `containerFactory`, một listener có thể sử dụng factory mặc định không bật observation hoặc trỏ đến cluster khác. Khi vận hành multi-cluster, đặt tên rõ cho factory và kiểm thử wiring là việc bắt buộc.

### 7.2. Listener Timer đo điều gì?

Observation của listener thường bọc việc thực thi callback theo semantics Spring Kafka, không phải đo đầy đủ thời gian event nằm trong Kafka **trước khi** consumer bắt đầu xử lý. Vì thế:

```text
Producer publishes at 10:00:00
Message waits in topic 2 minutes
Consumer starts callback at 10:02:00
Listener processing takes 100 ms

Listener duration ≈ 100 ms
End-to-end event age ≈ 2 phút + 100 ms + other delays
```

Để biết event chờ lâu bao nhiêu, cần Kafka timestamp, consumer lag/lag-time và nguồn thời gian có hợp đồng rõ. Không dùng listener duration làm event end-to-end latency một cách vô điều kiện.

### 7.3. Quan sát listener record/batch khác nhau

Nếu listener nhận **record** đơn, observation có thể gắn với từng lần callback. Với **batch listener**, một callback xử lý nhiều record, và cách tạo observation/tags của framework có thể khác. Đừng lấy count observations của một batch listener rồi coi là tổng số Kafka records đã xử lý.

Khi cần record count thật, sử dụng Kafka client records-consumed metrics hoặc business counter có semantics rõ, hoặc thêm instrumentation ở code xử lý từng record.

## 8. Metrics truyền thống và Observation có thể trùng tên

Spring Kafka đã có instrumentation sử dụng Micrometer Timer cho listener/template trước khi tích hợp Observation. Khi observation được bật, framework có thể dùng đường Observation thay cho đường Timer cũ trong các trường hợp phù hợp.

Điều này có vài hệ quả khi nâng cấp:

- Tên meter có thể tương tự nhưng **tag set khác**, dẫn đến dashboard không còn match.
- Cùng một operation có thể tạo metric từ nhiều nguồn nếu ứng dụng tự bọc Timer và bật observation mà không kiểm tra.
- Enable Observation không tự động tạo span nếu không có tracing bridge/handler.
- Nếu metrics biến mất sau khi tạo custom factory/template, cần kiểm tra chính bean có được bật instrumentation không.
- Dùng một hệ thống đo nhất quán, tránh đếm cùng một event nhiều lần vào business counter.

**Không xóa metric cũ khỏi dashboard ngay khi deploy cấu hình mới.** Nên chạy đối chiếu một giai đoạn hoặc kiểm tra target series và alert trước khi loại bỏ, nhất là với SLA/error-rate quan trọng.

## 9. Kafka client metrics: producer và consumer

Kafka clients phát sinh các số liệu nội bộ về request, I/O, buffer, fetch, poll, records và nhiều yếu tố khác. Spring Boot/Micrometer có thể đăng ký chúng với registry khi factory/client được tạo và listener instrumentation được cấu hình đúng.

Một số nhóm cần quan sát:

| Phía | Nhóm metric Kafka client | Chỉ báo |
|---|---|---|
| Producer | Record send rate / error rate / retry rate | Luồng gửi và tình trạng lỗi |
| Producer | Request latency, response rate | Network/broker latency |
| Producer | Buffer available/exhausted, batch size, compression | Memory pressure và batching |
| Producer | Record size max/avg | Payload tăng bất thường |
| Consumer | Records consumed rate | Khối lượng đọc |
| Consumer | Fetch rate/latency | Nhận dữ liệu từ broker |
| Consumer | Records lag max | Độ trễ về offset ở client |
| Consumer | Poll idle ratio, poll rate | Cách consumer poll |
| Consumer | Commit latency/rate | Hoạt động commit offset |
| Consumer | Assigned partitions/rebalance | Trạng thái consumer group |

**Tên metric sau khi Micrometer/Prometheus chuyển đổi không nhất thiết giống nguyên Kafka client metrics.** Ví dụ Kafka client metric group/name có thể được biểu diễn thành meter với prefix dạng `kafka.producer.*` hoặc `kafka.consumer.*`, rồi thành series Prometheus với dấu gạch dưới. Cần khám phá qua endpoint/registry thực trước khi viết expression cố định.

### 9.1. Khi auto-config không thấy client metrics

Một số nguyên nhân:

1. Chưa có Kafka producer/consumer thực sự được tạo.
2. Dùng custom `ProducerFactory`/`ConsumerFactory` nhưng không đăng ký Micrometer listener phù hợp.
3. Không có `MeterRegistry` hoặc actuator configuration phù hợp.
4. Chỉ đo listener, nhưng tưởng metrics broker cũng được Spring Boot tự thu thập.
5. Kafka client đã đóng; gauges/metrics không còn thấy ở thời điểm scrape.
6. Tags/metric naming thay đổi sau nâng cấp.

Spring Kafka cung cấp các listener cho producer/consumer factory để tích hợp Micrometer, thường qua `MicrometerProducerListener` và `MicrometerConsumerListener`. Với custom factories, có thể đăng ký theo hỗ trợ của phiên bản đang dùng:

```java
import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.MicrometerConsumerListener;
import org.springframework.kafka.core.MicrometerProducerListener;

// Minh họa sau khi đã tạo factory với config đúng.
producerFactory.addListener(
        new MicrometerProducerListener<>(meterRegistry));

consumerFactory.addListener(
        new MicrometerConsumerListener<>(meterRegistry));
```

Đây là đoạn **wiring minh họa**: `producerFactory` và `consumerFactory` ở đây là instance `DefaultKafkaProducerFactory`/`DefaultKafkaConsumerFactory` đã được tạo từ đúng map cấu hình; không phải biến tự động có sẵn. Trước khi tự thêm listener, kiểm tra Boot đã đăng ký instrumentation hay chưa, tránh duplicate meters.

### 9.2. Metrics từ Kafka client không bằng kết quả nghiệp vụ

Producer `record-send-rate` cao chỉ có nghĩa client gửi record tốt, không chứng minh consumer xử lý được. Consumer `records-consumed-rate` cao không chứng minh database commit hoặc outbox được publish.

Ví dụ:

```text
Kafka producer:  1.000 messages/s
Kafka consumer:  1.000 records/s
Business commit:   650 events/s
DLT/retry/duplicate: phần còn lại
```

Nếu chỉ nhìn network rate, hệ thống có thể trông khỏe mạnh. Cần business metrics để hiểu trạng thái thực tế của các event.

## 10. Consumer lag phải đo từ đúng nguồn

**Consumer lag** thường được dùng để biết consumer group còn bao nhiêu record cần xử lý trong một topic/partition.

Ở dạng đơn giản:

```text
lag ≈ log-end-offset - committed-offset
```

Trong Kafka, committed offset thường biểu diễn **vị trí tiếp theo sẽ đọc** (next offset), không nhất thiết là offset cuối đã xử lý. Với nhóm không có committed offset, việc tính lag cần xử lý quy tắc `auto.offset.reset` và retention.

Ví dụ:

```text
Partition 0:
  End offset (next) = 15.000
  Group committed offset = 14.200

  Lag = 15.000 - 14.200 = 800 records
```

Công thức đơn giản ở trên không bao quát mọi chi tiết isolation, transaction/LSO, compaction, retention hoặc cách exporter định nghĩa end offset. Hãy chọn công cụ đo và hiểu semantics của nó.

### 10.1. Client lag và group lag không giống nhau

- Một KafkaConsumer có thể báo **records-lag-max** đối với các partition **được gán** cho client đó.
- Một hệ thống giám sát consumer-group lag dùng offset broker và committed offsets của **toàn group**, kể cả partition mà client cụ thể không đang giữ.
- Nếu một consumer chết và không phát client metrics nữa, dashboard chỉ đọc client metrics có thể **mất tín hiệu** đúng lúc hệ thống có sự cố.
- Nếu consumer group chưa tồn tại hoặc không có committed offset, không phải công cụ nào cũng hiển thị như cùng một dạng lag.

Vì vậy khi cần SLO ở cấp dịch vụ, nên kết hợp:

1. Consumer client metrics.
2. Group lag ở cấp cluster qua exporter/monitoring platform (ví dụ broker/admin API-based exporter).
3. Liveness/partition assignment của listener.
4. Business processing throughput và outbox/DB status.

### 10.2. Lag cao không luôn là lỗi

Một job downstream xử lý theo lịch có thể chủ động để Kafka tích backlog rồi đọc theo batch. Với system real-time, lag 10.000 records có thể đã là vi phạm SLA.

Tài liệu nên ghi **SLO theo số record và/hoặc độ tuổi event**, ví dụ:

```text
payment-commands consumer group:
- Consumer lag < 5.000 records trong điều kiện bình thường.
- Event processing age p95 < 30 giây.
- Nếu lag tăng liên tục hơn 15 phút: cảnh báo.
```

Các số là minh họa. Lag 5.000 records với producer 100.000/s có thể là vài chục mili-giây workload; với producer 10/s có thể là nhiều phút. **Lag record count và event age nên được nhìn cùng nhau**.

## 11. Kafka broker metrics không tự xuất hiện từ Spring Actuator

Spring Kafka chạy **trong ứng dụng**, còn broker Kafka là một hệ thống riêng. Chỉ bật `spring-boot-starter-actuator` không tự thu thập:

- Under-replicated partitions.
- Offline partitions.
- Broker request queues.
- ISR shrink/expand events.
- Controller health.
- Disk fullness và disk latency.
- Network processor idle.
- Broker-side quota/throttling.

Các số liệu này thường đến từ broker JMX/exporter, platform Kafka managed monitoring hoặc một giải pháp telemetry chuyên biệt cho Kafka cluster.

Ví dụ kiến trúc triển khai:

```text
Spring Boot application             Kafka brokers
        |                                 |
 /actuator/prometheus                 JMX / exporter
        |                                 |
        +------------+--------------------+
                     |
                 Prometheus
                     |
                   Grafana
                     |
                 Alertmanager

 Traces từ app -> OpenTelemetry Collector -> Tempo/Jaeger
 Logs từ app   -> Log pipeline         -> Search UI
```

Nếu client producer latency tăng và broker `under-replicated-partitions` cũng tăng, vấn đề có thể thuộc cluster. Nếu broker vẫn ổn nhưng listener duration tăng do database, cần xem downstream.

## 12. Trace context truyền qua Kafka headers

Distributed tracing theo dõi một flow xuyên service:

```text
HTTP POST /payments
    |
    v
payment-api
    |  Span: HTTP request
    |
    +--> KafkaTemplate.send("payments-in.v1")
                   | Span: Kafka produce
                   |
                Kafka topic
                   |
                   v
             payment-worker
                   | Span: Kafka listener
                   |
                   +--> JDBC transaction
                   |
                   +--> KafkaTemplate.send("payments-out.v1")
                                  |
                                  v
                             next-service
```

Với Micrometer Observation + tracing bridge và Spring Kafka instrumentation phù hợp, trace context có thể được **inject** vào Kafka record headers khi producer gửi và **extract** ở listener phía nhận.

### 12.1. Điều kiện để có trace nối xuyên service

- Producer và consumer cùng hỗ trợ/truyền trace propagation headers theo định dạng đã thống nhất, thường W3C Trace Context.
- Cả hai service có ObservationRegistry/tracing handler được cấu hình đúng.
- Record headers không bị middleware/proxy/transformer loại bỏ.
- Instrumentation được bật ở template và listener container thực sự sử dụng.
- Không mất context khi service tự chuyển xử lý sang executor/thread khác mà không propagation.
- Sampling policy không loại bỏ toàn bộ traces cần quan sát.

Nếu hai service dùng propagation format khác nhau hoặc một service chỉ bật metrics, trace có thể bị đứt dù Kafka vẫn xử lý message bình thường.

### 12.2. Không tin headers từ nguồn ngoài một cách tuyệt đối

Headers như `traceparent`, `baggage` hoặc custom correlation ID có thể do producer ngoài tổ chức đặt. Chúng là **dữ liệu đầu vào**, không phải bằng chứng authorization hay danh tính.

Đừng đưa token, email, số tài khoản, payload nhạy cảm vào baggage chỉ để chúng “đi theo trace”; baggage có thể được truyền sang dịch vụ khác và được thu thập ở telemetry backend.

Một span/correlation ID không thay thế `eventId` làm khóa idempotency nghiệp vụ.

### 12.3. Khi thread xử lý thay đổi

Nếu listener hand off sang `CompletableFuture` hoặc executor, current span/context có thể không được giữ nguyên nếu không có context propagation. Spring Boot có các cơ chế hỗ trợ Micrometer Context Propagation tùy stack, nhưng cần kiểm tra executor và asynchronous boundary thực tế.

Đừng ghi một trace ID từ thread listener vào static field rồi dùng ở thread khác; điều đó không thread-safe và dễ tạo trace sai.

## 13. Custom Observation cho logic nghiệp vụ

Không phải mọi thời gian xử lý trong listener đều do Kafka tạo. Có thể cần một nested observation cho bước kiểm tra thanh toán hoặc cập nhật database.

Ví dụ:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public final class PaymentProcessingService {

    private final ObservationRegistry registry;
    private final PaymentRepository repository;

    public PaymentProcessingService(
            ObservationRegistry registry,
            PaymentRepository repository) {

        this.registry = registry;
        this.repository = repository;
    }

    public void process(PaymentEvent event) {
        Observation observation = Observation.createNotStarted(
                "payment.process",
                registry
        );

        observation.lowCardinalityKeyValue(
                "operation", "apply-payment");

        observation.lowCardinalityKeyValue(
                "source", event.sourceSystem());

        observation.observe(() ->
                repository.applyIdempotently(event)
        );
    }
}
```

`PaymentEvent` và `PaymentRepository` là các kiểu nghiệp vụ giả định. `applyIdempotently(...)` phải được ứng dụng triển khai đúng transaction và business key.

**Lưu ý về tag `source`:** ví dụ giả định `event.sourceSystem()` đến từ một **allowlist nhỏ và ổn định**. Nếu giá trị này là ID động của từng đối tác hoặc một chuỗi tự do từ payload, không nên dùng làm low-cardinality key. Thay bằng nhóm nguồn có giá trị hữu hạn hoặc dùng high-cardinality trace context/log theo policy.

### 13.1. Low cardinality và high cardinality

Một điểm khác biệt cốt lõi trong Observation:

- **Low-cardinality key-values** phù hợp cho metric tags: `operation=apply-payment`, `outcome=success/failed`, `source=partner-a/partner-b`.
- **High-cardinality key-values** chỉ phù hợp với trace/span attributes khi cần, chịu hạn chế bảo mật/lưu trữ: `eventId`, `paymentId`, `orderId`. Không đưa chúng thành metric labels.
- **Baggage** là thông tin có thể truyền xuyên dịch vụ; không coi nó như vùng lưu dữ liệu nhạy cảm.

Tránh:

```java
// Không nên: mỗi event tạo một metric time series riêng.
observation.lowCardinalityKeyValue(
        "eventId", event.eventId());
```

Ngay cả khi backend vẫn nhận được dữ liệu, hàng trăm nghìn event ID làm cardinality tăng theo số message và khiến monitoring quá tải.

### 13.2. Observation không tự rollback side effect

`observation.observe(...)` có thể ghi nhận exception và kết thúc span khi code ném lỗi, nhưng **không mở transaction nghiệp vụ**. Muốn xử lý đúng DB, cần transaction manager hoặc `@Transactional` áp dụng đúng ranh giới.

Với producer/outbox, observation không bảo đảm event được broker nhận nếu code chỉ queue async send rồi return.

## 14. Custom business counters: đếm đúng một việc

Metrics mặc định không luôn trả lời các câu hỏi nghiệp vụ. Có thể tự định nghĩa các counters:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public final class PaymentOutcomeMetrics {

    private final Counter accepted;
    private final Counter duplicate;
    private final Counter rejected;

    public PaymentOutcomeMetrics(MeterRegistry registry) {
        accepted = Counter.builder("payment.event.outcome")
                .tag("outcome", "accepted")
                .register(registry);

        duplicate = Counter.builder("payment.event.outcome")
                .tag("outcome", "duplicate")
                .register(registry);

        rejected = Counter.builder("payment.event.outcome")
                .tag("outcome", "rejected")
                .register(registry);
    }

    public void accepted() {
        accepted.increment();
    }

    public void duplicate() {
        duplicate.increment();
    }

    public void rejected() {
        rejected.increment();
    }
}
```

Nhưng phải định nghĩa **đếm tại đâu**:

- `received`: listener bắt đầu nhận record; có thể tăng nhiều lần khi Kafka redelivery.
- `attempted`: một lần thử xử lý nghiệp vụ; có thể tăng khi retry.
- `accepted`: business operation đã hoàn tất theo tiêu chí nào? DB commit hay chỉ validate?
- `duplicate`: event ID đã có trong inbox, nhưng có thực sự là exact duplicate không?
- `rejected`: lỗi nghiệp vụ được phân loại không thể xử lý.

Nếu cần báo cáo số giao dịch đã commit **chính xác**, counter trong memory không phải nguồn authoritative vì JVM có thể crash sau commit trước khi tăng counter, hoặc tăng counter trước khi transaction rollback. Dùng DB audit/inbox/outbox làm nguồn đối soát, metric phản ánh xu hướng vận hành.

### 14.1. Đừng đếm lỗi từ cả retry và final failure như nhau

Ví dụ một record lỗi tạm thời hai lần rồi thành công:

```text
Attempt 1: DB timeout
Attempt 2: DB timeout
Attempt 3: commit thành công

Retry attempts = 2
Final failed events = 0
Business accepted = 1
```

Nếu tăng `payment_event_failed_total` ở mỗi catch, dashboard sẽ báo 2 sự kiện thất bại dù cuối cùng không có event bị mất. Nên phân biệt `processing_attempt_errors_total` với `final_processing_failures_total` và DLT recovery.

## 15. Error handling, retry và DLT phải có telemetry riêng

Spring Kafka có `DefaultErrorHandler` và các recoverer để xử lý exception trong listener. Observability phải nhìn được cả **quá trình retry**, **quyết định recover** và **kết quả gửi sang DLT**.

Ví dụ sơ đồ:

```text
Kafka record
   |
   v
@KafkaListener
   |
   +-- success -------------> offset/transaction theo policy
   |
   +-- exception
          |
          v
   DefaultErrorHandler
          |
          +-- retry with backoff
          |
          +-- exhausted
                 |
                 +-- DLT publish (phải quan sát kết quả)
                 +-- stop/fail (tùy policy)
```

Một `KafkaTemplate` observation báo send thành công cho DLT chỉ cho thấy broker xác nhận theo policy của producer; quy trình xử lý DLT sau đó vẫn cần owner, retention và runbook.

### 15.1. DLT metrics nên có gì?

| Metric | Ý nghĩa |
|---|---|
| Số record được recover thành công vào DLT | Lỗi không xử lý được trong đường chính |
| Số lần DLT publish thất bại | Nguy cơ mất đường recovery |
| Tuổi record lâu nhất trong DLT | Sự cố còn tồn đọng |
| Phân loại lỗi trước recovery | Payload invalid, DB transient, schema mismatch |
| Số message được replay từ DLT | Tiến độ phục hồi |
| Số lần replay vẫn thất bại | Lỗi chưa được giải quyết |

Những metric này thường cần ứng dụng/recoverer và công cụ monitoring hỗ trợ; đừng mặc định Spring Kafka tự phát hết.

### 15.2. Ví dụ cấu hình error handler và DLT recoverer

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler paymentErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    var recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate);

    var handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
    );

    handler.addNotRetryableExceptions(
            InvalidPaymentEventException.class
    );

    return handler;
}
```

`InvalidPaymentEventException` là một exception nghiệp vụ giả định; `dltTemplate` phải được tạo và gắn đúng cluster, serializers, topics và ACL. Đoạn này chỉ minh họa error classification, **chưa có logic custom metrics hoặc xác nhận DLT publish theo mọi failure mode**.

Nếu consumer đọc cluster A và business producer ghi cluster B, DLT template phải trỏ cluster **dự kiến chứa DLT**, thường là A. Một template có Observation bật nhưng gửi nhầm cluster vẫn là lỗi chức năng.

## 16. Consumer lag và listener duration nên xem cùng nhau

Ví dụ dashboard theo thời gian:

| Thời điểm | Group lag | Listener p95 | DB p95 | Producer send p95 | Cách diễn giải ban đầu |
|---|---:|---:|---:|---:|---|
| 10:00 | 200 | 50 ms | 20 ms | 15 ms | Bình thường |
| 10:05 | 2.000 | 55 ms | 20 ms | 15 ms | Producer tăng tải hoặc consumer thiếu partition |
| 10:10 | 8.000 | 800 ms | 700 ms | 15 ms | DB có thể là bottleneck |
| 10:15 | 15.000 | 850 ms | 730 ms | 16 ms | Consumer không bắt kịp |
| 10:20 | 12.000 | 70 ms | 25 ms | 16 ms | Phục hồi, bắt đầu giảm backlog |

Số liệu là **minh họa** và không chứng minh nguyên nhân gốc. Cần đối chiếu logs, DB connection pool, query latency, partition assignment và producer rate để kết luận.

### 16.1. Ba câu hỏi điều tra lag tăng

1. **Nguồn phát tăng bất thường?** Nhìn producer rate/bytes, số records vào topic.
2. **Consumer xử lý chậm?** Nhìn listener duration, retry/DLT, DB/API latency và `max.poll.interval.ms`.
3. **Không đủ active consumers/partition?** Nhìn group assignment/rebalance, số partition, số pod/threads và cấu hình concurrency.

Lag có thể tăng ngay sau deploy do rebalance ngắn. Không nên alert chỉ dựa một sample mà không có cửa sổ thời gian hoặc ngữ cảnh thay đổi deployment.

## 17. Prometheus: metric names và cách viết query

Prometheus registry chuyển đổi meter names theo naming convention. Ví dụ một Micrometer Timer tên `spring.kafka.listener` có thể tạo các series như:

```text
spring_kafka_listener_seconds_count
spring_kafka_listener_seconds_sum
spring_kafka_listener_seconds_max
```

Tên cụ thể, loại series và tags phải được **kiểm tra tại /actuator/prometheus** vì phụ thuộc phiên bản Micrometer, registry và cách instrumentation.

### 17.1. Đếm lượt listener đã quan sát

Nếu metric Timer tồn tại, có thể viết:

```promql
sum(
  rate(spring_kafka_listener_seconds_count[5m])
)
```

Ý nghĩa là **lượt operation listener kết thúc trên mỗi giây** trong cửa sổ. Nếu listener kiểu batch thì một operation có thể chứa nhiều record; nếu có retry, một record có thể được xử lý nhiều lần. Đây **không nhất thiết là unique events/s**.

### 17.2. Thời gian listener trung bình

```promql
sum(
  rate(spring_kafka_listener_seconds_sum[5m])
)
/
sum(
  rate(spring_kafka_listener_seconds_count[5m])
)
```

Kết quả theo giây/operation nếu có đủ mẫu và hai series tồn tại.

Với một job hoặc consumer hiếm khi xử lý message, cửa sổ 5 phút có thể quá ít mẫu. Khi đó nên điều chỉnh khoảng nhìn, xem histogram theo tuần hoặc dữ liệu execution.

### 17.3. P95 với histogram

Nếu enable histogram và registry tạo `_bucket`:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(spring_kafka_listener_seconds_bucket[10m])
  )
)
```

Chỉ áp dụng khi histogram thực sự được xuất và số mẫu đủ. Percentile ở một topic mỗi giờ có vài record dễ gây hiểu sai.

Để bật histogram cho một số Timer, có thể cấu hình Micrometer distribution trên các meter có tên tương ứng:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        "[spring.kafka.listener]": true
        "[spring.kafka.template]": true
```

Tên meter trong phần này chỉ là ví dụ để cấu hình trên stack phù hợp. Histograms tiêu tốn tài nguyên và tăng số time series; nên bật có chọn lọc theo nhu cầu SLO, không bật trên mọi tag có cardinality cao.

### 17.4. Tách query theo topic hoặc listener ID

Một số meter có tag cho listener ID, topic, result hoặc exception. Nhưng tag name thay đổi theo instrument và version, nên cần đọc labels có thực trong Prometheus:

```text
# Ví dụ mô tả, không phải tag bắt buộc của mọi version:
spring_kafka_listener_seconds_count{spring_kafka_listener_id="..."}
```

Không hard-code `name`, `listener`, `topic` hay một key tag cụ thể khi chưa xác nhận. Sau khi khám phá, có thể group theo những nhãn ổn định để tránh gộp nhầm các consumer có SLA khác nhau.

## 18. Dashboard cho Spring Kafka Reliability Operations

Một dashboard hữu ích nên chia theo vai trò và kết quả, thay vì đưa hàng trăm metric vào cùng màn hình.

### 18.1. Overview

| Panel | Nguồn đo | Câu hỏi |
|---|---|---|
| Applications alive/readiness | Spring Actuator / orchestration | Service và listener còn hoạt động không? |
| Group lag và lag trend | Kafka group exporter | Các consumer theo kịp dữ liệu không? |
| Incoming/outgoing rate | Kafka client hoặc broker | Tải có tăng/giảm bất thường? |
| Listener processing p95 | Micrometer Observation Timer | Code xử lý có chậm không? |
| Business accepted/failed/duplicate | Business metrics/DB | Bao nhiêu event thực sự có outcome |
| DLT pending | DLT topic + audit | Sự cố chưa xử lý còn bao nhiêu? |
| Producer error/retry rate | Kafka client metrics + future callback | Đường gửi có bất ổn? |
| DB/API latency | Dependency instrumentation | Bottleneck downstream nằm ở đâu? |

### 18.2. Producer detail

Theo dõi:

- Sends/sec, bytes/sec, record error/retry rate.
- Request latency và record-size distribution.
- Buffer memory available/exhaustion.
- Broker ACK latency theo client metric.
- Số event đã tạo trong outbox nhưng chưa được publish.
- Tuổi outbox record lâu nhất, số lần publish thất bại.
- Trace từ business request đến Kafka send khi sampling cho phép.

Nếu producer client metrics bình thường nhưng outbox pending tăng, lỗi có thể nằm ở **publisher scheduler, DB query hoặc logic chọn outbox**, không hẳn ở Kafka.

### 18.3. Consumer detail

Theo dõi:

- Group lag và partition lag distribution.
- Records consumed/sec.
- Listener Timer p50/p95/p99 khi đủ mẫu.
- Error handler attempts và phân loại final outcomes.
- DLT records/age và replay.
- Commit latency/failure.
- Rebalance count/time, assigned partition count.
- DB connection pool wait, transaction duration, timeout.
- Số event được xử lý idempotently và số duplicate.

Một group có lag tổng nhỏ nhưng **một partition lag rất lớn** có thể bị data skew hoặc poison message. Đừng chỉ vẽ tổng lag.

## 19. Alert: đo tác động trước khi báo sự cố

Ví dụ alert rules cần phân biệt **symptom** và **cause**:

| Alert minh họa | Điều kiện | Hành động |
|---|---|---|
| Consumer lag tăng lâu | Group lag tăng liên tục 15 phút và vượt ngưỡng SLA | Kiểm tra load, partition, retry, DB |
| Không có progress | Lag > 0 nhưng processed rate = 0 trong 10 phút | Kiểm tra assignment, pause, auth, poison record |
| Producer send errors | Error rate vượt baseline trong 5 phút | Kiểm tra broker/network/ACL/quota |
| DLT tăng | DLT recovery tăng nhanh bất thường | Kiểm tra lỗi schema/poison data |
| Listener duration cao | p95 vượt SLO trên đủ mẫu | Kiểm tra DB/API/CPU/GC |
| Outbox già | Oldest pending age vượt SLA | Kiểm tra publisher và Kafka B |
| Rebalance liên tục | Rebalance rate tăng và lag không hồi phục | Kiểm tra pods, poll interval, static membership |
| Telemetry mất | Prometheus scrape target `up=0` | Kiểm tra instrumentation/endpoint/mạng |

Các ngưỡng là ví dụ. Alert cho consumer không xử lý message **khi không có message nào** dễ gây false positive; điều kiện nên xét lag/backlog và lịch hoạt động của pipeline.

### 19.1. Cách đặt alert để có hành động

Một alert tốt thường có:

- Tên group/topic hoặc service rõ ràng.
- Mức độ tác động đến SLA nghiệp vụ.
- Cửa sổ thời gian để tránh báo động do một spike ngắn.
- Link dashboard và log/trace liên quan.
- Runbook: ai xử lý, thao tác kiểm tra, điều kiện pause/resume/restart.
- Cách xác minh đã phục hồi, ví dụ lag giảm và business processing success trở lại.

Không tự kill consumer hoặc reset offsets chỉ vì lag cao. Những hành động đó có thể tăng duplicate hoặc bỏ sót dữ liệu nếu không có quy trình idempotency/replay.

## 20. Sampling, hiệu năng và chi phí telemetry

Metrics tổng hợp thường rẻ hơn lưu trace chi tiết cho **mỗi message**. Trong workload 100.000 record/giây, thu full traces với quá nhiều attributes có thể tạo chi phí lớn.

Một chính sách minh họa:

```yaml
management:
  tracing:
    sampling:
      probability: 0.10
```

Ý nghĩa: sampling cho **tracing**. Nó **không** có nghĩa listener chỉ được instrument 10% về mặt logic hay chỉ xử lý 10% dữ liệu. Metrics có thể vẫn được cập nhật theo handler/registry đang dùng trong khi spans chỉ được xuất theo sampling.

### 20.1. Chọn sampling theo nhu cầu

- Traffic thấp, giao dịch critical: có thể cần tỷ lệ tracing cao hơn.
- Traffic rất cao: giảm sampling, dùng metrics cho xu hướng, tăng sampling có điều kiện khi incident.
- Những lỗi hiếm: cần logging/audit có kiểm soát hoặc error-tail sampling nếu hệ thống tracing hỗ trợ.
- Dữ liệu nhạy cảm: giảm attributes, redact và hạn chế retention.

**Không dựa vào trace sampling để đếm chính xác số business events.** Một trace bị bỏ mẫu không có nghĩa event không được xử lý; một trace có nhiều attempt không nhất thiết là nhiều unique events.

### 20.2. Instrumentation overhead

Bật metrics/tracing thêm overhead về CPU, memory, allocation, exporter network và số time series. Cần benchmark trước và sau khi bật ở tải đại diện, đo:

- Throughput, listener p95/p99, GC.
- Memory/CPU của registry và exporter.
- Độ trễ export OTLP khi collector lỗi.
- Số series Prometheus do tag/histogram tạo.
- Buffer và rate-limit của telemetry pipeline.

Observability quan trọng cho reliability nhưng không nên làm hệ thống mất ổn định do exporter bị kẹt. Dùng exporter async, buffer và timeout có giới hạn theo thiết kế stack đang dùng.

## 21. Cardinality: sai lầm gây hỏng monitoring

Prometheus lưu một time series riêng cho mỗi tổ hợp **metric name + labels**. Kafka có rất nhiều thông tin định danh, nhưng không phải thông tin nào cũng phù hợp làm label.

### 21.1. Nhãn thường phù hợp

- `application`: tên service trong tập có giới hạn.
- `cluster`: cluster ID/alias có số lượng nhỏ.
- `topic`: trong tập topic đã quản lý.
- `consumer_group`: group name có vòng đời được kiểm soát.
- `listener_id`: ID được cấu hình ổn định.
- `outcome`: `success`, `failed`, `recovered`.
- `exception_class`: loại exception đã được chuẩn hóa thành số nhóm hữu hạn.

Ngay cả `topic`/`group` có thể trở thành high-cardinality nếu ứng dụng tạo topic/group theo từng customer hoặc session. Phải xét **số giá trị thực**, không chỉ tên trường.

### 21.2. Nhãn không nên dùng

- `eventId`, `messageId`, `paymentId`, `orderId`.
- Payload, exception message gốc.
- Timestamp từng record.
- Kafka offset của từng record.
- Một trace ID duy nhất cho mỗi request/event.
- Client ID sinh ngẫu nhiên mỗi lần reconnect mà không có chính sách bound.
- Tenant ID nếu có hàng chục nghìn tenants.

Các giá trị này phù hợp hơn với **structured logs hoặc trace attributes** sau khi kiểm tra quyền truy cập.

Ví dụ sai:

```java
Counter.builder("payment.processed")
        .tag("eventId", event.eventId())
        .register(registry)
        .increment();
```

Mỗi event mới có thể tạo một meter mới. Sửa thành:

```java
Counter.builder("payment.processed")
        .tag("outcome", "accepted")
        .register(registry)
        .increment();
```

Tốt hơn nữa, tạo/inject Counter một lần thay vì tìm đăng ký trong mỗi invocation, nhất là với các tags cố định.

### 21.3. Không dùng dữ liệu cá nhân làm trace attributes một cách tùy tiện

Traces và logs cũng là dữ liệu được lưu trữ và truy cập. Không đặt số thẻ, tên đầy đủ, địa chỉ email hoặc secret vào span để “debug tiện hơn”. Có thể dùng ID tham chiếu đã pseudonymize, retention hợp lý và quyền truy cập cần thiết.

## 22. Phân biệt Observation, offset commit và transaction

Một listener observation có thể kết thúc trong khi offset commit vẫn đang được container thực hiện theo policy. Một KafkaTemplate observation có thể ghi nhận thao tác gửi trong khi DB transaction phía ứng dụng chưa commit. Vì vậy, cần lập **bảng các ranh giới**:

| Hoạt động | Bằng chứng thực sự | Không được suy ra |
|---|---|---|
| Listener callback hoàn tất | Method đã trả về theo đường xử lý | Business data ở hệ khác chắc chắn commit |
| Producer future thành công | Broker xác nhận record theo `acks` | Consumer đã xử lý event |
| Kafka offset commit thành công | Group có vị trí đọc mới | Side effect ngoài Kafka không trùng |
| DB transaction commit | Dữ liệu trong DB được commit | Kafka output cũng đã tới broker |
| DLT publish thành công | Record đã vào DLT theo semantics producer | Có người xử lý/khôi phục record |
| Trace kết thúc | Operation được instrument đã kết thúc | End-to-end exactly once |

### 22.1. DB + Kafka outbox

Khi service vừa ghi database vừa phát Kafka, quy trình đáng tin cậy hơn là:

```text
Kafka consumer receives E-101
          |
          v
DB transaction:
  insert inbox(eventId=E-101) if absent
  update business tables
  insert outbox(eventId=E-101)
  COMMIT
          |
          v
Consumer ack/offset commit theo policy
          |
          v
Outbox publisher
   |
   +-- send to Kafka
   +-- observe future success/failure
   +-- mark delivered
          |
          v
Downstream idempotent consumer
```

Metrics cần theo dõi riêng `inbox_duplicate_total`, `outbox_pending`, `outbox_publish_failed_total` và Kafka producer metrics. Một producer Timer nhanh không thay thế việc đo tuổi outbox.

### 22.2. Kafka transactions

Spring Kafka hỗ trợ Kafka transactions và một số kiểu exactly-once Kafka-to-Kafka processing khi được cấu hình đúng. Nhưng transaction Kafka **không tự bao trùm PostgreSQL**, cũng không tạo transaction duy nhất giữa hai Kafka clusters độc lập.

Một dashboard “transaction committed” của Kafka không chứng minh mọi cập nhật trong external database cùng commit. Nếu mục tiêu là business consistency, cần test crash/recovery và đối soát.

## 23. Deployment nhiều cluster và observation

Trong hệ thống có producer và consumer kết nối các cluster khác nhau:

```text
Kafka Cluster A                          Kafka Cluster B
   inbound topic                            outbound topic
       |                                         ^
       v                                         |
 ConsumerFactory A                       ProducerFactory B
       |                                         |
 ListenerContainerFactory A               KafkaTemplate B
       |                                         |
       +------------- Application ---------------+
                             |
                      ObservationRegistry
                             |
                      Metrics + Tracing
```

Có thể dùng **một ObservationRegistry** trong JVM cho nhiều client roles, đồng thời thêm những low-cardinality tags ổn định để phân biệt inbound/outbound/cluster, nếu convention/instrumentation của từng thành phần hỗ trợ.

Nhưng:

- Registry dùng chung không tự làm clients kết nối đúng cluster.
- Listener factory A phải bật observation trên đúng `ContainerProperties`.
- KafkaTemplate B phải bật observation trên chính bean được publisher dùng.
- Các factory client có thể cần đăng ký Kafka client metrics listener riêng khi dùng custom configuration.
- DLT producer gửi về A có thể cần một KafkaTemplate khác; nó cũng phải được instrument nếu muốn quan sát.
- Các Kafka admin/client khác có thể dùng cluster riêng, cần kiểm tra metrics và health theo vai trò.

Một lỗi thường gặp là bật `spring.kafka.template.observation-enabled` cho template mặc định trong Boot, trong khi business service inject một template tên `outboundKafkaTemplate` do ứng dụng tự tạo nhưng không bật observation. Lúc đó trace có thể đứt ở outbound Kafka dù code vẫn publish được.

## 24. Application profiles và cấu hình theo môi trường

Tách cấu hình qua profile giúp vận hành rõ ràng.

Ví dụ local:

```yaml
# application-local.yml
spring:
  kafka:
    bootstrap-servers: localhost:9092

management:
  tracing:
    sampling:
      probability: 1.0

  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
```

Ví dụ production:

```yaml
# application-prod.yml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}

management:
  tracing:
    sampling:
      probability: 0.05

  otlp:
    tracing:
      endpoint: ${OTEL_TRACES_ENDPOINT}
```

Các giá trị sampling chỉ là ví dụ. Với metric scrape, production còn phải cấu hình Prometheus target, service discovery và network policy để scraper có thể truy cập endpoint mà không công khai trên internet.

### 24.1. Đừng để default localhost lọt vào production

Ví dụ:

```yaml
bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
```

tiện ở local, nhưng nếu env var thiếu trên production, ứng dụng có thể thử kết nối sai nơi. Nên dùng cấu hình bắt buộc, validation fail fast, và chỉ đặt fallback trong local profile.

### 24.2. Quản lý cấu hình như một contract

Nên ghi:

| Tên cấu hình | Owner | Giá trị/nguồn | Kiểm chứng |
|---|---|---|---|
| Kafka bootstrap | Kafka Platform | Env/config per cluster | Connectivity/metadata test |
| Topic/group | Service Team | Configuration versioned | Contract/wiring test |
| Observation enabled | Service Team | Boot properties/custom beans | Endpoint and test spans |
| Prometheus endpoint | Observability | Actuator + network policy | Scrape `up` |
| OTLP endpoint | Observability | Secret/config | Collector receives spans |
| Sampling | SRE + Service Team | Per-env policy | Trace volume/coverage |
| Metric tags | Observability | Stable allowlist | Cardinality review |
| Alert thresholds | Service Owner | SLO per workload | Incident simulation |

Một dòng “metrics enabled=true” trong tài liệu chưa đủ để xác nhận **telemetry pipeline có hoạt động**. Cần kiểm tra cuối đường từ app qua scraper/collector tới dashboard.

## 25. Bảo mật Actuator, telemetry và hệ thống thu thập

Endpoint `/actuator/prometheus` có thể lộ topic names, group IDs, broker aliases, version ứng dụng và các thông tin vận hành nội bộ. Không nên expose endpoint này công khai chỉ vì Prometheus cần scrape.

Biện pháp phù hợp:

- Chỉ cho phép mạng giám sát truy cập endpoint.
- Authentication/authorization hoặc service mesh policy tùy hạ tầng.
- TLS nếu metric vượt trust boundary.
- Không xuất secret qua tags, logs, span attributes hoặc exception message.
- Kiểm tra exporter endpoints và credentials, không commit password/token vào YAML.
- Giới hạn retention và quyền truy cập traces/logs.
- Tránh ghi raw Kafka payload vào tracing/logging pipeline.
- Kiểm soát cardinality để hạn chế khả năng gây quá tải backend.

**Tracing headers không phải thông tin xác thực**. Một record có trace ID “giống nội bộ” vẫn phải qua validation và authorization nghiệp vụ.

## 26. Kiểm thử metrics: unit test không cần Kafka broker

Với một custom `MeterRegistry` counter, có thể dùng `SimpleMeterRegistry` trong unit test để kiểm tra số liệu một cách deterministic.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.junit.jupiter.api.Test;

class PaymentOutcomeMetricsTest {

    @Test
    void acceptedCounterIncrementsOnce() {
        try (SimpleMeterRegistry registry =
                     new SimpleMeterRegistry()) {

            PaymentOutcomeMetrics metrics =
                    new PaymentOutcomeMetrics(registry);

            metrics.accepted();

            Counter counter = registry.find("payment.event.outcome")
                    .tag("outcome", "accepted")
                    .counter();

            assertEquals(1.0, counter.count(), 0.000001);
        }
    }
}
```

Test chứng minh code gọi Counter đúng, không chứng minh Kafka message đã commit hay metrics thật đã đến Prometheus. Các bộ đếm in-memory sẽ được khởi tạo lại khi JVM restart; dùng chúng để đo xu hướng, không thay một bảng audit bền vững.

### 26.1. Test tag policy

Tạo test hoặc static policy không cho phép business ID xuất hiện trong metric tags. Ví dụ giả định `PaymentOutcomeMetrics` chỉ dùng `outcome` với tập `accepted/duplicate/rejected`.

Cần kiểm tra khi xử lý nhiều event có ID khác nhau, số meter không tăng theo số ID. Nếu meter count tăng tuyến tính với số record, khả năng cao custom instrumentation đang dùng dynamic tags.

### 26.2. Test ObservationRegistry

Với code tự tạo observation, có thể dùng `TestObservationRegistry` trong dependency test của Micrometer Observation phù hợp hoặc một `ObservationHandler` giả để ghi nhận operation name, low-cardinality keys, error và lifecycle.

Các điều cần assert:

- Tên observation đúng, ví dụ `payment.process`.
- `operation` thuộc tập giá trị đã định.
- Exception được báo tới handler khi nghiệp vụ ném lỗi.
- Không đưa `eventId` vào low-cardinality keys.
- Operation được stop kể cả khi code thất bại.

Cần lưu ý rằng test tạo một registry không có handler không tự có span/metrics. Khi muốn assert Timer, phải thêm đúng metrics handler/registry hoặc dùng Spring Boot test context đã cấu hình.

## 27. Kiểm thử Spring Boot wiring: observation phải bật trên bean thật

Nếu có custom `KafkaTemplate` và custom listener factory, hãy kiểm tra thuộc tính đã bật và registry/wiring đúng.

Ví dụ test trong Spring context:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.KafkaTemplate;

@SpringBootTest
class KafkaObservationWiringTest {

    @Autowired
    @Qualifier("paymentKafkaTemplate")
    KafkaTemplate<String, String> template;

    @Autowired
    @Qualifier("observedListenerFactory")
    ConcurrentKafkaListenerContainerFactory<String, String> factory;

    @Test
    void customComponentsHaveObservationEnabled() {
        // Kiểm tra factory/container properties theo API của version.
        assertTrue(
                factory.getContainerProperties().isObservationEnabled()
        );

        // Ngoài việc kiểm tra bean tồn tại, test tích hợp phải
        // phát sinh một send và xác nhận observation thật.
        assertTrue(template != null);
    }
}
```

Ví dụ chỉ là **kiểm tra wiring cơ bản**. Khi dự án dùng nhiều custom factories, phải kiểm tra listener sử dụng chính factory được test và template có được bật observation đúng. Spring test context cần đủ dependency, config và bean producer/consumer; cấu hình test có thể dùng bootstrap giả nếu test chưa kết nối broker, nhưng không được coi test này là xác nhận network.

### 27.1. Kiểm thử Kafka end-to-end với broker test

`spring-kafka-test` và `@EmbeddedKafka` cho phép kiểm tra gửi/nhận record. Ví dụ cấu trúc:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.context.EmbeddedKafka;

@SpringBootTest(properties = {
        "spring.kafka.listener.observation-enabled=true",
        "spring.kafka.template.observation-enabled=true"
})
@EmbeddedKafka(
        partitions = 2,
        topics = {
                "test-payments-in",
                "test-payments-out"
        },
        bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class KafkaObservationIntegrationTest {

    @Test
    void producerAndListenerAreObserved() {
        // Arrange: tạo message/test listener và registry test.
        // Act: gửi record vào embedded topic.
        // Assert:
        //   1. Listener nhận record với timeout hữu hạn.
        //   2. Có observation/span phù hợp cho send và receive.
        //   3. Metrics Timer nhận mẫu theo version hiện có.
        //   4. Không có record bị xử lý ngoài ý muốn.
    }
}
```

Đây là **khung test**, chưa khai báo đầy đủ listener, template, registry hoặc assertions. Việc dùng `@EmbeddedKafka` không tự chứng minh traces được exporter ngoài nhận. Để kiểm tra exporter, cần integration test với in-memory span exporter hoặc collector test có thể kiểm tra dữ liệu.

### 27.2. Test bằng Testcontainers cho môi trường production-like

Testcontainers Kafka có thể mô phỏng broker tốt hơn ở một số khía cạnh, và có thể chạy hai Kafka containers để kiểm tra configuration multi-cluster.

Các kịch bản quan trọng:

1. Consumer nhận record trên cluster A; producer gửi sang cluster B.
2. Cả hai phía tạo metrics/observations từ đúng factory.
3. Tracing context theo event khi dịch vụ chuyển message.
4. Producer broker B unavailable: future thất bại; outbox pending tăng, không mất event.
5. Consumer DB timeout: retries được ghi nhận, business counter không tăng sai.
6. Message invalid: listener error handler chuyển DLT theo policy, có metric final recovery.
7. Consumer rebalance/restart: offset commit semantics đúng; event vẫn idempotent.
8. Schema/deserialization failure: có error signal khi listener method chưa được gọi.
9. Mất Collector: business processing vẫn vận hành theo thiết kế, telemetry có giới hạn retry/buffer.
10. Endpoint Prometheus bị chặn từ mạng không được phép, nhưng scraper được quyền vẫn truy cập.

Không thể thay test hai cluster bằng test hai topic trong **một broker** rồi kết luận đã kiểm tra chính sách credentials, routing và cross-cluster failures.

## 28. Những vấn đề vận hành thường gặp

### 28.1. Có metrics nhưng không có trace

Kiểm tra:

- Đã có Micrometer Tracing bridge tương thích chưa?
- Observation có thực sự bật ở template/listener không?
- Có ObservationRegistry và tracing handler hoạt động không?
- Sampling probability có quá thấp để thấy trace trong test không?
- Collector/endpoint/credentials đúng không?
- Trace headers có được truyền qua Kafka không?
- Context có bị mất ở async executor không?

**Không nên tăng sampling lên 100% ở production lâu dài chỉ để debug một sự cố** mà không đánh giá lưu lượng và chi phí. Có thể tạm tăng theo runbook.

### 28.2. Có trace nhưng không có Kafka client metrics

Kiểm tra factory/client Micrometer instrumentation, registry, bean auto-config, topic có traffic và endpoint. Traces KafkaTemplate/listener không thay thế Kafka client metrics về fetch, buffer, retry.

### 28.3. Consumer lag biến mất khi pod crash

Nếu dashboard chỉ đọc gauges từ KafkaConsumer sống, pod chết có thể khiến series dừng và nhìn như không có lag. Dùng group lag exporter từ cluster và scrape target availability để phát hiện tình huống này.

### 28.4. Metrics nhân đôi sau khi thêm instrumentation

Nếu có Timer manual bọc listener và bật Observation Timer, cùng một operation có thể bị đo hai lần với tên gần giống nhau. Xác định nguồn đo cho từng panel, bỏ instrumentation thừa hoặc đặt tên rõ ràng.

### 28.5. DLT bị tăng nhưng listener failure rate trông thấp

Có thể error handler recover record và listener instrumentation có semantics result/exception khác cách business metric được định nghĩa. Cần quan sát recoverer outcome và DLT publisher, không chỉ error tag của listener Timer.

### 28.6. Traces không nối được giữa producer và consumer

Một số nguyên nhân: type headers/trace headers bị lọc, format không tương thích, producer chưa bật observation, listener custom factory chưa bật, async context mất hoặc sampling. Kiểm tra record headers ở môi trường test an toàn, không log toàn bộ payload production.

### 28.7. Consumer processing chậm nhưng Kafka client metrics bình thường

Lỗi có thể nằm ở database connection pool, HTTP downstream, thread contention hoặc GC. Trace nested operation và DB metrics thường hữu ích hơn chỉ xem Kafka network.

### 28.8. Không có meter cho topic vắng traffic

Một số meters chỉ được tạo khi operation xảy ra. Không có series không đồng nghĩa trạng thái khỏe. Khi alert cần phân biệt `missing telemetry` với `zero traffic`, ví dụ dùng `up`, Kafka group assignment và business schedule.

## 29. Quy trình thiết lập giám sát từ đầu

Một quy trình triển khai có thể thực hiện theo thứ tự:

1. **Chốt SLO và event semantics:** consumer lag, event age, delivery success, DLT recovery và business commit.
2. **Thêm Actuator/registry:** xác nhận `/actuator/metrics` và `/actuator/prometheus` trên ứng dụng.
3. **Bật Observation cho KafkaTemplate và listener factory thực sự dùng:** qua Boot properties hoặc Java custom beans.
4. **Cấu hình tracing bridge/exporter:** xác nhận spans tới backend ở test environment.
5. **Thu Kafka client metrics:** xem producer retry/buffer và consumer poll/commit.
6. **Thu broker và group lag độc lập:** tránh chỉ dựa client gauges.
7. **Thêm business metrics có định nghĩa rõ:** attempt, accepted, duplicate, final failure, outbox pending.
8. **Kiểm soát tags:** chỉ low-cardinality labels, không payload/event ID.
9. **Thiết kế dashboard:** overview, producer, consumer, DLT, dependencies.
10. **Thiết kế alert theo SLO:** có cửa sổ thời gian, runbook và owner.
11. **Kiểm thử failure cases:** broker/DB/collector lỗi, rebalance, duplicate delivery, DLT publish failure.
12. **Triển khai có kiểm chứng:** đối chiếu telemetry cũ/mới nếu nâng cấp instrumentation hoặc đổi metric names.
13. **Theo dõi chi phí:** cardinality, traces/s, storage retention, exporter CPU/memory.
14. **Duy trì contract:** khi đổi Kafka version, serializer, group ID, partitions hoặc concurrency, cập nhật metric queries và runbook.

## 30. Checklist cho deployment và cấu hình

| Kiểm tra | Vì sao quan trọng? |
|---|---|
| Có `spring-boot-starter-actuator` và registry exporter phù hợp | Metrics có điểm xuất |
| Observation được bật trên đúng KafkaTemplate | Publish flow có instrumentation |
| Observation được bật trên đúng listener container factory | Receive callback có instrumentation |
| Tracing bridge/exporter được cấu hình nếu cần traces | Span không chỉ tồn tại trong memory |
| Kafka client metrics hiện diện sau khi client thực hoạt động | Có số liệu network/poll/buffer |
| Broker và group lag có nguồn đo độc lập | Phát hiện consumer chết và backlog |
| Topic/group/client IDs có cardinality kiểm soát | Backend không nổ series |
| Không dùng payload/event ID làm metric tag | Tránh cardinality và rò dữ liệu |
| Micrometer Timer/histogram không bị đếm trùng | SLO/p95 đáng tin |
| Retry metrics phân biệt attempts và final failures | Không phóng đại lỗi |
| DLT publish được quan sát và có runbook | Có đường phục hồi dữ liệu |
| Outbox pending/age được đo nếu có outbox | Phát hiện event chưa được gửi |
| Actuator endpoint không public ngoài ý muốn | Bảo vệ thông tin vận hành |
| Collector outage không làm business flow treo | Telemetry không thành single point of failure |
| Alert có ngưỡng và cửa sổ theo SLA | Giảm false positives |
| Test restart/rebalance/offset commit | Không suy luận sai về exactly-once |
| Multi-cluster routing được kiểm thử | Không gửi metric/debug message sang sai nơi |
| Profile production không fallback localhost tùy tiện | Fail fast khi thiếu cấu hình |
| Cấu hình và metric names được version hóa | Upgrade không làm dashboard mù |

## 31. Bài tập thực hành

Xây dựng dịch vụ `payment-worker` gồm một consumer nhận `payment-commands.v1`, một producer gửi `payment-results.v1` và database lưu trạng thái thanh toán.

### Yêu cầu 1: Metric cơ bản

1. Thêm Actuator và Prometheus registry.
2. Expose `/actuator/metrics` và `/actuator/prometheus` trên mạng test có kiểm soát.
3. Bật listener và template observation bằng Spring Boot properties.
4. Gửi 20 records vào topic test, xác nhận Timer/metrics có mẫu khi vận hành.
5. Phân biệt metric số lượt callback với số business events unique sau dedup.

### Yêu cầu 2: Tracing

6. Thêm Micrometer Tracing bridge và exporter OTLP vào Collector test.
7. Xác nhận trace gồm Kafka producer và consumer span phù hợp.
8. Thêm nested observation `payment.process` quanh business operation.
9. Thử hand off sang async executor và xác minh context propagation.
10. Kiểm tra không có payload, token hoặc số tài khoản trong span/baggage.

### Yêu cầu 3: Reliability metrics

11. Thêm business counters `accepted`, `duplicate` và `rejected` với outcome labels có giới hạn.
12. Mô phỏng DB timeout hai lần rồi thành công; phân biệt số retry attempts với final failures.
13. Cấu hình một DLT recoverer; theo dõi số record chuyển DLT và số lần DLT send thất bại.
14. Dùng một nguồn đo consumer-group lag ngoài client để phát hiện pod consumer chết.
15. Mô phỏng producer nhận broker ACK chậm và kiểm tra producer future errors/latency.

### Yêu cầu 4: Dashboard và alert

16. Tạo dashboard gồm group lag, records/s, listener p95, producer retry/error, DLT count và outbox age.
17. Đặt alert lag tăng 15 phút và event processing age vượt SLO; giải thích tại sao không alert chỉ từ một sample.
18. Xác nhận dashboard không sử dụng dynamic `eventId` hoặc payload làm label.
19. Thực hiện load test với sampling 1%, 10% và 100%; so throughput, CPU và trace volume trên môi trường test.
20. Mô phỏng Collector outage, xác nhận business flow vẫn tiếp tục theo thiết kế.
21. Nếu consumer đọc cluster A và producer gửi cluster B, tạo factory/template riêng, bật observation trên mỗi bean và chứng minh traces/metrics không nhầm cluster.
22. Viết runbook cho ba tình huống: lag cao, DLT tăng và mất trace sau deploy.

**Câu hỏi ôn tập 1:** Đã bật `spring.kafka.listener.observation-enabled=true` và thấy Timer listener. Điều đó có chứng minh message chỉ xử lý đúng một lần và DB đã commit không?

**Trả lời:** **Không.** Timer thể hiện operation được instrument theo semantics của listener; commit offset, database transaction, retry/rebalance và idempotency là các vấn đề khác. Cần instrumentation nghiệp vụ và kiểm thử consistency.

**Câu hỏi ôn tập 2:** Consumer pod chết khiến metric `records-lag-max` của pod biến mất. Có thể kết luận group không còn lag không?

**Trả lời:** **Không.** Metric của client ngừng xuất vì client không tồn tại. Cần đo group lag từ Kafka cluster/offsets và giám sát availability của pod/scrape target.

**Câu hỏi ôn tập 3:** Nếu metric `spring_kafka_listener_seconds_count` tăng 1.000 lần, có phải chính xác 1.000 event unique đã được xử lý thành công?

**Trả lời:** **Không nhất thiết.** Timer count có thể tương ứng callback attempts, batch listener, retries hoặc các result khác theo framework. Muốn đếm business events unique cần key, transaction và business metrics/audit có định nghĩa riêng.

## 32. Tài liệu tham khảo

- [Spring Boot Reference — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): Boot Kafka properties, KafkaTemplate, listener container và observation configuration.
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): MeterRegistry, Actuator metrics endpoint, Prometheus exporter và distribution settings.
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, bridges, tracing exporter và sampling.
- [Spring Kafka Reference — Micrometer](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html): Micrometer metrics, observation và monitoring cho KafkaTemplate/listeners.
- [Spring Kafka Reference — Observability](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html): listener/template observation và conventions trên những phiên bản hỗ trợ.
- [Spring Kafka Reference — Receiving Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages.html): listener container, ack modes và concurrency.
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): DefaultErrorHandler, retry/recovery và DLT.
- [Spring Kafka Reference — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): transaction Kafka và giới hạn bảo đảm.
- [Spring Kafka Reference — Testing](https://docs.spring.io/spring-kafka/reference/testing.html): EmbeddedKafka và integration test.
- [Micrometer Documentation — Observation](https://docs.micrometer.io/micrometer/reference/observation.html): observation lifecycle, conventions và key-values.
- [Micrometer Documentation — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): Timer và cách đo duration.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): tracing context xuyên process.
- [Prometheus Documentation — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): rate, bucket và percentile.
- [Apache Kafka — Monitoring](https://kafka.apache.org/documentation/#monitoring): Kafka broker/client metrics.
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs): offset, poll, fetch và group semantics.
