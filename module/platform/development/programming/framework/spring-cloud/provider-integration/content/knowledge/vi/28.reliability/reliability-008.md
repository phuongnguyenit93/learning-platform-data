# Transactional outbox và bù trừ khi không có giao dịch xuyên dịch vụ

Một ứng dụng Spring Boot thường phải cập nhật dữ liệu nghiệp vụ trong database rồi phát message để dịch vụ khác tiếp tục xử lý. Nếu ghi database và publish message là hai thao tác độc lập, hệ thống có thể rơi vào trạng thái chỉ hoàn thành một nửa: đơn hàng đã được tạo nhưng event không được gửi, hoặc message đã được gửi nhưng transaction database rollback.

Các dịch vụ managed như Azure Service Bus, Cosmos DB, AWS SQS, DynamoDB, Google Cloud Pub/Sub và Spanner có transaction hoặc cơ chế đảm bảo riêng, nhưng không có một transaction ACID chung bao trùm mọi database, broker và API bên ngoài trong một workflow thông thường. **Transactional outbox** giải quyết khoảng trống giữa ghi dữ liệu và phát event. **Saga và compensation** quản lý quy trình nghiệp vụ gồm nhiều transaction cục bộ khi không thể rollback toàn bộ hệ thống bằng một transaction duy nhất.

Bài thuộc chương **Độ tin cậy** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích dual-write problem và vì sao database transaction không bao gồm broker publish.
2. Thiết kế outbox record được ghi cùng transaction với business state.
3. Triển khai publisher theo polling/lease hoặc CDC và xử lý publish duplicate.
4. Bảo đảm message có event ID ổn định và consumer idempotent bằng inbox.
5. Phân biệt transactional outbox, transactional messaging, distributed transaction và saga.
6. Thiết kế saga orchestration/choreography với state machine và compensation.
7. Xử lý timeout, unknown outcome, retry và compensation failure.
8. Áp dụng mô hình với Cosmos DB/Service Bus, DynamoDB/Streams/SQS và Spanner/Firestore/Pub/Sub.
9. Tích hợp outbox với Spring Boot, Spring Data và Spring Cloud Stream.
10. Kiểm thử crash window, duplicate publish, partial failure và phục hồi workflow.

## 2. Dual-write problem: hai lần ghi, một khoảng trống

Giả sử Order API cần tạo đơn hàng trong PostgreSQL và gửi event OrderCreated lên broker.

Một cách triển khai ngây thơ:

~~~java
@Transactional
public Order createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(Order.from(command));
    messagePublisher.publish(new OrderCreated(order.getId()));
    return order;
}
~~~

Annotation @Transactional chỉ quản lý transaction của resource được Spring transaction manager tham gia, thường là database. Việc gọi broker không tự động trở thành một phần của transaction đó.

Có hai failure window:

### Database commit thành công, publish thất bại

~~~mermaid
sequenceDiagram
    participant A as Order API
    participant DB as Database
    participant B as Broker
    A->>DB: INSERT order
    DB-->>A: COMMIT
    A->>B: Publish OrderCreated
    B--xA: Timeout / unavailable
    Note over DB: Order tồn tại
    Note over B: Event chưa được xác nhận
~~~

Đơn hàng đã tồn tại nhưng dịch vụ inventory, notification hoặc fulfillment không biết có đơn mới.

### Publish thành công, database rollback

~~~mermaid
sequenceDiagram
    participant A as Order API
    participant DB as Database
    participant B as Broker
    A->>DB: INSERT order
    A->>B: Publish OrderCreated
    B-->>A: Accepted
    A->>DB: COMMIT
    DB--xA: Transaction rollback
    Note over B: Event đã được phát
    Note over DB: Order không tồn tại
~~~

Consumer nhận event tham chiếu tới một đơn hàng không tồn tại.

Đây là **dual-write problem**: hai hệ thống cần được cập nhật như một ý định nghiệp vụ, nhưng không có transaction nguyên tử chung.

### Vì sao không chỉ publish trong @Transactional?

Gọi broker bên trong transaction database không làm cho broker cùng rollback. Nếu database rollback sau khi broker đã nhận message, broker không tự xóa message. Nếu publish trước commit và consumer đọc ngay, consumer có thể truy vấn database trước khi order được commit.

Có thể dùng distributed transaction/XA trong một số hệ sinh thái có hỗ trợ, nhưng không phải lựa chọn phổ quát giữa managed database, cloud broker và HTTP API. Nó tăng coupling và chi phí vận hành; nhiều dịch vụ cloud không tham gia cùng một XA transaction.

## 3. Transactional outbox giải quyết điều gì?

Outbox lưu **ý định phát event** vào chính database chứa business state, trong cùng transaction.

~~~mermaid
flowchart LR
    A[Spring Boot command] --> T[Database transaction]
    T --> O[(Business table)]
    T --> X[(Outbox table)]
    X --> P[Outbox publisher / CDC]
    P --> B[Managed broker]
    B --> C[Consumer]
    C --> I[(Inbox + business transaction)]
~~~

Transaction tạo đơn hàng:

~~~text
BEGIN
  INSERT orders(...)
  INSERT outbox_events(...)
COMMIT
~~~

Nếu transaction commit, cả order và outbox event cùng tồn tại. Nếu transaction rollback, cả hai cùng biến mất.

Một publisher độc lập đọc outbox rồi gửi message tới broker. Nếu broker tạm thời unavailable, record vẫn được lưu và publisher thử lại sau.

**Outbox bảo đảm business state và ý định publish được commit nguyên tử trong cùng database.** Nó không bảo đảm broker chỉ nhận message một lần. Publisher có thể gửi lại nếu broker đã nhận nhưng publisher mất acknowledgment trước khi đánh dấu record là SENT. Vì vậy event ID phải ổn định và consumer vẫn phải idempotent.

## 4. Thiết kế outbox table

Một schema tham khảo cho PostgreSQL:

~~~sql
CREATE TABLE outbox_events (
    id                UUID PRIMARY KEY,
    aggregate_type    VARCHAR(120) NOT NULL,
    aggregate_id      VARCHAR(160) NOT NULL,
    aggregate_version BIGINT,
    event_type        VARCHAR(160) NOT NULL,
    schema_version    INTEGER NOT NULL,
    payload           JSONB NOT NULL,
    status            VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    next_attempt_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempts          INTEGER NOT NULL DEFAULT 0,
    lease_owner       VARCHAR(160),
    lease_token       UUID,
    lease_until       TIMESTAMPTZ,
    published_at      TIMESTAMPTZ,
    last_error_code   VARCHAR(120)
);
~~~

Các trường quan trọng:

| Trường | Vai trò |
| --- | --- |
| id | Event ID ổn định xuyên suốt publish retry |
| aggregate_type | Loại aggregate phát event |
| aggregate_id | Đối tượng nghiệp vụ liên quan |
| aggregate_version | Thứ tự event trong aggregate nếu domain có sequence |
| event_type | Tên loại event |
| schema_version | Phiên bản payload |
| payload | Dữ liệu event đã serialize |
| status | Trạng thái publish |
| next_attempt_at | Thời điểm được phép thử lại |
| attempts | Số lần publisher thử |
| lease_owner/token/until | Claim event khi nhiều publisher chạy đồng thời |
| published_at | Thời điểm broker đã xác nhận publish |
| last_error_code | Mã lỗi gần nhất để điều tra |

Trạng thái thường dùng:

- PENDING: chờ publisher.
- IN_FLIGHT: đang được một publisher claim.
- RETRY: lần publish trước thất bại tạm thời.
- SENT: broker đã xác nhận publish theo contract.
- DEAD: vượt retry budget hoặc lỗi cần điều tra thủ công.

Không phải ứng dụng nào cũng cần mọi trạng thái. Với hệ thống đơn giản, PENDING/SENT cùng attempt metadata có thể đủ. Với workflow quan trọng, nên có lease, retry schedule và dead-letter state rõ ràng.

### Index và uniqueness

Ví dụ index cho publisher polling:

~~~sql
CREATE INDEX idx_outbox_pending
ON outbox_events (next_attempt_at, created_at)
WHERE status IN ('PENDING', 'RETRY');

CREATE INDEX idx_outbox_lease
ON outbox_events (lease_until)
WHERE status = 'IN_FLIGHT';
~~~

Nếu mỗi aggregate version chỉ có một event, có thể thêm unique constraint:

~~~sql
CREATE UNIQUE INDEX uq_outbox_aggregate_version
ON outbox_events (aggregate_type, aggregate_id, aggregate_version)
WHERE aggregate_version IS NOT NULL;
~~~

Chỉ dùng constraint này khi domain bảo đảm một version tương ứng tối đa một event. Nếu một version phát nhiều event, cần sequence riêng hoặc thêm event ordinal.

## 5. Ghi business state và outbox trong cùng transaction

Ví dụ Spring Boot với Spring Data JPA. Đây là mẫu kiến trúc; entity mapping, JSON serialization và repository cần được hoàn thiện theo database của ứng dụng.

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final ObjectMapper objectMapper;

    public OrderApplicationService(
            OrderRepository orders,
            OutboxRepository outbox,
            ObjectMapper objectMapper) {
        this.orders = orders;
        this.outbox = outbox;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Order create(CreateOrderCommand command) {
        Order order = orders.save(Order.create(command));

        OrderCreated event = new OrderCreated(
                UUID.randomUUID(),
                order.getId(),
                order.getVersion(),
                Instant.now(),
                command.customerId());

        outbox.save(OutboxEvent.pending(
                event.eventId(),
                "Order",
                order.getId(),
                order.getVersion(),
                "OrderCreated",
                1,
                serialize(event)));

        return order;
    }

    private String serialize(Object event) {
        try {
            return objectMapper.writeValueAsString(event);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot serialize outbox event", ex);
        }
    }
}
~~~

Các điểm cần bảo đảm:

- Order và OutboxEvent dùng cùng datasource/transaction manager.
- Outbox insert không chạy ở một transaction độc lập với order.
- Event ID được tạo một lần và lưu bền vững; publisher không tạo ID mới mỗi lần retry.
- Payload là snapshot event cần phát, không phải một câu truy vấn tùy ý sẽ đọc lại state mới nhất sau này.
- Event schema có version và metadata đủ cho consumer.
- Không gọi broker trong transaction này.
- Không giữ transaction database mở trong lúc chờ mạng.

Nếu serialization thất bại, transaction phải rollback cả order và outbox. Nếu order commit thành công, outbox record cũng phải commit.

## 6. Polling publisher: đọc outbox theo batch

Cách triển khai phổ biến là một worker định kỳ đọc record PENDING/RETRY, claim record, gửi tới broker rồi đánh dấu SENT.

Flow:

1. Mở transaction ngắn.
2. Claim một batch record chưa được worker khác giữ.
3. Gán owner, lease token và lease expiry.
4. Commit claim.
5. Gửi message ra broker ngoài transaction database.
6. Chờ broker confirmation theo API/client contract.
7. Nếu broker xác nhận, đánh dấu SENT với điều kiện claim token còn đúng.
8. Nếu lỗi tạm thời, lên lịch RETRY với backoff.
9. Nếu lỗi vĩnh viễn hoặc hết budget, chuyển DEAD và cảnh báo.

### Claim nhiều publisher đồng thời

PostgreSQL hỗ trợ mẫu SELECT FOR UPDATE SKIP LOCKED. Ví dụ:

~~~sql
WITH candidates AS (
    SELECT id
    FROM outbox_events
    WHERE (
        status IN ('PENDING', 'RETRY')
        AND next_attempt_at <= now()
    ) OR (
        status = 'IN_FLIGHT'
        AND lease_until < now()
    )
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE outbox_events AS e
SET status = 'IN_FLIGHT',
    lease_owner = :worker_id,
    lease_token = :claim_token,
    lease_until = now() + interval '30 seconds',
    attempts = attempts + 1
FROM candidates AS c
WHERE e.id = c.id
RETURNING e.*;
~~~

Câu lệnh này minh họa cách claim nguyên tử. Cú pháp interval và locking phải được điều chỉnh theo database cụ thể.

Không giữ row lock trong khi gửi network request. Claim transaction phải ngắn để tránh làm publisher khác và business transaction bị chặn.

### Lease không loại bỏ duplicate

Giả sử publisher A claim event, gửi broker thành công nhưng bị pause trước khi đánh dấu SENT. Lease hết hạn; publisher B claim lại và gửi cùng event. Cả hai có thể publish message.

Lease token giúp ngăn worker cũ ghi đè trạng thái claim mới, nhưng không thể thu hồi message đã gửi. Vì vậy:

- Dùng event ID ổn định làm message ID.
- Consumer dùng inbox/unique constraint.
- Chỉ đánh dấu SENT nếu claim token vẫn thuộc publisher hiện tại.
- Gia hạn lease nếu publish kéo dài.
- Có timeout rõ ràng cho broker publish.
- Không coi lease là exactly-once.

### Đánh dấu SENT có điều kiện

~~~sql
UPDATE outbox_events
SET status = 'SENT',
    published_at = now(),
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL
WHERE id = :event_id
  AND status = 'IN_FLIGHT'
  AND lease_token = :claim_token;
~~~

Nếu update count bằng 0, publisher có thể đã mất lease hoặc record đã được worker khác claim. Không ghi đè claim mới. Message đã publish vẫn có thể được gửi lại; consumer deduplication xử lý.

## 7. Publish confirmation và unknown outcome

Khi publisher gọi broker, có ba kết quả:

- Broker xác nhận nhận message.
- Broker từ chối rõ ràng trước khi nhận.
- Publisher timeout/mất kết nối và không biết broker đã nhận hay chưa.

Trường hợp thứ ba là **unknown outcome**. Không thể suy ra message chưa được gửi chỉ vì client không nhận response.

Cách xử lý:

1. Giữ nguyên event ID.
2. Retry theo policy bằng cùng identity.
3. Chấp nhận broker có thể nhận duplicate.
4. Dùng consumer inbox/broker deduplication trong phạm vi hỗ trợ.
5. Theo dõi attempt và correlation ID.
6. Nếu event có side effect tài chính, consumer vẫn phải có business idempotency.

Không tạo event ID mới cho mỗi lần publish retry; nếu làm vậy, consumer có thể coi duplicate là event mới.

## 8. Giữ thứ tự khi publish outbox

Polling nhiều worker có thể gửi event cùng aggregate không theo thứ tự. Ví dụ version 12 được worker A gửi chậm, version 13 được worker B gửi trước.

Nếu cần thứ tự theo aggregate:

- Lưu aggregate ID và sequence/version trong outbox.
- Chọn partition/session/message group/ordering key bằng aggregate ID.
- Chỉ claim event tiếp theo của một aggregate khi event trước đã được publish theo policy.
- Không chạy song song publisher cho cùng aggregate nếu không có cơ chế ordering.
- Consumer vẫn kiểm tra version và idempotency.
- Xử lý replay/late event theo domain rule.

Có thể dùng query claim loại trừ record có event cũ hơn chưa SENT, nhưng phải tính cả IN_FLIGHT, RETRY và DEAD. Một event trước bị DEAD không nên tự động cho phép event sau chạy nếu nó là prerequisite nghiệp vụ.

Thứ tự broker trong partition/session không bảo đảm database commit order nếu consumer xử lý song song. Outbox ordering và consumer sequence guard cần phối hợp.

## 9. Polling publisher và CDC publisher

Có hai cách phổ biến để đưa outbox ra broker.

| Tiêu chí | Polling publisher | CDC publisher |
| --- | --- | --- |
| Cách hoạt động | Worker truy vấn bảng outbox theo lịch | Đọc transaction log/change stream |
| Độ trễ | Theo chu kỳ polling và batch | Thường thấp hơn, phụ thuộc connector |
| Độ phức tạp | Dễ bắt đầu, cần tối ưu query/claim | Cần connector, offsets, schema và vận hành |
| Tải database | Truy vấn outbox định kỳ | Đọc transaction log/change stream |
| Retry | Ứng dụng quản lý | Connector/offset và sink retry |
| Duplicate | Có thể xảy ra | Có thể xảy ra khi restart/offset replay |
| Ordering | Phải thiết kế claim và aggregate ordering | Phụ thuộc log order, partition và sink |
| Phù hợp | Ứng dụng vừa/nhỏ, cần kiểm soát trực tiếp | Lưu lượng lớn hoặc đã có CDC platform |

### Polling publisher

Ưu điểm:

- Dễ triển khai trong Spring Boot.
- Không cần thay đổi database log pipeline.
- Có thể lọc, rate limit và retry theo business policy.
- Dễ gắn metrics và trạng thái SENT/DEAD.

Nhược điểm:

- Query polling liên tục tạo tải.
- Cần lease/claim để phối hợp nhiều instance.
- Phải quản lý cleanup và batch size.
- Độ trễ phụ thuộc poll interval.

### CDC publisher

CDC đọc thay đổi đã commit từ transaction log hoặc change feed, rồi chuyển outbox event sang broker.

Ví dụ kiến trúc: database outbox → Debezium/CDC connector → broker. CDC chỉ nhìn thấy thay đổi đã commit nên tránh publish event của transaction rollback.

Tuy nhiên CDC vẫn có thể phát lại record khi connector restart, offset chưa được commit hoặc snapshot được chạy lại. Consumer cần idempotent. Cần quản lý connector offset, schema history, log retention và backpressure.

CDC không tự làm database transaction và broker publish thành một transaction chung. Nó thay đổi cách phát hiện record mới; không loại bỏ mọi failure window.

## 10. Consumer inbox: bảo vệ phía nhận

Outbox giải quyết khoảng trống phía producer. Consumer vẫn có thể nhận cùng message nhiều lần, vì broker delivery thường at-least-once hoặc publisher có thể retry sau unknown outcome.

Inbox table:

~~~sql
CREATE TABLE inbox_messages (
    consumer_name VARCHAR(120) NOT NULL,
    event_id      UUID NOT NULL,
    payload_hash  VARCHAR(64) NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    result_ref    VARCHAR(160),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong một transaction:

~~~text
BEGIN
  INSERT inbox(consumer_name, event_id, payload_hash)
  UPDATE business state
  INSERT next outbox event if required
COMMIT

ACK / Complete message
~~~

Nếu event ID đã tồn tại và payload hash giống nhau, consumer có thể ACK duplicate mà không lặp business effect. Nếu cùng ID nhưng payload khác, đó là identity conflict cần quarantine/alert.

Inbox và business state phải cùng transaction nếu cùng database. Nếu inbox ghi vào Redis còn business state nằm trong PostgreSQL, không có atomicity giữa hai nơi; crash giữa hai thao tác vẫn tạo lỗ hổng.

Inbox retention phải bao phủ broker redelivery, DLQ replay và thời gian vận hành có thể phát lại. Với payment/ledger, business unique reference có thể cần được giữ lâu hơn inbox record.

## 11. Outbox, inbox và exactly-once

Outbox + inbox tạo một chuỗi **effectively-once** cho business state trong phạm vi transaction database và event identity đã định nghĩa:

- Producer ghi business state và outbox trong một transaction.
- Publisher gửi event có identity ổn định; duplicate có thể xảy ra.
- Consumer ghi inbox và business state trong một transaction.
- Redelivery được inbox nhận diện.
- External side effect dùng provider idempotency hoặc saga/reconciliation.

## 12. Khi nào cần Saga?

Outbox bảo vệ việc phát event sau transaction cục bộ. Nhưng một workflow có thể cần cập nhật nhiều service/database độc lập:

~~~text
Order service: tạo order
Inventory service: giữ hàng
Payment service: authorize/capture payment
Shipping service: tạo shipment
Notification service: gửi xác nhận
~~~

Không có một database transaction chung cho tất cả service. Nếu bước shipping thất bại sau khi inventory và payment đã thành công, hệ thống cần một quy trình tiếp tục hoặc bù trừ.

**Saga** chia workflow thành nhiều local transaction. Mỗi bước commit độc lập và phát event/command tiếp theo. Nếu bước sau thất bại, saga có thể chạy compensation cho các bước trước theo business rule.

Saga không phải distributed rollback. Mỗi bước đã commit là trạng thái thật và có thể đã được hệ thống khác quan sát.

## 13. Orchestration và choreography

Có hai cách điều phối saga:

### Orchestration

Một saga orchestrator lưu trạng thái workflow và gửi command cho từng service.

~~~mermaid
flowchart TD
    O[Order Saga Orchestrator] --> I[Reserve Inventory]
    I --> P[Authorize Payment]
    P --> S[Create Shipment]
    S --> D[Complete Order]
    P -. failure .-> RI[Release Inventory]
    S -. failure .-> VP[Void Payment]
    VP --> RI
~~~

Ưu điểm:

- Luồng nghiệp vụ nhìn thấy được ở một nơi.
- Dễ theo dõi trạng thái, timeout và compensation.
- Dễ áp dụng retry budget và manual intervention.

Nhược điểm:

- Orchestrator là thành phần cần vận hành và scale.
- Có thể tạo coupling vào workflow definition.
- Cần bảo vệ state và command bằng outbox/inbox.

### Choreography

Các service phản ứng với event của service khác mà không có một coordinator trung tâm.

~~~mermaid
flowchart LR
    O[OrderCreated] --> I[Inventory Service]
    I -->|InventoryReserved| P[Payment Service]
    P -->|PaymentAuthorized| S[Shipping Service]
    S -->|ShipmentCreated| C[Order Completed]
    P -->|PaymentRejected| R[Inventory Release]
~~~

Ưu điểm:

- Service ít phụ thuộc trực tiếp vào coordinator.
- Mỗi service tự quản lý transaction và event của mình.
- Phù hợp workflow ngắn, ít nhánh.

Nhược điểm:

- Luồng tổng thể phân tán qua nhiều handler.
- Khó quan sát khi nhiều event/nhánh tương tác.
- Có nguy cơ tạo vòng event hoặc khó xác định ai chịu trách nhiệm timeout.
- Cần correlation ID, saga ID và trạng thái workflow rõ ràng.

### Chọn cách nào?

| Đặc điểm workflow | Hướng phù hợp |
| --- | --- |
| 2–3 bước đơn giản, ít nhánh | Choreography có thể đủ |
| Nhiều bước, timeout và compensation phức tạp | Orchestration thường dễ kiểm soát |
| Cần audit trạng thái toàn workflow | Orchestration hoặc saga state store rõ ràng |
| Các service độc lập phản ứng với domain event | Choreography |
| Cần operator retry/continue một bước | Orchestrator/state machine tường minh |

Không có quy tắc số bước tuyệt đối. Chọn theo khả năng hiểu, quan sát, phục hồi và thay đổi workflow.

## 14. Thiết kế Saga state và command

Một saga instance có thể lưu:

~~~sql
CREATE TABLE saga_instances (
    saga_id          UUID PRIMARY KEY,
    saga_type        VARCHAR(120) NOT NULL,
    business_key     VARCHAR(160) NOT NULL,
    state            VARCHAR(40) NOT NULL,
    current_step     VARCHAR(120),
    version          BIGINT NOT NULL DEFAULT 0,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    deadline_at      TIMESTAMPTZ,
    last_error_code  VARCHAR(120)
);
~~~

Bảng step:

~~~sql
CREATE TABLE saga_steps (
    saga_id          UUID NOT NULL,
    step_name        VARCHAR(120) NOT NULL,
    status           VARCHAR(30) NOT NULL,
    command_id       UUID NOT NULL,
    attempt_count    INTEGER NOT NULL DEFAULT 0,
    completed_at     TIMESTAMPTZ,
    compensation_id  UUID,
    last_error_code  VARCHAR(120),
    PRIMARY KEY (saga_id, step_name)
);
~~~

Trạng thái saga có thể gồm:

- STARTED/RUNNING: workflow đang tiến hành.
- COMPENSATING: đang bù trừ các bước đã thành công.
- COMPLETED: hoàn tất.
- FAILED_FINAL: thất bại cuối cùng sau policy.
- NEEDS_MANUAL_REVIEW: kết quả không xác định hoặc compensation không tự động hoàn tất.
- CANCELLED: hủy theo quy tắc nghiệp vụ.

Mỗi command/event cần identity ổn định. Dùng unique key như saga ID + step name + command type để tránh phát command trùng khi orchestrator restart.

Saga state và outbox command nên được cập nhật trong cùng local database transaction. Khi orchestrator chuyển state và phát command, ghi state + outbox trong một transaction.

## 15. Ví dụ Saga: đặt hàng, giữ hàng và thanh toán

Giả sử quy trình đặt hàng có các bước:

1. Order service tạo order ở trạng thái PENDING.
2. Inventory service reserve hàng.
3. Payment service authorize payment.
4. Shipping service tạo shipment.
5. Order service chuyển order sang CONFIRMED.

Một luồng orchestration:

~~~mermaid
sequenceDiagram
    participant O as Order Saga
    participant I as Inventory
    participant P as Payment
    participant S as Shipping
    O->>I: ReserveInventory
    I-->>O: InventoryReserved
    O->>P: AuthorizePayment
    P-->>O: PaymentAuthorized
    O->>S: CreateShipment
    S-->>O: ShipmentCreated
    O->>O: Mark order CONFIRMED
~~~

Nếu payment bị từ chối:

~~~mermaid
sequenceDiagram
    participant O as Order Saga
    participant I as Inventory
    participant P as Payment
    O->>I: ReserveInventory
    I-->>O: InventoryReserved
    O->>P: AuthorizePayment
    P-->>O: PaymentRejected
    O->>I: ReleaseInventory
    I-->>O: InventoryReleased
    O->>O: Mark order FAILED
~~~

Nếu shipment thất bại sau khi payment đã authorize:

1. Thử retry CreateShipment nếu lỗi transient và deadline còn.
2. Nếu không thể tiếp tục, yêu cầu VoidAuthorization.
3. Release inventory.
4. Chuyển order sang trạng thái FAILED/CANCELLED theo business rule.
5. Nếu void payment không thành công, đánh dấu NEEDS_MANUAL_REVIEW và reconcile.

### Authorize khác capture

Nếu payment provider hỗ trợ authorization/capture, có thể authorize trước khi shipment và chỉ capture ở thời điểm phù hợp. Nếu đã capture, compensation có thể là refund chứ không phải rollback. Refund là một transaction nghiệp vụ mới, có phí, độ trễ và trạng thái riêng.

## 16. Compensation không phải rollback

Compensation là hành động nghiệp vụ nhằm đưa workflow tới một trạng thái chấp nhận được sau khi bước sau thất bại. Nó không xóa lịch sử transaction đã commit.

| Hành động gốc | Compensation có thể có | Lưu ý |
| --- | --- | --- |
| Reserve inventory | Release reservation | Có thể reservation đã hết hạn hoặc hàng đã được phân bổ |
| Authorize payment | Void authorization | Phụ thuộc provider và trạng thái authorization |
| Capture payment | Refund payment | Refund là giao dịch mới, không phải rollback |
| Create shipment | Cancel shipment | Có thể phát sinh phí hoặc hàng đã bàn giao |
| Create subscription | Cancel subscription | Có thể có chu kỳ billing đã chạy |
| Send email | Không thể thu hồi email đã gửi | Có thể gửi correction/clarification |
| Upload document | Delete/mark superseded | Cần giữ audit nếu document đã được tham chiếu |

Compensation có thể thất bại. Vì vậy saga phải lưu trạng thái compensation riêng, retry có giới hạn, có escalation và reconciliation.

### Compensation chạy theo thứ tự nào?

Thông thường compensation chạy ngược thứ tự các bước đã thành công:

~~~text
Reserve inventory
  → Authorize payment
  → Create shipment (fails)

Compensate:
  → Void payment authorization
  → Release inventory
~~~

Tuy nhiên đây không phải quy tắc tuyệt đối. Business domain có thể yêu cầu hủy shipment trước, hoặc không release inventory cho tới khi payment void thành công. Thứ tự phải phản ánh invariant và rủi ro.

### Forward recovery và backward compensation

- **Forward recovery:** sửa dependency rồi tiếp tục bước còn thiếu.
- **Backward compensation:** thực hiện hành động bù trừ cho các bước đã hoàn tất.
- **Manual resolution:** cần operator hoặc bộ phận nghiệp vụ quyết định khi kết quả không thể tự xác định.

Không compensation chỉ vì một request timeout. Trước tiên cần xác định bước gốc đã thành công hay chưa.

## 17. Timeout và unknown outcome trong Saga

Một command có thể được service nhận và commit nhưng response event bị mất. Orchestrator không biết bước đó thành công hay thất bại.

Ví dụ Payment service đã authorize nhưng PaymentAuthorized event chưa đến.

Không gửi AuthorizePayment lần nữa bằng một command ID mới. Thay vào đó:

1. Giữ command ID/idempotency key ổn định.
2. Query payment status theo provider reference/command ID nếu có.
3. Chờ event retry hoặc phát query command.
4. Reconcile với provider.
5. Nếu đã authorize, tiếp tục bước tiếp theo.
6. Nếu chưa authorize, retry cùng operation identity theo contract.
7. Nếu không xác định được, chuyển saga sang NEEDS_MANUAL_REVIEW.

Timeout là trạng thái quan sát của caller, không phải kết luận về trạng thái hệ thống đích.

### Saga deadline

Mỗi saga nên có deadline và timeout cho từng step. Khi hết deadline:

- Không tự động bù trừ nếu step có unknown outcome.
- Query trạng thái step trước.
- Chọn forward retry, compensation hoặc manual review.
- Lưu lý do và thời điểm timeout.
- Giới hạn retry để tránh workflow sống vô hạn.

## 18. Idempotency cho từng bước Saga

Mỗi command và compensation cần idempotent riêng:

- ReserveInventory dùng reservation ID ổn định theo saga/order.
- AuthorizePayment dùng payment operation ID ổn định.
- CreateShipment dùng shipment request ID ổn định.
- ReleaseInventory dùng reservation ID và operation ID.
- VoidAuthorization dùng authorization reference.
- RefundPayment dùng refund operation ID riêng, liên kết payment gốc.

Một compensation có thể được gọi nhiều lần do retry. Nó phải kiểm tra trạng thái hiện tại và trả kết quả tương đương nếu đã thực hiện.

Không dùng một idempotency key chung cho mọi bước. Mỗi side effect có identity riêng nhưng phải liên kết với saga ID/correlation ID.

## 19. Outbox trong từng service của Saga

Mỗi service có local database và outbox riêng:

~~~text
Order service:
  BEGIN
    update saga/order state
    insert outbox command ReserveInventory
  COMMIT

Inventory service:
  receive command
  BEGIN
    insert inbox command ID
    reserve inventory
    insert outbox event InventoryReserved
  COMMIT
  ACK command

Saga orchestrator:
  receive InventoryReserved
  BEGIN
    update saga step
    insert outbox command AuthorizePayment
  COMMIT
~~~

Mỗi ranh giới service được bảo vệ bằng local transaction + outbox/inbox. Không cần một transaction bao trùm tất cả service.

Nếu Inventory service commit reservation nhưng không publish InventoryReserved, outbox publisher sẽ phát lại sau. Nếu publish duplicate, orchestrator inbox nhận diện.

Nếu command được giao lại, Inventory service inbox chặn reservation trùng. Nếu reservation provider có API ngoài, dùng idempotency key hoặc reconciliation riêng.

## 20. Spring Boot implementation: ghi outbox và phát message

### 20.1. Repository contract

~~~java
public interface OutboxRepository {
    List<ClaimedOutboxEvent> claimBatch(
            String workerId,
            UUID claimToken,
            int batchSize,
            Duration lease);

    boolean markSent(UUID eventId, UUID claimToken);

    boolean scheduleRetry(
            UUID eventId,
            UUID claimToken,
            Instant nextAttempt,
            String errorCode);

    boolean markDead(
            UUID eventId,
            UUID claimToken,
            String errorCode);
}
~~~

Repository phải thực hiện claim/mark bằng thao tác atomic trong database. Không triển khai claim bằng SELECT rồi UPDATE không có lock hoặc điều kiện cạnh tranh.

### 20.2. Publisher worker

~~~java
@Component
public class OutboxPublisher {

    private final OutboxRepository outbox;
    private final BrokerPublisher broker;
    private final String workerId;

    public OutboxPublisher(
            OutboxRepository outbox,
            BrokerPublisher broker,
            String workerId) {
        this.outbox = outbox;
        this.broker = broker;
        this.workerId = workerId;
    }

    @Scheduled(fixedDelay = 500)
    public void publishBatch() {
        UUID claimToken = UUID.randomUUID();

        List<ClaimedOutboxEvent> events =
                outbox.claimBatch(
                        workerId,
                        claimToken,
                        50,
                        Duration.ofSeconds(30));

        for (ClaimedOutboxEvent event : events) {
            try {
                broker.publish(
                        event.id(),
                        event.eventType(),
                        event.payload(),
                        event.aggregateId());

                outbox.markSent(event.id(), event.claimToken());
            } catch (RetryablePublishException ex) {
                Instant next = retryTime(event.attempts());
                outbox.scheduleRetry(
                        event.id(),
                        event.claimToken(),
                        next,
                        ex.code());
            } catch (PermanentPublishException ex) {
                outbox.markDead(
                        event.id(),
                        event.claimToken(),
                        ex.code());
            }
        }
    }

    private Instant retryTime(int attempts) {
        long seconds = Math.min(300, 1L << Math.min(attempts, 8));
        return Instant.now().plusSeconds(seconds);
    }
}
~~~

Đây là pseudocode minh họa. Trong production:

- BrokerPublisher phải chờ confirmation theo SDK/binder contract; return ngay sau khi enqueue vào local buffer chưa phải broker acknowledgment.
- Phân biệt timeout/unknown outcome với lỗi từ chối rõ ràng.
- Retry cần jitter, deadline và retry budget; ví dụ code rút gọn chỉ minh họa backoff.
- Claim lease phải đủ dài hoặc được renew khi publish batch.
- Mark SENT phải kiểm tra claim token.
- Không nuốt exception database khi cập nhật trạng thái.
- Không xử lý song song cùng aggregate nếu cần ordering nghiêm ngặt.
- Cần graceful shutdown để worker dừng claim mới và hoàn tất/để lease hết hạn cho event đang giữ.

### 20.3. Broker message identity

Khi gửi event, dùng outbox event ID làm message ID/idempotency identity:

~~~text
message_id = outbox_event.id
partition_key / session_id / ordering_key = aggregate_id
correlation_id = saga_id hoặc request correlation
~~~

Header và field cụ thể tùy broker. Không dùng trace ID thay cho event ID. Giữ schema version và event type để consumer chọn handler.

## 21. Spring Cloud Stream có thay thế Outbox không?

Spring Cloud Stream cung cấp abstraction để gửi/nhận message qua binder. Nó không tự biến một transaction JPA thành transaction nguyên tử với mọi broker.

Có thể dùng Spring Cloud Stream làm transport của outbox publisher:

1. Outbox poller claim event.
2. Gọi StreamBridge hoặc function output binding.
3. Chờ broker send result/confirmation theo binder thực tế.
4. Mark SENT sau khi confirmation được xác nhận.
5. Nếu kết quả không rõ, retry cùng event ID.

Cần kiểm tra:

- Binder có trả asynchronous send result hay acknowledgment không?
- Khi nào send result nghĩa là broker đã nhận?
- Exception có được ném đồng bộ hay báo qua callback?
- Transactional binder có phạm vi transaction nào?
- Retry binder có chồng lên retry outbox không?
- Message ID, partition key, session ID và headers được map ra sao?

Không đánh dấu SENT chỉ vì StreamBridge.send trả true nếu binder semantics không bảo đảm broker đã lưu message. Đọc đúng tài liệu binder/version và viết integration test.

## 22. Azure: Cosmos DB, Change Feed và Service Bus

### Cosmos DB transactional batch

Cosmos DB hỗ trợ transactional batch trong phạm vi một logical partition với các operation được hỗ trợ. Có thể lưu business document và outbox document trong cùng partition/batch:

~~~text
Partition key = orderId

Transactional batch:
  Create/replace Order document
  Create OutboxEvent document
Commit batch
~~~

Nếu batch thành công, cả hai document cùng commit; nếu thất bại, batch rollback theo semantics dịch vụ.

Cần chọn partition key sao cho business record và outbox record cùng logical partition. Nếu chúng ở partition khác nhau, không giả định transactional batch bao trùm cả hai.

### Change Feed publisher

Cosmos DB Change Feed Processor có thể đọc outbox documents mới/được thay đổi rồi gửi event tới Service Bus hoặc Event Hubs. Checkpoint/lease được quản lý theo processor và feed range.

Change feed consumer có thể phải xử lý lại khi restart, lease chuyển hoặc checkpoint chưa được lưu. Publisher phải dùng event ID ổn định và downstream consumer idempotent.

Không xóa outbox record ngay khi Change Feed đọc được. Cần lifecycle/TTL/cleanup phù hợp và bảo đảm connector/processor đã tiến qua record theo checkpoint policy.

### Service Bus transaction không phải transaction xuyên Cosmos DB

Service Bus có transaction cho các thao tác broker được hỗ trợ trong phạm vi namespace/transaction của Service Bus. Điều đó không tạo transaction chung với Cosmos DB hoặc một payment API. Cosmos outbox/change feed vẫn là cầu nối giữa database commit và broker publish.

## 23. AWS: DynamoDB, Streams và SQS

### DynamoDB TransactWriteItems

DynamoDB hỗ trợ transaction write cho nhiều item trong phạm vi một transaction dịch vụ. Có thể dùng TransactWriteItems để cập nhật business item và tạo outbox item cùng lúc:

~~~text
TransactWriteItems:
  Update Order item
  Put OutboxEvent item with condition attribute_not_exists(eventId)
Commit
~~~

Nếu transaction thành công, business state và outbox item cùng được ghi. Dùng condition expression để chống ghi trùng và bảo vệ version.

### DynamoDB Streams

DynamoDB Streams ghi nhận thay đổi item; Lambda/consumer có thể đọc stream rồi publish event tới SQS, SNS hoặc EventBridge theo kiến trúc.

Cần xử lý:

- Lambda/event source mapping có thể retry batch.
- Batch failure có thể làm record được xử lý lại; cấu hình partial batch response phù hợp nếu dùng.
- Stream retention có giới hạn; không dùng stream như archive dài hạn.
- Consumer cần event ID/idempotency ổn định.
- Nếu một record publish thành công nhưng checkpoint/ack của source chưa được ghi nhận, có thể publish lại.

Không coi DynamoDB Streams và broker đích là một transaction nguyên tử. Outbox item/stream event là nguồn phát, còn downstream cần dedupe.

### SQS và EventBridge

Outbox publisher có thể gửi event tới SQS hoặc EventBridge. Với SQS FIFO, dùng MessageGroupId theo aggregate và MessageDeduplicationId theo event ID trong cửa sổ dịch vụ hỗ trợ. Với Standard, consumer phải chịu duplicate. Dù broker có deduplication, inbox/business unique constraint vẫn bảo vệ side effect.

## 24. Google Cloud: Spanner, Firestore và Pub/Sub

### Cloud Spanner

Spanner hỗ trợ transaction trên dữ liệu trong database. Có thể cập nhật business row và insert outbox row trong cùng transaction. Publisher riêng đọc outbox rồi publish lên Pub/Sub.

Spanner change streams cũng có thể làm nguồn CDC cho pipeline. Cần quản lý partitioning, offsets, retention và duplicate khi consumer restart. Publish Pub/Sub vẫn là bước riêng với transaction database.

### Firestore

Firestore transaction có thể ghi nhiều document trong cùng database theo giới hạn và semantics của dịch vụ. Có thể ghi business document và outbox document trong cùng transaction nếu thiết kế phù hợp.

Trigger/event-driven consumer có thể được gọi lại theo delivery semantics của nền tảng. Dùng event ID ổn định, transaction/conditional write và inbox để chống duplicate. Theo dõi giới hạn transaction, contention, document size và write rate.

### Pub/Sub

Publisher gửi outbox event lên Pub/Sub sau khi database commit. Pub/Sub ordering key có thể dùng aggregate ID nếu cần ordering và subscription được cấu hình phù hợp. Consumer vẫn cần idempotency/inbox vì Pub/Sub và database không có một transaction chung cho toàn workflow.

Không nhầm Pub/Sub exactly-once delivery feature với exactly-once database update hoặc external API effect.

## 25. Saga compensation: ví dụ và nguyên tắc thiết kế

Một compensation cần trả lời:

- Hành động gốc đã hoàn thành chắc chắn chưa?
- Compensation có thể được gọi nhiều lần không?
- Compensation có thể thất bại hoặc timeout không?
- Có side effect không thể đảo ngược không?
- Có thể tiếp tục forward thay vì compensation không?
- Trạng thái nào cần manual review?
- Ai có quyền quyết định compensation tài chính?

### Reservation

Reserve inventory thường có reservation ID và expiry. Release reservation phải idempotent: nếu đã release, gọi lại không làm tồn kho tăng thêm lần nữa.

### Payment

Void authorization khác refund capture. Refund phải tham chiếu payment gốc, có refund ID và trạng thái riêng. Không gửi refund mới mỗi lần saga retry.

### Shipment

Cancel shipment có thể bị từ chối nếu hàng đã bàn giao cho carrier. Khi đó cần quy trình return/refund hoặc manual intervention, không giả định cancellation luôn đảo ngược create shipment.

### Email

Email đã gửi không thể rollback. Có thể gửi email đính chính hoặc notification mới, nhưng đó là business action khác.

## 26. Saga retry, timeout và compensation failure

Mỗi step nên có:

- Command ID/idempotency key.
- Attempt count và retry deadline.
- Timeout.
- Result state.
- Provider reference.
- Compensation command ID.
- Last error category/code.
- Correlation ID/saga ID.

Retry transient failure bằng backoff/jitter. Khi timeout với unknown outcome, query trạng thái trước khi gửi lại. Khi compensation thất bại, không đánh dấu saga hoàn tất; chuyển sang COMPENSATING hoặc NEEDS_MANUAL_REVIEW và phát cảnh báo.

Một saga có thể chạy trong nhiều giờ/ngày. Không giữ một database transaction mở suốt workflow. Mỗi bước là local transaction ngắn, trạng thái saga được lưu bền vững.

## 27. Bảo mật outbox và saga data

Outbox payload có thể chứa thông tin khách hàng, đơn hàng, địa chỉ hoặc payment reference. Áp dụng:

- Chỉ lưu trường cần cho event contract.
- Không lưu secret, access token, password hoặc connection string trong payload.
- Mã hóa database/storage theo policy.
- Giới hạn quyền đọc outbox/DLQ và quyền replay.
- Mask dữ liệu nhạy cảm trong log/trace.
- Audit người/identity chạy redrive hoặc compensation.
- Đặt retention/cleanup theo nghiệp vụ và pháp lý.
- Không cho một operator replay tùy ý payment/refund nếu không có quyền nghiệp vụ.
- Bảo vệ saga state khỏi sửa trực tiếp không qua workflow.

Replay và compensation có thể tạo tác động thật; quyền vận hành phải được phân tách và ghi audit.

## 28. Observability: theo dõi outbox và saga

Metrics cho outbox:

| Metric | Ý nghĩa |
| --- | --- |
| outbox_pending_count | Số event đang chờ |
| outbox_oldest_pending_age_seconds | Tuổi event chờ lâu nhất |
| outbox_publish_attempts_total | Số lần publisher thử |
| outbox_publish_confirmed_total | Số event broker xác nhận |
| outbox_publish_failed_total | Số lần publish lỗi |
| outbox_duplicate_publish_suspected_total | Số duplicate được phát hiện ở consumer |
| outbox_dead_count | Số event vượt retry budget |
| outbox_lease_expired_total | Số claim hết hạn |
| outbox_cdc_lag_seconds | Độ trễ của CDC nếu có |

Metrics cho saga:

| Metric | Ý nghĩa |
| --- | --- |
| saga_started_total | Số saga bắt đầu |
| saga_completed_total | Số saga hoàn tất |
| saga_compensating_count | Saga đang bù trừ |
| saga_failed_total | Saga thất bại cuối |
| saga_manual_review_count | Saga cần người xử lý |
| saga_step_duration_seconds | Thời gian từng bước |
| saga_compensation_failed_total | Compensation thất bại |
| saga_unknown_outcome_count | Step chưa xác định kết quả |

Theo dõi backlog, oldest age và lag thường hữu ích hơn chỉ nhìn số lượng message. Không dùng event ID, order ID hoặc saga ID làm metric label có cardinality cao; đưa vào log/trace có kiểm soát.

## 29. Kiểm thử Outbox và Saga

### Outbox test matrix

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Order insert thành công, outbox insert thành công | Cả hai commit |
| Outbox serialization/insert thất bại | Order transaction rollback |
| Database transaction rollback | Không có outbox event đã commit |
| Broker unavailable | Outbox giữ pending/retry |
| Broker nhận event, publisher crash trước mark SENT | Có thể publish duplicate; consumer inbox chặn |
| Hai publisher claim cùng lúc | Một claim owner cho mỗi record trong thời điểm hợp lệ |
| Lease hết hạn khi publisher cũ còn chạy | Claim token ngăn stale status update; event ID chống duplicate |
| Event trước chưa publish | Event sau cùng aggregate không vượt qua nếu strict ordering |
| CDC restart/offset replay | Duplicate được xử lý idempotently |
| Cleanup chạy | Không xóa pending/dead/in-flight record cần điều tra |

### Saga test matrix

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Mọi step thành công | Saga COMPLETED |
| Reserve inventory thất bại | Không authorize payment |
| Payment bị từ chối | Release inventory |
| Shipment transient failure | Retry trong deadline |
| Shipment permanent failure sau payment authorization | Void authorization rồi release inventory |
| Void payment timeout | Query provider, giữ unknown outcome |
| Compensation thất bại | Saga không đánh dấu hoàn tất; cảnh báo/manual review |
| Duplicate command | Service idempotent, không tạo side effect mới |
| Orchestrator restart | Khôi phục từ saga state/outbox |
| Event response đến trễ | Correlation/saga ID và step state loại stale response |
| Replay command cũ | Idempotency key ngăn chạy lại |
| Saga deadline hết hạn | Recovery policy rõ ràng, không rollback mù |

### Failure injection

1. Kill ứng dụng sau database commit nhưng trước publisher gửi event.
2. Kill publisher sau broker acceptance nhưng trước mark SENT.
3. Làm broker publish timeout với unknown outcome.
4. Restart CDC connector sau khi đọc record nhưng trước khi commit offset.
5. Làm payment service commit nhưng response event bị mất.
6. Làm compensation timeout sau khi provider đã xử lý.
7. Restart orchestrator khi saga đang COMPENSATING.
8. Gửi cùng command nhiều lần.
9. Làm một event response đến sau khi saga đã chuyển step.
10. Kiểm tra outbox backlog và saga manual review alert.

## 30. Bài thực hành: Order workflow dùng Outbox và Saga

**Bối cảnh:** Spring Boot Order service tạo đơn hàng và phát OrderCreated. Inventory service giữ hàng; Payment service authorize; Shipping service tạo shipment. Các service dùng database riêng và giao tiếp qua broker managed.

### Phần A — Outbox phía Order

1. Tạo bảng orders và outbox_events.
2. Ghi order và OrderCreated trong cùng transaction.
3. Xây dựng polling publisher hoặc CDC.
4. Dùng event ID ổn định làm message ID.
5. Theo dõi pending age, publish attempts và dead count.

### Phần B — Inbox và local transaction

1. Mỗi consumer có inbox riêng với unique key consumer/event.
2. Ghi inbox và business state trong cùng transaction.
3. Publish event tiếp theo bằng outbox của service.
4. Commit trước ACK/Complete.
5. Kiểm thử duplicate delivery và publisher crash.

### Phần C — Saga orchestration

1. Tạo saga instance cho order.
2. Gửi ReserveInventory.
3. Khi InventoryReserved, gửi AuthorizePayment.
4. Khi PaymentAuthorized, gửi CreateShipment.
5. Khi ShipmentCreated, chuyển order CONFIRMED.
6. Khi payment thất bại, ReleaseInventory.
7. Khi shipment thất bại cuối cùng, VoidAuthorization rồi ReleaseInventory.
8. Nếu compensation không xác định, chuyển NEEDS_MANUAL_REVIEW.

### Phần D — Kiểm thử phục hồi

1. Làm broker unavailable sau khi order commit.
2. Khởi động lại publisher và xác minh event được gửi.
3. Làm publish confirmation bị mất và xác minh consumer không tạo duplicate.
4. Làm payment timeout sau khi authorize.
5. Restart orchestrator và xác minh saga tiếp tục đúng step.
6. Làm void/refund thất bại và xác minh alert/manual review.
7. Đối chiếu business state, provider reference và outbox/inbox.

### Sản phẩm cần nộp

- Schema outbox, inbox, saga instance và saga step.
- Sơ đồ transaction boundary của từng service.
- Publisher polling hoặc CDC flow.
- Saga state machine và compensation matrix.
- Bằng chứng test dual-write failure, duplicate publish và partial failure.
- Dashboard outbox backlog, publish lag, saga state và compensation failure.
- Runbook cho unknown outcome và manual recovery.

### Câu hỏi tự kiểm tra

1. Vì sao @Transactional không tự bảo vệ database write và broker publish?
2. Outbox ghi business state và event intent ở đâu để bảo đảm atomicity?
3. Vì sao publisher có thể gửi duplicate dù dùng outbox?
4. Lease token bảo vệ điều gì và không bảo vệ điều gì?
5. Polling publisher khác CDC publisher thế nào?
6. Vì sao consumer vẫn cần inbox khi producer dùng outbox?
7. Outbox và saga giải quyết hai vấn đề khác nhau ra sao?
8. Orchestration và choreography có trade-off gì?
9. Vì sao compensation không phải rollback?
10. Void authorization khác refund payment thế nào?
11. Khi payment timeout với unknown outcome, orchestrator nên làm gì?
12. Vì sao saga state và command outbox nên được ghi cùng local transaction?
13. Cosmos DB transactional batch bị giới hạn bởi phạm vi nào?
14. DynamoDB Streams có làm publish sang SQS atomic với DynamoDB không?
15. Exactly-once delivery của Pub/Sub có bao gồm transaction Spanner không?
16. Những điều kiện nào khiến saga cần NEEDS_MANUAL_REVIEW?

## 31. Ghi nhớ

- Dual-write problem xuất hiện khi business database và broker được cập nhật bằng hai thao tác độc lập.
- Transactional outbox ghi business state và event intent trong cùng local transaction; publisher gửi sau commit.
- Outbox không bảo đảm publish đúng một lần. Publisher có thể gửi lại khi acknowledgment không rõ; event ID ổn định và inbox bảo vệ consumer.
- Polling và CDC là hai cách phát hiện outbox; cả hai đều cần quản lý offset/lease, retry, ordering và duplicate.
- Consumer inbox phải commit cùng business state trong một transaction; ACK sau commit theo broker settlement semantics.
- Saga chia workflow phân tán thành local transaction và compensation; mỗi step/compensation cần idempotency, timeout và state bền vững.
- Compensation là business action mới, có thể thất bại và không xóa lịch sử đã commit.
- Timeout không chứng minh side effect chưa xảy ra; query/reconcile trước retry hoặc compensation.
- Cosmos DB batch, DynamoDB transaction, Spanner/Firestore transaction và broker transaction có phạm vi riêng; không coi chúng là transaction xuyên mọi dịch vụ.
- Kiểm thử crash sau commit, publish unknown outcome, duplicate, CDC replay, compensation failure và orchestrator restart.

## Tài liệu tham khảo

- [Transactional outbox pattern — Azure Architecture Center](https://learn.microsoft.com/azure/architecture/databases/guide/transactional-outbox-cosmos)
- [Azure Cosmos DB transactional batch](https://learn.microsoft.com/azure/cosmos-db/nosql/transactional-batch)
- [Azure Cosmos DB change feed](https://learn.microsoft.com/azure/cosmos-db/change-feed)
- [Azure Service Bus transactions](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-transactions)
- [AWS DynamoDB transactions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transactions.html)
- [DynamoDB Streams](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.html)
- [AWS Prescriptive Guidance — Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
- [Google Cloud Spanner transactions](https://cloud.google.com/spanner/docs/transactions)
- [Google Cloud Firestore transactions and batched writes](https://firebase.google.com/docs/firestore/manage-data/transactions)
- [Google Cloud Pub/Sub overview](https://cloud.google.com/pubsub/docs/overview)
- [Spring Cloud Stream reference](https://docs.spring.io/spring-cloud-stream/reference/)
- [Saga pattern — Azure Architecture Center](https://learn.microsoft.com/azure/architecture/reference-architectures/saga/saga)
- [Microservices.io — Saga pattern](https://microservices.io/patterns/data/saga.html)
- [Microservices.io — Transactional outbox](https://microservices.io/patterns/data/transactional-outbox.html)
