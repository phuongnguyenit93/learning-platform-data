# Saga như chuỗi giao dịch cục bộ và hành động bù trừ

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices  
> **Nhóm kiến thức:** Giao dịch phân tán

## 1. Bài toán: một nghiệp vụ được thực thi bởi nhiều service

Trong kiến trúc microservices, mỗi service thường có database, transaction và quy tắc nghiệp vụ của riêng mình. Một hành trình đặt hàng lại đòi phối hợp nhiều service:

1. **Ordering** tạo đơn ở trạng thái PENDING.
2. **Inventory** giữ số lượng hàng cần bán.
3. **Payment** ủy quyền hoặc thu tiền.
4. **Ordering** xác nhận đơn.
5. **Shipping** tạo yêu cầu giao hàng sau khi đã đủ điều kiện.

Nếu mọi thay đổi nằm trong một database, một transaction ACID có thể thực hiện nhiều cập nhật rồi commit hoặc rollback nguyên tử. Nhưng khi Inventory đã commit reservation trong database của nó, một lệnh ROLLBACK của Ordering không thể tự động hoàn tác reservation. Nếu Payment từ chối sau bước giữ hàng, hệ thống có thể bị kẹt với hàng vẫn giữ và đơn chưa được xác nhận.

**Saga** là mẫu quản lý một quy trình nghiệp vụ dài bằng **chuỗi local transactions** ở những service khác nhau. Mỗi bước đã commit độc lập. Khi một bước không thể hoàn tất, hệ thống thực hiện **hành động bù trừ (compensating action)** hoặc một quy trình xử lý ngoại lệ để đưa các participant về một kết quả nghiệp vụ hợp lệ.

Điểm nền tảng: **Saga không tạo ra rollback ACID xuyên nhiều database**. Nó công khai trạng thái trung gian, chấp nhận nhiều commit độc lập và quản lý đường đi đến một kết quả cuối có thể quan sát, phục hồi và đối soát.

Ví dụ:

```text
T1 CreateOrder        -> COMMIT
T2 ReserveInventory   -> COMMIT
T3 AuthorizePayment   -> DECLINED
   |
   v
C2 ReleaseReservation -> COMMIT
C1 MarkOrderRejected  -> COMMIT
   |
   v
REJECTED
```

Trong mô hình này, compensation có thể không phải “trả mọi bit về trạng thái trước”, mà là một nghiệp vụ mới có audit và quy tắc riêng.

## 2. Local transaction và compensation khác nhau thế nào?

### 2.1. Local transaction

Local transaction là một chuỗi thay đổi trong phạm vi một tài nguyên transactional, ví dụ một database của Inventory. Nó bảo vệ invariant cục bộ như “không giữ hàng vượt số lượng khả dụng”.

Ví dụ SQL minh họa:

```sql
BEGIN;

UPDATE stock
SET available = available - 2,
    reserved = reserved + 2
WHERE sku = 'SKU-17'
  AND available >= 2;

-- Chỉ tiếp tục nếu UPDATE tác động đúng số hàng dự kiến.
INSERT INTO reservations (
    reservation_id, order_id, sku, quantity, state
) VALUES (
    'res-8042', 'ord-8042', 'SKU-17', 2, 'ACTIVE'
);

COMMIT;
```

Code thực tế phải kiểm tra affected-row count, concurrency, unique constraints và transaction isolation. Nếu không giữ được stock, transaction phải được xử lý nhất quán theo domain, không chỉ cố insert record rồi hy vọng giá trị đúng.

Một khi transaction đã commit, Inventory sở hữu sự thật rằng reservation tồn tại. Ordering hoặc Saga orchestrator chỉ có thể gọi **API/command công khai** để yêu cầu Inventory thực hiện một thao tác tiếp theo.

### 2.2. Compensation

Compensation là một hành động kinh doanh dùng để điều chỉnh tác động của bước trước:

| Bước đã commit | Compensation hoặc khắc phục có thể áp dụng | Giới hạn quan trọng |
| --- | --- | --- |
| ReserveInventory | ReleaseReservation | Chỉ release một reservation đang ACTIVE, không cộng stock lặp |
| AuthorizePayment | VoidAuthorization | Chỉ có thể void khi trạng thái và đối tác cho phép |
| CapturePayment | RefundPayment | Refund không phải rollback; có thể có phí, độ trễ, đối soát |
| CreateShipmentDraft | CancelShipmentDraft | Có thể không còn hợp lệ nếu hàng đã bàn giao |
| CreateOrder | MarkOrderCancelled/Rejected | Không xóa lịch sử giao dịch chỉ để “quay lại ban đầu” |
| SendNotification | Gửi đính chính nếu cần | Không bảo đảm thu hồi được email đã gửi |
| AllocateResource | DeallocateResource | Cần xác minh resource có đang được sử dụng không |

Một khoản hoàn tiền có thể mất vài ngày; một nhãn vận chuyển có thể đã được đối tác nhận; một email đã ra khỏi hệ thống. **Compensation không nhất thiết là hàm đảo ngược hoàn hảo.** Nó là một transaction mới, có thể bị từ chối, timeout hoặc cần phê duyệt thủ công.

### 2.3. Kết quả cuối phải được định nghĩa theo domain

Những trạng thái có thể là:

```text
COMPLETED
REJECTED
CANCELLED
COMPENSATED
COMPENSATION_PENDING
NEEDS_MANUAL_REVIEW
```

Không được đánh dấu COMPENSATED nếu RefundService mới chỉ nhận yêu cầu hoàn tiền mà chưa xác nhận đạt điều kiện nghiệp vụ cuối. Cũng không nên tự biến PENDING thành FAILED chỉ vì caller đã ngừng đợi.

## 3. Saga không có tính nguyên tử toàn cục

Giả sử flow:

```text
CreateOrder -> ReserveStock -> AuthorizePayment -> ConfirmOrder
```

Sau T2, một service khác có thể nhìn thấy Inventory đã giữ hàng trong lúc Ordering vẫn PENDING. Dữ liệu reservation này đã được commit thực sự, không phải dirty read SQL. Nhưng đó là **trạng thái trung gian của nghiệp vụ**.

Hệ thống phải trả lời:

- Client có được thấy order PENDING không?
- Một email “đơn đã xác nhận” được gửi sau bước nào?
- Shipping có được giao hàng khi order mới PENDING_PAYMENT không?
- Có được hủy reservation khi payment chưa có kết quả chắc chắn không?
- Các quy tắc số lượng tồn kho được bảo vệ bằng local transaction nào?
- Khi một bước sau commit thất bại, trạng thái nào còn hợp lệ?

Saga thường đạt **eventual consistency của toàn quy trình**, chứ không đảm bảo các service cùng phản ánh một trạng thái cuối ngay lập tức. Một ứng dụng cần ACID mạnh cho một invariant rất nhỏ có thể nên đặt các thành phần dữ liệu liên quan trong **cùng bounded context hoặc database**, thay vì tách quá vụn rồi dùng Saga để sửa hậu quả.

## 4. So sánh Saga với những phương án khác

| Phương án | Cơ chế | Khi cân nhắc |
| --- | --- | --- |
| Local ACID | Commit/rollback trong một database | Những bất biến cần thay đổi nguyên tử có cùng owner |
| 2PC/XA | Prepare rồi commit nhiều tài nguyên hỗ trợ distributed transaction | Hạ tầng cho phép; chấp nhận coupling và rủi ro về availability/liveness |
| Saga | Các local commits và compensations | Business transaction dài, nhiều owner độc lập |
| TCC (Try–Confirm–Cancel) | Reserve/try rồi confirm hoặc cancel | Participant được thiết kế API giữ tài nguyên và xử lý expiration |
| Outbox | Ghi domain state và intent phát message trong cùng local transaction | Giảm cửa sổ “đã commit nhưng event bị mất” |
| Read projection | Sao chép dữ liệu để đọc nhanh sau event | Truy vấn liên dịch vụ, không thay thế workflow thay đổi trạng thái |

Saga không nhất thiết tốt hơn 2PC trong mọi điều kiện; đó là một mô hình đánh đổi khác. TCC có nét liên quan Saga nhưng yêu cầu các participants hỗ trợ giao thức Try/Confirm/Cancel. Outbox giải quyết một phần reliability của message, không tự quản lý toàn bộ flow compensation.

## 5. Xác định bất biến nghiệp vụ trước khi vẽ Saga

Một thiết kế checkout có thể có các bất biến:

1. Không giao hàng nếu Order chưa đạt điều kiện CONFIRMED.
2. Một ý định thanh toán của một đơn không bị capture hai lần.
3. Inventory không cho phép số lượng available âm.
4. Một reservation ACTIVE có thời hạn, owner và đường RELEASE/CONSUME/EXPIRE rõ ràng.
5. Người dùng có thể tra cứu một đơn PENDING thay vì phải gửi lại với ID mới.
6. Khi đã capture tiền nhưng không thể giao hàng, có đường hoàn tiền và đối soát.
7. History của Payment/Accounting vẫn được giữ khi compensation chạy.

Chính các bất biến này quyết định thứ tự bước. Ví dụ, giữ hàng trước authorize có thể tránh thu tiền khi hoàn toàn không có hàng, nhưng đồng thời tạo chi phí reservation trong lúc Payment chậm. Capture trước hay sau shipping draft lại có các rủi ro riêng.

**Thiết kế dựa trên business outcome và chi phí side effect, không chỉ dựa trên “service nào đang có REST endpoint”.**

## 6. State machine cho một Saga đặt hàng

Một state machine minh họa:

```text
NEW
 |
 v
ORDER_PENDING
 |
 v
RESERVATION_REQUESTED
 | InventoryReserved
 v
STOCK_RESERVED
 |
 v
PAYMENT_REQUESTED
 | PaymentAuthorized           | PaymentDeclined
 v                             v
CONFIRM_ORDER              RELEASE_RESERVATION
 |                             |
 v                             v
COMPLETED                   MARK_ORDER_REJECTED
                               |
                               v
                            REJECTED
```

Ngoài happy path và declined path, cần các trạng thái:

```text
PAYMENT_OUTCOME_UNKNOWN
RETRY_SCHEDULED
CANCELLATION_REQUESTED
COMPENSATION_PENDING
COMPENSATION_FAILED
MANUAL_REVIEW
```

State machine phải có **guards**:

- Không chuyển PAYMENT_REQUESTED sang CONFIRMED nếu payment outcome chưa được xác minh.
- Không chuyển REJECTED thành COMPLETED do một reply đến trễ.
- Nếu cancellation đã được chấp nhận, payment reply đến sau phải đi theo quy trình đối soát.
- Khi compensation đang chạy, không lặp lại chính lệnh side effect với một idempotency key mới.
- Một event được xử lý lại không được tạo ra step mới nhiều lần.

Saga state machine và state của từng aggregate không giống nhau. Saga có thể COMPENSATION_PENDING trong khi Inventory đã RELEASED còn Payment vẫn REFUND_PENDING.

## 7. Choreography Saga

Trong **choreography**, các service phản ứng với integration event của nhau:

```text
Ordering
  | OrderPlaced
  v
Inventory
  | InventoryReserved
  v
Payment
  | PaymentAuthorized
  v
Ordering
  | OrderConfirmed
  v
Shipping

PaymentDeclined
  |------> Inventory releases reservation
  '--> Ordering marks order rejected
```

Không có một coordinator duy nhất phát command cho mọi bước. Ưu điểm là mô hình tương đối đơn giản cho các flow ít bước và event có ý nghĩa rõ. Mỗi service chỉ cần biết sự kiện nó quan tâm, và có thể triển khai phần xử lý của mình.

Đánh đổi:

- Logic tổng thể trải trên nhiều codebase.
- Một event có thể kích hoạt nhiều listener và những nhánh bù trừ khó quan sát.
- Khi thêm bước mới, nhiều consumer có thể phải thay đổi hành vi.
- Event đến trễ, lặp hoặc sai thứ tự dễ gây vòng phản hồi.
- Không có một nơi hiển nhiên trả lời “Saga hiện đang ở bước nào?” nếu không có tracking riêng.
- Các bounded context có thể bị coupling bằng các event đặt tên theo lệnh thay vì business fact.

Dùng choreography không có nghĩa hệ thống không cần ownership của workflow. Phải xác định ai chịu trách nhiệm báo outcome cuối, ai theo dõi thất bại kéo dài và khi nào một Saga được coi là kết thúc.

## 8. Orchestration Saga

Trong **orchestration**, một process manager theo dõi toàn bộ flow và gửi command có chủ đích:

```text
                    OrderSagaOrchestrator
                    /       |         \
                   /        |          \
             Ordering    Inventory     Payment
                |           |            |
                +------ step results -----+
```

Ví dụ:

```text
START
  -> CreateOrder
  -> ReserveInventory
  -> AuthorizePayment
  -> ConfirmOrder
  -> COMPLETED

Nếu PaymentDeclined:
  -> ReleaseInventory
  -> MarkOrderRejected
  -> REJECTED
```

Orchestrator có durable state:

```json
{
  "sagaId": "saga-8042",
  "orderId": "ord-8042",
  "state": "AUTHORIZING_PAYMENT",
  "completedSteps": [
    "CREATE_ORDER",
    "RESERVE_INVENTORY"
  ],
  "reservationId": "res-8042",
  "lastTransitionAt": "2026-11-11T09:02:00Z"
}
```

Ưu điểm: nhìn rõ state machine và compensation, tập trung scheduling, timeout, retry, báo cáo tiến độ. Đánh đổi: orchestrator cần durability, HA, idempotency, versioning và không nên trở thành nơi sao chép toàn bộ business logic của các participants.

**Orchestrator điều phối, không trực tiếp UPDATE database của Payment hoặc Inventory.** Participant vẫn sở hữu business invariant và tự thực hiện local transaction của mình.

### 8.1. Choreography hay orchestration?

| Tiêu chí | Choreography | Orchestration |
| --- | --- | --- |
| Flow ít bước, ít nhánh | Thường gọn | Có thể tạo coordinator không cần thiết |
| Nhiều bước/điều kiện/timeout | Khó theo dõi toàn bộ | Dễ hiện thực state machine |
| Compensation phức tạp | Phân tán qua handlers | Tập trung flow và trạng thái |
| Coupling | Qua event semantics | Qua command/result contracts |
| Recovery | Cần state/observability phân tán | Coordinator giữ durable state |
| Thêm business branch | Có thể đụng nhiều consumer | Có thể sửa process manager và contract |
| Điểm lỗi | Trải trên các consumers và broker | Coordinator phải resilient |

Cả hai đều có thể đúng. Một hệ thống có thể orchestration cho checkout, còn các tác vụ hậu xử lý như analytics hoặc notification chạy theo choreography sau OrderConfirmed.

## 9. Bước compensatable, retryable và pivot

**Compensatable step:** một local transaction có hành động nghiệp vụ bù trừ đã được định nghĩa, ví dụ ReserveInventory → ReleaseReservation.

**Retryable step:** thao tác được thiết kế để thử lại an toàn với idempotency, không lặp side effect. Một lời gọi POST không mặc nhiên retryable chỉ vì nó thất bại với HTTP 503.

**Pivot step:** một điểm cam kết quan trọng hoặc không thể bù trừ theo cách thông thường. Sau pivot, hệ thống cần tập trung hoàn tất các bước có thể retry hoặc kích hoạt quy trình xử lý đặc biệt.

Ví dụ, khi một kiện hàng đã thực sự được hãng vận chuyển nhận, CancelShipmentDraft không còn là phép bù trừ hợp lý. Có thể phải yêu cầu thu hồi hoặc hoàn trả hàng. Nếu đã gửi email, không có công nghệ nào đảm bảo “gửi lệnh hủy email” sẽ thu hồi tin từ hộp thư người nhận.

Cần cố gắng đặt những side effects khó đảo ngược **sau** khi các điều kiện cần thiết đã thỏa, trừ khi doanh nghiệp chấp nhận rõ ràng rủi ro, phí và quy trình đối soát.

## 10. Mô hình command và event cho Saga

**Command** yêu cầu một service thực hiện việc gì; **event** báo điều đã xảy ra.

| Command | Event/result có thể phát |
| --- | --- |
| CreateOrder | OrderCreated / OrderCreateRejected |
| ReserveInventory | InventoryReserved / InventoryReservationRejected |
| AuthorizePayment | PaymentAuthorized / PaymentDeclined |
| ConfirmOrder | OrderConfirmed / OrderConfirmationRejected |
| ReleaseReservation | InventoryReservationReleased / ReleaseFailed |
| VoidAuthorization | PaymentAuthorizationVoided / VoidFailed |

Ví dụ command giữ hàng:

```json
{
  "messageId": "cmd-8042-reserve-a",
  "messageType": "inventory.reserve",
  "schemaVersion": 1,
  "sagaId": "saga-8042",
  "orderId": "ord-8042",
  "idempotencyKey": "ord-8042:reserve",
  "issuedAt": "2026-11-11T09:00:00Z",
  "data": {
    "items": [
      {"sku": "SKU-17", "quantity": 2}
    ]
  }
}
```

Kết quả:

```json
{
  "eventId": "evt-8042-inventory-reserved",
  "eventType": "inventory.reserved",
  "schemaVersion": 1,
  "sagaId": "saga-8042",
  "causationId": "cmd-8042-reserve-a",
  "orderId": "ord-8042",
  "occurredAt": "2026-11-11T09:00:01Z",
  "data": {
    "reservationId": "res-8042",
    "state": "ACTIVE"
  }
}
```

Ý nghĩa:

- **sagaId:** nhận diện một workflow.
- **messageId/eventId:** nhận diện một publication/message để dedup.
- **idempotencyKey:** nhận diện business intent cần tránh side effect lặp.
- **causationId:** liên hệ result với command trước.
- **schemaVersion:** giúp quản lý sự phát triển của message.
- **business IDs:** giúp participant kiểm tra trạng thái và đối soát theo nguồn authoritative.

Không lấy một UUID mới ở mỗi retry làm idempotency key cho cùng ý định. Cũng không nhét toàn bộ ORM object hoặc thông tin nhạy cảm vào message chỉ vì tiện serialization.

## 11. Kết quả lỗi nghiệp vụ và kết quả chưa biết

Không gộp mọi thất bại vào một trạng thái FAILED.

| Trường hợp | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| Inventory hết hàng | Từ chối nghiệp vụ chắc chắn | Mark order rejected, bù trừ các bước đã thành công nếu cần |
| Payment từ chối có kết quả chắc chắn | Declined | Release inventory, reject order |
| Payment timeout sau khi gửi command | Outcome **chưa biết** | Query/reconcile theo key trước khi quyết định |
| Broker ngắt kết nối ngắn | Lỗi tạm thời | Retry có giới hạn, durable queue/outbox |
| Message không hợp schema | Lỗi contract/poison message | Quarantine/DLQ, cảnh báo; không retry vô hạn |
| Compensation timeout | Kết quả compensation có thể chưa rõ | Tra cứu, retry cùng key, giữ pending state |
| Không đủ quyền gọi service | Lỗi bảo mật/chính sách | Dừng, điều tra; không bypass authorization |

Một timeout chỉ có nghĩa bên gọi **không nhận được kết quả đúng hạn**, chứ không chứng minh bên nhận chưa commit.

### 11.1. Một tình huống payment timeout

```text
Orchestrator                     Payment
     | AuthorizePayment             |
     |----------------------------->|
     |                              | COMMIT AUTHORIZED
     |                              |
     |<---------- reply mất --------X
     |
     | Timeout
     v
AUTHORIZATION_OUTCOME_UNKNOWN
```

Nếu orchestrator vội tạo authorization khác với key mới, có nguy cơ tạo giao dịch trùng. Cách an toàn hơn:

1. Lưu durable state UNKNOWN.
2. Query Payment bằng payment reference hoặc idempotency key.
3. Nếu đã AUTHORIZED, tiếp tục hoặc bù trừ tùy Saga state hiện tại.
4. Nếu chắc chắn DECLINED, thực hiện nhánh từ chối.
5. Nếu vẫn UNKNOWN, retry query có backoff và thời hạn; escalate khi vượt SLA.

Điều này quan trọng đối với thanh toán, xuất hàng và các API bên thứ ba.

## 12. Transactional outbox: không mất event khi local transaction đã commit

Một cửa sổ lỗi phổ biến:

```text
1. Inventory commit Reservation ACTIVE.
2. Inventory định publish InventoryReserved.
3. Process crash trước khi publish.
4. Orchestrator không nhận được event.
```

Một cơ chế phổ biến là **transactional outbox**. Trong cùng local DB transaction, service thực hiện business change và ghi thông điệp sẽ phát:

```sql
BEGIN;

-- Cập nhật stock và tạo reservation atomically.
UPDATE stock
SET available = available - 2,
    reserved = reserved + 2
WHERE sku = 'SKU-17' AND available >= 2;

INSERT INTO reservations (
  reservation_id, order_id, sku, quantity, state
) VALUES (
  'res-8042', 'ord-8042', 'SKU-17', 2, 'ACTIVE'
);

INSERT INTO outbox_events (
  event_id, event_type, aggregate_id, payload, created_at
) VALUES (
  'evt-8042-inventory-reserved',
  'inventory.reserved',
  'res-8042',
  '{...}',
  CURRENT_TIMESTAMP
);

COMMIT;
```

SQL chỉ mô tả mô hình, chưa xử lý đầy đủ affected rows, constraints và race. Sau commit, một publisher riêng đọc outbox và phát message; có thể dùng polling hoặc CDC phù hợp.

**Outbox không tự cho exactly-once effect.** Nếu broker nhận event nhưng publisher crash trước khi lưu trạng thái đã publish, event có thể được phát lại. Consumer và handler phải idempotent.

### 12.1. Outbox ở orchestrator

Khi state machine chuyển từ STOCK_RESERVED sang PAYMENT_REQUESTED, durable state update và ý định gửi AuthorizePayment cần liên kết transactionally. Nếu chỉ lưu state rồi gửi message bên ngoài transaction, crash giữa hai bước có thể làm Saga kẹt.

### 12.2. Inbox/dedup ở participant

Participant có thể ghi processed-command/business key cùng transaction thay đổi state. Khi command lặp, nó trả cùng kết quả đã xác nhận hoặc một kết quả tương đương theo contract.

Nếu ack message trước commit, crash có thể làm mất xử lý. Nếu commit rồi crash trước ack, message có thể được giao lại. Vì vậy idempotency không phải tùy chọn chỉ để “tối ưu”; nó là phần cơ bản của delivery thực tế.

## 13. Idempotency của command và compensation

Một command giữ hàng có thể đến hai lần:

```text
ReserveInventory(orderId=8042, quantity=2, key=K)
ReserveInventory(orderId=8042, quantity=2, key=K)
```

Kết quả mong muốn: **một reservation**, không phải giữ 4 sản phẩm. Participant có thể lưu key K với unique constraint và kết quả; nhận lại K thì tra state đã commit.

Compensation cũng phải chịu lặp. Giả sử ReleaseReservation được gửi hai lần:

```text
ACTIVE -> RELEASED  (lần thứ nhất: hoàn stock)
RELEASED -> RELEASED (lần thứ hai: no-op hoặc trả ALREADY_RELEASED)
```

Không viết handler cộng stock vô điều kiện cho mọi lần nhận ReleaseReservation.

### 13.1. SQL minh họa cho release

```sql
BEGIN;

-- Khóa reservation hoặc dùng conditional update bảo vệ state.
SELECT state, sku, quantity
FROM reservations
WHERE reservation_id = 'res-8042'
FOR UPDATE;

-- Chỉ nếu state=ACTIVE:
UPDATE reservations
SET state = 'RELEASED'
WHERE reservation_id = 'res-8042'
  AND state = 'ACTIVE';

-- Chỉ hoàn lại số lượng khi chuyển ACTIVE -> RELEASED thành công.
UPDATE stock
SET available = available + 2,
    reserved = reserved - 2
WHERE sku = 'SKU-17';

COMMIT;
```

Đoạn mã phải được hiện thực với điều kiện của transaction để lệnh UPDATE stock không chạy khi reservation đã RELEASED hoặc không tồn tại. SQL ở đây minh họa ý tưởng và cần được đặt trong logic application kiểm tra state/affected rows.

### 13.2. Idempotency key cần chính sách

- Key gắn với scope nào (tenant, order, payment)?
- Key có thời hạn lưu bao lâu?
- Cùng key nhưng payload khác thì trả CONFLICT hay lỗi tương đương?
- Nếu operation đang PENDING và nhận lại request, trả trạng thái nào?
- Làm sao kiểm tra kết quả nếu key đã hết hạn?
- Có thể bảo đảm không nhân đôi tác dụng phụ ở provider ngoài không?

Idempotency cần được thực thi ở participant owner, không chỉ gateway. Gateway có thể phát lại request vì không nhận được response, nhưng nó không có khả năng tự biết Payment đã commit hay chưa.

## 14. Saga state và participant state phải được lưu bền

Một orchestrator nên lưu trạng thái và step history đủ để restart tiếp tục đúng nơi:

```sql
CREATE TABLE saga_instances (
    saga_id       VARCHAR(64) PRIMARY KEY,
    business_key  VARCHAR(128) NOT NULL,
    saga_type     VARCHAR(64) NOT NULL,
    state         VARCHAR(64) NOT NULL,
    version       BIGINT NOT NULL,
    updated_at    TIMESTAMP NOT NULL
);

CREATE TABLE saga_steps (
    saga_id       VARCHAR(64) NOT NULL,
    step_name     VARCHAR(64) NOT NULL,
    execution_id  VARCHAR(128) NOT NULL,
    state         VARCHAR(64) NOT NULL,
    attempts      INT NOT NULL,
    last_error    TEXT,
    PRIMARY KEY (saga_id, step_name, execution_id)
);
```

Tùy flow, cần thêm deadline, next retry time, compensation attempts, business refs và metadata. Không lưu raw token, PII hoặc toàn bộ provider response không cần thiết trong Saga payload.

### 14.1. Optimistic concurrency cho state transition

Nếu hai worker cùng nhận PaymentAuthorized, cả hai có thể cố chuyển Saga sang CONFIRMING_ORDER. Dùng guarded update/version:

```sql
UPDATE saga_instances
SET state = 'CONFIRMING_ORDER',
    version = version + 1
WHERE saga_id = 'saga-8042'
  AND state = 'AUTHORIZING_PAYMENT'
  AND version = 8;
```

Chỉ worker cập nhật được đúng một dòng mới có quyền phát intent kế tiếp. Worker còn lại tải lại state và xử lý duplicate/out-of-order, không gửi thêm ConfirmOrder theo key mới.

### 14.2. Late events sau terminal state

PaymentAuthorized có thể đến sau khi user cancel và Saga đánh dấu CANCELLATION_REQUESTED. Không được tự chuyển CANCELLED → COMPLETED. Phải đối chiếu authoritative Payment state và xem có cần void hoặc refund.

**Một event đúng nhưng đến trễ vẫn có thể làm state transition sai**, vì vậy cần kiểm tra state và version thay vì chỉ dựa vào event type.

## 15. Race condition, reservation expiration và cancellation

Xét timeline:

```text
T0 ReserveInventory success.
T1 AuthorizePayment command sent.
T2 Người dùng yêu cầu CancelOrder.
T3 Inventory reservation hết hạn.
T4 PaymentAuthorized event đến.
```

Một thiết kế ngây thơ có thể xác nhận đơn sau T4 dù hàng không còn được giữ.

Cần quy tắc rõ:

1. CancelOrder được chấp nhận ở state nào?
2. Nếu đang PAYMENT_PENDING, chuyển CANCELLATION_REQUESTED hay CANCELLED ngay?
3. Khi reservation EXPIRED, có được confirm order không? Thường cần xác minh lại.
4. Nếu Payment đã AUTHORIZED, void hay refund tùy trạng thái thực?
5. Nếu cả user cancel và PaymentAuthorized đến cùng lúc, guard nào quyết định transition duy nhất?
6. Khi đã giao hàng, cancellation có trở thành return/refund workflow riêng không?

Một Saga có thể sử dụng **semantic lock**, tức đặt order ở PENDING/CANCELLATION_REQUESTED để ngăn những thao tác khác xử lý như thể order đã confirmed. Đây là quy tắc trạng thái nghiệp vụ, không phải khóa database giữ nhiều phút xuyên service.

## 16. Bù trừ có thể thất bại và cần hoàn tất có kiểm soát

```text
PaymentDeclined
    |
    v
ReleaseInventory
    |
    +-- Success -> MarkOrderRejected -> REJECTED
    |
    '-- Timeout/Failure
            |
            v
     COMPENSATION_PENDING
            |
            +--> retry with same key
            +--> reconciliation
            '--> manual review if exceeds SLA
```

Không đủ nếu handler chỉ ghi log rồi bỏ qua thất bại. Compensation cần:

- Durable state nêu bước đang chờ.
- Retry scheduler bền vững, backoff và jitter.
- Idempotency key giữ ổn định.
- Quota/rate limit để không làm sập participant.
- Cơ chế truy vấn authoritative outcome khi timeout.
- Alert khi thời gian chờ vượt SLA.
- Quy trình manual review với quyền và audit trail.
- Trạng thái terminal chỉ khi đã đạt điều kiện business.

Ví dụ Payment capture đã xảy ra nhưng Shipping không thể giao. Refund có thể nằm ở REFUND_PENDING nhiều giờ hoặc ngày. Saga không nên báo COMPENSATED cho đến khi những điều kiện cuối được định nghĩa đã đạt, hoặc báo một trạng thái khác phản ánh trách nhiệm còn tồn tại.

## 17. Compensation phải biết thứ tự phụ thuộc

Trong ví dụ đơn giản, các compensation được mô tả theo thứ tự ngược:

```text
T1 -> T2 -> T3
          T3 fails
     C2 -> C1
```

Nhưng không phải mọi workflow nên tự đảo ngược danh sách một cách máy móc.

Ví dụ:

```text
T1 ReserveInventory
T2 AuthorizePayment
T3 CreateShipmentDraft
```

Nếu T3 thất bại, VoidAuthorization và ReleaseInventory có thể độc lập. Nếu shipment đã bắt đầu được vận chuyển, hủy shipment có thể cần đối tác xác nhận trước khi quyết định refund hoặc giải phóng một số tài nguyên. Những bước có thể chạy song song khi **business invariant** cho phép, nhưng khi có phụ thuộc phải giữ thứ tự.

Không gửi hàng loạt compensation chỉ để tối ưu latency rồi hy vọng eventual consistency tự giải quyết.

## 18. Phát triển Saga khi đang có nhiều phiên bản chạy

Trong rolling deployment, một orchestrator v2 có thể nhìn thấy Saga được tạo bởi code v1. Event lịch sử cũng có thể được replay. Cần quản lý:

- Version của Saga definition/state machine.
- Schema version của command/result event.
- Participant có hỗ trợ command v1 và v2 trong thời gian chuyển tiếp không?
- Một Saga đang chạy theo flow v1 có nên bị chuyển sang flow v2 không?
- Dữ liệu bước mới bắt buộc có tồn tại trong Saga đã khởi tạo từ trước không?
- Có thể rollback orchestrator sau khi đã phát command phiên bản mới không?

Một phương án là **pin Saga instance với definition version** cho tới khi kết thúc, hoặc có migration state đã được kiểm chứng. Không tự động chạy mọi Saga dở dang bằng state machine mới nếu các business meanings và compensation thay đổi.

Khi xóa field hoặc đổi nghĩa enum, cần xem tất cả participant và outbox messages chưa được xử lý. Schema registry có thể bắt một số lỗi cấu trúc nhưng không hiểu “PaymentAuthorized” có được dùng để giao hàng hay chưa.

## 19. Saga chạy song song những bước độc lập

Không phải Saga nào cũng tuyến tính. Nếu các điều kiện nghiệp vụ cho phép:

```text
                 +--> ReserveInventory --+
CreateOrder -----|                      +--> ConfirmOrder
                 +--> ValidateVoucher --+
```

Nếu ValidateVoucher thất bại nhưng ReserveInventory đã commit, cần ReleaseInventory. Nếu ReserveInventory timeout, kết quả có thể UNKNOWN và phải query trước khi quyết định bù trừ. Nếu hai reply đến theo thứ tự ngược, orchestrator phải lưu **per-step result** và chỉ chuyển khi tất cả điều kiện cần thiết đã đạt.

Đừng để một reply duplicate được tính là hai bước thành công. Không tính “đã nhận 2 messages” là đủ nếu cả hai đều là cùng một event.

Một Saga song song có thể phải ghi rõ dependency graph của compensation và trạng thái của mỗi nhánh. Đó là lý do durable per-step tracking rất quan trọng.

## 20. Mã giả của Saga orchestrator

```text
startOrderSaga(request):
    validateRequestAndAuthorization(request)
    saga = createDurableSaga(request.idempotencyKey)
    saveOutboxCommand(CreateOrder(saga.id, request))
    return PendingResponse(saga.id)

onStepResult(message):
    if messageAlreadyProcessed(message.id):
        acknowledgeAndReturn()

    saga = loadAndLockSaga(message.sagaId)

    if message == OrderCreated and saga.state == WAITING_ORDER:
        persistTransition(saga, RESERVING_INVENTORY)
        appendOutbox(ReserveInventory(saga.id, orderId))

    else if message == InventoryReserved and
            saga.state == RESERVING_INVENTORY:
        saveReservationId(message.reservationId)
        persistTransition(saga, AUTHORIZING_PAYMENT)
        appendOutbox(AuthorizePayment(saga.id, paymentIntent))

    else if message == PaymentAuthorized and
            saga.state == AUTHORIZING_PAYMENT:
        savePaymentId(message.paymentId)
        persistTransition(saga, CONFIRMING_ORDER)
        appendOutbox(ConfirmOrder(saga.id, orderId))

    else if message == PaymentDeclined and
            saga.state == AUTHORIZING_PAYMENT:
        persistTransition(saga, RELEASING_INVENTORY)
        appendOutbox(ReleaseInventory(saga.id, reservationId))

    else if message == InventoryReleased and
            saga.state == RELEASING_INVENTORY:
        persistTransition(saga, MARKING_REJECTED)
        appendOutbox(MarkOrderRejected(saga.id, orderId))

    else:
        classifyDuplicateStaleOrUnexpected(message, saga)

    recordProcessedMessage(message.id)
    commitLocalTransaction()
    acknowledgeBrokerMessage()
```

Đây là **pseudocode**, không phải code copy chạy được. Các thao tác persist transition, inbox/dedup và outbox command cần được thực thi trong transaction phù hợp, có version/guard để chống concurrency. Acknowledge message quá sớm có thể mất work; acknowledge sau commit có thể gây redelivery nên vẫn cần idempotency.

Một implementation đầy đủ phải có timeout watcher, trạng thái UNKNOWN, compensation retries, compensation history, cancellation branch và đường đối soát.

## 21. Ví dụ Java/Spring: local transaction và outbox

Dưới đây là mô phỏng một handler giữ hàng. Các repository và DTO chỉ là interface giả định; cần thêm kiểm tra concurrency, unique constraints và transaction behavior trước khi dùng production.

```java
@Service
public final class InventoryHandler {
    private final StockRepository stocks;
    private final ReservationRepository reservations;
    private final OutboxRepository outbox;

    public InventoryHandler(
            StockRepository stocks,
            ReservationRepository reservations,
            OutboxRepository outbox) {
        this.stocks = stocks;
        this.reservations = reservations;
        this.outbox = outbox;
    }

    @Transactional
    public ReservationResult reserve(ReserveInventory command) {
        var previous = reservations.findByBusinessKey(
            command.idempotencyKey());

        if (previous.isPresent()) {
            return ReservationResult.from(previous.get());
        }

        boolean success = stocks.tryReserveAtomically(
            command.sku(), command.quantity());

        if (!success) {
            outbox.save(InventoryRejectedEvent.from(command));
            return ReservationResult.rejected("OUT_OF_STOCK");
        }

        var reservation = Reservation.active(
            command.reservationId(), command.orderId(),
            command.sku(), command.quantity(),
            command.idempotencyKey());

        reservations.save(reservation);
        outbox.save(InventoryReservedEvent.from(reservation, command));

        return ReservationResult.reserved(reservation.id());
    }
}
```

Vấn đề cần xử lý khi làm thật:

- Hai thread có thể cùng quan sát không tìm thấy key. Phải có unique constraint và xử lý conflict khi insert.
- Stock update phải bảo đảm không âm dưới cạnh tranh.
- Outbox cùng database/transaction với reservation.
- Khi một business key đã tồn tại nhưng payload khác, cần trả conflict có ý nghĩa.
- Nếu trả reject, xác định result có được lưu để retry cùng key không.
- Handler gọi từ broker/HTTP phải đảm bảo idempotency xuyên cả các attempt.

### 21.1. Compensation handler

```java
@Transactional
public ReleaseResult release(ReleaseInventory command) {
    var reservation = reservations
        .findByIdForUpdate(command.reservationId())
        .orElse(null);

    if (reservation == null) {
        return ReleaseResult.notFoundOrAlreadyGone();
    }

    if (reservation.state() == ReservationState.RELEASED) {
        return ReleaseResult.alreadyReleased();
    }

    if (reservation.state() != ReservationState.ACTIVE) {
        return ReleaseResult.conflict(reservation.state());
    }

    reservation.release();
    stocks.restoreReservation(
        reservation.sku(), reservation.quantity());
    outbox.save(InventoryReservationReleasedEvent.from(
        command, reservation));

    return ReleaseResult.released();
}
```

Chỉ tăng stock khi chuyển ACTIVE → RELEASED trong cùng transaction. Với state CONSUMED hoặc EXPIRED, compensation có thể phải đi nhánh khác. Không tự động coi NOT_FOUND là “đã release thành công” nếu domain cần xác minh tồn tại trước đó.

## 22. API và UX khi Saga còn đang chạy

Một request đặt hàng có thể được ghi nhận bền vững rồi trả:

```http
HTTP/1.1 202 Accepted
Location: /order-operations/saga-8042
Content-Type: application/json
```

```json
{
  "operationId": "saga-8042",
  "orderId": "ord-8042",
  "status": "PENDING"
}
```

202 có nghĩa đã **tiếp nhận theo hợp đồng**, không phải đã thu tiền hoặc xác nhận đơn. Client có thể:

```text
GET /order-operations/saga-8042
```

để xem PENDING, COMPLETED, CANCELLED, COMPENSATION_PENDING hoặc trạng thái khác đã được công bố. Trong một số use case, API có thể trả kết quả synchronous nếu mọi bước hoàn tất trong deadline, nhưng khi caller timeout phải có cách nhận diện đúng operation thay vì tạo Saga mới mỗi lần.

Khi một bước còn UNKNOWN, UI không hiển thị “thanh toán thất bại” hoặc “đã thành công” theo suy đoán. Có thể hiển thị “đang xác minh kết quả” và đưa người dùng vào luồng kiểm tra trạng thái.

Mọi endpoint đọc Saga state cần kiểm tra quyền theo tenant/user; biết saga ID không mặc nhiên được phép đọc dữ liệu thanh toán hoặc thông tin cá nhân.

## 23. Saga không nhất thiết dùng một kết nối HTTP dài

Một Saga có thể kéo dài phút, giờ hoặc lâu hơn; request HTTP của client không nên bị giữ suốt thời gian đó.

Khả năng triển khai:

- API ghi nhận intent bằng local transaction.
- Worker/coordinator đọc outbox/queue và bắt đầu steps.
- Process manager lưu Saga state sau từng transition.
- Client polling status endpoint, nhận webhook hoặc cập nhật qua push.
- Timeout HTTP chỉ giới hạn thời gian chờ response, không chấm dứt durable workflow.
- Mọi business action vẫn cần idempotency.

Với một Saga dài, giữ transaction database mở qua các lời gọi mạng là một thiết kế nguy hiểm: khóa lâu, cạn connection, deadlock và rollback khó dự đoán. Local DB transactions nên đủ ngắn và chỉ bảo vệ thay đổi cục bộ phù hợp.

## 24. Reconciliation: đối soát khi hệ thống không chắc chắn

Không thể dựa hoàn toàn vào việc “nếu event delivery ổn thì Saga tự đúng”. Cần một cơ chế phát hiện và sửa workflow kẹt:

```text
Saga state: PAYMENT_OUTCOME_UNKNOWN
Payment:    AUTHORIZED
Inventory:  ACTIVE
Order:      PENDING
```

Reconciliation worker có thể:

1. Tìm Saga quá hạn tại một state.
2. Truy vấn participant theo ID/idempotency key.
3. So sánh authoritative state với state của orchestrator.
4. Phân loại duplicate, missing event, stale state, pending compensation.
5. Chọn bước tiếp theo hợp lệ theo state machine.
6. Lưu intent command trong outbox; retry an toàn.
7. Escalate những trường hợp không tự xử lý được.
8. Ghi lịch sử quyết định và evidence.

Ví dụ nếu Payment đã AUTHORIZED nhưng Saga đã bị người dùng hủy, không tự ConfirmOrder; có thể phải VoidAuthorization và ReleaseReservation. Nếu Payment đã CAPTURED, có thể cần RefundPayment và quy trình đối soát.

### 24.1. Manual review phải có người chịu trách nhiệm

Một case thủ công nên chứa sagaId, order/payment/reservation IDs, trạng thái từng bước, các command đã gửi, kết quả authoritative, lý do kẹt, những action được phép thực hiện và audit trail. Phải có concurrency control để hai nhân viên không cùng refund một giao dịch.

Một trường Boolean “needsManualReview” mà không có queue, quyền, SLA và escalation thì chưa phải kế hoạch phục hồi.

## 25. Observability của Saga phải theo kết quả nghiệp vụ

Một Saga có thể bắt đầu qua API trả 202 thành công nhưng kẹt nhiều giờ. Vì vậy chỉ số HTTP 2xx không đủ phản ánh độ tin cậy.

Nên theo dõi:

| Nhóm | Metrics / sự kiện |
| --- | --- |
| Tiến trình | Số Saga mới, đang chạy, hoàn tất theo loại |
| Kết quả | COMPLETED, REJECTED, COMPENSATED, MANUAL_REVIEW |
| Độ dài | Duration p50/p95/p99 từ bắt đầu tới terminal |
| Tồn đọng | Số Saga ở mỗi state và tuổi của Saga lâu nhất |
| Bước | Step latency, error rate, timeout, attempts |
| Message | Outbox backlog, publish lag, consumer lag |
| Lặp | Duplicate command/event, idempotency hit, conflict |
| Bù trừ | Compensation attempts, pending age, failure rate |
| Nghiệp vụ | Reservation expired, duplicate charge, refund pending |
| Đối soát | Mismatch giữa orchestrator và participant |

Dùng correlation ID/sagaId để tìm trace và log. Khi flow bất đồng bộ kéo dài, có thể dùng trace links hoặc kết hợp các trace theo business ID. Không đặt PII, token hoặc raw provider payload vào span attributes hay metrics labels có cardinality lớn.

### 25.1. Alert hữu ích

- Saga AUTHORIZING_PAYMENT quá deadline đã định.
- Compensation pending lâu hơn SLA.
- Outbox không publish được liên tục.
- Mỗi order có nhiều authorization/capture ngoài policy.
- Reservation ACTIVE nhưng Saga đã CANCELLED/REJECTED.
- Payment CAPTURED nhưng refund pending quá hạn sau một lệnh hủy.
- Event consumer lag tăng và state machine không tiến triển.

Mục tiêu alert là phát hiện **business outcome chưa được giải quyết**, không chỉ đếm exception.

## 26. Kiểm thử failure injection theo cửa sổ lỗi

Cần kiểm thử các điểm sau thay vì chỉ chạy happy path:

| Điểm gây lỗi | Điều phải xác minh |
| --- | --- |
| Crash trước commit T1 | Không báo accepted khi intent chưa được lưu |
| Crash sau commit trước publish | Outbox có phát lại được |
| T2 success nhưng reply mất | Retry không tạo hai reservations |
| T3 payment outcome unknown | Có query/reconcile, không tạo charge mới mù |
| Event giao lại hai lần | Chỉ một state transition hữu ích |
| Compensation nhận lặp | Stock không được cộng hai lần |
| Refund provider unavailable | Durable pending, retry, alert, review |
| User cancel trùng PaymentAuthorized | Guard chuyển state đúng và không confirm sai |
| Event đến sau terminal | Không đưa Saga trở lại state cũ |
| Reservation hết hạn | Không confirm dựa trên reservation invalid |
| Orchestrator restart giữa step | Tiếp tục đúng từ durable state |
| Consumer mới đọc event cũ | Hợp đồng version và replay đúng |
| Nhiều orchestrator workers cùng xử lý | Optimistic lock/unique constraints chặn race |

Ví dụ BDD:

```gherkin
Given order ord-8042 đang AUTHORIZING_PAYMENT
  And Inventory reservation res-8042 đang ACTIVE
When PaymentAuthorized được nhận hai lần
Then orchestrator chỉ chuyển sang CONFIRMING_ORDER một lần
  And không phát hai payment intents khác nhau
  And state của order vẫn phù hợp với workflow
```

Và:

```gherkin
Given reservation res-8042 đang ACTIVE
When ReleaseReservation được nhận hai lần
Then reservation chuyển sang RELEASED đúng một lần
  And số lượng stock chỉ được hoàn lại một lần
  And retry nhận kết quả hợp lệ mà không tạo side effect thêm
```

Kiểm thử cần xem database state, outbox, message processing và tác dụng phụ thật trong môi trường phù hợp; mock method call count thôi chưa đủ.

## 27. Những ngộ nhận quan trọng cần tránh

1. **“Saga là transaction ACID xuyên nhiều service.”** Sai; từng local transaction commit độc lập.
2. **“Compensation là rollback SQL của bước trước.”** Sai; refund hoặc thu hồi tài nguyên có ý nghĩa mới và lịch sử riêng.
3. **“Payment timeout nghĩa là chưa thu tiền.”** Sai; outcome có thể UNKNOWN.
4. **“Outbox giúp exactly-once trên toàn hệ thống.”** Sai; có thể publish lại, consumer phải idempotent.
5. **“Broker bảo đảm mỗi event chỉ được xử lý một lần.”** Không mặc định; redelivery và replay là tình huống bình thường.
6. **“Một Saga FAILED nghĩa là mọi side effect đã hoàn tác.”** Có thể còn compensation pending hoặc không thể đảo ngược.
7. **“Compensation không cần retry/monitoring.”** Nó có thể hỏng như mọi operation khác.
8. **“Nhận reply success là đủ để confirm bất kể state hiện tại.”** Reply có thể đến trễ sau cancellation.
9. **“Mỗi retry tạo một idempotency key mới.”** Điều đó làm mất khả năng chống lặp.
10. **“Choreography là không có coupling.”** Vẫn có event contracts và coupling qua hành vi.
11. **“Orchestration có một coordinator nghĩa là dùng chung database.”** Không; mỗi participant vẫn sở hữu data.
12. **“Saga nào cũng nên tuyến tính.”** Có thể song song nếu dependencies và compensation được thiết kế.
13. **“Chỉ cần log lỗi compensation.”** Cần durable state, SLA, cảnh báo và đường phục hồi.
14. **“Càng chia nhỏ service càng cần nhiều Saga thì càng tốt.”** Có thể là dấu hiệu ranh giới domain sai.
15. **“Có thể giao hàng ngay khi OrderCreated.”** Phải dựa trên business event thể hiện đủ điều kiện.
16. **“Có thể xóa đơn đã thất bại để sạch dữ liệu.”** Audit, kế toán và đối soát có thể bắt buộc giữ lịch sử.

## 28. Quy trình thiết kế một Saga mới

**Bước 1 — Xác định business outcome.** Viết điều kiện thành công, từ chối, hủy, tình trạng không chắc chắn và manual review.

**Bước 2 — Xác định owner và local transaction.** Mỗi bước do ai sở hữu? DB nào commit? Invariant nào được bảo vệ?

**Bước 3 — Liệt kê side effects.** Có lệnh gọi payment, shipment, email hoặc đối tác ngoài không? Bước nào khó đảo ngược?

**Bước 4 — Chọn thứ tự.** Đặt các bước dễ bù trừ trước; bảo vệ pivot/irreversible actions bằng điều kiện phù hợp.

**Bước 5 — Định nghĩa compensation.** Không chỉ tên API; cần điều kiện hợp lệ, tính idempotent, expected outcome và failure policy.

**Bước 6 — Chọn choreography/orchestration.** Cân nhắc độ phức tạp, số nhánh, khả năng quan sát, thay đổi và trách nhiệm tổng thể.

**Bước 7 — Vẽ state machine.** Bao gồm pending, success, definitive failure, unknown result, compensation pending và terminal states.

**Bước 8 — Định nghĩa contracts.** Command, event, IDs, phiên bản, business key, authorization, timeout, retry và compensation semantics.

**Bước 9 — Bảo đảm durability.** Local transaction, outbox, inbox/dedup, durable saga state và scheduling.

**Bước 10 — Thiết kế recovery.** Reconciliation, late event, cancel race, stale reservation, manual review.

**Bước 11 — Thiết kế API/UX.** Thời điểm báo accepted, cách truy vấn status, ý nghĩa PENDING/UNKNOWN.

**Bước 12 — Kiểm thử lỗi và giám sát.** Crash, duplicate, compensation failures, concurrency, schema migration và backlog.

## 29. Bài tập ứng dụng: Saga đặt hàng có giữ hàng và thanh toán

Một nền tảng thương mại có:

- Ordering tạo một order ở PENDING.
- Inventory giữ hai SKU trong 15 phút.
- Payment authorize khoản tiền theo payment intent.
- Shipping chỉ được bắt đầu khi order đã CONFIRMED.

Flow dự kiến:

```text
CreateOrder
  -> ReserveInventory
  -> AuthorizePayment
  -> ConfirmOrder
  -> StartShipping
```

Hãy trả lời:

1. Tại mỗi service, local transaction nên commit những gì?
2. Compensation cho ReserveInventory và AuthorizePayment khác nhau ra sao?
3. Nếu PaymentDeclined chắc chắn, thứ tự bù trừ và kết quả cuối là gì?
4. Nếu timeout Payment nhưng thực tế AUTHORIZED, tại sao không tạo authorization khác?
5. Khi ReleaseReservation bị giao hai lần, Inventory phải bảo vệ stock thế nào?
6. Nếu user cancel sau khi payment command đã gửi, state machine phải xử lý thế nào?
7. Reservation đã EXPIRED mà Payment mới thành công, có thể ConfirmOrder không?
8. Nếu Shipping đã bàn giao cho hãng vận chuyển, hủy draft có còn áp dụng không?
9. Nếu coordinator crash trước khi publish command, outbox và durable state giúp gì?
10. Nếu consumer nhận event trùng, có bảo đảm không phát lệnh ConfirmOrder lần hai không?
11. Nếu refund chưa hoàn tất, trạng thái Saga và trạng thái Payment nên là gì?
12. Các bước độc lập nào có thể song song và compensation graph ra sao?
13. API trả PENDING như thế nào, người dùng lấy trạng thái cuối ở đâu?
14. Khi Saga version thay đổi giữa lúc rollout, điều gì cần được duy trì để không phá instance cũ?
15. Các metrics nào cho thấy hệ thống đang thất thoát reservation hoặc gặp nguy cơ duplicate capture?

**Gợi ý suy luận:** Dùng reservation ID và payment intent ID ổn định, trạng thái PENDING rõ, định nghĩa một outcome UNKNOWN sau timeout, outbox để không mất message, idempotency ở mỗi participant, state machine có guarded transitions và reconciliation worker. Bù trừ theo trạng thái thực: void authorization không giống refund captured payment.

## 30. Ghi nhớ

Saga là **quy trình nghiệp vụ phân tán gồm nhiều local transactions**, trong đó mỗi bước có thể commit độc lập và những tác động đã commit được điều chỉnh bằng **compensating transactions** khi workflow thất bại hoặc thay đổi hướng.

Một Saga tin cậy cần:

- Invariant nghiệp vụ và data ownership đúng.
- Local transaction ngắn và có điều kiện concurrency.
- Compensation có nghĩa nghiệp vụ, không giả vờ rollback toàn cục.
- Orchestration hoặc choreography với trách nhiệm rõ.
- Durable saga state, outbox/inbox và idempotent participants.
- Phân biệt definitive failure với outcome UNKNOWN.
- Retry có giới hạn, reconciliation và manual review khi cần.
- Guarded state machine chống message trùng, event trễ và cancel race.
- API cho người dùng biết tiến trình PENDING/COMPLETED/COMPENSATING.
- Metrics và failure tests đo kết quả nghiệp vụ chứ không chỉ HTTP status.

**Khi một local transaction đã commit ở service khác, không có rollback từ xa miễn phí. Compensation là một giao dịch mới, có điều kiện, rủi ro và vòng đời riêng.** Thiết kế Saga tốt chấp nhận thực tế đó và cung cấp đường đi có thể chứng minh, phục hồi và vận hành để đạt kết quả nghiệp vụ cuối cùng.
