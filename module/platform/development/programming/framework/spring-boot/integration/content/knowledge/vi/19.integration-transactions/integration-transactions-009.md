# Phân biệt giao dịch cục bộ, giao dịch phân tán và nhất quán cuối cùng

> **Chương:** Giao dịch tích hợp  
> **Module:** SPRING_BOOT_INTEGRATION — tích hợp hệ thống trong Spring Boot qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter Spring Integration.  
> **Mục tiêu:** Nhận diện ranh giới commit thực sự, chọn cách phối hợp dữ liệu giữa các hệ thống và thiết kế xử lý lỗi, trùng lặp, kiểm thử, quan sát cho luồng tích hợp.

Một ứng dụng đặt hàng cần ghi đơn vào PostgreSQL, giảm hàng tồn tại một dịch vụ khác, rồi yêu cầu thanh toán. Nếu cả ba thao tác đều thành công, người dùng thấy đơn đã xác nhận. Nếu ghi đơn thành công nhưng thanh toán thất bại, hệ thống phải trả lời được: dữ liệu nào đã được commit, dữ liệu nào có thể hoàn tác, và bao giờ mọi dịch vụ nhìn thấy trạng thái cuối cùng?

Ba khái niệm thường bị nhầm lẫn:

- **Giao dịch cục bộ (local transaction):** một đơn vị công việc được commit/rollback bởi một transaction manager trên một tài nguyên giao dịch, thường là một cơ sở dữ liệu.
- **Giao dịch phân tán (distributed transaction):** một nghiệp vụ trải qua nhiều tài nguyên/dịch vụ cần phối hợp. Nếu yêu cầu commit nguyên tử giữa các tài nguyên hỗ trợ, có thể dùng **XA/JTA với two-phase commit (2PC)**; nếu phối hợp qua các bước có bù trừ, thường dùng **Saga**, với tính nhất quán được thiết kế ở mức nghiệp vụ.
- **Nhất quán cuối cùng (eventual consistency):** một **mô hình nhất quán**, trong đó các bản sao/dịch vụ có thể tạm thời nhìn thấy trạng thái khác nhau nhưng hội tụ về kết quả mong muốn sau khi cập nhật được phân phối và xử lý thành công.

Hai khái niệm đầu chủ yếu mô tả **ranh giới và cơ chế phối hợp giao dịch**; khái niệm thứ ba mô tả **khi nào dữ liệu giữa các thành phần phải thống nhất**. Một Saga là cách triển khai nghiệp vụ phân tán thường chấp nhận nhất quán cuối cùng, còn XA/2PC cố gắng bảo đảm commit nguyên tử trên các tài nguyên tham gia.

## 1. Tại sao ranh giới giao dịch quan trọng?

Xét chuỗi xử lý:

~~~mermaid
flowchart LR
    A["Order Service<br/>ghi PostgreSQL"] --> B["Inventory Service<br/>gọi HTTP"]
    B --> C["Payment Service<br/>gọi HTTP"]
    C --> D["Message Broker<br/>phát sự kiện"]
~~~

Không có một lệnh rollback mặc định nào có thể quay ngược đồng thời giao dịch PostgreSQL, request HTTP đã được dịch vụ khác xử lý, khoản thanh toán đã được chấp nhận và sự kiện đã được broker nhận.

Giả sử đoạn code:

~~~java
@Transactional
public void placeOrder(PlaceOrderCommand command) {
    orderRepository.save(new Order(command));
    inventoryClient.reserve(command); // HTTP
    paymentClient.charge(command);     // HTTP
}
~~~

Nếu **charge** thành công nhưng commit database tại Order Service thất bại, giao dịch cục bộ của Order Service rollback; nghiệp vụ thanh toán ở Payment Service **không tự rollback**. Nếu **reserve** thành công nhưng HTTP response bị mất, Order Service không biết bên kia đã thực thi hay chưa. Đây là vấn đề ranh giới hệ thống, không phải thiếu một annotation.

**Quy tắc cốt lõi:** trước khi chọn pattern, xác định rõ **ai giữ dữ liệu**, **ai sở hữu transaction manager**, **điểm commit nằm ở đâu** và **tài nguyên nào có khả năng tham gia giao thức giao dịch chung**.

## 2. Giao dịch cục bộ: ACID trong một ranh giới tài nguyên

Giao dịch cục bộ là lựa chọn phù hợp khi các thay đổi cần nguyên tử cùng được lưu trong một cơ sở dữ liệu. Ví dụ trong Order Service:

1. Chèn bản ghi **orders**.
2. Chèn các dòng **order_items**.
3. Trừ số lượng tồn kho **nếu tồn kho cũng được sở hữu và cập nhật trong cùng DB**.
4. Commit tất cả; nếu lỗi, rollback tất cả.

Các tính chất ACID gồm:

| Tính chất | Ý nghĩa trong một DB transaction |
| --- | --- |
| **Atomicity** | Tất cả thao tác trong transaction cùng thành công hoặc cùng rollback |
| **Consistency** | Constraint và các quy tắc được triển khai giúp DB đi từ trạng thái hợp lệ sang hợp lệ |
| **Isolation** | Các transaction đồng thời được cô lập theo isolation level đã chọn |
| **Durability** | Dữ liệu đã commit được DB lưu bền vững theo cam kết của hệ quản trị |

ACID không tự đảm bảo mọi quy tắc nghiệp vụ trong code đều đúng. Chọn isolation level quá yếu hoặc thiếu constraint vẫn có thể gây lost update, double booking và race condition.

### 2.1. Spring Boot với Spring Data/JDBC

Với Spring Boot sử dụng transaction manager cho JDBC/JPA, **@Transactional** thường tạo transaction ở ranh giới method public được gọi qua Spring proxy. Ví dụ một local transaction:

~~~java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final OrderItemRepository items;

    public OrderService(OrderRepository orders,
                        OrderItemRepository items) {
        this.orders = orders;
        this.items = items;
    }

    @Transactional
    public Long create(CreateOrderCommand command) {
        Order order = orders.save(
                new Order(command.customerId(), "PENDING"));
        command.lines().forEach(line ->
                items.save(new OrderItem(order.getId(),
                        line.sku(), line.quantity())));
        return order.getId();
    }
}
~~~

Các entity, repository và command ở ví dụ trên đại diện cho model của ứng dụng. Cả hai repository phải sử dụng **cùng transaction manager / data source có giao dịch được quản lý tương ứng** thì mới có cùng ranh giới rollback. Không suy diễn rằng hai datasource khác nhau sẽ được commit nguyên tử chỉ vì cùng xuất hiện trong method có @Transactional.

Lưu ý:

- Mặc định, declarative transaction của Spring rollback khi có **RuntimeException** hoặc **Error**; checked exception cần chính sách rollback phù hợp như **rollbackFor** nếu muốn rollback.
- **@Transactional** không có hiệu lực như mong đợi khi gọi method được đánh dấu từ một method khác của **chính object** qua self-invocation trong cấu hình proxy thông thường.
- Trong ứng dụng reactive R2DBC, cần **ReactiveTransactionManager** và luồng Publisher có quản lý transaction, ví dụ **TransactionalOperator**; transaction reactive đi theo Reactor Context, không tương đương transaction JDBC/JPA gắn thread.
- Không giữ transaction DB mở trong lúc chờ HTTP lâu: connection và lock có thể bị giữ, làm tăng contention và khó phục hồi.

### 2.2. Giao dịch cục bộ không bao phủ side effect ngoài DB

Ví dụ:

~~~java
@Transactional
public void completeOrder(Long orderId) {
    orders.markCompleted(orderId);     // thay đổi trong DB
    kafkaTemplate.send("orders", orderId.toString(), "COMPLETED");
}
~~~

Ngay cả khi database transaction rollback, một message đã được broker nhận **không mặc nhiên biến mất**. Ngược lại, database commit có thể thành công nhưng gửi message thất bại. Việc cấu hình transaction cho riêng Kafka producer hay cho riêng DB không tự tạo một giao dịch nguyên tử trải dài cả hai. Cần chỉ rõ cơ chế phối hợp, giới hạn bảo đảm và cách xử lý lỗi.

## 3. Giao dịch phân tán: một yêu cầu nghiệp vụ, nhiều nơi commit

Một giao dịch phân tán theo nghĩa rộng gồm nhiều bước tác động đến các hệ thống độc lập. Có hai nhóm chiến lược thường gặp:

1. **Atomic distributed transaction:** phối hợp commit trên các tài nguyên có hỗ trợ XA/2PC, cố gắng đạt all-or-nothing ở mức tài nguyên.
2. **Business transaction / Saga:** mỗi dịch vụ commit cục bộ một bước; nếu bước sau thất bại, chạy **compensating action** để đưa nghiệp vụ sang trạng thái chấp nhận được.

Không nên đồng nhất khái niệm **distributed transaction** chỉ với XA. Đồng thời cũng không nên gọi Saga là rollback nguyên tử: Saga có giai đoạn trung gian và hành động bù trừ thường không thể xóa mọi tác động quan sát được.

### 3.1. XA/JTA và two-phase commit (2PC)

Trong XA, một **transaction coordinator** trao đổi với các resource manager có hỗ trợ giao thức XA, thường qua các bước:

~~~mermaid
sequenceDiagram
    participant App as Application
    participant TM as JTA Transaction Manager
    participant DB as XA Database
    participant JMS as XA JMS Broker
    App->>TM: begin transaction
    App->>DB: write rows
    App->>JMS: send message
    TM->>DB: prepare
    DB-->>TM: prepared
    TM->>JMS: prepare
    JMS-->>TM: prepared
    Note over TM: Quyết định commit nếu các bên prepare thành công
    TM->>DB: commit
    TM->>JMS: commit
    Note over TM, JMS: Cần recovery khi có participant / coordinator lỗi
~~~

**Phase 1 — Prepare:** coordinator hỏi từng tài nguyên xem có sẵn sàng commit không; tài nguyên có thể cần giữ lock và trạng thái đã chuẩn bị. **Phase 2 — Commit/Rollback:** coordinator quyết định và yêu cầu từng tài nguyên thực hiện quyết định đó.

Các điều kiện tiên quyết:

- Có **JTA transaction manager** được cấu hình đúng, có khả năng recovery.
- Các driver/resource manager tham gia đều **hỗ trợ XA**, không chỉ hỗ trợ transaction cục bộ.
- Ứng dụng hiểu ranh giới timeout, lỗi mạng, khả năng **in-doubt** khi một participant đã prepare nhưng chưa biết kết quả cuối.
- Có cơ chế vận hành, giám sát, khôi phục coordinator log và xử lý transaction treo.

Ví dụ cấu hình **@Transactional** có thể tham gia JTA transaction nếu ứng dụng thực sự sử dụng transaction manager JTA và các resource được enlist đúng. Nhưng bản thân **@Transactional** không tự bật XA cho hai DB, REST API, Kafka, RabbitMQ hoặc mọi adapter của Spring Integration.

**Hạn chế quan trọng:** REST/HTTP thông thường không phải XA participant. Hai dịch vụ tự commit database của mình không tự tham gia một 2PC chỉ vì dịch vụ A gọi dịch vụ B bằng WebClient hoặc RestClient. Với Kafka, Spring Kafka cung cấp các cơ chế transaction của Kafka, nhưng không được giả định chúng là transaction XA chung với DB của ứng dụng.

2PC có thể hợp lý khi một hệ thống nội bộ kiểm soát vài resource hỗ trợ XA và yêu cầu nguyên tử rất cao. Đổi lại, phối hợp prepare/commit làm tăng độ trễ, coupling, lock contention và áp lực recovery; khả năng sẵn sàng có thể bị ảnh hưởng khi một participant hoặc coordinator gặp sự cố.

### 3.2. Saga: giao dịch nghiệp vụ theo chuỗi các local transaction

Giả sử mỗi dịch vụ sở hữu database riêng:

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant I as Inventory Service
    participant P as Payment Service
    O->>O: T1: lưu đơn PENDING
    O->>I: Reserve stock (command/event)
    I->>I: T2: commit reservation
    I-->>O: StockReserved
    O->>P: Authorize payment
    P->>P: T3: commit authorization
    alt Payment authorized
        P-->>O: PaymentAuthorized
        O->>O: T4: đơn CONFIRMED
    else Payment rejected
        P-->>O: PaymentRejected
        O->>I: Compensate: Release stock
        I->>I: T4: commit release
        O->>O: T5: đơn CANCELLED
    end
~~~

T1, T2, T3... là những transaction **cục bộ riêng**. Khi một bước bị lỗi nghiệp vụ, Saga thực hiện bước **bù trừ** (ví dụ giải phóng phần tồn đã giữ, hoàn tiền nếu đã thu). Bù trừ không đảm bảo xóa được email đã gửi, thông báo đã đọc hoặc chi phí bên ngoài đã phát sinh.

Hai kiểu tổ chức phổ biến:

| Kiểu Saga | Cách điều phối | Phù hợp | Rủi ro chính |
| --- | --- | --- | --- |
| **Choreography** | Các dịch vụ phản ứng với sự kiện nghiệp vụ của nhau | Luồng ít bước, phụ thuộc đơn giản | Khó nhìn toàn cục; dependency sự kiện dàn trải |
| **Orchestration** | Một orchestrator lưu trạng thái Saga và gửi command cho các bước | Luồng nhiều bước, timeout và bù trừ phức tạp | Orchestrator cần bảo đảm HA, lưu trạng thái và chống trùng |

Một Saga cần mô hình trạng thái rõ ràng, ví dụ **PENDING → RESERVING → PAYING → CONFIRMED** hoặc **COMPENSATING → CANCELLED**. Cần có idempotency, xử lý timeout, retry, phát hiện bước treo, thứ tự sự kiện và xử lý thủ công khi bù trừ không thành công.

## 4. Nhất quán cuối cùng: hội tụ sau một khoảng trễ

Nhất quán cuối cùng cho phép các thành phần tạm thời không đồng bộ. Sau khi hệ thống ngừng nhận cập nhật mới và các cập nhật đang chờ được xử lý thành công theo cơ chế đồng bộ, các bản sao/trạng thái liên quan **kỳ vọng hội tụ**.

Ví dụ Order Service đã commit **PENDING** lúc 10:00:00, Inventory Service giữ hàng lúc 10:00:01, Payment Service xác nhận lúc 10:00:02 và Order Service đổi thành **CONFIRMED** lúc 10:00:03. Trong khoảng ba giây, các dịch vụ có thể trả trạng thái khác nhau dù hệ thống hoạt động đúng thiết kế.

~~~mermaid
flowchart LR
    A["10:00:00<br/>Order: PENDING"] --> B["10:00:01<br/>Stock: RESERVED"]
    B --> C["10:00:02<br/>Payment: AUTHORIZED"]
    C --> D["10:00:03<br/>Order: CONFIRMED"]
~~~

**Không có một khoảng thời gian hội tụ cố định** do chữ eventual tự bảo đảm. Nếu sự kiện bị mất, consumer hỏng, message vào dead-letter queue hoặc compensation thất bại, hệ thống có thể **không hội tụ** nếu thiếu retry, reconciliation và xử lý ngoại lệ. Vì thế eventual consistency là một **cam kết thiết kế cần điều kiện vận hành**.

Cần quy định rõ:

- **Trạng thái trung gian:** API có thể trả **202 Accepted** hoặc **PENDING**, thay vì thông báo thanh toán thành công khi mới ghi đơn.
- **Thời gian hội tụ mong đợi:** ví dụ 99% đơn chuyển khỏi PENDING trong một ngưỡng đã đo, kèm cảnh báo các đơn quá hạn.
- **Quyền quan sát:** người dùng có thể đọc trạng thái nào, khi nào có quyền hủy, khi nào coi kết quả là cuối.
- **Quy tắc xung đột:** event cũ đến sau event mới phải được bỏ qua hoặc giải quyết qua version/sequence.
- **Chính sách phục hồi:** retry, dead-letter queue, job đối soát, dashboard và thao tác quản trị.

Nhất quán cuối cùng **không đồng nghĩa dữ liệu sai hoặc mất**; nó có nghĩa là có khoảng thời gian hệ thống chấp nhận sự khác biệt có kiểm soát. Một dịch vụ vẫn có thể dùng transaction ACID cục bộ, còn toàn bộ workflow tuân theo eventual consistency.

## 5. So sánh nhanh ba khái niệm

| Tiêu chí | Giao dịch cục bộ | Giao dịch phân tán kiểu XA/2PC | Phối hợp Saga và nhất quán cuối cùng |
| --- | --- | --- | --- |
| Đối tượng commit | Một resource/transaction manager | Nhiều resource XA dưới coordinator | Mỗi dịch vụ commit riêng |
| Bảo đảm nguyên tử | Trong phạm vi local DB/resource | Cố gắng nguyên tử qua XA participants theo giao thức/recovery | Không nguyên tử toàn cục; xử lý bù trừ ở mức nghiệp vụ |
| Dữ liệu nhìn thấy lúc chuyển trạng thái | Theo isolation/commit của local DB | Thường hướng tới cùng quyết định commit của các participant | Có trạng thái trung gian, có độ trễ |
| Lỗi giữa các bước | Rollback local transaction | Recovery và in-doubt theo coordinator | Retry, idempotency, compensation, reconciliation |
| Phụ thuộc hạ tầng | DB và transaction manager | JTA, XA-capable resources, recovery | Broker/HTTP, trạng thái Saga, outbox/inbox và retry |
| Độ phức tạp | Thấp hơn trong phạm vi một DB | Cao, yêu cầu tương thích giao thức | Cao về logic nghiệp vụ và vận hành |
| Hợp với REST API độc lập | Không bao trùm remote effect | HTTP thường không phải XA participant | Thường phù hợp hơn |
| Ví dụ | Ghi order và order_items cùng DB | DB + XA JMS trên hệ thống tương thích | Order–Inventory–Payment qua event/command |

Không tồn tại một lựa chọn tốt nhất cho mọi ứng dụng. Nếu business invariant có thể đặt trọn trong một DB transaction, giữ nó cục bộ sẽ dễ chứng minh tính đúng. Khi phải qua nhiều dịch vụ độc lập, cần chọn rõ atomic commit có khả thi hay chấp nhận tiến trình eventual với xử lý ngoại lệ.

## 6. Hai bài toán kinh điển khi ghép database với message broker

### 6.1. Gửi sự kiện sau khi commit: rủi ro mất event

~~~text
T1  Order Service: COMMIT order=123
T2  Process crash
T3  Chưa kịp PUBLISH OrderCreated
=> Database có đơn, nhưng downstream không được báo.
~~~

Nếu đổi thứ tự:

~~~text
T1  PUBLISH OrderCreated thành công
T2  Database COMMIT bị lỗi
=> Consumer đã xử lý một sự kiện cho đơn không tồn tại.
~~~

Việc gửi trước/sau commit đơn thuần không giải quyết được atomicity giữa DB và broker khi chúng là hai resource độc lập.

### 6.2. Transactional Outbox: đảm bảo lưu thay đổi và ý định phát event cùng nhau

**Transactional Outbox** ghi trạng thái nghiệp vụ và một hàng sự kiện vào **cùng database transaction**. Một publisher khác đọc outbox và gửi event tới broker. Kết quả: không có đơn nào commit mà thiếu **ý định phát event** đã commit tương ứng.

~~~mermaid
flowchart LR
    A["POST /orders"] --> B["Local DB transaction"]
    B --> C["orders<br/>status=PENDING"]
    B --> D["outbox_event<br/>type=OrderCreated"]
    D --> E["Outbox publisher / CDC"]
    E --> F["Broker"]
    F --> G["Inventory consumer"]
    G --> H["Local DB transaction<br/>inbox + business data"]
~~~

Ví dụ cấu trúc PostgreSQL:

~~~sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    sku VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE outbox_event (
    id UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ
);

CREATE INDEX idx_outbox_status_created
    ON outbox_event (status, created_at);
~~~

Một service Spring Boot dùng **JdbcTemplate** để minh họa atomic local write:

~~~java
import java.util.UUID;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper json;

    public OrderApplicationService(JdbcTemplate jdbc, ObjectMapper json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    @Transactional
    public UUID placeOrder(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        UUID orderId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();

        // Cùng datasource, cùng local transaction:
        jdbc.update("""
                INSERT INTO orders (id, sku, quantity, status)
                VALUES (?, ?, ?, 'PENDING')
                """, orderId, sku, quantity);

        String payload = json.createObjectNode()
                .put("eventId", eventId.toString())
                .put("orderId", orderId.toString())
                .put("sku", sku)
                .put("quantity", quantity)
                .toString();

        jdbc.update("""
                INSERT INTO outbox_event
                       (id, aggregate_id, event_type, payload)
                VALUES (?, ?, 'OrderCreated', ?)
                """, eventId, orderId, payload);

        return orderId;
    }
}
~~~

Khi **placeOrder** commit, cả **orders** và **outbox_event** tồn tại. Khi exception khiến transaction rollback, cả hai không tồn tại. Đó là bảo đảm của **transaction cục bộ**, không phải distributed commit với broker. Ví dụ sử dụng Java text block và PostgreSQL; dự án cần dependency Spring JDBC, PostgreSQL driver, Jackson và cấu hình DataSource/transaction manager phù hợp.

Publisher có thể dùng polling hoặc CDC:

~~~text
repeat:
    batch = claimOutboxWithLease(limit = 100)
    for event in batch:
        try:
            broker.publish(
                key = event.aggregateId,
                eventId = event.id,
                payload = event.payload
            )
            awaitBrokerAcknowledgement()
            markPublished(event.id)
        catch transientFailure:
            scheduleRetryWithBackoff(event.id)
~~~

**Đây là pseudocode về thuật toán**, không phải API có sẵn của Spring Kafka/JMS. Khi nhiều publisher chạy song song, cần cơ chế **claim/lease** có tính đồng thời, không giữ DB transaction mở suốt network call và giải phóng lease khi worker chết. Với PostgreSQL, thường dùng transaction ngắn và **FOR UPDATE SKIP LOCKED** để claim; cách thực thi cụ thể phụ thuộc yêu cầu ordering và schema.

Một tình huống đặc biệt quan trọng:

~~~text
Publish thành công -> broker đã nhận event
Publisher chết trước markPublished
Publisher chạy lại -> phát lại cùng event
=> Consumer có thể nhận hai lần.
~~~

Transactional Outbox bảo đảm **lưu ý định phát cùng thay đổi DB**, nhưng không tự đảm bảo chỉ có một lần phát/nhận trong mọi lỗi. Hãy thiết kế idempotent consumer hoặc Inbox pattern.

## 7. Inbox, idempotency và thứ tự sự kiện

Với delivery **at-least-once**, một event có thể được giao lại. Mỗi event cần **eventId** ổn định qua mọi lần retry và redelivery. Consumer có thể lưu eventId vào bảng **processed_message** trong **cùng local transaction** với thay đổi nghiệp vụ:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE shipment (
    order_id UUID PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);
~~~

~~~java
@Transactional
public void handleOrderCreated(UUID eventId, UUID orderId) {
    int firstTime = jdbc.update("""
            INSERT INTO processed_message (consumer_name, event_id)
            VALUES ('shipment-service', ?)
            ON CONFLICT DO NOTHING
            """, eventId);

    if (firstTime == 0) {
        return; // đã xử lý trước đó
    }

    jdbc.update("""
            INSERT INTO shipment (order_id, status)
            VALUES (?, 'NEW')
            ON CONFLICT (order_id) DO NOTHING
            """, orderId);
}
~~~

Đoạn handler minh họa PostgreSQL và cần đặt trong một Spring bean được transaction interceptor quản lý. Nếu transaction thất bại thì cả dấu đã xử lý và thay đổi shipment cùng rollback, để broker redeliver có thể xử lý lại. Acknowledge message **sau khi** transaction consumer commit thành công. Cần cân nhắc riêng lỗi nghiệp vụ vĩnh viễn: retry vô hạn một sự kiện sai định dạng có thể khiến hàng đợi bị kẹt.

**Idempotency key** cho request tạo đơn và **eventId** cho consumer là hai phạm vi khác nhau. Nếu client gửi POST hai lần do timeout, cần một **business request idempotency key** để không tạo hai đơn; Inbox chỉ chống trùng **sự kiện đã phát** và không tự chống trùng lệnh đầu vào.

Thứ tự sự kiện cũng không tự được bảo đảm trong mọi cấu hình broker. Nếu cùng một đơn phát **OrderCreated**, **OrderConfirmed**, **OrderCancelled**, có thể thêm **aggregateVersion** tăng đơn điệu và chỉ áp dụng transition hợp lệ. Với Kafka, dùng cùng aggregate ID làm partition key giúp giữ thứ tự trong một partition đối với đường phát phù hợp, nhưng vẫn phải xử lý replay, producer retry, nhiều publisher và version ở consumer.

## 8. Tình huống lỗi: điều gì thực sự xảy ra?

| Điểm lỗi | Local transaction | XA/2PC | Saga / outbox và eventual consistency |
| --- | --- | --- | --- |
| Lỗi trước DB commit | Rollback thay đổi trong DB | Coordinator ra quyết định rollback nếu chưa commit toàn cục | Local step rollback; có thể thử lại |
| Lỗi sau DB commit, trước gửi event | Event có thể mất nếu không có outbox | Nếu resource XA tham gia, recovery theo quyết định của coordinator | Outbox đã commit vẫn còn để publisher gửi lại |
| Gửi event xong nhưng mất ACK | Side effect ngoài DB có thể đã xảy ra | Chỉ được phối hợp nếu resource hỗ trợ XA và được enlist | Publisher có thể phát lại; consumer phải chống trùng |
| HTTP timeout sau khi đối tác xử lý | Không tự rollback HTTP | REST thông thường ngoài phạm vi XA | Query status/idempotency trước khi quyết định retry hay bù trừ |
| Một Saga step thất bại nghiệp vụ | Local step tương ứng rollback | Nếu các resource là XA participants có thể phối hợp rollback; không bao gồm mọi side effect | Chạy compensation theo state machine |
| Compensating action cũng lỗi | Không có cơ chế toàn cục mặc định | Không áp dụng trong kịch bản Saga | Ghi trạng thái COMPENSATING/FAILED, retry, đối soát, cảnh báo |
| Event đến trễ hoặc đảo thứ tự | Nằm ngoài transaction của producer | XA không tự giải quyết thứ tự nghiệp vụ sau commit | Dựa vào version, rule chuyển trạng thái, backlog monitoring |

**Không thể suy luận “HTTP timeout = đối tác chưa xử lý”.** Request có thể đã đến Payment Service, đã ghi database, nhưng response bị mất giữa mạng. Vì thế retry với **idempotency key** hoặc endpoint truy vấn trạng thái theo mã lệnh thường an toàn hơn việc gửi lệnh thu tiền mới không có khóa chống trùng.

## 9. Chọn phương án cho các kịch bản tích hợp Spring Boot

### 9.1. Bài toán một database

**Yêu cầu:** tạo đơn cùng các dòng chi tiết và cập nhật tổng tiền, tất cả trong một PostgreSQL.

**Lựa chọn:** local transaction với **@Transactional** (JPA/JDBC) và constraint trong database. Cân nhắc optimistic lock/version hoặc khóa phù hợp khi tranh chấp tồn kho. Không cần Saga nếu toàn bộ invariant đã nằm trong cùng một DB.

### 9.2. Database và sự kiện Kafka/RabbitMQ

**Yêu cầu:** commit đơn rồi thông báo sang email, kho hoặc analytics; việc gửi có thể trễ một chút.

**Lựa chọn:** transactional outbox + publisher hoặc CDC + consumer idempotent. Đảm bảo event không bị mất vì process crash sau commit DB, đồng thời chuẩn bị cho duplicate delivery, ordering và backlog.

### 9.3. Nhiều cơ sở dữ liệu XA trong một ứng dụng nội bộ

**Yêu cầu:** cập nhật hai resource có hỗ trợ XA, cần cùng quyết định commit; tổ chức chấp nhận chi phí recovery.

**Lựa chọn:** cân nhắc JTA/XA/2PC sau khi xác minh driver/resource manager và transaction manager. Nên benchmark lock, timeout, failover và diễn tập in-doubt transaction trước khi sử dụng production.

### 9.4. Order, Inventory và Payment là microservice độc lập

**Yêu cầu:** các dịch vụ sở hữu DB riêng, giao tiếp qua HTTP/broker, có thanh toán và bù trừ.

**Lựa chọn:** Saga với trạng thái rõ ràng, outbox/inbox ở những điểm cần phát/nhận sự kiện tin cậy, command idempotent, retry có điều kiện, timeout và compensation. Khách hàng nhìn thấy trạng thái **PENDING** cho tới khi hoàn tất.

### 9.5. Cache, read model và search index

**Yêu cầu:** cập nhật database rồi làm mới Redis cache hoặc Elasticsearch.

**Lựa chọn:** database là nguồn dữ liệu chính; cập nhật cache/index theo sự kiện hoặc invalidation, chấp nhận dữ liệu cũ trong cửa sổ xác định. Cache/index thường không là XA participant. Đặt TTL, versioning, retry và cơ chế rebuild/read repair nếu cần.

### 9.6. Luồng Spring Integration

Spring Integration cung cấp channel, adapter, endpoint, poller và cơ chế transaction trên các thành phần hỗ trợ. Một poller đọc DB/JMS có thể chạy trong transaction của nguồn khi được cấu hình đúng. Nhưng **flow gồm nhiều adapter** không tự biến thành một transaction nguyên tử xuyên HTTP, Kafka, cache và các dịch vụ độc lập. Cần xác định chính xác transaction manager và khả năng transaction của từng endpoint/adaptor.

## 10. Thiết kế hợp đồng và quan sát cho Saga/eventual consistency

Với luồng Order–Inventory–Payment, hợp đồng dữ liệu nên có các trường:

| Trường | Mục đích |
| --- | --- |
| **eventId** | Chống xử lý trùng cùng sự kiện |
| **orderId / aggregateId** | Định danh thực thể nghiệp vụ và partition key |
| **sagaId / correlationId** | Nối log, command và sự kiện của cùng một workflow |
| **eventType, schemaVersion** | Chọn handler và diễn giải phiên bản payload |
| **aggregateVersion / sequence** | Phát hiện sự kiện cũ hoặc sai thứ tự |
| **occurredAt** | Phân tích độ trễ; không dùng một mình để bảo đảm thứ tự |
| **causationId** | Truy ngược sự kiện/lệnh gây ra bước hiện tại |

Một event ví dụ:

~~~json
{
  "eventId": "904e9e0e-1400-4cc9-9f68-7a184900d132",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "orderId": "3b3990c8-f692-466e-9fe3-90f6a1ab2a4b",
  "aggregateVersion": 1,
  "sagaId": "saga-2026-001",
  "correlationId": "req-a14f",
  "occurredAt": "2026-11-21T06:00:00Z",
  "payload": {
    "sku": "SKU-42",
    "quantity": 2
  }
}
~~~

Không đưa dữ liệu thanh toán nhạy cảm, access token hay PII không cần thiết vào sự kiện. **Trace ID** phục vụ distributed tracing có thể đi qua instrumentation; **correlationId/sagaId** là định danh nghiệp vụ cần thống nhất quy ước. Cả ba có thể liên kết để tra cứu nhưng không bắt buộc giống nhau.

Những chỉ số vận hành hữu ích:

- **Outbox backlog:** số sự kiện chưa phát, tuổi lớn nhất, số lần retry và sự kiện bị kẹt lease.
- **Consumer lag / DLQ:** độ trễ xử lý, lỗi deserialize, message đầu độc và số lần xử lý trùng.
- **Saga duration:** thời gian từ PENDING đến CONFIRMED/CANCELLED; số saga quá SLA.
- **Compensation failures:** bước bù trừ lỗi, trạng thái chờ xử lý thủ công và kết quả đối soát.
- **Business consistency checks:** đơn CONFIRMED nhưng thiếu payment authorization, đơn CANCELLED vẫn giữ tồn, hoặc event đã phát nhưng không được downstream xác nhận.

Không chỉ đo HTTP 200/500: một request API có thể trả 202 thành công trong khi Saga mắc kẹt sau đó. Dashboard và cảnh báo phải nhìn theo toàn bộ vòng đời nghiệp vụ.

## 11. Kiểm thử các ranh giới lỗi thực tế

Để kiểm thử đúng tính chất giao dịch, nên có các bài test sau:

1. **Local rollback:** trong một DB transaction, cố tình gây exception sau khi ghi order nhưng trước khi ghi item; xác minh không có bản ghi nào commit.
2. **Outbox atomicity:** nếu ghi outbox lỗi, order cũng không commit; nếu commit thành công, cả order và outbox cùng hiện diện.
3. **Publisher crash:** publish thành công rồi giả lập crash trước khi cập nhật outbox; sau restart event được gửi lại và consumer chỉ sinh một tác động nghiệp vụ.
4. **Consumer redelivery:** giao cùng eventId nhiều lần, kể cả nhiều consumer chạy đồng thời; constraint/inbox ngăn bản ghi nghiệp vụ bị nhân đôi.
5. **HTTP uncertain outcome:** Payment Service xử lý xong rồi client timeout; retry cùng idempotency key không tạo giao dịch thu tiền thứ hai.
6. **Compensation:** thanh toán bị từ chối sau khi kho đã giữ hàng; hệ thống chuyển trạng thái, gửi lệnh release và giải phóng đúng lượng tồn; gửi release lặp vẫn an toàn.
7. **Out-of-order events:** event version cũ đến sau version mới; consumer không ghi đè trạng thái mới bằng trạng thái cũ.
8. **Broker/DB downtime:** quan sát backlog, retry backoff, DLQ và khả năng phục hồi mà không cần sửa tay từng record.
9. **XA failure injection** nếu dùng 2PC: dừng một participant giữa prepare/commit; kiểm tra log coordinator, recovery và transaction in-doubt.

Spring Boot có thể dùng integration test với database và broker thật qua Testcontainers, kết hợp các fake server cho HTTP timeout/response loss. Khi dùng test double, cần nhớ mock HTTP thành công không kiểm chứng được việc broker ack, DB commit hay network redelivery ở production. Việc kiểm thử **failure window giữa hai tài nguyên** mới phơi bày đúng rủi ro của phân tán.

## 12. Những nhầm lẫn thường gây sự cố

**“Chỉ cần @Transactional là an toàn cả WebClient và message broker.”** Sai: transaction Spring chỉ quản lý các resource thật sự tham gia transaction manager tương ứng. Một HTTP service bên ngoài vẫn có thể đã commit.

**“Có distributed transaction thì luôn dùng 2PC.”** Không phải mọi resource hỗ trợ XA; Saga là một hình thức phối hợp giao dịch nghiệp vụ phân tán với bảo đảm khác.

**“Saga rollback như một DB transaction.”** Compensation là hành động nghiệp vụ mới. Refund không xóa dấu vết đã charge; người dùng có thể đã thấy trạng thái trung gian.

**“Eventual consistency tức là muốn trễ bao lâu cũng được.”** Nếu không có SLA hội tụ, monitoring, retry và đối soát, không có cơ sở kiểm chứng hệ thống đang hoạt động đúng.

**“Transactional outbox đảm bảo exactly-once delivery.”** Publisher có thể gửi lại khi chết sau broker ack; cần eventId, idempotent consumer và transaction local ở phía nhận.

**“Timeout nghĩa là yêu cầu chưa chạy.”** Timeout chỉ nói rằng bên gọi không nhận được kết quả đúng hạn. Kết quả remote có thể đã commit, cần lookup hoặc retry idempotent.

**“Gửi lại cùng correlation ID sẽ chống ghi trùng.”** Correlation ID để đối chiếu luồng; **idempotency key** để nhận diện cùng một yêu cầu có side effect; **eventId** để chống xử lý trùng cùng sự kiện.

**“Thêm hàng đợi là đủ để đảm bảo eventual consistency.”** Broker không tự sửa business invariant, event sai thứ tự, message vào DLQ, hoặc bù trừ thất bại. Cần state machine và quy trình reconciliation.

## 13. Quy trình ra quyết định cho kiến trúc tích hợp

~~~mermaid
flowchart TD
    A["Các thay đổi nằm trong một transactional resource?"] -->|Có| B["Local ACID transaction<br/>constraint + isolation + retry phù hợp"]
    A -->|Không| C["Tất cả resources cần atomic commit<br/>đều hỗ trợ XA và có thể phối hợp?"]
    C -->|Có, và yêu cầu atomic cao| D["Đánh giá JTA/XA/2PC<br/>recovery + timeout + benchmark"]
    C -->|Không hoặc không phù hợp| E["Nghiệp vụ có thể dùng trạng thái trung gian<br/>và bước bù trừ?"]
    E -->|Có| F["Saga + local transactions<br/>outbox/inbox + idempotency"]
    E -->|Chưa| G["Thiết kế lại boundary/invariant<br/>hoặc thương lượng yêu cầu nghiệp vụ"]
    F --> H["Định nghĩa SLA hội tụ,<br/>observability và reconciliation"]
~~~

Trước khi chốt phương án, trả lời cụ thể:

1. **Invariant nào bắt buộc đúng ngay lập tức?** Nếu “không bao giờ bán quá số lượng còn lại” là invariant cứng, việc giữ chỗ tồn phải được bảo vệ cục bộ tại dịch vụ kho bằng transaction/constraint hoặc thuật toán đồng thời chính xác.
2. **Hệ thống nào là nguồn sự thật?** Không để hai dịch vụ độc lập tự quyết định đồng thời về cùng một quyền sở hữu dữ liệu.
3. **Có trạng thái trung gian hợp lệ không?** Nếu có, công khai rõ cho API/client thay vì báo CONFIRMED quá sớm.
4. **Khi một bước thất bại sau commit sẽ làm gì?** Retry idempotent, compensation, chuyển trạng thái NEEDS_REVIEW hay dừng để đối soát.
5. **Phục hồi sau process crash như thế nào?** Tình trạng job, outbox, Saga state và pending task phải tồn tại bền vững.
6. **Làm sao chứng minh hệ thống hội tụ?** Dựa vào metric, SLA, DLQ, reconcile job và bài kiểm thử inject lỗi.

## 14. Tóm tắt theo ví dụ đặt hàng

Giả sử người dùng đặt hai sản phẩm:

- **Trong Order Service:** ghi **orders** và **outbox_event** trong một **local transaction**. Hai bảng cùng commit hoặc cùng rollback.
- **Giữa Order–Inventory–Payment:** các hệ thống có DB riêng, không có transaction XA chung qua REST. Một **Saga** phối hợp giữ hàng, thanh toán và xác nhận đơn; lỗi sau khi giữ hàng có thể cần **release stock**.
- **Trong khoảng chờ:** Order có thể là **PENDING**, Inventory là **RESERVED**, Payment là **PROCESSING**. Đây là **eventual consistency có chủ đích**, với giới hạn thời gian mong đợi và cơ chế xử lý khi không hội tụ.
- **Qua broker:** publisher outbox có thể phát lại cùng event, consumer lưu **eventId** để chống xử lý trùng; các lệnh tạo đơn/thu tiền dùng idempotency key phù hợp.
- **Khi gặp lỗi:** theo dõi trạng thái Saga và correlation ID, không suy đoán trạng thái remote chỉ từ timeout.

**Điểm cần nhớ:** local transaction cho tính nguyên tử **trong một ranh giới commit**; XA/2PC cố phối hợp commit **giữa những tài nguyên hỗ trợ**; Saga phối hợp **nhiều giao dịch cục bộ bằng trạng thái và bù trừ**; eventual consistency mô tả **độ trễ và điều kiện hội tụ** của toàn luồng. Trong Spring Boot Integration, thiết kế tốt bắt đầu từ việc xác định đúng từng ranh giới, sau đó bổ sung outbox, idempotency, retry, kiểm thử sự cố và khả năng quan sát.

## Tài liệu tham khảo

- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework Reference — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/)
- [Microservices.io — Pattern: Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
- [Microservices.io — Pattern: Saga](https://microservices.io/patterns/data/saga.html)
