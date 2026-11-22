# Compensation sau primary commit

Trong **Spring Kafka kết hợp database**, **compensation sau primary commit** là cách phục hồi nghiệp vụ khi một transaction đã **commit thành công ở tài nguyên chính** nhưng một transaction khác hoặc một bước xử lý phụ thuộc **không hoàn tất**. Ví dụ, database đã lưu đơn hàng nhưng Kafka transaction phát sự kiện tương ứng thất bại; hoặc Kafka đã commit sự kiện nhưng transaction database sau đó rollback.

Vì **primary transaction đã commit**, ứng dụng không thể gọi rollback để xóa quyết định commit đó. Có hai hướng khác nhau: **forward recovery**, tức tiếp tục thực hiện bước secondary còn thiếu; hoặc **compensation**, tức thực hiện một hành động nghiệp vụ mới để đưa hệ thống đến trạng thái chấp nhận được. Khi secondary commit chỉ trả timeout và chưa rõ có thành công hay không, cần **reconciliation** trước khi lựa chọn.

Spring có thể đồng bộ lifecycle của Kafka transaction với một transaction manager khác, nhưng điều này **không tự tạo giao dịch phân tán nguyên tử giữa Kafka và database**. Đây là lý do transactional outbox, idempotency và saga state machine đặc biệt quan trọng trong vận hành.

## 1. Primary commit và secondary commit

Một nghiệp vụ có thể tác động tới hai hệ thống:

- **Database**: lưu order, payment, inventory reservation hoặc trạng thái workflow.
- **Kafka**: phát domain event, gửi command hoặc commit output records và input offsets trong Kafka transaction.

Trong một mô hình có thứ tự commit:

~~~text
Transaction thứ nhất COMMIT  -> primary commit
Transaction thứ hai COMMIT   -> secondary commit
~~~

Tên primary/secondary mô tả **thứ tự commit**, không phải Kafka hoặc database luôn có vai trò cố định.

Ví dụ **database-first**:

~~~text
T0: Bắt đầu database transaction
T1: INSERT order và trạng thái RESERVED
T2: Chuẩn bị gửi OrderReserved qua Kafka
T3: DATABASE COMMIT thành công         <- PRIMARY
T4: KAFKA TRANSACTION COMMIT thất bại  <- SECONDARY
~~~

Sau T3, order đã là dữ liệu committed. Exception ở T4 không thể làm T3 biến mất.

Ví dụ **Kafka-first**:

~~~text
T0: Bắt đầu Kafka transaction
T1: Gửi OrderCreated
T2: Chuẩn bị database insert
T3: KAFKA COMMIT thành công             <- PRIMARY
T4: DATABASE COMMIT thất bại           <- SECONDARY
~~~

Kafka event có thể đã được read_committed consumers đọc và thực hiện side effect. Rollback database tại T4 không rút lại event đã commit.

## 2. Vì sao không thể rollback primary sau commit?

Transaction rollback chỉ tác động đến thay đổi **chưa commit**. Khi database commit thành công, những rows mới có thể đã được query khác đọc, trigger/CDC đã quan sát, hoặc workflow khác đã hành động.

Với Kafka, commit transaction khiến transactional records trở nên nhìn thấy với consumers dùng isolation.level=read_committed. **Abort transaction khác** không thể xóa record đã committed trong transaction trước.

Sơ đồ tình huống:

~~~mermaid
flowchart TD
    A["Primary transaction"] --> B{"Primary commit"}
    B -->|Thất bại| C["Rollback/retry khi còn hợp lệ"]
    B -->|Thành công| D["Primary state đã committed"]
    D --> E["Secondary transaction"]
    E --> F{"Secondary outcome"}
    F -->|Thành công| G["Business flow hoàn tất"]
    F -->|Thất bại xác nhận| H["Forward recovery hoặc compensation"]
    F -->|Không rõ| I["Reconciliation trước khi quyết định"]
    H --> J["Transaction mới / workflow recovery"]
    I --> J
~~~

Không viết code như:

~~~java
try {
    commitPrimary();
    commitSecondary();
} catch (Exception e) {
    rollbackPrimary(); // Không thể rollback commit đã hoàn tất.
}
~~~

Đây chỉ là pseudocode minh họa **anti-pattern**. Sau primary commit, cần một transaction mới và quy tắc nghiệp vụ để bù, nếu quyết định bù là phù hợp.

## 3. Rollback, forward recovery, compensation và reconciliation

Bốn khái niệm này phải được phân biệt:

| Khái niệm | Diễn ra khi | Tác dụng |
|---|---|---|
| **Rollback** | Transaction chưa commit | Bỏ thay đổi chưa commit của transaction đó |
| **Forward recovery** | Primary đã commit, secondary chưa hoàn tất | Thực hiện lại/hoàn tất secondary action |
| **Compensation** | Primary đã commit, cần đảo ảnh hưởng nghiệp vụ | Thực hiện hành động mới: cancel, release, refund |
| **Reconciliation** | Kết quả commit hoặc business state không rõ | Đối chiếu trạng thái và quyết định bước tiếp theo |

Ví dụ order database đã commit và Kafka unavailable năm giây. Nếu đơn hàng vẫn hợp lệ, **forward recovery publish OrderCreated** là lựa chọn hợp lý. Xóa order chỉ vì một lỗi network ngắn thường gây mất dữ liệu nghiệp vụ.

Ngược lại, nếu payment capture đã commit nhưng fulfillment không thể thực hiện sau deadline, ứng dụng có thể cần **refund** và **cancel order**. Refund là giao dịch mới, không phải rollback của capture transaction.

## 4. Spring Kafka transaction synchronization không phải 2PC

Trong Spring, nhiều transaction managers có thể tồn tại cùng lúc:

- **JpaTransactionManager** hoặc **DataSourceTransactionManager** cho database.
- **KafkaTransactionManager** cho transactional Kafka producer.

Một số cấu hình cho phép KafkaTemplate tham gia Kafka transaction được đồng bộ cùng Spring-managed database transaction. Spring điều phối begin/commit/rollback theo thứ tự dự kiến nhưng không tự biến hai hệ thống thành **two-phase commit (2PC)** có prepare/commit decision nguyên tử.

~~~text
DB transaction: BEGIN ... COMMIT OK
Kafka transaction: BEGIN ... COMMIT ERROR
~~~

Lỗi tại secondary commit có thể được đưa về caller theo hành vi của phiên bản Spring Kafka, nhưng database **đã commit**. Không được kết luận DB rollback chỉ vì Java method cuối cùng ném exception.

Trong các phiên bản Spring Kafka khác nhau, cách secondary commit exception được propagate và API cấu hình transaction manager có thể thay đổi. Khi vận hành, cần xác minh **thứ tự commit hiệu lực** và **trạng thái thực của từng resource** thay vì suy đoán từ tên annotation.

## 5. Failure windows trong database-first

Giả sử service tạo order trong DB và phát OrderCreated lên Kafka:

~~~mermaid
sequenceDiagram
    participant U as API client
    participant S as OrderService
    participant DB as Database
    participant K as Kafka
    participant R as Recovery worker

    U->>S: Create order
    S->>DB: BEGIN, insert order
    DB-->>S: Prepared business data
    S->>DB: COMMIT
    DB-->>S: COMMIT OK
    S->>K: Send/commit OrderCreated
    K--xS: Timeout hoặc failure
    Note over DB,K: DB commit không bị rollback
    R->>DB: Đọc durable operation/outbox state
    R->>K: Retry publish hoặc reconcile
~~~

Có nhiều cửa sổ lỗi:

1. **Process crash sau DB commit, trước Kafka send**: chỉ memory callback sẽ mất. Nếu chưa lưu ý định publish bền vững, event có thể mất.
2. **Kafka send thất bại**: DB vẫn committed.
3. **Kafka send đã ACK nhưng Kafka transaction commit thất bại**: chưa thể xem transactional output đã committed.
4. **Kafka commit thành công nhưng response bị mất**: ứng dụng nhận timeout, kết quả thực tế có thể đã thành công.
5. **Kafka publish thành công, ứng dụng crash trước khi lưu trạng thái hoàn tất**: retry có thể tạo record trùng.

Không có một câu lệnh catch/rollback đơn giản nào giải quyết mọi trường hợp. Cần durable intent, idempotency và reconciliation.

## 6. Failure windows trong Kafka-first

Nếu Kafka là primary:

~~~text
Kafka OrderCreated COMMITTED
Database INSERT order thất bại
~~~

Downstream consumers có thể đã:

- Reserve inventory.
- Bắt đầu fulfillment.
- Gửi notification.
- Tạo payment authorization.

Không thể xóa event đã committed. Có thể cân nhắc:

1. **Forward recovery database** khi có thể tạo lại order đúng định danh, đúng version và không vi phạm invariant.
2. **Compensating event**, ví dụ OrderCreationCancelled với cùng correlation/operation ID.
3. **Saga recovery**, lần lượt yêu cầu các service đã thực hiện side effect hoàn tác theo business semantics.
4. **Manual review** nếu action không thể bù an toàn.

Không gửi compensating event ngay khi Kafka commit response timeout mà chưa biết Kafka commit có thành công hay không. Một cancellation event cho một creation event chưa từng committed có thể khiến downstream state machine đi sai.

## 7. Ma trận quyết định sau primary commit

| Primary | Secondary | Độ chắc chắn | Hành động |
|---|---|---|---|
| Chưa commit | Chưa thực hiện | Rõ | Rollback/retry transaction ban đầu |
| Commit thành công | Chưa bắt đầu | Rõ | Forward recovery từ durable intent |
| Commit thành công | Fail rõ ràng, còn retry được | Rõ | Retry secondary với BackOff |
| Commit thành công | Fail vĩnh viễn | Rõ | Bù nghiệp vụ nếu domain yêu cầu |
| Commit thành công | Commit thành công | Rõ | COMPLETED; không compensation |
| Commit thành công | Timeout khi commit | **UNKNOWN** | Reconcile, không bù mù |
| Primary timeout | Secondary chưa chạy | **UNKNOWN** | Xác minh primary trước |
| Bù đã bắt đầu | Bù đang lỗi | Rõ/unknown | Retry bù idempotently hoặc escalate |

**UNKNOWN không tương đương FAILED.** Timeout chỉ nói rằng caller chưa nhận được kết quả đáng tin cậy, không khẳng định transaction chưa commit.

## 8. Khi nào forward recovery tốt hơn compensation?

Nếu primary state vẫn có giá trị và secondary là một thao tác có thể thực hiện muộn, **forward recovery** thường ưu tiên.

Ví dụ:

- Database order đã tạo, Kafka outage 20 giây: tiếp tục phát OrderCreated khi broker phục hồi.
- Outbox đang PENDING, producer thiếu ACL: sửa ACL rồi relay publish.
- Kafka event committed nhưng DB projection service down: replay event/đợi projection phục hồi.
- Inventory reserved, billing service tạm HTTP 503: retry theo policy trước khi quyết định cancel.

Compensation nên là **business decision**, không phải hệ quả tự động của một lỗi kỹ thuật. Một số hệ thống phải giới hạn deadline; khi secondary không thể hoàn tất trong thời hạn, forward recovery không còn giữ invariant và compensation mới phù hợp.

~~~mermaid
flowchart TD
    A["Primary đã commit"] --> B{"Secondary outcome xác nhận?"}
    B -->|Chưa| C["RECONCILING"]
    C --> B
    B -->|COMMITTED| D["COMPLETED"]
    B -->|FAILED hoặc NOT_STARTED| E{"Secondary có thể retry và còn deadline?"}
    E -->|Có| F["RETRY_PENDING -> forward recovery"]
    F --> B
    E -->|Không| G{"Compensation hợp lệ?"}
    G -->|Có| H["COMPENSATING"]
    H --> I["Compensating transaction mới"]
    I --> J["COMPENSATED khi đã xác nhận"]
    G -->|Không| K["MANUAL_REVIEW"]
~~~

## 9. Transactional outbox: mẫu thường ưu tiên cho DB-first

**Transactional outbox** xử lý vấn đề quan trọng nhất: **database commit xong nhưng thông tin cần publish chưa bền vững**.

Trong cùng DB transaction, service ghi:

1. Domain state, ví dụ một order mới.
2. Outbox event mô tả **ý định phát Kafka message**.

Sau commit, relay riêng đọc outbox và publish Kafka.

~~~mermaid
flowchart LR
    API["Create order"] --> TX["Database transaction"]
    TX --> O["orders"]
    TX --> E["outbox_events"]
    O --> COMMIT["DB COMMIT"]
    E --> COMMIT
    COMMIT --> W["Outbox relay / CDC"]
    W --> K["Kafka"]
    W --> RETRY["Retry / checkpoint publish"]
~~~

Nếu DB commit thành công, order và event intent cùng tồn tại. Nếu DB rollback, cả hai cùng rollback. Process chết trước publish vẫn không xóa mất outbox row.

Outbox không tạo distributed atomic commit với Kafka. Sau khi Kafka publish thành công, relay có thể crash trước khi đánh dấu PUBLISHED, dẫn đến **publish trùng khi retry**. Consumer downstream cần idempotency.

## 10. Ví dụ schema cho outbox

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(40) NOT NULL,
    version BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE outbox_events (
    event_id VARCHAR(128) PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(128) NOT NULL,
    event_type VARCHAR(128) NOT NULL,
    payload TEXT NOT NULL,
    publish_state VARCHAR(32) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL,
    last_error TEXT NULL
);

CREATE INDEX idx_outbox_publish_state
    ON outbox_events (publish_state, next_attempt_at, created_at);
~~~

Đây là schema minh họa; kiểu timestamp, JSON và chiến lược index tùy database. Với nhiều relay instances, cần bổ sung **claim/lease** hoặc row-level locking để ngăn hai workers publish cùng một row cùng lúc ngoài dự kiến.

Trạng thái ví dụ:

| State | Ý nghĩa |
|---|---|
| PENDING | DB đã commit intent, chưa xử lý publish |
| IN_FLIGHT | Worker claim event và đang gửi |
| RETRY_PENDING | Publish lỗi hoặc response không chắc chắn |
| PUBLISHED | Đã xác nhận publish theo producer/transaction policy |
| QUARANTINED | Lỗi cấu hình/schema hoặc hết policy, cần điều tra |

Không để IN_FLIGHT tồn tại mãi khi worker crash. Claim nên có timeout/lease và worker recovery phải tìm lại các rows đã hết lease.

## 11. Viết domain state và outbox trong cùng transaction

Ví dụ Spring service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCreationService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderCreationService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional("transactionManager")
    public void createOrder(CreateOrderCommand command) {

        Order order = orders.insert(
                command.orderId(),
                command.items()
        );

        OutboxEvent event = OutboxEvent.pending(
                command.eventId(),
                "OrderCreated",
                String.valueOf(order.id()),
                serialize(order)
        );

        outbox.insert(event);
    }
}
~~~

Trong ví dụ, OrderRepository, OutboxRepository, Order, OutboxEvent, CreateOrderCommand và serialize là API domain do ứng dụng định nghĩa. Transaction manager có tên **transactionManager** phải quản lý database transaction chứa cả hai repository writes.

Nếu outbox insert lỗi thì order insert cũng rollback. Nếu commit thành công thì cả hai cùng tồn tại. Không thay thao tác outbox insert bằng một callback Kafka send thuần memory nếu yêu cầu không mất event qua crash.

## 12. Outbox relay và publish acknowledgement

Một relay làm việc theo chu trình:

1. Claim PENDING/RETRY_PENDING row đủ điều kiện.
2. Xác định topic, key, payload, event ID.
3. Publish bằng KafkaTemplate phù hợp.
4. Xác minh kết quả gửi hoặc Kafka transaction commit nếu dùng transactional producer.
5. Mark PUBLISHED trong DB transaction mới.
6. Nếu publish thất bại, cập nhật attempts/next_attempt_at và retry.

Pseudocode Java:

~~~java
public void publish(OutboxEvent event) {

    kafkaTemplate.send(
            event.destinationTopic(),
            event.aggregateId(),
            event.payload()
    ).join();

    outboxStateService.markPublishedInNewTransaction(
            event.eventId()
    );
}
~~~

Đoạn code minh họa producer gửi **không giao dịch** và future API của Spring Kafka hiện đại. Nếu dùng Kafka transaction, phải xem **commit transaction** mới là ranh giới output committed; send future hoàn tất không thay commit.

Nếu relay chết **sau Kafka publish thành công nhưng trước DB markPublished**, event được gửi lại. Để an toàn, event ID giữ nguyên qua retry và downstream consumer xử lý idempotently.

Đừng mark PUBLISHED trước khi Kafka send/commit được xác nhận theo policy. Một flag đặt quá sớm có thể khiến event bị bỏ lại vĩnh viễn.

## 13. Idempotent consumer bằng inbox table

Outbox là cơ chế reliable publish, **inbox** là cơ chế ngăn side effect lặp khi record bị giao lại.

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Service consumer:

~~~java
@Transactional("transactionManager")
public void reserveInventory(OrderCreated event) {

    boolean firstTime =
            processedEvents.insertIfAbsent(
                    "inventory-service",
                    event.eventId()
            );

    if (!firstTime) {
        return;
    }

    inventory.reserve(
            event.orderId(),
            event.items()
    );
}
~~~

Phương thức insertIfAbsent phải **atomic** với unique constraint hoặc câu lệnh database tương đương. Marker và inventory changes phải nằm trong **cùng DB transaction**. Nếu transaction rollback, marker cũng rollback để lần sau retry hợp lệ. Nếu DB commit nhưng Kafka offset chưa commit, redelivery không reserve lần thứ hai.

## 14. Khi nào cần compensation thật sự?

Một số nghiệp vụ không thể chờ secondary mãi:

- Reservation hết hạn trước khi downstream xác nhận.
- Payment captured nhưng không thể fulfillment.
- Workflow cần hoàn tất trong SLA đã thỏa thuận.
- Một hành động đã commit làm mất khả năng thực hiện bước kế tiếp.
- External API trả kết quả từ chối cuối cùng, không phải lỗi tạm thời.

Trong các tình huống này, cần giao dịch bù **theo nghiệp vụ**. Ví dụ:

| Primary action | Compensation |
|---|---|
| OrderCreated | OrderCancelled với audit trail |
| InventoryReserved | ReleaseInventory |
| PaymentCaptured | RefundPayment, tham chiếu original capture |
| ShippingRequested | CancelShipment nếu provider hỗ trợ |
| AccessGranted | RevokeAccess |
| EmailSent | Gửi đính chính, không thể unsend |
| Kafka event committed | Publish compensating event mới |

Compensation không luôn hoàn tác hoàn hảo. Refund có thể mất thời gian hoặc có phí; email đã gửi không thể bị thu hồi; inventory đã tiêu thụ có thể không còn khả năng release an toàn.

## 15. Thiết kế saga state machine

Một workflow bền vững có thể dùng:

~~~text
PENDING
  |
  v
PRIMARY_COMMITTED
  |
  +--> SECONDARY_PENDING
           |
           +--> COMPLETED
           |
           +--> RETRY_PENDING
           |
           +--> COMMIT_OUTCOME_UNKNOWN --> RECONCILING
           |
           +--> COMPENSATING
                    |
                    +--> COMPENSATED
                    |
                    +--> COMPENSATION_RETRY
                    |
                    +--> MANUAL_REVIEW
~~~

Đây là state machine **do ứng dụng định nghĩa**, không phải một enum mặc định của Spring Kafka.

Một operation row nên lưu:

| Field | Mục đích |
|---|---|
| operation_id | Định danh logic xuyên toàn workflow |
| aggregate_id | Đơn hàng hoặc đối tượng nghiệp vụ |
| primary_resource | Database/Kafka hoặc service đã commit |
| primary_status | COMMITTED/UNKNOWN/etc. |
| secondary_status | PENDING/COMMITTED/FAILED/UNKNOWN |
| compensation_status | NONE/REQUESTED/IN_PROGRESS/COMPLETED/FAILED |
| event_id | Định danh message ổn định |
| version | Optimistic concurrency/fencing state transition |
| attempts | Số lần retry |
| next_attempt_at | Lịch retry bền vững |
| deadline_at | Deadline nghiệp vụ |
| last_error | Lỗi cuối có kiểm soát dữ liệu nhạy cảm |

Không chỉ lưu state trong RAM hoặc đặt một scheduled task in-memory: crash sẽ làm mất toàn bộ ý định recovery.

## 16. Ví dụ compensation: giải phóng reservation

Sau primary commit, workflow có thể chuyển sang COMPENSATING rồi thực hiện một database transaction mới:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReservationCompensationService {

    private final ReservationRepository reservations;
    private final OutboxRepository outbox;

    public ReservationCompensationService(
            ReservationRepository reservations,
            OutboxRepository outbox) {
        this.reservations = reservations;
        this.outbox = outbox;
    }

    @Transactional("transactionManager")
    public void compensate(
            String operationId,
            long orderId) {

        Reservation reservation =
                reservations.lockByOrderId(orderId)
                        .orElseThrow();

        if (reservation.isReleased()) {
            return;
        }

        if (!reservation.mayRelease()) {
            throw new IllegalStateException(
                    "Reservation requires manual review"
            );
        }

        reservation.release();

        outbox.insertIfAbsent(
                operationId + ":inventory-released",
                "InventoryReleased",
                String.valueOf(orderId),
                toPayload(reservation)
        );
    }
}
~~~

Code mang tính minh họa domain. lockByOrderId, mayRelease, insertIfAbsent và toPayload phải được triển khai theo database/ứng dụng. Điều cốt lõi:

- Không gọi rollback trên primary transaction đã commit.
- Mở **transaction mới** cho trạng thái compensation.
- Giữ idempotency: gọi hai lần không release hai lần.
- Ghi compensation event vào outbox **cùng transaction**.
- Dùng operation ID ổn định qua các lần retry.

Nếu release cần gọi service bên ngoài, transaction này nên ghi **ReleaseInventoryRequested** và chờ acknowledgement từ service đó, thay vì chỉ đánh dấu đã release khi command vừa được gửi.

## 17. Compensating event không xóa event đã commit

Nếu OrderCreated đã được Kafka commit, hệ thống không thể xóa nó bằng một Kafka rollback ở transaction mới. Thay vào đó, publish một event:

~~~json
{
  "eventId": "order-42-cancelled-v1",
  "operationId": "order-42-create",
  "orderId": 42,
  "type": "OrderCancelled",
  "reason": "PAYMENT_REJECTED",
  "originalEventId": "order-42-created-v1"
}
~~~

Downstream consumer cần hiểu sequence:

~~~text
OrderCreated -> InventoryReserved -> OrderCancelled -> InventoryReleased
~~~

Không mọi consumer đều quan sát và xử lý theo đúng cùng thời gian. Do đó, nên có state/version, deduplication và handling cho event đến muộn.

Đặc biệt, một tombstone trong compacted topic không phải cơ chế rollback chung của Kafka event. Tombstone là một record mới có ý nghĩa riêng với compaction và consumer semantics.

## 18. Kết quả commit secondary không rõ

Một tình huống khó:

~~~text
T0: Database primary COMMIT OK
T1: Producer gửi Kafka commitTransaction()
T2: Broker xử lý commit
T3: Network timeout trước khi client nhận response
~~~

Ứng dụng biết DB đã commit và Kafka commit **có thể** đã thành công. Không biết chắc chỉ bằng exception timeout.

Các hành động **không nên thực hiện ngay**:

- Đánh dấu secondary FAILED vĩnh viễn.
- Xóa order hoặc bắt đầu refund.
- Phát OrderCancelled không kiểm tra domain state.
- Gửi một event mới với event ID khác và coi như tác vụ mới.
- Tự gọi abort và tuyên bố broker chưa commit.

Cần reconcile bằng các nguồn sự thật có sẵn: operation state, outbox event ID, producer transaction outcome khi có bằng chứng, Kafka audit/consumer state, downstream inbox và business state.

Nếu không thể đọc lại chính xác commit outcome của một lần gửi, hướng robust thường là **retry cùng logical event ID**, kết hợp idempotent downstream consumer. Với Kafka transactional producer ở fatal/fenced state, đóng và tạo producer phù hợp theo client contract thay vì tái sử dụng mù quáng.

## 19. Kafka send ACK khác Kafka transaction commit

Ba mốc khác nhau:

| Mốc | Có thể kết luận gì? |
|---|---|
| KafkaTemplate.send() được gọi | Đã yêu cầu producer gửi |
| Send future trả thành công | Broker đã ACK gửi record theo producer config |
| Kafka transaction commit thành công | Transactional record ở trạng thái committed |
| Downstream business ack | Một service khác xác nhận đã xử lý nghiệp vụ |

Nếu dùng transactional KafkaTemplate, send future thành công **không có nghĩa transaction đã committed**. Nếu không dùng Kafka transaction, producer ACK cũng chưa chứng minh downstream business action thành công.

Một compensation workflow nên dựa trên **business outcomes**, chứ không chỉ đợi Kafka send future rồi đánh dấu saga COMPLETED.

## 20. Spring transaction proxy và vị trí bắt exception

Với @Transactional, Spring thường commit transaction khi method kết thúc và transaction interceptor kết thúc scope. Do đó, một catch **bên trong method @Transactional** có thể không bắt được exception phát sinh ở commit boundary sau khi method body return.

Nếu cần xử lý exception từ call, đặt caller bên ngoài transaction proxy:

~~~java
@Component
public class CreateOrderCommandHandler {

    private final PrimaryOrderService primary;
    private final RecoveryCoordinator recovery;

    public CreateOrderCommandHandler(
            PrimaryOrderService primary,
            RecoveryCoordinator recovery) {
        this.primary = primary;
        this.recovery = recovery;
    }

    public void execute(CreateOrderCommand cmd) {
        try {
            primary.create(cmd);
        } catch (RuntimeException failure) {
            // Không đoán DB đã rollback hay đã commit.
            recovery.reconcile(
                    cmd.operationId(),
                    failure
            );
            throw failure;
        }
    }
}
~~~

RecoveryCoordinator phải đọc **durable status** để xác định primary commit, secondary outcome và policy, không dựa vào catch exception làm bằng chứng.

Nếu Spring @Transactional method được gọi nội bộ cùng bean, self-invocation có thể bypass transaction proxy. Tách service beans rõ ràng hoặc dùng TransactionTemplate để chỉ định transaction boundary.

## 21. Synchronized Kafka transaction trong DB-first

Một cấu trúc thường thấy:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final KafkaTemplate<String, OrderCreated> kafka;

    public OrderApplicationService(
            OrderRepository orders,
            KafkaTemplate<String, OrderCreated> kafka) {
        this.orders = orders;
        this.kafka = kafka;
    }

    @Transactional("dataSourceTransactionManager")
    public void create(CreateOrderCommand cmd) {

        Order order = orders.insert(cmd);

        kafka.send(
                "orders.created",
                String.valueOf(order.id()),
                new OrderCreated(order.id(), cmd.eventId())
        );
    }
}
~~~

Đây là **ví dụ mô hình**, không nên copy thẳng làm phương án reliability production. Tùy cấu hình KafkaTemplate transactional ProducerFactory, Spring transaction synchronization, Boot và Kafka versions, Kafka transaction có thể được đồng bộ với DB transaction. Trong DB-first ordering, nếu DB commit xong mà Kafka commit lỗi, primary state vẫn tồn tại.

Không khắc phục bằng việc thêm @Transactional vào cùng method rồi tuyên bố 2PC. Với yêu cầu **DB commit phải luôn để lại durable publish intent**, chọn **insert outbox** thay vì chỉ Kafka send trong synchronized transaction.

## 22. Claim/lease và chống nhiều worker bù trùng

Sau failover hoặc scale-out, nhiều recovery workers có thể quét cùng operation:

~~~text
Worker A thấy COMPENSATION_RETRY
Worker B cũng thấy COMPENSATION_RETRY
Cả hai cùng gửi refund/release
~~~

Cần ownership có kiểm soát:

- SQL transaction kết hợp row lock hoặc SKIP LOCKED nếu DB hỗ trợ.
- Atomic compare-and-set transition theo state/version.
- Lease có claimed_until và claimed_by để hồi phục khi worker chết.
- Unique constraint trên operation_id + compensation_step.
- Idempotency key ở downstream API.

Ví dụ update có guard:

~~~sql
UPDATE saga_operations
SET status = 'COMPENSATING',
    version = version + 1
WHERE operation_id = ?
  AND status = 'COMPENSATION_RETRY'
  AND version = ?;
~~~

Nếu updated rows bằng 0, worker không nên tự ý thực hiện compensation. Có thể operation đã được worker khác claim hoặc state đã thay đổi.

Không chỉ dùng một khóa Java synchronized trong mỗi process: nó không bảo vệ giữa các pods và không tồn tại sau restart.

## 23. Late events và race giữa forward recovery và compensation

Một race điển hình:

1. Forward recovery worker retry OrderCreated.
2. Deadline đến, saga chuyển sang COMPENSATING.
3. Forward recovery response đến muộn và đánh dấu COMPLETED.
4. Compensation worker cũng phát OrderCancelled.

Không có state machine và fencing, hệ thống có thể rơi vào hai trạng thái trái nhau.

Một số nguyên tắc:

- Claim/lease phải gắn với **operation version**.
- Chỉ chấp nhận transition nếu current state còn cho phép.
- Khi bắt đầu compensation, không cho forward worker cũ tiếp tục commit trạng thái success vô điều kiện.
- Late acknowledgement được ghi audit nhưng không tự đảo terminal state.
- Domain event có version/sequence để downstream xử lý out-of-order khi có thể.
- Saga state authority là DB row hoặc store bền vững, không phải memory variable.

Để hủy một hành động đã có thể thành công, trước tiên phải xác minh trạng thái và tính idempotent của compensating operation.

## 24. Retry budget, deadline và manual review

Một failure tạm thời không nên kích hoạt compensation ngay, nhưng retry mãi cũng không phù hợp.

| Chính sách | Ý nghĩa |
|---|---|
| Secondary max attempts | Số lần thử bước phụ |
| Retry BackOff | Khoảng chờ giữa các lần thử |
| Secondary deadline | Sau thời điểm này secondary hoàn tất muộn có thể không còn hợp lệ |
| Compensation max attempts | Số lần retry bù |
| Compensation deadline | Khi nào cần alert/escalate |
| Manual review threshold | Khi nào operator phải can thiệp |
| Outbox retention | Bao lâu giữ chưa publish intent |
| DLT retention | Bao lâu giữ failed messages để replay |

Ví dụ reservation có TTL 15 phút. Nếu Kafka unavailable 5 giây, retry publish là hợp lý. Nếu workflow đã vượt deadline và stock reservation có thể được giải phóng, saga có thể bắt đầu compensation.

Deadline cần lưu bền vững ở operation state. Không chỉ phụ thuộc setTimeout/scheduled callback trong memory của một instance.

## 25. DLT không phải compensation tự động

DLT giữ Kafka record đã hết retry hoặc không thể xử lý theo policy. Nó không biết nghiệp vụ đã commit những side effects nào trong DB hay external API.

Một DLT record có thể tượng trưng cho:

- Event malformed chưa xử lý gì.
- DB action đã commit nhưng Kafka offset chưa commit.
- Downstream step bị từ chối vĩnh viễn.
- Outbox relay publish thất bại.
- Compensation command không được thực thi.
- Compensation đã hoàn tất nhưng acknowledgement chưa đến.

Do đó, **không cấu hình mọi DLT record tự động hủy order**. Recovery service cần tra operation state, original event ID và các side effects đã xác nhận.

Replay phải giữ event ID/idempotency key. Nếu cần compensation, tạo compensation operation riêng với guard đúng state.

## 26. Khi compensation cũng thất bại

Một compensation không được bảo đảm thành công ngay:

- Refund API timeout.
- Inventory service unavailable.
- Database deadlock.
- Serialization/ACL lỗi trên topic compensation.
- Shipment đã quá muộn để cancel.

Cần lưu trạng thái **COMPENSATION_RETRY** và retry an toàn. Nếu API đã xử lý refund nhưng response mất, phải đối chiếu bằng idempotency key hoặc provider transaction ID trước khi refund tiếp.

Sau khi hết retry, chuyển MANUAL_REVIEW kèm đầy đủ evidence. Đừng nuốt exception rồi đánh dấu COMPENSATED chỉ để consumer lag giảm.

Compensation là **workflow có thể thất bại**, không phải hàm cleanup được đảm bảo thành công.

## 27. Kafka-first và downstream compensation theo saga

Ví dụ có các bước:

~~~text
A. OrderCreated event committed
B. InventoryReserved committed
C. PaymentCaptured succeeded
D. ShipmentCreation FAILED permanently
~~~

Các bước A, B, C đã tạo side effects. Saga có thể bù theo thứ tự phụ thuộc:

~~~text
D failed
   |
   v
Refund payment (compensate C)
   |
   v
Release inventory (compensate B)
   |
   v
OrderCancelled (compensate A)
~~~

Đây chỉ là một thứ tự minh họa; thực tế có thể thay đổi tùy domain. Refund và release thường là actions bất đồng bộ. Saga không nên báo COMPENSATED khi mới **gửi yêu cầu refund**, nếu provider chưa xác nhận hoàn tất.

Với workflow có nhiều bước, lưu state cho **từng compensating step** thay vì một boolean compensationDone chung.

## 28. Quan sát và metrics

Một dashboard chỉ theo dõi consumer lag thường không phát hiện partial commits trong Kafka + DB.

| Metric | Câu hỏi |
|---|---|
| primary_commit_success | Primary commits có bình thường không? |
| secondary_commit_failure | Có partial commits mới xuất hiện không? |
| secondary_outcome_unknown | Bao nhiêu operation cần reconcile? |
| outbox_pending_count | Bao nhiêu event chưa publish? |
| outbox_oldest_age | Event cũ nhất chờ bao lâu? |
| outbox_publish_retry | Có retry storm không? |
| saga_compensating_count | Có bao nhiêu nghiệp vụ đang bù? |
| compensation_failure_rate | Bước bù có bị lỗi không? |
| compensation_duration | Bù mất bao lâu tới terminal state? |
| manual_review_backlog | Có bao nhiêu trường hợp cần người xử lý? |
| dlt_oldest_age | DLT có tồn đọng vượt SLA không? |

Ví dụ log có cấu trúc:

~~~text
event=secondary_commit_outcome_unknown
service=order-service
operation_id=create-order-42
aggregate_id=order-42
primary_resource=database
primary_commit=CONFIRMED
secondary_resource=kafka
secondary_outcome=UNKNOWN
outbox_event_id=order-42-created-v1
saga_state=RECONCILING
exception=TimeoutException
~~~

Không ghi secondary_outcome=FAILED khi chỉ có timeout. Không đưa operation_id hoặc event_id vào metric labels có cardinality lớn; dùng các định danh đó ở logs/traces có kiểm soát.

## 29. Runbook khi primary đã commit nhưng secondary lỗi

1. Xác định operation ID, aggregate ID, event ID và service.
2. Xác nhận primary resource nào và bằng chứng primary commit đã thành công.
3. Phân loại secondary: NOT_STARTED, FAILED_CONFIRMED, COMMITTED hoặc UNKNOWN.
4. Nếu UNKNOWN, reconcile trước khi retry/bù.
5. Kiểm tra durable outbox row hoặc saga operation state.
6. Kiểm tra Kafka publish result và Kafka transaction commit nếu có.
7. Kiểm tra external side effects và downstream inbox.
8. Đối chiếu deadline và retry budget.
9. Nếu forward recovery hợp lệ, claim operation và retry secondary.
10. Nếu không còn hợp lệ, chuyển sang COMPENSATING bằng state guard.
11. Ghi compensation intent vào outbox trong transaction mới.
12. Chờ và xác minh business acknowledgement của từng bước bù.
13. Nếu bù lỗi, retry idempotently hoặc chuyển MANUAL_REVIEW.
14. Đối chiếu DB/Kafka/downstream state cuối cùng.
15. Ghi audit ai quyết định compensation và lý do.
16. Thêm test cho failure window vừa xảy ra.

Không xử lý sự cố bằng reset consumer offsets, xóa records hoặc xóa database rows một cách thủ công nếu chưa phân tích khả năng mất dữ liệu hoặc duplicate side effects.

## 30. Fault injection và integration testing

Cần test các cửa sổ lỗi thực tế:

| Kịch bản test | Kỳ vọng |
|---|---|
| DB rollback trước commit | Order và outbox đều rollback |
| DB commit rồi app crash trước Kafka publish | Outbox relay tìm lại event |
| Kafka producer timeout | Operation không bị đánh FAILED bừa |
| Kafka send success rồi relay crash trước markPublished | Event có thể được gửi lại; inbox ngăn side effect trùng |
| Kafka transaction commit outcome unknown | Reconciliation, không compensate vô điều kiện |
| Kafka-first commit thành công, DB rollback | Saga forward recover/compensate theo domain |
| Compensation transaction commit rồi Kafka publish fail | Compensation intent còn trong outbox |
| Compensation command bị giao lại | Không refund/release trùng |
| Hai workers cùng claim | Một transition có hiệu lực hoặc idempotency bảo vệ |
| DLT chứa event đã xử lý một phần | Recovery tra saga state trước khi hành động |
| Retry response đến muộn sau khi saga đang COMPENSATING | State guards ngăn transition sai |
| Compensation API timeout sau server success | Reconcile bằng idempotency key |
| Recovery worker restart sau lease timeout | Pending operations được nhận lại |

### Bài integration test order + outbox + compensation

1. Khởi tạo database và Kafka qua Testcontainers hoặc môi trường tương đương.
2. Tạo order với DB transaction chứa order và outbox row.
3. Assert cả hai cùng commit.
4. Làm Kafka không khả dụng trước relay publish.
5. Xác nhận outbox PENDING vẫn tồn tại.
6. Khôi phục Kafka, cho relay gửi OrderCreated.
7. Gây crash sau Kafka ACK trước khi markPublished.
8. Khởi động relay và xác nhận idempotent consumer không tạo side effect trùng.
9. Mô phỏng downstream business failure vĩnh viễn.
10. Chuyển saga sang COMPENSATING và tạo outbox compensation event.
11. Xác nhận downstream áp dụng compensation đúng một lần.
12. Replay compensation command, kiểm tra idempotency.
13. Đối chiếu trạng thái cuối và audit.
14. Xác nhận dashboards/alerts phản ánh failure và recovery.

Unit test cho method compensate không chứng minh được Kafka transaction outcome hay DB transaction commit; cần integration tests với failure injection để kiểm tra ranh giới commit.

## 31. Những lỗi triển khai thường gặp

**Gọi rollback sau primary commit.** Một transaction đã commit không thể được rollback bằng chính transaction cũ.

**Nhầm transaction synchronization với atomic distributed transaction.** DB commit và Kafka commit vẫn có failure window.

**Catch exception rồi kết luận DB chưa commit.** Secondary commit exception có thể xảy ra sau DB commit.

**Chỉ gửi Kafka từ callback in-memory sau DB commit.** Process crash có thể làm mất publish intent.

**Đánh dấu event PUBLISHED trước producer ACK/transaction commit.** Có nguy cơ mất event.

**Không giữ event ID ổn định qua retries.** Downstream không deduplicate được.

**Bù ngay khi timeout.** Commit secondary có thể đã thành công nhưng response bị mất.

**Xóa dữ liệu primary để bù.** Có thể mất audit và làm sai các references đã được hệ thống khác thấy.

**Không kiểm soát late success.** Forward retry và compensation có thể đồng thời làm workflow mâu thuẫn.

**Cho rằng DLT có nghĩa phải cancel.** DLT chỉ cho biết một đường xử lý lỗi; cần domain context.

**Retry compensation bằng ID mới.** Refund hoặc release có thể xảy ra nhiều lần.

**Giữ DB transaction mở khi gọi remote API lâu.** Tăng lock contention và deadlocks.

**Không lưu compensation progress.** Worker crash khiến saga không biết bước nào đã xong.

**Không kiểm tra business acknowledgement.** Gửi command thành công không có nghĩa compensation đã hoàn tất.

## 32. Checklist trước production

**Transaction boundaries**

- [ ] Biết rõ commit order và primary/secondary resources.
- [ ] Phân biệt rollback, forward recovery, compensation và reconciliation.
- [ ] Có cách nhận diện secondary outcome UNKNOWN.
- [ ] Không coi @Transactional DB+Kafka là 2PC.
- [ ] Có durable publish intent cho DB-first nếu không chấp nhận mất event.

**Reliability**

- [ ] Outbox và domain state commit cùng DB transaction.
- [ ] Outbox relay có claim/lease và khả năng phục hồi sau crash.
- [ ] Event ID và operation ID ổn định qua retry/replay.
- [ ] Downstream consumer idempotent bằng inbox/unique constraint.
- [ ] Compensation actions có idempotency keys riêng.

**Nghiệp vụ**

- [ ] Có state machine và deadline.
- [ ] Biết action nào không thể đảo ngược hoàn toàn.
- [ ] Phân biệt compensation requested và compensation completed.
- [ ] Có manual review path cho nghiệp vụ không bù được.
- [ ] Có guard để late events không làm sai terminal state.

**Vận hành**

- [ ] Có metrics cho primary commit, secondary failures và unknown outcomes.
- [ ] Dashboard outbox age, retry, saga compensation và DLT.
- [ ] Có alert stuck compensation và manual review backlog.
- [ ] Có runbook reconciliation với operator ownership.
- [ ] Có fault-injection tests tại các điểm sau primary commit.
- [ ] Có audit trail cho mọi bước bù và replay.

## 33. Nguyên tắc thiết kế

**Compensation sau primary commit** nghĩa là **giải quyết hậu quả của một thay đổi đã committed**, không phải rollback transaction đó. Trước khi hành động, phải xác nhận primary commit, phân loại secondary outcome và xác định mục tiêu nghiệp vụ. Nếu secondary còn có thể hoàn tất, ưu tiên **forward recovery**; nếu nghiệp vụ bắt buộc hủy, thực hiện **compensating transaction mới** có idempotency, state guard, audit và khả năng retry.

Với Spring Kafka và database, một kiến trúc đáng tin cậy thường dùng **transactional outbox** để giữ durable publish intent, **inbox** để chống duplicate consumption và **saga** cho các bước bù liên service. Không coi timeout từ Kafka commit là thất bại chắc chắn. Hãy dùng reconciliation, event/operation ID ổn định, kiểm thử crash ở mọi failure window và giám sát trạng thái tới khi operation đạt **COMPLETED** hoặc **COMPENSATED** có bằng chứng.

Đây là con đường thực tế để đạt **eventual consistency có kiểm soát** giữa Kafka và database mà không giả định hai resource có commit nguyên tử.
