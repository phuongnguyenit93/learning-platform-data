# Log message consumer trong Java: ghi nhận chính xác quá trình xử lý message

## 1. Message consumer là gì và cần log điều gì?

Trong một ứng dụng **message-driven**, *producer* tạo message và gửi tới broker/queue/topic; *consumer* nhận message rồi thực hiện logic nghiệp vụ. Consumer có thể chạy trong ứng dụng Java dùng Kafka, RabbitMQ, JMS, hoặc một hệ thống hàng đợi khác.

```text
Producer --> Broker/topic/queue --> Consumer poll/delivery
                                      |
                                      v
                            Deserialize / validate
                                      |
                                      v
                            Execute business logic
                                      |
                             +--------+--------+
                             |                 |
                           success           failure
                             |                 |
                      ACK / commit       retry / reject / DLQ
                             |
                     downstream effects
```

**Log message consumer** là việc ghi sự kiện có cấu trúc ở những thời điểm có ý nghĩa: message được nhận, bắt đầu xử lý, xử lý thành công, lỗi tạm thời, retry, bị chuyển dead-letter, bị nhận diện là trùng, hoặc consumer yêu cầu xác nhận đã xử lý.

Mục tiêu không phải in toàn bộ payload, mà là trả lời được:

- Message nào được consumer nào nhận?
- Đây là lần giao thứ mấy; có từng xử lý thành công chưa?
- Consumer đã làm gì với message: xử lý, retry, bỏ qua, hoặc gửi vào dead-letter queue?
- Lỗi xảy ra ở bước nào, có thể retry hay không?
- Trạng thái nghiệp vụ đã commit hay mới đang xử lý?
- ACK/offset commit đã **được yêu cầu**, hay đã được broker xác nhận theo API?
- Message mất, đến trễ hay xuất hiện nhiều lần là do đâu?

Một message có thể được giao nhiều lần, và một lần xử lý có thể phát ra nhiều log event. Do đó **không suy từ số dòng log “received” thành số nghiệp vụ thành công**.

## 2. Phân biệt các mốc của consumer

Một thiết kế log tốt dùng **tên event và outcome rõ ràng**:

| Event gợi ý | Ý nghĩa có thể khẳng định | Không tự khẳng định |
| --- | --- | --- |
| `consumer.received` | Ứng dụng nhìn thấy một lần giao message | Nghiệp vụ đã hoàn tất |
| `consumer.processing_started` | Handler bắt đầu xử lý lần giao | Transaction đã commit |
| `consumer.processing_succeeded` | Handler đạt điều kiện thành công đã định nghĩa | Broker đã nhận ACK |
| `consumer.ack_requested` | Ứng dụng gọi API xác nhận/commit | Broker đã lưu offset hoặc ACK bền vững |
| `consumer.offset_commit_succeeded` | Client nhận kết quả commit theo API | Mọi side effect downstream đều hoàn tất |
| `consumer.retry_scheduled` | Có kế hoạch/lệnh đưa message vào lần xử lý lại | Broker chắc chắn sẽ giao lại |
| `consumer.requeued` | Đã yêu cầu hoặc xác nhận requeue theo ngữ nghĩa cụ thể | Chắc chắn không trùng |
| `consumer.dead_lettered` | Đã chuyển vào dead-letter theo mức xác nhận được định nghĩa | DLQ tồn tại vĩnh viễn hoặc message sẽ được xử lý |
| `consumer.duplicate_detected` | Hệ thống xác định đã thấy event/idempotency key | Có thể bỏ qua an toàn trong mọi ngữ cảnh |
| `consumer.validation_failed` | Nội dung không đạt quy tắc hợp lệ | Có thể retry và sẽ thành công |

**Chú ý ngữ nghĩa:** một phương thức `acknowledge()` có thể chỉ đánh dấu một offset để container commit sau, hoặc yêu cầu broker xác nhận delivery theo giao thức. Đặt tên event phản ánh đúng mức xác nhận thực tế; không ghi `ACK_CONFIRMED` khi chỉ gọi hàm mà chưa có bằng chứng.

### 2.1. Không ghi “processed” ngay khi nhận

Sai:

```java
// Mã minh họa không độc lập: chỉ mới nhận, chưa xử lý.
log.info("Message processed, id={}", messageId);
businessHandler.process(message);
```

Nếu `process` lỗi, log đã khẳng định quá mức. Trình tự hợp lý hơn:

```java
// Mã tích hợp, cần handler/logger/biến do ứng dụng cung cấp.
log.debug("event=consumer.received id={}", messageId);
businessHandler.process(message); // Chưa chắc commit nếu transaction chưa kết thúc.
log.info("event=consumer.processing_succeeded id={}", messageId);
```

Với handler có transaction, phải xác định thời điểm **thành công sau commit**; một dòng log trước commit có thể sai khi transaction rollback. Nếu dùng outbox/transactional event, đồng bộ trạng thái nghiệp vụ và audit event theo thiết kế riêng.

## 3. Ba định danh thường bị nhầm lẫn

| Định danh | Thuộc về | Phục vụ |
| --- | --- | --- |
| **Message ID / event ID** | Message logic do producer hoặc broker cấp | Nhận diện nội dung/event có thể được giao lại |
| **Delivery/attempt ID** | Một lần giao hoặc một lần thực thi cụ thể | Phân biệt những lần xử lý trùng/retry |
| **Correlation/trace ID** | Chuỗi nghiệp vụ hoặc lời gọi phân tán | Liên kết producer, broker, consumer và service khác |

Một schema minh họa:

```json
{
  "event": "consumer.processing_succeeded",
  "timestamp": "2026-11-10T02:00:00Z",
  "service": "billing-service",
  "consumerGroup": "billing-workers",
  "messageId": "evt-2041",
  "messageType": "OrderCreated",
  "correlationId": "corr-719",
  "attempt": 2,
  "source": "orders",
  "partition": 3,
  "offset": 9012,
  "durationMs": 18,
  "outcome": "SUCCEEDED"
}
```

Đây là **dữ liệu ví dụ**, không phải output mặc định của Kafka hoặc Logback. Kafka có topic/partition/offset; RabbitMQ có exchange/routing key/queue và delivery tag; JMS có `JMSMessageID`, `JMSCorrelationID`. Không áp các trường Kafka một cách máy móc cho mọi broker.

Các nguyên tắc:

1. **Không coi message ID và delivery tag là giống nhau.** Trong RabbitMQ, delivery tag gắn với **channel** và lần giao, không phải định danh nghiệp vụ toàn cục.
2. Với Kafka, cặp **topic + partition + offset** định danh vị trí record trong log của topic ở phạm vi cụ thể; key/value và business event ID là vấn đề khác.
3. `correlationId` và `traceparent` có thể do producer/client khai báo; **validate, giới hạn độ dài và áp chính sách trust** trước khi dùng trong log.
4. Attempt count do framework/broker cung cấp có ngữ nghĩa riêng; số lần giao, số lần retry và số lần xử lý của ứng dụng không luôn bằng nhau.
5. Nếu producer chưa có business event ID ổn định, offset hoặc JMS message ID có thể hỗ trợ điều tra, nhưng **idempotency key cần bám vào nghiệp vụ** khi yêu cầu xử lý trùng qua các bản sao/re-publish.

## 4. Ghi log ở những điểm nào?

Không nên có một dòng INFO cho mọi phép gán biến trong consumer. Chọn các điểm cần điều tra:

```text
receive delivery
  -> consumer.received                   (thường DEBUG / sampled INFO)
  -> deserialize/validate
      -> consumer.invalid_message        (WARN, không dump raw payload)
  -> duplicate/idempotency check
      -> consumer.duplicate_detected     (INFO/DEBUG tùy yêu cầu)
  -> business transaction
      -> consumer.processing_succeeded   (INFO hoặc metric theo chính sách)
      -> consumer.processing_failed      (WARN/ERROR theo tác động)
  -> retry policy
      -> consumer.retry_scheduled        (WARN/INFO, attempt, delay, reason)
      -> consumer.dead_lettered          (WARN/ERROR, nguyên nhân và đích)
  -> acknowledgment / offset commit
      -> consumer.ack_requested          (DEBUG/INFO tùy yêu cầu)
      -> consumer.commit_failed          (ERROR/WARN khi đã biết kết quả)
```

**Không phải mọi mốc đều cần log ở INFO.** Ở hệ thống hàng chục nghìn message/giây, việc log mỗi lần nhận và hoàn tất có thể tạo chi phí đáng kể. Nếu các sự kiện mang tính audit bắt buộc lưu, chọn một kênh audit riêng với guarantee rõ ràng; không tùy tiện sampling chúng như log chẩn đoán.

Một log event tối thiểu nên có: `event`, `messageType`, `messageId` đã kiểm duyệt, `consumer`/`group`, nguồn topic/queue, một định danh lần giao, `outcome`, thời gian và loại lỗi được chuẩn hóa nếu lỗi. Chọn thêm `correlationId` khi có giá trị.

## 5. Java 17: ví dụ consumer, retry, duplicate và DLQ chạy độc lập

Ví dụ sau dùng `java.util.logging` (JUL) sẵn trong JDK và một hàng đợi **giả lập trong bộ nhớ**. Nó minh họa:

- Message `m-1` được xử lý thành công.
- Message `m-2` gặp lỗi tạm thời ở lần đầu; được xếp lại và thành công ở lần thứ hai.
- Message `m-3` gặp lỗi không thể khôi phục, chuyển sang danh sách dead-letter mô phỏng.
- Bản giao lặp của `m-1` được nhận diện là duplicate.
- Event `ACK_REQUESTED` được ghi **sau khi xử lý/đánh dấu bỏ qua hợp lệ** theo luật demo, không phải trước.
- Cuối cùng in các số liệu để có thể kiểm tra chính xác.

**Quan trọng:** đây là mô phỏng để học về event log, **không phải broker**, không có ACK thật, durable DLQ, transaction, xác thực hoặc bảo đảm exactly-once. Tập `processed` chỉ tồn tại trong RAM, không an toàn để dùng như một hệ thống idempotency production.

Lưu file **`MessageConsumerLoggingDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class MessageConsumerLoggingDemo {
    record Message(String id, String type, String correlationId) {}
    record Delivery(Message message, int attempt) {}

    static final class RetryableFailure extends RuntimeException {}
    static final class PermanentFailure extends RuntimeException {}

    private static void process(Delivery delivery) {
        String type = delivery.message().type();
        if ("RETRY_ONCE".equals(type) && delivery.attempt() == 1) {
            throw new RetryableFailure();
        }
        if ("INVALID".equals(type)) {
            throw new PermanentFailure();
        }
        // Nghiệp vụ thành công được mô phỏng, chưa có database.
    }

    private static void emit(
            Logger logger, Level level, String event, Delivery delivery) {
        Message message = delivery.message();
        logger.log(level, "event=" + event
                + " messageId=" + message.id()
                + " type=" + message.type()
                + " attempt=" + delivery.attempt()
                + " correlationId=" + message.correlationId());
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.consumer");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler stdout = new Handler() {
            {
                setLevel(Level.ALL);
            }

            @Override
            public void publish(LogRecord record) {
                if (record != null && isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " " + record.getMessage());
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        logger.addHandler(stdout);

        try {
            Message first = new Message("m-1", "ORDER_CREATED", "c-1");
            Message transientMessage =
                    new Message("m-2", "RETRY_ONCE", "c-2");
            Message invalid = new Message("m-3", "INVALID", "c-3");

            ArrayDeque<Delivery> queue = new ArrayDeque<>();
            queue.add(new Delivery(first, 1));
            queue.add(new Delivery(transientMessage, 1));
            queue.add(new Delivery(invalid, 1));
            queue.add(new Delivery(first, 1)); // Giao lại cùng event logic.

            Set<String> processed = new HashSet<>();
            List<Message> deadLetters = new ArrayList<>();
            int retries = 0;
            int duplicates = 0;

            while (!queue.isEmpty()) {
                Delivery delivery = queue.removeFirst();
                Message message = delivery.message();

                emit(logger, Level.INFO, "RECEIVED", delivery);

                if (processed.contains(message.id())) {
                    duplicates++;
                    emit(logger, Level.INFO, "DUPLICATE_SKIPPED", delivery);
                    emit(logger, Level.INFO, "ACK_REQUESTED", delivery);
                    continue;
                }

                try {
                    process(delivery);
                    processed.add(message.id());
                    emit(logger, Level.INFO, "SUCCEEDED", delivery);
                    emit(logger, Level.INFO, "ACK_REQUESTED", delivery);
                } catch (RetryableFailure failure) {
                    retries++;
                    queue.addLast(new Delivery(
                            message, delivery.attempt() + 1));
                    emit(logger, Level.WARNING,
                            "RETRY_SCHEDULED", delivery);
                } catch (PermanentFailure failure) {
                    deadLetters.add(message);
                    emit(logger, Level.WARNING, "DLQ_STORED", delivery);
                    emit(logger, Level.INFO, "ACK_REQUESTED", delivery);
                }
            }

            logger.info("event=SUMMARY processed=" + processed.size()
                    + " retries=" + retries
                    + " dlq=" + deadLetters.size()
                    + " duplicates=" + duplicates);
        } finally {
            logger.removeHandler(stdout);
            stdout.close();
        }
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac MessageConsumerLoggingDemo.java
java MessageConsumerLoggingDemo
```

Kết quả **`stdout` chính xác**:

```text
INFO event=RECEIVED messageId=m-1 type=ORDER_CREATED attempt=1 correlationId=c-1
INFO event=SUCCEEDED messageId=m-1 type=ORDER_CREATED attempt=1 correlationId=c-1
INFO event=ACK_REQUESTED messageId=m-1 type=ORDER_CREATED attempt=1 correlationId=c-1
INFO event=RECEIVED messageId=m-2 type=RETRY_ONCE attempt=1 correlationId=c-2
WARNING event=RETRY_SCHEDULED messageId=m-2 type=RETRY_ONCE attempt=1 correlationId=c-2
INFO event=RECEIVED messageId=m-3 type=INVALID attempt=1 correlationId=c-3
WARNING event=DLQ_STORED messageId=m-3 type=INVALID attempt=1 correlationId=c-3
INFO event=ACK_REQUESTED messageId=m-3 type=INVALID attempt=1 correlationId=c-3
INFO event=RECEIVED messageId=m-1 type=ORDER_CREATED attempt=1 correlationId=c-1
INFO event=DUPLICATE_SKIPPED messageId=m-1 type=ORDER_CREATED attempt=1 correlationId=c-1
INFO event=ACK_REQUESTED messageId=m-1 type=ORDER_CREATED attempt=1 correlationId=c-1
INFO event=RECEIVED messageId=m-2 type=RETRY_ONCE attempt=2 correlationId=c-2
INFO event=SUCCEEDED messageId=m-2 type=RETRY_ONCE attempt=2 correlationId=c-2
INFO event=ACK_REQUESTED messageId=m-2 type=RETRY_ONCE attempt=2 correlationId=c-2
INFO event=SUMMARY processed=2 retries=1 dlq=1 duplicates=1
```

### 5.1. Giải thích trình tự

- Queue ban đầu có bốn lần giao: m-1, m-2, m-3, rồi m-1 lặp.
- m-1 thành công, ID được đưa vào `processed` rồi có log `ACK_REQUESTED`.
- m-2 lần đầu ném `RetryableFailure`; consumer đưa một lần giao mới `attempt=2` vào **cuối queue**. Lần retry vì vậy diễn ra **sau** các phần tử đang chờ.
- m-3 ném `PermanentFailure` và được thêm vào `deadLetters` trong RAM. Đặt tên `DLQ_STORED` ở demo nghĩa là **đã lưu vào list cục bộ**, không phải broker có DLQ bền vững.
- Khi bản giao lặp của m-1 xuất hiện, `processed` đã chứa ID đó; handler bỏ qua xử lý nghiệp vụ mô phỏng và ghi `DUPLICATE_SKIPPED`.
- m-2 lần thứ hai chạy `process` không lỗi, nên hoàn tất.
- Kết quả cuối gồm hai message logic thành công, một lần retry, một message đi vào dead-letter giả lập, một lần phát hiện duplicate.

**Điểm cần nhớ:** `processed` là một `HashSet` trong process, **không** tự bền vững và **không** kiểm soát concurrency. Trong ứng dụng thật, hai consumer cùng xử lý một business event có thể cùng đọc “chưa xử lý”; idempotency cần uniqueness/transaction/lock phù hợp. Các dòng `ACK_REQUESTED` trong ví dụ **không gọi broker**. Không được dùng chúng làm bằng chứng broker đã commit offset hay xác nhận delivery.

### 5.2. Vì sao không in toàn bộ payload?

Ví dụ chỉ giữ ID và type có giá trị cố định. Trong hệ thống thật, message payload có thể chứa thông tin cá nhân, token, payment data, hoặc hàng megabyte JSON. Ghi raw payload ở `INFO` gây rò dữ liệu và bão log. Khi lỗi deserialize, có thể **không thể đọc được messageId từ body**; hãy ưu tiên broker metadata + một mã lỗi an toàn thay vì cố in body thô.

## 6. Thiết kế schema log có cấu trúc

Gợi ý trường cho một event:

| Trường | Mục đích |
| --- | --- |
| `event` | Mốc vòng đời: received, succeeded, retry, ack_requested, dead_lettered |
| `timestamp`, `level` | Thời điểm ghi và mức độ quan trọng |
| `service`, `instanceId` | Consumer đang chạy ở đâu |
| `consumerGroup` / `subscription` | Nhóm nhận message |
| `sourceTopic` / `sourceQueue` | Nguồn message |
| `partition`, `offset` | Vị trí record khi dùng Kafka |
| `deliveryTag`, `redelivered` | Metadata phù hợp RabbitMQ |
| `messageId`, `messageType` | Event logic và schema/type |
| `correlationId`, `traceId` | Liên kết request/chuỗi xử lý |
| `attempt` | Lần thử theo bộ đếm được định nghĩa |
| `outcome`, `errorCode` | Thành công, thất bại hoặc bị từ chối |
| `durationMs` | Thời gian xử lý đo được |
| `retryDelayMs`, `retryReason` | Chính sách xử lý lại |
| `deadLetterDestination` | Đích xử lý lỗi nếu đã xác nhận |
| `schemaVersion` | Để đọc lại dữ liệu lịch sử đúng nghĩa |

Không phải mọi broker đều có từng trường này. Schema nên ổn định, có version và **chỉ bổ sung metadata sẵn có, có ý nghĩa**; dùng `null`/bỏ field khi không áp dụng thay vì bịa offset/delivery tag.

Dùng các giá trị event code ổn định thay vì chỉ ghi `"Exception while processing"`. Ví dụ khi tìm các message bị retry:

```text
event = consumer.retry_scheduled
AND consumerGroup = billing-workers
AND errorCode = TEMPORARY_DEPENDENCY_UNAVAILABLE
```

Đây là **bộ lọc khái niệm**, không phải query syntax của một hệ lưu trữ cụ thể.

## 7. Log level cho consumer: INFO, DEBUG, WARN, ERROR

Một phương án thực hành:

| Tình huống | Mức thường cân nhắc | Vì sao |
| --- | --- | --- |
| Mỗi delivery thông thường được nhận | DEBUG hoặc sampled INFO | Lưu lượng lớn, dễ bão log |
| Processing thành công | INFO nếu cần theo dõi từng message; metric nếu không | Cân bằng truy vết và chi phí |
| Duplicate đã được xử lý an toàn | DEBUG/INFO | Giải thích message được giao lại |
| Retryable failure còn trong ngân sách retry | WARN hoặc INFO | Có lỗi nhưng hệ thống tự xử lý |
| Permanent failure / DLQ | WARN/ERROR | Cần quan sát và xử lý |
| Broker/consumer loop ngừng hoạt động | ERROR | Sự cố hạ tầng ảnh hưởng tiến độ xử lý |
| Lỗi deserialize của một message độc hại | WARN hoặc ERROR theo chính sách | Không được để một message gây log storm không kiểm soát |
| Lỗi commit/ack bất thường | WARN/ERROR | Khả năng redelivery và side-effect trùng |

**Không biến level thành outcome.** Một event `consumer.retry_scheduled` có thể được log WARN, nhưng chính trường `event`/`outcome` mới biểu diễn trạng thái. Đừng ghi ERROR cho hàng triệu retry bình thường nếu chỉ tạo thêm cảnh báo nhiễu; cũng đừng im lặng bỏ một DLQ event quan trọng.

Log của ứng dụng và metrics bổ trợ nhau. Metric counter có thể đếm throughput/attempt/failures, còn event log phục vụ truy vấn từng trường hợp. Với các nghiệp vụ bắt buộc audit, log chi tiết phải đi qua pipeline có yêu cầu retention/durability riêng; không dùng sampling làm mất chứng cứ bắt buộc.

## 8. Retry, backoff và dead-letter logging

### 8.1. Phân loại retryable và permanent

Ví dụ phân loại:

- **Retryable:** kết nối tới downstream tạm mất, HTTP 503, deadlock có thể thử lại, broker tạm từ chối.
- **Permanent/không phù hợp retry nguyên trạng:** payload sai schema không thể đọc, thiếu trường bắt buộc, business rule không thỏa trong trạng thái hiện tại, chữ ký sự kiện không hợp lệ.
- **Không rõ:** cần policy/quarantine, không mặc định retry vô hạn.

Phân loại phải dựa trên logic nghiệp vụ cụ thể. Một HTTP 400 có thể là permanent trong API này nhưng trong API khác có thể liên quan cấu hình chưa cập nhật; không áp dụng bảng “mọi exception loại X đều retry được” mà không đánh giá nguyên nhân.

Một `retry_scheduled` event nên có:

```json
{
  "event": "consumer.retry_scheduled",
  "messageId": "evt-2041",
  "attempt": 3,
  "nextAttempt": 4,
  "retryDelayMs": 4000,
  "errorCode": "DEPENDENCY_UNAVAILABLE",
  "maxAttempts": 5
}
```

Đây là cấu trúc minh họa. Nếu broker/container quyết định retry, hãy đặt tên trạng thái theo mức đã xác nhận: `retry_requested` khác với `retry_enqueued` hoặc `redelivered`.

### 8.2. Tại sao không retry vô hạn và log stack trace ở mọi lần?

Nếu một message poison liên tục được giao:

1. Handler thất bại.
2. Container retry ngay.
3. Mỗi retry ghi một stack trace lớn.
4. Log queue hoặc disk quá tải.
5. Việc xử lý message khác bị ảnh hưởng.

Nên có **retry budget, backoff, jitter** khi phù hợp, định nghĩa số lần thử tối đa và một đường cách ly/dead-letter. Ghi attempt count, error category và một correlation ID; stack trace chi tiết có thể ghi theo sampling/chính sách, nhưng không xóa những thông tin điều tra bắt buộc.

Với message lỗi cố định, dùng **rate limiting** cho cảnh báo lặp và metric đếm số lần thay vì in trùng toàn bộ payload.

### 8.3. Dead-letter phải có bằng chứng thực tế

Các trạng thái nên tách:

- `dead_letter_requested`: ứng dụng định chuyển message.
- `dead_letter_publish_succeeded`: có bằng chứng publisher/broker nhận theo hợp đồng.
- `dead_lettered`: message đã tới nơi cách ly theo tiêu chí hệ thống định nghĩa.
- `original_ack_requested`: đã yêu cầu xác nhận message gốc sau khi đảm bảo xử lý kết thúc phù hợp.

Nếu consumer **ACK message gốc trước khi publish DLQ thành công**, có thể mất message khi publish thất bại. Nếu publish DLQ thành công nhưng ACK gốc thất bại, có thể bị giao lại và đưa DLQ lần nữa. Tùy broker, cơ chế dead-letter có thể do broker xử lý sau reject/nack, không phải consumer tự publish. Cần kiểm chứng loại guarantee thật sự được cung cấp và thiết kế idempotency/đối soát.

Không ghi `DLQ_SUCCEEDED` khi chỉ gọi API bắt đầu publish nhưng chưa có kết quả xác nhận tương ứng.

## 9. ACK, offset commit và những khác biệt theo broker

### 9.1. Kafka

Kafka consumer đọc **records** trong các partition, ghi nhận vị trí bằng offset. Cần phân biệt:

- **Poll/receive:** record đã được client đọc.
- **Business processing:** logic nghiệp vụ đã chạy/transaction đã commit hay chưa.
- **Offset commit:** vị trí tiêu thụ được commit cho consumer group theo API.

Nếu business effect đã commit nhưng offset chưa được commit, record có thể được giao/xử lý lại. Nếu commit offset trước khi business effect chắc chắn thành công, record có nguy cơ bị bỏ qua sau sự cố. Chính vì thế **idempotency** thường rất quan trọng.

Ở Spring Kafka, `Acknowledgment.acknowledge()` khi chạy với kiểu manual acknowledgment yêu cầu container xử lý ACK/commit theo cấu hình. Nó không luôn chứng minh một **synchronous broker commit đã hoàn tất ngay tại dòng gọi**; phụ thuộc ack mode, error handler, thời điểm container commit và các tùy chọn liên quan.

Kafka có các cơ chế giao dịch và exactly-once semantics trong những luồng Kafka-to-Kafka phù hợp, nhưng **không được tự kết luận side effect ở external database/HTTP API được exactly-once** chỉ vì Kafka transaction tồn tại. Cần thiết kế ranh giới giao dịch cụ thể.

### 9.2. RabbitMQ (AMQP)

Với RabbitMQ manual acknowledgments:

- `basicAck(deliveryTag, false)`: producer/consumer-side client gửi yêu cầu ACK cho một delivery tag trên channel đó.
- `basicNack(deliveryTag, false, true)`: gửi NACK kèm yêu cầu **requeue**, có thể giao lại ngay và tạo vòng lặp.
- `basicNack(deliveryTag, false, false)` hoặc `basicReject(..., false)`: từ chối không requeue; message có thể được dead-letter **nếu queue/broker được cấu hình DLX/DLQ phù hợp**, còn không có thể bị bỏ.
- `deliveryTag` **chỉ có nghĩa trong phạm vi channel**, không phải một message ID logic dùng toàn hệ thống.

Không mô tả việc gọi `basicAck` trả về bình thường như một **publisher confirm** hay một xác nhận bền vững từng event từ broker. Phải hiểu channel, prefetch, acknowledgment mode và cơ chế xử lý connection failure.

Với xử lý async, cần cẩn thận về thread/channel ownership, thứ tự ACK, và đặc biệt `multiple=true` có thể ảnh hưởng nhiều delivery tag, không chỉ message đang quan sát.

### 9.3. JMS

JMS có session/acknowledgment và giao dịch riêng. Chẳng hạn, `CLIENT_ACKNOWLEDGE` ở nhiều tình huống xác nhận **các message đã tiêu thụ trên session** khi gọi acknowledge, không nhất thiết chỉ một message hiện tại. Session transacted có semantics commit/rollback riêng; provider có thể gắn `JMSRedelivered` hoặc `JMSXDeliveryCount` nếu hỗ trợ.

Vì vậy trường `acknowledged=true` hoặc `attempt` cần bám vào **provider, API và session mode** thực tế. Không dùng một mẫu audit từ Kafka cho JMS mà bỏ qua khác biệt.

## 10. Ví dụ tích hợp Spring Kafka: log kết quả rồi ACK

Ví dụ này dành cho một dự án **Spring Boot / Spring Kafka đã có cấu hình**. Không phải chương trình độc lập để chạy bằng `javac`: cần dependencies, broker, listener container, serializer/deserializer và một service xử lý nghiệp vụ.

```java
package com.example.messaging;

import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class OrderMessageConsumer {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderMessageConsumer.class);

    private final OrderHandler handler;

    public OrderMessageConsumer(OrderHandler handler) {
        this.handler = handler;
    }

    @KafkaListener(topics = "orders", groupId = "billing-workers")
    public void consume(ConsumerRecord<String, String> record,
                        Acknowledgment ack) {
        long startedAt = System.nanoTime();

        try {
            // Handler phải tự bảo đảm idempotency và commit theo contract.
            handler.processIdempotently(record.key(), record.value());
        } catch (RuntimeException failure) {
            LOG.warn(
                "event=consumer.processing_failed topic={} partition={} "
              + "offset={} errorType={}",
                record.topic(), record.partition(), record.offset(),
                failure.getClass().getSimpleName());
            throw failure; // Để error handler/retry policy xử lý.
        }

        long durationMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startedAt);

        LOG.info("event=consumer.processing_succeeded topic={} "
                + "partition={} offset={} durationMs={}",
                record.topic(), record.partition(), record.offset(),
                durationMs);

        ack.acknowledge(); // Yêu cầu ACK theo cấu hình container.
        LOG.debug("event=consumer.ack_requested topic={} partition={} "
                + "offset={}",
                record.topic(), record.partition(), record.offset());
    }

    public interface OrderHandler {
        void processIdempotently(String key, String value);
    }
}
```

Giải thích thiết kế:

1. `record.topic()`, `partition()`, `offset()` xác định vị trí Kafka record; không ghi nguyên payload hoặc raw key nếu có PII.
2. `handler.processIdempotently(...)` là **contract giao cho nghiệp vụ**; interface không tự thực hiện idempotency. Cần implementation có unique key, transaction hoặc cơ chế tương ứng.
3. Chỉ sau khi handler trả về thành công, consumer phát log xử lý thành công và gọi `ack.acknowledge()`. Nếu handler ném `RuntimeException`, mã log failure rồi **ném lại**, để Spring Kafka error handler theo cấu hình xử lý.
4. Cần cấu hình **manual acknowledgment mode** (ví dụ `MANUAL` hoặc `MANUAL_IMMEDIATE` tùy phiên bản và yêu cầu) và đối chiếu với retry/error handler. Nếu container dùng auto ACK, contract mã này không đúng.
5. Log `ack_requested` không tuyên bố offset đã commit thành công. Để có `commit_succeeded`, cần lấy kết quả commit/callback từ đúng API/cấu hình.
6. `LOG.warn` không cố in toàn bộ `record.value()`, exception message hoặc headers, vì chúng có thể chứa dữ liệu nhạy cảm.
7. Khi listener xử lý batch hoặc có concurrency/rebalance, thứ tự offset commit phức tạp hơn một phép ACK của một record; cần kiểm thử hành vi thực tế.

**Đây là mẫu tích hợp**, không có output cố định và không tự triển khai broker hay error handler. Nếu processing tham gia transaction trong đó commit xảy ra sau khi phương thức trả về, dòng `processing_succeeded` chỉ đúng khi handler contract chứng minh transaction đã commit tại thời điểm trả về. Cần điều chỉnh vị trí event theo transaction lifecycle thực tế.

### 10.1. Phát một event có correlation ID

Nếu message có business `eventId` và `correlationId` trong headers đã được validate, có thể ghi các trường đó bên cạnh Kafka coordinates. Tuy nhiên:

- Không tin tưởng một ID header bất kỳ là danh tính đã xác thực.
- Header có thể thiếu, trùng tên hoặc có bytes không giải mã được; đặt fallback rõ ràng.
- Không log raw `traceparent`/baggage không giới hạn; kiểm tra định dạng và kích thước.
- Với batch consumer, mỗi record cần message ID riêng; một batch ID chỉ định danh đợt poll, không thay thế event ID.

## 11. MDC và trace context trong consumer

Logging trong web app thường có request ID do HTTP middleware gán. **Message consumer không mặc nhiên có HTTP request context**. Khi xử lý message, có thể khôi phục correlation/trace context từ headers theo policy, rồi gắn vào MDC cho các log cùng luồng.

Đoạn tích hợp với SLF4J:

```java
import org.slf4j.MDC;

// Trong phương thức xử lý một message:
// validatedCorrelationId đã được kiểm tra độ dài và ký tự.
String previous = MDC.get("correlationId");
try {
    if (validatedCorrelationId == null) {
        MDC.remove("correlationId");
    } else {
        MDC.put("correlationId", validatedCorrelationId);
    }

    processMessage();
} finally {
    if (previous == null) {
        MDC.remove("correlationId");
    } else {
        MDC.put("correlationId", previous);
    }
}
```

Đây **không phải class chạy độc lập**; giả định `processMessage()` và biến tương ứng đã tồn tại. Giữ lại giá trị trước tránh làm hỏng MDC của một scope lồng nhau.

Điểm cần nhớ:

- `MDC` thường gắn với thread; thread pool **tái sử dụng thread** nên phải khôi phục/dọn context trong `finally`.
- Khi chạy `CompletableFuture`, Reactor/WebFlux hoặc executor khác, context không tự lan qua mọi thread; dùng cơ chế context propagation đúng framework.
- Nếu message xử lý song song, không dùng một static mutable `correlationId` chung cho tất cả listener.
- Không để header chưa validate quyết định routing file/topic hoặc trở thành metric label có cardinality cao.
- Trace context như W3C `traceparent` giúp nối span giữa producer và consumer khi được propagate đúng; **trace ID không thay thế message ID** và không chứng minh nghiệp vụ thành công.

## 12. Idempotency: vì sao log “duplicate” chưa đủ?

Nhiều hệ thống message có thể có **at-least-once delivery**: broker có thể giao cùng một message lần nữa nếu consumer crash hoặc ACK/commit chưa thành công. Khi đó:

```text
receive m-1
 -> update database succeeds
 -> JVM crashes before ACK
 -> broker redelivers m-1
 -> update database may be repeated
```

Nếu consumer chỉ ghi `Duplicate skipped` dựa vào một `HashSet` trong RAM, sau restart tập đó rỗng và message sẽ chạy lại. Trong production có thể dùng:

- **Unique constraint** trên `eventId`/idempotency key trong database.
- **Processed-message table** được cập nhật trong cùng transaction với business state.
- **Upsert/idempotent operation** khi nghiệp vụ cho phép.
- **Inbox/outbox** có cơ chế lưu bền vững, retry và đối soát.
- **Optimistic concurrency/version check** khi cùng một target có nhiều event.

Ví dụ mô hình (pseudo-SQL, không phụ thuộc một dialect cụ thể):

```sql
BEGIN TRANSACTION;
-- Insert một idempotency key với unique constraint.
-- Nếu key đã tồn tại: kiểm tra trạng thái và bỏ qua theo policy.
INSERT INTO processed_message(message_id) VALUES ('evt-2041');
-- Thực hiện thay đổi nghiệp vụ trong cùng transaction.
UPDATE account_balance SET ... WHERE ...;
COMMIT;
```

Đây là **phác họa**, không phải câu SQL hoàn chỉnh có thể chạy ngay: `UPDATE ...` cố ý chỉ biểu diễn bước nghiệp vụ, nên không dùng snippet này như script thực thi. Điểm cốt lõi là **đánh dấu đã xử lý và side effect cần nhất quán**, không chỉ thêm một record `processed` ngoài transaction.

Khi thấy `consumer.duplicate_detected`, log cần cho biết quyết định:

- Bản ghi duplicate đã được xác minh là **cùng event đã xử lý thành công**?
- Hay đó là một attempt trước còn `PROCESSING` và cần retry?
- Có xung đột cùng ID nhưng payload/version khác không?
- Consumer đã **ACK yêu cầu bỏ qua** hay cần tiếp tục xử lý?

**Không mặc định mọi lần trùng ID đều bỏ qua an toàn**, nhất là nếu lần đầu chưa commit nghiệp vụ hoặc trạng thái trung gian chưa được xử lý đúng.

## 13. Logger, filter và sink cũng có thể làm mất log consumer

Gọi `logger.info(...)` không bảo đảm event đã tới nơi lưu. Một pipeline logging có thể đi qua:

```text
Consumer code
   -> logger level/filter
   -> encoder/formatter
   -> AsyncAppender / queue (optional)
   -> console/file/network
   -> collector
   -> storage / retention
```

Các trường hợp cần phân biệt:

- DEBUG bị tắt: một `received` event không được tạo/ghi theo policy.
- Handler/appender filter loại một event dù logger cho phép.
- Queue logging đầy: framework có thể block hoặc drop theo cấu hình.
- File/collector lỗi: bản ghi chưa đến đích.
- JVM crash: các event chỉ nằm trong RAM queue có thể mất.
- Retry gửi log: có thể có bản ghi trùng ở collector.
- Logger bị đổi cấu hình runtime: số lượng và loại log biến động.

Nếu một message là giao dịch bắt buộc kiểm toán, **không thay thế audit trail bền vững bằng log chẩn đoán bất đồng bộ**. Có thể cần bản ghi trong database/outbox và đường lưu độc lập theo ràng buộc nghiệp vụ.

## 14. Bảo mật và quyền riêng tư trong log consumer

Message payload có thể chứa dữ liệu nhạy cảm hơn HTTP request headers: đơn hàng, dữ liệu thanh toán, hồ sơ khách hàng, JWT, secret, khóa API hoặc thông tin xác thực.

Nguyên tắc thực hành:

1. **Không log raw payload ở INFO/WARN/ERROR** chỉ vì consumer thất bại. Dùng `messageId`, `messageType`, version và mã lỗi đã kiểm duyệt.
2. Nếu lỗi deserialize làm payload không parse được, ghi broker coordinates và lỗi parser dạng **errorCode/exception class**, không dump bytes toàn bộ.
3. **Không ghi credential, token, password**, chuỗi kết nối hoặc thông tin định danh không cần thiết vào message/log.
4. Header correlation, routing key hay exception message có thể chứa input không tin cậy; tránh **log injection** do CR/LF, escape sequences và payload cực dài.
5. Dùng structured encoder/JSON escaping, allowlist trường và ràng buộc kích thước trước khi đưa vào logger/queue.
6. Không dùng message ID, correlation ID hoặc user ID làm **metric label**; high cardinality có thể làm hệ metrics quá tải.
7. Nếu cần xem payload để điều tra, dùng kênh truy xuất riêng có phân quyền, masking, retention ngắn và audit truy cập.
8. Bảo vệ quyền đọc file/topic/collector; log có thể tiết lộ dòng tiền, trạng thái nghiệp vụ và identifiers nhạy cảm.
9. Với audit sự kiện bắt buộc lưu, cần integrity, durability, retention và khả năng đối soát theo threat model.
10. Đừng coi một giá trị đã hash là tự động an toàn: dữ liệu có entropy thấp có thể đoán ngược qua dictionary attack.

Thông tin trong `Throwable.getMessage()` cũng có thể chứa dữ liệu raw từ message. Log exception class và error code trước; chỉ ghi stack trace trong kênh chẩn đoán phù hợp khi cần.

## 15. Hiệu năng: đừng tự làm đầy hệ thống logging

Trong message consumer throughput cao, logging trên từng delivery có thể tạo số lượng event lớn tương đương hoặc vượt message input. Nếu mỗi message ghi bốn log INFO, xử lý 10.000 message/giây đã tạo 40.000 log event/giây, **chưa kể retries và exception stack traces**.

Chọn điểm ghi theo mục đích:

- **DEBUG:** received/start với metadata tối thiểu khi cần điều tra.
- **INFO hoặc metric:** processing succeeded theo sampling/aggregation nếu không phải audit bắt buộc.
- **WARN/ERROR:** retry budget vượt ngưỡng, DLQ, worker không tiến triển, commit failures, lỗi downstream nghiêm trọng.
- **Metrics:** số received/succeeded/failed/retried/dead-lettered, duration, consumer lag.
- **Tracing:** một span cho processing, liên kết producer/consumer qua trace context.

Thường không cần một `if (log.isDebugEnabled())` cho mọi literal hoặc placeholder với biến đã có. Nhưng khi tạo chi tiết đắt tiền như JSON payload, stack trace string hay danh sách headers:

```java
// Đoạn tích hợp: serializeDebugInfo(...) có thể tốn CPU.
if (log.isDebugEnabled()) {
    log.debug("consumer.debug messageId={} details={}",
            messageId, serializeDebugInfo(message));
}
```

Dùng placeholder không làm phép tính `serializeDebugInfo(message)` trở nên lazy. Chỉ tính dữ liệu đắt tiền nếu level được bật hoặc dùng API Supplier tương thích.

Đừng đo “số received” bằng cách đếm log INFO nếu mức log có thể thay đổi hay sampling. Dùng counter được instrument độc lập cho số liệu vận hành.

## 16. Metrics, tracing và alert cho message consumer

Các metric đề xuất (**không phải mặc định của mọi framework**):

| Metric | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `consumer_deliveries_total{topic,group}` | Số lần broker giao/consumer nhận | Bao gồm redelivery |
| `consumer_processed_total{outcome,type}` | Số lần xử lý theo kết quả | Định nghĩa rõ “processed” |
| `consumer_retries_total{reason,type}` | Số lần quyết định/thực hiện retry | Phân biệt scheduled với delivered |
| `consumer_dead_letters_total{reason,type}` | Số message chuyển DLQ theo mốc xác nhận | Không suy từ số lần gọi |
| `consumer_processing_duration_seconds` | Histogram latency handler | Đo business duration chính xác |
| `consumer_ack_failures_total` | Lỗi ACK/commit theo API | Chỉ khi framework cung cấp kết quả quan sát |
| `consumer_lag` | Tồn đọng của consumer | Định nghĩa phụ thuộc Kafka/queue |
| `consumer_oldest_message_age_seconds` | Tuổi message đang đợi | Phụ thuộc broker/clock |
| `consumer_inflight_messages` | Số event đang xử lý | Phân biệt với queue backlog |

Những label như `topic`, `group`, `messageType`, `errorCode` nên thuộc **tập hữu hạn**. Không đặt `messageId`, `traceId`, `correlationId`, raw payload hoặc exception message vào metric label.

Các alert hữu ích:

- Consumer lag tăng kéo dài.
- Throughput xử lý thành công giảm nhưng số received vẫn cao.
- Retry rate và DLQ rate tăng bất thường.
- Nhiều message thất bại liên tục với cùng `errorCode`.
- Commit/ACK errors hoặc consumer rebalance lặp.
- Processing duration p95/p99 tăng.
- Worker chết, không còn poll/ack nhưng broker backlog vẫn tăng.
- DLQ đã phát triển và chưa có quy trình khôi phục/triage.

**Log, metrics và tracing không thay thế nhau.** Log giúp phân tích một event cụ thể; metrics phát hiện biến động; tracing liên kết các chặng phân tán.

## 17. Kiểm thử log consumer bằng tình huống cụ thể

| Tình huống | Kỳ vọng về log và nghiệp vụ |
| --- | --- |
| Message hợp lệ một lần | Có kết quả thành công; ACK/commit theo chính sách |
| Message không hợp lệ | Lỗi được phân loại; không đánh dấu thành công |
| Lỗi tạm thời | Có attempt và quyết định retry, backoff phù hợp |
| Lỗi permanent | Chuyển cách ly/DLQ theo policy, không retry vô hạn |
| Hai lần giao cùng business event ID | Side effect không nhân đôi; log có thể giải thích duplicate |
| Crash sau commit business, trước ACK | Redelivery có thể xảy ra; idempotency giữ kết quả đúng |
| Commit offset thành công trước side effect | Test chứng minh đây là thứ tự rủi ro cần tránh |
| Publish DLQ lỗi | Không ACK gốc như đã hoàn tất nếu chưa có bảo đảm phù hợp |
| Header correlation thiếu | Có fallback, không NPE |
| Header mang newline/control chars | Không thể tạo log line giả hoặc phá structured JSON |
| Payload có token, PII | Không bị phát ra log/stack trace trái chính sách |
| Consumer chạy song song | MDC không lẫn ID giữa các message |
| Rebalance / shutdown | Quan sát incomplete/inflight/commit theo API |
| Queue logging đầy | Không tạo thêm log storm làm hệ thống nghẽn |
| Sink/collector lỗi | Metrics/cảnh báo vẫn phản ánh sự cố |
| Retry delivery sau timeout | Không đếm lại thành nhiều nghiệp vụ thành công |

Với unit test, có thể đưa logger qua **test appender** và so sánh chính xác các field `event/messageId/outcome/attempt`. Với integration test, khởi động broker thử nghiệm hoặc dùng container phù hợp, cố tình tạo lỗi ACK, retry, DLQ; kiểm tra cả state database, consumer offset và dữ liệu audit cuối.

Đừng chỉ kiểm tra “một dòng `processed` xuất hiện” mà kết luận đã bảo đảm exactly-once. Test cần xác nhận **side effect và ranh giới commit**.

## 18. Sai lầm phổ biến

### 18.1. Log “message success” trước business commit

Nếu transaction rollback, log báo thành công sai. Đặt event sau ranh giới commit thật hoặc dùng outbox cùng transaction.

### 18.2. Gọi ACK rồi mới xử lý

Một số broker có thể coi message đã được tiêu thụ trước khi nghiệp vụ hoàn thành, dẫn tới mất cơ hội xử lý lại sau crash. Cần hiểu auto/manual ACK và chọn thứ tự an toàn cho business requirements.

### 18.3. Đồng nhất `acknowledge()` với broker xác nhận lưu thành công

API acknowledgment có thể chỉ gửi lệnh/đánh dấu offset, không phải receipt cuối. Ghi đúng tên `ack_requested` trừ khi thật sự có callback/xác nhận.

### 18.4. Dùng messageId từ payload mà không validate

Payload có thể thiếu ID, trùng ID, chứa ký tự điều khiển hoặc do sender không đáng tin. Validate/escape và dùng broker coordinates an toàn làm fallback.

### 18.5. Log full payload ở lần deserialize fail

Đây là thời điểm payload có thể chứa dữ liệu độc hại hoặc secret. Chỉ log metadata và mã lỗi phù hợp; giữ raw ở kho cách ly có quyền truy cập chặt nếu cần.

### 18.6. Coi redelivery là lỗi consumer

Với at-least-once delivery, redelivery là tình huống dự kiến khi chưa ACK/commit. Điều quan trọng là **idempotency và lý do redelivery**, không chỉ phát WARN cho mọi duplicate.

### 18.7. Đếm retry bằng số WARN logs

WARN có thể bị tắt/filter/drop/sampling, đồng thời một lần retry có thể tạo nhiều sự kiện. Dùng metric và schema rõ `attempt`/`retryScheduled`.

### 18.8. Không clear MDC trong thread pool

Worker thread có thể được dùng cho message kế tiếp, khiến correlation ID của message cũ gắn nhầm. Phải restore/clear trong `finally`.

### 18.9. Dùng cùng một logger sink cho audit bắt buộc và DEBUG ồn ào

Một queue/sink chung có thể bỏ/chặn audit event quan trọng khi log storm. Tách pipeline theo yêu cầu durability và quyền truy cập.

### 18.10. Xem mọi `dead_lettered` đều đã ghi bền vững

Đích DLQ có thể lỗi, publisher confirm chưa đến hoặc ACK gốc thất bại. Phải dùng trạng thái dựa trên guarantee thực tế và có đối soát.

## 19. Checklist triển khai

- [ ] Định nghĩa các mốc `received`, `processing_succeeded`, `ack_requested`, `retry`, `dead_lettered` và thời điểm phát.
- [ ] Gắn message ID logic, source/topic/queue, consumer group, delivery/attempt và correlation ID nếu có.
- [ ] Phân biệt **business commit** với ACK/offset commit; chỉ log `succeeded` sau điều kiện thành công thực.
- [ ] Có idempotency bền vững cho side effect có thể bị xử lý lại.
- [ ] Phân loại retryable/permanent, retry budget, backoff và quy trình DLQ.
- [ ] Không ACK message gốc quá sớm khi DLQ/retry/side effect chưa có bảo đảm phù hợp.
- [ ] Dùng structured logging, mã event ổn định, error code và giới hạn độ dài input.
- [ ] Không log raw payload/token/PII/secret và không đưa ID động vào metric labels.
- [ ] Khôi phục/clear MDC sau mỗi message; propagate trace context đúng cách qua async.
- [ ] Bám vào semantics **thực tế của Kafka, RabbitMQ hoặc JMS**, không sao chép ngữ nghĩa ACK giữa các broker.
- [ ] Kiểm soát log volume, async appender backpressure, sampling và log storm.
- [ ] Theo dõi received/succeeded/failed/retried/DLQ, lag, processing duration và ACK errors bằng metrics độc lập.
- [ ] Kiểm thử redelivery, duplicate, rollback, crash, DLQ failure, commit error, rebalances và shutdown.
- [ ] Nếu log là bằng chứng audit bắt buộc lưu, thiết kế durability/retention/integrity riêng khỏi diagnostic logging.

**Kết luận:** Log message consumer phải giải thích **message nào được nhận, xử lý ra sao, ở lần thử nào và đã đến ranh giới xác nhận nào**. Ghi rõ mốc `received`, `processing_succeeded`, `retry`, `dead_lettered` và `ack_requested` giúp điều tra dễ dàng, nhưng **không thay thế idempotency, transaction và guarantee của broker**. Muốn log đáng tin, hãy đặt sự kiện đúng thời điểm, bảo vệ dữ liệu và kiểm chứng đường ghi đến sink thật sự.
