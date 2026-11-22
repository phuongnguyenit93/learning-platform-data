# Giảm dữ liệu truyền qua mạng bằng projection, batch và nén trong MongoDB

Một màn hình liệt kê 20 đơn hàng chỉ hiển thị mã đơn, trạng thái và tổng tiền, nhưng API lại đọc cả ghi chú nội bộ, lịch sử thay đổi và mảng 5.000 sản phẩm của mỗi document. Một job xử lý dữ liệu gửi 100.000 lệnh cập nhật riêng lẻ tới MongoDB. Một dịch vụ khác truyền nhiều dữ liệu văn bản qua liên kết mạng chậm mà không nén. Cả ba có thể gây độ trễ, chi phí truyền dữ liệu và áp lực bộ nhớ đáng kể, dù các truy vấn không nhất thiết có lỗi cú pháp.

MongoDB có ba nhóm kỹ thuật để giảm chi phí mạng:

- **Projection**: chỉ trả về những trường cần thiết, giảm kích thước BSON response.
- **Batch**: truyền nhiều documents hoặc operations trong những lô hợp lý, giảm số lần trao đổi giữa ứng dụng và database.
- **Wire compression**: nén các thông điệp MongoDB trên đường truyền với bộ giải mã tương thích ở hai đầu, đổi lại tiêu tốn CPU.

Chúng giải quyết **những nguyên nhân khác nhau**. Projection giảm bytes dữ liệu gốc; batch giảm round-trips và overhead của từng lệnh; compression giảm bytes thực sự đi qua mạng. Tăng batch size không loại bỏ trường dư. Nén một document lớn không có nghĩa ứng dụng cần toàn bộ nội dung đó. Và dù response nhỏ, query vẫn có thể chậm do thiếu index hoặc pipeline tốn nhiều CPU.

Bài thuộc chương **Tối ưu hiệu năng** của module *Database Engine Document MongoDB*. Các ví dụ dùng **mongosh**, **Node.js MongoDB Driver** và **Java Sync Driver**; dữ liệu, số liệu và hostname chỉ mang tính học tập. Một số mặc định về batch, tính năng nén và giới hạn wire protocol phụ thuộc phiên bản server/driver, vì vậy cần xác minh trong hệ thống đang vận hành. Không chạy lệnh thay đổi dữ liệu trên production chỉ để thực hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt BSON document bytes, network wire bytes, round-trip và kích thước response API.
2. Đọc và viết projection của `find`, bao gồm trường lồng nhau và `_id`.
3. Giảm payload mảng bằng `$slice`, `$elemMatch`, `$filter` hoặc tính tổng thay vì tải mọi phần tử.
4. Dùng `$project`/`$unset` trong aggregation với đúng thứ tự xử lý.
5. Giảm số documents bằng `$match`, `limit`, pagination và query có index phù hợp.
6. Giải thích covered query và điều kiện để tránh đọc full document.
7. Hiểu MongoDB cursor, `firstBatch`, `getMore` và ý nghĩa của `batchSize`.
8. Phân biệt cursor batch size, total query limit, HTTP page size và bulk write batch.
9. Dùng Node.js/Java streaming cursor để tránh đọc hàng triệu documents vào RAM.
10. Gộp các write operations qua `insertMany`/`bulkWrite` và xử lý ordered/unordered, partial errors, retries.
11. Hiểu giới hạn BSON document, wire message và số operations trong một write batch.
12. Cấu hình các bộ nén snappy, zlib, zstd theo tính năng được driver/server hỗ trợ.
13. Phân biệt wire compression, TLS encryption, WiredTiger compression và HTTP compression.
14. Đo document size, execution plan, số lượt mạng, network counters, CPU và p95/p99 latency.
15. Nhận diện khi một tối ưu làm tăng CPU, memory, latency hoặc vô tình thay đổi kết quả nghiệp vụ.

## 2. Mô hình chi phí truyền dữ liệu

Một lần đọc MongoDB không chỉ là thời gian thực thi query ở server. Nó còn gồm chọn connection, truyền request, xử lý BSON, mã hóa/nén nếu có, chuyển response, giải mã và xử lý ở client.

~~~mermaid
flowchart LR
    App["Ứng dụng"] --> Driver["MongoDB Driver / pool"]
    Driver -->|"find/aggregate"| Server["mongod hoặc mongos"]
    Server --> Query["Index scan, filter, sort"]
    Query --> Project["Project output BSON"]
    Project --> Compress["Wire compression nếu có"]
    Compress -->|"Network response"| Driver
    Driver --> Decode["Decode/deserialize"]
    Decode --> App
~~~

Một mô hình gần đúng:

\[
T \approx T_{\text{server}}+
N_{\text{roundtrips}}\cdot RTT+
\frac{B_{\text{wire}}}{\text{bandwidth}}+
T_{\text{encode/decode}}+
T_{\text{compress/decompress}}
\]

Mô hình không bao quát mọi concurrency, packet loss và pipelining, nhưng chỉ ra:

| Công cụ | Thứ thường giảm | Giá phải trả |
|---|---|---|
| Projection | Payload BSON/output, deserialize cost | Có thể cần một request chi tiết sau đó |
| Filter/limit | Số records cần trả | Cần index/logic phân trang đúng |
| Cursor batching | Số `getMore`/round-trips | Memory cho từng batch |
| Bulk write | Per-operation command overhead | Kích thước batch, partial failures |
| Wire compression | Bytes trên kết nối MongoDB | CPU và đôi khi tăng latency |

**Lưu ý:** giảm network bytes không tự giảm disk I/O. Một query quét 5 triệu records có thể chỉ trả một document nhỏ sau projection, nhưng vẫn tốn nhiều CPU/I/O ở server. Luôn xem query plan.

## 3. Phân biệt BSON size, wire size và JSON size

MongoDB lưu/gửi documents theo BSON với overhead cho tên field, kiểu dữ liệu và cấu trúc. Một API có thể chuyển BSON thành JSON rồi nén HTTP, tức có các mức kích thước khác nhau:

~~~text
BSON size trước projection
    -> BSON size sau projection
        -> MongoDB wire message trước nén
            -> MongoDB wire bytes sau compression
                -> HTTP JSON bytes sau chuyển đổi ở API
                    -> HTTP response bytes sau Content-Encoding
~~~

Đừng dùng `JSON.stringify(doc).length` làm số byte BSON chuẩn: JavaScript `String.length` là số UTF-16 code units, còn BSON có representation cho ObjectId, Date, Decimal128, binary và các field khác.

### 3.1. Một ví dụ định lượng giả định

Nếu một document đầy đủ khoảng 40 KiB nhưng chỉ các trường danh sách khoảng 500 bytes, với 1.000 documents:

| Dạng trả về | Ước lượng payload BSON |
|---|---:|
| Full documents | Khoảng 40 MiB |
| Projected list fields | Khoảng 0,5 MiB |

Đây là **phép minh họa**, không phải kết quả đo từ MongoDB. Nếu zstd có thể nén full documents đáng kể, việc gửi toàn bộ field thừa vẫn có chi phí encode/decode và nén; projection thường là điểm bắt đầu đúng hơn.

### 3.2. TCP packets khác cursor batches

Một MongoDB response có thể đi qua nhiều TCP packets. Ngược lại, `getMore` là **một command ở tầng MongoDB** để lấy batch tiếp theo. Đếm packets TCP không đồng nghĩa đếm số lượt getMore.

## 4. Chuẩn bị lab có document nặng

Các lệnh dưới đây chỉ dùng trong database học tập:

~~~javascript
use network_optimization_lab

db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "idx_tenant_status_created_id" }
)

db.orders.insertMany([
  {
    _id: 101,
    tenantId: "t-01",
    orderNo: "O-101",
    status: "PAID",
    total: 120000,
    createdAt: ISODate("2026-11-01T10:00:00Z"),
    customer: {
      customerId: "C-1", name: "Khách A",
      email: "a@example.invalid"
    },
    items: [
      { sku: "SKU-A", quantity: 2, price: 40000 },
      { sku: "SKU-B", quantity: 1, price: 40000 }
    ],
    internalNotes: "Ghi chú dài không cần cho list API. ".repeat(200),
    auditTrail: Array.from({ length: 20 }, (_, i) => ({
      step: i,
      message: "Thông tin kiểm toán dành cho màn hình khác"
    }))
  },
  {
    _id: 102,
    tenantId: "t-01",
    orderNo: "O-102",
    status: "PAID",
    total: 99000,
    createdAt: ISODate("2026-11-02T10:00:00Z"),
    customer: {
      customerId: "C-2", name: "Khách B",
      email: "b@example.invalid"
    },
    items: [{ sku: "SKU-C", quantity: 1, price: 99000 }],
    internalNotes: "Không cần tải ghi chú khi xem danh sách. ".repeat(200),
    auditTrail: []
  },
  {
    _id: 103,
    tenantId: "t-01",
    orderNo: "O-103",
    status: "PENDING",
    total: 250000,
    createdAt: ISODate("2026-11-03T10:00:00Z"),
    customer: {
      customerId: "C-1", name: "Khách A",
      email: "a@example.invalid"
    },
    items: [{ sku: "SKU-D", quantity: 2, price: 125000 }],
    internalNotes: "Payload dành cho xử lý nội bộ. ".repeat(200),
    auditTrail: []
  },
  {
    _id: 104,
    tenantId: "t-02",
    orderNo: "O-104",
    status: "PAID",
    total: 45000,
    createdAt: ISODate("2026-11-04T10:00:00Z"),
    customer: {
      customerId: "C-3", name: "Khách C",
      email: "c@example.invalid"
    },
    items: [{ sku: "SKU-E", quantity: 1, price: 45000 }],
    internalNotes: "Dữ liệu tenant khác. ".repeat(200),
    auditTrail: []
  }
])
~~~

Lab chỉ có bốn documents, không đủ làm benchmark. Không insert lại với cùng `_id` vì sẽ gây duplicate key. `tenantId` minh họa filter đa tenant; `internalNotes`/`auditTrail` là payload nặng; `orderNo`, `status`, `total` và `createdAt` đủ cho list API.

## 5. Projection với `find`

Không có projection:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
})
~~~

Query có thể trả toàn bộ notes, items, email và audit trail. Trong list API, chỉ cần:

~~~javascript
db.orders.find(
  { tenantId: "t-01", status: "PAID" },
  {
    _id: 1,
    orderNo: 1,
    status: 1,
    total: 1,
    createdAt: 1
  }
).sort({ createdAt: -1 }).limit(30)
~~~

Projection **không sửa dữ liệu lưu**; nó chỉ quy định dữ liệu query trả ra. Người dùng có quyền mở chi tiết sau đó vẫn có thể được cung cấp các field khác theo API policy.

### 5.1. Inclusion và exclusion

~~~javascript
// Inclusion: chỉ các trường đã chọn, cùng _id nếu không loại.
{ orderNo: 1, status: 1, total: 1 }

// Exclusion: mọi trường trừ những trường loại.
{ internalNotes: 0, auditTrail: 0 }
~~~

**Inclusion** thường thích hợp hơn cho public/API contract vì khi schema được bổ sung field nhạy cảm mới, field đó không tự động xuất hiện trong response.

### 5.2. `_id` được đưa vào mặc định

~~~javascript
// Chỉ muốn field business mà không cần _id:
{ _id: 0, orderNo: 1, total: 1 }
~~~

Thông thường không trộn include và exclude fields trong projection của `find`, **ngoại trừ `_id`**. Ví dụ `{orderNo:1,internalNotes:0}` không phải kiểu projection cơ bản hợp lệ. Một số projection expressions có quy tắc đặc biệt, nhưng nên dùng contract rõ ràng.

### 5.3. Có nên loại `_id`?

Chỉ loại nếu thật sự không cần. `_id` thường dùng để mở chi tiết, cập nhật và làm tie-breaker cho keyset pagination. Tối ưu vài bytes không đáng nếu frontend mất định danh ổn định.

## 6. Projection field lồng nhau

Nếu UI chỉ hiển thị tên khách mà không cần email:

~~~javascript
db.orders.find(
  { tenantId: "t-01" },
  {
    _id: 1,
    orderNo: 1,
    "customer.name": 1,
    status: 1
  }
)
~~~

MongoDB có thể trả `customer` chỉ chứa `name` theo dotted-path projection. Tránh chỉ định đồng thời parent path và child path theo cách mâu thuẫn, ví dụ `customer` và `customer.name`; có thể gặp path collision.

### 6.1. Projection là data minimization, không phải authorization

Ẩn email khỏi list giảm nguy cơ bị log/truyền dữ liệu dư, nhưng **không giới hạn quyền truy cập database** nếu một tài khoản khác vẫn có quyền query collection. Server/database RBAC và application authorization phải được thiết kế riêng.

### 6.2. Tenant filter phải ở server

Không đọc documents của mọi tenants về ứng dụng rồi dùng `Array.filter`. Điều đó chuyển dữ liệu người khác qua mạng và RAM, đồng thời tăng nguy cơ vi phạm isolation. `tenantId` phải lấy từ context xác thực và đưa vào query.

## 7. Giảm kích thước mảng

Một document chứa hàng nghìn `items` có thể quá nặng cho list API. Nếu UI chỉ cần ba sản phẩm đầu:

~~~javascript
db.orders.find(
  { tenantId: "t-01" },
  {
    orderNo: 1,
    items: { $slice: 3 }
  }
)
~~~

`$slice` trong projection của `find` giới hạn phần tử mảng được trả về, không cắt mảng trong database.

### 7.1. Phần tử từ cuối

~~~javascript
db.orders.find(
  { _id: 101, tenantId: "t-01" },
  {
    orderNo: 1,
    items: { $slice: -1 }
  }
)
~~~

Giá trị âm lấy phần tử tính từ cuối theo cú pháp `$slice` hỗ trợ.

### 7.2. `$elemMatch` ở projection

~~~javascript
db.orders.find(
  { _id: 101, tenantId: "t-01" },
  {
    orderNo: 1,
    items: { $elemMatch: { sku: "SKU-A" } }
  }
)
~~~

`$elemMatch` projection có semantics trả **một phần tử phù hợp**, không trả mọi phần tử match. Muốn trả nhiều phần tử, cần aggregation `$filter`.

### 7.3. Aggregation `$filter`

~~~javascript
db.orders.aggregate([
  { $match: { _id: 101, tenantId: "t-01" } },
  {
    $project: {
      orderNo: 1,
      expensiveItems: {
        $filter: {
          input: "$items",
          as: "item",
          cond: { $gte: ["$$item.price", 40000] }
        }
      }
    }
  }
])
~~~

Nếu muốn giới hạn output tiếp:

~~~javascript
{
  $project: {
    orderNo: 1,
    previewItems: { $slice: ["$items", 2] }
  }
}
~~~

Đây là aggregation `$slice` expression, khác cú pháp `$slice` projection của `find` dù cùng tên toán tử.

### 7.4. Trả số lượng thay vì cả mảng

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01" } },
  {
    $project: {
      orderNo: 1,
      itemsCount: { $size: "$items" }
    }
  }
])
~~~

`$size` cần input là array; khi field có thể thiếu/null, phải xử lý `$ifNull` hoặc điều kiện loại tương ứng. Không dùng `items.length` sau khi đã tải cả mảng lớn về client chỉ để đếm.

## 8. `$project` và `$unset` trong aggregation

Một pipeline liệt kê đơn hàng:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 30 },
  {
    $project: {
      _id: 1,
      orderNo: 1,
      status: 1,
      total: 1,
      createdAt: 1
    }
  }
])
~~~

`$unset` có thể loại field:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01" } },
  { $unset: ["internalNotes", "auditTrail"] },
  { $limit: 30 }
])
~~~

### 8.1. Có phải đặt `$project` ở đầu luôn nhanh hơn?

Không. MongoDB optimizer có thể phân tích field dependencies và giảm lượng fields cần xử lý giữa stages. Vì vậy, đặt một `$project` sớm chỉ để “tối ưu” chưa chắc có tác dụng. Thường ưu tiên `$match`/`$sort`/`$limit` đúng logic và dùng `$project` để định hình output. Nếu một `$lookup` hoặc stage trung gian tạo mảng lớn, giảm dữ liệu ngay nơi sinh ra có thể hữu ích. Cần xem `explain` và đo trên workload thật.

### 8.2. Không loại field trước khi còn cần

Nếu dự định sort theo `createdAt`, đừng loại field đó bằng `$project` rồi mới `$sort`. Pipeline phải giữ những field cần cho các stage kế tiếp, trừ khi dùng một biểu thức thay thế đúng semantics.

### 8.3. Phân biệt `$unset` query và update

`$unset` trong aggregation chỉ thay output của pipeline. `$unset` trong update operator thực sự xóa field khỏi documents lưu. Không chạy update để “giảm payload” của một API đọc.

## 9. Giảm số documents trước khi giảm bytes

Một API muốn 30 đơn PAID của tenant:

~~~javascript
db.orders.find(
  { tenantId: "t-01", status: "PAID" },
  { _id: 1, orderNo: 1, total: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(30)
~~~

Không làm:

~~~javascript
// Anti-pattern: đọc cả collection về app, sau đó lọc.
const all = await orders.find({}).toArray()
const rows = all
  .filter(x => x.tenantId === "t-01" && x.status === "PAID")
  .slice(0, 30)
~~~

Cách sai vừa tăng network, vừa có thể rò rỉ data cross-tenant vào application memory/logs.

### 9.1. Aggregate trên server thay vì tải mọi record

Nếu chỉ cần tổng doanh thu:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  {
    $group: {
      _id: null,
      totalRevenue: { $sum: "$total" },
      ordersCount: { $sum: 1 }
    }
  },
  { $project: { _id: 0, totalRevenue: 1, ordersCount: 1 } }
])
~~~

Server gửi một document tổng hợp thay vì hàng nghìn orders. Tuy nhiên aggregation vẫn cần quét/dùng index và tiêu tốn CPU; giảm response bytes không có nghĩa tổng compute giảm.

## 10. Projection và covered queries

Nếu một index chứa đủ fields để **filter, sort và trả kết quả**, MongoDB có thể xử lý từ index mà không FETCH full documents, trong những điều kiện được hỗ trợ.

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, orderNo: 1, total: 1 },
  { name: "idx_cover_order_list" }
)

db.orders.find(
  { tenantId: "t-01", status: "PAID" },
  { _id: 0, orderNo: 1, total: 1 }
)
~~~

Đây là **ứng viên** covered query: `_id` bị loại vì không có trong index. Phải xác nhận planner thực sự chọn index và đáp ứng quy tắc coverage.

### 10.1. Projection không tự tạo coverage

Nếu index chỉ có `tenantId,status` nhưng response cần `total`, MongoDB vẫn có thể FETCH documents. Multikey arrays, null checks và các query shapes khác có thêm giới hạn. Xác minh bằng `explain("executionStats")`.

### 10.2. Đừng index field lớn tùy tiện

Một compound index chứa quá nhiều trường ít dùng làm tăng storage, cache pressure và write amplification. Chỉ cân nhắc covered index cho những query quan trọng có fields nhỏ và access pattern ổn định.

### 10.3. Coverage khác compression

Covered query chủ yếu giảm server document fetch; projection giảm BSON output; wire compression giảm bytes của messages. Chúng có thể bổ sung nhưng không phải cùng khái niệm.

## 11. Phân trang để không trả hàng triệu documents

Trường hợp danh sách, giới hạn số records mỗi response:

~~~javascript
db.orders.find(
  { tenantId: "t-01", status: "PAID" },
  { _id: 1, orderNo: 1, total: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(30)
~~~

Không tin `limit` bất kỳ do frontend đưa, ví dụ 500.000. API cần đặt `pageSize` tối đa và kiểm soát fields theo endpoint.

### 11.1. Offset pagination

~~~javascript
db.orders.find(
  { tenantId: "t-01", status: "PAID" },
  { orderNo: 1, total: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 })
 .skip(30000)
 .limit(30)
~~~

Response chỉ chứa 30 records nhưng server có thể phải duyệt/bỏ qua 30.000 records trước đó. Network nhỏ không cứu được query cost của offset sâu.

### 11.2. Keyset pagination

Với sort ổn định `createdAt:-1,_id:-1`, lưu cặp khóa của record cuối trang trước:

~~~javascript
const lastCreatedAt = ISODate("2026-11-02T10:00:00Z")
const lastId = 102

db.orders.find(
  {
    tenantId: "t-01",
    status: "PAID",
    $or: [
      { createdAt: { $lt: lastCreatedAt } },
      { createdAt: lastCreatedAt, _id: { $lt: lastId } }
    ]
  },
  { _id: 1, orderNo: 1, total: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(30)
~~~

Index ứng viên:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 }
)
~~~

### 11.3. Vì sao cần tie-breaker?

Hai records có thể có cùng `createdAt`. Chỉ sort theo thời gian có thể làm pagination thiếu/trùng records do thứ tự không ổn định. `_id` unique là một tie-breaker thường dùng.

### 11.4. Keyset không tự tạo snapshot consistency

Nếu sort key bị sửa hoặc documents bị xóa trong lúc người dùng đọc các trang, danh sách vẫn có thể thay đổi. Báo cáo yêu cầu snapshot consistency cần chiến lược read concern/snapshot phù hợp, không chỉ continuation token.

## 12. Tránh N+1 reads

Một API tải 100 orders rồi gọi `findOne` lần lượt để lấy customer name của từng order:

~~~javascript
// Anti-pattern khái niệm:
for (const order of orders) {
  const customer = await customers.findOne({
    _id: order.customerId
  })
}
~~~

Có thể tạo 101 database calls logic, đặc biệt chậm khi RTT cao. Một phương án khác:

1. Lấy các customer IDs duy nhất.
2. Chia IDs thành những nhóm vừa phải.
3. Query một lần mỗi nhóm qua `$in`.
4. Projection chỉ lấy ID/displayName.
5. Ghép kết quả ở application theo ID.

~~~javascript
db.customers.find(
  {
    tenantId: "t-01",
    _id: { $in: ["C-1", "C-2", "C-3"] }
  },
  { _id: 1, displayName: 1 }
)
~~~

Collection `customers` ở đây minh họa access pattern, không nằm trong bộ lab orders ban đầu. `$in` quá lớn có thể tăng command size/planner work; cần chunk IDs hợp lý.

### 12.1. `$lookup` có thể thay nhiều requests

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1 } },
  { $limit: 30 },
  {
    $lookup: {
      from: "customers",
      let: { id: "$customer.customerId", tenant: "$tenantId" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$id"] },
                { $eq: ["$tenantId", "$$tenant"] }
              ]
            }
          }
        },
        { $project: { _id: 1, displayName: 1 } }
      ],
      as: "customerInfo"
    }
  },
  { $project: { orderNo: 1, total: 1, customerInfo: 1 } }
])
~~~

Giới hạn trước `$lookup` là đúng khi nghiệp vụ muốn join 30 orders mới nhất; nếu phải xếp hạng theo giá trị join rồi mới chọn 30, phải đổi pipeline. Foreign index và cardinality quyết định hiệu quả.

### 12.2. Coi chừng fan-out

Join 1:N có thể tạo mảng rất lớn, chạm giới hạn BSON document 16 MiB. Nếu chỉ cần số lượng hoặc tổng, tính ở server bằng `$count`/`$group` trong foreign pipeline thay vì trả mọi bản ghi.

## 13. Cursor: firstBatch và getMore

Với một `find` trả nhiều documents, server có thể trả `firstBatch` cùng cursor ID; driver gửi `getMore` khi tiêu thụ hết batch và cần tiếp.

~~~mermaid
sequenceDiagram
    participant App as Driver
    participant DB as MongoDB
    App->>DB: find(filter, projection, batchSize)
    DB-->>App: firstBatch + cursorId
    App->>App: Xử lý documents
    App->>DB: getMore(cursorId)
    DB-->>App: nextBatch
    App->>DB: getMore(cursorId)
    DB-->>App: finalBatch hoặc cursor exhausted
~~~

### 13.1. `batchSize` không phải giới hạn tổng số documents

~~~javascript
db.orders.find({ tenantId: "t-01" }).batchSize(100)
~~~

Query vẫn có thể trả hàng nghìn records qua nhiều batches. Muốn giới hạn tổng:

~~~javascript
db.orders.find({ tenantId: "t-01" })
  .limit(1000)
  .batchSize(200)
~~~

Lúc đó `limit=1000` giới hạn tổng records, còn `batchSize=200` điều khiển quy mô từng batch theo các giới hạn server/driver.

### 13.2. Batch size là yêu cầu, không phải bảo đảm

Một batch có thể bị giới hạn bởi số bytes của response và điều kiện xử lý cursor. Không khẳng định `batchSize(200)` luôn trả đúng 200 documents, nhất là khi documents rất lớn.

### 13.3. FirstBatch defaults có thể khác

MongoDB có quy tắc mặc định về số lượng/byte limit cho firstBatch và các `getMore`. Nhiều tài liệu nhắc tới firstBatch khoảng 101 documents trong trường hợp không chỉ định batch size, nhưng không hardcode điều đó như invariant cho mọi query, driver và version.

### 13.4. Cursor batches không phải HTTP pages

API page size là số records trả về cho frontend. Driver batch size là quy mô đọc từ MongoDB để phục vụ API/job. Một HTTP response 30 records có thể được phục vụ bằng một cursor batch, hoặc API backend chọn query khác; chúng không cùng contract.

## 14. Chọn batch size theo document bytes

Giả sử:

| Đặc điểm | Dataset A | Dataset B |
|---|---:|---:|
| Trung bình projected doc | 500 bytes | 40 KiB |
| Yêu cầu batch | 1000 docs | 1000 docs |
| Tổng BSON gần đúng | 0,5 MiB | 40 MiB |

Với A, batch 1000 tương đối nhẹ. Với B, dữ liệu gần mức wire message limit phổ biến nên server/driver có thể chia thêm, memory và latency cao hơn. Các số chỉ là ví dụ toán học.

### 14.1. Batch quá nhỏ

`batchSize=1` với 20.000 docs có thể gây hàng nghìn `getMore`, RTT trở thành bottleneck.

### 14.2. Batch quá lớn

`batchSize=10000` có thể làm mỗi request dùng nhiều RAM, tăng thời gian chờ kết quả đầu tiên và gây GC pressure nếu có nhiều cursors đồng thời. Số `getMore` giảm không đồng nghĩa p99 cải thiện.

### 14.3. Bảng đánh đổi

| Batch | Round-trips | Memory/client | Phù hợp |
|---|---|---|---|
| Nhỏ | Có thể nhiều | Thấp hơn | Streaming, client chậm |
| Vừa | Cân bằng | Cân bằng | Đa số jobs |
| Rất lớn | Ít hơn đến khi chạm limits | Có thể cao | Docs nhỏ, RTT lớn, đã benchmark |

Không có batchSize chuẩn cho mọi collection.

## 15. Node.js Driver: projection + streaming cursor

~~~javascript
import { MongoClient } from "mongodb"

const client = new MongoClient(process.env.MONGODB_URI, {
  maxPoolSize: 30
})
await client.connect()

try {
  const orders = client.db("network_optimization_lab")
    .collection("orders")

  const cursor = orders.find(
    { tenantId: "t-01", status: "PAID" },
    {
      projection: {
        _id: 1,
        orderNo: 1,
        status: 1,
        total: 1,
        createdAt: 1
      },
      batchSize: 200,
      limit: 1000
    }
  ).sort({ createdAt: -1, _id: -1 })

  try {
    for await (const order of cursor) {
      // Xử lý từng document; ở production tránh log PII.
      console.log(order.orderNo, order.total)
    }
  } finally {
    await cursor.close()
  }
} finally {
  await client.close()
}
~~~

### 15.1. Vì sao dùng iterator?

`for await` cho phép tiêu thụ results dần. `toArray()` gom toàn bộ results đã đọc vào RAM: ngay cả khi driver dùng `batchSize=100`, kết quả cuối có thể là một mảng hàng triệu documents.

### 15.2. Khi nào `toArray()` vẫn hợp lý?

Với một page có `limit(30)` và documents nhỏ theo contract, `toArray()` dễ dùng:

~~~javascript
const rows = await orders.find(
  { tenantId: "t-01", status: "PAID" },
  { projection: { _id: 1, orderNo: 1, total: 1 } }
).limit(30).toArray()
~~~

Tránh `toArray()` không giới hạn trên jobs lớn.

### 15.3. Đóng cursor

Nếu app dừng sớm sau khi đủ 100 records hoặc có lỗi, đóng cursor để giải phóng tài nguyên server/client. Sử dụng `try/finally` hoặc cách quản lý lifecycle do driver hỗ trợ.

## 16. Java Sync Driver: cursor batch và projection

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

public class EfficientOrderReader {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                .getDatabase("network_optimization_lab")
                .getCollection("orders");

            try (MongoCursor<Document> cursor = orders.find(
                    Filters.and(
                        Filters.eq("tenantId", "t-01"),
                        Filters.eq("status", "PAID")
                    ))
                .projection(Projections.fields(
                    Projections.include(
                        "orderNo", "total", "status", "createdAt"
                    ),
                    Projections.excludeId()
                ))
                .sort(Sorts.descending("createdAt", "_id"))
                .limit(1000)
                .batchSize(200)
                .iterator()) {

                while (cursor.hasNext()) {
                    Document order = cursor.next();
                    System.out.println(order.getString("orderNo"));
                }
            }
        }
    }
}
~~~

Try-with-resources đóng `MongoCursor`. Nếu bạn thay vòng lặp bằng `into(new ArrayList<>())` trên query không giới hạn, app vẫn có thể gom tất cả docs vào RAM dù đã cấu hình batchSize.

### 16.1. Object mapping cũng tốn CPU

POJO deserialization, JSON conversion và GC đều tăng khi đưa field không cần qua driver. Projection giúp giảm cả bytes mạng và object allocation phía Java.

### 16.2. Connection pooling

Không tạo một `MongoClient` mới cho mỗi document/request. Reuse client pool theo lifecycle service để tránh DNS/topology/TLS connection overhead.

## 17. API page size khác batch size

Một API:

~~~text
GET /orders?pageSize=30&cursor=...
~~~

có thể triển khai bằng `limit(31)` để biết còn trang tiếp, còn MongoDB cursor dùng `batchSize=100` để vận chuyển results. Các tham số khác nhau:

| Tham số | Tầng | Ý nghĩa |
|---|---|---|
| HTTP `pageSize=30` | API | Số records tối đa frontend thấy |
| MongoDB `limit(31)` | Query | Tối đa 31 records backend lấy để xác định hasNext |
| MongoDB `batchSize(100)` | Cursor | Quy mô batch MongoDB, trong giới hạn wire |

Đừng trả trực tiếp MongoDB cursorId cho browser như một stable pagination token: nó phụ thuộc server cursor lifetime/protocol. Dùng token ứng dụng chứa seek keys và các thông tin cần xác thực.

## 18. `bulkWrite`: gom nhiều lệnh ghi

Một job update 50.000 orders bằng 50.000 lệnh `updateOne` tuần tự tốn nhiều round-trips. Có thể dùng `bulkWrite`:

~~~javascript
const orders = db.getSiblingDB("network_optimization_lab").orders

orders.bulkWrite([
  {
    updateOne: {
      filter: { _id: 101, tenantId: "t-01" },
      update: { $set: { status: "SHIPPED" } }
    }
  },
  {
    updateOne: {
      filter: { _id: 102, tenantId: "t-01" },
      update: { $set: { status: "SHIPPED" } }
    }
  }
], { ordered: false })
~~~

Chỉ dùng trên lab; thay đổi trạng thái đơn hàng thật cần kiểm soát business workflow.

### 18.1. Ordered và unordered

| Cấu hình | Semantics chung |
|---|---|
| `ordered:true` | Thực hiện theo thứ tự, dừng khi lỗi theo quy tắc API |
| `ordered:false` | Có thể tiếp tục xử lý operations khác khi một operation lỗi, không bảo đảm thứ tự |

`ordered:false` phù hợp với operations độc lập. Nếu operation B phụ thuộc A, không dùng unordered chỉ để có throughput cao hơn.

### 18.2. Bulk không phải transaction

Một bulkWrite gồm nhiều operations **không tự atomic toàn batch**. Có thể một số operations đã thành công trước khi gặp validation/duplicate key error. Nếu cần all-or-nothing, phải xem transaction support và constraints, không cố dùng một bulk siêu lớn thay transaction.

### 18.3. Partial failure

Khi driver trả bulk exception, cần xem những operations đã thành công và lỗi nào có thể retry. Retry mù quáng toàn batch có thể lặp side effects của `$inc` hoặc những writes không idempotent.

## 19. Node.js: chia bulk thành lô hợp lý

~~~javascript
async function writeInBatches(collection, operations, batchMaxOps = 500) {
  if (!Number.isInteger(batchMaxOps) || batchMaxOps <= 0) {
    throw new Error("INVALID_BATCH_MAX_OPS")
  }

  for (let start = 0; start < operations.length; start += batchMaxOps) {
    const batch = operations.slice(start, start + batchMaxOps)
    await collection.bulkWrite(batch, { ordered: false })
  }
}
~~~

`500` chỉ là số minh họa để hạn chế memory/error scope, **không phải mặc định tối ưu của MongoDB**. Với dữ liệu input rất lớn, nên xây array batch từ stream và flush từng lô thay vì load trước mọi operations vào memory.

### 19.1. Đếm operations chưa đủ

500 updates nhỏ có thể chỉ vài KiB, nhưng 500 inserts chứa tài liệu vài trăm KiB có thể rất lớn. Phải cân nhắc **byte budget**, concurrency, response errors và driver splitting.

### 19.2. Drivers chia message khi cần

Drivers hiện đại có cơ chế tuân thủ giới hạn số operations và kích thước message; application vẫn cần kiểm soát số lượng objects đang materialize, memory, retries và áp lực lên primary.

### 19.3. Write concern và correctness

Không giảm write concern/durability chỉ để cải thiện mạng nếu nghiệp vụ cần majority acknowledgement. Tối ưu latency không được làm mất cam kết độ bền của dữ liệu.

## 20. `insertMany` và server-side `updateMany`

~~~javascript
db.events.insertMany([
  { _id: "E-1", tenantId: "t-01", type: "CREATED" },
  { _id: "E-2", tenantId: "t-01", type: "PAID" },
  { _id: "E-3", tenantId: "t-01", type: "SHIPPED" }
], { ordered: false })
~~~

Collection `events` thuộc lab, không nhất thiết có sẵn. Insert lại cùng IDs gây duplicate key. Batching giảm command overhead, không làm mất bytes nội dung phải lưu.

Nếu có một điều kiện cập nhật hàng loạt và semantics cho phép:

~~~javascript
db.orders.updateMany(
  {
    tenantId: "t-01",
    status: "PENDING",
    createdAt: { $lt: ISODate("2026-11-01T00:00:00Z") }
  },
  { $set: { status: "EXPIRED" } }
)
~~~

Lệnh thực thi trên server, tránh đọc mọi documents về app rồi ghi lại từng cái. Nhưng `updateMany` không tự gọi những side effects hoặc validations nghiệp vụ mà một workflow cập nhật từng đơn đang thực hiện. Xem lại semantics trước khi thay.

## 21. Giới hạn BSON/wire protocol

MongoDB có nhiều giới hạn cần phân biệt:

| Giới hạn | Ý nghĩa |
|---|---|
| `maxBsonObjectSize` | Kích thước một BSON document, thông thường 16 MiB |
| `maxMessageSizeBytes` | Giới hạn một MongoDB wire message, nhiều phiên bản thường khoảng 48 MiB |
| `maxWriteBatchSize` | Số operations tối đa trong một write batch, thường 100.000 |
| Batch byte limits | Server có thể trả ít documents hơn batchSize yêu cầu |

Các giá trị thực tế được công bố qua `hello`:

~~~javascript
const hello = db.adminCommand({ hello: 1 })

printjson({
  maxBsonObjectSize: hello.maxBsonObjectSize,
  maxMessageSizeBytes: hello.maxMessageSizeBytes,
  maxWriteBatchSize: hello.maxWriteBatchSize
})
~~~

### 21.1. Không nhầm 16 MiB là giới hạn cả collection

Một collection có thể chứa rất nhiều documents; giới hạn BSON áp trên **mỗi document**. Compression không khiến document BSON 20 MiB trở thành hợp lệ chỉ vì bytes nén xuống ít hơn 16 MiB.

### 21.2. Không coi maximum batch là recommendation

`maxWriteBatchSize` là giới hạn protocol, không phải khuyến nghị dùng batch 100.000 operations mọi lúc. Batch thực tế nên chọn dựa vào payload, RTT, CPU, write contention, concurrency và retry granularity.

## 22. Java Sync Driver: `bulkWrite`

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.BulkWriteOptions;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.Updates;
import com.mongodb.client.model.WriteModel;
import org.bson.Document;
import java.util.List;

public class BulkUpdateDemo {
    public static void main(String[] args) {
        try (MongoClient client =
                MongoClients.create(System.getenv("MONGODB_URI"))) {
            MongoCollection<Document> orders = client
                .getDatabase("network_optimization_lab")
                .getCollection("orders");

            List<WriteModel<Document>> writes = List.of(
                new UpdateOneModel<>(
                    Filters.and(
                        Filters.eq("_id", 101),
                        Filters.eq("tenantId", "t-01")
                    ),
                    Updates.set("status", "SHIPPED")
                ),
                new UpdateOneModel<>(
                    Filters.and(
                        Filters.eq("_id", 102),
                        Filters.eq("tenantId", "t-01")
                    ),
                    Updates.set("status", "SHIPPED")
                )
            );

            orders.bulkWrite(
                writes,
                new BulkWriteOptions().ordered(false)
            );
        }
    }
}
~~~

Trong production, bắt/đọc lỗi `MongoBulkWriteException`, lưu per-operation status phù hợp và retry theo idempotency policy. Đừng chỉ in “bulk failed” rồi replay mọi non-idempotent updates.

## 23. Wire compression là gì?

MongoDB hỗ trợ **wire protocol compression** giữa server và driver khi hai phía có cùng codec được hỗ trợ. Trong quá trình mở kết nối, hai đầu công bố khả năng nén và có thể chọn một thuật toán chung cho các messages phù hợp.

~~~mermaid
sequenceDiagram
    participant Driver as MongoDB Driver
    participant Server as mongod/mongos
    Driver->>Server: Handshake / hello, compressor capabilities
    Server-->>Driver: Hello response / supported compressors
    Note over Driver,Server: Negotiation chọn codec chung nếu có
    Driver->>Server: Request message có thể compressed
    Server-->>Driver: Response message có thể compressed
    Driver->>Driver: Decompress rồi decode BSON
~~~

### 23.1. Nén không phải mã hóa

Nén làm dữ liệu ít bytes hơn; người có bytes nén và codec có thể giải nén. **TLS** dùng để bảo vệ confidentiality/integrity; một kết nối có zstd nhưng không có TLS không đáp ứng yêu cầu encrypted transport.

### 23.2. Không mọi message đều nén

Handshake và những messages rất nhỏ hoặc trường hợp protocol riêng có thể không được nén. Không khẳng định bật compressor sẽ làm mọi packet giảm đúng một tỷ lệ cố định.

### 23.3. Mã hóa và nén ở hai lớp

Một kết nối có thể dùng cả TLS và wire compression theo support của protocol/runtime. Không tắt TLS để thử cải thiện compression throughput trên production.

## 24. So sánh snappy, zlib và zstd

| Codec | Xu hướng thường gặp | Đánh đổi |
|---|---|---|
| **snappy** | Tốc độ nén/giải nén cao, compression ratio vừa phải | Có thể tiết kiệm ít bytes hơn codec mạnh |
| **zlib** | Có mức compression level; ratio có thể tốt trên text | CPU phụ thuộc level, có thể tăng latency |
| **zstd** | Thường cân bằng ratio và tốc độ tốt trên nhiều workload | Cần phiên bản/driver/runtime hỗ trợ |

Không có codec tốt nhất chung. Nội dung khác nhau cho kết quả khác nhau:

- Văn bản lặp lại, documents cùng schema: thường dễ nén.
- Random bytes, ciphertext, JPEG, MP4: thường khó nén thêm.
- Response chỉ vài chục bytes: codec overhead có thể vượt savings.

### 24.1. Nén mạnh có thể làm chậm

Nếu server và app ở cùng vùng mạng tốc độ cao, tiết kiệm vài KiB có thể không bù được CPU nén/giải nén. Khi mạng WAN băng thông hạn chế, trade-off có thể ngược lại. Phải đo p95/p99 và CPU thay vì chỉ xem compression ratio.

### 24.2. Compression ratio không phải latency ratio

Một message giảm từ 10 MiB xuống 3 MiB không có nghĩa request nhanh gấp 3,3 lần. Server query, serialization, connection wait và CPU nén có thể chiếm phần lớn thời gian.

## 25. Server configuration cho wire compression

Với server tự quản có hỗ trợ codecs tương ứng:

~~~yaml
net:
  compression:
    compressors: zstd,snappy,zlib
~~~

Đây chỉ là **phần cấu hình nén minh họa**, không phải file `mongod.conf` hoàn chỉnh. TLS, authorization, bind addresses, replication/sharding config vẫn phải được thiết lập riêng. Mặc định, tên/cú pháp option và khả năng codec cần xác minh theo MongoDB version.

### 25.1. Phải có codec chung

Nếu server hỗ trợ `snappy` còn client chỉ yêu cầu `zstd`, không thể mặc định dùng zstd. Tùy driver/protocol, kết nối có thể không nén khi không có compressor chung. Cần kiểm tra negotiation, không chỉ đọc một đầu config.

### 25.2. Sharded cluster có hai chặng

~~~text
Application --TLS/compression tùy negotiation--> mongos
mongos --TLS/compression tùy negotiation--> shard mongod
~~~

Client nén với mongos không chứng minh traffic nội bộ mongos→shard cùng dùng codec. Đo và cấu hình theo các network segments thực tế.

### 25.3. Storage compression không phải wire compression

WiredTiger compression giảm kích thước dữ liệu trên disk. `net.compression.compressors` liên quan network messages. Một system bật nén storage vẫn có thể gửi messages không nén cho driver nếu không có thương lượng wire compression.

## 26. Node.js: bật compressors

~~~javascript
import { MongoClient } from "mongodb"

const client = new MongoClient(process.env.MONGODB_URI, {
  compressors: ["zstd", "snappy", "zlib"],
  zlibCompressionLevel: 6
})

await client.connect()

try {
  console.log(
    await client.db("admin").command({ ping: 1 })
  )
} finally {
  await client.close()
}
~~~

Tùy MongoDB Node.js Driver version, snappy/zstd có thể cần các package/native libraries bổ sung. Nếu thiếu dependency, có thể không sử dụng được codec hoặc việc khởi tạo báo lỗi; kiểm tra driver docs, logs và môi trường triển khai.

### 26.1. URI compressors

Một số drivers hỗ trợ URI option:

~~~text
mongodb://mongo1.db.internal:27017/?tls=true&compressors=zstd,snappy,zlib
~~~

Hãy kiểm tra parser/version và những package đã cài. Không đưa username/password thật vào URI chia sẻ trong logs.

### 26.2. `zlibCompressionLevel`

Tăng compression level có thể cải thiện ratio nhưng thêm CPU và độ trễ. Option này chỉ có ý nghĩa khi zlib được chọn và driver hỗ trợ. Đừng cấu hình high level theo cảm tính.

### 26.3. Connection pool và negotiated state

Kết nối trong pool được thương lượng khi tạo. Sau khi thay compressor settings, các kết nối hiện hữu có thể chưa phản ánh cấu hình mới; cần rollout/reconnect đúng quy trình và benchmark ở steady state.

## 27. Java Driver: cấu hình compressors

Với Java Sync Driver, có thể truyền compressor options qua connection string trong các phiên bản hỗ trợ:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;

public class CompressionDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        // URI từ secret/config:
        // mongodb://mongo1.db.internal:27017/
        // ?tls=true&compressors=zstd,snappy,zlib

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .build();

        try (MongoClient client = MongoClients.create(settings)) {
            Document ping = client.getDatabase("admin")
                .runCommand(new Document("ping", 1));
            System.out.println(ping.toJson());
        }
    }
}
~~~

Kiểm tra dependencies/classpath cho những codecs được yêu cầu theo Java Driver version, không giả định zstd/snappy có sẵn trong mọi runtime. Giữ nguyên TLS certificate verification.

## 28. Wire compression khác HTTP compression

Một ứng dụng có hai chặng:

~~~text
MongoDB -> Backend API -> Browser
~~~

MongoDB wire compression tác động chặng MongoDB→backend. Sau đó backend có thể biến BSON thành JSON rồi trả HTTP response; HTTP `Content-Encoding:gzip`/`br` là cơ chế **riêng**. Bật zstd ở MongoDB driver không tự khiến browser nhận dữ liệu nhỏ.

### 28.1. Content đã nén

Với ảnh JPEG, MP4, PDF nén hoặc binary encrypted, nén lại thường ít lợi và dùng CPU. Với media lớn, cân nhắc streaming/GridFS/object storage/CDN, thumbnail hoặc lazy loading thay vì đưa binary vào list API.

### 28.2. Base64 JSON

Nếu backend chuyển binary thành Base64 string trong JSON, representation lớn hơn bytes gốc và gây parse overhead. Khi phù hợp, stream binary qua một endpoint riêng với authorization và caching policy.

## 29. Đo document size qua `$bsonSize`

MongoDB aggregation có thể tính kích thước BSON:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01" } },
  {
    $project: {
      orderNo: 1,
      rawBsonBytes: { $bsonSize: "$$ROOT" }
    }
  }
])
~~~

Để đo hình dạng sau projection:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01" } },
  {
    $project: {
      orderNo: 1,
      status: 1,
      total: 1,
      createdAt: 1
    }
  },
  {
    $project: {
      projectedBsonBytes: { $bsonSize: "$$ROOT" }
    }
  }
])
~~~

### 29.1. Kết quả không phải wire bytes

`$bsonSize` phản ánh BSON document, không tính protocol headers, compression ratio, TLS records hoặc HTTP JSON response. Nó giúp đánh giá projection chứ không phải đo traffic chính xác.

### 29.2. Quan tâm outliers

Average document size có thể che một số documents chứa mảng gần giới hạn BSON. Khi chọn batch size, hãy xem phân bố/p95/p99 kích thước documents và trường hợp cực lớn.

## 30. `explain()` cho query plan

~~~javascript
db.orders.explain("executionStats").find(
  { tenantId: "t-01", status: "PAID" },
  { _id: 0, orderNo: 1, total: 1 }
)
~~~

Đọc:

- `nReturned`.
- `totalKeysExamined` và `totalDocsExamined`.
- Index được lựa chọn.
- Có `COLLSCAN`, `FETCH` hoặc index-only execution tùy engine/version?
- Query execution statistics trong phạm vi `explain`.

### 30.1. `explain` không phải wire profiler

`explain` không trả compressed response bytes hoặc số TCP packets chính xác. Projection có thể giảm response rất mạnh trong khi docsExamined vẫn lớn nếu query không có index tốt.

### 30.2. Cùng semantics mới so sánh được

Khi benchmark before/after, giữ nguyên filter, sort, limits, read concern và dữ liệu trả về theo nghiệp vụ. Một phiên bản “nhanh hơn” vì vô tình loại 90% records không phải tối ưu hợp lệ.

## 31. Network counters và monitoring

Với quyền phù hợp, có thể quan sát:

~~~javascript
const network = db.adminCommand({ serverStatus: 1 }).network
printjson(network)
~~~

Tùy phiên bản, network stats có thể chứa `bytesIn`, `bytesOut`, `numRequests` và compression-related metrics. Các counter này thường là **process-wide**, không riêng một HTTP request hay MongoDB query.

### 31.1. Không suy per-request từ serverStatus production

Nếu production có 300 clients chạy cùng lúc, chênh lệch `bytesOut` trong 10 giây phản ánh tất cả workloads. Để ước lượng lợi ích per-query, dùng môi trường thử riêng hoặc instrumentation phù hợp với client/network monitoring.

### 31.2. Driver command monitoring

Có thể quan sát số `find`/`getMore`/bulk requests bằng command monitoring theo tính năng driver. Nhưng log command payload có thể chứa thông tin nhạy cảm và gây overhead. Chỉ bật ở môi trường kiểm thử hoặc với redaction/sampling policy.

### 31.3. Đo cả hai đầu

Khi có mongos, load balancer hoặc API gateway, đo bytes tại đúng network hop bạn muốn tối ưu. Server network bytes, client received bytes và HTTP egress có thể khác vì compression/serialization.

## 32. Đo BSON ở Node.js

Tùy MongoDB Node.js Driver version, BSON utilities có thể dùng để tính size object mẫu:

~~~javascript
import { BSON } from "mongodb"

const sample = {
  orderNo: "O-101",
  status: "PAID",
  total: 120000
}

console.log(BSON.calculateObjectSize(sample))
~~~

Giá trị đo BSON representation của sample, **không** đo nén wire hay HTTP payload. Nếu mỗi record có BSON types khác với object JavaScript mẫu, cần đối chiếu với dữ liệu thực.

Không tải vài triệu docs vào `toArray()` chỉ để tính kích thước; dùng sample hoặc `$bsonSize` trên server theo mục tiêu đo lường.

## 33. Benchmark tối ưu một cách công bằng

Để đo projection/batch/compression, lập ma trận:

| Biến | Các lựa chọn |
|---|---|
| Projection | Full / list fields / array preview |
| Cursor batchSize | 20 / 100 / 500 / 2000 |
| Compressor | None / snappy / zlib / zstd nếu hỗ trợ |
| Dataset | Text / documents nhỏ / binary đã nén |
| Network | Cùng region / cross-region / latency giả lập |
| Concurrency | 1 / 10 / 50 workers |

Thu cho mỗi lần thử:

1. Số documents và fields trả.
2. Raw BSON size ước tính.
3. Network bytes thực đo trên hop liên quan.
4. Số `find`/`getMore` và round-trips.
5. CPU server/client, RSS, GC và connection pool wait.
6. Latency p50/p95/p99, throughput và timeout/error rate.
7. Index plan và docsExamined.
8. Correctness checks: số records và business invariants.

### 33.1. Warm-up

Lần kết nối đầu có thể bao gồm DNS, TLS handshake, topology discovery và cold cache. Không so baseline warm với một variant cold. Chạy nhiều vòng và đo steady-state với cùng dữ liệu.

### 33.2. Thay một biến mỗi lần

Nếu cùng lúc tạo index, thêm projection và bật zstd, không thể kết luận yếu tố nào giúp nhiều nhất. Benchmark từng thay đổi rồi thử tổ hợp.

### 33.3. Metrics trung bình chưa đủ

Một batch size lớn có thể cải thiện average nhưng làm p99 tệ do outlier documents hoặc GC pauses. Đo phân bố và tình huống peak load.

## 34. Khi nào chọn projection, batch hay compression?

~~~mermaid
flowchart TD
    Start["API/job chậm hoặc network bytes cao"] --> Extra{"Đang trả fields/docs thừa?"}
    Extra -->|"Có"| Project["Filter, projection, limit, pagination"]
    Extra -->|"Không"| RTT{"Nhiều getMore / N+1 / write calls?"}
    Project --> RTT
    RTT -->|"Có"| Batch["Cursor batching, bulkWrite, batch fetch"]
    RTT -->|"Không"| Bandwidth{"Bandwidth bottleneck và data dễ nén?"}
    Batch --> Bandwidth
    Bandwidth -->|"Có"| Compress["Benchmark snappy, zlib, zstd"]
    Bandwidth -->|"Không"| Plan["Kiểm tra query plan, disk, CPU, locks"]
    Compress --> Measure["Đo end-to-end latency, bytes, CPU, correctness"]
    Plan --> Measure
~~~

Hãy ưu tiên **giảm dữ liệu không cần thiết trước**, rồi giảm round-trips, sau đó thử nén nếu network bytes vẫn quan trọng. Tuy nhiên thứ tự thực tế còn phụ thuộc workload; tránh biến lời khuyên thành quy tắc tuyệt đối.

## 35. Bảo mật khi giảm payload

Projection giúp giảm dữ liệu nhạy cảm xuất hiện trong responses/logs, nhưng **không thay** authentication/authorization. Tenant filter phải đến từ principal đã xác thực.

Wire compression không phải cơ chế bảo mật. Giữ TLS và certificate validation. Trong một số giao thức, độ dài dữ liệu sau nén có thể gây side channel nếu attacker điều khiển một phần nội dung và quan sát độ dài truyền. Mức rủi ro phụ thuộc threat model và trust boundaries; đánh giá khi dữ liệu đặc biệt nhạy cảm.

### 35.1. Không dùng nén để “ẩn” secrets

Một password hoặc API key dù compressed vẫn tồn tại trong data và có thể bị client giải mã. Phương án đúng là không trả field, kiểm tra quyền và giới hạn log exposure.

### 35.2. Tối ưu không được hạ durability

Không giảm read concern/write concern, loại tenant filter hoặc bỏ validation chỉ để đạt benchmark latency tốt hơn. Những thay đổi đó sửa **semantics/rủi ro nghiệp vụ**, không đơn thuần network cost.

## 36. Bài thực hành A — projection

Với lab `orders`:

1. Query tất cả fields của đơn `tenantId:"t-01",status:"PAID"`.
2. Query cùng filter nhưng chỉ `_id`, `orderNo`, `total`, `createdAt`.
3. Giải thích field nào giảm bytes mạnh nhất.
4. Tại sao không lọc tenant sau khi tải về app?

## 37. Bài thực hành B — mảng lớn

Viết projection chỉ trả hai `items` đầu. Viết aggregation chỉ trả `itemsCount`. Giải thích vì sao `$elemMatch` ở projection không trả mọi matching elements như `$filter`.

## 38. Bài thực hành C — covered query

Cho index `{tenantId:1,status:1,orderNo:1,total:1}`. Viết query/projection là ứng viên covered, giải thích `_id:0` và kiểm tra `explain` có FETCH không. Vì sao không nên thêm một field notes dài vào index chỉ để cover?

## 39. Bài thực hành D — batchSize và limit

Một job cần đọc tối đa 10.000 docs:

1. `batchSize(200)` có giới hạn tổng 200 docs không?
2. `limit(10000)` có giới hạn số lượt `getMore` cố định không?
3. Vì sao batch 200 docs × 1 MiB/doc có thể bị giới hạn bytes?
4. Khi nào nên dùng stream/iterator thay `toArray()`?

## 40. Bài thực hành E — pagination

Thiết kế API list 30 orders theo `createdAt:-1,_id:-1`, có last sort key cho trang tiếp theo. Chọn index ứng viên. So sánh với `skip(30000)` về network response và server work.

## 41. Bài thực hành F — N+1 và joins

Một API đọc 200 orders rồi query 200 customers tuần tự. Đếm số calls logic, đề xuất `$in` batch với projection, hoặc `$lookup` có foreign projection. Vì sao phải thêm tenant filter và tránh fan-out lớn?

## 42. Bài thực hành G — bulk operations

Viết `bulkWrite` cập nhật ba orders độc lập với `ordered:false`. Giải thích khi một operation lỗi thì những operations khác có thể xảy ra điều gì, bulk có atomic toàn batch không, và vì sao retry toàn bộ `$inc` có rủi ro.

## 43. Bài thực hành H — codecs

Đo cùng dataset text theo bốn cấu hình: uncompressed, snappy, zlib và zstd (khi hỗ trợ). Thu bytes, CPU, p95, p99 và throughput. Giải thích tại sao codec tốt nhất trên text chưa chắc tốt trên JPEG/MP4.

## 44. Bài thực hành I — storage vs wire

Một đồng nghiệp nói: “WiredTiger đã bật snappy nên MongoDB driver nhận dữ liệu đã nén trên mạng.” Hãy sửa phát biểu, nêu sự khác nhau giữa `storage compression`, `wire compression` và TLS.

## 45. Bài thực hành J — observability

Đo `serverStatus().network` trước/sau workload trong lab cô lập. Dùng `$bsonSize` đo raw BSON docs và driver monitoring đếm `getMore` nếu môi trường cho phép.

Tại sao không được diễn giải network counters production là bytes của riêng một query? Tại sao raw BSON bytes khác compressed wire bytes?

## 46. Bài thực hành K — tài liệu nhị phân

Một list API trả 100 records, mỗi record có ảnh JPEG 2 MiB dù UI chỉ cần thumbnail URL. Chọn projection, design API chi tiết và cách trả binary. Có nên mong zstd làm JPEG giảm 90% không?

## 47. Bài thực hành L — regression sau tăng batch

Sau khi đổi `batchSize` từ 100 lên 10000, số `getMore` giảm nhưng RSS và p99 tăng. Đề xuất giả thuyết về memory, GC, document outliers, concurrency và byte limits. Xây lại benchmark với các batch sizes vừa phải.

## 48. Gợi ý đáp án thực hành

**A:** Projection inclusion `{_id:1,orderNo:1,total:1,createdAt:1}` giảm notes/arrays; tenant filter giúp đúng quyền và giảm dữ liệu truyền.

**B:** `{items:{$slice:2}}` giới hạn output mảng; aggregation `$size:"$items"` trả count; `$elemMatch` projection trả một element, khác `$filter`.

**C:** Query theo tenant/status, project `{_id:0,orderNo:1,total:1}` có cơ hội index-only; verify explain, không index field quá lớn.

**D:** `batchSize` không giới hạn tổng docs; `limit` có. Số getMore phụ thuộc server/driver/data size. Cursor iterator tránh giữ toàn bộ results trong RAM.

**E:** Seek pagination dựa trên last `createdAt,_id` và filter tenant; index `{tenantId:1,status:1,createdAt:-1,_id:-1}`. `skip` vẫn đòi server duyệt những records bỏ qua.

**F:** Có thể có 201 calls logic (1 query orders + 200 queries customer). Batch IDs hoặc join, giữ tenant isolation, tối ưu cardinality/index.

**G:** Unordered cho phép các operations độc lập tiếp tục khi có lỗi; bulk không atomic toàn batch. Retry non-idempotent updates có thể lặp side effects.

**H:** Text thường có thể nén tốt; ảnh/video đã nén thường ít giảm. Chọn codec theo wire bytes và CPU/latency đo thực.

**I:** WiredTiger compression giảm bytes trên disk; wire compressor cần negotiation giữa server/driver; TLS mã hóa traffic.

**J:** Counters là process-wide, `$bsonSize` là raw BSON, compressed wire bytes phụ thuộc codec/messages. Đo isolated.

**K:** Không đưa JPEG binary vào list, trả thumbnail URL, tải file theo request riêng; dùng GridFS/object storage/CDN phù hợp, không kỳ vọng nén JPEG rất mạnh.

**L:** Ít getMore không đủ chứng minh nhanh hơn; kiểm tra bytes/doc, memory, GC, concurrency, response limits và benchmark nhiều batch sizes.

## 49. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| API list trả MiB dữ liệu | Trả full documents | Inclusion projection, pagination |
| `_id` vẫn xuất hiện | Không loại `_id` | Thêm `_id:0` nếu thật sự không cần |
| Projection báo path collision | Field cha/con không nhất quán | Sửa projection paths |
| Query chậm dù response nhỏ | Thiếu index, nhiều docsExamined | `explain`, cải thiện query |
| Covered query không xảy ra | Index thiếu field hoặc multikey limitations | Xem winning plan/FETCH |
| `batchSize` không trả đúng N | Byte limits/result availability | Đo actual batch/getMore |
| App OOM dù batchSize nhỏ | `toArray()` gom tất cả | Stream iterator |
| Quá nhiều `getMore` | Batch quá nhỏ | Tăng hợp lý và đo |
| Batch lớn làm p99 xấu | Memory/GC/time-to-first-result | Giảm/điều chỉnh batch |
| BulkWrite partial error | Một phần operations fail | Inspect errors, retry policy |
| Duplicate side effects sau retry | Updates không idempotent | Stable IDs và kiểm soát retry |
| Nén không giảm bytes | Dữ liệu khó nén/codec không negotiated | Test support, dataset |
| Nén làm CPU tăng | Codec/level quá nặng | Benchmark settings |
| Zstd/snapppy không hoạt động | Dependencies/version mismatch | Kiểm tra driver packages |
| Frontend vẫn chậm | HTTP JSON response lớn | Tối ưu hop API→browser |
| `$lookup` vượt BSON limit | Fan-out mảng lớn | Foreign projection/count |
| Pagination trùng/thiếu records | Sort key không ổn định | Tie-breaker và seek |
| Metrics network lệch | Production traffic nhiều clients | Benchmark isolated |

## 50. Câu hỏi ôn tập

**1. Projection giảm gì?** — Fields BSON không cần trả về, decode và network payload.

**2. `{a:1,b:1}` có trả `_id` không?** — Có, trừ khi đặt `_id:0`.

**3. Có được trộn `a:1` và `b:0` tùy ý không?** — Không theo quy tắc cơ bản, ngoại trừ `_id`.

**4. `$slice` projection dùng khi nào?** — Khi UI chỉ cần một phần mảng.

**5. `$elemMatch` projection có trả mọi matches?** — Không; dùng aggregation `$filter` cho nhiều matches.

**6. Đặt `$project` đầu pipeline luôn nhanh hơn?** — Không; optimizer có thể đã giảm fields cần.

**7. Covered query là gì?** — Query có thể được phục vụ từ index mà không FETCH documents, khi đủ điều kiện.

**8. Projection tự biến query thành covered?** — Không; index và query shape phải phù hợp.

**9. `batchSize(100)` có nghĩa tối đa 100 records?** — Không, phải dùng `limit`.

**10. `getMore` là gì?** — Command lấy batch tiếp theo từ server cursor.

**11. `toArray()` có thể gây OOM?** — Có, nếu gom dữ liệu quá lớn.

**12. Batch lớn có luôn giảm p99?** — Không; memory, byte caps và GC có thể tăng.

**13. API pageSize có giống MongoDB batchSize?** — Không, là hai tầng.

**14. `skip` trang sâu tốn gì?** — Server phải duyệt/bỏ qua nhiều records.

**15. N+1 gây hại gì?** — Tăng số round-trips và command overhead.

**16. BulkWrite có atomic toàn batch?** — Không mặc định.

**17. `ordered:false` phù hợp khi nào?** — Các operations độc lập, có xử lý lỗi từng phần.

**18. Compression làm vượt BSON 16 MiB limit được không?** — Không.

**19. snappy, zlib, zstd thuộc lớp nào?** — Wire compression khi được thương lượng.

**20. Nén có thay TLS không?** — Không, nén không mã hóa.

**21. WiredTiger nén disk có tự nén network?** — Không.

**22. JPEG thường dễ nén tiếp?** — Không đáng kể vì thường đã nén.

**23. `$bsonSize` có đo wire bytes sau nén không?** — Không.

**24. `explain` có đo TCP packets không?** — Không.

**25. Vì sao phải đo CPU/p95/p99 ngoài bytes?** — Nén và batching có thể tốn CPU/memory làm latency tệ hơn.

**26. Projection có tự cấp security không?** — Không; vẫn cần authorization.

**27. Mỗi HTTP request có nên tạo MongoClient mới không?** — Không; dùng connection pooling.

**28. Thứ tự tối ưu thông thường?** — Giảm dữ liệu dư, giảm lượt trao đổi, thử compression, đo và xác minh tính đúng.

## 51. Bảng ghi nhớ nhanh

| Mục đích | Cú pháp/cơ chế |
|---|---|
| Inclusion projection | `find(filter,{field:1,_id:0})` |
| Loại field nặng | `find(filter,{largeField:0})` |
| Chỉ lấy nested field | `{"customer.name":1}` |
| Lấy vài phần tử mảng | `items:{$slice:3}` |
| Chọn một phần tử match | `$elemMatch` projection |
| Chọn nhiều phần tử match | Aggregation `$filter` |
| Chỉ lấy số phần tử | Aggregation `$size` |
| Định hình output | `$project`/`$unset` |
| Giảm số records | `$match`, `limit`, pagination |
| Avoid N+1 | Batch `$in` / `$lookup` |
| Index-only read | Covered query nếu đủ điều kiện |
| Cursor batches | `batchSize`, `getMore` |
| Giới hạn tổng | `limit` |
| Node streaming | `for await (const x of cursor)` |
| Java streaming | `MongoCursor` trong try-with-resources |
| Gom writes | `insertMany`/`bulkWrite` |
| Ordered/unordered writes | `ordered:true/false` |
| Server wire compressors | `net.compression.compressors` |
| Driver wire compressors | `compressors=zstd,snappy,zlib` theo support |
| Encryption | TLS |
| Storage compression | WiredTiger compression |
| Đo BSON | `$bsonSize` |
| Query plan | `explain("executionStats")` |
| Network counters | `serverStatus().network` |
| Protocol limits | `db.adminCommand({hello:1})` |

## 52. Checklist triển khai production

- [ ] List/detail APIs có hợp đồng fields rõ ràng?
- [ ] Không trả notes, arrays hoặc PII không được sử dụng?
- [ ] Đã dùng inclusion projection và xử lý `_id` có chủ đích?
- [ ] Trường nested và array preview trả đúng semantics?
- [ ] Filter theo tenant đến từ context xác thực?
- [ ] `$match`, sort, limit và index được thiết kế cùng nhau?
- [ ] Đã kiểm tra `explain`, docsExamined, keysExamined?
- [ ] Không kéo full collection về client để filter/group?
- [ ] Đã cân nhắc keyset pagination cho trang sâu?
- [ ] Tránh N+1 calls và `$lookup` fan-out không giới hạn?
- [ ] Đã phân biệt API pageSize, cursor batchSize và limit?
- [ ] BatchSize được chọn theo document size/RTT/memory?
- [ ] Dùng iterator/stream cho large result sets?
- [ ] Cursor được đóng khi dừng sớm?
- [ ] Bulk writes có operation count/byte budget phù hợp?
- [ ] Xử lý partial failures, retries và idempotency?
- [ ] Không hạ durability/write concern để đạt benchmark tốt?
- [ ] Server/driver có cùng compressor thực sự được hỗ trợ?
- [ ] Node/Java codec dependencies đã được kiểm tra?
- [ ] TLS và hostname validation vẫn được duy trì?
- [ ] Phân biệt wire compression với storage/HTTP compression?
- [ ] Không kỳ vọng nén lại JPEG/MP4 hiệu quả cao?
- [ ] Đã đo network bytes, requests, CPU, memory, p95/p99?
- [ ] Có benchmark representative, warm-up và nhiều lần lặp?
- [ ] Đã so sánh số records/fields và business invariants?
- [ ] Có monitoring và rollback plan khi triển khai tuning?

## 53. Kết luận

Tối ưu đường truyền MongoDB bắt đầu từ nguyên tắc **không gửi dữ liệu ứng dụng không sử dụng**. Projection, `$match`, limit và pagination giảm cả số field lẫn số documents. Các kỹ thuật với array và server-side aggregation giúp trả metadata, preview hoặc thống kê thay vì payload lớn; covered query còn có thể giảm server document fetch nếu index phù hợp.

Khi vẫn có nhiều round-trips, **cursor batching** và **bulk writes** giúp giảm command overhead. Nhưng batchSize không phải limit, `toArray()` có thể vẫn chiếm nhiều RAM, và `bulkWrite` không tạo transaction cho cả batch. Chọn batch bằng phép đo document bytes, RTT, concurrency, memory và error semantics.

Sau cùng, **wire compression** bằng snappy, zlib hoặc zstd có thể giảm bytes truyền trên MongoDB connections khi codec được client/server thương lượng và dữ liệu dễ nén. Nén không thay TLS, không tương đương WiredTiger storage compression và không tự làm query plan tốt hơn. Một cải thiện hiệu năng đáng tin phải được xác minh bằng **network bytes, CPU, p95/p99 latency và tính đúng đắn của kết quả**, chứ không chỉ một con số “nén được bao nhiêu phần trăm”.
