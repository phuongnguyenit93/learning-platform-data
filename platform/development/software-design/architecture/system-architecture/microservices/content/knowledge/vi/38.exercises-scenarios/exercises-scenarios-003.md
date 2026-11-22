# Thiết kế luồng đặt hàng, giữ tồn kho và thanh toán bằng Saga

## 1. Bài toán giao dịch xuyên nhiều microservice

Một luồng đặt hàng thường cập nhật nhiều phần dữ liệu thuộc các bounded context khác nhau:
- Order service tạo đơn hàng và quản lý trạng thái đơn.
- Inventory service kiểm tra và giữ số lượng tồn kho.
- Payment service yêu cầu cổng thanh toán authorize hoặc charge.
- Notification service gửi email/SMS sau khi đơn đạt trạng thái phù hợp.
- Shipping/fulfillment service có thể tạo yêu cầu giao hàng sau khi đơn được xác nhận.

Nếu tất cả dữ liệu nằm trong một database, một transaction ACID có thể bao phủ nhiều bảng. Nhưng trong kiến trúc microservices, mỗi service thường sở hữu database riêng và commit transaction độc lập. Không thể giả định một transaction SQL thông thường sẽ rollback được những thay đổi đã commit ở service khác.

Ví dụ:
1. Order service tạo đơn.
2. Inventory service giữ hàng thành công.
3. Payment service gọi cổng thanh toán.
4. Cổng thanh toán đã authorize nhưng response bị timeout.
5. Order service không biết payment thành công hay chưa.

Lúc này hệ thống có thể tồn tại đơn hàng đang chờ, tồn kho đã bị giữ và giao dịch thanh toán chưa rõ trạng thái. Nếu chỉ retry mù hoặc xóa order record, dữ liệu và side effect sẽ lệch nhau.

**Saga pattern** là cách điều phối một giao dịch nghiệp vụ dài thành chuỗi các local transaction tại từng service. Mỗi bước commit trong database của service sở hữu dữ liệu. Khi một bước không thể tiếp tục, Saga chạy các **compensating transactions** (giao dịch bù) để đưa nghiệp vụ về một trạng thái chấp nhận được.

Saga không phải distributed ACID transaction và compensation không phải rollback vật lý. Một giao dịch đã charge thẻ không thể “quên rằng nó đã xảy ra”; hệ thống phải thực hiện refund hoặc một hành động nghiệp vụ bù tương ứng, hành động này cũng có thể thất bại và cần được theo dõi.

Bài học này xây dựng một luồng đặt hàng, giữ tồn kho và thanh toán bằng Saga, tập trung vào:
1. Phân rã nghiệp vụ thành local transactions và xác định thứ tự.
2. Chọn Saga orchestration hoặc choreography.
3. Thiết kế state machine, timeout, retry và compensation.
4. Bảo đảm idempotency, consistency và xử lý kết quả không rõ.
5. Dùng transactional outbox/inbox để tránh mất hoặc nhân đôi event.
6. Triển khai với Java/Spring Boot và message broker.
7. Kiểm thử failure scenarios, quan sát tiến trình và vận hành phục hồi.

## 2. Mô hình nghiệp vụ và các invariant

Trước khi chọn framework hoặc broker, xác định điều kiện đúng của nghiệp vụ.

Một đơn hàng chỉ được xác nhận khi:
- Request được xác thực và hợp lệ.
- Giá, currency và các điều kiện bán được chấp nhận theo policy.
- Inventory đã giữ đủ số lượng hoặc có reservation hợp lệ.
- Payment đã đạt trạng thái authorization/capture mà nghiệp vụ yêu cầu.
- Order service đã lưu trạng thái và các tham chiếu giao dịch nhất quán.

Các invariant quan trọng:
- Không bán vượt tồn kho được phép theo mô hình reservation.
- Không charge hai lần cho cùng một business intent.
- Một reservation chỉ được release theo đúng owner/order và trạng thái.
- Một payment chỉ được capture/refund theo quy tắc và trạng thái hợp lệ.
- Một order không được chuyển từ CANCELLED về CONFIRMED do event đến trễ.
- Mỗi bước retry phải an toàn khi thực thi nhiều lần.
- Trạng thái cuối cùng có thể đối soát từ order, inventory và payment records.

Một mô hình trạng thái đơn giản:

~~~text
PENDING
  → INVENTORY_RESERVED
  → PAYMENT_AUTHORIZED
  → CONFIRMED

Nhánh thất bại:
  INVENTORY_RESERVED → PAYMENT_FAILED
  PAYMENT_FAILED → INVENTORY_RELEASED
  INVENTORY_RESERVE_FAILED → REJECTED

Kết quả không rõ:
  PAYMENT_PENDING → PAYMENT_UNKNOWN
  PAYMENT_UNKNOWN → RECONCILING
  RECONCILING → PAYMENT_AUTHORIZED hoặc PAYMENT_FAILED
~~~

Đây là state machine khái niệm; hệ thống thật cần định nghĩa rõ trạng thái intermediate, terminal, retryable và manual intervention. Trạng thái `PAYMENT_UNKNOWN` rất quan trọng: timeout không chứng minh payment provider chưa xử lý request.

## 3. Local transaction và Saga transaction

Một Saga gồm các local transaction được commit riêng:

| Bước | Service sở hữu | Local transaction | Kết quả |
| --- | --- | --- | --- |
| T1 | Order | Tạo order ở trạng thái PENDING và lưu Saga ID | Order tồn tại, chưa xác nhận |
| T2 | Inventory | Reserve quantity cho order | Reservation ACTIVE hoặc REJECTED |
| T3 | Payment | Authorize payment với idempotency key | Authorization thành công/thất bại/unknown |
| T4 | Order | Chuyển order sang CONFIRMED | Order được xác nhận |
| T5 | Notification | Gửi thông báo theo event OrderConfirmed | Side effect thông báo |

Các bước T1–T4 thuộc luồng Saga cốt lõi; notification thường là side effect bất đồng bộ sau khi order confirmed. Không nên giữ Saga ở trạng thái pending chỉ vì email provider đang lỗi, trừ khi nghiệp vụ thực sự yêu cầu email là điều kiện hoàn tất đơn.

### 3.1. Vì sao không giữ một transaction mở xuyên service?

Giữ transaction DB mở trong khi gọi HTTP sang inventory/payment gây:
- Connection và lock bị giữ lâu.
- Latency phụ thuộc network/provider.
- Deadlock và timeout khó dự đoán.
- Không thể rollback side effect đã commit ở service khác.
- Khó scale và phục hồi khi một service ngừng hoạt động.

Saga cho phép mỗi service commit ngắn, giải phóng tài nguyên, sau đó tiếp tục bước tiếp theo bằng command/event bền vững.

### 3.2. Saga không đảm bảo isolation như ACID

Trong lúc Saga đang chạy, người dùng hoặc tiến trình khác có thể quan sát trạng thái trung gian. Ví dụ order ở PENDING trong khi reservation đã ACTIVE. Đây là **eventual consistency** theo quy trình.

Cần thiết kế:
- Trạng thái hiển thị rõ với client.
- Không thực hiện fulfillment trước khi điều kiện xác nhận đạt.
- Reservation có expiry/lease.
- Payment có trạng thái pending/authorized/captured rõ.
- Các command cạnh tranh được serialize hoặc bảo vệ bằng version/optimistic locking.
- Query/read model biết cách biểu diễn giao dịch đang xử lý.

Saga điều phối trạng thái nghiệp vụ; nó không biến nhiều database thành một transaction nguyên tử.

## 4. Thiết kế luồng đặt hàng chuẩn

Một trình tự phổ biến:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as Order Service
    participant I as Inventory Service
    participant P as Payment Service
    participant PG as Payment Provider
    participant B as Event Bus
    C->>O: CreateOrder (idempotency key)
    O->>O: Save PENDING + Saga + Outbox
    O-->>C: 202 Accepted / orderId
    O->>I: ReserveInventory
    I->>I: Commit reservation
    I-->>O: InventoryReserved
    O->>P: AuthorizePayment
    P->>PG: Authorize (provider idempotency key)
    PG-->>P: Authorized
    P->>P: Persist payment result + outbox
    P-->>O: PaymentAuthorized
    O->>O: Commit order CONFIRMED
    O->>B: Publish OrderConfirmed via outbox
~~~

Sơ đồ rút gọn bỏ qua retry, timeout, callback và reconciliation. Trong thiết kế thật, các command/event nên được lưu bền và có ID để có thể retry an toàn.

### 4.1. Tại sao reserve inventory trước payment?

Giữ tồn kho trước có thể tránh authorize payment cho mặt hàng đã hết. Tuy nhiên reservation có thể hết hạn hoặc payment mất nhiều thời gian. Cần:
- TTL/lease cho reservation.
- Gia hạn có kiểm soát nếu workflow vẫn hợp lệ.
- Release khi payment thất bại hoặc Saga bị hủy.
- Đảm bảo reservation không bị release sau khi order đã confirmed.
- Reconcile nếu payment thành công nhưng inventory reservation đã hết hạn.

Một số domain chọn authorize payment trước rồi reserve stock, hoặc kiểm tra stock sơ bộ trước cả hai. Thứ tự tùy thuộc chi phí/khả năng đảo ngược của từng side effect và hợp đồng provider. Không có thứ tự đúng cho mọi nghiệp vụ.

### 4.2. Authorize và capture

Trong thanh toán thẻ, có thể tách:
- **Authorize:** giữ/ủy quyền một khoản tiền, chưa nhất thiết capture.
- **Capture:** thu tiền theo authorization.
- **Void/reversal:** hủy authorization khi có thể.
- **Refund:** hoàn tiền sau khi đã capture.

Nếu fulfillment chỉ được bắt đầu sau khi capture, Saga cần thể hiện bước capture và compensation refund. Nếu authorize đủ để xác nhận đơn và capture sau khi giao hàng, state machine sẽ khác. Phải thống nhất semantics với payment provider và finance team.

## 5. Chọn Orchestration hay Choreography

### 5.1. Orchestration

Một Saga orchestrator điều phối các bước:
- Gửi ReserveInventory.
- Chờ InventoryReserved/Rejected.
- Gửi AuthorizePayment.
- Chờ PaymentAuthorized/Failed/Unknown.
- Cập nhật Order hoặc phát command compensation.

Ưu điểm:
- Luồng nghiệp vụ nhìn thấy tại một nơi.
- Thứ tự, timeout và compensation rõ.
- Dễ audit tiến trình và theo dõi Saga state.
- Phù hợp quy trình nhiều bước và nhiều nhánh.

Nhược điểm:
- Orchestrator trở thành thành phần cần vận hành, scale và HA.
- Nếu chứa quá nhiều domain logic, dễ thành central monolith.
- Các service phải tuân thủ command/result contract.
- Cần quản lý version workflow khi Saga đang chạy trong lúc deploy.

### 5.2. Choreography

Không có central orchestrator. Service phản ứng với event:
- Order service phát OrderCreated.
- Inventory service nghe và phát InventoryReserved.
- Payment service nghe InventoryReserved và phát PaymentAuthorized.
- Order service nghe PaymentAuthorized rồi xác nhận đơn.
- Nếu PaymentFailed, một service phát lệnh release reservation.

Ưu điểm:
- Mỗi service phản ứng với event trong phạm vi ownership.
- Giảm một điểm điều phối trung tâm.
- Có thể phù hợp flow ngắn, ít nhánh và event contract ổn định.

Nhược điểm:
- Toàn bộ flow bị phân tán giữa nhiều consumer.
- Khó biết Saga đang ở bước nào nếu không có correlation/state tracking.
- Vòng lặp event và dependency khó quan sát.
- Timeout/compensation khó điều phối thống nhất.
- Thay đổi schema hoặc thứ tự event có thể làm flow sai.

### 5.3. Bảng so sánh

| Tiêu chí | Orchestration | Choreography |
| --- | --- | --- |
| Điều phối | Một orchestrator có state | Service phản ứng với event |
| Khả năng nhìn toàn luồng | Tập trung hơn | Phải ghép nhiều log/event |
| Độ phức tạp ban đầu | Tập trung vào workflow | Phân tán qua consumer |
| Phù hợp | Flow dài, nhiều nhánh/compensation | Flow đơn giản, ít bước |
| Coupling | Orchestrator biết các command | Consumer biết event contract |
| Failure handling | Có nơi quản lý timeout/state | Cần convention xuyên service |
| Versioning | Workflow version và event contract | Event contract/consumer compatibility |
| Rủi ro | Orchestrator thành central bottleneck | Event choreography khó debug |

### 5.4. Tiêu chí chọn

Chọn orchestration khi:
- Quy trình có nhiều bước tuần tự và điều kiện.
- Cần timeout và compensation theo state.
- Có human intervention hoặc reconciliation.
- Business muốn theo dõi tiến trình order end-to-end.
- Cần audit rõ ai/step nào quyết định trạng thái.

Chọn choreography khi:
- Flow ngắn, event-driven tự nhiên.
- Các consumer độc lập và ít điều kiện điều phối.
- Không cần coordinator quản lý toàn bộ transaction.
- Có observability, event contract và ownership trưởng thành.

Có thể kết hợp: orchestrator điều phối order/inventory/payment, còn notification, analytics và search projection dùng choreography sau khi OrderConfirmed.

## 6. Xác định compensation cho từng bước

Compensation là hành động nghiệp vụ bù cho một local transaction đã commit. Nó không nhất thiết khôi phục đúng trạng thái lịch sử, mà đưa hệ thống về một kết quả hợp lệ.

| Forward action | Compensation | Điều kiện/giới hạn |
| --- | --- | --- |
| Create pending order | Cancel/reject order | Không xóa audit history |
| Reserve inventory | Release reservation | Chỉ release reservation thuộc Saga/order |
| Authorize payment | Void authorization | Có thể provider không hỗ trợ hoặc authorization đã capture |
| Capture payment | Refund payment | Refund là giao dịch mới, có thể pending/fail |
| Create shipment | Cancel shipment request | Có thể đã đóng gói hoặc bàn giao |
| Send email | Thường không thể thu hồi | Có thể gửi thông báo đính chính |
| Publish event | Phát event correction/compensation | Không xóa message đã được consumer xử lý |

### 6.1. Compensation phải idempotent

Nếu ReleaseInventory được gửi ba lần, reservation chỉ được chuyển từ ACTIVE sang RELEASED một lần theo cùng Saga ID. Nếu RefundPayment retry, provider idempotency key phải ngăn hoàn tiền nhiều lần.

Compensation nên:
- Có command ID duy nhất.
- Có Saga ID và business reference.
- Kiểm tra state/version trước khi đổi.
- Ghi kết quả và audit.
- Retry có giới hạn và backoff.
- Có trạng thái FAILED/REQUIRES_MANUAL_ACTION khi không thể tự phục hồi.

### 6.2. Compensation không phải reverse database snapshot

Không dùng cách “restore database về trước Saga” vì các giao dịch khác có thể đã commit sau đó. Compensation là thao tác domain-specific trên dữ liệu hiện hành, bảo toàn các giao dịch độc lập khác.

### 6.3. Compensation có thể thất bại

Ví dụ payment đã capture, nhưng refund provider đang unavailable. Order không thể đơn giản được đánh dấu CANCELLED như thể tiền đã hoàn. Có thể cần trạng thái `CANCEL_PENDING_REFUND` hoặc `REFUND_PENDING`, cảnh báo và đối soát cho đến khi refund hoàn tất.

Một Saga có thể kết thúc ở trạng thái cần can thiệp thủ công. Điều quan trọng là trạng thái đó rõ, có owner và có khả năng tiếp tục/reconcile; không che lỗi bằng cách đánh dấu rollback thành công.

## 7. State machine cho Order Saga

Một model minh họa:

~~~text
PENDING
  ├── ReserveInventory command
  │     ├── RESERVED
  │     └── REJECTED → ORDER_REJECTED
  ├── AuthorizePayment command
  │     ├── AUTHORIZED
  │     ├── DECLINED → RELEASE_INVENTORY → ORDER_PAYMENT_FAILED
  │     └── UNKNOWN → RECONCILING
  └── CONFIRM_ORDER
        → CONFIRMED

Cancellation:
  CONFIRMED → CANCEL_REQUESTED
    → VOID/REFUND_PAYMENT
    → RELEASE/RETURN_INVENTORY (theo fulfillment state)
    → CANCELLED hoặc CANCEL_REQUIRES_ACTION
~~~

Thực tế cần tách state của Order, Saga, Inventory Reservation và Payment. Một enum duy nhất không nên cố đại diện mọi domain. Ví dụ:
- Order status: PENDING, CONFIRMED, CANCELLED.
- Saga status: RUNNING, COMPENSATING, COMPLETED, FAILED, MANUAL_ACTION.
- Reservation status: ACTIVE, RELEASED, EXPIRED, CONSUMED.
- Payment status: INITIATED, AUTHORIZED, CAPTURED, DECLINED, UNKNOWN, VOIDED, REFUNDED.

State transition phải có guard và version. Không cho event cũ chuyển PAYMENT_REFUNDED về PAYMENT_AUTHORIZED.

## 8. Command, event và correlation

Phân biệt:
- **Command:** yêu cầu một service thực hiện hành động, ví dụ ReserveInventory.
- **Event:** sự kiện đã xảy ra, ví dụ InventoryReserved.
- **Reply/result:** kết quả của command, ví dụ ReservationRejected.

Tên command thường mang tính mệnh lệnh; event dùng thì quá khứ và chỉ phát sau khi thay đổi đã commit.

Một envelope ví dụ:

~~~json
{
  "messageId": "msg-1001",
  "messageType": "InventoryReserved",
  "schemaVersion": 1,
  "occurredAt": "2026-11-12T10:00:00Z",
  "producer": "inventory-service",
  "sagaId": "saga-9001",
  "correlationId": "checkout-77",
  "causationId": "cmd-reserve-9001",
  "tenantId": "tenant-42",
  "aggregateId": "order-501",
  "aggregateVersion": 3,
  "data": {
    "orderId": "order-501",
    "reservationId": "reservation-501",
    "expiresAt": "2026-11-12T10:15:00Z"
  }
}
~~~

Payload minh họa. Không đưa dữ liệu thanh toán nhạy cảm, card number hoặc secret vào event. Consumer phải xác thực nguồn phát, validate schema, kiểm tra tenant scope và không tin payload chỉ vì nó nằm trong broker.

### 8.1. Saga ID và correlation ID

- **Saga ID:** định danh một lần thực thi quy trình phân tán.
- **Correlation ID:** liên hệ request/luồng nghiệp vụ gốc, có thể bao trùm nhiều Saga.
- **Causation ID:** message/command gây ra message hiện tại.
- **Message ID:** định danh duy nhất cho một message delivery logic.
- **Aggregate ID/version:** xác định đối tượng và thứ tự thay đổi nếu cần.

Không dùng orderId làm Saga ID nếu cùng order có thể có nhiều Saga khác nhau như create, cancel, refund. Có thể liên kết chúng nhưng cần định danh workflow riêng.

## 9. Persist Saga state và recovery

Orchestrator cần lưu trạng thái bền:
- saga_id.
- order_id.
- tenant_id.
- workflow_type và workflow_version.
- current_state.
- status.
- next_action/deadline.
- retry_count/attempt metadata.
- last_error_code.
- correlation_id.
- created_at/updated_at.
- version/optimistic lock.
- compensation state và operator notes.

Không chỉ lưu state trong memory của process. Nếu orchestrator restart, nhiều Saga đang chạy phải tiếp tục được từ database hoặc workflow engine.

### 9.1. Optimistic locking

Nếu cùng Saga nhận hai event duplicate hoặc hai worker xử lý đồng thời, state có thể bị ghi đè. Dùng version column:

~~~sql
UPDATE order_sagas
SET state = :new_state,
    version = version + 1,
    updated_at = now()
WHERE saga_id = :saga_id
  AND version = :expected_version;
~~~

Nếu affected row bằng 0, worker phải đọc lại state và quyết định duplicate, conflict hay stale event. Không tự retry update bằng state cũ.

### 9.2. Durable timer và timeout event

Saga có thể chờ payment result trong một khoảng thời gian. Timer phải được lưu bền hoặc quản lý bởi workflow engine, không chỉ dùng ScheduledExecutorService trong một pod. Khi orchestrator restart, timeout vẫn phải được kích hoạt đúng.

Timeout command cần:
- sagaId và stepId.
- Deadline.
- Version/state expected.
- Idempotency key.
- Hành vi khi response đến sau timeout.
- Quy tắc hủy timer khi step hoàn tất.

## 10. Transactional outbox và inbox

### 10.1. Vấn đề dual write

Nếu order service:
1. Commit order vào database.
2. Publish OrderCreated lên broker.

Có hai cửa sổ lỗi:
- DB commit thành công nhưng publish thất bại: consumer không biết order đã tạo.
- Publish thành công nhưng DB rollback hoặc process không xác nhận: consumer nhận event không tương ứng state bền.

**Transactional outbox** ghi business data và event record trong cùng local database transaction. Một relay/CDC process phát event sau commit.

~~~sql
BEGIN;

INSERT INTO orders(order_id, status, total_amount)
VALUES (:order_id, 'PENDING', :amount);

INSERT INTO outbox_events(
    event_id, aggregate_type, aggregate_id,
    event_type, payload, created_at
)
VALUES (
    :event_id, 'Order', :order_id,
    'OrderCreated', :payload, now()
);

COMMIT;
~~~

Relay đọc outbox và publish. Có thể publish trùng nếu relay crash sau broker ack nhưng trước khi đánh dấu published; vì vậy consumer vẫn cần idempotency.

### 10.2. Inbox/deduplication

Consumer lưu message ID đã xử lý cùng với local state update:

~~~sql
BEGIN;

INSERT INTO inbox_messages(consumer_name, message_id, received_at)
VALUES (:consumer, :message_id, now())
ON CONFLICT DO NOTHING;

-- Chỉ thực hiện business update nếu insert mới thành công.
-- Update reservation/payment/order state theo contract.
-- Có thể ghi outbox event tiếp theo trong cùng transaction.

COMMIT;
~~~

Trong code, phải kiểm tra số row insert/returning để biết message mới hay duplicate. Nếu duplicate, ACK an toàn sau khi biết lần trước đã commit. Không đánh dấu inbox processed trước khi business transaction hoàn tất.

### 10.3. Outbox relay

Có thể dùng polling hoặc CDC:
- Polling dễ bắt đầu nhưng cần xử lý lock/claim/batch.
- CDC giảm polling nhưng tăng vận hành connector/schema/offset.
- Partition theo aggregate hoặc key nếu cần ordering.
- Retry publish và track attempt.
- Cleanup/archive outbox theo retention sau khi xác nhận.
- Monitor oldest unpublished event age.

## 11. Inventory reservation và concurrency

Tồn kho là nguồn dữ liệu cạnh tranh. Hai đơn cùng đọc available=1 rồi cùng ghi reservation có thể oversell nếu không có atomic guard.

Một cách mô hình hóa:
- on_hand: tổng lượng vật lý được ghi nhận.
- reserved: lượng đang giữ cho đơn chưa hoàn tất.
- available: on_hand - reserved (tùy mô hình).
- reservation: order, SKU, quantity, status, expiry.

Ví dụ atomic update:

~~~sql
UPDATE inventory
SET reserved = reserved + :quantity,
    version = version + 1
WHERE sku = :sku
  AND on_hand - reserved >= :quantity;
~~~

Nếu affected row = 0, không đủ hàng hoặc conflict; cần phân biệt theo query/transaction phù hợp. Với nhiều SKU, phải xử lý thứ tự lock nhất quán hoặc chiến lược tránh deadlock.

### 11.1. Reservation record

~~~sql
CREATE TABLE inventory_reservations (
    reservation_id UUID PRIMARY KEY,
    saga_id UUID NOT NULL,
    order_id UUID NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    status TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (saga_id, sku)
);
~~~

Schema minh họa, cần điều chỉnh composite key theo tenant, currency/warehouse và mô hình multi-line reservation. Unique constraint hỗ trợ idempotency khi cùng Saga gửi ReserveInventory nhiều lần.

### 11.2. Release và consume khác nhau

- **Release:** bỏ giữ hàng khi Saga thất bại/hủy trước fulfillment.
- **Consume/deduct:** giảm tồn kho thực tế khi nghiệp vụ giao/fulfill đạt điều kiện.
- **Expire:** reservation hết TTL và được giải phóng theo policy.
- **Return/restock:** hàng hoàn về sau fulfillment; không đồng nghĩa release reservation.

Không dùng một command ReleaseInventory cho mọi trạng thái, vì có thể cộng tồn kho sai nếu hàng đã được xuất.

### 11.3. Reservation expiry race

Một payment authorization có thể đến đúng lúc reservation hết hạn. Inventory service cần quyết định atomic:
- Nếu reservation còn ACTIVE và chưa hết hạn: có thể confirm/consume theo policy.
- Nếu EXPIRED: không được tự coi payment là hợp lệ để fulfillment.
- Nếu expiry job và confirm command cạnh tranh: dùng row lock/version và transition guard.
- Nếu payment đã authorize nhưng reservation hết hạn: Saga cần void authorization hoặc flow re-reserve/reconcile.

## 12. Payment state và kết quả không rõ

Payment service thường tích hợp provider ngoài. Kết quả có thể:
- Authorized/declined rõ ràng.
- Timeout trước khi provider nhận request.
- Provider xử lý thành công nhưng response bị mất.
- Callback/webhook tới trước response đồng bộ.
- Callback duplicate hoặc sai thứ tự.
- Provider trả pending và quyết định sau.

Không ánh xạ mọi timeout thành PAYMENT_FAILED. Dùng trạng thái UNKNOWN/PENDING_RECONCILIATION để tránh charge lần hai.

### 12.1. Idempotency key với provider

Tạo key ổn định theo business operation, ví dụ:
`payment-authorize:<orderId>:<paymentAttempt>`.

Cùng attempt retry phải dùng lại key. Attempt mới chỉ được tạo sau khi xác định attempt cũ đã failed/voided hoặc có quy tắc rõ. Lưu provider reference và request fingerprint.

### 12.2. Reconciliation

Nếu response unknown:
1. Không tạo authorize mới ngay.
2. Query provider theo idempotency key/reference.
3. Chờ webhook/callback có xác thực.
4. Đối chiếu amount, currency, order và merchant account.
5. Chuyển payment state bằng guarded transition.
6. Nếu đã authorize nhưng Saga đã hủy, thực hiện void.
7. Nếu đã capture, refund theo quy trình.
8. Ghi audit và phát event kết quả.

Reconciliation cần schedule, alert và owner. Có thể phải chờ provider settlement data để giải quyết một số trạng thái.

## 13. Compensation và thứ tự rollback

Giả sử flow:
1. Create pending order.
2. Reserve inventory.
3. Authorize payment.
4. Confirm order.

Nếu payment declined:
- Payment service ghi trạng thái DECLINED.
- Saga chuyển COMPENSATING.
- Inventory service nhận ReleaseReservation.
- Khi release xác nhận, order chuyển PAYMENT_FAILED/REJECTED theo policy.
- Nếu release thất bại, Saga tiếp tục retry hoặc manual action.

Nếu order confirmation thất bại sau khi payment đã authorize:
- Có thể retry bước confirm vì đó là local DB operation.
- Nếu không thể phục hồi, void payment authorization.
- Release inventory sau khi payment compensation đạt điều kiện.
- Chỉ kết thúc Saga khi các compensation đạt trạng thái được định nghĩa hoặc chuyển MANUAL_ACTION.

### 13.1. Compensation order

Thường compensation chạy theo thứ tự ngược với forward steps, nhưng không phải luôn là reverse đơn giản. Thứ tự phải dựa trên dependency và an toàn:
- Không release inventory trước khi chắc chắn order không thể confirm hoặc đã hủy.
- Không refund trước khi biết payment đã capture hay chỉ authorize.
- Nếu payment unknown, cần reconcile trước khi quyết định compensation.
- Nếu fulfillment đã bắt đầu, cancellation có thể cần workflow riêng.

### 13.2. Compensation failure

Một Saga có thể ở COMPENSATING lâu. Cần:
- Retry có backoff.
- Dead-letter/manual queue cho compensation không thể tự xử lý.
- Alert theo oldest Saga age và compensation failure.
- Dashboard theo step.
- Operator action có audit.
- Runbook để retry/override sau khi xác minh trạng thái bên ngoài.

Không tự chuyển Saga sang COMPLETED chỉ vì hết số lần retry.

## 14. Orchestrator implementation với Java/Spring Boot

Có thể triển khai orchestrator riêng hoặc dùng workflow engine. Dù chọn cách nào, domain state và recovery semantics vẫn cần rõ.

### 14.1. Domain model

~~~java
public enum OrderSagaState {
    STARTED,
    INVENTORY_PENDING,
    INVENTORY_RESERVED,
    PAYMENT_PENDING,
    PAYMENT_UNKNOWN,
    PAYMENT_AUTHORIZED,
    COMPENSATING,
    CONFIRMED,
    REJECTED,
    MANUAL_ACTION
}

public enum SagaStatus {
    RUNNING,
    COMPENSATING,
    COMPLETED,
    FAILED,
    MANUAL_ACTION
}

public record SagaCommand(
    UUID sagaId,
    UUID orderId,
    String tenantId,
    String idempotencyKey
) {}
~~~

Ví dụ rút gọn. State machine thực tế cần thêm step version, deadline, retry count, failure reason và transitions hợp lệ.

### 14.2. Saga entity và persistence

~~~java
@Entity
@Table(name = "order_sagas")
public class OrderSaga {
    @Id
    private UUID sagaId;

    private UUID orderId;
    private String tenantId;

    @Enumerated(EnumType.STRING)
    private OrderSagaState state;

    @Enumerated(EnumType.STRING)
    private SagaStatus status;

    private long version;
    private Instant deadlineAt;
    private int retryCount;

    // getters, guarded transition methods, optimistic locking
}
~~~

Có thể dùng `@Version` cho optimistic locking. Không expose entity trực tiếp qua API. Mọi transition nên đi qua method/domain service kiểm tra state hiện tại và command/event version.

### 14.3. Bắt đầu Saga trong transaction local

~~~java
@Transactional
public OrderCreatedResult createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(
        Order.pending(command.orderId(), command.tenantId())
    );

    OrderSaga saga = sagaRepository.save(
        OrderSaga.start(command.sagaId(), order.getId(),
                        command.tenantId())
    );

    outboxRepository.save(
        OutboxEvent.reserveInventory(saga.getSagaId(), order)
    );

    return new OrderCreatedResult(order.getId(), "PENDING");
}
~~~

Order, Saga và command outbox được commit trong cùng database transaction. Relay phát command sau commit. Nếu API trả 202, client có thể poll order/operation status.

### 14.4. Xử lý InventoryReserved

~~~java
@Transactional
public void onInventoryReserved(InventoryReserved event) {
    if (inboxRepository.existsByMessageId(event.messageId())) {
        return;
    }

    OrderSaga saga = sagaRepository.findByIdForUpdate(event.sagaId())
        .orElseThrow();

    if (saga.state() != OrderSagaState.INVENTORY_PENDING) {
        inboxRepository.record(event.messageId());
        return; // stale/duplicate event; production code logs outcome
    }

    saga.markInventoryReserved(event.reservationId());

    outboxRepository.save(
        OutboxEvent.authorizePayment(saga, event)
    );
    inboxRepository.record(event.messageId());
}
~~~

Đây là pseudocode minh họa. Trong code thật, cần bảo đảm inbox record, saga transition và outbox insert cùng transaction. Nếu event stale, chỉ ACK sau khi quyết định stale là an toàn theo state/version; không âm thầm bỏ qua event có thể cần reconciliation.

### 14.5. Transaction boundary của consumer

Listener nên gọi application service có transaction rõ ràng. Broker ACK/offset commit phải phối hợp với kết quả DB transaction theo semantics framework. Nếu DB commit xong nhưng ACK thất bại, message được giao lại; inbox sẽ deduplicate. Nếu ACK trước DB commit, crash có thể làm mất xử lý.

Không đặt `@Transactional` một cách máy móc ở method private hoặc self-invocation mà Spring proxy không áp dụng. Kiểm tra propagation và transaction manager thực tế.

## 15. Inventory service command handler

Ví dụ logic:

~~~java
@Transactional
public ReservationResult reserve(ReserveInventoryCommand command) {
    var existing = reservationRepository
        .findBySagaIdAndSku(command.sagaId(), command.sku());

    if (existing.isPresent()) {
        return ReservationResult.from(existing.get());
    }

    int updated = inventoryRepository.reserveIfAvailable(
        command.sku(), command.quantity()
    );

    if (updated == 0) {
        return ReservationResult.rejected("INSUFFICIENT_STOCK");
    }

    Reservation reservation = reservationRepository.save(
        Reservation.active(
            command.sagaId(),
            command.orderId(),
            command.sku(),
            command.quantity(),
            command.expiresAt()
        )
    );

    outboxRepository.save(
        OutboxEvent.inventoryReserved(command, reservation)
    );

    return ReservationResult.reserved(reservation.getId());
}
~~~

Ví dụ cần tinh chỉnh để tránh race giữa kiểm tra existing và insert reservation: unique constraint theo Saga/SKU, xử lý conflict và transaction isolation phải được kiểm chứng. Atomic stock update và reservation insert phải nằm cùng transaction. Nếu insert thất bại do duplicate, không được để quantity đã tăng thêm; transaction rollback hoặc xử lý atomic đúng.

### 15.1. Reserve nhiều SKU

Một order có nhiều line:
- Validate SKU và quantity.
- Sort SKU để giảm deadlock khi lock nhiều row.
- Reserve tất cả trong một local transaction nếu cùng database và quy mô cho phép.
- Nếu một SKU thiếu, rollback toàn bộ reservation của service rồi trả rejection.
- Hoặc tạo reservation từng phần nếu domain cho phép, nhưng Saga phải biết partial state và compensation cho từng line.

Không giữ một transaction DB mở trong lúc chờ payment. Reservation local có thể commit nhanh, sau đó Saga tiếp tục.

## 16. Payment service command handler

Payment service cần phân biệt attempt và order:
- Một order có thể có nhiều payment attempt.
- Một attempt có thể có nhiều network retry nhưng cùng idempotency key.
- Provider reference phải được lưu.
- Amount/currency được xác thực từ dữ liệu server-side.
- Callback được xác thực và deduplicate.

Pseudo flow:

~~~text
AuthorizePayment(command):
  find payment attempt by sagaId/operationKey
  if terminal result exists:
      return saved result

  persist attempt = REQUESTED
  call provider with same idempotency key and timeout

  if provider says authorized:
      persist AUTHORIZED + providerReference + outbox event
  else if provider says declined:
      persist DECLINED + outbox event
  else if timeout/unknown:
      persist UNKNOWN + schedule reconciliation
~~~

Không giữ transaction database mở khi gọi provider nếu không cần. Có thể ghi attempt trước, gọi provider ngoài transaction, rồi transaction thứ hai lưu kết quả/outbox. Khi crash giữa call và persist, reconciliation dùng idempotency key/provider reference để xác định kết quả.

### 16.1. Webhook và callback

Webhook có thể đến trước khi synchronous response được ghi. Payment service cần:
- Verify signature và timestamp.
- Replay protection.
- Idempotent event ID.
- Correlate theo provider reference và merchant account.
- Guard state transition.
- Ghi inbox/outbox cùng local transaction.
- Chấp nhận event out-of-order theo policy.

## 17. Orchestrator timeout và scheduler bền vững

Mỗi step có deadline. Ví dụ:
- Inventory reservation deadline 2 giây.
- Payment authorization deadline 15 giây.
- Reconciliation window có thể dài hơn và chạy bất đồng bộ.

Các số phải dựa trên SLA provider và business requirements.

Không dùng một `@Scheduled` đơn giản trong mọi replica mà không có distributed lock/claim semantics; nhiều pod có thể cùng phát timeout command. Có thể:
- Lưu `next_action_at` trong saga table.
- Worker claim row theo lock/lease và SKIP LOCKED nếu DB hỗ trợ.
- Dùng workflow engine có durable timer.
- Có unique timeout command ID và expected state version.
- Retry worker sau crash.

Timeout event nên chứa Saga ID, step ID, deadline và version. Khi response thành công tới sau timeout, state machine phải xử lý theo chính sách:
- Nếu chưa compensation: có thể nhận kết quả và tiếp tục.
- Nếu đã compensation: thực hiện action bù cho side effect đến muộn, ví dụ void authorization.
- Nếu trạng thái không rõ: reconciliation trước khi quyết định.

## 18. Event ordering, duplicate và out-of-order

Broker thường đảm bảo ordering trong một partition/key scope, không phải toàn bộ topic hoặc mọi service. Các event có thể:
- Được giao nhiều lần.
- Đến trễ.
- Đến sai thứ tự giữa các partition.
- Được replay sau deploy.
- Được xử lý song song.

Cần:
- Partition key phù hợp aggregate/order ID.
- Aggregate version/sequence.
- State transition guard.
- Inbox/dedup.
- Event schema version.
- Idempotency cho external side effect.
- Stale event handling và audit.
- Reconciliation khi phát hiện gap.

Nếu PaymentAuthorized version 5 đến sau PaymentRefunded version 7, consumer không được ghi state quay ngược. Có thể bỏ qua stale event nhưng cần lưu evidence và xác định event gap có ý nghĩa hay không.

## 19. Cancellation và thay đổi nghiệp vụ khi Saga đang chạy

Người dùng có thể hủy order khi payment đang pending. Cancellation là command mới, không phải xóa Saga record.

Một flow:
1. Order service nhận CancelOrder và kiểm tra policy.
2. Saga state chuyển CANCEL_REQUESTED nếu cho phép.
3. Ngăn phát bước forward mới.
4. Nếu inventory reserved, gửi release.
5. Nếu payment chưa authorize, cancel attempt hoặc chờ kết quả.
6. Nếu payment đã authorize, void.
7. Nếu payment đã capture, refund.
8. Khi compensation đạt điều kiện, order chuyển CANCELLED.
9. Nếu có side effect không thể tự bù, chuyển MANUAL_ACTION.

Cần xử lý race giữa CancelOrder và PaymentAuthorized. Cả hai event có thể tới gần nhau. Dùng optimistic locking/row lock và state machine để chỉ một transition hợp lệ; nếu payment authorized sau cancellation, phát command void theo đúng payment reference.

## 20. Saga versioning và deploy

Saga có thể chạy trong nhiều phút/giờ/ngày. Khi deploy code mới, những Saga cũ có thể vẫn đang ở step giữa.

Cần:
- Lưu workflow version.
- Giữ handler/transition tương thích cho version đang chạy.
- Version event/command schema.
- Không đổi ý nghĩa state cũ mà không migration.
- Có chiến lược migrate in-flight Saga.
- Deploy consumer tương thích trước producer.
- Theo dõi số Saga theo workflow version và tuổi.

Nếu code mới không hiểu state `PAYMENT_UNKNOWN` do workflow cũ tạo, deployment có thể làm kẹt giao dịch. Một lựa chọn là versioned orchestrator handlers hoặc workflow definition versioning của engine.

## 21. Chọn message broker và workflow engine

Saga có thể được triển khai bằng:
- Kafka/RabbitMQ/cloud queue cho command/event.
- Database outbox/inbox.
- Orchestrator tự xây.
- Durable workflow engine/state machine.
- Managed workflow service.

Tiêu chí:
- Durable state và timer.
- Retry/backoff/compensation.
- Exactly-once không nên giả định xuyên toàn bộ external side effect.
- Message ordering/partitioning.
- Schema registry và compatibility.
- Visibility vào từng execution.
- Replay và audit.
- Versioning in-flight workflows.
- Operational cost, vendor lock-in và team expertise.

Broker chỉ vận chuyển message; nó không tự cung cấp business Saga semantics. Workflow engine quản lý state/step nhưng vẫn cần local transaction, idempotency và domain compensation.

## 22. Kiểm thử Saga theo failure matrix

Không chỉ test happy path. Tối thiểu:

| Điểm lỗi | Điều kiện mô phỏng | Kết quả kỳ vọng |
| --- | --- | --- |
| Create order | API retry cùng idempotency key | Một order/Saga |
| Reserve inventory | Không đủ stock | Order rejected, không gọi payment |
| Reserve inventory | Message duplicate | Một reservation |
| Reserve inventory | DB commit xong nhưng ACK mất | Redelivery không tăng reserved lần hai |
| Payment | Declined | Release reservation |
| Payment | Timeout trước provider xử lý | Reconcile hoặc retry cùng key |
| Payment | Provider authorize nhưng response mất | Không charge lần hai; query/callback xác nhận |
| Order confirm | DB tạm lỗi | Retry local transition idempotent |
| Compensation | Release inventory lỗi | Saga COMPENSATING, retry/alert |
| Compensation | Refund lỗi | REFUND_PENDING/MANUAL_ACTION |
| Timeout | Payment result đến sau timeout | Guarded transition/void/reconcile |
| Cancellation | Cancel race với payment success | Không confirm sai; void/refund |
| Orchestrator | Pod restart | Saga resume từ persisted state |
| Broker | Consumer lag/DLQ | Alert, replay có kiểm soát |
| Deploy | Old Saga chạy qua version mới | Handler tương thích hoặc migration |
| Event order | Event cũ đến sau event mới | Không rollback state version |

### 22.1. Contract tests

Test command/event schema giữa producer và consumer:
- Required/optional fields.
- Version compatibility.
- Unknown enum values.
- Amount/currency precision.
- Tenant and aggregate identity.
- Correlation/causation IDs.
- Backward/forward compatibility theo policy.

### 22.2. Integration tests

Dùng database và broker test thực tế hoặc container/emulator tương thích để kiểm tra:
- Transaction commit/outbox.
- Duplicate delivery.
- Inbox atomicity.
- Lock/version conflict.
- Reservation concurrency.
- Timeout và redelivery.
- Restart giữa các bước.

Mock đơn thuần không thể chứng minh database isolation, unique constraint, transaction semantics hoặc broker ACK behavior.

### 22.3. Chaos/failure injection

Trong môi trường an toàn:
- Kill orchestrator sau khi commit outbox.
- Drop response từ payment provider.
- Pause consumer và tạo backlog.
- Làm database unavailable.
- Delay webhook.
- Duplicate/reorder event.
- Expire reservation trong khi payment pending.

Đo thời gian phục hồi, số Saga cần manual action và khả năng đối soát. Không thử phá production nếu không có phạm vi, quyền và kế hoạch giới hạn tác động.

## 23. Observability và vận hành Saga

Mỗi Saga cần truy vấn được theo:
- sagaId.
- orderId.
- tenantId theo quyền truy cập.
- workflow version.
- current state/status.
- current step.
- started/updated/deadline timestamps.
- retry/compensation count.
- last error classification.
- external payment/reservation references.

Metrics:
- Saga started/completed/failed.
- Saga duration p50/p95/p99.
- Running Saga age.
- Step duration và timeout rate.
- Compensation success/failure.
- Payment UNKNOWN count/age.
- Reservation expiry count.
- DLQ depth/oldest message age.
- Manual action backlog.
- Duplicate event count.
- Order confirmation rate.

Không đưa orderId, sagaId hoặc userId vào metric labels nếu cardinality lớn; dùng logs/traces và searchable structured fields có access control.

### 23.1. Dashboard theo trạng thái

Một dashboard hữu ích:
- Số Saga theo state.
- Saga lâu hơn ngưỡng theo step.
- Payment UNKNOWN chờ reconciliation.
- Reservation ACTIVE sắp hết hạn.
- Compensation đang retry.
- DLQ và consumer lag.
- External provider availability/latency.
- Order confirmed rate.

### 23.2. Alert theo business impact

Không page chỉ vì một event duplicate nếu dedup hoạt động đúng. Nên alert khi:
- Payment UNKNOWN tồn tại quá lâu.
- Reservation không được release đúng hạn.
- Compensation thất bại liên tiếp.
- Saga stuck vượt deadline.
- Confirmed order không có payment reference theo invariant.
- Payment đã capture nhưng order chưa confirm.
- DLQ tăng hoặc oldest age vượt SLA.

## 24. Security và dữ liệu nhạy cảm

Saga event và state có thể chứa order details, tenant, payment reference và dữ liệu cá nhân. Cần:
- Event payload tối thiểu.
- Tokenization/provider reference thay vì card data.
- TLS/mTLS và broker ACL.
- IAM least privilege theo producer/consumer.
- Tenant authorization khi truy vấn Saga status.
- Encryption at rest và key rotation.
- Retention/erasure policy cho outbox, inbox, DLQ và logs.
- Redaction trong logs/traces.
- Audit cho operator retry/compensation/override.

Không cho client gửi sagaId rồi đọc bất kỳ Saga nào. API GET /orders/{id}/status phải kiểm tra quyền truy cập resource và tenant scope.

## 25. API cho client theo dõi tiến trình

Nếu flow không hoàn tất ngay trong HTTP deadline, trả 202:

~~~http
POST /api/v1/orders
Idempotency-Key: create-order-tenant42-abc
Content-Type: application/json

{
  "items": [
    {"sku": "SKU-100", "quantity": 2}
  ],
  "currency": "VND"
}
~~~

Response:

~~~http
HTTP/1.1 202 Accepted
Location: /api/v1/orders/order-501
Retry-After: 2
Content-Type: application/json

{
  "orderId": "order-501",
  "status": "PENDING",
  "sagaStatus": "RUNNING"
}
~~~

Client có thể poll status hoặc nhận webhook/notification khi terminal. Cần rate limit polling, cache policy phù hợp, authorization và contract cho terminal/intermediate states. Không expose internal compensation detail nếu không cần cho client.

## 26. Reconciliation và manual intervention

Không phải mọi failure đều có thể tự xử lý. Một số provider không trả kết quả rõ, refund bị từ chối, inventory record không khớp hoặc message bị poison.

Reconciliation job có thể:
1. Lấy Saga/Payment/Reservation đang ở trạng thái pending/unknown quá lâu.
2. Query authoritative service/provider.
3. So sánh amount, currency, order ID, reservation ID.
4. Xác định transition hợp lệ.
5. Ghi audit và command/event tiếp theo.
6. Không tự sửa khi bằng chứng mâu thuẫn; chuyển manual action.

Operator tool nên:
- Hiển thị toàn bộ timeline và evidence.
- Yêu cầu permission/approval cho action nguy hiểm.
- Chỉ cung cấp các action hợp lệ theo state.
- Ghi người thực hiện, lý do, thời gian và kết quả.
- Có dry-run/preview nếu có thể.
- Không cho chỉnh trực tiếp database để “sửa cho xong”.

## 27. Các lỗi thiết kế phổ biến

1. **Coi Saga như một transaction ACID toàn cục:** không hiểu trạng thái trung gian và compensation.
2. **Không persist Saga state:** orchestrator restart làm mất tiến trình.
3. **Không idempotent:** duplicate event tạo reservation/charge trùng.
4. **Timeout = failure:** payment đã authorize nhưng service đánh dấu failed.
5. **Compensation chỉ là delete record:** bỏ qua side effect đã xảy ra.
6. **Không có reservation expiry:** giữ hàng vô hạn khi Saga kẹt.
7. **Không có reconciliation:** trạng thái unknown không bao giờ được giải quyết.
8. **Dùng local scheduler trong mỗi pod:** timeout command phát trùng.
9. **ACK trước DB commit:** message có thể mất xử lý.
10. **Outbox không có cleanup/monitor:** bảng tăng vô hạn hoặc event kẹt.
11. **Không version workflow:** deploy mới làm hỏng Saga đang chạy.
12. **Compensation chạy mù:** release reservation đã consume hoặc refund sai amount.
13. **Không phân biệt authorize và capture:** order được confirm sai thời điểm.
14. **Chỉ test happy path:** bỏ sót timeout, duplicate, crash và out-of-order.
15. **Không có manual-action owner:** giao dịch lỗi bị bỏ quên.
16. **Dùng một enum cho mọi domain:** state của order/payment/inventory lẫn nhau.
17. **Không theo dõi business outcome:** consumer ACK thành công nhưng order vẫn kẹt.
18. **Event chứa quá nhiều dữ liệu nhạy cảm:** tăng blast radius khi broker/DLQ bị truy cập.

## 28. Kế hoạch triển khai theo giai đoạn

**Giai đoạn 1 — Chốt nghiệp vụ và state machine.** Xác định order, reservation, payment states, invariant, authorize/capture semantics, timeout và terminal outcomes.

**Giai đoạn 2 — Chốt contract.** Thiết kế command/event schema, Saga ID, correlation/causation, idempotency key và version compatibility.

**Giai đoạn 3 — Xây local transaction an toàn.** Inventory reservation atomic, payment attempt persistence, order state transition, unique constraints và optimistic locking.

**Giai đoạn 4 — Thêm outbox/inbox.** Bảo đảm event/command không bị mất khi DB commit và publish lệch nhau; dedup message trong consumer.

**Giai đoạn 5 — Xây orchestrator/workflow.** Persist Saga state, durable timers, retry, timeout, compensation và workflow version.

**Giai đoạn 6 — Xây reconciliation và operator path.** Xử lý UNKNOWN, late response, refund pending và compensation failure.

**Giai đoạn 7 — Observability/security.** Dashboard, trace, alert, tenant authorization, audit, DLQ policy và data retention.

**Giai đoạn 8 — Test failure matrix.** Duplicate, out-of-order, provider timeout after success, crash, concurrent reservation, deploy in-flight Saga.

**Giai đoạn 9 — Rollout có kiểm soát.** Chạy shadow/test flows, canary, đối soát dữ liệu, theo dõi business metrics và chuẩn bị rollback/forward-fix.

## 29. Bài tập thực hành hoàn chỉnh

Một nền tảng thương mại điện tử cần triển khai checkout với:
- order-service sở hữu đơn hàng.
- inventory-service sở hữu tồn kho và reservation.
- payment-service tích hợp cổng thanh toán.
- Kafka truyền command/event.
- PostgreSQL riêng cho mỗi service.
- Notification worker gửi email sau xác nhận.

Yêu cầu thiết kế:

### A. Business model
- Xác định order, inventory reservation, payment attempt.
- Viết invariant và state transition.
- Chốt authorize/capture/refund semantics.

### B. Saga design
- Chọn orchestration hoặc choreography, giải thích trade-off.
- Vẽ sequence diagram forward path.
- Vẽ compensation path khi payment decline.
- Xử lý timeout và PAYMENT_UNKNOWN.

### C. Persistence
- Thiết kế saga table, reservation table, payment attempt table.
- Chọn unique constraints/idempotency keys.
- Dùng outbox/inbox đúng transaction boundary.
- Thiết kế optimistic locking và durable timer.

### D. Inventory
- Bảo vệ oversell khi nhiều order cạnh tranh.
- Reservation TTL, expiry và race với payment callback.
- Phân biệt release, consume và return.

### E. Payment
- Retry cùng provider idempotency key.
- Xử lý callback duplicate/out-of-order.
- Reconciliation khi provider response mất.
- Compensation void/refund theo trạng thái thực.

### F. Operations
- Dashboard theo Saga state.
- Alert cho stuck Saga, UNKNOWN payment, failed compensation và DLQ.
- Runbook manual action và audit.
- Theo dõi order confirmation rate và duration.

### G. Testing
- Viết integration tests cho duplicate event và DB commit/ACK gap.
- Mô phỏng provider authorize thành công nhưng response timeout.
- Mô phỏng orchestrator restart.
- Mô phỏng cancellation race với payment success.
- Kiểm tra không oversell và không charge/refund trùng.

### H. Migration/rollout
- Triển khai tương thích với API hiện tại.
- Đảm bảo event versioning và consumer rollout order.
- Định nghĩa canary metrics, rollback constraints và reconciliation trước khi mở traffic.

Một lời giải đạt yêu cầu phải cho thấy từng bước **ai sở hữu dữ liệu, local transaction nào commit, event nào phát ra, timeout xử lý thế nào, compensation có thể làm gì và khi nào phải chuyển sang manual action**.

## 30. Câu hỏi tự kiểm tra

1. Vì sao Saga cần thiết khi mỗi microservice sở hữu database riêng?
2. Local transaction khác distributed ACID transaction ra sao?
3. Compensation khác rollback SQL thế nào?
4. Khi nào orchestration phù hợp hơn choreography?
5. Vì sao payment timeout không đồng nghĩa payment failed?
6. Reservation cần TTL và trạng thái nào?
7. Release inventory khác consume inventory như thế nào?
8. Tại sao authorize và capture cần được mô hình hóa riêng?
9. Saga ID, correlation ID và causation ID khác nhau ra sao?
10. Transactional outbox giải quyết dual-write window nào?
11. Vì sao outbox vẫn có thể publish duplicate?
12. Inbox cần commit cùng business state như thế nào?
13. Làm sao ngăn hai worker xử lý cùng Saga state đồng thời?
14. Vì sao timeout event cần state/version guard?
15. Điều gì xảy ra nếu payment callback tới sau khi Saga đã bắt đầu compensation?
16. Làm sao xử lý provider side effect đã thành công nhưng response bị mất?
17. Tại sao compensation có thể thất bại và cần manual action?
18. Vì sao một Saga dài cần workflow versioning?
19. Những metric nào cho thấy Saga đang bị kẹt?
20. Làm sao bảo đảm retry không tạo duplicate order, reservation hoặc charge?
21. Vì sao broker ACK phải phối hợp với database commit?
22. Khi nào nên trả 202 Accepted thay vì giữ HTTP request mở?
23. Làm sao xử lý cancellation race với payment success?
24. Những failure scenarios nào phải có integration test?

## 31. Ghi nhớ

- **Saga chia giao dịch nghiệp vụ xuyên service thành các local transaction**; mỗi service commit dữ liệu trong phạm vi ownership của mình.
- Khi một bước không thể tiếp tục, **compensating transaction** thực hiện hành động nghiệp vụ bù; đó không phải rollback vật lý của mọi database.
- Orchestration phù hợp flow dài/nhiều nhánh cần theo dõi tập trung; choreography phù hợp các event flow đơn giản, độc lập.
- Saga cần state bền, step/version, timeout và timer có thể phục hồi sau restart.
- **Duplicate delivery là điều phải thiết kế để chịu được**: command, event, consumer và compensation đều cần idempotency.
- Transactional outbox/inbox giảm rủi ro mất message và dual-write, nhưng không loại bỏ duplicate hoặc external side-effect ambiguity.
- Inventory reservation cần atomic concurrency control, TTL và phân biệt release/consume/return.
- Payment UNKNOWN phải được reconcile; không coi timeout là decline và không retry charge bằng key mới một cách mù quáng.
- Compensation có thể thất bại; cần retry, alert, audit và manual-action owner.
- Saga thành công khi trạng thái nghiệp vụ được xác nhận và đối soát được, không chỉ khi mọi message đã được ACK.
