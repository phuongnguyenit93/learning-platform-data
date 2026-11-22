# Log transaction id

Trong Spring Kafka, khi một message được gửi bằng Kafka transaction, việc ghi log đúng **transaction identity** giúp nối các sự kiện ở producer, broker, listener container và consumer group trong cùng một cuộc điều tra. Khi gặp lỗi như transaction abort, timeout hoặc `ProducerFencedException`, log cần cho biết producer nào đang giao dịch, thao tác nghiệp vụ nào liên quan, record nào được xử lý và transaction kết thúc với kết quả gì.

Tuy nhiên, cụm từ **transaction ID** thường bị dùng cho nhiều giá trị khác nhau. Trong Kafka, `transactional.id` là định danh ổn định của một transactional producer, được dùng để nhận diện producer qua các lần khởi động và hỗ trợ fencing. Nó **không phải một ID mới cho mỗi lần commit transaction**. Một producer có cùng `transactional.id` có thể thực hiện nhiều transaction nối tiếp. Kafka còn có producer ID và epoch do broker quản lý; ứng dụng thường không cần tự tạo các giá trị đó.

Để chẩn đoán tốt, cần log riêng:

- **Kafka transactional.id:** định danh producer transactional được cấu hình/cấp phát bởi producer factory.
- **Transaction attempt ID:** mã ứng dụng tạo cho một lần xử lý/giao dịch cụ thể.
- **Event ID:** định danh nghiệp vụ ổn định của message, giữ nguyên qua retry/re-drive.
- **Trace ID / Span ID:** định danh hoạt động quan sát phân tán.
- **Consumer group, topic, partition, offset:** vị trí và ngữ cảnh tiêu thụ.
- **Transaction outcome:** commit, rollback/abort hoặc unknown/failure.

Bài này thuộc chủ đề **Logging và chẩn đoán** trong Spring Kafka Reliability Operations. Mục tiêu là xây dựng log có thể truy vết một transaction qua producer, consumer listener, transaction completion, retry và DLT mà không nhầm transaction identity với business identity.

## 1. Transaction ID trong Kafka có nghĩa gì?

Kafka producer transaction sử dụng cấu hình `transactional.id`. Producer gửi ID này tới transaction coordinator để khởi tạo và quản lý transaction.

Ví dụ:

~~~properties
transactional.id=orders-service-pod-7-0
~~~

Định danh này gắn với **một logical producer identity**. Producer có thể thực hiện nhiều chu kỳ:

    transactional.id = orders-service-pod-7-0

    initTransactions()
       |
       +--> beginTransaction() -> send A -> commitTransaction()
       |
       +--> beginTransaction() -> send B -> commitTransaction()
       |
       +--> beginTransaction() -> send C -> abortTransaction()

Ba transaction trên cùng sử dụng một transactional.id. Vì vậy, nếu log chỉ ghi transactional.id, ta biết producer identity nhưng chưa biết lần giao dịch cụ thể nào đã lỗi.

Khi cần phân biệt từng lần thử, ứng dụng nên tạo thêm một **transactionAttemptId** riêng. ID này là metadata quan sát do ứng dụng quản lý, không thay thế Kafka transactional.id và không được gửi vào cấu hình Kafka producer.

## 2. Phân biệt các loại ID

| Giá trị | Phạm vi | Có thay đổi qua retry? | Dùng để |
|---|---|---|---|
| `transactional.id` | Logical transactional producer | Thường giữ ổn định trong vòng đời producer identity | Fencing, khôi phục producer transaction |
| Producer ID | Broker cấp cho producer | Có thể thay đổi khi identity được khởi tạo lại theo protocol | Nhận diện producer ở protocol |
| Producer epoch | Broker quản lý theo producer identity | Tăng khi producer identity được fencing/reinitialized | Chặn producer cũ |
| Transaction attempt ID | Một lần xử lý/giao dịch do ứng dụng đặt | Nên tạo mới cho mỗi attempt | Tìm log của một lần thử |
| Event ID | Một sự kiện nghiệp vụ | Giữ nguyên qua retry/re-drive của cùng event | Idempotency, audit |
| Correlation ID | Một workflow nghiệp vụ | Thường giữ qua nhiều event trong workflow | Ghép các bước nghiệp vụ |
| Trace ID | Một distributed trace | Có thể thay đổi khi retry/re-drive tạo trace mới | Truy vết spans |
| Consumer group ID | Nhóm consumer | Giữ theo cấu hình group | Theo dõi offset và assignment |

Không dùng `transactional.id` làm event ID. Không dùng trace ID làm idempotency key. Không dùng producer ID/epoch thay cho mã giao dịch nghiệp vụ.

## 3. Vì sao Kafka cần transactional.id?

Transactional ID cho phép Kafka nhận diện một producer transactional qua những lần tạo producer. Khi một producer mới khởi tạo với cùng transactional.id, broker có thể tăng epoch và **fence** producer cũ.

Ví dụ:

    Producer cũ A:
      transactional.id = orders-pod-7-0
      producerId = 1234
      epoch = 4

    Producer mới B khởi tạo cùng transactional.id:
      transactional.id = orders-pod-7-0
      broker cấp epoch mới

    Producer A dùng epoch cũ:
      -> bị fencing
      -> không được tiếp tục commit như producer hợp lệ

Fencing bảo vệ tính đúng đắn của transaction khi producer cũ còn sống nhưng đã mất quyền điều khiển hợp lệ, chẳng hạn process cũ bị network partition trong khi instance mới tiếp quản cùng identity.

Khi điều tra, log transactional.id giúp tìm producer identity bị xung đột. Nhưng để biết lần nghiệp vụ nào đang chạy, vẫn cần transactionAttemptId, eventId và trace context.

## 4. Spring Kafka tạo transactional.id như thế nào?

Trong Spring Kafka, transactional producer thường được tạo thông qua `ProducerFactory`. Với `DefaultKafkaProducerFactory`, ứng dụng có thể cấu hình một transaction ID prefix. Factory dùng prefix cùng suffix do nó quản lý để tạo transactional producer IDs phù hợp với các producer được cache/tạo.

Spring Boot thường cấu hình prefix qua:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-service-${INSTANCE_ID}-
~~~

Ở đây `INSTANCE_ID` là biến môi trường do deployment cung cấp, ví dụ pod identity. Prefix cần **duy nhất giữa các application instance đang hoạt động** nếu những instance đó dùng cùng Kafka cluster và cùng producer identity namespace.

Không nên cấu hình một prefix tĩnh giống hệt nhau cho mọi pod nếu factory có thể tạo các transactional IDs va chạm. Producer fencing liên tục có thể xảy ra khi các instance cùng sử dụng một transactional.id.

Lưu ý:

- Prefix là phần đầu của transactional IDs do factory tạo.
- Factory có thể thêm suffix và quản lý cache/suffix reuse.
- Không nên tự ghép prefix với số thread rồi khẳng định đã biết chính xác transactional.id runtime.
- Hãy kiểm tra cấu hình và API của Spring Kafka version thực tế.
- Không tự đặt cùng một transactional.id cho nhiều producer hoạt động đồng thời.

## 5. Không nhầm transaction ID với transaction attempt ID

Giả sử một listener xử lý record có eventId `evt-901`. Lần đầu transaction abort vì database/API lỗi; lần sau consumer redeliver record và xử lý thành công.

    Kafka transactional.id: orders-worker-pod-2-0

    Attempt 1:
      transactionAttemptId = txa-01
      eventId = evt-901
      outcome = ABORTED

    Attempt 2:
      transactionAttemptId = txa-02
      eventId = evt-901
      outcome = COMMITTED

Transactional ID giống nhau vì cùng logical producer identity. Attempt ID khác nhau vì đây là hai lần thực thi. Event ID giữ nguyên vì vẫn là cùng sự kiện nghiệp vụ.

Cấu trúc log như vậy giúp trả lời ba câu hỏi:

1. Producer identity nào đang gặp vấn đề?
2. Lần thử nào commit/abort?
3. Record nghiệp vụ nào được xử lý lại?

Nếu chỉ log transactional.id, hai attempt có thể bị gộp vào một dòng sự kiện khó phân biệt.

## 6. Những trường nên có trong log transaction

Một log có ích thường có các trường sau:

| Field | Ví dụ | Mục đích |
|---|---|---|
| `kafka.transactional_id` | `orders-pod-2-0` | Producer identity |
| `app.transaction_attempt_id` | `txa-7f3...` | Một lần thực thi |
| `event.id` | `evt-901` | Sự kiện nghiệp vụ |
| `correlation.id` | `order-flow-55` | Workflow |
| `trace_id` | `4bf9...` | Distributed trace |
| `span_id` | `00f0...` | Span hiện tại |
| `kafka.topic` | `orders.created` | Topic nguồn/đích |
| `kafka.partition` | `2` | Partition |
| `kafka.offset` | `901` | Offset nguồn |
| `kafka.group_id` | `orders-worker` | Consumer group |
| `transaction.phase` | `begin/send/commit/abort` | Giai đoạn |
| `transaction.outcome` | `COMMITTED` | Kết quả cuối |
| `error.type` | `ProducerFencedException` | Phân loại lỗi |

Không phải mọi log đều cần tất cả field. Log `begin` có thể chưa biết topic offset; log từ consumer cần group/topic/partition/offset; log producer cần destination topic và event ID.

Dùng structured logging để lưu field tách biệt. Tránh ghép toàn bộ thành một message string nếu hệ thống log cần filter hoặc aggregate theo field.

## 7. Log transaction ID không có nghĩa ghi payload

Để điều tra transaction, không cần log toàn bộ message value. Payload có thể chứa thông tin khách hàng, thanh toán, địa chỉ hoặc token.

Nên ghi:

- Event ID đã được chuẩn hóa.
- Topic, partition, offset.
- Key nếu key không chứa dữ liệu nhạy cảm.
- Transactional ID hoặc producer identity.
- Transaction attempt ID.
- Trace ID và error class.
- Outcome và thời gian.

Tránh ghi:

- Password, access token, API key.
- Số thẻ, thông tin thanh toán hoặc dữ liệu cá nhân không cần thiết.
- Toàn bộ payload JSON ở mọi lần retry.
- Baggage/headers chưa được kiểm soát.
- Secret từ Kafka producer/consumer properties.

Transactional ID thường là metadata vận hành, không phải credential. Tuy vậy, vẫn nên tuân thủ chính sách log retention và quyền truy cập vì nó có thể tiết lộ tên service, pod và cấu trúc triển khai.

## 8. Cấu hình Kafka transaction trong Spring Boot

Ví dụ cấu hình producer transactional:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: orders-service-${INSTANCE_ID}-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        acks: all
        enable.idempotence: true
    consumer:
      group-id: orders-worker
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
    listener:
      ack-mode: record
~~~

Giải thích:

- `transaction-id-prefix` làm producer factory tạo transactional producers.
- `enable-auto-commit=false` tránh consumer offset được tự commit ngoài container/transaction.
- `isolation.level=read_committed` khiến downstream consumer chỉ nhận output transactional đã commit.
- `acks=all` và idempotence hỗ trợ độ bền/an toàn producer theo cấu hình cluster.
- `ack-mode` điều khiển cách container quản lý acknowledgment; khi dùng transaction, offset có thể được gửi vào Kafka transaction theo lifecycle container.

Spring Boot auto-configuration có thể tạo KafkaTransactionManager khi transaction prefix được cấu hình, tùy phiên bản và cách ứng dụng tùy biến factory. Nếu tự tạo listener container factory hoặc ProducerFactory, phải xác nhận transaction manager và KafkaTemplate thực tế tham gia đúng transaction.

## 9. Tạo transaction attempt ID ở tầng ứng dụng

Kafka không cấp một chuỗi mới cho mỗi lần gọi beginTransaction theo kiểu transactionAttemptId của nghiệp vụ. Nếu muốn log mỗi attempt riêng, ứng dụng có thể tạo UUID trước khi bắt đầu một thao tác.

Ví dụ service gửi event trong Kafka transaction:

~~~java
@Service
public class OrderPublisher {

    private static final Logger log =
            LoggerFactory.getLogger(OrderPublisher.class);

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publish(OrderEvent event) {

        String attemptId = UUID.randomUUID().toString();

        log.info(
            "Kafka transaction work started: attemptId={}, eventId={}, topic={}",
            attemptId,
            event.eventId(),
            "orders.created"
        );

        kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
        );

        registerTransactionCompletion(attemptId, event.eventId());
    }

    private void registerTransactionCompletion(
            String attemptId,
            String eventId) {

        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            log.warn(
                "No transaction synchronization active: attemptId={}, eventId={}",
                attemptId,
                eventId
            );
            return;
        }

        TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void afterCompletion(int status) {
                    String outcome = switch (status) {
                        case STATUS_COMMITTED -> "COMMITTED";
                        case STATUS_ROLLED_BACK -> "ROLLED_BACK";
                        default -> "UNKNOWN";
                    };

                    log.info(
                        "Kafka transaction completed: attemptId={}, eventId={}, outcome={}",
                        attemptId,
                        eventId,
                        outcome
                    );
                }
            }
        );
    }
}
~~~

Các import chính:

~~~java
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
~~~

Đây là ví dụ cho Spring Kafka/Spring Framework có hỗ trợ API trên và một transaction manager tên `kafkaTransactionManager`. Event DTO có `eventId()`, `orderId()` theo mô hình minh họa.

Điểm quan trọng: `afterCompletion` chạy khi Spring transaction hoàn tất. Vì vậy log này phản ánh trạng thái transaction manager báo về sau completion, thay vì suy luận commit chỉ từ việc method `send()` đã được gọi.

## 10. Vì sao phải log sau transaction completion?

Đoạn sau chưa đủ để kết luận transaction đã commit:

~~~java
kafkaTemplate.send("orders.created", key, event);
log.info("Kafka transaction committed");
~~~

`send()` thường trả về một future. Việc gọi method thành công không có nghĩa broker đã nhận record và transaction đã commit. Producer có thể gặp lỗi send, timeout hoặc transaction commit thất bại sau đó.

Nên phân biệt các mốc:

    T0: Kafka transaction bắt đầu
    T1: KafkaTemplate.send() được gọi
    T2: Producer nhận kết quả send
    T3: Listener/service hoàn tất
    T4: Transaction manager commit hoặc abort
    T5: afterCompletion log outcome

Log tại T1 nên là `send_requested`. Log tại T2 có thể là `send_acknowledged` nếu future hoàn tất thành công. Chỉ log `COMMITTED` sau khi transaction completion xác nhận commit.

Với `@Transactional`, interceptor thường commit sau khi method body trả về. Do đó, log "method finished" ở cuối method vẫn có thể xảy ra **trước** khi transaction commit.

## 11. Ghi log send result riêng với transaction outcome

Có thể gắn callback vào future để ghi nhận kết quả gửi record:

~~~java
CompletableFuture<SendResult<String, OrderEvent>> future =
        kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
        );

future.whenComplete((result, error) -> {
    if (error != null) {
        log.error(
            "Kafka send failed: attemptId={}, eventId={}, topic={}",
            attemptId,
            event.eventId(),
            "orders.created",
            error
        );
    }
    else {
        RecordMetadata metadata = result.getRecordMetadata();

        log.info(
            "Kafka send acknowledged: attemptId={}, eventId={}, topic={}, partition={}, offset={}",
            attemptId,
            event.eventId(),
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    }
});
~~~

Imports:

~~~java
import java.util.concurrent.CompletableFuture;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.support.SendResult;
~~~

Đoạn này cần đặt trong method có biến `attemptId` và `event`. Spring Kafka 3.x sử dụng CompletableFuture cho send APIs; ở version cũ, kiểu future có thể khác.

Hai kết quả cần được log riêng:

- Send future thành công: broker đã xác nhận send theo producer API.
- Transaction commit thành công: transaction coordinator đã hoàn tất transaction.

Trong transaction, record được gửi thành công nhưng sau đó transaction abort thì downstream `read_committed` không coi record đó là output committed.

Callback future có thể chạy trên thread khác. Nếu log cần trace context hoặc MDC, phải truyền context phù hợp qua callback; không giả định thread-local luôn được giữ.

## 12. Dùng MDC để gắn attempt ID vào mọi log trong scope

Mapped Diagnostic Context (MDC) giúp bổ sung field vào các log phát sinh trong cùng thread. Có thể đặt transactionAttemptId, eventId và correlationId trước khi xử lý.

~~~java
String previousAttempt = MDC.get("transactionAttemptId");
String previousEvent = MDC.get("eventId");

try {
    MDC.put("transactionAttemptId", attemptId);
    MDC.put("eventId", event.eventId());

    log.info("Starting Kafka transactional publish");

    kafkaTemplate.send("orders.created", event.orderId(), event);
}
finally {
    restoreMdc("transactionAttemptId", previousAttempt);
    restoreMdc("eventId", previousEvent);
}

private void restoreMdc(String key, String previousValue) {
    if (previousValue == null) {
        MDC.remove(key);
    }
    else {
        MDC.put(key, previousValue);
    }
}
~~~

Import:

~~~java
import org.slf4j.MDC;
~~~

Đây là pattern minh họa; trong code thật, method helper phải nằm trong class và phần transaction completion phải được đăng ký trước khi method trả về.

**Phải khôi phục MDC cũ** thay vì chỉ gọi MDC.clear() nếu scope có thể chạy bên trong một context lớn hơn. Thread pool tái sử dụng thread; nếu không dọn MDC đúng cách, log của request tiếp theo có thể mang ID của request trước.

MDC thường gắn với thread. Nó không tự truyền qua executor, CompletableFuture hoặc callback chạy trên thread khác.

## 13. Log sau completion khi MDC đã được dọn

Một chi tiết dễ bỏ sót: với `@Transactional`, `afterCompletion` thường chạy sau khi method body kết thúc. Nếu MDC được khôi phục trong finally trước khi transaction interceptor commit, callback có thể không còn thấy attempt ID trong MDC.

Cách an toàn là **capture ID trong closure** và truyền trực tiếp vào log completion:

~~~java
String attemptId = UUID.randomUUID().toString();

TransactionSynchronizationManager.registerSynchronization(
    new TransactionSynchronization() {
        @Override
        public void afterCompletion(int status) {
            log.info(
                "Kafka transaction outcome: attemptId={}, status={}",
                attemptId,
                status
            );
        }
    }
);
~~~

Không cần giữ MDC mở trên consumer thread chỉ để callback có thể đọc lại. Giữ dữ liệu cần thiết trong biến bất biến làm rõ ownership của context và giảm nguy cơ rò rỉ giữa các record.

Nếu transaction synchronization không active, cần log một cảnh báo cấu hình hoặc dùng cơ chế instrumentation khác; đừng giả vờ đã quan sát được commit outcome.

## 14. Log transactional.id runtime bằng ProducerFactory listener

Trong Spring Kafka, `ProducerFactory` quản lý việc tạo và đóng Kafka producer. Các phiên bản hỗ trợ `ProducerFactory.Listener` cung cấp callback khi producer được thêm hoặc loại bỏ khỏi factory.

Ví dụ:

~~~java
producerFactory.addListener(
    new ProducerFactory.Listener<String, OrderEvent>() {

        @Override
        public void producerAdded(
                String id,
                Producer<String, OrderEvent> producer) {

            log.info(
                "Kafka producer added to factory: producerFactoryId={}",
                id
            );
        }

        @Override
        public void producerRemoved(
                String id,
                Producer<String, OrderEvent> producer) {

            log.info(
                "Kafka producer removed from factory: producerFactoryId={}",
                id
            );
        }
    }
);
~~~

Imports:

~~~java
import org.apache.kafka.clients.producer.Producer;
import org.springframework.kafka.core.ProducerFactory;
~~~

Đoạn này giả định ứng dụng đang cấu hình custom ProducerFactory và đăng ký listener trên factory thực sự được KafkaTemplate sử dụng. API listener và ý nghĩa chính xác của tham số `id` cần đối chiếu Javadoc của Spring Kafka version đang chạy. Trong một số triển khai, giá trị là ID mà factory dùng để quản lý producer; **không tự khẳng định nó là transactional.id nếu contract version không nói rõ**.

Nếu mục tiêu là log transactional.id thực tế, hãy dùng callback/API được version đó tài liệu hóa cho transactional producer identity hoặc log thông tin từ Kafka client ở mức phù hợp. Không suy ra ID hoàn chỉnh chỉ bằng cách nối prefix với một số thread do ứng dụng tự đặt.

## 15. Log prefix và runtime producer identity khác nhau

Cấu hình:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-service-pod-7-
~~~

chỉ cho biết prefix. Factory có thể thêm suffix để tạo các producer identity riêng, và có thể quản lý suffix theo cache lifecycle.

Một log:

~~~text
transactionIdPrefix=orders-service-pod-7-
~~~

không tương đương:

~~~text
transactional.id=orders-service-pod-7-0
~~~

Nếu cần truy vết chính xác producer đã bị fencing, log factory prefix hữu ích để khoanh vùng instance nhưng có thể chưa đủ để nhận diện producer cụ thể.

Nên log đồng thời:

- service.name và instance/pod ID.
- transaction-id prefix từ cấu hình đã chuẩn hóa.
- producer factory identifier nếu callback cung cấp.
- Kafka client ID.
- transactional.id thực tế nếu có API/log được version hỗ trợ.
- transactionAttemptId cho từng lần xử lý.

## 16. Đặt transaction ID vào structured log

Với JSON logging, nên dùng các field độc lập:

~~~json
{
  "level": "INFO",
  "message": "Kafka transaction completed",
  "service": "orders-service",
  "instance": "orders-service-pod-7",
  "kafka.transactional_id": "orders-service-pod-7-0",
  "app.transaction_attempt_id": "txa-7f3c",
  "event.id": "evt-901",
  "kafka.topic": "orders.created",
  "transaction.outcome": "COMMITTED"
}
~~~

Đây là ví dụ cấu trúc, không phải dữ liệu từ một hệ thống thật.

Ưu điểm:

- Có thể filter theo transactional.id khi điều tra fencing.
- Có thể group theo attempt ID để tìm log start/send/commit.
- Có thể tra eventId qua retry và DLT.
- Có thể join log với traceId.
- Có thể query theo topic/partition/offset.

Tên field nên thống nhất giữa service. Ví dụ service A dùng `transactionId`, service B dùng `tx_id`, service C dùng `kafkaTxn` sẽ khiến dashboard và truy vấn khó bảo trì.

## 17. Log transaction begin, send, commit và abort

Một quy ước event log dễ đọc:

| Event name | Khi nào ghi | Nội dung chính |
|---|---|---|
| `kafka.transaction.begin` | Khi transaction scope bắt đầu | attempt ID, producer identity nếu có |
| `kafka.record.send.requested` | Khi gọi send | topic, event ID, key an toàn |
| `kafka.record.send.acknowledged` | Khi send future thành công | topic, partition, offset |
| `kafka.transaction.commit` | Khi transaction completion xác nhận commit | attempt ID, duration |
| `kafka.transaction.rollback` | Khi transaction completion xác nhận rollback | attempt ID, exception category |
| `kafka.transaction.outcome_unknown` | Khi client không thể xác định chắc chắn outcome | attempt ID, error, recovery action |

Không phải mọi transaction manager đều cung cấp callback cho mọi giai đoạn với cùng semantics. Có thể phải kết hợp application logging, Spring transaction synchronization và Kafka client logs.

Tránh ghi `commit` ngay sau `send()`. Hãy dùng tên `send_requested` hoặc `send_acknowledged` cho đúng mốc.

## 18. Đo transaction duration

Có thể ghi thời điểm bắt đầu và tính duration tại callback completion:

~~~java
long startedNanos = System.nanoTime();
String attemptId = UUID.randomUUID().toString();

TransactionSynchronizationManager.registerSynchronization(
    new TransactionSynchronization() {
        @Override
        public void afterCompletion(int status) {
            long durationNanos = System.nanoTime() - startedNanos;

            log.info(
                "Kafka transaction completed: attemptId={}, status={}, durationMs={}",
                attemptId,
                status,
                TimeUnit.NANOSECONDS.toMillis(durationNanos)
            );
        }
    }
);
~~~

Imports:

~~~java
import java.util.concurrent.TimeUnit;
~~~

Dùng `System.nanoTime()` để đo duration vì nó là đồng hồ đơn điệu phù hợp cho khoảng thời gian. Dùng `Instant.now()` hoặc timestamp log để ghi thời điểm wall-clock.

Duration ở callback Spring transaction là thời gian từ lúc bắt đầu đo tới completion callback, có thể bao gồm business processing, send, commit/abort và các callback synchronization khác tùy vị trí đăng ký. Ghi rõ phạm vi metric là `application_transaction_scope_duration`, không tự gọi nó là broker-only commit latency.

Nếu cần đo riêng thời gian coordinator commit, dùng Kafka client metrics hoặc instrumentation phù hợp ở tầng producer/transaction manager.

## 19. Gắn event ID và Kafka record coordinates

Trong consumer listener, log record coordinates để tìm lại message trong Kafka:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "orders-worker"
)
public void consume(ConsumerRecord<String, OrderEvent> record) {

    OrderEvent event = record.value();

    log.info(
        "Consuming Kafka record: eventId={}, topic={}, partition={}, offset={}, key={}",
        event.eventId(),
        record.topic(),
        record.partition(),
        record.offset(),
        safeKey(record.key())
    );

    orderService.process(event);
}
~~~

`safeKey` là helper ứng dụng quyết định có thể log key hay cần mask. Nếu key chứa email/customer identifier hoặc thông tin nhạy cảm, không log raw value.

Các coordinates topic/partition/offset rất hữu ích khi tra consumer lag, DLT metadata và redelivery. Offset là duy nhất trong một partition, không phải duy nhất trên toàn topic; luôn log cả topic và partition.

Khi listener chạy lại cùng record, eventId và coordinates có thể giống nhau, trong khi transactionAttemptId nên khác nhau cho mỗi attempt.

## 20. Consumer transaction: log group và source offset

Với transactional listener, Kafka output và input offsets có thể nằm trong cùng Kafka transaction. Khi log cần thể hiện mối liên hệ đó:

    Transaction attempt txa-01
      groupId = orders-worker
      input = orders.created-2@901
      output = orders.validated-1@440
      outcome = COMMITTED

Nếu transaction abort:

    Transaction attempt txa-02
      groupId = orders-worker
      input = orders.created-2@901
      output send was acknowledged
      outcome = ROLLED_BACK

Consumer có thể redeliver offset 901 trong lần thử tiếp theo. Output của transaction abort không được downstream `read_committed` coi là committed.

Đừng log offset nguồn là committed ngay khi listener method hoàn tất. Trong container-managed transaction, container gửi offsets vào transaction và commit sau đó. Cần log outcome ở điểm completion phù hợp.

Nếu một poll chứa nhiều record, transaction boundary có thể bao phủ nhiều record tùy listener type/configuration. Khi đó, log cần có danh sách hoặc summary coordinates phù hợp, tránh giả định một transaction chỉ chứa đúng một offset.

## 21. Xử lý retry: giữ event ID, tạo attempt ID mới

Một record có thể được retry nhiều lần:

    eventId = evt-901

    attemptId = txa-A -> exception -> rollback
    attemptId = txa-B -> timeout   -> rollback
    attemptId = txa-C -> success   -> commit

Điều cần giữ ổn định:

- eventId.
- Original topic/partition/offset (nếu vẫn xử lý cùng record).
- Business correlation ID.
- Payload identity hoặc schema version phù hợp.

Điều thường thay đổi:

- transactionAttemptId.
- spanId.
- Consumer instance/client ID nếu rebalance sang pod khác.
- Delivery attempt count.
- Thời gian xử lý và exception.

Nếu retry topic tạo một record mới ở topic khác, log cả original source coordinates và current retry topic coordinates. Không chỉ log topic hiện tại, vì khi điều tra cần biết record bắt đầu từ đâu.

## 22. Log khi transaction bị abort

Một log rollback nên cho biết:

- attempt ID.
- transactional.id/producer identity nếu xác định được.
- event ID và source coordinates.
- Exception class.
- Retry attempt/backoff nếu có.
- Transaction outcome.
- Consumer group và instance.
- Correlation/trace IDs.

Ví dụ:

~~~text
level=WARN
event=kafka.transaction.rollback
transactionAttemptId=txa-02
transactionalId=orders-pod-7-0
eventId=evt-901
sourceTopic=orders.created
sourcePartition=2
sourceOffset=901
groupId=orders-worker
exception=TransientDataAccessException
outcome=ROLLED_BACK
~~~

Không ghi payload hoặc stack trace đầy đủ ở mọi lần retry nếu log volume lớn. Có thể ghi exception class và stack trace ở lần đầu/lần cuối hoặc theo sampling policy, đồng thời giữ đủ thông tin để truy xuất lỗi.

Rollback không tự nói rằng listener không thực hiện side effect bên ngoài Kafka. Nếu DB/API đã thành công trước khi Kafka transaction abort, cần idempotency và log business outcome riêng.

## 23. Log ProducerFencedException

Một trong những lỗi quan trọng liên quan transactional.id là `ProducerFencedException`.

Ví dụ xử lý lỗi ở application boundary:

~~~java
try {
    publisher.publish(event);
}
catch (ProducerFencedException exception) {
    log.error(
        "Kafka transactional producer fenced: eventId={}, instance={}",
        event.eventId(),
        instanceId,
        exception
    );
    throw exception;
}
~~~

ProducerFencedException có thể xuất hiện qua wrapper/exception khác tùy đường commit và Spring Kafka version. Trong thực tế, kiểm tra cause chain để xác định exception gốc thay vì chỉ so sánh top-level type.

Điều tra:

1. Log transactional.id hoặc producer factory identity.
2. So sánh instance/pod đang dùng cùng identity.
3. Kiểm tra rolling deployment và zombie producer.
4. Kiểm tra transaction-id-prefix có unique theo instance không.
5. Xem producer lifecycle/cache và thời điểm producer mới khởi tạo.
6. Xác nhận consumer group và transaction outcome.
7. Sửa identity/lifecycle trước khi restart liên tục.

Không tự retry ngay với cùng một producer đã bị fencing. Producer cũ không thể trở thành hợp lệ bằng cách lặp lại cùng thao tác commit.

## 24. Log timeout và outcome không chắc chắn

Một timeout khi commit transaction không phải lúc nào cũng chứng minh broker chưa commit. Response có thể bị mất sau khi broker đã hoàn tất hoặc trạng thái client không còn xác định.

Ví dụ log nên phân biệt:

~~~text
event=kafka.transaction.commit_attempt
transactionAttemptId=txa-77
outcome=UNKNOWN
error=TimeoutException
action=inspect_before_retry
~~~

Đừng log `ABORTED` chỉ vì client không nhận response commit. Nếu broker đã commit, retry business command với một event ID mới có thể tạo output trùng.

Khi outcome không rõ:

- Giữ eventId/commandId ổn định.
- Kiểm tra transaction/client logs và downstream read_committed nếu có thể.
- Dùng idempotent consumer ở downstream.
- Dựa vào trạng thái nghiệp vụ/audit để reconciliation.
- Không tự ý commit source offset hoặc bỏ qua record.
- Thiết kế retry sao cho cùng business command không tạo side effect trùng.

Kafka transaction protocol xử lý nhiều lỗi nội bộ, nhưng ứng dụng vẫn cần log trạng thái không chắc chắn trung thực.

## 25. Logging với KafkaTemplate.executeInTransaction

KafkaTemplate cung cấp `executeInTransaction` cho một số producer-initiated use cases, tạo một transaction cục bộ cho callback.

Ví dụ:

~~~java
public void publish(OrderEvent event) {

    String attemptId = UUID.randomUUID().toString();

    kafkaTemplate.executeInTransaction(operations -> {
        log.info(
            "Kafka transaction callback started: attemptId={}, eventId={}",
            attemptId,
            event.eventId()
        );

        operations.send(
            "orders.created",
            event.orderId(),
            event
        );

        return null;
    });

    log.info(
        "Kafka executeInTransaction returned: attemptId={}, eventId={}",
        attemptId,
        event.eventId()
    );
}
~~~

Ở đây log sau `executeInTransaction` trả về chỉ được ghi nếu callback/transaction hoàn tất bình thường theo contract API. Nếu exception xảy ra, dòng log đó không chạy trừ khi có finally/catch riêng.

Cần phân biệt API này với một method `@Transactional` tham gia KafkaTransactionManager. `executeInTransaction` có semantics riêng và không nên giả định nó tham gia transaction đang hoạt động giống một `KafkaTemplate.send()` thông thường.

Đối với code cần log commit/abort chi tiết, kết hợp exception handling và timing quanh lời gọi, đồng thời kiểm tra API version.

## 26. Logging với @Transactional và KafkaTransactionManager

Một method có thể khai báo rõ transaction manager:

~~~java
@Transactional(transactionManager = "kafkaTransactionManager")
public void publish(OrderEvent event) {
    kafkaTemplate.send("orders.created", event.orderId(), event);
}
~~~

Điều này yêu cầu:

- KafkaTransactionManager được cấu hình.
- ProducerFactory có transactional capability.
- KafkaTemplate sử dụng ProducerFactory phù hợp.
- Method được gọi qua Spring proxy.
- Exception cần rollback không bị catch rồi nuốt.
- Transaction boundary được hiểu đúng nếu method tham gia một transaction đang tồn tại.

Khi method được gọi qua proxy, interceptor bắt đầu/commit transaction quanh method invocation. Log ở đầu method là log bắt đầu business work; log ở cuối body có thể vẫn xảy ra trước commit. Muốn log completion, dùng transaction synchronization hoặc instrumentation tại transaction manager.

Nếu có nhiều transaction managers, luôn chỉ rõ tên manager trong annotation để tránh log một transaction database rồi gọi nhầm đó là Kafka transaction.

## 27. Transaction name của Spring có thay transactional.id không?

Spring có thể cung cấp transaction name hiện tại thông qua TransactionSynchronizationManager trong một số transaction context:

~~~java
String springTransactionName =
        TransactionSynchronizationManager.getCurrentTransactionName();
~~~

Giá trị này thuộc **Spring transaction metadata**, không nhất thiết là Kafka transactional.id. Nó có thể là tên method/class được transaction interceptor sử dụng hoặc null tùy context.

Có thể log riêng:

~~~text
spring.transaction.name=OrderPublisher.publish
kafka.transactional.id=orders-pod-7-0
app.transaction_attempt_id=txa-77
~~~

Không đặt field `transactional.id` bằng `getCurrentTransactionName()`. Hai giá trị trả lời hai câu hỏi khác nhau.

Tương tự, `TransactionSynchronizationManager.isActualTransactionActive()` chỉ cho biết Spring có actual transaction active trong thread context, không xác nhận broker đã commit.

## 28. Logging producer ID và epoch

Kafka broker quản lý producer ID và epoch cho transactional producer. Producer fencing có liên quan đến epoch, vì broker từ chối producer cũ sau khi identity được khởi tạo lại.

Các giá trị này hữu ích khi đọc Kafka client/broker logs, nhưng Kafka Producer public API không cung cấp một getter đơn giản, portable để ứng dụng lấy producer ID/epoch của mọi transaction.

Không nên dùng reflection để đọc private fields của KafkaProducer hoặc TransactionManager chỉ để đưa chúng vào log. Nội bộ client có thể đổi theo version, và truy cập không an toàn có thể làm hỏng producer.

Hướng tiếp cận:

- Dùng transactional.id/factory identity được framework hỗ trợ.
- Bật log Kafka client ở mức DEBUG/TRACE có kiểm soát khi điều tra.
- Dùng broker logs và metrics phù hợp để đối chiếu fencing.
- Ghi instance ID và transactionAttemptId ở tầng ứng dụng.
- Không tự tạo producer ID/epoch giả.

## 29. Bật log Kafka client có chọn lọc

Trong Spring Boot có thể tăng log level tạm thời cho những package liên quan:

~~~yaml
logging:
  level:
    org.springframework.kafka.transaction: DEBUG
    org.springframework.kafka.core.KafkaTemplate: DEBUG
    org.springframework.kafka.listener: INFO
    org.apache.kafka.clients.producer.internals.TransactionManager: DEBUG
    org.apache.kafka.clients.consumer.internals.ConsumerCoordinator: INFO
~~~

Tên logger và nội dung cụ thể phụ thuộc version. Một số package nội bộ Kafka không phải public API ổn định; khi nâng client, log có thể thay đổi.

Thực hành tốt:

1. Chỉ bật DEBUG/TRACE trong thời gian điều tra hoặc trên phạm vi instance cần thiết.
2. Ước lượng log volume trước khi bật ở toàn cluster.
3. Không log producer/consumer configs chứa credentials.
4. Thu thập đủ log trước/sau lỗi, không chỉ dòng exception cuối.
5. Hạ log level sau khi sự cố kết thúc.
6. Kết hợp structured application logs để truy vấn attempt/event ID.

Không bật TRACE liên tục cho mọi producer ở workload hàng chục nghìn message/giây nếu chưa đánh giá chi phí I/O và storage.

## 30. Log correlation ID và trace context cùng transaction ID

Một log tốt nối được cả vận hành Kafka lẫn tracing:

~~~text
service=orders-service
instance=orders-pod-7
transactionalId=orders-pod-7-0
transactionAttemptId=txa-77
eventId=evt-901
correlationId=order-flow-55
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=00f067aa0ba902b7
topic=orders.created
partition=2
offset=901
phase=commit
outcome=COMMITTED
~~~

Mỗi ID phục vụ một mục tiêu:

- transactionalId tìm producer identity.
- transactionAttemptId ghép các log trong một transaction attempt.
- eventId theo dõi cùng sự kiện qua retry/re-drive.
- correlationId theo dõi workflow nghiệp vụ.
- traceId/spanId mở distributed trace.
- topic/partition/offset tìm record trong Kafka.

Nếu dùng Micrometer Tracing, traceId/spanId có thể được đưa vào MDC theo cấu hình. Transaction attempt ID vẫn cần được quản lý riêng; không tự đặt traceId thành transactional.id.

## 31. Consumer retry và delivery attempt

Khi listener bị lỗi, Spring Kafka có thể retry theo DefaultErrorHandler hoặc AfterRollbackProcessor tùy loại container và transaction configuration. Một record có thể có nhiều lần delivery.

Log cần ghi:

~~~text
eventId=evt-901
sourceTopic=orders.created
sourcePartition=2
sourceOffset=901
deliveryAttempt=2
transactionAttemptId=txa-B
transactionalId=orders-worker-pod-2-0
outcome=ROLLED_BACK
exception=TransientDataAccessException
~~~

API lấy delivery attempt header phụ thuộc error handling/version. Nếu không có header hoặc API đáng tin cậy, có thể log retry stage từ error handler hoặc metadata ứng dụng đã được quản lý.

Không tăng attempt counter trong một biến RAM không gắn với record vì rebalance/restart có thể reset nó. Nếu cần số lần thử bền vững, dùng header/retry topic metadata hoặc state store có chính sách rõ.

Khi cùng record được xử lý lại ở pod khác, transactional.id có thể thay đổi do instance identity; eventId và source coordinates giúp nối hai lần xử lý.

## 32. DLT và re-drive cần log identity thế nào?

Khi record được chuyển sang DLT, giữ lại những thông tin cần điều tra:

- Event ID gốc.
- Original topic/partition/offset.
- Exception type và metadata an toàn.
- Transaction attempt ID của lần recovery.
- Transactional producer identity của recoverer nếu có.
- DLT topic/partition/offset.
- Recovery transaction outcome.
- Re-drive operation ID khi phát lại.

Ví dụ:

~~~text
event=kafka.dlt.recovery
eventId=evt-901
source=orders.created-2@901
destination=orders.created.DLT-2@44
transactionAttemptId=txa-recover-01
transactionalId=orders-recovery-pod-1-0
outcome=COMMITTED
~~~

Nếu DLT publish thành công nhưng source offset commit thất bại, record nguồn có thể redeliver và recovery có thể chạy lại. Cần thiết kế recovery idempotent và log cả hai tọa độ.

Không coi DLT record đã tồn tại là bằng chứng source offset đã commit. Hai thao tác chỉ nguyên tử khi được đưa vào cùng một Kafka transaction phù hợp.

## 33. Batch listener: một transaction có nhiều record

Với batch listener, một lần transaction có thể liên quan nhiều input records. Một transactionAttemptId có thể gắn với toàn bộ batch, trong khi mỗi record có eventId và coordinates riêng.

Ví dụ:

    transactionAttemptId = txa-batch-12

    inputs:
      orders.created-0@100 / evt-A
      orders.created-0@101 / evt-B
      orders.created-1@220 / evt-C

    outputs:
      orders.validated-0@500
      orders.validated-1@610

    outcome = COMMITTED

Không log một eventId duy nhất làm đại diện cho cả batch nếu batch chứa nhiều event. Có thể ghi batch size và summary, rồi log record-level detail theo mức cần thiết.

Nếu một record lỗi làm transaction abort, output của cả transaction có thể bị abort; log cần cho biết transactionAttemptId chung và record gây lỗi nếu framework cung cấp chính xác thông tin đó.

## 34. Kafka transaction với database transaction

Một listener có thể vừa ghi database vừa publish Kafka output. Hai resource manager có transaction riêng nếu không dùng một distributed transaction protocol được cấu hình đầy đủ.

Ví dụ:

    DB transaction:
      UPDATE orders

    Kafka transaction:
      send orders.updated

Nếu Kafka commit abort sau khi database đã commit, database change không tự rollback. Khi record nguồn redeliver, side effect DB có thể chạy lại.

Log nên tách:

- `db.transaction_attempt_id`
- `kafka.transaction_attempt_id`
- `kafka.transactional.id`
- `event.id`
- `db.outcome`
- `kafka.outcome`

Không dùng một field `transactionId` cho cả DB và Kafka vì có thể trùng hoặc không thể diễn giải.

Nếu ứng dụng dùng transactional outbox, log DB transaction ghi outbox row và publisher transaction gửi Kafka là hai giai đoạn khác nhau. Hãy dùng eventId để nối chúng.

## 35. Không dùng transaction ID làm metric label

Log và metric có mục tiêu khác nhau. Transactional IDs có thể tăng theo số instance, producer cache và vòng đời deployment; transaction attempt IDs thường là UUID mới cho mỗi lần xử lý.

Nếu gắn các giá trị này vào label Prometheus:

~~~text
kafka_transaction_duration_seconds{
  transactional_id="orders-pod-7-0",
  transaction_attempt_id="txa-..."
}
~~~

số time series có thể tăng rất nhanh, gây high cardinality và chi phí storage.

Nên dùng metric labels có cardinality thấp:

- application/service.
- consumer group.
- listener ID ổn định.
- topic (nếu số topic được kiểm soát).
- outcome: committed/aborted/unknown.
- exception category chuẩn hóa.

Để tìm một transaction cụ thể, dùng structured logs hoặc tracing. Không đưa attempt ID, event ID, offset hay span ID vào metric labels mặc định.

## 36. Sampling log và tránh log quá nhiều

Nếu mỗi record đều tạo một transaction và log 4–5 dòng cho begin/send/commit, volume có thể rất lớn.

Ví dụ:

    20.000 transactions/s
    4 log lines/transaction
    = 80.000 log events/s

Một số chiến lược:

- Log transaction start ở DEBUG.
- Log commit success ở DEBUG hoặc dùng counter/summary metrics.
- Log rollback/failure ở WARN/ERROR theo policy.
- Log full stack trace ở lần đầu/lần cuối hoặc theo sampling có kiểm soát.
- Luôn giữ eventId và coordinates trong những log quan trọng.
- Tạo log summary cho batch thay vì log payload từng record.
- Giữ structured logs cho các sự kiện lifecycle và lỗi cần điều tra.

Không sample mất toàn bộ lỗi nghiêm trọng hoặc log transaction outcome unknown. Với success volume cao, metrics thường phù hợp hơn việc tạo một dòng INFO cho mỗi transaction.

## 37. Tương quan với ConsumerStoppedEvent và fencing

Khi consumer container dừng vì transactional producer bị fencing, có thể xuất hiện ConsumerStoppedEvent với reason phù hợp theo Spring Kafka version.

Log nên ghép:

    ConsumerStoppedEvent
       |
       +-- reason=FENCED
       +-- listenerId=ordersListener
       +-- instance=orders-pod-7
       |
       +-- Kafka client logs
       |      transactional.id=orders-pod-7-0
       |      ProducerFencedException
       |
       +-- application transaction logs
              attemptId=txa-77
              eventId=evt-901
              outcome=UNKNOWN/ROLLED_BACK

Không phải mọi ProducerFencedException đều xuất hiện qua đúng một event hoặc đúng một thứ tự callback. Dùng log/event của phiên bản đang chạy và đối chiếu group/transaction state.

Nếu consumer đã mất ownership, đừng dùng transaction ID log như lý do để cố commit offset từ owner cũ. Fencing và group ownership là các lớp bảo vệ khác nhau; log giúp điều tra, không cấp quyền thao tác.

## 38. Kiểm thử log transaction ID

Một unit test có thể kiểm tra adapter/logging service nhận đúng metadata đã chuẩn hóa. Nhưng để chứng minh transactional producer identity và transaction completion, cần integration test với Kafka broker.

Các kịch bản:

### 38.1. Happy path

1. Cấu hình transactional.id prefix riêng cho test instance.
2. Gửi một event có eventId cố định.
3. Xác nhận log có transactionAttemptId.
4. Xác nhận transaction completion ghi outcome COMMITTED.
5. Xác nhận output xuất hiện với consumer read_committed.
6. Đối chiếu topic/partition/offset với log send acknowledgment.

### 38.2. Abort

1. Gửi output trong Kafka transaction.
2. Cố ý ném exception trước commit.
3. Xác nhận completion log ghi ROLLED_BACK hoặc status tương ứng.
4. Xác nhận downstream read_committed không nhận output bị abort.
5. Xác nhận attempt ID mới ở lần retry.
6. Xác nhận eventId giữ nguyên.

### 38.3. Producer fencing

1. Dùng transactional.id test được kiểm soát.
2. Tạo producer mới cùng identity để fencing producer cũ theo protocol.
3. Xác nhận client logs/exception thể hiện fencing.
4. Xác nhận application logs có producer identity và instance.
5. Không dùng ID này trong môi trường dùng chung hoặc production.
6. Sửa identity rồi kiểm tra phục hồi.

### 38.4. Timeout/outcome không chắc chắn

1. Mô phỏng lỗi network/response ở thời điểm commit.
2. Xác nhận log ghi timeout/unknown nếu outcome không thể xác định.
3. Kiểm tra downstream read_committed và trạng thái business theo eventId.
4. Retry theo idempotency policy, không tạo command nghiệp vụ mới ngoài ý muốn.

### 38.5. Retry và DLT

1. Tạo record lỗi để transaction rollback.
2. Quan sát transactionAttemptId mới cho mỗi attempt.
3. Khi hết retry, publish DLT theo cấu hình.
4. Log DLT destination và source coordinates.
5. Xác nhận offset recovered chỉ được ghi nhận theo cơ chế recovery thành công.
6. Re-drive với eventId gốc và attempt ID mới.

Không viết assertion cho một transactional.id suffix cố định nếu factory có cơ chế cấp suffix/cache thay đổi giữa các lần chạy. Test nên xác nhận ID có format/namespace hợp lệ theo contract của version hoặc dùng producer-factory callback được tài liệu hóa.

## 39. Dashboard và truy vấn log

Một số truy vấn hữu ích trong hệ thống log tập trung:

**Tìm tất cả lần thử của một event:**

~~~text
event.id = "evt-901"
~~~

**Tìm mọi transaction của một producer identity:**

~~~text
kafka.transactional_id = "orders-pod-7-0"
~~~

**Tìm transaction abort:**

~~~text
event = "kafka.transaction.rollback"
~~~

**Tìm outcome không chắc chắn:**

~~~text
transaction.outcome = "UNKNOWN"
~~~

**Tìm lỗi fencing:**

~~~text
error.type contains "ProducerFencedException"
~~~

**Tìm record consumer cụ thể:**

~~~text
kafka.topic = "orders.created"
AND kafka.partition = 2
AND kafka.offset = 901
~~~

Cú pháp truy vấn thực tế phụ thuộc Elasticsearch/OpenSearch, Loki, Splunk hoặc backend khác. Các ví dụ chỉ thể hiện field logic.

Dashboard có thể tổng hợp transaction duration, commit/abort rate và fencing count; log search dùng để drill down vào attempt/event cụ thể.

## 40. Runbook khi transaction ID có dấu hiệu xung đột

Khi thấy ProducerFencedException hoặc nhiều transaction abort liên quan cùng producer identity:

1. Xác định service, instance và transactional.id/factory identity.
2. Tìm tất cả pod/process đang log cùng identity.
3. Kiểm tra deployment rolling update, zombie process và shutdown.
4. Kiểm tra transaction-id-prefix có unique giữa các instance.
5. Xem producer factory suffix/cache và lifecycle.
6. Kiểm tra client/broker logs cho producer fencing/epoch changes.
7. Xác định transactionAttemptId và eventId bị ảnh hưởng.
8. Xác nhận output/offset transaction đã commit, abort hay outcome chưa rõ.
9. Kiểm tra consumer group, partition ownership và redelivery.
10. Xác nhận side effect ngoài Kafka có idempotent không.
11. Sửa cấu hình identity/lifecycle.
12. Restart có kiểm soát sau khi nguyên nhân được xử lý.
13. Theo dõi abort rate, stopped events, lag và duplicate detection.

Không xóa offset hoặc reset group để chữa producer fencing. Lỗi này thường liên quan producer identity/lifecycle; thay đổi consumer offset không sửa nguyên nhân.

## 41. Những lỗi logging thường gặp

| Sai sót | Hậu quả | Cách làm đúng |
|---|---|---|
| Coi transactional.id là ID riêng mỗi transaction | Không phân biệt được các lần attempt | Thêm transactionAttemptId |
| Dùng eventId làm transactional.id | Producer identity thay đổi theo business record, sai mục đích | Giữ transactional.id do factory quản lý |
| Tự ghép prefix + thread number | Log có thể không khớp ID runtime | Dùng API/factory identity được version hỗ trợ |
| Log commit ngay sau send() | Báo thành công giả khi transaction abort | Log outcome sau completion |
| Dùng Spring transaction name làm Kafka transactional.id | Nhầm hai lớp identity | Log field riêng |
| Ghi payload đầy đủ để tìm transaction | Rò rỉ dữ liệu, tăng log volume | Log event ID và coordinates |
| Không log topic/partition/offset | Khó tìm record nguồn | Ghi record coordinates |
| Dùng trace ID làm dedup key | Replay có thể tạo trace mới | Dùng eventId |
| Gắn transactionAttemptId vào metric label | High cardinality | Đưa ID vào logs/traces |
| Không khôi phục MDC | ID cũ rò sang record sau | Save/restore MDC |
| Giả định MDC qua async callback | Log mất hoặc sai trace context | Propagate context rõ ràng |
| Coi send future success là transaction commit | Output có thể bị abort | Log send và transaction outcome riêng |
| Retry mù sau timeout | Có thể tạo duplicate business output | Giữ eventId, reconcile outcome |
| Bật DEBUG/TRACE lâu dài trên toàn cluster | Log flood và chi phí cao | Bật chọn lọc, có thời hạn |
| Dùng reflection lấy producer epoch | Phụ thuộc nội bộ client, dễ vỡ | Dùng client/broker logs và API được hỗ trợ |

## 42. Checklist triển khai production

Trước khi dùng log transaction ID làm cơ sở vận hành:

- Đã xác định transactional.id là producer identity ổn định, không phải per-transaction attempt ID?
- Transactional ID prefix có unique giữa các instance đang hoạt động?
- Có transactionAttemptId riêng cho mỗi lần xử lý/giao dịch?
- Event ID có giữ ổn định qua retry/re-drive?
- Có log topic, partition, offset và consumer group khi xử lý input?
- Có phân biệt send requested, send acknowledged và transaction committed?
- Có log rollback/abort và unknown outcome?
- Có dùng transaction synchronization hoặc instrumentation đúng để ghi completion?
- ProducerFactory listener/API có được kiểm tra theo version?
- Có log instance/client ID để điều tra fencing?
- Có traceId/spanId và correlationId khi tracing được bật?
- MDC có save/restore đúng, nhất là trong thread pool?
- Không log secrets, PII hoặc toàn bộ payload?
- Không đưa transactional/attempt/event IDs vào metric labels?
- Có policy sampling/log level theo throughput?
- Có integration tests cho commit, abort, fencing, timeout và DLT?
- Có runbook xác minh transaction outcome trước khi retry?
- Có kiểm tra side effect database/API ngoài Kafka bằng idempotency?

## 43. Kết luận

**Log transaction id** trong Spring Kafka cần phân biệt rõ transactional.id của producer với transactionAttemptId của ứng dụng, producer ID/epoch của Kafka protocol và event ID của nghiệp vụ. Transactional ID giúp xác định producer identity và điều tra fencing; attempt ID giúp ghép các log của một lần xử lý; event ID giúp theo dõi cùng record qua retry và recovery.

Một log hữu ích ghi được các giai đoạn begin, send, commit/abort, kèm topic/partition/offset, group, instance, trace và error category. Đặc biệt, chỉ log COMMITTED sau khi transaction completion được xác nhận; send future thành công hoặc listener method trả về chưa đủ chứng minh transaction đã commit.

Khi có timeout hoặc fencing, log phải phản ánh đúng trạng thái đã biết và giữ riêng outcome unknown nếu chưa thể xác định. Kết hợp structured logs, Kafka client metrics, Spring transaction lifecycle, tracing và idempotency sẽ giúp đội vận hành tìm đúng producer/attempt/record mà không đánh đổi delivery guarantee hay làm lộ dữ liệu nghiệp vụ.
