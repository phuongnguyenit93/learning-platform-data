# Tối ưu aggregation, join và dữ liệu tổng hợp tính sẵn trong MongoDB

## Mục tiêu bài học

Khi hệ thống MongoDB lớn lên, một truy vấn chạy tốt trên vài nghìn document có thể trở thành điểm nghẽn khi dữ liệu đạt hàng triệu bản ghi, tỷ lệ đọc/ghi tăng, số tenant nhiều hơn và dashboard cần trả kết quả gần như tức thời. Đặc biệt, ba nhóm công việc thường tiêu tốn tài nguyên:

1. **Aggregation pipeline:** lọc, sắp xếp, nhóm, tính toán, biến đổi dữ liệu qua nhiều stage.
2. **Join bằng `$lookup`:** ghép dữ liệu từ nhiều collection, có thể làm tăng số bản ghi trung gian và phát sinh nhiều lần truy cập index/collection.
3. **Dữ liệu tổng hợp tính sẵn (precomputed aggregates/materialized views):** duy trì kết quả tính toán từ trước để đổi công việc CPU/I/O tại lúc đọc thành công việc tính trước hoặc khi dữ liệu thay đổi.

Tối ưu đúng không có nghĩa đơn giản là “cứ đặt `$match` đầu tiên”, “thêm thật nhiều index” hoặc “cache hết các kết quả”. MongoDB query optimizer có những phép biến đổi riêng; một phép join có thể thay đổi ý nghĩa khi di chuyển `$limit`; còn bảng tổng hợp có thể nhanh nhưng sai nếu bỏ sót update, delete, late events hoặc thay đổi trạng thái đơn hàng.

Bài thuộc **Database Engine Document MongoDB → Tối ưu hiệu năng → Tối ưu aggregation, join và dữ liệu tổng hợp tính sẵn**.

Sau bài, người học có thể:

- Đọc cấu trúc và chi phí của một aggregation pipeline.
- Tối ưu `$match`, `$sort`, `$limit`, `$project`, `$group`, `$unwind`, `$facet` và `$setWindowFields` theo query semantics.
- Giải thích khi nào một index hỗ trợ filter + sort và khi nào stage phải sort/group trong memory hoặc spill ra disk.
- Dùng `explain("executionStats")`, `totalKeysExamined`, `totalDocsExamined`, `nReturned` và timing để đo thay vì suy đoán.
- Thiết kế `$lookup` equality/correlated pipeline, thêm index ở foreign collection, hạn chế fan-out và tránh mô hình N+1.
- Cân nhắc embedding, denormalization, application-side query và `$lookup` theo kích thước/độ biến động dữ liệu.
- Xây collection tổng hợp theo ngày/tenant bằng `$group` + `$merge`, có unique keys và timezone rõ ràng.
- So sánh full refresh, scheduled refresh và incremental refresh từ Change Streams/outbox.
- Xử lý dữ liệu mới, update, delete, late-arriving events, duplicate processing, concurrency và reprocessing.
- Phân biệt eventual consistency với data correctness và xác định độ mới của báo cáo bằng `computedAt`/watermark.
- Đo hiệu năng trên dữ liệu giống production và xây chính sách observability/rollout/rollback.
- Viết truy vấn minh họa bằng mongosh và Java Sync Driver.

> **Nguyên tắc:** Mọi tối ưu đều phải giữ **đúng tập kết quả, đúng thứ tự, đúng phạm vi dữ liệu và đúng thời gian** mà nghiệp vụ yêu cầu. Một pipeline nhanh nhưng bỏ sót giao dịch hoặc lộ dữ liệu tenant khác là một pipeline sai.

---

## 1. Bức tranh tổng thể: tính toán lúc đọc hay trước lúc đọc?

Giả sử trang quản trị hiển thị doanh thu theo ngày cho mỗi tenant.

Một truy vấn trực tiếp:

~~~text
GET /dashboard/revenue?from=...&to=...
      |
      v
db.orders.aggregate(
  $match -> $group -> $sort -> ...
)
      |
      v
Hàng triệu orders được quét/nhóm để trả vài chục hàng
~~~

Phương án tính sẵn:

~~~text
Order created/paid/cancelled
          |
          v
Aggregation worker / Change Stream / scheduled job
          |
          v
dailyOrderSales
          |
          v
GET /dashboard/revenue
          |
          v
Find 30 documents đã tổng hợp
~~~

Phương án thứ hai có thể giảm latency đọc mạnh, nhưng đổi lại phải chịu:

- Logic refresh phức tạp hơn.
- Độ trễ giữa source và bảng tổng hợp.
- Khả năng stale hoặc missing aggregates.
- Nhu cầu backfill, replay và reconciliation.
- Chi phí ghi thêm, storage và index.
- Thay đổi nghiệp vụ cần migrate/recompute kết quả.

Câu hỏi thiết kế phải là: **phép tính nào thực hiện vào lúc đọc, phép tính nào được duy trì trước, và độ tươi dữ liệu nào được chấp nhận?**

### 1.1. Ba tầng hiệu năng

| Tầng | Câu hỏi | Công cụ |
|---|---|---|
| **Query shape** | Có đang lọc, sort, join sai thứ tự? | Pipeline rewrites, projection, limit |
| **Physical access** | Dùng index hay scan? Có join fan-out? | Compound index, explain, schema |
| **Architecture** | Có đang tính lại cùng kết quả quá nhiều lần? | Materialized view, CDC, cache, pre-aggregation |

Không nên nhảy ngay sang materialized view khi chỉ thiếu một index quan trọng; ngược lại, một aggregation được index tốt vẫn có thể tốn chi phí lớn nếu báo cáo phải nhóm hàng chục triệu orders trên mỗi request.

---

## 2. Bộ dữ liệu minh họa

Ta dùng database `aggregation_perf_lab` với ba collection chính:

- `orders`: source of truth cho đơn hàng.
- `customers`: thông tin khách được tham chiếu qua `customerId`.
- `dailyOrderSales`: kết quả doanh thu được tính sẵn.

Các mốc thời gian, tiền và IDs chỉ phục vụ ví dụ.

### 2.1. Orders

~~~javascript
use aggregation_perf_lab

db.orders.insertMany([
  {
    _id: "ORD-101",
    tenantId: "tenant-a",
    customerId: "CUS-101",
    status: "PAID",
    createdAt: ISODate("2026-11-10T01:00:00Z"),
    paidAt: ISODate("2026-11-10T01:05:00Z"),
    currency: "VND",
    totalVnd: NumberLong("500000"),
    items: [
      { sku: "SKU-1", qty: 2, unitPriceVnd: NumberLong("150000") },
      { sku: "SKU-2", qty: 1, unitPriceVnd: NumberLong("200000") }
    ],
    updatedAt: ISODate("2026-11-10T01:05:00Z")
  },
  {
    _id: "ORD-102",
    tenantId: "tenant-a",
    customerId: "CUS-102",
    status: "PAID",
    createdAt: ISODate("2026-11-10T03:00:00Z"),
    paidAt: ISODate("2026-11-10T03:02:00Z"),
    currency: "VND",
    totalVnd: NumberLong("850000"),
    items: [
      { sku: "SKU-3", qty: 1, unitPriceVnd: NumberLong("850000") }
    ],
    updatedAt: ISODate("2026-11-10T03:02:00Z")
  },
  {
    _id: "ORD-103",
    tenantId: "tenant-a",
    customerId: "CUS-101",
    status: "PENDING",
    createdAt: ISODate("2026-11-11T05:00:00Z"),
    paidAt: null,
    currency: "VND",
    totalVnd: NumberLong("400000"),
    items: [
      { sku: "SKU-1", qty: 1, unitPriceVnd: NumberLong("400000") }
    ],
    updatedAt: ISODate("2026-11-11T05:00:00Z")
  },
  {
    _id: "ORD-104",
    tenantId: "tenant-b",
    customerId: "CUS-201",
    status: "PAID",
    createdAt: ISODate("2026-11-10T04:00:00Z"),
    paidAt: ISODate("2026-11-10T04:05:00Z"),
    currency: "VND",
    totalVnd: NumberLong("900000"),
    items: [
      { sku: "SKU-8", qty: 1, unitPriceVnd: NumberLong("900000") }
    ],
    updatedAt: ISODate("2026-11-10T04:05:00Z")
  }
]);

db.customers.insertMany([
  {
    _id: "CUS-101",
    tenantId: "tenant-a",
    displayName: "Khách A",
    segment: "LOYAL",
    active: true
  },
  {
    _id: "CUS-102",
    tenantId: "tenant-a",
    displayName: "Khách B",
    segment: "NEW",
    active: true
  },
  {
    _id: "CUS-201",
    tenantId: "tenant-b",
    displayName: "Khách C",
    segment: "LOYAL",
    active: true
  }
]);
~~~

Với ứng dụng thật, cần bảo đảm `totalVnd` là số tiền được tính/kiểm chứng theo nghiệp vụ. Dùng `NumberLong` cho tiền nguyên VND hoặc `Decimal128` cho tiền có phần thập phân; không mặc định JavaScript `double` phù hợp mọi tính toán tài chính.

### 2.2. Index ứng viên

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    paidAt: -1,
    _id: -1
  },
  {
    name: "idx_orders_tenant_status_paidAt_id"
  }
);

db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1
  },
  {
    name: "idx_orders_tenant_customer"
  }
);

db.customers.createIndex(
  {
    tenantId: 1,
    segment: 1
  },
  {
    name: "idx_customers_tenant_segment"
  }
);
~~~

Các indexes chỉ là **ứng viên**. `customers._id` đã có unique index mặc định. Trên dataset nhỏ, optimizer có thể chọn collection scan; điều này không chứng minh index sai. Cần đo với workload và kích thước dữ liệu tương tự production.

---

## 3. Bản chất chi phí của aggregation pipeline

Một pipeline:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-a" } },
  { $sort: { paidAt: -1 } },
  { $group: { _id: "$status", count: { $sum: 1 } } },
  { $sort: { count: -1 } }
]);
~~~

có các loại chi phí khác nhau:

- **I/O:** đọc documents/index keys từ storage/cache.
- **CPU:** so sánh điều kiện, parse expressions, group keys, join predicates.
- **Memory:** sort, group hash tables, window states, arrays trung gian.
- **Disk spill:** stages blocking vượt ngưỡng bộ nhớ được phép.
- **Network:** chuyển dữ liệu giữa shards/routers hoặc trả kết quả quá lớn.
- **Write overhead:** khi materialize dữ liệu ra collection bằng `$merge` hoặc `$out`.

### 3.1. Streaming và blocking stages

| Stage | Xu hướng xử lý | Điểm cần nhớ |
|---|---|---|
| `$match` | Có thể lọc theo stream/index | Cần đẩy predicate phù hợp gần source |
| `$project` / `$set` | Biến đổi từng document | Giảm payload khi cần, không tự bảo đảm dùng index |
| `$unwind` | Có thể làm tăng số hàng | Cardinality explosion |
| `$sort` | Có thể blocking nếu không được index hỗ trợ | Memory/spill/top-k |
| `$group` | Thường phải tích lũy state | Group cardinality, memory |
| `$lookup` | Phụ thuộc chiến lược join và indexes | Foreign scans, fan-out |
| `$facet` | Chia một input thành nhiều nhánh | Giới hạn memory và output |
| `$setWindowFields` | Window calculations | Partition/sort/memory |
| `$merge` | Ghi dữ liệu ra collection | Extra writes và consistency |

### 3.2. Pipeline order là logic, plan là thực thi

MongoDB query optimizer có thể di chuyển `$match`, tối ưu `$sort` + `$limit` hoặc thực hiện projection optimization tùy query shape/version. Vì vậy source code có 8 stages không có nghĩa engine sẽ thực thi y hệt theo một vòng lặp đơn giản.

Cần xem `explain()` để biết execution plan thực tế.

### 3.3. Tối ưu phải giữ ngữ nghĩa

Giả sử yêu cầu “20 đơn có khách VIP gần đây nhất”. Nếu `$limit:20` trước khi lọc khách VIP từ `$lookup`, có thể chỉ còn vài đơn VIP dù còn nhiều đơn hợp lệ ở các vị trí sau. Đổi thứ tự stage là **thay đổi kết quả**, không chỉ thay đổi hiệu năng.

---

## 4. `$match`: lọc sớm và đúng chỉ mục

### 4.1. Truy vấn phạm vi thời gian có điều kiện rõ

~~~javascript
const from = ISODate("2026-11-01T00:00:00Z");
const to = ISODate("2026-12-01T00:00:00Z");

db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID",
      paidAt: {
        $gte: from,
        $lt: to
      }
    }
  },
  {
    $group: {
      _id: null,
      totalVnd: { $sum: "$totalVnd" },
      orders: { $sum: 1 }
    }
  }
]);
~~~

So với `$match` sau `$group`, lọc source sớm có thể giảm số rows phải xử lý. Tập trung vào predicates thực sự có tính chọn lọc như tenant, status, date range.

### 4.2. Tránh biến đổi field index trong filter nếu có thể

Cách khó khai thác index thường gặp:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      $expr: {
        $eq: [
          { $year: "$paidAt" },
          2026
        ]
      }
    }
  }
]);
~~~

Nếu đã biết phạm vi năm theo UTC, có thể diễn đạt:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      paidAt: {
        $gte: ISODate("2026-01-01T00:00:00Z"),
        $lt: ISODate("2027-01-01T00:00:00Z")
      }
    }
  }
]);
~~~

Phạm vi trực tiếp trên field thường giúp index range scan rõ hơn. Nếu nghiệp vụ theo timezone địa phương, tính ranh giới UTC đúng từ timezone thay vì dùng UTC midnight tùy tiện.

### 4.3. Không phải `$match` nào cũng đẩy lên đầu được

Nếu predicate phụ thuộc field vừa được tạo:

~~~javascript
[
  {
    $addFields: {
      netVnd: {
        $subtract: ["$grossVnd", "$refundVnd"]
      }
    }
  },
  { $match: { netVnd: { $gte: 100000 } } }
]
~~~

Engine không thể đưa predicate `netVnd` trước bước tạo field nếu chưa có cách biến đổi tương đương. Query optimizer chỉ hoán đổi các stages an toàn theo dependencies.

### 4.4. Những stage có điều kiện “đầu pipeline”

Một số stages như `$geoNear`, `$search` hoặc `$vectorSearch` có yêu cầu vị trí stage riêng. Không thể áp lời khuyên “luôn `$match` đầu tiên” một cách máy móc.

Khi query dùng các search/geo stages, dùng `query`/`filter` phù hợp theo tính năng thay vì đặt `$match` sai vị trí.

### 4.5. Phạm vi tenant luôn là điều kiện nghiệp vụ

Với ứng dụng multi-tenant:

~~~javascript
{
  tenantId: authenticatedContext.tenantId,
  status: "PAID"
}
~~~

`tenantId` phải đến từ ngữ cảnh đã xác thực, không lấy arbitrary BSON filter từ client. Một pipeline nhanh nhưng thiếu tenant filter là lỗi bảo mật.

---

## 5. Compound indexes và quy tắc ESR

**ESR** là heuristic thường dùng khi chọn thứ tự compound index:

- **Equality:** các field so sánh bằng.
- **Sort:** các field dùng sắp xếp.
- **Range:** các field lọc theo khoảng.

Ví dụ:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  paidAt: -1,
  _id: -1
});
~~~

Cho query:

~~~javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "PAID"
}).sort({
  paidAt: -1,
  _id: -1
}).limit(20);
~~~

Index có thể cung cấp dữ liệu đã sắp phù hợp trong phạm vi equality, tránh một blocking sort.

### 5.1. Range thay đổi lựa chọn index

Query:

~~~javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "PAID",
  paidAt: { $gte: ISODate("2026-11-01T00:00:00Z") }
}).sort({
  paidAt: -1,
  _id: -1
});
~~~

Các predicates và sort liên quan cùng trường `paidAt`. Hiệu quả thực tế còn tùy dữ liệu và query planner. ESR không phải công thức cứng, nhất là khi range predicate rất chọn lọc hoặc việc sort chiếm chi phí lớn.

### 5.2. Index càng dài chưa chắc càng nhanh

Thêm mọi fields vào compound index có thể:

- Tăng storage/RAM.
- Tăng chi phí insert/update/delete.
- Tăng số lượng candidate indexes cho optimizer.
- Không cải thiện query nếu fields ở vị trí không được khai thác.
- Không giải quyết được sort khi semantics không phù hợp.

Hãy đo `keysExamined`, `docsExamined`, execution time và index size.

### 5.3. Covered query không tự áp dụng cho mọi pipeline

Một query có thể được index cover khi filter, sort và projection đều tương thích với index. Nhưng sau `$group`, `$lookup`, expression hoặc khi cần fields khác, planner có thể phải đọc documents. Không coi mọi aggregation trên indexed fields là covered.

### 5.4. Collation và kiểu dữ liệu

String equality/sort có thể phụ thuộc collation của query và index. Decimal128, NumberLong, strings và date comparisons có semantics khác nhau. Cần dùng cùng schema/types trong dữ liệu và queries để đảm bảo đúng và hiệu quả.

---

## 6. `$sort`, `$limit` và top-k optimization

### 6.1. Sắp xếp theo index trước khi join

Nếu muốn 20 đơn đã thanh toán mới nhất:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID"
    }
  },
  {
    $sort: {
      paidAt: -1,
      _id: -1
    }
  },
  { $limit: 20 },
  {
    $project: {
      _id: 1,
      paidAt: 1,
      totalVnd: 1,
      customerId: 1
    }
  }
]);
~~~

Khi compound index phù hợp, engine có thể trả nhanh những documents đầu. `_id` làm tie-breaker để kết quả ổn định hơn khi `paidAt` trùng.

### 6.2. `$sort + $limit` coalescence

Khi không có stage thay đổi số document nằm giữa, MongoDB có thể tối ưu `$sort` theo cơ chế top-k giữ giới hạn kết quả cần thiết, giảm memory so với sort toàn bộ tập. Nếu `$skip` nằm giữa, optimizer có thể điều chỉnh số phần tử cần xét.

Không giả định optimization luôn chạy ở mọi pipeline/version; xác nhận bằng `explain()`.

### 6.3. Tránh `$skip` quá sâu

~~~javascript
[
  { $sort: { paidAt: -1, _id: -1 } },
  { $skip: 200000 },
  { $limit: 20 }
]
~~~

Deep pagination phải đi qua nhiều entries; latency thường tăng theo offset. Với feed/orders, keyset pagination thường phù hợp hơn.

### 6.4. Keyset pagination

Sau trang đầu, lưu cặp `paidAt`, `_id` cuối. Trang tiếp theo:

~~~javascript
const lastPaidAt =
  ISODate("2026-11-10T03:02:00Z");

const lastId = "ORD-102";

db.orders.find({
  tenantId: "tenant-a",
  status: "PAID",
  $or: [
    {
      paidAt: { $lt: lastPaidAt }
    },
    {
      paidAt: lastPaidAt,
      _id: { $lt: lastId }
    }
  ]
}).sort({
  paidAt: -1,
  _id: -1
}).limit(20);
~~~

Điều kiện này giả định `_id` có kiểu sắp xếp nhất quán và sử dụng cùng sort giữa các trang. Khi dữ liệu động thay đổi, pagination không bảo đảm snapshot bất biến trừ khi ứng dụng bổ sung consistency contract.

### 6.5. Sort có thể thay thứ tự kết quả đang mong muốn

Nếu `$sort` xảy ra trước hay sau `$group`, semantics khác nhau: sort source documents không phải sort groups. Cần biết đang xếp theo đơn, theo khách hay theo tổng doanh thu.

---

## 7. `$project` và tối ưu kích thước document

### 7.1. Trả ít field hơn

Một document order có thể chứa hàng trăm item lines, địa chỉ giao hàng và audit details, nhưng dashboard chỉ cần:

~~~javascript
{
  _id: 1,
  tenantId: 1,
  paidAt: 1,
  totalVnd: 1
}
~~~

Projection giảm payload ra client/giữa các stages khi hợp lý.

### 7.2. Không phải cứ `$project` sớm là nhanh nhất

MongoDB optimizer có thể tự nhận diện fields cần thiết và thực hiện projection optimization. Đặt một `$project` ngay đầu pipeline chỉ vì “ít field hơn” **không mặc nhiên cải thiện** plan.

Nên dùng early projection khi:

- Cần loại bỏ field rất lớn trước thao tác xử lý mà engine không tối ưu tự động như mong đợi.
- Cần tránh chuyển dữ liệu nhạy cảm ra downstream.
- Cần thu gọn cấu trúc sau `$lookup`/`$unwind`.
- `explain` hoặc benchmark chứng minh lợi ích.

### 7.3. Projection có thể ảnh hưởng index use

Nếu `$project` đổi tên hoặc tính toán một field trước `$match/$sort`, query có thể không còn dùng index trên source field theo cách ban đầu. Xác định dependencies trước khi di chuyển stages.

### 7.4. Không trả embedding/blob lớn nếu không cần

Tương tự, khi aggregation chỉ cần total/count, không trả arrays lớn hoặc GridFS metadata thừa. Payload lớn có thể khiến network trở thành bottleneck dù database scan nhanh.

---

## 8. `$group`: giảm tập dữ liệu, nhưng có chi phí memory

### 8.1. Tính doanh thu theo ngày

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID",
      paidAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$paidAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orders: { $sum: 1 },
      grossVnd: { $sum: "$totalVnd" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

`$dateTrunc` (MongoDB 5.0+) tạo bucket ngày theo timezone. Giá trị Date được lưu vẫn biểu diễn thời điểm UTC; bucket “00:00 địa phương” không nhất thiết là 00:00Z.

### 8.2. Group cardinality

Giả sử một triệu orders và 30 nhóm ngày, `$group` thường chỉ duy trì state cho khoảng 30 groups.

Nếu group theo `customerId` có 900.000 khách riêng, engine phải duy trì số nhóm rất lớn, có thể tiêu tốn đáng kể memory.

### 8.3. Accumulators

| Accumulator | Dùng cho | Chú ý |
|---|---|---|
| `$sum` | Tổng tiền/count | Numeric types, overflow |
| `$avg` | Trung bình | Kết quả và precision |
| `$min` / `$max` | Giá trị thấp/cao nhất | Delete/update khó duy trì incremental |
| `$first` / `$last` | Đầu/cuối theo thứ tự input | Sort semantics bắt buộc |
| `$push` | Gom nhiều values thành array | Có thể tạo document quá lớn |
| `$addToSet` | Tập values distinct | Memory tăng theo distinct count |
| `$topN` / `$bottomN` | Top-N trong group | Version support và bộ nhớ |
| `$count` accumulator | Đếm nhóm | Dùng đúng stage/version |

### 8.4. Rủi ro `$push` mọi phần tử

~~~javascript
{
  $group: {
    _id: "$tenantId",
    allOrders: { $push: "$$ROOT" }
  }
}
~~~

Nếu tenant có hàng triệu orders, kết quả array có thể quá lớn và document output vượt giới hạn BSON 16 MiB. Không dùng group làm cách gom toàn bộ raw data vào một document khổng lồ.

### 8.5. Nếu chỉ cần count

Nếu API chỉ cần count theo điều kiện, có thể dùng `countDocuments()` hoặc pipeline `$match + $count`. Không dùng `$group + $push + $size` vì tạo array trung gian không cần thiết.

### 8.6. `$first/$last` cần thứ tự xác định

Muốn order gần nhất mỗi customer:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a"
    }
  },
  {
    $sort: {
      customerId: 1,
      createdAt: -1,
      _id: -1
    }
  },
  {
    $group: {
      _id: "$customerId",
      newestOrder: { $first: "$$ROOT" }
    }
  }
]);
~~~

Có thể tối ưu bằng index theo tenant/customer/createdAt khi query shape phù hợp. Không dùng `$first` nếu chưa định nghĩa thứ tự mong muốn.

---

## 9. Memory limit, disk spill và `allowDiskUse`

Một số stages như `$sort` và `$group` cần giữ state. MongoDB có giới hạn bộ nhớ liên quan stage; khi vượt giới hạn, thao tác có thể spill ra disk nếu cho phép hoặc báo lỗi.

### 9.1. MongoDB 6.0 và tham số mặc định

Từ MongoDB 6.0, server parameter `allowDiskUseByDefault` ảnh hưởng việc tự động spill ra disk cho các stages cần nhiều hơn ngưỡng memory được quy định. Tùy phiên bản/cấu hình, có thể override ở query bằng `allowDiskUse`.

Ví dụ:

~~~javascript
db.orders.aggregate(
  [
    { $match: { tenantId: "tenant-a" } },
    {
      $group: {
        _id: "$customerId",
        totalVnd: { $sum: "$totalVnd" }
      }
    },
    { $sort: { totalVnd: -1 } }
  ],
  {
    allowDiskUse: true
  }
);
~~~

### 9.2. Spill không phải chiến thắng

Spill cho phép query hoàn thành thay vì lỗi memory, nhưng có thể:

- Tăng I/O disk.
- Tăng latency p95/p99.
- Gây tranh chấp tài nguyên với database workloads khác.
- Che dấu high-cardinality group hoặc sort thiếu index.

Cần đo executionStats/profiler và chỉnh query shape/schema nếu spill xảy ra quá thường xuyên.

### 9.3. Không phải stage nào cũng spill

Ví dụ `$facet` có các giới hạn output/memory riêng, và `allowDiskUse` không làm nó trở thành một pipeline vô hạn bộ nhớ. `$facet` có giới hạn document output và không thể spill theo cách một số stages khác thực hiện.

### 9.4. Không tăng memory limit tùy tiện

Mọi query chạy đồng thời đều tiêu thụ tài nguyên. Một query memory-hungry tăng 10 lần không có nghĩa cluster có tổng headroom 10 lần khi có 100 requests đồng thời.

---

## 10. `$lookup`: join equality hiệu quả

### 10.1. Từ orders sang customers

Một đơn có `customerId`, trong `customers` có `_id` tương ứng.

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID"
    }
  },
  {
    $sort: {
      paidAt: -1,
      _id: -1
    }
  },
  { $limit: 20 },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  {
    $unwind: {
      path: "$customer",
      preserveNullAndEmptyArrays: true
    }
  },
  {
    $project: {
      _id: 1,
      paidAt: 1,
      totalVnd: 1,
      "customer.displayName": 1
    }
  }
]);
~~~

Điều kiện `$limit` trước join **hợp lý trong trường hợp này** vì yêu cầu là “20 orders mới nhất, sau đó enrich tên khách”, chứ **không lọc/xếp hạng dựa trên field được join**.

### 10.2. Vì sao foreign index quan trọng?

`customers._id` có index mặc định, cho phép equality join tra document tương ứng thay vì quét toàn collection khách hàng cho mỗi nhóm orders.

Nếu foreign field không được index, số documents examined có thể tăng mạnh. MongoDB Manual khuyến nghị tạo index trên `foreignField` cho các equality `$lookup` hay dùng.

### 10.3. `$lookup` trả array

Kể cả khi một order chỉ có một khách, field `customer` từ `$lookup` vẫn là array. `$unwind` chuyển array thành các rows, có thể giữ lại order không có match với `preserveNullAndEmptyArrays:true`.

### 10.4. Null/missing và join semantics

Nếu `localField` hoặc `foreignField` thiếu/null, equality `$lookup` có semantics liên quan null. Không mặc định mọi record sẽ luôn có đúng một match. Với business keys, validate schema và index uniqueness phù hợp.

### 10.5. Tenant isolation

Nếu `customerId` chỉ unique trong tenant hoặc khi join qua một khóa business như email, phải xét cả `tenantId` ở foreign side. Không vô tình ghép dữ liệu tenant khác. Unique `_id` toàn collection có thể làm join theo _id an toàn hơn về identity, nhưng authorization/visibility vẫn phải được kiểm tra bởi ứng dụng.

---

## 11. Correlated `$lookup` bằng `pipeline` và `let`

Khi join cần nhiều điều kiện, sử dụng `let` và `$expr`:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID"
    }
  },
  {
    $lookup: {
      from: "customers",
      let: {
        orderCustomerId: "$customerId",
        orderTenantId: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$orderCustomerId"] },
                { $eq: ["$tenantId", "$$orderTenantId"] }
              ]
            }
          }
        },
        {
          $project: {
            _id: 1,
            displayName: 1,
            segment: 1
          }
        }
      ],
      as: "customer"
    }
  }
]);
~~~

### 11.1. Những gì nên đẩy xuống foreign pipeline

- Điều kiện equality/range trên foreign fields khi đúng semantics.
- `$project` chỉ lấy dữ liệu cần.
- `$limit` trong trường hợp business join chỉ cần một match và logic không bị thay.
- Sort đúng nếu chọn top-N related documents per parent.

### 11.2. `$expr` và index

Trong `$lookup` pipeline, MongoDB có thể sử dụng một số index cho comparisons như `$eq`, `$lt`, `$lte`, `$gt`, `$gte` bên trong `$expr` khi biến `let` phân giải thành giá trị phù hợp và các điều kiện index được đáp ứng.

Nhưng không phải mọi expression đều được index; tài liệu nêu giới hạn với multikey, partial/sparse indexes và các trường hợp biến rỗng/missing. Đừng khẳng định “có index là mọi correlated lookup chạy nhanh”.

### 11.3. Equality syntax thường đơn giản hơn

Nếu chỉ join một cặp fields, `localField/foreignField` có thể dễ đọc và dễ tối ưu hơn một correlated subpipeline phức tạp. Chọn pipeline khi thực sự cần predicate/shape bổ sung.

### 11.4. Join theo tenant + business key

Nếu khách được xác định bằng `externalCustomerCode` trong tenant, cân nhắc unique compound index:

~~~javascript
db.customers.createIndex(
  {
    tenantId: 1,
    externalCustomerCode: 1
  },
  {
    unique: true,
    name: "uk_customer_tenant_external_code"
  }
);
~~~

Index này bảo vệ identity theo tenant; cần thiết kế lookup query khớp với schema.

---

## 12. Fan-out: nguyên nhân làm `$lookup` tốn tài nguyên

### 12.1. Join cardinality

Giả sử có:

- 1.000 customers.
- Mỗi customer có trung bình 500 orders.
- Join từ customers sang orders.

Kết quả `$lookup` có thể chứa arrays tổng cộng 500.000 orders. Nếu tiếp tục `$unwind`, pipeline tạo tới 500.000 rows, thay vì 1.000.

### 12.2. Không tự load tất cả quan hệ vào một document

Ví dụ nguy hiểm:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "_id",
      foreignField: "customerId",
      as: "allOrders"
    }
  }
]);
~~~

Một khách có hàng trăm nghìn orders có thể khiến `allOrders` phình to, tăng memory và vượt BSON document size.

### 12.3. Chỉ lấy summary hoặc top-N khi đủ

Ví dụ lấy tối đa 3 đơn mới nhất của mỗi khách:

~~~javascript
db.customers.aggregate([
  {
    $match: {
      tenantId: "tenant-a"
    }
  },
  {
    $lookup: {
      from: "orders",
      let: {
        cid: "$_id",
        tid: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$customerId", "$$cid"] },
                { $eq: ["$tenantId", "$$tid"] }
              ]
            }
          }
        },
        {
          $sort: {
            createdAt: -1,
            _id: -1
          }
        },
        { $limit: 3 },
        {
          $project: {
            _id: 1,
            createdAt: 1,
            totalVnd: 1
          }
        }
      ],
      as: "recentOrders"
    }
  }
]);
~~~

Index ứng viên:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  createdAt: -1,
  _id: -1
});
~~~

Điều kiện quan trọng: `$limit:3` ở foreign pipeline đúng vì yêu cầu **top 3 đơn trên mỗi customer**; không áp dụng nếu cần đếm/tổng tất cả orders.

### 12.4. Khi nào chuyển sang aggregate summary?

Nếu dashboard chỉ cần `orderCount` và `totalSpent` cho mỗi khách, không cần tải tất cả orders vào array. Có thể group orders trước để thành một số summary records, rồi join vào customers hoặc materialize lâu dài.

---

## 13. Đếm/tổng related documents thay vì trả mảng join lớn

### 13.1. Correlated aggregate summary

~~~javascript
db.customers.aggregate([
  {
    $match: {
      tenantId: "tenant-a"
    }
  },
  {
    $lookup: {
      from: "orders",
      let: {
        cid: "$_id",
        tid: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$customerId", "$$cid"] },
                { $eq: ["$tenantId", "$$tid"] }
              ]
            },
            status: "PAID"
          }
        },
        {
          $group: {
            _id: null,
            orderCount: { $sum: 1 },
            totalSpentVnd: { $sum: "$totalVnd" }
          }
        }
      ],
      as: "purchaseSummary"
    }
  },
  {
    $project: {
      displayName: 1,
      purchaseSummary: 1
    }
  }
]);
~~~

### 13.2. Trade-off

Mỗi customer là một correlated subquery logic; dù được index, nếu phải group nhiều orders cho hàng trăm nghìn customers mỗi request thì tổng I/O vẫn cao.

Nếu endpoint thường xuyên đọc cùng summary, cân nhắc collection `customerPurchaseStats` được duy trì trước.

### 13.3. Group trước rồi join

Một cách khác:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 },
      totalSpentVnd: { $sum: "$totalVnd" }
    }
  },
  {
    $lookup: {
      from: "customers",
      localField: "_id",
      foreignField: "_id",
      as: "customer"
    }
  }
]);
~~~

Cách này tạo một summary row per customer trước khi join, thường tránh fan-out của raw orders; nhưng vẫn phải quét/nhóm toàn orders trong phạm vi lọc mỗi lần chạy. So sánh bằng benchmark.

---

## 14. `$unwind`: stage làm nhân số bản ghi

### 14.1. Ví dụ order items

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID"
    }
  },
  {
    $unwind: "$items"
  },
  {
    $group: {
      _id: "$items.sku",
      unitsSold: { $sum: "$items.qty" }
    }
  },
  {
    $sort: {
      unitsSold: -1
    }
  },
  { $limit: 10 }
]);
~~~

Một order có 20 items tạo 20 rows sau `$unwind`. Một triệu orders với trung bình 10 items tạo 10 triệu rows.

### 14.2. Khi nào không cần unwind?

Nếu chỉ cần tổng `totalVnd` của đơn, không unwind `items`. Unwind rồi group lại theo order là công việc thừa, còn có thể đếm một order nhiều lần.

### 14.3. `preserveNullAndEmptyArrays`

Nếu dùng `$unwind` với array missing/empty, mặc định document có thể không tạo output row. Khi muốn giữ parent, dùng:

~~~javascript
{
  $unwind: {
    path: "$items",
    preserveNullAndEmptyArrays: true
  }
}
~~~

Điều này thay đổi kết quả count/group; cần chọn theo nghiệp vụ, không chỉ performance.

### 14.4. `$filter` và `$map` thay thế trong một số trường hợp

Nếu chỉ cần xử lý các phần tử trong array và giữ một document gốc, `$filter`/`$map` có thể phù hợp hơn so với unwind → group lại. Nhưng chúng cũng tốn CPU/memory và chịu giới hạn kích thước BSON.

---

## 15. `$facet`: nhiều kết quả từ một tập input

Ví dụ kết quả search cần:

- 20 orders mới nhất.
- Tổng số orders theo status.
- Thống kê giá trị orders.

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a"
    }
  },
  {
    $facet: {
      page: [
        {
          $sort: {
            createdAt: -1,
            _id: -1
          }
        },
        { $limit: 20 },
        {
          $project: {
            _id: 1,
            status: 1,
            totalVnd: 1
          }
        }
      ],
      byStatus: [
        {
          $group: {
            _id: "$status",
            count: { $sum: 1 }
          }
        }
      ],
      totals: [
        {
          $group: {
            _id: null,
            count: { $sum: 1 },
            totalVnd: { $sum: "$totalVnd" }
          }
        }
      ]
    }
  }
]);
~~~

### 15.1. Lợi ích

Một tập input có thể được sử dụng cho nhiều nhánh thống kê. Hữu ích cho API trả facets + page đồng thời.

### 15.2. Giới hạn

`$facet` có giới hạn memory/output riêng; `allowDiskUse` không làm nó vô hạn bộ nhớ. Nếu đặt `$facet` làm stage đầu, nó thường không tận dụng index trên source collection theo cách một `$match`/`$sort` trước đó có thể.

### 15.3. Không mặc định một pipeline facet luôn rẻ hơn nhiều queries

Nếu nhánh page chỉ cần 20 docs nhưng nhánh totals phải đọc hàng triệu docs, `$facet` có thể làm thời gian response phụ thuộc nhánh nặng. Với UI cho phép stats trễ, tách query hoặc dùng materialized view có thể tốt hơn.

---

## 16. Window functions và giới hạn khi tối ưu

`$setWindowFields` cho phép rank, running sum, moving average theo partition/sort.

Ví dụ running revenue trong mỗi tenant:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID"
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$tenantId",
      sortBy: {
        paidAt: 1
      },
      output: {
        runningVnd: {
          $sum: "$totalVnd",
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
      paidAt: 1,
      totalVnd: 1,
      runningVnd: 1
    }
  }
]);
~~~

### 16.1. Tối ưu window

- Lọc đúng dữ liệu trước khi window.
- Chọn partition hợp lý.
- Index theo partition/sort khi query shape có thể hưởng lợi.
- Không tạo hàng triệu partitions mà không đo memory.
- Giới hạn phạm vi thời gian nếu yêu cầu business cho phép.

### 16.2. Moving window và dữ liệu đến muộn

Nếu tạo moving average 7 ngày, một giao dịch đến muộn cho ngày cũ có thể ảnh hưởng **nhiều ngày sau**, không chỉ bucket của ngày cũ. Materialized view phải recompute các windows bị ảnh hưởng, không chỉ update một row.

---

## 17. `explain()`: quan sát thay vì đoán

### 17.1. Aggregation explain

~~~javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID"
    }
  },
  {
    $sort: {
      paidAt: -1,
      _id: -1
    }
  },
  { $limit: 20 }
]);
~~~

### 17.2. Metrics cần xem

| Metric | Ý nghĩa |
|---|---|
| `winningPlan` | Đường truy cập được planner chọn |
| `IXSCAN` / `COLLSCAN` | Index scan/collection scan trong plan khi xuất hiện |
| `totalKeysExamined` | Số index entries được xét |
| `totalDocsExamined` | Số documents được kiểm tra |
| `nReturned` | Số rows trả |
| `executionTimeMillis` | Chi phí thực thi theo môi trường |
| Sort stage/spill | Có sort blocking và disk spill không |
| Join stages/index use | Foreign side có dùng index không |
| `usedDisk`/spills | Dấu hiệu aggregation dùng disk khi được báo cáo |

Tên stages/vị trí fields trong `explain` có thể đổi theo MongoDB version và query execution engine. Không viết test phụ thuộc cứng vào một stage name mà không xét version.

### 17.3. Với `$lookup`

Kiểm tra:

- Bao nhiêu documents đầu vào join?
- Có index foreign field không?
- Number of foreign docs examined.
- Có repeated foreign scans không?
- Fan-out từ parent sang related records.
- Có sort/limit được push down vào foreign subpipeline hay không?

Các thống kê `$lookup` cụ thể phụ thuộc server version/explain representation.

### 17.4. Query engine và `EQ_LOOKUP`

Một số MongoDB versions/query shapes có thể dùng slot-based execution engine cho equality `$lookup`; explain có thể thể hiện `EQ_LOOKUP`. Không xem xuất hiện/không xuất hiện `EQ_LOOKUP` là tiêu chí duy nhất, vì correlated pipelines, sharding, index types và stage placement ảnh hưởng eligibility.

### 17.5. `explain` không thay production latency metrics

`executionTimeMillis` đo một lần và có thể chịu tác động cache/warmup. Cần xem profiler, slow-query logs, application traces, p50/p95/p99 và throughput dưới concurrency thực.

---

## 18. Schema modeling: embed, reference hay precompute?

### 18.1. Embedding

Ví dụ order chứa snapshot tên/giá sản phẩm tại lúc mua:

~~~javascript
{
  _id: "ORD-101",
  tenantId: "tenant-a",
  items: [
    {
      sku: "SKU-1",
      titleAtPurchase: "Áo khoác",
      qty: 2,
      unitPriceVnd: NumberLong("150000")
    }
  ]
}
~~~

Ưu điểm: đọc order không cần join tới current products để biết lịch sử mua. Điều này **đúng cả nghiệp vụ** vì tên/giá hiện tại có thể đã thay đổi.

Đánh đổi: lặp dữ liệu và phải phân biệt snapshot-at-purchase với canonical product profile.

### 18.2. References + `$lookup`

Phù hợp khi dữ liệu lớn, thay đổi thường xuyên, one-to-many không giới hạn hoặc cần quản lý entity độc lập.

### 18.3. Precomputed summary

Phù hợp khi nhiều requests cùng hỏi count/sum/ranking theo group trong khi raw data lớn.

### 18.4. Bảng quyết định

| Câu hỏi | Embed | `$lookup` | Materialized view |
|---|---|---|---|
| One-to-few ổn định | Tốt | Có thể | Thường không cần |
| One-to-many rất lớn | Rủi ro document phình | Có index/limit | Tốt nếu chỉ cần summary |
| Dữ liệu thay đổi liên tục | Cần sync | Nguồn mới nhất | Cần refresh |
| Lịch sử giá lúc mua | Rất phù hợp | Join current price có thể sai | Có thể tổng hợp snapshot |
| Báo cáo doanh thu theo ngày | Không thay thế group | Không cần nếu orders đầy đủ | Rất phù hợp |
| Cần exact real-time transactional state | Source document | Có thể join source | Staleness là rủi ro |

### 18.5. Không tự dùng SQL thinking cho mọi MongoDB workload

Một số dữ liệu nên được denormalize để giảm join, nhưng không nhồi mọi thứ vào một document vô hạn hoặc tạo nhiều bản sao khó cập nhật. Tối ưu là đánh đổi **read latency, write amplification, consistency và storage**.

---

## 19. Khi nào nên có collection tổng hợp tính sẵn?

Một báo cáo thường xuyên được gọi:

~~~text
Dashboard mỗi 10 giây
  -> Đếm 10 triệu orders theo tenant/ngày
  -> Trả 30 rows
~~~

Nếu mọi request đều chạy cùng `$group`, nhiều nguồn lực bị sử dụng để tái tạo kết quả gần giống nhau.

Ta có thể tạo:

~~~javascript
{
  tenantId: "tenant-a",
  day: ISODate("2026-11-09T17:00:00Z"),
  currency: "VND",
  paidOrders: 1250,
  grossVnd: NumberLong("750000000"),
  computedAt: ISODate("2026-11-14T05:00:00Z"),
  version: 1
}
~~~

`day` là mốc đầu ngày **theo timezone địa phương**, được biểu diễn bằng UTC Date (ở đây 00:00 ngày 10/11 theo Asia/Ho_Chi_Minh tương ứng 17:00Z ngày 09/11).

### 19.1. Khi materialization hợp lý

- Tần suất đọc summary cao hơn tần suất thay đổi.
- Raw scans/groups lớn.
- Có tiêu chí freshness phù hợp.
- Có cách recompute/reconcile từ source.
- Kết quả nhỏ hơn source nhiều.
- Business rules và metric definitions ổn định đủ để quản lý versions.

### 19.2. Khi không nên

- Dataset nhỏ, index query đã đáp ứng.
- Người dùng cần filter tùy ý hàng nghìn combinations; aggregate precompute quá nhiều chiều.
- Data correctness yêu cầu transactional snapshot tức thời nhưng refresh pipeline chỉ eventual.
- Métric thay đổi thường xuyên, backfill quá tốn.
- Không có quy trình khắc phục stale/drift.

### 19.3. Materialized view không phải MongoDB view thông thường

MongoDB **view** là logical, được tính khi đọc qua aggregation definition. Một **materialized view** là collection lưu kết quả đã tính, cần refresh theo lịch/CDC. Hai loại không giống nhau về chi phí và độ mới.

---

## 20. Tạo bảng tổng hợp bằng `$group` và `$merge`

### 20.1. Thiết kế khóa duy nhất

Mỗi tenant, ngày và currency có một row:

~~~javascript
db.dailyOrderSales.createIndex(
  {
    tenantId: 1,
    day: 1,
    currency: 1
  },
  {
    unique: true,
    name: "uk_sales_tenant_day_currency"
  }
);
~~~

Khóa gồm `currency` để tránh cộng lẫn VND và USD. Nếu tất cả orders đã được quy đổi theo tỷ giá lịch sử sang một currency chuẩn, cần lưu metric/tỷ giá/version rõ thay vì âm thầm gộp.

### 20.2. Full aggregation từ source

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      paidAt: { $type: "date" }
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        day: {
          $dateTrunc: {
            date: "$paidAt",
            unit: "day",
            timezone: "Asia/Ho_Chi_Minh"
          }
        },
        currency: "$currency"
      },
      paidOrders: { $sum: 1 },
      grossVnd: { $sum: "$totalVnd" }
    }
  },
  {
    $project: {
      _id: 0,
      tenantId: "$_id.tenantId",
      day: "$_id.day",
      currency: "$_id.currency",
      paidOrders: 1,
      grossVnd: 1,
      computedAt: "$$NOW"
    }
  },
  {
    $merge: {
      into: "dailyOrderSales",
      on: ["tenantId", "day", "currency"],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]);
~~~

**Điều kiện:** Index trên fields trong `on` phải đáp ứng yêu cầu unique index của `$merge`, collation/field rules tương ứng, và mọi output row phải có đúng các trường khóa. Các quy tắc thêm áp dụng với sharded target hoặc những MongoDB versions khác nhau.

### 20.3. Vì sao dùng `$merge`?

`$merge` ghi kết quả aggregation vào collection đích. Với `on` và `whenMatched:"replace"`, một group hiện có được thay bằng số liệu vừa tính; group mới được insert.

Một pipeline dùng replace như trên thường **idempotent ở mức kết quả group tính từ cùng source snapshot**, thuận tiện cho việc chạy lại một bucket. Tuy nhiên các runs đồng thời/chênh lệch nguồn vẫn có thể gây race; cần kiểm soát refresh order.

### 20.4. Khi `$merge` không tự giải quyết consistency

- Một ngày không còn orders PAID sau delete/status rollback: pipeline không sinh row cho ngày đó, nên `$merge` **không tự xóa row cũ**.
- Hai refresh workers cùng viết một bucket có thể ghi kết quả stale đè mới.
- Data thay đổi trong lúc full aggregation có thể làm source read không phản ánh một business cut nhất quán như mong muốn.
- Output snapshot của nhiều groups không được cập nhật atomically như một transaction toàn bộ báo cáo.
- Nếu running `$merge` thất bại giữa chừng, một số rows có thể đã được ghi.

Vì vậy `$merge` là công cụ ghi kết quả, không phải “exactly-once materialized view engine” hoàn chỉnh.

### 20.5. `$out` khác `$merge` thế nào?

- `$merge` hỗ trợ match theo keys và update/insert vào existing collection.
- `$out` tạo/ghi lại output collection theo semantics riêng, thích hợp một số full-refresh jobs.
- Cả hai có các ràng buộc về transactions, sharding, read/write stages và môi trường; không dùng trong read-only API request vô tình.
- Với production cần atomic cutover một snapshot aggregate lớn, có thể build ra **collection version mới**, kiểm tra rồi đổi read pointer/namespace theo chiến lược phù hợp thay vì mutate hàng nghìn rows không đồng bộ.

---

## 21. Query dashboard từ summary collection

Sau materialization:

~~~javascript
db.dailyOrderSales.find(
  {
    tenantId: "tenant-a",
    currency: "VND",
    day: {
      $gte: ISODate("2026-10-31T17:00:00Z"),
      $lt: ISODate("2026-11-30T17:00:00Z")
    }
  },
  {
    _id: 0,
    day: 1,
    paidOrders: 1,
    grossVnd: 1,
    computedAt: 1
  }
).sort({
  day: 1
});
~~~

### 21.1. Index cho dashboard read

Unique index `{tenantId:1,day:1,currency:1}` phục vụ identity của `$merge`, nhưng nếu query luôn có equality trên `tenantId` và `currency` và range/sort `day`, cân nhắc thêm read-optimized index:

~~~javascript
db.dailyOrderSales.createIndex(
  {
    tenantId: 1,
    currency: 1,
    day: 1
  },
  {
    name: "idx_daily_sales_tenant_currency_day"
  }
);
~~~

Hai indexes tạo write amplification; đo có cần cả hai hay có thể thiết kế khóa/index chung phù hợp.

### 21.2. Số lượng rows nhỏ hơn

Nếu có 10 triệu orders nhưng 100 tenants × 365 ngày × 2 currencies, summary tối đa khoảng 73.000 rows, thường rẻ hơn group raw orders liên tục.

### 21.3. Gắn freshness metadata

Một API nên cho thấy:

~~~json
{
  "tenantId": "tenant-a",
  "currency": "VND",
  "rows": [
    {
      "day": "2026-11-10",
      "paidOrders": 1250,
      "grossVnd": 750000000
    }
  ],
  "computedAt": "2026-11-14T05:00:00Z",
  "freshness": "AS_OF_COMPUTED_AT"
}
~~~

Số liệu minh họa. `computedAt` cho biết lúc job chạy, nhưng không chứng minh input đã theo kịp mọi changes. Với streaming, có thể cần **watermark của source events**/resume checkpoint để mô tả freshness tin cậy.

---

## 22. Full refresh, scheduled refresh và incremental refresh

| Cách cập nhật | Khi phù hợp | Lợi ích | Rủi ro |
|---|---|---|---|
| On-demand aggregation | Ít requests/data nhỏ | Đọc dữ liệu trực tiếp | Query nặng khi scale |
| Scheduled full refresh | Báo cáo ít thay đổi, dataset vừa | Logic đơn giản | Đọc lại toàn source |
| Scheduled partial refresh | Daily buckets gần đây | Ít scan hơn | Bỏ sót corrections cũ |
| Event-driven incremental | Thay đổi liên tục, freshness thấp | Ít tính lại nếu đúng | CDC/idempotency/concurrency phức tạp |
| Hybrid CDC + reconciliation | Production critical summary | Freshness + self-healing | Cần nhiều vận hành |
| Append-only rollup | Immutable events | Dễ incremental | Khó với update/delete/backdated |

### 22.1. Scheduled full refresh

Job mỗi giờ chạy group tất cả orders. Đơn giản nhưng đọc lặp lớn. Nếu tenant-a có 10 triệu orders, mỗi giờ lại quét tất cả; cần dự đoán chi phí.

### 22.2. Scheduled partial refresh

Nếu data mới chủ yếu ở 7 ngày gần nhất, job có thể recompute 7 daily buckets. Nhưng late refund cho order 3 tháng trước vẫn cần cập nhật tháng cũ.

### 22.3. Event-driven incremental

Change Stream hoặc outbox event thông báo thay đổi; worker tính lại hoặc điều chỉnh affected groups. Fresh hơn, nhưng phải xử lý retry, duplicate, ordering và event history retention.

### 22.4. Hybrid

Một phương án phổ biến:

~~~text
Change Streams -> cập nhật gần real time
             |
             v
dailyOrderSales

Nightly reconciliation:
  group authoritative orders
  -> compare/repair dailyOrderSales
~~~

Trong hệ thống báo cáo quan trọng, hybrid giúp giảm nguy cơ drift do missed events/restarts.

---

## 23. Incremental aggregation: đừng `$inc` một cách mù quáng

Giả sử một order chuyển từ PENDING sang PAID:

~~~javascript
{
  status: "PAID",
  totalVnd: NumberLong("500000")
}
~~~

Ta có thể nghĩ:

~~~javascript
db.dailyOrderSales.updateOne(
  {
    tenantId: "tenant-a",
    day: saleDay,
    currency: "VND"
  },
  {
    $inc: {
      paidOrders: 1,
      grossVnd: NumberLong("500000")
    }
  },
  { upsert: true }
);
~~~

Nhưng nếu same event được xử lý **hai lần** sau retry, doanh thu tăng gấp đôi.

### 23.1. Các chuyển đổi cần xử lý

| Thay đổi order | Ảnh hưởng aggregate |
|---|---|
| New PENDING | Không tăng PAID revenue |
| PENDING → PAID | Tăng count và amount |
| PAID → REFUNDED | Có thể trừ/reclassify theo policy |
| PAID amount sửa | Cần bù chênh lệch |
| paidAt đổi sang ngày khác | Trừ bucket cũ, cộng bucket mới |
| currency đổi | Chuyển metric sang bucket currency khác |
| Order deleted | Phải trừ/recompute nếu được tính |
| Duplicate CDC event | Không được cộng lại |
| Event đến muộn | Cập nhật lịch sử đúng |
| Business rule thay đổi | Cần backfill/recompute |

### 23.2. Phương án an toàn hơn: recompute affected bucket

Khi nhận event cho order thuộc ngày D:

1. Xác định tenant/currency/day cũ và mới nếu có.
2. Đọc lại source of truth `orders` cho từng affected bucket.
3. Group lại bucket đó.
4. Replace summary row hoặc delete summary nếu bucket không còn order.
5. Ghi checkpoint sau khi kết quả được lưu theo policy.

Đây là phương án **idempotent theo nguồn hiện tại** trong điều kiện không có stale concurrent write. Nó tránh cộng lại same event, đổi lại tốn group scan của bucket.

### 23.3. Khi bucket cũng rất lớn

Có thể duy trì contribution ledger theo `orderId` rồi áp differences có transaction/idempotency. Nhưng thiết kế phức tạp:

- Lưu last accounted status/amount/day.
- Transactionally claim event/contribution version.
- Trừ contribution cũ, cộng mới.
- Dùng unique event ID và ordering.
- Handle out-of-order updates.
- Reconcile với source định kỳ.

Không tuyên bố Change Streams bảo đảm exactly-once business processing chỉ vì có resume token.

---

## 24. Recompute một daily bucket đúng cách

Giả sử cần recompute:

~~~javascript
const tenantId = "tenant-a";
const currency = "VND";
const from = ISODate("2026-11-09T17:00:00Z");
const to = ISODate("2026-11-10T17:00:00Z");

db.orders.aggregate([
  {
    $match: {
      tenantId,
      currency,
      status: "PAID",
      paidAt: {
        $gte: from,
        $lt: to
      }
    }
  },
  {
    $group: {
      _id: null,
      paidOrders: { $sum: 1 },
      grossVnd: { $sum: "$totalVnd" }
    }
  }
]);
~~~

### 24.1. Vì sao dùng `[from,to)`?

Khoảng nửa mở tránh overlap giữa hai ngày liên tiếp. `to` là đầu ngày tiếp theo theo timezone của tenant/business, không nhất thiết là `from+24 giờ` ở vùng có DST.

### 24.2. Nếu không còn order nào?

`$group` có thể không trả document. Worker phải **xóa hoặc đặt summary=0** theo policy. `$merge` của full pipeline không tự xóa stale row trong tình huống này.

### 24.3. Concurrency

Worker A đọc source lúc T1, worker B đọc T2 mới hơn. Nếu B ghi summary trước, A ghi sau, state có thể bị **stale overwrite**. Cần:

- Serial processing per bucket.
- Lease/lock per key.
- Generation/watermark monotonic CAS.
- Hoặc recompute sau khi tất cả events đến và reconcile định kỳ.

Không chỉ “$merge replace idempotent” mà bỏ qua race.

### 24.4. Snapshot semantics

Một aggregation đọc source trong khi writes tiếp tục có thể quan sát dữ liệu thay đổi theo semantics read concern/snapshot. Với financial reporting, xác định cutoff/consistency policy; không mặc định mọi group cùng đại diện một transactionally consistent global point.

---

## 25. Change Streams để duy trì summary

### 25.1. Luồng tổng quát

~~~text
MongoDB orders
   |
   +-- insert/update/replace/delete
   |
   v
Change Stream consumer
   |
   v
Determine affected bucket(s)
   |
   v
Recompute or apply idempotent contribution
   |
   v
dailyOrderSales
   |
   v
Checkpoint resume token
~~~

### 25.2. Vì sao cần resume token?

Khi worker crash, token cho phép tiếp tục từ sự kiện đã xử lý theo semantics của Change Streams, nếu oplog history vẫn còn phù hợp.

### 25.3. Không checkpoint trước khi lưu summary

Sai:

~~~text
Read event
  -> persist resume token
  -> crash
  -> summary chưa cập nhật
~~~

Sau restart, worker có thể bỏ lỡ ảnh hưởng event đó.

Tốt hơn là chỉ lưu checkpoint sau khi update summary thành công. Tuy nhiên nếu crash **sau update trước checkpoint**, event sẽ được xử lý lại, nên refresh phải idempotent hoặc có dedup transaction.

### 25.4. Delete và pre-images

Một delete event thường mang document key nhưng không mặc định chứa toàn bộ before document. Để biết bucket ngày/tenant cũ, có thể cần:

- Change Stream pre-images được bật khi phù hợp và retention đủ.
- Contribution ledger keyed by orderId.
- Audit/outbox event lưu before/after.
- Reconciliation/backfill nếu không có thông tin cũ.

Không giả định luôn biết old `paidAt` và `currency` từ delete event.

### 25.5. Oplog history loss

Nếu consumer dừng quá lâu, resume token có thể không còn dùng được. Khi đó cần bootstrap/recompute từ source và thiết lập checkpoint mới theo quy trình tránh mất khoảng dữ liệu, không chỉ watch “từ hiện tại” và bỏ qua những thay đổi đã xảy ra.

---

## 26. Bảo vệ summary khỏi double-count và drift

### 26.1. At-least-once delivery là mặc định thiết kế an toàn

Một event có thể được xử lý lại sau crash/retry. Vì thế code `$inc` phải có dedup trước khi apply; nếu không, count/sum sai.

### 26.2. Contribution ledger

Lưu document:

~~~javascript
{
  _id: "ORD-101",
  tenantId: "tenant-a",
  sourceVersion: 12,
  day: ISODate("2026-11-09T17:00:00Z"),
  currency: "VND",
  paidContributionVnd: NumberLong("500000"),
  paidContributionCount: 1,
  updatedAt: ISODate("2026-11-14T04:00:00Z")
}
~~~

Với update mới, tìm contribution cũ rồi tính delta. Mọi thay đổi ledger + summary cần atomicity/idempotency phù hợp; nếu dùng transaction, phải thiết kế write concern/retry/unknown commit result.

### 26.3. Không giả định event ordering toàn hệ thống

Change Streams bảo tồn thứ tự theo những semantics cụ thể, nhưng nhiều partitions/workers, external broker và retries có thể làm event đến lệch thứ tự ở service của bạn.

Dùng source version hoặc sequence monotonic để không apply event cũ đè event mới. Không dùng `updatedAt` client-controlled làm version tuyệt đối nếu clock skew là rủi ro.

### 26.4. Reconciliation job

Định kỳ tính lại một số buckets bằng aggregation authoritative và so:

~~~text
expected grossVnd from orders
vs
observed grossVnd in dailyOrderSales
~~~

Nếu chênh lệch, ghi metric và repair có audit. Một summary nhanh nhưng sai 0,5% doanh thu vẫn không đạt yêu cầu báo cáo tiền.

---

## 27. Dữ liệu đến muộn và backfill

### 27.1. Event time vs processing time

Một order thanh toán lúc 23:59 ngày thứ hai nhưng event tới worker lúc 00:05 thứ ba. Nếu group theo processing time, doanh thu bị chuyển sai ngày.

Quy tắc thường đúng hơn: tính bucket bằng **business event time** như `paidAt` theo timezone đã chọn.

### 27.2. Late correction

Một order của tháng trước có refund hôm nay. Business có thể muốn:

- Giảm revenue của **ngày bán ban đầu**.
- Ghi revenue net âm ở **ngày refund**.
- Theo dõi gross sales và refunds như **hai metrics riêng**.

Không có một định nghĩa kế toán duy nhất; phải xác định metric contract trước khi viết pipeline.

### 27.3. Backfill history

Khi đổi định nghĩa “paid order” hoặc thêm currency:

1. Tăng `metricSchemaVersion`.
2. Chạy backfill vào collection/version mới.
3. Đo completeness/checksum.
4. Canary so với báo cáo cũ.
5. Đổi dashboard read pointer/feature flag.
6. Giữ rollback path.
7. Dọn aggregate cũ khi được duyệt.

### 27.4. TTL không thay business retention

Nếu TTL xóa raw orders trước khi backfill/repair, summary có thể không còn nguồn để tính lại. Retention của raw data và event logs phải bao phủ cửa sổ correction, audit và restore cần thiết.

---

## 28. Các phép tổng hợp khó cập nhật incremental

### 28.1. `$sum` và `$count`

Tương đối dễ áp delta nếu biết before/after và event không bị áp trùng.

### 28.2. `$avg`

Không chỉ lưu average; lưu `sum` và `count` rồi tính average từ hai trường. Khi có delete/update, điều chỉnh sum/count đúng.

### 28.3. `$min` và `$max`

Giả sử min price=100, bản ghi giữ min bị xóa. Không thể tìm min mới chỉ từ giá trị 100; cần dữ liệu thành viên hoặc recompute bucket.

### 28.4. Distinct count

Đếm unique customers có thể cần set lớn, contribution/reference counts hoặc thuật toán approximate distinct (nếu business chấp nhận). Không thể cộng mọi event “customerSeen” vì một khách có nhiều orders.

### 28.5. Percentiles

Percentile không có phép trừ đơn giản khi một record bị xóa. Có thể dùng batch recomputation, histogram hoặc cấu trúc dữ liệu approximate với policy rõ ràng.

### 28.6. Window aggregates

Moving averages/running totals có thể phụ thuộc nhiều buckets; update một ngày lịch sử ảnh hưởng cả cửa sổ phía sau.

---

## 29. Nhiều tenants và sharded cluster

### 29.1. Tenant-aware filtering

Đặt tenant filter trong source match và materialized key. Không tính summary toàn hệ thống rồi cho tenant tùy ý đọc records nếu privacy/isolation yêu cầu tách.

### 29.2. Shard key

Với sharded `orders`, query có `tenantId` có thể target ít shards hơn nếu shard key và query shape phù hợp. Nhưng shard key chọn không chỉ cho dashboard; phải cân bằng writes, tenant skew và hotspot.

### 29.3. `$lookup` trên sharded collections

MongoDB hỗ trợ `$lookup` với sharded foreign collection ở các phiên bản được hỗ trợ (ví dụ từ MongoDB 5.1 trở lên), nhưng performance chịu ảnh hưởng của routing, index và lượng dữ liệu liên shards. Không giả định join giữa shards nhanh như một local `_id` lookup.

### 29.4. `$group` trên sharded clusters

Aggregation có thể thực hiện partial aggregation trên shards rồi merge results, nhưng cần kiểm tra stage placement, merge location và network. Một group toàn cluster có thể tốn coordinator memory/I/O.

### 29.5. `$merge` vào sharded target

Có yêu cầu đối với fields trong `on` và shard key/index uniqueness. Không viết một `$merge` chỉ dựa trên `tenantId,day` khi target shard key đòi fields khác mà chưa kiểm tra MongoDB version/rules.

### 29.6. Hot buckets

Một tenant lớn có thể làm “daily aggregate document” trở thành hot document nếu cập nhật `$inc` trên mỗi đơn. Có thể:

- Dùng sharded counters/buckets rồi hợp nhất.
- Batch updates.
- Materialize từ log theo khoảng.
- Dùng per-minute/hour summary rồi roll up.
- Tối ưu queue partitioning theo tenant + time.

Cân bằng write contention với số documents/indexes và read complexity.

---

## 30. Java Sync Driver: aggregation pipeline tối ưu

Ví dụ backend truy vấn 20 đơn đã thanh toán gần nhất và enrich tên khách.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.List;

public class OptimizedOrdersExample {

    public static void run(MongoClient client) {
        MongoDatabase db =
            client.getDatabase("aggregation_perf_lab");

        MongoCollection<Document> orders =
            db.getCollection("orders");

        Document match = new Document(
            "$match",
            new Document("tenantId", "tenant-a")
                .append("status", "PAID")
        );

        Document sort = new Document(
            "$sort",
            new Document("paidAt", -1)
                .append("_id", -1)
        );

        Document lookup = new Document(
            "$lookup",
            new Document("from", "customers")
                .append("localField", "customerId")
                .append("foreignField", "_id")
                .append("as", "customer")
        );

        Document unwind = new Document(
            "$unwind",
            new Document("path", "$customer")
                .append(
                    "preserveNullAndEmptyArrays",
                    true
                )
        );

        Document project = new Document(
            "$project",
            new Document("_id", 1)
                .append("paidAt", 1)
                .append("totalVnd", 1)
                .append("customer.displayName", 1)
        );

        orders.aggregate(
            List.of(
                match,
                sort,
                new Document("$limit", 20),
                lookup,
                unwind,
                project
            )
        ).forEach(System.out::println);
    }
}
~~~

### 30.1. Lý do chọn stage order

- `$match` lọc tenant/status.
- `$sort` + `$limit` chọn 20 orders cần hiển thị.
- `$lookup` chỉ join 20 orders.
- `$unwind` và `$project` tạo response gọn.

**Không dùng lại thứ tự này** nếu yêu cầu “20 orders thuộc khách VIP gần nhất” vì lúc đó cần xét customer segment trước limit hoặc dùng denormalized segment có freshness semantics phù hợp.

### 30.2. Quản lý MongoClient

Trong Java backend, `MongoClient` thường là đối tượng dùng lâu dài có pooling, không tạo mới mỗi request. Đặt server-side timeout và application-level deadline để aggregation nặng không giữ request vô hạn.

### 30.3. Input từ client

Dữ liệu tenant và authorization phải do backend xác định. Không truyền raw user JSON làm arbitrary `$match` hoặc `$lookup` vì có thể bypass quyền và gây query quá tải.

---

## 31. Java Sync Driver: tạo job tính summary

Có thể dùng raw BSON stages để biểu diễn `$merge`:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.List;

public class DailySalesRefresh {

    public static void execute(MongoClient client) {
        MongoDatabase db =
            client.getDatabase("aggregation_perf_lab");

        MongoCollection<Document> orders =
            db.getCollection("orders");

        Document dateTrunc = new Document(
            "$dateTrunc",
            new Document("date", "$paidAt")
                .append("unit", "day")
                .append(
                    "timezone",
                    "Asia/Ho_Chi_Minh"
                )
        );

        Document match = new Document(
            "$match",
            new Document("status", "PAID")
        );

        Document groupId = new Document(
            "tenantId", "$tenantId"
        )
            .append("currency", "$currency")
            .append("day", dateTrunc);

        Document group = new Document(
            "$group",
            new Document("_id", groupId)
                .append(
                    "paidOrders",
                    new Document("$sum", 1)
                )
                .append(
                    "grossVnd",
                    new Document("$sum", "$totalVnd")
                )
        );

        Document projection = new Document(
            "$project",
            new Document("_id", 0)
                .append("tenantId", "$_id.tenantId")
                .append("currency", "$_id.currency")
                .append("day", "$_id.day")
                .append("paidOrders", 1)
                .append("grossVnd", 1)
        );

        Document merge = new Document(
            "$merge",
            new Document(
                "into",
                "dailyOrderSales"
            )
                .append(
                    "on",
                    List.of(
                        "tenantId", "day", "currency"
                    )
                )
                .append(
                    "whenMatched",
                    "replace"
                )
                .append(
                    "whenNotMatched",
                    "insert"
                )
        );

        // $merge là write stage, không trả rows
        // theo cách một query báo cáo thông thường.
        orders.aggregate(
            List.of(
                match,
                group,
                projection,
                merge
            )
        ).toCollection();
    }
}
~~~

### 31.1. Điều kiện trước khi chạy

- Database/index unique đúng.
- Server/version hỗ trợ các stages/expressions.
- Account có quyền đọc orders và ghi collection summary.
- Timezone và số tiền đúng business policy.
- Job không đụng các concurrent refresh khác theo cách stale overwrite.
- Có monitoring khi failed/missed refresh.

### 31.2. Không gọi từ mỗi HTTP request

`$merge` thay đổi dữ liệu; không nên để một dashboard request vô tình chạy full refresh. Dùng scheduled job/worker có retry, lock và SLO riêng, sau đó dashboard query summary collection.

---

## 32. Benchmark: đo đúng workload

### 32.1. Dữ liệu lab nhỏ không đủ

Với 4 orders, cả `COLLSCAN` và index scan đều nhanh. Nên benchmark trên dataset giả lập gần production:

- 1–100 triệu orders.
- Nhiều tenants có kích thước chênh lệch.
- Phân bố status, dates và customerId thực tế.
- Array items dài/ngắn khác nhau.
- Số customers trung bình/tenant.
- Tỷ lệ update/delete/refund.
- Query concurrency.
- Cold vs warm cache.
- Sharding/topology tương tự production.

### 32.2. Các phương án so sánh

A. Raw aggregation mỗi lần dashboard mở.

B. Raw aggregation với compound indexes.

C. `$group` trước `$lookup`.

D. Correlated `$lookup` với index foreign và `$limit`.

E. Scheduled materialized summary.

F. Incremental summary + nightly reconciliation.

### 32.3. Chỉ số benchmark

| Nhóm | Chỉ số |
|---|---|
| Latency | p50/p95/p99, max duration |
| Throughput | Requests/second |
| Query work | Keys/docs examined |
| Memory | Sort/group/spill |
| Join | Foreign scans, returned fan-out |
| I/O | Disk read/write, network |
| Resource | CPU/RAM/search or mongod usage |
| Write cost | Extra writes, index updates |
| Freshness | Summary lag/watermark |
| Correctness | Mismatch ratio vs authoritative recompute |
| Operations | Failed refresh, replay time, backfill duration |

### 32.4. Đo correctness cùng performance

Ví dụ summary query giảm từ 2 giây xuống 20 ms nhưng doanh thu sai 1% do duplicate CDC events. Không được coi đó là cải thiện thành công.

### 32.5. Warm-up và explain overhead

Chạy benchmark nhiều lần với dữ liệu/query shapes đa dạng. `explain("executionStats")` hữu ích để nhìn plan, nhưng workload thực tế còn có network, application serialization, cache, concurrency và framework overhead.

---

## 33. Những lỗi thiết kế thường gặp

**Lỗi 1 — “Cứ `$match` là stage đầu tiên.”** Không phải mọi trường hợp; search/geo stages có quy tắc và computed fields có dependencies.

**Lỗi 2 — “Đặt `$project` đầu mọi pipeline là tối ưu.”** Optimizer đã có field projection optimization, phải đo.

**Lỗi 3 — “Chỉ cần thêm index cho mọi field.”** Index tăng storage/write overhead và không bảo đảm plan tốt.

**Lỗi 4 — “`$sort` có index thì mọi pipeline đều free.”** Nếu đã group/biến đổi key, sort theo aggregate field vẫn có thể blocking.

**Lỗi 5 — “`$limit` trước join không đổi kết quả.”** Sai khi join lọc hoặc xếp hạng dựa trên related data.

**Lỗi 6 — “`$lookup` luôn trả một document.”** Nó trả array; one-to-many có thể fan-out lớn.

**Lỗi 7 — “Foreign collection có index bất kỳ là đủ.”** Phải phù hợp foreign key/predicate, xem explain.

**Lỗi 8 — “Correlated `$expr` dùng index cho mọi expression.”** Có giới hạn field-vs-constant và multikey/các index types.

**Lỗi 9 — “`$unwind` không làm tăng rows.”** One-to-many array có thể nhân dữ liệu gấp hàng chục lần.

**Lỗi 10 — “`$group` rồi `$push:$$ROOT` là cách xuất dữ liệu an toàn.”** Có thể vượt memory và giới hạn BSON 16 MiB.

**Lỗi 11 — “`allowDiskUse:true` làm query nhanh hơn.”** Thường chỉ cho phép spill, có thể tăng I/O/latency.

**Lỗi 12 — “`$facet` không giới hạn bộ nhớ khi allowDiskUse.”** Không đúng.

**Lỗi 13 — “View thường là materialized view.”** MongoDB view logic tính lúc đọc; precomputed collection phải refresh.

**Lỗi 14 — “`$merge` tự xóa các groups đã biến mất.”** Không. Nhóm không còn source thường không xuất hiện trong output để cập nhật.

**Lỗi 15 — “`$merge replace` tự ngăn stale concurrent jobs.”** Không; worker cũ có thể ghi đè worker mới.

**Lỗi 16 — “Change Stream chỉ giao event một lần.”** Không được thiết kế nghiệp vụ theo giả định exactly-once.

**Lỗi 17 — “`$inc` mỗi event là an toàn.”** Duplicate event gây double count.

**Lỗi 18 — “Delete event luôn có before image.”** Không mặc định; cần pre-images/audit/contribution ledger.

**Lỗi 19 — “Order đổi ngày chỉ cộng bucket mới.”** Phải trừ/recompute bucket cũ.

**Lỗi 20 — “VND và USD có thể cộng thẳng.”** Không; cần currency dimension hoặc conversion contract.

**Lỗi 21 — “Có tổng và count hiện tại thì xử lý min/max delete được.”** Không; có thể cần recompute.

**Lỗi 22 — “Một materialized aggregate là nguồn dữ liệu thật.”** Source of truth nên xác định rõ; summary có thể stale.

**Lỗi 23 — “Số computedAt mới chứng minh mọi events đã xử lý.”** Không; cần checkpoint/watermark.

**Lỗi 24 — “Một index tốt cho mọi tenants.”** Tenant skew, sharding và query mix ảnh hưởng index strategy.

**Lỗi 25 — “Query nhanh trên 1.000 docs là production-ready.”** Cần data scale/concurrency/correctness tests.

---

## 34. Checklist tối ưu aggregation, join và summary

### 34.1. Aggregation

- [ ] Có yêu cầu business/metric chính xác.
- [ ] `$match` dùng tenant/status/time range và được đặt đúng.
- [ ] `$sort` dựa trên index khi có thể.
- [ ] `$limit` đặt không làm mất kết quả business hợp lệ.
- [ ] Không dùng `$skip` sâu khi có thể keyset.
- [ ] Projection loại fields không cần.
- [ ] `$group` không có số groups/arrays quá lớn.
- [ ] Memory/spill được giám sát.
- [ ] Query explain được đo trên realistic dataset.
- [ ] Không nhầm UTC vs timezone business.

### 34.2. Join

- [ ] Foreign join keys có index phù hợp.
- [ ] Fan-out được ước lượng.
- [ ] Có tenant/authorization predicates.
- [ ] Không lookup hàng triệu related docs khi chỉ cần count.
- [ ] Dùng correlated pipeline khi cần nhiều điều kiện.
- [ ] Khi `$unwind`, hiểu chuyện missing/empty arrays.
- [ ] Đặt sort/limit trước join chỉ khi semantics cho phép.
- [ ] Không tạo N+1 query loop ở application.
- [ ] Đã cân nhắc denormalize snapshot fields khi business hợp lý.

### 34.3. Materialized summary

- [ ] Source of truth được xác định.
- [ ] Metric definition, currency và timezone rõ ràng.
- [ ] Unique summary key/index phù hợp.
- [ ] Có trạng thái refresh, `computedAt` và watermark.
- [ ] Insert/update/delete/late-event handling.
- [ ] Dedup/idempotency/ordering.
- [ ] Không stale overwrite từ concurrent workers.
- [ ] Có xử lý group về 0/biến mất.
- [ ] Scheduled reconciliation và backfill.
- [ ] Schema/metric versioning + rollback path.
- [ ] Thử read consistency khi refresh chạy.
- [ ] Có alert khi summary lag/drift.

### 34.4. Production

- [ ] p95/p99 latency và CPU/IO trong SLO.
- [ ] Search/sharding/deployment version constraints.
- [ ] MaxTimeMS/timeout/rate limits phù hợp.
- [ ] Không lộ dữ liệu tenant khác.
- [ ] Backup/restore cả source và view/index definitions cần thiết.
- [ ] Có quyền riêng cho refresh worker.
- [ ] Benchmark trên data volume/trạng thái thực tế.

---

## 35. Bài tập thực hành

### Bài tập 1 — Pipeline đơn giản

Viết aggregation doanh thu của tenant-a theo ngày trong tháng 11/2026. Dùng `$match` trước `$group` và `$dateTrunc` với timezone `Asia/Ho_Chi_Minh`.

### Bài tập 2 — Giải thích sort

So sánh `$sort + $limit` với `$limit + $sort`. Vì sao thứ tự thứ hai có thể không trả top 20 toàn tập?

### Bài tập 3 — Index ESR

Đề xuất index cho `tenantId=status=PAID`, sort `paidAt:-1,_id:-1`. Chạy explain.

### Bài tập 4 — Projection

So sánh query trả toàn bộ order với chỉ `_id,paidAt,totalVnd`. Đo payload/latency.

### Bài tập 5 — Group cardinality

Group theo `status`, rồi theo `customerId`; quan sát số groups và memory sử dụng khi dataset tăng.

### Bài tập 6 — `$first` đúng nghĩa

Tìm newest order theo mỗi customer. Thêm sort tie-break theo `_id`.

### Bài tập 7 — `$lookup` equality

Join orders → customers qua `customerId` và `_id`, chỉ trả displayName. Kiểm tra foreign index.

### Bài tập 8 — Fan-out

Join customers → all orders rồi unwind. Tính số rows trung gian khi một customer có 10.000 orders.

### Bài tập 9 — Lookup top 3

Viết correlated lookup trả ba orders mới nhất per customer, đề xuất foreign compound index.

### Bài tập 10 — Count thay array

Thay lookup allOrders bằng pipeline group count/total. So sánh memory/network.

### Bài tập 11 — Tenant filter

Viết correlated lookup với cả `customerId` và `tenantId`. Test một customerId/logic key trùng giữa hai tenants.

### Bài tập 12 — `$unwind`

Một order có 5 items, 1 order có 0 items. So sánh output khi `preserveNullAndEmptyArrays` bật/tắt.

### Bài tập 13 — `$facet`

Tạo response gồm page 20 orders, counts by status, tổng doanh thu. Nêu khi nào nên tách stats thành query summary.

### Bài tập 14 — `allowDiskUse`

Tạo aggregation high-cardinality group trong môi trường lab, so sánh explain/spill theo điều kiện server hỗ trợ.

### Bài tập 15 — Materialized view

Tạo `dailyOrderSales` với unique key `tenantId/day/currency` và `$group + $merge`. Đọc summary theo tháng.

### Bài tập 16 — Group bị xóa

Sau khi materialize, đổi tất cả orders một ngày từ PAID sang CANCELLED. Vì sao `$merge` full refresh có thể để row cũ? Đề xuất cách xóa/zero/rebuild.

### Bài tập 17 — Duplicate event

Worker dùng `$inc` nhận cùng change event hai lần. Chứng minh doanh thu bị double-count và thiết kế dedup.

### Bài tập 18 — Order đổi ngày

Một order đổi `paidAt` từ ngày 10 sang ngày 11. Nêu những buckets cần recompute.

### Bài tập 19 — Refund

Chọn chính sách gross revenue và refunds; thiết kế hai metrics để không nhầm gross/net.

### Bài tập 20 — Late event

Một payment 23:59 ngày 10 được consumer nhận 00:05 ngày 11. Giải thích event time vs processing time và timezone.

### Bài tập 21 — $merge concurrency

Hai workers cùng recompute một ngày ở source snapshots khác nhau. Đề xuất serialization/CAS/watermark.

### Bài tập 22 — Incremental min/max

Một nhóm có min 100 và second min 120. Xóa document min 100; vì sao không thể chỉ subtract min và cần recompute?

### Bài tập 23 — Change Streams

Thiết kế checkpoint-after-success và cơ chế bootstrap sau oplog history lost; xử lý delete không có before image.

### Bài tập 24 — Java Sync Driver

Viết pipeline match/sort/limit/lookup/unwind/project bằng `Document` và giải thích vì sao limit đúng trong use case này.

### Bài tập 25 — Multi-tenant sharding

Nêu ảnh hưởng của tenant skew khi group/join và khi cập nhật một summary document nóng.

### Bài tập 26 — Benchmark

So sánh raw aggregation mỗi request và materialized summary trên dataset lớn, đo p95 latency, I/O, summary freshness, discrepancy và write cost.

---

## 36. Câu hỏi ôn tập

1. Ba nhóm chi phí lớn của aggregation, join và materialization là gì?
2. Khi nào `$match` được đưa lên sớm?
3. Vì sao không phải `$match` nào cũng đặt đầu pipeline được?
4. `$geoNear`, `$search` và `$vectorSearch` ảnh hưởng stage order thế nào?
5. ESR là viết tắt của gì?
6. Vì sao compound index có thể giúp cả filter và sort?
7. Vì sao index rất dài đôi khi làm writes chậm hơn?
8. Thế nào là covered query?
9. Khi nào `$sort` là blocking?
10. `$sort+$limit` có thể được optimizer tối ưu như thế nào?
11. Vì sao deep `$skip` có thể chậm?
12. Keyset pagination cần những sort keys nào?
13. `$project` sớm luôn cải thiện tốc độ không?
14. `$group` có chi phí memory như thế nào?
15. Tại sao group bằng `customerId` khác group bằng `status`?
16. `$first` có ý nghĩa gì khi chưa có sort?
17. Vì sao `$push:$$ROOT` nguy hiểm với group rất lớn?
18. `allowDiskUse` giải quyết được mọi memory limit không?
19. `$lookup` trả object hay array?
20. Foreign index quan trọng thế nào?
21. `$lookup` dùng `localField/foreignField` khác correlated `pipeline/let` ra sao?
22. Các điều kiện nào giúp `$expr` trong `$lookup` có thể dùng index?
23. Fan-out trong join là gì?
24. Khi nào nên `$limit` trước `$lookup`?
25. Vì sao lọc customer VIP sau limit có thể làm mất top-20 hợp lệ?
26. `$unwind` có thể làm số rows thay đổi ra sao?
27. Khi nào dùng `$filter/$map` thay unwind?
28. `$facet` có những giới hạn gì?
29. MongoDB view khác materialized view như thế nào?
30. Khi nào nên tính sẵn dữ liệu?
31. `$merge` khác `$out` thế nào?
32. Tại sao `$merge` cần unique index cho fields trong `on`?
33. Vì sao full refresh `$merge` không tự xóa group đã biến mất?
34. Khi nào cần full refresh thay incremental?
35. Tại sao `$inc` theo mỗi event có thể double-count?
36. Change Streams có bảo đảm exactly-once business processing không?
37. Delete event thiếu before image gây vấn đề gì?
38. Contribution ledger dùng để làm gì?
39. Vì sao average nên được lưu thành sum/count?
40. Vì sao min/max khó incremental sau delete?
41. Vì sao currency cần là dimension của summary?
42. Local day khác UTC day thế nào?
43. Dữ liệu đến muộn ảnh hưởng summary ra sao?
44. Worker cũ ghi đè summary mới là lỗi concurrency gì?
45. `computedAt` và source watermark khác nhau ra sao?
46. Search index/cache/summary nào là source of truth?
47. Sharded join có thể tốn network ở đâu?
48. Hot aggregate bucket nên được xử lý thế nào?
49. Vì sao explain không đủ để chứng minh SLO?
50. Tối ưu nhanh nhưng sai business results có được chấp nhận không?

---

## 37. Tổng kết

Tối ưu MongoDB aggregation, join và dữ liệu tổng hợp tính sẵn phải thực hiện theo ba tầng.

**Tầng truy vấn:** Viết `$match`/`$sort`/`$limit`/`$project`/`$group` đúng ngữ nghĩa, loại bỏ xử lý thừa, tránh fan-out và sort trên tập quá lớn.

**Tầng truy cập vật lý:** Chọn compound indexes phù hợp filter/sort/join, kiểm tra `explain("executionStats")`, memory, spills, documents examined và foreign scans.

**Tầng kiến trúc:** Khi dashboard phải lặp đi lặp lại cùng phép nhóm khối dữ liệu lớn, materialize kết quả ra collection với `$merge` hoặc pipeline refresh phù hợp. Luôn có một authoritative source, định nghĩa metric, timezone, currency, consistency contract, idempotent refresh, backfill và reconciliation.

Những nguyên tắc quan trọng:

1. **Giữ tính đúng trước khi tối ưu:** không di chuyển limit/join/group tùy tiện.
2. **Đo bằng explain và benchmark thực tế:** không suy từ code hoặc dataset bé.
3. **Giới hạn join fan-out:** lookup chỉ những rows/fields cần hoặc tính summary trước.
4. **Đừng tính lại cùng báo cáo nặng mỗi request** nếu dữ liệu có thể được tính sẵn theo mức freshness chấp nhận.
5. **Dữ liệu tổng hợp có lifecycle riêng:** rebuild, incremental updates, late events, deletes, concurrency, schema versioning và monitoring.
6. **`$merge` không tự giải quyết stale groups, exactly-once hoặc concurrent writer ordering.**
7. **Phân biệt computedAt và freshness thật:** dùng checkpoint/watermark và định kỳ đối soát với source.
8. **Tenant isolation, money precision và timezone** là một phần của tính đúng kết quả, không phải chi tiết phụ.

Câu hỏi cuối cùng khi thiết kế pipeline không chỉ là “có thể giảm từ 2 giây xuống 20 ms không?”, mà là **“20 ms đó còn trả đúng tập dữ liệu, đúng tenant, đúng thời điểm và vẫn đúng sau update/delete/retry không?”**

## Tài liệu tham khảo

- [MongoDB Manual — Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/)
- [MongoDB Manual — Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)
- [MongoDB Manual — Aggregation Commands](https://www.mongodb.com/docs/manual/aggregation/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — $match](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/)
- [MongoDB Manual — $sort](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sort/)
- [MongoDB Manual — $limit](https://www.mongodb.com/docs/manual/reference/operator/aggregation/limit/)
- [MongoDB Manual — $project](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/)
- [MongoDB Manual — $group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/)
- [MongoDB Manual — $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [MongoDB Manual — $unwind](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/)
- [MongoDB Manual — $facet](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/)
- [MongoDB Manual — $setWindowFields](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setWindowFields/)
- [MongoDB Manual — $dateTrunc](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/)
- [MongoDB Manual — $merge](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/)
- [MongoDB Manual — $out](https://www.mongodb.com/docs/manual/reference/operator/aggregation/out/)
- [MongoDB Manual — Read-Only Views and Materialized Views](https://www.mongodb.com/docs/manual/core/materialized-views/)
- [MongoDB Manual — ESR Index Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/)
- [MongoDB Manual — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/)
