# Transactional resource và message channel trong Spring Integration

## 1. Câu hỏi mở đầu: transaction đang bảo vệ cái gì?

Giả sử ứng dụng xử lý một đơn đặt hàng:

1. Lưu bản ghi `orders` vào PostgreSQL.
2. Đưa thông điệp `ReserveInventory` vào một `MessageChannel` của Spring Integration.
3. Consumer lấy thông điệp, trừ tồn kho trong database rồi hoàn tất việc xử lý.

Nếu transaction tạo đơn hàng rollback, liệu message ở bước 2 có biến mất? Nếu consumer ghi tồn kho thất bại, message đã lấy khỏi channel có được đưa lại để retry? **Không thể trả lời chỉ bằng tên `MessageChannel` hoặc sự hiện diện của `@Transactional`.**

Phải biết **transactional resource** nào thực sự tham gia giao dịch:

- Với `DirectChannel`, bản thân kênh chỉ chuyển thông điệp đồng bộ; những JDBC handler downstream *có thể* tham gia transaction của caller.
- Với `QueueChannel` mặc định dùng bộ nhớ, enqueue/dequeue không trở thành thao tác JDBC transactional chỉ vì bên ngoài có `@Transactional`.
- Với `QueueChannel` sử dụng **transactional JDBC message store**, việc lưu hoặc lấy message *có thể* tham gia cùng một database transaction với dữ liệu nghiệp vụ.
- Với JMS, RabbitMQ, Kafka hay một external API, nguồn message có transaction/ACK riêng; `DataSourceTransactionManager` không tự quản lý những tài nguyên đó.

Bài **Transactional resource và message channel** thuộc chương *Transactional messaging* của module `SPRING_INTEGRATION_PATTERN`. Mục tiêu là xây dựng Enterprise Integration Patterns (Router, Filter, Transformer, Splitter, Aggregator, Gateway...) ít phụ thuộc, có khả năng mở rộng, retry và xử lý lỗi rõ ràng **mà không hiểu sai ranh giới transaction**.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt *message channel*, *message store*, *transaction manager* và *transactional resource*.
2. Đánh giá hiệu lực rollback theo từng kiểu `DirectChannel`, `ExecutorChannel`, `QueueChannel` và persistent channel.
3. Cấu hình một `QueueChannel` với `JdbcChannelMessageStore` và một transactional poller trong bối cảnh dùng PostgreSQL.
4. Thiết kế trường hợp send cùng transaction tạo đơn và receive cùng transaction cập nhật nghiệp vụ.
5. Phân biệt resource-local transaction với transaction phối hợp liên tài nguyên; xác định lúc nào cần outbox, inbox và idempotent consumer.
6. Kiểm thử những tình huống crash, rollback, redelivery, retry, error channel và xử lý phân nhánh.

## 2. Bốn thành phần phải tách bạch

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Message** | Mang `payload` và `headers` đi qua flow. | `Message<ReserveInventory>`, `eventId`, `correlationId`. |
| **MessageChannel** | Quy định cách chuyển giao từ người gửi sang consumer/handler. | `DirectChannel`, `ExecutorChannel`, `QueueChannel`, `PublishSubscribeChannel`. |
| **Resource** | Nơi lưu trạng thái hoặc tạo tác dụng phụ, có/không hỗ trợ transaction. | PostgreSQL, JMS session, Kafka producer, bộ nhớ, hệ thống HTTP. |
| **Transaction manager** | Mở, commit, rollback transaction đối với những resource được cấu hình tham gia. | `JdbcTransactionManager`, `DataSourceTransactionManager`, `JmsTransactionManager`, JTA manager. |

**Điểm quan trọng:** Channel là cơ chế trao đổi thông điệp. Resource là thứ có thể thật sự *commit/rollback*. Một flow có thể có nhiều channel nhưng chỉ một transaction trên một DB; ngược lại, hai channel nhìn tương tự có thể ghi vào hai resource khác nhau và **không** commit nguyên tử cùng nhau.

### Một hình dung đơn giản

~~~mermaid
flowchart LR
    G["Gateway"] --> DC["DirectChannel"]
    DC --> A["Service Activator"]
    A --> DB[("Business PostgreSQL")]
    DC --> Q["QueueChannel"]
    Q --> MS[("MessageStore")]
    MS --> P["Transactional poller"]
    P --> H["Handler"]
    H --> DB
    T["Transaction manager"] -. "quản lý resource đã enlist" .-> DB
    T -. "nếu store cùng DB/manager" .-> MS
~~~

Trong một transaction JDBC, `JdbcTemplate` thường lấy connection được Spring gắn với thread. Nếu `JdbcChannelMessageStore` dùng **cùng datasource và transaction manager tương thích**, thao tác store có thể tham gia physical transaction đó. Nếu message store dùng datasource khác, không thể mặc định cả hai ghi commit nguyên tử.

## 3. “Transactional channel” không phải thuộc tính của mọi MessageChannel

Spring Integration định nghĩa kênh theo hai nhóm giao tiếp chính:

- **`SubscribableChannel`**: các handler đăng ký nhận message được channel dispatch. Thường gặp `DirectChannel`, `ExecutorChannel`, `PublishSubscribeChannel`.
- **`PollableChannel`**: consumer chủ động lấy message qua `receive()`. Thường gặp `QueueChannel`, `PriorityChannel`, `RendezvousChannel`.

Cùng là channel nhưng chúng khác nhau về thread, lưu trữ và khả năng rollback của thao tác đưa vào/lấy ra.

| Channel | Cơ chế hoạt động | Quan hệ với transaction |
| --- | --- | --- |
| `DirectChannel` | Dispatch handler đồng bộ trong thread gửi. | Cho phép downstream JDBC handler dùng transaction hiện hành, nhưng kênh không tự cung cấp lưu trữ durable. |
| `PublishSubscribeChannel` không executor | Dispatch subscriber đồng bộ. | Các handler có thể tham gia transaction hiện hành; external side effect ở subscriber trước không nhất thiết hoàn tác được. |
| `ExecutorChannel` | Bàn giao xử lý qua `TaskExecutor`, thường sang thread khác. | Không tự truyền transaction thread-bound; sender và worker có boundary riêng. |
| `QueueChannel` mặc định | Lưu trong queue RAM, consumer poll sau. | DB rollback không tự đảo enqueue/dequeue trong RAM; restart có thể mất message. |
| `PriorityChannel` mặc định | Queue RAM lấy theo mức ưu tiên. | Có đặc tính durability/transaction tương tự queue RAM; ordering không phải transaction. |
| `RendezvousChannel` | Bàn giao trực tiếp qua cơ chế đồng bộ hóa giữa sender và receiver. | Đồng bộ thời điểm handoff không đồng nghĩa transaction chung giữa threads. |
| `QueueChannel` + transactional `ChannelMessageStore` | Lưu message trong resource như JDBC DB. | Store operation có thể được rollback nếu nó tham gia transaction được cấu hình đúng. |
| JMS/AMQP-backed channel hoặc inbound/outbound adapter | Dựa vào broker/session/ACK ngoài process. | Phụ thuộc cơ chế transaction, confirmation và acknowledgement của broker; không tự tham gia JDBC transaction. |

Việc `send()` trả về `true` chỉ có ý nghĩa theo hợp đồng channel: ví dụ đã dispatch thành công hoặc đã chấp nhận message vào queue. Nó **không phải bằng chứng chung** rằng handler bất đồng bộ đã commit DB hay broker đã xác nhận xử lý nghiệp vụ.

## 4. Vì sao cùng @Transactional nhưng hai QueueChannel cho kết quả khác nhau?

Giả sử có đoạn code:

~~~java
@Transactional
public void placeOrder(CreateOrder command) {
    jdbc.update(
            "INSERT INTO orders(order_id, state) VALUES (?, ?)",
            command.orderId(), "CREATED");

    boolean accepted = messageChannel.send(
            MessageBuilder.withPayload(
                    new ReserveInventory(
                            command.eventId(),
                            command.orderId(),
                            command.sku(),
                            command.quantity()))
                    .build());

    if (!accepted) {
        throw new IllegalStateException("Message channel rejected event");
    }
}
~~~

Đoạn code chưa đủ thông tin để kết luận message sẽ tồn tại hay biến mất khi transaction rollback. Hãy thay từng implementation cho `messageChannel`:

### Phương án A: `QueueChannel(100)`

~~~java
@Bean("messageChannel")
PollableChannel messageChannel() {
    return new QueueChannel(100);
}
~~~

`send()` có thể đưa message vào RAM thành công. Sau đó transaction trên `orders` rollback, nhưng message trong queue **không tự bị xóa**; consumer có thể nhận một đơn hàng chưa được commit. Nếu process crash, queue RAM lại có thể mất message.

### Phương án B: `QueueChannel` với transactional JDBC message store

~~~text
BEGIN TX-A (business DB)
  INSERT orders
  INSERT message vào JDBC channel store (cùng DB/TX-A)
COMMIT hoặc ROLLBACK TX-A
~~~

Nếu hai lệnh insert dùng cùng physical DB transaction, cả **đơn hàng và bản ghi message trong store** commit hoặc rollback cùng nhau. Consumer không đọc message chưa commit khi dùng isolation phù hợp (chẳng hạn READ_COMMITTED).

### Phương án C: channel broker nằm ngoài transaction DB

~~~text
BEGIN TX-A (business DB)
  INSERT orders
  PUBLISH message tới broker (resource khác)
  ROLLBACK TX-A
~~~

Broker có thể đã nhận message dù database rollback. Đặt lời publish trong `@Transactional` **không** tự đưa broker vào JDBC transaction. Nếu broker/session có local transaction riêng, vẫn phải xác định thứ tự commit giữa hai resource.

### Ma trận ngắn

| Resource của channel | DB rollback của caller | App crash | Phù hợp với |
| --- | --- | --- | --- |
| RAM queue | Không mặc định rollback enqueue/dequeue. | Có thể mất message. | Handoff nội bộ chấp nhận mất dữ liệu. |
| JDBC store **cùng transaction** | Store insert/remove có thể rollback cùng DB. | Bản ghi đã commit có thể được khôi phục. | Luồng DB-centric cần atomicity với business rows. |
| JDBC store **khác datasource/transaction** | Không tự rollback cùng business DB. | Có thể vẫn bền vững riêng. | Cần thiết kế dual write/idempotency. |
| JMS/AMQP/Kafka | Phụ thuộc resource/transaction riêng của broker. | Có thể bền vững theo cấu hình broker. | Tích hợp giữa process, mở rộng consumer. |

## 5. Cấu hình JDBC-backed QueueChannel với Spring Integration

Một persistent queue trong Spring Integration có thể dùng `JdbcChannelMessageStore` từ module `spring-integration-jdbc`. Store này lưu message vào các bảng do Spring Integration cung cấp DDL; với PostgreSQL, nên cấu hình query provider tương ứng.

### 5.1. Các điều kiện tiên quyết

- Ứng dụng có `DataSource` trỏ tới PostgreSQL và một `PlatformTransactionManager` áp dụng cho datasource đó.
- Đã thêm Spring Integration JDBC và tạo schema/tables dành cho JDBC channel message store theo **script chính thức của phiên bản đang dùng**.
- Producer/consumer đồng ý về region và group ID của queue; tên nhóm không va chạm với queue khác.
- Payload và headers phải tương thích với cơ chế serialization/message conversion của store; giữ định danh nghiệp vụ ổn định qua khôi phục.
- Không tự định nghĩa schema queue tối giản thay thế bảng nội bộ rồi kỳ vọng `JdbcChannelMessageStore` hoạt động.

Để chạy các ví dụ nghiệp vụ bên dưới, có thể tạo riêng hai bảng ứng dụng (không thay thế schema của Spring Integration):

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    state VARCHAR(24) NOT NULL
);

CREATE TABLE inventory (
    sku VARCHAR(80) PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);
~~~

### 5.2. Payload cho ví dụ

~~~java
record CreateOrder(
        String eventId,
        String orderId,
        String sku,
        int quantity) {}

record ReserveInventory(
        String eventId,
        String orderId,
        String sku,
        int quantity) implements java.io.Serializable {}
~~~

`Serializable` minh họa một lựa chọn để lưu payload với serializer mặc định; nếu dùng JSON hoặc custom converter, cần bảo đảm schema evolution và khả năng đọc message của các phiên bản ứng dụng đang triển khai.

### 5.3. Java configuration

~~~java
@Configuration
@EnableIntegration
class DurableQueueConfig {

    @Bean
    JdbcChannelMessageStore orderChannelStore(DataSource dataSource) {
        JdbcChannelMessageStore store =
                new JdbcChannelMessageStore(dataSource);
        store.setChannelMessageStoreQueryProvider(
                new PostgresChannelMessageStoreQueryProvider());
        store.setRegion("order-service");
        return store;
    }

    @Bean("pendingReservations")
    PollableChannel pendingReservations(
            JdbcChannelMessageStore orderChannelStore) {
        return new QueueChannel(
                new MessageGroupQueue(
                        orderChannelStore, "pending-reservations"));
    }
}
~~~

Đây là Java configuration minh họa cách nối `JdbcChannelMessageStore` với `MessageGroupQueue`, vốn là một implementation `BlockingQueue` dựa trên `MessageGroupStore`. Tên lớp và phương thức phải được kiểm tra với **Spring Integration version** thực tế khi đưa vào dự án.

**Cần hiểu vai trò của `region` và `groupId`:**

- `region` phân vùng dữ liệu giữa những ứng dụng/nhóm channel cùng dùng bảng lưu message.
- `groupId` xác định nhóm message thuộc queue logic đó.
- Các node chia sẻ cùng durable queue phải thống nhất định danh, còn các queue không liên quan cần tách biệt để tránh đọc chéo message.

Đừng cấu hình `capacity=100` của queue RAM rồi tưởng đây là giới hạn dung lượng của JDBC-backed queue. Với message store, giới hạn thông thường do policy lưu trữ và tài nguyên DB quyết định; cần giám sát backlog, dung lượng bảng, index và tốc độ polling.

### 5.4. Vì sao Java bean `QueueChannel` chưa tự tạo transaction?

`new QueueChannel(new MessageGroupQueue(...))` chỉ thay **nơi lưu** của queue. Transaction hoạt động khi Spring mở transaction và các thao tác JDBC của store dùng datasource/connection đang tham gia transaction.

Nói cách khác:

> **Persistent** là khả năng lưu message qua restart; **transactional** là khả năng store operation cùng commit hoặc rollback với transaction liên quan. Hai thuộc tính có quan hệ nhưng không đồng nhất.

Việc gửi message vào JDBC store *ngoài* `@Transactional` có thể được database auto-commit ngay. Việc nhận từ JDBC-backed queue mà không có transactional poller có thể xóa message khỏi store trước khi business handler lỗi. Độ bền của store **không thay thế** transaction boundary đúng.

## 6. Producer: ghi dữ liệu và gửi message trong một JDBC transaction

Với `pendingReservations` ở phần 5, có thể viết:

~~~java
@Service
class OrderCommandService {
    private final JdbcTemplate jdbc;
    private final PollableChannel pendingReservations;

    OrderCommandService(
            JdbcTemplate jdbc,
            @Qualifier("pendingReservations")
            PollableChannel pendingReservations) {
        this.jdbc = jdbc;
        this.pendingReservations = pendingReservations;
    }

    @Transactional
    public void place(CreateOrder command) {
        writeAndEnqueue(command);
    }

    @Transactional
    public void placeThenFail(CreateOrder command) {
        writeAndEnqueue(command);
        throw new IllegalStateException("Simulated rollback");
    }

    private void writeAndEnqueue(CreateOrder command) {
        jdbc.update(
                "INSERT INTO orders(order_id, state) VALUES (?, ?)",
                command.orderId(), "CREATED");

        ReserveInventory event = new ReserveInventory(
                command.eventId(),
                command.orderId(),
                command.sku(),
                command.quantity());

        boolean accepted = pendingReservations.send(
                MessageBuilder.withPayload(event)
                        .setHeader("businessEventId", command.eventId())
                        .build());

        if (!accepted) {
            throw new IllegalStateException("Durable channel rejected event");
        }
    }
}
~~~

Hai phương thức public minh họa tình huống thành công và rollback, dùng chung helper ghi/gửi **không mở transaction riêng** và đều kiểm tra kết quả channel. `placeThenFail` không gọi `this.place(...)` rồi phụ thuộc vào proxy của một lời gọi nội bộ; transaction do interceptor của chính `placeThenFail` mở.

Giả sử `orders` và `JdbcChannelMessageStore` dùng cùng `DataSource` và transaction manager:

~~~mermaid
sequenceDiagram
    participant API as OrderCommandService
    participant DB as PostgreSQL
    participant Q as JDBC-backed QueueChannel
    API->>DB: BEGIN TX-A
    API->>DB: INSERT orders (TX-A)
    API->>Q: send(ReserveInventory)
    Q->>DB: INSERT channel message (TX-A)
    alt Thành công
        API->>DB: COMMIT TX-A
        Note over DB,Q: Đơn + message cùng bền vững
    else Lỗi trước commit
        API->>DB: ROLLBACK TX-A
        Note over DB,Q: Không còn đơn hay message chưa commit
    end
~~~

**Caveat:** Kết luận nguyên tử chỉ đúng khi store thực sự dùng **transactional resource giống business JDBC**. Nếu code gửi message thông qua `ExecutorChannel`, một listener network hoặc một datasource riêng trước khi tới store, tính nguyên tử nêu trên không còn được bảo đảm.

## 7. Consumer: transactional poller và rollback thao tác lấy message

Khía cạnh thứ hai của transactional channel là **receive**. Tài liệu Spring Integration mô tả rằng một persistent `QueueChannel` với transactional store có thể hoàn tác việc loại message khỏi store nếu poller xử lý trong transaction và transaction đó rollback.

### Java DSL

~~~java
@Configuration
@EnableIntegration
class ReservationConsumerFlow {

    @Bean
    IntegrationFlow reservationFlow(
            PlatformTransactionManager transactionManager,
            InventoryHandler inventoryHandler) {
        return IntegrationFlow.from(
                        "pendingReservations",
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(1_000)
                                        .maxMessagesPerPoll(1)
                                        .transactional(transactionManager)))
                .handle(inventoryHandler, "reserve")
                .get();
    }
}
~~~

Handler dùng cùng PostgreSQL:

~~~java
@Service
class InventoryHandler {
    private final JdbcTemplate jdbc;

    InventoryHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void reserve(ReserveInventory event) {
        int count = jdbc.update("""
                UPDATE inventory
                   SET available = available - ?
                 WHERE sku = ? AND available >= ?
                """,
                event.quantity(), event.sku(), event.quantity());

        if (count != 1) {
            throw new IllegalStateException(
                    "Cannot reserve stock: " + event.sku());
        }
    }
}
~~~

Ở đây, nếu transaction manager của poller quản lý cùng datasource với message store và business data, việc **dequeue** và cập nhật `inventory` có thể nằm trong **một physical JDBC transaction**:

~~~mermaid
sequenceDiagram
    participant Poller as Transactional poller
    participant Store as JdbcChannelMessageStore
    participant Handler as InventoryHandler
    participant DB as PostgreSQL
    Poller->>DB: BEGIN TX-P
    Poller->>Store: receive()
    Store->>DB: Lấy/xóa message trong TX-P
    Poller->>Handler: reserve(event)
    Handler->>DB: UPDATE inventory (TX-P)
    alt Handler thành công
        Poller->>DB: COMMIT TX-P
        Note over DB,Store: Thay đổi tồn kho và xóa message cùng commit
    else Handler ném lỗi
        Poller->>DB: ROLLBACK TX-P
        Note over DB,Store: UPDATE rollback; message không bị xóa vĩnh viễn
    end
~~~

### Điều kiện để rollback receive làm message xuất hiện lại

1. **Store transactional**: thao tác lấy/xóa message thực thi bằng JDBC resource hỗ trợ rollback.
2. **Poller transaction**: transaction advice bao quanh cả receive và downstream synchronous handler.
3. **Đúng transaction manager/datasource**: thao tác store và business update tham gia transaction tương thích, thường là cùng datasource.
4. **Lỗi được truyền ra**: exception phải đến advice và thỏa rollback rules; không bị error flow xử lý rồi return như một thành công.
5. **Không có async boundary trước business update**: nếu poller chỉ gửi sang executor và kết thúc, việc xóa message có thể commit trong khi worker chưa xử lý.

Với `QueueChannel(100)` RAM, điều kiện (1) không tồn tại: dù poller mở JDBC transaction, thao tác dequeue từ memory không tự được rollback. Với store JDBC nhưng handler chạy trên datasource khác, rollback có thể bảo vệ **chỉ thao tác store**, còn business DB đã commit riêng hoặc ngược lại.

### Một giới hạn khác: redelivery không đồng nghĩa exactly-once

Nếu xử lý nghiệp vụ gửi HTTP hoặc cập nhật một database độc lập trước khi transaction store rollback, message có thể được nhận lại trong khi side effect bên ngoài đã hoàn tất. Consumer **vẫn cần idempotency** cho mọi hoạt động ngoài resource transaction chung.

## 8. Khi message store dùng database khác business database

Xét hai datasource:

~~~text
DataSource A -> PostgreSQL "business"
DataSource B -> PostgreSQL "integration-message-store"
~~~

Một `DataSourceTransactionManager` đang quản lý A **không** tự điều khiển commit/rollback của B. Ngay cả khi cả hai là PostgreSQL hoặc chạy trên cùng cluster, khác connection/resource/transaction scope vẫn có nguy cơ **dual write**.

| Thứ tự ghi | Crash/failure window | Hệ quả |
| --- | --- | --- |
| Ghi business A rồi ghi channel store B | Business A commit, store B chưa ghi/commit. | Có đơn hàng nhưng thiếu message. |
| Ghi store B rồi commit business A | Store B commit, business A rollback. | Message của đơn chưa tồn tại. |
| Handler commit business B rồi dequeue commit trên store A | Worker sập giữa hai commit. | Message bị giao lại, có thể xử lý trùng. |
| Dequeue commit trên store A rồi business B rollback | Worker sập/DB lỗi sau dequeue. | Mất message nếu source không redeliver. |

### Chọn cách phối hợp

- **Một DB transaction**: nếu phù hợp kiến trúc, lưu business row và durable intent/message trong cùng database với một transaction manager; khi ấy bảo đảm nguyên tử trong DB dễ hiểu và kiểm thử.
- **XA/JTA/2PC**: chỉ cân nhắc khi *tất cả* resource hỗ trợ transaction phối hợp, chấp nhận chi phí và đã thiết lập/test rõ failure semantics. Việc có hai `PlatformTransactionManager` không tự tạo global transaction.
- **Transactional outbox/inbox**: ghi intent/đã xử lý vào DB nghiệp vụ, chuyển message giữa service bằng cơ chế bền vững và idempotency. Đây là phương án thực tiễn khi nhiều tài nguyên không thể commit nguyên tử.
- **Saga/compensation**: nếu nhiều service đã commit riêng, lưu trạng thái workflow và thực thi nghiệp vụ bù trừ; không coi bù trừ là rollback của một transaction JDBC khác.

## 9. Resource riêng của JMS, AMQP và Kafka

Message broker có thể cung cấp durability, ACK và transaction semantics **khác** JDBC-backed message store.

| Công nghệ | Resource/điểm xác nhận | Điều cần hiểu |
| --- | --- | --- |
| **JMS** | JMS `Session`, session transaction hoặc acknowledgement do listener container quản lý. | `JmsTransactionManager` cho JMS local transaction, không tự làm JDBC business DB cùng atomic; session rollback có thể gây redelivery. |
| **RabbitMQ / AMQP** | Connection/channel, ACK/NACK/requeue, broker transaction hoặc publisher confirm tùy adapter. | Consumer ACK khác publisher confirm. Broker transaction không tự tham gia PostgreSQL transaction. |
| **Kafka** | Producer transaction, consumer offsets và việc commit offsets theo cấu hình. | Kafka transaction có thể hỗ trợ atomicity cho luồng Kafka-read→Kafka-write; không tự đưa JDBC DB vào Kafka transaction. |
| **JDBC MessageStore** | Database rows/transaction của datasource. | Send/dequeue có thể nằm trong DB transaction nếu store và handler dùng đúng resource/manager. |
| **Redis hoặc store NoSQL khác** | Phụ thuộc implementation store và cơ chế transaction của sản phẩm. | Không suy khả năng rollback dequeue chỉ từ từ "persistent"; cần kiểm chứng API/adapter cụ thể. |
| **HTTP/email/external API** | Remote side effect và response. | Một JDBC rollback không tự thu hồi email hay API request đã thực hiện. |

### Ví dụ JMS local transaction không bao hết business DB

~~~text
JMS listener nhận OrderPaid
  -> JDBC handler mở transaction và cập nhật orders
  -> JDBC COMMIT thành công
  -> JMS session COMMIT thất bại
  -> JMS có thể redeliver OrderPaid
~~~

JMS session transaction bảo vệ thao tác JMS của chính session. Nếu JDBC đã commit riêng, lần redelivery có thể lặp business effect. Phải dùng định danh sự kiện cố định và consumer idempotent. Tương tự, `@Transactional` trên JDBC handler không tự quyết định RabbitMQ ACK hoặc Kafka offset.

### Đừng nhầm “transactional broker” với “end-to-end exactly-once”

Một broker có thể cung cấp exactly-once hoặc transaction guarantee **trong phạm vi được tài liệu của nó định nghĩa**. Nhưng một hệ thống đi qua broker, database bên ngoài, email và HTTP không tự có một global transaction chỉ vì mọi thành phần đều hỗ trợ một dạng transaction cục bộ.

## 10. Propagation và thread quyết định resource nào được dùng

Với một handler Spring bean:

~~~java
@Transactional(propagation = Propagation.REQUIRED)
public void handle(ReserveInventory event) {
    int changed = jdbc.update("""
            UPDATE inventory
               SET available = available - ?
             WHERE sku = ? AND available >= ?
            """, event.quantity(), event.sku(), event.quantity());
    if (changed != 1) {
        throw new IllegalStateException("Unable to reserve inventory");
    }
}
~~~

`REQUIRED` tham gia transaction đang có ở thread hiện hành; nếu không có, nó mở transaction mới qua manager được chọn. Các propagation khác cần cân nhắc:

| Propagation | Ý nghĩa khi được gọi qua `DirectChannel` từ outer transaction | Nguy cơ trong flow |
| --- | --- | --- |
| `REQUIRED` | Tham gia physical transaction hiện tại. | Outer rollback kéo theo ghi JDBC của handler; exception bị catch có thể để lại rollback-only. |
| `REQUIRES_NEW` | Suspend outer, mở transaction độc lập. | Inner có thể commit dù outer rollback; resource store và business update có thể không còn atomic theo kỳ vọng. |
| `NESTED` | Có thể dùng savepoint khi manager hỗ trợ. | Inner không commit độc lập; không rollback side effect ngoài DB. |
| `MANDATORY` | Bắt buộc caller có transaction. | Có thể lỗi nếu handler chạy từ worker/executor không mang transaction. |
| `SUPPORTS` | Tham gia khi có, nếu không chạy không có actual transaction. | Không nên dùng khi bắt buộc store/dequeue atomic với business DB. |
| `NOT_SUPPORTED` | Suspend outer, chạy không có transaction. | Thao tác JDBC/store trong method có thể commit riêng và không rollback theo outer. |
| `NEVER` | Từ chối lời gọi có transaction. | Không phù hợp đường xử lý đòi hỏi transaction. |

### Cùng channel, khác kết quả vì đổi thread

~~~mermaid
flowchart LR
    S["Gateway / Poller có TX-A"] --> D{"Channel"}
    D -->|"DirectChannel"| H1["Handler trong thread A, có thể dùng TX-A"]
    D -->|"ExecutorChannel"| H2["Worker thread B, không tự có TX-A"]
    H1 --> DB[("Business DB")]
    H2 --> TB["Transaction B nếu handler mở"]
    TB --> DB
~~~

Với executor bất đồng bộ, poller có thể commit **dequeue từ durable store** ngay sau khi bàn giao task cho executor; worker gặp lỗi sau đó nhưng message đã bị xóa bền vững. Muốn xử lý async an toàn, cần một **durable handoff** hoặc thay đổi cách ACK/dequeue để chỉ hoàn tất sau điểm xử lý bền vững thực sự.

Một số `TaskExecutor` có thể thực thi inline, vì vậy phải xem cấu hình thật trước khi kết luận worker chắc chắn khác thread.

## 11. Error channel, retry và transactional resource

### Lỗi của handler đồng bộ

Khi `DirectChannel` dispatch handler đồng bộ và handler ném exception, lỗi thường có thể truyền về poller/listener/caller. Nếu transaction interceptor thấy exception phù hợp rollback rules, các thay đổi trên resource tham gia có thể rollback.

~~~java
@Transactional
public void process(ReserveInventory event) {
    jdbc.update("UPDATE inventory SET ...");
    throw new IllegalStateException("Simulated handler failure");
}
~~~

### Anti-pattern: bắt lỗi rồi hoàn tất bình thường

~~~java
public void processAndHideFailure(ReserveInventory event) {
    try {
        inventoryHandler.reserve(event);
    } catch (Exception ex) {
        log.error("Cannot reserve inventory", ex);
        // Nếu caller chỉ return, poller hoặc container có thể coi là success.
    }
}
~~~

Nếu source là JDBC-backed queue với transactional poller, một error handler trả về bình thường có thể khiến transaction poller **commit việc dequeue** mặc dù business handler chưa hoàn tất. Nếu nguồn là broker, listener có thể ACK. Hành vi cụ thể phụ thuộc rollback-only state và advice chain; đừng chỉ kiểm tra log lỗi rồi kết luận sẽ redeliver.

### Retry ngoài và trong transaction

~~~text
Retry bao ngoài transaction:
  attempt 1 -> BEGIN TX-1 -> receive/process -> ROLLBACK
  backoff
  attempt 2 -> BEGIN TX-2 -> receive/process -> COMMIT

Retry trong cùng transaction:
  BEGIN TX-A
    attempt 1 -> lỗi, TX-A có thể rollback-only
    attempt 2 -> handler chạy lại
  COMMIT cố gắng -> có thể UnexpectedRollbackException
~~~

Với transaction đã đánh dấu rollback-only, retry cùng physical transaction không bảo đảm khả năng commit. Khi cần retry toàn đơn vị xử lý JDBC, thường nên có **transaction mới cho từng attempt**, kiểm tra thứ tự retry advice và transaction advice thực tế.

### DLQ và poison message

Nếu một message không hợp lệ bị rollback trở lại JDBC store mãi, một poller có thể liên tục nhận lại **cùng poison message**. Cần chính sách giới hạn attempt, backoff, quarantine/dead-letter và cách phát lại sau khi sửa dữ liệu. Nếu chuyển message lỗi sang một **DB table** trong transaction mới, không được vô tình commit xóa message gốc trong lúc việc lưu lỗi thất bại.

Khi giao việc cho error channel, hãy xác định:

- Lỗi là **message lỗi có thể chấp nhận và lưu bền vững** hay là tín hiệu phải rollback?
- Error handler chạy trong cùng thread và transaction hay đã qua executor khác?
- Đưa vào DLQ có chính sách duplicate và retry riêng hay không?
- Khi error flow return bình thường, poller hoặc broker sẽ coi delivery là thành công không?

## 12. Mô hình inbox/outbox khi không dùng chung transaction resource

Nếu nguồn inbound và business DB không chia sẻ một physical transaction, một mô hình thường dùng là **at-least-once delivery + idempotent consumer**. Nếu business DB phải phát event mới, thêm transactional outbox.

### Schema minh họa

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE outbox_events (
    event_id VARCHAR(100) PRIMARY KEY,
    aggregate_id VARCHAR(100) NOT NULL,
    payload_json TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

### Idempotent handler

~~~java
@Service
class IdempotentInventoryHandler {
    private final JdbcTemplate jdbc;

    IdempotentInventoryHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void reserve(ReserveInventory event) {
        int marked = jdbc.update("""
                INSERT INTO processed_events(consumer_name, event_id)
                VALUES (?, ?)
                ON CONFLICT (consumer_name, event_id) DO NOTHING
                """, "inventory", event.eventId());

        if (marked == 0) {
            return; // Message đã commit ở lần xử lý trước.
        }

        int changed = jdbc.update("""
                UPDATE inventory
                   SET available = available - ?
                 WHERE sku = ? AND available >= ?
                """, event.quantity(), event.sku(), event.quantity());

        if (changed != 1) {
            throw new IllegalStateException("Cannot reserve stock");
        }
        // Nếu cần publish OrderReserved, ghi outbox row tại đây
        // bằng cùng JdbcTemplate/transaction.
    }
}
~~~

Đoạn SQL dùng cú pháp PostgreSQL. `PRIMARY KEY` bảo vệ khỏi hai worker đồng thời xử lý cùng `eventId`; dấu đã xử lý và business update phải cùng transaction. Nếu nghiệp vụ thất bại, rollback xóa cả marker lẫn thay đổi tồn kho. Nếu message bị giao lại sau commit nhưng trước ACK, lần sau nhận ra duplicate và tránh trừ kho thêm.

### Vì sao có thể cần cả inbox lẫn outbox?

~~~mermaid
sequenceDiagram
    participant Broker as Inbound broker
    participant C as Consumer
    participant DB as Business DB
    participant Relay as Outbox relay
    participant Downstream as Outbound broker
    Broker->>C: Deliver eventId=E-42
    C->>DB: BEGIN
    C->>DB: INSERT processed_events(E-42) nếu chưa có
    C->>DB: UPDATE business rows
    C->>DB: INSERT outbox_events(newEventId)
    C->>DB: COMMIT
    C-->>Broker: ACK theo policy
    Relay->>DB: Đọc pending outbox
    Relay->>Downstream: Publish newEventId
    Downstream-->>Relay: Confirmation
    Relay->>DB: Mark SENT (có thể retry)
~~~

Inbox giải quyết trường hợp **redelivery đầu vào**. Outbox bảo đảm **ý định gửi đầu ra** được commit cùng business rows. Nếu relay publish thành công rồi sập trước lúc đánh dấu `SENT`, nó có thể publish lặp: consumer downstream phải idempotent.

**Không nhầm outbox với JDBC channel store:** cả hai đều có thể lưu message trên database và tham gia transaction; tuy nhiên outbox là một *pattern* với bảng sự kiện, relay, trạng thái publish và khả năng tích hợp liên service. JDBC-backed `QueueChannel` là implementation của một channel nội bộ dựa trên `MessageStore`. Chọn theo bài toán, không chỉ theo tên "durable".

## 13. Router, Filter, Splitter và Aggregator với transactional resource

Một flow thực tế có thể rẽ nhánh:

~~~mermaid
flowchart LR
    G["Gateway"] --> T["Transformer"]
    T --> R{"Router"}
    R --> F["Filter"]
    R --> S["Splitter"]
    F --> D["DirectChannel -> DB handler"]
    S --> Q["Persistent QueueChannel"]
    Q --> P["Transactional poller"]
    P --> W["Worker / handler"]
    D --> A["Aggregator"]
    W --> A
~~~

Ở mỗi bước, hãy đánh dấu **resource** và **boundary**:

- **Transformer/Filter** chạy đồng bộ có thể nằm trong transaction hiện hành. Filter loại một message thường là kết quả hợp lệ, không tự kích hoạt rollback.
- **Router** có thể chuyển từ channel đồng bộ sang persistent queue. Khi send vào store dùng cùng DB transaction, bản ghi queue có thể commit/rollback cùng nghiệp vụ; nếu dùng store khác, đó là dual write.
- **Splitter** tạo các message con. Nếu tất cả ghi vào cùng transactional store của một transaction, thao tác enqueue có thể commit nguyên tử trong phạm vi DB đó; **xử lý** các message con ở worker sau đó là transaction khác.
- **Aggregator** cần `correlationId`, sequence/release strategy và message store bền vững nếu phải phục hồi sau restart. Persistent aggregator state không mặc định cùng transaction với mọi consumer branch; cần xem store và manager riêng.
- **Error channel** thường là một flow khác; nếu lỗi bị tiêu thụ trước khi poller commit, có thể khiến source coi message đã xử lý, bất kể business side effect có đầy đủ hay không.
- **Gateway** trả lời thành công không đồng nghĩa các nhánh async đã hoàn tất; cần contract phản hồi “accepted” khác với “processed”.

### Event ID không phải message ID

| Định danh | Chức năng | Dùng để chống xử lý trùng? |
| --- | --- | --- |
| `MessageHeaders.ID` | Nhận diện một message instance trong Spring Integration. | Không nên phụ thuộc duy nhất: message có thể được tái tạo với ID khác. |
| `correlationId` | Nhóm message thuộc một workflow/order. | Dùng để ghép nhánh, không mặc định là unique event ID. |
| `sequenceNumber` | Thứ tự của message con sau Splitter. | Không đại diện một lần thực thi nghiệp vụ toàn cục. |
| `eventId`/`commandId` nghiệp vụ | Định danh công việc/sự kiện ổn định qua retry. | Thường là khóa phù hợp cho idempotent consumer. |

Transaction bảo vệ resource, còn correlation/idempotency giúp giải quyết **trạng thái phân tán** mà một transaction cục bộ không bao trùm được.

## 14. Những lỗi thiết kế thường gặp

### Lỗi 1 — “Có @Transactional nên QueueChannel trong RAM được rollback”

Sai. `@Transactional` chỉ quản lý transaction của những tài nguyên đã tham gia. Enqueue/dequeue trong queue RAM không tự rollback theo JDBC.

### Lỗi 2 — “Persistent QueueChannel thì chắc chắn redeliver”

Chưa đủ. Nếu dequeue được commit **trước** khi handler xử lý xong hoặc poller không có transaction, message có thể bị xóa khỏi store khi handler thất bại. Phải kiểm tra transaction scope của **cả receive và downstream handler**.

### Lỗi 3 — “Hai JDBC datasource nghĩa là một transaction”

Không mặc định. Cùng framework/driver không đảm bảo cùng physical transaction. Kiểm tra datasource, connection, transaction manager và nếu thật sự cần, cơ chế phối hợp transaction.

### Lỗi 4 — “ExecutorChannel giữ JDBC transaction của caller”

Thông thường không. Transaction imperative là thread-bound. Async boundary tạo consumer transaction riêng; cần durable handoff và idempotency.

### Lỗi 5 — “Gửi Kafka/JMS trong @Transactional JDBC là nguyên tử”

Không mặc định. Resource-local transaction của broker và database là hai phạm vi. Có thể có message của DB rollback, hoặc DB commit nhưng thiếu message; dùng outbox khi cần bảo đảm ý định gửi.

### Lỗi 6 — “Đã rollback thì không thể duplicate”

Không đúng nếu side effect ở resource khác đã commit. Ngoài ra consumer có thể commit DB nhưng source chưa ACK rồi được redeliver. Idempotency vẫn bắt buộc ở boundary phù hợp.

### Lỗi 7 — “Thông điệp trong JDBC store luôn là FIFO và vô hạn throughput”

Thứ tự phụ thuộc query provider, ưu tiên và concurrency. PostgreSQL-backed store còn cần quản lý locking, index, serialization, backlog và dung lượng bảng. Với khối lượng message lớn, broker chuyên dụng có thể phù hợp hơn DB làm queue.

## 15. Kiểm thử send/receive cùng transaction

Để chứng minh transaction của channel store đúng, không chỉ assert handler được gọi. Cần kiểm tra **bản ghi trong DB business** và **khả năng nhận lại message từ store** sau transaction hoàn tất.

### Test A — producer rollback thì message không xuất hiện

Giả sử có một `PollableChannel pendingReservations` dùng `JdbcChannelMessageStore`, và trong cấu hình test **không cho poller tự chạy** để kiểm soát việc lấy message.

~~~java
@SpringBootTest
class DurableChannelProducerIT {
    @Autowired OrderCommandService service;
    @Autowired JdbcTemplate jdbc;

    @Autowired
    @Qualifier("pendingReservations")
    PollableChannel queue;

    @Test
    void rollbackRemovesBothOrderAndQueuedMessage() {
        String orderId = UUID.randomUUID().toString();
        String eventId = UUID.randomUUID().toString();

        assertThrows(IllegalStateException.class,
                () -> service.placeThenFail(new CreateOrder(
                        eventId, orderId, "SKU-1", 2)));

        Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders WHERE order_id = ?",
                Integer.class, orderId);

        assertEquals(0, rows);
        assertNull(queue.receive(0));
    }
}
~~~

**Điều kiện của test:** schema `orders` và schema store đã được tạo, DB trống hoặc queue/group ID độc lập cho case này, đồng thời không có poller/worker khác tranh nhận. Test gọi service qua proxy để annotation thực sự áp dụng.

### Test B — poller rollback thì message còn nhận lại được

Có thể dùng `TransactionTemplate` để mô phỏng đúng ý nghĩa của transactional poll:

~~~java
@SpringBootTest
class DurableChannelRollbackIT {
    @Autowired
    @Qualifier("pendingReservations")
    PollableChannel queue;
    @Autowired PlatformTransactionManager transactionManager;

    @Test
    void failedReceiveTransactionKeepsMessageAvailable() {
        String eventId = UUID.randomUUID().toString();
        ReserveInventory command = new ReserveInventory(
                eventId, "ORDER-TEST-1", "SKU-1", 1);
        queue.send(MessageBuilder.withPayload(command).build());

        TransactionTemplate tx = new TransactionTemplate(transactionManager);

        assertThrows(IllegalStateException.class,
                () -> tx.executeWithoutResult(status -> {
                    Message<?> received = queue.receive(0);
                    assertNotNull(received);
                    throw new IllegalStateException("Simulated failure");
                }));

        Message<?> redelivered = tx.execute(status -> queue.receive(0));
        assertNotNull(redelivered);
        ReserveInventory payload = (ReserveInventory) redelivered.getPayload();
        assertEquals(eventId, payload.eventId());
    }
}
~~~

**Giới hạn test:** ở ví dụ này, lần `receive(0)` thứ hai được thực hiện **bên trong một transaction và commit khi callback kết thúc**, nên nó sẽ xóa message khỏi store nếu commit thành công. Test cần chạy trên queue độc lập, với store và transaction manager phù hợp. Việc dùng store khác loại hoặc polling có executor có thể cho kết quả khác.

### Test C — chứng minh business DB và store cùng transaction

Mở transaction trên poller, nhận message, cập nhật tồn kho rồi ném `RuntimeException`. Quan sát sau rollback:

1. Tồn kho không thay đổi.
2. Message còn khả năng được nhận lại từ store.
3. Không có audit/outbox row nào đã commit nếu chúng cùng transaction.

Lặp lại với handler thành công: message bị xóa vĩnh viễn khỏi store và tồn kho giảm đúng một lần.

## 16. Ma trận failure injection và điều cần quan sát

| Điểm gây lỗi | Source/channel | Kỳ vọng kiểm chứng |
| --- | --- | --- |
| Producer ghi `orders` rồi rollback trước commit | JDBC store cùng DB/TX | Không còn business row hay message chưa commit. |
| Producer ghi `orders` rồi rollback trước commit | `QueueChannel` RAM | Message RAM có thể vẫn tồn tại dù DB rollback. |
| Producer publish broker rồi DB rollback | Broker khác resource | Message có thể đã tới broker; cần outbox/compensation. |
| Consumer nhận từ JDBC store rồi ném lỗi trước commit | Transactional poller cùng DB | Business update rollback, message không bị xóa vĩnh viễn. |
| Consumer nhận từ JDBC store mà không mở transaction | JDBC store auto-commit dequeue | Handler lỗi sau đó có thể mất message. |
| Consumer lấy message rồi dispatch sang executor | JDBC store + poller | Dequeue có thể commit trước khi worker hoàn tất. |
| Worker ghi DB commit, broker mất ACK | JMS/AMQP/Kafka | Nguồn có thể giao lại; consumer idempotent. |
| Hai worker đồng thời nhận cùng `eventId` | Broker/store phân tán | Unique constraint/DB transaction ngăn side effect trùng. |
| Một message sai schema liên tục rollback | Durable queue | Retry phải có giới hạn, DLQ/quarantine và replay. |
| Một nhánh Splitter commit, nhánh khác rollback | Nhiều resource/worker | Không có rollback tự động xuyên nhánh; cần Saga/compensation. |

Trong các ca trên, log ít nhất: `eventId`, `correlationId`, channel/source, transaction ID nếu hệ thống hỗ trợ, thread, trạng thái commit/rollback, delivery attempt, ACK/offset và số lần dedupe. Đừng coi một log `"send successful"` hay `"received message"` là kết quả end-to-end.

## 17. Quan sát vận hành và hiệu năng

| Metric | Ý nghĩa |
| --- | --- |
| Queue depth / pending store rows | Message chưa được xử lý; tăng liên tục có thể báo consumer bị chậm hoặc lỗi. |
| Oldest message age | Sự chậm trễ tối đa của công việc pending, quan trọng hơn chỉ nhìn số lượng. |
| Commit/rollback ratio | Chất lượng dữ liệu và sự ổn định của handler/transaction resource. |
| Retry/redelivery attempts | Nguồn bị lỗi, worker không ACK hoặc task poison. |
| Duplicate suppressed count | Consumer nhận lặp nhưng bỏ qua side effect nhờ idempotency. |
| Handler latency / DB lock wait | Transaction quá dài hoặc nhiều poller tranh chấp row. |
| DLQ/quarantine backlog | Công việc cần sửa/replay có kiểm soát. |
| Connection pool utilization | Có thiếu connection do concurrency hoặc `REQUIRES_NEW`/transaction nesting không? |

Với JDBC-backed queue, chú ý transaction isolation, truy vấn lấy message, index, vacuum/cleanup theo DB, khối lượng dữ liệu serialization và số poller đồng thời. Với luồng lớn, đánh giá broker chuyên dụng (JMS/AMQP/Kafka) hoặc kết hợp outbox thay vì mặc định biến DB nghiệp vụ thành queue thông lượng cao.

## 18. Chọn kiến trúc theo yêu cầu

| Nhu cầu | Phương án gợi ý | Bảo đảm/giới hạn |
| --- | --- | --- |
| Chuyển message đồng bộ giữa các handler JDBC trên cùng DB | `DirectChannel` + outer `@Transactional` + handler tham gia cùng TX. | Rollback các thao tác DB cùng resource, không rollback HTTP/email. |
| Handoff nội bộ không cần phục hồi khi restart | `QueueChannel` RAM có capacity. | Không transactional và không durable theo JDBC. |
| Lưu message cùng DB nghiệp vụ trước khi xử lý nền | `QueueChannel` + `JdbcChannelMessageStore` cùng DB/TX, transactional poller. | Cần quản lý schema, DB workload, concurrency và error path. |
| Nhiều service/consumer độc lập có broker riêng | JMS/AMQP/Kafka + consumer transaction + idempotency. | DB và broker không tự commit nguyên tử. |
| Phát sự kiện nghiệp vụ không được bỏ quên sau DB commit | Transactional outbox + relay + idempotent downstream. | Có thể publish trùng; cần backlog monitoring và retry. |
| Nhận event từ broker, cập nhật DB và phát event tiếp | Inbox/deduplication + business update + outbox cùng DB transaction. | ACK theo nguồn, xử lý redelivery và duplicate. |
| Flow nhiều nhánh cần kết quả tổng hợp | Correlation + persistent aggregator state + transaction mỗi nhánh, có compensation. | Các nhánh đã commit không tự rollback bởi aggregator. |
| Cần atomicity xuyên nhiều resource | Kiểm chứng XA/JTA/2PC khi được tất cả resource hỗ trợ, hoặc đổi kiến trúc. | Độ phức tạp vận hành lớn; đừng giả định từ các local transaction managers. |

**Nguyên tắc thiết kế:** xác định đầu tiên *resource nào chứa dữ liệu thật cần bảo vệ*, sau đó chọn channel và transaction boundary để thao tác trên resource đó cùng commit/rollback. Nếu một bước vượt qua resource, thread hoặc process, bổ sung **durable handoff, idempotency, retry và khả năng reconcile**.

## 19. Bài tập thực hành

**Bài 1 — so sánh hai QueueChannel.** Cấu hình một `QueueChannel(20)` RAM và một queue dùng `JdbcChannelMessageStore`. Trong một `@Transactional` service, lần lượt insert `orders`, send event rồi throw exception. Quan sát dữ liệu DB và message còn trong mỗi queue.

**Bài 2 — transactional receive.** Với JDBC-backed queue, cấu hình poller transaction và handler cập nhật tồn kho; tiêm lỗi ngay sau update. Chứng minh business row rollback và message được nhận lại. Sau đó bỏ transaction khỏi poller và giải thích kết quả khác.

**Bài 3 — đổi sang ExecutorChannel.** Thêm `ExecutorChannel` trước handler. Vẽ thread và transaction của poller/worker; tạo lỗi ở worker sau khi poller hoàn tất và xác định message có được khôi phục hay không. Đề xuất durable handoff.

**Bài 4 — hai datasource.** Cho business DB và channel store dùng datasource khác. Liệt kê các cửa sổ crash trong dual write và chọn giữa XA/JTA, outbox hoặc idempotent retry theo yêu cầu.

**Bài 5 — poison message.** Gửi payload không giải mã được hoặc quantity âm vào persistent queue. Thiết kế cơ chế retry hữu hạn, quarantine không mất message, thông báo lỗi và replay sau khi sửa payload.

**Bài 6 — Router/Splitter/Aggregator.** Một Gateway tạo yêu cầu, Splitter tách ba item rồi Router đưa các item vào các durable queue. Mỗi worker commit riêng. Thiết kế correlation ID, timeout, dedupe và compensation khi một item thất bại.

### Câu hỏi tự kiểm tra

**1. `DirectChannel` có phải một transactional resource không?** Không. Nó dispatch đồng bộ; các resource mà handler sử dụng mới quyết định phạm vi commit/rollback.

**2. Vì sao `QueueChannel` RAM không rollback enqueue cùng JDBC?** Vì queue trong bộ nhớ không phải JDBC resource do transaction manager quản lý.

**3. Khi nào `JdbcChannelMessageStore` có thể giúp message và business row cùng commit?** Khi cả hai dùng datasource/transaction manager tương thích, có một physical transaction bao quanh thao tác store và SQL nghiệp vụ.

**4. Vì sao phải có transactional poller khi consume từ JDBC-backed QueueChannel?** Để receive/remove và xử lý downstream đồng bộ cùng nằm trong transaction; nếu rollback, thao tác xóa message từ store có thể được đảo ngược.

**5. Dùng database khác cho store có tự tạo global transaction không?** Không. Phải cấu hình cơ chế phối hợp phù hợp hoặc chuyển sang outbox/inbox/idempotency.

**6. Tại sao retry vẫn cần `eventId` ổn định?** Một lần xử lý có thể commit ở resource này nhưng lỗi/không ACK ở resource khác; cùng message có thể xuất hiện lại và gây side effect lặp.

## 20. Checklist trước khi vận hành

- [ ] Ghi rõ resource transactional của từng bước: JDBC datasource, store, broker/session, external API.
- [ ] Biết channel nào đồng bộ, channel nào chuyển thread, channel nào lưu trong bộ nhớ hay durable store.
- [ ] Không coi `@Transactional` là cam kết mọi channel/broker cùng rollback.
- [ ] Với JDBC store, dùng schema/query provider đúng DB và version, quản lý `region`/group ID rõ ràng.
- [ ] Cấu hình transaction manager đúng datasource; chứng minh business rows và store operations thật sự dùng cùng physical transaction khi yêu cầu atomicity.
- [ ] Có transactional poller bao quanh **receive và downstream synchronous processing** khi muốn rollback dequeue.
- [ ] Không chuyển sang executor trước khi có một durable handoff hoặc chính sách xử lý lỗi phù hợp.
- [ ] Kiểm tra resource khác nhau cần XA/JTA hay thay bằng outbox/inbox; không ngầm giả định distributed transaction.
- [ ] Giữ `eventId` ổn định qua retry/redelivery; unique constraint và consumer idempotent cho side effect quan trọng.
- [ ] Không nuốt lỗi làm transaction/ACK coi xử lý thất bại thành công; kiểm tra error channel và rollback rules.
- [ ] Có retry/backoff hữu hạn, DLQ/quarantine, quy trình sửa/replay và giám sát backlog.
- [ ] Với Router/Splitter/Aggregator, thiết kế correlation, timeout, durable state và compensation.
- [ ] Kiểm thử rollback producer, rollback consumer, crash giữa các commit, redelivery và worker concurrency.
- [ ] Giám sát queue depth, age, DB lock, connection pool, retry, duplicate, DLQ và độ trễ end-to-end.

**Ghi nhớ:** **MessageChannel quyết định cách chuyển thông điệp; transactional resource quyết định thao tác nào thực sự có thể commit hoặc rollback.** Khi Spring Integration flow dùng cùng JDBC resource và transaction manager, một persistent channel store có thể giúp message và business data đi cùng giao dịch. Khi flow bước qua RAM queue, executor, broker, datasource khác hoặc external API, phải thiết kế riêng độ bền, ACK, redelivery và idempotency thay vì giả định transaction tự đi theo message.

### Tài liệu tham khảo

- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html): phân biệt channel và cách cấu hình persistent QueueChannel.
- [Spring Integration — JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html): query provider, schema, concurrency và đặc tính JDBC-backed channel.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): các propagation và transaction scope.

*Các ví dụ được viết để minh họa kiến trúc. Khi áp dụng, hãy đối chiếu API, schema, transaction manager và adapter với phiên bản Spring Integration/Spring Framework trong dự án; đo kiểm bằng integration test thay vì coi một annotation hoặc tên channel là đủ để chứng minh atomicity.*
