# Outbox và relay process trong Spring Framework Application Events

## 1. Bài toán: ghi database thành công nhưng gửi event ra ngoài thất bại

Trong ứng dụng Spring, `ApplicationEventPublisher.publishEvent(...)` hữu ích để báo các thành phần trong cùng `ApplicationContext` rằng một sự kiện đã xảy ra. Nhưng khi sự kiện cần đi đến **một process/service khác** (ví dụ billing, vận chuyển, kho, search index hoặc hệ thống gửi thông báo), việc chỉ gọi publisher nội bộ hoặc một HTTP client ngay trong use case **không bảo đảm hai hệ thống cùng thấy một kết quả nhất quán**.

Ví dụ use case đặt hàng có hai hành động:

1. Lưu Order vào database.
2. Gửi `OrderPlaced` sang message broker hoặc dịch vụ ngoài.

Nếu làm lần lượt:

~~~text
Request
   |
   +--> BEGIN DB transaction
   +--> INSERT order
   +--> COMMIT DB
   |
   +--> broker.publish(OrderPlaced)
              |
              +--> network timeout / broker unavailable / process crash
~~~

Database đã ghi đơn hàng, nhưng event cần cho service khác **có thể chưa được giao**. Đảo thứ tự lại cũng không giải quyết được:

~~~text
broker.publish(OrderPlaced) --> accepted
                   |
                   +--> INSERT order
                   +--> DB rollback
~~~

Bên ngoài đã nghe một fact `OrderPlaced` dù đơn hàng nguồn không tồn tại vì transaction rollback.

Đây là **dual-write problem**: ứng dụng đang cố ghi hai tài nguyên độc lập (database và broker) nhưng một transaction database cục bộ không bao trùm cả hai. Chỉ thêm `@Transactional` quanh một HTTP/broker publish không biến database transaction thành distributed transaction.

**Transactional outbox pattern** tách hai mốc:

- Trong **một transaction database**, lưu trạng thái nghiệp vụ **và** một bản ghi outbox mô tả ý định giao event.
- Một **relay process** riêng đọc các outbox record đã commit, chuyển chúng đến broker/đích ngoài, theo dõi kết quả và retry khi cần.

Sơ đồ:

~~~text
OrderService
   |
   |  T1: one local DB transaction
   +-- INSERT orders
   +-- INSERT outbox(eventId, OrderPlaced, ...)
   +-- COMMIT T1
   |
   v
Order DB + Outbox Table
   |
   | Polling relay hoặc CDC relay
   v
Message Broker / Integration Endpoint
   |
   v
Consumer
   +-- deduplicate eventId
   +-- update local state / side effect
   +-- acknowledge/checkpoint
~~~

**Ý nghĩa cốt lõi:** Order và **ý định giao event** cùng commit hoặc cùng rollback. Relay thực hiện network I/O **sau transaction**, có khả năng tiếp tục từ bản ghi bền vững khi process khởi động lại.

Bài này thuộc nhóm **Tích hợp ngoài ứng dụng** của Spring Framework Application Events. Trọng tâm là ranh giới database ↔ relay ↔ broker ↔ consumer, không chỉ cách gọi một annotation event listener.

## 2. Cam kết của outbox: có gì và không có gì?

Outbox giải quyết một loại bất nhất quan trọng:

- Nếu transaction nghiệp vụ **rollback**, bản ghi outbox cũng rollback.
- Nếu transaction nghiệp vụ **commit**, ý định gửi event có một bản ghi bền vững trong cùng database.
- Nếu app hoặc relay chết sau commit, một relay được vận hành đúng có thể tiếp tục từ bản ghi còn pending/chưa được checkpoint.

Nhưng outbox **không tự mang lại “exactly once delivery/effect”**. Relay có thể giao **cùng một event nhiều lần**, đặc biệt khi broker đã nhận nhưng relay chết trước khi cập nhật trạng thái đã gửi. Consumer cần idempotency/deduplication.

### 2.1. Các mức trạng thái phải phân biệt

| Mốc | Có thể khẳng định | Chưa thể khẳng định |
| --- | --- | --- |
| Use case gọi `INSERT outbox` | DB đang được yêu cầu tạo intent | Transaction đã commit |
| Transaction commit | Business state và outbox intent cùng tồn tại | Broker đã nhận event |
| Relay claim record | Worker đã nhận trách nhiệm thử gửi | Đã gửi hoặc nhận ack |
| Broker xác nhận publish theo contract | Broker đã chấp nhận theo mức đảm bảo của nó | Consumer đã xử lý |
| Consumer nhận event | Consumer đã được giao message | Side effect đã commit |
| Consumer commit + ack | Outcome đã ghi theo hợp đồng consumer | Không có redelivery trong tương lai |
| Relay đánh dấu SENT | Relay đã ghi nhận publish ack | Mọi downstream consumer đã hoàn tất |

Không đổi trạng thái outbox sang `SENT` ngay sau khi chỉ **enqueue một tác vụ trong RAM** hoặc trước khi có broker acknowledgement tương ứng.

### 2.2. At-least-once hay exactly-once?

Thiết kế outbox thực dụng thường hướng đến **at-least-once delivery**: sự kiện có thể giao lại, nhưng phải có đường retry/recovery để không bị mất âm thầm. Chính sách cụ thể còn phụ thuộc retention, thời gian sống message, broker ack, vận hành relay và consumer.

“Exactly-once” ở tầng broker (nếu có cơ chế hỗ trợ) **không đồng nghĩa** tác động nghiệp vụ ở database/email/payment bên ngoài sẽ được thực hiện đúng một lần. Cần idempotency key, unique constraint hoặc transaction của consumer để kiểm soát side effect.

## 3. Những thành phần và trách nhiệm

### 3.1. Producer / transaction owner

Ứng dụng nguồn sở hữu aggregate, validation và transaction boundary. Nó tạo sự kiện **sau một thay đổi nghiệp vụ hợp lệ**, nhưng ghi nó vào outbox **trong cùng transaction** với dữ liệu nguồn.

Producer không đợi dịch vụ ngoài xử lý xong; nó cam kết đã ghi ý định giao event. Nếu business API cần chờ downstream hoàn thành, phải có workflow/orchestration và status contract khác, không giả định outbox tự là synchronous RPC.

### 3.2. Outbox storage

Một bảng hoặc cơ chế lưu bền vững chứa event ID, aggregate ID, event type, schema version, payload, timestamps và trạng thái chuyển giao (nếu dùng polling). Outbox được ghi bằng cùng `DataSource`/transaction manager cục bộ với business state. **Đừng dùng hai database độc lập rồi mặc định cả hai cùng commit.**

### 3.3. Relay process

Relay có thể là:

- Một scheduled/polling worker trong cùng codebase nhưng có lifecycle và năng lực riêng.
- Một service/job runner độc lập đọc bảng outbox.
- Một **CDC (Change Data Capture)** connector đọc database commit log, ví dụ Debezium, rồi chuyển outbox insert đến broker.

Dù triển khai ở process nào, relay phải có khả năng khởi động lại, giới hạn số việc đang xử lý và theo dõi lỗi/lag.

### 3.4. Broker và consumer

Broker (Kafka, RabbitMQ, managed queue, v.v.) chịu trách nhiệm lưu/định tuyến message theo chính cấu hình của nó. Consumer xử lý event ở phía nhận, có transaction và checkpoint/ack riêng. Consumer **không được giả định message xuất hiện duy nhất một lần** chỉ vì nguồn dùng outbox.

## 4. Thiết kế bảng outbox cho polling relay

Một mẫu PostgreSQL để minh họa **polling relay có thể cập nhật trạng thái**:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    total_cents BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE outbox (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    aggregate_version BIGINT,
    event_type VARCHAR(120) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    correlation_id VARCHAR(100),
    state VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_owner VARCHAR(100),
    lease_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ,
    last_error_code VARCHAR(100)
);

CREATE INDEX idx_outbox_ready
    ON outbox (state, available_at, created_at, event_id);

CREATE INDEX idx_outbox_aggregate
    ON outbox (aggregate_type, aggregate_id, aggregate_version);
~~~

**Đây là schema minh họa PostgreSQL**, không phải schema SQL chung cho mọi database. Cần review index, partitioning, retention và isolation level với DBA theo tải thực tế.

Một event:

~~~json
{
  "eventId": "11111111-1111-4111-8111-111111111111",
  "aggregateType": "Order",
  "aggregateId": "101",
  "aggregateVersion": 7,
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "occurredAt": "2026-11-11T04:00:00Z",
  "payload": {
    "orderId": 101,
    "totalCents": 8500
  }
}
~~~

Các trường cần cân nhắc:

| Trường | Công dụng | Lưu ý |
| --- | --- | --- |
| `event_id` | Stable identity để dedup | Unique và không đổi khi retry |
| `aggregate_type`/`aggregate_id` | Route/partition cùng aggregate | Không nhét PII vào key tùy tiện |
| `aggregate_version` | Kiểm tra ordering, stale events | Tăng theo quy tắc của domain |
| `event_type`/`schema_version` | Hợp đồng consumer | Có schema evolution |
| `payload` | Dữ liệu fact tối thiểu | Không serialize nguyên JPA entity |
| `correlation_id` | Liên hệ request/workflow | Tránh secret trong correlation ID |
| `state` | Trạng thái relay polling | PENDING/IN_FLIGHT/SENT/FAILED |
| `attempts`/`available_at` | Retry và backoff | Tránh retry vô hạn |
| `lease_owner`/`lease_until` | Claim nhiều relay worker | Cần token/fencing cho update muộn |
| `created_at`/`sent_at` | Đo backlog/lag | Dùng thời gian rõ UTC |
| `last_error_code` | Chẩn đoán | Không ghi raw payload/secrets vào error |

### 4.1. Không dùng bảng polling mutable cho mọi loại CDC

Schema có `state`, `attempts` và các lệnh `UPDATE` thuộc một **thiết kế polling relay**. Với CDC dùng Debezium Outbox Event Router SMT mặc định, mô hình thường là **append-only INSERT vào outbox** để connector đọc database log; cấu hình mặc định của SMT mong outbox change event dạng insert và **không dùng các state updates như tín hiệu event mới**.

Vì vậy cần tách rõ **hai kiểu vận hành**:

- **Polling relay:** ứng dụng/worker cập nhật PENDING → IN_FLIGHT → SENT để quản lý queue.
- **CDC outbox:** application ghi append-only outbox row; connector chuyển bản ghi insert dựa trên change log/offset. Policy cleanup/retention/checkpoint riêng, không bê nguyên mọi state transition polling sang SMT mặc định.

Không phối hợp hai cơ chế một cách ngẫu nhiên trên cùng bảng rồi kỳ vọng mỗi update tạo một message hợp lệ.

## 5. Transaction đúng trong Spring: viết business state và outbox cùng lần commit

Trong Spring, một service có `@Transactional` có thể dùng `JdbcTemplate`/JPA repository ghi business state và outbox. Điều kiện là **cùng transaction manager và database connection/resource tương ứng**.

~~~java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void place(PlaceOrder command) {
        Order order = validateAndCreate(command);
        orders.save(order);
        outbox.insert(
            OrderPlaced.from(order)
        );
    }
}
~~~

Đây là **code minh họa trong ứng dụng có các type/repository chưa định nghĩa**, không phải tệp độc lập để biên dịch. Ví dụ runnable với Spring JDBC/H2 có ở mục 11.

### 5.1. “Same transaction” là điều kiện cốt lõi

Không được tách:

~~~text
T1: save order in DB-A   -> COMMIT
T2: save outbox in DB-B  -> COMMIT
~~~

rồi gọi đó là transactional outbox với bảo đảm atomic. Giữa T1 và T2 vẫn có cửa sổ lỗi. Cùng một RDBMS nhưng dùng connection/transaction manager độc lập cũng có thể phá atomicity.

Nếu service nguồn đã có database, outbox thường được lưu **trong cùng database và transaction cục bộ**; relay mới xử lý việc đưa message ra ngoài.

### 5.2. @Transactional qua proxy và self-invocation

Spring `@Transactional` dạng proxy chỉ intercept lời gọi đi qua bean proxy. Một method `this.place(...)` gọi nội bộ cùng object thường **không mở transaction mới** theo annotation ở method được tự gọi. Vì vậy hãy gọi service transactional qua Spring bean, kiểm thử rollback thật và đừng tự tạo service bằng `new` rồi mong `@Transactional` có tác dụng.

Theo mặc định, Spring rollback khi method transaction ném `RuntimeException` hoặc `Error`; checked exception có rule mặc định khác, có thể cấu hình. Trong bài demo, lỗi giả lập là `IllegalStateException` nên transaction có thể rollback cả order và outbox.

### 5.3. Không gọi broker trong cùng DB transaction rồi tưởng đã atomic

~~~java
@Transactional
public void placeOrder(...) {
    orders.save(...);
    broker.publish(...);
}
~~~

Cho dù `broker.publish` được gọi trước commit, **DB transaction không tự rollback một message đã được broker chấp nhận**. Và nếu DB commit trước publish, app có thể chết trước lần gửi. Outbox chuyển call network ra ngoài transaction, giảm rủi ro mismatch này.

## 6. Relay polling: từ claim đến broker acknowledgement

Một polling relay cần làm nhiều hơn “SELECT các row pending và gửi” nếu có nhiều instance hoặc high traffic.

Một chu kỳ production thường gồm:

1. Chọn batch những record có `state=PENDING` và `available_at <= now()`, hoặc lease cũ đã hết hạn.
2. **Claim atomically** để chỉ một worker sở hữu quyền thử giao trong cửa sổ lease.
3. Commit transaction claim **trước khi làm network I/O** (tránh giữ row locks suốt thời gian gọi broker).
4. Publish tới broker, chờ **ack theo contract broker** (không chỉ enqueue RAM).
5. Khi ack thành công, ghi `SENT` với điều kiện owner/token còn hợp lệ.
6. Nếu lỗi tạm thời, ghi trạng thái retry và `available_at` mới, tăng `attempts`.
7. Nếu lỗi cố định/vượt giới hạn, chuyển `FAILED`/quarantine, alert và có quy trình xử lý lại.
8. Khi worker chết, lease hết hạn khiến record có thể được worker khác thử lại.

~~~text
PENDING
   |
   | claim with lease/fencing
   v
IN_FLIGHT
   |
   +-- ack received --> SENT
   |
   +-- transient failure --> PENDING (available_at future)
   |
   +-- permanent failure --> FAILED / quarantine
   |
   +-- worker crash --> lease expires --> retry/reclaim
~~~

### 6.1. Phác thảo claim trên PostgreSQL

~~~sql
-- Pseudocode SQL cho PostgreSQL; transaction rất ngắn.
BEGIN;

SELECT event_id
FROM outbox
WHERE (state = 'PENDING' AND available_at <= now())
   OR (state = 'IN_FLIGHT' AND lease_until < now())
ORDER BY created_at, event_id
LIMIT 100
FOR UPDATE SKIP LOCKED;

-- Với tập event_id vừa được khóa, cập nhật:
-- state = 'IN_FLIGHT'
-- lease_owner = worker identity
-- lease_until = now() + lease duration
-- attempts = attempts + 1
-- claim_token = fresh unique token (nếu schema có cột này)
-- Sau đó COMMIT trước khi gọi broker.

COMMIT;
~~~

Đây là **đoạn giải thích cơ chế**, không phải một stored procedure tự chạy: application phải nhận tập IDs, thực hiện `UPDATE` đúng các row vừa claim và commit. Cách dùng `FOR UPDATE SKIP LOCKED`/isolation tùy RDBMS và phiên bản. Nếu cần `claim_token`, thêm cột và quy tắc unique token trong schema production.

**Không giữ transaction/row lock trong suốt broker.send()** vì network có thể chậm hoặc timeout, làm nghẽn DB. Worker chỉ cần một claim ngắn rồi giao ngoài transaction claim.

### 6.2. Lease, fencing và race

Giả sử worker A claim event, bị treo lâu và lease hết hạn. Worker B claim lại, gửi thành công, rồi A tỉnh dậy và cố cập nhật SENT hoặc FAILED. Nếu không có **fencing token/claim generation**, update muộn của A có thể ghi đè trạng thái hợp lệ của B.

Một cập nhật nên yêu cầu event ID **và** token claim còn hiện hành, ví dụ:

~~~sql
UPDATE outbox
SET state = 'SENT', sent_at = now()
WHERE event_id = :eventId
  AND state = 'IN_FLIGHT'
  AND claim_token = :claimToken;
~~~

Đây là **SQL minh họa có named parameters**. Chỉ dùng khi schema có `claim_token`, và phải kiểm tra affected row count. Token ngăn stale worker sửa state, **không thể ngăn message đã được gửi trùng**; consumer vẫn cần idempotency.

### 6.3. Polling frequency và batch size

Polling quá thường xuyên có thể làm DB bị quét liên tục; polling quá chậm làm event lag lớn. Chọn batch size, index, worker concurrency, jitter và sleep/backoff dựa trên metric `oldest_pending_age`, query latency và throughput.

Không chỉ dựa vào `Thread.sleep(100)` trong một vòng lặp vô hạn. Có thể dùng `@Scheduled(fixedDelayString=...)`, job runner hoặc dedicated relay service với lifecycle, cancellation, bounded concurrency và graceful shutdown phù hợp. Nếu dùng nhiều instance, phải có claim/lease coordination.

## 7. Cửa sổ lỗi: vì sao retry gây duplicate mà vẫn đúng thiết kế?

Xét các mốc:

~~~text
A. DB commit order + outbox
B. Relay đọc và claim
C. Relay publish event đến broker
D. Broker xác nhận đã chấp nhận
E. Relay ghi SENT vào DB
F. Consumer xử lý/ack
~~~

Các lỗi:

| Lỗi xảy ra tại | Tình trạng | Chiến lược phục hồi |
| --- | --- | --- |
| Trước A | Transaction có thể rollback, không có intent commit | Request retry theo contract |
| Sau A, trước B | Outbox row còn pending | Relay sau restart đọc lại |
| Giữa B và C | Record đang leased nhưng chưa gửi | Lease hết hạn, retry |
| Sau C/D, trước E | Broker **có thể đã nhận**, outbox vẫn chưa SENT | Relay gửi lại; consumer dedup |
| Sau E, trước F | Relay coi broker đã nhận, consumer có thể chưa xong | Broker retention/ack/retry của consumer |
| Trong F trước commit consumer | Consumer có thể nhận lại message | Transactional inbox + idempotency |
| Sau commit consumer, trước ack | Side effect có thể xong nhưng message được giao lại | Dedup theo stable event ID |

**Cửa sổ D → E là quan trọng nhất để hiểu at-least-once:** relay đã giao thành công nhưng chết trước khi update outbox. Sau restart, cùng event được gửi lại là hành vi **có thể xảy ra và phải được thiết kế để chịu đựng**.

Không đặt `SENT` **trước** khi broker thực sự xác nhận theo mức đảm bảo mong muốn: làm vậy mở cửa sổ event bị đánh dấu hoàn thành nhưng chưa được broker nhận.

### 7.1. Broker ack khác consumer ack

Kafka producer acknowledgement, RabbitMQ publisher confirm hay managed queue send acknowledgement là **xác nhận ở tầng broker** theo cấu hình cụ thể. Nó không chứng minh mọi subscriber đã thực thi business side effect. Consumer xử lý và checkpoint/ack là chuỗi trách nhiệm khác.

Vì vậy monitor phải phân biệt **outbox pending lag**, **relay publish success**, **broker queue/consumer lag** và **consumer outcome**.

## 8. Polling relay hay CDC (Change Data Capture)?

Hai cách đều dùng outbox nhưng công cụ, quyền và mô hình khác nhau.

| Tiêu chí | Polling relay | CDC relay (ví dụ Debezium) |
| --- | --- | --- |
| Nguồn đọc | Query outbox table | Database commit/change log |
| Trạng thái xử lý | Thường dùng PENDING/LEASE/SENT | Connector offset/checkpoint, theo SMT |
| Tải lên DB | SELECT/UPDATE theo batch | Log streaming; vẫn có overhead vận hành |
| Độ trễ | Tùy poll interval, batch, DB | Có thể thấp; tùy connector/broker |
| Nhiều worker | Claim/lock/lease | Connector task/partition semantics |
| Vận hành | App tự viết relay và cleanup | Connector, log retention, snapshot, config |
| Portability | SQL theo DB | Phụ thuộc connector/CDC support |
| Failure handling | App sở hữu retry/lease | Connector framework + broker + consumer |
| Ordering | Phải thiết kế claim/sequence | Commit order/partition key tùy pipeline |
| Phù hợp | Hệ thống nhỏ–vừa, hạ tầng đơn giản | Streaming thay đổi lớn và hạ tầng CDC sẵn |

### 8.1. Debezium Outbox Event Router

Debezium cung cấp **Outbox Event Router SMT** có thể biến row insert của outbox thành message cho Kafka. Những field mặc định trong tài liệu Debezium gồm `id`, `aggregatetype`, `aggregateid`, `type` và `payload`.

Ví dụ khái niệm:

~~~text
outbox INSERT:
  id = evt-123
  aggregatetype = Order
  aggregateid = 101
  type = OrderPlaced
  payload = {orderId:101,totalCents:8500}

Debezium connector + Outbox Event Router
  |
  +--> topic như outbox.event.Order
  +--> key là aggregateid
  +--> message body từ payload
  +--> event ID dùng ở header/metadata theo config
~~~

**Lưu ý:** đây là mô tả khái quát, không phải một file cấu hình Debezium đầy đủ. Với SMT mặc định, outbox được kỳ vọng tạo insert và có hành vi lọc delete/update phù hợp. Không giả định schema polling `PENDING/SENT` bên trên sẽ được SMT xử lý tương đương.

`aggregateid` thường dùng làm Kafka key để những event cùng aggregate được đưa tới cùng partition khi partitioning ổn định, hỗ trợ ordering theo key. Nhưng **thứ tự xử lý end-to-end** còn phụ thuộc retry, consumer concurrency và việc có dùng version/sequence guard hay không.

### 8.2. Những trách nhiệm CDC không xóa đi

- Theo dõi connector health, offset lag, database log retention và snapshot behavior.
- Đảm bảo outbox INSERT có schema/payload phù hợp mapping.
- Kiểm tra mapping topic/key, header eventId, schemaVersion.
- Thực hiện idempotent consumer.
- Quản lý migration, cleanup và retention outbox/CDC log.
- Bảo vệ dữ liệu trong commit log, connector, broker và consumer.
- Test restart, connector rebalancing, duplicate delivery và replay.

CDC giúp chuyển cơ chế relay, **không xóa nhu cầu thiết kế message contract và consumer recovery**.

## 9. Ordering: thứ tự commit, gửi và xử lý có thể khác nhau

Giả sử cùng Order 101 có:

~~~text
OrderPlaced      version=1
OrderConfirmed   version=2
OrderShipped     version=3
~~~

Nếu hai relay workers claim ba record và gửi song song, broker hoặc consumer có thể quan sát thứ tự khác. Để giữ đúng state machine:

- Ghi `aggregate_id` và `aggregate_version` ngay khi tạo fact.
- Xây dựng version tăng trong **transaction cập nhật aggregate**.
- Route theo key `aggregate_id` để giữ cùng partition/ordering nơi broker hỗ trợ.
- Tránh xử lý song song cùng aggregate trong consumer nếu cần ordering chặt.
- Consumer kiểm tra version; không áp dụng event cũ nếu aggregate đã ở version mới.
- Xác định policy khi thiếu version (buffer, retry, fetch state, reconcile) thay vì skip vô điều kiện.

### 9.1. Không xem created_at như sequence chính xác

Hai row có thể có timestamp giống nhau, và thời gian do nhiều process tạo có thể lệch. `ORDER BY created_at` hữu ích cho polling nhưng không bảo đảm **logical order** của mọi event. Cần version/sequence hoặc thứ tự commit/partition được thiết kế rõ.

### 9.2. Transaction cho nhiều event cùng aggregate

Nếu một transaction thay đổi aggregate và tạo nhiều event, quy tắc về version và event ordering phải được định nghĩa. Không tái sử dụng cùng `eventId` cho hai fact riêng; event ID là identity của **từng event instance**.

## 10. Idempotent consumer: transaction inbox và side effect

Một consumer có thể nhận cùng event nhiều lần. Mẫu **inbox/dedup table** dùng unique key:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong transaction của consumer:

~~~text
BEGIN consumer transaction
  INSERT (consumerName, eventId) vào inbox với unique constraint
  IF duplicate:
      coi như đã xử lý, không lặp side effect DB
  ELSE:
      áp dụng state change/business effect
COMMIT consumer transaction
ACK message sau commit
~~~

**Điều kiện quan trọng:** inbox insert và **side effect database cục bộ** phải cùng transaction nếu muốn bảo đảm atomic chống lặp cho phần dữ liệu đó. Nếu inbox commit trước rồi side effect DB lỗi, retry có thể bị skip sai.

### 10.1. External side effect phức tạp hơn

Nếu consumer gọi email, payment API hoặc một dịch vụ ngoài, transaction DB của inbox **không thể rollback lời gọi ngoài**. Cần API idempotency key nếu hỗ trợ, mô hình command intent/outbox ở consumer hoặc workflow có reconciliation.

Ví dụ email đã gửi nhưng response timeout: retry cùng event ID có thể gửi trùng nếu provider không hỗ trợ idempotency và hệ thống không theo dõi outcome đúng cách. Không hứa “exactly once email” chỉ vì có inbox table.

### 10.2. Identity phải ổn định

`eventId` phải giữ nguyên trên lần relay retry, broker redelivery hoặc consumer retry cùng một fact. Đổi UUID mỗi lần gửi lại sẽ vô hiệu hóa dedup. Ngược lại, hai sự kiện khác nhau dù cùng order ID không được dùng chung event ID.

## 11. Dự án Java 17+ hoàn chỉnh: atomic outbox, relay và redelivery

Ví dụ sau **chạy độc lập** với Java 17+, Maven, Spring Framework 6.2.8, Spring JDBC và H2 in-memory. Không cần Spring Boot, Kafka hoặc một database server bên ngoài.

Mục tiêu:

1. `OrderService.place(...)` lưu Order + outbox row trong cùng **Spring-managed transaction**.
2. Một lời gọi có lỗi `IllegalStateException` sau khi ghi thử cả hai row bị rollback: **không còn Order và outbox của yêu cầu lỗi**.
3. Relay đọc outbox pending và chuyển đến `FakeBroker`.
4. Relay cố tình mô phỏng **crash sau broker accept nhưng trước khi đánh dấu SENT**, khiến outbox vẫn pending.
5. Relay chạy lại, gửi trùng cùng event ID; consumer dùng **transactional inbox** và unique constraint để tránh ghi side effect database lần hai.
6. Relay đánh dấu SENT sau lần publish/ack giả lập thứ hai.

**Giới hạn đúng của ví dụ:** `FakeBroker` gọi consumer đồng bộ trong cùng JVM để mô phỏng đường gửi/nhận; nó **không** mô phỏng độ bền và các loại acknowledgement của Kafka/RabbitMQ thật. H2 cũng là in-memory database nên **không sống qua process restart**. Lỗi “crash” được mô phỏng bằng việc dừng trước khi cập nhật `SENT` mà không kill process. Bài demo kiểm chứng transaction/logic redelivery, **không phải bằng chứng durable delivery sau kill thật**.

### 11.1. Cấu trúc tệp

~~~text
spring-outbox-relay-demo/
├── pom.xml
└── src/main/java/OutboxRelayDemo.java
~~~

### 11.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-outbox-relay-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>OutboxRelayDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 11.3. src/main/java/OutboxRelayDemo.java

~~~java
import java.util.List;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public final class OutboxRelayDemo {

    public record OutboxRow(
        String eventId, long orderId, String payload
    ) { }

    // Không final: Spring tạo transaction proxy cho service.
    public static class OrderService {
        private final JdbcTemplate jdbc;

        public OrderService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void place(
                long id, long totalCents,
                String eventId, boolean simulateFailure
        ) {
            if (id <= 0 || totalCents <= 0) {
                throw new IllegalArgumentException("invalid order");
            }

            jdbc.update(
                "INSERT INTO orders(id, total_cents) VALUES (?, ?)",
                id, totalCents
            );

            jdbc.update(
                "INSERT INTO outbox(" +
                "event_id, order_id, event_type, payload, status" +
                ") VALUES (?, ?, ?, ?, 'PENDING')",
                eventId,
                id,
                "OrderPlaced",
                "orderId=" + id + ";totalCents=" + totalCents
            );

            if (simulateFailure) {
                throw new IllegalStateException("forced rollback");
            }
        }
    }

    // Side effect cục bộ và inbox được ghi atomically.
    public static class InboxConsumer {
        private final JdbcTemplate jdbc;

        public InboxConsumer(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void consume(OutboxRow row) {
            jdbc.update(
                "INSERT INTO consumer_inbox(event_id) VALUES (?)",
                row.eventId()
            );

            jdbc.update(
                "INSERT INTO notification_effects(" +
                "event_id, order_id) VALUES (?, ?)",
                row.eventId(),
                row.orderId()
            );
        }
    }

    // Mô phỏng broker nhận + chuyển cho consumer.
    public static class FakeBroker {
        private final InboxConsumer consumer;

        public FakeBroker(InboxConsumer consumer) {
            this.consumer = consumer;
        }

        public void publish(OutboxRow row) {
            System.out.println("BROKER_ACCEPTED " + row.eventId());

            try {
                consumer.consume(row);
                System.out.println(
                    "CONSUMER_APPLIED " + row.eventId()
                );
            } catch (DuplicateKeyException ex) {
                // Unique constraint trong consumer_inbox:
                // side effect DB đã được xử lý ở lần giao trước.
                System.out.println(
                    "CONSUMER_DUPLICATE " + row.eventId()
                );
            }
        }
    }

    // Polling relay một worker, chưa có claim/lease đa instance.
    public static class Relay {
        private final JdbcTemplate jdbc;
        private final FakeBroker broker;

        public Relay(JdbcTemplate jdbc, FakeBroker broker) {
            this.jdbc = jdbc;
            this.broker = broker;
        }

        public void tick(boolean crashBeforeMarkSent) {
            List<OutboxRow> pending = jdbc.query(
                "SELECT event_id, order_id, payload " +
                "FROM outbox WHERE status = 'PENDING' " +
                "ORDER BY event_id",
                (rs, n) -> new OutboxRow(
                    rs.getString("event_id"),
                    rs.getLong("order_id"),
                    rs.getString("payload")
                )
            );

            for (OutboxRow row : pending) {
                broker.publish(row);

                if (crashBeforeMarkSent) {
                    System.out.println(
                        "SIMULATED_CRASH_BEFORE_MARK " +
                        row.eventId()
                    );
                    return;
                }

                int changed = jdbc.update(
                    "UPDATE outbox SET status = 'SENT' " +
                    "WHERE event_id = ? AND status = 'PENDING'",
                    row.eventId()
                );

                if (changed != 1) {
                    throw new IllegalStateException(
                        "Unable to mark sent"
                    );
                }

                System.out.println(
                    "RELAY_MARKED_SENT " + row.eventId()
                );
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds =
                new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:outboxdemo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        OrderService orderService(JdbcTemplate jdbc) {
            return new OrderService(jdbc);
        }

        @Bean
        InboxConsumer inboxConsumer(JdbcTemplate jdbc) {
            return new InboxConsumer(jdbc);
        }

        @Bean
        FakeBroker fakeBroker(InboxConsumer consumer) {
            return new FakeBroker(consumer);
        }

        @Bean
        Relay relay(JdbcTemplate jdbc, FakeBroker broker) {
            return new Relay(jdbc, broker);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute(
                "CREATE TABLE orders (" +
                "id BIGINT PRIMARY KEY, total_cents BIGINT NOT NULL)"
            );
            jdbc.execute(
                "CREATE TABLE outbox (" +
                "event_id VARCHAR(80) PRIMARY KEY, " +
                "order_id BIGINT NOT NULL, " +
                "event_type VARCHAR(80) NOT NULL, " +
                "payload VARCHAR(200) NOT NULL, " +
                "status VARCHAR(15) NOT NULL)"
            );
            jdbc.execute(
                "CREATE TABLE consumer_inbox (" +
                "event_id VARCHAR(80) PRIMARY KEY)"
            );
            jdbc.execute(
                "CREATE TABLE notification_effects (" +
                "event_id VARCHAR(80) PRIMARY KEY, " +
                "order_id BIGINT NOT NULL)"
            );

            OrderService orders = context.getBean(
                OrderService.class
            );

            orders.place(101L, 8500L, "evt-101", false);

            try {
                // INSERT order/outbox đều được gọi, nhưng
                // exception làm rollback transaction.
                orders.place(102L, 9900L, "evt-102", true);
            } catch (IllegalStateException ex) {
                System.out.println("ROLLBACK_CONFIRMED");
            }

            System.out.println(
                "ORDERS=" + jdbc.queryForObject(
                    "SELECT COUNT(*) FROM orders", Integer.class
                )
            );

            System.out.println(
                "OUTBOX_PENDING=" + jdbc.queryForObject(
                    "SELECT COUNT(*) FROM outbox " +
                    "WHERE status = 'PENDING'",
                    Integer.class
                )
            );

            Relay relay = context.getBean(Relay.class);

            // Đã giao tới FakeBroker/consumer nhưng chưa
            // ghi trạng thái SENT: mô phỏng crash window.
            relay.tick(true);

            System.out.println(
                "PENDING_AFTER_SIMULATED_CRASH=" +
                jdbc.queryForObject(
                    "SELECT COUNT(*) FROM outbox " +
                    "WHERE status = 'PENDING'",
                    Integer.class
                )
            );

            // Giao lại event cũ: unique inbox chống
            // lặp side effect DB trong consumer.
            relay.tick(false);

            System.out.println(
                "OUTBOX_SENT=" + jdbc.queryForObject(
                    "SELECT COUNT(*) FROM outbox " +
                    "WHERE status = 'SENT'",
                    Integer.class
                )
            );

            System.out.println(
                "NOTIFICATION_EFFECTS=" +
                jdbc.queryForObject(
                    "SELECT COUNT(*) FROM notification_effects",
                    Integer.class
                )
            );
        }
    }
}
~~~

### 11.4. Chạy và output mong đợi

Tại thư mục `spring-outbox-relay-demo`, sử dụng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java
~~~

Các dòng **do chương trình in** khi không xảy ra lỗi cấu hình/dependency:

~~~text
ROLLBACK_CONFIRMED
ORDERS=1
OUTBOX_PENDING=1
BROKER_ACCEPTED evt-101
CONSUMER_APPLIED evt-101
SIMULATED_CRASH_BEFORE_MARK evt-101
PENDING_AFTER_SIMULATED_CRASH=1
BROKER_ACCEPTED evt-101
CONSUMER_DUPLICATE evt-101
RELAY_MARKED_SENT evt-101
OUTBOX_SENT=1
NOTIFICATION_EFFECTS=1
~~~

### 11.5. Phân tích output

**Rollback được kiểm chứng bằng DB:** lời gọi `place(102, ..., true)` chèn thử order/outbox rồi ném `IllegalStateException`. Vì `OrderService` được lấy từ Spring context và `@EnableTransactionManagement` có mặt, transaction proxy điều phối rollback. Query sau đó có `ORDERS=1` và `OUTBOX_PENDING=1`: chỉ order 101 và event tương ứng còn tồn tại.

**Lần relay đầu:** đọc `evt-101` pending, gọi `FakeBroker.publish`, consumer ghi `consumer_inbox` và `notification_effects` trong một transaction rồi in `CONSUMER_APPLIED`. Relay cố ý không chạy `UPDATE status='SENT'`, nên in `SIMULATED_CRASH_BEFORE_MARK` và row còn pending.

**Lần relay thứ hai:** đọc lại `evt-101` và publish lần nữa. Insert trùng `consumer_inbox.event_id` vi phạm primary key, Spring JDBC ném `DuplicateKeyException`, transaction của consumer bị rollback và side effect thứ hai không được tạo. Fake broker in `CONSUMER_DUPLICATE`. Relay đánh dấu SENT, cuối cùng `NOTIFICATION_EFFECTS=1`.

**Không suy diễn quá mức:** cơ chế chống trùng ở đây áp dụng cho **side effect trong database của consumer**. Nếu thay `notification_effects` bằng email/network call, cần chiến lược idempotency và xử lý uncertain outcome riêng. Và ở ví dụ H2, fake broker không tách process; production phải xác định chính xác mốc broker ack.

### 11.6. Vì sao dùng JdbcTemplate thay vì ApplicationEventPublisher?

Ví dụ cần **thao tác transaction và outbox lưu bền vững**, nên dùng `JdbcTemplate` dưới `DataSourceTransactionManager` để nhìn thấy rõ hai row commit/rollback cùng nhau. `ApplicationEventPublisher` có thể vẫn được dùng trong process cho công việc best-effort; nó **không** tự làm payload xuất hiện trong outbox table.

Một kiến trúc có thể có cả hai:

~~~text
OrderService transaction
   +--> orders table
   +--> outbox table       [external integration contract]

Optional after-commit internal event
   +--> in-process metrics/cache listeners (best effort)
~~~

Đừng dùng một `@EventListener` async để ghi outbox **sau** commit rồi gọi đó là transactional outbox: nếu process chết trước khi listener ghi, intent có thể mất. Outbox nên được ghi **cùng transaction nguồn**, qua service/repository được gọi rõ ràng.

## 12. So sánh @EventListener, @TransactionalEventListener và outbox

| Phương án | Khi nào chạy | Bảo đảm lưu intent sau crash? | Giới hạn |
| --- | --- | --- | --- |
| `@EventListener` sync | Khi event được dispatch trong context | Không | Phụ thuộc thread/transaction, không qua process |
| `@Async @EventListener` | Khi executor chạy task | Không | RAM queue, lỗi async, process crash |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau commit của transaction phù hợp | Không | Đúng phase nhưng có khoảng hở commit → worker |
| Ghi outbox trong `@Transactional` | Intent và domain state cùng commit | **Có, theo durability của DB** | Chưa giao broker, cần relay |
| Polling relay | Sau khi outbox đã commit | Theo DB + retry/lease design | Dễ duplicate, cần claim/monitor |
| CDC relay | Đọc database log/offset | Theo connector/retention/ack setup | Cần vận hành CDC và broker |
| Broker + idempotent consumer | Sau khi message đến consumer | Theo broker/consumer storage | Cần dedup và xử lý lỗi end-to-end |

### 12.1. AFTER_COMMIT không thay outbox

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` chỉ điều phối **thời điểm listener có thể thực thi** sau commit. Nếu process crash sau khi DB commit nhưng trước listener/broker publish, event vẫn có thể mất nếu chưa có intent bền vững.

Nếu publish ngoài transaction, `@TransactionalEventListener` mặc định có thể không chạy khi không cấu hình `fallbackExecution=true`. Đây là hành vi riêng của transaction-bound listener, không phải một cơ chế durability.

### 12.2. @Async không chia sẻ transaction nguồn

Worker `@Async` chạy trên thread khác, không tự kế thừa imperative thread-bound transaction của publisher. Một worker viết outbox ở transaction riêng **sau** commit có cửa sổ mất intent. Nếu job thật sự phải tồn tại, ghi outbox tại source transaction trước.

### 12.3. Tại sao không dùng dual-write với “retry tại controller”?

Nếu save DB thành công rồi gửi broker lỗi, API có thể trả lỗi để client retry toàn bộ request. Điều này có thể tạo order thứ hai, duplicate payment hoặc trạng thái không rõ ràng. Idempotency ở HTTP command là hữu ích, nhưng vẫn **không bảo đảm event từng được ghi bền vững** nếu bước gửi ngoài chưa có outbox.

## 13. Relay process như một dịch vụ sản xuất

Một relay production thường có:

- **Owner/lifecycle rõ:** một scheduled worker riêng, service hoặc CDC connector.
- **Batching và rate limit:** giới hạn số row claim, số sends đang chạy, tránh spam broker.
- **Lease/fencing:** nhiều instances có thể hợp tác, không ghi đè stale state.
- **Retry:** exponential backoff + jitter, phân loại transient/permanent.
- **Ack-aware update:** không mark SENT trước confirmed broker publish.
- **Dead-letter/quarantine:** lỗi schema/payload vĩnh viễn cần con người hoặc sửa dữ liệu.
- **Outbox cleanup:** retention cho row SENT, không delete pending chưa xử lý.
- **Alerting:** oldest pending age, failed total, lease expirations, backlog.
- **Graceful shutdown:** dừng claim mới, đợi in-flight trong budget, thả claim/để lease expire.
- **Operational replay:** cách retry event chọn lọc với cùng event ID và audit trail.

### 13.1. Scheduling với Spring

Ví dụ trong ứng dụng Spring có cấu hình `@EnableScheduling`:

~~~java
@Component
public class RelayScheduler {
    private final RelayService relay;

    public RelayScheduler(RelayService relay) {
        this.relay = relay;
    }

    @Scheduled(fixedDelayString = "PT1S")
    public void runCycle() {
        relay.claimAndDispatchBatch();
    }
}
~~~

Đây là **snippet minh họa**: cần import annotation, `RelayService` thực tế, xử lý lỗi và không bắt đầu hai chu kỳ chồng lên nhau ngoài ý định. Giá trị `PT1S` (duration string) là lịch ví dụ, không phải policy tối ưu. Trong multi-instance, `@Scheduled` chạy ở từng instance nếu được bật; claim lock/lease vẫn bắt buộc.

### 13.2. Tối ưu relay không làm mất dữ liệu

Backpressure có thể khiến relay chậm hoặc tạm dừng, nhưng outbox backlog vẫn được lưu trong DB. Nếu storage tăng vô hạn hoặc không có capacity plan, DB có thể đầy và ảnh hưởng transaction nghiệp vụ. Do đó giám sát **oldest pending**, kích thước table, tốc độ insert/send, index health và dọn row đã giao đúng policy.

### 13.3. Khi nào cần tách process?

Tách relay khỏi request service có lợi nếu broker I/O tốn tài nguyên, cần scale/rollout độc lập hoặc muốn một process chỉ làm job delivery. Tuy nhiên một relay nằm cùng application vẫn có thể dùng outbox đúng nếu storage durable và startup/shutdown được kiểm soát. **Tên “relay process” không bắt buộc một executable riêng**, nhưng tách deployment thường thuận tiện cho vận hành tải lớn.

## 14. Hợp đồng event, schema evolution và bảo vệ dữ liệu

Một outbox row có thể sống lâu hơn release đã tạo nó. Consumer có thể xử lý event sau khi code/schema thay đổi. Vì vậy contract cần:

- `eventType` và `schemaVersion` rõ, có chính sách backward compatibility.
- Stable `eventId`, `aggregateId` và `aggregateVersion` nếu cần ordering.
- Payload không phụ thuộc raw JPA entity hoặc internal Java class name.
- Trường hợp consumer cũ/ mới đọc event khác version phải có serializer/deserializer policy.
- Migration trước khi thêm field bắt buộc hoặc đổi meaning.
- Retention và cleanup rõ ràng; không delete những row còn cần retry hoặc CDC đọc.

### 14.1. Không serialize thừa PII

Outbox tăng độ bền, nên event nhạy cảm có thể tồn tại dài trong DB, backup, change log, broker và consumer logs. Chỉ đưa dữ liệu cần thiết, mã hóa ở rest/in transit theo policy, kiểm soát quyền DB/connector, secret management, retention và yêu cầu xóa dữ liệu.

Đừng đưa access token, password, raw HTTP request, full `Authentication` hoặc JPA entity có graph quan hệ vào payload chỉ vì nó có sẵn tại thời điểm publish.

### 14.2. Event ID và correlation ID

`eventId` dùng dedup của một fact. `correlationId` liên kết workflow; `causationId` có thể chỉ event/command gây ra event hiện tại. Hai field trace này **không thay thế idempotency key** và cũng không phải dữ liệu nên dùng làm Prometheus label có cardinality cao.

## 15. Observability: đo backlog và độ trễ thật

Một pipeline outbox có nhiều chỗ thành công/thất bại:

~~~text
source committed -> outbox pending -> claimed -> broker accepted
    -> consumer received -> consumer DB committed -> consumer ack
~~~

Cần đo riêng:

- `outbox_created_total`, `outbox_pending_count`, `outbox_oldest_pending_age_seconds`.
- `relay_claimed_total`, `relay_publish_success_total`, `relay_publish_failed_total`.
- `relay_retry_total`, `relay_lease_expired_total`, `relay_failed_or_quarantined_total`.
- `relay_publish_duration_seconds` và `outbox_delivery_lag_seconds`.
- Broker queue depth/consumer lag theo công nghệ đang dùng.
- `consumer_processed_total`, `consumer_duplicate_total`, `consumer_failure_total`.
- `inbox_commit_latency` và downstream side-effect outcome.
- DB outbox table size, write latency, read query latency, disk/storage headroom.

Tên trên là **gợi ý metric ứng dụng tự định nghĩa**, không mặc định Spring cung cấp.

### 15.1. Metric và log không được lộ dữ liệu

`eventId`, `orderId`, email hoặc tenant ID cardinality cao nên ở **structured logs/traces có kiểm soát**, không ở metric labels không giới hạn. Error code nên hữu hạn, không copy raw exception message chứa PII vào metric label.

Ví dụ log có mục đích:

~~~text
stage=outbox_insert eventType=OrderPlaced eventId=evt-101 status=committed
stage=relay_send eventId=evt-101 attempt=1 status=acked
stage=relay_recover eventId=evt-101 attempt=2 status=redelivered
stage=consumer eventId=evt-101 status=duplicate_skipped
~~~

Các dòng này chỉ là format minh họa, không phải log tự sinh bởi demo trong mục 11.

### 15.2. Đặt SLO phù hợp

Ví dụ các SLO cần thống nhất với nghiệp vụ:

- 99.9% outbox row được broker chấp nhận trong 30 giây sau commit.
- Oldest pending age hiếm khi vượt vài phút.
- Không có row pending vĩnh viễn mà không alert.
- Consumer processing lag và duplicate count được đo.
- Retry/failed/quarantine có runbook và owner.

**Những con số chỉ là ví dụ, không phải khuyến nghị cố định.** Độ trễ cho billing, email và analytics có thể khác nhau đáng kể.

## 16. Những lỗi triển khai thường gặp

1. **Ghi Order rồi publish broker ngoài transaction, không có outbox:** dual-write gap gây mất event.
2. **Publish broker trước commit:** consumer có thể thấy fact dù DB rollback.
3. **Ghi outbox bằng database/transaction khác Order:** không còn atomic.
4. **Đưa INSERT outbox vào @Async listener sau commit:** process crash có thể mất intent.
5. **Coi @TransactionalEventListener(AFTER_COMMIT) là durable queue:** chỉ điều phối phase.
6. **Mark SENT trước khi có broker ack:** mất event nếu broker chưa nhận.
7. **Tưởng broker ack chứng minh consumer side effect đã commit:** hai mốc khác nhau.
8. **Không có stable eventId:** retry sinh UUID mới, dedup không hoạt động.
9. **Coi at-least-once = exactly-once:** duplicate là tình huống bình thường.
10. **Consumer inbox insert và DB effect không cùng transaction:** có thể skip sai hoặc lặp hiệu ứng.
11. **Dùng inbox DB để hứa exactly-once external email:** không giải quyết uncertainty của API ngoài.
12. **Nhiều relay poll cùng record không claim atomically:** gửi trùng ngoài dự kiến.
13. **Giữ DB lock suốt network send:** tăng contention, deadlock, transaction duration.
14. **Lease hết hạn nhưng không có fencing token:** stale worker cập nhật trạng thái của worker mới.
15. **Dựa vào created_at để bảo đảm ordering tuyệt đối:** timestamp không phải aggregate sequence.
16. **Không giới hạn batch/retry:** relay overload làm DB và broker suy yếu.
17. **Không có backoff/quarantine:** payload lỗi mãi bị gửi vô hạn.
18. **Xóa outbox row trước khi connector đọc:** CDC bị mất dữ liệu.
19. **Trộn mutable polling schema vào Debezium SMT mặc định:** update state không tương đương event insert.
20. **Chỉ đo outbox insert, không đo oldest pending age:** backlog có thể tăng vô hạn.
21. **Không version event schema:** consumer cũ không đọc được message mới.
22. **Serialize JPA entity/secret/PII vào payload:** tạo nhiều bản sao dữ liệu lâu dài.
23. **Không có shutdown/restart tests:** pending/leased job kẹt sau deploy.
24. **Không có runbook khi broker down dài:** DB outbox table tăng đến đầy disk.
25. **Dùng H2 in-memory demo như bằng chứng crash durability:** H2 memory mất khi restart process.

## 17. Kế hoạch kiểm thử từ unit đến failure injection

| Test case | Kỳ vọng |
| --- | --- |
| Use case thành công | Có 1 Order + 1 outbox row cùng commit |
| Business exception sau hai INSERT | Không có Order/outbox của transaction rollback |
| Outbox insert lỗi | Transaction Order cũng rollback |
| Relay nhận pending | Gửi với stable eventId, mark SENT sau ack |
| Broker publish lỗi tạm thời | Row còn khả năng retry, backoff |
| Broker ack nhưng relay crash trước SENT | Giao lại sau restart, consumer dedup |
| Consumer DB lỗi sau inbox insert | Cả inbox và side effect DB rollback |
| Message được giao lại | Unique key ngăn lặp DB effect |
| Nhiều relay workers | Claim/lease không làm job bị kẹt hoặc ghi state sai |
| Lease timeout/race | Stale token không overwrite claim mới |
| Event cùng aggregate, nhiều version | Ordering/version guard bảo vệ state |
| Relay bị shutdown giữa batch | Pending/lease có thể phục hồi |
| Outbox retention cleanup | Chỉ xóa row đã giao và được phép xóa |
| CDC connector restart | Offset/replay, mapping key/type và dedup đúng |
| Schema version mới | Consumer backward/forward compatibility theo contract |
| Broker down lâu | Alert backlog, không hết disk âm thầm |
| Payload chứa thông tin nhạy cảm | Không leak qua outbox/log/broker |
| Multi-tenant | Routing và authorization đúng tenant |

### 17.1. Unit test khác integration test

Unit test có thể mock `OutboxRepository` để kiểm tra service gọi insert sau khi tạo Order; nó **không chứng minh transaction atomic**. Integration test với database và Spring transaction manager thật mới xác minh rollback của cả hai row khi throw exception.

### 17.2. Test broker ack gap

Để kiểm chứng duplicate handling, inject điểm lỗi **sau publish ack, trước mark SENT**. Đừng chỉ giả lập “broker không nhận” vì đó là đường lỗi khác. Demo mục 11 mô phỏng đúng ack gap để thấy `CONSUMER_DUPLICATE` khi relay gọi lại.

### 17.3. Kiểm thử process restart thật

Với PostgreSQL/MySQL thật hoặc một DB durable tương đương, hãy:

1. Commit business + outbox row.
2. Dừng/kill relay trước khi gửi hoặc sau broker accept trước mark SENT.
3. Restart relay.
4. Xác minh row được claim/retry.
5. Xác minh consumer idempotent trong database của nó.
6. Kiểm tra offset/checkpoint và cleanup để không tạo message mất/lặp vô hạn.

Một test trên H2 in-memory **không thay thế** được test restart này.

## 18. Checklist triển khai sản xuất

- [ ] Business state và outbox dùng cùng local database transaction?
- [ ] Ghi outbox trực tiếp trong use case transaction, không đợi async after-commit?
- [ ] Event ID/aggregate ID/version/schema version rõ ràng?
- [ ] Relay là polling hay CDC, không lẫn lộn state protocol?
- [ ] Mark SENT chỉ sau broker ack theo contract?
- [ ] Khi broker down, row vẫn có đường retry và backoff?
- [ ] Polling multi-worker có claim/lease/fencing hợp lệ?
- [ ] Batch size, queue capacity và network concurrency được giới hạn?
- [ ] Có retry budget, poison-message quarantine và runbook?
- [ ] Consumer có dedup theo stable eventId, xử lý trong transaction cục bộ?
- [ ] External API side effect có idempotency/reconciliation riêng?
- [ ] Có aggregate ordering/version guard khi cần?
- [ ] Có metrics oldest pending age, sent/failed/retry/duplicate?
- [ ] Có giám sát disk/table growth và cleanup/retention?
- [ ] Outbox/broker/log payload được phân loại, mã hóa và kiểm soát truy cập?
- [ ] Có integration test commit/rollback và crash/ack-gap?
- [ ] Relay shutdown/restart, broker failure và CDC offset đã được diễn tập?
- [ ] SLA API nói rõ accepted/committed hay external processing completed?

## 19. Bài tập tự kiểm tra

1. Vì sao `@Transactional` quanh `orders.save()` và `broker.publish()` không tạo atomic write tới cả DB và broker?
2. Ghi outbox và Order ở hai database độc lập có còn cùng transaction cục bộ không?
3. Relay đã nhận broker ack nhưng crash trước khi mark SENT. Sau restart có thể xảy ra điều gì?
4. Vì sao consumer phải giữ `eventId` ổn định và dùng unique constraint/inbox?
5. Inbox insert đã commit nhưng update DB side effect thất bại: thiết kế này có vấn đề gì?
6. Có thể dùng `@TransactionalEventListener(AFTER_COMMIT)` thay outbox để bảo đảm delivery qua crash không?
7. Trong demo, vì sao `ORDERS=1` dù `place(...)` được gọi hai lần?
8. Vì sao demo in `BROKER_ACCEPTED evt-101` hai lần nhưng `NOTIFICATION_EFFECTS=1`?
9. Polling relay và Debezium CDC outbox khác nhau ở chỗ nào về PENDING/SENT/INSERT?
10. Vì sao update `SENT` phải kiểm tra claim token/affected row count trong môi trường nhiều worker?
11. `FOR UPDATE SKIP LOCKED` giúp gì, và vì sao không giữ lock khi gọi broker?
12. `aggregateVersion` giải quyết vấn đề gì khi hai event cùng aggregate bị xử lý khác thứ tự?
13. Broker ack có nghĩa consumer đã ghi DB xong chưa?
14. Nếu broker không hoạt động trong ba ngày, cần theo dõi những thứ gì?
15. Nếu event chứa email/password, outbox làm rủi ro dữ liệu tăng hay giảm?
16. Khi nào chọn polling và khi nào chọn CDC?

**Định hướng:** (1) local DB transaction không bao trùm broker; (2) không; (3) gửi lại cùng event, có thể duplicate; (4) dedup; (5) consumer có thể skip dù effect chưa thành công; (6) không; (7) lời gọi thứ hai throw và rollback; (8) inbox unique chống lặp DB effect; (9) polling thường update state, CDC default router xử lý insert qua log/offset; (10) tránh stale update; (11) chia claim giữa worker, giảm DB lock duration; (12) ordering/skip stale; (13) không; (14) pending age, disk, retries, error/consumer lag; (15) tăng số nơi lưu nếu không tối giản; (16) tùy hạ tầng, độ trễ, tải và vận hành.

## 20. Tổng kết

**Transactional outbox** giải quyết cửa sổ bất nhất giữa business database và ý định phát message ra ngoài bằng cách ghi **cả hai trong một transaction cục bộ**. **Relay process** tách riêng việc giao event qua mạng sau commit, sử dụng polling hoặc CDC, và chịu trách nhiệm retry, acknowledgement, recovery và observability.

Những điểm phải ghi nhớ:

- Order/business state và outbox intent **commit/rollback cùng nhau**.
- Relay đọc row đã commit, gửi broker và chỉ mark SENT sau ack phù hợp.
- Relay crash sau broker accept trước cập nhật trạng thái có thể gây **duplicate**.
- Consumer cần stable eventId, inbox/idempotency và transaction cho side effect DB.
- Polling relay và CDC/Debezium không dùng chung mọi giả định về schema/status.
- Ordering, lease/fencing, retry, dead-letter, retention và monitoring là phần thiết kế production.
- `@EventListener`, `@Async` hoặc `@TransactionalEventListener(AFTER_COMMIT)` **không tự thay thế durable outbox**.
- Mọi payload bền vững cần schema version, data minimization và security controls.

Outbox **không làm cho hệ thống phân tán trở thành một transaction duy nhất**. Nó tạo một đường giao event có thể phục hồi, để các service xử lý eventual consistency có kiểm soát.

## Tài liệu tham khảo

- Spring Framework — *Using @Transactional*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — *Programmatic Transaction Management and DataSourceTransactionManager*: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework — *JDBC Core / JdbcTemplate*: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework 6.2.8 Javadoc — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Debezium — *Outbox Event Router*: https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html
- Microservices Patterns — *Transactional Outbox*: https://microservices.io/patterns/data/transactional-outbox.html
