# Records processed và records failed

Trong vận hành **Spring Kafka Reliability Operations**, hai câu hỏi thường xuất hiện đầu tiên khi có sự cố là: **bao nhiêu record đã xử lý thành công?** và **bao nhiêu record xử lý thất bại?**. Hai con số này cần được đo rõ ràng vì Kafka consumer có thể đọc record nhưng listener thất bại, một record có thể bị retry nhiều lần, hoặc nghiệp vụ đã hoàn tất nhưng offset chưa commit khiến record được giao lại.

**Records processed** và **records failed** không phải metric Kafka broker mặc định với một ý nghĩa thống nhất cho mọi ứng dụng. Chúng là các khái niệm giám sát phải được gắn với **điểm đo** cụ thể: Kafka fetch, listener invocation, business transaction, commit offset hay DLT recovery. Nếu dashboard trộn các điểm đo này, một hệ thống đang mất khả năng xử lý có thể bị hiểu nhầm là khỏe, hoặc một retry tự phục hồi bị báo thành hàng chục record hỏng.

Bài học hướng dẫn cách định nghĩa và instrument các chỉ số bằng Micrometer/Spring Kafka, phân biệt lỗi tạm thời với terminal failure, quan sát Prometheus, tính rate, kết hợp lag và vận hành runbook.

## 1. Một record đi qua những trạng thái nào?

~~~mermaid
flowchart TD
    A[Producer publish] --> B[Kafka topic/partition]
    B --> C[Consumer poll/fetch]
    C --> D{Deserialize thành công?}
    D -->|Không| E[Deserialization error handler]
    D -->|Có| F[Spring Kafka listener]
    F --> G{Nghiệp vụ thành công?}
    G -->|Có| H[Listener trả về]
    G -->|Không| I[Listener ném exception]
    I --> J[Error handler hoặc transaction rollback]
    J -->|Retry| F
    J -->|Hết retry| K[Recoverer / DLT]
    H --> L[Offset commit theo AckMode/transaction]
    K --> M[Offset tiến theo recovery policy]
    E --> J
~~~

Mỗi bước cho một loại số liệu khác nhau:

| Điểm đo | Metric logic | Ý nghĩa |
|---|---|---|
| Kafka broker | Produced/appended records | Broker ghi nhận dữ liệu được gửi đến topic. |
| Kafka consumer | Consumed/fetched records | Client đọc được record, chưa khẳng định xử lý thành công. |
| Listener | Processing attempts | Số lần listener được gọi, bao gồm retry/redelivery. |
| Listener | Successful attempts | Số lần method hoàn tất bình thường theo contract. |
| Listener | Failed attempts | Số lần method ném exception. |
| Nghiệp vụ | Business applied | Tác động nghiệp vụ mới được commit bền vững. |
| Idempotency | Duplicate suppressed | Event cũ được nhận lại nhưng không áp dụng hiệu ứng lần nữa. |
| Recovery | Terminal failure | Record đã hết retry hoặc không retry và đi sang xử lý lỗi. |
| Kafka group | Committed offset | Vị trí consumer group sẽ tiếp tục sau restart. |

Không dùng một bộ đếm duy nhất tên `records_processed` để đại diện cho toàn bộ quá trình. **Metric contract** phải ghi rõ thành công ở cấp listener, ở transaction nghiệp vụ, hay ở offset commit.

## 2. Định nghĩa chính xác records processed

Một định nghĩa thực dụng cho metric ở listener là:

> `records_processed` = số lần listener xử lý một record và trả về bình thường mà không ném exception.

Ưu điểm: dễ instrument, dễ tính throughput và so sánh với failed attempts. Hạn chế: kết quả chưa chứng minh Kafka offset đã commit, chưa chứng minh transaction Kafka commit và chưa chắc là một hiệu ứng nghiệp vụ **duy nhất**.

Ví dụ record `evt-123` được xử lý thành công, database commit, nhưng pod chết trước offset commit. Khi pod mới nhận lại cùng offset, listener có thể return thành công lần nữa. `records_processed` tăng **hai**, dù business event chỉ có **một**.

Với service cần đếm số sự kiện mới áp dụng thật sự, nên có metric khác:

- `records_business_applied`: event tạo ra tác động nghiệp vụ mới.
- `records_duplicate_suppressed`: event được phát hiện đã xử lý, không tạo tác động lần nữa.
- `records_business_rejected`: event bị từ chối theo quy tắc nghiệp vụ nhưng listener xử lý trạng thái từ chối thành công.

**Business rejection không nhất thiết là Kafka processing failure.** Ví dụ một giao dịch bị từ chối do hạn mức là outcome hợp lệ; listener ghi `REJECTED` thành công vẫn có thể được xem là processed.

## 3. Định nghĩa chính xác records failed

Một record có thể thất bại nhiều lần nhưng cuối cùng thành công. Vì vậy nên tách:

| Metric logic | Khi tăng | Dùng để làm gì |
|---|---|---|
| `records_failed_attempts` | Mỗi lần listener invocation ném exception | Phát hiện retry storm, lỗi hạ tầng, tỷ lệ attempt lỗi. |
| `records_terminally_failed` | Retry policy kết thúc mà nghiệp vụ không được xử lý thành công | Đếm outcome lỗi ở cấp record, không phải số attempt. |
| `records_dlt_published` | DLT publish được xác nhận theo producer send policy | Đếm record đã được bàn giao bền vững vào DLT. |
| `records_deserialization_failed` | Record lỗi trước khi listener được gọi | Bổ sung phần lỗi listener metrics không nhìn thấy. |
| `records_recovered_without_dlt` | Record được recovery bằng cơ chế khác | Phân biệt nhánh recovery với DLT. |

`records_failed_attempts` là metric vận hành **theo lần thử**. `records_terminally_failed` muốn có ý nghĩa **theo record duy nhất** cần thêm chính sách nhận diện logical event, retry topic, replay và duplicate. Không suy ra số unique failed events chỉ bằng cách lấy số exception.

## 4. Ví dụ: năm sự kiện nhưng mười lần listener được gọi

Giả sử:

- A thành công ngay lần đầu.
- B lỗi hai lần rồi thành công ở lần thứ ba.
- C lỗi bốn lần rồi được chuyển sang DLT.
- D là duplicate, listener kiểm tra inbox và return thành công nhưng không cập nhật database lần nữa.
- E thành công ngay lần đầu.

| Event | Listener attempts | Failed attempts | Successful attempts | Applied mới | Duplicate | Terminal DLT |
|---|---:|---:|---:|---:|---:|---:|
| A | 1 | 0 | 1 | 1 | 0 | 0 |
| B | 3 | 2 | 1 | 1 | 0 | 0 |
| C | 4 | 4 | 0 | 0 | 0 | 1 |
| D | 1 | 0 | 1 | 0 | 1 | 0 |
| E | 1 | 0 | 1 | 1 | 0 | 0 |
| **Tổng** | **10** | **6** | **4** | **3** | **1** | **1** |

Nếu dashboard hiển thị `failed_attempts=6`, điều đó **không có nghĩa sáu event bị hỏng**. Chỉ event C kết thúc ở nhánh recovery terminal. B đã tự phục hồi sau retry.

Nếu dashboard hiển thị `processed=4`, cũng không có nghĩa bốn thay đổi nghiệp vụ mới: D chỉ là duplicate được xử lý an toàn.

Phải xác định rõ **mẫu số** và **tập đối tượng** trước khi đưa ra tỷ lệ lỗi.

## 5. Metric naming convention và labels

Ví dụ quy ước ứng dụng:

~~~text
app.kafka.records.processed
app.kafka.records.failed.attempts
app.kafka.records.business
app.kafka.records.terminally.failed
app.kafka.records.dlt.published
app.kafka.records.deserialization.failed
app.kafka.record.processing.duration
~~~

Đây là **custom Micrometer metrics** của ứng dụng, không phải tên metric mặc định của Spring Kafka. Với Prometheus registry, chúng thường xuất thành:

~~~text
app_kafka_records_processed_total
app_kafka_records_failed_attempts_total
app_kafka_records_business_total
app_kafka_records_terminally_failed_total
app_kafka_records_dlt_published_total
~~~

Tên thực tế phụ thuộc naming convention và registry version. Luôn quan sát endpoint `/actuator/prometheus` thay vì giả định chuỗi xuất ra giống tên trong code.

### Labels nên có

| Label | Giá trị ví dụ | Mục tiêu |
|---|---|---|
| `application` | `orders-service` | Phân biệt ứng dụng. |
| `environment` | `production` | Phân biệt môi trường. |
| `listener` | `orders-listener` | Khoanh vùng handler. |
| `topic` | `orders.events` | Khoanh vùng luồng dữ liệu. |
| `consumer_group` | `orders-service` | Tương quan với lag/assignment. |
| `outcome` | `applied`, `duplicate`, `rejected` | Phân loại business result hữu hạn. |
| `error_category` | `validation`, `dependency_timeout`, `other` | Nhìn nhóm lỗi thay vì stack trace. |

### Labels không nên có

- `eventId`, `orderId`, `customerId`, request ID.
- Offset, payload hoặc exception message nguyên văn.
- URL có query thay đổi liên tục.
- UUID tạo mới cho mỗi attempt hoặc replay.

Những nhãn đó làm **cardinality** tăng cực lớn, gây tốn bộ nhớ và truy vấn Prometheus. Đặt chúng vào structured logs/traces. Label `partition` là hữu hạn nhưng có thể tạo nhiều series khi topic rất lớn; chỉ thêm nếu thật sự cần phân tích metrics ở cấp partition.

## 6. Tích hợp Spring Boot Actuator và Micrometer

Các dependency Maven thông dụng:

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

Cấu hình minh họa:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: orders-service
      environment: production

spring:
  kafka:
    consumer:
      group-id: orders-service
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

`/actuator/metrics` dùng để xem metric names và tags ở dạng Actuator; `/actuator/prometheus` xuất dữ liệu cho Prometheus khi registry được cài và endpoint được mở đúng. Trong production cần kiểm soát network, authentication và quyền truy cập các endpoint giám sát. Không công khai endpoint metrics tùy tiện.

### Loại metric nào phù hợp?

- `Counter`: số lần processed, failed attempts, DLT published, duplicate suppressed.
- `Timer`: thời lượng listener xử lý record; cho phép quan sát throughput/count và latency.
- `Gauge`: giá trị hiện tại như in-flight work, queue size; không thay counter sự kiện.

Counter là số **tích lũy trong process**, có thể reset khi pod restart. Dashboard nên dùng `rate()`/`increase()` để quan sát thay đổi theo thời gian, không lấy counter hiện tại làm tổng lịch sử đáng tin cậy.

## 7. Instrument listener bằng Micrometer

Ví dụ listener xử lý sự kiện đơn lẻ và đếm processed, failed attempts, cùng outcome áp dụng nghiệp vụ.

~~~java
@Component
public class OrdersKafkaListener {

    private final OrdersService ordersService;
    private final MeterRegistry registry;

    public OrdersKafkaListener(
            OrdersService ordersService,
            MeterRegistry registry) {
        this.ordersService = ordersService;
        this.registry = registry;
    }

    @KafkaListener(
            id = "orders-listener",
            topics = "orders.events",
            groupId = "orders-service")
    public void onMessage(ConsumerRecord<String, OrderEvent> record) {
        long startedAt = System.nanoTime();
        String result = "failed";

        try {
            ApplyResult applyResult =
                    ordersService.applyIdempotently(record.value());

            registry.counter(
                    "app.kafka.records.processed",
                    "listener", "orders-listener"
            ).increment();

            registry.counter(
                    "app.kafka.records.business",
                    "listener", "orders-listener",
                    "outcome",
                    applyResult == ApplyResult.APPLIED
                            ? "applied" : "duplicate"
            ).increment();

            result = "processed";
        }
        catch (RuntimeException ex) {
            registry.counter(
                    "app.kafka.records.failed.attempts",
                    "listener", "orders-listener",
                    "error_category", classify(ex)
            ).increment();

            throw ex;
        }
        finally {
            Timer.builder("app.kafka.record.processing.duration")
                    .tags("listener", "orders-listener",
                          "result", result)
                    .register(registry)
                    .record(System.nanoTime() - startedAt,
                            TimeUnit.NANOSECONDS);
        }
    }

    private static String classify(RuntimeException ex) {
        if (ex instanceof BusinessValidationException) {
            return "validation";
        }
        if (ex instanceof DownstreamTimeoutException) {
            return "dependency_timeout";
        }
        return "other";
    }
}
~~~

`OrdersService`, `OrderEvent`, `ApplyResult`, `BusinessValidationException` và `DownstreamTimeoutException` là các kiểu ứng dụng tự định nghĩa. Import `MeterRegistry`, `Timer`, `ConsumerRecord`, `TimeUnit`, annotation Spring và các class nghiệp vụ tùy dự án.

Điểm đo `processed` nằm sau lời gọi service. Nếu service là **Spring bean riêng** với database transaction hoàn tất trước khi lời gọi service trả về, metric này có thể phản ánh tốt kết quả database của mỗi invocation. Nhưng Kafka offset/transaction thường được commit **sau** khi listener return. Do đó đây vẫn là **listener success counter**, không phải chứng nhận Kafka transaction đã commit.

### Vì sao phải throw lại exception?

Nếu listener catch exception rồi chỉ ghi failed metric nhưng không throw và cũng không có recovery hợp lệ:

~~~java
try {
    ordersService.apply(event);
}
catch (Exception ex) {
    registry.counter("app.kafka.records.failed.attempts").increment();
    // Anti-pattern: chỉ log rồi return bình thường.
}
~~~

Container có thể coi record đã xử lý xong và commit offset theo `AckMode`, dù nghiệp vụ chưa hoàn tất. Ghi counter failed **không thay thế** `DefaultErrorHandler` hoặc transaction rollback.

Ngược lại, business rejection hợp lệ có thể được lưu như một outcome nghiệp vụ rồi return thành công, không nhất thiết phải ném exception.

## 8. Record được giao lại: processed không phải unique applied

Một kịch bản at-least-once:

~~~text
T1: Consumer xử lý evt-17, ghi DB thành công.
T2: Process crash trước khi commit Kafka offset.
T3: Consumer mới nhận lại evt-17.
T4: Inbox nhận ra event đã xử lý, bỏ qua side effect.
T5: Listener return thành công lần nữa.
~~~

Nếu instrument tại listener:

~~~text
records_processed += 2
records_business{outcome="applied"} += 1
records_business{outcome="duplicate"} += 1
~~~

Vì vậy metric `business_applied` cần gắn với kết quả áp dụng nghiệp vụ bền vững, không chỉ dựa trên method invocation. Một cách phổ biến là lưu `eventId` với unique constraint trong cùng database transaction với thay đổi trạng thái nghiệp vụ. Khi record được giao lại, duplicate được nhận diện trước khi cập nhật lần nữa.

Nếu yêu cầu **đối soát chính xác dài hạn**, nguồn sự thật nên là bảng nghiệp vụ/audit hoặc một event log bền vững. Prometheus counter là telemetry có thể mất một số lần tăng khi process chết trước lần scrape.

## 9. Failed attempts và terminal failure đặt ở hai tầng khác nhau

Khi listener ném exception, `DefaultErrorHandler` có thể retry nhiều lần. Vì thế code `catch` ở listener chỉ được phép đếm **failed attempt**. Listener chưa biết record sẽ được retry, được DLT recovery hay thành công ở lần sau.

~~~mermaid
flowchart LR
    A[Listener throws] --> B[Failed attempt +1]
    B --> C[Error handler]
    C --> D{Retry tiếp?}
    D -->|Có| E[Re-deliver]
    E --> A
    D -->|Không| F[Recoverer]
    F --> G{Recovery xác nhận thành công?}
    G -->|Có| H[Terminal outcome +1]
    G -->|Không| I[Recovery failure]
~~~

Ví dụ `FixedBackOff(1000L, 3L)` cho phép ba lần retry sau lần xử lý đầu tiên, theo semantics của Spring `FixedBackOff`. Một record có thể tạo đến bốn failed attempts trước khi recoverer được gọi.

Nếu kết quả recovery là đưa sang DLT, tăng `records_dlt_published` khi record đã được **xác nhận publish** theo producer ack/send result policy. Tùy phiên bản, recoverer có thể hoạt động với send bất đồng bộ hoặc có tùy chọn kiểm tra kết quả gửi; việc một method return không phải lúc nào cũng tương đương dữ liệu đã lưu bền vững.

`records_terminally_failed` cũng phải có contract rõ: nó đếm mỗi lần record đến terminal recovery stage hay mỗi **unique logical event**. Khi có retry topic/replay, một event có thể đi qua nhiều topic, vì vậy cần correlation/event ID để tránh cộng trùng.

### DLT không phải business success

Record được chuyển sang DLT và offset nguồn có thể tiến theo recovery policy. Consumer lag giảm, nhưng nghiệp vụ gốc chưa thành công. Dashboard cần tách `handled_by_recovery` khỏi `business_applied`.

## 10. Lỗi xảy ra trước listener

Không phải mọi record lỗi đều đi vào method `@KafkaListener`. Payload sai schema có thể khiến deserializer ném exception trước khi listener được gọi.

Vì thế:

- Listener `records_failed_attempts` có thể vẫn bằng 0.
- Record lỗi vẫn có thể chặn consumer hoặc được error handler recovery.
- Consumer lag tăng hoặc DLT tăng.
- Dashboard chỉ quan sát `catch` của listener sẽ bỏ sót lỗi này.

Spring Kafka có `ErrorHandlingDeserializer` để chuyển thông tin lỗi deserialize vào error-handling path theo cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.trusted.packages]": "com.example.orders.events"
~~~

Ví dụ chỉ minh họa nguyên tắc; cần cấu hình type mappings và trusted packages đúng contract. Không mở `trusted.packages=*` tùy tiện trong production.

Nếu cần đếm lỗi deserialize, hãy instrument tại error handler/recovery path phù hợp. Đừng gộp lỗi deserialize với listener failed attempts nếu mục tiêu muốn phân tích riêng các tầng.

## 11. Kafka client metrics khác listener metrics

Kafka consumer client có metrics như:

- `records-consumed-rate`, `records-consumed-total`.
- `bytes-consumed-rate`.
- `records-lag`, `records-lag-max`.
- Commit latency và poll metrics.

Tên cụ thể và cách xuất qua JMX/Micrometer phụ thuộc Kafka client, Spring Boot và registry.

Các metric đó phản ánh **fetch/poll/commit ở Kafka client**, không đồng nghĩa số event nghiệp vụ đã xử lý. Một consumer có thể fetch records trước khi listener xử lý; retry có thể giao lại cùng record; record có thể filtered hoặc deserialize lỗi.

Không đặt quan hệ giả định:

~~~text
Kafka records consumed = records processed = unique business events applied
~~~

Mối quan hệ này thường không đúng.

### Micrometer listener timers và observations có sẵn

Spring Kafka có hỗ trợ Micrometer listener timers và Micrometer Observation ở các phiên bản phù hợp. Timer truyền thống có thể xuất hiện với tên như `spring.kafka.listener`, cùng các tags kết quả/exception tùy version.

Ví dụ những cấu hình container có trong các dòng Spring Kafka hỗ trợ:

~~~java
factory.getContainerProperties().setMicrometerEnabled(true);
~~~

Hoặc dùng Observation:

~~~java
factory.getContainerProperties().setObservationEnabled(true);
~~~

Cần kiểm tra API và cơ chế hiện hành của phiên bản Spring Kafka. Khi Observation được bật, việc thu metrics/traces và naming có thể khác timer truyền thống; không bật cả hai tùy tiện để tránh telemetry trùng.

**Timer count là số listener invocations**, không tự bảo đảm record count hoặc business unique count. Với batch listener, một invocation có thể có hàng trăm records. Kiểm tra `/actuator/metrics` để biết metric/tag thực tế thay vì đoán tên.

## 12. Batch listener: invocation count không phải record count

Với batch listener:

~~~java
@KafkaListener(topics = "orders.events", batch = "true")
public void onBatch(List<ConsumerRecord<String, OrderEvent>> records) {
    for (ConsumerRecord<String, OrderEvent> record : records) {
        ordersService.applyIdempotently(record.value());
    }
}
~~~

Nếu batch có 100 records:

- Listener timer count có thể chỉ tăng **1**.
- Nếu từng record được áp dụng thành công, record-level processed counter nên tăng **100** theo contract.
- Nếu record thứ 30 lỗi, cần hiểu 29 record trước có thực sự commit hay transaction bị rollback.
- Nếu batch exception không chỉ rõ vị trí lỗi, error handler có thể xử lý lại toàn batch.

`BatchListenerFailedException` trong những phiên bản hỗ trợ giúp chỉ ra index/record lỗi. Instrumentation phải gắn với record thật sự hoàn tất, không cộng toàn bộ batch ngay khi bắt đầu.

Khi batch chứa nhiều partition, offset và tiến độ cần được quản lý riêng theo từng topic-partition. Không có một offset toàn cục cho cả batch.

## 13. Consumer concurrency và nhiều pod

Spring Kafka `ConcurrentMessageListenerContainer` có thể tạo nhiều consumer threads; counter Micrometer xử lý cập nhật đồng thời tốt hơn biến `long` không đồng bộ.

Ví dụ:

~~~text
Pod A:
  Thread 1: processed 1.500
  Thread 2: processed 2.100

Pod B:
  Thread 1: processed 1.200
  Thread 2: processed 1.700

Tổng telemetry tại thời điểm quan sát: 6.500
~~~

Nhưng counter của mỗi pod có thể reset sau restart. Dashboard Prometheus nên dùng `rate()`/`increase()`, sum theo application/group/listener/environment để không cộng nhầm workload khác.

Nếu metrics có label `instance` hoặc `pod`, khi aggregate cho cả service cần xử lý label này một cách rõ ràng. Không cộng dữ liệu của production và staging hoặc hai consumer groups phục vụ hai mục đích nghiệp vụ khác nhau.

## 14. Truy vấn Prometheus cơ bản

Giả sử ứng dụng xuất:

~~~text
app_kafka_records_processed_total{application="orders-service",listener="orders-listener"}
app_kafka_records_failed_attempts_total{application="orders-service",listener="orders-listener",error_category="dependency_timeout"}
app_kafka_records_dlt_published_total{application="orders-service",listener="orders-listener"}
~~~

### Successful listener attempts mỗi giây

~~~promql
sum by (application, listener) (
  rate(app_kafka_records_processed_total[5m])
)
~~~

### Failed listener attempts mỗi giây

~~~promql
sum by (application, listener) (
  rate(app_kafka_records_failed_attempts_total[5m])
)
~~~

### Phân loại lỗi theo nhóm

~~~promql
sum by (application, listener, error_category) (
  rate(app_kafka_records_failed_attempts_total[10m])
)
~~~

### Tỷ lệ failed attempts trên các invocations được instrument

~~~promql
sum(rate(app_kafka_records_failed_attempts_total[5m]))
/
clamp_min(
    sum(rate(app_kafka_records_failed_attempts_total[5m]))
  + sum(rate(app_kafka_records_processed_total[5m])),
  0.001
)
~~~

Công thức chỉ phù hợp khi mỗi listener invocation nằm trong một trong hai outcome **processed** hoặc **failed attempt**, và cả hai metrics cùng phạm vi. Nó **không** tính deserialization failure trước listener nếu không instrument, không phải tỷ lệ record duy nhất bị lỗi terminal, và dễ kém ý nghĩa khi traffic rất thấp.

### Terminal failure trong một giờ

~~~promql
sum by (application, listener) (
  increase(app_kafka_records_terminally_failed_total[1h])
)
~~~

### DLT publish trong một giờ

~~~promql
sum by (application, listener) (
  increase(app_kafka_records_dlt_published_total[1h])
)
~~~

Khi có nhiều retry topics, cần thiết kế label `logical_pipeline` hoặc một mapping nhất quán để tổng hợp event đi qua các listener khác nhau. Nếu metrics bị chia theo tên topic retry, một event có thể xuất hiện nhiều lần ở các chặng và bị cộng trùng khi muốn đo unique business outcomes.

## 15. Không lấy failed / consumed để tính business failure rate

Công thức thường thấy nhưng dễ sai:

~~~text
failure_rate = listener_exceptions / kafka_records_consumed
~~~

Sai lệch đến từ:

- Một record bị retry nhiều lần.
- Client fetch nhiều record trước khi listener được gọi.
- Có lỗi trước listener.
- Record bị filter hoặc duplicate.
- Batch listener xử lý nhiều record trong một invocation.
- Retry topic tạo thêm record trên các topic trung gian.
- Hai metrics dùng window/nhãn khác nhau.

Nếu cần **terminal failure ratio theo event nguồn**, phải đo những outcome tương thích:

~~~text
terminal_failure_ratio =
    unique_source_events_terminally_failed
    /
    (unique_source_events_applied
     + unique_source_events_terminally_failed)
~~~

Công thức cần định nghĩa rõ event identity, khoảng thời gian, pending, replay và duplicate. Với nhiều ứng dụng, nên duy trì **hai dashboard**: technical processing attempts và business outcomes.

## 16. Processed rate phải xem cùng consumer lag

Một service có processed throughput cao vẫn có thể tụt lại nếu producer ghi nhanh hơn.

Ví dụ:

~~~text
Producer incoming rate:    1.000 records/giây
Successful attempts:         700 /giây
Failed attempts:              50 /giây
Consumer lag: tăng
~~~

Ví dụ mang tính minh họa, không phải quan hệ toán học chính xác trong mọi tình huống retry/transaction. Cần đo **lag slope** thực tế.

| Processed | Failed attempts | Lag | Khả năng cần điều tra |
|---|---|---|---|
| Cao | Thấp | Giảm | Consumer bắt kịp dữ liệu. |
| Cao | Thấp | Tăng | Producer rate tăng, consumer thiếu capacity. |
| Giảm | Tăng | Tăng | Lỗi listener hoặc downstream timeout. |
| Bằng 0 | Bằng 0 | Tăng | Consumer stopped/paused, poll lỗi, deserialize lỗi hoặc thiếu metrics. |
| Bằng 0 | Bằng 0 | Bằng 0 | Có thể không có traffic; bình thường theo lịch. |
| Cao | Cao | Tăng | Retry storm khiến nhiều attempts tốn thời gian. |
| Tăng | Thấp | Ổn định, DLT tăng | Nhánh recovery có thể đang bỏ qua nghiệp vụ gốc. |

Đối với partition bị kẹt, so sánh end offset, committed offset, assignment và listener exception. Một partition có lag lớn nhưng các partition khác bình thường có thể do poison pill, hot key hoặc pause.

## 17. Blocking retry và retry topics làm metric thay đổi thế nào?

Với `DefaultErrorHandler` blocking retry:

- Một record lỗi có thể tăng `failed_attempts` nhiều lần.
- Thread consumer có thể bị giữ bởi backoff hoặc xử lý.
- `processed` chỉ tăng khi một attempt hoàn tất bình thường.
- Lag có thể tăng trong lúc retry, kể cả khi producer tiếp tục ghi.

Với `@RetryableTopic` non-blocking retry:

- Record có thể chuyển từ topic nguồn sang một hoặc nhiều retry topics.
- Consumer topic nguồn có thể tiếp tục xử lý record mới.
- Listener ở retry topic có thể tạo metrics riêng.
- Một logical event có thể xuất hiện trong nhiều invocations ở những topic khác nhau.
- Thứ tự xử lý của các record cùng key trong topic nguồn có thể không còn được bảo toàn xuyên retry topic.

Không cộng `processed` của topic nguồn và retry topic rồi gọi đó là **unique source events processed**. Cần có contract về việc chuyển record sang retry topic: đó là **handoff**, không phải business applied.

## 18. Kafka transaction: processed counter có thể tăng trước commit

Trong transactional consume–transform–produce, Spring Kafka có thể đưa Kafka output và input offset vào cùng transaction. Nhưng code listener thực thi **trước khi Kafka transaction commit**.

~~~text
1. Listener xử lý và KafkaTemplate.send().
2. Counter records_processed += 1.
3. Listener return.
4. Container gửi offset vào transaction.
5. Kafka commit thất bại hoặc producer bị fenced.
6. Transaction abort; input có thể được giao lại.
~~~

Metric ở bước 2 đã tăng dù output Kafka chưa commit. Đó là vì nó đo **listener return success**, không phải transaction committed.

Nếu cần số Kafka transactions committed, sử dụng instrumentation phù hợp transaction lifecycle hoặc Kafka producer/client metrics theo version. Cũng không suy ra từ đó số database operations thành công vì Kafka transaction không tự bao trùm database hoặc HTTP.

Với business effect ngoài Kafka, idempotency là cần thiết cho redelivery, kể cả hệ thống sử dụng EOS cho Kafka-to-Kafka processing.

## 19. Record filtering và business rejection

`RecordFilterStrategy` có thể loại bỏ record **trước khi listener chạy**. Khi đó Kafka consumer fetch metric có thể tăng, nhưng custom listener `processed` không tăng. Nếu filter là một nhánh hợp lệ, cần đo `records_filtered` tại tầng filter theo contract, không tự coi record này là failed.

Tương tự, business event bị từ chối do rule hợp lệ có thể tạo kết quả:

~~~text
Input: PaymentRequested amount vượt hạn mức
Business outcome: REJECTED
Listener xử lý trạng thái từ chối thành công
Kafka processing outcome: SUCCESS
~~~

Nếu muốn thống kê nghiệp vụ, dùng `business_outcome=rejected` thay vì đẩy exception retry vô ích. Chỉ ném exception khi hành vi retry/recovery là chính sách mong muốn.

## 20. Monitoring theo partition

Một topic có thể có hot partition hoặc một partition bị kẹt trong khi throughput tổng thể vẫn cao.

~~~text
payments.events
  P0: processed ~400/s, lag ~0
  P1: processed ~0/s,   lag ~30.000
  P2: processed ~380/s, lag ~0
~~~

Để điều tra P1:

1. Xác định owner consumer hiện tại của partition.
2. Kiểm tra poll health, pause status và rebalance.
3. So sánh committed offset với end offset theo thời gian.
4. Tìm exception và record offset đang retry.
5. Kiểm tra DLT recoverer nếu lỗi permanent.
6. Đo processing duration và downstream latency.

Đặt partition làm label trên mọi custom metric có thể gây bùng nổ series. Với cluster lớn, ưu tiên Kafka group/client metrics theo partition cho lag và vị trí offset; application counters tổng hợp theo listener, topic và error category.

## 21. Dashboard tối thiểu cho production

| Panel | Chỉ số | Ý nghĩa vận hành |
|---|---|---|
| Processing throughput | Successful listener invocations / sec | Listener có hoạt động và tốc độ bao nhiêu. |
| Failed attempt rate | Failed listener invocations / sec | Lỗi/retry đang tăng hay giảm. |
| Attempt failure ratio | Failed / total instrumented attempts | Sức khỏe lần thử, không phải unique failure. |
| Terminal/DLT | DLT published, terminal recovered | Record không hoàn tất nghiệp vụ tại luồng chính. |
| Business outcome | Applied, duplicate, rejected | Kết quả nghiệp vụ thực tế. |
| Processing duration | p50/p95/p99 listener latency | Tìm bottleneck và nguy cơ timeout. |
| Consumer lag | Group/topic/partition lag | Consumer có theo kịp dữ liệu không. |
| Group health | Member count, rebalance, assignments | Consumer có còn phục vụ không. |
| Poll health | Poll interval, non-responsive events | Phát hiện thread bị giữ hoặc không poll. |
| Recovery backlog | Retry topic/DLT age và unresolved | Công việc chưa xử lý đang tích tụ. |

Đặt tên panel rõ đơn vị. “Successful listener invocations” khác “Unique business events applied”; “Failed attempts” khác “Terminally failed records”.

## 22. Alerting: đừng cảnh báo chỉ theo một counter

### Failed attempts tăng bất thường

Nên kết hợp:
- Tỷ lệ failed attempts.
- Số lượng invocations đủ lớn trong window.
- Thời gian duy trì vượt ngưỡng.
- Consumer lag và processing latency.
- Terminal failures/DLT.

Một lỗi duy nhất trong giờ có rất ít traffic có thể tạo tỷ lệ 100%; không nhất thiết là sự cố hệ thống.

### Processed bằng 0

Trước khi alert, cần xác định broker có nhận record mới không. Nếu topic thường chỉ có traffic giờ hành chính, processed bằng 0 giữa đêm có thể bình thường. Nếu producer ingress tăng, lag tăng mà processed bằng 0, đó là cảnh báo quan trọng.

### DLT tăng

Đây là outcome cần có owner và replay policy. DLT count tăng đều có thể nguy hiểm hơn nhiều failed attempts được retry thành công. Theo dõi tuổi unresolved records và khả năng xử lý trước retention deadline.

### Listener duration gần max.poll.interval.ms

Retry dài, timeout downstream và batch lớn có thể khiến consumer mất quyền trong group do vượt `max.poll.interval.ms`. Khi đó duplicate/rebalance/commit failure có thể tăng; phải quan sát thời gian poll cùng processing duration.

## 23. Runbook: Failed attempts tăng mạnh

1. Xác định application, listener, topic, environment và thời điểm bắt đầu.
2. Xem breakdown theo `error_category`; lấy stack trace tiêu biểu từ logs.
3. Đối chiếu thời điểm với deployment, thay đổi schema, database/API timeout hoặc broker incident.
4. Kiểm tra retry policy: attempt count, backoff, not-retryable exceptions.
5. So sánh terminal failure/DLT với failed attempts để biết lỗi có tự phục hồi không.
6. Kiểm tra consumer lag, processing duration và các partition bị giữ offset.
7. Với lỗi dữ liệu permanent, áp dụng quarantine/DLT theo policy thay vì retry vô hạn.
8. Với lỗi transient, khắc phục dependency và tránh retry storm.
9. Xác nhận failed rate giảm và business/offset progress phục hồi.

Không skip offset để làm dashboard hết lỗi khi chưa có quyết định nghiệp vụ.

## 24. Runbook: Processed bằng 0 nhưng failed cũng bằng 0

1. Kiểm tra producer ingress và broker end offset; có thể topic thực sự không có traffic.
2. Kiểm tra group member count, partition assignment và container running state.
3. Kiểm tra consumer pause, rebalance, auth và poll health.
4. Kiểm tra lỗi deserialize trước listener và RecordFilterStrategy.
5. Kiểm tra metric endpoint/scrape target còn xuất dữ liệu không.
6. Đối chiếu committed offset, end offset và lag từng partition.
7. Khắc phục nguyên nhân, xác minh listener xử lý và offset tiến.

**Không có failed metric** không chứng minh record nào cũng thành công; có thể listener chưa từng được gọi.

## 25. Runbook: Processed tăng nhưng lag tiếp tục tăng

1. Đo producer ingress rate và consumer processing rate trên cùng cửa sổ.
2. Xác định partition hot và phân bố key.
3. Kiểm tra số partition so với consumer concurrency.
4. Đo listener p95/p99 và downstream latency.
5. Kiểm tra retry overhead hoặc batch quá lớn.
6. Cân nhắc concurrency, batching, backpressure hoặc tối ưu business logic.
7. Không tăng concurrency vượt số partition rồi chờ một partition được xử lý song song.
8. Theo dõi lag slope và terminal/DLT outcome sau thay đổi.

## 26. Runbook: DLT tăng nhưng listener failed attempts thấp

1. Kiểm tra DLT records đến từ topic/listener nào, có retry topics không.
2. Xem lỗi permanent có bị đưa thẳng recovery mà không retry không.
3. Kiểm tra deserialize errors có xảy ra trước listener không.
4. Xác định custom counters có instrument tất cả retry listeners hay chỉ listener gốc.
5. Xác minh DLT send result đã được broker xác nhận.
6. Kiểm tra offset nguồn và recovery policy.
7. Bổ sung instrumentation ở error handler/deserialize path để không bỏ sót.
8. Lập hồ sơ replay và phân loại lỗi nghiệp vụ phù hợp.

## 27. Runbook: Processed tăng đột biến sau restart

1. Kiểm tra consumer group rebalance, pod restart và committed offset trước/sau.
2. Xác định có redelivery của record đã được database áp dụng không.
3. So sánh `processed`, `business_applied` và `duplicate_suppressed`.
4. Kiểm tra unique event ID/inbox constraint.
5. Đối chiếu Kafka offset với transaction outcome.
6. Nếu có side effect trùng, đánh giá bù trừ nghiệp vụ.
7. Không coi số tăng do replay là traffic business mới.
8. Dùng `rate()`/`increase()` thay vì so tổng counter qua restart.

## 28. Runbook: Query Prometheus không còn trả dữ liệu

1. Kiểm tra `/actuator/prometheus` có được expose và bảo vệ đúng không.
2. Kiểm tra Micrometer registry dependency và Actuator config.
3. Xem scrape target trong Prometheus còn `UP` không.
4. Kiểm tra tên metric có đổi sau version/naming convention hoặc khi chuyển từ Timer sang Observation không.
5. Kiểm tra labels mới làm filter query không match.
6. Xem listener có traffic để counter được tạo hay chưa; có thể pre-register meter nếu cần.
7. Kiểm tra pod labels và relabeling.
8. Phân biệt **missing series** với metric có giá trị 0, không tự gán mọi missing thành healthy.

## 29. Các kịch bản test cần có cho metric contract

| Kịch bản | Processed | Failed attempts | Business applied | Terminal/DLT |
|---|---|---|---|---|
| Thành công lần đầu | +1 | 0 | +1 | 0 |
| Retry lỗi 2 lần rồi thành công | +1 | +2 | +1 | 0 |
| Permanent exception vào DLT | 0 | +1 nếu listener nhận record | 0 | +1 sau recovery confirmed |
| Duplicate được suppress | +1 nếu listener return bình thường | 0 | 0; duplicate +1 | 0 |
| Deserialize fail trước listener | 0 ở listener | 0 ở listener | 0 | Theo error-handler policy |
| Database commit rồi crash trước Kafka offset | Có thể processed lại khi redelivery | Tùy | Chỉ một hiệu ứng nếu idempotent | Tùy |
| Transaction Kafka abort sau listener return | Processed có thể đã +1 | Không nhất thiết tăng | Tùy transaction ngoại Kafka | Theo rollback policy |
| Batch 100 records thành công | +100 nếu instrument theo record | 0 | Tùy số event mới | 0 |

Với unit tests có thể dùng `SimpleMeterRegistry` để kiểm tra Counter và Timer; cần integration tests với Kafka để kiểm chứng retries, deserialization, DLT, rebalance và transaction. Các kịch bản trong bài này là hướng dẫn, không phải thực thi test ở STEP 4.

## 30. Bảng kiểm soát records processed và records failed

| Điểm kiểm soát | Câu hỏi cần trả lời | Bằng chứng |
|---|---|---|
| Semantics | `processed` nghĩa listener return, business applied hay offset committed? | Metric contract và instrumentation. |
| Attempts | `failed` đếm mỗi attempt hay unique terminal records? | Retry policy và failure logs. |
| Coverage | Có bắt lỗi trước listener (deserialize/filter) không? | Error-handler instrumentation. |
| Batch | Một invocation có bao nhiêu records? | Batch listener và per-record metrics. |
| Duplicate | Redelivery có tăng processed mà không tăng business applied không? | Event ID và inbox counters. |
| Transaction | Counter tăng trước hay sau DB/Kafka commit? | Transaction boundary và commit logs. |
| Recovery | DLT metric chỉ tăng sau publish được xác nhận? | Producer send result và recoverer configuration. |
| Labels | Có nhãn cardinality cao không? | Meter series count và tag policy. |
| Export | Có thấy metric thực tế trên Actuator/Prometheus? | Endpoint và scrape status. |
| Aggregation | Query tổng hợp đúng môi trường, listener, group? | PromQL labels. |
| Performance | Xem processing duration cùng lag và throughput? | Dashboard, poll metrics. |
| Alerting | Có traffic threshold và persistence window? | Alert rules. |
| Business | Terminal outcome có chủ xử lý/replay SLA? | DLT/quarantine ticket, audit. |

**Kết luận:** Hai chỉ số **records processed** và **records failed** chỉ phản ánh đúng Spring Kafka reliability khi được định nghĩa theo một ranh giới rõ ràng. Hãy đo riêng **successful listener invocations**, **failed attempts**, **business events applied**, **duplicate suppressed** và **terminal recovery/DLT**. Dùng Micrometer counters và timers cùng Kafka client/group metrics, không nhầm listener success với offset commit hoặc exactly-once nghiệp vụ. Khi kết hợp các chỉ số với consumer lag, retry policy, partition assignment và business SLA, dashboard mới giúp phát hiện đúng sự cố, định lượng ảnh hưởng và xác nhận phục hồi an toàn.
