# CQRS và Event Sourcing như lựa chọn bổ sung theo nhu cầu

## 1. Mục tiêu và bối cảnh

Một ứng dụng thường phải phục vụ hai loại công việc khác nhau. Đường ghi bảo vệ quy tắc nghiệp vụ, kiểm tra trạng thái và xử lý cạnh tranh; đường đọc cần truy vấn nhanh, lọc theo nhiều chiều và trả dữ liệu phù hợp với màn hình. Mô hình quan hệ được chuẩn hóa có thể rất tốt cho giao dịch nhưng không thuận tiện cho mọi kiểu truy vấn. Một document tối ưu cho tìm kiếm lại không nhất thiết phù hợp để kiểm soát transaction và invariant.

**CQRS (Command Query Responsibility Segregation)** tách trách nhiệm xử lý lệnh thay đổi trạng thái khỏi trách nhiệm phục vụ truy vấn. **Event Sourcing** lưu lịch sử thay đổi dưới dạng sự kiện bất biến để dựng lại trạng thái bằng cách áp dụng chúng theo thứ tự hợp lệ.

Hai ý tưởng có thể kết hợp, nhưng không bắt buộc đi cùng nhau:

- CQRS có thể dùng một database quan hệ duy nhất, với command model và query model khác nhau trong cùng ứng dụng.
- Event Sourcing có thể tồn tại mà không cần nhiều read databases hay query services riêng.
- Có thể kết hợp cả hai khi cần lịch sử nghiệp vụ đầy đủ, nhiều read models và khả năng tái dựng dữ liệu.
- Cũng có thể không dùng cả hai nếu CRUD với database quan hệ đáp ứng tốt yêu cầu.

Bài này thuộc nhóm **Quan hệ kiến trúc**. Mục tiêu là xem đây là các lựa chọn có lợi ích, chi phí và điều kiện áp dụng cụ thể, không phải mặc định cho mọi microservice.

Sau bài học, bạn có thể:

1. Phân biệt Command, Query, CQRS, Event Sourcing, Domain Event và Event Log.
2. Thiết kế write model bảo vệ invariant và read model tối ưu truy vấn.
3. Hiểu eventual consistency, projection lag và read-your-writes.
4. Phân biệt event store với message broker, transactional outbox và audit log.
5. Thiết kế aggregate stream, event identity, sequence, concurrency và idempotency.
6. Dựng projections, snapshots, replay và xử lý schema evolution.
7. Nhận diện rủi ro về dữ liệu, quyền riêng tư, vận hành và disaster recovery.
8. Chọn CQRS riêng, Event Sourcing riêng, kết hợp hoặc CRUD truyền thống.
9. Xây lộ trình chuyển đổi từng phần thay vì rewrite toàn hệ thống.

Ví dụ xuyên suốt là nền tảng thương mại điện tử gồm Order, Payment, Inventory, Search và Reporting. Các ví dụ Java, SQL, JSON và broker chỉ mang tính minh họa; cần điều chỉnh theo domain và công nghệ thực tế.

## 2. Hai loại nhu cầu: ghi và đọc

Một yêu cầu ghi biểu đạt ý định thay đổi trạng thái:

- Tạo đơn hàng.
- Hủy đơn.
- Xác nhận thanh toán.
- Giữ hàng.
- Thay đổi địa chỉ giao hàng.

Một yêu cầu đọc lấy thông tin mà không thay đổi trạng thái:

- Tìm đơn theo khách hàng.
- Xem tổng tiền theo tháng.
- Lọc đơn theo trạng thái, vùng và ngày.
- Xem dashboard tồn kho.
- Tìm sản phẩm theo từ khóa.

Trong CRUD đơn giản, cùng một model và database thường xử lý cả hai. Điều này hợp lý khi quy mô và độ phức tạp vừa phải. Khi nhu cầu đọc tăng, bảng chuẩn hóa có thể cần nhiều joins, index và truy vấn phức tạp. Khi nhu cầu ghi tăng, việc thêm các trường phục vụ dashboard có thể làm transaction model phình to và tạo coupling.

CQRS đặt ranh giới rõ hơn:

~~~text
Command side                         Query side
------------                         ----------
CreateOrder                          SearchOrders
CancelOrder                          GetOrderSummary
CapturePayment                       GetRevenueByDay
ReserveInventory                     ListAvailableStock
Validate invariants                  Optimize read shape
Update write state                   Serve read models
~~~

Command và Query không chỉ là hai endpoint khác nhau. Chúng có **mục đích, mô hình dữ liệu và quy tắc xử lý khác nhau**.

## 3. CQRS là gì?

CQRS tách mô hình thực thi lệnh (command model) khỏi mô hình phục vụ truy vấn (query model).

### 3.1. Command

Command biểu đạt một ý định thay đổi trạng thái:

~~~json
{
  "commandId": "cmd-1042",
  "type": "CancelOrder",
  "orderId": "ord-9001",
  "reason": "CUSTOMER_REQUEST",
  "expectedVersion": 7
}
~~~

Command thường có mục tiêu nghiệp vụ rõ; có thể bị từ chối vì invariant hoặc trạng thái hiện tại; có thể cần authorization và optimistic concurrency; khi thành công tạo thay đổi trạng thái và có thể phát domain event. Command chưa phải sự kiện đã xảy ra.

Ví dụ `CancelOrder` là yêu cầu. Chỉ sau khi domain xác nhận đơn có thể hủy, hệ thống mới phát `OrderCancelled`.

### 3.2. Query

Query yêu cầu dữ liệu, không làm thay đổi domain state:

~~~json
{
  "type": "SearchOrders",
  "customerId": "customer-17",
  "status": ["PAID", "FULFILLING"],
  "page": 1,
  "pageSize": 20
}
~~~

Query có thể đọc từ projection, dùng denormalized documents, trả dữ liệu tổng hợp, cache hoặc search index, và tối ưu riêng cho latency/pagination/filtering. Query có thể ghi cache metrics nhưng không được thay đổi sự thật nghiệp vụ.

### 3.3. CQRS không đồng nghĩa microservices

Có thể áp dụng CQRS trong một monolith:

~~~text
Application
  ├─ Command handlers
  ├─ Domain model
  ├─ Query handlers
  └─ One relational database
~~~

Hoặc tách thành nhiều deployment:

~~~text
Command API -> Write model -> Database
Query API   -> Read model  -> Search/SQL/Cache
~~~

Tách deployment làm tăng network, consistency và vận hành. Không cần tạo hai service riêng chỉ để nói rằng hệ thống dùng CQRS.

## 4. Write model bảo vệ invariant

Write model phải bảo vệ quy tắc quan trọng của domain. Với Order:

- Không thanh toán một đơn đã hủy.
- Không hoàn tất đơn nếu chưa giữ được hàng.
- Không hủy sau khi đã giao, trừ quy trình return riêng.
- Không đổi currency sau khi đã capture tiền.
- Không áp cùng một logical payment capture hai lần.

Các quy tắc này phải nằm trong domain model/transaction boundary có thẩm quyền, không phụ thuộc read model có thể trễ.

Ví dụ pseudocode:

~~~java
public Order cancel(CancelReason reason, long expectedVersion) {
    if (version != expectedVersion) {
        throw new ConcurrentModificationException();
    }
    if (status == OrderStatus.SHIPPED ||
        status == OrderStatus.CANCELLED) {
        throw new InvalidOrderTransitionException(status);
    }

    status = OrderStatus.CANCELLED;
    version++;
    return this;
}
~~~

Đây là minh họa. Production cần xác định transaction, authorization, idempotency key, audit và side effects. Read model hiển thị nút Cancel không bảo đảm command sẽ thành công; write model vẫn phải kiểm tra trạng thái thực.

## 5. Read model tối ưu cho từng cách đọc

Một Order domain model có thể được chuẩn hóa thành orders, order_items, payments, shipments, customers và addresses. Nhưng màn hình lịch sử đơn có thể cần một document tổng hợp:

~~~json
{
  "orderId": "ord-9001",
  "customerName": "Example Customer",
  "createdAt": "2026-11-12T09:30:00Z",
  "status": "FULFILLING",
  "total": {
    "amountMinor": 1250000,
    "currency": "VND"
  },
  "itemCount": 3,
  "paymentStatus": "CAPTURED",
  "shipmentStatus": "PACKING"
}
~~~

Read model có thể nằm ở PostgreSQL view, Elasticsearch/OpenSearch, Redis, document database hoặc warehouse. Một domain có thể có nhiều projections: customer order history, operations dashboard, finance daily revenue, search index và inventory availability.

Mỗi projection cần owner, schema, rebuild strategy và freshness target. Không cố tạo một read model duy nhất cho mọi truy vấn.

### 5.1. Denormalization có nghĩa vụ cập nhật

Read model có thể lặp customer display name hoặc payment status để query nhanh. Khi nguồn thay đổi, projection phải được cập nhật. Cần xác định event nào cập nhật field, event đến trễ xử lý ra sao, có giữ historical value tại thời điểm order không, nguồn rebuild là gì và độ stale chấp nhận được.

## 6. Luồng CQRS cơ bản

~~~mermaid
flowchart LR
    U[Client] --> C[Command API]
    C --> H[Command Handler]
    H --> D[Domain Model]
    D --> W[(Write Store)]
    W --> E[Outbox / Domain Events]
    E --> P[Projection Handler]
    P --> R[(Read Store)]
    U --> Q[Query API]
    Q --> R
~~~

Trình tự:

1. Client gửi command.
2. Command handler xác thực và gọi domain logic.
3. Write store commit trạng thái.
4. Sự kiện được phát sau commit theo cơ chế đáng tin cậy.
5. Projection handler cập nhật read store.
6. Query API đọc từ read store.

Bước phát sự kiện và cập nhật projection có thể bất đồng bộ. Response của command không nhất thiết đồng nghĩa read model đã cập nhật.

### 6.1. CQRS với cùng database

~~~text
Command handler -> normalized write tables
Query handler   -> read-optimized views/materialized views
~~~

Đây là CQRS hợp lệ nếu command/query models tách biệt về trách nhiệm. Nó giảm consistency overhead so với hai datastore, nhưng vẫn có thể gặp locking, view refresh và workload contention.

### 6.2. CQRS với hai datastore

Khi read workload khác write workload rõ rệt, có thể dùng write store cho transaction/constraints/aggregate state và read store cho search/denormalized documents/reporting. Event/outbox truyền thay đổi, projection consumer đồng bộ read model.

Lợi ích là tối ưu độc lập; chi phí là eventual consistency, duplicated data, replay và operational burden.

## 7. Eventual consistency và trải nghiệm người dùng

Nếu command commit lúc 10:00:00 nhưng projection xử lý lúc 10:00:02, query trong hai giây đó có thể trả dữ liệu cũ.

Đây là **eventual consistency**: nếu không còn cập nhật mới và pipeline hoạt động bình thường, read model cuối cùng sẽ hội tụ theo nguồn. Không phải use case nào cũng chấp nhận cùng độ trễ.

| Use case | Consistency thường cần |
|---|---|
| Dashboard doanh thu | Vài giây/phút có thể chấp nhận |
| Search sản phẩm | Propagation delay nhỏ có thể chấp nhận |
| Xem đơn ngay sau khi tạo | Read-your-writes hoặc command response |
| Kiểm tra số dư để cho phép thanh toán | Nguồn authoritative |
| Tồn kho để tránh oversell | Command kiểm tra nguồn có thẩm quyền |
| Analytics theo ngày | Eventual với watermark |
| Trạng thái fraud/risk | Theo chính sách và độ trễ rủi ro |

### 7.1. Read-your-writes

Sau khi tạo đơn, người dùng mong thấy đơn vừa tạo. Có thể trả summary từ command response, query write store cho request tiếp theo, đưa version/position vào response và đợi projection đạt mốc đó, dùng session affinity/read-your-writes token, hoặc hiển thị trạng thái “đang đồng bộ” có thời hạn.

Không ép mọi query đọc write database vì sẽ làm mất lợi ích read scaling và tạo coupling.

### 7.2. Projection lag phải được đo

Theo dõi source event position, last applied position, oldest unapplied event age, processing errors, thời gian từ command commit tới read visibility, backlog/throughput và rebuild progress. Khi query trả dữ liệu cũ, phân biệt lag bình thường, consumer lỗi, event quarantine và source event bị mất.

## 8. CQRS không bắt buộc Event Sourcing

Có thể lưu write state trong relational database và phát event qua outbox:

~~~text
Command
  -> SQL transaction updates orders
  -> insert outbox row
  -> commit
  -> publisher sends OrderUpdated
  -> read projector updates search document
~~~

Write database vẫn là nguồn sự thật. Event chỉ thông báo thay đổi để đồng bộ projections. Mô hình này mang lại nhiều lợi ích CQRS mà không cần quản lý event store làm primary database. Nó phù hợp khi cần nhiều read models nhưng không cần tái dựng mọi trạng thái lịch sử từ đầu.

## 9. Event Sourcing là gì?

Event Sourcing lưu **chuỗi sự kiện đã xảy ra** làm nguồn sự thật cho aggregate. Trạng thái hiện tại được tính bằng cách áp sự kiện theo thứ tự hợp lệ.

~~~text
OrderCreated
ItemAdded
PaymentAuthorized
InventoryReserved
OrderCompleted
~~~

Thay vì chỉ lưu row hiện tại:

~~~json
{
  "orderId": "ord-9001",
  "status": "COMPLETED",
  "totalMinor": 1250000
}
~~~

event-sourced model lưu history có nghĩa nghiệp vụ:

~~~json
[
  {"type": "OrderCreated", "sequence": 1, "items": 3},
  {"type": "PaymentAuthorized", "sequence": 2, "paymentIntent": "pay-100"},
  {"type": "InventoryReserved", "sequence": 3, "reservation": "res-77"},
  {"type": "OrderCompleted", "sequence": 4}
]
~~~

Đây là ví dụ giản lược; event thật cần metadata, version, identity và payload theo domain.

### 9.1. Event mô tả sự thật

Phân biệt:

- Command: `CapturePayment` — yêu cầu capture tiền.
- Event: `PaymentCaptured` — xác nhận tiền đã được capture.
- Query: `GetPaymentStatus` — hỏi trạng thái.
- Projection: Payment Summary — cách nhìn được tính từ dữ liệu.

Event nên được phát khi điều được mô tả đã thực sự xảy ra theo contract. Không đặt tên một command chưa được xác nhận thành event thành công.

### 9.2. Event bất biến

Thông thường event lịch sử không bị sửa trực tiếp. Nếu cần sửa nghiệp vụ, ghi correction/compensation event có provenance. Điều này giúp giữ audit và khả năng giải thích trạng thái qua thời gian.

Bất biến không có nghĩa giữ PII vô hạn. Retention, deletion, encryption và crypto-erasure cần được thiết kế cùng event store.

## 10. Event Store khác Message Broker

| Thành phần | Vai trò | Khả năng thường cần |
|---|---|---|
| Event Store | Lưu stream lịch sử theo aggregate | Append, read stream, version/concurrency, snapshots |
| Message Broker | Phân phối messages tới consumers | Topics/queues, partitions, consumer groups, retention |
| Transactional Outbox | Ghi event cùng transaction DB | Bảo đảm state và publication không tách rời |
| Audit Log | Ghi hoạt động/actor để kiểm toán | Integrity, access control, retention |
| CDC Log | Phản ánh thay đổi transaction DB | LSN/offset, schema mapping, snapshot |

Kafka topic retention 7 ngày không tự động là event store lưu lịch sử nghiệp vụ 7 năm. Compaction có thể giữ latest record theo key nhưng mất transitions trước. Event store chuyên dụng có thể hỗ trợ đọc stream và optimistic concurrency theo aggregate.

Nếu dùng broker làm event history, phải xác minh retention, compaction, ordering, archive, replay semantics, schema compatibility và backup/restore.

## 11. Aggregate stream và consistency boundary

Trong Event Sourcing, aggregate thường là đơn vị có invariant và stream riêng.

~~~text
orders/ord-9001:
  version 1 OrderCreated
  version 2 ItemAdded
  version 3 PaymentAuthorized
  version 4 InventoryReserved
  version 5 OrderCompleted
~~~

Command load stream hoặc snapshot + events, dựng state, kiểm tra invariant, rồi append event mới với expected version.

### 11.1. Aggregate không nên quá lớn

Aggregate quá lớn khiến mọi thay đổi phải tuần tự hóa trên cùng stream, tạo contention. Aggregate quá nhỏ làm invariant cần kiểm qua nhiều streams, khó đảm bảo transaction nhất quán. Chọn boundary theo consistency requirement và ownership; không biến Order, Customer, Payment, Inventory thành một aggregate chỉ vì chúng liên quan trong checkout.

### 11.2. Cross-aggregate workflows

Checkout gồm Order, Payment, Inventory. Thường không có transaction event-store toàn cục bao trùm tất cả. Có thể dùng saga/process manager:

~~~mermaid
flowchart TD
    A[OrderCreated] --> B[Request Payment Authorization]
    B --> C{Payment authorized?}
    C -->|Yes| D[Request Inventory Reservation]
    C -->|No| E[OrderPaymentFailed]
    D --> F{Inventory reserved?}
    F -->|Yes| G[OrderReady]
    F -->|No| H[Request Payment Void]
    H --> I[OrderCompensated]
~~~

Mỗi domain sở hữu stream của mình. Process manager theo dõi correlation và phát command tới bước tiếp theo. Compensation là hành động nghiệp vụ mới, không xóa event cũ.

## 12. Concurrency và optimistic locking

Hai command có thể cùng load aggregate version 10 rồi cùng muốn append version 11. Chỉ một command nên thành công.

~~~text
append(
  stream = "orders/ord-9001",
  expectedVersion = 10,
  events = [OrderCancelled]
)
~~~

Nếu stream đã lên version 11, store từ chối append; command handler phải reload và quyết định lại.

### 12.1. Không tự động retry mọi conflict

Conflict có thể là cạnh tranh vô hại hoặc hai ý định không thể cùng đúng. Ví dụ CancelOrder và CompleteOrder đến gần nhau. Retry mù có thể làm một lệnh thành công trên state không còn hợp lệ. Phải chạy lại domain validation.

### 12.2. Idempotent commands

Client có thể gửi lại command vì timeout dù server đã commit. Dùng idempotency key/command ID và lưu kết quả theo contract. Event ID de-dup là lớp khác; logical payment operation cần business identity riêng.

## 13. Transactional Outbox khi chưa dùng Event Sourcing

Nếu write store là relational DB, rủi ro phổ biến là dual write:

~~~text
1. UPDATE orders
2. PUBLISH OrderUpdated to broker
~~~

Nếu DB commit thành công nhưng publish thất bại, projection không cập nhật. Nếu publish thành công nhưng DB rollback, consumer nhận event không có trạng thái tương ứng.

Transactional outbox ghi domain row và outbox row trong cùng DB transaction:

~~~sql
BEGIN;

UPDATE orders
SET status = 'PAID', version = version + 1
WHERE order_id = :orderId;

INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, payload
) VALUES (
    :eventId, :orderId, 'OrderPaid', :payload
);

COMMIT;
~~~

Publisher đọc outbox và gửi broker; sau đó đánh dấu đã publish hoặc quản lý offset. Publisher có thể gửi lặp nếu crash giữa publish và mark-sent, nên consumers vẫn phải idempotent.

Outbox cho phép event-driven projections mà không cần chuyển toàn bộ domain sang Event Sourcing.

## 14. Projector và read models

Projector tiêu thụ event rồi cập nhật một mô hình đọc:

~~~text
OrderCreated
OrderPaid
OrderShipped
     |
     v
OrderHistoryProjector
     |
     v
customer_order_history
~~~

Một domain có thể có nhiều projectors độc lập: Search, Customer History, Revenue Aggregation, Operations Dashboard và Notification Preferences.

Mỗi projection cần owner, mục đích, event types/schema versions hỗ trợ, idempotency/ordering behavior, checkpoint/offset, rebuild strategy, freshness SLO, deletion policy, validation và monitoring.

### 14.1. Projection không phải nguồn sự thật

Nếu search index báo đơn PAID nhưng Payment domain xác nhận FAILED, xử lý discrepancy theo nguồn authoritative. Không sửa payment bằng cách cập nhật document search. Projection có thể rebuild; domain state cần quy trình correction chính thức.

### 14.2. Nhiều projections có thể khác nhau

Finance projection tính net revenue; operations projection tính orders awaiting fulfillment; customer projection ẩn thông tin nội bộ. Chúng có schema, latency và quyền truy cập khác nhau. Không cố tạo một bảng universal read model.

## 15. Replay và snapshot

Một lợi ích của Event Sourcing là dựng lại state/projection từ event history. Replay cần:

- Event history đầy đủ và có integrity.
- Schema cũ có thể decode/upcast.
- Reducer có tính xác định.
- Duplicate events được xử lý.
- Ordering/sequence được kiểm.
- Không gọi lại side effects như charge tiền/gửi email.
- Target rebuild được tách biệt.
- Checkpoints cho phép resume.
- Validation trước cutover.

### 15.1. Snapshot

Nếu aggregate có hàng triệu events, snapshot lưu state tại một version:

~~~text
Snapshot at aggregate version 10,000
  + events 10,001 ... 10,250
  = current aggregate state
~~~

Snapshot là cache của phép tính, không thay event history làm nguồn sự thật. Nếu snapshot hỏng hoặc projector đổi semantics, có thể cần rebuild từ history hoặc snapshot khác đã xác minh.

### 15.2. Replay projection mới

Có thể chạy projector v2 vào shadow read store, đọc event history, catch up tới high watermark, validate và đổi read pointer. Đường replay cần consumer group/job riêng, quota và quyền hạn chế; không reset offsets của live consumer đang thực hiện side effects.

## 16. Schema evolution và upcasting

Event sống lâu hơn một phiên bản code:

- `OrderCreated v1` có customer ID và items.
- v2 thêm currency.
- v3 thêm tax breakdown và shipping method.

Projector mới cần đọc được các phiên bản cũ:

~~~text
Stored Event v1/v2/v3
       |
       v
Version-specific deserializer
       |
       v
Upcaster to canonical event
       |
       v
Projection reducer
~~~

Java pseudocode:

~~~java
CanonicalOrderCreated normalize(EventEnvelope event) {
    return switch (event.version()) {
        case 1 -> upcastV1(event.payload());
        case 2 -> upcastV2(event.payload());
        case 3 -> decodeV3(event.payload());
        default -> throw new UnsupportedEventVersionException(event.version());
    };
}
~~~

Nếu v1 thiếu currency và không có historical source đáng tin, không gán currency hiện tại. Đánh dấu không thể tái tính chính xác hoặc dùng nguồn tham chiếu có provenance.

### 16.1. Upcast khác sửa event gốc

Upcaster chuyển đổi khi đọc, giữ nguyên history gốc. Correction event biểu diễn sự thật sửa đổi có audit. Sửa trực tiếp event lịch sử có thể phá integrity, signature và audit trail; chỉ thực hiện event-store migration khi có kế hoạch và bằng chứng đầy đủ.

## 17. CQRS/Event Sourcing trong nhiều services

Microservices có thể dùng event-driven communication mà không cần Event Sourcing. Ví dụ Order dùng SQL và outbox, phát OrderCreated; Payment dùng SQL, nhận command và phát PaymentAuthorized.

Nếu một domain dùng Event Sourcing, các service khác vẫn có thể consume integration events và duy trì DB riêng. Không nên chia sẻ event store giữa mọi services; mỗi domain giữ ownership và invariant của mình.

### 17.1. Domain event và integration event

- **Domain event:** sự thật bên trong domain, có thể chứa chi tiết cần cho domain model.
- **Integration event:** contract công bố cho hệ thống khác, ổn định và có chủ đích.
- **Event store record:** bản ghi lịch sử để tái dựng aggregate.
- **Broker message:** bản tin phân phối, có thể retry/duplicate/expire.

Không phát mọi internal event ra ngoài. Contract công khai cần kiểm soát PII, schema evolution, versioning và compatibility.

### 17.2. Chuyển đổi contract

Integration event có thể được map từ domain event qua publisher/anti-corruption layer. Điều này tránh để consumer phụ thuộc cấu trúc nội bộ aggregate. Nếu domain model đổi, integration contract vẫn có thể giữ ổn định.

## 18. Khi nào nên dùng CQRS?

CQRS hữu ích khi read workload khác rõ write workload, nhiều màn hình/report cần data shapes khác nhau, read scaling cần độc lập, query joins phức tạp có thể materialize trước, hoặc write model cần bảo vệ invariant chặt còn read model cần tối ưu UX.

Không cần CQRS chỉ vì ứng dụng có GET và POST endpoint; mọi ứng dụng đều có đọc và ghi. Cũng không cần read database riêng nếu SQL queries và indexes đã đáp ứng.

## 19. Khi nào nên dùng Event Sourcing?

Event Sourcing có thể phù hợp khi:

- Lịch sử nghiệp vụ là một phần quan trọng của sản phẩm/audit.
- Cần giải thích tại sao state hiện tại được tạo ra.
- Nhiều projections cần cùng historical stream.
- Có nhu cầu replay/backfill/rebuild thường xuyên.
- Domain transitions có ý nghĩa và event model ổn định.
- Team đủ năng lực vận hành event store, schema evolution và replay.

Không nên dùng chỉ vì muốn có audit log. Database audit trail, append-only ledger hoặc CDC có thể đáp ứng với độ phức tạp thấp hơn.

### 19.1. Tín hiệu không phù hợp

- Domain đơn giản, CRUD đủ dùng.
- Lịch sử không cần lưu hoặc có thể lưu audit riêng.
- Team chưa có năng lực xử lý event schema/ordering/replay.
- Data deletion/retention khó tương thích với event history.
- Transaction xuyên nhiều aggregate cần consistency mạnh mà thiết kế chưa giải quyết.
- RTO không cho phép rebuild và chưa có snapshot/backup phù hợp.
- Lợi ích kinh doanh chưa bù chi phí vận hành.

## 20. Ma trận lựa chọn

| Nhu cầu | CRUD truyền thống | CQRS | Event Sourcing | Kết hợp CQRS + ES |
|---|---|---|---|---|
| CRUD đơn giản | Rất phù hợp | Có thể dư thừa | Thường dư thừa | Dư thừa |
| Nhiều read shapes | Có thể cần joins/views | Phù hợp | Không bắt buộc | Phù hợp |
| Read/write scale khác nhau | Có thể tách bằng replica | Phù hợp | Không tự giải quyết | Phù hợp |
| Lịch sử nghiệp vụ đầy đủ | Audit bổ sung | Không tự có | Phù hợp | Phù hợp |
| Replay projections | Từ DB/CDC/outbox | Có thể | Phù hợp nếu history đủ | Phù hợp |
| Strong transaction invariants | RDBMS phù hợp | Write side giữ invariant | Aggregate stream concurrency | Cần thiết kế aggregate |
| Nhiều projections | CDC/outbox | Phù hợp | Rất phù hợp | Rất phù hợp |
| Vận hành đơn giản | Thường tốt nhất | Phức tạp hơn | Phức tạp hơn | Cao nhất |
| Audit/explainability | Audit log riêng | Không tự có | Lịch sử sự kiện | Lịch sử + read models |

Bảng là hướng dẫn, không phải công thức. Một hệ thống có thể dùng CRUD cho Catalog, CQRS cho Search và Event Sourcing cho Ledger mà vẫn hợp lý.

## 21. Thiết kế API và command handling

Một command endpoint có thể là:

~~~http
POST /orders/ord-9001/cancel
Idempotency-Key: cancel-ord-9001-2026-11-12

{
  "reason": "CUSTOMER_REQUEST",
  "expectedVersion": 7
}
~~~

Response:

~~~http
202 Accepted

{
  "commandId": "cmd-1042",
  "orderId": "ord-9001",
  "accepted": true,
  "resultVersion": 8,
  "status": "CANCEL_REQUESTED"
}
~~~

202 Accepted có nghĩa yêu cầu được chấp nhận xử lý theo contract; không mặc định mọi side effects đã hoàn tất. Nếu command xử lý đồng bộ và transaction đã commit, có thể trả trạng thái rõ hơn. API phải mô tả idempotency, error mapping và consistency expectations.

### 21.1. Query API

~~~http
GET /customers/customer-17/orders?status=PAID&page=1&pageSize=20
~~~

Nếu projection trễ, response có thể chứa watermark/version hoặc freshness metadata khi sản phẩm cần. Không tiết lộ internal offsets nếu không có ích cho client.

### 21.2. Command validation ở server

Read model có thể hiển thị một action nhưng không phải authorization source. Command handler vẫn phải kiểm tenant, permissions, current state, limits và business rules. Không tin client đã đọc trạng thái hợp lệ vài giây trước.

## 22. Event identity, ordering và idempotency

Một event envelope nên có metadata:

~~~json
{
  "eventId": "evt-1042",
  "aggregateType": "Order",
  "aggregateId": "ord-9001",
  "aggregateVersion": 8,
  "eventType": "OrderCancelled",
  "eventVersion": 2,
  "occurredAt": "2026-11-12T09:45:00Z",
  "correlationId": "checkout-9001",
  "causationId": "cmd-1042",
  "payload": {
    "reason": "CUSTOMER_REQUEST"
  }
}
~~~

Các trường giúp nhận diện event, aggregate, version, schema và chuỗi nhân quả. Không dựa timestamp để đảm bảo thứ tự vì clock skew và event đến trễ.

### 22.1. Idempotent projector

Projector phải có thể nhận lại event mà không tạo state sai. Dùng processed-event inbox với unique event ID, version guard hoặc upsert theo aggregate sequence.

Với projection cộng dồn (doanh thu), duplicate phải được xử lý trước khi cộng. Với projection latest-state, sequence guard ngăn event cũ ghi đè mới. Event ID de-dup không thay thế business uniqueness như PSP transaction ID.

### 22.2. Poison events

Event không decode hoặc vi phạm invariant cần quarantine, retry có giới hạn hoặc dừng partition theo policy. Không bỏ qua âm thầm rồi vẫn báo projection healthy. Lưu reason, event identity và cách xử lý có audit, nhưng bảo vệ payload nhạy cảm.

## 23. Tách Event Sourcing khỏi external side effects

Replay `PaymentCaptured` để cập nhật báo cáo là hợp lý. Replay command capture tiền có thể thu tiền lần nữa.

~~~text
Live command:
  validate
  -> domain decision
  -> external side effect if authorized
  -> append/persist outcome event

Projection:
  read historical event
  -> pure reducer
  -> update derived view
  -> checkpoint
  -> no outbound command
~~~

Dùng workload identity riêng cho replay, không cấp PSP/email/shipping credentials, giới hạn network egress và không subscribe vào command topics. Đừng chỉ dựa vào một cờ chế độ replay trong handler có side effects.

## 24. Transaction boundary và saga

Event Sourcing không tạo transaction toàn cục miễn phí. Nếu Order stream append thành công nhưng Payment stream thất bại, cần workflow quản lý trạng thái chưa hoàn tất.

Saga/process manager có thể theo dõi correlation ID, gửi command tiếp theo khi event phù hợp đến, lưu process state/checkpoint, retry có giới hạn, phát compensation, hỗ trợ timeout và manual intervention.

Ví dụ payment đã capture nhưng inventory reservation thất bại. Hệ thống có thể yêu cầu refund/void theo trạng thái provider. Refund là hành động mới có thể thất bại; phải theo dõi tới terminal outcome và đối soát ledger. Compensation không xóa side effect cũ.

## 25. Snapshot và event retention

Event stream dài có thể làm aggregate load chậm. Snapshot lưu state tại version N, rồi load event sau N.

Cần xác minh snapshot có checksum/schema/projector version, tương thích reducer hiện tại, cutoff là last-applied hay next-to-read, event history sau cutoff còn đầy đủ, backup snapshot độc lập đã thử restore, deletion/correction events được áp và có thể fallback replay từ history nếu snapshot lỗi.

Retention là quyết định domain, legal và privacy. Không giữ raw personal data vô hạn chỉ vì Event Sourcing thuận tiện. Cần data minimization, encryption, deletion/tombstone hoặc crypto-erasure phù hợp; replay phải không hồi sinh dữ liệu đã xóa hợp lệ.

## 26. Operational complexity và observability

CQRS/ES tăng số thành phần cần giám sát:

| Thành phần | Metric/health cần theo dõi |
|---|---|
| Command API | latency, rejection, validation failures |
| Event store | append/read latency, storage, backup |
| Event publisher | outbox age, publish failures, duplicates |
| Broker | lag, partition skew, retention, disk |
| Projector | processing rate, errors, checkpoint age |
| Read store | write errors, query latency, stale data |
| Snapshot job | duration, coverage, checksum, failures |
| Saga/process manager | stuck workflows, retries, compensation age |
| Schema registry/upcasters | decode failures, unsupported versions |

Một hệ thống có command API xanh nhưng projection lag hàng giờ vẫn có thể làm sản phẩm sai. SLO nên tách write availability, read freshness và workflow completion.

### 26.1. Alert theo business impact

- Order đã thanh toán nhưng read model không cập nhật trong SLA.
- Projection lag khiến customer portal hiển thị sai trạng thái.
- Event store không append được và command path mất khả năng ghi.
- Saga stuck ở payment/inventory compensation.
- Event schema mới không được consumer hỗ trợ.
- Replay không đạt catch-up ETA hoặc có quarantine events.

CPU/broker lag là bằng chứng chẩn đoán; alert nên nêu capability và tác động.

## 27. Disaster recovery và rebuild

CQRS read models thường có thể dựng lại từ write source/events nếu history đầy đủ. Cần phân biệt event store là domain source of truth, broker chỉ giữ một phần history, outbox có thể đã được dọn, read database có backup riêng, projection có thể chứa bug trong logic cũ và archive/snapshot có thể không restore được.

Runbook rebuild:

1. Xác định source authoritative và khoảng lịch sử.
2. Xác minh retention/archive/snapshot.
3. Tạo shadow target.
4. Chạy projector version được kiểm soát, idempotent.
5. Theo dõi checkpoints, lag và quarantine.
6. Catch up live events.
7. Reconcile counts, state, financial invariants và privacy deletion.
8. Cutover read pointer.
9. Giữ rollback target và giám sát sau chuyển đổi.

Không reset live consumer offsets hoặc chạy lại handler có side effects để rebuild read model.

## 28. Bảo mật và quyền riêng tư

Event history có thể chứa nhiều dữ liệu nhạy cảm hơn read model hiện tại. Kiểm soát cần có:

- Access control theo domain/stream và purpose.
- Encryption at rest/in transit.
- Không đưa secrets, tokens hoặc payment card data vào event.
- PII minimization/tokenization.
- Retention/deletion policy áp dụng cho archive, snapshot và projection.
- Audit truy cập và replay production.
- Workload identity riêng cho projector/replay.
- Tenant isolation khi đọc stream và dựng projection.
- Data residency khi replicate cross-region.
- Bảo vệ event schema và signing keys.

Một read model có thể che field nhạy cảm trong khi event stream vẫn chứa chúng. Quyền truy cập event store cần được đánh giá riêng, không kế thừa tự động từ quyền đọc API.

## 29. CQRS mà không Event Sourcing

Ví dụ Order dùng PostgreSQL làm nguồn sự thật:

1. Command handler validate và update orders.
2. Cùng transaction ghi outbox event.
3. Publisher phát integration events.
4. Search projector tạo index.
5. Finance projector tổng hợp doanh thu.
6. Customer projector tạo lịch sử đơn.
7. Query APIs đọc projections phù hợp.
8. Nếu event history retention không đủ, dùng DB backup/CDC để rebuild latest-state views.

Lợi ích: write model đơn giản, transaction SQL/constraints, read models độc lập, không cần giữ event history vô hạn. Hạn chế: không thể tự dựng mọi lịch sử từ outbox ngắn hạn; cần archive nếu reporting cần lịch sử lâu dài.

Đây thường là bước phù hợp khi nhu cầu chính là query optimization và nhiều read models.

## 30. Event Sourcing với CQRS đơn giản

Một domain ledger có thể lưu stream sự kiện làm nguồn sự thật và có một API đọc aggregate state bằng snapshot + events. Có thể chưa cần nhiều read databases hay query services riêng.

Lợi ích là lịch sử và khả năng giải thích state. Chi phí vẫn gồm event schema evolution, concurrency, snapshots, replay, retention và operational tooling. Không cần dựng CQRS phân tán nếu read needs còn đơn giản.

## 31. Khi nào kết hợp cả hai?

Kết hợp có giá trị khi domain có lịch sử nghiệp vụ quan trọng, nhiều read models cần cùng history, cần replay/backfill/rebuild, read traffic khác write traffic rõ, team đủ năng lực vận hành event store và event contract có semantics ổn định.

~~~mermaid
flowchart LR
    C[Commands] --> H[Aggregate Handler]
    H --> E[(Event Store)]
    E --> P1[Search Projector]
    E --> P2[Customer History Projector]
    E --> P3[Finance Projector]
    P1 --> R1[(Search Index)]
    P2 --> R2[(Customer Read DB)]
    P3 --> R3[(Analytics Store)]
    Q1[Search Query] --> R1
    Q2[Customer Query] --> R2
    Q3[Finance Query] --> R3
~~~

Mỗi projection có lifecycle độc lập; event store giữ nguồn lịch sử. Các projectors cần version, checkpoints và replay policy.

## 32. Migration từng phần, không rewrite toàn bộ

### Giai đoạn 1 — Tách query handlers

Giữ một DB, tách command/query code và định nghĩa query-specific DTO. Đo query latency và coupling.

### Giai đoạn 2 — Tạo read projection

Dùng SQL views/materialized views hoặc bảng đọc riêng. Xác định owner, refresh và consistency behavior.

### Giai đoạn 3 — Thêm outbox

Ghi event cùng transaction domain DB. Dùng publisher và consumers idempotent. Đây là bước tạo event-driven integration mà chưa chuyển sang Event Sourcing.

### Giai đoạn 4 — Tách datastore nếu cần

Đưa search/reporting/read models sang datastore phù hợp. Thêm lag monitoring và read-your-writes path cho use case cần.

### Giai đoạn 5 — Thử Event Sourcing ở domain có lợi ích rõ

Chọn ledger hoặc workflow cần lịch sử đầy đủ. Thiết kế aggregate stream, event contracts, snapshots, upcasters, replay và DR trước khi đưa production.

### Giai đoạn 6 — Mở rộng theo bằng chứng

Chỉ mở rộng nếu giảm coupling hoặc đáp ứng requirement đã đo. Giữ CRUD cho domain không hưởng lợi.

## 33. Case study: Order Service dùng CQRS không Event Sourcing

### Bối cảnh

Order Service dùng PostgreSQL, dashboard và search query ngày càng nặng. Nhiều consumers cần order updates nhưng domain chỉ cần trạng thái hiện tại và audit cơ bản.

### Thiết kế

- Giữ orders và order_items làm write model.
- Command handlers enforce state transitions.
- Transaction ghi outbox.
- Publisher phát integration events.
- Search projector tạo document.
- Finance projector tổng hợp doanh thu.
- Customer projector tạo lịch sử đơn.
- Query APIs đọc projections phù hợp.
- Nếu event history retention không đủ, dùng DB backup/CDC để rebuild latest-state views.

### Trade-off

Đạt read scaling và query-specific models mà không cần event store primary. Nhưng không thể tự dựng mọi lịch sử từ outbox ngắn hạn; cần archive nếu reporting yêu cầu lịch sử lâu dài.

## 34. Case study: Payment Ledger dùng Event Sourcing

### Bối cảnh

Payment cần biết mọi transition, authorization, capture, void, refund, chargeback và correction. Audit và đối soát là yêu cầu quan trọng.

### Thiết kế

- Payment intent là aggregate có stream.
- Commands validate idempotency/business identity.
- Event store append với expected version.
- External PSP calls được điều phối bằng process manager, lưu outcome event sau khi xác nhận.
- Finance projection tính ledger views.
- Operations projection hiển thị pending/unknown outcomes.
- Reconciliation so event history với PSP settlement.
- Snapshot giảm thời gian load aggregate.
- Replay projectors không gọi lại PSP.

### Rủi ro

Timeout PSP có thể tạo unknown outcome; không suy rằng chưa charge. Event history giúp truy vết, nhưng không thay provider reconciliation và ledger controls. Refund là hành động mới cần command riêng, không phải xóa capture event.

## 35. Những lỗi thường gặp

1. Nghĩ CQRS và Event Sourcing là một kỹ thuật duy nhất.
2. Tách read/write databases dù chưa có nhu cầu.
3. Gọi mọi HTTP GET/POST là CQRS.
4. Dùng event bus ngắn retention như event store dài hạn.
5. Đưa commands và events vào cùng semantics/topic mà không phân biệt.
6. Cho query model quyết định invariant tài chính.
7. Không có read-your-writes và khiến user thấy trạng thái cũ.
8. Không đo projection lag.
9. Projector không idempotent, redelivery làm sai dữ liệu.
10. Dựa timestamp để sắp thứ tự aggregate.
11. Aggregate quá lớn gây contention.
12. Aggregate quá nhỏ làm invariant xuyên stream khó bảo vệ.
13. Dùng Event Sourcing chỉ để có audit log.
14. Sửa historical events tại chỗ không có provenance.
15. Không có upcasters cho event schema cũ.
16. Replay kích hoạt lại payment/email/shipping side effects.
17. Không có snapshot/checkpoint và RTO không đạt.
18. Coi eventual consistency là chấp nhận được cho mọi use case.
19. Một projection duy nhất phục vụ tất cả queries.
20. Không có owner hoặc rebuild strategy cho read model.
21. Dùng Event Sourcing nhưng không có event-store backup/restore.
22. Bỏ qua privacy deletion và làm sống lại PII.
23. Không phân biệt domain event và integration event.
24. Tạo saga không có timeout, compensation hoặc manual recovery.
25. Tự động retry conflict mà không chạy lại domain validation.
26. Chỉ test happy path, bỏ duplicate/out-of-order/crash cases.
27. Tách microservices để “đúng kiến trúc” dù tăng vận hành vô ích.
28. Không có cách đối soát projection với nguồn authoritative.

## 36. Bài tập thực hành

### Bài A — Chọn mô hình

Catalog có CRUD đơn giản, Search cần filter nhiều chiều, Finance cần lịch sử mọi lần thay đổi giá. Chọn mô hình cho từng capability: CRUD, CQRS, Event Sourcing hoặc kết hợp. Nêu source of truth và retention.

### Bài B — Read-your-writes

Client tạo Order thành công nhưng Customer History projection mất 3 giây mới cập nhật. Thiết kế response/consistency token hoặc query path để user thấy đơn ngay mà không buộc mọi read vào write DB.

### Bài C — Outbox dual-write

Service update SQL thành công nhưng broker publish thất bại. Thiết kế outbox transaction, publisher retry và consumer idempotency. Mô tả crash window sau publish trước mark-sent.

### Bài D — Event sequence conflict

Hai command cùng load Order version 10; một command Cancel, một Complete. Thiết kế expected-version append và xử lý conflict sao cho không có trạng thái terminal sai.

### Bài E — Replay an toàn

Rebuild Search index từ lịch sử 200 triệu events. Thiết kế shadow index, snapshot/cutoff, consumer group, throttle, checkpoints, upcasters, delete events, validation và alias cutover. Nêu cách ngăn email/payment side effects.

### Bài F — Payment unknown outcome

PSP đã nhận capture nhưng response timeout; Payment Service chưa biết kết quả. Nêu command/event states, reconciliation và lý do không được retry capture mù. Phân biệt event history với PSP ledger.

### Bài G — Event schema evolution

OrderCreated v1 không có currency; v2 có currency. Projection v3 cần báo cáo theo currency. Xác định nguồn lịch sử có thể hỗ trợ upcast và khi nào phải đánh dấu dữ liệu không đủ căn cứ.

### Bài H — Saga compensation

Payment authorized nhưng Inventory reserve thất bại. Thiết kế process manager, void/refund command, compensation outcome và stuck workflow alert. Nêu vì sao compensation không xóa event cũ.

### Bài I — So sánh TCO

CQRS + ES làm tăng event store, broker, projection workers, schema registry, monitoring và on-call. Xây bảng lợi ích/chi phí so với CRUD + outbox, gồm audit, replay, read scaling và RTO.

### Bài J — Lộ trình migration

Monolith Order có PostgreSQL và báo cáo chậm. Thiết kế lộ trình tách query handlers, read projections, outbox và chỉ cân nhắc Event Sourcing khi có requirement cụ thể.

## 37. Checklist thiết kế và vận hành

### Trước khi chọn mô hình

- [ ] Có requirement rõ cho read/write separation hoặc event history.
- [ ] CRUD hiện tại đã được đo và có bằng chứng không đáp ứng.
- [ ] Domain ownership và aggregate boundaries được xác định.
- [ ] Invariants và consistency requirements được ghi.
- [ ] Đã so chi phí vận hành và complexity.
- [ ] Có retention, privacy và audit requirements.
- [ ] Có RPO/RTO và backup/replay strategy.

### Khi triển khai CQRS

- [ ] Command model kiểm invariant và authorization.
- [ ] Query model tối ưu cho use cases cụ thể.
- [ ] Read model có owner/schema/rebuild strategy.
- [ ] Event/outbox publication đáng tin.
- [ ] Projection idempotent và theo dõi lag.
- [ ] Read-your-writes cho trải nghiệm cần thiết.
- [ ] Không dùng stale projection để quyết định giao dịch quan trọng.
- [ ] Contract và integration tests bảo vệ consumers.

### Khi triển khai Event Sourcing

- [ ] Event là sự thật đã xảy ra, phân biệt với command.
- [ ] Event identity, aggregate sequence và schema version rõ.
- [ ] Optimistic concurrency và idempotency được kiểm.
- [ ] Event store/archive có retention và backup/restore.
- [ ] Snapshots có cutoff, checksum và version.
- [ ] Upcasters hỗ trợ event versions cần thiết.
- [ ] Replay không có external side effects.
- [ ] Corrections/deletions/privacy được xử lý.
- [ ] Projections có checkpoints và reconciliation.
- [ ] Saga có timeout, compensation và manual recovery.

### Vận hành

- [ ] Monitor command latency/rejections và event-store health.
- [ ] Monitor outbox age, broker lag, projection freshness.
- [ ] Alert theo user/business impact.
- [ ] Replay có quota/throttle và audit.
- [ ] DR drill đo được RTO/RPO.
- [ ] Có quy trình cutover/rollback.
- [ ] Có ownership cho event schema và projection lifecycle.

## 38. Ghi nhớ cốt lõi

**CQRS tách trách nhiệm ghi và đọc; Event Sourcing lưu lịch sử sự kiện làm nguồn sự thật.** Chúng liên quan nhưng khác nhau. CQRS có thể dùng với database quan hệ và transactional outbox. Event Sourcing có thể dùng với một read model đơn giản. Kết hợp cả hai khi lịch sử nghiệp vụ, replay và nhiều read models tạo ra giá trị đủ lớn.

Đừng chọn mô hình vì nó phổ biến hoặc vì hệ thống có nhiều microservices. Hãy bắt đầu từ invariant, query patterns, audit needs, consistency, data retention và khả năng vận hành. Nếu CRUD đáp ứng yêu cầu, giữ nó đơn giản. Nếu read workload cần tối ưu độc lập, thêm CQRS có kiểm soát. Nếu lịch sử nghiệp vụ thực sự là nguồn sự thật cần truy vết và tái dựng, cân nhắc Event Sourcing với event store, schema evolution, snapshots, idempotency và DR được thiết kế ngay từ đầu.

Một kiến trúc thành công phải bảo đảm **command được kiểm tra đúng, read model đủ mới theo contract, event history đáng tin và mọi projection có thể được vận hành, đối soát, khôi phục**.