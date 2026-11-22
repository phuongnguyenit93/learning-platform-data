# Đọc `explain` cho aggregation và tối ưu thứ tự stage trong MongoDB

Một aggregation pipeline có thể cho kết quả đúng nhưng vẫn chạy chậm khi collection lớn. Nguyên nhân có thể là MongoDB phải đọc quá nhiều document trước khi lọc, sắp xếp một tập dữ liệu rộng, nhân số dòng bằng `$unwind`, tạo nhiều nhóm trung gian với `$group` hoặc truy cập collection khác nhiều lần qua `$lookup`. Chỉ nhìn câu lệnh pipeline chưa đủ để biết máy chủ thực sự làm những công việc nào.

Trong chương **Aggregation nâng cao**, chúng ta kết hợp hai kỹ năng:

1. **Đọc kết quả `explain` của aggregation:** xác định truy vấn có dùng index, phần nào quét collection, phần nào thực thi các stage, bao nhiêu dữ liệu được xem xét, có thao tác sort/group tốn bộ nhớ hoặc ghi dữ liệu tạm ra đĩa không.
2. **Tối ưu thứ tự stage:** đưa những điều kiện lọc có thể áp dụng sớm về trước, tận dụng index cho `$match` và `$sort`, đặt `$limit` đúng chỗ, hạn chế mở rộng số dòng bằng `$unwind` và khối lượng join bằng `$lookup`, đồng thời giữ **nguyên ý nghĩa kết quả**.

Điều cần ghi nhớ ngay từ đầu là MongoDB có **aggregation optimizer**. Server có thể tự di chuyển, tách hoặc kết hợp một số stage khi việc đó không đổi ngữ nghĩa. Do đó, tối ưu không phải cứ đổi vị trí các dòng trong pipeline là chắc chắn nhanh hơn; cần dùng `explain` để xem kế hoạch sau tối ưu và đo đạc trên dữ liệu đại diện.

## 1. Tư duy về pipeline: dữ liệu chảy qua từng stage

Một pipeline ví dụ:

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 10 },
  { $project: { _id: 1, customerId: 1, total: 1 } }
])
```

Ý nghĩa logic:

```text
orders collection
      |
      v
  $match status=paid        Giữ đơn đã thanh toán
      |
      v
  $sort mới nhất trước      Xác định thứ tự
      |
      v
  $limit 10                 Lấy tối đa 10 đơn
      |
      v
  $project                  Giữ các field cần hiển thị
      |
      v
  Kết quả
```

Để so sánh các pipeline, hãy phân biệt:

| Khái niệm | Ý nghĩa | Cần quan sát |
| --- | --- | --- |
| **Thứ tự viết trong pipeline** | Ngữ nghĩa do lập trình viên khai báo | Stage trước có tạo field cho stage sau không? |
| **Pipeline được optimizer biến đổi** | Những bước MongoDB có thể di chuyển/gộp khi tương đương | Có `$match` được đẩy lên trước `$project` không? `$limit` có nhập vào `$sort` không? |
| **Query plan truy cập collection** | Cách lấy dữ liệu ban đầu từ collection/index | `COLLSCAN`, `IXSCAN`, `FETCH`, `SORT`, index bounds |
| **Thực thi các stage còn lại** | Công việc của `$group`, `$lookup`, `$unwind`, `$setWindowFields`, v.v. | Số dòng đầu vào/đầu ra, thời gian, bộ nhớ, spill nếu được báo cáo |

Một pipeline có cùng kết quả logic ở hai cách viết có thể đã được optimizer biến về kế hoạch tương tự. Nhưng một phép đổi thứ tự **không tương đương** sẽ tạo kết quả khác, không phải một tối ưu hợp lệ.

## 2. Chuẩn bị bộ dữ liệu thực hành

Mở `mongosh` và chọn database riêng:

```javascript
use mongo_aggregation_explain_lab
```

Chèn 12 đơn hàng vào collection `orders` mới hoặc trống:

```javascript
db.orders.insertMany([
  {
    _id: 101, customerId: "u1", status: "paid",
    region: "north", total: 120,
    createdAt: ISODate("2026-11-10T08:00:00Z"),
    items: [{ sku: "A", qty: 2 }, { sku: "B", qty: 1 }]
  },
  {
    _id: 102, customerId: "u2", status: "paid",
    region: "south", total: 250,
    createdAt: ISODate("2026-11-10T09:00:00Z"),
    items: [{ sku: "B", qty: 3 }]
  },
  {
    _id: 103, customerId: "u1", status: "pending",
    region: "north", total: 80,
    createdAt: ISODate("2026-11-10T10:00:00Z"),
    items: [{ sku: "C", qty: 1 }]
  },
  {
    _id: 104, customerId: "u3", status: "paid",
    region: "north", total: 300,
    createdAt: ISODate("2026-11-11T08:00:00Z"),
    items: [{ sku: "A", qty: 1 }, { sku: "C", qty: 2 }]
  },
  {
    _id: 105, customerId: "u2", status: "refunded",
    region: "south", total: 70,
    createdAt: ISODate("2026-11-11T09:00:00Z"),
    items: [{ sku: "B", qty: 1 }]
  },
  {
    _id: 106, customerId: "u1", status: "paid",
    region: "south", total: 180,
    createdAt: ISODate("2026-11-11T10:00:00Z"),
    items: [{ sku: "A", qty: 3 }]
  },
  {
    _id: 107, customerId: "u4", status: "pending",
    region: "north", total: 90,
    createdAt: ISODate("2026-11-12T08:00:00Z"),
    items: [{ sku: "B", qty: 2 }]
  },
  {
    _id: 108, customerId: "u3", status: "paid",
    region: "south", total: 210,
    createdAt: ISODate("2026-11-12T09:00:00Z"),
    items: [{ sku: "C", qty: 3 }]
  },
  {
    _id: 109, customerId: "u2", status: "paid",
    region: "north", total: 160,
    createdAt: ISODate("2026-11-12T10:00:00Z"),
    items: [{ sku: "A", qty: 2 }]
  },
  {
    _id: 110, customerId: "u5", status: "paid",
    region: "south", total: 130,
    createdAt: ISODate("2026-11-12T11:00:00Z"),
    items: [{ sku: "B", qty: 1 }]
  },
  {
    _id: 111, customerId: "u4", status: "paid",
    region: "north", total: 110,
    createdAt: ISODate("2026-11-13T08:00:00Z"),
    items: [{ sku: "A", qty: 1 }]
  },
  {
    _id: 112, customerId: "u5", status: "pending",
    region: "south", total: 60,
    createdAt: ISODate("2026-11-13T09:00:00Z"),
    items: [{ sku: "C", qty: 1 }]
  }
])
```

Thêm collection nhỏ để minh họa join:

```javascript
db.customers.insertMany([
  { _id: "u1", name: "An", tier: "gold" },
  { _id: "u2", name: "Bình", tier: "silver" },
  { _id: "u3", name: "Chi", tier: "gold" },
  { _id: "u4", name: "Dũng", tier: "silver" },
  { _id: "u5", name: "Em", tier: "bronze" }
])
```

Từ dữ liệu trên:

| Nhóm đơn | Số document | Tổng tiền `total` |
| --- | ---: | ---: |
| `paid` | 8 | 1.460 |
| `pending` | 3 | 230 |
| `refunded` | 1 | 70 |
| `paid` và `region: "north"` | 4 | 690 |
| `paid` và `region: "south"` | 4 | 770 |

**Lưu ý:** Bộ dữ liệu nhỏ thích hợp để kiểm tra ngữ nghĩa nhưng **không đại diện cho hiệu năng production**. Với vài document, `COLLSCAN` có thể rất rẻ và query planner có thể không chọn index dù index tồn tại. Không suy ra số `keysExamined` hoặc thời gian chạy cụ thể từ những ví dụ này.

Chỉ chạy các lệnh `insertMany()` một lần trên collection trống; chạy lặp với cùng `_id` có thể gặp duplicate key. Không xóa dữ liệu quan trọng để chạy lại bài.

## 3. Gọi `explain` cho một aggregation pipeline

Cách trực quan trong `mongosh` là dùng explainable collection:

```javascript
const pipeline = [
  { $match: { status: "paid", region: "north" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 },
  { $project: { _id: 1, customerId: 1, total: 1, createdAt: 1 } }
];

db.orders.explain("queryPlanner").aggregate(pipeline);
db.orders.explain("executionStats").aggregate(pipeline);
db.orders.explain("allPlansExecution").aggregate(pipeline);
```

Ba mức verbosity có vai trò khác nhau:

| Verbosity | Thông tin chính | Khi nào dùng? |
| --- | --- | --- |
| `queryPlanner` | Kế hoạch thắng, index, các kế hoạch không được chọn, cấu trúc tối ưu | Muốn hiểu đường truy cập dữ liệu và cách optimizer tổ chức truy vấn |
| `executionStats` | Thêm số liệu thực thi của kế hoạch thắng và các stage được báo cáo | Muốn biết xem xét bao nhiêu key/document, số kết quả và dấu hiệu chi phí |
| `allPlansExecution` | Thêm thống kê giai đoạn thử nghiệm ứng viên khi có nhiều kế hoạch | Muốn điều tra quá trình lựa chọn giữa các kế hoạch cạnh tranh |

`allPlansExecution` **không** có nghĩa mọi kế hoạch ứng viên đều đã được thực thi đến hết dữ liệu. Những số liệu ứng viên chủ yếu phản ánh **giai đoạn thử nghiệm lựa chọn kế hoạch**, còn thống kê hoạt động đầy đủ liên quan kế hoạch thắng trong lần giải thích.

### Gọi bằng database command

Khi cần biểu diễn trực tiếp command (hữu ích cho Java Driver):

```javascript
db.runCommand({
  explain: {
    aggregate: "orders",
    pipeline: [
      { $match: { status: "paid" } },
      { $group: { _id: "$region", totalAmount: { $sum: "$total" } } }
    ],
    cursor: {}
  },
  verbosity: "executionStats"
})
```

Lệnh chạy trên **database hiện tại** và trả tài liệu giải thích, không trả các dòng báo cáo như một lệnh `aggregate()` thông thường. Với phân tích hiệu năng, cần dùng pipeline giống query thật: cùng filter, sort, projection, limit, collation và các tùy chọn có liên quan.

### Tại sao không chỉ dùng `explain()` cho `find()`?

Một aggregation có thể:

```javascript
[
  { $match: { status: "paid" } },
  { $unwind: "$items" },
  { $group: { _id: "$items.sku", qty: { $sum: "$items.qty" } } },
  { $sort: { qty: -1 } }
]
```

`find({status:"paid"}).explain()` chỉ cho biết truy vấn lấy các đơn `paid` như thế nào. Nó **không mô tả chi phí** mở rộng items, tính tổng theo SKU và sắp xếp nhóm. Để hiểu pipeline thực tế, hãy chạy `explain` trên **chính aggregation pipeline**.

## 4. Đọc cấu trúc kết quả `explain` của aggregation

Tùy phiên bản MongoDB, cấu hình server và loại pipeline, tài liệu explain có thể xuất hiện ở các dạng khác nhau.

**Dạng có các stage aggregation tường minh:**

```javascript
// Sơ đồ minh họa vị trí các phần, không phải output thực tế
{
  stages: [
    {
      $cursor: {
        queryPlanner: {
          winningPlan: { /* cây kế hoạch truy cập collection */ }
        },
        executionStats: { /* có ở verbosity tương ứng */ }
      }
    },
    { $group: { /* stage đã được biểu diễn trong explain */ } },
    { $sort: { /* thông tin stage và chỉ số, nếu được báo */ } }
  ]
}
```

**Dạng có query planner ở cấp cao:**

```javascript
// Sơ đồ minh họa
{
  queryPlanner: {
    winningPlan: {
      queryPlan: { /* các stage như IXSCAN, GROUP hoặc EQ_LOOKUP */ },
      slotBasedPlan: { /* khi phù hợp với SBE */ }
    }
  },
  executionStats: {
    nReturned: 0,
    totalKeysExamined: 0,
    totalDocsExamined: 0,
    executionStages: { /* chi tiết thực thi */ }
  }
}
```

Các giá trị `0` trong sơ đồ chỉ là placeholder cho thấy kiểu trường, **không phải số đo**. Một số pipeline được đẩy xuống query execution engine, có thể xuất hiện trong cây `winningPlan`; các pipeline khác có `stages` ở ngoài. Với **slot-based execution engine (SBE)**, cấu trúc còn có thể chứa `queryPlan`, `slotBasedPlan` và những stage khác với classic engine.

Không nên xây script giả định mọi explain của aggregation đều có đường dẫn cố định `result.queryPlanner.winningPlan.stage`. Cần kiểm tra loại truy vấn, version, phạm vi sharding và nơi MongoDB đặt phần `$cursor`/`executionStats`.

### Những thành phần cần nhận diện

| Thành phần | Ý nghĩa quan sát | Lưu ý |
| --- | --- | --- |
| `$cursor` | Phần lấy document đầu vào từ collection | Thường chứa planner và execution metrics của thao tác đọc |
| `winningPlan` | Kế hoạch MongoDB chọn trong lần explain | Có thể dùng nhiều dạng cây tùy query engine |
| `rejectedPlans` | Các kế hoạch ứng viên không được chọn | Không có nghĩa chúng sai hoặc hỏng |
| `COLLSCAN` | Quét collection | Đôi khi hợp lý nếu tập dữ liệu nhỏ hoặc điều kiện ít chọn lọc |
| `IXSCAN` | Duyệt index | Cần xem index name/bounds và keys examined |
| `FETCH` | Lấy document gốc | Có thể cần vì index không chứa mọi field |
| `SORT` | Sắp xếp trong kế hoạch | Cần xem có index hỗ trợ thứ tự hay không |
| `GROUP` hoặc `$group` | Xử lý gom nhóm | Có thể thấy ở SBE hay các stage aggregation |
| `EQ_LOOKUP` hoặc `$lookup` | Join dữ liệu | Tên và nội dung tùy kế hoạch/phiên bản |
| `nReturned` | Số kết quả của phần thực thi được báo | Xác định phạm vi: cursor hay toàn pipeline |
| `totalKeysExamined` | Số khóa index đã xem | Có thể cao dù kết quả ít |
| `totalDocsExamined` | Số document được xem xét | Có thể bằng 0 cho covered query phù hợp |
| `executionTimeMillis` | Thời gian thực thi được báo | Không tương đương đầy đủ với latency API |

Khi nhìn một pipeline `$match → $group`, đừng mặc định `nReturned` của **một `$cursor` bên trong explain** chính là số nhóm cuối cùng. Cursor có thể trả 8 đơn vào `$group`, nhưng `$group` chỉ trả 2 dòng tổng hợp theo vùng.

## 5. Các chỉ số `executionStats` cần đọc cùng nhau

Ví dụ một truy vấn giả định trả 10 kết quả:

```text
Kế hoạch A:
  nReturned          = 10
  totalKeysExamined  = 12
  totalDocsExamined  = 10

Kế hoạch B:
  nReturned          = 10
  totalKeysExamined  = 250000
  totalDocsExamined  = 50000
```

Kế hoạch A đi qua ít dữ liệu hơn để trả cùng số kết quả. Nhưng chưa thể tuyên bố A luôn nhanh trong mọi điều kiện, vì còn phải xét sort, group, dữ liệu trong cache, kích thước document và các công việc sau cursor.

Đối với aggregation có tính tổng:

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "paid" } },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } }
])
```

Bộ dữ liệu mẫu có 8 document `paid`, nhưng output cuối là 2 nhóm `north` và `south`. Một stage đầu vào cần xử lý 8 document để tính đủ doanh thu; vì vậy **số examined lớn hơn số nhóm trả về** không tự chứng minh pipeline kém hiệu quả.

### Khi giải thích chênh lệch examined/returned

- **`$match` rất chọn lọc:** ít document qua stage sau; index phù hợp có thể giảm reads.
- **`$group` gộp nhiều dòng:** số nhóm trả về nhỏ hơn nhiều số document phải xử lý là bình thường.
- **`$unwind` mở rộng dòng:** số dòng sau unwind có thể nhiều hơn đầu vào.
- **`$lookup` hoặc `$facet`:** có công việc bổ sung không thể suy ra chỉ bằng đếm output của cursor ngoài.
- **`$sort` và `$skip`:** có thể cần xem nhiều dữ liệu trước khi trả vài kết quả.
- **Covered query:** có thể duyệt index mà `totalDocsExamined = 0`, nhưng chưa chắc cả pipeline nhẹ.

Hãy đọc **tên stage, số lượng ở từng bước và loại công việc** trước khi kết luận.

## 6. Bước tối ưu đầu tiên: lọc sớm bằng `$match`

Giả sử cần danh sách đơn đã thanh toán tại miền Bắc, mới nhất trước:

```javascript
db.orders.aggregate([
  { $match: { status: "paid", region: "north" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 },
  { $project: { _id: 1, customerId: 1, total: 1 } }
])
```

Ở dữ liệu mẫu, `$match` giảm 12 đơn xuống 4 đơn; `$sort` sắp những đơn này; `$limit: 3` trả các ID **111, 109, 104**.

### Hai cách viết có thể tương đương

```javascript
// Cách A: lọc trước sort
[
  { $match: { status: "paid" } },
  { $sort: { createdAt: -1, _id: -1 } }
]

// Cách B: sort trước filter độc lập
[
  { $sort: { createdAt: -1, _id: -1 } },
  { $match: { status: "paid" } }
]
```

Nếu không có `$limit`/`$skip` xen giữa và bộ lọc không phụ thuộc vào một field vừa được tính sau, hai chuỗi này có thể có cùng kết quả logic; optimizer có thể **đẩy `$match` lên trước `$sort`**. Nhưng không nên dựa vào đó để giữ pipeline viết khó đọc: mô tả ý định lọc sớm giúp người đọc và người vận hành hiểu rõ hơn.

### Không phải mọi `$match` đều đẩy lên được

Ví dụ phải tính `highValue` từ `total` trước:

```javascript
db.orders.aggregate([
  {
    $set: {
      highValue: { $gte: ["$total", 200] }
    }
  },
  { $match: { highValue: true } },
  { $project: { _id: 1, total: 1, highValue: 1 } }
])
```

`highValue` **chưa tồn tại** trên document gốc. Nếu tự chuyển `$match: {highValue:true}` lên trước `$set`, kết quả có thể rỗng hoặc sai.

Nếu biểu thức chỉ đại diện cho điều kiện trên field gốc, có thể **viết lại tương đương theo điều kiện nguồn**:

```javascript
db.orders.aggregate([
  { $match: { total: { $gte: 200 } } },
  { $project: { _id: 1, total: 1 } }
])
```

Với dữ liệu mẫu, hai truy vấn dùng điều kiện `total >= 200` và phép tính tương ứng đều nhằm chọn những đơn có tổng 200 trở lên; khi đưa vào hệ thống thật cần xét thêm trường hợp null, sai kiểu và các biểu thức phức tạp.

### Optimizer có thể tách `$match` theo sự phụ thuộc

```javascript
db.orders.aggregate([
  {
    $addFields: {
      isLarge: { $gte: ["$total", 200] }
    }
  },
  {
    $match: {
      status: "paid",
      isLarge: true
    }
  }
])
```

Điều kiện `status: "paid"` không phụ thuộc `isLarge`, nên optimizer có thể đưa điều kiện này lên sớm hơn, trong khi điều kiện `isLarge` phải đợi stage tính ra nó. Explain có thể thể hiện bộ lọc đã được **tách hoặc dời**. Một stage nguồn không nhất thiết tương ứng một stage thực thi.

## 7. Tận dụng index cho `$match` và `$sort`

Khi pipeline bắt đầu bằng filter và sort trên field gốc, index có thể giảm đáng kể công việc:

```javascript
db.orders.createIndex(
  { status: 1, region: 1, createdAt: -1, _id: -1 },
  { name: "idx_status_region_created_id" }
)
```

Chạy explain:

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "paid", region: "north" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 },
  { $project: { _id: 1, customerId: 1, total: 1 } }
])
```

Index này có hai field equality (`status`, `region`) và hai field theo thứ tự sort. Nếu query planner dùng index phù hợp, MongoDB có thể tìm vùng khóa rồi đọc theo thời gian giảm dần, tránh một bước sort bổ sung trên nhiều document.

Tuy nhiên, index chỉ mang tính **ứng viên**. Collection mẫu rất nhỏ nên planner có thể chọn quét collection. Hãy quan sát `IXSCAN`/`COLLSCAN`, tên index, bounds, `SORT`, `totalKeysExamined` và `totalDocsExamined` từ explain thật.

### Vì sao `$project` không mặc nhiên biến query thành covered?

Projection:

```javascript
{ $project: { _id: 1, customerId: 1, total: 1 } }
```

cần `customerId` và `total`, nhưng index ở trên chỉ có `status`, `region`, `createdAt`, `_id`. Máy chủ có thể phải **FETCH** document gốc để lấy những field còn thiếu. Nếu một truy vấn được phục vụ hoàn toàn từ index thì có thể thấy `totalDocsExamined = 0` ở phần đọc tương ứng; điều đó không được bảo đảm chỉ từ việc có `$project`.

Đánh đổi giữa mở rộng compound index để covered query và chi phí dung lượng/ghi phải dựa trên workload. Không nên thêm mọi field vào index chỉ để phục vụ một báo cáo ít được gọi.

### Thứ tự field trong index quan trọng

```javascript
{ status: 1, region: 1, createdAt: -1, _id: -1 }
```

khác với:

```javascript
{ createdAt: -1, status: 1, region: 1, _id: -1 }
```

Với equality trên `status` và `region`, thứ tự đầu thường giúp thu hẹp vùng khóa trước khi đọc theo sort. Đây là minh họa cho hướng dẫn **Equality – Sort – Range (ESR)**. Thứ tự thực tế còn phụ thuộc điều kiện range, tính chọn lọc, các index đã có và kế hoạch được chọn.

## 8. `$sort` và `$limit`: tối ưu top-K nhưng không đổi ngữ nghĩa

Với yêu cầu “ba đơn đã thanh toán mới nhất”, thứ tự đúng:

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 }
])
```

Theo dữ liệu mẫu, kết quả ID là **111, 110, 109**.

Ngược lại:

```javascript
// KHÁC NGỮ NGHĨA: giới hạn trước khi sắp xếp
db.orders.aggregate([
  { $match: { status: "paid" } },
  { $limit: 3 },
  { $sort: { createdAt: -1, _id: -1 } }
])
```

Stage `$limit: 3` chọn ba document đầu theo thứ tự đầu vào hiện tại (thứ tự này không được đảm bảo khi không có `$sort`). Stage sau chỉ sắp lại **ba document đã chọn**; nó không thể tìm ba đơn mới nhất của toàn bộ tập `paid`.

### Optimizer có thể gộp sort và limit

Với:

```javascript
[
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 }
]
```

MongoDB có thể tối ưu thành thao tác sort có giới hạn **top-K**, giữ tối đa lượng dữ liệu trung gian cần thiết để chọn ba kết quả đầu, thay vì lưu toàn bộ kết quả đã sort theo cùng một cách. Điều kiện là không có stage trung gian làm thay đổi số document theo cách cản trở phép gộp.

Một ví dụ trên tập lớn:

```text
Nguồn 2.000.000 document
          |
          v
      $sort theo key
          |
          v
       $limit 20

Optimizer có thể sử dụng sort có giới hạn 20
(khi phù hợp), giảm trạng thái sort trung gian.
```

**Nhưng top-K không có nghĩa server chỉ đọc 20 document.** Nếu không có index hỗ trợ sort, máy chủ vẫn có thể phải xem phần lớn tập đầu vào để biết đâu là 20 document đứng đầu.

### Sort có `$skip` và `$limit`

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $skip: 3 },
  { $limit: 3 }
])
```

MongoDB có thể tối ưu sort/skip/limit thành kế hoạch cần xét **ít nhất `skip + limit` phần tử dẫn đầu** trong thứ tự kết quả rồi bỏ qua `skip`; ở ví dụ là 6 vị trí. Không thể chuyển `$limit: 3` lên trước `$skip: 3` và giữ nguyên kết quả.

Phân trang offset sâu vẫn có chi phí: `$skip: 100000` thường đòi hỏi đi qua nhiều mục trước khi trả vài kết quả. Với luồng “xem tiếp” rất sâu, có thể cân nhắc phân trang dựa trên khóa sắp xếp (keyset pagination) thay vì offset lớn.

## 9. `$project`, `$set` và `$unset`: giảm dữ liệu nhưng giữ field phụ thuộc

Giảm kích thước document sớm **có thể** hữu ích khi phía sau có stage cần giữ nhiều dữ liệu trung gian, nhưng phải giữ những field được dùng trong filter, sort, group hoặc join.

Ví dụ cần tổng tiền theo vùng:

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  { $project: { region: 1, total: 1, _id: 0 } },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$total" }
    }
  }
])
```

Projection chỉ giữ `region` và `total`, đủ để tính kết quả. Dữ liệu mẫu tạo hai nhóm: `north = 690`, `south = 770`.

### Ví dụ sai vì bỏ field quá sớm

```javascript
db.orders.aggregate([
  { $project: { region: 1, total: 1, _id: 0 } },
  { $match: { status: "paid" } },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } }
])
```

Ở ngữ nghĩa pipeline nguồn, `status` đã bị loại trước `$match`. Vì thế điều kiện `status: "paid"` không còn thấy field và có thể loại hết dữ liệu; **đừng mong optimizer sửa một pipeline vốn đã khác ngữ nghĩa**.

### Không cần tự project sớm trong mọi trường hợp

MongoDB có thể tự thực hiện **projection optimization**, chỉ mang những field cần thiết qua các bước liên quan. Vì vậy thêm hàng loạt `$project` đầu pipeline không phải lúc nào cũng tăng tốc; nó có thể làm code dài và gây lỗi khi về sau thêm điều kiện cần field đã bị loại.

Hãy tập trung vào những trường hợp có tác dụng rõ:

- Stage `$group` với `$push: "$$ROOT"` có nguy cơ giữ document lớn.
- `$lookup` trả về nhiều field của collection ngoại mà báo cáo không cần.
- Pipeline phải truyền các document lớn qua nhiều stage nặng.
- Cần loại bỏ field nhạy cảm khỏi kết quả trả về API.

`$project` ảnh hưởng hình dạng dòng dữ liệu; nó không làm document trong collection nhỏ đi và không tự bảo đảm index coverage.

### `$match` sau projection có thể được đẩy lên

Nếu projection giữ nguyên `status`:

```javascript
[
  { $project: { status: 1, total: 1 } },
  { $match: { status: "paid" } }
]
```

optimizer có thể đưa điều kiện `status` lên trước projection. Nếu projection **đổi tên hoặc tính lại** giá trị mà filter sử dụng, khả năng di chuyển phụ thuộc quan hệ giữa các biểu thức. Xem explain để phân biệt stage nguồn với các bước được tối ưu.

## 10. `$group`: lọc trước khi nhóm và chỉ nhóm ở độ hạt cần thiết

`$group` gom nhiều document thành các nhóm với accumulator. Ví dụ thống kê doanh thu đã thanh toán theo vùng:

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  {
    $group: {
      _id: "$region",
      orderCount: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  },
  { $sort: { revenue: -1 } }
])
```

Kết quả:

```javascript
{ _id: "south", orderCount: 4, revenue: 770 }
{ _id: "north", orderCount: 4, revenue: 690 }
```

**Tối ưu quan trọng:** nếu chỉ quan tâm đơn `paid`, đặt `$match` trước `$group` để giảm đầu vào và có cơ hội dùng index trên `status`.

### `$match` trên kết quả nhóm phải đứng sau `$group`

Yêu cầu: chỉ lấy vùng có tổng doanh thu `paid` lớn hơn 700:

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$total" }
    }
  },
  { $match: { revenue: { $gt: 700 } } }
])
```

Kết quả chỉ có vùng `south`, doanh thu 770. Không thể chuyển `$match: {revenue:{$gt:700}}` lên trước group, vì `revenue` chỉ tồn tại **sau khi cộng tất cả các document trong nhóm**.

### Thứ tự `$limit` và `$group` thay đổi câu hỏi

```javascript
// Tổng theo vùng trên TẤT CẢ đơn paid
[
  { $match: { status: "paid" } },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } },
  { $sort: { revenue: -1 } },
  { $limit: 1 }
]
```

nghĩa là “vùng nào có doanh thu cao nhất?”; khác với:

```javascript
// Tổng theo vùng chỉ trên 3 đơn paid mới nhất
[
  { $match: { status: "paid" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } }
]
```

Trong pipeline thứ hai, `$limit` **thay đổi tập đầu vào** của group. Đây là sự thay đổi nghiệp vụ hợp lệ nếu thực sự chỉ muốn nhóm ba đơn mới nhất, nhưng **không phải** phép tối ưu tương đương cho báo cáo tổng trên tất cả đơn.

### Số nhóm và bộ nhớ

Một nhóm cho mỗi `region` có thể rất ít trạng thái. Một nhóm cho mỗi `customerId + timestamp + sku` có thể tạo rất nhiều nhóm. Accumulator như `$push` có thể làm trạng thái mỗi nhóm rất lớn. Đó là lý do cần đặt đúng độ hạt, lọc sớm và tránh gom những field/array không cần thiết.

MongoDB có thể báo các thông tin như `usedDisk`, `spills`, `spilledRecords`, `maxAccumulatorMemoryUsageBytes` hoặc các chỉ số bộ nhớ khác **khi phiên bản và stage cung cấp**. Nếu có spill, đây là dấu hiệu nên xem lại độ hạt nhóm, input và bộ nhớ; cho phép spill ra đĩa không tự khiến pipeline nhanh hơn.

## 11. `$unwind`: chú ý việc nhân số dòng trước khi làm việc nặng

`$unwind` tách mỗi phần tử mảng thành một dòng pipeline. Với document:

```javascript
{ _id: 101, items: [{sku:"A",qty:2},{sku:"B",qty:1}] }
```

sau `$unwind: "$items"`, document này đóng góp **hai dòng**. Vì thế các stage sau có thể phải xử lý nhiều dòng hơn số document nguồn.

### Lọc đơn trước, rồi tách items

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      units: { $sum: "$items.qty" }
    }
  },
  { $sort: { units: -1, _id: 1 } }
])
```

Ở đây chỉ các đơn `paid` được mở rộng thành các dòng item. Nếu `$unwind` đứng trước `$match` và không có tối ưu phù hợp, nó có thể mở rộng cả những đơn `pending` hoặc `refunded` rồi mới bỏ.

### Hai điều kiện `$match` không hẳn có cùng ý nghĩa

```javascript
// 1. Lọc đơn có chứa SKU A, rồi unwind TẤT CẢ items của đơn đó
db.orders.aggregate([
  { $match: { "items.sku": "A" } },
  { $unwind: "$items" },
  { $project: { _id: 1, "items.sku": 1 } }
])
```

Với đơn `101` chứa A và B, kết quả vẫn có **cả A lẫn B**, vì filter kiểm tra document **trước** khi unwind.

```javascript
// 2. Unwind trước, chỉ giữ dòng item có SKU A
db.orders.aggregate([
  { $unwind: "$items" },
  { $match: { "items.sku": "A" } },
  { $project: { _id: 1, "items.sku": 1 } }
])
```

Lần này đơn `101` chỉ đóng góp **dòng item A**. Hai pipeline có ý nghĩa khác nhau; tự ý đổi vị trí để “lọc sớm hơn” có thể thay đổi output.

Nếu mục tiêu là chỉ lấy dòng A nhưng vẫn muốn giảm đầu vào ban đầu, có thể dùng **hai bộ lọc**:

```javascript
db.orders.aggregate([
  { $match: { "items.sku": "A" } },
  { $unwind: "$items" },
  { $match: { "items.sku": "A" } }
])
```

Bộ lọc đầu loại các đơn không có A; bộ lọc sau chỉ giữ các phần tử A. Cách này có thể hữu ích khi có multikey index hỗ trợ bộ lọc đầu và dữ liệu chứa nhiều item, nhưng cần đo lường bằng explain thay vì cho rằng luôn tốt hơn.

### Giá trị mảng rỗng và `preserveNullAndEmptyArrays`

`$unwind: "$items"` mặc định không tạo dòng cho array rỗng, field `null` hoặc field thiếu. Khi dùng:

```javascript
{
  $unwind: {
    path: "$items",
    preserveNullAndEmptyArrays: true
  }
}
```

MongoDB giữ lại những document thiếu phần tử để unwind theo ngữ nghĩa tương ứng. Thay đổi tùy chọn này có thể làm số dòng và kết quả group khác; hãy chọn theo yêu cầu nghiệp vụ chứ không đơn thuần để giữ tổng đếm.

## 12. `$lookup`: giảm số document trước khi join

`$lookup` kết hợp dữ liệu từ một collection khác. Nếu pipeline chỉ cần thông tin khách hàng của ba đơn `paid` mới nhất, việc join tất cả đơn rồi mới giới hạn thường không phải cách diễn đạt tốt nhất.

### Truy vấn danh sách: giới hạn trước join nếu đúng yêu cầu

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  {
    $project: {
      _id: 1,
      total: 1,
      createdAt: 1,
      customer: 1
    }
  }
])
```

Ở đây chỉ ba đơn mới nhất được đưa vào lookup. `customers._id` đã có unique index mặc định trong collection thông thường, thích hợp cho equality join theo khóa khách hàng. Với dữ liệu mẫu, ba đơn là `111`, `110`, `109`.

**Nhưng cần phân biệt một yêu cầu khác:** “ba đơn mới nhất của **khách hàng hạng gold**”. Nếu chỉ lọc `customer.tier: "gold"` **sau** `$limit: 3`, bạn có thể bỏ sót đơn gold đứng thứ tư, thứ năm, v.v. Khi tiêu chí chọn top 3 phụ thuộc thông tin từ collection ngoại, thứ tự lookup/filter/limit phải được thiết kế theo đúng ý nghĩa.

Ví dụ đúng ý định “ba đơn `paid` mới nhất của khách hàng gold”:

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $unwind: "$customer" },
  { $match: { "customer.tier": "gold" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 }
])
```

Kết quả dựa trên đơn hàng của `u1`, `u3`, với ID `108`, `106`, `104` (theo createdAt giảm dần). Một chiến lược khác có thể lọc từ phía khách hàng hạng gold hoặc thiết kế lại phép join tùy đặc điểm dữ liệu.

### Explain cho lookup

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "paid" } },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  }
])
```

Ở những phiên bản/kiểu kế hoạch phù hợp, thông tin `$lookup` có thể có `indexesUsed`, `totalDocsExamined`, `totalKeysExamined`, số lượt tìm kiếm hoặc các stage như `EQ_LOOKUP`. Đường dẫn JSON và tên trường **không đồng nhất ở mọi phiên bản**.

Không chỉ xem index trên `orders`: với join, **index của collection `customers` cũng quan trọng**. Nếu join vào một field ngoại không có index thích hợp, MongoDB có thể phải làm nhiều công việc hơn đáng kể.

### Optimizer có thể gộp lookup, unwind và match

Một chuỗi:

```javascript
[
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $unwind: "$customer" },
  { $match: { "customer.tier": "gold" } }
]
```

trong những trường hợp phù hợp có thể được optimizer kết hợp để tránh dựng các array trung gian không cần thiết hoặc đẩy điều kiện vào xử lý lookup. Explain có thể hiển thị thông tin như `unwinding`, pipeline nội bộ hoặc một dạng join khác. Đừng kết luận stage bị “mất” chỉ vì không thấy `$unwind` tách riêng trong explain.

Tuy nhiên, **không phải mọi `$lookup` đều được tối ưu như nhau**, nhất là lookup có pipeline tính toán, điều kiện phức tạp, sharding hoặc schema khác. Khi tối ưu, cần kiểm tra query shape và phiên bản máy chủ.

## 13. `$facet`: lọc chung trước khi tách nhiều báo cáo

`$facet` cho phép chạy nhiều pipeline con trên cùng một tập document đầu vào. Ví dụ màn hình vừa cần tổng doanh thu theo vùng vừa cần số lượng đơn theo trạng thái:

```javascript
db.orders.aggregate([
  {
    $match: {
      createdAt: {
        $gte: ISODate("2026-11-10T00:00:00Z")
      }
    }
  },
  {
    $facet: {
      byRegion: [
        {
          $group: {
            _id: "$region",
            orderCount: { $sum: 1 },
            total: { $sum: "$total" }
          }
        }
      ],
      byStatus: [
        {
          $group: {
            _id: "$status",
            orderCount: { $sum: 1 }
          }
        }
      ]
    }
  }
])
```

Đặt điều kiện chung `$match` **trước `$facet`** giúp giới hạn tập document được đưa vào mọi pipeline con và có cơ hội dùng index cho điều kiện đầu vào.

Ngược lại, nếu đặt `$facet` là stage đầu tiên của pipeline, thông thường nó không thể tự sử dụng index để lọc collection theo các điều kiện nằm bên trong facet. Tuy nhiên khi các stage trước facet (`$match`, `$sort`) đã dùng index, facet có thể nhận luồng đầu vào từ quá trình đó mà **không nhất thiết gây một collection scan mới**.

### Không đẩy filter riêng của một nhánh ra ngoài một cách vô điều kiện

Nếu `byStatus` cần thống kê tất cả đơn nhưng `byRegion` chỉ cần đơn `paid`, việc đặt `$match:{status:"paid"}` **trước facet** sẽ làm cả hai nhánh chỉ thấy đơn `paid`. Điều đó đổi nghiệp vụ.

Khi mỗi nhánh có điều kiện riêng, để điều kiện trong nhánh tương ứng hoặc thiết kế pipeline hai tầng, thay vì đẩy tất cả filter lên trước.

`$facet` còn có giới hạn bộ nhớ/kích thước đầu ra đặc thù; `allowDiskUse` không phải cách vượt qua mọi giới hạn này. Pipeline nhiều nhánh lớn nên được đo đạc và cân nhắc tách thành nhiều truy vấn nếu phù hợp với yêu cầu nhất quán và hiệu năng.

## 14. Nhận diện stage nặng: blocking, memory và disk spill

Một số stage cần tích lũy đáng kể dữ liệu trước khi hoàn tất đầu ra:

| Stage | Chi phí thường gặp | Hướng xem xét |
| --- | --- | --- |
| `$sort` | Sắp xếp nhiều document, có thể cần bộ nhớ lớn | Index phù hợp, filter sớm, top-K nếu có limit |
| `$group` | Giữ trạng thái cho nhiều khóa nhóm/accumulator | Giảm số document đầu vào và độ hạt nhóm |
| `$setWindowFields` | Cần sắp xếp/giữ cửa sổ theo partition/order | Lọc trước nếu đúng nghĩa, index theo partition/sort khi phù hợp |
| `$lookup` | Truy xuất và kết hợp collection ngoại | Lọc đầu vào, index foreign key, kiểm soát số match |
| `$unwind` | Một document có thể thành nhiều dòng | Tránh unwind quá sớm nếu chưa cần |
| `$facet` | Nhiều pipeline con trên chung đầu vào | Filter chung sớm, tránh các nhánh quá nặng |

Các phiên bản MongoDB có giới hạn bộ nhớ cho một số stage và có thể ghi dữ liệu trung gian ra đĩa khi được cho phép. Tùy phiên bản, thông số cấu hình và loại stage, explain/profiler có thể báo dấu hiệu như `usedDisk`, `spills`, `spilledDataStorageSize` hoặc bộ đếm tương đương.

Khi cần, có thể chạy pipeline với tùy chọn `allowDiskUse`:

```javascript
db.orders.aggregate(
  [
    { $match: { status: "paid" } },
    { $group: { _id: "$region", total: { $sum: "$total" } } },
    { $sort: { total: -1 } }
  ],
  { allowDiskUse: true }
)
```

**Cho phép sử dụng đĩa không phải phép tối ưu tự động.** Spill thường tốn I/O, và không loại bỏ các giới hạn về kích thước BSON của một document kết quả hay các giới hạn đặc thù của stage.

### Quy tắc về `$setWindowFields`

Nếu một pipeline tính tổng lũy kế theo khách hàng:

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  {
    $setWindowFields: {
      partitionBy: "$customerId",
      sortBy: { createdAt: 1, _id: 1 },
      output: {
        runningTotal: {
          $sum: "$total",
          window: { documents: ["unbounded", "current"] }
        }
      }
    }
  }
])
```

thì lọc `$match:{status:"paid"}` **trước** window nghĩa là tổng lũy kế chỉ tính các đơn paid; lọc **sau** window nghĩa là cửa sổ có thể đã tính trên cả pending/refunded rồi mới bỏ các dòng đó khỏi kết quả. Chuyển vị trí filter **có thể đổi giá trị** dù cả hai pipeline cuối cùng chỉ hiển thị đơn paid.

`$setWindowFields` chỉ có trên các phiên bản MongoDB hỗ trợ. Nếu môi trường chưa hỗ trợ, cần phương án báo cáo tương ứng và không nên sao chép cú pháp mà không kiểm tra server version.

## 15. So sánh pipeline trước và sau thay đổi một cách có căn cứ

Khi nhận thấy aggregation chậm, hãy so sánh có kiểm soát thay vì sửa nhiều yếu tố cùng lúc.

**Ví dụ baseline về doanh thu vùng:**

```javascript
const baseline = [
  { $match: { status: "paid" } },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$total" }
    }
  },
  { $sort: { revenue: -1 } }
];

db.orders.explain("executionStats").aggregate(baseline);
```

**Một phiên bản tối ưu khi chỉ cần vùng `north`:**

```javascript
const filtered = [
  { $match: { status: "paid", region: "north" } },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$total" }
    }
  }
];

db.orders.explain("executionStats").aggregate(filtered);
```

Hai pipeline trên **không trả cùng tập kết quả**: baseline trả cả north và south, còn filtered chỉ trả north. Chúng minh họa lợi ích lọc sớm **khi yêu cầu nghiệp vụ đã thay đổi hoặc vốn chỉ cần north**, chứ không phải một benchmark tương đương của hai cách viết.

Nếu cần so sánh **hai cách viết cho cùng yêu cầu**, dùng cùng filter, projection, sort và dữ liệu; ví dụ:

```javascript
const versionA = [
  { $match: { status: "paid", region: "north" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 }
];

const versionB = [
  { $sort: { createdAt: -1, _id: -1 } },
  { $match: { status: "paid", region: "north" } },
  { $limit: 3 }
];

db.orders.explain("executionStats").aggregate(versionA);
db.orders.explain("executionStats").aggregate(versionB);
```

Vì filter trong B đứng trước limit và độc lập với sort, optimizer có thể biến hai phiên bản thành kế hoạch rất giống nhau. Nếu số liệu khác, cần xem cache, index, query planner và điều kiện đo trước khi kết luận rằng chính thứ tự viết gây khác biệt.

### Những chỉ số nên ghi lại

| Chỉ số/bằng chứng | Lý do |
| --- | --- |
| Bộ lọc và giá trị tham số | Chọn lọc và phân bố dữ liệu tác động đến kế hoạch |
| Sort, limit, skip, projection | Thay đổi query shape và lượng công việc |
| Index có sẵn và `winningPlan` | Cho biết đường truy cập dữ liệu |
| `totalKeysExamined`, `totalDocsExamined` | Ước lượng phạm vi key/document đã xem |
| Stage `SORT`, `FETCH`, `GROUP`, `EQ_LOOKUP` | Xác định công việc đáng chú ý |
| Số dòng sau các stage quan trọng | Phát hiện `$unwind` nhân dòng hoặc `$group` thu nhỏ |
| Bộ nhớ/spill nếu có | Phát hiện stage trung gian quá lớn |
| Thời gian nhiều lần đo | Tránh kết luận từ một lần chạy chịu ảnh hưởng cache và tải |

Không dựa vào một con số `executionTimeMillis` đơn lẻ để tuyên bố API sẽ nhanh cùng mức đó. Thời gian ứng dụng còn có network, driver, BSON decoding, xử lý phía service và sự cạnh tranh tài nguyên production.

## 16. `explain` không phải ảnh chụp tuyệt đối của mọi request

MongoDB dùng query planning và có thể có **plan cache** cho những truy vấn tương tự. Theo hành vi giải thích kế hoạch, `explain` không sử dụng entry plan cache hiện có như một truy vấn thông thường và không tạo entry plan cache mới từ lần explain.

Vì vậy, `winningPlan` của explain phản ánh kế hoạch được chọn **trong lần explain đó**; không chứng minh tất cả request đang chạy của ứng dụng đều dùng đúng plan này. Khi sự chậm chạp chỉ xảy ra với một vài giá trị tham số hoặc vào giờ cao điểm, cần kết hợp explain với monitoring, profiler hoặc log truy vấn chậm theo quyền hạn và chính sách vận hành.

### Dùng `hint()` khi nghiên cứu index

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "paid", region: "north" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 }
], {
  hint: "idx_status_region_created_id"
})
```

Nếu phiên bản mongosh/driver hỗ trợ tùy chọn `hint` trong lệnh aggregation tương ứng, nó có thể giúp nghiên cứu kế hoạch dùng index nêu rõ. Tuy nhiên, hint thường áp dụng cho truy cập collection ban đầu, **không buộc mọi stage phía sau phải dùng index**; nó cũng không bảo đảm pipeline nhanh hơn.

Không ép hint cố định trong production chỉ dựa trên thử nghiệm nhỏ. Khi index bị xóa, schema/workload thay đổi hoặc dữ liệu trở nên lệch, hint có thể kém hiệu quả hay gây lỗi.

### Truy vấn trên sharded cluster

Trong môi trường sharding, explain có thể có phần riêng cho từng shard, router/merge và các bước sort/group phân tán. Cần xác định:

- Query có được **target** đến một shard nhờ shard key hay phải scatter-gather?
- Các stage nào chạy trên shard và stage nào chạy ở phần merge?
- Có trao đổi nhiều document giữa shard và router không?
- Stage group có được chia thành tổng hợp cục bộ rồi hợp nhất không?

Không cộng tùy tiện thống kê từ nhiều nhánh rồi coi chúng tương đương một standalone explain. Cấu trúc và phạm vi số liệu phụ thuộc phiên bản và loại pipeline.

## 17. Java MongoDB Sync Driver: gọi explain cho aggregation

Có thể dùng database command `explain` để nhận JSON/BSON mô tả pipeline từ Java:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.List;

public class AggregationExplainDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                client.getDatabase("mongo_aggregation_explain_lab");

            List<Document> pipeline = List.of(
                new Document("$match",
                    new Document("status", "paid")
                        .append("region", "north")),
                new Document("$sort",
                    new Document("createdAt", -1)
                        .append("_id", -1)),
                new Document("$limit", 3),
                new Document("$project",
                    new Document("_id", 1)
                        .append("customerId", 1)
                        .append("total", 1))
            );

            Document aggregateCommand =
                new Document("aggregate", "orders")
                    .append("pipeline", pipeline)
                    .append("cursor", new Document());

            Document explainCommand =
                new Document("explain", aggregateCommand)
                    .append("verbosity", "executionStats");

            Document explanation =
                database.runCommand(explainCommand);

            System.out.println(explanation.toJson());

            // Không giả định toàn bộ explain luôn có top-level
            // executionStats: aggregation có thể đặt thông tin
            // bên trong stages[].$cursor hoặc cấu trúc SBE khác.
            Document stats =
                explanation.get("executionStats", Document.class);
            if (stats != null) {
                System.out.println(
                    "keysExamined = " + stats.get("totalKeysExamined"));
                System.out.println(
                    "docsExamined = " + stats.get("totalDocsExamined"));
            }
        }
    }
}
```

Đoạn code cần MongoDB Java Sync Driver và Java có `List.of`. Connection string lấy từ biến môi trường `MONGODB_URI` để không ghi mật khẩu vào source.

Với những phiên bản driver có API `explain` trực tiếp trên `AggregateIterable`, cũng có thể dùng API đó và `ExplainVerbosity` tương ứng. Dùng `runCommand` trong bài này để thấy rõ command `aggregate`, `pipeline`, `cursor` và `verbosity`; không phải vì mọi môi trường bắt buộc dùng database command.

### Phân tích explain từ Java cần xử lý nhiều hình dạng

Một chương trình đọc thống kê nghiêm túc cần hỗ trợ các biến thể:

- `queryPlanner`/`executionStats` ở cấp cao.
- `stages` chứa `$cursor` và các stage aggregation khác.
- Cây classic hoặc `queryPlan`/`slotBasedPlan` của SBE.
- Phần riêng theo shard trong hệ phân tán.
- Tên trường và chỉ số stage khác nhau theo phiên bản.

Không parse một explain JSON được chụp ở máy development rồi khẳng định nó là schema cố định cho mọi server.

## 18. Bài tập thực hành với đáp án

### Bài 1. Explain đúng pipeline

Yêu cầu: xem thống kê thực thi cho các đơn `paid` tại `north`, mới nhất trước, tối đa ba đơn.

**Đáp án:**

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "paid", region: "north" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 }
])
```

ID kết quả logic khi chạy pipeline bình thường là `111`, `109`, `104`. Output của lệnh explain là **kế hoạch/thống kê**, không phải array ba document đó.

### Bài 2. Phát hiện phép đổi thứ tự sai

So sánh:

```javascript
// A
[
  { $match: { status: "paid" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 }
]

// B
[
  { $match: { status: "paid" } },
  { $limit: 3 },
  { $sort: { createdAt: -1, _id: -1 } }
]
```

**Đáp án:** A chọn ba đơn paid mới nhất từ toàn tập. B chọn ba đơn paid đầu vào trước rồi mới sắp chúng; tập ba đơn đó không được đảm bảo là mới nhất. Đây không phải thay đổi thứ tự hợp lệ khi muốn giữ kết quả.

### Bài 3. Đếm đúng số dòng khi unwind

Document đơn `101` có hai phần tử trong `items`: A và B. Tại sao `$unwind` rồi `$group` với `$sum: 1` có thể đếm 2 trong khi collection chỉ có một đơn `101`?

**Đáp án:** Sau `$unwind`, document 101 trở thành hai dòng pipeline. `$sum:1` đếm **dòng đầu vào của group**, không phải số document đơn hàng duy nhất. Nếu cần số đơn khác nhau chứa SKU, có thể gom các ID bằng `$addToSet` hoặc thiết kế phép đếm distinct phù hợp.

### Bài 4. Có thể đẩy `$match` lên trước `$group` không?

```javascript
[
  { $match: { status: "paid" } },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } },
  { $match: { revenue: { $gt: 700 } } }
]
```

**Đáp án:** Không thể tự đẩy `$match` theo `revenue` lên trước `$group` mà giữ ngữ nghĩa, vì `revenue` chỉ được tính từ tổng của các document sau group. Có thể lọc `status` trước group vì field này có ở document nguồn.

### Bài 5. Explain cho thấy `COLLSCAN`, có chắc index sai?

Trong collection mẫu 12 đơn, mặc dù đã tạo index theo `status, region, createdAt, _id`, explain vẫn hiển thị `COLLSCAN`. Có thể kết luận index vô dụng trên production không?

**Đáp án:** Không. Collection nhỏ khiến quét collection rất rẻ. Cần kiểm tra query shape, phân bố dữ liệu, `winningPlan`, số examined, sort và workload với quy mô thực tế trước khi kết luận. Index phù hợp không buộc planner phải chọn nó trong mọi trường hợp.

### Bài 6. Tối ưu join mà không đổi kết quả

Yêu cầu A: lấy ba đơn `paid` mới nhất rồi hiển thị thông tin khách hàng tương ứng. Yêu cầu B: lấy ba đơn `paid` mới nhất **của những khách hàng gold**.

**Đáp án:** Với A, có thể `$match → $sort → $limit → $lookup`, vì điều kiện top 3 không phụ thuộc dữ liệu khách hàng. Với B, cần kiểm tra tier trước khi chọn top 3: `$match paid → $lookup → $unwind → $match customer.tier → $sort → $limit` hoặc một cấu trúc tương đương có lọc khách hàng trước. Đưa `$limit` lên trước khi lọc gold có thể bỏ sót kết quả.

### Bài 7. Stage nào cần kiểm tra bộ nhớ?

Pipeline nhóm theo `customerId` với `$push: "$$ROOT"` trên hàng triệu document xuất hiện dấu hiệu spill và sử dụng nhiều RAM.

**Đáp án:** `$group` giữ trạng thái và mảng giá trị của các nhóm, có thể rất lớn. Nên cân nhắc bỏ `$push: "$$ROOT"` nếu không cần, project bớt field, lọc sớm, giảm độ hạt hoặc thay đổi cách tạo báo cáo. `allowDiskUse` có thể cho phép một số thao tác spill nhưng không loại bỏ chi phí hay giới hạn kích thước document kết quả.

### Bài 8. Vì sao explain không có `stages` như mong đợi?

Một pipeline aggregation đơn giản được explain trên máy A có `stages:[{$cursor:...},{$group:...}]`, nhưng máy B có `queryPlanner.winningPlan.queryPlan` ở cấp cao.

**Đáp án:** Cấu trúc explain thay đổi theo phiên bản, khả năng đẩy stage xuống query execution engine và việc dùng classic/SBE. Không nên kết luận explain thiếu dữ liệu chỉ vì đường dẫn JSON khác. Hãy đọc nội dung planner/stats ở nơi server thực sự báo cáo.

## 19. Quy trình thực tế khi tối ưu aggregation

Để tối ưu có căn cứ mà vẫn giữ kết quả chính xác, có thể áp dụng trình tự:

1. **Định nghĩa output kỳ vọng:** mỗi dòng trả về là gì, filter áp dụng trước hay sau group/window, `$limit` giới hạn document hay nhóm, có được phép mất dòng từ mảng rỗng không?
2. **Ghi lại pipeline gốc và query shape:** giữ nguyên tất cả stage, options và điều kiện lọc thực tế. Tránh tối ưu từ một truy vấn rút gọn không đại diện cho endpoint.
3. **Chạy `queryPlanner` để xem đường đọc dữ liệu:** index name, bounds, `COLLSCAN`, `IXSCAN`, `FETCH`, `SORT` và phần `$cursor`.
4. **Chạy `executionStats`:** đọc keys/docs examined, số dòng từng stage khi có, thời gian và dấu hiệu memory/spill; xác định stage đang đọc, nhân, gom hoặc sắp nhiều dữ liệu.
5. **Xem dependency giữa các stage:** đẩy `$match` độc lập lên trước, nhưng giữ filter trên field tính toán sau stage tạo field; không chuyển `$limit` qua group/unwind/lookup tùy ý.
6. **Cân nhắc index cho prefix `$match`/`$sort`:** chọn key order theo điều kiện equality, sort và range; không kỳ vọng index giải quyết trực tiếp mọi phép group/join.
7. **Giảm fan-out và trạng thái trung gian:** hạn chế unwind/join trên dữ liệu không cần thiết; không đẩy `$project` quá sớm khiến mất field; tránh `$push` những object lớn khi không cần.
8. **So sánh có kiểm soát:** xác nhận đầu ra tương đương khi yêu cầu không đổi, rồi đo trên dữ liệu đại diện với nhiều giá trị tham số và tình trạng cache/tải phù hợp.
9. **Theo dõi sau thay đổi:** nhìn cả latency ứng dụng, CPU, I/O, cache, dung lượng index, throughput ghi và các mẫu truy vấn khác; một index mới cũng có chi phí vận hành.

## 20. Kết luận

`explain` là công cụ quan sát **kế hoạch truy cập collection lẫn quá trình thực thi aggregation**. Khi đọc, đừng chỉ tìm chữ `IXSCAN` hay một con số thời gian; hãy lần theo dữ liệu từ `$match`, `$cursor`, `$sort`, `$group`, `$unwind`, `$lookup` tới kết quả cuối, đồng thời hiểu rằng optimizer có thể biến đổi cấu trúc stage.

Thứ tự stage tốt thường nhằm **loại dữ liệu không cần thiết càng sớm càng hợp lệ**, **giữ thứ tự phù hợp với index**, **giảm số dòng trước các stage tốn tài nguyên** và **tránh giữ dữ liệu trung gian quá lớn**. Nhưng tính đúng đắn luôn đi trước hiệu năng: lọc sau group không thể tự chuyển trước group nếu phụ thuộc kết quả tổng hợp; limit trước sort không tương đương top-K; filter trước hay sau unwind có thể chọn document hoặc chọn phần tử; limit trước lookup có thể bỏ sót những bản ghi thỏa điều kiện ở collection ngoại. Khi vừa đọc đúng explain vừa giữ đúng ngữ nghĩa pipeline, việc tối ưu MongoDB trở thành quá trình kiểm chứng bằng bằng chứng thay vì phỏng đoán.
