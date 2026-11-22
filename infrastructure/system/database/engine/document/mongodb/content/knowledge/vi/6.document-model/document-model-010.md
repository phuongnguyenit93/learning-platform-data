# Đánh giá mô hình document bằng truy vấn, index, dung lượng và chi phí cập nhật

## Mục tiêu bài học

MongoDB cho phép biểu diễn quan hệ nghiệp vụ bằng **document nhúng (embedded document)**, **tham chiếu (reference)** hoặc kết hợp hai cách. Cùng một dữ liệu có thể được tổ chức thành một document lớn hoặc nhiều document nhỏ ở các collection khác nhau. Không có mô hình nào luôn tốt hơn: mô hình nhanh cho thao tác xem chi tiết có thể làm tăng chi phí cập nhật hoặc khiến index và dung lượng phát triển quá lớn.

Bài học này trình bày một quy trình ra quyết định dựa trên **workload đo được** thay vì dựa trên trực giác. Sau khi học, bạn có thể:

- Liệt kê những truy vấn, cập nhật và yêu cầu nhất quán chi phối thiết kế.
- So sánh embedding, referencing và hybrid theo các đường đọc/ghi thực tế.
- Tạo và đánh giá index với `explain("executionStats")`, nhận biết scan tốn kém.
- Ước lượng BSON size, index size, dữ liệu nhân bản và tốc độ tăng trưởng.
- Phân tích chi phí update mảng, cập nhật dữ liệu dùng chung, hot document và giao dịch.
- Lập benchmark có thể lặp lại, so hiệu năng và chi phí trên cùng lượng dữ liệu nghiệp vụ.
- Đề xuất mô hình với giả định, điều kiện bắt buộc và bằng chứng rõ ràng.

> **Nguyên tắc:** Hãy lưu chung những gì thường **đọc chung**, có vòng đời gần nhau và cần **cập nhật nguyên tử chung**. Hãy tách những gì có thể tăng vô hạn, truy vấn độc lập hoặc thay đổi liên tục với các đối tượng khác.

## 1. Vì sao hình dạng document quyết định hiệu năng?

Giả sử hệ thống thương mại điện tử có khách hàng, sản phẩm, đơn hàng và đánh giá. Một đơn hàng có thể biểu diễn như sau:

~~~javascript
{
  _id: "ORD-1001",
  customerId: "CUS-001",
  createdAt: ISODate("2026-11-14T03:15:00Z"),
  status: "NEW",
  total: NumberDecimal("1490000"),
  items: [
    {
      productId: "PRD-01",
      productNameAtPurchase: "Bàn phím cơ",
      quantity: 1,
      unitPriceAtPurchase: NumberDecimal("850000")
    },
    {
      productId: "PRD-02",
      productNameAtPurchase: "Chuột không dây",
      quantity: 2,
      unitPriceAtPurchase: NumberDecimal("320000")
    }
  ]
}
~~~

API chi tiết đơn hàng có thể lấy tất cả thông tin trong một lần đọc. Nhưng nếu cần tìm mọi đơn chứa sản phẩm `PRD-01`, hệ thống phải có truy vấn và index phù hợp cho mảng `items`. Nếu số item không giới hạn, document có thể phình to. Nếu một tên sản phẩm đang được sao chép vào hàng triệu đơn và yêu cầu đồng bộ với catalog, mỗi lần đổi tên có thể gây cập nhật hàng loạt.

Trong các đánh giá sau, phải phân biệt **dữ liệu snapshot** (giá, tên sản phẩm lúc khách đặt hàng) với **dữ liệu hiện tại** (giá bán mới nhất trong catalog). Trùng lặp có chủ đích để giữ lịch sử thường là thiết kế đúng; đồng bộ ngược giá mới vào đơn cũ có thể vừa sai nghiệp vụ vừa rất tốn kém.

Bốn trục đánh giá:

| Trục | Câu hỏi | Minh chứng |
|---|---|---|
| Truy vấn | Trả đúng dữ liệu sau bao nhiêu lần đọc, bao nhiêu round trip và bao lâu? | Request latency p95/p99, `nReturned`, số lệnh, byte phản hồi |
| Index | Filter và sort có được hỗ trợ hiệu quả? Index chiếm bao nhiêu tài nguyên? | `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, `indexSizes` |
| Dung lượng | Document có tăng quá lớn và dữ liệu trùng lặp ra sao? | `$bsonSize`, `avgObjSize`, `storageSize`, `totalIndexSize` |
| Cập nhật | Một thay đổi nghiệp vụ tác động đến bao nhiêu document và index? | Write p95, số document sửa, conflicts/retry, replication và transaction overhead |

Không có một metric đơn lẻ quyết định mô hình tốt hay xấu.

## 2. Thu thập workload trước khi chọn embedding hay reference

### 2.1. Lập danh sách thao tác đọc/ghi

Một workload giả định để học:

| Tác vụ | Tần suất giả định | Filter / sort | Trường cần | Đặc điểm |
|---|---|---|---|---|
| Danh sách đơn của khách | Cao | `customerId`, `createdAt DESC` | Mã, ngày, trạng thái, tổng tiền | 20 đơn/trang |
| Chi tiết đơn | Cao | `orderNo` | Header, items, địa chỉ lúc mua | Đọc chung |
| Tra đơn theo sản phẩm | Trung bình | `items.productId` và khoảng ngày | Đơn và item liên quan | Cần index trên array nếu embed |
| Chuyển trạng thái đơn | Trung bình | `orderNo` và trạng thái hiện tại | `status`, `updatedAt` | Tính nhất quán nghiệp vụ |
| Sửa giá catalog | Trung bình | `productId` | `currentPrice` | Không làm đổi giá lịch sử |
| Danh sách review mới | Cao ở sản phẩm phổ biến | `productId`, `createdAt DESC` | 20 review/trang | Có thể tăng không giới hạn |
| Thêm review | Trung bình | `productId`, user | Một review mới | Có thể nhiều writer đồng thời |

Đây là bảng giả định, không phải dữ liệu benchmark. Trong dự án thật, thu số lượng request, tỷ lệ đọc/ghi, số phần tử mỗi mảng, số document mỗi nhóm, kích thước payload và phân bố theo tenant hoặc khách hàng.

### 2.2. Một truy vấn cần được mô tả đầy đủ

Không nên chỉ ghi “tìm đơn hàng”. Hãy ghi:

~~~text
Operation: GetRecentOrdersByCustomer
Filter: customerId = ?
Sort: createdAt DESC, _id DESC
Projection: orderNo, createdAt, status, total
Page size: 20
Read rate: đo bằng telemetry
Latency target: p95/p99 theo SLA
Cardinality: số đơn/khách, phân bố trung bình và cực đại
~~~

`_id` có thể được dùng làm khóa thứ hai để sắp xếp ổn định khi nhiều đơn có cùng timestamp. Khi phân trang sâu, cân nhắc keyset pagination thay cho `skip` lớn.

### 2.3. Những ràng buộc cần ghi thành giả định kiểm chứng được

- Một đơn tối đa bao nhiêu line item? Giới hạn được áp đặt ở đâu?
- Một sản phẩm có thể nhận bao nhiêu review và tồn tại bao lâu?
- Thông tin sao chép là snapshot bất biến hay cache cần cập nhật?
- Những thay đổi nào phải nguyên tử trong **một document** hoặc **nhiều document**?
- Có quyền truy cập khác nhau đối với một phần dữ liệu không?
- Có sharding, hot key hoặc truy vấn xuyên shard không?
- Dung lượng và lưu lượng 6–12 tháng tới tăng ra sao?
- Cần retention, TTL hoặc archive khác nhau cho từng loại dữ liệu không?

Các câu trả lời dẫn đến những phương án schema khác nhau. “Mảng có lẽ sẽ không lớn” là giả định yếu; “mỗi đơn tối đa 100 line item và ứng dụng chặn số lượng lớn hơn” là ràng buộc có thể kiểm chứng.

## 3. So sánh ba mô hình trên cùng nghiệp vụ

### 3.1. Embedding: nhúng line item vào đơn

~~~javascript
// Collection: orders_embedded
{
  _id: "ORD-1001",
  customerId: "CUS-001",
  createdAt: ISODate("2026-11-14T03:15:00Z"),
  status: "NEW",
  total: NumberDecimal("1490000"),
  items: [
    {
      productId: "PRD-01",
      productNameAtPurchase: "Bàn phím cơ",
      quantity: 1,
      unitPriceAtPurchase: NumberDecimal("850000")
    },
    {
      productId: "PRD-02",
      productNameAtPurchase: "Chuột không dây",
      quantity: 2,
      unitPriceAtPurchase: NumberDecimal("320000")
    }
  ]
}
~~~

**Lợi ích:**

- Truy vấn chi tiết đọc một document, giảm công ghép dữ liệu.
- Field thuộc cùng document có thể được cập nhật nguyên tử trong một write.
- Dữ liệu snapshot lịch sử luôn ở cạnh đơn hàng.
- Phù hợp khi số items nhỏ và có giới hạn nghiệp vụ.

**Giới hạn:**

- Document lớn dần theo mảng; nếu số items tăng không kiểm soát, có rủi ro kích thước và cache.
- Multikey index trên array tăng số index entry.
- Trả về toàn bộ document có thể truyền payload không cần thiết nếu trang chỉ cần header.
- Cập nhật thường xuyên trên cùng document có thể tạo contention.
- Một BSON document thông thường có giới hạn **16 MiB**.

Embedding phù hợp khi child gắn chặt vào cha, thường được đọc chung, vòng đời giống nhau và số lượng child được chặn rõ ràng.

### 3.2. Referencing: tách header và line item

~~~javascript
// Collection: orders_ref
{
  _id: "ORD-1001",
  customerId: "CUS-001",
  createdAt: ISODate("2026-11-14T03:15:00Z"),
  status: "NEW",
  total: NumberDecimal("1490000")
}

// Collection: order_items
{
  _id: "OI-001",
  orderId: "ORD-1001",
  productId: "PRD-01",
  productNameAtPurchase: "Bàn phím cơ",
  quantity: 1,
  unitPriceAtPurchase: NumberDecimal("850000")
}
~~~

**Lợi ích:**

- Header order nhỏ, không tăng theo số lượng item.
- Có thể tìm kiếm, cập nhật và phân trang items độc lập.
- Index và retention cho child có thể được thiết kế riêng.
- Thích hợp với quan hệ một–nhiều lớn hoặc không giới hạn.

**Chi phí:**

- Chi tiết order thường cần hai query hoặc `$lookup`.
- Nhiều document cần các khóa liên kết và index bổ sung.
- Một nghiệp vụ cần ghi cả header lẫn items có thể cần transaction, cơ chế retry/idempotency hoặc thiết kế bảo đảm nhất quán khác.
- Phải xử lý orphan reference và quy trình xóa liên quan.

Không nên kết luận reference luôn tốn dung lượng ít hơn: nhiều document nhỏ có `_id`, field liên kết và index riêng cũng có overhead.

### 3.3. Hybrid: chia theo ngữ nghĩa và vòng đời

Một mô hình thương mại điện tử phổ biến về mặt nguyên tắc:

~~~text
customers
    |
    +--> orders
           |
           +--> items[]: số lượng giới hạn,
                         tên/giá tại thời điểm mua
           |
           +--> productId tham chiếu catalog nếu cần

products
    |
    +--> currentPrice, currentName, stock
    |
    +--> ratingSummary: thông tin tính trước
    |
    +--> reviews collection: từng review độc lập, phân trang
~~~

Ví dụ review riêng:

~~~javascript
{
  _id: ObjectId("..."),
  productId: "PRD-01",
  customerId: "CUS-001",
  rating: 5,
  content: "Bàn phím gõ tốt",
  createdAt: ISODate("2026-11-14T04:00:00Z")
}
~~~

Product có thể lưu một số thống kê để đọc nhanh:

~~~javascript
{
  _id: "PRD-01",
  currentName: "Bàn phím cơ",
  currentPrice: NumberDecimal("850000"),
  stock: 120,
  ratingSummary: {
    count: 2389,
    average: 4.7
  }
}
~~~

Đây là hybrid vì:

- Line item giữ snapshot, không cần cập nhật khi catalog đổi giá.
- Review tăng không giới hạn được tách để phân trang và ghi độc lập.
- `ratingSummary` là dữ liệu dẫn xuất để giảm chi phí aggregate tại thời điểm đọc; cần chiến lược cập nhật và rebuild.

**Nguồn chuẩn phải rõ ràng:** Review collection là nguồn cho review; `ratingSummary` là projection tính trước. Giá đơn hàng là snapshot; `products.currentPrice` là giá live.

## 4. Đánh giá bằng số lần truy vấn và dữ liệu trả về

### 4.1. Đọc chi tiết: một document so với join

**Embedding:**

~~~javascript
db.orders_embedded.findOne({ _id: "ORD-1001" });
~~~

**Reference qua hai truy vấn:**

~~~javascript
const order = db.orders_ref.findOne({ _id: "ORD-1001" });

const items = db.order_items
  .find({ orderId: "ORD-1001" })
  .toArray();
~~~

Reference có thể dùng một aggregation thay vì hai round trip:

~~~javascript
db.orders_ref.aggregate([
  { $match: { _id: "ORD-1001" } },
  {
    $lookup: {
      from: "order_items",
      localField: "_id",
      foreignField: "orderId",
      as: "items"
    }
  }
]);
~~~

Index để thử ở collection được join:

~~~javascript
db.order_items.createIndex(
  { orderId: 1 },
  { name: "idx_order_items_orderId" }
);
~~~

`$lookup` không mặc nhiên chậm. Chi phí phụ thuộc số order được match trước join, index, số child của mỗi order và kích thước dữ liệu trả về. Nếu một order có rất nhiều child, trả tất cả trong một mảng kết quả vẫn có thể gây áp lực bộ nhớ và giới hạn BSON.

### 4.2. Danh sách đơn: dùng projection

Trang danh sách chỉ cần header:

~~~javascript
db.orders_embedded.find(
  { customerId: "CUS-001" },
  {
    _id: 1,
    createdAt: 1,
    status: 1,
    total: 1
  }
).sort({ createdAt: -1, _id: -1 }).limit(20);
~~~

Projection có thể giảm số byte truyền về driver. Tuy nhiên, nó không đảm bảo disk I/O giảm cùng tỷ lệ: nếu query phải fetch document từ storage, việc đọc, cache và decompress còn phụ thuộc kế hoạch thực thi.

Nếu trường filter, sort và projection đều đáp ứng bởi một index phù hợp, MongoDB có thể thực hiện covered query. Hãy xác minh bằng explain, bởi multikey và một số cấu trúc query có giới hạn riêng.

### 4.3. Đọc một phần array không miễn phí trong mọi tình huống

Nếu ứng dụng chỉ hiển thị 10 review gần nhất của một sản phẩm, nhúng toàn bộ 100.000 review vào product rồi chỉ chọn 10 phần tử không giải quyết tốt việc document gốc liên tục tăng.

Reference có thể:

~~~javascript
db.reviews.find(
  { productId: "PRD-01" }
).sort({ createdAt: -1, _id: -1 }).limit(10);
~~~

Cùng index:

~~~javascript
db.reviews.createIndex(
  { productId: 1, createdAt: -1, _id: -1 },
  { name: "idx_recent_product_reviews" }
);
~~~

Mô hình này giữ số review đọc theo page size và tránh dồn mọi ghi vào một product document.

## 5. Dùng `explain("executionStats")` để kiểm tra truy vấn

Tạo index phù hợp với truy vấn danh sách đơn:

~~~javascript
db.orders_embedded.createIndex(
  { customerId: 1, createdAt: -1, _id: -1 },
  { name: "idx_customer_recent_orders" }
);
~~~

Đo kế hoạch:

~~~javascript
const result = db.orders_embedded
  .find({ customerId: "CUS-001" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");

printjson(result.executionStats);
printjson(result.queryPlanner.winningPlan);
~~~

Các trường nên đọc:

| Trường | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| `nReturned` | Số document kết quả | Không khớp mục tiêu truy vấn |
| `totalKeysExamined` | Số entry trong index được duyệt | Rất lớn so với lượng kết quả |
| `totalDocsExamined` | Số document đã được xem/fetch | Quét rất nhiều document để lấy ít kết quả |
| `executionTimeMillis` | Thời gian thực thi được explain báo | Cao hoặc biến động lớn; cần đo thêm phía ứng dụng |
| `winningPlan` | Kế hoạch được chọn | `COLLSCAN` khi query đáng lẽ cần index, sort tốn tài nguyên |
| `rejectedPlans` | Những kế hoạch ứng viên bị bỏ, nếu trả về | Hữu ích để điều tra lựa chọn index |

Nếu truy vấn trả 20 đơn nhưng phải đọc 100.000 document, khả năng cao cần xem lại index hoặc filter. Tuy nhiên, không dùng một tỷ lệ cố định `docsExamined/nReturned` cho mọi truy vấn: aggregate, count và một số phép xử lý dữ liệu cố ý quét nhiều bản ghi.

Kế hoạch có thể được biểu diễn khác nhau tùy MongoDB version và query engine. Các stage như `IXSCAN`, `FETCH`, `SORT` hoặc `COLLSCAN` có thể nằm ở các nhánh khác nhau của cây plan. Đọc tổng thể kế hoạch thay vì chỉ tìm một field ở đường JSON cố định.

**Giới hạn của explain:** nó giải thích công việc database đã làm, nhưng không thay thế end-to-end latency. Response time còn gồm connection pool, mạng, TLS, driver BSON decoding, serialization, business logic và concurrency.

## 6. Thiết kế index theo workload

### 6.1. Equality, sort và range

Ví dụ:

~~~javascript
db.orders_embedded.find({
  customerId: "CUS-001",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z")
  }
}).sort({ createdAt: -1 }).limit(20);
~~~

Ứng viên index:

~~~javascript
db.orders_embedded.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "idx_customer_created" }
);
~~~

Nguyên tắc **Equality – Sort – Range (ESR)** thường hữu ích để định hướng thứ tự field trong compound index. Nhưng index tốt phải đo trong workload thật; các trường hợp sort/range đa chiều hoặc filter có độ chọn lọc khác nhau có thể cần kế hoạch khác.

### 6.2. Index trên field nằm trong array

Tìm order có sản phẩm cụ thể:

~~~javascript
db.orders_embedded.find({
  "items.productId": "PRD-01"
});
~~~

Index ứng viên:

~~~javascript
db.orders_embedded.createIndex(
  { "items.productId": 1, createdAt: -1 },
  { name: "idx_item_product_created" }
);
~~~

Đây là **multikey index** vì `items` là array. Một document có nhiều item có thể đóng góp nhiều index entry. Các quy tắc index multikey cũng ảnh hưởng đến điều kiện sort và việc kết hợp nhiều field từ array.

Mảng nhúng dài làm tăng:

- Index entry cần lưu và cập nhật.
- Kích thước document và payload.
- Chi phí insert/update đối với các field được index.
- Rủi ro hot document nếu nhiều writer sửa cùng một array.

Cùng nghiệp vụ, mô hình reference cho phép index riêng:

~~~javascript
db.order_items.createIndex(
  { productId: 1, orderId: 1 },
  { name: "idx_item_product_order" }
);
~~~

Nhưng để trả **đơn hàng** thay vì **line item**, phải cộng chi phí join/lookup hoặc truy vấn theo `orderId`. So sánh hai câu lệnh trả dữ liệu khác nhau là không công bằng.

### 6.3. Index luôn có chi phí bảo trì

Một insert có thể phải ghi dữ liệu chính và cập nhật nhiều index. Update các field trong index có thể đòi hỏi sửa các key liên quan. Quá nhiều index dẫn đến tăng disk, nhu cầu cache, thời gian build và write amplification.

Danh sách kiểm tra khi thêm index:

1. Truy vấn nào thực sự dùng index này?
2. Index có hỗ trợ cả filter lẫn sort không?
3. Có trùng đáng kể với index hiện có không?
4. Kích thước index so với dữ liệu là bao nhiêu?
5. Có bao nhiêu thao tác ghi làm thay đổi key liên quan?
6. Index phục vụ constraint như unique hay chỉ phục vụ tốc độ đọc?
7. Index có thể là partial index hoặc loại khác phù hợp hơn không?

Một index có ít lượt truy cập vẫn có thể cần thiết để bảo đảm uniqueness. Đừng xóa chỉ vì thống kê truy cập thấp.

### 6.4. Xem metadata và mức sử dụng index

~~~javascript
db.orders_embedded.getIndexes();
db.orders_embedded.stats();

db.orders_embedded.aggregate([
  { $indexStats: {} }
]);
~~~

Trong các phiên bản hỗ trợ, collection stats có những trường như `indexSizes`, `totalIndexSize`, `avgObjSize`, `size` và `storageSize`. Cách diễn giải cụ thể phụ thuộc storage engine và version.

`$indexStats` cho số lần truy cập index trong cửa sổ thống kê được duy trì. Các số này có thể reset sau sự kiện vận hành như restart/index recreation. Nên quan sát một khoảng thời gian đại diện trước khi kết luận index vô dụng.

## 7. Đánh giá dung lượng BSON, storage và index

### 7.1. Giới hạn 16 MiB và tăng trưởng mảng

MongoDB giới hạn một **BSON document thông thường tối đa 16 MiB**. Nếu nhúng toàn bộ comment/review vào một document cha, mảng có thể tiến đến giới hạn này khi dữ liệu phát triển.

~~~javascript
// Ví dụ mô hình dễ phình không kiểm soát:
{
  _id: "PRD-01",
  name: "Bàn phím cơ",
  reviews: [
    // Mọi review từ ngày ra mắt đến nhiều năm sau...
  ]
}
~~~

Ngay cả trước khi đạt 16 MiB, document quá lớn có thể gây p95/p99 latency, áp lực cache và xung đột khi ghi. Thay thế thường là review riêng, phân trang và nếu cần thì có một tập nhỏ review đã chọn/được tính trước trong document product.

### 7.2. Đo kích thước document bằng `$bsonSize`

Với collection order có mảng `items`:

~~~javascript
db.orders_embedded.aggregate([
  {
    $project: {
      documentBytes: { $bsonSize: "$$ROOT" },
      itemCount: { $size: "$items" }
    }
  },
  {
    $group: {
      _id: null,
      count: { $sum: 1 },
      avgBytes: { $avg: "$documentBytes" },
      maxBytes: { $max: "$documentBytes" },
      totalMeasuredBytes: { $sum: "$documentBytes" },
      avgItems: { $avg: "$itemCount" }
    }
  }
]);
~~~

Ví dụ giả định mọi order đều có array `items`. Nếu dữ liệu cũ có document thiếu field hoặc `items` không phải array, cần xử lý trước khi dùng `$size`.

Không chỉ đo average. Các document lớn nhất, các nhóm outlier và phân bố số phần tử có thể quyết định rủi ro lớn nhất.

### 7.3. BSON logical size khác disk size

| Chỉ số | Phản ánh |
|---|---|
| `$bsonSize` | Kích thước BSON logic của document |
| `size` hoặc `avgObjSize` trong stats | Thông tin kích thước dữ liệu logic theo thống kê |
| `storageSize` | Dung lượng storage được cấp dùng cho dữ liệu, chịu ảnh hưởng storage engine/compression |
| `totalIndexSize` | Dung lượng các index được báo cáo |
| Network payload | Số byte truyền thực tế qua driver và API, có thể khác kích thước BSON lưu trữ |

Document nhiều field lặp lại có thể được compression tốt; ngược lại, dữ liệu khó nén có thể chiếm nhiều chỗ. Không lấy kết quả `$bsonSize` rồi khẳng định đó là chi phí disk hoặc hóa đơn cloud. Cần đo trên bản dữ liệu đại diện.

### 7.4. Ước lượng trùng lặp theo tăng trưởng

Giả sử có **1.000.000 order**, mỗi order trung bình **5 item**; mỗi item sao chép tên sản phẩm trung bình **50 byte nội dung string**.

~~~text
1.000.000 orders × 5 items/order × 50 bytes/item
= 250.000.000 bytes ≈ 250 MB payload tên sản phẩm thô
~~~

Đây chưa phải tổng BSON size. Cần cộng overhead BSON, tên field, các giá trị snapshot khác, index và replica; storage compression có thể giảm dung lượng disk. Với snapshot lịch sử, chi phí này có thể hợp lý. Với dữ liệu live phải đồng bộ mỗi lần sửa product, chi phí fan-out update cần tính thêm.

Dự báo tổng dung lượng nên bao gồm:

~~~text
Dữ liệu được lưu sau ảnh hưởng storage engine
+ Index
+ Replica copies / mức dự phòng
+ Backup / snapshot và retention
+ Dung lượng tạm cho migration, restore, index build
+ Dung lượng tăng trưởng dự phòng
~~~

Đối với dịch vụ managed, chi phí tính theo tier, dung lượng, I/O, backup và mạng còn phụ thuộc nhà cung cấp.

### 7.5. Đừng bỏ qua read payload

Nếu trang danh sách chỉ cần `orderNo`, `status`, `total` mà API lại trả cả `items`, payload có thể tăng rất lớn khi mỗi order có nhiều items. Projection giảm dữ liệu chuyển về client; index phù hợp và read model có thể giảm thêm chi phí trong những trường hợp nhất định.

Một mô hình chia nhỏ header và detail có thể phù hợp với ứng dụng chỉ đọc detail hiếm khi, dù thêm join khi cần xem detail.

## 8. Chi phí cập nhật: đơn vị đo là một thay đổi nghiệp vụ

### 8.1. Update một document có tính nguyên tử

MongoDB cung cấp atomicity cho thao tác ghi **trên một document**, kể cả khi sửa nhiều field trong document:

~~~javascript
db.orders_embedded.updateOne(
  { _id: "ORD-1001", status: "NEW" },
  {
    $set: {
      status: "PAID",
      paidAt: new Date(),
      updatedAt: new Date()
    }
  }
);
~~~

Filter gồm trạng thái mong đợi là một kiểu **conditional update** giúp phát hiện trạng thái đã chuyển bởi request khác. Ứng dụng phải xử lý `matchedCount`, lỗi, retry và idempotency phù hợp.

Atomicity trên một document không có nghĩa mọi câu lệnh đều nhanh. Chi phí vẫn phụ thuộc index, kích thước, storage engine, write concern và nhiều writer cùng tác động.

### 8.2. Cập nhật array: phần tử ít hay nhiều?

Thêm một item bằng `$push`:

~~~javascript
db.orders_embedded.updateOne(
  { _id: "ORD-1001" },
  {
    $push: {
      items: {
        productId: "PRD-03",
        productNameAtPurchase: "Tai nghe",
        quantity: 1,
        unitPriceAtPurchase: NumberDecimal("450000")
      }
    }
  }
);
~~~

Đây chỉ là ví dụ về cập nhật array; với đơn hàng thật, còn phải cập nhật tổng tiền, tồn kho, thuế và các quy tắc trạng thái.

Nếu array dài và được sửa liên tục, hãy đo:

- Tốc độ tăng BSON size và số index keys.
- Update latency p95/p99.
- Write conflict/retry hoặc contention trên hot document.
- Số byte/network khi phải đọc lại document.
- Độ phức tạp khi nhiều thao tác sửa array cùng lúc.
- Rủi ro vượt giới hạn document.

### 8.3. Không mặc định mỗi update phải ghi lại toàn bộ BSON

Một câu khẳng định thiếu chính xác là: “Sửa 10 byte trong document 1 MiB luôn ghi lại 1 MiB xuống đĩa”. Storage engine có thể có các tối ưu và cơ chế ghi khác nhau theo loại update, index, journal/oplog và cấu trúc dữ liệu.

Không thể suy ra write amplification từ kích thước document một cách tuyến tính trong mọi trường hợp. Nhưng document lớn vẫn có chi phí cache, truyền dữ liệu, concurrency và phát triển index; cần benchmark đúng workload.

### 8.4. Fan-out update khi trùng lặp dữ liệu live

Nếu copy giá bán hiện tại của sản phẩm vào mọi đơn rồi muốn đồng bộ giá mới, một thay đổi có thể phải tìm và sửa hàng trăm nghìn document.

Ví dụ minh họa **một kiểu cập nhật nguy hiểm đối với snapshot lịch sử**, không chạy trên đơn hàng đã chốt:

~~~javascript
db.orders_embedded.updateMany(
  { "items.productId": "PRD-01" },
  {
    $set: {
      "items.$[line].productNameAtPurchase": "Tên sản phẩm mới"
    }
  },
  {
    arrayFilters: [
      { "line.productId": "PRD-01" }
    ]
  }
);
~~~

Đối với field `productNameAtPurchase`, thao tác trên thường còn **sai nghiệp vụ** vì lịch sử phải giữ thông tin lúc mua.

Một thiết kế phù hợp hơn:

- Lưu giá và tên **lúc mua** trong order (snapshot bất biến).
- Lưu `products.currentPrice` và tên hiện tại trong catalog (nguồn chuẩn).
- Nếu trang cần dữ liệu hiện tại, đọc riêng theo `productId` hoặc dùng một read model đồng bộ có kiểm soát.
- Chỉ trả chi phí denormalization khi lợi ích đọc thực sự đáng giá.

Số document bị ảnh hưởng là tiêu chí thiết yếu: một lệnh `updateMany` có thể tốn hơn nhiều so với vài lệnh `updateOne`.

### 8.5. Hot document và nhiều writer

Một document sản phẩm chứa toàn bộ reviews và mọi người dùng đều `$push` vào cùng array là điểm ghi tập trung. Database có thể gặp write conflicts/retries hoặc giảm throughput khi nhiều write cạnh tranh trên cùng document.

Tách reviews thành các document độc lập giúp phân tán thao tác ghi và tạo index riêng cho phân trang. Nếu cần điểm đánh giá tổng hợp, `ratingSummary` có thể là computed field cập nhật theo cơ chế được thiết kế riêng.

### 8.6. Transaction và chi phí nhất quán

Embedding giúp thao tác trên nhiều field của một document có thể nguyên tử. Với referencing, một nghiệp vụ cần cập nhật nhiều document hoặc collection có thể cần **multi-document transaction** trong topology được hỗ trợ.

Transaction có chi phí quản lý phiên, kiểm soát đồng thời, commit và retry. Nó không tự loại bỏ vấn đề fan-out update, document quá lớn hay index kém. Hãy dùng transaction để đáp ứng yêu cầu nhất quán thực sự, sau khi đã xem xét phạm vi cập nhật.

### 8.7. Đo chi phí cập nhật đầy đủ

Với một thay đổi nghiệp vụ, hỏi:

~~~text
Một thay đổi nghiệp vụ
  -> Bao nhiêu document phải tìm và sửa?
  -> Bao nhiêu index bị cập nhật?
  -> Có cần transaction nhiều collection không?
  -> Bao nhiêu writer có thể cập nhật cùng document?
  -> Tốc độ update và độ trễ p95/p99?
  -> Sự cố giữa chừng dẫn đến trạng thái gì?
  -> Có cần rebuild cache hoặc read model không?
  -> Chi phí replication, backup và lưu trữ tăng thế nào?
~~~

Đây là cách đánh giá thực tế hơn việc chỉ đo thời gian của một lệnh đơn.

## 9. Mẫu thiết kế giúp cân bằng bốn trục chi phí

| Pattern | Hướng tiếp cận | Phù hợp khi | Chi phí phải quản lý |
|---|---|---|---|
| Embedding | Đặt child bên trong cha | Child ít, có giới hạn, đọc cùng | Document/multikey index lớn, hot updates |
| Reference | Khóa liên kết sang collection riêng | Child nhiều, độc lập, cần phân trang | Join, index liên kết, tính nhất quán |
| Subset | Nhúng phần đọc thường xuyên, tách phần ít dùng | Detail lớn, UI chỉ lấy vài field | Đồng bộ subset nếu là bản sao |
| Extended reference | Lưu khóa và vài field ổn định của entity liên quan | Giảm lookup với snapshot/read model | Quy định nguồn chuẩn và refresh |
| Bucket | Gom sự kiện thành từng nhóm có giới hạn | Lượng event lớn, truy vấn theo kỳ | Bucket boundary, concurrency, sizing |
| Outlier | Phân tách riêng phần vượt ngưỡng | Đa số document nhỏ, ít trường hợp cực lớn | Hai đường đọc và migration |
| Computed | Lưu giá trị tổng hợp tính trước | Đọc tổng hợp rất nhiều | Consistency, retry, rebuild |

**Ví dụ subset:** profile chỉ giữ vài hoạt động gần nhất để hiển thị trên dashboard, còn lịch sử đầy đủ ở `user_activities`.

**Ví dụ bucket:** sensor readings theo thiết bị và giờ, mỗi bucket có giới hạn kích thước. Với telemetry theo thời gian, nên đánh giá cả **time series collections** trước khi tự viết bucket thủ công.

**Ví dụ computed:** product lưu `ratingSummary.average` và `ratingSummary.count`, còn reviews đầy đủ nằm ở collection riêng. Nếu tổng hợp bất đồng bộ, UI phải chấp nhận độ trễ và có kế hoạch sửa lệch.

## 10. Thực hành: hai schema cùng một bộ dữ liệu

Sử dụng mongosh trong database lab riêng. Các lệnh cố ý tạo namespace mới; không chạy trên database production. Với lượng dữ liệu nhỏ, mục tiêu là quan sát cấu trúc và query plan chứ chưa phải benchmark hiệu năng quy mô lớn.

### 10.1. Tạo dữ liệu sản phẩm

~~~javascript
use document_model_lab

db.products.insertMany([
  {
    _id: "PRD-01",
    name: "Bàn phím cơ",
    currentPrice: NumberDecimal("850000"),
    stock: 120
  },
  {
    _id: "PRD-02",
    name: "Chuột không dây",
    currentPrice: NumberDecimal("320000"),
    stock: 250
  },
  {
    _id: "PRD-03",
    name: "Tai nghe",
    currentPrice: NumberDecimal("450000"),
    stock: 90
  }
]);
~~~

### 10.2. Phương án A: nhúng items

~~~javascript
db.orders_embedded.insertMany([
  {
    _id: "ORD-1001",
    customerId: "CUS-001",
    createdAt: ISODate("2026-11-14T03:15:00Z"),
    status: "NEW",
    total: NumberDecimal("1490000"),
    items: [
      {
        productId: "PRD-01",
        productNameAtPurchase: "Bàn phím cơ",
        quantity: 1,
        unitPriceAtPurchase: NumberDecimal("850000")
      },
      {
        productId: "PRD-02",
        productNameAtPurchase: "Chuột không dây",
        quantity: 2,
        unitPriceAtPurchase: NumberDecimal("320000")
      }
    ]
  },
  {
    _id: "ORD-1002",
    customerId: "CUS-001",
    createdAt: ISODate("2026-11-14T04:20:00Z"),
    status: "PAID",
    total: NumberDecimal("450000"),
    items: [
      {
        productId: "PRD-03",
        productNameAtPurchase: "Tai nghe",
        quantity: 1,
        unitPriceAtPurchase: NumberDecimal("450000")
      }
    ]
  },
  {
    _id: "ORD-1003",
    customerId: "CUS-002",
    createdAt: ISODate("2026-11-14T05:00:00Z"),
    status: "NEW",
    total: NumberDecimal("850000"),
    items: [
      {
        productId: "PRD-01",
        productNameAtPurchase: "Bàn phím cơ",
        quantity: 1,
        unitPriceAtPurchase: NumberDecimal("850000")
      }
    ]
  }
]);
~~~

Tạo index cho read patterns:

~~~javascript
db.orders_embedded.createIndex(
  { customerId: 1, createdAt: -1, _id: -1 },
  { name: "idx_customer_recent" }
);

db.orders_embedded.createIndex(
  { "items.productId": 1, createdAt: -1 },
  { name: "idx_product_created" }
);
~~~

### 10.3. Phương án B: tham chiếu items

~~~javascript
db.orders_ref.insertMany([
  {
    _id: "ORD-1001",
    customerId: "CUS-001",
    createdAt: ISODate("2026-11-14T03:15:00Z"),
    status: "NEW",
    total: NumberDecimal("1490000")
  },
  {
    _id: "ORD-1002",
    customerId: "CUS-001",
    createdAt: ISODate("2026-11-14T04:20:00Z"),
    status: "PAID",
    total: NumberDecimal("450000")
  },
  {
    _id: "ORD-1003",
    customerId: "CUS-002",
    createdAt: ISODate("2026-11-14T05:00:00Z"),
    status: "NEW",
    total: NumberDecimal("850000")
  }
]);

db.order_items.insertMany([
  {
    _id: "OI-001",
    orderId: "ORD-1001",
    productId: "PRD-01",
    productNameAtPurchase: "Bàn phím cơ",
    quantity: 1,
    unitPriceAtPurchase: NumberDecimal("850000")
  },
  {
    _id: "OI-002",
    orderId: "ORD-1001",
    productId: "PRD-02",
    productNameAtPurchase: "Chuột không dây",
    quantity: 2,
    unitPriceAtPurchase: NumberDecimal("320000")
  },
  {
    _id: "OI-003",
    orderId: "ORD-1002",
    productId: "PRD-03",
    productNameAtPurchase: "Tai nghe",
    quantity: 1,
    unitPriceAtPurchase: NumberDecimal("450000")
  },
  {
    _id: "OI-004",
    orderId: "ORD-1003",
    productId: "PRD-01",
    productNameAtPurchase: "Bàn phím cơ",
    quantity: 1,
    unitPriceAtPurchase: NumberDecimal("850000")
  }
]);
~~~

Index:

~~~javascript
db.orders_ref.createIndex(
  { customerId: 1, createdAt: -1, _id: -1 },
  { name: "idx_customer_recent" }
);

db.order_items.createIndex(
  { orderId: 1 },
  { name: "idx_items_order" }
);

db.order_items.createIndex(
  { productId: 1, orderId: 1 },
  { name: "idx_items_product_order" }
);
~~~

### 10.4. So cùng nội dung nghiệp vụ

Chi tiết đơn nhúng:

~~~javascript
db.orders_embedded.findOne({ _id: "ORD-1001" });
~~~

Chi tiết đơn tham chiếu:

~~~javascript
db.orders_ref.aggregate([
  { $match: { _id: "ORD-1001" } },
  {
    $lookup: {
      from: "order_items",
      localField: "_id",
      foreignField: "orderId",
      as: "items"
    }
  }
]);
~~~

So số truy vấn cần thực hiện, dữ liệu trả về, index trên khóa join và CPU/latency dưới tải thực tế. Không so một truy vấn trả header với truy vấn trả cả items rồi kết luận mô hình nào nhanh hơn.

### 10.5. Đo explain theo hai đường truy vấn

Danh sách đơn:

~~~javascript
db.orders_embedded
  .find({ customerId: "CUS-001" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");

db.orders_ref
  .find({ customerId: "CUS-001" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
~~~

Tìm orders liên quan đến một product:

~~~javascript
db.orders_embedded
  .find({ "items.productId": "PRD-01" })
  .explain("executionStats");

db.order_items
  .find({ productId: "PRD-01" })
  .explain("executionStats");
~~~

Với referenced model, câu truy vấn cuối trả item, không phải order header. Nếu yêu cầu nghiệp vụ là trả order, hãy tính cả bước ghép order. Đây là cách tránh phép so sánh lệch phạm vi.

### 10.6. Đo BSON bytes trên từng mô hình

~~~javascript
db.orders_embedded.aggregate([
  {
    $project: {
      bsonBytes: { $bsonSize: "$$ROOT" },
      itemCount: { $size: "$items" }
    }
  }
]);

db.orders_ref.aggregate([
  {
    $project: {
      bsonBytes: { $bsonSize: "$$ROOT" }
    }
  }
]);

db.order_items.aggregate([
  {
    $project: {
      bsonBytes: { $bsonSize: "$$ROOT" }
    }
  }
]);
~~~

Kiểm tra storage và index:

~~~javascript
db.orders_embedded.stats();
db.orders_ref.stats();
db.order_items.stats();

db.orders_embedded.getIndexes();
db.orders_ref.getIndexes();
db.order_items.getIndexes();
~~~

**So sánh công bằng:** Dung lượng referenced bằng tổng của **orders_ref + order_items + index của cả hai collection**. Chỉ so `orders_ref` với `orders_embedded` là bỏ sót dữ liệu child.

### 10.7. Đo thay đổi trạng thái đơn

~~~javascript
db.orders_embedded.updateOne(
  { _id: "ORD-1001", status: "NEW" },
  { $set: { status: "PAID", updatedAt: new Date() } }
);

db.orders_ref.updateOne(
  { _id: "ORD-1001", status: "NEW" },
  { $set: { status: "PAID", updatedAt: new Date() } }
);
~~~

Ở cả hai mô hình, đây là thay đổi trên một document. Chênh lệch rõ hơn có thể đến khi sửa items, ghi đồng thời hoặc thực hiện nghiệp vụ yêu cầu atomicity xuyên header và child.

### 10.8. Ghi kết quả vào bảng đánh giá

| Chỉ số | Embedded | Referenced | Cách đo |
|---|---:|---:|---|
| Collection cần cho chi tiết đơn | 1 | 2 | Sơ đồ dữ liệu |
| Số round trip của implementation | Đo | Đo | Telemetry driver/API |
| `totalKeysExamined` | Đo | Đo | Explain các query liên quan |
| `totalDocsExamined` | Đo | Đo | Explain và join phụ |
| BSON bytes toàn dataset | Đo | Đo | `$bsonSize` cộng các collection |
| Index bytes toàn dataset | Đo | Đo | Stats của mọi collection |
| p95 đọc chi tiết | Đo | Đo | Load test với dữ liệu lớn |
| p95 update item | Đo | Đo | Load test write |
| Kích thước document lớn nhất | Đo | Đo | Aggregation, outlier |
| Tính nhất quán khi ghi nhiều entity | Đánh giá | Đánh giá | Thiết kế transaction/atomicity |

Các ô “Đo” cần được điền từ dữ liệu lab/workload thật, không tự gán số hiệu năng.

## 11. Benchmark công bằng ở quy mô thực tế

### 11.1. Những điều kiện phải giữ tương đương

- Cùng phiên bản MongoDB, storage engine và hạ tầng CPU/RAM/disk.
- Cùng dữ liệu nghiệp vụ và cùng phân bố số orders/items/reviews.
- Cùng điều kiện filter, sort, projection, page size và nội dung trả về.
- Cùng write concern, read concern và chính sách transaction.
- Cùng số lượng client, connection pool, mức đồng thời, mạng và driver.
- Mỗi mô hình có index phù hợp với chính workload của nó.
- Cùng tỷ lệ đọc/ghi, đặc biệt các đợt peak traffic.
- Có warm-up, lặp lại nhiều lần và ghi độ biến động kết quả.

Không công bằng nếu benchmark embedding khi data nằm trong cache ấm, còn reference dùng dữ liệu cold trên disk; cũng không công bằng nếu một mô hình có index đầy đủ, mô hình kia không.

### 11.2. Dữ liệu giả lập phải phản ánh sự phân bố

Nếu tất cả 1.000.000 order đều có đúng hai items, bạn bỏ lỡ:

- Một số ít khách có rất nhiều đơn.
- Sản phẩm bán chạy được nhắc lại trong hàng trăm nghìn orders.
- Đơn có một item và một số đơn B2B hàng trăm items.
- Các phiên ghi cao điểm, update cùng entity.
- Dữ liệu legacy thiếu field hoặc số field không đồng nhất.
- Các nhóm document rất lớn tạo p99 latency.

Dữ liệu outlier có thể quyết định tính khả thi của embedding trước khi giá trị trung bình trở thành vấn đề.

### 11.3. Quy trình thực nghiệm

1. Viết giả thuyết cụ thể: ví dụ “nhúng items giảm p95 chi tiết đơn ít nhất 20%, trong khi total storage tăng dưới 15%”.
2. Tạo dữ liệu đại diện cho cả hai phương án.
3. Tạo index phù hợp, ghi kích thước và thời gian xây dựng.
4. Warm-up, chạy các mức tải ổn định, đo p50/p95/p99 và throughput.
5. Chạy riêng read-heavy, write-heavy và mixed workloads.
6. Đo các thao tác fan-out update và trường hợp một key rất nóng.
7. Theo dõi CPU, cache, memory, disk I/O, network, replication lag và write conflicts khi khả dụng.
8. Lặp phép đo với cùng điều kiện; ghi cả trung vị và độ biến động.
9. Ước lượng tổng chi phí storage/index/backup và công thay đổi schema.
10. Chọn phương án đáp ứng yêu cầu và lưu giả định để theo dõi sau triển khai.

`explain()` chỉ là một phần của đo lường. p95/p99 thực sự nên được thu từ ứng dụng hoặc công cụ load test dưới mức concurrency tương đương production.

Không bật profiler mức chi tiết cao trên production chỉ để lấy số liệu tùy tiện; profiling có overhead và có thể ghi thông tin truy vấn nhạy cảm. Chọn cơ chế quan sát theo chính sách vận hành.

## 12. Ma trận quyết định có trọng số

Dùng hai lớp đánh giá:

**Lớp 1 — Điều kiện bắt buộc (pass/fail):**

- Đúng ngữ nghĩa dữ liệu (snapshot hay live).
- Không có mảng tăng vô hạn vượt giới hạn document.
- Đáp ứng quyền truy cập và retention.
- Đáp ứng mức consistency, transaction và recovery yêu cầu.
- Có cách migrate và rollback phù hợp.

**Lớp 2 — Tối ưu có trọng số:** đọc, index, dung lượng, cập nhật và khả năng mở rộng.

Ví dụ thang điểm 1–5, trong đó 5 tốt nhất. Điểm hoàn toàn **giả định để minh họa phương pháp**, không phải benchmark MongoDB:

| Tiêu chí | Trọng số | Embedding | Reference | Hybrid |
|---|---:|---:|---:|---:|
| Chi tiết đơn | 30% | 5 | 3 | 5 |
| Truy vấn theo sản phẩm | 20% | 3 | 5 | 4 |
| Dung lượng và index | 15% | 3 | 4 | 4 |
| Chi phí cập nhật và nhất quán | 25% | 3 | 4 | 5 |
| Quan hệ tăng trưởng | 10% | 2 | 5 | 4 |

Tính điểm:

~~~text
Embedding = 5×0,30 + 3×0,20 + 3×0,15 + 3×0,25 + 2×0,10 = 3,50
Reference = 3×0,30 + 5×0,20 + 4×0,15 + 4×0,25 + 5×0,10 = 4,00
Hybrid    = 5×0,30 + 4×0,20 + 4×0,15 + 5×0,25 + 4×0,10 = 4,55
~~~

Trong ví dụ này hybrid có điểm cao, nhưng nếu workload thiên về ghi sự kiện hoặc mỗi child luôn được đọc riêng, kết quả có thể đảo ngược. Không chọn một mô hình vi phạm điều kiện bắt buộc chỉ vì điểm tổng cao.

## 13. Các tình huống thường gặp

### 13.1. Giỏ hàng có giới hạn items

**Yêu cầu:** Mỗi giỏ có tối đa 50 sản phẩm, trang chi tiết luôn tải toàn bộ giỏ, cập nhật thường trên một giỏ.

**Ứng viên:** Nhúng items trong cart. Cần kiểm tra giới hạn và concurrency khi nhiều request sửa giỏ cùng lúc; atomic update trong một document có lợi.

### 13.2. Bình luận dưới bài viết phổ biến

**Yêu cầu:** Một bài có thể có hàng trăm nghìn comments; mỗi lần chỉ xem 20 comment; nhiều người gửi đồng thời.

**Ứng viên:** `comments` collection riêng, index `{postId:1, createdAt:-1, _id:-1}`, phân trang. Có thể giữ vài comment nổi bật như read model trong post nếu thực sự cần.

### 13.3. Hóa đơn đã thanh toán

**Yêu cầu:** Tên và giá lúc mua phải không thay đổi khi catalog cập nhật.

**Ứng viên:** Nhúng line item snapshot; giữ productId để tham chiếu catalog khi cần, không sửa snapshot lịch sử. Đây là dữ liệu trùng lặp có giá trị nghiệp vụ.

### 13.4. Profile và lịch sử đăng nhập

**Yêu cầu:** Profile đọc rất nhiều; login events tăng liên tục và có retention riêng.

**Ứng viên:** Profile gọn, login events collection riêng theo `userId` và timestamp. Tránh nhúng toàn bộ lịch sử đăng nhập vào profile.

### 13.5. Điểm đánh giá sản phẩm

**Yêu cầu:** Trang sản phẩm đọc average rating hàng nghìn lần, review mới liên tục, danh sách review phân trang.

**Ứng viên:** Reviews riêng và computed `ratingSummary` trên product. Phải có cơ chế cập nhật chống trùng, phát hiện độ lệch và rebuild.

### 13.6. Tài liệu cấu hình ít thay đổi

**Yêu cầu:** Cấu hình có vài object lồng nhau, đọc cả document, hiếm khi sửa và cần cập nhật như một phiên bản.

**Ứng viên:** Nhúng trong một document. Nếu có hàng nghìn writer sửa đồng thời, phải xem xét versioning/conditional update và contention.

## 14. Những hiểu lầm thường gặp

**“MongoDB thì phải nhúng tất cả.”** Không đúng. Nhúng quan hệ không giới hạn có thể tạo document quá lớn và hot writes.

**“Reference luôn tiết kiệm dung lượng.”** Không chắc. Collection mới cần `_id`, khóa liên kết, index và overhead cho nhiều document.

**“Nhúng dữ liệu thì không cần index.”** Không đúng. Truy vấn filter/sort trên parent và array vẫn có thể cần index.

**“Nhiều index nghĩa là tốc độ luôn tốt hơn.”** Không đúng. Index tăng tài nguyên và chi phí cập nhật; planner có thể không dùng.

**“`$lookup` luôn chậm hơn một document.”** Không thể kết luận tuyệt đối. Hiệu quả phụ thuộc index, số bản ghi match, cache và lượng kết quả.

**“Sửa một field trong document 1 MiB chắc chắn ghi lại 1 MiB lên disk.”** Không phải quy luật chung của storage engine. Cần đo.

**“Mỗi lần đổi giá sản phẩm phải sửa toàn bộ order cũ.”** Thường sai về nghiệp vụ nếu giá order là snapshot tại thời điểm mua.

**“Dữ liệu trung bình nhỏ thì không sợ 16 MiB.”** Những outlier có mảng cực lớn vẫn có thể chạm giới hạn.

**“`explain` là đủ để biết latency sản phẩm.”** Không đúng. Còn mạng, driver, mapping, serialization và concurrency.

**“Một lần benchmark thắng là schema tối ưu.”** Không đủ. Cần nhiều vòng đo, tải đại diện và đường ghi.

**“Transaction giải quyết mọi vấn đề của reference.”** Transaction xử lý tính nguyên tử nhiều document trong điều kiện hỗ trợ, nhưng không tự làm giảm fan-out và chi phí storage.

**“Trùng lặp dữ liệu luôn sai.”** Snapshot và read model có thể là lựa chọn đúng nếu định nghĩa rõ nguồn chuẩn và chính sách cập nhật.

## 15. Bài tập

### Bài tập 1 — Lập workload matrix

Một hệ thống học trực tuyến có:

- 100.000 học viên.
- Mỗi học viên đăng ký nhiều khóa.
- Mỗi khóa có danh sách bài giảng thường đọc cùng.
- Mỗi khóa có hàng nghìn lịch sử lượt xem.
- Trang lịch sử chỉ trả 20 event/trang.
- Tiến độ học viên cập nhật liên tục.

Hãy lập bảng Operation/Filter/Sort/Projection/Frequency/Growth/Consistency và đề xuất embedding/reference cho `lessons`, `viewEvents`, `studentProgress`. Giải thích bằng cả đường đọc và đường ghi.

### Bài tập 2 — Phân tích explain

Truy vấn:

~~~javascript
db.orders_embedded.find({
  customerId: "CUS-100",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(20);
~~~

Một lần đo giả định:

~~~text
nReturned = 20
totalKeysExamined = 120000
totalDocsExamined = 90000
~~~

Vì sao nên điều tra? Đề xuất hai compound index ứng viên và giải thích cách kiểm chứng thứ tự field bằng explain. Tại sao độ chọn lọc và phân bố dữ liệu ảnh hưởng quyết định?

### Bài tập 3 — Tính tăng trưởng thô

Một collection `posts` có 200.000 bài; mỗi bài trung bình 500 bình luận; mỗi comment giả định chiếm 180 byte BSON.

- Ước lượng tổng dữ liệu comment trước index, compression và replica.
- Giải thích vì sao một số bài cực phổ biến có thể chạm giới hạn 16 MiB.
- Phân tích chi phí multikey index và việc thêm comment đồng thời.
- Đề xuất collection comments riêng và index theo post/time.

### Bài tập 4 — Chi phí cập nhật dữ liệu trùng lặp

Tên một đơn vị vận chuyển xuất hiện trong hai triệu order. Doanh nghiệp đổi thương hiệu:

1. Tên trên order là snapshot hay dữ liệu live?
2. Nếu snapshot, có nên sửa hai triệu order?
3. Nếu là cache live, cách quản lý đồng bộ nào phù hợp?
4. Reference sẽ tăng chi phí đọc ở endpoint nào?
5. Cần đo những chỉ số nào trước khi đổi schema?

### Bài tập 5 — Thử nghiệm schema

Từ bộ dữ liệu lab, sinh thêm orders với phân bố số items không đều. So sánh:

- p95 chi tiết đơn và danh sách đơn.
- `totalKeysExamined`/`totalDocsExamined` của các read patterns.
- BSON size toàn dữ liệu cùng tổng index size.
- p95 update item/trạng thái dưới concurrency.
- Những đơn B2B có số items lớn bất thường.
- Khả năng migrate từ mô hình cũ sang mô hình mới.

Viết đề xuất cuối cùng có nêu cả lợi ích, chi phí và tình huống mà phương án còn lại tốt hơn.

## 16. Câu hỏi ôn tập

1. Vì sao mô hình document nên bắt đầu từ workload?
2. Những thuộc tính nào của query quyết định index?
3. Khi nào embedding tốt cho atomicity và locality?
4. Khi nào child nên tách collection?
5. Multikey index tăng chi phí thế nào?
6. `nReturned`, `totalKeysExamined` và `totalDocsExamined` giúp thấy điều gì?
7. Vì sao projection không đảm bảo giảm disk I/O tương ứng?
8. BSON logical size khác storage size như thế nào?
9. Vì sao phải cộng index của mọi collection khi đánh giá reference?
10. Trùng lặp snapshot khác cache live ở đâu?
11. Vì sao cập nhật nhỏ không luôn có chi phí ghi bằng kích thước document?
12. Hot document xuất hiện ra sao?
13. Multi-document transaction giải quyết gì và không giải quyết gì?
14. Một benchmark đáng tin cần những điều kiện tương đương nào?
15. Các điều kiện bắt buộc nào nên kiểm tra trước khi dùng bảng điểm trọng số?

## 17. Tổng kết

Đánh giá mô hình document MongoDB phải kết hợp **truy vấn, index, dung lượng và cập nhật**. Embedding có lợi với dữ liệu con nhỏ, đọc cùng cha và có giới hạn. Reference có lợi khi child tăng lớn, được đọc/phân trang và cập nhật độc lập. Hybrid thường hữu ích khi vừa cần snapshot lịch sử vừa cần dữ liệu live hoặc computed read model.

Một quyết định có thể kiểm chứng gồm: **workload rõ ràng → các phương án schema → index phù hợp → đo explain và BSON/index size → benchmark đọc/ghi dưới concurrency → đối chiếu consistency, giới hạn và tổng chi phí**. Trước mọi phép tối ưu, xác định ngữ nghĩa của dữ liệu sao chép: đây là snapshot được giữ nguyên hay bản sao phải đồng bộ theo nguồn chuẩn?

## Tài liệu chính thức tham khảo

- [MongoDB Manual — Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Manual — Embedded Data Versus References](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/)
- [MongoDB Manual — Data Model Design Patterns](https://www.mongodb.com/docs/manual/data-modeling/design-patterns/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [MongoDB Manual — BSON Document Limits](https://www.mongodb.com/docs/manual/reference/limits/)
- [MongoDB Manual — BSON Size Aggregation Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bsonSize/)
- [MongoDB Manual — Index Statistics Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
