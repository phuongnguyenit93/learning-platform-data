# Đồng bộ thay đổi dữ liệu với sự kiện bằng transactional outbox

Trong chương **Tính đúng đắn của dữ liệu**, transactional outbox giải quyết một lỗi phổ biến trong ứng dụng phân tán: dữ liệu trong database đã thay đổi nhưng event thông báo cho hệ thống khác lại không được phát, hoặc event đã được phát dù transaction nghiệp vụ cuối cùng rollback. Mẫu này ghi thay đổi nghiệp vụ và event cần phát vào cùng một transaction, sau đó một publisher riêng gửi event đã commit tới queue hoặc event bus.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng theo mô hình serverless, đặc biệt là Java function kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Người học xử lý trigger, trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí để xác định khi nào nên dùng FaaS. Transactional outbox giúp Java function đồng bộ thay đổi dữ liệu với luồng event mà không phụ thuộc vào một lời gọi publish nằm ngoài transaction database.

## 1. Bài toán dual-write

Giả sử một HTTP handler nhận yêu cầu tạo đơn hàng. Ứng dụng cần:

1. Ghi order vào database.
2. Phát event OrderCreated để inventory, billing và notification xử lý.

Nếu code thực hiện hai thao tác riêng rẽ, có hai cửa sổ lỗi:

**Ghi database trước, publish sau**

- Database commit thành công.
- Process bị dừng hoặc Lambda timeout trước khi publish.
- Order tồn tại nhưng consumer không nhận OrderCreated.

**Publish trước, ghi database sau**

- Event được publish và consumer xử lý.
- Database transaction thất bại hoặc rollback.
- Hệ thống downstream tin rằng order đã được tạo trong khi database nguồn không có order.

Đây là bài toán dual-write: hai hệ thống độc lập phải được cập nhật như thể chúng là một thao tác nguyên tử, nhưng không có transaction chung giữa database và broker.

~~~mermaid
sequenceDiagram
    participant API as Java handler
    participant DB as Database
    participant BUS as Event broker
    participant C as Consumer
    API->>DB: INSERT order
    DB-->>API: COMMIT
    API->>BUS: Publish OrderCreated
    Note over API,BUS: Process can fail between the two writes
    BUS->>C: Event
~~~

Retry lời gọi publish không giải quyết triệt để vấn đề. Nếu process crash sau khi broker nhận event nhưng trước khi ứng dụng ghi nhận publish thành công, lần retry có thể phát event lần thứ hai.

## 2. Transactional outbox giải quyết điều gì?

Transactional outbox thêm một bảng hoặc một tập bản ghi outbox trong cùng database với dữ liệu nghiệp vụ. Trong một transaction:

- Cập nhật bảng nghiệp vụ.
- Thêm event vào outbox.
- Commit cả hai cùng nhau.

Một publisher riêng đọc các outbox record đã commit và gửi chúng tới broker. Khi broker xác nhận nhận event, publisher cập nhật trạng thái record để không tiếp tục gửi trong luồng bình thường.

~~~mermaid
flowchart TD
    API["Java application / Lambda"] --> TX["One database transaction"]
    TX --> B["Write business data"]
    TX --> O["Insert outbox event"]
    B --> COMMIT["Commit"]
    O --> COMMIT
    COMMIT --> PUB["Outbox publisher"]
    PUB --> BUS["Queue / EventBridge / Kafka"]
    BUS --> C["Idempotent consumers"]
~~~

Nếu transaction rollback, cả thay đổi nghiệp vụ và outbox event đều không tồn tại. Nếu transaction commit, cả hai đều có thể được publisher tìm thấy sau này, kể cả khi application process bị dừng ngay sau commit.

Transactional outbox giải quyết tính nguyên tử giữa business write và ý định phát event. Nó không tạo ra một transaction phân tán giữa database và broker, và không bảo đảm broker nhận đúng một lần. Publisher vẫn có thể gửi lặp; consumer vẫn cần idempotency.

## 3. Những bảo đảm và giới hạn

| Thuộc tính | Outbox cung cấp? | Giải thích |
|---|---|---|
| Business state và event record commit cùng nhau | Có | Cùng database transaction |
| Event chỉ được tạo khi business transaction commit | Có | Rollback loại bỏ cả hai |
| Event cuối cùng được thử publish | Có, nếu publisher tiếp tục hoạt động | Cần retry, monitoring và xử lý record lỗi |
| Broker nhận đúng một lần | Không | Crash sau send nhưng trước mark-published có thể tạo duplicate |
| Consumer xử lý đúng một lần nghiệp vụ | Không tự động | Cần inbox/idempotency và transaction phía consumer |
| Giữ thứ tự toàn cục | Không | Cần partition/group key và publisher ordering |
| Event được phát ngay lập tức | Không | Có độ trễ giữa commit và lần publisher chạy |

Mô hình thực tế thường là at-least-once delivery kết hợp idempotent consumer. Hệ thống có thể đạt kết quả nghiệp vụ tương đương exactly-once trong phạm vi được thiết kế, nhưng không nên tuyên bố mọi message chỉ đi qua toàn bộ hệ thống đúng một lần.

## 4. Chọn event contract trước khi tạo outbox

Outbox lưu một event có ý nghĩa nghiệp vụ, không chỉ là bản sao tùy tiện của một row database. Một event envelope nên có:

| Field | Mục đích |
|---|---|
| eventId | Định danh ổn định để deduplicate |
| eventType | Tên loại sự kiện |
| schemaVersion | Phiên bản payload |
| aggregateId | Đối tượng nghiệp vụ liên quan |
| aggregateVersion | Thứ tự thay đổi trong aggregate |
| occurredAt | Thời điểm nghiệp vụ xảy ra |
| correlationId | Liên kết các bước của workflow |
| causationId | Command hoặc event gây ra thay đổi |
| payload | Dữ liệu consumer cần để xử lý |

Ví dụ payload:

~~~json
{
  "eventId": "evt-01J9ORDER42",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "aggregateId": "order-42",
  "aggregateVersion": 1,
  "occurredAt": "2026-11-17T10:15:00Z",
  "correlationId": "request-8f31",
  "payload": {
    "orderId": "order-42",
    "customerId": "customer-17",
    "currency": "VND",
    "totalAmount": 850000
  }
}
~~~

Event nên mô tả sự việc đã xảy ra, ví dụ OrderCreated hoặc PaymentAuthorized. Tránh đặt tên event như một lệnh yêu cầu consumer thực hiện hành động, ví dụ CreateInvoice, trừ khi contract thực sự là command gửi tới một owner cụ thể.

Không dùng timestamp làm thứ tự duy nhất. Nếu nhiều event của cùng order cần được áp dụng tuần tự, producer phải cấp aggregateVersion hoặc sequence có thẩm quyền.

## 5. Thiết kế bảng outbox

Một schema SQL phổ biến:

~~~sql
CREATE TABLE outbox_event (
    event_id           VARCHAR(200) PRIMARY KEY,
    aggregate_type     VARCHAR(120) NOT NULL,
    aggregate_id       VARCHAR(200) NOT NULL,
    aggregate_version  BIGINT NOT NULL,
    event_type         VARCHAR(160) NOT NULL,
    schema_version     INTEGER NOT NULL,
    payload            JSONB NOT NULL,
    occurred_at        TIMESTAMPTZ NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at       TIMESTAMPTZ,
    attempt_count      INTEGER NOT NULL DEFAULT 0,
    next_attempt_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lease_owner        VARCHAR(160),
    lease_until        TIMESTAMPTZ,
    last_error_code    VARCHAR(120)
);
~~~

Các field chính:

- event_id là khóa duy nhất và được tạo trước khi commit.
- aggregate_type và aggregate_id cho biết event thuộc đối tượng nào.
- aggregate_version giúp giữ thứ tự trong một aggregate.
- payload chứa event đã serialize.
- published_at rỗng nghĩa là publisher chưa xác nhận hoàn tất.
- attempt_count và next_attempt_at điều khiển retry.
- lease_owner và lease_until giúp nhiều publisher chia sẻ công việc.
- last_error_code hỗ trợ điều tra mà không cần ghi secret vào log.

Index cho các event chưa publish:

~~~sql
CREATE INDEX idx_outbox_ready
ON outbox_event (next_attempt_at, created_at)
WHERE published_at IS NULL;
~~~

Index nên được thiết kế theo database và query thực tế. Khi outbox lớn, cần đo số row được quét, index bloat và thời gian cleanup.

Không lưu credential, access token hoặc dữ liệu cá nhân không cần thiết trong payload. Nếu event cần tham chiếu dữ liệu nhạy cảm, cân nhắc lưu identifier và để consumer lấy dữ liệu qua API có authorization phù hợp.

## 6. Ghi business state và outbox trong cùng transaction

Ví dụ với Spring và JPA/JDBC:

~~~java
@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final EventSerializer serializer;

    public OrderApplicationService(
            OrderRepository orders,
            OutboxRepository outbox,
            EventSerializer serializer) {
        this.orders = orders;
        this.outbox = outbox;
        this.serializer = serializer;
    }

    @Transactional
    public OrderResult createOrder(CreateOrder command) {
        Order order = Order.create(
                command.customerId(),
                command.items());

        orders.save(order);

        OrderCreated event = OrderCreated.from(order);
        OutboxRecord record = new OutboxRecord(
                event.eventId(),
                "Order",
                order.id(),
                order.version(),
                "OrderCreated",
                1,
                serializer.toJson(event));

        outbox.insert(record);

        return OrderResult.from(order);
    }
}
~~~

OrderRepository và OutboxRepository phải tham gia cùng một transaction manager và cùng database transaction. Nếu một repository ghi sang database khác hoặc dùng một transaction manager khác, tính nguyên tử không còn được bảo đảm.

Không gọi broker trực tiếp trong method createOrder rồi cho rằng @Transactional sẽ rollback được message đã gửi. Transaction của Spring chỉ điều khiển resource tham gia transaction manager; nó không tự thu hồi một event đã được broker chấp nhận.

### 6.1. Transaction boundary

Một transaction nên bao gồm:

1. Kiểm tra điều kiện nghiệp vụ.
2. Ghi hoặc cập nhật aggregate.
3. Cấp aggregate version mới.
4. Serialize event từ dữ liệu đã xác nhận.
5. Insert outbox record.
6. Commit.

Không giữ transaction mở trong lúc gọi network tới broker. Network call có thể chậm hoặc timeout, giữ lock lâu và làm tăng contention của database.

Nếu dùng event callback sau commit để đánh thức publisher cho độ trễ thấp, callback chỉ nên là tín hiệu tối ưu hóa. Outbox record vẫn là nguồn dữ liệu bền vững; nếu callback bị mất, publisher polling/CDC phải tìm thấy record.

## 7. Tạo event từ dữ liệu đã commit

Event nên phản ánh đúng thay đổi đã được commit. Có hai cách phổ biến:

**Snapshot event:** payload chứa các giá trị cần thiết tại thời điểm phát sinh sự kiện. Consumer có thể xử lý mà không phải đọc lại toàn bộ aggregate. Cần xác định rõ field nào được phép đưa vào event và tránh gửi dữ liệu nhạy cảm.

**Reference event:** payload chứa aggregate ID hoặc resource reference. Consumer đọc dữ liệu hiện tại qua API hoặc database. Cách này giảm payload nhưng dữ liệu có thể đã thay đổi khi consumer đọc; nếu cần trạng thái tại thời điểm event xảy ra, reference đơn thuần không đủ.

Không tạo payload bằng cách serialize entity ORM một cách máy móc. Entity có thể chứa lazy relation, field nội bộ hoặc trạng thái chưa được commit. Dùng event DTO riêng để ổn định contract.

## 8. Publisher polling: đọc và gửi outbox theo lô

Cách triển khai đơn giản là một scheduled worker hoặc Lambda định kỳ:

1. Tìm các row chưa publish và đã đến thời điểm retry.
2. Claim một batch để chỉ publisher này xử lý.
3. Commit claim/lease.
4. Gửi event tới broker.
5. Khi broker xác nhận, đánh dấu row published.
6. Nếu lỗi, cập nhật attempt count và next_attempt_at.

Publisher không nên giữ database transaction mở trong toàn bộ network call. Claim trước, commit lease, gửi sau, rồi cập nhật kết quả trong transaction ngắn khác.

### 8.1. Claim bằng lease và SKIP LOCKED

Với PostgreSQL, một query khái niệm:

~~~sql
WITH candidates AS (
    SELECT event_id
    FROM outbox_event
    WHERE published_at IS NULL
      AND next_attempt_at <= CURRENT_TIMESTAMP
      AND (
          lease_until IS NULL
          OR lease_until < CURRENT_TIMESTAMP
      )
    ORDER BY created_at, event_id
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
UPDATE outbox_event AS o
SET lease_owner = :worker_id,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '30 seconds',
    attempt_count = attempt_count + 1
FROM candidates AS c
WHERE o.event_id = c.event_id
RETURNING o.*;
~~~

Đây là ví dụ PostgreSQL; cú pháp binding và transaction cần được điều chỉnh theo JDBC/ORM đang dùng. SKIP LOCKED cho phép nhiều publisher claim các row khác nhau mà không phải chờ khóa của nhau.

Lease cần dài hơn thời gian publish bình thường nhưng vẫn có giới hạn. Nếu publisher chết, lease hết hạn và worker khác có thể claim lại. Nếu publish mất nhiều thời gian hơn lease, hai worker có thể cùng gửi một event; có thể gia hạn lease hoặc dùng timeout phù hợp, nhưng consumer vẫn cần deduplicate.

### 8.2. Đánh dấu published sau broker acknowledgement

Sau khi broker xác nhận event đã được chấp nhận, publisher cập nhật:

~~~sql
UPDATE outbox_event
SET published_at = CURRENT_TIMESTAMP,
    lease_owner = NULL,
    lease_until = NULL,
    last_error_code = NULL
WHERE event_id = :event_id
  AND lease_owner = :worker_id
  AND published_at IS NULL;
~~~

Điều kiện lease_owner tránh worker cũ ghi đè trạng thái của worker đã claim lại row sau khi lease hết hạn.

Cửa sổ lỗi vẫn còn: broker nhận event thành công, publisher crash trước câu UPDATE. Khi lease hết hạn, event được gửi lại. Đây là hành vi at-least-once có chủ đích; consumer phải xử lý duplicate an toàn.

Không đánh dấu published trước khi broker xác nhận. Nếu làm vậy rồi broker từ chối hoặc network lỗi trước khi nhận event, outbox có thể bị mất khỏi luồng retry.

## 9. Retry và xử lý outbox record lỗi

Lỗi publish có thể là transient hoặc permanent:

| Lỗi | Hành động |
|---|---|
| Timeout/network reset | Retry với backoff |
| Broker throttling | Tôn trọng quota/retry-after nếu có |
| Authentication/authorization | Cảnh báo và sửa quyền; không retry vô hạn |
| Payload vượt giới hạn | Đưa vào trạng thái cần xử lý, sửa contract hoặc dùng reference |
| Schema/config sai | Quarantine record và điều tra |
| Broker unavailable kéo dài | Giữ outbox, cảnh báo backlog, giới hạn producer nếu cần |

Backoff có jitter giúp publisher không tạo retry storm:

\[
delay_n = random(0,\ min(maxDelay,\ baseDelay \times 2^n))
\]

Cần giới hạn attempt hoặc tổng tuổi event, nhưng không xóa event nghiệp vụ chỉ vì publisher đã thử nhiều lần. Có thể chuyển record sang trạng thái NEEDS_ATTENTION, giữ payload, phát cảnh báo và yêu cầu can thiệp. Chính sách lưu trữ phải bảo đảm không làm mất event chưa được xác nhận.

Một event lỗi không nên chặn toàn bộ outbox. Tuy nhiên, nếu thứ tự trong cùng aggregate là bắt buộc, event version sau có thể phải chờ event trước. Đây là quyết định giữa availability và ordering, cần được ghi rõ trong thiết kế.

## 10. Giữ thứ tự event theo aggregate

Nhiều publisher chạy song song có thể phát event của cùng aggregate sai thứ tự. Ví dụ version 5 bị xử lý chậm trong khi version 6 được publisher khác gửi trước.

Nếu thứ tự quan trọng:

- Dùng aggregate_id làm partition key hoặc message group key.
- Publisher chỉ gửi event kế tiếp của một aggregate khi event trước đã được broker xác nhận.
- Không cho nhiều publisher đồng thời phát cùng aggregate.
- Dùng aggregate_version để consumer phát hiện event cũ hoặc gap.
- Chấp nhận rằng một event lỗi có thể chặn các version sau của aggregate đó.

Không cần giữ thứ tự toàn cục nếu nghiệp vụ chỉ yêu cầu thứ tự trong một aggregate. Chia theo aggregate giúp nhiều aggregate được publish song song.

Một query claim có thể loại các row đang có event version thấp hơn chưa publish, nhưng logic SQL phải được kiểm thử dưới concurrency. Một cách khác là phân vùng publisher theo hash của aggregate_id và xử lý tuần tự trong từng partition.

Broker ordering chỉ giữ thứ tự trong phạm vi mà broker hỗ trợ, ví dụ message group hoặc partition. Nó không sửa được event producer đã cấp version sai hoặc event được replay ngoài thứ tự.

## 11. CDC publisher thay cho polling

Change Data Capture (CDC) đọc transaction log hoặc change stream của database để phát hiện outbox record mới. Ví dụ:

- Debezium đọc transaction log của PostgreSQL/MySQL và dùng outbox event router.
- DynamoDB Streams phát record thay đổi của bảng outbox.
- Một dịch vụ CDC được quản lý đọc log database rồi chuyển record tới broker.

CDC giảm nhu cầu polling liên tục và có thể giảm độ trễ. Nhưng CDC không loại bỏ duplicate, ordering hoặc schema compatibility.

Cần quản lý:

- Connector offset/checkpoint.
- Transaction log retention.
- Restart và resnapshot.
- Schema history.
- Connector lag.
- Quyền đọc transaction log.
- Backpressure khi broker chậm.
- Duplicate khi connector gửi lại sau restart.

Nếu connector bị dừng lâu hơn retention của transaction log, có thể cần resnapshot hoặc quy trình khôi phục riêng. Không coi CDC là một dịch vụ “bật lên là exactly-once”.

### 11.1. Polling hay CDC?

| Tiêu chí | Polling publisher | CDC publisher |
|---|---|---|
| Độ phức tạp ban đầu | Thấp hơn | Cao hơn |
| Độ trễ | Theo chu kỳ polling | Thường thấp hơn |
| Tải query database | Có polling/index scan | Đọc transaction log/change stream |
| Quản lý offset | Lease và trạng thái outbox | Connector offset/checkpoint |
| Vận hành | Worker và retry | Connector, log retention và recovery |
| Phù hợp | Hệ thống nhỏ/vừa, muốn tự kiểm soát | Lưu lượng lớn hoặc cần độ trễ thấp |

Không có lựa chọn đúng cho mọi hệ thống. Bắt đầu bằng polling có thể hợp lý nếu tải chưa lớn; chuyển sang CDC khi số liệu cho thấy polling tạo tải hoặc độ trễ không còn phù hợp.

## 12. Transactional outbox với DynamoDB và Lambda

DynamoDB không dùng SQL transaction thông thường, nhưng TransactWriteItems có thể ghi nhiều item theo một transaction. Một request có thể:

- Cập nhật order item với condition version.
- Put một outbox item có eventId duy nhất.
- Commit cả hai hoặc không commit.

Ví dụ cấu trúc item outbox:

~~~json
{
  "PK": "OUTBOX#2026-11-17",
  "SK": "ORDER#order-42#VERSION#7",
  "eventId": "evt-order-42-v7",
  "aggregateId": "order-42",
  "aggregateVersion": 7,
  "eventType": "OrderStatusChanged",
  "schemaVersion": 1,
  "payload": {
    "status": "PAID"
  }
}
~~~

DynamoDB Streams có thể kích hoạt Lambda khi outbox item được thêm. Consumer lọc record INSERT thuộc loại outbox rồi publish hoặc xử lý event. Cần thiết kế partition key, stream view type, retention và quyền IAM theo workload.

Stream delivery có thể được retry; Lambda có thể xử lý lại batch hoặc record. Consumer/publisher vẫn cần idempotency. Nếu stream là đường duy nhất để chuyển event và record hết retention trước khi được xử lý, cần cơ chế cảnh báo và phục hồi phù hợp với thiết kế lưu trữ.

Không đặt outbox item ở một hệ thống hoặc bảng không tham gia cùng TransactWriteItems với business state rồi giả định transaction vẫn nguyên tử.

## 13. Lambda làm publisher: concurrency và database connection

Một scheduled Lambda có thể poll outbox, nhưng cần giới hạn số execution environment và batch size:

- Reserved concurrency có thể giới hạn tổng publisher invocation.
- Batch size giới hạn số row mỗi lần claim.
- Lease giúp nhiều invocation không gửi cùng row trong trường hợp bình thường.
- Connection pool phải nhỏ và được tái sử dụng trong execution environment.
- Timeout cần đủ cho claim, publish batch và cập nhật trạng thái.
- RDS Proxy hoặc connection pooling phù hợp có thể giúp giảm áp lực kết nối khi Lambda scale.

Nếu mỗi Lambda environment mở nhiều connection và publisher scale nhanh, database có thể cạn connection dù broker còn capacity. Tính tổng connection theo concurrency tối đa, pool size và các workload khác cùng dùng database.

Không để mỗi invocation tạo hàng trăm thread publish song song. Chọn concurrency dựa trên quota broker, database và ordering requirements.

### 13.1. Polling theo lịch và worker liên tục

**Scheduled Lambda** phù hợp khi lưu lượng outbox vừa phải và chấp nhận độ trễ theo chu kỳ. Cần tránh invocation chồng lấn nếu một batch chạy lâu hơn lịch kích hoạt.

**Worker dài hạn trên container** phù hợp khi throughput ổn định hoặc cần kiểm soát connection/polling liên tục. Worker vẫn cần lease, retry và shutdown an toàn.

**CDC managed connector** phù hợp khi tổ chức đã có hạ tầng CDC và cần độ trễ thấp. Cần có đội ngũ theo dõi connector lag và transaction log retention.

## 14. Consumer vẫn cần inbox và idempotency

Outbox publisher có thể gửi event lặp sau crash. Consumer nên dùng inbox table hoặc idempotency store với unique key:

~~~sql
CREATE TABLE inbox_event (
    consumer_name VARCHAR(120) NOT NULL,
    event_id       VARCHAR(200) NOT NULL,
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong một transaction phía consumer:

1. Insert inbox record bằng unique key.
2. Nếu key đã tồn tại và business operation đã hoàn tất, trả duplicate.
3. Cập nhật business state.
4. Ghi outbox mới nếu consumer phát event tiếp.
5. Commit.
6. ACK/checkpoint sau commit.

Unique key cần phân biệt consumer hoặc operation để hai consumer độc lập không chặn nhau. Retention của inbox phải đủ dài cho thời gian retry, DLQ redrive và event replay có thể xảy ra.

Nếu consumer gọi external API, dùng idempotency key do provider hỗ trợ. Database transaction nội bộ không thể tự rollback một side effect đã xảy ra ở hệ thống bên ngoài.

## 15. Không dùng callback sau commit thay outbox

Một cách thường thấy là dùng callback như TransactionalEventListener ở giai đoạn AFTER_COMMIT rồi publish event trực tiếp. Cách này giảm độ trễ, nhưng vẫn có cửa sổ:

- Database commit thành công.
- Process bị dừng trước khi callback chạy hoặc trước khi broker nhận event.
- Không có durable record để publisher khác thử lại.

Có thể dùng callback sau commit để đánh thức một poller hoặc gửi tín hiệu tối ưu hóa, nhưng outbox record phải là nguồn dữ liệu bền vững. Nếu callback bị mất, poller/CDC vẫn phải phát hiện event.

## 16. Payload lớn và dữ liệu nhạy cảm

Outbox table thường nằm trong database nghiệp vụ. Payload quá lớn có thể làm tăng write amplification, backup size, replication lag và query cost.

Với payload lớn:

- Lưu object bất biến trong object storage trước hoặc theo workflow có quản lý.
- Ghi object reference, checksum và version vào outbox.
- Bảo đảm object đã tồn tại và được bảo vệ trước khi transaction commit event tham chiếu tới nó.
- Có lifecycle policy không xóa object khi event còn có thể được retry/replay.
- Consumer kiểm tra checksum và authorization khi tải object.

Nếu object upload thành công nhưng database transaction rollback, có thể tạo orphan object; cần lifecycle cleanup hoặc garbage collection. Nếu database commit nhưng object không tồn tại, consumer không thể xử lý. Thiết kế thứ tự upload, reference và cleanup rõ ràng.

Không đưa secret, bearer token hoặc dữ liệu cá nhân không cần thiết vào event. Outbox, broker và DLQ đều có thể giữ dữ liệu lâu hơn request ban đầu.

## 17. Schema evolution và versioning

Event có thể nằm trong outbox hoặc broker lâu hơn một lần deploy. Consumer mới phải hiểu event cũ; publisher mới không nên phát payload phá vỡ consumer cũ trong quá trình rolling deployment.

Nên:

- Có schemaVersion và eventType ổn định.
- Ưu tiên thêm field optional có default.
- Không thay đổi ý nghĩa field hiện có.
- Duy trì backward compatibility trong khoảng retention/replay.
- Dùng upcaster hoặc adapter khi cần chuyển schema.
- Lưu event payload đã serialize tại thời điểm transaction, không serialize lại từ entity hiện tại lúc publish.

Điểm cuối rất quan trọng: nếu publisher đọc lại order hiện tại rồi dựng event cũ từ trạng thái mới, event OrderUpdated v5 có thể vô tình chứa dữ liệu của version 8. Outbox nên lưu snapshot event hoặc reference có version bất biến để bảo toàn ý nghĩa tại thời điểm commit.

## 18. Cleanup, retention và partitioning

Outbox là bảng tăng liên tục. Cần chính sách dọn dẹp:

- Chỉ xóa hoặc archive event đã publish và đã qua thời gian lưu cần thiết.
- Giữ event chưa publish hoặc đang cần điều tra.
- Không xóa event chỉ vì attempt_count lớn.
- Dùng batch delete để tránh transaction quá lớn.
- Cân nhắc partition theo created_at nếu volume cao.
- Lưu audit/metrics trước khi xóa.
- Giữ đủ dữ liệu để replay theo yêu cầu nghiệp vụ.

Nếu event được giữ trong broker hoặc event archive, xác định rõ outbox có phải nguồn audit lâu dài không. Có thể chuyển event đã publish sang archive riêng trước khi cleanup.

Không để cleanup job cạnh tranh với publisher và xóa row đang có lease. Dùng điều kiện published_at, lease state và cutoff time rõ ràng.

## 19. Bảo mật và quyền truy cập

Outbox chứa event nghiệp vụ nên cần bảo vệ như dữ liệu production:

- Chỉ application role được insert event.
- Publisher role chỉ đọc outbox và cập nhật trạng thái publish cần thiết.
- Consumer không cần quyền truy cập trực tiếp toàn bộ outbox database nếu chỉ nhận event qua broker.
- Mã hóa database, backup và transport.
- Giới hạn quyền đọc payload.
- Không log raw payload nếu có PII hoặc secret.
- Audit thay đổi trạng thái, export và thao tác replay.
- Tách quyền vận hành database khỏi quyền publish event khi phù hợp.

Publisher không nên có quyền sửa business table. Nếu publisher bị xâm nhập, quyền tối thiểu giúp giới hạn tác động ở luồng event.

## 20. Quan sát outbox và phát hiện backlog

Các metric cần có:

- Số row chưa publish.
- Tuổi của outbox event cũ nhất chưa publish.
- Publish latency từ created_at đến published_at.
- Attempt count và tỷ lệ publish failure.
- Số event đang có lease và lease hết hạn.
- Số event NEEDS_ATTENTION hoặc bị quarantine.
- Throughput event/giây.
- CDC connector lag hoặc polling duration.
- Database connection usage và query latency.
- Consumer lag, duplicate rate và downstream error rate.

Một publisher có thể không báo error nhưng backlog vẫn tăng vì tốc độ publish thấp hơn tốc độ tạo event. Cảnh báo oldest unpublished age thường có ý nghĩa vận hành hơn chỉ đếm số row.

Log nên có eventId, aggregateId, aggregateVersion, eventType và publisher/worker ID. Không dùng eventId hoặc aggregateId làm metric dimension có cardinality cao; để chúng trong log/trace.

## 21. Kiểm thử failure window

Outbox cần được kiểm thử ở các điểm crash cụ thể:

| Tình huống | Kết quả mong đợi |
|---|---|
| Business update thất bại trước commit | Không có outbox event |
| Outbox insert thất bại | Business update rollback |
| Commit thành công, application crash | Publisher vẫn tìm thấy event |
| Broker từ chối publish | Event còn pending và được retry |
| Broker nhận event, publisher crash trước mark-published | Event có thể được gửi lặp; consumer deduplicate |
| Lease hết hạn khi worker cũ còn chạy | Không để worker cũ ghi đè claim mới |
| Consumer commit xong nhưng ACK thất bại | Event giao lại nhưng side effect không lặp |
| Hai publisher claim đồng thời | Một row không bị hai worker xử lý bình thường cùng lúc |
| Event version trước bị lỗi | Chính sách ordering quyết định event sau có chờ hay không |

Integration test nên dùng database và broker thật trong môi trường cô lập hoặc test container phù hợp. Mock chỉ xác minh logic gọi method; nó không chứng minh transaction, lock, lease hoặc acknowledgement semantics.

## 22. Quy trình triển khai transactional outbox

Một lộ trình có thể thực hiện:

1. Xác định các business write hiện đang publish event trực tiếp.
2. Xác định event contract, event ID và aggregate version.
3. Tạo outbox table và index.
4. Thêm insert outbox vào cùng transaction với business write.
5. Viết publisher polling hoặc cấu hình CDC.
6. Thêm lease/claim, retry và trạng thái cần điều tra.
7. Đưa idempotency vào consumer trước khi chuyển traffic.
8. Kiểm thử crash window và duplicate.
9. Canary publisher với một loại event hoặc một nhóm aggregate.
10. Theo dõi outbox lag, consumer lag và business reconciliation.
11. Chuyển dần producer sang outbox.
12. Gỡ đường publish trực tiếp sau khi xác nhận không còn dual path.

Nếu trong giai đoạn chuyển đổi cả đường cũ và outbox cùng publish một event, consumer có thể nhận duplicate. Cần giữ eventId ổn định hoặc dùng migration marker để tránh phát hai bản có identity khác nhau.

## 23. Những lỗi thường gặp

**Ghi database rồi publish trực tiếp:** Process crash giữa hai thao tác làm mất event. Ghi outbox cùng transaction.

**Publish trong transaction database:** Network call kéo dài transaction và broker không tham gia rollback. Chỉ insert outbox trong transaction, publish sau commit.

**Dùng callback AFTER_COMMIT thay outbox:** Callback có thể không chạy sau process crash. Dùng durable outbox record.

**Đánh dấu published trước khi broker xác nhận:** Event có thể bị mất. Chỉ mark sau acknowledgement.

**Giả định publisher không gửi trùng:** Crash sau send có thể gây duplicate. Consumer phải idempotent.

**Không có lease khi chạy nhiều publisher:** Hai worker có thể gửi cùng row đồng thời. Dùng row lock, SKIP LOCKED hoặc cơ chế claim tương đương.

**Lease quá ngắn:** Worker khác claim lại khi lần publish đầu vẫn đang chạy. Đặt timeout/lease hợp lý và hỗ trợ renew nếu cần.

**Không giữ thứ tự theo aggregate:** Publisher song song có thể phát version sau trước version trước. Dùng partition key và serialization per aggregate.

**Outbox payload được dựng lại từ entity hiện tại:** Event lịch sử có thể mang state mới hơn. Lưu payload snapshot hoặc reference bất biến tại thời điểm commit.

**Không cleanup outbox:** Bảng phình lớn và index/query chậm. Dọn theo batch sau retention và chỉ với record đã publish.

**Retry lỗi cấu hình vô hạn:** AccessDenied hoặc schema sai không tự hết. Phân loại lỗi và chuyển sang trạng thái cần điều tra.

**Lambda publisher mở quá nhiều database connection:** Scale-out có thể làm database cạn connection. Giới hạn concurrency, pool và batch size.

## 24. Checklist production

- [ ] Business state và outbox record dùng cùng database transaction.
- [ ] Repository dùng cùng transaction manager và datasource.
- [ ] Event ID ổn định và event contract có schemaVersion.
- [ ] Event payload phản ánh đúng state tại thời điểm commit.
- [ ] Aggregate version/sequence được cấp nhất quán.
- [ ] Publisher chỉ đọc event đã commit.
- [ ] Publisher claim row bằng lock/lease an toàn khi chạy song song.
- [ ] Broker acknowledgement xảy ra trước khi mark-published.
- [ ] Crash sau send được xem là có thể tạo duplicate.
- [ ] Consumer có inbox/unique constraint hoặc idempotency store.
- [ ] Thứ tự theo aggregate được giữ nếu nghiệp vụ yêu cầu.
- [ ] Retry có backoff, jitter và phân loại lỗi.
- [ ] Record lỗi có trạng thái điều tra, không bị xóa âm thầm.
- [ ] Outbox cleanup chỉ xóa record đã publish sau retention.
- [ ] CDC offset/log retention được giám sát nếu dùng CDC.
- [ ] Lambda concurrency và DB connection pool được giới hạn.
- [ ] Payload nhạy cảm được bảo vệ và không ghi raw vào log.
- [ ] Có metric oldest unpublished age và publish lag.
- [ ] Có integration test cho rollback, crash, duplicate và ordering.
- [ ] Có reconciliation để kiểm tra business state với downstream.

## Kết luận

Transactional outbox đồng bộ thay đổi dữ liệu với event bằng cách ghi business state và event record trong cùng một database transaction. Publisher riêng đọc các record đã commit và gửi tới queue hoặc event bus. Cách này loại bỏ khoảng trống dual-write giữa database và broker, đồng thời cho phép retry sau khi application bị dừng.

Outbox không tự tạo exactly-once delivery. Publisher có thể gửi lặp sau crash, vì vậy consumer cần inbox/idempotency; thứ tự cần được quản lý theo aggregate version và partition key. Với Java serverless, polling Lambda, worker dài hạn và CDC đều có thể làm publisher, nhưng phải kiểm soát lease, concurrency, database connection, retry, retention và observability. Khi các ranh giới này được thiết kế rõ, hệ thống có thể phát event đáng tin cậy mà vẫn giữ trạng thái nghiệp vụ nhất quán.

