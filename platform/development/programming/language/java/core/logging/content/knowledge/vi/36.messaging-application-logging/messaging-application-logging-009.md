# Duplicate message log trong ứng dụng message Java

## 1. Vấn đề: vì sao một message xuất hiện nhiều lần trong log?

Trong hệ thống bất đồng bộ, một message có thể được giao lại cho consumer sau lỗi xử lý, timeout, restart hoặc khi bước acknowledgement/commit chưa hoàn tất. Vì vậy, các dòng như sau không nhất thiết chỉ ra bug:

```text
INFO event=message_received eventId=evt-100 attempt=1
INFO event=message_received eventId=evt-100 attempt=2
```

Đây có thể là **hai lần nhận cùng một sự kiện logic**. Nhưng cũng có trường hợp chỉ **một lần nhận** mà logger, appender hoặc collector in ra **hai dòng giống hệt**. Hai hiện tượng này cần được phân biệt trước khi “xóa log trùng”.

Trong bài này, **duplicate message log** được hiểu là việc phân tích và xử lý những bản ghi log lặp trong ứng dụng sử dụng message queue, message broker hoặc event-driven architecture. Trọng tâm là:
- Phân biệt **message redelivery**, **duplicate business event**, **duplicate log emission** và **duplicate downstream ingestion**.
- Ghi nhận đúng **message ID, delivery attempt, consumer, outcome và correlation ID**.
- Tránh ghi nhận **một lần xử lý nghiệp vụ thành công** cho mỗi lần nhận khi message bị giao lại.
- Thiết kế **idempotent consumer** và chính sách ack/commit để chống tác động nghiệp vụ lặp.
- Điều tra log lặp từ Logback/Log4j 2, logger additivity, nhiều handler/appender và collector.
- Giảm nhiễu, chi phí và lượng dữ liệu nhạy cảm trong log mà vẫn giữ dấu vết xử lý.

> **Điểm cần nhớ:** Log có hai dòng giống nhau không tự chứng minh nghiệp vụ đã xử lý hai lần. Ngược lại, log chỉ có một dòng cũng không chứng minh đã tránh được duplicate side effect. Phải đối chiếu **sự kiện logic**, **lần delivery**, **kết quả xử lý** và **đích xuất log**.

## 2. Bốn kiểu “trùng” dễ bị nhầm

| Kiểu trùng | Dấu hiệu | Nguyên nhân thường gặp | Điều cần kiểm tra |
| --- | --- | --- | --- |
| **Message redelivery** | Cùng `eventId` nhận lại, attempt khác | Chưa ack/commit, timeout, restart, requeue | Broker metadata, lần nhận, thời điểm ack |
| **Duplicate logical message** | Producer xuất nhiều message biểu diễn cùng hành động | Retry gửi, outbox replay, publisher bug, client gửi lặp | Business key/event ID, producer idempotency |
| **Duplicate log emission** | Một lần gọi logger xuất hai dòng qua cùng pipeline | Additivity, gắn nhiều handler/appender, instrumentation kép | Logger tree, appender refs, handler count |
| **Duplicate log ingestion** | Một log event được collector/index lưu nhiều lần | Forwarder gửi lại, retry sau mất ACK, nhiều agent thu cùng file | Agent pipeline, document/event ID tại sink |

Một message broker có thể bảo đảm thứ tự hay cách giao riêng theo sản phẩm, nhưng không nên suy luận rằng **mọi consumer xử lý chính xác một lần**. Trong mô hình *at-least-once*, redelivery là khả năng phải được xử lý như tình huống bình thường.

**Ví dụ:** Một consumer hoàn tất lưu hóa đơn vào database nhưng bị crash trước khi commit offset. Khi chạy lại, broker có thể giao lại bản tin đó. Hai dòng `message_received` là hợp lý; câu hỏi nghiêm trọng hơn là **hóa đơn có bị tạo hai lần hay không**.

Ngược lại, nếu một request chỉ tạo một delivery và `logger.info(...)` được gọi một lần, nhưng root logger cùng child logger đều tham chiếu console appender, output có thể bị nhân đôi. Sửa idempotency trong consumer không khắc phục kiểu này.

## 3. Luồng nhận, xử lý, ack và redelivery

Một luồng xử lý phổ biến:

```text
Producer -> Broker -> Consumer
                         |
                         v
                   Receive message
                         |
                         v
                  Identify event ID
                         |
                +--------+--------+
                |                 |
           Chưa xử lý         Đã xử lý
                |                 |
                v                 v
       Apply business effect   Skip effect
                |                 |
                v                 v
        Commit durable state   Record duplicate
                |                 |
                +--------+--------+
                         |
                         v
                  Ack / commit
                         |
                    Broker state
```

**Cửa sổ gây duplicate:** Consumer xử lý nghiệp vụ thành công, nhưng **ack/commit thất bại hoặc chưa kịp thực hiện**. Broker chưa biết consumer đã xử lý nên có thể gửi lại. Vì vậy, một event có thể có **nhiều lần delivery hợp lệ**.

**Cửa sổ gây mất xử lý:** Consumer ack/commit **trước** khi xử lý bền vững, rồi crash. Broker có thể coi message đã xong trong khi nghiệp vụ chưa hoàn tất. Không nên chuyển ack lên đầu chỉ để làm biến mất log redelivery.

Thứ tự thiết kế thường hướng đến:
1. Xác minh message và idempotency key.
2. Thực hiện thay đổi nghiệp vụ và ghi nhận đã xử lý **trong cùng ranh giới transaction khả thi**.
3. Commit transaction bền vững.
4. Ack/commit message sau khi transaction hoàn tất.
5. Nếu bước 4 thất bại, chấp nhận delivery lại và **bỏ qua side effect nhờ cơ chế idempotency**.

Không có một quy tắc ack duy nhất cho mọi broker và mọi kiểu xử lý. Kafka dùng offset commit/transaction theo cách khác RabbitMQ acknowledgement hay SQS delete message. Tuy nhiên, **không lấy việc log ít đi làm mục tiêu thay thế cho tính đúng đắn nghiệp vụ**.

### 3.1. Kafka

Với Kafka consumer, việc ghi log `message_received` mỗi lần `poll` trả record có thể tạo log lặp nếu record được xử lý lại sau rebalance/restart hoặc offset chưa được commit tương ứng. Các trường hữu ích:
- `topic`, `partition`, `offset`: vị trí record trong một topic/partition cụ thể.
- `consumer_group`, `consumer_instance`: bối cảnh consumer.
- `event_id` hoặc idempotency key: định danh **sự kiện logic** ở payload/envelope nếu được producer xác định ổn định.

**Không dùng mỗi offset làm business event ID** khi sự kiện có thể được republish sang topic khác: offset chỉ định danh vị trí trong một partition của topic. Kafka producer idempotence và Kafka transactions có thể cung cấp bảo đảm trong một số luồng Kafka-to-Kafka được cấu hình đúng; **không tự động bảo đảm side effect ở database hoặc HTTP API ngoài Kafka chỉ xảy ra một lần**.

### 3.2. RabbitMQ

Với RabbitMQ, message có thể được gửi lại khi channel/connection đóng trước acknowledgement hoặc consumer `nack` với requeue. Metadata như cờ `redelivered` là một tín hiệu về việc message đã được giao lại, nhưng **không phải bộ đếm lần thử chính xác** và không nên là chứng cứ duy nhất cho một quyết định nghiệp vụ.

`deliveryTag` mang ý nghĩa trong phạm vi channel, **không phải event ID bất biến xuyên các lần delivery**. Có thể dùng application message ID và business idempotency key được gắn từ producer; ack/nack phải theo contract của channel/client đang dùng.

### 3.3. Amazon SQS hoặc queue có visibility timeout

Ở queue kiểu visibility timeout, một message có thể được consumer khác nhận khi thời gian ẩn hết trước khi message được xóa. `receiptHandle` thường gắn với **một lần nhận**, vì vậy không được dùng làm ID logic để deduplicate. Nếu có trường chỉ số lần nhận, hãy xem đó là **metadata của broker** với semantics riêng, không phải bộ đếm nghiệp vụ đáng tin tuyệt đối.

Với FIFO queue hoặc cơ chế deduplication của broker, vẫn cần hiểu **thời hạn/ranh giới** dedup của broker và các external side effects. Không coi broker-side dedup là thay thế cho idempotency ở consumer nếu thao tác phải chính xác qua lỗi/crash.

## 4. Một log event có thể mô tả những giai đoạn khác nhau

Không nên ghi mọi tình huống dưới một message `Processed message X`. Hãy dùng event type phản ánh đúng việc đã xảy ra.

| Event log | Ý nghĩa chính xác | Khi nào phát |
| --- | --- | --- |
| `MESSAGE_RECEIVED` | Consumer nhận/được giao một message | Khi message đến handler |
| `MESSAGE_VALIDATION_FAILED` | Message sai schema/hợp đồng | Sau kiểm tra hợp lệ |
| `MESSAGE_PROCESSING_STARTED` | Bắt đầu xử lý, **chưa có nghĩa thành công** | Trước business operation |
| `MESSAGE_APPLIED` | Business effect đã được commit/ghi nhận thành công theo contract | Sau xác nhận ranh giới xử lý |
| `MESSAGE_DUPLICATE` | Có bằng chứng event đã được xử lý, side effect được bỏ qua | Khi idempotency store trả kết quả duplicate |
| `MESSAGE_PROCESSING_FAILED` | Handler thất bại | Sau lỗi, với mã lỗi an toàn |
| `MESSAGE_RETRY_SCHEDULED` | Retry/requeue đã được yêu cầu | Khi lập lịch theo cơ chế ứng dụng |
| `MESSAGE_ACK_REQUESTED` | Consumer đã gọi API ack/commit | Khi gọi, **không đồng nghĩa broker đã xác nhận** |
| `MESSAGE_ACK_CONFIRMED` | Có xác nhận ack/commit theo khả năng API | Chỉ khi client API thực sự cung cấp bằng chứng |
| `MESSAGE_DEAD_LETTERED` | Message được gửi/được xác nhận ở DLQ theo contract | Khi đã có kết quả phù hợp |

**Tên event phải phù hợp với thời điểm ghi.** Ví dụ `MESSAGE_APPLIED` không nên được log trước khi database commit thành công. Tuy nhiên, kể cả log sau commit cũng có thể bị mất nếu process crash giữa commit và ghi log. Nếu **audit event bắt buộc phải tồn tại** cùng thay đổi nghiệp vụ, hãy lưu nó vào database/outbox trong transaction, thay vì chỉ dựa vào logger.

Khi nhận một message lặp, log `MESSAGE_RECEIVED` nhiều lần có thể là **mong muốn** để phục vụ điều tra. Cần phân biệt nó với `MESSAGE_APPLIED` là business effect được kỳ vọng không lặp.

## 5. Schema log cho message delivery

Một structured event có thể có các trường sau:

```json
{
  "event": "message_received",
  "event_id": "evt-100",
  "message_id": "msg-900",
  "consumer": "invoice-projector",
  "destination": "billing.events",
  "delivery_attempt": 2,
  "redelivered": true,
  "trace_id": "trace-demo-42",
  "processing_result": "RECEIVED",
  "timestamp": "2026-11-10T03:00:00Z"
}
```

Đây chỉ là **dữ liệu minh họa**, không phải event quan sát thật. Trong production, cần định nghĩa rõ:
- `event_id`: định danh bền vững của **sự kiện logic** từ producer/envelope. Event này có thể được gửi nhiều lần.
- `message_id`: ID message ở tầng ứng dụng/broker, có thể đổi nếu message được publish lại; không mặc định bằng event ID.
- `consumer`: tên handler/subscription/công việc tiêu thụ event. Một event có thể được **nhiều consumer khác nhau xử lý hợp lệ**.
- `destination`: topic, queue hoặc subscription; dùng tên ổn định.
- `delivery_attempt`: đến từ broker nếu có semantics phù hợp hoặc do consumer tự quản lý. **Không bịa số lần thử** nếu không có nguồn đáng tin.
- `redelivered`: tín hiệu từ broker khi hỗ trợ; không đồng nghĩa event đã được xử lý nghiệp vụ.
- `trace_id`/`correlation_id`: phục vụ liên kết với request/producer/tracing; phải kiểm soát định dạng và độ tin cậy.
- `processing_result`: `RECEIVED`/`APPLIED`/`DUPLICATE_SKIPPED`/`FAILED`; dùng enum thay vì chuỗi dữ liệu tự do.
- `timestamp`: thời điểm cụ thể của giai đoạn phát sinh log, thường chuẩn hóa UTC.
- `broker_position`: tùy công nghệ, như Kafka topic/partition/offset; không tự dùng làm event ID xuyên các hệ thống.

**Không log raw payload** theo mặc định. Message body có thể chứa email, password, access token, payment data, tài liệu riêng tư hoặc dữ liệu nhị phân. Không ghi `Authorization`, secret header hoặc full message object chỉ vì cần tìm duplicate. Trong nhiều trường hợp **event ID và metadata đã đủ**.

### 5.1. Ba loại ID không được hoán đổi

```text
Business operation:   paymentId=pay-42
Logical event:        eventId=evt-100
Broker delivery #1:   attempt=1
Broker delivery #2:   attempt=2
Log statement/event:  log emitted at each stage
```

- **Business key** (`paymentId`) xác định thực thể/hoạt động nghiệp vụ; một payment có thể có **nhiều sự kiện khác nhau** (created, authorized, captured). Không nên coi tất cả event của cùng payment là duplicate.
- **Event ID** định danh một lần phát sinh sự kiện logic và nên ổn định khi producer retry cùng sự kiện.
- **Delivery identity/attempt** nhận diện một lần giao; thay đổi khi redelivery, nhưng semantics phụ thuộc broker.
- **Log event identity** nếu được hệ thống logging cung cấp sẽ phục vụ dedup ở collector; đừng đánh đồng nó với business event.

Đôi khi hai message có **event ID khác nhau nhưng cùng business operation bị gửi lặp**. Khi đó dedup theo event ID đơn thuần không đủ; nghiệp vụ cần **idempotency key hoặc ràng buộc uniqueness** thích hợp, ví dụ `payment_id + operation_type`. Ngược lại, hai event khác nhau chia sẻ resource ID **không mặc nhiên là duplicate**.

## 6. Ví dụ Java 17 chạy độc lập: log mỗi delivery, chỉ áp dụng business effect một lần

Ví dụ sử dụng **JUL** (`java.util.logging`) có sẵn trong JDK 17. Nó mô phỏng ba lần giao:
1. `evt-100` được nhận lần đầu, áp dụng nghiệp vụ.
2. `evt-100` được nhận lại, log duplicate và **bỏ qua** business effect.
3. `evt-101` là event khác, áp dụng nghiệp vụ.

`Set` và `Map` trong chương trình nằm trong **bộ nhớ một luồng** chỉ để minh họa sự khác biệt giữa log delivery và log business effect. Đừng dùng mô hình này để chứng minh idempotency production khi có restart, nhiều consumer, concurrency hoặc lỗi giữa xử lý và đánh dấu.

Tạo file `DuplicateMessageLogDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class DuplicateMessageLogDemo {
    private record Message(String eventId, String payload) {}

    private static final class DemoConsumer {
        private final Logger logger;
        private final Set<String> applied = new HashSet<>();
        private final Map<String, Integer> deliveryCounts = new HashMap<>();

        DemoConsumer(Logger logger) {
            this.logger = logger;
        }

        void onDelivery(Message message) {
            String eventId = message.eventId();
            int attempt = deliveryCounts.merge(eventId, 1, Integer::sum);

            logger.info("event=message_received eventId="
                    + eventId + " attempt=" + attempt);

            if (applied.add(eventId)) {
                // Chỉ mô phỏng business effect trong bộ nhớ.
                logger.info("event=business_applied eventId=" + eventId);
            } else {
                logger.info("event=message_duplicate eventId="
                        + eventId + " attempt=" + attempt
                        + " action=SKIP_BUSINESS");
            }

            // Đây KHÔNG phải một lời gọi ACK tới broker.
            logger.info("event=ack_simulated eventId="
                    + eventId + " attempt=" + attempt);
        }

        int uniqueBusinessEffects() {
            return applied.size();
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("lesson.message.duplicate");
        logger.setLevel(Level.INFO);
        logger.setUseParentHandlers(false);

        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getMessage());
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
        output.setLevel(Level.ALL);
        logger.addHandler(output);

        try {
            DemoConsumer consumer = new DemoConsumer(logger);
            Message first = new Message("evt-100", "private-payload");

            consumer.onDelivery(first);
            consumer.onDelivery(first); // Redelivery giả lập.
            consumer.onDelivery(new Message("evt-101", "other-private"));

            System.out.println("uniqueBusinessEffects="
                    + consumer.uniqueBusinessEffects());
        } finally {
            logger.removeHandler(output);
            output.close();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac DuplicateMessageLogDemo.java
java DuplicateMessageLogDemo
```

**Stdout chính xác** của chương trình trên:

```text
event=message_received eventId=evt-100 attempt=1
event=business_applied eventId=evt-100
event=ack_simulated eventId=evt-100 attempt=1
event=message_received eventId=evt-100 attempt=2
event=message_duplicate eventId=evt-100 attempt=2 action=SKIP_BUSINESS
event=ack_simulated eventId=evt-100 attempt=2
event=message_received eventId=evt-101 attempt=1
event=business_applied eventId=evt-101
event=ack_simulated eventId=evt-101 attempt=1
uniqueBusinessEffects=2
```

**Diễn giải đúng:**
- Có **3 delivery được mô phỏng** nhưng chỉ có **2 event ID được coi là đã áp dụng** trong một lần chạy.
- Dòng `message_received` cho `evt-100` xuất hiện hai lần là **đúng với hai lần nhận**; không nên xóa dòng thứ hai nếu mục đích là chẩn đoán redelivery.
- Chỉ có một `business_applied` cho `evt-100`; lần hai dùng `message_duplicate` và `SKIP_BUSINESS`.
- `attempt` trong demo là **bộ đếm cục bộ**, không phải Kafka offset, RabbitMQ delivery tag hay số retry do broker bảo đảm. Nó **reset khi JVM restart**.
- `ack_simulated` chỉ là dòng mô phỏng; code không tích hợp message broker và **không chứng minh message đã được ack**.
- `payload` tồn tại trên `Message` nhưng **không xuất trong log**, tránh lộ nội dung.
- `Handler` xuất `record.getMessage()` vào stdout và tắt parent handlers, do đó output không có timestamp phụ. Chương trình giả định chạy một lần trong JVM mới để minh họa.

**Điểm yếu có chủ đích:** `applied.add(eventId)` và business effect thực không cùng database transaction; demo cũng không hỗ trợ concurrency. Nếu application crash sau khi thêm vào set nhưng trước khi thao tác nghiệp vụ hoàn tất, cơ chế như vậy có thể bỏ qua sai message sau khi hồi phục (nếu state được lưu độc lập). Nếu có nhiều instances, mỗi instance có một set riêng. **Không dùng in-memory Set làm idempotency store production**.

## 7. Idempotent consumer: giải pháp nằm ở nghiệp vụ, không phải ở logger

Khi nhận message nhiều lần, application cần làm cho side effect của **cùng một hành động logic** không bị nhân đôi. Đây là ý tưởng *idempotency*.

Ví dụ:
- Tạo hóa đơn: cùng idempotency key không tạo hai invoice.
- Ghi nhận thanh toán: cùng `payment_capture_id` không trừ tiền hai lần.
- Cập nhật projection: cùng event có thể được nhận lại mà không cộng tổng số lần nữa.
- Gửi email: cùng business request cần cơ chế chống gửi lại phù hợp; chỉ check database **chưa đủ** nếu gửi email nằm ngoài transaction.

### 7.1. Chọn khóa chống trùng đúng phạm vi

Không có khóa duy nhất cho mọi trường hợp. Một thiết kế phổ biến là:

```text
dedup_key = (consumer_name, event_id)
```

Lý do thêm `consumer_name`: cùng một event có thể phải được **nhiều consumer khác nhau** xử lý, ví dụ `invoice-projector` và `analytics-indexer`. Nếu dùng một set toàn hệ thống theo event ID, consumer đầu tiên có thể khiến các consumer còn lại bỏ qua công việc hợp lệ.

Nhưng khi producer có thể sinh hai event ID cho **cùng hành động kinh doanh bị retry**, cần thêm ràng buộc nghiệp vụ như `paymentId + captureOperation` hoặc idempotency key thống nhất từ API. Phân tích thế nào là “cùng thao tác” dựa trên domain model, không chỉ dựa vào text message hay timestamp.

Không dùng:
- Hash toàn payload làm khóa duy nhất: serialization order, metadata và các field không ổn định có thể làm hash khác; hai message giống body cũng chưa chắc là cùng event.
- Timestamp làm ID: nhiều event có cùng timestamp hoặc cùng event có timestamp mới khi republish.
- `deliveryTag` hoặc `receiptHandle` làm stable event ID: chúng có thể thay đổi qua lần nhận.
- Kafka `offset` làm identity xuyên topic hoặc sau republish.
- Trace ID làm idempotency key: một trace có thể có nhiều sự kiện/hành động hợp lệ.

### 7.2. Database transaction và unique constraint

Với nhiều consumer instances, hãy lưu trạng thái xử lý trong hệ thống có tính bền vững và phép kiểm tra/tạo khóa **atomic**. Ví dụ PostgreSQL:

```sql
CREATE TABLE processed_message (
    consumer_name TEXT NOT NULL,
    event_id      TEXT NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
```

Trong transaction nghiệp vụ, có thể thử insert:

```sql
-- Mã SQL minh họa cho PostgreSQL, chạy trong transaction.
INSERT INTO processed_message (consumer_name, event_id)
VALUES ('invoice-projector', 'evt-100')
ON CONFLICT (consumer_name, event_id) DO NOTHING
RETURNING event_id;
```

Nếu câu lệnh trả **một row**, consumer đã nhận quyền thực hiện **lần xử lý đầu tiên** trong transaction này; chỉ khi đó mới chạy cập nhật nghiệp vụ trong **cùng transaction** và commit. Nếu trả **0 row**, khóa đã tồn tại, có thể bỏ qua business side effect và xử lý acknowledgement theo chính sách. Kết quả còn phụ thuộc isolation, lock và việc record cũ có thật sự tương ứng với trạng thái committed hoàn tất.

Một pseudocode gọn:

```text
begin transaction
    inserted = insertDedupKeyIfAbsent(consumerName, eventId)
    if inserted:
        applyBusinessChangesInSameTransaction()
        insertAuditOrOutboxIfRequired()
commit transaction
ackOrCommitBrokerMessage()
```

**Bắt buộc chú ý:**
1. **Không đặt dấu processed bền vững rồi commit trước khi chạy business operation.** Crash ở giữa có thể làm lần nhận sau tưởng đã xử lý thành công.
2. **Không chỉ làm `SELECT` rồi `INSERT` theo hai bước độc lập**. Hai consumers chạy đồng thời có thể cùng thấy “chưa tồn tại”. Unique constraint/atomic upsert hoặc khóa phù hợp mới đóng race.
3. Nếu business transaction rollback, dedup insert cũng phải rollback; khi retry, consumer được phép thử lại.
4. ACK broker **sau commit** vẫn có thể bị mất; khi redelivery, dedup store nhận ra event đã hoàn tất.
5. Với side effect ngoài transaction như HTTP API, email hoặc thanh toán qua cổng ngoài, cần idempotency key được **dịch vụ đích** hỗ trợ, outbox/worker với retry, hoặc quy trình reconcile/compensation. Không tuyên bố transaction local bảo đảm exactly-once cho network side effect.
6. Nếu có retention/cleanup bảng processed messages, thời gian giữ khóa phải xét **cửa sổ redelivery, DLQ redrive và replay**; xóa khóa quá sớm có thể khiến event cũ được áp dụng lại.
7. Tính duy nhất của khóa phải gắn với **version/schema/consumer contract** nếu một event có thể được replay hợp lệ cho một phiên bản projection mới. Không dùng dedup để cản quá trình rebuild có chủ đích.

### 7.3. Kết quả nghiệp vụ và log có độ bền khác nhau

Giả sử DB commit thành công nhưng JVM crash trước `logger.info("MESSAGE_APPLIED")`. Side effect là thật, nhưng **dòng log thành công có thể không tồn tại**. Nếu logger in trước commit, log “thành công” có thể được xuất rồi transaction lại rollback.

Vì thế:
- Log kỹ thuật giúp điều tra nhưng có thể thiếu.
- Audit nghiệp vụ bắt buộc nên có **event lưu bền vững** trong cùng transaction hoặc cơ chế có tương đương contract.
- Không lấy số dòng `MESSAGE_APPLIED` làm nguồn chân lý kế toán nếu log pipeline không có bảo đảm phù hợp.
- Idempotency store/DB constraint mới là cơ chế chống tác động nghiệp vụ lặp trong thiết kế đã chọn, không phải lệnh tắt log duplicate.

## 8. Ghi nhận retry và lỗi mà không tạo thông điệp sai

Một message thất bại có thể được retry bởi ứng dụng hoặc broker. Thiết kế log nên tránh gọi mọi lần nhận là “thành công”.

Ví dụ một chuỗi event:

```text
message_received   eventId=evt-100 attempt=1
processing_failed  eventId=evt-100 attempt=1 reason=TEMPORARY_DB_ERROR
retry_requested    eventId=evt-100 attempt=1 policy=BACKOFF
message_received   eventId=evt-100 attempt=2
business_applied   eventId=evt-100 attempt=2
ack_requested      eventId=evt-100 attempt=2
```

Đây là **ví dụ luồng**, không phải stdout từ demo. Các mốc trong hệ thống thật có thể khác tùy transaction và broker.

Điều cần quan sát:
- `reason` là **mã lỗi chuẩn hóa**, không tự động in cả payload/exception message có thể chứa token, PII.
- `retry_requested` chỉ có nghĩa đã yêu cầu retry; nếu scheduler/broker không xác nhận, đừng log chắc chắn retry đã được lưu.
- `attempt` có thể là app counter, broker metadata hoặc attempt được quản lý bởi framework; cần chỉ ra nguồn.
- Với lỗi tạm thời, backoff/jitter và giới hạn số lần thử giúp tránh log storm và tải lại downstream.
- Với message poison không bao giờ parse được, cần chiến lược DLQ/quarantine và log reference thay vì dump toàn bộ message.
- Đảm bảo các log failure/duplicate được gắn `eventId`, `consumer`, correlation metadata để phân biệt những message khác nhau có cùng nội dung lỗi.

**Đừng log exception giống nhau ở mọi tầng.** Framework retry handler, listener method và exception handler tổng có thể đều gọi logger cho cùng lỗi. Hãy quy định tầng sở hữu event failure và tầng nào chỉ thêm context/tracing để tránh nhân ba volume.

## 9. Log lặp do cấu hình logging, không phải broker

Không phải hai dòng giống nhau luôn đến từ hai deliveries. Trong Logback/Log4j 2/JUL, một log event có thể được đưa tới **nhiều handler/appender**.

### 9.1. Logback additivity

Giả sử logger cho package `com.example.consumer` tham chiếu console appender và root cũng tham chiếu đúng console appender. Theo mặc định, Logback logger có **additivity**, nên event có thể đi qua logger con rồi lên root, làm một dòng xuất **hai lần**.

Một cấu hình Logback mẫu giúp tránh lặp khi muốn child logger có appender riêng:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.consumer"
            level="INFO" additivity="false">
        <appender-ref ref="CONSOLE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

`additivity="false"` dừng propagation tới ancestor loggers từ package này; không phải cơ chế message deduplication. Cần hiểu đúng quy hoạch appender: nếu cố ý muốn child logger ghi cả console lẫn audit sink ở root, tắt additivity bừa bãi có thể làm **mất log cần thiết**. Sửa theo mục tiêu định tuyến của hệ thống, không áp dụng hàng loạt.

Một lỗi tương tự ở **JUL** là gắn `Handler` vào logger con và vẫn để `setUseParentHandlers(true)`, khiến parent cũng ghi record. Với **Log4j 2**, tên thuộc tính/config có thể khác nhưng cũng cần kiểm tra additivity và appender references theo bản đang chạy.

### 9.2. Các nguyên nhân khác

- **Gắn cùng handler/appender ở nhiều tầng** hoặc khởi tạo logging configuration nhiều lần trong lifecycle.
- Một listener tự log failure, trong khi retry middleware/AOP interceptor cũng log cùng exception.
- Một message bị **hai listener containers** thực sự nhận theo topology của broker; có thể là hai subscriptions hợp lệ chứ không phải trùng ở logger.
- Một agent thu cùng container stdout và cùng file log thêm lần nữa.
- Forwarder/collector gửi lại batch sau khi mất ACK, khiến một raw log record được index hai lần.
- Một lớp bridge giữa JUL, SLF4J và backend cấu hình sai, tạo vòng hoặc emission không mong muốn.

**Cách phân biệt:** Gắn một `eventId` logic và một correlation/delivery identifier khi có, kiểm tra số lần listener callback chạy, số lần logger method được gọi, sau đó so sánh stdout/file/collector. Nếu callback chạy một lần mà stdout có hai dòng, nghi ngờ logger/appender. Nếu stdout chỉ có một dòng mà index có hai documents, nghi ngờ collector. Nếu callback chạy hai lần với một eventId, đó có thể là redelivery hoặc hai subscriptions.

Không dựa riêng vào timestamp: hai log giống nhau gần thời điểm không đủ để kết luận có hai lần xử lý.

## 10. Structured logging và SLF4J 2.x

Với SLF4J 2.x, có thể đặt các field vào một event thay vì nối message string dài. Đoạn code dưới đây **chỉ là tích hợp**, cần logger, message và các biến context đã được chuẩn bị, cùng backend hỗ trợ xuất key-value fields:

```java
// SLF4J 2.x + backend/encoder tương thích.
logger.atInfo()
      .addKeyValue("event", "message_received")
      .addKeyValue("event_id", safeEventId)
      .addKeyValue("consumer", "invoice-projector")
      .addKeyValue("attempt", knownAttempt)
      .addKeyValue("redelivered", redelivered)
      .log("Message received");
```

Trong đó:
- `safeEventId` là ID đã được kiểm tra cú pháp/độ dài, không phải full payload.
- `knownAttempt` chỉ được ghi khi hệ thống có nguồn số đếm rõ ràng; nếu không, bỏ field hoặc ghi unknown theo schema.
- `redelivered` đến từ broker/client contract nếu có; không tự đoán từ timestamp.
- Backend/encoder phải được cấu hình để xuất key-value; pattern text không tự đảm bảo mọi field xuất hiện.
- Nếu dùng MDC/ThreadContext, đảm bảo cleanup tại cuối callback và propagation chính xác qua executor/async threads. Không đưa raw message body/token vào MDC.
- Structured event giúp truy vấn, nhưng **không tự loại dữ liệu nhạy cảm**, cũng không giải quyết duplicate delivery.

Dùng schema và tên field thống nhất giữa các consumers, nhưng không ép hai backend có semantics khác nhau phải giả vờ có một `deliveryAttempt` giống nhau.

## 11. Bao nhiêu log là vừa đủ?

Nếu mỗi message bị retry 50 lần, log ở mức INFO toàn bộ payload và stack trace có thể tăng đáng kể CPU, heap, dung lượng lưu, chi phí collector và độ nhiễu dashboard.

Một chính sách tham khảo:

| Tình huống | Mức/khối lượng log hợp lý |
| --- | --- |
| Nhận event thường xuyên | DEBUG hoặc INFO tóm tắt theo nhu cầu observability, không raw body |
| Xử lý thành công | Một event kết quả sau commit nếu thực sự cần |
| Duplicate phát hiện và bỏ qua | Event phân biệt `DUPLICATE_SKIPPED`, có ID và counter |
| Retry tạm thời | Mã nguyên nhân, attempt và lịch backoff, tránh stack trace trùng lặp |
| Hết retry / DLQ | Event nổi bật với reference, consumer, lỗi đã chuẩn hóa và nơi lưu |
| Poison message | Không dump payload nhạy cảm; quarantine/định danh an toàn |
| Audit bắt buộc | Theo chính sách riêng, không sampling tùy ý |

**Sampling:** có thể giảm log volume của những sự kiện nhận thường xuyên, nhưng không nên sampling mù quáng log audit bắt buộc, thao tác tài chính hoặc log cần phục vụ điều tra bảo mật. Một hệ thống có thể giữ **metrics counters** cho toàn bộ attempts và log chi tiết có chọn lọc, nhưng phải nêu rõ số liệu nào là tổng thật, số liệu nào là mẫu.

**Metrics:** sử dụng các label ổn định như consumer, destination, result, failure reason. **Không gắn `eventId`, request ID hay message ID làm label metrics** vì cardinality có thể tăng vô hạn. Các ID này thuộc log/trace hoặc kho tra cứu phù hợp.

Các chỉ số gợi ý:
- `message_deliveries_total{consumer,result}`.
- `message_duplicates_skipped_total{consumer}`.
- `message_processing_failures_total{consumer,reason}`.
- `message_processing_duration_seconds`.
- `message_ack_failures_total{consumer}`.
- `message_dlq_total{consumer,reason}`.
- Queue lag/backlog, consumer restarts/rebalances và storage health.

Đừng suy ra `processed_unique_total = deliveries_total - duplicates_total` nếu còn failed, dropped, invalid hoặc skipped vì lý do khác. Cần định nghĩa counters theo trạng thái rõ ràng và kiểm tra tính nhất quán.

## 12. Debug khi thấy log duplicate: quy trình điều tra

### Bước 1: xác định “trùng” theo cấp nào

Chọn một `eventId` cụ thể, biết nó thuộc consumer/destination nào. Đừng kết luận chỉ từ hai dòng text có cùng message. Xem timestamp, consumer instance, broker pointer, attempt/source, event type và correlation ID.

### Bước 2: đếm callback của consumer

Tạo test/staging có listener callback count, và quan sát broker metadata. Nếu callback được gọi hai lần, kiểm tra:
- Có redelivery do ack/commit timeout, rebalance/restart, requeue, visibility timeout hay không?
- Có hai consumer/subscription được cấu hình cùng xử lý message theo chủ đích hay không?
- Producer có publish hai logical events hay cùng message hai lần?
- Hệ thống có retry **nội bộ handler** bên trong cùng delivery trước khi broker biết kết quả không?

### Bước 3: xác định side effect

Kiểm tra idempotency table, database unique constraint, external payment/email API và business transaction. Hai `MESSAGE_RECEIVED` có thể chỉ ứng với một effect. Nếu có hai effects, điều tra dedup key và ranh giới atomicity.

### Bước 4: kiểm tra logger/appender tại điểm phát

Với cùng callback, đếm invocation của logger; xem logger tree và additivity. So sánh log ở console/file trước collector. Nếu output bị nhân đôi tại JVM, sửa cấu hình logging hoặc double instrumentation chứ không cần thay retry policy.

### Bước 5: kiểm tra tuyến thu gom

Nếu JVM xuất một bản nhưng collector/index chứa hai bản, kiểm tra agent thu nhiều nguồn, retry/replay, index document ID và policy dedup tại sink. Nếu collector dùng at-least-once delivery, duplicate ở index có thể là hiệu ứng của retry batch.

### Bước 6: kiểm thử cả lỗi và phục hồi

Tạo failure injection: process business commit thành công rồi giả lập mất ACK; xác minh lần nhận lại được log đúng `MESSAGE_DUPLICATE` và không tạo side effect lần nữa. Thử restart/nhiều instances, độc lập với demo in-memory.

## 13. Bảng kiểm thử mẫu

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Một message, một delivery | Một business effect, log nhận và kết quả phù hợp |
| Giao lại sau xử lý thành công | Hai `RECEIVED` có thể xuất hiện, chỉ một business effect |
| Crash trước DB commit | Transaction rollback, xử lý lại được khi nhận lại |
| Crash sau DB commit nhưng trước ack | Redelivery được nhận diện duplicate, không áp lại side effect |
| Hai consumer instances xử lý cùng event đồng thời | Unique constraint/transaction ngăn race |
| Producer publish lại cùng event ID | Cùng consumer deduplicate theo policy |
| Hai event khác ID nhưng cùng payment operation | Domain idempotency key ngăn tác động nghiệp vụ lặp nếu thật sự cùng operation |
| Hai consumers khác nhau nhận một event | Mỗi consumer hợp lệ được xử lý riêng trong scope của nó |
| Message đi qua DLQ rồi redrive sau nhiều ngày | Retention dedup key đủ dài theo policy hoặc xử lý replay có chủ đích |
| Message không có ID/ID sai | Schema validation/failure policy; không tự tạo ID mới rồi coi là giống event gốc |
| Event ID chứa newline/ký tự điều khiển | Log được escaping/validation, không chèn record giả |
| Listener một lần nhưng console hai dòng | Kiểm tra additivity/handler refs/instrumentation |
| Console một dòng nhưng collector hai bản | Kiểm tra shipper retry/duplicate ingestion |
| Async logging queue đầy | Metrics/drop policy và audit durability được kiểm tra |
| Broker ack API thất bại | Không log `ACK_CONFIRMED` giả; có cơ chế retry/redelivery phù hợp |

Kiểm thử phải đối chiếu cả **log**, **trạng thái nghiệp vụ**, **dedup store** và **broker**. Một unit test chỉ đếm số log không thể chứng minh idempotency.

## 14. Các sai lầm thường gặp

| Sai lầm | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Xóa toàn bộ log trùng theo `eventId` | Làm mất dấu vết retry, lỗi, thời điểm nhận | Giữ event type + attempt, tối ưu volume đúng chỗ |
| Coi mọi `message_received` là `processed` | Nhầm nhận với commit business | Log từng giai đoạn chính xác |
| Tắt retry chỉ để không thấy log lặp | Có thể mất message khi consumer lỗi | Giữ delivery policy phù hợp và idempotency |
| Dùng in-memory `Set` production | Mất state sau restart, không chia sẻ giữa replicas | Durable store + atomic constraint |
| Check-then-insert không transaction | Hai consumer có thể cùng xử lý | Unique key/atomic upsert và business transaction |
| Commit dedup trước khi business effect | Crash có thể khiến xử lý bị bỏ qua vĩnh viễn | Cùng transaction, xác nhận commit trước ack |
| Ack trước khi commit nghiệp vụ | Crash có thể gây mất xử lý | Thiết kế thứ tự ack/commit theo broker |
| Dùng Rabbit `deliveryTag` làm business ID | Tag thay đổi theo channel/delivery | Event ID/idempotency key ổn định |
| Dùng Kafka offset làm ID xuyên các lần republish | Offset chỉ là vị trí trong topic/partition | Event ID do producer quy định |
| Dùng SQS receipt handle làm dedup key | Thay đổi khi nhận lại | Application event ID ổn định |
| Log raw payload để tìm duplicate | Lộ PII/token, tăng log volume | Log ID và metadata đã được chọn |
| Bật sampling cho audit bắt buộc | Có thể mất bằng chứng phải lưu | Tách audit durability khỏi diagnostic sampling |
| Tắt Logback additivity không xem topology | Có thể làm mất log ở root/appender khác | Sửa cấu hình theo routing mong muốn |
| Gắn message ID vào metrics labels | Cardinality cực cao | Dùng label consumer/result, ID ở log |
| Chỉ xem log mà không xem side effect | Không phát hiện charge/email/invoice bị lặp | Đối chiếu DB, external API và idempotency record |
| Nghĩ Kafka EOS bảo đảm mọi DB/HTTP effect đúng một lần | Bảo đảm có phạm vi, không bao trùm ngoại hệ thống | Idempotent downstream/outbox phù hợp |

## 15. Bài tập tự kiểm tra

**Câu 1.** Một listener ghi hai dòng `MESSAGE_RECEIVED` có cùng `eventId` nhưng `attempt=1` và `attempt=2`. Có thể khẳng định bug logging hay nghiệp vụ chạy hai lần không?

**Không.** Có thể là redelivery hợp lệ. Cần xem số lần business effect được commit và chứng cứ ack/offset, đồng thời kiểm tra callback count.

**Câu 2.** `logger.info("Received {}", id)` được gọi một lần, nhưng Logback console xuất hai lần. Nơi kiểm tra đầu tiên?

**Logger tree, appender refs và additivity**; cũng cần xem duplicate handler/instrumentation. Không thay idempotency logic chỉ vì output bị nhân đôi.

**Câu 3.** Consumer commit DB rồi crash trước ack. Khi nhận lại message, nên xử lý ra sao?

Dùng dedup key bền vững theo consumer và event, xác nhận business change đã commit và **skip side effect lặp**, sau đó ack theo chính sách broker. Có thể log `MESSAGE_DUPLICATE` để lưu bằng chứng redelivery.

**Câu 4.** Hai message có `eventId` khác nhau nhưng cùng `paymentCaptureId` của cùng thao tác. Dedup chỉ theo event ID có đủ?

**Không hẳn.** Nếu producer/operation cho phép cùng hành động được phát với hai event IDs, cần idempotency key ở tầng domain hoặc khóa duy nhất tại payment operation.

**Câu 5.** Một event được gửi cho `billing-projector` và `analytics-projector`. Nếu billing đánh dấu event ID đã xử lý, analytics có phải bỏ qua không?

**Không.** Hai consumers có công việc độc lập; dedup scope thường gồm `consumer_name + event_id` hoặc một khóa tương đương.

**Câu 6.** Bộ đếm `deliveryAttempt` trong RAM của một consumer có phản ánh số lần redelivery trên mọi replicas sau restart không?

**Không.** Nó reset theo lifecycle và không chia sẻ state. Cần phân biệt app-local count với broker-provided attempt metadata và không khẳng định nó là số lần global.

## 16. Checklist áp dụng trong dự án Java

Trước khi kết luận đã xử lý đúng duplicate message log:

1. **Phân biệt bốn loại trùng**: broker redelivery, logical event duplicate, logger/appender double emission và collector duplicate ingestion.
2. Có **event ID ổn định**, business idempotency key đúng domain và consumer scope rõ ràng.
3. Log riêng các event `RECEIVED`, `APPLIED`, `DUPLICATE_SKIPPED`, `FAILED`, retry và ack; không dùng một message “processed” cho mọi trạng thái.
4. Ghi attempt/redelivered và broker position **chỉ khi có nguồn đúng semantics**; không dùng offset/deliveryTag/receiptHandle làm business identity.
5. Consumer idempotency dùng durable store/unique constraint và transaction cùng business change; không dựa vào RAM hoặc check-then-act.
6. Hiểu cửa sổ crash **trước commit**, **sau commit trước ack** và **sau ack**, cũng như các hậu quả mất/lặp.
7. Với side effect ngoài DB, có idempotency key ở dịch vụ đích, outbox/reconcile hoặc chiến lược bù trừ thích hợp.
8. Logback/Log4j 2/JUL handler tree và routing được kiểm tra; không nhân đôi output ngoài chủ đích.
9. Pipeline log collector không thu cùng nguồn nhiều lần hoặc đã có chính sách nhận biết duplicate ingestion nếu cần.
10. Không đưa raw message payload, credential, token hoặc dữ liệu cá nhân vào log; event ID được validation và escape.
11. Có metrics deliveries/duplicates/failures/retries/DLQ với label cardinality thấp; ID riêng ở log/trace.
12. Kiểm thử concurrency, restart, DLQ redrive, external failure, offset/ack loss, async queue và collector retry.
13. Audit bắt buộc được lưu bằng cơ chế đủ bền vững, không dựa vào một dòng logger.info không có xác nhận.
14. Bảng điều tra phân biệt **số delivery**, **số event logic** và **số side effects thực tế**.

**Kết luận:** Trong ứng dụng message Java, một message được nhận lại và có nhiều dòng log chưa chắc là lỗi. Cần biết dòng log đó mô tả **delivery**, **xử lý nghiệp vụ**, **retry**, **ack** hay **việc xuất log qua appender/collector**. Hãy thiết kế event schema rõ ràng, idempotency bền vững và quan sát đủ các giai đoạn; giữ dấu vết duplicate hữu ích, nhưng không nhân đôi side effect hay làm lộ payload chỉ để phục vụ debug.