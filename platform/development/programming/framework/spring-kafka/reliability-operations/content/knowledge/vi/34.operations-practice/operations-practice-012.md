# Thiết kế dashboard reliability cho Spring Kafka

## 1. Mục tiêu của dashboard reliability

Khi vận hành một hệ thống dùng Spring Kafka, câu hỏi quan trọng nhất không phải chỉ là **“Kafka còn chạy không?”**, mà là:

> **Các sự kiện nghiệp vụ được nhận, xử lý, hoàn tất và có thể khôi phục đúng thời hạn hay không?**

Một Kafka cluster có thể khỏe, topic vẫn nhận message và consumer process vẫn `UP`, nhưng một nhóm message đã kẹt vì poison pill, consumer lag tăng, retry kéo dài hoặc dữ liệu đã bị gửi vào dead-letter topic (DLT) mà không ai xử lý.

Ví dụ kiến trúc nhập đơn hàng:

```text
Order API
   |
   | produce order.created
   v
Kafka: orders.created
   |
   | consumer group = order-processors
   v
Spring Kafka @KafkaListener
   |
   +-- success --> update/order projection --> business completion
   |
   +-- transient failure --> retry / backoff --> success
   |
   +-- non-recoverable --> orders.created.DLT --> investigation/re-drive
```

Dashboard vận hành cần thể hiện cả **khả năng phục vụ hiện tại**, **độ trễ đầu cuối**, **tốc độ xử lý**, **tồn đọng**, **lỗi và khôi phục**, đồng thời cung cấp đủ ngữ cảnh để on-call quyết định bước tiếp theo.

Sau bài này, người học có thể:

1. Chuyển yêu cầu reliability thành SLI/SLO có thể đo được.
2. Chọn metric theo từng lớp producer, Kafka broker, consumer group, Spring listener, retry và DLT.
3. Thiết kế dashboard Grafana/Prometheus có cấu trúc từ tổng quan đến drill-down.
4. Phân biệt lag, throughput, processing latency, event age và tỷ lệ thành công.
5. Bổ sung instrumentation bằng Spring Boot Actuator và Micrometer.
6. Viết PromQL cho các panel và cảnh báo, biết giới hạn của số liệu.
7. Lập runbook điều tra khi lag tăng, listener lỗi, DLT phình to hoặc producer bị fencing.
8. Kiểm chứng dashboard qua failure injection trước khi sử dụng trong production.

Phạm vi minh họa: **Java 17+, Spring Boot 3.x, Spring Kafka 3.x, Micrometer, Prometheus và Grafana**. Các tên metric do ứng dụng tự tạo trong bài là *quy ước minh họa*, không phải cam kết toàn bộ Spring Kafka xuất sẵn những metric đó. Hệ thống dùng Spring Kafka 4.x hoặc exporter khác cần xác nhận tên metric và API theo phiên bản.

## 2. Bản đồ luồng dữ liệu và nơi phát sinh tín hiệu

```text
       [Producer API / Outbox publisher]
         |  acks, send failures, send latency
         |  retries, throughput, transaction outcome
         v
       [Kafka Broker + Topic]
         |  broker health, partitions, replication
         |  throughput, request latency, ISR
         v
       [Consumer Group]
         |  committed offsets, log end offsets
         |  group lag, rebalance, assignment
         v
       [Spring @KafkaListener]
         |  handled records, processing latency
         |  exceptions, retries, acknowledgements
         v
       [Database / External API / Kafka output]
         |  business completion, idempotency
         |  E2E age, correctness, publish outcome
         |
         +-- failed / exhausted retry
                      |
                      v
                  [DLT / Quarantine]
                      |
                      +-- oldest unresolved, re-drive
                      +-- recovery outcome and age

 Observability plane:
  Spring Boot Actuator/Micrometer
  Kafka client metrics/JMX
  Broker JMX metrics
  Consumer group offset exporter
  Logs/traces/audit and deployment annotations
                      |
                      v
              Prometheus / TSDB
                      |
                      v
             Grafana dashboards + alerts
```

**Nguyên tắc quan trọng:** không một loại metric đơn lẻ nào mô tả toàn bộ hành trình. Consumer lag đến từ vị trí commit và vị trí cuối log; số record xử lý thành công đến từ application; broker replication health đến từ Kafka; business correctness thường phải đo trong database hoặc hệ thống downstream.

Một dashboard “Kafka OK” chỉ hiển thị số broker và CPU sẽ bỏ lỡ sự cố nghiệp vụ. Ngược lại, một dashboard chỉ có listener exception có thể bỏ qua broker unavailable, under-replicated partitions hoặc consumer group không còn được assign partition nào.

## 3. Xác định người dùng dashboard và câu hỏi cần trả lời

Thiết kế panel từ câu hỏi vận hành, không bắt đầu bằng việc kéo mọi metric có sẵn lên Grafana.

| Đối tượng | Câu hỏi chính | Thông tin cần thấy |
| --- | --- | --- |
| On-call ứng dụng | Message có đang được xử lý đúng hạn? | SLO, backlog, tuổi sự kiện, error/retry/DLT, trạng thái consumer |
| Nhóm Kafka platform | Broker có đáp ứng được lưu lượng? | ISR, under-replicated partitions, request latency, broker/network/disk |
| Chủ sở hữu nghiệp vụ | Đơn hàng nào đang bị chậm hoặc thất bại? | Business completion, số sự kiện pending, DLT/quarantine và đối soát |
| Nhóm triển khai | Rollout mới có làm reliability giảm không? | Annotate deploy, error/lag trước-sau, rebalance, phiên bản |
| Incident commander | Blast radius và diễn tiến sự cố là gì? | Cluster, environment, service, topic, consumer group và thời gian bắt đầu |

Nên có **một dashboard tổng quan** cho trạng thái cuối người dùng và các dashboard chi tiết theo component. Không nên ép hàng trăm panel vào một màn hình tổng quan; càng nhiều panel không nhất thiết càng dễ xử lý sự cố.

### Các chiều lọc tối thiểu

Dashboard mẫu cung cấp biến:

```text
environment: dev | staging | prod
cluster: kafka-cluster-a | kafka-cluster-b
service: orders-producer | orders-consumer
topic: orders.created | orders.validated | orders.created.DLT
consumer_group: order-processors
listener: orderCreatedListener
```

Các danh sách này phải đến từ inventory hoặc label đáng tin, không dựa vào việc dashboard tự đoán topic thuộc business flow nào. Nên có naming convention để production/staging không trộn và không cộng chung metrics giữa hai Kafka clusters.

## 4. Reliability không đồng nghĩa throughput

Hệ thống có thể xử lý 50.000 events/giây nhưng vẫn mất một loại record quan trọng. Vì vậy các tín hiệu cần được nhóm theo mục tiêu:

| Mục tiêu | SLI hoặc signal | Ý nghĩa |
| --- | --- | --- |
| Availability | Tỷ lệ event đủ điều kiện được hoàn tất | Message không biến mất âm thầm |
| Timeliness | Tỷ lệ hoàn tất trong thời hạn, p95/p99 event-to-completion | Không chỉ “eventually processed” |
| Integrity | Duplicate/missing/inconsistent business effect | Không lặp thanh toán hoặc bỏ sót đơn |
| Recoverability | Retry success, DLT recovery time, unresolved backlog | Có thể đưa record lỗi về trạng thái đúng |
| Capacity | Lag, ingress/egress rate, consumer saturation | Có đủ năng lực để theo kịp nguồn |
| Infrastructure | Broker availability, ISR, replication, storage | Hệ thống nền có ổn định |

**Thành công của listener chưa chắc là thành công của nghiệp vụ.** Nếu listener chỉ đưa message vào một queue nội bộ rồi return, metric listener success đo việc *nhận và chuyển tiếp*, không phải đơn hàng đã ghi thành công vào database.

Do đó, trước khi tạo metric tên `success`, cần viết rõ **thành công tại ranh giới nào**: deserialize, invoke handler, persist DB, commit offset, hay hoàn tất nghiệp vụ end-to-end.

## 5. Thiết kế SLI và SLO trước khi chọn biểu đồ

Giả sử sản phẩm cam kết: **99,9% sự kiện đơn hàng hợp lệ được hoàn tất trong 5 phút, đo theo cửa sổ 30 ngày**.

Định nghĩa:

- *Eligible event*: sự kiện có business ID hợp lệ, thuộc contract đã được nhận, không nằm trong tập được loại trừ theo chính sách đã công bố.
- *Completed event*: kết quả nghiệp vụ đã được ghi nhận bền vững ở ranh giới đã định, không chỉ listener return.
- *Latency*: từ thời điểm sự kiện được chấp nhận (hoặc business event time được quy định) đến thời điểm outcome được commit.
- *Denominator*: số **business event duy nhất**, không phải tổng số lần listener được gọi.
- *Window*: 30 ngày rolling, UTC hoặc timezone theo contract.

SLI minh họa:

\[
\text{TimelyCompletionSLI}
=\frac{\#\{\text{eligible events hoàn tất trong 5 phút}\}}
{\#\{\text{eligible events đã đủ thời hạn đánh giá}\}}
\]

Nếu sự kiện mới được nhận 10 giây trước mà deadline là 5 phút, chưa nên tính nó là vi phạm deadline ở mẫu số “đã đủ thời hạn đánh giá”, trừ khi định nghĩa SLO lựa chọn cách tính khác. Cần công bố quy tắc cutoff để tránh dashboard biến động sai khi traffic tăng.

SLO ví dụ:

```text
SLI: timely business completion, per unique eligible event
SLO: >= 99.9% over rolling 30 days
Deadline: 5 minutes
Exclusions: explicitly documented invalid-source cases only
Owner: orders-processing team
Error budget: 0.1% of eligible events in window
```

### Vì sao không lấy listener error rate làm SLO duy nhất?

Một event có thể được handler gọi ba lần:

```text
Attempt 1: timeout   -> failure
Attempt 2: timeout   -> failure
Attempt 3: success   -> completed business effect
```

Nếu tính trên **attempts**, tỷ lệ thành công là 1/3. Nếu tính trên **unique eligible business events**, event đó hoàn tất thành công. Cả hai con số đều hữu ích, nhưng chúng đo hai thứ khác nhau:

- **Attempt failure rate**: tín hiệu phục vụ điều tra, năng lực và lỗi phụ thuộc.
- **Business completion SLI**: trải nghiệm/độ tin cậy của luồng nghiệp vụ.

Để tính chính xác unique completion SLI, cần event ID và một ledger/state machine hoặc dữ liệu nguồn đáng tin cậy; chỉ tính `rate(listener_success_total) / rate(listener_total)` thường không đủ.

## 6. Bốn nhóm chỉ số đầu tiên cần có

Để nhanh chóng có dashboard hữu dụng, ưu tiên:

1. **Traffic và progress:** tốc độ producer gửi thành công, tốc độ consumer xử lý và số business event hoàn tất.
2. **Lag và freshness:** độ tồn đọng consumer group, tuổi sự kiện khi được xử lý, thời gian kể từ lần hoàn tất gần nhất.
3. **Errors và recovery:** lỗi handler, retry, DLT, transaction abort và số record chưa được xử lý lại.
4. **Saturation và infrastructure:** CPU/heap, connection pool, thread concurrency, broker request latency và replication health.

Đây là các nhóm liên quan mô hình **traffic, errors, latency, saturation** (golden signals). Với Kafka, cần bổ sung thông tin **offset, lag, rebalance và DLT** vì đây là pipeline bất đồng bộ, không phải một HTTP request/response đơn giản.

## 7. Consumer lag: metric quan trọng nhưng dễ bị hiểu sai

Ở một topic-partition, một mô hình lag thường dùng:

\[
\text{lag}_{p}
=\text{logEndOffset}_{p}-\text{committedOffset}_{p}
\]

Trong thực tế, các exporter/Kafka client metric có thể tính khác nhau theo **fetch position** hoặc **committed group offset**. Cần biết cụ thể datasource của mình đang hiển thị loại lag nào.

Ví dụ consumer group có bốn partitions:

| Partition | Group lag (records) |
| --- | ---: |
| 0 | 1.200 |
| 1 | 1.100 |
| 2 | 40 |
| 3 | 60 |
| **Tổng** | **2.400** |

Nếu group duy trì **100 record/giây** và không có dữ liệu mới, phép tính `2.400/100 = 24 giây` có thể dùng làm **ước lượng rất thô** để hình dung backlog, không phải “event age” thật hay SLA. Khi producer vẫn ghi, phân phối partition lệch, record có thời gian xử lý khác nhau hoặc consumer bị pause, con số này có thể sai lớn.

### Những cách dùng lag đúng

- Tổng lag theo **consumer group + topic + cluster**: quy mô backlog.
- Lag lớn nhất theo partition: phát hiện partition hot hoặc mất cân bằng assignment.
- Tốc độ thay đổi lag: backlog đang tăng, giảm hay đứng yên.
- Lag so với input rate và processing throughput: tìm nguyên nhân không theo kịp.
- Lag của retry topics và DLT (nếu có consumer tương ứng): backlog chưa được xử lý ở từng luồng.

### Những điều lag không nói được

- Không tự cho biết **tuổi của record cũ nhất**.
- Không chứng minh event được xử lý đúng nghiệp vụ.
- Không đo thời gian handler dành cho mỗi record.
- Không chỉ ra vì sao consumer chưa commit offset.
- Không thể hiện đầy đủ các event đã bị publish thành công vào DLT nhưng chưa được xử lý lại.

**Lưu ý đặc biệt về offset commit:** với manual ack, transactions và asynchronous processing, vị trí fetch, vị trí xử lý và vị trí commit có thể khác nhau. Một nhóm có thể đã đọc nhiều records nhưng chưa commit; tùy exporter, lag sẽ phản ánh “chưa commit” hoặc “chưa fetch”. Không dùng một metric lag không rõ semantics làm bằng chứng rằng đã hoàn tất business work.

## 8. Phân biệt processing latency, event age và backlog age

Các thời gian thường được gọi chung là “Kafka latency”, nhưng ý nghĩa khác nhau:

| Metric | Bắt đầu | Kết thúc | Ý nghĩa |
| --- | --- | --- | --- |
| Producer send latency | Bắt đầu send | Broker acknowledgement/future completed | Phần gửi và xác nhận |
| Kafka broker request latency | Broker nhận request | Broker trả response | Hiệu năng broker/network |
| Listener processing duration | Bắt đầu handler | Handler return/throw | Thời gian logic xử lý trong application |
| Event age at processing | Event timestamp đã chọn | Lúc bắt đầu hoặc hoàn tất xử lý | Dữ liệu đến xử lý có cũ không |
| Business end-to-end latency | Event được accept | Business result durable | Trải nghiệm nghiệp vụ thực tế |
| Oldest unresolved backlog age | Event chưa hoàn tất cũ nhất | Thời điểm hiện tại | Độ già của tồn đọng chưa giải quyết |
| DLT unresolved age | DLT/quarantine event chờ xử lý lâu nhất | Thời điểm hiện tại | Rủi ro recovery quá hạn |

### Event time có thể không đáng tin

`ConsumerRecord.timestamp()` là timestamp của record với kiểu `CREATE_TIME` hoặc `LOG_APPEND_TIME`, tùy Kafka topic/broker/producer configuration. Nó không nhất thiết là thời điểm event nghiệp vụ xảy ra.

Nếu muốn đo SLA “sau khi hệ thống nhận đơn”, cần một `acceptedAt` đáng tin tại boundary nghiệp vụ, được giữ xuyên suốt retry/DLT. Nếu lấy timestamp của record retry topic mới, tuổi event có thể **bị reset** sau mỗi lần publish lại.

Ngoài ra, đồng hồ giữa producer và consumer có thể lệch. Hãy chuẩn hóa UTC, NTP và định nghĩa cách xử lý negative duration do clock skew; không âm thầm biến một timestamp không hợp lệ thành “latency bằng 0”.

## 9. Bộ metric đề xuất cho dashboard

Để các ví dụ PromQL nhất quán, bài này định nghĩa một **contract metric minh họa**. Chúng chỉ tồn tại nếu ứng dụng hoặc exporter của bạn phát ra đúng tên/label:

| Metric Prometheus minh họa | Loại | Nhãn quan trọng | Nguồn |
| --- | --- | --- | --- |
| `app_kafka_listener_records_total` | Counter | service, listener, result | Application instrumentation |
| `app_kafka_listener_processing_seconds_bucket` | Histogram | service, listener, le | Micrometer Timer cấu hình histogram |
| `app_kafka_business_events_total` | Counter | service, flow, outcome | Business completion ledger/instrumentation |
| `app_kafka_retry_attempts_total` | Counter | service, listener, reason | Error handler/retry instrumentation |
| `app_kafka_dlt_published_total` | Counter | service, source_topic, result | DLT producer callback/recoverer |
| `app_kafka_dlt_unresolved_records` | Gauge | service, dlt_topic | Quarantine/DLT audit system |
| `app_kafka_dlt_oldest_unresolved_age_seconds` | Gauge | service, dlt_topic | Recovery state store |
| `app_kafka_consumer_group_lag_records` | Gauge | cluster, consumer_group, topic, partition | Kafka exporter/group offsets |
| `app_kafka_producer_sends_total` | Counter | service, result, destination | Producer instrumentation |
| `app_kafka_transaction_outcomes_total` | Counter | service, outcome | Transaction lifecycle instrumentation |
| `app_kafka_last_business_success_timestamp_seconds` | Gauge | service, flow | Application durable success checkpoint |
| `app_kafka_event_to_completion_seconds_bucket` | Histogram | service, flow, le | End-to-end business instrumentation |

Không nên khai báo mọi metric thành custom nếu Micrometer hoặc exporter đã có metric phù hợp. **Trước tiên inventory metrics hiện có** rồi đặt một chuẩn tên, định nghĩa và đơn vị để tránh double count.

### Metric label và đơn vị phải nhất quán

- Counter tăng theo số lần hoặc số event; không reset chủ động giữa chu kỳ, ngoại trừ process restart vốn Prometheus xử lý qua `rate`/`increase`.
- Gauge có thể lên/xuống, phù hợp backlog và lần cuối thành công.
- Histogram bucket đo seconds cho latency, không trộn milliseconds với seconds trong cùng metric.
- Topic, service, listener, cluster là chiều lọc hữu ích nhưng số lượng cần được quản lý.
- Không dùng `eventId`, `orderId`, `correlationId`, `offset`, stacktrace hay exception message làm label; chúng có cardinality rất cao.

## 10. Các metric nào Spring Kafka có sẵn?

Spring Kafka và Kafka clients cung cấp nhiều tín hiệu qua Micrometer, Observation và Kafka client metrics; broker có metric JMX. Nhưng **tên Prometheus cuối cùng không đồng nhất giữa mọi phiên bản, binder, exporter và metric naming convention**.

Ví dụ theo nhóm:

| Nguồn | Có thể quan sát | Những điều không tự có |
| --- | --- | --- |
| Spring Kafka listener metrics/Observation | Listener invocation duration, result hoặc tags theo config | Unique business completion SLO |
| Spring Kafka template metrics/Observation | Send/template operation duration | Transaction final commit của toàn business flow |
| Kafka producer metrics | Record send rate, error/retry rate, request latency, buffer wait | Đơn hàng đã hoàn tất trong DB |
| Kafka consumer metrics | Consume rate, poll/fetch, lag theo client, rebalance | Toàn bộ backlog chưa xử lý của consumer group nếu không có committed-offset exporter |
| Kafka broker JMX | Request throughput, ISR, under-replicated partitions, controller, storage | Message outcome ở business layer |
| Consumer group exporter | Group committed offset và log end offset/lag | Handler failure hoặc DLT recovery |
| Application custom instrumentation | Retry/DLT decisions, business completion, idempotency conflicts | Infrastructure health nếu không tích hợp exporter |

Trong Spring Kafka 3.x, một số built-in metrics có tên dạng `spring.kafka.listener` hoặc `spring.kafka.template` trong Micrometer; khi xuất Prometheus chúng thường được đổi thành quy ước dấu gạch dưới và suffix thời gian. **Hãy kiểm tra `/actuator/metrics` hoặc `/actuator/prometheus` trên đúng build đang triển khai**, thay vì copy một tên metric trên internet vào dashboard rồi coi “No data” là hệ thống không hoạt động.

Mọi ví dụ PromQL phía dưới sử dụng **contract custom metric đã nêu ở mục 9**, không phụ thuộc một tên exporter Kafka cụ thể.

## 11. Bật Actuator và Prometheus endpoint

### 11.1. Dependency

Ví dụ `pom.xml` với Spring Boot dependency management:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-kafka</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
```

Trong hệ Spring Boot chuẩn, Spring Kafka starter thường được cung cấp bằng dependency `org.springframework.kafka:spring-kafka`, không phải mọi phiên bản Boot đều có artifact `spring-boot-starter-kafka`. Nếu build hiện tại không có starter Kafka tương ứng, dùng dependency chính thức:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
```

Với Spring Boot 3.x và Spring Kafka 3.x, **`spring-kafka`** là dependency chính thức an toàn để khai báo khi Boot BOM đã quản lý version. Trong project thực tế, chọn một phương án dependency được build chứng minh hỗ trợ; đừng giữ cùng lúc một starter không tồn tại và dependency thay thế. Ví dụ `pom.xml` đầu mục chỉ nhằm thể hiện nhu cầu Kafka + Actuator + Prometheus.

### 11.2. application.yml

```yaml
spring:
  application:
    name: orders-consumer
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    consumer:
      group-id: order-processors
      auto-offset-reset: earliest

management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      probes:
        enabled: true

logging:
  level:
    org.springframework.kafka: INFO
```

Boot Actuator expose `/actuator/prometheus` nếu registry và endpoint được cấu hình phù hợp. Trong Kubernetes production:

- Chỉ expose endpoint metrics qua mạng nội bộ hoặc cổng management có policy truy cập.
- Không mở toàn bộ actuator endpoints ra public internet.
- Dùng NetworkPolicy, auth/TLS hoặc metrics sidecar theo hạ tầng.
- Đừng đặt thông tin bí mật trong metric tags hoặc custom metric names.

### 11.3. Ví dụ Prometheus scrape

```yaml
scrape_configs:
  - job_name: spring-kafka-orders
    metrics_path: /actuator/prometheus
    scrape_interval: 15s
    static_configs:
      - targets:
          - orders-consumer-1:8080
          - orders-consumer-2:8080
```

Đây là cấu hình minh họa cho môi trường có hostnames cố định; Kubernetes thường dùng ServiceMonitor/PodMonitor hoặc service discovery thay vì hardcode từng Pod IP. Khi tổng hợp metrics từ nhiều replicas, phải dùng `sum by (...)` hoặc `max by (...)` phù hợp semantics của từng metric, không cộng các gauge đã được exporter xuất trùng ở nhiều nơi.

## 12. Kết hợp Observation với custom business metrics

Spring Kafka 3.x hỗ trợ Micrometer Observation cho listener/template khi được bật ở container/template phù hợp. Một ví dụ cấu hình listener factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaObservationConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
    kafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setObservationEnabled(true);
        return factory;
    }
}
```

Đây là cách cấu hình theo API Spring Kafka 3.x; nếu Spring Boot đã tự tạo container factory hoặc dự án có nhiều factory, cần xác nhận bean thực sự dùng bởi `@KafkaListener`. Spring Boot/Spring Kafka phiên bản khác có thể có property để bật Observation; không nên cấu hình hai luồng metrics trùng lặp mà không xác minh.

Nếu muốn Observation cho template:

```java
KafkaTemplate<String, String> template =
        new KafkaTemplate<>(producerFactory);
template.setObservationEnabled(true);
```

`producerFactory` trong đoạn code trên là bean đã cấu hình ở ứng dụng. Observation thường giúp thu thập timing/traces của framework, còn reliability dashboard vẫn cần **business outcomes, retry, DLT và freshness** do ứng dụng định nghĩa.

### Vì sao cần custom metric?

Framework có thể biết method listener return, nhưng nó không biết “đơn hàng đã thanh toán”, “invoice đã được publish cho downstream”, “DLT record đã được sửa” hay “một customer nhận hai lần payment effect”. Chỉ business layer mới xác nhận những ranh giới đó.

## 13. Instrumentation trong Spring listener bằng Micrometer

Ví dụ một helper đo **attempts** ở listener, không coi nó là unique business events:

```java
package com.example.orders.metrics;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import org.springframework.stereotype.Component;

@Component
public class OrderListenerMetrics {

    private final Counter success;
    private final Counter failure;
    private final Timer duration;

    public OrderListenerMetrics(MeterRegistry registry) {
        this.success = Counter.builder("app.kafka.listener.records")
                .description("Handler attempts that completed normally")
                .tag("service", "orders-consumer")
                .tag("listener", "orderCreated")
                .tag("result", "success")
                .register(registry);

        this.failure = Counter.builder("app.kafka.listener.records")
                .description("Handler attempts that threw an exception")
                .tag("service", "orders-consumer")
                .tag("listener", "orderCreated")
                .tag("result", "failure")
                .register(registry);

        this.duration =
                Timer.builder("app.kafka.listener.processing")
                        .description("Handler attempt duration")
                        .tag("service", "orders-consumer")
                        .tag("listener", "orderCreated")
                        .publishPercentileHistogram()
                        .register(registry);
    }

    public void recordSuccess(Duration elapsed) {
        success.increment();
        duration.record(elapsed);
    }

    public void recordFailure(Duration elapsed) {
        failure.increment();
        duration.record(elapsed);
    }
}
```

Listener sử dụng helper:

```java
import java.time.Duration;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderService orderService;
    private final OrderListenerMetrics metrics;

    public OrderListener(
            OrderService orderService,
            OrderListenerMetrics metrics) {
        this.orderService = orderService;
        this.metrics = metrics;
    }

    @KafkaListener(
            id = "orderCreated",
            topics = "orders.created",
            groupId = "order-processors")
    public void onOrder(ConsumerRecord<String, String> record) {

        long start = System.nanoTime();
        try {
            orderService.process(record.key(), record.value());
            metrics.recordSuccess(
                    Duration.ofNanos(System.nanoTime() - start));
        } catch (RuntimeException ex) {
            metrics.recordFailure(
                    Duration.ofNanos(System.nanoTime() - start));
            throw ex;
        }
    }
}
```

`OrderService` là service nghiệp vụ do ứng dụng định nghĩa. Nó phải đảm bảo side effect và idempotency theo transaction strategy đang dùng.

**Giới hạn của phép đo này:**

- `success` nghĩa là **method `orderService.process` return thành công**.
- Nó không tự chứng minh consumer offset đã commit hoặc business transaction distributed đã commit.
- Khi listener bị retry, mỗi attempt có thể tăng counter. Đây là metric *attempt-level*, không phải SLO unique-event.
- Nếu exception thuộc loại `Error` hoặc phát sinh sau callback (ví dụ khi commit transaction), metric listener ở đây có thể chưa thấy failure.
- Nếu ứng dụng đã bật Micrometer Observation, có thể có timer framework khác; dashboard cần phân biệt nguồn và không cộng hai counter/timer trùng ngữ nghĩa.

Đo processing duration bằng `System.nanoTime()` giúp tránh sai số do thay đổi wall clock. Nhưng event-to-completion latency vẫn cần timestamp nghiệp vụ và thời điểm durable outcome.

## 14. Custom metric cho kết quả nghiệp vụ

Giả sử business completion được ghi vào bảng:

```sql
CREATE TABLE order_processing_result (
    event_id       VARCHAR(100) PRIMARY KEY,
    order_id       VARCHAR(100) NOT NULL,
    status         VARCHAR(30) NOT NULL,
    accepted_at    TIMESTAMP NOT NULL,
    completed_at   TIMESTAMP,
    last_error     VARCHAR(100)
);
```

Một event được xử lý lại có cùng `event_id`. Unique key giúp không ghi nhiều completion row cho cùng event. App có thể cập nhật trạng thái:

```text
ACCEPTED -> PROCESSING -> COMPLETED
                       \-> RETRYING
                       \-> QUARANTINED
```

**Ledger phải được thiết kế theo nghiệp vụ.** Không đơn giản coi message đã đi vào DLT là completed success; DLT có thể là kết quả *recoverable failure* nhưng vẫn vi phạm SLO hoàn tất của order.

### Lưu ý atomicity của metric và database

Giả sử DB commit thành công nhưng process crash **trước khi tăng counter**. Prometheus counter không được cập nhật, dù business event đã hoàn tất. Ngược lại, tăng counter trước commit có thể đếm cả transaction bị rollback.

Vì vậy:

- Counter Micrometer phù hợp **health/operational trends**.
- SLO đòi hỏi chính xác nên dựa trên **bản ghi durable** hoặc nguồn dữ liệu được reconcile.
- Nếu dùng counter làm SLO approximation, phải tài liệu hóa độ lệch và khả năng double count.
- Việc gắn metric sau commit chỉ giảm một số rủi ro, không tạo atomic transaction giữa TSDB và database.

### Thiết kế business outcome metrics

```text
app_kafka_business_events_total{flow="orderImport", outcome="completed"}
app_kafka_business_events_total{flow="orderImport", outcome="quarantined"}
app_kafka_business_events_total{flow="orderImport", outcome="expired"}
app_kafka_last_business_success_timestamp_seconds{flow="orderImport"}
```

Nếu một event chuyển `RETRYING -> COMPLETED`, cần quyết định counter đo **transition** hay **final outcome**; không cộng các transition thành tổng số unique events. Với SLO chính xác, tính từ snapshot/state của ledger.

## 15. Instrumentation của producer

Đối với producer, cần biết:

- Record gửi vào topic thành công hay thất bại ở mức Kafka send future.
- Latency bắt đầu send đến khi future được hoàn tất.
- Error/retry rate của Kafka client và các lỗi serialization trước network.
- Transaction commit/abort, producer fencing nếu sử dụng Kafka transactions.
- Outbox pending size và age nếu dùng outbox publisher.

Ví dụ ghi kết quả send bằng `CompletableFuture` của Spring Kafka 3.x:

```java
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.CompletableFuture;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class InstrumentedOrderPublisher {

    private final KafkaTemplate<String, String> template;
    private final MeterRegistry registry;

    public InstrumentedOrderPublisher(
            KafkaTemplate<String, String> template,
            MeterRegistry registry) {
        this.template = template;
        this.registry = registry;
    }

    public CompletableFuture<SendResult<String, String>>
    publish(String orderId, String jsonPayload) {

        long start = System.nanoTime();

        CompletableFuture<SendResult<String, String>> future =
                template.send("orders.created", orderId, jsonPayload);

        future.whenComplete((result, exception) -> {
            String outcome = exception == null ? "success" : "failure";
            registry.counter(
                    "app.kafka.producer.sends",
                    "service", "orders-producer",
                    "destination", "orders.created",
                    "result", outcome).increment();

            registry.timer(
                    "app.kafka.producer.send.duration",
                    "service", "orders-producer",
                    "destination", "orders.created")
                    .record(System.nanoTime() - start,
                            java.util.concurrent.TimeUnit.NANOSECONDS);
        });
        return future;
    }
}
```

Ví dụ giả định `template` và các topic đã được cấu hình. Không dùng exception message làm metric label; nếu cần error category, ánh xạ exception vào danh sách hữu hạn, như `SERIALIZATION`, `TIMEOUT`, `AUTHORIZATION`, `BROKER`.

**Đối với Kafka transaction:** future của send thành công không chứng minh toàn transaction cuối cùng đã **commit**. Cần metric transaction outcome ở transaction boundary, đồng thời giữ business idempotency ngoài Kafka khi có database/API. Không coi `ProducerFencedException` chỉ là retryable network error: producer bị fence cần được đóng/thay thế theo lifecycle tương ứng.

## 16. Retry và DLT: tín hiệu về khả năng khôi phục

Spring Kafka có nhiều cơ chế xử lý lỗi:

- Blocking retry với `DefaultErrorHandler` và `BackOff`.
- Non-blocking retry topics với `@RetryableTopic`/retry-topic infrastructure khi phù hợp.
- `DeadLetterPublishingRecoverer` và DLT.
- Recovery job hoặc replay tool dùng để sửa và phát lại record.

Dashboard phải phân biệt:

```text
attempt failure
     |
     +-- retry -> eventual success
     |
     +-- retries exhausted -> published to DLT
                                |
                                +-- waiting investigation
                                +-- re-drive success
                                +-- permanent rejection
```

### Các metric recovery nên có

| Signal | Định nghĩa chính | Chú ý |
| --- | --- | --- |
| Retry attempts | Tổng số lượt retry phát sinh | Một event có thể góp nhiều lượt |
| Retried event count | Số event duy nhất đã từng retry | Cần event ID hoặc audit |
| Retry exhaustion | Số event đi hết retry policy | Không nhất thiết đã vào DLT thành công |
| DLT publish success | Record đã được broker xác nhận ở DLT | Không đồng nghĩa lỗi đã được giải quyết |
| DLT publish failure | Hệ thống không lưu được failed record vào DLT | Nguy cơ mất visibility/loop failure |
| Unresolved DLT backlog | Số event đang chờ xử lý | Cần state store hoặc cơ chế tracking |
| Oldest unresolved DLT age | Thời gian tồn đọng lâu nhất | Đo recoverability SLO |
| Re-drive outcome | Phát lại thành công/thất bại | Cần chống duplicate side effect |

Nếu hệ thống chỉ có một DLT topic và không có consumer group đọc DLT, **Kafka consumer lag của DLT có thể không có ý nghĩa**. Muốn đo unresolved DLT backlog, cần một quy trình audit/quarantine quản lý trạng thái đã điều tra, đã sửa và đã re-drive.

### Không đếm DLT bằng offset delta rồi kết luận “unresolved”

Số record Kafka lưu trong DLT là **số record đã publish** (trong retention), không tự cho biết đã được re-drive hay chưa. Một record có thể được phát lại thành công nhưng vẫn tồn tại trong DLT cho đến khi retention xóa. Vì vậy, số record DLT trên broker khác với số case nghiệp vụ chưa giải quyết.

## 17. Rebalance, listener liveness và assignment

Consumer group có thể gặp vấn đề dù process còn `UP`:

- Consumer không được assign partition nào.
- Rebalance liên tục khiến việc xử lý ngắt quãng.
- `max.poll.interval.ms` bị vi phạm vì handler xử lý quá lâu.
- Consumer bị pause do error handler hoặc backoff.
- Thread listener bị treo ở dependency.
- Container đang stop hoặc authentication lỗi.

Các tín hiệu cần quan sát:

```text
assigned_partitions_count
consumer_poll_frequency
poll_idle_time
rebalance_count / rebalance_rate
last_successful_business_event_time
listener_container_running
consumer_group_lag
```

Không phải tất cả đều có sẵn với đúng tên trên; có thể lấy một số từ Kafka client metrics, Spring Kafka listener container events hoặc bổ sung custom metrics.

### Khi nào assignment=0 là lỗi?

Một consumer instance không được assign partition nào **có thể hoàn toàn bình thường** nếu số replica nhiều hơn số partitions. Đừng alert từng Pod có `assigned_partitions=0`. Hãy alert khi:

- Cả consumer group không có instance tiến hành công việc khi **đáng lẽ phải xử lý**.
- Có lag dương kéo dài nhưng không có processing progress.
- Rebalance storm khiến throughput giảm rõ rệt.

Metric cần gắn với **consumer group và workload**, không chỉ trạng thái của một Pod.

## 18. Infrastructure panel: broker và client

Application reliability không thể tách khỏi Kafka infrastructure. Tối thiểu cần dữ liệu từ Kafka broker exporter/JMX hoặc đội platform:

| Nhóm | Tín hiệu | Phân tích |
| --- | --- | --- |
| Broker health | Broker up, active controller/metadata quorum health | Có mất thành viên cluster không |
| Replication | Under-replicated/offline partitions, ISR shrink | Rủi ro durability hoặc produce bị từ chối |
| Request serving | Produce/fetch request latency, errors, request queue | Broker có phục vụ chậm không |
| Storage/network | Disk utilization, I/O, throughput, page cache | Saturation, nguy cơ hết dung lượng |
| Producer client | Send errors/retries, record size, buffer pool wait | Producer bị nghẽn từ client hay broker |
| Consumer client | Fetch rate/latency, poll activity, rebalance | Không theo kịp nguồn hoặc bị coordinator churn |
| Security | Authentication/authorization failures | Cấu hình SASL/ACL/cert hoặc credential expiry |
| Transactions | Abort/fence, transaction coordinator pressure | Lỗi exactly-once pipeline/transaction lifecycle |

**Cách lấy số liệu:** tên JMX MBean và metric exposed bởi JMX Exporter có thể thay đổi theo cấu hình exporter và Kafka version. Không hardcode tên metric trong tài liệu vận hành nếu chưa đối chiếu endpoint thực tế. Nếu nhóm Kafka platform có dashboard riêng, dashboard ứng dụng nên link trực tiếp từ panel broker health sang dashboard cluster đó.

## 19. Dashboard bố cục như thế nào?

Một dashboard trên một màn hình lớn có thể chia thành năm khu vực.

```text
┌───────────────────────────────────────────────────────────────┐
│ FILTERS: env | cluster | service | group | topic | version     │
├───────────────────────────────────────────────────────────────┤
│ SLO 30d        Last success     Lag total      Oldest DLT     │
│ 99.93%         28 sec ago       2,400 records  12 min        │
├───────────────────────────────────────────────────────────────┤
│ Incoming rate (records/s)  | Processing success rate (records/s)│
│ Total lag by group/topic   | Max partition lag                 │
├───────────────────────────────────────────────────────────────┤
│ p95/p99 processing        | Event-to-completion age p95/p99    │
│ Failure/retry rate        | DLT publish + unresolved backlog   │
├───────────────────────────────────────────────────────────────┤
│ Producer send errors      | Consumer rebalance / assignments  │
│ Transaction abort/fence   | Broker health / under-replication  │
├───────────────────────────────────────────────────────────────┤
│ Deploy / incident annotation | Logs/traces/runbooks            │
└───────────────────────────────────────────────────────────────┘
```

Các giá trị minh họa ở wireframe **không phải số đo thật** của một hệ thống.

### Hàng 1 — Tình trạng tổng thể

Hiển thị:

- SLO compliance trong cửa sổ 30 ngày, biết rõ nguồn numerator/denominator.
- Time since last **durable business success**.
- Tổng consumer group lag và max partition lag.
- Số DLT case chưa giải quyết và oldest age.

Đây là nơi on-call nhìn trong 10 giây đầu để biết luồng có đang đạt cam kết hay không.

### Hàng 2 — Traffic và progress

Đặt incoming rate cạnh processing rate. Nếu input 2.000 records/s và processing 1.000 records/s, lag sẽ tăng trừ khi có một dòng tiêu thụ khác hoặc offset semantics đặc biệt. Nếu cả hai giảm về 0, đó có thể là traffic tự nhiên giảm, upstream outage hoặc metrics pipeline mất dữ liệu — cần kiểm tra input expectation.

### Hàng 3 — Latency và failure

Hiển thị histogram p95/p99 processing duration và event-to-completion age tách biệt. Thêm retry attempts, listener exceptions và DLT outcomes. DLT published nhiều nhưng unresolved giảm đều có thể là hệ thống recovery đang làm việc; DLT unresolved tăng liên tục là tín hiệu cần hành động.

### Hàng 4 — Capacity và infrastructure

Đặt producer errors, Kafka client rebalance, assigned partitions, broker request latency/ISR cùng biểu đồ CPU/memory. Kết hợp chúng giúp xác định lỗi ứng dụng hay hạ tầng.

### Hàng 5 — Ngữ cảnh deployment

Thêm annotation khi:

- Deploy một application version mới.
- Scale replicas/concurrency.
- Đổi consumer group configuration.
- Thay retry/DLT policy.
- Broker upgrade hoặc partition reassignment.

Sự cố reliability thường bắt đầu sau thay đổi. Annotation giúp on-call tìm tương quan nhanh, nhưng **tương quan theo thời gian không tự chứng minh nguyên nhân**.

## 20. PromQL: throughput của listener

Giả sử ứng dụng đã xuất counter:

```text
app_kafka_listener_records_total{
  service="orders-consumer",
  listener="orderCreated",
  result="success"
}
```

Tốc độ handler attempts thành công trên 5 phút:

```promql
sum by (service, listener) (
  rate(app_kafka_listener_records_total{result="success"}[5m])
)
```

Tốc độ handler attempts thất bại:

```promql
sum by (service, listener) (
  rate(app_kafka_listener_records_total{result="failure"}[5m])
)
```

Tổng attempts:

```promql
sum by (service, listener) (
  rate(app_kafka_listener_records_total[5m])
)
```

Các câu query này **cộng across replicas** nhờ `sum by`. Với một listener có nhiều instance, không sử dụng một series từ Pod ngẫu nhiên để suy ra throughput toàn service.

**Giới hạn:** khi một event bị retry ba lần, nó có thể đóng góp ba attempts vào counter. Muốn số **unique business events** hoàn tất, dùng metric/ledger `app_kafka_business_events_total` đã được định nghĩa riêng.

## 21. PromQL: error rate và xử lý số liệu thưa

Tỷ lệ handler failed attempts:

```promql
sum by (service, listener) (
  rate(app_kafka_listener_records_total{result="failure"}[5m])
)
/
clamp_min(
  sum by (service, listener) (
    rate(app_kafka_listener_records_total[5m])
  ),
  0.000001
)
```

Kết quả là ratio, ví dụ `0.05` nghĩa là 5%. Với traffic thấp, chỉ một lỗi có thể khiến tỷ lệ nhảy rất cao. Vì vậy alert nên kết hợp **minimum traffic**, **duration** và impact:

```promql
(
  sum by (service, listener) (
    rate(app_kafka_listener_records_total{result="failure"}[10m])
  )
  /
  clamp_min(
    sum by (service, listener) (
      rate(app_kafka_listener_records_total[10m])
    ),
    0.000001
  )
) > 0.05
and on(service, listener)
sum by (service, listener) (
  increase(app_kafka_listener_records_total[10m])
) > 100
```

Đây là điều kiện tham khảo; không có ngưỡng 5% hay 100 attempts phù hợp với mọi workload. Một topic low-volume chứa sự kiện tài chính quan trọng có thể cần alert ngay từ **một lỗi không khôi phục**.

### Không biến No data thành OK

Khi process chết hoặc Prometheus không scrape được endpoint, rate có thể biến mất. Nếu dashboard hiển thị “0 lỗi” trong trường hợp **không có time series**, on-call có thể hiểu nhầm. Cần giám sát `up` của scrape target và alert mất metrics riêng.

## 22. PromQL: lag toàn group và partition nóng

Giả sử exporter xuất:

```text
app_kafka_consumer_group_lag_records{
  cluster="kafka-prod-a",
  consumer_group="order-processors",
  topic="orders.created",
  partition="0"
}
```

Tổng lag:

```promql
sum by (cluster, consumer_group, topic) (
  app_kafka_consumer_group_lag_records
)
```

Partition có lag cao nhất:

```promql
max by (cluster, consumer_group, topic) (
  app_kafka_consumer_group_lag_records
)
```

Top partition cần điều tra:

```promql
topk(10, app_kafka_consumer_group_lag_records)
```

**Quan trọng:** metric ví dụ phải chứa **một series duy nhất cho mỗi partition/group/topic/cluster**, hoặc query phải lọc bỏ bản sao do nhiều exporters cùng scrape một dữ liệu. Nếu exporter nhân bản series theo `instance`, cộng tất cả có thể đếm trùng backlog.

### Lag tăng có phải consumer lỗi?

Không nhất thiết. Lag tăng có thể do:

- Upstream đẩy traffic tăng đột biến.
- Consumer throughput thấp hơn producer, cần capacity.
- Một partition có nhiều record hơn phần còn lại.
- Message xử lý lâu vì database chậm.
- Consumer group rebalance liên tục.
- Consumer bị pause hoặc error handler block.
- Metadata của group offset chưa cập nhật/quan sát trễ.

Đọc **ingress rate, processing rate, max partition lag và error rate cùng nhau** thay vì chỉ tăng replica khi thấy lag tăng.

## 23. PromQL: p95/p99 processing duration

Nếu `Timer` trong mục 13 đã được cấu hình `publishPercentileHistogram()` và Prometheus xuất:

```text
app_kafka_listener_processing_seconds_bucket{le="0.1",...}
app_kafka_listener_processing_seconds_count{...}
app_kafka_listener_processing_seconds_sum{...}
```

p95:

```promql
histogram_quantile(
  0.95,
  sum by (le, service, listener) (
    rate(app_kafka_listener_processing_seconds_bucket[5m])
  )
)
```

p99:

```promql
histogram_quantile(
  0.99,
  sum by (le, service, listener) (
    rate(app_kafka_listener_processing_seconds_bucket[5m])
  )
)
```

Nếu hệ thống chỉ xuất `_count` và `_sum` mà **không có buckets**, query `histogram_quantile` sẽ không có dữ liệu. Cần bật histogram qua cấu hình Micrometer hoặc code, và kiểm tra exported metric.

### Vì sao không cộng p95 của từng Pod?

Percentile **không cộng được**. p95 của Pod A cộng p95 của Pod B không phải p95 toàn service. Với classic histogram, gom bucket counts bằng `sum by (le,...)` rồi mới tính quantile. Nếu dùng native histograms hoặc hệ tracing backend khác, cú pháp tổng hợp thay đổi theo datasource.

### Bucket boundaries ảnh hưởng kết quả

Nếu SLA xử lý dưới 5 giây, chọn bucket đủ chi tiết quanh 0,1 s, 0,5 s, 1 s, 2 s, 5 s, 10 s. Histogram có thể dùng nhiều series vì mỗi bucket × label combination là một series; thiết kế histogram phải cân bằng độ chính xác và chi phí lưu trữ.

## 24. PromQL: retry, DLT và thời gian chưa khôi phục

Tổng retries trên 5 phút:

```promql
sum by (service, listener, reason) (
  rate(app_kafka_retry_attempts_total[5m])
)
```

Số DLT publishes thành công trong 15 phút:

```promql
sum by (service, source_topic) (
  increase(app_kafka_dlt_published_total{result="success"}[15m])
)
```

DLT unresolved hiện tại:

```promql
sum by (service, dlt_topic) (
  app_kafka_dlt_unresolved_records
)
```

Oldest unresolved age:

```promql
max by (service, dlt_topic) (
  app_kafka_dlt_oldest_unresolved_age_seconds
)
```

**Cảnh báo về gauge DLT:** ứng dụng phải tự xác định một DLT case là unresolved hay resolved. Nếu không có recovery store, không nên tạo gauge bằng cách đo số Kafka records đang nằm trên DLT topic và gắn nhãn “unresolved”.

### Phát hiện pipeline đứng im

Nếu ứng dụng duy trì gauge `app_kafka_last_business_success_timestamp_seconds` dưới dạng Unix epoch seconds:

```promql
time() - max by (service, flow) (
  app_kafka_last_business_success_timestamp_seconds
)
```

Query trả số giây kể từ lần durable success. Nó hữu ích cho luồng dự kiến hoạt động thường xuyên. Với workload chỉ có message vào ban đêm, không đặt alert “không xử lý trong 10 phút” suốt 24 giờ; so với lịch nhận dữ liệu, input expectation hoặc cửa sổ business schedule.

Nếu series không tồn tại (app chưa xử lý event nào hoặc scrape lỗi), `time() - gauge` không tự hiển thị số giây đúng. Cần quy tắc cho no data và giám sát scrape availability.

## 25. PromQL: event-to-completion SLI ở lớp nghiệp vụ

Ví dụ application đã xuất histogram **từ các event completed**:

```promql
histogram_quantile(
  0.99,
  sum by (le, service, flow) (
    rate(app_kafka_event_to_completion_seconds_bucket[10m])
  )
)
```

Query này cho p99 latency **trên tập đã hoàn tất**, nên không tự nhìn thấy các event đang mắc kẹt chưa có completion. Nếu toàn bộ pipeline ngừng xử lý, histogram có thể không có quan sát mới và p99 không xấu đi, dù người dùng đang chờ.

Muốn đo SLO “99,9% hoàn tất trước 5 phút” thật sự cần:

1. Thống kê eligible events và thời điểm bắt đầu SLA.
2. Theo dõi outcome durable theo unique event ID.
3. Xác định những event đã quá deadline mà chưa completed.
4. Loại trừ/điều chỉnh theo contract được công bố.
5. Tính numerator/denominator trên window đủ tuổi.

Một histogram completion-only có thể hỗ trợ biểu đồ “thời gian của những event đã hoàn tất”, **nhưng không thay thế ledger-based timely completion ratio**.

### Error budget

Nếu SLO 99,9% trong 30 ngày thì allowed bad event ratio là `0,001`. Error budget consumption có thể được tính từ số **bad eligible events** chia cho tổng eligible events trong window, so với `0,001`.

\[
\text{BudgetUsedFraction}
=\frac{\text{BadEligibleEvents}/\text{EligibleEvents}}{0.001}
\]

Nếu `BudgetUsedFraction = 0.4`, đã sử dụng 40% error budget của window. Với volume thấp, cần xử lý số mẫu nhỏ và mức độ quan trọng từng event; không nên dùng phép chia khi denominator bằng 0.

## 26. Thiết kế cảnh báo: từ panel đến hành động

Một panel chỉ giúp người xem nhìn thấy sự cố; alert phải gắn với **hành động có thể thực hiện**. Mỗi alert nên có:

- Mô tả ảnh hưởng người dùng/nghiệp vụ.
- Owner và severity.
- Điều kiện và duration.
- Link dashboard với filter đúng service/group/topic.
- Link runbook.
- Cách phân biệt mất telemetry với sự cố thực tế.
- Điều kiện kết thúc/auto-resolve.

### Alert tiêu biểu

| Alert | Điều kiện gợi ý | Phản ứng đầu tiên |
| --- | --- | --- |
| **Business SLO burn** | Error budget bị tiêu thụ nhanh trên short/long window | Xác định event quá hạn, pause rollout nếu tương quan |
| **Consumer lag sustained** | Lag vượt ngưỡng trong nhiều phút và không giảm | So sánh ingress vs throughput, partition distribution |
| **No processing progress** | Lag dương và success throughput gần 0 | Kiểm tra listener container, errors, rebalance, dependencies |
| **DLT publish failures** | Có failed attempts khi đưa DLT | Ưu tiên vì khả năng lưu lỗi bị ảnh hưởng |
| **DLT unresolved age breach** | Case chưa giải quyết quá deadline | Mở incident/quarantine workflow |
| **Producer error spike** | Send failures tăng với traffic đủ lớn | Kiểm tra auth, broker, serialization, timeout |
| **Transaction fencing** | ProducerFencedException không dự kiến | Kiểm tra transactionIdPrefix theo instance |
| **Broker replication risk** | Under-replicated/offline partitions tồn tại | Chuyển tới Kafka platform team |
| **Telemetry missing** | Scrape target down/no metric | Xác minh app/metrics endpoint trước khi kết luận khỏe |

Không tạo một alert Slack cho mỗi transient retry; việc đó gây alert fatigue. Có thể bắt đầu từ **SLO impact, backlog không phục hồi và lỗi mất khả năng recovery**, rồi dùng các signals khác làm thông tin chẩn đoán.

## 27. Ví dụ alert rules bằng Prometheus

Giả sử đã có custom metric theo mục 9, nhóm rule minh họa:

```yaml
groups:
  - name: spring-kafka-orders-reliability
    rules:
      - alert: KafkaConsumerLagSustained
        expr: |
          sum by (cluster, consumer_group, topic) (
            app_kafka_consumer_group_lag_records
          ) > 10000
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Kafka consumer lag sustained"
          description: "Review ingress, processing rate and partition skew."

      - alert: KafkaDltPublishFailure
        expr: |
          sum by (service, source_topic) (
            increase(app_kafka_dlt_published_total{result="failure"}[10m])
          ) > 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Failed record could not be published to DLT"

      - alert: KafkaBusinessNoProgress
        expr: |
          time() - max by (service, flow) (
            app_kafka_last_business_success_timestamp_seconds
          ) > 600
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "No durable business completion in 10 minutes"
```

**Chưa phải production-ready alerts**: ngưỡng 10.000 records, 10 phút và 15 phút chỉ để minh họa. Phải hiệu chỉnh theo giờ cao điểm, thời hạn xử lý, tốc độ nguồn, số partitions và mức độ nghiêm trọng.

Rule `KafkaBusinessNoProgress` không phù hợp nếu dòng sự kiện vốn chỉ chạy theo lịch thưa hoặc dừng có chủ đích. Trong production nên kết hợp expected input/schedule và no-data alert. Với DLT publish failure, cần xác nhận metric được tăng tại đúng **lần publish thất bại**; không tăng nó cho việc handler fail trước khi thử publish.

### Severity theo tác động

- **Critical:** có business events quá deadline, DLT không thể lưu lỗi, broker có phân vùng offline ảnh hưởng dữ liệu hoặc transaction pipeline mất khả năng commit.
- **Warning:** backlog tăng nhưng còn trong error budget, retry tăng, DLT có record cần xử lý, imbalance xuất hiện.
- **Info:** một deploy, rebalance đơn lẻ hoặc spike ngắn chưa ảnh hưởng mục tiêu.

Đặt severity theo *impact + urgency*, không chỉ theo giá trị CPU hoặc độ lớn của một counter.

## 28. Phân biệt hiệu ứng của retry với dữ liệu trùng

Spring Kafka có thể gọi listener nhiều lần trên cùng record sau exception/rollback. Kafka transactions giúp atomicity của một số Kafka-to-Kafka flows nhưng **không ngăn mọi side effect lặp ở database/API**.

Ví dụ:

```text
Consumer đọc order.created event E-1001
  -> call billing API thành công
  -> consumer transaction rollback trước commit offset
Consumer đọc lại E-1001
  -> call billing API một lần nữa
```

Metric “listener attempts” tăng hai lần nhưng business event E-1001 phải được tính một lần nếu idempotency hoạt động.

Dashboard nên bổ sung:

```text
app_kafka_idempotency_conflicts_total
app_kafka_duplicate_events_suppressed_total
app_kafka_business_events_total{outcome="completed"}
app_kafka_business_events_total{outcome="rejected"}
```

Đây là metric do ứng dụng thiết kế. **Không lấy duplicate-suppressed lớn tự động làm lỗi:** nếu producer retry hoặc upstream gửi lặp được contract cho phép, số suppression có thể bình thường. Điều đáng lo là duplicate business effects hoặc unique completion bị sai.

## 29. Runbook: lag tăng liên tục

### Triệu chứng

```text
consumer_group=order-processors
lag total: 2.000 -> 10.000 -> 40.000
incoming rate: 1.500/s
processing success: 700/s
listener error rate: 0.1%
```

Đây là số liệu giả định để minh họa.

### Chẩn đoán

1. Kiểm tra input rate tăng hay processing rate giảm trước.
2. Xem max partition lag: có một partition “hot” hay cả nhóm cùng chậm?
3. Xem listener p95/p99 duration; nếu tăng, kiểm tra dependency, DB pool, API rate limit.
4. Xem consumer assignment và rebalance; có churn hoặc nhiều consumer idle?
5. Xem CPU/heap/GC và số thread concurrency.
6. Xem broker fetch latency, under-replicated partitions và network.
7. Kiểm tra deploy/traffic event mới nhất.

### Hành động

- Nếu traffic spike hợp lệ và consumer healthy: cân nhắc scale **trong giới hạn số partition** và capacity downstream.
- Nếu một partition hot: tăng replica có thể **không giúp partition đó**; cần xem key distribution và partition strategy.
- Nếu processing chậm vì DB: sửa query/index/connection pool hoặc giảm overload; tăng consumers có thể làm DB càng quá tải.
- Nếu rebalances liên tục: điều tra poll interval, listener duration và group membership.
- Nếu có poison pill: xử lý retry policy/DLT, không mở skip mọi exception để ép lag về 0.

Đừng dùng offset seek-to-end để “khắc phục lag” nếu không có quyết định rõ về việc bỏ dữ liệu; đó có thể là mất dữ liệu nghiệp vụ.

## 30. Runbook: lag gần 0 nhưng đơn hàng vẫn chậm

### Triệu chứng

```text
consumer lag: gần 0
listener success: cao
business completion: giảm
end-to-end p99: 12 phút (SLO 5 phút)
```

Khả năng:

- Listener chỉ đẩy event vào queue nội bộ, nhưng worker downstream bị kẹt.
- Database đã nhận request nhưng transaction commit lâu.
- Outbox publisher không theo kịp sau khi listener hoàn tất.
- Logic retry ngoài Kafka đang chờ.
- Metric listener success chỉ đếm handler return, không đo durable business completion.

Hành động:

1. Xem pipeline sau listener: DB/outbox/external API.
2. Kiểm tra trạng thái event trong business ledger, không chỉ offsets.
3. Đo thời gian từng stage để tìm bottleneck.
4. Đối chiếu event ID với outcome cuối.

Đây là lý do dashboard phải có business SLA và không dựa hoàn toàn vào consumer lag.

## 31. Runbook: retry và DLT tăng sau deploy

### Triệu chứng

```text
Deployment v42 -> v43
handler errors tăng
retry attempts tăng
DLT published tăng
lag dao động
```

Kiểm tra:

- Payload/schema/header compatibility giữa producer cũ và consumer mới.
- Có đổi serializer/deserializer, error handler hoặc trusted packages?
- Có thay topic, key, partition, timeout hoặc transaction boundary?
- Có nhiều event cùng mã lỗi validation hay timeout?
- Có record được retry vô hạn thay vì DLT?
- Có DLT record được publish nhưng không còn đủ origin headers để điều tra?

Hành động:

1. Đối chiếu annotation thời điểm deploy với thời điểm thay đổi metric.
2. Xác định nhóm lỗi bằng exception class/category **hữu hạn**.
3. Nếu lỗi do version mới, cân nhắc rollback/canary halt theo change policy.
4. Giữ lại DLT/quarantine để sửa và re-drive; không xóa dữ liệu lỗi.
5. Sau khắc phục, xác minh unresolved backlog giảm và unique business outcomes chính xác.

Không coi “DLT publish thành công” là sự cố đã được giải quyết. Nó chỉ chứng minh sự kiện lỗi đã được lưu để xử lý tiếp.

## 32. Runbook: transaction abort hoặc ProducerFencedException

Với Kafka-to-Kafka transactional processing:

```text
transaction abort spike
producer fenced exceptions
consumer retry / listener restarts
throughput decrease
```

Các nguyên nhân cần phân biệt:

- Nhiều replicas/factories dùng cùng `transactionIdPrefix` dẫn đến trùng `transactional.id`.
- Stable producer identity bị thay thế có chủ đích; fencing là hành vi bảo vệ.
- Producer idle/transactional ID expiration, producer cache lifecycle.
- Transaction timeout hoặc broker/coordinator unavailable.
- Listener xử lý quá lâu khiến poll/rebalance và transaction fail.

Dashboard cần link tới:

- Logs có `instanceId`, `transactionIdPrefix`, exception class và deployment version.
- Kafka client producer/transaction metrics.
- Listener rebalance/commit/abort signals.
- Dữ liệu nghiệp vụ để xác minh duplicate prevention.

Đừng tắt transactions để xóa lỗi mà chưa đánh giá ảnh hưởng exactly-once semantics. Fencing có thể đang bảo vệ dữ liệu.

## 33. Capacity planning và partition skew

Một consumer group có 24 partitions không thể xử lý song song bằng 100 consumer **trong cùng group** trên cùng topic theo cách mỗi consumer sở hữu một partition riêng; nhiều consumer sẽ idle. Tối đa concurrency hữu ích bị ràng buộc bởi số partitions và topology, đồng thời hiệu năng thực tế còn phụ thuộc I/O và downstream.

Dashboard capacity nên có:

```text
partition count
assigned partitions per active consumer
max partition lag / median lag
processing records per second per consumer
listener processing p95 and p99
CPU, heap, GC, DB connection pool utilization
downstream requests/sec and error rate
```

### Khi tăng replica có ích

- Có nhiều partitions chưa được khai thác đủ.
- Bottleneck nằm ở CPU hoặc listener instance, không phải DB/API chung.
- Key distribution không quá lệch.
- Rebalance overhead và startup time chấp nhận được.

### Khi tăng replica không ích

- Một partition hot chứa phần lớn traffic.
- DB pool/third-party API đã quá tải.
- Error handler đang tạm dừng/pause nhiều partitions.
- Producer throughput bị giới hạn bởi broker.
- Business work bị khóa tuần tự theo cùng order key.

Một biểu đồ “lag total” đi kèm “max partition lag” và “throughput per consumer” giúp tránh quyết định scale sai.

## 34. Cardinality và chi phí lưu trữ metric

Prometheus lưu một time series cho mỗi **kết hợp label**. Với:

```text
service=10
topic=50
consumer_group=20
partition=24
instance=100
```

Nếu phát metric có mọi chiều cùng lúc, số series lý thuyết có thể lên tới:

\[
10 \times 50 \times 20 \times 24 \times 100 = 24{,}000{,}000
\]

Ví dụ này minh họa **tích các cardinality tối đa**, không có nghĩa mọi tổ hợp thực sự tồn tại. Nhưng nó cho thấy vì sao không thêm nhãn bừa bãi.

### Nhãn nên/không nên dùng

| Dữ liệu | Metric label? | Lý do |
| --- | --- | --- |
| `service`, `environment`, `cluster` | Có, tập hữu hạn | Lọc và phân trách nhiệm |
| `listenerId`, `topic`, `consumer_group` | Có khi cardinality được kiểm soát | Phân tích flow |
| `partition` | Chỉ khi cần drill-down và exporter phù hợp | Có thể tạo nhiều series |
| `result`, `errorCategory` | Có, enum hữu hạn | Tỷ lệ kết quả |
| `exceptionClass` | Cân nhắc nhóm chuẩn, không để dynamic arbitrary | Có thể gây cardinality cao |
| `orderId`, `eventId`, `correlationId` | Không | Gần như unique mỗi event |
| `offset`, `message timestamp` | Không | Thay đổi theo mỗi record |
| Full exception message / stacktrace | Không | Vô hạn và có thể chứa secrets |
| Dynamic retry topic name do UUID | Không nếu có thể tạo vô hạn | Hỏng cardinality budget |

Trong log và trace có thể lưu event IDs khi cần điều tra, nhưng phải áp dụng retention, privacy policy và kiểm soát truy cập phù hợp.

## 35. Thiết kế ownership và tài liệu metric

Mỗi metric/panel cần có contract:

```yaml
metric: app_kafka_listener_records_total
owner: orders-processing
type: counter
unit: attempts
source: Spring Kafka listener application code
labels:
  - service
  - listener
  - result
semantics:
  success: handler returned without RuntimeException
  failure: handler threw RuntimeException
limitations:
  - retries produce multiple attempts
  - does not guarantee offset commit
  - does not represent unique business completion
dashboard_panel: "Listener attempt throughput"
```

Đây là một **ví dụ tài liệu metric**, không phải cấu hình Micrometer được đọc tự động. Khi nhóm thay code retry hoặc chuyển sang non-blocking retries, tài liệu semantics phải được cập nhật cùng dashboard.

Sử dụng ownership rõ ràng:

- Application team sở hữu handler business metrics, DLT recovery metrics và runbook.
- Kafka platform team sở hữu broker JMX, cluster alerts, partition/replication health.
- SRE/observability team sở hữu Prometheus/Grafana availability, retention, label budget và alert routing.
- Data/business owner định nghĩa SLO, phạm vi event eligible và tiêu chí hoàn tất.

## 36. Kiểm thử dashboard trước khi go-live

Một dashboard chỉ hoạt động trên dữ liệu “happy path” chưa đủ tin cậy. Cần thực hành với các tình huống giả lập.

| Tình huống | Signal kỳ vọng | Dashboard/runbook cần làm gì |
| --- | --- | --- |
| Producer gửi nhanh gấp đôi | Ingress tăng, lag có thể tăng | Thấy rõ năng lực consumer hiện tại |
| Consumer tắt 5 phút | Success throughput về 0, group lag tăng | Alert no progress khi nguồn đang có traffic |
| Một partition hot | Max partition lag tăng mạnh so với các partition khác | Drill-down partition/key distribution |
| DB chậm | Listener p95/p99 tăng, throughput giảm | Link tới DB dashboard |
| Payload invalid | Processing errors, retries/DLT tăng | Nhóm error category đúng |
| DLT producer bị permission denied | DLT publish failures | Alert critical, không đánh đồng với DLT publish success |
| DLT record được re-drive thành công | Unresolved backlog/age giảm | Re-drive outcome và audit khớp |
| Kafka producer transaction fenced | Abort/fence errors | Correlate instance prefix và rollout |
| Consumer group rebalance liên tục | Rebalance count tăng, throughput dao động | Điều tra poll interval/membership |
| Application Pod restart | Counter reset, scrape target thay | `rate` không tạo spike sai |
| Metrics endpoint không scrape được | `up=0` hoặc series biến mất | No-data alert, không hiện 0 như khỏe |
| Business completion ngừng nhưng listener vẫn return | Business SLO xấu, handler success bình thường | Phát hiện được downstream bị kẹt |
| Message retry nhiều lần | Attempt counter > unique event count | SLO không đếm unique event sai |
| Thay header/schema khi rolling upgrade | Conversion/DLT error tăng | Canary/rollback theo runbook |

### Kịch bản kiểm thử tự động

Với Testcontainers Kafka hoặc `@EmbeddedKafka` (theo phiên bản tương thích), tạo producer/consumer test:

1. Gửi N record có `eventId` duy nhất.
2. Cho một số record throw exception trong listener.
3. Cấu hình retry policy rồi DLT sau khi hết attempts.
4. Đợi trạng thái xử lý hội tụ, kiểm tra metric attempt counts khác unique completed counts.
5. Đọc Prometheus exposition hoặc `MeterRegistry` trong test để assert metric đã phát sinh.
6. Chạy re-drive và kiểm tra unresolved DLT age/count giảm.

Để test alert rules, dùng `promtool test rules` với input series đã thiết kế; đây là việc của bước QA/triển khai thực tế sau khi tài liệu được áp dụng, không phải yêu cầu chạy build ngay khi soạn bài.

## 37. Mẫu kiểm thử Micrometer bằng SimpleMeterRegistry

Logic ghi metric có thể unit test mà không chạy Kafka broker:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class OrderListenerMetricsTest {

    @Test
    void recordsOneSuccessAndOneFailureAttempt() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            OrderListenerMetrics metrics =
                    new OrderListenerMetrics(registry);

            metrics.recordSuccess(Duration.ofMillis(50));
            metrics.recordFailure(Duration.ofMillis(100));

            double successes = registry
                    .get("app.kafka.listener.records")
                    .tag("listener", "orderCreated")
                    .tag("result", "success")
                    .counter().count();

            double failures = registry
                    .get("app.kafka.listener.records")
                    .tag("listener", "orderCreated")
                    .tag("result", "failure")
                    .counter().count();

            long durationCount = registry
                    .get("app.kafka.listener.processing")
                    .tag("listener", "orderCreated")
                    .timer().count();

            assertEquals(1.0, successes);
            assertEquals(1.0, failures);
            assertEquals(2, durationCount);
        }
    }
}
```

Test này xác minh **instrumentation**, không chứng minh Kafka record đã được commit hoặc Prometheus đã scrape thành công. Với end-to-end reliability, cần thêm integration tests có broker, database và logic event IDs.

## 38. Từ dashboard đến quy trình trực ca

Một dashboard vận hành chỉ có giá trị khi dẫn đến hành động:

```text
ALERT
  |
  v
Open dashboard filtered to service + group + topic
  |
  v
Check business SLO and active impact
  |
  +-- no traffic expected? -> verify schedule / upstream
  |
  +-- lag growing? -> inspect processing rate and partition skew
  |
  +-- processing failing? -> inspect error categories + retry/DLT
  |
  +-- broker/client failing? -> inspect infrastructure
  |
  v
Follow runbook and apply bounded mitigation
  |
  v
Verify recovery:
    lag decreases
    completion rate recovers
    oldest unresolved age decreases
    error budget burn stabilizes
    no duplicate business effects
  |
  v
Document incident and improve thresholds/tests
```

Không đóng incident chỉ vì lag về 0 nếu DLT backlog, dữ liệu mất hoặc business completion SLA vẫn chưa phục hồi. Ngược lại, có thể một lag spike ngắn không cần incident nếu hệ thống nhanh chóng bắt kịp và không vi phạm deadline.

## 39. Bài thực hành xây dashboard reliability

**Bài 1 — Chọn SLO.** Với luồng `orders.created`, định nghĩa “eligible”, “durable completion”, deadline 5 phút và cửa sổ 30 ngày. Giải thích vì sao listener success rate không bằng timely completion SLI.

**Bài 2 — Inventory metric.** Chạy Spring Boot Actuator Prometheus trong môi trường test, liệt kê metric thực từ Spring Kafka listener/template và Kafka client. So sánh với contract custom ở mục 9, ghi rõ nguồn và đơn vị.

**Bài 3 — Consumer lag.** Đưa một topic bốn partitions vào dashboard, vẽ total lag và max partition lag. Tạo partition hot để xem vì sao hai biểu đồ cần đứng cạnh nhau.

**Bài 4 — Throughput.** Tạo panel records/second cho producer và consumer. Gây traffic spike, xem backlog tăng và xác định throughput tại điểm cân bằng.

**Bài 5 — Processing latency.** Bật histogram của Micrometer Timer, vẽ p95/p99. Thêm độ trễ ngẫu nhiên ở database call và quan sát tác động.

**Bài 6 — Business freshness.** Ghi `acceptedAt` trong event và `completedAt` trong ledger. Đo event-to-completion latency, so sánh với listener duration và thiết kế metric oldest unresolved event.

**Bài 7 — Retry/DLT.** Gây một lỗi transient và một lỗi permanent. Thiết kế panel phân biệt retry attempts, DLT published, unresolved DLT và DLT publish failure.

**Bài 8 — Alert no progress.** Chạy consumer với input liên tục rồi dừng listener. Tạo rule lag dương + processing progress thấp; kiểm tra hành vi khi upstream ngừng gửi vì lịch.

**Bài 9 — Broker infrastructure.** Kết nối dashboard nhóm ứng dụng với broker health/replication dashboard. Ghi rõ khi nào phải chuyển incident sang Kafka platform team.

**Bài 10 — Transaction fencing.** Chạy hai instance Spring Kafka có collision `transactionIdPrefix` trong môi trường test. Quan sát producer fenced, transaction abort và consumer progress; sửa prefix rồi xem hệ thống hồi phục.

**Bài 11 — Metric cardinality.** Thử gắn event ID vào label trong môi trường test cô lập, quan sát series tăng. Sau đó chuyển ID vào log/tracing và giữ metric labels hữu hạn.

**Bài 12 — Canary deployment.** Thực hiện một thay đổi handler/schema có kiểm soát. Annotation version lên dashboard, thiết lập rollback threshold dựa trên SLO và error/DLT rate.

**Bài 13 — DLT re-drive.** Xây một bảng trạng thái DLT case với source event ID, status và timestamps. Dashboard hiển thị unresolved count, oldest age; sau re-drive thành công, kiểm tra các gauge giảm.

**Bài 14 — Alert testing.** Viết test cho Prometheus recording/alert rules bằng chuỗi time series mô phỏng lag tăng, metric biến mất và DLT failures. Xác minh alert không spam khi không có traffic theo lịch.

**Bài 15 — Incident drill.** Giả lập “consumer lag thấp nhưng business completion ngừng”. Ghi lại các bước tra cứu xuyên listener, outbox/DB và ledger đến khi tìm ra stage mắc kẹt.

## 40. Checklist bàn giao dashboard

Trước khi coi dashboard đủ điều kiện trực vận hành, cần trả lời được:

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| SLI/SLO đã định nghĩa cùng business owner? | Document nêu denominator, deadline và exclusions |
| Dashboard có đúng environment/cluster không? | Filter và metric labels được kiểm soát |
| Có thể biết listener còn xử lý không? | Throughput, last success, lag và scrape status |
| Có phân biệt lag theo committed offset với fetch lag? | Tài liệu datasource lag exporter |
| Có biết DLT record đã được giải quyết chưa? | Recovery/audit state, không chỉ Kafka topic size |
| Histogram có buckets phù hợp? | Prometheus exposition và p95/p99 panels |
| Error/attempt counts có bị đếm như unique events? | Metric contract rõ ràng |
| Alert có owner và runbook? | Link/categorization trong alert annotations |
| Hệ thống có no-data alert? | Scrape up/absent test |
| Dashboard được kiểm thử khi failure? | Failure injection results và incident drill |
| Migrations có kiểm tra metric name/label? | Version-aware compatibility tests |
| Có tránh nhãn cardinality cao và secrets? | Metric labels inventory/retention policy |

Đây là checklist để nhóm áp dụng trong quy trình thực tế; trong bước soạn tài liệu STEP 4, không có yêu cầu chạy hệ thống Kafka, Prometheus, Gradle hay đánh giá nội dung bài.

## 41. Kết luận

Dashboard reliability cho Spring Kafka phải trả lời **dữ liệu có đến đích đúng thời hạn và có thể phục hồi an toàn hay không**, thay vì chỉ hiển thị Kafka cluster đang hoạt động.

Thiết kế hiệu quả cần kết hợp:

- **Business SLO/SLI** dựa trên event ID và durable outcome rõ ràng.
- **Producer/consumer telemetry** để biết traffic, progress, errors, transaction và rebalance.
- **Lag + freshness + latency** với đúng semantics, không biến “records behind” thành “seconds late” tùy tiện.
- **Retry/DLT/recovery metrics** để biết việc sửa dữ liệu lỗi đã hoàn tất hay chỉ mới lưu vào DLT.
- **Broker và downstream health** để tìm đúng tầng bottleneck.
- **PromQL, Grafana, alerts, runbooks và failure tests** để biến số liệu thành hành động vận hành.

Khi kết hợp được các tầng đó, dashboard không chỉ cho biết một consumer đang chậm, mà còn giúp trả lời **ai bị ảnh hưởng, từ lúc nào, có còn error budget không, cần sửa chỗ nào và làm sao biết sự cố đã thực sự phục hồi**.

### Tài liệu tham khảo

- [Spring Kafka Reference — Micrometer Observations and Metrics](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka Reference — Non-blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html)
- [Spring Kafka Reference — Kafka Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Boot Reference — Metrics and Actuator](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Apache Kafka — Monitoring](https://kafka.apache.org/documentation/#monitoring)
- [Grafana — Dashboard Best Practices](https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/best-practices/)
