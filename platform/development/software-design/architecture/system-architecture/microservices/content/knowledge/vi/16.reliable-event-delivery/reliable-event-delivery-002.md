# Transactional Outbox và ranh giới giao dịch với dữ liệu nghiệp vụ

## Mục tiêu bài học

Trong Microservices, một service thường vừa thay đổi dữ liệu nghiệp vụ vừa cần thông báo thay đổi cho những service khác. Ví dụ Order Service lưu đơn hàng mới vào database, sau đó phát sự kiện OrderCreated để Inventory Service giữ tồn kho và Analytics Service cập nhật báo cáo. Hai thao tác này tưởng như là một công việc, nhưng thực chất nằm trên **hai hệ thống có ranh giới giao dịch khác nhau**: database của Order và message broker.

Nếu viết dữ liệu xong rồi publish sự kiện, service có thể crash giữa hai bước: đơn hàng đã tồn tại nhưng không consumer nào nhận được tin. Nếu publish trước khi commit dữ liệu, consumer có thể nhận một sự kiện về đơn hàng sau đó bị rollback. Việc chỉ đặt cả hai dòng code trong một method có @Transactional không tự giải quyết được hai khoảng lỗi này.

**Transactional Outbox** là mẫu thiết kế ghi **dữ liệu nghiệp vụ và ý định phát thông điệp** vào **cùng một local database transaction**. Một tiến trình khác đọc outbox và đưa thông điệp lên broker. Nó giúp bảo vệ quan hệ “nghiệp vụ đã commit thì có bản ghi sự kiện để phát”, nhưng **không tạo transaction ACID xuyên database và broker**, và cũng không loại bỏ khả năng broker nhận trùng message.

Sau bài học, bạn có thể:
- Giải thích ranh giới atomicity giữa business data, outbox, relay, broker và consumer.
- Phân tích vì sao hai lệnh “save vào DB” và “publish event” không tự atomic.
- Thiết kế outbox table và ghi nó cùng dữ liệu nghiệp vụ trong một transaction cục bộ.
- So sánh relay bằng polling và Change Data Capture (CDC).
- Bảo vệ dữ liệu khi relay crash trước/sau publish, khi message trùng hoặc consumer xử lý lỗi.
- Thiết kế identity, ordering, schema evolution, retry, retention và quan sát backlog.
- Triển khai các mẫu SQL và Spring Boot/Java, đồng thời xây bộ kiểm thử lỗi theo thời điểm.

## 1. Bối cảnh: dữ liệu nghiệp vụ phải đi cùng sự kiện

Một checkout có thể bắt đầu như sau:

~~~text
Client
   |
   v
Order Service
   |                     +--> Inventory Service
   |                     |
   +--> Orders DB        +--> Notification Service
   |                     |
   +--> Broker ----------+--> Analytics Service
~~~

Khi client tạo order-471, Order Service có hai trách nhiệm liên quan:

1. Lưu Order(id=order-471, status=PENDING) như trạng thái nghiệp vụ có thẩm quyền.
2. Đưa thông điệp OrderCreated(orderId=order-471) đến hệ thống phân phối sự kiện.

Nếu chỉ hoàn thành bước 1 mà quên bước 2, Inventory không biết cần giữ hàng. Nếu chỉ hoàn thành bước 2 mà bước 1 rollback, consumer có thể xử lý một đơn không tồn tại.

Business invariant có thể được diễn đạt thành:

> Với mỗi Order được commit thành công, phải có một ý định phát OrderCreated bền vững để quy trình downstream có thể tiếp tục.

Invariant này **chưa yêu cầu mọi consumer hoàn tất tức thời**. Nó yêu cầu không đánh mất nguyên nhân khởi động workflow khi transaction của Order thành công.

### 1.1. Sự khác nhau giữa business record và event record

**Business record** là trạng thái có thẩm quyền trong service, ví dụ Order, Payment hoặc InventoryReservation.

**Outbox record** lưu thông tin cần thiết để phát một sự kiện hoặc command ra ngoài service; nó là **ý định giao tiếp đã được commit**, không phải một bản sao khác có quyền sửa business state.

Một row Order có thể có trạng thái PENDING trong khi outbox event vẫn ở trạng thái NEW. Điều đó hoàn toàn hợp lệ: dữ liệu nghiệp vụ đã được commit và event chưa được relay.

## 2. Vì sao cách publish trực tiếp tạo dual-write problem?

Xét code:

~~~java
@Transactional
public void createOrder(CreateOrderCommand command) {
    orderRepository.save(Order.pending(command));
    kafkaTemplate.send("orders", toOrderCreated(command));
}
~~~

Hai dòng code có thể nằm trong cùng một method, nhưng không mặc định thuộc cùng một đơn vị atomic commit.

### 2.1. Ghi database trước rồi mới publish

~~~text
T0  Begin DB transaction
T1  Insert Order(PENDING)
T2  COMMIT Orders DB
T3  Process crash
T4  Chưa publish OrderCreated
~~~

Ở T2, Order đã được lưu. Tại T3, tiến trình bị dừng trước khi broker có message. Một controller retry không phải luôn xảy ra; ngay cả khi client retry, nó có thể phát sinh một order mới hoặc bị dedup. Sự kiện gốc vẫn có thể mất nếu không có nơi lưu ý định publish.

### 2.2. Publish trước rồi mới commit

~~~text
T0  Begin DB transaction
T1  Publish OrderCreated lên broker
T2  Broker nhận và ACK
T3  DB transaction lỗi và ROLLBACK
T4  Consumer xử lý OrderCreated
~~~

Consumer có thể nhìn thấy một Order không tồn tại trong source of truth. Một broker ACK không buộc Orders DB commit.

### 2.3. Chờ future publish cũng chưa loại bỏ được lỗi

Giả sử code gọi send(...).get() và đợi broker ACK trước khi commit DB. Đường đi vẫn có thể là:

~~~text
Broker ACK success
       |
       v
DB commit fails
~~~

Đảo lại, nếu commit DB trước rồi chờ ACK, vẫn có thể mất thông điệp khi process crash. Nếu broker đã nhận nhưng ACK bị mất, ứng dụng còn có thể publish lại và gây duplicate.

**Vấn đề nằm ở hai resource có commit độc lập**, không phải chỉ ở việc dùng synchronous hay asynchronous API.

### 2.4. @Transactional bảo vệ những resource nào?

Trong một ứng dụng Spring Boot dùng một DataSource, @Transactional thường điều khiển transaction của database thông qua transaction manager được cấu hình. Kafka, RabbitMQ, REST API, object storage và email provider không tự tham gia cùng local DB transaction chỉ vì code của chúng được gọi từ method đó.

Một số framework hỗ trợ phối hợp transaction giữa resource ở mức nhất định; phải hiểu rõ ranh giới và failure guarantees. Không nên coi bất kỳ dạng synchronization nào cũng tương đương atomic commit xuyên DB và broker.

## 3. Transactional Outbox đặt ranh giới atomicity ở đâu?

Luồng chuẩn:

~~~text
           Order Service
                 |
                 v
          BEGIN local DB tx
                 |
       +---------+----------+
       |                    |
       v                    v
INSERT/UPDATE Order    INSERT OutboxEvent
       |                    |
       +---------+----------+
                 |
                 v
           COMMIT DB
                 |
                 v
             Orders DB
                 |
                 v
          Outbox relay/CDC
                 |
                 v
              Broker
                 |
                 v
       Inventory / Analytics
~~~

**Đơn vị atomic được bảo đảm là business write + outbox write trong cùng một database transaction.**

Vì hai record cùng nằm trong local transaction, những trường hợp quan trọng có kết quả:

| Kết quả local DB transaction | Business state | Outbox intent |
| --- | --- | --- |
| Commit thành công | Có | Có |
| Rollback | Không có thay đổi của transaction đó | Không có record intent của transaction đó |
| Application crash trước commit | DB phục hồi theo transaction semantics | Cùng chung kết quả với business state |
| Crash sau commit | Business state tồn tại | Intent vẫn tồn tại, relay có thể tiếp tục |

Sau commit, việc phát event ra broker là một thao tác **riêng**, có thể retry từ dữ liệu đã lưu.

### 3.1. Outbox bảo đảm điều gì?

Trong phạm vi triển khai đúng:
- Không bị mất **ý định publish** chỉ vì process crash sau khi commit nghiệp vụ.
- Không phát một sự kiện từ outbox cho một transaction đã rollback.
- Có thể tách phát thông điệp khỏi thời gian chờ của HTTP request.
- Có checkpoint/status để relay phục hồi sau restart.
- Có cơ sở quan sát các thông điệp còn chờ hoặc thất bại.

### 3.2. Outbox không bảo đảm điều gì?

- Không tự tạo atomic commit giữa Orders DB và Kafka.
- Không tự bảo đảm message chỉ xuất hiện một lần trên broker.
- Không buộc mọi consumer xử lý sự kiện thành công.
- Không ngăn consumer xử lý trùng nếu thiếu idempotency.
- Không bảo đảm thứ tự toàn cục giữa nhiều service và nhiều partition.
- Không làm một API thanh toán bên ngoài trở nên idempotent.
- Không thay đổi sự thật rằng read model downstream có thể cập nhật trễ.
- Không ngăn event schema thay đổi phá tương thích consumer.

Tóm lại, outbox **di chuyển vấn đề từ “có thể mất sự kiện vĩnh viễn” sang “có thể phát lại sự kiện đã lưu”**. Phát lại được là một lợi thế rất lớn, nhưng consumer phải được thiết kế để chịu duplicate.

## 4. Thiết kế bảng business data và outbox

Ví dụ một cơ sở dữ liệu thuộc Order Service:

~~~sql
CREATE TABLE orders (
    id VARCHAR(100) PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    customer_id VARCHAR(100) NOT NULL,
    status VARCHAR(40) NOT NULL,
    total_minor BIGINT NOT NULL,
    currency VARCHAR(3) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE outbox_events (
    event_id VARCHAR(100) PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload TEXT NOT NULL,
    status VARCHAR(30) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP,
    lease_owner VARCHAR(100),
    lease_until TIMESTAMP,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP
);
~~~

Đây là schema minh họa. Data types, indexing, status/lease model, timezone, lock semantics và retention phải được chọn theo database cụ thể.

### 4.1. Những trường outbox đáng chú ý

| Trường | Vai trò |
| --- | --- |
| event_id | Identity ổn định để dedup và điều tra |
| aggregate_type | Domain entity hoặc aggregate mà event liên quan |
| aggregate_id | Khóa cho partitioning và per-aggregate ordering |
| aggregate_version | Phiên bản trạng thái, hỗ trợ loại bỏ event cũ |
| event_type | Tên sự kiện theo hợp đồng tích hợp |
| schema_version | Phiên bản payload để consumer hiểu đúng |
| payload | Nội dung integration event đã được đóng gói |
| status | NEW, CLAIMED, PUBLISHED hoặc trạng thái vận hành |
| attempt_count | Số lần relay thử gửi |
| next_attempt_at | Thời điểm retry tiếp theo |
| lease_owner, lease_until | Hỗ trợ nhiều relay workers, nếu dùng polling |
| created_at, published_at | Đo backlog và thời gian từ commit đến publish |
| tenant_id | Scope, quota, quyền và truy vết |

Không nhất thiết mọi implementation đều phải có các trường status/lease. Một CDC relay đọc transaction log có thể không cần polling status như trên.

### 4.2. Identity và ordering

Event ID phải giữ nguyên qua retry; nếu relay tạo event ID mới ở mỗi lần publish, consumer khó nhận diện một sự kiện bị gửi lại.

Aggregate ID giúp phân vùng messages theo entity. Nếu Order 471 thay đổi từ PENDING sang CONFIRMED, consumer cần thứ tự có ý nghĩa giữa OrderCreated và OrderConfirmed. Aggregate version/sequence là công cụ hữu ích, nhưng cần phối hợp với broker partitioning, publisher concurrency và consumer behavior.

### 4.3. Payload là hợp đồng, không phải database entity

Không nên serialize thẳng JPA entity hoặc toàn bộ bảng orders ra event. Nếu thêm cột mới vào database, consumer sẽ vô tình bị ảnh hưởng. Một integration event nên chứa các trường consumer có quyền và cần sử dụng:

~~~json
{
  "eventId": "evt-order-471-created",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-12T02:00:00Z",
  "aggregateId": "order-471",
  "aggregateVersion": 1,
  "tenantId": "tenant-A",
  "data": {
    "orderId": "order-471",
    "customerId": "customer-91",
    "totalMinor": 159900,
    "currency": "VND"
  }
}
~~~

Payload ở ví dụ là một hợp đồng tích hợp; trong hệ thống thật cần chính sách về thông tin cá nhân, dữ liệu tài chính, schema registry và retention.

## 5. SQL transaction: nghiệp vụ và outbox cùng commit

Một ví dụ create order:

~~~sql
BEGIN;

INSERT INTO orders (
    id, tenant_id, customer_id, status,
    total_minor, currency, version, created_at, updated_at
) VALUES (
    'order-471', 'tenant-A', 'customer-91', 'PENDING',
    159900, 'VND', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
);

INSERT INTO outbox_events (
    event_id, tenant_id, aggregate_type, aggregate_id,
    aggregate_version, event_type, schema_version,
    payload, status, created_at
) VALUES (
    'evt-order-471-created',
    'tenant-A', 'Order', 'order-471',
    1, 'OrderCreated', 1,
    '{"orderId":"order-471","status":"PENDING"}',
    'NEW', CURRENT_TIMESTAMP
);

COMMIT;
~~~

Hai câu INSERT phải dùng **cùng transaction của cùng database connection/transaction manager**. Nếu chỉ ghi outbox sau khi business transaction đã commit, ta lại tạo đúng khoảng lỗi ban đầu.

### 5.1. Không gọi broker trong ranh giới này để thay thế outbox

Transactional Outbox không yêu cầu service publish ngay trước commit. Thường nên:
1. Validate nghiệp vụ.
2. Ghi trạng thái domain.
3. Ghi outbox record tương ứng.
4. Commit nhanh.
5. Trả response theo contract.
6. Để relay/CDC phát event sau đó.

Giữ database transaction ngắn giúp giảm lock contention và connection hold time. Chờ broker, HTTP downstream hoặc retry bên trong transaction có thể giữ tài nguyên lâu mà vẫn không loại bỏ dual-write problem.

### 5.2. Cập nhật dữ liệu nghiệp vụ phải đi cùng event thích hợp

Ví dụ xác nhận đơn:

~~~sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = 'order-471'
  AND status = 'PENDING'
  AND version = 1;

-- Chỉ ghi OrderConfirmed nếu UPDATE thật sự chuyển trạng thái
-- và nghiệp vụ đã đủ điều kiện xác nhận.

INSERT INTO outbox_events (
    event_id, tenant_id, aggregate_type, aggregate_id,
    aggregate_version, event_type, schema_version,
    payload, status, created_at
) VALUES (
    'evt-order-471-confirmed',
    'tenant-A', 'Order', 'order-471',
    2, 'OrderConfirmed', 1,
    '{"orderId":"order-471","status":"CONFIRMED"}',
    'NEW', CURRENT_TIMESTAMP
);

COMMIT;
~~~

SQL chỉ minh họa hai thao tác trong một transaction. Trong implementation thật phải **kiểm tra số dòng đã cập nhật bằng 1 trước khi ghi outbox**; nếu không, một state transition không hợp lệ vẫn có thể tạo event. Event cũng cần xác định từ trạng thái domain có thẩm quyền, không tự suy ra từ request chưa được commit.

## 6. Spring Boot: lưu Order cùng outbox bằng một local transaction

Một mẫu ứng dụng:

~~~java
public record CreateOrderCommand(
    String orderId,
    String tenantId,
    String customerId,
    long totalMinor,
    String currency
) {}

public record OrderCreatedPayload(
    String orderId,
    String customerId,
    long totalMinor,
    String currency
) {}

public interface OrderRepository {
    void save(Order order);
}

public interface OutboxRepository {
    void save(OutboxEvent event);
}
~~~

Use case:

~~~java
@Service
public class CreateOrderUseCase {
    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final EventIdFactory ids;
    private final Clock clock;

    public CreateOrderUseCase(
            OrderRepository orders,
            OutboxRepository outbox,
            EventIdFactory ids,
            Clock clock) {
        this.orders = orders;
        this.outbox = outbox;
        this.ids = ids;
        this.clock = clock;
    }

    @Transactional
    public void create(CreateOrderCommand cmd) {
        Order order = Order.pending(
                cmd.orderId(), cmd.tenantId(),
                cmd.customerId(), cmd.totalMinor(),
                cmd.currency(), clock.instant());

        orders.save(order);

        OutboxEvent event = OutboxEvent.newEvent(
                ids.forOrderCreated(order.id()),
                cmd.tenantId(),
                "Order",
                order.id(),
                order.version(),
                "OrderCreated",
                1,
                new OrderCreatedPayload(
                        order.id(), order.customerId(),
                        order.totalMinor(), order.currency()),
                clock.instant());

        outbox.save(event);
    }
}
~~~

Đây là ví dụ cấu trúc, không phải code độc lập có đầy đủ model/repository/serializer. Điều cần giữ đúng:
- OrderRepository và OutboxRepository cùng sử dụng **một transaction manager và DataSource thuộc cùng nguồn dữ liệu**.
- Khi lỗi ở một insert, transaction rollback toàn bộ phần business write và outbox.
- Không nuốt exception khiến transaction commit ngoài ý muốn.
- Nếu command trùng do retry, cần business idempotency/unique constraint để không tạo Order và event mới vô hạn.
- Tạo event dựa trên domain transition đã chấp nhận, không dựa trên request chưa được xác minh.

### 6.1. Cạm bẫy về transaction của Spring

Có thể thấy annotation @Transactional nhưng transaction không được áp dụng như dự kiến nếu gọi phương thức nội bộ qua self-invocation hoặc cấu hình transaction manager chưa đúng. Một số trường hợp dùng nhiều DataSources phải chỉ rõ manager và phân tách ranh giới dữ liệu.

Thay vì chỉ nhìn annotation, hãy kiểm tra bằng integration test rằng hai insert thật sự cùng commit/rollback. Điều này thuộc kiểm tra **kỹ thuật transactional guarantee**, không phải việc thêm nhiều annotation cho yên tâm.

### 6.2. Không sửa event payload sau commit

Outbox record nên biểu diễn một sự kiện bất biến có event ID và schema version rõ. Nếu relay mỗi lần thử lại query dữ liệu Order hiện tại để tạo lại payload, retry của OrderCreated có thể chứa thông tin đã thay đổi sau đó, làm consumer khó tái tạo trạng thái tại thời điểm sự kiện.

Có hai lựa chọn có chủ đích:
- Lưu payload immutable vào outbox ngay trong transaction.
- Lưu một representation đủ bền vững rồi derive ra integration payload theo version/semantics có bảo đảm.

Không lấy “dữ liệu mới nhất” để thay cho “sự kiện đã xảy ra” nếu contract đòi giá trị tại thời điểm xảy ra.

## 7. Điều gì xảy ra khi service crash?

Xét từng điểm:

~~~text
A: BEGIN
B: Save Order
C: Save Outbox
D: COMMIT DB
E: Relay read Outbox
F: Broker receives event
G: Broker ACK reaches relay
H: Relay marks PUBLISHED
I: Consumer processes event
J: Consumer commits local result
K: Consumer ACKs broker
~~~

| Vị trí lỗi | Hệ quả | Cơ chế phục hồi |
| --- | --- | --- |
| Trước COMMIT | Transaction rollback hoặc DB phục hồi theo ACID | Không có event orphan nếu cùng transaction |
| Sau COMMIT, trước relay | Order + outbox bền vững | Relay đọc lại từ outbox |
| Relay đã đọc, chưa publish | Outbox vẫn còn | Retry sau lease hoặc lần poll tiếp |
| Broker nhận, ACK bị mất | Relay không chắc đã publish | Retry có thể phát trùng |
| Broker ACK rồi relay crash trước đánh dấu PUBLISHED | Message đã có trên broker, outbox chưa đánh dấu | Relay phát lại; consumer phải dedup |
| Relay đánh dấu PUBLISHED | Event không nên mất nếu ACK thật sự có nghĩa durable theo broker contract | Theo dõi broker retention, consumer health |
| Consumer commit rồi crash trước ACK | Broker có thể redeliver | Inbox/idempotent domain handler |
| Consumer lỗi trước commit | Local DB rollback | Broker redelivery hoặc retry theo policy |

Bảng trên cho thấy **mỗi cặp hệ thống có khoảng lỗi riêng**. Transactional Outbox xử lý tốt khoảng lỗi đầu tiên giữa business DB và message intent, nhưng relay/consumer vẫn cần thiết kế theo delivery semantics thực tế.

### 7.1. Không thể giải quyết bằng “mark sent trước”

Nếu relay đánh dấu PUBLISHED trong DB **trước khi** broker xác nhận nhận event:

~~~text
Mark PUBLISHED → Crash → Chưa gửi event
~~~

Bản ghi không còn được retry và sự kiện có thể mất.

Nếu relay đánh dấu PUBLISHED **sau** broker ACK:

~~~text
Broker ACK → Crash → Chưa mark PUBLISHED
~~~

Sự kiện có thể bị publish lại, nhưng không bị mất chỉ vì local relay crash. Đây thường là đánh đổi ưu tiên **at-least-once publication + idempotent consumer**.

### 7.2. Broker ACK phải được hiểu theo cấu hình

Một send() call trả thành công từ thư viện không phải lúc nào cũng đồng nghĩa message đã được lưu bền theo yêu cầu. Với Kafka, cấu hình acknowledgments và producer idempotence/durability phải được hiểu đúng; với RabbitMQ, cần biết publisher confirms, queue durability và delivery mode phù hợp.

Outbox không thể bù cho việc broker ACK một message nhưng sau đó mất message do cấu hình durability yếu, retention không phù hợp hoặc vận hành sai. Reliability là kết quả của **cả chuỗi cam kết**, không chỉ một bảng outbox.

## 8. Relay bằng polling

Một cách triển khai là một worker định kỳ đọc những event chưa publish:

~~~text
Outbox table --poll--> Relay worker --publish--> Broker
                              |
                              +-- mark published
~~~

Luồng:
1. Tìm các record NEW đến hạn retry.
2. Claim một batch bằng cơ chế concurrency-safe.
3. Publish từng event dùng chính event ID, key và payload đã lưu.
4. Chờ broker ACK theo contract.
5. Mark PUBLISHED sau khi ACK.
6. Khi lỗi, tăng attempt và lên lịch retry có backoff.
7. Khi worker crash, lease hết hạn và worker khác có thể reclaim.

### 8.1. Claim batch đúng khi nhiều relay chạy đồng thời

Với database hỗ trợ cú pháp tương ứng, có thể dùng một query kiểu:

~~~sql
SELECT event_id
FROM outbox_events
WHERE (
    status = 'NEW'
    OR (status = 'CLAIMED' AND lease_until < CURRENT_TIMESTAMP)
)
  AND (next_attempt_at IS NULL OR next_attempt_at <= CURRENT_TIMESTAMP)
ORDER BY created_at, event_id
LIMIT 100
FOR UPDATE SKIP LOCKED;
~~~

Đây là SQL mang tính minh họa; cú pháp và semantics của SKIP LOCKED, LIMIT, row locking và isolation phụ thuộc database. Worker cần claim records bằng transaction ngắn, lưu lease owner/lease until, rồi commit claim **trước khi** chờ broker send.

Không giữ một SQL transaction/row lock mở suốt lời gọi mạng tới broker trong vài giây hoặc vài phút. Điều đó làm contention và connection hold time tăng, nhưng không tạo atomic commit giữa DB và broker.

### 8.2. Mẫu claim → publish → acknowledge

~~~text
Local transaction:
  Claim batch and set lease
COMMIT

For each claimed event:
  Publish with stable event_id
  Await broker acknowledgement

Local transaction:
  Mark PUBLISHED
COMMIT
~~~

Nếu process crash sau publish nhưng trước mark PUBLISHED, event có thể được phát lại. Vì vậy relay phải thiết kế để **phát lại an toàn**, không cố tuyên bố exactly-once giữa hai commits.

### 8.3. Khi lease hết hạn nhưng worker cũ vẫn chạy

Một worker có thể tạm dừng vì GC hoặc network, lease hết hạn, rồi worker thứ hai claim cùng event. Cả hai có thể publish. Có thể giảm rủi ro bằng owner token, claim generation/fencing token và thời gian lease hợp lý, nhưng **không thể dựa vào lease để thay thế consumer idempotency**.

Cần tránh worker cũ ghi trạng thái PUBLISHED cho claim mới nếu việc đó phá logic quản lý. Một UPDATE có điều kiện owner/claim generation có thể bảo vệ record state.

### 8.4. Poll interval và batch size

Poll mỗi vài mili giây có thể tăng query load; poll quá thưa gây độ trễ sự kiện lớn. Batch quá lớn có thể giữ nhiều events trong lease, làm tail latency cao khi worker crash.

Các tham số cần đo:
- Poll interval.
- Batch size.
- Max concurrent publishes.
- Lease TTL.
- Broker ACK timeout.
- Retry backoff và jitter.
- Số outbox rows đang pending.
- Publish throughput và backlog age.

Cân bằng với workload, database CPU/I/O và broker capacity thay vì chọn một giá trị “chuẩn” cho mọi hệ thống.

## 9. Relay bằng Change Data Capture (CDC)

Một lựa chọn khác là CDC đọc thay đổi từ transaction log của database và chuyển outbox inserts thành messages.

~~~text
Business + Outbox COMMIT
          |
          v
Database transaction log
          |
          v
CDC connector (ví dụ Debezium)
          |
          v
Event mapping / outbox router
          |
          v
Message broker
~~~

Ưu điểm tiềm năng:
- Không cần poll table liên tục theo interval.
- Có thể phát hiện committed inserts gần thời gian thực.
- Tận dụng ordering trong transaction log của database.
- Giảm lượng query polling, tùy tải và cách triển khai.

Nhưng CDC **không tự động giải quyết mọi vấn đề**:
- Connector phải lưu và phục hồi offset.
- Transaction log/WAL/binlog có retention và storage cost.
- Replication slot hoặc connector chậm có thể khiến log tích tụ.
- Event routing/serialization phải có contract ổn định.
- Khi broker lỗi, connector lag tăng.
- Khi thay đổi schema outbox, connector mapping cũng phải tương thích.
- Consumer vẫn có thể nhận message trùng khi restart/replay.

### 9.1. Không đồng nhất raw CDC với integration event

Nếu một consumer trực tiếp subscribe vào CDC của bảng orders, nó sẽ phụ thuộc vào cột database nội bộ. Khi Order Service đổi schema, consumer có thể hỏng dù business contract không đổi.

Mẫu outbox dùng CDC làm cơ chế **đọc outbox record đã được thiết kế như integration event**, thay vì phát toàn bộ thay đổi của domain table ra bên ngoài.

### 9.2. Polling hay CDC?

| Tiêu chí | Polling relay | CDC relay |
| --- | --- | --- |
| Độ phức tạp ban đầu | Có thể đơn giản hơn | Cần connector/log configuration |
| Độ trễ | Phụ thuộc interval/batch | Có thể thấp, phụ thuộc lag |
| Tải database | Query bảng thường xuyên | Đọc log và quản lý retention |
| Ordering | Phải thiết kế claim/publish order | Có thứ tự theo log trong phạm vi nguồn, vẫn cần broker mapping |
| Retry | Worker tự quản lý | Connector/offset và downstream retry |
| Khả năng vận hành | Worker/lease/index | Connector health, log slot, offsets |
| Khả năng phát trùng | Có | Có thể |
| Phù hợp | Hệ thống đơn giản hoặc kiểm soát tốt polling | Khối lượng lớn/độ trễ thấp khi có năng lực CDC |

Chọn theo khả năng vận hành và các cam kết cụ thể. Cả hai đều bắt đầu từ cùng nguyên tắc: **business state và outbox intent được commit atomically trong local database**.

## 10. Ordering: outbox không tự bảo đảm thứ tự toàn cục

Giả sử Order Service phát:

~~~text
OrderCreated(order-471, version=1)
OrderConfirmed(order-471, version=2)
OrderCancelled(order-471, version=3)
~~~

Một relay có nhiều worker, broker nhiều partitions, consumer song song có thể làm thứ tự nhận khác thứ tự tạo nếu không có chính sách. Có thể xảy ra:
- Worker A claim event v1 nhưng publish chậm.
- Worker B claim event v2 và publish trước.
- Consumer nhận v2 trước v1.

### 10.1. Thứ tự theo aggregate

Thường chỉ cần thứ tự trong cùng aggregate, không cần total global order cho mọi Order.

Giải pháp có thể gồm:
1. Mỗi aggregate có version/sequence tăng theo transaction.
2. Đưa cùng aggregateId làm partition key để broker hỗ trợ ordering theo key.
3. Điều khiển relay concurrency và claim order theo aggregate.
4. Consumer kiểm tra version; không áp dụng event cũ lên state mới.
5. Xử lý gaps: đợi/retry, query authoritative source hoặc rebuild projection.
6. Có quy tắc khi event bị mất khỏi retention hoặc state bị xóa.

### 10.2. Sequence phải được cấp atomically

Không đủ nếu hai concurrent transactions tự đếm số event rồi cùng đặt version=5. Cần bảo vệ bằng aggregate row version, optimistic locking hoặc sequence allocation phù hợp trong local DB transaction.

Một event version có thể lấy từ domain aggregate sau transition đã commit. Nếu transaction rollback, version và event đó không nên trở thành sự thật nghiệp vụ.

### 10.3. Broker ordering có phạm vi

Kafka thường duy trì thứ tự trong một partition, không bảo đảm tổng thứ tự giữa partitions. Một topic dùng aggregateId làm key có thể hữu ích, nhưng consumer rebalance/retry/side effects vẫn phải xử lý idempotency và event version. Không xem partition ordering là bằng chứng không có duplicate.

## 11. Consumer cần inbox/idempotency

Đường đi hoàn chỉnh:

~~~text
Order DB:
  Order + Outbox --atomic COMMIT
          |
          v
Relay -> Broker (may publish again)
          |
          v
Inventory Consumer
          |
          v
Inventory DB:
  Inbox + Reservation --atomic COMMIT
~~~

Consumer có thể nhận event nhiều lần vì:
- Relay phát lại sau ACK mơ hồ.
- Broker redelivery sau consumer crash.
- Consumer xử lý xong nhưng ACK message bị mất.
- Replay data để rebuild service.
- Người vận hành chủ động phát lại sự kiện.

### 11.1. Inbox table

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong một local Inventory transaction:
1. Xác minh event schema/tenant/business conditions.
2. Claim eventId trong inbox theo unique constraint.
3. Nếu đã xử lý, trả thành công idempotent.
4. Nếu chưa xử lý, thực hiện reservation theo business key.
5. Commit inbox record và business changes cùng nhau.
6. ACK broker theo contract.

Nếu consumer crash sau local commit nhưng trước ACK, broker có thể redeliver; inbox bảo vệ bước đã commit.

### 11.2. SQL ví dụ với business invariant

~~~sql
CREATE TABLE reservations (
    reservation_id VARCHAR(100) PRIMARY KEY,
    order_id VARCHAR(100) NOT NULL,
    sku VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL,
    status VARCHAR(30) NOT NULL,
    UNIQUE (order_id, sku)
);
~~~

Unique (order_id, sku) chỉ là ví dụ. Nếu nghiệp vụ cho phép nhiều reservations cùng SKU cho các fulfillment attempts khác nhau, khóa đúng có thể là (order_id, sku, reservation_purpose) hoặc một business operation ID khác.

Không nên dựa hoàn toàn vào eventId để chặn side effect trùng nếu upstream có thể phát hai event IDs khác nhau cho cùng ý định nghiệp vụ. Cần cả **message deduplication** và **business idempotency**.

### 11.3. Xử lý event trùng phải không gây tác động phụ

Nếu consumer thấy event đã xử lý, nó không được lại trừ tồn hoặc tạo shipment. Có thể trả ACK an toàn sau khi xác định transaction trước đã thành công.

Đặc biệt, không lưu inbox riêng trước rồi mới ghi reservation ở một transaction khác; nếu crash giữa hai bước, lần redelivery sẽ tưởng event đã xử lý dù business effect chưa xảy ra.

## 12. At-least-once và “exactly once” cần hiểu đúng phạm vi

Một cách diễn giải thực tế:
- **At-most-once:** có thể mất message nhưng thường không cố phát lại.
- **At-least-once:** retry tới khi có xác nhận theo policy; message có thể trùng.
- **Exactly-once trong phạm vi cụ thể:** một nền tảng có thể bảo đảm một số thao tác transactional hoặc state update theo phạm vi của nó.

Transactional Outbox thường được kết hợp với **at-least-once publication** từ relay. Nó không biến side effect của consumer thành đúng một lần nếu consumer không idempotent.

Ngay cả khi broker có tính năng exactly-once đối với producer/stream processing, việc trừ tiền ở PSP, ghi SQL ở database ngoài hoặc gửi email vẫn có transaction boundary khác.

Thay vì tuyên bố “chính xác một lần end-to-end”, nên mô tả **business invariant được bảo vệ**:
- Một OrderCreate intent chỉ tạo một Order.
- Một ReserveInventory intent không giảm available hai lần.
- Một PaymentCapture intent không capture hai lần.
- Một event state transition không áp dụng lặp khi đã commit.
- Một workflow có thể recover sau duplicate và crash.

## 13. Event identity, correlation và contract

Một outbox message nên chứa các metadata phục vụ cả transport và nghiệp vụ:

| Metadata | Mục đích |
| --- | --- |
| eventId | Stable dedup identity |
| eventType | Ý nghĩa nghiệp vụ của event |
| schemaVersion | Quy tắc đọc payload |
| aggregateId | Correlation/partitioning |
| aggregateVersion | Per-aggregate ordering |
| occurredAt | Thời điểm nghiệp vụ được ghi nhận |
| correlationId | Liên kết các bước của workflow |
| causationId | Event/command dẫn tới event hiện tại |
| tenantId | Scope dữ liệu và bảo mật |
| traceparent | Liên kết distributed tracing, nếu cần |
| producerService | Quyền sở hữu, vận hành, audit |

Không nên dùng thời điểm system clock giữa nhiều service để thiết lập **total ordering** tuyệt đối: clock có thể lệch. Sequence/version có ý nghĩa trong một bounded context thường tốt hơn khi ordering quan trọng.

### 13.1. Event là fact đã xảy ra, không phải ý định chưa thực hiện

Ví dụ:
- OrderCreated: Order đã được commit thành công.
- InventoryReserved: reservation đã được commit.
- PaymentAuthorized: payment service đã có kết luận có thẩm quyền theo contract.
- RequestInventoryReservation có thể là command, không phải fact Inventory đã reserve.

Đặt tên event phải phản ánh điểm commit. Nếu phát OrderConfirmed trước khi Order transaction commit, message đang tuyên bố một sự thật chưa được xác nhận.

### 13.2. Không expose aggregate nội bộ

Domain model có thể thay đổi không đồng bộ với consumer. Integration event cần một schema stable, versioned và giới hạn thông tin. Không serialize toàn bộ ORM entity, lazy-loaded relations hoặc password/token/PII không cần thiết.

## 14. Event schema evolution

Khi Order Service thêm currency và bỏ một trường cũ, consumer có thể chưa nâng cấp. Bản ghi outbox tồn tại theo phiên bản payload tại lúc local commit, và relay có thể publish sau nhiều phút hoặc giờ.

Vì vậy:
- Schema version phải được lưu cùng event.
- Consumer có thể cần hỗ trợ old and new versions trong compatibility window.
- Không xóa serializer/decoder cũ khi backlog vẫn chứa payload cũ.
- Cần kiểm tra dữ liệu replay từ retention hoặc archive.
- Thay đổi semantics nghiệp vụ cũng phải được quản lý, không chỉ type.
- Schema registry/AsyncAPI có thể hỗ trợ governance nhưng không tự phát hiện mọi semantic break.

### 14.1. Ví dụ additive change

Payload v1:

~~~json
{
  "orderId": "order-471",
  "totalMinor": 159900
}
~~~

Payload v2:

~~~json
{
  "orderId": "order-471",
  "totalMinor": 159900,
  "currency": "VND"
}
~~~

Thêm field có thể tương thích nếu consumer cũ cho phép unknown fields và không cần đổi semantics; nhưng một strict JSON parser có thể reject field mới. Contract tests phải phản ánh hành vi thực của consumers.

### 14.2. Đừng đổi đơn vị hoặc ý nghĩa field âm thầm

Nếu totalMinor đang là số đơn vị nhỏ nhất của tiền tệ mà producer bắt đầu gửi một đơn vị khác dưới cùng field, hệ thống có thể sai dù JSON schema vẫn hợp lệ. Đó là breaking semantic change.

## 15. Retry và xử lý thông điệp lỗi

Không phải lỗi publish nào cũng giống nhau.

**Transient:**
- Broker tạm unavailable.
- Network timeout.
- Throttling.
- Connection reset.

Những lỗi này thường phù hợp retry với backoff/jitter và retry budget.

**Permanent hoặc cần can thiệp:**
- Payload không serialize được theo contract.
- Topic không tồn tại do cấu hình.
- Message quá lớn so với giới hạn broker.
- Authorization bị từ chối.
- Schema version không được chấp nhận.
- Dữ liệu nội bộ không hợp lệ.

Không nên lặp lại vô hạn một event poison mà không báo động.

### 15.1. Retry policy minh họa

~~~text
Initial attempt  -> failed
Retry 1: +1 second + jitter
Retry 2: +3 seconds + jitter
Retry 3: +10 seconds + jitter
Retry 4: +30 seconds + jitter
...
Max attempts / max age / manual review
~~~

Các con số chỉ là ví dụ; chính sách phụ thuộc SLA, latency, broker, loại event và mức quan trọng. Một OrderCreated cần tiến trình downstream sớm có thể ưu tiên alert và khả năng phục hồi khác với AnalyticsUpdate ít cấp thiết.

### 15.2. Dead-letter queue và outbox stuck records

Khi event không thể publish do lỗi không phục hồi tự động, có thể chuyển trạng thái FAILED hoặc gửi vào dead-letter path. Nhưng DLQ không phải “giải quyết xong”:
- Cần owner, alert và quy trình điều tra.
- Không tự xóa event có business effect chưa được xử lý.
- Replay phải giữ identity phù hợp để dedup.
- Sửa payload hoặc schema phải có audit, phê duyệt khi cần.
- Cần phân biệt retry của relay với retry ở consumer.

Một hệ thống “không mất message” nhưng để event nằm trong DLQ nhiều tuần vẫn có thể vi phạm business SLA.

## 16. Giữ bảng outbox không phình vô hạn

Outbox liên tục tăng khi service có nhiều giao dịch. Nếu không có retention và cleanup, bảng trở nên lớn, index nặng và polling chậm.

Các biện pháp:
- Index theo status, next_attempt_at và created_at phù hợp query.
- Dọn record PUBLISHED theo retention đã thống nhất.
- Partition bảng theo thời gian hoặc tenant nếu volume lớn, tùy database.
- Thực hiện cleanup theo batch, không dùng delete khổng lồ gây lock.
- Theo dõi disk utilization, index bloat và replication lag.
- Nếu cần audit lịch sử, lưu vào hệ thống audit/archive riêng, không mặc định giữ mọi record trong hot outbox mãi mãi.

### 16.1. Không xóa record NEW chỉ vì quá cũ

Một event NEW đã chờ ba ngày có thể là sự kiện quan trọng chưa được publish. Dọn theo TTL mà không xét status có thể làm mất intent. Cleanup phải phân biệt PUBLISHED, FAILED và NEW/CLAIMED quá hạn.

Nếu event vẫn không thể publish, cần quy trình xử lý/khôi phục, không xóa để metric backlog “đẹp” hơn.

### 16.2. Purge chỉ khi đủ bằng chứng

Status PUBLISHED nghĩa là broker ACK theo contract, không có nghĩa mọi consumer đã xử lý. Nếu business yêu cầu chứng minh consumer hoàn tất, cần tracking/workflow confirmation riêng. Đừng dùng outbox retention như bằng chứng end-to-end processing.

## 17. Backpressure giữa DB, relay và broker

Giả sử Order Service tạo 20.000 events mỗi giây nhưng relay chỉ publish 5.000 events mỗi giây. Outbox backlog sẽ tăng dù mọi business transaction vẫn commit thành công.

~~~text
Business transactions --> Outbox table --> Relay --> Broker
      20k/s                 growing         5k/s
~~~

Đây là **queueing/throughput problem**, không phải một lỗi SQL transaction.

Các phương án:
- Tăng số relay workers hoặc throughput CDC, nếu broker và DB chịu được.
- Điều chỉnh batch size, polling interval và network/TLS settings.
- Phân vùng events theo aggregate/tenant, bảo toàn ordering cần thiết.
- Giới hạn hoặc trì hoãn một số non-critical writes khi downstream đã quá tải theo policy.
- Xác định khả năng buffer tối đa và SLA cho event delivery.
- Theo dõi outbox oldest age và khả năng catch-up sau broker outage.
- Hạn chế lưu payload không cần thiết quá lớn.

### 17.1. Scale relay có đánh đổi ordering

Tăng worker concurrency có thể giúp throughput nhưng tăng nguy cơ event v2 được publish trước v1 nếu cùng aggregate. Khi ordering quan trọng, cần chiến lược claim và partitioning phù hợp, không chỉ tăng số workers.

### 17.2. Backpressure không tự sinh từ một bảng SQL

Outbox table là nơi lưu bền intent, nhưng không tự gửi tín hiệu demand tới Order Service. Nếu backlog có thể vượt storage budget, hệ thống cần chính sách chủ động: cảnh báo sớm, quota, admission control hoặc chuyển chế độ giảm tải theo mức độ business impact.

## 18. Quan sát và SLO cho outbox

Các metrics hữu ích:

| Chỉ số | Ý nghĩa |
| --- | --- |
| outbox_pending_count | Số events chưa publish |
| outbox_oldest_pending_age | Event cũ nhất đang chờ bao lâu |
| outbox_publish_latency | Thời gian từ business commit tới broker ACK |
| outbox_publish_attempts | Số attempt trên mỗi event |
| outbox_publish_errors | Lỗi theo broker/topic/reason |
| outbox_relay_throughput | Số events/s được ACK |
| outbox_claimed_expired | Số leases hết hạn cần reclaim |
| outbox_poison_event_count | Số events không thể tự publish |
| broker_consumer_lag | Consumer chậm bao nhiêu so với broker |
| consumer_duplicate_count | Số events được dedup thành công |
| consumer_processing_errors | Lỗi domain/integration ở consumer |
| end_to_end_workflow_age | Bao lâu một Order mới được reserve/confirm |
| db_outbox_size | Disk usage, rows/index size |
| cdc_connector_lag | CDC đã theo kịp transaction log chưa |

### 18.1. Đừng chỉ đo số messages sent

Một dashboard cho thấy relay gửi 10.000 messages/phút không đủ chứng minh an toàn nếu vẫn có 2.000 events NEW lâu hơn SLA hoặc consumer lag tăng liên tục.

Cần phân biệt:
1. **Local commit thành công**.
2. **Event intent đã lưu trong outbox**.
3. **Broker đã ACK publish**.
4. **Consumer đã commit xử lý**.
5. **Business workflow cuối đã hoàn tất**.

Mỗi bước có nguồn sự thật và metrics riêng.

### 18.2. Alerts theo tuổi backlog

Tổng pending count hữu ích nhưng tuổi bản ghi cũ nhất thường phản ánh mức độ trễ nghiệp vụ tốt hơn. Một backlog nhỏ với một event quan trọng kẹt nhiều giờ có thể đáng báo động hơn backlog lớn vừa hình thành trong burst.

Nên có alert riêng cho event quan trọng như PaymentAuthorized hoặc OrderCreated, và phân tách các luồng Analytics ít cấp thiết nếu kiến trúc cần ưu tiên.

## 19. Bảo mật, quyền dữ liệu và phân quyền database

Trong một hệ thống multi-tenant:
- Outbox payload có thể chứa dữ liệu nghiệp vụ nhạy cảm; chỉ lưu trường cần thiết.
- Outbox table phải có access control phù hợp; không cho mọi service đọc trực tiếp.
- Relay credential có quyền đọc/đổi trạng thái outbox và publish vào topic được cho phép, không có quyền DDL rộng nếu không cần.
- Consumer không được coi eventId là chứng cứ quyền truy cập; phải xác minh tenant/context.
- Tracing/logging không nên dump toàn bộ payload có PII hoặc secrets.
- Broker ACL, encryption in transit/at rest và retention cần được cấu hình theo dữ liệu.
- Event replay phải bảo vệ quyền và audit, đặc biệt khi consumer cũ không còn được phép truy cập data.

Không dùng outbox như đường vòng để công khai raw database schema. Integration event phải do service sở hữu business contract quyết định.

## 20. Outbox và mô hình Saga

Saga có thể dùng outbox để phát events/commands đáng tin sau từng local step:

~~~text
Order DB:
  Create Order(PENDING) + Outbox(OrderCreated)
           |
           v
       Broker
           |
           v
Inventory DB:
  Reserve + Outbox(InventoryReserved)
           |
           v
       Broker
           |
           v
Payment DB:
  Mark request + Outbox(PaymentAuthorizationRequested)
           |
           v
       Payment processing / PSP
~~~

Saga và outbox giải quyết **hai vấn đề khác nhau**:
- Saga: quản lý trình tự các bước nghiệp vụ, trạng thái trung gian, timeout và compensation.
- Outbox: đảm bảo ý định gửi thông điệp tương ứng với local transaction đã commit không bị mất giữa DB và broker.

Một Saga có thể dùng outbox; outbox một mình không tạo Saga. Nếu Payment thất bại sau khi Inventory đã reserve, cần compensation ReleaseReservation và state machine. Outbox chỉ giúp phát các command/events tương ứng một cách tin cậy.

### 20.1. Command hay event?

**Event:** thông báo sự kiện đã xảy ra, ví dụ InventoryReserved.

**Command:** yêu cầu một service thực hiện việc gì, ví dụ ReserveInventory.

Cả hai có thể được lưu ở outbox dưới dạng message intent để gửi qua broker. Nhưng contract phải phân biệt: publish ReserveInventory command không có nghĩa Inventory đã reserve. Chỉ khi Inventory commit reservation và phát InventoryReserved mới có bằng chứng sự kiện đó xảy ra.

### 20.2. Trạng thái UNKNOWN vẫn tồn tại

Outbox không giải quyết tình huống Payment gọi PSP và response bị mất. Payment Service phải dùng stable provider reference, idempotency và reconciliation với PSP. Outbox có thể phát PaymentAuthorized **sau khi** Payment đã có kết quả có thẩm quyền và commit nó cục bộ.

Không phát PaymentAuthorized chỉ vì đã gửi request đến PSP.

## 21. Outbox và read models/eventual consistency

Analytics hoặc Search Service có thể xây projection từ events. Khi Order commit ở 10:00 và event được publish ở 10:00:02, một search index có thể đến 10:00:05 mới phản ánh đơn mới.

~~~text
Orders DB     COMMITTED Order
Outbox        NEW -> PUBLISHED
Broker        Has OrderCreated
Search index  Still old -> catches up
~~~

Đây là độ trễ nhất quán giữa source of truth và read model.

Nếu client vừa tạo Order và cần lập tức nhìn thấy chính Order đó:
- Có thể đọc trực tiếp Order Service khi cần read-your-writes.
- Có thể trả OrderId/representation từ command response.
- Có thể cung cấp operation status.
- Có thể dùng version token hoặc read model watermark nếu hệ thống hỗ trợ.

Không mặc định một projection eventual consistent là nguồn quyết định business invariant mạnh như “đã giữ tồn chưa?” hoặc “đã thu tiền chưa?” nếu có độ trễ.

## 22. Tích hợp trực tiếp REST và sự kiện

Một service có thể vừa gọi REST đồng bộ vừa phát event bất đồng bộ. Cần xác định business ownership:

~~~text
Order Service
  |
  +-- Local COMMIT Order(PENDING) + Outbox(OrderCreated)
  |
  +-- Optionally GET Customer profile for validation
  |
  +-- Event drives Inventory workflow
~~~

Nếu một HTTP downstream call nằm trong local transaction, nó vẫn không tham gia COMMIT của DB nếu không có distributed transaction thật. Cần tách transaction boundary và quản lý timeout/unknown outcome.

Một nguyên tắc thiết kế hữu ích:
- Nếu cần kết quả đồng bộ để quyết định có cho phép commit business state không, hãy cân nhắc nơi invariant được sở hữu và cách lấy dữ liệu trước transaction.
- Nếu việc downstream có thể xảy ra sau commit, lưu event/command intent vào outbox.
- Nếu downstream có side effect quan trọng, dùng idempotency và status inquiry.
- Nếu toàn bộ workflow phải giữ invariants tức thời không thể bù trừ, xem lại ranh giới service thay vì ép outbox giải quyết điều nó không bảo đảm.

## 23. Những sai lầm phổ biến

**“Đã dùng @Transactional thì publish Kafka cùng COMMIT DB.”** Không đúng trong cấu hình local transaction thông thường. Resource broker có failure window riêng.

**“Outbox đảm bảo exactly-once end-to-end.”** Không. Relay có thể publish trùng sau crash hoặc ACK mơ hồ; consumer phải idempotent.

**“Outbox event là bản sao database row.”** Không nên. Integration event cần business contract, quyền dữ liệu và schema version riêng.

**“Publish trước rồi DB commit cũng ổn nếu broker nhanh.”** Không. Consumer có thể xử lý sự kiện của transaction bị rollback.

**“Mark PUBLISHED trước send để tránh duplicate.”** Nguy hiểm: crash sau mark nhưng trước send làm mất event.

**“Mark PUBLISHED sau send là tuyệt đối không trùng.”** Không: broker ACK có thể xảy ra trước crash, còn DB mark chưa commit.

**“Nhiều relay workers sẽ tự giữ thứ tự.”** Không. Cần per-aggregate sequencing/partitioning hoặc consumer version guards.

**“Cứ để outbox table tăng mãi để có audit.”** Có thể làm polling, index và storage quá tải; audit và hot outbox có mục đích khác nhau.

**“DELETE các events quá ba ngày là dọn dẹp tốt.”** Sai nếu chúng chưa publish. Retention phải dựa vào status/ack và chính sách dữ liệu.

**“CDC luôn tốt hơn polling.”** Không có đáp án chung; CDC cần vận hành log, offsets, connector lag và recovery.

**“Broker exactly-once làm consumer SQL không cần idempotency.”** Sai phạm vi. SQL/PSP side effects vẫn có transaction boundary độc lập.

**“Outbox tự giải quyết Saga và compensation.”** Không. Saga cần state machine, deadline, trạng thái trung gian và bước bù trừ.

**“Có event ID là đủ chống trùng nghiệp vụ.”** Chưa chắc. Cùng business intent có thể bị upstream phát dưới nhiều event IDs nếu nguồn không idempotent; cần unique business key.

**“Broker ACK đồng nghĩa mọi consumer đã xử lý.”** Không. ACK publish và consumer completion là những mốc khác nhau.

**“Sau khi commit Order thì event phải đến mọi consumer ngay.”** Outbox hỗ trợ eventual reliable delivery theo hoạt động của relay/broker; vẫn có độ trễ, backlog và lỗi cần phục hồi.

## 24. Kiểm thử kỹ thuật theo từng điểm lỗi

Chỉ test happy path OrderCreated đến Inventory là chưa đủ. Nên có fault injection và assertions về dữ liệu.

### Case 1 — Transaction nghiệp vụ rollback

Cho OrderRepository throw hoặc constraint failure sau khi chuẩn bị event. Kỳ vọng: không có Order mới và không có outbox event orphan.

### Case 2 — Outbox insert thất bại

Cho outbox INSERT fail trước commit. Kỳ vọng: Order INSERT cũng rollback, client nhận lỗi phù hợp và có thể retry theo business identity.

### Case 3 — Crash ngay sau local COMMIT

Dừng Order process trước khi relay chạy. Kỳ vọng: Order + outbox vẫn tồn tại; relay sau restart phát được OrderCreated.

### Case 4 — Broker unavailable

Outbox tiếp tục giữ NEW/CLAIMED và worker retry có backoff; sau khi broker phục hồi, events được publish. Backlog age và lỗi publish phải có metric/alert.

### Case 5 — Broker nhận event, response ACK mất

Relay retry cùng eventId. Kỳ vọng: consumer idempotent và business side effect chỉ xảy ra một lần.

### Case 6 — Relay crash trước mark PUBLISHED

Broker đã ACK, relay crash. Sau lease expire, event có thể được phát lại. Không mất dữ liệu và không tạo duplicate reservation.

### Case 7 — Hai relay workers đồng thời claim

Cho hai workers cạnh tranh. Kỳ vọng: claim/lease state hợp lệ, không có một record bị permanently stuck; nếu duplicate publish do lease race, consumer vẫn an toàn.

### Case 8 — Consumer crash sau local commit trước ACK

Inventory đã tạo reservation nhưng broker redeliver. Kỳ vọng: inbox/business constraint không trừ tồn lần hai.

### Case 9 — Event v2 đến trước v1

Kỳ vọng: consumer áp version guard, retry/rebuild theo policy, không ghi đè aggregate mới bằng state cũ.

### Case 10 — Schema v1 còn trong backlog khi code lên v2

Kỳ vọng: relay có thể gửi payload v1 và consumer mới vẫn hiểu theo compatibility window.

### Case 11 — Poison event

Payload không hợp lệ hoặc topic/ACL cấu hình sai. Kỳ vọng: retry không vô hạn trong im lặng, có trạng thái lỗi, alert, owner và kênh xử lý.

### Case 12 — Broker outage kéo dài

Outbox tích tụ nhiều rows. Kỳ vọng: database còn dung lượng, backlog được quan sát, có quota/giảm tải và khả năng catch-up sau recovery.

### Case 13 — Tenant isolation

Hai tenants có aggregateId trùng nhau. Kỳ vọng: event scope và consumer authorization đúng; không lộ payload cross-tenant.

### Case 14 — Outbox cleanup

Dọn records đã publish theo retention. Kỳ vọng: không xóa NEW/FAILED chưa xử lý, không phá khả năng replay cần thiết.

### Case 15 — Local transaction dài

Giả lập broker chậm và kiểm tra use case createOrder không giữ database transaction chờ broker ACK. Kỳ vọng: thời gian giữ lock/connection theo local DB operations, không theo broker latency.

**Tiêu chí thành công cốt lõi:** mọi business transaction đã commit đều có intent tương ứng; không phát event của transaction rollback; duplicate publication không nhân đôi side effect; eventual delivery có thể quan sát và phục hồi.

## 25. Checklist triển khai Transactional Outbox

- [ ] Đã xác định service sở hữu business data và database?
- [ ] Business write và outbox insert nằm trong cùng local transaction?
- [ ] Không publish trực tiếp như cơ chế duy nhất rồi hy vọng hai resource atomic?
- [ ] Event được tạo từ business transition đã chấp nhận?
- [ ] Event ID ổn định và duy nhất theo contract?
- [ ] Payload/schema version được lưu bền, không tự biến đổi theo DB mới nhất?
- [ ] Có aggregateId, aggregateVersion và ordering policy phù hợp?
- [ ] Có index/batch size và công cụ polling/CDC hợp lý?
- [ ] Có recovery khi relay process crash?
- [ ] Mark PUBLISHED chỉ sau broker ACK phù hợp?
- [ ] Có retry backoff/jitter và xử lý poison events?
- [ ] Có lease/concurrent claim safety hoặc CDC offsets/recovery?
- [ ] Consumer dùng inbox/dedup trong local business transaction?
- [ ] Business idempotency bảo vệ duplicate intent ngoài eventId?
- [ ] Có policy về schema evolution và historical replay?
- [ ] Có security policy cho outbox payload, topic ACL và tenant scope?
- [ ] Có giới hạn DB storage và cleanup chỉ cho events đủ điều kiện?
- [ ] Có metrics oldest_pending_age, retries, errors, throughput, consumer lag?
- [ ] Có alert và owner cho events bị stuck/FAILED?
- [ ] Có fault injection ở các thời điểm COMMIT/ACK/crash/redelivery?
- [ ] Có phân biệt “broker đã nhận” với “consumer đã xử lý”?
- [ ] Các Saga/commands downstream vẫn có idempotency, status query và compensation?

## 26. Bài tập tình huống

### Bài 1 — Crash giữa DB và Kafka

Order Service commit đơn hàng rồi crash trước kafkaTemplate.send().

**Câu hỏi:** Điều gì bị mất và outbox sửa bằng cách nào?

*Gợi ý:* Không mất Order mà mất ý định phát event nếu chỉ lưu trong RAM. Ghi Order và OutboxEvent trong cùng local transaction, để relay phục hồi sau restart.

### Bài 2 — Broker ACK rồi relay crash

Relay publish OrderCreated, broker ACK, relay crash trước UPDATE status=PUBLISHED.

**Câu hỏi:** Relay khởi động lại nên làm gì? Consumer cần cơ chế gì?

*Gợi ý:* Retry cùng eventId vì chưa có xác nhận local mark. Consumer dùng inbox và business unique constraint; không thể dựa vào publish một lần tuyệt đối.

### Bài 3 — Publish trước commit

Service gửi InventoryReservationRequested rồi DB transaction tạo Order rollback.

**Câu hỏi:** Vì sao sự kiện này không còn cùng nguồn sự thật? Phương án sửa?

*Gợi ý:* Không gửi command từ transaction chưa commit; lưu message intent trong outbox và publish sau local COMMIT.

### Bài 4 — Hai relay workers

Hai worker cùng select 100 rows NEW rồi publish trùng và cùng cập nhật status.

**Câu hỏi:** Cần cơ chế concurrency nào?

*Gợi ý:* Atomic claim, row locking/lease hoặc một CDC pipeline; owner token và idempotent consumer. Không dựa vào read-then-update không có guard.

### Bài 5 — Event ordering

OrderCreated v1 và OrderConfirmed v2 đi lên broker theo thứ tự ngược do hai relay worker.

**Câu hỏi:** Thiết kế nào giúp giữ hoặc tái dựng thứ tự đúng?

*Gợi ý:* Aggregate sequence/version, partition key, policy claim/publish và consumer version guard/gap handling.

### Bài 6 — Backlog ba ngày

Broker outage làm outbox có một triệu events NEW; một cleanup job xóa rows cũ hơn 48 giờ.

**Câu hỏi:** Có an toàn không?

*Gợi ý:* Không. Cleanup không được xóa intent chưa publish; cần backlog capacity, alert, retry/recovery và retention theo status.

### Bài 7 — Dữ liệu nhạy cảm trong event

Service lưu toàn bộ CustomerEntity (kể cả PII nội bộ) vào outbox và publish cho mọi consumer.

**Câu hỏi:** Sai ở đâu?

*Gợi ý:* Outbox payload phải là integration contract tối thiểu, có authorization/ACL và privacy retention, không phải raw entity.

### Bài 8 — Consumer đã commit nhưng broker redelivery

Inventory consumer ghi reservation rồi crash trước message ACK.

**Câu hỏi:** Làm sao không trừ kho hai lần?

*Gợi ý:* Inbox record và reservation trong cùng local transaction, có unique business key và idempotent transition.

### Bài 9 — “Đã phát sự kiện” có phải “đã hoàn tất checkout”?

OrderCreated outbox status=PUBLISHED nhưng Inventory vẫn chưa reserve.

**Câu hỏi:** Có được trả Order.CONFIRMED?

*Gợi ý:* Không. Broker publish ACK chỉ xác nhận mốc gửi; phải có bằng chứng từng bước của Saga hoặc authoritative reservation/payment status.

### Bài 10 — Polling hay CDC?

Một service nhỏ tạo 20 events/giây và team không vận hành connector CDC. Một hệ thống lớn tạo hàng chục nghìn events/giây, có platform CDC.

**Câu hỏi:** Hai bối cảnh nên đánh giá giải pháp thế nào?

*Gợi ý:* Cân nhắc SLO, độ trễ, khối lượng, polling DB cost, CDC log/offset retention và năng lực vận hành. Đừng mặc định một kỹ thuật luôn tốt hơn.

## 27. Kết luận

**Transactional Outbox giải quyết khoảng trống quan trọng giữa local database COMMIT và ý định phát thông điệp ra ngoài.** Khi business record và outbox event được lưu trong **cùng một ACID transaction**, chúng cùng commit hoặc cùng rollback. Process có thể crash sau commit mà không làm mất dấu vết sự kiện cần phát, vì relay/CDC có thể đọc lại outbox để tiếp tục.

Nhưng sau COMMIT, broker, relay và consumer vẫn ở các ranh giới giao dịch khác. **Message có thể được phát trùng; consumer có thể crash sau commit trước ACK; sự kiện có thể đến muộn hoặc khác thứ tự.** Vì thế một thiết kế tin cậy cần kết hợp outbox với stable event ID, polling/CDC recovery, retry/backoff, per-aggregate ordering, inbox/idempotent consumer, business constraints, schema compatibility, monitoring và quy trình xử lý backlog.

Nguyên tắc thực hành: **Điều nào phải atomic với dữ liệu nghiệp vụ thì hãy ghi trong cùng local database transaction; điều nào đi qua network/broker thì phải chấp nhận failure windows và thiết kế cơ chế phát lại, chống trùng và phục hồi có thể kiểm chứng.**
