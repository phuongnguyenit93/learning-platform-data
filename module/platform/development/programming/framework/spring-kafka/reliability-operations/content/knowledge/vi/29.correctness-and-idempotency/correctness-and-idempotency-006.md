# Tác vụ ngoài transaction

Một Kafka consumer thường không chỉ đọc record rồi cập nhật offset. Nó có thể gọi payment gateway, gửi email, ghi database, tạo file, cập nhật object storage hoặc gọi một service khác. Những thao tác này nằm ngoài transaction của Kafka. Nếu side effect thành công nhưng process dừng trước khi offset được commit, Kafka có thể giao lại record và consumer thực hiện side effect lần nữa.

Đây là ranh giới quan trọng của **tính đúng và idempotency**: Kafka transaction có thể phối hợp việc đọc/ghi dữ liệu Kafka trong một transaction, nhưng không tự rollback một HTTP request đã tới hệ thống ngoài, email đã gửi hoặc file đã được ghi. Muốn vận hành đúng, ứng dụng phải thiết kế cho các khoảng thời gian crash, timeout không rõ kết quả, retry và replay.

Bài học thuộc chương **Tính đúng và idempotency** của Spring Kafka Reliability Operations. Nội dung tập trung vào cách xử lý **tác vụ ngoài transaction** trong Spring Kafka: xác định ranh giới nguyên tử, thiết kế idempotency key, dùng inbox/outbox, tách side effect khỏi listener khi phù hợp, phối hợp retry/DLT, xây dựng saga/compensation và kiểm thử các tình huống lỗi.

## 1. Transaction Kafka bảo vệ điều gì?

Với Kafka transaction, producer có thể gửi nhiều record và commit chúng như một đơn vị. Trong mô hình consume-process-produce, Spring Kafka có thể đưa offset của consumer vào cùng Kafka transaction với output record. Consumer dùng isolation level phù hợp, thường là `read_committed`, chỉ thấy các record transactional đã commit.

~~~text
Kafka input topic
      |
      v
Consumer poll
      |
      v
Listener xử lý
      |
      +---- KafkaTemplate.send(output)
      |
      v
Kafka transaction commit
      |
      +---- Output records được commit
      |
      +---- Input offsets được commit
~~~

Nếu transaction abort, output transactional không được consumer `read_committed` coi là đã commit và input offsets trong transaction cũng không tiến theo transaction đó. Record đầu vào có thể được giao lại.

Đó là bảo đảm **bên trong Kafka**. Transaction không tự bao phủ:
- SQL update trên database không tham gia cùng một distributed transaction.
- HTTP request tới payment provider hoặc REST service.
- Email, SMS, push notification.
- File trên filesystem hoặc object storage.
- Tác vụ tạo invoice, gọi hệ thống kế toán hoặc thiết bị bên ngoài.

Ví dụ:

~~~text
Kafka listener
    |
    +-- Kafka transaction đang mở
    |
    +-- HTTP POST /payments -> provider charge thành công
    |
    +-- Kafka transaction abort
             |
             v
       Input record được giao lại
             |
             v
       HTTP POST /payments lần nữa
             |
             v
       Nguy cơ charge hai lần
~~~

Kafka có thể rollback output record và offset, nhưng không thể yêu cầu payment provider hoàn tác một khoản charge chỉ bằng cách abort Kafka transaction.

## 2. Vì sao side effect có thể bị thực hiện nhiều lần?

Giả sử listener đọc event `PaymentRequested`, gọi API thanh toán và sau đó commit offset:

~~~text
1. poll record E
2. gọi payment API
3. payment API trả SUCCESS
4. process crash
5. Kafka offset chưa commit
6. consumer khởi động lại và đọc E
7. gọi payment API lần nữa
~~~

Đây là cửa sổ lỗi phổ biến. Consumer có thể đã hoàn tất side effect nhưng chưa ghi nhận tiến độ trong Kafka. Với delivery at-least-once, record được giao lại là hành vi hợp lệ.

Một timeout còn khó hơn:

~~~text
Consumer gửi HTTP request
       |
       v
Provider thực hiện charge thành công
       |
       v
Response bị mất hoặc client timeout
       |
       v
Consumer không biết kết quả thật
       |
       v
Retry request
~~~

Timeout chỉ nói rằng client không nhận được response đúng hạn; nó **không chứng minh server chưa thực hiện thao tác**. Nếu retry với một request identity mới, side effect có thể xảy ra hai lần.

Thiết kế phải xử lý cả:
- Crash sau khi side effect thành công nhưng trước khi offset commit.
- Timeout sau khi server đã nhận và xử lý request.
- Consumer rebalance trong khi listener đang chạy.
- Retry sau lỗi tạm thời.
- DLT replay nhiều giờ hoặc nhiều ngày sau.
- Operator chạy lại cùng event để phục hồi dữ liệu.

## 3. Phân biệt delivery guarantee và side-effect guarantee

| Khái niệm | Điều nó bảo đảm | Điều nó không tự bảo đảm |
|---|---|---|
| At-most-once | Record không được xử lý lại theo chính sách commit trước xử lý. | Có thể mất record nếu xử lý thất bại sau commit. |
| At-least-once | Record chưa được ghi nhận thành công có thể được giao lại. | Side effect ngoài Kafka có thể bị lặp. |
| Kafka transactions / exactly-once processing trong Kafka | Phối hợp output Kafka records và input offsets trong transaction Kafka theo cấu hình. | Không tự tạo exactly-once cho HTTP, email, database hoặc filesystem. |
| Idempotent side effect | Nhiều lần yêu cầu cùng logical operation tạo một kết quả nghiệp vụ duy nhất. | Không tự bảo đảm record được giao đúng thứ tự hoặc mọi request cuối cùng thành công. |
| Effectively-once business outcome | Retry/replay có thể xảy ra nhưng kết quả nghiệp vụ được deduplicate hoặc đối soát. | Không phải phép màu của broker; cần thiết kế và lưu trạng thái bền vững. |

Trong hệ thống phân tán, từ “exactly once” phải luôn gắn với **ranh giới cụ thể**. Một pipeline Kafka-to-Kafka có thể có exactly-once semantics trong phạm vi Kafka transaction. Một workflow gọi payment API và gửi email thường cần idempotency, outbox/inbox hoặc saga để đạt business outcome effectively-once.

## 4. Xác định ranh giới transaction trong listener

Ví dụ listener gọi database và API bên ngoài:

~~~java
@KafkaListener(topics = "payments.requested")
public void handle(PaymentRequested event) {
    paymentRepository.markProcessing(event.paymentId());

    paymentGateway.charge(
            event.paymentId(),
            event.amount());

    paymentRepository.markPaid(event.paymentId());
}
~~~

Đoạn code này có thể có nhiều rủi ro:
- Nếu DB update đầu tiên commit nhưng HTTP call thất bại, trạng thái có thể dở dang.
- Nếu payment provider charge thành công nhưng response timeout, consumer không biết kết quả.
- Nếu process crash sau charge nhưng trước offset commit, event có thể được giao lại.
- Nếu listener transaction chỉ là Kafka transaction, hai DB update không được Kafka rollback.
- Nếu DB transaction được mở quanh cả lời gọi HTTP, connection/lock có thể bị giữ trong khi network chậm; rollback DB vẫn không đảo ngược charge đã thực hiện.

Cần xác định rõ **transaction nào đang bảo vệ từng thay đổi**. Một method có annotation `@Transactional` không làm mọi resource mà method gọi trở thành một transaction nguyên tử. Transaction manager chỉ quản lý resource mà nó hỗ trợ và đã được enlist đúng cách.

## 5. Đừng giữ database transaction mở trong lúc chờ HTTP

Một cách dễ viết nhưng nguy hiểm:

~~~java
@Transactional
public void process(PaymentRequested event) {
    paymentRepository.markProcessing(event.paymentId());

    paymentGateway.charge(event.paymentId(), event.amount());

    paymentRepository.markPaid(event.paymentId());
}
~~~

Nếu API ngoài mất 20 giây, DB connection và transaction có thể bị giữ trong 20 giây. Hậu quả:
- Connection pool cạn khi traffic tăng.
- Row/table locks kéo dài.
- Deadlock hoặc lock contention.
- Transaction timeout.
- Retry tạo thêm tải lên DB và provider.
- Rollback DB không hoàn tác side effect đã thực hiện ở provider.

Với side effect không thể rollback, thường nên tách workflow thành các bước có trạng thái bền vững: ghi nhận ý định, gọi provider với idempotency key, rồi ghi kết quả. Cách tách này làm các khoảng crash có thể quan sát và phục hồi.

## 6. Idempotency key cho API bên ngoài

Nếu provider hỗ trợ idempotency, gửi một **key ổn định cho cùng logical operation** ở mọi lần retry.

~~~java
public PaymentResult charge(PaymentRequested event) {
    String idempotencyKey = event.paymentId();

    return paymentClient.charge(
            event.paymentId(),
            event.amount(),
            idempotencyKey);
}
~~~

Ví dụ HTTP:

~~~http
POST /v1/payments
Idempotency-Key: payment-4821
Content-Type: application/json

{
  "paymentId": "payment-4821",
  "amount": 125000
}
~~~

Provider lưu kết quả gắn với key và trả lại kết quả tương ứng khi nhận request lặp theo contract của họ. Cần đọc rõ:
- Key được giữ trong bao lâu?
- Cùng key nhưng payload khác thì provider xử lý ra sao?
- Hai request đồng thời cùng key có được serialize/deduplicate không?
- Response được replay có giống response gốc không?
- Key có scope theo merchant/account/endpoint không?
- Sau khi key hết retention, retry cũ có thể tạo charge mới không?

**Không tạo UUID mới cho mỗi lần retry.** Key phải được sinh từ event hoặc logical operation và được lưu bền vững để mọi lần giao lại dùng cùng giá trị.

Một event ID chung có thể chưa đủ nếu một event tạo nhiều side effect. Ví dụ một order có charge, reserve inventory và issue invoice; cần idempotency key riêng theo operation, chẳng hạn `eventId + ":charge"` và `eventId + ":reserve"`. Mỗi side effect có trạng thái và quy tắc dedupe riêng.

## 7. Khi provider không hỗ trợ idempotency

Không phải API bên ngoài nào cũng có idempotency key. Khi đó có thể:
- Dùng một external reference ổn định mà provider cho phép tra cứu.
- Tạo request record trước khi gọi provider và ghi trạng thái `PENDING`.
- Sau timeout, truy vấn provider theo reference trước khi quyết định gửi lại.
- Đối soát định kỳ các request không rõ kết quả.
- Chuyển trường hợp không thể xác định sang trạng thái `UNKNOWN` và cần xử lý có kiểm soát.
- Thiết lập quy trình manual review cho side effect không thể tự động xác nhận.

Không retry mù một lệnh không idempotent sau timeout. Nếu provider không cho tra cứu theo reference và cũng không hỗ trợ deduplication, ứng dụng không thể tự chứng minh request trước chưa được thực hiện. Đây là giới hạn của contract bên ngoài và cần được xử lý bằng quy trình nghiệp vụ.

## 8. Dùng inbox pattern để deduplicate event trong database

Khi consumer cập nhật database, một cách phổ biến là ghi **inbox/processed-event marker** trong cùng DB transaction với business update.

Bảng ví dụ:

~~~sql
CREATE TABLE processed_event (
    event_id       VARCHAR(100) PRIMARY KEY,
    processed_at   TIMESTAMP NOT NULL
);
~~~

Service xử lý:

~~~java
@Service
public class OrderProjectionService {

    private final JdbcTemplate jdbc;

    public OrderProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean applyOnce(OrderCreated event) {
        int inserted = jdbc.update("""
            INSERT INTO processed_event(event_id, processed_at)
            VALUES (?, CURRENT_TIMESTAMP)
            ON CONFLICT (event_id) DO NOTHING
            """,
            event.eventId());

        if (inserted == 0) {
            // Event đã được xử lý trong transaction trước.
            return false;
        }

        jdbc.update("""
            UPDATE order_projection
               SET status = ?, total_amount = ?
             WHERE order_id = ?
            """,
            "CREATED",
            event.totalAmount(),
            event.orderId());

        return true;
    }
}
~~~

Đây là ví dụ SQL theo PostgreSQL (`ON CONFLICT`). Với database khác, dùng cú pháp insert-if-absent hoặc unique constraint tương ứng. Cần bảo đảm marker và business update dùng **cùng database transaction và cùng transaction manager**.

Listener:

~~~java
@Component
public class OrderCreatedListener {

    private final OrderProjectionService service;

    public OrderCreatedListener(OrderProjectionService service) {
        this.service = service;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-projection-v1"
    )
    public void consume(OrderCreated event) {
        service.applyOnce(event);
    }
}
~~~

Nếu DB transaction commit thành công nhưng Kafka offset commit thất bại, record được giao lại. Lần sau unique constraint khiến `inserted` bằng 0, business update không chạy lần nữa. Nếu DB transaction rollback, cả inbox marker và business update cùng rollback; lần giao lại có thể thực hiện lại.

Điều kiện quan trọng:
- `eventId` ổn định xuyên retry/replay.
- Unique constraint nằm trong DB, không chỉ kiểm tra bằng SELECT rồi INSERT vì race condition.
- Inbox marker và business state được commit nguyên tử.
- Offset được commit sau khi listener xử lý thành công theo ack mode phù hợp.
- Retention inbox phải đủ dài so với khoảng replay có thể xảy ra.

Inbox không tự deduplicate một HTTP side effect được gọi trước khi transaction DB commit. Với side effect ngoài DB, cần idempotency key hoặc outbox workflow.

## 9. Tại sao SELECT rồi INSERT không đủ để chống trùng?

Cách viết dễ mắc race:

~~~java
if (!repository.existsByEventId(event.eventId())) {
    repository.save(new ProcessedEvent(event.eventId()));
    updateBusinessState(event);
}
~~~

Hai consumer/process có thể cùng kiểm tra trước khi bên nào insert:

~~~text
Consumer A: SELECT -> chưa tồn tại
Consumer B: SELECT -> chưa tồn tại
Consumer A: INSERT
Consumer B: INSERT
Consumer A: thực hiện side effect
Consumer B: thực hiện side effect
~~~

Unique constraint sẽ chặn một insert trùng, nhưng ứng dụng phải xử lý duplicate-key/insert result và **chỉ side effect khi insert thắng**. Cần transaction bao trọn marker và thay đổi DB. Trong nhiều hệ thống, câu lệnh insert-if-absent là cách rõ ràng hơn so với kiểm tra trước.

Nếu một event cần xử lý từng phần, không dùng một marker chung đánh dấu toàn bộ event đã hoàn tất trước khi mọi bước xong. Có thể lưu trạng thái từng operation hoặc dùng state machine có transition rõ ràng.

## 10. Outbox pattern cho DB update và Kafka publish

Một tình huống khác: service cập nhật DB rồi publish event Kafka. Nếu hai thao tác không cùng transaction nguyên tử, có thể xảy ra:
- DB commit thành công nhưng Kafka send thất bại: dữ liệu DB thay đổi mà event không được phát.
- Kafka send thành công nhưng DB rollback: event đã phát dù thay đổi DB không tồn tại.

**Transactional outbox** giải quyết dual-write bằng cách ghi business state và outbox row trong cùng một DB transaction:

~~~text
Application transaction
       |
       +--> UPDATE orders
       |
       +--> INSERT outbox_event
       |
       v
Database COMMIT
       |
       v
Outbox publisher / CDC
       |
       v
Kafka topic
~~~

Schema đơn giản:

~~~sql
CREATE TABLE outbox_event (
    event_id       VARCHAR(100) PRIMARY KEY,
    aggregate_id   VARCHAR(100) NOT NULL,
    event_type     VARCHAR(200) NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP NULL
);
~~~

Service:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    @Transactional
    public void createOrder(CreateOrder command) {
        Order order = orders.create(command);

        OrderCreated event = new OrderCreated(
                command.eventId(),
                order.getId(),
                order.getTotal());

        outbox.insert(event.eventId(), order.getId(),
                "OrderCreated", serialize(event));
    }
}
~~~

Nếu transaction DB rollback, cả order và outbox row rollback. Nếu commit thành công, publisher có thể đọc outbox và gửi Kafka record. Có thể triển khai publisher polling có lock/claim, hoặc CDC như Debezium tùy kiến trúc.

Outbox publisher vẫn có thể crash sau khi Kafka publish thành công nhưng trước khi đánh dấu row đã publish. Khi chạy lại, nó có thể gửi event lần nữa. Vì vậy downstream vẫn cần idempotency/inbox; outbox **giải quyết mất event do dual-write**, không tự biến việc publish thành exactly-once end-to-end.

## 11. Inbox và outbox kết hợp

Một chuỗi xử lý phổ biến:

~~~text
Service A:
  DB business update + outbox row
       |
       v
  Outbox publisher -> Kafka
                         |
                         v
Service B:
  Kafka consumer
       |
       v
  DB transaction:
    insert inbox(event_id)
    update business state
       |
       v
  commit DB
       |
       v
  Kafka offset commit
~~~

- Outbox bảo đảm thay đổi DB có event tương ứng để publish.
- Inbox deduplicate event khi consumer nhận lại.
- Kafka offset commit sau xử lý giúp crash có thể gây redelivery nhưng không lặp business update trong DB.
- Event ID nối các bước qua service.

Đây là mô hình **effectively-once business processing** trong phạm vi state DB được bảo vệ bởi inbox. Nếu service B còn gọi payment API hoặc gửi email, cần một outbox riêng cho command đó hoặc idempotency ở provider.

## 12. Side effect ngoài DB: ghi intent trước, thực hiện sau

Đối với payment, email, shipping hoặc API bên ngoài, có thể ghi một **command/outbox intent** trong DB transaction, rồi worker riêng thực hiện.

~~~text
Kafka listener
     |
     v
DB transaction:
  - inbox(event_id)
  - update order state
  - insert payment_command
     |
     v
DB commit
     |
     v
Payment worker reads payment_command
     |
     v
Call provider with stable idempotency key
     |
     v
Persist provider result / command status
~~~

Lợi ích:
- Listener không giữ Kafka consumer thread trong khi chờ provider.
- Intent được lưu bền vững và có thể tiếp tục sau restart.
- Có trạng thái rõ ràng cho pending, in-flight, succeeded, failed hoặc unknown.
- Worker có thể áp dụng rate limit, retry và concurrency riêng.
- Business state và command intent được commit cùng một DB transaction.

Tuy nhiên, worker vẫn phải xử lý cửa sổ: provider thực hiện thành công nhưng worker crash trước khi cập nhật command status. Khi retry, phải dùng cùng idempotency key hoặc tra cứu provider theo external reference. Nếu không có hai khả năng đó, cần reconciliation/manual review.

## 13. Mô hình trạng thái cho side effect

Một command ngoài transaction nên có trạng thái tường minh thay vì chỉ một boolean `done`.

~~~text
PENDING
   |
   v
IN_FLIGHT
   |
   +------ provider confirms success ------> SUCCEEDED
   |
   +------ definite retryable failure -----> RETRY_WAIT
   |                                            |
   |                                            v
   |                                        IN_FLIGHT
   |
   +------ permanent business failure ------> FAILED
   |
   +------ timeout / result unknown --------> UNKNOWN
                                                |
                                                v
                                          RECONCILING
                                           /       \
                                          v         v
                                    SUCCEEDED     RETRY_SAFE
~~~

Các trạng thái gợi ý:

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| `PENDING` | Intent đã ghi, chưa gửi. | Worker có thể claim. |
| `IN_FLIGHT` | Một worker đang thực hiện. | Lease/claim ngăn worker khác xử lý đồng thời. |
| `RETRY_WAIT` | Lỗi chắc chắn có thể thử lại sau backoff. | Retry sau thời điểm cho phép. |
| `SUCCEEDED` | Có bằng chứng provider đã hoàn tất. | Không gửi lại. |
| `FAILED` | Lỗi nghiệp vụ/permanent đã xác định. | Chờ xử lý hoặc thông báo nghiệp vụ. |
| `UNKNOWN` | Timeout hoặc mất kết nối khiến kết quả không rõ. | Query/reconcile trước khi gửi lại. |

Một trạng thái `IN_FLIGHT` cần lease/timeout để worker khác có thể tiếp quản sau crash. Lease hết hạn không chứng minh request cũ chưa được provider xử lý; worker mới vẫn phải dùng cùng idempotency key hoặc kiểm tra trạng thái từ provider.

## 14. Retry an toàn cho tác vụ ngoài transaction

Retry cần dựa trên loại lỗi:

| Loại lỗi | Ví dụ | Chính sách |
|---|---|---|
| Transient và chắc chắn chưa thực hiện | DNS/connect failure trước khi request được gửi. | Có thể retry với backoff. |
| Transient nhưng kết quả không rõ | Read timeout sau khi provider nhận request. | Query bằng idempotency key/reference hoặc retry cùng key. |
| Permanent/business | Thẻ bị từ chối, địa chỉ không hợp lệ. | Không retry vô hạn; ghi trạng thái nghiệp vụ và xử lý phù hợp. |
| Authentication/configuration | Credential hết hạn, ACL denied. | Dừng hoặc retry chậm sau khi cấu hình được sửa; cảnh báo owner. |
| Rate limited | HTTP 429 hoặc quota response. | Tôn trọng `Retry-After` nếu có, backoff và giới hạn concurrency. |

Dùng exponential backoff có jitter để nhiều worker không retry cùng thời điểm:

~~~java
Duration delayForAttempt(int attempt) {
    long baseMillis = 500L;
    long capMillis = 60_000L;

    long exponential = Math.min(
            capMillis,
            baseMillis * (1L << Math.min(attempt, 10)));

    long jitter = ThreadLocalRandom.current()
            .nextLong(Math.max(1L, exponential / 2), exponential + 1);

    return Duration.ofMillis(jitter);
}
~~~

Đây là ví dụ minh họa; code production cần xử lý overflow, giới hạn attempt, clock và policy của provider. Retry không được vượt quá business deadline hoặc thời gian provider giữ idempotency key nếu điều đó làm request cũ trở nên nguy hiểm.

## 15. Retry topic và DLT không làm side effect tự idempotent

Spring Kafka có thể dùng `DefaultErrorHandler`, recoverer hoặc `@RetryableTopic` để retry và chuyển record lỗi sang DLT. Cơ chế này điều khiển việc giao lại Kafka record, không biết một payment/email/API call đã thành công trước khi exception xảy ra hay chưa.

Ví dụ:

~~~text
Kafka record E
   |
   v
Listener calls external API
   |
   +-- API succeeds, response lost
   |
   v
Listener throws timeout
   |
   v
Retry record
   |
   v
External API called again
~~~

Với retry topic:
- Giữ event ID và idempotency key ổn định.
- Không tạo request identity mới ở mỗi attempt.
- Log attempt và trạng thái side effect.
- Xử lý DLT replay bằng cùng business dedupe key.
- Đảm bảo retention inbox/provider idempotency đủ dài.
- Phân biệt lỗi Kafka serialization/consumer với lỗi side effect bên ngoài.

Một record vào DLT không nhất thiết side effect chưa từng xảy ra. Trước khi replay, phải kiểm tra trạng thái provider hoặc command table.

## 16. Compensation và Saga

Có những workflow gồm nhiều side effect không thể commit chung:

~~~text
Create order
    |
    v
Reserve inventory
    |
    v
Charge payment
    |
    v
Arrange shipment
~~~

Nếu bước arrange shipment thất bại sau khi payment đã thành công, không thể rollback tất cả bằng Kafka transaction. Có thể dùng **Saga**: mỗi bước có một hành động bù trừ (compensating action) theo quy tắc nghiệp vụ.

~~~text
Reserve inventory
       |
       v
Charge payment
       |
       v
Shipment fails
       |
       v
Refund payment
       |
       v
Release inventory
       |
       v
Order = COMPENSATED / CANCELLED
~~~

Compensation không phải rollback kỹ thuật:
- Refund là một giao dịch mới, có thể thất bại hoặc chậm.
- Release inventory có thể không còn khả dụng nếu hàng đã chuyển.
- Email đã gửi không thể thu hồi; có thể gửi thông báo đính chính.
- Mỗi compensation cũng cần idempotency key và trạng thái riêng.

Saga cần lưu trạng thái workflow bền vững, timeout từng bước, retry/compensation policy và quy trình manual intervention khi bù trừ thất bại. Không giả định compensation luôn thành công hoặc có thể đảo ngược hoàn toàn.

## 17. File và object storage cũng là side effect

Ghi file trong listener có cùng vấn đề crash window:

~~~text
Write object successfully
       |
       v
Process crashes before Kafka offset commit
       |
       v
Record redelivered
       |
       v
Write object again
~~~

Một số kỹ thuật:
- Dùng object key deterministic từ event ID/aggregate ID nếu cùng event phải cập nhật cùng object.
- Ghi file tạm rồi atomic rename khi filesystem hỗ trợ.
- Dùng conditional write/version precondition khi object store hỗ trợ.
- Lưu checksum và metadata để xác nhận object hiện tại tương ứng nội dung nào.
- Lưu trạng thái command trong DB/inbox để biết thao tác đã hoàn tất.
- Với file lớn, lưu intent và xử lý bằng worker có lease thay vì giữ listener thread.

Deterministic key không tự giải quyết mọi race: hai worker có thể cùng ghi, và ghi đè object cũ có thể không an toàn. Cần quy tắc versioning, conditional write và ownership phù hợp.

## 18. Email, SMS và notification

Email thường không có thao tác “undo”. Nếu consumer gửi email rồi crash trước offset commit, record có thể được giao lại và gửi email thứ hai.

Các cách giảm rủi ro:
- Dùng notification ID ổn định.
- Lưu notification intent và trạng thái gửi.
- Dùng provider idempotency nếu có.
- Nếu provider không hỗ trợ, tra cứu delivery status theo provider message ID/reference nếu API cho phép.
- Thiết kế nội dung thông báo chịu được duplicate hoặc có cơ chế suppression.
- Đối soát các trạng thái không rõ kết quả thay vì retry mù.

Một inbox marker DB chỉ bảo vệ việc ghi marker/business state trong DB. Nếu marker được commit trước khi gửi email, crash giữa marker và email có thể làm email bị mất. Nếu gửi email trước rồi mới commit marker, crash có thể gửi trùng. Outbox notification giúp lưu intent bền vững; worker và provider idempotency xử lý phần gửi.

## 19. Phối hợp DB transaction và Kafka transaction

Spring Kafka hỗ trợ Kafka transaction manager và transaction synchronization với một số transaction manager khác. Điều đó hữu ích để phối hợp thứ tự commit, nhưng **không biến database và Kafka thành một distributed atomic transaction** chỉ bằng cách bật hai transaction manager.

Có thể xảy ra:
- DB transaction commit thành công, Kafka commit thất bại: database đã đổi nhưng Kafka offset/output chưa commit; record có thể được giao lại.
- Kafka commit thành công trước khi DB commit hoàn tất (nếu cấu hình thứ tự không phù hợp): consumer có thể tiến offset trong khi DB update chưa bền vững.
- Một resource commit xong, resource còn lại lỗi: không có rollback toàn cục tự động cho resource đã commit.

Spring transaction synchronization có thể điều phối thứ tự commit và rollback callback theo cấu hình/version. Cần hiểu transaction manager chính, secondary manager, listener container transaction và acknowledgment mode thực tế. **Đừng gọi đây là XA/2PC hoặc exactly-once DB+Kafka nếu không có distributed transaction protocol thực sự.**

Một lựa chọn thường dễ phục hồi là:
1. DB transaction ghi business state + inbox/outbox.
2. Commit DB.
3. Kafka offset được commit theo cấu hình sau listener success.
4. Nếu offset commit thất bại, redelivery được inbox deduplicate.
5. Outbox publisher phát event và downstream cũng idempotent.

Đây là thiết kế rõ ràng vì mỗi bước có durable state và retry semantics.

## 20. Chọn chiến lược theo loại side effect

| Side effect | Mẫu thiết kế thường phù hợp | Cần đặc biệt chú ý |
|---|---|---|
| DB update trong cùng database | Inbox marker + business update trong một DB transaction. | Unique constraint, commit ordering, retention. |
| DB update rồi publish Kafka | Transactional outbox + downstream inbox. | Outbox publisher có thể gửi trùng. |
| HTTP payment/booking API | Provider idempotency key + durable command state. | Timeout ambiguous, key retention, reconciliation. |
| Email/SMS | Notification outbox + provider dedupe/reference. | Không thể undo; delivery status có thể không rõ. |
| File/object storage | Deterministic key + conditional write/version/checksum. | Concurrent writers và overwrite semantics. |
| Nhiều bước nghiệp vụ xuyên service | Saga + state machine + compensation. | Compensation có thể thất bại; cần manual recovery. |
| Gửi dữ liệu Kafka sang Kafka | Kafka transaction khi cần atomic consume-process-produce. | Chỉ trong ranh giới Kafka và cấu hình isolation/transaction phù hợp. |

Không có một pattern duy nhất cho mọi tác vụ. Chọn theo khả năng của external system, mức độ không thể đảo ngược, yêu cầu audit và chi phí vận hành.

## 21. Ví dụ: consumer ghi intent thanh toán rồi worker gọi provider

Listener chỉ ghi inbox và payment command trong DB:

~~~java
@Service
public class PaymentCommandService {

    private final JdbcTemplate jdbc;

    public PaymentCommandService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void accept(PaymentRequested event) {
        int inserted = jdbc.update("""
            INSERT INTO processed_event(event_id, processed_at)
            VALUES (?, CURRENT_TIMESTAMP)
            ON CONFLICT (event_id) DO NOTHING
            """, event.eventId());

        if (inserted == 0) {
            return;
        }

        jdbc.update("""
            INSERT INTO payment_command(
                command_id, payment_id, amount, status, idempotency_key
            )
            VALUES (?, ?, ?, 'PENDING', ?)
            ON CONFLICT (command_id) DO NOTHING
            """,
            event.eventId() + ":charge",
            event.paymentId(),
            event.amount(),
            event.paymentId());
    }
}
~~~

Worker xử lý command:

~~~java
public void execute(PaymentCommand command) {
    PaymentResult result = paymentProvider.charge(
            command.paymentId(),
            command.amount(),
            command.idempotencyKey());

    commandRepository.markSucceeded(
            command.commandId(),
            result.providerReference());
}
~~~

Ví dụ giả định provider hỗ trợ idempotency key và command repository có transaction/state transition phù hợp. Worker cần claim command an toàn để tránh nhiều instance cùng thực hiện; kể cả claim thành công, lease hết hạn sau crash vẫn có thể khiến command được thử lại. Provider idempotency key là lớp bảo vệ cuối cho trường hợp provider đã charge nhưng worker chưa ghi được kết quả.

## 22. Concurrency và claim command

Nếu nhiều worker cùng đọc bảng command, một câu SELECT pending rồi UPDATE sau đó không đủ ngăn race. Có thể dùng atomic claim/lease theo khả năng database:

~~~sql
UPDATE payment_command
   SET status = 'IN_FLIGHT',
       lease_owner = :worker_id,
       lease_until = :lease_until
 WHERE command_id = :command_id
   AND (
       status IN ('PENDING', 'RETRY_WAIT')
       OR (status = 'IN_FLIGHT' AND lease_until < CURRENT_TIMESTAMP)
   );
~~~

Câu SQL minh họa; production cần transaction/locking, kiểm tra row count, lease duration và database dialect phù hợp.

Worker chỉ xử lý khi update claim đúng một row. Lease ngăn hai worker cùng claim bình thường, nhưng không thể thu hồi request HTTP đang chạy ở worker cũ chỉ vì lease hết hạn. Nếu provider xử lý lâu hơn lease, worker mới có thể bắt đầu lần nữa. Vì vậy:
- Lease phải được gia hạn khi tác vụ dài.
- HTTP timeout và lease cần được phối hợp.
- Mọi attempt dùng cùng idempotency key.
- Trạng thái `UNKNOWN` cần reconcile trước khi gửi lại nếu provider không dedupe.

## 23. Quan sát và audit tác vụ ngoài transaction

Một side effect cần log/metric đủ để trả lời “đã gửi chưa?”, “kết quả có rõ không?” và “retry có an toàn không?”.

Structured log gợi ý:

~~~json
{
  "event": "external_effect_attempt",
  "eventId": "evt-4821",
  "commandId": "evt-4821:charge",
  "effectType": "PAYMENT_CHARGE",
  "provider": "payment-gateway",
  "idempotencyKeyRef": "payment-4821",
  "attempt": 2,
  "status": "UNKNOWN",
  "reason": "read-timeout"
}
~~~

Đây là schema minh họa. Không log idempotency key nếu nó được coi là bí mật hoặc provider cho phép dùng nó như token truy cập; có thể log một reference/hash an toàn.

Các metric hữu ích:
- Số command pending và tuổi command lâu nhất.
- Số side-effect attempt theo provider và outcome.
- Retry rate, timeout rate và unknown-result count.
- Thời gian từ intent creation tới completion.
- Inbox duplicate count.
- Outbox backlog và publish failure.
- Compensation pending/failed.
- DLT ingress và replay count.

Không đưa event ID, payment ID hoặc idempotency key vào metric labels có cardinality không giới hạn. Dùng logs/traces để điều tra từng operation; metrics dùng labels có miền giá trị nhỏ.

## 24. Runbook: timeout khi gọi external API

Giả sử consumer gọi payment provider và nhận read timeout.

**Bước 1 — Không suy luận thất bại từ timeout.** Ghi nhận request đã được gửi hay chưa, timeout ở connect, write hay response-read.

**Bước 2 — Xác định logical operation.** Tìm event ID, payment ID, command ID và idempotency key ổn định. Kiểm tra attempt trước đã dùng key nào.

**Bước 3 — Kiểm tra provider.** Nếu API hỗ trợ query theo idempotency key hoặc external reference, tra cứu trạng thái trước khi quyết định gửi lại.

**Bước 4 — Xử lý theo kết quả.** Nếu provider xác nhận success, cập nhật command thành `SUCCEEDED`; nếu xác nhận chưa xử lý, retry cùng key; nếu không xác định được, giữ `UNKNOWN` và chuyển reconciliation.

**Bước 5 — Bảo vệ Kafka offset.** Không đánh dấu listener thành công nếu durable intent chưa được ghi. Nếu listener ném lỗi và record được retry, inbox/dedupe phải bảo vệ business state.

**Bước 6 — Kiểm tra side effect trùng.** Đối chiếu provider reference và internal payment record; không chỉ nhìn số lần consumer invocation.

**Bước 7 — Xác nhận phục hồi.** Command đạt terminal state, retry/unknown backlog giảm và record được xử lý theo chính sách.

Không tạo idempotency key mới để “thử lại cho chắc”; điều đó có thể tạo một payment operation khác.

## 25. Runbook: side effect thành công nhưng offset chưa commit

Một record đã gọi API thành công, nhưng pod restart trước commit offset.

1. Xác nhận record được giao lại bằng topic/partition/offset và event ID.
2. Kiểm tra inbox/command table hoặc provider state từ lần xử lý trước.
3. Nếu provider đã thành công, cập nhật internal state từ kết quả đã biết và không gọi charge lần nữa.
4. Nếu cần gọi lại, dùng đúng idempotency key cũ theo provider contract.
5. Nếu không có bằng chứng provider state, đưa command vào reconciliation/`UNKNOWN`.
6. Sau khi business state bền vững, để listener hoàn tất và offset commit theo ack mode.
7. Theo dõi duplicate delivery count và provider operation count để xác nhận không có duplicate business effect.

Kafka redelivery sau crash là bình thường. Hệ thống phải biến nó thành một lần kiểm tra trạng thái/dedupe an toàn.

## 26. Runbook: DLT replay cho event có side effect

Trước khi replay:
1. Xác định event ID và original topic/partition/offset.
2. Tìm command/inbox state của side effect.
3. Query provider nếu lần trước có timeout hoặc kết quả chưa rõ.
4. Xác định event đã charge, gửi email, tạo file hoặc cập nhật DB chưa.
5. Dùng cùng idempotency key nếu cần thử lại cùng operation.
6. Xác nhận consumer version/config đã sửa nguyên nhân lỗi.
7. Replay với batch nhỏ/canary và theo dõi kết quả.
8. Ghi replay ID, actor, lý do và kết quả.
9. Đối soát các event đã replay và đóng command ở trạng thái cuối.

Không xóa inbox marker hoặc command history chỉ để ép record chạy lại. Nếu cần chạy lại một nghiệp vụ mới, tạo operation/command mới có định danh mới và được nghiệp vụ phê duyệt.

## 27. Kiểm thử crash window và duplicate

Một integration test hữu ích không chỉ kiểm tra listener xử lý thành công mà còn mô phỏng các khoảng crash:

1. Gửi event có event ID ổn định.
2. Cho consumer ghi DB inbox + business update rồi giả lập offset commit thất bại; gửi lại record và xác nhận DB effect chỉ xảy ra một lần.
3. Cho external provider giả lập nhận request và ghi nhận success nhưng làm response timeout; retry cùng idempotency key và xác nhận provider chỉ tạo một operation.
4. Giả lập worker crash sau provider success nhưng trước khi command status update; worker mới tiếp quản và reconcile bằng key/reference.
5. Giả lập lỗi vĩnh viễn và xác nhận DLT/recovery state không bị đánh dấu success sai.
6. Replay cùng event ID nhiều lần và xác nhận dedupe vẫn hoạt động.
7. Test hai worker claim cùng command đồng thời để xác nhận chỉ một worker sở hữu lease hợp lệ.
8. Test compensation failure và trạng thái manual intervention nếu dùng Saga.

Dùng Kafka Testcontainers/embedded broker, database test và fake HTTP provider có trạng thái bền vững trong test. Không cần gọi payment provider thật hoặc gửi email production để kiểm tra idempotency.

## 28. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ Kafka transaction rollback được HTTP call | Side effect vẫn xảy ra dù Kafka transaction abort. | Dùng idempotency, outbox/command hoặc compensation. |
| Gọi API rồi commit offset, không có dedupe | Redelivery có thể tạo side effect trùng. | Stable idempotency key và durable state. |
| Tạo UUID mới ở mỗi retry | Provider xem mỗi attempt là operation mới. | Dùng key ổn định theo logical operation. |
| Retry mù sau read timeout | Provider có thể đã thực hiện operation trước timeout. | Query/reconcile hoặc retry cùng key. |
| DB marker commit trước email, rồi crash | Email có thể bị mất dù event được coi là xử lý. | Notification outbox và worker. |
| Gửi email trước DB marker rồi crash | Email có thể gửi trùng. | Provider dedupe hoặc suppression/reconciliation. |
| SELECT rồi INSERT để dedupe | Race giữa hai consumer/process. | Unique constraint và insert-if-absent trong transaction. |
| Outbox publisher đánh dấu sau send nhưng crash giữa hai bước | Event có thể publish lặp. | Downstream inbox/idempotency. |
| Giữ DB transaction mở khi chờ HTTP | Lock/connection pool pressure và timeout. | Ghi intent trong transaction ngắn, xử lý ngoài transaction. |
| DLT replay không kiểm tra provider state | Charge/email/file có thể lặp. | Kiểm tra command/inbox và idempotency trước replay. |
| Compensation được xem như rollback tuyệt đối | Compensation có thể thất bại hoặc không đảo ngược hoàn toàn. | Saga state machine và manual recovery. |

## 29. Checklist trước production

- [ ] Liệt kê tất cả side effect ngoài Kafka: DB, HTTP, email, file, object storage và service khác.
- [ ] Xác định crash window giữa side effect và Kafka offset/transaction commit.
- [ ] Mỗi logical operation có event ID/command ID ổn định.
- [ ] API provider dùng idempotency key ổn định nếu hỗ trợ.
- [ ] Timeout ambiguous được xử lý bằng query/reconciliation, không retry mù.
- [ ] DB inbox marker và business update nằm trong cùng DB transaction.
- [ ] Outbox row và business state được commit cùng nhau khi publish event từ DB.
- [ ] Downstream có dedupe vì outbox publisher có thể gửi lại.
- [ ] Worker command có state, lease, retry policy và terminal outcome rõ ràng.
- [ ] Retry/DLT replay giữ event identity và không tạo idempotency key mới.
- [ ] Side effect không thể đảo ngược có compensation hoặc manual recovery plan.
- [ ] Không giữ DB transaction/connection lâu trong lúc chờ network.
- [ ] Log có event ID, command ID, provider reference, attempt và outcome; không log secret.
- [ ] Có metric cho pending/unknown/retry/duplicate/outbox backlog.
- [ ] Test crash sau provider success, timeout ambiguous, offset commit failure và replay.
- [ ] Tài liệu nêu rõ ranh giới của exactly-once; không tuyên bố Kafka transaction bao phủ hệ thống ngoài.

## 30. Kết luận

**Tác vụ ngoài transaction phải được thiết kế như một workflow có thể retry, không phải một phần tự động của Kafka transaction.** Kafka transaction có thể phối hợp Kafka output records và input offsets; nó không rollback payment, email, SQL transaction độc lập hay file đã ghi. Vì vậy, consumer cần stable idempotency key, durable inbox/outbox state, trạng thái command rõ ràng và quy trình reconciliation cho những kết quả không xác định.

Với DB, inbox giúp deduplicate event và outbox giải quyết dual-write. Với HTTP provider, dùng idempotency key và query trạng thái sau timeout. Với nhiều bước nghiệp vụ, Saga và compensation cung cấp đường phục hồi có kiểm soát. Khi các pattern này được kết hợp với retry/DLT và kiểm thử crash window, hệ thống có thể chịu được redelivery/replay mà vẫn bảo toàn business outcome.
