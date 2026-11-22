# Saga qua Kafka và trách nhiệm xử lý bù

Saga là mẫu thiết kế cho giao dịch nghiệp vụ kéo dài qua nhiều service. Mỗi service thực hiện một transaction cục bộ, phát kết quả cho bước tiếp theo và cung cấp hành động bù khi quy trình không thể hoàn tất. Kafka vận chuyển command và event; ứng dụng chịu trách nhiệm lưu state, xử lý duplicate, timeout, retry và compensation.

Saga không tạo transaction ACID xuyên suốt các service. Compensation là một thao tác nghiệp vụ mới nhằm đưa hệ thống về trạng thái chấp nhận được; nó không phải rollback vật lý hoàn hảo.

## 1. Bài toán giao dịch qua nhiều service

Giả sử khách hàng đặt một đơn hàng. Quy trình cần tạo đơn ở Order Service, giữ hàng ở Inventory Service, xác thực thanh toán ở Payment Service rồi tạo shipment. Mỗi service sở hữu database riêng. Một transaction SQL trong Order Service không thể tự động commit hoặc rollback transaction của Inventory và Payment. Nếu Payment bị từ chối sau khi Inventory đã giữ hàng, hệ thống phải giải phóng phần hàng đã giữ.

~~~mermaid
sequenceDiagram
    participant API
    participant O as Order/Saga Orchestrator
    participant I as Inventory
    participant P as Payment
    API->>O: Create order
    O->>O: Save order, saga and outbox
    O-->>I: ReserveInventory command
    I->>I: Reserve stock, inbox and outbox
    I-->>O: InventoryReserved event
    O->>O: Advance saga state
    O-->>P: AuthorizePayment command
    P->>P: Authorize payment
    P-->>O: PaymentDeclined event
    O->>O: Start compensation
    O-->>I: ReleaseInventory command
    I->>I: Release reservation
    I-->>O: InventoryReleased event
    O->>O: Mark saga COMPENSATED
~~~

## 2. Orchestration và choreography

### Orchestration

Một orchestrator lưu state machine và gửi command đến từng service. Service thực hiện công việc rồi trả event kết quả. Orchestrator quyết định bước tiếp theo hoặc bắt đầu compensation.

~~~mermaid
flowchart TD
    O["Saga Orchestrator + State Store"] -->|ReserveInventory command| I["Inventory Service"]
    I -->|InventoryReserved or InventoryRejected| O
    O -->|AuthorizePayment command| P["Payment Service"]
    P -->|PaymentAuthorized or PaymentDeclined| O
    O -->|CreateShipment command| S["Shipping Service"]
    S -->|ShipmentCreated or ShipmentRejected| O
    O -->|Compensation commands| I
    O -->|Compensation commands| P
~~~

Ưu điểm:

- Luồng nghiệp vụ và thứ tự step được nhìn thấy tại một nơi.
- Dễ xác định step hiện tại, timeout, retry và compensation.
- Có thể quản lý deadline và trạng thái cuối tập trung.
- Service tham gia chỉ cần xử lý command và phát event kết quả.

Hạn chế:

- Orchestrator là thành phần nghiệp vụ quan trọng cần scale và phục hồi.
- Nếu chứa mọi business rule, nó có thể thành bottleneck và tạo coupling.
- Cần quản lý state machine, version và concurrency khi nhiều event của cùng Saga đến đồng thời.

Orchestrator không nên gọi đồng bộ trực tiếp mọi service rồi giữ HTTP request mở nhiều phút. Nó nên phát command qua Kafka, lưu trạng thái và tiếp tục khi nhận event.

### Choreography

Không có orchestrator trung tâm. Mỗi service subscribe event của service trước, thực hiện local transaction rồi phát event tiếp theo.

~~~mermaid
flowchart LR
    O["Order Service"] -->|"OrderCreated"| I["Inventory Service"]
    I -->|"InventoryReserved"| P["Payment Service"]
    P -->|"PaymentAuthorized"| S["Shipping Service"]
    P -->|"PaymentDeclined"| I
    I -->|"InventoryReleased"| O
~~~

Ưu điểm:

- Các service ít phụ thuộc vào một bộ điều phối trung tâm.
- Luồng đơn giản có thể mở rộng bằng cách thêm subscriber.
- Mỗi service sở hữu quyết định và dữ liệu của mình.

Hạn chế:

- Luồng nghiệp vụ bị phân tán qua nhiều topic và consumer.
- Khó nhìn toàn bộ trạng thái Saga nếu thiếu correlation, event history và state projection.
- Vòng lặp event hoặc phụ thuộc ngầm có thể làm flow khó hiểu.
- Timeout, retry và compensation phải được thiết kế rõ ở từng service hoặc process manager.

Choreography không có nghĩa là không cần lưu state. Service vẫn cần persistence và idempotency nếu phải nhớ event đã nhận, lệnh đã phát hoặc bước cần bù sau restart.

### So sánh

| Tiêu chí | Orchestration | Choreography |
|---|---|---|
| Điều khiển flow | Orchestrator gửi command | Service phản ứng với event |
| Trạng thái toàn Saga | Tập trung | Phân tán, cần projection/audit |
| Độ dễ quan sát | Step tập trung | Cần correlation và tracing tốt |
| Coupling | Service biết command contract | Service biết event contract của service khác |
| Phù hợp | Flow dài, nhiều nhánh, bù phức tạp | Flow ngắn, ít nhánh, event rõ |
| Rủi ro | Orchestrator phình to | Khó truy vết và đổi thứ tự |

Chọn orchestration khi quy trình có nhiều nhánh, deadline, compensation nhiều bước hoặc cần một nơi chịu trách nhiệm trạng thái toàn cục. Chọn choreography khi các phản ứng độc lập, đơn giản và event là hợp đồng domain tự nhiên. Mỗi Saga cụ thể cần một nguồn quyết định rõ ràng.

## 3. Phân biệt command và event

Command và event đều có thể được gửi qua Kafka, nhưng ý nghĩa khác nhau:

| Đặc điểm | Command | Event |
|---|---|---|
| Ý nghĩa | Yêu cầu thực hiện hành động | Sự kiện đã xảy ra |
| Cách đặt tên | Mệnh lệnh: `ReserveInventory` | Sự thật đã xảy ra: `InventoryReserved` |
| Người nhận | Một service/owner chịu trách nhiệm | Có thể có nhiều subscriber |
| Kết quả | Accepted, rejected hoặc failed | Fact đã được ghi nhận |
| Retry | Cùng command ID theo idempotency policy | Consumer dedupe theo event ID |

Ví dụ: `ReserveInventory` là command gửi đến Inventory Service; `InventoryReserved` là event phát sau khi giữ hàng thành công; `ReleaseInventory` là command bù; `InventoryReleased` xác nhận reservation đã được giải phóng.

Không phát `InventoryReserved` trước khi transaction giữ hàng commit. Nếu phát trước rồi database rollback, service khác có thể tin vào một việc chưa xảy ra. Command cần owner, timeout, kết quả và retry policy; event mô tả fact bất biến, không mang nghĩa “hãy làm điều này”.

## 4. ID và message envelope

| ID | Mục đích |
|---|---|
| `sagaId` | Định danh một Saga instance từ đầu đến cuối |
| `correlationId` | Liên kết request/message cùng business flow hoặc trace |
| `causationId` | Định danh command/event trực tiếp gây ra message hiện tại |
| `commandId` | Idempotency key của một command |
| `eventId` | Định danh duy nhất của event để dedupe |
| `aggregateId` | Entity nghiệp vụ như `orderId` |
| `stepId` | Định danh step trong Saga |

Không dùng correlation ID thay cho event ID. Một Saga có nhiều event cùng correlation ID; inbox cần dedupe theo event ID/message ID duy nhất. Không dùng saga ID thay command ID nếu một Saga có thể gửi nhiều command cùng loại.

Ví dụ command:

~~~json
{
  "messageType": "ReserveInventory",
  "schemaVersion": 1,
  "commandId": "cmd-8b2f",
  "sagaId": "saga-7d91",
  "correlationId": "req-92a4",
  "causationId": "evt-order-created-17",
  "stepId": "reserve-inventory",
  "orderId": "order-42",
  "deadlineAt": "2026-11-20T10:15:00Z",
  "items": [{"sku": "SKU-1", "quantity": 2}]
}
~~~

Ví dụ event:

~~~json
{
  "messageType": "InventoryReserved",
  "schemaVersion": 1,
  "eventId": "evt-inventory-reserved-51",
  "sagaId": "saga-7d91",
  "correlationId": "req-92a4",
  "causationId": "cmd-8b2f",
  "stepId": "reserve-inventory",
  "orderId": "order-42",
  "reservationId": "reservation-100",
  "occurredAt": "2026-11-20T10:12:15Z"
}
~~~

Envelope cần schema version, timestamp và identifier phù hợp. Không đưa credential, dữ liệu thanh toán nhạy cảm hoặc thông tin cá nhân không cần thiết vào event.

## 5. Kafka key và ordering

Với Saga orchestration, thường dùng `sagaId` làm Kafka key cho message của Saga để chúng vào cùng partition trong một topic. Nếu state được phân vùng theo order, có thể dùng `orderId`; lựa chọn phải thống nhất với ownership của state.

Kafka bảo đảm thứ tự trong một partition, không bảo đảm thứ tự tổng thể giữa hai partition, hai topic, hai producer độc lập hoặc giữa database commit và Kafka publish.

Không giả định `PaymentAuthorized` luôn đến trước timeout event chỉ vì payment xảy ra trước theo thời gian nghiệp vụ. State machine phải kiểm tra `stepId`, `sagaVersion`, trạng thái hiện tại và transition hợp lệ.

Cùng key trên nhiều topic không tạo thứ tự toàn cục xuyên các topic. Dùng version/sequence để loại bỏ event cũ hoặc xử lý event đến muộn. Tăng partition count có thể đổi mapping key sang partition mới; nếu ordering quan trọng, cần migration plan.

## 6. State machine và persistence

Saga state phải được lưu bền vững ngoài memory consumer. Sau restart, service cần biết Saga ở trạng thái nào, step nào thành công/đang chờ, command ID nào đã gửi, attempt count, next retry time, deadline, step nào cần bù, version state và lý do thất bại.

Ví dụ bảng Saga:

~~~sql
CREATE TABLE saga_instance (
    saga_id          VARCHAR(100) PRIMARY KEY,
    order_id         VARCHAR(100) NOT NULL,
    correlation_id   VARCHAR(100) NOT NULL,
    saga_type        VARCHAR(80) NOT NULL,
    status           VARCHAR(40) NOT NULL,
    current_step     VARCHAR(80),
    version          BIGINT NOT NULL,
    deadline_at      TIMESTAMP WITH TIME ZONE,
    created_at       TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at       TIMESTAMP WITH TIME ZONE NOT NULL,
    failure_code     VARCHAR(100),
    failure_detail   TEXT
);
~~~

Ví dụ bảng step:

~~~sql
CREATE TABLE saga_step (
    saga_id          VARCHAR(100) NOT NULL,
    step_id          VARCHAR(80) NOT NULL,
    status           VARCHAR(40) NOT NULL,
    command_id       VARCHAR(100),
    attempt_count    INTEGER NOT NULL DEFAULT 0,
    next_attempt_at  TIMESTAMP WITH TIME ZONE,
    completed_at     TIMESTAMP WITH TIME ZONE,
    compensation_id  VARCHAR(100),
    last_error       TEXT,
    PRIMARY KEY (saga_id, step_id)
);
~~~

Version hỗ trợ optimistic locking. Mỗi transition phải kiểm tra version hoặc dùng row lock để hai consumer instance không cùng advance một Saga. Có thể lưu bảng history/audit append-only để truy vết transition; không chỉ ghi đè trạng thái mới nhất.

Các trạng thái Saga thường dùng gồm `STARTED`, `RUNNING`, `WAITING`, `COMPENSATING`, `COMPLETED`, `COMPENSATED` và `FAILED_MANUAL_REVIEW`. Trạng thái step nên chi tiết hơn: `PENDING`, `COMMAND_SENT`, `SUCCEEDED`, `RETRY_WAIT`, `TIMED_OUT_UNKNOWN`, `COMPENSATING`, `COMPENSATED` hoặc `FAILED`. Tách trạng thái Saga và trạng thái step giúp biết toàn quy trình đang ở đâu và side effect nào đã xảy ra.

| State hiện tại | Input | State tiếp theo | Hành động |
|---|---|---|---|
| `STARTED` | Saga created | `RUNNING` | Gửi `ReserveInventory` |
| `RUNNING/RESERVING` | `InventoryReserved` | `RUNNING/PAYING` | Gửi `AuthorizePayment` |
| `RUNNING/PAYING` | `PaymentAuthorized` | `RUNNING/SHIPPING` | Gửi `CreateShipment` |
| `RUNNING/PAYING` | `PaymentDeclined` | `COMPENSATING` | Gửi `ReleaseInventory` |
| `RUNNING/SHIPPING` | `ShipmentCreated` | `COMPLETED` | Xác nhận order |
| `COMPENSATING` | `InventoryReleased` | `COMPENSATED` | Kết thúc Saga |

Event không khớp state có thể là duplicate, event cũ, đến sớm, đến muộn hoặc lỗi contract. Không bỏ qua im lặng: ghi nhận, phân loại và quyết định ignore có audit, retry hoặc manual review.

## 7. Transaction boundary và dual-write

Mỗi bước Saga nên là transaction cục bộ ngắn:

1. Kiểm tra command/event đã xử lý chưa.
2. Kiểm tra điều kiện nghiệp vụ.
3. Cập nhật database của service.
4. Ghi outbox message trong cùng database transaction.
5. Commit.

Không giữ database lock trong lúc chờ Kafka hoặc service khác. Không mở transaction rồi đợi payment response hoặc shipment completion.

Nếu code commit database rồi gọi `KafkaTemplate.send()`:

- Database commit thành công nhưng process crash trước publish: state đã đổi, event bị mất.
- Publish thành công nhưng database rollback: event mô tả thay đổi chưa commit.
- Publish timeout: producer không biết broker đã nhận record hay chưa; retry có thể tạo duplicate.

Hai hệ thống không tự tạo atomic transaction chỉ vì hai lời gọi nằm trong cùng method Java.

## 8. Transactional Outbox

Outbox ghi business state và message cần phát vào cùng database transaction. Relay hoặc CDC connector đọc outbox rồi publish sang Kafka.

~~~mermaid
flowchart LR
    A["Service handler"] --> T["Local DB transaction"]
    T --> D["Business tables"]
    T --> O["Outbox table"]
    O --> R["Outbox relay or CDC"]
    R --> K["Kafka topic"]
    K --> C["Next service"]
~~~

~~~sql
CREATE TABLE outbox_message (
    message_id       VARCHAR(100) PRIMARY KEY,
    aggregate_id     VARCHAR(100) NOT NULL,
    aggregate_seq    BIGINT,
    message_type     VARCHAR(120) NOT NULL,
    topic_name       VARCHAR(200) NOT NULL,
    message_key      VARCHAR(200) NOT NULL,
    payload          JSONB NOT NULL,
    status           VARCHAR(20) NOT NULL DEFAULT 'NEW',
    created_at       TIMESTAMP WITH TIME ZONE NOT NULL,
    published_at     TIMESTAMP WITH TIME ZONE
);
~~~

Relay đọc row `NEW`, gửi record đến Kafka và đánh dấu `PUBLISHED`. Nếu relay crash sau khi Kafka nhận record nhưng trước khi cập nhật status, record có thể được gửi lại. Outbox loại bỏ nguy cơ mất message do dual-write nhưng không bảo đảm consumer chỉ nhận một lần. Consumer vẫn cần inbox/idempotency.

CDC như Debezium Outbox Event Router có thể đọc thay đổi outbox từ transaction log database. Polling relay đơn giản hơn nhưng phải quản lý locking, batch, retry, ordering và cleanup row. Event ID phải ổn định qua lần publish lại.

Nếu cần giữ thứ tự event của aggregate, lưu `aggregate_seq` và publish theo sequence. Relay phải tránh nhiều worker phát sequence của cùng aggregate theo thứ tự ngược. Dùng `aggregate_id` làm Kafka key chỉ giúp khi relay đã gửi theo đúng thứ tự.

## 9. Inbox và idempotent consumer

Kafka thường được xử lý theo semantics at-least-once ở tầng ứng dụng: consumer có thể xử lý lại nếu process crash sau khi commit database nhưng trước khi commit offset. Inbox lưu message ID đã xử lý trong cùng transaction với side effect.

~~~sql
CREATE TABLE inbox_message (
    subscriber_id    VARCHAR(120) NOT NULL,
    message_id       VARCHAR(100) NOT NULL,
    processed_at     TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (subscriber_id, message_id)
);
~~~

Một consumer xử lý:

1. Bắt đầu DB transaction.
2. Insert subscriber ID và message ID vào inbox.
3. Nếu conflict/đã tồn tại, kết thúc mà không lặp side effect.
4. Nếu mới, cập nhật business data và ghi outbox response/event.
5. Commit DB transaction.
6. Sau đó listener mới hoàn tất để offset được commit theo cấu hình container.

Nếu process crash sau bước 5 nhưng trước bước 6, Kafka giao lại record; inbox phát hiện duplicate và không lặp side effect.

Idempotency key phải đại diện cho một command/event cụ thể. Không dùng payload hash nếu hai command hợp lệ có cùng payload nhưng là hai lần thực hiện khác nhau.

## 10. Compensation là hành động nghiệp vụ, không phải rollback

| Step thành công | Compensation có thể dùng | Giới hạn |
|---|---|---|
| Giữ hàng | Giải phóng reservation | Hàng có thể đã đóng gói hoặc chuyển trạng thái |
| Authorize payment | Void authorization | Authorization có thể đã capture hoặc hết hạn |
| Capture payment | Refund | Refund có thể chậm, mất phí hoặc không hoàn đủ |
| Tạo shipment | Hủy shipment | Không thể hủy nếu hàng đã giao cho hãng vận chuyển |
| Áp coupon | Khôi phục quota coupon | Chính sách quota và thời hạn có thể đã đổi |
| Gửi email | Gửi email đính chính | Không thể thu hồi email đã gửi |

Compensation không nhất thiết đảo ngược chính xác mọi tác động. Hoàn tiền không làm thời gian khách đã chờ biến mất; hủy shipment có thể phát sinh phí; email đã gửi không thể xóa khỏi inbox.

Thiết kế compensation cần trả lời business state nào được khôi phục, side effect nào không thể đảo ngược, có cần hoàn tiền/đền bù/thông báo khách không, compensation có thể thất bại hoặc timeout không, chạy hai lần có an toàn không, và step gốc đến muộn sau khi Saga bắt đầu bù thì xử lý thế nào.

Nếu các step thành công theo thứ tự A → B → C và C thất bại, compensation thường chạy B⁻¹ → A⁻¹. Nhưng thứ tự bù phải theo dependency nghiệp vụ, không chỉ đảo danh sách máy móc. Một số compensation có thể chạy song song nếu độc lập; một số phải tuần tự để tránh vi phạm invariant.

Không bù step chưa thành công. Nếu trạng thái step chưa rõ vì timeout, cần truy vấn trạng thái nghiệp vụ hoặc gửi command idempotent để xác định kết quả trước khi quyết định bù.

## 11. Retry, timeout và lỗi không rõ kết quả

| Nhóm lỗi | Ví dụ | Hành động |
|---|---|---|
| Tạm thời | Network reset, broker unavailable, database deadlock | Retry có giới hạn và backoff |
| Quá tải | Rate limit, quota, downstream throttling | Backoff, giảm concurrency hoặc chờ quota |
| Nghiệp vụ từ chối | Không đủ hàng, thẻ bị từ chối | Không retry mù; chuyển nhánh business/compensation |
| Dữ liệu không hợp lệ | Schema sai, thiếu field | Không retry vô hạn; quarantine/DLQ |
| Kết quả không rõ | Request timeout sau khi service có thể đã commit | Query theo idempotency key hoặc retry cùng command ID |
| Lỗi vĩnh viễn | Resource không tồn tại, policy cấm | Dừng step theo business policy |

Retry dùng exponential backoff và jitter:

\[
delay_n = \min(maxDelay,\ baseDelay \times 2^n) + jitter
\]

Giới hạn số lần retry, tổng thời gian retry và deadline toàn Saga. Retry topic hoặc scheduler có thể trì hoãn lần thử sau; không giữ consumer thread bằng `Thread.sleep()` trong khi chờ.

### Timeout không đồng nghĩa step thất bại

Timeout chỉ nói orchestrator chưa nhận kết quả trong thời hạn. Service đích có thể đã hoàn tất side effect nhưng event phản hồi bị chậm hoặc mất.

Khi timeout:

1. Đánh dấu step `TIMED_OUT/UNKNOWN`, không vội kết luận side effect chưa xảy ra.
2. Query service đích bằng command ID/idempotency key nếu có API tra cứu.
3. Nếu chưa xử lý, gửi lại cùng command ID để service dedupe.
4. Nếu đã thành công, tiếp tục Saga hoặc bắt đầu compensation theo policy.
5. Nếu trạng thái không thể xác định, chuyển manual review thay vì thực hiện bù mù.

Timeout event và success event có thể đến đồng thời. State transition phải dùng version/CAS hoặc row lock để chỉ một nhánh thắng. Event đến sau cần được xử lý như late event có audit.

### Lịch timeout

Kafka không cung cấp timer tổng quát cho mỗi message. Có thể dùng bảng deadline trong database và scheduler/poller, delay topic theo bucket thời gian, retry topic hoặc scheduler bên ngoài phát timeout command/event.

Không giữ một partition consumer bị chặn bởi message phải chờ nhiều phút. Timer cần bền vững qua restart, có idempotency và kiểm tra Saga vẫn ở đúng step trước khi phát timeout.

## 12. Duplicate, out-of-order và late event

Một Saga có thể nhận cùng event nhiều lần, event của step cũ sau khi Saga tiến bước, timeout sau khi step thành công, success event sau khi compensation bắt đầu hoặc hai event kết quả khác nhau do retry/race.

Quy tắc:

1. Dedupe theo event ID/message ID bằng inbox.
2. Kiểm tra saga ID, step ID và command ID.
3. Kiểm tra state hiện tại và version.
4. Chỉ áp dụng transition hợp lệ.
5. Lưu event đến muộn vào audit.
6. Nếu late success chứng minh side effect đã xảy ra sau khi bù bắt đầu, phát compensation bổ sung hoặc chuyển manual review.

Không chỉ dựa vào Kafka offset để xác định event mới/cũ ở cấp nghiệp vụ. Offset chỉ có thứ tự trong một partition; nó không mô tả thứ tự giữa các topic hoặc trạng thái database.

## 13. Ví dụ Saga orchestration bằng Java và Spring Kafka

Ví dụ sau minh họa ranh giới giữa listener, state machine, outbox và command. Repository/DTO là phần domain adapter cần triển khai theo database và schema của ứng dụng.

### Message contract

~~~java
public record ReserveInventory(
    String commandId,
    String sagaId,
    String correlationId,
    String causationId,
    String orderId,
    List<OrderLine> lines
) {}

public record InventoryReserved(
    String eventId,
    String sagaId,
    String correlationId,
    String causationId,
    String orderId,
    String reservationId
) {}

public record PaymentDeclined(
    String eventId,
    String sagaId,
    String correlationId,
    String causationId,
    String orderId,
    String reasonCode
) {}

public record ReleaseInventory(
    String commandId,
    String sagaId,
    String correlationId,
    String causationId,
    String orderId,
    String reservationId
) {}
~~~

Command có command ID ổn định để Inventory Service dedupe. Event có event ID riêng để orchestrator dedupe. Causation ID liên kết response với command đã tạo ra nó.

### Bắt đầu Saga trong Order Service

~~~java
@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final SagaRepository sagas;
    private final OutboxRepository outbox;

    public OrderApplicationService(
        OrderRepository orders,
        SagaRepository sagas,
        OutboxRepository outbox
    ) {
        this.orders = orders;
        this.sagas = sagas;
        this.outbox = outbox;
    }

    @Transactional
    public String placeOrder(CreateOrder request) {
        String sagaId = UUID.randomUUID().toString();
        String correlationId = request.correlationId();
        String orderId = UUID.randomUUID().toString();
        String commandId = UUID.randomUUID().toString();

        orders.createPending(orderId, request);
        sagas.insertStarted(sagaId, orderId, correlationId, "RESERVING_INVENTORY");

        ReserveInventory command = new ReserveInventory(
            commandId, sagaId, correlationId,
            "order-created:" + orderId, orderId, request.lines()
        );
        outbox.append(
            commandId, "inventory.commands", sagaId,
            "ReserveInventory", command
        );
        return sagaId;
    }
}
~~~

Order row, Saga state và outbox command được ghi trong cùng database transaction. Relay publish command sau commit. API có thể trả `202 Accepted` cùng order/saga ID; trạng thái cuối được truy vấn qua API hoặc notification khi Saga hoàn tất.

### Nhận event và advance state

~~~java
@Component
public class SagaEventListener {
    private final SagaApplicationService sagaService;

    public SagaEventListener(SagaApplicationService sagaService) {
        this.sagaService = sagaService;
    }

    @KafkaListener(topics = "saga.events", groupId = "order-saga")
    public void onSagaEvent(SagaEventEnvelope event) {
        sagaService.handle(event);
    }
}
~~~

Một listener nhận envelope rồi dispatch theo message type giúp tránh lỗi khai báo nhiều listener cùng group/topic trong khi mong đợi tất cả listener nhận cùng record. Một consumer group phân phối record cho member; nó không broadcast mỗi record tới mọi listener. Cấu hình topic/group production nên externalize qua properties.

### Xử lý event bằng transaction cục bộ

~~~java
@Service
public class SagaApplicationService {
    private final InboxRepository inbox;
    private final SagaRepository sagas;
    private final OutboxRepository outbox;
    private final OrderRepository orders;

    public SagaApplicationService(
        InboxRepository inbox,
        SagaRepository sagas,
        OutboxRepository outbox,
        OrderRepository orders
    ) {
        this.inbox = inbox;
        this.sagas = sagas;
        this.outbox = outbox;
        this.orders = orders;
    }

    @Transactional
    public void onInventoryReserved(InventoryReserved event) {
        if (!inbox.insertIfAbsent("order-saga", event.eventId())) {
            return;
        }
        Saga saga = sagas.findForUpdate(event.sagaId()).orElseThrow();
        if (!saga.isWaitingFor("RESERVING_INVENTORY")) {
            sagas.recordLateOrUnexpectedEvent(event.sagaId(), event.eventId());
            return;
        }

        saga.markStepSucceeded("RESERVING_INVENTORY", event.reservationId());
        saga.moveTo("AUTHORIZING_PAYMENT");
        sagas.save(saga);

        AuthorizePayment command = AuthorizePayment.forSaga(
            saga.id(), saga.orderId(), event.eventId()
        );
        outbox.append(
            command.commandId(), "payment.commands", saga.id(),
            "AuthorizePayment", command
        );
    }

    @Transactional
    public void onPaymentDeclined(PaymentDeclined event) {
        if (!inbox.insertIfAbsent("order-saga", event.eventId())) {
            return;
        }
        Saga saga = sagas.findForUpdate(event.sagaId()).orElseThrow();
        if (!saga.isWaitingFor("AUTHORIZING_PAYMENT")) {
            sagas.recordLateOrUnexpectedEvent(event.sagaId(), event.eventId());
            return;
        }

        saga.markStepFailed("AUTHORIZING_PAYMENT", event.reasonCode());
        saga.moveTo("COMPENSATING_INVENTORY");
        sagas.save(saga);

        ReleaseInventory compensation = ReleaseInventory.forSaga(
            saga.id(), saga.orderId(), saga.reservationId(), event.eventId()
        );
        outbox.append(
            compensation.commandId(), "inventory.commands", saga.id(),
            "ReleaseInventory", compensation
        );
        orders.markPaymentDeclined(saga.orderId(), event.reasonCode());
    }
}
~~~

Đây là skeleton minh họa. Inbox insert cần unique constraint trong DB; findForUpdate hoặc optimistic version phải bảo vệ concurrent transition; outbox append phải tham gia cùng transaction. Event không khớp state cần được phân loại late/duplicate/unexpected thay vì bỏ qua không log.

### Consumer của Inventory Service

~~~java
@KafkaListener(topics = "inventory.commands", groupId = "inventory")
public void reserveInventory(ReserveInventory command) {
    inventoryApplicationService.reserve(command);
}

@Service
public class InventoryApplicationService {
    private final InboxRepository inbox;
    private final InventoryRepository inventory;
    private final ReservationRepository reservations;
    private final OutboxRepository outbox;

    @Transactional
    public void reserve(ReserveInventory command) {
        if (!inbox.insertIfAbsent("inventory-reserve", command.commandId())) {
            return;
        }
        ReservationResult result =
            inventory.reserveAtomically(command.orderId(), command.lines());

        if (result.success()) {
            reservations.save(result.reservation());
            outbox.append(
                "evt-" + command.commandId(), "saga.events", command.sagaId(),
                "InventoryReserved",
                InventoryReserved.from(command, result.reservation())
            );
        } else {
            outbox.append(
                "evt-rejected-" + command.commandId(), "saga.events",
                command.sagaId(), "InventoryRejected",
                InventoryRejected.from(command, result.reason())
            );
        }
    }
}
~~~

Ví dụ giả định `reserveAtomically` bảo đảm không giữ vượt quá tồn kho, ví dụ bằng conditional update/row lock và kiểm tra số row được cập nhật. Không đọc tồn kho rồi update không điều kiện vì hai Saga đồng thời có thể cùng giữ một lượng hàng.

## 14. Compensation trong Java/Spring Kafka

Inventory Service xử lý command bù bằng cùng quy tắc idempotency:

~~~java
@Transactional
public void release(ReleaseInventory command) {
    if (!inbox.insertIfAbsent("inventory-release", command.commandId())) {
        return;
    }

    Reservation reservation =
        reservations.findByIdForUpdate(command.reservationId()).orElseThrow();

    if (reservation.isReleased()) {
        return;
    }
    if (!reservation.canBeReleased()) {
        outbox.append(
            "evt-release-blocked-" + command.commandId(), "saga.events",
            command.sagaId(), "InventoryReleaseBlocked",
            InventoryReleaseBlocked.from(command, reservation.status())
        );
        return;
    }

    inventory.release(reservation);
    reservation.markReleased();
    outbox.append(
        "evt-released-" + command.commandId(), "saga.events",
        command.sagaId(), "InventoryReleased",
        InventoryReleased.from(command, reservation)
    );
}
~~~

Đây là service method rút gọn; listener nên gọi bean service khác để Spring proxy áp dụng `@Transactional` rõ ràng. Code thực tế cần xử lý reservation không tồn tại, đã shipment hoặc đã release; mỗi trạng thái cần kết quả domain rõ ràng.

Nếu reservation không thể release vì hàng đã chuyển sang fulfillment, không được giả vờ compensation thành công. Phát event kết quả phù hợp để orchestrator quyết định hủy shipment, yêu cầu return, hoàn tiền hoặc manual review.

## 15. Spring transaction và Kafka offset

`@Transactional` mặc định không tạo transaction phân tán giữa database và Kafka.

Với listener cập nhật database:

- DB transaction commit business state + inbox + outbox.
- Sau khi listener hoàn tất thành công, container commit Kafka offset theo ack mode/container configuration.
- Nếu process crash giữa DB commit và offset commit, record được giao lại; inbox loại duplicate.
- Nếu DB transaction rollback, listener ném exception để error handler/retry policy xử lý; không ack record như đã thành công.

Kafka producer transaction có thể atomically ghi output records và consumer offsets trong Kafka, nhưng không bao gồm database transaction tùy ý. Kafka EOS không tự bảo vệ side effect trong PostgreSQL, REST API, payment gateway hoặc hệ thống ngoài Kafka.

Không dựa vào hai annotation `@Transactional` để suy luận có atomicity xuyên DB/Kafka. Hãy thiết kế outbox/inbox và xác định rõ ai commit trước, retry ở đâu, dedupe bằng key nào.

## 16. Timeout và retry trong Spring

Có thể lưu deadline trong step state rồi dùng scheduler phát timeout command. Scheduler phải claim row bằng lock/lease để nhiều instance không phát cùng timeout vô hạn.

~~~java
@Scheduled(fixedDelay = 1000)
public void publishDueTimeouts() {
    List<SagaStep> dueSteps =
        stepRepository.claimExpiredSteps(Instant.now(), 100);

    for (SagaStep step : dueSteps) {
        outboxRepository.appendTimeoutIfAbsent(
            step.sagaId(), step.stepId(), step.timeoutGeneration()
        );
    }
}
~~~

`claimExpiredSteps` cần atomic claim/lease và `appendTimeoutIfAbsent` cần unique key. Timeout event phải chứa saga ID, step ID, generation hoặc expected version; handler chỉ áp dụng nếu Saga vẫn chờ đúng generation đó.

Với lỗi transient, có thể dùng Spring Kafka retry topic/backoff hoặc outbox scheduler. Retry cùng command ID để consumer dedupe side effect. Nếu là một lần nghiệp vụ mới, tạo command ID mới nhưng vẫn liên kết saga ID và causation ID.

Không retry lỗi business như “không đủ hàng” vô hạn. Đây là kết quả domain, không phải lỗi hạ tầng.

## 17. Compensation thất bại và manual recovery

Compensation cũng là step phân tán: có command, timeout, retry, idempotency và event kết quả. Nó có thể thất bại do service unavailable, trạng thái nghiệp vụ đã đổi hoặc hệ thống ngoài không hỗ trợ hoàn tác.

Chính sách gợi ý:

1. Retry lỗi transient với giới hạn và backoff.
2. Query trạng thái trước khi retry nếu kết quả trước đó không rõ.
3. Không gửi compensation mới với ID mới chỉ vì producer timeout; giữ idempotency key của cùng hành động bù.
4. Nếu compensation bị từ chối vì business constraint, ghi failure code và chuyển manual review.
5. Alert theo age/amount/criticality của Saga đang bù.
6. Cung cấp thao tác vận hành có audit để retry, skip theo policy hoặc hoàn tất thủ công.

Không đánh dấu Saga `COMPENSATED` chỉ vì đã gửi compensation command. Chỉ hoàn tất khi nhận kết quả bù thành công hoặc có quyết định nghiệp vụ được phê duyệt.

## 18. Chọn đúng ranh giới Outbox/Inbox và Kafka transaction

| Tình huống | Cơ chế phù hợp | Điều được bảo đảm |
|---|---|---|
| DB update và cần phát Kafka event | Transactional Outbox | DB state và outbox row commit cùng nhau |
| Consumer xử lý DB và có thể nhận lại record | Inbox + DB transaction | Side effect DB không lặp theo message ID |
| Kafka consume-transform-produce thuần Kafka | Kafka transaction/EOS | Output Kafka và input offsets có thể commit nguyên tử trong Kafka |
| Gọi external API/payment | Idempotency key + trạng thái request + reconciliation | Giảm duplicate; cần API hỗ trợ idempotency hoặc query trạng thái |
| Gửi email/notification | Outbox + delivery state + dedupe | Retry có kiểm soát; không thể thu hồi side effect đã gửi |

Outbox/inbox không làm external side effect thành exactly-once. Chúng tạo nền tảng at-least-once an toàn hơn bằng stable ID và deduplication. Với payment gateway, gửi payment request ID ổn định và query giao dịch theo ID trước khi quyết định retry hoặc refund.

## 19. Observability cho Saga

Log tối thiểu:

- Saga ID, correlation ID, order ID.
- Event ID/command ID, causation ID, step ID.
- State trước/sau và Saga version.
- Attempt count, retry delay, deadline và timeout generation.
- Compensation action/result.
- Failure code và service sở hữu step.

Không chỉ ghi log “Kafka message processed”. Cần biết message làm Saga nào chuyển từ state nào sang state nào.

Metrics nên có:

| Metric | Ý nghĩa |
|---|---|
| `saga_started_total` | Số Saga bắt đầu |
| `saga_completed_total` | Số Saga hoàn tất |
| `saga_compensated_total` | Số Saga bù thành công |
| `saga_manual_review_total` | Saga cần can thiệp |
| `saga_step_duration_seconds` | Thời gian từng step |
| `saga_age_seconds` | Tuổi của Saga chưa kết thúc |
| `saga_retry_total` | Số lần retry |
| `saga_compensation_failure_total` | Lỗi compensation |
| `outbox_oldest_unpublished_seconds` | Tuổi message outbox chưa publish |
| `inbox_duplicate_total` | Số message bị dedupe |

Không dùng saga ID, order ID hoặc event ID làm metric label vì cardinality tăng không giới hạn. Dùng các ID trong log/trace; metric label nên là step type, service, outcome và error class có cardinality kiểm soát.

Truyền trace context qua Kafka headers. Correlation ID giúp tìm cả Saga; trace/span ID nối các lần xử lý kỹ thuật. Saga có thể kéo dài hàng giờ/ngày, vượt vòng đời một distributed trace; có thể tạo trace mới cho từng step và liên kết bằng span link/correlation ID.

Dashboard nên có số Saga theo state và tuổi, step chờ lâu nhất, retry/DLQ theo service và error class, compensation đang chạy/thất bại, outbox backlog và tuổi row cũ nhất, inbox duplicate rate, consumer lag của topic Saga.

## 20. Runbook vận hành Saga

Khi một Saga không tiến triển:

1. Tìm saga ID hoặc correlation ID trong API/log.
2. Đọc Saga state và version từ state store.
3. Kiểm tra step đang chờ, command ID, attempt count và deadline.
4. Kiểm tra outbox row đã publish chưa; nếu chưa, kiểm tra relay/CDC.
5. Kiểm tra topic/partition/offset và consumer lag của service đích.
6. Tìm event theo causation ID/command ID để xác định service đã thực hiện side effect chưa.
7. Kiểm tra inbox để biết message đã được xử lý trong DB chưa.
8. Nếu timeout, query service sở hữu step theo idempotency key trước khi retry.
9. Nếu cần compensation, xác nhận side effect gốc đã xảy ra và compensation còn hợp lệ.
10. Nếu compensation thất bại hoặc trạng thái không xác định, chuyển `FAILED_MANUAL_REVIEW`, tạo ticket/audit và ngăn Saga retry vô hạn.
11. Sau sửa chữa, ghi operator ID, lý do, command/event ID và state transition mới.

### Payment timeout

- Không kết luận payment thất bại chỉ vì không nhận response.
- Query Payment Service/gateway theo payment request ID.
- Nếu đã authorized, phát bước tiếp theo hoặc void theo policy.
- Nếu chưa xử lý, retry cùng idempotency key.
- Nếu trạng thái gateway không xác định, dừng tự động và manual review để tránh charge hai lần.

### Compensation release inventory timeout

- Query reservation theo reservation ID.
- Nếu đã release, ghi nhận kết quả và advance Saga dù event phản hồi có thể bị mất.
- Nếu chưa release và vẫn hợp lệ, retry cùng compensation ID.
- Nếu hàng đã chuyển fulfillment, không force update tồn kho; chuyển sang quy trình hủy shipment/return hoặc manual review.

## 21. Các lỗi thiết kế thường gặp

- **Dùng Saga như distributed rollback:** compensation là nghiệp vụ mới, không xóa được mọi side effect.
- **Không persist state:** restart làm mất step đang chạy và không biết tiếp tục hay bù.
- **Không có inbox:** redelivery làm giữ hàng, charge hoặc refund nhiều lần.
- **Publish sau DB commit không có outbox:** crash giữa hai thao tác làm mất event.
- **Dùng correlation ID làm event ID:** dedupe nhầm nhiều event hợp lệ của cùng Saga.
- **Retry timeout bằng command ID mới:** side effect cũ có thể đã thành công, dẫn tới thực hiện hai lần.
- **Timeout đồng nghĩa thất bại:** có thể bù một side effect chưa được xác minh.
- **Bỏ qua event đến muộn:** có thể bỏ sót side effect cần compensation.
- **Commit offset trước DB transaction:** crash có thể làm mất xử lý.
- **Giữ DB transaction khi chờ service khác:** lock lâu, deadlock và coupling.
- **Không có deadline toàn Saga:** Saga có thể ở RUNNING vô thời hạn.
- **Không có manual recovery:** compensation thất bại làm trạng thái nghiệp vụ mắc kẹt.
- **Dùng metric label là saga ID:** cardinality tăng không kiểm soát.

## 22. Checklist thiết kế production

- [ ] Chọn orchestration hoặc choreography và xác định owner của flow.
- [ ] Vẽ step, điều kiện thành công/thất bại và compensation cho từng side effect.
- [ ] Phân biệt command và event; command có owner và idempotency key.
- [ ] Định nghĩa saga ID, correlation ID, causation ID, command ID, event ID và step ID.
- [ ] Chọn Kafka key phù hợp để giữ thứ tự trong từng partition.
- [ ] Persist Saga state, step state, attempt, deadline và version.
- [ ] Dùng optimistic locking/row lock để chống concurrent transition.
- [ ] Dùng Outbox cho DB update + Kafka publish.
- [ ] Dùng Inbox/unique constraint cho consumer deduplication.
- [ ] Mỗi local transaction ngắn, không giữ transaction khi chờ service khác.
- [ ] Retry transient có backoff/jitter, max attempts và deadline.
- [ ] Timeout không được coi là bằng chứng side effect chưa xảy ra.
- [ ] Compensation idempotent, có timeout/retry và kết quả riêng.
- [ ] Có xử lý late/out-of-order event và race giữa timeout/success.
- [ ] Có DLQ/quarantine và quy trình replay có kiểm soát.
- [ ] Có manual review/repair cho compensation không thể tự hoàn tất.
- [ ] Có metrics cho Saga age, step duration, outbox backlog và compensation failure.
- [ ] Log/trace có correlation ID nhưng metric label không có ID cardinality cao.
- [ ] Runbook có query theo saga/command/reservation/payment ID.
- [ ] Kiểm thử crash giữa DB commit và Kafka offset commit, duplicate, timeout, late event và compensation failure.

## 23. Bài tập thực hành

1. Thiết kế Saga đặt hàng gồm giữ hàng, authorize payment và tạo shipment. Vẽ cả orchestration và choreography.
2. Định nghĩa command/event envelope có saga ID, correlation ID, causation ID, command ID và event ID.
3. Tạo bảng Saga/step/outbox/inbox trong PostgreSQL và triển khai state transition có optimistic locking.
4. Dùng Spring Kafka listener nhận `InventoryReserved`, ghi inbox, cập nhật Saga và ghi `AuthorizePayment` vào outbox trong một transaction.
5. Cố ý crash sau DB commit nhưng trước Kafka offset commit; xác nhận inbox ngăn side effect lặp.
6. Cố ý timeout Payment Service sau khi payment đã authorized; query theo idempotency key và quyết định tiếp tục/void.
7. Làm `ReleaseInventory` được gửi hai lần; xác nhận compensation idempotent.
8. Gửi event đến muộn sau khi Saga bắt đầu compensation; xác định transition và manual recovery phù hợp.
9. Làm compensation thất bại nhiều lần; xác nhận Saga chuyển manual review và tạo alert.
10. Xây dashboard cho Saga age, step latency, retry, outbox backlog và compensation failure.

Saga qua Kafka là một state machine nghiệp vụ chạy trên nhiều transaction cục bộ. Kafka vận chuyển command/event; database của mỗi service giữ sự thật về side effect của service đó. Outbox/inbox, idempotency, timeout có deadline và compensation có persistence giúp quy trình chịu được crash, redelivery và kết quả không rõ. Thiết kế chỉ hoàn chỉnh khi có đường thành công, đường bù, đường manual recovery và runbook để người vận hành xác minh trạng thái trước khi can thiệp.
