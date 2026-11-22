# Phân biệt metric, log và trace

Trong một hệ thống Spring Kafka, listener có thể vẫn đang chạy nhưng consumer lag tăng, một record có thể bị retry nhiều lần trước khi vào Dead Letter Topic (DLT), hoặc việc xử lý có thể bị chậm do database dù Kafka broker vẫn khỏe. Để hiểu những tình huống đó, chỉ nhìn một dòng log hoặc một biểu đồ throughput thường không đủ.

Ba tín hiệu observability cơ bản là **metric**, **log** và **trace**. Chúng mô tả hệ thống dưới ba góc độ khác nhau:

- **Metric**: Có bao nhiêu sự kiện, tốc độ hoặc tỷ lệ thay đổi thế nào, độ trễ phân bố ra sao?
- **Log**: Ở một thời điểm cụ thể, thành phần nào đã làm gì, với record nào và kết quả gì?
- **Trace**: Một operation đi qua các thành phần nào, bước nào chậm hoặc thất bại, các bước liên hệ ra sao?

Trong chương **Observation và tracing** của module **Spring Kafka Reliability Operations**, trọng tâm là phân biệt ba tín hiệu theo **mục đích, phạm vi, độ chính xác của kết luận và chi phí**, sau đó phối hợp chúng để điều tra retry, rebalance, consumer lag, DLT, Kafka transactions và tác dụng phụ ở database.

**Nguyên tắc xuyên suốt:** metric/log/trace giúp quan sát và chẩn đoán; chúng không thay thế broker committed offset, kết quả Kafka transaction hoặc database state khi cần chứng minh dữ liệu đã được xử lý bền vững.

## 1. Một sự cố Kafka nhìn từ ba tín hiệu

Giả sử service `payment-worker` consume `payments.authorized`, cập nhật PostgreSQL rồi publish `payments.settled`:

~~~text
Payment API
     |
     v
payments.authorized (Kafka)
     |
     v
Spring Kafka payment-worker
     |
     +---- PostgreSQL
     |
     +---- payments.settled (Kafka)
~~~

Sau khi triển khai phiên bản mới, consumer lag tăng. Đội vận hành muốn trả lời:

1. Lag bắt đầu tăng lúc nào, trên những partition nào?
2. Những record nào bị retry, exception có phải từ database không?
3. Thời gian xử lý bị tiêu tốn ở Kafka poll, validation, chờ connection pool, SQL hay producer send?
4. Kafka output và input offset đã commit chưa?
5. Có record nào vào DLT và có thất bại khi publish DLT không?

| Câu hỏi | Tín hiệu phù hợp nhất | Tín hiệu bổ trợ |
|---|---|---|
| Lag tăng từ khi nào và mức độ bao nhiêu? | **Metric** | Log mốc deployment/rebalance |
| Partition nào chậm? | **Metric** lag/throughput per partition | Log topic-partition-offset |
| Record cụ thể nào ném exception? | **Structured log** | Trace nếu được lấy mẫu |
| DB hay Kafka send chậm? | **Trace** có spans theo bước | Timer metrics, duration logs |
| Tỷ lệ lỗi tăng bao nhiêu? | **Metric** counter/rate | Logs theo nhóm lỗi |
| Recovery chọn retry hay DLT? | **Log** ghi quyết định | Counter retries/DLT |
| Kafka transaction đã commit? | Trạng thái Kafka thực tế và commit result | Commit log/metric/trace đúng boundary |

Một quy trình điều tra hiệu quả thường bắt đầu bằng **metric phát hiện vấn đề**, chuyển sang **log để tìm record/exception cụ thể**, rồi dùng **trace để xem đường đi và nguyên nhân độ trễ**.

## 2. Metric: phép đo có thể tổng hợp theo thời gian

**Metric** là số đo hoặc phân phối số đo, thường xuất hiện dưới dạng time series với các nhãn như `service`, `topic`, `listener`, `outcome` và `error_category`.

Các loại metric thường gặp:

| Loại | Ý nghĩa | Ví dụ trong Spring Kafka |
|---|---|---|
| **Counter** | Tổng số lần một sự kiện xảy ra, chỉ tăng trong vòng đời meter | Listener attempts, errors, retries, DLT publish failures |
| **Gauge** | Giá trị quan sát tại một thời điểm, có thể tăng/giảm | Outbox pending count, connection pool active |
| **Timer** | Thời gian chạy và số lượng mẫu; có thể xuất histogram | Listener processing duration, DB call duration |
| **Distribution summary** | Phân phối độ lớn, không nhất thiết là thời gian | Payload size, batch size |
| **Long-task timer** | Số lượng và thời gian của các thao tác dài còn đang chạy | Công việc kéo dài được instrument riêng |

Ví dụ minh họa (không phải tên metric mặc định bắt buộc của Spring Kafka):

~~~text
app_kafka_listener_attempts_total{
  service="payment-worker",
  listener="payment-authorized",
  outcome="failed"
}

app_kafka_listener_duration_seconds_bucket{
  service="payment-worker",
  listener="payment-authorized",
  le="0.25"
}
~~~

Metric phù hợp với dashboard, alert, capacity planning và Service Level Objectives (SLO) vì có thể tổng hợp trên nhiều instances trong thời gian dài.

### 2.1. Metric phát hiện xu hướng, không mô tả toàn bộ nguyên nhân

`consumer_lag=50000` cho thấy tồn đọng lớn theo định nghĩa metric đang dùng, nhưng không tự giải thích vì sao. Các khả năng gồm:

- Producer đột ngột tăng throughput.
- Database query chậm hoặc hết connection pool.
- Listener retry mãi một poison record.
- Container bị pause.
- Consumer group rebalance liên tục.
- Deserializer gặp nhiều exception.
- Commit offset thất bại hoặc transactional producer bị fence.

Muốn tìm root cause, phải đối chiếu thêm processing latency, producer rate, error metrics, log và trace.

### 2.2. Counter và rate là hai cách đọc khác nhau

Counter là số tích lũy trong vòng đời process; sau restart nó có thể quay về 0. Với Prometheus, thường xem `rate()` hoặc `increase()` theo cửa sổ thời gian hơn là so giá trị raw counter giữa các Pods.

Ví dụ PromQL ý tưởng:

~~~promql
sum by (service, listener) (
  rate(app_kafka_listener_attempts_total{outcome="failed"}[5m])
)
~~~

Tên metric phụ thuộc exporter và cách đặt meter thực tế. Một mẫu có 1 failure trên 1 attempt không có ý nghĩa vận hành giống 10.000 failures trên 10.000 attempts; cần kết hợp **tỷ lệ, volume và thời gian kéo dài**.

### 2.3. Metric tags phải kiểm soát cardinality

Một time series thường ứng với một tổ hợp label values. Đưa `eventId`, `orderId`, `offset`, full exception message hoặc trace ID vào tags có thể tạo hàng triệu series.

**Nên dùng:**

~~~text
service=payment-worker
topic=payments.authorized
outcome=failed
error_category=database_timeout
environment=production
~~~

**Không nên dùng làm metric tags:**

~~~text
payment_id=P-92837283
event_id=c8f6...
offset=98126812
trace_id=24ac...
exception_message="account 1234 unavailable..."
~~~

Các giá trị nhận diện từng event phù hợp hơn với log hoặc trace attributes được kiểm soát. Những labels khác như `partition` cũng cần cân nhắc tổng số partition: hữu ích cho drill-down nhưng có thể tăng số series lớn ở cluster nhiều topics/partitions.

## 3. Log: bằng chứng sự kiện cụ thể

**Log** là bản ghi về một sự kiện hoặc quyết định xảy ra trong quá trình chạy chương trình. Log thường có thời gian, severity, message, exception và các trường ngữ cảnh.

Ví dụ structured log do ứng dụng tạo:

~~~json
{
  "timestamp": "2026-11-15T10:14:23.551Z",
  "level": "ERROR",
  "service": "payment-worker",
  "listener": "payments-authorized",
  "eventId": "evt-58f3",
  "topic": "payments.authorized",
  "partition": 4,
  "offset": 18233,
  "attempt": 3,
  "errorCategory": "database_timeout",
  "action": "retry",
  "traceId": "7d4e3f3f988b45b7b768b729e73be102",
  "message": "Payment processing failed; retry scheduled"
}
~~~

Một log như vậy trả lời chính xác **record nào, ở đâu, bị lỗi gì và ứng dụng đã quyết định gì**. Nếu người vận hành chỉ thấy `ERROR Failed!`, việc tìm nguyên nhân và phân biệt các record rất khó.

### 3.1. Log nên ghi sự kiện, không ghi điều chưa được xác nhận

So sánh:

~~~text
Sai: "Kafka publish SUCCESS"
      ngay sau KafkaTemplate.send() khi future chưa hoàn tất

Rõ hơn:
  kafka.send.submitted
  kafka.send.acknowledged
  kafka.transaction.committed
~~~

Một send future thành công không đồng nghĩa Kafka transaction đã commit; trong transaction, output có thể được ack nhưng cuối cùng abort. Tương tự, `repository.save()` hoặc SQL `UPDATE` không chứng minh database đã commit.

Các tên sự kiện nên phản ánh **đúng commit boundary**. Khi dùng database và Kafka đồng thời, log cần phân biệt `db.tx.committed`, `kafka.tx.committed`, `kafka.tx.failed` và `commit.outcome.unknown` nếu mất xác nhận tại một bước.

### 3.2. Structured logs hỗ trợ correlation

Các trường hữu ích cho một Kafka listener:

- `service`, `instance`, `listenerId`, `consumerGroup`.
- `topic`, `partition`, `offset`.
- `eventId`, `correlationId` và key nghiệp vụ khi không nhạy cảm.
- `traceId`, `spanId` nếu có tracing context.
- `retryAttempt`, `retryTopic`, `dltTopic`.
- `errorCategory`, `action`, `durationMs`.

Không log toàn bộ payload mặc định, nhất là thông tin cá nhân, bí mật, thẻ thanh toán hay authentication tokens. Dùng masking/redaction và retention policy.

### 3.3. Log nhiều lần không phải xử lý nhiều business events

Một record có thể được listener thực thi nhiều lần do retry, rollback hoặc redelivery. Log “received event E” có thể xuất hiện năm lần dù business effect cuối cùng chỉ được commit một lần.

Vì thế, metric `listener.attempts`, log theo `eventId + attempt`, và bằng chứng durable business state cần được đọc cùng nhau. Đừng dùng số dòng log `received` làm số thanh toán đã xử lý xong.

## 4. Trace: đường đi và mối liên hệ giữa các bước

**Distributed trace** mô tả một operation qua nhiều thành phần và service. Trace gồm các **spans**, mỗi span có thời điểm bắt đầu/kết thúc, tên operation, attributes, status và có thể chứa events hoặc links.

Sơ đồ khái niệm:

~~~text
HTTP POST /payments
   |
   +-- validate request                        5ms
   +-- DB insert                              18ms
   +-- Kafka produce payments.authorized      12ms

Kafka consume payments.authorized
   |
   +-- decode/validate                         4ms
   +-- paymentService.apply                    8ms
   +-- PostgreSQL update                     620ms
   +-- Kafka produce payments.settled          20ms
~~~

Trace giúp trả lời “bước nào mất 620ms?” và “lỗi xuất hiện trước hay sau DB call?”. Nó đặc biệt hữu ích với workflow trải qua producer, Kafka topic, consumer, HTTP dependency, database và nhiều service.

Kafka là **ranh giới bất đồng bộ**. Producer và consumer có thể ở khác process và chạy cách nhau rất lâu. Tùy instrumentation và propagation, consumer span có thể là child của propagated context, một trace mới được liên kết bằng span links, hoặc không có correlation nếu propagation thất bại. Không mặc định mọi record đều thuộc một cây spans hoàn chỉnh.

### 4.1. Trace ID, span ID, event ID và offset không giống nhau

| Định danh | Vai trò | Khi retry/replay |
|---|---|---|
| `traceId` | Nhóm spans của một trace | Có thể thay đổi giữa attempts hoặc sau replay |
| `spanId` | Một operation cụ thể trong trace | Thay đổi ở mỗi span |
| `eventId` | Định danh business event do ứng dụng cấp | Nên giữ ổn định qua retry/DLT/replay |
| `correlationId` | Liên kết nhiều công việc cùng một workflow | Có thể sống lâu hơn một trace |
| `topic-partition-offset` | Vị trí record trong một Kafka topic | Thay đổi khi chuyển sang topic mới |

**Không dùng trace ID làm idempotency key**. Cùng một business event có thể được xử lý lại sau một ngày bằng một trace mới. Sử dụng event ID/khóa nghiệp vụ ổn định cho chống trùng, và trace ID để điều tra một lần thực thi.

### 4.2. Trace có thể bị sampling

Hệ thống thường không giữ trace cho 100% Kafka records khi throughput cao. Khi trace bị sampling, việc không tìm được trace của event cụ thể không chứng minh event đó không chạy.

Để đếm tỷ lệ lỗi hoặc tính SLO chính xác toàn traffic, ưu tiên metric. Để audit tất cả hoạt động nhạy cảm, cần audit log/ledger bền vững riêng; trace backend có sampling và retention nên không đáp ứng thay thế mặc định.

## 5. Bảng so sánh metric, log và trace

| Tiêu chí | Metric | Log | Trace |
|---|---|---|---|
| Đơn vị | Giá trị số/phân phối theo thời gian | Một sự kiện/decision | Một operation gồm spans |
| Mạnh nhất | Xu hướng, SLO, alerting | Forensics và chi tiết record | Đường đi và latency breakdown |
| Chi phí điển hình | Thấp nếu labels hợp lý | Tăng theo log volume/indexing | Tăng theo span volume/sampling |
| Định danh record riêng lẻ | Không phù hợp làm label | Rất phù hợp | Khi trace được ghi |
| Dùng tìm lỗi cụ thể | Định hướng, phân nhóm | Exception và hoàn cảnh | Liên hệ nguyên nhân và bước lỗi |
| Dùng đo throughput | Rất phù hợp | Khó và đắt để tổng hợp | Không đủ khi sampled |
| Dùng đo p95 latency | Timer histogram | Duration logs có thể hỗ trợ | Xem lý do của vài execution chậm |
| Bảo đảm durability | Không | Không | Không |

Không đặt ba loại telemetry vào vị trí của transaction log hay database. Chúng là **quan sát**, không phải hệ thống ghi nhận sự thật nghiệp vụ cuối cùng.

## 6. Kết hợp ba tín hiệu theo workflow Kafka

Một mô hình correlation:

~~~text
HTTP request
     |
     v
KafkaTemplate producer
     |
     +---- eventId, correlationId
     +---- tracing propagation headers (nếu enabled)
     v
Kafka topic
     |
     v
@KafkaListener
     |
     +---- metric: invocation, duration, outcome
     +---- log: eventId, topic, partition, offset, exception
     +---- trace: consumer span và business spans
     |
     +---- DB / HTTP dependency
     |
     +---- Kafka output hoặc retry/DLT
~~~

Thiết kế cần phân biệt hai nhóm metadata:

1. **Business correlation:** `eventId` và `correlationId`, được quản lý để chịu được retry và replay.
2. **Execution correlation:** `traceId`, `spanId`, span links, mô tả một lần hoặc một chuỗi lần thực thi.

Kafka headers có thể mang context truyền qua các service. Tuy nhiên, việc tự động inject/extract cần có instrumentation phù hợp; chỉ dùng KafkaTemplate và @KafkaListener không mặc nhiên tạo distributed trace có thể truy vấn.

## 7. Micrometer Metrics và Micrometer Observation

Trong Spring Boot/Spring Kafka, **Micrometer Metrics** cung cấp Counter, Timer, Gauge và meter registry. **Micrometer Observation** cho phép instrument một operation thông qua `ObservationRegistry`; các handlers được cấu hình có thể chuyển observation thành metric và tracing span.

~~~text
Spring Kafka listener / KafkaTemplate
              |
              v
       Micrometer Observation
              |
        +-----+------+
        |            |
        v            v
  Metrics handler  Tracing handler
        |            |
        v            v
  MeterRegistry    Tracer/exporter
        |            |
        v            v
  Prometheus       OTLP/Zipkin/etc.
~~~

**Observation là API instrumentation**, không phải một loại dữ liệu lưu trữ thứ tư. Có ObservationRegistry nhưng thiếu tracer/bridge thì ứng dụng có thể có metrics mà không có exported traces. Ngược lại, cấu hình tracing không có nghĩa mọi metric Kafka client đều được xuất tự động.

Micrometer Observation còn phân biệt:

- **Low-cardinality key-values:** phù hợp làm metric labels, cần số giá trị hữu hạn.
- **High-cardinality key-values:** có thể phù hợp cho tracing metadata, nhưng phải bảo vệ dữ liệu nhạy cảm và chi phí.

Không gắn `eventId`, payload hoặc exception message vào low-cardinality tags.

## 8. Bật Observation cho listener và KafkaTemplate

Các phiên bản Spring Kafka hỗ trợ observation cho listener container:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>
        paymentListenerFactory(
                ConsumerFactory<String, PaymentEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setObservationEnabled(true);

    return factory;
}
~~~

Với KafkaTemplate ở những phiên bản hỗ trợ:

~~~java
@Bean
KafkaTemplate<String, PaymentEvent> paymentTemplate(
        ProducerFactory<String, PaymentEvent> producerFactory) {

    var template = new KafkaTemplate<>(producerFactory);
    template.setObservationEnabled(true);
    return template;
}
~~~

Để có **distributed tracing**, ứng dụng còn cần Micrometer Tracing bridge (ví dụ OpenTelemetry hoặc Brave), propagation configuration và exporter/backend phù hợp.

Lưu ý khi vận hành:

- Xác định custom listener factory nào thực sự được @KafkaListener dùng.
- Xác định KafkaTemplate nào đang publish main/retry/DLT topics.
- Xác nhận cả producer lẫn consumer có propagation nếu muốn nối trace xuyên Kafka.
- Không mặc định auto-configuration của một phiên bản Spring Boot áp dụng y hệt cho custom beans.
- Kiểm tra headers và spans bằng test thay vì chỉ thấy dependency tracing trong build.

### 8.1. Observation không đồng nghĩa transaction commit

KafkaTemplate send observation có thể kết thúc khi producer send hoàn tất; nếu send nằm trong Kafka transaction thì transaction có thể commit/abort sau đó. Listener observation cũng có thể kết thúc trước offset commit của container.

Nếu muốn metric/log phản ánh **Kafka transaction committed**, phải instrument đúng transaction completion. Nếu muốn **database committed**, cần quan sát database transaction tương ứng. Không đổi tên listener method success thành “exactly once achieved”.

## 9. Tạo custom Timer cho nghiệp vụ

Kafka client metrics không tự biết “payment đã được áp dụng chính xác trong database”. Ứng dụng có thể instrument business operation:

~~~java
@Component
public class PaymentProcessor {

    private final PaymentService service;
    private final MeterRegistry registry;

    public PaymentProcessor(
            PaymentService service,
            MeterRegistry registry) {
        this.service = service;
        this.registry = registry;
    }

    public void process(PaymentEvent event) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            service.apply(event);
        } catch (RuntimeException exception) {
            outcome = "failure";
            throw exception;
        } finally {
            sample.stop(registry.timer(
                    "app.payment.processing.duration",
                    "outcome", outcome));
            registry.counter(
                    "app.payment.processing.attempts",
                    "outcome", outcome).increment();
        }
    }
}
~~~

Đoạn code đo **attempt của method**. Nếu database transaction commit sau khi method trả về, hoặc Kafka transaction commit ở container bên ngoài, một attempt “success” không đồng nghĩa mọi resource đã commit.

Muốn metric thể hiện durable business success, thiết kế điểm đo theo business commit boundary, đồng thời tách tên như `processing.attempt.success`, `db.commit.success` và `kafka.transaction.commit.success`.

### 9.1. Không double count khi framework đã instrument

Khi listener container đã có observation, một custom Timer bao quanh đúng toàn bộ listener method có thể trùng ý nghĩa với framework timer. Nên dùng:

- Framework observation cho listener invocation và KafkaTemplate send.
- Custom observation cho bước business khác biệt (validation, DB update, HTTP call).
- Custom counter cho business outcome/reconciliation mà framework không biết.
- Kafka client/broker metrics cho fetch, poll, retry requests và throughput.

## 10. Tạo custom Observation cho một bước xử lý

Ví dụ instrument validation:

~~~java
@Component
public class PaymentValidator {

    private final ObservationRegistry registry;

    public PaymentValidator(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void validate(PaymentEvent event) {
        Observation observation =
                Observation.start("payment.validate", registry);

        observation.lowCardinalityKeyValue(
                "operation", "payment-validation");

        try (Observation.Scope scope = observation.openScope()) {
            validateFields(event);
        } catch (RuntimeException exception) {
            observation.error(exception);
            throw exception;
        } finally {
            observation.stop();
        }
    }
}
~~~

Imports:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
~~~

Với handlers phù hợp, operation này đóng góp metric về duration và một span cho validation. Nếu muốn trace chứa một thuộc tính liên quan tới event, cân nhắc high-cardinality attribute đã được kiểm soát và không chứa PII; **không** biến event ID thành metric tag.

## 11. Structured logging trong @KafkaListener

Một record listener có thể ghi context an toàn:

~~~java
@KafkaListener(
        id = "payment-listener",
        topics = "payments.authorized",
        groupId = "payment-worker")
public void handle(ConsumerRecord<String, PaymentEvent> record) {
    PaymentEvent event = record.value();

    log.info(
            "Payment received eventId={} topic={} partition={} offset={}",
            event.eventId(),
            record.topic(),
            record.partition(),
            record.offset());

    paymentService.apply(event);
}
~~~

Với structured JSON logging, các trường này trở thành keys thay vì chuỗi cần parse. Nếu tracing stack đưa `traceId` và `spanId` vào MDC, log có thể liên kết trực tiếp tới trace.

Tuy nhiên, MDC thường dùng thread-local context. Nếu listener chuyển công việc sang executor, future hoặc callback chạy thread khác, cần context propagation thích hợp; nếu không, log có thể **mất trace ID** hoặc thậm chí gán nhầm context cũ do thread được tái sử dụng.

Không tự gọi KafkaConsumer methods từ worker threads chỉ để bổ sung logs/traces. KafkaConsumer không thread-safe cho các thao tác thông thường; ack và commit phải tuân theo framework semantics.

## 12. Correlation qua Kafka headers

Một producer có thể gắn tracing context trong Kafka headers theo propagator được cấu hình (ví dụ W3C Trace Context). Consumer extract context khi nhận record:

~~~text
HTTP request / Producer span
            |
            v
Kafka record headers:
   traceparent / tracestate (nếu enabled)
   business eventId
            |
            v
Kafka consumer:
   extract context
   create consumer observation/span
   business log có eventId và traceId
~~~

Không tự giả định tracing headers luôn được bảo toàn qua custom producer, retry topics hoặc DLT. Cần test từng loại publisher/recoverer.

Cũng cần phân biệt:

- **Tracing propagation headers** có thể thay đổi theo operation/attempt.
- **Business correlation headers** nên được bảo toàn qua retry/replay theo contract.
- **DLT error headers** có thể tăng kích thước record qua nhiều hops.
- **Sensitive headers** không nên được sao chép hoặc xuất ra telemetry một cách mù quáng.

Kafka record có thể ở trong topic hàng giờ. Tracing spans chỉ thể hiện công việc đã instrument; thời gian record nằm chờ không tự xuất hiện như một synchronous child span kéo dài hàng giờ.

## 13. Retry và DLT: ba tín hiệu nên mô tả gì?

Một poison record có thể trải qua:

~~~text
orders.created offset 481
      |
      +---- listener attempt 1 -> DB timeout
      |
      +---- listener attempt 2 -> DB timeout
      |
      +---- listener attempt 3 -> validation failure
      |
      v
DeadLetterPublishingRecoverer
      |
      +---- DLT publish ack / failure / unknown
      |
      v
orders.created.DLT
~~~

| Giai đoạn | Metric | Log | Trace |
|---|---|---|---|
| Listener attempts | Retry/error counters | Event ID, attempt, exception | Attempt span nếu sampled |
| Backoff | Retry duration/count | Quyết định backoff | Span/event nếu đã instrument |
| DLT publishing | Attempts, acked, failed, unknown | Source offset, destination, publish error | Producer span nếu sampled |
| Recovery transaction | Commit/abort metrics | Commit outcome, fencing details | Transaction span nếu có |
| DLT triage/replay | Unresolved age, replay count | Event ID, action, operator | Trace mới hoặc linked trace |

**DLT publish success không phải business success.** Một record đã gửi tới DLT vẫn chưa được nghiệp vụ xử lý đúng. Metric nên phân biệt `dlt.publish.acked`, `dlt.tx.committed`, `dlt.consumed` và `dlt.resolved` nếu workflow có các giai đoạn này.

### 13.1. Chống nhầm lẫn khi retry tạo nhiều traces

Một business event có thể được retry trong cùng container rồi được publish sang retry topic sau vài phút. Tracing backend có thể lưu nhiều traces hoặc không giữ được trace ban đầu do retention.

Do đó, với incident cần tra cứu lâu dài, sử dụng **event ID** cùng **original topic-partition-offset** làm correlation chính. Trace ID dùng để hiểu một execution path đã được instrument, không phải khóa duy nhất của bản ghi nghiệp vụ.

## 14. Transactional listener và các ranh giới cần đo

Trong một Kafka transactional listener:

~~~text
Kafka consumer nhận record
       |
       v
Kafka transaction begin
       |
       +---- listener processing
       +---- KafkaTemplate.send(output)
       +---- input offset đưa vào transaction
       |
       v
Kafka transaction COMMIT hoặc ABORT
~~~

Cần phân biệt:

1. **Method duration**: thời gian listener chạy.
2. **Send acknowledgment**: broker ack cho output record.
3. **Kafka transaction commit**: output và input offset trong Kafka transaction đã commit.
4. **Database transaction commit**: DB state đã commit riêng, nếu listener ghi DB.

Nếu method trả về không lỗi nhưng Kafka transaction commit thất bại, metric `listener_method_success` không nên được hiểu là `kafka_tx_commit_success`. Nếu DB commit rồi Kafka rollback, input có thể redelivery và business DB cần idempotency.

Log và trace giúp điều tra, nhưng **không** làm Kafka transaction và database transaction trở thành XA transaction. Khi yêu cầu bảo đảm event DB không thất lạc, cân nhắc transactional outbox/inbox và reconciliation.

## 15. Consumer lag và latency: đo đúng đối tượng

Lag thường liên quan chênh lệch giữa log end offset và committed group offset hoặc vị trí consumer theo nguồn metric cụ thể.

~~~text
Partition p0:
  log end offset:          30,000
  committed group offset:  27,000
  lag theo committed:       3,000 records
~~~

Lag không phải latency tuyệt đối và không nói vì sao record tồn đọng. Để tìm nguyên nhân, kết hợp:

- Incoming records/sec và consumed records/sec.
- Processing p95/p99.
- Database connection wait và query latency.
- Listener error/retry rate.
- Rebalance count/duration.
- Pause state và offset commit errors.

Ngoài ra cần tách bốn loại latency:

| Loại latency | Từ đâu tới đâu? | Vai trò |
|---|---|---|
| Producer send latency | Submit send → broker ack | Hiệu năng producer/broker |
| Queueing delay | Record publish/create → bắt đầu consume | Thời gian record chờ trong Kafka |
| Listener processing | Listener start → return/throw | Hiệu năng logic listener |
| End-to-end business | Event được tạo → trạng thái nghiệp vụ durable | SLO thực tế |

Một trace listener dài 200ms không có nghĩa event chỉ mất 200ms từ khi producer phát; nó có thể nằm trong topic 15 phút trước đó. Cần timestamp nguồn đáng tin cậy và đồng hồ được đồng bộ nếu đo end-to-end.

## 16. Trace sampling và retention

Ghi trace 100% ở 100.000 messages/giây có thể rất tốn storage. Các chiến lược thường gặp:

- **Head sampling:** quyết định khi trace bắt đầu.
- **Tail sampling:** collector chọn trace sau khi thấy đủ thông tin như lỗi hoặc duration.
- **Priority sampling:** ưu tiên giữ trace lỗi/chậm nếu stack hỗ trợ.
- **Per-service sampling:** điều chỉnh theo throughput và chi phí.

Hệ quả:

- Có log mà không có trace là bình thường nếu tracing sampled.
- Không dùng tổng số sampled spans để tính tỷ lệ lỗi toàn hệ thống.
- Producer và consumer có thể được sample khác nhau, khiến trace thiếu spans.
- Record DLT được replay sau nhiều ngày có thể không còn trace gốc.
- Trace attributes chứa PII vẫn là rủi ro dù tỷ lệ sampling thấp.

Metric đáp ứng thống kê SLO/alert, còn logs và sampled traces hỗ trợ đi sâu khi xảy ra sự cố.

## 17. Chi phí lưu trữ và bảo mật telemetry

| Tín hiệu | Chi phí chính | Rủi ro cần kiểm soát |
|---|---|---|
| Metric | Số time series do tags | Cardinality explosion, sensitive labels |
| Log | Khối lượng lưu và indexing | Payload/headers/PII, log storm, retention |
| Trace | Số spans và attributes | High-cardinality data, SQL/URL secrets, sampling |

Quy tắc production:

1. Không log nguyên payload của record mặc định.
2. Không đưa access tokens, password hoặc dữ liệu cá nhân vào tracing baggage.
3. Không dùng event ID làm low-cardinality metric tag.
4. Giới hạn kích thước Kafka tracing/baggage headers.
5. Ghi exception ở mức cần thiết, có redaction.
6. Thiết lập retention và quyền truy cập theo độ nhạy từng loại telemetry.
7. Dùng structured logs để truy vấn event ID; dùng metrics để thống kê tổng.
8. Tracing exporter không được chặn listener vô thời hạn khi backend quan sát gặp sự cố.

Một hệ thống quan sát bị lỗi không nên tự làm Kafka processing mất an toàn hoặc biến telemetry endpoint thành dependency bắt buộc cho việc commit record.

## 18. Dashboard phối hợp ba tín hiệu

Bố cục dashboard gợi ý:

~~~text
Spring Kafka Reliability Dashboard
|
+-- Metrics: health và SLO
|     consumer lag theo topic/partition
|     records/sec, processing errors/sec
|     listener processing p50/p95/p99
|     retry/DLT rates và transaction aborts
|     DB/HTTP latency
|
+-- Logs: điều tra sự kiện
|     filter service/topic/error category
|     search event ID hoặc source offset
|
+-- Traces: đường đi và bottleneck
      slow/error traces
      producer/consumer spans
      DB/HTTP child spans
~~~

Nếu observability backend hỗ trợ **exemplars**, metric point có thể liên kết tới một trace tiêu biểu. Nhưng exemplar chỉ là mẫu; không phải mọi record hoặc metric sample đều có trace đầy đủ.

Đừng thiết kế dashboard chỉ có một đèn “Kafka healthy”. Container running không bảo đảm consumer đang tiến triển, và DLT publish success cao không bảo đảm business errors thấp.

## 19. Incident walkthrough: DLT publish failure

Giả sử người vận hành thấy:

~~~text
Metrics:
  listener.errors/sec          tăng
  dlt.publish.attempts/sec     tăng
  dlt.publish.failures/sec     tăng
  consumer_lag{partition="2"}  tăng
~~~

Tín hiệu cho thấy đường recovery có vấn đề, nhưng chưa đủ xác định nguyên nhân. Structured log:

~~~text
ERROR service=orders-worker
      event_id=evt-7aa2
      source_topic=orders.created
      partition=2 offset=481
      dlt_topic=orders.created.DLT
      action=publish_dlt
      error_category=authorization
      message="DLT write unauthorized"
~~~

Nếu trace được giữ lại:

~~~text
consume orders.created
   |
   +-- business validation -> error
   |
   +-- recoverer publish DLT -> authorization error
~~~

Các bước tiếp theo: kiểm tra topic DLT, partition và producer ACL; sau khi sửa, quan sát DLT publish ack/transaction commit, source committed offset và giảm lag. Không tự commit source offset chỉ để làm lag giảm khi record chưa được bảo toàn trong DLT.

## 20. Incident walkthrough: database chậm gây lag

Metric:

~~~text
consumer_lag tăng mạnh
listener_processing_p95 tăng
kafka_fetch_latency ổn định
db_pool_active gần giới hạn
~~~

Log:

~~~text
WARN event_id=evt-58f3 topic=payments.authorized
     partition=4 offset=18233
     error_category=db_connection_timeout
     action=retry
~~~

Trace:

~~~text
consume payments.authorized
   |
   +-- validation                    5ms
   +-- DB connection acquisition  1800ms
   +-- SQL update                    40ms
~~~

Kết luận hợp lý: bottleneck nằm ở database pool hoặc dependency, không phải Kafka broker fetch. Thay đổi `pollTimeout` thường không giải quyết gốc rễ. Cần điều tra pool capacity, connection leaks, query plan, lock contention và retry policy.

Sau khắc phục, metric chứng minh latency/lag phục hồi; log cho biết những records lỗi được retry hay đưa DLT; trace xác minh DB wait giảm trên những execution được lấy mẫu.

## 21. Kiểm thử instrumentation

Test cần chứng minh **tín hiệu đã được ghi ở đúng chỗ**, không chỉ method observer được gọi.

### 21.1. Metric test

Với `SimpleMeterRegistry` hoặc test registry tương ứng:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

// processor và service test double được khởi tạo trong setup.
processor.process(event);

double attempts = registry
        .find("app.payment.processing.attempts")
        .tag("outcome", "success")
        .counter()
        .count();

assertThat(attempts).isEqualTo(1.0);
~~~

Đây là fragment minh họa: `processor`, `event` được chuẩn bị trong test. Cần kiểm tra cả đường error, Timer duration và không có tags chứa event ID.

### 21.2. Log test

Dùng test appender hoặc log capture để xác nhận:

- Log có event ID và source topic-partition-offset.
- Retry/DLT stages được phân loại đúng.
- Có error category rõ ràng.
- Không lộ payload nhạy cảm.
- Có traceId/spanId khi tracing scope đã thiết lập.
- Khi retry nhiều lần, không phát full stack trace không giới hạn.

Không assert full stack trace byte-for-byte nếu không cần; version và exception wrapping có thể thay đổi.

### 21.3. Tracing test

Với in-memory tracing exporter/test backend phù hợp:

1. Bật observation trên KafkaTemplate và listener container.
2. Produce record với context propagation.
3. Consumer nhận record và tạo business span.
4. Kiểm tra producer/consumer observations xuất hiện theo hợp đồng.
5. Kiểm tra correlation propagation hoặc span links như cấu hình thực tế.
6. Tạo exception và kiểm tra span error event/status phù hợp.
7. Đảm bảo event ID không lọt vào metric low-cardinality tags.
8. Nếu có executor, kiểm tra context không bị mất hoặc rò sang record khác.

Không hard-code parent-child tree nếu tracing stack sử dụng span links hoặc sampling. Test cần xác minh correlation semantics đã chọn.

### 21.4. Integration test Kafka + database

Dùng Kafka Testcontainers/Embedded Kafka và database thật cho những yêu cầu như:

- Log và metric thể hiện record retries đúng.
- DLT publish failure được quan sát khi thiếu ACL/topic hoặc serializer sai.
- Kafka transactional send ack không bị ghi nhầm thành transaction commit.
- DB commit và Kafka commit được đo/ghi nhận riêng.
- Redelivery của cùng event ID không tạo double business side effect.
- Khi tracing backend không khả dụng, Kafka listener vẫn hoạt động theo policy.
- Sau rebalance/restart, MDC của record trước không rò vào record mới.

Những kiểm thử này đánh giá observability ở biên thật thay vì chỉ mock lời gọi của listener method.

## 22. Những nhầm lẫn cần tránh

- **Đếm log lines thay cho business events:** một record có thể retry nhiều lần.
- **Gắn event ID làm metric tag:** tạo cardinality explosion.
- **Coi metric lag là nguyên nhân:** lag chỉ là triệu chứng có nhiều nguồn.
- **Coi trace là audit đầy đủ:** traces có sampling và retention.
- **Coi trace ID là idempotency key:** replay có thể đổi trace.
- **Bật tracing producer nhưng không bật consumer:** propagation có thể bị đứt.
- **Cho rằng mọi thread tự có MDC:** async executor cần context propagation.
- **Xem KafkaTemplate send span là Kafka transaction committed:** send và commit khác nhau.
- **Xem listener method success là DB durable success:** transaction có thể commit sau method.
- **Chỉ quan sát main topic, quên retry/DLT:** record có thể đổi topic.
- **Không đo queueing delay:** listener processing nhanh vẫn có thể khiến end-to-end SLA trễ.
- **Log raw payload/headers:** rủi ro bảo mật và chi phí lưu trữ.
- **Tạo spans cho mọi bước nhỏ không cần thiết:** overhead và khó tìm signal.
- **Không kiểm thử metric tags:** application có thể tạo hàng triệu time series mà không ai nhận ra.
- **Dùng telemetry thay cho transactional outbox/idempotency:** quan sát không tự tạo bảo đảm dữ liệu.

## 23. Chọn tín hiệu theo nhu cầu

| Cần biết điều gì? | Ưu tiên |
|---|---|
| Có bao nhiêu records lỗi mỗi phút? | Metric Counter/Rate |
| p95 listener processing bao nhiêu? | Metric Timer/Histogram |
| Record ở offset 481 lỗi vì sao? | Structured Log |
| Service quyết định retry hay DLT? | Log + recovery counter |
| Lệnh Kafka này bắt nguồn từ HTTP request nào? | Trace + business correlation |
| DB query nào làm processing chậm? | Trace + DB latency metric |
| Consumer group lag nằm ở partition nào? | Kafka lag metric |
| Record DLT đã được Kafka commit? | Kafka commit result/committed state + log/metric đúng mốc |
| Thanh toán đã áp dụng đúng một lần? | Database/inbox/ledger state; telemetry hỗ trợ |
| SLO đang bị vi phạm? | Metric đo đúng end-to-end boundary |
| Vì sao SLO bị vi phạm? | Logs + representative traces |

**Kết luận:** metric trả lời *mức độ và xu hướng*; log trả lời *sự kiện và quyết định cụ thể*; trace trả lời *đường đi và chi phí từng bước*. Trong Spring Kafka, ba tín hiệu phải được liên kết qua event ID, source topic-partition-offset và trace context, nhưng kết quả xử lý bền vững vẫn phải được xác nhận bằng Kafka commit/offset và database state. Sử dụng đúng công cụ ở đúng ranh giới giúp phát hiện sớm lỗi, giảm thời gian điều tra và tránh những kết luận sai như “listener chạy thành công nghĩa là transaction đã commit” hoặc “DLT publish được gọi nghĩa là record đã được bảo toàn”.

