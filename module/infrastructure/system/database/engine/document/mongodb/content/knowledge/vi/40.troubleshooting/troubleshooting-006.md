# Truy vấn chậm do thiếu index, sort, collation hoặc kiểu dữ liệu trong MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chương:** Xử lý sự cố  
> **Bài học:** Truy vấn chậm do thiếu index, sort, collation hoặc kiểu dữ liệu

## 1. Tình huống và mục tiêu

Một ứng dụng bán hàng đang sử dụng MongoDB có bốn endpoint bất ngờ chậm hoặc trả thiếu kết quả:

- `GET /orders?tenant=t05&status=PAID` phải duyệt hàng trăm nghìn bản ghi để lấy 20 đơn gần nhất.
- Một API báo cáo `sort({createdAt:-1})` phải sắp xếp trong RAM và đôi khi ghi file tạm.
- Tìm tên khách hàng không phân biệt hoa/thường đã có index nhưng optimizer vẫn chọn `COLLSCAN`.
- Truy vấn lọc sau ngày 1/11 không tìm được một số documents vì `createdAt` được lưu lẫn BSON Date và String.

Cả bốn đều có thể xuất hiện dưới triệu chứng “MongoDB slow query”, nhưng không thể sửa bằng cùng một câu lệnh `createIndex()`. Cách xử lý đúng bắt đầu bằng **xác minh kết quả, query shape, kiểu BSON, collation, index catalog và execution plan**, sau đó mới thử giải pháp và đo tác động.

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Tìm query chậm từ logs, profiler, metrics và application traces.
2. Đọc `explain("executionStats")` để xác định lượng document/index key phải xét.
3. Phân biệt thiếu index với index sai thứ tự hoặc không đủ chọn lọc.
4. Phân tích `IXSCAN`, `COLLSCAN`, `FETCH`, `SORT` và `indexBounds`.
5. Thiết kế compound index theo equality/sort/range, hiểu ESR và ERS.
6. Giải thích blocking sort, memory spill, pagination và hướng sort.
7. Chẩn đoán collation mismatch giữa query, collection và index.
8. Hiểu `strength`, `locale`, `numericOrdering`, giới hạn của `$regex /i`.
9. Phát hiện và sửa lỗi String/ObjectId, String/BSON Date, String/Number.
10. Thực hành mongosh, Java Sync Driver, Spring Data, kiểm thử và runbook production.

### 1.2. Phân loại bốn nguyên nhân

| Nguyên nhân | Dấu hiệu ban đầu | Cách kiểm chứng |
|---|---|---|
| Thiếu hoặc sai index | `COLLSCAN`, docsExamined lớn | `getIndexes()`, explain, query filter |
| Sort không có index phù hợp | `SORT`, memory/spill, latency tăng theo tập dữ liệu | Sort fields/direction, index prefix, explain |
| Collation mismatch | Index string tồn tại nhưng không hỗ trợ phép so sánh | Index/collection/query collation |
| BSON types không nhất quán | Query thiếu kết quả, filter chuyển kiểu, sort lạ | `$type`, query operand types, migration history |

**Cảnh báo:** `COLLSCAN` trên một collection nhỏ hoặc query analytics quét toàn tập có thể hợp lý. `IXSCAN` quét triệu keys vẫn có thể rất chậm. Không đánh giá bằng tên stage đơn lẻ.

---

## 2. Xác định “chậm” đang nằm ở đâu

Một HTTP request trải qua nhiều tầng:

```text
HTTP client
    │
    ├── API authentication, validation, serialization
    ├── Java Driver server selection / connection pool
    ├── Network, TLS, retries
    ▼
MongoDB server
    │
    ├── Query parse, optimization, plan cache
    ├── Index scan hoặc collection scan
    ├── FETCH / filter
    ├── SORT / aggregation / grouping
    ├── Storage cache, I/O, concurrency
    └── Cursor firstBatch / getMore
    ▼
Java Driver BSON decoding
    │
    ▼
HTTP response
```

Nếu application p99 là 1 giây nhưng MongoDB server-side command chỉ mất 20 ms, phải điều tra connection pool/network/application. Nếu profiler ghi 700 ms, `docsExamined=900000` và `planSummary=COLLSCAN` thì query plan đáng ưu tiên.

### 2.1. Cần thu thập những dữ kiện nào?

- Namespace, thời gian xảy ra, host/member/shard và MongoDB Server version.
- Query filter, projection, sort, collation, limit, skip, hint.
- BSON types thực của operands và stored fields.
- Số documents của collection và phân bố dữ liệu.
- Index catalog (keys, order, collation, hidden/partial options).
- Explain statistics và slow log/profiler record.
- Application/driver metrics và resource utilization.
- Những deploy, schema migrations hoặc index changes gần đây.

### 2.2. Query correctness đứng trước performance

Một truy vấn dùng String để tìm ObjectId có thể trả 0 document rất nhanh. Đó là **lỗi correctness**. Nếu ứng dụng thấy 0 kết quả rồi fallback quét toàn collection để tìm bằng conversion, nó trở thành cả **lỗi hiệu năng**. Luôn kiểm tra kết quả đúng trước khi “tối ưu”.

---

## 3. Lưu nguyên query shape

Ví dụ:

```javascript
db.orders.find(
  {
    tenantId: "t05",
    status: "PAID"
  },
  {
    customerId: 1,
    total: 1,
    createdAt: 1
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.collation({ locale: "simple" });
```

Không bỏ qua bất kỳ chi tiết nào:

- Thêm `tenantId` có thể thay đổi index cần thiết.
- `sort({_id:-1})` làm tie-breaker có thể thay đổi index direction.
- `limit` ảnh hưởng kế hoạch top-N.
- `collation` ảnh hưởng string comparison và index use.
- `$in`, `$gt` và `$ne` có selectivity khác equality.
- `hint` có thể ép một index không tốt.
- Query parameters của tenant có 500 records khác tenant 5 triệu records.

### 3.1. Hai query không tương đương

```javascript
db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(20);

db.orders.find({ tenantId: "t05", status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(20);
```

Một compound index có equality prefix `tenantId` có thể rất tốt cho query thứ hai nhưng không nhất thiết tốt cho query thứ nhất.

### 3.2. Không chỉ đọc source code

Ứng dụng có thể truyền String thay vì BSON Date, thêm sort/hint qua framework hoặc sử dụng collation theo request. Khi cần, dùng sanitized driver command monitoring để xác minh command thực gửi xuống server.

---

## 4. Giải thích explain("executionStats")

### 4.1. Lệnh cơ bản

```javascript
const plan = db.orders.find({
  tenantId: "t05",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");

printjson(plan.queryPlanner);
printjson(plan.executionStats);
```

Ba mức phổ biến:

- `queryPlanner`: winning plan và rejected candidates khi có.
- `executionStats`: statistics từ việc thực thi winning plan.
- `allPlansExecution`: bổ sung thông tin trial execution cho các candidate plans.

### 4.2. Các trường quan trọng

| Trường | Cần hiểu |
|---|---|
| `nReturned` | Số kết quả của execution được giải thích |
| `totalDocsExamined` | Số lần xét documents, có thể tính một document nhiều lần |
| `totalKeysExamined` | Số index entries đã xét |
| `winningPlan` | Access path được planner chọn |
| `indexName` | Index được stage dùng, nếu có |
| `indexBounds` | Bounds/range được duyệt |
| `executionTimeMillis` | Timing của explain, không phải cam kết latency ổn định |
| `usedDisk`/`spills` | Tín hiệu disk spill khi được hỗ trợ |

### 4.3. Ví dụ collection scan

```javascript
{
  queryPlanner: {
    winningPlan: { stage: "COLLSCAN" }
  },
  executionStats: {
    nReturned: 20,
    totalDocsExamined: 500000,
    totalKeysExamined: 0,
    executionTimeMillis: 400
  }
}
```

Các số liệu minh họa. Với một API listing lấy 20 documents, `500000/20=25000` là scan ratio cần điều tra.

### 4.4. Ví dụ indexed access hiệu quả

```javascript
{
  queryPlanner: {
    winningPlan: {
      stage: "FETCH",
      inputStage: {
        stage: "IXSCAN",
        indexName: "idx_tenant_status_created"
      }
    }
  },
  executionStats: {
    nReturned: 20,
    totalDocsExamined: 20,
    totalKeysExamined: 20
  }
}
```

Đây là example output giản lược, không phải cấu trúc JSON cố định.

### 4.5. Không dùng exact plan tree làm điều kiện chung

MongoDB Classic Engine, SBE, EXPRESS fast paths và sharded explain có cấu trúc khác nhau. Một số versions có:

```text
winningPlan.inputStage
winningPlan.queryPlan
winningPlan.slotBasedPlan
per-shard winningPlans
```

Chỉ hardcode stage path khi test pin MongoDB version/topology. Ưu tiên đọc logical work và index metadata.

### 4.6. Explain không phản ánh hoàn toàn plan cache production

Theo MongoDB documentation, `explain()` bỏ qua cached plan hiện có và không cache winning plan của lần explain. Vì vậy explain là **chứng cứ về hành vi truy vấn tại thời điểm test**, không xác nhận chắc chắn plan mà request production trước đó đã sử dụng.

### 4.7. Không assert thời gian ngẫu nhiên

Sai cho CI regression:

```javascript
if (plan.executionStats.executionTimeMillis > 10) {
  throw new Error("Slow query");
}
```

Đúng hướng hơn:

```javascript
const s = plan.executionStats;
if (s.totalDocsExamined > 100 ||
    s.totalKeysExamined > 200) {
  throw new Error("Excessive scan work");
}
```

Ngưỡng chỉ hợp lý với fixture và query xác định. Latency SLO vẫn cần benchmark riêng.

---

## 5. Nguyên nhân 1: index thiếu hoặc không phù hợp

### 5.1. getIndexes là bước đầu

```javascript
db.orders.getIndexes();
```

Kiểm tra:

- Key pattern và thứ tự.
- Direction 1/-1.
- Unique, partial, sparse, hidden.
- Index type (B-tree, hashed, text, wildcard, multikey).
- Collation.
- Cùng database/collection trên đúng cluster.

### 5.2. Nhiều single-field indexes không tương đương compound index

Giả sử có:

```javascript
db.orders.createIndex({ tenantId: 1 });
db.orders.createIndex({ status: 1 });
db.orders.createIndex({ createdAt: -1 });
```

Query:

```javascript
db.orders.find({
  tenantId: "t05",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(20);
```

MongoDB có thể phải scan một index rộng rồi filter/sort bổ sung. Dù engine có khả năng dùng index intersection ở một số tình huống, đó không phải thay thế được bảo đảm cho một compound index đúng workload.

### 5.3. Compound index đề xuất

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);
```

Index này tổ chức hai equality predicates trước và sort field sau.

### 5.4. Vì sao key order quan trọng?

Index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

khác:

```javascript
{ createdAt: -1, status: 1, tenantId: 1 }
```

đối với việc thu hẹp bounds theo tenant/status và lấy thứ tự createdAt. Đừng xem compound index chỉ là danh sách field names không có thứ tự.

### 5.5. Prefix rule

Index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

có prefixes:

```javascript
{ tenantId: 1 }
{ tenantId: 1, status: 1 }
{ tenantId: 1, status: 1, createdAt: -1 }
```

Query chỉ có `status:"PAID"` không có `tenantId` thường không thu hẹp range như query có equality prefix.

### 5.6. Đọc indexBounds

Explain có thể cho:

```javascript
indexBounds: {
  tenantId: ['["t05", "t05"]'],
  status: ['["PAID", "PAID"]'],
  createdAt: ["[MaxKey, MinKey]"]
}
```

Output mang tính minh họa; syntax bounds, ordering và availability khác engine/version.

- Equality bounds hẹp: tốt cho selective filter.
- Bounds gần toàn domain: index có thể quét rộng.
- Query thiếu predicate trên prefix: những keys sau có thể không được tận dụng hiệu quả.

### 5.7. Index không phải luôn được chọn

Ngay cả khi tồn tại index đúng, planner vẫn có thể chọn COLLSCAN khi collection nhỏ hoặc predicate không chọn lọc. Xác minh dữ liệu và chi phí thay vì ép index ngay.

---

## 6. ESR/ERS: equality, sort, range

### 6.1. Quy tắc ESR

- **E — Equality**: những fields bằng hằng số.
- **S — Sort**: những fields cần thứ tự.
- **R — Range**: phạm vi `$gte`/`$lte`/`$gt`/`$lt`.

Query:

```javascript
db.orders.find({
  tenantId: "t05",
  status: "PAID",
  total: { $gte: 1000 }
}).sort({ createdAt: -1 }).limit(20);
```

Index ESR ứng viên:

```javascript
{
  tenantId: 1,
  status: 1,
  createdAt: -1,
  total: 1
}
```

### 6.2. Khi ERS có thể tốt hơn

Nếu `total>=1000000` cực chọn lọc, index:

```javascript
{
  tenantId: 1,
  status: 1,
  total: 1,
  createdAt: -1
}
```

có thể giảm số entries được scan, dù có thể cần sort trong memory. ESR ưu tiên tránh sort; ERS ưu tiên thu hẹp rất sớm bằng range. **Không có một thứ tự tối ưu cho mọi query**.

### 6.3. Cách quyết định

1. Ước lượng equality selectivity.
2. Xem range có chọn lọc mạnh không.
3. Xem số rows thực cần sort.
4. So explain với candidate indexes trong môi trường test.
5. Benchmark nếu chênh lệch cost/time đáng kể.
6. Đánh giá write amplification và dung lượng index.

### 6.4. Không tạo index cho mỗi query không giới hạn

Mỗi index làm tăng storage, cache pressure và chi phí insert/update/delete. Tìm index phục vụ nhóm query shapes quan trọng, tránh redundant indexes.

---

## 7. Vì sao index có sẵn nhưng vẫn COLLSCAN?

| Nguyên nhân | Ví dụ |
|---|---|
| Index không có equality prefix | Index bắt đầu bằng customerId, query chỉ filter status |
| Index không có sort field | Filter tốt, nhưng blocking SORT |
| Filter rất ít chọn lọc | 95% documents match |
| Collection nhỏ | Full scan rẻ hơn index traversal |
| Partial index không cover query | Query thiếu điều kiện active:true |
| Hidden index | Có index trong catalog nhưng planner không dùng |
| Index collation không khớp | String equality với simple query, index ICU |
| Query tính expression trên field | `$expr/$toDate` khiến predicate khó dùng index |
| Hint ép index sai | Application hardcode hint cũ |
| Shard/node khác | Index build/status hoặc workload không như kỳ vọng |
| Query type mismatch | Filter không match hoặc ép conversion |
| Plan cache/replanning | Production cached path khác explain |

### 7.1. Partial index

```javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  {
    name: "idx_active_by_tenant",
    partialFilterExpression: { active: true }
  }
);
```

Query không bảo đảm `active:true` có thể không dùng partial index vì nếu dùng sẽ bỏ mất inactive documents mà query vẫn cần.

### 7.2. Hidden index

Hidden index có thể xuất hiện trong `getIndexes()` nhưng không được optimizer chọn. Không lập tức tạo một index trùng; trước tiên kiểm tra hidden state và rollout history.

### 7.3. Hashed index

Một hashed index phù hợp equality/sharding workload nhưng không phục vụ range/sort giống ascending/descending B-tree index. Cần phân biệt index type.

### 7.4. Multikey index

Array values tạo nhiều index entries; keysExamined có thể lớn hơn docsExamined. Compound multikey indexes có restrictions; sort trên array field có thể vẫn cần in-memory sort.

### 7.5. Wildcard/text indexes

Wildcard, text, geospatial và vector/search indexes có behavior khác conventional compound index. Không dùng một heuristic ESR từ scalar equality query cho mọi loại search.

---

## 8. Nguyên nhân 2: sort khiến query chậm

### 8.1. Index có thể cung cấp sort order

Với:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

query:

```javascript
db.orders.find({
  tenantId: "t05",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(20);
```

có thể duyệt entries đúng thứ tự và tránh sort thêm.

### 8.2. Blocking sort

Khi index không hỗ trợ order:

```text
COLLSCAN/IXSCAN → FETCH/filter → SORT → LIMIT
                                      │
                                      └── memory hoặc disk spill
```

Một query trả chỉ 20 documents sau limit có thể phải đọc và sort rất nhiều candidates.

### 8.3. Dấu hiệu

- Plan chứa `SORT` hoặc equivalent engine stage.
- Docs/keys examined cao.
- Memory/spill statistics khi được hỗ trợ.
- Logs/profiler có `usedDisk`.
- Latency tăng rõ khi số candidates tăng.

### 8.4. Index sort direction

Index đơn:

```javascript
{ createdAt: 1 }
```

có thể hỗ trợ cả sort tăng và giảm bằng cách duyệt index forward/backward.

Compound index có nhiều sort fields chỉ hỗ trợ các direction patterns phù hợp hoặc đảo ngược **toàn bộ** pattern.

Ví dụ index:

```javascript
{ score: -1, createdAt: 1 }
```

thường hỗ trợ:

```javascript
{ score: -1, createdAt: 1 }
{ score: 1, createdAt: -1 }
```

không mặc định hỗ trợ cùng hiệu quả:

```javascript
{ score: -1, createdAt: -1 }
```

### 8.5. Equality prefix trước sort

Index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

để dùng sort theo createdAt hiệu quả thường cần equality predicates cho preceding keys tenantId/status.

Nếu status thay đổi mà query chỉ filter tenantId, entries được nhóm theo status nên không phải một dãy createdAt giảm duy nhất trong cả tenant.

### 8.6. Sort có thể hợp lý

Một báo cáo full scan và sort 2.000 records có thể đủ nhanh. Đừng buộc tạo index nếu write overhead lớn hơn lợi ích thực tế.

---

## 9. Sort memory, disk spill và allowDiskUse

### 9.1. Giới hạn memory

Nhiều MongoDB releases có memory threshold khoảng 100 MB cho những pipeline stages như `$sort`. Từ MongoDB 6.0, `allowDiskUseByDefault` điều khiển việc stages vượt threshold có spill ra disk mặc định hay báo lỗi. Những versions mới có thể có thêm per-operation memory limits.

Luôn kiểm tra actual MongoDB Server version/config trước khi kết luận.

### 9.2. allowDiskUse

```javascript
db.orders.aggregate(
  [
    { $match: { status: "PAID" } },
    { $sort: { createdAt: -1 } }
  ],
  { allowDiskUse: true }
);
```

Nó cho phép temporary disk usage khi operation/stage hỗ trợ; **không có nghĩa truy vấn được tối ưu**. Có thể tăng disk I/O, latency và áp lực dung lượng.

### 9.3. $sort + $limit

```javascript
db.orders.aggregate([
  { $match: { tenantId: "t05", status: "PAID" } },
  { $sort: { createdAt: -1 } },
  { $limit: 20 }
]);
```

MongoDB có thể coalesce `$sort` và `$limit` khi không có intervening stages thay đổi số rows, chỉ cần giữ top N.

### 9.4. Sai thứ tự làm thay đổi kết quả

Không được sửa:

```javascript
[{ $sort: { createdAt: -1 } }, { $limit: 20 }]
```

thành:

```javascript
[{ $limit: 20 }, { $sort: { createdAt: -1 } }]
```

nếu nghiệp vụ cần 20 documents mới nhất toàn collection. Thao tác sau chỉ sort trong 20 documents được lấy trước.

### 9.5. Sort sau aggregation

```javascript
db.orders.aggregate([
  { $group: { _id: "$tenantId", revenue: { $sum: "$total" } } },
  { $sort: { revenue: -1 } }
]);
```

`revenue` là computed field sau `$group`; index trên raw `total` không tự phục vụ sort trên grouped revenue. Có thể cần materialized summaries, caching, batch report hoặc chấp nhận sort phù hợp.

---

## 10. Sort ổn định, pagination và skip

### 10.1. Thứ tự không xác định với duplicate sort values

Nếu hai documents cùng createdAt, sort:

```javascript
.sort({ createdAt: -1 })
```

không đảm bảo thứ tự duy nhất giữa các documents có timestamp bằng nhau.

### 10.2. Tie-breaker

```javascript
.sort({ createdAt: -1, _id: -1 })
```

Index ứng viên:

```javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
```

Phải đảm bảo _id type/schema phù hợp, nhất là dữ liệu legacy.

### 10.3. Deep skip

```javascript
db.orders.find(filter)
  .sort({ createdAt: -1, _id: -1 })
  .skip(100000)
  .limit(20);
```

Ngay cả với index phù hợp, server vẫn phải đi qua nhiều entries để bỏ qua offset lớn.

### 10.4. Keyset pagination

Lưu boundary cuối trang:

```javascript
const lastCreatedAt =
  ISODate("2026-11-01T10:00:00Z");
const lastId = "t05-0999"; // Nếu _id là String trong schema.

db.orders.find({
  tenantId: "t05",
  status: "PAID",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

Không áp dụng nguyên xi khi ID là ObjectId hoặc sort/collation khác. Cần kiểm tra lexicographic ordering, tie-breakers và behavior khi dữ liệu thay đổi giữa các pages.

---

## 11. Nguyên nhân 3: collation mismatch

### 11.1. Collation là gì?

Collation quy định cách so sánh strings theo locale, lettercase, diacritics, numeric ordering và các quy tắc ICU. Nếu collection/query không chỉ định collation, MongoDB thường dùng `locale:"simple"` với binary comparison.

Có ba nơi cần kiểm tra:

1. Collection default collation.
2. Index collation.
3. Query/aggregate collation.

### 11.2. Case-insensitive index

```javascript
db.customers.createIndex(
  { displayName: 1 },
  {
    name: "idx_name_ci",
    collation: { locale: "en", strength: 2 }
  }
);
```

`strength:2` thường bỏ qua case nhưng phân biệt accents theo ICU locale. `strength:1` thường bỏ qua cả accents và case ở primary comparison level, phụ thuộc locale/options.

### 11.3. Query matching collation

```javascript
db.customers.find({ displayName: "alice" })
  .collation({ locale: "en", strength: 2 });
```

Nếu collection mặc định simple, query sau:

```javascript
db.customers.find({ displayName: "alice" });
```

có binary semantics. Một index ICU strength 2 không thể tự cung cấp đúng string comparison của query simple.

### 11.4. Collation mismatch không luôn vô hiệu toàn index

Một compound index collation ICU vẫn có thể hỗ trợ một số comparisons trên non-string prefix fields tùy query. Chính xác hơn: mismatch có thể khiến index **không hỗ trợ string comparison hoặc string sort** theo semantics cần.

### 11.5. Kiểm tra metadata

```javascript
db.customers.getIndexes();
```

Xem cả:

- `locale`.
- `strength`.
- `caseLevel`.
- `numericOrdering`.
- Các options khác liên quan.

Không chỉ so tên field.

### 11.6. Default inheritance

Collection có collation default thì indexes và operations thường kế thừa collation đó nếu không khai báo override. Vì vậy tìm hiểu collection được tạo lúc nào và với options gì.

---

## 12. Strength, tiếng Việt có dấu và thay đổi semantics

### 12.1. Các levels thường gặp

| Strength | Mô tả giản lược |
|---|---|
| `1` Primary | Bỏ qua nhiều khác biệt case/accent |
| `2` Secondary | Thường phân biệt accents nhưng không phân biệt case |
| `3` Tertiary | Thường tính cả case |
| `4`/`5` | Thêm các khác biệt chi tiết theo locale/settings |

Đây là khái quát ICU; kết quả thực tế phụ thuộc locale và cấu hình.

### 12.2. Tên tiếng Việt

Với tên `Nguyễn`, `nguyen`, `NGUYỄN`, API phải quyết định:

- Tìm exact hay case-insensitive?
- Có bỏ dấu hay không?
- Có tìm prefix/substring?
- Dữ liệu có chuẩn Unicode NFC/NFD chưa?
- Có hỗ trợ tên nhiều ngôn ngữ?

Không mặc định `locale:"en"` phù hợp mọi quy tắc tiếng Việt. Thử `locale:"vi"` và các strength levels phù hợp môi trường.

### 12.3. Unique index có thể bị ảnh hưởng

```javascript
db.users.createIndex(
  { username: 1 },
  {
    unique: true,
    name: "uq_username_ci",
    collation: { locale: "en", strength: 2 }
  }
);
```

Nó có thể coi `alice` và `ALICE` là duplicate. Thay collation có thể làm index build fail do dữ liệu đã có, nên phải audit duplicate candidates trước rollout.

### 12.4. Không chỉ đổi collation để “tăng tốc”

Collation ảnh hưởng **correctness**. Nếu query trước đây phân biệt case mà giờ không, số matches thay đổi. Phải test behavior nghiệp vụ và unique rules.

---

## 13. $regex /i và giới hạn của collation indexes

### 13.1. Anti-pattern phổ biến

```javascript
db.customers.find({
  displayName: { $regex: "^alice", $options: "i" }
});
```

Team tạo index:

```javascript
db.customers.createIndex(
  { displayName: 1 },
  { collation: { locale: "en", strength: 2 } }
);
```

MongoDB documentation nêu `$regex` **không collation-aware**, nên case-insensitive indexes không cải thiện regex queries theo cách equality với collation có thể làm được.

### 13.2. Các kiểu search khác nhau

| Tìm kiếm | Gợi ý |
|---|---|
| Equality không phân biệt case | Matching query/index collation |
| Prefix case-sensitive, anchored | Có thể dùng B-tree prefix range khi phù hợp |
| Prefix case-insensitive | Normalized search key hoặc công cụ search phù hợp |
| Substring/full-text | Cân nhắc specialized search index/Atlas Search |
| Fuzzy, accent-aware | Thiết kế search semantics & relevance, không đơn giản B-tree |

### 13.3. Normalized field

Ví dụ:

```json
{
  "displayName": "Nguyễn Văn A",
  "searchKey": "nguyen van a"
}
```

Index `searchKey` khi nghiệp vụ đã quy định normalization. Không tự viết thuật toán bỏ dấu thiếu kiểm thử Unicode/locale, và không coi normalized key hoàn toàn tương đương ICU comparison.

### 13.4. Regex input từ user

Không đưa nguyên regex user input vào MongoDB vô kiểm soát; regular expressions có thể tốn CPU hoặc tạo scans lớn. Có giới hạn độ dài, operators và logic escape/validation phù hợp.

---

## 14. numericOrdering không phải ép kiểu String sang Number

Data:

```javascript
{ code: "2" }
{ code: "10" }
{ code: "100" }
```

Simple lexicographic order có thể là `"10", "100", "2"`.

```javascript
db.codes.find().sort({ code: 1 })
  .collation({ locale: "en", numericOrdering: true });
```

có thể sắp các non-negative integer digit substrings theo giá trị.

### 14.1. Giới hạn

Theo MongoDB documentation, `numericOrdering:true` không hỗ trợ đầy đủ:

- Dấu âm hoặc dấu cộng.
- Decimal separators.
- Exponents.
- Một số chuỗi chữ số quá dài.

Không dùng numericOrdering thay cho data model của tiền tệ, số lượng hoặc số đo.

### 14.2. Chọn BSON Number cho giá

Nếu field `price` cần so sánh số học, nên dùng NumberInt/NumberLong/Double/Decimal128 phù hợp, thay vì lưu thành String và hy vọng collation tự hiểu.

---

## 15. Nguyên nhân 4: BSON types không nhất quán

### 15.1. Flexible schema là con dao hai lưỡi

MongoDB cho phép một field mang các types khác nhau nếu không có schema validation.

Ví dụ:

```javascript
{
  _id: ObjectId("65b8f9a53a9b43885f4e52c1"),
  createdAt: ISODate("2026-11-01T00:00:00Z"),
  total: NumberDecimal("150.00")
}

{
  _id: "65b8f9a53a9b43885f4e52c2",
  createdAt: "2026-11-02T00:00:00Z",
  total: "150.00"
}
```

Một index trên createdAt không tự chuyển String sang Date; một index trên total không đổi String thành Decimal128.

### 15.2. Triệu chứng

- Lookup bằng ID “trông giống nhau” nhưng không match.
- Date range trả thiếu.
- Sort trường ngày/giá thành các nhóm bất ngờ.
- Query dùng `$toDate/$toString` trên field gây work lớn.
- Một migration nhập CSV/JSON và thay BSON types.
- Hai services serialize field theo conventions khác nhau.

### 15.3. Type bracketing

Các comparison query operators `$gt`, `$gte`, `$lt`, `$lte` có **type bracketing**: chúng thường so với BSON values thuộc type category thích hợp.

### 15.4. Numeric types là nhóm đặc biệt

Int32, Int64, Double và Decimal128 được MongoDB xem như numeric types có thể so sánh với nhau theo numeric comparison semantics. String `"150"` **không phải** Number 150.

### 15.5. $ne/$nin khác range predicates

`$ne` và `$nin` không type-bracket giống `$gt/$gte/$lt/$lte`. Không dựa vào behavior `$ne` để suy ra range queries tự ép kiểu.

### 15.6. BSON sort order

Với mixed types, MongoDB sắp xếp theo BSON type comparison order. Đừng nghĩ tất cả values hiển thị “ngày tháng” sẽ sắp theo thời gian nếu một phần là strings.

---

## 16. ObjectId khác String

### 16.1. Tạo document có ObjectId

```javascript
db.orders.insertOne({
  _id: ObjectId("65b8f9a53a9b43885f4e52c1"),
  status: "PAID"
});
```

### 16.2. Query sai type

```javascript
db.orders.findOne({
  _id: "65b8f9a53a9b43885f4e52c1"
});
```

BSON String không bằng BSON ObjectId tương ứng. Có thể trả null dù cả hai hiển thị chuỗi hex giống nhau.

### 16.3. Query đúng

```javascript
db.orders.findOne({
  _id: ObjectId("65b8f9a53a9b43885f4e52c1")
});
```

### 16.4. Anti-pattern conversion trên server

```javascript
db.orders.find({
  $expr: {
    $eq: [
      { $toString: "$_id" },
      "65b8f9a53a9b43885f4e52c1"
    ]
  }
});
```

Server phải đánh giá expression trên nhiều documents và có thể không tận dụng index `_id` trực tiếp. Hãy chuyển incoming ID sang BSON type đúng ở application boundary.

### 16.5. Không convert mọi String ID thành ObjectId

Nhiều schema chủ ý lưu String ID. Kiểu lưu thực của collection quyết định nên query bằng String hay ObjectId; không tự đoán từ độ dài chuỗi.

---

## 17. BSON Date khác chuỗi ngày ISO

### 17.1. Data

```javascript
{ _id: 1, createdAt: ISODate("2026-11-01T00:00:00Z") }
{ _id: 2, createdAt: "2026-11-01T00:00:00Z" }
```

### 17.2. Query Date range

```javascript
db.events.find({
  createdAt: {
    $gte: ISODate("2026-10-01T00:00:00Z")
  }
});
```

Range predicate với BSON Date không tự parse document String thành Date.

### 17.3. Kiểm tra kiểu

```javascript
db.events.aggregate([
  {
    $group: {
      _id: { $type: "$createdAt" },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

### 17.4. Tại sao String ISO vẫn không ổn?

Có thể có:

- Offsets `+07:00` và `Z`.
- Format thiếu milliseconds.
- Date strings không cùng format.
- Mixed String/Date.
- Parse errors hoặc timezone assumptions.

Dù một nhóm ISO strings chuẩn đôi khi có lexicographic order tương ứng, nó không thay thế BSON Date.

### 17.5. $toDate trong $expr

```javascript
db.events.find({
  $expr: {
    $gte: [
      { $toDate: "$createdAt" },
      ISODate("2026-11-01T00:00:00Z")
    ]
  }
});
```

Cách này có thể phải convert nhiều documents tại runtime, giảm khả năng dùng index trực tiếp. Chuỗi không parse được cũng có thể làm lỗi operation.

### 17.6. Hướng xử lý

- Parse/validate ngay ở Java API boundary.
- Migrate String → BSON Date bằng batches an toàn.
- Dùng schema validation.
- Kiểm thử timezone và Date precision.
- Xem lại index sau khi dữ liệu nhất quán.

---

## 18. Numeric BSON types và String number

Data:

```javascript
db.products.insertMany([
  { _id: 1, price: NumberInt(150) },
  { _id: 2, price: NumberLong("150") },
  { _id: 3, price: 150.0 },
  { _id: 4, price: NumberDecimal("150.00") },
  { _id: 5, price: "150" }
]);
```

Query:

```javascript
db.products.find({
  price: { $gte: 100 }
});
```

Có thể match các numeric values, nhưng không auto-convert String `"150"`.

### 18.1. Vì sao vừa correctness vừa hiệu năng?

Nếu UI không thấy sản phẩm có String price, developer có thể viết fallback aggregation convert toàn collection, tạo CPU pressure thay vì sửa schema.

### 18.2. Decimal128 và tiền tệ

Khi cần decimal semantics chính xác, cân nhắc `Decimal128`/Java `BigDecimal` mapping hoặc integer minor units theo policy. Không đổi schema numeric production mà không xem converters/rounding rules.

### 18.3. $type kiểm tra

```javascript
db.products.aggregate([
  {
    $group: {
      _id: { $type: "$price" },
      count: { $sum: 1 }
    }
  }
]);
```

### 18.4. Không dùng numericOrdering để sửa price

Numeric ordering chỉ ảnh hưởng string collation. Tối ưu đúng là lưu price bằng numeric BSON types phù hợp.

---

## 19. Java Sync Driver: xử lý đúng BSON operands

### 19.1. ObjectId

```java
import org.bson.types.ObjectId;
import static com.mongodb.client.model.Filters.eq;

String incomingId = "65b8f9a53a9b43885f4e52c1";

if (!ObjectId.isValid(incomingId)) {
    throw new IllegalArgumentException("Invalid ObjectId");
}

ObjectId id = new ObjectId(incomingId);
Document order = orders.find(eq("_id", id)).first();
```

Chỉ dùng khi `_id` được lưu là ObjectId. Nếu collection dùng String ID, giữ String.

### 19.2. BSON Date

Sai khi field là Date:

```java
orders.find(Filters.gte(
        "createdAt", "2026-11-01")).first();
```

Đúng:

```java
import java.time.Instant;
import java.util.Date;

Date threshold = Date.from(
        Instant.parse("2026-11-01T00:00:00Z"));

Document order = orders.find(
        Filters.gte("createdAt", threshold)
).first();
```

### 19.3. Collation với Java Driver

```java
import com.mongodb.client.model.Collation;
import com.mongodb.client.model.CollationStrength;

Collation caseInsensitive = Collation.builder()
        .locale("en")
        .collationStrength(CollationStrength.SECONDARY)
        .build();

Document customer = customers
        .find(Filters.eq("displayName", "alice"))
        .collation(caseInsensitive)
        .first();
```

Index trên displayName cần collation tương ứng nếu muốn cải thiện string lookup. Đừng chỉ thay driver options mà bỏ qua catalog.

### 19.4. Explain bằng Java Driver

```java
import com.mongodb.ExplainVerbosity;

Document explain = orders.find(
        Filters.and(
                Filters.eq("tenantId", "t05"),
                Filters.eq("status", "PAID")))
        .sort(Sorts.descending("createdAt"))
        .limit(20)
        .explain(ExplainVerbosity.EXECUTION_STATS);

Document stats = explain.get(
        "executionStats", Document.class);

long returned =
        ((Number) stats.get("nReturned")).longValue();
long examined =
        ((Number) stats.get("totalDocsExamined")).longValue();
long keys =
        ((Number) stats.get("totalKeysExamined")).longValue();
```

Kiểm tra null/field availability khi dùng thực tế. `Number` tránh phụ thuộc numeric field có decode thành Integer hay Long.

### 19.5. Spring Data MongoDB

Spring Data mapping có thể chuyển `@Id String` thành ObjectId trong một số flows; `@MongoId` và converters có thể giúp chỉ rõ desired representation. Luôn kiểm tra BSON lưu thật và query BSON types từ integration tests.

Với `BigDecimal`, quyết định Decimal128 hay String representation theo mapping/annotations và migration rules. Không giả định đổi Java property type sẽ tự sửa documents cũ.

---

## 20. Từ slow logs tới query shape

### 20.1. Diagnostic slow-operation logs

Một MongoDB structured log có thể ghi:

```json
{
  "s": "I",
  "c": "COMMAND",
  "msg": "Slow query",
  "attr": {
    "ns": "commerce.orders",
    "planSummary": "COLLSCAN",
    "docsExamined": 500000,
    "keysExamined": 0,
    "durationMillis": 850
  }
}
```

Đây là ví dụ rút gọn, không phải exact schema.

### 20.2. Database profiler

`system.profile` có thể lưu operation details khi profiler được bật theo level/threshold/filter. Nó có chi phí CPU/I/O/storage/PII; không bật profiling level 2 lâu dài chỉ vì cần một slow query.

### 20.3. Driver metrics

Dùng `CommandListener` hoặc tracing để đo command duration ở client; đối chiếu server logs, pool wait, retries và cursor batches. Không so trực tiếp `explain.executionTimeMillis` với HTTP p99 mà bỏ qua môi trường.

### 20.4. Chọn representative queries

Lấy query shapes/field types từ telemetry đã sanitize, không copy raw customer PII vào repository hoặc CI fixture.

### 20.5. Không chỉ nhìn top một query

Query chạy 80 ms nhưng 20.000 lần/giây có thể tiêu thụ nhiều CPU hơn query 2 giây chạy một lần/giờ. Kết hợp duration, frequency, docs/keys examined và resource metrics.

---

## 21. Lab 1: index thiếu và sort

**Chỉ chạy trên MongoDB lab cô lập**. Database `slow_query_lab` và collection `orders` dưới đây phải trống trước khi seed; không chạy `dropDatabase()` trên môi trường chung.

### 21.1. Sinh dữ liệu deterministic

```javascript
const lab = db.getSiblingDB("slow_query_lab");
const orders = lab.getCollection("orders");
const base = ISODate("2026-01-01T00:00:00Z");
let batch = [];

for (let tenant = 0; tenant < 6; tenant++) {
  const tenantId =
    "t" + String(tenant).padStart(2, "0");

  for (let i = 0; i < 2000; i++) {
    batch.push({
      _id: tenantId + "-" + String(i).padStart(4, "0"),
      tenantId,
      status: i % 4 === 0 ? "PAID" : "PENDING",
      total: i + 100,
      createdAt: new Date(base.getTime() + i * 60000),
      customerId: "C-" + (i % 100)
    });

    if (batch.length === 500) {
      orders.insertMany(batch);
      batch = [];
    }
  }
}

if (batch.length) {
  orders.insertMany(batch);
}

print("total=" + orders.countDocuments({}));
print("t05Paid=" + orders.countDocuments({
  tenantId: "t05", status: "PAID"
}));
```

Expected:

```text
total=12000
t05Paid=500
```

### 21.2. Explain trước index

```javascript
const filter = { tenantId: "t05", status: "PAID" };

const before = orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");

printjson({
  returned: before.executionStats.nReturned,
  docsExamined: before.executionStats.totalDocsExamined,
  keysExamined: before.executionStats.totalKeysExamined,
  winning: before.queryPlanner.winningPlan
});
```

Khi chưa có index ngoài `_id`, nhiều khả năng sẽ thấy COLLSCAN và sort; inspect actual output thay vì hardcode exact stages.

### 21.3. Tạo compound index

```javascript
orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);
```

### 21.4. Explain sau index

```javascript
const after = orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");

printjson({
  returned: after.executionStats.nReturned,
  docsExamined: after.executionStats.totalDocsExamined,
  keysExamined: after.executionStats.totalKeysExamined,
  winning: after.queryPlanner.winningPlan
});
```

### 21.5. Kiểm tra correctness

```javascript
const results = orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(20).toArray();

print(results.length);
print(results[0]._id);
```

Kỳ vọng 20 results; record đầu thường là `t05-1996` với fixture đã seed và sort theo createdAt.

### 21.6. Negative control bằng natural scan

```javascript
const natural = orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(20)
  .hint({ $natural: 1 })
  .explain("executionStats");

printjson({
  docs: natural.executionStats.totalDocsExamined,
  keys: natural.executionStats.totalKeysExamined
});
```

Đây là diagnostic lab. Không dùng natural hint để sửa query production.

---

## 22. Lab 2: collation mismatch

### 22.1. Tạo collection

```javascript
const lab = db.getSiblingDB("slow_query_lab");
const customers = lab.getCollection("customers");

customers.insertMany([
  { _id: 1, displayName: "Alice" },
  { _id: 2, displayName: "alice" },
  { _id: 3, displayName: "ALICE" },
  { _id: 4, displayName: "Bob" }
]);
```

### 22.2. Tạo ICU index

```javascript
customers.createIndex(
  { displayName: 1 },
  {
    name: "idx_name_ci",
    collation: { locale: "en", strength: 2 }
  }
);
```

### 22.3. Không collation

```javascript
printjson(customers.find({
  displayName: "alice"
}).toArray());

printjson(customers.find({
  displayName: "alice"
}).explain("executionStats"));
```

### 22.4. Matching collation

```javascript
printjson(customers.find({
  displayName: "alice"
}).collation({
  locale: "en", strength: 2
}).toArray());

printjson(customers.find({
  displayName: "alice"
}).collation({
  locale: "en", strength: 2
}).explain("executionStats"));
```

### 22.5. Diễn giải

- Query results khác vì comparison semantics.
- Matching collation giúp ICU index đủ điều kiện cho string comparison.
- Collection chỉ bốn documents: optimizer vẫn có thể chọn COLLSCAN; không kết luận index sai từ một fixture nhỏ.
- Seed nhiều docs giả lập nếu cần kiểm chứng plan choice.
- Thử strength 1 và 2 với accented values, đánh giá correctness trước khi chọn.

---

## 23. Lab 3: BSON type mismatch

### 23.1. Tạo mixed data

```javascript
const lab = db.getSiblingDB("slow_query_lab");
const mixed = lab.getCollection("mixed_types");

mixed.insertMany([
  {
    _id: ObjectId("65b8f9a53a9b43885f4e52c1"),
    createdAt: ISODate("2026-11-01T00:00:00Z"),
    price: NumberDecimal("150.00")
  },
  {
    _id: "65b8f9a53a9b43885f4e52c2",
    createdAt: "2026-11-02T00:00:00Z",
    price: "150"
  },
  {
    _id: "numeric-01",
    createdAt: ISODate("2026-11-03T00:00:00Z"),
    price: NumberInt(200)
  }
]);
```

### 23.2. Phân loại types

```javascript
mixed.aggregate([
  {
    $project: {
      idType: { $type: "$_id" },
      dateType: { $type: "$createdAt" },
      priceType: { $type: "$price" }
    }
  }
]);
```

### 23.3. So String và ObjectId

```javascript
printjson(mixed.findOne({
  _id: "65b8f9a53a9b43885f4e52c1"
}));

printjson(mixed.findOne({
  _id: ObjectId("65b8f9a53a9b43885f4e52c1")
}));
```

### 23.4. Date range

```javascript
mixed.find({
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z")
  }
}).toArray();
```

### 23.5. Numeric range

```javascript
mixed.find({
  price: { $gte: 100 }
}).toArray();
```

Quan sát sự khác biệt giữa numeric BSON values và String price; giải thích vì sao không thể sửa chỉ bằng index.

---

## 24. Migration từ mixed types sang schema nhất quán

### 24.1. Đừng chạy conversion đại trà ngay

Một update pipeline chuyển mọi field sang Date có thể lỗi với malformed strings, gây ghi khối lượng lớn hoặc ảnh hưởng replication.

### 24.2. Audit trước khi migrate

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: { $type: "$createdAt" },
      count: { $sum: 1 }
    }
  }
]);
```

### 24.3. Kiểm tra khả năng convert

```javascript
db.orders.aggregate([
  {
    $project: {
      oldType: { $type: "$createdAt" },
      parsedDate: {
        $convert: {
          input: "$createdAt",
          to: "date",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Không tự ghi `null` vào production field khi conversion fail.

### 24.4. Migration an toàn

1. Xác định source formats và timezone.
2. Backup/snapshot theo policy.
3. Chạy trên staging với representative data.
4. Chỉ chọn records có type sai.
5. Parse/validate; record conversion failures.
6. Write theo batches và checkpoints idempotent.
7. Theo dõi CPU, disk, oplog window, replication lag.
8. Kiểm tra counts và random samples.
9. Chuyển ứng dụng sang typed filters.
10. Thêm schema validation để tránh tái diễn.

### 24.5. MongoDB JSON Schema

Ví dụ kiểm tra BSON Date:

```javascript
db.runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      properties: {
        createdAt: { bsonType: "date" }
      }
    }
  }
});
```

Đây là **khung lab**. Trên production, phải merge với validator hiện có, quyết định required fields/validationLevel và tương thích writers. Validation không tự sửa documents cũ.

### 24.6. Chưa sửa data thì index chưa giải quyết gốc

Nếu query type luôn Date nhưng 10% documents String, index Date không làm kết quả đúng đầy đủ. Cần schema migration và sửa writer sources.

---

## 25. Aggregation và computed sort

### 25.1. $match sớm

```javascript
db.orders.aggregate([
  { $match: { tenantId: "t05", status: "PAID" } },
  { $sort: { createdAt: -1 } },
  { $limit: 20 },
  { $project: { customerId: 1, total: 1, createdAt: 1 } }
]);
```

Giữ semantics cho phép optimizer tận dụng collection indexes khi thích hợp.

### 25.2. $project có thể làm mất index access path

Nếu projection xóa field trước sort hoặc tạo computed field mới, sorter có thể không tận dụng cùng index order. Kiểm tra optimized pipeline thay vì chỉ nhìn original stage order.

### 25.3. $group tạo field mới

```javascript
db.orders.aggregate([
  { $group: { _id: "$tenantId", revenue: { $sum: "$total" } } },
  { $sort: { revenue: -1 } }
]);
```

Index trên raw `total` không tự cung cấp thứ tự cho computed `revenue`. Có thể cần materialized summary collection, caching hoặc batch report.

### 25.4. $lookup

Foreign collection thiếu index trên join key có thể làm aggregation chậm dù base collection index tốt. Xem explain $lookup, `indexesUsed`, docs examined và fan-out nếu server version hỗ trợ.

### 25.5. Aggregation explain output khác find

Các counters có thể ở nested stages hoặc sharded sections. Không giả định mọi pipeline có `executionStats.totalDocsExamined` cùng path như find.

---

## 26. Diagnostic hint: so sánh access paths

### 26.1. Dùng trong môi trường an toàn

```javascript
const filter = {
  tenantId: "t05",
  status: "PAID"
};

const noHint = db.orders.find(filter)
  .sort({ createdAt: -1 }).limit(20)
  .explain("executionStats");

const withHint = db.orders.find(filter)
  .sort({ createdAt: -1 }).limit(20)
  .hint("idx_tenant_status_created")
  .explain("executionStats");

printjson({
  plannerDocs: noHint.executionStats.totalDocsExamined,
  hintedDocs: withHint.executionStats.totalDocsExamined
});
```

### 26.2. Không dùng hint để che sai plan

Hint có thể giúp chứng minh index candidate hữu ích, nhưng hardcode vào production có thể:

- Bị lỗi khi index bị xóa.
- Bỏ lỡ index tốt hơn sau upgrade.
- Bị sai khi data distribution đổi.
- Tạo regression cho các query variants khác.

### 26.3. So cả correctness

Một partial index và query conditions không phù hợp có thể dẫn tới lỗi hoặc result semantics khác. Không chỉ so examined counters.

---

## 27. Trên replica set và sharded cluster

### 27.1. Replica set

Query có thể chạy trên primary hoặc secondary. Các members khác nhau về cache, load, replication lag và read preference. Kiểm tra nơi request thực đi tới.

### 27.2. Mongos fan-out

```text
Java app
   │
   ▼
mongos
   ├─ shard A: IXSCAN
   ├─ shard B: IXSCAN
   └─ shard C: IXSCAN
        │
        ▼
   merge/sort
```

Query thiếu shard-key predicate có thể scatter-gather, kể cả khi từng shard dùng index tốt.

### 27.3. Per-shard explain

Quan sát per-shard docs/keys examined và routing. Không cộng duration của các shards chạy song song thành một con số HTTP latency.

### 27.4. Collation và sharding

Sharded indexes, unique indexes và collation có restrictions phụ thuộc server version/topology. Không thay collection default collation hay shard key tùy tiện để chữa một slow query.

### 27.5. Index rollout ở nhiều members

Index build có chi phí CPU, disk, cache, replication và workload concurrency. Cần change window/monitoring/rollback rõ.

---

## 28. Runbook sự cố chậm ở production

### Bước 1 — Xác định mức độ ảnh hưởng

Ghi affected APIs, bắt đầu lúc nào, p95/p99/error rate, cluster/replica/shard, deploy/index/schema changes gần đây.

### Bước 2 — Ghi query thực

Thu filter, projection, sort, collation, limit/skip, hint, BSON operand types, driver/server versions; sanitize PII.

### Bước 3 — Kiểm tra correctness

Có documents đáng lẽ phải match nhưng không được trả không? Các fields có mixed types không? Collation có đổi semantics không?

### Bước 4 — Kiểm tra catalog

```javascript
db.orders.getIndexes();
```

So key order, hidden/partial/sparse, collation, unique và migration state.

### Bước 5 — Explain có kiểm soát

```javascript
db.orders.find(filter)
  .sort(sort)
  .limit(20)
  .explain("executionStats");
```

Không chạy explain trên unbounded query rất nặng trong giờ peak thiếu đánh giá tác động.

### Bước 6 — Phân loại root cause

- Missing/wrong index.
- Index bounds rộng.
- Blocking sort/spill.
- Collation mismatch.
- BSON type inconsistency.
- Deep pagination/regex/expression.
- Query plan cache/topology.
- Non-query bottleneck.

### Bước 7 — Thử fix nhỏ nhất trên lab/staging

Đo result correctness, docs/keys examined và index catalog trước/sau. Benchmark representative workload riêng để xác nhận latency.

### Bước 8 — Production rollout

Có owner, approval, resource budget, rollback. Index build/schema backfill có thể ảnh hưởng writes, disk và replica lag. Không xóa index đang phục vụ query khác ngay.

### Bước 9 — Xác minh

So latency distribution, throughput, query work, errors, CPU, I/O, cache và replication. Test case/accent/timezone/type correctness.

### Bước 10 — Postmortem

Ghi root cause cụ thể và biện pháp chống tái diễn: migration, schema validation, index tests, query reviews hoặc observability.

---

## 29. Bảng xử lý nhanh

| Triệu chứng | Kiểm tra đầu tiên | Giải pháp khả thi |
|---|---|---|
| `COLLSCAN` và docsExamined cao | Index existence/shape | Compound index phù hợp |
| `IXSCAN` nhưng keysExamined cao | Bounds/prefix/selectivity | Sửa index key order/query |
| Blocking `SORT` | Equality prefix/direction | Index filter+sort, limit |
| `usedDisk` | Pipeline cardinality/memory | Index, $match, top-N, batch |
| Sort deep skip chậm | skip depth | Keyset pagination |
| Case-insensitive index không dùng | Query/index collation | Align collation |
| `$regex /i` chậm | Regex semantics | Normalized key/search solution |
| String date không match Date filter | `$type` | Data migration + validation |
| String ID không match ObjectId | BSON type | Parse ObjectId ở boundary |
| Price String sort sai | `$type` | Numeric BSON representation |
| Partial index không dùng | Predicate filter | Match partial conditions |
| Hidden index | Catalog hidden flag | Review state/rollout |
| Aggregation computed sort | $group/$project stages | Materialize/report design |
| Explain khác production logs | Cache/version/data/node | Correlate telemetry |
| Index mới làm ghi chậm | Index overhead | Rà soát index portfolio |

---

## 30. Bài tập A — Missing compound index

Có một triệu orders, chỉ có indexes `{status:1}` và `{createdAt:-1}`. Query lọc tenant/status, sort createdAt giảm, limit 20.

Yêu cầu:

1. Giải thích vì sao hai single-field indexes chưa đủ tốt.
2. Đề xuất compound index.
3. Viết explain.
4. Đặt docs/keys budgets cho fixture phù hợp.
5. Phân tích write/storage cost của index mới.

## 31. Bài tập B — IXSCAN vẫn chậm

Explain:

```text
nReturned=10
keysExamined=650000
docsExamined=300000
winning plan contains IXSCAN
```

Giải thích vì sao “có index” không có nghĩa “query tối ưu”, phân tích indexBounds và đề xuất cải thiện.

## 32. Bài tập C — Sort direction

Index:

```javascript
{ score: -1, createdAt: 1 }
```

So sánh sort:

```javascript
{ score: -1, createdAt: 1 }
{ score: 1, createdAt: -1 }
{ score: -1, createdAt: -1 }
```

Pattern nào có thể được hỗ trợ bằng forward/reverse scan? Pattern nào có thể cần sort bổ sung?

## 33. Bài tập D — Equality prefix

Index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

So sánh query:

```javascript
{ tenantId: "t05", status: "PAID" }
{ tenantId: "t05" }
{ status: "PAID" }
```

trong bối cảnh sort createdAt. Giải thích tại sao equality prefix ảnh hưởng sort/index access.

## 34. Bài tập E — Collation

Index:

```javascript
{ username: 1 }
// collation: { locale: "en", strength: 2 }
```

Hãy so query simple và query collation strength 2, kết quả case-insensitive, rủi ro unique index và lý do regex /i không giải quyết vấn đề tự động.

## 35. Bài tập F — Date vs String

Data:

```javascript
{ createdAt: ISODate("2026-11-01T00:00:00Z") }
{ createdAt: "2026-11-01T00:00:00Z" }
```

Viết query Date range, dự đoán kết quả, dùng $type, đề xuất migration và validation.

## 36. Bài tập G — ObjectId và Java Driver

Java:

```java
collection.find(Filters.eq(
  "_id", "65b8f9a53a9b43885f4e52c1")).first();
```

Collection lưu ObjectId. Giải thích mismatch, sửa type ở boundary, xử lý invalid IDs và tránh $expr/$toString scan.

## 37. Bài tập H — Numeric fields

Data:

```javascript
{ price: NumberInt(150) }
{ price: NumberDecimal("150.00") }
{ price: "150" }
```

Query `price:{$gte:100}` match nhóm nào? Vì sao numericOrdering không thay schema numeric?

## 38. Bài tập I — Sort spill

Pipeline:

```javascript
[
  { $match: { status: "PAID" } },
  { $sort: { createdAt: -1 } }
]
```

Logs có `usedDisk:true`. Đề xuất cách kiểm tra index, selective filter, limit và memory configuration. Giải thích vì sao bật allowDiskUse chưa phải giải pháp tối ưu.

## 39. Bài tập J — Incident runbook

API p99 tăng sau migration CSV; 15% createdAt chuyển thành String, query bắt đầu dùng `$expr/$toDate`. Viết:

1. Cách xác minh root cause.
2. Biện pháp giảm tải ngắn hạn.
3. Migration idempotent có rollback.
4. Schema validation.
5. Before/after explain.
6. Benchmark và regression tests.

## 40. Bài tập K — Sharding

Mongos scatter-gather 5 shards; mỗi shard có IXSCAN nhưng router merge/sort chậm. Nêu cách điều tra shard targeting, per-shard indexes, query collation và routing. Vì sao không cộng shard durations thành HTTP latency?

## 41. Bài tập L — Search tiếng Việt

Tìm tên “Nguyễn”, “NGUYỄN”, “nguyen”:

1. Quy định case/accent semantics.
2. Thiết kế index/collation hoặc normalized key.
3. Test Unicode correctness.
4. Kiểm tra regex prefix/search performance.
5. Đảm bảo không làm thay đổi unique username behavior ngoài ý muốn.

---

## 42. Checklist trước khi kết thúc incident

### 42.1. Chứng cứ

- [ ] Có query shape thật, gồm collation/operands types.
- [ ] Có index catalog.
- [ ] Có result correctness.
- [ ] Có explain before/after.
- [ ] Có docsExamined/keysExamined/nReturned.
- [ ] Có metrics latency/throughput/resource.
- [ ] Có topology/versions và query member context.

### 42.2. Correctness

- [ ] ObjectId/String ID tương thích schema.
- [ ] BSON Date và timezone policy đúng.
- [ ] Numeric types thống nhất.
- [ ] Collation case/accent đúng.
- [ ] Unique constraints không đổi ngoài ý muốn.
- [ ] Sort/pagination có stable ordering.
- [ ] Legacy data được xử lý.

### 42.3. Hiệu năng

- [ ] Index phù hợp equality/sort/range.
- [ ] Index bounds đủ hẹp.
- [ ] Blocking sort/spill được giải quyết hoặc chấp nhận có căn cứ.
- [ ] Deep skip/regex/expressions được xem xét.
- [ ] Docs/keys scan budget phù hợp.
- [ ] p95/p99 cải thiện qua nhiều mẫu.
- [ ] Index mới không làm write workload vượt budget.

### 42.4. Vận hành

- [ ] Có owner và rollback.
- [ ] Không drop index trên shared database để thử.
- [ ] Migration có backup/checkpoint/validation.
- [ ] Không log raw PII/secrets.
- [ ] Có integration tests về type/collation/index.
- [ ] Monitoring tiếp tục sau rollout.
- [ ] Postmortem ghi nguyên nhân cụ thể.

---

## 43. Tài liệu tham khảo chính thức

- [MongoDB — Interpret Explain Plan Results](https://www.mongodb.com/docs/manual/tutorial/analyze-query-plan/)
- [MongoDB — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB — Query Plans and Plan Cache](https://www.mongodb.com/docs/manual/core/query-plans/)
- [MongoDB — Use Indexes to Sort Query Results](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/)
- [MongoDB — ESR Equality, Sort, Range](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/)
- [MongoDB — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB — Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/)
- [MongoDB — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [MongoDB — Collation](https://www.mongodb.com/docs/manual/reference/collation/)
- [MongoDB — Case-Insensitive Indexes](https://www.mongodb.com/docs/manual/core/index-case-insensitive/)
- [MongoDB — BSON Comparison/Sort Order](https://www.mongodb.com/docs/manual/reference/bson-type-comparison-order/)
- [MongoDB — Type Bracketing in Query Predicates](https://www.mongodb.com/docs/manual/reference/mql/query-predicates/type-bracketing/)
- [MongoDB — $type Aggregation](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/)
- [MongoDB — $convert](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/)
- [MongoDB — $toDate](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toDate/)
- [MongoDB — Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)
- [MongoDB — $sort](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sort/)
- [MongoDB — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Java Sync Driver — Query Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)
- [MongoDB Java Sync Driver — Collation](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/limit-sort/)
- [MongoDB Java Sync Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/monitoring-and-logging/)

> **Lưu ý phiên bản:** MongoDB Classic/SBE/EXPRESS query plans, sort spill limits, collation behaviors, index visibility và aggregation explain có thể khác giữa server releases. Hãy đối chiếu với đúng MongoDB Server, Java Driver và topology đang sử dụng. Các lệnh tạo dữ liệu/index/validator chỉ dành cho lab hoặc deployment có change approval.

---

## 44. Tổng kết

1. **Thiếu/sai index** thường làm MongoDB xét rất nhiều documents hoặc index entries. Kiểm tra index catalog, key order, prefixes, selectivity và `explain("executionStats")`.
2. **Sort chậm** có thể do index không cung cấp đúng thứ tự, hướng sort không phù hợp, thiếu equality prefixes, pagination sâu hoặc sort trên computed field. `allowDiskUse` không phải index optimization.
3. **Collation mismatch** khiến index ICU không hỗ trợ string comparison của query dùng collation khác. Case-insensitive `$regex` không tự hưởng lợi từ case-insensitive collation index.
4. **BSON types** là một phần của query correctness: ObjectId khác String, Date khác String, numeric BSON khác numeric string. Range predicates có type bracketing, trong khi các BSON numeric types được so sánh như một nhóm.
5. **Explain không phải production latency benchmark**. Dùng docs/keys examined, index/plan metadata và correctness để chẩn đoán logical work; dùng APM/benchmark để kiểm tra SLO.
6. **Schema migration và validation** thường là giải pháp bền vững cho sai kiểu dữ liệu, thay vì query-time casts khiến index kém hữu ích.
7. **Rollout an toàn** cần lab, before/after evidence, index build resource budget, regression tests, monitoring và rollback.

**Nguyên tắc vận hành:** Hãy điều tra theo chuỗi **query shape → BSON type và collation → index catalog → explain work → xác minh giả thuyết → thử nghiệm → rollout và đo lại**. Xác định đúng nguyên nhân giúp cải thiện hiệu năng mà không đánh đổi tính đúng của dữ liệu.
