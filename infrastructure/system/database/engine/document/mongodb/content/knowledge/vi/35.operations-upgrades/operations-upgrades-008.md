# Quản lý thay đổi index, validator và cấu hình trên dữ liệu thật trong MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chương:** Vận hành và nâng cấp  
> **Bài học:** Quản lý thay đổi index, validator và cấu hình trên dữ liệu thật

## 1. Tình huống mở đầu: thay đổi nhỏ, tác động lớn

Một hệ thống đặt hàng đang chạy MongoDB replica set với hàng chục triệu document. Đội phát triển muốn thực hiện ba thay đổi:

1. Tạo compound index `{tenantId: 1, status: 1, createdAt: -1}` để tăng tốc trang danh sách đơn hàng.
2. Bổ sung validator yêu cầu `status` thuộc tập `CREATED`, `PAID`, `CANCELLED` và `amountCents` không âm.
3. Đổi một cấu hình giám sát và một số tham số của server để giảm cảnh báo hiệu năng.

Trên collection test chỉ vài trăm document, tất cả thay đổi đều chạy trong vài giây. Trên dữ liệu thật, tình hình khác:

- Index build có thể tạo tải CPU, RAM, I/O, cần thêm disk, và phải đồng bộ trên replica set.
- Dữ liệu cũ có thể sai kiểu, thiếu field, chứa giá trị trùng hoặc không còn phù hợp validator.
- Validator mới có thể làm lỗi hàng loạt request ghi của các phiên bản ứng dụng chưa được nâng cấp.
- Index được tạo nhưng query planner không dùng; ngược lại xóa một index tưởng không cần có thể làm p99 tăng mạnh.
- Đổi TTL có thể kích hoạt xóa nhiều document trước dự kiến.
- Tham số cấu hình có thể có phạm vi **runtime**, **startup**, **collection** hoặc **cluster**, không phải tất cả đều áp dụng/rollback như nhau.
- Nếu thay đổi trùng đợt failover, batch import hoặc nâng cấp server, việc xác định nguyên nhân sẽ khó hơn.

Vì vậy câu hỏi đúng không phải chỉ là **“Lệnh MongoDB nào chạy được?”**, mà là:

> **Làm sao đưa thay đổi vào production trong khi vẫn bảo vệ dữ liệu, giữ SLO, kiểm soát tương thích, có phép đo trước–sau và biết cách quay lại?**

Bài học giải thích một quy trình **change management** hoàn chỉnh cho **index, schema validator và cấu hình MongoDB** trên dữ liệu đang phục vụ người dùng.

### 1.1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân loại thay đổi theo rủi ro, khả năng đảo ngược và mức tác động tới các node.
- Lấy baseline về query plans, indexes, schema violations, version/FCV và cấu hình đang chạy.
- Lập kế hoạch index build trên populated collections, theo dõi commit quorum và tài nguyên.
- Sử dụng **hidden index** để thử tác động của việc bỏ index mà chưa xóa vật lý.
- Chuyển một index sang **unique** theo quy trình kiểm tra duplicate có kiểm soát.
- Thay đổi TTL và partial/compound index mà không gây xóa dữ liệu hoặc regression bất ngờ.
- Triển khai validator bằng `$jsonSchema`, `collMod`, `validationLevel` và `validationAction` theo nhiều giai đoạn.
- Phân biệt config có thể thay đổi runtime với config cần rolling restart, FCV/upgrade và config do managed service quản lý.
- Thiết kế **expand–migrate–contract**, migration idempotent, rollout canary, rollback và runbook xử lý lỗi.
- Thực hành trong một namespace MongoDB riêng, chỉ ghi/xóa dữ liệu do chính bài lab tạo.

## 2. “Thay đổi schema” trong MongoDB không giống thay đổi một file YAML

MongoDB là document database. Dữ liệu trong cùng collection có thể không đồng nhất:

```javascript
// Document cũ
{
  _id: ObjectId("66a000000000000000000381"),
  tenantId: "T-1",
  status: "paid",
  amount: "350000"
}

// Document mới
{
  _id: ObjectId("66a000000000000000000382"),
  tenantId: "T-1",
  status: "PAID",
  amountCents: NumberLong("35000000"),
  createdAt: ISODate("2026-11-14T04:00:00Z")
}
```

Nếu validator yêu cầu `amountCents` kiểu `long` và `status:"PAID"` viết hoa, document cũ chưa đáp ứng.

**Tính linh hoạt schema** giúp phát triển nhanh, nhưng cũng đòi hỏi kỷ luật khi thay đổi contract giữa database và ứng dụng.

### 2.1. Ba loại thay đổi có bản chất khác nhau

| Loại | Ví dụ | Tác động thường gặp |
| --- | --- | --- |
| Index | Tạo compound/unique/TTL/partial index; hide/drop | Query planner, CPU, disk, write amplification, constraints |
| Validator | `collMod` thay `$jsonSchema`, validation level/action | Khả năng chấp nhận inserts/updates, tính đúng kiểu/dữ liệu |
| Cấu hình | `setParameter`, startup YAML, driver options, FCV | Monitoring, network/auth, memory/threads, feature behavior và khả năng vận hành |

Một thay đổi có thể giao nhau nhiều loại. Ví dụ chuyển `status` từ chuỗi tự do sang enum:

1. Cần ứng dụng ghi status mới.
2. Cần migrate các status cũ.
3. Cần validator để chặn status không hợp lệ.
4. Có thể cần index mới tối ưu query lọc trạng thái.
5. Phải tránh xóa index cũ khi ứng dụng phiên bản trước còn dùng.

### 2.2. Phân loại theo độ rủi ro

| Thay đổi | Có dễ rollback? | Nguy cơ lớn nhất |
| --- | --- | --- |
| Thêm index non-unique | Có thể drop, nhưng xây lại tốn chi phí | Disk/CPU/IOPS khi build và write overhead |
| Thêm hidden index | Có thể drop hoặc unhide | Vẫn có chi phí build/ghi và unique/TTL semantics nếu bật |
| Hide index | Thường unhide nhanh | Query có thể chuyển plan và chậm |
| Drop index | Muốn quay lại phải **rebuild** | Mất performance/constraints trong thời gian rebuild |
| Bật unique | Hạ unique có thể cần rebuild, không phải chỉ toggle đơn giản | Duplicate existing/new writes, sai invariant |
| Rút ngắn TTL | Có thể đổi lại nhưng tài liệu đã xóa không tự phục hồi | Data loss hợp lệ theo TTL bị kích hoạt sớm |
| Validator `warn` | Có thể đổi lại | Logs tăng; không thực sự chặn dữ liệu xấu |
| Validator `error` | Có thể đổi lại | Request inserts/updates bắt đầu thất bại |
| Startup auth/TLS/port | Có kế hoạch rolling rollback nhưng rủi ro cao | Mất kết nối, lỗi health checks/election |
| FCV/major upgrade | Có ràng buộc đường nâng/hạ cấp | Không tương thích feature/data/driver |

Không chỉ dựa trên nhận định “lệnh chạy vài mili giây” để xếp độ rủi ro. Đánh giá **tác động dữ liệu và hệ thống sau khi lệnh hoàn tất**.

## 3. Hợp đồng thay đổi: mục tiêu, phạm vi và người chịu trách nhiệm

Mỗi thay đổi production nên có một change record ngắn, cụ thể:

```yaml
changeId: mongo-orders-2026-11-14-01
owner: team-orders
environment: production
cluster: orders-rs
database: commerce
collection: orders
changeType: index
objective: reduce p95 latency of listOrders query
proposal: add hidden compound index then unhide
preconditions:
  - clusterHealthy
  - enoughDiskHeadroom
  - noConcurrentMigration
  - currentIndexesSaved
successMetrics:
  - readP95BelowSLO
  - noNewWriteErrors
  - replicationLagWithinBaseline
rollbackTrigger:
  - readP99Regresses
  - writeLatencyOrDiskSaturation
rollbackMethod: hideNewIndexAndRestorePreviousRouting
approvals:
  - applicationOwner
  - databaseOperator
```

Đây là **mẫu change record của ứng dụng**, không phải YAML mà MongoDB tự đọc.

### 3.1. Những câu hỏi bắt buộc trước khi bắt đầu

- Thay đổi ảnh hưởng **database/collection/shards** nào?
- Có bao nhiêu documents, indexes, tenant và người dùng?
- Phiên bản MongoDB, FCV, driver và topology hiện tại?
- Có primary/secondary nào chậm, unhealthy hoặc thiếu disk?
- Điều gì đã đo ở staging với dataset đại diện?
- Write paths nào sẽ đổi? Có ứng dụng/worker cũ còn đang chạy không?
- Có backup/restore strategy đã được kiểm tra?
- Có maintenance window hoặc traffic guardrail không?
- Thế nào là thành công; khi nào phải dừng?
- Nếu không rollback ngay được, kế hoạch **forward fix** là gì?

### 3.2. Không thay ba thứ lớn cùng một lúc

Nếu đồng thời tạo index, bật validator nghiêm ngặt và đổi cluster settings, một đợt tăng latency sẽ khó truy ra nguyên nhân. Thông thường nên theo thứ tự:

```text
Baseline + backups
        |
        v
Deploy backward-compatible application code
        |
        v
Create/validate new index (as needed)
        |
        v
Observe / clean old data
        |
        v
Tighten validator with monitoring
        |
        v
Remove obsolete indexes/settings later
```

Có thể nhóm một số bước vào cùng release, nhưng mỗi bước cần một **checkpoint và quyết định tiếp tục/rollback**.

## 4. Thu thập inventory và baseline trước thay đổi

### 4.1. Đúng cluster, đúng phiên bản, đúng namespace

Trong `mongosh`, chỉ với quyền được cấp:

```javascript
printjson({
  dbName: db.getName(),
  serverVersion: db.version(),
  hello: db.adminCommand({ hello: 1 })
});
```

Đọc feature compatibility version nếu có quyền:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Kết quả `hello` thay đổi theo topology/version. Một kết nối qua `mongos` khác kết nối trực tiếp `mongod`; với sharded collection còn phải xét shard key và phân phối dữ liệu.

**Đừng thực hiện DDL trong production bằng một URI copy từ môi trường test.** Ghi rõ endpoint, database, collection, cluster ID trong change record và có cơ chế xác nhận hai người cho thay đổi phá hủy dữ liệu.

### 4.2. Lưu định nghĩa index hiện tại

```javascript
const c = db.getCollection("orders");

printjson(c.getIndexes());
```

Thông tin cần lưu:

- Index name, key order, unique, sparse, partial filter.
- Collation, TTL, hidden flag.
- Các index chuyên biệt (text, geospatial, hashed, wildcard...).
- Index liên quan shard key.
- Kích thước index và tần suất sử dụng.

Trên populated collection, `getIndexes()` **không cho biết index có lợi thực sự**. Phải xem query patterns và usage.

### 4.3. Lưu collection options và validator hiện tại

```javascript
const infos = db.getCollectionInfos({
  name: "orders"
});

printjson(infos.map((x) => ({
  name: x.name,
  options: x.options
})));
```

Đặc biệt lưu nguyên văn:

- `validator`.
- `validationLevel`.
- `validationAction`.
- Collation mặc định.
- Time-series, capped, encryption/other đặc tính nếu có.

Muốn rollback validator đúng, cần biết **biểu thức cũ và các options cũ**, không chỉ ghi nhớ “trước đây không nghiêm”.

### 4.4. Baseline query plans và hiệu năng

```javascript
db.orders.find({
  tenantId: "T-1",
  status: "PAID"
}).sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");
```

Theo dõi:

- `totalDocsExamined` và `totalKeysExamined`.
- `nReturned`.
- Các plan stages như `IXSCAN`/`COLLSCAN`, blocking sort nếu có.
- Latency p50/p95/p99 **từ traffic thực**, không chỉ một lần explain.
- Write latency/error rate và CPU/disk load.

`explain("executionStats")` có thể thực thi công việc đọc đáng kể; không chạy các truy vấn scan toàn cluster không giới hạn trong giờ cao điểm chỉ để lấy một report.

### 4.5. Baseline tài nguyên

Các nhóm cần nhìn:

| Nhóm | Trước thay đổi |
| --- | --- |
| CPU/RAM | CPU process, resident, WiredTiger cache/dirty/eviction |
| Disk | IOPS, throughput, read/write await, queue, free space |
| Replication | Secondary lag, health, majority commit/read concern |
| DB concurrency | Active/waiting operations, locks/tickets, pool wait |
| Application | QPS, timeout, p95/p99 read/write, errors |
| DDL | Index builds/index count, recent migrations |
| Business | Số document sai schema, duplicate keys, TTL eligibility |

## 5. Thay đổi index: chọn đúng trước khi xây

### 5.1. Compound index phải theo query pattern

Giả sử API:

```javascript
db.orders.find({
  tenantId: "T-1",
  status: "PAID"
}).sort({ createdAt: -1 })
  .limit(20);
```

Một ứng viên index:

```javascript
{
  tenantId: 1,
  status: 1,
  createdAt: -1
}
```

Ở đây có hai equality filters và một field sort. Nhưng index tốt nhất vẫn phụ thuộc:

- Cardinality và độ chọn lọc thực tế.
- Query dùng nhiều loại status hay chỉ một status.
- Điều kiện range, pagination, collation.
- Query nào khác cần dùng prefix của compound index.
- Write overhead, dung lượng index, RAM/cache.
- Plan cache và hint trong ứng dụng.

Không tạo một index cho mỗi query variation nếu tổng write overhead và index size quá lớn.

### 5.2. Quy tắc thứ tự trường

Trong nhiều query có equality + sort + range, có thể bắt đầu bằng tư duy **Equality – Sort – Range (ESR)**, nhưng đây là heuristic, không phải luật tuyệt đối. Range filter rất chọn lọc có thể thay đổi ưu tiên. Cần dùng explain và benchmark.

Ví dụ:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

có thể phục vụ lọc tenant/status và sort descending. Index:

```javascript
{ createdAt: -1, tenantId: 1, status: 1 }
```

không tự tương đương cho tập query trên.

### 5.3. Partial index có thể tiết kiệm nhưng có điều kiện

Nếu query chỉ quan tâm đơn hàng đang hoạt động:

```javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  {
    name: "active_orders_by_tenant",
    partialFilterExpression: {
      status: "ACTIVE"
    }
  }
);
```

Index chỉ có một tập con documents. Query planner chỉ dùng partial index khi query predicate bảo đảm kết quả hợp lệ tương ứng với filter của index. Một query không lọc `status:"ACTIVE"` không thể tự dùng index này để lấy đầy đủ tất cả documents.

Không thay một full index bằng partial index khi còn query phải bao phủ cả inactive/cancelled data.

### 5.4. Unique index có rủi ro dữ liệu lịch sử

Muốn thêm:

```javascript
{ tenantId: 1, externalOrderId: 1 }
```

với `unique:true`, phải kiểm tra:

- Duplicates đã tồn tại chưa.
- Các document thiếu `externalOrderId` hoặc có null.
- Semantics của collations/case/Unicode.
- Các write paths cũ có thể tiếp tục tạo duplicate không.
- Trong sharded collection, quy tắc unique index và shard key.
- Có đổi business scope từ global sang per-tenant không.

Đừng chỉ thử `createIndex(...,{unique:true})` trên production rồi đợi lỗi để “khám phá dữ liệu”.

## 6. Index build trên collection có dữ liệu lớn

### 6.1. Index build không hoàn toàn miễn phí khi online

MongoDB hiện đại dùng cơ chế xây index trên populated collections cho phép đọc/ghi xen kẽ trong phần lớn quá trình. Tuy nhiên:

- Có exclusive collection lock ở **đầu và cuối** index build.
- Quá trình scan/sort có thể dùng CPU, RAM và temporary disk.
- Ghi đồng thời phải được xử lý trong quá trình build.
- Replicated/sharded deployments cần tham gia của các data-bearing members.
- Index build có thể bị abort hoặc chờ quorum khi node gặp sự cố.

Vì vậy “build online” **không có nghĩa không ảnh hưởng latency**. Cần sizing, capacity headroom và giám sát.

### 6.2. Commit quorum trên replica set

Trong cơ chế replicated index builds, primary cần một tập data-bearing voting members hoàn tất xây index theo **commit quorum** trước khi index được đánh dấu sẵn sàng.

Các khái niệm:

- `commitQuorum`: số members cần hoàn thành build theo chính sách.
- Default thường là `votingMembers` theo tài liệu.
- Member voting unavailable có thể khiến index build **đợi**.
- Kết quả phải được theo dõi trên **từng member**.
- Điều chỉnh commit quorum là quyết định vận hành có rủi ro, không phải cách mặc định để “ép xong”.

Ví dụ cú pháp **chỉ để tham khảo**:

```javascript
db.runCommand({
  createIndexes: "orders",
  indexes: [
    {
      key: { tenantId: 1, status: 1, createdAt: -1 },
      name: "orders_tenant_status_created_v2"
    }
  ],
  commitQuorum: "votingMembers"
});
```

Không thực thi mẫu này trên production khi chưa xác minh indexes đang có, storage headroom, replicaset health và quyền đổi schema.

### 6.3. Mặc định dùng replicated index build

Đừng tự thực hiện “rolling index build” bằng cách gỡ từng replica set member để chạy standalone khi chưa có runbook được MongoDB hỗ trợ. Quy trình rolling index build là lựa chọn **đặc biệt**, có thể làm giảm khả năng chịu lỗi, kéo dài thay đổi và cần election.

Không chạy replicated index build và rolling index build trùng nhau nếu tài liệu cảnh báo xung đột. Với Atlas/managed service, dùng công cụ quản lý index thích hợp của dịch vụ.

### 6.4. Theo dõi tiến độ

Trên môi trường có quyền thích hợp:

```javascript
db.adminCommand({
  currentOp: 1,
  $all: true
});
```

Hoặc dùng `$currentOp` trên `admin` ở phiên bản và quyền phù hợp. Tìm operations đang build index, thời gian chạy, progress, namespace và wait state.

**Không** kill một index build chỉ vì thời gian dài; phải xem khả năng abort/recovery, mức disk, commit quorum và ảnh hưởng workloads.

### 6.5. Hạn chế tài nguyên xây index

Kiểm tra:

- Disk free trên mỗi member và temporary space.
- `maxIndexBuildMemoryUsageMegabytes`/cấu hình tương ứng theo phiên bản.
- `indexBuildMinAvailableDiskSpaceMB` (khả năng từ MongoDB 7.1) nếu áp dụng.
- CPU/IOPS/throughput/burst credits.
- Các DDL khác đang chạy.
- Oplog/replication lag khi writes lớn.

Không đổi các knobs nội bộ dựa trên một blog cũ mà không đối chiếu release/version.

## 7. Hidden indexes: công cụ quan trọng cho rollout và rollback

### 7.1. Hidden là gì?

**Hidden index** vẫn tồn tại, được cập nhật khi ghi, tiêu thụ disk/RAM và thực thi các semantics như **unique** hoặc **TTL**. Chỉ có một khác biệt quan trọng: **query planner không được chọn nó** để thực thi query thông thường.

Nó hữu ích để:

- Tạo index mới trước, chưa đưa vào kế hoạch truy vấn.
- Kiểm tra tác động nếu index hiện hữu bị “rút khỏi” query planner.
- Rollback nhanh bằng **unhide** nếu hiệu năng kém khi ẩn index.
- Canh thời điểm công bố index mới theo feature flag/change window.

### 7.2. Tạo index ở trạng thái hidden

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  {
    name: "orders_tenant_status_created_v2",
    hidden: true
  }
);
```

Sau build, index đã chiếm tài nguyên dù chưa được planner dùng.

### 7.3. Unhide để kích hoạt cho optimizer

```javascript
db.orders.unhideIndex(
  "orders_tenant_status_created_v2"
);
```

Kiểm chứng:

```javascript
printjson(db.orders.getIndexes());

printjson(
  db.orders.find({
    tenantId: "T-1",
    status: "PAID"
  }).sort({ createdAt: -1 }).limit(20)
    .explain("executionStats")
);
```

Unhide làm index **eligible**, không bảo đảm planner chọn index đó cho mọi query. Phải theo dõi plan và latency thực tế.

### 7.4. Hide để thử tác động khi bỏ một index

```javascript
db.orders.hideIndex(
  "orders_status_legacy"
);
```

Theo dõi đủ các query shapes và thời gian. Nếu p99 tăng:

```javascript
db.orders.unhideIndex(
  "orders_status_legacy"
);
```

Nhưng rollback này chỉ có tác dụng khi index còn nguyên. **Drop** index sẽ phải **rebuild** nếu cần quay lại.

### 7.5. Giới hạn của hidden

- Không thể hide `_id` index.
- Không thể dùng `hint()` để ép truy vấn sử dụng hidden index.
- Unique constraint **vẫn áp dụng**.
- TTL expiration **vẫn chạy**.
- Hidden index tiếp tục làm writes tốn tài nguyên.
- Khi đổi hide/unhide, bộ đếm `$indexStats` có thể được **reset**.

Vì vậy nếu muốn canary index mới, không dùng `hint(hiddenIndex)` để thử trên nó. Cần **unhide có kiểm soát** và quan sát optimizer/traffic, hoặc thử trên cluster/collection staging tương đương.

### 7.6. Hidden chưa phải là canary theo tenant

Hide/unhide là thuộc tính index ở cấp collection, **không phải feature flag cho riêng một tenant**. Khi unhide, planner trên workload của toàn collection có thể cân nhắc index mới.

Nếu cần canary theo cohort, phải thiết kế application routing/query shape hoặc môi trường shadow/staging riêng, đồng thời theo dõi tác động khi index trở thành eligible cho mọi query.

## 8. Khi nào nên drop index?

### 8.1. Không drop chỉ vì `$indexStats.ops` thấp

Index usage được đọc bằng:

```javascript
db.orders.aggregate([
  { $indexStats: {} }
]);
```

Một index ít được dùng trong 1 giờ có thể là index phục vụ:

- End-of-month billing.
- Nightly job/quarterly reports.
- Khôi phục sau failover.
- Query hiếm nhưng cực kỳ quan trọng.
- Một API cũ vẫn còn hoạt động.

`$indexStats` còn có giới hạn: số liệu thường tính trên node được đọc và reset theo các sự kiện như restart hoặc hide/unhide. Không so raw ops giữa hai members/uptimes khác nhau rồi kết luận index không dùng.

### 8.2. Quy trình loại bỏ index

1. Lập danh sách query hiện dùng index và owner.
2. Kiểm tra không cần cho uniqueness/TTL/business rules.
3. Hide index trước.
4. Quan sát các chu kỳ nghiệp vụ đại diện.
5. Nếu ổn, lên lịch drop theo change ticket.
6. Giữ definition để có thể rebuild khi cần.
7. Theo dõi write latency/storage sau drop.
8. Nếu có regression, phục hồi bằng quy trình index build hợp lệ.

`dropIndex()` là DDL, không được đưa trực tiếp vào cron “cleanup index” thiếu review.

### 8.3. Không bỏ index ràng buộc vì muốn giảm write overhead

Nếu một unique index bảo vệ định danh duy nhất, hide không bỏ constraint, nhưng drop sẽ bỏ. **Tác động dữ liệu quan trọng hơn tiết kiệm disk**. Với TTL, drop có thể ngừng retention deletion và thay đổi yêu cầu xóa dữ liệu.

## 9. Unique index trên dữ liệu cũ: phát hiện và ngăn duplicate

### 9.1. Tìm duplicate trước khi bật unique

Ví dụ dự kiến unique theo `tenantId + externalOrderId`:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      },
      count: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $limit: 50 }
]);
```

**Không dùng pipeline này không giới hạn trên collection hàng trăm triệu document**: `$group`/`$push` có thể tiêu tốn RAM/disk, lưu array ID khổng lồ và gây tải. Trên production, dùng sampling/partitioning, giới hạn batch hoặc workflow audit có budget; đối chiếu BSON null/missing và collation.

### 9.2. Lộ trình chuyển non-unique index thành unique (MongoDB 6.0+)

MongoDB hỗ trợ một quy trình `collMod` với `prepareUnique`:

```text
Existing non-unique index
           |
           v
prepareUnique: true
  -> chặn duplicate MỚI
           |
           v
Audit/fix old duplicates
           |
           v
unique: true, dryRun: true
           |
           v
unique: true
  -> kiểm tra và chuyển đổi
```

Ví dụ lệnh, **không chạy trực tiếp trên production thiếu approval**:

```javascript
// 1. Index có trước (tên chính xác phải được xác minh):
db.runCommand({
  collMod: "orders",
  index: {
    name: "tenant_externalOrderId_lookup",
    prepareUnique: true
  }
});

// 2. Audit khả năng chuyển:
db.runCommand({
  collMod: "orders",
  index: {
    name: "tenant_externalOrderId_lookup",
    unique: true
  },
  dryRun: true
});

// 3. Chỉ sau khi sửa duplicates và dryRun đạt:
db.runCommand({
  collMod: "orders",
  index: {
    name: "tenant_externalOrderId_lookup",
    unique: true
  }
});
```

`prepareUnique:true` **không tự quét và sửa duplicates cũ**; nó bắt đầu chặn duplicate mới. Chuyển `unique:true` sẽ scan để tìm duplicates. Nếu phát hiện, lệnh báo lỗi (ví dụ `CannotConvertIndexToUnique`), cần xử lý từng conflict rồi chạy lại.

`dryRun:true` không phải transaction hay lock business workflow; vẫn cần kiểm soát writes đồng thời. Quy tắc unique trong **sharded collections** cần kiểm tra shard key prefix và các giới hạn liên quan.

### 9.3. Kế hoạch xử lý duplicate phải theo nghiệp vụ

Không chọn “giữ document đầu tiên, xóa phần còn lại” khi duplicate có payments, audit logs hoặc references.

Các lựa chọn có thể là:

- Hợp nhất theo business decision và lineage.
- Phân biệt quy tắc unique theo tenant.
- Đánh dấu legacy duplicates để xử lý theo policy.
- Tách historical records khỏi active records.
- Dùng partial unique index **chỉ khi semantics thực sự cho phép**.

Khi unique đã bật, ứng dụng phải xử lý lỗi **DuplicateKey** như một phần contract; không retry insert vô hạn với ID mới.

## 10. TTL index: thay đổi có thể xóa dữ liệu hàng loạt

### 10.1. Ví dụ TTL

```javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  {
    name: "session_expiration",
    expireAfterSeconds: 0
  }
);
```

Với date ở `expiresAt`, TTL monitor xóa document khi đến hạn theo điều kiện index. TTL deletion **không đúng thời điểm millisecond tuyệt đối**, chịu ảnh hưởng monitor schedule và tải server.

### 10.2. Rút ngắn TTL trên dữ liệu cũ

Giả sử index dùng `expireAfterSeconds: 2592000` (30 ngày), đổi xuống `86400` (1 ngày). Nhiều document lịch sử có thể **đột nhiên trở thành eligible để bị xóa**.

Đây không chỉ là “đổi performance index”, mà là **thay retention policy và có thể gây mất dữ liệu không thể tự rollback**.

Quy trình:

1. Tính số records sẽ eligible với TTL mới.
2. Kiểm legal hold, compliance, audit retention.
3. Kiểm ảnh hưởng lên downstream systems.
4. Cân nhắc xóa theo batch trước khi đổi để tránh burst.
5. Backup/recovery checkpoint khi cần.
6. Chỉ thay TTL sau khi có approval.
7. Theo dõi TTL deletion rate, replication lag, disk and write latency.

### 10.3. Đổi TTL index bằng `collMod`

Trên phiên bản hỗ trợ:

```javascript
db.runCommand({
  collMod: "sessions",
  index: {
    name: "session_expiration",
    expireAfterSeconds: 86400
  }
});
```

**Chỉ là ví dụ cú pháp.** Không chạy khi chưa đo dữ liệu sẽ bị hết hạn. Đổi lại TTL sau khi đã xóa records **không khôi phục được những records đã mất**.

### 10.4. Hidden TTL vẫn xóa

Một index TTL dù `hidden:true` vẫn thực hiện expiration. **Không hide TTL như cách tạm dừng dọn dữ liệu**.

## 11. Validator: ràng buộc ghi dữ liệu chứ không phải “migration tự động”

### 11.1. Validator hoạt động lúc nào?

MongoDB collection validator kiểm tra inserts và updates theo `validationLevel`/`validationAction`. Đặt validator mới bằng `collMod` **không tự quét/sửa hay loại bỏ ngay** tất cả document đang có.

Ví dụ document legacy:

```javascript
{
  _id: 1,
  amountCents: "50000",
  status: "paid"
}
```

Nếu validator mới yêu cầu `amountCents` kiểu `long` và `status:"PAID"`, document này vẫn có thể nằm trong collection **ngay sau khi `collMod` thành công**. Mục tiêu validator là bảo vệ **đường ghi tiếp theo** theo lựa chọn level/action.

### 11.2. Dùng `$jsonSchema`

Ví dụ validator cho orders:

```javascript
const orderValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "tenantId",
      "status",
      "amountCents"
    ],
    properties: {
      tenantId: {
        bsonType: "string",
        minLength: 1
      },
      status: {
        enum: ["CREATED", "PAID", "CANCELLED"]
      },
      amountCents: {
        bsonType: ["int", "long"],
        minimum: 0
      },
      createdAt: {
        bsonType: "date"
      }
    }
  }
};
```

Không phải mọi tính năng JSON Schema draft đều được MongoDB hỗ trợ y nguyên. MongoDB dùng `bsonType`, và các toán tử/keywords có giới hạn theo phiên bản. Khi dùng `NumberInt`, `NumberLong`, `Decimal128` cần khớp **BSON types**, không chỉ giá trị hiển thị.

### 11.3. `validationAction`

| Giá trị | Hành vi |
| --- | --- |
| `warn` | Cho phép ghi không hợp lệ nhưng ghi cảnh báo vào MongoDB log |
| `error` | Từ chối insert/update vi phạm khi validation được áp dụng |
| `errorAndLog` | Từ chối và log thông tin vi phạm; có từ MongoDB 8.1 theo tài liệu |

`warn` hữu ích để **đo vi phạm trước khi chặn ghi**, nhưng không đảm bảo dữ liệu luôn đúng. `errorAndLog` có thể tăng log volume và thông tin nhạy cảm nếu không quản trị logs; không dùng chỉ vì muốn “debug nhiều hơn”.

### 11.4. `validationLevel`

| Giá trị | Ý nghĩa |
| --- | --- |
| `off` | Tắt validation cho inserts/updates |
| `moderate` | Validate inserts và updates trên **document hiện đang hợp lệ**; updates trên existing invalid documents không bị validator chặn theo cùng cách |
| `strict` | Validate mọi inserts và mọi updates theo quy tắc |
| `constraint` | MongoDB 9.0+, mức có điều kiện chuẩn bị để đảm bảo mọi document trong collection phù hợp, ngăn bypass theo quy tắc |

`strict` là default của schema validation thông thường. Nhưng `strict` **không retro-validate toàn bộ document cũ khi chỉ mới đặt rule**; các document cũ chỉ bắt đầu chịu kiểm tra khi chúng được cập nhật. Mức `constraint` mới có điều kiện chuẩn bị/upgrade và cần tham khảo tài liệu version cụ thể.

### 11.5. Một ma trận các trạng thái

Giả sử validator mới coi document A là **hợp lệ**, document B là **không hợp lệ**:

| Operation | `moderate + error` | `strict + error` |
| --- | --- | --- |
| Insert document mới hợp lệ | Cho phép | Cho phép |
| Insert document mới sai | Từ chối | Từ chối |
| Update A thành sai | Từ chối | Từ chối |
| Update B vẫn sai | Có thể được phép vì B vốn invalid | Từ chối |
| Update B thành hợp lệ | Có thể thực hiện | Có thể thực hiện |
| Existing B không bị update | Vẫn còn | Vẫn còn |

Khi `validationAction:"warn"`, các violations thuộc phạm vi validation thường được log thay vì từ chối; điều này phù hợp giai đoạn quan sát.

### 11.6. Validation không thay business transaction

Validator có thể ràng buộc kiểu `amountCents` và enum `status`. Nhưng nó không tự:

- Cưỡng chế unique business key nếu cần compound unique index.
- Kiểm quyền sở hữu tenant.
- Bảo đảm inventory không âm trong giao dịch giữa nhiều documents.
- Xác thực thanh toán với bên thứ ba.
- Tự đảm bảo dữ liệu tham chiếu ở collection khác tồn tại.

Dùng validator cho **document-level contract**. Dùng atomic operations, indexes, transactions (khi phù hợp) và authorization cho các bất biến khác.

## 12. Audit dữ liệu trước khi bật validator nghiêm

### 12.1. Đo những document không phù hợp

Giả sử `orderValidator` như phần trước:

```javascript
db.orders.find({
  $nor: [orderValidator]
}).limit(30);
```

Hoặc:

```javascript
db.orders.countDocuments({
  $nor: [orderValidator]
});
```

Đây là cách **đánh giá bằng query tương đương điều kiện validator**, không thay đổi collection. Trên hàng chục triệu documents có thể cần full scan; phải giới hạn chi phí hoặc chạy theo batch/partition/index hỗ trợ.

**Không dùng một lần count scan nặng giữa peak rồi kết luận “validator gây chậm”.** Thực hiện audit trên staging/snapshot, giới hạn thời gian và đo CPU/disk.

### 12.2. Phân loại vi phạm, không sửa tất cả một kiểu

| Vi phạm | Ví dụ | Cách cân nhắc |
| --- | --- | --- |
| Thiếu field | `amountCents` không tồn tại | Xác định giá trị từ source, không bịa bằng 0 |
| Sai BSON type | Chuỗi `"50000"` thay vì `Long` | Parse/validate, xử lý giá trị ngoài miền |
| Sai enum | `"paid"` vs `"PAID"` | Mapping có chủ đích, giữ semantics |
| Negative value | `amountCents:-15` | Điều tra lỗi nghiệp vụ, không tự sửa thành 0 |
| Field cũ đổi tên | `amount` vs `amountCents` | Migration có version và đối soát |
| Document không thuộc schema mới | Legacy event type | Có thể tách collection hoặc dùng validator điều kiện hợp lệ |

Câu “dữ liệu thật” có nghĩa document đang được dùng cho kinh doanh, có audit/truy vết. **Không auto-delete hoặc sửa số tiền không rõ nguồn** chỉ để validator pass.

### 12.3. Bắt đầu từ thống kê phân phối

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: { $type: "$amountCents" },
      total: { $sum: 1 }
    }
  },
  { $sort: { total: -1 } }
]);
```

Lệnh `$type` trả tên type của field hoặc biểu diễn missing theo version; giúp thấy có bao nhiêu documents với `long`, `int`, `string` hoặc thiếu field.

Trên collection lớn, `$group` có chi phí; chỉ chạy theo môi trường/khung giờ phù hợp.

## 13. Triển khai validator theo giai đoạn

### 13.1. Giai đoạn 0 — Code ứng dụng tương thích

Trước khi thay database:

- Update tất cả write paths để ghi BSON types đúng.
- Update batch jobs/importers/ETL.
- Kiểm tra version ứng dụng cũ còn chạy.
- Chuẩn hóa enum và field semantics.
- Chuẩn bị logging của DocumentValidationFailure.
- Kiểm tra test với cả documents legacy và documents mới.

Một validator tốt sẽ trở thành outage nếu vẫn còn nhiều service ghi dạng cũ.

### 13.2. Giai đoạn 1 — Chỉ cảnh báo

```javascript
db.runCommand({
  collMod: "orders",
  validator: orderValidator,
  validationLevel: "moderate",
  validationAction: "warn"
});
```

Lệnh này cho phép ghi sai (trong phạm vi mức validation) nhưng log violations. Nó có thể tăng diagnostic log volume; phải xác định retention/PII và theo dõi lỗi.

Điều kiện qua giai đoạn tiếp: số lần vi phạm mới giảm về mức có thể chấp nhận, hiểu từng nguồn phát sinh.

### 13.3. Giai đoạn 2 — Chặn dữ liệu mới sai, vẫn hỗ trợ legacy remediation

```javascript
db.runCommand({
  collMod: "orders",
  validator: orderValidator,
  validationLevel: "moderate",
  validationAction: "error"
});
```

Tác động:

- Insert invalid mới bị từ chối.
- Update từ document hợp lệ sang invalid bị từ chối.
- Existing invalid documents có thể tiếp tục được sửa theo semantics moderate.

Dùng giai đoạn này để chặn nguồn vi phạm mới trước khi migrate historical data.

### 13.4. Giai đoạn 3 — Sửa legacy theo batch

Không dùng `updateMany({},{ $set:{ amountCents:0 }})` trên production.

Phương án chuẩn:

1. Chọn một cohort nhỏ theo `_id`/tenant/time.
2. Đọc dữ liệu nguồn và tính giá trị đích một cách xác định.
3. Validate riêng từng conversion.
4. Ghi update có **compare-and-set** theo version/old value.
5. Ghi progress và lỗi, không tự bỏ qua records lỗi.
6. Đối soát trước/sau.
7. Tiếp tục batch tiếp theo, có throttle.

Nếu một record sai do inconsistency nghiệp vụ, đưa vào queue manual remediation thay vì ép “hợp lệ cho đẹp dashboard”.

### 13.5. Giai đoạn 4 — Chuyển strict

Sau khi số document sai còn 0 theo audit đủ tin cậy và mọi writer đã đúng schema:

```javascript
db.runCommand({
  collMod: "orders",
  validator: orderValidator,
  validationLevel: "strict",
  validationAction: "error"
});
```

Mọi updates chịu validation. Nhưng `strict` không tự chứng minh dữ liệu cũ còn 0 vi phạm nếu audit thiếu hoặc có bypass; phải tiếp tục giám sát.

### 13.6. MongoDB 9.0: `constraint` là mức đặc biệt

Trong MongoDB 9.0+, tài liệu cung cấp mức `validationLevel:"constraint"` và bước chuẩn bị:

```javascript
// Chỉ minh họa thứ tự áp dụng, không chạy trên prod
// nếu chưa có kế hoạch và không xác nhận MongoDB >= 9.0.
db.runCommand({
  collMod: "orders",
  prepareConstraintValidationLevel: true
});

db.runCommand({
  collMod: "orders",
  validationLevel: "constraint",
  validationAction: "error"
});
```

Các điều kiện:

- Cần validator hiện hữu được xác định trước.
- Phải làm bước chuẩn bị trên collection cũ theo tài liệu.
- Không thể sửa rules cùng lúc upgrade lên constraint.
- Validation action phải `error` hoặc `errorAndLog`.
- Hạn chế `bypassDocumentValidation` và thay validator khi đang ở constraint.
- Muốn sửa rules sau đó có thể cần **downgrade level** rồi thực hiện quy trình upgrade lại.

**Không áp đoạn lệnh 9.0 lên MongoDB 7.0/8.0**. Lưu ý FCV/driver và compatibility matrix trước khi chọn mức mới.

## 14. Validator mới ảnh hưởng những thao tác nào?

### 14.1. Update “không liên quan” vẫn có thể bị từ chối

Ví dụ legacy document có `amountCents:"50000"`. Ứng dụng chỉ muốn sửa ghi chú:

```javascript
db.orders.updateOne(
  { _id: id },
  { $set: { note: "Đã gọi xác nhận" } }
);
```

Với `strict + error`, MongoDB kiểm tra document sau update; kết quả vẫn invalid và update có thể bị từ chối. Vì vậy **tăng validationLevel** trên dữ liệu cũ có thể làm lỗi các thao tác tưởng không liên quan.

### 14.2. `bypassDocumentValidation` không phải chính sách mặc định

Một số lệnh/driver có khả năng `bypassDocumentValidation` nếu user có privilege. Đây là **ngoại lệ có kiểm soát**, không phải cách xử lý khẩn cấp mặc định.

- Chỉ cấp quyền bypass khi có mục đích vận hành rõ.
- Ghi audit và thời gian dùng.
- Không dùng bypass để duy trì ứng dụng cũ ghi dữ liệu sai.
- Với `constraint` MongoDB 9.0, khả năng bypass bị hạn chế theo documentation.

### 14.3. Validator không tự chạy trên delete

Schema validation áp dụng khi insert/update; xóa document không cần làm document “hợp lệ”. Nhưng delete có thể bị ràng buộc bởi authorization, retention hoặc transaction/business rules khác.

### 14.4. Bảo mật khi logging validation failure

Validator errors/logs có thể chứa thông tin về dữ liệu vi phạm. Không dump toàn bộ production document vào centralized logs mà không kiểm soát PII, token, địa chỉ, ghi chú cá nhân và dữ liệu tài chính.

Cần role-based access, masking, retention và hạn chế mức log khi dùng `warn`/`errorAndLog`.

## 15. Cấu hình MongoDB: phân biệt scope trước khi đổi

### 15.1. Những lớp cấu hình

```text
Application / MongoDB Driver
  URI, pool, retryWrites, readPreference, timeouts
                     |
                     v
MongoDB Process startup
  mongod.conf / command flags, networking, TLS, storage
                     |
                     v
Server runtime parameters
  selected getParameter / setParameter capabilities
                     |
                     v
Database/collection options
  collMod validator, index definition, TTL, collation
                     |
                     v
Cluster-wide semantics
  replica set config, FCV, sharding, auth/upgrade features
```

Các thay đổi này khác nhau về **phạm vi, quyền, thời gian hiệu lực và rollback**.

### 15.2. Runtime `getParameter` / `setParameter`

Đọc một số parameter:

```javascript
db.adminCommand({
  getParameter: 1,
  slowOpThresholdMs: 1
});
```

Ở phiên bản cho phép, `slowOpThresholdMs` có thể điều chỉnh runtime và ảnh hưởng logging/profiling of slow operations. Nhưng **không phải mọi parameter đều có thể đổi runtime**, không phải tất cả parameter có nghĩa giống nhau trên mongod/mongos hoặc mọi release.

Một ví dụ **chỉ minh họa**:

```javascript
// Không chạy trên production chỉ vì bài học:
db.adminCommand({
  setParameter: 1,
  slowOpThresholdMs: 200
});
```

Cần:

- Ghi giá trị cũ.
- Xác minh tính mutable của parameter theo version.
- Biết parameter tác động lên logging/performance như thế nào.
- Xác định có persist qua restart không.
- Tạo rollback/change expiration và đo log volume.
- Biết cách áp dụng nhất quán trên mọi member nếu thực sự cần.

### 15.3. Runtime không nhất thiết bền qua restart

Một thay đổi `setParameter` thành công có thể **không được ghi vào startup config**. Khi process restart, server có thể dùng giá trị trong `mongod.conf` hoặc default.

Vì vậy quy trình phải quy định:

- Desired value ở config management/IaC.
- Observed runtime value.
- Giá trị startup thực đã parse.
- Owner của config.
- Cách phát hiện drift.

### 15.4. Startup config cần rollout thích hợp

Ví dụ thay cấu hình network/TLS, storage engine, hoặc một tham số chỉ đọc lúc khởi động thường cần restart process để áp dụng.

Với replica set:

1. Kiểm tra health và backup.
2. Xác minh hai server versions/FCV tương thích trong suốt quá trình.
3. Đổi từng member theo **rolling procedure chính thức**, không hạ cả quorum cùng lúc.
4. Theo dõi election và replication catch-up.
5. Đảm bảo app driver có CA/TLS/URI tương thích.
6. Chỉ chuyển primary khi cần và đã sẵn sàng.
7. Giữ rollback config/keys phù hợp.

Không áp “rolling restart” tự chế với sharded cluster/mongos/config servers mà không theo documented upgrade order.

### 15.5. Đọc startup options

```javascript
const config = db.adminCommand({
  getCmdLineOpts: 1
});

printjson({
  parsedStorage: config.parsed?.storage,
  parsedNet: config.parsed?.net,
  parsedSetParameter: config.parsed?.setParameter
});
```

Command cần quyền và có thể bị hạn chế trên managed services. Output có thể chứa **thông tin cấu hình nhạy cảm**; không copy toàn bộ lên ticket công khai.

### 15.6. Driver configuration cũng là một thay đổi hiệu năng

Một số nguyên nhân latency thực tế không nằm ở `mongod` mà ở:

- Connection pool bị bão hòa.
- `maxPoolSize` quá thấp/cao.
- `waitQueueTimeoutMS` hoặc server selection timeout.
- `retryWrites` và transient errors.
- Read preference sang secondary bị lag.
- `maxTimeMS` khác giữa endpoints.
- BSON serialization hoặc nén mạng.

Không chỉnh server memory/index nếu truy vấn MongoDB tự chạy nhanh nhưng request bị kẹt ở driver connection pool.

## 16. Feature Compatibility Version và nâng cấp server

### 16.1. FCV không phải chỉ số version đẹp mắt

MongoDB có **featureCompatibilityVersion (FCV)** để quản lý khả năng sử dụng một số tính năng/định dạng sau nâng cấp binary. Cùng một binary version nhưng FCV có thể ảnh hưởng khả năng bật feature và đường downgrade.

Quy trình nâng cấp chuẩn thường bao gồm:

```text
Read upgrade release notes
          |
          v
Driver/application compatibility check
          |
          v
Backup + test restore
          |
          v
Rolling binary upgrade per topology
          |
          v
Observe cluster stability
          |
          v
Set FCV using documented procedure
          |
          v
Enable version-dependent features
```

Không chạy `setFeatureCompatibilityVersion` chỉ vì muốn bật hidden index/validator nâng cao mà chưa thực hiện upgrade path hỗ trợ.

### 16.2. Version-aware validator/index features

Ví dụ các tính năng có mốc version:

- Hidden indexes có yêu cầu version/FCV.
- Convert non-unique index sang unique với `prepareUnique`/`dryRun` từ MongoDB 6.0.
- Index build memory/disk safeguards thay đổi theo release.
- `validationAction:"errorAndLog"` từ MongoDB 8.1.
- `validationLevel:"constraint"` từ MongoDB 9.0.

Đội vận hành cần kiểm **server version + FCV + topology + driver + Atlas plan** trước khi phát hành scripts.

### 16.3. Managed service không giống self-managed

Atlas và các dịch vụ managed có thể:

- Giới hạn thao tác `setParameter`.
- Tự điều phối index builds/restarts.
- Cung cấp dashboard/query profiler khác.
- Chặn cấu hình trực tiếp vào `mongod.conf`.
- Tự thiết lập backup, PITR và upgrade windows.

Không dùng command tự vận hành của self-managed cluster để vượt cơ chế kiểm soát của nhà cung cấp.

## 17. Expand–migrate–contract: mẫu thay đổi schema an toàn

### 17.1. Tại sao cần nhiều release?

Giả sử muốn đổi:

```javascript
// Cũ
{ amount: "350000" }

// Mới
{ amountCents: NumberLong("35000000") }
```

Không thể deploy một validator chỉ cho phép `amountCents:long` trước khi mọi writer và dữ liệu cũ chuyển đổi.

### 17.2. Expand

- App mới có thể đọc cả `amount` và `amountCents`.
- App mới bắt đầu ghi giá trị mới.
- Xác định source of truth duy nhất trong giai đoạn chuyển tiếp.
- Nếu dual-write, cả hai field phải được cập nhật nhất quán và có cơ chế phát hiện mismatch.
- Tạo index mới chưa dùng/hidden nếu cần.
- Triển khai validator ở mức `warn` trước.

### 17.3. Migrate

- Backfill documents cũ theo batch nhỏ.
- Dùng compare-and-set hoặc version để tránh ghi đè concurrent writes.
- Track progress theo `_id` hoặc job state, có retry idempotent.
- Kiểm dữ liệu theo semantics nghiệp vụ (đơn vị tiền, timezone, enum).
- Theo dõi replication lag, write p95, disk và log violations.
- Có canary cohorts và manual queue cho dữ liệu không thể tự convert.

### 17.4. Contract

- Ngừng ghi/read field cũ khi mọi client đã chuyển.
- Bật validator `moderate+error` rồi `strict+error` khi đạt điều kiện.
- Hide old index, đo, mới drop.
- Xóa code/field legacy bằng change riêng.
- Giữ backup/rollback theo chính sách retention.

**Contract nên là bước cuối**, sau khi đã chứng minh không còn writer cũ hoặc dữ liệu chưa migrate.

## 18. Migration idempotent và xử lý ghi đồng thời

### 18.1. Vì sao `updateMany` toàn collection thường nguy hiểm?

Một lệnh kiểu:

```javascript
// Không chạy trên dữ liệu thật:
db.orders.updateMany(
  {},
  { $set: { amountCents: NumberLong(0) } }
);
```

có thể phá giá trị của mọi đơn hàng, tăng oplog, dirty pages, làm secondary lag và không có cách rollback đơn giản.

### 18.2. Điều kiện update phải có old value/version

Một record:

```javascript
{
  _id: orderId,
  version: 7,
  amount: "350000",
  amountCents: null
}
```

Sau khi ứng dụng tính được giá trị đích hợp lệ:

```javascript
db.orders.updateOne(
  {
    _id: orderId,
    version: 7,
    amount: "350000",
    amountCents: null
  },
  {
    $set: {
      amountCents: NumberLong("35000000"),
      migrationVersion: "amount-v2"
    },
    $inc: { version: 1 }
  }
);
```

Điều kiện lọc giúp phát hiện document đã thay đổi trước khi migration ghi. Nếu `matchedCount:0`, phải đọc lại và quyết định; **không đổi sang filter chỉ `_id` rồi ghi đè**.

Với legacy data thiếu field hoặc version, thiết kế filter theo trạng thái hiện hữu thực và kiểm tra `$exists`/giá trị phù hợp, không copy một mẫu vào mọi document.

### 18.3. Batch và checkpoint

```text
Read candidate IDs (bounded)
         |
         v
Transform and validate in app
         |
         v
BulkWrite bounded updates
         |
         v
Record matched/modified/conflicts
         |
         v
Checkpoint last processed ID
         |
         v
Throttle, observe, repeat
```

Không giữ một cursor vô hạn hoặc giao dịch bao trùm hàng triệu documents. Dùng chunk nhỏ, có stop flag, rate limit và restart-safe progress.

### 18.4. Khi có writes mới trong lúc backfill

Có hai kiểu điều phối:

**Option A — Quiesce writes:** tạm dừng ghi vào tập dữ liệu mục tiêu trong maintenance window.

**Option B — Online migration:** ứng dụng ghi theo contract mới, backfill theo version, kết hợp outbox/change streams/reconciliation nếu cần, xử lý eventual consistency.

Không giả định một phép scan ở T0 rồi update ở T1 có snapshot nhất quán khi nhiều service vẫn ghi.

## 19. Canary, traffic và query plan rollback

### 19.1. Chia rollout thành checkpoints

```text
Baseline captured
     |
New index built hidden
     |
Index unhidden / query plans observed
     |
App canary / guardrails
     |
Validator warn
     |
Migration small cohort
     |
Validator moderate+error
     |
Validator strict+error
     |
Old index hidden, then drop later
```

Thứ tự cụ thể phụ thuộc mục đích. Nếu index mới bắt buộc cho ứng dụng mới, phải build trước khi tăng traffic ứng dụng.

### 19.2. Một số thay đổi là toàn collection

- `collMod` validator tác động lên mọi write paths của collection theo rules.
- Hide/unhide index làm planner của collection thay đổi, không riêng một user.
- TTL changes ảnh hưởng toàn dữ liệu eligible.
- Cluster startup config ảnh hưởng node.

Do đó **canary application traffic** không giới hạn hoàn toàn blast radius của những DDL global. Với rủi ro cao, dùng collection shadow/namespace versioned hoặc staging thực tế.

### 19.3. Guardrails

Theo dõi trong rollout:

- API p95/p99 và error rate.
- `DocumentValidationFailure`/`DuplicateKey`.
- MongoDB write/read latency.
- `totalDocsExamined`/`totalKeysExamined` của query nóng.
- Index build state.
- CPU/memory/disk IOPS, queue, free disk.
- Replication lag và member health.
- TTL deletions nếu thay retention.
- Business conversions/record counts.

Đặt threshold theo baseline/SLO nội bộ; không có “5% latency tăng là luôn cho phép” chung.

### 19.4. Không tự xóa dữ liệu để rollback

Một rollback tốt nhất nên **giữ nguyên dữ liệu**:

- Hide index mới hoặc unhide index cũ.
- Khôi phục validator cũ từ snapshot definition.
- Trở lại application query version trước nếu còn tương thích.
- Phục hồi runtime parameter cũ.
- Với startup config, dùng rolling rollback hợp lệ.

Nếu dữ liệu đã migrate/xóa TTL, rollback có thể cần **forward fix hoặc restore có kiểm soát**, không chỉ một lệnh đảo ngược.

## 20. Bảng khả năng rollback

| Thay đổi | Có thể quay lại bằng | Lưu ý |
| --- | --- | --- |
| Add index | Hide/drop index | Drop yêu cầu rebuild nếu cần lại |
| Unhide new index | Hide index | Planner/cache có thể thay đổi |
| Hide old index | Unhide old index | Thực hiện nhanh vì index còn được duy trì |
| Drop index | Recreate/rebuild từ definition | Tốn I/O/time; constraints có thể mất |
| Validator warn | Restore old validator/options | Vi phạm đã được chấp nhận vẫn còn |
| Validator strict/error | Restore previous level/action/rule | Những writes bị từ chối không tự được replay |
| Unique conversion | Quy trình đổi constraint/index theo docs | Không coi là toggle dễ đảo; duplicates/queries cần quản lý |
| TTL rút ngắn | Đổi TTL lại | Documents đã xóa **không tự khôi phục** |
| Runtime setParameter | Apply lại previous value | Kiểm tra persistence sau restart |
| Startup config | Rolling restart với config cũ | Cần giữ quorum và compatibility |
| FCV/major upgrade | Theo đường downgrade chính thức nếu còn hỗ trợ | Có thể không thể rollback nếu đã dùng feature mới |
| Data migration | Reverse migration có thể | Có thể mất thông tin nếu transform không đảo ngược |

Không hứa “mọi schema change đều rollback trong 1 phút” vì một số thay đổi phá hủy dữ liệu theo semantics.

## 21. Monitor rủi ro trong và sau change

### 21.1. Dashboard tối thiểu

```text
+-----------------------------+------------------------------+
| API p95 / p99 + error rate  | MongoDB read/write latency   |
+-----------------------------+------------------------------+
| Validation failures         | DuplicateKey rate            |
+-----------------------------+------------------------------+
| Index build progress        | Index size / disk free       |
+-----------------------------+------------------------------+
| Query plan/docs examined    | Index usage ($indexStats)    |
+-----------------------------+------------------------------+
| CPU / WiredTiger cache      | Disk IOPS / await / queue    |
+-----------------------------+------------------------------+
| Replication lag + elections | Migration progress/conflicts |
+-----------------------------+------------------------------+
| TTL deletions               | Config/version drift         |
+-----------------------------+------------------------------+
```

### 21.2. Monitoring theo thời gian, không một snapshot

Một index có thể làm p95 giảm ngay nhưng **write overhead** tăng sau vài ngày khi writes tăng. Validator có thể gây errors chỉ khi nightly job chạy. TTL có thể xóa nhiều dữ liệu khi đến ngưỡng tuổi.

Vì vậy cần:

- Giai đoạn monitoring sát sau deploy.
- Đo thêm ít nhất một chu kỳ nghiệp vụ quan trọng.
- So theo namespace, query shape và client version.
- Ghi lại thời điểm hide/unhide/reset metrics.
- Dùng absolute counters/rates đúng cách khi process restart.

### 21.3. Alert phân biệt sự cố với biến động bình thường

| Alert | Hướng điều tra |
| --- | --- |
| Index build lỗi | Duplicates, disk, quorum, conflict, version |
| Query latency tăng sau unhide/hide | Planner đã chọn plan nào, query shape nào |
| Validation errors tăng | Writer cũ, wrong BSON type, document legacy |
| DuplicateKey tăng | Data race, unique index mới, missing key semantics |
| TTL deletes tăng sau thay retention | Tính đúng lượng eligible và business policy |
| Replication lag tăng trong migration | Batch size, disk/CPU secondary, write concern |
| Disk free tụt khi index build | Index size/temp files, snapshots, growth |
| Config drift sau restart | Runtime parameter không persist, IaC chưa cập nhật |

Không tự hồi phục bằng cách drop index hoặc tắt validator khi một alert vừa xuất hiện; cần theo **decision tree và change owner**.

## 22. Runbook: index build chậm hoặc không hoàn tất

### 22.1. Quan sát

```text
Index build running 40 minutes
Disk queue rising
Replication lag growing
Primary is healthy
One voting secondary is unreachable
```

Có thể có kết hợp I/O pressure và **commit quorum waiting**. Không suy luận “server deadlock” chỉ từ thời gian build.

### 22.2. Quy trình

1. Xác nhận namespace/index name và change ticket.
2. Xem `currentOp`/logs build state và members nào tham gia.
3. Xem free disk/temp space trên mọi member.
4. Xem CPU, WiredTiger cache, IOPS, replication lag.
5. Kiểm tra voting members và commit quorum.
6. Có cần dừng batch jobs không cấp thiết?
7. Quyết định chờ, sửa node, hoặc abort theo runbook phù hợp.
8. Ghi nhận lỗi/tình trạng nếu build bị hủy.
9. Không chạy build thứ hai cùng index name một cách mù quáng.

Điều chỉnh commit quorum thấp hơn default có trade-off tính nhất quán/availability; không làm tùy ý.

## 23. Runbook: bật validator xong ứng dụng ghi lỗi

### 23.1. Tín hiệu

- `DocumentValidationFailure` tăng.
- Error rate của API insert/update tăng.
- Chỉ một phiên bản ứng dụng cũ hoặc ETL job bị ảnh hưởng.
- Data audits vẫn còn nhiều legacy invalid records.

### 23.2. Điều tra

1. Tìm validator/level/action hiện tại qua `getCollectionInfos`.
2. Xác định nhóm documents và BSON types vi phạm.
3. Tìm app versions và code paths chưa đổi.
4. Phân biệt **insert mới invalid** với **update legacy invalid**.
5. Kiểm tra privacy của error/log payload.
6. So với kế hoạch rollout và rollback thresholds.

### 23.3. Mitigation

Tùy mức độ nghiêm trọng:

- Fix/rollback writer code.
- Giảm level từ strict về moderate nếu đã phê duyệt và mục tiêu cho phép.
- Chuyển `error` về `warn` **chỉ như emergency exception có theo dõi**.
- Sửa dữ liệu cũ theo batch và retry các requests cần thiết.
- Không bật `bypassDocumentValidation` cho tất cả writers để né validator.

Phục hồi validator không tự replay những request đã thất bại; ứng dụng phải có idempotent retry/reconciliation.

## 24. Runbook: hide/drop index làm query chậm

Giả sử sau hide index cũ:

```text
Query p95: 50 ms -> 650 ms
DocsExamined: 200 -> 2,000,000
COLLSCAN on hot path
```

Hành động:

1. Xác nhận trước/sau query shape và index names.
2. Xem `explain` trên query đại diện có giới hạn.
3. Nếu index còn hidden, **unhide** là rollback khả dĩ.
4. Nếu đã drop, phải tạo lại có sizing/build plan; cân nhắc giảm tải/route traffic tạm.
5. Kiểm plan cache, filters, collation và query changes.
6. Đừng tăng connection pool để “che” COLLSCAN.
7. Ghi root cause để cập nhật index inventory.

## 25. Thực hành trên MongoDB test: index hidden + validator theo giai đoạn

### 25.1. Điều kiện và giới hạn

Bài thực hành chỉ sử dụng **MongoDB test deployment** hỗ trợ hidden indexes và `collMod` validator, với quyền tạo collection. Không áp lệnh vào production.

Thiết kế an toàn:

- Một database lab với **collection tên ngẫu nhiên riêng** cho mỗi lượt.
- Documents có `runId` riêng và `_id` ổn định.
- Có một legacy invalid document được tạo **trước khi validator bật**.
- Chỉ xóa document do chính lượt thử tạo.
- Không đổi cluster config/FCV, không chạy migration toàn hệ thống.
- Không drop database hoặc index đang được người khác dùng.

### 25.2. Tạo namespace riêng

```javascript
const lab = db.getSiblingDB("mongo_change_row380_lab");
const runId = "row380-" + new ObjectId().toHexString();
const collName = "orders_" + runId.replace(/-/g, "_");

if (lab.getCollectionNames().includes(collName)) {
  throw new Error("Collection name đã tồn tại; không ghi đè.");
}

lab.createCollection(collName);
const orders = lab.getCollection(collName);

printjson({
  database: lab.getName(),
  collection: orders.getName(),
  runId
});
```

### 25.3. Tạo một vài document trước validator

```javascript
const validId1 = new ObjectId();
const validId2 = new ObjectId();
const legacyId = new ObjectId();

orders.insertMany([
  {
    _id: validId1,
    runId,
    tenantId: "TENANT-LAB",
    status: "CREATED",
    amountCents: NumberInt(1000),
    createdAt: new Date()
  },
  {
    _id: validId2,
    runId,
    tenantId: "TENANT-LAB",
    status: "PAID",
    amountCents: NumberInt(2500),
    createdAt: new Date()
  },
  {
    _id: legacyId,
    runId,
    tenantId: "TENANT-LAB",
    status: "paid",            // legacy enum sai
    amountCents: "2500",       // legacy BSON type sai
    createdAt: new Date()
  }
]);

print("owned=" + orders.countDocuments({ runId }));
```

### 25.4. Tạo hidden compound index

```javascript
const indexName = "row380_tenant_status_created_v1";

orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: indexName, hidden: true }
);

printjson(orders.getIndexes());
```

Query planner không dùng index hidden. Khi thử:

```javascript
const q = {
  tenantId: "TENANT-LAB",
  status: "PAID"
};

printjson(
  orders.find(q)
    .sort({ createdAt: -1 })
    .limit(10)
    .explain("executionStats")
);
```

Sau đó unhide:

```javascript
orders.unhideIndex(indexName);

printjson(
  orders.find(q)
    .sort({ createdAt: -1 })
    .limit(10)
    .explain("executionStats")
);
```

Trên collection chỉ 3 documents, planner có thể **không dùng index** dù unhide vì COLLSCAN rẻ hơn. Điều đó không phải lỗi. Mục tiêu là hiểu eligibility của index, không chứng minh performance từ lab nhỏ.

### 25.5. Tạo validator

```javascript
const validator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["tenantId", "status", "amountCents"],
    properties: {
      tenantId: { bsonType: "string", minLength: 1 },
      status: { enum: ["CREATED", "PAID", "CANCELLED"] },
      amountCents: {
        bsonType: ["int", "long"],
        minimum: 0
      }
    }
  }
};
```

### 25.6. Bật `warn + moderate`

```javascript
lab.runCommand({
  collMod: collName,
  validator,
  validationLevel: "moderate",
  validationAction: "warn"
});
```

Document legacy vẫn tồn tại vì `collMod` không tự chuyển data. Đo:

```javascript
printjson(
  orders.find({
    runId,
    $nor: [validator]
  }).toArray()
);
```

Một test insert sai:

```javascript
const warnBadId = new ObjectId();

orders.insertOne({
  _id: warnBadId,
  runId,
  tenantId: "TENANT-LAB",
  status: "paid",
  amountCents: NumberInt(-5)
});
```

Với `warn`, MongoDB có thể cho phép insert và log validation violation. Chỉ dùng dữ liệu giả trên collection lab, và xem diagnostic logs nếu được phép (không cần quyền admin chỉ để chứng minh demo).

### 25.7. Đổi sang `moderate + error`

```javascript
lab.runCommand({
  collMod: collName,
  validator,
  validationLevel: "moderate",
  validationAction: "error"
});
```

Thử insert sai với một ID mới:

```javascript
const rejectedId = new ObjectId();

try {
  orders.insertOne({
    _id: rejectedId,
    runId,
    tenantId: "TENANT-LAB",
    status: "UNKNOWN",
    amountCents: NumberInt(-10)
  });
  print("UNEXPECTED: invalid document inserted");
} catch (e) {
  print("Expected validation error: " + e.codeName);
}
```

Nếu insert bị từ chối, document với `rejectedId` không xuất hiện. Trong phần viết tool chạy trên môi trường chưa rõ server version, cần kiểm tra error code/name; không giả định mọi driver báo cùng message.

### 25.8. Sửa riêng các document legacy của lab

Với dữ liệu thật, không được tự đổi status/amount vô căn cứ. Trong lab ta **biết trước** ý nghĩa những giá trị giả:

```javascript
const fixedLegacy = orders.updateOne(
  {
    _id: legacyId,
    runId,
    status: "paid",
    amountCents: "2500"
  },
  {
    $set: {
      status: "PAID",
      amountCents: NumberInt(2500)
    }
  }
);

const fixedWarn = orders.updateOne(
  {
    _id: warnBadId,
    runId,
    status: "paid",
    amountCents: NumberInt(-5)
  },
  {
    $set: {
      status: "CANCELLED",
      amountCents: NumberInt(0)
    }
  }
);

printjson({ fixedLegacy, fixedWarn });
```

Giá trị 0 ở demo là quy ước thử nghiệm; **không** đại diện quy trình sửa số tiền âm trên production. Sau đó:

```javascript
print("invalidOwned=" + orders.countDocuments({
  runId,
  $nor: [validator]
}));
```

### 25.9. Chuyển sang `strict + error`

Sau khi audit xác nhận dữ liệu thử đã đúng:

```javascript
lab.runCommand({
  collMod: collName,
  validator,
  validationLevel: "strict",
  validationAction: "error"
});
```

Kiểm tra validator được lưu:

```javascript
printjson(
  lab.getCollectionInfos({ name: collName })
);
```

Thử một update không hợp lệ trên document đã đúng:

```javascript
try {
  orders.updateOne(
    { _id: validId1, runId },
    { $set: { amountCents: "wrong type" } }
  );
  print("UNEXPECTED: invalid update accepted");
} catch (e) {
  print("Expected validation error: " + e.codeName);
}
```

Nếu validator hoạt động, update lỗi và document vẫn có amountCents kiểu hợp lệ.

### 25.10. Hide lại index nếu muốn mô phỏng rollback

```javascript
orders.hideIndex(indexName);
printjson(orders.getIndexes());
```

Không xóa vật lý index. Lab chỉ minh họa rằng hide/unhide là thao tác quản lý eligibility của query planner.

### 25.11. Dọn chỉ những document thuộc lượt thử

Kiểm tra:

```javascript
print("db=" + lab.getName());
print("collection=" + collName);
print("runId=" + runId);

const ownedDocs = orders.find(
  { runId },
  { _id: 1, runId: 1 }
).toArray();

printjson({
  ownedCount: ownedDocs.length,
  ownedIds: ownedDocs.map((x) => x._id)
});
```

Nếu chính bạn xác nhận đúng collection/runId và records thuộc lượt thử:

```javascript
for (const item of ownedDocs) {
  orders.deleteOne({
    _id: item._id,
    runId
  });
}

print("remaining=" + orders.countDocuments({ runId }));
```

Collection và index lab còn lại sau khi dọn data. Người quản trị lab có thể thu hồi **đúng collection tên ngẫu nhiên** theo quy trình môi trường, nhưng không dùng `dropDatabase()` hoặc `deleteMany({})` trên database chia sẻ.

## 26. Một mẫu change plan cho index mới trên production

### 26.1. Before

```text
[ ] Owner + approvals + scheduled window
[ ] Cluster/version/FCV/topology xác minh
[ ] Existing indexes và validator/export config đã lưu
[ ] Query plans và latency baseline
[ ] Disk/memory/IOPS headroom trên từng member
[ ] Replication healthy, không có index build khác
[ ] Data duplicates/constraints kiểm tra nếu unique
[ ] Có backup và recovery plan
[ ] App rollback/feature flag đã chuẩn bị
```

### 26.2. During

```text
1. Create index hidden (nếu phù hợp).
2. Observe index build progress, disk, CPU, replication.
3. Confirm build completed across relevant nodes.
4. Unhide at change checkpoint.
5. Compare query plans + p95/p99, error rate, writes.
6. Hold/continue/rollback based on defined guardrails.
7. Record timestamp, operator and results.
```

### 26.3. After

```text
[ ] No unexplained query regressions
[ ] No new write failures / DuplicateKey surprises
[ ] Replication and disk within budget
[ ] Index owner/use cases documented
[ ] Previous index kept until representative observation
[ ] Rollback/forward-fix state clear
[ ] Review after business cycle/nightly jobs
```

Đây là **mẫu runbook**, không phải đánh giá Content QA của bài học.

## 27. Một mẫu change plan cho validator

Trước khi bật `error`:

- Audit violators theo BSON types và business meaning.
- Đảm bảo tất cả services, ETL, migrations, admin scripts ghi đúng.
- Bắt đầu với `moderate + warn` nếu hiện trạng nhiều legacy data.
- Theo dõi warning trend và log volume.
- Chuyển `moderate + error` khi nguồn vi phạm mới được xử lý.
- Backfill legacy với idempotency/compare-and-set.
- Chuyển `strict + error` khi có bằng chứng đầy đủ.
- Chỉ dùng `constraint` MongoDB 9.0+ khi đã chuẩn bị và hiểu hạn chế.

Rollback có thể khôi phục validator/options trước, nhưng không tự sửa dữ liệu mới đã được chấp nhận dưới `warn` hoặc các request bị từ chối dưới `error`.

## 28. Một mẫu change plan cho server configuration

Trước khi `setParameter`, sửa `mongod.conf` hoặc FCV:

1. Xác định parameter nằm ở **runtime/startup/cluster** nào.
2. Đọc tài liệu chính thức của đúng MongoDB/FCV và edition.
3. Snapshot config và thông số hiện tại.
4. Xác định thay đổi có cần restart, election, rolling order.
5. Kiểm TLS/auth/network và khả năng driver reconnect.
6. Thử staging + rollback.
7. Lập kế hoạch backup, downtime window và communication.
8. Triển khai từng node theo supported procedure.
9. Xác minh giá trị observed/runtime sau restart.
10. So latency, error rate, replication và logs.

Không tự thay đổi cấu hình bảo mật, durability hoặc eviction/cache “chỉ để test” trên production nếu thiếu phê duyệt.

## 29. Những sai lầm dễ gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Tạo index trên 100 triệu documents mà không xem free disk | Index build/temp files có thể đầy disk | Dự báo, monitor từng member |
| “Online build không ảnh hưởng writes” | Có locks đầu/cuối, CPU/IOPS và commit quorum | Đo, chọn window, guardrails |
| “Index mới chắc chắn được planner dùng” | Planner phụ thuộc query/cost | Dùng explain/latency |
| “Hidden index không tiêu tài nguyên” | Vẫn duy trì trên writes và chiếm disk | Tính write overhead |
| “Hide unique là tắt unique” | Unique vẫn enforce | Không dùng hide để nới constraint |
| “Hide TTL để tạm dừng xóa” | Hidden TTL vẫn expire | Thay retention có quản trị |
| “Có thể hint hidden index” | Hidden index không eligible | Unhide có kiểm soát |
| “Index không có ops trong 1 giờ nên drop” | Có nightly/monthly jobs | Quan sát chu kỳ đại diện |
| “Drop index rollback bằng unhide” | Đã mất index vật lý | Phải rebuild |
| “Unique index sẽ tự hợp nhất duplicates” | Build/conversion lỗi khi gặp duplicates | Audit và xử lý theo nghiệp vụ |
| “prepareUnique quét sạch duplicates cũ” | Chỉ ngăn duplicate mới | DryRun và remediation |
| “Rút TTL không làm gì đến data cũ” | Có thể xóa hàng loạt | Count eligible, legal review |
| “`collMod` sửa mọi document sai” | Không retro-migrate dữ liệu | Audit + backfill |
| “strict validator nghĩa collection hiện toàn valid” | Legacy invalid vẫn có thể tồn tại | Audit/reconcile |
| “moderate chặn mọi update legacy sai” | Existing invalid được xử lý linh hoạt | Hiểu level và dùng strict sau migrate |
| “warn bảo đảm dữ liệu không xấu” | Warn cho ghi đi qua | Dùng để quan sát, rồi error |
| “error rollback thì request cũ tự chạy lại” | Errors đã xảy ra không tự replay | Idempotent retry/reconciliation |
| “Dùng bypass cho mọi migration” | Làm yếu invariant và audit | Giới hạn quyền, mục đích |
| “Thêm schemaMap client tự migrate dữ liệu cũ” | Không retro-process collection | Expand–migrate–contract |
| “Đổi `setParameter` là persist mãi” | Nhiều runtime settings mất khi restart | Config management + drift check |
| “Mọi config có thể đổi runtime” | Có startup-only/managed limits | Kiểm version và scope |
| “Đổi FCV tùy ý để bật feature” | FCV gắn upgrade path/downgrade | Theo documented procedure |
| “Canary app giới hạn mọi DDL chỉ cho một nhóm user” | Validator/index là collection-global | Shadow/staging và rollback |
| “Replica set chỉ cần kiểm primary” | Index build/replication ảnh hưởng mọi member | Monitor tất cả data-bearing members |
| “Explain nhanh = toàn hệ nhanh” | Không đại diện traffic/cache/p99 | Theo dõi production SLO |
| “Migration ghi đè dựa trên _id là đủ” | Concurrent updates có thể mất | Compare-and-set/version |
| “Sau migration có thể xóa backups ngay” | Rollback/retention có thể cần | Giữ theo policy |
| “Lỗi TTL có thể đảo một option là xong” | Data đã xóa không tự hồi phục | Recovery plan trước |
| “MongoDB có validator nên không cần auth” | Validator không kiểm quyền tenant | RBAC + application authorization |

## 30. Bài tập vận dụng

### Bài A — Lập kế hoạch index

Một collection 80 triệu orders có query:

```javascript
find({ tenantId, status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(30)
```

Hãy thiết kế compound index, giải thích thứ tự field, thống kê cần đo, vì sao hidden index hữu ích và giới hạn của hidden khi muốn canary.

### Bài B — Tìm duplicate trước unique

Dữ liệu:

```javascript
{ tenantId: "T1", externalOrderId: "A1" }
{ tenantId: "T1", externalOrderId: "A1" }
{ tenantId: "T2", externalOrderId: "A1" }
```

1. Nếu unique key là `{tenantId,externalOrderId}`, cặp nào conflict?
2. Vì sao không tự xóa record trùng?
3. Lộ trình `prepareUnique → dryRun → unique` ra sao?
4. Sharded collection cần xét shard key thế nào?

### Bài C — Rút TTL

Session documents đã tồn tại trong 40 ngày. TTL được đổi từ 60 ngày xuống 7 ngày.

1. Những session nào có thể trở thành eligible deletion?
2. Thao tác hide index có tạm dừng xóa không?
3. Vì sao cần backup/legal review?
4. Cần giám sát replication lag và IOPS ra sao?

### Bài D — Đổi validator trên legacy data

Có:

```javascript
{ status: "paid", amountCents: "1000" }
{ status: "PAID", amountCents: NumberInt(1000) }
```

Validator yêu cầu `status:"PAID"` và `amountCents` kiểu int/long.

1. `collMod` có tự sửa document thứ nhất không?
2. So `warn`, `moderate+error` và `strict+error`.
3. Nếu service cũ sửa trường `note` trên document thứ nhất thì có thể xảy ra gì?
4. Hãy thiết kế migration có kiểm chứng.

### Bài E — Thêm field bắt buộc

Đội phát triển muốn `currency` trở thành required string cho tất cả invoices.

1. Vì sao không bật strict validator trước khi mọi client ghi currency?
2. Expand–migrate–contract triển khai thế nào?
3. Dữ liệu cũ thiếu currency phải được suy ra từ nguồn nào?
4. Khi nào mới bỏ code đọc field legacy?

### Bài F — Đổi config runtime

Một operator chạy `setParameter` trong giờ cao điểm, thay đổi biến mất sau restart.

1. Vì sao?
2. Cần ghi vào config management gì?
3. Kiểm observed vs desired config ra sao?
4. Thế nào là startup-only settings?

### Bài G — FCV và upgrade

Một service muốn dùng feature của MongoDB 9.0, nhưng binary mới đã cài còn FCV chưa nâng.

1. Tại sao feature có thể chưa khả dụng?
2. Vì sao không đổi FCV trước rolling binary upgrade?
3. Cần kiểm driver, backup và downgrade path nào?
4. Ai phê duyệt bước irreversible trong release?

### Bài H — Index build chờ commit quorum

Một voting secondary unavailable; build trên primary đã scan xong nhưng chưa ready.

1. Commit quorum tác động thế nào?
2. Tại sao không giảm quorum vội?
3. Cần kiểm node/disk/log gì?
4. Làm sao kiểm năng lực build sau khi member trở lại?

### Bài I — Thiết kế rollback

Sau hide index cũ, p99 từ 90 ms lên 2.5 s. Index cũ vẫn hidden.

1. Lệnh nào giúp phục hồi eligibility nhanh?
2. Vì sao drop đã làm việc này khó hơn?
3. Có cần xem plan cache và query shapes không?
4. SLO và thời gian theo dõi nào làm rollback hợp lý?

### Bài J — Migration tiền tệ

Một số field `amount` là chuỗi VND, số khác là “đồng đã nhân 100”. Nhiệm vụ migrate sang `amountCents:Long`.

1. Tại sao không thể tự nhân 100 cho mọi bản ghi?
2. Cần metadata/nguồn nào để chuẩn hóa?
3. Thiết kế update có version/filter.
4. Làm thế nào nhận diện conflicts, retry idempotently và audit?

### Bài K — Managed MongoDB

Tài liệu hướng dẫn một startup YAML trên self-managed MongoDB, nhưng dịch vụ thực tế dùng Atlas.

1. Vì sao không sửa trực tiếp `mongod.conf`?
2. Cần xem controls nào của Atlas?
3. Metric/quyền nào có thể khác?
4. Ai sở hữu rolling upgrade/backup/change window?

### Bài L — Chuỗi thay đổi liên quan

Một dự án vừa đổi index, vừa chuẩn hóa BSON type và dự định xóa field cũ.

Hãy lập kế hoạch ít nhất 5 phases, cho mỗi phase ghi:

- Preconditions.
- Lệnh/cấu hình thay đổi.
- Metric thành công.
- Rủi ro/race.
- Phương án rollback hoặc forward fix.
- Thời điểm báo cho application owners.

## 31. Tài liệu tham khảo chính thức

Những chi tiết thay đổi theo MongoDB server version, FCV, driver và topology. Trước khi chạy DDL production, kiểm tra đúng tài liệu release và quyền thực tế:

- [Indexes](https://www.mongodb.com/docs/manual/indexes/) — các loại index và sử dụng.
- [Index Builds on Populated Collections](https://www.mongodb.com/docs/manual/core/index-creation/) — build process, locks, replicated index builds, commit quorum và resource requirements.
- [Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/) — hide/unhide, unique/TTL semantics, `$indexStats` reset.
- [`createIndexes` command](https://www.mongodb.com/docs/manual/reference/command/createIndexes/) — cú pháp và options.
- [`collMod` command](https://www.mongodb.com/docs/manual/reference/command/collMod/) — validator, validationLevel/action, TTL, hidden và convert-to-unique.
- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — `$jsonSchema`, tác động trên existing documents.
- [Specify Validation Level](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/) — moderate, strict, constraint (nếu có).
- [Handle Invalid Documents](https://www.mongodb.com/docs/manual/core/schema-validation/handle-invalid-documents/) — warn/error/errorAndLog.
- [Convert an Existing Index to a Unique Index](https://www.mongodb.com/docs/manual/core/index-unique/convert-to-unique/) — prepareUnique, dryRun và khắc phục duplicates.
- [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — dữ liệu được xóa theo TTL và hành vi monitor.
- [`$indexStats`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/) — cách đọc index usage.
- [`getCmdLineOpts`](https://www.mongodb.com/docs/manual/reference/command/getCmdLineOpts/) — cấu hình startup đã parse.
- [`getParameter` / `setParameter`](https://www.mongodb.com/docs/manual/reference/command/setParameter/) — runtime parameters và điều kiện hỗ trợ.
- [Upgrade a Replica Set](https://www.mongodb.com/docs/manual/release-notes/) — release notes, FCV/upgrade path.
- [MongoDB Atlas Monitoring](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/) — metrics managed service.
- [Rolling Index Builds](https://www.mongodb.com/docs/manual/core/rolling-index-builds/) — ngoại lệ, trade-offs và cảnh báo.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — xác nhận ghi và những tình huống không rõ kết quả.

**Lưu ý:** tài liệu hiện hành có thêm các khả năng ở MongoDB 8.1 và 9.0; không giả định chúng tồn tại trên 6.0/7.0/8.0. Hidden indexes, unique conversion và các options `collMod` phải được xác minh đúng server/FCV trước khi áp dụng.

## 32. Kết luận

**Quản lý thay đổi index, validator và cấu hình trên dữ liệu thật** là quy trình vận hành nhiều giai đoạn, không chỉ là chạy một lệnh DDL.

- **Index:** chọn từ query pattern, xây với capacity headroom, cân nhắc hidden trước khi drop, bảo vệ unique/TTL semantics, theo dõi commit quorum và query plans.
- **Validator:** đừng coi `collMod` là phép tự sửa legacy data. Từ `warn` tới `moderate+error`, migrate rồi `strict+error`, kết hợp kiểm tra dữ liệu và tương thích của mọi writers.
- **Cấu hình:** phân biệt driver/runtime/startup/cluster/FCV, biết yêu cầu restart, persistence, deployment ownership và khả năng downgrade.
- **Dữ liệu thật:** migration cần idempotency, compare-and-set, audit, retention, backup và quyền hạn. Rollback không thể phục hồi tự động những document đã bị TTL xóa hoặc data transform mất thông tin.
- **Quan sát:** p95/p99, error rate, disk/CPU, replication, index build/usage, validation errors và business outcomes phải cùng được theo dõi từ baseline tới sau rollout.

**Nguyên tắc cốt lõi:** trước mỗi thay đổi, hãy xác định **đối tượng nào sẽ bị tác động, điều kiện thành công, bằng chứng an toàn, cách phát hiện lỗi và đường phục hồi**. Một thay đổi tốt không chỉ làm hệ thống chạy nhanh hoặc dữ liệu đúng hơn; nó còn phải có thể triển khai và vận hành an toàn khi người dùng vẫn đang sử dụng MongoDB.
