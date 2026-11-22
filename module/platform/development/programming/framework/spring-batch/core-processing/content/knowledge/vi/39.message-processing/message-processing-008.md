# Dead-letter message

Trong hệ thống xử lý message, có những message thất bại lặp đi lặp lại dù consumer đã retry. Ví dụ payload JSON sai cú pháp, schema version không được hỗ trợ, dữ liệu nghiệp vụ thiếu trường bắt buộc hoặc một message luôn làm processor ném exception. Nếu broker tiếp tục redeliver message đó, nó có thể chặn tiến độ xử lý và tạo tải không cần thiết. **Dead-letter message** là message được chuyển sang một nơi lưu riêng (dead-letter queue, dead-letter topic hoặc quarantine store) sau khi không thể xử lý theo chính sách đã định.

Trong Spring Batch, cần phân biệt dead-letter handling ở tầng broker với skip handling ở tầng Step. Broker có thể đưa message vào DLQ khi delivery/acknowledgement thất bại quá số lần cho phép. Spring Batch có thể xác định một item không hợp lệ và skip nó trong chunk. Hai cơ chế không tự động thay thế nhau. Nếu Step đọc message rồi phát hiện lỗi nghiệp vụ, ứng dụng phải quyết định rõ cách lưu message lỗi, acknowledge nguồn và bảo đảm không mất hoặc xử lý trùng dữ liệu.

## 1. Dead-letter message là gì?

Dead-letter message là message không thể tiếp tục xử lý bình thường và được chuyển sang một luồng cách ly để điều tra, sửa dữ liệu hoặc replay sau này. Nơi nhận thường được gọi là:

- Dead-letter queue (DLQ) với broker dạng queue.
- Dead-letter topic (DLT) với Kafka hoặc hệ thống topic-based.
- Quarantine queue/store nếu tổ chức muốn phân biệt dữ liệu bị cách ly với DLQ do broker quản lý.

Ví dụ luồng xử lý:

```text
Input queue / topic
        |
        v
Consumer / Spring Batch reader
        |
        v
Validate + process
        |
        +---- Thành công ----> Business writer ----> Commit
        |
        +---- Lỗi tạm thời --> Retry có giới hạn
        |                         |
        |                         +--> Thành công: tiếp tục
        |                         |
        |                         +--> Vượt giới hạn
        |                                  |
        +---- Lỗi cố định -----------------+
                                           |
                                           v
                                   Dead-letter route
                                           |
                                           v
                                   DLQ / DLT / quarantine
```

Message được đưa vào dead-letter route cần giữ đủ thông tin để biết nó đến từ đâu, vì sao thất bại và có thể replay an toàn hay không. DLQ là nơi lưu lỗi có chủ đích, không phải thùng rác để xóa message khó xử lý.

## 2. Poison message và nguyên nhân cần dead-letter

*Poison message* là message gây lỗi mỗi khi được xử lý, thường do nội dung hoặc trạng thái cố định. Một số ví dụ:

- JSON/XML malformed, không parse được.
- Payload thiếu field bắt buộc hoặc field có kiểu sai.
- Schema version không được ứng dụng hiện tại hỗ trợ.
- Giá trị enum hoặc discriminator không nằm trong allowlist.
- Business key không tồn tại hoặc vi phạm quy tắc nghiệp vụ.
- Message chứa tham chiếu không thể resolve sau khi dữ liệu nguồn đã được xác nhận.
- Message vượt giới hạn kích thước hoặc cấu trúc lồng nhau được phép.

Không phải mọi lỗi đều là poison message. Database tạm thời unavailable, broker timeout, network reset hoặc deadlock có thể tự phục hồi. Đưa các lỗi tạm thời vào DLQ ngay lập tức có thể làm cách ly dữ liệu hợp lệ chỉ vì hạ tầng đang gặp sự cố.

## 3. Phân loại lỗi trước khi quyết định retry hay dead-letter

Chính sách xử lý nên phân biệt ít nhất ba nhóm:

| Nhóm lỗi | Ví dụ | Hành động thường phù hợp |
|---|---|---|
| Transient infrastructure error | Timeout, broker unavailable, deadlock, connection reset | Retry có giới hạn, backoff và jitter |
| Permanent data/contract error | JSON sai, schema không hỗ trợ, field bắt buộc thiếu | Dead-letter hoặc quarantine |
| Business rejection | Order bị hủy, số tiền vượt giới hạn, trạng thái không hợp lệ | Có thể ghi kết quả từ chối nghiệp vụ; chỉ DLQ nếu cần điều tra/replay |

Một business rejection có thể là kết quả hợp lệ của nghiệp vụ chứ không phải lỗi kỹ thuật. Ví dụ khách hàng không đủ hạn mức có thể được ghi thành trạng thái `REJECTED`, không nhất thiết đưa message vào DLQ. Ngược lại, payload thiếu customer ID có thể là vi phạm contract cần cách ly.

Classifier lỗi nên dựa trên exception type, mã lỗi nghiệp vụ và context của message. Tránh chỉ dựa vào chuỗi exception message vì wording có thể thay đổi theo library/version.

## 4. Retry trước khi đưa vào DLQ

Một chính sách phổ biến là thử lại lỗi transient trước khi dead-letter:

```text
Attempt 1 -> lỗi transient -> chờ backoff
Attempt 2 -> lỗi transient -> chờ backoff
Attempt 3 -> lỗi transient -> chờ backoff
Attempt 4 -> vượt giới hạn -> DLQ
```

Retry nên có:

- Số lần thử tối đa.
- Backoff tăng dần hoặc fixed delay phù hợp.
- Jitter để nhiều consumer không retry đồng loạt.
- Timeout tổng và giới hạn thời gian giữ message.
- Phân loại exception retryable và non-retryable.
- Metric về retry count, delivery count và kết quả cuối.

Không retry vô hạn. Một message lỗi cố định sẽ chiếm worker, tăng chi phí broker và làm chậm message hợp lệ phía sau.

## 5. Retry trong Spring Batch khác broker redelivery

Spring Batch fault tolerance có thể retry một item hoặc chunk theo cấu hình Step. Broker lại có cơ chế redelivery riêng khi message chưa được acknowledge hoặc offset chưa commit.

Hai tầng có thể cùng hoạt động:

```text
Broker delivery attempt
        |
        v
Spring Batch chunk attempt
        |
        +--> Retry trong Step
        |       |
        |       +--> thành công: chunk commit
        |       +--> hết retry: Step xử lý skip/fail
        |
        +--> transaction rollback / no acknowledgement
                |
                v
           Broker redelivery
```

Nếu cả Spring Retry và broker đều retry, số lần xử lý thực tế có thể lớn hơn giới hạn ở từng tầng. Cần xác định một tầng chịu trách nhiệm retry chính cho mỗi loại lỗi, hoặc tính toán rõ tổng số lần thử.

## 6. Skip của Spring Batch không tự động là dead-letter

Trong fault-tolerant Step, Spring Batch có thể skip item khi exception thuộc loại được cho phép và chưa vượt `skipLimit`. Skip có nghĩa item không tiếp tục qua luồng xử lý bình thường của Step. Nó không tự động gửi message đến DLQ.

Ví dụ:

```java
return new StepBuilder("processMessagesStep", jobRepository)
        .<InboundMessage, ProcessedMessage>chunk(100, transactionManager)
        .reader(messageReader)
        .processor(messageProcessor)
        .writer(messageWriter)
        .faultTolerant()
        .skip(InvalidPayloadException.class)
        .skipLimit(50)
        .build();
```

Đoạn cấu hình chỉ cho phép Step skip một số lỗi `InvalidPayloadException`. Nó chưa lưu message lỗi vào DLQ. Muốn dead-letter, cần thêm một cơ chế lưu/quarantine message, chẳng hạn `SkipListener`, broker error handler hoặc outbox writer.

Không nên cấu hình `skip(Exception.class)` rộng chỉ để Job tiếp tục. Điều đó có thể che lỗi database, lỗi lập trình hoặc lỗi hạ tầng vốn cần làm Step thất bại.

## 7. Dùng SkipListener để ghi nhận item bị skip

`SkipListener` cung cấp callback khi item bị skip ở các giai đoạn read, process hoặc write. Với lỗi process/write, callback nhận được item tương ứng và có thể ghi thông tin vào quarantine/outbox.

```java
public class MessageSkipListener
        implements SkipListener<InboundMessage, ProcessedMessage> {

    private final DeadLetterOutboxRepository outboxRepository;

    public MessageSkipListener(DeadLetterOutboxRepository outboxRepository) {
        this.outboxRepository = outboxRepository;
    }

    @Override
    public void onSkipInProcess(InboundMessage item, Throwable error) {
        outboxRepository.save(DeadLetterRecord.from(
                item.messageId(), item.payload(), "PROCESS", error));
    }

    @Override
    public void onSkipInWrite(ProcessedMessage item, Throwable error) {
        outboxRepository.save(DeadLetterRecord.from(
                item.messageId(), item.originalPayload(), "WRITE", error));
    }

    @Override
    public void onSkipInRead(Throwable error) {
        // Không có item được truyền vào callback này.
        // Reader cần lưu raw message/metadata nếu muốn quarantine read failure.
    }
}
```

Ví dụ đăng ký listener:

```java
.faultTolerant()
.skip(InvalidPayloadException.class)
.skipLimit(50)
.listener(messageSkipListener)
```

Đây là ví dụ minh họa; kiểu `InboundMessage`, `ProcessedMessage` và repository là model của ứng dụng. Với callback `onSkipInRead`, Spring Batch chỉ cung cấp exception, không cung cấp item vì reader chưa trả được item hợp lệ. Nếu cần lưu raw payload khi parse thất bại, reader phải giữ envelope/raw bytes và metadata lỗi, hoặc để broker-level error handler xử lý.

## 8. Ghi dead-letter bằng transactional outbox

Nếu Step vừa ghi database vừa cần gửi message sang broker DLQ, không nên giả định database transaction và broker send là atomic. Một cách an toàn là ghi dead-letter record vào outbox table cùng transaction database của chunk, rồi publisher riêng gửi record đó sang broker.

Ví dụ bảng:

```sql
CREATE TABLE dead_letter_outbox (
    dead_letter_id  VARCHAR(100) PRIMARY KEY,
    original_id     VARCHAR(100) NOT NULL,
    source_name     VARCHAR(300) NOT NULL,
    payload         TEXT NOT NULL,
    error_code      VARCHAR(100) NOT NULL,
    error_message   VARCHAR(1000),
    failed_at       TIMESTAMP NOT NULL,
    published_at    TIMESTAMP NULL
);
```

Trong `SkipListener`, ghi record vào outbox bằng repository tham gia cùng database transaction của Step nếu cấu hình cho phép. Spring Batch gọi skip listener ở giai đoạn ngay trước khi transaction chunk commit; vì vậy, một outbox repository dùng cùng transaction manager/DataSource có thể commit record dead-letter cùng checkpoint/business data.

Publisher riêng đọc outbox chưa publish, gửi đến DLQ, rồi cập nhật trạng thái. Nếu broker nhận message nhưng publisher crash trước khi đánh dấu `published_at`, publisher có thể gửi lại. Vì vậy dead-letter record cần ID ổn định và consumer/operator tooling cần deduplicate.

Outbox tạo khả năng retry bền vững cho việc gửi DLQ; nó không biến database và broker thành một distributed transaction.

## 9. Broker-managed DLQ và application-managed quarantine

Có hai nơi có thể quyết định dead-letter:

**Broker-managed DLQ:** broker đưa message vào DLQ sau khi delivery/acknowledgement thất bại theo redelivery policy hoặc consumer error handler. Đây là cơ chế của broker/integration container.

**Application-managed quarantine:** ứng dụng đã nhận và đọc được message, nhưng xác định payload hoặc business data không hợp lệ. Ứng dụng ghi message vào quarantine/DLT theo chính sách của mình.

| Tiêu chí | Broker-managed DLQ | Application quarantine |
|---|---|---|
| Thời điểm | Khi broker/consumer infrastructure xác định delivery thất bại | Sau khi ứng dụng parse/validate/process |
| Lý do điển hình | Consumer không ack, listener liên tục throw, delivery limit vượt ngưỡng | Schema sai, business validation fail, loại payload không hỗ trợ |
| Thông tin lỗi | Delivery count, broker headers, listener exception tùy integration | Có thể thêm error code, stage, validation detail và JobExecution ID |
| Cách cấu hình | Broker redelivery policy, listener container error handler | SkipListener, outbox, custom writer/reader hoặc application service |
| Phạm vi | Phụ thuộc broker/provider | Do ứng dụng quản lý |

Không nên để cả broker và ứng dụng dead-letter cùng một lỗi mà không có quy tắc rõ ràng. Điều đó có thể tạo hai bản sao DLQ hoặc làm message bị route nhiều lần.

## 10. JMS Dead Letter Queue

Với JMS, broker thường có cấu hình redelivery policy và dead-letter destination. Khi message bị rollback hoặc không được acknowledge, broker có thể redeliver. Sau số lần giao tối đa, broker chuyển message sang DLQ theo cấu hình provider.

Một số metadata JMS hữu ích:

- `JMSMessageID`: định danh message do provider tạo.
- `JMSCorrelationID`: liên kết message với request/flow khác.
- `JMSRedelivered`: cho biết message đã từng được giao trước đó theo semantics JMS.
- `JMSXDeliveryCount`: delivery count nếu provider hỗ trợ property chuẩn này.
- Application properties: event ID, source system, schema version hoặc batch ID.

Tên DLQ, số lần redelivery, delay, poison-message handling và cách lưu exception thường được cấu hình theo broker như ActiveMQ Classic, Artemis hoặc provider khác. JMS API không quy định một destination tên `DLQ` dùng chung cho mọi broker.

Nếu dùng Spring JMS listener container, error handling và transaction configuration quyết định khi nào session rollback và broker có redeliver hay không. Với custom Spring Batch `ItemReader`, cần tự bảo đảm message không bị acknowledge trước khi chunk hoàn tất nếu muốn rollback có thể đưa message trở lại nguồn.

## 11. Kafka Dead Letter Topic

Kafka không có DLQ tích hợp ở cấp broker giống một queue destination cố định. Một convention phổ biến là tạo topic riêng, ví dụ:

```text
orders.input
orders.input.DLT
```

Consumer hoặc listener error handler gửi record lỗi sang DLT sau khi retry đã hết. DLT thường giữ payload gốc và bổ sung headers cho topic/partition/offset ban đầu cùng thông tin exception.

Trong Spring Kafka listener container, có thể dùng `DefaultErrorHandler` với `DeadLetterPublishingRecoverer` để retry rồi publish record thất bại sang DLT. Ví dụ khái niệm:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> template) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
    );
}
```

Sau đó gắn common error handler vào listener container factory theo phiên bản Spring Kafka đang dùng. Constructor, generic type, destination resolver và header behavior có thể khác theo version; cần đối chiếu dependency của ứng dụng.

**Lưu ý:** `DefaultErrorHandler` là cơ chế của Spring Kafka listener container. Nó không tự động được gọi khi Spring Batch dùng một custom Kafka `ItemReader` hoặc consumer API trực tiếp. Với reader tự quản lý poll/offset, ứng dụng phải thiết kế dead-letter route và commit offset phù hợp.

## 12. Kafka DLT headers và giữ nguồn gốc record

Khi chuyển record sang DLT, cần giữ metadata để có thể xác định chính xác record ban đầu:

- Original topic.
- Original partition.
- Original offset.
- Original timestamp.
- Original key.
- Consumer group hoặc application identity nếu cần.
- Exception class và mô tả lỗi đã được làm sạch.
- Delivery/retry attempt.
- Correlation ID, event ID và schema version.

Spring Kafka `DeadLetterPublishingRecoverer` có thể thêm các header nguồn gốc theo convention của framework. Hãy kiểm tra header names trong version đang dùng và tránh tự thêm một bộ header trùng tên.

Nếu DLT cần giữ cùng partition number, topic đích phải có đủ partition tương ứng hoặc destination resolver phải chọn partition hợp lệ. Nếu không, publish có thể thất bại. Không nên giả định topic DLT tự có partition count phù hợp.

## 13. Dead-letter trong một Spring Batch Step đọc message

Khi Spring Batch đọc message bằng custom reader, lỗi có thể xuất hiện ở các giai đoạn khác nhau:

1. Lỗi nhận message từ broker.
2. Lỗi deserialize payload trong reader.
3. Lỗi validation hoặc xử lý trong processor.
4. Lỗi ghi kết quả trong writer.

Mỗi giai đoạn có thông tin và transaction behavior khác nhau.

| Giai đoạn | Có item hợp lệ trong callback không? | Cách xử lý thường gặp |
|---|---|---|
| Broker receive/poll | Có thể mới chỉ có raw record/metadata | Broker error handling hoặc reader giữ envelope |
| Deserialize trong `read()` | Thường chưa có item typed | Lưu raw payload/headers trước khi parse; custom exception/quarantine |
| `process()` | Có input item | `SkipListener.onSkipInProcess` có thể ghi dead-letter record |
| `write()` | Có output item; có thể cần original payload | `SkipListener.onSkipInWrite` hoặc error handling riêng |

`SkipListener.onSkipInRead(Throwable)` không nhận item. Nếu reader parse payload rồi ném exception trước khi trả item, cần giữ raw bytes, source partition/offset hoặc message ID ở reader để có thể tạo dead-letter record.

Nếu message vẫn đang được giữ bởi broker transaction, hãy quyết định DLQ publish và input acknowledgement được phối hợp thế nào. Ghi raw payload vào một database outbox rồi commit transaction là một phương án, nhưng phải bảo đảm message input chỉ được ack sau khi outbox record đã bền vững.

## 14. Không acknowledge trước khi dead-letter đã bền vững

Giả sử ứng dụng nhận một message lỗi và gửi nó đến DLQ. Nếu ứng dụng acknowledge message nguồn trước, rồi publish DLQ thất bại, message gốc có thể mất mà không có bản dead-letter.

Thứ tự không an toàn:

```text
Receive source message
       |
       v
ACK source message
       |
       v
Publish to DLQ fails
       |
       v
Message lost
```

Một thứ tự an toàn hơn trong mô hình local transaction:

```text
Receive source message
       |
       v
Persist dead-letter intent (e.g. DB outbox)
       |
       v
Commit durable record
       |
       v
ACK source message
       |
       v
Publisher retries delivery to DLQ
```

Chi tiết chính xác phụ thuộc broker và cách consumer transaction hoạt động. Mục tiêu là luôn có ít nhất một bản bền vững của message lỗi trước khi nguồn bị xác nhận. Nếu database và broker cùng hỗ trợ XA, có thể phối hợp transaction; nếu không, outbox/inbox cùng idempotency là lựa chọn phổ biến.

## 15. DLQ và chunk rollback

Một chunk có thể chứa nhiều message. Nếu một item lỗi trong processor và được skip, Spring Batch có thể rollback/replay chunk theo fault-tolerance algorithm trước khi xác định item được skip. `SkipListener` được gọi theo lifecycle skip, và callback được thiết kế để tránh gọi lặp cho cùng một skip trong các tình huống rollback nội bộ của chunk.

Tuy nhiên, gửi trực tiếp đến broker DLQ từ callback hoặc processor là side effect ngoài transaction database nếu không có transaction coordinator. Nếu chunk rollback sau khi publish DLQ thành công, item có thể được xử lý lại và publish duplicate.

Để kiểm soát:

- Dùng dead-letter ID ổn định, thường dựa trên source message ID hoặc topic/partition/offset.
- Ghi outbox record cùng transaction database của chunk.
- Publisher gửi outbox record theo at-least-once và consumer DLQ deduplicate.
- Không xóa/ack source message trước khi durable intent được commit.
- Kiểm thử các điểm crash giữa persist, publish và acknowledge.

## 16. Cấu trúc dead-letter envelope

Không nên chỉ gửi một chuỗi exception vào DLQ. Hãy định nghĩa envelope có cấu trúc để operator và replay tool hiểu được:

```json
{
  "deadLetterId": "dlq-8b5f...",
  "originalMessageId": "event-12345",
  "source": {
    "system": "orders-service",
    "destination": "orders.input",
    "partition": 2,
    "offset": 9812
  },
  "payloadType": "ORDER_CREATED",
  "schemaVersion": 3,
  "failedStage": "PROCESS",
  "errorCode": "CUSTOMER_NOT_FOUND",
  "errorType": "InvalidOrderException",
  "failedAt": "2026-11-15T10:30:00Z",
  "attempts": 3,
  "correlationId": "corr-456",
  "payload": {
    "orderId": 1001,
    "customerId": 9999
  }
}
```

Đây là schema minh họa. Envelope thực tế cần quy định:

- Payload gốc được giữ nguyên byte-for-byte hay được deserialize/serialize lại.
- Header nào được copy, header nào được chuẩn hóa.
- Error message có thể chứa dữ liệu nhạy cảm hay không.
- Giới hạn kích thước payload và cách lưu attachment lớn.
- Timestamp theo UTC và format nhất quán.
- Phiên bản schema của dead-letter envelope.
- TTL/retention và quyền truy cập.

Nếu có thể, giữ raw payload gốc để replay không bị thay đổi do serializer hiện tại. Đồng thời lưu một phần payload đã parse hoặc error summary để điều tra thuận tiện.

## 17. Không làm lộ dữ liệu nhạy cảm trong DLQ

DLQ thường được truy cập bởi nhóm vận hành hoặc hệ thống replay rộng hơn ứng dụng nghiệp vụ. Vì vậy, payload trong DLQ cần được bảo vệ như dữ liệu nguồn.

Các biện pháp nên cân nhắc:

- Mã hóa dữ liệu khi truyền và khi lưu.
- ACL/authorization riêng cho DLQ, chỉ cấp quyền cần thiết.
- Không đưa password, token, session key hoặc secret vào headers/log.
- Mask hoặc loại bỏ dữ liệu cá nhân khỏi error summary nếu không cần thiết.
- Giới hạn retention và có chính sách xóa theo yêu cầu pháp lý.
- Audit thao tác đọc, export, replay và purge.
- Kiểm soát kích thước message để tránh payload cực lớn làm cạn storage.

Không log toàn bộ raw payload khi parse lỗi. Có thể log deadLetterId, messageId, source, errorCode và correlationId để truy vấn record có quyền truy cập.

## 18. Redrive và replay từ DLQ

**Redrive** là đưa message từ DLQ trở lại luồng xử lý, thường sau khi lỗi đã được sửa. **Replay** là chạy lại message đã lưu, có thể vào cùng input destination hoặc một luồng replay riêng.

Một quy trình redrive nên có các bước:

1. Xác định nguyên nhân gốc và sửa code, cấu hình hoặc dữ liệu tham chiếu.
2. Chọn đúng message theo batch ID, event ID, thời gian hoặc error code.
3. Kiểm tra message có còn hợp lệ theo schema hiện tại không.
4. Xác nhận side effect trước đó đã xảy ra hay chưa.
5. Replay một lượng nhỏ trước, quan sát kết quả.
6. Tăng dần tốc độ replay để không gây tải đột biến.
7. Ghi nhận replay attempt, operator/job ID và kết quả.
8. Giữ bản DLQ gốc theo retention/audit policy.

Không tự động requeue toàn bộ DLQ ngay khi deployment mới hoàn tất. Một số message có thể vẫn không hợp lệ hoặc có thể đã được xử lý một phần trước khi lỗi.

## 19. Giữ nguyên message ID khi replay

Khi replay, nên giữ original message ID/event ID để deduplication nhận ra đây là cùng một sự kiện nghiệp vụ. Có thể thêm replay metadata riêng:

```json
{
  "originalMessageId": "event-12345",
  "replayId": "replay-20261115-0042",
  "replayAttempt": 2,
  "replayedAt": "2026-11-15T11:00:00Z",
  "replayRequestedBy": "batch-operations"
}
```

Không thay original ID bằng một UUID mới rồi kỳ vọng inbox/unique constraint ngăn duplicate. Nếu hệ thống cần ID vận chuyển mới, giữ cả `originalMessageId` và `replayMessageId` để phân biệt transport attempt với business event identity.

## 20. Replay và thứ tự message

Replaying message cũ có thể phá vỡ thứ tự nghiệp vụ. Ví dụ event `OrderCreated` bị dead-letter, nhưng `OrderPaid` và `OrderShipped` đã được xử lý. Replay `OrderCreated` sau cùng có thể tạo trạng thái không hợp lệ.

Trước khi replay, cần xác định:

- Message có phụ thuộc event trước/sau không?
- Ordering key hoặc Kafka partition key là gì?
- Các event sau đã được áp dụng chưa?
- Có thể replay theo aggregate ID hoặc sequence number không?
- Có cần rebuild projection từ event log thay vì phát lại một message đơn lẻ không?
- Có thể xử lý idempotent và kiểm tra version để từ chối event cũ không?

Với dữ liệu cần ordering, replay theo nhóm aggregate hoặc theo sequence đã xác định. Không chỉ sort theo thời gian dead-letter vì thời điểm lỗi không nhất thiết là thứ tự nghiệp vụ gốc.

## 21. Kafka retry topic và DLT

Trong Kafka, có thể dùng retry topic cho các lỗi transient cần delay trước khi thử lại, rồi chuyển sang DLT sau khi vượt số lần thử. Ví dụ:

```text
orders.input
     |
     +--> xử lý thành công
     |
     +--> lỗi transient --> orders.retry.1
     |                         |
     |                         +--> retry thành công
     |                         |
     |                         +--> tiếp tục lỗi --> orders.retry.2
     |                                                |
     |                                                +--> orders.DLT
     |
     +--> lỗi permanent ------------------------------> orders.DLT
```

Retry topic tách việc chờ retry khỏi consumer chính, nhưng có thể làm thay đổi ordering giữa các record. Một record đang retry có thể được xử lý sau record đến sau nó ở topic chính. Nếu ordering theo key/aggregate là bắt buộc, cần thiết kế retry strategy phù hợp và hiểu semantics của framework đang dùng.

Spring Kafka có các cơ chế retry topic như `@RetryableTopic` cho listener-based processing. Chúng thuộc Spring Kafka listener infrastructure; không tự động áp dụng cho custom Spring Batch reader. Với Batch, có thể triển khai retry/DLT bằng reader/writer riêng, outbox và các Step điều phối.

## 22. JMS redelivery và DLQ

Với JMS, message thường được redeliver khi transacted session rollback hoặc message không được acknowledge theo mode đã cấu hình. Broker quản lý delivery count và áp dụng redelivery policy. Khi vượt ngưỡng, broker chuyển message đến dead-letter destination.

Một số điểm cần kiểm tra theo provider:

- Maximum redelivery attempts.
- Redelivery delay và exponential backoff.
- Dead-letter destination mặc định hoặc per-queue.
- Cách giữ original destination và exception metadata.
- Hành vi khi DLQ destination không tồn tại hoặc đầy.
- Message expiration/TTL và DLQ retention.
- Chính sách với non-persistent message.

Không nên hard-code tên DLQ theo convention của một broker nếu ứng dụng phải chạy trên nhiều provider. Đưa destination vào cấu hình và kiểm thử trên broker thực tế.

## 23. Spring Kafka DefaultErrorHandler và DeadLetterPublishingRecoverer

Với Spring Kafka listener container, `DefaultErrorHandler` có thể retry exception theo backoff và gọi recoverer khi đã hết retry. `DeadLetterPublishingRecoverer` là một recoverer phổ biến để publish record lỗi sang DLT.

Ví dụ cấu hình ở mức khái niệm:

```java
@Bean
DefaultErrorHandler errorHandler(KafkaTemplate<Object, Object> template) {
    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);

    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);
    return new DefaultErrorHandler(recoverer, backOff);
}
```

Để phân loại lỗi cố định không cần retry, có thể cấu hình exception là non-retryable bằng API của `DefaultErrorHandler` trong phiên bản tương ứng. Khi recoverer publish DLT thành công, container mới có thể commit/ack input theo error handler semantics.

Đây là cấu hình listener container, không phải cấu hình chung cho mọi `ItemReader`. Với Spring Batch polling trực tiếp Kafka, cần tích hợp rõ producer transaction/offset commit hoặc dùng outbox để tránh ack input trước khi DLT record được lưu bền vững.

## 24. DLQ bị đầy hoặc publish DLQ thất bại

Dead-letter destination cũng là một resource có thể gặp sự cố:

- DLQ hết quota hoặc retention storage.
- Kafka DLT không có partition tương ứng.
- Producer không có quyền publish.
- Broker unavailable.
- Payload vượt message size limit.
- Serialization của dead-letter envelope thất bại.

Không nên acknowledge message nguồn nếu dead-letter record chưa được lưu bền vững theo chính sách. Nếu DLT publish thất bại, có thể giữ message nguồn để retry, rollback transaction hoặc ghi vào outbox/database quarantine. Cần tránh vòng lặp gửi DLQ lỗi rồi tiếp tục redeliver vô hạn mà không có alert.

DLQ cũng cần monitoring về depth, oldest message age, publish failure và storage utilization. Nếu DLQ đầy mà không ai xử lý, hệ thống chỉ chuyển backlog từ queue chính sang queue lỗi.

## 25. Poison message có thể chặn partition hoặc queue

Trong queue FIFO hoặc một số mô hình ordering, một message poison ở đầu có thể ngăn message sau được xử lý nếu broker giữ thứ tự và message liên tục redeliver. Với Kafka, record lỗi có thể làm consumer không commit offset qua vị trí đó, khiến partition bị kẹt.

Dead-letter sau số lần thử hữu hạn giúp consumer tiến tiếp, nhưng phải đánh đổi ordering. Khi bỏ qua offset/message lỗi, các record sau có thể được xử lý trước khi record cũ được sửa và replay.

Nếu ordering là yêu cầu bắt buộc, cần quyết định liệu partition/queue nên tạm dừng, chuyển toàn bộ aggregate sang quarantine, hay tiếp tục với một trạng thái degraded. Đây là quyết định nghiệp vụ, không chỉ là cấu hình retry.

## 26. Dead-letter record và dữ liệu nguồn gốc

Để điều tra và replay, cần lưu source identity:

- Broker type và cluster/environment.
- Queue/topic gốc.
- Kafka partition/offset hoặc JMS message ID/correlation ID.
- Consumer group/subscription nếu phù hợp.
- Event/business ID.
- Batch ID, JobExecution ID và StepExecution ID nếu được xử lý bởi Spring Batch.
- Payload type/schema version.
- Timestamp nhận và timestamp thất bại.
- Processing stage và error code.
- Delivery count/retry attempt.

Nếu chỉ lưu exception text, sau này khó tìm lại message nguồn hoặc xác định nó đã được xử lý chưa. Hãy chuẩn hóa metadata thành một envelope có version và tránh phụ thuộc vào tên header riêng của một provider trong domain model.

## 27. Dead-letter retention và vận hành

DLQ cần chính sách retention rõ ràng. Giữ mãi mọi message có thể làm tăng chi phí và rủi ro bảo mật; xóa quá sớm có thể làm mất dữ liệu cần điều tra hoặc replay.

Chính sách nên xác định:

- Thời gian lưu theo loại lỗi và dữ liệu.
- Ai được đọc, export, replay và purge.
- Mã hóa, masking và audit access.
- Ngưỡng cảnh báo theo số message và tuổi message cũ nhất.
- Quy trình triage và owner chịu trách nhiệm.
- SLA xử lý DLQ.
- Quy trình archive trước khi purge.
- Cách liên kết dead-letter record với incident/ticket.

Một DLQ có lượng message tăng liên tục là dấu hiệu lỗi hệ thống hoặc contract upstream, không phải trạng thái bình thường nên bỏ qua.

## 28. Quan sát dead-letter trong Spring Batch

Nên theo dõi số liệu theo Job/Step và theo broker:

- Tổng item đọc, process, write, filter và skip.
- Số dead-letter theo error code và payload type.
- Số lần retry trong Spring Batch.
- Broker delivery count/redelivery count.
- Số message publish thành công/thất bại vào DLQ.
- DLQ depth và oldest message age.
- Số message được redrive và kết quả replay.
- Số duplicate bị inbox/idempotency phát hiện.
- Batch ID, JobExecution ID, StepExecution ID và correlation ID.

Không ghi toàn bộ payload vào log. Ghi deadLetterId, originalMessageId, source, errorCode và correlation ID; payload được lưu trong nơi có kiểm soát truy cập.

## 29. Kiểm thử dead-letter flow

Unit test mock writer chỉ chứng minh code gọi đúng collaborator. Cần integration test với broker và database để xác nhận transaction, acknowledgement, redelivery và DLT publish.

Các trường hợp nên kiểm thử:

1. Message hợp lệ được xử lý bình thường và không vào DLQ.
2. Lỗi transient được retry rồi thành công.
3. Lỗi transient vượt retry limit và được dead-letter.
4. Lỗi permanent được chuyển thẳng đến quarantine/DLT theo chính sách.
5. Payload malformed vẫn được lưu raw payload và source metadata.
6. Lỗi trong `process()` được ghi nhận qua `onSkipInProcess`.
7. Lỗi trong `write()` được xử lý theo chính sách skip/dead-letter đã định.
8. Lỗi trong `read()` không làm mất raw message dù callback không có item.
9. Chunk rollback không làm mất dead-letter intent hoặc tạo duplicate ngoài kiểm soát.
10. DLQ publish thất bại không khiến source message bị ack mất.
11. Message redelivery được deduplicate bằng original message ID.
12. Replay giữ original ID và có replay metadata.
13. Replay theo aggregate/partition không phá ordering nghiệp vụ.
14. DLQ đầy, permission denied hoặc broker unavailable tạo alert và trạng thái có thể phục hồi.
15. Job restart không bỏ sót message giữa Batch checkpoint và broker offset.

Với Kafka, kiểm thử topic/partition/offset và `read_committed` nếu dùng producer transaction. Với JMS, kiểm thử rollback session, redelivery count và provider DLQ behavior. Không chỉ kiểm tra message đã xuất hiện ở DLQ; hãy xác nhận message nguồn được ack/commit đúng thời điểm.

## 30. Những nhầm lẫn thường gặp

**Cho rằng Spring Batch tự tạo DLQ khi skip item.** Skip chỉ bỏ item khỏi luồng Step; cần listener, outbox hoặc broker error handler để lưu dead-letter.

**Đưa mọi exception vào DLQ ngay lập tức.** Lỗi hạ tầng transient cần retry; lỗi dữ liệu cố định mới thường phù hợp với quarantine.

**Cho rằng broker DLQ và application quarantine là một cơ chế.** Chúng xảy ra ở các tầng khác nhau và cần quy tắc phối hợp.

**Acknowledge message nguồn trước khi DLQ được lưu.** Nếu publish DLQ thất bại, message có thể mất.

**Gửi trực tiếp DLQ từ SkipListener và giả định atomic với database.** Broker và database thường là hai local transaction; dùng outbox hoặc XA nếu cần atomicity.

**Cho rằng `onSkipInRead` cung cấp item lỗi.** Callback này chỉ nhận exception. Reader phải giữ raw payload/metadata hoặc để broker error handling xử lý.

**Cho rằng Kafka có một DLQ cố định do broker tự tạo.** DLT thường là topic do ứng dụng/platform tạo và error handler publish vào.

**Replay bằng message ID mới.** Điều đó có thể phá deduplication. Giữ original business/event ID và thêm replay ID riêng.

**Replay toàn bộ DLQ cùng lúc.** Có thể tạo tải đột biến và phá ordering. Chọn lọc, replay theo batch/aggregate và theo dõi tốc độ.

**Không theo dõi DLQ.** Message bị cách ly mà không có owner/SLA sẽ trở thành backlog lỗi lâu dài.

## 31. Cách thiết kế dead-letter flow

Trước hết, xác định lỗi nào transient, lỗi nào permanent và business rejection nào là kết quả nghiệp vụ hợp lệ. Đặt retry limit, backoff và timeout rõ ràng. Chỉ dead-letter khi lỗi không thể phục hồi theo chính sách hoặc khi broker delivery đã vượt ngưỡng.

Nếu broker tự quản lý redelivery, cấu hình DLQ ở broker/listener container và kiểm tra acknowledgement semantics. Nếu Spring Batch đã đọc được item rồi processor phát hiện lỗi, dùng skip policy kết hợp `SkipListener` hoặc quarantine writer. Với lỗi parse trong `read()`, giữ raw payload và source metadata trước khi deserialize vì `onSkipInRead` không có item để lưu.

Khi database và broker là hai local transaction, ghi dead-letter intent vào outbox cùng transaction database rồi publisher gửi sang DLQ. Giữ original message ID, source topic/queue/partition/offset, payload type, schema version, error code và retry metadata. Chỉ acknowledge source khi dead-letter record đã bền vững theo mô hình đã chọn.

Xây dựng quy trình redrive có kiểm soát: sửa nguyên nhân, chọn message, kiểm tra trạng thái side effect, giữ original ID, thêm replay metadata, replay theo tốc độ và thứ tự an toàn. Bảo vệ DLQ bằng ACL, encryption, retention và audit. Kiểm thử crash giữa persist, publish, ack, rollback và restart. Dead-letter flow tốt giúp message lỗi không chặn pipeline, đồng thời giữ khả năng điều tra và xử lý lại mà không làm mất hoặc nhân đôi hiệu ứng nghiệp vụ.
