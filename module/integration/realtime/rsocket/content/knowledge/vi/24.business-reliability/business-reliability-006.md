# Phối hợp transaction cơ sở dữ liệu với việc gửi thông điệp

Một thao tác nghiệp vụ thường cần vừa cập nhật cơ sở dữ liệu vừa thông báo cho hệ thống khác. Ví dụ, khi tạo đơn hàng, dịch vụ phải lưu đơn hàng và phát sự kiện <code>OrderCreated</code> để kho, thanh toán hoặc thông báo tiếp tục xử lý.

Hai thao tác này thuộc hai hệ thống độc lập: database và kênh truyền thông điệp. Transaction ACID của database không tự bao trùm một lần gửi RSocket, Kafka hay message broker. Nếu gọi gửi thông điệp ngay trong hoặc ngay sau transaction, một lỗi tiến trình hoặc lỗi mạng có thể làm trạng thái dữ liệu và thông điệp không khớp nhau.

Transactional Outbox giải quyết vấn đề đó bằng cách ghi sự kiện cần gửi vào cùng transaction với dữ liệu nghiệp vụ. Một relay riêng đọc các bản ghi đã commit rồi gửi thông điệp. Ở phía nhận, Inbox và idempotency giúp xử lý an toàn khi thông điệp được gửi lại. Đây là cách phối hợp thực tế cho hệ thống Spring Boot, Reactor và RSocket.

## 1. Vấn đề dual-write

Giả sử dịch vụ Order cần lưu đơn hàng vào database rồi gửi sự kiện sang dịch vụ Inventory. Nếu thực hiện hai thao tác độc lập, có hai thứ tự thường gặp:

**Gửi thông điệp trước, commit database sau**

1. Dịch vụ gửi <code>OrderCreated</code>.
2. Inventory nhận sự kiện và giữ hàng.
3. Transaction lưu đơn hàng bị rollback hoặc database không commit được.
4. Inventory đã thay đổi trạng thái nhưng đơn hàng nguồn không tồn tại.

**Commit database trước, gửi thông điệp sau**

1. Database commit đơn hàng thành công.
2. Process dừng đột ngột trước khi gửi <code>OrderCreated</code>.
3. Đơn hàng tồn tại nhưng Inventory không biết để giữ hàng.

| Thứ tự | Lỗi xảy ra | Hậu quả |
| --- | --- | --- |
| Gửi rồi mới commit | Database rollback | Hệ thống nhận thông điệp về một thay đổi chưa được commit. |
| Commit rồi mới gửi | Process crash hoặc mất kết nối trước khi gửi | Dữ liệu đã đổi nhưng không có thông điệp tương ứng. |
| Gửi và chờ phản hồi trong transaction DB | Network timeout hoặc peer chậm | Transaction DB bị giữ lâu; phản hồi có thể không cho biết chắc chắn peer đã commit hay chưa. |

Đây là dual-write problem: ứng dụng phải cập nhật hai hệ thống nhưng không có một transaction nguyên tử chung bao trùm cả hai.

Không nên giữ transaction database mở trong lúc gọi mạng để cố tạo cảm giác nguyên tử. Việc đó kéo dài thời gian giữ lock và connection, làm tăng deadlock, timeout và tải database. RSocket cũng không cung cấp transaction phân tán ACID giữa database và peer.

## 2. Vì sao @TransactionalEventListener(AFTER_COMMIT) chưa đủ?

Spring có <code>@TransactionalEventListener(phase = AFTER_COMMIT)</code> để chạy listener sau khi transaction commit. Cơ chế này hữu ích khi cần phản ứng sau commit trong cùng ứng dụng, nhưng tự nó không bảo đảm thông điệp được phát bền vững.

Ví dụ:

1. Transaction commit thành công.
2. Process dừng trước khi listener gửi thông điệp.
3. Khi process khởi động lại, event trong bộ nhớ không tự xuất hiện lại.

Listener cũng có thể gặp lỗi gửi sau commit, lúc đó transaction database đã hoàn tất và không thể rollback để khôi phục tính nhất quán. Có thể dùng AFTER_COMMIT để đánh thức một outbox relay nhằm giảm độ trễ, nhưng bản ghi outbox trong database mới là nguồn sự thật bền vững.

## 3. Transactional Outbox hoạt động như thế nào?

Trong một transaction database duy nhất, ứng dụng:

1. Ghi hoặc cập nhật dữ liệu nghiệp vụ.
2. Tạo một bản ghi outbox chứa sự kiện cần phát.
3. Commit cả hai thay đổi cùng nhau.

Sau commit, một relay độc lập đọc outbox và gửi sự kiện tới đích. Nếu transaction rollback, cả dữ liệu nghiệp vụ và outbox đều không tồn tại. Nếu transaction commit, sự kiện vẫn còn trong outbox kể cả khi process dừng trước khi gửi.

~~~text
Client
  |
  | command: create order
  v
Order Service
  |
  |--- BEGIN DATABASE TRANSACTION ----------------------+
  |                                                      |
  |  INSERT/UPDATE business_order                       |
  |  INSERT outbox_event                                 |
  |                                                      |
  |--- COMMIT -------------------------------------------+
  |
  v
Outbox Relay (polling hoặc CDC)
  |
  | REQUEST_RESPONSE + eventId + payload
  v
Inventory Service
  |
  |--- BEGIN DATABASE TRANSACTION ----------------------+
  |  INSERT inbox_message (unique messageId)             |
  |  UPDATE inventory/business state                     |
  |--- COMMIT -------------------------------------------+
  |
  | application acknowledgement
  v
Outbox Relay đánh dấu event đã được xác nhận
~~~

Outbox không cần distributed transaction hoặc two-phase commit giữa database và message transport. Nó bảo đảm việc ghi nhận ý định phát sự kiện nguyên tử với thay đổi dữ liệu nguồn; relay sẽ thử gửi cho tới khi thành công hoặc chuyển sang trạng thái cần xử lý.

## 4. Thiết kế bảng outbox

Một bảng outbox quan hệ thường lưu định danh sự kiện, aggregate nguồn, loại sự kiện, payload và trạng thái gửi. Ví dụ PostgreSQL:

~~~sql
CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(150) NOT NULL,
    aggregate_sequence BIGINT NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_owner VARCHAR(100),
    lease_until TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    last_error TEXT
);

CREATE INDEX idx_outbox_pending
    ON outbox_event (next_attempt_at, occurred_at)
    WHERE status IN ('PENDING', 'RETRY');

CREATE UNIQUE INDEX uq_outbox_aggregate_sequence
    ON outbox_event (aggregate_type, aggregate_id, aggregate_sequence);
~~~

Các trường có ý nghĩa:

| Trường | Mục đích |
| --- | --- |
| <code>event_id</code> | ID duy nhất, được dùng làm idempotency key ở consumer. |
| <code>aggregate_type</code>, <code>aggregate_id</code> | Xác định đối tượng nghiệp vụ phát sinh sự kiện. |
| <code>aggregate_sequence</code> | Số thứ tự sự kiện trong một aggregate để phát hiện hoặc giữ thứ tự. |
| <code>event_type</code> | Tên loại sự kiện, ví dụ <code>OrderCreated</code>. |
| <code>payload</code> | Nội dung sự kiện đã serialize. |
| <code>status</code> | Trạng thái như PENDING, IN_PROGRESS, RETRY, PUBLISHED hoặc DEAD. |
| <code>attempts</code>, <code>next_attempt_at</code> | Điều khiển retry và backoff. |
| <code>lease_owner</code>, <code>lease_until</code> | Claim bản ghi khi nhiều relay chạy song song. |
| <code>published_at</code> | Thời điểm relay nhận application acknowledgement. |
| <code>last_error</code> | Lỗi gần nhất, đã được làm sạch thông tin nhạy cảm. |

Unique index theo aggregate sequence phù hợp khi mỗi version aggregate chỉ tạo một event. Nếu một transaction phát nhiều event cho cùng version, hãy dùng sequence riêng cho từng event hoặc thêm ordinal vào khóa duy nhất.

Không lưu toàn bộ entity JPA vào outbox. Hãy tạo event payload có schema rõ ràng, chỉ chứa dữ liệu cần cho consumer. Thêm event version hoặc schema version để hỗ trợ thay đổi hợp đồng theo thời gian.

## 5. Ghi dữ liệu nghiệp vụ và outbox trong cùng transaction

Ví dụ dưới đây dùng Spring transaction imperative với JDBC/JPA. Repository của đơn hàng và outbox phải cùng tham gia một transaction manager và cùng database transaction.

Định nghĩa event:

~~~java
public record OrderCreated(
    UUID eventId,
    UUID orderId,
    long sequence,
    Instant occurredAt,
    BigDecimal total
) {}
~~~

Service tạo đơn hàng:

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
    public UUID createOrder(CreateOrder command) {
        Order order = Order.create(command);
        orders.save(order);

        OrderCreated event = new OrderCreated(
            UUID.randomUUID(),
            order.id(),
            order.version(),
            Instant.now(),
            order.total()
        );

        try {
            outbox.insert(
                event.eventId(),
                "Order",
                order.id().toString(),
                event.sequence(),
                "OrderCreated",
                objectMapper.writeValueAsString(event)
            );
        } catch (JsonProcessingException error) {
            throw new IllegalStateException(
                "Cannot serialize OrderCreated event", error
            );
        }

        return order.id();
    }
}
~~~

<code>orders.save(...)</code> và <code>outbox.insert(...)</code> cùng commit hoặc cùng rollback. Nếu serialize event hoặc insert outbox thất bại, exception làm transaction rollback; đơn hàng không bị lưu một mình.

Trong ứng dụng thực tế, repository outbox có thể dùng <code>JdbcTemplate</code>, Spring Data JDBC hoặc JPA. Điều quan trọng là hai thao tác tham gia cùng một transaction vật lý. Nếu chúng dùng hai datasource hoặc hai transaction manager độc lập, annotation <code>@Transactional</code> thông thường không tự tạo ra tính nguyên tử giữa chúng.

Không gửi RSocket trực tiếp trong method <code>createOrder</code>. Method chỉ ghi dữ liệu và ý định phát sự kiện. Relay xử lý việc gửi sau khi transaction đã commit.

## 6. Relay gửi sự kiện qua RSocket

Relay đọc các outbox row đã commit, tạo event envelope và gửi tới consumer. Với RSocket, có thể dùng request-response để nhận acknowledgement nghiệp vụ:

~~~java
public record EventEnvelope(
    UUID eventId,
    String aggregateType,
    String aggregateId,
    long sequence,
    String eventType,
    int schemaVersion,
    JsonNode payload
) {}

public record DeliveryAck(
    UUID eventId,
    String status
) {}
~~~

Gửi một sự kiện:

~~~java
Mono<DeliveryAck> send(EventEnvelope event) {
    return requester
        .route("events.consume")
        .data(event)
        .retrieveMono(DeliveryAck.class);
}
~~~

Route <code>events.consume</code> là route do ứng dụng định nghĩa ở consumer. Response <code>DeliveryAck</code> cũng là hợp đồng do ứng dụng định nghĩa. Consumer chỉ nên trả ACK thành công sau khi transaction ghi inbox và cập nhật dữ liệu nghiệp vụ đã commit.

Hai phía cần có encoder/decoder tương thích cho <code>EventEnvelope</code> và <code>DeliveryAck</code>, ví dụ JSON với cùng schema version. Có thể dùng Composite Metadata để mang route, tracing và authentication; không đưa credential vào event payload.

Không coi việc Mono phía client hoàn tất hoặc socket còn mở là bằng chứng dữ liệu đã được lưu ở consumer. Chỉ application acknowledgement theo hợp đồng mới xác nhận consumer đã xử lý ở mức nghiệp vụ mà hệ thống mong muốn.

### Vì sao không dùng Fire-and-Forget cho outbox quan trọng?

RSocket Fire-and-Forget dùng frame REQUEST_FNF và không có response. Theo protocol, FNF là best-effort; responder có thể không xử lý được message nếu SETUP bị từ chối, frame sai định dạng hoặc có vấn đề khác. Sender không nhận được application acknowledgement để biết consumer đã commit dữ liệu hay chưa.

Vì vậy:

- Dùng request-response nếu relay cần xác nhận consumer đã xử lý và commit.
- Có thể dùng FNF cho telemetry hoặc thông báo có thể mất, khi ứng dụng chấp nhận best-effort.
- Nếu cần phát một luồng sự kiện, có thể dùng request-stream/channel nhưng vẫn phải thiết kế ACK, cursor, retry và persistence ở tầng ứng dụng.

Ngay cả request-response cũng không tạo ra exactly-once. Nếu consumer commit xong nhưng response bị mất trên mạng, relay không biết chắc transaction đã hoàn tất và có thể gửi lại. Consumer phải idempotent.

## 7. Claim outbox row và retry an toàn

Polling relay thường chạy theo batch. Khi có nhiều instance relay, chúng phải claim row để tránh cùng xử lý một bản ghi đồng thời. Với PostgreSQL, có thể dùng <code>FOR UPDATE SKIP LOCKED</code> để chọn row chưa được instance khác claim.

Quy trình khuyến nghị:

1. Mở transaction ngắn để chọn batch row đến hạn.
2. Đặt trạng thái IN_PROGRESS, lease owner và lease expiry.
3. Commit transaction claim.
4. Gửi thông điệp qua RSocket ở ngoài transaction database.
5. Nếu nhận ACK đúng event ID, cập nhật trạng thái PUBLISHED và published_at.
6. Nếu timeout hoặc lỗi, tăng attempts và đặt next_attempt_at theo backoff.
7. Nếu process dừng, lease hết hạn để instance khác có thể claim lại.

Không giữ database lock trong lúc chờ response mạng. Lease giúp phục hồi khi relay crash; nó không ngăn được duplicate nếu relay đã gửi thành công nhưng chết trước khi ghi PUBLISHED.

Pseudo-code cho phần gửi:

~~~java
void publishClaimed(OutboxEvent event) {
    EventEnvelope envelope = mapper.toEnvelope(event);

    requester.route("events.consume")
        .data(envelope)
        .retrieveMono(DeliveryAck.class)
        .timeout(Duration.ofSeconds(5))
        .subscribe(
            ack -> {
                if (ack.eventId().equals(event.eventId())
                        && "COMMITTED".equals(ack.status())) {
                    outbox.markPublished(event.eventId());
                } else {
                    outbox.scheduleRetry(
                        event.eventId(), "Unexpected acknowledgement"
                    );
                }
            },
            error -> outbox.scheduleRetry(
                event.eventId(), sanitize(error)
            )
        );
}
~~~

Đây là phác thảo luồng relay; trong production, việc cập nhật trạng thái và giới hạn concurrency cần được quản lý bằng worker lifecycle có kiểm soát. Không tạo subscription không giới hạn cho từng row. Hãy dùng batch size, concurrency cap, timeout, retry policy và shutdown hook để chờ hoặc nhường lại lease khi dừng.

### Backoff và trạng thái lỗi

Retry nên dùng exponential backoff có jitter, ví dụ tăng dần 1 giây, 2 giây, 4 giây, 8 giây và giới hạn ở một mức tối đa. Jitter tránh nhiều relay cùng retry vào một thời điểm sau khi peer phục hồi.

Khi vượt số lần thử:

- Đưa row vào trạng thái DEAD hoặc chuyển sang dead-letter workflow.
- Ghi mã lỗi và thông tin chẩn đoán đã loại bỏ credential.
- Tạo metric và cảnh báo.
- Cho phép operator replay sau khi xử lý nguyên nhân.
- Không xóa row chỉ vì gửi thất bại.

Phân biệt lỗi tạm thời như timeout, connection reset, peer unavailable với lỗi vĩnh viễn như schema không hỗ trợ hoặc event không hợp lệ. Retry lỗi vĩnh viễn vô hạn chỉ làm tăng tải và che khuất vấn đề dữ liệu.

## 8. Inbox và idempotency ở consumer

Outbox relay có thể gửi cùng một event nhiều lần. Điều này xảy ra khi consumer đã commit nhưng ACK bị mất, relay timeout rồi retry, hoặc relay crash trước khi đánh dấu row đã gửi.

Consumer cần lưu message ID đã xử lý. Bảng inbox có unique key theo consumer và event ID:

~~~sql
CREATE TABLE inbox_message (
    consumer_name VARCHAR(100) NOT NULL,
    message_id UUID NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, message_id)
);
~~~

Khi nhận event, consumer thực hiện trong cùng transaction:

1. Insert <code>(consumer_name, message_id)</code> vào inbox.
2. Nếu insert không tạo row vì khóa đã tồn tại, event đã được xử lý trước đó; trả ACK duplicate.
3. Nếu insert thành công, cập nhật dữ liệu nghiệp vụ.
4. Commit cả inbox và business update.
5. Chỉ sau khi commit, trả ACK cho relay.

Ví dụ với PostgreSQL và JDBC:

~~~java
@Service
public class InventoryEventService {

    private final JdbcTemplate jdbc;
    private final InventoryRepository inventory;

    @Transactional
    public DeliveryAck handle(EventEnvelope event) {
        int inserted = jdbc.update("""
            INSERT INTO inbox_message (consumer_name, message_id)
            VALUES (?, ?)
            ON CONFLICT (consumer_name, message_id) DO NOTHING
            """,
            "inventory-service",
            event.eventId()
        );

        if (inserted == 0) {
            return new DeliveryAck(event.eventId(), "DUPLICATE");
        }

        OrderCreated order = decodeOrderCreated(event.payload());
        inventory.reserve(order.orderId(), order.total());

        return new DeliveryAck(event.eventId(), "COMMITTED");
    }
}
~~~

Handler RSocket gọi service transaction:

~~~java
@Controller
public class InventoryRSocketController {

    private final InventoryEventService eventService;

    public InventoryRSocketController(
            InventoryEventService eventService) {
        this.eventService = eventService;
    }

    @MessageMapping("events.consume")
    Mono<DeliveryAck> consume(EventEnvelope event) {
        return Mono.fromCallable(() -> eventService.handle(event))
            .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Ví dụ controller chuyển thao tác JDBC blocking sang bounded elastic. Service transaction là bean riêng, được gọi qua Spring proxy; khi method đồng bộ trả về, interceptor đã hoàn tất commit trước khi controller phát ACK. Nếu commit lỗi, exception được truyền thành lỗi RSocket thay vì ACK thành công.

Nếu consumer dùng R2DBC, hãy dùng reactive repository/DatabaseClient và reactive transaction manager trong cùng Reactor pipeline. Không trộn JDBC blocking và R2DBC transaction rồi kỳ vọng chúng tự tham gia cùng một transaction.

## 9. ACK bị mất sau khi consumer commit

Một tình huống quan trọng:

1. Relay gửi event ID E-100.
2. Consumer insert inbox, cập nhật tồn kho và commit.
3. Consumer gửi ACK.
4. Kết nối bị đứt trước khi relay nhận ACK.
5. Relay không thể phân biệt ACK bị mất với consumer chưa xử lý, nên retry E-100.
6. Consumer insert inbox gặp unique conflict, bỏ qua business update và trả ACK DUPLICATE.
7. Relay đánh dấu outbox row đã được xác nhận.

Kết quả là message có thể được truyền nhiều lần nhưng hiệu ứng nghiệp vụ chỉ được áp dụng một lần trong transaction của consumer.

~~~text
Relay                         Consumer
  |                               |
  |---- event E-100 ------------->|
  |                               | BEGIN
  |                               | INSERT inbox E-100
  |                               | UPDATE inventory
  |                               | COMMIT
  |<--- ACK COMMITTED -------------|
  X ACK bị mất trên mạng            |
  |                               |
  |---- retry E-100 ------------->|
  |                               | INSERT inbox -> duplicate
  |<--- ACK DUPLICATE -------------|
  |                               |
  | mark outbox PUBLISHED          |
~~~

Đây là at-least-once delivery kết hợp idempotent processing. Có thể đạt hiệu ứng nghiệp vụ effectively-once trong phạm vi transaction và khóa idempotency được thiết kế đúng, nhưng không nên quảng cáo là exactly-once end-to-end giữa nhiều hệ thống độc lập.

## 10. Giữ thứ tự sự kiện

Nhiều nghiệp vụ cần xử lý sự kiện theo thứ tự. Ví dụ <code>OrderCreated</code> phải tới trước <code>OrderCancelled</code>. Thứ tự gửi có thể bị đảo nếu nhiều relay xử lý song song các row cùng aggregate.

Một số cách giữ thứ tự:

- Gắn aggregate ID và sequence tăng dần vào mỗi event.
- Claim và gửi tuần tự theo từng aggregate.
- Chỉ gửi sequence kế tiếp sau khi sequence trước đã được xác nhận.
- Nếu dùng broker có partition, chọn aggregate ID làm message key để các event của aggregate đi cùng partition.
- Consumer lưu sequence cuối đã áp dụng và phát hiện event đến sai thứ tự.

Không nên ép toàn hệ thống chạy một luồng gửi duy nhất chỉ để giữ thứ tự toàn cục. Thường chỉ cần bảo đảm thứ tự trong một aggregate hoặc một partition để vẫn tận dụng được concurrency.

Nếu consumer nhận sequence 12 trước sequence 11, có thể giữ event 12 ở trạng thái chờ, yêu cầu replay 11 hoặc phát hiện gap để xử lý theo chính sách. Không âm thầm áp dụng event sai thứ tự nếu phép biến đổi nghiệp vụ không giao hoán.

## 11. Polling publisher hay CDC?

Outbox có hai cách phổ biến để relay đọc sự kiện:

| Cách | Hoạt động | Khi phù hợp |
| --- | --- | --- |
| Polling publisher | Worker truy vấn bảng outbox theo batch và trạng thái. | Hệ thống nhỏ hoặc vừa, cần triển khai đơn giản và kiểm soát trực tiếp. |
| Change Data Capture (CDC) | Connector đọc transaction log của database và phát thay đổi outbox. | Lưu lượng lớn, cần giảm polling và đã có nền tảng CDC/broker. |

Với CDC, Debezium Outbox Event Router có thể đọc thay đổi từ bảng outbox và biến chúng thành message. Các trường như event ID, aggregate type, aggregate ID và payload được ánh xạ thành message key, header hoặc value tùy cấu hình.

Schema ví dụ ở phần 4 dùng tên cột <code>event_id</code>, <code>aggregate_type</code> và <code>aggregate_id</code>. Debezium có tên cột mặc định riêng cho outbox table; nếu giữ schema tùy chỉnh này, cần cấu hình mapping của Outbox Event Router cho đúng tên cột. Có thể chọn cách khác là dùng trực tiếp cấu trúc cột mặc định mà connector mong đợi.

CDC không loại bỏ idempotency ở consumer. Connector, broker hoặc downstream relay vẫn có thể phát lại khi phục hồi offset hay gặp lỗi. Consumer vẫn phải xử lý duplicate.

Nếu muốn đưa sự kiện tới RSocket service, một kiến trúc thường gặp là:

~~~text
Database outbox
      |
      v
Debezium CDC
      |
      v
Message broker / durable log
      |
      v
RSocket gateway hoặc consumer relay
      |
      v
RSocket request-response
      |
      v
Consumer service
~~~

CDC và polling là hai lựa chọn cho vai trò relay từ outbox. Tránh để cả hai cùng phát toàn bộ một bảng outbox nếu chưa thiết kế ownership và deduplication rõ ràng, vì sẽ tạo hai luồng thông điệp trùng nhau.

## 12. Transaction reactive với R2DBC

Nếu ứng dụng dùng R2DBC thay vì JDBC/JPA, có thể ghi business row và outbox row trong một reactive transaction. Spring dùng <code>ReactiveTransactionManager</code> và Reactor Context để gắn connection database với pipeline.

Ví dụ:

~~~java
@Service
public class ReactiveOrderService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public ReactiveOrderService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public Mono<UUID> create(CreateOrder command) {
        return orders.save(Order.from(command))
            .flatMap(order -> {
                OrderCreated event = OrderCreated.from(order);
                return outbox.save(OutboxEvent.from(event))
                    .thenReturn(order.id());
            });
    }
}
~~~

Đoạn code chỉ an toàn khi cả hai repository dùng cùng R2DBC ConnectionFactory và cùng reactive transaction manager. Các thao tác database phải nằm trong cùng reactive pipeline và Reactor Context.

Không gọi RSocket peer hoặc message broker bên trong reactive database transaction. Transaction nên chỉ bao gồm các thao tác local database cần commit nguyên tử. Sau khi pipeline transaction hoàn tất, relay riêng mới gửi sự kiện.

Không trộn kiểu transaction imperative và reactive:

- JDBC/JPA thường dùng <code>PlatformTransactionManager</code> và transaction gắn với thread.
- R2DBC dùng <code>ReactiveTransactionManager</code> và transaction gắn với Reactor Context.
- Một method reactive <code>@Transactional</code> cần trả về Publisher như Mono hoặc Flux.
- Không gọi blocking JDBC trong reactive transaction rồi giả định JDBC tự tham gia transaction R2DBC.

Có thể dùng <code>TransactionalOperator</code> để xác định rõ phạm vi một reactive transaction khi không muốn dùng annotation.

## 13. Những việc outbox không giải quyết thay bạn

Transactional Outbox bảo đảm dữ liệu nguồn và ý định phát sự kiện được commit cùng nhau. Nó không tự giải quyết toàn bộ quy trình phân tán:

- Consumer vẫn cần idempotency và inbox.
- Sự kiện có thể đến trễ hoặc trùng.
- Thứ tự cần được thiết kế theo aggregate/partition.
- Schema event cần versioning và chính sách tương thích.
- Sự cố vĩnh viễn cần dead-letter và quy trình replay.
- Nghiệp vụ gồm nhiều service và nhiều database cần Saga hoặc workflow bù trừ.
- Outbox cần retention, archive và cleanup để tránh tăng dung lượng vô hạn.
- Payload nhạy cảm cần kiểm soát quyền truy cập, mã hóa và retention.

Outbox không làm một chuỗi transaction trên nhiều service trở thành transaction ACID toàn cục. Mỗi service vẫn commit dữ liệu của mình và phát sự kiện tiếp theo; Saga điều phối các bước và hành động bù trừ khi một bước thất bại.

## 14. Quan sát và vận hành

Nên theo dõi các chỉ số sau:

| Metric | Ý nghĩa |
| --- | --- |
| Outbox pending count | Số event đang chờ gửi. |
| Oldest pending age | Tuổi của event chờ lâu nhất; giúp phát hiện relay bị nghẽn. |
| Publish attempts | Số lần gửi lại theo event hoặc theo khoảng thời gian. |
| Publish/ACK latency | Thời gian từ lúc claim tới khi nhận application ACK. |
| Duplicate inbox count | Số lần consumer nhận event đã xử lý. |
| Dead event count | Số event cần can thiệp thủ công. |
| Sequence gap count | Số aggregate bị thiếu hoặc đảo thứ tự event. |
| Lease expiry count | Số row phải claim lại sau khi worker dừng. |

Log nên chứa event ID, aggregate ID, event type, sequence, relay instance và correlation ID. Không ghi credential RSocket, access token hoặc payload chứa dữ liệu nhạy cảm nguyên vẹn.

Đặt cảnh báo khi pending age vượt ngưỡng nghiệp vụ, số DEAD tăng hoặc ACK latency kéo dài. Định nghĩa runbook để kiểm tra consumer, kết nối, schema, retry và replay một event cụ thể.

## 15. Kiểm thử các điểm lỗi

Kiểm thử happy path là chưa đủ. Hãy chủ động tạo lỗi ở ranh giới giữa commit, send và acknowledgement:

| Tình huống | Kết quả cần xác nhận |
| --- | --- |
| Business insert thành công, outbox insert lỗi | Cả hai rollback. |
| Transaction rollback | Không có outbox row để relay phát. |
| Transaction commit, process dừng trước khi relay gửi | Event vẫn còn và được gửi sau khi relay phục hồi. |
| Consumer unavailable | Outbox vẫn pending/retry; không đánh dấu published. |
| Consumer commit nhưng ACK bị mất | Relay gửi lại; inbox loại duplicate; business effect không lặp. |
| Relay crash sau ACK trước khi mark published | Event có thể được gửi lại; consumer xử lý idempotent. |
| Nhiều relay cùng chạy | Không claim cùng row đồng thời trong lease hợp lệ. |
| Event đến sai thứ tự | Sequence gap được phát hiện và xử lý theo chính sách. |
| Event schema không hỗ trợ | Không retry vô hạn; chuyển DEAD và phát cảnh báo. |
| Consumer transaction rollback | Không có inbox marker đã commit và không có business update một phần. |

Với integration test, có thể dùng database test thật hoặc Testcontainers để kiểm tra unique constraint, transaction rollback, row claiming và hành vi khi process bị dừng. Kiểm thử RSocket request-response với timeout để mô phỏng trường hợp consumer commit nhưng ACK không tới relay.

## 16. Checklist triển khai

- [ ] Ghi business state và outbox row trong cùng một database transaction.
- [ ] Tạo event ID ổn định và aggregate sequence.
- [ ] Không gọi mạng khi transaction database còn mở.
- [ ] Chọn polling relay hoặc CDC và xác định rõ ownership.
- [ ] Claim row bằng lease để hỗ trợ nhiều relay.
- [ ] Gửi qua RSocket request-response nếu cần application ACK.
- [ ] Chỉ đánh dấu PUBLISHED khi ACK có event ID khớp và trạng thái hợp lệ.
- [ ] Dùng retry có backoff, jitter, timeout và dead-letter.
- [ ] Tạo inbox unique key và cập nhật business state trong cùng transaction ở consumer.
- [ ] Giữ thứ tự theo aggregate nếu nghiệp vụ yêu cầu.
- [ ] Theo dõi outbox lag, duplicate, retry, ACK latency và dead event.
- [ ] Kiểm thử rollback, crash, timeout, duplicate và replay.

## 17. Ghi nhớ

- Dual-write xảy ra khi một thao tác phải cập nhật database và gửi thông điệp tới một hệ thống khác.
- Gửi trước commit có thể phát sự kiện cho dữ liệu rollback; gửi sau commit có thể mất sự kiện nếu process dừng trước khi gửi.
- Transactional Outbox ghi business state và event vào cùng transaction, sau đó relay gửi event đã commit.
- RSocket Fire-and-Forget là best-effort và không có application response; dùng request-response khi cần ACK nghiệp vụ.
- Request-response không bảo đảm exactly-once: ACK có thể mất sau khi consumer đã commit.
- Inbox với unique message ID và business update trong cùng transaction giúp consumer xử lý duplicate an toàn.
- Outbox relay thường có at-least-once delivery; idempotency tạo hiệu ứng nghiệp vụ effectively-once trong phạm vi được thiết kế.
- Dùng aggregate sequence và partition key để giữ thứ tự khi cần.
- Polling publisher và CDC/Debezium là hai cách phổ biến để relay outbox.
- Với R2DBC, dùng reactive transaction manager và giữ mọi thao tác database trong cùng Reactor Context.
- Outbox không thay thế Saga khi nghiệp vụ cần phối hợp nhiều transaction trên nhiều service.

## Tài liệu tham khảo

- [Pattern: Transactional Outbox — microservices.io](https://microservices.io/patterns/data/transactional-outbox.html)
- [Transactional outbox pattern — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
- [Debezium — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)
- [RSocket Protocol — Fire and Forget, Request Response](https://rsocket.io/about/protocol/)
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — Reactive Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
