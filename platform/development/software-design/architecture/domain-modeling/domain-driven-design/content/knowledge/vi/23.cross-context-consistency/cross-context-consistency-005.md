# Transactional Outbox: liên hệ giữa ghi dữ liệu và công bố sự kiện

Trong hệ thống DDD có nhiều Bounded Context, một thay đổi trong context này thường cần được context khác biết đến. Ví dụ, Ordering xác nhận đơn hàng và Inventory cần nhận sự kiện để giữ chỗ; Payment hoàn tất thanh toán và Ordering cần cập nhật trạng thái đơn. Message broker giúp các context trao đổi sự kiện mà không phải gọi trực tiếp database của nhau.

Khó khăn nằm ở chỗ ứng dụng thường phải thực hiện hai thao tác: **ghi thay đổi vào database** và **gửi sự kiện lên message broker**. Hai thao tác này thuộc hai hệ thống tài nguyên khác nhau. Nếu database commit thành công nhưng publish thất bại, context khác không nhận được sự kiện. Nếu publish thành công nhưng database rollback, context khác lại nhận một sự kiện mô tả thay đổi chưa từng được lưu.

Transactional Outbox giải quyết khoảng trống này bằng cách ghi thay đổi nghiệp vụ và một bản ghi sự kiện vào **cùng một database transaction**. Một tiến trình relay đọc các bản ghi Outbox đã commit rồi gửi chúng đến broker. Cách làm này bảo đảm ý định phát sự kiện được lưu bền vững cùng thay đổi nghiệp vụ; relay có thể gửi lại khi gặp lỗi.

## 1. Vấn đề dual write

### 1.1. Một use case cần ghi database và publish message

Giả sử Ordering xử lý use case xác nhận đơn:

1. Đổi trạng thái Order từ Submitted sang Confirmed.
2. Phát sự kiện OrderConfirmed để Inventory và các context liên quan tiếp tục xử lý.

Một cách triển khai trực tiếp:

~~~java
@Transactional
public void confirmOrder(OrderId orderId) {
    Order order = orders.findById(orderId)
        .orElseThrow(() -> new OrderNotFound(orderId));

    order.confirm();
    orders.save(order);

    messageBroker.publish(new OrderConfirmed(order.id()));
}
~~~

Đoạn code có vẻ đơn giản nhưng chứa hai lần ghi độc lập: database commit và broker publish. Annotation transaction thường chỉ quản lý tài nguyên database đã tham gia transaction; nó không tự làm cho thao tác publish trở thành một phần của transaction database.

### 1.2. Hai thứ tự đều có thể tạo ra dữ liệu không nhất quán

Nếu publish trước rồi database commit:

- Broker nhận OrderConfirmed.
- Consumer bắt đầu giữ chỗ tồn kho hoặc gửi thông báo.
- Database transaction của Ordering gặp lỗi và rollback.
- Consumer đã hành động dựa trên một đơn hàng chưa được xác nhận.

Nếu commit database trước rồi publish:

- Database lưu Order ở trạng thái Confirmed.
- Process dừng, broker mất kết nối hoặc publish timeout.
- Order đã được xác nhận nhưng không có sự kiện để context khác xử lý.

Không có thứ tự gọi tuần tự nào loại bỏ được cả hai khoảng lỗi này khi hai hệ thống không cùng tham gia một cơ chế commit nguyên tử.

### 1.3. Bảng tình huống lỗi

| Thứ tự thao tác | Sự cố | Hậu quả |
|---|---|---|
| Publish rồi commit | Database rollback | Consumer nhận sự kiện không có thay đổi tương ứng |
| Commit rồi publish | Broker không nhận message | Thay đổi đã lưu nhưng context khác không được thông báo |
| Commit rồi publish | Process dừng giữa hai thao tác | Không có cách chắc chắn để biết message còn cần gửi |
| Publish timeout | Broker có thể đã nhận hoặc chưa nhận | Retry có thể tạo message trùng |

Đây là dual-write problem: một use case cần ghi hai hệ thống nhưng không có một transaction nguyên tử chung để xác nhận cả hai.

### 1.4. Vì sao chỉ bắt exception và retry chưa đủ?

Có thể thử retry publish trong catch block hoặc dùng một job quét những bản ghi chưa gửi. Nhưng nếu trạng thái “cần gửi” chỉ nằm trong bộ nhớ, process có thể dừng trước khi lưu được trạng thái đó.

Một bảng trạng thái riêng được cập nhật sau commit cũng tạo ra một dual write mới: database nghiệp vụ đã commit nhưng cập nhật trạng thái gửi thất bại. Cần một dấu vết bền vững được ghi cùng transaction với thay đổi gốc.

## 2. Ý tưởng của Transactional Outbox

Outbox là một bảng hoặc cấu trúc lưu trữ các integration event cần được công bố. Khi một use case thay đổi aggregate, ứng dụng ghi:

- Thay đổi của aggregate.
- Một bản ghi Outbox chứa sự kiện cần gửi.

Hai thao tác ghi này dùng cùng database connection và cùng transaction. Vì vậy:

- Nếu transaction commit, cả thay đổi nghiệp vụ và Outbox record đều tồn tại.
- Nếu transaction rollback, cả hai đều không tồn tại.

Một tiến trình khác, thường gọi là Outbox Relay hoặc Publisher, đọc Outbox record đã commit và gửi message đến broker.

~~~mermaid
flowchart LR
    A["Application Service"] --> B["Domain Aggregate"]
    B --> C["Thay đổi trạng thái"]
    A --> D["Outbox Repository"]
    C --> E[("Database")]
    D --> E
    E --> F["Outbox Relay"]
    F --> G["Message Broker"]
    G --> H["Consumer ở context khác"]
~~~

Điểm quan trọng là broker không cần tham gia transaction của database. Database transaction chỉ cần lưu thành công thay đổi nghiệp vụ và ý định phát sự kiện. Relay xử lý việc chuyển ý định đó thành message bên ngoài.

## 3. Outbox bảo đảm điều gì?

### 3.1. Bảo đảm tính nguyên tử của hai bản ghi trong database

Giả sử Order và OutboxEvent cùng nằm trong một database:

~~~sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE id = :order_id;

INSERT INTO outbox_event (
    id,
    aggregate_type,
    aggregate_id,
    event_type,
    payload,
    occurred_at
) VALUES (
    :event_id,
    'Order',
    :order_id,
    'OrderConfirmed',
    :payload,
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

Nếu INSERT Outbox thất bại, transaction không được commit thì UPDATE Order cũng bị rollback. Nếu transaction commit, relay có thể tìm thấy event đã lưu.

Ví dụ SQL dùng cú pháp tham số khái niệm; kiểu dữ liệu, JSON column và cách sinh ID phụ thuộc database.

### 3.2. Không bảo đảm broker nhận đúng một lần

Outbox không làm cho database và broker trở thành một transaction nguyên tử. Relay vẫn có thể gửi message thành công nhưng chết trước khi đánh dấu bản ghi đã gửi.

Khi khởi động lại, relay thấy bản ghi chưa được đánh dấu và gửi lại. Vì thế, mô hình phổ biến là **at-least-once delivery**: message có thể được gửi lại, nên consumer phải xử lý lặp an toàn.

Không nên quảng bá Outbox như một cơ chế exactly-once end-to-end. Mục tiêu của nó là tránh mất ý định phát sự kiện sau khi thay đổi nghiệp vụ đã commit, đồng thời chấp nhận khả năng gửi trùng để có thể retry.

### 3.3. Điều kiện quan trọng: cùng database transaction

Atomic write chỉ có ý nghĩa khi aggregate và Outbox record được ghi trong cùng transaction trên cùng tài nguyên database có hỗ trợ transaction đó.

Nếu Outbox nằm ở một database khác, hai lần ghi lại trở thành dual write. Nếu dữ liệu nghiệp vụ nằm ở hai database độc lập, một Outbox trong một database không thể tự bảo đảm commit nguyên tử cho cả hai.

Trong kiến trúc microservices, mỗi service thường sở hữu database riêng và ghi Outbox cục bộ cùng thay đổi của chính service đó. Việc phối hợp giữa các service diễn ra qua message và quy trình Saga hoặc eventual consistency.

## 4. Phân biệt Domain Event và Integration Event

### 4.1. Domain Event diễn đạt điều đã xảy ra trong mô hình miền

Domain Event là sự kiện có ý nghĩa trong ngôn ngữ của một Bounded Context, ví dụ:

- OrderConfirmed.
- RefundApproved.
- StockReserved.

Nó có thể được dùng nội bộ trong domain/application để kích hoạt các hành vi tiếp theo. Domain Event thường mang kiểu dữ liệu và ngữ nghĩa gắn với mô hình miền của context sở hữu nó.

### 4.2. Integration Event là hợp đồng trao đổi giữa context

Integration Event là thông điệp được công bố ra bên ngoài để context khác có thể hiểu và phản ứng. Hợp đồng cần ổn định hơn implementation nội bộ.

Ví dụ, domain model có thể có object Order với nhiều phương thức và kiểu nội bộ, nhưng integration event chỉ cần:

~~~json
{
  "eventId": "6a65a5e0-95a6-4cb0-9b57-32fdde44e5b2",
  "eventType": "ordering.order-confirmed",
  "eventVersion": 1,
  "occurredAt": "2026-11-18T08:30:00Z",
  "aggregateId": "order-123",
  "data": {
    "orderId": "order-123",
    "buyerId": "buyer-42",
    "currency": "VND",
    "totalAmount": "1250000"
  }
}
~~~

Consumer không cần biết class Order được cài đặt thế nào. Nó chỉ cần một schema có ý nghĩa và đủ dữ liệu để thực hiện trách nhiệm của context mình.

### 4.3. Chuyển Domain Event thành Integration Event

Application layer hoặc một mapper chuyên trách có thể chuyển domain event thành integration event:

1. Aggregate thực hiện hành vi và ghi nhận domain event.
2. Application layer thu thập domain event sau hành vi.
3. Mapper chuyển event thành contract công khai.
4. Outbox Repository ghi integration event vào database transaction hiện tại.
5. Relay công bố event đã commit.

Không nên tuần tự hóa trực tiếp toàn bộ aggregate hoặc entity ORM vào Outbox. Làm vậy khiến contract bên ngoài phụ thuộc vào lazy proxy, quan hệ nội bộ, field nhạy cảm và cấu trúc database.

### 4.4. Snapshot dữ liệu tại thời điểm sự kiện

Payload nên mô tả sự kiện tại thời điểm nó xảy ra. Ví dụ OrderConfirmed cần giữ tổng tiền và loại tiền đã được xác nhận theo chính sách lúc đó.

Không nên chỉ lưu aggregate ID rồi nhiều giờ sau relay mới tải Order hiện tại để dựng payload. Trong khoảng thời gian đó Order có thể đã thay đổi địa chỉ, trạng thái hoặc tổng tiền; message phát ra sẽ mô tả sai thời điểm sự kiện.

Hãy tạo immutable integration event và lưu payload snapshot trong cùng transaction với thay đổi nghiệp vụ.

## 5. Thiết kế bảng Outbox

Một bảng Outbox thường có các trường sau:

| Trường | Mục đích |
|---|---|
| id | ID duy nhất của event, dùng làm message ID và idempotency key |
| aggregate_type | Loại aggregate phát sinh event |
| aggregate_id | Identity của aggregate |
| aggregate_sequence | Thứ tự event trong một aggregate, nếu cần |
| event_type | Tên event ổn định |
| event_version | Phiên bản schema |
| payload | Nội dung integration event |
| occurred_at | Thời điểm nghiệp vụ xảy ra |
| created_at | Thời điểm Outbox record được ghi |
| published_at | Thời điểm relay xác nhận broker đã nhận |
| attempts | Số lần relay thử gửi |
| next_attempt_at | Thời điểm được phép thử lại |
| locked_by / locked_until | Thông tin lease khi nhiều relay cùng chạy |
| last_error | Lỗi gần nhất đã được rút gọn hoặc mã hóa phù hợp |

Không phải hệ thống nào cũng cần tất cả trường. Chọn cấu trúc theo nhu cầu retry, quan sát, thứ tự và retention.

### 5.1. Ví dụ schema PostgreSQL

~~~sql
CREATE TABLE outbox_event (
    id UUID PRIMARY KEY,
    aggregate_type VARCHAR(120) NOT NULL,
    aggregate_id VARCHAR(160) NOT NULL,
    aggregate_sequence BIGINT,
    event_type VARCHAR(200) NOT NULL,
    event_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_by VARCHAR(120),
    locked_until TIMESTAMPTZ,
    last_error TEXT
);

CREATE INDEX ix_outbox_pending
    ON outbox_event (next_attempt_at, created_at)
    WHERE published_at IS NULL;

CREATE UNIQUE INDEX ux_outbox_aggregate_sequence
    ON outbox_event (
        aggregate_type,
        aggregate_id,
        aggregate_sequence
    )
    WHERE aggregate_sequence IS NOT NULL;
~~~

Partial index trên các bản ghi chưa publish giúp relay không phải quét toàn bộ lịch sử. Cú pháp và chiến lược index cần được kiểm chứng theo database thực tế và truy vấn polling.

### 5.2. ID và sequence có vai trò khác nhau

- Event ID xác định duy nhất một message qua các lần retry.
- Aggregate ID cho biết event thuộc Entity/Aggregate nào.
- Aggregate sequence biểu diễn thứ tự event trong vòng đời aggregate.
- OccurredAt là thời điểm nghiệp vụ, không phải lúc broker chắc chắn nhận message.

Không nên dùng timestamp đơn lẻ để bảo đảm thứ tự tuyệt đối. Hai event có thể cùng timestamp, đồng hồ hệ thống có thể lệch và nhiều relay có thể xử lý song song.

### 5.3. Payload nên là dữ liệu đã định nghĩa schema

JSON payload thường thuận tiện cho integration event, nhưng cần:

- Quy định field bắt buộc và field tùy chọn.
- Định nghĩa kiểu số tiền, timestamp, ID và enum.
- Tránh serialize Java class name hoặc cấu trúc object graph nội bộ.
- Có event version hoặc schema identifier.
- Kiểm soát dữ liệu cá nhân và thông tin bí mật.

## 6. Ghi Outbox cùng aggregate trong Spring/JPA

### 6.1. Application service điều phối một transaction

Application service tải aggregate, thực hiện hành vi miền và ghi Outbox record. Cả repository aggregate và Outbox repository phải tham gia cùng transaction manager và cùng database transaction.

~~~java
@Service
public class ConfirmOrderService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final IntegrationEventMapper eventMapper;

    public ConfirmOrderService(
            OrderRepository orders,
            OutboxRepository outbox,
            IntegrationEventMapper eventMapper) {
        this.orders = orders;
        this.outbox = outbox;
        this.eventMapper = eventMapper;
    }

    @Transactional
    public void confirm(OrderId orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new OrderNotFound(orderId));

        order.confirm();

        List<IntegrationEvent> events =
            eventMapper.toIntegrationEvents(order.pullDomainEvents());

        outbox.saveAll(events.stream()
            .map(OutboxRecord::from)
            .toList());
    }
}
~~~

Đoạn code minh họa cách điều phối. `pullDomainEvents`, mapper và OutboxRecord là các thành phần của ví dụ, cần được triển khai theo mô hình của dự án. Việc gọi `saveAll` phải dùng cùng transaction với thay đổi Order.

Nếu Outbox insert gặp lỗi, exception phải khiến transaction rollback theo rollback rule đã cấu hình. Nếu ứng dụng bắt exception rồi tiếp tục commit mà không xử lý đúng, atomicity mong muốn sẽ bị phá vỡ.

### 6.2. Repository ghi Outbox

~~~java
public interface OutboxRepository {
    void saveAll(List<OutboxRecord> records);
}
~~~

Adapter JPA có thể dùng EntityManager hoặc Spring Data repository. Không mở transaction độc lập bằng REQUIRES_NEW cho Outbox nếu mục tiêu là commit nó cùng thay đổi aggregate.

### 6.3. Mapping integration event

~~~java
public record OrderConfirmedV1(
    UUID eventId,
    String orderId,
    String buyerId,
    String currency,
    String totalAmount,
    Instant occurredAt
) implements IntegrationEvent {
}
~~~

Event DTO không cần tham chiếu trực tiếp đến Entity Order. Các giá trị được sao chép thành dữ liệu bất biến khi use case tạo sự kiện.

### 6.4. Chú ý transaction manager và database

Chỉ đặt hai lệnh trong cùng phương thức có `@Transactional` chưa đủ nếu chúng thực tế dùng hai transaction manager hoặc hai database khác nhau. Hãy xác minh:

- Order repository và Outbox repository dùng cùng database.
- Chúng tham gia cùng transaction manager.
- Không có propagation độc lập làm commit Outbox sớm.
- Không có asynchronous boundary tách việc ghi Outbox ra thread khác.
- Transaction rollback khi một trong hai thao tác ghi thất bại.

Đây là điều kiện kỹ thuật cốt lõi của pattern.

## 7. Outbox Relay: đưa event từ database sang broker

Relay là thành phần đọc những Outbox record đã commit và gửi message đến broker. Có hai hướng phổ biến: polling publisher và Change Data Capture (CDC).

### 7.1. Polling publisher

Polling publisher định kỳ truy vấn bảng Outbox để tìm record chưa gửi:

1. Tìm batch event đến hạn gửi.
2. Claim batch để tránh nhiều worker gửi cùng lúc.
3. Commit việc claim hoặc lease.
4. Gửi event đến broker.
5. Khi broker xác nhận, đánh dấu event đã publish.
6. Nếu thất bại, lên lịch retry.

Polling dễ triển khai và không cần hệ thống CDC riêng. Đổi lại, cần quản lý tần suất poll, batch size, lease, index và tải truy vấn.

### 7.2. Claim record khi có nhiều worker

Nếu nhiều relay cùng chạy, chúng không nên đọc rồi gửi cùng một batch mà không có cơ chế phối hợp. Với PostgreSQL, có thể dùng `FOR UPDATE SKIP LOCKED` để mỗi worker claim các hàng khác nhau.

Ví dụ khái niệm:

~~~sql
WITH candidates AS (
    SELECT id
    FROM outbox_event
    WHERE published_at IS NULL
      AND next_attempt_at <= now()
      AND (locked_until IS NULL OR locked_until < now())
    ORDER BY created_at, id
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
UPDATE outbox_event AS event
SET locked_by = :worker_id,
    locked_until = now() + interval '30 seconds',
    attempts = attempts + 1
FROM candidates
WHERE event.id = candidates.id
RETURNING event.*;
~~~

Transaction claim nên ngắn và commit trước khi gọi broker. Lease giúp worker khác có thể nhận lại record nếu worker hiện tại chết và lease hết hạn.

Đây là ví dụ theo PostgreSQL; database khác có cú pháp locking và cách claim khác. Cần kiểm tra query plan, thời hạn lease và hành vi khi broker xử lý lâu hơn lease.

### 7.3. Gửi message và xác nhận

Sau khi claim, relay gửi payload tới broker. Chỉ đánh dấu published sau khi nhận được acknowledgement theo semantics của client/broker đang dùng.

~~~java
for (OutboxRecord record : claimedRecords) {
    try {
        broker.publish(
            record.eventType(),
            record.aggregateId(),
            record.payload(),
            record.id().toString()
        );

        outbox.markPublished(record.id(), clock.instant());
    } catch (Exception error) {
        outbox.scheduleRetry(
            record.id(),
            nextAttempt(record.attempts()),
            safeErrorCode(error)
        );
    }
}
~~~

Đoạn code chỉ mô tả luồng. Cần quyết định rõ publish API là đồng bộ hay bất đồng bộ và acknowledgement có nghĩa broker đã nhận, đã ghi bền vững hay chỉ mới nhận vào client buffer.

Không nên giữ database row lock trong suốt thời gian gọi broker nếu thời gian mạng không xác định. Cách claim bằng lease rồi gửi ngoài transaction giúp giảm thời gian giữ khóa, nhưng cho phép gửi trùng khi worker gặp sự cố ở khoảng giữa broker acknowledgement và cập nhật Outbox.

Khi cập nhật trạng thái, relay nên kiểm tra record vẫn thuộc lease/token của worker hiện tại, chẳng hạn điều kiện `locked_by = :worker_id`. Điều này ngăn một worker cũ ghi đè trạng thái claim mới sau khi lease hết hạn. `scheduleRetry` cũng cần đặt `next_attempt_at` và giải phóng lease theo cách nguyên tử. Lease/token không loại bỏ khả năng duplicate nếu broker đã nhận event trước khi worker gặp sự cố.

### 7.4. Vì sao phải chấp nhận gửi trùng?

Giả sử:

1. Relay gửi event E.
2. Broker ghi nhận E và trả acknowledgement.
3. Relay dừng trước khi cập nhật `published_at`.
4. Lease hết hạn.
5. Worker khác gửi lại E.

Database vẫn thấy E chưa publish, nên retry là hành vi đúng để tránh mất event. Consumer có thể nhận E hai lần; idempotency phải được xử lý ở phía nhận.

Không có cách suy ra chắc chắn từ timeout rằng broker chưa nhận message. Đây là lý do retry cần kết hợp event ID và consumer idempotency.

## 8. Change Data Capture (CDC) làm relay

### 8.1. CDC là gì?

CDC đọc các thay đổi đã commit từ transaction log hoặc cơ chế log của database, rồi chuyển chúng đến hệ thống downstream. Với Outbox, ứng dụng vẫn ghi event vào bảng Outbox trong cùng transaction; connector CDC đọc bản ghi mới và phát message.

Ví dụ hệ sinh thái có thể dùng Debezium cùng Kafka Connect và Outbox Event Router. Cấu hình cụ thể phụ thuộc database, connector và schema Outbox.

### 8.2. Polling và CDC

| Tiêu chí | Polling publisher | CDC |
|---|---|---|
| Cách đọc | Query các record chưa publish | Đọc transaction log/change stream |
| Độ trễ | Theo chu kỳ poll hoặc batch | Có thể gần thời gian thực |
| Vận hành | Cần quản lý worker, lease, retry | Cần quản lý connector, offset và log retention |
| Tải database | Truy vấn lặp và cập nhật trạng thái | Đọc log và có thể cần schema/table routing |
| Độ linh hoạt | Dễ tùy biến logic theo record | Phụ thuộc năng lực connector và routing |
| Phù hợp | Hệ thống vừa/nhỏ, muốn tự kiểm soát | Hệ thống event stream lớn hoặc đã có CDC |

CDC không loại bỏ yêu cầu idempotency. Connector có thể phát lại khi restart hoặc khi offset chưa được xác nhận. Consumer vẫn cần xử lý message trùng.

### 8.3. Ai đánh dấu event đã gửi?

Với polling, ứng dụng thường cập nhật trạng thái Outbox như published hoặc ghi timestamp. Với CDC, connector quản lý offset của log; bản ghi Outbox có thể được giữ lại rồi dọn theo chính sách retention.

Không nên vừa cấu hình CDC theo dõi delete vừa xóa Outbox quá sớm mà chưa hiểu connector cần đọc log và schema như thế nào. Quy trình cleanup phải tương thích với cách CDC xử lý dữ liệu.

## 9. Retry, backoff và poison event

### 9.1. Retry có kiểm soát

Lỗi broker hoặc mạng có thể tạm thời. Relay nên retry với exponential backoff và jitter để tránh nhiều worker cùng dồn request vào broker:

~~~text
delay = min(maxDelay, baseDelay * 2^attempt)
nextAttempt = now + delay + randomJitter
~~~

Giới hạn số lần retry liên tiếp hoặc dùng trạng thái cần can thiệp tùy yêu cầu. Không xóa event chỉ vì một số lần gửi thất bại.

### 9.2. Phân loại lỗi

- Lỗi mạng hoặc broker tạm thời: retry.
- Broker từ chối do quota hoặc unavailable: backoff và cảnh báo.
- Payload không hợp lệ: có thể là lỗi dữ liệu/schema, cần quarantine hoặc dead-letter workflow.
- Credential hết hạn: dừng hoặc giảm tốc relay và cảnh báo vận hành.
- Event quá lớn: xử lý theo giới hạn broker và hợp đồng payload; không retry vô hạn cùng một payload.

### 9.3. Poison event

Poison event là record liên tục thất bại do một vấn đề không tự hết, chẳng hạn schema sai hoặc payload vượt giới hạn. Nếu một event lỗi chặn cả batch, các event phía sau có thể bị đói.

Có thể:

- Ghi trạng thái cần can thiệp và giữ nguyên payload.
- Đưa metadata lỗi vào dead-letter store có quyền truy cập kiểm soát.
- Cho phép operator retry sau khi sửa dependency hoặc mapping.
- Giữ lại event ID và lịch sử attempts để audit.
- Cảnh báo theo tuổi của event lâu nhất chưa gửi.

Không nên âm thầm bỏ qua hoặc xóa event lỗi vì có thể làm mất một bước nghiệp vụ liên context.

### 9.4. Không retry mù quáng lỗi vĩnh viễn

Retry liên tục payload không hợp lệ không làm nó trở nên hợp lệ. Cần phân biệt lỗi tạm thời và lỗi cần can thiệp. Một chính sách retry tốt có trạng thái cuối hoặc quy trình xử lý thủ công có kiểm soát.

## 10. Idempotency ở consumer

### 10.1. Consumer phải giả định có message trùng

Vì relay có thể gửi lại, consumer cần xử lý cùng một event nhiều lần mà không lặp tác dụng nghiệp vụ ngoài ý muốn.

Một cách phổ biến là bảng Inbox hoặc ProcessedMessage:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(160) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer mở transaction database, ghi nhận event ID và áp dụng thay đổi nghiệp vụ trong cùng transaction:

~~~java
@Transactional
public void handle(OrderConfirmed event) {
    boolean firstDelivery =
        inbox.tryRecord("inventory-order-confirmed", event.eventId());

    if (!firstDelivery) {
        return;
    }

    Stock stock = stocks.findForOrder(event.orderId())
        .orElseThrow(() -> new StockNotFound(event.orderId()));

    stock.reserve(event.lines());
}
~~~

Ví dụ giả định `tryRecord` dùng unique constraint để phân biệt lần đầu và message trùng. Nếu xử lý stock thất bại và transaction rollback, Inbox insert cũng rollback; broker có thể redeliver để thử lại.

### 10.2. Inbox insert và business update phải cùng transaction

Nếu consumer đánh dấu event đã xử lý rồi mới cập nhật nghiệp vụ ở transaction khác, process có thể dừng giữa hai thao tác:

- Inbox đã ghi nhưng nghiệp vụ chưa cập nhật: lần gửi lại bị bỏ qua, mất xử lý.
- Nghiệp vụ đã cập nhật nhưng Inbox chưa ghi: lần gửi lại có thể thực hiện tác dụng lần hai.

Đặt Inbox insert và thay đổi nghiệp vụ trong cùng local transaction giúp tránh khoảng lỗi này khi chúng dùng cùng database.

Consumer cũng cần xác nhận (ack) message với broker sau khi transaction database cục bộ commit thành công. Nếu ack trước rồi transaction rollback, broker có thể không gửi lại message dù thay đổi nghiệp vụ chưa được lưu. Nếu commit thành công nhưng ack thất bại, broker có thể giao lại; Inbox sẽ nhận diện lần giao trùng.

### 10.3. Idempotency không chỉ là lưu event ID

Event ID giúp nhận diện cùng một lần phát. Nếu publisher tạo event ID mới cho mỗi lần retry thì consumer không thể nhận ra đó là cùng message. Relay phải giữ nguyên event ID qua mọi lần gửi lại.

Nếu một nghiệp vụ cần chống lặp theo business key, ví dụ một order chỉ được giữ chỗ một lần, consumer cũng có thể cần unique constraint hoặc idempotency key theo Order ID. Event ID và business idempotency giải quyết hai lớp khác nhau.

Một số broker có idempotent producer để giảm duplicate do retry trong phạm vi session/sequence của producer. Tính năng đó hữu ích nhưng không thay thế Inbox: relay có thể khởi động lại, gửi lại một event đã commit từ trước hoặc publish qua producer session mới.

### 10.4. Ghi Inbox nguyên tử

`tryRecord` nên dùng thao tác insert nguyên tử dựa trên unique key để trả lời chính xác message này đã được consumer ghi nhận hay chưa. Với PostgreSQL, có thể dùng:

~~~sql
INSERT INTO processed_message (consumer_name, event_id)
VALUES (:consumer_name, :event_id)
ON CONFLICT DO NOTHING
RETURNING event_id;
~~~

Có hàng trả về nghĩa là lần giao này đã được ghi nhận mới; không có hàng trả về nghĩa là event đã được xử lý trước đó. Cách này tránh dựa vào một truy vấn kiểm tra rồi insert vốn có race condition khi hai delivery đến đồng thời. Không nên bắt unique-constraint exception rồi tiếp tục dùng cùng transaction một cách tùy tiện, vì provider/database có thể đã đánh dấu transaction rollback-only.

## 11. Thứ tự event theo aggregate

### 11.1. Vì sao thứ tự có thể bị đảo?

Một Order có thể phát:

1. OrderSubmitted.
2. OrderConfirmed.
3. OrderCancelled.

Nếu nhiều relay worker gửi song song, event thứ hai có thể đến broker trước event thứ nhất. Broker cũng có thể chỉ bảo đảm thứ tự trong một partition hoặc một luồng cụ thể.

### 11.2. Dùng aggregate sequence

Aggregate có thể duy trì sequence tăng dần cho mỗi event phát sinh. Outbox lưu sequence cùng aggregate ID:

| Aggregate ID | Sequence | Event |
|---|---:|---|
| order-123 | 1 | OrderSubmitted |
| order-123 | 2 | OrderConfirmed |
| order-123 | 3 | OrderCancelled |

Consumer có thể kiểm tra sequence để phát hiện event đến muộn, trùng hoặc thiếu. Có thể dùng aggregate ID làm partition key để các event của cùng aggregate đi cùng partition.

### 11.3. Chỉ gửi event tiếp theo khi event trước đã xử lý

Nếu thứ tự là yêu cầu cứng, relay cần tránh claim event sequence N+1 khi N chưa được xác nhận publish. Có thể:

- Chia partition/worker theo aggregate key.
- Query chỉ lấy event sớm nhất chưa publish của từng aggregate.
- Dùng một luồng tuần tự cho mỗi partition.
- Để consumer kiểm tra sequence và trì hoãn event đến sớm.

Đánh đổi là throughput và mức song song giảm khi nhiều event cùng aggregate. Chỉ bảo đảm thứ tự ở phạm vi thực sự cần, thường là theo một aggregate hoặc partition, thay vì yêu cầu thứ tự toàn hệ thống.

### 11.4. Timestamp không thay thế sequence

Timestamp có thể trùng, lệch giữa node hoặc phản ánh lúc tạo record thay vì thứ tự commit. Nếu thứ tự nghiệp vụ quan trọng, dùng sequence do aggregate hoặc cơ chế lưu trữ cấp phát có kiểm soát.

## 12. Versioning và tiến hóa event contract

Integration event là hợp đồng giữa các Bounded Context. Khi contract thay đổi, producer và consumer có thể được triển khai ở các thời điểm khác nhau.

### 12.1. Thay đổi tương thích

Thêm field optional với default hợp lý thường dễ tương thích hơn việc đổi tên hoặc đổi kiểu field hiện tại. Tuy nhiên, mức tương thích còn phụ thuộc serializer, schema registry và cách consumer xử lý field lạ.

### 12.2. Thay đổi phá vỡ tương thích

Các thay đổi như xóa field bắt buộc, đổi semantics, đổi đơn vị hoặc đổi cấu trúc có thể làm consumer cũ xử lý sai.

Giải pháp có thể gồm:

- Tăng event version.
- Duy trì consumer tương thích ngược trong giai đoạn chuyển đổi.
- Phát event mới song song khi có kế hoạch migration.
- Dùng schema registry và compatibility policy.
- Chuyển đổi payload cũ bằng adapter khi cần replay.

### 12.3. Event cũ có thể được phát lại

Outbox record hoặc event archive có thể được dùng để replay sau sự cố. Vì vậy, payload cần đủ thông tin để consumer hiểu event theo schema version của nó.

Không nên tái dựng event cũ từ trạng thái aggregate hiện tại. Hãy giữ payload snapshot hoặc lưu trữ dữ liệu lịch sử cần thiết.

## 13. Bảo mật và quyền riêng tư của payload

Outbox là nơi lưu bản sao dữ liệu sẽ được gửi sang context khác. Điều đó tạo thêm một vị trí lưu trữ cần bảo vệ.

- Chỉ đưa dữ liệu consumer thực sự cần.
- Không đưa password, access token, secret hoặc thông tin xác thực vào event.
- Hạn chế dữ liệu cá nhân; cân nhắc token/reference thay cho dữ liệu đầy đủ.
- Bảo vệ database, log, dead-letter store và công cụ quản trị.
- Định nghĩa thời hạn lưu Outbox và payload archive.
- Có chính sách xử lý yêu cầu xóa hoặc ẩn dữ liệu theo nghĩa vụ của hệ thống.

Không nên ghi toàn bộ exception hoặc payload nhạy cảm vào `last_error`. Lưu mã lỗi và thông tin chẩn đoán đã lọc phù hợp hơn.

## 14. Vận hành và quan sát Outbox

Outbox tạo một hàng đợi bền vững trong database. Nếu relay dừng lâu, số record chưa gửi sẽ tăng. Cần quan sát cả số lượng và tuổi của record.

Các chỉ số hữu ích:

- Số Outbox record chưa publish.
- Tuổi của event chưa publish lâu nhất.
- Thời gian từ occurred_at đến published_at.
- Số lần retry và số event bị quarantine.
- Tốc độ tạo event so với tốc độ publish.
- Số lần broker acknowledgement thất bại.
- Thời gian xử lý một batch và số record mỗi batch.
- Số message trùng được consumer phát hiện.

### 14.1. Backlog và cảnh báo

Một backlog tăng liên tục có thể cho thấy broker không khả dụng, relay không đủ worker, truy vấn polling chậm hoặc payload thường xuyên lỗi.

Cảnh báo nên dựa trên tuổi event chưa gửi và xu hướng backlog, không chỉ một ngưỡng số lượng cố định. Một backlog 1.000 event có thể bình thường trong đợt cao điểm nhưng bất thường trong một hệ thống thường chỉ có vài event mỗi phút.

### 14.2. Cleanup và retention

Outbox record đã publish có thể được xóa hoặc chuyển sang archive sau một thời gian. Cần giữ đủ lâu cho:

- Điều tra sự cố.
- Replay có kiểm soát.
- Đối chiếu với broker và consumer.
- Yêu cầu audit.

Nếu dùng CDC, cleanup phải tuân theo yêu cầu connector và transaction log. Nếu dùng polling, có thể phân vùng theo thời gian hoặc xóa theo batch để tránh transaction cleanup quá lớn.

Không xóa record chưa publish hoặc record đang được lease mà không có quy trình phục hồi rõ ràng.

### 14.3. Quyền vận hành thủ công

Operator có thể cần:

- Xem event và lịch sử retry.
- Tạm dừng relay.
- Retry một event sau khi khắc phục lỗi.
- Chuyển event sang trạng thái cần xử lý.
- Tra cứu event ID, aggregate ID và correlation ID.

Các thao tác thủ công phải có audit, phân quyền và cơ chế tránh phát lại nhầm payload nhạy cảm.

## 15. Outbox trong quy trình Saga và nhiều Bounded Context

Outbox thường là một thành phần trong kiến trúc event-driven và Saga.

Ví dụ luồng đặt hàng:

1. Ordering xác nhận đơn và ghi OrderConfirmed cùng Outbox trong transaction cục bộ.
2. Relay gửi OrderConfirmed.
3. Inventory nhận event, ghi Inbox và giữ chỗ tồn kho trong transaction của Inventory.
4. Inventory ghi StockReserved hoặc StockReservationRejected cùng Outbox của chính nó.
5. Ordering nhận kết quả và tiếp tục quy trình.
6. Nếu giữ chỗ thất bại, Ordering có thể hủy đơn hoặc yêu cầu bước bù trừ theo chính sách.

Mỗi service sở hữu database của mình và ghi Outbox cho sự kiện do chính service đó phát sinh. Không có một transaction database duy nhất bao trùm toàn bộ Saga.

~~~mermaid
sequenceDiagram
    participant O as Ordering
    participant ODB as Ordering DB
    participant OR as Ordering Relay
    participant B as Broker
    participant I as Inventory
    participant IDB as Inventory DB
    participant IR as Inventory Relay
    O->>ODB: Confirm Order + Outbox
    Note over ODB: Commit cục bộ
    OR->>ODB: Đọc Outbox
    OR->>B: OrderConfirmed
    B->>I: OrderConfirmed
    I->>IDB: Inbox + Reserve Stock + Outbox
    Note over IDB: Commit cục bộ
    IR->>IDB: Đọc Outbox
    IR->>B: StockReserved
    B->>O: StockReserved
~~~

Nếu một bước không thể hoàn tất, Saga điều phối retry, timeout và compensation. Outbox bảo đảm việc phát event của từng bước gắn với transaction cục bộ; nó không tự định nghĩa chính sách bù trừ.

## 16. So sánh với các lựa chọn khác

| Cách làm | Ưu điểm | Giới hạn |
|---|---|---|
| Publish trực tiếp trong transaction | Code ngắn, dễ bắt đầu | Database và broker không commit nguyên tử; có thể phát event cho thay đổi rollback |
| Publish sau commit trong memory callback | Không gửi event khi transaction rollback | Process có thể dừng sau commit trước khi gửi; ý định phát không bền vững |
| Transactional Outbox + polling | Dễ hiểu, tự kiểm soát retry và lease | Polling tạo tải truy vấn; cần quản lý backlog và duplicate |
| Transactional Outbox + CDC | Độ trễ thấp, tận dụng transaction log | Vận hành connector, offset, schema và retention phức tạp hơn |
| Distributed transaction/2PC | Có thể phối hợp nhiều resource nếu hệ thống hỗ trợ | Coupling, độ phức tạp và giới hạn hỗ trợ cao; không phải lựa chọn mặc định cho microservices |

Không phải use case nào cũng cần Outbox. Nếu việc gửi message không quan trọng, có thể chấp nhận best-effort. Nếu event là tín hiệu bắt buộc để context khác tiếp tục một quy trình nghiệp vụ, Outbox thường là lựa chọn đáng cân nhắc.

## 17. Kiểm thử Transactional Outbox

### 17.1. Aggregate và Outbox cùng commit

Kiểm thử use case thành công:

- Order chuyển sang Confirmed.
- Outbox có đúng integration event.
- Event ID và payload khớp với trạng thái nghiệp vụ tại thời điểm xác nhận.

### 17.2. Rollback thì không có cả hai thay đổi

Buộc Outbox insert thất bại hoặc tạo lỗi trước commit:

- Order không được lưu ở trạng thái Confirmed.
- Outbox event không tồn tại.
- Không có message nào được publish.

Đây là test quan trọng nhất để xác minh hai thao tác ghi thực sự cùng transaction.

### 17.3. Relay retry

Kiểm thử các trường hợp:

- Broker unavailable: event chưa được đánh dấu published.
- Broker acknowledgement thành công: event được đánh dấu published.
- Worker chết sau acknowledgement nhưng trước khi đánh dấu: event có thể được gửi lại.
- Lease hết hạn: worker khác có thể claim event.
- Payload lỗi: event được quarantine hoặc chuyển sang trạng thái cần can thiệp theo policy.

### 17.4. Consumer idempotency

Gửi cùng một event ID hai lần:

- Lần đầu ghi Inbox và thay đổi nghiệp vụ.
- Lần thứ hai được nhận diện là duplicate.
- Tác dụng nghiệp vụ chỉ xảy ra một lần trong database của consumer.

### 17.5. Kiểm thử thứ tự

Nếu thứ tự event theo aggregate là bắt buộc, phát nhiều event cho cùng aggregate và xác minh relay/consumer không áp dụng sequence sau trước sequence trước. Đồng thời kiểm thử hai aggregate khác nhau vẫn có thể được xử lý song song.

## 18. Những sai lầm thường gặp

**Publish trực tiếp rồi mới commit.** Consumer có thể nhận sự kiện cho thay đổi bị rollback. Hãy ghi Outbox cùng transaction và publish sau commit.

**Commit database rồi gửi message mà không lưu ý định gửi.** Process có thể dừng giữa hai thao tác và làm mất event. Outbox lưu ý định phát một cách bền vững.

**Ghi Outbox bằng transaction riêng.** Hai thao tác không còn nguyên tử. Outbox phải tham gia transaction ghi aggregate.

**Đặt Outbox ở database khác.** Vấn đề dual write vẫn tồn tại nếu không có một cơ chế phân tán khác. Hãy đặt Outbox trong database của service phát event.

**Cho rằng Outbox bảo đảm exactly once.** Relay có thể gửi trùng. Giữ event ID ổn định và thiết kế consumer idempotent.

**Đánh dấu published trước khi broker xác nhận.** Nếu publish thất bại sau đó, event bị mất khỏi hàng đợi cần gửi. Chỉ cập nhật trạng thái sau acknowledgement theo semantics đã chọn.

**Giữ row lock trong lúc gọi broker.** Network call có thể kéo dài và giữ khóa database. Dùng claim/lease với transaction ngắn nếu phù hợp.

**Không xử lý thứ tự event.** Nhiều worker có thể đảo thứ tự. Dùng aggregate sequence và partition/claim policy khi thứ tự có ý nghĩa.

**Tuần tự hóa trực tiếp Entity ORM.** Payload có thể kéo theo quan hệ lazy, dữ liệu nhạy cảm và contract nội bộ. Tạo integration event DTO riêng.

**Dựng payload từ aggregate hiện tại lúc relay chạy.** Trạng thái có thể đã thay đổi. Lưu snapshot payload tại thời điểm nghiệp vụ xảy ra.

**Retry vô hạn mà không quan sát.** Poison event có thể chiếm tài nguyên và chặn batch. Cần backoff, phân loại lỗi, quarantine và cảnh báo.

**Xóa Outbox quá sớm.** Việc điều tra, replay và CDC có thể mất dữ liệu cần thiết. Định nghĩa retention dựa trên yêu cầu vận hành.

**Bỏ qua Inbox ở consumer.** Duplicate delivery có thể lặp tác dụng nghiệp vụ. Dùng event ID, unique constraint và transaction cục bộ.

## 19. Quy trình thiết kế và triển khai

1. Xác định thay đổi nghiệp vụ nào cần thông báo cho context khác.
2. Xác định integration event và consumer cần dữ liệu gì.
3. Phân biệt domain event nội bộ với integration event công khai.
4. Thiết kế event ID, aggregate ID, sequence, event type, version và payload.
5. Tạo Outbox table trong database của service phát event.
6. Đặt ghi aggregate và Outbox record trong cùng transaction.
7. Xây relay polling hoặc CDC theo quy mô và năng lực vận hành.
8. Thiết kế acknowledgement, lease, retry, backoff và poison-event workflow.
9. Bảo đảm consumer idempotent bằng Inbox hoặc business idempotency key.
10. Xác định thứ tự event cần bảo đảm ở phạm vi aggregate/partition nào.
11. Thiết kế schema evolution, retention, cleanup và quyền truy cập payload.
12. Kiểm thử rollback, retry, duplicate, ordering và tình huống process dừng.
13. Theo dõi backlog, tuổi event, publish latency và lỗi consumer trong production.

~~~mermaid
flowchart TD
    A["Use case thay đổi aggregate"] --> B["Tạo integration event snapshot"]
    B --> C["Ghi aggregate + Outbox trong cùng transaction"]
    C --> D{"Transaction commit?"}
    D -->|Không| E["Rollback cả hai"]
    D -->|Có| F["Relay đọc Outbox đã commit"]
    F --> G["Publish tới broker"]
    G --> H{"Broker acknowledge?"}
    H -->|Không| I["Backoff và retry"]
    I --> F
    H -->|Có| J["Đánh dấu published"]
    G --> K["Consumer nhận message"]
    K --> L["Inbox/idempotency + business update"]
~~~

## 20. Checklist trước khi đưa Outbox vào production

**Tính nguyên tử**

- Aggregate và Outbox có cùng database transaction không?
- Có dùng cùng transaction manager và datasource không?
- Outbox insert thất bại có làm rollback thay đổi aggregate không?
- Có đường code nào publish trực tiếp bỏ qua Outbox không?

**Event contract**

- Event ID có duy nhất và giữ nguyên qua retry không?
- Payload có phải snapshot tại thời điểm nghiệp vụ xảy ra không?
- Event type, version, timestamp và aggregate identity có rõ không?
- Có tránh dữ liệu nhạy cảm và object graph nội bộ không?
- Có chính sách tương thích schema và replay không?

**Relay**

- Có claim/lease an toàn khi chạy nhiều worker không?
- Chỉ đánh dấu published sau acknowledgement không?
- Retry có backoff, jitter và giới hạn phù hợp không?
- Poison event có thể được quarantine và xử lý thủ công không?
- Có kiểm soát thứ tự event khi nghiệp vụ yêu cầu không?

**Consumer**

- Consumer có idempotent với cùng event ID không?
- Inbox insert và business update có cùng local transaction không?
- Có business key/unique constraint để chống lặp nghiệp vụ không?
- Có xử lý event cũ, event sai version và event đến sai thứ tự không?

**Vận hành**

- Có dashboard backlog, oldest event age và publish latency không?
- Có cảnh báo relay dừng hoặc event bị kẹt không?
- Retention và cleanup có an toàn cho replay/CDC không?
- Operator có thể tra cứu, retry và audit thao tác không?
- Có correlation ID để lần theo một quy trình qua nhiều context không?

Transactional Outbox nối thay đổi nghiệp vụ với ý định phát sự kiện bằng một lần commit database. Relay chịu trách nhiệm chuyển ý định đó sang broker và retry khi cần; consumer chịu trách nhiệm xử lý lặp an toàn. Khi kết hợp các phần này với event contract ổn định, thứ tự phù hợp và quan sát vận hành, các Bounded Context có thể phối hợp tin cậy hơn mà không cần chia sẻ transaction database xuyên hệ thống.
