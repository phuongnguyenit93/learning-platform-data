# Phân tích truy vấn có sort, projection, mảng và nhiều nhánh điều kiện trong MongoDB

Một truy vấn MongoDB có thể lọc đúng dữ liệu nhưng vẫn chậm vì hệ quản trị phải đọc quá nhiều document, thực hiện sắp xếp riêng trong bộ nhớ hoặc phối hợp nhiều nhánh điều kiện mà index hiện có không hỗ trợ. Đặc biệt, khi truy vấn kết hợp **sort**, **projection**, **field dạng mảng** và toán tử **$or/$and**, việc nhìn vào tên index thường không đủ để biết truy vấn có được tối ưu hay không.

Công cụ quan trọng nhất để phân tích là **explain()**. Kết quả explain cho biết MongoDB lựa chọn kế hoạch thực thi nào, các stage nào được dùng, bao nhiêu index key và document được xét, có cần FETCH hay SORT không, và truy vấn đã trả bao nhiêu kết quả.

Bài học hướng dẫn cách đọc và giải thích kế hoạch thực thi, lựa chọn compound index theo filter và sort, đánh giá covered projection, phân tích multikey index của array, và xử lý các nhánh **$or**, **$and**, **$in**. Ví dụ được xây dựng với **mongosh** và MongoDB Java Sync Driver.

## 1. Từ truy vấn đến kế hoạch thực thi

Ứng dụng gửi câu truy vấn có thể gồm bốn phần:

~~~javascript
db.orders.find(
  {
    tenantId: "T-01",
    status: "PAID",
    tags: "priority"
  },
  {
    _id: 0,
    orderNo: 1,
    createdAt: 1,
    totalAmount: 1
  }
)
.sort({ createdAt: -1 })
.limit(20);
~~~

Các phần có vai trò khác nhau:

| Thành phần | Mục đích | Vấn đề hiệu năng cần xem |
| --- | --- | --- |
| **Filter** | Chọn document phù hợp | Có index nào giúp giới hạn số document phải xem? |
| **Sort** | Đưa kết quả về thứ tự yêu cầu | Index có trả dữ liệu đúng thứ tự hay phải sort riêng? |
| **Projection** | Chọn field trả về | Có thể trả dữ liệu chỉ từ index hay phải fetch document? |
| **Limit** | Giới hạn số kết quả | Có thể dừng sớm khi index hỗ trợ filter/sort không? |

Để thực thi, query planner có thể lựa chọn một trong nhiều **candidate plan**. Ví dụ:

~~~text
Query:
  tenantId = T-01
  status = PAID
  sort createdAt descending
  limit 20

Plan A:
  IXSCAN compound index
    -> FETCH nếu cần
    -> LIMIT
    -> trả kết quả

Plan B:
  IXSCAN một index khác
    -> FETCH
    -> SORT
    -> LIMIT
    -> trả kết quả

Plan C:
  COLLSCAN
    -> FILTER
    -> SORT
    -> LIMIT
    -> trả kết quả
~~~

Ba plan có thể trả **cùng tập kết quả logic**, nhưng chi phí đọc và sắp xếp khác nhau nhiều. Tác vụ phân tích không chỉ là “có dùng index hay không” mà còn là **dùng index nào, đọc bao nhiêu key/document, có bước blocking sort và có điều kiện nào được lọc muộn**.

### 1.1. Explain là bản mô tả thực thi, không phải câu lệnh sửa dữ liệu

Dùng:

~~~javascript
db.orders.find({ tenantId: "T-01" })
  .sort({ createdAt: -1 })
  .explain("executionStats");
~~~

Lệnh trả về một document chứa kế hoạch truy vấn và thống kê thực thi. Nó không tạo index hay thay đổi dữ liệu nghiệp vụ.

**Giới hạn cần nhớ:** explain quan sát một truy vấn và điều kiện cụ thể tại thời điểm chạy. Nó không thay thế benchmark dưới tải production và không bảo đảm planner sẽ luôn chọn cùng kế hoạch cho mọi biến thể dữ liệu.

## 2. Bộ dữ liệu mẫu cho cả bài

Ta dùng một collection đơn hàng đa tenant, với field đơn, document con và các array. Mỗi document có những field:

~~~javascript
{
  _id: 1,
  tenantId: "T-01",
  orderNo: "ORD-001",
  status: "PAID",
  channel: "APP",
  createdAt: ISODate("2026-11-01T09:00:00Z"),
  totalAmount: 150000,
  shipping: {
    city: "HCM"
  },
  tags: ["priority", "gift"],
  items: [
    { sku: "BOOK-01", quantity: 2, unitPrice: 50000 },
    { sku: "PEN-02", quantity: 1, unitPrice: 50000 }
  ]
}
~~~

Sử dụng database thực hành:

~~~javascript
use mongo_plan_lab

// Chỉ chạy thao tác xóa trên database thử nghiệm.
db.orders.drop();

db.orders.insertMany([
  {
    _id: 1,
    tenantId: "T-01",
    orderNo: "ORD-001",
    status: "PAID",
    channel: "APP",
    createdAt: ISODate("2026-11-01T09:00:00Z"),
    totalAmount: 150000,
    shipping: { city: "HCM" },
    tags: ["priority", "gift"],
    items: [
      { sku: "BOOK-01", quantity: 2, unitPrice: 50000 },
      { sku: "PEN-02", quantity: 1, unitPrice: 50000 }
    ]
  },
  {
    _id: 2,
    tenantId: "T-01",
    orderNo: "ORD-002",
    status: "PAID",
    channel: "WEB",
    createdAt: ISODate("2026-11-02T10:00:00Z"),
    totalAmount: 240000,
    shipping: { city: "HN" },
    tags: ["gift"],
    items: [
      { sku: "BOOK-02", quantity: 1, unitPrice: 240000 }
    ]
  },
  {
    _id: 3,
    tenantId: "T-01",
    orderNo: "ORD-003",
    status: "PENDING",
    channel: "APP",
    createdAt: ISODate("2026-11-03T08:00:00Z"),
    totalAmount: 80000,
    shipping: { city: "HCM" },
    tags: ["new"],
    items: [
      { sku: "PEN-02", quantity: 2, unitPrice: 40000 }
    ]
  },
  {
    _id: 4,
    tenantId: "T-01",
    orderNo: "ORD-004",
    status: "SHIPPED",
    channel: "APP",
    createdAt: ISODate("2026-11-04T11:00:00Z"),
    totalAmount: 450000,
    shipping: { city: "DN" },
    tags: ["priority"],
    items: [
      { sku: "BOOK-01", quantity: 1, unitPrice: 150000 },
      { sku: "BOOK-02", quantity: 1, unitPrice: 300000 }
    ]
  },
  {
    _id: 5,
    tenantId: "T-01",
    orderNo: "ORD-005",
    status: "PAID",
    channel: "APP",
    createdAt: ISODate("2026-11-05T12:00:00Z"),
    totalAmount: 120000,
    shipping: { city: "HCM" },
    tags: ["priority"],
    items: [
      { sku: "BOOK-01", quantity: 1, unitPrice: 120000 }
    ]
  },
  {
    _id: 6,
    tenantId: "T-01",
    orderNo: "ORD-006",
    status: "CANCELLED",
    channel: "WEB",
    createdAt: ISODate("2026-11-06T08:30:00Z"),
    totalAmount: 300000,
    shipping: { city: "HN" },
    tags: [],
    items: [
      { sku: "BOOK-03", quantity: 2, unitPrice: 150000 }
    ]
  },
  {
    _id: 7,
    tenantId: "T-02",
    orderNo: "ORD-007",
    status: "PAID",
    channel: "WEB",
    createdAt: ISODate("2026-11-01T14:00:00Z"),
    totalAmount: 900000,
    shipping: { city: "DN" },
    tags: ["gift"],
    items: [
      { sku: "BOOK-04", quantity: 3, unitPrice: 300000 }
    ]
  },
  {
    _id: 8,
    tenantId: "T-02",
    orderNo: "ORD-008",
    status: "PENDING",
    channel: "APP",
    createdAt: ISODate("2026-11-02T15:00:00Z"),
    totalAmount: 300000,
    shipping: { city: "HCM" },
    tags: ["new", "priority"],
    items: [
      { sku: "BOOK-01", quantity: 1, unitPrice: 300000 }
    ]
  },
  {
    _id: 9,
    tenantId: "T-02",
    orderNo: "ORD-009",
    status: "PAID",
    channel: "APP",
    createdAt: ISODate("2026-11-03T16:00:00Z"),
    totalAmount: 75000,
    shipping: { city: "HN" },
    tags: ["new"],
    items: [
      { sku: "PEN-02", quantity: 3, unitPrice: 25000 }
    ]
  },
  {
    _id: 10,
    tenantId: "T-02",
    orderNo: "ORD-010",
    status: "SHIPPED",
    channel: "WEB",
    createdAt: ISODate("2026-11-05T17:00:00Z"),
    totalAmount: 150000,
    shipping: { city: "HCM" },
    tags: [],
    items: [
      { sku: "BOOK-02", quantity: 1, unitPrice: 150000 }
    ]
  },
  {
    _id: 11,
    tenantId: "T-01",
    orderNo: "ORD-011",
    status: "PAID",
    channel: "WEB",
    createdAt: ISODate("2026-11-07T10:30:00Z"),
    totalAmount: 500000,
    shipping: { city: "DN" },
    tags: ["gift", "priority"],
    items: [
      { sku: "BOOK-04", quantity: 1, unitPrice: 500000 }
    ]
  },
  {
    _id: 12,
    tenantId: "T-01",
    orderNo: "ORD-012",
    status: "SHIPPED",
    channel: "WEB",
    createdAt: ISODate("2026-11-08T11:30:00Z"),
    totalAmount: 230000,
    shipping: { city: "HCM" },
    tags: ["priority"],
    items: [
      { sku: "BOOK-01", quantity: 2, unitPrice: 100000 },
      { sku: "PEN-02", quantity: 1, unitPrice: 30000 }
    ]
  }
]);
~~~

Bộ dữ liệu chỉ có **12 document**, đủ để hiểu kết quả logic:

- Tenant **T-01** có **8 đơn**.
- Tenant **T-01**, status **PAID** có **4 đơn**: 1, 2, 5, 11.
- Tenant **T-01**, status **PAID**, channel **APP** có **2 đơn**: 1 và 5.
- Trạng thái và ngày tạo được dùng để minh họa sort.
- **tags** là array scalar; **items** là array embedded document.

**Quan trọng:** với 12 document, MongoDB có thể chọn **COLLSCAN** là kế hoạch rẻ nhất ngay cả khi đã tạo index. Ví dụ cấu trúc plan và bảng số liệu về collection lớn sau đây là **minh họa**, không phải kết quả cố định có thể tái hiện chính xác trên bộ dữ liệu nhỏ.

## 3. Các chế độ explain và chỉ số cần đọc

MongoDB cung cấp các mức explain thường gặp:

~~~javascript
// Chỉ xem kế hoạch do planner chọn và những ứng viên liên quan.
db.orders.find({ status: "PAID" })
  .explain("queryPlanner");

// Xem kế hoạch và thống kê khi thực thi.
db.orders.find({ status: "PAID" })
  .explain("executionStats");

// Xem thêm thông tin thực thi các candidate plan.
db.orders.find({ status: "PAID" })
  .explain("allPlansExecution");
~~~

### 3.1. queryPlanner

Phần này thường mô tả:

- **winningPlan**: kế hoạch được chọn.
- **rejectedPlans**: những candidate plan không được chọn, khi có.
- **planCacheShapeHash / queryHash / planCacheKey**: thông tin nhận diện query shape và kế hoạch theo phiên bản.
- Những stage hoặc cấu trúc plan thể hiện đường đi của dữ liệu.

Không nên giả định tên field và cấu trúc cây plan luôn giống giữa các phiên bản MongoDB. Các bản dùng **Slot-Based Execution Engine (SBE)** có thể hiển thị phần **queryPlan**, **slotBasedPlan**, hoặc những stage khác cách hiển thị classic engine.

### 3.2. executionStats

Các chỉ số hữu ích:

| Chỉ số | Ý nghĩa | Cần chú ý |
| --- | --- | --- |
| **nReturned** | Số document/kết quả thực sự trả về | Nhỏ không có nghĩa truy vấn rẻ |
| **totalKeysExamined** | Tổng số index key được xem | Có thể lớn khi index không chọn lọc, hoặc index multikey |
| **totalDocsExamined** | Tổng số lần document được xem để đánh giá truy vấn | Bằng 0 có thể là dấu hiệu covered query |
| **executionTimeMillis** | Thời gian server ghi nhận cho lần explain | Dễ bị ảnh hưởng cache, tải và điều kiện thực thi |
| **executionStages** | Cây stage và thống kê từng stage | Tìm IXSCAN, FETCH, COLLSCAN, SORT, LIMIT |
| **works / advanced / needTime** | Counter thực thi trong những engine/stage hỗ trợ | Diễn giải theo phiên bản, không phải mọi plan đều có |

Ví dụ một truy vấn trả 20 đơn nhưng phải đọc 500.000 document:

~~~text
nReturned          = 20
totalKeysExamined  = 0
totalDocsExamined  = 500000
~~~

Đây có thể là dấu hiệu collection scan hoặc điều kiện rất kém hiệu quả. Ngược lại:

~~~text
nReturned          = 20
totalKeysExamined  = 20
totalDocsExamined  = 20
~~~

có thể phản ánh index scan rất hẹp. Đây chỉ là ví dụ so sánh, không phải quy tắc “keysExamined phải bằng nReturned”.

**totalDocsExamined có thể vượt số document logic duy nhất** trong một số cấu trúc plan, và totalKeysExamined có thể lớn hơn số document vì multikey hoặc các đoạn scan. Cần đọc cùng stage và filter để diễn giải.

### 3.3. allPlansExecution

Chế độ này hữu ích khi muốn tìm hiểu các candidate plan đã cạnh tranh như thế nào. Nhưng dữ liệu của candidate bị loại có thể chỉ là một phần hoạt động trong giai đoạn thử kế hoạch, không nhất thiết bằng thống kê nếu plan đó được chạy đầy đủ.

Không nên chỉ thấy một rejected plan dùng nhiều key hơn rồi kết luận planner luôn đúng hoặc luôn sai. Cần xem workload, phân bố tham số và thử nghiệm phù hợp.

### 3.4. Explain và plan cache

Một truy vấn thông thường có thể dùng plan cache hoặc lập kế hoạch theo chính sách của MongoDB. **explain không sử dụng các plan cache entry hiện có làm lựa chọn thắng và không đưa winning plan vào plan cache theo cách một truy vấn thông thường sử dụng cache**.

Vì vậy, explain rất hữu ích để phân tích, nhưng sự chênh lệch với request ứng dụng thật vẫn có thể xuất hiện. Khi truy vấn ở production chậm bất thường, hãy đối chiếu thêm profiler, telemetry và cơ chế plan cache theo phiên bản đang dùng.

## 4. Nhận diện các stage thường gặp

Cấu trúc plan có thể khác nhưng một số tên stage rất quan trọng.

| Stage / dạng kế hoạch | Diễn giải |
| --- | --- |
| **COLLSCAN** | Quét các document trong collection |
| **IXSCAN** | Duyệt index key theo khoảng hoặc hướng xác định |
| **FETCH** | Lấy document gốc sau khi tìm candidate qua index |
| **SORT** | Thực hiện bước sắp xếp riêng, thường là blocking sort |
| **LIMIT** | Giới hạn số kết quả ở một bước |
| **SKIP** | Bỏ qua số kết quả đầu |
| **PROJECTION_COVERED** | Projection có thể được thỏa từ index mà không phải fetch document |
| **PROJECTION_DEFAULT / PROJECTION_SIMPLE** | Stage áp dụng projection theo kế hoạch |
| **OR** | Kết hợp kết quả của nhiều nhánh kế hoạch |
| **SORT_MERGE** | Trộn những luồng dữ liệu có thứ tự trong một số trường hợp |
| **AND_HASH / AND_SORTED** | Một số dạng index intersection |
| **COUNT_SCAN** | Một số kế hoạch đếm từ index |
| **SHARD_MERGE / SHARDING_FILTER** | Một số bước liên quan tới sharded execution |

Không phải MongoDB luôn hiển thị chính xác các tên trên. Những phiên bản mới, aggregation pipeline hoặc SBE có thể dùng cách hiển thị khác. **Mục tiêu là nhận ra công việc thực sự**, chứ không viết parser phụ thuộc cứng vào một tên stage.

### 4.1. Hai plan mẫu

Plan sử dụng index để lọc rồi lấy document:

~~~text
LIMIT
└── FETCH
    └── IXSCAN
        indexName: idx_tenant_status_created
~~~

Plan không có index phù hợp cho sort:

~~~text
LIMIT
└── SORT
    └── FETCH
        └── IXSCAN
            indexName: idx_tenant_status
~~~

Ở plan thứ hai, index vẫn có ích cho filter, nhưng kết quả trung gian phải được sắp xếp. Một truy vấn có IXSCAN **vẫn có thể rất tốn tài nguyên** nếu SORT xử lý hàng trăm nghìn document trước khi lấy 20 kết quả.

### 4.2. Cách đọc cây plan

Bắt đầu từ node trả kết quả, lần xuống các node con để tìm:

1. **IXSCAN hay COLLSCAN** là nguồn dữ liệu?
2. Nếu IXSCAN, **indexName** là gì?
3. **indexBounds** hẹp hay rộng?
4. Có **FETCH** không, tại sao?
5. Có **SORT** không, liệu index đã cung cấp thứ tự?
6. Có filter được áp dụng muộn tại FETCH không?
7. Có nhánh OR hoặc merge nào không?
8. **nReturned**, keys/docs examined có hợp lý với kết quả không?

Hãy tránh suy luận rằng **FETCH là lỗi**. Nếu query cần field không có trong index, đọc document là hoạt động bình thường. Vấn đề là số document phải fetch quá lớn so với số kết quả cần.

## 5. Sort: khi index phục vụ được thứ tự yêu cầu

Giả sử nhu cầu phổ biến là lấy đơn PAID mới nhất của tenant T-01:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20);
~~~

Tạo compound index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);
~~~

Index sắp các key trước theo tenantId, tiếp đến status, rồi createdAt giảm dần trong nhóm tương ứng.

Khi filter có **tenantId = T-01** và **status = PAID**, MongoDB có thể duyệt vùng index phù hợp mà các key đã theo **createdAt giảm dần**. Tùy kế hoạch, hệ thống có thể dừng sớm sau khi tìm đủ 20 document.

### 5.1. Ví dụ logic thứ tự trong compound index

~~~text
Index keys: (tenantId asc, status asc, createdAt desc)

T-01 | PAID    | 2026-11-07
T-01 | PAID    | 2026-11-05
T-01 | PAID    | 2026-11-02
T-01 | PAID    | 2026-11-01
T-01 | PENDING | 2026-11-03
T-01 | SHIPPED | 2026-11-08
...
~~~

Với filter tenant và status cố định, đoạn key tương ứng đã sắp theo createdAt. Đây là ví dụ trực quan cho việc **equality prefix giúp index phục vụ sort ở những field phía sau**.

### 5.2. Quy tắc ESR: Equality – Sort – Range

Một hướng thiết kế compound index phổ biến:

1. **Equality:** field so sánh bằng thường đặt ở phần đầu.
2. **Sort:** các field giúp cung cấp thứ tự cần lấy.
3. **Range:** field dùng toán tử phạm vi như $gte/$lt thường xét phía sau phần sort nếu ưu tiên tránh blocking sort.

Ví dụ:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  status: "PAID",
  totalAmount: { $gte: 100000 }
})
.sort({ createdAt: -1 })
.limit(20);
~~~

Một index ứng viên:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    totalAmount: 1
  },
  { name: "idx_tenant_status_created_amount" }
);
~~~

Index này có thể phục vụ equality tenant/status và thứ tự createdAt, trong khi điều kiện totalAmount vẫn phải được xét trong quá trình duyệt. Nếu điều kiện amount cực kỳ chọn lọc, thiết kế đặt **totalAmount** sớm hơn có thể hữu ích hơn dù sort cần xử lý riêng.

**ESR là nguyên tắc khởi đầu, không phải định luật luôn thắng**. Một số workload theo hướng **Equality – Range – Sort (ERS)** có thể tối ưu hơn khi range rất chọn lọc. Phải so sánh bằng explain và độ trễ thực tế.

### 5.3. Index có field trung gian không được equality ràng buộc

Giả sử chỉ lọc tenantId và sort createdAt:

~~~javascript
db.orders.find({
  tenantId: "T-01"
})
.sort({ createdAt: -1 })
.limit(20);
~~~

Index hiện có:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

Trong index, các giá trị createdAt được sắp theo **từng nhóm status**. Nếu status không được cố định, thứ tự createdAt không nhất thiết là thứ tự toàn cục cho tất cả document của tenant. MongoDB có thể cần blocking sort hoặc index khác.

Một index riêng phù hợp hơn:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  { name: "idx_tenant_created" }
);
~~~

Như vậy không chỉ nhìn thấy **createdAt** ở đâu đó trong index là đủ. **Thứ tự field trong compound index và những field đã được filter bằng equality** quyết định khả năng index phục vụ sort.

### 5.4. Chiều sort và quét ngược index

Index:

~~~javascript
{ tenantId: 1, createdAt: -1 }
~~~

có thể phục vụ:

~~~javascript
db.orders.find({ tenantId: "T-01" })
  .sort({ createdAt: -1 });
~~~

và nhiều trường hợp có thể quét theo chiều ngược để phục vụ:

~~~javascript
db.orders.find({ tenantId: "T-01" })
  .sort({ createdAt: 1 });
~~~

Với **sort nhiều field**, hướng của các field phải tương thích với key pattern hoặc **đảo chiều toàn bộ phần thứ tự tương ứng**; không phải mọi tổ hợp đổi từng chiều độc lập đều được một index hỗ trợ.

Ví dụ:

~~~javascript
// Index:
{ tenantId: 1, status: 1, createdAt: -1 }

// Với tenantId equality, sort status asc, createdAt desc:
// Có thể phù hợp với thứ tự index.
db.orders.find({ tenantId: "T-01" })
  .sort({ status: 1, createdAt: -1 });
~~~

Nhưng nếu yêu cầu status asc và createdAt asc, index trên không mặc nhiên trả đúng thứ tự đó bằng một lần quét; cần phân tích hướng sort đầy đủ.

## 6. Blocking sort và chi phí của nó

**Blocking sort** cần nhận và sắp xếp một tập kết quả trung gian trước khi biết thứ tự trả ra. Điều này khác việc đọc index key vốn đã theo thứ tự mong muốn.

Ví dụ:

~~~javascript
db.orders.find({
  tenantId: "T-01"
})
.sort({ totalAmount: -1 })
.limit(10);
~~~

Nếu collection chỉ có index trên tenantId và createdAt, planner có thể đọc các đơn T-01 rồi sort theo totalAmount.

Sơ đồ:

~~~text
IXSCAN theo tenantId
       |
       v
FETCH document và lấy totalAmount
       |
       v
SORT theo totalAmount descending
       |
       v
LIMIT 10
~~~

Một **top-k sort** có thể tối ưu bộ nhớ khi kết hợp sort và limit, nhưng vẫn có thể phải **xét rất nhiều document đầu vào** để xác định top 10. Có limit không có nghĩa MongoDB chỉ đọc đúng 10 document.

### 6.1. Khi nào có thể tránh SORT?

Tạo index phù hợp:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, totalAmount: -1 },
  { name: "idx_tenant_amount" }
);
~~~

Truy vấn có thể đọc các key của tenant T-01 theo amount giảm dần rồi dừng khi đủ limit.

### 6.2. Sort cần bộ nhớ và đôi khi spill ra đĩa

Nếu cần sort lượng lớn dữ liệu không được index hỗ trợ, MongoDB có giới hạn bộ nhớ cho từng stage và cơ chế cho phép ghi dữ liệu tạm ra đĩa theo phiên bản/cấu hình và tùy chọn cho phép. Nếu không được phép spill hoặc vượt các giới hạn tương ứng, query có thể thất bại.

Ví dụ aggregation:

~~~javascript
db.orders.aggregate(
  [
    { $match: { tenantId: "T-01" } },
    { $sort: { totalAmount: -1 } },
    { $limit: 20 }
  ],
  { allowDiskUse: true }
);
~~~

**allowDiskUse không biến sort thành thao tác miễn phí**. Nó cho phép xử lý những trường hợp cần tài nguyên tạm trên đĩa khi được hỗ trợ, nhưng có thể tăng I/O và thời gian xử lý. Giải pháp dài hạn thường là cải thiện index hoặc giảm tập đầu vào cần sort.

### 6.3. Sort không ổn định nếu các giá trị bằng nhau

Nếu nhiều đơn có cùng createdAt, MongoDB không bảo đảm thứ tự cố định của chúng khi chỉ sort theo createdAt.

Để phân trang ổn định:

~~~javascript
db.orders.find({ tenantId: "T-01" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
~~~

Index tương ứng:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  { name: "idx_tenant_created_id" }
);
~~~

Field **_id** làm tie-breaker khi các document có cùng timestamp, giả sử _id unique trong phạm vi truy vấn. Với sharded collection, cần kiểm tra quy tắc định danh và shard key cho uniqueness/ordering toàn cục.

## 7. Projection: ít field trả về không có nghĩa không phải FETCH

Projection giới hạn field trong kết quả:

~~~javascript
db.orders.find(
  { tenantId: "T-01", status: "PAID" },
  { _id: 0, tenantId: 1, status: 1, createdAt: 1 }
)
.sort({ createdAt: -1 });
~~~

Nếu index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

chứa tất cả field cần lọc, sắp xếp và trả về, MongoDB có thể thực hiện **covered query**: dùng index mà không phải đọc document gốc.

Plan minh họa:

~~~text
PROJECTION_COVERED
└── IXSCAN
    indexName: idx_tenant_status_created

totalDocsExamined = 0
~~~

Điều kiện cụ thể của covered query còn phụ thuộc kiểu index, field được truy vấn, collation, multikey và các ràng buộc trong deployment.

### 7.1. Tại sao thường phải loại _id khỏi projection?

MongoDB mặc định đưa **_id** vào kết quả find, trừ khi projection loại bỏ nó.

Ví dụ:

~~~javascript
// Projection _id vẫn được trả về mặc định.
db.orders.find(
  { tenantId: "T-01", status: "PAID" },
  { tenantId: 1, status: 1, createdAt: 1 }
);
~~~

Nếu index không chứa _id, một query cần trả _id có thể phải FETCH document. Để tăng cơ hội covered query:

~~~javascript
db.orders.find(
  { tenantId: "T-01", status: "PAID" },
  {
    _id: 0,
    tenantId: 1,
    status: 1,
    createdAt: 1
  }
);
~~~

Hoặc thiết kế index có _id nếu việc trả _id là một nhu cầu quan trọng và lợi ích hợp lý với chi phí index bổ sung.

### 7.2. Chỉ một field ngoài index cũng có thể buộc FETCH

Với index tenant/status/createdAt:

~~~javascript
db.orders.find(
  { tenantId: "T-01", status: "PAID" },
  { _id: 0, tenantId: 1, status: 1, createdAt: 1, totalAmount: 1 }
);
~~~

Field **totalAmount** không có trong index nên MongoDB thường phải lấy document gốc để trả field này.

Sơ đồ minh họa:

~~~text
PROJECTION_DEFAULT / PROJECTION_SIMPLE
└── FETCH
    └── IXSCAN
        indexName: idx_tenant_status_created
~~~

Projection giúp giảm dữ liệu gửi tới client, nhưng **không bảo đảm giảm lượng document phải đọc**. Covered query mới là trường hợp đáng chú ý khi muốn tránh FETCH.

### 7.3. Chỉ nên đưa field vào index khi có lợi ích thực tế

Có thể thêm totalAmount:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    totalAmount: 1
  },
  { name: "idx_tenant_status_created_amount" }
);
~~~

Nhưng index lớn hơn có chi phí lưu trữ, cache và ghi. Không nên thêm mọi field cần trả về vào một index khổng lồ chỉ để đạt covered query. Cần so sánh số document phải FETCH với chi phí duy trì index.

### 7.4. Projection không thay đổi điều kiện filter

Ví dụ:

~~~javascript
db.orders.find(
  { status: "PAID", totalAmount: { $gte: 100000 } },
  { _id: 0, orderNo: 1 }
);
~~~

Mặc dù projection chỉ trả **orderNo**, server vẫn phải đánh giá **status** và **totalAmount**. Nếu index không thể giúp đánh giá filter, số document examined vẫn có thể rất cao.

**Projection không phải là cơ chế biến một query scan toàn collection thành query có index.**

## 8. Array và multikey index: vì sao explain khác index thường?

MongoDB có thể tạo index trên field chứa array. Khi index một array, MongoDB tạo các index key từ các phần tử phù hợp theo quy tắc của **multikey index**.

Ví dụ:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, tags: 1 },
  { name: "idx_tenant_tags" }
);
~~~

Document:

~~~javascript
{
  _id: 1,
  tenantId: "T-01",
  tags: ["priority", "gift"]
}
~~~

đóng góp các index key gắn với giá trị phần tử array, theo semantics của multikey index.

### 8.1. Một document có thể tạo nhiều index key

Truy vấn:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  tags: "priority"
});
~~~

Khi dùng multikey index, số **keysExamined** có thể lớn hơn số document được trả về. Một document chứa nhiều phần tử array có thể đóng góp nhiều key, và planner cần loại trùng kết quả khi nhiều key dẫn tới cùng document.

Cần phân biệt:

- **Index entry/key:** đại diện một giá trị được index.
- **Document:** đơn vị kết quả find.
- **nReturned:** số document sau khi đã áp dụng filter và các bước xử lý.

Không nên kết luận index multikey vô hiệu chỉ vì totalKeysExamined lớn hơn nReturned. Hãy xem tỷ lệ, bounds và những field thực sự được lọc bằng index.

### 8.2. Explain cho biết index có phải multikey không

Trong IXSCAN, tùy phiên bản, kết quả có thể có các field như:

~~~javascript
{
  stage: "IXSCAN",
  indexName: "idx_tenant_tags",
  isMultiKey: true,
  multiKeyPaths: {
    tenantId: [],
    tags: ["tags"]
  }
}
~~~

Đây là ví dụ minh họa cấu trúc, không phải output nguyên văn cố định của mọi phiên bản.

**isMultiKey: true** cho thấy index có dữ liệu đa khóa. **multiKeyPaths** giúp hiểu field/path nào trong compound index phát sinh multikey.

Một compound multikey index có những ràng buộc về các array được index. Không thể tùy ý tạo index kết hợp nhiều field array độc lập trong cùng một document; những ràng buộc này cần được xét khi thiết kế compound index.

## 9. Array of documents và $elemMatch

Giả sử order có:

~~~javascript
{
  _id: 100,
  items: [
    { sku: "BOOK-01", quantity: 1 },
    { sku: "PEN-02", quantity: 5 }
  ]
}
~~~

Yêu cầu: tìm đơn có **cùng một item** mang sku BOOK-01 và quantity ít nhất 2.

### 9.1. Hai điều kiện dot notation có thể khớp hai phần tử khác nhau

~~~javascript
db.orders.find({
  "items.sku": "BOOK-01",
  "items.quantity": { $gte: 2 }
});
~~~

Document ví dụ **có thể khớp**:

- Một phần tử có sku BOOK-01, quantity = 1.
- Phần tử khác có quantity = 5.

Hai điều kiện không mặc nhiên được ràng buộc vào cùng một phần tử array.

### 9.2. Dùng $elemMatch để ràng buộc cùng phần tử

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "BOOK-01",
      quantity: { $gte: 2 }
    }
  }
});
~~~

Document ví dụ không khớp, vì item BOOK-01 có quantity 1.

Trên dữ liệu mẫu 12 document, đơn **_id = 1** có BOOK-01 quantity 2 nên phù hợp; đơn _id = 4 có BOOK-01 quantity 1 nên không phù hợp điều kiện này.

### 9.3. Compound multikey index và index bounds

Có thể cân nhắc:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    "items.sku": 1,
    "items.quantity": 1
  },
  { name: "idx_tenant_item_sku_qty" }
);
~~~

Hai field **items.sku** và **items.quantity** cùng thuộc array embedded document **items**. Khi lọc có **$elemMatch trên đường dẫn chung items**, MongoDB có thể sử dụng điều kiện để ghép giới hạn index (bounds compounding) một cách chặt chẽ hơn theo quy tắc multikey index.

~~~javascript
db.orders.find({
  tenantId: "T-01",
  items: {
    $elemMatch: {
      sku: "BOOK-01",
      quantity: { $gte: 2 }
    }
  }
}).explain("executionStats");
~~~

Trong explain cần xem:

- Index **idx_tenant_item_sku_qty** có được chọn không?
- Bounds của **items.sku** và **items.quantity** được thu hẹp tới đâu?
- Có nhiều key phải xét vì các phần tử array không?
- Có FETCH để xác nhận điều kiện document không?
- totalKeysExamined và totalDocsExamined có giảm so với plan khác không?

**$elemMatch vừa xác định đúng semantics nghiệp vụ vừa có thể giúp khai thác compound bounds trên những field thuộc cùng array**, nhưng nó không bảo đảm truy vấn sẽ dùng một index cụ thể.

### 9.4. Không áp dụng bừa quy tắc của field scalar cho array

Với field scalar, hai điều kiện:

~~~javascript
{ status: "PAID", totalAmount: { $gte: 100000 } }
~~~

đều thuộc cùng một document và có thể khai thác compound index theo cách tương đối trực tiếp.

Với hai field đi xuyên qua array embedded document, phải cân nhắc liệu điều kiện cần cùng phần tử hay có thể thuộc những phần tử khác nhau. Đây vừa là vấn đề **kết quả đúng** vừa là vấn đề **cách index bounds được kết hợp**.

## 10. Sort trên field array: điểm dễ hiểu sai

Giả sử cần sort đơn hàng theo tags hoặc theo giá của phần tử trong items.

~~~javascript
db.orders.find({ tenantId: "T-01" })
  .sort({ tags: 1 });
~~~

Khi sort trực tiếp trên một array trong MongoDB, giá trị sort được xác định theo **các phần tử array**; với thứ tự tăng dần dùng phần tử nhỏ nhất theo quy tắc so sánh, còn giảm dần dùng phần tử lớn nhất. Đây không phải thứ tự tùy ý của phần tử đầu tiên trong array.

### 10.1. Filter vào một phần tử không nhất thiết đổi sort key

Ví dụ:

~~~javascript
db.orders.find({
  tags: "priority"
})
.sort({
  tags: 1
});
~~~

Truy vấn lọc những document có chứa **priority**. Nhưng sort trên field **tags** vẫn tuân theo quy tắc sort của toàn array, không tự giới hạn sort key thành phần tử **priority** vừa khớp filter.

Tương tự, nếu lọc **items.sku = BOOK-01** rồi sort theo **items.unitPrice**, không nên mặc định MongoDB đang sort theo đơn giá của **chính item BOOK-01**. Nếu nghiệp vụ yêu cầu giá của item khớp điều kiện, cần mô hình hóa hoặc aggregation để rút đúng giá trị trước khi sort.

### 10.2. Multikey index có giới hạn khi phục vụ sort

MongoDB có các quy tắc chặt chẽ hơn khi dùng **multikey index** cho sort. Trong những tình huống nhất định, ngay cả khi field sort xuất hiện trong index, planner vẫn cần **blocking SORT** do index bounds và đường dẫn multikey ảnh hưởng thứ tự.

Ví dụ minh họa:

~~~javascript
db.orders.createIndex(
  { tags: 1, createdAt: -1 },
  { name: "idx_tags_created" }
);

db.orders.find({
  tags: "priority"
})
.sort({
  tags: 1
})
.explain("executionStats");
~~~

Cần kiểm tra có SORT stage hay không. Không được suy luận rằng chỉ vì một index chứa field **tags** thì mọi sort trên tags đều được index giải quyết.

Về nguyên tắc, khả năng tránh blocking sort đối với multikey index phụ thuộc phạm vi bounds của trường sort và quan hệ đường dẫn với các trường multikey được ràng buộc. Một quy tắc có liên quan là các bounds của field sort phải không bị giới hạn theo cách ngăn index cung cấp thứ tự phù hợp; các path prefix chung với multikey fields cũng cần xét. **Hãy dùng explain thay vì khẳng định một index multikey luôn hỗ trợ sort**.

### 10.3. Tính đúng đắn khi sắp xếp theo item cụ thể

Nếu yêu cầu “đơn chứa BOOK-01, sắp theo giá BOOK-01 trong từng đơn”, aggregation có thể tách items để sort trên đúng phần tử:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "T-01" } },
  { $unwind: "$items" },
  { $match: { "items.sku": "BOOK-01" } },
  { $sort: { "items.unitPrice": -1, _id: 1 } },
  {
    $project: {
      _id: 1,
      orderNo: 1,
      sku: "$items.sku",
      itemPrice: "$items.unitPrice"
    }
  }
]);
~~~

Pipeline trên trả **một kết quả cho mỗi item BOOK-01** sau khi unwind. Nếu một order có nhiều item cùng sku, có thể xuất hiện nhiều hàng cho cùng order; muốn một hàng mỗi order cần thêm quy tắc group hoặc ràng buộc schema.

Aggregation **không tự động nhanh hơn** find. $unwind có thể làm tăng số dòng trung gian, và sort có thể trở thành blocking stage. Mục đích đầu tiên là làm rõ semantics.

## 11. Projection với multikey index

Covered query trên array có những điều kiện riêng.

Giả sử index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, tags: 1 },
  { name: "idx_tenant_tags" }
);
~~~

Truy vấn chỉ lọc bằng tags nhưng không trả field array:

~~~javascript
db.orders.find(
  {
    tenantId: "T-01",
    tags: "priority"
  },
  {
    _id: 0,
    tenantId: 1
  }
);
~~~

Tùy điều kiện, MongoDB có thể có cơ hội dùng index mà không fetch document vì projection không yêu cầu trả array tags.

Ngược lại:

~~~javascript
db.orders.find(
  {
    tenantId: "T-01",
    tags: "priority"
  },
  {
    _id: 0,
    tenantId: 1,
    tags: 1
  }
);
~~~

Muốn trả nguyên array tags, index multikey không lưu cấu trúc array gốc theo cách đủ để dựng lại đầy đủ, nên **không thể mặc định là covered query**. Truy vấn có thể phải FETCH document.

Các điều kiện covered query khi index là multikey thường bao gồm **không project field array**, đáp ứng các yêu cầu khác của covered query và không dùng $elemMatch trong những bối cảnh loại trừ coverage.

Một truy vấn có projection ngắn trên array không vì thế trở nên covered; phải xem **totalDocsExamined** và các stage thực tế.

## 12. Nhiều nhánh điều kiện: phân biệt $and, $or và $in

MongoDB cho phép kết hợp điều kiện với nhiều mức logic.

### 12.1. $and: tất cả điều kiện cùng đúng

~~~javascript
db.orders.find({
  $and: [
    { tenantId: "T-01" },
    { status: "PAID" },
    { totalAmount: { $gte: 100000 } }
  ]
});
~~~

Trong trường hợp các field không cần toán tử lặp phức tạp, dạng này tương đương với:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  status: "PAID",
  totalAmount: { $gte: 100000 }
});
~~~

Một **compound index** phù hợp thường là ứng viên tốt để phục vụ nhiều điều kiện. MongoDB cũng có thể cân nhắc **index intersection** trong một số trường hợp, nhưng không được đảm bảo planner sẽ luôn chọn intersection khi nhiều single-field index tồn tại.

### 12.2. $or: ít nhất một nhánh đúng

~~~javascript
db.orders.find({
  tenantId: "T-01",
  $or: [
    { status: "PAID" },
    { channel: "APP" }
  ]
});
~~~

Điều kiện có nghĩa:

~~~text
tenantId = T-01
AND
(
  status = PAID
  OR
  channel = APP
)
~~~

Lưu ý đặt tenantId ngoài $or để nó là điều kiện chung. Nếu vô tình đặt tenantId chỉ trong một nhánh, semantics có thể mở rộng dữ liệu ngoài tenant, gây vấn đề correctness và bảo mật.

### 12.3. $in: một field thuộc một tập giá trị

~~~javascript
db.orders.find({
  tenantId: "T-01",
  status: {
    $in: ["PAID", "SHIPPED"]
  }
});
~~~

Về logic, nó gần với:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  $or: [
    { status: "PAID" },
    { status: "SHIPPED" }
  ]
});
~~~

Khi nhiều giá trị cùng được so trên **một field**, $in thường biểu diễn rõ ràng hơn. Nhưng lựa chọn plan và khả năng giữ sort phụ thuộc vào số giá trị, bounds, compound index và phiên bản MongoDB. Không được cho rằng một danh sách $in rất lớn luôn hoạt động như equality đơn lẻ.

## 13. $or và index: mỗi nhánh có thể có đường truy cập riêng

Giả sử tìm đơn T-01 có status PAID **hoặc** có channel APP:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  $or: [
    { status: "PAID" },
    { channel: "APP" }
  ]
});
~~~

Có thể tạo các index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1 },
  { name: "idx_tenant_status" }
);

db.orders.createIndex(
  { tenantId: 1, channel: 1 },
  { name: "idx_tenant_channel" }
);
~~~

Query planner có thể sử dụng một plan kết hợp các nhánh với index khác nhau:

~~~text
OR / UNION
├── IXSCAN idx_tenant_status
└── IXSCAN idx_tenant_channel
       |
       v
Deduplicate document nếu phù hợp
       |
       v
FETCH / PROJECTION
~~~

Đây là sơ đồ khái niệm, không phải tên stage chắc chắn của mọi MongoDB version.

### 13.1. Vì sao một nhánh không có index có thể làm cả OR tốn kém?

Với OR, MongoDB cần tìm kết quả từ **mọi nhánh**. Nếu có một nhánh phải quét hầu hết collection, tổng plan dùng nhiều index cho những nhánh khác chưa chắc có lợi.

Ví dụ:

~~~javascript
db.orders.find({
  $or: [
    { status: "PAID" },
    { "shipping.city": "HCM" }
  ]
});
~~~

Nếu có index cho status nhưng không có index phù hợp cho shipping.city, planner có thể chọn **COLLSCAN** cho toàn bộ OR thay vì ghép các index plan. Đây là một lý do kiểm tra **mọi nhánh** của OR, không chỉ nhánh đầu tiên.

Không được hiểu đây là quy tắc tuyệt đối về một tên stage; planner cân nhắc các kế hoạch hợp lệ theo tình huống và phiên bản. Với các nhánh đủ indexable, MongoDB có khả năng dùng nhiều index.

### 13.2. OR có thể trả cùng document từ nhiều nhánh

Document _id = 1 có status PAID và channel APP, vì vậy thỏa **cả hai** nhánh. Query find thông thường vẫn trả document đó **một lần**, không phải hai lần.

Khi phân tích explain cho OR, số index key hoặc số candidate được xét có thể lớn hơn nReturned do nhiều nhánh cùng dẫn tới một document. Đừng nhầm số key xét với số kết quả duy nhất.

### 13.3. Điều kiện chung có thể ảnh hưởng index bounds

~~~javascript
{
  tenantId: "T-01",
  $or: [
    { status: "PAID" },
    { channel: "APP" }
  ]
}
~~~

Khi có compound index cùng prefix tenantId, các nhánh có cơ hội giới hạn vùng index theo tenant, thay vì quét toàn bộ tenant khác.

Với hệ thống đa tenant, việc luôn giữ tenantId trong filter là vấn đề **đúng dữ liệu và phân quyền** trước khi là tối ưu truy vấn. Nếu index bắt đầu bằng tenantId, nó cũng có thể giúp giảm số key cần xét khi workload chủ yếu truy vấn theo tenant.

## 14. $or kết hợp sort: vì sao dễ xuất hiện SORT

Giả sử thêm sort:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  $or: [
    { status: "PAID" },
    { channel: "APP" }
  ]
})
.sort({ createdAt: -1 })
.limit(20);
~~~

Ngay cả khi hai nhánh có index:

~~~javascript
{ tenantId: 1, status: 1 }
{ tenantId: 1, channel: 1 }
~~~

thứ tự kết quả kết hợp từ hai index không nhất thiết theo **createdAt giảm dần**.

Plan có thể là:

~~~text
LIMIT
└── SORT createdAt descending
    └── OR
        ├── IXSCAN idx_tenant_status
        └── IXSCAN idx_tenant_channel
~~~

Trường hợp khác, nếu từng nhánh có thể cung cấp cùng một thứ tự và planner có chiến lược phù hợp, có thể xuất hiện **SORT_MERGE** hoặc plan khác tránh sort toàn bộ theo kiểu thông thường.

Ví dụ index ứng viên:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);

db.orders.createIndex(
  { tenantId: 1, channel: 1, createdAt: -1 },
  { name: "idx_tenant_channel_created" }
);
~~~

Những index này giúp từng nhánh khi status/channel là equality, nhưng **không bảo đảm** toàn bộ OR + sort chắc chắn dùng plan merge không blocking. Phải đọc explain thật.

### 14.1. Đổi index để ưu tiên sort toàn cục

Một lựa chọn khác:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  { name: "idx_tenant_created" }
);
~~~

Planner có thể duyệt đơn của T-01 theo createdAt giảm dần, rồi kiểm tra điều kiện status/channel. Nếu limit nhỏ và tỷ lệ document phù hợp cao, cách này có thể hiệu quả.

Nhưng nếu điều kiện OR rất chọn lọc, planner phải duyệt rất nhiều document mới tìm đủ 20 kết quả, khiến plan này kém hiệu quả hơn các nhánh index chọn lọc rồi sort.

Đây là bài toán đánh đổi:

- **Index theo nhánh:** lọc hẹp hơn, có thể cần sort/merge.
- **Index theo thứ tự chung:** có thể tránh sort, nhưng đọc nhiều document để tìm match.

Không có lựa chọn mặc định thắng mọi phân bố dữ liệu.

### 14.2. Đọc thông số đúng theo mục tiêu

Nếu API cần 20 kết quả:

| Plan | keysExamined | docsExamined | Có SORT? | Nhận xét |
| --- | ---: | ---: | --- | --- |
| Quét index theo sort chung | 700 | 700 | Không | Đọc nhiều để tìm đủ match |
| Hai nhánh index chọn lọc | 80 | 65 | Có | Ít document hơn nhưng phải sort |
| Collection scan | 1.000.000 | 1.000.000 | Có | Có thể rất tốn kém |

**Đây là số liệu giả định để minh họa.** Kết luận phải dựa trên executionStats và latency thật, không nhìn riêng vào một cột.

## 15. $and và index intersection

Giả sử có index đơn:

~~~javascript
db.orders.createIndex(
  { status: 1 },
  { name: "idx_status" }
);

db.orders.createIndex(
  { channel: 1 },
  { name: "idx_channel" }
);
~~~

Và query:

~~~javascript
db.orders.find({
  status: "PAID",
  channel: "APP"
});
~~~

Một số kế hoạch có thể là:

1. Dùng idx_status rồi FETCH để kiểm tra channel.
2. Dùng idx_channel rồi FETCH để kiểm tra status.
3. Dùng **index intersection** khi planner đánh giá phù hợp.
4. Dùng compound index status + channel nếu tồn tại.

### 15.1. Intersection không phải cam kết

Các stage như **AND_HASH** hoặc **AND_SORTED** là dấu hiệu của một số kế hoạch index intersection. Nhưng planner có thể chọn một index đơn vì ít chi phí hơn. Việc tồn tại nhiều index không có nghĩa MongoDB nhất định kết hợp chúng.

Nếu một query shape xuất hiện thường xuyên và rất quan trọng, compound index:

~~~javascript
db.orders.createIndex(
  { status: 1, channel: 1 },
  { name: "idx_status_channel" }
);
~~~

có thể hiệu quả và dễ dự đoán hơn, tùy workload. Tuy nhiên, mỗi index mới tăng chi phí lưu trữ và ghi; không nên tạo index cho mọi tổ hợp field chỉ vì có thể.

### 15.2. Intersection không tự giải quyết sort

Giả sử:

~~~javascript
db.orders.find({
  status: "PAID",
  channel: "APP"
})
.sort({ createdAt: -1 });
~~~

Ngay cả khi intersection giúp lọc status/channel, kết quả từ intersection chưa chắc có thứ tự createdAt. Một compound index tính đến filter và sort có thể tốt hơn:

~~~javascript
db.orders.createIndex(
  { status: 1, channel: 1, createdAt: -1 },
  { name: "idx_status_channel_created" }
);
~~~

Đây là lý do đánh giá **toàn bộ query shape**, không chỉ filter.

## 16. Điều kiện lồng nhau nhiều cấp

Một truy vấn thực tế có thể dùng nhiều nhánh:

~~~javascript
const filter = {
  tenantId: "T-01",
  $and: [
    {
      $or: [
        { status: "PAID" },
        { status: "SHIPPED" }
      ]
    },
    {
      $or: [
        { channel: "APP" },
        { "shipping.city": "HCM" }
      ]
    }
  ]
};

db.orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(20);
~~~

Truy vấn có nghĩa:

~~~text
tenantId = T-01
AND
(status = PAID OR status = SHIPPED)
AND
(channel = APP OR shipping.city = HCM)
~~~

Ở đây có nhiều con đường để document phù hợp. Planner phải đánh giá các nhánh theo logic và lựa chọn cách thực thi; không thể suy ra một compound index duy nhất tự phục vụ mọi tình huống.

### 16.1. Đơn giản hóa khi các nhánh trên cùng field

Hai nhánh:

~~~javascript
{
  $or: [
    { status: "PAID" },
    { status: "SHIPPED" }
  ]
}
~~~

thường có thể diễn đạt thành:

~~~javascript
{
  status: {
    $in: ["PAID", "SHIPPED"]
  }
}
~~~

Cách viết này rõ hơn và có thể giúp ứng dụng quản lý query shape. Tuy nhiên, tác động tới plan vẫn phải xem khi kết hợp sort.

### 16.2. Không rewrite làm thay đổi semantics

Không biến:

~~~text
(A OR B) AND (C OR D)
~~~

thành:

~~~text
A OR B OR C OR D
~~~

vì hai biểu thức không tương đương. Tối ưu index phải bảo toàn chính xác logic lọc, đặc biệt trong hệ thống đa tenant hoặc truy vấn có điều kiện phân quyền.

### 16.3. Khi nào nên tách thành nhiều truy vấn?

Nếu OR rất phức tạp và mỗi nhánh cần kiểu index khác nhau, đôi khi có thể thử thực hiện nhiều query riêng rồi hợp nhất kết quả ở ứng dụng. Nhưng cần giải quyết:

- Loại trùng document xuất hiện ở nhiều nhánh.
- Đảm bảo sort tổng thể đúng.
- Phân trang và limit toàn cục.
- Read consistency giữa các query.
- Chi phí mạng và số lần round trip.
- Khả năng trả document đúng một lần.

Tách OR thành nhiều query **không mặc nhiên nhanh hơn hoặc đơn giản hơn**. Chỉ nên làm sau khi đo đạc và định nghĩa rõ semantics.

## 17. Explain đối với aggregation pipeline

Khi nhu cầu gồm filter, projection, sort và xử lý array, ứng dụng có thể dùng aggregation:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "T-01", status: "PAID" } },
  {
    $project: {
      _id: 0,
      orderNo: 1,
      createdAt: 1,
      totalAmount: 1
    }
  },
  { $sort: { createdAt: -1 } },
  { $limit: 20 }
]);
~~~

Giải thích:

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "T-01", status: "PAID" } },
  {
    $project: {
      _id: 0,
      orderNo: 1,
      createdAt: 1,
      totalAmount: 1
    }
  },
  { $sort: { createdAt: -1 } },
  { $limit: 20 }
]);
~~~

MongoDB có bộ tối ưu aggregation có thể di chuyển hoặc kết hợp các stage khi điều kiện cho phép, chẳng hạn đẩy $match xuống sớm hoặc tối ưu $sort + $limit.

**Đừng giả định thứ tự viết trong pipeline luôn đúng bằng thứ tự stage máy thực thi dùng.** Đọc phần optimized pipeline, query plan và executionStats nếu được trả về.

### 17.1. $match đầu pipeline và index

Một $match ở đầu pipeline thường giúp MongoDB có cơ hội sử dụng index của collection:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "T-01" } },
  { $sort: { createdAt: -1 } },
  { $limit: 20 }
]);
~~~

Nếu index **{ tenantId: 1, createdAt: -1 }** phù hợp, optimizer có thể tận dụng nó. Nhưng một stage biến đổi document trước $match/$sort có thể thay đổi khả năng dùng index.

### 17.2. $unwind làm tăng số dòng

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "T-01" } },
  { $unwind: "$items" },
  { $match: { "items.sku": "BOOK-01" } },
  { $sort: { "items.unitPrice": -1 } }
]);
~~~

Sau $unwind, một order có ba item có thể biến thành ba dòng đầu vào. Chỉ số output của các stage sau unwind cần hiểu theo **số dòng pipeline**, không chỉ số document gốc.

Nếu mục tiêu chỉ cần lọc order có item phù hợp, $elemMatch trên document gốc có thể ít công việc hơn:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  items: {
    $elemMatch: {
      sku: "BOOK-01"
    }
  }
});
~~~

Nhưng hai cách không trả cùng cấu trúc kết quả nếu aggregation sau unwind trả riêng từng item. Cần chọn theo mục tiêu nghiệp vụ.

### 17.3. $project sớm không phải lúc nào cũng tăng tốc

Nếu projection sớm làm mất field cần cho sort hoặc filter, pipeline không còn tương đương. Nếu projection thêm field tính toán, index có thể không phục vụ sort trên biểu thức đó như với field lưu sẵn.

Tối ưu hóa nên dựa vào explain và semantics sau khi MongoDB tối ưu pipeline, không chỉ vào nguyên tắc “đưa $project lên trước càng nhiều càng tốt”.

## 18. Filter và sort trong sharded cluster

Với collection được sharding, truy vấn có thể được định tuyến tới một shard hoặc nhiều shard tùy shard key.

Ví dụ giả định **tenantId** tham gia shard key theo thiết kế cluster:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20);
~~~

Nếu điều kiện đủ để định tuyến hẹp, số shard tham gia có thể giảm. Nếu query không có shard key phù hợp:

~~~javascript
db.orders.find({
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20);
~~~

yêu cầu có thể cần chạy trên nhiều shard rồi hợp nhất kết quả.

Trong explain có thể thấy plan từng shard và bước merge/sort kết quả. Một index tối ưu trên từng shard không có nghĩa toàn bộ truy vấn phân tán không có chi phí mạng hoặc merge.

### 18.1. Phân biệt sort cục bộ và sort toàn cục

Một shard có thể trả kết quả theo createdAt giảm dần nhờ index. Nhưng nếu có nhiều shard, mongos hoặc các bước merge vẫn phải phối hợp các dòng để trả **thứ tự toàn cục**.

Khi có limit, các shard có thể áp dụng những tối ưu phù hợp để giảm dữ liệu gửi về, nhưng hiệu quả cụ thể cần xem explain của cluster đang chạy.

### 18.2. Multikey và OR trong sharded cluster

Truy vấn trên array hoặc nhiều nhánh OR có thể được thực hiện ở các shard tương ứng. Nếu điều kiện không đủ để định tuyến, workload có thể fan-out tới nhiều shard. Hãy phân tích:

- Số shard được hỏi.
- Index mỗi shard dùng.
- Số key/document mỗi shard xét.
- Tải ở bước merge.
- Tác động của sort/projection tới lượng dữ liệu truyền qua mạng.

Không nên kết luận dựa trên explain của một shard rồi suy ra toàn bộ truy vấn phân tán có cùng chi phí.

## 19. Tạo một bộ tiêu chí đọc explain cho truy vấn phức tạp

Khi gặp truy vấn có filter, sort, projection, array và OR, hãy đi theo thứ tự.

### Bước 1 – Mô tả query shape

Ghi lại:

~~~text
Collection:
Các equality filter:
Các range filter:
Các nhánh $or:
Điều kiện trên array:
Sort pattern:
Projection fields:
Limit/skip:
Collation:
Read preference:
Shard key liên quan:
~~~

Nếu chưa mô tả đúng query shape, có thể tạo index hỗ trợ một biến thể nhỏ nhưng bỏ sót workload thật.

### Bước 2 – Đọc winning plan

~~~javascript
db.orders.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
~~~

Xác định IXSCAN/COLLSCAN, indexName và bounds. Không chỉ kiểm tra tên index mà bỏ qua residual filter.

### Bước 3 – Tìm SORT

Nếu có SORT:

- Có phải field sort không có index?
- Có field trung gian chưa equality-bound trong compound index không?
- Có range trước sort làm index không duy trì thứ tự cần thiết không?
- Có multikey restriction không?
- Có nhánh OR trả nhiều luồng kết quả không?
- Có collation không tương thích index không?

### Bước 4 – Tìm FETCH và projection

Nếu có FETCH:

- Projection có yêu cầu field không nằm trong index không?
- Field _id có bị trả mặc định không?
- Điều kiện filter nào phải được đánh giá tại document?
- Có field array hoặc $elemMatch khiến coverage không khả thi không?

FETCH tự nó không xấu. Cần xem **bao nhiêu document** phải FETCH.

### Bước 5 – Phân tích array và các nhánh

Với array:

- Index có isMultiKey không?
- Truy vấn cần cùng một phần tử không?
- Đã dùng $elemMatch đúng chưa?
- Sort trên array có ý nghĩa nghiệp vụ đúng không?

Với OR:

- Mọi nhánh có index phù hợp không?
- Document trùng giữa các nhánh được xử lý ra sao?
- Sort toàn cục có cần stage riêng không?
- Có thể thay OR cùng field bằng $in mà giữ semantics không?

### Bước 6 – Đánh giá chi phí

So sánh:

~~~text
nReturned
totalKeysExamined
totalDocsExamined
Số stage SORT/FETCH
Số shard tham gia
executionTimeMillis
P95/P99 trên ứng dụng thực
CPU / I/O / cache
~~~

Một query trả 10 document nhưng xét 500.000 index key vẫn có thể đáng tối ưu. Một query trả 100.000 document có totalDocsExamined tương đương 100.000 chưa chắc là sai nếu nghiệp vụ thực sự phải chuyển lượng dữ liệu lớn như vậy.

### Bước 7 – Thử index ứng viên

Tạo index thử nghiệm trong môi trường phù hợp:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_trial_tenant_status_created" }
);
~~~

Chạy lại cùng query shape và tham số đại diện. Có thể dùng **hint** để kiểm tra một index cụ thể có thể tạo plan gì:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.hint("idx_trial_tenant_status_created")
.explain("executionStats");
~~~

**Hint là công cụ thử nghiệm, không phải giải pháp mặc định cho mọi truy vấn production.** Nếu dữ liệu thay đổi, hint cố định có thể ép một plan không còn phù hợp; nếu index bị drop/hidden, hint có thể gây lỗi.

### Bước 8 – Đo trên workload đại diện

Collection nhỏ trong lab giúp hiểu semantics nhưng không đại diện cho sản phẩm có hàng triệu document. Cần có dữ liệu đủ lớn và phân bố gần production, bao gồm các query shape phổ biến và hiếm, trạng thái dữ liệu lệch, điều kiện theo tenant và mức concurrency thực tế.

## 20. Những anti-pattern thường gặp

| Nhầm lẫn | Thực tế cần hiểu |
| --- | --- |
| Có IXSCAN là truy vấn đã tối ưu | Có thể đọc rất nhiều key hoặc vẫn cần FETCH/SORT |
| Không có SORT stage nghĩa là kết quả chắc chắn được sort đúng | Chỉ đúng khi query có sort yêu cầu và plan cung cấp thứ tự đó |
| Field sort xuất hiện trong compound index là đủ | Phải xét prefix equality, phạm vi/range và hướng sort |
| Có limit 20 thì MongoDB chỉ đọc 20 document | Có thể phải đọc và sort số lượng lớn để tìm top 20 |
| Projection ít field luôn tiết kiệm việc đọc document | Chỉ covered query mới có thể tránh FETCH hoàn toàn |
| Bỏ _id khỏi projection không quan trọng | _id mặc định được trả, có thể ảnh hưởng coverage |
| Multikey index có một key mỗi document | Một array có thể tạo nhiều key |
| Hai điều kiện items.sku và items.quantity luôn cùng phần tử | Phải dùng $elemMatch khi nghiệp vụ yêu cầu cùng phần tử |
| Sort trên field array dùng phần tử đã khớp filter | Sort trên array có semantics riêng, không tự gắn với phần tử lọc |
| Mỗi nhánh OR đều có index thì chắc chắn không SORT | Việc hợp nhất kết quả vẫn có thể cần sort |
| Một nhánh OR có index là đủ tối ưu cả OR | Nhánh khác có thể buộc quét nhiều dữ liệu |
| Hai single-field index luôn được intersection | Planner không bảo đảm chọn index intersection |
| $in với nhiều giá trị luôn như equality đơn lẻ cho sort | Có thể cần nhiều range/merge tùy số giá trị và query plan |
| explain có plan nhanh thì API luôn nhanh | Production có cache, network, concurrency và dữ liệu khác |
| Tạo compound index càng nhiều field càng tốt | Index lớn tăng chi phí ghi, lưu trữ và cache |
| $unwind không làm thay đổi số lượng kết quả | Một document có thể thành nhiều dòng pipeline |
| explain ở một shard đại diện cho cả cluster | Có thể có bước fan-out và merge giữa nhiều shard |

## 21. Java Sync Driver: tạo truy vấn và gọi explain

Trong Java, có thể tạo một query bằng **Filters**, **Sorts** và **Projections**. Ví dụ:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

public class QueryPlanExample {

    public static void main(String[] args) {
        try (MongoClient client =
                     MongoClients.create("mongodb://localhost:27017")) {

            MongoDatabase database =
                    client.getDatabase("mongo_plan_lab");

            MongoCollection<Document> orders =
                    database.getCollection("orders");

            Bson filter = Filters.and(
                    Filters.eq("tenantId", "T-01"),
                    Filters.eq("status", "PAID")
            );

            Bson sort = Sorts.descending("createdAt");

            Bson projection = Projections.fields(
                    Projections.include(
                            "tenantId", "status", "createdAt"
                    ),
                    Projections.excludeId()
            );

            orders.find(filter)
                    .sort(sort)
                    .projection(projection)
                    .limit(20)
                    .forEach(System.out::println);
        }
    }
}
~~~

Muốn có output explain ít phụ thuộc helper API khác nhau giữa phiên bản driver, có thể gửi **explain command** trực tiếp qua MongoDatabase.runCommand():

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class ExplainFindCommand {

    public static void main(String[] args) {
        try (MongoClient client =
                     MongoClients.create("mongodb://localhost:27017")) {

            MongoDatabase database =
                    client.getDatabase("mongo_plan_lab");

            Document findCommand = new Document("find", "orders")
                    .append("filter", new Document(
                            "tenantId", "T-01"
                    ).append("status", "PAID"))
                    .append("sort", new Document(
                            "createdAt", -1
                    ))
                    .append("projection", new Document(
                            "_id", 0
                    ).append("tenantId", 1)
                     .append("status", 1)
                     .append("createdAt", 1))
                    .append("limit", 20);

            Document explainCommand =
                    new Document("explain", findCommand)
                            .append("verbosity", "executionStats");

            Document result =
                    database.runCommand(explainCommand);

            System.out.println(result.toJson());
        }
    }
}
~~~

Ví dụ yêu cầu MongoDB server đang chạy và dependency MongoDB Java Sync Driver. Một số phiên bản driver còn có API explain trên iterable phù hợp. Nội dung response phụ thuộc phiên bản MongoDB và chiến lược thực thi.

### 21.1. Điều chỉnh index từ Java

Có thể tạo compound index:

~~~java
import com.mongodb.client.model.Indexes;

// orders là MongoCollection<Document> đã được khởi tạo.
orders.createIndex(
        Indexes.compoundIndex(
                Indexes.ascending("tenantId", "status"),
                Indexes.descending("createdAt")
        )
);
~~~

Trong production, tạo index trên collection lớn cần kế hoạch thay đổi và theo dõi tài nguyên. Chỉ tạo index sau khi xác định query shape và đánh giá chi phí, không nên để code xử lý request liên tục gọi createIndex.

### 21.2. Đọc explain thay vì hard-code stage

Nếu muốn tích hợp giám sát tự động, hãy thu thập các chỉ số có hợp đồng tương đối ổn định như **nReturned**, **totalKeysExamined**, **totalDocsExamined**, cùng plan summary/log query shape phù hợp. Không nên chỉ dùng một phép tìm văn bản **"IXSCAN"** trong JSON vì cấu trúc output có thể thay đổi theo engine và version.

## 22. Bài thực hành: sort và compound index

Dùng collection **mongo_plan_lab.orders** đã tạo. Trong lab nhỏ, kết quả explain có thể chọn COLLSCAN dù index tồn tại. Mục tiêu chính là hiểu cách đặt câu hỏi và cách đọc plan.

### Bài A – So sánh sort có index và không có index

Tạo index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);
~~~

Chạy:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(3)
.explain("executionStats");
~~~

Trả lời:

1. Trong trường hợp index được chọn, equality prefix gồm những field nào?
2. Index có thể cung cấp thứ tự createdAt descending không?
3. Có FETCH vì truy vấn trả nguyên document không?
4. Vì sao limit 3 không chứng minh chỉ đọc đúng 3 key?
5. Nếu bỏ status khỏi filter, index này còn chắc chắn tránh blocking sort không?

### Bài B – Thử sort trên field không có trong index

~~~javascript
db.orders.find({
  tenantId: "T-01"
})
.sort({ totalAmount: -1 })
.limit(3)
.explain("executionStats");
~~~

Sau đó thử:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, totalAmount: -1 },
  { name: "idx_tenant_amount" }
);
~~~

Chạy lại explain và quan sát sort stage. Nếu bộ dữ liệu nhỏ cho kết quả không khác nhiều, hãy giải thích vì sao cần tập dữ liệu lớn và phân bố đại diện để đánh giá index.

## 23. Bài thực hành: projection và covered query

### Bài C – So sánh projection có và không có _id

~~~javascript
const filter = {
  tenantId: "T-01",
  status: "PAID"
};

db.orders.find(
  filter,
  {
    tenantId: 1,
    status: 1,
    createdAt: 1
  }
).explain("executionStats");
~~~

So sánh với:

~~~javascript
db.orders.find(
  filter,
  {
    _id: 0,
    tenantId: 1,
    status: 1,
    createdAt: 1
  }
).explain("executionStats");
~~~

Trả lời:

1. Vì sao projection mặc định trả _id?
2. Khi nào plan có thể đạt totalDocsExamined = 0?
3. Vì sao projection thêm totalAmount có thể làm xuất hiện FETCH?
4. Có đáng tạo index mới chỉ để cover thêm một field không?

### Bài D – Projection lên field array

~~~javascript
db.orders.createIndex(
  { tenantId: 1, tags: 1 },
  { name: "idx_tenant_tags" }
);

db.orders.find(
  { tenantId: "T-01", tags: "priority" },
  { _id: 0, tenantId: 1 }
).explain("executionStats");
~~~

So sánh với projection có thêm **tags: 1** và giải thích vì sao yêu cầu trả nguyên array có thể ngăn covered query.

## 24. Bài thực hành: array và $elemMatch

### Bài E – So sánh hai điều kiện trên embedded array

~~~javascript
const looseQuery = {
  "items.sku": "BOOK-01",
  "items.quantity": { $gte: 2 }
};

const sameElementQuery = {
  items: {
    $elemMatch: {
      sku: "BOOK-01",
      quantity: { $gte: 2 }
    }
  }
};

printjson(db.orders.find(looseQuery, { _id: 1 }).toArray());

printjson(
  db.orders.find(sameElementQuery, { _id: 1 }).toArray()
);
~~~

Trả lời:

1. Vì sao hai query có thể trả tập kết quả khác nhau?
2. Document nào có sku phù hợp nhưng quantity chỉ đủ ở item khác?
3. Nếu tạo compound multikey index trên items.sku/items.quantity, $elemMatch có thể giúp planner kết hợp bounds như thế nào?
4. Vì sao totalKeysExamined có thể lớn hơn nReturned khi có array?

### Bài F – Sắp xếp theo một item cụ thể

Viết aggregation dùng **$unwind**, **$match**, **$sort** để lấy item BOOK-01 theo unitPrice giảm dần. Giải thích vì sao:

~~~javascript
db.orders.find({
  "items.sku": "BOOK-01"
}).sort({
  "items.unitPrice": -1
});
~~~

không tự mang ý nghĩa “sort theo unitPrice của item BOOK-01 đã khớp”.

## 25. Bài thực hành: $or, $and và sort

### Bài G – Đo một OR hai nhánh

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1 },
  { name: "idx_tenant_status" }
);

db.orders.createIndex(
  { tenantId: 1, channel: 1 },
  { name: "idx_tenant_channel" }
);

db.orders.find({
  tenantId: "T-01",
  $or: [
    { status: "PAID" },
    { channel: "APP" }
  ]
})
.explain("executionStats");
~~~

Xác định:

1. Có thể dùng index nào cho từng nhánh?
2. Một document thỏa cả hai nhánh có xuất hiện hai lần không?
3. Nếu thêm sort createdAt descending, plan có thể cần thêm stage nào?
4. Nếu bỏ index của channel, vì sao plan có thể chuyển sang collection scan?
5. Vì sao index { tenantId: 1, createdAt: -1 } có thể là lựa chọn khác cho query có limit nhỏ?

### Bài H – Tối ưu một query nhiều nhánh

~~~javascript
db.orders.find({
  tenantId: "T-01",
  status: { $in: ["PAID", "SHIPPED"] },
  $or: [
    { channel: "APP" },
    { "shipping.city": "HCM" }
  ],
  totalAmount: { $gte: 100000 }
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

Hãy phân tích theo từng bước:

- Những field nào là equality, range, các nhánh OR?
- Có bao nhiêu index khác nhau có thể là ứng viên?
- Có thể ưu tiên sort hay ưu tiên filter chọn lọc?
- Có cần compound index chứa createdAt và _id không?
- Nếu một nhánh OR rất ít match, index riêng cho nhánh đó có đáng tạo không?
- Làm thế nào đo totalKeysExamined/totalDocsExamined, blocking sort, thời gian và chi phí duy trì index?

Câu trả lời phải dựa trên **workload và dữ liệu thực tế**, không có một compound index duy nhất được bảo đảm tối ưu với mọi biến thể.

## 26. Tóm lược phương pháp phân tích

Khi truy vấn MongoDB phức tạp, nên xem xét theo bốn câu hỏi:

1. **Filter:** MongoDB tìm document bằng index bounds hẹp hay đang quét quá nhiều key/document?
2. **Sort:** Thứ tự kết quả đã được index cung cấp hay cần blocking sort/merge?
3. **Projection:** Có thể trả dữ liệu chỉ từ index hay phải FETCH document gốc?
4. **Array và nhánh điều kiện:** Multikey, $elemMatch, $or/$and/$in làm thay đổi semantics, số key xét và kế hoạch thực thi thế nào?

Hãy xác minh bằng **explain("executionStats")**, so sánh các index ứng viên theo cùng query shape, ghi nhận **nReturned**, **totalKeysExamined**, **totalDocsExamined**, SORT/FETCH/IXSCAN/COLLSCAN và đối chiếu với độ trễ thực tế. Với workload lớn, đừng chỉ tối ưu một câu truy vấn trên dữ liệu mẫu nhỏ; cân nhắc cả chi phí lưu trữ và bảo trì index.

**Kế hoạch tốt là kế hoạch đáp ứng đúng kết quả nghiệp vụ và phù hợp với workload thực tế**, không phải kế hoạch có nhiều stage IXSCAN nhất hoặc không có FETCH bằng mọi giá.

## Tài liệu tham khảo

- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — db.collection.explain()](https://www.mongodb.com/docs/manual/reference/method/db.collection.explain/)
- [MongoDB Manual — Query Plans](https://www.mongodb.com/docs/manual/core/query-plans/)
- [MongoDB Manual — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual — ESR Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/)
- [MongoDB Manual — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [MongoDB Manual — $elemMatch](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/)
- [MongoDB Manual — $or](https://www.mongodb.com/docs/manual/reference/operator/query/or/)
- [MongoDB Manual — Sort Results](https://www.mongodb.com/docs/manual/reference/method/cursor.sort/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
