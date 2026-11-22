# Chuyển lưu lượng, theo dõi sai lệch và phương án quay lại trong MongoDB

Khi một ứng dụng thay đổi mô hình document, tách collection, nâng cấp schema hoặc chuyển MongoDB sang cluster mới, việc sao chép đủ dữ liệu lịch sử **chưa có nghĩa migration đã hoàn thành**. Trong khi backfill chạy, ứng dụng vẫn tạo đơn hàng, cập nhật số dư, hủy giao dịch và xóa bản ghi. Nếu đổi lưu lượng đọc quá sớm, người dùng có thể thấy dữ liệu cũ. Nếu đổi lưu lượng ghi không có rào chắn, hai đường dữ liệu có thể phân kỳ. Nếu lập tức quay về nguồn cũ sau khi nguồn mới đã nhận các giao dịch được xác nhận, những thay đổi đó có thể **biến mất** khỏi ứng dụng.

Vì vậy, tiến hóa dữ liệu MongoDB cần thiết kế ba năng lực cùng lúc:

1. **Chuyển lưu lượng có kiểm soát:** xác định source of truth, thực hiện shadow reads/canary, chốt điểm cutover và ngăn writers không đúng quyền.
2. **Theo dõi sai lệch có ý nghĩa:** so sánh khóa, nội dung, revision, deletes, business invariants, CDC lag và hiệu năng, không chỉ so count.
3. **Quay lại có bảo toàn dữ liệu:** xác định rollback window, reverse sync và chính sách xử lý những writes mới đã commit sau cutover.

Bài thuộc chương **Tiến hóa dữ liệu** của module *Database Engine Document MongoDB*. Ví dụ sử dụng hai collections `orders_v1` và `orders_v2`, cùng các tình huống hai clusters. Lệnh ghi chỉ chạy trên **database lab cô lập**; thresholds và hostname là giả lập. Tính năng change streams, transactions, read concern, sharding và driver options phải được kiểm tra theo phiên bản/topology thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt data migration, backfill, CDC, read cutover, write cutover và rollback.
2. Xây state machine `prepare → backfill → catch-up → verify → shadow → canary → cutover → stabilize → contract`.
3. Chỉ ra nguồn dữ liệu authoritative trong từng pha và cách bảo vệ quyền ghi.
4. So sánh big-bang, expand-and-contract, blue/green, shadow reads, dual writes và CDC.
5. Tổ chức backfill trong khi vẫn thu change events để không bỏ sót writes.
6. Hiểu checkpoints, resume tokens, oplog window, event ordering, deletes và idempotency.
7. Thiết kế hàm transform và canonical parity cho schema thay đổi.
8. Đo missing/extra IDs, same-revision mismatches, lag và business invariants.
9. Thiết lập canary cohort, read-your-writes policy và ngưỡng GO/NO-GO.
10. Chuyển quyền ghi bằng drain, fencing, watermark và xác nhận writers cũ ngừng.
11. Phân biệt rollback trước và sau khi writes đã chuyển sang v2.
12. Xây reverse CDC, rollback window và forward-fix decision.
13. Kiểm thử fault/crash/replay, diễn tập rollback và vận hành dashboard.

## 2. Dữ liệu đã copy khác lưu lượng đã chuyển

| Dữ liệu | Lưu lượng | Trạng thái |
|---|---|---|
| v2 rỗng | Đọc/ghi v1 | Chuẩn bị |
| v2 đang backfill | Đọc/ghi v1 | Chưa đủ dữ liệu |
| Copy xong nhưng CDC còn lag | Đọc/ghi v1 | Chưa đủ mới |
| v2 bắt kịp và parity đạt | Đọc/ghi v1, shadow v2 | Kiểm chứng |
| Canary reads v2 | Writes v1 | Kiểm tra UX/latency, xử lý consistency |
| Đổi quyền ghi | Drain/fence, chốt watermark | Thời điểm rủi ro |
| v2 authoritative | Đọc/ghi v2 | Theo dõi và giữ rollback readiness |
| Hết rollback window | Đọc/ghi v2 | Dọn nguồn cũ có kiểm soát |

### 2.1. Source of truth

Source of truth là đường dữ liệu được công nhận để quyết định **một business write đã thành công hay chưa**. Một bản sao có revision mới hơn không tự trở thành authority nếu nó được ghi bởi worker sai đường.

### 2.2. Hai collections và hai clusters

Trong một MongoDB deployment hỗ trợ transactions, nhiều writes có thể được commit trong một transaction theo giới hạn tương ứng. Với **hai MongoDB clusters độc lập**, không có transaction MongoDB thông thường tự commit nguyên tử xuyên cả hai clusters. Cần protocol replication/outbox, retry và reconciliation.

### 2.3. State machine

~~~mermaid
stateDiagram-v2
    [*] --> PREPARE
    PREPARE --> BACKFILL
    BACKFILL --> CATCH_UP
    CATCH_UP --> SHADOW
    SHADOW --> CANARY_READ
    CANARY_READ --> WRITE_CUTOVER
    WRITE_CUTOVER --> STABILIZE
    STABILIZE --> CONTRACT
    CANARY_READ --> READ_ROLLBACK
    WRITE_CUTOVER --> SYNC_ROLLBACK
    STABILIZE --> SYNC_ROLLBACK
    READ_ROLLBACK --> SHADOW
    SYNC_ROLLBACK --> PREPARE
    CONTRACT --> [*]
~~~

Không đi từ BACKFILL thẳng đến CONTRACT chỉ vì row count đã bằng nhau.

## 3. Ví dụ xuyên suốt: orders_v1 → orders_v2

Document cũ:

~~~javascript
{
  _id: "O-1001",
  tenantId: "t-01",
  amountCents: NumberLong(125000),
  state: "paid",
  updatedAt: ISODate("2026-11-01T10:00:00Z"),
  revision: NumberLong(7)
}
~~~

Document mới:

~~~javascript
{
  _id: "O-1001",
  tenantId: "t-01",
  totalMinor: NumberLong(125000),
  status: "PAID",
  updatedAt: ISODate("2026-11-01T10:00:00Z"),
  revision: NumberLong(7),
  schemaVersion: 2
}
~~~

Giữ nguyên `_id`, tenant, money units và revision. `amountCents` thành `totalMinor`, `state` thành `status`. Nếu đổi ID, cần **stable ID mapping** và xử lý các foreign references. Tự sinh ID mới mỗi lần retry backfill tạo nguy cơ duplicate.

### 3.1. Revision phải đơn điệu

Backfill có thể đưa revision 7 tới v2 **sau khi** CDC đã áp revision 9. Nếu writer dùng replace không điều kiện, v2 bị lùi trạng thái. Cần monotonic revision hoặc event sequence theo aggregate; timestamps do clients cung cấp không phải bảo đảm tuyệt đối cho ordering.

### 3.2. Hàm transform deterministic

~~~javascript
function toV2(source) {
  const states = {
    pending: "PENDING",
    paid: "PAID",
    shipped: "SHIPPED",
    cancelled: "CANCELLED"
  };
  const status = states[source.state];
  if (!status) throw new Error("UNKNOWN_STATE:" + source.state);
  return {
    _id: source._id,
    tenantId: source.tenantId,
    totalMinor: source.amountCents,
    status,
    revision: source.revision,
    updatedAt: source.updatedAt,
    schemaVersion: 2
  };
}
~~~

Không âm thầm đổi unknown status thành PENDING; đưa vào quarantine và alert. Không dùng `new Date()` hoặc random number để tạo canonical business output nếu cần đối soát lặp lại.

## 4. Các chiến lược chuyển đổi

| Chiến lược | Cơ chế | Rủi ro |
|---|---|---|
| Big-bang | Tạm dừng writes, copy rồi chuyển một lần | Downtime, rollback phức tạp |
| Expand-and-contract | Readers/writers tương thích nhiều schema qua releases | Duy trì compatibility lâu |
| Shadow read | Query v2 để so nhưng vẫn trả v1 | Tăng read load, metrics có lag |
| Canary read | Cohort nhỏ đọc v2 thật | Read-your-writes, p99 |
| Dual write | Ghi cùng business action tới v1/v2 | Partial success, ordering, authority |
| Backfill + CDC | Copy lịch sử và apply changes liên tục | Checkpoint, oplog gap |
| Blue/green | Hai deployments trước khi đổi traffic | Dữ liệu mới sau cutover khó đảo |

Lựa chọn phụ thuộc số writes/s, data size, yêu cầu downtime, backward compatibility, nghiệp vụ và topology.

## 5. Expand → migrate → contract

**Expand:** phát hành readers chịu được cả old/new fields, tạo target indexes và chuẩn bị migration code. **Migrate:** backfill, đồng bộ CDC, đối soát, shadow, canary và cutover. **Contract:** chỉ xóa đường cũ sau stabilization và hết rollback window.

~~~text
App cũ:       đọc/ghi v1 ------------------------------|
App chuyển:   hiểu v1/v2, ghi theo authority ----------|
App mới:                              đọc/ghi v2 ----------------|
Xóa v1:                                                  sau cùng
~~~

Trong rolling deploy, một scheduled job hoặc consumer cũ vẫn có thể chạy dù phần lớn HTTP pods đã lên version mới.

### 5.1. Readers trước writers

Thông thường deploy code **đọc được schema mới** trước khi writers bắt đầu ghi schema chỉ v2 hiểu. Đừng xóa field cũ trước khi tất cả consumers đã được chuyển.

### 5.2. Dual fields trong một document

Nếu đổi schema tại chỗ, một atomic update trên cùng document có thể duy trì cả fields cũ/mới:

~~~javascript
db.orders.updateOne(
  { _id: "O-1001", tenantId: "t-01" },
  { $set: {
      amountCents: NumberLong(125000),
      totalMinor: NumberLong(125000),
      state: "paid",
      status: "PAID",
      schemaVersion: 2
  }}
);
~~~

Mọi write path phải duy trì chúng theo contract; một worker cũ chỉ cập nhật `state` có thể tạo drift nội document.

## 6. Quyền ghi theo từng pha

| Pha | Writes authoritative | Reads | Đường phụ |
|---|---|---|---|
| PREPARE | v1 | v1 | Index/validator v2 |
| BACKFILL | v1 | v1 | Batch copy |
| CATCH_UP | v1 | v1 | CDC v1→v2 |
| SHADOW | v1 | v1 | Compare v2 |
| READ_CANARY | v1 | v1/v2 | CDC v1→v2 |
| WRITE_CUTOVER | Chuyển có fencing | Tùy gate | Watermark/drain |
| STABILIZE | v2 | v2 | Reverse sync nếu cần |
| CONTRACT | v2 | v2 | Xóa phụ thuộc cũ |

**Dual write** không có nghĩa hai phía đều được tự quyết khi kết quả khác nhau. Phải xác định acknowledgement, retries, conflict resolution và source of truth rõ.

## 7. Chuẩn bị inventory

1. Dữ liệu: collections, document size, variants, indexes, unique keys, TTL, validators, collation.
2. Writers: APIs, cron, queues, batch scripts, ETL, admin tools, external integrations.
3. Readers: services, reports, search, caches, data warehouse và outbox consumers.
4. Topology: replica set/sharding, shard key, FCV, regions, DNS, TLS, drivers.
5. Semantics: tenant isolation, money types, states, retention, read/write concern, idempotency.
6. Operations: backups/PITR, oplog window, throughput, on-call, rollback RPO/RTO và owners.

### 7.1. Tạo indexes/validators trước cutover

Sao chép documents không mặc nhiên sao chép đúng target indexes, collation, TTL và access roles. Một v2 đúng dữ liệu nhưng thiếu unique index có thể nhận double bookings sau khi bật writes.

### 7.2. Bảo vệ source

Backfill/shadow tạo thêm CPU, I/O, network và connections. Giới hạn batch size/concurrency, test qua workload đại diện và tránh tạo tình trạng source quá tải trước khi cutover.

## 8. Backfill cùng change data capture

~~~mermaid
flowchart LR
    V1["Source v1"] -->|"Batched scan"| V2["Target v2"]
    V1 -->|"Change streams"| CDC["CDC + checkpoint"]
    CDC -->|"Idempotent apply"| V2
    V2 --> Compare["Parity + watermark"]
~~~

Nếu backfill chạy hai giờ, dữ liệu vẫn đổi suốt hai giờ. Mở change capture **sau khi** copy xong có thể bỏ sót inserts, updates và deletes xảy ra trong cửa sổ scan.

### 8.1. Quy trình

1. Thiết lập stream/checkpoint có thể resume **trước cửa sổ scan**.
2. Quét source theo key/ranges; lưu checkpoints của backfill.
3. Nhận/buffer events phát sinh trong lúc scan.
4. Apply target theo stable ID, revision/sequence và deletes.
5. Replay backlog và tiếp tục CDC tới source watermark.
6. Xác minh parity tại boundary có thể so sánh.

### 8.2. Không mặc nhiên là snapshot

Nhiều lần `find` trên một collection không tự tạo snapshot cùng thời điểm. Nếu không có snapshot read phù hợp, cần CDC/version guard xử lý race giữa backfill và writes đang chạy.

### 8.3. Oplog retention

Nếu CDC worker tạm dừng vượt history window, resume token có thể không dùng được. Monitor oplog headroom/checkpoint age, alert và dùng resync plan; **không mở lại stream từ “now” rồi tuyên bố dữ liệu hoàn chỉnh**.

## 9. Backfill theo khóa và checkpoint

Lab riêng:

~~~javascript
use migration_lab
db.orders_v1.insertMany([
  {
    _id: "O-1001", tenantId: "t-01",
    amountCents: NumberLong(125000), state: "paid",
    revision: NumberLong(7),
    updatedAt: ISODate("2026-11-01T10:00:00Z")
  },
  {
    _id: "O-1002", tenantId: "t-01",
    amountCents: NumberLong(95000), state: "pending",
    revision: NumberLong(1),
    updatedAt: ISODate("2026-11-02T10:00:00Z")
  }
])
~~~

Một batch:

~~~javascript
const lastId = "O-1000";
const rows = db.orders_v1.find(
  { _id: { $gt: lastId } }
).sort({ _id: 1 }).limit(500).toArray();
print(rows.length);
~~~

### 9.1. Vì sao không dùng skip sâu?

`skip(5000000)` có thể duyệt nhiều index entries; seek theo last key thường tiết kiệm hơn khi scan. Nhưng inserts mới có `_id` thấp hơn last key vẫn phải được **CDC** bao phủ.

### 9.2. Checkpoints phải bền

Lưu last source key, progress per range, target apply outcomes, CDC token và verified watermark. Một worker có thể crash sau target write nhưng trước checkpoint; retry batch không được nhân đôi dữ liệu hoặc lùi revision.

## 10. Change streams

MongoDB change streams hỗ trợ theo dõi thay đổi trên topology phù hợp (thường replica set/sharded cluster). Ví dụ Node.js **chỉ nhận events**:

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient(process.env.MONGO_SOURCE_URI);
await client.connect();
try {
  const source = client.db("migration_lab").collection("orders_v1");
  const stream = source.watch(
    [],
    { fullDocument: "updateLookup", maxAwaitTimeMS: 1000 }
  );
  try {
    for await (const event of stream) {
      console.log({
        type: event.operationType,
        key: event.documentKey,
        hasResumeToken: Boolean(event._id)
      });
      // Production: validate, transform, apply, checkpoint.
    }
  } finally {
    await stream.close();
  }
} finally {
  await client.close();
}
~~~

### 10.1. `updateLookup` không bảo đảm đúng post-image event

`fullDocument:"updateLookup"` có thể trả trạng thái majority-committed **mới hơn** trạng thái ngay sau event đó nếu document đã được sửa tiếp. Với replay chính xác phải hiểu `updateDescription`, pre/post images khi có support, version và ordering.

### 10.2. Delete events

Delete thường cung cấp `documentKey`, không mặc nhiên kèm full document đã xóa. Target cần xử lý delete/tombstone theo stable key và thứ tự, nếu không backfill cũ có thể tái tạo document.

## 11. Durable checkpoint và at-least-once

~~~text
Nhận event E
  → Validate/transform
  → Apply target durably
  → Persist token/checkpoint của E
  → Advance progress
~~~

Checkpoint trước target apply có thể khiến event mất sau crash. Target apply trước token có thể làm event được replay; vì vậy applicator cần **idempotent operations** hoặc atomic checkpoint+apply nếu cùng transaction boundary hỗ trợ.

### 11.1. Token là opaque BSON

Không tự bóc token thành timestamp rồi dùng như resume token khác. Lưu đúng form/source/namespace và xử lý token invalidation, oplog gap bằng pause + alert + resync.

### 11.2. Parallel processing

Nếu event E102 còn lỗi nhưng E103 đã apply, checkpoint không được vượt qua E102 nếu khi restart sẽ bỏ event. Quản lý **contiguous applied watermark** và order per aggregate key.

## 12. Chống backfill cũ ghi đè CDC mới

Tình huống:

~~~text
Backfill đọc revision 7
CDC apply revision 9 vào v2
Backfill revision 7 tới muộn
~~~

Unconditional replace sẽ làm v2 lùi version. Quy tắc:

~~~text
incoming > stored → apply
incoming = stored → replay/no-op nếu cùng canonical payload
incoming < stored → skip stale
same revision nhưng khác nội dung → report conflict
~~~

### 12.1. CAS cho target đã có document

~~~javascript
const incoming = toV2(sourceDocument);
const result = db.orders_v2.replaceOne(
  {
    _id: incoming._id,
    revision: { $lt: incoming.revision }
  },
  incoming
);
~~~

Nếu `matchedCount=0`, target có thể chưa tồn tại hoặc version bằng/lớn hơn. Cần insert-if-absent với unique `_id`, version check và xử lý races. Không gắn `upsert:true` bừa vào filter versioned: khi document có version mới, upsert có thể cố tạo lại cùng `_id` và gặp E11000.

### 12.2. Tombstone ngăn resurrection

~~~javascript
{
  _id: "O-1001",
  deleted: true,
  revision: NumberLong(10)
}
~~~

Một stale update revision 7 không được áp lên tombstone 10. Delete events không tự chứa revision trong mọi schema; migration phải định nghĩa sequence/ordering và thời gian giữ tombstone bao phủ replay window.

## 13. Dual writes khác một authority + CDC

Một pattern có nguồn quyền rõ:

~~~text
App write v1 authoritative
    → durable change/outbox
         → idempotent apply v2
~~~

Nếu app gửi hai writes trực tiếp tới **hai clusters**, v1 có thể thành công trong khi v2 timeout. Không có cross-cluster MongoDB transaction mặc định khiến chúng atomic; cần durable retry/reconcile và policy đánh giá business success.

### 13.1. Không tự chuyển thành hai nguồn truth

Hai services cùng ghi v1/v2 có thể gây split-brain. Dù dual write, cần xác định đường authoritative, cách xử lý partial write, per-key order và idempotency.

### 13.2. Event deduplication khác HTTP request deduplication

CDC event có thể replay sau crash; checkout request cũng có thể bị user gửi lại sau timeout. Phải phân biệt event identity với business operation/request ID.

## 14. Shadow reads: so sánh không phục vụ v2

~~~mermaid
flowchart LR
    Req["Client"] --> API["Backend"]
    API --> Old["v1 read"]
    API -.-> New["v2 shadow read"]
    Old --> Response["Response"]
    Old -.-> Compare["Canonical diff"]
    New --> Compare
    Compare --> Metrics["Metrics + redacted samples"]
~~~

Quy tắc:

- User vẫn nhận **v1 output**.
- v2 reads được sample và giới hạn timeout/concurrency.
- Giữ cùng tenant filter, projection, sort và authorization context.
- So sánh canonical business representation thay vì raw JSON.
- Không log PII/tokens/payment payload; log hashed IDs, revision, paths và metadata được duyệt.
- Shadow nên async/bounded để v2 không làm p99 của v1 tăng.

### 14.1. Shadow không tạo distributed snapshot

Hai reads gần đồng thời vẫn có thể thấy revision khác nhau do CDC lag. So sánh phải biết **expected lag** thay vì báo mọi diff thành data corruption.

## 15. Node.js canonical comparison

~~~javascript
function canonicalOrder(doc, isOld) {
  if (!doc) return null;
  return {
    id: doc._id,
    tenant: doc.tenantId,
    money: String(isOld ? doc.amountCents : doc.totalMinor),
    status: isOld
      ? String(doc.state).toUpperCase()
      : doc.status,
    revision: String(doc.revision)
  };
}

async function compareOne(oldColl, newColl, tenantId, id) {
  const filter = { _id: id, tenantId };
  const [oldDoc, newDoc] = await Promise.all([
    oldColl.findOne(filter), newColl.findOne(filter)
  ]);
  const left = canonicalOrder(oldDoc, true);
  const right = canonicalOrder(newDoc, false);
  return {
    equal: JSON.stringify(left) === JSON.stringify(right),
    oldRevision: left?.revision ?? null,
    newRevision: right?.revision ?? null
  };
}
~~~

Chỉ là demo với object có field order do hàm canonical cố định. Production cần xử lý ObjectId, Decimal128, timestamps, arrays, null/missing và tiền tệ mà không chuyển sang floating-point không chính xác.

### 15.1. Phân loại diff

- v1 revision > v2: target có thể đang lag.
- Cùng revision nhưng content khác: nghi mapper/data corruption.
- v2 revision > v1 khi v1 vẫn authoritative: nghi unauthorized target writer.
- Record missing ở một bên: kiểm tra checkpoint, delete và backfill.

## 16. Canonicalization theo business contract

| Thành phần | Quy tắc cần quyết định |
|---|---|
| Money | Units, Decimal128, rounding, currency |
| Timestamp | UTC/millisecond, null semantics |
| Status | Mapping đầy đủ, unknown states |
| Strings | Case/Unicode normalization chỉ khi được phép |
| Arrays | Thứ tự có ý nghĩa hay là set? |
| IDs | Stable IDs/mapping |
| Missing/null | Có tương đương không? |
| Deletes | Tombstone và visibility policy |
| Metadata | Bỏ migration-only fields có chủ đích |

Không được chuẩn hóa quá mức để giấu lỗi: nếu nghiệp vụ phân biệt `"ABC"` và `"abc"`, việc lower-case cả hai sẽ che mismatch thật.

## 17. Theo dõi sai lệch không chỉ bằng count

| Loại | Chỉ số | Điều muốn kiểm tra |
|---|---|---|
| Key parity | Missing IDs, extra IDs | Có cùng tập records ở mốc đã xác minh không? |
| Revision parity | Target behind/ahead | Đang lag hay có writer ngoài quy trình? |
| Content parity | Canonical mismatch tại cùng revision | Mapping có chính xác không? |
| Delete parity | Pending deletes, resurrected IDs | Không tái tạo bản ghi đã xóa |
| CDC health | Checkpoint age, capture/apply lag, dead letters | Pipeline còn bắt kịp không? |
| Business invariant | Tổng tiền, uniqueness, status transitions | Có phá quy tắc nghiệp vụ không? |
| Performance | p95/p99, CPU, I/O, connection pool wait | Target có đáp ứng SLO không? |
| Safety | Old writer attempts, routing epoch conflicts | Có split-brain writes không? |

### 17.1. Count bằng nhau không chứng minh dữ liệu giống nhau

~~~text
v1 IDs = {A, B, C}
v2 IDs = {A, B, D}
~~~

Hai phía đều có count=3 nhưng thiếu C và thừa D. Kể cả IDs giống nhau, money/status vẫn có thể khác.

### 17.2. Chia buckets để đối soát

Chia theo `tenantId`, shard, khoảng `_id` hoặc ngày tạo. Mỗi bucket có source count, target count, missing/extra IDs, checksum canonical và số mismatch. Khoanh vùng bucket sai để reconcile, tránh quét lại toàn collection mỗi lần.

### 17.3. Sampling và full coverage

Shadow sampling cho tín hiệu sớm nhưng không chứng minh mọi document đúng. Trước cutover quan trọng, cân nhắc full deterministic reconciliation hoặc coverage theo yêu cầu rủi ro. Đo tỷ lệ coverage và tuổi của kết quả đối soát.

## 18. Watermark và độ trễ đồng bộ

Một mô hình:

~~~text
sourceWatermark = latest source change đã được xác nhận
targetWatermark = latest contiguous change đã apply bền ở v2
lag = khoảng cách có định nghĩa giữa hai mốc
~~~

Đừng trừ tùy tiện timestamps từ hai hosts có clock skew hoặc coi MongoDB cluster times của hai clusters độc lập là một đồng hồ chung nếu không có mapping.

### 18.1. Bốn loại lag

1. Capture lag: source đã commit nhưng listener chưa đọc.
2. Queue lag: đã capture nhưng đang chờ worker.
3. Apply lag: target chưa commit.
4. Visibility lag: target đã có nhưng API/secondary/cache chưa thấy.

Queue lag bằng 0 không tự bảo đảm **read-your-writes** ở đường đọc của khách.

### 18.2. Contiguous applied watermark

Worker xử lý E101, E102, E103. Nếu E103 hoàn tất mà E102 còn lỗi, không được checkpoint qua E102 nếu restart sẽ bỏ E102.

### 18.3. Per-key skew

Một order cập nhật liên tục có thể vẫn behind dù p50 lag toàn pipeline thấp. Quan sát tail latency, hot keys, failure queue và tenants quan trọng.

## 19. Các phép đối soát có giá trị

Trong lab:

~~~javascript
const dbLab = db.getSiblingDB("migration_lab");
print(dbLab.orders_v1.countDocuments({ tenantId: "t-01" }));
print(dbLab.orders_v2.countDocuments({ tenantId: "t-01" }));
~~~

Đếm ở hai thời điểm khác nhau khi writes đang chạy chỉ có ý nghĩa **tín hiệu sơ bộ**. Phải kiểm chứng theo một watermark hoặc tập dữ liệu ổn định.

### 19.1. Aggregate theo business status

~~~javascript
db.orders_v2.aggregate([
  { $match: { tenantId: "t-01" } },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 },
      sumTotalMinor: { $sum: "$totalMinor" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

So với aggregation đã canonical của v1 **cùng boundary**; không kết luận tiền bị mất khi v1 tiếp tục nhận orders trong lúc query v2 chưa bắt kịp.

### 19.2. Business invariants

- Không mất `tenantId` và không đổi đơn vị tiền.
- Không có trạng thái chưa được mapper định nghĩa.
- Unique business key như `(tenantId,orderNo)` vẫn được enforce.
- Không có confirmed order thiếu ledger.
- Không xóa nhầm record do TTL/validator khác.
- Không nhân đôi payment khi CDC/retry.

### 19.3. Metadata và sharding

Target phải có indexes, unique/partial index constraints, collation, validators, TTL và roles đúng. Nếu đổi shard key hoặc topology, tính duy nhất toàn cluster và routing có thể khác; cần kiểm tra luật unique index theo server/shard key thực tế.

## 20. Phân loại mismatch trước khi sửa

| Loại | Ví dụ | Xử lý |
|---|---|---|
| Expected lag | v1 revision 9, v2 revision 8, event E9 còn queue | Chờ theo budget/alert khi quá lâu |
| Missing target | ID A chưa có sau watermark | Targeted backfill/replay |
| Extra target | v1 đã xóa B, v2 còn B | Replay delete/tombstone |
| Same-revision difference | Cùng revision nhưng amount khác | PAUSE cutover, kiểm tra mapper |
| Target ahead | v2 revision 10, v1 9 khi v1 authoritative | Truy tìm unauthorized writer |
| Unknown state | `state:"refunded"` chưa được map | Quarantine + migration rule |
| Precision mismatch | Date/Decimal bị đổi không đúng | Sửa normalization/transform |
| Count mismatch tạm thời | Dữ liệu đổi khi đếm | So cùng watermark |

### 20.1. Không chọn last-write-wins tùy tiện

Đối với payment, inventory và workflow, “timestamp lớn hơn thắng” có thể che double charge hoặc hủy đơn sai. Reconciliation phải theo domain rules với audit trail, review và khả năng dừng tự động sửa.

### 20.2. Sửa mismatch cũng phải idempotent

Reconciliation worker có thể crash/retry; giữ stable IDs, version guard và nhật ký đã sửa. Không biến script đối soát thành writer thứ ba không có authority.

## 21. GO/NO-GO gates

Một tập ngưỡng **chỉ mang tính minh họa**:

~~~yaml
cutoverGates:
  checkpointHealthy: true
  maxP99ApplyLagSeconds: 2
  missingKeysAtVerifiedWatermark: 0
  sameRevisionCanonicalMismatch: 0
  unknownStateMappings: 0
  targetIndexesReady: true
  maxP95LatencyRegressionPercent: 10
  oldWriterFencingReady: true
  rollbackRehearsalPassed: true
~~~

Không lấy 2 giây và 10% làm mặc định sản phẩm. Ngưỡng phải xuất phát từ SLA/read consistency, business risk và throughput.

### 21.1. Freshness và coverage của metrics

Exporter chết có thể khiến dashboard hiện 0 errors. Gate phải kiểm tra tuổi lần đo, độ bao phủ theo tenant/shard, số samples và trạng thái collector. **Thiếu dữ liệu đo không được tính PASS**.

### 21.2. Không chỉ average

Một canary 1% có thể chỉ chạm một shard khỏe. Theo dõi p95/p99 theo cohort, read path, update/delete và nhóm documents hiếm.

### 21.3. Auto-pause

Nếu lag tăng liên tục, checkpoint đứng yên, mismatch same-revision xuất hiện hoặc target p99 xấu: dừng tăng rollout, trả canary reads về v1 nếu an toàn, điều tra và reconcile trước khi resume.

## 22. Canary reads theo nhóm ổn định

~~~text
0%  v2 reads: shadow only
1%  v2 reads: internal/low-risk users
5%  v2 reads: representative cohort
25% v2 reads: mở rộng sau gates
50% v2 reads: theo dõi theo shard/tenant
100% v2 reads: chỉ khi contract nhất quán cho phép
~~~

Phần trăm mang tính minh họa, không phải lịch bắt buộc.

### 22.1. Sticky routing

Dùng stable hash của tenant/user và rollout salt để chọn cohort. Nếu một user ngẫu nhiên lúc đọc v1, lúc đọc v2, CDC lag có thể khiến UI “lúc thấy/lúc không”. Không cho frontend tự bật `source=v2` mà bỏ qua authorization.

### 22.2. Read-your-writes

Nếu POST ghi v1 thành công rồi GET ngay được canary sang v2, chưa chắc GET thấy order. Các hướng:

1. Route reads sau write về v1 trong một phiên đủ ngắn/cho tới khi target đạt watermark.
2. Chờ v2 catch-up theo operation watermark với deadline.
3. Không canary các read paths cần immediate consistency.
4. Chuyển authority cho từng tenant theo một protocol atomic/fencing riêng, nếu cần.

CDC lag thấp theo trung bình **không đồng nghĩa** mọi request có bảo đảm read-your-writes.

### 22.3. Read canary khác write canary

Cho 5% reads từ v2 khi writes vẫn ở v1 là tương đối dễ đảo. Cho 5% writes tới v2 có thể tạo hai đường authority trừ khi routing per aggregate/tenant và đồng bộ được thiết kế nghiêm ngặt.

## 23. Feature flags và routing epochs

Một cấu hình control plane có thể:

~~~text
routingMode = V1_ONLY | SHADOW_V2 | V2_READ_CANARY | V2_PRIMARY
readCanaryPercent = 5
cutoverEpoch = 42
~~~

Java mô tả:

~~~java
enum RoutingMode {
    V1_ONLY, SHADOW_V2, V2_READ_CANARY, V2_PRIMARY
}

// Pseudocode: security, repositories và lifecycle được quản lý riêng.
Order readOrder(String tenantId, String id, RoutingConfig cfg) {
    if (cfg.mode() == RoutingMode.V1_ONLY) {
        return readV1(tenantId, id);
    }
    if (cfg.mode() == RoutingMode.SHADOW_V2) {
        scheduleBoundedShadowCompare(tenantId, id);
        return readV1(tenantId, id);
    }
    if (cfg.mode() == RoutingMode.V2_READ_CANARY &&
            !isStableCanaryTenant(tenantId, cfg.canaryPercent())) {
        return readV1(tenantId, id);
    }
    return readV2(tenantId, id);
}
~~~

### 23.1. Feature flag không chặn in-flight writes

Khi thay flag, một request cũ có thể đã chọn v1 và đang chạy. Một worker có cached config cũng có thể tiếp tục. Write cutover cần drain/fencing/permission enforcement được **mọi write paths** tuân thủ.

### 23.2. Ghi audit config

Lưu config revision, epoch, percent, tenant cohort, ai phê duyệt, thời điểm đổi, các instances đã nhận config và lý do rollback.

## 24. Chuyển quyền ghi: thứ tự an toàn

Một runbook tham khảo:

1. Freeze deploy/config không liên quan; thông báo cutover.
2. Xác nhận CDC v1→v2 healthy và parity gates đạt.
3. Tạm ngưng admission writes hoặc nhận bằng **durable queue** có deadline/ack policy rõ.
4. Drain in-flight v1 writes; reconcile requests có unknown outcomes.
5. Fence old writers, gồm APIs, background consumers, cron jobs và admin scripts.
6. Chốt source watermark W.
7. Đợi v2 apply đầy đủ changes qua W, gồm deletes và relevant transactions.
8. Chạy final parity/invariant checks ở boundary đã định nghĩa.
9. Đổi routing epoch để v2 thành authoritative.
10. Mở writes mới tới v2, kiểm tra bằng stable request IDs và smoke tests.
11. Mở traffic theo kế hoạch, giữ khả năng reverse-sync và giám sát.

### 24.1. Fencing không chỉ là flag

`cutoverEpoch=42` trên dashboard không ngăn một scheduled script có credentials ghi trực tiếp v1. Cần enforcement tại write gateway/lease protocol/quyền mạng hoặc policy mà mọi writers phải qua; đồng thời theo dõi attempts từ phiên cũ.

### 24.2. Không dùng `Thread.sleep(30000)` làm gate

Đợi 30 giây không chứng minh queue trống hay target đã apply đủ. Dùng observed state: in-flight requests, acknowledged writes, watermarks, checksum và deadline.

### 24.3. Durable queue đúng nghĩa

Nếu ứng dụng trả success trước khi request được lưu bền, crash có thể làm mất một acknowledged write. Cần định nghĩa khi nào queue acknowledge, backpressure và xử lý timeout.

## 25. Cutover watermark: sơ đồ thời gian

~~~mermaid
sequenceDiagram
    participant API as Write ingress
    participant V1 as MongoDB v1
    participant CDC as CDC worker
    participant V2 as MongoDB v2
    API->>API: Pause/drain
    API->>V1: Complete inflight writes
    V1-->>API: Acknowledged outcomes
    API->>CDC: Capture source watermark W
    CDC->>V2: Apply through W
    V2-->>CDC: Durable apply + parity
    CDC-->>API: Target caught up to W
    API->>API: Fence old writers, flip epoch
    API->>V2: Resume write traffic
~~~

### 25.1. Unknown outcomes

Một lệnh trả timeout có thể đã commit ở v1. Không coi nó thất bại để chốt watermark: kiểm tra idempotency ledger, request identity hoặc source state theo business contract.

### 25.2. Writes bị chặn giữa cutover

Nếu ingress từ chối, trả lỗi có retry policy rõ; nếu queue, queue phải đủ bền và giới hạn để không làm mất những requests mà hệ thống đã nhận trách nhiệm.

### 25.3. Sau khi mở writes v2

Nếu smoke test lỗi, rollback **không còn chỉ là đổi flag** nếu đã có bất kỳ acknowledged write mới ở v2. Phải dùng post-cutover rollback plan.

## 26. Theo dõi sau khi v2 nhận writes

Đọc/ghi 100% ở v2 vẫn chưa có nghĩa migration đã kết thúc:

- Đối soát cả **new writes**, không chỉ dữ liệu cũ đã backfill.
- Theo dõi reverse-sync backlog nếu rollback plan yêu cầu.
- Cảnh báo old writer attempts và thay đổi ngoài epoch được phép.
- Giữ source/compatibility code qua rollback window.
- Kiểm tra performance, index plans, p95/p99, errors và resource budgets.
- Chuyển cache, search, event consumers, reports và data warehouse.
- Duy trì backup/PITR và runbook mới.

### 26.1. Không drop nguồn cũ ngay

V1 còn hữu ích cho rollback, audit và điều tra sai lệch. Chỉ xóa sau khi không còn dependencies, hết rollback window, các gates hậu cutover đạt và có approvals.

### 26.2. Không dùng snapshot restore như undo nút đổi traffic

Restore snapshot có thể xóa những writes hợp lệ sau thời điểm backup. Data rollback cần xử lý **acknowledged writes đã phát sinh sau cutover**, không chỉ restore một image cũ.

## 27. Định nghĩa rollback đúng phạm vi

Có bốn lớp:

1. **Traffic rollback:** trả read/write routing về đường cũ.
2. **Application rollback:** deploy code phiên bản cũ.
3. **Data rollback:** đảm bảo source cũ có đủ những thay đổi mới cần thiết.
4. **Infrastructure rollback:** khôi phục DNS, network, credentials, endpoints hoặc clusters.

### 27.1. Trước khi chuyển writes

Khi v1 còn authoritative và canary chỉ đọc v2, tắt canary và trả reads về v1 thường tương đối dễ, miễn không có side effect phụ ở v2.

### 27.2. Sau khi chuyển writes

Một order được v2 xác nhận lúc 10:05 nhưng v1 không có. Quay reads/writes về v1 lúc 10:06 sẽ khiến khách không thấy order đó. Phải reverse-sync/reconcile hoặc forward-fix theo một quyết định có RPO/RTO.

### 27.3. Xóa source/contract

Sau khi bỏ schema cũ, feature mới có thể không chuyển ngược được. Rollback đầy đủ có thể đòi data transformation phức tạp hoặc không còn khả thi; đánh dấu contract là một **mốc gần như không đảo ngược** nếu chưa có khôi phục đặc biệt.

## 28. Ma trận rollback theo pha

| Pha | Hành động có thể thực hiện | Độ phức tạp |
|---|---|---|
| BACKFILL | Dừng job, giữ v1 authoritative | Thấp |
| SHADOW | Tắt shadow, tiếp tục v1 | Thấp |
| READ_CANARY | Đổi reads về v1, kiểm tra caches | Thấp–vừa |
| WRITE_CUTOVER | Fence writes, reverse-sync từ v2→v1, xác minh | Cao |
| STABILIZE | Reconcile writes mới, backward compatibility | Cao |
| CONTRACT | Forward-fix/rebuild/restore tùy khả năng | Rất cao |

Không gộp tất cả thành một nút “Rollback” mà không kiểm tra đã có writes mới ở v2 chưa.

## 29. Reverse CDC để giữ khả năng quay lại

Trước cutover:

~~~text
v1 authoritative → CDC v1→v2
~~~

Sau cutover (nếu yêu cầu rollback):

~~~text
v2 authoritative → reverse CDC v2→v1
~~~

Reverse sync cần deterministic reverse transform, stable IDs, revision mapping, idempotent apply, ordered events, tombstones, checkpoint lag và dead-letter handling.

### 29.1. Chống replication feedback loop

Nếu cả hai streams cùng mirror mọi update, event v2→v1 có thể phát event v1→v2 rồi lặp. Phân biệt origin/epoch, vô hiệu hóa hướng không còn authority hoặc dùng một protocol có loop suppression được kiểm thử.

### 29.2. Mã hóa trạng thái mới

V2 có `PARTIALLY_REFUNDED` nhưng v1 không hiểu. Reverse transform không thể lossless nếu không bổ sung representation. Các lựa chọn: khóa feature mới tới hết rollback window, lưu supplemental data, mở rộng schema v1 hoặc chấp nhận forward-fix có kiểm soát.

### 29.3. Kích thước backlog

Nếu reverse queue có 20 triệu events, “rollback trong 5 phút” có thể không thực tế. Đo apply throughput, bandwidth, target index pressure và backlog aging trước cutover.

## 30. Runbook rollback sau khi có writes ở v2

1. Tuyên bố incident; chỉ định incident commander, communication channel và quyết định rollback/forward-fix.
2. Dừng tăng traffic, tạm chặn/queue writes có deadline và durability policy.
3. Fence các writes v2 ở epoch cũ để xác lập boundary.
4. Chốt watermark của **mọi acknowledged writes ở v2**; reconcile unknown outcomes.
5. Reverse CDC/replay đến watermark hoặc repair data có kiểm soát.
6. Đối soát IDs, revisions, business fields, deletes và invariants ở v1.
7. Kiểm tra v1 indexes, validation, query plans, compatibility với code rollback.
8. Chỉ sau khi gate đạt, đổi authority/routing về v1 và xác nhận old/new writers không chồng nhau.
9. Mở traffic theo nhóm nhỏ/plan khẩn cấp; theo dõi error rate và latency.
10. Giữ v2 và logs để điều tra, không drop ngay; ghi các request IDs chưa resolved.

### 30.1. Nếu reverse sync không kịp

Không tự flip về v1 vì áp lực thời gian. Có thể giữ v2 và chuyển read-only, giới hạn tính năng hoặc forward-fix; phương án phụ thuộc RPO/RTO đã phê duyệt. Nếu chấp nhận mất acknowledged writes, đó phải là **quyết định tác động dữ liệu được phê duyệt rõ**, không phải thao tác vận hành thông thường.

### 30.2. Cache và downstream state

Rollback routing MongoDB không tự invalidate Redis cache, search indexes, warehouse snapshots và event consumers dùng v2. Runbook phải chuyển/version/invalidate các read models tương ứng.

## 31. RPO, RTO và rollback window

- **RPO:** lượng dữ liệu mất tối đa chấp nhận được trong phục hồi.
- **RTO:** thời gian phục hồi dịch vụ chấp nhận được.
- **Rollback window:** khoảng thời gian còn đủ source data, compatibility, CDC history, recovery capacity và nhân sự để quay lại.

Ví dụ **không phải mặc định**:

~~~text
RPO: zero acknowledged orders lost
RTO: 15 minutes read-only at most
Rollback window: 72 hours after cutover
~~~

### 31.1. RPO=0 không đạt bằng backup mỗi 15 phút

Nếu restore backup cũ hơn những writes đã được xác nhận, bạn mất dữ liệu. RPO=0 cần cơ chế bảo toàn tất cả acknowledged writes trong phạm vi và topology có thể chứng minh.

### 31.2. Giữ v1 72 giờ chưa đủ

Nếu v1 không nhận reverse changes, nó sẽ càng cũ. Rollback window cần **dữ liệu được đồng bộ, runbook, code tương thích và năng lực replay**.

## 32. Khi nào forward-fix tốt hơn rollback?

| Tình huống | Điều cần cân nhắc |
|---|---|
| v2 thiếu index, có thể xây/sửa nhanh | Forward-fix có thể ít rủi ro hơn reverse millions writes |
| Mapping sai một field nhưng có source record | Pause/repair target + verify có thể đủ |
| v2 đã có trạng thái không biểu diễn ở v1 | Rollback dễ mất thông tin |
| v2 outage kéo dài, v1 đã reverse-sync đủ | Rollback theo watermark có thể phù hợp |
| Có dấu hiệu double charge hoặc mất ledger | Business incident; dừng flow nhạy cảm và reconcile |

Quyết định không chỉ dựa vào latency. Cần xem data-loss risk, effects bên ngoài MongoDB, RPO/RTO, compatibility và thời gian khôi phục thật.

## 33. Cross-cluster và sharding

Hai clusters có thể khác server version/FCV, indexes, shard keys, distribution, TLS, roles, timeouts, read/write concerns và region network latency.

### 33.1. Không có cross-cluster atomic commit mặc định

Một source write có thể thành công khi target không có. Nếu dùng dual writes trực tiếp, app cần xử lý partial success; một durable outbox/CDC với authority rõ thường dễ kiểm chứng hơn.

### 33.2. Cluster times và resume tokens

Không lấy source clusterTime làm đồng hồ chung tùy tiện hoặc dùng source resume token ở target stream. Định nghĩa migration checkpoints theo source stream và mapping tiến độ áp dụng vào target.

### 33.3. Shard key và uniqueness

Nếu đổi shard key, query routing và unique index constraints có thể thay đổi. Chỉ copy documents không đủ; cần kiểm thử uniqueness, chunk distribution, cross-shard query latency và data access tại mongos.

## 34. Consumers phụ thuộc schema cũ

Những đường phụ thuộc thường bị bỏ quên:

- Redis caches/materialized views.
- Search indexing và CDC consumers.
- ETL vào warehouse, BI dashboards.
- Outbox/event schemas và notification services.
- Scheduled workers cũ chứa hardcoded collection name.
- Export scripts/BI account có quyền chỉ đọc v1.

### 34.1. Tất cả đều là một phần cutover

API đọc v2 trong khi báo cáo vẫn lấy v1 có thể cho hai nguồn dữ liệu trái nhau. Lập inventory readers/writers, chuyển theo kế hoạch và đối soát kết quả.

### 34.2. Đừng dual publish business event tùy tiện

Một logical order update có thể phát ở cả v1/v2 change streams; nếu Kafka consumers xử lý cả hai, side effects có thể lặp. Cần event identity, schema version và dedupe.

## 35. Dấu hiệu phải pause rollout

| Dấu hiệu | Lý do |
|---|---|
| CDC checkpoint không tiến | Worker lỗi/poison event |
| Oplog retention không đủ | History gap, resume fail |
| Target behind tăng liên tục | Không còn catch-up |
| Same-revision mismatch | Sai mapping/transform |
| Target ahead khi v1 authoritative | Writer ngoài policy |
| Delete resurrection | Tombstone/order lỗi |
| Unexpected old writers sau cutover | Split-brain authority |
| P99 hoặc error rate tăng | SLO bị ảnh hưởng |
| Unique index thiếu hoặc duplicate IDs | Business invariant không được bảo vệ |
| Metrics freshness mất | Không đủ bằng chứng để GO |

Không “tự sửa” bằng last-write-wins khi chưa xác định authority. Pause, giữ diagnostic metadata/redacted samples, truy nguyên nguyên nhân và reconcile.

## 36. Dashboard cần bao phủ những gì?

~~~text
Traffic:
  read_v1/read_v2, write_v1/write_v2, canary cohort, routing epoch
Data:
  missing_keys, extra_keys, canonical_mismatch, target_revision_ahead
  target_revision_behind, pending_deletes, business_invariants
Pipeline:
  capture_lag, queue_depth, apply_lag, checkpoint_age
  retry_count, poison_events, oplog_window_remaining
Application:
  errors, p95/p99, timeouts, connection_pool_wait
Safety:
  old_writer_attempts, in_flight_writes, reverse_sync_lag
~~~

### 36.1. Theo tenant và shard

Average toàn hệ thống có thể che lỗi của một tenant quan trọng hoặc một shard. Gắn nhãn cohort, deployment version, writer type, namespace và cluster để điều tra.

### 36.2. Missing metrics không phải success

Nếu exporter lỗi, 0 mismatch có thể chỉ là không có dữ liệu. Gate cần tự báo lỗi nếu không có samples mới.

## 37. Runbook trước giờ cutover

1. Xác nhận cluster IDs, namespace, credentials, owners và recovery contacts.
2. Kiểm tra last backup/PITR và diễn tập restore phù hợp.
3. Xác minh backfill/CDC checkpoints và oplog headroom.
4. So key parity, canonical content, deletes và business invariants.
5. Kiểm tra target indexes, validators, TTL, read/write concerns.
6. Chạy synthetic APIs ở v2 với dữ liệu không nhạy cảm.
7. Hoàn tất shadow/canary SLO gates.
8. Test feature flag rollback khi writes vẫn ở v1.
9. Diễn tập write drain/fencing/reverse sync.
10. Ghi rõ GO/NO-GO, ai phê duyệt và freeze window.

### 37.1. Bằng chứng cần lưu

Config revision, canary cohort, binary versions, source/target watermarks, parity report, open issues, rollback drill result, throughput estimate và người chịu trách nhiệm.

## 38. Runbook write cutover

~~~text
1. Declare cutover started
2. Pause admission or durable queue
3. Drain source writes; reconcile uncertain outcomes
4. Fence old writers
5. Record source watermark W
6. Wait for target catch-up to W
7. Verify parity/invariants at W
8. Set v2 authoritative routing epoch
9. Controlled new writes with stable request IDs
10. Reopen traffic and monitor
~~~

### 38.1. Nếu fail trước bước 8

Không mở write traffic v2. Giữ/reopen source v1 theo protocol và xử lý queue/rejections. Điều tra checkpoint/mismatch.

### 38.2. Nếu fail sau bước 9

Đã có thể có acknowledged writes ở v2. Dùng **post-write-cutover rollback plan** chứ không flip flag về v1 tức thời.

## 39. Giai đoạn stabilize và exit criteria

Trong những ngày đầu sau cutover:

1. Giám sát read/write latency p50/p95/p99, error rate, connection pools, CPU, I/O và slow query plans.
2. Đối soát cả historical records và những **writes chỉ xuất hiện sau cutover**.
3. Kiểm tra CDC/reverse CDC nếu rollback plan cần, gồm checkpoint age và tombstones.
4. Alert old-writer attempts, unauthorized target writes và routing epoch conflicts.
5. Kiểm tra tenant isolation, financial totals, status transitions và business reports.
6. Theo dõi search/cache/warehouse consistency và event consumers.
7. Giữ source, compatibility code và rollback owners trong rollback window.
8. Không bật các schema/business features không đảo được nếu reverse transform chưa sẵn sàng.

### 39.1. Khi nào được CONTRACT?

Chỉ dọn schema/source cũ khi:

- Không còn writers/consumers dựa vào v1.
- Hết rollback window hoặc có chấp thuận rõ ràng.
- Không còn unresolved mismatch/unknown business outcome.
- SLO đã ổn định qua workload representative.
- Có backup/PITR và disaster recovery plan cho v2.
- Docs, runbooks, monitoring và ownership đã chuyển sang hệ thống mới.

### 39.2. Xóa source là một thay đổi độc lập

Không gộp “đổi reads”, “đổi writes”, “xóa v1” vào một deploy không thể dừng giữa chừng. Cleanup nên là một bước thay đổi riêng có review, retention và backup approval.

## 40. Diễn tập rollback trước production

Trong staging hoặc test cluster đại diện:

1. Tạo v1 với historical records, including edge-case states, deletes và revisions.
2. Bật CDC, chạy backfill, verify parity.
3. Bật shadow reads, rồi canary.
4. Thực hiện cutover writes với drain/watermark/fencing.
5. Phát sinh **những orders được xác nhận mới ở v2**, không có trong v1 ban đầu.
6. Giả lập lỗi v2 nghiêm trọng.
7. Chốt v2 acknowledged watermark và chạy reverse CDC.
8. Đối soát v1 đã có đủ những orders mới, updates và deletes.
9. Đổi authority về v1, mở đọc/ghi có kiểm soát.
10. Xác nhận không mất acknowledged orders, không duplicate ledger và không resurrect deleted records.
11. Đo replay duration/incident workflow so với RTO/RPO.

### 40.1. Test có tính đúng

Nếu v1 sau rollback có đủ count nhưng trạng thái SHIPPED bị lùi về PAID, rehearsal **chưa đạt**. So canonical fields và revisions, không chỉ row count.

### 40.2. Test vận hành

Runbook cần thực thi được bởi on-call có quyền phù hợp. Diễn tập cả credentials, feature flag propagation, cache invalidation và dashboards, không chỉ câu lệnh MongoDB.

## 41. Fault injection: crash ở các điểm quan trọng

| Điểm crash | Kỳ vọng sau restart |
|---|---|
| Trước target apply | Event còn trong stream/queue, được xử lý lại |
| Sau target apply, trước checkpoint | Event có thể replay nhưng không nhân đôi effect |
| Sau checkpoint an toàn | Không mất event đã cam kết và không bỏ event trước đó |
| Trong xử lý delete | Không resurrect bản ghi từ backfill cũ |
| Sau revision mới, trước backfill cũ | Revision không bị lùi |
| Trong read canary | Có thể trả về v1 theo safety policy |
| Sau write cutover, trước reverse catch-up | Không tuyên bố rollback an toàn |
| Khi old writer vẫn active | Attempt bị fence hoặc được phát hiện/reconcile |

### 41.1. Kiểm thử lịch sử stream bị mất

Trong môi trường thử nghiệm có quyền, mô phỏng CDC tạm dừng tới khi history không còn có thể resume. Expected behavior là **PAUSE + ALERT + RESYNC**, không tự bỏ qua khoảng thiếu.

### 41.2. Kiểm thử network partition

Nếu application mất kết nối sau khi source commit nhưng trước response, outcome có thể chưa biết. Reconcile bằng stable requestId/ledger trước khi retry một command tạo side effect.

### 41.3. Kiểm thử CDC trong sharded cluster

Test khi chunks di chuyển, topology failover, stream bị resume và routing ở mongos. Không giả định một mongod standalone test đủ chứng minh behavior cross-shard.

## 42. Tình huống rollback “không thể làm chỉ bằng cờ”

Giả sử:

~~~text
10:00 v1 authoritative; v2 bắt kịp
10:01 write cutover -> v2 authoritative
10:05 v2 nhận 5.000 orders mới, ack thành công
10:06 target p99 tăng do index thiếu
10:07 đề xuất đổi source từ v2 về v1
~~~

Nếu v1 không có 5.000 orders mới, flip về v1 khiến API không tìm thấy chúng. Một lựa chọn:

1. Dừng ghi v2 có kiểm soát, chốt watermark cuối.
2. Reverse-sync những orders/updates/deletes mới tới v1.
3. Kiểm tra unique/foreign keys và canonical parity.
4. Chỉ sau khi v1 đã sẵn sàng, đổi writes/reads về v1.

Một lựa chọn khác là giữ v2 authoritative và **forward-fix index**, nếu an toàn và nhanh hơn replay ngược. Quyết định dựa trên RPO/RTO, tính đúng nghiệp vụ và khả năng khôi phục, không chỉ thao tác nhanh nhất trên dashboard.

## 43. Những bài học về transaction và consistency

### 43.1. Cùng deployment không có nghĩa mọi cutover atomic

MongoDB transactions có thể giúp nhiều writes dữ liệu trong một deployment commit cùng nhau, nhưng thay flag routing của hàng trăm service instances **không tự là một MongoDB transaction**. In-flight requests, cached config và external consumers vẫn cần coordination.

### 43.2. Hai clusters không có distributed snapshot tự động

Đọc v1 rồi v2 gần như cùng lúc không đảm bảo hai phía cùng một logical time. Hãy so theo source watermark và versioned records thay vì coi một phép Promise.all là snapshot.

### 43.3. Majority không thay event ordering

Write concern majority là một chính sách acknowledgement/durability trong replication, không khiến event cũ đến muộn tự bị chặn trên target. Version guard, per-key sequencing và checkpoints vẫn quan trọng.

### 43.4. Backup không thay CDC

Snapshot/PITR phục vụ recovery, không tự bắt từng change trong live backfill. Cần lựa chọn công cụ sao chép/capture phù hợp với topology và mục tiêu RPO.

## 44. Bài thực hành A — thiết kế state machine

Tạo sơ đồ phases PREPARE, BACKFILL, CATCH_UP, SHADOW, CANARY_READ, WRITE_CUTOVER, STABILIZE, CONTRACT. Với mỗi phase, ghi rõ:

- Source of truth.
- Read path.
- Write path.
- CDC direction.
- GO/NO-GO criteria.
- Rollback cần reverse sync hay không.

## 45. Bài thực hành B — schema mapping

Cho v1 có `amountCents`/`state` và v2 có `totalMinor`/`status`. Viết deterministic mapping bảo toàn tiền, ID, tenant và revision. Bổ sung trường hợp v1 `state:"refunded"` chưa được map; cần xử lý thế nào mà không âm thầm đổi thành PENDING?

## 46. Bài thực hành C — backfill và CDC

Backfill mất 2 giờ, source phát sinh 200 changes mỗi phút. Tính tổng changes minh họa, giải thích nguy cơ nếu change stream chỉ được bật sau khi copy hoàn thành. Thiết kế checkpoint trước backfill và replay idempotent theo revision.

## 47. Bài thực hành D — checkpoint sau crash

CDC apply E10 thành công vào v2 rồi crash trước khi lưu resume token. Khi restart, E10 được gửi lại. Kỳ vọng nào đúng? Nếu checkpoint đã được lưu trước khi target apply E10 thì điều gì có thể xảy ra?

## 48. Bài thực hành E — revision cũ tới muộn

CDC ghi order revision 9, sau đó batch backfill chứa revision 7 tới target. Vì sao unconditional replace gây regression? Viết logic CAS/skip/no-op cho incoming revisions nhỏ hơn, bằng và lớn hơn current revision.

## 49. Bài thực hành F — delete resurrection

Source đã xóa order O-10. Target nhận delete nhưng một backfill batch cũ chứa O-10 vẫn đang xử lý. Đề xuất tombstone/version sequence để ngăn tạo lại order. Trường hợp change stream delete không có version riêng thì phải thiết kế gì?

## 50. Bài thực hành G — shadow canary

Thiết kế thử nghiệm shadow 1% GET orders và canary reads 5%. Các yêu cầu:

- Response v1 ở shadow, v2 ở canary được chọn.
- Canonical diff với money/status/ID.
- Redacted logging, bounded shadow timeouts.
- Sticky cohort theo tenant.
- Đo read-your-writes violations.

## 51. Bài thực hành H — count parity sai

Hai collections đều có 1 triệu documents nhưng 300 IDs ở v1 không có trong v2 và 300 IDs khác ở v2 không có v1. Lập kế hoạch phân buckets/so keys/canonical hashes để tìm sai lệch. Vì sao chỉ xem dashboard count sẽ bỏ sót?

## 52. Bài thực hành I — quyết định GO/NO-GO

Giả sử:

~~~text
CDC p99 lag = 1.2s
Same revision diffs = 0
Missing keys = 0
Target p99 latency = 2x baseline
Rollback rehearsal = chưa hoàn thành
~~~

Có nên bật 100% writes sang v2 ngay không? Nêu ít nhất hai gate chưa đạt, cách pause và cách điều tra.

## 53. Bài thực hành J — old writer sau cutover

API pods đã chuyển v2, nhưng một cron job cũ vẫn ghi v1 trong 10 phút. Hãy xác định split-brain, cách phát hiện old-writer attempts, cơ chế fencing và cách reconcile writes đã lọt qua trong khi không phá những writes mới ở v2.

## 54. Bài thực hành K — rollback sau v2 commits

v2 đã nhận 5.000 đơn hàng được acknowledge. Một người muốn đổi feature flag về v1 ngay. Viết runbook bảo toàn 5.000 đơn và kiểm tra reverse-sync watermark. Nếu v2 chỉ bị query chậm do index, khi nào forward-fix hợp lý hơn rollback?

## 55. Bài thực hành L — reverse transform không lossless

v2 cho phép `PARTIALLY_REFUNDED`, v1 chỉ biết PAID/REFUNDED. Nêu ba phương án xử lý để vẫn giữ rollback readiness và hệ quả nếu không có cách biểu diễn trạng thái mới trong v1.

## 56. Bài thực hành M — fault injection

Giả lập lỗi ở ba thời điểm:

1. Sau target write, trước checkpoint.
2. Trong xử lý delete, trước khi tombstone được lưu bền.
3. Sau cutover, trước khi reverse CDC bắt kịp.

Với từng tình huống, viết hậu điều kiện cần được xác minh sau recovery.

## 57. Bài thực hành N — kế hoạch quan sát

Thiết kế dashboard có:

- Lưu lượng read/write theo v1/v2 và routing epoch.
- Capture/apply lag, checkpoint age và oplog headroom.
- Missing/extra keys, same-revision mismatch, target ahead.
- Old-writer attempts, tombstones, rollback sync lag.
- API p95/p99, timeout/error rates, business invariants.

Định nghĩa ít nhất một ngưỡng auto-pause và một tình huống incident commander phải quyết định rollback hoặc forward-fix.

## 58. Gợi ý đáp án thực hành

**A:** Trước WRITE_CUTOVER, v1 authoritative nên rollback đọc thường không cần reverse-sync; sau WRITE_CUTOVER, v2 authoritative và quay writes về v1 chỉ an toàn khi dữ liệu mới đã được đồng bộ ngược/đối soát.

**B:** Mapping giữ stable `_id`/tenant/revision/money units; unknown status phải quarantine/alert, mở rộng mapping có kiểm thử, không gán default gây sai nghiệp vụ.

**C:** 2 giờ × 60 phút × 200 changes/phút = **24.000 changes** minh họa. CDC cần bắt từ mốc trước cửa sổ scan; nếu mở sau, các changes trung gian có thể mất.

**D:** Apply rồi crash trước token khiến E10 replay; idempotency guard khiến business effect không lặp. Checkpoint trước apply có nguy cơ bỏ E10 hoàn toàn.

**E:** Unconditional replace làm v2 lùi 9→7. Với incoming nhỏ hơn: skip; bằng: no-op nếu canonical equal, nếu khác thì conflict; lớn hơn: CAS apply.

**F:** Tombstone mang sequence/revision cao hơn bản backfill cũ; delete event thiếu revision cần protocol sequence/ordering để biết thứ tự authoritative.

**G:** Shadow không ảnh hưởng HTTP response; canary dùng stable cohort và kiểm tra consistency. So sánh cần canonical fields + watermark, không log PII.

**H:** Count bằng nhưng key sets khác; chia ranges, so missing/extra IDs và content hashes/canonical fields ở verified watermark.

**I:** NO-GO vì p99 regression và rollback rehearsal chưa đạt; pause rollout, điều tra query/index/network, diễn tập rollback và đo lại.

**J:** Writer cũ tạo writes ở nguồn không còn authoritative; fence/deny theo epoch/permissions, đo writes lọt qua và reconcile theo business ordering, không overwrite v2 tùy tiện.

**K:** Không flip về v1 nếu thiếu 5.000 acknowledged orders; fence v2, reverse-sync đến watermark, verify keys/revisions/invariants, rồi cutover ngược. Nếu chỉ thiếu index có thể sửa an toàn nhanh, forward-fix ít rủi ro hơn.

**L:** Khóa feature mới trong rollback window, mở rộng schema v1 hoặc giữ supplemental representation, hay chọn forward-fix; không tuyên bố reverse transform lossless nếu v1 không biểu diễn đủ.

**M:** Replay không duplicate effect; deletes không resurrect; rollback phải giữ mọi acknowledged writes đã phát sinh ở v2.

**N:** Dashboard phải có freshness/coverage và alerts; pause khi lag/mismatch/latency vượt gates, điều tra. Business invariant breach như double charge/mất confirmed order cần incident và quyết định có phê duyệt.

## 59. Những lỗi thường gặp

| Sai lầm | Hậu quả | Sửa bằng |
|---|---|---|
| Copy xong rồi mới mở CDC | Mất writes trong lúc copy | Capture trước backfill |
| Chỉ so count | Missing/extra IDs bị che | Key/content parity |
| Backfill replace không revision | Ghi đè trạng thái mới | CAS/version guard |
| Checkpoint trước apply | Event bị bỏ sau crash | Durable apply rồi checkpoint |
| Parallel checkpoint theo worker nhanh nhất | Bỏ event đang lỗi | Contiguous watermark |
| Bỏ delete events | Resurrect documents | Tombstones/ordered deletes |
| Dùng updatedAt không đáng tin làm authority | Last-write-wins sai nghiệp vụ | Monotonic version/domain policy |
| Shadow queries blocking | p99 của v1 tăng | Bounded async shadow |
| So raw JSON hai schemas khác nhau | False mismatches | Canonical comparison |
| Shadow logging PII | Rò rỉ data | Redact/hash IDs và fields |
| Canary random mỗi request | UI inconsistent | Sticky cohorts |
| Không xử lý read-your-writes | POST xong GET không thấy | Route v1/chờ watermark |
| Gửi hai writes nhưng không có source truth | Divergence | One authority + CDC/outbox |
| Chỉ đổi flag, không drain | In-flight old writes | Fencing/watermark |
| Quên scheduled writers | Split-brain | Inventory/fence mọi write paths |
| Missing metrics thành green | Cutover sai thời điểm | Monitor freshness/coverage |
| Snapshot restore xem như rollback hoàn chỉnh | Mất writes mới | Reverse sync/RPO |
| Flip về v1 sau v2 commits | Disappear acknowledged data | Backfill ngược trước flip |
| Hai chiều mirror không chống loop | Replication storm | Epoch/origin loop suppression |
| Xóa v1 ngay khi reads 100% v2 | Không còn fallback | Contract sau rollback window |
| Reverse transform không bao phủ trạng thái mới | Mất thông tin | Compatibility/forward-fix |

## 60. Câu hỏi ôn tập

**1. Data copy xong là migration hoàn thành?** — Không; còn CDC, parity, cutover, stabilization và rollback readiness.

**2. Source of truth là gì?** — Đường dữ liệu có thẩm quyền xác nhận và giải quyết business writes.

**3. Backfill khác CDC?** — Backfill sao chép lịch sử; CDC thu những changes phát sinh.

**4. Vì sao bắt CDC trước backfill?** — Tránh bỏ sót events trong cửa sổ scan.

**5. Change streams tự copy toàn bộ lịch sử trước đó?** — Không.

**6. Vì sao resume token phải lưu sau apply?** — Tránh checkpoint qua event chưa được target ghi bền.

**7. Apply event cần idempotent vì sao?** — Crash có thể làm event được replay.

**8. `updateLookup` luôn đúng post-image từng event?** — Không; có thể thấy state mới hơn.

**9. Backfill cũ đến sau CDC mới xử lý sao?** — So revision và skip/CAS, không ghi đè.

**10. Delete resurrection là gì?** — Bản ghi đã xóa bị stale event/backfill tạo lại.

**11. Count v1/v2 bằng nhau chứng minh parity?** — Không.

**12. Same-revision mismatch cần làm gì?** — Dừng cutover và điều tra transform/consistency.

**13. Target ahead khi v1 authoritative có đáng lo?** — Có thể là unauthorized writer/split-brain.

**14. Shadow reads là gì?** — Query v2 để compare, trả v1 cho user.

**15. Canary read khác write canary?** — Write canary đổi authority và khó rollback hơn nhiều.

**16. Read-your-writes có tự được đảm bảo với writes v1, reads v2?** — Không nếu CDC bất đồng bộ.

**17. Routing flag đã đổi là mọi old writer dừng?** — Không; cần fencing/drain/verification.

**18. Source watermark dùng làm gì?** — Xác định toàn bộ source changes phải có trên target trước cutover.

**19. Vì sao rollback sau write cutover phức tạp?** — V2 có acknowledged writes mà v1 chưa có.

**20. PITR snapshot restore có tự bảo toàn writes sau snapshot?** — Không.

**21. Reverse CDC cần chống điều gì?** — Out-of-order, duplicates, deletes, loss và feedback loops.

**22. Forward-fix là gì?** — Sửa v2 và tiếp tục giữ v2 authoritative thay vì quay traffic/data về v1.

**23. RPO=0 có nghĩa gì?** — Không chấp nhận mất acknowledged writes theo phạm vi được xác định.

**24. Hết rollback window nghĩa là có thể xóa v1 ngay?** — Chỉ sau khi verify dependencies, stabilization, backup và approval.

**25. Metric lag bằng 0 đã đủ GO?** — Không; còn parity, invariants, performance và observability health.

## 61. Bảng ghi nhớ nhanh

| Khái niệm | Quy tắc |
|---|---|
| Expand | App tương thích old/new |
| Backfill | Quét dữ liệu lịch sử có checkpoint |
| CDC | Theo dõi live changes và replay |
| Source of truth | Một write authority rõ trong từng pha |
| Shadow | So sánh v2 nhưng trả v1 |
| Canary | Cohort thật đọc v2 |
| Sticky cohort | Routing hash ổn định theo tenant/user |
| Read-your-writes | Route về source hoặc đợi watermark |
| Revision guard | Không ghi đè dữ liệu newer bằng stale |
| Tombstone | Ngăn records đã xóa bị resurrect |
| Resume token | Opaque checkpoint của stream |
| Contiguous watermark | Không bỏ event lỗi khi xử lý song song |
| Canonical diff | So sánh theo business schema |
| Cutover write | Drain → fence → W → catch-up → parity → flip |
| GO/NO-GO gate | Correctness, lag, performance và readiness |
| Reverse CDC | Đồng bộ v2→v1 sau đổi authority |
| Rollback window | Giữ data, code, CDC và runbook đủ để quay lại |
| Forward-fix | Chọn sửa v2 khi rollback rủi ro hơn |
| RPO/RTO | Mất dữ liệu/thời gian phục hồi chấp nhận được |
| Contract | Xóa old path sau stabilization |

## 62. Checklist triển khai production

- [ ] Source/target namespaces, clusters, owners được xác định?
- [ ] Đã inventory tất cả writers/readers/consumers và dependencies?
- [ ] Schema mapping/reverse mapping và unique business IDs rõ?
- [ ] Revision/sequence monotonic và delete semantics được thiết kế?
- [ ] Đã tạo indexes, validators, TTL, collation, permissions trên target?
- [ ] Backfill có batching, checkpoints, resume và idempotent apply?
- [ ] CDC bao phủ toàn bộ cửa sổ backfill và oplog history đủ?
- [ ] Resume tokens được lưu sau durable apply?
- [ ] Applicators giữ per-key ordering và contiguous progress?
- [ ] Tombstones tránh stale resurrection?
- [ ] Quarantine unknown mappings và target-ahead conflicts?
- [ ] Key/content parity được đo tại watermark cùng logic?
- [ ] Business invariants về tiền, trạng thái, uniqueness được kiểm tra?
- [ ] Metrics có sample freshness, tenant/shard coverage và alert?
- [ ] Shadow reads async, bounded và không log PII?
- [ ] Canary sử dụng stable cohort và được giám sát p95/p99?
- [ ] Read-your-writes policy có kiểm thử?
- [ ] Có GO/NO-GO gates rõ, owner có quyền dừng?
- [ ] Đã thử rollback đọc khi writes còn v1?
- [ ] Có kế hoạch drain/queue writes với durability và deadline?
- [ ] Đã tìm và fence tất cả old writers, kể cả scripts/cron?
- [ ] Chốt cutover watermark W và verify target apply tới W?
- [ ] Đã reconcile requests với unknown commit outcome?
- [ ] Có đủ reverse CDC để bảo vệ acknowledged writes mới ở v2?
- [ ] Reverse transform xử lý schema features mới hay đã freeze chúng?
- [ ] Rollback window, RPO/RTO và replay throughput đã xác minh?
- [ ] Có runbook hậu cutover, cache invalidation và downstream migration?
- [ ] Đã diễn tập crash/replay, deletes, out-of-order và split-brain?
- [ ] Có backup/PITR riêng của v2 và disaster recovery plan?
- [ ] Chỉ cleanup v1 sau khi không còn phụ thuộc và có approval?

## 63. Kết luận

Trong tiến hóa dữ liệu MongoDB, **chuyển lưu lượng không chỉ là thay connection string hay collection name**. Nó là quá trình thay đổi trách nhiệm về một business write đã được xác nhận ở đâu, đọc dữ liệu đủ mới từ nơi nào và hệ thống sẽ làm gì khi một phần di trú thất bại. Shadow/canary có thể chuyển dần reads, nhưng write cutover phải có **authority duy nhất, drain/fencing, watermark và kiểm chứng parity**.

Một bản sao mới chỉ đáng tin khi được đo bằng **key parity, canonical fields, revision, deletes, CDC lag, business invariants và SLO**, không chỉ bằng document count. Change streams, resume tokens và checkpoints giúp kết nối backfill với live writes, nhưng vẫn phải xử lý event replay, oplog gaps, out-of-order và stale backfill.

Cuối cùng, **rollback phải bảo toàn tất cả acknowledged business writes mới sau cutover**. Khi v2 đã nhận writes, quay lại v1 có thể yêu cầu reverse synchronization và reconciliation; có lúc forward-fix an toàn hơn. Chỉ hoàn tất contract và xóa v1 khi compatibility, rollback window, downstream consumers, backup và kế hoạch phục hồi đã được xác minh bằng diễn tập cùng bằng chứng vận hành.
