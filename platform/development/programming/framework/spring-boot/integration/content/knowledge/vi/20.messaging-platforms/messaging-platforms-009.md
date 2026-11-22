# Thông điệp lỗi, thử lại, dead-letter và phát lại

## 1. Bối cảnh và mục tiêu

Trong module **Spring Boot Integration**, ứng dụng thường nhận sự kiện từ Kafka, RabbitMQ, Apache Pulsar hoặc một adapter của Spring Integration, rồi đọc/ghi cơ sở dữ liệu, tra cache hay gọi HTTP API đối tác. Một thông điệp lỗi có thể khiến hàng loạt bản ghi bị chặn, tạo retry storm, mất dữ liệu hoặc thực hiện cùng một giao dịch nhiều lần. Do đó, xử lý lỗi là **một phần của hợp đồng tích hợp**, không chỉ là một `catch (Exception)`.

Xét một consumer nhận `OrderCreated` rồi gọi dịch vụ cấp hạn mức. Có ba khả năng:

1. Payload sai schema, thiếu `orderId`: dữ liệu **không thể xử lý với hợp đồng hiện tại**.
2. Dịch vụ hạn mức trả `503` hoặc bị timeout: có thể là lỗi **tạm thời**; việc gọi đã thành công ở phía đối tác hay chưa còn chưa chắc chắn.
3. Consumer đã ghi DB thành công nhưng chết trước khi xác nhận với broker: broker có thể **giao lại** dù tác dụng phụ đã hoàn tất.

Một thiết kế đầy đủ cần định nghĩa: **phát hiện lỗi → phân loại → thử lại có giới hạn → đưa vào vùng dead-letter khi cần → sửa nguyên nhân → phát lại có kiểm soát**, đồng thời bảo vệ idempotency và khả năng quan sát.

### Chuỗi xử lý tổng quát

~~~mermaid
flowchart TD
    A[Producer gửi sự kiện] --> B[Broker: topic / queue gốc]
    B --> C[Consumer Spring Boot]
    C --> D{Kiểm tra hợp đồng và xử lý}
    D -->|Thành công| E[Ghi kết quả / outbox]
    E --> F[Ack hoặc commit offset]
    D -->|Lỗi tạm thời| G{Còn retry budget?}
    G -->|Có| H[Backoff / retry queue hoặc topic]
    H --> C
    G -->|Không| I[DLQ / DLT + metadata lỗi]
    D -->|Lỗi vĩnh viễn| I
    I --> J[Incident, cảnh báo, phân loại và sửa lỗi]
    J --> K{Được phép replay?}
    K -->|Có| L[Replay có idempotency, throttle, audit]
    L --> B
    K -->|Chưa| M[Lưu giữ / cách ly / kết thúc theo policy]
~~~

Sơ đồ mô tả **ý định xử lý**, không ngụ ý một giao dịch nguyên tử xuyên producer, broker, database và HTTP đối tác. Cần chọn bảo đảm giao nhận phù hợp với từng nền tảng và kiểm tra ranh giới acknowledgment.

## 2. Định nghĩa: lỗi, retry, dead-letter và replay

| Khái niệm | Nghĩa | Phân biệt quan trọng |
| --- | --- | --- |
| **Error message** | Thông điệp mô tả sự cố, có thể là `ErrorMessage` trong Spring Integration hoặc sự kiện lỗi của hệ thống | Không nhất thiết là bản sao của sự kiện nghiệp vụ ban đầu |
| **Retry** | Thử xử lý lại **cùng một yêu cầu logic** vì hy vọng lỗi đã hết | Retry có thể thực hiện tại consumer, trong broker hoặc bởi scheduler |
| **Backoff** | Khoảng chờ trước lần thử tiếp theo, thường có exponential growth và jitter | Không phải số lần retry; cần cả giới hạn thời gian và concurrency |
| **DLQ** | *Dead-letter queue*: hàng đợi cách ly message không xử lý được hoặc vượt số lần thử | Phổ biến trong RabbitMQ/AMQP; cần exchange/binding và retention phù hợp |
| **DLT** | *Dead-letter topic*: topic chứa record thất bại | Phổ biến trong Kafka; một topic mới **không tự có** chỉ vì listener ném exception |
| **Replay / redrive** | Đưa message đã lưu giữ trở lại luồng xử lý bằng một tác vụ có kiểm soát | Là một hoạt động mới, có thể tạo offset/ack mới và side effect mới |
| **Poison message** | Message luôn gây lỗi tại cùng điểm, thường vì schema hoặc dữ liệu không hợp lệ | Không nên lặp vô hạn, có nguy cơ chặn cả partition/queue |
| **Redelivery** | Broker giao lại message chưa được xác nhận hoặc chưa được xử lý theo cơ chế broker | Có thể xảy ra **không qua** retry policy trong ứng dụng |

### Cần lưu gì trong hợp đồng message?

Ví dụ event JSON:

~~~json
{
  "eventId": "evt-8f2a",
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "sourceSystem": "checkout",
  "aggregateId": "order-5042",
  "occurredAt": "2026-11-21T05:00:00Z",
  "data": {
    "orderId": "order-5042",
    "amount": 125000,
    "currency": "VND"
  }
}
~~~

| Trường | Mục đích khi lỗi và replay |
| --- | --- |
| `eventId` | Khóa idempotency của **sự kiện logic**; giữ ổn định qua retry/replay |
| `eventType` + `schemaVersion` | Chọn deserializer/validator phù hợp, hỗ trợ migration có chủ đích |
| `sourceSystem` | Quy định nguồn sở hữu dữ liệu, phân loại và quyền replay |
| `aggregateId` | Khóa partition/routing để giữ thứ tự theo đối tượng nghiệp vụ khi cần |
| `occurredAt` | Mốc phát sinh sự kiện; không thay bằng thời gian retry |
| `correlationId` / trace context trong headers | Liên kết log, trace và các thao tác ở DB/HTTP/broker |
| `attempt`, `firstFailureAt`, `failureCategory` | Metadata hạ tầng được quản lý theo broker/consumer; dùng để định tuyến và cảnh báo |

Không yêu cầu mọi hệ thống phải dùng chính xác JSON này. Định dạng thực tế có thể là Avro, Protobuf hoặc JSON Schema; điều quan trọng là khóa nghiệp vụ, phiên bản hợp đồng và ngữ nghĩa của từng trường được công bố. Nếu payload chứa dữ liệu cá nhân, DLQ/DLT vẫn phải tuân thủ quy tắc mã hóa, quyền truy cập, retention và xóa dữ liệu.

### Delivery guarantee ≠ business guarantee

- **At-most-once:** tránh giao lại nhưng có thể mất message nếu consumer chết trước khi hoàn tất.
- **At-least-once:** broker có thể giao lại; ứng dụng phải chịu được duplicate. Đây là tiền đề phổ biến cho tích hợp cần độ tin cậy.
- **Exactly-once** ở một số cơ chế broker/transaction có **phạm vi cụ thể**, ví dụ xử lý và ghi lại vào Kafka theo transaction; không tự bao phủ HTTP API hoặc database độc lập.

Ví dụ: DB đã commit rồi consumer crash trước khi ack. Broker giao lại message và worker có thể ghi thêm lần nữa. Vì vậy dùng `eventId`/`sourceSystem` làm khóa duy nhất ở **consumer inbox/idempotency table**, và yêu cầu HTTP bên ngoài hỗ trợ idempotency key hoặc có cơ chế reconciliation.

## 3. Phân loại lỗi trước khi retry

Không phải lỗi nào cũng “retryable”. Nên phân loại bằng logic có thể kiểm thử, dựa vào hợp đồng dữ liệu, response code và nguyên nhân hạ tầng.

| Nhóm lỗi | Ví dụ | Hành động ban đầu | Khi hết giới hạn |
| --- | --- | --- | --- |
| **Permanent / contract** | Thiếu field bắt buộc, schemaVersion không hỗ trợ, enum lạ | Không retry lặp; ghi lý do có cấu trúc | DLT/DLQ hoặc quarantine nghiệp vụ |
| **Business rejection có chủ đích** | Đơn hàng đã bị từ chối hợp lệ theo policy | Kết quả nghiệp vụ, không phải lỗi hạ tầng | Ghi trạng thái `REJECTED` theo hợp đồng, có thể không cần DLQ |
| **Transient dependency** | HTTP `503`, DB tạm unavailable, pool timeout | Retry có giới hạn, backoff và circuit breaker | DLT/DLQ + cảnh báo, cho replay sau khi sửa sự cố |
| **Rate limit / overload** | HTTP `429`, broker downstream quá tải | Tôn trọng `Retry-After` nếu hợp lệ; giảm concurrency | Retry topic/queue có delay hoặc quarantine có kế hoạch |
| **Ambiguous outcome** | Timeout sau POST, disconnect sau DB commit | Tra cứu kết quả hoặc retry với **cùng idempotency key** | Incident riêng, không kết luận “chắc chắn chưa thực thi” |
| **Serialization / deserialization** | JSON sai cú pháp, Avro schema incompatible | Error-handling deserializer / error channel cấp adapter | DLT lưu raw payload an toàn và thông tin schema |
| **Configuration / security** | Sai TLS truststore, credential không hợp lệ | Cảnh báo và sửa cấu hình; không retry không giới hạn | Tạm dừng/giảm tải, giữ message chờ |
| **Broker publish/ack failure** | Không publish được DLT, lost confirm | Không ack như thể đã lưu dead-letter thành công | Retry/recover riêng việc chuyển DLT, theo cơ chế nền tảng |

Một quy tắc thực hành: **thành công nghiệp vụ**, **từ chối hợp lệ**, **lỗi retryable** và **lỗi không thể xử lý** là bốn kết quả riêng. Đừng ép tất cả vào một boolean `success` hoặc ghi nhận mọi exception là “không tìm thấy”.

### Mô hình mã lỗi có cấu trúc

~~~java
public enum FailureKind {
    INVALID_CONTRACT,
    BUSINESS_REJECTED,
    TRANSIENT_DEPENDENCY,
    RATE_LIMITED,
    UNKNOWN_OUTCOME,
    CONFIGURATION,
    UNEXPECTED
}

public record FailureDescription(
        FailureKind kind,
        String safeCode,
        boolean retryable,
        String eventId) {
}
~~~

`safeCode` là mã ổn định như `PARTNER_TIMEOUT` hoặc `SCHEMA_VERSION_UNSUPPORTED`, không chứa body/token/password hoặc stack trace. `retryable` nên xuất phát từ chính sách từng operation: một `POST` không có idempotency/reconciliation sẽ khác một `GET` chỉ đọc.

## 4. Thiết kế retry budget và backoff

### 4.1. Retry tại consumer hay qua broker?

| Cách thử lại | Đặc tính | Khi nào nên chọn | Hạn chế |
| --- | --- | --- | --- |
| **Blocking/local retry** | Giữ record trong consumer trong lúc đợi và thử lại | Lỗi thoáng qua vài trăm mili giây đến vài giây, cần giữ thứ tự | Có thể giữ partition/thread, làm tăng consumer lag |
| **Retry topic Kafka** | Gửi record sang topic retry, consumer xử lý về sau | Backoff dài, cần tránh chặn luồng chính | Có thể thay đổi thứ tự xử lý theo key, phát sinh topic/consumer |
| **Retry queue / TTL / delayed delivery RabbitMQ** | Broker giữ message đến mốc thử lại | Delay lớn, tránh requeue vòng lặp tức thời | Cần cấu hình DLX/TTL/limits và tính bảo đảm chuyển tiếp |
| **Scheduler retry từ DB/outbox** | Ghi trạng thái retry bền vững rồi job lấy ra | Quy trình đòi xác minh downstream/đợi hàng giờ | Phải tự thiết kế lease, concurrency, idempotency và cleanup |
| **Immediate requeue** | Đặt lại message vào queue ngay | Hiếm khi phù hợp nếu lỗi sẽ tiếp diễn | Có thể tạo vòng lặp nóng và bão CPU/connection |

### 4.2. Số lần, khoảng chờ và tổng thời gian

Ví dụ policy:

~~~text
Attempt 1: tại t = 0
Attempt 2: sau 1 giây
Attempt 3: sau 2 giây
Attempt 4: sau 4 giây
=> 4 lần thực thi (1 lần đầu + 3 retry), khoảng chờ tối thiểu 7 giây,
   CHƯA gồm thời gian xử lý mỗi lần, jitter và chuyển topic/queue.
~~~

Đặt `maxAttempts` cùng `initialDelay`, `multiplier`, `maxDelay`, **total deadline** và giới hạn số request đang retry. Thêm **jitter** để không có hàng nghìn consumer cùng thức dậy sau một giây khi đối tác vừa lỗi. Với `429`, đọc `Retry-After` nhưng vẫn áp ngân sách tổng và giới hạn của dịch vụ. Một lỗi cấu hình không tự hết sau backoff.

Tránh “retry tầng tầng lớp lớp”: HTTP client retry 3 lần, service retry 3 lần, Kafka retry 4 lần có thể tạo tới **36 lần gọi HTTP** cho cùng event. Chính sách cần nêu rõ tầng nào sở hữu retry, tầng nào chỉ trả lỗi để escalates.

### 4.3. Retry và thứ tự xử lý

Với Kafka, mỗi partition có thứ tự offset. Blocking retry thường giữ record lỗi ở tuyến xử lý partition đó; **non-blocking retry topics** có thể cho record sau đi tiếp trong topic chính trước khi record lỗi quay lại. Nếu xử lý `OrderCreated` rồi `OrderCancelled` phụ thuộc thứ tự cùng `aggregateId`, dùng retry topic không cân nhắc có thể làm trạng thái cuối sai.

Với RabbitMQ, một message bị `nack(requeue=true)` có thể trở lại queue và được consumer khác lấy trước/sau các message khác tùy prefetch, số consumer và trạng thái queue. FIFO không đủ để đảm bảo ordering khi có nhiều consumer, requeue và retry delay.

Lựa chọn là quyết định nghiệp vụ: giữ thứ tự bằng một lane/partition theo aggregate key, dùng version và conditional update ở DB, hoặc chấp nhận xử lý lệch thứ tự rồi reconcile. Không hứa exactly-once hoặc total order chỉ từ lựa chọn broker.

## 5. Kafka: DefaultErrorHandler, DLT và retry topics

Kafka lưu record theo **topic/partition/offset**. Offset cho biết consumer đã đi tới đâu; record không bị xóa khỏi log chỉ vì listener xử lý thành công hay lỗi. DLT trong Kafka thường là **một topic riêng được consumer/framework publish sang**, không phải queue mà Kafka tự tạo sau một lần `throw`.

### 5.1. Dependencies và cấu hình tiêu biểu (Spring Boot 3.x)

~~~xml
<dependency>
  <groupId>org.springframework.kafka</groupId>
  <artifactId>spring-kafka</artifactId>
</dependency>
~~~

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: order-integration
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
    listener:
      ack-mode: record
~~~

Ví dụ này nhận chuỗi JSON và tự kiểm tra, vì thế tránh lỗi deserializer trước khi vào listener. Với Avro/Protobuf hoặc Spring JsonDeserializer, cần thêm cơ chế bắt **deserialization failure trước listener** như `ErrorHandlingDeserializer` và producer DLT có serializer hỗ trợ raw bytes khi cần; nếu không, handler có thể chưa bao giờ nhận được payload hợp lệ để chuyển DLT.

### 5.2. Lỗi trong listener và phân loại ngoại lệ

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderKafkaListener {

    private final ObjectMapper objectMapper;
    private final OrderProcessor processor;

    public OrderKafkaListener(
            ObjectMapper objectMapper, OrderProcessor processor) {
        this.objectMapper = objectMapper;
        this.processor = processor;
    }

    @KafkaListener(topics = "orders.events")
    public void consume(String json) {
        OrderCreated event;
        try {
            event = objectMapper.readValue(json, OrderCreated.class);
        } catch (JsonProcessingException ex) {
            throw new InvalidOrderEventException("Invalid order JSON", ex);
        }

        if (event.eventId() == null || event.eventId().isBlank()
                || event.orderId() == null || event.orderId().isBlank()) {
            throw new InvalidOrderEventException("Missing eventId/orderId");
        }

        processor.process(event); // Có idempotency/inbox ở tầng nghiệp vụ.
    }
}

record OrderCreated(String eventId, String orderId, long amount) {}

interface OrderProcessor {
    void process(OrderCreated event);
}

class InvalidOrderEventException extends RuntimeException {
    InvalidOrderEventException(String message) {
        super(message);
    }
    InvalidOrderEventException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Trong một file Java thật, cần đặt từng kiểu top-level `public` vào file mang đúng tên hoặc để các kiểu minh họa package-private như trên. `processor.process` là contract cần cài đặt: ví dụ ghi `eventId` vào inbox collection/bảng có unique constraint trước khi áp dụng tác dụng phụ. Nếu service gọi HTTP partner và gặp timeout, nó nên ném một loại exception riêng như `TransientPartnerException` thay vì biến lỗi thành `InvalidOrderEventException`.

### 5.3. Blocking retry rồi publish sang DLT

Với **Spring Kafka 3.x**, `DefaultErrorHandler` có thể retry record một số lần với backoff, sau đó sử dụng `DeadLetterPublishingRecoverer` đưa record sang topic lỗi:

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration(proxyBeanMethods = false)
public class OrderKafkaErrorConfiguration {

    @Bean
    DefaultErrorHandler orderKafkaErrorHandler(
            KafkaTemplate<String, String> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                        kafkaTemplate,
                        (record, error) -> new TopicPartition(
                                "orders.events.DLT", record.partition()));

        recoverer.setFailIfSendResultIsError(true);

        // 2 retries sau lần nhận đầu: tổng cộng tối đa 3 attempts.
        DefaultErrorHandler handler = new DefaultErrorHandler(
                recoverer, new FixedBackOff(1_000L, 2L));
        handler.addNotRetryableExceptions(InvalidOrderEventException.class);
        return handler;
    }
}
~~~

Khi dùng Spring Boot Kafka listener factory tự cấu hình, bean `CommonErrorHandler`/`DefaultErrorHandler` được Boot sử dụng để cấu hình listener container. Nếu ứng dụng tự khai báo `ConcurrentKafkaListenerContainerFactory`, phải **gắn handler đó** bằng `factory.setCommonErrorHandler(handler)`; đừng mặc định bean sẽ tác động lên mọi factory tùy chỉnh.

Một chu kỳ:

~~~text
orders.events, partition=2, offset=91
  -> listener lần 1: 503 (retryable)
  -> FixedBackOff 1.000 ms -> lần 2: 503
  -> FixedBackOff 1.000 ms -> lần 3: 503
  -> recoverer publish sang orders.events.DLT, partition=2
  -> chỉ tiếp tục / commit record gốc theo container policy
     khi recovery thành công
~~~

`FixedBackOff(1_000L, 2L)` nghĩa là **hai lần retry**, không phải hai lần xử lý tổng cộng. `InvalidOrderEventException` thuộc nhóm không retry, nên được chuyển thẳng sang DLT. Tùy phiên bản, mặc định Spring Kafka còn coi một số lỗi `DeserializationException`, `MessageConversionException` là fatal. Đừng trộn thay đổi chính sách giữa nhiều error handler mà không có test xác nhận.

**Điều kiện triển khai:**

- Topic `orders.events.DLT` phải tồn tại và có **ít nhất cùng số partition với topic nguồn** nếu recoverer chuyển sang `record.partition()`. Nếu muốn để producer chọn partition, resolver có thể trả `TopicPartition(name, -1)` trong cấu hình phù hợp.
- Cấu hình producer DLT, broker authorization, serializer và message size tương thích. Nếu publish DLT lỗi nhưng consumer vẫn coi record đã recover, dữ liệu có thể mất khỏi tuyến xử lý chính.
- Bảo đảm publish thành công theo chính sách (ví dụ `setFailIfSendResultIsError(true)`, producer ack và kiểm thử lỗi broker) trước khi coi bản ghi đã được cách ly.
- Metadata DLT gồm original topic/partition/offset, exception class và các headers khác; kiểm soát thông tin nhạy cảm. Thời gian lưu giữ DLT phải đủ để điều tra, không vô hạn.
- Việc commit offset sau xử lý/recover còn phụ thuộc `AckMode`, `commitRecovered` và cấu hình container/transaction. Không suy diễn từ code listener mà không kiểm tra broker và consumer group.

### 5.4. Theo dõi record trong DLT

Có thể dùng một consumer riêng để ghi incident mà **không tự replay**:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderDltInspector {
    private final FailureIncidentStore incidents;

    public OrderDltInspector(FailureIncidentStore incidents) {
        this.incidents = incidents;
    }

    @KafkaListener(
            topics = "orders.events.DLT",
            groupId = "orders-dlt-inspector")
    public void inspect(ConsumerRecord<String, String> record) {
        incidents.record(
                record.key(), record.topic(), record.partition(),
                record.offset(), record.value(), record.headers());
    }
}

interface FailureIncidentStore {
    void record(String key, String topic, int partition, long offset,
                String rawValue, org.apache.kafka.common.header.Headers headers);
}
~~~

Incident store phải có khóa duy nhất cho lần quan sát DLT, vì chính listener kiểm toán cũng có thể được giao lại. Trong production, không lưu raw payload chưa được kiểm tra quyền/PII; chỉ giữ dữ liệu tối thiểu hoặc lưu ciphertext có retention. Nếu incident DB lỗi, hãy để listener thất bại theo policy để broker giao lại, thay vì ACK và mất dấu lỗi.

### 5.5. Retry topic không chặn luồng chính

Thay cho blocking retry ở mục 5.3, Spring Kafka hỗ trợ **non-blocking retry topics** với `@RetryableTopic`. Đây là **một phương án thay thế**, không bật chồng cả hai lên cùng listener nếu chưa thiết kế rõ:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.DltHandler;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
class RetryTopicOrderConsumer {
    private final ObjectMapper objectMapper;
    private final OrderProcessor processor;
    private final FailureIncidentStore incidents;

    RetryTopicOrderConsumer(
            ObjectMapper objectMapper,
            OrderProcessor processor, FailureIncidentStore incidents) {
        this.objectMapper = objectMapper;
        this.processor = processor;
        this.incidents = incidents;
    }

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(delay = 1_000, multiplier = 2.0,
                               maxDelay = 5_000),
            exclude = InvalidOrderEventException.class,
            autoCreateTopics = "false")
    @KafkaListener(
            topics = "orders.retry-demo",
            groupId = "orders-retry-demo")
    public void consume(String rawJson) {
        processor.process(parseOrder(rawJson));
    }

    @DltHandler
    public void inspectDeadLetter(ConsumerRecord<String, String> record) {
        // Ghi incident; không tự phát lại ngay.
        incidents.record(
                record.key(), record.topic(), record.partition(),
                record.offset(), record.value(), record.headers());
    }

    private OrderCreated parseOrder(String rawJson) {
        try {
            OrderCreated event =
                    objectMapper.readValue(rawJson, OrderCreated.class);
            if (event.eventId() == null || event.eventId().isBlank()
                    || event.orderId() == null || event.orderId().isBlank()) {
                throw new InvalidOrderEventException("Missing eventId/orderId");
            }
            return event;
        } catch (JsonProcessingException ex) {
            throw new InvalidOrderEventException("Invalid order JSON", ex);
        }
    }
}
~~~

`@RetryableTopic` dựa trên Spring Retry (`org.springframework.retry.annotation.Backoff`); với `attempts="4"`, số lần là **1 lần gốc + 3 lần retry**. `exclude = InvalidOrderEventException.class` loại lỗi hợp đồng khỏi retry và chuyển sang DLT ngay. `autoCreateTopics="false"` yêu cầu provision các retry topic/DLT theo tên và số partition mà Spring Kafka của phiên bản đang dùng sẽ dùng; nếu không, listener không hoạt động như mong đợi. Ví dụ có cùng `OrderCreated`, `OrderProcessor`, `InvalidOrderEventException` và `FailureIncidentStore` được khai báo ở các đoạn trước.

Các hạn chế cần biết: non-blocking retry **không kết hợp được với Kafka container transactions** và **không hỗ trợ batch listeners**; nó có thể làm thay đổi thứ tự record cùng key khi record sau vượt trước record đang nằm ở retry topic. Với nghiệp vụ phải xử lý tuần tự, cân nhắc blocking retry, version gate hoặc hàng đợi xử lý riêng theo key. Nếu dùng Spring Kafka 4.x, kiểm tra lại tên topic retry, số lần mặc định và các chế độ tái sử dụng retry topic; không dựa vào một quy tắc suffix cố định qua mọi phiên bản.

## 6. RabbitMQ: reject/nack, DLX và DLQ

RabbitMQ dùng **exchange → routing key → queue**. Broker giao message cho consumer; consumer hoặc listener container xác nhận (`basic.ack`), từ chối (`basic.reject`) hoặc `basic.nack`. Khi `requeue=false` và queue có cấu hình dead-letter exchange (**DLX**), broker có thể chuyển message đến queue lỗi. Những lý do dead-letter khác gồm TTL hết hạn, vượt queue length limit hoặc vượt delivery limit của quorum queue.

### 6.1. Cấu hình topology RabbitMQ

Với **Spring Boot 3.x và Spring AMQP 3.x**:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RabbitDeadLetterTopology {

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange("orders.exchange", true, false);
    }

    @Bean
    DirectExchange ordersDeadExchange() {
        return new DirectExchange("orders.dlx", true, false);
    }

    @Bean
    Queue ordersWorkQueue() {
        return QueueBuilder.durable("orders.work")
                .deadLetterExchange("orders.dlx")
                .deadLetterRoutingKey("orders.dead")
                .build();
    }

    @Bean
    Queue ordersDeadQueue() {
        return QueueBuilder.durable("orders.dlq").build();
    }

    @Bean
    Binding ordersBinding(Queue ordersWorkQueue,
                          DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersWorkQueue)
                .to(ordersExchange).with("orders.created");
    }

    @Bean
    Binding deadBinding(Queue ordersDeadQueue,
                        DirectExchange ordersDeadExchange) {
        return BindingBuilder.bind(ordersDeadQueue)
                .to(ordersDeadExchange).with("orders.dead");
    }
}
~~~

Đường đi:

~~~text
publish exchange=orders.exchange, routingKey=orders.created
         -> queue orders.work
         -> consumer xử lý lỗi
         -> reject/nack(requeue=false)
         -> DLX orders.dlx, routingKey=orders.dead
         -> queue orders.dlq
~~~

Spring AMQP có thể khai báo `Queue`, `Exchange` và `Binding` qua `RabbitAdmin` nếu được cấu hình. Trong production, RabbitMQ khuyến nghị quản lý DLX qua **policy** để có thể thay đổi mà không phải xóa/tạo lại queue; mã phía trên giúp nhìn rõ topology của bài thực hành. Queue argument `x-dead-letter-exchange` và `x-dead-letter-routing-key` có tác dụng tương ứng với builder.

**DLQ không tự được tạo chỉ vì `default-requeue-rejected=false`.** Broker cần có DLX và binding đích hợp lệ; nếu không, message bị reject có thể bị loại khỏi queue nguồn mà không nằm trong vùng cách ly mong muốn. Khi yêu cầu giữ message lâu dài, kiểm tra durability, persistence, quyền publish/routing, disk alarm và giới hạn dung lượng.

### 6.2. Listener và retry ở container

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderRabbitListener {
    private final OrderMessageService service;

    public OrderRabbitListener(OrderMessageService service) {
        this.service = service;
    }

    @RabbitListener(queues = "orders.work")
    public void receive(String rawJson) {
        service.handle(rawJson);
    }
}

interface OrderMessageService {
    void handle(String rawJson);
}
~~~

Nếu service ném exception, listener container xử lý theo acknowledgment/requeue/retry đã cấu hình. Ví dụ:

~~~yaml
spring:
  rabbitmq:
    host: ${RABBITMQ_HOST:localhost}
    listener:
      simple:
        acknowledge-mode: auto
        default-requeue-rejected: false
        prefetch: 20
        retry:
          enabled: true
          max-attempts: 4
          initial-interval: 1s
          multiplier: 2
          max-interval: 8s
~~~

Khi listener container có retry interceptor theo cấu hình Boot, `max-attempts: 4` nghĩa là **lần đầu và tối đa ba lần retry** trong quá trình xử lý message. Khi hết retry và final failure được reject không requeue, RabbitMQ có thể dead-letter message theo topology đã khai báo. `acknowledge-mode: auto` nghĩa là container tự ack sau khi listener xử lý thành công; nó **không** nói rằng broker bảo đảm tác dụng phụ của DB/HTTP đã xảy ra exactly-once.

**Phân loại lỗi vĩnh viễn:** retry interceptor mặc định có thể retry cả lỗi schema/validation rồi mới reject. Nếu muốn chuyển thẳng những lỗi đó sang DLQ, cấu hình `RetryPolicy`/`RetryOperationsInterceptor` với exception classifier phù hợp hoặc chia tuyến validation trước handler. `AmqpRejectAndDontRequeueException` có thể buộc container reject với `requeue=false` khi exception đến tới tầng container; nếu bên ngoài có retry advice, vẫn phải xét advice có xử lý exception đó trước hay không.

### 6.3. Vì sao không được requeue vô hạn?

Nếu luôn `nack(requeue=true)` trong lúc DB đang ngừng hoạt động, cùng message có thể quay lại ngay, nhiều consumer cùng lặp lỗi và CPU/connection của cả cluster tăng đột biến. Giải pháp:

- Chọn số lần thử tại consumer đủ nhỏ cho lỗi ngắn.
- Với lỗi kéo dài, chuyển sang **delayed retry queue** hoặc cơ chế scheduler/retry phù hợp; không dùng vòng lặp nóng.
- Đặt giới hạn delivery/quorum queue và policy rõ ràng cho lỗi không thể phục hồi.
- Theo dõi số lượng message ready/unacked, consumer utilization, redelivery rate và DLQ depth.
- Nếu lỗi gây tác dụng phụ không chắc chắn, giữ idempotency key và kiểm tra downstream trước khi thử lại.

Một kiến trúc retry dựa trên TTL có thể dùng:

~~~text
orders.work -> khi lỗi tạm thời -> retry.exchange
                                  -> orders.retry.5s (TTL 5 giây)
                                  -> khi hết TTL, DLX quay về orders.exchange
                                  -> orders.work
orders.work -> khi hết budget/poison -> orders.dlx -> orders.dlq
~~~

Đây là sơ đồ **logic**, cần cấu hình đầy đủ exchange, queue, routing key, TTL, retry-count và phân nhánh cuối. RabbitMQ hỗ trợ dead-lettering khi message hết TTL, nhưng TTL trên một hàng đợi dùng chung và nhiều delay khác nhau có thể tạo head-of-line blocking; cân nhắc nhiều retry queue theo khoảng chờ hoặc delayed-delivery mechanism phù hợp phiên bản broker.

### 6.4. Dead-letter có thể thất bại

Ở RabbitMQ, dead-lettering là **một lần publish mới ở phía broker**. Mặc định, cơ chế chuyển qua DLX có các giới hạn về durability; không nên giả định mọi trường hợp đều có bảo đảm at-least-once. Với **quorum queue**, RabbitMQ hỗ trợ dead-letter strategy `at-least-once` bằng publisher confirms nội bộ khi được cấu hình đúng, đổi lại tiêu thụ tài nguyên và giữ message nguồn cho đến khi đích xác nhận. Kiểm tra yêu cầu `overflow=reject-publish`, policy, queue type, quyền và tình trạng target. Cần kiểm thử khi DLX hoặc queue đích không sẵn sàng.

RabbitMQ đặt header broker-managed `x-death` ghi lại những lần dead-letter theo queue/reason. Không tự nhận `x-death.count` do producer gửi là một retry counter đáng tin cậy; RabbitMQ 4.x bỏ qua các header `x-*` do client tự gán trong một số đường publish. Nếu ứng dụng tự republish message để retry, quản lý `retry_count`/metadata của riêng mình theo hợp đồng và tránh chu trình dead-letter vô tận.

### 6.5. Khác nhau giữa reject, republish và recover

| Cơ chế Spring AMQP | Message nguồn sau khi xử lý recoverer | Điểm cần chú ý |
| --- | --- | --- |
| `AmqpRejectAndDontRequeueException` | Bị từ chối với `requeue=false` ở container | Broker DLX có thể nhận nếu đã cấu hình và định tuyến đúng |
| `RejectAndDontRequeueRecoverer` | Kết thúc retry bằng reject tương ứng | Có thể dùng khi muốn broker thực hiện DLX |
| `RepublishMessageRecoverer` | Recoverer chủ động publish thông điệp mới đến exchange/routing key đã chọn | Message nguồn thường được coi là đã recover và ack; **không tự đi DLX broker** |
| `RepublishMessageRecovererWithConfirms` | Publish và đợi publisher confirms theo cấu hình | Giảm nguy cơ ack nguồn khi publish đích thất bại, nhưng vẫn phải kiểm thử failure mode |
| `ImmediateRequeueAmqpException` | Yêu cầu container requeue ngay | Có nguy cơ hot loop; chỉ dùng khi thật sự hợp lý |

Nếu một recoverer chỉ log rồi trả về thành công, container có thể ack message và không còn bản sao trong DLQ. Khi mục tiêu là **không mất khả năng điều tra**, hãy kiểm thử cả đường thất bại publish DLT/DLQ chứ không chỉ đường xử lý thành công.

## 7. Spring Integration: ErrorMessage và errorChannel

Spring Integration có khái niệm `Message<?>`, channel và endpoint. Khi một xử lý **bất đồng bộ** thất bại hoặc poller phát sinh exception, framework có thể tạo `org.springframework.messaging.support.ErrorMessage` chứa `Throwable` và gửi đến **error channel** của message hoặc channel toàn cục mang tên `errorChannel`.

~~~text
Message<OrderCreated> -> IntegrationFlow
    |       \
    |        \-- synchronous DirectChannel: exception có thể ném về sender
    |
    +-- async ExecutorChannel / poller:
              exception -> ErrorMessage(Throwable)
                                  |
                             errorChannel
                                  |
                        log/incident/route/recovery
~~~

Ví dụ listener giám sát:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class IntegrationFailureObserver {
    private final IntegrationIncidentService incidents;

    public IntegrationFailureObserver(IntegrationIncidentService incidents) {
        this.incidents = incidents;
    }

    @ServiceActivator(inputChannel = "errorChannel")
    public void onError(ErrorMessage errorMessage) {
        Throwable failure = errorMessage.getPayload();
        Message<?> failed = null;
        if (failure instanceof MessagingException messagingFailure) {
            failed = messagingFailure.getFailedMessage();
        }
        incidents.record(failure, failed);
    }
}

interface IntegrationIncidentService {
    void record(Throwable error, Message<?> failedMessage);
}
~~~

`errorChannel` là **một luồng xử lý lỗi trong ứng dụng**, không tự tương đương với Kafka DLT hoặc RabbitMQ DLQ có lưu bền. Nếu muốn giữ message để phát lại sau restart, cần chủ động publish sang broker/incident store có chính sách confirm và retention. Lưu ý `failedMessage` đôi khi `null` hoặc mang payload đã transform, nên lưu correlation/eventId tại ranh giới intake.

**Ranh giới acknowledgment đặc biệt quan trọng:** nếu consumer broker chuyển message sang một `ExecutorChannel` rồi trả về ngay, broker listener có thể đã xem xử lý thành công trước khi tác vụ bất đồng bộ báo lỗi. Việc `ErrorMessage` được log không làm broker tự redeliver. Ngược lại, nếu một handler trên `DirectChannel` ném exception đồng bộ, nó có thể quay về listener container và được error handler của Kafka/RabbitMQ xử lý. Muốn broker retry đúng nghĩa, phải thiết kế ownership của ack, transaction, channel và điểm xác nhận kết quả.

Nếu dùng poller có cấu hình `errorChannel`, exception sẽ được gửi sang channel đó trong phạm vi của scheduled task. Nếu cần routing theo exception type, có thể dùng `ErrorMessageExceptionTypeRouter` hoặc service activator phân loại, nhưng không làm mất message vì một handler chỉ ghi log rồi trả về.

### 7.1. Đặt ranh giới lỗi ở đúng tầng

| Tầng | Error handler chính | Đặc điểm |
| --- | --- | --- |
| HTTP client | Status handler, exception mapping, retry/circuit breaker | Có thể biết 4xx/5xx hoặc timeout không có response |
| Spring Integration async endpoint | `ErrorMessage` qua `errorChannel` | Quyết định route/log/recover trong ứng dụng |
| Kafka listener container | `CommonErrorHandler`, retry topic/DLT | Có khả năng điều khiển retry record và commit offset |
| Rabbit listener container | Retry interceptor, reject/nack, recoverer | Có khả năng điều khiển ack/requeue/DLX |
| DB/outbox | Transaction và unique key | Ngăn side effect trùng, phối hợp việc publish |
| Replay job | Audit, authorization, rate limit, idempotency | Đưa message lỗi trở lại sau điều tra |

Tránh thiết kế để cả `IntegrationFlow` và listener container đều retry cùng một call mà không tính tổng số attempts và timeout. Mỗi loại exception cần một **chủ sở hữu chính sách** rõ ràng.

## 8. Phát lại (replay/redrive) có kiểm soát

Dead-letter là **trạm dừng để điều tra**, không phải bằng chứng rằng message có thể tự động đưa trở lại ngay lập tức. Replay chỉ nên được thực hiện khi nguyên nhân đã được xử lý hoặc dữ liệu đã được sửa theo một quy trình có thể kiểm toán.

### 8.1. Ba hình thức replay khác nhau

| Hình thức | Tác động lên broker | Khi nào dùng |
| --- | --- | --- |
| **Đọc DLT/DLQ rồi publish lại** | Tạo message mới trong topic/queue mục tiêu; cần xác nhận publish rồi đánh dấu đã chuyển | Phát lại một tập message đã điều tra |
| **Kafka reset/seek offset** | Consumer group đọc lại phần lịch sử còn retention, không tạo record mới trong log | Khôi phục một khoảng thời gian/offset khi logic consumer đã được sửa |
| **Tái tạo từ source-of-truth/outbox** | Xuất lại event từ trạng thái bền vững nguồn | Khi DLT không còn, schema cần chuyển đổi, hoặc nghiệp vụ phải đối soát |

Kafka offset **không phải message ID nghiệp vụ**. Nếu DLT consumer publish record trở lại `orders.events`, nó nhận một **offset mới** và có thể ở partition mới nếu partitioning policy thay đổi. Nếu reset consumer group để đọc lại từ offset cũ, tất cả record trong khoảng đó có thể được xử lý lại, kể cả record đã thành công; do đó cần idempotency trước khi reset.

Với RabbitMQ, khi consume một message từ DLQ và republish, message đã được lấy khỏi DLQ theo acknowledgment của **consumer replay**; không có thao tác “move nguyên tử” mặc định giữa hai queue riêng và HTTP/DB ngoài broker. Cần dùng publisher confirms/returns, chỉ ack DLQ khi publish đích đã được xác nhận theo policy và chấp nhận rằng vẫn có thể có duplicate sau crash.

### 8.2. Checklist trước một lần replay

1. **Khoanh vùng:** chỉ định topic/queue, partition/offset range hoặc danh sách incident ID; không “replay tất cả” theo cảm tính.
2. **Xác định nguyên nhân:** lỗi schema, bug ứng dụng, broker hay downstream? Đã sửa và deploy phiên bản đúng chưa?
3. **Kiểm tra hợp đồng:** payload còn hợp lệ với schema consumer mới không; cần migration/transform riêng và lưu dấu bản gốc không?
4. **Bảo vệ idempotency:** `eventId` không đổi; unique constraint ở inbox/DB; lệnh HTTP dùng cùng idempotency key hoặc reconciliation; xử lý lại không xóa/cập nhật sai dữ liệu mới hơn.
5. **Kiểm tra thứ tự:** record cũ có thể đi sau record mới; áp dụng version hoặc điều kiện cập nhật nếu cần.
6. **Giới hạn tải:** concurrency, batch size, throughput, backoff và số message tối đa; không làm nghẽn production khi redrive.
7. **Ghi audit:** người/phần mềm yêu cầu, phê duyệt (nếu thuộc quy trình), thời gian, scope, commit/version code, lý do, số bản ghi thành công/thất bại.
8. **Có điểm dừng:** dừng khi lỗi gia tăng, DLQ tiếp tục phình to, downstream quá tải hoặc tỷ lệ duplicate vượt ngưỡng.

Replay không nên được thực hiện từ một consumer DLT **tự động** publish lại ngay mỗi message: nếu nguyên nhân chưa được sửa, message sẽ quay vòng DLT–gốc vô hạn và che mất sự cố.

### 8.3. Mô hình trạng thái cho replay job

~~~mermaid
stateDiagram-v2
    [*] --> QUARANTINED: Message vào DLT/DLQ
    QUARANTINED --> READY: Điều tra và xác nhận chính sách
    READY --> CLAIMED: Replay worker nhận quyền
    CLAIMED --> PUBLISHING: Bắt đầu publish lại
    PUBLISHING --> SUBMITTED: Broker confirm thành công
    PUBLISHING --> RETRY_PENDING: Lỗi publish/timeout
    RETRY_PENDING --> CLAIMED: Backoff + lease hợp lệ
    SUBMITTED --> VERIFIED: Consumer xử lý lại thành công
    SUBMITTED --> QUARANTINED: Lại lỗi, tạo incident mới
    VERIFIED --> [*]
~~~

`SUBMITTED` chỉ nói rằng broker đã xác nhận nhận thông điệp replay; nó **không** nói rằng consumer đích đã xử lý nghiệp vụ xong. Muốn `VERIFIED`, phải có bằng chứng từ trạng thái nghiệp vụ/outbox/inbox hoặc message kết quả. Mọi trạng thái phải được lưu bền để worker khác có thể tiếp tục nếu process crash.

### 8.4. Ví dụ publish lại Kafka bằng khóa cũ

Sau khi incident đã được chọn và được phép phát lại, một service có thể gửi lại raw JSON bằng cùng aggregate key:

~~~java
import java.util.concurrent.CompletableFuture;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

record ReplayCandidate(
        String incidentId,
        String eventId,
        String aggregateId,
        String rawJson) {
}

@Service
public class KafkaReplayPublisher {
    private final KafkaTemplate<String, String> template;

    public KafkaReplayPublisher(KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public CompletableFuture<RecordMetadata> publish(
            ReplayCandidate candidate) {
        // Caller chịu trách nhiệm xác thực phạm vi replay, giới hạn tốc độ
        // và ghi trạng thái PUBLISHING/SUBMITTED vào incident store.
        return template
                .send("orders.events",
                      candidate.aggregateId(), candidate.rawJson())
                .thenApply(SendResult::getRecordMetadata);
    }
}
~~~

Caller **chỉ** ghi `SUBMITTED` khi future trả kết quả thành công; nếu future thất bại thì để trạng thái có thể retry. Trong tình huống broker nhận record rồi client mất kết nối trước khi biết kết quả, lần publish tiếp theo vẫn có thể tạo record trùng: consumer phải idempotent dựa trên `eventId`. Nếu serializer, schema hoặc partitioning rule đã đổi, cần kiểm tra đầu ra trước khi replay, không gửi raw payload không tương thích vào topic đang chạy.

Để trace một lần replay mà không đổi `eventId`, có thể thêm **header riêng** như `replayRunId`/`originalIncidentId` (với allowlist và không chứa PII). Không sửa `eventId` thành UUID mới chỉ để tránh việc consumer phát hiện duplicate, vì đó là thay đổi ngữ nghĩa nghiệp vụ.

### 8.5. RabbitMQ redrive từ DLQ

Một replay worker có thể consume `orders.dlq` ở chế độ **manual ack** và thực hiện:

~~~text
1. Nhận DLQ delivery, giữ deliveryTag.
2. Kiểm tra replay policy, schema và requestId/eventId.
3. Publish sang exchange gốc với routing key đích,
   thêm header replayRunId, giữ business key và dùng persistent delivery.
4. Đợi publisher confirm; kiểm tra unroutable return (mandatory) nếu áp dụng.
5. Chỉ sau khi publish đích được xác nhận mới basic.ack DLQ delivery.
6. Nếu publish lỗi / connection mất: không ack; để broker redeliver,
   dùng inbox/idempotency để chặn duplicate nếu publish đã thành công thực tế.
7. Ghi audit, cập nhật incident và theo dõi xử lý đầu cuối.
~~~

Đây là **thuật toán**, không phải `RabbitTemplate.convertAndSend(...)` tự nó đảm bảo giao dịch di chuyển queue. Nếu dùng publisher confirms của Spring AMQP, xác nhận cần bao gồm cả đường publish và routing khi dùng mandatory returns. Khi source là quorum queue, kiểm tra cơ chế delivery limit để replay worker không biến một lỗi tạm thành vòng lặp độc hại.

### 8.6. Ngừng replay khi nào?

Không replay khi chưa rõ nguyên nhân, khi schema được cập nhật không tương thích nhưng chưa có converter, khi downstream vẫn lỗi trên diện rộng, khi yêu cầu xử lý phải giữ strict ordering nhưng chưa có kế hoạch, hoặc khi replay có thể làm sai trạng thái nghiệp vụ hiện tại. Có thể chọn **quarantine lâu hơn hoặc bù trừ bằng quy trình nghiệp vụ** thay vì đẩy message cũ trở lại.

## 9. Kiểm thử: xác nhận hiệu ứng, không chỉ kiểm tra exception

Trong Spring Boot, kiểm thử policy nên chia thành các lớp: unit test cho classifier/processor; integration test với Kafka/RabbitMQ thật bằng Testcontainers hoặc công cụ tương đương; failure test mô phỏng consumer crash, DLT publish failure và downstream timeout. Không chỉ mock `KafkaTemplate`/`RabbitTemplate` rồi kết luận broker dead-letter hoạt động.

### 9.1. Ma trận kiểm thử tối thiểu

| Ca thử | Kích hoạt | Kết quả cần quan sát |
| --- | --- | --- |
| Event hợp lệ | Có `eventId`, schemaVersion được hỗ trợ | Xử lý một lần trong kịch bản bình thường; ack/commit theo policy |
| Contract invalid | JSON sai, thiếu `orderId` | Không gọi downstream; đưa DLT/DLQ với lý do rõ ràng |
| Transient HTTP failure | 503 trong 2 attempts đầu, sau đó 200 | Đúng số lần retry/backoff; xử lý thành công, không tạo DLQ |
| Retry exhausted | Downstream luôn 503 | Đưa DLT/DLQ một bản ghi logic có metadata; không lặp vô hạn |
| Timeout ambiguous | POST đã được nhận, response timeout | Retry cùng idempotency key; không tạo hai đơn hàng |
| DB commit rồi crash | Dừng consumer trước ack/commit | Broker có thể redeliver; unique key/inbox ngăn side effect thứ hai |
| DLT topic thiếu partition | Publish recoverer tới partition không có | Recover không được xem là thành công; báo cảnh báo và giữ khả năng xử lý lại |
| Rabbit DLX thiếu binding | Reject với `requeue=false` | Test phát hiện không có message ở DLQ; pipeline deployment phải ngăn phát hành |
| Rabbit requeue liên tục | Downstream lỗi kéo dài | Có giới hạn delivery/backoff; không có vòng lặp nóng |
| Kafka non-blocking ordering | Record A lỗi, record B cùng key đến sau | Đo hành vi lệch thứ tự; business version/conditional update bảo vệ kết quả |
| Consumer restart/rebalance | Dừng pod trong lúc processing | Không mất message đã cam kết giao nhận; số side effect đúng |
| Replay cùng event | Chọn một DLT record, publish lại | Giữ eventId; có replayRunId và audit; consumer không nhân đôi kết quả |
| DLT/DLQ retention | Chờ gần thời gian hết hạn hoặc vượt quota | Cảnh báo trước khi dữ liệu cần điều tra bị xóa |
| Message chứa PII | DLT lưu lỗi và payload | Không lộ token/password/stack trace nhạy cảm; có retention/access control |

### 9.2. Đo số attempts thật

Test cần phân biệt **lần xử lý đầu tiên** với **lần retry**. Ví dụ `FixedBackOff(1000L, 2L)` là 3 attempts, trong khi `@RetryableTopic(attempts="4")` là 4 attempts. Đo bộ đếm attempts từ adapter giả, không suy đoán qua số lần log exception bởi framework có thể log ở nhiều lớp.

Đặt timeout cho test vì broker có backoff và polling; dùng Awaitility hoặc cơ chế chờ điều kiện với deadline. Khi test thất bại phải thu thập nguyên nhân: record ở source/DLT, consumer offset, queue ready/unacked, incident store, cấu hình retry topic và broker logs. Test nên kiểm tra cả trường hợp **DLT publish fail**; nếu không, đường mất dữ liệu nguy hiểm nhất có thể không được phát hiện.

### 9.3. Kiểm tra ordering và tính lặp

Đưa vào một chuỗi theo cùng `aggregateId`: `OrderCreated(v1)`, `OrderPaid(v2)`, `OrderCancelled(v3)`; làm `v1` lỗi tạm rồi để `v2` và `v3` đi tiếp trong retry-topic mode. Kiểm tra consumer có xử lý theo version hay tạo trạng thái sai. Nếu thứ tự bắt buộc, phải phát hiện version gap và defer/reconcile thay vì chỉ hy vọng Kafka partition order vẫn được bảo toàn khi record đi qua topic khác.

Test duplicate cũng phải quan sát **DB row, HTTP side effect và broker output**, vì việc một listener được gọi hai lần là bình thường trong at-least-once. Thành công là **không tạo thêm tác dụng phụ logic**, chứ không phải “listener chỉ bao giờ chạy một lần”.

## 10. Observability và runbook vận hành

### 10.1. Metric và log đề xuất

| Tín hiệu | Ý nghĩa | Gợi ý cảnh báo |
| --- | --- | --- |
| `messages_processed_total{topic,result}` | Thành công, từ chối hợp lệ, lỗi tạm | Tỷ lệ lỗi tăng nhanh |
| `message_processing_duration_seconds{consumer}` | Độ trễ xử lý nghiệp vụ | P95/P99 vượt ngân sách |
| `message_retry_attempts_total{reason}` | Áp lực retry | Tăng đột biến hoặc retry storm |
| `message_dead_letter_total{reason}` | Số record vào DLT/DLQ | Liên tục tăng, đặc biệt lỗi schema |
| `dlt_publish_failures_total` | Không cách ly được record lỗi | Cảnh báo khẩn nếu có nguy cơ mất/khóa luồng |
| `dead_letter_backlog` và `oldest_age_seconds` | Quy mô và tuổi message chưa xử lý | Tiệm cận retention, SLA khôi phục |
| Kafka consumer lag | Khoảng cách giữa log và offset đã xử lý | Lag kéo dài hoặc partition bị chặn |
| Rabbit queue ready/unacked | Message chờ/đang xử lý | Queue tắc, prefetch/concurrency không phù hợp |
| `replay_submitted_total` / `replay_verified_total` | Phân biệt gửi lại và hoàn tất nghiệp vụ | Submitted nhiều nhưng verified thấp |
| `duplicate_suppressed_total` | Idempotency đang ngăn bản sao | Tăng bất thường có thể chỉ lỗi ack/retry |

Những metric trên là **đề xuất của ứng dụng**, không phải tên tự động tồn tại trong mọi Spring Boot/broker. Sử dụng tag cardinality thấp như topic, consumer group, operation, failure kind; tránh dùng `eventId`, raw payload, request ID hoặc exception message làm metric label. Log/tracing có thể dùng correlation ID với quyền truy cập/retention phù hợp, nhưng không ghi credentials, token hoặc dữ liệu cá nhân vào DLT headers.

### 10.2. Runbook khi DLT/DLQ tăng

1. Xác minh topic/queue nào tăng, lỗi chủ đạo là gì, từ khi nào và những phiên bản producer/consumer nào đang chạy.
2. Kiểm tra lag, số retries, tình trạng HTTP/DB/broker, disk/quota và khả năng publish sang DLQ/DLT.
3. Tách **lỗi hợp đồng** khỏi **lỗi hạ tầng**; ưu tiên ngừng retry storm trước khi sửa schema.
4. Đánh giá liệu có mất data, có áp dụng side effect rồi hay chưa; dùng business idempotency key/outbox để đối chiếu.
5. Sửa nguyên nhân, deploy và chạy canary bằng một số event lỗi đã được chọn; kiểm tra có xử lý được trước khi mở rộng replay.
6. Replay theo batch với rate limit, theo dõi submitted/verified/failures; dừng nếu xuất hiện lỗi mới, quá tải hoặc lệch thứ tự.
7. Đánh dấu incident hoàn tất và lưu bằng chứng; đối soát nguồn–đích để tìm record chưa có kết quả.

### 10.3. Các lỗi thiết kế nên tránh

**1. Retry vô hạn:** không bao giờ kết thúc khi lỗi schema, gây kẹt partition/queue và rút cạn thread. Phải có số lần, ngân sách thời gian và chính sách dead-letter.

**2. DLQ như nơi xóa message:** cấu hình `requeue=false` nhưng thiếu DLX/binding hoặc DLT topic, rồi coi message đã được bảo toàn. Hãy kiểm tra publish/route/confirm trong test triển khai.

**3. Nuốt exception trước khi broker ack:** `try/catch` chỉ log khiến listener trả về thành công, offset được commit hoặc queue message được ack; record lỗi biến mất khỏi tuyến recovery. Nếu intentionally quarantine, phải xác nhận đã lưu incident/message lỗi trước khi trả thành công.

**4. Phát lại làm mới business ID:** mỗi attempt có UUID mới làm vô hiệu idempotency và tạo double charge/double shipment. Replay phải giữ định danh logic, chỉ thêm replay metadata.

**5. Phụ thuộc vào thứ tự sau retry topic:** record bị chuyển sang topic khác có thể quay về sau event mới. Thiết kế version gating hoặc lựa chọn retry chiến lược khác.

**6. Thêm retry ở mọi tầng:** HTTP library, Spring service, consumer và broker cùng retry tạo traffic nhân theo cấp số. Chỉ định một tầng chịu trách nhiệm và có attempt budget xuyên suốt.

**7. Tin rằng dead-letter luôn bền vững:** DLX, DLT publishing và ack có failure mode riêng. Cần xác minh partition, binding, permissions, publisher confirms, serializer và retention.

**8. Để DLT giữ PII mãi mãi:** message lỗi vẫn phải đáp ứng chính sách phân quyền, encryption, dữ liệu nhạy cảm và retention; giới hạn stack trace và thông tin lỗi trong headers.

## 11. Ghi nhớ và câu hỏi tự kiểm tra

Một hệ thống nhắn tin đáng tin cậy cần giữ ba ranh giới riêng:

- **Broker delivery:** một record có được ack/commit, requeue hay publish sang DLT/DLQ đúng chính sách không?
- **Business effect:** message có thể được giao nhiều lần mà DB, HTTP API và broker downstream vẫn không tạo side effect trùng không?
- **Operational recovery:** có biết vì sao lỗi, lưu đủ dữ liệu để sửa, và replay theo phạm vi có thể kiểm soát không?

Tự trả lời:

1. Vì sao `DefaultErrorHandler(new FixedBackOff(1000, 2))` không có nghĩa tổng cộng chỉ hai lần xử lý?
2. Vì sao Kafka non-blocking retry có thể làm hỏng ordering theo cùng aggregate key?
3. Trong RabbitMQ, điều gì xảy ra nếu reject với `requeue=false` nhưng DLX không tồn tại?
4. Tại sao Spring Integration `errorChannel` không tự tương đương DLT/DLQ?
5. Vì sao một POST timeout phải được xem là “kết quả không chắc chắn”?
6. Tại sao publish từ DLT về topic nguồn tạo offset mới nhưng `eventId` phải giữ nguyên?
7. Điều kiện gì chứng minh một replay đã **verified** thay vì chỉ **submitted**?

## Tài liệu tham khảo

- [Spring Kafka — Handling Exceptions / DefaultErrorHandler](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html)
- [Spring Kafka — Retry Topic Configuration](https://docs.spring.io/spring-kafka/reference/retrytopic/retry-config.html)
- [Spring Kafka — Retry Features and Backoff](https://docs.spring.io/spring-kafka/reference/retrytopic/features.html)
- [Spring AMQP — Recovering from Errors and Broker Failures](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html)
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)
- [RabbitMQ — Quorum Queues and At-Least-Once Dead Lettering](https://www.rabbitmq.com/docs/quorum-queues)
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)




