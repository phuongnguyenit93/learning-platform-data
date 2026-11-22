# Ghi sự kiện cùng dữ liệu nghiệp vụ bằng transactional outbox

Một dịch vụ thường phải vừa cập nhật database vừa thông báo cho hệ thống khác. Ví dụ, khi xác nhận đơn hàng, ứng dụng đổi `orders.status` thành `CONFIRMED` và publish event `OrderConfirmed` lên message broker để dịch vụ kho, thanh toán hoặc thông báo tiếp tục xử lý.

Hai thao tác này thường dùng hai tài nguyên độc lập: database và broker. Transaction ACID của database không tự bao trùm lệnh publish. Nếu ứng dụng commit database trước rồi crash trước khi publish, dữ liệu đã đổi nhưng event bị mất. Nếu publish trước rồi database rollback, consumer có thể nhận một event mô tả thay đổi chưa từng được commit.

**Transactional outbox** giải quyết khoảng trống này bằng cách ghi dữ liệu nghiệp vụ và bản ghi sự kiện vào cùng một database transaction. Một relay riêng đọc outbox sau commit và chuyển sự kiện đến broker. Nếu transaction rollback, cả thay đổi nghiệp vụ lẫn event đều không tồn tại; nếu transaction commit, event đã được lưu bền vững để relay có thể gửi sau đó.

Outbox thường cung cấp khả năng phát event ít nhất một lần (at-least-once). Relay có thể publish thành công rồi crash trước khi đánh dấu bản ghi đã gửi, nên duplicate vẫn có thể xảy ra. Consumer cần idempotency hoặc inbox để bảo vệ hiệu ứng nghiệp vụ. Outbox giải quyết tính nguyên tử giữa ghi database và lưu ý định phát event; nó không tạo ra một transaction phân tán bao trùm mọi hệ thống.

## 1. Vấn đề dual-write

Giả sử API xác nhận một đơn hàng cần thực hiện:

1. Cập nhật trạng thái đơn hàng trong database.
2. Publish `OrderConfirmed` lên broker.

Nếu hai thao tác không nằm trong cùng một giao dịch phân tán, ứng dụng phải chọn thứ tự. Cả hai thứ tự đều có một cửa sổ lỗi.

### Database commit trước, publish sau

```text
BEGIN
  UPDATE orders SET status = 'CONFIRMED'
COMMIT
        |
        v
Ứng dụng crash trước khi publish
        |
        v
Database đã CONFIRMED, nhưng không có event
```

Hệ thống nguồn cho rằng đơn hàng đã xác nhận, trong khi các dịch vụ phụ thuộc không nhận được thông báo. Nếu không có cơ chế phục hồi, trạng thái giữa các dịch vụ bị lệch vĩnh viễn.

### Publish trước, database commit sau

```text
Publish OrderConfirmed thành công
        |
        v
Ứng dụng crash hoặc database rollback
        |
        v
Consumer nhận event, nhưng đơn hàng chưa CONFIRMED
```

Consumer có thể gửi thông báo, giữ hàng hoặc tạo hóa đơn dựa trên một sự kiện không tương ứng với trạng thái đã commit. Nếu ứng dụng retry, event còn có thể được gửi nhiều lần.

### Vì sao try/catch không giải quyết được?

`try/catch` chỉ xử lý lỗi mà tiến trình còn sống và nhận biết được. Nó không thể chạy phần bù khi máy bị tắt đột ngột, mất điện, process bị kill hoặc kết nối bị ngắt sau khi hệ thống đích đã nhận dữ liệu. Retry cũng không loại bỏ được khoảng thời gian giữa hai thao tác.

Muốn bảo đảm thay đổi nghiệp vụ và ý định phát event cùng tồn tại hoặc cùng biến mất, cả hai phải được ghi trong một transaction mà cùng một database quản lý. Đó là vai trò của outbox.

## 2. Cấu trúc transactional outbox

Outbox là một bảng nằm trong cùng database với dữ liệu nghiệp vụ. Mỗi hàng outbox đại diện cho một sự kiện mà dịch vụ cần phát sau khi transaction commit.

Ví dụ schema theo cú pháp gần với MySQL:

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE outbox_events (
    event_id CHAR(36) NOT NULL,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    aggregate_version BIGINT NULL,
    event_type VARCHAR(150) NOT NULL,
    schema_version INT NOT NULL,
    payload JSON NOT NULL,
    occurred_at TIMESTAMP(6) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    published_at TIMESTAMP(6) NULL,
    attempts INT NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP(6) NULL,
    last_error TEXT NULL,
    PRIMARY KEY (event_id),
    KEY ix_outbox_pending (published_at, next_attempt_at, created_at)
) ENGINE = InnoDB;
```

Các trường có ý nghĩa:

| Trường | Mục đích |
|---|---|
| `event_id` | Định danh duy nhất, ổn định của event; consumer dùng để deduplicate. |
| `aggregate_type`, `aggregate_id` | Xác định đối tượng nghiệp vụ phát event, ví dụ `Order` và `42`. |
| `aggregate_version` | Phiên bản hoặc sequence của aggregate, hữu ích khi cần phát hiện event sai thứ tự. |
| `event_type` | Tên loại sự kiện, ví dụ `OrderConfirmed`. |
| `schema_version` | Phiên bản cấu trúc payload để consumer biết cách giải mã. |
| `payload` | Nội dung event đủ để consumer xử lý hoặc tham chiếu dữ liệu cần thiết. |
| `occurred_at` | Thời điểm nghiệp vụ xảy ra theo nguồn tạo event. |
| `published_at` | Thời điểm relay ghi nhận đã publish thành công theo giao thức của ứng dụng. |
| `attempts`, `next_attempt_at`, `last_error` | Hỗ trợ retry và quan sát lỗi publish. |

Schema thực tế có thể dùng cột `status`, `lease_until`, `locked_by`, `partition_key` hoặc bảng riêng cho trạng thái relay. Cần chọn cấu trúc phù hợp với database, throughput, cách claim event và yêu cầu vận hành. Chỉ mục phải phục vụ truy vấn event chưa gửi; không nên để relay quét toàn bộ bảng mỗi vòng.

Với PostgreSQL, kiểu JSON thường là `JSONB`, thời gian có thể dùng `TIMESTAMPTZ`, và cú pháp tạo index/claim khác đôi chút. Không sao chép nguyên schema MySQL vào PostgreSQL mà không chuyển kiểu dữ liệu và default phù hợp.

## 3. Ghi dữ liệu nghiệp vụ và event trong cùng transaction

Ứng dụng thực hiện thay đổi nghiệp vụ, sau đó thêm event vào outbox trước khi commit:

```sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED',
    version = version + 1
WHERE id = 42
  AND status = 'PENDING';

INSERT INTO outbox_events (
    event_id,
    aggregate_type,
    aggregate_id,
    aggregate_version,
    event_type,
    schema_version,
    payload,
    occurred_at
)
VALUES (
    'a8c6e4b4-4b12-4f8a-8c17-7c8b2d90e042',
    'Order',
    '42',
    3,
    'OrderConfirmed',
    1,
    '{"orderId":42,"status":"CONFIRMED"}',
    CURRENT_TIMESTAMP(6)
);

COMMIT;
```

Ví dụ trên minh họa cấu trúc. Trong code thực tế, chỉ insert outbox nếu câu `UPDATE` thành công đúng số hàng kỳ vọng. Nếu đơn hàng không còn ở trạng thái `PENDING`, ứng dụng không được phát `OrderConfirmed` như thể việc xác nhận đã xảy ra.

Nếu bất kỳ thao tác nào trong transaction thất bại, transaction rollback và cả hai thay đổi không được commit. Nếu commit thành công, bản ghi outbox tồn tại bền vững cùng trạng thái đơn hàng. Relay có thể dừng rồi chạy lại mà vẫn tìm thấy event cần gửi.

Điểm quan trọng là **không publish trực tiếp lên broker bên trong transaction database rồi coi việc publish là một phần của commit**. Lệnh publish không tự rollback khi database rollback, và database commit không thể xác nhận broker đã nhận message. Transaction chỉ ghi outbox row; relay xử lý việc giao tiếp bên ngoài sau commit.

## 4. Tạo event đúng với thay đổi đã commit

Một outbox event phải mô tả một thay đổi thực sự được chấp nhận. Ứng dụng cần xác định:

- Lệnh cập nhật có tác động đúng hàng mong đợi không?
- Có thay đổi trạng thái thật sự hay request chỉ lặp lại một trạng thái đã có?
- Event cần phản ánh dữ liệu trước hay sau thay đổi?
- Event là sự kiện nghiệp vụ (`OrderConfirmed`) hay chỉ là thông báo kỹ thuật (`OrderRowUpdated`)?
- Payload chứa snapshot cần thiết hay chỉ chứa ID để consumer đọc lại dữ liệu?

### Event theo kết quả nghiệp vụ

Nếu câu `UPDATE` trả về 0 hàng, không nên insert event thành công. Ứng dụng cần xác định đơn hàng không tồn tại, đã được xác nhận trước đó hay trạng thái không còn hợp lệ.

```java
int updated = updateOrderStatus(connection, orderId);

if (updated != 1) {
    throw new OrderStateConflictException(orderId);
}

insertOutboxEvent(connection, event);
connection.commit();
```

Hai hàm phải dùng cùng connection và cùng transaction. Nếu `insertOutboxEvent` thất bại, thay đổi đơn hàng cũng phải rollback.

### Payload snapshot hay tham chiếu ID?

Có hai cách phổ biến:

| Cách | Ưu điểm | Hạn chế |
|---|---|---|
| Event chứa snapshot dữ liệu cần thiết | Consumer xử lý theo dữ liệu tại thời điểm event phát; ít phải gọi ngược producer | Payload lớn hơn; cần version schema và quản lý dữ liệu nhạy cảm |
| Event chỉ chứa aggregate ID | Payload nhỏ; consumer có thể đọc trạng thái hiện tại | Consumer có thể thấy trạng thái mới hơn event; dữ liệu có thể đã bị xóa hoặc thay đổi |

Nếu consumer cần biết chính xác trạng thái tại thời điểm `OrderConfirmed`, snapshot thường rõ nghĩa hơn. Nếu event chỉ là thông báo “đơn hàng đã thay đổi, hãy đồng bộ lại”, ID có thể phù hợp. Không nên phát event chỉ chứa ID rồi giả định consumer sẽ đọc được trạng thái lịch sử chính xác của event.

## 5. Event relay: đưa outbox đến broker

Relay là tiến trình nền đọc các event chưa publish, gửi chúng đến broker rồi cập nhật trạng thái. Có hai hướng triển khai chính:

1. **Polling publisher:** truy vấn bảng outbox định kỳ và publish các hàng đang chờ.
2. **Transaction-log tailing / CDC:** đọc thay đổi đã commit từ transaction log như MySQL binlog hoặc PostgreSQL WAL rồi chuyển outbox record đến broker.

Hai hướng đều dựa trên nguyên tắc event chỉ được xem là hợp lệ sau khi transaction database commit.

### Polling publisher

Polling dễ triển khai và không yêu cầu đọc transaction log. Relay có thể dùng một truy vấn để tìm event chưa gửi, claim một batch, rồi publish. Cần tránh để nhiều relay cùng claim một hàng hoặc giữ khóa database trong lúc chờ broker.

Một mô hình claim với lease:

1. Mở transaction ngắn.
2. Chọn một batch event chưa gửi và chưa bị worker khác claim, dùng `FOR UPDATE SKIP LOCKED` nếu database hỗ trợ.
3. Đánh dấu các hàng đó là `IN_PROGRESS`, gán `locked_by` và `lease_until`.
4. Commit transaction claim.
5. Publish từng event ngoài transaction database.
6. Khi broker xác nhận publish, mở transaction ngắn khác và đánh dấu event `PUBLISHED`/`published_at`.
7. Nếu publish thất bại, tăng attempts và đặt `next_attempt_at` theo backoff; nếu lease hết hạn, worker khác có thể claim lại.

Pseudocode:

```text
repeat:
    BEGIN
      rows = SELECT pending outbox rows
             FOR UPDATE SKIP LOCKED
             LIMIT batch_size
      UPDATE rows SET status='IN_PROGRESS', lease_until=...
    COMMIT

    for row in rows:
        try:
            broker.publish(row.event_id, row.payload)
            wait for broker confirmation
            BEGIN
              UPDATE outbox SET status='PUBLISHED', published_at=now()
              WHERE event_id=row.event_id
            COMMIT
        catch transient_error:
            schedule retry with backoff
```

`SKIP LOCKED` giúp nhiều worker lấy các batch khác nhau mà không chờ nhau trên cùng hàng. Nó không tự bảo đảm thứ tự toàn cục; nhiều worker có thể publish event sau trước event trước.

### Vì sao cần lease?

Nếu relay đánh dấu một hàng `IN_PROGRESS` rồi process bị kill, hàng đó có thể bị kẹt vĩnh viễn nếu không có lease. `lease_until` cho phép hệ thống thu hồi claim đã hết hạn. Worker cần cập nhật trạng thái bằng điều kiện xác nhận nó vẫn sở hữu lease để tránh worker cũ ghi đè trạng thái của worker mới.

Ví dụ:

```sql
UPDATE outbox_events
SET status = 'PUBLISHED',
    published_at = CURRENT_TIMESTAMP(6)
WHERE event_id = :event_id
  AND status = 'IN_PROGRESS'
  AND locked_by = :worker_id;
```

Nếu lease đã hết hạn và event được worker khác claim, update của worker cũ sẽ không khớp. Dù vậy, worker cũ có thể đã publish event trước đó; consumer vẫn cần deduplicate.

### CDC / transaction-log tailing

Với CDC, connector đọc transaction log để nhận biết outbox row được commit và chuyển nó thành message. Cách này giảm truy vấn polling liên tục và có thể giữ thứ tự theo log/partition phù hợp với công cụ.

CDC có yêu cầu vận hành riêng:

- Connector phải theo dõi offset/position của binlog hoặc WAL.
- Transaction log cần được giữ đủ lâu để connector phục hồi sau downtime.
- Schema change của bảng outbox và payload cần tương thích với connector.
- Connector có thể phát lại record sau restart nếu offset chưa được commit; consumer vẫn nên idempotent.
- Cần giám sát lag, slot/offset, dung lượng log và trạng thái connector.

CDC không biến database và broker thành một transaction nguyên tử. Connector có thể phát lại record nếu crash ở giữa publish và lưu offset. Hãy đọc semantics của connector cụ thể trước khi tuyên bố bảo đảm giao đúng một lần.

## 6. Vì sao outbox vẫn có thể gửi trùng?

Giả sử relay dùng polling và thực hiện:

```text
1. Đọc event E từ outbox
2. Publish E lên broker
3. Broker xác nhận đã nhận E
4. Relay crash trước khi đánh dấu E là PUBLISHED
```

Khi relay khởi động lại, E vẫn có trạng thái chưa publish. Relay gửi E lần nữa. Broker có thể chứa hai bản message có cùng `event_id`.

```text
Database                    Relay                       Broker
--------                    -----                       ------
Outbox E pending
                            đọc E
                            publish E ---------------> E đã nhận
                            <------------------------- ACK
                            CRASH trước khi mark

Outbox E vẫn pending
                            đọc E lần nữa
                            publish E ---------------> E bản thứ hai
```

Đây là trade-off có chủ đích. Nếu relay đánh dấu `PUBLISHED` trước khi gửi, crash giữa đánh dấu và publish sẽ làm mất event. Publish trước rồi đánh dấu chấp nhận khả năng duplicate để tránh mất event trong cửa sổ đó.

Do đó, outbox thường tạo **at-least-once publication** khi relay retry cho đến khi xác nhận thành công. Consumer cần xử lý cùng một event ID nhiều lần mà chỉ tạo hiệu ứng nghiệp vụ một lần trong phạm vi database của consumer.

## 7. Consumer idempotent và inbox pattern

Consumer nên lưu `event_id` đã xử lý trong cùng transaction với thay đổi dữ liệu của nó:

```sql
CREATE TABLE inbox_messages (
    consumer_name VARCHAR(100) NOT NULL,
    event_id CHAR(36) NOT NULL,
    processed_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (consumer_name, event_id)
);
```

Luồng xử lý:

```text
Nhận event E
    |
    v
BEGIN consumer database transaction
    |
    v
INSERT inbox(consumer, event_id)
    |
    +-- duplicate key --> bỏ qua hiệu ứng đã xử lý
    |
    +-- insert thành công --> áp dụng thay đổi nghiệp vụ
                               |
                               v
                             COMMIT
                               |
                               v
                             ACK broker
```

Nếu consumer crash sau commit nhưng trước ACK, broker giao lại event. Inbox row đã tồn tại nên consumer bỏ qua hiệu ứng lặp rồi ACK. Nếu crash trước commit, inbox row và thay đổi nghiệp vụ cùng rollback; event được giao lại và xử lý lại từ đầu.

Inbox chỉ bảo vệ các thay đổi nằm trong cùng transaction database của consumer. Nếu consumer còn gọi email hoặc payment API, cần idempotency key ở hệ thống ngoài hoặc một outbox mới để chuyển tiếp tác dụng phụ.

## 8. Thứ tự event và nhiều relay

Outbox bảo đảm event được lưu cùng transaction, nhưng thứ tự publish có thể khác thứ tự commit nếu relay chạy song song, claim batch hoặc retry event cũ.

Ví dụ cùng aggregate `Order 42`:

```text
Order version 4: OrderConfirmed
Order version 5: OrderShipped
```

Nếu event version 5 được publish trước version 4, consumer có thể nhận trạng thái giao hàng trước trạng thái xác nhận. Cách xử lý phụ thuộc loại event và hợp đồng nghiệp vụ.

Các biện pháp thường dùng:

- Lưu `aggregate_version` hoặc sequence tăng đơn điệu trong cùng transaction với thay đổi nghiệp vụ.
- Dùng broker partition key theo `aggregate_id` để các event cùng aggregate vào cùng partition.
- Chỉ publish event tiếp theo của aggregate sau khi event trước được xác nhận, nếu cần thứ tự nghiêm ngặt.
- Consumer kiểm tra version và phát hiện event cũ, event trùng hoặc khoảng trống sequence.
- Nếu event là snapshot state, consumer có thể chỉ áp dụng version lớn hơn version hiện tại; nếu event là delta, cần xử lý gap trước khi tiếp tục.

`created_at` không đủ để bảo đảm thứ tự. Nhiều event có thể có timestamp giống nhau, đồng hồ ứng dụng có thể lệch và nhiều worker có thể publish đồng thời. Sequence được cấp theo aggregate trong transaction thường là dấu mốc rõ ràng hơn.

## 9. Event schema và tính tương thích

Event là hợp đồng giữa producer và consumer. Khi payload thay đổi, các consumer cũ có thể vẫn đang hoạt động hoặc broker có thể giữ message lâu trước khi được xử lý.

Nên lưu:

- `event_type` ổn định, không phụ thuộc tên class Java nội bộ.
- `schema_version` hoặc schema identifier.
- `event_id` duy nhất.
- `aggregate_id` và sequence/version khi cần thứ tự.
- Thời điểm nghiệp vụ và thông tin correlation/causation phù hợp.
- Payload có kiểu dữ liệu rõ và không chứa thông tin nhạy cảm không cần thiết.

Ưu tiên thay đổi tương thích ngược như thêm trường optional có default. Khi bỏ hoặc đổi nghĩa trường, cần chiến lược versioning và triển khai consumer/producer theo thứ tự phù hợp. Không serialize trực tiếp một object Java tùy tiện rồi coi cấu trúc class là hợp đồng vĩnh viễn.

## 10. Java/Spring: ghi outbox trong transaction nghiệp vụ

Một service Spring có thể lưu entity và outbox event trong cùng transaction:

```java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final EventSerializer serializer;

    @Transactional
    public void confirm(long orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.confirm();

        OutboxEvent event = new OutboxEvent(
            UUID.randomUUID(),
            "Order",
            Long.toString(order.getId()),
            order.getVersion() + 1,
            "OrderConfirmed",
            1,
            serializer.serialize(new OrderConfirmed(order.getId()))
        );

        outbox.save(event);
    }
}
```

Ví dụ giả định `order.confirm()` thay đổi entity và repository dùng cùng transaction manager/database. Cần xác định thời điểm JPA tăng `@Version` (thường tại flush) trước khi gán `aggregate_version`; có thể dùng sequence nghiệp vụ riêng hoặc flush có kiểm soát để lấy version chính xác. Không dựa vào giá trị version cũ trong persistence context.

Không gọi `broker.send()` như một thao tác được coi là nguyên tử với `@Transactional` database. Việc gửi broker thuộc relay chạy sau commit.

### Polling relay trong Java

Relay có thể có cấu trúc:

```java
public void publishBatch() {
    List<OutboxEvent> claimed = claimService.claimBatch(100);

    for (OutboxEvent event : claimed) {
        try {
            broker.publish(event.eventId(), event.payload());
            broker.awaitConfirmation(event.eventId());
            claimService.markPublished(event.eventId());
        } catch (TransientPublishException ex) {
            claimService.scheduleRetry(event.eventId(), ex);
        }
    }
}
```

`claimBatch`, `markPublished` và `scheduleRetry` thực hiện các transaction database ngắn riêng biệt. `broker.publish` và chờ confirmation diễn ra ngoài transaction claim. Nếu relay crash sau confirmation nhưng trước `markPublished`, event có thể được gửi lại; `eventId` phải giữ nguyên để consumer deduplicate.

Trong Spring, có thể tách service claim/mark thành các bean transactional riêng để proxy quản lý transaction rõ ràng. Không giữ một transaction `@Transactional` bao quanh cả vòng lặp publish nếu broker có thể chậm hoặc mất kết nối.

## 11. Claim event an toàn khi nhiều worker

Nếu nhiều instance relay cùng chạy, chúng cần phân chia event mà không cùng xử lý một hàng trong cùng thời điểm. Một phương pháp là `FOR UPDATE SKIP LOCKED` kết hợp lease. Ví dụ khái niệm với MySQL 8.0:

```sql
START TRANSACTION;

SELECT event_id
FROM outbox_events
WHERE status = 'PENDING'
  AND (next_attempt_at IS NULL OR next_attempt_at <= NOW(6))
ORDER BY created_at, event_id
LIMIT 100
FOR UPDATE SKIP LOCKED;

UPDATE outbox_events
SET status = 'IN_PROGRESS',
    locked_by = 'relay-3',
    lease_until = NOW(6) + INTERVAL 30 SECOND,
    attempts = attempts + 1
WHERE event_id IN (...);

COMMIT;
```

Ví dụ cần bổ sung các cột `status`, `locked_by`, `lease_until` vào schema. Trong code thực tế, danh sách ID được bind parameter an toàn; không nối chuỗi SQL từ dữ liệu ngoài.

Sau commit claim, relay publish. Khi thành công, nó đánh dấu `PUBLISHED` với điều kiện `locked_by` vẫn là worker hiện tại. Khi thất bại, nó đặt `PENDING`, `next_attempt_at` và `last_error` hoặc chuyển sang trạng thái cần can thiệp sau khi vượt giới hạn.

Lease phải dài hơn khoảng thời gian xử lý dự kiến hoặc được gia hạn khi cần. Nếu lease quá ngắn, worker thứ hai có thể claim event khi worker đầu vẫn đang publish. Nếu lease quá dài, event bị kẹt lâu sau khi worker chết. Dù chọn lease nào, duplicate vẫn có thể xảy ra ở cửa sổ broker đã nhận nhưng database chưa được đánh dấu.

PostgreSQL cũng hỗ trợ `FOR UPDATE SKIP LOCKED`, nhưng kiểu dữ liệu thời gian, cú pháp interval, câu `UPDATE ... RETURNING` và cách tổ chức claim có thể khác. Hãy triển khai theo database cụ thể.

## 12. Retry publish và xử lý poison event

Không phải lỗi publish nào cũng tạm thời. Mất kết nối broker hoặc timeout có thể phục hồi; payload không hợp lệ hoặc schema không được hỗ trợ có thể thất bại liên tục.

Một chiến lược retry thường gồm:

1. Tăng `attempts`.
2. Lưu mã lỗi rút gọn trong `last_error`, tránh lưu dữ liệu nhạy cảm.
3. Đặt `next_attempt_at` bằng exponential backoff có jitter.
4. Sau ngưỡng cấu hình, chuyển event sang `FAILED`/dead-letter state và cảnh báo vận hành.
5. Cho phép operator sửa nguyên nhân rồi replay event bằng cùng `event_id` hoặc tạo event mới theo chính sách được kiểm soát.

Không xóa event chỉ vì đã retry nhiều lần. Một event lỗi có thể đại diện cho thay đổi nghiệp vụ đã commit; bỏ nó đi sẽ khiến dịch vụ phụ thuộc không bao giờ nhận được thông tin. Cần trạng thái rõ ràng, cảnh báo và quy trình phục hồi.

Nếu broker xác nhận publish nhưng response bị mất, relay không biết broker đã nhận hay chưa. Cách an toàn là retry cùng `event_id`, chấp nhận duplicate và để consumer deduplicate. Không tạo event ID mới khi retry một lần publish của cùng outbox row.

## 13. Dọn dẹp outbox và lưu lịch sử

Outbox tăng liên tục nếu không có chính sách lưu trữ. Tuy nhiên, xóa event quá sớm có thể làm mất khả năng audit, replay hoặc điều tra.

Các lựa chọn:

- Giữ event đã publish trong một khoảng thời gian rồi xóa theo batch.
- Chuyển event cũ sang bảng archive hoặc object storage.
- Dùng partition theo thời gian để quản lý vòng đời dữ liệu lớn.
- Giữ event lỗi hoặc chưa publish cho đến khi được xử lý, không áp dụng cleanup chung cho chúng.

Cleanup phải lọc chỉ event đã publish và đã qua retention. Xóa theo batch nhỏ để tránh transaction lớn, lock lâu và I/O đột biến. Nếu cần replay lịch sử, phải lưu payload và schema đủ lâu hoặc có nguồn tái tạo event đáng tin cậy.

Retention của outbox, retention của broker và retention của inbox consumer có liên quan. Nếu consumer có thể replay message 30 ngày nhưng inbox chỉ giữ 7 ngày, event cũ có thể tạo hiệu ứng lần nữa sau khi dedup record bị xóa. Chính sách lưu phải được thiết kế xuyên suốt workflow.

## 14. Quan sát và vận hành outbox

Các metric hữu ích:

- Số lượng event đang chờ publish.
- Tuổi của event pending lâu nhất (`now - created_at`).
- Số event `IN_PROGRESS` và số lease đã hết hạn.
- Tốc độ publish, tỷ lệ thành công và tỷ lệ retry.
- Số event ở trạng thái failed/dead-letter.
- Độ trễ từ `occurred_at`/`created_at` đến `published_at`.
- CDC lag hoặc binlog/WAL position lag nếu dùng CDC.
- Số duplicate event được consumer phát hiện.

Độ dài queue không đủ để đánh giá sức khỏe. Một outbox có 10 event nhưng event cũ nhất đã chờ 2 giờ có thể nghiêm trọng hơn 10.000 event vừa được tạo trong vài giây và relay đang xử lý bình thường.

Log nên có `event_id`, `aggregate_id`, `event_type`, worker/relay ID, attempt number, broker destination và correlation ID. Tránh ghi payload nhạy cảm hoặc token vào log.

Các cảnh báo nên dựa trên SLA nghiệp vụ, ví dụ event `OrderConfirmed` phải đến dịch vụ kho trong vòng 1 phút. Chọn ngưỡng theo yêu cầu thật, không đặt ngưỡng tùy tiện chỉ dựa trên số lượng hàng.

## 15. Outbox không tự giải quyết thứ tự và tính nhất quán toàn workflow

Outbox lưu sự kiện theo transaction commit, nhưng nhiều relay hoặc partition broker có thể làm event đến sai thứ tự. Nếu consumer chỉ cần trạng thái mới nhất, nó có thể áp dụng event có version cao hơn và bỏ qua version cũ. Nếu event là delta, ví dụ `InventoryDecreasedBy(3)`, bỏ qua hoặc đảo thứ tự có thể làm sai kết quả.

Consumer cần biết loại event:

- **State snapshot:** chứa trạng thái hoặc version đủ để áp dụng trạng thái mới nhất; có thể dùng điều kiện `incoming_version > current_version`.
- **Delta/event fact:** mô tả một sự kiện cần áp dụng đúng thứ tự; cần sequence, partition key hoặc phát hiện gap.

Outbox cũng không bảo đảm consumer xử lý thành công. Nó chỉ bảo đảm producer lưu được ý định phát event cùng transaction. Consumer vẫn có thể lỗi, cần retry, inbox, dead-letter handling và reconciliation.

## 16. Khi nào cân nhắc CDC, broker transaction hoặc distributed transaction?

| Cách tiếp cận | Phù hợp khi | Giới hạn cần hiểu |
|---|---|---|
| Polling outbox | Muốn triển khai đơn giản, kiểm soát bằng bảng và SQL | Tạo tải polling; cần claim/lease và cleanup |
| CDC từ binlog/WAL | Throughput cao, muốn phát hiện row commit gần thời gian thực | Cần vận hành connector, offset, retention log và schema evolution |
| Broker transaction | Cần nguyên tử giữa consume/produce/offset trong phạm vi broker | Không tự bao trùm database hoặc HTTP API độc lập |
| XA/two-phase commit | Tất cả participant hỗ trợ cùng giao thức và yêu cầu nguyên tử xuyên hệ thống thực sự cần thiết | Coordinator, blocking, phức tạp vận hành và hỗ trợ không đồng đều |
| Saga | Workflow nhiều service với các transaction cục bộ và hành động bù | Eventual consistency; compensation có thể thất bại và cần idempotency |

Không có một lựa chọn đúng cho mọi hệ thống. Outbox là lựa chọn phổ biến khi database là nguồn sự thật và cần phát event đáng tin cậy sau commit.

## 17. Kiểm thử các cửa sổ lỗi

Một triển khai outbox cần được kiểm thử bằng cách mô phỏng crash tại các điểm khác nhau:

1. Crash trước khi transaction producer commit: không có thay đổi nghiệp vụ và không có outbox row.
2. Outbox insert thất bại: transaction nghiệp vụ rollback.
3. Crash sau commit nhưng trước khi relay đọc: event vẫn còn trong outbox và sẽ được relay sau đó.
4. Relay claim event rồi crash trước publish: lease hết hạn và event được claim lại.
5. Broker nhận event nhưng relay crash trước khi mark published: event có thể được publish lại; consumer dedup.
6. Consumer commit database rồi crash trước ACK: broker giao lại; inbox ngăn lặp hiệu ứng trong database consumer.
7. Consumer crash trước commit: inbox và thay đổi nghiệp vụ rollback; message được xử lý lại.
8. Broker hoặc consumer ngừng hoạt động lâu: outbox backlog tăng, cảnh báo và recovery phải hoạt động.
9. Event sai schema hoặc poison message: event không bị xóa âm thầm và có quy trình xử lý.
10. Hai event cùng aggregate đến sai thứ tự: consumer phát hiện version/gap và áp dụng chính sách đúng.

Kiểm thử cần xác nhận trạng thái cuối cùng của database nguồn, broker, database consumer và hệ thống ngoài. Chỉ thấy log “publish success” không chứng minh toàn workflow hoàn tất.

## 18. Quy trình triển khai transactional outbox

1. Xác định thay đổi nghiệp vụ nào cần phát event và consumer nào phụ thuộc vào nó.
2. Thiết kế event ID, aggregate ID, sequence/version, type và schema version.
3. Tạo bảng outbox cùng index phục vụ truy vấn pending.
4. Trong service nghiệp vụ, cập nhật domain data và insert outbox row bằng cùng connection/transaction.
5. Chỉ tạo event khi thay đổi nghiệp vụ thành công và đúng điều kiện.
6. Chọn polling relay hoặc CDC theo throughput, độ trễ và khả năng vận hành.
7. Với polling, triển khai claim an toàn, lease, publish confirmation và trạng thái retry.
8. Giữ event ID ổn định qua mọi lần publish lại.
9. Triển khai inbox/idempotency ở consumer; commit dedup marker cùng thay đổi nghiệp vụ.
10. Xác định thứ tự event và cách consumer xử lý duplicate, reorder hoặc gap.
11. Đặt retry/backoff, dead-letter handling, retention và cleanup.
12. Theo dõi backlog, tuổi event pending, publish latency, retry và CDC lag.
13. Kiểm thử crash ở từng cửa sổ lỗi trước khi triển khai production.

## 19. Tự kiểm tra

**Vì sao ghi database rồi publish trực tiếp có thể làm mất event?**

Ứng dụng có thể crash sau khi database commit nhưng trước khi broker nhận event. Database không có thông tin bền vững rằng cần publish lại.

**Transactional outbox ghi những gì trong cùng transaction?**

Nó ghi thay đổi dữ liệu nghiệp vụ và bản ghi event cần phát. Cả hai cùng commit hoặc cùng rollback trong database.

**Outbox có bảo đảm relay không bao giờ publish trùng không?**

Không. Relay có thể publish thành công rồi crash trước khi đánh dấu event đã gửi. Khi chạy lại, nó publish lại cùng event ID. Consumer cần deduplicate.

**Vì sao không đánh dấu event đã publish trước khi gửi broker?**

Nếu relay crash sau khi đánh dấu nhưng trước khi broker nhận, event bị mất và outbox không còn chọn lại. Publish trước rồi mark chấp nhận duplicate để tránh mất event.

**Vì sao outbox row và cập nhật đơn hàng phải dùng cùng transaction?**

Nếu tách transaction, có thể xuất hiện đơn hàng đã đổi nhưng không có event, hoặc event tồn tại trong khi thay đổi nghiệp vụ rollback. Cùng transaction bảo đảm hai trạng thái nhất quán trong database nguồn.

**Consumer cần làm gì khi nhận lại cùng event ID?**

Dùng inbox/unique constraint hoặc cơ chế idempotency để nhận ra event đã xử lý. Dedup marker và thay đổi nghiệp vụ của consumer phải được commit cùng transaction.

**Polling relay và CDC khác nhau ở đâu?**

Polling định kỳ truy vấn bảng outbox và claim hàng; CDC đọc transaction log đã commit như binlog/WAL. Cả hai cần quản lý offset/lease, duplicate, lag và phục hồi.

Transactional outbox tạo một ranh giới rõ ràng: **thay đổi nghiệp vụ và ý định phát event được commit cùng nhau trong database; relay giao event sau commit; consumer bảo vệ hiệu ứng lặp bằng idempotency**. Cách này giúp hệ thống phục hồi sau crash mà không giả định database và broker có chung một transaction. Khi triển khai, cần thiết kế thêm thứ tự event, retry, retention, deduplication và quan sát backlog để bảo đảm workflow hoạt động ổn định.
