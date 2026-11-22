# Lọc sớm bằng $match và quan hệ với index

Trong MongoDB Aggregation Framework, một pipeline xử lý document qua các **stage** liên tiếp. Mỗi stage có thể lọc, biến đổi, sắp xếp, nhóm hoặc kết hợp dữ liệu. Nếu pipeline phải đọc hàng triệu document rồi mới loại phần lớn bằng `$match`, các stage trước đó có thể đã tốn CPU, bộ nhớ, I/O và thời gian mà không mang lại giá trị. Vì vậy, nguyên tắc quan trọng là **lọc sớm bằng `$match` khi không làm thay đổi ý nghĩa kết quả**, đồng thời tạo điều kiện để query planner khai thác **index**.

Tuy nhiên “đưa `$match` lên đầu” không phải quy luật áp dụng mù quáng: có filter phải đặt **sau `$unwind`, `$group`, `$addFields` hoặc `$lookup`** vì chúng dựa trên dữ liệu mà các stage đó tạo ra. MongoDB có **aggregation pipeline optimizer** có thể tự tách và đẩy một số filter lên trước; mức tối ưu phụ thuộc dependency, phiên bản và hình dạng pipeline. Bài hướng dẫn cả **ngữ nghĩa đúng** và **cách kiểm chứng hiệu năng bằng `explain`**.

Đây là bài trong chương **Aggregation cơ bản** thuộc module *Database Engine Document MongoDB*. Sau bài học, bạn có thể:

1. Viết `$match` với cú pháp tương tự `find()`, dùng `$expr` khi cần tính biểu thức.
2. Chọn vị trí lọc sao cho giảm lượng dữ liệu phải qua các stage đắt tiền.
3. Hiểu khi nào `$match` có thể tận dụng **single-field, compound, multikey và partial index**.
4. Phân biệt **lọc trước khi đổi hình dạng dữ liệu** và **lọc trên kết quả tính toán**.
5. Đọc `explain("executionStats")` để kiểm tra `IXSCAN`, `COLLSCAN`, số keys/documents đã xem và các tối ưu pipeline.
6. Thiết kế pipeline có `$sort`, `$group`, `$unwind`, `$lookup`, `$facet` mà vẫn đúng nghiệp vụ.
7. Viết truy vấn tương đương qua MongoDB Java Sync Driver và chọn index theo access pattern.

> **Phiên bản:** Các ví dụ dùng cú pháp phổ biến ở MongoDB 7.0/8.0 và các bản tương thích. Cấu trúc `explain`, query optimizer và execution engine như SBE có thể thay đổi giữa phiên bản. Hãy đối chiếu Database Manual đúng MongoDB Server/FCV; không coi một `explain` cụ thể là định dạng cố định.

## 1. `$match` làm gì trong pipeline?

`$match` là **aggregation stage** chỉ giữ những document thỏa điều kiện và loại document không khớp trước khi chuyển sang stage kế tiếp.

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } }
])
~~~

Điều kiện bên trong `$match` thường dùng **query predicate syntax** tương tự `find()`:

~~~javascript
// Hai cách lọc cùng ý nghĩa trên document gốc:
db.orders.find({ status: "PAID" })

db.orders.aggregate([
  { $match: { status: "PAID" } }
])
~~~

Nhưng aggregation cho phép những stage sau tiếp tục xử lý:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$customerId", total: { $sum: "$total" } } },
  { $sort: { total: -1 } }
])
~~~

### 1.1. Luồng dữ liệu

~~~text
Collection orders: hàng triệu document
            |
            v
        $match
    status = "PAID"
            |
            v
   Chỉ document phù hợp
            |
            v
       $group
   Gom theo customerId
            |
            v
        $sort
   Sắp tổng tiền giảm dần
~~~

Nếu `$match` loại nhiều document ở đầu, `$group` nhận ít input hơn, bảng hash/accumulator có thể nhỏ hơn, số nhóm cần sort cuối pipeline cũng có thể giảm. Lợi ích thực tế phụ thuộc **tính chọn lọc của filter, index, cardinality của nhóm và cách thực thi**.

### 1.2. `$match` lọc document, không tự biến đổi field

| Stage | Vai trò |
|---|---|
| `$match` | Lọc document theo điều kiện. |
| `$project` | Giữ/bỏ/tính toán field output. |
| `$addFields` / `$set` | Bổ sung hoặc ghi đè field. |
| `$unwind` | Tách phần tử array thành pipeline documents riêng. |
| `$group` | Gom document theo khóa, tính accumulator. |
| `$sort` | Sắp xếp pipeline documents. |
| `$limit` | Giữ số document tối đa. |
| `$lookup` | Ghép dữ liệu từ collection khác. |
| `$facet` | Chạy nhiều nhánh trên cùng tập input. |

Lọc trước những stage biến đổi thường có lợi **nếu điều kiện chỉ dùng field gốc và việc chuyển vị trí không làm đổi kết quả**. Khi filter tham chiếu field do stage khác tính, hoặc cần áp lên một item sau unwind, phải giữ dependency.

### 1.3. Predicate thường dùng

~~~javascript
{
  $match: {
    tenantId: "T-A",
    status: { $in: ["PAID", "SHIPPED"] },
    total: { $gte: 100000 },
    createdAt: {
      $gte: ISODate("2026-06-01T00:00:00Z"),
      $lt: ISODate("2026-07-01T00:00:00Z")
    }
  }
}
~~~

Các field cùng cấp kết hợp logic **AND**. Dùng `$or` cho điều kiện thay thế:

~~~javascript
{
  $match: {
    tenantId: "T-A",
    $or: [
      { status: "PAID" },
      { status: "SHIPPED" }
    ]
  }
}
~~~

Nên so sánh **BSON Date với BSON Date** và số với số; không đổi date thành string trước khi lọc nếu yêu cầu thật sự là một khoảng thời gian.

## 2. Bộ dữ liệu thực hành

Sử dụng collection `agg_match_lab.orders` với chín đơn thuộc hai tenant. Dữ liệu cho phép kiểm chứng kết quả filter bằng mắt.

> **Chỉ chạy trên lab.** Script giả định collection trống. Nếu chạy lại, các `_id` cố định sẽ gây duplicate key; chọn database/collection lab mới hoặc reset đúng fixture có chủ đích, không xóa database dùng chung.

~~~javascript
const lab = db.getSiblingDB("agg_match_lab")

lab.orders.insertMany([
  {
    _id: "O-101", tenantId: "T-A", status: "PAID",
    createdAt: ISODate("2026-06-01T08:00:00Z"),
    region: "HN", customerId: "C-1", total: 320000,
    items: [
      { sku: "BK-01", qty: 2, price: 120000 },
      { sku: "PN-02", qty: 8, price: 10000 }
    ]
  },
  {
    _id: "O-102", tenantId: "T-A", status: "PAID",
    createdAt: ISODate("2026-06-03T09:00:00Z"),
    region: "HN", customerId: "C-2", total: 140000,
    items: [{ sku: "PN-02", qty: 14, price: 10000 }]
  },
  {
    _id: "O-103", tenantId: "T-A", status: "CANCELLED",
    createdAt: ISODate("2026-06-04T10:00:00Z"),
    region: "SG", customerId: "C-3", total: 90000,
    items: [{ sku: "BK-03", qty: 1, price: 90000 }]
  },
  {
    _id: "O-104", tenantId: "T-A", status: "PAID",
    createdAt: ISODate("2026-06-08T11:00:00Z"),
    region: "SG", customerId: "C-1", total: 800000,
    items: [
      { sku: "BK-01", qty: 5, price: 120000 },
      { sku: "BK-03", qty: 2, price: 100000 }
    ]
  },
  {
    _id: "O-105", tenantId: "T-B", status: "PAID",
    createdAt: ISODate("2026-06-01T12:00:00Z"),
    region: "HN", customerId: "C-4", total: 250000,
    items: [{ sku: "BK-01", qty: 2, price: 125000 }]
  },
  {
    _id: "O-106", tenantId: "T-A", status: "CREATED",
    createdAt: ISODate("2026-06-10T13:00:00Z"),
    region: "HN", customerId: "C-5", total: 200000,
    items: [{ sku: "PN-02", qty: 20, price: 10000 }]
  },
  {
    _id: "O-107", tenantId: "T-A", status: "PAID",
    createdAt: ISODate("2026-06-15T14:00:00Z"),
    region: "SG", customerId: "C-2", total: 460000,
    items: [
      { sku: "BK-01", qty: 3, price: 120000 },
      { sku: "PN-02", qty: 10, price: 10000 }
    ]
  },
  {
    _id: "O-108", tenantId: "T-B", status: "CANCELLED",
    createdAt: ISODate("2026-06-18T15:00:00Z"),
    region: "SG", customerId: "C-6", total: 650000,
    items: [{ sku: "BK-03", qty: 5, price: 130000 }]
  },
  {
    _id: "O-109", tenantId: "T-A", status: "PAID",
    createdAt: ISODate("2026-07-01T08:00:00Z"),
    region: "HN", customerId: "C-7", total: 90000,
    items: [{ sku: "BK-03", qty: 1, price: 90000 }]
  }
])

lab.orders.find(
  {},
  { _id: 1, tenantId: 1, status: 1, createdAt: 1, total: 1 }
).sort({ _id: 1 })
~~~

Đặt biến filter dùng xuyên bài:

~~~javascript
const start = ISODate("2026-06-01T00:00:00Z")
const end = ISODate("2026-07-01T00:00:00Z")

const paidJuneTenantA = {
  tenantId: "T-A",
  status: "PAID",
  createdAt: { $gte: start, $lt: end }
}
~~~

Filter chọn **O-101, O-102, O-104, O-107**. Nó loại O-103 (CANCELLED), O-105 (tenant khác), O-106 (CREATED), O-108 (tenant khác) và O-109 (đã sang tháng 7). Các con số kết quả ở phần tiếp theo chỉ đúng với **fixture** chưa bị sửa.

## 3. Lọc sớm giảm lượng dữ liệu đi qua pipeline

### 3.1. Pipeline có filter đặt muộn

~~~javascript
lab.orders.aggregate([
  {
    $project: {
      tenantId: 1, status: 1, createdAt: 1,
      region: 1, total: 1,
      totalWithNoChange: { $add: ["$total", 0] }
    }
  },
  { $match: paidJuneTenantA },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$totalWithNoChange" },
      orderCount: { $sum: 1 }
    }
  }
])
~~~

Nếu server thực thi projection trên nhiều document rồi mới lọc, nó tính `totalWithNoChange` cho những document bị loại. Tuy nhiên MongoDB **có thể tự đẩy các predicate độc lập lên trước projection**; không được kết luận chỉ từ thứ tự viết rằng tất cả document chắc chắn đã qua projection. Dù vậy, thể hiện ý định lọc sớm trong pipeline giúp dễ đọc và quản lý.

### 3.2. Đặt `$match` đầu tiên khi có thể

~~~javascript
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  {
    $project: {
      region: 1,
      totalWithNoChange: { $add: ["$total", 0] }
    }
  },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$totalWithNoChange" },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { revenue: -1 } }
])
~~~

Kết quả dự kiến:

| `_id` / region | `revenue` | `orderCount` |
|---|---:|---:|
| `"SG"` | 1.260.000 | 2 (O-104, O-107) |
| `"HN"` | 460.000 | 2 (O-101, O-102) |

Trước `$group` chỉ còn **4 document** thay vì **9 document** của fixture. Với dữ liệu lớn, việc thu hẹp sớm có thể giảm đáng kể số document được chuyển giữa các stage.

### 3.3. Dùng nửa khoảng thời gian `[start, end)`

~~~javascript
createdAt: {
  $gte: ISODate("2026-06-01T00:00:00Z"),
  $lt: ISODate("2026-07-01T00:00:00Z")
}
~~~

Cách viết **đầu kỳ bao gồm, cuối kỳ loại trừ** giúp tránh lỗi biên khi timestamp có độ chính xác millisecond, không phải tính “23:59:59.999”, và phù hợp range scan qua index. Nếu kỳ báo cáo tính theo múi giờ Việt Nam, phải chuyển ranh giới địa phương sang UTC chính xác.

Không nên chuyển date thành chuỗi cho mỗi document nếu mục tiêu chỉ là một khoảng:

~~~javascript
// Có thể làm mất khả năng tối ưu range index trực tiếp.
{
  $match: {
    $expr: {
      $eq: [
        { $dateToString: { format: "%Y-%m", date: "$createdAt" } },
        "2026-06"
      ]
    }
  }
}
~~~

Một expression tính toán trên field có thể khiến server **khó tận dụng index B-tree hiện có trên `createdAt`** để lọc. Khi có cách tương đương về ngữ nghĩa, ưu tiên range trên field BSON Date gốc.

## 4. `$match` ở đầu pipeline và index

Một `$match` đặt đầu pipeline có thể được xử lý tương tự **query filter** của `find()`. Khi có index phù hợp và planner chọn nó, MongoDB có thể đọc những index keys cần thiết thay vì quét toàn collection.

### 4.1. Index đơn trường

~~~javascript
const lab = db.getSiblingDB("agg_match_lab")

lab.orders.createIndex(
  { status: 1 },
  { name: "ix_status" }
)

lab.orders.aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$region", count: { $sum: 1 } } }
])
~~~

Planner **có thể** dùng `ix_status` để lấy các đơn PAID trước khi nhóm, nhưng **có index không đảm bảo có `IXSCAN`**:

- Nếu PAID chiếm gần như toàn collection, `COLLSCAN` có thể rẻ hơn.
- Nếu collection nhỏ, quét tuần tự đôi khi rẻ hơn index traversal + fetch.
- Nếu index hoặc collation không hợp filter, planner có thể chọn đường khác.
- Nếu cần nhiều field nằm ngoài index, có thể phải `FETCH` các document gốc.
- Plan cache, thống kê và cấu trúc query cũng ảnh hưởng lựa chọn.

**Đánh giá bằng `explain` trên dữ liệu đại diện**, không dựa vào suy đoán rằng `$match` ở đầu pipeline thì server luôn dùng index.

### 4.2. Compound index cho nhiều điều kiện

Query báo cáo lọc **tenant**, **status**, **khoảng createdAt** rồi sắp ngày giảm:

~~~javascript
lab.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "ix_tenant_status_createdAt_desc" }
)

lab.orders.aggregate([
  { $match: paidJuneTenantA },
  { $sort: { createdAt: -1 } },
  { $project: { _id: 1, region: 1, total: 1, createdAt: 1 } }
])
~~~

Hai field đầu trong index có điều kiện **equality**, còn `createdAt` vừa có **range** vừa cần **sort giảm dần**. Với index phù hợp, planner có cơ hội giới hạn documents và duy trì thứ tự từ index thay vì chạy sort in-memory riêng. Nhưng cần xem `explain` thực tế vì chi phí còn phụ thuộc số lượng khớp và việc đọc các field ngoài index.

### 4.3. Prefix của compound index

Index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

thường phù hợp với:

~~~javascript
{ tenantId: "T-A" }

{ tenantId: "T-A", status: "PAID" }

{
  tenantId: "T-A",
  status: "PAID",
  createdAt: { $gte: start, $lt: end }
}
~~~

Ngược lại, query chỉ có `status:"PAID"` nhưng **không lọc tenantId** khó khai thác index này theo cách tối ưu prefix. Server đôi khi vẫn có thể quét index rộng, nhưng không nên giả định compound index tự tối ưu mọi tập con field.

Quy tắc định hướng **Equality → Sort → Range (ESR)** hữu ích khi thiết kế index cho nhiều điều kiện, nhưng phải xét tính chọn lọc, phân bố dữ liệu và sort thật. Trong một số workload range cực kỳ chọn lọc, thứ tự **ERS** có thể tốt hơn. Hãy đo trên workload thay vì chỉ áp dụng thứ tự cố định.

### 4.4. So sánh các truy vấn và index ứng viên

| Pipeline/filter | Index ứng viên | Lý do |
|---|---|---|
| `$match: {status:"PAID"}` | `{status:1}` | Equality trên status. |
| `$match: {tenantId:"T-A",status:"PAID"}` | `{tenantId:1,status:1}` | Compound equality. |
| `$match` tenant/status/date + `$sort` createdAt giảm | `{tenantId:1,status:1,createdAt:-1}` | Equality prefix, range/sort trên date. |
| `$match: {"items.sku":"BK-01"}` | `{"items.sku":1}` | Multikey index trên array field. |
| `$match: {region:"HN"}` | `{region:1}` | Equality trên region; chỉ tạo nếu workload cần. |
| `$match` theo year tạo bởi `$addFields` | Index `{createdAt:1}` không trực tiếp index computed year | Thường lọc range trên date gốc nếu tương đương. |

Tạo quá nhiều index tăng chi phí insert/update/delete và dung lượng lưu trữ. Một index hữu ích phục vụ **access pattern lặp lại**, không phải mọi field xuất hiện một lần trong pipeline.

## 5. `$match` kết hợp `$sort` và `$limit`

Một báo cáo thường cần **đơn PAID mới nhất** theo tenant:

~~~javascript
lab.orders.aggregate([
  { $match: { tenantId: "T-A", status: "PAID" } },
  { $sort: { createdAt: -1 } },
  { $limit: 3 },
  {
    $project: {
      _id: 1, createdAt: 1, region: 1, total: 1
    }
  }
])
// Dữ liệu mẫu: O-109, O-107, O-104.
~~~

Với compound index `{tenantId:1,status:1,createdAt:-1}`, planner có thể vừa định vị tập tenant/status vừa đi theo thứ tự createdAt. `$limit:3` giúp kết quả cuối nhỏ; nếu plan khai thác index sort hiệu quả, lượng tài liệu cần truy xuất cũng có thể giảm đáng kể.

### 5.1. Sort sớm nhưng match muộn có thể lãng phí

~~~javascript
lab.orders.aggregate([
  { $sort: { createdAt: -1 } },
  { $match: { tenantId: "T-A", status: "PAID" } },
  { $limit: 3 }
])
~~~

Về ngữ nghĩa, nếu filter chỉ dùng field gốc và không có stage làm thay đổi documents giữa hai bước, MongoDB có thể **tối ưu lại thứ tự `$sort` và `$match`** để giảm dữ liệu cần sort. Đừng đánh giá hiệu năng chỉ bằng việc đọc thứ tự source; hãy xem **optimized plan**.

Code chủ động viết `$match` trước `$sort` thường rõ ý hơn. Quan trọng hơn là tạo **index phù hợp với cả filter và sort**, vì dù sắp lại stage, thiếu index vẫn có thể khiến server phải scan/sort nhiều dữ liệu.

### 5.2. `$limit` trước `$match` làm thay đổi kết quả

So sánh:

~~~javascript
// A: lấy ba đơn mới nhất trong số các đơn PAID của tenant T-A.
lab.orders.aggregate([
  { $match: { tenantId: "T-A", status: "PAID" } },
  { $sort: { createdAt: -1 } },
  { $limit: 3 }
])
// O-109, O-107, O-104.

// B: lấy ba đơn mới nhất của toàn collection,
// rồi chỉ giữ những đơn PAID thuộc T-A.
lab.orders.aggregate([
  { $sort: { createdAt: -1 } },
  { $limit: 3 },
  { $match: { tenantId: "T-A", status: "PAID" } }
])
// O-109, O-107 (O-108 lọt top 3 nhưng bị loại).
~~~

Pipeline B không tương đương A vì `$limit` đã cắt tập dữ liệu **trước khi lọc**. Optimizer không thể tùy tiện hoán đổi `$match` qua `$limit` nếu làm đổi kết quả. Đây là một ví dụ quan trọng rằng “lọc sớm” phải giữ nguyên **ngữ nghĩa**.

### 5.3. Sort + limit có thể được tối ưu chung

MongoDB có optimization kết hợp `$sort` và `$limit` trong những trường hợp thích hợp, giúp sort giữ số kết quả cần thiết thay vì giữ toàn bộ dữ liệu. Nhưng tối ưu này không thay thế index: nếu có index hỗ trợ sort và match, engine có thể tránh một blocking sort tốn bộ nhớ.

Nếu pipeline có `$skip` rồi `$limit`, cần cân nhắc việc **skip sâu** có thể vẫn phải đi qua nhiều index keys/documents. Với pagination rất sâu, **keyset pagination** dựa trên `createdAt` cùng một khóa tie-breaker như `_id` thường đáng cân nhắc, thay vì tăng `$skip` liên tục.

### 5.4. Sort theo computed field thì sao?

~~~javascript
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  { $addFields: { shippingScore: { $multiply: ["$total", 0.01] } } },
  { $sort: { shippingScore: -1 } },
  { $limit: 3 }
])
~~~

Index trên `total` không mặc nhiên cung cấp trực tiếp thứ tự của `shippingScore` ở mọi biểu thức. Nếu sort phụ thuộc **field mới được tính trong pipeline**, thường phải tính giá trị rồi sort, trừ khi cấu trúc query/optimizer có cách tương đương được hỗ trợ. Đẩy `$match` trên các field gốc lên trước giúp hạn chế số document phải tính điểm/sort.

## 6. MongoDB optimizer có thể đẩy `$match` lên sớm đến đâu?

MongoDB thực hiện các phép **pipeline optimization** trước khi chạy. Ví dụ, một `$match` sau `$project` hoặc `$addFields` có thể được tách thành nhiều filter độc lập và chuyển từng phần lên trước những stage **không tạo/ghi đè field mà filter phụ thuộc**.

### 6.1. Ví dụ tách filter theo dependency

~~~javascript
lab.orders.aggregate([
  {
    $addFields: {
      discountAdjustedTotal: {
        $multiply: ["$total", 0.95]
      }
    }
  },
  {
    $match: {
      status: "PAID",
      tenantId: "T-A",
      discountAdjustedTotal: { $gte: 200000 }
    }
  }
])
~~~

Ba điều kiện có dependency khác nhau:

| Predicate | Phụ thuộc stage tính toán trước đó? | Khả năng đẩy lên sớm |
|---|---|---|
| `status = "PAID"` | Không | Có thể đẩy trước `$addFields` và tận dụng index. |
| `tenantId = "T-A"` | Không | Có thể đẩy trước `$addFields`. |
| `discountAdjustedTotal >= 200000` | **Có** | Phải ở sau lúc tính field này, trừ một phép biến đổi tương đương đặc biệt được optimizer chứng minh. |

Optimizer có thể tách filter thành một phần lọc theo `status`/`tenantId` trước và phần lọc computed total sau `$addFields`. Khi đọc code, không cần ép tất cả predicate vào một `$match` nếu làm mất tính rõ ràng:

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      tenantId: "T-A",
      status: "PAID"
    }
  },
  {
    $addFields: {
      discountAdjustedTotal: { $multiply: ["$total", 0.95] }
    }
  },
  {
    $match: {
      discountAdjustedTotal: { $gte: 200000 }
    }
  }
])
~~~

Phiên bản thứ hai thể hiện rõ **hai pha**: lọc bằng field có sẵn trước, tính dữ liệu phái sinh sau, rồi lọc theo kết quả tính toán.

### 6.2. `$project` bỏ field cũng thay đổi nơi filter có thể nằm

~~~javascript
lab.orders.aggregate([
  { $project: { region: 1, total: 1 } },
  { $match: { status: "PAID" } }
])
~~~

Nếu chỉ nhìn luồng dữ liệu theo thứ tự khai báo, `status` đã bị project bỏ, nên filter phía sau không còn thấy `status` như field gốc. Tuy nhiên optimizer **có thể đẩy** filter `status` lên trước projection nếu chứng minh an toàn. Không nên viết pipeline dựa vào giả định rằng optimizer luôn cứu một cấu trúc logic khó đọc; cách sáng sủa là:

~~~javascript
lab.orders.aggregate([
  { $match: { status: "PAID" } },
  { $project: { region: 1, total: 1 } }
])
~~~

Trong code review, hãy coi **dependency của field** là câu hỏi đầu tiên: tại thời điểm filter, field đó là field gốc, field đã bị bỏ, hay field mới tính?

### 6.3. `$addFields` ghi đè field thì không thể chuyển filter bừa

~~~javascript
lab.orders.aggregate([
  {
    $set: {
      status: { $toUpper: "$status" }
    }
  },
  {
    $match: {
      status: "PAID"
    }
  }
])
~~~

Ở đây `status` sau `$set` là **giá trị đã biến đổi**, không đơn giản là field gốc. Đẩy `$match` trước `$set` có thể đổi kết quả với dữ liệu gốc chứa `"paid"`. Vì vậy không được tự sắp lại chỉ để cố dùng index trên `status` nếu dữ liệu thực tế và quy tắc so sánh khác nhau.

Nếu muốn có truy vấn hiệu quả và nhất quán, nên chuẩn hóa dữ liệu khi ghi, dùng collation/index thích hợp hoặc thiết kế field canonical, thay vì bắt mọi pipeline tính lại chuẩn hóa khi đọc.

### 6.4. Giữa các `$match` độc lập, optimizer có thể gộp

~~~javascript
lab.orders.aggregate([
  { $match: { tenantId: "T-A" } },
  { $match: { status: "PAID" } },
  { $match: { createdAt: { $gte: start, $lt: end } } }
])
~~~

Các `$match` liên tiếp có thể được **coalesce/gộp** thành điều kiện tương đương. Vì vậy tách filter thành vài stage cho dễ quản lý không nhất thiết làm tăng số lượt đọc collection. Nhưng không suy rộng rằng MongoDB luôn gộp **mọi** filter xuyên qua `$unwind`, `$group` hoặc `$limit`; dependency và ranh giới ngữ nghĩa mới quyết định.

### 6.5. Optimizer không phải hợp đồng API về thứ tự stage cụ thể

MongoDB có thể thay đổi quy tắc rewrite giữa các phiên bản, query engine và tình huống. Tài liệu giải thích các tối ưu phổ biến, nhưng **không bảo đảm mã nguồn pipeline luôn được giữ nguyên hay luôn biến thành đúng một dạng tối ưu định trước**. Hãy kiểm tra `explain` của **server đang chạy** và đánh giá hiệu năng bằng dữ liệu đủ lớn.

## 7. `$match` trước và sau `$unwind`: dễ đổi ý nghĩa

`$unwind` biến **một document chứa array** thành **nhiều pipeline documents**, mỗi document mang một phần tử array. Đưa filter trước hoặc sau `$unwind` có thể trả về các đơn vị kết quả khác nhau.

### 7.1. Lọc trước unwind: chọn order có item cần tìm

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      "items.sku": "BK-01"
    }
  },
  {
    $unwind: "$items"
  },
  {
    $project: {
      _id: 1,
      sku: "$items.sku",
      qty: "$items.qty"
    }
  }
])
~~~

`$match` đầu tiên chọn **order** có *ít nhất một* item BK-01. Với fixture, các order đó là **O-101, O-104, O-105, O-107**. Nhưng `$unwind` tiếp theo sẽ tách **mọi item** của các order đó; kết quả vẫn có cả SKU PN-02/BK-03 của những order đã khớp, không chỉ BK-01.

Đây là một bẫy rất hay gặp: **lọc document cha trước `$unwind` không đồng nghĩa lọc phần tử sau `$unwind`**.

### 7.2. Lọc sau unwind: chọn từng dòng item BK-01

~~~javascript
lab.orders.aggregate([
  { $unwind: "$items" },
  { $match: { "items.sku": "BK-01" } },
  {
    $project: {
      _id: 1,
      sku: "$items.sku",
      qty: "$items.qty"
    }
  }
])
~~~

Ở đây `$match` chạy trên **mỗi dòng đã unwind**, nên chỉ giữ các dòng BK-01. Kết quả gồm item BK-01 của O-101, O-104, O-105 và O-107.

Tuy nhiên, một pipeline chỉ unwind rồi mới match có thể phải xử lý tất cả items trước khi lọc. Ta có thể kết hợp hai `$match` để vừa đúng ngữ nghĩa vừa giảm input.

### 7.3. Kết hợp lọc trước và sau unwind

~~~javascript
lab.orders.aggregate([
  // Chọn trước những order có thể chứa SKU cần tìm.
  { $match: { "items.sku": "BK-01" } },

  // Tách item trong những order đã chọn.
  { $unwind: "$items" },

  // Chỉ giữ đúng item BK-01.
  { $match: { "items.sku": "BK-01" } },

  {
    $group: {
      _id: "$items.sku",
      qtySold: { $sum: "$items.qty" },
      lineCount: { $sum: 1 }
    }
  }
])
// Trên fixture: _id BK-01, qtySold 12, lineCount 4.
~~~

Giải thích: 2 + 5 + 2 + 3 = **12 đơn vị BK-01** ở bốn order. `$match` trước unwind có thể sử dụng **multikey index** trên `items.sku`, còn `$match` sau unwind giữ đúng line items cho aggregation.

Nếu cần lọc **chính xác một item đáp ứng đồng thời nhiều điều kiện**, dùng `$elemMatch` ở pre-filter:

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      items: {
        $elemMatch: {
          sku: "BK-01",
          qty: { $gte: 3 }
        }
      }
    }
  },
  { $unwind: "$items" },
  {
    $match: {
      "items.sku": "BK-01",
      "items.qty": { $gte: 3 }
    }
  }
])
// Trong fixture: BK-01 ở O-104 và O-107.
~~~

Trước unwind, hai predicate dot notation riêng có thể khớp **hai item khác nhau**; `$elemMatch` bảo đảm cùng item. Sau unwind mỗi pipeline document chứa **một item**, nên các predicate trên `items.sku` và `items.qty` mô tả chính item đó.

### 7.4. Có thể bỏ `$match` sau unwind không?

Chỉ khi đầu ra cần **tất cả items** của những order chứa SKU mục tiêu. Nếu đầu ra là báo cáo **dòng BK-01**, bỏ filter sau unwind sẽ tính lẫn PN-02/BK-03. Mong muốn giảm stage không được ưu tiên hơn **ngữ nghĩa dữ liệu**.

### 7.5. Filter sau unwind có thể được optimizer đẩy trước không?

MongoDB có một số rewrite liên quan `$unwind`, `$lookup` và các `$match` tiếp theo. Nhưng filter trên phần tử đã tách **không thể nói chung** được hoán đổi với pre-filter mà giữ nguyên số dòng/output. Đừng dựa vào việc optimizer “tự hiểu” phải lọc item nào: hãy viết pipeline phản ánh rõ ranh giới **document cha** và **phần tử con**, rồi dùng explain để xác nhận plan.

## 8. `$match` trước và sau `$group`: hai loại điều kiện khác nhau

`$group` có thể tạo **document tổng hợp**, với `_id` và các giá trị accumulator. Sau stage đó, một field gốc chưa được giữ lại có thể không còn tồn tại.

### 8.1. Lọc trên document gốc trước `$group`

Yêu cầu: doanh thu mỗi region từ **đơn PAID tháng 6 của T-A**.

~~~javascript
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$total" },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { revenue: -1 } }
])
~~~

`$match` đầu pipeline loại đơn ngoài phạm vi. `$group` chỉ tính trên bốn đơn hợp lệ.

### 8.2. Lọc **giá trị tổng hợp** sau `$group`

Nếu thêm yêu cầu: “chỉ trả region có doanh thu PAID tháng 6 của T-A **trên 500.000**”:

~~~javascript
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$total" },
      orderCount: { $sum: 1 }
    }
  },
  { $match: { revenue: { $gt: 500000 } } },
  { $sort: { revenue: -1 } }
])
// Chỉ region SG, revenue 1.260.000.
~~~

`revenue` **chỉ tồn tại sau `$group`**. Không thể đưa `{revenue:{$gt:500000}}` lên đầu pipeline và đòi index trên `orders.revenue` hỗ trợ, vì đây là **kết quả tổng hợp của nhiều đơn** chứ không phải field gốc.

### 8.3. Đừng lọc mỗi đơn lớn hơn ngưỡng thay vì tổng nhóm

Hai mệnh đề khác nhau:

~~~text
A. "Chỉ nhóm region có TỔNG doanh thu > 500.000."
B. "Chỉ lấy các đơn ĐƠN LẺ có total > 500.000 rồi nhóm."
~~~

Pipeline A:

~~~javascript
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } },
  { $match: { revenue: { $gt: 500000 } } }
])
~~~

Pipeline B:

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      ...paidJuneTenantA,
      total: { $gt: 500000 }
    }
  },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } }
])
~~~

Trong fixture, pipeline B chỉ tính O-104 ở SG với 800.000; nó bỏ O-107 dù O-107 góp 460.000 vào doanh thu SG. Pipeline A cho SG 1.260.000. **Không đổi filter tổng nhóm thành filter từng document** chỉ để đẩy lên đầu/index.

### 8.4. Lọc theo khóa nhóm có thể tối ưu khác lọc accumulator

Đôi khi filter sau `$group` chỉ dùng **`_id` là khóa nhóm**, và có thể tương đương với việc lọc field gốc trước nhóm, ví dụ chỉ region HN. Optimizer có thể nhận ra một số trường hợp và đẩy predicate thích hợp. Nhưng nếu group tạo khóa qua biểu thức hoặc có ngữ nghĩa liên quan empty/missing, phải xét tương đương cẩn thận.

Ví dụ dạng chủ động lọc sớm:

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      ...paidJuneTenantA,
      region: "HN"
    }
  },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$total" }
    }
  }
])
~~~

Nếu mục tiêu chỉ là nhóm HN từ đầu, cách này giảm input. Nếu cần **xếp hạng toàn bộ nhóm trước rồi lấy HN**, thứ tự stage có thể mang ngữ nghĩa khác.

## 9. `$match` sau `$lookup` và quan hệ với index hai collection

`$lookup` thường lấy dữ liệu từ một collection khác để gắn thêm vào document đầu vào. Có **hai nơi khác nhau để lọc**:

1. Lọc document **nguồn** trước `$lookup`, có thể dùng index trên collection nguồn.
2. Lọc dữ liệu ở **collection được lookup**, với pipeline/điều kiện thích hợp, có thể dùng index ở collection bên kia.

### 9.1. Giảm input trước join

Giả sử có collection `customers` lưu `_id`, `name`, `tier`, còn `orders.customerId` là ID khách hàng. Có thể lọc bốn đơn PAID tháng 6 của T-A trước khi lookup customer:

~~~javascript
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $unwind: "$customer" },
  {
    $project: {
      _id: 1,
      total: 1,
      customerName: "$customer.name"
    }
  }
])
~~~

Index `{tenantId:1,status:1,createdAt:-1}` có thể hỗ trợ **lọc orders**; index mặc định `_id` trên `customers` có thể hỗ trợ **lookup theo foreignField**. Hai index phục vụ **hai phía khác nhau**; không có một index trên orders tự tối ưu mọi truy vấn vào customers.

Nếu cần filter thêm theo `customers.tier`, có thể cần thiết kế `$lookup.pipeline` cùng indexes phù hợp, tùy điều kiện join và server version. Trong pipeline của `$lookup`, một `$match` dùng `$expr` để so sánh field ở foreign collection với biến `let` có những **giới hạn index** riêng (ví dụ field–constant, biến được resolve thành constant và một số hạn chế về multikey). Không mặc định mọi `$expr` trong lookup đều dùng index.

### 9.2. Một pre-match không thể lọc field chỉ có sau lookup

~~~javascript
// Customer tier được lấy từ collection customers.
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $unwind: "$customer" },
  { $match: { "customer.tier": "GOLD" } }
])
~~~

Filter `"customer.tier"` không áp lên `orders` gốc vì field này chỉ xuất hiện sau join. Đẩy nó lên đầu pipeline sẽ không đúng. Một giải pháp hiệu năng có thể là **lọc tier sớm ngay trong foreign side** bằng `$lookup` dạng pipeline trong những trường hợp tương đương; cần kiểm tra join semantics, đặc biệt khi `preserveNullAndEmptyArrays`, left-outer join và cardinality làm thay đổi kết quả.

### 9.3. Một số stage có quy tắc phải đứng đầu

Không phải pipeline nào cũng cho `$match` đứng vị trí 0. Ví dụ:

- `$geoNear` là một stage cần đứng đầu theo giới hạn cú pháp thông thường; đưa những điều kiện địa lý và các predicate phù hợp vào tùy chọn `query` của `$geoNear` khi được hỗ trợ.
- `$search` (MongoDB Atlas Search) và `$vectorSearch` có những giới hạn vị trí và cú pháp riêng; thông thường chúng phải là stage đầu ở pipeline phù hợp, hoặc `$vectorSearch` có cách lọc bằng `filter` được hỗ trợ.
- Với `$text` trong aggregation, biểu thức `$match` có `$text` phải là **stage đầu** trong pipeline theo quy định, không dùng `$text` sau tùy ý những stage khác.

Vì vậy quy tắc tổng quát là **lọc tại thời điểm sớm nhất được phép và còn tương đương về ngữ nghĩa**, chứ không phải “`$match` luôn phải là stage đầu tuyệt đối”.

## 10. `$facet` và việc lọc chung trước nhiều nhánh

`$facet` cho phép chạy nhiều sub-pipelines trên **cùng tập document đầu vào**, thường dùng để vừa thống kê vừa trả một danh sách. Nếu mọi nhánh chỉ cần cùng phạm vi tenant/thời gian, lọc trước `$facet` giúp giảm khối lượng đầu vào của tất cả nhánh.

~~~javascript
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  {
    $facet: {
      summary: [
        {
          $group: {
            _id: null,
            revenue: { $sum: "$total" },
            count: { $sum: 1 }
          }
        }
      ],
      byRegion: [
        {
          $group: {
            _id: "$region",
            revenue: { $sum: "$total" }
          }
        },
        { $sort: { revenue: -1 } }
      ],
      recent: [
        { $sort: { createdAt: -1 } },
        { $limit: 2 },
        { $project: { _id: 1, createdAt: 1, total: 1 } }
      ]
    }
  }
])
~~~

`$match` ngoài `$facet` có cơ hội dùng index trên collection gốc. Theo tài liệu MongoDB, nếu `$facet` là **stage đầu** thì nó có thể phải thực hiện **collection scan**; khi `$match` hoặc `$sort` trước nó đã khai thác index, `$facet` nhận kết quả từ upstream thay vì khởi động scan riêng.

### 10.1. Đừng lọc chung nếu các nhánh cần tập dữ liệu khác nhau

Nếu nhánh `summary` muốn **tất cả trạng thái**, còn nhánh `recentPaid` chỉ muốn PAID, đặt `$match:{status:"PAID"}` ngoài facet sẽ làm sai `summary`. Khi đó:

~~~javascript
lab.orders.aggregate([
  // Điều kiện chung thật sự cho mọi nhánh:
  {
    $match: {
      tenantId: "T-A",
      createdAt: { $gte: start, $lt: end }
    }
  },
  {
    $facet: {
      allStatuses: [
        { $group: { _id: "$status", count: { $sum: 1 } } }
      ],
      paid: [
        { $match: { status: "PAID" } },
        { $group: { _id: null, revenue: { $sum: "$total" } } }
      ]
    }
  }
])
~~~

**Lọc chung sớm, lọc riêng trong nhánh** là mô hình dễ hiểu. Subpipeline `$match` của `$facet` không tự “khởi động lại” scan collection từ index gốc theo cách như một pipeline độc lập: nó nhận **document đã được facet phân phối**.

### 10.2. Giới hạn bộ nhớ của facet

`$facet` có các giới hạn bộ nhớ/kích thước output riêng; lọc sớm giúp giảm input nhưng không tự xóa mọi nguy cơ khi mỗi nhánh tạo ra mảng kết quả quá lớn. Phân trang, giới hạn dữ liệu output và quan sát execution là cần thiết, nhất là khi phân tích trên collection lớn.

## 11. Dùng `explain` để kiểm tra `$match` có tận dụng index không

**Đo và quan sát**, thay vì suy đoán từ pipeline. Trong `mongosh`, dùng:

~~~javascript
const lab = db.getSiblingDB("agg_match_lab")

const pipeline = [
  {
    $match: {
      tenantId: "T-A",
      status: "PAID",
      createdAt: {
        $gte: ISODate("2026-06-01T00:00:00Z"),
        $lt: ISODate("2026-07-01T00:00:00Z")
      }
    }
  },
  { $sort: { createdAt: -1 } },
  { $project: { _id: 1, createdAt: 1, region: 1, total: 1 } }
]

printjson(
  lab.orders.explain("executionStats").aggregate(pipeline)
)
~~~

`executionStats` yêu cầu thông tin thống kê execution ngoài kế hoạch. `queryPlanner` chủ yếu cho biết đường planner chọn; `allPlansExecution` có thể cung cấp dữ liệu về nhiều candidate plans ở các ngữ cảnh hỗ trợ.

### 11.1. Nhìn vào đâu trong explain?

| Khái niệm | Cách hiểu |
|---|---|
| **`COLLSCAN`** | Đọc document bằng collection scan. Không đồng nghĩa chắc chắn chậm; với tập rất nhỏ hoặc filter kém chọn lọc có thể hợp lý. |
| **`IXSCAN`** | Quét index keys theo index được chọn. |
| **`FETCH`** | Đọc document thực từ collection sau index scan khi còn cần field/kiểm tra khác. |
| **`PROJECTION`** | Chỉ chọn/tính một số field output; biểu diễn cụ thể tùy engine. |
| **`SORT`** | Có thao tác sort trong plan; có thể là blocking sort nếu không phục vụ từ thứ tự index. |
| **`DISTINCT_SCAN`** | Một kiểu index scan đặc thù, có thể được dùng cho một số pattern distinct/group tối ưu. |
| **`totalKeysExamined`** | Tổng số index keys mà execution đã xem trong phần kế hoạch tương ứng. |
| **`totalDocsExamined`** | Tổng số document đọc/kiểm tra trong phần execution tương ứng. |
| **`nReturned`** | Số document được trả về tại mức thống kê tương ứng. |
| **`indexBounds`** | Những khoảng khóa index được quét cho từng field. |

Các trường này có thể nằm ở **`queryPlanner`, `executionStats`, `stages`, `winningPlan` hoặc `queryPlan` lồng bên trong**, tùy pipeline, SBE/classic engine và phiên bản. Một số `$group`/`$sort` được thể hiện bằng các execution stages khác tên ở các bản mới; không viết chương trình đọc explain bằng một đường JSON cố định mà chưa kiểm tra server.

### 11.2. Cách đọc một số tình huống

~~~text
Tình huống A:
  COLLSCAN
  docsExamined: 1,000,000
  nReturned: 1,200

Tình huống B:
  IXSCAN -> FETCH
  keysExamined: 1,350
  docsExamined: 1,210
  nReturned: 1,200
~~~

Nếu đây là hai execution plans **thực sự tương đương** và dữ liệu được đo cùng điều kiện, kế hoạch B có thể giảm I/O đáng kể. Nhưng các con số chỉ là **minh họa khái niệm**, không phải explain được sinh từ fixture chín document của bài. Không suy ra latency giảm đúng bằng tỷ lệ docs examined; còn có tác động của cache, network, CPU, index size, contention và aggregation sau match.

Một plan có `IXSCAN` nhưng `keysExamined` rất lớn so với `nReturned` vẫn có thể không tốt. Ví dụ index chỉ trên field `status`, trong khi 90% đơn có status PAID, có thể phải quét phần lớn index và fetch nhiều document.

### 11.3. Một số câu hỏi khi đọc explain

1. Server đã chọn **index nào**? Có đúng kỳ vọng không?
2. `$match` trên field gốc đã được đẩy vào **cursor/query plan** hay vẫn xử lý sau các stage?
3. Có `SORT` tốn tài nguyên dù đã có index phục vụ thứ tự không?
4. Có `FETCH` nhiều document không? Projection đã giảm dữ liệu truyền đi nhưng chưa giảm số document phải fetch?
5. Số `keysExamined/docsExamined` có hợp lý so với `nReturned` và selectivity không?
6. Trên sharded cluster, query có **target đúng shard** hay phải fan out?
7. Chạy lại trên dữ liệu đủ lớn và tương đương production thì plan có thay đổi không?

### 11.4. So sánh pipeline trước và sau khi đổi thứ tự

~~~javascript
const lab = db.getSiblingDB("agg_match_lab")

const late = [
  { $project: {
      tenantId: 1, status: 1, createdAt: 1,
      total: 1, region: 1
  } },
  { $match: paidJuneTenantA },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } }
]

const early = [
  { $match: paidJuneTenantA },
  { $project: { total: 1, region: 1 } },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } }
]

printjson(lab.orders.explain("executionStats").aggregate(late))
printjson(lab.orders.explain("executionStats").aggregate(early))
~~~

Nếu optimizer có thể đẩy `$match` trước projection trong cả hai pipeline, các plan có thể **rất giống nhau**. Đây là kết quả hợp lý: MongoDB đã tối ưu giúp bạn. Giá trị của việc viết rõ early match là tính dễ hiểu và kiểm soát, chứ không phải mọi trường hợp sẽ thấy thay đổi lớn về execution stats.

### 11.5. `hint` để kiểm tra một index ứng viên

`aggregate()` hỗ trợ tùy chọn `hint` đối với phép đọc collection ban đầu trong những ngữ cảnh/phiên bản cho phép:

~~~javascript
lab.orders.aggregate(
  [
    { $match: paidJuneTenantA },
    { $sort: { createdAt: -1 } }
  ],
  {
    hint: "ix_tenant_status_createdAt_desc"
  }
)
~~~

Hoặc đặt hint trong phép explain bằng API phù hợp với phiên bản shell/driver. **`hint` không tạo index**; nếu chỉ định index không tồn tại hoặc không thích hợp, command có thể thất bại hay hoạt động kém. Tùy chọn hint trên aggregation áp dụng cho **collection nguồn**, không tự điều khiển index được chọn bên trong mọi `$lookup`/$unionWith`.

**Không nên pin index chỉ vì một explain đơn lẻ:** index/khối lượng dữ liệu thay đổi có thể khiến hint tệ hơn planner tự chọn. Hãy dùng hint khi cần điều khiển execution có lý do và đã đo hiệu năng.

### 11.6. `allowDiskUse` không phải thay thế cho filter/index tốt

Một số aggregation stages như `$sort` hoặc `$group` có thể dùng nhiều bộ nhớ; theo phiên bản/cấu hình, các thao tác phù hợp có thể **spill to disk** khi được phép. Tùy chọn `allowDiskUse` và cấu hình `allowDiskUseByDefault` thay đổi theo MongoDB version, nhưng dù có spill thì việc xử lý hàng triệu document không cần thiết vẫn tốn I/O.

~~~javascript
lab.orders.aggregate(
  [
    { $match: paidJuneTenantA },
    { $group: { _id: "$customerId", total: { $sum: "$total" } } },
    { $sort: { total: -1 } }
  ],
  { allowDiskUse: true }
)
~~~

`allowDiskUse: true` chỉ là cách cho phép dùng tài nguyên đĩa trong những giai đoạn được hỗ trợ, **không thay thế việc lọc sớm, đặt index hợp lý hay giảm kích thước tập input**.

## 12. Những tình huống index không được dùng như kỳ vọng

### 12.1. Filter kém chọn lọc

Nếu 99% đơn có `status:"PAID"`, index chỉ trên `status` không giúp loại được nhiều document. Planner có thể chọn collection scan hợp lý, hoặc index scan nhưng vẫn fetch phần lớn dữ liệu.

Ngược lại, filter kết hợp `tenantId`, `status` và khoảng `createdAt` có thể chỉ chọn một phần nhỏ. Điều này giải thích vì sao compound index dựa trên **access pattern** thường hiệu quả hơn index một field có cardinality thấp.

### 12.2. Đường dẫn/kiểu BSON không khớp

~~~javascript
// Dữ liệu dùng BSON Date:
{ createdAt: ISODate("2026-06-01T08:00:00Z") }

// Filter sau dùng string, không phải cùng BSON type:
{ createdAt: "2026-06-01" }
~~~

Index không thể “sửa” lỗi ngữ nghĩa về kiểu dữ liệu. MongoDB sử dụng BSON comparison rules; các so sánh khác kiểu có hành vi theo operator và type bracketing. Với yêu cầu date range, phải truy vấn bằng Date tương ứng.

Nếu legacy data trộn string/date trong cùng field, nên migrate schema hoặc tách xử lý, không tạo index rồi kỳ vọng một range query tự hiểu cả hai kiểu.

### 12.3. Biểu thức tính toán trên field

~~~javascript
// Filter trực tiếp (ứng viên tốt cho index total):
{ $match: { total: { $gte: 500000 } } }

// Tính toán theo expression trước rồi lọc:
{
  $match: {
    $expr: {
      $gte: [
        { $multiply: ["$total", 1.1] },
        550000
      ]
    }
  }
}
~~~

Hai điều kiện có thể tương đương trong một domain numeric đã được kiểm soát, nhưng dạng `$expr` có phép nhân **không mặc nhiên dùng được index bounds của `total`** như predicate trực tiếp. Một số `$expr` comparison đơn giản có thể được tối ưu/index hỗ trợ trong ngữ cảnh nhất định, nhưng không nên suy rộng tới mọi biểu thức.

Trước khi rewrite, kiểm tra **kiểu số**, precision/rounding, null/missing và điều kiện biên; đừng đổi một expression phức tạp thành predicate trực tiếp nếu làm sai nghiệp vụ.

### 12.4. Case-insensitive regex và collation

~~~javascript
// Regex theo prefix có thể có index bounds hữu ích
// trên index string phù hợp trong một số tình huống.
{ $match: { customerId: /^C-/ } }

// Case-insensitive regex không tự tận dụng index
// case-insensitive collation theo cách bạn có thể kỳ vọng.
{ $match: { customerId: /^c-/i } }
~~~

Với query string case-insensitive thường xuyên, cân nhắc **collation có index tương ứng** hoặc field canonical phù hợp. Không kết luận “có index trên customerId thì mọi regex đều nhanh”, đặc biệt với pattern không anchored hoặc có ký tự wildcard ở đầu.

### 12.5. Partial index chỉ áp dụng khi filter bao hàm điều kiện

~~~javascript
lab.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  {
    name: "ix_paid_tenant_date",
    partialFilterExpression: { status: "PAID" }
  }
)
~~~

Index này chỉ chứa đơn **PAID**. Query:

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      tenantId: "T-A",
      status: "PAID",
      createdAt: { $gte: start, $lt: end }
    }
  }
])
~~~

là ứng viên dùng partial index vì nó bao hàm `status:"PAID"`. Nhưng query chỉ tìm `tenantId:"T-A"`, bất kể status, **không thể mặc nhiên** dùng partial index làm nguồn dữ liệu đầy đủ vì nó bỏ qua đơn CREATED/CANCELLED.

**Partial index** có thể giảm kích thước index và chi phí query phù hợp, nhưng cần xem tác động khi business status đổi, query lọc nhiều trạng thái hoặc plan không thỏa điều kiện dùng index.

### 12.6. Collation index và collation của query

Nếu index trên `customerName` có collation `{locale:"en", strength:2}`, query so sánh chuỗi bằng collation khác có thể không dùng index để so sánh string theo cùng cách. Cần thiết kế collation từ **quy tắc so sánh nghiệp vụ** và truyền collation phù hợp khi cần:

~~~javascript
lab.orders.aggregate(
  [{ $match: { customerName: "an" } }],
  { collation: { locale: "en", strength: 2 } }
)
~~~

Ví dụ chỉ minh họa cú pháp; fixture không có `customerName`, nên nó không trả kết quả trên dữ liệu hiện tại. Không tạo index theo collation rồi giả định mọi query mặc định đã đổi cách so sánh.

### 12.7. Multikey index và nhiều điều kiện lên array

~~~javascript
lab.orders.createIndex(
  { "items.sku": 1, "items.qty": 1 },
  { name: "ix_item_sku_qty" }
)
~~~

Hai điều kiện dot notation:

~~~javascript
{
  $match: {
    "items.sku": "BK-01",
    "items.qty": { $gte: 3 }
  }
}
~~~

có thể khớp **hai items khác nhau** trong cùng order. Nếu nghiệp vụ muốn cùng một item, cần:

~~~javascript
{
  $match: {
    items: {
      $elemMatch: {
        sku: "BK-01",
        qty: { $gte: 3 }
      }
    }
  }
}
~~~

`$elemMatch` vừa làm ngữ nghĩa đúng, vừa có thể giúp planner **ghép compound multikey index bounds** khi những predicate cùng ranh giới array. Với multikey index có hạn chế về covered queries và compound parallel arrays; không tự suy rằng index này phù hợp cho mọi trường hợp array lồng nhiều cấp.

### 12.8. Index không thay thế quyền và filter tenant

Trên một ứng dụng multi-tenant, mọi truy vấn cần lọc `tenantId` từ **ngữ cảnh phân quyền đáng tin**, không đơn giản tin vào tenantId do client tùy ý gửi. Đặt `$match` tenant sớm giúp targeted query và giảm input, nhưng **không thay authorization**. Nếu một pipeline lookup/group bỏ sót tenant filter ở nhánh khác, index nhanh không khiến truy vấn trở nên an toàn về phân tách dữ liệu.

### 12.9. Sharding và shard-key targeting

Trên sharded collection, query có điều kiện phù hợp với **shard key** có thể được router hướng đến các shard cần thiết thay vì gửi tới tất cả shard. `$match` chứa shard-key predicate sớm có thể rất quan trọng cho hiệu năng. Nhưng tác động còn phụ thuộc shard key pattern, range/hashed routing, cách phân phối chunks, version và pipeline optimizer.

Trên `explain` của sharded aggregation, cần quan sát **những shard tham gia**, `SHARD_MERGE` hoặc các stage liên quan thay vì chỉ nhìn `IXSCAN` của một shard. Không mặc nhiên cho rằng filter theo `tenantId` luôn targeted nếu collection không shard theo tenantId hoặc field không đủ shard key.

## 13. Ngữ nghĩa `$match`: thêm những giới hạn và bẫy cần biết

### 13.1. Query predicate không phải aggregation expression

Trong `$match`, cú pháp sau dùng **query operator**:

~~~javascript
{
  $match: {
    total: { $gte: 500000 }
  }
}
~~~

Nếu cần so sánh **hai field trong cùng document** hoặc tính giá trị bằng aggregation expression, dùng `$expr`:

~~~javascript
{
  $match: {
    $expr: {
      $gt: ["$total", "$creditLimit"]
    }
  }
}
~~~

Filter thứ hai có ý nghĩa “total lớn hơn creditLimit của document này”. Dấu `"$total"` là **field path expression** trong aggregation language, khác với key `total` của query syntax. Tùy biểu thức, `$expr` có thể không tận dụng được index bounds như predicate trực tiếp; phải xem explain.

### 13.2. Đừng đưa biểu thức từ stage `$project` vào `$match` như query syntax

Sai ý định:

~~~javascript
// $toUpper không phải cách khai báo field predicate trực tiếp như thế này.
{
  $match: {
    status: { $toUpper: "$status" }
  }
}
~~~

Đúng khi mục đích là so sánh status sau khi chuyển thành chữ hoa:

~~~javascript
{
  $match: {
    $expr: {
      $eq: [{ $toUpper: "$status" }, "PAID"]
    }
  }
}
~~~

Nhưng nếu dữ liệu đã được chuẩn hóa về trạng thái uppercase, filter trực tiếp `{status:"PAID"}` thường dễ dùng index hơn. Nếu yêu cầu là so sánh chuỗi case-insensitive mà vẫn dùng index, xem xét collation/canonical key thay vì tính lại `$toUpper` cho từng document.

### 13.3. `$match` không có nghĩa giống SQL HAVING trong mọi vị trí

Trong SQL, ta hay phân biệt WHERE (lọc dòng gốc) và HAVING (lọc nhóm). Aggregation MongoDB dùng **cùng tên `$match`**:

~~~javascript
// Tương tự WHERE: lọc orders trước khi nhóm.
{ $match: { status: "PAID" } }

// Tương tự HAVING: lọc kết quả sau $group.
{ $match: { revenue: { $gt: 500000 } } }
~~~

Sự khác nhau nằm ở **vị trí và hình dạng document** đang chạy qua pipeline, không phải tên stage. Một `$match` ở đầu tìm kiếm `status` trong orders; một `$match` sau group kiểm tra `revenue` do group tạo.

### 13.4. Null, missing và array paths

Trong MongoDB query language:

~~~javascript
{ $match: { optionalField: null } }
~~~

thường khớp document có field **explicit null** hoặc **không có field**, tùy đường dẫn/ngữ cảnh. Nếu mục đích là “field không tồn tại”:

~~~javascript
{ $match: { optionalField: { $exists: false } } }
~~~

Nếu mục đích là “field tồn tại và là BSON null”:

~~~javascript
{ $match: { optionalField: { $type: "null" } } }
~~~

Với đường dẫn qua array, nhiều điều kiện dot notation có thể được thỏa bởi **các phần tử khác nhau**. Muốn cùng phần tử, dùng `$elemMatch` như mục 7. Đây không chỉ là vấn đề hiệu năng/index, mà là **tính đúng đắn** của filter.

### 13.5. Những operator không thể dùng tùy ý trong `$match`

`$match` hỗ trợ nhiều query operators, nhưng có giới hạn:

- **`$where`** không được dùng trong `$match`.
- **`$near` và `$nearSphere`** không dùng trong `$match` theo cách thông thường; xem `$geoNear` hoặc predicate địa lý được hỗ trợ như `$geoWithin`, tùy mục đích.
- **`$text` trong `$match` phải ở stage đầu** theo quy tắc aggregation text search; không tùy ý đặt sau `$project` hoặc `$group`.
- Một số stage tìm kiếm chuyên biệt của Atlas có ràng buộc vị trí riêng, như đã đề cập ở mục 9.

Việc biết giới hạn cú pháp giúp tránh biến mẹo “đưa match lên đầu” thành một pipeline server không chấp nhận.

### 13.6. `$match` với biểu thức trên kết quả computed field

Ví dụ tính giá trị của đơn sau discount:

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      tenantId: "T-A",
      status: "PAID"
    }
  },
  {
    $addFields: {
      amountAfterDiscount: {
        $multiply: ["$total", 0.9]
      }
    }
  },
  {
    $match: {
      amountAfterDiscount: { $gte: 300000 }
    }
  },
  {
    $project: {
      _id: 1, total: 1, amountAfterDiscount: 1
    }
  }
])
~~~

Hai `$match` có **vai trò khác nhau**: đầu tiên có thể tận dụng compound index theo tenant/status; thứ hai phải xét trường tính toán để trả những đơn đạt ngưỡng. Đây là một pipeline hợp lý ngay cả khi không thể đẩy mọi điều kiện lên đầu.

## 14. Viết pipeline hiệu quả với MongoDB Java Sync Driver

Trong Java Sync Driver, `MongoCollection.aggregate()` nhận danh sách `Bson` stages. Các builders như `Aggregates.match`, `Filters.and`, `Filters.eq`, `Filters.gte`, `Filters.lt`, `Indexes.compoundIndex` giúp xây cú pháp tương đương `mongosh` nhưng có kiểm tra kiểu API ở compile time.

### 14.1. Chuyển `$match` + `$sort` + `$limit` sang Java

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.time.Instant;
import java.util.Arrays;
import java.util.Date;
import java.util.List;

import static com.mongodb.client.model.Aggregates.limit;
import static com.mongodb.client.model.Aggregates.match;
import static com.mongodb.client.model.Aggregates.project;
import static com.mongodb.client.model.Aggregates.sort;
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Filters.lt;
import static com.mongodb.client.model.Projections.fields;
import static com.mongodb.client.model.Projections.include;
import static com.mongodb.client.model.Sorts.descending;

// Giả sử database là MongoDatabase đã trỏ tới "agg_match_lab".
MongoCollection<Document> orders = database.getCollection("orders");

Date start = Date.from(Instant.parse("2026-06-01T00:00:00Z"));
Date end = Date.from(Instant.parse("2026-07-01T00:00:00Z"));

Bson matchFilter = and(
    eq("tenantId", "T-A"),
    eq("status", "PAID"),
    gte("createdAt", start),
    lt("createdAt", end)
);

List<Bson> pipeline = Arrays.asList(
    match(matchFilter),
    sort(descending("createdAt")),
    limit(3),
    project(include("_id", "createdAt", "region", "total"))
);

orders.aggregate(pipeline).forEach(System.out::println);
~~~

**Lưu ý về imports:** Không nên static import đồng thời `Indexes.descending` và `Sorts.descending` khi không cần thiết, vì dễ gây nhầm lẫn tên builder. Ví dụ dùng `Sorts.descending` cho `$sort`; khi tạo index bên dưới, gọi `Indexes.descending` qua tên class đầy đủ để diễn đạt đúng mục đích.

### 14.2. Tạo compound index trong Java

~~~java
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;

orders.createIndex(
    Indexes.compoundIndex(
        Indexes.ascending("tenantId", "status"),
        Indexes.descending("createdAt")
    ),
    new IndexOptions().name("ix_tenant_status_createdAt_desc")
);
~~~

Ví dụ mô tả **key pattern**, không chứng minh planner luôn chọn index. Sau khi tạo, chạy explain trên server thật và xem workload. Nếu collection đã có index tương đương, không nên tạo index trùng chỉ khác tên mà không xem chi phí.

### 14.3. Aggregation trong Java có `$group`

~~~java
import static com.mongodb.client.model.Aggregates.group;
import static com.mongodb.client.model.Accumulators.sum;

orders.aggregate(Arrays.asList(
    match(matchFilter),
    group(
        "$region",
        sum("revenue", "$total"),
        sum("orderCount", 1)
    )
)).forEach(System.out::println);
~~~

Kết quả tương ứng nhóm SG và HN ở mục 3. Với API Java, `group` tạo stage tổng hợp; `match` đầu tiên vẫn là bộ lọc trên document gốc.

### 14.4. Khi dùng Spring Data MongoDB

Spring Data có DSL như `Aggregation.match(Criteria.where(...))`. Ý nghĩa vẫn giống:

~~~java
import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;
import org.springframework.data.mongodb.core.query.Criteria;

var aggregation = newAggregation(
    match(
        Criteria.where("tenantId").is("T-A")
            .and("status").is("PAID")
            .and("createdAt").gte(start).lt(end)
    ),
    group("region").sum("total").as("revenue"),
    sort(org.springframework.data.domain.Sort.Direction.DESC, "revenue")
);
~~~

Đây là **minh họa DSL**, cần kiểm tra phiên bản Spring Data MongoDB của dự án khi dùng trong code. Nếu framework có entity field mapping, alias hoặc converter đặc biệt, hãy hiểu BSON pipeline thực tế. Không dựa vào code nhìn giống `$match` mà mặc định nó lọc đúng field name được lưu trong MongoDB.

### 14.5. Vì sao quan hệ với index không phụ thuộc framework?

Cho dù filter được tạo từ `mongosh`, Java Driver, Spring Data hay một service ngôn ngữ khác, MongoDB Server vẫn nhận **BSON query/pipeline**. Query planner chọn index dựa trên **dữ liệu và biểu thức thực tế** chứ không dựa vào việc ứng dụng dùng builder nào. Vì vậy cần quan sát pipeline BSON thực tế và server `explain` khi debug performance.

## 15. Phương pháp tối ưu theo từng bước

Một quy trình cân bằng **tính đúng đắn** và **hiệu năng**:

### Bước 1 — Ghi rõ kết quả nghiệp vụ

Ví dụ:

~~~text
Tính doanh thu từng region của các đơn PAID
thuộc tenant T-A được tạo trong tháng 6/2026 (theo UTC).
Chỉ trả những region có tổng doanh thu > 500.000,
sắp xếp theo doanh thu giảm dần.
~~~

Phân loại:

| Điều kiện | Áp lên dữ liệu nào? | Vị trí hợp lý |
|---|---|---|
| tenantId = T-A | Document gốc | `$match` đầu tiên. |
| status = PAID | Document gốc | `$match` đầu tiên. |
| createdAt trong tháng 6 | Document gốc | `$match` đầu tiên. |
| group by region | Tập đã lọc | `$group`. |
| revenue > 500.000 | **Kết quả nhóm** | `$match` sau `$group`. |
| sort revenue giảm | **Kết quả nhóm** | `$sort` sau nhóm/filter doanh thu. |

### Bước 2 — Viết pipeline đơn giản, đúng ngữ nghĩa

~~~javascript
const pipeline = [
  { $match: paidJuneTenantA },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$total" },
      orders: { $sum: 1 }
    }
  },
  { $match: { revenue: { $gt: 500000 } } },
  { $sort: { revenue: -1 } }
]

lab.orders.aggregate(pipeline)
~~~

### Bước 3 — Xác định query/access pattern lặp lại

Nếu nhiều endpoint liên tục lọc tenant/status/date rồi sort theo createdAt, compound index `{tenantId:1,status:1,createdAt:-1}` là ứng viên tự nhiên. Nhưng nếu phần lớn các query chỉ dùng `region`, một index khác có thể phục vụ tốt hơn. Đừng tạo index chỉ dựa vào một pipeline thử nghiệm hiếm khi chạy.

### Bước 4 — Dùng `explain` và đo

~~~javascript
printjson(lab.orders.explain("executionStats").aggregate(pipeline))
~~~

Đọc stage scan, indexName/indexBounds, keys/docs examined, số document đi vào `$group`, sort stage và tổng latency. Với dataset thật, so sánh các phương án trên cùng workload tương đương; không đọc một con số `executionTimeMillis` đơn lẻ rồi quyết định index tối ưu.

### Bước 5 — Quan sát khi rollout

- **Throughput/latency:** p50/p95/p99 của báo cáo hay API.
- **Index size, write overhead:** index mới có tăng chi phí ghi đáng kể không?
- **CPU/I/O/cache:** liệu giảm docsExamined có giảm tải thật?
- **Spill/disk usage:** `$group` hoặc `$sort` có cần đĩa tạm?
- **Cardinality và data skew:** một tenant cực lớn có thể không giống tenant trong test.
- **Sharding/replication:** query có target đúng shard? Aggregation có fan out hoặc merge tốn kém?
- **Tính đúng đắn:** nhóm/tổng/số đơn có còn giống yêu cầu, đặc biệt sau khi chuyển vị trí `$match`?

### Bước 6 — Chỉ tối ưu tiếp khi có bottleneck thật

Sau khi đã match sớm và có index phù hợp, nếu bottleneck nằm ở `$lookup`/`$group` hoặc lượng output, có thể cần thay đổi pipeline, pre-aggregation, caching hoặc mô hình dữ liệu. Thêm nhiều `$match` không tự giải quyết bài toán nếu filter vốn đã chọn gần như toàn bộ collection.

## 16. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “`$match` luôn phải là stage 0.” | Một số stage có yêu cầu đứng đầu; filter trên field computed hoặc sau unwind/group có dependency phải tôn trọng. |
| “Cứ có `$match` đầu thì MongoDB chắc chắn dùng index.” | Planner có thể chọn `COLLSCAN` nếu index không hợp hoặc collection/filter không đủ chọn lọc. |
| “Index trên mọi field trong `$match` sẽ nhanh nhất.” | Index tăng chi phí ghi; cần chọn theo access patterns, prefix và thống kê thực tế. |
| “Index đơn field status đủ cho mọi báo cáo.” | Nếu status ít phân biệt, compound index trên tenant/status/date có thể hữu ích hơn. |
| “Đặt filter sau `$project` chắc chắn sẽ tính projection trước.” | Optimizer có thể đẩy các predicate độc lập lên trước; cần xem `explain`. |
| “Optimizer chắc chắn đẩy được mọi `$match` lên trước.” | Không thể đẩy điều kiện dựa trên field mới tạo hoặc qua ranh giới đổi ngữ nghĩa. |
| “Đặt `$match` trước `$limit` hay sau đều giống nhau.” | Không; lọc top N khác lấy top N trong tập đã lọc. |
| “`$match` trước `$unwind` chỉ giữ các item khớp.” | Nó chỉ chọn document cha; unwind sau đó có thể trả cả item khác. |
| “Bất kỳ filter sau `$unwind` đều nên xóa để tăng tốc.” | Filter sau unwind có thể cần để chọn đúng từng phần tử. |
| “Hai điều kiện `items.sku` và `items.qty` luôn cùng item.” | Có thể khớp hai phần tử; dùng `$elemMatch` khi cần cùng phần tử. |
| “`$match` tổng doanh thu > X có thể đưa trước `$group`.” | Nếu lọc trên accumulator của group thì phải giữ sau group. |
| “`$match` sau `$group` không bao giờ tối ưu sớm được.” | Filter chỉ theo khóa nhóm đôi khi có thể đẩy; xem dependency và optimizer. |
| “`$match` trước `$lookup` lọc được field bên foreign collection.” | Field từ lookup chỉ xuất hiện sau join, trừ khi đưa filter phù hợp vào foreign lookup pipeline. |
| “Index trên orders cũng tăng tốc mọi điều kiện trong `$lookup`.” | Lookup cần index thích hợp ở **foreign collection**; hai phía là hai access patterns. |
| “`$facet` đầu tiên vẫn sử dụng mọi index như query bình thường.” | `$facet` đầu có thể dẫn đến `COLLSCAN`; lọc/index ở upstream thường tốt hơn khi đúng ngữ nghĩa. |
| “`IXSCAN` chứng minh plan đã tối ưu.” | Cần xét `keysExamined`, `docsExamined`, `FETCH`, sort và latency. |
| “`hint` luôn nhanh hơn planner tự chọn.” | Hint có thể ép một index tệ, phải đo và xét phiên bản/dữ liệu. |
| “`allowDiskUse` giải quyết truy vấn chậm do lọc muộn.” | Chỉ xử lý khả năng dùng đĩa cho stage phù hợp; không loại bỏ công việc thừa. |
| “`$dateToString` rồi match tháng giống hệt range index về hiệu năng.” | Có thể đúng ý nghĩa nếu xử lý timezone cẩn thận, nhưng không trực tiếp tận dụng range index như filter trên Date gốc. |
| “`$expr` luôn dùng index như predicate field–constant thông thường.” | Hỗ trợ index phụ thuộc biểu thức/ngữ cảnh; cần đo trên server thực. |
| “Partial index luôn dùng được cho mọi query có field trong key.” | Query phải nằm trong tập được lập chỉ mục (bao hàm partial filter) để trả đủ kết quả. |
| “Collation của index tự áp cho mọi query.” | Query cần dùng collation tương thích khi so sánh string nếu muốn kết quả/index theo quy tắc đó. |
| “Query theo tenantId nhanh nghĩa là bảo mật tenant đúng.” | Phải lấy tenant identity từ authorization và áp filter đúng ở mọi nhánh. |
| “MongoDB shell và Java driver có execution plan khác chỉ vì cú pháp khác.” | Planner dựa trên BSON query/collection/index thực; khác biệt thường do pipeline/options/dữ liệu. |

## 17. Bài tập thực hành và đáp án gợi ý

Các bài tập dựa trên bộ dữ liệu chín orders ở mục 2, giả định chưa bị thay đổi. Có thể chạy lại trên collection thử nghiệm mới để đảm bảo fixture ban đầu. Mục tiêu là xác định **ngữ nghĩa của filter** và **cơ hội dùng index**, không cố đo tốc độ tuyệt đối với chín document.

### Bài 1 — Lọc sớm trước group

**Yêu cầu:** Đếm số đơn PAID của tenant T-A trong tháng 6/2026, nhóm theo region.

**Đáp án:**

~~~javascript
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  { $group: { _id: "$region", count: { $sum: 1 } } }
])
~~~

Kết quả: HN có **2** đơn và SG có **2** đơn. `$match` dùng field gốc nên có thể đặt trước group và trở thành ứng viên dùng index.

### Bài 2 — Doanh thu sau group

**Yêu cầu:** Chỉ trả region có doanh thu PAID tháng 6 của T-A lớn hơn 500.000.

**Đáp án:**

~~~javascript
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } },
  { $match: { revenue: { $gt: 500000 } } }
])
// Chỉ SG, 1.260.000.
~~~

Không đưa điều kiện `revenue > 500000` trước group vì revenue là **accumulator result**, không phải `total` của một order.

### Bài 3 — Lọc top ba đơn mới nhất

**Yêu cầu:** Ba đơn PAID mới nhất của T-A (không giới hạn tháng).

**Đáp án:**

~~~javascript
lab.orders.aggregate([
  { $match: { tenantId: "T-A", status: "PAID" } },
  { $sort: { createdAt: -1 } },
  { $limit: 3 }
])
// O-109, O-107, O-104.
~~~

Đổi `$limit` lên trước match sẽ thành “lọc trong ba đơn mới nhất toàn hệ thống”, không còn tương đương.

### Bài 4 — Chọn compound index

**Yêu cầu:** Nhiều báo cáo chạy filter `tenantId = T-A`, `status = PAID`, `createdAt` trong range và sắp theo createdAt giảm. Index nào là ứng viên hợp lý?

**Đáp án:**

~~~javascript
lab.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 }
)
~~~

Hai equality fields dẫn trước, createdAt phục vụ range/sort. Dùng `explain` với dữ liệu đại diện để đánh giá; không khẳng định duy nhất index này luôn tối ưu cho mọi query.

### Bài 5 — Filter sau unwind có thật sự cần?

~~~javascript
lab.orders.aggregate([
  { $match: { "items.sku": "BK-01" } },
  { $unwind: "$items" }
])
~~~

**Câu hỏi:** Kết quả có chỉ chứa items BK-01 không?

**Đáp án:** Không. Pre-match chỉ chọn các order **có ít nhất một BK-01**; unwind sẽ tách **mọi item** trong những order đó. Thêm `{ $match: {"items.sku":"BK-01"} }` sau unwind để chỉ giữ dòng BK-01.

### Bài 6 — Một phần tử thỏa cả hai điều kiện

**Yêu cầu:** Tìm order có item `sku = BK-01` và `qty >= 3` **trên cùng item**.

**Đáp án:**

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      items: {
        $elemMatch: {
          sku: "BK-01",
          qty: { $gte: 3 }
        }
      }
    }
  }
])
// O-104, O-107.
~~~

Hai điều kiện dot notation riêng có thể match khác item; `$elemMatch` thể hiện đúng bất biến. Index compound trên `items.sku`/`items.qty` có thể hữu ích theo giới hạn multikey.

### Bài 7 — Kết hợp hai bộ lọc quanh `$addFields`

**Yêu cầu:** Tìm những đơn PAID của T-A có tổng tiền sau giảm 10% ít nhất 300.000.

**Đáp án:**

~~~javascript
lab.orders.aggregate([
  { $match: { tenantId: "T-A", status: "PAID" } },
  {
    $addFields: {
      discountedTotal: { $multiply: ["$total", 0.9] }
    }
  },
  { $match: { discountedTotal: { $gte: 300000 } } },
  { $project: { _id: 1, discountedTotal: 1 } }
])
// O-104 (720.000) và O-107 (414.000).
~~~

Filter đầu có thể dùng index theo tenant/status; filter sau phụ thuộc field tính toán, nên giữ sau khi tạo field.

### Bài 8 — `$limit` có thể đặt đầu không?

Yêu cầu “lấy hai order PAID có tổng tiền cao nhất của T-A”. So sánh:

~~~javascript
// Đúng:
[
  { $match: { tenantId: "T-A", status: "PAID" } },
  { $sort: { total: -1 } },
  { $limit: 2 }
]

// Không tương đương:
[
  { $sort: { total: -1 } },
  { $limit: 2 },
  { $match: { tenantId: "T-A", status: "PAID" } }
]
~~~

**Đáp án:** Pipeline đầu chọn O-104 và O-107. Pipeline thứ hai chọn top hai đơn toàn collection trước, nên có thể loại một trong số đó sau filter; không đảm bảo trả đủ top hai trong tập được yêu cầu.

### Bài 9 — Giải thích `IXSCAN` và `FETCH`

Một explain có `IXSCAN` trên `{tenantId:1,status:1,createdAt:-1}` rồi `FETCH` document. Vì sao vẫn cần fetch?

**Đáp án:** Pipeline cần các field như `region` hoặc `total` không có trong index, hoặc cần xác minh predicate khác; engine phải đọc document gốc. Index scan chỉ chứng minh đã khai thác khóa index cho một phần xử lý.

### Bài 10 — `COLLSCAN` có luôn là lỗi không?

Trên fixture chín document, `explain` chọn `COLLSCAN` dù có index trên status. Có đủ căn cứ kết luận query performance kém không?

**Đáp án:** Không. Collection quá nhỏ hoặc predicate kém chọn lọc có thể khiến collection scan rẻ hơn. Đánh giá trên dữ liệu và workload đại diện, xem keys/docs examined, sort, latency và plan.

### Bài 11 — Partial index

Có index:

~~~javascript
lab.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  { partialFilterExpression: { status: "PAID" } }
)
~~~

**Câu hỏi:** Pipeline chỉ `$match:{tenantId:"T-A"}` có thể dùng index này làm nguồn đầy đủ cho mọi orders của tenant không?

**Đáp án:** Không. Index chỉ chứa đơn PAID; query không giới hạn status còn cần cả CREATED/CANCELLED. Query bao hàm `status:"PAID"` là ứng viên phù hợp hơn.

### Bài 12 — `$facet` hai phạm vi

**Yêu cầu:** Trong tháng 6 của T-A, một nhánh đếm **mọi trạng thái**, một nhánh chỉ tính doanh thu PAID.

**Đáp án:**

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      tenantId: "T-A",
      createdAt: { $gte: start, $lt: end }
    }
  },
  {
    $facet: {
      statusCounts: [
        { $group: { _id: "$status", count: { $sum: 1 } } }
      ],
      paidRevenue: [
        { $match: { status: "PAID" } },
        { $group: { _id: null, revenue: { $sum: "$total" } } }
      ]
    }
  }
])
~~~

Đặt status PAID ở pre-match chung sẽ làm nhánh statusCounts **mất dữ liệu CREATED/CANCELLED**.

### Bài 13 — Lọc sau lookup

Một pipeline lookup customers rồi lọc `customer.tier:"GOLD"`. Vì sao không thể chỉ chuyển filter này lên trước lookup để dùng index trên orders?

**Đáp án:** `customer.tier` không có trên document orders gốc; nó xuất hiện sau join. Có thể tối ưu bằng filter trên foreign side với `$lookup.pipeline` và index phù hợp trên customers, nhưng phải giữ ngữ nghĩa join và kiểm tra explain.

### Bài 14 — Đo hiệu năng

**Yêu cầu:** Viết lệnh explain cho aggregation lọc PAID tháng 6 của tenant T-A rồi group theo region.

**Đáp án:**

~~~javascript
lab.orders.explain("executionStats").aggregate([
  { $match: paidJuneTenantA },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } }
])
~~~

Đọc query plan/indexName, scan stages, `keysExamined`, `docsExamined`, dữ liệu được đưa vào group và các thống kê có trong phiên bản server. Không kỳ vọng mọi output luôn có cùng cấu trúc JSON.

### Bài 15 — Date range với giờ địa phương

Yêu cầu lọc các đơn được tạo trong ngày 01/06/2026 theo **Asia/Ho_Chi_Minh**, trong khi BSON Date lưu timestamp UTC. Có nên dùng khoảng UTC từ `2026-06-01T00:00:00Z` tới `2026-06-02T00:00:00Z` không?

**Đáp án:** Không nếu kỳ ngày định nghĩa theo giờ Việt Nam. Cần chuyển thời điểm bắt đầu/kết thúc theo UTC+7 (nếu không có chuyển giờ mùa hè ở múi giờ này):

~~~javascript
{
  $match: {
    createdAt: {
      $gte: ISODate("2026-05-31T17:00:00Z"),
      $lt: ISODate("2026-06-01T17:00:00Z")
    }
  }
}
~~~

Dùng range BSON Date có thể hỗ trợ index; điểm quyết định là **chuyển đổi ranh giới đúng timezone nghiệp vụ**, không phải format chuỗi theo máy client.

### Bài 16 — Java Driver và filter sớm

**Yêu cầu:** Chuyển `{$match:{tenantId:"T-A",status:"PAID"}}` sang Java Sync Driver.

**Đáp án:**

~~~java
Bson firstStage = Aggregates.match(
    Filters.and(
        Filters.eq("tenantId", "T-A"),
        Filters.eq("status", "PAID")
    )
);
~~~

Đặt stage này vào đầu `List<Bson>` của `collection.aggregate(...)`. Khi dùng các builders, import `com.mongodb.client.model.Aggregates` và `Filters` hoặc static imports tương đương.

## 18. Tài liệu MongoDB chính thức để đọc sâu

Các liên kết dưới đây là tài liệu MongoDB Database Manual và Java Driver. Khi áp dụng cho production, chọn **nhánh server/driver đang chạy**; cấu trúc `explain` và optimizer có thể thay đổi theo phiên bản.

- [`$match` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/) — cú pháp, các giới hạn và điều kiện để dùng index.
- [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/) — tách/đẩy `$match`, reorder `$sort`/`$match`, coalescence và tương tác với execution engine.
- [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) — cách stages truyền document và xử lý dữ liệu.
- [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/) — bộ nhớ, disk usage và các giới hạn pipeline.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — cách đọc `IXSCAN`, `COLLSCAN`, `FETCH`, index bounds, execution stats.
- [`db.collection.explain()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.explain/) — gọi explain cho aggregate/query.
- [Indexes](https://www.mongodb.com/docs/manual/indexes/) — tổng quan index types và trade-off chi phí ghi.
- [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/) — compound key, prefix, kết hợp filter/sort.
- [The ESR Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/) — Equality, Sort, Range và các lựa chọn thứ tự index.
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/) — index trên arrays và compound bounds với `$elemMatch`.
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — ranh giới các document được index và điều kiện query sử dụng index.
- [`$expr` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/expr/) — dùng aggregation expressions trong filter và giới hạn index.
- [`$unwind` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/) — tách phần tử mảng thành pipeline document.
- [`$group` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/) — accumulator, tài nguyên và các tối ưu trong trường hợp thích hợp.
- [`$sort` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sort/) — quan hệ với index và `$limit`.
- [`$lookup` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/) — lọc foreign collection, indexes và pipeline rewrite.
- [`$facet` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/) — chạy nhiều nhánh và tác động của stage đầu tới index.
- [`$geoNear` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geoNear/) — stage địa lý có ràng buộc vị trí.
- [`db.collection.aggregate()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.aggregate/) — options như `hint`, `allowDiskUse` và `collation`.
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/) — xây pipeline với `Aggregates`, `Filters` và Java Driver.
- [MongoDB 8.0 — Aggregation Pipeline Optimization](https://www.mongodb.com/docs/v8.0/core/aggregation-pipeline-optimization/) — tham chiếu nhánh 8.0 để so sánh các tối ưu.
- [MongoDB 7.0 — `$match`](https://www.mongodb.com/docs/v7.0/reference/operator/aggregation/match/) — cú pháp/giới hạn ở nhánh 7.0.

**Kết luận:** `$match` có thể làm aggregation hiệu quả hơn bằng cách **thu hẹp dữ liệu sớm** và tạo điều kiện cho MongoDB dùng **index**. Nhưng thứ tự stage chỉ đúng khi **ngữ nghĩa được giữ nguyên**: filter trên field gốc có thể đặt sớm, còn filter trên **phần tử đã unwind**, **giá trị group**, **field tính toán** hoặc **dữ liệu lookup** phải theo dependency thực tế. Index có lợi khi phù hợp **predicate, compound prefix, sort, collation, partial filter và phân bố dữ liệu**; sự tồn tại của index không phải bằng chứng optimizer đã sử dụng. Hãy viết pipeline rõ ý, xây index từ access pattern và kiểm tra quyết định của server bằng **`explain("executionStats")`** trên dữ liệu đại diện.
