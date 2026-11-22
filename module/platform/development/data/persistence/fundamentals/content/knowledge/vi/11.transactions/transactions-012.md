# Giới hạn của giao dịch cục bộ khi có nhiều tài nguyên bên ngoài

Một giao dịch cơ sở dữ liệu giúp ứng dụng Java thay đổi nhiều bảng theo nguyên tắc *cùng thành công hoặc cùng thất bại*. Nhưng trong một chức năng thực tế, ứng dụng thường còn gọi HTTP API, gửi thông điệp qua message broker, tải tệp lên object storage, yêu cầu cổng thanh toán hoặc gửi email. Những thao tác đó **không tự động trở thành một phần của giao dịch database** chỉ vì chúng được gọi bên trong một phương thức có @Transactional.

Bài học thuộc chương **Giao dịch** của module DATA_PERSISTENCE_FUNDAMENTALS. Mục tiêu là hiểu ranh giới bảo đảm của persistence trong Java, nhận ra các trạng thái không nhất quán khi hệ thống có nhiều tài nguyên và chọn cơ chế phối hợp phù hợp với yêu cầu nghiệp vụ.

## 1. Kết quả cần đạt

Sau bài này, người học có thể:

- Xác định chính xác tài nguyên nào được một giao dịch cục bộ bảo vệ.
- Giải thích vì sao commit hoặc rollback của một database không thể tự hoàn tác HTTP, email, message broker hay cơ sở dữ liệu độc lập.
- Chỉ ra các thời điểm lỗi khi hệ thống vừa lưu dữ liệu vừa phát sự kiện, kể cả tình huống đã thực hiện thành công nhưng không nhận được phản hồi.
- Phân biệt giao dịch phân tán XA/2PC với các chiến lược eventual consistency như transactional outbox và Saga.
- Thiết kế luồng Java có idempotency, retry, ghi nhận trạng thái nghiệp vụ và cơ chế quan sát sự cố.
- Chọn phương án tùy theo mức độ cần nguyên tử, chi phí vận hành và khả năng sửa sai của tác vụ.

## 2. Giao dịch cục bộ bảo đảm điều gì?

Xét giao dịch JDBC:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        // Các câu SQL đều dùng cùng connection và cùng transaction.
        insertOrder(connection, order);
        insertOrderItems(connection, order.items());
        decreaseAvailableStock(connection, order.items());

        connection.commit();
    } catch (Exception ex) {
        connection.rollback();
        throw ex;
    }
}
~~~

Nếu tất cả thao tác trên thuộc cùng một giao dịch có hiệu lực trong database, khi commit thành công các thay đổi cùng được ghi nhận; khi rollback thành công chúng không trở thành dữ liệu đã commit. Tính nguyên tử này còn phụ thuộc vào khả năng giao dịch của database, cấu hình kết nối và các ràng buộc cụ thể của hệ quản trị. Nó không thay cho việc xử lý cạnh tranh, chọn mức cô lập và kiểm tra tính đúng đắn nghiệp vụ.

**Phạm vi điển hình:** một connection JDBC tới một cơ sở dữ liệu, hoặc một transaction manager quản lý các thao tác của cùng một tài nguyên giao dịch. Nhiều bảng và nhiều câu SQL trên cùng connection có thể ở cùng transaction; hai connection độc lập, hai database khác nhau hoặc một dịch vụ HTTP không đương nhiên cùng transaction.

Spring thường tạo ranh giới giao dịch thông qua proxy và transaction manager:

~~~java
@Service
public class OrderService {
    private final OrderRepository orderRepository;
    private final OrderItemRepository itemRepository;

    public OrderService(
            OrderRepository orderRepository,
            OrderItemRepository itemRepository) {
        this.orderRepository = orderRepository;
        this.itemRepository = itemRepository;
    }

    @Transactional
    public void createOrder(Order order) {
        orderRepository.save(order);
        itemRepository.saveAll(order.items());
    }
}
~~~

Với cấu hình phù hợp để cả hai repository dùng cùng transaction manager và cùng nguồn dữ liệu, các lệnh ghi trên cùng database được phối hợp trong transaction đó. Nhưng **@Transactional không tạo ra giao dịch toàn cục** cho mọi đối tượng hoặc dịch vụ được gọi từ phương thức.

Các giới hạn cần nhớ:

| Tài nguyên hoặc hành động | Có tự rollback cùng JDBC transaction không? | Giải thích |
|---|---|---|
| Hai bảng trên cùng database qua cùng transaction | Có, trong điều kiện hệ quản trị hỗ trợ | Cùng giao dịch DB; vẫn cần xử lý isolation và lỗi commit |
| Truy vấn từ repository khác dùng đúng transaction manager | Thường có | Phụ thuộc cấu hình, propagation và cùng tài nguyên |
| Cơ sở dữ liệu thứ hai với transaction manager riêng | Không | Hai commit/rollback độc lập trừ khi có cơ chế phối hợp phân tán |
| Gửi thông điệp tới Kafka/RabbitMQ hoặc broker khác | Không | Broker có giao thức xác nhận và cơ chế transaction riêng |
| Gọi API thanh toán qua HTTP | Không | Giao dịch DB không điều khiển được trạng thái cổng thanh toán |
| Lưu hoặc xóa object trên dịch vụ lưu trữ | Không | API lưu trữ có quy tắc thành công/thất bại riêng |
| Gửi email, SMS hoặc webhook | Không | Hành động bên ngoài có thể đã đến người nhận dù DB rollback |

Ngay cả khi nhiều dịch vụ cùng dùng khái niệm “transaction”, tên gọi giống nhau **không** có nghĩa chúng chia sẻ một transaction coordinator.

## 3. Ví dụ: tạo đơn hàng, cập nhật DB rồi phát sự kiện

Một chức năng đặt hàng cần:

1. Ghi bản ghi đơn hàng vào database.
2. Gửi sự kiện OrderCreated để một dịch vụ khác giữ hàng trong kho.
3. Trả kết quả cho người dùng.

Triển khai tưởng như hợp lý:

~~~java
@Transactional
public UUID createOrder(CreateOrderCommand command) {
    UUID orderId = UUID.randomUUID();
    orderRepository.insertPending(orderId, command.customerId());

    eventPublisher.publish(new OrderCreated(orderId));
    return orderId;
}
~~~

Giả sử orderRepository dùng PostgreSQL còn eventPublisher dùng message broker. Thứ tự thực tế là:

~~~text
Bắt đầu transaction DB
  |
  +-- INSERT orders                            [chưa commit]
  |
  +-- PUBLISH OrderCreated sang broker         [tác động độc lập]
  |
  +-- Phương thức trả về
  |
  +-- Transaction manager COMMIT DB
~~~

Chú ý **commit diễn ra khi phương thức @Transactional kết thúc**, không phải ngay sau INSERT. Nếu broker nhận sự kiện rồi DB commit thất bại, hệ thống có sự kiện về đơn hàng chưa tồn tại ở trạng thái đã commit. Một consumer chạy nhanh còn có thể đọc sự kiện **trước khi** DB transaction commit và không tìm thấy đơn.

Đổi vị trí publish thành “sau commit” chỉ loại bỏ một kiểu lỗi, nhưng tạo một kiểu khác: DB đã commit, ứng dụng chết trước khi publish. Điều cần giải quyết là **hai hệ thống có hai điểm commit không thể gộp thành một hành động nguyên tử bằng thứ tự gọi thông thường**.

### 3.1. Các thời điểm lỗi quan trọng

| Thứ tự và thời điểm xảy ra lỗi | Trạng thái có thể thấy | Vấn đề |
|---|---|---|
| Publish trước, DB rollback hoặc commit thất bại | Sự kiện đã được nhận, đơn chưa được commit | Consumer làm việc dựa trên dữ liệu chưa tồn tại |
| DB commit trước, tiến trình chết trước publish | Đơn tồn tại, không có sự kiện | Dịch vụ khác không biết có đơn cần xử lý |
| DB commit trước, publish trả lỗi | Đơn tồn tại, chưa biết broker đã nhận chưa | Không thể suy ra trạng thái chỉ từ exception |
| Broker nhận sự kiện, phản hồi xác nhận bị mất | Sự kiện đã tồn tại nhưng ứng dụng tưởng thất bại | Retry có thể gây publish trùng |
| Consumer ghi thay đổi rồi chết trước ACK | Thay đổi đã commit, broker có thể gửi lại | Cần consumer chịu được delivery trùng |
| DB commit thành công, HTTP response đến client bị mất | Đơn tồn tại, client không biết | Client retry có thể tạo thêm đơn nếu không có idempotency key |

Điểm chung là **kết quả bên ngoài có thể không rõ ràng**. Timeout chứng minh người gọi chưa nhận phản hồi kịp thời; nó không chứng minh tác vụ ở phía nhận chưa diễn ra.

## 4. Vì sao cách xử lý đơn giản thường thất bại?

### 4.1. Gọi hệ thống ngoài ngay trong @Transactional

~~~java
@Transactional
public void placeOrder(Order order) {
    orderRepository.insert(order);
    paymentClient.charge(order.payment());
}
~~~

Nếu charge thành công nhưng lệnh commit DB thất bại, thanh toán không tự được hoàn lại. Ngược lại, charge treo lâu còn khiến transaction DB giữ connection hoặc lock trong thời gian chờ mạng, gây áp lực lên pool và tăng nguy cơ xung đột.

Lỗi mạng giữa chừng khiến kết quả charge không chắc chắn. Retry thiếu idempotency có thể trừ tiền hai lần.

### 4.2. Chỉ chuyển lời gọi sang afterCommit

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    broker.publish(event);
}
~~~

Cách này có thể tránh publish trước lúc transaction DB commit. Tuy nhiên sau khi DB commit, callback vẫn có thể thất bại, tiến trình vẫn có thể chết, hoặc broker đã nhận nhưng mất xác nhận. Callback in-memory không phải hàng đợi bền vững và không giải quyết bài toán mất sự kiện.

**afterCommit phù hợp khi tác động là tùy chọn hoặc đã có cơ chế phục hồi bền vững khác.** Nếu sự kiện bắt buộc phải được phát, cần lưu ý định phát sự kiện vào tài nguyên bền vững cùng transaction DB.

### 4.3. Bọc lỗi bằng try/catch rồi tiếp tục

~~~java
@Transactional
public void placeOrder(Order order) {
    orderRepository.insert(order);

    try {
        broker.publish(new OrderCreated(order.id()));
    } catch (RuntimeException ex) {
        log.warn("Publish failed", ex);
    }
}
~~~

Cách này cho phép DB commit trong khi sự kiện không được gửi. Nó che mất trạng thái cần phục hồi. Ngược lại, chỉ ném exception khi broker lỗi cũng không chắc rollback sẽ xóa được sự kiện đã phát ở những lần gọi trước.

### 4.4. Nghĩ rằng retry luôn an toàn

Retry giúp xử lý lỗi tạm thời **chỉ khi thao tác có thể lặp lại an toàn**. Ví dụ gửi lại “trừ 100.000 đồng” không giống gửi lại yêu cầu “xác nhận thanh toán có paymentRequestId=X”. Trước khi retry phải xác định định danh yêu cầu, trạng thái đã thực hiện, chính sách của API nhận và giới hạn số lần thử.

## 5. Các hướng giải quyết và giới hạn của chúng

| Cách tiếp cận | Bảo đảm đạt được | Đổi lại / giới hạn | Phù hợp khi |
|---|---|---|---|
| Một DB transaction | Nguyên tử trong phạm vi một DB transaction | Không bao phủ HTTP, broker, storage khác | Các thay đổi đều nằm trong cùng database |
| XA / Two-Phase Commit (2PC) | Phối hợp commit giữa các resource manager tương thích, nếu cấu hình đúng | Coordinator, log, trạng thái in-doubt, nguy cơ chờ/block, chi phí vận hành; không áp dụng tùy ý với API ngoài | Cần nguyên tử giữa một số hệ hỗ trợ XA và chấp nhận độ phức tạp |
| Transactional outbox | Thay đổi nghiệp vụ và ý định phát event được ghi nguyên tử trong một DB | Phát event bất đồng bộ, có thể trùng; cần worker, quan sát, idempotent consumer | DB + message broker, yêu cầu không mất sự kiện sau commit |
| Saga | Điều phối nhiều local transaction với bước bù khi thất bại | Eventual consistency; bù không luôn khôi phục đúng trạng thái cũ | Quy trình nghiệp vụ nhiều dịch vụ/tài nguyên có thể bù |
| Idempotency + retry + reconciliation | Cho phép lặp lại an toàn và phục hồi kết quả chưa rõ | Cần lưu key, trạng thái, giới hạn retry và xử lý thủ công ngoại lệ | Hầu hết API thanh toán, webhook, consumer và tích hợp ngoài |
| Reservation / trạng thái trung gian | Tránh tuyên bố hoàn tất trước khi các bước quan trọng xong | Người dùng có thể thấy PENDING/PROCESSING; cần timeout và thu hồi | Đặt hàng, tồn kho, thanh toán nhiều bước |

Không có lựa chọn nào giúp mọi tác động bên ngoài trở thành một transaction duy nhất theo nghĩa của ACID. Thiết kế phải xác định rõ **điều gì được bảo đảm ngay lúc commit và điều gì sẽ hội tụ sau đó**.

## 6. Transactional outbox: gắn sự kiện với commit DB

### 6.1. Ý tưởng

Thay vì vừa ghi DB vừa gọi broker trong cùng một phương thức, ta lưu **dữ liệu nghiệp vụ** và **bản ghi sự kiện cần phát (outbox)** trong một transaction của cùng database. Một tiến trình dispatcher độc lập đọc outbox rồi phát tới broker.

~~~mermaid
flowchart LR
    A["Java API"] --> B["DB transaction"]
    B --> C["orders"]
    B --> D["outbox_events"]
    D --> E["Outbox dispatcher"]
    E --> F["Message broker"]
    F --> G["Consumer"]
    G --> H["Local transaction của consumer"]
~~~

Cả orders và outbox_events phải nằm trong cùng DB transaction. Chỉ khi commit thành công mới tồn tại đồng thời bản ghi đơn và sự kiện cần phát. Nếu rollback, cả hai đều mất.

### 6.2. Lược đồ minh họa

Ví dụ dùng PostgreSQL:

~~~sql
CREATE TABLE orders (
    id          uuid PRIMARY KEY,
    customer_id bigint NOT NULL,
    status      text NOT NULL
                CHECK (status IN ('PENDING', 'CONFIRMED', 'CANCELLED')),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE outbox_events (
    event_id      uuid PRIMARY KEY,
    aggregate_id  uuid NOT NULL,
    event_type    text NOT NULL,
    payload       jsonb NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    published_at  timestamptz
);

CREATE INDEX idx_outbox_unpublished
    ON outbox_events (created_at, event_id)
    WHERE published_at IS NULL;
~~~

Bản ghi published_at rỗng thể hiện còn cần phát. Trong hệ thống lớn có thể bổ sung attempt_count, next_attempt_at, lease_until, last_error và metadata về version/schema của sự kiện. Các trường đó giúp điều phối retry và quan sát sự cố; chúng không thay đổi tính chất nguyên tử của transaction ban đầu.

Để tránh tạo nhiều đơn khi client retry sau timeout, API nên dùng **idempotency key ổn định** và ràng buộc UNIQUE tương ứng với phạm vi nghiệp vụ (ví dụ tenant_id + request_key). Ví dụ tối giản bên dưới nhận orderId ổn định từ lớp gọi; nó chưa triển khai đầy đủ logic trả lại kết quả cũ của một yêu cầu đã xử lý.

### 6.3. Ghi order và outbox trong cùng local transaction

~~~java
@Service
public class OrderApplicationService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public OrderApplicationService(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Transactional
    public UUID createPendingOrder(UUID orderId, long customerId) {
        String payload;
        try {
            payload = mapper.writeValueAsString(Map.of(
                "orderId", orderId.toString(),
                "customerId", customerId
            ));
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot serialize OrderCreated", ex);
        }

        jdbc.update(
            "INSERT INTO orders(id, customer_id, status) VALUES (?, ?, 'PENDING')",
            orderId, customerId
        );

        jdbc.update(
            """
            INSERT INTO outbox_events(event_id, aggregate_id, event_type, payload)
            VALUES (?, ?, 'OrderCreated', ?::jsonb)
            """,
            UUID.randomUUID(), orderId, payload
        );

        return orderId;
    }
}
~~~

Ví dụ giả định Spring quản lý transaction của cùng DataSource mà JdbcTemplate sử dụng và phương thức được gọi qua proxy @Transactional. Ngoại lệ runtime khiến transaction rollback theo mặc định của Spring. Nếu chỉ lệnh INSERT order thành công nhưng INSERT outbox thất bại, **không có bản ghi order đã commit** khi rollback được thực hiện.

Cần hiểu rõ bảo đảm: “order đã commit thì bản ghi outbox cũng đã commit”, **chưa phải** “broker chắc chắn đã nhận event ngay lúc API trả về”. Tác vụ phát vẫn cần thành phần phục hồi riêng.

### 6.4. Dispatcher và cửa sổ lỗi còn lại

Một dispatcher hoạt động theo chu trình:

1. Lấy các bản ghi outbox chưa phát và **claim** một lô bằng transaction ngắn; dùng cơ chế locking/lease phù hợp để nhiều worker không lấy cùng bản ghi liên tục.
2. Commit thao tác claim, sau đó publish ra broker **ngoài** transaction DB, kèm event_id cố định.
3. Sau khi có xác nhận publish từ broker, dùng một transaction DB khác cập nhật trạng thái đã phát.
4. Nếu hết thời gian chờ, dispatcher chết hoặc publish thất bại, để lease hết hạn rồi thử lại, với backoff và giới hạn retry thích hợp.

Ví dụ luồng:

~~~text
DB COMMIT (order + outbox)
       |
       v
Dispatcher đọc/claim event_id = E
       |
       v
Broker nhận E ---------> ACK
       |                    |
       |                    v
       |             DB đánh dấu published
       |
       +--- Nếu ACK mất hoặc worker chết:
                    E có thể được publish lại
~~~

Vì broker có thể đã nhận E trước khi dispatcher chết hoặc trước khi mất ACK, outbox **không bảo đảm phát đúng một lần**. Thiết kế thông thường nhắm tới **at-least-once** cho việc phát sau commit, với giả định dispatcher tiếp tục chạy, lỗi có thể phục hồi, bản ghi được giữ bền vững và quy trình retry được thực hiện đúng.

Không giữ transaction DB mở trong lúc chờ broker nếu có thể tránh, vì thời gian chờ mạng làm tăng giữ connection/lock. Cơ chế claim bằng lease cần xử lý tranh chấp, thời hạn lease, clock và khả năng worker chậm; nếu hai worker cùng xử lý một event thì consumer vẫn phải chịu được trùng lặp.

**Một ngộ nhận:** cập nhật published_at thành thời điểm hiện tại *trước khi* publish để tránh trùng sẽ tạo nguy cơ mất sự kiện vĩnh viễn nếu tiến trình chết giữa hai bước. Cập nhật sau ACK chấp nhận khả năng trùng để tránh đánh dấu một thông điệp chưa chắc đã được gửi.

### 6.5. Vì sao không thể dựa vào “exactly once” của broker?

Một số nền tảng có giao dịch và cơ chế exactly-once trong phạm vi nhất định, ví dụ phối hợp ghi và tiêu thụ bản ghi bên trong hệ sinh thái của broker. Điều đó không tự bảo đảm thao tác DB của ứng dụng Java hoặc lời gọi HTTP tới dịch vụ khác chỉ diễn ra đúng một lần. Cần xem chính xác **ranh giới của bảo đảm**: broker, database, consumer hay toàn bộ hiệu ứng nghiệp vụ.

## 7. Idempotent consumer: nhận lại sự kiện mà không lặp hiệu ứng

Consumer phải giả định broker có thể giao lại cùng một event. Cách thường gặp là tạo bảng lưu ID sự kiện đã xử lý, có ràng buộc UNIQUE hoặc PRIMARY KEY. Ghi nhận ID và cập nhật nghiệp vụ trong **cùng local transaction** ở database phía consumer.

~~~sql
CREATE TABLE processed_messages (
    consumer_name text NOT NULL,
    event_id      uuid NOT NULL,
    processed_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE inventory_reservations (
    order_id uuid PRIMARY KEY,
    status   text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
~~~

Ví dụ Java JDBC trong dịch vụ kho:

~~~java
@Service
public class InventoryEventHandler {
    private final JdbcTemplate jdbc;

    public InventoryEventHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void handleOrderCreated(UUID eventId, UUID orderId) {
        int inserted = jdbc.update(
            """
            INSERT INTO processed_messages(consumer_name, event_id)
            VALUES ('inventory', ?)
            ON CONFLICT DO NOTHING
            """,
            eventId
        );

        if (inserted == 0) {
            return; // Event này đã được xử lý thành công trước đó.
        }

        jdbc.update(
            """
            INSERT INTO inventory_reservations(order_id, status)
            VALUES (?, 'REQUESTED')
            ON CONFLICT (order_id) DO NOTHING
            """,
            orderId
        );
    }
}
~~~

Nếu lỗi xảy ra sau INSERT processed_messages nhưng trước khi ghi reservation, cả transaction rollback, sự kiện sẽ có cơ hội xử lý lại. Nếu cả hai đã commit nhưng ACK từ consumer tới broker bị mất, lần giao lại gặp khóa chính đã tồn tại và không lặp lại thay đổi.

Mẫu trên xử lý **trùng event_id**, nhưng chưa giải quyết tất cả các vấn đề: sự kiện khác ID nhưng cùng ý nghĩa nghiệp vụ, sự kiện đến sai thứ tự, tồn kho không đủ hoặc cập nhật cạnh tranh. Ràng buộc order_id duy nhất giúp chống tạo nhiều reservation cho một order; phần giữ số lượng hàng thật cần có logic đồng thời và quy tắc nghiệp vụ riêng.

Nếu một consumer thực hiện thêm HTTP call ra ngoài, transaction DB của consumer cũng **không** bao phủ HTTP call đó. Khi ấy lại cần outbox hoặc idempotency của hệ đích cho chặng tiếp theo.

## 8. Saga: điều phối một quy trình qua nhiều tài nguyên

Outbox bảo đảm không mất ý định phát sự kiện trong DB. Tuy nhiên một yêu cầu kinh doanh thường bao gồm nhiều công việc ở các dịch vụ khác nhau:

- Tạo đơn hàng trong Order Service.
- Giữ tồn kho ở Inventory Service.
- Xác thực hoặc giữ tiền ở Payment Service.
- Xác nhận đơn và thông báo người dùng.

Không thể sử dụng một local transaction xuyên qua tất cả bước. **Saga** mô hình hóa chúng như chuỗi local transaction; mỗi bước hoàn thành thì ghi trạng thái và kích hoạt bước kế tiếp. Nếu có bước thất bại, hệ thống gọi **hành động bù (compensation)** để giảm hoặc đảo ngược tác động trước đó khi nghiệp vụ cho phép.

~~~mermaid
flowchart TD
    A["Order: PENDING"] --> B["Reserve inventory"]
    B -->|Thành công| C["Authorize payment"]
    B -->|Thất bại| F["Order: CANCELLED"]
    C -->|Thành công| D["Order: CONFIRMED"]
    C -->|Thất bại| E["Release inventory"]
    E --> F
    C -->|Kết quả chưa rõ| G["WAITING_RECONCILIATION"]
    G --> H["Kiểm tra trạng thái Payment"]
    H -->|Đã authorize| D
    H -->|Không authorize hoặc thất bại| E
~~~

Sơ đồ đơn giản hóa nhánh xử lý: trong thực tế, nếu không thể xác nhận trạng thái giữ hàng hay thanh toán, hệ thống cần tiếp tục đối soát hoặc chuyển sang can thiệp vận hành thay vì tự suy đoán thành công/thất bại.

### 8.1. Compensation không phải rollback DB

Rollback trong DB có thể hủy những thay đổi chưa commit. Compensation là **hành động nghiệp vụ mới**, chẳng hạn:

| Đã thực hiện | Hành động bù có thể dùng | Giới hạn |
|---|---|---|
| Giữ 2 sản phẩm trong kho | Release reservation | Reservation đã hết hạn hoặc trạng thái kho đã thay đổi |
| Authorize khoản thanh toán | Void authorization | Cổng thanh toán có điều kiện và thời hạn riêng |
| Đã capture tiền | Refund | Có thể mất thời gian, phát sinh phí hoặc chưa thành công |
| Tạo bản nháp tài liệu trên storage | Xóa bản nháp | File có thể đã được người khác đọc hoặc sao chép |
| Gửi email xác nhận | Gửi email đính chính | Không thể thu hồi email đã nhận một cách chắc chắn |

Vì compensation có thể thất bại, hệ thống cần retry, lưu trạng thái và cảnh báo để con người xử lý khi cần. Đừng tuyên bố một Saga đảm bảo rollback nguyên tử như một DB transaction.

### 8.2. Orchestration hay choreography?

**Orchestration:** một coordinator quyết định bước tiếp theo và ghi trạng thái quy trình. Cách này giúp nhìn thấy toàn bộ luồng, xử lý timeout và bù rõ ràng, nhưng coordinator phải được thiết kế bền vững, khôi phục được sau khi restart.

**Choreography:** các dịch vụ phản ứng với event của nhau. Cách này giảm điều phối tập trung nhưng luồng dễ khó theo dõi khi nhiều nhánh, sự kiện đến trễ hoặc trùng, và trách nhiệm kích hoạt compensation trở nên phân tán.

Cả hai đều cần định danh workflow, idempotent handler, timeout, version trạng thái và khả năng quan sát. Chọn dựa trên độ phức tạp quy trình và cách nhóm vận hành kiểm soát lỗi, không chỉ số lượng dịch vụ.

## 9. XA và Two-Phase Commit: khi nào thực sự phù hợp?

Một giải pháp khác là giao dịch phân tán có coordinator, thường dựa trên XA/2PC giữa những resource manager hỗ trợ giao thức.

### Pha 1: Prepare

Coordinator yêu cầu từng resource chuẩn bị commit. Tài nguyên báo rằng có thể commit và giữ đủ thông tin để hoàn tất sau đó.

### Pha 2: Commit hoặc rollback

Nếu tất cả đồng ý, coordinator quyết định commit; nếu một thành phần không thể chuẩn bị, coordinator yêu cầu rollback theo cơ chế của giao thức.

~~~text
             Coordinator
             /          \
       Prepare         Prepare
          |                |
     Database A        Database B
          |                |
        Ready            Ready
             \          /
               Commit
~~~

Trong trường hợp cấu hình đúng, XA cho phép phối hợp các resource hỗ trợ protocol thay vì tự làm hai thao tác commit độc lập. Nhưng:

- Cần transaction manager, resource manager tương thích và cấu hình XA thực sự; thêm @Transactional không đủ.
- Việc giữ trạng thái prepared và phục hồi in-doubt khi coordinator hoặc mạng hỏng có thể gây block và khó vận hành.
- Có chi phí về kết nối, log, timeout và khả năng chịu lỗi khi kéo dài giao dịch phân tán.
- HTTP API thông thường, email và nhiều hệ thống bên ngoài không phải resource XA.
- Ngay cả khi DB và broker có hỗ trợ giao dịch riêng, phải xác nhận **có hỗ trợ phối hợp trong cùng giao thức/phạm vi** trước khi hứa hẹn atomicity.

XA có thể hợp lý trong một số hệ thống cần tính nguyên tử mạnh giữa các resource hỗ trợ và đội vận hành có thể đáp ứng yêu cầu đó. Với phần lớn workflow dịch vụ kết hợp thanh toán, HTTP và thông báo, thiết kế trạng thái tường minh cùng retry và compensation thường thực tế hơn.

## 10. Thiết kế trạng thái nghiệp vụ khi chưa thể kết luận ngay

Giả sử API tạo đơn sẽ kích hoạt thanh toán qua nhà cung cấp bên ngoài. Nếu API thanh toán timeout, hệ thống không biết khoản thanh toán có được chấp nhận hay chưa.

Không nên làm:

~~~text
HTTP timeout -> coi như thanh toán thất bại -> tạo yêu cầu mới với ID khác
~~~

Thay vào đó, dùng **paymentRequestId ổn định** và một state machine thể hiện sự chưa chắc chắn:

~~~text
PENDING_PAYMENT
      |
      +--> PAYMENT_IN_PROGRESS
                 |
                 +--> AUTHORIZED --> CONFIRMED
                 |
                 +--> DECLINED --> CANCELLED
                 |
                 +--> UNKNOWN --> RECONCILING
                                       |
                            provider status lookup / webhook
                                       |
                        AUTHORIZED hoặc DECLINED
~~~

Quy tắc nên có:

1. Mỗi yêu cầu thanh toán có ID/idempotency key ổn định, dùng lại cho retry theo khả năng hỗ trợ của nhà cung cấp.
2. Lưu trạng thái local trước/sau lời gọi theo ranh giới transaction phù hợp; không giữ lock DB trong suốt thời gian chờ HTTP.
3. Xác minh kết quả chưa rõ bằng API tra cứu, webhook có xác thực hoặc báo cáo đối soát.
4. Các callback đến nhiều lần, đến trễ hoặc sai thứ tự phải được xử lý bằng kiểm tra version/chuyển trạng thái hợp lệ.
5. Khi chuyển sang trạng thái cuối, phát sự kiện bằng outbox nếu dịch vụ khác cần biết; không dựa vào một callback tạm thời trong RAM.

**Tính đúng đắn nghiệp vụ quan trọng hơn phản hồi tức thì.** Một kết quả PENDING với mã theo dõi và cơ chế đối soát có thể an toàn hơn trả “thành công” hoặc “thất bại” khi chưa đủ chứng cứ.

## 11. Các trường hợp nhiều tài nguyên thường gặp

### 11.1. Hai database độc lập

~~~text
Service -> DB A: commit customer
        -> DB B: commit profile
~~~

Nếu DB A commit thành công nhưng DB B thất bại, local transaction của DB A không tự hoàn tác được. Nếu hai phần bắt buộc đồng bộ tức thì và hạ tầng hỗ trợ, đánh giá XA/2PC; nếu chấp nhận nhất quán sau, có thể dùng trạng thái trung gian, outbox và retry hoặc Saga.

Trong Java, hai @Transactional với hai transaction manager độc lập cũng không tạo ra atomicity giữa chúng. Chọn transaction manager và propagation rõ ràng; tránh suy diễn từ annotation.

### 11.2. DB và object storage

Ứng dụng cần lưu metadata tài liệu vào DB và upload file lên object storage. Nếu upload thành công nhưng DB rollback, file bị mồ côi. Nếu DB commit trước nhưng upload lỗi, metadata trỏ tới file chưa tồn tại.

Mẫu giảm thiểu:

- Tạo bản ghi UPLOADING/PENDING, cấp upload ID.
- Upload vào vùng staging với object key xác định.
- Xác minh object tồn tại và hợp lệ, sau đó cập nhật READY trong local transaction DB.
- Dùng job dọn file mồ côi/quá hạn, reconcile metadata và object theo định danh.
- Nếu có event sang dịch vụ khác, chỉ phát thông báo READY qua outbox trong cùng transaction cập nhật trạng thái READY.

Việc xóa file sau timeout hoặc thất bại cần xét khả năng người khác đã tham chiếu và chính sách lưu giữ.

### 11.3. DB và gửi email

Email đã gửi không thể được rollback theo database. Nếu email là bước quan trọng sau commit, ghi intent vào outbox và cho worker gửi sau khi commit; dùng message ID hoặc business key để giảm gửi trùng nếu nhà cung cấp hỗ trợ. Dù vậy, timeout sau khi gửi có thể dẫn đến trùng và việc thu hồi email không được bảo đảm.

Với email thuần thông báo có thể chấp nhận thất bại, afterCommit hoặc queue ít ràng buộc hơn có thể đủ; cần làm rõ mức bảo đảm mong muốn.

### 11.4. Database và cache

Nếu DB đã commit nhưng cập nhật cache thất bại, người đọc có thể thấy dữ liệu cũ. Cần định nghĩa chiến lược invalidation, TTL, version và trường hợp đọc stale. Không nên coi thao tác cache là một phần của ACID transaction DB. Đối với thông tin cần tính nhất quán cao như số dư hoặc phân quyền, cân nhắc nguồn dữ liệu authoritative và quy tắc đọc phù hợp.

## 12. Vấn đề thứ tự, đồng thời và phiên bản sự kiện

At-least-once không chỉ tạo bản sao event; hệ thống phân tán còn có thể nhận sự kiện sai thứ tự. Ví dụ:

~~~text
OrderConfirmed(orderId=O, version=3)
OrderCancelled(orderId=O, version=4)
~~~

Nếu consumer xử lý version=4 trước, rồi một bản sao version=3 đến sau và ghi đè trạng thái, đơn có thể bị “xác nhận lại” sai.

Cần một hoặc nhiều biện pháp:

- Mang aggregate_id và số version tăng đơn điệu trong event khi nghiệp vụ yêu cầu thứ tự.
- Kiểm tra chuyển trạng thái hợp lệ; không cho bản tin cũ ghi đè trạng thái mới hơn.
- Cấu hình partition/routing cùng khóa aggregate khi broker hỗ trợ, nhưng vẫn đề phòng retry, replay và xử lý đồng thời.
- Dùng optimistic locking, khóa hàng hoặc constraint khi cập nhật cùng aggregate trong database.
- Ghi nhận event_id để chống trùng và version để chống áp dụng sai thứ tự: hai việc này giải quyết **hai bài toán khác nhau**.

Idempotency cũng có phạm vi: ID của request, event, payment hay reservation không phải một thứ. Cần đặt key ở đúng ranh giới có khả năng phát sinh yêu cầu trùng.

## 13. Retry, timeout và phục hồi mà không khuếch đại lỗi

Retry liên tục không giới hạn có thể làm hệ thống ngoài quá tải. Một chính sách an toàn thường gồm:

| Cơ chế | Mục đích | Lưu ý |
|---|---|---|
| Retry có backoff và jitter | Giảm số lần thử dồn dập sau lỗi tạm thời | Giữ idempotency key qua mọi lần thử |
| Deadline/timeout | Giới hạn thời gian chờ mỗi bước | Timeout không chứng minh hệ đích chưa xử lý |
| Lease + reclaim | Phục hồi job sau khi worker chết | Lease phải hết hạn và xử lý tranh chấp đúng |
| Dead-letter / parking | Cô lập thông điệp lỗi lâu dài | Phải có cách kiểm tra, sửa và replay có kiểm soát |
| Reconciliation | So sánh trạng thái local với hệ ngoài | Rất quan trọng cho thanh toán và sự kiện mất xác nhận |
| Circuit breaker / giới hạn concurrency | Tránh dồn lỗi vào dịch vụ đang suy yếu | Không thay thế retry bền vững hoặc đối soát |
| Log/trace/metrics | Chỉ ra workflow nào đang mắc kẹt | Không log dữ liệu nhạy cảm như token, thông tin thẻ |

Các chỉ số nên theo dõi gồm số event outbox chưa phát, tuổi bản ghi cũ nhất, số lần publish lại, số lỗi consumer, thời gian từ commit đến xử lý xong, số Saga đang PENDING/RECONCILING và số bước bù thất bại.

Chỉ ghi log exception mà không lưu trạng thái phục hồi sẽ khiến restart làm mất dấu công việc. Ngược lại, outbox hoặc bảng workflow bền vững phải có quy trình vận hành để các bản ghi đó thực sự được tiếp tục xử lý.

## 14. Lựa chọn ranh giới transaction trong Java

Khi thiết kế một chức năng, hãy làm rõ từng câu hỏi:

1. **Nguồn dữ liệu gốc là gì?** Ví dụ DB orders là nguồn authoritative cho tình trạng đơn; Payment Service là nguồn authoritative cho khoản charge.
2. **Những thay đổi nào phải commit nguyên tử ngay?** Ví dụ đơn PENDING và outbox OrderCreated trong cùng DB.
3. **Những bước nào chỉ có thể hoàn thành sau?** Ví dụ giữ hàng, thanh toán, email.
4. **Nếu process chết tại từng điểm thì hồi phục thế nào?** Phải có bản ghi bền vững, mã định danh và worker/reconciliation.
5. **Nếu thông điệp hoặc request đến hai lần thì sao?** UNIQUE constraint, idempotency key và kiểm tra trạng thái.
6. **Nếu các bước đến sai thứ tự hoặc cạnh tranh thì sao?** Version, lock, validation của state machine.
7. **Lúc nào được báo thành công cho người dùng?** Tùy hợp đồng API: “đã nhận đơn”, “đã đặt hàng thành công”, “đã thanh toán” là những mốc khác nhau.

Một ví dụ về ranh giới rõ ràng:

~~~text
HTTP POST /orders
   |
   v
Local DB TX:
  - INSERT orders(status=PENDING)
  - INSERT outbox_events(OrderCreated)
COMMIT
   |
   v
HTTP 202 Accepted + orderId
   |
   v
Dispatcher -> Broker -> Inventory/Payment
   |
   v
Order status cập nhật CONFIRMED/CANCELLED qua local TX
   |
   v
GET /orders/{id} hoặc event/webhook báo trạng thái cuối
~~~

HTTP 202 Accepted là lựa chọn **khi API có hợp đồng xử lý bất đồng bộ**; không phải mọi API đều cần trả 202. Điều cốt lõi là không khẳng định “đã hoàn thành toàn bộ” khi mới commit một bước cục bộ.

### 14.1. Một số lưu ý riêng của Spring

- @Transactional dùng proxy theo cấu hình thông thường. Lời gọi cùng đối tượng qua this.someMethod() có thể không đi qua proxy nên không kích hoạt giao dịch theo mong đợi.
- Rollback mặc định áp dụng cho RuntimeException và Error; với checked exception, cần cấu hình rollbackFor hoặc chuyển thành lỗi phù hợp nếu muốn rollback.
- Việc truyền transaction context giữa thread, tác vụ @Async hay tiến trình khác không tự diễn ra như một transaction chung.
- Một phương thức dùng nhiều DataSource nhưng chỉ có một transaction manager không tự bao phủ cả hai DataSource.
- Không duy trì DB transaction trong lúc gọi API ngoài lâu; chỉ dùng giao dịch ngắn cho phần thay đổi dữ liệu cục bộ.

Đừng suy từ tên annotation hay tên phương thức repository; khi cần hãy kiểm tra transaction manager, DataSource, propagation và SQL thực tế của ứng dụng.

## 15. Bài tập tình huống

### Bài 1. Publish trước commit

Một service có @Transactional, ghi orders rồi publish OrderCreated. Broker xác nhận thành công, nhưng DB commit bị lỗi.

**Câu hỏi:** Consumer có thể thấy gì? Chuyển publish sang afterCommit có giải quyết hoàn toàn không?

**Gợi ý đáp án:** Consumer có thể nhận event của đơn chưa tồn tại ở trạng thái đã commit. afterCommit tránh trường hợp publish trước commit nhưng vẫn có cửa sổ DB đã commit mà process chết trước publish. Transactional outbox lưu event intent với order trong cùng DB transaction rồi phát sau.

### Bài 2. Thanh toán timeout

Ứng dụng gọi cổng thanh toán và bị timeout. Client gửi lại HTTP request với request ID mới và hệ thống tiếp tục charge.

**Câu hỏi:** Rủi ro chính và cách xử lý?

**Gợi ý đáp án:** Timeout không chứng minh charge thất bại; retry với request ID mới có thể trừ tiền hai lần. Giữ key ổn định, lưu trạng thái UNKNOWN/RECONCILING, truy vấn trạng thái nhà cung cấp hoặc dùng webhook đã xác thực, chỉ quyết định trạng thái cuối khi đủ chứng cứ.

### Bài 3. Outbox đã publish nhưng chưa đánh dấu

Dispatcher publish event E thành công, chết trước khi cập nhật published_at. Sau restart, E được phát lại.

**Câu hỏi:** Có phải outbox lỗi không? Cần kiểm soát tại đâu?

**Gợi ý đáp án:** Đây là hành vi có thể xảy ra của at-least-once. Consumer dùng event_id để chống xử lý trùng trong cùng local transaction với thay đổi nghiệp vụ; đồng thời dùng business key để ngăn tác động trùng không mong muốn.

### Bài 4. Hai database trong một service

Một Spring service có hai repository: mỗi repository dùng một DataSource và transaction manager riêng. Phương thức ngoài có @Transactional.

**Câu hỏi:** Có thể khẳng định cả hai database commit nguyên tử không?

**Gợi ý đáp án:** Không. Cần kiểm tra transaction manager thực tế và cách enlist các tài nguyên. Nếu không có XA/2PC hay cơ chế phù hợp, mỗi DB có commit độc lập; cần chọn mô hình phục hồi như Saga, đồng bộ qua outbox hoặc thiết kế lại ranh giới dữ liệu.

### Bài 5. Đã gửi email, sau đó bù Saga

Đơn đã được xác nhận và email đã gửi. Sau đó một bước cuối thất bại khiến đơn bị hủy.

**Câu hỏi:** Vì sao không thể gọi đây là rollback toàn bộ?

**Gợi ý đáp án:** Email đã đến người nhận không tự bị xóa khi DB đổi trạng thái. Có thể gửi thư đính chính, nhưng đó là tác động bổ sung, không khôi phục chính xác thế giới về trước khi gửi. Vì vậy cần chọn thời điểm gửi và nội dung email theo trạng thái nghiệp vụ thực tế.

## 16. Checklist thiết kế và kiểm thử lỗi

- [ ] Xác định rõ phạm vi local transaction: connection, DataSource, database, transaction manager.
- [ ] Liệt kê mọi tác động ngoài DB: HTTP, broker, storage, email, cache, database khác.
- [ ] Vẽ cửa sổ lỗi trước/sau từng commit, publish, ACK và HTTP response.
- [ ] Lưu intent bền vững khi bước ngoài bắt buộc phải diễn ra sau DB commit.
- [ ] Dùng idempotency key, constraint và kiểm tra phiên bản để xử lý retry, duplicate và out-of-order.
- [ ] Không dùng exception/timeout làm bằng chứng chắc chắn rằng hệ ngoài chưa thực hiện tác vụ.
- [ ] Xác định trạng thái PENDING/UNKNOWN và cách reconciliation tới trạng thái cuối.
- [ ] Thiết kế compensation, retry, giới hạn và cách xử lý thủ công cho các bước không thể rollback.
- [ ] Quan sát outbox backlog, tuổi event, retry, Saga bị kẹt và chênh lệch dữ liệu giữa các hệ.
- [ ] Kiểm tra các kịch bản crash sau DB commit, sau broker ACK, trước khi mark published, sau consumer commit và trước khi trả response.
- [ ] Đánh giá chi phí/giới hạn XA trước khi áp dụng, chỉ khi các tài nguyên thực sự hỗ trợ giao dịch phân tán.
- [ ] Xác nhận API báo đúng mức hoàn thành nghiệp vụ: “đã tiếp nhận” khác với “đã thanh toán và giao hàng”.

**Ghi nhớ:** giao dịch cục bộ là nền tảng bảo vệ tính nhất quán **bên trong một ranh giới persistence**. Khi workflow Java bước qua ranh giới ấy, không thể dựa vào một commit hay @Transactional để bảo đảm mọi hệ thống cùng thay đổi nguyên tử. Thiết kế đáng tin cậy phải phối hợp **trạng thái bền vững, outbox, idempotency, retry, đối soát và hành động bù** theo đúng yêu cầu nghiệp vụ.
