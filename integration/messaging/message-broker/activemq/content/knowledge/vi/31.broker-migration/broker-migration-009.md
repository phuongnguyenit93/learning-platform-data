# Đối soát số lượng, thông điệp lặp, thứ tự và độ trễ sau di chuyển

> **Chương:** Di chuyển broker  
> **Phạm vi:** Xác minh dữ liệu và hành vi nghiệp vụ sau khi chuyển luồng message giữa ActiveMQ Classic và Artemis hoặc giữa hai broker cùng loại. Trọng tâm là đối soát event, phát hiện message thiếu/trùng, kiểm tra thứ tự theo khóa và đo độ trễ sau cutover. Không giả định message ID, queue counters hay thứ tự toàn cục được giữ nguyên sau migration.

## 1. Vì sao không thể chỉ so sánh queue size?

Sau migration, queue nguồn có 12.000 message và queue đích có 12.000 message chưa chứng minh dữ liệu đã khớp. Hai queue có thể chứa hai tập event khác nhau nhưng cùng số lượng. Ngược lại, queue đích có ít message hơn chưa chắc mất dữ liệu: consumer có thể đã xử lý một phần trong lúc cutover, một số message đã hết hạn hoặc topic subscription có semantics khác.

Cần đối soát theo **danh tính nghiệp vụ ổn định của event** và một mốc cutover có thể giải thích.

Ví dụ hệ thống Order có producer gửi event vào `orders.events`. Khi chuyển broker:

- Một message có thể được copy/replay sang broker mới nên xuất hiện hai lần.
- Consumer cũ có thể đã nhận nhưng chưa commit; broker mới cũng nhận bản replay.
- `JMSMessageID` có thể đổi vì provider tạo ID mới khi publish lại.
- Consumer concurrency thay đổi có thể làm thứ tự xử lý khác trước.
- Queue mới có thể bắt đầu nhận message ngay trong lúc đang import dữ liệu cũ.
- Thời gian dừng luồng, replay và backlog làm latency tăng dù số lượng cuối cùng khớp.

Cần kiểm tra ít nhất bốn chiều:

| Chiều đối soát | Câu hỏi | Bằng chứng chính |
| --- | --- | --- |
| **Số lượng/tập event** | Có event nào thiếu hoặc thừa ở đích? | Stable event ID, cutover watermark, source/target manifest |
| **Duplicate** | Có cùng event được lưu hoặc xử lý nhiều lần? | Event ID, delivery count, idempotency/inbox record |
| **Thứ tự** | Event theo cùng aggregate/key có bị đảo hoặc đứt sequence? | Ordering key và sequence number do producer gán |
| **Độ trễ** | Sau cutover, message đến consumer và hoàn tất nghiệp vụ trong bao lâu? | Producer timestamp, receive/process/commit timestamps, p50/p95/p99 |

**Nguyên tắc:** queue metrics giúp khoanh vùng; event-level reconciliation mới chứng minh dữ liệu nghiệp vụ khớp.

## 2. Xác lập mốc cutover và tập dữ liệu phải đối soát

### 2.1. Chọn một watermark có thể tái lập

Trước khi chuyển, xác định một watermark cho từng producer partition hoặc ordering key. Watermark là sequence cuối cùng đã được producer phát và broker nguồn xác nhận trước thời điểm đóng luồng.

Ví dụ:

```text
producerId       partition   lastCommittedSequence
orders-api-01    0            845120
orders-api-01    1            912044
orders-api-02    0            501992
orders-api-02    1            488120
```

Không dùng một timestamp wall-clock duy nhất làm watermark nếu producer có nhiều instance, clock skew hoặc retry. Sequence theo producer/partition dễ kiểm tra khoảng trống và trùng hơn.

Quy trình cutover có kiểm soát:

1. Ngừng hoặc chuyển producer ingress theo kế hoạch; ghi lại thời điểm và watermark cuối.
2. Dừng consumers hoặc chờ các transaction đang mở hoàn tất theo runbook.
3. Chụp source manifest: event ID, ordering key, sequence, payload hash, destination và trạng thái cần di chuyển.
4. Phân loại message pending, delivering/in-flight, scheduled, expired và DLQ. Không gộp chúng thành một con số.
5. Xử lý in-flight: commit/ACK, rollback/redelivery hoặc ghi rõ danh sách unresolved trước khi chuyển.
6. Import/replay sang broker đích; ghi nhận run ID và kết quả theo từng batch.
7. Chỉ mở consumer/producer ở đích theo thứ tự đã thống nhất; ghi target manifest và thời điểm bắt đầu xử lý.
8. Giữ nguồn ở chế độ read-only/fenced cho tới khi đạt acceptance criteria hoặc hết cửa sổ rollback.

Nếu không thể dừng producer/consumer, cần một giao thức dual-write/CDC hoặc capture log có sequence/watermark. Không thể tạo snapshot nhất quán chỉ bằng cách đọc queue count trong khi message liên tục được gửi, nhận và ACK.

### 2.2. Phân biệt các tập dữ liệu

Đối soát phải nói rõ event thuộc trạng thái nào:

| Tập | Định nghĩa | Kỳ vọng sau migration |
| --- | --- | --- |
| **Committed at source** | Producer đã được broker nguồn chấp nhận theo mức bảo đảm đã chọn | Có trong manifest nguồn hoặc có bằng chứng terminal state |
| **Pending** | Message chưa được consumer xác nhận | Thường phải chuyển/replay nếu thuộc scope |
| **Delivering/in-flight** | Broker đã dispatch nhưng chưa nhận ACK/commit | Phải resolve hoặc ghi nhận riêng; không coi là pending thông thường |
| **Acknowledged** | Consumer đã xác nhận | Không replay lại trừ khi business replay có chủ đích |
| **Scheduled** | Message được lên lịch giao sau | Giữ due time/expiration semantics hoặc lập kế hoạch riêng |
| **Expired** | Message hết hạn theo policy | Không kỳ vọng replay như message còn hiệu lực |
| **Dead-letter/quarantine** | Message đã bị đưa sang vùng lỗi | Đối soát riêng; không tự động nhập lại luồng chính |
| **Filtered/excluded** | Message bị loại theo migration scope đã phê duyệt | Phải có rule và count giải thích được |

**Không cộng tất cả trạng thái rồi so với queue size.** Một message scheduled có thể chưa xuất hiện trong số liệu pending theo cùng cách trên mọi broker; topic có thể có nhiều bản theo subscription; in-flight có thể được tính riêng. Manifest phải quy định rõ những lớp nào nằm trong scope.

### 2.3. Queue và topic có đơn vị đếm khác nhau

- Với **queue**, một event được route tới queue theo semantics của destination. Nhiều competing consumers chia nhau xử lý message.
- Với **topic**, mỗi durable subscription thường có queue/backlog riêng. Một publication có thể tạo một bản cho từng durable subscription; không thể lấy tổng queue messages ở broker A rồi so trực tiếp với số event publish ở broker B.
- Artemis multicast address có các queues gắn với subscription; Classic durable topic subscription cũng có state riêng.
- Non-durable subscription thường không giữ backlog khi subscriber offline; nếu migration yêu cầu không mất event khi offline, cần xác minh durable/shared subscription semantics.

Đối với topic, manifest cần khóa định danh gồm `topic/address + subscription identity`, không chỉ tên topic. Nếu có ba durable subscribers, hãy đối soát ba luồng subscription riêng.

## 3. Dùng event ID ổn định; không dựa vào JMSMessageID

### 3.1. Các ID có mục đích khác nhau

| Trường | Nguồn tạo | Có ổn định qua republish/migration? | Dùng để |
| --- | --- | --- | --- |
| `JMSMessageID` | JMS provider/broker | **Không đảm bảo**; broker mới có thể tạo ID mới | Điều tra message instance trong một broker |
| `JMSCorrelationID` | Ứng dụng hoặc caller | Tùy contract; thường đại diện quan hệ request/reply | Ghép các message liên quan |
| `eventId` | Ứng dụng/producer | **Phải giữ nguyên** qua retry, replay và migration | Deduplicate và đối soát nghiệp vụ |
| `producerId + partition + sequenceNo` | Producer | Phải ổn định theo stream | Kiểm tra gap, duplicate và ordering |
| `payloadSha256` | Producer/canonicalizer | Chỉ ổn định nếu bytes/canonicalization giống nhau | Phát hiện payload thay đổi/hỏng |

Một event có thể có `JMSMessageID` khác nhau ở source và target nhưng vẫn là cùng event nếu `eventId` giống nhau. Không coi khác `JMSMessageID` là message mới, và cũng không coi hai message cùng `JMSCorrelationID` là duplicate.

### 3.2. Metadata nên gắn vào message

Một event envelope nên có tối thiểu:

```json
{
  "eventId": "01JORDER8Z5K5M3WQ8S7V0F3X1A",
  "eventType": "OrderCreated",
  "producerId": "orders-api-01",
  "partition": 0,
  "orderingKey": "order-7842",
  "sequenceNo": 845120,
  "eventCreatedAt": "2026-11-17T08:30:12.450Z",
  "schemaVersion": 3,
  "payload": {
    "orderId": "7842"
  }
}
```

Nếu không thể thay đổi body schema, đặt metadata đối soát vào JMS properties:

- `eventId`: stable ID duy nhất cho một business event.
- `producerId`, `partition`, `sequenceNo`: định vị event trong stream.
- `orderingKey`: khóa cần bảo toàn thứ tự (order ID, account ID…).
- `eventCreatedAtEpochMs`: thời điểm producer tạo event; dùng để đo age nếu clock được đồng bộ.
- `payloadSha256`: hash của bytes payload theo một quy tắc canonical rõ ràng.
- `schemaVersion`: giúp xác định transform/compatibility.

Không đặt PII hoặc secret vào property chỉ để dễ đối soát; properties có thể xuất hiện trong logs, Console và metrics labels.

### 3.3. Java Jakarta JMS: gửi stable identity và hash

Ví dụ Java 17+, payload đã serialize thành UTF-8 bytes. Hash phải được tính trên **đúng bytes contract**; nếu JSON được serialize khác thứ tự field, hãy canonicalize trước khi hash.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.HexFormat;

import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

public final class MigrationMessageMetadata {

    public static String sha256(byte[] payload) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(payload);
        return HexFormat.of().formatHex(digest);
    }

    public static void send(
            Session session,
            MessageProducer producer,
            String json,
            String eventId,
            String producerId,
            int partition,
            String orderingKey,
            long sequenceNo,
            int schemaVersion) throws Exception {

        byte[] payload = json.getBytes(StandardCharsets.UTF_8);
        TextMessage message = session.createTextMessage(json);

        message.setStringProperty("eventId", eventId);
        message.setStringProperty("producerId", producerId);
        message.setIntProperty("partition", partition);
        message.setStringProperty("orderingKey", orderingKey);
        message.setLongProperty("sequenceNo", sequenceNo);
        message.setLongProperty(
                "eventCreatedAtEpochMs", Instant.now().toEpochMilli());
        message.setIntProperty("schemaVersion", schemaVersion);
        message.setStringProperty("payloadSha256", sha256(payload));

        producer.send(message);
    }
}
```

Đoạn gửi không tự quyết định transaction mode. Nếu session transacted, producer phải commit; chỉ ghi manifest `source_committed` sau khi commit được xác nhận. Nếu commit timeout và outcome không rõ, đánh dấu `commit_unknown`, đối soát event ID trước khi retry.

**Không dùng timestamp làm sequence.** Nhiều producer có thể tạo cùng timestamp hoặc clock bị lệch. Sequence phải được cấp theo producer partition hoặc ordering key có cơ chế đồng bộ.

## 4. Thiết kế manifest đối soát có thể truy vết

### 4.1. Một observation cho mỗi giai đoạn

Không chỉ lưu “source count = 100, target count = 100”. Hãy ghi lại event observations theo stage:

| Stage | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `source_pending` | Event còn ở queue nguồn tại watermark | Nằm trong scope migration |
| `source_inflight` | Event đã dispatch nhưng chưa ACK | Cần resolve riêng |
| `source_dlq` | Event ở DLQ nguồn | Chuyển DLQ theo kế hoạch riêng |
| `target_imported` | Event đã được ghi ở queue đích | Xác nhận import/replay |
| `target_delivered` | Consumer đích đã nhận | Chưa đồng nghĩa business commit |
| `target_processed` | Business result đã commit | Terminal success theo nghiệp vụ |
| `excluded` | Event bị loại theo rule được duyệt | Giải thích chênh lệch có chủ đích |

Một observation cần lưu `migrationRunId`, logical destination, broker side, stage, `eventId`, `producerId`, partition, ordering key, sequence, payload hash, timestamp, `JMSMessageID`, `JMSRedelivered` và delivery count nếu provider hỗ trợ.

`target_delivered` và `target_processed` phải tách riêng. Nếu consumer nhận message nhưng transaction rollback, observation delivery có thể tồn tại nhưng business result chưa được commit. Audit DB độc lập với JMS transaction cũng có thể ghi attempt dù JMS rollback; không gọi attempt đó là processed.

### 4.2. Schema PostgreSQL minh họa

```sql
CREATE TABLE migration_observation (
    observation_id       BIGSERIAL PRIMARY KEY,
    migration_run_id    TEXT NOT NULL,
    logical_destination TEXT NOT NULL,
    broker_side         TEXT NOT NULL,
    stage               TEXT NOT NULL,
    event_id            TEXT NOT NULL,
    producer_id         TEXT,
    partition_id        INTEGER,
    ordering_key        TEXT,
    sequence_no         BIGINT,
    payload_sha256      CHAR(64),
    jms_message_id      TEXT,
    jms_redelivered     BOOLEAN,
    delivery_count      INTEGER,
    event_created_at    TIMESTAMPTZ,
    observed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at        TIMESTAMPTZ
);

CREATE INDEX idx_migration_event
    ON migration_observation (
        migration_run_id, logical_destination, event_id
    );

CREATE INDEX idx_migration_stage
    ON migration_observation (
        migration_run_id, broker_side, stage
    );

CREATE INDEX idx_migration_order
    ON migration_observation (
        migration_run_id, logical_destination,
        producer_id, partition_id, ordering_key, sequence_no
    );
```

Bảng lưu **nhiều observations** cho một event ở các stage khác nhau và cả các delivery attempts. Không đặt unique constraint đơn giản trên `event_id`, vì điều đó sẽ xóa mất bằng chứng duplicate. Nếu cần chống ghi trùng một observation do audit retry, thêm `observation_key` idempotent riêng cho mỗi lần đo/stage/attempt.

Trong hệ thống lớn, partition bảng theo `migration_run_id` hoặc thời gian, retention ngắn cho raw observations và lưu aggregate lâu hơn. Hạn chế quyền đọc vì bảng có thể chứa event IDs, correlation IDs và metadata nhạy cảm.

### 4.3. Đối soát count theo stage

```sql
SELECT
    broker_side,
    stage,
    logical_destination,
    COUNT(*) AS observation_rows,
    COUNT(DISTINCT event_id) AS distinct_events
FROM migration_observation
WHERE migration_run_id = 'cutover-2026-11-17'
GROUP BY broker_side, stage, logical_destination
ORDER BY logical_destination, broker_side, stage;
```

`observation_rows` có thể lớn hơn `distinct_events` vì một event có nhiều delivery attempts hoặc observation retries. Để đếm số message instance được lưu ở queue, stage phải được ghi **một lần cho mỗi instance tại snapshot**, không phải mỗi lần consumer nhận.

Tạo manifest theo event ID từ source pending:

```sql
WITH source_set AS (
    SELECT DISTINCT event_id
    FROM migration_observation
    WHERE migration_run_id = 'cutover-2026-11-17'
      AND broker_side = 'source'
      AND stage = 'source_pending'
      AND logical_destination = 'orders.events'
),
target_set AS (
    SELECT DISTINCT event_id
    FROM migration_observation
    WHERE migration_run_id = 'cutover-2026-11-17'
      AND broker_side = 'target'
      AND stage = 'target_imported'
      AND logical_destination = 'orders.events'
)
SELECT event_id
FROM source_set
EXCEPT
SELECT event_id
FROM target_set;
```

Kết quả là event IDs có ở source manifest nhưng không có ở target import manifest. Chạy truy vấn ngược `target_set EXCEPT source_set` để phát hiện event ngoài scope hoặc replay trùng run.

Nếu source manifest gồm cả `source_pending` và `source_inflight`, phải resolve hai stage riêng trước khi so. Không đưa event đã acknowledged hoặc expired vào tập expected target trừ khi migration contract nói rõ phải replay chúng.

### 4.4. Phát hiện duplicate trong target

```sql
SELECT
    logical_destination,
    event_id,
    COUNT(*) AS stored_instances
FROM migration_observation
WHERE migration_run_id = 'cutover-2026-11-17'
  AND broker_side = 'target'
  AND stage = 'target_imported'
GROUP BY logical_destination, event_id
HAVING COUNT(*) > 1
ORDER BY stored_instances DESC;
```

Đây là **duplicate message instances** tại snapshot import. Để tìm duplicate business processing, query stage `target_processed` và đảm bảo mỗi event chỉ có một business commit hợp lệ; audit attempts có thể lặp nên cần khóa idempotency ở bảng business/inbox.

### 4.5. Phát hiện payload mismatch

```sql
SELECT
    s.event_id,
    s.payload_sha256 AS source_hash,
    t.payload_sha256 AS target_hash
FROM migration_observation s
JOIN migration_observation t
  ON t.migration_run_id = s.migration_run_id
 AND t.logical_destination = s.logical_destination
 AND t.event_id = s.event_id
WHERE s.migration_run_id = 'cutover-2026-11-17'
  AND s.broker_side = 'source'
  AND s.stage = 'source_pending'
  AND t.broker_side = 'target'
  AND t.stage = 'target_imported'
  AND s.payload_sha256 IS DISTINCT FROM t.payload_sha256;
```

Hash khác nhau có thể do payload bị thay đổi, encoding khác hoặc serializer không canonical. Xác minh hash được tính trên cùng representation; không “sửa” hash để làm báo cáo xanh. Nếu migration có transform schema hợp lệ, lưu `source_hash`, `target_hash`, transform version và mapping để kiểm tra theo contract thay vì đòi hash bằng nhau.

## 5. Đối soát message lặp: phân biệt ba loại duplicate

Từ “duplicate” thường bị dùng cho ba hiện tượng khác nhau:

1. **Duplicate instance:** cùng `eventId` có nhiều bản được lưu ở một queue/target subscription.
2. **Duplicate delivery:** cùng một message được giao lại nhiều lần do rollback, timeout hoặc connection loss; đây là hành vi at-least-once có thể xảy ra.
3. **Duplicate business effect:** cùng một event làm side effect nghiệp vụ được commit nhiều lần; đây là lỗi cần ngăn bằng idempotency.

| Quan sát | Có phải lỗi migration? | Cách xử lý |
| --- | --- | --- |
| Một eventId, hai JMSMessageID ở target import | Có thể là duplicate instance do replay; phải kiểm tra manifest | Deduplicate theo eventId nếu contract cho phép |
| Một JMSMessageID, JMSRedelivered=true ở lần giao sau | Thường là redelivery, không phải hai bản lưu | Kiểm tra rollback/ACK và delivery count |
| Hai lần insert cùng eventId vào business table | Duplicate business effect | Unique constraint/inbox idempotency, đối soát side effect |
| Cùng eventId nhưng payload hash khác | Data mismatch nghiêm trọng hoặc transform chưa được ghi nhận | Dừng replay, kiểm tra source/target bytes và schema |
| Một event có mặt ở nhiều durable topic subscriptions | Có thể đúng semantics pub/sub | Đối soát từng subscription identity |

### 5.1. Idempotency ở consumer

Ví dụ schema inbox trong PostgreSQL:

```sql
CREATE TABLE processed_event (
    event_id       TEXT PRIMARY KEY,
    payload_sha256 CHAR(64) NOT NULL,
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Trong cùng DB transaction với business update, insert event ID trước khi áp dụng side effect:

```sql
INSERT INTO processed_event(event_id, payload_sha256)
VALUES (:event_id, :payload_sha256)
ON CONFLICT (event_id) DO NOTHING;
```

Ứng dụng phải kiểm tra số dòng insert:

- Insert thành công: event mới, tiếp tục xử lý nghiệp vụ trong cùng DB transaction.
- Conflict: event đã xử lý; so hash. Nếu hash giống, có thể bỏ qua duplicate delivery; nếu hash khác, ghi incident và không âm thầm bỏ qua.
- Business update và inbox insert phải commit cùng DB transaction để tránh đánh dấu processed trước khi side effect hoàn tất.

Local JMS transaction và DB transaction **không tự atomic** với nhau. Nếu cần bảo đảm qua hai resource, dùng XA/JTA hoặc transactional inbox/outbox phù hợp; khi dùng inbox, consumer phải phối hợp ACK/retry sao cho message không mất nếu DB commit thành công nhưng JMS commit thất bại.

## 6. Đối soát thứ tự: chỉ kiểm tra trong phạm vi có ordering contract

### 6.1. Không mặc định có global order

Khi tăng consumer concurrency, dùng prefetch, retry message hoặc chuyển broker, thứ tự quan sát toàn queue có thể thay đổi. Nhiều producers cũng không có một total order tự nhiên.

Thường chỉ cần bảo toàn thứ tự theo **ordering key**:

- `orderId`: các event của cùng đơn hàng.
- `accountId`: các thay đổi số dư của cùng tài khoản.
- `aggregateId`: event stream của một aggregate.
- `partition`: một shard/partition được producer tuần tự hóa.

Ví dụ hợp lệ:

```text
order-100:  sequence 1 -> 2 -> 3 -> 4
order-200:  sequence 1 -> 2 -> 3

Interleaving giữa hai order không quan trọng:
order-100/1, order-200/1, order-200/2,
order-100/2, order-100/3, order-200/3, order-100/4
```

Ví dụ lỗi nếu contract yêu cầu order theo `orderId`:

```text
order-100: 1 -> 3 -> 2 -> 4
                 ^ inversion
```

Dùng `sequenceNo` producer cấp cho cùng ordering key; không dùng `JMSMessageID` hoặc timestamp để suy thứ tự.

### 6.2. Query phát hiện inversion

Nếu audit table ghi mỗi lần business processing thành công:

```sql
WITH ordered_events AS (
    SELECT
        logical_destination,
        ordering_key,
        producer_id,
        partition_id,
        event_id,
        sequence_no,
        processed_at,
        LAG(sequence_no) OVER (
            PARTITION BY logical_destination,
                         ordering_key,
                         producer_id,
                         partition_id
            ORDER BY processed_at, observation_id
        ) AS previous_sequence
    FROM migration_observation
    WHERE migration_run_id = 'cutover-2026-11-17'
      AND broker_side = 'target'
      AND stage = 'target_processed'
)
SELECT *
FROM ordered_events
WHERE sequence_no < previous_sequence
ORDER BY logical_destination, ordering_key, processed_at;
```

Query phát hiện gap (chỉ dùng khi sequence được cam kết liên tục cho từng partition/key và không có filter hợp lệ):

```sql
WITH ordered_events AS (
    SELECT
        ordering_key,
        producer_id,
        partition_id,
        sequence_no,
        LAG(sequence_no) OVER (
            PARTITION BY ordering_key, producer_id, partition_id
            ORDER BY sequence_no
        ) AS previous_sequence
    FROM migration_observation
    WHERE migration_run_id = 'cutover-2026-11-17'
      AND broker_side = 'target'
      AND stage = 'target_processed'
)
SELECT *
FROM ordered_events
WHERE previous_sequence IS NOT NULL
  AND sequence_no > previous_sequence + 1;
```

Nếu event bị filter, expired hoặc chưa tới consumer, gap chưa chắc là mất message. So với source manifest/watermark trước khi kết luận. Với nhiều producers cùng ghi một ordering key, cần một sequencer/partition owner; sequence riêng từng producer không tạo total order chung.

### 6.3. Kiểm tra sequence sau cutover

Với mỗi ordering key/partition, tạo bảng kết quả:

| Key | Source last sequence | Target max sequence | Missing sequence | Inversion | Kết luận |
| --- | ---: | ---: | --- | --- | --- |
| order-100 | 120 | 120 | Không | Không | PASS |
| order-200 | 88 | 88 | 86 | Không | Điều tra gap |
| account-9 | 501 | 501 | Không | Có 500 trước 499 | Điều tra inversion |

Không yêu cầu thứ tự toàn cục giữa các keys nếu business contract không yêu cầu. Nếu nghiệp vụ cần total order, phải giữ một consumer/partition serialization strategy tương ứng; tăng consumer không thể tự tạo ra global ordering.

## 7. Đo độ trễ sau migration

### 7.1. Tách latency thành các đoạn

Không chỉ đo “message timestamp đến bây giờ”. Dùng các mốc:

- `eventCreatedAt`: producer tạo business event.
- `sourceAcceptedAt` (nếu capture được): source broker xác nhận nhận message.
- `targetImportedAt`: event đã được ghi vào target.
- `consumerReceivedAt`: consumer đích nhận message.
- `businessCommittedAt`: business side effect đã commit.

Từ đó có thể tính:

```text
migration_gap = targetImportedAt - sourceAcceptedAt
queue_wait    = consumerReceivedAt - targetImportedAt
handler_time  = businessCommittedAt - consumerReceivedAt
end_to_end    = businessCommittedAt - eventCreatedAt
```

Các mốc phải dùng clock đồng bộ (NTP/PTP) hoặc một timebase đáng tin cậy. Nếu source/target host lệch clock, latency có thể âm hoặc sai; không “clamp về 0” rồi coi số liệu đúng. Với handler duration trong cùng process, dùng `System.nanoTime()`.

### 7.2. Broker timestamp không phải business event time

`JMSTimestamp` do provider đặt khi message được gửi theo cấu hình delivery timestamp. Khi replay sang broker mới, timestamp broker có thể thay đổi. Vì thế:

- Giữ `eventCreatedAt` do producer tạo trong custom property/body.
- Lưu `sourceAcceptedAt` và `targetImportedAt` vào audit ngoài message nếu cần so sánh migration gap.
- Không ghi đè `eventCreatedAt` bằng thời điểm replay.
- Ghi `replayAt`/`migrationRunId` thành metadata riêng để phân biệt tuổi business event và tuổi bản replay.

### 7.3. Percentiles và baseline

Đo ít nhất:

| Metric | Ý nghĩa |
| --- | --- |
| End-to-end p50/p95/p99 | Thời gian từ event creation đến business commit |
| Queue wait p50/p95/p99 | Thời gian target import đến consumer receive |
| Handler duration p50/p95/p99 | Thời gian consumer xử lý |
| Oldest message age | Tuổi message chưa xử lý lâu nhất |
| Migration gap | Thời gian từ source acceptance tới target import |
| ACK/commit rate | Số message hoàn tất mỗi giây |
| Redelivery rate | Tỷ lệ delivery attempts không phải lần đầu |

Không chỉ dùng average; p99 có thể xấu dù average tốt. So sánh với baseline trước migration ở cùng workload, payload size, consumer concurrency, persistence và downstream capacity.

Query PostgreSQL tính p95/p99 end-to-end:

```sql
SELECT
    percentile_cont(0.50) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (processed_at - event_created_at)) * 1000
    ) AS p50_ms,
    percentile_cont(0.95) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (processed_at - event_created_at)) * 1000
    ) AS p95_ms,
    percentile_cont(0.99) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (processed_at - event_created_at)) * 1000
    ) AS p99_ms
FROM migration_observation
WHERE migration_run_id = 'cutover-2026-11-17'
  AND broker_side = 'target'
  AND stage = 'target_processed'
  AND event_created_at IS NOT NULL
  AND processed_at IS NOT NULL;
```

Loại bỏ các bản ghi thiếu timestamp, kiểm tra clock skew và chỉ so sánh cùng cohort. Một batch replay cũ có thể có end-to-end age lớn dù queue wait trên broker mới rất thấp; báo cáo riêng hai chỉ số này.

## 8. Java consumer: ghi nhận delivery và business completion đúng nghĩa

Ví dụ sau minh họa cách đọc metadata và đo handler duration. Phần `businessStore.processIdempotently(...)` đại diện một transaction DB có inbox/idempotency; chỉ ghi `target_processed` sau khi business transaction commit.

```java
import java.time.Instant;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageListener;

public final class ReconciliationListener implements MessageListener {

    private final BusinessStore businessStore;
    private final AuditStore auditStore;

    public ReconciliationListener(
            BusinessStore businessStore,
            AuditStore auditStore) {
        this.businessStore = businessStore;
        this.auditStore = auditStore;
    }

    @Override
    public void onMessage(Message message) {
        long started = System.nanoTime();

        try {
            String eventId = message.getStringProperty("eventId");
            String producerId = message.getStringProperty("producerId");
            String orderingKey =
                    message.getStringProperty("orderingKey");
            long sequenceNo = message.getLongProperty("sequenceNo");
            String payloadHash =
                    message.getStringProperty("payloadSha256");

            if (eventId == null || eventId.isBlank()) {
                throw new IllegalArgumentException(
                        "Missing stable eventId");
            }

            boolean redelivered = message.getJMSRedelivered();
            int deliveryCount = message.propertyExists("JMSXDeliveryCount")
                    ? message.getIntProperty("JMSXDeliveryCount")
                    : -1; // Không suy ra số lần giao chỉ từ cờ redelivered.

            Instant receivedAt = Instant.now();

            // Ghi attempt riêng; attempt có thể lặp nếu JMS rollback.
            auditStore.recordDeliveryAttempt(
                    eventId, producerId, orderingKey, sequenceNo,
                    payloadHash, message.getJMSMessageID(),
                    redelivered, deliveryCount, receivedAt);

            // Phải idempotent theo eventId. Method trả về sau DB commit.
            businessStore.processIdempotently(
                    eventId, payloadHash, message);

            long handlerNanos = System.nanoTime() - started;
            auditStore.recordBusinessCommitted(
                    eventId, Instant.now(), handlerNanos);

        } catch (JMSException exception) {
            throw new IllegalStateException(
                    "Cannot read JMS metadata", exception);
        } catch (RuntimeException exception) {
            // Với transacted listener container, exception thoát ra
            // để container rollback theo cấu hình.
            throw exception;
        }
    }
}
```

Đây là listener minh họa cho Spring/JMS container có transaction. Với `AUTO_ACKNOWLEDGE`, exception và redelivery semantics phụ thuộc provider; muốn ACK sau xử lý, cấu hình transacted session/container và kiểm tra rollback behavior.

`AuditStore` nên ghi attempts tách khỏi business completion. Nếu audit store commit độc lập rồi JMS transaction rollback, cùng event có thể có nhiều attempt rows — điều đó đúng. Nhưng không được ghi business completion trước khi business DB transaction thật sự commit.

**Lưu ý transaction boundary:** local JMS transaction và DB transaction riêng không tự atomic. Nếu businessStore dùng DB và listener dùng local JMS transaction, failure giữa DB commit và JMS commit có thể tạo redelivery; inbox unique key xử lý duplicate. Nếu cần atomic đa resource, thiết kế XA/JTA và test recovery hoặc dùng outbox/inbox.

## 9. Phân biệt metrics broker giữa Classic và Artemis

Không map tên counter một-một rồi coi chúng có cùng semantics.

| Mục tiêu | ActiveMQ Classic | ActiveMQ Artemis |
| --- | --- | --- |
| Message còn chờ trong queue | `QueueSize` | `MessageCount` |
| Message đã dispatch nhưng chưa ACK | `InFlightCount` | `DeliveringCount` |
| Consumer hiện tại | `ConsumerCount` | `ConsumerCount` |
| Message được thêm | `EnqueueCount` | `MessagesAdded` |
| Message được xác nhận | `DequeueCount` | `MessagesAcknowledged` |
| Quan sát payload | JMX QueueView/browser hoặc JMS QueueBrowser | Console/Jolokia/QueueControl browse hoặc JMS QueueBrowser |

Các counter là tín hiệu điều tra, không thay manifest event. `QueueSize` và `MessageCount` có thể không bao gồm cùng trạng thái scheduled/paged/in-flight theo cách giống nhau. Queue name cũng có thể đổi khi chuyển từ Classic destination sang Artemis address + queue.

Với **topic**, đo riêng từng durable subscription/queue. Đừng so một topic publication count với tổng số messages trong nhiều subscription queues mà không nhân theo fan-out semantics.

## 10. Tiêu chí chấp nhận sau migration

Acceptance criteria phải được owner nghiệp vụ và vận hành chốt trước cutover. Mẫu dưới đây là cấu trúc, không phải SLA áp dụng cho mọi hệ thống:

| Kiểm tra | Mẫu điều kiện PASS | Nếu FAIL |
| --- | --- | --- |
| Event coverage | Mọi event trong source manifest thuộc scope có target observation hoặc terminal state được giải thích | Dừng mở rộng traffic; tìm event IDs thiếu |
| Unexpected target events | Không có event ngoài scope, trừ producer đã được mở theo watermark mới | Kiểm tra dual-write, replay overlap, wrong destination |
| Duplicate stored instances | Không có duplicate ngoài danh sách replay/at-least-once được duyệt | Dừng replay; deduplicate bằng event ID |
| Business duplicate effects | Unique inbox/business key ngăn side effect lặp | Đối soát và xử lý dữ liệu nghiệp vụ |
| Payload integrity | Hash khớp, hoặc transform version/mapping được phê duyệt | Dừng consumer với event mismatch |
| Ordering | Không gap/inversion trong phạm vi ordering contract | Kiểm tra partitioning, message groups, consumer concurrency |
| Latency | p95/p99 trong ngưỡng SLO đã thống nhất sau warm-up | Giảm ingress, tăng capacity đúng bottleneck |
| DLQ/expiry | Số lượng và nguyên nhân được giải thích, không có spike ngoài dự kiến | Kiểm tra redelivery policy/schema/consumer |
| Recovery | Reconnect/restart không làm mất event hoặc tạo business effect trùng | Giữ nguồn fenced, rollback hoặc chạy reconciliation bổ sung |

Không yêu cầu duplicate delivery bằng 0 trong hệ thống at-least-once nếu có rollback/reconnect hợp lệ. Mục tiêu quan trọng là **không có duplicate business effect** và mọi duplicate instance được nhận diện/giải thích.

### 10.1. Ngưỡng theo giai đoạn

Có thể chia acceptance thành:

- **Gate 1 — Import:** source manifest khớp target imported; payload hash hợp lệ; không có unexplained missing IDs.
- **Gate 2 — Canary processing:** một nhóm event xử lý thành công; ordering theo key và idempotency đạt.
- **Gate 3 — Traffic ramp:** tăng tỷ lệ traffic theo bước; theo dõi ACK rate, queue age, p95/p99 và DLQ.
- **Gate 4 — Source retirement:** chỉ bỏ source sau khi backlog/in-flight đã resolve, audit complete và rollback window kết thúc.

Nếu Gate 1 chưa đạt, không mở consumer đích cho toàn bộ traffic. Nếu Gate 2/3 phát hiện duplicate hoặc order violation, giảm/đóng traffic và giữ source ở trạng thái có thể đối soát.

## 11. Runbook đối soát theo thứ tự

1. **Chốt scope:** broker/source/target, destination mapping, durable subscriptions, message classes và migration run ID.
2. **Chốt watermark:** per producer/partition; ghi source committed, pending, in-flight, DLQ, scheduled, expired.
3. **Tạo source manifest:** event ID, sequence, ordering key, payload hash và original destination.
4. **Chuyển dữ liệu:** ghi batch ID, source count, target accepted count, retry/exception và checkpoint.
5. **Tạo target manifest:** cùng schema observation và stage `target_imported`.
6. **So set difference:** source minus target tìm missing; target minus source tìm unexpected.
7. **So duplicate:** duplicate instances ở target; duplicate deliveries; business duplicate effects.
8. **So payload:** hash hoặc transform mapping cho từng event ID.
9. **So order:** sequence gaps/inversions theo ordering key/partition.
10. **So latency:** migration gap, queue wait, handler time, end-to-end p50/p95/p99.
11. **Chạy canary và traffic ramp:** theo acceptance gates; dừng ngay nếu unexplained loss, payload mismatch hoặc business duplicate.
12. **Lưu bằng chứng:** query results, manifests, dashboards, change ticket, operator, thời gian và quyết định.
13. **Retire source:** sau khi business owner xác nhận và rollback window đóng.

## 12. Các sai lầm khiến báo cáo migration sai

- **Chỉ so queue size:** hai queue cùng count nhưng khác event IDs.
- **Dùng JMSMessageID làm primary key:** broker mới có thể cấp ID mới khi republish.
- **Coi mọi redelivery là duplicate message:** redelivery là một delivery attempt khác của cùng message.
- **Coi duplicate instance là duplicate business effect:** consumer idempotent có thể ngăn side effect lặp.
- **So global order:** nhiều producers/consumers không có global order contract.
- **Dùng timestamp làm sequence:** clock skew và concurrent producers làm thứ tự sai.
- **Bỏ qua durable topic subscriptions:** fan-out khiến số message theo queue khác số publication.
- **Gộp in-flight vào pending:** không biết event đã được giao cho consumer hay chưa.
- **Đếm ACK như business completion:** ACK có thể xảy ra trước DB commit nếu transaction boundary sai.
- **Đo latency bằng JMSTimestamp sau replay:** broker timestamp có thể được tạo lại.
- **Tính average thay p95/p99:** tail latency bị che khuất.
- **Mở source và target consumers đồng thời không idempotency:** duplicate processing khi overlap.
- **Xóa source ngay khi target count khớp:** chưa có bằng chứng event-level và rollback window.

## 13. Checklist hoàn tất đối soát

- [ ] Đã xác định destination mapping và từng durable topic subscription.
- [ ] Có migration run ID và watermark per producer/partition.
- [ ] Source manifest phân biệt pending, in-flight, acknowledged, scheduled, expired và DLQ.
- [ ] Mỗi business event có stable `eventId`; không phụ thuộc `JMSMessageID`.
- [ ] Producer/consumer observations có sequence, ordering key và payload hash.
- [ ] Source minus target và target minus source đã được truy vấn.
- [ ] Duplicate instance, duplicate delivery và duplicate business effect được báo riêng.
- [ ] Payload mismatch đã được điều tra hoặc có transform mapping được duyệt.
- [ ] Ordering được kiểm tra theo key/partition, không áp global order vô căn cứ.
- [ ] p50/p95/p99 latency tách migration gap, queue wait và handler time.
- [ ] Clock sync và timestamp source/target đã được kiểm tra.
- [ ] DLQ, expiry, scheduled và non-durable topic behavior đã được đối soát.
- [ ] Canary processing và traffic ramp đạt acceptance gates.
- [ ] Business owner ký xác nhận trước khi retire source.
- [ ] Evidence, audit và rollback window được lưu theo retention policy.

## Tài liệu tham khảo

1. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): message headers/properties, delivery, acknowledgment và durable subscriptions.
2. [Jakarta Messaging API — Message](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message): `JMSMessageID`, `JMSCorrelationID`, `JMSTimestamp`, `JMSRedelivered` và properties.
3. [ActiveMQ Classic — JMX](https://activemq.apache.org/components/classic/documentation/jmx): destination statistics và queue management.
4. [ActiveMQ Artemis — Management](https://artemis.apache.org/components/artemis/documentation/latest/management.html): QueueControl và address/queue metrics.
5. [ActiveMQ Artemis — Metrics](https://artemis.apache.org/components/artemis/documentation/latest/metrics.html): broker, address, queue và runtime metrics.
6. [ActiveMQ Artemis — Clustering](https://artemis.apache.org/components/artemis/documentation/latest/clusters.html): routing, redistribution và topology behavior.
7. [PostgreSQL — Aggregate Functions](https://www.postgresql.org/docs/current/functions-aggregate.html): COUNT(DISTINCT ...) và percentile_cont.
