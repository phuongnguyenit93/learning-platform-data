# At-most-once, at-least-once và phạm vi của tuyên bố exactly-once

Trong hệ thống NoSQL, một thay đổi nghiệp vụ có thể tạo sự kiện được truyền qua Kafka, MongoDB Change Streams, DynamoDB Streams, Cassandra CDC hoặc transactional outbox. Consumer nhận sự kiện để cập nhật search index, ghi báo cáo, cộng điểm thưởng hoặc gửi thông báo. Điểm khó xuất hiện khi **consumer đã commit hiệu ứng nhưng mất kết nối trước khi xác nhận với broker**: broker có thể giao lại cùng message. Nếu handler không chống lặp, một ý định nghiệp vụ bị xử lý hai lần.

**At-most-once**, **at-least-once** và **exactly-once** là các bảo đảm về số lần giao hoặc xử lý một đơn vị công việc **trong một phạm vi xác định**. Chúng không phải ba chế độ có thể áp dụng vô điều kiện từ database nguồn qua broker tới mọi hệ bên ngoài.

Trong chương **Sự kiện và CDC** thuộc module **Database No SQL**, bài học này phân tích message delivery, handler execution và business effect; các lịch crash/ACK; outbox, CDC, inbox, Kafka transactions, event ordering, replay, retention, external side effects, cùng ví dụ Java, SQL và bài tập.

> **Nguyên tắc:** khi đọc một tuyên bố “exactly-once”, hãy hỏi: **“Chính xác một lần đối với cái gì, tại ranh giới commit nào, và với các giả định gì về retry, retention và lỗi?”**

## 1. Một sự kiện có thể được quan sát ở nhiều tầng

Booking Service phát:

~~~json
{
  "eventId": "evt-801",
  "eventType": "ReservationConfirmed",
  "reservationId": "res-420",
  "aggregateVersion": 12,
  "occurredAt": "2026-11-14T08:00:00Z",
  "data": {
    "listingId": "L42",
    "status": "CONFIRMED"
  }
}
~~~

~~~text
Booking DB → Outbox/CDC → Event broker
                               |
                               +→ Search projector
                               +→ Loyalty database
                               +→ Email provider
                               +→ Analytics warehouse
~~~

Đối với `evt-801`, có năm con số:

1. Broker **giao message** bao nhiêu lần?
2. Java handler `onEvent` **được gọi** bao nhiêu lần?
3. Loyalty DB **commit điểm thưởng** bao nhiêu lần?
4. Email provider **nhận yêu cầu gửi** bao nhiêu lần?
5. Booking Service đã **xác nhận ý định đặt chỗ** bao nhiêu lần?

Các con số này có thể khác nhau. Handler được gọi ba lần nhưng database chỉ commit một lần là một trường hợp **giao lại message nhưng business effect không trùng**.

## 2. Ba tầng ngữ nghĩa cần phân biệt

| Tầng | Thứ được đếm | Ví dụ |
| --- | --- | --- |
| Delivery semantics | Lần broker/source giao message | Event E được giao lại |
| Execution semantics | Lần computation/handler chạy | `onEvent(E)` chạy hai lần |
| Effect semantics | Lần thay đổi trạng thái được commit | Một hàng award được tạo |

Không nên nói mơ hồ “consumer xử lý đúng một lần” nếu không làm rõ đang nói **method invocation**, **database transaction** hay **external API side effect**.

Một tuyên bố chính xác hơn:

> Broker chuyển events theo at-least-once delivery. Loyalty consumer dùng unique inbox marker và cập nhật điểm trong cùng transaction nên một event ID chỉ tạo tối đa một hiệu ứng tại Loyalty DB.

Đó là bảo đảm **effect-once trong phạm vi Loyalty DB**, không phải exactly-once delivery trên mạng.

## 3. At-most-once: không trùng nhưng có thể mất

At-most-once delivery:

\[
\operatorname{deliveryCount}(m)\in\{0,1\}
\]

Một consumer commit offset trước khi thực hiện effect:

~~~text
Broker                  Consumer                 Database
   |                        |                        |
   |------ Event E -------->|                        |
   |<-- ACK offset E -------|                        |
   |                        X crash                  |
   |                                                 |
   |                  Business effect chưa xảy ra     |
~~~

Khi restart, consumer bắt đầu sau offset E. **E có thể mất về mặt xử lý**, dù không có duplicate.

### Sử dụng phù hợp

- Một số telemetry/sample metrics có thể chấp nhận mất.
- Trạng thái có thể tính lại từ nguồn khác.
- Tình huống mà xử lý lặp còn nguy hiểm hơn bỏ một thông tin không quan trọng.

Đây không phải lựa chọn mặc định cho payment ledger, booking confirmation hoặc dữ liệu không được phép bỏ sót.

## 4. At-least-once: không bỏ qua theo giả định, nhưng có thể lặp

At-least-once delivery:

\[
\operatorname{deliveryCount}(m)\ge1
\]

với điều kiện nguồn/broker đã lưu bền, message còn trong retention, consumer có thể phục hồi, retry còn hoạt động và không bị partition vĩnh viễn.

~~~text
Broker                  Consumer                 Database
   |                        |                        |
   |------ Event E -------->|                        |
   |                        |--- COMMIT effect ----->|
   |                        |<--------- OK ----------|
   |                        X crash trước ACK        |
   |                                                 |
   |------ Redeliver E ---->|                        |
   |                        |--- effect lần nữa? ---->|
~~~

Nếu handler là `points += 100`, hai lần commit tạo **200 điểm** thay vì 100.

### Giới hạn của câu “ít nhất một lần”

Không thể hứa liveness vô điều kiện: broker có thể mất bản ghi chưa durable, retention hết trước khi replay, consumer luôn lỗi ở poison event hoặc mất quyền truy cập. Vì vậy phải công bố **failure assumptions, retry policy và recovery plan**.

## 5. Exactly-once: bảo đảm phải có phạm vi

Với một business effect định nghĩa rõ, mục tiêu:

\[
\operatorname{committedEffects}(m)=1
\]

gồm hai phần:

- **Safety:** không commit hơn một lần.
- **Liveness:** cuối cùng commit ít nhất một lần, với các điều kiện hệ có khả năng hoàn tất.

Ví dụ:

~~~text
Broker delivers E three times
   |
   +→ Attempt 1: atomic INSERT inbox + UPDATE points → COMMIT
   +→ Attempt 2: inbox conflict → NO-OP
   +→ Attempt 3: inbox conflict → NO-OP
~~~

Ba handler executions có thể tương ứng với **một committed business effect**.

### Những điều không tự được bảo đảm

Một transaction Kafka không tự bao gồm PostgreSQL, MongoDB, Redis, email hay payment provider. Mỗi nơi có commit/ACK riêng. Đừng diễn đạt “exactly-once end-to-end” nếu không chỉ ra cách xử lý từng ranh giới.

## 6. Bảng so sánh ba ngữ nghĩa

| Thuộc tính | At-most-once | At-least-once | Exactly-once effect trong phạm vi xác định |
| --- | --- | --- | --- |
| Có thể mất message/effect? | Có | Không khi liveness assumptions giữ | Không khi công việc hợp lệ cuối cùng hoàn tất |
| Delivery có thể lặp? | Không trong delivery scope | Có | Có thể |
| Handler có thể chạy lại? | Tùy cách triển khai/scope | Có | Có thể |
| Business effect có thể lặp? | Không nếu không retry | Có nếu không idempotent | Không trong boundary được chứng minh |
| Cơ chế phổ biến | ACK/checkpoint trước xử lý | ACK sau xử lý, retry | Atomic dedupe+effect hoặc transaction protocol |

Số lượng messages ít không chứng minh hệ “tốt hơn”. Độ trễ, correctness, throughput và chi phí transaction mới quyết định tradeoff theo nghiệp vụ.

## 7. ACK là ACK của việc gì?

~~~text
Producer → Broker ACK
Consumer → Broker offset commit
Database → Caller transaction ACK
Provider → Service HTTP response
~~~

| Tín hiệu | Nói lên điều gì | Không tự nói lên |
| --- | --- | --- |
| Broker nhận record | Record được accept theo broker policy | Sink đã xử lý |
| Offset commit | Group nhớ tiến độ | Effect DB đã commit |
| Database ACK | DB báo commit theo consistency/durability policy | Caller nhận response chắc chắn |
| Payment API response | Provider báo trạng thái theo hợp đồng | Có transaction chung với broker |

Một log `ACKed` không đầy đủ nếu thiếu bên phát/nhận, trạng thái trước và sau ACK, durability và business identity.

## 8. Timeout tạo ra unknown outcome

~~~text
Lịch A:
  Request bị mất trước khi tới server.
  Không có effect.

Lịch B:
  Server COMMIT effect.
  Response bị mất trên đường về.
~~~

Caller chỉ thấy cùng một `TimeoutException`. Không thể kết luận chắc việc chưa xảy ra.

~~~text
Client                       Server
  |-------- request --------->|
  |                            | COMMIT
  |<-------- response -----X   |
  | timeout                    |
~~~

Retry phải dùng **stable operation identity**. Nếu mỗi retry tạo một `requestId` mới, server có thể coi đó là một ý định nghiệp vụ khác.

### Ba loại identity

- `eventId`: định danh một event logic.
- `businessIntentId` hoặc `idempotencyKey`: định danh ý định nghiệp vụ.
- `aggregateVersion`: thứ tự committed state của một aggregate.

Ba giá trị này có chức năng khác nhau; không thay thế tùy tiện.

## 9. At-most-once theo thứ tự commit offset trước

~~~text
1. Fetch E at offset 52.
2. Commit offset 53.
3. Process E.
~~~

Crash ở bước 2–3: E có thể bị bỏ qua vĩnh viễn. Nếu nghiệp vụ không chịu được mất event, đây là protocol không phù hợp.

## 10. At-least-once theo thứ tự commit offset sau

~~~text
1. Fetch E at offset 52.
2. Process E and COMMIT sink effect.
3. Commit offset 53.
~~~

Crash ở bước 2–3: effect đã xảy ra, offset chưa tiến, E bị giao lại.

Rebalance, ACK loss hoặc consumer quá chậm cũng có thể gây redelivery. **Offset quản lý progress, không phải khóa chống trùng của sink database**.

## 11. Các cửa sổ lỗi trên pipeline

~~~text
Source DB → Outbox → CDC/Relay → Broker → Consumer → Sink
     A          B         C        D         E        F
~~~

| Điểm lỗi | Ví dụ | Cần bảo vệ gì? |
| --- | --- | --- |
| A | Source transaction rollback | Không phát event thành công giả |
| B | DB commit rồi process crash | Outbox record phải còn |
| C | Broker ACK mất sau publish | Stable event ID, retry/dedupe |
| D | Broker retention hết | Replay/rebuild/reconciliation |
| E | Handler crash trước effect commit | Retry không làm mất ý định |
| F | Sink COMMIT rồi crash trước offset ACK | Atomic idempotency |

**Một ACK ở C không bảo đảm effect ở F.** Test một lỗi mạng chung chưa thay thế được việc tiêm lỗi ngay tại từng ranh giới.

## 12. Transactional outbox

Mẫu dual-write không an toàn:

~~~text
UPDATE reservation in DB
COMMIT
PUBLISH ReservationConfirmed
~~~

Nếu crash sau COMMIT trước PUBLISH, business state đã thay đổi nhưng event không được phát.

Mẫu outbox:

~~~text
BEGIN source DB transaction
  UPDATE reservation = CONFIRMED
  INSERT outbox(eventId, type, payload)
COMMIT

Later: relay or CDC publishes outbox record
~~~

Source business state và event intent commit **trong cùng một local transaction**. Nhưng việc publish broker vẫn ở ngoài transaction đó.

### Tại sao relay có thể phát trùng?

~~~text
T0: Read outbox event E.
T1: Publish E, broker ACK.
T2: Crash before marking E published.
T3: Restart and publish E again.
~~~

Đó là lịch hợp lệ của at-least-once relay. Consumer phải xử lý duplicate.

## 13. SQL minh họa outbox

~~~sql
CREATE TABLE reservation (
    reservation_id UUID PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    reservation_id UUID NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ
);
~~~

Một transaction logic:

~~~sql
BEGIN;

UPDATE reservation
SET status = 'CONFIRMED', version = version + 1
WHERE reservation_id =
    '11111111-1111-4111-8111-111111111111'
  AND status = 'PENDING'
RETURNING version;

-- Nếu không update đúng một row: ROLLBACK.
-- Phải sử dụng version thực từ RETURNING.

INSERT INTO outbox_event (
  event_id, reservation_id, aggregate_version,
  event_type, payload
) VALUES (
  '22222222-2222-4222-8222-222222222222',
  '11111111-1111-4111-8111-111111111111',
  12,
  'ReservationConfirmed',
  '{"reservationId":"11111111-1111-4111-8111-111111111111",
    "version":12}'::jsonb
);

COMMIT;
~~~

**Lưu ý:** version 12 là giá trị minh họa. Implementation thật phải dùng giá trị `RETURNING` đã commit, không hardcode. Retry request nguồn cần `request_id` ổn định, kiểm state transition và idempotency.

## 14. CDC: Change Data Capture

CDC thu các changes đã commit từ log/change stream của database:

~~~text
Authoritative DB
      |
      v
Commit log / change stream
      |
      v
CDC connector
      |
      v
Broker topic
      |
      v
Consumer
~~~

Outbox và CDC **không đối lập**: một ứng dụng có thể ghi outbox trong transaction; CDC phát những outbox rows đã commit.

### Các lịch checkpoint

Nếu CDC connector publish E rồi crash **trước khi lưu source offset**, nó có thể publish E lần nữa. Nếu checkpoint **trước publish**, crash có thể bỏ sót E.

CDC còn phụ thuộc retention của source log, ordering theo shard/partition, khả năng resume và snapshot bootstrap. Một raw row change không tự là domain event có schema/ngữ nghĩa ổn định.

## 15. Snapshot và CDC cùng lúc

Khi backfill projection:

~~~text
T0: Snapshot reads product version 10.
T1: Source commits version 11.
T2: CDC version 11 arrives at sink.
T3: Snapshot version 10 arrives late.
~~~

Nếu sink upsert theo arrival order, state có thể đi lùi v11 → v10.

**Đây là out-of-order giữa hai updates hợp lệ**, không phải duplicate cùng một event ID. Cần snapshot watermark, version guard, CDC catch-up và reconciliation theo protocol.

## 16. Transactional inbox

Ở sink, một mẫu effect-once:

~~~text
Consumer receives E
       |
       v
BEGIN sink DB transaction
  INSERT unique processed_event(consumer, eventId)
  IF marker newly inserted:
      apply business mutation
  ELSE:
      skip duplicate
COMMIT
       |
       v
ACK broker offset
~~~

**Marker và effect phải commit trong cùng atomic boundary.** Nếu marker nằm ở Redis còn effect ở PostgreSQL, hai writes độc lập có thể gây partial success hoặc false completed.

## 17. SQL inbox và ledger mutation

~~~sql
CREATE TABLE processed_event (
    consumer_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    payload_hash TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE booking_stats (
    listing_id TEXT PRIMARY KEY,
    confirmed_count BIGINT NOT NULL DEFAULT 0
);
~~~

Giao thức:

~~~sql
BEGIN;

INSERT INTO processed_event(
    consumer_name, event_id, payload_hash
) VALUES (
    'booking-analytics',
    '22222222-2222-4222-8222-222222222222',
    'canonical-payload-hash'
)
ON CONFLICT DO NOTHING;

-- Chỉ nếu INSERT affected row count = 1
-- mới được thực hiện mutation bên dưới.

INSERT INTO booking_stats(listing_id, confirmed_count)
VALUES ('L42', 1)
ON CONFLICT (listing_id)
DO UPDATE SET confirmed_count =
    booking_stats.confirmed_count + 1;

COMMIT;
~~~

**Đoạn UPDATE là conditional application step**, không được chạy vô điều kiện sau insert conflict. Nếu eventId đã tồn tại với **payload hash khác**, phải báo lỗi integrity/quarantine thay vì im lặng bỏ qua.

### Crash trước COMMIT

Marker và effect đều rollback; E retry hợp lệ.

### Crash sau COMMIT, trước ACK

Broker redeliver E; unique marker conflict, effect không lặp.

Đây là bảo đảm cho **một sink DB transaction**, không phải toàn bộ email/payment workflow.

## 18. Race của hai consumer workers

Một lỗi check-then-act:

~~~text
Worker A: SELECT marker E → absent
Worker B: SELECT marker E → absent
Worker A: UPDATE points +100
Worker B: UPDATE points +100
~~~

Chỉ SELECT trước rồi update không an toàn. Dùng **unique conditional INSERT/CAS** trong cùng transaction với business mutation.

Trong NoSQL, một atomic single-document update chỉ bảo vệ phạm vi document được DBMS hứa. Marker và effect ở **hai documents** có thể đòi multi-document transaction hoặc thiết kế aggregate khác. Lock TTL cũng không thay unique effect guard vì worker cũ có thể trở lại sau lease expiry.

## 19. Java demo ba lịch xử lý

Ví dụ sau chạy với Java 17+, mô phỏng **at-most-once mất effect**, **at-least-once gây lặp** và **at-least-once delivery với inbox chống lặp effect**.

Tạo file `DeliverySemanticsDemo.java`:

~~~java
import java.util.HashSet;
import java.util.Set;

public final class DeliverySemanticsDemo {
    record Event(String id, int points) {}

    static final class NaiveSink {
        private int points;

        void apply(Event event) {
            points += event.points();
        }

        int value() {
            return points;
        }
    }

    static final class InboxSink {
        private final Set<String> processed = new HashSet<>();
        private int points;

        synchronized boolean applyOnce(Event event) {
            if (processed.contains(event.id())) {
                return false;
            }
            // Chỉ là atomic critical section trong JVM.
            points += event.points();
            processed.add(event.id());
            return true;
        }

        synchronized int value() {
            return points;
        }
    }

    public static void main(String[] args) {
        Event event = new Event("evt-801", 100);

        // ACK trước effect, rồi crash:
        NaiveSink atMostOnce = new NaiveSink();
        System.out.println("At-most-once points="
                + atMostOnce.value());

        // Effect trước ACK, crash, sau đó redeliver:
        NaiveSink atLeastOnce = new NaiveSink();
        atLeastOnce.apply(event);
        atLeastOnce.apply(event);
        System.out.println("At-least-once points="
                + atLeastOnce.value());

        // Handler vẫn chạy lại; effect chỉ apply một lần.
        InboxSink guarded = new InboxSink();
        boolean first = guarded.applyOnce(event);
        boolean again = guarded.applyOnce(event);
        System.out.println("Inbox first=" + first
                + ", redeliveryApplied=" + again
                + ", points=" + guarded.value());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac DeliverySemanticsDemo.java
java DeliverySemanticsDemo
~~~

Kết quả minh họa:

~~~text
At-most-once points=0
At-least-once points=200
Inbox first=true, redeliveryApplied=false, points=100
~~~

### Giới hạn

- Không có broker/network/disk/transaction DB thật.
- `HashSet` không durable qua restart, `synchronized` chỉ bảo vệ một JVM.
- Production phải dùng marker và effect trong cùng durable transaction/conditional state.
- Demo không chứng minh exactly-once delivery; nó minh họa **effect-once** khi có dedupe.

## 20. JDBC skeleton atomic inbox

Ví dụ cho PostgreSQL:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;

final class AnalyticsConsumer {
    static boolean applyOnce(Connection db, UUID eventId,
                             String listingId, String payloadHash)
            throws SQLException {
        db.setAutoCommit(false);
        try {
            int inserted;
            try (PreparedStatement claim = db.prepareStatement(
                    "INSERT INTO processed_event "
                  + "(consumer_name,event_id,payload_hash) "
                  + "VALUES ('booking-analytics',?,?) "
                  + "ON CONFLICT DO NOTHING")) {
                claim.setObject(1, eventId);
                claim.setString(2, payloadHash);
                inserted = claim.executeUpdate();
            }
            if (inserted == 0) {
                // Production: verify stored payload hash.
                db.commit();
                return false;
            }
            try (PreparedStatement update = db.prepareStatement(
                    "INSERT INTO booking_stats "
                  + "(listing_id,confirmed_count) VALUES (?,1) "
                  + "ON CONFLICT (listing_id) DO UPDATE SET "
                  + "confirmed_count = "
                  + "booking_stats.confirmed_count + 1")) {
                update.setString(1, listingId);
                update.executeUpdate();
            }
            db.commit();
            return true;
        } catch (SQLException | RuntimeException failure) {
            try {
                db.rollback();
            } catch (SQLException rollbackError) {
                failure.addSuppressed(rollbackError);
            }
            throw failure;
        }
    }
}
~~~

Đây là **skeleton**: caller quản lý connection lifecycle/restore auto-commit; code thật phải triển khai kiểm hash khi duplicate, quản lý isolation và chỉ ACK broker **sau** sink transaction. Không đặt external HTTP side effects vào một SQL transaction rồi mặc định chúng nguyên tử cùng DB.

## 21. Inbox retention và replay horizon

~~~text
Day 1:  E processed; inbox marker stored.
Day 8:  Marker expired (7-day TTL).
Day 20: Operator replays E from 30-day broker log.
~~~

Nếu effect là `counter += 1`, E có thể bị cộng lần nữa. Cần:

- Dedupe retention tương thích với max replay/redelivery horizon.
- Hoặc business-unique ledger keys có vòng đời đủ dài.
- Hoặc replay vào **projection mới** rồi cutover, không cộng vào kết quả cũ.
- Reconciliation để phát hiện duplicate sau manual replay.

**Inbox TTL là một phần của hợp đồng consistency**, không chỉ tối ưu dung lượng.

## 22. Event ID khác business intent ID

Client retry thanh toán sai:

~~~text
Payment intent P1 captured.
HTTP ACK lost.
Client retries with NEW intent P2.
P2 captured.

Event A: PaymentCaptured(P1), eventId=evt-101
Event B: PaymentCaptured(P2), eventId=evt-102
~~~

Inbox theo eventId thấy **hai events khác nhau** và không ngăn double charge.

Phải bảo vệ ở payment authority bằng **stable business idempotency key**, unique intent/payment state và reconciliation. Event ID chống duplicate delivery; business ID chống duplicate ý định.

## 23. Ordering độc lập với deduplication

Source:

~~~text
Inventory v10: remaining=3
Inventory v11: remaining=2
Inventory v12: remaining=1
~~~

Consumer nhận `v12, v10, v11`. Không có event ID lặp nhưng nếu blind-upsert theo arrival, kết quả có thể đi lùi.

Ba lớp bảo vệ:

1. **Dedupe event ID:** ngăn cùng event tạo hiệu ứng hai lần.
2. **Version/order:** ngăn event cũ ghi đè trạng thái mới.
3. **Gap/completeness:** phát hiện sự kiện trung gian bị thiếu.

### Snapshot khác delta

`SetRemaining(1,version=12)` có thể thay thế snapshots cũ nếu payload đủ. `Decrement(1,version=12)` là delta: bỏ version 11 có thể tạo state sai. Cần replay/gap handling và atomic update theo semantics.

## 24. Kafka idempotent producer và transactions

Trong Apache Kafka:

- **Idempotent producer:** broker có thể tránh duplicate records từ producer retry cùng batch theo producer identity/sequence trong điều kiện hỗ trợ.
- **Transactional producer:** ghi nhiều Kafka records với commit/abort visibility.
- **Consumer offsets trong transaction:** processor Kafka→Kafka có thể commit outputs và source offsets cùng Kafka transaction.
- **`read_committed`:** consumer không đọc những transactional records đã abort theo protocol.

Producer idempotence **không ngăn code tự phát hai business events khác nhau** cho một ý định. Kafka transaction cũng không đưa PostgreSQL, Redis hay payment provider vào cùng commit boundary.

## 25. Kafka exactly-once processing cho Kafka→Kafka

~~~text
Topic IN → Consumer/Transformer → Topic OUT
             |
             + Kafka transaction:
                 output records
                 consumed offsets
~~~

Processor về logic:

~~~text
beginTransaction
produce output for IN offset 52
send source offset 53 in same transaction
commitTransaction
~~~

Crash trước transaction commit: outputs chưa commit bị abort/fenced theo protocol; offsets chưa commit; processor có thể đọc lại input.

Commit thành công: outputs và consumed offsets được ghi trong một transaction Kafka, với isolation/fencing/consumer group cấu hình phù hợp.

**Phạm vi tuyên bố là Kafka records và offsets của pipeline Kafka→Kafka**, không mặc nhiên bao gồm sink external.

## 26. Kafka transaction không bao gồm external DB

~~~text
1. Consume Kafka E.
2. UPDATE PostgreSQL points += 100; COMMIT.
3. Produce output and COMMIT Kafka transaction.
~~~

Crash sau bước 2 nhưng trước bước 3:

~~~text
PostgreSQL effect: committed.
Kafka input offset: not committed.
Replay E: possible.
~~~

Nếu không có inbox tại PostgreSQL, effect bị cộng lại. Dùng sink transaction unique marker hoặc một protocol phân tán được các participants hỗ trợ nếu cần atomicity xuyên hệ.

**Kafka EOS không tự tạo PostgreSQL EOS.**

## 27. Framework xử lý luồng có giới hạn gì?

Flink/Kafka Streams/connector frameworks có thể cung cấp exactly-once processing cho **source positions, state và sinks tương thích**.

Trước khi tin nhãn này, hỏi:

1. Checkpoint gồm những gì?
2. Output sink có transaction/commit protocol tham gia checkpoint không?
3. Nếu callback gọi HTTP POST không idempotent, framework có thể rollback POST không?
4. Crash sau side effect trước checkpoint gây gì?
5. Retention/replay nhiều ngày có vượt dedupe window không?

**Guarantee của framework chỉ đúng với các connectors và transaction boundaries mà nó thực sự điều phối.**

## 28. NoSQL change streams và checkpoint semantics

- **MongoDB Change Streams:** resume token giúp tiếp tục đọc, nhưng thời điểm lưu token so với sink commit tạo tradeoff loss/duplicate; cần xem retention/change stream guarantees.
- **DynamoDB Streams:** sequence/shards, retention và consumer qua Lambda/KCL hoặc code tùy chọn có retry/checkpoint semantics riêng.
- **Cassandra CDC:** ordering và replay phụ thuộc log/connector/phiên bản; raw row change không tự là business event atomic xuyên nhiều bảng.

Đối với bất kỳ nguồn nào:

~~~text
Where did source COMMIT?
Can the source replay?
Which key identifies each event?
Where is the checkpoint?
Where does sink COMMIT?
What if retention expires?
~~~

## 29. Batches và partial progress

Consumer xử lý E1–E100, commit E1–E60, crash trước ACK batch. Broker có thể giao lại cả E1–E100.

Các lựa chọn:

- Per-event atomic inbox+effect.
- Batch transaction trong cùng sink DB nếu phù hợp.
- Idempotent business keys.
- Bounded batch/checkpoint sau durable work.
- Retry/poison message handling.

Không giữ một `batchProcessed=true` trong RAM rồi cho rằng crash không thay đổi kết quả.

## 30. In-progress marker khác completed marker

Lỗi:

~~~text
1. Write inbox(E, IN_PROGRESS).
2. Crash before effect.
3. Retry sees marker and skips E.
~~~

Nếu marker/hiệu ứng không cùng transaction, cần state machine:

~~~text
CLAIMED → COMPLETED
       ↘ FAILED_RETRYABLE
       ↘ FAILED_PERMANENT
~~~

Có lease/recovery cho việc đang xử lý, nhưng worker cũ có thể resume sau lease expiry. Vì vậy vẫn cần fencing hoặc idempotent effect tại sink.

## 31. External payment và notification

### Payment

Một payment API timeout có thể là **request chưa tới** hoặc **đã capture nhưng ACK mất**. Retry với intent ID mới có thể thu tiền hai lần. Cần stable provider idempotency key, state lookup, workflow log và reconciliation.

### Notification

Provider báo email `202 Accepted` có thể chỉ nghĩa là **đã queue**, không chứng minh user chỉ nhận một email vật lý. Có thể bảo đảm **một notification intent trong database**, nhưng actual delivery còn phụ thuộc provider và network.

**Không quảng bá exactly-once payment/email end-to-end khi không có bằng chứng từ từng external boundary.**

## 32. Poison events và liveness

Một event sai schema:

~~~json
{
  "eventId": "bad-55",
  "eventType": "PaymentCaptured",
  "amountMinor": "not-a-number"
}
~~~

Consumer retry mãi nhưng luôn parse fail. Pipeline có thể kẹt.

Thiết kế:

- Phân biệt transient và deterministic errors.
- Retry có budget/backoff.
- Quarantine/DLQ với owner, lý do, khả năng replay.
- Sửa producer/consumer và xử lý lại event cần thiết.
- Không âm thầm commit offset/skip một business-critical event rồi tiếp tục hứa “at-least-once effect” không ngoại lệ.

## 33. Consumer group rebalance

~~~text
Worker A owns partition P.
A processes E slowly.
Group rebalances P to B.
B processes E from last committed offset.
A resumes and tries to commit.
~~~

Hai workers có thể cùng cố tạo effect. Partition ownership không phải khóa tuyệt đối ở external database. Cần unique/conditional effect guard, cancellation/fencing và idempotency.

Trong multi-partition streams, ordering chỉ được bảo đảm trong phạm vi partition/protocol tương ứng, **không có total order chung cho mọi aggregates**. Chọn partition key theo aggregate nếu business ordering cần.

## 34. Observability: theo dõi effect, không chỉ messages

| Metric | Điều phản ánh |
| --- | --- |
| Outbox oldest pending age | Event intent đang kẹt |
| CDC lag/source position | Connector còn cách commit nguồn bao xa |
| Broker consumer lag | Records chưa tiêu thụ |
| Delivery attempts per event | Redelivery/duplicates |
| Inbox conflict rate | Dedupe hoạt động |
| Sink commits/failures | Hiệu ứng đã commit hay chưa |
| Offset/checkpoint age | Progress được lưu bền |
| DLQ size/oldest age | Poison events chưa sửa |
| Applied aggregate version | State projection theo kịp nguồn? |
| Source/sink reconciliation drift | Mất/trùng business effects |

Trace nên nối `businessIntentId`, `sourceCommitId`, `eventId`, `brokerPartition/Offset`, `sinkTransactionId`, `inboxResult` và `offsetCommitStatus`.

Đừng log dữ liệu thanh toán nhạy cảm hoặc PII chỉ để theo dõi retries.

## 35. Fault matrix cần chạy trong lab

| ID | Fault injection | Kỳ vọng |
| --- | --- | --- |
| F1 | Producer crash trước broker accept | Retry/repair theo source intent |
| F2 | Publish thành công nhưng ACK lost | Event có thể publish lại cùng ID |
| F3 | Source commit rồi app crash trước publish | Outbox/CDC phục hồi |
| F4 | Relay publish rồi crash trước published flag | Consumer dedupe |
| F5 | Consumer crash trước sink COMMIT | Marker/effect rollback, retry |
| F6 | Consumer crash sau sink COMMIT trước offset ACK | Redelivery nhưng effect không lặp |
| F7 | Hai workers xử lý E đồng thời | Unique marker thắng một lần |
| F8 | Event v12 tới trước v11 | Version/gap handling |
| F9 | Snapshot v10 tới sau CDC v11 | Không ghi đè bản mới |
| F10 | Rebalance khi worker A đang commit | Late worker không duplicate effect |
| F11 | CDC retention hết trước recovery | Phát hiện gap, rebuild |
| F12 | Replay sau inbox TTL | Phát hiện giới hạn dedupe |
| F13 | Payment provider commit, HTTP ACK lost | Stable payment intent và status query |
| F14 | Poison event luôn fail | DLQ/remediation, không kẹt vô hạn |

**Mỗi test cần oracle từ authoritative business state**, không chỉ đếm số messages được ACK.

## 36. Reconciliation theo business identity

Giả sử source có 1.000 confirmed reservations và sink ACK 1.000 events. Không thể kết luận đúng 1.000 effects: một reservation có thể bị bỏ sót, một reservation khác bị đếm hai lần.

Đặt invariant ví dụ:

\[
\forall r\in ConfirmedReservations:
\quad \operatorname{loyaltyAwardCount}(r)=1
\]

nếu mỗi confirmed reservation được thưởng đúng một lần. Nếu có nhiều chiến dịch, identity có thể là `(reservationId,campaignId)`.

Reconciliation nên so **tập IDs, versions và ledger rows**, không chỉ total count. Khi dữ liệu lớn, dùng partitioned comparisons/checksums, sampling và targeted repair với giới hạn tải.

## 37. Mẫu mô tả bảo đảm xử lý

~~~yaml
pipeline: "booking-to-loyalty"
source:
  authority: "booking database"
  eventIntent: "transactional outbox"
  capture: "CDC of committed outbox"
delivery:
  semantics: "at-least-once under retention/recovery assumptions"
consumer:
  name: "loyalty"
  dedupeKey: ["consumer", "eventId"]
  effectBoundary: "loyalty DB transaction"
  effectGuard: "unique business award ID"
  checkpoint: "after sink commit"
guarantees:
  safety: "at most one award per business key"
  liveness: "eventual processing under stated assumptions"
exclusions:
  - "Network delivery and handler execution may repeat"
  - "External email and payment effects not covered"
operations:
  - "DLQ/replay and reconciliation"
  - "Inbox retention aligned to replay horizon"
~~~

Đây là mô tả phạm vi/điều kiện, không phải cấu hình cắm thẳng vào broker. Nó có ý nghĩa hơn một cờ `exactlyOnce: true` không nêu transaction boundary.

## 38. Những hiểu lầm thường gặp

| Hiểu lầm | Vì sao sai | Hướng đúng |
| --- | --- | --- |
| ACK nghĩa là business effect đã commit | Có nhiều loại ACK | Xác định commit boundary |
| At-most-once không có vấn đề | Có thể mất event | Chấp nhận loss hoặc đổi semantics |
| At-least-once không có duplicate | Redelivery bình thường | Idempotent sink |
| Exactly-once là handler chạy một lần | Handler có thể replay | Chứng minh committed effect |
| Kafka EOS bảo đảm PostgreSQL | DB ngoài Kafka transaction | Inbox/unique guard |
| Outbox bảo đảm broker publish một lần | Relay có thể crash sau publish | Stable event ID |
| CDC không bao giờ lặp | Checkpoint/restart gây replay | Dedupe/reconcile |
| Event ID là business intent ID | Hai events có thể cùng một ý định | Stable business key |
| Inbox marker trước effect là đủ | Crash gây false completed | Atomic marker+effect |
| SELECT trước UPDATE là an toàn | Concurrent workers race | Conditional unique claim |
| Dedupe TTL tùy ý | Replay sau TTL gây lặp | Retention hợp lý |
| Version lớn nhất đủ cho mọi events | Delta cần xử lý gaps | Snapshot/delta policy |
| Dedupe đảm bảo ordering | Events hợp lệ vẫn đến đảo thứ tự | Version/partition discipline |
| Offset ACK chứng minh sink commit | Offset khác sink | Ack after commit + idempotency |
| Retry poison event vô hạn | Block liveness | DLQ/remediation |
| Một lần test pass là proof hoàn chỉnh | Chưa bao phủ mọi lịch lỗi | Crash matrix và reconciliation |
| Exactly-once email dễ chứng minh | Provider/recipient ngoài transaction | Mô tả notification intent scope |

## 39. Bài tập thực hành

### Bài 1 — Ba tầng

Broker gửi E ba lần, handler chạy ba lần, sink commit một lần. Đây là exactly-once delivery hay exactly-once effect?

**Gợi ý:** đếm committed effects.

### Bài 2 — At-most-once

Consumer ACK offset rồi crash trước xử lý. Nêu kết quả và đối tượng bị mất.

**Gợi ý:** không duplicate nhưng có thể thiếu effect.

### Bài 3 — At-least-once

Consumer cộng 100 điểm rồi crash trước ACK. Broker giao lại. Không có inbox thì số điểm thay đổi thế nào?

**Gợi ý:** 200.

### Bài 4 — Timeout

Tạo hai lịch cùng gây timeout nhưng một lịch chưa commit, lịch kia đã commit và ACK mất. Vì sao client không được tự tạo request ID mới khi retry?

**Gợi ý:** unknown outcome.

### Bài 5 — Outbox

Viết local transaction cập nhật booking và insert outbox event. Nêu trạng thái khi crash trước và sau COMMIT.

**Gợi ý:** cùng transaction source.

### Bài 6 — Relay duplicate

Relay publish xong nhưng chưa ghi published flag đã crash. Cần giữ event ID thế nào?

**Gợi ý:** không đổi ID ở retry.

### Bài 7 — CDC checkpoint

Nếu connector checkpoint trước publish rồi crash, điều gì có thể mất? Nếu checkpoint sau thì sao?

**Gợi ý:** loss vs duplicate.

### Bài 8 — Snapshot

Snapshot v10 tới sau CDC v11. Vì sao dedupe theo event ID không đủ?

**Gợi ý:** hai updates khác nhau, ordering.

### Bài 9 — Inbox atomicity

Marker được commit riêng trước effect. Crash ở giữa gây gì? Hãy đưa marker và mutation vào cùng transaction.

**Gợi ý:** tránh false completed.

### Bài 10 — Unique constraint

Hai workers cùng SELECT thấy chưa có marker E. Vì sao chỉ check-then-act không đủ?

**Gợi ý:** atomic conflict winner.

### Bài 11 — Payload mismatch

Cùng eventId nhưng payload khác nhau. Có nên im lặng bỏ qua?

**Gợi ý:** integrity violation.

### Bài 12 — Business identity

Hai PaymentCaptured events khác IDs nhưng cùng business intent. Inbox eventId có ngăn double charge không?

**Gợi ý:** idempotency tại payment authority.

### Bài 13 — Snapshot vs delta

Nếu v12 tới trước v11, xử lý `SetRemaining(1,v12)` khác `Decrement(1,v12)` ra sao?

**Gợi ý:** snapshots có thể bỏ cũ, deltas cần đủ sequence.

### Bài 14 — Kafka transaction

Processor consume topic A, produce topic B và commit offsets trong cùng Kafka transaction. Phạm vi exactly-once là gì?

**Gợi ý:** Kafka records và offsets.

### Bài 15 — External sink

Processor update PostgreSQL trước khi Kafka transaction commit rồi crash. Kết quả có thể là gì?

**Gợi ý:** DB effect lặp khi replay; inbox.

### Bài 16 — Framework checkpoint

Flink checkpoint state, nhưng custom sink gọi HTTP POST không idempotent. Có hứa exactly-once external effect được không?

**Gợi ý:** external API không tham gia sink commit protocol.

### Bài 17 — MongoDB resume

Lưu resume token trước sink COMMIT và sau sink COMMIT có hai loại rủi ro nào?

**Gợi ý:** loss và duplicate.

### Bài 18 — NoSQL transaction boundary

Một NoSQL store có conditional put marker nhưng effect cập nhật document khác ngoài transaction. Có bảo đảm atomic effect không?

**Gợi ý:** conditional ở một document chưa bao trùm document khác.

### Bài 19 — Inbox retention

Inbox TTL 7 ngày, broker replay 30 ngày. Tạo lịch duplicate effect ngày 20.

**Gợi ý:** marker đã hết hạn.

### Bài 20 — Poison event

Một event sai schema làm consumer retry vô hạn. Thiết kế DLQ và replay sau khi sửa lỗi mà không âm thầm bỏ business event.

**Gợi ý:** remediation và explicit exception.

### Bài 21 — Rebalance

Worker A xử lý E chậm, partition giao sang B, A quay lại commit muộn. Hệ cần bảo vệ gì ở sink?

**Gợi ý:** unique business effect.

### Bài 22 — Payment

Payment API đã capture nhưng response timeout. Vì sao Kafka transactions không chống được double capture?

**Gợi ý:** provider idempotency/status query.

### Bài 23 — Email

Nêu sự khác nhau giữa một notification intent trong DB và một email vật lý được recipient nhận.

**Gợi ý:** provider boundary.

### Bài 24 — Reconciliation

Source có 1.000 reservations, sink có 1.000 ACKs. Vì sao vẫn có thể thiếu một record và trùng một record khác?

**Gợi ý:** so sets, không chỉ count.

### Bài 25 — Java demo

Chạy `DeliverySemanticsDemo.java`, giải thích các kết quả 0, 200 và 100. Thay `InboxSink.applyOnce` bằng phép cộng không check marker thì sao?

**Gợi ý:** execution count khác effect count.

### Bài 26 — JDBC

Trong skeleton JDBC, nếu insert marker thành công nhưng update stats fail, transaction cần làm gì? Khi broker ACK mất sau DB commit thì sao?

**Gợi ý:** rollback hoặc duplicate no-op.

### Bài 27 — Metrics

Hãy chọn 8–10 metrics và IDs để điều tra một reservation được cộng điểm hai lần. Bao gồm sourceCommitId, eventId, businessIntentId, sink transaction và consumer offset.

**Gợi ý:** trace theo ranh giới.

### Bài 28 — Thiết kế cuối chương

Thiết kế pipeline `ReservationConfirmed` từ một NoSQL source qua outbox/CDC, Kafka, PostgreSQL loyalty ledger và một email provider. Yêu cầu:

1. Không mất event intent sau source COMMIT.
2. Broker giao at-least-once.
3. Loyalty effect không trùng theo business key.
4. Xử lý duplicate/out-of-order và replay.
5. Dedupe retention phù hợp.
6. Email được mô tả đúng scope.
7. Có crash fault matrix và business reconciliation.
8. Viết một tuyên bố exactly-once có điều kiện và ngoại lệ rõ ràng.

**Gợi ý:** vẽ từng commit boundary trước khi chọn framework.

## 40. Checklist thiết kế

1. “Một lần” đang đếm delivery, execution hay business effect?
2. Business intent ID khác event ID không?
3. Source state và outbox có commit cùng transaction không?
4. Relay có thể phát trùng cùng event ID không?
5. Broker ACK nói về durability mức nào?
6. Consumer offset commit trước hay sau sink effect?
7. Inbox marker và business mutation có atomic không?
8. Concurrent workers có thể vượt check-then-act không?
9. Duplicate event ID khác payload có bị phát hiện không?
10. Dedupe retention phù hợp replay horizon không?
11. Ordering theo aggregate và gap handling có đúng semantics không?
12. Snapshot+CDC có watermark/version guard không?
13. Kafka EOS chỉ được tuyên bố trong scope Kafka không?
14. External payment/email có idempotency/status contract riêng không?
15. Poison events có DLQ và remediation không?
16. Consumer rebalance có gây late duplicate effect không?
17. Khi source log retention hết có đường rebuild/reconciliation không?
18. Metrics bao gồm effect commits, lag, duplicate, checkpoint, drift không?
19. Đã fault test crash trước/sau COMMIT và ACK loss chưa?
20. Bản tuyên bố exactly-once có giả định/ngoại lệ rõ không?

**Nếu thiết kế chỉ có `enableExactlyOnce=true` nhưng chưa chỉ ra event identity, transaction boundary và xử lý crash giữa commit/ACK, lời hứa chưa có nội dung kỹ thuật kiểm chứng được.**

## 41. Tổng kết

1. **At-most-once** không giao/xử lý lặp trong phạm vi đã định nhưng có thể mất công việc khi checkpoint đi trước effect.
2. **At-least-once** retry theo điều kiện durability/retention/recovery, nhưng duplicate delivery và handler execution là tình huống bình thường.
3. **Exactly-once effect** nói về số lần commit của một hiệu ứng trong một phạm vi, không nhất thiết là exactly-once network delivery.
4. **ACK và checkpoint ở nhiều tầng khác nhau**. Timeout có thể xuất hiện sau commit, nên retry cần identity ổn định.
5. **Transactional outbox** gắn business state với event intent ở source; relay/CDC vẫn có thể phát trùng.
6. **Atomic inbox + business mutation** tại sink bảo vệ hiệu ứng trước redelivery; unique key, concurrent race, payload mismatch và retention đều quan trọng.
7. **Kafka transactions có phạm vi Kafka records/offsets**, không tự bao gồm PostgreSQL, MongoDB, Redis, payment hay email.
8. **Dedupe, ordering và completeness là các bài toán riêng**. Không trùng event ID vẫn có thể sai state vì đảo thứ tự hoặc thiếu event.
9. **Business idempotency và reconciliation** giúp giữ đúng ý định nghiệp vụ xuyên nhiều systems.
10. **Fault injection phải kiểm các điểm commit và ACK**, sau đó so trạng thái authoritative, không chỉ đếm ACKs.

**Nguyên tắc thực hành:** mỗi khi một pipeline CDC hoặc event bus được quảng bá “exactly-once”, hãy dựng sơ đồ **source COMMIT → event intent → publish → consumer checkpoint → sink COMMIT → external effects**. Thử hai lịch khó nhất: **crash trước sink COMMIT** và **crash sau sink COMMIT nhưng trước ACK**. Nếu cả hai lịch được xử lý đúng theo những giả định đã tuyên bố, bảo đảm xử lý mới có ý nghĩa thực tế.
