# Mối liên hệ giữa BSON, truy vấn, index và aggregation trong MongoDB

## 1. Bức tranh tổng thể

Khi làm việc với MongoDB, bốn khái niệm **BSON**, **truy vấn (query)**, **chỉ mục (index)** và **đường ống tổng hợp (aggregation pipeline)** không hoạt động độc lập. Chúng nối với nhau thành một quá trình xử lý dữ liệu:

1. **BSON** quyết định tài liệu chứa những trường nào, giá trị thuộc kiểu gì và cấu trúc lồng nhau ra sao.
2. **Truy vấn** dùng các trường và kiểu dữ liệu đó để diễn tả tài liệu cần tìm.
3. **Index** lưu những khóa được trích từ tài liệu, giúp MongoDB định vị hoặc sắp xếp dữ liệu hiệu quả hơn nếu hình dạng truy vấn phù hợp.
4. **Aggregation** biến đổi một luồng tài liệu thành kết quả phân tích; một số giai đoạn vẫn có thể sử dụng index, còn những phép tính và gom nhóm thường phải xử lý dữ liệu sau khi đọc.

```text
Ứng dụng gửi lệnh tìm kiếm / aggregate
                   |
                   v
        Điều kiện + toán tử truy vấn
                   |
                   v
     Bộ lập kế hoạch thực thi (planner)
          /                     \
  Đọc theo index              Quét collection
   (IXSCAN, ...)                (COLLSCAN)
          \                     /
           v                   v
          Tài liệu BSON thỏa điều kiện
                   |
           Các stage aggregation
      ($match, $unwind, $group, ...)
                   |
                   v
             Kết quả BSON
```

Sơ đồ là mô hình khái niệm. MongoDB có thể kết hợp các bước, chọn kế hoạch khác nhau hoặc đẩy một số phép lọc xuống giai đoạn đọc dữ liệu. **Có index không đồng nghĩa mọi truy vấn hoặc mọi stage aggregation đều dùng được index.**

### Ví dụ xuyên suốt: đơn hàng

Giả sử hệ thống lưu collection `orders`. Các ví dụ dưới đây dùng cú pháp **mongosh** (MongoDB Shell); `ISODate(...)` và `NumberDecimal(...)` là hàm tạo giá trị BSON trong shell, không phải cú pháp JSON chuẩn.

```javascript
db.orders.insertMany([
  {
    _id: 1001,
    customerId: "C01",
    status: "PAID",
    createdAt: ISODate("2026-10-01T08:00:00Z"),
    shipping: { city: "Hà Nội" },
    items: [
      { sku: "BOOK-01", category: "BOOK",
        quantity: 2, unitPrice: NumberDecimal("150000") },
      { sku: "PEN-01", category: "STATIONERY",
        quantity: 1, unitPrice: NumberDecimal("20000") }
    ]
  },
  {
    _id: 1002,
    customerId: "C01",
    status: "PAID",
    createdAt: ISODate("2026-10-05T08:00:00Z"),
    shipping: { city: "Đà Nẵng" },
    items: [
      { sku: "BOOK-01", category: "BOOK",
        quantity: 1, unitPrice: NumberDecimal("150000") },
      { sku: "PEN-01", category: "STATIONERY",
        quantity: 3, unitPrice: NumberDecimal("20000") }
    ]
  },
  {
    _id: 1003,
    customerId: "C02",
    status: "PENDING",
    createdAt: ISODate("2026-10-06T08:00:00Z"),
    shipping: { city: "Hà Nội" },
    items: [
      { sku: "BOOK-01", category: "BOOK",
        quantity: 1, unitPrice: NumberDecimal("150000") }
    ]
  }
]);
```

Ở đây `createdAt` có kiểu ngày giờ, `unitPrice` là số thập phân Decimal128, `shipping` là tài liệu lồng nhau và `items` là mảng tài liệu. Chính những đặc điểm BSON này ảnh hưởng đến biểu thức lọc, loại index và cách viết pipeline.

## 2. BSON là nền tảng của dữ liệu và biểu thức truy vấn

### 2.1. BSON là gì?

**BSON (Binary JSON)** là định dạng nhị phân biểu diễn tài liệu của MongoDB. Về mặt ý tưởng, tài liệu giống một đối tượng JSON gồm cặp `field: value`, nhưng BSON hỗ trợ kiểu dữ liệu phong phú hơn JSON thuần:

| Kiểu BSON | Ví dụ trong mongosh | Ý nghĩa khi truy vấn |
|---|---|---|
| String | `"PAID"` | Phân biệt với số và giá trị kiểu khác |
| Số nguyên / số thực | `42`, `NumberInt(42)`, `NumberLong("42")` | Dùng toán tử so sánh, tính toán; chú ý độ chính xác và kiểu số |
| Decimal128 | `NumberDecimal("150000")` | Phù hợp số tiền cần biểu diễn thập phân chính xác |
| Date | `ISODate("2026-10-01T08:00:00Z")` | Lọc khoảng thời gian và sắp xếp theo thời điểm |
| ObjectId | `ObjectId("507f1f77bcf86cd799439011")` | Thường gặp ở `_id`, khác với chuỗi ký tự cùng hình dạng |
| Boolean | `true` | Lọc trạng thái đúng/sai |
| Array | `["BOOK", "PEN"]` | Có thể sinh nhiều khóa trong multikey index |
| Embedded document | `{ city: "Hà Nội" }` | Truy vấn theo đường dẫn như `shipping.city` |
| Null | `null` | Cần phân biệt giá trị null với trường không tồn tại |

MongoDB truyền, lưu và trả về tài liệu dưới dạng BSON qua driver và máy chủ. Cách trình bày bằng JSON hay cú pháp mongosh chỉ là **biểu diễn dễ đọc** của dữ liệu. Ví dụ Extended JSON có thể hiển thị ngày giờ dưới dạng:

```json
{
  "createdAt": { "$date": "2026-10-01T08:00:00Z" },
  "unitPrice": { "$numberDecimal": "150000" }
}
```

Ứng dụng dùng driver nên truyền đối tượng ngày giờ, Decimal128, ObjectId... đúng kiểu mà driver hỗ trợ; không nên tự biến tất cả thành chuỗi.

### 2.2. Kiểu dữ liệu quyết định phép so khớp

Xem hai điều kiện:

```javascript
// Đúng khi createdAt được lưu dưới dạng BSON Date.
db.orders.find({
  createdAt: { $gte: ISODate("2026-10-01T00:00:00Z") }
});

// Không tương đương: đây là một chuỗi.
db.orders.find({
  createdAt: { $gte: "2026-10-01T00:00:00Z" }
});
```

Điều kiện thứ hai không phải phép lọc ngày giờ như điều kiện đầu; đối với nhiều toán tử so sánh, MongoDB áp dụng quy tắc giới hạn theo kiểu BSON (type bracketing). Tương tự, `ObjectId("...")` không giống `"..."`, và việc lưu giá tiền lúc là chuỗi, lúc là số sẽ làm việc lọc/tổng hợp khó dự đoán.

Một số kiểu số BSON có thể được so sánh theo giá trị số dù khác kiểu lưu trữ, nhưng điều đó **không bảo đảm cùng độ chính xác** khi tính toán. Với số tiền, dùng Decimal128 nhất quán thường an toàn hơn dùng số thực nhị phân rồi kỳ vọng kết quả thập phân luôn chính xác.

### 2.3. Cấu trúc lồng nhau và mảng làm thay đổi ý nghĩa truy vấn

```javascript
// Đọc trường trong tài liệu lồng nhau.
db.orders.find({ "shipping.city": "Hà Nội" });

// Tìm đơn có ít nhất một phần tử items mang SKU này.
db.orders.find({ "items.sku": "BOOK-01" });

// Hai điều kiện phải đúng trên CÙNG một phần tử mảng.
db.orders.find({
  items: {
    $elemMatch: {
      category: "BOOK",
      quantity: { $gte: 2 }
    }
  }
});
```

Nếu chỉ dùng `{ "items.category": "BOOK", "items.quantity": { $gte: 2 } }`, hai điều kiện có thể được thỏa bởi **hai phần tử mảng khác nhau**. `$elemMatch` giải quyết điều đó. Khi lập index lên đường dẫn qua mảng, MongoDB thường tạo **multikey index**, có các hạn chế và quy tắc lập kế hoạch riêng.

Một điểm khác dễ nhầm:

```javascript
db.orders.find({ couponCode: null });                // null HOẶC thiếu field
db.orders.find({ couponCode: { $exists: false } });  // thiếu field
db.orders.find({
  couponCode: { $type: "null" }                        // BSON Null thực sự
});
```

Như vậy, trước khi tối ưu query hay index, phải biết dữ liệu thực tế chứa **kiểu gì**, trường **có thể thiếu hay không**, và trường **là mảng hay đối tượng**.

## 3. Query: diễn tả cần tìm tài liệu nào

### 3.1. Điều kiện lọc không phải thuật toán quét

`find()` diễn đạt kết quả mong muốn, không bắt buộc cách máy chủ đi tìm:

```javascript
db.orders.find(
  {
    customerId: "C01",
    status: "PAID",
    createdAt: { $gte: ISODate("2026-10-01T00:00:00Z") }
  },
  { _id: 0, customerId: 1, status: 1, createdAt: 1 }
).sort({ createdAt: -1 }).limit(10);
```

Lệnh trên gồm bốn phần khác nhau:

- **Filter:** `customerId` và `status` bằng giá trị cụ thể; `createdAt` thuộc một khoảng thời gian.
- **Projection:** chỉ trả về ba trường chỉ định; `_id: 0` ẩn trường `_id` mặc định.
- **Sort:** sắp xếp theo ngày mới nhất trước.
- **Limit:** lấy tối đa 10 tài liệu.

Bộ lập kế hoạch truy vấn (query planner) có thể đọc theo index, quét collection, lọc thêm trên tài liệu, hoặc kết hợp nhiều công đoạn. Kết quả logic của câu lệnh không đổi vì có thêm index; **chi phí thực thi** có thể thay đổi đáng kể.

### 3.2. Những phép lọc thường gặp

```javascript
// So khớp bằng nhau.
db.orders.find({ status: "PAID" });

// Điều kiện phạm vi.
db.orders.find({
  createdAt: {
    $gte: ISODate("2026-10-01T00:00:00Z"),
    $lt: ISODate("2026-11-01T00:00:00Z")
  }
});

// Một trong nhiều giá trị.
db.orders.find({ status: { $in: ["PAID", "PENDING"] } });

// Kết hợp logic tường minh khi cần.
db.orders.find({
  $or: [{ customerId: "C01" }, { "shipping.city": "Hà Nội" }]
});
```

Điều kiện bằng nhau, khoảng giá trị, toán tử mảng và điều kiện `$or` có thể dẫn đến các chiến lược dùng index khác nhau. Một truy vấn trả về hầu hết collection đôi khi quét trực tiếp lại hợp lý hơn đi qua index rồi đọc nhiều tài liệu.

## 4. Index: cấu trúc tăng tốc cho một số truy vấn

### 4.1. Một index lưu gì?

Có thể hình dung index thông thường như một cấu trúc cây sắp thứ tự **khóa được trích từ các trường BSON**, kèm tham chiếu để tìm tài liệu. Thay vì xem lần lượt mọi đơn hàng, máy chủ có thể tìm các khóa phù hợp rồi lấy tài liệu tương ứng.

```javascript
db.orders.createIndex({ status: 1 });
```

Index trên không chứa toàn bộ nội dung tài liệu; nó tập trung vào trường `status` và vị trí tài liệu. MongoDB mặc định cũng tạo index duy nhất trên `_id` khi tạo collection thông thường.

Index có **chi phí**: tốn dung lượng lưu trữ và thêm công việc khi ghi, cập nhật, xóa tài liệu. Tạo index cho mọi trường không phải chiến lược tốt.

### 4.2. Compound index: thứ tự các trường rất quan trọng

Cho nhu cầu "xem 10 đơn đã thanh toán mới nhất của khách C01":

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1
});

db.orders.find({
  customerId: "C01",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(10);
```

Với các giá trị `customerId` và `status` cố định, các khóa theo `createdAt` trong index đã được sắp theo thứ tự giảm dần. MongoDB **có khả năng** vừa thu hẹp vùng đọc, vừa phục vụ `sort` từ index, tránh một phép sắp xếp riêng. Đây là ví dụ trực quan cho hướng thiết kế theo **Equality → Sort → Range (ESR)**; ESR là hướng dẫn thiết kế, không phải quy tắc luôn tối ưu cho mọi lượng dữ liệu.

Thứ tự các trường được quyết định theo **hình dạng truy vấn thường dùng**, không đơn thuần theo thứ tự xuất hiện trong BSON. Index `{ customerId: 1, status: 1, createdAt: -1 }` cũng có thể giúp các truy vấn dùng tiền tố `customerId`, hoặc `customerId + status`; nhưng không mặc nhiên tối ưu cho truy vấn chỉ lọc `createdAt`.

Lưu ý rằng cùng một index có thể không hỗ trợ sort nếu truy vấn thiếu điều kiện thích hợp ở các trường đứng trước, hoặc nếu bộ so sánh chuỗi (collation) không phù hợp. Máy chủ luôn cân nhắc kế hoạch thực tế.

### 4.3. Index lên trường lồng nhau và mảng

```javascript
db.orders.createIndex({ "shipping.city": 1 });
db.orders.createIndex({ "items.sku": 1 });
```

Đường dẫn `shipping.city` được dùng tương tự trong filter và trong khai báo index. Với `items.sku`, vì `items` là mảng, MongoDB tạo multikey index: một đơn hàng có nhiều `sku` có thể đóng góp nhiều khóa index. Do đó:

- **Một index entry không luôn tương ứng một tài liệu duy nhất**; cơ chế quét phải xử lý trường hợp nhiều khóa cùng trỏ về một tài liệu.
- Chỉ có điều kiện trên mảng chưa đủ để kết luận phép so khớp có cùng phần tử; `$elemMatch` vẫn cần khi nghiệp vụ đòi hỏi như vậy.
- Compound multikey index có ràng buộc riêng, đặc biệt khi một tài liệu chứa nhiều trường mảng được index đồng thời.
- Index trên đường dẫn mảng không tự làm mọi truy vấn hoặc projection liên quan đến mảng trở thành covered query.

### 4.4. Covered query: đôi khi không phải đọc toàn bộ BSON

Nếu tất cả trường cần lọc và trả về đều có trong index, và thỏa các điều kiện để index che phủ truy vấn, máy chủ có thể không cần lấy tài liệu gốc:

```javascript
db.orders.createIndex({ customerId: 1, status: 1 });

db.orders.find(
  { customerId: "C01" },
  { _id: 0, customerId: 1, status: 1 }
);
```

Projection loại `_id` vì mặc định MongoDB thường trả trường này, trong khi index ví dụ không bao gồm `_id`. Có thể kiểm tra với `explain` để biết truy vấn thực tế có được che phủ hay không. Covered query còn phụ thuộc toán tử, kiểu index và dữ liệu (đặc biệt các trường mảng).

### 4.5. Đọc `explain()` thay vì đoán

```javascript
db.orders.find({
  customerId: "C01",
  status: "PAID"
}).sort({ createdAt: -1 })
  .explain("executionStats");
```

Các dấu hiệu hữu ích trong kết quả:

| Thành phần / số liệu | Diễn giải thực hành |
|---|---|
| `COLLSCAN` | Đang quét collection |
| `IXSCAN` | Có quét khóa index |
| `FETCH` | Cần đọc tài liệu từ collection sau khi tìm khóa |
| `SORT` | Có bước sắp xếp trong kế hoạch; cần xem liệu index đã đáp ứng sort hay chưa |
| `totalKeysExamined` | Số khóa index được kiểm tra |
| `totalDocsExamined` | Số tài liệu được kiểm tra |
| `nReturned` | Số kết quả trả về |

Tên stage và cấu trúc chi tiết của `explain` có thể khác theo phiên bản MongoDB và bộ máy thực thi. Không nên kết luận chỉ dựa vào việc thấy `IXSCAN`: một index quét quá nhiều khóa vẫn có thể tốn chi phí. Hãy so sánh dữ liệu thực, bộ lọc, số tài liệu cần đọc và độ trễ đo được.

## 5. Aggregation: truy vấn kết hợp biến đổi dữ liệu

### 5.1. Pipeline là một chuỗi các stage

`aggregate()` nhận một mảng stage. Mỗi stage nhận tài liệu từ stage trước và chuyển tiếp tài liệu đã lọc, biến đổi hoặc tổng hợp:

```text
orders (BSON documents)
  -> $match  (chỉ chọn đơn PAID)
  -> $unwind (mỗi items thành một bản ghi xử lý)
  -> $group  (cộng doanh thu theo category)
  -> $sort   (xếp danh mục theo doanh thu)
  -> kết quả
```

Những stage thường gặp:

| Stage | Vai trò |
|---|---|
| `$match` | Lọc tài liệu theo biểu thức truy vấn MongoDB |
| `$project` / `$set` | Chọn, tính toán hoặc tạo trường |
| `$unwind` | Tách từng phần tử mảng thành luồng tài liệu |
| `$group` | Gom nhóm và tính `$sum`, `$avg`, `$count`... |
| `$sort` | Sắp thứ tự |
| `$limit` / `$skip` | Giới hạn hoặc bỏ qua số lượng kết quả |
| `$lookup` | Kết hợp dữ liệu từ collection khác theo điều kiện phù hợp |

### 5.2. Một pipeline hoàn chỉnh

Yêu cầu: **tính doanh thu theo nhóm sản phẩm cho các đơn đã thanh toán trong tháng 10/2026**. Giá mỗi dòng hàng được lưu dưới dạng Decimal128.

```javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      createdAt: {
        $gte: ISODate("2026-10-01T00:00:00Z"),
        $lt: ISODate("2026-11-01T00:00:00Z")
      }
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.category",
      revenue: {
        $sum: {
          $multiply: ["$items.quantity", "$items.unitPrice"]
        }
      }
    }
  },
  { $sort: { revenue: -1 } }
]);
```

Với ba đơn hàng mẫu, đơn `1003` bị loại vì `PENDING`; kết quả về mặt giá trị:

```javascript
[
  { _id: "BOOK", revenue: NumberDecimal("450000") },
  { _id: "STATIONERY", revenue: NumberDecimal("80000") }
]
```

Giải thích theo từng bước:

1. `$match` chọn đơn `1001` và `1002` dựa trên BSON String `status` và BSON Date `createdAt`.
2. `$unwind` biến hai mảng `items` thành bốn dòng hàng để tính riêng từng sản phẩm.
3. `$group` nhóm theo `items.category`; `$multiply` tính thành tiền dòng hàng, `$sum` cộng thành doanh thu.
4. `$sort` xếp hai nhóm theo trường `revenue` vừa tính.

Điểm quan trọng: `revenue` **không tồn tại trong tài liệu gốc hoặc index thông thường**. Đây là kết quả phát sinh sau `$group`, nên index trên `createdAt` hay `status` không thể trực tiếp sắp xếp theo `revenue` thay cho stage cuối.

### 5.3. Khi nào aggregation dùng được index?

MongoDB có thể tối ưu các stage tùy pipeline. Một `$match` ở đầu pipeline thường có cơ hội dùng index giống như `find()`:

```javascript
db.orders.createIndex({ status: 1, createdAt: -1 });
```

Index này có thể giúp thu hẹp các đơn `PAID` theo khoảng `createdAt` **trước khi** thực hiện `$unwind` và `$group`. Nếu chỉ ít đơn thuộc tháng cần tính, chi phí tổng hợp sẽ thấp hơn đáng kể so với quét và xử lý toàn bộ đơn hàng.

Ngược lại:

- `$group` có thể phải xử lý nhiều tài liệu đầu vào; index không mặc nhiên biến phép cộng thành tra cứu tức thì.
- `$sort` **trước các phép biến đổi** có thể tận dụng thứ tự index khi các điều kiện phù hợp; `$sort` trên trường vừa tính sau `$group` thường cần sắp xếp kết quả trong pipeline.
- `$match` sau một stage thay đổi giá trị trường có thể không được đưa xuống lúc đọc dữ liệu. Trình tối ưu chỉ dịch chuyển những phép lọc khi bảo toàn ngữ nghĩa.
- `$lookup` có thể hưởng lợi từ index ở collection được kết hợp, tùy trường khóa nối và dạng pipeline. Không thể suy ra tốc độ chỉ từ việc đã tạo index ở collection đầu vào.

Kiểm tra kế hoạch thực thi aggregation:

```javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      status: "PAID",
      createdAt: { $gte: ISODate("2026-10-01T00:00:00Z") }
    }
  },
  { $group: { _id: "$customerId", orderCount: { $sum: 1 } } }
]);
```

Thông tin về bộ quét index có thể xuất hiện trong phần `queryPlanner`, `executionStats` hoặc cấu trúc stage phụ thuộc phiên bản/engine. Mục tiêu là xác định **có đọc hiệu quả tập tài liệu đầu vào không**, rồi xem các stage xử lý bao nhiêu dữ liệu.

## 6. Ghép bốn khái niệm khi thiết kế chức năng

Xét ba yêu cầu khác nhau trên cùng collection:

| Yêu cầu | BSON liên quan | Query / aggregation | Hướng index |
|---|---|---|---|
| Liệt kê đơn PAID mới nhất của khách C01 | `customerId`, `status` là String; `createdAt` là Date | `find` + filter + `sort` + `limit` | Compound index `{ customerId: 1, status: 1, createdAt: -1 }` |
| Đếm đơn PAID theo khách hàng | String và Date nếu lọc kỳ | `$match` → `$group` | Index cho điều kiện `$match`; không hứa rằng toàn bộ `$group` được index xử lý |
| Tính doanh thu từng nhóm sản phẩm | `items` là mảng; `unitPrice` là Decimal128 | `$match` → `$unwind` → `$group` → `$sort` | Index để lọc đơn ban đầu; tổng hợp doanh thu là công việc tiếp theo |

### 6.1. Một truy vấn nhanh không có nghĩa một pipeline nhanh

Giả sử một index giúp `$match` tìm được 100.000 đơn khá nhanh. Nếu mỗi đơn có 20 dòng `items`, `$unwind` có thể tạo luồng tới khoảng 2.000.000 dòng để tính toán. Như vậy cần phân biệt:

- **Hiệu quả đọc tài liệu**: index có giảm lượng tài liệu phải xét không?
- **Số lượng tài liệu trung gian**: `$unwind` có khuếch đại dữ liệu không?
- **Chi phí nhóm và sắp xếp**: có quá nhiều nhóm, trường tính toán hoặc dữ liệu phải giữ trong bộ nhớ không?
- **Độ chính xác kiểu số**: phép cộng/nhân đang dùng Decimal128 hay một kiểu số không phù hợp?

Đây là các câu hỏi khác nhau, cần đo ở các tầng khác nhau.

### 6.2. Thiết kế schema từ cách đọc và xử lý dữ liệu

MongoDB linh hoạt về cấu trúc tài liệu nhưng không có nghĩa nên để một trường thay đổi kiểu tùy tiện. Ví dụ:

```javascript
// Tránh dữ liệu không nhất quán:
{ createdAt: "2026-10-01", unitPrice: "150000" }
{ createdAt: ISODate("2026-10-01T00:00:00Z"),
  unitPrice: NumberDecimal("150000") }
```

Hai tài liệu trên có thể trông giống nhau trên màn hình, nhưng điều kiện lọc ngày và phép tính doanh thu sẽ khác. Một thiết kế tốt thường:

1. Chọn kiểu BSON nhất quán cho từng trường nghiệp vụ.
2. Đặt cấu trúc mảng và tài liệu lồng nhau theo những truy vấn thật sự sẽ sử dụng.
3. Viết một vài query/pipeline điển hình trước khi quyết định index.
4. Xem `explain()` và lượng dữ liệu thật để xác nhận lựa chọn.
5. Cân nhắc chi phí ghi và lưu trữ trước khi bổ sung index.

### 6.3. Những ngộ nhận dễ gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| BSON chỉ là JSON đổi sang nhị phân | BSON có các kiểu dữ liệu riêng; kiểu ảnh hưởng phép so khớp và tính toán |
| Có index trên một trường thì mọi lệnh dùng trường đó đều nhanh | Phụ thuộc toán tử, thứ tự index, độ chọn lọc, sort, projection và kế hoạch thực thi |
| Các trường trong compound index đổi thứ tự tùy ý | Thứ tự khóa ảnh hưởng tiền tố, quét phạm vi và khả năng đáp ứng sort |
| Pipeline nào cũng tận dụng index xuyên suốt | Index thường hữu ích ở khâu lọc/đọc; `$unwind`, `$group` và trường tính toán có chi phí riêng |
| `$match` luôn phải được viết ở đầu tiên bất kể nội dung | Đặt điều kiện có thể lọc sớm thường tốt, nhưng điều kiện phụ thuộc trường vừa tính phải đứng sau stage tạo trường |
| `"42"` và `42` là cùng dữ liệu | Một giá trị là String, một giá trị là số; không nên trộn kiểu |
| Điều kiện trên hai đường dẫn của cùng mảng tự tìm cùng phần tử | Cần `$elemMatch` khi bắt buộc nhiều điều kiện áp dụng trên cùng phần tử |

## 7. Thực hành tự kiểm chứng

Sau khi tạo collection `orders` như đầu bài, có thể thực hiện ba thử nghiệm:

**Thử nghiệm A – Có và không có compound index.** Chạy `explain("executionStats")` cho truy vấn lọc `customerId`, `status` rồi sort `createdAt`. Tạo index compound tương ứng, chạy lại để quan sát kế hoạch. Với chỉ ba tài liệu mẫu, MongoDB có thể chọn quét collection vì dữ liệu quá nhỏ; đừng dùng thời gian của bộ dữ liệu nhỏ để kết luận index vô ích.

**Thử nghiệm B – Đổi vị trí stage.** So sánh pipeline lọc `status: "PAID"` trước `$unwind` với pipeline chỉ có thể lọc một điều kiện trên dòng `items` sau `$unwind`. Tự xác định stage nào giảm số đơn, stage nào tăng số dòng trung gian, và vì sao không được chuyển bừa điều kiện liên quan đến dòng hàng.

**Thử nghiệm C – Đổi kiểu dữ liệu.** Trong một collection thử nghiệm riêng, lưu cùng ngày dưới dạng String và Date; so sánh truy vấn bằng `ISODate`. Sau đó so sánh phép tính tiền trên Decimal128 với dữ liệu giá lưu dưới dạng chuỗi. Mục tiêu là hiểu rằng một pipeline đúng về cú pháp vẫn phụ thuộc vào schema BSON để cho kết quả đúng.

### Câu hỏi ôn tập

1. Tại sao index trên `createdAt` không thể sửa được lỗi dữ liệu ngày lúc lưu String, lúc lưu Date?
2. Vì sao index `{ customerId: 1, status: 1, createdAt: -1 }` phù hợp với truy vấn liệt kê đơn gần nhất của một khách hơn index chỉ có `status`?
3. Nếu `$match` chỉ chọn 100 đơn nhưng `$unwind` tạo 5.000 dòng, nên tối ưu thêm ở bước nào?
4. Vì sao `$sort` theo doanh thu vừa tính sau `$group` thường không hưởng lợi từ index trên collection gốc?
5. Khi cần kiểm tra hai thuộc tính thuộc cùng một phần tử `items`, vì sao nên dùng `$elemMatch`?

**Ghi nhớ:** *BSON xác định bản chất dữ liệu; query mô tả tập cần lấy; index hỗ trợ cách truy cập; aggregation xử lý và biến đổi tập dữ liệu đã được đọc.* Muốn MongoDB vừa **đúng kết quả** vừa **hiệu quả**, cần nhìn cả bốn trong cùng một luồng.
