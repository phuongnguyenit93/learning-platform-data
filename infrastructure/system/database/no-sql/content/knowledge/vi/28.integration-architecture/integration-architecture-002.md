# Polyglot persistence và ranh giới trách nhiệm giữa các hệ lưu trữ

Một ứng dụng lớn có nhiều cách sử dụng dữ liệu: đặt chỗ cần transaction chính xác; tìm kiếm cần lọc theo văn bản, vị trí và giá; màn hình phổ biến cần đọc nhanh; analytics cần quét lịch sử dài; ảnh và tệp lớn cần lưu trữ với chi phí phù hợp. Một database có thể đáp ứng nhiều việc, nhưng **không có lý do để cho rằng một công nghệ luôn tối ưu mọi workload**.

**Polyglot persistence** là cách dùng **nhiều mô hình hoặc hệ quản trị lưu trữ** trong cùng một sản phẩm, chọn theo access pattern và yêu cầu nhất quán. Vấn đề quan trọng nhất là **ranh giới trách nhiệm**: nơi nào có thẩm quyền sửa trạng thái nghiệp vụ, nơi nào chỉ chứa dữ liệu dẫn xuất, dữ liệu đồng bộ qua đâu và ứng dụng ứng xử ra sao khi một hệ chậm hoặc lỗi.

Ví dụ kiến trúc nền tảng cho thuê:

~~~text
Transactional DB → Booking, inventory, payment state
Document DB      → Listing profile nếu schema và truy vấn phù hợp
Search engine    → Full-text search, facets, relevance
Redis            → Cache và dữ liệu tạm
Event bus        → Vận chuyển domain events
Object storage   → Ảnh, hợp đồng, tệp lớn
Warehouse        → Phân tích sự kiện và báo cáo
~~~

Đây chỉ là **một phương án**, không phải yêu cầu phải có đủ bảy hệ. Nếu một relational DB với JSON/index đáp ứng tốt nhu cầu, việc dùng thêm MongoDB, Redis hoặc search engine có thể tạo nhiều chi phí hơn giá trị.

Bài học thuộc chương **Tích hợp và kiến trúc**, module **Database No SQL**. Chúng ta sẽ đi từ ownership và invariant đến local transaction, outbox, CDC, event ordering, read model, cache, saga, migration, observability, security và ví dụ Java.

> **Nguyên tắc xuyên suốt:** cùng một giá trị xuất hiện ở nhiều storage engines **không có nghĩa tất cả chúng đều là nguồn sự thật**. Phải biết ai được quyền ghi, ai chỉ được đọc, dữ liệu có thể trễ bao lâu và cách khôi phục khi các bản sao không còn giống nhau.

## 1. Polyglot persistence giải quyết bài toán gì?

Những nhóm workload có yêu cầu rất khác:

| Nhu cầu | Đặc điểm | Hướng lưu trữ cần cân nhắc |
| --- | --- | --- |
| Đặt chỗ cuối cùng | Invariant, conditional write, transaction | Relational hoặc transactional NoSQL phù hợp |
| Listing profile | Aggregate dạng document, fields có thể thay đổi | Document DB hoặc RDBMS có JSON |
| Point lookup rất nhiều | Độ trễ thấp, dữ liệu nóng | Key–value/cache |
| Tìm kiếm | Full-text, scoring, facets, autocomplete | Search engine |
| Quan hệ nhiều bước | Traversal qua edges | Graph DB |
| Telemetry/event | Ghi nhiều, retention thời gian | Time-series/wide-column/log |
| Báo cáo | Scan/group-by nhiều dữ liệu | Analytical DB/warehouse |
| Tệp/ảnh | Blob và CDN | Object storage |

**Đừng chọn database từ tên mô hình trước rồi mới tìm use case cho nó.** Bắt đầu bằng query patterns, số lượng dữ liệu, QPS, latency SLO, giới hạn transaction, consistency và đội ngũ vận hành.

Một hệ nhỏ có thể giữ listing và booking trong một database quan hệ mà vẫn tổ chức code theo domain. Polyglot không đồng nghĩa microservices, và microservices cũng không bắt buộc một DBMS riêng cho từng service.

## 2. Phân biệt source of truth, projection, cache và backup

Giả sử dữ liệu `remainingUnits=2` xuất hiện tại bốn nơi:

~~~text
Booking DB: remainingUnits=2
Search:     availabilityHint=2
Redis:      cachedRemaining=2
Warehouse:  remainingAtSnapshot=2
~~~

Chúng có thể tạm thời khác nhau. Vai trò cần phân biệt:

| Bản thể | Có quyền quyết định booking? | Có thể stale? | Có thể xây lại? |
| --- | --- | --- | --- |
| Authoritative booking state | Có | Không cho đường commit | Không mặc định |
| Search projection | Không | Có theo SLO | Thường có |
| Redis cache | Không | Có giới hạn | Có |
| Analytics copy | Không | Thường có | Thường có |
| Backup | Không phục vụ OLTP trực tiếp | Ảnh trạng thái tại thời điểm | Dùng để restore |

**Source of truth là vai trò của một state/aggregate**, không phải tính chất cố định của một sản phẩm. Event-sourced systems có thể có event log làm nguồn sự thật; trong kiến trúc khác, Kafka chỉ là kênh tích hợp.

## 3. Ranh giới trách nhiệm theo domain và field

Không nên chỉ nói “PostgreSQL là nguồn sự thật của toàn hệ”. Một sản phẩm có nhiều owners:

| Dữ liệu | Service sở hữu | Authoritative store | Bản sao đọc |
| --- | --- | --- | --- |
| Tiêu đề, mô tả listing | Listing Service | Listing DB | Search, cache |
| Inventory/booking status | Booking Service | Booking DB | Search, notifications |
| Payment intent/status | Payment Service | Payment DB/provider contract | Billing view |
| Identity/consent | Identity Service | Identity DB | Claims/cache có kiểm soát |
| Search ranking | Search domain | Search model/index | Không nhất thiết có |
| Analytics facts | Analytics domain | Event/warehouse theo kiến trúc | Dashboard |

Mỗi **mutable business field** cần một write owner hoặc một multi-writer protocol được định nghĩa rõ. Không cho Search Service sửa inventory authoritative vì nó đang có một trường availability trong index.

### Phân chia theo nghiệp vụ

~~~text
Listing Service  → quản lý thông tin listing
Booking Service  → quyết định giữ/đặt chỗ
Payment Service  → quản lý thanh toán
Search Service   → tạo mô hình tìm kiếm
Analytics        → tổng hợp lịch sử
~~~

Service khác giao tiếp qua **API hoặc domain events**, không tự ý truy cập nội bộ database để sửa trạng thái.

## 4. Vì sao nhiều nguồn ghi cùng field nguy hiểm?

Giả sử Listing Service cập nhật title trong MongoDB, còn Search Service cho phép chỉnh title ngay trên OpenSearch:

~~~text
T0: MongoDB.title = "Apartment A"
T1: Search.title = "Apartment A"
T2: Listing Service writes "Apartment B"
T3: Search operator writes "Apartment C"
T4: Event from T2 reaches Search
~~~

Giá trị cuối cùng phụ thuộc arrival order và không có quy tắc nghiệp vụ rõ ràng. Nếu người dùng đọc ở hai hệ, họ có thể thấy hai titles khác nhau.

Thiết kế rõ hơn:

1. Title chỉ sửa qua Listing Service.
2. Source DB commit title cùng source version.
3. Event `ListingUpdated` được phát.
4. Search projector upsert bản dẫn xuất theo version.
5. Search không cung cấp public write API cho title authoritative.

Nếu bắt buộc multi-writer, cần conflict resolution có định nghĩa, không chỉ “write nào tới cuối thì thắng”.

## 5. Ví dụ kiến trúc đặt chỗ và tìm kiếm

~~~text
                          Web / Mobile
                              |
                           API layer
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
      Listing             Booking              Search
      Service             Service              Service
          |                   |                   |
      Listing DB          Booking DB         Search Index
          |                   |                   ^
          +----- events ------+---> Event Bus -----+
                              |        |
                              |        +--> Analytics
                              |
                              +--> Cache invalidator --> Redis

          Listing images --> Object storage / CDN
~~~

### Đường tìm kiếm

Search dùng index để trả listing IDs, ranking, filters và availability hint. Kết quả có thể trễ vì projection update bất đồng bộ.

### Đường đặt chỗ

Booking Service đọc trạng thái authoritative và thực hiện conditional transaction. Nó không tin một availability hint từ search hay cache để xác nhận cuối cùng.

### Sau commit

Booking phát event đáng tin để Search, cache, notifications và analytics bắt kịp. Các pipeline có thể chạy riêng và retry khi lỗi.

## 6. Invariant nghiệp vụ nên nằm ở đâu?

Ví dụ đơn giản:

\[
\forall listing:\ remainingUnits(listing)\ge0
\]

Nếu cho thuê một tài sản cụ thể theo thời gian, còn cần invariant **không có hai booking CONFIRMED chồng lấn khoảng ngày trong phạm vi được cấm**. Counter đơn giản không mô tả đủ.

Một đường commit:

~~~text
Client POST /reservations
          |
          v
Booking Service
  - Check request idempotency
  - Validate current authoritative state
  - Conditional write / transaction
  - Commit reservation
          |
          v
     Confirm or reject
~~~

**Đường tìm kiếm chỉ hỗ trợ khám phá**. Nếu search nói còn căn hộ nhưng Booking Service kiểm lại thấy hết, hệ nên từ chối đặt chỗ thay vì double-book.

## 7. Một hệ có thể chọn consistency khác nhau theo API

| API | Contract phù hợp để xem xét |
| --- | --- |
| Search listings | Eventual với freshness SLO |
| Listing detail | Cached, độ trễ cập nhật được nêu rõ |
| Confirm booking | Authoritative conditional transaction |
| Get booking vừa tạo | Read-your-writes hoặc authoritative read |
| Payment status | Idempotent state machine, xử lý unknown outcome |
| Analytics dashboard | Eventual aggregation |

Không bắt buộc mọi read đều strongly consistent. Nhưng cũng không được gọi projection eventual là authoritative chỉ vì nó trả response nhanh.

## 8. Dual-write trực tiếp không phải một transaction

Sai lầm thường gặp:

~~~text
1. INSERT reservation into PostgreSQL → COMMIT
2. UPDATE search index             → TIMEOUT
3. API fails, client retries
~~~

Booking có thể đã tạo nhưng search chưa đổi. Nếu client retry với request ID mới, có thể sinh thêm booking. Đổi thứ tự cũng tạo tình huống partial update:

~~~text
1. Search updated
2. Booking DB commit failed
~~~

**Hai local DB commits không trở thành atomic commit chỉ vì gọi nối tiếp trong Java.**

Giải pháp phụ thuộc vai trò:

- Nếu hai thay đổi đều cần invariant nguyên tử: cố gắng đặt chúng trong cùng authoritative transaction boundary hoặc dùng một distributed protocol phù hợp.
- Nếu search là derived view: commit source và event intent, rồi cập nhật search eventual.
- Nếu là workflow nhiều domains có side effects: cân nhắc saga/compensation và idempotency.

## 9. Transactional outbox

Mẫu outbox giúp phối hợp **một local transaction** với việc phát event về sau.

~~~text
Booking command
      |
      v
Local DB transaction:
  - Update inventory/reservation
  - Insert outbox event
      |
     COMMIT
      |
      v
Outbox relay / CDC
      |
      v
Event broker
   /     |       \
Search  Cache   Analytics
~~~

Source state và outbox row được commit cùng nhau. Nếu service crash sau commit, outbox còn để relay phát lại.

### Outbox không đảm bảo delivery đúng một lần

~~~text
T0: Relay reads event E.
T1: Broker accepts E.
T2: Relay crashes before marking E published.
T3: Relay restarts, publishes E again.
~~~

Consumer có thể nhận E hai lần. Outbox giúp **không quên event intent sau source commit**, nhưng downstream vẫn phải xử lý **at-least-once delivery**, duplicate, ordering và replay.

## 10. SQL minh họa transaction và outbox

Mẫu PostgreSQL dưới đây giả định inventory được mô hình hóa bằng số lượng. Nó **không thay thế thiết kế lịch đặt chỗ và ngày chồng lấn**.

~~~sql
CREATE TABLE listing_inventory (
    listing_id TEXT PRIMARY KEY,
    remaining INTEGER NOT NULL CHECK (remaining >= 0),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE reservation (
    reservation_id UUID PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    listing_id TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_id TEXT NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ
);
~~~

Một transaction logic:

~~~sql
BEGIN;

UPDATE listing_inventory
SET remaining = remaining - 1,
    version = version + 1
WHERE listing_id = 'L42'
  AND remaining > 0
RETURNING remaining, version;

-- Ứng dụng kiểm affected rows = 1.
-- Lấy remaining và version thực từ RETURNING.

INSERT INTO reservation (
    reservation_id, request_id, listing_id, status
) VALUES (
    '11111111-1111-4111-8111-111111111111',
    'request-801', 'L42', 'CONFIRMED'
);

INSERT INTO outbox_event (
    event_id, aggregate_id, aggregate_version,
    event_type, payload
) VALUES (
    '22222222-2222-4222-8222-222222222222',
    'L42', 7, 'InventoryChanged',
    '{"listingId":"L42","version":7,"remaining":0}'::jsonb
);

COMMIT;
~~~

### Điểm cần làm đúng trong code thật

1. `version=7` và `remaining=0` ở ví dụ chỉ để minh họa; phải dùng giá trị thực từ `UPDATE ... RETURNING`.
2. Không thành công ở `UPDATE` thì rollback, không tạo reservation.
3. `request_id` phải ổn định qua retry; duplicate unique violation cần rollback và tra outcome cũ, đồng thời kiểm payload trùng.
4. Booking theo ngày cần invariant về date ranges, không dùng counter nếu không đúng mô hình.
5. Client có thể timeout **sau COMMIT**; không suy từ timeout rằng transaction chưa xảy ra.

## 11. CDC và outbox kết hợp

**Change Data Capture (CDC)** theo dõi những thay đổi đã commit, thường qua transaction log hoặc stream do DBMS hỗ trợ:

~~~text
Business transaction
   |
   v
Outbox row committed
   |
   v
CDC connector reads log
   |
   v
Broker publishes domain event
~~~

Outbox định nghĩa **business event** cần phát; CDC là **một cơ chế vận chuyển** event đó.

### Raw CDC không tự thành domain event

Một thay đổi cột `reservation.status=PENDING→CONFIRMED` không nhất thiết đủ thông tin về nghiệp vụ, schema version, request correlation hoặc idempotency. Nếu consumer cần hợp đồng dài hạn, service nên công bố **domain event ổn định** thay vì cho mọi consumer phụ thuộc trực tiếp schema nội bộ.

## 12. Event bus khác event sourcing

**Integration events:**

~~~text
Booking DB is source of truth.
Broker carries ReservationConfirmed events downstream.
~~~

**Event sourcing:**

~~~text
Canonical event history is authoritative.
Current state is derived from ordered events.
~~~

Event sourcing yêu cầu append/version semantics, đủ history, replay, snapshots, evolution và invariants phù hợp. Dùng Kafka hoặc CDC để truyền sự kiện **không tự biến một hệ thành event sourced**.

## 13. Event contract cần định nghĩa rõ

~~~json
{
  "eventId": "evt-801",
  "eventType": "ListingAvailabilityChanged",
  "schemaVersion": 2,
  "aggregateId": "L42",
  "aggregateVersion": 7,
  "occurredAt": "2026-11-14T09:30:00Z",
  "source": "booking-service",
  "correlationId": "request-801",
  "data": {
    "listingId": "L42",
    "remaining": 0
  }
}
~~~

| Field | Mục đích |
| --- | --- |
| `eventId` | Dedupe/replay |
| `eventType` | Ngữ nghĩa nghiệp vụ |
| `schemaVersion` | Thay đổi payload có quản lý |
| `aggregateId` | Định danh entity, giúp routing/partitioning |
| `aggregateVersion` | Kiểm trùng hoặc thứ tự event |
| `occurredAt` | Audit; không tự là total order |
| `correlationId` | Truy vết workflow |
| `data` | Payload tối thiểu theo hợp đồng |

Không đẩy dữ liệu cá nhân không cần thiết vào events. Broker retention, consumer access và privacy deletion có thể khác source DB.

## 14. Ordering và duplicate events

Một read model nhận:

~~~text
Source version 5: remaining=2
Source version 6: remaining=1
Source version 7: remaining=0

Consumer receive order:
  v7, v5, v6, v7(duplicate)
~~~

Nếu apply theo thời điểm nhận, projection có thể đi lùi từ 0 về 1.

### Snapshot event

`SetRemaining(0,version=7)` chứa trạng thái đủ. Consumer có thể cho phép upsert nếu version mới hơn và bỏ những state snapshots cũ.

### Delta event

`DecrementRemainingBy(1,version=7)` là thay đổi tương đối. Consumer có thể cần các versions liên tiếp hoặc dedupe theo eventId và state transaction, nếu thiếu một delta thì kết quả sai.

**Snapshot và delta đòi hai chiến lược ordering khác nhau.** Không có một quy tắc “chỉ lấy version lớn nhất” đúng cho tất cả.

## 15. Consumer idempotency

Lịch dễ xảy ra:

~~~text
Consumer receives E.
Consumer commits search projection.
Consumer crashes before broker ACK.
Broker redelivers E.
~~~

Nếu E là một delta và consumer cộng/trừ lại, dữ liệu có thể bị áp hai lần.

Hướng xử lý:

- Conditional upsert theo aggregateVersion cho state snapshots.
- Với delta, ghi dedupe marker `eventId` và state mutation **trong cùng atomic boundary** khi storage cho phép.
- Broker ACK sau khi effect phù hợp đã được commit, chấp nhận redelivery.
- Event có thể tới muộn/đảo thứ tự, cần version checks.
- Với external API, cần provider idempotency hoặc workflow state riêng.

**Exactly-once semantics chỉ có ý nghĩa trong phạm vi được chứng minh**, không tự lan ra payment gateway hoặc search service khác.

## 16. Java: mô phỏng replay và version gap

Ví dụ chạy trong một JVM, dùng Map để mô phỏng source và search read model. Đây **không phải** triển khai durable production.

Tạo file `PolyglotProjectionDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public final class PolyglotProjectionDemo {
    static final class Event {
        final String id;
        final String listingId;
        final long version;
        final int remaining;

        Event(String id, String listingId,
              long version, int remaining) {
            this.id = id;
            this.listingId = listingId;
            this.version = version;
            this.remaining = remaining;
        }
    }

    static final class Source {
        int remaining = 3;
        long version = 0;

        synchronized Event reserve(String listingId) {
            if (remaining <= 0) {
                throw new IllegalStateException("Sold out");
            }
            remaining--;
            version++;
            return new Event(
                    "evt-" + version, listingId,
                    version, remaining);
        }
    }

    static final class SearchProjection {
        final Map<String, Long> versions = new HashMap<>();
        final Map<String, Integer> values = new HashMap<>();

        synchronized void apply(Event event) {
            long current = versions.getOrDefault(
                    event.listingId, 0L);
            if (event.version <= current) {
                System.out.println("Ignore duplicate/stale "
                        + event.id);
                return;
            }
            if (event.version != current + 1) {
                throw new IllegalStateException(
                        "Gap: expected " + (current + 1)
                        + ", received " + event.version);
            }
            values.put(event.listingId, event.remaining);
            versions.put(event.listingId, event.version);
        }

        synchronized String get(String listingId) {
            Integer value = values.get(listingId);
            return value == null
                    ? "NOT_INDEXED"
                    : "remaining=" + value;
        }
    }

    public static void main(String[] args) {
        Source source = new Source();
        SearchProjection search = new SearchProjection();

        Event e1 = source.reserve("L42");
        Event e2 = source.reserve("L42");

        System.out.println("Source=" + source.remaining);
        System.out.println("Search before="
                + search.get("L42"));

        try {
            search.apply(e2);
        } catch (IllegalStateException expected) {
            System.out.println(expected.getMessage());
        }
        search.apply(e1);
        search.apply(e2);
        search.apply(e1);

        System.out.println("Search after="
                + search.get("L42"));
    }
}
~~~

Chạy:

~~~bash
javac PolyglotProjectionDemo.java
java PolyglotProjectionDemo
~~~

Kết quả dự kiến:

~~~text
Source=1
Search before=NOT_INDEXED
Gap: expected 1, received 2
Ignore duplicate/stale evt-1
Search after=remaining=1
~~~

### Giới hạn mô phỏng

- State ở RAM, không có broker, source DB hay outbox thật.
- `synchronized` chỉ bảo vệ cùng một JVM, không phải distributed consensus.
- Code chọn xử lý tuần tự từng version để minh họa gap detection; một projector của snapshot events đầy đủ có thể chọn chỉ apply version cao nhất.
- Không mô phỏng consumer checkpoint, crash, index refresh hoặc schema evolution.

Thông điệp: **source có thể đã commit trong khi search chưa cập nhật**, và consumer cần chính sách rõ cho duplicate/out-of-order.

## 17. Search index là projection, không phải booking authority

Một search document có thể:

~~~json
{
  "listingId": "L42",
  "city": "Da Nang",
  "title": "Căn hộ gần biển",
  "priceMinor": 1750000,
  "amenities": ["wifi", "kitchen"],
  "availabilityHint": 1,
  "listingVersion": 11,
  "inventoryVersion": 7
}
~~~

Title từ Listing Service; availability từ Booking Service. Hai fields có **versions riêng theo owner**.

~~~text
ListingUpdated(v11) --------\
                             → Search document
InventoryChanged(v7) -------/
~~~

Không áp một global version chung khiến event inventory mới vô tình ghi đè title, hoặc ngược lại.

Search rất phù hợp khám phá lựa chọn, nhưng khi user click **Đặt chỗ**, Booking Service phải đọc/ghi authoritative store và xác nhận kết quả.

## 18. Redis cache-aside và race invalidation

~~~text
READ:
  Redis GET key
  HIT  → return cached data if freshness acceptable
  MISS → read source → SET cache with TTL

WRITE:
  Commit source
  Invalidate cache using agreed policy
~~~

Một race:

~~~text
T0: Reader cache miss, reads source version 6.
T1: Writer commits source version 7.
T2: Writer deletes Redis key.
T3: Reader SET cache version 6.
~~~

Cache cũ xuất hiện lại **sau invalidation**.

Biện pháp:

- SourceVersion trong cached payload; conditional fill/compare.
- Invalidation event mang version/watermark.
- TTL và giới hạn thời gian stale.
- Không dùng cache cho authoritative booking decision.
- Coalescing requests/backpressure khi cache miss hàng loạt.

**Chỉ xóa cache sau write không tự chứng minh cache luôn mới** vì concurrent reader có thể ghi lại bản cũ.

## 19. CQRS không bắt buộc nhiều databases

**CQRS** tách command side và query side:

~~~text
Command: reserve booking → authoritative state transition.
Query:   search listing  → read-optimized projection.
~~~

Nó có thể đi cùng polyglot persistence, nhưng:

- CQRS có thể dùng **cùng một database**.
- Polyglot persistence có thể chỉ là một DB với Redis cache, chưa có CQRS đầy đủ.
- Query projection chọn fields không tự tạo một database dẫn xuất.
- Materialized views có thể được cập nhật đồng bộ hoặc bất đồng bộ tùy DBMS.

Không thêm CQRS chỉ để tăng số lớp kiến trúc khi query/write workloads chưa có nhu cầu tách.

## 20. Saga cho workflow nhiều owner

Booking và Payment là hai domains:

~~~text
PENDING
   |
   v
INVENTORY_HELD
   |
   +--- Payment authorized ---> CONFIRMED
   |
   +--- Payment failed -------> RELEASING_HOLD
                                    |
                                    v
                                 CANCELLED
~~~

**Saga** tổ chức nhiều local transactions và những thao tác bù trừ (*compensation*).

### Những yêu cầu

1. Workflow state được lưu bền qua crash.
2. Mỗi bước có idempotency key/correlation ID.
3. Status transition có expected version/CAS.
4. Hold expiry và release được quản lý.
5. Payment timeout có thể là unknown outcome, cần tra cứu trước khi retry.
6. Compensation không được tự tạo tác động trùng.

**Compensation không phải rollback nguyên tử theo nghĩa SQL.** Nếu đã capture tiền, có thể phải refund; nếu đã gửi email, không thể xóa ký ức người nhận.

## 21. 2PC và lựa chọn thay thế

**Two-phase commit (2PC)** có thể phối hợp commit nếu các participants hỗ trợ protocol/điều kiện phù hợp, nhưng không phải mọi DBMS hoặc payment API đều tham gia.

Chi phí có thể gồm coordinator, recovery state, blocking/latency và áp lực tài nguyên trong phase prepare.

Vì vậy các workflow polyglot thường cân nhắc:

- Đặt invariant cần nguyên tử trong một authoritative DB.
- Outbox để phát event bất đồng bộ sau local commit.
- Saga và idempotency cho cross-service business steps.
- Reconciliation cho các bản dẫn xuất.

Không kết luận 2PC luôn sai hoặc saga luôn đủ. Mục tiêu là **đúng invariant trong phạm vi hệ thống thật hỗ trợ**.

## 22. Đồng bộ và bất đồng bộ nên nằm ở đâu?

Một đường booking:

~~~text
Client → Booking Service → Booking DB → Confirm/Reject
~~~

Đây là bước phải **đồng bộ** để quyết định thành công.

Sau commit:

~~~text
Outbox event
   ├── Search projection
   ├── Cache invalidation
   ├── Notification workflow
   └── Analytics
~~~

Những bước này có thể **bất đồng bộ** nếu product chấp nhận dữ liệu cập nhật trễ và có retry/replay.

Không để search down làm transaction booking fail nếu search chỉ là read model; ngược lại, không xác nhận booking trước khi authority xử lý vì tin rằng event “rồi sẽ tới”.

## 23. Freshness SLO phải đo end-to-end

~~~text
t0 = 10:00:00.000 Booking DB COMMIT
t1 = 10:00:00.100 Event published
t2 = 10:00:01.400 Search projector applied
t3 = 10:00:01.700 Search query sees new version
~~~

Vậy:

- Publish lag: 100 ms.
- Apply lag từ commit: 1,4 giây.
- **Visible lag từ commit: 1,7 giây.**

Nếu cam kết UI “search thấy thay đổi dưới 2 giây”, cần đo tới `t3`, không chỉ tới broker ACK.

Các metrics:

| Metric | Mục đích |
| --- | --- |
| Oldest pending outbox age | Phát hiện relay kẹt |
| Consumer lag | Backlog xử lý events |
| Applied aggregate version | Biết read model tới version nào |
| Search-visible version | Đo cập nhật thực thấy |
| DLQ age/count | Poison events |
| Reconciliation mismatch | Silent drift giữa stores |

## 24. Read-your-writes khi nguồn và query store khác nhau

User sửa title:

~~~text
T0: Listing DB commits title v12.
T1: API returns OK.
T2: Search still has title v11.
~~~

Giải pháp tùy contract:

- Sau edit đọc từ authoritative source.
- Optimistic UI với trạng thái đồng bộ minh bạch.
- Chờ search projection đạt `version >= 12` rồi mới báo đã cập nhật ở search.
- Session token/version watermark nếu hệ hỗ trợ.

Đừng gọi search index eventual là linearizable chỉ vì source database vừa commit.

## 25. Degraded mode khi một storage engine lỗi

| Sự cố | Hành vi có thể phù hợp |
| --- | --- |
| Search down | Booking vẫn commit nếu source khỏe; search tạm không có |
| Redis down | Fallback source có giới hạn, tránh cache stampede |
| Broker down | Outbox tích tụ có giám sát/capacity, source commit theo policy |
| Search consumer lag | Hiển thị availability unverified hoặc giới hạn feature |
| Booking DB down | Không tự confirm từ search/cache |
| Payment provider timeout | Trả pending/unknown, tra status/idempotency |

**Graceful degradation không có nghĩa dữ liệu sai vẫn được xác nhận.** Từng endpoint phải phân biệt nơi cho phép stale với nơi bắt buộc authority.

## 26. Rebuild search từ source và CDC

Nếu index bị mất hoặc mapping đổi:

~~~text
Source snapshot at watermark W
               |
               v
Backfill new search index
               |
               +--- Apply CDC/events after W
               |
               v
Verify version, counts, queries
               |
               v
Switch search alias
~~~

Một race:

~~~text
T0: Snapshot includes L42 version 10.
T1: Source commits L42 version 11.
T2: Event v11 updates target.
T3: Snapshot row v10 arrives late.
~~~

Nếu blind-upsert v10, search đi lùi. Cần watermark/version guard, đồng thời không cutover khi index chưa đủ nội dung hoặc lag chưa đạt tiêu chí.

### Rebuildable không nghĩa miễn phí

Cần tính thời gian index hàng triệu documents, network/disk cost, ảnh hưởng lên source DB và khả năng replay deletes/tombstones đúng.

## 27. Reconciliation khi dữ liệu drift

Events có thể bị bỏ lỡ vì relay/consumer bug, broker retention, DLQ, schema mismatch hoặc thao tác chỉnh source thủ công.

~~~text
Source L42: remaining=0, version=7
Search L42: remaining=1, version=6
                 |
                 v
Mismatch → targeted repair/replay
~~~

Các phương pháp:

- Sample compare records.
- So per-aggregate version/watermark.
- Checksums theo partition/range.
- Scheduled full reconciliation khi khả thi.
- Repair/reindex đối tượng bị lệch.

**Đừng chỉ tin consumer lag bằng 0** là index hoàn toàn đúng; có thể event không hề được phát hoặc consumer đã silently ignore.

## 28. Schema evolution xuyên nhiều hệ

Ví dụ đổi representation tiền:

~~~text
Old: price = 17.5 as floating point.
New: priceMinor = 1750, currency = "USD".
~~~

Ảnh hưởng tới:

- Source schema.
- API DTOs.
- Event schema/version.
- Search mappings.
- Redis serialization.
- Analytics tables.
- Backfill/rebuild code.

Chiến lược **expand–migrate–contract**:

1. Expand: readers hiểu old và new.
2. Migrate: writers phát new, backfill historical data, chuyển consumers.
3. Contract: chỉ bỏ old khi compatibility/retention cho phép.

Schema registry và contract tests hữu ích, nhưng **deserialize thành công không chứng minh giá trị tiền/đơn vị vẫn đúng nghiệp vụ**.

## 29. Data lineage và quyền sở hữu của pipeline

Vẽ tuyến dữ liệu:

~~~text
Booking DB
   |
   +--> Outbox/CDC → Event bus
                        |
                        +--> Search
                        +--> Cache invalidator
                        +--> Analytics
                        +--> Notifications
~~~

Mỗi cạnh cần:

- Producer và consumer owner.
- Schema/event version.
- Dedupe/ordering policy.
- Retention và replay.
- Freshness SLO.
- ACL/PII.
- Monitoring, runbook và on-call contact.

Không có lineage sẽ khó trả lời một field còn tồn tại ở đâu sau khi user yêu cầu xóa.

## 30. Security, tenant isolation và least privilege

Nhiều stores có nghĩa nhiều credentials, API keys, network rules, backups và logs.

Một policy hợp lý:

- Booking Service có quyền authoritative write.
- Search projector chỉ sửa search index của mình.
- Analytics không có quyền update booking DB.
- Event consumers chỉ subscribe topics được cấp.
- Cache keys phân tách tenant/permission context phù hợp.
- Search filtering không tin hoàn toàn `tenantId` do client tự gửi.

**Một search index rất nhanh nhưng trả document của tenant khác là lỗi nghiêm trọng**, không phải trade-off hiệu năng chấp nhận được.

## 31. Retention và xóa PII

Một yêu cầu privacy deletion có thể tác động:

~~~text
Source DB
Search index
Redis cache
Event logs / CDC streams
Warehouse
Object storage
Backups / snapshots
~~~

Cần xác định bản nào có PII, retention ở đâu, cách truyền event xóa/tombstone, cách đảm bảo rebuild từ snapshot cũ không hồi sinh dữ liệu đã xóa, chính sách backup và data residency phù hợp quy định áp dụng.

Không hứa xóa tức thì khỏi mọi hệ nếu event/backup retention chưa được thiết kế và xác minh.

## 32. Backup và DR theo vai trò

| Storage | Hướng phục hồi |
| --- | --- |
| Source of truth | Backup/PITR/DR có RPO/RTO chặt |
| Search projection | Rebuild từ source + CDC nếu giữ đủ lịch sử |
| Redis cache | Warm-up lại nếu chỉ là cache |
| Analytics | Snapshot/backfill/replay theo SLA |
| Object storage | Versioning/backup/replication theo policy |

Không coi “search có thể rebuild” là bằng chứng RTO ngắn. Hãy diễn tập tốc độ backfill, giữ phiên bản đã xóa, cutover và tải tăng lên source.

## 33. Chi phí vận hành phải tính

Thêm mỗi hệ sẽ tăng:

- Hạ tầng và storage duplication.
- Client libraries, connection pools.
- Secrets/IAM, backups.
- Patch/upgrade/schema migration.
- Events, CDC, replay và reconciliation.
- Network egress.
- Monitoring và on-call expertise.
- Bề mặt compliance/security.

Một database với index tối ưu thường tốt hơn năm hệ nếu đáp ứng toàn bộ SLO. Chỉ thêm công nghệ khi có **năng lực thiếu hụt hoặc lợi ích đo được**.

## 34. Quy trình ra quyết định

1. Liệt kê **access patterns** theo endpoint.
2. Ghi **business invariants** và yêu cầu consistency.
3. Xác định **owner của từng aggregate/field**.
4. Ghi freshness SLO cho read models.
5. Đo baseline p95/p99, QPS, data size và cost.
6. Đánh giá khả năng DB hiện tại: index, query tuning, partitioning.
7. Chọn thêm engine nếu lợi ích phù hợp.
8. Thiết kế outbox/CDC, event IDs, versions, retries trước khi launch.
9. Thiết kế rebuild, reconciliation, DLQ và degraded mode.
10. Kiểm thử fault, privacy deletion, backup và on-call runbook.

## 35. Fault matrix cho polyglot architecture

| Lỗi | Cần quan sát |
| --- | --- |
| Cache down | Fallback không làm nguồn quá tải |
| Search down | Không ảnh hưởng booking correctness |
| Broker down | Outbox durable và backlog có giới hạn |
| Relay crash sau publish | Consumer xử lý duplicate |
| Out-of-order events | Không làm projection đi lùi |
| CDC checkpoint mất | Replay không phá dữ liệu |
| Search lag quá SLO | UI degrade đúng contract |
| Booking source down | Không confirm từ stale cache |
| Payment timeout sau capture | Idempotency/unknown outcome |
| Search index mất | Rebuild/cutover có xác minh |
| Event schema mismatch | DLQ và compatibility recovery |
| Tenant nóng | Isolation/rate limiting |

Một lần test chỉ xem HTTP 200 không đủ; cần đối chiếu business state, version và recovery.

## 36. Anti-patterns

| Cách làm sai | Vấn đề | Cách sửa |
| --- | --- | --- |
| Hai databases cùng sửa field | Conflict | Một authority hoặc protocol rõ |
| Search quyết định booking | Double-book | Commit ở source |
| Dual-write không atomic | Partial updates | Outbox/CDC, workflow phù hợp |
| Tin broker luôn đúng một lần | Duplicate effects | Idempotent consumer |
| Chỉ có raw CDC schema | Coupling chặt | Domain event contract |
| Apply theo arrival time | Projection đi lùi | Version/ordering |
| Không event ID | Không dedupe được | Stable identity |
| Cache invalidation không xét race | Stale cache tái sinh | Conditional/version-aware fill |
| Rebuild không theo watermark | Bỏ writes mới | Snapshot+catch-up |
| ACK broker trước commit view | Mất cập nhật | Safe ACK/replay |
| Saga là try/catch | Crash mất workflow | Durable state/compensation |
| Không reconcile | Silent drift | Scheduled compare/repair |
| Không data lineage | Privacy deletion thiếu | Audit copies/retention |
| Không ownership on-call | Incident kéo dài | Runbook và trách nhiệm |

## 37. Runbook khi Search projector bị chậm

1. Xác định số listing/tenant ảnh hưởng và độ trễ.
2. Kiểm source DB có commit/outbox tiếp không.
3. Kiểm relay pending age/publish failures.
4. Kiểm broker consumer lag, retention và DLQ.
5. Kiểm search indexing throughput, disk và refresh visibility.
6. Bật degraded mode, không quảng bá availability chưa kiểm chứng.
7. Replay với event ID/version guard, giới hạn tải.
8. Reconcile với source.
9. Đo lag và query latency trở lại SLO.
10. Ghi postmortem và cập nhật alert.

Không vá thủ công search documents rồi kết luận đã sửa nếu producer/consumer vẫn làm sai dữ liệu.

## 38. Migration từng bước từ monolith

Giả sử ban đầu một PostgreSQL chứa listings/bookings và phục vụ search SQL.

1. Profile search queries và thử index/query tuning.
2. Định nghĩa search document và event contract.
3. Tạo outbox/CDC, backfill search index.
4. Catch up changes từ snapshot watermark.
5. Shadow reads so latency/coverage; khác biệt relevance có thể có chủ đích.
6. Canary search traffic bằng feature flag.
7. Giữ booking commit ở authoritative DB.
8. Chuẩn bị rollback route, rebuild và privacy deletion.

**Tách read path không đồng nghĩa chuyển write authority.** Rollout theo giai đoạn giảm phạm vi rủi ro.

## 39. Template Architecture Decision Record

~~~yaml
decision: "Add search projection for listing discovery"
businessGoals:
  - "Full-text search, facets and ranking"
  - "No double-confirmed booking"
authoritativeOwners:
  listing:
    service: "Listing Service"
    store: "Document or relational DB"
  booking:
    service: "Booking Service"
    store: "Transactional DB"
derivedStores:
  search:
    role: "Eventually consistent read model"
    sourceEvents:
      - "ListingUpdated"
      - "InventoryChanged"
    freshnessSlo: "Explicit and measurable"
    rebuild: "Snapshot plus CDC/events"
  cache:
    role: "Replaceable"
    policy: "TTL and version-aware invalidation"
eventDelivery:
  pattern: "Transactional outbox with relay/CDC"
  semantics: "At least once; dedupe required"
  ordering: "Per aggregate/source version"
invariants:
  - "Booking authority decides confirmation"
  - "Retry cannot duplicate booking effect"
failureBehavior:
  searchDown: "Degrade discovery"
  sourceDown: "Do not confirm from stale view"
security:
  - "Least privilege"
  - "Tenant isolation"
  - "PII retention and deletion"
operations:
  - "Lag monitoring"
  - "DLQ and reconciliation"
  - "Rebuild and restore drills"
tradeoffs:
  benefit: "Rich search and isolated query workload"
  cost: "Eventual freshness and pipeline complexity"
~~~

Đây là **mẫu tài liệu kiến trúc**, không phải config deploy. Phải thay những trường chung bằng lựa chọn/tiêu chí cụ thể của hệ.

## 40. Bài tập thực hành

### Bài 1 — Source of truth

Hệ có PostgreSQL booking, OpenSearch listing search và Redis cache. Ai được quyền commit thay đổi inventory? Search/cache giữ representation gì?

**Gợi ý:** Booking authority, các bản khác là read copies.

### Bài 2 — Hai writers

Listing Service và Search Service cùng sửa title trên hai DB. Hãy viết một lịch gây conflict và thiết kế lại ownership.

**Gợi ý:** authoritative writer và domain event.

### Bài 3 — Dual-write

Booking commit thành công, search update timeout, client retry với booking ID mới. Lỗi nào có thể xảy ra và cách sửa?

**Gợi ý:** unknown outcome, idempotency, outbox.

### Bài 4 — Outbox

Mô tả local transaction ghi reservation và outbox event. Crash trước và sau COMMIT khác nhau thế nào?

**Gợi ý:** cùng commit hoặc rollback.

### Bài 5 — Relay duplicate

Relay phát event rồi crash trước update trạng thái. Consumer nhận event hai lần. Làm sao tránh áp delta hai lần?

**Gợi ý:** eventId dedupe trong atomic boundary.

### Bài 6 — Snapshot và delta

So `SetRemaining(0,v7)` với `Decrement(1,v7)` khi event v7 tới trước v6. Tại sao có thể cần ordering khác nhau?

**Gợi ý:** state snapshot đủ nội dung, delta phải đủ trình tự.

### Bài 7 — Multi-owner search

Title từ Listing Service v11, availability từ Booking Service v7. Thiết kế các version guards để tránh overwriting chéo.

**Gợi ý:** per-source versions.

### Bài 8 — Cache race

Reader đọc source v6, writer commit v7 và invalidate, reader cũ fill cache v6 sau đó. Nêu hai cách giảm rủi ro.

**Gợi ý:** version-aware cache fill, TTL, authoritative path.

### Bài 9 — Search stale

Search báo còn chỗ, Booking DB báo hết. UI và Booking API nên làm gì?

**Gợi ý:** gợi ý tìm kiếm không phải cam kết giao dịch.

### Bài 10 — Read-your-writes

Người dùng sửa title rồi thấy title cũ trên search. Đề xuất hai cách đáp ứng kỳ vọng mà không biến search thành transaction authority.

**Gợi ý:** đọc source hoặc chờ version watermark.

### Bài 11 — CDC

Vì sao một row change từ CDC chưa chắc là domain event có contract ổn định?

**Gợi ý:** schema nội bộ khác business meaning.

### Bài 12 — Event sourcing

Phân biệt integration events với canonical event log. Muốn replay toàn state thì cần gì thêm?

**Gợi ý:** complete history, ordering, retention, schemas.

### Bài 13 — Reconciliation

Source L42 version 10, Search version 8. Thiết kế detection và repair có version guard.

**Gợi ý:** compare watermark, replay/reindex.

### Bài 14 — Saga

Inventory hold thành công, payment authorization thất bại. Thiết kế các state và compensation.

**Gợi ý:** durable state và idempotent release.

### Bài 15 — Unknown payment outcome

Provider đã capture nhưng client timeout. Tại sao retry với payment intent mới nguy hiểm?

**Gợi ý:** idempotency key, tra status.

### Bài 16 — Privacy deletion

Người dùng yêu cầu xóa PII. Hãy liệt kê tất cả stores/streams/backups có thể còn dữ liệu và thiết kế propagation.

**Gợi ý:** source, cache, search, warehouse, events, object storage, snapshots.

### Bài 17 — Java demo

Chạy `PolyglotProjectionDemo`. Vì sao v2 trước v1 báo gap và v1 được giao lại không làm projection đi lùi?

**Gợi ý:** strict aggregateVersion ordering.

### Bài 18 — Rebuild

Snapshot v10 tới sau CDC event v11. Làm sao ngăn snapshot ghi đè state mới?

**Gợi ý:** version guard và watermark.

### Bài 19 — Freshness

Commit lúc 10:00:00, event publish lúc 10:00:01, consumer apply lúc 10:00:04, search visible lúc 10:00:07. Độ trễ thực mà user nhìn thấy là bao nhiêu?

**Gợi ý:** 7 giây.

### Bài 20 — Có cần polyglot?

Một MVP có 20.000 listings và search đơn giản. Team muốn dùng PostgreSQL, MongoDB, Redis, Kafka, Cassandra và OpenSearch ngay. Hãy đánh giá lợi ích và tổng chi phí.

**Gợi ý:** benchmark và ưu tiên đơn giản.

### Bài 21 — Failure matrix

Đề xuất hành vi khi Redis, broker, search hoặc Booking DB lần lượt down. Khi nào bắt buộc fail-closed?

**Gợi ý:** không confirm booking từ projection stale.

### Bài 22 — Least privilege

Search Service có credential update Booking DB để đồng bộ nhanh. Rủi ro nào xuất hiện và quyền nên thay thế ra sao?

**Gợi ý:** owner API/events, least privilege.

### Bài 23 — Schema migration

Đổi `price: double` sang `priceMinor: long` và `currency`. Viết kế hoạch expand–migrate–contract qua source, events, search, Redis, analytics.

**Gợi ý:** compatibility, backfill và versioned events.

### Bài 24 — Thiết kế hệ cho thuê

Cho yêu cầu: tìm kiếm theo text/giá, không double-book, retry payment an toàn, search freshness theo SLO, có thể rebuild index và xóa PII đúng quy định. Hãy lập sơ đồ storage ownership, outbox/CDC, API consistency, saga, monitoring và recovery.

**Gợi ý:** bắt đầu từ invariant và authority, không bắt đầu từ tên database.

## 41. Checklist áp dụng polyglot persistence

1. Workload nào cần storage engine mới?
2. DB hiện có đáp ứng bằng index/query tuning không?
3. Field nào được nhân bản?
4. Ai là authoritative writer?
5. Read models được stale bao lâu?
6. Invariant nào phải kiểm ở commit boundary?
7. Business state và event intent có được commit nguyên tử không?
8. Event có duplicate/out-of-order không?
9. Consumer có eventId/version guard không?
10. Cache invalidation có race không?
11. Search document nhiều nguồn có version theo owner không?
12. Client retries có idempotency key ổn định không?
13. Có contract tests cho event schema evolution không?
14. Có DLQ và replay không?
15. Có snapshot watermark khi rebuild không?
16. Có reconciliation phát hiện silent drift không?
17. Freshness được đo tới khi query thấy mới chưa?
18. Read-your-writes được đáp ứng thế nào?
19. Saga state/compensation có bền và idempotent không?
20. Khi source, search, cache hoặc broker down, chức năng nào degrade?
21. Tenant isolation và ACL đúng với ownership không?
22. PII retention, data residency, deletion và backup được bao phủ chưa?
23. RTO rebuild đã được diễn tập chưa?
24. Có owner on-call/runbook cho mỗi pipeline không?
25. Lợi ích có vượt chi phí vận hành không?

**Nếu chưa chỉ ra được ai có quyền sửa field và phải làm gì khi một event bị trễ/mất, kiến trúc polyglot chưa có ranh giới trách nhiệm đủ rõ.**

## 42. Tổng kết

1. **Polyglot persistence** sử dụng nhiều hệ lưu trữ theo access pattern, nhưng không bắt buộc nhiều database nếu một hệ đủ đáp ứng.
2. **Source of truth phải được định nghĩa theo domain/aggregate/field**, không theo nhãn công nghệ.
3. **Search, cache và analytics thường giữ bản dẫn xuất**, có thể stale theo SLO; chúng không nên tự xác nhận booking hoặc payment.
4. **Dual-write trực tiếp không nguyên tử.** Outbox trong cùng local transaction và relay/CDC giúp phát event đáng tin hơn.
5. **Event delivery có thể lặp và đảo thứ tự.** Event IDs, versions, idempotent consumers và semantics snapshot/delta là cần thiết.
6. **CQRS và polyglot liên quan nhưng không tương đương.** CQRS tách command/query; polyglot chọn storage theo nhu cầu.
7. **Saga điều phối workflows qua nhiều owners**, cần durable state, compensation và idempotency; không tự tạo rollback nguyên tử xuyên mọi API.
8. **Cache invalidation và rebuild search có race**. Version guards, CDC watermark và reconciliation giúp tránh dữ liệu đi lùi.
9. **Data lineage, privacy, security, backup và on-call** phải bao phủ mọi bản sao.
10. **Thêm storage engine là thêm hợp đồng tích hợp và chi phí vận hành**, nên luôn đo lợi ích trước.

**Nguyên tắc thực hành:** trước khi đưa thêm MongoDB, Redis, Cassandra hay search engine vào kiến trúc, hãy vẽ bảng **“dữ liệu nào → owner nào → store nào có thẩm quyền → bản nào là projection → đồng bộ bằng gì → khi lỗi thì phục hồi ra sao”**. Chỉ khi các ranh giới được thiết kế và kiểm thử rõ ràng thì polyglot persistence mới tạo ra lợi ích bền vững.
