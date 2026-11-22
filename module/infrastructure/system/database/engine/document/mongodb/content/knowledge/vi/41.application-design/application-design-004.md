# Dữ liệu sự kiện: lưu lịch sử, thời gian giữ và truy vấn tổng hợp trong MongoDB

## 1. Vì sao phải thiết kế dữ liệu sự kiện khác dữ liệu trạng thái?

Một ứng dụng có thể có document `orders` biểu diễn **trạng thái hiện tại** của đơn hàng:

~~~javascript
{
  _id: "order-101",
  tenantId: "tenant-A",
  status: "SHIPPED",
  total: NumberDecimal("125.50"),
  updatedAt: ISODate("2026-11-14T09:05:00Z")
}
~~~

Document này trả lời câu hỏi “Đơn hàng hiện ở trạng thái nào?”. Nhưng nó không tự trả lời:

- Đơn được tạo lúc nào, qua những trạng thái nào?
- Ai hoặc hệ thống nào thay trạng thái, và vì sao?
- Đã phát sinh bao nhiêu sự kiện `OrderPaid` trong một giờ?
- Những thao tác nào cần giữ 30 ngày, 13 tháng hoặc lâu hơn?
- Khi khách hàng yêu cầu đối soát, làm sao tái dựng diễn biến?
- Hệ thống báo cáo có thể xem dữ liệu tổng hợp mà không quét hàng tỷ bản ghi không?

Để trả lời, ta thường lưu **event history** theo hướng append-only: mỗi thay đổi quan trọng tạo một sự kiện mới, thay vì ghi đè sự kiện cũ.

~~~text
Orders collection: trạng thái hiện tại
  order-101: SHIPPED
             |
             +------> Event history:
                        08:00 OrderCreated
                        08:10 PaymentAuthorized
                        08:15 PaymentCaptured
                        09:00 OrderPacked
                        09:05 OrderShipped
                                     |
                        +------------+------------+
                        |                         |
                        v                         v
                  Timeline API             Daily rollups
~~~

Bài thuộc module **Database Engine Document MongoDB**, chương **Thiết kế ứng dụng**, với đề bài **Dữ liệu sự kiện: lưu lịch sử, thời gian giữ và truy vấn tổng hợp**.

### 1.1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt event log, audit log, domain event, telemetry và change stream.
2. Thiết kế document sự kiện với identity, tenant, actor, timestamps, schema version và payload.
3. Phân biệt `occurredAt` (event time), `receivedAt` (ingest time) và `expiresAt`.
4. Lưu lịch sử append-only và xử lý correction, replay, duplicate, out-of-order events.
5. Chọn collection thông thường, time-series collection hoặc bucket document khi phù hợp.
6. Thiết kế unique index, compound index, shard key và partition theo workload.
7. Áp retention bằng TTL index hoặc time-series `expireAfterSeconds`, hiểu độ trễ xóa và rủi ro.
8. Xây chính sách hot/warm/cold archive, legal hold và dữ liệu cá nhân.
9. Viết pipeline tổng hợp theo giờ/ngày/tháng bằng `$match`, `$dateTrunc`, `$group`.
10. Xử lý timezone, ngày có DST, missing time buckets và late arrivals.
11. Tạo rollup/materialized views bằng `$merge` hoặc worker.
12. Biết khi nào dùng Change Streams để cập nhật projection và vì sao cần checkpoint/idempotency.
13. Viết ví dụ MongoDB Java Driver/Spring Data MongoDB để ingest và aggregate.
14. Chẩn đoán performance, memory/disk spilling, query indexes, TTL backlog và data correctness.
15. Hoàn thành bài tập thực hành và checklist production.

## 2. Có nhiều loại “sự kiện”, không phải một định dạng chung

| Loại | Ví dụ | Mục đích | Đặc điểm lưu trữ |
|---|---|---|---|
| Domain event | `OrderPaid`, `RentalReturned` | Mô tả nghiệp vụ đã xảy ra | Identity + business version + context |
| Audit event | Ai thay quyền user nào? | Truy vết, kiểm soát | Actor, before/after, integrity |
| Application event | Request retry, job completed | Chẩn đoán ứng dụng | Correlation/tracing, retention ngắn |
| Security event | Login denied, role grant | Điều tra bảo mật | Retention và truy cập hạn chế |
| Telemetry/measurement | CPU 65%, nhiệt độ 28°C | Phân tích theo thời gian | Nhiều điểm đo, cấu trúc đều |
| CDC/change event | MongoDB insert/update/delete | Đồng bộ downstream | Resume token và scope |
| Business fact | Một giao dịch thanh toán | Báo cáo và đối soát | Tiền tệ, ID tham chiếu, trạng thái |

### 2.1. Domain event không đồng nghĩa log text

Chuỗi `"user did something"` không đủ để tái dựng nghiệp vụ. Event tốt có:

- Loại sự kiện được định nghĩa rõ.
- ID duy nhất ở phạm vi đã chọn.
- ID đối tượng nghiệp vụ.
- Timestamp và actor.
- Payload tối thiểu có schema version.
- Thông tin correlation/causation.
- Chính sách retention.

### 2.2. Audit event không nhất thiết là event-sourcing event

Audit phục vụ điều tra; event sourcing có thể sử dụng chuỗi events làm **nguồn sự thật** để tái dựng aggregate. Hai mô hình có yêu cầu khác nhau về bất biến dữ liệu, thứ tự, consistency và retention.

**Không** bật TTL 30 ngày lên event store làm nguồn sự thật của một hệ thống event-sourced mà chưa có snapshot/replay/long-term preservation.

### 2.3. MongoDB Change Streams không thay event history

Change Stream đọc lịch sử thao tác trên oplog, không phải kho sự kiện nghiệp vụ vô hạn. Resume token chỉ dùng được khi lịch sử oplog phù hợp còn tồn tại.

Nếu cần truy vấn các events ba năm trước, thường phải có collection/archive được thiết kế cho mục đích đó, thay vì đợi `watch()`.

## 3. Ba câu hỏi thiết kế trước khi tạo collection

1. **Dữ liệu dùng để làm gì?** Timeline cho user, audit, analytics theo giờ, replay trạng thái, hay regulatory evidence?
2. **Giữ trong bao lâu?** Dựa vào product value, chi phí và nghĩa vụ pháp lý, không dựa vào mặc định TTL ngẫu nhiên.
3. **Truy vấn phổ biến là gì?** Theo `tenantId + entityId`, theo thời gian, theo `eventType`, hay GROUP BY theo ngày?

Một schema chỉ tối ưu insert throughput nhưng không có index/filter theo thời gian có thể làm dashboard chậm. Ngược lại, nhiều indexes trên event stream lớn làm tăng write amplification và storage cost.

## 4. Đề xuất schema cho event history thông thường

Ví dụ một event dạng document:

~~~javascript
{
  _id: "evt-order-101-0004",
  tenantId: "tenant-A",
  eventId: "evt-order-101-0004",
  aggregateType: "Order",
  aggregateId: "order-101",
  aggregateVersion: NumberLong(4),
  eventType: "OrderShipped",
  schemaVersion: 2,
  occurredAt: ISODate("2026-11-14T09:05:00.000Z"),
  receivedAt: ISODate("2026-11-14T09:05:00.180Z"),
  actor: {
    kind: "system",
    id: "warehouse-worker"
  },
  correlationId: "checkout-request-204",
  causationId: "evt-order-101-0003",
  payload: {
    carrier: "carrier-demo",
    trackingReference: "tracking-redacted",
    region: "south"
  },
  retentionClass: "standard",
  expiresAt: ISODate("2027-02-12T09:05:00.000Z")
}
~~~

### 4.1. Identity và duplicate protection

- `_id` hoặc `eventId` là định danh duy nhất của event.
- `tenantId` là ranh giới logic của đa khách hàng.
- `aggregateId` nối event với đối tượng.
- `aggregateVersion` biểu thị thứ tự theo đối tượng khi workflow kiểm soát được version.

Nếu producer retry sau timeout, cùng event phải có **cùng event ID** để tránh nhân đôi. Không tạo ObjectId mới cho mỗi retry rồi coi đó là một sự kiện nghiệp vụ khác.

### 4.2. occurredAt và receivedAt khác nhau

- `occurredAt`: thời điểm nghiệp vụ thực sự xảy ra, theo clock/source đáng tin cậy.
- `receivedAt`: thời điểm server ingest nhận/ghi event.

Một thiết bị mất mạng 2 giờ có thể gửi event lúc 11:00 mà `occurredAt` là 09:00. Đây là **late-arriving event**, không phải dữ liệu sai mặc định.

### 4.3. actor, correlationId và causationId

Các trường này giúp truy vết:

~~~text
Request R42
  |
  +--> PaymentAuthorized event
              |
              +--> OrderConfirmed event
                        |
                        +--> ShipmentScheduled event
~~~

Không cần đưa email, số điện thoại hoặc toàn bộ HTTP headers vào mỗi event chỉ để theo dõi. Dùng internal identifiers được kiểm soát quyền.

### 4.4. schemaVersion

Payload thay đổi theo release:

~~~text
OrderPaid v1: { amount, currency }
OrderPaid v2: { amount, currency, paymentMethodCategory }
~~~

Consumers cần versioned decoders/upcasters hoặc migration plan. Đừng rename field âm thầm rồi kỳ vọng báo cáo cũ vẫn đúng.

### 4.5. Dùng Decimal128 cho tiền tệ

Giá trị tiền không nên dùng binary floating-point tùy tiện nếu yêu cầu chính xác đến cents. MongoDB hỗ trợ BSON Decimal128; cần thống nhất currency, rounding và conversion policy.

## 5. Append-only: chỉnh sửa bằng sự kiện mới

Trong event history có ý nghĩa pháp lý/nghiệp vụ, nên lưu một event mới để sửa kết quả thay vì thay payload event cũ.

~~~text
2026-11-14 09:00  PaymentCaptured amount 125.50
2026-11-14 09:10  PaymentRefunded amount 20.00
2026-11-14 09:15  PaymentAdjustmentPosted amount -5.00
~~~

Trạng thái/tổng tiền được suy ra từ chuỗi sự kiện theo quy tắc domain.

### 5.1. Chống sửa lịch sử

MongoDB RBAC có thể tách:

- Producer: `insert`, đọc tối thiểu.
- Reader: `find`.
- Aggregator: `find` và ghi rollup collection.
- Administrator: thay đổi index/retention theo approval.

Không cấp `update`/`remove` trên event archive cho mọi services. Tuy nhiên “append-only trong ứng dụng” **không tự trở thành WORM/immutable storage có chứng nhận pháp lý**; cần kiểm soát quyền admin, audit, backup và archive policy.

### 5.2. Correction không phải xóa event cũ

Một correction nên tham chiếu event gốc bằng `correctsEventId` hoặc `causationId`, và các projections phải biết áp dụng correction theo domain logic.

### 5.3. Không giữ secrets trong event payload

Không lưu access tokens, thẻ thanh toán thô, passwords hoặc sensitive headers trong event log. Giới hạn dữ liệu, mã hóa khi phù hợp và có chính sách xóa/anonymize nếu pháp luật yêu cầu.

## 6. Chọn một trong ba mô hình lưu trữ

| Mô hình | Tốt cho | Đánh đổi |
|---|---|---|
| Collection document thông thường | Domain events, audit, event sourcing, uniqueness, transactions | Nhiều documents/index entries |
| Time-series collection | Measurements dày đặc theo sensor/device và thời gian | Hạn chế unique indexes, writes trong transactions, updates |
| Bucket pattern tự quản | Gom events nhỏ theo entity/time bucket | Update bucket, kích thước document, concurrent writes |
| Archive object storage + index manifest | Lịch sử rất lâu, giá lưu trữ thấp | Truy vấn trực tiếp phức tạp, cần restore/replay |
| Summary/rollup collection | Dashboard/truy vấn tổng hợp nhanh | Có thể stale, phải reconcile |

### 6.1. Mô hình mặc định cho business event history

Nếu cần per-event unique ID, cập nhật state + outbox atomically, index theo aggregate và truy vấn đa dạng, **regular collection** thường là lựa chọn dễ kiểm soát.

### 6.2. Mô hình mặc định cho measurements

Nếu mỗi thiết bị gửi một điểm đo mỗi giây, payload nhỏ và chủ yếu aggregate theo thời gian, time-series collection là ứng viên tốt. Nhưng phải chấp nhận hạn chế về unique/index/transaction.

### 6.3. Tránh chọn theo tên “event”

Không phải cứ dữ liệu có timestamp là dùng time-series collection. Audit trail đòi kiểm soát uniqueness/transaction và giữ lâu có thể không hợp với giới hạn time-series.

## 7. Đọc/ghi sự kiện theo tập truy vấn trước

Giả sử ba nhu cầu:

1. Timeline cho một order trong một tenant.
2. Đếm tất cả `OrderCreated` theo giờ trong một khoảng ngày.
3. Báo cáo số tiền thu trong từng ngày theo tenant.

Để đáp ứng, cần ít nhất:

~~~text
tenantId
aggregateId
occurredAt
eventType
amount (nếu là sự kiện tiền)
~~~

### 7.1. Quy ước ordered timeline

Dùng `aggregateVersion` khi có sequence theo aggregate. Nếu không, sort theo `occurredAt` và tie-breaker stable như `_id`, nhưng không coi wall-clock đồng bộ hoàn hảo giữa producers.

### 7.2. Không tạo field trùng tùy tiện

Nếu `_id` đã là event ID có định danh duy nhất, field `eventId` lặp có thể chỉ phục vụ API/standardization. Quyết định và ghi rõ invariants.

## 8. Cấu hình collections trong mongosh lab

Dùng database riêng, không chạy các thao tác dưới đây trên production dữ liệu thật:

~~~javascript
use event_design_lab

db.createCollection("domain_events");
db.createCollection("daily_rollups");
db.createCollection("event_archive_manifest");
~~~

### 8.1. Unique constraint

Nếu collection **không sharded**, `_id` là unique theo collection:

~~~javascript
db.domain_events.createIndex(
  { tenantId: 1, eventId: 1 },
  { unique: true, name: "uq_tenant_event_id" }
);
~~~

Index này chống duplicate event ID trong một tenant, nếu mỗi event dùng cùng `tenantId` và `eventId`.

### 8.2. Timeline index

~~~javascript
db.domain_events.createIndex(
  { tenantId: 1, aggregateId: 1, occurredAt: 1, _id: 1 },
  { name: "ix_tenant_aggregate_time" }
);
~~~

Giúp lọc theo tenant+aggregate, duyệt theo thời gian và tie-breaker.

### 8.3. Reporting index

~~~javascript
db.domain_events.createIndex(
  { tenantId: 1, eventType: 1, occurredAt: 1 },
  { name: "ix_tenant_type_time" }
);
~~~

Không tạo quá nhiều indexes theo mọi permutation. Kiểm tra workload, selectivity và `explain("executionStats")` trước khi chốt.

### 8.4. Index tăng chi phí ghi

Mỗi event insert phải cập nhật tất cả indexes. Một collection vài trăm triệu events với nhiều secondary indexes có thể tăng storage, cache pressure và write latency đáng kể.

## 9. Dữ liệu lab nhất quán để tính được kết quả

Chạy **một lần trên collection mới**:

~~~javascript
db.domain_events.insertMany([
  {
    _id: "evt-a-001",
    tenantId: "tenant-A",
    eventId: "evt-a-001",
    aggregateId: "order-101",
    aggregateVersion: 1,
    eventType: "OrderCreated",
    occurredAt: ISODate("2026-11-10T08:00:00Z"),
    receivedAt: ISODate("2026-11-10T08:00:01Z"),
    amount: NumberDecimal("0.00"),
    schemaVersion: 1
  },
  {
    _id: "evt-a-002",
    tenantId: "tenant-A",
    eventId: "evt-a-002",
    aggregateId: "order-101",
    aggregateVersion: 2,
    eventType: "PaymentCaptured",
    occurredAt: ISODate("2026-11-10T08:10:00Z"),
    receivedAt: ISODate("2026-11-10T08:10:01Z"),
    amount: NumberDecimal("125.50"),
    schemaVersion: 1
  },
  {
    _id: "evt-a-003",
    tenantId: "tenant-A",
    eventId: "evt-a-003",
    aggregateId: "order-102",
    aggregateVersion: 1,
    eventType: "PaymentCaptured",
    occurredAt: ISODate("2026-11-10T11:30:00Z"),
    receivedAt: ISODate("2026-11-10T11:30:02Z"),
    amount: NumberDecimal("75.00"),
    schemaVersion: 1
  },
  {
    _id: "evt-a-004",
    tenantId: "tenant-A",
    eventId: "evt-a-004",
    aggregateId: "order-101",
    aggregateVersion: 3,
    eventType: "PaymentRefunded",
    occurredAt: ISODate("2026-11-11T09:00:00Z"),
    receivedAt: ISODate("2026-11-11T09:00:01Z"),
    amount: NumberDecimal("-20.00"),
    schemaVersion: 1
  },
  {
    _id: "evt-b-001",
    tenantId: "tenant-B",
    eventId: "evt-b-001",
    aggregateId: "order-201",
    aggregateVersion: 1,
    eventType: "PaymentCaptured",
    occurredAt: ISODate("2026-11-10T16:00:00Z"),
    receivedAt: ISODate("2026-11-10T16:00:01Z"),
    amount: NumberDecimal("400.00"),
    schemaVersion: 1
  },
  {
    _id: "evt-a-005",
    tenantId: "tenant-A",
    eventId: "evt-a-005",
    aggregateId: "order-103",
    aggregateVersion: 1,
    eventType: "PaymentCaptured",
    occurredAt: ISODate("2026-11-10T06:00:00Z"),
    receivedAt: ISODate("2026-11-12T12:00:00Z"),
    amount: NumberDecimal("10.00"),
    schemaVersion: 1
  }
]);
~~~

Dòng cuối là **late-arriving event**: xảy ra ngày 10 nhưng chỉ nhận ngày 12. Nó phải được tính vào báo cáo **ngày xảy ra** nếu báo cáo theo event time.

### 9.1. Dataset này không gắn TTL ngay

Tránh dùng eventTime cũ khi đang học tổng hợp rồi tự xóa dữ liệu bởi TTL. Phần TTL dùng collection lab riêng.

### 9.2. Test dữ liệu mẫu có thể chạy lại không?

`insertMany` với `_id` cố định sẽ báo duplicate key khi chạy lại. Đó là tín hiệu tốt về uniqueness, không phải lỗi cần xử lý bằng cách xóa tất cả dữ liệu thật.

## 10. Truy vấn timeline cho một aggregate

~~~javascript
db.domain_events.find(
  {
    tenantId: "tenant-A",
    aggregateId: "order-101"
  },
  {
    _id: 1,
    eventType: 1,
    aggregateVersion: 1,
    occurredAt: 1,
    amount: 1
  }
).sort({
  aggregateVersion: 1,
  _id: 1
});
~~~

Trong dataset, order-101 có `OrderCreated`, `PaymentCaptured` và `PaymentRefunded`.

### 10.1. Thứ tự theo aggregateVersion

Nếu producer quản lý sequence tăng một cách có kiểm soát, `aggregateVersion` đáng tin hơn chỉ sort timestamp để tái dựng aggregate.

### 10.2. Event replay đòi định nghĩa nghiệp vụ

Không phải chỉ sắp xếp sự kiện là đã tái dựng trạng thái. Cần projection logic:

~~~text
OrderCreated  -> status CREATED
PaymentCaptured -> payment status PAID
PaymentRefunded -> adjust paid amount
~~~

### 10.3. Event sourcing phải kiểm tra gaps

Nếu aggregate versions là 1, 2, 4, thiếu version 3 cần điều tra; không chỉ bỏ qua sự kiện bị thiếu.

## 11. Query theo thời gian: dùng half-open interval

Đối với báo cáo ngày 2026-11-10 UTC:

~~~javascript
const start = ISODate("2026-11-10T00:00:00.000Z");
const end = ISODate("2026-11-11T00:00:00.000Z");

db.domain_events.find({
  tenantId: "tenant-A",
  occurredAt: {
    $gte: start,
    $lt: end
  }
});
~~~

### 11.1. Vì sao không dùng 23:59:59?

MongoDB BSON Date có độ phân giải milliseconds. Dùng mốc cuối ngày như `23:59:59` dễ bỏ qua phần milliseconds cuối; half-open interval `[start, end)` tránh lỗi biên và thuận tiện chia buckets.

### 11.2. Không mix kiểu timestamp

BSON Date khác string ISO. Nếu một phần documents có `occurredAt` dạng string, query range và `$dateTrunc` có thể lỗi hoặc sort sai.

### 11.3. Event-time hay ingest-time?

| Báo cáo | Thường lọc theo |
|---|---|
| Doanh thu ngày khách thanh toán | `occurredAt` |
| Vận hành pipeline, ingestion backlog | `receivedAt` |
| Tối ưu retention sau khi nhận | `expiresAt` hoặc `receivedAt` |
| Audit về thời điểm hệ thống biết thông tin | `receivedAt` cùng source timestamp |

Một báo cáo có thể cần cả hai dimensions. Ghi rõ định nghĩa lên dashboard.

## 12. TTL trên collection thông thường

MongoDB TTL index cho phép xóa documents có Date field khi đến hạn. Ví dụ collection lab riêng:

~~~javascript
db.createCollection("transient_events");

db.transient_events.createIndex(
  { expiresAt: 1 },
  {
    expireAfterSeconds: 0,
    name: "ttl_expire_at"
  }
);
~~~

Khi `expireAfterSeconds:0`, documents với `expiresAt` là BSON Date sẽ đủ điều kiện xóa khi thời gian đã qua giá trị đó.

### 12.1. Ví dụ insert theo policy 7 ngày

~~~javascript
const now = new Date();
const sevenDaysMs = 7 * 24 * 60 * 60 * 1000;

db.transient_events.insertOne({
  _id: "temp-event-001",
  occurredAt: now,
  receivedAt: now,
  eventType: "NotificationSent",
  expiresAt: new Date(now.getTime() + sevenDaysMs)
});
~~~

Chính sách này tính từ **ingest**; nếu yêu cầu giữ 7 ngày từ lúc thực sự xảy ra, cần dùng `occurredAt` đúng định nghĩa, đồng thời xử lý late arrivals.

### 12.2. TTL field phải là Date

Nếu `expiresAt` là string hoặc missing, TTL không xóa document như kỳ vọng. Dùng schema validation/contract để yêu cầu trường Date.

### 12.3. TTL không áp dụng lên _id

TTL index phải là **single-field**; không tạo TTL compound index để “lọc thêm tenantId”, và không dùng TTL trên `_id`.

### 12.4. Index TTL cũng hỗ trợ query

TTL index là index thật; tuy nhiên không thay các indexes theo tenant/time/eventType của workload.

## 13. TTL là xóa nền, không phải đồng hồ chính xác

MongoDB TTL monitor chạy nền; một document vừa hết hạn không được bảo đảm bị xóa ngay.

~~~text
expiresAt reached
       |
       v
Eligible for deletion
       |
   TTL monitor
       |
       v
Deletion observed later
~~~

### 13.1. Độ trễ phụ thuộc tải

Việc xóa có thể chậm hơn khi collection lớn, quá nhiều expired documents hoặc server đang bận. TTL không thay thế cơ chế kiểm soát truy cập để chặn đọc dữ liệu đã hết hiệu lực.

### 13.2. Với replica set

TTL deletes do primary thực hiện và được replicated xuống secondaries. Nếu cluster không có primary/thiếu majority hoặc đang quá tải, đừng kỳ vọng TTL vẫn vận hành như lịch tuyệt đối.

### 13.3. TTL không phải chính sách pháp lý hoàn chỉnh

TTL tự động xóa data trong MongoDB collection, nhưng:

- Backups/snapshots có retention riêng.
- Archives/lake/object stores có bản sao riêng.
- Search indexes/caches có thể giữ bản sao.
- Legal hold có thể đòi giữ hoặc xóa theo quy trình đặc biệt.
- Dữ liệu có thể còn trong một khoảng sau expiration.

Cần data lifecycle governance và evidence đủ theo yêu cầu pháp lý, không coi TTL là bằng chứng xóa sạch mọi bản sao.

## 14. Tính thời hạn từ event time hay ingest time

Giả sử policy “giữ 30 ngày”.

| Cách tính | Ưu điểm | Rủi ro |
|---|---|---|
| `occurredAt + 30d` | Bám ngày nghiệp vụ | Late event có thể vừa ingest đã expired |
| `receivedAt + 30d` | Có đủ 30 ngày xử lý sau ingest | Lịch sử sự kiện được giữ lâu hơn tuổi nghiệp vụ |
| `expiresAt` theo retentionClass | Điều khiển từng event rõ | Phải đảm bảo field đúng và đồng bộ policy |
| Per-collection TTL | Đơn giản khi cùng policy | Khó phân nhóm retention khác nhau |
| Archive then delete | Giữ dữ liệu lâu ngoài hot DB | Có pipeline và correctness proof |

### 14.1. Late arrival

Event xảy ra cách đây 40 ngày nhưng được nhận hôm nay. Nếu TTL là 30 ngày từ occurredAt, document có thể bị xóa ngay sau ingest. Muốn phân tích late data, phải tính policy phù hợp.

### 14.2. RetentionClass và expiresAt

~~~javascript
{
  eventType: "LoginAttempt",
  retentionClass: "security-90d",
  receivedAt: ISODate("2026-11-14T00:00:00Z"),
  expiresAt: ISODate("2027-02-12T00:00:00Z")
}
~~~

Đây là minh họa policy; thời hạn thật theo security/privacy/legal requirements.

### 14.3. “Không có expiresAt” là một chính sách nguy hiểm nếu không kiểm soát

Một document thiếu field không bị TTL xóa. Nếu một producer lỗi schema, dữ liệu có thể bị giữ vô hạn. Dùng validator, monitoring cho `expiresAt: {$exists:false}` và quy trình exception.

## 15. Partial TTL, legal hold và phân loại dữ liệu

Với **regular collection**, một partial TTL index có thể áp một điều kiện lên tập documents, nếu đáp ứng phiên bản và yêu cầu index.

Ví dụ policy “chỉ xóa audit debug events”:

~~~javascript
db.transient_events.createIndex(
  { expiresAt: 1 },
  {
    name: "ttl_debug_only",
    expireAfterSeconds: 0,
    partialFilterExpression: {
      retentionClass: "debug"
    }
  }
);
~~~

**Lưu ý:** Đây là một ví dụ trên collection **khác hoặc index design thay thế**; không tạo nó cùng key specification với index TTL `ttl_expire_at` ở mục 12 trong một collection mà không kiểm tra index conflicts. Dùng một chính sách duy nhất hoặc tách collections/TTL fields có chủ đích.

### 15.1. Legal hold

Không cố giải quyết mọi legal hold bằng cách set `expiresAt` thật xa trong tương lai khi chưa có governance. Có thể:

- Tách held records vào collection/archive không áp TTL.
- Loại trừ bằng partial TTL với policy đúng.
- Tạo workflow hold/release có phê duyệt.
- Giữ audit record của quyết định hold.
- Đồng bộ backup/archive handling.

### 15.2. Partial TTL không làm xóa tức thì

Một document match filter và hết hạn vẫn đợi TTL monitor. Không dùng TTL làm điều kiện bảo mật cho việc chặn truy cập thời gian thực.

### 15.3. Lưu trữ theo loại sự kiện

Nếu audit 7 năm và telemetry 7 ngày, việc dùng chung một collection với TTL policy phức tạp có thể khó vận hành. Tách collections theo access pattern/retention thường đáng cân nhắc.

## 16. Thay đổi TTL policy cần change management

Trước khi đổi `expireAfterSeconds` từ 90 ngày xuống 7 ngày:

1. Ước lượng có bao nhiêu documents ngay lập tức đủ điều kiện xóa.
2. Đánh giá backup/archive và legal retention.
3. Kiểm tra disk/CPU/I/O và tác động replication của deletes.
4. Xem SLO và maintenance window.
5. Có approval và rollback plan thực tế.
6. Thay bằng `collMod` theo tài liệu/version phù hợp.
7. Quan sát TTL deletion lag và dataset còn lại.
8. Không giả định dữ liệu đã xóa có thể “rollback” bằng đổi TTL trở lại.

### 16.1. Không dùng createIndex để đổi TTL trên index cũ

MongoDB docs yêu cầu thay `expireAfterSeconds` của TTL index hiện có bằng `collMod` (theo phiên bản/tính năng phù hợp), không chỉ tạo lại cùng index với option khác.

### 16.2. Backup trước thay đổi phá dữ liệu

TTL expiration là dữ liệu bị xóa; nó không được rollback bằng cách tăng expiration sau khi documents đã biến mất. Nếu cần phục hồi phải có backup và reconciliation plan.

## 17. Time-series collection cho phép gom measurements

Đối với sensor readings, MongoDB có time-series collections lưu theo buckets ở mức engine.

~~~javascript
db.createCollection("device_measurements", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "minutes"
  },
  expireAfterSeconds: 2592000
});
~~~

`2592000` giây tương đương 30 ngày để minh họa. `measuredAt` là **measurement time**; `meta` chứa metadata tương đối ổn định của nguồn.

### 17.1. Ví dụ đo

~~~javascript
db.device_measurements.insertMany([
  {
    measuredAt: ISODate("2026-11-14T08:00:00Z"),
    meta: {
      tenantId: "tenant-A",
      deviceId: "device-7",
      region: "south"
    },
    temperatureC: 27.3,
    humidityPct: 65
  },
  {
    measuredAt: ISODate("2026-11-14T08:05:00Z"),
    meta: {
      tenantId: "tenant-A",
      deviceId: "device-7",
      region: "south"
    },
    temperatureC: 27.8,
    humidityPct: 64
  }
]);
~~~

### 17.2. MetaField nên ổn định

`meta` nên đại diện các thuộc tính định danh/cụm của chuỗi đo, ví dụ deviceId, tenantId, location/region. Thay metadata từng record tùy tiện có thể làm buckets phân mảnh, giảm hiệu quả lưu trữ.

### 17.3. Không cho mọi payload vào meta

Không đặt timestamp, request ID hoặc field biến động từng sự kiện vào meta nếu không phục vụ grouping. High cardinality và thay đổi liên tục có thể làm bucket compression kém hiệu quả.

## 18. Những giới hạn quan trọng của time-series

So với regular collection, time-series có semantics riêng theo MongoDB version:

- MongoDB không hỗ trợ **unique indexes** trên time-series collections.
- Không mặc định có `_id` index như regular collection.
- Không thể thực hiện **writes** vào time-series collections trong transactions.
- Updates/deletes bị giới hạn; không dùng như bảng mutable order state.
- Time-series measurements có giới hạn document size riêng (theo Manual hiện hành là 4 MB).
- Indexing và shard key patterns có hạn chế phụ thuộc release.
- TTL xử lý theo **bucket**, không phải “document xóa đúng mili-giây”.

### 18.1. Vấn đề idempotency

Nếu producer gửi cùng measurement hai lần với eventId giống nhau, time-series collection không cho phép unique index trên eventId. Bạn phải chấp nhận duplicate/dedup trong query hoặc dùng staging/dedup architecture khác.

### 18.2. Không thể giải quyết mọi thứ bằng transaction với side collection

Vì time-series writes không được hỗ trợ trong transactions, không thể tự tạo một MongoDB transaction gồm “insert unique event key vào regular collection” và “insert time-series measurement” rồi tuyên bố hai bước atomic.

Các phương án:

- Regular collection là source of truth có unique constraint, time-series là derived read model.
- At-least-once ingest rồi dedup trong downstream.
- Dùng message broker/event ID và pipeline có idempotency/reconciliation.
- Nếu uniqueness mạnh là bắt buộc, cân nhắc regular collection thay vì time-series.

### 18.3. Read side vẫn có khả năng aggregation

Time-series rất phù hợp các truy vấn theo meta/time và thống kê. Giới hạn write/unique không có nghĩa nó không query/aggregate tốt.

## 19. TTL của time-series được thực hiện theo bucket

Khi tạo time-series collection có `expireAfterSeconds`, MongoDB dùng `timeField` để tính expiration, nhưng **xóa bucket khi tất cả measurements trong bucket đã hết hạn**.

~~~text
Bucket B contains:
  08:00 measurement
  08:20 measurement
  08:55 measurement

TTL 30 days:
  08:00 đã hết hạn
  08:20 chưa hết hạn
  08:55 chưa hết hạn

=> Bucket B chưa bị xóa.
~~~

Ngay khi bucket đủ điều kiện, MongoDB vẫn dùng TTL background process, nên deletion không tức thì.

### 19.1. Granularity ảnh hưởng bucket coverage

Theo tài liệu time-series TTL, granularity `seconds`/`minutes`/`hours` quy định khoảng thời gian tối đa mà bucket có thể bao phủ. Bucket phủ dài thường tạo độ trễ xóa theo measurement time lớn hơn.

### 19.2. Partial TTL trên time-series

Từ MongoDB 7.0, có khả năng tạo partial TTL index dựa trên `metaField` để cho một nhóm measurements hết hạn **sớm hơn** collection-level TTL. Nếu collection có global `expireAfterSeconds`, partial TTL **không** làm nhóm đó sống lâu hơn TTL toàn collection.

### 19.3. Không áp một cú pháp TTL regular collection lên time-series tùy tiện

Hãy đọc tài liệu đúng server version. Time-series TTL/index policies có điều kiện khác regular collection; không giả định mọi partialFilterExpression được hỗ trợ.

### 19.4. Time-series for audit trail?

Nếu audit yêu cầu unique eventId, khả năng sửa sai bằng compensating record, retention phân lớp và transaction với domain state, một regular collection thường phù hợp hơn.

## 20. Sharding cho dữ liệu sự kiện

Dữ liệu events tăng liên tục có thể cần sharding. Nhưng shard key phải được chọn theo queries và write distribution.

Các lựa chọn thường đánh giá:

- `tenantId`: truy vấn thường trong một tenant; rủi ro tenant quá lớn.
- `tenantId + aggregateId`: cùng entity có locality; query theo time range rộng có thể scatter.
- `tenantId + occurredAt`: time-range routing theo tenant; rủi ro shard hotspot nếu monotonic.
- Hashed key giúp phân phối writes nhưng có đánh đổi range query và unique index.

### 20.1. Quy tắc unique index khi sharding

MongoDB sharded collection có ràng buộc **unique index shard-key-prefix**. Không phải mọi unique index từng hợp lệ trên unsharded collection đều tiếp tục được phép sau sharding.

Ví dụ với range shard key `{ tenantId: 1 }`, unique index `{ tenantId:1, eventId:1 }` phù hợp với quy tắc prefix trong các điều kiện khác.

### 20.2. Không giả định _id unique toàn cụm khi _id không là shard key

Trên sharded collection, nếu `_id` không là shard key, MongoDB có thể chỉ bảo đảm uniqueness `_id` trong từng shard; producer cần bảo đảm global IDs hoặc design key phù hợp.

### 20.3. Hashed unique có giới hạn

MongoDB không hỗ trợ unique hashed indexes. Nếu cần uniqueness mạnh theo `tenantId,eventId`, không chọn hashed shard key rồi suy luận có thể áp unique index không đổi.

### 20.4. Time-series sharding riêng

Time-series collections có giới hạn shard key theo `metaField` và `timeField`. MongoDB Manual hiện hành cảnh báo timeField-only shard key có thể tạo hotspot; timeField trong time-series shard key đã có deprecation từ MongoDB 8.0. Xem release documentation trước khi chốt.

## 21. Lưu trữ sự kiện lớn: phân lớp hot/warm/cold

Một chính sách mẫu:

~~~text
Event created
      |
      v
Hot MongoDB (0-30 days)
      |
      +--> near-real-time API
      +--> troubleshooting
      +--> dashboard short windows
      |
      v
Warm history (30-180 days)
      |
      +--> archive MongoDB / optimized storage
      +--> weekly/monthly reporting
      |
      v
Cold archive (>180 days)
      |
      +--> object storage / data lake
      +--> compliance/replay on demand
      |
      v
Final deletion per policy (subject to legal hold)
~~~

Các khoảng ngày là ví dụ, không phải MongoDB defaults hay khuyến nghị pháp lý.

### 21.1. Archive phải hoàn tất trước delete

~~~text
Select finalized range
     |
Export/upload with checksums
     |
Verify count, IDs, schemas, decrypt/restore
     |
Write immutable archive manifest
     |
Approve deletion of hot copy
     |
TTL/manual cleanup
~~~

Không bật TTL rồi mới bắt đầu archive nếu event có thể bị xóa trước khi export xong.

### 21.2. Archive manifest

~~~javascript
{
  _id: "archive-tenantA-2026-10",
  tenantId: "tenant-A",
  from: ISODate("2026-10-01T00:00:00Z"),
  toExclusive: ISODate("2026-11-01T00:00:00Z"),
  objectUri: "archive://approved-bucket/tenantA/2026-10",
  documentCount: NumberLong(1200345),
  checksum: "sha256-reference-value",
  schemaVersion: 3,
  verifiedAt: ISODate("2026-11-14T00:00:00Z"),
  status: "VERIFIED"
}
~~~

URI/checksum là placeholder; manifest cần chính sách quyền và chống sửa phù hợp.

### 21.3. Backup khác archive

Backup phục vụ khôi phục trạng thái hệ thống tại mốc thời gian; archive phục vụ giữ và truy vấn lịch sử dài hạn. TTL deletes vẫn được tái hiện theo replication/backup chronology, nhưng snapshots cũ có thể giữ events đã bị TTL xóa.

### 21.4. Restore test

Archive có ý nghĩa khi có thể giải mã, tải, kiểm tra schema/count/checksum và replay. Không đánh dấu `ARCHIVED` chỉ dựa vào việc upload job trả success.

## 22. Compliance, privacy và legal hold

Một event log có thể chứa personal data dù chỉ lưu IDs và timestamps, do khả năng liên kết.

Cần xác định:

- Data controller/owner.
- Purpose limitation và dữ liệu tối thiểu.
- Retention category và legal basis.
- Quy trình xóa/ẩn danh/hold.
- Access control và audit.
- Encryption at rest/in transit.
- Backup/archive retention.
- Region/residency requirements.
- Quy trình data subject requests.

### 22.1. Event-sourcing và quyền xóa dữ liệu có thể xung đột

Nếu event history là nguồn sự thật lâu dài nhưng chứa PII, chính sách xóa phải được thiết kế từ đầu: tham chiếu tokenized, tách PII side store, redaction policy, hoặc crypto-shredding khi pháp lý cho phép.

### 22.2. TTL không xóa search index hay cache

Một event hết TTL ở MongoDB nhưng bản sao trong Elasticsearch, data lake hoặc cache có thể còn. Cần propagate deletion theo policy.

### 22.3. Legal hold nên rõ trong retention model

Không lạm dụng `expiresAt:null` không được giám sát để thể hiện hold vô thời hạn. Đặt state/approval và các controls riêng, có khả năng chứng minh khi release hold.

## 23. MongoDB aggregation: đếm events theo loại

Đếm theo `tenantId` và `eventType`:

~~~javascript
db.domain_events.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      occurredAt: {
        $gte: ISODate("2026-11-10T00:00:00Z"),
        $lt: ISODate("2026-11-12T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$eventType",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1, _id: 1 } }
]);
~~~

Trong dataset: tenant-A có 3 `PaymentCaptured`, 1 `PaymentRefunded` và 1 `OrderCreated` (bao gồm late arrival đã được ingest).

### 23.1. $match nên ở đầu pipeline

Đặt filter tenant/time sớm để tận dụng index và giảm dữ liệu cho các blocking stages.

### 23.2. Quy tắc privacy multi-tenant

Không quên filter `tenantId` trên dashboard/request. Application authorization phải xác nhận tenant được phép trước query; database role trên collection không tự làm row-level tenant isolation.

## 24. $dateTrunc: gom theo giờ hoặc ngày

MongoDB 5.0+ cung cấp `$dateTrunc`:

~~~javascript
db.domain_events.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      eventType: "PaymentCaptured",
      occurredAt: {
        $gte: ISODate("2026-11-10T00:00:00Z"),
        $lt: ISODate("2026-11-11T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        bucketStart: {
          $dateTrunc: {
            date: "$occurredAt",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      events: { $sum: 1 },
      gross: { $sum: "$amount" }
    }
  },
  { $sort: { "_id.bucketStart": 1 } }
]);
~~~

Kết quả cho tenant-A ngày 10 UTC có buckets 06:00 (10.00), 08:00 (125.50), 11:00 (75.00). Dữ liệu `receivedAt` của event cuối là ngày 12, nhưng vì group theo `occurredAt` nên nó tính về ngày 10.

### 24.1. Lưu buckets bằng BSON Date

Không chuyển bucket thành string để group nếu còn cần sort/range/index Date. Format chuỗi tại API/presentation layer khi phù hợp.

### 24.2. binSize

~~~javascript
{
  $dateTrunc: {
    date: "$occurredAt",
    unit: "minute",
    binSize: 15,
    timezone: "UTC"
  }
}
~~~

Gom theo các khoảng 15 phút.

### 24.3. startOfWeek

Với weekly reporting, xác định tuần bắt đầu Monday hay Sunday theo nghiệp vụ bằng `startOfWeek` khi `unit:"week"`. Đừng để dashboard và batch job dùng quy ước khác nhau.

## 25. Timezone và Daylight Saving Time

MongoDB lưu BSON Date theo UTC milliseconds từ epoch. Nhưng một “ngày kinh doanh” có thể tính theo timezone của tenant.

Ví dụ:

~~~javascript
{
  $dateTrunc: {
    date: "$occurredAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

### 25.1. UTC bucket khác local calendar date

Một event lúc 2026-11-10 23:30Z thuộc ngày 11 ở Việt Nam (UTC+7). Nếu dashboard báo “ngày 10 theo Việt Nam”, query phải tính boundary UTC từ local midnight tương ứng, không chỉ dùng ngày UTC của timestamp.

### 25.2. DST

Với timezone có Daylight Saving Time, một ngày địa phương có thể dài 23 hoặc 25 giờ. `$dateTrunc` hiểu timezone rules; không cộng cố định 24 giờ để biểu diễn mọi local calendar day.

### 25.3. Timezone nên là policy field

Nếu mỗi tenant ở một múi giờ, dùng timezone identifier có kiểm soát, ví dụ `Asia/Ho_Chi_Minh`, chứ không lưu offset `+07:00` làm thay thế cho mọi timezone có DST.

### 25.4. Không trộn timezone group và timezone filter

Nếu group theo local day nhưng match theo UTC day, bạn có thể cắt mất events ở đầu/cuối ngày địa phương. Tính `startUtc` và `endUtc` từ requested local date.

## 26. Tổng hợp số tiền và sự kiện điều chỉnh

Nếu có `PaymentCaptured` (+) và `PaymentRefunded` (-), định nghĩa net cash amount:

~~~javascript
db.domain_events.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      eventType: {
        $in: ["PaymentCaptured", "PaymentRefunded"]
      },
      occurredAt: {
        $gte: ISODate("2026-11-10T00:00:00Z"),
        $lt: ISODate("2026-11-12T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        day: {
          $dateTrunc: {
            date: "$occurredAt",
            unit: "day",
            timezone: "UTC"
          }
        }
      },
      net: { $sum: "$amount" },
      eventCount: { $sum: 1 }
    }
  },
  { $sort: { "_id.day": 1 } }
]);
~~~

Kết quả mong đợi cho tenant-A:

- Ngày 10 UTC: 125.50 + 75.00 + 10.00 = **210.50**.
- Ngày 11 UTC: -20.00 = **-20.00**.

### 26.1. Không cộng mọi eventType

Nếu `OrderCreated` cũng có field `amount`, tổng mọi eventType có thể đếm lặp doanh thu. Định nghĩa danh sách events đóng góp tiền vào từng metric.

### 26.2. Refund không luôn là số âm

Một hệ thống có thể lưu `amount` của refund là số dương, sau đó cần `$cond` để đảo dấu theo eventType. Chọn convention nhất quán, kiểm thử trên dữ liệu thật và có versioning.

### 26.3. Multi-currency

Không cộng USD với VND thành một con số `net`. Group theo `currency` hoặc chuyển đổi bằng FX rate đã được xác định tại mốc nghiệp vụ, đồng thời lưu nguồn tỷ giá/rounding rules.

## 27. Cách nhóm thời gian thiếu dữ liệu và $densify

Nếu API biểu đồ cần 24 buckets mỗi giờ nhưng events chỉ xuất hiện lúc 06:00, 08:00, 11:00, kết quả aggregation thông thường **không** tự tạo buckets trống.

MongoDB 5.1+ hỗ trợ `$densify`:

~~~javascript
db.domain_events.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      eventType: "PaymentCaptured",
      occurredAt: {
        $gte: ISODate("2026-11-10T00:00:00Z"),
        $lt: ISODate("2026-11-11T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "hour",
          timezone: "UTC"
        }
      },
      total: { $sum: "$amount" }
    }
  },
  { $set: { hour: "$_id" } },
  { $project: { _id: 0, hour: 1, total: 1 } },
  {
    $densify: {
      field: "hour",
      range: {
        step: 1,
        unit: "hour",
        bounds: [
          ISODate("2026-11-10T00:00:00Z"),
          ISODate("2026-11-11T00:00:00Z")
        ]
      }
    }
  },
  {
    $set: {
      total: { $ifNull: ["$total", NumberDecimal("0")] }
    }
  },
  { $sort: { hour: 1 } }
]);
~~~

### 27.1. Chú ý semantic của bounds

`$densify` tạo missing documents trong khoảng bounds cho phép; thử edge cases ở đầu/cuối ngày, version MongoDB và loại inclusive/exclusive của bounds trước khi đưa vào production API.

### 27.2. Không tạo hàng triệu buckets vô tình

Nếu `$densify` chạy trên khoảng 10 năm với step 1 giây, số records phát sinh khổng lồ. Giới hạn query window, step, partitions và output size.

### 27.3. Zero khác missing

Báo cáo giao dịch có thể coi không có events là 0. Nhưng với sensor telemetry, missing measurement khác giá trị nhiệt độ 0°C. Đừng fill 0 theo mặc định cho mọi metric.

## 28. $fill và dữ liệu telemetry bị đứt quãng

MongoDB 5.3+ có `$fill`, gồm methods như `locf` (last observation carried forward) và `linear` trong điều kiện phù hợp.

Ví dụ cho một chuỗi đã được densify:

~~~javascript
{
  $fill: {
    sortBy: { measuredAt: 1 },
    output: {
      temperatureC: {
        method: "locf"
      }
    }
  }
}
~~~

### 28.1. Không dùng LOCF cho sự kiện tiền tệ

Nhiệt độ trước đó có thể dùng làm approximation theo chính sách; nhưng “không có giao dịch” không đồng nghĩa mang số tiền của giờ trước sang giờ sau.

### 28.2. Linear interpolation có giới hạn

Không nội suy dữ liệu lỗi/hết hạn thành số liệu “thật” nếu sản phẩm cần phân biệt measured vs estimated. Nếu nội suy, thêm metadata `isEstimated` và cách tính.

### 28.3. Người dùng cần biết metric origin

Bảng kết quả nên phân biệt raw observation, rollup, imputed value và correction.

## 29. $setWindowFields: running total và moving average

MongoDB 5.0+ hỗ trợ window functions.

Ví dụ tính running total trên **rollup ngày**:

~~~javascript
db.daily_rollups.aggregate([
  { $match: { tenantId: "tenant-A", metric: "net-payments" } },
  {
    $setWindowFields: {
      partitionBy: "$tenantId",
      sortBy: { bucketStart: 1 },
      output: {
        cumulativeNet: {
          $sum: "$net",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $project: {
      tenantId: 1,
      bucketStart: 1,
      net: 1,
      cumulativeNet: 1
    }
  }
]);
~~~

### 29.1. Partition theo tenant và metric

Nếu không partition, dữ liệu nhiều tenants có thể bị cộng chung. Nếu collection chứa nhiều metrics/currencies, partition/filter đầy đủ.

### 29.2. SortBy không bảo đảm final output ordering

Theo docs, `$setWindowFields` không đảm bảo thứ tự cuối cùng. Nếu API yêu cầu sorted results, thêm `$sort` cuối pipeline.

### 29.3. Moving average trên measurement

Có thể dùng `$avg` với `documents:[-2,0]` để tính trung bình ba điểm đo gần nhất. Đó là **3 observations**, không nhất thiết là 3 phút khi data có gaps.

## 30. Phân biệt raw aggregation và materialized rollup

| Cách | Độ mới | Chi phí query | Chi phí ghi/bảo trì |
|---|---|---|---|
| Query raw events | Gần real-time | Tăng theo số events trong window | Ít infrastructure hơn |
| Query precomputed daily rollup | Có độ trễ | Thường nhỏ | Cần rollup jobs |
| Incremental rollup qua Change Streams | Gần real-time | Nhỏ | Checkpoint/idempotency và replay |
| Offline warehouse analytics | Chậm hơn | Tối ưu báo cáo dài hạn | ETL và synchronization |
| Mixed hot + archive query | Tùy | Phức tạp | Phải merge data sources |

### 30.1. Khi nào rollup có giá trị?

Nếu mỗi dashboard mở 20 lần/phút và quét 100 triệu events, precomputed hourly/daily rollups thường hiệu quả hơn.

### 30.2. Raw data vẫn là nguồn đối soát

Khi có thay đổi business rule hoặc late events, phải có khả năng tính lại rollup từ nguồn đáng tin cậy trong retention/archive window.

### 30.3. Định nghĩa metric phải version hóa

`net-payments-v1` và `net-payments-v2` có thể có quy tắc refunds khác nhau. Không âm thầm ghi đè historical metrics mà không có migration và thông báo cho downstream.

## 31. Batch rollup theo ngày bằng $merge

MongoDB aggregation có `$merge` để upsert kết quả vào collection vật lý.

Ví dụ **tính lại** bucket của ngày 10 UTC cho tenant-A:

~~~javascript
db.domain_events.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      eventType: {
        $in: ["PaymentCaptured", "PaymentRefunded"]
      },
      occurredAt: {
        $gte: ISODate("2026-11-10T00:00:00Z"),
        $lt: ISODate("2026-11-11T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        bucketStart: {
          $dateTrunc: {
            date: "$occurredAt",
            unit: "day",
            timezone: "UTC"
          }
        }
      },
      net: { $sum: "$amount" },
      eventCount: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: {
        $concat: [
          "$_id.tenantId",
          ":net-payments:",
          {
            $dateToString: {
              date: "$_id.bucketStart",
              format: "%Y-%m-%d",
              timezone: "UTC"
            }
          }
        ]
      },
      tenantId: "$_id.tenantId",
      metric: { $literal: "net-payments" },
      bucketStart: "$_id.bucketStart",
      net: 1,
      eventCount: 1
    }
  },
  {
    $merge: {
      into: "daily_rollups",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]);
~~~

### 31.1. Vì sao whenMatched: replace?

Nếu tính lại cả bucket từ raw events, ta muốn thay kết quả cũ bằng tổng mới, **không cộng chồng lần chạy trước**. Điều này giúp rerun idempotent đối với tập dữ liệu nguồn và metric definition không đổi.

### 31.2. Nếu không có events thì sao?

Một pipeline `$group` không tạo output cho bucket rỗng. `$merge` vì vậy **không tự xóa rollup cũ** khi toàn bộ nguồn của bucket bị remove/corrected. Cần explicit reconciliation/deletion policy cho empty buckets.

### 31.3. Không cộng incremental một cách mù quáng

`$merge` with `whenMatched:"merge"` hoặc cập nhật `$inc` có thể double count nếu job retry/replay. Nếu dùng incremental updates, cần per-event dedup/atomic checkpoint.

### 31.4. Sharded target

Khi `daily_rollups` sharded, `$merge` có các yêu cầu về unique index/on-fields/shard key theo version. Đọc trang `$merge` và kiểm tra target index trước khi deploy.

## 32. Late-arriving events làm thay đổi rollup quá khứ

Ví dụ event `evt-a-005` xảy ra ngày 10 nhưng tới ngày 12. Nếu rollup ngày 10 chạy ngày 11, kết quả cũ là:

~~~text
PaymentCaptured: 125.50 + 75.00 = 200.50
~~~

Sau khi nhận late event 10.00, kết quả đúng:

~~~text
PaymentCaptured: 210.50
~~~

### 32.1. Cách xử lý

- Dùng rolling re-computation window, ví dụ tính lại 7 ngày gần nhất.
- Dùng watermark theo `receivedAt` và đánh dấu các event-time buckets bị ảnh hưởng.
- Dùng correction queue chứa các bucket keys cần tính lại.
- Với late data cực cũ, truy vấn từ archive và tạo restatement có audit.

### 32.2. Watermark không phải “đồng hồ hiện tại”

Nếu hệ thống đợi event đến tối đa 48 giờ, một bucket chỉ “final” khi watermark theo dữ liệu đủ mức. Cần định nghĩa lateness SLA và khi nào vẫn cho phép correction.

### 32.3. Báo cáo đã công bố cần restatement semantics

Một báo cáo tài chính đã khóa sổ không nên tự thay số cũ mà không có dấu vết. Lưu report version, correction event, approval và thời điểm phát hành lại theo nghiệp vụ.

## 33. Change Streams cho rollup gần real-time

Nếu cần cập nhật nhanh, có thể dùng Change Streams để theo dõi inserts vào regular event collection:

~~~text
Domain event inserted
       |
       v
MongoDB Change Stream
       |
       v
Consumer processor
       |
       +--> update rollup/projection
       |
       +--> persist resume token/checkpoint
~~~

### 33.1. Không mặc định exactly-once

Consumer có thể xử lý một event rồi chết trước khi lưu token; sau restart, event được phát lại. Nếu consumer cộng `$inc` thêm một lần, rollup bị double count.

### 33.2. Idempotency

Các lựa chọn:

- Unique processed-event key trong collection riêng.
- Atomic transaction ghi projection và checkpoint khi cả hai ở regular MongoDB collections.
- Recompute bucket từ raw events khi nhận tín hiệu thay đổi.
- Version-based upsert.

### 33.3. Change Stream token không sống mãi

Resume token phụ thuộc oplog history. Nếu downtime vượt oplog window, worker cần rebootstrap/reconciliation, không chỉ gọi `resumeAfter` mãi.

### 33.4. Time-series đặc biệt

Time-series changes/events và write transaction constraints khác regular collection. Không tự giả định có thể áp y nguyên atomic write+checkpoint pattern vào time-series; kiểm tra server version và xây derived materialization phù hợp.

## 34. Outbox khi event là kết quả giao dịch nghiệp vụ

Giả sử một use case cập nhật `orders` và phát `OrderPaid`. Việc ghi event vào MongoDB regular collection cùng transaction có thể bảo đảm atomic intent:

~~~text
@Transactional:
  update orders.order-101
  insert domain_events (OrderPaid)
  insert outbox (publish intent)

Commit MongoDB

Async publisher:
  read outbox
  send broker
  mark delivered idempotently
~~~

### 34.1. Domain event không tự phát ra Kafka

MongoDB transaction không rollback một HTTP call hoặc broker publish ngoài MongoDB. Dùng outbox và at-least-once delivery với consumer idempotency.

### 34.2. Không giữ MongoDB transaction qua network I/O

Nếu gọi payment gateway bên trong transaction rồi commit fail, hệ thống có side effect ngoài DB. Thiết kế saga/compensation nếu workflow trải nhiều dịch vụ.

### 34.3. Time-series không nhận writes trong transaction

Nếu cần atomic commit state+event, lưu domain event ở regular collection trước; có thể tạo time-series projection/metrics downstream.

## 35. Compression, storage và bucket pattern tự quản

Nếu mỗi event rất nhỏ, lượng document/index overhead có thể đáng kể. Có thể thử bucket pattern:

~~~javascript
{
  _id: "device-7:2026-11-14T08",
  tenantId: "tenant-A",
  deviceId: "device-7",
  hourStart: ISODate("2026-11-14T08:00:00Z"),
  entries: [
    { second: 0, value: 27.3 },
    { second: 300, value: 27.8 }
  ]
}
~~~

### 35.1. Ưu điểm

Giảm số documents cho rất nhiều measurements nhỏ, thuận lợi fetch một khoảng thời gian cho một device.

### 35.2. Nhược điểm

- Hot bucket bị concurrent updates.
- Array có thể lớn tới document size limit.
- Khó dedup mỗi entry.
- TTL xóa nguyên bucket, không phải từng event.
- Index theo nested events khó hơn.
- Thêm validation/compaction code.

### 35.3. Time-series bucket tự động thường tốt hơn khi phù hợp

MongoDB time-series đã tối ưu bucket storage. Chỉ tự xây bucket pattern khi có yêu cầu đặc thù mà time-series không đáp ứng, và benchmark trade-offs.

## 36. Hiệu năng aggregation: giải thích query plan

Ví dụ:

~~~javascript
db.domain_events.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      eventType: "PaymentCaptured",
      occurredAt: {
        $gte: ISODate("2026-11-10T00:00:00Z"),
        $lt: ISODate("2026-11-11T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$tenantId",
      count: { $sum: 1 }
    }
  }
]);
~~~

### 36.1. Tín hiệu cần đọc

- Có index phù hợp với filter không?
- `totalDocsExamined`, `totalKeysExamined`.
- Bao nhiêu input documents vào `$group`?
- Có blocking sort không?
- Có spill ra disk không?
- Mức p95/p99 thực tế với workload production.
- Có scatter-gather do shard key thiếu không?

### 36.2. Không tối ưu từ dataset quá nhỏ

Với sáu event lab, planner chọn collection scan có thể vẫn hợp lý. Benchmark với data volume/cardinality đại diện.

### 36.3. Query shape phải ổn định

Không log nguyên dynamic event payload làm metric labels; log query shape, collection, tenant group đã ẩn danh và durations.

## 37. Memory limits, disk spill và output BSON size

Một pipeline có `$group`/`$sort` trên hàng chục triệu events có thể tiêu tốn RAM. MongoDB có các giới hạn memory cho blocking stages, và hỗ trợ spill tùy stage/version/config.

Ví dụ:

~~~javascript
db.domain_events.aggregate(
  [
    { $match: { tenantId: "tenant-A" } },
    {
      $group: {
        _id: "$eventType",
        count: { $sum: 1 }
      }
    }
  ],
  { allowDiskUse: true }
);
~~~

### 37.1. allowDiskUse không làm query vô hạn rẻ

Spill ra disk tốn I/O, có thể ảnh hưởng các workloads khác. Trước hết hãy giới hạn thời gian, giảm cardinality, tạo index hợp lý hoặc dùng rollup.

### 37.2. Output document size

BSON document size thường giới hạn 16 MiB cho regular collections/results. Đừng group toàn bộ events bằng `$push:"$$ROOT"` vào một mảng khổng lồ rồi mong trả về trong một document.

### 37.3. Cursor và pagination

Aggregate results có thể rất lớn; dùng cursor batch size, pagination theo time/key hoặc rollup. Không lấy toàn bộ data nhiều tháng vào JVM memory rồi group nếu MongoDB làm tốt hơn.

## 38. Quy tắc index cho một dashboard

Giả sử dashboard có query:

~~~javascript
{
  tenantId: "tenant-A",
  eventType: "PaymentCaptured",
  occurredAt: {
    $gte: start,
    $lt: end
  }
}
~~~

Index phù hợp thường là:

~~~javascript
{
  tenantId: 1,
  eventType: 1,
  occurredAt: 1
}
~~~

### 38.1. Equality trước, range sau

Khi filter equality trên tenantId/eventType rồi range theo occurredAt, compound index này thường thuận lợi. Nhưng workload thực tế, selectivity, collation và sort requirements có thể làm phương án khác tốt hơn.

### 38.2. Timeline có query khác

Timeline theo `tenantId + aggregateId` và sort by time nên dùng index riêng, không ép mọi loại queries dùng một index duy nhất.

### 38.3. Hot write paths

Đừng thêm một index mới chỉ để một admin dashboard hiếm khi chạy nhanh hơn nếu nó làm tất cả writes chậm. Có thể dùng rollup hoặc archive query.

### 38.4. Index theo ngày string?

Đừng chỉ lưu `dateKey:"2026-11-10"` và bỏ Date gốc. Date key có thể hữu ích cho rollup, nhưng timezone/policy thay đổi sẽ làm key cũ không còn đủ nghĩa.

## 39. Java Sync Driver: insert idempotent event

Ví dụ Java 17+ với MongoDB Java Sync Driver:

~~~java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.types.Decimal128;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Date;

public final class EventWriter {

    private final MongoCollection<Document> events;

    public EventWriter(MongoCollection<Document> events) {
        this.events = events;
    }

    public void recordPayment(String tenantId, String eventId,
                              String orderId, BigDecimal amount) {

        Document event = new Document("_id", eventId)
            .append("tenantId", tenantId)
            .append("eventId", eventId)
            .append("aggregateId", orderId)
            .append("aggregateVersion", 1L)
            .append("eventType", "PaymentCaptured")
            .append("schemaVersion", 1)
            .append("occurredAt", Date.from(Instant.now()))
            .append("receivedAt", new Date())
            .append("amount", new Decimal128(amount));

        try {
            events.insertOne(event);
        } catch (MongoWriteException ex) {
            if (ex.getError().getCode() == 11000) {
                // Duplicate ID: cần reconcile payload/business invariant.
                // Không được tự kết luận mọi duplicate đều là thành công.
                return;
            }
            throw ex;
        }
    }
}
~~~

### 39.1. Duplicate key cần kiểm tra payload

Nếu cùng eventId đến với payload khác, đây có thể là data-integrity incident chứ không phải idempotent retry hợp lệ. So event hash/version/tenant và báo lỗi nếu nội dung xung đột.

### 39.2. Global IDs trong sharded deployment

Ví dụ `_id=eventId` giả định eventId unique do producer kiểm soát. Khi sharding theo tenant khác `_id`, phải xét MongoDB `_id` uniqueness locality. Tạo schema/unique index phù hợp với shard-key-prefix, hoặc dùng cơ chế uniqueness ngoài sharded collection.

### 39.3. Timestamp từ JVM clock

`Instant.now()` phụ thuộc clock của server ứng dụng. Nếu event time quan trọng, kiểm soát clock sync và nguồn thời gian (business source vs ingest server). Không dùng ObjectId timestamp làm thay thế cho mọi nghiệp vụ.

## 40. Java Driver: query history theo time range

~~~java
import static com.mongodb.client.model.Filters.*;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

import java.time.Instant;
import java.util.Date;

public final class EventHistoryReader {

    private final MongoCollection<Document> events;

    public EventHistoryReader(MongoCollection<Document> events) {
        this.events = events;
    }

    public void printTimeline(String tenantId,
                              String aggregateId,
                              Instant start,
                              Instant end) {

        events.find(and(
                eq("tenantId", tenantId),
                eq("aggregateId", aggregateId),
                gte("occurredAt", Date.from(start)),
                lt("occurredAt", Date.from(end))
            ))
            .sort(Sorts.ascending("occurredAt", "_id"))
            .limit(100)
            .forEach(doc -> {
                System.out.println(
                    doc.getString("eventType") + " " +
                    doc.getDate("occurredAt"));
            });
    }
}
~~~

### 40.1. Pagination

`limit(100)` một mình không cho phân trang ổn định. Với timeline dài, dùng cursor keyset dựa trên `occurredAt` + `_id`, tính predicate cho trang sau và giữ sort/index nhất quán.

### 40.2. Không log full event payload

Thông tin eventType/time là ví dụ lab. Production cần redaction và tenancy guard; đừng in customer data lên stdout chỉ để debug.

## 41. Java Driver: aggregate theo ngày

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Accumulators;
import com.mongodb.client.model.Filters;
import org.bson.Document;

import java.time.Instant;
import java.util.Arrays;
import java.util.Date;

public class DailyEventCounter {

    public void report(MongoCollection<Document> events,
                       String tenantId,
                       Instant from,
                       Instant toExclusive) {

        events.aggregate(Arrays.asList(
            Aggregates.match(Filters.and(
                Filters.eq("tenantId", tenantId),
                Filters.gte("occurredAt", Date.from(from)),
                Filters.lt("occurredAt", Date.from(toExclusive))
            )),
            new Document("$set", new Document("day",
                new Document("$dateTrunc", new Document("date", "$occurredAt")
                    .append("unit", "day")
                    .append("timezone", "UTC")))),
            Aggregates.group("$day", Accumulators.sum("count", 1)),
            Aggregates.sort(new Document("_id", 1))
        )).forEach(System.out::println);
    }
}
~~~

### 41.1. Schema version và null guards

Nếu một event thiếu occurredAt hoặc có sai type, dateTrunc có thể trả null/lỗi. Dùng schema validation và data quality checks ở ingestion, không chỉ filter bỏ dữ liệu sai rồi tuyên bố số liệu hoàn chỉnh.

### 41.2. Thống nhất version dependencies

Driver builder API/aggregation support theo dependency của ứng dụng. Dùng MongoDB Java Driver version do Spring Boot BOM quản lý nếu tích hợp Spring; kiểm tra tương thích với MongoDB server/operator versions.

## 42. Spring Data MongoDB: event entity

Ví dụ:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.index.CompoundIndexes;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("domain_events")
@CompoundIndexes({
    @CompoundIndex(
        name = "ix_tenant_aggregate_time",
        def = "{'tenantId':1, 'aggregateId':1, 'occurredAt':1, '_id':1}"
    ),
    @CompoundIndex(
        name = "ix_tenant_type_time",
        def = "{'tenantId':1, 'eventType':1, 'occurredAt':1}"
    )
})
public class DomainEvent {

    @Id
    private String id;

    private String tenantId;
    private String aggregateId;
    private long aggregateVersion;
    private String eventType;
    private int schemaVersion;
    private Instant occurredAt;
    private Instant receivedAt;

    protected DomainEvent() {
    }

    // Constructor/getters và payload mapping theo nghiệp vụ.
}
~~~

### 42.1. Index annotation không là migration plan

Trong production, không mặc định bật auto-index creation mà không kiểm tra thời gian xây index, unique violations và write impact. Có thể quản indexes qua migration pipeline riêng.

### 42.2. Mapping timestamps

Spring Data Java Time types có converters sang BSON Date. Đảm bảo thống nhất UTC/timezone logic; một Instant không mang timezone địa phương như ZonedDateTime.

### 42.3. Repository không giải quyết mọi aggregation

`MongoRepository` phù hợp CRUD/query đơn giản. Với pipelines phức tạp hoặc rollup, dùng `MongoTemplate.aggregate`, Aggregation builders, hoặc driver API có kiểm thử.

## 43. Spring Data MongoDB: aggregate bằng MongoTemplate

Ví dụ Spring Data code:

~~~java
import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;
import org.bson.Document;

import java.time.Instant;
import java.util.Date;

public class EventReportService {

    private final MongoTemplate template;

    public EventReportService(MongoTemplate template) {
        this.template = template;
    }

    public AggregationResults<Document> countByType(
            String tenantId, Instant from, Instant to) {

        Aggregation pipeline = newAggregation(
            match(Criteria.where("tenantId").is(tenantId)
                .and("occurredAt").gte(Date.from(from))
                .lt(Date.from(to))),
            group("eventType").count().as("eventCount"),
            sort(org.springframework.data.domain.Sort.Direction.DESC,
                "eventCount")
        );

        return template.aggregate(
            pipeline, "domain_events", Document.class
        );
    }
}
~~~

### 43.1. Không bỏ qua tenant authorization

Template không tự kiểm tra user thuộc tenant nào. Service phải authorize tenantId hoặc lấy tenant context từ authenticated principal thay vì tin nguyên request param.

### 43.2. Spring Boot config prefix

Spring Boot 3.5 dùng `spring.data.mongodb.uri`. Spring Boot 4.x dùng `spring.mongodb.uri` theo tài liệu tương ứng. Một app kết nối nhầm cluster không nên được sửa bằng cách đổi dữ liệu report.

## 44. Event schema validation

MongoDB có `$jsonSchema` validators để chặn documents sai cấu trúc trong collection regular.

Ví dụ yêu cầu minimal fields:

~~~javascript
db.runCommand({
  collMod: "domain_events",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "tenantId",
        "eventId",
        "eventType",
        "occurredAt",
        "receivedAt",
        "schemaVersion"
      ],
      properties: {
        tenantId: { bsonType: "string" },
        eventId: { bsonType: "string" },
        eventType: { bsonType: "string" },
        occurredAt: { bsonType: "date" },
        receivedAt: { bsonType: "date" },
        schemaVersion: {
          bsonType: "int",
          minimum: 1
        }
      }
    }
  },
  validationAction: "error"
});
~~~

Đây là thao tác thay validator **chỉ cho lab đã chuẩn bị**. Trong production cần migration review và dữ liệu legacy phải tương thích trước khi `collMod`.

### 44.1. Kiểu Numeric version

`schemaVersion` có thể dùng int hoặc long nhưng contract phải thống nhất. Validator trên yêu cầu int.

### 44.2. Conditional fields

Nếu `PaymentCaptured` bắt buộc amount/currency nhưng `OrderCreated` không, cần conditional validation/schema registry/application checks, hoặc tách event types/collections phù hợp.

### 44.3. Schema validation không thay security

Validator không ngăn authorized admin xóa documents hay ngăn sensitive data nằm trong arbitrary payload field nếu schema cho phép. Cần RBAC và dữ liệu tối thiểu.

## 45. Đo và kiểm soát event ingestion

Các tín hiệu hữu ích:

~~~text
events_ingested_total{eventType}
events_rejected_total{reason}
events_duplicate_total
events_schema_invalid_total
events_late_arrivals_total
events_ingestion_lag_seconds
events_write_latency_seconds
events_rollup_lag_seconds
events_archive_backlog
events_retention_backlog
events_size_bytes
events_ttl_deleted_total
~~~

Các tên là **custom application metrics** minh họa; không mặc định có trong MongoDB.

### 45.1. Tính độ trễ ingest

~~~text
ingestion lag = receivedAt - occurredAt
~~~

Nếu nguồn clock không đồng bộ, kết quả có thể âm; cần validate clocks và quality flags.

### 45.2. TTL monitor metrics

MongoDB `serverStatus` có counters dưới `metrics.ttl` theo version, chẳng hạn deletedDocuments/passes/subPasses. Theo dõi rates, backlog, storage và expiration distribution; counters reset sau process restart.

### 45.3. Dấu hiệu aggregation regressions

Theo dõi query duration, documents examined, scan/return ratio, disk spill, cache/disk I/O, index usage và p95/p99 dashboards.

### 45.4. High cardinality metrics

Không dùng `eventId`, `tenantId` ngẫu nhiên hoặc `aggregateId` làm Prometheus label cho mọi event. Số lượng unique time series metrics có thể bùng nổ.

## 46. Kiểm chứng retention mà không cần đợi TTL xóa ngay

Trong lab:

~~~javascript
const now = new Date();

db.transient_events.countDocuments({
  expiresAt: {
    $lte: now
  }
});
~~~

Con số này đo **documents hiện đã đến hạn nhưng còn tồn tại**, không chứng minh TTL monitor đang hỏng. Cần so với monitor activity, workload và khoảng chờ.

### 46.1. Test TTL có giới hạn thời gian hợp lý

Không assert “document hết hạn phải biến mất trong 50 milliseconds”. Dùng wait-until với deadline có thể cấu hình và report lag thực tế.

### 46.2. Test time-series TTL khác

Với time-series buckets, một measurement cũ có thể còn cho đến khi **cả bucket** đủ điều kiện. Kiểm thử phải xét bucket span và granularity, không chỉ từng measurement timestamp.

### 46.3. Test thay policy

Nếu giảm retention khiến hàng triệu documents đến hạn, test resource impact/staging trước; không chạy production experiment phá dữ liệu.

## 47. Data correctness: backfill, replay và dedup

Một hệ thống event analytics muốn đáng tin phải xử lý:

| Hiện tượng | Tác động | Giải pháp |
|---|---|---|
| Producer retry | Duplicate event | Stable eventId + unique key/dedup |
| Network partition | Late arrival | Event time + ingest time |
| Out-of-order delivery | Projection sai | Aggregate version/ordering |
| Business correction | Báo cáo cũ sai | Correction event + recompute |
| Consumer crash | Event replay | Idempotent processor |
| Oplog history loss | Gap của stream | Rebootstrap/reconciliation |
| Schema v1/v2 | Parse/metric drift | Schema version/upcaster |
| Clock skew | Sai time bucket | Time sync và quality flag |
| TTL sớm hơn archive | Mất lịch sử | Archive-first workflow |
| Legal hold | Xung đột xóa | Governed hold store/policy |
| Multi-currency | Tổng tiền vô nghĩa | Group currency/FX policy |

### 47.1. Immutable events nhưng projections có thể cập nhật

Raw event append-only, còn `daily_rollups` là derived state nên có thể `replace` khi recompute. Không nhầm update rollup với sửa lịch sử raw.

### 47.2. Replay có thể tạo side effect

Re-run aggregator từ raw events là an toàn khi ghi kết quả deterministically. Re-run event consumer gửi email/SMS/charge card thì cần idempotency hoặc disable external effects trong replay mode.

## 48. Test plan cho thiết kế sự kiện

| Test | Input | Assertion |
|---|---|---|
| Insert event mới | Event ID hợp lệ | Một document |
| Duplicate event | Same eventId/payload | Không nhân đôi |
| Conflicting duplicate | Same ID, khác payload | Incident/conflict |
| Timeline | Event versions 1,2,3 | Sorted, không gap |
| Half-open range | Time đúng boundary | Không trùng bucket |
| Late event | occurredAt cũ, receivedAt mới | Tính đúng bucket cũ |
| Mixed currency | USD/VND | Không cộng bừa |
| Refund | Negative adjustment | Net đúng |
| Timezone | Local midnight | Correct UTC interval |
| DST | 23h/25h day | Calendar buckets đúng |
| TTL Date | expiresAt BSON Date | Eventual deletion |
| TTL string | expiresAt string | Validation rejects |
| Time-series TTL | Một số bucket còn valid | Chỉ xóa khi bucket eligible |
| Rollup rerun | Chạy job hai lần | Không double count |
| Rollup late correction | Event vào sau | Kết quả restated |
| Archive verify | Export + checksum | Count/invariants pass |
| Legal hold | Held record | Không bị workflow xóa |
| Sharded uniqueness | Shard-key prefix | Constraint đúng |
| Query performance | Production-scale samples | p95 và scan ratio trong ngưỡng |
| History loss | Change Stream token old | Reconcile, không báo caught-up |

### 48.1. Testcontainers và environment

Dùng replica set nếu muốn kiểm thử transactions/change streams. Time-series features/TTL/aggregation cần MongoDB Server version tương thích và container image được pin rõ.

### 48.2. Không dùng production dữ liệu thật

Tạo test tenant, generated event IDs và dataset không chứa PII. Fault injection/TTL retention changes chỉ dùng lab được phép.

## 49. Anti-patterns phổ biến

| Sai lầm | Tại sao sai | Thay bằng |
|---|---|---|
| Ghi đè event cũ | Mất lịch sử | Append correction |
| Dùng Change Streams làm archive | Oplog hữu hạn | Regular event store/archive |
| Chỉ lưu timestamp string | Query/timezone khó | BSON Date |
| Chỉ lưu receivedAt | Không phân biệt late data | occurredAt + receivedAt |
| Chọn TTL từ occurredAt không kiểm tra late arrivals | Event backfill bị xóa ngay | Retention policy rõ |
| Tin TTL xóa ngay | Background monitor | Chấp nhận eventual cleanup |
| TTL index compound | Không được hỗ trợ | Single Date-field TTL |
| Dùng time-series cho unique event ledger | Unique index unsupported | Regular collection |
| Ghi time-series trong transaction | Không hỗ trợ | Regular source-of-truth |
| Nhét eventId thay đổi vào metaField | Bucket fragmentation | Stable metadata |
| Group theo UTC nhưng label local | Sai báo cáo ngày | Đồng bộ timezone |
| Cộng mọi eventType | Double counting | Metric semantics |
| Cộng USD+VND | Sai tiền | Group currency |
| $inc mỗi lần Change Stream replay | Double count | Dedup/atomic checkpoint |
| Dùng $merge merge khi batch recompute | Có thể giữ số cũ sai | Replace deterministic |
| Không xóa rollup rỗng | Stale metrics | Reconciliation |
| Chỉ index occurredAt | Tenant query chậm | Compound index phù hợp |
| Too many indexes | Write amplification | Workload-driven indexes |
| Không giới hạn $densify | Output bùng nổ | Bound window/step |
| Long aggregation làm API | Latency cao | Materialize/async |
| Không kiểm tra retention backups | Xóa không triệt để | Governance toàn lifecycle |
| Legal hold bằng null tùy hứng | Khó audit | Explicit hold policy |
| Archive rồi không verify | Mất dữ liệu | Checksum/count/restore drill |
| Chốt số theo batch một lần | Late corrections | Watermark/restate policy |

## 50. Checklist production cho event data

### Mô hình và schema

- [ ] Đã phân loại domain/audit/telemetry/CDC events.
- [ ] Có stable event ID và tenant/aggregate identity.
- [ ] Có `schemaVersion` và contract evolution policy.
- [ ] Có `occurredAt` và `receivedAt` theo nghĩa rõ ràng.
- [ ] Timestamps dùng BSON Date, UTC storage.
- [ ] Decimal128 hoặc numeric model đúng cho money.
- [ ] Không lưu secrets/PII thừa trong payload.
- [ ] Có correction/compensation semantics.
- [ ] Có idempotency khi retries hoặc replay.
- [ ] Có unique/shard-key design được kiểm tra.

### Lưu trữ và retention

- [ ] Regular vs time-series được chọn dựa trên constraints.
- [ ] Time-series limits về unique/transactions/updates đã được hiểu.
- [ ] TTL single-field Date hoặc collection TTL phù hợp.
- [ ] TTL deletion lag được chấp nhận/giám sát.
- [ ] Có schema validation cho expiry fields.
- [ ] Late arrivals không tự bị xóa ngoài ý muốn.
- [ ] Backup/archive/legal hold policy thống nhất.
- [ ] Archive được verify trước hot deletion.
- [ ] Có restore test và checksum.
- [ ] Có owner và approval khi đổi retention.

### Query/analytics

- [ ] Query luôn có tenant/time filters phù hợp.
- [ ] Sử dụng half-open time ranges.
- [ ] Group by dateTrunc với timezone đúng.
- [ ] Business metric định nghĩa event types/units/currency.
- [ ] Có cách xử lý empty buckets và data quality.
- [ ] Indexes phục vụ timeline/report workload.
- [ ] Explain/profiler/performance được đo với dataset đại diện.
- [ ] Không gây memory/disk spills quá mức.
- [ ] Có rollup cho long-range/frequent dashboards.
- [ ] Rollup rerun/late corrections được kiểm tra.

### Hệ thống và vận hành

- [ ] Change Streams có resume/checkpoint khi dùng.
- [ ] Consumer có idempotency/fencing.
- [ ] Oplog window và lag được giám sát.
- [ ] Có data correctness test sau failover/restart.
- [ ] Có metrics ingestion/rollup/archive/TTL.
- [ ] Có alert theo latency, backlog và retention.
- [ ] RBAC hạn chế writes/updates/deletes.
- [ ] Audit và data privacy policy được áp dụng.
- [ ] Có runbook backfill/replay/recompute.
- [ ] Có owner/incident procedure khi mất dữ liệu.

## 51. Bài tập thực hành

Chỉ chạy các thao tác tạo/xóa TTL, chèn dữ liệu hoặc chỉnh schema trên MongoDB lab.

### Bài 1 — Phân biệt loại sự kiện

So sánh domain event, audit event, telemetry measurement và MongoDB change stream.

### Bài 2 — State vs history

Một order hiện SHIPPED. Những câu hỏi nào cần event history thay vì chỉ đọc order status?

### Bài 3 — Event identity

Thiết kế eventId ổn định qua producer retries và tránh duplicate inserts.

### Bài 4 — Tenant isolation

Một event collection phục vụ 100 tenants. Thiết kế fields/queries để không lộ dữ liệu tenant khác.

### Bài 5 — Event time và ingest time

Thiết bị ghi sự kiện lúc 09:00 và gửi lúc 12:00. Dashboard ngày dùng trường nào?

### Bài 6 — SchemaVersion

Tạo hai version của PaymentCaptured và phương án backward-compatible consumer.

### Bài 7 — Correction

Một payment đã ghi sai amount. Vì sao thêm AdjustmentPosted event có thể tốt hơn sửa event gốc?

### Bài 8 — Money

Giải thích vì sao binary floating point có thể gây sai lệch khi cộng tiền; dùng Decimal128 ra sao?

### Bài 9 — Regular vs time-series

Một audit event cần unique ID và transaction cùng order. Chọn loại collection nào?

### Bài 10 — Time-series constraints

Vì sao không dùng unique index trên eventId trong time-series collection?

### Bài 11 — TTL cơ bản

Tạo TTL index trên expiresAt Date, expireAfterSeconds:0.

### Bài 12 — TTL delay

Tại sao event vừa hết hạn chưa chắc biến mất ngay?

### Bài 13 — TTL invalid values

Nếu expiresAt là string hoặc missing, chính sách xóa có vấn đề gì?

### Bài 14 — Late arrival và retention

Event đã xảy ra 45 ngày trước mới ingest, TTL 30 ngày từ occurredAt. Điều gì có thể xảy ra?

### Bài 15 — Partial TTL

Phân loại debug events và audit events có thời hạn khác nhau; thiết kế collection/policy an toàn.

### Bài 16 — Legal hold

Một event đang hết TTL nhưng có legal hold. Thiết kế workflow ngăn xóa và lưu approval.

### Bài 17 — Archive-first

Viết các gates kiểm chứng cần có trước khi xóa dữ liệu hot sau export.

### Bài 18 — Backup vs archive

Vì sao backup snapshot không đồng nghĩa một hệ thống archive có thể query/replay lâu dài?

### Bài 19 — Time-series bucket expiry

Một bucket có measurements 08:00, 08:20, 08:55. Vì sao không xóa bucket lúc record 08:00 hết hạn?

### Bài 20 — Time-series meta

Chọn metadata ổn định cho device measurements và chỉ ra field không nên đưa vào meta.

### Bài 21 — Sharding

Nếu cần unique {tenantId,eventId}, shard key nên liên hệ thế nào với unique index?

### Bài 22 — Timeline index

Thiết kế index cho tenantId + aggregateId + occurredAt, giải thích sort.

### Bài 23 — Reporting index

Thiết kế index cho tenantId + eventType + time range.

### Bài 24 — Half-open interval

Vì sao dùng `$gte start` và `$lt end` thay cho 23:59:59?

### Bài 25 — Aggregate count

Đếm PaymentCaptured theo từng giờ bằng `$match`, `$group`, `$dateTrunc`.

### Bài 26 — Net amount

Từ dataset lab, tính net amount của tenant-A cho hai ngày 10 và 11 UTC.

### Bài 27 — Multi-currency

Giải thích vì sao tổng USD+VND không có ý nghĩa nếu thiếu FX conversion policy.

### Bài 28 — Local timezone

Một event 23:30 UTC thuộc ngày nào ở Việt Nam? Viết dateTrunc timezone phù hợp.

### Bài 29 — DST

Vì sao một ngày địa phương có thể không dài 24 giờ?

### Bài 30 — Missing bucket

Một biểu đồ không có measurement tại 07:00. Khi nào nên fill 0, khi nào nên trả missing?

### Bài 31 — $densify

Densify theo giờ trong khoảng một ngày; những giới hạn để không bùng nổ output?

### Bài 32 — $fill

So sánh last-observation-carried-forward và linear interpolation.

### Bài 33 — Running total

Dùng `$setWindowFields` trên rollup ngày để tạo cumulative net payments.

### Bài 34 — Batch rollup

Sử dụng `$merge` khiMatched=replace để tính lại daily bucket mà không double count khi retry.

### Bài 35 — Empty bucket

Nếu source events của một ngày bị correction/remove hết, vì sao `$merge` không tự xóa rollup cũ?

### Bài 36 — Late events

Một event ngày 10 được nhận ngày 12. Thiết kế recompute/restatement strategy.

### Bài 37 — Change Stream replay

Consumer increment rollup xong nhưng chết trước checkpoint. Cần cơ chế nào để không double count?

### Bài 38 — Oplog history loss

Consumer downtime dài hơn oplog window. Có thể resume token cũ bằng cách retry mãi không?

### Bài 39 — Outbox

Thiết kế transaction cập nhật order + ghi event/outbox trong regular collections.

### Bài 40 — Performance

Giải thích sự khác nhau giữa docsExamined, keysExamined, query duration và disk spill.

### Bài 41 — Projection quyền truy cập

Producer chỉ cần insert; report reader chỉ cần find. Vì sao không dùng chung root account?

### Bài 42 — Java Driver

Viết insert event với stable ID và phân biệt duplicate retry hợp lệ với duplicate payload conflict.

### Bài 43 — Spring Data

Tạo DomainEvent entity có occurredAt và query aggregation theo tenant/time.

### Bài 44 — TTL observation

Viết script đếm events đã quá expiresAt nhưng còn tồn tại. Vì sao không kết luận ngay TTL hỏng?

### Bài 45 — Test plan

Đề xuất positive/negative test cho unique IDs, time boundaries, timezone, late data, retention và rollup.

### Bài 46 — Lập kiến trúc tổng hợp

Thiết kế hệ thống xử lý một tỷ order/payment events mỗi tháng với:

- Raw MongoDB regular event collection.
- Tenant/aggregate identities và uniqueness.
- Hot retention 90 ngày, archive dài hạn.
- TTL và legal hold workflow.
- Atlas/self-managed backup strategy.
- Index theo timeline và report.
- Daily materialized rollups.
- Late arrivals và restatement.
- Java/Spring Data ingestion.
- Monitoring, SLO, dedup, replay.
- Data privacy và restoration drill.

## 52. Tổng kết

Một thiết kế dữ liệu sự kiện MongoDB đáng tin cần đồng thời giải quyết **lưu lịch sử**, **thời gian giữ** và **khả năng tổng hợp**:

1. **Lịch sử:** Event có ID ổn định, tenant/aggregate identity, timestamp event/ingest, schema version và payload tối thiểu. Sửa lịch sử bằng correction/compensation, không âm thầm ghi đè.
2. **Lựa chọn collection:** Regular collections phù hợp domain/audit/transactional events; time-series phù hợp measurements dày đặc nhưng có hạn chế unique indexes, updates và transaction writes.
3. **Retention:** TTL index hoặc time-series `expireAfterSeconds` chỉ là xóa nền không tức thì. Muốn đúng lifecycle phải có archive-first, backup/retention alignment, legal hold và data privacy controls.
4. **Truy vấn:** Dùng tenant + time filters, khoảng `[start,end)`, BSON Date/UTC, `$dateTrunc` với timezone và business metric semantics; không cộng lẫn event types/currencies.
5. **Tổng hợp:** Dashboard thường xuyên nên dùng rollup với khả năng recompute. `$merge` theo cách deterministic tránh double count; late events buộc phải có watermark/restate policy.
6. **Vận hành:** Change Stream chỉ là nguồn sự kiện gần real-time, không phải archive; cần idempotent consumers, checkpoint, oplog headroom, tests và reconciliation.
7. **Bảo mật:** Append-only application behavior, least-privilege RBAC, audit, encryption và retention policy phải được thiết kế cùng nhau.

**Quy tắc nhớ nhanh:** *Lưu sự kiện để giữ sự thật đã xảy ra; retention để kiểm soát vòng đời; rollup để trả lời nhanh — nhưng chỉ đáng tin khi cả ba dùng cùng định nghĩa về thời gian, identity và tính đúng đắn.*

## Tài liệu tham khảo chính thức

- [MongoDB Manual — Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/)
- [MongoDB Manual — Time Series Collection Limitations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/)
- [MongoDB Manual — Time Series Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-index/)
- [MongoDB Manual — Automatic Removal for Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/)
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Manual — Indexing Strategies](https://www.mongodb.com/docs/manual/applications/indexes/)
- [MongoDB Manual — Unique Indexes and Sharding](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/)
- [MongoDB Manual — $dateTrunc](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/)
- [MongoDB Manual — $densify](https://www.mongodb.com/docs/manual/reference/operator/aggregation/densify/)
- [MongoDB Manual — $fill](https://www.mongodb.com/docs/manual/reference/operator/aggregation/fill/)
- [MongoDB Manual — $setWindowFields](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setWindowFields/)
- [MongoDB Manual — $merge](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changestreams/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/)
- [Spring Data MongoDB — Aggregation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html)
- [Spring Data MongoDB — Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html)
