# Bài toán ghi cơ sở dữ liệu và gửi thông điệp không nguyên tử

Trong hệ thống microservices, nhiều thay đổi nghiệp vụ cần **đồng thời ghi trạng thái cục bộ** và **phát một thông điệp cho thành phần khác**. Ví dụ, Ordering ghi một đơn hàng mới vào database rồi phát sự kiện OrderPlaced để Inventory, Payments hoặc Notifications tiếp tục quy trình. Nếu database và broker không nằm trong cùng một giao dịch nguyên tử, hai hành động có thể thành công hoặc thất bại **độc lập**. Đây là bài toán **dual write** (ghi hai hệ thống) và là một nguồn gây mất sự kiện, phát sự kiện giả hoặc gửi trùng rất phổ biến.

~~~text
Ordering Service
      |
      +--> (1) Database: lưu Order mới
      |
      +--> (2) Message broker: publish OrderPlaced
~~~

Câu hỏi cốt lõi là: **Làm sao bảo đảm khi một trạng thái nghiệp vụ đã commit thì thông điệp cần thiết cuối cùng cũng có thể được phát, ngay cả khi ứng dụng chết hoặc mạng bị lỗi giữa hai bước?** Đồng thời, nếu publisher phải gửi lại, làm sao consumer không xử lý hai lần cùng một tác động?

Một câu trả lời phổ biến là **transactional outbox**, kết hợp local database transaction, outbox publisher/CDC, broker có cơ chế lưu và consumer idempotent. Đây không phải một giao dịch ACID toàn hệ thống; nó chủ yếu chuyển vấn đề từ “một trong hai write bị mất vĩnh viễn” sang “một event có thể được gửi lặp nhưng có thể phục hồi và kiểm soát”. Bài học dưới đây đi từ failure timeline, các giải pháp, thiết kế bảng dữ liệu, Java/Spring, vận hành, kiểm thử đến ranh giới bảo đảm.

## 1. Phân biệt tính nguyên tử với độ tin cậy

**Atomicity (tính nguyên tử)** là một thuộc tính của transaction: các thay đổi trong cùng phạm vi được commit cùng nhau hoặc rollback cùng nhau. Một transaction ACID cục bộ trong một database có thể ghi cả bảng Orders và bảng Outbox một cách nguyên tử nếu hai bảng thuộc cùng ranh giới transaction.

**Dual write** xảy ra khi ứng dụng phải thực hiện hai thao tác có ảnh hưởng bền vững trên các hệ thống có transaction độc lập, chẳng hạn:

- INSERT Order vào PostgreSQL và publish OrderPlaced vào Kafka.
- UPDATE Payment trong MySQL và gửi message vào RabbitMQ.
- Ghi trạng thái trong database và gọi HTTP API tạo yêu cầu shipment.
- Commit giao dịch rồi gọi dịch vụ email hoặc payment gateway.
- Ghi vào một database và cập nhật một database khác không cùng transaction coordinator.

**Reliable event delivery** là mong muốn thông điệp không bị mất do crash hoặc outage trong các điều kiện đã thiết kế, có retry, quan sát và hồi phục. Bảo đảm này phải ghi rõ phạm vi: producer đã lưu gì, broker xác nhận đến mức nào, consumer có thể đọc lại được bao lâu và DLQ/replay được xử lý thế nào.

**At-least-once delivery** cho phép gửi lại một logical message nhiều lần để giảm khả năng mất. Nó **không đồng nghĩa** với “nghiệp vụ chỉ bị tác động một lần”.

**Idempotent processing** bảo đảm nhiều lần xử lý cùng một operation identity không nhân đôi hiệu ứng nghiệp vụ ngoài dự tính. Nó đặc biệt quan trọng khi outbox publisher hoặc broker có redelivery.

**Exactly-once** phải đi kèm phạm vi rất cụ thể. Một số nền tảng hỗ trợ transaction hoặc dedup trong phạm vi log/stream của mình, nhưng không mặc nhiên có transaction nguyên tử giữa database PostgreSQL, broker và payment gateway bên ngoài.

## 2. Vì sao không thể chỉ bọc hai lệnh trong một transaction Java?

Ví dụ sai lầm:

~~~java
@Transactional
public Order placeOrder(PlaceOrder request) {
    Order order = orderRepository.save(Order.create(request));
    kafkaTemplate.send("order-events", order.id(), toOrderPlaced(order));
    return order;
}
~~~

Một annotation @Transactional thông thường của Spring trên repository JPA quản lý **transaction của database**. KafkaTemplate.send có cơ chế gửi/ACK và transaction riêng (nếu cấu hình). Đặt hai lệnh trong cùng một phương thức Java không khiến chúng commit đồng thời theo một transaction ACID duy nhất.

Có ít nhất hai tài nguyên cần quan tâm:

~~~text
Resource 1: relational database      COMMIT DB?
Resource 2: message broker           PUBLISH ACCEPTED?
~~~

Nếu JVM hoặc mạng chết giữa hai quyết định commit, không có lời gọi finally, catch hay rollback Java nào chắc chắn đưa cả hai về cùng trạng thái. Thậm chí producer ACK bị mất khiến ứng dụng **không biết** broker có lưu event hay chưa.

**Một hàm thực thi tuần tự không phải một transaction phân tán.** Muốn nguyên tử giữa hai resource cần một giao thức/phối hợp giao dịch hỗ trợ bởi cả hai phía, hoặc phải thay đổi thiết kế để chỉ có một lần commit nguyên tử rồi truyền tải bất đồng bộ có thể retry.

## 3. Các cửa sổ lỗi khi ghi DB trước, gửi message sau

Cách viết trực tiếp:

~~~text
T1: INSERT Order
T2: COMMIT database
T3: publish OrderPlaced
T4: broker ACK
~~~

Ma trận sự cố:

| Thời điểm xảy ra lỗi | Database | Broker | Hậu quả |
| --- | --- | --- | --- |
| Trước T1 | Chưa đổi | Chưa có event | Thường an toàn, retry command theo idempotency |
| Trong transaction trước T2 | Rollback | Chưa có event | Không tạo trạng thái nửa chừng |
| **Sau T2, trước T3** | Order đã commit | Chưa có event | **Lost event** nếu không có cơ chế khôi phục |
| Sau T3 nhưng trước T4 | Order đã commit | Có thể đã lưu event | Producer không biết kết quả, retry có thể gửi trùng |
| Sau T4 | Order đã commit | Broker đã ACK theo policy | Chưa chứng minh consumer đã xử lý |

Tình huống nguy hiểm nhất là **DB commit thành công nhưng event không được công bố**. Inventory không nhận OrderPlaced và không khởi động giữ hàng; Notifications không có bản tin để gửi xác nhận; Analytics thiếu một đơn trong báo cáo. Hệ thống có thể không phát sinh exception vì process đã chết trước khi logging.

Nếu chỉ retry trong catch của cùng request, việc retry cũng không chạy khi process bị kill, pod bị evict, machine mất điện hoặc network partition kéo dài. Retry phải dựa trên **trạng thái bền vững còn tồn tại sau khi process chết**.

## 4. Đổi thứ tự: gửi message trước rồi commit DB có tốt hơn không?

Nếu đổi:

~~~text
T1: publish OrderPlaced
T2: broker ACK
T3: INSERT Order
T4: COMMIT database
~~~

Lỗi xảy ra sau T2 nhưng trước T4 dẫn tới **phantom event**: consumer nhìn thấy OrderPlaced nhưng Order chưa tồn tại vì transaction database sau đó rollback.

~~~text
Ordering publish OrderPlaced
             |
             v
Inventory nhận event -> bắt đầu giữ hàng
             |
             v
Ordering rollback transaction tạo Order
=> Inventory thực hiện hành động dựa trên một đơn không tồn tại
~~~

Điều này có thể tạo reservation mồ côi, email xác nhận sai hoặc dữ liệu báo cáo không có đối tượng gốc. Gửi trước không sửa dual write; chỉ đổi từ **mất event** sang **event không tương ứng fact đã commit**.

Việc publish sự kiện domain trong bộ nhớ trước commit cũng cần phân biệt với **integration event public**: domain event có thể được tạo khi aggregate thay đổi, nhưng integration event không nên được broker phát đến bên ngoài trước khi transaction có thẩm quyền commit thành công.

## 5. Các cách “sửa nhanh” không đủ an toàn

### 5.1. try/catch và retry ngay

~~~java
orderRepository.save(order);

try {
    publisher.publish(event);
} catch (Exception ex) {
    publisher.publish(event); // retry một lần
}
~~~

Không xử lý process crash giữa commit và lần publish đầu, không chứng minh transaction DB đã commit, và có thể tạo duplicate nếu ACK bị mất. Retry cần có **nguồn công việc bền vững** và giới hạn/backoff phù hợp.

### 5.2. @TransactionalEventListener(AFTER_COMMIT)

Listener chạy sau commit giúp tránh một số trường hợp publish trước commit, nhưng nếu ứng dụng chết sau DB commit và trước listener thì event vẫn mất. AFTER_COMMIT là cơ chế thời điểm thực thi listener trong process, **không phải durable outbox**.

### 5.3. Đưa publish vào finally

finally không chạy khi process bị kill mạnh, máy bị mất nguồn hoặc runtime crash. Một callback cũng không biến hai resource thành transaction nguyên tử.

### 5.4. Chờ broker ACK trước khi trả response HTTP

ACK có ích để biết một mức tiếp nhận của broker, nhưng không giải quyết trạng thái “DB đã commit, publisher chưa gửi” khi process chết. Nếu publisher ACK bị mất, server còn không biết publish có thành công không.

### 5.5. “Dùng Kafka transaction là đủ”

Kafka transactions có khả năng bảo đảm trong phạm vi các record/offset liên quan ở Kafka theo cấu hình, nhưng không mặc định bao gồm commit của một database SQL tùy ý. Không kết luận transaction đồng bộ giữa JPA và Kafka là ACID end-to-end chỉ vì cả hai đều hỗ trợ transaction riêng.

### 5.6. “Cứ publish lại khi GET thấy thiếu”

Consumer và read model có thể chậm hợp lệ; query từ bản sao không biết source đang thiếu event hay chỉ bị lag. Gửi lại bừa bãi có thể gây duplicate và không có lộ trình phục hồi rõ khi người dùng không tiếp tục truy vấn.

## 6. Transactional outbox: thay đổi mô hình

Ý tưởng: thay vì ghi database rồi gửi broker như hai hành động không nguyên tử trong request, **ghi dữ liệu nghiệp vụ và một bản ghi yêu cầu phát event trong cùng local transaction**.

~~~text
                   CÙNG DATABASE / CÙNG TRANSACTION
Ordering             +-----------------------------+
  | -- BEGIN ------->| Orders table                |
  | -- INSERT Order ->| Order #1001                 |
  | -- INSERT Outbox->| Outbox(evt-1001, PENDING)   |
  | -- COMMIT ------>| Cả hai cùng commit          |
                     +-----------------------------+
                                  |
                                  v
                           Outbox publisher
                                  |
                                  v
                             Message broker
                                  |
                                  v
                             Consumers
~~~

Nếu database commit thất bại, **cả Order lẫn outbox record đều không tồn tại**. Nếu commit thành công, **cả hai cùng tồn tại**. Publisher có thể chết, nhưng record outbox vẫn nằm trong database để worker khác hoặc lần chạy sau tiếp tục phát.

Tính nguyên tử đạt được là giữa **business state và ý định phát thông điệp** trong cùng database. Việc đưa thông điệp qua mạng và consumer xử lý vẫn là bất đồng bộ, có thể delay và duplicate.

### 6.1. Tại sao outbox không cần gửi trong request?

Request có thể commit Order và outbox rất nhanh, trả 201 Created hoặc command status phù hợp. Worker/CDC đảm nhận việc publish. Điều này giảm phụ thuộc runtime trực tiếp của command vào broker, nhưng tạo **eventual consistency**: consumer nhận thông điệp sau commit một khoảng thời gian.

Cần công bố rõ SLA truyền event, theo dõi backlog, và xác định khi nào command được coi là hoàn thành. Ví dụ PlaceOrder có thể hoàn thành bước ghi đơn, còn toàn workflow thanh toán/giao hàng đang PENDING.

### 6.2. Khi nào nên dùng?

Transactional outbox phù hợp khi:

- Service sở hữu local database và cần phát integration event tương ứng thay đổi dữ liệu.
- Không muốn mất event khi broker tạm down sau DB commit.
- Có thể chấp nhận lan truyền bất đồng bộ và xử lý trùng.
- Muốn scale publisher độc lập với request handlers.
- Muốn audit/troubleshoot những event đang chờ phát.

Không phải mọi thông điệp đều yêu cầu outbox. Telemetry không quan trọng có thể chấp nhận mất; command không có DB write tại sender có thể dùng broker durable send trực tiếp kèm retry thích hợp. Quyết định dựa trên yêu cầu nghiệp vụ.

## 7. Thiết kế bảng outbox

Một schema PostgreSQL minh họa:

~~~sql
CREATE TABLE orders (
    order_id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL,
    total_minor BIGINT NOT NULL,
    currency CHAR(3) NOT NULL,
    version BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(120) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_by VARCHAR(120),
    claim_until TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    last_error TEXT
);

CREATE INDEX outbox_pending_idx
    ON outbox_events (next_attempt_at, occurred_at)
    WHERE status = 'PENDING';

CREATE INDEX outbox_aggregate_idx
    ON outbox_events (aggregate_type, aggregate_id, aggregate_version);
~~~

Các field:

| Trường | Mục đích |
| --- | --- |
| event_id | Định danh **logical event** ổn định qua retry |
| aggregate_type/id | Owner và business entity của sự kiện |
| aggregate_version | Version để consumer kiểm tra thứ tự và stale update |
| event_type | Tên event có ngữ nghĩa, ví dụ OrderPlaced |
| schema_version | Phiên bản hợp đồng payload |
| payload | Snapshot dữ liệu sự kiện tại thời điểm transaction |
| occurred_at | Thời điểm fact được owner ghi nhận |
| status | PENDING, CLAIMED, PUBLISHED hoặc các trạng thái đã thiết kế |
| attempts/next_attempt_at | Retry budget và backoff |
| claimed_by/claim_until | Phối hợp nhiều publisher worker |
| published_at | Mốc được xác nhận đã publish theo policy |
| last_error | Thông tin lỗi để vận hành |

Lược đồ chỉ là ví dụ. Với poller nhiều worker, index và state cần phù hợp truy vấn claim thực tế; nếu dùng CDC, có thể không cần các field PENDING/CLAIMED/PUBLISHED vì tiến độ được checkpoint ở connector. Không nên áp dụng nguyên bảng này cho mọi kiểu outbox mà không xem phương pháp phát.

### Thiết kế payload theo thời điểm commit

Outbox nên chứa dữ liệu cần công bố ở trạng thái đã xác định **trong transaction**, thay vì chỉ lưu orderId rồi publisher lấy lại Order sau nhiều phút. Nếu dữ liệu Order đã thay đổi, việc đọc trạng thái hiện tại có thể làm event OrderPlaced chứa nội dung của Order sau khi bị sửa/hủy, không đúng fact ban đầu.

Nếu event quá lớn, có thể lưu reference/snapshot riêng, nhưng phải bảo đảm dữ liệu tham chiếu có vòng đời, version và quyền truy cập thích hợp. Việc chỉ lưu pointer tới trạng thái hiện tại không tự bảo toàn semantics quá khứ.

## 8. Ghi Order và outbox trong một transaction

Pseudo flow:

~~~text
POST /orders
  -> authenticate, authorize, validate
  -> bắt đầu database transaction
  -> tạo Order theo domain rules
  -> INSERT orders(...)
  -> INSERT outbox_events(eventId, OrderPlaced, payload)
  -> COMMIT
  -> trả Order id/status/version
~~~

Trong Java/Spring:

~~~java
@Service
public class PlaceOrderService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final EventSerializer serializer;

    public PlaceOrderService(
            OrderRepository orders,
            OutboxRepository outbox,
            EventSerializer serializer) {
        this.orders = orders;
        this.outbox = outbox;
        this.serializer = serializer;
    }

    @Transactional
    public PlaceOrderResult place(PlaceOrderCommand command) {
        Order order = Order.create(
            command.orderId(),
            command.customerId(),
            command.items()
        );

        orders.save(order);

        OrderPlaced event = new OrderPlaced(
            UUID.randomUUID(),
            order.id(),
            order.version(),
            Instant.now(),
            order.customerId(),
            order.totalMinor(),
            order.currency()
        );

        outbox.insert(
            event.eventId(),
            "Order",
            event.orderId().toString(),
            event.orderVersion(),
            "OrderPlaced",
            1,
            serializer.toJson(event)
        );

        return new PlaceOrderResult(order.id(), order.status().name());
    }
}
~~~

Các kiểu Order, OrderRepository, OutboxRepository, Command, EventSerializer và record là các thành phần minh họa chưa được định nghĩa đầy đủ trong đoạn này. Triển khai thực tế cần imports, validation, optimistic locking, unique constraint cho command idempotency và test transaction.

Điều kiện bắt buộc:

- orders.save và outbox.insert phải thực sự tham gia **cùng database transaction**.
- Không được tự cấu hình REQUIRES_NEW cho outbox làm nó commit độc lập với Order.
- Nếu outbox insert thất bại, toàn bộ transaction phải rollback.
- Domain event chỉ được công bố ra broker sau commit thông qua publisher.
- eventId nên được tạo một lần cho logical event; khi worker retry phải giữ nguyên.
- Nếu PlaceOrder HTTP bị retry sau response timeout, cần **command idempotency** để tránh tạo hai Order và hai logical event khác nhau.
- Nếu có nhiều event phát sinh trong một transaction, ghi từng outbox record kèm aggregate version hoặc sequence thích hợp.

## 9. Một transaction thất bại ở đâu?

| Sự cố | Order row | Outbox row | Kết luận |
| --- | --- | --- | --- |
| Exception trước BEGIN | Không có | Không có | An toàn |
| Order INSERT lỗi | Rollback | Không có | An toàn |
| Outbox INSERT lỗi | Rollback Order | Rollback | Không để Order thiếu event |
| DB commit thành công | Có | Có | Có bản ghi durable để phát |
| Process chết ngay sau commit | Có | Có | Publisher khác có thể tiếp tục |
| Broker down nhiều phút | Có | Có | Outbox tích tụ, cần theo dõi |
| Publisher publish thành công nhưng ACK mất | Có | Có, chưa đánh dấu | Có nguy cơ gửi trùng khi retry |
| Publisher gửi thành công rồi chết trước đánh dấu PUBLISHED | Có | Có, vẫn pending/claimed | Có nguy cơ gửi trùng |
| Consumer xử lý rồi chết trước ACK | Có | Có | Broker có thể redeliver, consumer phải idempotent |

Không nên báo hệ thống “exactly once” từ bảng trên. Mục tiêu là **không mất logical event do khoảng trống giữa DB commit và publish**, còn duplicate được kiểm soát bằng identity, inbox/idempotency và transaction của consumer.

## 10. Hai cách phổ biến phát outbox

### 10.1. Polling publisher

Worker định kỳ tìm outbox record chưa gửi và publish đến broker. Khi có nhiều worker, cần claim record an toàn để tránh tất cả cùng gửi liên tục.

~~~text
Outbox database
   |
   +-- poll batch chưa gửi
   +-- claim record theo lease/locking
   +-- publish vào broker, chờ xác nhận
   +-- đánh dấu PUBLISHED
   +-- nếu không rõ kết quả, retry sau backoff
~~~

Ưu điểm: đơn giản, dễ hiểu, không cần CDC infrastructure. Nhược điểm: phải quản lý polling interval, retry, dead-letter, contention, ordering, khối lượng bảng outbox và cleanup.

**Không giữ transaction DB mở khi chờ broker ACK lâu.** Có thể claim một batch nhanh trong transaction, commit claim, publish ngoài transaction, rồi update trạng thái theo kết quả. Khi lease hết hạn hoặc worker chết, worker khác có thể claim lại; duplicate vẫn có thể xảy ra và phải được chấp nhận.

Một ví dụ claim với PostgreSQL trong transaction ngắn:

~~~sql
-- Minh họa, cần hàm ứng dụng kiểm soát transaction và lease.
WITH picked AS (
    SELECT event_id
    FROM outbox_events
    WHERE
        status = 'PENDING'
        AND next_attempt_at <= now()
    ORDER BY occurred_at, event_id
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
UPDATE outbox_events AS o
SET
    status = 'CLAIMED',
    claimed_by = 'publisher-1',
    claim_until = now() + interval '30 seconds',
    attempts = attempts + 1
FROM picked
WHERE o.event_id = picked.event_id
RETURNING o.*;
~~~

**Quan trọng:** Khi dùng trạng thái CLAIMED phải có job/điều kiện **thu hồi lease hết hạn**, nếu không process chết sẽ khiến record bị kẹt mãi. Ví dụ trên chỉ claim PENDING; hệ thống thực phải đưa expired CLAIMED về danh sách có thể claim và không cho worker cũ đánh dấu PUBLISHED sau khi lease đã bị worker khác chiếm trừ khi kiểm soát bằng lease token/fencing phù hợp.

Worker có thể:

1. Claim record và nhận lease token.
2. Gửi message với eventId ổn định.
3. Chờ broker ACK theo durability policy.
4. Update PUBLISHED chỉ nếu claim vẫn hợp lệ hoặc dùng giao thức fencing an toàn.
5. Với timeout, tính nextAttemptAt và chuyển trạng thái để retry.
6. Với lỗi vĩnh viễn như schema không hợp lệ, đưa vào trạng thái cần điều tra, không retry nóng vô hạn.

Nếu broker đã nhận message nhưng ACK timeout, worker phải mặc định kết quả **không rõ**, không chắc là thất bại. Retry có thể tạo duplicate.

### 10.2. Change Data Capture (CDC)

Thay vì polling các hàng, một connector CDC có thể đọc thay đổi đã commit từ transaction log/WAL của database và phát các outbox record đến broker.

~~~text
Ordering transaction:
  INSERT Order
  INSERT Outbox
  COMMIT
          |
          v
Database WAL / change stream
          |
          v
CDC connector (ví dụ Debezium)
          |
          v
Kafka topic(s)
          |
          v
Consumers
~~~

Ưu điểm:

- Đọc thay đổi qua log, tránh polling tần suất cao trên bảng.
- Có thể giữ quan hệ với commit order ở phạm vi mà database/connector hỗ trợ.
- Có thể route event bằng outbox event router/transform.
- Tách application write path khỏi publish worker.

Thách thức:

- Cần vận hành connector, replication slot, log retention và checkpoint.
- Database WAL có thể tăng dung lượng nếu connector tụt dài hạn.
- Snapshot ban đầu hoặc restart connector cần chính sách không tạo duplicate bất ngờ.
- Schema của outbox và routing transform là hợp đồng vận hành.
- Khi connector lỗi, phải có retry, alert, replay/backfill và bảo vệ tính nhất quán.
- Phạm vi thứ tự/sắp xếp giữa các partition/broker topic cần được xác nhận, không suy ra global order.
- CDC không tự giải quyết việc consumer gây side effect trùng.

**Cả polling và CDC đều dựa trên cùng nguyên tắc: event intent được ghi nguyên tử với dữ liệu nghiệp vụ.** Chúng khác nhau ở cách đưa record đã commit đến broker và cách quản lý tiến độ.

## 11. So sánh polling outbox và CDC

| Tiêu chí | Polling publisher | CDC từ transaction log |
| --- | --- | --- |
| Tích hợp ứng dụng | Worker và repository tự triển khai | Connector/stream processor chuyên dụng |
| Độ trễ | Phụ thuộc polling interval và tải | Thường thấp, phụ thuộc connector/log/broker |
| Tải database | Truy vấn/claim/update outbox | Đọc log, vẫn có chi phí WAL/slot |
| Nhiều worker | Claim/lease, tránh contention | Coordinator/partitioning của connector |
| Retry | Ứng dụng quản lý trạng thái và backoff | Connector quản lý checkpoint/retry; vẫn cần vận hành |
| Ordering | Phải thiết kế theo aggregate/sequence | Có thể giữ thứ tự commit trong phạm vi nguồn rồi route phù hợp |
| Cleanup | Cần xóa/archive hàng đã phát | Cần retention dữ liệu và quản lý log/slot |
| Failure recovery | Rescan pending/expired lease | Resume từ checkpoint/log position |
| Vận hành | Ít hạ tầng hơn, nhiều code custom | Hạ tầng chuyên dụng và giám sát connector |
| Duplicate | Có thể, nhất là publish ACK không rõ | Vẫn có thể khi replay/checkpoint |
| Khi phù hợp | Đội nhỏ, workload vừa, muốn kiểm soát trực tiếp | Hệ thống có CDC platform, throughput lớn, cần streaming |

Không chọn CDC chỉ vì muốn gọi giải pháp “exactly once”. Cả hai vẫn phải chịu các failure modes của mạng, broker và consumer.

## 12. Kết quả publish phải được hiểu theo tầng

Một event có các mốc:

~~~text
1. Business transaction committed
2. Outbox record tồn tại
3. Publisher lấy record
4. Client library chấp nhận send
5. Broker ACK theo cấu hình
6. Consumer nhận record
7. Consumer commit local database
8. Consumer ACK/commit offset
9. Workflow/business completed
~~~

Mốc 4 chưa chắc broker đã lưu. Mốc 5 không chứng minh consumer đã hoàn tất. Mốc 8 không chứng minh external side effect như email/payment gateway đã xảy ra đúng một lần. Mốc 9 là trạng thái nghiệp vụ riêng do domain owner/workflow xác định.

Ví dụ người dùng đặt hàng:

- 201 Created từ Ordering có thể là **đã tạo Order và ghi outbox**.
- StockReserved event có thể đến sau và cần saga cập nhật Order.
- PaymentCaptured event có thể đến muộn hoặc thất bại.
- Chỉ khi những điều kiện của domain được thỏa, Order mới có thể chuyển CONFIRMED hoặc READY_TO_SHIP.

UI phải phân biệt **đã nhận/đã lưu yêu cầu** và **toàn bộ workflow hoàn tất**.

## 13. Vấn đề gửi trùng là tất yếu trong cửa sổ ACK không rõ

Một kịch bản:

~~~text
Publisher -> Broker: publish OrderPlaced(evt-101)
Broker: lưu thành công
Broker -> Publisher: ACK
Kết nối đứt trước khi Publisher nhận ACK
Publisher: không biết kết quả
Publisher retry evt-101
Broker có thể nhận evt-101 lần nữa
~~~

Nếu publisher đổi eventId mỗi lần retry, consumer khó xác định hai bản tin là cùng một logical event. Hãy tạo eventId **khi ghi outbox** và sử dụng lại không đổi trong mọi lần publish/replay của record đó.

Consumer có thể lưu processed event ID trong cùng local transaction với projection:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer thực hiện:

~~~text
Receive OrderPlaced(eventId)
BEGIN TRANSACTION
  nếu (consumer, eventId) đã xử lý:
      không tạo side effect mới
  nếu chưa:
      INSERT processed_events unique
      cập nhật projection / ghi command nội bộ
COMMIT
ACK broker hoặc commit offset
~~~

Có thể dùng INSERT ... ON CONFLICT DO NOTHING để xử lý race, nhưng application phải kiểm tra có thực sự insert được mới chạy side effect. Processed ID và projection phải cùng transaction; nếu commit inbox trước projection, crash có thể khiến lần sau bỏ qua event chưa từng áp dụng.

### Những trường hợp cần business idempotency ngoài event ID

Nếu publisher hoặc upstream tạo hai **logical events khác nhau** cho cùng một thao tác nghiệp vụ, dedup theo eventId không đủ. Ví dụ HTTP POST PlaceOrder bị retry với request ID mới và tạo hai Order. Cần idempotency key ở **command boundary**, unique constraint theo business operation và trả lại kết quả đã lưu khi nhận cùng yêu cầu.

Ví dụ đặt hàng: customerId + checkoutAttemptKey là operation identity, còn eventId nhận diện từng event sinh ra từ commit. Hai lớp này có trách nhiệm khác nhau.

## 14. Consumer side effect và inbox

Giả sử Analytics nhận OrderPlaced và tăng doanh thu:

~~~text
Receive evt-101
  -> UPDATE daily_revenue += 159900
  -> COMMIT DB
  -> ACK broker
~~~

Nếu crash sau COMMIT nhưng trước ACK, broker giao lại và Analytics cộng thêm lần nữa. Dùng inbox/processed ID trong cùng transaction để update doanh thu **một lần theo eventId**.

Mã giả Java:

~~~java
@Service
public class OrderPlacedProjectionHandler {
    private final ProcessedEventRepository inbox;
    private final RevenueProjectionRepository projections;

    public OrderPlacedProjectionHandler(
            ProcessedEventRepository inbox,
            RevenueProjectionRepository projections) {
        this.inbox = inbox;
        this.projections = projections;
    }

    @Transactional
    public void handle(OrderPlaced event) {
        boolean firstProcessing = inbox.tryInsertUnique(
            "analytics-order-projection", event.eventId());

        if (!firstProcessing) {
            return; // Event này đã tác động vào projection.
        }

        projections.addRevenue(
            event.occurredAt(),
            event.currency(),
            event.totalMinor()
        );
    }
}
~~~

Mã minh họa interface và transaction, không phải project hoàn chỉnh. Trong production, phải bảo đảm tryInsertUnique có unique constraint thật, transaction không bị split, handler không ACK broker trước commit và việc cộng tiền dùng đúng quy tắc business.

Với read model dạng upsert, cũng có thể dùng aggregateVersion để bỏ stale update, nhưng **version check không tự thay thế event dedup** khi một event tạo side effect cộng dồn hoặc gửi tác vụ.

## 15. Side effect ngoài database cần chiến lược riêng

Một consumer có thể gọi:

- Payment gateway để charge/refund.
- Email/SMS provider để gửi thông báo.
- Shipping provider để tạo vận đơn.
- External ERP để lập hóa đơn.

Các hệ thống này **không tham gia local transaction** của bảng inbox. Tình huống khó:

~~~text
Notifications:
  1. Gọi email provider
  2. Provider đã nhận và gửi email
  3. Notifications crash trước khi ghi SENT
  4. Retry -> có thể gửi email lần nữa
~~~

Inbox đơn thuần không chứng minh email chỉ gửi một lần. Phải xem provider có hỗ trợ **idempotency key** hay không, định nghĩa business operation ID ổn định, lưu trạng thái PENDING/SENT/UNKNOWN và reconcile nếu kết quả không rõ. Với email không có idempotency end-to-end, có thể chấp nhận rủi ro duplicate có kiểm soát hoặc thiết kế notification policy không gửi lại vô điều kiện.

Đặc biệt với payments, khi gateway timeout sau khi capture tiền, **không tạo capture attempt mới bằng operation key khác** khi chưa kiểm tra kết quả của key cũ. Cần payment operation record, unique constraint, gateway idempotency khi hỗ trợ, webhook/sync reconciliation và trạng thái UNKNOWN/PENDING.

### Kết hợp outbox và inbox

~~~text
Ordering DB:
  Order + outbox(OrderPlaced) trong một transaction
         |
         v
      Broker
         |
         v
Analytics DB:
  inbox(eventId) + projection update trong một transaction
         |
         v
  ACK/offset sau commit
~~~

Đây là mô hình thực dụng giúp hệ thống chịu được mất kết nối và redelivery. Các bước khác như Payments hoặc Shipment tiếp tục cần saga, idempotency và business compensation riêng.

## 16. Bảo toàn thứ tự khi một aggregate phát nhiều event

Ví dụ Ordering phát:

~~~text
OrderPlaced(orderId=1001, version=1)
OrderConfirmed(orderId=1001, version=2)
OrderCancelled(orderId=1001, version=3)
~~~

Nếu publisher đa luồng lấy outbox theo thời gian tạo rồi publish không có kiểm soát, event v3 có thể tới consumer trước v2. Nếu consumer apply một cách mù quáng, trạng thái có thể lùi từ CANCELLED về CONFIRMED.

Thiết kế:

1. Ghi aggregateVersion/sequence trong transaction cập nhật aggregate.
2. Dùng key theo aggregateId để route các event cùng aggregate vào cùng partition nếu broker hỗ trợ và cần thứ tự.
3. Xác định owner của ordering: thứ tự commit, thứ tự publish hay thứ tự apply?
4. Với polling nhiều worker, hạn chế claim đồng thời event của cùng aggregate khi cần bảo toàn thứ tự publish.
5. Consumer kiểm tra version, bỏ event cũ hoặc đợi/fetch source khi có gap theo state machine.
6. Không mặc định một topic nhiều partition có **global ordering**.
7. Nếu tăng số partition hoặc đổi partitioner, xem xét ảnh hưởng mapping key và ordering.
8. Khi replay outbox, đảm bảo quy tắc version vẫn có hiệu lực.

Một chỉ số timestamp occurredAt đơn lẻ không đủ làm total order giữa nhiều máy. Sequence/version trong phạm vi aggregate đáng tin hơn nếu được cập nhật nguyên tử.

## 17. Phân biệt event intent và nghiệp vụ kết thúc

Trong event-driven workflow, OrderPlaced thường chỉ nghĩa một Order đã được ghi nhận. Sau đó cần:

~~~text
OrderPlaced
   |
   v
OrderSaga sends ReserveStock
   |
   +--> StockReserved
   |        |
   |        v
   |   AuthorizePayment
   |        |
   |        +--> PaymentAuthorized -> ConfirmOrder
   |        +--> PaymentDeclined -> ReleaseReservation, CancelOrder
   |
   +--> ReservationRejected -> CancelOrder
~~~

Outbox đảm bảo fact đã commit có khả năng được truyền đi, **không bảo đảm các bước tiếp theo thành công**. Bị thiếu stock, lỗi gateway hoặc customer hủy giữa chừng vẫn là kết quả nghiệp vụ cần state machine, timeout và bù trừ.

Cần phân biệt:

- Event được ghi vào outbox.
- Event đã được broker nhận.
- Command downstream đã được nhận.
- Command downstream đã thực thi thành công.
- Workflow đã đến trạng thái cuối theo business invariant.

Trộn chúng thành một cờ SUCCESS sẽ gây báo cáo sai, UI sai và khó khôi phục.

## 18. Đặt giới hạn trễ và bảo vệ backlog

Khi broker down 30 phút, Ordering vẫn có thể ghi Order và outbox nếu database hoạt động. Điều này có lợi về độ bền nhưng backlog sẽ tăng. Không có hệ thống lưu trữ vô hạn.

Cần xác định:

- Outbox có thể chứa tối đa bao nhiêu record/GB?
- Tải ghi thêm vào database khi mỗi business transaction có thêm event record?
- Worker/connector cần bao lâu để bắt kịp sau outage?
- Nếu outbox đạt ngưỡng an toàn, service sẽ giảm tải, từ chối command hay cho tiếp tục ghi?
- Khi broker hồi phục, replay nhiều sự kiện có làm consumer và database downstream quá tải không?
- Event nào có thời hạn xử lý? Event đến muộn còn ý nghĩa gì?
- Outbox record đã phát được giữ bao lâu cho audit/recovery?
- Có backup/restore và reconciliation khi dữ liệu outbox bị mất không?

Một thiết kế chỉ có retry vô hạn mà không có alert, quota và runbook sẽ biến một sự cố broker nhỏ thành vấn đề database capacity.

### Metric quan trọng

| Metric | Ý nghĩa |
| --- | --- |
| outbox_pending_count | Số event chưa xác nhận đã phát |
| outbox_oldest_pending_age | Event cũ nhất chờ bao lâu |
| outbox_publish_rate | Publisher đang gửi với tốc độ nào |
| outbox_publish_errors | Lỗi route/serialize/auth/broker |
| publisher_retry_count | Bao nhiêu lần phải gửi lại |
| lease_expired_count | Worker chết hoặc bị chậm khi giữ claim |
| broker_ack_latency | Thời gian publisher chờ xác nhận |
| consumer_lag | Consumer tụt bao xa so với broker |
| consumer_duplicate_skipped | Bao nhiêu message trùng được nhận diện |
| dlq_count/age | Message không thể xử lý đang tồn tại |
| event_propagation_p95/p99 | Từ owner commit đến consumer projection |
| saga_stuck_count | Quy trình nghiệp vụ bị kẹt |
| reconciliation_mismatch | Sai lệch giữa owner và bản sao |

Đặt cảnh báo theo **tuổi event chờ** và SLO, không chỉ theo số lượng record. 10.000 event chờ vài giây ở hệ throughput cao có thể bình thường; một event thanh toán chờ một giờ lại rất nghiêm trọng.

## 19. Retry policy và dead-letter cho publisher

Không phải lỗi nào cũng nên retry như nhau.

| Lỗi | Xử lý phù hợp |
| --- | --- |
| Broker tạm unreachable | Retry có exponential backoff/jitter |
| Broker quá tải/rate limit | Giảm tốc, retry có giới hạn, cảnh báo |
| Producer ACK timeout | Kết quả không rõ, retry cùng eventId |
| Authorization denied | Dừng nóng, cảnh báo cấu hình/ACL |
| Schema invalid | Quarantine record, sửa mapping/schema |
| Payload quá lớn | Triage và xử lý thiết kế payload |
| Event deadline hết | Theo chính sách nghiệp vụ, không âm thầm xóa |
| Lease claim bị mất | Worker cũ không tiếp tục finalize claim sai |
| Record stuck quá SLO | Escalate và runbook/replay |
| CDC connector không còn WAL | Cần recovery/re-snapshot có kiểm soát |

Dead-letter của publisher không nên là “đã xong”. Record bị bỏ ra khỏi luồng chính cần một owner, cơ chế inspect an toàn và đường replay. Một event có thể bị lỗi schema nhưng Order đã commit; nếu drop event, downstream sẽ không biết. Quyết định khôi phục phải xét tác động nghiệp vụ.

## 20. Dọn bảng outbox an toàn

Nếu polling publisher đánh dấu PUBLISHED, giữ mãi mọi record sẽ làm bảng lớn và ảnh hưởng index/query. Cần chính sách:

- Chỉ dọn record sau khi đạt mốc publish được xác nhận theo contract.
- Giữ đủ thời gian cho điều tra, duplicate/replay và audit nếu cần.
- Cleanup theo batch/partition, tránh khóa bảng lớn.
- Đảm bảo retention của outbox phù hợp với log/recovery strategy.
- Không dọn PENDING, CLAIMED còn có khả năng cần retry chỉ vì record cũ.
- Với CDC, không xóa/outbox cleanup theo cách khiến connector mất thay đổi chưa checkpoint.
- Khi khôi phục từ backup, đối chiếu offset/checkpoint để tránh gap hoặc phát lại không kiểm soát.
- Quan sát dung lượng bảng, index bloat, WAL/replication slot và cleanup failures.

Một event đã được broker ACK có thể bị broker hết retention trước khi consumer offline bắt kịp; đó là failure/recovery khác với dual-write và cần chính sách lưu trữ riêng. Đừng coi xóa outbox record như bằng chứng mọi consumer đã hoàn tất.

## 21. Trường hợp update database và gọi API đồng bộ

Không phải mọi dual-write đều là database + broker. Ví dụ:

~~~text
Order Service:
  1. COMMIT order
  2. HTTP POST /shipments to Shipping
~~~

Nếu crash giữa hai bước, shipment chưa được tạo. Nếu HTTP timeout sau khi Shipping đã tạo shipment, retry có thể tạo vận đơn trùng.

Cách xử lý có thể là:

- Trong transaction Order, ghi **outbox command intent** cần gửi CreateShipment với operation key ổn định.
- Worker phát command qua broker hoặc gọi HTTP sau khi lấy record bền vững.
- Shipping xử lý idempotent theo shipmentOperationId/business key.
- OrderSaga theo dõi ShipmentCreated/ShipmentRejected hoặc operation status.
- Reconcile khi response không rõ.

Sự kiện **OrderPlaced** và lệnh **CreateShipment** có nghĩa khác nhau. Outbox là cơ chế độ bền cho việc phát; nó không thay thế quyết định nên công bố fact hay gửi command.

Với HTTP API ngoại vi, có thể dùng workflow engine hoặc job table thay outbox event chuyên biệt, miễn đảm bảo **intent được commit cùng thay đổi gốc** và handler có retry/idempotency.

## 22. Saga và transactional outbox giải quyết hai vấn đề khác nhau

**Outbox** giải quyết tính nguyên tử của **business state + message intent** trong một service.

**Saga/process manager** giải quyết workflow nghiệp vụ trải qua nhiều service, có thể gồm các command, event kết quả, timeout, compensation và reconciliation.

~~~text
Ordering local transaction:
    Order PENDING + outbox(OrderPlaced)

Outbox publish:
    OrderPlaced -> Broker

OrderSaga:
    ReserveStock -> Inventory
    StockReserved -> OrderSaga
    CapturePayment -> Payments
    PaymentCaptured -> OrderSaga
    ConfirmOrder -> Ordering
~~~

Nếu Inventory không đủ hàng, đây là business rejection; broker và outbox vẫn có thể hoạt động hoàn hảo. Nếu Payments capture xong nhưng bước tiếp theo lỗi, saga cần bù trừ/đối chiếu, không thể chỉ “rollback toàn bộ” như trong một database.

Không quảng bá outbox như một replacement cho distributed workflow state. Cả hai thường bổ trợ nhau.

## 23. Khi nào dùng distributed transaction/XA/2PC?

Về lý thuyết, một transaction coordinator và các resource hỗ trợ giao thức 2-phase commit có thể phối hợp commit nhiều resource. Nhưng:

- Broker, database, client library và transaction manager phải **thực sự hỗ trợ chung giao thức**.
- Locks và trạng thái prepared có thể tồn tại khi coordinator bị lỗi.
- Availability và hiệu năng có thể bị ảnh hưởng bởi network partition và recovery.
- Việc nâng cấp, vận hành, retry và rollback phức tạp hơn.
- Không phải hệ broker hoặc managed service nào cũng hỗ trợ XA theo cách mong muốn.
- Giao dịch xuyên nhiều bounded contexts có thể làm tăng coupling và rủi ro khi scale.

Khi nền tảng có transaction coordinator phù hợp, 2PC có thể là lựa chọn trong phạm vi hẹp; không nên tuyên bố luôn sai. Tuy nhiên, với microservices và message broker phổ biến, **local transaction + outbox + idempotent consumer** thường là mô hình dễ vận hành và chịu lỗi hơn.

Kafka transactional producer có phạm vi bảo đảm riêng, không tự biến một PostgreSQL transaction thành participant XA. Nếu team dựa trên một tính năng transaction của framework, phải kiểm thử cụ thể crash giữa các bước commit để biết điều gì thực sự được bảo đảm.

## 24. Chọn polling, CDC hay transaction broker

Bảng quyết định:

| Điều kiện | Hướng nên xem xét |
| --- | --- |
| Một service có database quan hệ và cần phát event đáng tin | Transactional outbox |
| Ít event, team muốn triển khai đơn giản | Outbox + polling worker |
| Hạ tầng đã có CDC, nhiều service và throughput cao | Outbox + log-based CDC |
| Broker có transaction nội bộ giữa topic/offset | Dùng trong phạm vi broker nếu phù hợp, vẫn xem DB boundary |
| Workflow nhiều service và compensation | Saga + outbox/inbox |
| External API có idempotency key | Durable job/outbox + key ổn định + reconciliation |
| Event không quan trọng và chấp nhận mất | Có thể publish best-effort có chủ đích |
| Source database không cho transaction ghi cùng outbox | Cần đánh giá redesign, change stream/CDC, command journal hoặc cơ chế bền vững khác |

**Không chọn giải pháp chỉ từ tên công nghệ.** Hãy vẽ các mốc commit và xác định cửa sổ lỗi, khả năng replay, thứ tự cần bảo vệ và chi phí hồi phục.

## 25. Contract và metadata cho event

Một outbox event cần đủ thông tin để publisher không phải đoán:

~~~json
{
  "eventId": "60d18c9a-944a-4e37-a73f-0e390c3bf2f8",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "aggregateType": "Order",
  "aggregateId": "ord-1001",
  "aggregateVersion": 1,
  "occurredAt": "2026-11-11T09:21:15Z",
  "correlationId": "checkout-888",
  "causationId": "cmd-place-1001",
  "payload": {
    "orderId": "ord-1001",
    "customerId": "cust-71",
    "totalMinor": 159900,
    "currency": "VND"
  }
}
~~~

- **eventId** ổn định qua retry, là khóa dedup message.
- **eventType** mô tả fact, không chỉ DB table update.
- **schemaVersion** hỗ trợ consumer cũ/mới trong rolling deployment.
- **aggregateVersion** hỗ trợ thứ tự trong phạm vi Order.
- **occurredAt** do owner ghi khi fact được commit, không phải thời gian worker publish.
- **correlationId** liên kết workflow; **causationId** chỉ hành động trực tiếp.
- **payload** mô tả fact với dữ liệu cần thiết và không lộ thông tin nhạy cảm.

Consumer nhận event có thể tồn tại nhiều phiên bản; schema compatibility phải được kiểm tra để không làm mất event khi producer nâng cấp. Thay field từ integer thành string, đổi ý nghĩa PAID hoặc bỏ field bắt buộc là thay đổi phá hợp đồng dù outbox publish thành công.

## 26. Dữ liệu trùng, mất và sai thứ tự: phân loại rõ

| Triệu chứng | Nguồn có thể | Cơ chế bảo vệ |
| --- | --- | --- |
| Order tồn tại nhưng không có event | DB commit rồi app crash trước publish | Atomic Order+outbox |
| Event có nhưng Order không tồn tại | Publish trước commit/rollback | Chỉ publish intent đã commit |
| Cùng eventId xuất hiện hai lần | Publisher retry sau ACK mất | Consumer inbox/idempotency |
| Hai eventId cho một checkout | HTTP command retry tạo hai operation | Command idempotency/business key |
| Consumer cập nhật hai lần sau redelivery | Commit DB xong crash trước ACK | Inbox cùng local transaction |
| Event v3 đến trước v2 | Publish/partition/concurrency | Aggregate sequence, consumer state guard |
| Event bị bỏ quá retention | Consumer offline dài, broker log hết hạn | Recovery/backfill, retention policy |
| Event schema lỗi liên tục | Producer/consumer contract break | Registry/contract tests, DLQ, replay |
| Publish thành công nhưng workflow không xong | Downstream business rejection/timeout | Saga, trạng thái operation |
| Email/charge bị lặp | External side effect không nằm trong transaction | Operation ID, provider idempotency, reconcile |

Đừng gộp mọi triệu chứng thành “Kafka mất event”; có thể là gap ở outbox, trễ ở publisher, consumer lag hoặc state machine sai. Mỗi lớp có metric và ranh giới ownership riêng.

## 27. Java/Spring: worker polling minh họa

Một publisher có thể làm như sau:

~~~java
@Component
public class OutboxPublisher {
    private final OutboxStore store;
    private final BrokerPublisher broker;

    public OutboxPublisher(OutboxStore store, BrokerPublisher broker) {
        this.store = store;
        this.broker = broker;
    }

    @Scheduled(fixedDelayString = "\${outbox.poll.delay-ms:500}")
    public void publishBatch() {
        // claimBatch thực hiện transaction DB ngắn.
        // Mỗi record có lease token và idempotent event ID.
        List<ClaimedOutboxEvent> claimed = store.claimBatch(100);

        for (ClaimedOutboxEvent event : claimed) {
            try {
                // Chờ kết quả broker ACK, với timeout phù hợp.
                broker.publishAndConfirm(
                    event.destination(),
                    event.aggregateId(),
                    event.eventId(),
                    event.payload());

                // Mark chỉ khi lease token/version còn hợp lệ.
                store.markPublished(event.eventId(), event.claimToken());
            } catch (Exception ex) {
                store.scheduleRetry(
                    event.eventId(),
                    event.claimToken(),
                    ex.getClass().getSimpleName());
            }
        }
    }
}
~~~

Đây là pseudocode Java/Spring có interface do dự án cung cấp. Worker này chưa thể chạy độc lập khi thiếu cấu hình broker, transaction/lease implementation, retry policy và dependencies. Các điểm quan trọng:

- claimBatch mở transaction ngắn rồi commit, không giữ lock DB trong khi chờ broker.
- Worker cần một đường reclaim lease hết hạn để không bị kẹt nếu instance chết.
- BrokerPublisher phải chờ mức xác nhận publish phù hợp; client.send trả về chưa chắc broker nhận.
- Nếu broker đã nhận nhưng ACK bị mất, scheduleRetry khiến event có thể xuất hiện lại. Consumer phải dedup.
- MarkPublished và scheduleRetry cần so claimToken để tránh worker cũ ghi đè trạng thái của worker mới.
- Khi cả broker và database lỗi, worker không được âm thầm xóa event; theo dõi và hồi phục khi hệ thống có sẵn.
- Với message lớn hoặc nhiều failed attempts, có chính sách quarantine, cảnh báo và manual replay.
- Đừng dùng Scheduled để ngụ ý thứ tự tuyệt đối khi chạy nhiều replica; cần key/sequence và concurrency design.

Với Spring Kafka, một KafkaTemplate có thể được dùng trong BrokerPublisher. Cần cấu hình producer serializer, ACK policy, retries, idempotence khi phù hợp; không coi cấu hình broker là thay thế cho application-level event ID.

## 28. Một ví dụ SQL claim/lease có thể phục hồi

Worker phải xem record CLAIMED đã hết hạn như công việc có thể lấy lại, chẳng hạn quy tắc truy vấn:

~~~sql
SELECT event_id
FROM outbox_events
WHERE
  (status = 'PENDING' AND next_attempt_at <= now())
  OR
  (status = 'CLAIMED' AND claim_until < now())
ORDER BY occurred_at, event_id
FOR UPDATE SKIP LOCKED
LIMIT 100;
~~~

Một giao dịch claim phải cập nhật những record được chọn sang CLAIMED với lease token mới. Tránh hai worker đọc cùng record mà không lock/claim atomically.

Khi finalize:

~~~sql
UPDATE outbox_events
SET status = 'PUBLISHED',
    published_at = now(),
    claimed_by = NULL,
    claim_until = NULL
WHERE event_id = :event_id
  AND claimed_by = :worker_id
  AND claim_until >= now()
  AND status = 'CLAIMED';
~~~

Đây là ví dụ hình thức, không phải giải pháp fencing hoàn chỉnh: worker ID có thể tái sử dụng và điều kiện thời gian dựa trên DB clock. Hệ production nên dùng **claim token/version tăng đơn điệu hoặc UUID duy nhất cho mỗi lần claim**, atomically so sánh token trước finalize. Nếu UPDATE trả 0 row, worker phải xem mình không còn quyền finalize, không tự coi message đã được xử lý xong.

Vì publisher có thể publish xong nhưng mất lease trong lúc chờ ACK, một worker khác có thể gửi lại; đây là cửa sổ duplicate chấp nhận được, nên idempotent consumer vẫn là yêu cầu cốt lõi.

## 29. CDC với Debezium: luồng triển khai tổng quan

Một giải pháp CDC phổ biến dùng PostgreSQL logical decoding và Debezium đọc thay đổi outbox:

~~~text
Business transaction: Orders + outbox_events COMMIT
             |
             v
        PostgreSQL WAL
             |
             v
      Debezium connector
             |
             v
      Outbox event routing
             |
             v
          Kafka
             |
             v
        Consumer groups
~~~

Các bước thiết kế:

1. Database bật replication/logging cần thiết theo chính sách hạ tầng.
2. Outbox có schema ổn định với eventId, aggregate key, event type và payload.
3. Connector chỉ đọc các bảng/outbox thuộc phạm vi được phép.
4. Routing transform xác định topic và key phù hợp.
5. Checkpoint/offset được lưu có thể phục hồi.
6. Monitor connector status, restart, WAL backlog, replication slot và broker publish.
7. Chạy thử sự cố: restart connector sau commit, broker outage, schema evolution, replay.
8. Kiểm tra consumer vẫn idempotent khi message được phát lại.

Một **connector đang RUNNING không đủ chứng minh không có gap**. Phải có metric thời gian lan truyền, kiểm tra lượng event và reconciliation theo nguồn, nhất là sau backup/restore, migration database hoặc điều chỉnh replication slot.

Cần đặc biệt chú ý PostgreSQL WAL retention khi consumer CDC tụt dài; slot có thể giữ WAL và gây đầy đĩa. Đây là một failure mode vận hành khác với polling outbox.

## 30. Đảm bảo tương thích hợp đồng khi event phát muộn

Giả sử event được ghi vào outbox với schemaVersion=1 vào thứ Hai. Broker down, publisher chỉ phát lại thứ Tư, trong khi các consumer đã nâng cấp lên version 2.

Nếu consumer v2 chỉ đọc event v2, bản tin cũ bị lỗi dù việc lưu outbox và publish đều chính xác. Thiết kế reliable event transmission còn phải bao gồm:

- Consumer mới đọc được schema cũ trong retention/recovery window.
- Producer không đổi nghĩa eventType đã công bố.
- Payload của event được snapshot ở transaction gốc và không bị serialize theo trạng thái mới tùy tiện.
- Không xóa schema/version cũ trước khi backlog và DLQ liên quan hết.
- Event có timestamp để consumer xác định việc xử lý muộn có còn hợp lệ không.
- Khi event cần sequencing, có aggregateVersion và cơ chế xử lý stale event.
- Contract tests trong CI bao phủ các tổ hợp producer/consumer có thể cùng tồn tại khi replay.

Ví dụ StockReserved đã xảy ra hôm qua nhưng hôm nay reservation được giải phóng. Nếu event StockReserved hôm qua đến chậm, consumer không thể mù quáng đặt trạng thái mới nhất thành RESERVED; phải xét version/state transition.

## 31. Không nhầm delivery success và business outcome

Một event OrderPlaced có thể đã đến Payments consumer nhưng Payment bị từ chối vì thẻ không hợp lệ. Đây **không phải lỗi truyền thông điệp**. Người vận hành cần nhìn:

| Trạng thái | Hệ thống nên thể hiện |
| --- | --- |
| Order + outbox committed | Đơn đã ghi nhận |
| Event chưa published | Đang chờ truyền event |
| Event published | Broker đã nhận sự kiện |
| Command ReserveStock accepted | Đang thực hiện giữ hàng |
| StockReserved | Đã giữ hàng theo Inventory owner |
| ReservationRejected | Không thể giữ hàng vì lý do nghiệp vụ |
| PaymentAuthorized | Thanh toán đã được authorize theo hợp đồng |
| PaymentCaptured | Tiền đã được capture theo owner |
| OrderConfirmed | Ordering xác nhận điều kiện nghiệp vụ hoàn tất |

Không dùng một status SENT để mô tả các trạng thái trên. “Đã gửi event” và “đơn được giao hàng” là hai sự thật khác nhau.

## 32. Kiểm thử crash và các cửa sổ lỗi

Chỉ chạy happy path không đủ. Cần thử tắt process, làm broker chậm và gây timeout tại từng ranh giới:

| Kịch bản kiểm thử | Kết quả mong đợi |
| --- | --- |
| Outbox insert lỗi trước DB commit | Order cũng rollback |
| Order insert lỗi | Không có outbox event |
| Process kill ngay sau COMMIT | Event còn trong outbox và được phát sau restart |
| Broker unavailable 10 phút | Pending tăng, không mất event, sau recovery bắt kịp |
| Publisher nhận ACK timeout nhưng broker đã lưu | Có thể phát trùng, consumer chỉ áp dụng business effect một lần |
| Publisher kill sau ACK trước mark PUBLISHED | Khi retry vẫn giữ eventId và không nhân side effect |
| Worker claim rồi chết | Lease hết hạn, worker khác claim lại |
| Hai worker claim cùng lúc | Mỗi record được claim theo chính sách, không bị lost update |
| Consumer DB commit xong chết trước offset commit | Redelivery không cộng doanh thu hai lần |
| Message schema sai | Quarantine/DLQ, không retry vô hạn |
| Event version 3 đến trước version 2 | Consumer xử lý gap/stale theo state policy |
| HTTP CreateOrder retry cùng key | Không tạo hai Order/OrderPlaced |
| Payment gateway timeout sau capture | Không tạo capture mới không kiểm soát |
| CDC connector restart sau checkpoint bất định | Không mất event, có thể duplicate và consumer dedup |
| Outbox quá lớn | Hệ thống có backpressure/cảnh báo, không hết disk âm thầm |
| Consumer offline quá retention | Có recovery/backfill hoặc báo blocker rõ |

Test nên khẳng định **cả database state lẫn danh sách logical events và side effects**, không chỉ kiểm tra một HTTP status 200.

### Gợi ý kỹ thuật kiểm thử

- Dùng testcontainers hoặc môi trường tích hợp thật với database và broker.
- Đặt fault injection hooks sau các mốc commit/publish/ACK trong môi trường test.
- Ghi eventId và operationId để đối chiếu trước/sau crash.
- Tạo test retry và concurrent publisher để phát hiện race.
- Dùng clock/lease giả lập hoặc môi trường có khả năng điều khiển thời gian.
- Kiểm tra DLQ/replay và schema cũ khi consumer mới chạy.
- Theo dõi p95/p99 propagation và outbox pending sau lỗi.
- Xác nhận không có code path publish trước transaction commit.

## 33. Truy vết một event từ source đến destination

Một trace/log có cấu trúc:

~~~text
correlationId = checkout-888
commandId     = cmd-place-1001
orderId       = ord-1001
eventId       = evt-order-1001-v1

Ordering:
  transaction COMMIT, outbox persisted

Outbox Publisher:
  record claimed, attempt=1
  publish broker topic=order-events
  broker ACK offset=144
  outbox marked PUBLISHED

Analytics:
  eventId received
  inbox inserted
  projection committed
  consumer offset committed

Notifications:
  eventId received
  email operation created
  provider status PENDING
~~~

Nên kết hợp metrics và tracing; không log raw payload chứa số thẻ, token, mật khẩu hoặc dữ liệu cá nhân không cần thiết. CorrelationId giúp liên kết hành trình, causationId giúp hiểu event/command nào gây ra event hiện tại.

Cần có một đường điều tra: **Business state ở owner → outbox row → broker record/offset → consumer inbox → projection/workflow state**. Nếu một event có ở DB nhưng không có broker thì điều tra publisher; nếu có broker nhưng chưa có projection thì điều tra consumer, DLQ hoặc transaction.

## 34. Khôi phục khi phát hiện dữ liệu đã sai lệch

Với lỗi tồn tại trước khi triển khai outbox hoặc lỗi vận hành nghiêm trọng, có thể xảy ra Order đã commit nhưng **không có outbox row**. Bản thân outbox publisher không thể tự tạo lại một event mà nó chưa từng được yêu cầu ghi.

Cần reconciliation:

1. Xác định phạm vi business records và các version cần có event.
2. Đối chiếu log/transaction records/outbox/event store để xác định gap.
3. Chọn cách sửa: tạo integration event phục hồi, backfill read model hoặc gọi API sync do owner cung cấp.
4. Giữ eventId/operation identity nhất quán và lưu dấu hành động khôi phục.
5. Xác định semantics của recovered event: phát lại fact cũ hay snapshot hiện tại?
6. Đảm bảo consumer có thể nhận lại và không nhân side effect.
7. Chạy canary/limited replay trước khi phát toàn bộ.
8. Theo dõi lag, DLQ và state sau khôi phục.
9. Ghi incident timeline và root cause để tránh lặp.

Đừng tự tái phát mọi OrderPlaced lịch sử lên topic production mà không kiểm tra Notifications có gửi email mới cho toàn bộ khách hàng hay Payments có thu tiền lại. Replay cần giới hạn consumer, side effect và phiên bản.

## 35. Các sai lầm kiến trúc thường gặp

**Sai lầm 1 — Gọi publisher trong @Transactional rồi tin mọi thứ atomic.** Database và broker là hai resource; annotation thường không làm chúng commit nguyên tử.

**Sai lầm 2 — Publish trước DB commit.** Consumer có thể thấy fact chưa từng xảy ra sau rollback.

**Sai lầm 3 — Chỉ dùng @TransactionalEventListener AFTER_COMMIT.** Tránh publish trước commit nhưng không chịu được process crash sau commit.

**Sai lầm 4 — Dùng outbox nhưng event payload lại đọc trạng thái mới nhất sau nhiều giờ.** Event không còn thể hiện snapshot fact ban đầu.

**Sai lầm 5 — Dùng random eventId ở mỗi retry.** Consumer không dedup được logical event đã gửi trước đó.

**Sai lầm 6 — ACK consumer trước khi commit projection.** Crash làm mất tiến độ chưa áp dụng.

**Sai lầm 7 — Commit inbox trước business side effect.** Khi crash, event bị coi đã xử lý dù effect chưa xảy ra.

**Sai lầm 8 — Tin broker exactly-once áp dụng được tới payment gateway.** Bảo đảm broker có phạm vi, external API cần idempotency/reconciliation.

**Sai lầm 9 — Claim outbox mà không có lease recovery.** Worker chết giữ CLAIMED vĩnh viễn.

**Sai lầm 10 — Dọn outbox PENDING vì quá cũ.** Mất thông điệp cho một transaction đã commit.

**Sai lầm 11 — Không giám sát tuổi event pending.** Outbox tích tụ nhiều ngày nhưng application vẫn trả HTTP 201 bình thường.

**Sai lầm 12 — Xóa schema v1 khi vẫn còn outbox v1.** Consumer mới không xử lý được event phát muộn.

**Sai lầm 13 — Chỉ bảo đảm publish, không xử lý redelivery.** Analytics cộng doanh thu hoặc Notifications gửi email hai lần.

**Sai lầm 14 — Publish command và event có tên giống nhau.** Consumer không biết đó là yêu cầu hành động hay fact đã xảy ra, dẫn đến side effect trùng.

**Sai lầm 15 — Chỉ chạy integration test khi các service đều mới.** Không bắt được event/schema cũ còn nằm trong outbox hoặc broker.

**Sai lầm 16 — Coi outbox giải quyết toàn bộ saga.** Một bước payment bị từ chối vẫn đòi compensation/timeout và business state rõ ràng.

**Sai lầm 17 — Chọn global order cho mọi event.** Gây bottleneck không cần thiết; nên xác định thứ tự theo aggregate hoặc workflow nếu đủ.

**Sai lầm 18 — Retry vô hạn không giới hạn tải.** Khi broker trở lại, một làn sóng publish có thể làm consumer và DB downstream quá tải.

## 36. Bài thực hành: OrderPlaced không mất, không nhân đôi doanh thu

Bối cảnh:

- Ordering ghi Order và cần phát OrderPlaced.
- Analytics cộng doanh thu theo đơn.
- Notifications tạo yêu cầu gửi email xác nhận.
- Broker có thể mất kết nối 5 phút.
- Producer hoặc consumer có thể bị kill ở bất kỳ mốc nào.
- Không được ghi đơn rồi mất event; không được cộng doanh thu hai lần.
- Email cần hạn chế gửi trùng; downstream provider có idempotency hay không chưa chắc chắn.

### Yêu cầu thiết kế

1. Vẽ các cửa sổ lỗi khi DB commit trước publish và khi publish trước DB commit.
2. Thiết kế bảng outbox có eventId, aggregateId/version, eventType, schemaVersion, payload và trạng thái phát.
3. Viết local transaction tạo Order và outbox atomically.
4. Chọn polling hay CDC, giải thích vì sao.
5. Mô tả publisher retry khi ACK timeout và khi crash sau broker ACK.
6. Xây inbox/idempotency cho Analytics.
7. Thiết kế Notification operation key và cách xử lý gateway timeout.
8. Đưa ra cách giữ thứ tự OrderPlaced/OrderCancelled.
9. Chọn metric cảnh báo khi backlog vượt SLO.
10. Lập kịch bản fault injection tại các mốc DB commit, broker ACK và consumer commit.
11. Thiết kế recovery nếu event cũ không còn trong broker retention.
12. Phân biệt “đã tạo Order” với “đã thanh toán/gửi email” trên UI.

### Một lời giải tham khảo

~~~text
PlaceOrder HTTP
  -> validate + command idempotency
  -> local transaction:
       insert Order
       insert Outbox(OrderPlaced, fixed eventId)
     commit
  -> return Order created, workflow PENDING

Outbox publisher
  -> claim/poll or CDC
  -> publish OrderPlaced
  -> on ambiguous ACK retry same eventId

Analytics consumer
  -> local transaction:
       insert processed(eventId) unique
       increment/update projection only on first insert
     commit
  -> ACK/commit offset

Notifications consumer
  -> local transaction:
       insert email_operation(orderId, type) unique
     commit
  -> durable worker sends to email provider with stable key if supported
  -> persist result/reconcile before retrying ambiguous effect
~~~

Với cách này, broker outage không bắt buộc làm mất OrderPlaced vì outbox record còn bền vững. Nhưng nếu DB hết dung lượng do backlog, ứng dụng vẫn phải có backpressure/alert. Với email provider không hỗ trợ idempotency, phải nêu giới hạn bảo đảm thay vì hứa tuyệt đối không bao giờ gửi trùng.

## 37. Checklist thiết kế và phát hành reliable event transmission

1. **Owner:** Service nào sở hữu business state và fact event?
2. **Atomicity boundary:** Dữ liệu và outbox có thật sự cùng DB transaction?
3. **Event identity:** eventId được tạo một lần và ổn định qua retry?
4. **Command idempotency:** Request HTTP gửi lại có tạo nhiều logical operations không?
5. **Payload:** Event là snapshot chính xác lúc commit, không đọc dữ liệu tương lai?
6. **Version:** Schema/version/aggregate sequence có hợp đồng rõ?
7. **Publisher:** Polling hay CDC? Ai chịu trách nhiệm vận hành?
8. **Claim/recovery:** Worker chết có thể claim lại không? Lease/fencing an toàn?
9. **ACK policy:** Mark published dựa trên broker confirmation nào?
10. **Ambiguous outcome:** ACK mất thì có chấp nhận duplicate và dedup được không?
11. **Consumer:** Inbox/processed ID cùng local transaction với effect?
12. **External effects:** Payment/email/shipping API có idempotency và reconciliation?
13. **Ordering:** Cần thứ tự theo aggregate nào? Key/sequence bảo vệ thế nào?
14. **Retention:** Outbox/broker/DLQ có đủ thời gian recovery không?
15. **Error handling:** Retry backoff, poison message và DLQ được giám sát?
16. **Backpressure:** Broker outage kéo dài có làm database đầy không?
17. **Observability:** Pending age, publish errors, consumer lag và business completion có SLO?
18. **Security:** ACL, credentials, payload PII và log có được bảo vệ?
19. **Compatibility:** Consumer mới có đọc event cũ phát chậm được không?
20. **Testing:** Có crash/kill tests ở trước-sau các mốc commit/ACK?
21. **Runbook:** Có manual replay/reconciliation an toàn, không nhân side effects?
22. **Business state:** UI nói rõ accepted, committed, pending downstream và completed?
23. **Cleanup:** Có cách xóa/archive outbox an toàn sau mốc xác nhận?
24. **Boundary:** Team có phân biệt local atomicity với end-to-end delivery và final business outcome?

---

**Nguyên tắc cần nhớ:** Hai thao tác “ghi database” và “gửi thông điệp” đến hai resource độc lập **không trở nên nguyên tử chỉ vì được đặt cạnh nhau trong code hoặc chung @Transactional**. Nếu ghi DB trước, có thể mất event; nếu gửi trước, có thể phát event giả. **Transactional outbox** đưa business state và message intent vào cùng local commit để loại bỏ khoảng trống đó; **publisher/CDC** phát lại từ trạng thái bền vững; **consumer idempotent/inbox** chống nhân đôi tác động khi redelivery; **saga/reconciliation** giải quyết phần nghiệp vụ và nguồn ngoài database. Thiết kế tin cậy cần nêu rõ phạm vi bảo đảm, thử crash thật và đo thời gian phục hồi thay vì tuyên bố exactly-once một cách chung chung.