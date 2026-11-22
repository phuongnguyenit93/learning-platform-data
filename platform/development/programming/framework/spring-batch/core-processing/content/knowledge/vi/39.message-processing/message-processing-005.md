# Redelivery và duplicate item trong Spring Batch

Khi một Job xử lý message từ queue hoặc broker, cùng một message có thể được giao nhiều lần. Việc giao lại được gọi là **redelivery**. Nếu ứng dụng đã xử lý message nhưng chưa xác nhận với broker, hoặc process bị dừng trước khi acknowledgment được ghi nhận, broker có thể giao message đó lại. Một tình huống tương tự xảy ra khi chunk đã thực hiện một phần side effect nhưng transaction rollback hoặc Job restart khiến item được xử lý lại.

Vì vậy, một pipeline message thường phải chấp nhận khả năng **at-least-once delivery**: một message hợp lệ sẽ được giao ít nhất một lần, nhưng có thể xuất hiện nhiều lần. Ứng dụng cần phát hiện hoặc xử lý an toàn các lần xuất hiện trùng. Đây là nền tảng của thiết kế **idempotent processing**.

Spring Batch cung cấp chunk transaction, retry, skip, ExecutionContext và JobRepository để điều phối việc xử lý. Tuy nhiên, các cơ chế đó không tự làm cho message broker và database trở thành một transaction duy nhất. Cần hiểu thời điểm message được acknowledge, thời điểm chunk commit, cách broker redeliver, và cách writer ngăn một business event được áp dụng nhiều lần.

Bài học này giải thích nguyên nhân redelivery, phân biệt retry với redelivery, cách nhận diện duplicate item, các mẫu idempotency và inbox/outbox, phối hợp acknowledgment với transaction, xử lý poison message và dead-letter queue, cùng cách kiểm thử pipeline message trong Spring Batch.

## 1. Redelivery và duplicate item là gì?

**Redelivery** xảy ra khi broker giao lại một message mà consumer đã nhận trước đó nhưng broker chưa ghi nhận hoàn tất theo giao thức. Message được giao lại có thể giữ nguyên message ID hoặc delivery metadata thay đổi tùy broker.

**Duplicate item** là một item đại diện cho cùng một sự kiện hoặc cùng một tác vụ nghiệp vụ xuất hiện nhiều hơn một lần trong pipeline. Duplicate có thể xuất hiện do redelivery, retry, restart, producer gửi lặp, hoặc hai consumer cùng xử lý một sự kiện.

Ví dụ một message yêu cầu ghi nhận thanh toán:

~~~json
{
  "eventId": "evt-9001",
  "paymentId": "pay-123",
  "eventType": "PAYMENT_CAPTURED",
  "amount": 250.00
}
~~~

Consumer nhận message, cập nhật database, nhưng process bị dừng trước khi acknowledgment đến broker. Broker không biết việc cập nhật đã hoàn tất và giao message lại. Nếu consumer cập nhật số dư thêm lần nữa, cùng một payment có thể bị áp dụng hai lần.

Redelivery là hành vi của hệ thống giao nhận. Duplicate là vấn đề của luồng nghiệp vụ khi một sự kiện được xử lý nhiều lần mà không có kiểm soát.

## 2. Vì sao broker redeliver message?

Broker thường chỉ xóa message khỏi trạng thái chờ xử lý khi nhận được acknowledgment hoặc khi transaction chứa việc nhận message được commit. Nếu broker không nhận được xác nhận, message có thể quay lại hàng đợi.

Các nguyên nhân phổ biến:

- Consumer process crash sau khi nhận message.
- Container hoặc máy chủ bị restart trước khi acknowledge.
- Consumer mất kết nối với broker.
- Message visibility timeout hết hạn khi xử lý lâu hơn thời gian lease.
- Consumer gọi negative acknowledgment hoặc rollback transaction.
- Listener ném exception và container được cấu hình redelivery.
- Broker không nhận được acknowledgment do network partition.
- Consumer xử lý xong nhưng acknowledgment bị mất trên đường truyền.
- Consumer bị dừng khi đang xử lý chunk.
- Message được publish nhiều lần bởi producer do producer retry.

Một số broker dùng acknowledgment thủ công; một số dùng transaction; một số dùng visibility timeout và receipt handle. Chi tiết redelivery phụ thuộc broker, client và cấu hình consumer. Không nên giả định mọi broker có cùng semantics.

### Redelivery không nhất thiết là lỗi

Redelivery là cơ chế giúp message không bị mất khi consumer chưa xác nhận thành công. Nó là một phần bình thường của hệ thống at-least-once.

Điều cần kiểm soát là side effect nghiệp vụ. Nếu xử lý cùng event lần thứ hai không làm thay đổi kết quả đã đạt được, redelivery có thể được chấp nhận an toàn.

## 3. At-most-once, at-least-once và exactly-once

Ba thuật ngữ thường mô tả semantics giao nhận:

| Semantics | Ý nghĩa | Rủi ro chính |
|---|---|---|
| At-most-once | Message được giao tối đa một lần | Có thể mất message |
| At-least-once | Message được giao một hoặc nhiều lần | Có thể có duplicate |
| Exactly-once | Hiệu ứng nghiệp vụ chỉ được áp dụng một lần theo một phạm vi được xác định | Cần phối hợp transaction, deduplication và hệ thống đích |

At-most-once có thể đạt được bằng cách acknowledge sớm, nhưng nếu consumer crash sau ack và trước khi xử lý thì message mất.

At-least-once thường an toàn hơn cho dữ liệu quan trọng vì message chưa được xác nhận có thể được giao lại. Đổi lại, consumer phải idempotent.

Exactly-once thường bị hiểu quá rộng. Một broker có thể bảo đảm exactly-once trong phạm vi một transaction hoặc một luồng nội bộ, nhưng điều đó không tự mở rộng sang database, HTTP API, file system hoặc hệ thống thanh toán bên ngoài. Hãy xác định chính xác “once” áp dụng cho message delivery, broker log hay business side effect.

Một thiết kế thực tế thường dùng at-least-once delivery kết hợp với deduplication bền vững để đạt hiệu ứng nghiệp vụ effectively-once trong phạm vi database mà ứng dụng kiểm soát.

## 4. Phân biệt retry và redelivery

Retry và redelivery đều có thể khiến cùng một item được xử lý lại, nhưng chúng xảy ra ở các tầng khác nhau.

- **Retry:** application hoặc Spring Batch gọi lại một thao tác sau lỗi được xem là có thể phục hồi.
- **Redelivery:** broker giao message lại cho consumer vì message chưa được xác nhận hoàn tất.
- **Restart:** Spring Batch tạo execution mới cho cùng JobInstance và tiếp tục từ checkpoint đã lưu.
- **Duplicate publish:** producer gửi cùng business event nhiều lần, thường do retry hoặc thiếu idempotency ở phía gửi.

| Cơ chế | Ai khởi động? | Phạm vi |
|---|---|---|
| Spring Retry trong Step | Spring Batch | Gọi lại operation theo retry policy |
| Broker redelivery | Message broker | Giao lại message chưa được acknowledge |
| Job restart | JobOperator/JobLauncher | Tiếp tục Job từ metadata và checkpoint |
| Producer retry | Producer/client | Có thể publish lại cùng event |

Ví dụ một writer gọi API thanh toán và nhận timeout. Spring Batch retry write. API có thể đã xử lý request trước khi timeout, vì vậy lần gọi lại có thể tạo side effect trùng nếu API không nhận idempotency key.

Một trường hợp khác: consumer đọc message, xử lý xong nhưng broker chưa nhận ack. Broker redeliver message khi consumer khác nhận. Đây không phải Spring Batch retry; nó là một lần giao mới từ broker.

Cần quan sát attempt của ứng dụng và delivery count của broker riêng biệt.

## 5. Duplicate có thể xuất hiện ở những điểm nào?

Một pipeline message có nhiều ranh giới có thể tạo duplicate:

~~~mermaid
flowchart LR
    A["Producer"] --> B["Broker"]
    B --> C["Consumer / ItemReader"]
    C --> D["Processor"]
    D --> E["Writer / Database"]
    E --> F["Commit"]
    F --> G["Acknowledge"]
    G --> H["Broker removes message"]
~~~

Các cửa sổ lỗi:

1. Producer publish thành công nhưng không nhận được confirmation, rồi publish lại.
2. Broker giao message nhưng consumer crash trước khi xử lý.
3. Consumer xử lý nhưng crash trước khi commit database.
4. Database commit nhưng consumer crash trước acknowledgment.
5. Acknowledgment được gửi nhưng mất kết nối khiến consumer không biết broker đã nhận hay chưa.
6. Chunk commit thành công nhưng JobRepository checkpoint không được lưu theo cùng transaction.
7. Job restart đọc lại item do checkpoint chưa phản ánh đúng.
8. Hai consumer nhận cùng logical event do cấu hình visibility/lease hoặc producer duplicate.
9. Một message được chuyển từ queue chính sang retry queue rồi lại được giao nhiều lần.
10. Một người vận hành chủ động replay message đã xử lý.

Cửa sổ database commit thành công nhưng acknowledgment thất bại là lý do phổ biến khiến consumer phải xử lý duplicate. Không thể chỉ dựa vào việc “đã gọi ack” để khẳng định message sẽ không xuất hiện lần nữa.

## 6. Xác định khóa duplicate

Để phát hiện duplicate, cần một khóa đại diện cho business event. Khóa đó thường được gọi là **idempotency key**, **event ID** hoặc **deduplication key**.

Một message có thể chứa:

~~~json
{
  "eventId": "evt-9001",
  "aggregateId": "payment-123",
  "eventVersion": 7,
  "eventType": "PAYMENT_CAPTURED",
  "occurredAt": "2026-11-15T10:30:00Z"
}
~~~

Các lựa chọn khóa:

- Event ID do producer tạo và giữ ổn định qua retry.
- Business transaction ID như paymentId nếu mỗi payment chỉ có một event loại đó.
- Aggregate ID kết hợp event version.
- Source system kết hợp source event ID.
- Một composite key theo loại nghiệp vụ.

Không dùng delivery tag, receipt handle hoặc attempt number làm idempotency key. Những giá trị này thường mô tả lần giao, có thể thay đổi giữa các lần redelivery.

### Event ID khác aggregate ID

Một aggregate có thể phát sinh nhiều event. Nếu chỉ dùng aggregateId, event thứ hai của cùng payment có thể bị coi là duplicate dù nó là một chuyển trạng thái hợp lệ.

Ví dụ:

- payment-123 / PAYMENT_CREATED
- payment-123 / PAYMENT_CAPTURED
- payment-123 / PAYMENT_REFUNDED

Có thể dùng eventId riêng, hoặc aggregateId + eventType + version tùy contract. Khóa phải phân biệt các sự kiện hợp lệ nhưng nhận diện cùng một sự kiện khi nó được publish lại.

### Khóa phải được tạo ở producer

Nếu consumer tạo UUID mới mỗi lần nhận message, redelivery sẽ tạo khóa khác nhau và không thể deduplicate.

Producer cần tạo event ID một lần, lưu cùng business event và tái sử dụng ID đó khi publish retry. Consumer dùng ID này để phát hiện các lần giao lại.

## 7. Idempotent processing là gì?

Một thao tác idempotent có thể được thực hiện nhiều lần mà kết quả cuối không thay đổi sau lần thực hiện đầu tiên.

Ví dụ cập nhật trạng thái:

~~~sql
UPDATE payment
SET status = 'CAPTURED'
WHERE payment_id = ?
  AND status <> 'CAPTURED';
~~~

Đây có thể là thao tác idempotent nếu trạng thái CAPTURED là kết quả cuối và không có side effect phụ bị lặp. Nhưng nếu mỗi lần update đều tạo ledger entry hoặc gửi notification, toàn bộ use case chưa chắc idempotent.

Ví dụ không idempotent:

~~~sql
UPDATE account
SET balance = balance + 250.00
WHERE account_id = 'A-10';
~~~

Chạy hai lần sẽ cộng tiền hai lần.

Thiết kế idempotent cần kiểm soát mọi side effect, không chỉ câu lệnh SQL chính. Các side effect có thể gồm:

- Cập nhật số dư.
- Tạo transaction ledger.
- Gửi email hoặc SMS.
- Publish event tiếp theo.
- Tạo file export.
- Gọi API đối tác.
- Ghi audit record.

Có thể dùng event ID để bảo đảm cùng một event chỉ tạo side effect một lần trong database transaction.

## 8. Bảng inbox để deduplicate message

Một pattern phổ biến là **Inbox Pattern**: lưu ID của message đã xử lý trong cùng database với business update.

Ví dụ schema:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

consumer_name giúp cùng một event có thể được xử lý bởi các consumer logic khác nhau nếu nghiệp vụ yêu cầu. Nếu một event chỉ được xử lý một lần toàn hệ thống, có thể dùng event_id làm khóa chính.

Quy trình:

1. Bắt đầu database transaction của chunk.
2. Thử insert event ID vào processed_message.
3. Nếu insert thành công, tiếp tục cập nhật dữ liệu nghiệp vụ.
4. Nếu unique constraint báo event đã tồn tại, bỏ qua business side effect.
5. Commit inbox record và business update cùng transaction.
6. Chỉ acknowledge message sau khi transaction commit thành công theo semantics của broker integration.

Ví dụ service:

~~~java
@Transactional
public ProcessingResult processOnce(MessageEnvelope<OrderEvent> message) {
    int inserted = inboxRepository.tryInsert(
        "order-import",
        message.eventId()
    );

    if (inserted == 0) {
        return ProcessingResult.DUPLICATE;
    }

    orderService.apply(message.payload());

    return ProcessingResult.PROCESSED;
}
~~~

tryInsert cần được cài đặt bằng câu lệnh database phù hợp và xử lý unique constraint theo database đang dùng. Không nên catch mọi DataIntegrityViolationException rồi coi là duplicate; lỗi constraint khác vẫn cần được báo.

### Vì sao inbox và business update phải cùng transaction?

Nếu insert inbox commit trước business update, process có thể crash giữa hai thao tác. Lần redelivery sau thấy event đã tồn tại và bỏ qua, trong khi business update chưa từng xảy ra. Message bị đánh dấu đã xử lý dù side effect chưa hoàn tất.

Nếu business update commit trước inbox record, crash ở giữa có thể khiến lần redelivery áp dụng business update lần nữa.

Đưa hai thao tác vào cùng một transaction database giúp chúng cùng commit hoặc cùng rollback.

~~~mermaid
flowchart TD
    A["Bắt đầu DB transaction"] --> B["Insert inbox event ID"]
    B --> C{"Unique key mới?"}
    C -->|Không| D["Đánh dấu duplicate / no-op"]
    C -->|Có| E["Áp dụng business update"]
    D --> F["Commit"]
    E --> F
    F --> G["Acknowledge theo broker integration"]
~~~

Nếu inbox insert và business update nằm ở hai database khác nhau, transaction cục bộ không bảo đảm atomicity. Khi đó cần distributed transaction hoặc một workflow có recovery/idempotency riêng.

## 9. Xử lý unique constraint khi có consumer đồng thời

Hai consumer có thể cùng nhận một event hoặc producer có thể publish trùng gần như đồng thời. Cả hai đều kiểm tra “chưa có event” trước khi insert. Nếu dùng mô hình SELECT rồi INSERT, cả hai có thể cùng thấy chưa tồn tại.

Không làm:

~~~java
if (!repository.exists(eventId)) {
    repository.insert(eventId);
    applyBusinessUpdate();
}
~~~

Kiểm tra và insert không atomic. Dùng unique constraint làm cơ chế đồng bộ cuối cùng.

Một câu lệnh database có thể thực hiện insert-if-absent, ví dụ PostgreSQL:

~~~sql
INSERT INTO processed_message (
    consumer_name,
    event_id,
    processed_at
)
VALUES (?, ?, CURRENT_TIMESTAMP)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

Số dòng được insert cho biết event mới hay đã tồn tại. Với database khác, dùng cú pháp tương ứng hoặc bắt đúng unique constraint trong transaction.

Điểm cần giữ:

- Unique key phải được database bảo vệ.
- Inbox insert và business update cùng transaction.
- Duplicate không được biến thành lỗi chung bị bỏ qua.
- Nếu transaction bị rollback, inbox row cũng phải rollback.
- Xử lý lock contention và retry deadlock theo policy phù hợp.

## 10. Dùng inbox trong ItemProcessor hay ItemWriter?

Việc deduplicate có thể được đặt ở nhiều tầng, nhưng cần chọn nơi có transaction phù hợp.

### Trong processor

Processor có thể kiểm tra event ID và trả null nếu duplicate. Cách này có thể filter item, nhưng nếu processor insert inbox record hoặc tạo side effect thì việc đó có thể diễn ra ngoài transaction write theo semantics mong muốn. Processor cũng có thể được gọi lại khi rollback/retry.

Chỉ dùng processor để đọc/đánh giá duplicate nếu thao tác kiểm tra là an toàn và không tạo side effect. Một câu SELECT trước khi writer ghi không loại bỏ race condition.

### Trong writer hoặc service được writer gọi

Writer chạy trong chunk transaction và thường là nơi phù hợp để phối hợp inbox insert với business update:

~~~java
public class IdempotentOrderWriter implements ItemWriter<OrderEvent> {

    private final InboxRepository inbox;
    private final OrderService orderService;

    public IdempotentOrderWriter(
            InboxRepository inbox,
            OrderService orderService) {
        this.inbox = inbox;
        this.orderService = orderService;
    }

    @Override
    public void write(Chunk<? extends OrderEvent> chunk) {
        for (OrderEvent event : chunk.getItems()) {
            boolean firstDelivery = inbox.insertIfAbsent(
                "order-import",
                event.eventId()
            );

            if (!firstDelivery) {
                continue;
            }

            orderService.apply(event);
        }
    }
}
~~~

Đảm bảo repository và orderService dùng cùng DataSource/transaction manager hoặc một transaction strategy tương đương. Nếu service mở transaction độc lập hoặc commit riêng, atomicity có thể bị phá vỡ.

### Deduplicate trước khi tạo item

Một broker adapter có thể kiểm tra ID và chỉ đưa message chưa xử lý vào reader. Tuy nhiên, nếu marker được ghi trước khi chunk commit, có thể mất message sau crash. Chỉ dùng cách này khi marker và business processing được phối hợp transaction an toàn.

## 11. Duplicate item trong cùng một chunk

Một chunk có thể chứa hai message có cùng eventId do producer publish lặp hoặc broker giao lặp.

Ví dụ:

~~~text
Chunk:
  evt-9001
  evt-9002
  evt-9001
  evt-9003
~~~

Nếu writer chỉ deduplicate bằng một Set local trong chunk, có thể loại duplicate trong lần gọi đó. Nhưng Set local không bảo vệ duplicate giữa các chunk, các JobExecution hoặc các process khác.

Cơ chế bền vững cần unique key trong database hoặc một idempotency store dùng chung.

Có thể tối ưu bằng cách gom ID trong chunk trước khi xử lý, nhưng database vẫn phải là nơi bảo vệ tính duy nhất:

~~~java
Set<String> idsInChunk = new HashSet<>();

for (OrderEvent event : chunk) {
    if (!idsInChunk.add(event.eventId())) {
        continue;
    }

    processOnce(event);
}
~~~

Đoạn này chỉ loại duplicate lặp ngay trong cùng chunk. Nó không thay thế inbox table.

Cần xác định hành vi nếu hai item cùng eventId nhưng payload khác nhau. Đây có thể là producer bug hoặc event ID bị tái sử dụng. Không nên âm thầm coi là duplicate hợp lệ. Có thể lưu payload hash và fail/quarantine khi cùng ID nhưng nội dung khác.

## 12. Lưu payload hash để phát hiện event ID bị tái sử dụng

Một inbox schema có thể lưu hash:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    payload_hash VARCHAR(128) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Khi event ID đã tồn tại:

- Nếu payload hash giống nhau, đây có thể là redelivery hợp lệ.
- Nếu payload hash khác nhau, cùng event ID đại diện cho hai nội dung khác nhau; cần điều tra và thường nên fail hoặc quarantine.

Hash cần được tính từ representation ổn định. Nếu JSON field order hoặc whitespace có thể khác mà semantics giống nhau, hãy canonicalize payload trước khi hash hoặc dùng business fields được xác định rõ.

Không dùng hash làm thay thế event ID nếu có khóa nghiệp vụ ổn định. Hash chủ yếu hỗ trợ phát hiện ID reuse hoặc thay đổi payload bất thường.

## 13. Inbox retention và phạm vi deduplication

Inbox table không thể tăng vô hạn mà không có chính sách retention. Tuy nhiên, xóa event ID quá sớm có thể khiến một message replay sau nhiều tháng được xử lý lại.

Retention cần dựa trên:

- Broker retention và khả năng replay.
- Thời gian retry tối đa.
- Thời gian message nằm trong DLQ.
- Quy trình replay thủ công.
- Thời gian audit hoặc dispute nghiệp vụ.
- Idempotency window của hệ thống downstream.

Có thể lưu inbox vĩnh viễn cho business event quan trọng hoặc archive theo partition/date khi thời gian replay đã hết.

Khóa deduplication cũng cần scope rõ. Ví dụ consumer_name + event_id cho phép cùng event được xử lý bởi hai projection khác nhau. Nếu dùng event_id global, một consumer có thể vô tình chặn consumer khác.

## 14. Redelivery và transaction acknowledgment

Một nguyên tắc quan trọng là tránh acknowledge trước khi dữ liệu nghiệp vụ được commit.

### Acknowledge quá sớm

~~~text
1. Consumer nhận message
2. Acknowledge broker
3. Database update
4. Process crash trước commit
~~~

Broker đã xóa message nhưng database chưa ghi nhận thay đổi. Dữ liệu bị mất.

### Acknowledge sau commit

~~~text
1. Consumer nhận message
2. Database transaction cập nhật inbox + business data
3. Commit database
4. Acknowledge broker
5. Process crash trước khi broker nhận ack
6. Broker redeliver
7. Inbox phát hiện duplicate và bỏ qua business update
8. Acknowledge lần giao lại
~~~

Trường hợp thứ hai có thể tạo redelivery nhưng không tạo side effect nghiệp vụ trùng. Đây là thiết kế at-least-once kết hợp idempotency.

### Hai resource không tự atomic

Database commit và broker acknowledgment thường là hai thao tác trên hai resource. Có một cửa sổ lỗi giữa chúng. Nếu không dùng distributed transaction được hỗ trợ bởi cả hai hệ thống, hãy chấp nhận khả năng redelivery và bảo vệ bằng inbox/idempotency.

Một số broker/client hỗ trợ transaction hoặc coordinated acknowledgment. Cần kiểm tra chính xác transaction manager, connection factory và listener/container configuration. Không giả định việc dùng @Transactional tự động enlist broker và database vào cùng một atomic transaction.

## 15. JMS và acknowledgment

Với JMS, session acknowledgment mode ảnh hưởng thời điểm message được xác nhận.

Các mode phổ biến:

- AUTO_ACKNOWLEDGE: provider tự acknowledge theo semantics của session sau khi listener nhận message thành công.
- CLIENT_ACKNOWLEDGE: ứng dụng gọi acknowledge theo API.
- DUPS_OK_ACKNOWLEDGE: provider có thể lazy acknowledge và cho phép duplicate.
- Transacted session: acknowledgment gắn với commit/rollback của JMS session.

Tên mode và cách container quản lý session cần được hiểu cùng framework listener đang dùng. Spring listener container có thể quản lý acknowledgment và transaction theo cấu hình riêng.

Khi listener ném exception trong một transacted session, rollback có thể khiến message được redeliver. Với AUTO_ACKNOWLEDGE, không nên suy luận đơn giản từ việc method trả về hay exception bị bắt; hãy xác minh container semantics và test với broker thực tế.

Không tự gọi acknowledge trong một listener mà container đang quản lý transaction nếu điều đó xung đột với ownership của session.

## 16. Visibility timeout và receipt handle

Một số broker dùng visibility timeout thay cho acknowledgment kiểu JMS. Khi consumer nhận message, message tạm thời không hiển thị cho consumer khác trong một khoảng thời gian. Nếu không delete/ack trước khi timeout, message xuất hiện lại.

Các lưu ý:

- Thời gian xử lý có thể vượt visibility timeout.
- Consumer có thể cần gia hạn visibility/lease khi xử lý dài.
- Một receipt handle có thể gắn với lần nhận cụ thể; phải dùng handle hợp lệ để xóa message.
- Message có thể được giao lại nếu delete thất bại hoặc handle hết hiệu lực.
- Hai consumer có thể cùng xử lý nếu visibility không được gia hạn kịp.

Nếu Spring Batch chunk xử lý lâu, visibility timeout phải tính đến thời gian đọc, xử lý, ghi và commit. Không đặt timeout quá ngắn so với thời gian chunk ở percentile cao.

Ngay cả khi gia hạn visibility thành công, vẫn cần idempotency vì network failure hoặc process crash có thể tạo duplicate.

## 17. Tích hợp message reader với Spring Batch

Một ItemReader có thể lấy message từ broker hoặc một adapter có trách nhiệm nhận message. Reader cần định nghĩa điều kiện EOF cho một batch hữu hạn.

Ví dụ model:

~~~java
public record MessageEnvelope<T>(
    String eventId,
    String deliveryId,
    T payload,
    int deliveryAttempt
) {
}
~~~

Reader khái niệm:

~~~java
public class BrokerItemReader
        implements ItemStreamReader<MessageEnvelope<OrderEvent>> {

    private final BrokerClient brokerClient;
    private final String batchId;

    @Override
    public MessageEnvelope<OrderEvent> read() {
        BrokerMessage message =
            brokerClient.receiveForBatch(batchId);

        if (message == null) {
            return null;
        }

        return mapEnvelope(message);
    }

    @Override
    public void open(ExecutionContext context) {
        brokerClient.open();
    }

    @Override
    public void update(ExecutionContext context) {
        // Lưu cursor hoặc batch watermark nếu broker hỗ trợ.
    }

    @Override
    public void close() {
        brokerClient.close();
    }
}
~~~

Đây là adapter minh họa, không phải implementation dùng chung cho mọi broker. API receive có thể block, timeout hoặc trả trạng thái rỗng. Không chuyển timeout ngắn thành EOF nếu batch vẫn còn message.

Với queue vô hạn, một ItemReader chờ mãi sẽ không kết thúc Step. Cần xác định batch boundary như message count, batch ID, cutoff timestamp hoặc snapshot offset.

### Reader không nên acknowledge độc lập nếu chunk chưa commit

Nếu reader acknowledge ngay sau receive, writer có thể thất bại và message đã bị xóa. Một thiết kế an toàn cần trì hoãn acknowledgment đến sau commit hoặc dùng transaction/adapter bảo đảm semantics tương đương.

Với Spring Batch, reader và transaction manager phải được tích hợp cụ thể. Nếu không có transaction coordination, có thể dùng inbox/outbox và chấp nhận redelivery.

## 18. Phân biệt broker offset với ExecutionContext checkpoint

Với broker log hoặc queue có offset, có thể tồn tại hai trạng thái:

- Broker consumer offset hoặc acknowledgment state.
- Spring Batch ExecutionContext checkpoint.

Nếu hai trạng thái được commit độc lập, chúng có thể lệch nhau.

Ví dụ:

- ExecutionContext đã lưu offset 500 nhưng broker offset vẫn 490: message 491–500 có thể được giao lại; idempotency xử lý duplicate.
- Broker offset đã commit 500 nhưng JobRepository chỉ lưu 490: restart từ 490 có thể bỏ qua message nếu broker không cho seek/replay hoặc offset đã tiến không thể lùi.

Cần xác định nguồn nào là authority để restart. Một số kiến trúc dùng broker offset làm checkpoint chính; một số dùng JobRepository; một số dùng inbox table để làm durable processing ledger.

Không lưu hai checkpoint độc lập mà không có quy tắc recovery. Nếu Spring Batch quản lý checkpoint, phải bảo đảm broker adapter có thể seek hoặc replay từ checkpoint đó. Nếu broker quản lý offset, cần bảo đảm JobRepository không đưa ra trạng thái mâu thuẫn.

## 19. Idempotency cho database update

Cách đơn giản là ghi event ID trong cùng transaction với business update.

Ví dụ service:

~~~java
@Transactional
public void applyPaymentCaptured(PaymentCaptured event) {
    if (!inboxRepository.insertIfAbsent(
            "payment-projection",
            event.eventId())) {
        return;
    }

    paymentRepository.markCaptured(
        event.paymentId(),
        event.amount()
    );

    ledgerRepository.insertCapture(
        event.eventId(),
        event.paymentId(),
        event.amount()
    );
}
~~~

Nếu event được giao lại, insertIfAbsent trả false và service không áp dụng lại payment hoặc tạo ledger entry mới.

Ledger table cũng nên có unique key theo event ID để bảo vệ ở tầng database:

~~~sql
ALTER TABLE payment_ledger
ADD CONSTRAINT uq_payment_ledger_event
UNIQUE (event_id);
~~~

Đây là lớp bảo vệ bổ sung. Không chỉ dựa vào kiểm tra trong Java vì nhiều consumer có thể chạy đồng thời.

### Conditional update

Với một số state transition, có thể dùng điều kiện trạng thái:

~~~sql
UPDATE payment
SET status = 'CAPTURED'
WHERE payment_id = ?
  AND status = 'AUTHORIZED';
~~~

Số dòng update bằng 1 nghĩa là chuyển trạng thái thành công; bằng 0 có thể là duplicate hoặc trạng thái không hợp lệ. Cần query/logic bổ sung để phân biệt hai trường hợp.

Conditional update giúp tránh transition lặp, nhưng không thay thế event ledger nếu cần audit mỗi event.

## 20. Idempotency cho HTTP API và dịch vụ bên ngoài

Nếu writer gọi API ngoài, database inbox không thể tự bảo vệ side effect của API đó trừ khi API hỗ trợ idempotency key hoặc có một cơ chế phối hợp khác.

Ví dụ HTTP request:

~~~http
POST /payments/pay-123/capture
Idempotency-Key: evt-9001
Content-Type: application/json
~~~

Khi retry, gửi lại cùng key. API nhận biết request đã xử lý và trả lại kết quả trước đó thay vì capture lần nữa.

Quy tắc:

- Key phải ổn định qua retry và redelivery.
- Payload cho cùng key phải giống nhau theo contract.
- Key retention của API phải đủ dài cho retry/replay window.
- Xử lý response timeout không chứng minh request thất bại.
- Lưu kết quả hoặc correlation ID để điều tra.

Nếu API không hỗ trợ idempotency, cần một workflow bù trừ hoặc reconciliation. Không thể bảo đảm exactly-once side effect chỉ bằng cách đánh dấu event trong database trước/sau HTTP call, vì vẫn tồn tại crash window giữa hai hệ thống.

## 21. Outbox Pattern khi cần publish event tiếp theo

Một consumer có thể cập nhật database và cần publish event tiếp theo. Nếu cập nhật database commit nhưng publish thất bại, downstream không nhận được event. Nếu publish thành công nhưng database rollback, downstream nhận event cho thay đổi chưa commit.

**Outbox Pattern** giải quyết bằng cách ghi business update và outgoing event vào cùng database transaction:

~~~sql
CREATE TABLE outbox_event (
    event_id VARCHAR(200) PRIMARY KEY,
    aggregate_id VARCHAR(200) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

Trong cùng transaction:

1. Insert inbox event ID để deduplicate input.
2. Cập nhật business data.
3. Insert outgoing event vào outbox.
4. Commit.

Một publisher riêng đọc outbox và publish lên broker. Nếu publish thành công nhưng publisher crash trước khi đánh dấu published, event có thể được publish lại. Consumer downstream vẫn cần idempotency.

~~~mermaid
flowchart TD
    A["Inbound message"] --> B["DB transaction"]
    B --> C["Insert inbox ID"]
    C --> D["Update business data"]
    D --> E["Insert outbox event"]
    E --> F["Commit"]
    F --> G["Outbox publisher"]
    G --> H["Broker"]
    H --> I["Downstream idempotent consumer"]
~~~

Outbox không tự bảo đảm publisher chỉ gửi một lần. Nó bảo đảm business update và ý định publish được lưu atomic trong database. Delivery ra broker vẫn thường là at-least-once.

## 22. Retry, backoff và giới hạn redelivery

Nếu lỗi tạm thời, retry có thể giúp xử lý thành công. Nhưng retry vô hạn có thể giữ message và tài nguyên mãi mãi.

Các yếu tố cần quyết định:

- Số lần retry tối đa.
- Backoff cố định hay exponential.
- Jitter để tránh nhiều consumer retry cùng lúc.
- Timeout cho từng lần gọi.
- Tổng thời gian retry.
- Phân loại exception retryable.
- Thời điểm chuyển message sang DLQ.
- Có cần giữ thứ tự message không.

Ví dụ Spring Batch fault-tolerant Step:

~~~java
return new StepBuilder("messageImportStep", jobRepository)
    .<MessageEnvelope<OrderEvent>, MessageEnvelope<OrderEvent>>
        chunk(50, transactionManager)
    .reader(messageReader)
    .writer(idempotentWriter)
    .faultTolerant()
    .retry(TransientBrokerException.class)
    .retryLimit(3)
    .build();
~~~

Ví dụ này mô tả retry của Step. Nó không tự cấu hình redelivery policy của broker. Retry trong Step và broker redelivery cần được điều chỉnh cùng nhau để tránh nhân số attempt ngoài dự kiến.

Nếu Step retry 3 lần và broker cũng giao lại tối đa 5 lần, tổng số lần thực thi có thể cao hơn nhiều so với con số mà một phía cấu hình.

### Backoff

Exponential backoff thường tăng khoảng chờ sau mỗi lần thất bại:

~~~text
attempt 1: 1 giây
attempt 2: 2 giây
attempt 3: 4 giây
attempt 4: 8 giây
~~~

Có thể thêm jitter để tránh tất cả consumer retry cùng thời điểm. Giá trị thực tế cần dựa trên latency và retry budget của hệ thống.

Không retry lỗi không thể phục hồi như schema sai, credential sai hoặc event ID bị tái sử dụng với payload khác.

## 23. Poison message và Dead-Letter Queue

**Poison message** là message liên tục thất bại vì nội dung hoặc điều kiện xử lý không thể tự phục hồi. Ví dụ:

- JSON/XML malformed.
- Thiếu business key bắt buộc.
- Enum không được hỗ trợ.
- Vi phạm invariant nghiệp vụ.
- Payload vượt giới hạn.
- Schema version không được consumer hỗ trợ.

Nếu cứ redeliver message này vô hạn, nó có thể chặn queue hoặc làm consumer tốn tài nguyên.

**Dead-Letter Queue (DLQ)** hoặc dead-letter topic lưu message đã vượt quá chính sách retry/redelivery.

Thông tin nên giữ khi chuyển DLQ:

- Original event ID.
- Original queue/topic.
- Payload hoặc reference an toàn tới payload.
- Exception class và error code.
- Số lần delivery/attempt.
- Thời điểm đầu tiên và lần cuối xử lý.
- Consumer/job/step identifier.
- Correlation ID và trace ID.
- Schema version.

Không ghi credential hoặc dữ liệu nhạy cảm vào header/log DLQ nếu không cần. DLQ cần retention và quyền truy cập phù hợp.

### Replay từ DLQ

Replay không phải lúc nào cũng chỉ là publish lại message. Cần quyết định:

- Sửa payload hay sửa code trước?
- Giữ event ID gốc hay tạo event mới?
- Inbox có đang đánh dấu event đã xử lý không?
- Nếu event đã được xử lý một phần, có cần reconciliation?
- Replay có được phép tạo side effect mới không?
- Làm sao audit người thực hiện replay?

Nếu event đã được xử lý thành công nhưng bị chuyển DLQ do lỗi acknowledgment, replay phải được deduplicate. Nếu event chưa từng xử lý, replay cần đi qua cùng idempotency policy.

## 24. Skip trong Spring Batch không giống DLQ

Skip là quyết định của Step bỏ qua một item hoặc exception theo SkipPolicy. DLQ là cơ chế lưu message bị từ chối ở tầng messaging.

Skip item trong Spring Batch không tự chuyển message về DLQ. Nếu muốn quarantine, cần một reject writer hoặc một integration với broker/DLQ có transaction và acknowledgment rõ ràng.

Ví dụ processor ném lỗi dữ liệu:

~~~java
return new StepBuilder("messageImportStep", jobRepository)
    .<MessageEnvelope<OrderEvent>, OrderEvent>chunk(50, transactionManager)
    .reader(messageReader)
    .processor(eventProcessor)
    .writer(idempotentWriter)
    .faultTolerant()
    .skip(InvalidEventException.class)
    .skipLimit(100)
    .listener(rejectListener)
    .build();
~~~

Reject listener có thể ghi audit, nhưng không nên thực hiện side effect không idempotent. Nếu cần lưu payload reject bền vững, thường dùng writer/transactional reject store hoặc một Step riêng.

Không skip lỗi hạ tầng như database unavailable hoặc broker connection failure chỉ để Step hoàn tất. Phân biệt lỗi dữ liệu của một message với lỗi toàn hệ thống.

## 25. Redelivery và thứ tự message

Redelivery có thể ảnh hưởng ordering. Một message thất bại nhiều lần có thể bị đưa về cuối queue hoặc retry queue; các message sau có thể được xử lý trước.

Nếu nghiệp vụ yêu cầu thứ tự theo aggregate:

- Dùng partition key theo aggregate ID.
- Dùng sequence/version trên event.
- Kiểm tra version trước khi apply.
- Không cho event version mới vượt qua event cũ chưa xử lý nếu điều đó làm sai state.
- Cấu hình retry/DLQ sao cho không âm thầm phá ordering.
- Xử lý duplicate event ID độc lập với out-of-order event.

Ví dụ bảng aggregate lưu version:

~~~sql
UPDATE account_projection
SET balance = ?,
    event_version = ?
WHERE account_id = ?
  AND event_version = ?;
~~~

Câu lệnh cần kiểm tra expected version và cập nhật atomic. Nếu version đã lớn hơn hoặc bằng event đang nhận, có thể là duplicate/stale event; nếu version nhỏ hơn expected, có thể đang thiếu event trước đó.

Đây là optimistic concurrency control cho event ordering. Quy tắc cụ thể phụ thuộc event model.

## 26. Redelivery trong partitioned hoặc concurrent Step

Nếu nhiều worker cùng đọc message, duplicate có thể được xử lý đồng thời. Inbox unique constraint vẫn cần thiết vì in-memory lock trong một JVM không bảo vệ process khác.

Cần xem xét:

- Mỗi partition có reader và checkpoint riêng.
- Message broker có phân vùng/partition ownership ra sao.
- Visibility timeout có đủ dài cho worker không.
- Hai worker có thể cùng nhận cùng event không.
- Idempotency key có unique toàn consumer group không.
- Writer có transaction isolation phù hợp không.
- DLQ/retry queue có giữ ordering theo key không.

Không dùng static Set trong JVM làm deduplication store. Nó mất khi process restart, không chia sẻ giữa nhiều instance và có thể tăng bộ nhớ không giới hạn.

Với concurrent consumers, unique constraint hoặc conditional write ở database là điểm đồng bộ bền vững.

## 27. Checkpoint và deduplication giải quyết hai vấn đề khác nhau

ExecutionContext checkpoint trả lời: reader nên tiếp tục đọc từ đâu?

Inbox/idempotency trả lời: business event này đã được áp dụng chưa?

Hai cơ chế không thay thế nhau.

Ví dụ reader đã đọc message 100 và chunk commit thành công, nhưng broker acknowledgment thất bại. ExecutionContext có thể đã lưu checkpoint sau message 100. Broker vẫn redeliver message 100. Nếu reader chỉ dựa vào checkpoint của queue log, có thể nó không đọc lại message đó; nhưng nếu broker giao trực tiếp, duplicate vẫn có thể đến. Inbox xử lý trường hợp này.

Ngược lại, inbox có event ID không tự bảo đảm reader có thể khôi phục offset hoặc continuation token. Reader vẫn cần checkpoint/replay strategy.

Một thiết kế đáng tin cậy xác định cả hai:

- Nguồn nào quyết định vị trí đọc?
- Khi nào checkpoint được commit?
- Khi nào broker acknowledgment xảy ra?
- Inbox marker và business update nằm trong transaction nào?
- Khi checkpoint và broker state lệch nhau thì recovery theo quy tắc nào?

## 28. Kiểm thử redelivery và duplicate

Unit test nên xác nhận cùng event ID được áp dụng một lần:

~~~java
@Test
void duplicateEventDoesNotApplyBusinessUpdateTwice() {
    OrderEvent event = new OrderEvent(
        "evt-9001",
        "order-123",
        new BigDecimal("250.00")
    );

    when(inboxRepository.insertIfAbsent(
        "order-import",
        "evt-9001"
    )).thenReturn(true, false);

    idempotentService.process(event);
    idempotentService.process(event);

    verify(orderService, times(1)).apply(event);
}
~~~

Test này kiểm tra service behavior. Nó chưa chứng minh transaction database hoặc concurrency. Cần integration test với database thật hoặc Testcontainers để xác nhận unique constraint.

### Test cùng event trong cùng chunk

Tạo chunk có event ID lặp:

~~~text
evt-1
evt-2
evt-1
evt-3
~~~

Xác nhận:

- Business update cho evt-1 chỉ xảy ra một lần.
- evt-2 và evt-3 được xử lý.
- Inbox chỉ có một row cho mỗi event.
- Write count và reject/duplicate metrics theo quy ước ứng dụng.

Nếu writer nhận duplicate trong cùng chunk, unique constraint phải xử lý đúng cả trường hợp hai lần insert xảy ra trong cùng transaction.

## 29. Kiểm thử crash window giữa database commit và acknowledgment

Đây là test quan trọng để xác nhận thiết kế idempotent.

Mô phỏng:

1. Consumer nhận event evt-9001.
2. Inbox và business update commit thành công.
3. Giả lập lỗi trước khi acknowledgment được broker ghi nhận.
4. Broker giao event evt-9001 lần nữa.
5. Consumer nhận duplicate.
6. Inbox insert-if-absent không tạo row mới.
7. Business update không chạy lần thứ hai.
8. Consumer acknowledge lần giao lại.

Kết quả mong đợi: message có thể được giao hai lần nhưng business side effect chỉ xảy ra một lần.

Không thể chứng minh cửa sổ này chỉ bằng mock service đơn giản. Nên có integration test với broker/test container nếu semantics của broker là phần quan trọng của hệ thống.

## 30. Kiểm thử transaction rollback

Một test khác mô phỏng business update thất bại sau inbox insert:

1. Bắt đầu transaction.
2. Inbox insert thành công.
3. Business update ném exception.
4. Transaction rollback.
5. Xác nhận inbox row không tồn tại.
6. Gửi lại event.
7. Xác nhận lần sau có thể insert inbox và xử lý thành công.

Nếu inbox row vẫn tồn tại sau rollback, có thể inbox repository dùng transaction khác hoặc propagation độc lập. Điều đó có thể khiến message bị đánh dấu duplicate dù business update chưa hoàn tất.

Test nên kiểm tra transaction manager và DataSource thật của ứng dụng.

## 31. Kiểm thử broker redelivery và DLQ

Một integration test broker có thể xác nhận:

- Message được giao lần đầu.
- Consumer rollback hoặc không acknowledge.
- Broker redeliver theo cấu hình.
- Delivery count/attempt metadata thay đổi đúng.
- Sau số lần thất bại, message được chuyển DLQ.
- Payload, event ID và exception metadata được giữ.
- Replay message không tạo side effect trùng.

Các bước cụ thể khác nhau giữa JMS broker, Kafka, RabbitMQ, SQS và các hệ thống khác. Dùng broker test tương ứng hoặc test container để xác nhận behavior thực tế.

Không chỉ kiểm tra method listener được gọi hai lần; cần xác nhận broker thực sự giao lại message theo protocol.

## 32. Observability cho duplicate và redelivery

Trong production, cần phân biệt số lần nhận message với số business event mới được xử lý.

Metric hữu ích:

- message.received.count
- message.redelivery.count
- message.duplicate.count
- message.processed.count
- message.retry.count
- message.deadletter.count
- message.processing.duration
- inbox.insert.conflict.count
- message.ack.failure.count

Log có cấu trúc nên chứa:

- eventId.
- broker message ID.
- delivery attempt/count.
- consumer name.
- JobExecution ID.
- StepExecution ID.
- aggregate ID/version.
- outcome: processed, duplicate, skipped, retrying, dead-lettered.
- exception type và error code.

Không ghi toàn bộ payload vào log nếu chứa thông tin cá nhân, payment data hoặc secret. Dùng event ID và correlation ID để liên kết trace.

### Tỷ lệ duplicate tăng bất thường

Duplicate là điều có thể xảy ra trong at-least-once. Nhưng tỷ lệ tăng mạnh có thể chỉ ra:

- Consumer timeout hoặc crash.
- Visibility timeout quá ngắn.
- Broker connection không ổn định.
- Acknowledgment bị lỗi.
- Producer publish lặp.
- Consumer xử lý lâu hơn retry budget.
- Job restart thường xuyên.
- Inbox retention quá ngắn.

Theo dõi xu hướng để phân biệt duplicate bình thường với sự cố hệ thống.

## 33. Những lỗi thiết kế thường gặp

### Acknowledge trước khi commit business data

Process crash sau ack có thể làm mất message. Acknowledge sau commit hoặc dùng transaction coordination phù hợp.

### Cho rằng broker không bao giờ giao trùng

At-least-once cho phép redelivery. Consumer cần idempotent.

### Dùng delivery tag làm idempotency key

Delivery tag/receipt handle có thể thay đổi theo lần nhận. Dùng event ID ổn định.

### Chỉ SELECT trước khi INSERT

Hai consumer đồng thời có thể cùng thấy chưa tồn tại. Dùng unique constraint và insert-if-absent atomic.

### Insert inbox trong transaction riêng

Inbox commit trước business update có thể làm event bị bỏ qua dù business data chưa cập nhật. Đặt chúng trong cùng transaction khi có thể.

### Deduplicate bằng Set trong JVM

Set mất khi restart và không chia sẻ giữa nhiều instance. Dùng store bền vững.

### Dùng aggregate ID làm event ID

Một aggregate có nhiều event hợp lệ. Dùng event ID hoặc composite key phân biệt event/version.

### Coi timeout HTTP là request thất bại

Server có thể đã xử lý request. Gửi lại cùng idempotency key hoặc reconciliation.

### Retry vô hạn poison message

Một message không thể phục hồi có thể chặn queue. Dùng retry budget và DLQ.

### Nhầm skip với DLQ

Skip không tự chuyển message sang broker DLQ. Thiết kế reject persistence hoặc broker dead-letter policy riêng.

### Dùng ExecutionContext thay inbox

Checkpoint theo vị trí đọc không chứng minh business event đã được áp dụng. Cần cả checkpoint và deduplication.

### Dùng inbox thay checkpoint

Inbox không cho reader biết nên tiếp tục đọc từ đâu. Cần reader restart strategy.

### Không kiểm tra payload khi event ID trùng

Cùng event ID nhưng payload khác có thể là producer bug. Lưu hash hoặc so sánh business identity theo contract.

### Cho rằng @Transactional bao gồm broker và database

Transaction manager thường chỉ quản lý resource được enlist. Kiểm tra integration hoặc dùng inbox/outbox.

## 34. Quy trình thiết kế redelivery và duplicate handling

Khi xây dựng message processing Job, có thể thực hiện theo trình tự:

1. **Xác định delivery semantics:** broker dùng at-most-once, at-least-once hay transaction semantics nào?
2. **Chọn business event ID:** ID ổn định qua producer retry và broker redelivery.
3. **Xác định batch boundary:** message nào thuộc Job/Step và điều kiện EOF là gì?
4. **Thiết kế acknowledgment:** ack xảy ra trước hay sau commit; ai sở hữu session/receipt handle?
5. **Thiết kế inbox:** unique key, consumer scope, payload hash và retention.
6. **Đặt transaction boundary:** inbox marker và business update cùng transaction nếu có thể.
7. **Bảo vệ external side effect:** idempotency key, outbox hoặc reconciliation.
8. **Cấu hình retry:** exception classification, backoff, attempt limit và timeout.
9. **Cấu hình DLQ:** poison message, metadata, retention và replay procedure.
10. **Thiết kế checkpoint:** xác định authority giữa broker offset và JobRepository ExecutionContext.
11. **Kiểm tra concurrency/order:** unique constraint, aggregate version và partition key.
12. **Kiểm thử crash window:** commit trước ack, rollback sau inbox insert, redelivery và replay.
13. **Theo dõi:** received, redelivery, duplicate, ack failure, retry và DLQ metrics.

## 35. Những điểm cần nhớ

- Redelivery là broker giao lại message chưa được xác nhận hoàn tất.
- Duplicate item có thể xuất hiện do redelivery, producer retry, application retry hoặc Job restart.
- At-least-once thường cho phép duplicate; consumer cần idempotent.
- Retry của Spring Batch khác với redelivery của broker và restart của Job.
- Idempotency key phải ổn định qua mọi lần giao, thường là event ID do producer tạo.
- Không dùng delivery tag hoặc receipt handle làm khóa deduplication.
- Inbox table với unique constraint giúp phát hiện duplicate bền vững.
- Inbox insert và business update nên nằm trong cùng database transaction.
- Acknowledge trước commit có thể làm mất message; commit trước ack có thể tạo redelivery, vì vậy cần idempotency.
- Database transaction và broker ack không tự atomic nếu không có integration/distributed transaction tương ứng.
- Checkpoint ExecutionContext và inbox giải quyết hai vấn đề khác nhau.
- External API cần idempotency key hoặc reconciliation; inbox nội bộ không tự bảo vệ side effect bên ngoài.
- Outbox phối hợp business update và ý định publish trong một transaction, nhưng publisher vẫn có thể gửi lặp.
- Retry cần giới hạn, backoff và phân loại lỗi; poison message cần DLQ.
- Skip trong Spring Batch không đồng nghĩa chuyển message vào DLQ.
- Test crash window giữa DB commit và broker acknowledgment.
- Theo dõi delivery count, duplicate rate, acknowledgment failure và DLQ.

Redelivery không thể bị loại bỏ hoàn toàn trong nhiều hệ thống message at-least-once, và cũng không cần phải loại bỏ nếu consumer xử lý idempotent. Khi event ID ổn định, inbox và business update được phối hợp transaction, acknowledgment đặt đúng thời điểm, còn retry/DLQ có giới hạn rõ ràng, Spring Batch có thể xử lý message giao lại mà không lặp side effect nghiệp vụ.

