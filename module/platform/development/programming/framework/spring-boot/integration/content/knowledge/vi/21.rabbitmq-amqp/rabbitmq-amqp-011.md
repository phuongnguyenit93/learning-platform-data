# Ranh giới giao dịch RabbitMQ với cập nhật cơ sở dữ liệu

Trong một hệ thống Spring Boot, thao tác ghi cơ sở dữ liệu (database) và gửi hoặc nhận thông điệp RabbitMQ thường nằm trong cùng một nghiệp vụ, nhưng **không tự động nằm trong cùng một giao dịch nguyên tử**. Đây là điểm cốt lõi khi tích hợp HTTP, cơ sở dữ liệu, cache và broker thông điệp: cần phân biệt rõ bên nào đã cam kết dữ liệu, bên nào đã tiếp nhận thông điệp, bên nào đã xử lý xong và cách phục hồi khi một bước thất bại.

Ví dụ xuyên suốt: dịch vụ **Đơn hàng** lưu đơn vào PostgreSQL rồi phát sự kiện **OrderCreated** lên RabbitMQ; dịch vụ **Kho** nhận sự kiện, cập nhật số lượng hàng đã giữ chỗ và xác nhận thông điệp. Yêu cầu nghiệp vụ là không được mất sự kiện của đơn hàng đã ghi thành công và không được trừ tồn kho hai lần khi RabbitMQ giao lại cùng một sự kiện.

## 1. Các giao dịch và tín hiệu xác nhận có phạm vi khác nhau

| Cơ chế | Phạm vi bảo vệ | Điều cơ chế này **không** bảo đảm |
| --- | --- | --- |
| Giao dịch JDBC/JPA với **@Transactional** | Các thao tác SQL dùng chung transaction manager và kết nối cơ sở dữ liệu trong cùng ranh giới giao dịch | Không làm RabbitMQ commit hoặc rollback cùng với cơ sở dữ liệu |
| Giao dịch AMQP trên một channel (lệnh **tx.select**, **tx.commit**, **tx.rollback**) | Các thao tác AMQP phù hợp trên channel đó | Không phải giao dịch phân tán với PostgreSQL; không thay thế publisher confirms |
| **Publisher confirm** | Broker xác nhận đã nhận và xử lý thao tác publish theo điều kiện bảo đảm của broker và loại queue | Không xác nhận consumer đã xử lý; một confirm thành công vẫn có thể đi cùng thông điệp bị trả về vì không định tuyến được |
| **Publisher return** với **mandatory=true** | Phát hiện thông điệp không thể định tuyến đến queue nào | Không xác nhận xử lý nghiệp vụ ở consumer |
| **Consumer acknowledgment (ack)** | Consumer báo cho broker rằng delivery đã được xử lý và có thể loại khỏi hàng đợi | Không commit cơ sở dữ liệu của consumer; nếu ack trước DB commit có thể mất việc xử lý |
| **Persistent message + durable queue** | Tăng khả năng sống sót qua sự cố broker khi cấu hình phù hợp; queue quorum thường được chọn nếu cần sao chép và độ bền cao | Không khép được khoảng hở giữa commit SQL và publish |

Trong Spring Boot, **@Transactional** mặc định dùng một transaction manager tương ứng với tài nguyên được cấu hình. Chẳng hạn, **JpaTransactionManager** kiểm soát giao dịch JPA trên PostgreSQL. **RabbitTemplate** gửi thông điệp đến một hệ thống bên ngoài qua kết nối AMQP; chỉ đặt hai thao tác trong cùng một phương thức có **@Transactional** không biến chúng thành một giao dịch toàn cục.

Đặc biệt cần phân biệt:

- **DB commit**: thay đổi đơn hàng đã được chấp nhận trong cơ sở dữ liệu.
- **Broker confirm**: broker đã xác nhận lệnh publish; kiểm tra thêm return để biết thông điệp có được định tuyến.
- **Consumer DB commit**: xử lý nghiệp vụ ở dịch vụ nhận đã bền vững.
- **Consumer ack**: broker nhận tín hiệu xóa delivery đã giao khỏi queue.

Đây là bốn mốc độc lập. Thiết kế tích hợp phải xử lý việc tiến trình có thể dừng ở bất cứ khoảng hở nào giữa chúng.

## 2. Vì sao ghi DB rồi publish trực tiếp tạo ra lỗi dual-write?

Mã sau trông hợp lý nhưng chưa bảo đảm tính nhất quán:

~~~java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final RabbitTemplate rabbitTemplate;

    public OrderService(OrderRepository orders, RabbitTemplate rabbitTemplate) {
        this.orders = orders;
        this.rabbitTemplate = rabbitTemplate;
    }

    @Transactional
    public void createOrder(CreateOrderCommand command) {
        Order order = orders.save(Order.from(command));
        rabbitTemplate.convertAndSend(
                "domain.events", "order.created",
                new OrderCreated(order.getId()));
    }
}
~~~

Với cấu hình thông thường, lời gọi **convertAndSend** trả về sau khi gửi/ghi dữ liệu qua client, không đồng nghĩa broker đã xác nhận lưu và định tuyến thành công. Hơn nữa, giao dịch JPA thường chỉ commit **sau khi phương thức @Transactional trả về**. Kịch bản lỗi:

1. Thông điệp được RabbitMQ chấp nhận.
2. Giao dịch database commit thất bại (ví dụ ràng buộc dữ liệu hoặc mất kết nối).
3. Dịch vụ Kho nhận một **OrderCreated** cho đơn hàng không tồn tại.

Nếu đổi thứ tự thành **commit DB trước, publish sau**, lại có kịch bản:

1. Đơn hàng đã commit thành công.
2. Tiến trình chết trước lệnh publish, hoặc broker từ chối lệnh.
3. Đơn hàng tồn tại nhưng không có sự kiện cho dịch vụ Kho.

~~~mermaid
flowchart TD
    A["Yêu cầu tạo đơn"] --> B["Ghi đơn hàng vào DB"]
    B --> C{"DB đã commit?"}
    C -->|Không| D["Rollback DB"]
    C -->|Có| E["Publish RabbitMQ"]
    E --> F{"Broker nhận và định tuyến?"}
    F -->|Có| G["Tiếp tục quy trình"]
    F -->|Không / tiến trình chết| H["Đơn đã lưu nhưng có thể mất sự kiện"]
~~~

Lỗi này được gọi là **dual-write problem**: hai tài nguyên độc lập cần cập nhật theo một kết quả nghiệp vụ, nhưng không có transaction coordinator bảo đảm cả hai cùng commit hoặc cùng rollback.

### Đặt RabbitMQ vào một transaction AMQP có giải quyết được không?

Spring AMQP hỗ trợ **channelTransacted=true** để dùng AMQP transaction. Khi có giao dịch cơ sở dữ liệu bên ngoài, Spring AMQP có thể đồng bộ giao dịch channel theo giao dịch đó theo kiểu **best efforts one-phase commit**. Điều này giúp nhiều lỗi thông thường kích hoạt rollback ở cả hai phía, nhưng **không có cam kết nguyên tử hai pha**: DB có thể commit thành công rồi việc commit AMQP thất bại. Lúc ấy không thể thu hồi bản ghi DB đã commit.

Vì vậy:

- Có thể dùng transaction AMQP khi cần giao dịch cục bộ cho các thao tác trên channel, và hiểu giới hạn của nó.
- Không xem **channelTransacted=true** là lời giải cho dual-write giữa RabbitMQ và DB.
- Publisher confirms và AMQP transactions là hai mô hình xác nhận khác nhau, không dùng đồng thời trên cùng channel.
- Với thay đổi nghiệp vụ bắt buộc có sự kiện sau commit, lựa chọn phổ biến là **Transactional Outbox** và consumer **idempotent**.

## 3. Transactional Outbox: ghi dữ liệu nghiệp vụ và ý định phát sự kiện cùng một DB transaction

Ý tưởng: thay vì gửi RabbitMQ ngay trong giao dịch tạo đơn, lưu một hàng **outbox_event** trong **chính cơ sở dữ liệu** đang chứa đơn hàng. Hai bản ghi cùng commit hoặc cùng rollback. Một tiến trình độc lập đọc outbox rồi gửi sang RabbitMQ, có cơ chế thử lại nếu gặp lỗi.

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant DB as PostgreSQL
    participant Relay as Outbox Relay
    participant MQ as RabbitMQ
    participant Consumer as Inventory Consumer
    API->>DB: BEGIN; INSERT order; INSERT outbox
    DB-->>API: COMMIT thành công
    Relay->>DB: Lấy outbox chưa gửi (claim)
    DB-->>Relay: eventId + payload
    Relay->>MQ: Publish OrderCreated(eventId)
    MQ-->>Relay: Publisher confirm (+ kiểm tra return)
    Relay->>DB: Đánh dấu outbox SENT
    MQ->>Consumer: Giao sự kiện
    Consumer->>DB: Giao dịch nghiệp vụ + inbox
    DB-->>Consumer: COMMIT
    Consumer-->>MQ: ACK
~~~

### 3.1. Schema minh họa trên PostgreSQL

~~~sql
CREATE TABLE outbox_event (
    id              uuid PRIMARY KEY,             -- đồng thời là eventId
    aggregate_type  varchar(80) NOT NULL,
    aggregate_id    uuid NOT NULL,
    event_type      varchar(120) NOT NULL,
    payload         jsonb NOT NULL,
    status          varchar(16) NOT NULL DEFAULT 'PENDING',
    attempts        integer NOT NULL DEFAULT 0,
    available_at    timestamptz NOT NULL DEFAULT now(),
    claimed_until   timestamptz,
    lease_token     uuid,
    created_at      timestamptz NOT NULL DEFAULT now(),
    published_at    timestamptz,
    CONSTRAINT outbox_status_check
        CHECK (status IN ('PENDING', 'CLAIMED', 'SENT'))
);

CREATE INDEX outbox_pending_idx
    ON outbox_event (available_at, created_at)
    WHERE status = 'PENDING';
~~~

**id** của hàng outbox là định danh sự kiện bất biến. Khi gửi lại, relay phải giữ nguyên **eventId** và nội dung sự kiện, không phát sinh ID mới. **payload** nên bao gồm loại sự kiện, phiên bản hợp đồng dữ liệu, thời điểm phát sinh và các khóa nghiệp vụ cần thiết; tuyệt đối không dựa vào việc consumer đọc được các thực thể Java của service nguồn.

### 3.2. Ghi outbox ngay trong transaction tạo đơn

Ví dụ rút gọn dưới đây dùng Spring Data JPA cho đơn hàng và **JdbcTemplate** cho outbox. Hai thao tác phải sử dụng **cùng DataSource và transaction manager** được cấu hình để tham gia một giao dịch DB.

~~~java
public record OrderCreatedEvent(
        UUID eventId,
        UUID orderId,
        Instant occurredAt,
        int schemaVersion) {}

@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public OrderApplicationService(
            OrderRepository orders, JdbcTemplate jdbc, ObjectMapper mapper) {
        this.orders = orders;
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Transactional
    public UUID createOrder(CreateOrderCommand command)
            throws JsonProcessingException {
        Order order = orders.save(Order.from(command));
        OrderCreatedEvent event = new OrderCreatedEvent(
                UUID.randomUUID(), order.getId(), Instant.now(), 1);

        jdbc.update("""
                INSERT INTO outbox_event
                    (id, aggregate_type, aggregate_id, event_type, payload)
                VALUES (?, 'Order', ?, 'OrderCreated', CAST(? AS jsonb))
                """,
                event.eventId(),
                event.orderId(),
                mapper.writeValueAsString(event));

        return order.getId();
    }
}
~~~

Nếu insert outbox thất bại, toàn bộ giao dịch tạo đơn rollback. Nếu insert đơn hàng thất bại, outbox cũng rollback. API có thể trả về sau DB commit, **không cần chờ RabbitMQ hoạt động**; việc phát thông điệp diễn ra bất đồng bộ.

Lưu ý về Spring transaction: lời gọi **@Transactional** cần đi qua Spring proxy, nên **self-invocation** trong cùng bean có thể không kích hoạt advice. Không đặt hai thao tác lên hai DB hoặc hai transaction manager độc lập rồi giả định tính nguyên tử.

### 3.3. Relay claim bản ghi theo lô, tránh nhiều instance phát trùng đồng thời

Trong nhiều replica, chỉ truy vấn **SELECT ... WHERE status = 'PENDING'** rồi cùng gửi có thể khiến nhiều instance cùng xử lý một hàng. Một cách là **claim có lease** bằng giao dịch DB ngắn. Ví dụ PostgreSQL (tham số **:batchSize** và **:leaseToken** được truyền từ code):

~~~sql
WITH picked AS (
    SELECT id
    FROM outbox_event
    WHERE (status = 'PENDING' AND available_at <= now())
       OR (status = 'CLAIMED' AND claimed_until < now())
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT :batchSize
)
UPDATE outbox_event AS e
SET status = 'CLAIMED',
    lease_token = :leaseToken,
    claimed_until = now() + interval '60 seconds',
    attempts = attempts + 1
FROM picked
WHERE e.id = picked.id
RETURNING e.id, e.event_type, e.payload, e.lease_token;
~~~

Transaction claim nên **commit trước khi gọi RabbitMQ**, tránh giữ khóa DB trong lúc chờ mạng. Sau khi broker xác nhận thành công, relay đánh dấu đã phát với điều kiện vẫn sở hữu lease:

~~~sql
UPDATE outbox_event
SET status = 'SENT',
    published_at = now(),
    lease_token = NULL,
    claimed_until = NULL
WHERE id = :eventId
  AND status = 'CLAIMED'
  AND lease_token = :leaseToken;
~~~

Nếu publish thất bại, đưa hàng về **PENDING** với **available_at** trong tương lai (exponential backoff có jitter), ghi nhận lỗi và thử lại. Khi relay chết trong lúc đang giữ lease, hàng **CLAIMED** hết hạn có thể được một instance khác claim lại. Trong môi trường tải lớn, cần điều chỉnh lease đủ dài so với timeout publish, tránh nhiều relay cùng gửi một hàng; nhưng vẫn phải chấp nhận giao lại trùng và dựa vào idempotency phía nhận.

### 3.4. Publisher confirms và mandatory returns

Cấu hình minh họa:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Một hàm gửi có thể chờ kết quả **publisher confirm** cho từng sự kiện outbox:

~~~java
// Hàm minh họa một lần publish; caller quản lý claim, retry và đánh dấu SENT.
void publishOne(OutboxRow row, RabbitTemplate rabbitTemplate)
        throws Exception {
    CorrelationData correlation = new CorrelationData(row.id().toString());

    rabbitTemplate.convertAndSend(
            "domain.events",
            "order.created",
            row.payloadJson(),
            message -> {
                message.getMessageProperties()
                        .setMessageId(row.id().toString());
                message.getMessageProperties()
                        .setContentType(MessageProperties.CONTENT_TYPE_JSON);
                message.getMessageProperties()
                        .setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                return message;
            },
            correlation);

    CorrelationData.Confirm confirm =
            correlation.getFuture().get(10, TimeUnit.SECONDS);

    if (!confirm.isAck()) {
        throw new IllegalStateException(
                "RabbitMQ nack: " + confirm.getReason());
    }
    if (correlation.getReturned() != null) {
        throw new IllegalStateException(
                "Message was returned as unroutable");
    }
}
~~~

Trong Spring AMQP, với **publisher-confirm-type=correlated**, publisher có thể nhận kết quả qua **CorrelationData**. Khi bật returns và mandatory, thông tin returned message được thiết lập trước khi confirm tương ứng hoàn tất; relay cần xem **cả** confirm và return. Một lệnh publish được broker **ack** vẫn có thể bị **return** nếu exchange không tìm được queue phù hợp. Nếu timeout hoặc kết nối đứt, kết quả có thể **không xác định**: broker đã nhận nhưng ứng dụng chưa kịp biết. Vì thế **không đánh dấu SENT** và cho phép gửi lại với cùng eventId.

Trong ứng dụng thực tế, có thể dùng callback và xử lý confirm bất đồng bộ thay vì block một thread cho từng sự kiện. Dù cách nào, chỉ cập nhật **SENT** sau khi có bằng chứng publish đạt yêu cầu của hệ thống. Bảo đảm độ bền phía broker còn phụ thuộc loại queue, độ bền queue/exchange, delivery mode và cấu hình cụm RabbitMQ.

## 4. Ranh giới xử lý ở consumer: commit DB trước, ack sau

Ngay cả khi producer dùng outbox, RabbitMQ vẫn có thể **giao lại cùng một sự kiện**. Ví dụ consumer cập nhật DB thành công rồi tiến trình chết trước khi broker nhận **ack**. Broker thấy delivery chưa được xác nhận và sẽ gửi lại. Nếu consumer không chống trùng, tồn kho có thể bị giữ chỗ hai lần.

Một thứ tự an toàn cho dữ liệu trong DB của consumer là:

1. Nhận thông điệp và đọc **eventId**, kiểm tra định dạng/hợp đồng sự kiện.
2. Trong **một DB transaction**, ghi dấu sự kiện đã xử lý (**inbox**) và cập nhật nghiệp vụ.
3. Đợi **DB commit thành công**.
4. Sau đó mới **ack** delivery với RabbitMQ.

Nếu bước 2 thất bại, rollback cả inbox và cập nhật nghiệp vụ; thông điệp chưa được ack phải được retry hoặc đưa vào dead-letter queue theo chính sách lỗi. Nếu bước 4 thất bại, thông điệp có thể bị gửi lại nhưng inbox giúp bỏ qua tác động lặp.

### 4.1. Bảng inbox và idempotent handler

~~~sql
CREATE TABLE processed_event (
    consumer_name varchar(100) NOT NULL,
    event_id      uuid NOT NULL,
    processed_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Ví dụ **InventoryService** xử lý event trong một transaction DB:

~~~java
@Service
public class InventoryService {
    private final JdbcTemplate jdbc;
    private final InventoryRepository inventory;

    public InventoryService(
            JdbcTemplate jdbc, InventoryRepository inventory) {
        this.jdbc = jdbc;
        this.inventory = inventory;
    }

    @Transactional
    public void reserveForOrder(OrderCreatedEvent event) {
        int inserted = jdbc.update("""
                INSERT INTO processed_event (consumer_name, event_id)
                VALUES ('inventory-reservation', ?)
                ON CONFLICT DO NOTHING
                """, event.eventId());

        if (inserted == 0) {
            return; // eventId này đã commit thành công trước đó
        }

        inventory.reserve(event.orderId()); // cập nhật DB cùng transaction
    }
}
~~~

Khóa chính **(consumer_name, event_id)** vừa ngăn hai bản tin trùng được xử lý ở hai transaction đồng thời, vừa cho phép nhiều nhóm consumer độc lập dùng chung hạ tầng inbox. Nếu **inventory.reserve** ném exception, insert inbox cũng rollback; thông điệp có thể thử lại. Với các nghiệp vụ có nhiều loại sự kiện cùng tác động một thực thể, vẫn cần khóa/điều kiện nghiệp vụ (ví dụ unique theo **order_id**, kiểm tra trạng thái đơn, optimistic locking); inbox theo eventId chỉ chống xử lý trùng **cùng một sự kiện**.

### 4.2. Ack sau khi giao dịch xử lý trả về thành công

~~~java
@Component
public class OrderCreatedListener {
    private final ObjectMapper mapper;
    private final InventoryService inventoryService;

    public OrderCreatedListener(
            ObjectMapper mapper, InventoryService inventoryService) {
        this.mapper = mapper;
        this.inventoryService = inventoryService;
    }

    @RabbitListener(queues = "order.created.queue", ackMode = "MANUAL")
    public void onMessage(Message message, Channel channel)
            throws IOException {
        long deliveryTag = message.getMessageProperties().getDeliveryTag();
        try {
            OrderCreatedEvent event = mapper.readValue(
                    message.getBody(), OrderCreatedEvent.class);

            // Gọi qua bean khác: transaction của InventoryService
            // đã commit khi phương thức này trả về thành công.
            inventoryService.reserveForOrder(event);
        } catch (Exception processingFailure) {
            // Ví dụ với queue đã cấu hình DLX; production cần phân loại
            // lỗi tạm thời để retry có giới hạn và backoff.
            channel.basicNack(deliveryTag, false, false);
            return;
        }
        channel.basicAck(deliveryTag, false);
    }
}
~~~

Mã trên dùng **MANUAL ack** để thấy rõ mốc commit và ack. **ackMode=AUTO** của listener container cũng có thể phù hợp nếu listener hoàn tất sau khi transaction DB đã commit; container ack khi lời gọi listener thành công. Tuy nhiên cần biết cấu hình transaction/advice của listener container và chính sách xử lý exception để không ack nhầm trước commit.

Lưu ý:

- Đừng gọi **basicAck** bên trong một phương thức **@Transactional** khi transaction đó vẫn chưa commit.
- **basicNack(requeue=false)** chỉ đưa đến DLQ khi queue có dead-letter exchange/routing phù hợp; nếu không, thông điệp có thể bị loại bỏ. Production nên phân biệt lỗi tạm thời (DB timeout) với lỗi vĩnh viễn (payload sai phiên bản), dùng retry có giới hạn, backoff và DLQ.
- Nếu **basicAck** gặp sự cố sau DB commit, hãy chấp nhận khả năng redelivery; inbox xử lý trường hợp này.
- Không thực hiện side effect bên ngoài DB (gửi email, gọi payment API, publish sự kiện kế tiếp) trực tiếp bên trong transaction inbox mà giả định tất cả nguyên tử. Nếu cần, tạo **outbox mới** ở service consumer và xử lý theo cùng mẫu.

## 5. Ma trận lỗi: điều gì xảy ra và hệ thống phục hồi ra sao?

| Thời điểm lỗi | Trạng thái sau lỗi | Cách phục hồi an toàn |
| --- | --- | --- |
| Transaction tạo đơn rollback trước commit | Không có đơn và không có outbox | Trả lỗi yêu cầu; không phát sự kiện |
| Đơn và outbox đã commit, relay chưa gửi | Outbox ở PENDING/CLAIMED; queue chưa có sự kiện | Relay quét lại hoặc chờ lease hết hạn rồi gửi |
| Broker đã nhận nhưng confirm bị timeout/mất | Kết quả publish không chắc chắn; outbox chưa SENT | Gửi lại **cùng eventId**; consumer chống trùng |
| Broker confirm ack nhưng message bị return | Không có queue nhận thông điệp như mong đợi | Không đánh dấu SENT; sửa exchange/binding/routing rồi retry |
| Relay nhận confirm nhưng chết trước khi đánh dấu SENT | Có thể đã có thông điệp trong queue, outbox vẫn cần retry | Gửi lại; dedupe ở consumer |
| Consumer lỗi trước khi DB commit | Inbox và nghiệp vụ đều rollback | Retry có backoff hoặc DLQ |
| Consumer DB commit thành công, tiến trình chết trước ack | Nghiệp vụ đã cập nhật; RabbitMQ có thể giao lại | Inbox nhận diện eventId và bỏ qua tác động lặp, sau đó ack |
| Consumer ack trước khi DB commit rồi DB rollback | Broker có thể đã xóa delivery nhưng nghiệp vụ chưa làm | **Lỗi thiết kế**; sửa thứ tự commit trước ack |

Từ ma trận này rút ra **bảo đảm thực tế**: outbox + publisher confirms + retry tạo luồng phát **at-least-once**; inbox + commit trước ack làm cho **tác động DB của một eventId** có thể được thực hiện đúng một lần trong phạm vi giao dịch DB. Đây **không phải** cam kết exactly-once end-to-end cho mọi side effect, và thứ tự các event khác nhau không được RabbitMQ/outbox tự động bảo đảm.

## 6. So sánh các cách triển khai theo yêu cầu nhất quán

| Cách làm | Đặc điểm | Phù hợp |
| --- | --- | --- |
| Ghi DB rồi gọi **RabbitTemplate** trực tiếp | Dễ viết; có khoảng hở crash giữa hai hệ thống | Thông báo best-effort, có thể chấp nhận thiếu sự kiện |
| **@TransactionalEventListener(phase=AFTER_COMMIT)** rồi publish | Chỉ publish sau khi DB đã commit; vẫn mất sự kiện nếu tiến trình chết trước/trong publish, không có hàng đợi bền vững để khôi phục | Hệ thống chấp nhận best-effort hoặc có cơ chế phục hồi riêng |
| **channelTransacted=true** với external DB transaction | Đồng bộ best-efforts 1PC; vẫn có khoảng hở khi một commit thành công và commit kia thất bại | Trường hợp hiểu rõ giới hạn, không đòi hỏi atomic cross-resource |
| **Transactional Outbox + confirms + retry** | Không mất ý định publish khi business transaction commit; chấp nhận gửi trùng | Sự kiện nghiệp vụ quan trọng, cần phục hồi và quan sát được |
| **Outbox + idempotent consumer/inbox** | Bảo vệ cả chiều phát và chiều xử lý DB khi redelivery | Quy trình bất đồng bộ cần độ tin cậy cao |

Nếu chỉ cần giảm độ trễ và chấp nhận thất lạc hiếm gặp, phương án đơn giản có thể đủ. Với đơn hàng, thanh toán, giữ hàng, cập nhật quyền truy cập hoặc dữ liệu kiểm toán, nên quy định rõ mức nhất quán trước khi chọn mô hình.

## 7. Những chi tiết vận hành dễ bị bỏ sót

### 7.1. Idempotency và khóa nghiệp vụ

**eventId** phải cố định qua các lần retry; các service độc lập có thể xử lý cùng eventId nhưng mỗi service lưu dấu dưới **consumer_name** riêng. Nếu hai sự kiện khác ID cùng yêu cầu thực hiện một hành động nghiệp vụ một lần (ví dụ cùng paymentId), cần thêm unique constraint theo khóa nghiệp vụ chứ không chỉ theo eventId.

Việc consumer bỏ qua một eventId trùng phải xảy ra **sau khi chứng cứ xử lý trước đó đã commit**. Không dùng cache Redis không giao dịch với DB làm bằng chứng duy nhất đã xử lý nếu mất cache có thể gây xử lý lặp. Có thể dùng Redis để tối ưu nhưng ràng buộc nhất quán cần được bảo đảm tại DB hoặc thiết kế nghiệp vụ.

### 7.2. Thứ tự sự kiện

Hai event của cùng đơn hàng, chẳng hạn **OrderCreated** và **OrderCancelled**, có thể đến consumer khác thứ tự do nhiều relay, retry, nhiều queue hoặc consumer song song. Nếu thứ tự quan trọng, đưa **aggregateId** và **sequence/version** vào payload, chọn chiến lược xuất bản tuần tự theo aggregate hoặc kiểm tra version/trạng thái tại consumer. Chỉ sắp xếp theo **created_at** trong truy vấn outbox không đủ để bảo đảm thứ tự xử lý end-to-end.

### 7.3. Hợp đồng dữ liệu và bảo mật

Đặt **schemaVersion**, định dạng thời gian UTC và kiểu ID ổn định; thêm trace/correlation ID để nối log từ HTTP request đến outbox, RabbitMQ và consumer. Tránh đưa token, mật khẩu, thông tin thẻ và dữ liệu cá nhân không cần thiết vào payload hoặc log lỗi. Consumer phải xác thực/validate trường bắt buộc và có chiến lược khi không hỗ trợ version sự kiện.

### 7.4. Giám sát và xử lý sự cố

Nên theo dõi ít nhất:

- **Outbox backlog**: số hàng PENDING/CLAIMED, tuổi hàng cũ nhất, thời gian từ DB commit đến publish.
- **Publish health**: tỉ lệ confirm nack/timeout, returned messages, số lần retry, bản ghi hết lease hoặc mắc kẹt.
- **Consumer health**: số message chưa ack, tỉ lệ redelivery, độ trễ xử lý, lỗi database, độ sâu queue và DLQ.
- **Dữ liệu nghiệp vụ**: đối soát số đơn đã commit so với sự kiện đã phát và tác động tại downstream, có quy trình replay an toàn.

Cần cảnh báo khi outbox không thoát trạng thái chưa gửi sau ngưỡng thời gian, khi DLQ tăng hoặc khi độ trễ tăng liên tục. Không xóa hàng thất bại để “dọn queue”; giữ thông tin lỗi, hỗ trợ retry/replay có kiểm soát và chính sách lưu trữ hàng **SENT**.

## 8. Kiểm thử ranh giới giao dịch

Kiểm thử đơn vị cho việc gọi phương thức là chưa đủ. Một bộ kiểm thử tích hợp nên dùng PostgreSQL và RabbitMQ thật trong môi trường cô lập (ví dụ Testcontainers), sau đó tạo có chủ đích các tình huống sau:

1. **Rollback nguyên tử:** gây lỗi khi ghi outbox và xác nhận không có đơn hàng được commit.
2. **Publisher không sẵn sàng:** commit đơn và outbox khi RabbitMQ tắt; khởi động lại relay và kiểm tra event được phát sau đó.
3. **Mất confirm:** giả lập timeout sau khi broker đã nhận; kiểm tra relay gửi lại **cùng eventId**, consumer chỉ tác động DB một lần.
4. **Unroutable publish:** publish vào exchange có routing key không khớp; xác nhận returns được nhận và outbox chưa SENT.
5. **Crash sau consumer DB commit:** không ack, kích hoạt redelivery; kiểm tra chỉ một bản ghi inbox và một thay đổi tồn kho.
6. **Xử lý song song:** gửi cùng eventId vào nhiều consumer instance; unique constraint + transaction phải ngăn tác động lặp.
7. **Dữ liệu lỗi:** gửi payload sai version hoặc thiếu trường; xác minh retry/DLQ đúng chính sách, không lặp vô hạn.
8. **Kiểm thử thứ tự:** nếu nghiệp vụ yêu cầu ordering, đảo thứ tự hai sự kiện của cùng aggregate và kiểm tra handler thực thi đúng quy tắc version.

Ví dụ tiêu chí chấp nhận cho ca tạo đơn: **Sau khi API trả thành công, hoặc event OrderCreated sẽ được xử lý cuối cùng, hoặc hệ thống giữ lại một outbox record có thể quan sát và retry; mọi lần giao lại cùng eventId không làm giữ hàng thêm lần thứ hai.** Tiêu chí này cụ thể hơn câu “DB và RabbitMQ nằm trong cùng một @Transactional”.

## 9. Checklist trước khi đưa vào production

- [ ] Ghi **business row + outbox row** trong **một DB transaction**; có ràng buộc hợp đồng dữ liệu và khóa idempotency.
- [ ] Relay có claim/lease, retry với backoff, timeout, confirm/return handling và giám sát backlog.
- [ ] Exchange, binding, queue durability, delivery mode và chính sách sao chép broker đáp ứng mức tin cậy cần thiết.
- [ ] Consumer commit dữ liệu và inbox trước khi ack, xử lý redelivery và lỗi vĩnh viễn có DLQ.
- [ ] Các side effect của consumer sang hệ thống thứ ba có chiến lược idempotency/outbox riêng.
- [ ] Có kiểm thử crash ở những khoảng hở giữa DB commit, publish confirm, đánh dấu SENT và consumer ack.
- [ ] Có đối soát, khả năng replay, alert và quy tắc lưu trữ/xóa dữ liệu outbox/inbox.

**Nguyên tắc cần nhớ:** **@Transactional** chỉ bảo vệ transaction manager và tài nguyên mà nó quản lý. Khi RabbitMQ và cơ sở dữ liệu cùng tham gia một nghiệp vụ, cách an toàn thường là **commit ý định phát sự kiện cùng dữ liệu nghiệp vụ bằng outbox, publish có xác nhận và thử lại, xử lý consumer có inbox/idempotency, rồi ack sau DB commit**. Thiết kế như vậy chấp nhận tính nhất quán cuối cùng và khả năng thông điệp trùng, đồng thời cung cấp đường phục hồi rõ ràng cho các sự cố thực tế.
