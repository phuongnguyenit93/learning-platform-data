# Transactional outbox để phối hợp cập nhật dữ liệu và phát thông điệp

> **Chương:** Độ tin cậy  
> **Học phần:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic và Artemis trong giao tiếp bất đồng bộ với queue/topic/routing, JMS, acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành broker đáng tin cậy.  
> **Phạm vi:** Giải quyết bài toán **ghi database và phát thông điệp từ cùng một thay đổi nghiệp vụ**. Ví dụ dùng **PostgreSQL, Java/JDBC, Jakarta JMS và ActiveMQ Artemis**; cơ chế outbox không phụ thuộc riêng vào broker. Không có `SPECIAL_NOTE` bổ sung.

## 1. Bài toán: cập nhật DB thành công nhưng không có message

Giả sử API **`POST /orders`** phải tạo đơn hàng trong PostgreSQL và phát sự kiện `ShippingRequested` lên queue `shipping.commands` của ActiveMQ Artemis. Shipping worker chỉ bắt đầu xử lý khi nhận message.

Một triển khai ngây thơ dùng hai hệ thống độc lập:

~~~java
orderRepository.insert(order);            // PostgreSQL COMMIT
jmsProducer.send(shippingQueue, message); // JMS SEND
~~~

Dòng đầu thành công, nhưng JVM có thể chết trước dòng hai. Đơn hàng đã tồn tại nhưng shipping worker không biết có việc. Đảo thứ tự cũng không an toàn:

~~~java
jmsProducer.send(shippingQueue, message); // Broker chấp nhận
orderRepository.insert(order);            // DB có thể rollback
~~~

Worker có thể nhận `ShippingRequested` cho đơn hàng chưa bao giờ được tạo thành công. Ngay cả khi hai thao tác nằm trong cùng phương thức Java hoặc chung annotation `@Transactional`, **JDBC transaction và JMS transaction không tự trở thành một giao dịch nguyên tử**.

Transactional outbox thay đổi đường đi:

1. Trong **một PostgreSQL transaction**, ghi dữ liệu nghiệp vụ **và** một bản ghi outbox mô tả message cần phát.
2. Commit transaction đó: **cùng tồn tại hoặc cùng rollback**.
3. Một tiến trình **relay** độc lập đọc bản ghi outbox đã commit và publish vào broker.
4. Chỉ sau khi có kết quả publish/commit phù hợp, relay đánh dấu đã phát. Nếu kết quả không chắc chắn, relay có thể thử lại.
5. Consumer xử lý theo **`eventId` bất biến**, chịu được cùng message được phát/nhận nhiều lần.

~~~mermaid
flowchart LR
    API["Order API"] -->|"Một DB transaction"| DB[("orders + outbox_events")]
    DB -->|"Poll hoặc CDC"| R["Outbox relay"]
    R -->|"JMS persistent send + commit"| B[["ActiveMQ queue: shipping.commands"]]
    B -->|"Delivery có thể lặp"| W["Shipping consumer"]
    W -->|"DB transaction"| S[("shipment_jobs + consumer_inbox")]
    W -->|"JMS ACK sau DB commit"| B
~~~

**Cam kết quan trọng của outbox:** không có trạng thái **đơn hàng đã commit mà ý định phát message chưa được lưu**. Nó **không** tạo ra giao dịch nguyên tử giữa DB và broker; vì vậy **at-least-once publication** và **idempotent consumption** là một phần bắt buộc của thiết kế.

### 1.1. Phân biệt chính xác ba chữ “thành công”

| Bằng chứng | Có thể nói gì? | Không thể suy ra |
|---|---|---|
| `orders + outbox_events` commit DB | Ý định nghiệp vụ và phát message đã được lưu **nguyên tử trong DB** | Broker đã nhận message |
| Relay `JMSContext.commit()` thành công | Giao dịch gửi phía broker/JMS đã được provider xác nhận theo cấu hình | Consumer đã xử lý thành công |
| Consumer DB commit, sau đó JMS ACK | Tác dụng nghiệp vụ trong DB consumer đã được lưu; broker có thể gỡ message sau ACK | Mọi side effect ngoài DB tự động exactly-once |

Trong ví dụ, HTTP API có thể trả `201 Created` cho **resource order** đã được lưu; trạng thái `shipping=PENDING` vẫn còn đúng. Không trả “đã tạo vận đơn” ngay khi vừa commit outbox.

## 2. Vì sao chỉ dùng local transaction hoặc JMS transaction không đủ?

Xem bốn điểm lỗi:

~~~text
Order DB             Relay                 ActiveMQ broker
   |                   |                            |
   | COMMIT order      |                            |
   X <crash>           |                            |  (không có outbox)
   |                   |                            |
   | COMMIT order      |                            |
   | + outbox          |                            |
   |------------------>| poll committed outbox      |
   |                   |--- JMS SEND/COMMIT ------->|
   |                   X <crash before mark>         |  (message đã có)
   |                   |                            |
   |                   | retry same eventId ------->|  (có thể duplicate)
~~~

- **Không có outbox:** chết sau khi commit order và trước publish làm mất ý định phát.
- **Có outbox:** nếu order commit thì bản ghi outbox cũng commit; relay có thể đọc và phát sau khi API chết.
- **Relay chết sau JMS commit nhưng trước DB update `PUBLISHED`:** broker có message, outbox vẫn chưa đánh dấu, lần sau relay phát lại; **có thể duplicate**.
- **Consumer chết sau DB commit nhưng trước JMS ACK:** broker redeliver; consumer phải tránh tác dụng nghiệp vụ trùng.

Đừng cố chữa khoảng trống này bằng `Thread.sleep`, retry mù, hay giữ một JDBC transaction mở trong suốt lúc gọi broker. Hai commit thuộc hai resource manager độc lập. XA/2PC có thể phối hợp **những resource thực sự hỗ trợ XA** nhưng đi kèm recovery, timeout, log giao dịch, vận hành và mức sẵn sàng riêng; outbox thường được chọn khi chấp nhận **eventual consistency và duplicate delivery** với kiến trúc đơn giản hơn về phối hợp phân tán.

## 3. Thiết kế dữ liệu outbox có trạng thái và khả năng phục hồi

Ví dụ PostgreSQL sau dùng ba trạng thái:

- **`PENDING`**: bản ghi đã commit, có thể được relay claim khi `next_attempt_at` tới hạn.
- **`IN_FLIGHT`**: một relay đã claim bằng `claim_token` và lease có thời hạn.
- **`PUBLISHED`**: relay đã nhận kết quả JMS send/commit và cập nhật kết quả này vào DB.

`PUBLISHED` **không** có nghĩa consumer hoàn tất. Nếu hệ thống cần theo dõi tác vụ nghiệp vụ, dùng bảng trạng thái riêng như `shipments` hoặc `order_shipping_status`.

### 3.1. Schema PostgreSQL minh họa

~~~sql
CREATE TABLE orders (
    order_id         VARCHAR(64) PRIMARY KEY,
    state            VARCHAR(24) NOT NULL DEFAULT 'PLACED',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE outbox_events (
    event_id          UUID PRIMARY KEY,
    aggregate_type    VARCHAR(80) NOT NULL,
    aggregate_id      VARCHAR(128) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type        VARCHAR(120) NOT NULL,
    payload           JSONB NOT NULL,
    status            VARCHAR(16) NOT NULL DEFAULT 'PENDING'
                      CHECK (status IN ('PENDING','IN_FLIGHT','PUBLISHED')),
    attempt_count     INTEGER NOT NULL DEFAULT 0
                      CHECK (attempt_count >= 0),
    next_attempt_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    claim_token       UUID,
    lease_until       TIMESTAMPTZ,
    last_error        TEXT,
    published_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX outbox_due_idx
    ON outbox_events (next_attempt_at, created_at)
    WHERE status = 'PENDING';

CREATE INDEX outbox_expired_lease_idx
    ON outbox_events (lease_until)
    WHERE status = 'IN_FLIGHT';

-- Tùy hợp đồng miền dữ liệu, cấm ghi hai event cùng loại
-- ở cùng phiên bản của một aggregate:
CREATE UNIQUE INDEX outbox_aggregate_event_version_idx
    ON outbox_events
       (aggregate_type, aggregate_id, event_type, aggregate_version);
~~~

**Ý nghĩa các cột chính:**

| Cột | Vì sao cần |
|---|---|
| `event_id` | Định danh nghiệp vụ **ổn định qua retry**; consumer dùng để deduplicate. Không dùng `JMSMessageID` thay thế. |
| `aggregate_id` và `aggregate_version` | Hỗ trợ tương quan và phát hiện xử lý event sai thứ tự theo từng aggregate. |
| `event_type` + `payload` | Hợp đồng dữ liệu cho bên nhận; thêm `schemaVersion` trong payload khi cần tiến hóa schema. |
| `status` | Tiến độ của **relay**, không phải kết quả nghiệp vụ. |
| `claim_token`, `lease_until` | Cho phép nhiều relay claim an toàn; phát hiện relay chết hoặc lease hết hạn. |
| `attempt_count`, `next_attempt_at`, `last_error` | Retry có backoff và khả năng chẩn đoán. |
| `published_at` | Thời gian relay xác nhận publish; dùng cho metric/retention. |

Một số hệ outbox chỉ cần bảng append-only với `published_at` và `SELECT FOR UPDATE SKIP LOCKED`; schema trên dành cho **polling nhiều relay** có thể gặp sự cố và cần xử lý lease rõ ràng. Đừng thêm mọi cột nếu workload không cần, nhưng một khi relay chạy song song thì cơ chế sở hữu/khôi phục phải nhất quán.

**Ràng buộc version:** unique index trên `aggregate_type, aggregate_id, event_type, aggregate_version` chỉ hợp lý nếu mô hình nghiệp vụ quy định tối đa một event *cùng loại* cho mỗi phiên bản aggregate. Nếu một transaction hợp lệ phát nhiều event cùng loại từ cùng aggregate version, phải đổi khóa phù hợp. `aggregate_version` không tự sinh một thứ tự giao hàng tuyệt đối.

### 3.2. Bản ghi outbox mang nội dung gì?

Ví dụ:

~~~json
{
  "schemaVersion": 1,
  "eventId": "93c0125b-5043-4605-ae3d-84aa0d41afe2",
  "eventType": "ShippingRequested",
  "orderId": "order-1029",
  "occurredAt": "2026-11-17T08:00:00Z"
}
~~~

Nên lưu **thông tin đủ để consumer xử lý**, thay vì payload chứa toàn bộ object nghiệp vụ tùy ý. Dùng ID, schema version, loại event và các dữ kiện cần thiết; tránh password, token, thông tin nhạy cảm không cần thiết. Nếu consumer phải truy vấn thêm từ API nguồn, cân nhắc API nguồn có sẵn đúng lúc, version và điều kiện nhất quán của dữ liệu.

Phân biệt:
- **Command** `ShippingRequested`: “hãy làm việc này”; có thể gửi vào queue cho một nhóm worker.
- **Domain event** `OrderPlaced`: “việc này đã xảy ra”; có thể cần nhiều subscriber, topic hoặc multicast.

Outbox hoạt động cho cả command và event; **đích JMS, routing và semantics consumer** phải dựa vào hợp đồng thực tế.

## 4. Ghi business row và outbox row trong đúng một DB transaction

Mô hình chuẩn của API là một transaction tại **cùng PostgreSQL database**:

~~~sql
BEGIN;

INSERT INTO orders(order_id, state)
VALUES ('order-1029', 'PLACED');

INSERT INTO outbox_events(
    event_id, aggregate_type, aggregate_id,
    aggregate_version, event_type, payload
) VALUES (
    '93c0125b-5043-4605-ae3d-84aa0d41afe2',
    'Order', 'order-1029', 1, 'ShippingRequested',
    '{"schemaVersion":1,"eventId":"93c0125b-5043-4605-ae3d-84aa0d41afe2",
      "eventType":"ShippingRequested","orderId":"order-1029"}'::jsonb
);

COMMIT;
~~~

Nếu **bất kỳ** lệnh SQL nào thất bại, rollback cả hai. Nếu process chết sau COMMIT, outbox vẫn còn để relay xử lý. **Không gửi JMS bên trong transaction DB này** chỉ để tạo cảm giác an toàn: JDBC commit và JMS commit vẫn không nguyên tử, trong khi giữ lock DB lâu hơn.

### 4.1. Java/JDBC: một transaction, hai INSERT

Dùng `DataSource` đã được ứng dụng cấu hình. Trích đoạn dưới không phụ thuộc framework DI:

~~~java
package lab;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

public final class OrderWriter {
    private final DataSource dataSource;

    public OrderWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public UUID placeOrder(String orderId) throws SQLException {
        UUID eventId = UUID.randomUUID();

        try (Connection db = dataSource.getConnection()) {
            db.setAutoCommit(false);
            try {
                try (PreparedStatement st = db.prepareStatement(
                        "INSERT INTO orders(order_id, state) "
                        + "VALUES (?, 'PLACED')")) {
                    st.setString(1, orderId);
                    st.executeUpdate();
                }

                try (PreparedStatement st = db.prepareStatement(
                        "INSERT INTO outbox_events("
                        + "event_id, aggregate_type, aggregate_id,"
                        + "aggregate_version, event_type, payload) "
                        + "VALUES (?, 'Order', ?, 1, 'ShippingRequested', "
                        + "jsonb_build_object("
                        + "'schemaVersion', 1, "
                        + "'eventId', CAST(? AS text), "
                        + "'eventType', 'ShippingRequested', "
                        + "'orderId', CAST(? AS text)))")) {
                    st.setObject(1, eventId);
                    st.setString(2, orderId);
                    st.setString(3, eventId.toString());
                    st.setString(4, orderId);
                    st.executeUpdate();
                }

                db.commit();      // Order + outbox cùng được lưu.
                return eventId;
            } catch (SQLException | RuntimeException ex) {
                db.rollback();    // Không để chỉ một trong hai row commit.
                throw ex;
            }
        }
    }
}
~~~

**Điều kiện cần:** hai INSERT dùng **cùng `Connection`** trong cùng DB transaction. Nếu ORM hay repository tự tạo connection/transaction khác nhau, cấu trúc trên sẽ không còn nguyên tử; kiểm tra transaction manager thực tế. Khi hai bảng ở **hai database/resource khác nhau**, một local JDBC transaction cũng không bao phủ cả hai.

**HTTP retry:** nếu client gửi lại cùng yêu cầu vì timeout, tạo `eventId` mới có thể phát hai yêu cầu shipping cho cùng đơn. Production cần **API idempotency key/unique business constraint** để trả lại kết quả của request đã commit, thay vì chỉ bắt duplicate key rồi trả lỗi không rõ trạng thái. Ví dụ cố ý dùng `order_id` duy nhất nhưng chưa triển khai đầy đủ idempotency endpoint.

## 5. Relay polling: claim, publish, mark với lease và khóa sở hữu

Relay là phần quyết định khả năng phục hồi. Không nên để hai instance cùng đọc tất cả row `PENDING` bằng `SELECT` thông thường rồi cùng gửi; cả hai có thể publish cùng event.

Một thiết kế phổ biến là:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: DB commit tạo row
    PENDING --> IN_FLIGHT: relay claim + token + lease
    IN_FLIGHT --> PUBLISHED: JMS commit OK, cập nhật bằng token đúng
    IN_FLIGHT --> PENDING: publish lỗi và lên lịch retry
    IN_FLIGHT --> IN_FLIGHT: lease hết hạn, relay khác claim lại
    PUBLISHED --> [*]: lưu theo retention / archive
~~~

Trong ví dụ, **mỗi relay claim một event tại một thời điểm**, commit claim nhanh, rồi gọi broker **ngoài DB transaction**. Điều này tránh giữ row lock trong suốt network call.

### 5.1. Claim an toàn bằng PostgreSQL `SKIP LOCKED`

SQL sau áp dụng trong **DB transaction ngắn**:

~~~sql
WITH picked AS (
    SELECT event_id
    FROM outbox_events
    WHERE (status = 'PENDING' AND next_attempt_at <= now())
       OR (status = 'IN_FLIGHT' AND lease_until < now())
    ORDER BY created_at, event_id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE outbox_events AS o
SET status        = 'IN_FLIGHT',
    claim_token   = ?,
    lease_until   = now() + INTERVAL '60 seconds',
    attempt_count = o.attempt_count + 1
FROM picked AS p
WHERE o.event_id = p.event_id
RETURNING o.event_id, o.aggregate_id, o.event_type,
          o.payload::text AS payload_text,
          o.claim_token, o.attempt_count;
~~~

- `FOR UPDATE SKIP LOCKED` để các relay đang chạy song song **không đợi nhau khóa cùng row** ở bước chọn.
- `claim_token` là UUID mới mỗi lần claim, dùng như **fencing token cho việc cập nhật trạng thái row**.
- Lease hết hạn giúp event được claim lại khi relay chết sau claim, trước publish.
- `attempt_count` hỗ trợ metric/retry, nhưng không phải số lần broker chắc chắn đã nhận message.
- `ORDER BY created_at` chỉ ưu tiên lấy row cũ; với nhiều relay và retry, **không bảo đảm thứ tự event cho một order**.

**Giới hạn của lease:** relay có thể gửi JMS rất chậm, hết lease và bị relay khác claim trước khi send hoàn tất. Fencing token chỉ ngăn relay cũ **đánh dấu trạng thái row bằng token hết hạn**, nó không thu hồi được message đã gửi vào broker. Cần timeout publish ngắn hơn lease, hoặc gia hạn lease, và **consumer vẫn bắt buộc idempotent**.

### 5.2. Sau JMS commit, đánh dấu published bằng điều kiện token

~~~sql
UPDATE outbox_events
SET status       = 'PUBLISHED',
    published_at = now(),
    claim_token  = NULL,
    lease_until  = NULL,
    last_error   = NULL
WHERE event_id = ?
  AND claim_token = ?
  AND status = 'IN_FLIGHT';
~~~

Nếu UPDATE tác động **0 row**, lease có thể đã bị relay khác claim hoặc trạng thái bị thay đổi; **không** chạy UPDATE không có token để cưỡng ép `PUBLISHED`. Broker có thể đã nhận message từ relay cũ, còn relay mới cũng có thể phát lại. Hãy ghi metric, điều tra khi tỷ lệ token mismatch cao và dựa vào dedup consumer.

Nếu publish thất bại hoặc **kết quả không rõ**, đánh dấu lại `PENDING` cùng backoff bằng token đang sở hữu:

~~~sql
UPDATE outbox_events
SET status          = 'PENDING',
    next_attempt_at = now() + (? * INTERVAL '1 second'),
    claim_token     = NULL,
    lease_until     = NULL,
    last_error      = ?
WHERE event_id = ?
  AND claim_token = ?
  AND status = 'IN_FLIGHT';
~~~

Không ghi log toàn bộ payload/token nhạy cảm vào `last_error`; ở production nên chuẩn hóa mã lỗi và giới hạn kích thước. Nếu database cũng đang lỗi nên chưa cập nhật được, lease sẽ hết hạn và row vẫn được lấy lại.

### 5.3. Java/JDBC + Jakarta JMS: relay tối thiểu

Ứng dụng thực có thể chạy relay định kỳ qua scheduler/worker. Đoạn dưới trình bày **một lượt `runOnce()`**, phù hợp để đưa vào dịch vụ có `DataSource`, `ConnectionFactory` và thông tin đăng nhập đã được cấp. Nó không tạo một Spring application hoặc HTTP server.

Dependency Maven tương ứng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <version>42.7.4</version>
    </dependency>
    <dependency>
        <groupId>org.apache.activemq</groupId>
        <artifactId>artemis-jakarta-client</artifactId>
        <version>2.40.0</version>
    </dependency>
    <dependency>
        <groupId>jakarta.jms</groupId>
        <artifactId>jakarta.jms-api</artifactId>
        <version>3.1.0</version>
    </dependency>
</dependencies>
~~~

Các phiên bản được **cố định để minh họa**, không có hàm ý mới nhất. Artemis native Jakarta JMS client giao tiếp bằng protocol phù hợp với broker Artemis; ActiveMQ Classic 5.x thường cần `activemq-client` và namespace `javax.jms` tương ứng.

~~~java
package lab;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSException;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import java.util.UUID;

public final class OutboxRelay {
    private static final String ADDRESS = "shipping.commands";

    private final DataSource dataSource;
    private final ConnectionFactory jmsFactory;
    private final String brokerUser;
    private final String brokerPassword;

    public OutboxRelay(DataSource dataSource, ConnectionFactory jmsFactory,
                       String brokerUser, String brokerPassword) {
        this.dataSource = dataSource;
        this.jmsFactory = jmsFactory;
        this.brokerUser = brokerUser;
        this.brokerPassword = brokerPassword;
    }

    private record Event(UUID id, String aggregateId, String type,
                         String payload, UUID token, int attempts) {}

    // Scheduler gọi định kỳ; nhiều instance có thể cùng gọi.
    public boolean runOnce() throws SQLException {
        Optional<Event> item = claimOne();
        if (item.isEmpty()) {
            return false; // Chưa có event tới hạn.
        }

        Event event = item.get();
        try {
            publishToJms(event);
        } catch (Exception sendOrCommitFailure) {
            // JMS commit có thể đã xảy ra dù client nhận exception.
            // Retry cùng eventId; consumer phải chịu được duplicate.
            scheduleRetry(event, sendOrCommitFailure);
            return true;
        }

        // JMS commit trả thành công; cập nhật DB độc lập với JMS.
        // Nếu DB lỗi, để lease hết hạn và thử lại (có thể phát trùng).
        if (!markPublished(event)) {
            System.err.println("OUTBOX_STALE_CLAIM eventId=" + event.id());
        }
        return true;
    }

    private Optional<Event> claimOne() throws SQLException {
        String sql = """
            WITH picked AS (
                SELECT event_id FROM outbox_events
                WHERE (status='PENDING' AND next_attempt_at <= now())
                   OR (status='IN_FLIGHT' AND lease_until < now())
                ORDER BY created_at, event_id
                LIMIT 1 FOR UPDATE SKIP LOCKED
            )
            UPDATE outbox_events o
            SET status='IN_FLIGHT',
                claim_token=?,
                lease_until=now() + INTERVAL '60 seconds',
                attempt_count=o.attempt_count + 1
            FROM picked p
            WHERE o.event_id=p.event_id
            RETURNING o.event_id, o.aggregate_id, o.event_type,
                      o.payload::text AS payload_text,
                      o.claim_token, o.attempt_count
            """;

        UUID token = UUID.randomUUID();
        try (Connection db = dataSource.getConnection()) {
            db.setAutoCommit(false);
            try {
                Optional<Event> result;
                try (PreparedStatement st = db.prepareStatement(sql)) {
                    st.setObject(1, token);
                    try (ResultSet rs = st.executeQuery()) {
                        result = rs.next()
                                ? Optional.of(new Event(
                                        (UUID) rs.getObject("event_id"),
                                        rs.getString("aggregate_id"),
                                        rs.getString("event_type"),
                                        rs.getString("payload_text"),
                                        (UUID) rs.getObject("claim_token"),
                                        rs.getInt("attempt_count")))
                                : Optional.empty();
                    }
                }
                db.commit(); // Giải phóng row lock trước khi gọi JMS.
                return result;
            } catch (SQLException | RuntimeException ex) {
                db.rollback();
                throw ex;
            }
        }
    }

    private void publishToJms(Event event) throws JMSException {
        try (JMSContext jms = jmsFactory.createContext(
                brokerUser, brokerPassword,
                JMSContext.SESSION_TRANSACTED)) {

            Queue queue = jms.createQueue(ADDRESS);
            TextMessage message = jms.createTextMessage(event.payload());
            message.setStringProperty("eventId", event.id().toString());
            message.setStringProperty("aggregateId", event.aggregateId());
            message.setStringProperty("eventType", event.type());

            jms.createProducer()
               .setDeliveryMode(DeliveryMode.PERSISTENT)
               .send(queue, message);

            jms.commit(); // Đây là mốc publish/commit phía JMS.
        }
    }

    private boolean markPublished(Event e) throws SQLException {
        String sql = """
            UPDATE outbox_events
            SET status='PUBLISHED', published_at=now(),
                claim_token=NULL, lease_until=NULL, last_error=NULL
            WHERE event_id=? AND claim_token=? AND status='IN_FLIGHT'
            """;
        try (Connection db = dataSource.getConnection();
             PreparedStatement st = db.prepareStatement(sql)) {
            st.setObject(1, e.id());
            st.setObject(2, e.token());
            return st.executeUpdate() == 1;
        }
    }

    private void scheduleRetry(Event e, Exception error)
            throws SQLException {
        String sql = """
            UPDATE outbox_events
            SET status='PENDING',
                next_attempt_at=now() + (? * INTERVAL '1 second'),
                claim_token=NULL, lease_until=NULL, last_error=?
            WHERE event_id=? AND claim_token=? AND status='IN_FLIGHT'
            """;

        // Exponential backoff minh họa: 2, 4, 8... tối đa 300 giây.
        long delaySeconds = Math.min(
                300L, 1L << Math.min(8, e.attempts()));

        try (Connection db = dataSource.getConnection();
             PreparedStatement st = db.prepareStatement(sql)) {
            st.setLong(1, delaySeconds);
            st.setString(2, error.getClass().getSimpleName());
            st.setObject(3, e.id());
            st.setObject(4, e.token());
            if (st.executeUpdate() != 1) {
                System.err.println(
                        "OUTBOX_RETRY_TOKEN_MISMATCH eventId=" + e.id());
            }
        }
    }
}
~~~

**Đọc code đúng phạm vi:**

- `OrderWriter` commit **orders + outbox** ở một DB transaction; `OutboxRelay` chạy sau, hoàn toàn tách khỏi transaction đó.
- `claimOne()` dùng `SKIP LOCKED` cùng token/lease và **commit claim trước khi gọi JMS**.
- `publishToJms()` thực hiện **JMS transacted send**; `send()` trong transaction chưa đủ, phải có `jms.commit()`.
- `markPublished()` là cập nhật DB **riêng sau JMS commit**. Việc này có thể thất bại, gây phát trùng khi lease hết hạn.
- `scheduleRetry()` lên lịch phát lại bằng **cùng `eventId`**. Với lỗi trong `commit()`, relay không thể kết luận chắc broker chưa nhận.
- Ví dụ dùng `60 seconds` lease và gửi mỗi lần một event để dễ thấy phạm vi. Production phải cấu hình timeout, lease renewal, jitter, batching, giới hạn concurrency và health check phù hợp.

**Vấn đề cần tránh trong môi trường thật:** Nếu gọi `runOnce()` thành một vòng lặp vô hạn không giới hạn nhịp, DB có thể bị poll liên tục. Dùng scheduler có backoff khi queue outbox rỗng, connection pool được giới hạn, metric và graceful shutdown. Với task đã claim nhưng process bị kill, lease hết hạn sẽ cho một relay khác xử lý tiếp.

### 5.4. Cấu hình broker Artemis cần khớp

Trích đoạn đặt **bên trong** khối `<addresses>` sẵn có của `broker.xml`:

~~~xml
<address name="shipping.commands">
    <anycast>
        <queue name="shipping.commands" durable="true"/>
    </anycast>
</address>
~~~

JMS queue gửi tới `shipping.commands` phải được route vào queue tương ứng; user relay có quyền **send**. Dùng chế độ persistent không thay thế cấu hình storage/journal, backup/replication hoặc chính sách expiry. Với **ActiveMQ Classic**, cần cấu hình queue/store/security và client phù hợp với Classic; outbox ở DB **không yêu cầu** broker phải thuộc một dòng cụ thể.

## 6. Những điểm lỗi phải mô phỏng

Bảng này quan trọng hơn việc chỉ kiểm thử đường đi thành công:

| Vị trí lỗi | Dữ liệu đang ở đâu? | Khả năng xảy ra | Kết quả thiết kế đúng |
|---|---|---|---|
| API chết **trước DB commit** | Không có order/outbox đã commit | Request thất bại hoặc không rõ | Giao dịch rollback; retry API theo idempotency key |
| API chết **sau DB commit** | Có order và outbox `PENDING` | Relay chạy về sau | Không mất ý định publish |
| Relay chết **sau claim, trước JMS send** | Outbox `IN_FLIGHT`, broker chưa chắc có message | Lease còn hiệu lực | Lease hết hạn → claim lại |
| Relay send nhưng **JMS transaction rollback** | Outbox còn `IN_FLIGHT`/`PENDING` | Không có publish commit thành công | Retry, giữ cùng eventId |
| Broker commit JMS nhưng reply mất | Broker **có thể** đã có message | Relay thấy timeout/exception | Retry có thể trùng; consumer dedup |
| JMS commit thành công, relay chết **trước DB mark** | Broker có message, outbox chưa `PUBLISHED` | Relay sau phát lại | Consumer chỉ áp dụng nghiệp vụ một lần |
| DB mark `PUBLISHED` thành công | Relay hoàn tất trách nhiệm publish | Consumer vẫn có thể offline/lỗi | Theo dõi delivery và business state riêng |
| Consumer DB commit, **trước JMS ACK** bị chết | Business DB đã thay đổi, broker có thể redeliver | Duplicate delivery | Consumer dedup theo eventId, ACK sau DB commit |
| Consumer xử lý mãi không được | Message retries rồi có thể vào DLQ | Outbox vẫn `PUBLISHED` | Theo dõi DLQ và business status, không coi published là completed |
| Relay lease hết hạn khi JMS send chậm | Hai relay có thể cùng publish | Duplicate ngoài thời điểm crash | Fencing DB update, timeout/lease phù hợp, idempotency |

Bài test có giá trị phải kiểm tra **DB rows, queue message, eventId và tác dụng nghiệp vụ** ở cả trước và sau điểm crash.

## 7. Consumer idempotent: phần không thể thiếu của outbox

Outbox không chống được phát trùng: consumer **phải** chịu được ít nhất hai lần delivery cho cùng `eventId`.

Đối với mỗi nhóm xử lý độc lập, sử dụng `(consumer_name, event_id)` làm khóa duy nhất. Nếu hai service **Shipping** và **Analytics** đều xử lý cùng event, chúng không được ngăn nhau chỉ vì dùng chung event ID.

### 7.1. Schema của consumer

Ví dụ trong database của Shipping service:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(80) NOT NULL,
    event_id      UUID NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE shipment_jobs (
    order_id      VARCHAR(64) PRIMARY KEY,
    status        VARCHAR(24) NOT NULL DEFAULT 'NEW',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Khi nhận message, consumer thực hiện **trong một DB transaction**:

~~~sql
BEGIN;

INSERT INTO consumer_inbox(consumer_name, event_id)
VALUES ('shipping-worker', '93c0125b-5043-4605-ae3d-84aa0d41afe2')
ON CONFLICT DO NOTHING;

-- Chỉ khi INSERT phía trên thực sự thêm 1 row:
INSERT INTO shipment_jobs(order_id, status)
VALUES ('order-1029', 'NEW');

COMMIT;
-- SAU ĐÓ consumer mới ACK/COMMIT JMS
~~~

Trong code thực phải kiểm tra số row được INSERT vào `consumer_inbox`; nếu **0**, coi event đã được xử lý và **bỏ qua side effect** trước khi ACK. SQL phía trên chỉ minh họa luồng, không phải script tự động kiểm tra điều kiện.

### 7.2. Java/JDBC consumer handler có điều kiện rõ ràng

~~~java
package lab;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

public final class ShippingInboxHandler {
    private final DataSource dataSource;

    public ShippingInboxHandler(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void process(UUID eventId, String orderId)
            throws SQLException {
        try (Connection db = dataSource.getConnection()) {
            db.setAutoCommit(false);
            try {
                int inserted;
                try (PreparedStatement st = db.prepareStatement(
                        "INSERT INTO consumer_inbox(consumer_name,event_id) "
                        + "VALUES ('shipping-worker', ?) "
                        + "ON CONFLICT DO NOTHING")) {
                    st.setObject(1, eventId);
                    inserted = st.executeUpdate();
                }

                if (inserted == 1) {
                    try (PreparedStatement st = db.prepareStatement(
                            "INSERT INTO shipment_jobs(order_id,status) "
                            + "VALUES (?, 'NEW')")) {
                        st.setString(1, orderId);
                        st.executeUpdate();
                    }
                }

                db.commit();
            } catch (SQLException | RuntimeException ex) {
                db.rollback();
                throw ex;
            }
        }
    }
}
~~~

Với PostgreSQL, unique constraint bảo đảm hai consumer concurrent xử lý cùng event không cùng ghi dấu thành công. Khi DB transaction đầu rollback, dấu inbox và nghiệp vụ cùng rollback; transaction khác có thể xử lý sau.

**Giới hạn:** nếu business handler còn gọi API hãng vận chuyển bên ngoài DB, một transaction local không quản lý được side effect bên ngoài. Cần sử dụng **idempotency key với đối tác** hoặc cách ghi trạng thái/đối soát trước khi thử lại. Đối với event có nhiều phiên bản/order state, dedup theo eventId chưa đủ đảm bảo thứ tự: phải có version check/optimistic locking hoặc xử lý theo khóa.

### 7.3. ACK JMS sau DB commit

~~~java
// Trích đoạn trong consumer sử dụng jakarta.jms, một message/lượt.
try (JMSContext jms = factory.createContext(
        user, password, JMSContext.SESSION_TRANSACTED)) {
    JMSConsumer consumer = jms.createConsumer(
            jms.createQueue("shipping.commands"));
    Message message = consumer.receive(5000);

    if (message != null) {
        try {
            UUID eventId = UUID.fromString(
                    message.getStringProperty("eventId"));
            String orderId = message.getStringProperty("aggregateId");

            handler.process(eventId, orderId); // DB COMMIT bên trong.
            jms.commit();                       // JMS ACK COMMIT sau.
        } catch (Exception failure) {
            jms.rollback(); // Để broker redeliver theo chính sách.
            throw failure;
        }
    }
}
~~~

Ở đây `factory`, `user`, `password` và `handler` do ứng dụng cấu hình; trích đoạn không phải một file Java độc lập. Transaction **JMS** và transaction **PostgreSQL** vẫn độc lập. Nếu process chết giữa hai commit, lần nhận lại đi qua `consumer_inbox` và tránh tạo tác dụng nghiệp vụ trùng.

## 8. Ordering: outbox không tự bảo đảm thứ tự event

Giả sử một order phát:

~~~text
v1: OrderPlaced
v2: AddressChanged
v3: OrderCancelled
~~~

Với hai relay poll song song:
- Relay A claim `v1` nhưng gửi chậm.
- Relay B claim `v2` và publish trước.
- Consumer có thể thấy `v2` trước `v1`, đặc biệt khi retry và nhiều queue/consumer.

**`ORDER BY created_at` + `SKIP LOCKED` không bảo đảm strict per-aggregate ordering.** Một số cách xử lý:

1. **Thiết kế consumer chịu thứ tự không chắc chắn:** mang `aggregate_version`, chỉ chấp nhận phiên bản phù hợp hoặc đối soát trạng thái mới nhất.
2. **Serialize publish theo aggregate:** không claim `v2` khi `v1` của cùng aggregate chưa được xử lý theo điều kiện nghiệp vụ; cần lock/partition strategy có chủ đích.
3. **Partition theo khóa:** định tuyến toàn bộ event của một aggregate qua cùng lane/consumer có trật tự phù hợp; vẫn phải xử lý retry và failover.
4. **CDC theo database log:** có thể giúp bảo toàn một số thứ tự commit trong cùng nguồn dữ liệu, nhưng khi chuyển qua queue, nhiều worker và redelivery vẫn có thể thay đổi thứ tự hoàn tất.

Nếu một event cũ có thể ghi đè trạng thái mới, **version check phía consumer** mới là rào chắn cuối cùng đáng tin cậy.

## 9. Polling outbox và CDC: chọn mô hình relay phù hợp

| Tiêu chí | Polling publisher (ví dụ trong bài) | CDC / transaction log relay |
|---|---|---|
| Phát hiện row đã commit | Query `outbox_events` định kỳ | Đọc WAL/binlog của DB thông qua connector phù hợp |
| Độ trễ | Phụ thuộc polling interval, tải DB, backlog | Có thể thấp, phụ thuộc connector/lag và hạ tầng |
| Tải nguồn | Query/index/lock, có thể nhiều request rỗng | WAL retention, replication slot/log capture và vận hành connector |
| Đồng thời | `SKIP LOCKED`, claim token, lease | Connector phân vùng/snapshot/offset theo công nghệ |
| Retry | Tự triển khai trạng thái PENDING/IN_FLIGHT/backoff | Checkpoint/offset, delivery/retry của connector/sink |
| Ordering | Phải thiết kế nếu nhiều relay/worker | Có thể giữ log order tại nguồn, nhưng downstream vẫn cần ràng buộc |
| Duplication | Có thể phát trùng | Vẫn phải thiết kế idempotency và kiểm tra sink guarantee |
| Vận hành | Dễ bắt đầu khi đã có DB | Thêm connector, quyền đọc log, giám sát lag và retention |

Với PostgreSQL, **Debezium outbox event router** là một cách phổ biến xây CDC relay; tuy nhiên nó có **schema/mapping yêu cầu riêng**. Bảng outbox trạng thái `PENDING/IN_FLIGHT/PUBLISHED` trong bài **không thể đưa nguyên xi vào một cấu hình Debezium mặc định mà coi là tương đương**. Nếu chuyển sang CDC, thiết kế lại hợp đồng bảng, cấu hình routing, offset và sink tương ứng. Không nên để cả polling relay và CDC relay cùng đọc/phát một bảng mà không có quy tắc sở hữu rõ ràng.

CDC không tự cấp exactly-once end-to-end qua **DB → connector → broker → consumer business DB**. Dù connector hỗ trợ transaction/checkpoint ở một đoạn pipeline, cần xác minh toàn bộ phạm vi và vẫn xử lý trùng ở consumer.

## 10. Hợp đồng JMS và cấu hình ActiveMQ cần quan tâm

Outbox giải quyết **atomicity giữa business DB và ý định publish**. Nó không cấu hình hộ phần messaging. Phải xác minh:

- **Routing:** destination JMS queue/topic đúng tên; với Artemis cần address/queue và **ANYCAST/MULTICAST** tương ứng. Một send được client xác nhận không tự nói message đã tới queue mong muốn nếu destination/routing không hợp lệ.
- **Persistence:** producer dùng `PERSISTENT`, broker có durable queue/store/journal phù hợp yêu cầu. Test restart broker bằng storage thực.
- **Security:** relay chỉ có quyền `send` đích cần thiết; consumer chỉ có `consume`; TLS và quản lý credential riêng. Không lưu credential trong outbox payload.
- **Transaction:** relay chỉ đánh dấu `PUBLISHED` **sau** mốc send/commit đã chọn; JMS session transacted cần `commit()`.
- **Expiry/TTL:** nếu TTL ngắn hơn thời gian backlog/recovery, một message có thể expire trước khi consumer xử lý, dù outbox đã `PUBLISHED`. Cần định nghĩa chính sách TTL và yêu cầu nghiệp vụ.
- **Redelivery/DLQ:** sau publish, consumer rollback có thể khiến message redeliver hoặc vào DLQ; outbox vẫn có trạng thái `PUBLISHED`. Cảnh báo business failure không được chỉ dựa vào outbox.
- **Client/protocol:** ví dụ Java dùng `artemis-jakarta-client` với `jakarta.jms`. ActiveMQ Classic 5.x thường dùng `activemq-client` với `javax.jms`; outbox DB/relay pattern vẫn giữ nguyên, còn XML/SDK/client policy phải chọn đúng sản phẩm.

**Không hứa “exactly-once message delivery” chỉ vì có outbox.** Thành quả đúng có thể đạt được là **at-least-once publish + idempotent business effect trong phạm vi hệ thống đã thiết kế**, với việc xử lý được các điểm lỗi và khả năng đối soát.

## 11. Retry, poison event, retention và housekeeping

### 11.1. Backoff và giới hạn retry

Retry ngay với một broker đang ngắt sẽ tạo storm và tăng tải DB. Dùng exponential backoff có jitter; ví dụ:

~~~text
attempt 1 -> 2 s (+ jitter)
attempt 2 -> 4 s (+ jitter)
attempt 3 -> 8 s (+ jitter)
...
max      -> 5 min (+ jitter)
~~~

Jitter làm nhiều relay bớt thử lại đồng loạt. Tách lỗi:

- **Tạm thời:** mất kết nối broker, timeout, dịch vụ không sẵn sàng; retry có giới hạn tốc độ.
- **Dữ liệu sai/không hợp lệ:** schema không thể serialize hoặc destination sai; cảnh báo/đưa quarantine, không retry vô hạn mà không sửa nguyên nhân.
- **Trạng thái JMS commit không chắc chắn:** **vẫn phải chịu duplicate**, không biến timeout thành khẳng định broker chắc chắn chưa nhận.
- **Lỗi authorization:** không tự mở rộng quyền của relay; sửa quyền/cấu hình chính xác rồi phát lại.

Nếu triển khai trạng thái `FAILED` hoặc `QUARANTINED`, phải cập nhật **schema/check constraint, retry worker, alert, manual replay policy** nhất quán. Mẫu schema ba trạng thái ở mục 3 không có trạng thái này để giữ đường đi minh họa gọn.

### 11.2. Giữ lại dữ liệu và xóa an toàn

Bảng outbox có thể lớn nhanh; nên:

1. Giữ các row `PUBLISHED` đủ lâu phục vụ điều tra/audit hoặc chuyển sang bảng lưu trữ.
2. Chỉ xóa/archive row sau mốc thời gian và chính sách được duyệt, bảo đảm không xóa `PENDING`/`IN_FLIGHT` đang cần recovery.
3. Giám sát index bloat, vacuum, partition và tốc độ ghi đọc khi volume tăng.
4. Nếu archive phục vụ audit, phân biệt “đã publish” với “consumer đã xử lý”; outbox không thay thế business audit log.

Không xóa message/row retry chỉ để làm hết cảnh báo backlog. Cần có quy trình sửa lỗi và tái phát có kiểm soát cùng ID gốc.

### 11.3. Chỉ số vận hành nên có

| Metric | Giải thích | Khi nào đáng báo động |
|---|---|---|
| `outbox_pending_count` | Số event chưa được relay phát | Tăng liên tục khi API vẫn tạo event |
| `outbox_oldest_pending_age_seconds` | Độ tuổi event chưa phát lâu nhất | Vượt SLA publish |
| `outbox_inflight_expired_count` | Lease hết hạn, cần reclaim | Nhiều relay chết/đang treo hoặc lease quá ngắn |
| `outbox_publish_attempts_total` | Tổng lần relay thử publish | Tăng nhanh nhưng published không tăng |
| `outbox_publish_unknown_total` | Kết quả JMS send/commit không rõ | Tăng khi broker/network không ổn định |
| `outbox_published_total` | Row chuyển sang PUBLISHED | Không tương đương shipping completed |
| `outbox_token_mismatch_total` | Relay mất quyền claim trước khi cập nhật DB | Lease hết hạn khi send lâu, concurrency/GC pause |
| `outbox_db_update_failures_total` | Lỗi đánh dấu trạng thái sau publish | Nguy cơ phát trùng khi lease hết hạn |
| `consumer_deduplicated_total` | Delivery trùng đã bị consumer bỏ qua an toàn | Tăng đột biến báo hiệu relay/retry hoặc broker issue |
| `shipping_business_failures_total` / DLQ size | Lỗi xử lý sau publish | Published vẫn bình thường nhưng nghiệp vụ không hoàn tất |

Cảnh báo cần gắn với **SLO publish và SLO xử lý nghiệp vụ riêng**. Một queue chờ lâu là vấn đề consumer/broker; một outbox row chờ lâu là vấn đề API DB/relay/JMS publish. Khi cả hai cùng tăng, điều tra chuỗi phụ thuộc và rate limit.

## 12. Bộ kiểm thử lỗi tối thiểu

Các phép thử sau nên chạy trên môi trường lab với queue và database dành riêng. Không dùng queue có dữ liệu production để purge/seed.

| Thử nghiệm | Cách thực hiện | Điều phải xác nhận |
|---|---|---|
| **DB rollback** | Cho INSERT outbox lỗi để transaction Order rollback | Không có order **và** outbox row được commit |
| **API chết sau DB commit** | Kill API sau commit nhưng trước bất kỳ publish nào | Row `PENDING` vẫn có và relay gửi được |
| **Relay chết sau claim** | Kill sau khi UPDATE IN_FLIGHT commit nhưng trước JMS send | Lease hết hạn, relay khác claim lại |
| **Relay chết sau JMS commit** | Kill ngay trước `markPublished` | Consumer có thể nhận trùng; business effect đúng một lần |
| **Mất phản hồi JMS commit** | Dùng test hook/proxy cắt kết nối ở thời điểm commit | Relay đánh dấu chưa chắc chắn và retry cùng eventId |
| **Chậm quá lease** | Tạo delay ở JMS send vượt lease | Token cũ không được mark; có thể duplicate; consumer dedup |
| **DB unavailable sau JMS commit** | Ngắt DB ở bước mark | Lease phục hồi và retry; không mất event |
| **Consumer crash sau DB commit** | Kill trước JMS ACK commit | Message có thể redeliver, inbox ngăn side effect trùng |
| **Hai relay cạnh tranh** | Chạy hai instance claim liên tục | Không cùng claim token sống trong DB cho một row ở cùng thời điểm |
| **Sai thứ tự aggregate** | Cố ý làm `v1` chậm hơn `v2` | Consumer version check không cho state cũ ghi đè state mới |
| **Poison message** | Gửi payload sai schema có eventId rõ ràng | Quarantine/DLQ/alert được kích hoạt; không mất dấu event |
| **Broker restart** | Gửi persistent message, dừng và khởi động lại broker cùng store | Kiểm chứng persistence/queue recovery và relay reconciliation |

### 12.1. Một kịch bản cần suy luận kỹ

Ở thời điểm T1, relay A claim `evt-9`. T2, A gửi JMS và commit thành công. T3, A chết trước cập nhật `PUBLISHED`. T4, lease hết hạn, relay B claim `evt-9` và gửi lại. T5, Shipping worker nhận cả hai delivery.

**Kết quả hợp lý**: hai JMS message có thể mang **hai `JMSMessageID` khác nhau** nhưng **cùng `eventId=evt-9`**. Consumer chỉ thêm **một** row `consumer_inbox` và một shipment job nhờ unique constraint trong cùng DB transaction. Relay cuối cùng đánh dấu outbox `PUBLISHED`. Đây là **duplicate delivery được kiểm soát**, không phải exactly-once delivery.

### 12.2. Vì sao không đặt `PUBLISHED` trước khi gửi?

Nếu cập nhật `PUBLISHED` trong DB rồi mới `send()`, relay có thể chết ở giữa; row không được retry dù broker chưa có message. Thiết kế đúng **ưu tiên không mất ý định phát** và chấp nhận có thể gửi trùng, vì trùng có thể được nhận diện bằng `eventId`, còn message chưa từng được gửi nhưng đã bị đánh dấu xong thì khó khôi phục.

## 13. Checklist review thiết kế

- [ ] Business row và outbox row được ghi trong **cùng một DB transaction** thực sự.
- [ ] Event ID/aggregate ID/schema version ổn định qua retry và HTTP request idempotency được định nghĩa.
- [ ] Relay chỉ đọc **row đã commit**, có cách claim tránh nhiều relay lấy cùng một row đang sống.
- [ ] Claim có lease và token; crash sau claim có thể khôi phục.
- [ ] JMS send/commit và DB mark published được ghi nhận là **hai commit độc lập**.
- [ ] Không đánh dấu published trước khi kết quả JMS publish/commit đạt điều kiện.
- [ ] Tình huống commit JMS không chắc chắn được xử lý bằng retry + idempotency, không giả định chưa nhận.
- [ ] Consumer có inbox/dedup và cập nhật nghiệp vụ trong **cùng DB transaction**.
- [ ] Consumer ACK/commit JMS sau khi business DB commit thành công.
- [ ] Ordering theo aggregate, TTL, no-route, queue durability, DLQ và re-drive được thiết kế.
- [ ] Retry/backoff/jitter/retention và cảnh báo có owner vận hành.
- [ ] Đã thử lỗi tại mọi điểm **trước/sau DB commit, JMS commit và mark published**.
- [ ] Đã tách SLO `outbox publish` khỏi `business completed`.

## 14. Kết luận kỹ thuật

**Transactional outbox biến thao tác “ghi DB rồi cố gửi JMS” thành “ghi DB và ý định gửi trong cùng một commit, rồi phát thông điệp có thể thử lại”.** Nhờ đó, nếu thay đổi nghiệp vụ đã commit, relay còn một bản ghi bền để khôi phục việc phát khi API hoặc broker gặp sự cố.

Ranh giới giữa **JMS commit** và **đánh dấu outbox `PUBLISHED`** vẫn không nguyên tử: relay có thể gửi trùng sau lỗi hoặc timeout. Giải pháp đáng tin cậy là **eventId bất biến, consumer idempotent, ACK sau business commit, lease/fencing, retry có kiểm soát, đối soát và giám sát riêng từng mốc**. Áp dụng đúng các nguyên tắc này với ActiveMQ Artemis hoặc Classic để đảm bảo ý định phát không bị bỏ sót và tác dụng nghiệp vụ không bị lặp trong phạm vi đã thiết kế.
