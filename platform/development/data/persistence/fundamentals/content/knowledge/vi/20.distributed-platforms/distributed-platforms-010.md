# Vấn đề ghi đồng thời vào hai hệ thống (dual write)

Một dịch vụ đặt hàng Java vừa ghi đơn hàng vào PostgreSQL vừa gửi thông điệp `OrderCreated` tới message broker. Nếu cơ sở dữ liệu đã commit nhưng broker chưa nhận thông điệp, dịch vụ xử lý giao hàng có thể không bao giờ biết có đơn mới. Nếu gửi thông điệp trước rồi transaction database rollback, bên giao hàng có thể xử lý một đơn **không tồn tại**. Đổi thứ tự hai lời gọi chỉ làm thay đổi tình huống lỗi, không biến chúng thành một giao dịch nguyên tử.

Đó là **dual write**: một thao tác nghiệp vụ phải tạo tác động ở **hai hệ thống độc lập** — chẳng hạn database và broker, database và Redis, hai database, database và dịch vụ thanh toán — nhưng không có một ranh giới commit duy nhất tự động bao trùm cả hai.

Bài học thuộc chương **Nền tảng phân tán** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Người học sẽ kết nối kiến thức Java persistence, transaction, durability, kiểm soát đồng thời và xử lý lỗi để hiểu tại sao dual write khó, thiết kế **transactional outbox**, **inbox/deduplication**, retry và đối soát, đồng thời nhận diện trường hợp cần saga hoặc giao thức giao dịch phân tán.

**Thông điệp cốt lõi:** hai lời gọi `write()` thành công liên tiếp **không** chứng minh hệ thống có bảo đảm *all-or-nothing*. Muốn đúng đắn phải xác định **đâu là nguồn sự thật**, **thao tác nào commit nguyên tử**, **điều gì xảy ra nếu crash ở từng điểm**, và **cách khôi phục an toàn**.

## 1. Dual write xuất hiện ở đâu?

| Nhu cầu | Hệ thống thứ nhất | Hệ thống thứ hai | Hệ quả nếu chỉ một bên thành công |
| --- | --- | --- | --- |
| Tạo đơn và thông báo | PostgreSQL: `orders` | Kafka/RabbitMQ: `OrderCreated` | Đơn tồn tại nhưng không được xử lý tiếp; hoặc có event về đơn chưa commit |
| Đổi giá và xóa cache | Database sản phẩm | Redis/Caffeine | Cache phục vụ giá cũ hoặc vô hiệu hóa quá sớm |
| Cập nhật hồ sơ và chỉ mục tìm kiếm | Database hồ sơ | OpenSearch/Elasticsearch | Người dùng không tìm thấy hồ sơ đã ghi, hoặc tìm thấy dữ liệu bị rollback |
| Đặt hàng và thu tiền | Database đơn hàng | Payment provider qua HTTP | Có đơn nhưng chưa thu tiền; hoặc tiền đã thu mà đơn chưa được lưu |
| Ghi dữ liệu chính và phân tích | Transactional store | Kho analytics/warehouse | Số liệu thống kê thiếu hoặc trùng bản ghi |
| Ghi hai database trong hai dịch vụ | Database A | Database B | Một bên phản ánh trạng thái mới, bên kia vẫn ở trạng thái cũ |

Dual write không nhất thiết xảy ra trong một thread hoặc cùng một phương thức. Nếu một request cần hai tác động ở hai miền lưu trữ khác nhau và **nghiệp vụ mong chúng tương ứng**, bài toán đồng bộ vẫn tồn tại.

Cũng cần phân biệt:

- **Hai câu SQL trong cùng một transaction của cùng database** thường không phải dual write theo nghĩa cần giải quyết ở đây: database có thể commit/rollback chúng nguyên tử.
- **Hai connection tới hai database độc lập** không tự chia sẻ transaction, dù cả hai đều dùng JDBC.
- **Một transaction database và một lệnh HTTP** gần như luôn thuộc hai ranh giới nguyên tử riêng.
- **Một broker có giao dịch riêng** không có nghĩa transaction đó bao trùm database khác.

## 2. Ranh giới commit: vì sao `@Transactional` chưa đủ?

Trong Spring, phương thức sau nhìn có vẻ an toàn:

~~~java
@Transactional
public void placeOrder(PlaceOrder command) {
    Order order = orderRepository.insert(command);
    eventPublisher.publish(new OrderCreated(order.id()));
}
~~~

Giả sử `orderRepository` tham gia transaction PostgreSQL còn `eventPublisher` gửi trực tiếp tới broker. Annotation `@Transactional` thường chỉ quản lý **một transaction manager và những tài nguyên được enlist đúng cách**. Lời gọi gửi broker ở đây **không tự động** được rollback khi transaction PostgreSQL rollback.

~~~mermaid
flowchart LR
    A[Application Service] --> B[Transaction PostgreSQL]
    A --> C[Broker publish]
    B --> D[(Orders DB)]
    C --> E[(Message Broker)]
    D -.- F[Hai điểm xác nhận độc lập]
    E -.- F
~~~

Ngay cả khi API gửi event trả thành công, điều đó chỉ có ý nghĩa theo **hợp đồng acknowledgement của broker/client** (ví dụ đã nhận vào broker theo cấu hình), không chứng minh PostgreSQL đã commit. Ngược lại, `entityManager.flush()` chỉ đưa thay đổi ORM đến database trong transaction hiện tại; nó không commit và không đồng bộ với broker.

### Ba tầng cần phân biệt

1. **Đã gọi API ghi:** client có thể mới đưa dữ liệu vào buffer hoặc gửi trên mạng.
2. **Hệ thống đích xác nhận ghi:** ý nghĩa phụ thuộc write concern, acknowledgement, replication và cấu hình durability của đích.
3. **Nghiệp vụ hoàn thành nhất quán:** mọi điều kiện cần thiết đã được đáp ứng hoặc có quy trình khôi phục được trạng thái chưa hoàn tất.

Đừng đổi tên `publish()` thành `publishReliably()` rồi mặc định bước thứ ba được bảo đảm.

## 3. Ma trận lỗi của cách “ghi DB rồi gửi event”

Xem trình tự phổ biến:

~~~text
BEGIN DB TRANSACTION
  INSERT orders
COMMIT DB
PUBLISH OrderCreated TO broker
RETURN HTTP 201
~~~

| Điểm xảy ra lỗi | DB | Broker | Hậu quả |
| --- | --- | --- | --- |
| Trước DB commit, rollback thành công | Không có đơn đã commit | Chưa có event | Không tạo đơn; có thể thử lại |
| **Sau commit, trước publish** | Có đơn | **Không có event** | Downstream có thể không bao giờ chạy |
| Publish timeout, broker thực ra đã nhận | Có đơn | **Có thể** đã nhận | Retry publish có thể tạo event trùng |
| Publish thành công, HTTP response mất | Có đơn | Có event | Client retry tạo đơn/event trùng nếu thiếu idempotency |
| Process crash ngay sau commit | Có đơn | Chưa biết đã publish chưa | Không thể phục hồi chỉ từ RAM của process |

Chỉ cần một lần crash ở khoảng giữa **commit DB** và **publish broker** là đủ tạo trạng thái lệch. Đặt `publish()` trong `try/catch` rồi retry vài lần **không giải quyết** trường hợp tiến trình chết vĩnh viễn trước khi retry được lên lịch.

~~~mermaid
sequenceDiagram
    participant A as Java Service
    participant DB as PostgreSQL
    participant B as Broker
    A->>DB: INSERT order 125
    A->>DB: COMMIT
    DB-->>A: Commit thành công
    Note over A: Crash trước publish
    Note over DB: Order 125 tồn tại
    Note over B: Không có OrderCreated(125)
~~~

## 4. Gửi event trước DB commit cũng thất bại

Một người có thể đề nghị đổi thứ tự:

~~~text
BEGIN DB TRANSACTION
  INSERT orders
PUBLISH OrderCreated TO broker
COMMIT DB
~~~

Nó tránh được cửa sổ “DB commit nhưng chưa gửi event” ở một số tình huống, nhưng tạo ra nguy cơ khác:

~~~mermaid
sequenceDiagram
    participant A as Java Service
    participant B as Broker
    participant DB as PostgreSQL
    A->>DB: BEGIN; INSERT order 126
    A->>B: PUBLISH OrderCreated(126)
    B-->>A: Acknowledged
    A->>DB: COMMIT
    DB-->>A: Lỗi; transaction rollback
    Note over B: Event đã có, order không tồn tại
~~~

Consumer có thể nhận event **trước khi đơn hiển thị được ở database**, hoặc nhận event về đơn đã rollback. Chờ một chút rồi đọc lại DB chỉ che triệu chứng, không giải quyết tính nguyên tử.

| Thứ tự | Cửa sổ lỗi tiêu biểu | Kết quả thường gặp |
| --- | --- | --- |
| DB commit → publish | Crash sau commit trước publish | **Thiếu event** |
| Publish → DB commit | DB rollback sau publish | **Event giả / sự kiện sớm** |
| DB ghi → cache cập nhật trước commit | DB rollback sau cache update | **Cache phản ánh dữ liệu chưa commit** |
| DB commit → cache cập nhật | Crash sau commit trước cache update | **Cache stale** |

Không có thứ tự hai lời gọi trực tiếp nào đảm bảo *all-or-nothing* khi hai hệ không tham gia cùng một giao thức commit.

## 5. Không thể suy kết quả ghi từ timeout

Một lỗi mạng tại thời điểm ghi có thể là **ambiguous outcome**:

~~~text
Java ---- gửi PUBLISH ----> Broker
Java <---- [mất phản hồi] ---- Broker đã lưu message?
~~~

Ứng dụng có thể nhận timeout vì:

- Request chưa đến broker.
- Broker đã nhận nhưng chưa xác nhận.
- Broker đã lưu và xác nhận, nhưng gói response bị mất.
- Kết nối bị cắt trong một lần failover.

Trong nhiều trường hợp Java **không biết chắc** bên kia đã áp dụng thao tác hay chưa. Nếu thử lại, có thể tạo duplicate; nếu bỏ qua, có thể mất event.

Điều này đúng với DB `COMMIT` bị mất phản hồi, HTTP gọi payment provider, lệnh ghi vào một kho thứ hai và cả việc đánh dấu event đã xử lý ở consumer. Vì vậy, thiết kế đúng không chỉ trả lời “khi lỗi thì retry”, mà phải trả lời **retry có gây side effect lặp không và làm sao đối soát nếu không biết kết quả**.

## 6. Transactional outbox: gom hai ghi *quan trọng* vào một transaction DB

Mẫu **transactional outbox** thay lời gọi trực tiếp tới broker bằng **một bản ghi yêu cầu phát event nằm trong cùng database** với dữ liệu nghiệp vụ:

~~~text
BEGIN DB TRANSACTION
  INSERT orders (...)
  INSERT outbox_events (event_id, aggregate_id, type, payload, ...)
COMMIT DB

Sau commit:
  Worker đọc outbox_events
  Worker gửi event tới broker
  Worker đánh dấu đã publish theo chính sách
~~~

Do `orders` và `outbox_events` nằm trong **cùng một transaction database**, nếu transaction rollback, cả đơn lẫn yêu cầu phát event đều bị hủy. Nếu commit thành công, cả hai cùng được ghi nhận ở DB.

~~~mermaid
flowchart TD
    A[Java Application Service] --> B[BEGIN DB transaction]
    B --> C[INSERT / UPDATE nghiệp vụ]
    C --> D[INSERT outbox event]
    D --> E{COMMIT?}
    E -- Lỗi / ROLLBACK --> F[Không có nghiệp vụ, không có event pending]
    E -- Thành công --> G[(DB: nghiệp vụ + outbox)]
    G --> H[Outbox worker / CDC]
    H --> I[(Message Broker)]
    I --> J[Consumer]
~~~

**Outbox không làm broker và database cùng commit nguyên tử.** Nó chuyển bài toán từ “hai ghi liên tiếp không thể phục hồi” thành “một ghi nguyên tử trong DB và một công việc phát lại được”. Khoảng giữa commit và publish vẫn có độ trễ; worker phải có retry và monitoring.

### Bảo đảm nào thực sự đạt được?

Nếu thiết kế đầy đủ:

- **Atomicity cục bộ:** thay đổi nghiệp vụ và việc ghi *ý định phát event* cùng commit/rollback.
- **Không bỏ quên event đã commit một cách im lặng:** outbox vẫn còn để worker xử lý sau crash, trong phạm vi độ bền của DB và chính sách retention.
- **Khả năng publish lại:** worker có thể thử gửi những event chưa xác nhận.
- **Có thể gửi trùng:** nếu broker đã nhận nhưng worker crash trước khi đánh dấu published, event sẽ được gửi lại.
- **Eventual delivery có điều kiện:** chỉ khi worker tiếp tục chạy, lỗi được xử lý/retry, không bị xóa mất event và hạ tầng cuối cùng phục hồi.

Do đó, kiến trúc outbox thường hướng tới **at-least-once publication**, không phải “mọi event chắc chắn được phát đúng một lần end-to-end”.

## 7. Thiết kế bảng outbox và định danh event

Ví dụ trên PostgreSQL:

~~~sql
CREATE TABLE orders (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id  UUID NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    total       NUMERIC(18, 2) NOT NULL CHECK (total > 0),
    status      VARCHAR(20) NOT NULL
);

CREATE TABLE outbox_events (
    event_id         UUID PRIMARY KEY,
    aggregate_type   VARCHAR(80) NOT NULL,
    aggregate_id     VARCHAR(120) NOT NULL,
    aggregate_version BIGINT,
    event_type       VARCHAR(100) NOT NULL,
    payload          JSONB NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at     TIMESTAMPTZ,
    attempt_count    INTEGER NOT NULL DEFAULT 0,
    lease_owner      UUID,
    lease_until      TIMESTAMPTZ
);

CREATE INDEX outbox_unpublished_created_idx
    ON outbox_events (created_at, event_id)
    WHERE published_at IS NULL;
~~~

| Trường | Mục đích |
| --- | --- |
| `event_id` | ID duy nhất, ổn định qua mọi lần publish/retry; consumer dùng để dedupe |
| `aggregate_type`, `aggregate_id` | Nêu nguồn phát event và khóa phân vùng/định tuyến khi cần |
| `aggregate_version` | Hỗ trợ phát hiện event đến sai thứ tự và kiểm soát phiên bản |
| `event_type` | Hợp đồng ngữ nghĩa như `OrderPlaced`, không chỉ “row updated” |
| `payload` | Dữ liệu cần cho consumer theo schema sự kiện có version |
| `created_at` | Quan sát độ trễ từ commit/ghi outbox đến publish |
| `published_at` | Dấu mốc worker đã nhận xác nhận từ broker theo chính sách |
| `attempt_count` | Chẩn đoán retry, lỗi lặp |
| `lease_owner`, `lease_until` | Giúp nhiều worker tranh chấp claim có kiểm soát nếu chọn polling |

Đây là **schema minh họa**, không phải lược đồ bắt buộc. Trong production, có thể thêm `schema_version`, `tenant_id`, `correlation_id`, `next_attempt_at`, khóa fencing/generation, last error code, partitioning hoặc cơ chế lưu trữ khác. Đừng lưu dữ liệu nhạy cảm không cần thiết trong payload; áp dụng retention, phân quyền và mã hóa phù hợp.

### Event ID khác business ID

`event_id` nhận diện **một sự kiện**. `order_id` nhận diện đơn. Một order có thể phát nhiều event theo thời gian. `request_id` nhận diện **một ý định tạo đơn** và giúp chống HTTP retry tạo đơn trùng. Ba loại khóa này liên quan nhưng khác mục đích:

~~~text
request_id = R-123       (một ý định đặt hàng)
order_id   = 125         (một thực thể nghiệp vụ)
event_id   = E-777       (sự kiện OrderPlaced của đơn 125)
event_id   = E-778       (sự kiện OrderConfirmed của đơn 125)
~~~

Nếu retry phát lại `OrderPlaced`, phải giữ nguyên `E-777`; không tạo event ID khác cho cùng một lần phát lặp.

## 8. Ví dụ Java/JDBC: ghi đơn và outbox trong cùng transaction

Ví dụ dưới đây dùng PostgreSQL, `DataSource` và JDBC thuần. Giả định request đã qua xác thực và `customerId` lấy từ ngữ cảnh được ủy quyền. `requestId` do client hoặc hệ thống cấp ổn định để chống retry HTTP tạo đơn trùng.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.UUID;
import javax.sql.DataSource;

public final class OrderApplicationService {
    private final DataSource dataSource;

    public OrderApplicationService(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public record PlacedOrder(long orderId, UUID eventId) {}

    public PlacedOrder placeOrder(
            UUID requestId, long customerId, BigDecimal total)
            throws SQLException {
        Objects.requireNonNull(requestId);
        Objects.requireNonNull(total);
        if (customerId <= 0 || total.signum() <= 0) {
            throw new IllegalArgumentException("Đơn hàng không hợp lệ");
        }

        UUID eventId = UUID.randomUUID();

        try (Connection c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                long orderId = insertOrder(
                        c, requestId, customerId, total);
                insertOutbox(c, eventId, orderId);

                // Hai INSERT thuộc cùng transaction của một DB.
                c.commit();
                return new PlacedOrder(orderId, eventId);
            } catch (SQLException | RuntimeException failure) {
                try {
                    c.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }

    private long insertOrder(Connection c, UUID requestId,
                             long customerId, BigDecimal total)
            throws SQLException {
        String sql = "INSERT INTO orders " +
                "(request_id, customer_id, total, status) " +
                "VALUES (?, ?, ?, 'PENDING') RETURNING id";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setObject(1, requestId);
            ps.setLong(2, customerId);
            ps.setBigDecimal(3, total);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Không nhận được order ID");
                }
                return rs.getLong(1);
            }
        }
    }

    private void insertOutbox(Connection c, UUID eventId, long orderId)
            throws SQLException {
        String payload = "{\"orderId\":" + orderId + "}";
        String sql = "INSERT INTO outbox_events " +
                "(event_id, aggregate_type, aggregate_id, " +
                "aggregate_version, event_type, payload) " +
                "VALUES (?, 'Order', ?, 1, 'OrderPlaced', CAST(? AS jsonb))";

        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setObject(1, eventId);
            ps.setString(2, Long.toString(orderId));
            ps.setString(3, payload);
            if (ps.executeUpdate() != 1) {
                throw new SQLException("Không lưu được outbox event");
            }
        }
    }
}
~~~

**Điều đúng về mã ví dụ:**

1. Có **một connection**, `autoCommit=false` và một transaction.
2. `orders` và `outbox_events` là hai bảng **cùng một database PostgreSQL**.
3. Nếu chèn event thất bại, `rollback()` hủy cả order chưa commit; nếu commit thành công, cả hai cùng hiện diện.
4. Không có lời gọi broker trong transaction; một worker khác phát event sau.
5. `try-with-resources` đóng `ResultSet`/`PreparedStatement` và connection khi rời phạm vi; đóng tài nguyên không thay commit.

**Giới hạn của mã ví dụ:** đây không phải endpoint sản xuất hoàn chỉnh. Nếu request có cùng `request_id` được retry, ràng buộc unique khiến lần chèn thứ hai thất bại; tầng API/service cần bắt và phân loại xung đột sau rollback, **truy vấn trạng thái đơn theo request ID bằng transaction mới**, rồi phát lại kết quả cũ nếu payload khớp. Nên lưu fingerprint để phát hiện cùng request ID nhưng payload đổi. Ngoài ra, lỗi mạng đúng lúc `commit()` có thể làm kết quả **chưa rõ**; gọi `rollback()` trong catch không chứng minh transaction chưa commit. Phải tra cứu/đối soát theo `request_id` trước khi xử lý lại.

Một dịch vụ dùng Spring có thể thay mã quản lý `Connection` bằng `@Transactional` ở application service, miễn là thao tác nghiệp vụ và ghi outbox **cùng tham gia transaction manager đúng DB**. Tạo một transaction khác trong adapter outbox sẽ phá bảo đảm nguyên tử.

## 9. Outbox relay: polling và Change Data Capture

Sau khi DB commit, hệ thống cần một thành phần **outbox relay** chuyển event đến broker.

### Cách A — Polling publisher

Worker định kỳ đọc các record chưa publish, claim một lô, gửi tới broker, rồi đánh dấu thành công:

~~~text
1. Claim N event chưa publish một cách cạnh tranh an toàn.
2. Thả transaction DB dùng để claim.
3. Publish event, giữ nguyên event_id.
4. Chờ broker acknowledgement theo cấu hình.
5. Ghi published_at theo owner/lease nếu còn quyền.
6. Nếu lỗi, áp dụng retry với backoff; có cơ chế xử lý poison event.
~~~

Với PostgreSQL, có thể claim bằng một transaction có `SELECT ... FOR UPDATE SKIP LOCKED`, hoặc dùng optimistic version/lease. Ví dụ minh họa claim:

~~~sql
WITH candidates AS (
    SELECT event_id
    FROM outbox_events
    WHERE published_at IS NULL
      AND (lease_until IS NULL OR lease_until < CURRENT_TIMESTAMP)
    ORDER BY created_at, event_id
    LIMIT 50
    FOR UPDATE SKIP LOCKED
)
UPDATE outbox_events o
SET lease_owner = :workerToken,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '30 seconds',
    attempt_count = attempt_count + 1
FROM candidates c
WHERE o.event_id = c.event_id
RETURNING o.event_id, o.event_type, o.payload, o.aggregate_id;
~~~

Đoạn SQL phải chạy trong một **transaction claim** và được commit trước khi worker publish nếu không muốn giữ khóa DB xuyên thao tác mạng. Worker khác bỏ qua record có lease còn hiệu lực. Nếu worker crash, lease hết hạn để một worker khác tiếp quản.

Sau khi broker xác nhận, worker chỉ đánh dấu event đã publish nếu vẫn sở hữu claim:

~~~sql
UPDATE outbox_events
SET published_at = CURRENT_TIMESTAMP,
    lease_owner = NULL,
    lease_until = NULL
WHERE event_id = :eventId
  AND lease_owner = :workerToken
  AND published_at IS NULL;
~~~

Đây là **mẫu cơ chế**, chưa đủ để sao chép vào production mà không bổ sung kiểm tra số dòng, lease renewal, backoff, timeout, retry policy và chống tranh chấp. Nếu lease hết hạn trong khi publish chưa xong, hai worker có thể **cùng publish một event**. Việc đánh dấu theo owner ngăn worker cũ sửa trạng thái của worker mới, nhưng **không ngăn broker nhận duplicate**; consumer vẫn phải idempotent.

### Cách B — Change Data Capture (CDC)

Một hệ CDC có thể đọc thay đổi đã commit từ transaction log/WAL của DB, lấy event từ bảng outbox và gửi sang broker. Ví dụ kiến trúc thường dùng một connector CDC (chẳng hạn Debezium cho hệ được hỗ trợ) thay cho logic polling thủ công.

~~~mermaid
flowchart LR
    A[Ứng dụng: transaction orders + outbox] --> B[(PostgreSQL)]
    B --> C[WAL / CDC connector]
    C --> D[(Broker topic)]
    D --> E[Consumers]
~~~

CDC có thể giảm nhu cầu scan bảng liên tục và khai thác thứ tự log commit của nguồn. Tuy nhiên, nó có các yêu cầu vận hành riêng: quyền đọc log, replication slot/log retention, schema evolution, snapshot/restart, lag, checkpoint connector và duplicate khi khởi động lại. **CDC không khiến broker với DB cùng commit nguyên tử** và không miễn trừ xử lý trùng phía consumer.

### Polling hay CDC?

| Tiêu chí | Polling outbox | CDC/outbox |
| --- | --- | --- |
| Độ phức tạp code trong ứng dụng | Worker claim/retry/ack | Ít code polling, nhiều phụ thuộc hạ tầng connector |
| Độ trễ | Phụ thuộc lịch poll và tải | Thường có thể theo sát log, vẫn có connector lag |
| Sắp thứ tự | Phải quản lý khi claim nhiều worker | Có thể tận dụng thứ tự log, cần xét phân vùng và consumer |
| Khả năng phục hồi | Outbox row, lease, retry | WAL/log offset, checkpoint, replay |
| Rủi ro vận hành | Lock contention, backlog, bảng lớn | Log retention, cấu hình connector, snapshot, schema |
| Phát lặp | Có | Vẫn có thể có, tùy đường truyền và chế độ |

Lựa chọn dựa trên yêu cầu SLO, năng lực vận hành và semantics của hệ cụ thể, không phải “CDC luôn exactly once”.

## 10. Cửa sổ gửi trùng không thể xóa bằng đánh dấu published

Giả sử worker xử lý event `E-777`:

~~~mermaid
sequenceDiagram
    participant W as Outbox Worker
    participant B as Broker
    participant DB as Outbox DB
    W->>B: Publish E-777
    B-->>W: Acknowledged
    Note over W: Worker crash trước UPDATE published_at
    Note over DB: E-777 vẫn là pending
    Note over W: Worker mới khởi động hoặc lease hết hạn
    W->>DB: Đọc E-777 chưa published
    W->>B: Publish lại E-777
    Note over B: Có thể có hai bản sao E-777
~~~

Nếu đánh dấu published **trước khi publish**, khi tiến trình chết giữa hai thao tác sẽ có **mất event**. Nếu đánh dấu **sau khi publish**, khi tiến trình chết giữa hai thao tác có **duplicate event**. Với hệ không có một transaction nguyên tử chung, thứ tự hợp lý để ưu tiên không mất thông điệp thường chấp nhận khả năng **gửi ít nhất một lần**, rồi yêu cầu xử lý trùng an toàn.

**Không nên tạo event ID mới khi gửi lại.** Nếu mỗi lần retry đặt một UUID khác nhau, consumer không còn cách đơn giản để nhận ra đây là bản sao của sự kiện cũ.

## 11. Inbox / processed-message: consumer xử lý trùng an toàn

Trong mô hình **at-least-once delivery**, consumer có thể nhận cùng một message nhiều lần vì broker gửi lại sau crash, timeout hoặc acknowledgment bị mất. Dedupe ở consumer thường dùng một bảng **inbox** hoặc `processed_messages` với unique constraint.

~~~sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      UUID NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Một consumer cập nhật **một database cục bộ** có thể làm:

~~~text
BEGIN TRANSACTION
  INSERT processed_messages(consumer_name, event_id)
  ON CONFLICT DO NOTHING;

  Nếu INSERT thêm đúng 1 dòng:
      Thực hiện UPDATE/INSERT nghiệp vụ trong cùng transaction.
  Nếu không thêm dòng:
      Bỏ qua side effect; message đã được xử lý.

COMMIT
ACK message với broker sau khi COMMIT.
~~~

Nếu consumer crash **trước commit**, cả marker inbox và thay đổi nghiệp vụ rollback; broker giao lại thì có thể xử lý. Nếu crash **sau commit nhưng trước ACK**, broker giao lại; unique constraint phát hiện event đã xử lý và không làm side effect lần hai.

Ví dụ SQL:

~~~sql
BEGIN;
INSERT INTO processed_messages (consumer_name, event_id)
VALUES ('shipping-service', :eventId)
ON CONFLICT DO NOTHING;
-- Chỉ thực thi update shipment nếu INSERT trả 1 affected row.
-- Ghi thay đổi shipment cùng transaction này.
COMMIT;
-- Sau commit mới ACK message với broker.
~~~

**Điều kiện quan trọng:** marker và side effect được bảo vệ trong **cùng transaction của cùng nguồn lưu trữ**. Nếu consumer gửi email hoặc gọi payment provider bên ngoài transaction này, inbox không tự biến thao tác bên ngoài thành nguyên tử; phải dùng idempotency của provider, outbox tiếp theo hoặc reconciliation.

### Idempotent effect khác deduplicate delivery

- **Duplicate delivery:** broker chuyển hai message có cùng `event_id`.
- **Duplicate processing:** code tạo tác động hai lần dù hai message cùng nội dung.
- **Business idempotency:** cùng ý định nghiệp vụ không làm tăng tác động khi gửi lại.

Một inbox giúp ngăn duplicate processing ở phạm vi consumer/database cụ thể. Nếu consumer có hai chức năng độc lập cần cùng event, dùng `consumer_name` hoặc namespace để mỗi chức năng có marker riêng.

## 12. Ordering: “at-least-once” chưa đủ để giữ đúng trạng thái

Giả sử hệ thống phát hai sự kiện cho cùng order:

~~~text
E1: OrderCreated, aggregate_version=1
E2: OrderCancelled, aggregate_version=2
~~~

Nếu E2 đến trước E1 (do nhiều worker, partition khác nhau, retry hoặc consumer xử lý song song), consumer chỉ ghi trạng thái theo thứ tự nhận sẽ có thể kết thúc sai ở `CREATED` dù order thực tế đã `CANCELLED`.

Giải pháp phụ thuộc yêu cầu:

- Gắn **aggregate ID** và **revision tăng đơn điệu** khi nguồn thay đổi.
- Định tuyến message cùng aggregate vào **cùng partition/key** khi broker hỗ trợ, đồng thời tránh xử lý song song phá thứ tự trong partition.
- Consumer kiểm tra `aggregate_version` và **không cho event cũ ghi đè phiên bản mới**.
- Nếu một workflow bắt buộc xử lý mọi bước liên tiếp, consumer cần cơ chế chờ/bù khi **thiếu version** thay vì luôn bỏ qua event đến muộn.
- Nếu mỗi event là delta (ví dụ `increaseBy(1)`), không thể tùy tiện bỏ qua bản cũ chỉ vì đã thấy version lớn hơn; cần replay theo thứ tự hoặc mô hình snapshot/commutative update phù hợp.

~~~sql
UPDATE order_projections
SET status = :status,
    revision = :incomingRevision
WHERE order_id = :orderId
  AND revision < :incomingRevision;
~~~

SQL này là ví dụ **chặn stale snapshot** nếu trạng thái trong event là **trạng thái đầy đủ** tại phiên bản đó. Nó chưa giải quyết trường hợp projection chưa có hàng; cần upsert có điều kiện tương đương. Nó cũng không thay quy trình quản lý event bị thiếu khi projection dựa vào nhiều bước incremental.

Ngay cả outbox có `ORDER BY created_at` cũng **không tự bảo đảm thứ tự xử lý cuối cùng**, đặc biệt khi có nhiều worker, nhiều partition, thời điểm commit khác thời điểm tạo record, lease retry và network reordering.

## 13. Khi hai hệ đều có trạng thái nghiệp vụ: saga thay vì giả vờ một commit

Transactional outbox rất phù hợp để phát **sự kiện về một thay đổi đã commit**. Nhưng một quy trình đặt hàng thường có nhiều trạng thái được duy trì bởi các dịch vụ:

1. Order Service tạo đơn ở trạng thái `PENDING_PAYMENT` và phát event.
2. Payment Service thu tiền hoặc từ chối; có kho dữ liệu và API/provider riêng.
3. Inventory Service giữ hàng nếu thành công, hoặc giải phóng nếu hủy.
4. Order Service chuyển sang `CONFIRMED`, `CANCELLED` hoặc trạng thái cần đối soát.

Đây là một **saga**: chuỗi transaction cục bộ liên kết bằng message/command và có cơ chế **compensation hoặc reconciliation** nếu một bước thất bại.

~~~mermaid
flowchart TD
    A[Order PENDING_PAYMENT] --> B[Payment requested via outbox]
    B --> C{Kết quả payment?}
    C -- Thành công --> D[Payment recorded]
    D --> E[Reserve inventory]
    E --> F{Reserve được?}
    F -- Có --> G[Order CONFIRMED]
    F -- Không --> H[Refund / cancel payment]
    H --> I[Order CANCELLED / kiểm tra đối soát]
    C -- Thất bại --> I
    C -- Chưa rõ --> J[Tra cứu provider, retry an toàn]
    J --> C
~~~

**Compensation không phải rollback tức thời**: tiền đã thu có thể phải hoàn sau, email đã gửi không thu hồi được, hàng giữ chỗ có thể hết hạn. Quy trình phải có trạng thái trung gian quan sát được, timeout, quyền sở hữu tác vụ, idempotency và cơ chế hỗ trợ khi lỗi kéo dài.

### Orchestration và choreography

| Mô hình | Ý nghĩa | Đánh đổi |
| --- | --- | --- |
| **Orchestration** | Một coordinator quyết định bước tiếp theo và trạng thái saga | Dễ nhìn luồng, nhưng coordinator là thành phần phải bền vững/phục hồi |
| **Choreography** | Các service phản ứng với event và phát event tiếp | Giảm điều phối tập trung, nhưng luồng phụ thuộc sự kiện khó theo dõi nếu nhiều bước |

Dù dùng kiểu nào, mỗi service vẫn phải tự bảo vệ **transaction cục bộ** và đảm bảo **message bị gửi trùng không làm side effect trùng**.

## 14. Dual write với cache và search index

Không phải mọi dual write cần cùng giải pháp như thanh toán. Đối với **cache hoặc search index được tái tạo từ nguồn chính**, có thể dùng eventual consistency và cơ chế đối soát:

~~~text
DB primary = source of truth
  |
  +-- COMMIT dữ liệu + outbox event
          |
          +-- worker cập nhật/xóa Redis cache
          +-- worker cập nhật search index
~~~

Những rủi ro còn lại:

- **Event trễ:** cache/search có thể phục vụ trạng thái cũ trước khi worker xử lý.
- **Event đảo thứ tự:** bản index cũ có thể ghi đè bản mới nếu không kiểm tra revision.
- **Reader nạp lại bản cũ sau invalidation:** race giữa cache miss, DB read và cache fill; outbox không xóa hết race này.
- **Index lỗi lâu ngày:** có thể phải rebuild từ DB hoặc chạy reconciliation.
- **Tạo/xóa thực thể:** event delete và recreate cùng ID cần generation/version phù hợp để tránh “hồi sinh” dữ liệu cũ.

Nếu dữ liệu dùng để **quyết định nghiệp vụ** như tồn kho hay quyền truy cập, không thể lấy cache/search chỉ vì API nhanh và giả định chúng đủ mới. Việc kiểm tra và cập nhật **nguồn authoritative** phải diễn ra ở điểm quyết định với ràng buộc phù hợp.

### Có cần outbox cho mọi lần xóa cache?

Không nhất thiết. Nếu stale trong TTL được chấp nhận, việc invalidate sau commit với fallback expiration có thể phù hợp và đơn giản. Nếu trễ invalidation gây thiệt hại nghiêm trọng hoặc cần dấu vết khôi phục, outbox/CDC là lựa chọn đáng cân nhắc. Thiết kế dựa trên **mức độ nhất quán được yêu cầu**, không áp dụng cùng độ phức tạp cho mọi cache.

## 15. Giao dịch phân tán / 2PC: khả năng và giới hạn

Về lý thuyết, **two-phase commit (2PC)** cho phép một coordinator phối hợp nhiều resource manager có hỗ trợ giao thức tham gia giao dịch:

~~~text
Phase 1 — PREPARE:
  Coordinator yêu cầu các participant chuẩn bị commit.
  Mỗi participant giữ trạng thái có thể commit hoặc báo không thể.

Phase 2 — COMMIT/ROLLBACK:
  Coordinator quyết định kết quả và yêu cầu các bên thực hiện.
~~~

Nếu dùng Java/JTA/XA với các resource thực sự hỗ trợ tham gia transaction được điều phối, có thể đạt atomic commit theo hợp đồng và cơ chế recovery của hạ tầng đó. **Nhưng không phải** một HTTP payment API, Redis command, Kafka producer hay dịch vụ SaaS bất kỳ đều là XA participant; cần xác minh hỗ trợ cụ thể.

Các đánh đổi của 2PC:

- Transaction phân tán giữ trạng thái và tài nguyên trong nhiều hệ; có thể **block** khi coordinator/participant lỗi.
- Hiệu năng và availability thường kém hơn transaction cục bộ.
- Vận hành recovery, transaction log và xử lý coordinator failure phức tạp.
- Không giải quyết mọi side effect không đảo ngược như email đã gửi.

Vì vậy, trong microservices hoặc tích hợp với broker/API bên ngoài, **outbox + idempotent consumer + saga/reconciliation** thường thực tế hơn. Nhưng không nên khẳng định 2PC “không bao giờ dùng được”: trong môi trường hỗ trợ đầy đủ và có yêu cầu atomicity phù hợp, nó vẫn là một lựa chọn có chi phí và hợp đồng riêng.

### Kafka transaction có giải quyết dual write DB + Kafka không?

Broker có thể cung cấp transaction hoặc khả năng xử lý “exactly-once” trong **phạm vi riêng của broker/stream-processing**. Điều đó **không tự động** biến một `COMMIT` PostgreSQL và một Kafka transaction thành một commit atomically coordinated. Muốn kết hợp cần kiến trúc, connector hoặc giao thức được chứng minh đáp ứng đúng phạm vi; outbox vẫn là mẫu hữu ích khi DB là nguồn ghi chính.

## 16. Retry, backoff, dead letter và đối soát

Một hệ dual-write đáng tin cậy phải có quy trình xử lý khi consumer/relay liên tục gặp lỗi:

| Tình huống | Xử lý phù hợp |
| --- | --- |
| Broker tạm ngắt hoặc network timeout | Retry hữu hạn mỗi lượt, backoff và jitter, giữ nguyên event ID |
| Broker đã nhận nhưng ACK mất | Cho phép gửi lại; consumer dedupe |
| Payload không hợp schema của consumer | Đưa vào luồng lỗi/poison message, điều tra và sửa schema |
| Một event lỗi mãi | Dead-letter/quarantine theo chính sách; không xóa bằng cách “đánh dấu thành công” |
| Worker chết giữa claim và publish | Lease timeout, claim lại, chấp nhận duplicate nếu cần |
| Consumer ghi DB xong nhưng ACK broker mất | Broker gửi lại, inbox ngăn tác động lặp |
| Event mất/không phát sau nhiều ngày | Reconciliation dựa trên source of truth và outbox/status |
| Bên ngoài đã thực hiện tác động nhưng response mất | Tra cứu trạng thái theo idempotency key/provider ID trước khi retry |

**Dead-letter queue không có nghĩa nghiệp vụ đã hoàn tất.** Nó chỉ chuyển một thông điệp khó xử lý sang nơi có thể theo dõi/khắc phục. Nếu ngừng xử lý một message, hệ thống cần nêu rõ tác động tới tính đầy đủ dữ liệu và cơ chế phát lại sau sửa lỗi.

### Reconciliation là thành phần thiết yếu

Ví dụ có thể so sánh:

- Những order `CONFIRMED` có tương ứng với payment record hợp lệ không?
- Mọi outbox record quá hạn chưa published có đang bị kẹt không?
- Các projection/cache/search index có revision phù hợp với source of truth không?
- Có yêu cầu đã gửi sang payment provider nhưng kết quả DB đang ở `UNKNOWN` không?
- Event nào đã tới broker nhưng consumer chưa xác nhận xử lý?

Nếu phát hiện lệch, có thể **phát lại event với cùng event ID**, cập nhật projection từ snapshot chuẩn hoặc kích hoạt quy trình bù/đối soát. Tránh tạo một side effect mới không có idempotency.

## 17. Observability và các metric quan trọng

Đừng chỉ theo dõi tỷ lệ HTTP 200. Một endpoint có thể trả thành công liên tục trong khi outbox không được gửi, khiến downstream chậm dần nhiều giờ.

| Metric / tín hiệu | Câu hỏi cần trả lời |
| --- | --- |
| `outbox_pending_count` | Có bao nhiêu event chưa publish? |
| `oldest_outbox_age` | Event lâu nhất đang đợi bao lâu từ lúc được ghi/commit? |
| `publish_latency` | Từ ghi outbox đến broker acknowledgment mất bao lâu? |
| `publish_retry_count`, error code | Broker đang lỗi hay worker retry quá mức? |
| `lease_expired_count` | Có worker thường xuyên treo/chết hoặc xử lý quá lâu? |
| `consumer_duplicate_count` | Có bao nhiêu delivery lặp bị inbox loại bỏ? |
| `consumer_lag` | Downstream chậm tới mức nào? |
| `dlq_count` và `dlq_oldest_age` | Có message không thể tự phục hồi? |
| `aggregate_version_gap` | Projection có thiếu/mất thứ tự event? |
| `reconciliation_mismatch` | Hệ thống lệch nhau bao nhiêu trường hợp nghiệp vụ? |
| `commit_unknown_count` | Có bao nhiêu giao dịch client không chắc kết quả? |

Log và trace nên gắn `request_id`, `order_id`, `event_id`, `correlation_id`, consumer name và trạng thái; tránh gắn raw event ID làm **metric label cardinality cao** và tránh ghi payload chứa dữ liệu cá nhân hoặc thông tin thanh toán. Khi khảo sát lỗi, cần xem **đường đi của một event qua nhiều hệ thống**, không chỉ stack trace tại producer.

## 18. Kiểm thử bằng cách gây lỗi đúng khoảng cửa sổ

Các test cần bao phủ **thời điểm crash** chứ không chỉ đường thành công:

| Kịch bản | Kỳ vọng |
| --- | --- |
| Lỗi trước DB commit | Không có order lẫn outbox event đã commit |
| INSERT order thành công, INSERT outbox thất bại | Transaction rollback cả hai |
| DB commit rồi process crash trước worker publish | Outbox vẫn còn; worker khác tiếp tục phát |
| Publish thành công, worker chết trước đánh dấu published | Event có thể phát lại; consumer không tạo tác động lặp |
| Hai worker cùng claim outbox | Không cập nhật claim sai; lease và owner được kiểm tra |
| Event E2 đến trước E1 | Consumer xử lý thứ tự/phiên bản theo hợp đồng |
| Consumer commit thay đổi nhưng ACK broker thất bại | Inbox chặn double processing sau redelivery |
| HTTP create order timeout sau commit | Retry cùng request ID không tạo đơn thứ hai |
| Payment provider trả timeout sau khi thu tiền | Tra cứu/đối soát theo provider idempotency key, không charge lần hai |
| Broker ngừng lâu | Backlog tăng, có alert và sau phục hồi event được phát tiếp |
| Payload sai schema | Event được giữ để xử lý; không đánh dấu hoàn tất giả |
| CDC connector restart và replay | Consumer chấp nhận duplicate và tiến trình tiếp tục |

### Test giao dịch cục bộ bằng hai bảng

1. Mở transaction trên database integration test.
2. Chèn order hợp lệ.
3. Cố ý làm chèn outbox thất bại (ví dụ trùng `event_id`).
4. Bắt lỗi và rollback.
5. Dùng **transaction/kết nối mới** xác nhận order **không** tồn tại.

Không chỉ kiểm tra mock `eventPublisher.publish()` đã được gọi. Kiểm thử đó không xác minh commit nguyên tử.

### Test duplicate theo consumer

1. Phát event `E-777` tới consumer.
2. Consumer chèn inbox marker và thay đổi projection trong cùng transaction, sau đó commit.
3. Giả lập crash trước khi ACK broker.
4. Gửi lại đúng `E-777`.
5. Kiểm tra **một** tác động nghiệp vụ được commit, dù có **hai** lần delivery.

Để tái hiện tranh chấp, dùng `CountDownLatch` hoặc barrier và **hai transaction độc lập**, tránh chỉ `Thread.sleep()` mong tình cờ tạo race. Với hệ phân tán, nên dùng môi trường test với broker/DB cùng loại production hoặc hệ kiểm thử tích hợp phù hợp.

## 19. Sai lầm phổ biến khi xử lý dual write

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| “Đã có `@Transactional` nên DB và broker cùng rollback” | Event có thể xuất hiện trước hoặc sau rollback DB | Xác định resource manager thực sự tham gia transaction |
| Gửi event sau commit trực tiếp rồi coi là đáng tin cậy | Crash giữa commit và publish làm mất event | Outbox được ghi cùng transaction |
| Gửi event trước commit để “chắc chắn không mất” | Consumer thấy event về dữ liệu rollback | Phát theo trạng thái đã commit |
| Đánh dấu published trước khi broker xác nhận | Event có thể bị mất | Ghi trạng thái sau ACK, chấp nhận và xử lý duplicate |
| Nghĩ outbox tự bảo đảm exactly-once | Crash trước mark published gây publish lặp | Event ID ổn định và inbox/idempotent consumer |
| Mỗi lần retry tạo một event ID khác | Consumer không nhận diện bản sao | Giữ `event_id` qua toàn bộ vòng đời event |
| Consumer đọc duplicate rồi vẫn cộng counter | Tác động nghiệp vụ bị nhân đôi | Inbox marker cùng transaction với side effect |
| Consumer gọi payment bên ngoài dù đã có inbox | Payment không được bảo vệ bởi transaction DB | Provider idempotency, outbox, reconciliation |
| Thực thi publish trong transaction DB dài | Giữ lock/connection khi chờ network, vẫn không có atomicity | Commit DB trước, relay publish riêng |
| Tin rằng `ORDER BY created_at` đảm bảo mọi consumer thấy đúng thứ tự | Parallelism và retry vẫn có thể đảo thứ tự | Aggregate version/partitioning và xử lý gap |
| Dùng Redis cache làm nguồn quyết định tồn kho khi trễ đồng bộ | Bán quá số lượng | Kiểm tra và ghi điều kiện tại source of truth |
| Lỗi lâu ngày thì xóa outbox record | Mất dấu vết nghiệp vụ chưa hoàn tất | DLQ/quarantine, alert và replay sau khắc phục |
| Không có retention/cleanup | Outbox/inbox phình to, index và query chậm | Chính sách lưu trữ tương thích retry/replay window |
| Chỉ test HTTP success | Không phát hiện cửa sổ crash và duplicate | Fault-injection ở từng ranh giới commit/ACK |

## 20. Bài tập: đơn hàng, tồn kho và thanh toán

Một ứng dụng Java hiện có:

~~~text
POST /orders
  1. BEGIN PostgreSQL
  2. INSERT order PENDING
  3. Redis SET stock:42 = stock - 1
  4. PaymentProvider.charge(card, 500000)
  5. Kafka publish OrderCreated
  6. COMMIT PostgreSQL
  7. RETURN HTTP 201
~~~

Hãy trả lời:

1. Nếu payment provider đã thu tiền ở bước 4 nhưng PostgreSQL rollback ở bước 6, có thể rollback tiền bằng `connection.rollback()` không?
2. Nếu Kafka nhận event ở bước 5 nhưng PostgreSQL rollback, consumer có thể thấy chuyện gì?
3. Nếu Redis update thành công nhưng PostgreSQL rollback, liệu tồn kho hai bên có nhất quán?
4. Đổi bước Kafka publish xuống sau DB commit có giải quyết hoàn toàn không?
5. Hãy viết lại ranh giới transaction để đảm bảo **order và ý định phát event** commit cùng nhau.
6. Khi Kafka nhận một event hai lần, worker xử lý tồn kho hoặc gửi email cần làm gì?
7. Nếu user retry sau timeout ở bước 7, hệ thống làm thế nào để không tạo order và payment lần hai?

**Hướng giải đề xuất:**

- (1) Không. Transaction JDBC chỉ điều khiển database có tham gia; cần provider idempotency, tra cứu và refund/compensation theo quy trình.
- (2) Consumer có thể xử lý một đơn chưa tồn tại hoặc đã rollback.
- (3) Redis không tự rollback cùng PostgreSQL; phải xác định nguồn tồn kho và cơ chế cập nhật/đối soát.
- (4) Không. Crash ngay sau DB commit nhưng trước publish vẫn làm thiếu event.
- (5) Một transaction DB lưu `orders` và `outbox_events`. Sau commit, relay publish với `event_id` ổn định; có retry và monitoring.
- (6) Dedupe theo `event_id` bằng inbox hoặc xử lý có tính lũy đẳng; email/payment cần cơ chế riêng tránh tác động ngoài DB bị lặp.
- (7) Dùng `request_id`/idempotency key, unique constraint và lưu kết quả. Khi mất phản hồi commit, tra cứu trạng thái theo key trước khi chạy lại.

**Một thiết kế hợp lý hơn** có thể tạo order `PENDING_PAYMENT` và outbox yêu cầu thanh toán trong transaction đầu, rồi để payment workflow có trạng thái riêng xử lý qua API provider với idempotency key. Sau khi thanh toán được xác nhận, tạo event/cập nhật trạng thái trong transaction cục bộ tiếp theo. Việc giữ tồn kho phải dùng cơ chế điều kiện nguyên tử tại nguồn có thẩm quyền; các bước không thể cam kết atomically giữa nhiều hệ phải được bù/đối soát.

## 21. Checklist trước khi đưa dual write vào production

1. **Nguồn sự thật:** hệ nào sở hữu dữ liệu và bất biến nghiệp vụ cho mỗi loại thực thể?
2. **Phạm vi nguyên tử:** các bảng trong transaction cục bộ nào, còn hệ thống nào ở bên ngoài?
3. **Crash points:** đã phân tích lỗi trước/sau commit, publish, acknowledgment và cập nhật trạng thái relay chưa?
4. **Bền vững:** intent/event có được ghi cùng transaction chính thay vì chỉ nằm trong RAM không?
5. **Delivery:** worker/CDC xử lý retry, backoff, lease, poison event và recovery như thế nào?
6. **Idempotency:** có request ID, event ID ổn định, inbox marker và provider key khi cần không?
7. **Ordering:** consumer có thể nhận event đảo thứ tự không, aggregate version có đủ không?
8. **Transaction:** consumer effect và dedupe marker có commit trong cùng DB không?
9. **Consistency:** downstream chấp nhận trễ bao lâu; thao tác nào phải kiểm tra nguồn authoritative?
10. **Compensation:** các side effect không rollback được có quy trình bù/đối soát và trạng thái trung gian không?
11. **Observability:** có alert về outbox lag, DLQ, consumer lag, duplicate và trạng thái chưa rõ không?
12. **Security:** event có lộ dữ liệu nhạy cảm không; quyền truy cập broker/outbox có đúng least privilege không?
13. **Schema evolution:** producer/consumer có tương thích khi event type và payload thay đổi không?
14. **Retention:** inbox/outbox/CDC log được giữ đủ lâu cho retry, replay, điều tra và khôi phục không?
15. **Kiểm thử:** đã gây crash và retry ở đúng các ranh giới quan trọng trên môi trường tích hợp chưa?

**Kết luận:** vấn đề dual write không nằm ở số câu lệnh mà nằm ở **hai điểm commit không cùng một cơ chế nguyên tử**. Chọn thứ tự gọi API hoặc thêm `@Transactional` không đủ giải quyết. Với nguồn ghi chính là database, **transactional outbox** giữ ý định phát sự kiện cùng thay đổi nghiệp vụ; **relay/CDC** truyền đi sau commit; **idempotent consumer, inbox, versioning và reconciliation** xử lý phát lặp, đảo thứ tự và lỗi mạng. Với tác động nhiều hệ thống như thanh toán, **saga và bù/đối soát** giải quyết phần mà một transaction DB không thể rollback. Thiết kế đúng là thiết kế được **cả đường thành công lẫn đường khôi phục sau lỗi**.
