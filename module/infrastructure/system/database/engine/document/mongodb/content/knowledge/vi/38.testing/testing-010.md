# Kiểm thử hiệu năng và kế hoạch truy vấn mà không phụ thuộc chỉ số thời gian ngẫu nhiên

> **Module:** Database Engine Document MongoDB  
> **Chương:** Kiểm thử  
> **Bài học:** Kiểm thử hiệu năng và kế hoạch truy vấn mà không phụ thuộc chỉ số thời gian ngẫu nhiên

## 1. Bài toán: một query chậm hôm nay nhưng chạy nhanh ngày mai?

Một đội phát triển Java viết API:

~~~javascript
db.orders.find({
  tenantId: "tenant-03",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(10);
~~~

Họ tạo một test đơn giản:

~~~java
long start = System.nanoTime();

List<Document> result = orders.find(filter)
        .sort(descending("createdAt"))
        .limit(10)
        .into(new ArrayList<>());

long elapsedMs =
        TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - start);

assertTrue(elapsedMs < 100);
~~~

Test này có thể vượt qua trên laptop của một developer nhưng thất bại trên CI. Một phút sau chạy lại thì vượt qua. Truy vấn không đổi; index không đổi; kết quả vẫn đúng.

Vì sao?

- CI runner chia sẻ CPU với các tác vụ khác.
- JVM/JIT chưa warm up.
- MongoDB vừa khởi động, WiredTiger cache lạnh.
- DNS/TLS/connection pooling gây dao động.
- Hệ điều hành đang flush page cache hoặc thực hiện I/O.
- Query planner vừa chọn plan; một lượt khác dùng plan cache.
- Số lượng background writes/compaction/checkpoint thay đổi.
- Container bị CPU throttling.
- Network scheduling thay đổi.
- Dataset test quá nhỏ để một lần dùng collection scan khác biệt rõ với index scan.

Vấn đề chính: **thời gian đo được là kết quả của cả môi trường**, không phải một đặc tả ổn định của query.

Kiểm thử hiệu năng MongoDB nên được chia thành hai tầng:

1. **Kiểm thử hồi quy hiệu quả truy vấn có tính quyết định cao**: dữ liệu cố định, kết quả đúng, index contract, `explain("executionStats")`, `docsExamined`, `keysExamined`, `nReturned`, query shape và các ràng buộc chi phí scan.
2. **Benchmark/kiểm thử tải**: đo latency p50/p95/p99, throughput, CPU, I/O và tài nguyên trên môi trường có kiểm soát, dùng phương pháp thống kê và đánh giá xu hướng; không đặt một assertion milliseconds quá cứng cho mỗi lần chạy CI.

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Hiểu vì sao assertion `executionTimeMillis < 50` hoặc `System.nanoTime() < 100ms` thường flaky.
- Đọc đúng `queryPlanner` và `executionStats`.
- Phân biệt `IXSCAN`, `COLLSCAN`, `FETCH`, blocking `SORT`, covered queries và các biến thể query engine.
- Viết assertion dựa trên **chi phí scan có ngân sách**, không dựa vào từng millisecond.
- Dùng dataset và query shape có tính đại diện nhưng tái lập được.
- Chọn các chỉ số mạnh như `totalDocsExamined`, `totalKeysExamined`, `nReturned` và index specification.
- Tránh test phụ thuộc chính xác vào toàn bộ cây `winningPlan`.
- Thử nghiệm có/không có index bằng `hint` và negative control.
- Tạo JUnit integration test với MongoDB Java Sync Driver.
- Hiểu vai trò của Testcontainers, môi trường CI riêng và seed dữ liệu cố định.
- Nhận diện tác động của plan cache, classic engine, SBE, sharding và MongoDB version.
- Phân biệt performance regression gate với benchmarking thống kê.
- Thiết kế quy trình xử lý khi test kế hoạch truy vấn thất bại.

---

## 2. Ba loại kiểm thử thường bị trộn lẫn

| Loại | Câu hỏi | Chỉ số nên dùng | CI mỗi commit? |
|---|---|---|---|
| **Correctness test** | Query có trả đúng dữ liệu không? | Documents, thứ tự, filter, projection | Có |
| **Query efficiency regression test** | Query có quét ít dữ liệu và dùng index phù hợp không? | Explain metrics, index catalog, scan budget | Có, nếu fixture ổn định |
| **Performance benchmark** | Trên hạ tầng này query đạt latency/throughput nào? | p50/p95/p99, ops/s, CPU, cache/I/O, error rate | Có thể chạy riêng/định kỳ |

### 2.1. Correctness không chứng minh hiệu năng

Hai kế hoạch sau có thể cùng trả đúng mười documents:

```text
Plan A:
  IXSCAN tenantId/status/createdAt
  docsExamined = 10
  nReturned = 10

Plan B:
  COLLSCAN trên 100.000 documents
  blocking SORT
  docsExamined = 100000
  nReturned = 10
```

Unit test kiểm tra kết quả có thể pass với cả hai.

### 2.2. Query efficiency không chứng minh SLA thời gian

Query có `docsExamined = 10` vẫn có thể chậm khi:

- Storage I/O bị nghẽn.
- Server đang failover.
- Connection pool cạn.
- Network RTT cao.
- Documents rất lớn.
- Write lock/resource contention.
- Query chạy trong aggregation phức tạp.
- Application serialization bị nghẽn.

Vì vậy efficiency assertions không thay benchmark và production monitoring.

### 2.3. Benchmark không thay kiểm thử correctness/plan

Một benchmark cho kết quả 30 ms hôm nay có thể che dấu việc planner dùng `COLLSCAN`, bởi dataset mới nhỏ hoặc toàn bộ document nằm trong RAM. Khi collection tăng lên 10 triệu documents, latency có thể tăng mạnh.

Kiểm thử tốt kết hợp cả ba lớp, nhưng **không dùng cùng một assertion để đo mọi thứ**.

---

## 3. Những chỉ số thời gian không nên dùng làm điều kiện pass/fail đơn lẻ

### 3.1. Đo ở ứng dụng Java

~~~java
long elapsed = System.nanoTime() - start;
assertTrue(elapsed < TimeUnit.MILLISECONDS.toNanos(50));
~~~

Nguồn nhiễu:

- JVM warmup/JIT.
- GC/safepoint.
- Thread scheduling.
- Driver server selection.
- Connection checkout.
- TLS/network.
- Test runner load.
- BSON decoding.
- MongoDB server load.

### 3.2. Đo bằng mongosh

~~~javascript
const t0 = Date.now();
db.orders.find({ status: "PAID" }).toArray();
print(Date.now() - t0);
~~~

Đây là phép đo end-to-end phụ thuộc client, process và machine conditions. Nó hữu ích để quan sát nhanh nhưng không phù hợp làm invariant cứng của query plan.

### 3.3. executionStats.executionTimeMillis

MongoDB `explain("executionStats")` trả về thông số:

```javascript
{
  executionStats: {
    executionTimeMillis: 3,
    totalKeysExamined: 10,
    totalDocsExamined: 10,
    nReturned: 10
  }
}
```

Tài liệu chính thức nhấn mạnh `executionTimeMillis` **không nhất thiết đại diện thời gian chạy thực tế**. Explain có thể gồm chi phí chọn plan, bỏ qua plan cache; hoạt động production với cached plan hoặc hint có chi phí khác.

Không viết:

~~~javascript
const plan = db.orders.find(filter)
  .explain("executionStats");

if (plan.executionStats.executionTimeMillis > 10) {
  throw new Error("Query regression");
}
~~~

như một assertion bắt buộc trên mọi máy CI.

### 3.4. allPlansExecution không làm timing ổn định hơn

`allPlansExecution` cung cấp thông tin về trial execution của các candidate plans ngoài winning plan. Nó hữu ích khi cần hiểu planner lựa chọn thế nào, không khiến milliseconds trở thành một đặc tả ổn định.

### 3.5. Cách dùng thời gian đúng chỗ

Dùng latency/throughput trong **benchmark environment riêng**, thu nhiều mẫu, đo percentiles, mô tả hardware/dataset/concurrency, lưu lịch sử và phân tích variance. Không gộp benchmark đó với một single-shot query-plan test.

---

## 4. Explain: ba mức verbosity

MongoDB hỗ trợ:

1. `queryPlanner`.
2. `executionStats`.
3. `allPlansExecution`.

### 4.1. queryPlanner

Ví dụ:

~~~javascript
db.orders.find({
  tenantId: "tenant-03",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(10).explain("queryPlanner");
~~~

Trả về thông tin query planner và winning/rejected plans, không yêu cầu đầy đủ execution stats.

### 4.2. executionStats

~~~javascript
db.orders.find({
  tenantId: "tenant-03",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(10).explain("executionStats");
~~~

Ở mức này MongoDB thực thi winning plan để đưa ra statistics. Đây là lựa chọn chính cho **efficiency regression test**.

### 4.3. allPlansExecution

~~~javascript
db.orders.find({
  tenantId: "tenant-03",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(10).explain("allPlansExecution");
~~~

Thêm partial execution statistics của các candidate plans trong quá trình chọn kế hoạch. Không dùng raw statistics của rejected plans như các con số của full query execution.

### 4.4. Lưu ý default khác nhau giữa command và helpers

`cursor.explain()` và `db.collection.explain()` thường mặc định `queryPlanner`, còn database `explain` command có default khác theo API.

Vì vậy test nên luôn ghi **verbosity tường minh**, không dựa vào default ngầm.

### 4.5. Explain có thực thi thao tác ghi không?

Theo MongoDB docs, explain cho write operations mô tả việc tìm records và các modifications **sẽ** thực hiện, nhưng bản thân explain **không áp dụng modifications** vào database.

Dù vậy, production test không nên biến explain trên bulk write phức tạp thành cách gây tải; executionStats vẫn có thể tốn tài nguyên để đánh giá predicates.

---

## 5. Hai phần output quan trọng: queryPlanner và executionStats

Một explain output **được rút gọn để minh họa**:

~~~javascript
{
  queryPlanner: {
    namespace: "plan_lab.orders",
    winningPlan: {
      stage: "LIMIT",
      inputStage: {
        stage: "FETCH",
        inputStage: {
          stage: "IXSCAN",
          indexName: "idx_tenant_status_created",
          keyPattern: {
            tenantId: 1,
            status: 1,
            createdAt: -1
          }
        }
      }
    }
  },
  executionStats: {
    nReturned: 10,
    executionTimeMillis: 2,
    totalKeysExamined: 10,
    totalDocsExamined: 10
  }
}
~~~

**Không coi đây là schema đảm bảo của MongoDB.** Cây winningPlan khác giữa classic engine, Slot-Based Execution (SBE), EXPRESS fast paths, sharded clusters và MongoDB versions.

### 5.1. queryPlanner

Cho biết:

- Namespace/query shape.
- Winning plan.
- Rejected plans (khi có).
- Indexes mà planner cân nhắc.
- Một số thông tin plan cache/query identifiers tùy server version.

### 5.2. executionStats

Cho biết các metrics của winning plan:

- `nReturned`.
- `totalDocsExamined`.
- `totalKeysExamined`.
- `executionTimeMillis` (dùng tham khảo, không làm CI hard threshold).
- Execution stage details và counters khác theo engine.

### 5.3. Tại sao nên assert tổng scan thay vì timings?

Với dataset cố định, query có index tốt thường quét ít keys/docs hơn rất nhiều so với collection scan. Chỉ số scan thể hiện **khối lượng công việc logic** tương đối ổn định hơn sự dao động của OS/network.

Nhưng scan counters **cũng không phải bất biến tuyệt đối**: có thể đổi khi planner/engine/index/data thay đổi. Cần thiết kế budget hợp lý và test theo ý định, không chỉ khóa một con số đúng đến từng đơn vị.

---

## 6. Các chỉ số tốt cho regression test

| Field | Câu hỏi | Test phù hợp |
|---|---|---|
| `executionStats.nReturned` | Query trả bao nhiêu rows? | Expected result với fixture cố định |
| `executionStats.totalDocsExamined` | Bao nhiêu documents đã xét? | Upper bound theo result/budget |
| `executionStats.totalKeysExamined` | Bao nhiêu index entries đã xét? | Upper bound với query có index |
| `queryPlanner.winningPlan` | Planner chọn access path gì? | Kiểm tra index/stage với parser linh hoạt |
| `indexName` | Index nào được sử dụng? | Index contract khi thật sự quan trọng |
| `keyPattern` | Index key order? | Kiểm tra schema index riêng |
| `SORT` stage | Có blocking sort không? | Có thể kiểm tra theo engine/version |
| `COLLSCAN` stage | Có collection scan không? | Quan sát; cần xét dataset/context |
| `totalKeysExamined/nReturned` | Scan efficiency với index | Heuristic/budget |
| `executionTimeMillis` | Thời gian explain ước lượng | Chỉ ghi nhận, không hard gate |

### 6.1. Đừng kiểm tra docsExamined bằng đúng một giá trị ở mọi bản

Tránh:

~~~java
assertEquals(10, docsExamined);
~~~

Thay bằng:

~~~java
assertTrue(docsExamined <= 25);
~~~

khi fixture và business query bảo đảm chỉ cần lấy 10 documents qua index tốt.

Vì sao để budget? Planner/index coverage/mapping/optimizer khác nhau có thể tạo một chút thay đổi hợp lý trong số lượng examined. Bạn chỉ cần chặn regression kiểu 10 → 50.000, không phải khóa micro-detail.

### 6.2. Không dùng ratio khi nReturned=0 mà không xử lý

Một heuristic:

```text
scanRatio = docsExamined / max(nReturned, 1)
```

Nếu nReturned = 0, ratio vẫn có nghĩa tham khảo nhưng không nên tuyên bố đây là tỷ lệ thực giữa documents scanned và returned.

Trong test, có thể dùng **absolute upper bound**, cộng với result correctness.

### 6.3. totalKeysExamined=0 không tự chứng minh query tốt

Nếu `totalKeysExamined=0` và `totalDocsExamined=100000`, query có thể dùng collection scan. Vì vậy chỉ test `keysExamined < 30` là chưa đủ.

### 6.4. docsExamined=0 có thể là tín hiệu tốt

Một **covered query** có thể chỉ đọc index keys, trả đủ dữ liệu mà không fetch documents. Khi đó `totalDocsExamined=0` hoàn toàn hợp lý.

Không viết test yêu cầu `docsExamined >= nReturned` cho mọi query.

### 6.5. nReturned không luôn là số business entities toàn API

Aggregation/group, pagination, cursor batches và sharded pipelines có semantics khác. Với query trả 10 documents sau limit, `nReturned=10` thường dễ kiểm thử. Nhưng với pipeline `$group` trả 1 aggregate row từ 100k documents, đó không phải 1 document scanned.

---

## 7. IXSCAN, COLLSCAN, FETCH và các stages liên quan

### 7.1. IXSCAN

`IXSCAN` thể hiện việc duyệt entries trong index. Trường liên quan có thể gồm:

- `indexName`.
- `keyPattern`.
- `indexBounds`.
- `direction`.

Một IXSCAN không tự bảo đảm hiệu năng tốt: nếu index range rộng và scan cả triệu keys, query vẫn tốn nhiều tài nguyên.

### 7.2. COLLSCAN

`COLLSCAN` duyệt documents trong collection. Nó có thể tốn kém với query lọc chọn lọc trên collection lớn.

Nhưng COLLSCAN **không luôn là bug**:

- Collection rất nhỏ.
- Query cần xem gần như toàn bộ documents.
- Một tác vụ analytics/full scan là chủ đích.
- Optimizer đánh giá index không có lợi.

CI test nên cấm COLLSCAN **chỉ khi workload contract yêu cầu index access**, không phải trên mọi MongoDB query.

### 7.3. FETCH

`FETCH` thường chỉ ra MongoDB cần lấy document sau khi scan index. Nếu projection được covered bởi index, FETCH có thể biến mất hoặc bị tối ưu khác tùy engine.

### 7.4. SORT

Một blocking SORT stage có thể phát sinh khi index không phục vụ sort order phù hợp. Cần xem:

- Filter equality prefix.
- Index key order.
- Sort direction.
- Collation.
- Multikey constraints.
- Whether sort can be satisfied by index.

Không đơn giản nhìn `SORT` là luôn tệ: query analytics cần sort toàn tập có thể chấp nhận được.

### 7.5. SBE và EXPRESS stages

Các MongoDB versions hiện đại có Slot-Based Execution Engine; một số fast paths có `EXPRESS_IXSCAN`/`EXPRESS_CLUSTERED_IXSCAN` thay vì stage `IXSCAN` thông thường.

Viết assertion:

~~~text
winningPlan.stage == "IXSCAN"
~~~

sẽ dễ thất bại khi engine thay đổi dù query vẫn hiệu quả.

### 7.6. Cây plan không có một đường dẫn JSON cố định

Ví dụ classic:

```text
queryPlanner.winningPlan.inputStage.inputStage.stage
~~~

Ví dụ SBE có thể xuất hiện:

```text
queryPlanner.winningPlan.queryPlan.stage
queryPlanner.winningPlan.slotBasedPlan
~~~

Sharded output có thể chứa các nhánh per-shard. Không giả định `winningPlan.inputStage.stage` tồn tại ở mọi cluster/version.

---

## 8. Nguyên tắc xây test ổn định

### 8.1. Test đúng ba thứ

1. **Dữ liệu trả đúng**.
2. **Index/shape đủ điều kiện**.
3. **Work examined không vượt budget**.

### 8.2. Tránh hardcode những thứ chỉ có tính chẩn đoán

Không gate CI bằng:

- `executionTimeMillis` cụ thể.
- `executionTimeMillisEstimate` của stage.
- `planCacheKey` hoặc query hash cố định.
- Số nested stages exact.
- Mọi field trong JSON explain.
- Thứ tự rejected plans.
- Plan candidate score.
- Raw timestamp/host/queryPlanner internals.

### 8.3. Dùng budget với biên an toàn

Ví dụ:

```text
Expected nReturned = 10
Good path docsExamined ~ 10
Collection scan docsExamined ~ 20000

CI budget:
  totalDocsExamined <= 100
  totalKeysExamined <= 200
~~~

Biên an toàn vẫn rất nhỏ so với regression 20.000 docs.

### 8.4. Budget phải dựa trên số liệu và bài toán, không đoán

Tạo fixture đại diện, xem explain với index đúng, sau đó chọn budget đủ rộng để không khóa một plan implementation, nhưng đủ chặt để phát hiện scan tăng một bậc độ lớn.

### 8.5. Test không được tạo ra tình huống ngẫu nhiên

Không seed data bằng:

~~~javascript
Math.random()
~~~

không có seed cố định rồi kỳ vọng selectivity giống nhau qua mỗi CI run.

Dùng deterministic data generation và kiểm tra cardinality.

---

## 9. Fixture đủ lớn, có tính chọn lọc rõ ràng

Một dataset chỉ 5–10 documents thường khiến COLLSCAN vẫn là lựa chọn hợp lý. Nếu test muốn ngăn regression thiếu index, cần nhiều dữ liệu hơn.

### 9.1. Thiết kế fixture

Ví dụ 8 tenants, mỗi tenant 1000 orders:

```text
8 tenants × 1000 orders = 8000 documents

Mỗi tenant:
  500 PAID
  500 PENDING

Query:
  tenantId = tenant-03
  status = PAID
  sort createdAt desc
  limit 10
~~~

Mục tiêu:

- Có 500 matches theo tenant+status.
- Index tốt chỉ cần xét gần 10 entries.
- Collection scan phải kiểm tra nhiều documents.
- Kết quả có thể tính trước.
- Thứ tự sort tái lập được.

### 9.2. Schema mẫu

```json
{
  "_id": "tenant-03-0998",
  "tenantId": "tenant-03",
  "status": "PAID",
  "amount": 998,
  "createdAt": {
    "$date": "2026-01-01T16:38:00Z"
  }
}
```

Các giá trị cố định cho phép assertions chính xác về dữ liệu.

### 9.3. Index phù hợp

```javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1
  },
  {
    name: "idx_tenant_status_created"
  }
);
~~~

- `tenantId` là equality field.
- `status` là equality field.
- `createdAt` là sort field.

Đây là mẫu áp dụng nguyên tắc ESR (Equality, Sort, Range). Không tự coi nó là index tối ưu cho mọi workload.

### 9.4. Vì sao không dùng _id mặc định?

Index `_id` giúp tìm một document bằng ID, nhưng query lọc tenant/status và sort createdAt không được phục vụ đầy đủ bởi `_id` index nếu không có predicate thích hợp.

### 9.5. Tài nguyên CI

8.000 documents là kích thước minh họa. Có thể dùng 2.000, 20.000 hoặc mức khác tùy CI capacity. Điểm quan trọng là tạo **khoảng cách đủ lớn** giữa plan tốt và plan xấu.

---

## 10. Tạo fixture bằng mongosh

Chạy trong **database lab chuyên dụng**. Không chạy trên production.

### 10.1. Chuẩn bị database

```javascript
const lab = db.getSiblingDB("plan_lab");
const orders = lab.getCollection("orders");
~~~

Các lệnh sau giả định `plan_lab.orders` trống. Nếu đã có dữ liệu test từ trước, hãy dùng một database cô lập mới hoặc thực hiện cleanup theo quyền và quy trình lab, không xóa nhầm collections khác.

### 10.2. Sinh dữ liệu deterministic

```javascript
const base = ISODate("2026-01-01T00:00:00Z");
let batch = [];

for (let tenant = 0; tenant < 8; tenant++) {
  const tenantId = "tenant-" +
    String(tenant).padStart(2, "0");

  for (let i = 0; i < 1000; i++) {
    const status = i % 2 === 0
      ? "PAID"
      : "PENDING";

    batch.push({
      _id: tenantId + "-" +
        String(i).padStart(4, "0"),
      tenantId: tenantId,
      status: status,
      amount: i + 100,
      createdAt: new Date(base.getTime() + i * 60000)
    });

    if (batch.length === 500) {
      orders.insertMany(batch);
      batch = [];
    }
  }
}

if (batch.length > 0) {
  orders.insertMany(batch);
}

print("total=" + orders.countDocuments({}));
~~~

### 10.3. Kiểm tra fixture

```javascript
print("tenant-03 PAID=" +
  orders.countDocuments({
    tenantId: "tenant-03",
    status: "PAID"
  }));
~~~

Kết quả mong đợi:

```text
total=8000
tenant-03 PAID=500
~~~

Nếu không đúng, dừng test trước khi phân tích plan; kết quả ngẫu nhiên có thể là lỗi fixture, không phải lỗi query optimizer.

### 10.4. Tạo index

```javascript
orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);

printjson(orders.getIndexes());
~~~

---

## 11. Phân tích query khi có index

### 11.1. Query

```javascript
const filter = {
  tenantId: "tenant-03",
  status: "PAID"
};

const cursor = orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(10);
~~~

### 11.2. Kết quả đúng

```javascript
const documents = cursor.toArray();

print("count=" + documents.length);
print("firstId=" + documents[0]._id);
~~~

Dữ liệu có 500 matches. CreatedAt tăng theo `i` nên `limit(10)` với sort desc trả 10 docs có `i` chẵn lớn nhất, bắt đầu từ 998.

### 11.3. Explain

```javascript
const explain = orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(10)
  .explain("executionStats");

printjson({
  nReturned: explain.executionStats.nReturned,
  totalDocsExamined:
    explain.executionStats.totalDocsExamined,
  totalKeysExamined:
    explain.executionStats.totalKeysExamined,
  executionTimeMillis:
    explain.executionStats.executionTimeMillis
});
~~~

Kỳ vọng với index phù hợp thường là số keys/docs examined gần số docs trả về (đường chạy thực tế thay đổi theo version/engine). Không đặt assertion exact 10 trước khi xác minh.

### 11.4. Budget minh họa

```javascript
const stats = explain.executionStats;

if (stats.nReturned !== 10) {
  throw new Error("Unexpected result count");
}

if (stats.totalDocsExamined > 30) {
  throw new Error(
    "Too many documents examined: " +
      stats.totalDocsExamined);
}

if (stats.totalKeysExamined > 50) {
  throw new Error(
    "Too many keys examined: " +
      stats.totalKeysExamined);
}
~~~

**Lưu ý:** Ngưỡng 30/50 chỉ có ý nghĩa với fixture và query của ví dụ. Không sao chép thành quy định cho mọi query production.

### 11.5. Tại sao không assert executionTimeMillis?

Ngay trong cùng một fixture/index, thời gian có thể dao động do CPU, cache, JIT, I/O và plan selection. Một test tốt nên vẫn pass nếu cùng logical work được thực hiện trong 2 ms hoặc 25 ms.

---

## 12. Negative control: cố tình dùng collection scan

Một test chỉ vượt qua khi index tồn tại có thể chưa đủ chứng minh budget có khả năng phát hiện regression. Hãy thử một **đối chứng âm** trong lab.

### 12.1. Force natural collection scan bằng hint

```javascript
const naturalExplain = orders.find({
  tenantId: "tenant-03",
  status: "PAID"
})
  .sort({ createdAt: -1 })
  .limit(10)
  .hint({ $natural: 1 })
  .explain("executionStats");

printjson({
  docs: naturalExplain.executionStats.totalDocsExamined,
  keys: naturalExplain.executionStats.totalKeysExamined,
  returned: naturalExplain.executionStats.nReturned
});
~~~

`$natural` hint ép natural collection access trong các trường hợp hỗ trợ. Với fixture này, docsExamined dự kiến lớn hơn đáng kể so với indexed path.

### 12.2. So sánh

```text
Có index, optimizer chọn đường tốt:
  nReturned = 10
  docsExamined ≈ 10
  keysExamined ≈ 10

Force natural scan:
  nReturned = 10
  docsExamined ≈ 8000
  keysExamined = 0
~~~

Đây là số **minh họa**, không phải kết quả đã đo. Tài liệu/engine có thể thể hiện counters khác nhau.

### 12.3. Ý nghĩa của đối chứng âm

Nó cho thấy một query scan xấu có khả năng bị CI budget `docsExamined <= 30` chặn.

### 12.4. Đừng hint index trong test chính nếu mục tiêu là kiểm tra planner

Sai cách kiểm tra planner tự chọn index:

```javascript
orders.find(filter)
  .hint("idx_tenant_status_created")
  .explain("executionStats");
~~~

Nếu test luôn force index, bạn chỉ chứng minh index tồn tại/có thể dùng, **không chứng minh planner sẽ chọn nó khi query chạy bình thường**.

Nên tách:

- **Test chính không hint:** query optimizer tự chọn; đánh giá scan budget.
- **Diagnostic test có hint:** so sánh phương án index A/B.
- **Negative control:** force natural scan hoặc dùng fixture không có index trên database test riêng.

### 12.5. Không drop index trên shared database

Đừng chạy:

```javascript
db.orders.dropIndex("idx_tenant_status_created");
~~~

trên staging/production dùng chung chỉ để chứng minh test sẽ fail.

Tạo isolated disposable database và dùng hint hoặc setup riêng cho test đối chứng. Index DDL có tác động tới plan cache và concurrent operations.

---

## 13. Kiểm tra index contract tách khỏi explain

Nếu performance quan trọng phụ thuộc một compound index được migration tạo:

```javascript
{
  tenantId: 1,
  status: 1,
  createdAt: -1
}
~~~

Nên có **test index catalog** riêng.

### 13.1. Vì sao?

Một developer có thể xóa migration tạo index mà query correctness tests vẫn pass. Khi CI dựng database mới, index bị thiếu; scan budget sẽ fail. Test index catalog đưa ra lỗi rõ hơn.

### 13.2. mongosh

```javascript
const indexes = orders.getIndexes();

const expected = indexes.find(
  i => i.name === "idx_tenant_status_created");

if (!expected) {
  throw new Error("Missing expected index");
}

printjson(expected.key);
~~~

### 13.3. Thứ tự key rất quan trọng

Compound indexes:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

và:

```javascript
{ createdAt: -1, status: 1, tenantId: 1 }
~~~

không tương đương cho tất cả query shapes.

Kiểm tra đúng key order/direction, không chỉ có ba field names.

### 13.4. Index options cũng quan trọng

Một index có thể là:

- Partial.
- Sparse.
- Unique.
- Collation-specific.
- Hidden.
- TTL.
- Multikey.
- Wildcard.
- Hashed.

Tên và keys đúng chưa chắc semantics đúng. Nếu correctness/performance phụ thuộc partial filter hay collation, test luôn các index options quan trọng.

### 13.5. Index bị hidden

Một hidden index vẫn tồn tại trong catalog nhưng query planner không cân nhắc dùng như index thông thường. Vì vậy test chỉ kiểm tra tồn tại index có thể pass trong khi plan regression vẫn xảy ra.

Kết hợp catalog test với no-hint explain test.

---

## 14. Bảng nguyên tắc thiết kế assert

| Mục tiêu | Assertion nên ưu tiên | Tránh |
|---|---|---|
| Đúng số lượng kết quả | `nReturned==expected` và results assertions | Chỉ kiểm tra millis |
| Chặn collection scan lớn | `totalDocsExamined<=budget` | Assert toàn bộ plan JSON |
| Chặn index range quá rộng | `totalKeysExamined<=budget` | Chỉ yêu cầu IXSCAN |
| Xác nhận index contract | `listIndexes` kiểm tra keys/options | Kiểm tra tên index mà bỏ key order |
| Chặn blocking sort đáng kể | Stage/metric check theo engine và fixture | Exact path `winningPlan.inputStage...` trên mọi version |
| Kiểm tra covered query | `docsExamined≈0` cùng projection/index contract | Đòi mọi IXSCAN đều covered |
| Tìm timeout/latency regression | Dedicated benchmark/monitoring | Một lần `executionTimeMillis<5` |
| So sánh production plans | Slow logs, profiler, `$planCacheStats`, query telemetry | Dùng explain như plan cache lookup |
| Negative control | Hint natural trong test db riêng | Drop index trên shared cluster |

---

## 15. Java Sync Driver: lấy explain("executionStats")

MongoDB Java Sync Driver cung cấp `FindIterable.explain(...)`.

Ví dụ Java:

```java
import com.mongodb.ExplainVerbosity;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;

import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Sorts.descending;

public class ExplainExample {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_TEST_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                    "MONGODB_TEST_URI must point to a test database");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("plan_lab");
            MongoCollection<Document> orders =
                    db.getCollection("orders");

            Document explain = orders
                    .find(and(
                            eq("tenantId", "tenant-03"),
                            eq("status", "PAID")))
                    .sort(descending("createdAt"))
                    .limit(10)
                    .explain(ExplainVerbosity.EXECUTION_STATS);

            Document stats =
                    explain.get("executionStats", Document.class);

            long nReturned =
                    ((Number) stats.get("nReturned")).longValue();
            long docsExamined =
                    ((Number) stats.get("totalDocsExamined")).longValue();
            long keysExamined =
                    ((Number) stats.get("totalKeysExamined")).longValue();

            System.out.printf(
                    "returned=%d docs=%d keys=%d%n",
                    nReturned, docsExamined, keysExamined);
        }
    }
}
~~~

### 15.1. Vì sao ép sang Number?

Các BSON numeric values có thể được decode thành `Integer` hoặc `Long` tùy giá trị/driver. Viết:

```java
stats.getLong("totalDocsExamined")
~~~

có thể không phù hợp khi field có kiểu Int32. Dùng `((Number)value).longValue()` để normalize numeric type khi field được xác minh tồn tại.

### 15.2. Vì sao không lấy executionTimeMillis?

Mục tiêu test là chặn scan regression. Có thể ghi metric thời gian để chẩn đoán nhưng không dùng nó làm điều kiện pass/fail cho một run.

### 15.3. Error handling

Nếu `executionStats` hoặc field cần thiết không tồn tại:

- Kiểm tra verbosity.
- Kiểm tra query type.
- Kiểm tra topology/sharded output.
- Kiểm tra server/driver compatibility.
- Không tự động coi missing metric bằng 0 và cho test pass.

Fail với diagnostic error hữu ích hơn che mất thay đổi schema.

---

## 16. JUnit 5: integration test hoàn chỉnh không đo milliseconds

Ví dụ này dùng MongoDB Java Sync Driver, JUnit 5 và một MongoDB test instance được cung cấp qua `MONGODB_TEST_URI`. Dùng **database có tên duy nhất** để tránh xung đột test.

### 16.1. Mục tiêu test

- Seed 8.000 deterministic documents.
- Tạo compound index.
- Assert result correctness.
- Assert `totalDocsExamined<=30`.
- Assert `totalKeysExamined<=50`.
- Kiểm tra index được catalog đăng ký.
- Không assert executionTimeMillis.
- Cleanup đúng database test.

### 16.2. JUnit code

```java
import com.mongodb.ExplainVerbosity;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.IndexOptions;
import org.bson.Document;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Indexes.ascending;
import static com.mongodb.client.model.Indexes.compoundIndex;
import static com.mongodb.client.model.Sorts.descending;
import static org.junit.jupiter.api.Assertions.*;

class QueryPlanRegressionTest {

    private static final String INDEX_NAME =
            "idx_tenant_status_created";

    private static MongoClient client;
    private static MongoDatabase database;
    private static MongoCollection<Document> orders;

    @BeforeAll
    static void setupDatabase() {
        String uri = System.getenv("MONGODB_TEST_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                    "MONGODB_TEST_URI is required for this test");
        }

        // Must be a dedicated disposable MongoDB TEST instance.
        client = MongoClients.create(uri);

        String dbName = "plan_regression_" +
                UUID.randomUUID().toString().replace("-", "");

        database = client.getDatabase(dbName);
        orders = database.getCollection("orders");

        final Instant base =
                Instant.parse("2026-01-01T00:00:00Z");

        List<Document> batch = new ArrayList<>(500);

        for (int tenant = 0; tenant < 8; tenant++) {
            String tenantId = String.format(
                    Locale.ROOT, "tenant-%02d", tenant);

            for (int i = 0; i < 1000; i++) {
                String id = String.format(
                        Locale.ROOT, "%s-%04d", tenantId, i);

                Document order = new Document("_id", id)
                        .append("tenantId", tenantId)
                        .append("status",
                                i % 2 == 0 ? "PAID" : "PENDING")
                        .append("amount", i + 100)
                        .append("createdAt",
                                Date.from(base.plusSeconds(i * 60L)));

                batch.add(order);

                if (batch.size() == 500) {
                    orders.insertMany(batch);
                    batch = new ArrayList<>(500);
                }
            }
        }

        if (!batch.isEmpty()) {
            orders.insertMany(batch);
        }

        orders.createIndex(
                compoundIndex(
                        ascending("tenantId", "status"),
                        com.mongodb.client.model.Indexes.descending(
                                "createdAt")),
                new IndexOptions().name(INDEX_NAME));
    }

    @AfterAll
    static void cleanup() {
        try {
            if (database != null) {
                // Only the uniquely named test database.
                database.drop();
            }
        } finally {
            if (client != null) {
                client.close();
            }
        }
    }

    @Test
    void returnsCorrectOrdersAndRespectsScanBudget() {
        var filter = and(
                eq("tenantId", "tenant-03"),
                eq("status", "PAID"));

        List<Document> results = orders.find(filter)
                .sort(descending("createdAt"))
                .limit(10)
                .into(new ArrayList<>());

        assertEquals(10, results.size());
        assertEquals("tenant-03-0998",
                results.get(0).getString("_id"));

        for (Document result : results) {
            assertEquals("tenant-03",
                    result.getString("tenantId"));
            assertEquals("PAID",
                    result.getString("status"));
        }

        for (int i = 1; i < results.size(); i++) {
            Date previous = results.get(i - 1).getDate("createdAt");
            Date current = results.get(i).getDate("createdAt");
            assertFalse(previous.before(current),
                    "Sort order must be descending");
        }

        Document explain = orders.find(filter)
                .sort(descending("createdAt"))
                .limit(10)
                .explain(ExplainVerbosity.EXECUTION_STATS);

        Document stats =
                explain.get("executionStats", Document.class);

        assertNotNull(stats,
                "Expected executionStats in explain output");

        long returned = number(stats, "nReturned");
        long docs = number(stats, "totalDocsExamined");
        long keys = number(stats, "totalKeysExamined");

        assertEquals(10L, returned);
        assertTrue(docs <= 30,
                "Docs examined too high: " + docs);
        assertTrue(keys <= 50,
                "Keys examined too high: " + keys);

        // Intentionally no executionTimeMillis assertion.
    }

    @Test
    void declaresExpectedIndex() {
        boolean found = false;

        for (Document idx : orders.listIndexes()) {
            if (INDEX_NAME.equals(idx.getString("name"))) {
                Document key = idx.get("key", Document.class);

                assertEquals(
                        new Document("tenantId", 1)
                                .append("status", 1)
                                .append("createdAt", -1),
                        key);

                found = true;
                break;
            }
        }

        assertTrue(found,
                "Expected compound index not found");
    }

    private static long number(Document document, String key) {
        Object value = document.get(key);

        assertNotNull(value, "Missing metric: " + key);
        assertTrue(value instanceof Number,
                "Metric is not numeric: " + key);

        return ((Number) value).longValue();
    }
}
~~~

### 16.3. Điểm mạnh

- Không có điều kiện `elapsedMs < N`.
- Fixture deterministic.
- Database test mới, riêng biệt mỗi test run.
- Query có result correctness assertion.
- Scan budget đủ chặt để phát hiện collection scan trên 8.000 docs.
- Index metadata được kiểm tra riêng.
- JDBC/HTTP/application timings không chen vào efficiency assertion.

### 16.4. Cảnh báo an toàn

Ví dụ `cleanup()` gọi `database.drop()`. Chỉ chạy trên MongoDB **test instance cô lập**, với `MONGODB_TEST_URI` được cấu hình rõ và user có quyền phù hợp. Không trỏ biến này tới production/staging chung.

Trong project thật, nên thêm guard cấu hình test profile/container network hoặc whitelist test host/cluster để không thể xóa nhầm database.

### 16.5. Vì sao không assert tên index ngay trong test chính?

Ví dụ trên dùng **index contract** và **scan budget** làm hai lớp kiểm soát. Nó không khóa toàn bộ internal structure của query planner. Nếu use case yêu cầu xác minh index thực sự được chọn, có thể bổ sung inspection linh hoạt của `winningPlan`; phần sau mô tả cách làm.

---

## 17. Kiểm tra tên index sử dụng bằng parser linh hoạt

Khi cần chắc chắn planner dùng một index cụ thể, hãy duyệt đệ quy cấu trúc explain thay vì truy cập một path cứng.

### 17.1. Helper Java

```java
import org.bson.Document;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class ExplainIndexNames {

    private ExplainIndexNames() {
    }

    public static Set<String> collect(Document explain) {
        Set<String> names = new HashSet<>();
        Object planner = explain.get("queryPlanner");
        visit(planner, names);
        return names;
    }

    private static void visit(Object value, Set<String> names) {
        if (value instanceof Document) {
            Document document = (Document) value;

            Object name = document.get("indexName");
            if (name instanceof String) {
                names.add((String) name);
            }

            for (Object child : document.values()) {
                visit(child, names);
            }
        } else if (value instanceof List<?>) {
            for (Object child : (List<?>) value) {
                visit(child, names);
            }
        }
    }
}
~~~

### 17.2. Dùng với test

```java
Set<String> usedIndexes = ExplainIndexNames.collect(explain);

assertTrue(
        usedIndexes.contains("idx_tenant_status_created"),
        "Expected index not present in planner output: " +
                usedIndexes);
~~~

### 17.3. Giới hạn của helper đơn giản

- Một số explain trees có candidate/rejected plans cũng chứa `indexName`. Nếu duyệt toàn bộ `queryPlanner`, helper có thể lấy **index thuộc rejectedPlans**, không chứng minh winning plan dùng nó.
- Có output sharded/SBE với nhiều nhánh hoặc dạng stage mới.
- Các versions có thể thay đổi internal fields.
- Một số stages không có indexName theo cách thông thường.

Vì vậy để kiểm tra **winning index**, bắt đầu traversal từ `queryPlanner.winningPlan` và các winning subplans; không duyệt rejectedPlans.

### 17.4. Bản chỉ duyệt winningPlan

```java
Document planner =
        explain.get("queryPlanner", Document.class);
assertNotNull(planner);

Object winning = planner.get("winningPlan");

Set<String> names = new java.util.HashSet<>();

// Có thể dùng helper visit riêng trên winning branch.
// Không nên gom rejectedPlans làm bằng chứng winning index.
~~~

Bạn có thể refactor helper để nhận `Object winningPlan`, rồi duyệt từ đó. Nếu cần hỗ trợ nhiều MongoDB major versions, phải kiểm thử parser theo các output đại diện của từng engine/topology.

### 17.5. Khi nào chỉ cần scan budget?

Nếu mong muốn thực sự là “API lấy 10 orders mà không quét hàng nghìn docs”, budget trên `totalDocsExamined` và `totalKeysExamined` thường ít ràng buộc vào implementation hơn test tên một index.

Nếu query còn có yêu cầu order/predicate đặc biệt, kiểm tra index catalog + read correctness + budget là sự kết hợp hợp lý.

---

## 18. Kiểm thử blocking SORT và index sort order

Một query:

```javascript
db.orders.find({
  tenantId: "tenant-03",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(10);
~~~

có thể tận dụng index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

để filter và sort.

### 18.1. Nếu index thiếu createdAt

Index chỉ:

```javascript
{ tenantId: 1, status: 1 }
~~~

có thể lọc đúng 500 records, nhưng cần sắp xếp kết quả theo createdAt trước khi lấy top 10.

### 18.2. Cách kiểm tra

Trong explain, xem stages liên quan `SORT` và scan work. Có thể viết parser stage đệ quy:

```java
static boolean containsStage(Object value, String wanted) {
    if (value instanceof Document) {
        Document d = (Document) value;
        Object stage = d.get("stage");

        if (wanted.equals(stage)) {
            return true;
        }

        for (Object child : d.values()) {
            if (containsStage(child, wanted)) {
                return true;
            }
        }
    } else if (value instanceof List<?>) {
        for (Object child : (List<?>) value) {
            if (containsStage(child, wanted)) {
                return true;
            }
        }
    }
    return false;
}
~~~

### 18.3. Vì sao SORT assertion dễ vỡ?

SBE có thể biểu diễn execution bằng các stage tên/field khác, và optimizer có thể pushdown hoặc hợp nhất stages.

Vì vậy:

- Với **test matrix pin server version** có thể assert stage `SORT` khi biết output format.
- Với **test hỗ trợ nhiều major versions**, ưu tiên semantic checks + scan budgets, và lưu plan structure làm diagnostic artifact khi fail.
- Không phụ thuộc duy nhất vào việc `containsStage(winningPlan,"SORT") == false` như một cam kết cross-version.

### 18.4. Có SORT chưa chắc cần sửa

Nếu workload cần sort hàng trăm nghìn records làm báo cáo batch, blocking sort có thể chấp nhận nếu tài nguyên/SLO được dự trù. Test nên có mục tiêu nghiệp vụ rõ.

---

## 19. Kiểm thử covered query

Một query được index cover khi các trường cần filter/project có thể được đáp ứng từ index mà không fetch documents theo điều kiện thích hợp.

### 19.1. Ví dụ index cover

```javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    amount: 1
  },
  {
    name: "idx_orders_cover"
  }
);
~~~

Query:

```javascript
const plan = db.orders.find(
  { tenantId: "tenant-03", status: "PAID" },
  { _id: 0, tenantId: 1, status: 1, createdAt: 1, amount: 1 }
)
  .sort({ createdAt: -1 })
  .limit(10)
  .hint("idx_orders_cover")
  .explain("executionStats");

printjson({
  n: plan.executionStats.nReturned,
  docs: plan.executionStats.totalDocsExamined,
  keys: plan.executionStats.totalKeysExamined
});
~~~

Nếu index và query được cover, `totalDocsExamined` có thể bằng **0**.

### 19.2. Vì sao projection phải loại _id?

MongoDB mặc định trả `_id`. Nếu index không chứa `_id`, query có thể phải fetch document để lấy `_id`. Dùng `_id:0` hoặc thêm `_id` vào index khi có mục đích và đánh giá chi phí.

### 19.3. Multikey và collation

Covered queries có các ràng buộc với:

- Multikey array fields.
- Collation.
- Query operators.
- Projection.
- Index type.
- Server version.

Không khẳng định chỉ cần tạo index chứa đủ names là luôn có `docsExamined=0`.

### 19.4. Đừng ép coverage bằng hint trong test production path

Hint có ích để kiểm tra khả năng của index. Test chính không hint để xác nhận optimizer tự chọn đường hợp lý; nếu optimizer không chọn, tìm nguyên nhân thay vì cho test pass bằng hint.

---

## 20. Plan cache: explain không phải bằng chứng của cached plan

Một điểm đặc biệt quan trọng trong tài liệu MongoDB:

> Explain **bỏ qua plan cache hiện có** và ngăn planner cache winning plan của lần explain đó.

Hệ quả:

- Explain rất hữu ích để hiểu cách optimizer đánh giá query tại thời điểm kiểm tra.
- Nhưng nó **không phản ánh đầy đủ steady-state execution** của một application đang dùng cached plan.
- Một explain test không bảo đảm production cached plan hiện tại giống hệt.
- `executionTimeMillis` từ explain có thể gồm plan selection cost mà request thường không chịu trong steady state.

### 20.1. Query plan cache có thể bị thay đổi bởi DDL

Creating, dropping, hiding indexes hoặc thay đổi schema/index configuration có thể invalidate plan cache cho collection.

Vì vậy một benchmark ngay sau index migration có thể khác benchmark sau workload warmup.

### 20.2. $planCacheStats

MongoDB hỗ trợ aggregation stage `$planCacheStats` để xem thông tin plan cache trong điều kiện privilege/topology phù hợp.

~~~javascript
db.orders.aggregate([
  { $planCacheStats: {} }
]);
~~~

Output phụ thuộc version/engine và cache state. Không assert toàn bộ plan cache document exact trong CI.

### 20.3. explain vs production logs

Nếu production slow query log ghi `planSummary: COLLSCAN` nhưng explain trên staging sau khi thêm index ghi IXSCAN, điều đó không nhất thiết mâu thuẫn:

- Plan cache khác.
- Dataset khác.
- Index khác.
- Query shape/parameters khác.
- Server version/engine khác.
- Collation/hint khác.
- Execution node/shard khác.

Cần ghi đầy đủ context trước khi kết luận.

### 20.4. Không xóa plan cache bừa bãi trên production

Dùng `planCacheClear` hoặc DDL chỉ theo runbook khi có lý do; đây không phải bước “reset” nên tự động chạy trong mọi CI test trỏ tới cluster chung.

---

## 21. Query shape và parameter selectivity

Hai query:

```javascript
{ tenantId: "tenant-01", status: "PAID" }
{ tenantId: "tenant-03", status: "PAID" }
~~~

có thể cùng shape nhưng data distribution khác.

### 21.1. Vì sao cùng shape vẫn có performance khác?

Một tenant có 500 orders, tenant khác có 5 triệu. Query lấy 10 gần nhất có thể vẫn nhanh nếu index đúng; nhưng query không limit hoặc aggregation có thể khác rất lớn.

### 21.2. Không chỉ test một literal parameter

Nên test một tập representative:

- Tenant nhỏ.
- Tenant lớn/hot.
- Status phổ biến.
- Status hiếm.
- Date range ngắn.
- Date range dài.
- Có/không có kết quả.
- Pagination đầu/cuối.

### 21.3. Không dùng data hoàn toàn ngẫu nhiên

Dùng deterministic fixture có **phân bố được thiết kế**, ví dụ:

```text
tenant-small: 200 orders
tenant-medium: 5.000 orders
tenant-hot: 100.000 orders

status:
  PAID: 80%
  PENDING: 15%
  CANCELLED: 5%
~~~

Các tỷ lệ phải được seed lặp lại được.

### 21.4. Query shape hash không phải test ID vĩnh viễn

Tên và semantics của các fields như `queryHash`, `planCacheShapeHash`, `queryShapeHash` thay đổi giữa MongoDB versions. Không hardcode một query shape hash làm assertion xuyên nhiều major releases.

---

## 22. ESR: equality, sort, range và index regression

ESR là một nguyên tắc gợi ý cách sắp thứ tự index keys:

- **Equality** predicates trước.
- **Sort** keys khi cần.
- **Range** predicates trong vị trí phù hợp với selectivity.

Ví dụ:

```javascript
db.orders.find({
  tenantId: "tenant-03",
  status: "PAID",
  createdAt: { $gte: ISODate("2026-01-01T05:00:00Z") }
}).sort({ createdAt: -1 }).limit(10);
~~~

Index ứng viên:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

### 22.1. Vì sao thứ tự index matters?

Nếu index bắt đầu bằng `amount` nhưng query không có điều kiện `amount`, nó có thể không phục vụ filter/sort hiệu quả như mong muốn.

### 22.2. Kiểm thử range

Fixture nên chứa đủ documents ngoài range để regression thể hiện qua `keysExamined`/`docsExamined`.

### 22.3. Không áp dụng ESR máy móc

Một số workload có range predicate cực chọn lọc và sort trên tập nhỏ; ERS có thể tốt hơn theo tài liệu/measurements. Cần test các access paths phù hợp thay vì cho rằng một quy tắc luôn đúng.

### 22.4. Test index definition và explain cùng nhau

- Index catalog giúp phát hiện mất/thay key order.
- Explain budget giúp phát hiện scan rộng.
- Correctness test giúp phát hiện filter/sort sai.
- Benchmark giúp đo latency thực tế trên workload.

---

## 23. Multikey indexes và số index keys examined

Một field array có thể tạo nhiều index keys từ một document.

Ví dụ:

```javascript
{
  _id: 1,
  tenantId: "tenant-01",
  tags: ["promo", "vip", "mobile"]
}
~~~

Index:

```javascript
{ tenantId: 1, tags: 1 }
~~~

### 23.1. Vì sao keysExamined có thể lớn hơn docsExamined?

Một document có thể có nhiều index entries vì array/multikey structure. Vì vậy:

```text
keysExamined = 100
docsExamined = 20
nReturned = 20
~~~

không tự chứng minh planner chạy sai.

### 23.2. Test cần biết field cardinality

Nếu fixture tags arrays dài hơn gấp 10, scan budget có thể đổi dù query code/index vẫn giống. Cần cố định distribution và cập nhật budget khi intentional data model change.

### 23.3. $elemMatch và correlated predicates

Query trên array fields có thể tận dụng multikey index bounds tốt hơn khi dùng `$elemMatch` đúng ngữ nghĩa. Nhưng đừng thêm `$elemMatch` chỉ để ép index nếu nó thay đổi correctness.

### 23.4. Không assert keysExamined==nReturned trên mọi query

Equality, range, multikey, duplicate values, sparse/partial indexes có số keys examined khác số documents trả về.

---

## 24. Partial indexes, sparse indexes và collation

### 24.1. Partial index

```javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  {
    name: "idx_active_by_tenant",
    partialFilterExpression: { active: true }
  }
);
~~~

Index này chỉ chứa documents thỏa partial filter.

Query phải có điều kiện đủ để planner có thể an toàn sử dụng index. Nếu query không đảm bảo `active: true`, planner có thể bỏ qua partial index để tránh thiếu kết quả.

### 24.2. CI test cần thể hiện partial semantics

Test:

1. Query có `active:true`.
2. Query không có `active`.
3. Dữ liệu active/inactive có distribution rõ.
4. Index catalog chứa đúng partialFilterExpression.
5. Explain budget phù hợp từng query.

### 24.3. Collation

Index có collation đặc biệt có thể không được dùng như mong muốn nếu query collations không phù hợp.

Với case-insensitive search, cả index và query collation phải được xem như **một phần của query contract**.

### 24.4. Sparse/unique indexes

Một sparse index có thể bỏ qua documents thiếu field. Một unique sparse/partial index có semantics riêng; không được dựa vào presence của index để suy ra mọi query đều dùng được.

### 24.5. Hashed/wildcard/text indexes

Các index đặc thù có explain stages và applicability khác B-tree compound indexes. Test budget phải được thiết kế theo đúng operation, không copy ngưỡng từ query status/createdAt.

---

## 25. Aggregation pipelines: test work thay vì millis

Ví dụ pipeline:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-03", status: "PAID" } },
  { $sort: { createdAt: -1 } },
  { $limit: 10 },
  { $project: { _id: 0, amount: 1, createdAt: 1 } }
]);
~~~

### 25.1. Ưu tiên $match sớm khi giữ semantics

Đẩy filter có chọn lọc lên sớm có thể giúp tận dụng indexes, nhưng optimizer cũng có các biến đổi riêng. Không assume mọi pipeline rewrite đều giữ semantics.

### 25.2. Explain aggregation

```javascript
const aggPlan = db.orders.explain("executionStats")
  .aggregate([
    { $match: { tenantId: "tenant-03", status: "PAID" } },
    { $sort: { createdAt: -1 } },
    { $limit: 10 },
    { $project: { _id: 0, amount: 1, createdAt: 1 } }
  ]);

printjson(aggPlan);
~~~

Aggregation explain output có thể chứa `stages`, `queryPlanner` và SBE-specific nested structures tùy pipeline/version.

### 25.3. Không giả định totalDocsExamined ở top level

Với aggregation/sharding, counters có thể nằm ở nested sections. Nếu test cần parse stats, phải:

- Biết cấu trúc output của target version.
- Lấy counters từ đúng shard/stage.
- Tránh double count.
- Document parser assumptions.

### 25.4. $group và nReturned

Pipeline:

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$tenantId", count: { $sum: 1 } } }
]);
~~~

có thể trả 8 result rows dù scan hàng nghìn orders. Scan ratio cao là một phần tự nhiên của aggregation.

### 25.5. Spill metrics

Các pipeline sort/group có thể spill to disk khi dữ liệu lớn và cấu hình phù hợp. Tùy version/engine, explain chứa counters như `usedDisk`, `spills` hoặc `spilledBytes`.

Có thể kiểm tra một **budget về spill/memory** trong test kiểm soát version, nhưng đừng khóa exact field path cross-version khi output structure khác.

### 25.6. $lookup

Một pipeline join qua `$lookup` cần test index của foreign collection, fan-out, cardinality và query correctness. Tổng docs examined của một stage không tự phản ánh đầy đủ mọi nested collection access theo cách đơn giản.

---

## 26. Sharded cluster: một explain có nhiều nguồn công việc

Trong sharded cluster:

```text
Java application
      │
      ▼
mongos
  ├── shardA
  ├── shardB
  └── shardC
~~~

### 26.1. Query targeting

Nếu query chứa shard key phù hợp, mongos có thể route tới ít shards hơn. Nếu thiếu, có thể scatter-gather.

### 26.2. Vì sao test trên replica set không đủ cho sharding?

Test plan trên unsharded collection không chứng minh:

- Shard targeting.
- Routing/merge overhead.
- Per-shard index availability.
- Balancer/chunk distribution.
- Cross-shard sort behavior.

### 26.3. Explain output khác

Sharded explain thường có per-shard sections và merge stages. Không giả định mọi counters là một object đơn ở:

```text
executionStats.totalDocsExamined
~~~

### 26.4. Budget theo shard

Một test topology-aware có thể kiểm tra:

- Số shards targeted, khi API/plan output cung cấp thông tin ổn định.
- Per-shard docs/keys examined.
- Tổng examined sau tổng hợp **một lần**, tránh double count.
- Sự xuất hiện scatter-gather không mong muốn.
- Kết quả trả về và sort/limit semantics.

### 26.5. Không cộng shard durations thành HTTP latency

Các shards có thể chạy song song. Thời gian của từng shard không được cộng tuyến tính để suy ra response time; cần đo router/network/merge.

### 26.6. Có nên chạy sharded plan test trong mỗi PR?

Có thể chi phí cao. Thiết kế:

- Fast replica-set contract tests mỗi PR.
- Sharded topology integration tests định kỳ hoặc trước release.
- Production telemetry theo query shape.

---

## 27. Classic engine, SBE và khả năng thay đổi qua versions

MongoDB có nhiều execution engines. Explain result trees không phải API cấu trúc bất biến.

### 27.1. Classic plan

Có thể thấy:

```text
LIMIT
  FETCH
    IXSCAN
~~~

### 27.2. SBE plan

Có thể có:

```text
queryPlanner.winningPlan.queryPlan
queryPlanner.winningPlan.slotBasedPlan
~~~

### 27.3. EXPRESS path

MongoDB 8.0+ có những specialized EXPRESS stages cho một số query shapes, chẳng hạn `EXPRESS_IXSCAN`. Exact stage token `IXSCAN` không bao quát hết các trường hợp index access.

### 27.4. Cách viết kiểm thử bền hơn

Ưu tiên:

1. Data correctness.
2. Index catalog contract.
3. Aggregate scan budget.
4. Optional plan stage diagnostic.
5. Version-specific stage assertions chỉ khi thực sự cần và có test matrix.

### 27.5. MongoDB Stable API không cố định explain JSON structure

MongoDB documentation nêu **không bảo đảm một định dạng output cố định cho explain**, kể cả trong bối cảnh Stable API. Vì vậy đừng xây một bộ kiểm thử cross-version dựa trên full JSON equality.

### 27.6. Khi upgrade server

Trước khi nâng major version:

- Lưu các explain summary representative.
- Chạy CI index/scan tests trên target version.
- Điều tra failures do parser/schema vs actual regression.
- Review release notes về optimizer/SBE.
- Benchmark workload riêng.
- Không thay đổi budget chỉ để làm test xanh mà không có giải thích.

---

## 28. Query planner có thể chọn COLLSCAN dù index tồn tại

Trường hợp thường gặp:

- Collection nhỏ.
- Index kém chọn lọc.
- Query trả phần lớn documents.
- Index không phù hợp sort/collation.
- Query predicate không chứng minh partial filter.
- Index hidden.
- Workload/distribution thay đổi.
- Planner đánh giá cost khác giữa versions.

### 28.1. Vì sao đừng cấm COLLSCAN toàn cục?

Một test:

```java
assertFalse(explain.toJson().contains("COLLSCAN"));
~~~

có thể fail khi COLLSCAN nằm trong rejected plan, nested trial data hoặc khi full scan là hợp lý.

### 28.2. Đúng cách

Kiểm tra:

- Winning plan trong đúng context.
- Scan budgets.
- Query correctness.
- Index contract.
- Workload intent.

### 28.3. Nếu planner chọn plan bất ngờ

Hãy phân tích:

1. Dataset có đủ lớn chưa?
2. Index build hoàn tất chưa?
3. Query filter/sort/collation đúng chưa?
4. Projection có phù hợp không?
5. Index có hidden/partial không?
6. Có plan cache khác ở runtime production không?
7. MongoDB Server version/engine gì?
8. Có concurrent workload ảnh hưởng statistics không?

---

## 29. Tách CI regression gate khỏi benchmark suite

Một pipeline khuyến nghị:

```text
Pull Request
   │
   ├── Unit tests
   ├── Integration correctness tests
   ├── Index migration/catalog tests
   └── Explain scan-budget tests
          │
          └── PASS/FAIL không phụ thuộc elapsedMs

Nightly / Pre-release
   │
   ├── Workload replay / benchmark
   ├── Controlled load/concurrency
   ├── p50/p95/p99 latency
   ├── Throughput/error rate
   ├── CPU/IO/cache/replication
   └── Trend comparison, regression review

Production
   │
   ├── APM/tracing
   ├── Slow-operation logs
   ├── Profiler có kiểm soát
   ├── Query shape telemetry
   └── SLO-based alerting
~~~

### 29.1. Tại sao hai pipeline khác nhau?

CI cần feedback nhanh và determinism. Benchmark cần môi trường ổn định, thời gian chạy đủ dài và thống kê đáng tin.

### 29.2. CI có thể giữ diagnostic timings

Có thể ghi `executionTimeMillis` hoặc elapsedMs vào logs để hỗ trợ điều tra, nhưng không dùng nó làm hard threshold.

### 29.3. Có nên đặt time budget ở mọi cấp?

Có thể đặt **timeout rất rộng để ngăn test treo** (ví dụ integration test không được chạy vô hạn), nhưng đó là safety mechanism, không phải performance regression assertion.

Một timeout quá chặt trên CI vẫn flaky.

---

## 30. Benchmark latency đúng phương pháp

Khi cần xác định API có đạt SLO 100 ms không, phải đo latency thực sự.

### 30.1. Môi trường có kiểm soát

- Dedicated MongoDB instance/cluster.
- Version/FCV thống nhất.
- Index/schema và dataset đại diện production.
- Hardware/cgroup resources cố định.
- Không chạy đồng thời các job gây noise.
- Network RTT xác định.
- Connection pooling phù hợp.
- Read/write concerns đúng production.
- Sharding/replica topology tương ứng nếu cần.

### 30.2. Warmup

Cho JVM, driver pool, TLS connections, OS/WiredTiger cache và query planner có thời gian ổn định trước khi lấy mẫu.

Nhưng không chỉ benchmark warm state nếu production traffic có cold starts. Nên đo cả **warm** và **cold** như hai scenario khác nhau.

### 30.3. Concurrency

Single-thread benchmark không phản ánh contention trên hệ thống chạy 1000 concurrent requests.

Đo nhiều mức:

- 1 client.
- 10 concurrent clients.
- 100 concurrent clients.
- Peak representative concurrency.

Cần tránh vượt khả năng harness mà rồi đánh giá nhầm lỗi load generator.

### 30.4. Percentiles

Thay vì một lần 42 ms:

```text
p50 = 18 ms
p95 = 45 ms
p99 = 96 ms
max = 340 ms
error rate = 0.05%
~~~

Các số là ví dụ. Percentiles mô tả phân bố tốt hơn một thời điểm riêng lẻ.

### 30.5. Repeated runs

Lặp benchmark nhiều lần trên cùng điều kiện, so distribution và confidence intervals. Không dùng một run duy nhất làm kết luận upgrade chậm hơn 4%.

### 30.6. Bootstrap confidence intervals

Có thể dùng bootstrap trên các samples hoặc trên run-level aggregates phù hợp để ước lượng uncertainty. Tránh coi các request observations bị autocorrelation là hoàn toàn độc lập nếu dùng resampling đơn giản.

### 30.7. Throughput và latency đi cùng nhau

Một thay đổi có thể giảm p95 ở 100 ops/s nhưng throughput giảm mạnh ở 1000 ops/s. Benchmark phải ghi workload arrival rate/concurrency.

### 30.8. Không nhầm query time và API time

Đo:

- MongoDB command latency.
- End-to-end HTTP latency.
- Driver pool wait.
- Application serialization.
- Network.
- Retries.

Kết quả trên mỗi layer giải thích các bottleneck khác nhau.

---

## 31. JMH có phù hợp cho MongoDB query benchmark không?

JMH rất tốt cho Java microbenchmarks như BSON serialization hoặc một hàm mapping CPU-bound, nhưng một MongoDB database query qua network có nhiều yếu tố bên ngoài JVM.

### 31.1. Khi JMH hữu ích

- So sánh BSON encode/decode.
- So sánh business transformations.
- So sánh custom codec.
- So sánh query-building overhead ở client.

### 31.2. Khi JMH chưa đủ

- Throughput của replica set.
- Index scan performance qua storage.
- Network latency.
- Sharded router overhead.
- Write concern/replication.
- Connection pool under load.

Cần load test/workload benchmark cấp hệ thống, không chỉ JMH.

### 31.3. Không chạy JMH trong unit test thường

Benchmark harness đòi warmup/measurement/fork settings riêng, có chi phí cao và dễ bị nhiễu trong PR CI thông thường.

---

## 32. Testcontainers và cô lập MongoDB test environment

Testcontainers có thể tạo MongoDB container cho integration tests.

### 32.1. Lợi ích

- Tái lập server version.
- Database cô lập.
- Không ảnh hưởng production.
- Dễ chạy trên CI hỗ trợ containers.
- Fixture cleanup an toàn.
- Có thể dựng replica set khi bài test yêu cầu transactions/change streams.

### 32.2. Pin image version

Không dùng tag `latest` cho một query-plan regression gate nếu muốn test output ổn định. Nên pin MongoDB major/minor hoặc image digest theo policy.

Ví dụ thiết kế:

```text
MongoDB test image: pinned release
Java driver: pinned via dependency management
Fixture generator version: 3
Index migration version: 12
Query contract version: 2
~~~

### 32.3. MongoDBContainer API thay đổi theo Testcontainers versions

Cách import/package và helper methods có thể khác giữa Testcontainers major releases. Đừng copy nguyên API từ blog cũ.

Trong bài thực hành trên, JUnit nhận `MONGODB_TEST_URI` để tách phần tạo MongoDB test instance khỏi phần assertion; test harness có thể cung cấp URI từ Testcontainers tương thích.

### 32.4. Replica set hoặc standalone?

Đối với explain/index-read regression thông thường, một mongod test instance có thể đủ. Nếu test còn kiểm tra transaction, sessions/causal consistency hoặc change streams, cần replica set topology phù hợp.

### 32.5. Test environment khác production vẫn có giá trị

Testcontainers không mô phỏng production network/storage/scale chính xác. Nó phù hợp cho **logical scan regression gate**, không nên tuyên bố thay thế production benchmark.

### 32.6. Data cleanup

Dùng database duy nhất theo run ID, không thả lệnh `dropDatabase()` vào một database chung trỏ nhầm production.

---

## 33. CI setup chuẩn cho query-plan tests

### 33.1. Tách setup khỏi test

1. Start test MongoDB instance.
2. Apply schema/index migrations.
3. Seed deterministic fixtures.
4. Validate fixture counts/distributions.
5. Run correctness assertions.
6. Run explain budget tests.
7. Record plan diagnostics khi fail.
8. Cleanup isolated data.

### 33.2. Vì sao phải apply migrations thật?

Nếu test tự tạo index mà production migration quên tạo, query plan test vẫn pass trong khi deploy thật sẽ chậm.

Có hai loại test:

- **Migration contract test:** chạy migrations production, kiểm tra index catalog.
- **Query behavior test:** seed data và đo scan budgets trên schema/index đã có.

Có thể kết hợp chúng để chặn thiếu index release.

### 33.3. Không chạy test theo thứ tự ngẫu nhiên mà chia sẻ state

Nếu test A drop index rồi test B chạy explain trên cùng database, kết quả phụ thuộc test order/concurrency.

Dùng:

- Unique database per test class/run.
- No shared mutable plan cache/index DDL.
- Setup & cleanup có ownership rõ.
- Tests isolation.

### 33.4. Lưu diagnostics khi fail

Khi budget fail, log:

- Query name/shape.
- Fixture sizes.
- MongoDB version.
- Index names/keys (không cần secrets).
- `nReturned`.
- `totalDocsExamined`.
- `totalKeysExamined`.
- Sanitized winningPlan summary.
- Chosen budgets.

Không cần log toàn bộ raw query documents có PII.

---

## 34. Một dạng contract test theo query name

Thay vì viết trùng từng assertion, có thể xây abstraction:

```java
public record QueryBudget(
        String name,
        long expectedReturned,
        long maxDocsExamined,
        long maxKeysExamined) {
}
~~~

Ví dụ:

```java
QueryBudget recentPaidOrders = new QueryBudget(
        "recent-paid-orders",
        10,
        30,
        50);
~~~

### 34.1. Assertion helper

```java
static void assertBudget(
        Document explain,
        QueryBudget budget) {

    Document stats =
            explain.get("executionStats", Document.class);

    if (stats == null) {
        throw new AssertionError(
                "Missing executionStats for " + budget.name());
    }

    long returned =
            ((Number) stats.get("nReturned")).longValue();
    long docs =
            ((Number) stats.get("totalDocsExamined")).longValue();
    long keys =
            ((Number) stats.get("totalKeysExamined")).longValue();

    if (returned != budget.expectedReturned()) {
        throw new AssertionError(
                budget.name() + " returned " + returned);
    }

    if (docs > budget.maxDocsExamined()) {
        throw new AssertionError(
                budget.name() + " docsExamined " + docs);
    }

    if (keys > budget.maxKeysExamined()) {
        throw new AssertionError(
                budget.name() + " keysExamined " + keys);
    }
}
~~~

### 34.2. Lợi ích

- Query budget có tên nghiệp vụ.
- Dễ review trong PR.
- Không nhầm milliseconds thành budget.
- Có thể phân cấp theo workload.
- Giảm copy/paste.

### 34.3. Giới hạn

Helper trên giả định unsharded find explain với stats top-level. Với aggregation/sharded explain phải có adapter riêng và xử lý missing fields rõ ràng.

### 34.4. Budget không phải SLA production

`maxDocsExamined=30` là một **guardrail logical work**. SLO p95 vẫn cần benchmark/APM.

---

## 35. Test có/không có result và sort stability

### 35.1. Query có kết quả

Với fixture xác định, assert count, fields, sort.

### 35.2. Query không có kết quả

Ví dụ:

```javascript
db.orders.find({
  tenantId: "tenant-not-exist",
  status: "PAID"
}).explain("executionStats");
~~~

Nếu index đúng, query không có kết quả có thể không cần scan nhiều data. Nhưng `nReturned=0` có thể làm ratio-based assertion khó hiểu; nên dùng absolute docs/keys budgets.

### 35.3. Sort tie-breaker

Nếu nhiều documents có cùng `createdAt`, sort chỉ trên createdAt không bảo đảm order duy nhất giữa records cùng timestamp.

Nên dùng deterministic secondary sort:

```javascript
db.orders.find(filter)
  .sort({ createdAt: -1, _id: 1 })
  .limit(10);
~~~

Nếu dùng sort này, index candidate cũng cần xét thêm `_id:1` để hỗ trợ sort trọn vẹn:

```javascript
{
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: 1
}
~~~

### 35.4. Vì sao nên test tie-breaker?

Pagination dựa trên sort không ổn định có thể bỏ sót/lặp records giữa pages, ngay cả khi explain performance tốt.

### 35.5. Đừng tự đổi sort trong test khác production

Test phải dùng đúng query shape production, gồm filter, sort, projection, limit, collation và options. Nếu test dùng sort khác, plan/correctness conclusions không áp dụng cho API thật.

---

## 36. Pagination: skip và keyset

### 36.1. Skip lớn

```javascript
db.orders.find({ tenantId: "tenant-03" })
  .sort({ createdAt: -1 })
  .skip(900)
  .limit(10);
~~~

Dù có index, MongoDB có thể phải tiến qua nhiều keys để bỏ qua 900 records.

### 36.2. Keyset pagination

Thay vì skip, dùng cursor boundary phù hợp:

```javascript
db.orders.find({
  tenantId: "tenant-03",
  createdAt: { $lt: ISODate("2026-01-01T12:00:00Z") }
}).sort({ createdAt: -1 }).limit(10);
~~~

Đây là minh họa đơn giản. Nếu timestamp có ties, cần điều kiện lexicographic kết hợp _id cùng sort/index.

### 36.3. Test hai mức page depth

Nếu API bắt buộc hỗ trợ page 1000, đừng chỉ test page đầu. Sử dụng fixture đủ lớn và budget/benchmark cho deep pagination.

### 36.4. Không kỳ vọng keyset luôn tương đương skip

Keyset thay đổi API contract, cần ổn định sort/unique tie-breaker và handling khi records được insert/delete giữa các pages.

---

## 37. Geospatial/text/vector workloads cần metric riêng

Không dùng duy nhất threshold `docsExamined<=30` cho mọi loại tìm kiếm.

### 37.1. Geospatial

Index `2dsphere` có thể tạo nhiều candidate matches và cần kiểm tra geometry. Query efficiency cần xét index applicability, returned results, distance, false-positive filtering và correctness.

### 37.2. Text search

Text search có ranking/score semantics; một query text trả 10 kết quả vẫn có thể xét nhiều postings/docs hợp lý.

### 37.3. Vector search

Atlas Vector Search hoặc các cơ chế search chuyên dụng có telemetry/plan output khác MongoDB core find. Không mặc định `explain.executionStats.totalDocsExamined` có cùng ý nghĩa/field path.

### 37.4. Thiết kế test theo operator

- Correctness/ranking consistency.
- Index definitions.
- Relevant explain/search metrics.
- Result quality.
- Specialized benchmark.

Không áp dụng chung một budget cho B-tree equality query và nearest-neighbor search.

---

## 38. Sự khác nhau giữa cold cache và warm cache

### 38.1. Cache lạnh

Query cần đọc blocks từ disk, có thể chậm dù docsExamined ít.

### 38.2. Cache nóng

Cùng query có thể chạy nhanh hơn nhiều vì data/index pages đã trong WiredTiger/OS cache.

### 38.3. Explain budgets ít bị ảnh hưởng hơn timing

Số documents/keys examined chủ yếu phụ thuộc logical access path, nên thường ổn định hơn khi cache thay đổi, trong khi `executionTimeMillis` dao động mạnh.

Nhưng không kết luận scan counts hoàn toàn invariant: optimizer/data/index/engine có thể thay đổi.

### 38.4. Benchmark phải ghi cache condition

Nếu chỉ benchmark warm state, không thể suy ra cold-start latency. Có thể chạy hai scenarios:

- Cold-ish controlled restart/cache state (nếu môi trường hỗ trợ).
- Warm steady-state workload.

### 38.5. Không reset OS cache trên shared CI host

Các lệnh flush OS cache hoặc restart MongoDB có thể ảnh hưởng nhiều workload khác. Dùng isolated benchmark node, không chạy destructive cache operations trên môi trường chung.

---

## 39. Slow query logs và database profiler làm gì cho regression testing?

### 39.1. Slow-operation logs

MongoDB diagnostic logs có thể ghi:

- Namespace.
- Plan summary.
- Duration.
- Docs/keys examined.
- Query shape/identifiers.
- Operation type.

Rất hữu ích để tìm **truy vấn cần thêm contract test**.

### 39.2. Database profiler

`system.profile` có thể ghi chi tiết operation execution khi bật ở mức phù hợp; nhưng tạo thêm resource overhead.

### 39.3. Không dùng slow log làm CI assertion duy nhất

Nếu CI query không vượt threshold, log sẽ không có event. Từ việc không có slow logs không thể kết luận query hiệu quả.

### 39.4. Dùng logs để chọn query representative

Production telemetry có thể chỉ ra:

- API route nào tốn chi phí nhất.
- Query shape nào quét nhiều docs.
- Tenant/data skew.
- Aggregation nào spill disk.
- Workloads nào xuất hiện trong p99.

Sau khi xác minh và sanitize, tạo **deterministic fixture** tái hiện pattern trong test.

### 39.5. Không copy raw production data vào CI

Production logs/query filters có thể chứa PII. Tạo dữ liệu giả lập theo distribution/cardinality nhưng không mang raw customer records vào repository hoặc CI artifacts.

---

## 40. Khi kế hoạch truy vấn thay đổi nhưng vẫn hiệu quả

Một upgrade MongoDB có thể đổi:

```text
FETCH -> IXSCAN
~~~

thành một SBE-specific plan, trong khi:

```text
nReturned = 10
totalDocsExamined = 10
totalKeysExamined = 10
~~~

vẫn giữ tương đương.

### 40.1. Đây có phải regression?

Không nhất thiết. Nếu query correctness và work budget vẫn tốt, không nên fail test chỉ vì JSON tree khác.

### 40.2. Khi nào đổi stage đáng điều tra?

- TotalDocsExamined tăng mạnh.
- TotalKeysExamined tăng mạnh.
- Có blocking sort/spill bất ngờ.
- Plan cache/replanning bất thường.
- Query latency production tăng có ý nghĩa.
- Dữ liệu returned sai.
- Index bị mất/hidden.

### 40.3. Ghi version trong test reports

Khi fail, log MongoDB server version và relevant driver version. Một failure chỉ xảy ra ở MongoDB 9.x có thể cần update parser theo optimizer engine mới.

---

## 41. Khi index được dùng nhưng số keysExamined vẫn cao

Giả sử:

```text
Plan:
  IXSCAN { status: 1 }

Stats:
  keysExamined = 500000
  docsExamined = 500000
  nReturned = 10
~~~

Nếu chỉ assert `IXSCAN present`, test sẽ pass dù query scan nửa triệu index entries.

### 41.1. Budget tốt hơn

```text
nReturned == 10
docsExamined <= 100
keysExamined <= 200
~~~

### 41.2. Index candidate

Thay:

```javascript
{ status: 1 }
~~~

bằng index phù hợp query:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

với bằng chứng từ explain.

### 41.3. Tác động tới writes

Thêm compound index làm tăng storage và write amplification. Đừng tạo index chỉ vì một query test thất bại mà bỏ qua workload ghi/retention.

### 41.4. Test cả write overhead trong benchmark

Explain test bảo vệ query read access path; benchmark riêng cần đo insert/update throughput sau khi thêm index.

---

## 42. Test failing do dataset thay đổi có chủ đích

Ví dụ tính năng mới bổ sung hàng loạt PAID orders khiến query result cardinality tăng gấp 20 lần.

### 42.1. Test vẫn có giá trị

Nó cho thấy scan budget có thể cần điều chỉnh hoặc index design cần thay đổi.

### 42.2. Không tự tăng budget vô điều kiện

Một PR sửa:

```text
maxDocsExamined: 30 -> 100000
~~~

để test xanh mà không giải thích là làm mất regression guard.

### 42.3. Quy trình thay đổi budget

1. Chỉ ra data/query shape change.
2. So explain trước/sau.
3. So index options.
4. Đo response count/selectivity.
5. Xác định work budget mới hợp lý.
6. Đánh giá benchmark nếu workload lớn.
7. Đưa lý do vào PR/ADR.

### 42.4. Dùng relative budgets đúng chỗ

Nếu query phục vụ N returned documents, có thể dùng:

```text
docsExamined <= max(absoluteFloor, ratioBudget * nReturned)
~~~

Nhưng với `nReturned=0`, aggregation, multikey và array predicates, ratio có giới hạn. Kết hợp absolute bound.

---

## 43. Test không có index: baseline và negative control định kỳ

Một thực hành hữu ích là định kỳ xác nhận guardrail bắt được regression:

1. Seed fixture.
2. Explain query với index đúng.
3. Force natural scan hoặc tạo isolated DB không có index.
4. Confirm docsExamined vượt budget.
5. Restore/drop isolated test database.

### 43.1. Không biến negative control thành CI flaky test

Nếu fixture quá nhỏ, COLLSCAN vẫn trong budget và negative control không chứng minh được gì.

### 43.2. Khi query không trả nhiều rows

Thêm data ngoài match predicate để đảm bảo natural scan phải xem nhiều documents.

### 43.3. Query với limit có thể dừng sớm

Đặc biệt với không sort hoặc data được sắp xếp thuận lợi trong collection, COLLSCAN có thể tìm đủ 10 matches sớm.

Để đối chứng rõ, dùng query có sort không được index phục vụ hoặc đặt distribution sao cho full scan đáng kể. Không đoán natural scan luôn quét toàn bộ collection.

### 43.4. Không test fail cố ý trong PR pipeline thường

Negative control có thể ở test riêng được thiết kế để assert “work > threshold” và pass khi regression simulation được phát hiện, không được viết test luôn throw exception rồi gây build đỏ.

---

## 44. Một bộ tiêu chí theo mức độ quan trọng

| Nhóm query | Mức độ | Test gate |
|---|---|---|
| Critical checkout/read-after-write | Rất cao | Correctness + index contract + explain budget + failover tests |
| User-facing listing/search | Cao | Correctness + scan budget + pagination/sort tests |
| Admin report | Trung bình | Pipeline explain + workload benchmark định kỳ |
| One-time migration | Theo runbook | Dry run, batching, resource budget, checkpoints |
| Background analytics | Theo SLA batch | Explain/benchmark; không cấm mọi COLLSCAN |
| Rare maintenance query | Thấp hơn | Correctness + resource safety |
| Specialized vector/text search | Theo chất lượng/ranking | Index/search metrics + relevance + benchmark |

### 44.1. Chọn query để test đầu tiên

Ưu tiên:

- Nhiều traffic.
- Chi phí scan lớn.
- Latency nhạy cảm.
- Phân bố tenant skew.
- Query shape hay thay đổi.
- Collection tăng trưởng nhanh.
- Truy vấn có rủi ro thiếu compound index.
- Pipeline join/group/sort phức tạp.

### 44.2. Không cần hàng nghìn plan tests

Một bộ test nhỏ nhưng đại diện có thể tốt hơn một loạt assertions exact stage structure dễ vỡ.

---

## 45. Quy trình khi CI query-plan test thất bại

### Bước 1 — Xác định failure category

- Correctness mismatch?
- Missing index?
- Too many docs examined?
- Too many keys examined?
- Explain field missing?
- Driver/server not compatible?
- Unexpected stage?
- Test fixture corrupted?

### Bước 2 — Kiểm tra dữ liệu test

- Tổng document count.
- Cardinality theo predicate.
- Sort tie-breaker.
- Index definitions/options.
- Test DB isolation.

### Bước 3 — Kiểm tra query shape

- Filter.
- Sort.
- Projection.
- Limit/skip.
- Collation.
- Hint.
- Read preference.
- Aggregation stages.

### Bước 4 — So explain trước/sau

Lưu sanitized summary:

```text
Query: recent-paid-orders
Server version: pinned test version
Returned: 10

Before:
  docsExamined: 10
  keysExamined: 10
  index: idx_tenant_status_created

After:
  docsExamined: 8000
  keysExamined: 0
  winning access: COLLSCAN
~~~

### Bước 5 — Xem code/migration

- Ai đổi index?
- Có migration bị bỏ?
- Có query predicate mới?
- Index bị hidden/partial?
- Có field đổi type?
- Có collation mismatch?
- Có update data distribution?

### Bước 6 — Chọn cách sửa

- Khôi phục index.
- Điều chỉnh query.
- Thêm predicate chọn lọc.
- Sửa sort.
- Tối ưu projection.
- Chuyển skip sang keyset.
- Điều chỉnh schema.
- Chỉnh budget có evidence.

### Bước 7 — Xác minh không gây regression khác

Một index mới cải thiện read có thể làm write chậm hơn. Dùng benchmark và theo dõi storage/write overhead.

### Bước 8 — Đóng incident

Ghi:

- Root cause.
- Query shape.
- Before/after scan metrics.
- Index migration/version.
- Benchmark nếu có.
- Rủi ro còn lại.

Không chỉ báo “test hết flaky” sau khi tăng timeout từ 50 lên 5000 ms.

---

## 46. Những lỗi phổ biến khi viết query-plan tests

| Lỗi | Vì sao sai | Cách sửa |
|---|---|---|
| `assert elapsedMs < 10` | Môi trường gây dao động | Dùng scan budget |
| `assert executionTimeMillis == 1` | Explain timing không ổn định | Chỉ ghi diagnostic |
| Dataset 3 documents | COLLSCAN vẫn hợp lý | Seed đủ lớn |
| Random data mỗi run | Selectivity thay đổi | Fixture deterministic |
| Chỉ assert IXSCAN | Có thể scan triệu keys | Keys/docs budget |
| Chỉ assert keysExamined thấp | COLLSCAN có keys=0 | Kèm docs budget |
| Chỉ assert docsExamined thấp | Index range vẫn rộng/covered scan | Kèm keys budget |
| Assert toàn bộ winningPlan JSON | Engine/version thay đổi | Robust semantic checks |
| Duyệt cả rejectedPlans và báo winning index | Sai context | Chỉ duyệt winning branch |
| Dùng hint trong test chính | Che planner regression | No-hint main test |
| Drop index trên shared staging | Ảnh hưởng users/plan cache | Isolated DB/negative hint |
| Assume explain dùng plan cache | Explain bỏ qua plan cache | Dùng production telemetry riêng |
| Assert queryHash bằng chuỗi cố định | Version/query shape identifiers thay đổi | Tránh exact hash |
| nReturned == docsExamined với covered query | Docs có thể 0 | Dùng upper bound |
| docsExamined/nReturned cho $group | Aggregate trả ít rows | Operator-specific tests |
| Test sort mà không tie-break | Order không xác định khi cùng key | Sort thêm stable unique key |
| Test query khác production | Plan không đại diện | Giữ shape/options |
| Không kiểm tra index catalog | Missing index khó chẩn đoán | Index contract test |
| Bỏ qua partial filter/collation | Planner bỏ index | Test index options |
| Benchmark trên shared CI runner | CPU/cache noise | Dedicated benchmark |
| p95 từ 10 requests | Không đủ mẫu | Repeated representative workloads |
| Không warmup | JIT/pool/cold cache bias | Warmup có kiểm soát |
| JMH microbenchmark thay DB load test | Không đo network/storage | System workload benchmark |
| Mọi COLLSCAN đều fail | Có full scan hợp lý | Workload-specific goals |
| Scan budget đặt theo cảm giác | False pass/false fail | Ground từ fixture và data |
| Test DB dùng production URI | Nguy cơ xóa data thật | Dedicated test instance |
| Test share mutable database | Flaky do concurrent DDL | Unique DB/isolation |
| Set maxTimeMS cực thấp để test perf | Timeout flakiness | Broad safety timeout riêng |
| Coi CI plan gate thay SLO | Không đo host/network/throughput | Benchmark và monitoring |
| Dùng ngưỡng từ find cho vector search | Metrics khác | Specialized test |
| Copy production query values vào CI | Rủi ro PII | Synthetic sanitized fixtures |

---

## 47. Bài tập thực hành A: thay test millis bằng work budget

Cho test cũ:

~~~java
long start = System.nanoTime();
List<Document> orders = collection.find(filter)
        .limit(20)
        .into(new ArrayList<>());
long ms = (System.nanoTime() - start) / 1_000_000;
assertTrue(ms < 30);
~~~

Yêu cầu:

1. Thêm correctness assertions.
2. Lấy explain executionStats.
3. Assert docs/keys budgets phù hợp fixture.
4. Ghi executionTimeMillis chỉ để tham khảo.
5. Giải thích tại sao test mới ít flaky hơn.

---

## 48. Bài tập B: so sánh two plans

Có:

```text
Plan A: IXSCAN
  keysExamined = 20
  docsExamined = 20
  nReturned = 20

Plan B: IXSCAN
  keysExamined = 700000
  docsExamined = 350000
  nReturned = 20
~~~

Hãy:

1. Giải thích vì sao cả hai đều dùng index mà độ hiệu quả khác.
2. Chọn budgets để bắt Plan B.
3. Đề xuất compound index.
4. Mô tả chi phí write của index mới.

---

## 49. Bài tập C: fixture deterministic

Tạo 12.000 orders với:

- 6 tenants.
- 2.000 orders/tenant.
- 70% PAID.
- Timestamp tăng một phút.
- ID deterministic.

Yêu cầu:

1. Seed không dùng random không kiểm soát.
2. Kiểm tra counts.
3. Tạo compound index.
4. Chạy query top 10.
5. Đọc nReturned/docsExamined/keysExamined.
6. Thiết kế budget có biên an toàn.

---

## 50. Bài tập D: index thiếu sort field

Ban đầu index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

Sau đó đổi thành:

```javascript
{ tenantId: 1, status: 1 }
~~~

Yêu cầu:

1. Dự đoán tác động khi sort createdAt desc.
2. So explain plans.
3. Xem blocking sort.
4. Chọn test phù hợp với engine/version.
5. Giải thích vì sao không cần assert toàn bộ plan tree.

---

## 51. Bài tập E: covered query

Cho index:

```javascript
{ tenantId: 1, status: 1, amount: 1 }
~~~

Và query projection:

```javascript
{ _id: 0, tenantId: 1, status: 1, amount: 1 }
~~~

Yêu cầu:

1. Giải thích điều kiện coverage.
2. Vì sao `docsExamined=0` có thể đúng?
3. Nếu thêm `_id:1` vào projection, điều gì có thể đổi?
4. Xem multikey/collation limitations.

---

## 52. Bài tập F: plan cache

Một explain test thấy IXSCAN, nhưng slow query log production ghi COLLSCAN.

Hãy liệt kê tối thiểu bảy nguyên nhân, bao gồm:

- Plan cache.
- Dataset distribution.
- Index/migration state.
- Query shape/parameters.
- Server version/engine.
- Collation/hint.
- Router/shard differences.

Giải thích vì sao `explain()` không phải plan cache inspection.

---

## 53. Bài tập G: aggregation regression

Một pipeline:

```javascript
[
  { $match: { tenantId: "tenant-03" } },
  { $group: { _id: "$status", count: { $sum: 1 } } }
]
~~~

Trả 2 groups nhưng scan 1000 orders.

1. Vì sao docsExamined/nReturned cao có thể hợp lý?
2. Có thể lọc hơn không?
3. Index nào hỗ trợ match?
4. Metrics nào giúp đánh giá grouping?
5. Vì sao threshold 30 docs từ top-10 query không phù hợp?

---

## 54. Bài tập H: sharded plan

Một query tới 4 shards. Mỗi shard có executionStats riêng.

1. Làm sao tránh double count?
2. Số shards targeted phản ánh điều gì?
3. Vì sao không cộng durations để ra HTTP latency?
4. Khi nào phải test router với mongos thay vì only mongod?
5. Viết mô hình budget theo shard targeting.

---

## 55. Bài tập I: pagination

Một API dùng:

```javascript
.skip(100000).limit(20)
~~~

Hãy:

1. Dự đoán keys examined khi có index.
2. Đề xuất keyset cursor.
3. Thêm sort tie-breaker.
4. Chọn fixture đủ sâu.
5. So correctness/scan budgets.
6. Benchmark deep-page latency riêng.

---

## 56. Bài tập J: CI vs benchmark

Một team muốn mọi pull request có điều kiện:

```text
MongoDB query p95 <= 30 ms
~~~

tính từ 20 requests trên shared CI runner.

Hãy thiết kế lại thành:

- Fast deterministic explain gate.
- Dedicated benchmark nightly/pre-release.
- Sampling và confidence analysis.
- Production SLO monitoring.
- Policy xử lý regression.

---

## 57. Bài tập K: MongoDB upgrade

Sau upgrade server, explain tree đổi từ IXSCAN/FETCH sang SBE path nhưng counters tương đương.

1. Test exact stage có nên fail không?
2. Cách kiểm tra semantic equivalence?
3. Khi nào update plan parser?
4. Có cần benchmark nữa không?
5. Ghi MongoDB version/FCV trong diagnostics thế nào?

---

## 58. Bài tập L: negative control

Thiết kế test chứng minh budget `docsExamined<=30` sẽ chặn collection scan.

1. Seed dataset.
2. Run no-hint explain.
3. Force `$natural` hint.
4. So scan metrics.
5. Không drop index trên production.
6. Không dùng force-hint để “làm đẹp” test chính.

---

## 59. Checklist chuẩn cho query-efficiency regression tests

### 59.1. Fixture

- [ ] Dedicated MongoDB test instance/namespace.
- [ ] Database name duy nhất hoặc isolate rõ.
- [ ] Seed deterministic.
- [ ] Counts/distributions được xác minh.
- [ ] Data đủ lớn để index vs collection scan khác biệt.
- [ ] Không dùng raw production PII.
- [ ] Có cleanup an toàn.
- [ ] Không share mutable index/plan state giữa tests.

### 59.2. Query contract

- [ ] Filter giống production shape.
- [ ] Sort đầy đủ, có tie-breaker khi cần.
- [ ] Projection/limit/skip/collation giống thực tế.
- [ ] Correctness assertions đầy đủ.
- [ ] Result size được kiểm tra.
- [ ] Mỗi important query có tên/owner.
- [ ] Có test các trường hợp data skew.

### 59.3. Index contract

- [ ] Index definitions được tạo bởi migrations thực.
- [ ] Key order/direction đúng.
- [ ] Partial/sparse/unique/collation options đúng.
- [ ] Index không bị hidden ngoài ý muốn.
- [ ] Có explain no-hint test.
- [ ] Có negative control phù hợp.
- [ ] Không thay index trên shared production để test.

### 59.4. Assertions

- [ ] Dùng `executionStats` explicit.
- [ ] Đọc `nReturned`.
- [ ] Đọc `totalDocsExamined`.
- [ ] Đọc `totalKeysExamined`.
- [ ] Chọn budgets có cơ sở.
- [ ] Xử lý nReturned=0.
- [ ] Không assert milliseconds exact.
- [ ] Không assert toàn bộ explain JSON.
- [ ] Không coi query hash bất biến xuyên releases.
- [ ] Parser biết classic/SBE/sharded variations.
- [ ] Có diagnostic output khi fail.

### 59.5. Benchmark và monitoring

- [ ] Có benchmark riêng cho latency/throughput.
- [ ] Có warmup và stable environment.
- [ ] Ghi p50/p95/p99 và error rate.
- [ ] Ghi concurrency/ops/s.
- [ ] Ghi CPU/memory/disk/network.
- [ ] So repeated runs/statistical variance.
- [ ] Phân biệt application vs MongoDB timings.
- [ ] Không dùng JMH đơn lẻ thay system benchmark.
- [ ] Production SLO được theo dõi độc lập CI explain tests.

---

## 60. Tài liệu tham khảo chính thức

- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Interpret Explain Plan Results](https://www.mongodb.com/docs/manual/tutorial/analyze-query-plan/)
- [MongoDB Manual — Explain Command](https://www.mongodb.com/docs/manual/reference/command/explain/)
- [MongoDB Manual — cursor.explain()](https://www.mongodb.com/docs/manual/reference/method/cursor.explain/)
- [MongoDB Manual — db.collection.explain()](https://www.mongodb.com/docs/manual/reference/method/db.collection.explain/)
- [MongoDB Manual — Query Plans and Plan Cache](https://www.mongodb.com/docs/manual/core/query-plans/)
- [MongoDB Manual — Slot-Based Query Execution Engine](https://www.mongodb.com/docs/manual/reference/sbe/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — ESR Equality, Sort, Range Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/)
- [MongoDB Manual — Covered Queries](https://www.mongodb.com/docs/manual/core/query-optimization/#covered-query)
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual — Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/)
- [MongoDB Manual — $planCacheStats](https://www.mongodb.com/docs/manual/reference/operator/aggregation/planCacheStats/)
- [MongoDB Java Sync Driver — Cursors and Explain](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/cursor/)
- [MongoDB Java Sync Driver — Indexes](https://www.mongodb.com/docs/drivers/java/sync/current/indexes/)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Testcontainers MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/)

> **Lưu ý:** `explain` output format không được MongoDB bảo đảm cố định, kể cả khi dùng Stable API. Khi viết parser hoặc test stage-specific, phải đối chiếu chính xác MongoDB Server version, execution engine, topology và Java Driver đang triển khai. Các ví dụ dùng isolated test database, không phải lệnh chạy trên production.

---

## 61. Tổng kết

1. **Không dùng milliseconds của một lần query làm điều kiện pass/fail chính trong CI.** Time bị ảnh hưởng bởi JVM, network, cache, load và planner.
2. **Kiểm thử hiệu quả truy vấn** nên tập trung vào correctness, index contract, `nReturned`, `totalDocsExamined`, `totalKeysExamined` và ngân sách scan phù hợp workload.
3. **Explain("executionStats")** là công cụ quan sát logical work rất hữu ích, nhưng **bỏ qua plan cache** và timing của explain không đồng nghĩa steady-state production latency.
4. **IXSCAN không tự chứng minh query tốt; COLLSCAN không tự chứng minh query sai.** Cần đọc khối lượng công việc thực và mục tiêu nghiệp vụ.
5. **Cây winningPlan không bất biến** giữa classic/SBE/EXPRESS/sharded versions. Tránh exact JSON equality và exact stage paths trừ khi test pin version rõ ràng.
6. **Fixture phải deterministic và đủ lớn**, có phân bố selectivity đại diện để regression index thật sự làm scan budgets vượt ngưỡng.
7. **Tách no-hint main test khỏi hinted diagnosis**. Hint có ích để so các access paths nhưng có thể che vấn đề planner tự chọn index.
8. **Index catalog và query-plan tests bổ sung cho nhau**: một test xác nhận migrations tạo đúng index, test kia xác nhận query không quét quá nhiều.
9. **Aggregation, multikey, deep pagination và sharding** có semantics khác; không sao chép một budget từ equality top-10 query cho mọi operation.
10. **Benchmark thực sự phải đo nhiều mẫu và percentiles** trên môi trường có kiểm soát, đồng thời quan sát throughput, concurrency, CPU, I/O và error rate.

**Nguyên tắc cuối cùng:** Kiểm thử CI nên chặn những thay đổi làm **khối lượng công việc logic tăng bất thường**, còn benchmark và production monitoring trả lời câu hỏi **hệ thống thực sự nhanh đến mức nào**. Tách hai mục tiêu này giúp test ít flaky hơn mà vẫn phát hiện được những hồi quy query plan có ý nghĩa.
