# Producer send latency

Trong Spring Kafka, producer có nhiệm vụ mã hóa record, gom batch và gửi dữ liệu tới Kafka broker. Một lời gọi `KafkaTemplate.send(...)` thường trả về rất nhanh vì quá trình gửi là **bất đồng bộ**. Nhưng việc method trả về không đồng nghĩa Kafka đã nhận record, đã ghi bền vững hoặc downstream consumer đã đọc được. Để vận hành hệ thống tin cậy, cần đo chính xác **producer send latency** ở các ranh giới khác nhau, tìm được nguyên nhân khi độ trễ tăng và xác định ảnh hưởng tới SLA của nghiệp vụ.

Producer send latency trong bài này là thời gian mà một record mất từ lúc ứng dụng bắt đầu gửi đến khi Kafka producer thông báo kết quả gửi, đồng thời phân biệt nó với thời gian xếp hàng trong producer, độ trễ request tới broker, thời gian commit Kafka transaction và độ trễ end-to-end đến consumer.

Bài học nằm trong chương **Monitoring và metrics** của **Spring Kafka Reliability Operations**. Nội dung sử dụng Spring Boot, `KafkaTemplate`, Kafka producer client metrics, JMX và Micrometer, kèm các runbook điều tra sự cố ở production.

## 1. Một lần send có nhiều mốc thời gian

Luồng phổ biến khi ứng dụng gọi producer:

```text
Ứng dụng                          Kafka producer                    Broker
    |                                    |                             |
 t0 | KafkaTemplate.send(key, value)    |                             |
    +----------------------------------->| serialize / chọn partition  |
    |                                    | lấy metadata / buffer        |
 t1 | <---- CompletableFuture trả về ----+                             |
    |                                    | queue / linger / batch       |
    |                                    | sender thread                |
    |                                    +----- ProduceRequest ------->|
    |                                    |                             | ghi log /
    |                                    |                             | kiểm tra acks
    |                                    |<------ ProduceResponse -----+
 t2 | <--- future hoàn tất / callback ---|                             |
    |                                                                  |
 t3 | (nếu transactional) commitTransaction() hoàn tất                  |
    |                                                                  |
 t4 | (nếu cần end-to-end) consumer downstream xử lý record             |
```

Các mốc đo có ý nghĩa khác nhau:

| Khoảng thời gian | Cách hiểu | Dùng khi nào? |
|---|---|---|
| **t1 − t0** | Thời gian gọi `send()` trước khi nhận future. Có thể gồm serialization, tìm metadata hoặc chờ buffer. | Phát hiện lời gọi send đang block application thread. |
| **t2 − t0** | Thời gian từ khi ứng dụng bắt đầu send đến khi future thành công/thất bại. | Đo producer acknowledgment/completion latency của ứng dụng. |
| **t3 − t0** | Thời gian tới khi transaction được commit, nếu dùng Kafka transactions. | Đánh giá độ trễ hoàn tất của transactional publish. |
| **t4 − t0** | Thời gian từ lúc phát đến khi downstream xử lý. | Đo độ trễ end-to-end, cần trace và timestamp rõ ràng. |

Đây là các mốc **logic**. Không phải record nào cũng dùng transaction; không phải mọi send thành công đều có cùng mức durability vì `acks` có thể khác nhau. Nếu `acks=0`, future hoàn tất không phải bằng chứng broker đã nhận record.

**Điểm cốt lõi:** khi ai đó nói “send latency tăng”, hãy hỏi đang đo **độ trễ lời gọi `send()`**, **thời gian chờ future**, **Kafka request latency**, hay **transaction commit latency**. Nếu trộn các đại lượng, nguyên nhân sẽ bị chẩn đoán sai.

## 2. KafkaTemplate.send() là bất đồng bộ

Một listener hoặc REST service có thể gửi event như sau:

```java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String orderId, String payload) {

        return kafkaTemplate.send("orders.created", orderId, payload);
    }
}
```

Trong các phiên bản Spring Kafka hiện đại (3.x), `KafkaTemplate.send(...)` trả `CompletableFuture<SendResult<K, V>>`. Future có thể hoàn tất thành công hoặc ngoại lệ, thường sau khi producer nhận kết quả theo chính sách `acks` và retry.

```java
publisher.publish(orderId, payload)
        .whenComplete((result, exception) -> {
            if (exception == null) {
                log.info(
                    "Kafka send completed: topic={}, partition={}, offset={}",
                    result.getRecordMetadata().topic(),
                    result.getRecordMetadata().partition(),
                    result.getRecordMetadata().offset());
            } else {
                log.error("Kafka send failed: orderId={}", orderId, exception);
            }
        });
```

Nếu application chỉ đo:

```java
long start = System.nanoTime();
kafkaTemplate.send("orders.created", orderId, payload);
long duration = System.nanoTime() - start;
```

thì `duration` chủ yếu phản ánh **thời gian enqueue** chứ không phải thời gian record được broker xác nhận. Một số trường hợp `send()` cũng có thể block để chờ metadata hoặc chỗ trống trong producer buffer; vì vậy thời gian enqueue không nhất thiết luôn gần bằng 0.

**Không gọi `get()` hoặc `join()` trên future trong mọi listener/request chỉ để lấy metric.** Làm như vậy có thể biến luồng bất đồng bộ thành đồng bộ, chiếm application thread và gây backpressure không mong muốn. Nếu nghiệp vụ thực sự phải chờ gửi thành công, hãy đặt timeout và thiết kế rõ quy tắc xử lý lỗi, không chặn vô hạn.

## 3. Đo send completion latency ở tầng ứng dụng

Để đo từ `t0` đến `t2`, bắt đầu timer **trước** lời gọi `KafkaTemplate.send(...)` và kết thúc khi future hoàn tất. Ví dụ dùng Micrometer:

```java
@Component
public class MeteredOrderPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final MeterRegistry registry;

    public MeteredOrderPublisher(
            KafkaTemplate<String, String> kafkaTemplate,
            MeterRegistry registry) {
        this.kafkaTemplate = kafkaTemplate;
        this.registry = registry;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String orderId, String payload) {

        Timer.Sample sample = Timer.start(registry);
        try {
            return kafkaTemplate
                    .send("orders.created", orderId, payload)
                    .whenComplete((result, failure) -> {
                        String outcome =
                                failure == null ? "success" : "failure";

                        sample.stop(registry.timer(
                                "app.kafka.producer.send.completion",
                                "topic", "orders.created",
                                "outcome", outcome));
                    });
        } catch (RuntimeException failure) {
            // Một số lỗi có thể xuất hiện trước khi nhận được future.
            sample.stop(registry.timer(
                    "app.kafka.producer.send.completion",
                    "topic", "orders.created",
                    "outcome", "failure"));
            throw failure;
        }
    }
}
```

Các import chính:

```java
import java.util.concurrent.CompletableFuture;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Component;
```

Metric `app.kafka.producer.send.completion` trong ví dụ là **metric ứng dụng tự định nghĩa**, không phải tên chuẩn bắt buộc của Kafka hoặc Spring Kafka. Nó đo khoảng thời gian từ trước khi gọi send đến khi future hoàn tất hoặc lời gọi ném exception đồng bộ.

Một số lưu ý:

- `whenComplete` có thể chạy trên producer callback thread. Callback chỉ nên ghi metric/log gọn, không gọi database hoặc API chậm.
- Khi future hoàn tất với lỗi, timer vẫn cần được ghi; nếu chỉ đo success, histogram bị thiên lệch và không phản ánh outage.
- Các trường hợp không có `MeterRegistry` bean cần bỏ phần Micrometer hoặc cấu hình dependency phù hợp.
- Không gắn `orderId`, payload hoặc event ID làm metric tag: cardinality có thể tăng vô hạn.
- `topic` và `outcome` là nhãn phù hợp nếu số topic hữu hạn; với hệ thống multi-tenant có topic động, cần kiểm soát cardinality.
- Nếu ứng dụng đã bật observation của `KafkaTemplate`, tránh instrument lặp các histogram có cùng ý nghĩa mà không phân biệt rõ mục đích.

Metric timer thường hỗ trợ count, total time và phân phối latency khi registry bật histogram hoặc percentiles. Nếu cần p95/p99 tổng hợp được giữa nhiều pod, ưu tiên histogram phù hợp với hệ thống quan sát đang dùng; client-side quantile không phải lúc nào cũng tổng hợp chính xác qua nhiều instance.

## 4. Micrometer và observation có sẵn trong Spring Kafka

Spring Kafka hỗ trợ Micrometer timers và, ở các phiên bản hiện đại, **Micrometer Observation** cho `KafkaTemplate`. Khi bật observation với một `ObservationRegistry` phù hợp, hệ thống có thể theo dõi thao tác gửi thông qua observation/timer và liên kết trace.

Ví dụ bật observation trên template khi ứng dụng tự cấu hình:

```java
@Bean
KafkaTemplate<String, String> kafkaTemplate(
        ProducerFactory<String, String> producerFactory) {

    KafkaTemplate<String, String> template =
            new KafkaTemplate<>(producerFactory);
    template.setObservationEnabled(true);
    return template;
}
```

Cấu hình ví dụ yêu cầu ứng dụng đã có Micrometer Observation/Meter Registry hoặc tracing infrastructure phù hợp. Nếu Spring Boot đã tự tạo template và tự cấu hình observation, không cần tạo bean mới chỉ để bật một cờ; hãy kiểm tra cấu hình thực tế và phiên bản đang dùng.

Tên convention thường gặp cho observation của KafkaTemplate là `spring.kafka.template`, nhưng tên meter, tag, trace span và việc bật metric/observation phụ thuộc phiên bản Spring Kafka, Spring Boot và cách registry export. Không tự suy ra một Prometheus series chính xác từ tên Java API; phải xem metric thực tế do ứng dụng xuất.

Phân biệt hai tầng:

| Nguồn đo | Mô tả | Giới hạn |
|---|---|---|
| Application timer / `KafkaTemplate` observation | Độ trễ nhìn từ code ứng dụng của thao tác send. | Không cho biết riêng queue, broker request, mạng và replica chiếm bao nhiêu. |
| Kafka producer client metrics | Thời gian/throughput ở tầng Kafka client như queue, request, retries, buffer. | Không trực tiếp đo toàn bộ nghiệp vụ HTTP → consumer downstream. |

Nên dùng cả hai tầng để **liên kết triệu chứng và nguyên nhân**, thay vì chỉ nhìn một biểu đồ latency chung.

## 5. Producer request latency không bằng send completion latency

Kafka producer phát metric qua JMX/Kafka client metrics. Một số metric quan trọng trong nhóm producer:

| Metric client thường gặp | Ý nghĩa vận hành |
|---|---|
| `request-latency-avg` / `request-latency-max` | Thời gian phản hồi trung bình/lớn nhất của request mà producer đo; không phải riêng toàn bộ thời gian một event từ `send()` tới future. |
| `record-queue-time-avg` / `record-queue-time-max` | Thời gian record chờ trong producer accumulator trước khi được gửi. |
| `record-send-rate` | Tốc độ producer gửi record; giúp hiểu tải và throughput. |
| `record-retry-rate` | Tốc độ record phải retry vì lỗi có thể thử lại. |
| `record-error-rate` | Tốc độ record gửi thất bại. |
| `batch-size-avg` / `batch-size-max` | Kích thước các batch được gửi, giúp phân tích `linger.ms` và hiệu quả batching. |
| `records-per-request-avg` | Số record trung bình trên request, một chỉ báo hiệu quả gom batch. |
| `bufferpool-wait-ratio` / `bufferpool-wait-time-total` | Mức chờ buffer, giúp phát hiện producer bị backpressure nội bộ. |
| `waiting-threads` | Số thread đang đợi cấp phát buffer tại thời điểm đo. |
| `buffer-available-bytes` | Dung lượng buffer còn khả dụng theo Kafka client. |
| `produce-throttle-time-avg` / `produce-throttle-time-max` | Thời gian producer bị broker/quota throttle, ở các client/phiên bản có metric này. |

Tên và sự hiện diện metric có thể khác giữa Kafka client versions; JMX exporter và Micrometer có thể **đổi tên hoặc chuẩn hóa dấu chấm/gạch nối**. Bảng nêu các metric Kafka client thường gặp, không cam kết mọi series đã có sẵn trên Prometheus.

Một đường đi đơn giản để hiểu sự khác biệt:

```text
KafkaTemplate.send()
       |
       +-- Metadata lookup / serializer / buffer allocation
       |
       v
Producer accumulator
       |
       +-- record-queue-time
       |
       v
Sender thread / ProduceRequest
       |
       +-- request-latency
       |     (network + broker + response theo định nghĩa client)
       |
       v
Producer callback / future completion
       |
       +-- application send completion latency
```

Với retry, một record có thể đi qua **nhiều request**, chờ nhiều lần và chịu backoff. Vì vậy không cộng máy móc `record-queue-time-avg + request-latency-avg` để kết luận chính xác latency của từng record. Hai giá trị thường là trung bình của những tập quan sát khác nhau.

## 6. Đọc Kafka client metrics qua JMX

Kafka producer xuất các metric theo Kafka `client.id`. ObjectName JMX thường có dạng:

```text
kafka.producer:type=producer-metrics,client-id=order-producer-1
```

Một số thuộc tính thường gặp trong object này:

```text
request-latency-avg
request-latency-max
record-queue-time-avg
record-retry-rate
record-error-rate
record-send-rate
bufferpool-wait-ratio
waiting-threads
```

Metric theo topic thường nằm ở nhóm `producer-topic-metrics`, với client ID và topic tương ứng. Nếu một service publish tới nhiều topic, phân tích tổng thể theo producer có thể che giấu topic đang gây tải lớn; cần kết hợp metric theo topic và context ứng dụng.

Trong Kubernetes, có thể dùng Kafka client metrics được export qua Micrometer hoặc JMX exporter theo chính sách của tổ chức. Khi cấu hình exporter, kiểm tra:

- `client.id` của Kafka producer thực tế.
- Pod/instance, namespace và service labels để phân biệt nguồn.
- Mapping tên JMX metric sang Prometheus series.
- Số lượng client ID/topic, tránh label cardinality lớn.
- Khoảng scrape và cửa sổ tính rate đủ ổn định.

**Không coi `request-latency-avg` là một histogram end-to-end p99.** Nó là metric tổng hợp client-level; muốn p95/p99 send completion, cần một histogram hoặc timer ở tầng thao tác gửi với cấu hình export phù hợp.

## 7. linger.ms, batch.size và producer queue

Kafka producer thường gom nhiều record thành batch trước khi gửi để tăng throughput và giảm overhead request.

Hai tham số quan trọng:

- `linger.ms`: khoảng thời gian tối đa producer có thể chờ để gom thêm record khi batch chưa đủ đầy.
- `batch.size`: mục tiêu kích thước bộ nhớ cho một batch theo partition, không phải giới hạn tuyệt đối kích thước một Kafka message.

Ví dụ:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[linger.ms]": 5
        "[batch.size]": 32768
```

Với throughput thấp, record có thể chờ gần mức linger trước khi sender gửi batch. Với throughput cao, batch có thể đầy trước nên không phải mọi record đều chờ đủ `linger.ms`.

```text
Record 1 đến lúc 00 ms
Record 2 đến lúc 02 ms
Record 3 đến lúc 04 ms
           |
           v
Sender gửi batch khoảng thời điểm thích hợp
           |
           v
Broker xác nhận batch
```

Tăng `linger.ms` có thể cải thiện batching và throughput nhưng làm tăng latency của record ít traffic. Giảm `linger.ms` có thể giảm queue wait cho record nhỏ lẻ nhưng tăng số request và overhead, nhất là khi throughput cao.

Khi `record-queue-time-avg` tăng, hãy xem **đồng thời** `batch-size-avg`, `records-per-request-avg`, request rate và tải broker. Không kết luận “Kafka chậm” chỉ từ producer queue time, vì queue có thể tăng do policy batching được cấu hình chủ động.

## 8. buffer.memory, max.block.ms và lời gọi send bị block

Kafka producer duy trì buffer để giữ record trước khi sender thread chuyển thành ProduceRequest. Nếu tốc độ gửi thấp hơn tốc độ ứng dụng tạo record, buffer có thể đầy.

Các tham số liên quan:

| Thuộc tính | Vai trò |
|---|---|
| `buffer.memory` | Tổng bộ nhớ gần đúng cho các record producer đang đợi được gửi; không phải toàn bộ RAM của client. |
| `max.block.ms` | Thời gian tối đa `send()` hoặc thao tác tương ứng có thể block khi thiếu metadata hoặc buffer, theo quy tắc Kafka client. |
| `batch.size` | Dung lượng mục tiêu cho batch theo partition. |
| `linger.ms` | Khoảng chờ gom thêm record trước khi gửi. |

Ví dụ khi broker phản hồi chậm:

```text
Application tạo 10.000 record/giây
      |
      v
Producer enqueue record
      |
      v
Sender chỉ gửi được 4.000 record/giây
      |
      v
Buffer sử dụng ngày càng nhiều
      |
      v
Lời gọi send() bắt đầu chờ buffer
      |
      v
Có thể gặp TimeoutException do max.block.ms
```

Ở đây, `t1 − t0` tăng vì caller phải chờ, ngay cả khi method `send()` vẫn được gọi theo cách bất đồng bộ về phần publish.

**Cần phân biệt hai timeout:** `max.block.ms` liên quan thời gian chờ trong lời gọi API (ví dụ metadata/buffer); `delivery.timeout.ms` liên quan thời gian hoàn tất việc gửi của record sau khi nó được chấp nhận. Thời gian chạy bên trong custom serializer hoặc partitioner có thể có quy tắc tính timeout khác và không được bảo đảm bởi `max.block.ms`.

Giải pháp không phải cứ tăng `buffer.memory` vô hạn. Buffer lớn hơn có thể chỉ trì hoãn thời điểm quá tải bộc lộ và làm tăng memory pressure. Cần xử lý nguyên nhân throughput giảm, hoặc áp dụng **backpressure** tại nguồn phát để giảm tốc độ gửi.

## 9. request.timeout.ms, delivery.timeout.ms và retries

Một record có thể không được xác nhận trong lần request đầu vì broker/network timeout, leader election hoặc lỗi tạm thời. Kafka producer có cơ chế retry theo cấu hình.

| Cấu hình | Ý nghĩa |
|---|---|
| `request.timeout.ms` | Thời gian tối đa client chờ phản hồi một request theo quy tắc Kafka producer. |
| `delivery.timeout.ms` | Giới hạn tổng thời gian client cố gắng hoàn tất delivery record, gồm batching, request và retry theo semantics client. |
| `retries` | Số lần client được thử lại khi lỗi thuộc nhóm retryable, tùy giới hạn delivery timeout. |
| `retry.backoff.ms` | Khoảng chờ giữa những lần retry tương ứng. |
| `acks` | Yêu cầu broker acknowledgment ở mức nào. |

Thông thường phải chọn `delivery.timeout.ms` không nhỏ hơn `request.timeout.ms + linger.ms` để tránh cấu hình không hợp lệ hoặc record hết thời gian delivery quá sớm.

Ví dụ một cấu hình minh họa:

```yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[linger.ms]": 5
        "[request.timeout.ms]": 30000
        "[delivery.timeout.ms]": 120000
        "[retry.backoff.ms]": 100
        "[enable.idempotence]": true
```

Đây **không phải cấu hình tối ưu cho mọi SLA**. Nếu ứng dụng cần phản hồi trong 200 ms, một future có thể đợi tới hàng chục giây trước khi lỗi là không phù hợp với yêu cầu end-to-end; phải lựa chọn chiến lược fail-fast, queueing, asynchronous API hoặc outbox theo nhu cầu nghiệp vụ.

Nếu `record-retry-rate` tăng cùng `request-latency-avg` và send completion p99, nghi ngờ producer đang retry nhiều request. Tìm nguyên nhân server/network/quota trước khi vội giảm retries, vì giảm retry có thể tăng failure rate và làm mất tính bền bỉ của luồng phát event nếu ứng dụng không có recovery.

## 10. acks và độ trễ durability

`acks` ảnh hưởng mức xác nhận và latency:

| `acks` | Thành công của send phản ánh gì? | Đánh đổi |
|---|---|---|
| `0` | Producer không đợi acknowledgment từ broker cho record. | Latency báo hoàn tất có thể thấp, nhưng không xác nhận broker đã ghi. |
| `1` | Leader broker xác nhận theo hành vi gửi của producer. | Có rủi ro khi leader gặp sự cố trước khi replica bắt kịp. |
| `all` | Leader đợi acknowledgment từ các replica in-sync theo chính sách Kafka. | Bền vững hơn trong cấu hình replication phù hợp, có thể tăng latency khi replica chậm. |

Với `acks=all`, cần xem `min.insync.replicas` ở broker/topic và `replication.factor`. Nếu ISR giảm dưới ngưỡng yêu cầu, producer có thể nhận lỗi thay vì tiếp tục ghi ở mức durability không được chấp nhận.

**Không giảm `acks` chỉ để làm đẹp biểu đồ latency** khi nghiệp vụ cần bảo đảm event đã được Kafka xác nhận bền vững. Thay đổi `acks` là thay đổi **delivery semantics**, không chỉ performance tuning.

Kafka idempotent producer thường là lựa chọn quan trọng để hạn chế duplicate do client retry trong những điều kiện Kafka hỗ trợ. Với transactional producer, cần phân biệt future send đã hoàn tất với **`commitTransaction()` đã hoàn tất**; send thành công trước commit không đủ chứng minh giao dịch đã được xác nhận.

## 11. Transactional producer: send latency chưa phải transaction latency

Trong Kafka transaction, một listener hoặc service có thể gửi nhiều record rồi commit:

```text
beginTransaction()
      |
      +--> send(record A) -> future A hoàn tất
      +--> send(record B) -> future B hoàn tất
      |
      v
commitTransaction()
      |
      v
Transaction thực sự committed
```

Nếu broker abort transaction hoặc commit lỗi, output không được consumer `read_committed` coi là kết quả đã commit, ngay cả khi một số `send()` future đã hoàn tất thành công trước đó.

Vì vậy, với luồng transactional cần đo tối thiểu:

- Send completion latency cho các record.
- `commitTransaction()` duration, commit/abort count.
- Transaction timeout, fencing, producer epoch errors.
- Consumer lag và downstream visibility nếu producer là một bước trong Kafka-to-Kafka pipeline.

Nếu ứng dụng dùng Spring Kafka `KafkaTransactionManager` với listener, thời gian giao dịch có thể bao gồm cả xử lý nghiệp vụ và đưa consumer offset vào transaction. Đừng đồng nhất transaction duration với `request-latency-avg` của producer.

## 12. Network, broker và quota throttling

Producer request latency có thể tăng dù CPU của application vẫn thấp. Khi nghi ngờ broker/network, nên kết hợp metric hai phía:

| Triệu chứng | Giả thuyết | Kiểm tra |
|---|---|---|
| `request-latency-avg` tăng ở nhiều producer cùng lúc | Network, broker response chậm, quota hoặc leader bottleneck. | Broker request latency, network throughput, CPU/disk và quota throttle. |
| `produce-throttle-time-avg` tăng | Client bị áp dụng throughput quota. | Kafka quotas, byte rate của client/user và broker metrics. |
| Chỉ một topic có latency bất thường | Hot partition/leader, replication hoặc batch size khác. | Topic-partition distribution, leader, ISR, record size. |
| Retry rate tăng sau broker rolling restart | Leader election, metadata refresh hoặc transient errors. | Broker logs, partition leader state, retry/error metrics. |
| Latency tăng cùng ISR biến động | Replica lag hoặc replication bottleneck. | Under-replicated partitions, ISR changes, disk/network. |
| Latency tăng nhưng broker metrics ổn | Producer buffer, DNS/TLS, serializer hoặc application thread block. | Bufferpool, send enqueue timing, thread dump, client logs. |

Nếu broker áp quota, giảm linger chưa chắc cải thiện latency; nhiều request nhỏ có thể làm tình trạng tệ hơn. Cần xem **tổng dữ liệu gửi**, số request, throttle time và chính sách capacity của cluster.

Với topic có một partition nóng, throughput producer có thể bị giới hạn bởi leader của partition đó. Thêm pod producer không tự tăng khả năng ghi vào đúng partition nóng; cần đánh giá key distribution, partition count và thứ tự nghiệp vụ.

## 13. Kích thước record, compression và serializer

Message lớn, compression mạnh hoặc serializer đắt CPU có thể làm send latency tăng ở các giai đoạn khác nhau.

- **Serializer:** chạy trong đường gọi gửi để chuyển key/value thành bytes; một serializer chậm có thể làm tăng `t1 − t0`.
- **Compression:** producer có thể tiêu tốn CPU để nén batch, nhưng giảm lượng bytes qua network và broker.
- **Record size:** record lớn làm tăng request size, buffer pressure và nguy cơ vượt `max.request.size` hoặc giới hạn message của broker/topic.
- **Batching:** batch lớn có thể tăng hiệu suất khi gửi nhiều record cùng lúc, nhưng ảnh hưởng thời gian gom và memory usage.

Ví dụ:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[compression.type]": zstd
        "[batch.size]": 65536
```

Đây là cấu hình minh họa, cần tương thích với phiên bản Kafka và khả năng CPU của producer. Không chọn compression chỉ theo tỷ lệ nén; hãy đo **producer CPU, bytes sent, queue time, request latency và send completion latency** sau thay đổi.

Nếu latency chỉ tăng khi payload rất lớn, cần điều tra phân phối size, serializer, compression CPU, request/response size và broker message limit trước khi chỉnh retry.

## 14. Ví dụ định nghĩa SLO và alert

Giả sử luồng publish `orders.created` có yêu cầu nội bộ:

```text
Trong điều kiện broker hoạt động bình thường:
  send completion p95 dưới 150 ms
  send completion p99 dưới 500 ms
  send failure rate dưới 0,1%
```

Các ngưỡng trên chỉ là **ví dụ**, không phải mặc định Kafka. Với sự kiện giao dịch tài chính, yêu cầu độ bền và ngân sách thời gian có thể khác với telemetry hoặc log không quan trọng.

Một dashboard hữu ích có thể chia:

1. **Golden signal:** p50/p95/p99 send completion latency và failure rate do ứng dụng đo.
2. **Producer internals:** `request-latency`, `record-queue-time`, buffer wait, retries, throttle và bytes/record send rate.
3. **Broker:** Produce request latency, errors, ISR, disk/network, quota throttling.
4. **Business:** request API latency, event backlog/outbox age và downstream processing lag.

Thay vì chỉ alert trên p99 trong vài giây, nên yêu cầu đủ lượng sample và một cửa sổ quan sát để tránh nhiễu khi traffic rất thấp. Khi có lỗi, latency của **những future hoàn tất thành công** có thể trông bình thường trong khi nhiều record lỗi; phải quan sát failure rate song song.

Với hệ thống transaction, thêm transaction commit/abort metrics. Nếu business event cần outbox, theo dõi **tuổi outbox record chưa publish** bên cạnh producer send latency, vì producer có thể nhanh nhưng worker đang nghẽn.

## 15. Chẩn đoán bằng ma trận triệu chứng

| Tình huống | Chỉ số thường thấy | Khả năng cao | Hướng điều tra |
|---|---|---|---|
| `send()` trả về chậm ngay tại caller | Enqueue duration, `bufferpool-wait` hoặc metadata timeout tăng. | Hết buffer, metadata lookup, serializer chậm. | Thread dump, buffer metrics, producer configs, broker metadata. |
| Future chậm, queue time cao | `record-queue-time` tăng, request latency có thể bình thường. | Linger/batching, sender không theo kịp, producer buffer backlog. | `linger.ms`, batch size, sender throughput, request rate. |
| Future chậm, request latency cao | `request-latency` tăng. | Broker/network/throttle/replication. | Broker request metrics, ISR, quota, network. |
| Future chậm, retry tăng mạnh | `record-retry-rate` và error rate tăng. | Transient produce errors, leader election, request timeout. | Client exceptions, broker events, delivery timeout. |
| p99 tăng chỉ với payload lớn | Record/request size, CPU compression tăng. | Serialization, compression hoặc network size. | Payload distribution, profiler, compression config. |
| Transaction commit chậm nhưng send future nhanh | Transaction duration tăng, send time ít đổi. | Coordinator, commit, transaction dài. | Transaction manager, timeout, producer fencing. |
| Kafka latency thấp nhưng API chậm | Kafka timer bình thường; DB/HTTP latency tăng. | Bottleneck ngoài producer. | Request trace, dependency metrics, thread pool. |
| Lag downstream tăng dù send nhanh | Producer publish ổn; consumer lag tăng. | Consumer xử lý chậm hoặc bị pause. | Group assignment, committed offset, retries/DLT. |

**Chẩn đoán theo xu hướng tương quan**, không coi một metric đơn lẻ là kết luận. Ví dụ queue time cao có thể là batching có chủ đích, còn request latency cao có thể do quota chứ không phải broker “yếu”.

## 16. Runbook: Producer send latency tăng sau deployment

Giả sử sau khi triển khai bản mới, `app.kafka.producer.send.completion` p99 tăng từ 120 ms lên 1,2 giây.

**Bước 1 — Xác định thước đo.** p99 là send-to-future hay chỉ thời gian gọi `send()`? Có thay đổi metric instrumentation hoặc histogram buckets sau deploy không?

**Bước 2 — Khoanh vùng.** Một instance, một topic hay toàn bộ application? Phân tách producer client ID, topic, region và thời điểm deployment. Kiểm tra volume để tránh kết luận từ số mẫu ít.

**Bước 3 — Đối chiếu producer internals.** Xem `record-queue-time`, `request-latency`, buffer wait, retries, errors, throttling và records-per-request. Chỉ số nào thay đổi đồng thời với p99?

**Bước 4 — So sánh cấu hình.** Bản mới có thay `linger.ms`, `batch.size`, `acks`, `compression.type`, `delivery.timeout.ms`, serializer, record size hoặc producer factory không?

**Bước 5 — Kiểm tra broker.** Có rolling restart, leader election, ISR shrink, quota, disk/network pressure hoặc broker request latency tăng cùng thời điểm không?

**Bước 6 — Đánh giá hậu quả nghiệp vụ.** Future thất bại bao nhiêu? API có timeout hoặc transaction abort? Outbox backlog tăng? Consumer lag có liên quan?

**Bước 7 — Khắc phục có kiểm soát.** Nếu do config deployment, rollback hoặc điều chỉnh có mục tiêu; nếu do capacity, giảm tốc phát và xử lý broker/quota. Không thay đồng thời quá nhiều producer parameters khiến khó quy nguyên nhân.

**Bước 8 — Xác nhận.** Send completion p95/p99 giảm, failure/retry rate ổn định, broker không còn bất thường, business backlog giảm và không phát sinh duplicate ngoài dự kiến.

Không reset consumer offsets, xóa DLT hoặc đổi `acks=0` chỉ để dashboard producer trông đẹp hơn.

## 17. Runbook: Producer buffer đầy hoặc TimeoutException

Triệu chứng: log `TimeoutException` khi `send()` chờ metadata/buffer, application thread bị block, `bufferpool-wait-ratio` tăng hoặc còn nhiều thread chờ buffer.

Quy trình:

1. Kiểm tra send enqueue duration để xác nhận application thread đang chờ **trước khi future được trả về**.
2. Kiểm tra `buffer-available-bytes`, `waiting-threads`, `bufferpool-wait-ratio` và tổng record/byte rate.
3. Kiểm tra producer request latency và broker throughput: sender chậm vì network/quota hay vì quá nhiều record?
4. Kiểm tra tăng tải bất thường, payload size, số partition hot và thay đổi batching/compression.
5. Giảm tốc từ nguồn: queue có giới hạn, rate limiting, semaphore hoặc backpressure phù hợp, tránh tạo buffer vô hạn ở tầng ứng dụng.
6. Chỉ tăng `buffer.memory` sau khi tính toán heap/native memory và xác nhận broker có khả năng xử lý lượng tải thực tế.
7. Kiểm tra code xử lý lỗi: nếu `send()` ném exception đồng bộ, không được giả định đã có future để callback xử lý.
8. Sau phục hồi, theo dõi buffer pressure giảm, send latency trở lại và tỷ lệ lỗi được giải quyết.

**Không retry send trong vòng lặp nóng vô hạn** khi buffer đang đầy; mỗi vòng mới lại tranh tài nguyên và có thể gây hiệu ứng khuếch đại tải.

## 18. Runbook: request latency tăng do broker hoặc quota

Nếu `request-latency-avg` tăng trên nhiều producer cùng thời điểm:

1. Kiểm tra Produce request latency trên broker, request handler idle, disk I/O và network.
2. Xem quota/throttle theo client/user; `produce-throttle-time` có tăng không?
3. Kiểm tra leader/ISR của partition nóng, under-replicated partitions và leader election gần thời điểm lỗi.
4. Đối chiếu producer retry/errors; nếu có `NotEnoughReplicas` hoặc lỗi leader, không vội tăng buffer.
5. Kiểm tra client có đặt `acks=all`, min ISR và replication factor đáp ứng yêu cầu không.
6. Giảm peak publish rate hoặc cải thiện capacity/quota theo quy trình vận hành được phép.
7. Theo dõi broker metrics và producer completion latency cùng hồi phục.

Một Kafka cluster khỏe trong dashboard tổng thể vẫn có thể có **một leader partition** bị nóng. Khi đó cần drill down theo topic/partition, key distribution và broker leader placement.

## 19. Những lỗi hiểu sai thường gặp

| Hiểu sai | Diễn giải đúng |
|---|---|
| “`KafkaTemplate.send()` trả về nhanh nên broker xác nhận nhanh.” | Method thường trả future bất đồng bộ; phải đo tới future completion. |
| “`request-latency-avg` là end-to-end latency từ ứng dụng đến consumer.” | Đây là Kafka producer client metric cho request, không bao gồm toàn luồng nghiệp vụ. |
| “Tăng `linger.ms` luôn làm latency cao hơn tương ứng.” | Batch có thể đầy trước linger; cần xem throughput và queue time thực tế. |
| “Tăng `buffer.memory` là giải pháp vĩnh viễn khi producer chậm.” | Chỉ tăng sức chứa tạm; nếu input > output lâu dài, buffer lại đầy. |
| “Future thành công nghĩa transaction đã commit.” | Với transactional producer, send result khác transaction commit. |
| “`acks=0` là cách tối ưu an toàn cho event quan trọng.” | Nó bỏ acknowledgment broker, thay đổi rõ rệt độ tin cậy. |
| “Latency thấp chứng minh không mất dữ liệu.” | Cần xem send failures, transaction, durability, DLT/outbox và downstream. |
| “Record retry là duplicate nghiệp vụ.” | Client idempotence giải quyết một số duplicate do retry; application replay cần idempotency riêng. |
| “Kafka client metrics có sẵn đúng tên Prometheus ở mọi cluster.” | Exporter/registry có thể đổi tên và danh sách metric khác theo phiên bản. |
| “Tắt retry sẽ khắc phục gốc rễ.” | Có thể làm future lỗi nhanh hơn nhưng không sửa broker/network và có thể tăng event loss nếu thiếu recovery. |

## 20. Checklist trước khi triển khai thay đổi

- [ ] Định nghĩa rõ send latency đang đo: enqueue, future completion, transaction commit hay end-to-end.
- [ ] Có timer/histogram hoặc observation đo cả success và failure, không chỉ log thời gian `send()` trả về.
- [ ] Có Kafka client metrics cho queue, request, buffer, retry, error và throttling.
- [ ] Metric tags có cardinality kiểm soát; không gắn key, event ID, payload hoặc tenant động vào mọi series.
- [ ] Biết `client.id` và producer factory thực tế của application, tránh nhìn nhầm metric producer khác.
- [ ] Cấu hình `acks`, idempotence, delivery timeout và retries khớp delivery guarantee của nghiệp vụ.
- [ ] Hiểu đánh đổi giữa `linger.ms`, `batch.size`, compression, throughput và latency.
- [ ] Có backpressure khi producer buffer/broker throughput không theo kịp application.
- [ ] Với Kafka transactions, đo commit/abort riêng, không coi send future là committed output.
- [ ] Có alert cho p95/p99 đi kèm failure rate và số lượng sample đủ đáng tin.
- [ ] Có runbook phân biệt broker/network, producer queue và application serialization.
- [ ] Thử nghiệm tăng tải, broker chậm, quota, send timeout và shutdown/restart trong môi trường cô lập.

## 21. Kết luận

**Producer send latency** là một tập hợp nhiều độ trễ, không phải một con số duy nhất. Với Spring Kafka, `KafkaTemplate.send()` thường chỉ đưa record vào producer và trả về future; độ trễ hoàn tất cần được đo khi future success/failure, còn việc commit Kafka transaction và downstream xử lý là các mốc riêng.

Để vận hành tin cậy, hãy kết hợp **application send completion timer**, **Kafka producer queue/request/buffer/retry metrics**, và **broker/quota metrics**. Cách quan sát nhiều tầng này giúp phân biệt vấn đề batching, buffer đầy, metadata lookup, network, ISR và transaction commit. Khi tối ưu, bảo toàn `acks`, idempotency và chính sách xử lý lỗi phù hợp; không đánh đổi độ tin cậy nghiệp vụ chỉ để giảm một chỉ số latency trên dashboard.
