# Xử lý sự kiện tồn kho đến trễ, trùng hoặc sai thứ tự

Trong kiến trúc microservices, Inventory Service thường nhận lệnh giữ hàng từ Order Service và phát sự kiện để các dịch vụ khác cập nhật trạng thái. Các sự kiện như StockReceived, InventoryReserved, ReservationReleased hoặc StockAdjusted có thể đi qua broker, retry, consumer group và nhiều vùng triển khai. Vì message broker thường cung cấp delivery ít nhất một lần trong nhiều cấu hình phổ biến, consumer có thể nhận cùng một sự kiện nhiều lần. Khi có retry, consumer restart, nhiều partition hoặc xử lý song song, sự kiện cũng có thể đến trễ hoặc được xử lý không đúng thứ tự nghiệp vụ.

Một ví dụ đơn giản:

    v10: StockReceived +10
    v11: InventoryReserved -3
    v12: ReservationReleased +3

    Consumer nhận theo thứ tự:
      v12, v10, v11, v11

Nếu consumer cộng/trừ số lượng ngay khi nhận message mà không kiểm tra event identity, version và trạng thái nghiệp vụ, tồn kho có thể bị tăng/giảm sai, reservation bị tạo hai lần hoặc dữ liệu hiển thị không khớp với nguồn sự thật.

**Xử lý sự kiện tồn kho đến trễ, trùng hoặc sai thứ tự** đòi hỏi xác định đúng owner của tồn kho, mô hình dữ liệu, semantics của từng event, khóa định danh, sequence/version, idempotency, concurrency control và quy trình đối soát. Không thể giải quyết bằng cách chỉ bật ordering của broker hoặc bỏ qua message có timestamp cũ.

Bài học này dùng một nền tảng bán hàng có Order Service, Inventory Service, message broker và các read model. Nội dung tập trung vào cách thiết kế consumer an toàn, phát hiện gap, phục hồi từ snapshot/event log, kiểm soát reservation và xây dựng các bài kiểm thử cho duplicate, late và out-of-order delivery.

## 1. Bối cảnh nghiệp vụ và ranh giới trách nhiệm

Giả sử một kho hàng có các SKU ở nhiều warehouse. Order Service tạo đơn và yêu cầu Inventory Service giữ số lượng. Inventory Service là owner của trạng thái tồn kho và reservation.

Một luồng cơ bản:

    Customer
       |
       v
    Order Service
       |
       | ReserveInventory command
       v
    Inventory Service
       |
       +--> Inventory DB
       |
       +--> Outbox
                |
                v
             Broker
                |
       +--------+---------+
       v                  v
    Order consumer     Analytics consumer
    cập nhật trạng thái  dựng read model

Cần phân biệt:

- **Inventory Service** quyết định có thể giữ hàng hay không và là nơi thực thi invariant về số lượng.
- **Order Service** sở hữu vòng đời đơn hàng; nó không tự ý sửa stock quantity trong database Inventory.
- **Broker** vận chuyển event, không phải nguồn sự thật của số lượng hàng.
- **Read model** ở Search, Analytics hoặc Dashboard có thể trễ; nó không thay thế canonical inventory state.
- **Warehouse/fulfillment systems** có thể phát sinh stock movement, nhưng phải đi qua contract được Inventory owner xác nhận.

Nếu nhiều service cùng cộng/trừ số lượng trực tiếp, không có một nguồn sự thật rõ ràng. Khi event đến trễ hoặc trùng, không có nơi nào có thể quyết định trạng thái cuối cùng đúng.

## 2. Các tình huống cần xử lý

### 2.1. Duplicate event

Cùng một event được giao nhiều lần:

    event_id = E-100
    type = InventoryReserved
    sku = SKU-1
    quantity = 2

Consumer nhận E-100 hai lần. Nếu mỗi lần đều trừ available quantity đi 2, hệ thống giữ hàng 4 đơn vị dù nghiệp vụ chỉ yêu cầu 2.

Duplicate có thể đến từ:

- Relay publish thành công nhưng crash trước khi đánh dấu published.
- Consumer commit database nhưng crash trước khi ack message.
- Kafka offset chưa commit và record được giao lại.
- RabbitMQ redelivery sau consumer restart hoặc nack.
- Retry topic/DLQ replay.
- Producer retry command và vô tình tạo event mới cho cùng logical operation.
- Operator replay một khoảng thời gian đã được xử lý.

Cần phân biệt duplicate cùng event ID với hai event khác ID nhưng cùng đại diện một command nghiệp vụ. Inbox theo event ID giải quyết trường hợp đầu; idempotency/business uniqueness giải quyết trường hợp sau.

### 2.2. Late event

Event được tạo ở thời điểm trước nhưng tới consumer muộn:

    10:00:00 InventoryReserved v21 được tạo
    10:00:01 Broker/consumer gặp sự cố
    10:05:00 InventoryReleased v22 được tạo và xử lý
    10:07:00 Reservation v21 mới được giao tới consumer

Late event không đồng nghĩa event sai. Nó có thể là một thay đổi hợp lệ đã xảy ra trước, nhưng đường truyền hoặc consumer backlog làm việc giao nhận chậm.

Nếu v22 đã được áp dụng, consumer không thể tùy tiện áp v21 như trạng thái mới nhất. Cần sequence/version và quy tắc chuyển trạng thái.

### 2.3. Out-of-order event

Các event được tạo theo thứ tự nhưng consumer xử lý theo thứ tự khác:

    Source order: v30 -> v31 -> v32
    Consumer order: v32 -> v30 -> v31

Nguyên nhân:

- Nhiều consumer instance xử lý song song.
- Các message cùng aggregate đi vào nhiều partition/queue.
- Retry khiến event cũ quay lại sau event mới.
- Consumer gửi message sang retry topic rồi tiếp tục xử lý message sau.
- Một event có payload lớn hoặc xử lý lâu hơn event kế tiếp.
- Republish hoặc replay từ nhiều nguồn.
- Không có partition/routing key ổn định theo SKU và warehouse.

Out-of-order có thể làm hỏng projection, nhưng cũng có thể làm sai business state nếu consumer thực hiện delta mà không kiểm soát sequence.

## 3. Mô hình số lượng tồn kho và các invariant

Trước khi xử lý event, phải định nghĩa tồn kho nghĩa là gì. Một mô hình đơn giản:

    on_hand = số lượng vật lý được ghi nhận
    reserved = số lượng đang giữ cho các đơn chưa kết thúc
    available = on_hand - reserved

Trong hệ thống thực tế, có thể có thêm:

- incoming: hàng đã đặt mua nhưng chưa nhận.
- damaged: hàng hỏng.
- quarantined: hàng đang chờ kiểm định.
- allocated: hàng đã phân bổ cho đơn hoặc wave fulfillment.
- safety_stock: lượng không cho phép bán.
- backordered: lượng đơn chờ bổ sung.

Một công thức có thể là:

    sellable_available =
        on_hand
        - reserved
        - damaged
        - quarantined
        - safety_stock

Công thức thực tế phụ thuộc nghiệp vụ và cách phân loại các bucket. Không cộng mọi trạng thái vào một trường quantity rồi hy vọng consumer tự hiểu.

### 3.1. Invariant quan trọng

Ví dụ:

1. Không được reserve vượt quá sellable available.
2. Một reservation của cùng order line không được tạo hai lần.
3. Một reservation chỉ được release hoặc consume theo trạng thái hợp lệ.
4. Một reservation đã consumed không được release lần nữa.
5. Stock adjustment phải có business reference và audit.
6. Một event cũ không được ghi đè trạng thái mới hơn.
7. Tổng reservation đang active phải khớp ledger/reservation records theo định nghĩa.
8. Tenant, warehouse và SKU phải đúng phạm vi.
9. Một command đã xác nhận thành công phải có thể truy vết.
10. Replay message không được tạo side effect nghiệp vụ lặp.

Các invariant cần được bảo vệ ở Inventory Service bằng transaction, constraint, conditional update hoặc locking phù hợp. Consumer ở dịch vụ khác không thể bảo vệ thay cho owner.

## 4. Phân biệt command, event và state snapshot

Ba loại message có ý nghĩa khác nhau.

**Command:** yêu cầu thực hiện hành động, ví dụ ReserveInventory hoặc ReleaseReservation. Command có thể bị từ chối và cần kết quả theo contract.

**Event:** thông báo một thay đổi đã xảy ra, ví dụ InventoryReserved hoặc ReservationReleased. Event mô tả sự thật đã được owner xác nhận.

**Snapshot:** mô tả trạng thái tại một version hoặc mốc cụ thể, ví dụ InventorySnapshot với on_hand=100, reserved=18, version=42.

Không xử lý command như event. Nếu consumer nhận ReserveInventory command, nó phải kiểm tra điều kiện và tạo reservation nếu hợp lệ. Nếu consumer nhận InventoryReserved event, nó chỉ cập nhật projection hoặc thực hiện các phản ứng được định nghĩa sau khi reservation đã được xác nhận.

Snapshot cũng không phải delta. Nếu payload nói available=80, không cộng 80 vào state hiện tại; cần thay thế projection ở version phù hợp.

## 5. Thiết kế event envelope

Một event nên có metadata đủ để dedupe, ordering, tracing và replay.

Ví dụ:

    {
      "eventId": "evt-1001",
      "eventType": "InventoryReserved",
      "schemaVersion": 2,
      "aggregateType": "InventoryPosition",
      "aggregateId": "warehouse-7:SKU-1",
      "aggregateVersion": 42,
      "eventSequence": 105,
      "occurredAt": "2026-11-12T02:10:00Z",
      "publishedAt": "2026-11-12T02:10:01Z",
      "tenantId": "tenant-7",
      "correlationId": "order-flow-123",
      "causationId": "cmd-reserve-456",
      "payload": {
        "orderId": "order-123",
        "reservationId": "reservation-456",
        "quantity": 2,
        "warehouseId": "warehouse-7",
        "sku": "SKU-1"
      }
    }

Các trường quan trọng:

- eventId: nhận diện duy nhất một event logic, giữ nguyên qua retry.
- eventType: semantics của thay đổi.
- schemaVersion: phiên bản cấu trúc payload.
- aggregateId: định danh thực thể cần ordering.
- aggregateVersion/eventSequence: xác định thứ tự business change.
- occurredAt: thời điểm nghiệp vụ xảy ra, hữu ích cho audit.
- publishedAt: thời điểm relay phát message, hữu ích vận hành.
- tenantId: phạm vi dữ liệu đã được xác thực.
- correlationId: nối các bước workflow.
- causationId: truy ngược command/event gây ra event này.
- payload: nội dung tối thiểu consumer cần.

Không phải mọi hệ thống cần cả aggregateVersion và eventSequence. Cần xác định semantics của từng giá trị. Nếu một transaction tạo nhiều event cho cùng aggregate, eventSequence có thể phân biệt thứ tự trong cùng aggregateVersion.

**Không dùng timestamp làm thứ tự duy nhất.** Đồng hồ giữa node có thể lệch, timestamp có độ phân giải hạn chế, và event được tạo trong transaction có thể commit theo thứ tự khác thời gian máy ghi nhận.

## 6. Event ID, command ID, aggregate version và correlation ID

Những định danh này không thể thay thế nhau:

| Định danh | Mục đích | Ví dụ |
| --- | --- | --- |
| eventId | Dedupe cùng event | evt-1001 |
| commandId/idempotencyKey | Dedupe một yêu cầu nghiệp vụ | reserve-order-123-line-1 |
| aggregateId | Nhóm thay đổi cùng thực thể | warehouse-7:SKU-1 |
| aggregateVersion | Version trạng thái aggregate | 42 |
| eventSequence | Thứ tự event trong aggregate | 105 |
| correlationId | Nối workflow nhiều service | order-flow-123 |
| causationId | Nguyên nhân trực tiếp | cmd-reserve-456 |

Một client có thể gửi ReserveInventory hai lần do timeout. Nếu mỗi lần producer tạo event ID mới, inbox ở consumer không biết chúng là cùng command. Inventory Service cần idempotency key hoặc unique business constraint cho reservation theo order line.

Ngược lại, cùng một event ID được relay gửi lại nhiều lần phải được consumer nhận diện là cùng một event.

## 7. Idempotency: nền tảng xử lý duplicate

**Idempotent consumer** bảo đảm xử lý cùng một event nhiều lần không tạo thêm tác động nghiệp vụ sau lần đầu thành công.

Một bảng inbox:

    create table processed_events (
        consumer_name varchar(120) not null,
        event_id uuid not null,
        processed_at timestamptz not null default now(),
        primary key (consumer_name, event_id)
    );

Consumer xử lý trong một transaction:

    BEGIN
      INSERT processed_events(consumer_name, event_id)
        ON CONFLICT DO NOTHING

      Nếu insert không thêm row:
        đây là duplicate, không chạy business update.

      Nếu insert thêm row:
        cập nhật projection/business state.
    COMMIT

Inbox record và local business update phải commit hoặc rollback cùng nhau. Nếu insert inbox commit riêng rồi update inventory thất bại, lần redelivery sau sẽ bị bỏ qua dù business state chưa được cập nhật.

### 7.1. Atomic insert thay vì SELECT rồi INSERT

Thiết kế dễ lỗi:

    SELECT event_id FROM processed_events WHERE event_id = ?
    Nếu không thấy:
        INSERT event_id
        UPDATE inventory

Hai consumer instance có thể cùng SELECT không thấy event rồi cùng thực hiện. Unique constraint có thể khiến một insert thất bại, nhưng business update phải nằm sau khi insert giành được quyền xử lý thành công.

Dùng INSERT ... ON CONFLICT DO NOTHING hoặc thao tác atomic tương đương; dựa vào unique constraint của database để phối hợp concurrency.

### 7.2. Inbox scope

Khóa thường gồm consumer_name + event_id vì hai consumer độc lập có thể cần xử lý cùng event một lần mỗi consumer. Nếu nhiều handler trong cùng service có business effects khác nhau, định nghĩa consumer identity theo đơn vị idempotency thực tế.

Không dùng eventId làm idempotency key cho một command khác được tạo ra từ event nếu command đó có vòng đời riêng.

## 8. Idempotency ở Inventory command boundary

Ví dụ client yêu cầu reserve cho một order line:

    POST /inventory/reservations
    Idempotency-Key: order-123-line-1-reserve-v1

Inventory Service lưu command key, tenant scope, request hash và kết quả:

    create table inventory_commands (
        tenant_id uuid not null,
        idempotency_key varchar(200) not null,
        request_hash varchar(128) not null,
        status varchar(30) not null,
        reservation_id uuid,
        response_payload jsonb,
        created_at timestamptz not null default now(),
        primary key (tenant_id, idempotency_key)
    );

Nếu cùng key và cùng payload, trả lại kết quả đã lưu hoặc trạng thái đang xử lý. Nếu cùng key nhưng payload khác, trả conflict. Nếu client thực sự tạo một lần reserve mới sau khi release, phải dùng logical command key mới theo policy.

Ngoài idempotency key, có thể cần unique constraint nghiệp vụ như (tenant_id, order_id, order_line_id, reservation_attempt) để ngăn cùng một line tạo reservation trùng.

## 9. Version guard để bỏ qua event cũ

Inbox giải quyết duplicate cùng event ID. Nó không ngăn một event cũ khác ID ghi đè state mới.

Ví dụ:

    v41: InventoryPosition available=10
    v42: InventoryPosition available=8
    v43: InventoryPosition available=12

Consumer nhận v43 rồi v42. Nếu cập nhật vô điều kiện, projection lùi về available=8.

Dùng version guard:

    UPDATE inventory_projection
       SET available = :incoming_available,
           aggregate_version = :incoming_version
     WHERE aggregate_id = :aggregate_id
       AND aggregate_version < :incoming_version;

Nếu update không tác động row, cần phân biệt:
- Event đã được áp dụng hoặc stale.
- Projection chưa tồn tại.
- Có gap version.
- Event có cùng version nhưng payload khác.
- Aggregate ID sai.

Không nên âm thầm coi mọi trường hợp update count bằng 0 là duplicate.

### 9.1. State snapshot và delta event

Với **snapshot event**, version guard thường đủ để giữ trạng thái mới nhất nếu snapshot tự đầy đủ và version có thứ tự rõ.

Với **delta event**, ví dụ StockReceived +10 hoặc InventoryReserved -2, bỏ qua event cũ chỉ dựa vào version có thể làm mất một thay đổi hợp lệ nếu các event trước chưa được áp dụng.

Ví dụ consumer nhận sequence 15 rồi sequence 13. Nếu áp 15 và bỏ 13 vì cũ, nhưng 14 cũng chưa được áp dụng, số lượng cuối sai. Với delta event cần gap detection và xử lý sequence liên tục hoặc rebuild từ nguồn canonical.

## 10. Gap detection: phát hiện thiếu event

Giả sử consumer đã xử lý sequence 100 và nhận sequence 103. Có thể thiếu 101 và 102.

Không phải mọi hệ thống đều yêu cầu xử lý mọi sequence; nhưng nếu delta event phụ thuộc đầy đủ chuỗi, cần phát hiện gap.

Quy trình:

1. Đọc last_applied_sequence của aggregate.
2. So incoming sequence với expected = last + 1.
3. Nếu incoming == expected, xử lý và tăng checkpoint.
4. Nếu incoming <= last, kiểm tra duplicate/stale theo inbox/version.
5. Nếu incoming > expected, không áp delta mù; buffer hoặc đánh dấu gap.
6. Tìm cách lấy event bị thiếu, replay hoặc tải snapshot mới.
7. Sau khi khôi phục chuỗi, tiếp tục xử lý các event đang chờ.

Bảng checkpoint có thể là:

    create table consumer_offsets_by_aggregate (
        consumer_name varchar(120) not null,
        aggregate_id varchar(240) not null,
        last_sequence bigint not null,
        updated_at timestamptz not null,
        primary key (consumer_name, aggregate_id)
    );

Đây là checkpoint nghiệp vụ theo aggregate, khác offset của Kafka partition. Kafka offset cho biết consumer đã đọc tới vị trí nào trong partition; aggregate sequence cho biết chuỗi thay đổi của một InventoryPosition đã được áp tới đâu.

## 11. Ba chiến lược xử lý out-of-order

### 11.1. Buffer event khi có gap

Khi nhận sequence 103 nhưng last sequence là 100, lưu 103 vào pending table hoặc retry store. Chờ 101 và 102 tới, sau đó áp lần lượt.

Ưu điểm:
- Giữ được semantics của delta.
- Không bỏ qua transition.

Đánh đổi:
- Cần bounded buffer và timeout.
- Một gap kéo dài có thể chặn aggregate đó.
- Cần giới hạn số event chờ, số lần retry và cảnh báo.
- Khi thiếu event vĩnh viễn, cần snapshot/replay.

Không buffer vô hạn; nó có thể làm database/queue tăng không giới hạn.

### 11.2. Tải snapshot canonical

Nếu consumer chỉ cần trạng thái hiện tại, có thể gọi Inventory API hoặc nhận InventorySnapshot ở version mới nhất.

Quy trình:
- Phát hiện gap.
- Đánh dấu projection stale.
- Lấy snapshot từ owner.
- Kiểm tra aggregate ID và version.
- Chỉ thay projection nếu snapshot mới hơn state hiện tại.
- Ghi checkpoint/version snapshot.
- Bỏ các delta cũ hơn snapshot nếu semantics cho phép.
- Tiếp tục từ sequence sau snapshot.

Snapshot phải được tạo nhất quán và có version/sequence. Một snapshot không có mốc version không thể chứng minh event nào đã được bao gồm.

### 11.3. Dùng phép toán giao hoán khi phù hợp

Một số phép cộng có thể giao hoán về mặt toán học:

    +5 + (-2) = -2 + 5

Nhưng nghiệp vụ reservation không đơn giản là cộng/trừ. Reserve phải kiểm tra available không âm; release chỉ hợp lệ nếu reservation đang active; consume chỉ hợp lệ nếu hàng đã được giữ. Những chuyển trạng thái này không thể coi là delta độc lập.

Chỉ chọn mô hình commutative/CRDT khi phép toán và invariant thực sự đáp ứng các tính chất cần thiết. Không dùng phép cộng số lượng như lý do bỏ qua ordering của business state.

## 12. Thiết kế inventory ledger và reservation state machine

Một cách an toàn là ghi nhận stock movements và reservation state riêng.

Ví dụ các loại movement:

- RECEIPT: nhận hàng tăng on_hand.
- RESERVE: giữ hàng, tăng reserved.
- RELEASE: giải phóng reservation, giảm reserved.
- CONSUME: xuất hàng đã giữ, giảm on_hand và reserved.
- ADJUSTMENT: điều chỉnh có lý do/audit.
- RETURN: hàng trả về, tùy trạng thái kiểm định.
- DAMAGE: chuyển hàng sang bucket không bán được.

Mỗi movement có movement_id duy nhất, business reference, SKU, warehouse, quantity, occurred_at và version/sequence.

Reservation có state machine:

    REQUESTED
       |
       v
    RESERVED
       | \
       |  \--> EXPIRED
       |
       +-----> RELEASED
       |
       +-----> CONSUMED

Các transition phải được định nghĩa:
- RESERVED → RELEASED chỉ một lần.
- RESERVED → CONSUMED chỉ một lần.
- RELEASED không thể quay lại CONSUMED nếu không tạo một reservation mới.
- EXPIRED không được release thêm lần nữa nếu expiry đã giải phóng stock.
- Command trùng phải trả kết quả trước đó.

Có thể dùng optimistic locking hoặc row lock để hai command đồng thời không cùng vượt available quantity.

## 13. Atomic reserve và chống oversell

Ví dụ conditional update PostgreSQL:

    UPDATE inventory_positions
       SET reserved = reserved + :quantity,
           version = version + 1
     WHERE tenant_id = :tenant_id
       AND warehouse_id = :warehouse_id
       AND sku = :sku
       AND on_hand - reserved - safety_stock >= :quantity;

Nếu affected row count = 1, lệnh giữ hàng thành công. Nếu = 0, không đủ hàng hoặc record không tồn tại theo policy; cần phân biệt bằng truy vấn/contract phù hợp.

Cập nhật phải cùng transaction với:
- Reservation record.
- Idempotency/command record.
- Outbox event InventoryReserved.

Không thực hiện SELECT available rồi UPDATE riêng rẽ mà không khóa/điều kiện, vì hai request có thể cùng đọc available=5 rồi đều reserve 4.

Với nhiều dòng SKU trong cùng order, cần xác định atomicity policy: tất cả giữ thành công hoặc không giữ dòng nào; hoặc cho phép partial reservation và biểu diễn trạng thái rõ. Nếu nhiều SKU ở nhiều warehouse, transaction có thể phức tạp hơn; cần thứ tự lock ổn định hoặc workflow/saga có compensation.

## 14. Late event không nhất thiết là stale event

Cần phân biệt ba thời gian:

- **occurredAt:** khi thay đổi nghiệp vụ xảy ra.
- **publishedAt:** khi producer/relay phát event.
- **consumedAt:** khi consumer xử lý event.

Event có occurredAt cũ nhưng version cao hơn state consumer hiện tại có thể là event hợp lệ bị trễ. Ngược lại, event đến sau nhưng version thấp hơn có thể là event stale.

Ví dụ:

    Consumer hiện có version 50.
    Nhận event version 48, occurredAt cũ.
    => stale theo version, không áp lại.

    Consumer hiện có version 50.
    Nhận event version 52, occurredAt trước thời điểm nhận.
    => event mới đối với consumer, có thể đã bị trễ.
       Nhưng cần xử lý gap 51 nếu dùng delta sequence.

Không dùng điều kiện occurredAt < now để bỏ event. Cũng không dùng thời điểm nhận để quyết định event nào mới hơn.

## 15. Event snapshot và event delta có policy khác nhau

| Loại | Payload ví dụ | Xử lý khi đến trễ |
| --- | --- | --- |
| Full snapshot | on_hand=100, reserved=20, version=42 | Áp nếu version mới hơn |
| Delta movement | RECEIPT +10, sequence=42 | Cần đảm bảo sequence trước đã áp hoặc ledger xử lý đúng |
| State transition | ReservationReleased, version=42 | Kiểm tra reservation state và version |
| Notification fact | StockThresholdReached | Dedupe theo event ID/business key |
| Command | Reserve SKU 2 units | Kiểm tra idempotency, available và domain rules |

Không đặt mọi event vào một consumer handler chỉ có phép cộng/trừ quantity. Event type quyết định semantics và invariant cần bảo vệ.

## 16. Ordering ở Kafka và RabbitMQ

### 16.1. Kafka

Kafka đảm bảo thứ tự record trong cùng partition. Nếu muốn event của cùng InventoryPosition được xử lý theo thứ tự, dùng key ổn định như:

    key = tenantId + warehouseId + sku

Các lưu ý:
- Các event cùng key được đưa về cùng partition theo partitioner/configuration.
- Thứ tự không được bảo đảm giữa các partition.
- Nhiều consumer trong cùng group xử lý các partition khác nhau song song.
- Consumer concurrency bên trong một partition phải giữ thứ tự nếu handler async.
- Tăng partition có thể làm key được map sang partition khác; cần hiểu tác động với dữ liệu hiện hữu và ordering.
- Retry topic có thể làm event lỗi quay lại sau event mới.
- Offset commit phải phù hợp với business transaction.

Kafka partition ordering giảm out-of-order ở một phạm vi, nhưng không thay thế sequence/version guard và idempotency.

### 16.2. RabbitMQ

RabbitMQ queue có thể giao message theo thứ tự enqueue trong một số cấu hình, nhưng xử lý nhiều consumer, prefetch, redelivery, requeue và retry có thể khiến thứ tự hoàn tất khác thứ tự nhận.

Cần:
- Routing key theo aggregate nếu cần phân luồng.
- Single active consumer hoặc serial lane cho aggregate khi thật sự cần.
- Prefetch giới hạn để không có quá nhiều message đang xử lý.
- Retry/DLX không làm event cũ quay lại sau event mới mà không có version handling.
- Consumer idempotent và sequence-aware.

Không giả định Kafka và RabbitMQ có cùng semantics ordering/ack. Cấu hình cụ thể và topology quyết định hành vi.

## 17. Consumer concurrency và xử lý song song

Nếu cùng một SKU/warehouse có nhiều event đồng thời, hai handler có thể đọc cùng version và cùng update.

Các lựa chọn:

**Serial per aggregate:** xử lý một InventoryPosition tại một thời điểm. Dễ hiểu nhưng throughput cho key nóng bị giới hạn.

**Optimistic concurrency:** update với điều kiện version cũ, conflict thì reload và retry theo business rule.

**Pessimistic row lock:** SELECT FOR UPDATE để tuần tự hóa thay đổi trên row. Cần transaction ngắn và thứ tự lock ổn định.

**Partitioning:** đưa cùng aggregate key vào cùng lane/partition.

**Ledger append-only:** ghi movement với unique movement/event ID, rồi dựng projection bằng processor tuần tự hoặc replay.

Không dùng khóa toàn database nếu chỉ một SKU/warehouse cần tuần tự. Cũng không dùng thread pool vô hạn; concurrency cần phù hợp DB connection pool và throughput downstream.

## 18. Transactional Inbox và cập nhật projection cùng transaction

Một consumer projection có thể làm:

1. Bắt đầu transaction DB.
2. Insert eventId vào inbox.
3. Nếu duplicate, kết thúc thành công mà không thay state.
4. Kiểm tra aggregate version/sequence.
5. Nếu sequence đúng, cập nhật projection và checkpoint.
6. Commit.
7. Sau commit mới ack message/commit offset theo cấu hình.

Ví dụ SQL:

    BEGIN;

    INSERT INTO processed_events(consumer_name, event_id)
    VALUES (:consumer, :event_id)
    ON CONFLICT DO NOTHING;

    -- Chỉ tiếp tục nếu insert thành công.
    UPDATE inventory_projection
       SET on_hand = :on_hand,
           reserved = :reserved,
           version = :version
     WHERE aggregate_id = :aggregate_id
       AND version < :version;

    UPDATE consumer_offsets_by_aggregate
       SET last_sequence = :sequence,
           updated_at = now()
     WHERE consumer_name = :consumer
       AND aggregate_id = :aggregate_id;

    COMMIT;

SQL là minh họa, cần khóa/insert checkpoint khi aggregate mới và xử lý gap/stale trước khi update. Không chạy UPDATE projection nếu inbox insert đã conflict.

## 19. Java/Spring: event handler idempotent

Ví dụ khái niệm:

    @Service
    public class InventoryProjectionHandler {
        private final JdbcTemplate jdbc;

        public InventoryProjectionHandler(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void handle(InventorySnapshot event) {
            int inserted = jdbc.update(
                """
                insert into processed_events(
                    consumer_name, event_id
                )
                values (?, ?)
                on conflict do nothing
                """,
                "inventory-read-model",
                event.eventId()
            );

            if (inserted == 0) {
                return;
            }

            int updated = jdbc.update(
                """
                update inventory_projection
                   set on_hand = ?,
                       reserved = ?,
                       aggregate_version = ?,
                       updated_at = now()
                 where aggregate_id = ?
                   and aggregate_version < ?
                """,
                event.onHand(),
                event.reserved(),
                event.aggregateVersion(),
                event.aggregateId(),
                event.aggregateVersion()
            );

            // Nếu projection chưa có, tạo mới theo policy.
            // Nếu version có gap hoặc payload conflict,
            // không âm thầm bỏ qua; ghi nhận cần reconcile.
        }
    }

Các record/DTO là ví dụ, chưa bao gồm xử lý mọi trường hợp projection chưa tồn tại, version gap hoặc concurrent insert. Trong code production, inbox insert và projection update phải dùng cùng transaction manager. Event stale có thể được đánh dấu đã xử lý sau khi xác định an toàn rằng nó không cần áp dụng; event có gap phải được giữ lại để xử lý tiếp.

### 19.1. Đừng ack trước khi transaction commit

Nếu listener ack message trước rồi database transaction rollback, broker không giao lại event và projection bị thiếu. Nếu DB commit rồi process crash trước ack, broker có thể giao lại; inbox sẽ nhận ra duplicate.

Với Kafka, offset commit phải không đi trước record chưa xử lý thành công theo semantics của consumer. Với RabbitMQ, manual ack sau commit. Cấu hình container và async listener phải được integration test.

## 20. Xử lý version gap bằng pending table

Một pending table có thể lưu event đến sớm:

    create table pending_inventory_events (
        consumer_name varchar(120) not null,
        aggregate_id varchar(240) not null,
        sequence bigint not null,
        event_id uuid not null,
        payload jsonb not null,
        received_at timestamptz not null default now(),
        primary key (consumer_name, aggregate_id, sequence),
        unique (consumer_name, event_id)
    );

Khi nhận sequence 103 nhưng last applied là 100:
- Lưu event 103 vào pending.
- Phát hiện cần 101 và 102.
- Yêu cầu replay hoặc chờ message tới trong một khoảng giới hạn.
- Khi 101 được áp, thử lấy 102, sau đó 103.
- Nếu gap quá hạn, đánh dấu aggregate degraded và tải snapshot/rebuild.

Không giữ broker message chưa ack vô hạn chỉ để đợi một sequence nếu điều đó chặn partition/queue. Có thể persist vào pending store rồi ack theo policy, nhưng pending store phải có retry, retention, alert và recovery path.

## 21. Khi nào nên tải snapshot từ Inventory owner?

Snapshot recovery phù hợp khi:
- Consumer chỉ cần trạng thái hiện tại.
- Event history không còn đầy đủ.
- Gap không thể khôi phục trong budget.
- Projection bị sai do bug và cần rebuild.
- Một consumer mới cần bootstrap.

Snapshot cần:
- aggregate ID và tenant scope.
- version/sequence tại thời điểm chụp.
- dữ liệu đầy đủ cho projection.
- semantics rõ: snapshot bao gồm mọi event tới sequence nào.
- cách áp nguyên tử, tránh snapshot cũ ghi đè dữ liệu mới.
- checkpoint tiếp tục nhận delta từ sequence sau snapshot.

Một quy trình:

    1. Mark projection STALE.
    2. Request snapshot from Inventory owner.
    3. Receive snapshot version=120.
    4. Atomically replace projection if version is newer.
    5. Set last_sequence=120.
    6. Replay/apply events sequence >120.
    7. Mark projection CURRENT after catch-up.

Không tải snapshot rồi xóa pending events một cách mù quáng. Chỉ loại event đã được snapshot bao gồm hoặc đã xử lý theo sequence có bằng chứng.

## 22. Reconciliation: đối chiếu với nguồn sự thật

Event consumer có thể mất message, xử lý sai hoặc có bug trong transform. Vì vậy cần job reconciliation định kỳ.

Các phép kiểm tra:

- So available/on_hand/reserved của projection với Inventory API hoặc snapshot canonical.
- So tổng reservation active với reservation records.
- Tìm reservation không có order tương ứng hoặc order đã hủy nhưng reservation vẫn active.
- Tìm event sequence gap.
- So ledger movement với projection tổng hợp.
- Kiểm tra SKU/warehouse/tenant mapping.
- Kiểm tra negative available hoặc trạng thái không hợp lệ.
- Kiểm tra duplicate business reference.
- Đối chiếu đơn đã fulfilled với reservation đã consumed.

Không sửa canonical inventory chỉ dựa trên một projection sai. Nếu projection sai, rebuild projection từ source/ledger. Nếu canonical state sai, cần business adjustment có audit và lý do rõ.

### 22.1. Reconciliation có thể sửa thế nào?

- **Projection drift:** tải snapshot và replay events.
- **Missing consumer event:** replay từ event log hoặc outbox/archive.
- **Duplicate movement:** dedupe bằng movement/event ID và business uniqueness.
- **Canonical stock mismatch:** tạo adjustment command có người/nguồn phê duyệt, không sửa trực tiếp cột quantity không audit.
- **Reservation mismatch:** đối chiếu order/payment state và thực hiện release/consume theo state machine.

Reconciliation phải idempotent và có audit trail; chạy lại không tạo adjustment lặp.

## 23. Reservation lifecycle và event đến trễ

Giả sử order tạo reservation R1:

    ReservationCreated R1
    ReservationExpired R1
    PaymentAuthorized order-123
    ReservationCreated R1 (redelivery cũ)

Event cuối là duplicate hoặc stale. Consumer không được tạo lại reservation chỉ vì thấy ReservationCreated đến sau.

Lưu state theo reservation ID:

| State hiện tại | Event/command | Kết quả hợp lệ |
| --- | --- | --- |
| REQUESTED | Reserve accepted | RESERVED |
| RESERVED | Release | RELEASED |
| RESERVED | Consume/fulfill | CONSUMED |
| RESERVED | Expire | EXPIRED/RELEASED theo policy |
| RELEASED | Release lần nữa | Idempotent no-op |
| CONSUMED | Release | Từ chối hoặc compensation riêng |
| EXPIRED | Consume | Từ chối, cần workflow mới |
| RELEASED | Event Reserve cũ | Không hồi sinh |

Cần xác định race giữa PaymentAuthorized và ReservationExpired. Có thể dùng deadline, version và workflow coordinator; không quyết định chỉ theo timestamp tới consumer.

## 24. Race giữa release, expiry và consume

Một reservation có thể hết hạn cùng lúc worker fulfillment xử lý consume.

Hai command đồng thời:
- Expiry worker muốn RESERVED → RELEASED.
- Fulfillment muốn RESERVED → CONSUMED.

Chỉ một transition được thành công. Dùng conditional update:

    UPDATE reservations
       SET status = 'CONSUMED',
           version = version + 1
     WHERE reservation_id = :id
       AND status = 'RESERVED';

Nếu affected rows = 0, đọc trạng thái hiện tại và trả kết quả theo policy. Expiry worker cũng dùng điều kiện status=RESERVED. Transaction DB đảm bảo hai transition không cùng thành công.

Khi transition thành công, ghi movement/outbox trong cùng transaction. Event của transition thất bại không được phát ra.

## 25. Điều chỉnh tồn kho và kiểm soát delta

Một StockAdjusted event thường có thể là delta (+/-) hoặc snapshot tuyệt đối. Contract phải nói rõ.

Delta:

    quantityDelta = -3
    movementId = adjustment-100
    sequence = 51

Snapshot:

    onHand = 97
    aggregateVersion = 51

Nếu consumer nhận cùng delta hai lần, tổng số lượng bị đổi hai lần trừ khi dedupe. Nếu consumer nhận snapshot hai lần, version guard có thể khiến lần thứ hai no-op.

Không trộn hai semantics dưới cùng một event type hoặc field quantity mơ hồ. Với movement ledger, mỗi movement có unique ID và có thể được tổng hợp lại; snapshot giúp bootstrap/recovery.

## 26. Partition key và aggregate boundary

Chọn key cho broker theo đơn vị cần ordering. Đối với tồn kho thường là:

    tenantId + warehouseId + sku

Nếu quantity được quản lý theo lot/bin, aggregate key có thể chi tiết hơn:
- warehouse + SKU.
- warehouse + SKU + lot.
- warehouse + SKU + bin.

Key quá rộng làm giảm parallelism; key quá hẹp có thể phá invariant nếu nhiều bin cùng tham gia một reservation tổng. Chọn aggregate boundary theo nơi invariant được bảo vệ.

Một đơn hàng có nhiều SKU sẽ phát sinh nhiều aggregate inventory độc lập. Không có ordering toàn cục giữa các SKU nếu chúng ở partition khác. Nếu cần reserve tất cả hoặc không reserve gì, Inventory Service phải điều phối transaction/workflow; không dựa vào thứ tự message giữa partition.

## 27. Retry, DLQ và backpressure

Phân loại lỗi consumer:

**Transient:** database tạm unavailable, network reset, throttling. Retry với backoff, jitter và budget.

**Ordering gap:** không phải lỗi payload; persist pending hoặc yêu cầu replay/snapshot.

**Permanent/schema:** payload không parse được, event version không hỗ trợ. Đưa quarantine/DLQ, alert và xử lý schema/consumer.

**Business conflict:** reservation đã released/consumed. Trả kết quả theo state machine, không retry vô hạn.

**Unknown external outcome:** provider có thể đã thực hiện side effect. Query/reconcile trước khi retry command mới.

Giới hạn:
- Số lần retry và tuổi message.
- Số pending events trên mỗi aggregate.
- Tổng queue depth và oldest message age.
- Consumer concurrency.
- Database connection pool.
- Tốc độ replay sau outage.

Backpressure ngăn consumer lấy nhiều message hơn khả năng xử lý. Nếu retry ngay lập tức, message lỗi có thể tạo hot loop và chặn message hợp lệ.

### 27.1. DLQ và replay

DLQ cần owner và runbook:
- Lý do đưa vào DLQ.
- Event ID, aggregate ID, sequence.
- Payload được bảo vệ theo privacy policy.
- Consumer/schema version gây lỗi.
- Hướng sửa và quyền replay.
- Cách giữ ordering khi replay.
- Cách dedupe nếu event đã từng được xử lý.

Không tạo event ID mới khi replay cùng event cũ. Nếu cần tạo một business correction mới, phải tạo event mới, có causation/correlation và audit.

## 28. Kafka offset và RabbitMQ acknowledgment

### Kafka

Kafka offset thể hiện vị trí consumer group đã commit trong partition, không phải aggregate version. Nếu DB commit xong nhưng process crash trước offset commit, record có thể được giao lại; inbox dedupe bảo vệ business update.

Nếu commit offset trước DB commit rồi DB rollback, message có thể bị bỏ qua. Cần chọn ack/commit mode và batch semantics để offset không vượt qua record chưa được xử lý thành công.

### RabbitMQ

Với manual ack, chỉ ack sau khi business transaction commit. Nếu consumer crash trước ack, broker có thể redeliver; inbox xử lý duplicate. Prefetch giới hạn message đang unacked. Requeue ngay lập tức khi lỗi permanent có thể gây vòng lặp.

Không dùng cùng cấu hình mặc định cho hai broker. Hãy kiểm thử đúng container mode, concurrency, retry topology và failure behavior.

## 29. Java/Spring: inbox và version guard

Ví dụ handler cho snapshot projection:

    @Service
    public class InventorySnapshotHandler {
        private final JdbcTemplate jdbc;

        public InventorySnapshotHandler(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void handle(InventorySnapshot event) {
            int inserted = jdbc.update(
                """
                insert into processed_events(
                    consumer_name, event_id
                )
                values (?, ?)
                on conflict do nothing
                """,
                "inventory-dashboard",
                event.eventId()
            );

            if (inserted == 0) {
                return;
            }

            jdbc.update(
                """
                insert into inventory_projection(
                    aggregate_id, on_hand, reserved,
                    aggregate_version
                )
                values (?, ?, ?, ?)
                on conflict (aggregate_id)
                do update set
                    on_hand = excluded.on_hand,
                    reserved = excluded.reserved,
                    aggregate_version = excluded.aggregate_version
                where inventory_projection.aggregate_version
                      < excluded.aggregate_version
                """,
                event.aggregateId(),
                event.onHand(),
                event.reserved(),
                event.aggregateVersion()
            );
        }
    }

Đây là ví dụ minh họa. Production code cần xử lý projection chưa tồn tại, tenant key, snapshot staleness, version conflict và audit. Cùng transaction manager phải quản lý inbox và projection.

Snapshot có thể bỏ qua các version thấp hơn nếu nó chứa đầy đủ trạng thái tại version của mình. Với delta event, cần gap handling thay vì áp dụng câu lệnh trên một cách máy móc.

## 30. Java/Spring: atomic reservation với idempotency

Một transaction khái niệm:

    @Transactional
    public ReservationResult reserve(ReserveCommand command) {
        var previous = commandRepository.find(
            command.tenantId(), command.idempotencyKey()
        );

        if (previous.isPresent()) {
            return previous.get().sameRequest(command)
                ? previous.get().result()
                : throwConflict();
        }

        int updated = jdbc.update(
            """
            update inventory_positions
               set reserved = reserved + ?,
                   version = version + 1
             where tenant_id = ?
               and warehouse_id = ?
               and sku = ?
               and on_hand - reserved - safety_stock >= ?
            """,
            command.quantity(),
            command.tenantId(),
            command.warehouseId(),
            command.sku(),
            command.quantity()
        );

        if (updated != 1) {
            throw new InsufficientStockException();
        }

        Reservation reservation = reservationRepository.create(command);
        commandRepository.saveSuccess(command, reservation);
        outboxRepository.save(
            InventoryReservedEvent.from(reservation)
        );

        return ReservationResult.from(reservation);
    }

Đây là pseudo-code để diễn tả transaction boundary, không phải class hoàn chỉnh. Kiểm tra idempotency phải có unique constraint và xử lý race khi hai request cùng key đồng thời; một SELECT trước rồi INSERT riêng lẻ chưa đủ. Tốt hơn là claim key bằng atomic insert/unique constraint trong transaction.

Nếu reserve nhiều SKU, phải quyết định atomicity của toàn order và lock ordering để tránh deadlock. Nếu transaction rollback, reservation, stock update, command result và outbox event phải rollback cùng nhau.

## 31. Rebuild projection từ ledger

Một projection sai có thể được dựng lại nếu có ledger/event history đầy đủ.

Quy trình:

1. Tạo projection mới hoặc bảng staging.
2. Chọn snapshot/checkpoint canonical.
3. Replay movement/event từ sequence sau snapshot.
4. Deduplicate theo movement/event ID.
5. Kiểm tra sequence và business invariants.
6. So sánh với Inventory owner.
7. Chuyển reader sang projection mới bằng cutover có kiểm soát.
8. Giữ projection cũ trong cửa sổ recovery rồi cleanup.

Không rebuild trực tiếp bảng production đang được query nếu quá trình có thể làm state nửa chừng. Dùng staging table, versioned projection hoặc shadow rebuild rồi chuyển alias/routing sau khi xác minh.

Nếu event history không đầy đủ, snapshot canonical là điểm bắt đầu. Không giả định broker retention là event store vĩnh viễn.

## 32. Observability: phát hiện event trễ, trùng và sai thứ tự

Các metric hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| inventory_consumer_received_total | Tổng event nhận |
| inventory_consumer_processed_total | Event mới được xử lý |
| inventory_consumer_duplicate_total | Event bị inbox dedupe |
| inventory_consumer_stale_total | Event cũ bị version guard |
| inventory_sequence_gap_total | Phát hiện sequence gap |
| inventory_pending_event_count | Event đang chờ gap |
| inventory_oldest_pending_age_seconds | Tuổi pending lâu nhất |
| inventory_event_lag_seconds | consumedAt - publishedAt |
| inventory_event_processing_seconds | Thời gian xử lý |
| inventory_dlq_total | Event đưa vào DLQ |
| inventory_reconcile_mismatch_total | Sai lệch projection/canonical |
| inventory_reservation_conflict_total | Conflict state transition |
| inventory_available_negative_total | Vi phạm invariant nếu mô hình không cho phép |

Tên metric chỉ minh họa. Tránh dùng sku, orderId hoặc tenantId cardinality cao làm labels không giới hạn. Dùng warehouse/shard/service/event type và logs/traces có kiểm soát để drilldown.

### 32.1. Phân biệt event lag và business lateness

- Consumer lag theo broker offset cho biết consumer chậm so với broker.
- Processing delay cho biết event mất bao lâu từ publish tới xử lý.
- Business lateness có thể so occurredAt với consumedAt, nhưng cần clock synchronization và không dùng làm thứ tự canonical.
- Sequence gap cho biết có thiếu một phần chuỗi business change.
- Duplicate rate cho biết delivery/replay lặp.

Một consumer có lag thấp vẫn có thể xử lý sai thứ tự do nhiều worker; một consumer có lag cao vẫn có thể giữ đúng ordering nếu xử lý tuần tự.

### 32.2. Alert và runbook

Alert khi:
- Sequence gap tồn tại quá lâu.
- Pending event age vượt deadline.
- Duplicate rate tăng đột biến.
- DLQ tăng.
- Inventory projection khác canonical vượt ngưỡng.
- Reservation active không khớp order/payment.
- Consumer lag tăng liên tục.
- Available âm hoặc movement bị áp trùng.
- Consumer version/schema lỗi.

Runbook phải chỉ rõ khi nào replay, khi nào snapshot rebuild, khi nào dừng consumer, và ai được phép tạo adjustment canonical.

## 33. Bảo mật và multi-tenancy

Event inventory có thể chứa order IDs, SKU, warehouse, tenant và thông tin kinh doanh nhạy cảm.

Cần:
- Xác thực producer identity.
- Kiểm tra tenant ownership ở Inventory Service.
- Không tin tenantId từ message nếu producer không có quyền.
- Chỉ publish các field consumer cần.
- Bảo vệ broker, DLQ, pending store và event archive.
- Không log payload chứa PII không cần thiết.
- Audit thao tác replay/adjustment.
- Phân quyền consumer theo topic/event type.
- Chống message quá lớn hoặc payload không hợp lệ.
- Giữ retention và deletion theo policy.

Nếu một event sai tenant được xử lý, đó là lỗi data isolation, không phải chỉ là lỗi projection. Dừng luồng liên quan và điều tra mapping/authorization.

## 34. Failure matrix

| Tình huống | Hành vi sai | Cách xử lý đúng |
| --- | --- | --- |
| Event cùng ID đến hai lần | Trừ stock hai lần | Inbox unique + transaction |
| Hai event ID khác nhau cùng command | Tạo hai reservation | Idempotency key/business uniqueness |
| v12 tới trước v11 | State bị lùi | Sequence/version gap handling |
| Snapshot cũ tới sau snapshot mới | Ghi đè state mới | Monotonic version guard |
| Delta v15 tới khi thiếu v14 | Sai tổng quantity | Buffer/replay/snapshot |
| Consumer commit DB rồi crash trước ack | Event redelivery | Inbox dedupe |
| Ack trước DB commit | Mất update | Ack sau commit |
| Reservation release hai lần | Tăng available hai lần | State transition conditional |
| Consume sau expiry | Trừ hàng sai | Reservation state machine |
| Relay publish rồi crash trước mark | Duplicate publish | Event ID ổn định + inbox |
| Retry topic trả event cũ sau event mới | Out-of-order | Sequence guard/replay lane |
| Consumer backlog quá lớn | Event xử lý quá trễ | Backpressure, scale, priority |
| Projection bị sai | Sửa canonical theo projection | Rebuild projection từ owner/ledger |
| Stock canonical sai | Update quantity trực tiếp không audit | Adjustment command có kiểm soát |

## 35. Bộ kiểm thử bắt buộc

### Duplicate

- Cùng event ID nhận hai lần tuần tự.
- Cùng event ID nhận đồng thời ở hai consumer instance.
- Relay publish thành công rồi crash trước mark.
- Consumer DB commit rồi crash trước ack.
- DLQ replay event đã từng xử lý.

Kỳ vọng: một business effect duy nhất.

### Late và out-of-order

- Sequence 12 tới trước 11.
- Sequence 12 tới trước 10 và 11.
- Event 10 tới sau snapshot version 12.
- Event cũ tới sau delete/release.
- Retry event cũ sau khi event mới đã được xử lý.
- Một event bị thiếu vĩnh viễn.
- Snapshot được tải trong lúc delta mới vẫn tới.

Kỳ vọng: không lùi state; gap được phát hiện; recovery không mất movement hợp lệ.

### Concurrency và reservation

- Hai request cùng reserve số lượng còn lại.
- Reserve và release đồng thời.
- Expire và consume đồng thời.
- Hai order cạnh tranh cùng SKU/warehouse.
- Retry command với cùng idempotency key.
- Cùng key nhưng payload khác.
- Một order có nhiều SKU và một SKU không đủ hàng.

Kỳ vọng: invariant không bị phá; trạng thái reservation nhất quán.

### Broker và persistence

- Kafka partition rebalance.
- RabbitMQ redelivery.
- Consumer restart.
- Database failover.
- Retry queue/DLQ.
- Pending store hết capacity.
- Event schema cũ/mới.
- Replay từ checkpoint.

Kỳ vọng: không mất event đã commit, không side effect lặp và có alert khi không thể tự phục hồi.

## 36. Bài tập tình huống 1: sự kiện đến trễ sau khi reservation đã release

Một order giữ 3 đơn vị SKU-1 tại warehouse W1. Sau đó khách hủy đơn và Inventory Service release reservation. Do retry, consumer dashboard nhận InventoryReserved cũ sau InventoryReleased.

Dữ liệu giả định:

    Reservation R1:
      created event sequence 40
      released event sequence 41

    Dashboard last applied sequence = 41
    Late event sequence = 40

Câu hỏi:
1. Event 40 là duplicate hay stale? Cần dựa vào event ID, sequence hay cả hai?
2. Có nên cộng reserved thêm 3 không?
3. Nếu dashboard chỉ có delta event và chưa có sequence 41, phải làm gì?
4. Nếu reservation state canonical đã RELEASED, consumer projection phục hồi ra sao?
5. Test nào chứng minh event cũ không hồi sinh reservation?

Gợi ý: nếu last applied sequence đã là 41, event 40 không được áp lại. Nếu chuỗi chưa đầy đủ, không suy đoán từ trạng thái hiện tại; phát hiện gap, replay hoặc tải snapshot canonical có version. Reservation state machine phải ngăn RELEASED quay lại RESERVED do event cũ.

## 37. Bài tập tình huống 2: hai consumer cùng nhận duplicate

Một relay publish event InventoryReserved. Consumer A và B cùng nhận do cấu hình group/queue hoặc replay. Cả hai cùng cập nhật read model và gửi lệnh downstream.

Câu hỏi:
1. Inbox unique key nên gồm trường nào?
2. Vì sao SELECT rồi INSERT có race?
3. Inbox và projection update phải ở transaction nào?
4. Nếu downstream API đã thành công nhưng DB commit lỗi, xử lý ra sao?
5. Consumer group khác nhau có nên dùng chung consumer_name không?

Gợi ý: dedupe theo consumer identity + event ID cho mỗi business effect. Atomic insert với unique constraint quyết định winner. Local business state và inbox cùng transaction. Side effect ngoài cần idempotency key hoặc outbound outbox/reconciliation. Hai consumer độc lập có thể cần xử lý cùng event một lần mỗi consumer.

## 38. Bài tập tình huống 3: delta event bị thiếu

Projection đã xử lý sequence 100. Consumer nhận 103, nhưng 101 và 102 không đến do connector/broker retention.

Câu hỏi:
1. Có nên áp 103 rồi đánh dấu checkpoint 103?
2. Cách xác minh event 101/102 còn tồn tại?
3. Khi nào nên replay, khi nào tải snapshot?
4. Snapshot cần metadata nào để biết đã bao gồm những event nào?
5. Làm sao xử lý pending events sau snapshot?

Gợi ý: nếu delta phụ thuộc sequence, không áp 103 như thể chuỗi đầy đủ. Kiểm tra source log/outbox/archive và replay. Nếu không còn event, lấy snapshot canonical tại version/sequence rõ, thay projection nguyên tử rồi chỉ áp delta sau snapshot. Không xóa pending tùy tiện.

## 39. Bài tập tình huống 4: oversell khi nhiều request đồng thời

Tồn kho có 5 đơn vị. Hai order đồng thời yêu cầu reserve 4 đơn vị. Cả hai cùng SELECT available=5 trước khi UPDATE.

Câu hỏi:
1. Vì sao SELECT rồi UPDATE riêng lẻ có race?
2. Conditional update bảo vệ invariant ra sao?
3. Khi reserve nhiều SKU, cần transaction/locking policy nào?
4. Event InventoryReserved được ghi ở thời điểm nào?
5. Nếu client timeout nhưng reserve đã commit, retry thế nào?

Gợi ý: cập nhật có điều kiện trong database transaction, chỉ một request được affected row. Reservation record, command idempotency result và outbox event cùng commit. Retry cùng key trả lại kết quả đã biết, không reserve thêm.

## 40. Bài tập tình huống 5: snapshot mới và event cũ

Consumer đã tải InventorySnapshot version 80. Một event delta sequence 75 đến sau đó.

Câu hỏi:
1. Có thể bỏ event 75 không?
2. Điều gì cần chứng minh snapshot đã bao gồm event 75?
3. Nếu snapshot version 80 không có sequence mapping, xử lý thế nào?
4. Nếu event 81 tới ngay khi snapshot đang apply, tránh race ra sao?

Gợi ý: chỉ bỏ event cũ khi snapshot contract bảo đảm bao gồm toàn bộ thay đổi tới sequence tương ứng. Apply snapshot và checkpoint atomically; đồng bộ với consumer hoặc dùng staging/cutover để không mất event 81. Nếu không có metadata đủ, cần fetch snapshot có version rõ hoặc replay lại từ một checkpoint an toàn.

## 41. Bài tập tổng hợp: thiết kế Inventory event consumer

Một nền tảng có:
- Inventory Service sở hữu stock và reservation.
- Order Service phát ReserveInventory command.
- Kafka topic inventory.events có at-least-once delivery.
- Dashboard Service xây read projection.
- Warehouse adapter gửi StockReceived và StockAdjusted.
- Một SKU có thể được lưu ở nhiều warehouse.
- Consumer có thể chạy nhiều replica và event có thể retry/DLQ replay.

Yêu cầu:
1. Xác định aggregate boundary và partition key.
2. Thiết kế event envelope với eventId, aggregateVersion, eventSequence, occurredAt và causationId.
3. Định nghĩa event types và semantics snapshot/delta.
4. Thiết kế idempotency key cho ReserveInventory.
5. Thiết kế Inbox cho Dashboard và các consumer khác.
6. Quyết định event nào cần strict ordering, event nào chỉ cần latest snapshot.
7. Định nghĩa gap detection và pending event policy.
8. Thiết kế snapshot recovery và replay.
9. Thiết kế reservation state machine và atomic stock update.
10. Xử lý expire/release/consume race.
11. Định nghĩa retry, backoff, DLQ và replay permissions.
12. Tạo reconciliation giữa ledger, reservation và projection.
13. Thiết kế metrics và alerts.
14. Viết integration tests cho duplicate/out-of-order/late events.
15. Định nghĩa cách xử lý khi canonical Inventory DB sai hoặc bị mất dữ liệu.

Hướng giải tham khảo: InventoryPosition có key theo tenant/warehouse/SKU; Inventory Service là writer duy nhất. Reservation command có idempotency key và unique business constraint. Stock movement/outbox ghi cùng transaction. Event có ID và sequence. Dashboard dùng inbox và version-aware projection. Nếu delta gap, buffer/replay hoặc snapshot có sequence rõ. Reservation transitions conditional. Reconciliation so projection với canonical ledger, không dùng projection để sửa canonical.

## 42. Những sai lầm thường gặp

**“Broker bảo đảm exactly-once nên consumer không cần dedupe.”** Delivery và side effect database là hai ranh giới khác nhau.

**“Chỉ cần bỏ event có timestamp cũ.”** Clock skew và event-time semantics khiến timestamp không phải thứ tự canonical.

**“Event đến sau luôn mới hơn.”** Đến sau có thể là retry của event cũ.

**“Inbox theo event ID giải quyết mọi duplicate.”** Hai event ID khác nhau có thể cùng đại diện một command; cần business idempotency.

**“Version guard áp dụng giống nhau cho snapshot và delta.”** Snapshot có thể thay state; delta cần chuỗi đầy đủ hoặc replay.

**“Kafka partition key là đủ.”** Retry topic, consumer concurrency, partition migration và nhiều topic vẫn cần version/gap handling.

**“RabbitMQ giữ thứ tự nên không cần sequence.”** Redelivery, nhiều consumer và retry có thể đổi thứ tự hoàn tất.

**“Tăng consumer concurrency luôn tăng throughput an toàn.”** Có thể phá ordering, tăng DB contention và vượt capacity.

**“Retry ngay khi lỗi.”** Hot loop làm backlog và overload nặng hơn.

**“DLQ là nơi có thể bỏ qua.”** Message lỗi có thể đại diện movement nghiệp vụ chưa được áp dụng.

**“Projection sai thì sửa trực tiếp quantity.”** Projection cần rebuild từ source; canonical correction phải là adjustment có audit.

**“Reservation chỉ là phép trừ số lượng.”** Nó là state machine với các transition reserve, release, expire và consume.

**“Timeout nghĩa reserve thất bại.”** Inventory có thể đã commit trước khi response mất.

**“Snapshot không cần version.”** Không có version/sequence, không biết snapshot bao gồm những event nào.

**“Reconciliation chỉ cần so tổng quantity.”** Hai sai lệch có thể triệt tiêu nhau; cần so theo aggregate, movement, reservation và invariant.

## 43. Checklist triển khai

### Event contract
- Event ID duy nhất và ổn định qua retry?
- Aggregate ID/tenant/warehouse/SKU rõ?
- Schema version tách khỏi business version?
- Event type phân biệt command, event, snapshot và delta?
- occurredAt/publishedAt/consumedAt được dùng đúng mục đích?
- Sequence có semantics và phạm vi rõ?

### Consumer correctness
- Inbox unique và atomic?
- Inbox + business update cùng transaction?
- Ack/offset sau commit?
- Business idempotency key chống command lặp?
- Snapshot và delta có policy riêng?
- Gap detection, buffering/replay/snapshot?
- Reservation state machine và conditional transition?
- Concurrency/partition key phù hợp aggregate?

### Recovery and operations
- Retry có giới hạn/backoff/jitter?
- DLQ có owner, alert và replay procedure?
- Pending event có bound và timeout?
- Reconciliation so với canonical source?
- Snapshot có version/sequence và apply atomically?
- Metrics duplicate, stale, gap, lag và mismatch?
- Test crash sau commit trước ack?
- Test event trùng/late/out-of-order và race reservation?
- PII, tenant isolation và replay authorization được bảo vệ?

---

**Điểm cốt lõi:** Event tồn kho đến trễ, trùng hoặc sai thứ tự là tình huống bình thường cần được thiết kế trước trong hệ thống phân tán. Event ID và Inbox bảo vệ duplicate; idempotency key và business constraints bảo vệ command lặp; aggregate version/sequence phát hiện stale event và gap; snapshot, replay và reconciliation phục hồi projection; state machine và transaction/conditional update bảo vệ reservation và số lượng. Broker ordering giúp giảm một phần vấn đề nhưng không thay thế tính đúng đắn ở consumer. Inventory owner phải là nơi cuối cùng bảo vệ invariant, còn mọi consumer khác phải có khả năng xử lý lại message mà không tạo thêm tác động nghiệp vụ.
