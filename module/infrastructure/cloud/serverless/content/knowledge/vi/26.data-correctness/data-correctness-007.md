# Consumer inbox và ghi nhận sự kiện đã xử lý

Trong kiến trúc event-driven, một message có thể được giao nhiều lần. Consumer có thể xử lý xong dữ liệu nhưng bị dừng trước khi acknowledge; broker có thể không nhận được ack; function có thể timeout sau khi database đã commit; hoặc cùng một event được publish lặp từ producer. Vì vậy, “mỗi message chỉ đến một lần” không phải giả định an toàn.

**Consumer inbox** là mẫu thiết kế lưu dấu sự kiện đã nhận/xử lý trong database của consumer. Inbox kết hợp với unique constraint và transaction giúp consumer nhận diện duplicate, tránh áp dụng cùng một thay đổi nghiệp vụ nhiều lần. Trong Java serverless, inbox đặc biệt hữu ích cho function được kích hoạt bởi queue, stream, event bus hoặc webhook.

Inbox không tự tạo ra exactly-once delivery trên toàn hệ thống. Nó cung cấp khả năng deduplicate theo một event identity trong phạm vi consumer đã xác định. Muốn bảo đảm tác dụng phụ chỉ xảy ra một lần về mặt nghiệp vụ, việc ghi inbox phải được phối hợp đúng với transaction dữ liệu và với các hệ thống bên ngoài.

Bài học trình bày cách xác định event identity, thiết kế bảng inbox, xử lý duplicate đồng thời, ghi inbox cùng transaction nghiệp vụ, phối hợp ack/retry, xử lý side effect bên ngoài, retention, replay và kiểm thử lỗi.

## 1. Vì sao cần ghi nhận sự kiện đã xử lý?

Các hệ thống message thường ưu tiên giao ít nhất một lần (at-least-once) để giảm nguy cơ mất message. Điều đó có nghĩa cùng một message có thể được giao lại nếu consumer không xác nhận đúng lúc.

Một số tình huống phổ biến:

1. Consumer nhận message và cập nhật database.
2. Database commit thành công.
3. Function bị dừng trước khi acknowledge message.
4. Broker giao lại message.
5. Consumer chạy lại cùng nghiệp vụ.

Nếu không có deduplication, số dư có thể bị trừ hai lần, đơn hàng có thể được tạo trùng hoặc bộ đếm bị tăng lặp.

Một tình huống khác là function xử lý message thành công nhưng response/ack bị mất trên đường mạng. Consumer không biết broker đã ghi nhận ack hay chưa, vì vậy message có thể xuất hiện lại.

### Failure window

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant F as Java Function
    participant D as Database

    B->>F: Deliver event E-42
    F->>D: Update business data
    D-->>F: Commit success
    Note over F: Function bị dừng trước ACK
    B->>F: Redeliver event E-42
    F->>D: Update business data lần nữa
    Note over D: Không có inbox: side effect bị lặp
~~~

Consumer inbox đóng failure window này bằng cách lưu event identity trong cùng transaction với thay đổi dữ liệu nghiệp vụ. Khi event được giao lại, unique key cho biết consumer đã xử lý nó.

## 2. Inbox là gì và khác gì broker acknowledgment?

Inbox là bảng hoặc kho lưu trữ bền vững ở phía consumer. Nó trả lời câu hỏi: “Consumer logic này đã ghi nhận event identity này chưa?”

Broker acknowledgment trả lời câu hỏi khác: “Broker có thể xóa message hoặc tiến consumer offset qua message này chưa?”

Hai việc có liên quan nhưng không thay thế nhau:

- Ghi inbox và cập nhật nghiệp vụ là trách nhiệm của ứng dụng/database.
- Acknowledge, delete message hoặc commit offset là trách nhiệm tích hợp consumer với broker.
- Ack chỉ nên xảy ra sau khi transaction chứa inbox và business update đã commit.
- Nếu commit thành công nhưng ack thất bại, message có thể được giao lại; inbox nhận diện duplicate.
- Nếu ack trước khi commit và transaction sau đó rollback, message có thể bị mất khỏi luồng xử lý trong khi nghiệp vụ chưa được ghi.

Thứ tự an toàn thường là:

1. Nhận event.
2. Validate envelope và xác định event identity.
3. Bắt đầu database transaction.
4. Claim event identity bằng unique constraint.
5. Áp dụng thay đổi nghiệp vụ.
6. Đánh dấu inbox processed.
7. Commit transaction.
8. Acknowledge message theo semantics của broker.

Nếu database và broker không hỗ trợ một distributed transaction chung, vẫn có một cửa sổ commit/ack. Inbox giải quyết cửa sổ đó bằng cách làm cho lần giao lại trở nên an toàn.

## 3. Xác định event identity ổn định

Inbox chỉ deduplicate được nếu biết hai lần giao có đại diện cho cùng một event hay không. Vì vậy, event cần một identity ổn định.

Một event envelope có thể gồm:

~~~json
{
  "eventId": "evt-8f31a2",
  "source": "orders-service",
  "eventType": "order.paid",
  "schemaVersion": 2,
  "aggregateId": "order-918",
  "occurredAt": "2026-11-17T10:20:00Z",
  "payload": {
    "paymentReference": "pay-774"
  }
}
~~~

Các trường có ý nghĩa:

- **eventId:** định danh duy nhất của event do producer tạo và giữ nguyên khi retry/replay.
- **source:** hệ thống hoặc namespace tạo event.
- **eventType:** loại sự kiện để consumer chọn handler.
- **schemaVersion:** phiên bản contract.
- **aggregateId:** định danh thực thể nghiệp vụ như order hoặc account.
- **occurredAt:** thời điểm nghiệp vụ phát sinh; không dùng nó thay event ID.

Không dùng timestamp, payload JSON hoặc random ID được tạo mới ở mỗi lần delivery làm deduplication key.

### Event ID khác business ID

Một order có thể phát sinh nhiều event: order.created, order.paid, order.shipped. Nếu chỉ dùng orderId làm inbox key, consumer có thể vô tình coi các event khác nhau là duplicate.

Ngược lại, một business operation có thể được producer phát thành hai event ID khác nhau do bug hoặc retry ở tầng producer. Inbox theo eventId không nhận ra hai event đó là cùng một tác dụng phụ nghiệp vụ. Với thao tác nhạy cảm, có thể cần thêm business idempotency key hoặc ràng buộc unique theo operation.

### Namespace identity

Không phải mọi nguồn event đều bảo đảm event ID duy nhất toàn cục. Một key an toàn thường kết hợp:

```text
consumer identity + source namespace + event ID
```

Consumer identity là tên logic của handler/subscription cần deduplicate. Hai consumer độc lập có thể cần xử lý cùng event một lần mỗi consumer; vì vậy không nên dùng một bảng global chỉ unique theo eventId nếu các consumer có mục đích khác nhau.

## 4. Event ID theo từng loại broker

| Nguồn | Identity có thể dùng | Lưu ý |
|---|---|---|
| CloudEvents/event bus | source + id | Theo contract CloudEvents, cặp này định danh event |
| SQS | message ID hoặc application event ID | Producer retry bằng một lần send mới có thể tạo message ID khác; application event ID ổn định hơn |
| Kafka | topic + partition + offset, hoặc application event ID | Offset nhận diện record trong log; replay cùng record giữ offset, nhưng producer publish lại có offset mới |
| Kinesis | stream + shard/sequence number, hoặc application event ID | Sequence number gắn với record; event producer phát lại có thể là record mới |
| Pub/Sub | message ID do dịch vụ cấp hoặc application event ID | Publish lại cùng nội dung có thể tạo message ID mới |
| Webhook provider | event ID trong payload/header theo contract | Cần xác minh provider giữ nguyên ID khi retry |
| Database change stream | stream identity + record sequence/version | Phải xác định semantics khi snapshot, restore hoặc reprocess |

Nếu provider có application event ID ổn định, thường nên dùng nó. ID do broker cấp vẫn hữu ích để phân biệt delivery/record cụ thể. Có thể lưu cả hai để truy vết.

Với Kafka, nếu consumer group được reset offset để replay, topic/partition/offset vẫn nhận diện cùng record. Nếu producer phát lại nghiệp vụ thành một record mới, application event ID hoặc business operation ID mới giúp nhận biết quan hệ đó.

## 5. Thiết kế bảng inbox

Một schema tối thiểu cho relational database:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name  VARCHAR(128) NOT NULL,
    event_source   VARCHAR(256) NOT NULL,
    event_id       VARCHAR(256) NOT NULL,
    payload_hash   VARCHAR(128) NOT NULL,
    event_type     VARCHAR(128) NOT NULL,
    status         VARCHAR(24) NOT NULL,
    received_at    TIMESTAMP NOT NULL,
    processed_at   TIMESTAMP NULL,
    PRIMARY KEY (consumer_name, event_source, event_id)
);
~~~

Ý nghĩa:

- `consumer_name`: định danh logic của consumer/subscription.
- `event_source`: namespace producer hoặc event source.
- `event_id`: identity ổn định của event.
- `payload_hash`: phát hiện trường hợp cùng identity nhưng payload khác.
- `event_type`: phục vụ điều tra và routing.
- `status`: trạng thái xử lý theo state machine.
- `received_at`, `processed_at`: thời điểm nhận và hoàn tất.

Unique constraint trên bộ ba consumer/source/event là lớp chống xử lý lặp ở database. Không dựa vào đoạn code kiểu “SELECT xem có chưa rồi INSERT” vì hai invocation đồng thời có thể cùng thấy chưa có record và cùng thực hiện nghiệp vụ.

### Có cần lưu toàn bộ payload?

Không nhất thiết. Nếu message broker hoặc event store đã lưu payload, inbox có thể chỉ lưu identity, hash và metadata. Nếu cần audit hoặc replay độc lập, có thể lưu payload đã mã hóa hoặc reference đến object immutable.

Không lưu dữ liệu nhạy cảm vào inbox nếu không cần. Áp dụng retention, encryption, quyền truy cập và masking tương tự dữ liệu nghiệp vụ.

## 6. Mẫu atomic inbox: claim và business update trong cùng transaction

Đối với consumer chỉ thực hiện các thay đổi trong cùng một relational database, pattern đơn giản và mạnh là:

- Insert inbox row trong transaction.
- Nếu insert thành công, xử lý nghiệp vụ.
- Đánh dấu processed.
- Commit tất cả cùng lúc.
- Nếu bất kỳ bước nào lỗi, rollback cả inbox row và business update.

PostgreSQL có thể dùng:

~~~sql
INSERT INTO consumer_inbox (
    consumer_name,
    event_source,
    event_id,
    payload_hash,
    event_type,
    status,
    received_at
)
VALUES (?, ?, ?, ?, ?, 'PROCESSING', CURRENT_TIMESTAMP)
ON CONFLICT (consumer_name, event_source, event_id)
DO NOTHING;
~~~

Nếu số row được insert là 1, transaction này đã claim event. Nếu là 0, một transaction khác hoặc lần xử lý trước đã ghi identity đó.

Sau khi cập nhật dữ liệu nghiệp vụ thành công:

~~~sql
UPDATE consumer_inbox
SET status = 'PROCESSED',
    processed_at = CURRENT_TIMESTAMP
WHERE consumer_name = ?
  AND event_source = ?
  AND event_id = ?
  AND status = 'PROCESSING';
~~~

Trong pattern atomic này, row PROCESSING chưa commit trong lúc nghiệp vụ chạy. Transaction khác gặp unique conflict có thể phải chờ transaction đầu commit hoặc rollback. Nếu transaction đầu commit, lần sau thấy duplicate; nếu transaction đầu rollback, lần giao lại có thể claim và xử lý.

Không commit một row PROCESSING rồi thực hiện business update trong transaction khác nếu chưa thiết kế lease/recovery. Nếu làm vậy, cần cơ chế phát hiện và thu hồi claim bị bỏ dở.

## 7. Java JDBC: inbox và business update cùng transaction

Ví dụ dưới đây dùng PostgreSQL và JDBC. `applyBusinessChange` phải dùng chính connection được truyền vào để mọi thay đổi nằm trong cùng transaction.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderEventConsumer {

    private static final String CONSUMER = "order-projection-v2";

    private final DataSource dataSource;

    public OrderEventConsumer(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean handle(OrderPaidEvent event) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                int claimed;

                try (PreparedStatement statement =
                        connection.prepareStatement("""
                            INSERT INTO consumer_inbox (
                                consumer_name, event_source, event_id,
                                payload_hash, event_type, status, received_at
                            )
                            VALUES (?, ?, ?, ?, ?, 'PROCESSING', CURRENT_TIMESTAMP)
                            ON CONFLICT (
                                consumer_name, event_source, event_id
                            ) DO NOTHING
                            """)) {
                    statement.setString(1, CONSUMER);
                    statement.setString(2, event.source());
                    statement.setString(3, event.eventId());
                    statement.setString(4, event.payloadHash());
                    statement.setString(5, "order.paid");
                    claimed = statement.executeUpdate();
                }

                if (claimed == 0) {
                    verifyExistingEvent(
                            connection, event, CONSUMER);
                    connection.commit();
                    return false; // Duplicate: no business update.
                }

                applyBusinessChange(connection, event);

                try (PreparedStatement statement =
                        connection.prepareStatement("""
                            UPDATE consumer_inbox
                            SET status = 'PROCESSED',
                                processed_at = CURRENT_TIMESTAMP
                            WHERE consumer_name = ?
                              AND event_source = ?
                              AND event_id = ?
                              AND status = 'PROCESSING'
                            """)) {
                    statement.setString(1, CONSUMER);
                    statement.setString(2, event.source());
                    statement.setString(3, event.eventId());

                    if (statement.executeUpdate() != 1) {
                        throw new SQLException(
                                "Inbox state transition failed");
                    }
                }

                connection.commit();
                return true;
            } catch (SQLException | RuntimeException error) {
                connection.rollback();
                throw error;
            }
        }
    }

    private void applyBusinessChange(
            Connection connection,
            OrderPaidEvent event) throws SQLException {
        // Update order/projection using this same connection.
    }

    private void verifyExistingEvent(
            Connection connection,
            OrderPaidEvent event,
            String consumer) throws SQLException {
        // Read stored payload_hash. If the same identity has a
        // different hash, fail and alert instead of treating it
        // as a normal duplicate.
    }
}
~~~

Ví dụ giả định các type `OrderPaidEvent` và phương thức xác minh payload hash được định nghĩa trong ứng dụng. Trong production, `verifyExistingEvent` cần truy vấn record hiện có và so sánh hash; nếu cùng identity nhưng payload khác, đây là lỗi contract hoặc dấu hiệu bất thường, không nên âm thầm bỏ qua.

Nếu insert bị conflict, PostgreSQL có thể chờ transaction đang giữ unique key hoàn tất. Vì vậy, transaction phải ngắn và không nên gọi API bên ngoài hoặc sleep trong lúc giữ transaction.

### Vì sao commit trước rồi mới ACK?

Listener chỉ acknowledge sau khi `handle` trả về thành công, nghĩa là transaction đã commit. Nếu function bị dừng sau commit nhưng trước ACK, message được giao lại và `claimed == 0`; consumer xác minh duplicate rồi trả về thành công mà không cập nhật nghiệp vụ lần nữa.

Nếu transaction rollback, inbox claim cũng rollback. Message được retry có thể claim lại và chạy nghiệp vụ.

## 8. Spring transaction và message listener

Trong Spring, có thể đặt logic inbox và business update trong một service method được quản lý bởi transaction manager:

~~~java
@Service
public class OrderEventHandler {

    private final JdbcTemplate jdbc;
    private final OrderProjectionRepository repository;

    public OrderEventHandler(
            JdbcTemplate jdbc,
            OrderProjectionRepository repository) {
        this.jdbc = jdbc;
        this.repository = repository;
    }

    @Transactional
    public ProcessingResult process(OrderPaidEvent event) {
        int claimed = jdbc.update("""
            INSERT INTO consumer_inbox (
                consumer_name, event_source, event_id,
                payload_hash, event_type, status, received_at
            )
            VALUES (?, ?, ?, ?, ?, 'PROCESSING', CURRENT_TIMESTAMP)
            ON CONFLICT (consumer_name, event_source, event_id)
            DO NOTHING
            """,
            "order-projection-v2",
            event.source(),
            event.eventId(),
            event.payloadHash(),
            "order.paid");

        if (claimed == 0) {
            verifyPayloadHash(event);
            return ProcessingResult.DUPLICATE;
        }

        repository.applyPaidEvent(event);

        jdbc.update("""
            UPDATE consumer_inbox
            SET status = 'PROCESSED',
                processed_at = CURRENT_TIMESTAMP
            WHERE consumer_name = ?
              AND event_source = ?
              AND event_id = ?
              AND status = 'PROCESSING'
            """,
            "order-projection-v2",
            event.source(),
            event.eventId());

        return ProcessingResult.PROCESSED;
    }

    private void verifyPayloadHash(OrderPaidEvent event) {
        // Query and compare the stored hash.
        // Throw a non-retryable contract error on mismatch.
    }
}
~~~

Listener gọi service rồi mới ACK theo cơ chế của framework/provider. Không bắt exception trong listener rồi vẫn ACK nếu transaction đã rollback. Cũng cần bảo đảm method transactional được gọi qua Spring proxy; self-invocation trong cùng bean có thể không kích hoạt transaction như mong đợi.

Với Lambda hoặc function handler không dùng Spring, có thể áp dụng cùng nguyên tắc bằng JDBC transaction tường minh. Điều quan trọng là inbox row và business state dùng cùng database transaction.

## 9. Xử lý duplicate đồng thời

Khi scale-out, hai execution environment có thể nhận cùng event gần như cùng lúc. Kiểm tra duplicate ở Java memory hoặc cache cục bộ không đủ vì mỗi instance có bộ nhớ riêng.

Unique constraint là cơ chế phối hợp giữa các instance:

~~~mermaid
sequenceDiagram
    participant A as Consumer A
    participant B as Consumer B
    participant DB as Database

    A->>DB: INSERT inbox key E-42
    DB-->>A: Inserted
    B->>DB: INSERT same inbox key E-42
    Note over B,DB: B waits for unique-key outcome
    A->>DB: Apply business update
    A->>DB: Mark PROCESSED + COMMIT
    DB-->>B: Conflict / no row inserted
    B->>DB: Read existing hash/status
    DB-->>B: Already processed
    B-->>B: Return duplicate without side effect
~~~

Không dùng static Set, ConcurrentHashMap hoặc local cache làm nguồn deduplication chuẩn. Chúng chỉ có thể giảm một số lần đọc trong cùng instance; không bảo vệ được khi scale-out, cold start, restart hoặc chạy ở nhiều region.

Nếu hai invocation cùng xử lý một key, database transaction và unique constraint phải quyết định duy nhất invocation nào được claim. Cấu hình lock/statement timeout để invocation chờ không chiếm concurrency quá lâu; khi timeout, để message retry theo policy.

## 10. Cùng event ID nhưng payload khác

Một event identity phải đại diện cho một nội dung bất biến. Nếu producer gửi lại cùng source + eventId nhưng payload khác, consumer không nên coi đó là duplicate bình thường.

Có thể lưu hash của payload canonical:

- Serialize theo schema đã định và thứ tự field ổn định.
- Hoặc hash raw event bytes nếu producer giữ nguyên bytes khi retry.
- Không hash một JSON serialization không ổn định rồi giả định kết quả giống nhau.
- Không đưa secret hoặc dữ liệu nhạy cảm vào log khi hash mismatch.

Khi identity trùng nhưng hash khác:

1. Không áp dụng business update.
2. Ghi nhận lỗi contract/security.
3. Đưa message vào quarantine hoặc DLQ theo policy.
4. Alert owner của producer/consumer.
5. Điều tra việc tái sử dụng event ID hoặc sửa payload sau khi publish.

Hash chỉ phát hiện khác biệt payload; nó không chứng minh producer đáng tin hay event hợp lệ.

## 11. Khi cần trạng thái PROCESSING đã commit: lease và recovery

Atomic inbox phù hợp khi business update nằm trong một transaction ngắn của cùng database. Có trường hợp xử lý lâu, phải gọi nhiều bước hoặc cần worker khác tiếp tục công việc. Khi đó có thể commit claim trước rồi xử lý theo state machine, nhưng phải có lease.

Ví dụ schema mở rộng:

~~~sql
CREATE TABLE consumer_inbox_jobs (
    consumer_name VARCHAR(128) NOT NULL,
    event_source  VARCHAR(256) NOT NULL,
    event_id      VARCHAR(256) NOT NULL,
    payload_hash  VARCHAR(128) NOT NULL,
    status        VARCHAR(24) NOT NULL,
    lease_owner   VARCHAR(128) NULL,
    lease_until   TIMESTAMP NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    received_at   TIMESTAMP NOT NULL,
    processed_at  TIMESTAMP NULL,
    PRIMARY KEY (consumer_name, event_source, event_id)
);
~~~

State machine có thể là:

~~~text
RECEIVED -> PROCESSING -> PROCESSED
                  |
                  +-> RETRYABLE_FAILURE -> PROCESSING
                  |
                  +-> FAILED_TERMINAL
~~~

Khi worker claim job:

- Dùng transaction và row lock/conditional update để chỉ một worker có lease hợp lệ.
- Ghi lease owner, lease expiration và tăng attempt count.
- Gia hạn lease nếu công việc còn chạy lâu.
- Nếu worker chết, lease hết hạn để worker khác có thể claim.
- Khi hoàn tất, chỉ owner/lease token hợp lệ mới được chuyển sang PROCESSED.

### Lease cần fencing token

Lease hết hạn không bảo đảm worker cũ đã dừng. Ví dụ worker A bị pause lâu, lease hết hạn, worker B claim và xử lý; sau đó A chạy tiếp. Cả hai có thể ghi dữ liệu.

Dùng fencing token tăng đơn điệu hoặc version/lease generation. Mọi cập nhật trạng thái phải kiểm tra token hiện tại. Downstream cũng cần idempotency hoặc kiểm soát version để worker cũ không ghi đè kết quả mới.

Không chỉ dựa vào timestamp lease nếu clock giữa các worker có thể lệch; dùng thời gian database hoặc cơ chế compare-and-set do database quản lý.

## 12. Inbox không bao trùm side effect bên ngoài

Database transaction không thể tự động atomic với HTTP API đối tác, email provider hoặc payment gateway. Nếu consumer:

1. Ghi inbox.
2. Gọi API bên ngoài thành công.
3. Crash trước khi commit inbox.

Message được giao lại và API bên ngoài có thể bị gọi lần nữa.

Nếu commit inbox trước rồi gọi API bên ngoài, crash sau commit nhưng trước khi gọi sẽ làm mất side effect.

Đây là dual-write problem. Inbox một mình không giải quyết được.

### Kết hợp inbox với transactional outbox

Trong cùng transaction database:

- Insert/claim inbox.
- Cập nhật business state.
- Insert một outbox command mô tả side effect cần thực hiện.
- Mark inbox processed.
- Commit.

Sau đó một outbox dispatcher gửi command đến external API. Dispatcher có thể gửi lặp nếu crash sau khi provider xử lý nhưng trước khi đánh dấu outbox delivered, vì vậy vẫn cần idempotency key ở provider hoặc API tra cứu trạng thái.

~~~mermaid
flowchart TD
    Event[Incoming event]
    Consumer[Java consumer]
    Tx[DB transaction]
    Inbox[(Inbox)]
    Business[(Business state)]
    Outbox[(Outbox)]
    Dispatcher[Outbox dispatcher]
    Provider[External API/provider]

    Event --> Consumer --> Tx
    Tx --> Inbox
    Tx --> Business
    Tx --> Outbox
    Outbox --> Dispatcher --> Provider
~~~

Nếu provider hỗ trợ idempotency key, dùng key ổn định từ outbox command/business operation. Nếu provider không hỗ trợ, cần thiết kế reconciliation hoặc trạng thái “outcome unknown” thay vì khẳng định exactly-once.

## 13. Inbox và outbox khác nhau thế nào?

| Pattern | Hướng | Mục đích |
|---|---|---|
| Inbox | Event đi vào consumer | Deduplicate và ghi nhận event đã xử lý |
| Outbox | Event/command đi ra khỏi service | Đảm bảo business update và ý định publish được ghi cùng transaction |
| Inbox + Outbox | Vào và ra | Xử lý event lặp an toàn và phát sinh side effect/event tiếp theo đáng tin cậy |

Ví dụ order service nhận payment.authorized:

- Inbox ghi payment.authorized đã được consumer xử lý.
- Business transaction chuyển order sang PAID.
- Outbox ghi order.paid cần publish.
- Dispatcher publish order.paid.
- Consumer khác dùng inbox riêng để deduplicate order.paid.

Không nên nhầm outbox là nơi ghi nhận event đã nhận. Outbox giải quyết việc publish event đi ra; inbox giải quyết việc tiếp nhận event đi vào.

## 14. Ordering và event version

Inbox ngăn xử lý cùng một event identity nhiều lần, nhưng không tự bảo đảm event đến đúng thứ tự.

Ví dụ:

- order.updated version 4 đến trước version 3.
- Consumer xử lý version 4.
- Sau đó version 3 được giao lại hoặc replay.

Nếu consumer chỉ kiểm tra eventId, nó có thể ghi đè trạng thái mới bằng dữ liệu cũ.

Biện pháp:

- Gắn aggregate version hoặc sequence number.
- Cập nhật có điều kiện, ví dụ chỉ áp dụng event nếu version mới lớn hơn version hiện tại.
- Dùng partition key theo aggregate nếu broker hỗ trợ ordering theo key.
- Xử lý gap bằng cách chờ, retry, fetch snapshot hoặc reconciliation.
- Không giả định ordering toàn cục nếu provider chỉ bảo đảm trong partition/message group.

Ví dụ update có điều kiện:

~~~sql
UPDATE order_projection
SET status = ?,
    version = ?
WHERE order_id = ?
  AND version < ?;
~~~

Kết quả 0 row cần được phân loại: event cũ đã được áp dụng, version trùng hay aggregate chưa tồn tại. Không tự động coi mọi trường hợp là success nếu có thể đang thiếu event trước đó.

## 15. Retention, replay và thay đổi consumer version

Inbox record phải được giữ đủ lâu để bao phủ cửa sổ redelivery và replay. Nếu xóa record quá sớm, event cũ có thể được phát lại và gây side effect lần nữa.

Xác định retention dựa trên:

- Broker message retention.
- DLQ retention và redrive window.
- Stream replay window.
- Thời gian backup/restore có thể đưa event cũ trở lại.
- Quy trình backfill hoặc reprocessing.
- Thời hạn idempotency của external provider.
- Yêu cầu audit và pháp lý.

### Consumer version là một phần của identity

Nếu consumer v2 là một projection mới cần xử lý lại toàn bộ event lịch sử, có thể dùng consumer_name khác như `order-projection-v2`. Khi đó v2 có inbox namespace riêng và không bị v1 đánh dấu đã xử lý.

Nhưng không đổi consumer_name mỗi lần deploy thông thường. Nếu release v2 chỉ là bản sửa bug và cần tiếp tục trạng thái xử lý của v1, đổi namespace sẽ làm mất deduplication và có thể chạy lại mọi event. Hãy phân biệt logical consumer identity với code release version.

### Replay có chủ đích

Replay để rebuild projection có thể cần namespace mới và target storage riêng. Replay để khôi phục message chưa xử lý cần giữ identity gốc. Xác định rõ mục tiêu trước khi xóa inbox hoặc đổi consumer identity.

## 16. Poison event và trạng thái terminal

Một event có thể luôn thất bại vì schema sai, thiếu dữ liệu, business invariant bị vi phạm hoặc code không hỗ trợ event version. Retry vô hạn không giúp xử lý poison event.

Phân loại:

- **Retryable:** dependency tạm thời, lock conflict hoặc throttling.
- **Permanent/terminal:** payload sai, event type không hỗ trợ, vi phạm contract.
- **Ambiguous:** không biết side effect đã xảy ra hay chưa; cần idempotency/lookup.
- **Out-of-order:** event hợp lệ nhưng chưa thể áp dụng vì thiếu version trước.

Đối với lỗi terminal, ghi trạng thái/quarantine và acknowledge theo policy sau khi bảo đảm có audit và DLQ phù hợp. Không đánh dấu PROCESSED nếu business update chưa xảy ra; dùng trạng thái FAILED_TERMINAL riêng để thể hiện kết quả.

Đối với retryable error trong atomic inbox pattern, rollback transaction để event có thể được giao lại. Với lease pattern, cập nhật RETRYABLE_FAILURE và đặt next_attempt_at/lease state theo scheduler.

## 17. Quan sát inbox và xử lý duplicate

Inbox là một phần của reliability path nên cần metric và alert.

Theo dõi:

- Số event mới được claim.
- Số duplicate được bỏ qua.
- Số payload hash mismatch.
- Số transaction rollback khi xử lý.
- Số inbox record ở PROCESSING quá lâu.
- Số lease hết hạn và được reclaim.
- Số event FAILED_TERMINAL.
- Số event vào DLQ và redrive thành công.
- Độ trễ từ received_at đến processed_at.
- Kích thước inbox và tốc độ tăng dữ liệu.

Log nên có consumer name, source, event ID hoặc mã đã pseudonymize, operation ID, attempt và outcome. Không log payload nhạy cảm. Không đưa event ID hoặc tenant ID cardinality cao vào metric labels; dùng metric tổng hợp và log/trace để điều tra.

Alert khi PROCESSING vượt thời gian dự kiến, lease liên tục hết hạn, hash mismatch tăng hoặc DLQ tăng bất thường. Duplicate rate cao có thể chỉ là delivery semantics bình thường, nhưng thay đổi đột ngột có thể chỉ ra ack timeout, consumer latency hoặc producer retry bug.

## 18. Kiểm thử consumer inbox

Kiểm thử phải bao gồm duplicate tuần tự, duplicate đồng thời và crash ở mọi điểm quan trọng.

| Tình huống | Kết quả mong đợi |
|---|---|
| Event mới | Inbox và business state cùng commit |
| Giao lại event đã processed | Không áp dụng business update lần nữa |
| Crash trước commit | Inbox và business update rollback; event có thể retry |
| Crash sau commit trước ACK | Redelivery được nhận diện là duplicate |
| Hai invocation cùng event | Unique constraint chỉ cho một transaction claim |
| Cùng identity, payload khác | Không xử lý; ghi lỗi contract và quarantine |
| Business update lỗi | Transaction rollback hoặc state retryable theo pattern |
| External API thành công, dispatcher crash | Outbox retry với cùng idempotency key |
| Lease hết hạn | Worker khác reclaim theo fencing/version |
| Worker cũ chạy lại sau lease expiry | Fencing token ngăn ghi đè |
| Event đến sai thứ tự | Version check ngăn trạng thái lùi |
| Inbox record hết retention | Test xác minh replay policy không gây duplicate side effect |
| Consumer v2 replay lịch sử | Namespace riêng theo mục tiêu reprocessing |
| DLQ redrive | Giữ nguyên event/business identity |

### Fault injection

Chèn điểm dừng có chủ đích trong môi trường test:

1. Sau khi nhận message nhưng trước transaction.
2. Sau insert inbox nhưng trước business update.
3. Sau business update nhưng trước commit.
4. Ngay sau commit nhưng trước ack.
5. Sau external provider thành công nhưng trước outbox delivered.
6. Trong lúc lease hết hạn và worker mới reclaim.

Mỗi điểm phải chứng minh trạng thái cuối cùng đúng và side effect không bị lặp ngoài policy. Chỉ test handler chạy thành công một lần không chứng minh inbox hoạt động.

## 19. Những lỗi triển khai thường gặp

- **Dùng event ID không ổn định:** mỗi lần retry tạo ID mới nên dedup không có tác dụng; giữ application event ID qua mọi delivery.
- **Unique chỉ theo eventId toàn cục:** các consumer độc lập có thể chặn nhau; thêm consumer identity và source namespace.
- **SELECT rồi INSERT:** race condition khi hai invocation cùng xử lý; dùng unique constraint và atomic insert.
- **Commit inbox trước business update:** crash có thể khiến event bị đánh dấu đã nhận nhưng nghiệp vụ chưa chạy; dùng cùng transaction hoặc lease/recovery đầy đủ.
- **ACK trước database commit:** message có thể mất khi transaction rollback; commit rồi mới ACK.
- **Gọi external API trong transaction dài:** giữ lock/connection và vẫn không atomic với provider; dùng outbox.
- **Coi duplicate là lỗi retry:** tạo retry loop vô ích; duplicate đã xử lý nên được ACK/return success.
- **Bỏ qua payload hash mismatch:** event ID bị tái sử dụng có thể làm mất dữ liệu; kiểm tra contract.
- **Dùng static Set để dedup:** không chia sẻ giữa instance và mất khi restart; dùng kho bền vững.
- **Xóa inbox quá sớm:** replay cũ có thể chạy side effect lại; retention phải bao phủ replay window.
- **Đổi consumer name mỗi release:** mất lịch sử dedup; chỉ đổi khi chủ đích tạo logical consumer mới.
- **Cho rằng inbox bảo đảm exactly-once toàn hệ thống:** side effect bên ngoài vẫn có thể lặp; cần idempotency provider/reconciliation.
- **Không xử lý event ordering:** event cũ có thể ghi đè state mới; dùng aggregate version/sequence.
- **Commit PROCESSING mà không lease:** worker chết để lại record kẹt; dùng lease, fencing và recovery.
- **Không kiểm thử crash sau commit trước ACK:** bỏ sót failure window phổ biến nhất.

## 20. Quy trình triển khai inbox cho Java serverless

Khi xây dựng consumer mới, có thể thực hiện theo trình tự:

1. Xác định logical consumer identity và namespace của event source.
2. Chọn event ID ổn định; phân biệt event ID, broker message ID và business operation ID.
3. Định nghĩa payload hash/canonicalization và xử lý identity collision.
4. Tạo inbox table với composite unique key.
5. Với business update cùng database, claim inbox và cập nhật nghiệp vụ trong một transaction.
6. Đánh dấu PROCESSED trước khi commit; rollback cả inbox và business state nếu có lỗi.
7. Acknowledge message chỉ sau khi transaction commit.
8. Xử lý duplicate bằng cách xác minh hash rồi return success mà không lặp side effect.
9. Nếu xử lý dài hoặc nhiều bước, dùng state machine, lease, fencing token và recovery.
10. Với side effect bên ngoài, ghi outbox trong transaction và dùng provider idempotency/reconciliation.
11. Bảo vệ ordering bằng aggregate version hoặc partition key khi cần.
12. Đặt retention bao phủ redelivery, DLQ, backup restore và replay window.
13. Theo dõi duplicate, hash mismatch, processing age, lease expiry, DLQ và completion latency.
14. Kiểm thử duplicate đồng thời và crash ở mọi điểm trước/sau commit, ACK và external side effect.

## 21. Ghi nhớ

Consumer inbox lưu event identity bền vững để consumer nhận diện message đã xử lý. Unique constraint là cơ chế chống duplicate giữa nhiều execution environment; cache hoặc static Set trong Java không đủ cho serverless scale-out.

Với thay đổi nghiệp vụ nằm trong cùng database, ghi inbox, cập nhật business state và đánh dấu processed trong một transaction, rồi mới ACK message. Nếu transaction rollback, event có thể retry; nếu commit thành công nhưng ACK thất bại, lần giao lại sẽ bị nhận diện là duplicate.

Inbox không tự bảo đảm exactly-once cho HTTP API, email hoặc payment provider. Dùng transactional outbox, idempotency key phía provider và reconciliation cho side effect bên ngoài. Đặt retention phù hợp với replay window, xử lý ordering bằng version và kiểm thử crash sau commit trước ACK. Thiết kế đúng giúp consumer chịu được at-least-once delivery mà không làm lặp tác dụng phụ nghiệp vụ.

