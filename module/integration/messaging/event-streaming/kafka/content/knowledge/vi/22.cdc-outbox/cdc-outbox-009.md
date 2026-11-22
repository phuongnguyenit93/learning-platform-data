# Thiết kế outbox event ID, aggregate key và thứ tự sự kiện

## Ba câu hỏi phải trả lời cho mỗi outbox event

Khi ứng dụng ghi thay đổi nghiệp vụ và event vào cùng database transaction, transactional outbox bảo đảm rằng event cần phát không bị tách rời khỏi thay đổi đã commit. Tuy nhiên, để downstream xử lý đúng khi có retry, restart, replay hoặc nhiều request cập nhật cùng một aggregate, mỗi event cần có ba thuộc tính được thiết kế rõ ràng:

- **Event ID:** định danh ổn định của một sự kiện logic, dùng để nhận diện và chống xử lý trùng.
- **Aggregate key:** khóa đại diện cho đối tượng nghiệp vụ mà event thuộc về, dùng để route các event liên quan vào cùng Kafka partition.
- **Aggregate sequence:** số thứ tự tăng đơn điệu trong phạm vi aggregate, dùng để kiểm tra thứ tự và phát hiện event đến trễ hoặc thiếu.

Ba giá trị này có mục đích khác nhau. Event ID trả lời “đây có phải cùng một event đã gặp trước đó không?”. Aggregate key trả lời “các event nào cần đi cùng một luồng có thứ tự?”. Sequence trả lời “event này đứng ở vị trí nào trong lịch sử aggregate?”. Không nên dùng một trường cho cả ba vai trò.

Trong module KAFKA, thiết kế đúng ba thuộc tính này giúp CDC/outbox phát event có thể retry và replay an toàn, đồng thời giữ ordering theo đơn hàng, tài khoản, khách hàng hoặc aggregate khác.

## 1. Event ID: định danh ổn định của event

### 1.1 Event ID khác aggregate ID

Một aggregate có thể phát nhiều event trong suốt vòng đời. Ví dụ order `order-42` lần lượt phát `OrderPlaced`, `PaymentAuthorized`, `OrderPacked` và `OrderShipped`. Các event này cùng thuộc aggregate `order-42`, nhưng phải có event ID riêng.

| Trường | Ví dụ | Ý nghĩa |
|---|---|---|
| `event_id` | `0194...` | Định danh một event logic |
| `aggregate_id` | `order-42` | Định danh order sở hữu event |
| `aggregate_type` | `Order` | Loại aggregate |
| `aggregate_sequence` | `7` | Vị trí event trong lịch sử aggregate |

Không dùng `aggregate_id` làm event ID vì nhiều event của cùng order sẽ bị xem là một event. Không dùng sequence đơn lẻ làm event ID vì sequence chỉ duy nhất trong phạm vi aggregate, không duy nhất toàn hệ thống.

### 1.2 Chọn định dạng event ID

Event ID thường là UUID hoặc một định danh duy nhất do hệ thống cấp. Ví dụ:

```java
UUID eventId = UUID.randomUUID();
```

UUID ngẫu nhiên có xác suất va chạm rất thấp và không cần central ID generator. UUIDv7 có tính chất sắp xếp gần theo thời gian tạo, có thể hữu ích cho index/database, nhưng không thay thế aggregate sequence.

Không dùng timestamp đơn lẻ làm event ID: nhiều event có thể được tạo trong cùng đơn vị thời gian, clock giữa các instance có thể lệch và timestamp không thể hiện thứ tự commit đáng tin cậy.

Nếu một command được gửi lại do client retry, cần phân biệt hai trường hợp:

- Command retry là cùng một yêu cầu nghiệp vụ: dùng `command_id` hoặc idempotency key ổn định để tránh tạo hai aggregate transition và hai event logic.
- Một nghiệp vụ mới thực sự xảy ra: tạo event ID mới, dù payload có thể giống event trước.

Không tạo lại event ID khi relay/CDC đọc lại cùng một outbox row. ID được sinh và lưu cùng outbox row trong database; mọi lần publish lại phải giữ nguyên ID đó.

### 1.3 Event ID là khóa deduplication

Consumer có thể nhận cùng event nhiều lần do connector restart, producer retry ở tầng ứng dụng, offset commit thất bại hoặc replay. Consumer dùng `event_id` để phát hiện event đã xử lý.

Một bảng inbox đơn giản:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id       UUID NOT NULL,
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
```

Đặt `consumer_name` trong khóa để nhiều consumer logic độc lập có thể xử lý cùng một event. Trong cùng database transaction với side effect, consumer insert event ID vào bảng này. Nếu vi phạm unique constraint, event đã được xử lý trước đó và có thể bỏ qua theo chính sách.

Không ghi inbox marker trong một transaction riêng rồi mới thực hiện side effect ở transaction khác. Nếu marker commit nhưng side effect thất bại, lần phát lại sau có thể bị deduplicate và side effect không bao giờ được thực hiện. Inbox marker và side effect cần cùng transaction tại database đích.

## 2. Aggregate key: đưa event liên quan vào cùng partition

### 2.1 Aggregate key là khóa route

Kafka producer dùng record key để chọn partition. Khi các event của cùng aggregate dùng cùng key và cùng topic, chúng được route vào cùng partition theo partitioner hiện hành. Kafka bảo đảm thứ tự append/read trong một partition.

Ví dụ:

```text
Topic: order-events

Key=Order:order-42  -> Partition 2
Key=Order:order-42  -> Partition 2
Key=Order:order-42  -> Partition 2

Key=Order:order-99  -> Partition 0
Key=Order:order-99  -> Partition 0
```

Các event của `order-42` có thể được xử lý tuần tự trong partition 2; `order-99` có thể được xử lý song song ở partition 0.

### 2.2 Tạo key ổn định và không mơ hồ

Nếu ID chỉ duy nhất trong từng loại aggregate, ghép `aggregate_type` với `aggregate_id` để tạo key canonical:

```java
String aggregateKey = aggregateType + ":" + aggregateId;
```

Ví dụ `Order:42` và `Customer:42` là hai key khác nhau. Key phải ổn định giữa các phiên bản ứng dụng, không chứa timestamp ngẫu nhiên, request ID hoặc thông tin cá nhân không cần thiết.

Khi producer gửi event:

```java
ProducerRecord<String, OutboxEvent> record = new ProducerRecord<>(
        "domain-events",
        aggregateKey,
        event
);

kafkaTemplate.send(record);
```

Với Debezium Outbox Event Router, cấu hình cột aggregate ID làm Kafka record key theo schema outbox và phiên bản SMT đang dùng. Nếu dùng SMT, hãy xác minh key thực tế trong Kafka bằng consumer hoặc công cụ quan sát record; không chỉ dựa vào tên cột trong bảng.

### 2.3 Cùng key nhưng khác topic không tạo ordering chung

Kafka ordering chỉ áp dụng trong một partition. Nếu `OrderPlaced` được route vào topic `order-events` và `PaymentAuthorized` vào topic `payment-events`, dù hai record có cùng aggregate key, chúng nằm ở hai log độc lập. Consumer subscribe cả hai topic không có một thứ tự tổng thể được Kafka bảo đảm giữa chúng.

Nếu consumer cần thứ tự aggregate xuyên nhiều event type, cân nhắc route chúng vào cùng topic với một event envelope có `event_type`, hoặc dùng transaction metadata/sequence để consumer tự đồng bộ. Không giả định cùng key trên hai topic tạo một hàng đợi chung.

## 3. Aggregate sequence: thứ tự nghiệp vụ có thể kiểm chứng

### 3.1 Vì sao cần sequence nếu Kafka đã có offset?

Kafka offset là vị trí record trong một partition. Nó không phải phiên bản nghiệp vụ của aggregate:

- Một aggregate có thể chuyển sang partition khác nếu partition count hoặc partitioner thay đổi.
- Nhiều aggregate cùng chia sẻ một partition nên offset của chúng xen kẽ.
- Consumer có thể nhận event qua retry topic hoặc DLT replay, không còn theo thứ tự gốc.
- Một event có thể được gửi lại với offset mới dù cùng event ID.
- Consumer có thể subscribe nhiều topic/partition và không có một offset chung.

`aggregate_sequence` là số tăng đơn điệu do nguồn nghiệp vụ cấp cho mỗi event của một aggregate. Ví dụ:

| Aggregate | Event ID | Event type | Sequence |
|---|---|---|---:|
| `Order:42` | `evt-a1` | `OrderPlaced` | 1 |
| `Order:42` | `evt-a2` | `AddressChanged` | 2 |
| `Order:42` | `evt-a3` | `PaymentAuthorized` | 3 |
| `Order:99` | `evt-b1` | `OrderPlaced` | 1 |
| `Order:42` | `evt-a4` | `OrderPacked` | 4 |

Sequence chỉ cần liên tục trong phạm vi aggregate/stream đã định nghĩa. Không cần là số toàn cục cho cả hệ thống.

### 3.2 Sequence không phải timestamp

Timestamp biểu diễn thời điểm theo clock; sequence biểu diễn thứ tự logic đã được serialize cho aggregate. Hai transaction có thể chạy trên hai application instance với clock lệch nhau. Timestamp tạo event sớm hơn không chứng minh transaction đó commit trước.

Không sort event theo `created_at` hoặc UUIDv7 để thay thế sequence nếu nghiệp vụ yêu cầu thứ tự chính xác. Dùng sequence được cấp nguyên tử trong database transaction.

### 3.3 Aggregate version và event sequence

Một số domain model có `aggregate_version` tăng một lần cho mỗi lần cập nhật aggregate. Nếu mỗi lần cập nhật luôn tạo đúng một event, version có thể dùng làm sequence. Nếu một transaction tạo nhiều event, cần một event sequence riêng hoặc cấp một dải sequence cho các event trong transaction.

Không mặc định `aggregate_version` và `aggregate_sequence` là cùng một thứ. Hãy xác định rõ sequence đếm mỗi command, mỗi state transition hay mỗi event được phát.

## 4. Cấp sequence an toàn trong database

### 4.1 Lưu bộ đếm trên aggregate

Ví dụ PostgreSQL có cột `event_sequence` trong bảng `orders`:

```sql
ALTER TABLE orders
    ADD COLUMN event_sequence BIGINT NOT NULL DEFAULT 0;
```

Trong cùng transaction ghi order và outbox, cấp sequence bằng câu lệnh atomic:

```sql
UPDATE orders
SET event_sequence = event_sequence + 1
WHERE id = :order_id
RETURNING event_sequence;
```

Kết quả trả về được dùng làm `aggregate_sequence` của event vừa tạo. Cập nhật row khóa aggregate trong transaction; hai transaction cùng cập nhật một order sẽ phải tuần tự hóa trên row đó. Nếu transaction rollback, thay đổi bộ đếm và outbox row cùng rollback.

Nếu một transaction cần tạo ba event, có thể tăng bộ đếm thêm ba và cấp ba số liên tiếp trong cùng transaction. Hãy xác định thứ tự event trong command trước khi insert outbox rows.

### 4.2 Bảo vệ bằng unique constraint

Outbox schema có thể lưu các trường sau:

```sql
CREATE TABLE outbox_events (
    event_id            UUID PRIMARY KEY,
    aggregate_type      VARCHAR(100) NOT NULL,
    aggregate_id        VARCHAR(100) NOT NULL,
    aggregate_sequence  BIGINT NOT NULL,
    event_type          VARCHAR(200) NOT NULL,
    event_version       INTEGER NOT NULL,
    payload             JSONB NOT NULL,
    occurred_at         TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_outbox_aggregate_sequence
        UNIQUE (aggregate_type, aggregate_id, aggregate_sequence)
);

CREATE INDEX idx_outbox_aggregate_order
    ON outbox_events (aggregate_type, aggregate_id, aggregate_sequence);
```

Primary key bảo vệ event ID; unique constraint bảo vệ sequence không bị cấp trùng trong một aggregate. Hai ràng buộc này bắt được lỗi ở tầng database thay vì chỉ dựa vào code ứng dụng.

### 4.3 Không cấp sequence ngoài transaction

Nếu ứng dụng lấy sequence trong bộ nhớ, dùng timestamp hoặc tăng một biến local trước khi commit database, nhiều instance có thể tạo cùng sequence hoặc commit theo thứ tự khác với thứ tự cấp số.

Sequence phải được cấp và ghi outbox trong cùng database transaction với aggregate update. Dùng row lock, optimistic locking/retry hoặc một cơ chế serialize theo aggregate đã được kiểm chứng.

Với optimistic locking, nếu hai command cùng đọc version cũ, chỉ một transaction có thể commit update. Transaction còn lại phải đọc lại state và tạo lại event/sequence từ state mới; không gửi event cũ với sequence đã xung đột.

## 5. Ghi outbox event trong Spring transaction

### 5.1 Event envelope

Một event envelope có thể có cấu trúc:

```json
{
  "event_id": "4a1d8a4a-ec73-4e54-8f93-9a2a2b20f00a",
  "event_type": "OrderPlaced",
  "event_version": 1,
  "aggregate_type": "Order",
  "aggregate_id": "order-42",
  "aggregate_sequence": 7,
  "occurred_at": "2026-11-20T10:15:30Z",
  "correlation_id": "checkout-req-884",
  "causation_id": "command-119",
  "payload": {
    "customer_id": "customer-9",
    "total_amount": 1250000,
    "currency": "VND"
  }
}
```

`occurred_at` hỗ trợ audit và quan sát; `aggregate_sequence` mới là trường kiểm soát thứ tự. `correlation_id` liên kết nhiều hoạt động trong một luồng; `causation_id` chỉ ra command/event đã dẫn đến event hiện tại.

### 5.2 Ví dụ service

```java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final ObjectMapper objectMapper;

    @Transactional
    public void placeOrder(CreateOrderCommand command) {
        Order order = Order.create(command);
        orders.save(order);

        // Trong triển khai thực tế, repository gọi UPDATE ... RETURNING
        // hoặc cơ chế lock/version tương đương để cấp sequence nguyên tử.
        long sequence = orders.nextEventSequence(order.getId());

        UUID eventId = UUID.randomUUID();
        OrderPlaced event = new OrderPlaced(
                eventId,
                order.getId(),
                sequence,
                order.getCustomerId(),
                order.getTotalAmount()
        );

        outbox.save(OutboxEvent.from(
                eventId,
                "Order",
                order.getId(),
                sequence,
                "OrderPlaced",
                1,
                toJson(event)
        ));
    }
}
```

`orders.nextEventSequence()` là API repository minh họa; nó phải thực hiện cấp số atomically trong cùng transaction, không phải đọc rồi tăng một biến Java thông thường. `orders.save()` và `outbox.save()` phải dùng cùng database transaction manager.

### 5.3 Idempotency cho command tạo event

Nếu client gửi lại `PlaceOrder` vì không nhận response, ứng dụng có thể tạo order/event lần thứ hai nếu không có command idempotency. Dùng một `idempotency_key` duy nhất theo client/command và unique constraint trong database để một yêu cầu retry trả về kết quả đã có.

Command idempotency ngăn tạo hai nghiệp vụ; event ID ngăn xử lý cùng một event nhiều lần. Hai lớp bảo vệ giải quyết hai tình huống khác nhau.

## 6. Giữ ordering khi phát outbox sang Kafka

### 6.1 Kafka key và partition

Khi relay/CDC publish outbox row, record key cần là aggregate key ổn định, ví dụ `Order:order-42`. Producer partitioner sẽ route các event có cùng key vào cùng partition trong một topic với cùng partitioning configuration.

```text
Database outbox
  Order:42 seq=1  -> Kafka key Order:42 -> topic P2
  Order:99 seq=1  -> Kafka key Order:99 -> topic P0
  Order:42 seq=2  -> Kafka key Order:42 -> topic P2
  Order:42 seq=3  -> Kafka key Order:42 -> topic P2
```

Kafka giữ thứ tự record append trong partition 2. Để bảo đảm thứ tự nghiệp vụ, producer/relay còn phải gửi sequence 1 trước sequence 2 và sequence 3. Cùng key không tự sửa được trường hợp relay gửi sequence 3 trước sequence 2.

### 6.2 Concurrent relay có thể đảo thứ tự

Một polling relay có thể lấy nhiều outbox row rồi chia cho nhiều worker. Nếu worker xử lý song song các row của cùng aggregate, event sequence 8 có thể publish trước sequence 7 dù database lưu đúng thứ tự.

Các cách tránh:

- Phân công cùng aggregate vào một worker/queue theo key.
- Chỉ publish event kế tiếp khi sequence trước của aggregate đã được gửi thành công.
- Dùng CDC đọc transaction log và giữ source ordering theo khả năng connector, đồng thời route cùng aggregate key vào cùng Kafka partition.
- Có sequence ở event để consumer phát hiện reorder thay vì tin hoàn toàn vào relay.

Nếu dùng nhiều relay instance, cần ownership/partitioning hoặc khóa phù hợp để hai instance không đồng thời phát cùng aggregate. Lease/lock phải có fencing hoặc cơ chế hết hạn an toàn để instance cũ không tiếp tục publish sau khi mất quyền sở hữu.

### 6.3 Producer idempotence giúp gì?

Bật `enable.idempotence=true` giúp Kafka producer xử lý retry request mà không append trùng batch trong phạm vi producer ID/sequence. `acks=all` và cấu hình retry tương thích giúp tăng độ bền khi broker lỗi.

Idempotent producer không deduplicate hai lần gọi `send()` độc lập từ application relay, cũng không tự bảo đảm sequence 7 được gửi trước sequence 8 nếu code gọi send sai thứ tự. Event ID và aggregate sequence vẫn cần thiết.

### 6.4 Thay đổi partition count có thể ảnh hưởng ordering

Với partitioner dựa trên hash key và số partition, tăng partition count có thể làm cùng aggregate key được ánh xạ sang partition khác trong tương lai. Các event cũ vẫn nằm ở partition cũ, event mới có thể sang partition mới; Kafka không bảo đảm thứ tự giữa hai partition.

Nếu ordering theo aggregate là yêu cầu cứng, cần kế hoạch mở rộng partition có kiểm soát: dùng routing/partition mapping ổn định, tạo topic version mới và migrate, hoặc dùng sequence ở consumer để phát hiện/gỡ reorder. Không tăng partition count của topic quan trọng mà chưa đánh giá tác động đến key routing.

## 7. Consumer kiểm tra duplicate và sequence

### 7.1 Inbox deduplication

Consumer thực hiện side effect và ghi event ID đã xử lý trong cùng transaction database:

```java
@Transactional
public void handle(OrderEvent event) {
    boolean firstDelivery = inboxRepository.insertIfAbsent(
            "order-projection",
            event.eventId()
    );

    if (!firstDelivery) {
        return; // Event ID đã được xử lý
    }

    orderProjection.apply(event);
}
```

`insertIfAbsent()` cần được thực hiện bằng unique constraint/upsert có kiểm tra kết quả. Nếu insert inbox marker và update projection cùng transaction, rollback sẽ hoàn tác cả hai. Khi Kafka giao lại event, consumer có thể thử lại an toàn.

### 7.2 Kiểm tra sequence theo aggregate

Consumer có thể lưu sequence cuối đã áp dụng:

```sql
CREATE TABLE aggregate_checkpoints (
    consumer_name       VARCHAR(120) NOT NULL,
    aggregate_type      VARCHAR(100) NOT NULL,
    aggregate_id        VARCHAR(100) NOT NULL,
    last_sequence       BIGINT NOT NULL,
    PRIMARY KEY (consumer_name, aggregate_type, aggregate_id)
);
```

Khi nhận event:

- `sequence <= last_sequence`: event cũ hoặc duplicate; kiểm tra event ID và bỏ qua theo policy.
- `sequence = last_sequence + 1`: event kế tiếp; có thể áp dụng.
- `sequence > last_sequence + 1`: có gap; tạm hoãn/retry hoặc lấy event thiếu trước khi tiếp tục.

Chỉ dùng quy tắc contiguous sequence nếu consumer nhận đầy đủ mọi event trong phạm vi sequence đó. Nếu topic chỉ chứa một số loại event hoặc connector filter bớt bảng/event, sequence có thể có gap hợp lệ. Khi đó cần sequence riêng cho stream/consumer contract hoặc một cơ chế xác định gap nào được phép.

### 7.3 Event đến sai thứ tự

Giả sử consumer đã áp dụng sequence 10 nhưng nhận sequence 12 trước 11. Không nên áp dụng 12 rồi hy vọng 11 sẽ không gây lỗi. Có thể:

1. Đưa sequence 12 vào buffer có giới hạn theo aggregate.
2. Tìm sequence 11 trong Kafka/replay source hoặc chờ retry có giới hạn.
3. Khi sequence 11 được áp dụng, xử lý tiếp 12.
4. Nếu gap không được lấp trong deadline, đưa aggregate vào trạng thái cần điều tra/reconciliation.

Buffer phải bounded để tránh một aggregate bị thiếu event làm đầy bộ nhớ. Nếu event 11 bị mất do retention hoặc routing sai, cần quy trình rebuild projection từ snapshot/event history.

### 7.4 Kafka offset và aggregate sequence bổ sung cho nhau

Kafka committed offset giúp consumer tiếp tục đọc partition sau restart. Aggregate sequence giúp kiểm tra thứ tự nghiệp vụ của từng aggregate. Không thay thế offset bằng sequence; một partition chứa nhiều aggregate và consumer vẫn phải commit offset theo partition.

Khi side effect database thành công nhưng Kafka offset commit thất bại, record có thể được giao lại. Inbox event ID chặn side effect trùng; sequence bảo vệ khỏi áp dụng event cũ hoặc bỏ qua gap.

## 8. Retry, DLT và replay có thể làm thay đổi thứ tự

### 8.1 Retry topic tách event khỏi luồng gốc

Nếu sequence 20 lỗi và được đưa sang retry topic, consumer có thể tiếp tục xử lý sequence 21 trên topic chính. Khi sequence 20 quay lại sau, thứ tự quan sát không còn là 20 rồi 21.

Nếu aggregate yêu cầu ordering nghiêm ngặt, không dùng retry topic theo cách cho phép event sau vượt event lỗi. Có thể pause partition/aggregate, giữ trạng thái pending hoặc dùng sequence gate ở consumer.

### 8.2 DLT replay

Khi replay DLT, giữ nguyên event ID, aggregate key và aggregate sequence gốc. Không cấp event ID hoặc sequence mới chỉ vì đang replay; đó vẫn là cùng event logic.

Replay nên có rate limit và kiểm tra sequence trước khi áp dụng. Nếu aggregate đã tiến đến sequence 30 mà replay sequence 24, consumer cần quyết định đây là duplicate/stale, rebuild hay event cần bù trừ; không áp dụng mù quáng.

### 8.3 Snapshot và rebuild projection

Khi không thể lấp gap bằng replay, có thể rebuild projection từ snapshot nhất quán cộng event stream sau snapshot. Snapshot cần gắn mốc sequence/version cho từng aggregate hoặc checkpoint rõ ràng để consumer biết event nào đã được bao gồm.

Không ghép snapshot ở thời điểm T với event stream từ vị trí tùy ý; nếu mốc snapshot và checkpoint không nhất quán, projection có thể bỏ sót hoặc áp dụng trùng thay đổi.

## 9. Các nguyên tắc thiết kế schema outbox

Một schema outbox production thường cần các trường:

| Trường | Mục đích |
|---|---|
| `event_id` | Khóa duy nhất và deduplication |
| `aggregate_type` | Phân loại aggregate |
| `aggregate_id` | Định danh aggregate |
| `aggregate_sequence` | Thứ tự event trong aggregate |
| `event_type` | Tên event domain |
| `event_version` | Version của payload contract |
| `payload` | Nội dung event đã serialize |
| `occurred_at` | Thời điểm nghiệp vụ theo clock nguồn |
| `correlation_id` | Liên kết một luồng xử lý |
| `causation_id` | Command/event gây ra event hiện tại |

Các trường bổ sung như `tenant_id`, `traceparent`, `schema_ref` hoặc `source_service` có thể hữu ích. Tránh lưu thông tin nhạy cảm không cần thiết và tránh phụ thuộc vào cột database nội bộ trong contract public.

Ràng buộc database nên bảo vệ:

- `PRIMARY KEY (event_id)`.
- `UNIQUE (aggregate_type, aggregate_id, aggregate_sequence)` nếu sequence duy nhất cho từng aggregate.
- Index phục vụ connector/relay và quy trình cleanup.
- Foreign key hoặc retention policy phù hợp với aggregate lifecycle nếu cần.

Không tạo index quá nhiều trên bảng outbox có write rate cao mà chưa đo tác động đến transaction và WAL.

## 10. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng aggregate ID làm event ID | Các event của cùng aggregate bị deduplicate nhầm | Tạo event ID riêng cho từng event |
| Tạo event ID mới mỗi lần relay retry | Consumer không nhận ra cùng event được phát lại | Lưu ID trong outbox và giữ nguyên khi publish lại |
| Dùng timestamp để suy ra thứ tự | Clock skew và timestamp trùng gây reorder | Cấp aggregate sequence trong DB transaction |
| Không có aggregate key | Event của cùng aggregate rơi vào nhiều partition | Dùng key canonical ổn định |
| Cùng key nhưng route nhiều topic | Không có ordering tổng thể giữa topic | Dùng topic chung hoặc sequence/coordination |
| Relay xử lý song song cùng aggregate | Sequence sau có thể publish trước sequence trước | Serialize dispatch theo aggregate |
| Tăng partition count không đánh giá key mapping | Event mới của aggregate có thể sang partition khác | Migration/routing plan và sequence validation |
| Chỉ dựa vào Kafka offset | Không phát hiện event stale/gap sau replay | Dùng aggregate sequence |
| Inbox marker commit riêng với side effect | Có thể đánh dấu đã xử lý dù side effect thất bại | Cùng DB transaction và unique constraint |
| Retry topic cho event strict-order | Event sau vượt event lỗi | Pause/gate theo aggregate hoặc thiết kế retry có thứ tự |
| Replay cấp ID/sequence mới | Phá deduplication và lịch sử aggregate | Giữ nguyên metadata gốc khi replay |

## 11. Quy trình thiết kế và kiểm thử

1. Xác định aggregate boundary và event type cần phát.
2. Định nghĩa event ID ổn định, command idempotency key và quy tắc tạo ID.
3. Chọn aggregate key canonical, không chứa dữ liệu nhạy cảm.
4. Định nghĩa sequence: đếm mỗi event hay mỗi state transition; xác định phạm vi stream.
5. Cấp sequence trong cùng database transaction bằng row lock, optimistic locking hoặc cơ chế atomic tương đương.
6. Thêm primary/unique constraint cho event ID và aggregate sequence.
7. Ghi business state và outbox event trong cùng transaction.
8. Cấu hình CDC/relay route cùng aggregate key vào một Kafka topic/partition.
9. Bảo đảm relay không dispatch ngược thứ tự các event cùng aggregate.
10. Consumer ghi inbox marker cùng transaction với side effect.
11. Consumer kiểm tra sequence/gap nếu contract yêu cầu contiguous ordering.
12. Kiểm thử concurrent command, DB rollback, connector restart, producer timeout, duplicate delivery, retry topic, DLT replay và partition expansion.

## 12. Checklist production

- Event ID duy nhất cho mỗi event logic và không đổi qua retry/replay.
- Command idempotency được xử lý riêng với event deduplication.
- Aggregate key ổn định, canonical và được gửi làm Kafka record key.
- Các event cần ordering dùng cùng topic và cùng partitioning strategy.
- Aggregate sequence được cấp atomically trong database transaction.
- Unique constraint bảo vệ `(aggregate_type, aggregate_id, aggregate_sequence)`.
- Relay/CDC giữ thứ tự publish trong phạm vi aggregate.
- Producer idempotence bật phù hợp nhưng không được xem là deduplication nghiệp vụ.
- Consumer inbox marker và side effect cùng transaction.
- Consumer có chính sách cho duplicate, stale event và sequence gap.
- Retry/DLT/replay giữ nguyên event ID, aggregate key và sequence.
- Partition expansion được đánh giá vì có thể đổi mapping của key.
- Metrics theo dõi duplicate rate, sequence gap, reorder, outbox lag và retry/DLT age.
- Có quy trình rebuild/reconciliation khi event bị thiếu hoặc aggregate sequence không thể tiếp tục.

## Kết luận

Thiết kế outbox event tin cậy cần tách biệt ba khái niệm: event ID định danh một event logic, aggregate key route event liên quan vào cùng Kafka partition và aggregate sequence thể hiện thứ tự nghiệp vụ trong aggregate. Event ID phải giữ nguyên qua retry/replay; aggregate key phải ổn định; sequence phải được cấp nguyên tử trong cùng database transaction với business update và outbox insert.

Kafka bảo đảm thứ tự trong một partition, nhưng không tự bảo đảm relay gửi đúng sequence, không tạo thứ tự chung giữa nhiều topic và không ngăn consumer xử lý song song làm đảo thứ tự. Kết hợp key routing, relay serialization, producer idempotence, inbox deduplication và sequence validation giúp hệ thống KAFKA phát lại an toàn, phát hiện gap/reorder và giữ đúng lịch sử của từng aggregate.
