# Idempotent consumer

## 1. Idempotent consumer là gì?

**Idempotent consumer** là consumer được thiết kế để khi nhận cùng một message nhiều lần, kết quả nghiệp vụ cuối cùng vẫn tương đương với việc message chỉ được áp dụng một lần.

Trong Kafka, consumer có thể nhận lại record vì retry, rebalance, process crash hoặc offset chưa được commit. Đây là hành vi bình thường của mô hình **at-least-once delivery**. Vì vậy, một listener đáng tin cậy phải tính tới duplicate delivery ngay cả khi producer và broker hoạt động đúng.

Ví dụ topic orders.paid chứa event:

~~~json
{
  "eventId": "evt-8f21",
  "orderId": "order-1042",
  "amount": 125000,
  "currency": "VND"
}
~~~

Nếu listener tăng số tiền đã thu của order thêm 125.000 đồng mỗi lần nhận event, duplicate sẽ làm số tiền được ghi nhận hai lần. Nếu listener dùng eventId để bảo đảm event chỉ được áp dụng một lần trong database, lần giao lại có thể được nhận diện và bỏ qua.

~~~text
Kafka record evt-8f21
        |
        v
Consumer receives record
        |
        v
Check idempotency / inbox
        |
    +---+----------------------+
    |                          |
 First processing          Duplicate
    |                          |
    v                          v
Apply business effect       Skip effect
    |                          |
    v                          |
Commit DB transaction          |
    |                          |
    +-------------+------------+
                  |
                  v
       Listener completes
                  |
                  v
       Kafka offset advances
~~~

Idempotency không có nghĩa Kafka sẽ không bao giờ giao duplicate. Nó có nghĩa ứng dụng xử lý duplicate an toàn.

## 2. Vì sao Kafka có thể giao lại một record?

Kafka lưu offset theo consumer group và partition. Consumer chỉ có thể tiếp tục từ vị trí đã commit sau khi process restart hoặc partition được giao cho consumer khác.

Một cửa sổ lỗi phổ biến:

~~~text
1. Consumer đọc offset 120
2. Listener ghi database thành công
3. Process crash trước khi Kafka offset 121 được commit
4. Consumer mới nhận partition
5. Kafka giao lại offset 120
~~~

Database đã có side effect của lần đầu. Kafka chưa biết công việc đó đã hoàn tất, nên record có thể được giao lại.

Các nguyên nhân khác:

- Listener ném exception và error handler retry.
- Consumer vượt max.poll.interval.ms và bị group rebalance.
- Pod bị kill hoặc node restart.
- Network interruption khiến consumer không xác định được commit đã hoàn tất hay chưa.
- Manual acknowledgment chưa được gọi.
- Batch xử lý một phần rồi thất bại.
- Operator replay offset hoặc republish message.
- DLT record được đưa lại topic chính.

Duplicate delivery không nhất thiết là bug. Nó là tình huống cần được xử lý trong thiết kế.

## 3. Idempotency theo góc nhìn nghiệp vụ

Một thao tác idempotent có tính chất:

~~~text
f(f(state, event), event) = f(state, event)
~~~

Nói cách khác, áp dụng cùng event lần thứ hai không làm thay đổi kết quả cuối cùng thêm một lần nữa.

Ví dụ thao tác idempotent:

- Đặt trạng thái đơn hàng thành PAID nếu event xác nhận đúng order.
- Đặt địa chỉ giao hàng thành giá trị mới được version hóa.
- Ghi nhận eventId đã xử lý với unique constraint.
- Upsert một projection theo entity ID và version.

Ví dụ không idempotent nếu thực hiện lặp:

- Tăng balance thêm 100.000 đồng.
- Trừ inventory thêm 1 đơn vị.
- Gửi email xác nhận mỗi lần nhận record.
- Tạo một shipment mới cho mỗi invocation.
- Cộng thêm loyalty points mỗi lần xử lý event.

Không thể chỉ nhìn tên hàm updateOrder() để kết luận nó idempotent. Cần xem side effect thực tế và trạng thái trước/sau khi event được áp dụng.

## 4. Phân biệt message ID, key và offset

Để nhận diện duplicate, consumer cần một **idempotency key ổn định** đại diện cho một lần phát hành nghiệp vụ.

| Giá trị | Vai trò | Có nên làm idempotency key? |
|---|---|---|
| eventId/messageId | ID duy nhất của event theo contract producer | Thường là lựa chọn tốt |
| Kafka key | Khóa partitioning hoặc entity routing | Chỉ khi semantics bảo đảm phù hợp |
| Topic + partition + offset | Vị trí vật lý của record | Có thể nhận diện cùng Kafka record, không đủ cho republish |
| correlationId | Liên kết một luồng nghiệp vụ | Thường không, vì một flow có nhiều event |
| orderId | Nhận diện entity nghiệp vụ | Không nếu một order có nhiều event hợp lệ |
| requestId | Nhận diện request | Chỉ khi mỗi request tạo đúng một logical effect |

**Offset không phải event identity.** Khi cùng event được publish lại vào topic, nó có thể có offset mới. Nếu deduplicate theo topic-partition-offset, bản publish lại vẫn được xem là record mới.

**Correlation ID không phải event ID.** Một order flow có thể phát OrderCreated, PaymentAuthorized và OrderShipped với cùng correlation ID. Deduplicate tất cả theo correlation ID sẽ làm mất các event hợp lệ.

### 4.1. Event ID phải ổn định qua retry

Producer nên tạo eventId một lần khi tạo logical event, rồi giữ nguyên ID qua các lần retry publish hoặc republish cùng event.

Nếu producer tạo UUID mới cho mỗi lần gửi lại cùng business event, consumer không thể nhận biết hai record là cùng một logical event chỉ bằng eventId.

## 5. Idempotent producer không thay thế idempotent consumer

Kafka producer có cơ chế idempotence, bật bằng cấu hình enable.idempotence=true trong các cấu hình tương ứng. Cơ chế này giúp broker nhận diện và loại bỏ một số bản gửi trùng do producer retry trong protocol, dựa trên producer identity và sequence numbers.

Nó không tự giải quyết mọi duplicate nghiệp vụ:

- Ứng dụng gọi send hai lần cho cùng một event với hai lần tạo record mới.
- Hai producer instances độc lập phát cùng một logical event.
- Outbox relay publish lại sau khi không xác định được kết quả.
- Consumer xử lý record rồi crash trước khi commit offset.
- Operator replay hoặc DLT republish event.

| Cơ chế | Bảo vệ điều gì? |
|---|---|
| Producer idempotence | Duplicate do producer protocol retries trong phạm vi Kafka hỗ trợ |
| Consumer deduplication | Cùng logical event không lặp side effect ở consumer |
| Kafka transactions | Atomicity cho các thao tác Kafka được đưa vào transaction |
| Database transaction | Atomicity giữa inbox/dedup marker và DB business changes |
| API idempotency key | Dịch vụ bên ngoài nhận diện request lặp |

Một pipeline tin cậy có thể cần nhiều lớp trong bảng này.

## 6. Pattern phổ biến: Inbox table

**Inbox pattern** lưu dấu vết event đã xử lý trong cùng database transaction với business side effect.

Bảng inbox có unique constraint trên phạm vi consumer/handler và event ID:

~~~sql
CREATE TABLE processed_message (
    handler_name  VARCHAR(120) NOT NULL,
    event_id      VARCHAR(160) NOT NULL,
    payload_hash  VARCHAR(64),
    processed_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (handler_name, event_id)
);
~~~

handler_name phân biệt các consumer effects độc lập. Cùng event có thể được xử lý một lần bởi order projection và một lần bởi analytics projection; không nên deduplicate toàn hệ thống bằng một event ID duy nhất mà không xác định scope.

Nếu eventId được bảo đảm globally unique, schema có thể đơn giản hơn. Nếu ID chỉ unique trong tenant hoặc producer, cần đưa producer/tenant identity vào unique key.

### 6.1. Vì sao cần unique constraint?

Hai consumer invocations có thể đồng thời nhận cùng event do retry/rebalance hoặc một luồng replay. Một câu lệnh SELECT trước rồi INSERT sau không đủ an toàn:

~~~text
Thread A: SELECT -> no row
Thread B: SELECT -> no row
Thread A: INSERT
Thread B: INSERT
~~~

Cả hai thread đều có thể vượt qua check. Unique constraint ở database là lớp đồng bộ cuối cùng bảo đảm chỉ một transaction giành được quyền xử lý event trong cùng scope.

Không dùng một biến boolean trong JVM làm dedup store. Nó mất khi process restart và không chia sẻ giữa replicas.

## 7. Xử lý inbox và business update trong cùng transaction

Nguyên tắc quan trọng nhất:

**Ghi dấu event đã nhận và áp dụng business side effect phải nằm trong cùng một database transaction.**

Nếu inbox marker commit trước, rồi business update thất bại, lần retry sau có thể bị đánh dấu duplicate và bỏ qua dù nghiệp vụ chưa hoàn tất.

Nếu business update commit trước, rồi inbox marker thất bại, lần giao lại có thể áp dụng side effect lần nữa.

~~~text
BEGIN DB TRANSACTION
      |
      v
Insert inbox key (handler, eventId)
      |
      +-- Unique conflict --> Duplicate: do not apply effect
      |
      +-- Inserted
              |
              v
       Apply business update
              |
              v
          COMMIT
~~~

Nếu business update lỗi, transaction rollback cả inbox row và business changes. Lần giao lại có thể thử lại toàn bộ.

### 7.1. Ví dụ PostgreSQL

Câu lệnh insert idempotent:

~~~sql
INSERT INTO processed_message (
    handler_name,
    event_id,
    payload_hash
)
VALUES (
    :handlerName,
    :eventId,
    :payloadHash
)
ON CONFLICT (handler_name, event_id) DO NOTHING;
~~~

PostgreSQL trả số row affected:

- 1: transaction vừa giành được event key.
- 0: key đã tồn tại, event được xem là duplicate trong scope đó.

Đây là cú pháp PostgreSQL. Với MySQL, SQL Server hoặc Oracle, dùng cú pháp upsert/insert-if-absent tương ứng và kiểm tra semantics cạnh tranh/row count của database cụ thể.

### 7.2. Ví dụ repository Spring Data JPA

~~~java
public interface ProcessedMessageRepository
        extends Repository<ProcessedMessage, ProcessedMessageId> {

    @Modifying
    @Query(value = """
        INSERT INTO processed_message (
            handler_name,
            event_id,
            payload_hash
        )
        VALUES (
            :handlerName,
            :eventId,
            :payloadHash
        )
        ON CONFLICT (handler_name, event_id) DO NOTHING
        """, nativeQuery = true)
    int insertIfAbsent(
        @Param("handlerName") String handlerName,
        @Param("eventId") String eventId,
        @Param("payloadHash") String payloadHash
    );
}
~~~

Ví dụ giả định Spring Data JPA và PostgreSQL. Repository method phải chạy trong transaction đang bao trùm business update.

### 7.3. Service xử lý idempotent

~~~java
@Service
public class OrderPaidHandler {

    private static final String HANDLER = "order-paid-projection-v1";

    private final ProcessedMessageRepository processedMessages;
    private final OrderRepository orders;

    public OrderPaidHandler(
            ProcessedMessageRepository processedMessages,
            OrderRepository orders) {
        this.processedMessages = processedMessages;
        this.orders = orders;
    }

    @Transactional
    public ProcessingResult handle(OrderPaid event) {
        int inserted = processedMessages.insertIfAbsent(
            HANDLER,
            event.eventId(),
            event.payloadHash()
        );

        if (inserted == 0) {
            return ProcessingResult.DUPLICATE;
        }

        orders.markPaid(
            event.orderId(),
            event.paymentId(),
            event.amount()
        );

        return ProcessingResult.PROCESSED;
    }
}
~~~

Listener chỉ gọi service:

~~~java
@KafkaListener(
    topics = "orders.paid",
    groupId = "order-fulfillment"
)
public void consume(OrderPaid event) {
    ProcessingResult result = orderPaidHandler.handle(event);
    log.debug("OrderPaid outcome={}", result);
}
~~~

Gọi service qua Spring bean proxy giúp transaction interceptor hoạt động. Tránh self-invocation trong cùng bean rồi giả định @Transactional luôn được áp dụng.

Khi service trả về, DB transaction đã commit hoặc đã ném exception. Container mới tiếp tục hoàn tất listener invocation theo acknowledgment mode đang cấu hình.

## 8. Cửa sổ lỗi: DB commit xong nhưng Kafka offset chưa commit

Đây là tình huống inbox pattern xử lý:

~~~text
Consumer reads event evt-8f21
          |
          v
DB transaction:
  insert processed_message(evt-8f21)
  update order -> PAID
  COMMIT
          |
          v
Process crashes
          |
          X Kafka offset not committed
          |
          v
Kafka redelivers evt-8f21
          |
          v
INSERT conflicts with inbox key
          |
          v
Skip business update
          |
          v
Listener completes; offset advances
~~~

Side effect chỉ được áp dụng một lần trong database, dù listener được gọi nhiều lần.

Đây là lý do **inbox marker phải commit cùng business update**. Nếu không, crash giữa hai bước sẽ để lại trạng thái không nhất quán.

### 8.1. Listener trả về trước khi DB commit?

Nếu dùng @Transactional ở service riêng và transaction commit trước khi service method trả về qua proxy, listener chỉ tiếp tục sau khi DB transaction kết thúc.

Nếu transaction được mở ở một boundary khác, phải xác minh thứ tự thực tế. Không được để container commit Kafka offset trước khi DB side effect đã commit thành công.

## 9. Vì sao không chỉ dùng SELECT rồi INSERT?

Mẫu code sau có race condition:

~~~java
if (!repository.existsByEventId(event.eventId())) {
    repository.save(new ProcessedMessage(event.eventId()));
    orderRepository.markPaid(event.orderId());
}
~~~

Hai invocations đồng thời có thể cùng thấy event chưa tồn tại rồi cùng thực hiện side effect.

Cách đúng là dùng một thao tác insert-if-absent có unique constraint và để database quyết định transaction nào giành được key.

Nếu database báo unique violation thay vì trả row count, có thể bắt exception theo semantics của database, nhưng cần lưu ý nhiều ORM đánh dấu transaction rollback-only sau constraint violation. Câu lệnh ON CONFLICT DO NOTHING hoặc upsert tương đương thường dễ kiểm soát hơn.

Không bắt mọi DataIntegrityViolationException rồi coi là duplicate: lỗi constraint khác cũng có thể là data corruption cần được báo.

## 10. Duplicate event nhưng payload khác nhau

Nếu cùng eventId xuất hiện với payload khác, đó có thể là producer bug hoặc ID bị tái sử dụng.

~~~text
eventId=evt-8f21, orderId=1042, amount=125000
eventId=evt-8f21, orderId=2099, amount=990000
~~~

Inbox unique key sẽ nhận diện bản thứ hai là duplicate và có thể bỏ qua. Nhưng đây không phải duplicate bình thường: cùng ID đang đại diện hai nội dung khác nhau.

Lưu payload_hash hoặc một checksum canonical của business payload để so sánh. Khi duplicate:

- Hash giống nhau: có thể là redelivery hợp lệ.
- Hash khác nhau: ghi nhận conflict, alert và xử lý theo policy an toàn.

Không đưa raw payload hoặc hash có thể suy ngược dữ liệu nhạy cảm vào metric label. Hash phù hợp để so sánh trong storage có kiểm soát, nhưng vẫn phải cân nhắc dữ liệu đầu vào.

## 11. Chọn phạm vi của idempotency key

Idempotency key cần duy nhất trong đúng **scope của side effect**.

Ví dụ một event OrderPaid có thể được tiêu thụ bởi order-paid-projection, accounting-ledger và customer-notification. Mỗi handler có một side effect khác nhau. Nếu inbox table chỉ unique theo eventId trên toàn hệ thống, consumer đầu tiên có thể khiến các consumer khác bị chặn nhầm.

Schema composite key:

~~~text
PRIMARY KEY (handler_name, event_id)
~~~

Nếu cùng handler chạy nhiều phiên bản projection có mục đích độc lập, có thể đưa projection generation/version vào scope.

Với event ID không globally unique:

~~~text
PRIMARY KEY (consumer_name, producer_name, tenant_id, event_id)
~~~

Không thêm dimensions vào key tùy tiện. Scope phải thể hiện logical effect, không phải pod ID hoặc thread ID.

## 12. Idempotent business update không cần inbox trong mọi trường hợp

Một số thao tác có thể tự idempotent nhờ thiết kế state update.

~~~sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = :orderId
  AND status <> 'PAID';
~~~

Chạy lại câu lệnh không làm trạng thái PAID thay đổi thêm lần nữa.

Tuy nhiên, nếu business update còn insert ledger row mới, cộng balance, gửi email, gửi webhook hoặc tạo shipment thì những side effects đó vẫn có thể lặp.

Cần xem toàn bộ transaction, không chỉ câu SQL đầu tiên. Inbox pattern hữu ích khi một logical event tạo nhiều business changes cần được bảo vệ cùng nhau.

### 12.1. Set state và increment state

| Thao tác | Idempotent khi lặp? |
|---|---|
| Set order.status = PAID | Thường có, nếu state transition hợp lệ |
| Set customer.address = value mới | Có thể, nếu version/order được xử lý |
| Increment account.balance by amount | Không |
| Decrement inventory by quantity | Không |
| Insert ledger entry với unique eventId | Có |
| Send email mỗi invocation | Không nếu provider không deduplicate |

Đừng biến một thao tác increment thành update idempotent chỉ bằng cách thêm điều kiện trạng thái nếu còn nhiều bảng side effect khác.

## 13. Idempotency với account balance và inventory

Ví dụ không an toàn:

~~~sql
UPDATE account
SET balance = balance + :amount
WHERE account_id = :accountId;
~~~

Nếu record được giao lại, balance tăng thêm lần nữa.

Có thể bảo vệ bằng inbox và ledger entry trong cùng transaction:

~~~text
BEGIN
  insert inbox key
  if duplicate:
      skip
  else:
      insert ledger entry with unique event_id
      update account balance
COMMIT
~~~

Ledger entry có unique event ID giúp audit và chống duplicate. Balance update và ledger insert phải atomic trong cùng database transaction.

Với inventory decrement, dùng reservation ID hoặc allocation event ID duy nhất và state transition rõ ràng. Không chỉ dựa vào số lượng hiện tại vì duplicate có thể trừ nhiều lần.

## 14. Concurrency: hai consumer cùng nhận một logical event

Trong một consumer group bình thường, một partition chỉ được gán cho một member tại một thời điểm. Nhưng cùng logical event vẫn có thể đến đồng thời qua:

- Hai bản publish có cùng event ID vào các partitions khác nhau.
- Hai topic/route chứa cùng event.
- Manual replay chạy song song với live consumer.
- Hai handler instances xử lý cùng nguồn dữ liệu.
- Application code gọi service xử lý cùng event đồng thời.

Database unique constraint giúp phối hợp qua replicas.

~~~text
Consumer A                         Consumer B
    |                                  |
    v                                  v
INSERT inbox(evt-8f21)             INSERT inbox(evt-8f21)
    |                                  |
    v                                  v
Wins unique key                    Wait / conflict
    |                                  |
    v                                  v
Apply business update              No business update
    |                                  |
    v                                  v
COMMIT                              Observe duplicate
~~~

Transaction B có thể phải chờ transaction A kết thúc. Nếu A commit, B nhận conflict/no-op; nếu A rollback, B có thể giành quyền insert và xử lý. Hành vi cụ thể phụ thuộc isolation level và database.

Không dùng cache local làm cơ chế đồng bộ giữa consumer replicas.

## 15. Event ordering và idempotency là hai vấn đề khác nhau

Idempotency ngăn một event được áp dụng nhiều lần. Nó không bảo đảm event được áp dụng đúng thứ tự.

Ví dụ:

~~~text
OrderUpdated(version=5)
OrderUpdated(version=4)
~~~

Nếu version 4 đến sau version 5 và consumer áp dụng mù quáng, trạng thái mới có thể bị ghi đè bởi dữ liệu cũ.

Có thể dùng optimistic version check:

~~~sql
UPDATE order_projection
SET status = :status,
    version = :incomingVersion
WHERE order_id = :orderId
  AND version < :incomingVersion;
~~~

Cần xử lý trường hợp version bằng nhau nhưng payload khác, version bị nhảy hoặc event đến sai thứ tự. Partitioning theo entity key giúp giữ thứ tự trong một partition, nhưng không bảo đảm ordering giữa nhiều topics hoặc nhiều producer paths.

**Idempotency và ordering phải được thiết kế riêng.**

## 16. External API: dùng idempotency key

Database transaction của consumer không thể tự atomic với một HTTP service ngoài nếu không có distributed transaction protocol chung.

Ví dụ listener gọi payment provider:

~~~text
1. Consumer gọi POST /charges
2. Provider tạo charge thành công
3. Response bị mất do network timeout
4. Listener không biết charge đã được tạo
5. Kafka redelivers event
6. Consumer gọi POST /charges lần nữa
~~~

Nếu provider hỗ trợ idempotency key, gửi event ID ổn định:

~~~http
POST /charges
Idempotency-Key: evt-8f21
Content-Type: application/json
~~~

Provider phải bảo đảm các request lặp cùng key trong đúng scope trả về cùng kết quả hoặc không tạo side effect lần nữa.

Không chỉ thêm header tên Idempotency-Key là đủ. Cần kiểm tra API provider thực sự hỗ trợ semantics đó, retention window, key scope và cách xử lý cùng key nhưng payload khác.

### 16.1. Không có API idempotency support

Nếu downstream không hỗ trợ idempotency key, các lựa chọn gồm:

- Tạo adapter service có durable request ledger và cơ chế reconciliation.
- Ghi intent vào outbox trong DB rồi worker thực hiện side effect.
- Dùng trạng thái workflow có thể truy vấn kết quả trước khi retry.
- Thiết kế business operation tự idempotent.
- Có manual reconciliation cho các kết quả không xác định.

Không tự retry một lệnh charge/transfer không idempotent sau timeout mà không biết request đầu đã thành công hay chưa.

## 17. Inbox và Outbox kết hợp

**Inbox** bảo vệ consumer side effects khỏi duplicate delivery. **Outbox** bảo vệ việc publish event sau khi database transaction commit.

Nếu consumer cập nhật DB rồi gửi event trực tiếp bằng KafkaTemplate, có thể xảy ra:

- DB commit nhưng publish thất bại: state thay đổi nhưng downstream không nhận event.
- Publish thành công nhưng DB rollback: downstream nhận event cho state chưa commit.

Outbox pattern:

~~~text
BEGIN DB TRANSACTION
  update business tables
  insert outbox event with stable eventId
COMMIT
       |
       v
Outbox relay reads unpublished rows
       |
       v
Publish to Kafka
       |
       v
Mark outbox row published
~~~

Nếu relay crash sau publish nhưng trước khi đánh dấu published, event có thể được publish lại. Consumer downstream vẫn cần idempotency.

| Pattern | Vị trí | Vấn đề giải quyết |
|---|---|---|
| Inbox | Consumer database | Duplicate input không lặp side effect |
| Outbox | Producer database | Business commit và event intent được lưu atomic |
| Kafka transaction | Kafka resources | Atomic Kafka writes và consumed offsets trong transaction |

Không có một pattern đơn lẻ tự biến mọi side effects ở nhiều hệ thống thành exactly-once.

## 18. Kafka transactions và exactly-once semantics

Kafka transactions có thể cung cấp **exactly-once semantics trong phạm vi Kafka** cho luồng consume-process-produce khi được cấu hình đúng: output records và consumed offsets được commit trong cùng Kafka transaction.

Spring Kafka hỗ trợ transactional listener containers và KafkaTransactionManager theo cấu hình tương ứng.

~~~text
Kafka input records
        |
        v
Listener processing
        |
        v
KafkaTemplate sends output
        |
        v
Transaction commits:
  output records + consumed offsets
        |
        v
Downstream read_committed consumer
~~~

Nếu transaction abort, output records không được coi là committed đối với consumers dùng isolation.level=read_committed, và input offsets không được commit trong transaction đó.

### 18.1. Exactly-once không tự bao gồm database và HTTP

Nếu listener ghi PostgreSQL hoặc gọi payment API ngoài Kafka, Kafka transaction không tự rollback các side effects đó.

~~~text
Kafka transaction begins
  |
  +--> update external database
  |
  +--> send Kafka output
  |
  X Kafka transaction aborts
~~~

Kafka output/offset có thể abort nhưng database update ngoài transaction vẫn có thể đã commit.

Cần inbox/idempotent database operation, outbox, API idempotency key hoặc một workflow có reconciliation để bảo vệ các hệ thống ngoài Kafka.

### 18.2. Producer idempotence và transaction khác nhau

Producer idempotence giảm duplicate do protocol retry. Transaction gom nhiều Kafka operations và offsets vào một atomic outcome. Cả hai không thay thế event ID và consumer-side business deduplication khi logical event được phát lại như một record mới.

## 19. Retention của inbox table

Inbox table phải giữ key đủ lâu để chặn mọi lần redelivery/replay có thể xảy ra.

Nếu xóa inbox row sau 24 giờ nhưng operator có thể replay topic từ 30 ngày trước, một event cũ có thể tạo side effect lần nữa.

Retention cần xét:

- Kafka topic retention.
- DLT retention.
- Retry-topic delay.
- Backup/restore và disaster recovery.
- Replay window của operator.
- Consumer group reset policy.
- Event archive và reprocessing process.
- Quy định lưu trữ business/audit data.

Không xóa marker chỉ dựa vào thời gian ngắn hơn average processing. Cần một policy rõ ràng và có thể kiểm toán.

### 19.1. Rebuild projection có chủ đích

Khi muốn rebuild một projection từ đầu, inbox cũ có thể làm consumer bỏ qua tất cả events đã xử lý trước đây.

Có thể dùng một projection generation mới trong handler scope hoặc tạo inbox namespace riêng cho lần rebuild. Sau khi xác minh projection mới, chuyển traffic theo quy trình được kiểm soát.

Không xóa inbox production tùy tiện để cho consumer chạy lại; thao tác đó có thể kích hoạt side effects ngoài ý muốn.

## 20. Payload hash và schema evolution

Nếu lưu payload_hash để phát hiện cùng event ID nhưng payload khác, cần canonicalize payload trước khi hash.

JSON có thể biểu diễn cùng dữ liệu với thứ tự field hoặc whitespace khác nhau. Hash raw serialized bytes có thể khác dù business content tương đương.

Các lựa chọn:

- Hash canonical JSON theo schema.
- Hash một tập business fields ổn định.
- Lưu producer event version và compare fields quan trọng.
- Dùng immutable event envelope có canonical serialization.

Nếu schema version thay đổi nhưng eventId vẫn giữ nguyên, hãy định nghĩa rõ thay đổi đó có được xem là cùng logical event không.

Không dùng payload hash thay cho event ID. Hai event khác nhau có thể có payload giống hệt nhau nhưng vẫn cần được xử lý riêng.

## 21. DLT replay và idempotency key

Khi replay DLT, giữ nguyên event ID gốc nếu mục tiêu là tiếp tục xử lý cùng logical event. Inbox có thể nhận ra event đã xử lý và bỏ qua.

Nếu event trước đó thất bại trước khi business transaction commit, inbox row đã rollback nên replay có thể xử lý lại bình thường.

Nếu operator chủ động muốn áp dụng lại một business operation sau khi đã hoàn tất, cần một workflow/command mới với identity và authorization rõ ràng. Không đổi eventId tùy tiện để vượt qua deduplication vì điều đó có thể nhân đôi ledger/charge/shipment.

### 21.1. DLT headers

Spring Kafka recoverer có thể thêm metadata về original topic, partition, offset, exception và timestamp. Giữ correlation ID và event ID gốc theo policy, nhưng không copy exception payload/stack trace nhạy cảm vào nơi không được bảo vệ.

Khi consumer DLT republish event, cần phân biệt:

- eventId: identity của business event ban đầu.
- recoveryId/attemptId: identity của lần phục hồi.
- correlationId: identity của business flow.
- Kafka offset: vị trí của bản record trên DLT.

## 22. Batch listener và idempotency

Batch listener xử lý nhiều records trong một invocation. Cần quyết định transaction boundary.

**Một transaction cho toàn batch:** nếu một record thất bại, có thể rollback inbox markers và business updates của tất cả records trong batch. Khi retry, những record đã xử lý trước đó có thể được xử lý lại; inbox bảo vệ chúng khi transaction đã commit trước đó, nhưng nếu cùng batch rollback thì mọi thay đổi trong transaction đều rollback.

**Một transaction cho mỗi record:** mỗi event có thể commit độc lập, nhưng container acknowledgment/offset semantics phải phù hợp để không commit vượt qua record chưa xử lý.

~~~text
Batch: [E1, E2, E3]

Per-record transaction:
  E1 -> DB commit
  E2 -> DB commit
  E3 -> failure
  redelivery may include uncommitted offsets

Inbox:
  E1 duplicate -> skip
  E2 duplicate -> skip
  E3 -> retry
~~~

Cấu hình thực tế phụ thuộc listener type, AckMode, transaction manager và error handler. Không giả định một batch method invocation luôn tương ứng một atomic database transaction.

## 23. Idempotent consumer với state machine

Một cách bảo vệ khác là thiết kế state transitions có điều kiện:

~~~sql
UPDATE orders
SET status = 'SHIPPED',
    shipped_at = :shippedAt
WHERE order_id = :orderId
  AND status = 'PAID';
~~~

Lần đầu đổi PAID thành SHIPPED. Lần giao lại khi status đã là SHIPPED sẽ không cập nhật row.

Tuy nhiên, cần phân biệt:

- Không có row updated vì event duplicate hợp lệ.
- Không có row updated vì order chưa ở trạng thái PAID.
- Không có row updated vì order ID không tồn tại.
- Event cũ tới sau event mới.

Không gộp mọi trường hợp thành duplicate. Cần kiểm tra state và version để phân loại đúng outcome.

### 23.1. Monotonic version

Nếu event có aggregateVersion, chỉ áp dụng event mới hơn:

~~~sql
UPDATE order_projection
SET status = :status,
    aggregate_version = :incomingVersion
WHERE order_id = :orderId
  AND aggregate_version < :incomingVersion;
~~~

Event cùng version có thể là redelivery; version thấp hơn là stale; version cao hơn có thể bỏ sót event nếu domain yêu cầu sequence liên tục.

Idempotency key và aggregate version phục vụ hai kiểm soát khác nhau: một cái chống cùng event, một cái bảo vệ ordering/state freshness.

## 24. Idempotency cho email và notification

Email/SMS/push notification là side effects khó rollback. Nếu consumer gọi provider thành công nhưng timeout trước khi nhận response, lần retry có thể gửi lại.

Các lựa chọn:

- Provider hỗ trợ idempotency key dựa trên event ID.
- Lưu notification intent với unique event ID trong DB, rồi worker gửi.
- Lưu provider request ID và trạng thái gửi để reconcile.
- Thiết kế notification service deduplicate ở tầng nhận.
- Chấp nhận at-least-once delivery nếu business cho phép, và làm rõ duplicate handling.

Không đánh dấu inbox event là hoàn tất trước khi notification intent được lưu bền vững. Nếu gửi trực tiếp rồi mới insert inbox, crash có thể gửi lặp.

## 25. Failure matrix: inbox và business transaction

| Điểm lỗi | Inbox row | Business effect | Kafka offset | Hành vi khi giao lại |
|---|---|---|---|---|
| Trước DB transaction | Không có | Không có | Chưa commit | Xử lý từ đầu |
| Sau insert inbox, trước update | Rollback | Rollback | Chưa commit | Insert lại và xử lý |
| Business update thất bại | Rollback | Rollback | Chưa commit | Retry toàn bộ |
| DB commit thành công, trước Kafka commit | Có | Có | Chưa commit | Inbox nhận duplicate, skip effect |
| Kafka offset commit sau DB commit | Có | Có | Đã commit | Không cần giao lại trong flow bình thường |
| Inbox commit riêng trước business update | Có | Có thể không có | Chưa commit | Có nguy cơ skip event bị mất effect |

Dòng cuối giải thích vì sao **không commit inbox marker trong transaction riêng** trước business update.

## 26. Testing idempotency

Một bộ test nên chứng minh cả correctness lẫn các cửa sổ lỗi.

### 26.1. Cùng event được gửi hai lần

1. Gửi eventId=evt-1.
2. Xác nhận business effect được áp dụng.
3. Gửi lại cùng eventId và cùng payload.
4. Xác nhận inbox nhận duplicate.
5. Xác nhận business effect chỉ xuất hiện một lần.

### 26.2. Business failure rollback inbox

1. Gửi event mới.
2. Cho business update ném exception.
3. Xác nhận inbox row không commit.
4. Gửi lại event.
5. Xác nhận lần sau có thể giành inbox key và xử lý thành công.

### 26.3. DB commit trước Kafka offset commit

Mô phỏng crash hoặc ngắt xử lý sau khi DB transaction commit nhưng trước khi offset được xác nhận.

1. DB đã có inbox row và business update.
2. Kafka record được giao lại.
3. Consumer gọi service lần nữa.
4. Inbox insert no-op.
5. Không lặp side effect.
6. Listener hoàn tất và offset tiến.

### 26.4. Concurrent duplicate

Chạy hai invocations song song với cùng handler/eventId. Xác nhận unique constraint chỉ cho một transaction áp dụng business effect.

### 26.5. Các trường hợp bổ sung

- Cùng eventId nhưng payload hash khác.
- Cùng eventId ở hai handler scopes khác nhau.
- DLT replay.
- Projection rebuild generation.
- Batch partial failure.
- API timeout sau khi provider đã thực hiện side effect.
- Event version cũ tới sau version mới.
- Inbox retention và replay ngoài retention window.

## 27. Metrics và logs cho idempotent consumer

Theo dõi các outcome bằng metrics có cardinality thấp:

~~~text
app.kafka.consumer.events
  handler=order-paid
  outcome=processed|duplicate|failed|conflict
~~~

Các metric hữu ích:

- Số event được xử lý lần đầu.
- Số duplicate được bỏ qua.
- Số event ID/payload conflict.
- Business transaction failure.
- Retry count và DLT count.
- Inbox insert latency.
- Database lock/unique conflict latency.
- Consumer lag và processing latency.

Không gắn eventId, orderId, customerId hoặc correlationId vào metric labels. Những ID này phù hợp hơn với logs/traces có kiểm soát.

Structured log có thể ghi:

~~~text
event=consumer_message_outcome
handler=order-paid
eventId=evt-8f21
outcome=duplicate
topic=orders.paid
partition=2
offset=1842
~~~

Nếu eventId hoặc business ID bị coi là dữ liệu nhạy cảm, dùng giá trị đã redact hoặc reference nội bộ phù hợp.

## 28. Runbook khi phát hiện side effect bị lặp

1. Xác định business effect bị lặp: ledger, inventory, email, payment hay state update.
2. Tìm event ID và các Kafka records liên quan.
3. Kiểm tra producer có giữ stable eventId khi retry publish không.
4. Xem consumer có inbox/deduplication key hay không.
5. Xác nhận unique constraint tồn tại trong database.
6. Kiểm tra inbox marker và business update có cùng DB transaction không.
7. Đối chiếu DB commit timestamp với Kafka offset commit/rebalance timeline.
8. Kiểm tra retry topic, DLT replay và operator offset reset.
9. Kiểm tra các consumer replicas có cùng handler scope không.
10. Kiểm tra payload hash nếu cùng eventId nhưng nội dung khác.
11. Với API ngoài, xác minh provider hỗ trợ idempotency key và retention.
12. Dừng retry/replay gây thêm side effects theo incident policy.
13. Reconcile dữ liệu nghiệp vụ đã bị duplicate.
14. Sửa transaction boundary hoặc idempotency implementation.
15. Thêm test cho đúng failure window.
16. Theo dõi duplicate/conflict metrics sau deploy.

Không xóa inbox row hoặc đổi eventId để che duplicate. Trước hết phải xác định effect nào đã xảy ra và dữ liệu nào cần reconcile.

## 29. Những sai lầm thường gặp

**Kafka chỉ giao mỗi record đúng một lần.** Sai; at-least-once có thể giao lại sau crash/rebalance.

**enable.idempotence=true làm consumer idempotent.** Sai; nó bảo vệ producer protocol retries trong phạm vi hỗ trợ.

**Dùng Kafka offset làm event identity.** Sai khi logical event được republish với offset mới.

**Dùng correlationId làm dedup key cho mọi event.** Có thể bỏ qua các event hợp lệ cùng business flow.

**SELECT rồi INSERT là đủ.** Sai; có race condition khi nhiều invocations đồng thời.

**Ghi inbox rồi commit, sau đó mới update business table.** Có nguy cơ đánh dấu event hoàn tất dù side effect thất bại.

**Update business table rồi mới ghi inbox trong transaction khác.** Có nguy cơ lặp side effect khi crash.

**Unique key chỉ theo eventId cho toàn hệ thống.** Có thể chặn nhầm các handlers độc lập.

**Duplicate eventId luôn là duplicate hợp lệ.** Cùng ID nhưng payload khác có thể là producer bug.

**Xóa inbox marker sau vài giờ.** Có thể cho phép replay cũ lặp side effect.

**Kafka EOS bao gồm mọi database/HTTP call.** Không đúng; Kafka transaction không tự atomic với hệ thống ngoài.

**Async task được submit nghĩa record đã xử lý.** Không đúng; cần acknowledgment gắn với business completion.

**DLT replay phải tạo eventId mới.** Thường sai nếu mục tiêu là tiếp tục xử lý cùng logical event.

**Idempotency giải quyết ordering.** Không; cần version/state transition riêng.

## 30. Checklist triển khai

- [ ] Producer tạo eventId ổn định cho logical event.
- [ ] Consumer chọn idempotency key đúng scope.
- [ ] Database có unique constraint cho inbox key.
- [ ] Inbox insert và business changes nằm trong cùng DB transaction.
- [ ] Duplicate path bỏ qua side effect nhưng vẫn hoàn tất listener theo policy.
- [ ] Business failure rollback cả inbox marker và business update.
- [ ] Phát hiện cùng eventId nhưng payload khác.
- [ ] Có retention policy phù hợp replay/DLT window.
- [ ] Dùng idempotency key cho external API nếu provider hỗ trợ.
- [ ] Có outbox khi cần publish event sau DB commit.
- [ ] Hiểu rõ Kafka transaction chỉ bao phủ Kafka resources.
- [ ] Xử lý batch transaction/ack semantics rõ ràng.
- [ ] Phân biệt idempotency với ordering/version checks.
- [ ] Có metrics processed/duplicate/failed/conflict.
- [ ] Không dùng event ID làm metric label.
- [ ] Test duplicate, rollback, crash window, concurrency và DLT replay.
- [ ] Có runbook reconciliation khi side effect đã bị lặp.

## 31. Tài liệu tham khảo

- Apache Kafka Documentation — Design: https://kafka.apache.org/documentation/#design
- Apache Kafka Documentation — Producer Configs (enable.idempotence): https://kafka.apache.org/documentation/#producerconfigs_enable.idempotence
- Spring for Apache Kafka Reference — Transactions: https://docs.spring.io/spring-kafka/reference/kafka/transactions.html
- Spring for Apache Kafka Reference — Exactly Once Semantics: https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html
- Spring for Apache Kafka Reference — Error Handling: https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html

Đối chiếu đúng Spring Kafka/Kafka client version và database dialect trước khi áp dụng code mẫu, đặc biệt ở phần transaction manager, acknowledgment, batch listener và SQL upsert.

## 32. Ghi nhớ

**Idempotent consumer** bảo đảm cùng một logical event có thể được giao nhiều lần mà business side effect không bị áp dụng lặp. Kafka at-least-once có thể redeliver sau khi database commit nhưng trước khi offset commit, nên consumer phải có stable event ID và một cơ chế deduplication bền vững.

Với database side effects, **Inbox pattern** dùng unique constraint trên handler scope và event ID; inbox marker cùng business update phải commit trong **cùng một DB transaction**. Khi transaction rollback, cả hai cùng rollback; khi DB commit rồi Kafka redeliver, inbox nhận duplicate và consumer bỏ qua side effect.

Với HTTP/payment/email bên ngoài, dùng idempotency key được provider hỗ trợ hoặc workflow/outbox/reconciliation phù hợp. Kafka producer idempotence và Kafka transactions rất hữu ích nhưng không tự bao phủ database hay external APIs. Một thiết kế tin cậy cần thêm ordering/version checks, retention policy, concurrency safety, DLT replay handling, metrics và tests cho các failure windows.

