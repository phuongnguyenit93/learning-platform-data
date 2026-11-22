# Nhật ký outbox và xử lý lũy đẳng để phối hợp thay đổi

Một giao dịch Java có thể cập nhật cơ sở dữ liệu thành công nhưng không gửi được sự kiện tới message broker, hoặc gửi sự kiện thành công rồi thất bại khi ghi nhận đã gửi. Nếu chỉ viết `UPDATE` và `publish()` liên tiếp, hệ thống có thể tạo ra **trạng thái DB và thông điệp không khớp nhau**. Đây là bài toán *dual write*: một yêu cầu nghiệp vụ cần thay đổi dữ liệu ở hai hệ thống nhưng mỗi hệ thống có cơ chế commit riêng.

**Transactional outbox** giải quyết phần quan trọng của bài toán bằng cách ghi **thay đổi nghiệp vụ và một bản ghi sự kiện cần gửi** trong *cùng transaction của một cơ sở dữ liệu*. Một worker khác đọc các bản ghi outbox đã commit rồi phát chúng ra hệ thống ngoài. **Xử lý lũy đẳng** (*idempotent processing*) bảo đảm việc xử lý lại cùng một yêu cầu hoặc cùng một sự kiện không nhân đôi tác động nghiệp vụ.

Trong chương **Nền tảng phân tán** của **DATA_PERSISTENCE_FUNDAMENTALS**, bài học này nối transaction, độ bền dữ liệu, cơ chế retry, ranh giới persistence Java và phối hợp đa dịch vụ. Mục tiêu là thiết kế một luồng đáng tin cậy **dù tiến trình chết, kết nối đứt, broker trễ hay message được giao nhiều lần**, đồng thời hiểu chính xác điều outbox *không* cam kết.

## 1. Vì sao gửi sự kiện ngay trong giao dịch là không đủ?

Giả sử dịch vụ đặt hàng thực hiện hai thao tác:

1. Ghi `orders.status = 'CONFIRMED'` vào PostgreSQL.
2. Phát sự kiện `ORDER_CONFIRMED` đến broker để dịch vụ thông báo và kho hàng xử lý.

Nếu thực hiện hai bước độc lập, luôn có một khoảng thời gian hệ thống chỉ hoàn thành một bên:

```text
Phương án A: DB trước
  UPDATE orders -> COMMIT DB -> publish broker
                       |             |
                       +---- crash ---+  => DB đã đổi, sự kiện có thể chưa được gửi

Phương án B: broker trước
  publish broker -> UPDATE orders -> COMMIT DB
         |                |
         +----- crash ----+           => Sự kiện có thể đã tới nơi, DB chưa đổi
```

Giữ transaction DB mở trong lúc gọi broker cũng không làm hai bên **commit nguyên tử**: broker không tự rollback vì PostgreSQL rollback, và ngược lại. Ngoài ra, việc chờ mạng trong transaction làm tăng thời gian giữ connection/khóa.

Các tình huống lỗi khác nhau dẫn đến quyết định phục hồi khác nhau:

| Thời điểm lỗi | Hậu quả có thể xảy ra | Điều không nên làm |
| --- | --- | --- |
| DB rollback, broker đã nhận sự kiện | Consumer thấy một nghiệp vụ chưa thực sự được commit | Không coi publish trước DB là giao thức an toàn |
| DB commit, tiến trình chết trước publish | Sự kiện bị bỏ sót nếu không có nơi lưu ý định phát | Không chỉ dựa vào một lời gọi publish trong request |
| Broker nhận nhưng phản hồi bị mất | Publisher không biết đã gửi thành công hay chưa | Không suy từ timeout rằng broker chắc chắn chưa nhận |
| Broker đã ACK, DB chưa đánh dấu đã gửi | Sau restart có thể phát lại cùng sự kiện | Không giả định mỗi sự kiện chỉ xuất hiện một lần |
| Consumer cập nhật DB rồi chết trước khi ACK broker | Broker có thể giao lại cùng message | Không cập nhật lần hai nếu đó là cùng tác động nghiệp vụ |

**Outbox + idempotency** không phải giao dịch phân tán hai pha (2PC). Chúng cho phép phối hợp **theo thời gian** với giao hàng có thể lặp, đổi lại cần theo dõi trạng thái và hỗ trợ phục hồi.

## 2. Mẫu transactional outbox hoạt động như thế nào?

Luồng tối thiểu gồm hai transaction DB độc lập và một thao tác mạng:

```text
              Request xác nhận đơn
                       |
                       v
       +-----------------------------------+
       | TX1: PostgreSQL                   |
       |   UPDATE orders                   |
       |   INSERT outbox_events            |
       |   COMMIT                          |
       +-----------------------------------+
                       |
                       v
              Outbox row bền vững
                       |
                 Poller / CDC
                       |
          [claim công việc ngắn]
                       |
                 Trả DB connection
                       |
                       v
              Publish tới broker
                       |
                Broker xác nhận
                       |
                       v
          [TX2: đánh dấu SENT ở DB]
                       |
                       v
                Consumer nhận
                       |
              Dedupe và cập nhật DB
                       |
                ACK message
```

Các bất biến quan trọng:

- **Atomicity tại DB nguồn:** thay đổi trạng thái và outbox row cùng commit hoặc cùng rollback. Không thể có một trong hai thay đổi *đã commit* mà thay đổi còn lại không commit trong cùng transaction.
- **Publisher không được giữ TX1:** việc gọi broker diễn ra sau commit, thường trong tiến trình nền, không giữ connection/lock của transaction nghiệp vụ.
- **Sự kiện có định danh ổn định:** mỗi event có `event_id` không thay đổi qua mọi lần publish lại.
- **Được phép gửi trùng:** publisher có thể gửi nhiều lần khi không biết broker đã nhận chưa; consumer phải lũy đẳng.
- **ACK chỉ sau kết quả bền vững:** chỉ đánh dấu `SENT` khi giao thức broker/producer đã xác nhận lưu hoặc chấp nhận thông điệp theo mức bảo đảm đã chọn; không coi việc đặt message vào bộ đệm client là đã gửi.

Trong một thiết kế outbox thông thường, mục tiêu là **at-least-once delivery** nếu các thành phần còn khả năng phục hồi, dữ liệu outbox không bị mất và chính sách retry được vận hành đúng. Nó **không tự tạo exactly-once end-to-end** giữa database, broker và mọi consumer.

## 3. Thiết kế schema: nghiệp vụ, mã yêu cầu và outbox

Ví dụ xuyên suốt dùng **PostgreSQL** và Java 17+. Một yêu cầu xác nhận đơn có `request_id` là UUID do tầng gọi tạo **một lần và giữ nguyên khi retry**; ở ví dụ này mỗi request tạo đúng một event và dùng cùng UUID làm `event_id`.

```sql
CREATE TABLE orders (
    order_id     BIGINT PRIMARY KEY,
    status       VARCHAR(20) NOT NULL
                 CHECK (status IN ('PENDING', 'CONFIRMED', 'CANCELLED')),
    version      BIGINT NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Chống thực thi lại cùng một request nghiệp vụ.
CREATE TABLE command_receipts (
    request_id   UUID PRIMARY KEY,
    order_id     BIGINT NOT NULL REFERENCES orders(order_id),
    action       VARCHAR(40) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Hàng chờ sự kiện nằm trong cùng database giao dịch với orders.
CREATE TABLE outbox_events (
    event_id        UUID PRIMARY KEY,
    aggregate_id    BIGINT NOT NULL,
    aggregate_ver   BIGINT NOT NULL,
    event_type      VARCHAR(80) NOT NULL,
    payload         JSONB NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING', 'IN_PROGRESS', 'SENT', 'FAILED')),
    attempts        INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claim_token     UUID,
    lease_until     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at         TIMESTAMPTZ
);

CREATE INDEX outbox_pending_idx
    ON outbox_events(status, next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'IN_PROGRESS');
```

Một outbox record cần đủ dữ liệu để consumer hiểu sự kiện khi chạy lại sau nhiều giờ/ngày: `event_id`, loại sự kiện, mã aggregate, phiên bản và payload theo **hợp đồng schema**. Có thể thêm `schema_version`, correlation/causation ID, tenant ID hoặc metadata trace khi thiết kế yêu cầu.

Các lưu ý thiết kế:

1. **Không dùng outbox như bảng lưu duy nhất của dữ liệu nghiệp vụ.** `orders` là trạng thái nghiệp vụ; outbox ghi **ý định giao thông điệp** đã được commit cùng trạng thái.
2. **Không nhầm outbox với WAL của engine.** WAL phục vụ phục hồi/nhân bản nội bộ DB; outbox là bản ghi nghiệp vụ có schema, nơi consumer nhận sự kiện hoặc lệnh tích hợp. Có thể dùng **CDC** để đọc outbox từ log DB mà không cần polling.
3. **Không lưu bí mật không cần thiết trong payload.** Sự kiện có thể được phát, log hoặc giữ lại lâu; áp dụng quyền truy cập, che/mã hóa dữ liệu nhạy cảm theo chính sách.
4. **Có chiến lược dọn dữ liệu.** Outbox tăng kích thước theo tải; sau khi xác nhận gửi và hết thời hạn cần kiểm toán, có thể archive/partition/delete an toàn. Không xóa bản ghi còn chờ hoặc khi chưa biết broker đã nhận.

## 4. Ghi thay đổi và sự kiện trong một transaction JDBC

Service xác nhận đơn cần đảm bảo cùng lúc: (a) đơn còn ở trạng thái `PENDING`, (b) chỉ request hợp lệ đầu tiên được thực thi, (c) tạo outbox nếu cập nhật thành công.

SQL của transaction về mặt khái niệm:

```sql
BEGIN;

INSERT INTO command_receipts(request_id, order_id, action)
VALUES (:request_id, :order_id, 'CONFIRM_ORDER')
ON CONFLICT (request_id) DO NOTHING;
-- Nếu insert được 0 hàng, đối chiếu receipt cũ và không thực thi lặp.

UPDATE orders
SET status = 'CONFIRMED',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE order_id = :order_id AND status = 'PENDING'
RETURNING version;
-- Nếu không có hàng, rollback và báo từ chối nghiệp vụ.

INSERT INTO outbox_events(
    event_id, aggregate_id, aggregate_ver, event_type, payload)
VALUES (:request_id, :order_id, :version, 'ORDER_CONFIRMED', :payload);

COMMIT;
```

Đây là **pseudocode SQL** dùng placeholder dạng `:name` để minh họa. Với JDBC thuần, phải dùng `?` hoặc cơ chế bind của thư viện. Không chạy nguyên văn đoạn `:request_id` bằng PostgreSQL SQL console nếu công cụ không hỗ trợ named parameters.

### 4.1. Ví dụ Java/JDBC

Đoạn code dưới đây minh họa một service tự sở hữu transaction qua `DataSource`. Đối với mô hình Spring đang có transaction manager ở tầng gọi, cần chuyển trách nhiệm commit/rollback ra transaction manager chứ không lồng transaction thủ công.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;

public final class ConfirmOrderService {
    public enum Result { APPLIED, ALREADY_APPLIED, NOT_ALLOWED }

    private final DataSource dataSource;

    public ConfirmOrderService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Result confirm(long orderId, UUID requestId) throws SQLException {
        if (requestId == null) {
            throw new IllegalArgumentException("requestId bắt buộc");
        }

        try (Connection c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                if (!claimRequest(c, orderId, requestId)) {
                    verifySameRequest(c, orderId, requestId);
                    c.rollback(); // không có thay đổi mới
                    return Result.ALREADY_APPLIED;
                }

                Long newVersion = confirmPendingOrder(c, orderId);
                if (newVersion == null) {
                    c.rollback();
                    return Result.NOT_ALLOWED;
                }

                insertOutbox(c, orderId, requestId, newVersion);
                c.commit();
                return Result.APPLIED;
            } catch (SQLException | RuntimeException failure) {
                try {
                    c.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        }
    }

    private static boolean claimRequest(
            Connection c, long orderId, UUID requestId) throws SQLException {
        String sql = """
            INSERT INTO command_receipts(request_id, order_id, action)
            VALUES (?, ?, 'CONFIRM_ORDER')
            ON CONFLICT (request_id) DO NOTHING
            """;
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setObject(1, requestId);
            ps.setLong(2, orderId);
            return ps.executeUpdate() == 1;
        }
    }

    private static void verifySameRequest(
            Connection c, long orderId, UUID requestId) throws SQLException {
        String sql = """
            SELECT order_id, action
            FROM command_receipts WHERE request_id = ?
            """;
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setObject(1, requestId);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()
                        || rs.getLong("order_id") != orderId
                        || !"CONFIRM_ORDER".equals(rs.getString("action"))) {
                    throw new IllegalArgumentException(
                            "requestId đã dùng với tham số khác");
                }
            }
        }
    }

    private static Long confirmPendingOrder(
            Connection c, long orderId) throws SQLException {
        String sql = """
            UPDATE orders
            SET status = 'CONFIRMED',
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ? AND status = 'PENDING'
            RETURNING version
            """;
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, orderId);
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next() ? rs.getLong(1) : null;
            }
        }
    }

    private static void insertOutbox(Connection c, long orderId,
                                     UUID requestId, long version)
            throws SQLException {
        String sql = """
            INSERT INTO outbox_events(
                event_id, aggregate_id, aggregate_ver, event_type, payload)
            VALUES (?, ?, ?, 'ORDER_CONFIRMED',
                    jsonb_build_object(
                        'orderId', ?::bigint,
                        'status', 'CONFIRMED',
                        'version', ?::bigint))
            """;
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setObject(1, requestId);
            ps.setLong(2, orderId);
            ps.setLong(3, version);
            ps.setLong(4, orderId);
            ps.setLong(5, version);
            ps.executeUpdate();
        }
    }
}
```

**Ý nghĩa của các bước:**

- `requestId` do client/application tạo **một lần** cho nghiệp vụ; không tạo UUID mới trong vòng retry. Nếu hai request cùng ID chạy song song, ràng buộc unique trên `command_receipts.request_id` giúp phân xử. Sau khi một request đã commit, lần gọi sau với cùng ID không cập nhật đơn lần nữa.
- Nếu câu `UPDATE ... WHERE status='PENDING'` không đổi được hàng nào, transaction rollback, bao gồm cả receipt vừa insert; không ghi sự kiện giả. Những lỗi nghiệp vụ như “đơn đã hủy” không phải lỗi nên retry mù.
- Sau `COMMIT` thành công, ứng dụng có thể chắc chắn trạng thái đơn và outbox đã commit **theo cam kết durability của DB được cấu hình**. Nó chưa có nghĩa broker đã nhận message.
- Trong trường hợp `commit()` ném exception vì mất kết nối, **không được suy ra transaction chắc chắn rollback**. Việc gọi lại với *cùng* request ID có thể giúp xác định transaction trước đã commit; cần đối soát trên nguồn dữ liệu nhất quán, không tin ngay read replica có lag.
- Dùng `event_id = request_id` chỉ phù hợp vì ví dụ **mỗi command tạo đúng một event**. Nếu một command có nhiều event, mỗi event cần ID riêng, xác định ổn định hoặc được lưu cùng receipt trong transaction.

Để rút gọn, ví dụ chưa có phân quyền, tenant isolation, validation của API, timeout, backoff, exception mapping, hoặc logic khác ngoài DB. Kết nối pool phải được cấu hình để trả lại trạng thái `autoCommit` sạch sau mỗi lần mượn. Ngoài ra, một lệnh `confirm` ngoài cùng cần kiểm soát deadline; mã request ID bảo vệ chống thực thi lại nhưng không bảo đảm toàn bộ tích hợp ngoài DB không lặp.

## 5. Publisher: claim nhanh, phát ngoài transaction, ACK sau broker

Một worker có thể poll `outbox_events`. Nếu nhiều worker cùng chạy, **không được** để hai worker cùng chọn một hàng chưa xử lý mà không có claim an toàn. PostgreSQL hỗ trợ `FOR UPDATE SKIP LOCKED` để các worker tránh đợi những hàng đã khóa; câu lệnh claim nên nằm trong transaction **ngắn**.

### 5.1. Claim có thời hạn (lease) và token

```sql
WITH candidate AS (
    SELECT event_id
    FROM outbox_events
    WHERE (status = 'PENDING'
           AND next_attempt_at <= CURRENT_TIMESTAMP)
       OR (status = 'IN_PROGRESS'
           AND lease_until < CURRENT_TIMESTAMP)
    ORDER BY created_at, event_id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE outbox_events AS o
SET status      = 'IN_PROGRESS',
    attempts    = attempts + 1,
    claim_token = :new_claim_token,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '30 seconds'
FROM candidate
WHERE o.event_id = candidate.event_id
RETURNING o.event_id, o.event_type, o.payload, o.claim_token;
```

Ý nghĩa:

- Worker claim một hàng và commit **trước khi gửi**.
- Nếu worker chết sau claim, hàng `IN_PROGRESS` được phép claim lại sau khi `lease_until` hết hạn.
- Mỗi lần claim dùng một **token khác nhau**, để worker cũ không được đánh dấu `SENT` sau khi hàng đã chuyển quyền sở hữu cho worker khác.
- `SKIP LOCKED` phù hợp queue nhiều worker, nhưng **không có nghĩa các sự kiện cùng aggregate luôn được phát đúng thứ tự**. Nếu tính thứ tự quan trọng, cần thiết kế thêm.

Khi broker đã ACK theo mức bền vững yêu cầu, worker đánh dấu:

```sql
UPDATE outbox_events
SET status = 'SENT',
    sent_at = CURRENT_TIMESTAMP,
    claim_token = NULL,
    lease_until = NULL
WHERE event_id = :event_id
  AND status = 'IN_PROGRESS'
  AND claim_token = :claim_token;
```

Nếu câu `UPDATE` trả **0 hàng**, worker cũ không còn sở hữu record hoặc record đã thay trạng thái; không được cưỡng ép cập nhật bằng `WHERE event_id = ?` đơn thuần. Nếu broker đã nhận nhưng DB lỗi khi đánh dấu `SENT`, sự kiện sẽ được gửi lại: đây là lý do consumer phải idempotent.

### 5.2. Ví dụ Java/JDBC về worker

Ví dụ dưới đây cố ý tách đoạn dùng connection khỏi đoạn gọi broker. Interface `BrokerPublisher` chỉ có nghĩa “trả về khi broker đã xác nhận theo chính sách được cấu hình”; một API publish fire-and-forget không đáp ứng hợp đồng này.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import java.util.UUID;

public final class OutboxPublisher {
    public interface BrokerPublisher {
        void publish(UUID eventId, String eventType, String payload)
                throws Exception;
    }

    public record ClaimedEvent(
            UUID eventId, String eventType, String payload,
            UUID claimToken) {}

    private final DataSource dataSource;
    private final BrokerPublisher broker;

    public OutboxPublisher(DataSource dataSource, BrokerPublisher broker) {
        this.dataSource = dataSource;
        this.broker = broker;
    }

    public void runOne() throws Exception {
        Optional<ClaimedEvent> next = claimOne();
        if (next.isEmpty()) {
            return;
        }
        ClaimedEvent event = next.get();

        // Không giữ Connection/DB transaction trong lúc gọi broker.
        // Truyền cùng eventId ở mọi lần publish lại để consumer dedupe.
        broker.publish(event.eventId(), event.eventType(), event.payload());

        // Broker đã ACK: mở connection mới ghi trạng thái.
        markSent(event.eventId(), event.claimToken());
    }

    private Optional<ClaimedEvent> claimOne() throws SQLException {
        UUID token = UUID.randomUUID();
        String sql = """
            WITH candidate AS (
                SELECT event_id FROM outbox_events
                WHERE (status = 'PENDING'
                       AND next_attempt_at <= CURRENT_TIMESTAMP)
                   OR (status = 'IN_PROGRESS'
                       AND lease_until < CURRENT_TIMESTAMP)
                ORDER BY created_at, event_id
                FOR UPDATE SKIP LOCKED LIMIT 1
            )
            UPDATE outbox_events o
            SET status='IN_PROGRESS',
                attempts=attempts+1,
                claim_token=?,
                lease_until=CURRENT_TIMESTAMP + INTERVAL '30 seconds'
            FROM candidate
            WHERE o.event_id = candidate.event_id
            RETURNING o.event_id, o.event_type, o.payload::text
            """;

        try (Connection c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                Optional<ClaimedEvent> claimed;
                try (PreparedStatement ps = c.prepareStatement(sql)) {
                    ps.setObject(1, token);
                    try (ResultSet rs = ps.executeQuery()) {
                        claimed = rs.next()
                                ? Optional.of(new ClaimedEvent(
                                    rs.getObject(1, UUID.class),
                                    rs.getString(2),
                                    rs.getString(3),
                                    token))
                                : Optional.empty();
                    }
                }
                c.commit();
                return claimed;
            } catch (SQLException | RuntimeException failure) {
                try {
                    c.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        }
    }

    private void markSent(UUID eventId, UUID claimToken)
            throws SQLException {
        String sql = """
            UPDATE outbox_events
            SET status='SENT',
                sent_at=CURRENT_TIMESTAMP,
                claim_token=NULL,
                lease_until=NULL
            WHERE event_id=? AND status='IN_PROGRESS'
              AND claim_token=?
            """;
        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setObject(1, eventId);
            ps.setObject(2, claimToken);
            if (ps.executeUpdate() != 1) {
                throw new SQLException(
                        "Đã mất quyền claim hoặc event thay trạng thái");
            }
        }
    }
}
```

**Đây là bộ khung để học**, chưa phải một worker production hoàn chỉnh:

- Nếu publish lỗi hoặc timeout, `runOne()` ném exception và hàng giữ `IN_PROGRESS` cho đến khi lease hết hạn. Hệ thống thật nên ghi thông tin lỗi, có **backoff**, giới hạn `attempts`, chuyển sang `FAILED` hoặc dead-letter để xử lý *poison event*. Nếu chỉ đợi lease cố định, event có thể bị retry quá thường xuyên.
- Nếu publish mất **hơn 30 giây**, lease có thể hết khi worker vẫn đang gửi. Worker khác có thể claim và gửi cùng event. Cần điều chỉnh lease theo timeout tối đa, dùng gia hạn lease có điều kiện, hoặc chấp nhận bản gửi trùng và bảo vệ bằng idempotency. Không giữ transaction DB để “chờ hết publish”.
- Nếu crash giữa lúc broker nhận và lúc `markSent()`, bản ghi được phát lại là **hành vi dự kiến**; không sửa bằng cách đánh dấu `SENT` trước khi broker ACK.
- `claimOne()` và `markSent()` minh họa transaction boundary. Nếu mất kết nối ngay lúc commit claim hoặc mark `SENT`, kết quả có thể không rõ; dispatcher phải cho phép hồi phục qua trạng thái/lease, không suy diễn “chưa ghi”.
- Nếu muốn đảm bảo throughput, poll theo batch có giới hạn nhưng phải kiểm soát memory, lease, partition và backpressure; không giữ hàng nghìn connection khi đang chờ broker.

## 6. Consumer lũy đẳng: một event có thể được nhận nhiều lần

Mục tiêu của producer outbox là **không mất ý định phát message đã commit**, nhưng producer không thể luôn phân biệt “message chưa được broker nhận” và “broker đã nhận, phản hồi bị mất”. Vì vậy **bên nhận phải coi việc giao lại message là bình thường**.

Định nghĩa lũy đẳng theo góc nhìn nghiệp vụ: xử lý cùng một `event_id` nhiều lần phải có **tác động cuối tương đương xử lý một lần**. Đừng nhầm điều này với việc “HTTP handler không ném lỗi” hay “SQL chạy được nhiều lần”.

Ví dụ sai:

```sql
-- Event CREDIT_100 bị giao hai lần -> cộng hai lần.
UPDATE wallets
SET balance = balance + 100
WHERE wallet_id = 42;
```

Một consumer có thể dùng **inbox/deduplication table** với unique key trên cặp `(consumer_name, event_id)`, rồi đặt cả *ghi nhận đã xử lý* và *thay đổi DB local* trong **cùng transaction**:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);

-- Read model lưu trạng thái mới nhất theo phiên bản của một đơn.
CREATE TABLE order_status_view (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL
);
```

Giao thức xử lý:

```text
Nhận event E (ID ổn định)
    |
    v
BEGIN transaction trên DB của consumer
    |
    +-- INSERT processed_events(consumer, event_id)
    |   ON CONFLICT DO NOTHING
    |
    +-- Nếu đã tồn tại: không làm lại thay đổi nghiệp vụ
    |
    +-- Nếu lần đầu: áp dụng thay đổi trên DB local
    |
COMMIT
    |
    v
ACK broker
```

Nếu consumer chết **sau commit DB nhưng trước ACK broker**, broker giao lại E; lần sau thấy unique key đã tồn tại và không áp dụng tác động lần hai. Nếu consumer chết **trước commit DB**, cả marker lẫn cập nhật bị rollback và lần giao sau được xử lý lại. Đây là bất biến quan trọng: **marker và hiệu ứng local phải dùng một transaction**.

### 6.1. SQL cập nhật projection có phiên bản

Với event `ORDER_CONFIRMED` mang **trạng thái đầy đủ** và `version` của aggregate, có thể kết hợp bảng dedupe với câu UPSERT kiểm tra version:

```sql
-- Thực hiện bên trong một transaction, sau khi đã chèn
-- processed_events và biết đây là event mới.
INSERT INTO order_status_view(order_id, status, version)
VALUES (:order_id, 'CONFIRMED', :version)
ON CONFLICT (order_id) DO UPDATE
SET status = EXCLUDED.status,
    version = EXCLUDED.version
WHERE order_status_view.version < EXCLUDED.version;
```

Giả sử đã nhận event version `7` rồi mới nhận version `6`: bảng chỉ giữ version `7`. Điều này phù hợp với **sự kiện chứa trạng thái cuối có thể thay thế trạng thái trước**. Nếu event là phép cộng/trừ, mỗi delta phải được áp dụng theo thứ tự/giao thức phù hợp; **không được** tùy tiện bỏ delta cũ chỉ vì version thấp hơn.

Ví dụ Java/JDBC áp dụng một event projection trong transaction local, với `consumerName` cố định để định danh consumer:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;

public final class IdempotentProjectionHandler {
    private final DataSource dataSource;

    public IdempotentProjectionHandler(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void onOrderConfirmed(
            UUID eventId, long orderId, long version) throws SQLException {
        try (Connection c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                String marker = """
                    INSERT INTO processed_events(consumer_name, event_id)
                    VALUES ('order-status-view', ?)
                    ON CONFLICT DO NOTHING
                    """;
                int inserted;
                try (PreparedStatement ps = c.prepareStatement(marker)) {
                    ps.setObject(1, eventId);
                    inserted = ps.executeUpdate();
                }

                if (inserted == 1) {
                    String sql = """
                        INSERT INTO order_status_view(order_id, status, version)
                        VALUES (?, 'CONFIRMED', ?)
                        ON CONFLICT (order_id) DO UPDATE
                        SET status=EXCLUDED.status, version=EXCLUDED.version
                        WHERE order_status_view.version < EXCLUDED.version
                        """;
                    try (PreparedStatement ps = c.prepareStatement(sql)) {
                        ps.setLong(1, orderId);
                        ps.setLong(2, version);
                        ps.executeUpdate();
                    }
                }
                c.commit(); // Chỉ ACK broker SAU khi commit thành công.
            } catch (SQLException | RuntimeException failure) {
                try {
                    c.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        }
    }
}
```

Đoạn code giả định adapter nhận message đã **xác thực nguồn**, kiểm tra payload/schema, chuyển `event_id`, `order_id`, `version` sang kiểu phù hợp rồi gọi handler. Broker adapter chỉ ACK khi `onOrderConfirmed` kết thúc thành công; nếu lỗi SQL hoặc commit chưa rõ thì có thể không ACK và cho giao lại. Tên consumer phải ổn định: nếu đổi tên mà không di chuyển marker, các event cũ có thể được xử lý lại.

Nếu consumer thực hiện **tác dụng ngoài DB** như gửi SMS/thu tiền, marker trong DB **không tạo atomicity** với hệ thống ấy. Có thể cần một outbox riêng bên consumer, mã idempotency được cổng bên ngoài hỗ trợ, hoặc workflow có đối soát và bù trừ.

## 7. Phân biệt ba kiểu lũy đẳng

| Phạm vi | Khóa nhận diện | Đảm bảo được điều gì? | Cạm bẫy |
| --- | --- | --- | --- |
| **Request idempotency** | `request_id` cho command | Client retry không tạo lần thay đổi nghiệp vụ thứ hai nếu cùng yêu cầu | Phải kiểm tra cùng key có cùng tham số; xử lý commit-unknown |
| **Publisher deduplication** | `event_id`/producer sequence theo khả năng broker | Có thể hạn chế message bị lưu trùng trong một phạm vi cấu hình | Không chứng minh consumer chưa/chắc chắn đã xử lý |
| **Consumer idempotency** | `(consumer_name, event_id)` hoặc khóa nghiệp vụ | Message giao lặp không áp dụng lại cùng hiệu ứng local | Marker và hiệu ứng phải cùng transaction; không bảo vệ side effect ngoài DB |

Ba tầng này **bổ sung cho nhau**, không thay thế nhau. Một broker có producer idempotence vẫn có thể giao cùng record lại cho consumer sau khi consumer crash; một consumer lũy đẳng không cứu được việc **publisher quên phát một event** chưa bao giờ được ghi bền vững.

Với nghiệp vụ tài chính, một operation ID duy nhất thường cần lan truyền qua command, ledger entry, outbox và downstream idempotency key. Không dùng cùng chuỗi ID cho các loại sự kiện khác nhau nếu không có namespace/type phù hợp.

## 8. Thứ tự sự kiện và ranh giới transaction

Outbox bảo đảm **các row được ghi nguyên tử cùng transaction nguồn**, không tự đảm bảo thứ tự message đến consumer khi có nhiều publisher, nhiều partition hoặc retry. Ví dụ:

```text
Đơn 42:
  event E1: version 3, status CONFIRMED
  event E2: version 4, status CANCELLED

Worker A claim E1 rồi publish chậm.
Worker B claim E2 và publish ngay.
Consumer có thể thấy E2 trước E1.
```

Nếu consumer xây read model từ **snapshot trạng thái đầy đủ**, điều kiện version lớn hơn (như `order_status_view`) có thể bảo vệ trước event cũ đến trễ. Nếu consumer áp dụng **delta không giao hoán**, mất thứ tự có thể làm sai dữ liệu; cần phân vùng/serialize xử lý theo aggregate key, sequence/expectedVersion và cơ chế giữ sự kiện chờ khi có gap.

Một số chiến lược:

- Đính kèm `aggregate_id` và `aggregate_ver` vào event, dùng khóa partition ở broker dựa trên aggregate.
- Với cùng aggregate, chỉ cho một publisher/worker phát theo thứ tự version hoặc bảo đảm giao thức đọc outbox giữ thứ tự phù hợp. `ORDER BY created_at` một mình **không đủ** khi nhiều worker claim và publish song song.
- Trên consumer, chỉ áp dụng event khi hợp lệ theo version/chuỗi trạng thái, và lưu checkpoint phù hợp.
- Thiết kế phát lại (*replay*) an toàn: message cũ không được đảo ngược trạng thái mới hoặc nhân đôi số tiền.

**Cross-service transaction không còn là một transaction JDBC.** Mỗi dịch vụ sở hữu DB của mình; outbox truyền ý định đã commit, không tạo rollback nguyên tử xuyên các DB. Các quy trình dài có thể dùng saga/state machine, command có idempotency và thao tác bù trừ. Bù trừ không giống rollback: hoàn tiền là một nghiệp vụ mới có thể phải được kiểm toán.

## 9. Phục hồi theo tình huống lỗi

| Sự cố | Trạng thái có thể tồn tại | Chiến lược an toàn |
| --- | --- | --- |
| Lỗi trước khi transaction nguồn commit | `orders` và outbox đều chưa commit | Rollback; chỉ retry khi phân loại lỗi và business invariant cho phép |
| Nguồn DB commit rồi ứng dụng chết | Có row outbox `PENDING` | Worker tiếp tục xử lý sau restart |
| Worker claim rồi chết | Row `IN_PROGRESS`, lease hữu hạn | Claim lại sau khi lease hết; phát trùng vẫn phải được xử lý |
| Broker đã nhận nhưng worker không nhận ACK | Không biết publish đã thành công chưa | Phát lại cùng `event_id`; consumer dedupe |
| Broker ACK, worker chết trước khi đánh dấu `SENT` | Row chưa đánh dấu đã gửi | Worker khác gửi lại; không bỏ bản ghi |
| Worker cũ hoàn tất sau khi lease bị worker mới claim | Cả hai có thể đã publish | Token ngăn worker cũ ghi đè claim; consumer idempotent |
| Consumer commit DB rồi mất kết nối trước broker ACK | Broker sẽ giao lại | Marker dedupe ngăn hiệu ứng local lặp |
| Poison event luôn lỗi | Row bị retry lặp lại | Bounded retry, backoff, trạng thái `FAILED`/dead-letter, alert và sửa dữ liệu |
| Đọc replica chậm khi đối soát request | Không thấy receipt vừa commit | Đối soát trên nguồn đủ nhất quán; không kết luận thất bại từ replica lag |

Cần làm rõ **mốc chấp nhận**: việc broker ACK có thể phụ thuộc cách cấu hình producer, replication và durability. Nếu broker chỉ chấp nhận vào bộ đệm nhưng mất message khi restart, outbox đã bị đánh dấu `SENT` sẽ không tự động phát lại. Nên cấu hình producer/broker theo mức bền vững mong muốn và có khả năng giám sát/môi trường kiểm thử failover.

## 10. Thiết kế vận hành: không để outbox thành "bãi chứa"

Một triển khai đáng tin cậy cần tối thiểu:

1. **Quan sát tồn đọng:** số row `PENDING`, `IN_PROGRESS` quá hạn, `FAILED`, tuổi sự kiện chưa gửi lâu nhất, khoảng cách từ commit DB đến broker ACK (end-to-end lag), tỷ lệ retry.
2. **Alert và xử lý thủ công:** event không xử lý được phải có nguyên nhân, mức ưu tiên, quy trình sửa dữ liệu/replay và audit; không xóa hoặc bỏ qua âm thầm.
3. **Backpressure và giới hạn worker:** giới hạn số message đồng thời, connection pool, timeout broker, hạn mức retry và kích thước batch.
4. **Retention và dọn lịch sử:** partition hoặc archive các row `SENT` đã quá thời hạn cần kiểm toán; loại bỏ các record đã xử lý phải không làm mất khả năng đối soát cần thiết.
5. **Chuyển đổi schema event:** hợp đồng event có version, consumer đọc được phiên bản tương thích; không sửa payload của event đã phát mà không có chiến lược di trú.
6. **Quyền truy cập:** publisher chỉ đọc/ghi trường outbox cần thiết; consumer có quyền tối thiểu; không lộ thông tin nhạy cảm trong payload/log/trace.
7. **Kiểm thử crash/failover:** cố ý dừng tiến trình sau DB commit, sau publish, trước khi ACK/mark SENT, giữa consumer transaction, và khi lease hết hạn; xác minh cuối cùng không mất ý định phát và không nhân đôi tác động.

Tránh giả định “đã có outbox nên không cần backup”. Nếu mất toàn bộ DB trước khi worker phát event, outbox chưa publish có thể mất cùng dữ liệu nguồn tùy mức durability/backup. Cần cấu hình WAL/replication, backup/restore và RPO/RTO phù hợp. Nếu restore DB từ thời điểm cũ, phải đối soát những sự kiện đã phát nhưng outbox đã quay về trạng thái trước đó.

Một câu hỏi hiệu năng quan trọng là **dọn row `SENT` có gây bloat/lock và làm chậm poll không**. Tần suất cleanup, chỉ mục cho row pending, thời gian giữ transaction và vacuum cần được đo thực tế trên PostgreSQL hoặc engine đang dùng.

## 11. Bài tập thực hành

### Bài tập 1: xác định cửa sổ lỗi

Code thực hiện `updateOrder(); commit(); broker.publish();`. Tiến trình chết giữa `commit()` và `publish()`. Vì sao sự kiện có thể bị mất?

**Đáp án:** không có bản ghi bền vững nào lưu “cần phát sự kiện” sau DB commit. Đưa `INSERT outbox_events` vào transaction với `UPDATE orders`, để worker phát sau.

### Bài tập 2: broker nhận trùng

Publisher đã gửi E1 và broker ACK, nhưng ứng dụng chết trước khi cập nhật outbox thành `SENT`. E1 được gửi thêm lần nữa khi restart. Có vi phạm mô hình outbox không?

**Đáp án:** không; outbox thông thường có delivery **at least once**, vì thế giao trùng được dự kiến. Consumer dùng marker `(consumer_name, event_id)` unique và ghi marker cùng thay đổi local trong một transaction.

### Bài tập 3: gửi SMS trong transaction consumer

Consumer insert `processed_events`, gửi SMS qua HTTP, rồi commit. HTTP thành công nhưng commit thất bại. Lần xử lý lại gửi SMS lần hai. Inbox marker đã đủ chưa?

**Đáp án:** chưa. SMS không thuộc transaction DB; phải đưa ý định gửi SMS vào một outbox local, dùng request ID idempotent ở nhà cung cấp nếu hỗ trợ, hoặc thiết kế đối soát/bù trừ. Không giữ DB transaction khi chờ HTTP.

### Bài tập 4: event đến sai thứ tự

Read model nhận version 9 rồi mới nhận version 8 của cùng đơn. Event chứa **toàn bộ trạng thái cuối**, không phải delta. Có nên áp dụng version 8?

**Đáp án:** không. Dùng điều kiện `incoming_version > stored_version` để chỉ ghi phiên bản mới hơn. Nếu event chỉ là phép cộng/trừ (delta) thì phải áp dụng chính sách thứ tự đầy đủ, không được tùy tiện bỏ delta.

### Bài tập 5: một request bị gửi lại

Client xác nhận đơn với `request_id=R1`. Server đã commit nhưng response bị mất. Client gửi lại R1 với cùng order ID. Nếu server tạo event UUID mới mỗi lần, chuyện gì có thể xảy ra?

**Đáp án:** có thể tạo sự kiện/tác động lặp. Service phải tra receipt theo cùng R1 và trả kết quả đã thực hiện (hoặc đối soát nếu trạng thái commit chưa rõ), không lập một thay đổi mới. Nếu R1 được dùng với order ID khác, phải báo conflict thay vì mặc nhiên coi giống nhau.

### Checklist thiết kế outbox và idempotency

- Thay đổi nghiệp vụ và insert outbox có **cùng transaction và cùng DB nguồn** không?
- Có `event_id` ổn định, request ID cho retry và kiểm tra key trùng nhưng tham số khác không?
- Publisher chỉ gửi **sau commit**, chờ broker ACK bền vững rồi mới đánh dấu SENT không?
- Claim có lease/token, giới hạn số worker, backoff và xử lý sự kiện poison không?
- Consumer ghi marker dedupe và tác động **local DB** trong cùng transaction; ACK broker sau commit chưa?
- Có xử lý các tác động **ngoài DB** (email/SMS/payment) bằng quy trình riêng/idempotency không?
- Có chính sách xử lý thứ tự version, event đến trễ, redelivery và replay không?
- Đã đo outbox lag/failed count, thử crash theo từng mốc, backup/restore và bảo vệ payload nhạy cảm chưa?

**Kết luận:** Transactional outbox làm cho **thay đổi nghiệp vụ và ý định phát sự kiện** trở thành một đơn vị commit bền vững trong database nguồn. Worker tách việc gửi broker khỏi transaction nghiệp vụ; consumer lũy đẳng khiến giao lại cùng event không gây tác động local lần thứ hai. Phối hợp đáng tin cậy đến từ việc thiết kế **định danh ổn định, transaction boundary, ACK đúng mốc, retry hữu hạn, deduplication, thứ tự sự kiện và khôi phục sau lỗi** — không phải từ giả định message chỉ được gửi đúng một lần.
