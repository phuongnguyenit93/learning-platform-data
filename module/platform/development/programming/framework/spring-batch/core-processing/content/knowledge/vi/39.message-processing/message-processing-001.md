# ItemReader đọc message từ queue

Trong Spring Batch, một `ItemReader<T>` có thể lấy từng message từ một message queue để đưa vào chunk processing. Reader nhận message, chuyển payload thành object Java rồi trả về cho Processor và Writer. Các hệ thống thường gặp gồm JMS queue, RabbitMQ qua AMQP và các nền tảng message khác.

Điểm khó của queue reader là message có thể bị broker đánh dấu đã nhận hoặc xóa khỏi queue trước khi chunk database commit. Nếu Writer thất bại sau khi message đã bị acknowledge, dữ liệu có thể bị mất. Ngược lại, nếu message được giao lại sau rollback hoặc timeout, Writer có thể nhận cùng message nhiều lần. Vì vậy, phải thiết kế đồng thời cách xác định ranh giới batch, acknowledgement, transaction, idempotency và restart.

## 1. ItemReader và message queue

`ItemReader<T>` là abstraction đọc một item mỗi lần gọi `read()`:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}
```

Reader trả về một item khi có dữ liệu. Khi không còn item trong input của lần chạy, Reader trả về `null`; Spring Batch hiểu đó là end-of-input và kết thúc việc đọc của Step.

Với file hoặc database query có phạm vi xác định, end-of-input thường rõ ràng. Với queue đang hoạt động liên tục, queue rỗng tại một thời điểm chưa chắc có nghĩa là không còn message. Một message mới có thể đến ngay sau đó. Do vậy, Reader đọc queue cần một quy tắc xác định batch kết thúc, chẳng hạn số message đã đăng ký, end marker, watermark hoặc một khoảng thời gian nhận dữ liệu được giới hạn theo nghiệp vụ.

## 2. Pull reader và message listener

Có hai cách phổ biến để nhận message:

| Cách | Cơ chế | Đặc điểm |
|---|---|---|
| Pull | Reader chủ động gọi receive/poll từ broker | Phù hợp khi Step điều khiển nhịp đọc và xử lý chunk. |
| Push/listener | Broker/container gọi listener khi có message | Phù hợp với consumer chạy liên tục; có thể chuyển message vào channel hoặc inbox. |

Trong mô hình pull, `ItemReader.read()` chờ message rồi trả payload cho Spring Batch. Chunk size xác định số item tối đa được gom trước khi Writer chạy.

Trong mô hình listener, listener nhận message bên ngoài vòng `read()` của Step. Có thể đưa message vào `BlockingQueue` hoặc Spring Integration channel để một Reader lấy ra, nhưng cần quản lý backpressure, acknowledgement và shutdown. Nếu listener đã ack message ngay khi nhận rồi chỉ đặt payload vào memory queue, lỗi của Step có thể làm mất message khi process dừng.

Một consumer queue chạy vô hạn thường phù hợp với message-driven service hơn một Job Spring Batch duy nhất. Spring Batch phù hợp khi muốn xử lý một lô hữu hạn, có trạng thái Job/Step, checkpoint, báo cáo và khả năng restart.

## 3. Xác định ranh giới của một batch

Queue thường không có điểm kết thúc tự nhiên. `read()` trả `null` là tín hiệu kết thúc input của Step, không phải tín hiệu “hiện tại queue đang trống”. Nếu Reader dùng receive timeout ngắn rồi trả `null`, Step có thể kết thúc dù producer sắp gửi thêm message.

Các cách xác định phạm vi batch:

| Cách | Ý nghĩa | Lưu ý |
|---|---|---|
| `maxMessages` | Xử lý tối đa N message | Dễ kiểm soát; phải xử lý trường hợp timeout trước khi đủ N message. |
| End marker | Producer gửi message kết thúc lô | Cần batch ID và xử lý marker đúng một lần. |
| Watermark/sequence | Xử lý đến sequence hoặc offset đã chốt | Phù hợp khi nguồn có thứ tự và watermark đáng tin cậy. |
| Cutoff time | Xử lý message thuộc khoảng thời gian xác định | Cần quy tắc cho message đến trễ. |
| Inactivity timeout | Kết thúc khi không có message trong một khoảng | Chỉ dùng khi nghiệp vụ chấp nhận cửa sổ yên lặng là kết thúc. |

Nếu queue rỗng tạm thời nhưng batch chưa kết thúc, Reader nên tiếp tục chờ hoặc báo lỗi timeout theo chính sách. Không trả `null` chỉ vì một lần poll không có message, trừ khi timeout đó chính là ranh giới batch đã được định nghĩa.

## 4. Ví dụ pull reader có giới hạn số message

Ví dụ sau minh họa một Reader đơn giản dùng `JmsTemplate` để nhận payload từ JMS queue. `maxMessages` xác định số message thuộc batch. Nếu queue không cung cấp đủ message trong thời gian chờ, Reader ném exception thay vì trả `null` và kết thúc Job âm thầm.

```java
import org.springframework.batch.item.ItemReader;
import org.springframework.jms.core.JmsTemplate;

public class BoundedJmsItemReader<T> implements ItemReader<T> {

    private final JmsTemplate jmsTemplate;
    private final String queueName;
    private final long maxMessages;
    private long readCount;

    public BoundedJmsItemReader(
            JmsTemplate jmsTemplate,
            String queueName,
            long maxMessages) {
        this.jmsTemplate = jmsTemplate;
        this.queueName = queueName;
        this.maxMessages = maxMessages;
    }

    @Override
    @SuppressWarnings("unchecked")
    public T read() {
        if (readCount >= maxMessages) {
            return null;
        }

        Object payload = jmsTemplate.receiveAndConvert(queueName);
        if (payload == null) {
            throw new IllegalStateException(
                    "Queue did not provide the expected message count");
        }

        readCount++;
        return (T) payload;
    }
}
```

Thời gian chờ được cấu hình trên `JmsTemplate` (ví dụ `setReceiveTimeout(...)`). Nếu receive timeout được bật, Reader có thể nhận `null` khi hết thời gian chờ; đoạn code chuyển trường hợp đó thành exception vì batch vẫn đang chờ đủ `maxMessages`. Nếu không cấu hình timeout, thao tác receive có thể chờ vô hạn và cần được cân nhắc khi graceful stop.

Đây là ví dụ minh họa cách pull và giới hạn input; nó chưa phải implementation production có checkpoint và acknowledgement an toàn. `readCount` trong memory mất khi restart, và `receiveAndConvert()` có thể acknowledge message theo session/acknowledgement mode của JMS. Không được dùng đoạn code này như bảo đảm message sẽ được giao lại nếu chunk thất bại.

Trong ứng dụng thật, cần bổ sung `ItemStreamReader` nếu phải lưu state, chọn transaction/acknowledgement mode phù hợp và kiểm thử tình huống Writer lỗi sau khi Reader đã nhận message. Phần acknowledgement bên dưới giải thích vì sao chỉ lưu `readCount` không đủ.

## 5. Khai báo Reader bằng @StepScope và JobParameters

Tên queue, số message cần đọc hoặc batch ID thường được truyền khi launch Job. Có thể late-bind chúng bằng `@StepScope`:

```java
@Bean
@StepScope
public ItemReader<OrderMessage> orderQueueReader(
        JmsTemplate jmsTemplate,
        @Value("#{jobParameters['queueName']}") String queueName,
        @Value("#{jobParameters['maxMessages']}") Long maxMessages) {

    if (queueName == null || queueName.isBlank()) {
        throw new IllegalArgumentException("queueName is required");
    }
    if (maxMessages == null || maxMessages <= 0) {
        throw new IllegalArgumentException("maxMessages must be positive");
    }

    return new BoundedJmsItemReader<>(jmsTemplate, queueName, maxMessages);
}
```

JobParameters:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("queueName", "orders.queue", true)
        .addLong("maxMessages", 500L, true)
        .addString("batchId", "orders-2026-11-15-01", true)
        .toJobParameters();
```

`@StepScope` tạo Reader target cho StepExecution hiện tại. Các identifying parameters giúp xác định cùng JobInstance khi restart. Tuy nhiên, `maxMessages` chỉ xác định số lượng dự kiến; nó không chứng minh broker sẽ giao lại đúng các message cũ sau khi process dừng.

## 6. Acknowledgement là phần quan trọng nhất

Khi consumer nhận message, broker cần biết message đã được xử lý thành công hay cần giao lại. Tùy công nghệ, thao tác đó có tên acknowledgement, commit offset hoặc delete/complete receipt. Thời điểm xác nhận quyết định nguy cơ mất hoặc xử lý trùng message.

Hai thời điểm cần phân biệt:

- **Ack khi nhận:** message được xác nhận ngay sau khi Reader lấy payload. Nếu Writer hoặc transaction database thất bại sau đó, broker có thể không giao lại message.
- **Ack sau commit:** message chỉ được xác nhận sau khi chunk đã commit thành công. Nếu chunk rollback, message có thể được giao lại.

Với xử lý nghiệp vụ quan trọng, ack trước khi dữ liệu đích commit tạo ra nguy cơ mất message. Ack sau commit tạo ra mô hình at-least-once: message có thể được giao lại nếu process dừng sau khi database commit nhưng trước khi ack hoàn tất. Vì vậy, Writer vẫn cần idempotent.

```text
Ack quá sớm:
  receive -> ACK -> ghi database -> lỗi
                           |
                           +--> message đã bị loại khỏi queue
                                nhưng business data chưa commit

Ack sau commit:
  receive -> ghi database -> COMMIT -> ACK
                 |
                 +--> rollback: không ACK, broker có thể giao lại
```

Không có một acknowledgement mode chung cho mọi broker. Phải đọc đúng semantics của JMS provider, RabbitMQ/AMQP, Kafka hoặc dịch vụ queue đang dùng.

## 7. JMS acknowledgement và transaction

JMS có các acknowledgement mode phổ biến như `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE` và transacted session. Với `AUTO_ACKNOWLEDGE`, message có thể được xác nhận khi receive hoàn tất theo semantics của JMS provider và API được dùng. Điều đó có thể xảy ra trước khi chunk Writer commit.

Một JMS transacted session có thể rollback receive để broker giao lại message khi transaction JMS rollback. Nhưng nếu Step đồng thời ghi vào database qua một transaction manager JDBC/JPA độc lập, transaction JMS và database không tự động atomic với nhau.

Các lựa chọn:

1. Dùng JTA/XA với XA JMS ConnectionFactory và XA database resource nếu cần receive và business write cùng commit/rollback nguyên tử.
2. Dùng acknowledgement thủ công sau khi business transaction commit, kết hợp idempotency để xử lý redelivery nếu ack bị lỗi.
3. Nhận message vào inbox database bền vững trước, sau đó để Spring Batch đọc inbox bằng JDBC/JPA Reader.

`JmsTransactionManager` quản lý local transaction cho JMS resource. Nó không tự điều phối transaction của một database khác. Không dùng một local JMS transaction manager và một local JPA transaction manager rồi giả định cả hai sẽ commit cùng nhau.

## 8. AMQP/RabbitMQ acknowledgement

Với AMQP broker như RabbitMQ, consumer có thể dùng auto acknowledgement hoặc manual acknowledgement. Trong manual ack, ứng dụng xác nhận delivery sau khi xử lý thành công; nếu không ack và channel/connection đóng hoặc message bị reject/requeue theo cấu hình, broker có thể giao lại message.

Các điểm cần hiểu:

- Delivery tag là định danh delivery trong channel, không phải business ID bền vững.
- Ack phải được gửi trên channel liên quan đến delivery.
- `basicAck` xác nhận message; `basicNack`/reject có thể requeue hoặc đưa vào dead-letter flow tùy cấu hình.
- Prefetch giới hạn số message broker giao trước cho consumer và ảnh hưởng memory/backpressure.
- Auto ack có thể làm message biến mất khỏi queue trước khi chunk commit.

Nếu dùng listener container, cần cấu hình acknowledgement mode và transaction phù hợp. Với Spring AMQP, tên mode thường được thể hiện qua `AcknowledgeMode`; semantics chi tiết phụ thuộc container và cấu hình channel transaction. Không nên lấy delivery tag rồi ack trên một channel khác hoặc thread khác.

## 9. Ack sau chunk commit

Một mô hình manual-ack có thể giữ lại thông tin delivery trong phạm vi chunk rồi xác nhận các message sau khi transaction nghiệp vụ commit. Nếu chunk rollback, không ack; message được requeue/redeliver theo broker configuration.

```text
Chunk bắt đầu
    |
    v
Reader nhận message (manual ack)
    |
    v
Processor / Writer
    |
    +--> lỗi -> rollback -> không ACK / requeue
    |
    v
Business transaction COMMIT
    |
    v
Chunk after-commit hook
    |
    v
ACK các delivery thuộc chunk
```

Đây là mô hình khái niệm. Implementation cần giữ đúng delivery handle/channel, gom chính xác message thuộc chunk và chỉ ack sau commit. Với RabbitMQ, acknowledgement phải dùng đúng channel của delivery. Với JMS, dùng session transaction hoặc acknowledgement API đúng semantics của provider.

Ngay cả khi ack sau commit, vẫn có một cửa sổ nhỏ: database đã commit nhưng ứng dụng dừng trước khi broker nhận ack. Broker có thể giao lại message. Unique constraint hoặc inbox/idempotency key giúp lần xử lý lại không tạo hiệu ứng nghiệp vụ trùng.

## 10. Vì sao một count checkpoint không đủ cho queue?

Với file reader, checkpoint có thể lưu vị trí byte hoặc record trong resource bất biến. Với database paging reader, checkpoint có thể lưu key hoặc vị trí trang. Queue destructive receive khác ở chỗ message có thể đã bị broker loại khỏi trạng thái sẵn sàng ngay khi được nhận.

Nếu Reader chỉ lưu `readCount = 100` trong `ExecutionContext`, khi restart con số đó không làm broker gửi lại 100 message đã ack. Nó cũng không xác định được message nào đã commit và message nào mới chỉ được nhận.

Một checkpoint queue đáng tin cậy cần gắn với định danh message hoặc offset/sequence bền vững và semantics redelivery của broker. Ví dụ:

- JMS/AMQP: message ID hoặc application event ID cùng acknowledgement transaction.
- Kafka: topic, partition và offset; offset commit phải được điều phối với business write.
- Inbox database: message ID được lưu cùng trạng thái xử lý trong database.

Không dùng delivery tag, vị trí trong memory queue hoặc số lần `read()` làm business checkpoint bền vững.

## 11. Inbox pattern: đưa queue vào database trước khi batch xử lý

Một pattern dễ kiểm soát là consumer nhận message và lưu vào bảng inbox trước. Sau đó Spring Batch dùng `JdbcPagingItemReader` hoặc `JdbcCursorItemReader` đọc các dòng chưa xử lý. Broker acknowledgement diễn ra sau khi inbox insert đã bền vững; batch xử lý inbox bằng transaction database.

```text
Message broker
      |
      v
Queue consumer
      |
      v
INSERT inbox_message (message_id, payload, status)
      |
      +--> UNIQUE(message_id) chống nhận lặp
      |
      v
ACK broker sau khi inbox commit
      |
      v
Spring Batch JdbcPagingItemReader
      |
      v
Processor / Writer
      |
      v
UPDATE inbox_message SET status = 'PROCESSED'
```

Schema minh họa:

```sql
CREATE TABLE inbox_message (
    message_id VARCHAR(160) PRIMARY KEY,
    message_type VARCHAR(80) NOT NULL,
    payload JSON NOT NULL,
    status VARCHAR(20) NOT NULL,
    received_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP NULL
);
```

Unique key ngăn cùng message được insert nhiều lần nếu broker redeliver sau khi database đã commit nhưng ack chưa đến broker. Spring Batch chỉ đọc các message có `status = 'NEW'` theo thứ tự ổn định. Writer cập nhật dữ liệu nghiệp vụ và trạng thái inbox trong cùng database transaction nếu cả hai nằm trong cùng database.

Inbox pattern tách việc nhận message khỏi xử lý batch. Nó tạo một điểm lưu bền vững có thể restart, tra cứu và kiểm thử dễ hơn so với giữ message chưa ack trong memory của một Reader.

## 12. Ví dụ Reader đọc message từ inbox table

Khi message đã được lưu bền vững vào inbox, Reader của Spring Batch có thể dùng JDBC paging:

```java
@Bean
public JdbcPagingItemReader<InboxMessage> inboxReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider) {

    return new JdbcPagingItemReaderBuilder<InboxMessage>()
            .name("inboxReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .parameterValues(Map.of("status", "NEW"))
            .rowMapper(new BeanPropertyRowMapper<>(InboxMessage.class))
            .pageSize(200)
            .saveState(true)
            .build();
}
```

Query provider cần select các cột cần thiết từ `inbox_message`, lọc theo status và sắp xếp bằng khóa ổn định, duy nhất như `message_id` hoặc sequence tăng dần. Cú pháp `PagingQueryProvider` và cách tạo provider phụ thuộc database; ví dụ trên minh họa cách gắn Reader với nguồn inbox.

Writer nên cập nhật business data và `inbox_message.status` trong cùng transaction:

```java
UPDATE inbox_message
SET status = 'PROCESSED', processed_at = CURRENT_TIMESTAMP
WHERE message_id = :messageId AND status = 'NEW'
```

Trong hệ thống có nhiều worker, cần claim message an toàn để hai Step không cùng xử lý một dòng. Có thể dùng trạng thái `PROCESSING`, lease/lock, `SELECT ... FOR UPDATE SKIP LOCKED` nếu database hỗ trợ, hoặc chia partition không chồng lấn. Việc claim và cập nhật trạng thái phải có transaction và timeout rõ ràng.

## 13. Message ID, correlation ID và idempotency key

Một message thường có nhiều loại định danh:

| Định danh | Mục đích |
|---|---|
| Message ID | Nhận diện message cụ thể trong broker hoặc application. |
| Business key | Nhận diện đối tượng nghiệp vụ, ví dụ `orderId`. |
| Correlation ID | Liên kết nhiều message thuộc cùng một request hoặc workflow. |
| Batch ID | Gom message vào một đợt xử lý. |
| Delivery tag/receipt handle | Nhận diện lần giao cụ thể để ack/delete; thường không bền vững qua redelivery. |

Để chống trùng, ưu tiên application message ID hoặc event ID ổn định do producer tạo. Không dùng correlation ID làm idempotency key nếu một correlation có thể chứa nhiều message khác nhau.

Nếu producer có thể gửi lại cùng event với message ID mới, cần thêm business key/version để nhận diện cùng thao tác nghiệp vụ. Nếu hai event cùng order ID nhưng là hai cập nhật hợp lệ, cần có event ID hoặc version để không loại nhầm sự kiện mới.

## 14. Queue và delivery semantics

Các broker thường cung cấp một trong các kiểu giao nhận sau:

| Semantics | Ý nghĩa | Tác động tới batch |
|---|---|---|
| At-most-once | Message được giao tối đa một lần; có thể mất khi lỗi | Không phù hợp nếu không chấp nhận mất dữ liệu. |
| At-least-once | Message có thể được giao lại cho đến khi ack/commit | Writer phải idempotent và deduplicate. |
| Exactly-once (phạm vi broker cụ thể) | Broker bảo đảm một số thao tác trong phạm vi được hỗ trợ | Không tự động bao gồm database và mọi side effect bên ngoài. |

Không nên quảng bá toàn bộ Job là exactly-once chỉ vì broker hỗ trợ một chế độ exactly-once trong phạm vi riêng. Nếu database commit và broker acknowledgement không nằm trong cùng transaction coordinator, vẫn có cửa sổ replay hoặc mất dữ liệu.

Trong thực tế, at-least-once kết hợp business key, unique constraint, inbox/outbox và idempotent Writer thường dễ vận hành hơn việc cố tạo một transaction phân tán cho mọi resource.

## 15. Poison message, retry và dead-letter queue

Poison message là message luôn thất bại vì payload sai, schema không hỗ trợ hoặc lỗi nghiệp vụ không thể tự hết. Nếu broker cứ redeliver message này, consumer có thể bị kẹt ở một message và không xử lý được các message sau, tùy ordering và queue configuration.

Các biện pháp:

- Phân loại lỗi tạm thời và lỗi không thể phục hồi.
- Retry lỗi tạm thời với giới hạn và backoff.
- Sau số lần thất bại tối đa, reject/dead-letter message theo chính sách broker.
- Lưu message ID, payload reference, exception và attempt count để điều tra.
- Có quy trình sửa dữ liệu và replay message từ DLQ.

Không retry vô hạn một lỗi parse JSON hoặc thiếu field bắt buộc. Cũng không nên ack message lỗi rồi bỏ đi nếu nghiệp vụ yêu cầu lưu dấu vết. DLQ hoặc reject table giúp giữ message để xử lý sau.

Khi dùng Spring Batch, skip policy có thể xử lý lỗi ở item đã được Reader trả về. Nhưng nếu message bị broker redeliver hoặc ack không thành công, lần giao lại vẫn cần được nhận diện qua message ID. Skip không thay thế DLQ hoặc broker retry policy.

## 16. Backpressure, prefetch và chunk size

Queue có thể giao message nhanh hơn khả năng Writer xử lý. Cần điều chỉnh prefetch, số consumer, concurrency và chunk size để không tích lũy quá nhiều message trong memory hoặc giữ message unacked quá lâu.

| Tham số | Ảnh hưởng |
|---|---|
| Chunk size | Số item được gom trước khi Writer và commit. |
| Prefetch | Số message broker có thể giao trước cho consumer chưa ack. |
| Consumer concurrency | Số luồng/consumer nhận message đồng thời. |
| Receive timeout | Thời gian chờ message; không được nhầm với end-of-input nếu queue còn mở. |
| Transaction timeout | Giới hạn thời gian giữ transaction/lock khi xử lý chunk. |

Chunk quá lớn có thể giữ nhiều message chưa ack, tăng thời gian rollback và memory. Chunk quá nhỏ tăng overhead commit/metadata và số lần gọi Writer. Hãy đo throughput, latency, redelivery, queue depth, unacked count và thời gian transaction khi điều chỉnh.

Nếu thứ tự message có ý nghĩa nghiệp vụ, tăng concurrency hoặc prefetch có thể làm thứ tự hoàn tất khác thứ tự nhận. Cần dùng partition/group key hoặc xử lý tuần tự theo từng aggregate nếu phải giữ ordering.

## 17. Graceful stop và shutdown

Khi Job được yêu cầu dừng, Reader không nên giữ message vô hạn trong memory hoặc acknowledge những message chưa được xử lý thành công. Cần quy định cách xử lý message đang nhận:

- Message thuộc chunk đã commit: ack theo cơ chế đã chọn.
- Message thuộc chunk chưa commit: rollback và để broker redeliver/requeue hoặc giữ trong inbox ở trạng thái chưa xử lý.
- Message đã nhận nhưng chưa đưa vào chunk: không ack; giải phóng/requeue theo broker semantics.
- Listener/container đang chạy: dừng nhận message mới theo thứ tự shutdown đã định nghĩa.

Với pull reader, cần có receive timeout hữu hạn để Job có thể kiểm tra tín hiệu dừng, nhưng timeout không được tự động coi là EOF nếu batch chưa đạt điều kiện kết thúc. Có thể ném exception timeout/retry hoặc tiếp tục poll theo deadline của batch.

Không ack toàn bộ message đang giữ chỉ để shutdown nhanh. Làm vậy có thể biến các message chưa xử lý thành message đã mất khỏi queue.

## 18. Kafka khác với queue destructive receive

Kafka thường được dùng cho message processing nhưng bản chất là distributed log có topic, partition và offset. Consumer đọc record theo offset; commit offset là checkpoint của consumer group. Message không bị xóa khỏi log ngay khi một consumer đọc.

| Queue kiểu JMS/AMQP | Kafka |
|---|---|
| Consumer nhận và ack/requeue message | Consumer đọc record và commit offset. |
| Redelivery phụ thuộc ack và broker queue state | Replay phụ thuộc offset và retention. |
| Message thường được phân phối cho một consumer trong queue group | Record được phân phối theo partition trong consumer group. |
| Delivery tag/session là chi tiết của lần giao | Topic/partition/offset là vị trí log. |

Nếu dùng Kafka với Spring Batch, cần phối hợp offset commit với business transaction. Commit offset trước database commit có thể làm mất xử lý; database commit trước offset commit có thể dẫn đến replay. Idempotent Writer hoặc inbox/deduplication vẫn cần thiết trừ khi toàn bộ transaction được điều phối trong phạm vi hỗ trợ.

## 19. Kiểm thử queue ItemReader

Kiểm thử cần bao phủ cả luồng đọc và acknowledgement, không chỉ xác nhận Reader trả đúng payload.

Các kịch bản quan trọng:

1. **Message có sẵn:** Reader trả payload theo thứ tự và đúng kiểu.
2. **Queue tạm thời rỗng:** Reader không trả `null` sớm nếu batch chưa kết thúc.
3. **Đạt batch boundary:** Reader trả `null` đúng khi đã đọc đủ số message hoặc nhận end marker hợp lệ.
4. **Writer thất bại:** message chưa được ack và có thể redeliver, hoặc inbox record vẫn ở trạng thái chưa xử lý.
5. **DB commit thành công, ack thất bại:** message redeliver nhưng Writer idempotent không tạo hiệu ứng trùng.
6. **Restart Job:** cùng JobInstance tiếp tục từ trạng thái bền vững, không dựa vào counter trong memory.
7. **Poison message:** retry có giới hạn và đưa message vào DLQ/reject flow.
8. **Shutdown:** message chưa commit không bị ack nhầm.
9. **Concurrency:** nhiều consumer không xử lý trùng business key ngoài chính sách đã định.
10. **Ordering:** xác nhận thứ tự đầu ra nếu nghiệp vụ yêu cầu tuần tự.

Với broker thật, integration test có thể dùng Testcontainers hoặc broker test instance cùng loại. Mock `JmsTemplate`/`AmqpTemplate` hữu ích cho unit test cách Reader chuyển đổi payload, nhưng không chứng minh được acknowledgement, redelivery, transaction và DLQ semantics của broker.

## 20. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Trả `null` khi queue tạm thời rỗng | Spring Batch coi input đã kết thúc và Step dừng sớm. | Xác định batch boundary; tiếp tục chờ hoặc báo timeout. |
| Auto-ack ngay khi Reader nhận | Writer lỗi sau đó nhưng message đã bị loại khỏi queue. | Manual ack sau commit, XA hoặc inbox pattern. |
| Chỉ lưu số lần read trong ExecutionContext | Broker không tự giao lại message đã ack. | Lưu message ID/offset bền vững và phối hợp acknowledgement. |
| Ack trước database commit | Có thể mất message khi transaction database rollback. | Ack sau commit hoặc dùng transaction coordinator. |
| DB commit rồi ack thất bại | Broker redeliver và Writer có thể chạy lại. | Idempotency key, unique constraint hoặc inbox deduplication. |
| Dùng delivery tag làm business key | Tag có thể thay đổi theo channel/redelivery. | Dùng application message ID hoặc event ID ổn định. |
| Retry poison message vô hạn | Consumer bị kẹt và queue backlog tăng. | Giới hạn retry, backoff và DLQ. |
| Listener ack rồi đẩy vào memory queue | Process crash làm mất message chưa xử lý. | Persist vào inbox trước khi ack hoặc trì hoãn ack đúng cách. |
| Nhiều local transaction manager nhưng kỳ vọng atomic | JMS/AMQP và database có thể commit lệch nhau. | JTA/XA hoặc eventual consistency với outbox/inbox. |
| Prefetch/chunk quá lớn | Nhiều message unacked, memory cao và rollback tốn kém. | Đo tải và điều chỉnh concurrency, prefetch, chunk size. |

## Kết luận

`ItemReader` có thể pull message từ queue và đưa payload vào chunk processing, nhưng queue khác file/database ở semantics acknowledgement và end-of-input. Queue rỗng tạm thời không đồng nghĩa Reader nên trả `null`; cần ranh giới batch như số message, end marker hoặc watermark. Không ack message trước khi dữ liệu nghiệp vụ được bảo đảm, và không giả định transaction JMS/AMQP tự atomic với transaction database. Với xử lý quan trọng, dùng ack sau commit kết hợp idempotency, JTA/XA khi cần atomicity, hoặc inbox pattern để lưu message bền vững rồi cho Spring Batch đọc bằng JDBC/JPA Reader. Kiểm thử redelivery, rollback, restart, poison message và shutdown trên đúng broker để bảo đảm không mất hoặc nhân đôi hiệu ứng nghiệp vụ.
