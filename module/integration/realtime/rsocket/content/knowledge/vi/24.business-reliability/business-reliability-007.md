# Ranh giới nhất quán khi một luồng dữ liệu đi qua nhiều dịch vụ

Một luồng nghiệp vụ thường đi qua nhiều dịch vụ: Order nhận yêu cầu tạo đơn, Inventory giữ hàng, Payment xác nhận thanh toán, rồi Order chuyển đơn sang trạng thái đã xác nhận. Mỗi dịch vụ có cơ sở dữ liệu, tiến trình và vòng đời triển khai riêng. Một transaction cơ sở dữ liệu trong Order không thể tự động bao trùm thao tác ghi dữ liệu trong Inventory và Payment chỉ vì các lời gọi được gửi qua RSocket.

Vì vậy, cần xác định rõ **ranh giới nhất quán**: dữ liệu nào phải thay đổi nguyên tử trong một dịch vụ, bước nào được phép hoàn tất sau, cách biểu diễn trạng thái trung gian, và cách phục hồi khi một dịch vụ lỗi hoặc phản hồi bị mất. RSocket cung cấp các mô hình giao tiếp bất đồng bộ và hai chiều; nó không tự tạo distributed transaction hoặc bảo đảm một chuỗi nghiệp vụ nhiều dịch vụ chỉ chạy đúng một lần.

Bài học này dùng luồng đặt hàng để phân tích transaction cục bộ, eventual consistency, transactional outbox/inbox, saga, idempotency, retry, timeout và thứ tự sự kiện. Mục tiêu là thiết kế một quy trình có thể tiếp tục hoặc bù trừ khi một bước thất bại, thay vì phụ thuộc vào giả định mọi dịch vụ luôn phản hồi thành công.

Sau bài học, bạn có thể:

- Xác định ranh giới transaction và quyền sở hữu dữ liệu của từng dịch vụ.
- Phân biệt consistency trong một dịch vụ với consistency của quy trình liên dịch vụ.
- Thiết kế trạng thái trung gian và eventual consistency cho workflow.
- Dùng transactional outbox để ghi thay đổi nghiệp vụ và sự kiện trong cùng transaction.
- Dùng inbox/idempotency key để xử lý thông điệp gửi lại an toàn.
- Thiết kế saga theo choreography hoặc orchestration và các hành động bù trừ.
- Phân tích timeout, retry, duplicate, message ordering và kết quả không xác định.
- Chọn interaction RSocket phù hợp với yêu cầu xác nhận và độ tin cậy.
- Kiểm thử lỗi từng bước để xác nhận workflow có thể phục hồi.

## 1. Một luồng nghiệp vụ đi qua nhiều ranh giới dữ liệu

Xét quy trình tạo đơn hàng:

1. Order nhận yêu cầu và tạo đơn.
2. Inventory giữ số lượng sản phẩm.
3. Payment xác thực hoặc giữ khoản thanh toán.
4. Order xác nhận đơn khi các bước cần thiết hoàn tất.
5. Nếu một bước thất bại, hệ thống hủy hoặc bù trừ các bước đã thành công.

~~~mermaid
flowchart LR
    C[Client] --> O[Order Service]
    O -->|Reserve stock| I[Inventory Service]
    I -->|Reservation result| O
    O -->|Authorize payment| P[Payment Service]
    P -->|Payment result| O
    O -->|Confirm order| C
~~~

Mỗi dịch vụ sở hữu dữ liệu riêng:

| Dịch vụ | Dữ liệu sở hữu | Invariant cục bộ ví dụ |
|---|---|---|
| Order | Đơn hàng, trạng thái workflow | Một orderId chỉ có một đơn; tổng tiền khớp chi tiết đơn |
| Inventory | Tồn kho, reservation | Không giữ vượt quá số lượng khả dụng |
| Payment | Payment intent, authorization | Một idempotency key không tạo nhiều khoản charge |
| Shipping | Shipment và trạng thái giao | Một shipment chỉ gắn với đơn hợp lệ |

Một dịch vụ có thể dùng transaction cục bộ để bảo vệ invariant của dữ liệu do chính nó sở hữu. Ví dụ Inventory cập nhật số lượng khả dụng và tạo reservation trong cùng transaction. Order không thể mở transaction JPA rồi kỳ vọng transaction đó tự bao gồm thao tác ghi ở Inventory và Payment qua RSocket.

Điều cần thiết kế là một quy trình nghiệp vụ gồm nhiều transaction cục bộ. Mỗi bước commit độc lập và phát tín hiệu để bước tiếp theo tiếp tục.

## 2. Ranh giới nhất quán nằm ở đâu?

Có thể chia hệ thống thành hai loại invariant:

**Invariant cục bộ** cần đúng ngay trong một transaction của dịch vụ sở hữu dữ liệu. Ví dụ một reservation không được làm tồn kho âm. Dịch vụ phải kiểm tra và cập nhật bằng transaction, khóa phù hợp hoặc câu lệnh cập nhật có điều kiện.

**Invariant liên dịch vụ** mô tả kết quả cuối của một workflow. Ví dụ một đơn chỉ được xác nhận khi tồn kho đã được giữ và thanh toán đã được authorize. Quy trình này có thể đi qua nhiều transaction và có trạng thái trung gian như PENDING, STOCK_RESERVED hoặc PAYMENT_PENDING.

~~~mermaid
flowchart TD
    A[Order request] --> B[Order DB transaction]
    B --> C[Order=PENDING + Outbox event]
    C --> D[Inventory local transaction]
    D --> E[Reservation=HELD]
    E --> F[Payment local transaction]
    F --> G[Payment=AUTHORIZED]
    G --> H[Order local transaction]
    H --> I[Order=CONFIRMED]
    D -->|Failure| J[Compensation or reject]
    F -->|Failure| K[Release reservation]
~~~

Không nên cố làm cho mọi bảng ở mọi dịch vụ thay đổi cùng một thời điểm. Hãy định nghĩa:

- Trạng thái nào là trạng thái hợp lệ trong lúc workflow đang chạy.
- Dịch vụ nào có quyền quyết định chuyển trạng thái.
- Sự kiện nào chứng minh một bước đã commit.
- Thời hạn tối đa cho từng bước.
- Hành động bù trừ nếu bước tiếp theo không thể hoàn tất.
- Cách client quan sát trạng thái đang chờ hoặc đã thất bại.

Một đơn PENDING không nhất thiết là dữ liệu sai. Nó là trạng thái nghiệp vụ hợp lệ nếu API và giao diện công bố rõ rằng quá trình xác nhận chưa hoàn tất.

## 3. Vì sao không giữ transaction mở qua RSocket call?

Một cách dễ nghĩ tới là mở transaction ở Order, gọi Inventory và Payment, rồi commit Order nếu tất cả trả thành công. Cách này kéo dài transaction trong lúc chờ network và vẫn không tạo atomic commit giữa các cơ sở dữ liệu.

Ví dụ luồng không nên dùng làm ranh giới nhất quán:

~~~java
@Transactional
public Order confirmOrder(CreateOrder command) {
    Order order = orderRepository.save(Order.pending(command));

    inventoryClient.reserve(command.items()).block();
    paymentClient.authorize(command.payment()).block();

    order.confirm();
    return order;
}
~~~

Có một số vấn đề:

- Transaction Order giữ connection, lock hoặc snapshot trong suốt thời gian gọi mạng.
- Inventory có thể commit thành công nhưng response bị mất.
- Payment có thể commit trước khi Order rollback.
- Order rollback không tự hoàn tác reservation hoặc payment.
- Gọi block trong luồng reactive có thể chiếm thread và làm giảm khả năng phục vụ.
- Retry toàn bộ method có thể lặp lại thao tác đã thành công ở dịch vụ khác.

Ngay cả khi các lời gọi dùng request-response và đều trả thành công, chúng vẫn là các transaction độc lập. RSocket request-response không phải giao thức two-phase commit.

### Chia thành các bước commit ngắn

Order nên commit trạng thái ban đầu và ý định phát sự kiện trong một transaction cục bộ. Một worker gửi sự kiện sau commit. Inventory xử lý bằng transaction của nó và trả hoặc phát kết quả; Order tiếp tục workflow khi nhận kết quả.

~~~java
@Transactional
public Order createOrder(CreateOrder command) {
    Order order = orderRepository.save(
        Order.pending(command)
    );

    outboxRepository.save(
        OutboxEvent.orderCreated(order)
    );

    return order;
}
~~~

Order và outbox event được ghi cùng database transaction. Nếu transaction rollback, cả hai thay đổi đều rollback. Nếu commit, worker có thể gửi event sau đó, kể cả khi tiến trình khởi động lại.

## 4. Eventual consistency và trạng thái trung gian

Eventual consistency có nghĩa các bản ghi hoặc projection ở các dịch vụ có thể tạm thời chưa phản ánh cùng một trạng thái, nhưng workflow có cơ chế để tiến tới trạng thái cuối khi các bước được xử lý thành công.

Ví dụ:

| Thời điểm | Order | Inventory | Payment |
|---|---|---|---|
| T0 | PENDING | Chưa giữ hàng | Chưa authorize |
| T1 | PENDING | HELD | Chưa authorize |
| T2 | PENDING | HELD | AUTHORIZED |
| T3 | CONFIRMED | HELD | AUTHORIZED |

Trong khoảng T1 đến T2, Order chưa CONFIRMED dù Inventory đã giữ hàng. Đây là trạng thái trung gian có chủ đích.

Nếu Payment từ chối:

| Dịch vụ | Hành động |
|---|---|
| Payment | Ghi nhận DECLINED |
| Order | Chuyển sang PAYMENT_FAILED hoặc CANCELLING |
| Inventory | Nhận lệnh RELEASE_RESERVATION |
| Order | Chuyển sang REJECTED/CANCELLED khi bù trừ hoàn tất |

Client cần biết cách đọc trạng thái. Có thể trả về orderId cùng trạng thái PENDING, sau đó client subscribe một route RSocket request-stream để nhận cập nhật, hoặc truy vấn lại trạng thái bằng request-response.

Không trả về CONFIRMED ngay khi mới ghi đơn PENDING. Hợp đồng API phải phản ánh đúng mức độ hoàn tất thực tế.

## 5. Transactional Outbox: ghi dữ liệu và sự kiện cùng transaction

Một lỗi thường gặp là ghi đơn hàng vào database rồi publish event bằng một lệnh riêng:

~~~java
@Transactional
public Order create(CreateOrder command) {
    Order order = orderRepository.save(Order.pending(command));

    eventPublisher.publish(
        new OrderCreated(order.id())
    );

    return order;
}
~~~

Nếu database commit nhưng publish thất bại, đơn hàng tồn tại mà không có event để Inventory xử lý. Nếu publish thành công nhưng database rollback, Inventory có thể nhận event của một đơn không tồn tại.

Transactional Outbox giải quyết khoảng trống này bằng cách ghi event vào bảng outbox trong cùng transaction với dữ liệu nghiệp vụ.

~~~mermaid
flowchart TD
    A[Create order] --> B[Single local DB transaction]
    B --> C[Save Order]
    B --> D[Insert OutboxEvent]
    C --> E[Commit]
    D --> E
    E --> F[Outbox relay]
    F --> G[RSocket or message broker]
    G --> H[Consumer service]
~~~

Ví dụ bảng outbox:

~~~sql
CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    sequence_no BIGINT NOT NULL,
    payload JSON NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL,
    attempts INTEGER NOT NULL DEFAULT 0
);
~~~

Trong cùng transaction:

~~~java
@Transactional
public Order createOrder(CreateOrder command) {
    Order order = orderRepository.save(
        Order.pending(command)
    );

    outboxRepository.insert(
        OutboxEvent.create(
            UUID.randomUUID(),
            "Order",
            order.id(),
            "OrderCreated",
            order.version(),
            serialize(new OrderCreated(order.id(), order.items()))
        )
    );

    return order;
}
~~~

Một relay đọc các hàng chưa publish, gửi chúng tới consumer, rồi đánh dấu đã gửi sau khi nhận xác nhận phù hợp. Nếu relay crash sau khi consumer đã xử lý nhưng trước khi cập nhật published_at, event sẽ được gửi lại. Đây là hành vi bình thường của delivery at-least-once; consumer phải idempotent.

### Vì sao không đánh dấu trước khi gửi?

Nếu relay đánh dấu event đã publish rồi mới gửi, crash ở giữa sẽ làm mất event vĩnh viễn. Gửi trước rồi đánh dấu sau có thể tạo duplicate nhưng không mất event do khoảng trống đó. Duplicate có thể được xử lý bằng inbox/idempotency.

Nếu dùng nhiều relay, cần claim hàng outbox an toàn để tránh nhiều worker cùng gửi một event. Có thể dùng trạng thái CLAIMED với lease timeout, row locking hoặc cơ chế claim phù hợp database. Không giữ transaction database mở trong suốt network call; claim trong transaction ngắn, gửi bên ngoài transaction, rồi cập nhật trạng thái.

## 6. Inbox và idempotent consumer

Khi relay gửi lại event, consumer có thể nhận cùng event nhiều lần. Consumer cần nhận diện event đã xử lý để không lặp lại side effect.

Một inbox table lưu event ID đã được tiếp nhận:

~~~sql
CREATE TABLE inbox_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    received_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer xử lý trong một local transaction:

~~~java
@Transactional
public ProcessingResult handle(OrderCreated event) {
    boolean firstDelivery = inboxRepository.insertIfAbsent(
        "inventory",
        event.eventId()
    );

    if (!firstDelivery) {
        return ProcessingResult.duplicate();
    }

    inventoryService.reserve(
        event.orderId(),
        event.items()
    );

    return ProcessingResult.accepted();
}
~~~

insertIfAbsent cần dựa vào unique constraint để bảo vệ khi hai bản sao đến đồng thời. Không chỉ gọi exists rồi insert, vì hai transaction có thể cùng thấy chưa tồn tại. Nếu insert conflict, consumer coi đó là duplicate theo chính sách.

Việc ghi inbox và cập nhật dữ liệu nghiệp vụ phải nằm trong cùng transaction. Nếu inbox commit nhưng cập nhật tồn kho rollback, lần gửi lại sau đó sẽ bị coi là duplicate và thao tác reserve không được chạy. Nếu cập nhật tồn kho commit nhưng inbox rollback, event có thể bị xử lý lần nữa. Cùng transaction giúp hai thay đổi có cùng kết quả commit/rollback.

Với xử lý bất đồng bộ reactive dùng R2DBC, có thể dùng TransactionalOperator để gắn inbox và side effect vào cùng reactive transaction.

### Idempotency key cho command

Không chỉ event mới cần deduplication. Client có thể retry command tạo đơn khi timeout và vô tình tạo hai đơn. Dùng idempotency key do caller tạo:

~~~java
public record CreateOrderCommand(
    String idempotencyKey,
    List<OrderItem> items,
    PaymentDetails payment
) {}
~~~

Order lưu unique key cùng kết quả xử lý. Khi nhận lại cùng key, trả kết quả đã lưu thay vì tạo order mới.

Idempotency key phải ổn định qua các lần retry của cùng một thao tác. Không tạo UUID mới ở mỗi lần retry, nếu không server sẽ xem đó là command mới.

## 7. RSocket request-response có thể làm acknowledgement không?

RSocket hỗ trợ các interaction khác nhau, mỗi loại có ngữ nghĩa khác nhau:

| Interaction | Có response? | Phù hợp |
|---|---|---|
| REQUEST_RESPONSE | Một response | Command cần xác nhận đã được xử lý/tiếp nhận |
| REQUEST_FNF | Không có response payload | Telemetry hoặc thông báo không cần ACK |
| REQUEST_STREAM | Một request, nhiều response | Theo dõi trạng thái hoặc event stream |
| REQUEST_CHANNEL | Hai luồng payload | Trao đổi dữ liệu hai chiều liên tục |

Với command quan trọng, request-response thường dễ định nghĩa ACK hơn fire-and-forget. Tuy nhiên, ACK chỉ có ý nghĩa nếu server trả sau khi đã commit điều kiện được cam kết.

Ví dụ Inventory nhận lệnh reserve:

~~~java
@MessageMapping("inventory.reserve")
public Mono<ReservationAck> reserve(ReserveCommand command) {
    return reservationService.reserveAndCommit(command)
        .map(reservation ->
            new ReservationAck(
                command.eventId(),
                reservation.id(),
                "HELD"
            )
        );
}
~~~

Nếu service sử dụng reactive transaction, response cần được phát ra sau khi transaction hoàn tất commit. Nếu dùng imperative transaction, gọi service trong boundedElastic và chỉ phát ACK sau khi method transactional trả về:

~~~java
@MessageMapping("inventory.reserve")
public Mono<ReservationAck> reserve(ReserveCommand command) {
    return Mono.fromCallable(() ->
            reservationService.reserveAndCommit(command)
        )
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Ví dụ trên giả định reserveAndCommit là method imperative có transaction cục bộ và trả về sau commit. Với R2DBC, hãy dùng reactive transaction thay vì chuyển sang boundedElastic.

ACK có thể bị mất sau khi server commit. Client khi đó không biết thao tác đã hoàn tất hay chưa. Client phải retry cùng event ID/idempotency key hoặc truy vấn trạng thái; consumer cần idempotent để lần gửi lại không tạo reservation thứ hai.

Fire-and-forget không trả response payload nên requester không thể biết consumer đã commit hay chưa. Không dùng FNF làm bằng chứng một bước nghiệp vụ quan trọng đã hoàn tất.

## 8. Saga: điều phối nhiều transaction cục bộ

Saga là một workflow gồm nhiều transaction cục bộ. Mỗi bước commit ở dịch vụ sở hữu dữ liệu. Nếu bước sau thất bại, saga chạy hành động bù trừ cho các bước trước đó đã thành công.

Ví dụ đặt hàng:

| Bước | Transaction | Hành động bù trừ |
|---|---|---|
| 1 | Order tạo PENDING | Hủy đơn |
| 2 | Inventory giữ hàng | Giải phóng reservation |
| 3 | Payment authorize | Void authorization |
| 4 | Order xác nhận | Nếu đã confirm thì quy trình hủy riêng |

Bù trừ không phải rollback vật lý của transaction cũ. Nó là một hành động nghiệp vụ mới, có thể thất bại và cần retry. Ví dụ nếu hàng đã được đóng gói, không thể đơn giản "rollback" thao tác đóng gói; cần một quy trình hủy shipment hoặc trả hàng.

Một saga cần lưu trạng thái bền vững:

~~~java
public enum OrderSagaState {
    STARTED,
    STOCK_RESERVED,
    PAYMENT_AUTHORIZED,
    COMPLETED,
    COMPENSATING,
    COMPENSATED,
    FAILED
}
~~~

Không chỉ giữ state trong memory của một controller. Nếu process restart, workflow phải tiếp tục từ trạng thái đã commit.

## 9. Choreography và orchestration

Có hai cách phổ biến để điều phối saga.

### Choreography: dịch vụ phản ứng với event

Mỗi dịch vụ phát event sau khi hoàn thành transaction của nó. Dịch vụ tiếp theo đăng ký nhận event và thực hiện bước kế tiếp.

~~~mermaid
flowchart LR
    O[OrderCreated] --> I[Inventory Service]
    I -->|StockReserved| P[Payment Service]
    P -->|PaymentAuthorized| C[Order Service]
    I -->|StockRejected| F[Order Service]
    P -->|PaymentDeclined| R[Inventory Release]
    R --> F
~~~

Ưu điểm:

- Các dịch vụ ít phụ thuộc trực tiếp vào coordinator.
- Có thể mở rộng consumer theo event.
- Hợp với quy trình đơn giản, số bước ít.

Hạn chế:

- Khó nhìn toàn bộ workflow khi số event và nhánh tăng.
- Quan hệ giữa các dịch vụ có thể trở nên khó theo dõi.
- Dễ tạo vòng lặp event hoặc logic bù trừ phân tán nếu không có hợp đồng rõ.

### Orchestration: một coordinator quản lý state

Một saga orchestrator lưu state và gửi command đến từng dịch vụ. Khi nhận kết quả, nó quyết định bước tiếp theo hoặc hành động bù trừ.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Order Saga
    participant I as Inventory
    participant P as Payment
    C->>S: Create order
    S->>I: Reserve stock
    I-->>S: Stock reserved
    S->>P: Authorize payment
    P-->>S: Payment authorized
    S->>S: Commit saga state
    S-->>C: Order confirmed
    Note over S: Nếu Payment từ chối,<br/>orchestrator yêu cầu release stock
~~~

Orchestration phù hợp khi workflow có nhiều bước, timeout, deadline, nhánh điều kiện và hành động bù trừ. Coordinator là một thành phần quan trọng nên state và command phát đi cũng cần outbox/inbox để tránh mất bước khi process restart.

Không có lựa chọn đúng cho mọi hệ thống. Chọn choreography khi quy trình đơn giản và các event có quan hệ rõ; chọn orchestration khi cần quan sát và điều khiển một workflow nhiều nhánh.

## 10. Hành động bù trừ phải idempotent

Giả sử Payment authorize thành công nhưng Order không nhận được response. Orchestrator có thể timeout và gửi lại command authorize. Nếu Payment tạo authorization mới mỗi lần, khách hàng có thể bị giữ tiền nhiều lần.

Hãy dùng một operation ID ổn định:

~~~java
public record AuthorizePayment(
    UUID sagaId,
    UUID operationId,
    String orderId,
    BigDecimal amount
) {}
~~~

Payment lưu operationId với kết quả. Lần nhận lại cùng operationId trả kết quả cũ. Tương tự, lệnh release reservation cần có operationId hoặc reservationId và phải an toàn khi gọi lặp.

Các hành động bù trừ nên có trạng thái riêng:

- REQUESTED: đã yêu cầu bù trừ.
- IN_PROGRESS: đang xử lý.
- COMPLETED: bù trừ thành công.
- RETRYABLE_FAILURE: lỗi tạm thời, có thể thử lại.
- MANUAL_REVIEW: không thể tự động bù trừ an toàn.

Nếu bù trừ thất bại vĩnh viễn, đừng đánh dấu saga đã hoàn tất. Giữ trạng thái cần can thiệp và cung cấp công cụ vận hành để xử lý.

## 11. Timeout và kết quả không xác định

Timeout không chứng minh server chưa xử lý request. Có thể xảy ra các trường hợp:

1. Request chưa đến server.
2. Request đến server nhưng chưa bắt đầu xử lý.
3. Server đã commit nhưng response bị mất.
4. Server đang xử lý và client timeout trước khi hoàn tất.
5. Server đã trả response nhưng mạng bị ngắt trước khi client nhận.

~~~mermaid
sequenceDiagram
    participant C as RSocket client
    participant S as Service
    participant DB as Service database
    C->>S: REQUEST_RESPONSE (operationId)
    S->>DB: Commit local transaction
    DB-->>S: Commit OK
    S--xC: Response lost / timeout
    Note over C: Client không biết server đã commit hay chưa
    C->>S: Retry cùng operationId
    S->>DB: Check idempotency/inbox
    DB-->>S: Existing result
    S-->>C: Return original result
~~~

Vì vậy:

- Retry cùng command/event ID.
- Consumer tra cứu kết quả đã xử lý.
- Không tạo operation ID mới chỉ vì timeout.
- Cung cấp API truy vấn trạng thái nếu kết quả cần được xác định sau đó.
- Đặt deadline cho toàn saga, không chỉ từng request.
- Có chính sách xử lý workflow quá hạn.

Không nên retry tất cả lỗi. Validation error, authentication failure và business conflict thường không tự hết khi gửi lại. Retry lỗi tạm thời như network reset, service unavailable hoặc throttling với backoff, jitter và giới hạn số lần.

## 12. Thứ tự sự kiện và cạnh tranh cập nhật

Một event có thể đến trễ hoặc sai thứ tự do retry, nhiều relay, nhiều partition hoặc nhiều request song song. Không nên dựa hoàn toàn vào thứ tự thời gian nhận ở consumer.

Có thể gắn sequence number theo aggregate:

~~~java
public record OrderEvent(
    UUID eventId,
    String orderId,
    long sequence,
    String eventType,
    Instant occurredAt,
    Object payload
) {}
~~~

Consumer lưu sequence đã áp dụng. Nếu nhận sequence nhỏ hơn hoặc bằng sequence hiện tại, coi đó là duplicate/stale theo hợp đồng. Nếu sequence nhảy có khoảng trống, có thể tạm hoãn, truy vấn event thiếu hoặc đánh dấu workflow cần phục hồi.

Một số biện pháp:

- Partition event theo aggregateId để giữ thứ tự trong cùng một partition.
- Dùng optimistic locking/version trên aggregate.
- Kiểm tra sequence ở consumer.
- Thiết kế handler idempotent.
- Không giả định timestamp đồng hồ giữa nhiều máy luôn đồng bộ chính xác.

Nếu hai command cùng cập nhật một reservation, Inventory phải bảo vệ invariant bằng transaction và concurrency control cục bộ. Event ordering ở tầng transport không thay thế kiểm soát cạnh tranh trong database.

## 13. Đọc dữ liệu trong khi workflow chưa hoàn tất

Khi workflow eventual consistent, client có thể đọc trạng thái trước khi tất cả dịch vụ cập nhật xong. API nên công bố trạng thái đủ rõ:

~~~json
{
  "orderId": "order-42",
  "status": "PAYMENT_PENDING",
  "updatedAt": "2026-11-22T10:15:30Z"
}
~~~

Client có thể:

- Nhận orderId và trạng thái PENDING từ request-response.
- Gọi route orders.status để truy vấn trạng thái.
- Subscribe route orders.watch để nhận thay đổi.
- Hiển thị thông báo đang xử lý thay vì báo đơn đã xác nhận.

Nếu client cần read-your-writes, hãy trả trạng thái từ dịch vụ sở hữu order hoặc dùng một projection có version để bảo đảm kết quả không cũ hơn command vừa gửi. Không đọc một read model eventual consistent rồi khẳng định transaction mới đã được phản ánh.

## 14. Chọn interaction RSocket cho từng bước

RSocket cung cấp nhiều interaction, nhưng không interaction nào tự thay thế transaction boundary.

| Nhu cầu | Interaction gợi ý | Điều cần lưu ý |
|---|---|---|
| Gửi command và cần kết quả tiếp nhận | Request-response | ACK chỉ đáng tin khi được trả sau điều kiện commit đã cam kết |
| Gửi telemetry có thể bỏ | Fire-and-forget | Không có response để xác nhận |
| Theo dõi trạng thái saga | Request-stream | Hủy subscription không hủy saga trừ khi nghiệp vụ định nghĩa |
| Gửi chuỗi dữ liệu và nhận tiến độ | Request-channel | Cần quản lý cancellation, sequence và buffer |
| Gửi event bền vững | Outbox relay tới broker hoặc RSocket endpoint có ACK | Cần deduplication và retry |

Request-stream có thể thông báo trạng thái workflow, nhưng không nên coi việc client subscribe là điều kiện duy nhất để saga tiếp tục. Workflow phải tiến triển độc lập với vòng đời của giao diện hoặc kết nối client.

Nếu dùng RSocket trực tiếp làm đường truyền outbox, hãy định nghĩa ACK, timeout, retry, deduplication và lưu trạng thái dispatch. Với yêu cầu replay, retention, consumer group hoặc phân phối nhiều instance, message broker có thể phù hợp hơn. RSocket có thể là API giao tiếp giữa dịch vụ; broker có thể là lớp lưu giữ và phân phối event.

## 15. Các lỗi thiết kế thường gặp

| Cách làm sai | Hậu quả | Cách thiết kế lại |
|---|---|---|
| Giữ transaction DB mở trong khi gọi nhiều dịch vụ | Lock lâu, connection pool cạn, vẫn không atomic | Commit local state và tiếp tục bằng workflow |
| Ghi DB rồi publish riêng | DB commit nhưng event mất | Transactional outbox |
| Publish event trước khi DB commit | Consumer thấy event của dữ liệu chưa tồn tại | Ghi outbox cùng transaction |
| Đánh dấu outbox đã gửi trước khi gửi | Crash làm mất event | Gửi trước, đánh dấu sau; consumer dedupe |
| Consumer chỉ kiểm tra exists rồi insert | Race condition khi duplicate đến đồng thời | Unique constraint và insert-if-absent |
| Retry với ID mới | Tạo đơn, charge hoặc reservation trùng | Giữ idempotency key ổn định |
| Xem timeout là chắc chắn thất bại | Lặp lại side effect đã commit | Truy vấn kết quả hoặc retry idempotent |
| Dùng FNF cho command cần ACK | Không biết command đã được xử lý chưa | Request-response hoặc durable broker ACK |
| Dùng Sinks trong memory làm outbox | Restart có thể mất event | Lưu event bền vững trong database/broker |
| Xem compensation là rollback tự động | Bù trừ có thể lỗi hoặc cần nghiệp vụ mới | State machine, retry và manual review |

## 16. Kiểm thử ranh giới nhất quán

Happy-path test chỉ chứng minh mọi dịch vụ hoạt động khi không có lỗi. Độ tin cậy cần được kiểm tra bằng cách cố ý làm gián đoạn từng ranh giới.

| Tình huống kiểm thử | Kết quả cần xác nhận |
|---|---|
| Order commit nhưng relay chưa chạy | Outbox còn pending và được gửi sau restart |
| Relay gửi thành công rồi crash trước khi mark published | Event có thể gửi lại nhưng consumer không áp dụng side effect lần hai |
| Consumer commit nhưng ACK bị mất | Retry cùng eventId trả kết quả cũ |
| Inventory giữ hàng nhưng Payment từ chối | Saga yêu cầu release reservation |
| Compensation timeout | Trạng thái bù trừ còn pending và được retry |
| Client timeout sau server commit | Retry cùng idempotency key không tạo duplicate |
| Hai event cùng aggregate đến sai thứ tự | Sequence/version phát hiện stale hoặc gap |
| Consumer nhận hai bản sao đồng thời | Unique constraint bảo vệ inbox |
| Một dịch vụ không khả dụng lâu dài | Saga chuyển trạng thái lỗi hoặc manual review theo deadline |
| Client hủy request-stream theo dõi | Saga vẫn tiếp tục; chỉ subscription bị hủy |

### Kiểm thử duplicate delivery

Có thể gọi consumer hai lần với cùng event ID:

~~~java
@Test
void duplicateEventDoesNotReserveTwice() {
    OrderCreated event = sampleOrderCreated("event-42");

    ProcessingResult first = consumer.handle(event);
    ProcessingResult second = consumer.handle(event);

    assertThat(first).isEqualTo(ProcessingResult.ACCEPTED);
    assertThat(second).isEqualTo(ProcessingResult.DUPLICATE);

    assertThat(reservationRepository.countByOrderId(event.orderId()))
        .isEqualTo(1);
}
~~~

Test này cần chạy với database test thực hoặc test container để xác nhận unique constraint và transaction thực sự hoạt động. Một mock repository đơn giản không thể chứng minh race condition được ngăn ở database.

### Kiểm thử saga phục hồi

Tạo test điều khiển từng bước để mô phỏng Payment timeout sau khi đã commit, sau đó gửi lại cùng operationId. Xác nhận Payment trả lại kết quả cũ, Saga không tạo authorization thứ hai và Order cuối cùng đi đến trạng thái phù hợp.

## 17. Quy trình thiết kế consistency boundary

Khi thiết kế một luồng đi qua nhiều dịch vụ, hãy trả lời theo thứ tự:

1. Dịch vụ nào sở hữu từng dữ liệu và invariant?
2. Mỗi bước nào cần transaction cục bộ?
3. Trạng thái trung gian nào là hợp lệ và được công bố cho client?
4. Thay đổi database và event được ghi nguyên tử bằng outbox như thế nào?
5. Consumer dedupe bằng inbox/event ID ra sao?
6. Workflow được điều phối bằng choreography hay orchestration?
7. Mỗi bước có timeout, retry policy và idempotency key nào?
8. Khi bước thất bại, compensation nào cần chạy?
9. Event ordering và version được kiểm soát thế nào?
10. Nếu compensation không thể tự phục hồi, ai xử lý manual review?
11. Client quan sát tiến trình qua request-response, request-stream hay truy vấn trạng thái?
12. Test đã bao phủ crash, duplicate, timeout, reorder và restart chưa?

Ranh giới nhất quán tốt làm rõ phần nào phải nguyên tử, phần nào được phép hoàn tất sau và cách hệ thống tự phục hồi. Transaction cục bộ bảo vệ dữ liệu do từng dịch vụ sở hữu; outbox/inbox bảo vệ việc trao đổi event; saga điều phối các bước nghiệp vụ; idempotency làm cho retry an toàn. RSocket là kênh giao tiếp giữa các peer, còn độ tin cậy cuối cùng đến từ các quy tắc dữ liệu và workflow mà ứng dụng thực thi.

## Ghi nhớ

- Một transaction cục bộ không tự bao trùm các dịch vụ được gọi qua RSocket.
- Bảo vệ invariant bên trong dịch vụ sở hữu dữ liệu bằng local transaction.
- Workflow liên dịch vụ thường cần trạng thái trung gian và eventual consistency.
- Transactional outbox ghi dữ liệu nghiệp vụ và event trong cùng transaction.
- Outbox relay có thể gửi duplicate; consumer cần inbox/idempotency.
- Ghi inbox và side effect trong cùng local transaction.
- Saga gồm các transaction cục bộ và hành động bù trừ; compensation không phải rollback tự động.
- Timeout tạo kết quả không xác định; retry phải giữ nguyên operation ID.
- RSocket request-response có thể mang ACK ứng dụng nếu server chỉ trả sau commit; FNF không có response payload.
- Request-stream theo dõi trạng thái không phải transaction và không nên điều khiển vòng đời saga.
- Kiểm thử crash, duplicate, timeout, reorder, compensation và restart.

## Tài liệu tham khảo

- [RSocket Protocol](https://rsocket.io/about/protocol/)
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework — Reactive Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Microservices.io — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
- [Microservices.io — Saga Pattern](https://microservices.io/patterns/data/saga.html)
- [Microservices.io — Idempotent Consumer](https://microservices.io/patterns/communication-style/idempotent-consumer.html)
- [Martin Fowler — Eventual Consistency](https://martinfowler.com/articles/patterns-of-distributed-systems/eventual-consistency.html)

