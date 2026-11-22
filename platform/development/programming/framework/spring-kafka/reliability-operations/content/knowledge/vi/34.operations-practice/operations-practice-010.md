# Thiết lập metric và alert cho Spring Kafka Reliability Operations

## 1. Mục tiêu thực hành

Một ứng dụng Spring Kafka có thể có Pod `Ready`, HTTP health `UP` và không ném exception khi khởi động, nhưng vẫn đang **ngừng xử lý record**. Những tình huống phổ biến gồm consumer group lag tăng, một partition bị kẹt bởi poison message, producer future thất bại, retry liên tục, DLT tích tụ, hoặc database downstream chậm.

Vì vậy, **thiết lập metric và alert** không có nghĩa chỉ mở `/actuator/prometheus`. Cần theo dõi các tín hiệu ở nhiều lớp, xác định đúng đơn vị đo, thiết kế cảnh báo có ngưỡng và thời gian xác nhận hợp lý, rồi gắn mỗi cảnh báo với một hướng xử lý cụ thể.

Trong phần **Thực hành vận hành** của *Spring Kafka Reliability Operations*, chúng ta sẽ:

1. Phân biệt broker, consumer-group, client, listener và business metrics.
2. Bật Spring Boot Actuator, Micrometer, Prometheus endpoint.
3. Thêm custom counters cho listener và KafkaTemplate.
4. Đo consumer group lag đúng nguồn, không nhầm với một client metric cục bộ.
5. Viết các truy vấn PromQL phục vụ dashboard.
6. Cấu hình alert rule, thời gian `for` và Alertmanager routing.
7. Phân biệt **zero** với **missing telemetry**.
8. Kiểm thử counters và alert bằng fault injection.
9. Bảo vệ metrics endpoint và tránh label chứa secret, PII, event ID.
10. Sử dụng runbook khi lag, DLT, send failure hoặc rebalance tăng.

Ví dụ giả định **Java 17+, Spring Boot 3.x, Spring Kafka 3.x**, Kafka broker tương thích, Micrometer và Prometheus. Metric name và label từ exporter có thể khác giữa các phiên bản; phần dưới sẽ ghi rõ tên nào do ứng dụng tạo và tên nào cần xác minh từ nền tảng monitoring.

## 2. Sơ đồ kiến trúc observability

~~~text
                     Kafka cluster
                 broker / topic / group
                        |       |
                Broker JMX   Kafka exporter
                        |       | consumer group lag
                        v       v
                       Prometheus
                           ^
                           | scrape
                      /actuator/prometheus
                           |
                  Spring Kafka service
                  /                 \
           Kafka consumer       Kafka producer
             |      |               |
          listener  client       KafkaTemplate
             |    metrics           |
             v                      v
          business DB          send future ACK
             |
       Micrometer counters
                           |
                           v
                  Prometheus rules
                     |         |
                     v         v
                  Grafana   Alertmanager
                               |
                               v
                         On-call + runbook
~~~

| Tầng | Tín hiệu | Nguồn điển hình |
| --- | --- | --- |
| Broker/cluster | Broker availability, request latency, ISR/replication, disk, controller | Kafka JMX exporter hoặc managed Kafka monitoring. |
| Consumer group | Committed offset, log-end offset, lag theo topic/partition | Kafka exporter, Burrow hoặc dịch vụ tương đương. |
| Kafka client | Consumer fetch/poll, rebalance, producer request/retry/error | Native Kafka client metrics qua Micrometer/JMX binder. |
| Spring Kafka container | Listener duration, lỗi listener, consumer events, retry/DLT policy | Spring Kafka Micrometer/Observation và instrumentation riêng. |
| Business service | Thực thi thành công, sai dữ liệu, idempotency, downstream delay | Counter/Timer ứng dụng, audit database. |
| Telemetry | Scrape target up/down, series missing, rule evaluation | Prometheus. |

Một metric không thể thay thế mọi lớp:

- Lag bằng 0 **không chứng minh** producer gửi đủ event.
- Listener success tăng **không chứng minh** offset đã commit hoặc business side effect exactly-once.
- HTTP health `UP` **không chứng minh** consumer có partition assignment.
- Producer request retry nhiều lần **không đồng nghĩa** nhiều business events đã được phát.
- Không có series lỗi **không đồng nghĩa** số lỗi bằng 0.

## 3. Chọn SLI và alert theo nghiệp vụ

SLI (Service Level Indicator) phải được định nghĩa trước khi chọn ngưỡng:

| SLI | Phương pháp | Ví dụ cách hiểu |
| --- | --- | --- |
| Consumer lag | Log-end offset trừ committed group offset | Số record group còn cách đầu cuối log. |
| Processing delay | Timestamp nguồn đến business completion | Một event mất bao lâu mới được xử lý. |
| Consumer error ratio | Error listener attempts trên tổng attempts | Tỷ lệ lần gọi listener bị lỗi. |
| Producer send failure | Số send futures lỗi và tốc độ lỗi | Client không nhận được kết quả gửi theo cấu hình ACK. |
| DLT rate | Số record thực sự publish vào DLT | Số record cần triage/repair. |
| Processing throughput | Success attempts hoặc committed business ops/s | Mức độ tiêu thụ đang đạt. |
| Availability | Scrape target và group membership | Có tín hiệu và consumer hoạt động. |
| Data correctness | Audit, checksum, idempotency | Kết quả nghiệp vụ có đúng không. |

Với topic realtime, backlog 5 phút có thể vi phạm SLA; với batch topic chạy mỗi đêm, cùng lag trong vài phút có thể bình thường. Do đó **ngưỡng 1.000 hay 5.000 records trong bài chỉ là dữ liệu minh họa**, không phải chuẩn vận hành cố định.

Cần hỏi: producer có phát liên tục hay theo lịch, số partition, throughput trung bình/đỉnh, retention, group có downstream chậm không, message nào phải được xử lý trước hạn và điều gì đủ nghiêm trọng để page người trực.

## 4. Bật Actuator, Micrometer và Prometheus

### 4.1. Dependencies

Ví dụ `build.gradle` trong dự án Spring Boot 3.x quản lý version:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:kafka'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`starter-web` cho demo chạy HTTP server để Prometheus scrape. Nếu dùng WebFlux, management port riêng hoặc một app không có HTTP endpoint, cần chọn triển khai Actuator/exporter phù hợp. Không cần phơi cổng quản trị ra Internet.

### 4.2. Cấu hình mẫu

File `application.yml`:

~~~yaml
spring:
  application:
    name: orders-worker
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP}
      enable-auto-commit: false
      auto-offset-reset: ${KAFKA_AUTO_OFFSET_RESET:none}
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      properties:
        max.poll.records: ${KAFKA_MAX_POLL_RECORDS:100}
        max.poll.interval.ms: ${KAFKA_MAX_POLL_INTERVAL_MS:300000}
    listener:
      ack-mode: record
      concurrency: ${KAFKA_LISTENER_CONCURRENCY:2}
    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      properties:
        enable.idempotence: true

app:
  kafka:
    input-topic: ${KAFKA_INPUT_TOPIC}
    output-topic: ${KAFKA_OUTPUT_TOPIC}

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: ${spring.application.name}
~~~

Ý nghĩa quan trọng:

- `enable-auto-commit=false`: để Spring Kafka container kiểm soát offset commits theo acknowledgment strategy.
- `ack-mode=record`: container xử lý acknowledgment sau khi record listener thành công theo semantics của container/error handler. **Không tạo transaction ACID giữa Kafka và database.**
- `auto-offset-reset=none`: ở ví dụ fail nếu group không có committed offset hợp lệ; ứng dụng khác có thể dùng `earliest` hoặc `latest` theo hợp đồng nghiệp vụ.
- `concurrency=2`: tạo consumer threads theo container config, không vượt số partition được gán thực tế.
- `acks=all`, `enable.idempotence=true`: tăng độ an toàn gửi Kafka theo điều kiện broker/client; không bảo đảm side effect ngoài Kafka exactly-once.

Đối với production, externalize broker/group/topic và SASL/TLS config qua environment hoặc secret manager. Không đưa raw secret vào ConfigMap hoặc metric labels.

### 4.3. Truy vấn endpoint trong local

~~~bash
curl http://localhost:8080/actuator/health
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/prometheus
~~~

`/actuator/metrics` có thể giúp xác định meter name và available tags. `/actuator/prometheus` trả về exposition format Prometheus để scrape.

**Không có nghĩa mọi Kafka metric luôn xuất hiện từ lúc startup.** Nhiều meter chỉ được đăng ký khi client/producer/consumer tạo thành công hoặc sự kiện đầu tiên diễn ra. Với Spring Kafka 3.x, cơ chế Micrometer legacy timers và Micrometer Observation còn phụ thuộc cấu hình/version.

## 5. Phân biệt metric built-in và metric ứng dụng

### 5.1. JVM/process/HTTP metrics

Spring Boot Actuator thường hỗ trợ những meter như:

~~~text
jvm.memory.used
jvm.gc.pause
process.cpu.usage
system.cpu.usage
http.server.requests
~~~

Ở Prometheus, tên được đổi theo convention và loại meter, ví dụ `jvm_memory_used_bytes`. Đây là số liệu capacity của app, không phải bằng chứng event đã được xử lý.

### 5.2. Kafka client metrics

Kafka Java client có những metric theo client ID và nhóm nội bộ như `records-consumed-rate`, `records-lag-max`, `record-send-rate`, `record-error-rate`, `record-retry-rate`, `request-latency-avg`.

**Các tên trên không phải bảo đảm là tên Prometheus series.** Client JMX, Kafka metrics binder, Spring Kafka observation và exporter có thể map tên/labels khác nhau. Kiểm endpoint thực tế trên phiên bản đang chạy trước khi viết dashboard.

### 5.3. Spring Kafka listener/template metrics

Spring Kafka có Micrometer timers và hỗ trợ Observation. Các meter như `spring.kafka.listener` hoặc `spring.kafka.template` có thể xuất hiện khi instrumentation tương ứng được bật. Đừng mặc định rằng bật Observation và Micrometer legacy timer sẽ tạo hai luồng số liệu cần cộng lại.

### 5.4. Custom metrics của bài

Chúng ta sẽ tạo:

| Meter name | Type | Khi tăng | Prometheus name thường thấy |
| --- | --- | --- | --- |
| `app.kafka.consume.records` | Counter | Mỗi lần listener callback hoàn tất theo outcome | `app_kafka_consume_records_total` |
| `app.kafka.produce.results` | Counter | KafkaTemplate future success/failure | `app_kafka_produce_results_total` |

Hai meter này là **do code tạo**, không phải Kafka/Spring Kafka cung cấp sẵn. Tên sau khi export có thể phụ thuộc registry naming convention.

## 6. Listener instrument processing attempts

Giả sử topic chứa OrderEvent JSON:

~~~java
package com.example.kafka;

public record OrderEvent(
        String eventId,
        String orderId,
        long amount) {
}
~~~

Service nghiệp vụ:

~~~java
package com.example.kafka;

public interface OrderService {
    // Implementation phải xử lý idempotent theo event ID.
    void apply(OrderEvent event);
}
~~~

Listener:

~~~java
package com.example.kafka;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersListener {

    private final ObjectMapper mapper;
    private final OrderService service;
    private final Counter success;
    private final Counter error;

    public OrdersListener(
            ObjectMapper mapper,
            OrderService service,
            MeterRegistry registry) {
        this.mapper = mapper;
        this.service = service;

        this.success = Counter.builder("app.kafka.consume.records")
                .description("Observed listener attempts")
                .tag("listener", "orders")
                .tag("outcome", "success")
                .register(registry);

        this.error = Counter.builder("app.kafka.consume.records")
                .description("Observed listener attempts")
                .tag("listener", "orders")
                .tag("outcome", "error")
                .register(registry);
    }

    @KafkaListener(
        id = "orders-listener",
        topics = "${app.kafka.input-topic}",
        groupId = "${spring.kafka.consumer.group-id}")
    public void onMessage(ConsumerRecord<String, String> record)
            throws Exception {
        try {
            OrderEvent event =
                mapper.readValue(record.value(), OrderEvent.class);

            if (event.eventId() == null || event.eventId().isBlank()) {
                throw new IllegalArgumentException("Missing event ID");
            }

            service.apply(event);
            success.increment();
        } catch (Exception failure) {
            error.increment();
            // Error handler quyết định retry/DLT. Không swallow lỗi.
            throw failure;
        }
    }
}
~~~

**Đơn vị đếm:** số lần listener callback đã được code quan sát; **không phải số business events unique**.

Ví dụ một record fail hai lần rồi thành công:

~~~text
attempt 1 -> error +1
attempt 2 -> error +1
attempt 3 -> success +1
```

Vì vậy `error=2`, `success=1` không nghĩa có 3 event độc lập. Khi listener thành công, Kafka offset commit vẫn còn bước riêng của container. Nếu database commit xong nhưng process chết trước offset commit, message có thể được giao lại.

Để bảo đảm không có side effect trùng, cần **idempotency key ổn định theo business event**, transaction boundary hoặc outbox, không dựa vào Counter.

Không log raw `record.value()` hoặc full exception message nếu payload có dữ liệu nhạy cảm. Topic/partition/offset có thể dùng trong log điều tra phù hợp retention, nhưng không dùng event ID hay offset làm metric tag.

## 7. Producer metric theo kết quả send future

Một lỗi vận hành phổ biến là gọi `KafkaTemplate.send()` rồi đánh dấu producer success ngay lập tức. Lời gọi trả về `CompletableFuture`, còn broker ACK/failure có thể đến sau.

~~~java
package com.example.kafka;

import java.util.concurrent.CompletableFuture;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Component;

@Component
public class OrderPublisher {

    private final KafkaTemplate<String, String> template;
    private final Counter acknowledged;
    private final Counter failed;

    public OrderPublisher(
            KafkaTemplate<String, String> template,
            MeterRegistry registry) {
        this.template = template;

        this.acknowledged = Counter.builder(
                "app.kafka.produce.results")
                .tag("channel", "orders")
                .tag("outcome", "acknowledged")
                .register(registry);

        this.failed = Counter.builder(
                "app.kafka.produce.results")
                .tag("channel", "orders")
                .tag("outcome", "error")
                .register(registry);
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String topic, String key, String payload) {

        CompletableFuture<SendResult<String, String>> future =
                template.send(topic, key, payload);

        future.whenComplete((result, exception) -> {
            if (exception == null) {
                acknowledged.increment();
            } else {
                failed.increment();
            }
        });

        return future;
    }
}
~~~

Counter `acknowledged` biểu thị future send đã hoàn tất thành công theo cấu hình Kafka client (ví dụ `acks=all`), **không phải event đã được consumer downstream xử lý**. Callback vẫn có thể chưa chạy trước khi JVM crash.

Caller cần xử lý returned future/error theo hợp đồng publish; việc ghi metric không tự tạo retry bền vững. Nếu ứng dụng commit database rồi mới gửi Kafka, nên đánh giá transactional outbox thay vì chỉ retry trong bộ nhớ.

## 8. Consumer group lag lấy từ đâu?

Lag của group được tính từ broker log-end offset và offset group đã commit:

~~~text
topic-partition log-end offset
          -
consumer-group committed offset
          =
group lag tại thời điểm quan sát
~~~

Native client metric `records-lag-max` thường thể hiện một phạm vi consumer cục bộ, **không thay thế báo cáo committed lag của group toàn cluster**.

Ví dụ một Kafka exporter phổ biến có series:

~~~text
kafka_consumergroup_lag{
  consumergroup="orders-worker-prod",
  topic="orders.events",
  partition="0"
}
~~~

**Giả định từ đây:** exporter thật của bạn có `kafka_consumergroup_lag` với labels `consumergroup`, `topic`, `partition`. Một số exporter/managed Kafka platforms dùng tên/labels khác; phải xác minh trước khi dùng PromQL.

### 8.1. Tổng lag

~~~promql
sum by (consumergroup, topic) (
  kafka_consumergroup_lag{
    consumergroup="orders-worker-prod"
  }
)
~~~

### 8.2. Partition bị lag lớn nhất

~~~promql
max by (consumergroup, topic) (
  kafka_consumergroup_lag{
    consumergroup="orders-worker-prod"
  }
)
~~~

Cần cả **sum** và **max**: tổng lag nhỏ vẫn có thể có một hot partition gây trễ cho một nhóm business keys quan trọng.

### 8.3. Lag không phải delay time

Lag 5.000 records với consumer 100 records/s khác hoàn toàn consumer 20.000 records/s. Đối với SLA theo thời gian, nên bổ sung event age hoặc business processing delay với timestamp nguồn đáng tin cậy và xử lý clock skew.

### 8.4. No data không phải lag zero

Nếu group chưa commit offset, exporter thiếu quyền hoặc scraper mất kết nối, series có thể không được tạo. **Không dùng `or vector(0)` một cách mù quáng để hiển thị khỏe.** Cần có missing-telemetry/expected-group alert.

## 9. Thiết lập Prometheus scrape

Ví dụ cho lab có DNS `orders-worker` và `kafka-exporter` trong cùng mạng:

~~~yaml
global:
  scrape_interval: 30s
  evaluation_interval: 30s

scrape_configs:
  - job_name: orders-worker
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["orders-worker:8080"]
        labels:
          environment: lab
          cluster: kafka-lab

  - job_name: kafka-exporter
    static_configs:
      - targets: ["kafka-exporter:9308"]
        labels:
          environment: lab
          cluster: kafka-lab
~~~

Các host là **placeholder lab**, không phải endpoint của cluster thực. `localhost` chỉ đúng nếu exporter, app và Prometheus dùng cùng network namespace.

**Production nhiều Pod:** scrape qua một Service có thể chỉ nhìn thấy một Pod tại mỗi request và bỏ sót metrics của replica còn lại. Cần Kubernetes service discovery hoặc Prometheus Operator `PodMonitor`/`ServiceMonitor` để scrape từng Pod.

Ví dụ `PodMonitor` khi Pod có port tên `http`:

~~~yaml
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: orders-worker
  namespace: applications
  labels:
    release: kube-prometheus-stack
spec:
  namespaceSelector:
    matchNames:
      - applications
  selector:
    matchLabels:
      app: orders-worker
  podMetricsEndpoints:
    - port: http
      path: /actuator/prometheus
      interval: 30s
      scrapeTimeout: 10s
~~~

Đây là custom resource của **Prometheus Operator**, cần CRD/operator và selectors tương thích với Prometheus đang chạy. `http` phải đúng tên **container port**, network policy phải cho phép Prometheus scrape. Nếu có management port riêng, thay tương ứng.

Bảo vệ `/actuator/prometheus` bằng network policy, proxy hoặc authentication phù hợp. Không expose `/actuator/env`, `/actuator/configprops` hoặc heapdump ra Internet.

## 10. Các truy vấn PromQL quan trọng

### 10.1. Listener success rate

~~~promql
sum by (job, listener) (
  rate(
    app_kafka_consume_records_total{outcome="success"}[5m]
  )
)
~~~

### 10.2. Listener failure attempts trong 15 phút

~~~promql
sum by (job, listener) (
  increase(
    app_kafka_consume_records_total{outcome="error"}[15m]
  )
)
~~~

### 10.3. Lỗi produce per second

~~~promql
sum by (job, channel) (
  rate(
    app_kafka_produce_results_total{outcome="error"}[5m]
  )
)
~~~

### 10.4. Tỉ lệ listener attempts bị lỗi

~~~promql
sum by (job, listener) (
  rate(
    app_kafka_consume_records_total{outcome="error"}[5m]
  )
)
/
clamp_min(
  sum by (job, listener) (
    rate(app_kafka_consume_records_total[5m])
  ),
  0.001
)
~~~

`job` ở đây là **Prometheus scrape job**, không phải Kafka consumer group ID. Vì các custom counters có labels `listener`, `outcome`, còn group lag exporter có `consumergroup`, `topic`, không thể tự join theo topic/group nếu thiếu mapping. Đặt các panel cạnh nhau hoặc gắn một tập label nhất quán, low-cardinality theo cấu hình được kiểm soát.

### 10.5. Scrape availability

~~~promql
up{job="orders-worker"}
~~~

`up=1` chỉ nói scrape HTTP thành công. `up=0` là scraper không lấy được dữ liệu. Nếu target **biến mất khỏi discovery**, series `up` có thể mất hẳn; cần kiểm cả absent/missing target.

## 11. Cấu hình alert rules có thời gian xác nhận

Prometheus rule nên có:

- Query đo đúng đơn vị.
- Ngưỡng đủ phù hợp workload/SLO.
- `for` để chống spike ngắn.
- `severity` theo mức ảnh hưởng.
- Labels để routing không làm tăng cardinality vô hạn.
- Description và đường dẫn runbook hữu ích.
- Quy tắc khi telemetry không có.

Ví dụ file `kafka-alerts.yml`:

~~~yaml
groups:
  - name: spring-kafka-reliability
    interval: 30s
    rules:
      - alert: KafkaConsumerGroupLagHigh
        expr: |
          sum by (cluster, environment, consumergroup, topic) (
            kafka_consumergroup_lag{
              consumergroup="orders-worker-prod"
            }
          ) > 5000
        for: 10m
        labels:
          severity: warning
          service: orders-worker
        annotations:
          summary: "Kafka group lag cao"
          description: "Kiểm group membership, input rate, throughput, DLT"
          runbook_url: "https://runbooks.example.org/kafka/lag"

      - alert: KafkaConsumerPartitionLagHigh
        expr: |
          max by (cluster, environment, consumergroup, topic) (
            kafka_consumergroup_lag{
              consumergroup="orders-worker-prod"
            }
          ) > 2000
        for: 10m
        labels:
          severity: warning
          service: orders-worker
        annotations:
          summary: "Một partition có backlog lớn"

      - alert: KafkaListenerErrorRatioHigh
        expr: |
          (
            sum by (job, listener) (
              rate(
                app_kafka_consume_records_total{
                  outcome="error"
                }[5m]
              )
            )
            /
            clamp_min(
              sum by (job, listener) (
                rate(app_kafka_consume_records_total[5m])
              ),
              0.001
            )
          ) > 0.05
          and on (job, listener)
          (
            sum by (job, listener) (
              increase(app_kafka_consume_records_total[5m])
            ) > 20
          )
        for: 5m
        labels:
          severity: warning
          service: orders-worker
        annotations:
          summary: "Tỉ lệ listener attempt lỗi tăng"

      - alert: KafkaProducerSendFailures
        expr: |
          sum by (job, channel) (
            rate(
              app_kafka_produce_results_total{
                outcome="error"
              }[5m]
            )
          ) > 0.1
        for: 5m
        labels:
          severity: critical
          service: orders-worker
        annotations:
          summary: "Lỗi KafkaTemplate send kéo dài"

      - alert: KafkaApplicationScrapeDown
        expr: up{job="orders-worker"} == 0
        for: 3m
        labels:
          severity: critical
          service: orders-worker
        annotations:
          summary: "Không scrape được ứng dụng"

      - alert: KafkaExporterTargetMissing
        expr: absent(up{job="kafka-exporter"})
        for: 5m
        labels:
          severity: warning
          service: kafka-observability
        annotations:
          summary: "Không còn Kafka exporter target"
~~~

**Điều kiện cần trước khi sử dụng:**

1. Kafka exporter phải cung cấp `kafka_consumergroup_lag` và labels đã giả định.
2. Code listener/producer đã đăng ký hai metric `app.kafka.*`.
3. Prometheus scrape config tạo labels `job`, `cluster`, `environment` phù hợp.
4. Các ngưỡng là số **minh họa**, không copy thẳng vào production.
5. URL runbook là placeholder, phải thay đường dẫn thật.
6. Khi một series hoàn toàn mất, biểu thức tỷ lệ lỗi/lag có thể trả về empty vector; có alert missing telemetry riêng.
7. Nếu cùng Prometheus scrape nhiều environment, hãy filter rõ `environment`/`cluster` cho những rule quan trọng.

### 11.1. Tại sao alert ratio có điều kiện traffic?

Một lỗi trong một event duy nhất tạo error ratio 100%, nhưng có thể không đủ để page. Biểu thức:

~~~promql
sum by (job, listener) (
  increase(app_kafka_consume_records_total[5m])
) > 20
~~~

giới hạn ratio alert khi có ít nhất một lượng mẫu đáng kể. Với **event thanh toán quan trọng**, một lỗi nghiêm trọng vẫn có thể cần cảnh báo ngay bằng business audit alert khác. Không áp dụng cùng ngưỡng traffic cho tất cả SLO.

### 11.2. Tại sao `for` quan trọng?

Nếu một burst làm group lag vượt 5.000 trong 30 giây nhưng drain ngay, một alert `for: 10m` sẽ không page. Nếu lag kéo dài hơn 10 phút liên tục, rule có thể vào trạng thái firing theo evaluation schedule.

`for` không giải quyết được query sai, telemetry missing hay SLA chỉ 1 phút. Ngưỡng và thời gian phải xuất phát từ mức ảnh hưởng thực.

## 12. Đánh giá lag cùng tốc độ xử lý

Lag = 10.000 đang giảm 5.000 records/phút có thể là quá trình drain bình thường. Lag = 1.000 nhưng đứng im 30 phút với incoming traffic liên tục có thể nghiêm trọng hơn.

Một dashboard nên đặt cạnh nhau:

~~~promql
sum by (consumergroup, topic) (
  kafka_consumergroup_lag{
    consumergroup="orders-worker-prod"
  }
)
~~~

và:

~~~promql
sum by (listener) (
  rate(
    app_kafka_consume_records_total{outcome="success"}[5m]
  )
)
~~~

Không cộng hai kết quả: cái đầu là **số record backlog ở group**, cái sau là **lần listener callback thành công mỗi giây**. Khi retry hoặc redelivery, attempts không bằng unique events.

Nếu SLO tính thời gian hoàn tất, nên đo **business event age** hoặc delay từ timestamp đầu vào tới khi outcome bền vững. Việc ước lượng delay từ lag/throughput chỉ chính xác gần đúng trong tải tương đối ổn định.

## 13. Alertmanager routing và giảm nhiễu

Prometheus đánh giá rule; Alertmanager phụ trách grouping, routing, silence và inhibition.

Mẫu route đơn giản:

~~~yaml
route:
  receiver: default-ops
  group_by:
    - alertname
    - cluster
    - environment
    - service
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers:
        - severity="critical"
      receiver: oncall-critical

receivers:
  - name: default-ops
  - name: oncall-critical
~~~

Các receiver mới chỉ có tên minh họa, **chưa gửi thông báo**. Kết nối đến email, PagerDuty, chat hoặc webhook yêu cầu cấu hình receiver đúng và secret được quản lý an toàn, không commit token vào Git.

Cân nhắc:

- `warning`: ticket hoặc kênh theo dõi nếu xử lý được trong giờ làm việc.
- `critical`: page trực vận hành khi có nguy cơ mất dữ liệu, outage hoặc vi phạm SLO.
- Gom nhóm theo service/cluster thay vì tạo một thông báo cho từng partition/pod.
- Maintenance silence có thời hạn trong rollout, nhưng không tắt alert về data corruption.
- Khi exporter down, các alert lag có thể biến mất; không được hiểu là lag đã hết.

## 14. Dashboard Grafana tối thiểu

| Panel | Nguồn | Câu hỏi trả lời |
| --- | --- | --- |
| Group lag tổng | Kafka exporter | Backlog đang ở mức nào? |
| Max partition lag | Kafka exporter | Có partition bị kẹt không? |
| Listener success/error rate | Custom Micrometer | Consumer callback xử lý ra sao? |
| Producer ACK/failure rate | KafkaTemplate completion counters | Producer có gửi thành công? |
| Listener/business duration | Spring Kafka Timer/Observation hoặc Timer ứng dụng | p95/p99 có tăng không? |
| Consumer rebalances | Kafka client instrumentation | Group có bị churn không? |
| DLT backlog/rate | Exporter, DLT audit | Bao nhiêu record cần xử lý? |
| JVM CPU/heap/GC | Actuator | App có thiếu tài nguyên không? |
| Broker health/ISR/disk | Broker exporter | Cluster có áp lực không? |
| Business applied count | Database/audit | Đầu ra nghiệp vụ thực sự đúng không? |

Với percentiles, cần histogram buckets tương ứng. Nếu Timer chỉ xuất `_count`/`_sum` mà không có `_bucket`, không thể lấy p95 thực bằng `histogram_quantile` từ hai giá trị đó.

Khi dùng `MeterRegistry`, có thể tạo Timer cho phần xử lý nghiệp vụ riêng; không đo trùng built-in listener duration rồi cộng làm một. Với histogram nhiều labels, số series tăng theo số buckets.

## 15. DLT, retry và metric semantics

Luồng fault-tolerant điển hình:

~~~text
Consumer record
      |
      v
Listener processing
      |
      +-- success -> container ACK/commit theo policy
      |
      +-- error
            |
            v
       Error handler
            |
         retry(s)
            |
            +-- success
            |
            +-- exhausted
                    |
                    v
              DLT publisher
                    |
                 send future
                    |
                +---+---+
                |       |
               ACK     error
~~~

Không lấy `app.kafka.consume.records{outcome="error"}` rồi đổi tên thành `dlt_total`: một record có thể error nhiều lần rồi thành công, **không hề vào DLT**.

| Muốn đo | Thời điểm nên ghi |
| --- | --- |
| Listener attempts | Callback listener success/error. |
| Retry attempts | Retry/error-handler instrumentation cụ thể. |
| DLT publish requests | Khi recoverer gọi send. |
| DLT ACK successes | Khi future/recoverer xác nhận broker đã nhận theo cấu hình. |
| DLT backlog | Exporter/audit của DLT topic và group triage. |
| Business applied unique events | Transactional audit/idempotency store. |

Dùng `DefaultErrorHandler`, `DeadLetterPublishingRecoverer` hoặc `@RetryableTopic` theo version Spring Kafka đúng. Ghi nhận các tình huống error handler có thể retry/seek rồi commit offset theo recovery policy; không giả định một exception tương đương một message lost.

## 16. Kiểm thử custom counters bằng SimpleMeterRegistry

Với `OrdersListener` đã viết, có thể test trực tiếp mà không cần broker:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrdersListenerMetricsTest {

    @Test
    void countsSuccessAndErrorAttempts() throws Exception {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        try {
            OrderService service = event -> {
                if ("fail".equals(event.eventId())) {
                    throw new IllegalStateException("test failure");
                }
            };

            OrdersListener listener = new OrdersListener(
                new ObjectMapper(), service, registry);

            listener.onMessage(new ConsumerRecord<>(
                "orders.events", 0, 0L, "k1",
                "{\"eventId\":\"ok\",\"orderId\":\"o1\",\"amount\":100}"
            ));

            assertThrows(IllegalStateException.class, () ->
                listener.onMessage(new ConsumerRecord<>(
                    "orders.events", 0, 1L, "k2",
                    "{\"eventId\":\"fail\",\"orderId\":\"o2\",\"amount\":200}"
                ))
            );

            assertEquals(1.0,
                registry.get("app.kafka.consume.records")
                    .tags("listener", "orders", "outcome", "success")
                    .counter().count());

            assertEquals(1.0,
                registry.get("app.kafka.consume.records")
                    .tags("listener", "orders", "outcome", "error")
                    .counter().count());
        } finally {
            registry.close();
        }
    }
}
~~~

Test này chỉ xác nhận **Micrometer counters** tăng đúng. Nó không chứng minh Kafka partition assignment, offset commit, retry/DLT hoặc exporter group lag. Các điều đó cần integration test với broker thật.

Một registry có thể tồn tại qua nhiều test trong cùng Spring context: counter tích lũy. Dùng `SimpleMeterRegistry` riêng hoặc đo delta trước/sau, đừng giả định counter production luôn bắt đầu bằng 0.

## 17. Integration test với Kafka/DB

Dùng `@EmbeddedKafka` hoặc Testcontainers Kafka để dựng broker test, và database test cho business effect.

~~~text
Kafka test broker
    |
    +-- valid event ------> listener success
    |
    +-- invalid event ----> error handler retry/DLT
    |
    v
Micrometer test registry
    |
    v
Database/business audit
~~~

Ma trận test:

| Kịch bản | Assertion |
| --- | --- |
| Event hợp lệ | Listener success counter tăng, dữ liệu đích đúng. |
| Event làm use case ném lỗi | Error attempts tăng, error handler áp policy. |
| Retry thành công | Có error attempts trước success, business effect không trùng. |
| Poison message vào DLT | Record thật có trong DLT, ACK/recovery theo policy. |
| Producer broker không reachable | Future thất bại, producer error counter tăng. |
| Consumer restart | Group offsets/record redelivery theo policy, idempotency bảo vệ dữ liệu. |
| Pod bị restart | Counter runtime reset; DB audit và Kafka state vẫn được đối soát. |
| Exporter mất kết nối | `up`/missing alert, không trình bày lag=0 giả. |

Nếu cần kiểm SASL_SSL/TLS/ACL, broker test phải có security tương ứng; `@EmbeddedKafka` PLAINTEXT đơn giản không chứng minh production auth.

## 18. Kiểm thử alert bằng Prometheus rule tests

Alert có cú pháp đúng vẫn có thể không bao giờ firing vì:

- Metric name hoặc label không tồn tại.
- `job` label khác tên dự kiến.
- Window quá ngắn so với scrape interval.
- Query cho empty vector khi thiếu exporter.
- Condition `for` chưa kéo dài đủ.
- Alertmanager đang silence hoặc route sai receiver.
- Phân số có mẫu bằng zero hoặc số mẫu quá ít.

Quy trình test:

1. Xem series thật trong Prometheus expression browser.
2. Chạy từng biểu thức PromQL để kiểm labels/value.
3. Kiểm cú pháp bằng `promtool check rules`.
4. Dùng `promtool test rules` với fixture time series và expected alerts.
5. Trong staging, tạo lag/error có kiểm soát, theo dõi trạng thái `pending → firing → resolved`.
6. Kiểm Alertmanager nhận đúng severity/service/environment.
7. Kiểm thông báo dẫn tới runbook và dashboard đúng.
8. Chỉ sau đó mới enable route production.

Ví dụ thời gian:

~~~text
T+00: lag = 100
T+05: lag = 7000
T+10: lag = 7000
T+15: lag = 7000

Rule: lag > 5000, for: 10m

Không fire ngay tại T+05.
Có thể fire sau khi điều kiện duy trì đủ 10 phút,
theo nhịp evaluation thực của Prometheus.
~~~

Chú ý: nếu rule đã có `for: 10m`, việc chỉ test lỗi 30 giây chưa chứng minh alert sẽ firing.

## 19. Runbook: consumer lag tăng

**Triệu chứng:** sum lag hoặc max partition lag cao kéo dài.

### Chẩn đoán

1. Xác nhận exporter/scrape khỏe và lag series có thật.
2. Xác định group, topic, partition nào tăng.
3. Kiểm group membership và partition assignment.
4. Kiểm producer incoming rate: đang burst hay hệ thống thực sự chậm?
5. Kiểm listener attempts, lỗi, DLT, retry và poison message.
6. Kiểm rebalances, poll interval, consumer thread CPU/GC.
7. Kiểm downstream DB/API latency và connection pools.
8. So sánh backlog drain rate với thời hạn xử lý.
9. Kiểm deployment/config gần nhất, nhất là `group.id`, topic, concurrency, ack mode.

### Hành động

- Xử lý bottleneck downstream trước khi tăng concurrency.
- Nếu poison record chặn partition, dùng DLT/quarantine theo policy.
- Nếu ứng dụng xử lý quá lâu giữa poll, điều chỉnh batch size/processing hoặc interval sau khi có số đo.
- Nếu cần scale, kiểm `replicas × concurrency` với partition count và capacity DB.
- Nếu lag đang drain bình thường, theo dõi SLA và điều chỉnh alert threshold đúng hơn.

**Không đổi group ID hoặc reset offsets** chỉ để biểu đồ lag chuyển xanh. Hai thao tác này có thể replay hoặc bỏ sót dữ liệu.

## 20. Runbook: producer send failure

1. Kiểm bootstrap servers, DNS, advertised listeners và kết nối network.
2. Kiểm SASL/TLS handshake, credential rotation và ACL Write của producer.
3. Kiểm broker/topic health, ISR, latency và availability.
4. Kiểm payload size, serialization và Kafka client timeouts.
5. Kiểm returned future exception; phân biệt client retry và application retry.
6. Đối soát event ID/idempotency khi client timeout nhưng broker có thể đã nhận.
7. Với dữ liệu quan trọng, retry qua durable outbox theo policy thay vì drop event.

Đừng giảm `acks=all` thành `acks=0` để che lỗi. Điều đó thay đổi bảo đảm durability chứ không sửa nguyên nhân thực.

## 21. Runbook: DLT tăng hoặc record lỗi lặp

- Đối chiếu thời điểm release/schema change và DLT spike.
- Phân loại lỗi: deserialization, validation, DB transient, downstream timeout, ACL.
- Kiểm error handler và retry budget, tránh retry vô hạn.
- Kiểm DLT producer có quyền gửi và ACK hay không.
- Lưu các event IDs cần triage trong audit phù hợp, không đưa payload/PII lên metric label.
- Chỉ replay DLT sau khi root cause được sửa; kiểm idempotency vì một attempt trước có thể đã tạo side effect.
- Kiểm source topic lag và DLT backlog riêng.

Một DLT topic có record không có nghĩa mọi record đều mất: nó là **luồng phục hồi có kiểm soát**, nhưng vẫn phải có người/quy trình xử lý DLT.

## 22. Runbook: Prometheus/Grafana không có dữ liệu

~~~text
Application / Kafka exporter
             |
             v
       HTTP metrics endpoint
             |
             v
      Prometheus discovery/scrape
             |
             v
          TSDB/rules
             |
             v
       Grafana/Alertmanager
~~~

Kiểm:

1. App/Pod và exporter có chạy không?
2. `up{job="..."}` là 0, 1 hay hoàn toàn không có series?
3. Endpoint có trả HTTP 200 qua network của Prometheus?
4. ServiceMonitor/PodMonitor selector, namespace và port name có đúng?
5. Micrometer exporter registry có được cấu hình không?
6. Counter đã được đăng ký và listener/producer có thực sự chạy chưa?
7. Có đổi tên metric sau nâng version Spring Boot/Micrometer/exporter không?
8. Dashboard filter job/cluster/environment có đang loại hết dữ liệu không?
9. NetworkPolicy/TLS/auth có chặn scrape không?

**Không chuyển `No data` thành 0 một cách tự động** trong alert quan trọng. Cần alert thiếu telemetry hoặc thiếu expected targets.

## 23. Cardinality, bảo mật và chi phí

Một nhãn mới cho từng `eventId`, `orderId`, `offset`, email, exception message hoặc request ID có thể tạo hàng triệu time series và làm lộ dữ liệu nhạy cảm.

Không dùng:

~~~text
eventId=evt-123456
userEmail=user@example.org
apiToken=...
offset=123456789
exceptionMessage=Connection failed for password=...
~~~

Nên dùng các tập giá trị ổn định:

~~~text
listener=orders
outcome=success|error
channel=orders
errorCategory=validation|timeout|db|other
application=orders-worker
environment=production
~~~

Kafka exporter có thể cần label `topic`, `consumergroup`, `partition`, nhưng phải xét số lượng topic/partition/group và chi phí lưu trữ.

Các endpoint `/actuator/env`, `/actuator/configprops`, heapdump và metrics cần access control phù hợp. Không dump toàn bộ KafkaProperties vì có thể chứa SASL JAAS config. Alertmanager webhook/token phải nằm trong secret manager, không commit vào Git.

## 24. Phân biệt metric, log, trace và audit

| Công cụ | Phù hợp cho | Giới hạn |
| --- | --- | --- |
| Metrics | Rate, error ratio, latency, lag, SLO | Không chứa chi tiết từng event. |
| Logs | Stack trace, topic/partition/offset, error category | Không nên dùng để tính throughput dài hạn nếu có metric. |
| Traces | Đường đi event qua Kafka, app, DB, API | Sampling có thể bỏ sót một số event. |
| Audit DB/outbox | Business keys, side effects đã commit, đối soát | Không thay thế time series monitoring tức thời. |

Khi alert firing, dashboard cho biết **ở đâu và bao lâu**, logs/traces cho biết **vì sao**, còn audit xác minh **dữ liệu cuối có đúng không**.

## 25. Kiểm tra triển khai production

| Bước | Hành động | Kỳ vọng |
| --- | --- | --- |
| 1 | Chốt SLI/SLO và owner | Metric có ý nghĩa, ngưỡng có cơ sở. |
| 2 | Bật Actuator/Micrometer | Có metrics endpoint được bảo vệ. |
| 3 | Thêm custom counters | Đơn vị đếm attempts và futures rõ ràng. |
| 4 | Kết nối Kafka exporter | Lag theo group/topic/partition có thật. |
| 5 | Scrape tất cả Pod | Không bỏ sót replica do scrape qua một Service duy nhất. |
| 6 | Xác nhận metric names/labels | PromQL khớp dữ liệu thực tế. |
| 7 | Thiết lập rules + Alertmanager | Đúng severity, route và `for`. |
| 8 | Kiểm thiếu telemetry | Exporter/Pod mất metrics vẫn báo lỗi. |
| 9 | Fault injection ở staging | Alert firing/resolved đúng tình huống. |
| 10 | Gắn runbook | On-call có hành động cụ thể. |
| 11 | Calibrate theo traffic | Tránh false positives và alert fatigue. |
| 12 | Review security/cardinality | Không lộ secret/PII và không bùng nổ series. |

## 26. Bài tập thực hành

### Bài 1 — Quan sát bốn tầng

Liệt kê metric của broker, consumer group, Kafka client và business service. Chỉ ra `records-lag-max` khác `kafka_consumergroup_lag` thế nào và metric nào có thể reset khi Pod restart.

### Bài 2 — Actuator

Chạy Spring Boot local với Prometheus registry, xem `/actuator/metrics` và `/actuator/prometheus`. Ghi lại tên metric thật, không công khai endpoint nhạy cảm.

### Bài 3 — Listener attempts

Dùng fake OrderService cho một event thành công và một event lỗi. Kiểm counters tương ứng, đồng thời lỗi vẫn được ném để error handler áp retry/DLT.

### Bài 4 — Producer future

Mock KafkaTemplate future thành công và lỗi. Kiểm Counter tăng **khi future hoàn tất**, không phải khi `send()` vừa trả về.

### Bài 5 — Lag khi consumer tạm ngừng

Trên broker test, chạy group có committed offset, pause consumer rồi publish 100 record. Quan sát exporter lag sau scrape; resume và theo dõi lag drain. Không làm trên production.

### Bài 6 — Hot partition

Tạo topic 3 partitions, gửi nhiều record cùng key. So sánh tổng lag và max partition lag, giải thích vì sao tăng Pod không tự giải quyết một partition bị kẹt.

### Bài 7 — Error ratio với traffic thấp

Kiểm rule với 1/1 lỗi và 30/100 lỗi. Xác minh điều kiện traffic và `for` tạo cảnh báo theo mong muốn, không page ồ ạt vì một record đơn lẻ ngoài policy.

### Bài 8 — DLT

Gây poison message trên broker test, quan sát listener attempts, retry, DLT publish confirmations và DLT topic growth. Giải thích vì sao bốn số đếm không bằng nhau.

### Bài 9 — Missing telemetry

Ngắt exporter hoặc làm PodMonitor selector không khớp trong staging, kiểm `up`/absence alerts và dashboard không coi `No data` là khỏe.

### Bài 10 — Incident drill

Cho database test chậm gây consumer lag. Áp dụng runbook chẩn đoán, giải quyết bottleneck và kiểm dữ liệu business không duplicate sau khi consumer resume.

## 27. Tài liệu tham khảo

- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Prometheus Support](https://docs.spring.io/spring-boot/reference/actuator/metrics.html#actuator.metrics.export.prometheus)
- [Spring Kafka — Monitoring and Micrometer](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring Kafka — Receiving Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka — Error Handling](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Apache Kafka — Monitoring](https://kafka.apache.org/documentation/#monitoring)
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Prometheus — Querying Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Prometheus — Unit Testing Rules](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/)
- [Alertmanager — Configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [Prometheus Operator — PodMonitor API](https://prometheus-operator.dev/docs/api-reference/api/#monitoring.coreos.com/v1.PodMonitor)
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/)

