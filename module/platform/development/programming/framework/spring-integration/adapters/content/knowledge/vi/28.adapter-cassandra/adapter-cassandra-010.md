# Thiết kế idempotent khi ghi Cassandra trong Spring Integration

## 1. Bài toán: một sự kiện có thể được giao nhiều lần

Hãy xét luồng xử lý thanh toán:

~~~text
JMS/Kafka/HTTP
   -> Inbound adapter / gateway
   -> Spring Integration MessageChannel
   -> Validate + Transformer
   -> Cassandra outbound channel adapter
   -> Apache Cassandra
   -> Acknowledge/commit nguồn
~~~

Một sự kiện `OrderPaid(eventId=evt-10001)` có thể tới consumer nhiều lần vì mạng chập chờn, client timeout, broker redelivery, Kafka replay, deployment restart hoặc đối soát dữ liệu. **Đó là hành vi bình thường của nhiều kiến trúc at-least-once**, không nhất thiết là producer “gửi lỗi”.

Giả sử Cassandra đã ghi thành công nhưng phản hồi tới ứng dụng bị mất. Ứng dụng thấy `DriverTimeoutException`, JMS listener rollback, broker giao lại cùng sự kiện. Nếu consumer tạo UUID mới mỗi lần, bảng Cassandra có thể chứa **hai row cho một business event**. Nếu consumer ghi cùng row rồi gửi hai email xác nhận, row có thể đúng nhưng **nghiệp vụ vẫn xử lý lặp**.

Đích thiết kế là **idempotent processing**: khi nhận lại cùng một business event, hệ thống tạo kết quả tương đương lần xử lý hợp lệ đầu tiên, hoặc nhận ra đây là duplicate và xử lý an toàn, kể cả khi không biết kết quả request Cassandra trước đó.

Trong module **SPRING_INTEGRATION_ADAPTERS**, người học kết nối hệ thống ngoài với Spring Integration qua inbound/outbound adapter, gateway, poller và `MessageChannel`, thực hành các nguồn file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, cùng message contract, lỗi và vòng đời kết nối. Bài thuộc chương **Adapter Cassandra**, tập trung thiết kế khả năng thực thi lại an toàn trong mọi đường đi tới Cassandra.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **CQL idempotence**, **business idempotency** và **end-to-end effectively-once processing**.
2. Hiểu Cassandra `INSERT`/`UPDATE` có **upsert semantics**, timestamp-based conflict resolution, TTL và các thao tác **không idempotent** như counter increment/list prepend.
3. Tạo business event identity và Cassandra primary key **ổn định qua retry, replay, backfill và deploy**.
4. Phát hiện **duplicate cùng nội dung** khác với **conflicting duplicate cùng ID nhưng khác payload**.
5. So sánh unconditional upsert, `INSERT ... IF NOT EXISTS`/LWT, idempotency inbox và version-guarded state update.
6. Thiết kế ghi nhiều bảng/partitions mà không giả định có SQL-style atomic transaction hoặc giao dịch Cassandra–JMS/Kafka.
7. Viết Spring Data Cassandra/Java Driver/Spring Integration Java DSL với entity mapping, statement options, retry và acknowledgment boundary rõ ràng.
8. Kiểm thử timeout có kết quả không chắc, nguồn redelivery, concurrent writers, TTL expiry, migration và reconciliation.

## 2. Ba cấp độ idempotency phải được phân biệt

| Cấp độ | Ví dụ | Bảo đảm mong muốn | Không tự bảo đảm |
|---|---|---|---|
| **Statement-level** | `INSERT` cùng full primary key và same values | Thực thi lại không thêm business row mới | Không chống conflicting payload và side effects ngoài Cassandra |
| **Event-level** | `OrderPaid(evt-10001)` được nhận 10 lần | Cùng event chỉ được chấp nhận như một sự kiện hợp lệ; duplicate được nhận diện | Không tự khiến nhiều tables cùng commit |
| **Workflow-level** | Ghi Cassandra + phát email + commit JMS | Sau crash/retry, workflow có thể tiếp tục mà không tạo side effects sai | Không có transaction nguyên tử chung nếu từng hệ thống không hỗ trợ |

**Idempotent** không đồng nghĩa “chỉ thực thi đúng một lần”. Một SQL/CQL operation có thể **được gửi 5 lần**, nhưng bảng vẫn có **một row mang cùng primary key**. Đó là **at-least-once execution với idempotent effects**, không phải exactly-once execution.

~~~mermaid
flowchart TD
    S["Broker giao evt-10001"] --> F["Spring Integration flow"]
    F --> K["Derive stable event key"]
    K --> C["Cassandra write"]
    C --> A{"Có ACK Cassandra?"}
    A -->|"Có"| B["Commit/ack broker theo policy"]
    A -->|"Timeout / không rõ"| R["Retry có giới hạn / reconcile"]
    R --> F
    B -. "Broker commit fail/crash" .-> S
~~~

### 2.1. Một bản ghi không đồng nghĩa một side effect

Một consumer có thể:

~~~text
1. INSERT evt-10001 vào Cassandra (idempotent upsert)
2. POST /charge đến payment provider
3. Gửi email xác nhận
4. Commit JMS/Kafka source
~~~

Lần replay, bước 1 có thể tạo cùng row nhưng bước 2 hoặc 3 có thể chạy **lần nữa**. Do đó phải có **idempotency key riêng tại mỗi external side-effect boundary**, hoặc dùng outbox/inbox và workflow state có khả năng phục hồi.

### 2.2. "Exactly once" phải chỉ rõ phạm vi

Các cụm từ dễ nhầm:

- **At-most-once delivery:** có thể mất message, nhưng không chủ động giao lại.
- **At-least-once delivery:** có thể giao lặp, nhưng có cơ chế phát lại khi chưa xác nhận.
- **Exactly-once processing effect:** mục tiêu là hiệu ứng nghiệp vụ tương đương một lần, thường đạt được nhờ idempotency/deduplication/reconciliation.
- **Exactly-once transaction trên broker:** chỉ bao gồm những resources/protocol mà broker framework thực sự quản lý, không tự bao gồm Cassandra.

Không hứa **exactly-once end-to-end** chỉ vì Cassandra có LWT, JMS session transacted hoặc Kafka transactional producer.

## 3. Cassandra INSERT là upsert, không phải INSERT UNIQUE của SQL

Một table thử nghiệm:

~~~sql
CREATE KEYSPACE IF NOT EXISTS shop_integration
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS shop_integration.events_by_id (
    tenant_id text,
    event_id text,
    order_id text,
    event_type text,
    payload_sha256 text,
    occurred_at timestamp,
    payload_json text,
    PRIMARY KEY ((tenant_id, event_id))
);
~~~

**Môi trường:** ví dụ `dc1:3` chỉ dùng khi có datacenter tên `dc1` và tối thiểu ba Cassandra replica nodes phù hợp. Với lab một node, tạo keyspace RF=1 và **không** dùng nó để chứng minh quorum/failover.

Table dùng **composite partition key `(tenant_id, event_id)`**. Mỗi business event có định danh duy nhất **trong phạm vi tenant**. Đây là thiết kế phục vụ truy vấn theo event identity. Nếu cần timeline theo order/month, dùng thêm bảng theo query pattern thay vì `ALLOW FILTERING` quét toàn table.

### 3.1. Unconditional INSERT hai lần

~~~sql
INSERT INTO shop_integration.events_by_id
    (tenant_id, event_id, order_id, event_type, payload_sha256,
     occurred_at, payload_json)
VALUES
    ('tenant-42', 'evt-10001', 'ORD-501', 'OrderPaid', 'hash-A',
     '2026-11-23T03:00:00Z', '{"eventId":"evt-10001"}');

-- Cùng full PK, cùng giá trị:
INSERT INTO shop_integration.events_by_id
    (tenant_id, event_id, order_id, event_type, payload_sha256,
     occurred_at, payload_json)
VALUES
    ('tenant-42', 'evt-10001', 'ORD-501', 'OrderPaid', 'hash-A',
     '2026-11-23T03:00:00Z', '{"eventId":"evt-10001"}');
~~~

Kết quả là **một logical row theo full primary key**. Nhưng vì `INSERT` là upsert, Cassandra **không trả một boolean “đây là lần đầu”** cho unconditional insert. Nếu lần sau dùng cùng key mà `payload_sha256='hash-B'`, các regular columns có thể bị ghi đè theo **write timestamp reconciliation**.

### 3.2. Một primary key phải chứa đầy đủ định danh

| Identity ở producer | Cassandra PK | Hệ quả |
|---|---|---|
| `eventId` unique toàn hệ thống | `event_id` | Tra cứu đơn giản nhưng phải thật sự global |
| `eventId` chỉ unique trong tenant | `(tenant_id,event_id)` | Không xung đột giữa tenants |
| `eventId` unique trong order | `(tenant_id,order_id,event_id)` | Query/lookup phải biết đủ các phần key |
| Consumer tạo UUID mới mỗi attempt | PK khác qua replay | **Không idempotent** |
| Kafka offset làm PK duy nhất | Tùy topic/partition/replay path | Không thể mặc định là business identity |

**Ưu tiên business event ID do producer tạo một lần tại thời điểm sự kiện hình thành**, đưa theo message và giữ qua mọi retry. Nếu producer không có ID ổn định, phải xác định một **deterministic identity strategy** từ immutable source fields và collision/uniqueness rules, không dùng giờ xử lý hiện tại.

### 3.3. Upsert an toàn có điều kiện

Ghi cùng key và values có thể xem là idempotent khi:

1. Event body đã canonicalize và bất biến.
2. Tất cả primary-key components ổn định.
3. Không có side effect ngoài Cassandra trong operation lặp.
4. Mutation timestamp/TTL semantics không tạo thay đổi ngoài ý muốn.
5. Không có concurrent writers cùng key với payload khác mà thứ tự write làm sai business invariant.

Đó là **điều kiện cần kiểm chứng**, không phải mặc định của mọi `INSERT`.

## 4. Những thao tác Cassandra thường không idempotent

| CQL/business action | Lặp có an toàn? | Nguyên nhân |
|---|---|---|
| `SELECT` theo key | Thường an toàn để gửi lại | Kết quả có thể đổi do concurrent writes |
| `INSERT` cùng PK, values và timestamp policy bất biến | Thường an toàn theo row effect | Phải kiểm tra TTL/concurrency |
| `UPDATE SET state='PAID'` | Có điều kiện | Concurrent outdated writes có thể ghi đè |
| `UPDATE list_col = ['x'] + list_col` | **Không** | Prepend lặp tạo nhiều phần tử |
| `UPDATE counter_col = counter_col + 1` | **Không** | Counter tăng lại khi retry |
| `INSERT ... IF NOT EXISTS` | Có điều kiện | LWT trả applied=false khi row đã có; cần so payload |
| `DELETE` cùng PK | Có điều kiện | Tombstone/timestamp/concurrent writes cần xem xét |
| Multi-partition BATCH | Phụ thuộc **mọi mutation** | Logged batch không tạo SQL transaction |
| Gửi tiền/email/HTTP callback | Không tự an toàn | Cần idempotency key tại downstream |

### 4.1. Counter và list append là phản ví dụ rõ ràng

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_counters (
    order_id text PRIMARY KEY,
    processed_events counter
);

UPDATE shop_integration.order_counters
SET processed_events = processed_events + 1
WHERE order_id = 'ORD-501';
~~~

Nếu coordinator áp dụng `+1` nhưng response bị mất, client retry, counter có thể tăng **hai lần**. Không gắn `setIdempotent(true)` cho câu này chỉ để Java Driver retry thuận tiện.

Với CQL list append/prepend, thêm cùng element có thể tạo duplicate list entries; dùng `set` có semantics khác nhưng vẫn cần hiểu concurrent updates và business dedup.

### 4.2. UPSERT không phải "first-write wins"

Khi hai nguồn gửi:

~~~text
Source A: tenant-42 / evt-10001 / payload hash-A
Source B: tenant-42 / evt-10001 / payload hash-B
~~~

Unconditional upsert có thể để giá trị của mutation có Cassandra **write timestamp thắng** tồn tại trong row, không đảm bảo payload đầu tiên sẽ được giữ. Nếu cần **accept-once immutable event**, phải có conditional insert/LWT hoặc một idempotency claim protocol có kiểm tra xung đột.

## 5. Tạo event identity và partition key ổn định

### 5.1. Khóa được quyết định trước lúc đưa message lên broker

Một hợp đồng sự kiện ví dụ:

~~~json
{
  "tenantId": "tenant-42",
  "eventId": "evt-10001",
  "orderId": "ORD-501",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T03:00:00.123Z",
  "amountMinor": 150000,
  "currency": "VND"
}
~~~

**`eventId` được tạo tại nơi phát sinh sự kiện**, không sinh mới trong Cassandra consumer. Nếu producer retry publish, nó dùng lại **cùng eventId**. Source message có thể mang JMS message ID hoặc Kafka offset riêng, nhưng đó là transport coordinates, không tự trở thành business event ID.

### 5.2. Quy tắc giữ danh tính qua từng tầng

| Tầng | Phải bảo toàn | Không nên làm |
|---|---|---|
| Producer | `tenantId` xác thực, `eventId`, `occurredAt`, event version | Tạo ID mới khi publish retry |
| JMS/Kafka message | Business ID + immutable payload/headers đã kiểm soát | Chỉ dùng `JMSMessageID` hoặc offset làm event ID nếu chưa có contract |
| Spring Integration Transformer | Canonical event fields và deterministic key | Thêm `UUID.randomUUID()` khi mapper chạy lại |
| Cassandra entity | Full PK theo CQL schema | Chuyển tenant/bucket/shard dựa vào giờ consumer chạy |
| Retry/reconciliation | Same event identity + payload fingerprint | Sinh lại giá trị khác khi driver timeout |
| Backfill/migration | Mapping version + original event timestamp | Áp thuật toán shard mới cho dữ liệu cũ mà không version hóa |

### 5.3. Composite partition key và phân vùng theo thời gian

Ví dụ bảng timeline:

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.events_by_order_month (
    tenant_id text,
    order_id text,
    bucket_month text,
    occurred_at timestamp,
    event_id text,
    event_type text,
    payload_sha256 text,
    PRIMARY KEY (
        (tenant_id, order_id, bucket_month),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

Partition key là **(tenant_id, order_id, bucket_month)**; clustering columns là **occurred_at, event_id**. Nếu retry dùng giờ hiện tại để tính bucket, cùng business event có thể được đưa vào partition khác.

~~~java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;

public final class StableEventKeys {
    private static final DateTimeFormatter MONTH =
            DateTimeFormatter.ofPattern("uuuu-MM");

    private StableEventKeys() {}

    public static Instant canonicalTime(Instant original) {
        if (original == null) {
            throw new IllegalArgumentException("occurredAt missing");
        }
        // Cassandra CQL timestamp lưu ở độ chính xác millisecond.
        return original.truncatedTo(ChronoUnit.MILLIS);
    }

    public static String utcMonth(Instant occurredAt) {
        return MONTH.format(
                canonicalTime(occurredAt).atOffset(ZoneOffset.UTC));
    }
}
~~~

Với `occurredAt=2026-11-30T23:59:59.999Z`, bucket luôn là `2026-11` dù consumer replay ngày 1 tháng 12 hoặc tháng 1 năm sau. Dùng **UTC và canonical precision** thống nhất giữa các services.

### 5.4. Stable sharding

Nếu table có `shard` để giảm hot partition, shard phải được tính bằng **thuật toán ổn định từ event identity hoặc business discriminator**. Không dùng `ThreadLocalRandom` hoặc một Kafka partition index có thể đổi khi topic mở rộng.

Nếu chuyển từ 16 shards sang 32 shards:

- Công thức `hash(eventId) mod 16` và `mod 32` cho kết quả khác với một số events cũ.
- Dữ liệu cũ **không tự chuyển partition** khi code đổi.
- Cần versioned shard scheme, dual-read/backfill hoặc migration riêng.
- Idempotency của replay chỉ giữ được khi nó chọn **cùng key version** với lần ghi gốc.

## 6. Tính payload fingerprint để phát hiện conflicting duplicate

Idempotency key chỉ nói **hai messages cùng danh tính**. Nó không nói **nội dung có giống nhau**. Hai payload khác nhau mang cùng `eventId` thường là lỗi contract hoặc dấu hiệu ghi đè ngoài ý muốn.

### 6.1. Hash raw JSON có thể gây false conflict

Hai JSON sau diễn đạt cùng dữ liệu nhưng bytes khác:

~~~json
{"eventId":"evt-10001","amountMinor":150000}
~~~

~~~json
{ "amountMinor": 150000, "eventId": "evt-10001" }
~~~

Hash `SHA-256` của **raw bytes** sẽ khác vì khoảng trắng và thứ tự fields. Vì vậy nếu muốn kiểm tra **semantic duplicate**, cần **canonical payload format** được version hóa, không chỉ chạy hash trên raw JSON tùy producer serializer.

### 6.2. DTO canonical để lưu fingerprint

~~~java
import java.time.Instant;

public record OrderPaidEvent(
        String tenantId,
        String eventId,
        String orderId,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        long amountMinor,
        String currency) {}
~~~

Một cách tránh khác biệt thứ tự JSON là cập nhật digest bằng các trường **theo thứ tự, có length prefix**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class EventFingerprint {

    private EventFingerprint() {}

    public static String sha256(OrderPaidEvent e) {
        if (e == null || e.tenantId() == null || e.eventId() == null
                || e.orderId() == null || e.eventType() == null
                || e.currency() == null || e.occurredAt() == null
                || e.amountMinor() <= 0 || e.schemaVersion() != 1) {
            throw new IllegalArgumentException("Invalid OrderPaidEvent");
        }

        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            update(digest, "OrderPaidEvent:fingerprint:v1");
            update(digest, e.tenantId());
            update(digest, e.eventId());
            update(digest, e.orderId());
            update(digest, e.eventType());
            update(digest, Integer.toString(e.schemaVersion()));
            update(digest, StableEventKeys.canonicalTime(
                    e.occurredAt()).toString());
            update(digest, Long.toString(e.amountMinor()));
            update(digest, e.currency());
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    private static void update(MessageDigest digest, String value) {
        byte[] data = value.getBytes(StandardCharsets.UTF_8);
        digest.update(ByteBuffer.allocate(4)
                .putInt(data.length).array());
        digest.update(data);
    }
}
~~~

Đây là **một canonical encoding có version cố định**, không phải “chuẩn chung” cho mọi loại event. Bổ sung/đổi field phải **tăng version thuật toán** hoặc có compatibility rule. Không bỏ các fields ảnh hưởng nghiệp vụ khỏi fingerprint (như amount, currency, orderId) chỉ vì muốn giảm false conflict. Với Java `String`, cũng cần quy định Unicode normalization nếu nhiều producer/ngôn ngữ có thể tạo cách biểu diễn khác nhau.

### 6.3. Quy tắc xử lý duplicate

| Tình huống | `tenantId + eventId` | Fingerprint | Quyết định |
|---|---|---|---|
| Event mới | Chưa tồn tại | Bất kỳ hợp lệ | Có thể insert/claim |
| Redelivery giống hệt | Đã tồn tại | **Bằng** | Duplicate hợp lệ, không làm side effect lặp |
| Producer dùng lại ID cho payload mới | Đã tồn tại | **Khác** | Conflict, quarantine/alert |
| Same eventId ở tenant khác | **Khóa khác** | Có thể bằng/khác | Xử lý theo tenant scope, không trộn dữ liệu |
| Retry đổi thuật toán hash | Khóa giống | Có thể khác giả | Cần fingerprint version/compatibility |

**Hash không thay quyền truy cập**: service phải xác thực `tenantId` và message provenance trước khi đưa vào lookup/upsert. Chỉ dựa vào eventId do HTTP client gửi không đủ để quyết định tenant nào được đọc/ghi.

## 7. TTL, write timestamp và last-write-wins: các bẫy của "upsert idempotent"

### 7.1. TTL tính từ lần ghi, nên retry có thể kéo dài vòng đời

~~~sql
INSERT INTO shop_integration.events_by_id
    (tenant_id, event_id, order_id, event_type, payload_sha256)
VALUES
    ('tenant-42', 'evt-10001', 'ORD-501', 'OrderPaid', 'hash-A')
USING TTL 86400;
~~~

TTL 86.400 giây được gắn vào các giá trị cell được ghi. Nếu client gửi lại cùng statement sau một giờ, **expiry có thể bị đẩy lùi** cho những cells được ghi lại, bởi Cassandra tính TTL tương ứng write thời điểm mới. Vì thế “same key/same values” chưa chắc là **temporal idempotency**.

Đừng nhầm:

| Thuộc tính | Ý nghĩa |
|---|---|
| Cassandra `USING TTL 86400` | Thời gian dữ liệu còn sống sau write |
| Cassandra `USING TIMESTAMP n` | Write timestamp (microseconds), phục vụ reconciliation khi xung đột |
| Java Driver `setTimeout(Duration)` | Client request deadline |
| JMS message time-to-live | Broker retention của message |
| Business `occurredAt` | Mốc sự kiện trong hợp đồng |
| Event retention deadline | Chính sách nghiệp vụ về vòng đời event |

**Chính sách hợp lý** phụ thuộc use case: với event ledger đòi dedup lâu dài, cân nhắc **không TTL** hoặc TTL dài hơn mọi cửa sổ replay/backfill. Nếu cần TTL có thời điểm hết hạn nghiệp vụ cố định, phải thiết kế và kiểm thử quy tắc tính remaining TTL, giới hạn sai lệch giây và write timestamp; không giả định TTL tương đối tự đảm bảo expiry tuyệt đối.

### 7.2. Write timestamp mới có thể thắng mutation cũ

Theo Cassandra Java Driver 4.x, write timestamp có thể đến từ `USING TIMESTAMP`, `Statement.setQueryTimestamp(...)`, driver timestamp generator (mặc định có tính monotonic trong session) hoặc server. Vì vậy **hai lần retry cùng CQL text không tự có cùng timestamp**.

~~~text
Write A  t=1000: status=PAID
Write B  t=1200: status=CANCELLED
Replay A t=1300: status=PAID

Nếu không có version guard, replay A có thể ghi lùi
trạng thái từ CANCELLED về PAID.
~~~

Trường hợp event log immutable append-by-ID và state snapshot là **hai bài toán khác nhau**:

- **Event log:** giữ rows theo `eventId`, không ghi đè payload đã được chấp nhận.
- **Current state:** áp dụng theo `aggregateVersion`/compare-and-set hoặc protocol ordering có fencing, không chỉ last-write-wins ngầm.

### 7.3. Có nên đặt timestamp tường minh giống nhau qua retry?

Trong regular CQL, có thể cấu hình timestamp:

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement statement = SimpleStatement.builder(
        "INSERT INTO shop_integration.events_by_id "
        + "(tenant_id, event_id, order_id, event_type, payload_sha256) "
        + "VALUES (?, ?, ?, ?, ?)")
        .addPositionalValues(
                "tenant-42", "evt-10001", "ORD-501", "OrderPaid", "hash-A")
        .setQueryTimestamp(1_763_881_200_123_456L) // ví dụ microseconds
        .build();
~~~

Giá trị trên chỉ minh họa **microseconds từ Unix epoch**, không phải business `occurredAt` tính millisecond. Nếu cần repeatable timestamp cho event, nó phải thuộc một **timestamp policy được định nghĩa rõ** và được lưu/khôi phục ổn định. Tuy nhiên, đặt cùng timestamp không tự bảo vệ concurrent conflicting writes, delete/tombstone, TTL hoặc các điều kiện nghiệp vụ. Với LWT conditional statements, **không được gắn custom client write timestamp** như regular statements.

**Lưu ý:** driver timestamp generator mặc định có khả năng monotonic tại session; ứng dụng nhiều replicas/hosts không có một đồng hồ tổng thể bảo đảm business event ordering. Dựa vào LWW để thực thi state machine thường không phù hợp.

### 7.4. Null, UNSET và partial update

Trong Cassandra, gửi `NULL` cho column regular thường có semantics xóa/tombstone, còn `UNSET` trong driver bind có thể bỏ qua column đó. Nếu retry một PATCH message thiếu field nhưng mapper biến thành explicit null, nó có thể xóa dữ liệu.

Tách rõ:

1. Field **missing** trong event/patch.
2. Field **explicit null** có ý nghĩa xóa.
3. Field **non-null** cần cập nhật.

Spring Data Cassandra entity insert, update và các `WriteOptions` có quy tắc null khác nhau theo API/version. Không dùng một DTO có mọi field nullable rồi `update(entity)` với kỳ vọng framework tự hiểu “không đổi” ở mọi trường hợp.

## 8. Chọn chiến lược idempotency theo invariant nghiệp vụ

| Chiến lược | Phù hợp nhất | Bảo đảm chính | Đánh đổi |
|---|---|---|---|
| **Deterministic upsert** | Immutable event log, key không tái sử dụng | Same PK không tạo row mới | Upsert có thể ghi đè conflicting payload |
| **LWT `INSERT IF NOT EXISTS`** | First-write wins, phải phát hiện duplicate/conflict | Một conditional claim/insert tại Cassandra | Consensus latency, throughput thấp hơn |
| **Optimistic version guard** | Current state cập nhật theo version | Chặn stale/out-of-order state update | CAS contention, `applied=false` cần xử lý |
| **Durable inbox với state machine** | Workflow cần tiếp tục qua crash | Theo dõi PENDING/COMPLETED, claim và replay | Phải xây recovery/fencing |
| **Outbox ở nguồn transactional** | Phát event đáng tin cậy từ một source of truth | Gắn publish với transaction của nguồn nơi hỗ trợ | Không tự atomically commit Cassandra đích |
| **External idempotency key** | Payment/email/HTTP side effect | Downstream nhận diện request lặp | Phụ thuộc contract downstream |
| **Reconciliation projection** | Ghi nhiều Cassandra tables | Sửa thiếu sót khi một write thành công, write khác lỗi | Eventual consistency, giám sát/backfill |

### 8.1. Quyết định đầu tiên: cần dedup hay chỉ upsert an toàn?

Với immutable event history:

- Nếu consumer có **một writer có thẩm quyền**, eventId không bao giờ tái sử dụng và chỉ cần row cuối cùng đúng, **deterministic upsert** có thể đủ.
- Nếu có nhiều producers cùng gửi eventId, cần chứng minh **payload đầu tiên không thể bị thay** và phát hiện conflicting duplicates, cân nhắc **LWT conditional insert**.
- Nếu một event kéo theo nhiều side effects/steps, cần workflow state/inbox/reconciliation, không chỉ LWT một row.

Không áp `IF NOT EXISTS` cho mọi INSERT vô điều kiện: Cassandra LWT tốn thêm vòng consensus, tăng latency và contention, đặc biệt với hot keys.

## 9. Conditional INSERT với Cassandra LWT

`INSERT ... IF NOT EXISTS` cho phép bảo vệ điều kiện **row chưa tồn tại** trước khi ghi:

~~~sql
INSERT INTO shop_integration.events_by_id
    (tenant_id, event_id, order_id, event_type,
     payload_sha256, occurred_at, payload_json)
VALUES
    ('tenant-42', 'evt-10001', 'ORD-501', 'OrderPaid',
     'hash-A', '2026-11-23T03:00:00.123Z', '{"eventId":"evt-10001"}')
IF NOT EXISTS;
~~~

Một LWT dùng Cassandra consensus protocol cho conditional write (Paxos và các tối ưu theo version). Đây là cơ chế **compare-and-set trong phạm vi dữ liệu Cassandra hỗ trợ**, không phải giao dịch SQL nhiều hệ thống.

### 9.1. Ba kết quả cần phân biệt

| Kết quả | Ý nghĩa | Hành động |
|---|---|---|
| `[applied]=true` | Conditional insert được chấp nhận | Tiếp tục workflow và ack theo contract |
| `[applied]=false` | Row/condition không thỏa tại thời điểm kiểm tra | **Đọc row hiện có** và so fingerprint |
| Timeout/Unavailable | Caller không biết có applied hay chưa | Reconcile/retry có kiểm soát bằng same key |

**Rất quan trọng:** `applied=false` không phải automatic success vì “chắc là duplicate”. Cùng event ID **nhưng khác payload** phải được phân loại **CONFLICT**, không âm thầm bỏ qua.

### 9.2. Ví dụ Java Driver 4.x

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public final class FirstWriteWinsDao {
    private final CqlSession session;
    private final PreparedStatement insertIfAbsent;

    public FirstWriteWinsDao(CqlSession session) {
        this.session = session;
        this.insertIfAbsent = session.prepare(
                "INSERT INTO shop_integration.events_by_id "
                + "(tenant_id, event_id, order_id, event_type, "
                + "payload_sha256, occurred_at, payload_json) "
                + "VALUES (?, ?, ?, ?, ?, ?, ?) IF NOT EXISTS");
    }

    public boolean tryInsert(EventRowData row) {
        BoundStatement statement = insertIfAbsent.boundStatementBuilder()
                .setString(0, row.tenantId())
                .setString(1, row.eventId())
                .setString(2, row.orderId())
                .setString(3, row.eventType())
                .setString(4, row.payloadSha256())
                .setInstant(5, row.occurredAt())
                .setString(6, row.payloadJson())
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setSerialConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_SERIAL)
                .build();

        ResultSet result = session.execute(statement);
        return result.wasApplied();
    }
}

record EventRowData(
        String tenantId, String eventId, String orderId,
        String eventType, String payloadSha256,
        java.time.Instant occurredAt, String payloadJson) {}
~~~

Đây là ví dụ **cho cluster test có local datacenter và replication topology phù hợp**. `LOCAL_QUORUM` là regular consistency, `LOCAL_SERIAL` là serial consistency của LWT; trong multi-DC phải cân nhắc tính nhất quán xuyên datacenters và yêu cầu nghiệp vụ. **Không gắn `setQueryTimestamp(...)` trên LWT**; driver/Cassandra không cho tùy ý điều khiển timestamp như regular writes.

### 9.3. Khi applied=false, phải so hàng cũ

~~~java
PreparedStatement read = session.prepare(
        "SELECT payload_sha256, event_type, order_id "
        + "FROM shop_integration.events_by_id "
        + "WHERE tenant_id = ? AND event_id = ?");

BoundStatement q = read.boundStatementBuilder()
        .setString(0, incoming.tenantId())
        .setString(1, incoming.eventId())
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .build();

var existing = session.execute(q).one();
if (existing == null) {
    // Không khẳng định "absent" khi topology/consistency chưa ổn định;
    // trả kết quả chưa chắc hoặc lên lịch reconciliation.
    throw new IllegalStateException("Cannot reconcile existing row");
}

boolean same = incoming.payloadSha256().equals(
        existing.getString("payload_sha256"));
if (!same) {
    throw new IllegalStateException("Conflicting event ID");
}
// Same fingerprint: duplicate hợp lệ, nếu các downstream effects
// cũng đã được hoàn tất/được bảo đảm replay an toàn.
~~~

Đoạn này là **fragment** trong DAO đã có `session`, `incoming` và compiled dependencies. So sánh thêm event schema version/algorithm version nếu cùng ID có thể đến qua nhiều phiên bản message. **Một duplicate trong event table không chứng minh các projection hoặc side effects đã hoàn tất**; phần inbox/recovery ở dưới xử lý khoảng trống đó.

### 9.4. Khi nào nên dùng LWT?

Chọn LWT khi:

- Nhiều concurrent writers có thể tranh chấp cùng event identity.
- Phải thực hiện chính sách **first-write wins** ở một row.
- Cần compare-and-set cho state version.

Không chọn LWT nếu chỉ muốn tăng throughput. Bản chất consensus khiến nó **đắt hơn** regular insert và có thể tạo điểm nghẽn trên hot partition. Dùng **đúng invariant** thay vì trang trí mọi query bằng `IF NOT EXISTS`.

## 10. Durable inbox: ngăn lặp và phục hồi công việc dở dang

Một **idempotency inbox** lưu danh tính event và trạng thái xử lý để các lần delivery có thể **tiếp tục công việc** thay vì chỉ “bỏ qua nếu đã từng thấy ID”. Đây là khác biệt lớn giữa **deduplication** và **workflow recovery**.

### 10.1. Tại sao claim-only là chưa đủ?

Xét quy trình sai:

~~~text
1. INSERT inbox(evt-10001, status=SEEN) IF NOT EXISTS -> applied=true
2. JVM crash
3. Broker redeliver evt-10001
4. INSERT IF NOT EXISTS -> applied=false
5. App: "duplicate" -> ack và bỏ qua

Kết quả: sự kiện đã đánh dấu SEEN nhưng chưa ghi projection/side effect.
~~~

Không coi `applied=false` là lý do **bỏ qua toàn workflow**. Cần phân biệt:

| Trạng thái inbox | Ý nghĩa | Delivery/recovery xử lý |
|---|---|---|
| **ABSENT** | Chưa thấy event | Có thể claim bằng LWT |
| **PENDING** | Đã tiếp nhận nhưng chưa chứng minh mọi effects hoàn tất | Kiểm tra owner/lease hoặc enqueue retry có kiểm soát |
| **COMPLETED** | Các business steps theo contract đã hoàn tất | Duplicate cùng fingerprint có thể ack |
| **CONFLICT** | Same ID, payload khác/contract sai | Quarantine/alert, không tự ghi đè |
| **UNKNOWN** | Timeout hoặc đọc inbox thất bại | Defer/reconcile, không coi là completed |

### 10.2. Schema inbox minh họa

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.event_inbox (
    tenant_id text,
    event_id text,
    payload_sha256 text,
    state text,
    owner_token text,
    lease_version bigint,
    lease_until timestamp,
    updated_at timestamp,
    PRIMARY KEY ((tenant_id, event_id))
);
~~~

Schema này **tối ưu lookup theo event ID**, không cho phép quét hiệu quả tất cả rows `PENDING` chỉ với `WHERE state='PENDING'`. Nếu hệ thống cần worker tìm pending jobs, phải có **durable queue/source replay** hoặc thiết kế **bảng index theo time/status** chuyên dụng và reconciliation. Không thêm `ALLOW FILTERING` trên toàn bảng như giải pháp scheduler production.

### 10.3. Claim một event mới

~~~sql
INSERT INTO shop_integration.event_inbox
    (tenant_id, event_id, payload_sha256,
     state, owner_token, lease_version, lease_until, updated_at)
VALUES
    ('tenant-42', 'evt-10001', 'hash-A',
     'PENDING', 'worker-1:claim-abc', 0,
     '2026-11-23T03:05:00Z', '2026-11-23T03:00:00Z')
IF NOT EXISTS;
~~~

Nếu applied=false, **đọc bản ghi tồn tại**, kiểm tra fingerprint và state:

- Same fingerprint + COMPLETED → duplicate hợp lệ.
- Same fingerprint + PENDING → đã nhận nhưng **chưa hoàn tất**, cần recovery/lease policy.
- Different fingerprint → conflict.
- Timeout đọc/claim → trạng thái chưa rõ; defer/reconcile.

### 10.4. State machine an toàn hơn claim-only

~~~mermaid
stateDiagram-v2
    [*] --> ABSENT
    ABSENT --> PENDING: LWT claim new event
    PENDING --> PENDING: retry/recover incomplete work
    PENDING --> COMPLETED: verify effects then conditional finalize
    PENDING --> CONFLICT: same ID, different fingerprint
    COMPLETED --> COMPLETED: same event duplicate -> ACK
    COMPLETED --> CONFLICT: same ID, different payload
~~~

Một phương án:

1. Nhận event, validate identity và fingerprint.
2. LWT claim `PENDING` hoặc đối chiếu existing row.
3. Ghi business event/projections/side effects bằng **deterministic IDs**.
4. Nếu mọi bước cần thiết đã được xác nhận hoặc có durable recovery policy, chuyển `PENDING → COMPLETED` bằng conditional update.
5. Chỉ commit/ack nguồn khi **tiêu chí hoàn tất hoặc durable handoff** của business contract đạt.
6. Sau crash, worker/source replay đọc PENDING và tiếp tục **bước còn thiếu**.

### 10.5. Chuyển trạng thái bằng CAS

~~~sql
UPDATE shop_integration.event_inbox
SET state = 'COMPLETED',
    updated_at = '2026-11-23T03:01:00Z'
WHERE tenant_id = 'tenant-42'
  AND event_id = 'evt-10001'
IF state = 'PENDING'
   AND payload_sha256 = 'hash-A';
~~~

Với nhiều consumers, `IF state='PENDING'` **chưa đủ** ngăn hai workers cùng làm side effect trước khi finalize. Nên quản lý **owner token, lease_version/lease_until, conditional claim và fencing**; chỉ worker có version hợp lệ mới được chuyển state. Tuy nhiên, **fencing Cassandra không ngăn được một HTTP/payment provider đã nhận yêu cầu từ worker cũ** — external system cũng phải nhận idempotency token hoặc fencing protocol phù hợp.

### 10.6. Những chỗ recovery phải được thiết kế rõ

| Điểm crash | Trạng thái | Cách phục hồi |
|---|---|---|
| Trước LWT claim | ABSENT | Broker redelivery/producer retry |
| Sau claim, trước ghi business row | PENDING | Durable queue/source replay hoặc index/worker tìm PENDING |
| Sau business row, trước projection thứ hai | PENDING | Idempotent write projection thiếu |
| Sau mọi DB rows, trước mark COMPLETED | PENDING | Reconcile rồi finalize |
| Sau COMPLETED, trước JMS/Kafka commit | COMPLETED | Duplicate đọc inbox, không thực hiện side effects lại |
| Sau external HTTP success nhưng trước lưu completion | PENDING | Retry external call bằng **same downstream idempotency key** |

**Hạn chế cấu trúc:** trong Cassandra, một claim row, một projection row và một side effect HTTP là ba nguồn trạng thái khác nhau. Không có “commit tất cả” tự động. Inbox là **protocol phục hồi**, không phải phép màu biến nhiều tài nguyên thành một ACID transaction.

### 10.7. TTL của inbox và cửa sổ replay

Nếu inbox row hết TTL khi broker vẫn còn message cũ hoặc một backfill chạy sau nhiều tháng, same event có thể được claim **như mới** và side effects lặp. Cần giữ idempotency record ít nhất bằng **maximum redelivery + retention + backfill/reconciliation window**, thêm margin vận hành. Với một số event có rủi ro cao, nên **giữ record vô hạn hoặc archive durable identity**; nếu xóa/TTL vì pháp lý thì phải thiết kế cơ chế replay tương ứng.

**Không đếm số lần broker giao message rồi đoán đã qua replay window**: DLQ replay thủ công, restores và cross-system reprocessing có thể vượt lịch redelivery thông thường.

## 11. Current state theo aggregateVersion: chống ghi lùi khi replay muộn

Idempotent event log và correct **current state** không phải cùng một vấn đề. Một order có thể có events:

~~~text
OrderPaid(v2, eventId=evt-10002)
OrderCancelled(v3, eventId=evt-10003)

Retry muộn của v2 không được ghi state từ CANCELLED về PAID.
~~~

### 11.1. State table và conditional update

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_state (
    tenant_id text,
    order_id text,
    version bigint,
    state text,
    last_event_id text,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

Khởi tạo:

~~~sql
INSERT INTO shop_integration.order_state
    (tenant_id, order_id, version, state, last_event_id)
VALUES
    ('tenant-42', 'ORD-501', 1, 'CREATED', 'evt-10000')
IF NOT EXISTS;
~~~

Điều kiện chuyển từ v1 lên v2:

~~~sql
UPDATE shop_integration.order_state
SET version = 2, state = 'PAID', last_event_id = 'evt-10002'
WHERE tenant_id = 'tenant-42' AND order_id = 'ORD-501'
IF version = 1;
~~~

Nếu v2 đã applied, replay v2 sẽ trả `applied=false`. Đọc lại:

- `version=2, last_event_id=evt-10002` → retry duplicate hợp lệ.
- `version=3, state=CANCELLED` → v2 đã cũ, không ghi lùi.
- `version=2, last_event_id` khác → conflict/out-of-order, cần domain reconciliation.

### 11.2. Java Driver conditional statement

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement cas = SimpleStatement.builder(
        "UPDATE shop_integration.order_state "
        + "SET version = ?, state = ?, last_event_id = ? "
        + "WHERE tenant_id = ? AND order_id = ? IF version = ?")
        .addPositionalValues(
                2L, "PAID", "evt-10002", "tenant-42", "ORD-501", 1L)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
        .build();

boolean applied = session.execute(cas).wasApplied();
~~~

Khi có nhiều datacenters hoặc failover, **local serial consistency** cần đánh giá kỹ phạm vi và invariants. Nếu business đòi một thứ tự duy nhất toàn hệ thống, không chỉ chọn LOCAL_SERIAL vì latency mà bỏ qua cross-DC behavior.

### 11.3. Không đồng nhất ba loại version

| Giá trị | Vai trò |
|---|---|
| `schemaVersion` | Phiên bản JSON/serialization contract |
| `aggregateVersion` | Thứ tự domain state transition |
| `@Version` trên Spring Data entity | Optimistic locking/version của persistence entity |
| Cassandra write timestamp | Last-write-wins conflict resolution |
| Kafka offset | Vị trí record trong một topic partition |

Một event ở aggregate version 12 có thể mang schemaVersion 3; Cassandra timestamp/offset là tọa độ khác. Không dùng `Instant.now()` thay `aggregateVersion` để quyết định order state.

## 12. Ghi nhiều tables: không giả định một Cassandra BATCH là SQL transaction

Trong Cassandra, cùng business event có thể cần:

- `events_by_id` để tra cứu theo ID.
- `events_by_order_month` để hiển thị timeline.
- `order_state` để hiển thị trạng thái hiện tại.
- `event_inbox` để theo dõi tiến trình.

Một flow có thể:

~~~mermaid
flowchart LR
    A["Event evt-10002"] --> B["Claim / verify inbox"]
    B --> C["Upsert events_by_id"]
    C --> D["Upsert events_by_order_month"]
    D --> E["Conditional order_state"]
    E --> F["Finalize inbox"]
    F --> G["Ack nguồn"]
~~~

Nếu JVM crash sau C nhưng trước D, một bảng có row còn bảng kia thiếu. **Không được xử lý replay bằng cách nhìn inbox PENDING rồi bỏ qua**, cũng không được dựa vào một successful insert ở `events_by_id` như proof mọi projections đã hoàn tất.

### 12.1. Logged batch giúp gì?

~~~sql
BEGIN BATCH
    INSERT INTO shop_integration.events_by_id
        (tenant_id, event_id, order_id, event_type, payload_sha256)
    VALUES
        ('tenant-42','evt-10002','ORD-501','OrderPaid','hash-B');

    INSERT INTO shop_integration.events_by_order_month
        (tenant_id, order_id, bucket_month, occurred_at, event_id,
         event_type, payload_sha256)
    VALUES
        ('tenant-42','ORD-501','2026-11',
         '2026-11-23T03:01:00Z','evt-10002','OrderPaid','hash-B');
APPLY BATCH;
~~~

**LOGGED BATCH** (cú pháp `BEGIN BATCH` mặc định) cung cấp **batchlog recovery** để các mutations của batch được hoàn tất theo cơ chế Cassandra. Nhưng với **nhiều partitions**, một reader có thể **thấy row A trước row B** trong một khoảng thời gian. Không có isolation/snapshot transaction kiểu SQL, không gắn được atomic JMS/Kafka commit, và batch lớn nhiều partitions có overhead đáng kể.

### 12.2. Khi nào không nên batch?

Với hàng nghìn events độc lập thuộc nhiều partition keys, chọn **bounded asynchronous writes** thường phù hợp hơn multi-partition LOGGED batch khổng lồ. Với một business event có 2–3 mutations liên quan và thật sự cần completion recovery, có thể cân nhắc **batch nhỏ**. Nếu cần cross-resource exactly-once effects, vẫn phải có **idempotency/protocol/reconciliation**.

### 12.3. Reconciliation cho materialized views tự quản lý

Một routine sau khi crash:

1. Lấy lại business event từ durable source hoặc inbox có pending index.
2. Kiểm tra row `events_by_id` theo `tenantId,eventId`.
3. Nếu same fingerprint, đảm bảo projection `events_by_order_month` tồn tại theo **deterministic full PK**.
4. Kiểm tra `order_state` bằng version/event ID, không ghi đè bản mới hơn.
5. Đảm bảo side effects ngoài Cassandra thông qua idempotency key riêng.
6. Finalize inbox khi có chứng cứ completion.
7. Ghi metrics các repairs và conflicts; không silently delete dữ liệu sai.

**Đây là eventual repair**, không hứa mọi read liên-table thấy transaction snapshot ngay. Nếu client cần một invariant mạnh xuyên tables, xem lại cách gom dữ liệu theo **cùng Cassandra partition** hoặc chọn hệ thống giao dịch phù hợp hơn.

## 13. Spring Data Cassandra: entity và idempotent upsert

### 13.1. Tạo composite key và entity

Với schema `events_by_id` ở mục 3:

~~~java
import java.io.Serializable;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public record EventKey(
        @PrimaryKeyColumn(
                name = "tenant_id", ordinal = 0,
                type = PrimaryKeyType.PARTITIONED)
        String tenantId,
        @PrimaryKeyColumn(
                name = "event_id", ordinal = 1,
                type = PrimaryKeyType.PARTITIONED)
        String eventId) implements Serializable {
}
~~~

~~~java
import java.time.Instant;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_id")
public record EventRow(
        @PrimaryKey EventKey key,
        @Column("order_id") String orderId,
        @Column("event_type") String eventType,
        @Column("payload_sha256") String payloadSha256,
        @Column("occurred_at") Instant occurredAt,
        @Column("payload_json") String payloadJson) {
}
~~~

`@PrimaryKeyClass` + `@PrimaryKeyColumn(PARTITIONED)` mô tả **hai thành phần Cassandra partition key**. Java record cho value equality; nếu dùng class thông thường, phải viết `equals/hashCode` chính xác. `@Table` và `@Column` giúp mapping rõ tên CQL, không phụ thuộc ngầm vào naming convention.

### 13.2. Mapper bảo toàn khóa qua replay

~~~java
import java.util.Objects;

public final class EventRowMapper {

    public EventRow toRow(
            OrderPaidEvent event,
            String canonicalPayloadJson) {
        Objects.requireNonNull(event, "event");
        Objects.requireNonNull(canonicalPayloadJson, "canonicalPayloadJson");

        if (event.tenantId() == null || event.tenantId().isBlank()
                || event.eventId() == null || event.eventId().isBlank()
                || event.orderId() == null || event.orderId().isBlank()
                || !"OrderPaid".equals(event.eventType())) {
            throw new IllegalArgumentException("Invalid event identity");
        }

        return new EventRow(
                new EventKey(event.tenantId(), event.eventId()),
                event.orderId(),
                event.eventType(),
                EventFingerprint.sha256(event),
                StableEventKeys.canonicalTime(event.occurredAt()),
                canonicalPayloadJson);
    }
}
~~~

`canonicalPayloadJson` phải được tạo bằng một serializer **có hợp đồng ổn định**. Nếu producer gửi raw JSON đổi whitespace/field order, không nên dùng nó làm canonical text rồi mặc định mỗi lần retry giống hệt. Có thể dùng một DTO serializer có version và golden tests cross-language, hoặc lưu riêng raw payload nhưng fingerprint theo canonical business fields.

### 13.3. Regular upsert với ReactiveCassandraOperations

~~~java
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import reactor.core.publisher.Mono;

public final class EventUpsertService {
    private final ReactiveCassandraOperations operations;

    public EventUpsertService(
            ReactiveCassandraOperations operations) {
        this.operations = operations;
    }

    public Mono<Void> write(EventRow row) {
        if (row == null || row.key() == null
                || row.key().tenantId() == null
                || row.key().eventId() == null) {
            return Mono.error(new IllegalArgumentException("Missing event key"));
        }
        return operations.insert(row).then();
    }
}
~~~

`ReactiveCassandraOperations.insert(...)` trả **reactive publisher**: tạo `Mono` không đồng nghĩa I/O đã chạy. Endpoint/subscriber phải subscribe và xử lý completion/error. Regular insert **không phát tín hiệu "duplicate"**; nếu app cần phân biệt new vs existing/conflict, dùng conditional strategy.

### 13.4. Đặt WriteOptions cho regular upsert

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.cql.WriteOptions;

@Bean
WriteOptions immutableEventWriteOptions() {
    return WriteOptions.builder()
            .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .timeout(Duration.ofSeconds(3))
            .idempotent(true)
            .build();
}
~~~

Giá trị trên là **lab sample**. `idempotent(true)` chỉ được dùng khi sự kiện thực sự immutable; không tự gắn flag cho `UPDATE counter +1` hay list append. `WriteOptions.timeout` là **client request timeout** qua driver, không phải Cassandra TTL, JMS redelivery window hay Spring gateway reply timeout.

## 14. Spring Data Cassandra: conditional insert và kiểm tra applied

Spring Data Cassandra hiện đại cung cấp `InsertOptions.withIfNotExists()` và `ReactiveCassandraOperations.insert(entity, InsertOptions)` trả `Mono<EntityWriteResult<T>>`, cho phép xem `wasApplied()`.

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.data.cassandra.core.InsertOptions;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public final class ConditionalEventStore {
    private final ReactiveCassandraOperations operations;
    private final InsertOptions options;

    public ConditionalEventStore(ReactiveCassandraOperations operations) {
        this.operations = operations;
        this.options = InsertOptions.builder()
                .withIfNotExists()
                .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .serialConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_SERIAL)
                .timeout(Duration.ofSeconds(5))
                .build();
    }

    public Mono<AcceptResult> accept(EventRow incoming) {
        if (incoming == null || incoming.key() == null
                || incoming.key().tenantId() == null
                || incoming.key().eventId() == null
                || incoming.payloadSha256() == null) {
            return Mono.error(new IllegalArgumentException(
                    "Incomplete event identity/fingerprint"));
        }

        return operations.insert(incoming, options)
                .flatMap(write -> {
                    if (write.wasApplied()) {
                        return Mono.just(AcceptResult.NEW);
                    }
                    return operations.selectOneById(
                                    incoming.key(), EventRow.class)
                            .switchIfEmpty(Mono.error(
                                    new IllegalStateException(
                                            "Existing row unavailable for reconciliation")))
                            .flatMap(existing -> {
                                if (incoming.payloadSha256().equals(
                                        existing.payloadSha256())) {
                                    return Mono.just(AcceptResult.DUPLICATE);
                                }
                                return Mono.error(new IllegalStateException(
                                        "Conflicting duplicate event ID"));
                            });
                });
    }
}

enum AcceptResult { NEW, DUPLICATE }
~~~

**Những điều ví dụ cố tình chưa làm**:

- Không trả HTTP status, commit JMS/Kafka hoặc phát side effects.
- Không đối soát các projection khác; `AcceptResult.DUPLICATE` chỉ có nghĩa **event row** đã khớp fingerprint.
- Không xử lý topology outage giữa failed LWT và read-back; timeout/error phải đi đến recovery.
- Không kiểm tra version của thuật toán fingerprint; production cần lưu/kiểm tra khi migration.
- Không có cross-DC/linearizability guarantee ngoài phạm vi Cassandra CL và serial consistency đã chọn.

Với Cassandra LWT, không gắn custom client write timestamp như regular INSERT. **LWT có thể trả `wasApplied=false` khi replay một event đã ghi trước đó**; đây không phải network error. Đoạn service xử lý trường hợp đó bằng read-back. Nếu ứng dụng cần hoàn tất workflow nhiều bước, tiếp tục theo **inbox state machine** (mục 10), không ack dựa vào mỗi kết quả DUPLICATE.

### 14.1. Khi dùng INSERT IF NOT EXISTS, không nên set query idempotent bừa

Driver `setIdempotent(true)` cho phép một số retries/speculative executions. Mặc dù conditional insert nhiều lần không tạo nhiều row cùng primary key, **semantic result** có thể đổi từ `applied=true` sang `applied=false` và những bước phía ứng dụng có thể phụ thuộc vào kết quả. Chỉ bật retry/metadata khi code đã định nghĩa cách **reconcile** LWT outcome và không làm sai side effects khi kết quả khác giữa attempts. Không coi tính idempotent của **row creation** và tính idempotent của **cả API call** là một.

## 15. Java Driver 4.x: đánh dấu statement idempotent đúng nghĩa

### 15.1. Prepared upsert

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

public final class EventPreparedWriter {
    private final CqlSession session;
    private final PreparedStatement insert;

    public EventPreparedWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
                "INSERT INTO shop_integration.events_by_id "
                + "(tenant_id, event_id, order_id, event_type, "
                + "payload_sha256, occurred_at, payload_json) "
                + "VALUES (?, ?, ?, ?, ?, ?, ?)");
    }

    public void upsert(EventRowData row) {
        BoundStatement statement = insert.boundStatementBuilder()
                .setString(0, row.tenantId())
                .setString(1, row.eventId())
                .setString(2, row.orderId())
                .setString(3, row.eventType())
                .setString(4, row.payloadSha256())
                .setInstant(5, row.occurredAt())
                .setString(6, row.payloadJson())
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setTimeout(Duration.ofSeconds(3))
                .setIdempotent(true)
                .build();

        session.execute(statement);
    }
}
~~~

`EventRowData` đã được định nghĩa ở mục 9. Prepared statements giúp tách **CQL syntax** khỏi values và có thể reuse trong DAO singleton. Mỗi incoming event tạo **BoundStatement** riêng; không dùng mutable builder global cho nhiều threads.

**Quan trọng:** `setIdempotent(true)` là metadata cho driver retry/speculative execution policy; nó **không** deduplicate JMS/Kafka, không chặn conflicting payload và không tự thêm `IF NOT EXISTS`.

### 15.2. Immutable statements

Trong Driver 4.x, statement setters trả **new statement**:

~~~java
// Sai: không sử dụng instance trả về.
statement.setIdempotent(true);

// Đúng:
statement = statement.setIdempotent(true);
~~~

Ví dụ là fragment khi `statement` là một `BoundStatement` biến có thể gán lại. Dùng `boundStatementBuilder()` như mục 15.1 giúp giảm lỗi quên kết quả setter.

### 15.3. Default retry và speculative execution

Theo tài liệu Driver 4.19:

- `basic.request.default-idempotence` mặc định `false`.
- `DefaultRetryPolicy` chỉ retry **một số lỗi chọn lọc** trong request budget; không retry mọi `WRITE_TIMEOUT`.
- Speculative executions mặc định tắt; nếu bật, chỉ sử dụng cho idempotent statements.
- Driver timeout bao gồm retries/speculative executions trong tổng client deadline.
- **Cancel client request không rollback Cassandra mutation đã gửi**.

Không bật `basic.request.default-idempotence=true` toàn cục nếu hệ có counters, list append, conditional results hoặc operation mang side effects không được thiết kế tương ứng.

## 16. Spring Integration Cassandra: từ message tới deterministic row

Spring Integration cung cấp `CassandraMessageHandler` dùng `ReactiveCassandraOperations` cho `INSERT`, `UPDATE`, `DELETE` và `STATEMENT`. Nó có thể làm **outbound channel adapter** một chiều hoặc **outbound gateway** có reply. Mặc định handler **asynchronous**; có thể bật chế độ chờ kết quả bằng `setAsync(false)` (Java DSL `endpoint.async(false)`).

### 16.1. Chuẩn bị mapper ở tầng ứng dụng

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

@Component
public final class OrderPaidRowTransformer {

    private final EventRowMapper rowMapper = new EventRowMapper();
    private final ObjectMapper objectMapper;

    public OrderPaidRowTransformer(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public EventRow map(OrderPaidEvent event) {
        try {
            // Hợp đồng serializer phải được ổn định/version hóa;
            // ObjectMapper của ứng dụng cần Java Time support.
            String canonicalJson = objectMapper.writeValueAsString(event);
            return rowMapper.toRow(event, canonicalJson);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "Cannot serialize OrderPaidEvent", ex);
        }
    }
}
~~~

Ví dụ dùng namespace **Jackson 2** (`com.fasterxml.jackson...`) của các project Spring Boot 3.x; nếu dự án dùng Jackson 3/Spring Boot 4, điều chỉnh API/namespace và ObjectMapper theo framework version. Đảm bảo Java Time serialization, property naming/order, null inclusion và canonical rules **ổn định giữa deployments**, đặc biệt nếu `payload_json` phải có cùng bytes qua replay. Fingerprint ở mục 6 đã định nghĩa một cách encode riêng để tránh lệ thuộc vào whitespace/thứ tự JSON.

### 16.2. Java DSL cho entity INSERT có idempotency

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.data.cassandra.core.cql.WriteOptions;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class CassandraEventFlowConfig {

    @Bean
    public IntegrationFlow immutableEventUpsert(
            ReactiveCassandraOperations operations,
            OrderPaidRowTransformer transformer,
            WriteOptions immutableEventWriteOptions) {

        return IntegrationFlow.from("validatedOrderPaidEvents")
                .transform(OrderPaidEvent.class, transformer::map)
                .handle(Cassandra.outboundChannelAdapter(
                                operations,
                                CassandraMessageHandler.Type.INSERT)
                        .writeOptions(immutableEventWriteOptions),
                        endpoint -> endpoint.async(false))
                .get();
    }
}
~~~

Flow nhận `Message<OrderPaidEvent>` **đã được validate và xác thực tenant** trước khi vào channel. `Transformer` tạo `EventRow` có `@Table`, `@PrimaryKey` rõ ràng. Adapter thực thi regular upsert với `WriteOptions`. Đây là **phương án idempotent upsert**; nó **không tự phát hiện conflicting duplicate** nếu hai messages có cùng ID nhưng khác payload. Nếu cần bảo đảm first-write wins và đối soát fingerprint, dùng service conditional ở mục 14 thay vì chỉ entity INSERT.

### 16.3. Nếu cần conditional result, đừng dùng one-way adapter rồi đoán kết quả

~~~text
Message<OrderPaidEvent>
   -> Transformer tạo EventRow
   -> ConditionalEventStore.accept(row)
   -> Mono<AcceptResult>
      -> NEW: tiếp tục workflow
      -> DUPLICATE: kiểm tra trạng thái workflow/inbox
      -> CONFLICT/DB error: quarantine/retry/reconcile
~~~

Trong cách này, **ứng dụng phải thực sự subscribe/await `Mono<AcceptResult>`** và nối success/error signal với request/reply hoặc source acknowledgment. Không chỉ gọi `accept(row)` rồi bỏ publisher. Nếu Spring Integration endpoint được chọn xử lý publisher bất đồng bộ, phải có đường propagate completion/error tương ứng; hãy kiểm thử với đúng phiên bản Spring Integration.

**LWT `applied=false` không phải exception.** Nó là kết quả condition. Một outbound adapter một chiều dùng `send(true)` không cho caller biết applied/duplicate/conflict. Khi caller cần quyết định theo `wasApplied()`, ưu tiên service/gateway có reply và contract rõ ràng.

### 16.4. Nếu dùng driver Statement từ Spring Integration

`Cassandra.outboundChannelAdapter(operations).statementFunction(message -> Statement<?>)` có thể tạo CQL statement đã bind đủ primary key, consistency, timeout, idempotency. Tuy nhiên, với `INSERT IF NOT EXISTS` cần kết quả `wasApplied()`, nên dùng **outbound gateway** hoặc service đọc return value; không dùng một adapter một chiều rồi bỏ kết quả điều kiện.

Nguyên tắc:

- **Entity mode:** payload `@Table` entity, Spring Data map columns.
- **Statement mode:** ứng dụng map values/statement, tự chịu trách nhiệm CQL/key/codec.
- **Ingest query mode:** payload matrix `List<List<?>>`, không phải một JSON String hay entity duy nhất.
- **Gateway/read:** cần biết Cassandra result hoặc LWT applied status.

### 16.5. Transformer không được tái tạo business ID

~~~java
// SAI — mỗi lần redelivery tạo một row key mới:
String eventId = java.util.UUID.randomUUID().toString();

// ĐÚNG — lấy từ event identity đã được tạo ở producer:
String eventId = event.eventId();
~~~

`eventId` lấy từ payload đã xác thực là **nguồn sự thật về định danh nghiệp vụ**, không phải một Spring message ID tự tạo khi qua transformer/channel.

## 17. JMS, Kafka, HTTP: đặt acknowledgment và retry sau đúng sự kiện hoàn tất

### 17.1. JMS transacted listener và đồng bộ completion

~~~mermaid
sequenceDiagram
    participant J as JMS Broker
    participant L as JMS listener
    participant M as DirectChannel / Transformer
    participant C as Cassandra handler sync
    participant D as Cassandra
    J->>L: Deliver evt-10001
    L->>M: Message<OrderPaidEvent>
    M->>C: Message<EventRow>
    C->>D: INSERT / LWT
    alt Operation success
        D-->>C: Completion
        C-->>L: Return
        L-->>J: Commit JMS theo policy
    else Error or unknown
        D-->>C: Timeout/error
        C-->>L: Exception
        L-->>J: Rollback theo policy
        J->>L: Redelivery evt-10001
    end
~~~

Khi listener container dùng JMS transaction và dòng xử lý **`DirectChannel` + handler sync**, một Cassandra exception có cơ hội propagate về listener trước commit; việc rollback/redelivery cụ thể phụ thuộc container/broker policy.

**Cassandra write và JMS commit vẫn là hai giao dịch riêng.** Nếu Cassandra đã ghi nhưng JMS commit không thành công, event được redeliver và consumer **bắt buộc** có idempotency.

### 17.2. Async boundary có thể làm mất cơ hội redelivery

~~~text
JMS listener
  -> ExecutorChannel hoặc Cassandra handler async=true
  -> listener return + JMS commit
  -> Cassandra write đang chạy
  -> DB timeout

JMS đã commit: không tự rollback được chỉ vì DB lỗi xảy ra sau.
~~~

Nếu muốn xử lý async và vẫn durable:

- Handoff vào **durable queue/inbox** trước khi ack nguồn.
- Worker có retry budget và reconciliation.
- Không coi `QueueChannel`/`ExecutorChannel` **in-memory** là một persistent message store.
- Giữ original eventId và canonical content.

### 17.3. Kafka offset không cùng transaction Cassandra

~~~text
Kafka poll topic=payments partition=2 offset=120
  -> Cassandra write evt-10001
  -> Quan sát completion
  -> Commit/ack offset theo container policy
~~~

Nếu crash sau DB success nhưng trước Kafka offset commit, record có thể được replay. Nếu offset commit trước một Cassandra async write fail, Kafka **không tự phát lại offset đã commit** chỉ vì Cassandra gửi error sau đó.

Với Kafka retry topics, ordering của cùng aggregate có thể thay đổi; hãy dùng immutable event log và `aggregateVersion`/version guard khi cập nhật current state. Kafka record key có thể hỗ trợ partition ordering trong broker, **không tự bảo đảm các asynchronous Cassandra writes hoàn tất đúng thứ tự đó**.

### 17.4. HTTP retry và idempotency key

Một HTTP client có thể gửi lại request sau 504 Gateway Timeout. Nếu endpoint tạo mới `eventId` cho mỗi HTTP retry, backend sẽ nhận nhiều business events. Có thể:

- Yêu cầu client gửi **Idempotency-Key** duy nhất theo operation, có scope tenant/user và expiration contract.
- Server ánh xạ key tới business event ID một cách **bền vững**.
- Nếu cùng key nhưng payload khác → trả conflict thay vì silently chấp nhận.
- Nếu request trước còn PENDING → trả trạng thái pending/lookup phù hợp hoặc tiếp tục workflow, không tự làm side effect lần hai.

**Không trả `202 Accepted` chỉ vì đã gửi message vào queue in-memory** mà chưa có durable handoff. Trạng thái accepted phải có recovery contract rõ ràng.

### 17.5. Không giấu lỗi qua errorChannel

`errorChannel` của Spring Integration nhận `ErrorMessage` theo messaging/error-path semantics; **nó không phải** JMS broker DLQ, Kafka dead-letter topic hay cơ chế atomic rollback. Nếu error handler nuốt exception trước khi listener transacted thấy nó, source có thể commit dù Cassandra chưa hoàn tất.

Tách riêng:

- **Permanent contract errors:** JSON invalid, thiếu eventId, tenant unauthorized, codec mismatch → quarantine/DLQ với reason.
- **Transient infra errors:** Cassandra unavailable/timeout/overloaded → retry bounded/backoff/circuit breaker.
- **Unknown outcome:** driver/server timeout khi mutation có thể đã ghi → reconcile theo key/fingerprint.
- **Business conflict:** same event ID nhưng khác payload/version → không retry như lỗi network.

## 18. Retry, timeout và backpressure: lặp có kiểm soát

### 18.1. Timeout không chứng minh mutation chưa xảy ra

~~~mermaid
sequenceDiagram
    participant App as Consumer
    participant Drv as Java Driver
    participant C as Cassandra coordinator
    participant A as Replica A
    participant B as Replica B
    App->>Drv: INSERT evt-10001 LOCAL_QUORUM
    Drv->>C: CQL mutation
    C->>A: Write
    C->>B: Write
    A-->>C: ACK
    B-->>C: ACK
    C--xDrv: Response bị mất/chậm
    Drv-->>App: DriverTimeoutException
    Note over App,C: Quorum có thể đã đạt dù app chưa biết
    App->>Drv: Retry same event/key hoặc reconcile
~~~

Chỉ vì `DriverTimeoutException` hay `WriteTimeoutException` được ném **không thể kết luận rollback**. Sau timeout, trả về `FAILED` với ý nghĩa “database chắc chắn chưa ghi” là không chính xác; hệ thống có thể trả **unknown/pending** hoặc defer đến reconciliation theo business contract.

### 18.2. Vì sao Driver DefaultRetryPolicy không retry mọi write?

Java Driver 4.x `DefaultRetryPolicy` chỉ retry các tình huống được đánh giá có lợi và an toàn, có xét idempotency. Ví dụ `WRITE_TIMEOUT` loại `SIMPLE` thường được **rethrow**; riêng `BATCH_LOG` có policy đặc thù. `basic.request.timeout` là **tổng client request deadline**, bao gồm retries và speculative executions.

Không bật `ConsistencyDowngradingRetryPolicy` để tự hạ write `LOCAL_QUORUM` thành `ONE` khi đang outage nếu business invariant dựa trên quorum. Hạ CL có thể tạo stale reads, sai read-after-write và không còn hợp đồng đã công bố.

### 18.3. Retry budget end-to-end

~~~text
Broker JMS deliveries:      tối đa 5
Service retry:              2 retries sau first attempt
Driver possible attempts:   tối đa 2 trong một số errors

Cận trên minh họa: 5 × 3 × 2 = 30 executions/event
~~~

Đây là **tình huống minh họa**, không phải mọi exception đều khiến driver thử lại. Khi bật speculative executions, số requests phát lên cluster có thể còn cao hơn.

Một replay storm khi Cassandra đang thiếu capacity có thể làm hệ thống càng chậm. Nên:

1. Dùng driver default retry policy cho các tình huống chọn lọc.
2. Service retry có **max attempts**, backoff có jitter và deadline.
3. Broker retry/delayed redelivery hoặc durable retry topic cho outage kéo dài.
4. Giới hạn **in-flight Cassandra operations** và nguồn concurrent consumers.
5. Lỗi permanent → quarantine nhanh, không tiêu thụ retry budget DB.
6. LWT timeout/unknown outcome → read-back/inbox state/reconcile.

### 18.4. Example Reactor Retry với immutable upsert

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public Mono<Void> retryImmutableInsert(EventRow row) {
    return Mono.defer(() -> operations.insert(row).then())
            .retryWhen(
                    Retry.backoff(2, Duration.ofMillis(250))
                            .maxBackoff(Duration.ofSeconds(2))
                            .jitter(0.35)
                            .filter(CassandraRetryClassifier::isTransient));
}
~~~

Đây là **method fragment** trong service có `ReactiveCassandraOperations operations`, và `CassandraRetryClassifier` do ứng dụng định nghĩa theo error taxonomy. **Không áp method cho counters hoặc non-idempotent LWT workflows**; `Retry.backoff(2,...)` tạo tối đa **hai lần retry sau lần đầu**. Hệ Spring Data có thể wrap driver exception trong `DataAccessException`; classifier cần xem cause chain nhưng **không retry mọi RuntimeException**.

Nếu nguồn JMS/Kafka đã có retry durable sau failure, service có thể **không cần thêm** Reactor retry; chọn một chiến lược end-to-end thay vì xếp nhiều vòng không quan sát được.

### 18.5. Bounded reactive writes

~~~java
import reactor.core.publisher.Flux;

// source: Flux<EventRow> đã validate; operations: ReactiveCassandraOperations.
Flux<EventRow> completed = source.flatMap(
        row -> operations.insert(row).thenReturn(row),
        8);
~~~

Giới hạn **8 requests in-flight** chỉ là con số lab cần benchmark. `flatMap` có thể hoàn tất **không theo thứ tự source**; với current-state projection phải dùng version guard hoặc serialization theo business key. Không tự gọi `subscribe()` rồi ack broker trước khi completion/error được đưa về infrastructure.

### 18.6. Circuit breaker không thay idempotency

Circuit breaker ngăn phát thêm requests khi Cassandra outage rõ ràng và hỗ trợ fail-fast/defer. Nó **không** biết một mutation trước khi breaker open đã applied hay chưa, không làm dedup, và không biến QueueChannel in-memory thành durable backlog. Cần retry/recovery workflow riêng.

## 19. Observability: đo event effect thay vì chỉ ghi số lần insert

| Metric/log | Cấp đo | Ý nghĩa |
|---|---|---|
| Events received / validated | Inbound/transformer | Lưu lượng business thực sự |
| Unique accepted events | Domain/inbox | Event identities mới hợp lệ |
| Duplicate same-hash | Domain | Redelivery/replay an toàn |
| Conflicting duplicate | Domain/security | Producer reuse ID hoặc data corruption |
| Inbox PENDING age / count | Recovery | Có công việc được claim nhưng chưa finalize |
| Inbox COMPLETED count | Domain | Tiến trình hoàn tất đã xác nhận |
| Projection mismatch count | Reconciliation | Event row có mà timeline/state thiếu hoặc lệch |
| Cassandra write p95/p99 latency | Driver/cluster | Tốc độ, tail latency |
| Driver retries/speculative executions | Driver | Request amplification |
| `Unavailable` / `ReadTimeout` / `WriteTimeout` | Cluster/driver | Lỗi availability/ACK |
| Driver in-flight requests / throttling | Driver | Backpressure |
| JMS queue depth/redelivery count | Broker | Nguồn đang giao lặp |
| Kafka consumer lag/retry-topic backlog | Broker | Downstream chậm |
| DLQ/quarantine oldest age | Ops | Unresolved conflict/permanent errors |
| LWT `applied=false` rate | Domain/cluster | Concurrent duplicate/contended ID |
| Event retention expiry / replay after expiry | Ops | Dedup window có đủ dài? |

### 19.1. Log một event theo dõi được nhưng không lộ dữ liệu

~~~text
traceId=trace-8b2
tenantScope=tenant-42
eventId=evt-10001
operation=events_by_id_if_not_exists
fingerprintVersion=v1
businessOutcome=DUPLICATE_MATCH
inboxState=PENDING
source=jms
sourceCommitted=false
attemptScope=service
attempt=2
latencyMs=137
~~~

Không ghi full `payload_json`, raw authorization token, card/payment secrets hoặc query values nhạy cảm vào logs. `eventId` phù hợp để correlate **log/trace**, nhưng **không nên là metric label** cho từng event vì cardinality cực lớn.

### 19.2. Hai số phải tách riêng

**Write success rate** không bằng **business event completion rate**. Một row insert có thể thành công nhưng projection thứ hai thất bại, inbox còn PENDING. Nếu dashboard chỉ hiển thị số `INSERT` success, người vận hành sẽ tưởng mọi đơn hàng hoàn tất.

Theo dõi ít nhất:

- **DB operation outcome:** success/failure/unknown.
- **Business workflow outcome:** NEW/DUPLICATE/CONFLICT/PENDING/COMPLETED.

### 19.3. Runbook khi duplicate/conflict tăng

1. Kiểm tra nguồn nào đang redeliver: JMS, Kafka offset, HTTP client, backfill.
2. Xác định `eventId` có stable không; có producer tạo ID mỗi retry không?
3. Đối chiếu fingerprints cùng version: duplicate hay conflicting duplicate?
4. Xem timeouts và driver retries: response mất, coordinator chậm, liveness?
5. Đọc inbox state và age; có PENDING mắc kẹt do thiếu recovery queue không?
6. Đo projection mismatch và sửa theo deterministic row keys.
7. Nếu hash khác vì serializer thay đổi, kiểm tra **canonical version** trước khi coi producer có lỗi.
8. Khi khôi phục, **không** phát lại payment/email mà không có downstream idempotency token.

## 20. Bảng xử lý sự cố

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
|---|---|---|
| Redelivery tạo row mới mỗi lần | Consumer dùng random UUID/current bucket | Giữ producer eventId và original occurredAt |
| `INSERT` cùng PK nhưng payload đổi | Upsert/LWW, producer reuse ID | LWT first-write wins + fingerprint conflict check |
| `IF NOT EXISTS` trả false rồi app bỏ qua event | Chỉ check SEEN, không có workflow state | Inbox PENDING/COMPLETED + repair |
| LWT timeout nhưng app báo definitely failed | Không biết conditional write đã applied chưa | Read-back/reconcile trước khi kết luận |
| `applied=false` bị retry vô hạn | Nhầm business result với transport error | Phân loại DUPLICATE/CONFLICT, không retry nóng |
| Client timeout nhưng row tồn tại | Mutation applied, response mất | Giữ same ID; compare state |
| Counter bị tăng gấp đôi | Retry non-idempotent `+1` | Event log/dedup projection, không flag idempotent |
| List prepend tạo entries lặp | Non-idempotent collection update | Đổi model, review retry policy |
| Retry kéo dài TTL | TTL tương đối được gắn lại | Dùng retention/expiry policy ổn định |
| Replay v2 ghi đè v3 | Last-write-wins không có version guard | CAS theo aggregateVersion |
| Cassandra table A có row, table B thiếu | Crash giữa cross-table writes | Replay/reconcile projection, không coi claim là completion |
| Multi-partition logged batch bị xem là atomic snapshot | Hiểu sai batch isolation | Thiết kế view consistency/recovery rõ |
| Inbox PENDING mãi không xử lý | Không có durable queue hoặc pending index | Thêm durable discovery/replay và lease policy |
| Hai workers cùng xử lý PENDING | Thiếu owner token/fencing | Conditional claim, lease version, external idempotency |
| Inbox TTL hết rồi replay tạo side effects mới | Dedup retention window quá ngắn | Tăng retention/archival theo replay SLA |
| Source JMS commit trước DB error | Async handler/channel, không chờ completion | Durable handoff hoặc sync completion |
| Kafka offset committed nhưng Cassandra timeout | Commit policy không gắn DB completion | Thiết kế offset/ack policy + replay queue |
| Message mapping lỗi, retry mãi | Permanent schema/codec error | Quarantine, sửa contract |
| `setIdempotent(true)` không có tác dụng | Bỏ kết quả immutable setter | Reassign statement hoặc builder |
| LWT có throughput thấp | Consensus overhead/hot partition | Dùng conditional only where needed |
| Header tenantId có thể sửa | Trust user-provided tenant header | Verify identity/authorization trước derive key |
| Hash không bằng khi JSON reorder | Hash raw JSON bytes | Canonical schema/version/golden tests |
| Một nguồn có same eventId nhiều tenants | Identity thiếu tenant scope | Compound key/tenant-aware authorization |

### 20.1. Checklist trước khi triển khai

1. **Identity:** Producer tạo eventId một lần; uniqueness scope được ghi rõ.
2. **Key:** Full Cassandra partition/clustering key deterministic, kể cả bucket/shard.
3. **Fingerprint:** Chọn canonical fields/encoding/version, lưu fingerprint và kiểm tra conflict.
4. **Write semantics:** Upsert/LWT/CAS/inbox chọn đúng invariant.
5. **TTL:** Dedup retention không ngắn hơn replay/backfill window.
6. **Timestamp:** Không dùng LWW mặc định để ordering business state.
7. **Side effects:** Downstream idempotency key cho payment/email/HTTP.
8. **Crash windows:** Biết trạng thái sau từng bước và cách resume.
9. **Source ack:** Không commit quá sớm khi chỉ handoff in-memory.
10. **Retries:** Bounded, jitter, no consistency downgrade tùy tiện.
11. **Recovery:** PENDING discovery/durable queue, fencing và reconciliation.
12. **Observability:** Tách DB write success và business completion.
13. **Security:** Tenant authorization, không log raw secrets/payload.
14. **Tests:** Unit mapping, CQL integration, multi-node timeout, broker redelivery.

## 21. Bài thực hành: idempotent Cassandra write end-to-end

**Môi trường:** Java 17+, Spring Integration Cassandra 6+/7+ tương thích với Spring Data Cassandra, Java Driver 4.x, Cassandra test cluster/Testcontainers. Với fault-injection/quorum, cần cluster có nhiều replica nodes thật; với ack/replay, cần JMS/Kafka broker test. **Không** dùng `DROP/TRUNCATE`, kill node hay chaos injection trên production.

### Bài A — Unconditional upsert và conflicting duplicate

1. Tạo keyspace và bảng `events_by_id` ở mục 3.
2. Ghi event `tenant-42 + evt-10001` với hash-A.
3. Gửi lại **cùng CQL/PK và values**, query theo đủ tenantId + eventId.
4. Ghi lại cùng PK nhưng hash-B, kiểm tra giá trị row cuối theo Cassandra timestamps.
5. Giải thích tại sao `INSERT` không có duplicate exception mặc định và vì sao hash-B là conflict nghiệp vụ.
6. Không dùng `ALLOW FILTERING` để tìm event bằng mỗi `eventId` khi table PK là `(tenantId,eventId)`.

**PASS:** Có một logical row theo full PK, nhưng unconditional upsert **không** cung cấp first-write wins.

### Bài B — Deterministic key qua retry, replay và timezone

1. Tạo `OrderPaidEvent` chứa eventId và original occurredAt.
2. Dùng `StableEventKeys.canonicalTime/utcMonth` để tính canonical date/bucket.
3. Gửi cùng event ở ngày/giờ xử lý khác; kiểm tra full Cassandra key không đổi.
4. Thử Instant có nanoseconds và kiểm tra truncate sang milliseconds.
5. Thử đổi timezone JVM default; bucket vẫn theo UTC.
6. Thử shard function version 16 và 32; giải thích vì sao không đổi modulo trên dữ liệu cũ mà không migration.

**PASS:** Same event luôn tạo same key theo một key-schema version đã xác định, bất kể retry time.

### Bài C — Fingerprint ổn định

1. Tính `EventFingerprint.sha256(...)` của `OrderPaidEvent` hợp lệ.
2. Chạy 100 lần với cùng fields; hash phải giống nhau.
3. Đổi amountMinor/currency/orderId hoặc eventId; hash phải thay đổi.
4. Deserialize hai JSON có thứ tự field/khoảng trắng khác nhau thành cùng DTO rồi tính hash; hash bằng nhau.
5. Thử nâng schemaVersion 2: thiết kế **fingerprint:v2** thay vì âm thầm đổi fields của v1.
6. Viết golden test với một event cố định cho mỗi language/serializer được dùng, so hash.

**PASS:** Fingerprint đại diện canonical business values, không phụ thuộc raw JSON spacing.

### Bài D — LWT IF NOT EXISTS và applied=false

1. Chạy `INSERT ... IF NOT EXISTS` cho một event ID mới.
2. Kiểm tra `wasApplied()==true`.
3. Gửi lại cùng event, kiểm tra `wasApplied()==false`.
4. Đọc row và so fingerprint → `DUPLICATE_MATCH`.
5. Gửi same ID khác amount/payload, kiểm tra fingerprint khác → `CONFLICT`.
6. Thử đồng thời hai writers ghi same ID/different payload, quan sát chỉ có một conditional insert được applied.
7. Đo p99 LWT và so với regular INSERT dưới tải hợp lý.

**PASS:** LWT bảo vệ first-write condition; false được phân loại theo row nội dung chứ không coi là network error.

### Bài E — Spring Data Cassandra InsertOptions

1. Tạo `EventKey`, `EventRow` có `@PrimaryKeyClass`/`@PrimaryKeyColumn`.
2. Dùng `ReactiveCassandraOperations.insert(row, InsertOptions.builder().withIfNotExists()...)`.
3. Dùng `StepVerifier` hoặc subscriber test để nhận `EntityWriteResult<EventRow>`.
4. Kiểm tra `wasApplied()` trên first insert và replay.
5. Với applied=false, đọc lại bằng `selectOneById(row.key(), EventRow.class)`.
6. Simulate failure khi read-back không trả row; không tự đánh dấu duplicate.
7. Xác minh null/codec/primary key mapping bằng Cassandra thật.

**PASS:** Không chỉ kiểm tra số lần gọi mock API; có round-trip key/field và LWT result.

### Bài F — TTL và write timestamp

1. Tạo một **table thử nghiệm** có default TTL hoặc dùng CQL `USING TTL`.
2. Ghi row với TTL ngắn trong môi trường test, đọc `TTL(column)` nếu phù hợp.
3. Gửi lại same PK/values sau một khoảng thời gian; so remaining TTL/expiry.
4. Ghi hai update conflicting cùng key với timestamps được kiểm soát; quan sát LWW.
5. Thử replay event cũ sau state event mới; không dựa vào write timestamp để bảo toàn aggregate order.
6. Tìm hiểu vì sao custom write timestamp bị cấm/ignored cho LWT conditional statements.

**PASS:** Giải thích temporal idempotency khác logical-row idempotency.

### Bài G — Inbox crash ngay sau claim

1. Tạo `event_inbox` ở mục 10.
2. LWT claim `PENDING` cho `evt-10001`.
3. Simulate crash **trước** khi ghi business projection.
4. Broker redeliver event; LWT claim lại trả false.
5. **Không bỏ qua**: đọc PENDING và dùng durable retry/recovery path để tiếp tục.
6. Ghi business row và finalize `COMPLETED` bằng CAS phù hợp.
7. Redeliver lại same event; thấy COMPLETED + same hash và ack an toàn.

**PASS:** Không mất business effect vì “claim đã tồn tại”, có thể resume sau crash.

### Bài H — Hai workers và fencing

1. Tạo hai workers cùng nhận `evt-10002`.
2. Thử LWT claim đồng thời, quan sát chỉ một được `applied=true` khi ABSENT.
3. Worker A giữ lease; giả lập A chậm đến mức hết lease.
4. Worker B có thể nhận lease mới qua **conditional claim/version**.
5. Cho A thức dậy và thử finalize state; CAS theo owner/version phải ngăn A cập nhật sai inbox.
6. Nếu A đã gọi external HTTP, dùng **downstream idempotency token**; Cassandra fencing không thu hồi được request đã gửi.

**PASS:** Phân biệt CAS bảo vệ inbox state với idempotency của external side effect.

### Bài I — Ghi nhiều Cassandra tables và reconciliation

1. Tạo `events_by_id` và `events_by_order_month` với keys ở mục 12.
2. Ghi row ID thành công, rồi cố ý dừng trước khi ghi timeline.
3. Kiểm tra một table có data và table kia thiếu.
4. Replay/repair bằng same full PK của timeline, không sinh eventId khác.
5. Với current-state projection, dùng version guard để không ghi lùi state.
6. Chỉ chuyển inbox `COMPLETED` khi đã xác minh các bước cần thiết.
7. Thử multi-partition LOGGED batch nhỏ trong cluster test và quan sát khả năng partial visibility.

**PASS:** Reconciliation có thể bù bước thiếu, không tuyên bố multi-table SQL atomicity.

### Bài J — Spring Integration JMS/Kafka acknowledgment

1. Cấu hình source JMS transacted hoặc Kafka test consumer có ack/offset policy rõ.
2. Đưa `Message<OrderPaidEvent>` qua transformer → `EventRow` → Cassandra handler `async(false)` trên `DirectChannel`.
3. Cho Cassandra ghi thành công nhưng mô phỏng JVM crash trước JMS commit/Kafka offset commit.
4. Quan sát broker replay event **cùng ID**; projection không thêm business row thứ hai.
5. Đổi sang `ExecutorChannel` hoặc handler async; quan sát nguồn **có thể commit trước DB completion**.
6. Thiết kế durable handoff/retry queue và error propagation cho đường async.
7. Gửi payload malformed/unauthorized; kiểm tra DLQ/quarantine thay vì retry DB vô hạn.

**PASS:** Biết chính xác khi nào nguồn ack/commit và khi nào phải giữ durable replay.

### Bài K — Retry storm, timeout và backpressure

1. Đo baseline Cassandra p50/p95/p99 trên cluster khỏe.
2. Tăng concurrency có giới hạn, tạo lỗi timeout bằng test failure injection.
3. Bật driver `DefaultRetryPolicy` và một service retry có max attempts; quan sát request amplification.
4. Kiểm tra `DriverTimeoutException` **không chứng minh** mutation chưa xảy ra.
5. Thử lại bằng giảm upstream concurrency, jittered backoff/circuit breaker.
6. Đếm business `NEW/DUPLICATE/CONFLICT/PENDING/COMPLETED`, không chỉ database insert count.
7. Kiểm tra timeouts không làm mất recovery path của inbox/broker.

**PASS:** Retry mang tính phục hồi, có quan sát, không gây bão tải và không làm sai dữ liệu.

### Bài L — Migration, replay window và kiểm tra security

1. Tạo test event có `schemaVersion=1`, fingerprint version v1.
2. Thiết kế schemaVersion/fingerprint v2, kiểm thử cùng business identity qua compatibility rules.
3. Thử dùng cùng event ID từ hai tenants; full PK phải khác nhau theo tenant scope.
4. Gửi header tenantId giả mạo; authorization phải chặn trước derive key.
5. Thiết lập inbox TTL ngắn **chỉ trong lab**, chờ hết hạn rồi replay; quan sát nguy cơ claim lại như event mới.
6. Viết retention policy production tính từ maximum replay/backfill window.
7. Kiểm tra logs/metrics không chứa raw payment details hay event ID thành high-cardinality metric label.

**PASS:** Key/fingerprint versioned, tenant isolation đúng và dedup window phù hợp replay SLA.

### Ma trận kiểm thử cuối bài

| Kiểm tra | PASS khi |
|---|---|
| Business ID | Không đổi qua producer retry, JMS/Kafka replay, backfill |
| PK/partition key | Same event → same full key, kể cả bucket/shard |
| Canonical fingerprint | Same semantic payload → same digest |
| Conflict | Same ID/different payload bị từ chối/điều tra |
| Regular upsert | Không tạo row mới theo cùng PK, hiểu LWW |
| TTL | Biết retry có thể đổi expiration |
| LWT | `wasApplied()` true/false/timeout xử lý tách biệt |
| Inbox PENDING | Không ack/bỏ qua trước khi side effects được hoàn tất/durable |
| Inbox CAS/fencing | Stale worker không finalize sai |
| Current state | Old aggregateVersion không ghi đè version mới |
| Multi-table | Có reconciliation, không đòi instant atomic snapshot |
| Java Driver | Idempotency flag không bị áp mù, timeout/CL đúng |
| Spring Data | Entity mapping và InsertOptions đúng |
| Spring Integration | Transformer và handler sync/async dùng có chủ đích |
| JMS/Kafka | Source commit/offset không tự atomic với Cassandra |
| Retry/backpressure | Bounded, jitter, không retry permanent contract failures |
| Security | Tenant scope xác thực, không log raw secrets |
| Observability | Tách DB operation success khỏi business completion |

**Giới hạn unit mocks:** Không thể dùng một fake `ReactiveCassandraOperations` để chứng minh Cassandra LWT consensus, server/driver timeout, coordinator failover, batchlog recovery hoặc JDBC-like transaction semantics. Những nội dung đó cần **Cassandra thật** trong test; JMS/Kafka acknowledgment cần broker phù hợp và fault injection được kiểm soát.

## 22. Câu hỏi tự đánh giá

1. Vì sao JMS/Kafka at-least-once delivery có thể tạo nhiều lần xử lý cùng business event dù producer không sai?
2. CQL statement idempotence khác business event idempotency như thế nào?
3. Vì sao “chạy INSERT đúng một lần” và “event được xử lý với hiệu ứng tương đương một lần” không phải cùng khái niệm?
4. Cassandra unconditional `INSERT` là unique insert hay upsert?
5. Nếu hai payload khác nhau có cùng full primary key, điều gì có thể xảy ra với regular columns?
6. Vì sao nên đặt `tenantId` trong key nếu eventId chỉ unique trong từng tenant?
7. Business eventId khác `JMSMessageID`, Kafka offset và Spring Message ID như thế nào?
8. Khi nào producer nên tạo eventId, và client retry phải dùng lại ID nào?
9. Tại sao consumer không được gọi `UUID.randomUUID()` trong mỗi retry để làm Cassandra PK?
10. Vì sao dùng ngày xử lý hiện tại để tạo `bucket_month` gây duplicate khi replay?
11. `Instant` và CQL `timestamp` khác nhau về precision như thế nào?
12. Nếu tăng số shards từ 16 lên 32, vì sao key của dữ liệu cũ có thể thay đổi?
13. Hash raw JSON có thể thay đổi dù semantic fields không đổi không? Hãy cho ví dụ.
14. Một payload fingerprint nên gồm những trường nghiệp vụ nào để phát hiện conflicting duplicate?
15. Vì sao phải version hóa canonical fingerprint algorithm?
16. Same `eventId` và same fingerprint có luôn nghĩa mọi downstream effects đã hoàn tất không?
17. LWT `INSERT IF NOT EXISTS` giúp thực thi invariant nào?
18. `wasApplied()=false` cần được xử lý ra sao để phân biệt duplicate với conflict?
19. Timeout khi LWT conditional insert có chứng minh row chưa tồn tại không?
20. Vì sao `LOCAL_SERIAL` và `LOCAL_QUORUM` là hai cấu hình khác nhau trong LWT?
21. Tại sao không nên gắn custom `USING TIMESTAMP` vào LWT?
22. Khi nào regular deterministic upsert đủ, khi nào cần LWT first-write wins?
23. Vì sao LWT có thể làm throughput giảm khi dùng cho mọi event?
24. Cassandra `USING TTL` có thể làm event sống lâu hơn khi retry không?
25. Cassandra write timestamp có phải aggregate version của domain không?
26. Vì sao replay của `OrderPaid(v2)` có thể ghi lùi state sau `OrderCancelled(v3)`?
27. Compare-and-set `UPDATE ... IF version = ?` xử lý ordering ra sao?
28. `schemaVersion`, `aggregateVersion`, `@Version` và Kafka offset khác nhau thế nào?
29. Counter update `+1` có idempotent không? Tại sao?
30. Vì sao list prepend là thao tác nguy hiểm khi driver tự retry?
31. `setIdempotent(true)` của Java Driver tạo unique key/deduplication record không?
32. Vì sao không bật `basic.request.default-idempotence=true` toàn hệ thống khi có counters/side effects?
33. Java Driver immutable statement setter cần được sử dụng thế nào?
34. Vì sao `DriverTimeoutException` không kết luận Cassandra rollback?
35. Một inbox chỉ có trạng thái SEEN sẽ gây lỗi gì khi JVM crash sau claim?
36. Trạng thái `PENDING` và `COMPLETED` trong durable inbox khác nhau ra sao?
37. Nếu inbox row chỉ được partition theo eventId, làm sao worker tìm toàn bộ PENDING mà không dùng full-table scan?
38. Lease/version fencing ngăn stale worker ghi inbox nhưng không tự ngăn side effect nào bên ngoài?
39. Vì sao một external payment provider cũng cần idempotency token?
40. Inbox TTL phải xét những loại replay window nào?
41. Logged multi-partition batch có bảo đảm snapshot isolation giữa hai Cassandra tables không?
42. Vì sao cần reconciliation cho `events_by_id` và `events_by_order_month` sau crash?
43. Khi Cassandra ghi xong nhưng JMS commit thất bại, broker có thể làm gì?
44. Khi JMS commit sớm trước async Cassandra failure, tại sao lỗi không tự rollback được nguồn?
45. Kafka offset commit có transaction nguyên tử với Cassandra mutation không?
46. Spring Integration `CassandraMessageHandler` mặc định synchronous hay asynchronous?
47. Khi dùng Spring Integration one-way adapter, có thể dựa vào `send(true)` để biết LWT `wasApplied()` không?
48. `ReactiveCassandraOperations.insert(row, InsertOptions)` cho conditional insert có thể trả kết quả gì?
49. Vì sao không ack một duplicate event chỉ sau khi thấy event row tồn tại nếu workflow còn projection/email?
50. Retry budget nên phối hợp driver, service và broker thế nào để tránh request amplification?
51. Một `ErrorMessage` tới Spring Integration `errorChannel` có đồng nghĩa đã đưa vào JMS DLQ không?
52. Những metrics nào phân biệt database write success và business workflow completion?
53. Tại sao không dùng eventId làm metric label của mỗi event?
54. Khi producer gửi cùng ID với hash khác, ứng dụng nên retry database hay báo domain conflict?
55. Hãy đề xuất recovery plan cho một event PENDING đã ghi table A nhưng chưa ghi table B, trong khi bản state mới hơn đã tới.

## 23. Tài liệu tham khảo chính thức

- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `INSERT` upsert, `IF NOT EXISTS`, `UPDATE`, `BATCH`, TTL, timestamp và counter semantics.
- [Apache Cassandra — CQL Data Types](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/types.html): `timestamp`, `uuid`, `counter`, collections và dữ liệu typed.
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html): partition key/query-first design và kiểm soát partition growth.
- [Apache Cassandra — Dynamo Architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): tunable consistency, replication, quorum và conflict resolution.
- [Apache Cassandra Java Driver 4.19 — Idempotence](https://apache.github.io/cassandra-java-driver/4.19.0/core/idempotence/): `Statement.setIdempotent(...)`, default false và điều kiện retry/speculative execution.
- [Apache Cassandra Java Driver 4.19 — Retries](https://apache.github.io/cassandra-java-driver/4.19.0/core/retries/): `DefaultRetryPolicy` và các quyết định retry an toàn.
- [Apache Cassandra Java Driver 4.19 — Query Timestamps](https://apache.github.io/cassandra-java-driver/4.19.0/core/query_timestamps/): timestamp generator, `setQueryTimestamp(...)`, LWT restriction.
- [Apache Cassandra Java Driver 4.19 — Speculative Execution](https://apache.github.io/cassandra-java-driver/4.19.0/core/speculative_execution/): idempotent only, request amplification, cancellation semantics.
- [Apache Cassandra Java Driver 4.19 — Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/): immutable statements, CL, timeout, query timestamp.
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): `@Table`, `@PrimaryKeyClass`, `@PrimaryKeyColumn` và converter metadata.
- [Spring Data Cassandra — Persisting Entities](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): `ReactiveCassandraOperations`, `InsertOptions`, `UpdateOptions`, upsert và LWT.
- [Spring Data Cassandra API — InsertOptionsBuilder](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/InsertOptions.InsertOptionsBuilder.html): `withIfNotExists()`, consistency, serial consistency và timeout.
- [Spring Data Cassandra API — EntityWriteResult](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/EntityWriteResult.html): `wasApplied()` qua `WriteResult` và entity result.
- [Spring Data Cassandra API — ReactiveCassandraOperations](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/ReactiveCassandraOperations.html): reactive insert/select/conditional operations.
- [Spring Integration — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): `CassandraMessageHandler`, outbound adapter/gateway, `statementFunction`, async default và `writeOptions`.
- [Spring Integration — Message Transformation](https://docs.spring.io/spring-integration/reference/transformer.html): `Transformer` trước persistence handler.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `errorChannel`/`ErrorMessage` và synchronous/asynchronous behavior.
- [Spring Integration — JMS](https://docs.spring.io/spring-integration/reference/jms.html): message-driven inbound adapter, JMS container và transaction considerations.
- [Spring Integration — Kafka](https://docs.spring.io/spring-integration/reference/kafka.html): Kafka inbound adapter/gateway, error handling và offset boundary.
- [Project Reactor — Retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html#_retrying): `retryWhen`, backoff và error classification.

**Ghi nhớ:** Thiết kế idempotent khi ghi Cassandra bắt đầu bằng **business event ID bất biến**, **full Cassandra key deterministic** và **payload fingerprint có version**. Regular `INSERT` là **upsert**, không tự bảo vệ first-write wins hoặc phát hiện conflicting duplicate; khi cần dùng `INSERT IF NOT EXISTS`/LWT và kiểm tra `wasApplied()` **kèm read-back**. **Timeout không chứng minh dữ liệu chưa ghi**; retry phải bounded và chỉ áp cho thao tác thực sự an toàn. Đừng xem một row SEEN/PENDING, một multi-partition logged batch hoặc một `send(true)` là bằng chứng mọi side effects hoàn tất. Với Spring Integration qua JMS/Kafka/HTTP, cần **acknowledgment boundary, durable inbox/replay, conditional state transitions, downstream idempotency và reconciliation** để phục hồi đúng sau crash, concurrent delivery và reprocessing.








