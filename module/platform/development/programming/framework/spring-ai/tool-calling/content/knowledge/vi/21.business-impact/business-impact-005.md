# Phối hợp nhiều hệ thống bằng outbox hoặc bù trừ khi cần

Một tool có thể bắt đầu một quy trình đi qua nhiều dịch vụ: tạo đơn hàng, giữ tồn kho, thu tiền, tạo vận đơn và gửi thông báo. Mỗi dịch vụ sở hữu database riêng và chỉ có thể commit hoặc rollback transaction của chính nó. Nếu ứng dụng gọi tuần tự các API rồi hy vọng tất cả cùng thành công, một lỗi giữa chừng có thể để lại trạng thái dở dang.

Có hai vấn đề cần giải quyết:

- **Đưa sự kiện ra khỏi một service một cách tin cậy:** database đã commit nhưng ứng dụng có thể chết trước khi gửi message; hoặc message được gửi dù transaction database rollback. Transactional outbox giải quyết sự không nhất quán giữa ghi database và publish message.
- **Điều phối một nghiệp vụ trải qua nhiều service:** một bước có thể thất bại sau khi các bước trước đã commit. Saga phối hợp các local transaction và chạy hành động bù trừ khi cần.

Outbox và saga giải quyết hai phần khác nhau và thường được dùng cùng nhau. Outbox bảo đảm mỗi service phát được thông điệp tương ứng với thay đổi đã commit. Saga quyết định bước tiếp theo, khi nào retry và phải bù trừ những tác động nào.

Bài này sử dụng Spring AI 2.1.0, Spring Framework và Spring Modulith làm bối cảnh tích hợp. Ví dụ nghiệp vụ là quy trình đặt hàng qua Order, Inventory, Payment và Shipping.

## Vì sao không thể dùng một local transaction cho nhiều service?

Trong kiến trúc database-per-service, Order Service quản lý database đơn hàng, Inventory Service quản lý tồn kho, Payment Service quản lý thanh toán và Shipping Service quản lý vận chuyển. Transaction của Order Service không thể tự rollback transaction đã commit ở Payment Service.

Giả sử ứng dụng làm theo cách tuần tự:

1. Ghi order vào database.
2. Gửi message OrderPlaced.
3. Gọi Inventory Service để giữ hàng.
4. Gọi Payment Service để thu tiền.
5. Gọi Shipping Service để tạo vận đơn.

Mỗi bước có một cửa sổ lỗi riêng. Ví dụ database Order commit thành công nhưng broker không nhận được event; hoặc Payment capture thành công nhưng response bị timeout. Ứng dụng không thể biết chắc chỉ từ kết nối HTTP rằng dịch vụ đích chưa xử lý.

### Hai kiểu dual write nguy hiểm

| Thứ tự | Lỗi có thể xảy ra | Hậu quả |
|---|---|---|
| Ghi DB trước, publish message sau | DB commit, process chết trước publish. | Dữ liệu đã đổi nhưng service khác không biết. |
| Publish message trước, ghi DB sau | Message được gửi, DB transaction rollback. | Service khác xử lý một thay đổi chưa từng commit. |
| Ghi DB và publish song song | Một bên thành công, bên kia thất bại. | Không thể xác định một kết quả atomic chỉ từ hai lời gọi riêng. |

Không giải quyết được dual write bằng cách đặt hai lệnh trong cùng @Transactional thông thường. Transaction manager JDBC/JPA quản lý database resource; nó không tự enlist một HTTP call hoặc message broker vào cùng local transaction.

## Transactional outbox giải quyết dual write như thế nào?

Outbox là một bảng trong cùng database với dữ liệu nghiệp vụ. Trong một transaction local, service vừa cập nhật trạng thái nghiệp vụ vừa thêm một bản ghi mô tả event cần publish. Nếu transaction commit, cả hai cùng tồn tại. Nếu rollback, cả hai cùng biến mất.

Một tiến trình relay riêng đọc các bản ghi outbox đã commit rồi gửi chúng đến broker. Sau khi broker xác nhận nhận message, relay đánh dấu bản ghi đã publish.

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant Service as Order Service
    participant DB as Order Database
    participant Relay as Outbox Relay
    participant Broker as Message Broker
    participant Inventory as Inventory Service

    API->>Service: placeOrder(command)
    Service->>DB: BEGIN
    Service->>DB: INSERT order (PENDING)
    Service->>DB: INSERT outbox (OrderPlaced)
    Service->>DB: COMMIT
    Service-->>API: orderId + PENDING
    Relay->>DB: Đọc event chưa publish
    DB-->>Relay: Outbox event đã commit
    Relay->>Broker: Publish OrderPlaced
    Broker-->>Relay: Broker ACK
    Relay->>DB: Đánh dấu PUBLISHED
    Broker->>Inventory: Deliver OrderPlaced
    Inventory->>Inventory: Local transaction + deduplication
~~~

Điểm quan trọng là service nghiệp vụ chỉ ghi database và outbox trong cùng transaction. Relay chịu trách nhiệm giao message ra ngoài sau commit.

## Thiết kế bảng outbox

Một bảng outbox tối thiểu có thể chứa:

| Trường | Mục đích |
|---|---|
| event_id | ID duy nhất của event, dùng để deduplicate. |
| aggregate_type | Loại aggregate, ví dụ Order. |
| aggregate_id | ID của aggregate phát event. |
| aggregate_version | Phiên bản hoặc sequence để bảo toàn thứ tự theo aggregate. |
| event_type | Tên loại event, ví dụ OrderPlaced. |
| payload | Payload event đã serialize theo schema version. |
| occurred_at | Thời điểm thay đổi nghiệp vụ xảy ra. |
| status | PENDING, IN_FLIGHT, PUBLISHED, FAILED. |
| attempts | Số lần relay thử gửi. |
| next_attempt_at | Thời điểm được phép retry tiếp. |
| locked_until | Thời hạn lease để một relay instance claim event. |
| published_at | Thời điểm broker xác nhận nhận event. |

Ví dụ DDL rút gọn cho PostgreSQL:

~~~sql
CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(120) NOT NULL,
    aggregate_id VARCHAR(160) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type VARCHAR(160) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_until TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_outbox_pending
    ON outbox_event (next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'FAILED');
~~~

Đây là schema minh họa. Với hệ quản trị khác, kiểu JSON, cú pháp index và cơ chế claim event sẽ khác. Có thể tách payload lớn sang object storage, nhưng phải giữ tham chiếu bền vững và bảo đảm consumer có thể đọc payload trong suốt thời gian cần replay.

Event nên là một hợp đồng tích hợp ổn định, ví dụ OrderPlacedV1, thay vì serialize nguyên JPA entity. Không đưa password, token, dữ liệu thanh toán nhạy cảm hoặc internal field không cần thiết vào payload. Hãy định nghĩa rõ schema version và chính sách tương thích khi thêm/đổi field.

## Ghi nghiệp vụ và outbox trong cùng transaction

Một application service thực hiện hai lệnh ghi trong cùng transaction:

~~~java
public record PlaceOrderCommand(
        String customerId,
        List<OrderLineCommand> lines,
        String idempotencyKey) {
}

public record OrderLineEvent(String productId, int quantity) {
}

public record OrderPlaced(
        String eventId,
        String orderId,
        String customerId,
        List<OrderLineEvent> lines,
        long aggregateVersion,
        Instant occurredAt) {
}

@Service
class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final OutboxRepository outboxRepository;
    private final EventSerializer eventSerializer;

    OrderApplicationService(
            OrderRepository orderRepository,
            OutboxRepository outboxRepository,
            EventSerializer eventSerializer) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
        this.eventSerializer = eventSerializer;
    }

    @Transactional
    public PlaceOrderResult place(PlaceOrderCommand command) {
        Order order = Order.pending(
                command.customerId(),
                command.lines(),
                command.idempotencyKey()
        );

        orderRepository.save(order);

        OrderPlaced event = new OrderPlaced(
                UUID.randomUUID().toString(),
                order.getId(),
                order.getCustomerId(),
                order.getLines().stream()
                        .map(line -> new OrderLineEvent(
                                line.getProductId(),
                                line.getQuantity()))
                        .toList(),
                order.getVersion(),
                Instant.now()
        );

        outboxRepository.save(OutboxEvent.pending(
                UUID.fromString(event.eventId()),
                "Order",
                order.getId(),
                event.aggregateVersion(),
                "OrderPlaced",
                1,
                eventSerializer.serialize(event)
        ));

        return new PlaceOrderResult(order.getId(), "PENDING");
    }
}
~~~

Trong ví dụ, OrderLineEvent là DTO event chỉ chứa mã sản phẩm và số lượng cần thiết cho Inventory Service. Không đưa trực tiếp entity OrderLine hoặc quan hệ JPA vào payload tích hợp.

Nếu orderRepository.save hoặc outboxRepository.save thất bại, transaction rollback. Không có trường hợp order commit mà event tương ứng không được ghi vào outbox, miễn là cả hai repository tham gia cùng transaction manager và cùng database transaction.

Không publish message trực tiếp bên trong method @Transactional này rồi mới commit database. Làm như vậy sẽ đưa network/broker latency vào transaction và vẫn không giải quyết được lỗi khi một bên commit còn bên kia không.

## Outbox relay: polling hoặc change data capture

Có hai cách phổ biến để chuyển outbox event sang broker:

| Cách | Cơ chế | Phù hợp khi |
|---|---|---|
| Polling publisher | Worker truy vấn các row chưa publish theo batch rồi gửi message. | Muốn triển khai đơn giản, kiểm soát retry và trạng thái bằng database. |
| Change Data Capture (CDC) | Đọc transaction log/WAL/binlog của database và chuyển thay đổi outbox thành message. | Lưu lượng lớn, muốn giảm polling và có hạ tầng CDC như Debezium. |

### Polling publisher

Relay có thể chạy theo lịch hoặc worker liên tục. Với nhiều instance, cần cơ chế claim để tránh mọi instance cùng gửi một row. Có thể dùng row lock với FOR UPDATE SKIP LOCKED, hoặc cập nhật lease/claim token bằng một thao tác atomic.

Luồng xử lý:

1. Mở transaction ngắn để claim một batch event đến hạn.
2. Ghi locked_until, claim token và trạng thái IN_FLIGHT; commit transaction claim.
3. Gửi từng message đến broker ngoài transaction database.
4. Chỉ sau khi broker ACK, cập nhật row thành PUBLISHED và lưu published_at.
5. Nếu gửi thất bại hoặc timeout, tăng attempts, tính next_attempt_at và giải phóng/để hết lease.

Pseudocode:

~~~java
public void publishBatch() {
    List<OutboxEvent> batch = outboxService.claimBatch(100);

    for (OutboxEvent event : batch) {
        try {
            brokerPublisher.publish(
                    event.eventType(),
                    event.aggregateId(),
                    event.eventId().toString(),
                    event.payload()
            );
            outboxService.markPublished(event.eventId());
        }
        catch (TransientBrokerException ex) {
            outboxService.scheduleRetry(event.eventId(), ex);
        }
        catch (RuntimeException ex) {
            outboxService.markFailedOrDeadLetter(event.eventId(), ex);
        }
    }
}
~~~

Đây là pseudocode: claimBatch, markPublished và scheduleRetry nên là các transaction service riêng, không giữ một transaction database mở trong khi đợi broker ACK.

### Cửa sổ tạo duplicate của relay

Giả sử broker đã nhận message nhưng relay chết trước khi cập nhật PUBLISHED. Khi khởi động lại, relay sẽ gửi message đó lần nữa. Nếu relay đánh dấu PUBLISHED trước khi gửi, một crash sau khi cập nhật nhưng trước khi publish sẽ làm mất message.

Vì vậy, outbox relay thường ưu tiên không làm mất event và chấp nhận giao ít nhất một lần (at-least-once). Consumer phải idempotent. Không thể kết luận toàn bộ hệ thống có exactly-once effect chỉ vì broker hoặc producer có tính năng exactly-once.

### Change data capture

Với CDC, connector đọc transaction log của database và phát những row outbox đã commit. Cách này tránh phải polling liên tục và có thể tận dụng ordering của log. Tuy nhiên, cần quản lý offset, retention log, schema history, snapshot, connector restart và xử lý lại message.

CDC vẫn có thể tạo lại message khi connector phục hồi hoặc offset được reset. Consumer vẫn cần deduplication bằng event ID.

## Retry, dead letter và thứ tự event

Không retry mọi lỗi theo cùng một cách:

- Lỗi mạng, broker tạm unavailable hoặc throttling: retry với exponential backoff và jitter.
- Payload sai schema hoặc thiếu dữ liệu bắt buộc: đánh dấu lỗi cần xử lý; retry vô hạn không sửa được payload.
- Lỗi quyền hoặc cấu hình: đưa vào trạng thái cần vận hành can thiệp.
- Hết số lần retry: chuyển dead-letter/quarantine, giữ payload và nguyên nhân để điều tra, không xóa event.

Giữ lại event_id, aggregate_id, aggregate_version, correlation ID, attempt count và error category. Tránh log payload nhạy cảm hoặc thông tin xác thực.

### Ordering

Đa số nghiệp vụ chỉ cần thứ tự trong cùng một aggregate, không cần thứ tự toàn hệ thống. Dùng aggregate_id làm message key/partition key và tăng aggregate_version cho mỗi thay đổi. Consumer có thể từ chối hoặc trì hoãn event có version nhảy cóc.

Khi polling nhiều relay instance, phải bảo đảm hai event của cùng aggregate không bị publish đảo thứ tự nếu thứ tự đó có ý nghĩa. Có thể claim theo aggregate, chỉ cho một event chưa hoàn tất trên mỗi aggregate hoặc dùng sequence gate. Không giữ một global lock chỉ để ép toàn bộ hệ thống tuần tự.

## Consumer phải idempotent

Message broker có thể giao lại message. Consumer có thể xử lý thành công rồi chết trước khi ACK; broker sẽ giao lại. Vì vậy, consumer cần ghi nhận event đã xử lý trong cùng transaction với thay đổi nghiệp vụ.

Ví dụ bảng deduplication:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(120) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer xử lý:

~~~java
@Service
class InventoryEventHandler {

    private final ProcessedEventRepository processedEventRepository;
    private final InventoryRepository inventoryRepository;

    @Transactional
    public void onOrderPlaced(OrderPlaced event) {
        boolean firstDelivery = processedEventRepository.insertIfAbsent(
                "inventory-order-placed",
                UUID.fromString(event.eventId())
        );

        if (!firstDelivery) {
            return;
        }

        inventoryRepository.reserve(
                event.orderId(),
                event.lines()
        );
    }
}
~~~

insertIfAbsent cần dùng unique constraint/atomic insert. Nếu event đã được ghi nhận, consumer không thực hiện side effect lần nữa. Nếu reserve thất bại và exception làm transaction rollback, cả bản ghi processed_event cũng rollback; message có thể được retry.

Nếu consumer cập nhật database rồi lại cần phát event tiếp theo, consumer nên ghi outbox của chính nó trong cùng transaction. Mỗi service dùng outbox ở ranh giới publish và idempotency ở ranh giới consume.

## Spring Modulith và Event Publication Registry

Trong một ứng dụng Spring Modulith, có thể dùng application event để tách module nghiệp vụ. @ApplicationModuleListener là listener bất đồng bộ và transactional; Event Publication Registry lưu publication entry trong cùng transaction phát event, sau đó theo dõi việc listener hoàn tất. Nếu listener thất bại, entry chưa hoàn tất có thể được resubmit theo chính sách phục hồi.

Ví dụ:

~~~java
public record OrderPlaced(String orderId, String customerId) {
}

@Service
class OrderManagement {

    private final ApplicationEventPublisher events;
    private final OrderRepository orders;

    OrderManagement(
            ApplicationEventPublisher events,
            OrderRepository orders) {
        this.events = events;
        this.orders = orders;
    }

    @Transactional
    public void placeOrder(Order order) {
        orders.save(order);
        events.publishEvent(new OrderPlaced(
                order.getId(),
                order.getCustomerId()
        ));
    }
}

@Component
class InventoryManagement {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        // Xử lý event trong transaction riêng của listener.
    }
}
~~~

Event Publication Registry giúp không mất publication khi ứng dụng/listener lỗi và cung cấp API để xem/resubmit publication chưa hoàn tất. Đây là cơ chế phù hợp cho event listener trong ứng dụng Spring Modulith. Khi cần externalize event tới broker, hãy cấu hình broker integration và chế độ externalization phù hợp với phiên bản Spring Modulith đang dùng; không coi một @Async @TransactionalEventListener đơn thuần là outbox bền vững.

Listener vẫn nên idempotent. Một listener có thể thực hiện side effect rồi process chết trước khi registry ghi nhận completion; lần resubmit tiếp theo có thể chạy lại listener.

## Saga: điều phối local transaction qua nhiều service

Outbox bảo đảm message phát ra tương ứng với thay đổi đã commit. Nhưng outbox không tự quyết định quy trình phải đi tiếp hay bù trừ. Khi một nghiệp vụ trải qua nhiều database/service, dùng Saga.

Một saga là chuỗi local transaction. Mỗi participant commit dữ liệu trong database của mình và phát event/response để kích hoạt bước kế tiếp. Khi một bước không thể tiếp tục, saga có thể:

- **Forward recovery:** retry hoặc tiếp tục khi lỗi chỉ là tạm thời.
- **Compensation:** chạy một thao tác nghiệp vụ mới để cân bằng những bước đã commit trước đó.

Ví dụ:

| Bước | Local transaction | Event/command tiếp theo |
|---|---|---|
| 1. Order | Tạo order PENDING. | OrderPlaced |
| 2. Inventory | Giữ tồn kho. | InventoryReserved hoặc InventoryRejected |
| 3. Payment | Thu tiền. | PaymentCaptured hoặc PaymentRejected |
| 4. Shipping | Tạo vận đơn. | ShipmentCreated |
| 5. Order | Đánh dấu CONFIRMED. | OrderConfirmed |

Nếu Payment bị từ chối sau khi Inventory đã giữ hàng, saga phát lệnh ReleaseInventory. Nếu Shipping thất bại sau khi Payment đã capture, quy trình có thể thử lại Shipping hoặc yêu cầu refund và giải phóng tồn kho theo policy.

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> INVENTORY_RESERVED: InventoryReserved
    PENDING --> REJECTED: InventoryRejected
    INVENTORY_RESERVED --> PAYMENT_CAPTURED: PaymentCaptured
    INVENTORY_RESERVED --> COMPENSATING: PaymentRejected
    PAYMENT_CAPTURED --> SHIPPING_CREATED: ShipmentCreated
    PAYMENT_CAPTURED --> COMPENSATING: Shipping permanently failed
    SHIPPING_CREATED --> COMPLETED
    COMPENSATING --> REFUNDING: RefundPayment
    REFUNDING --> RELEASING_INVENTORY: PaymentRefunded
    RELEASING_INVENTORY --> CANCELLED: InventoryReleased
    COMPENSATING --> MANUAL_REVIEW: Compensation failed
    COMPLETED --> [*]
    CANCELLED --> [*]
    REJECTED --> [*]
    MANUAL_REVIEW --> [*]
~~~

## Compensation không phải rollback

Rollback database quay lại trạng thái trước commit trong cùng transaction. Compensation là một transaction mới có mục đích nghiệp vụ đảo ngược hoặc cân bằng tác động đã commit. Nó có thể không khôi phục được trạng thái lịch sử chính xác.

| Tác động đã commit | Compensation có thể có | Giới hạn |
|---|---|---|
| Reserve tồn kho | Release reservation. | Có thể thất bại nếu reservation đã hết hạn hoặc đã được xuất kho. |
| Capture payment | Refund hoặc void payment. | Refund là giao dịch mới, có thể chậm hoặc bị từ chối. |
| Tạo booking | Cancel booking. | Có thể có phí hủy hoặc không còn được phép hủy. |
| Gửi email | Gửi email đính chính. | Không thể thu hồi email đã gửi khỏi hộp thư người nhận. |
| Cấp quyền truy cập | Thu hồi quyền. | Tài nguyên có thể đã được truy cập trong khoảng thời gian quyền còn hiệu lực. |

Mỗi compensation cần:

- Có ID riêng và idempotency key.
- Kiểm tra trạng thái hiện tại trước khi đảo ngược.
- Lưu kết quả và thời điểm thực hiện.
- Có retry/backoff cho lỗi tạm thời.
- Có trạng thái COMPENSATION_FAILED và đường xử lý thủ công.
- Không chạy nếu bước gốc chưa commit hoặc đã được bù trừ.

Không thiết kế compensation chỉ bằng cách gán lại một field cũ. Ví dụ, cộng tồn kho trở lại phải dựa trên reservation ID và trạng thái xuất kho; refund phải dùng payment reference và số tiền có thể hoàn.

## Chọn choreography hay orchestration

Có hai cách phối hợp saga:

| Tiêu chí | Choreography | Orchestration |
|---|---|---|
| Cách điều khiển | Service phát domain event; service khác lắng nghe và thực hiện bước của mình. | Một saga orchestrator gửi command và nhận kết quả từ participant. |
| Luồng nghiệp vụ | Phân tán qua event handler. | Được mô tả rõ trong state machine/workflow. |
| Phù hợp | Ít participant, luồng ngắn, các bước tương đối độc lập. | Nhiều participant, nhiều nhánh lỗi, timeout và compensation phức tạp. |
| Ưu điểm | Ít thành phần điều phối trung tâm, participant ít phụ thuộc trực tiếp. | Dễ nhìn toàn bộ trạng thái, retry, deadline và nhánh compensation. |
| Chi phí | Luồng event có thể khó lần theo và dễ tạo vòng phụ thuộc. | Cần lưu trạng thái orchestrator và bảo vệ nó khỏi lỗi/duplicate. |

Không có lựa chọn nào tự cung cấp atomic transaction toàn hệ thống. Mỗi participant vẫn cần local transaction, outbox khi phát event và idempotent consumer khi nhận message.

## Lưu trạng thái saga và correlation

Với workflow dài, lưu trạng thái saga bền vững thay vì giữ toàn bộ tiến trình trong memory:

| Trường | Mục đích |
|---|---|
| saga_id | Định danh workflow duy nhất. |
| business_key | ID đơn hàng hoặc nghiệp vụ gốc. |
| status | Trạng thái tổng thể như RUNNING, COMPENSATING, COMPLETED, FAILED. |
| current_step | Bước đang chờ hoặc đang thực hiện. |
| version | Optimistic locking khi nhiều event cùng cập nhật saga. |
| started_at, updated_at, deadline_at | Theo dõi thời gian và timeout. |
| last_error_code | Lỗi đã lọc để điều phối/review. |
| correlation_id | Ghép log, trace và message của toàn workflow. |

Mỗi bước cũng nên có operation ID, attempt count, trạng thái, idempotency key và kết quả. Event phải mang saga_id hoặc correlation ID để participant biết nó thuộc workflow nào.

### Xử lý message trùng, sai thứ tự và đến muộn

- Dùng event_id để deduplicate message.
- Dùng saga_id và step_id để deduplicate lệnh thực hiện từng bước.
- Dùng aggregate version hoặc expected state để từ chối event đến sai thứ tự.
- Nếu event đến sau khi saga đã terminal, xác định đó là duplicate, late success cần compensation hay sự kiện không còn hợp lệ.
- Không áp dụng một event chỉ dựa vào tên; phải kiểm tra trạng thái saga hiện tại.

Saga không cung cấp isolation như một transaction ACID duy nhất. Trong lúc saga đang chạy, các request khác có thể nhìn thấy trạng thái trung gian. Dùng semantic lock, reservation, optimistic version hoặc trạng thái PENDING để ngăn thao tác xung đột.

## Retry và phân biệt lỗi kỹ thuật với lỗi nghiệp vụ

Không phải mọi thất bại đều cần compensation:

| Loại lỗi | Cách xử lý thường dùng |
|---|---|
| Timeout mạng, broker unavailable, HTTP 503 | Retry với backoff và giới hạn attempt. |
| Consumer crash sau commit nhưng trước ACK | Broker giao lại; deduplication bảo vệ side effect. |
| Business rule từ chối, ví dụ không đủ tồn kho | Không retry vô hạn; chuyển sang nhánh reject/compensation. |
| Payload/schema không tương thích | Quarantine/DLQ và xử lý phiên bản; không retry mù quáng. |
| Provider timeout không rõ đã capture hay chưa | Query trạng thái bằng operation ID trước khi retry. |
| Compensation thất bại | Retry theo policy hoặc chuyển manual review. |

Mỗi retry cần idempotency key ổn định. Không tạo key mới cho cùng một logical operation khi message được giao lại, nếu không consumer có thể thực hiện side effect lần nữa.

## Kết hợp outbox và saga trong Spring AI Tool Calling

Mô hình nên yêu cầu một tool bắt đầu use case nghiệp vụ. Application service tạo saga, ghi trạng thái ban đầu và outbox command/event trong cùng transaction. Các service phía sau tiếp tục saga bất đồng bộ.

Không nên để mô hình tự gọi lần lượt reserveInventory, capturePayment, createShipment như ba tool độc lập nếu nghiệp vụ yêu cầu phối hợp và bù trừ. Mô hình có thể dừng giữa các lần gọi, gọi sai thứ tự hoặc lặp lại một bước sau khi không nhận được kết quả.

### Tool chỉ khởi tạo workflow

~~~java
public record StartOrderResult(
        String orderId,
        String sagaId,
        String status,
        String statusUrl) {
}

@Component
class OrderWorkflowTools {

    private final OrderWorkflowService workflowService;

    OrderWorkflowTools(OrderWorkflowService workflowService) {
        this.workflowService = workflowService;
    }

    @Tool(description = "Bắt đầu quy trình đặt hàng và trả về mã theo dõi")
    public StartOrderResult placeOrder(
            String cartId,
            ToolContext toolContext) {

        String tenantId = trustedContextValue(toolContext, "tenantId");
        String actorId = trustedContextValue(toolContext, "actorId");

        return workflowService.start(cartId, tenantId, actorId);
    }

    @Tool(description = "Tra cứu trạng thái quy trình đặt hàng theo mã saga")
    public OrderWorkflowStatus getOrderWorkflowStatus(
            String sagaId,
            ToolContext toolContext) {

        String tenantId = trustedContextValue(toolContext, "tenantId");
        return workflowService.status(sagaId, tenantId);
    }
}
~~~

Service start thực hiện một transaction local:

~~~java
@Transactional
public StartOrderResult start(
        String cartId,
        String tenantId,
        String actorId) {

    Order order = orderService.createPending(cartId, tenantId, actorId);
    OrderSaga saga = sagaRepository.create(order.getId(), tenantId);

    outboxRepository.save(OutboxEvent.forCommand(
            UUID.randomUUID(),
            saga.getId(),
            "ReserveInventory",
            new ReserveInventoryCommand(saga.getId(), order.getId())
    ));

    return new StartOrderResult(
            order.getId(),
            saga.getId(),
            "RUNNING",
            "/orders/workflows/" + saga.getId()
    );
}
~~~

Đây là ví dụ kiến trúc; các service, repository và event type là thành phần ứng dụng. Outbox relay gửi command sau khi transaction commit. Orchestrator cập nhật saga state khi nhận kết quả từ participant.

### Trả kết quả trung thực cho mô hình

Khi tool trả RUNNING, mô hình chỉ nên thông báo quy trình đã được tiếp nhận và cung cấp mã theo dõi. Không nói đơn hàng đã xác nhận hoặc thanh toán thành công khi saga chưa đạt trạng thái COMPLETED.

Có thể cung cấp tool đọc getOrderWorkflowStatus(sagaId) để mô hình trả lời khi người dùng hỏi tiến độ. Tool này phải kiểm tra tenant/user từ ToolContext; không cho mô hình tự cung cấp tenant ID hoặc truy cập saga của người khác.

Với thao tác nhạy cảm như capture payment hoặc hủy đơn, dùng cơ chế xác nhận của ứng dụng/Spring AI trước khi bắt đầu side effect. Model chỉ đề xuất thao tác; authorization, confirmation, idempotency và saga state vẫn do ứng dụng kiểm soát.

## Kiểm thử outbox và saga

Nên kiểm thử từng ranh giới lỗi, đặc biệt là các điểm process có thể chết sau khi một bên đã thành công.

| Tình huống | Kết quả cần xác minh |
|---|---|
| DB transaction rollback | Không có business row hoặc outbox event tương ứng. |
| DB commit thành công, relay chưa chạy | Outbox row còn pending và được gửi sau. |
| Broker ACK, relay chết trước mark published | Message có thể gửi lại; consumer chỉ áp dụng side effect một lần. |
| Broker unavailable | Event được retry với backoff; không mất row. |
| Nhiều relay instance | Claim/lease không làm mất event; thứ tự theo aggregate được bảo toàn khi cần. |
| Consumer nhận cùng event hai lần | Processed-event unique key chặn side effect trùng. |
| Consumer commit nhưng ACK thất bại | Redelivery không làm cập nhật nghiệp vụ lần nữa. |
| Event đến sai thứ tự | Version/state guard từ chối hoặc trì hoãn event. |
| Payment thất bại vì business rule | Saga chạy nhánh compensation phù hợp. |
| Payment timeout không rõ kết quả | Query provider theo operation ID trước khi retry. |
| Compensation thất bại | Saga ở COMPENSATION_FAILED/manual review và có thể tiếp tục sau. |
| Duplicate command từ model/tool retry | Idempotency key trả lại saga/operation cũ. |
| Server restart giữa saga | Saga state, outbox và step log khôi phục được. |
| Event schema version cũ | Consumer tương thích hoặc quarantine có lý do. |
| Hai saga cùng cập nhật một resource | Reservation, version hoặc semantic lock bảo vệ invariant. |

Với test tích hợp, dùng database và broker test thật hoặc container phù hợp. Tạo fault injection tại các điểm sau: sau DB commit, sau broker ACK, sau consumer DB commit và trước ACK. Không chỉ mock happy path vì phần khó của outbox/saga nằm ở crash window và redelivery.

## Bài tập thực hành

Xây dựng quy trình đặt hàng có tồn kho, thanh toán và vận chuyển:

1. Order Service tạo order PENDING và OrderPlaced outbox event trong một transaction.
2. Relay gửi event đến broker; mô phỏng broker unavailable và process crash sau ACK.
3. Inventory Service consume event idempotently, reserve stock và ghi InventoryReserved outbox event.
4. Payment Service capture payment bằng provider idempotency key và phát PaymentCaptured hoặc PaymentRejected.
5. Orchestrator lưu trạng thái saga và quyết định tạo shipment hoặc compensation.
6. Nếu payment bị từ chối, release inventory và chuyển order sang CANCELLED.
7. Nếu shipment thất bại tạm thời, retry forward; nếu thất bại vĩnh viễn sau payment capture, thực hiện refund rồi release inventory.
8. Kiểm thử duplicate event, out-of-order event, timeout không rõ kết quả và compensation thất bại.
9. Tạo một @Tool bắt đầu saga và một tool đọc trạng thái; cả hai dùng tenant/user từ ToolContext.
10. Xác minh câu trả lời model không tuyên bố hoàn tất khi saga còn RUNNING hoặc COMPENSATION_PENDING.

Bạn hoàn thành khi có thể giải thích event nào được ghi cùng business transaction, ai relay event, consumer deduplicate bằng gì, saga chuyển trạng thái ra sao khi một bước thất bại và compensation nào cần chạy.

## Danh sách kiểm tra trước khi triển khai

- [ ] Xác định rõ thao tác nào nằm trong local transaction của từng service.
- [ ] Ghi business state và outbox event trong cùng transaction.
- [ ] Relay chỉ đánh dấu published sau broker ACK.
- [ ] Chấp nhận at-least-once delivery và thiết kế consumer idempotent.
- [ ] Có event ID, aggregate ID, sequence/version, schema version và correlation ID.
- [ ] Có lease/claim để nhiều relay instance không xử lý cùng row ngoài ý muốn.
- [ ] Có retry/backoff, dead letter/quarantine và công cụ resubmit.
- [ ] Bảo toàn thứ tự theo aggregate khi nghiệp vụ yêu cầu.
- [ ] Consumer ghi deduplication marker cùng transaction với business update.
- [ ] Consumer phát event tiếp theo bằng outbox của chính service.
- [ ] Saga lưu trạng thái và step log bền vững.
- [ ] Chọn choreography hoặc orchestration dựa trên số bước và độ phức tạp của nhánh lỗi.
- [ ] Phân biệt lỗi tạm thời cần forward recovery với lỗi nghiệp vụ cần compensation.
- [ ] Compensation có idempotency, kiểm tra trạng thái và đường xử lý thất bại.
- [ ] Có semantic lock/version/reservation để xử lý concurrent saga.
- [ ] Tool của Spring AI khởi tạo hoặc tra cứu workflow; application service/orchestrator sở hữu trình tự nghiệp vụ.
- [ ] ToolContext cung cấp tenant/user đáng tin cậy; authorization được kiểm tra ở service.
- [ ] Model chỉ thông báo trạng thái saga đã được xác minh.
- [ ] Có fault-injection test cho các crash window, duplicate, ordering và compensation.

Transactional outbox bảo đảm thay đổi dữ liệu và ý định phát event được commit cùng nhau trong một service. Saga phối hợp các local transaction qua nhiều service và dùng forward recovery hoặc compensation để đạt trạng thái nghiệp vụ mong muốn. Khi kết hợp hai pattern, mỗi bước có thể được retry và phục hồi sau crash mà không giả định tồn tại một transaction ACID bao trùm toàn hệ thống.

## Tài liệu tham khảo

- [Spring Modulith – Working with Application Events và Event Publication Registry](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith – Event Publication Registry API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/EventPublicationRegistry.html)
- [AWS Prescriptive Guidance – Transactional Outbox Pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
- [microservices.io – Saga Pattern](https://microservices.io/patterns/data/saga.html)
- [AWS Prescriptive Guidance – Saga Patterns](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga-patterns.html)
- [Spring AI 2.1.0 – Tool Calling and Tool Call Confirmation](https://docs.spring.io/spring-ai/reference/api/tools.html)
