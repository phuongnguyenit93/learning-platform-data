# Projection: chọn trường, loại trường và xử lý _id

Trong MongoDB, một document có thể chứa nhiều trường thông tin: mã định danh, tên, giá, tồn kho, mô tả, ảnh, lịch sử thay đổi và các object lồng nhau. Tuy nhiên, mỗi màn hình hoặc API thường chỉ cần một phần dữ liệu. **Projection** cho phép chọn những trường nào xuất hiện trong kết quả truy vấn, tránh trả toàn bộ document khi client chỉ cần vài thuộc tính.

Ví dụ một sản phẩm:

```javascript
{
  _id: "P001",
  sku: "KB-001",
  name: "Bàn phím cơ",
  category: "keyboard",
  price: NumberDecimal("1250000.00"),
  stock: 28,
  description: "Bàn phím cơ dùng trong văn phòng và lập trình.",
  specifications: {
    switch: "brown",
    layout: "75%",
    wireless: true
  },
  tags: ["mechanical", "wireless", "compact"],
  supplier: { company: "ABC Supplies", phone: "0123456789" },
  createdAt: ISODate("2026-01-05T08:00:00Z")
}
```

API danh sách sản phẩm chỉ cần tên và giá:

```javascript
db.products.find(
  { category: "keyboard" },
  { name: 1, price: 1, _id: 0 }
);
```

Kết quả chỉ chứa `name` và `price`. **Filter** `{ category: "keyboard" }` quyết định document nào được lấy; **projection** quyết định những trường nào được trả về.

## 1. Cú pháp projection trong truy vấn

Trong `mongosh`:

```javascript
db.collection.find(query, projection);
db.collection.findOne(query, projection);
```

Trong đó:

- `query`: bộ lọc để chọn document; ví dụ `{ status: "ACTIVE" }`, hoặc `{}` để chọn tất cả.
- `projection`: object mô tả các field được đưa vào hoặc loại khỏi kết quả.
- Giá trị `1` (hoặc `true`) thường mang nghĩa **include**.
- Giá trị `0` (hoặc `false`) thường mang nghĩa **exclude**.
- Trường `_id` được **bao gồm mặc định**, ngay cả khi projection chỉ chọn vài trường khác.

Ví dụ:

```javascript
// Không có projection: toàn bộ trường.
db.products.find({ category: "keyboard" });

// Có projection: name, price và _id mặc định.
db.products.find(
  { category: "keyboard" },
  { name: 1, price: 1 }
);

// Loại _id, chỉ giữ name và price.
db.products.find(
  { category: "keyboard" },
  { name: 1, price: 1, _id: 0 }
);
```

Projection có thể được kết hợp với filter, sort và limit:

```javascript
db.products.find(
  { category: "keyboard", stock: { $gt: 0 } },
  { _id: 0, sku: 1, name: 1, price: 1 }
).sort({ price: 1 }).limit(20);
```

Ý nghĩa: lọc bàn phím còn hàng, chỉ trả mã/tên/giá, sắp theo giá tăng dần và giới hạn 20 document. Trường `stock` có trong filter nhưng **không bắt buộc xuất hiện trong kết quả**.

## 2. Inclusion projection: chọn những trường cần dùng

Khi các trường được khai báo với `1`, MongoDB chỉ trả những trường đó, cộng với `_id` nếu không loại nó:

```javascript
db.products.find(
  { category: "keyboard" },
  { name: 1, price: 1 }
);
```

Một kết quả:

```javascript
{
  _id: "P001",
  name: "Bàn phím cơ",
  price: NumberDecimal("1250000.00")
}
```

Các trường như `description`, `specifications` và `supplier` không xuất hiện. MongoDB vẫn giữ nguyên document gốc trong collection.

### 2.1. Chỉ lấy một trường

```javascript
db.products.find({}, { name: 1, _id: 0 });
```

Kết quả minh họa:

```javascript
{ name: "Bàn phím cơ" }
{ name: "Chuột không dây" }
{ name: "Màn hình" }
```

Projection vẫn trả **một document kết quả cho mỗi document khớp bộ lọc**. Nếu mục tiêu là lấy các giá trị **khác nhau** của một trường, có thể dùng `distinct("category")` hoặc aggregation thay vì cho rằng projection tự loại giá trị trùng.

### 2.2. Chỉ lấy _id

```javascript
db.products.find(
  { stock: { $gt: 0 } },
  { _id: 1 }
);
```

Kết quả chỉ có `_id`. Dù filter dùng `stock`, nó không nhất thiết được trả về.

### 2.3. Trường không tồn tại

```javascript
db.projectionLab.insertMany([
  { _id: "A", name: "Sản phẩm A", color: "đen" },
  { _id: "B", name: "Sản phẩm B" }
]);

db.projectionLab.find(
  {},
  { _id: 1, name: 1, color: 1 }
).sort({ _id: 1 });
```

Dữ liệu trả về:

```javascript
{ _id: "A", name: "Sản phẩm A", color: "đen" }
{ _id: "B", name: "Sản phẩm B" }
```

MongoDB không tự tạo `color: null` cho document B chỉ vì projection yêu cầu trường đó. **Missing field** và **field có giá trị null** là hai tình huống dữ liệu khác nhau. Nếu API yêu cầu field luôn tồn tại, hãy chuẩn hóa schema hoặc gán giá trị mặc định trong ứng dụng/aggregation.

## 3. Exclusion projection: loại những trường không muốn trả

Khi dùng `0`, MongoDB loại các trường chỉ định và trả mọi trường khác:

```javascript
db.products.find(
  { category: "keyboard" },
  { description: 0, supplier: 0 }
);
```

Kết quả vẫn có `_id`, `sku`, `name`, `price`, `stock`, `tags` và các trường còn lại.

### 3.1. Loại riêng _id

```javascript
db.products.find({}, { _id: 0 });
```

Câu lệnh này trả **mọi trường trừ _id**, khác với:

```javascript
db.products.find({}, { _id: 1 });
```

Câu lệnh sau chỉ trả `_id`.

### 3.2. Trường hợp nên thận trọng với exclusion

Giả sử:

```javascript
db.users.find(
  { status: "ACTIVE" },
  { passwordHash: 0, recoveryCodes: 0 }
);
```

Nếu schema sau đó thêm `apiSecret`, projection loại hai trường cũ có thể **vô tình trả** trường mới. API công khai thường nên dùng inclusion (allowlist field) và DTO để nêu rõ các trường được phép hiển thị. Projection chỉ kiểm soát **hình dạng kết quả truy vấn hiện tại**; nó không thay thế quyền truy cập database, quy tắc bảo mật hoặc kiểm tra thông tin tại tầng ứng dụng.

## 4. Không được trộn inclusion với exclusion, ngoại trừ _id

Một quy tắc quan trọng của projection thông thường trong `find()`:

> Không kết hợp trường được include bằng `1` với trường khác bị exclude bằng `0`, **ngoại trừ trường đặc biệt _id**.

Ví dụ không hợp lệ:

```javascript
db.products.find(
  {},
  { name: 1, price: 1, description: 0 }
);
```

Ví dụ hợp lệ:

```javascript
// Inclusion: _id được trả mặc định.
db.products.find({}, { name: 1, price: 1 });

// Inclusion và ngoại lệ _id.
db.products.find({}, { name: 1, price: 1, _id: 0 });

// Exclusion các field không cần thiết.
db.products.find({}, { description: 0, supplier: 0 });

// Exclusion cả _id.
db.products.find({}, { description: 0, _id: 0 });

// Chỉ trả _id.
db.products.find({}, { _id: 1 });
```

| Projection | Ý nghĩa |
|---|---|
| `{}` | Trả toàn bộ trường như mặc định |
| `{ name: 1 }` | Chỉ `name` và `_id` |
| `{ name: 1, _id: 0 }` | Chỉ `name` |
| `{ price: 0 }` | Mọi trường trừ `price` |
| `{ price: 0, _id: 0 }` | Mọi trường trừ `price` và `_id` |
| `{ _id: 0 }` | Mọi trường trừ `_id` |
| `{ _id: 1 }` | Chỉ `_id` |
| `{ name: 1, price: 0 }` | Lỗi trộn inclusion/exclusion |

Các projection operator chuyên biệt và biểu thức projection trong những phiên bản hỗ trợ có quy tắc riêng. Điều này **không** cho phép tùy ý trộn `1` và `0` cho các trường thông thường.

## 5. Projection trường lồng nhau bằng dot notation

MongoDB cho phép chọn các field trong **embedded document**:

```javascript
{
  _id: "P001",
  name: "Bàn phím cơ",
  specifications: {
    layout: "75%",
    switch: "brown",
    wireless: true,
    connection: {
      bluetooth: true,
      usbC: true
    }
  }
}
```

Chỉ lấy tên, layout và trạng thái Bluetooth:

```javascript
db.products.find(
  { _id: "P001" },
  {
    _id: 0,
    name: 1,
    "specifications.layout": 1,
    "specifications.connection.bluetooth": 1
  }
);
```

Hình dạng kết quả:

```javascript
{
  name: "Bàn phím cơ",
  specifications: {
    layout: "75%",
    connection: {
      bluetooth: true
    }
  }
}
```

Tên có dấu chấm trong projection chỉ **đường dẫn**, không buộc kết quả trở thành key chứa dấu chấm. Object được biểu diễn dưới cấu trúc lồng nhau.

### 5.1. Loại một trường con

```javascript
db.products.find(
  { _id: "P001" },
  { "specifications.connection.usbC": 0 }
);
```

Kết quả giữ các trường khác nhưng loại đường dẫn `usbC`. Khi field không có trong một document, không có gì để trả/loại ở đường dẫn tương ứng.

### 5.2. Tránh path collision

Không nên chọn đồng thời toàn bộ parent và một child bằng những đường dẫn giao nhau:

```javascript
// Dễ gây path collision.
db.products.find(
  {},
  { specifications: 1, "specifications.layout": 1 }
);
```

Hãy chọn `specifications: 1` nếu cần toàn bộ object, hoặc chỉ chọn `"specifications.layout": 1` nếu muốn phần nhỏ. Thay đổi thứ tự khai báo key không phải cách hợp lệ để xử lý path collision.

### 5.3. Projection không cập nhật dữ liệu gốc

```javascript
db.products.findOne(
  { _id: "P001" },
  { "specifications.layout": 1, _id: 0 }
);
```

Lệnh này chỉ chọn trường trong **kết quả đọc**. Trường `switch` hoặc `wireless` vẫn tồn tại trong collection. Muốn xóa trường thật phải sử dụng thao tác update phù hợp như `$unset`.

## 6. Projection và array

Giả sử một đơn hàng:

```javascript
{
  _id: "ORD-1001",
  customerId: "C001",
  status: "PAID",
  items: [
    { sku: "BK-01", quantity: 2, price: 50000 },
    { sku: "PN-02", quantity: 1, price: 25000 },
    { sku: "KB-03", quantity: 1, price: 450000 }
  ],
  history: [
    { status: "CREATED", at: ISODate("2026-03-01T10:00:00Z") },
    { status: "PAID", at: ISODate("2026-03-01T10:05:00Z") },
    { status: "SHIPPED", at: ISODate("2026-03-02T08:00:00Z") }
  ]
}
```

Chọn `items: 1` sẽ trả **toàn bộ mảng**, không tự giới hạn số phần tử:

```javascript
db.orders.find(
  { _id: "ORD-1001" },
  { _id: 0, items: 1 }
);
```

### 6.1. Chọn field trong từng phần tử mảng

```javascript
db.orders.find(
  { _id: "ORD-1001" },
  { _id: 0, "items.sku": 1, "items.quantity": 1 }
);
```

Kết quả:

```javascript
{
  items: [
    { sku: "BK-01", quantity: 2 },
    { sku: "PN-02", quantity: 1 },
    { sku: "KB-03", quantity: 1 }
  ]
}
```

Dot notation chỉ chọn các field cần trả ở mỗi phần tử. Nó **không lọc bỏ** phần tử array theo giá hoặc mã sản phẩm.

### 6.2. Cắt array bằng $slice

Projection operator `$slice` giúp giới hạn số phần tử array **được trả về**:

```javascript
// Hai phần tử đầu của history.
db.orders.find(
  { _id: "ORD-1001" },
  { history: { $slice: 2 }, _id: 0 }
);

// Hai phần tử cuối.
db.orders.find(
  { _id: "ORD-1001" },
  { history: { $slice: -2 }, _id: 0 }
);

// Bỏ qua 1 phần tử, lấy 2 phần tử tiếp theo.
db.orders.find(
  { _id: "ORD-1001" },
  { history: { $slice: [1, 2] }, _id: 0 }
);
```

`$slice` trong projection đọc khác với modifier `$slice` kết hợp `$push` trong thao tác ghi. Lệnh đọc chỉ giảm số phần tử hiển thị, **không tự cắt mảng đang lưu trong database**. Nếu mảng lớn dần không giới hạn, cần thay mô hình lưu dữ liệu (như collection con riêng) thay vì chỉ thêm `$slice` khi đọc.

`$slice` cũng không tự sắp xếp array: “hai phần tử cuối” phụ thuộc thứ tự vốn có của array.

### 6.3. $elemMatch projection: lấy phần tử đầu tiên khớp điều kiện

```javascript
db.orders.find(
  { _id: "ORD-1001" },
  {
    _id: 0,
    items: { $elemMatch: { sku: "PN-02" } }
  }
);
```

Kết quả:

```javascript
{
  items: [
    { sku: "PN-02", quantity: 1, price: 25000 }
  ]
}
```

Ở ngữ cảnh **projection**, `$elemMatch` trả tối đa **một phần tử đầu tiên khớp** trong array. Phân biệt với `$elemMatch` trong query filter:

```javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "PN-02",
      quantity: { $gte: 1 }
    }
  }
});
```

Filter chọn document có ít nhất một item thỏa nhiều điều kiện trên cùng phần tử. Projection chọn phần tử được trả về. Nếu muốn **mọi item** thỏa điều kiện, dùng aggregation `$filter`.

### 6.4. Positional projection $

Khi query khớp một phần tử array, một số trường hợp cho phép dùng positional projection để trả **phần tử khớp đầu tiên**:

```javascript
db.orders.find(
  { "items.sku": "PN-02" },
  { "items.$": 1, _id: 0 }
);
```

Toán tử này có những giới hạn về array trong query và projection; khi query phức tạp hoặc có nhiều array, nên xem quy tắc phiên bản đang sử dụng. Đừng nhầm positional projection trong lệnh đọc với positional update operator dùng để sửa dữ liệu.

## 7. Projection trong aggregation: $project và phép biến đổi

Stage `$project` trong aggregation cho phép chọn field và **tính toán field mới**:

```javascript
db.products.aggregate([
  { $match: { category: "keyboard" } },
  {
    $project: {
      _id: 0,
      sku: 1,
      name: 1,
      price: 1,
      displayName: {
        $concat: ["$sku", " - ", "$name"]
      }
    }
  }
]);
```

Ngoài `sku`, `name` và `price`, kết quả có `displayName` là giá trị được dựng từ hai field. Nó **không tự lưu** vào collection.

Ví dụ tổng tiền từng dòng hàng:

```javascript
db.orderLines.aggregate([
  {
    $project: {
      _id: 0,
      orderId: 1,
      sku: 1,
      quantity: 1,
      unitPrice: 1,
      lineTotal: {
        $multiply: ["$quantity", "$unitPrice"]
      }
    }
  }
]);
```

### 7.1. Lọc mọi phần tử array bằng $filter

```javascript
db.orders.aggregate([
  { $match: { _id: "ORD-1001" } },
  {
    $project: {
      _id: 0,
      customerId: 1,
      expensiveItems: {
        $filter: {
          input: "$items",
          as: "item",
          cond: { $gte: ["$$item.price", 50000] }
        }
      }
    }
  }
]);
```

`$filter` giữ **mọi phần tử** thỏa biểu thức, khác `$elemMatch` projection trả tối đa một phần tử. Đối với array không tồn tại hoặc `null`, cần xem quy tắc xử lý của `$filter` và có thể dùng `$ifNull` nếu ứng dụng yêu cầu array rỗng.

### 7.2. Giá trị 0 và 1 là ký hiệu projection, không phải literal

Trong `$project`, `0` thường có nghĩa exclude và `1` có nghĩa include. Muốn **tạo giá trị số 0**, dùng `$literal`:

```javascript
db.orderLines.aggregate([
  {
    $project: {
      _id: 0,
      sku: 1,
      initialDiscount: { $literal: 0 }
    }
  }
]);
```

Nếu viết `initialDiscount: 0`, MongoDB hiểu là loại trường, không tạo số `0`. Stage `$project` thông thường cũng không cho trộn tùy ý inclusion/exclusion ngoài `_id`; các computed field được phép dùng cùng inclusion theo quy tắc riêng.

### 7.3. Loại trường bằng $unset trong aggregation

```javascript
db.products.aggregate([
  { $unset: ["description", "supplier"] }
]);
```

Đây là stage xử lý **dòng kết quả của pipeline**, không phải lệnh update xóa trường khỏi document. Có thể dùng `$project` exclusion tương ứng nếu phù hợp:

```javascript
db.products.aggregate([
  {
    $project: {
      description: 0,
      supplier: 0,
      _id: 0
    }
  }
]);
```

Một số phiên bản MongoDB còn hỗ trợ biểu thức aggregation trong projection của `find()`. Nhưng khi cần nhiều phép tính, lọc mảng phức tạp và đổi cấu trúc kết quả, aggregation thường thể hiện ý định rõ hơn.

## 8. Projection và hiệu năng: tiết kiệm phần nào?

Projection thường đem lại các lợi ích sau:

- **Truyền ít byte hơn qua mạng** vì document kết quả có ít field.
- **Giảm công việc xử lý phía client** khi không phải decode/deserialise nhiều trường không dùng.
- **Có thể tạo covered query** khi filter và trường projection đều được phục vụ bằng index thích hợp.

Tuy nhiên, projection **không bảo đảm giảm số document được đọc từ storage engine**. Nếu query plan có bước `FETCH`, MongoDB vẫn cần truy xuất document để lấy trường ngoài index. Một response nhỏ không đồng nghĩa I/O đĩa nhỏ tương ứng.

### 8.1. Covered query: chỉ cần index

Tạo index:

```javascript
db.products.createIndex({
  category: 1,
  name: 1
});
```

Query:

```javascript
db.products.find(
  { category: "keyboard" },
  { name: 1, _id: 0 }
);
```

Có thể được phục vụ bằng index bởi:

1. `category` là trường filter.
2. `name` là trường trả về.
3. `_id` được loại rõ ràng nên không cần lấy ID từ document.
4. Index chứa các giá trị cần thiết cho filter/projection.

Nếu không loại `_id`:

```javascript
db.products.find(
  { category: "keyboard" },
  { name: 1 }
);
```

MongoDB mặc định trả thêm `_id`. Secondary index `{ category: 1, name: 1 }` không mặc nhiên chứa `_id` của document dưới dạng một key query có thể trả, vì vậy query có thể phải `FETCH`, trừ khi có kế hoạch/index khác phù hợp.

Đây là ví dụ cho thấy **xử lý _id ảnh hưởng cả response và khả năng cover bởi index**.

### 8.2. Quan sát bằng explain

```javascript
db.products.find(
  { category: "keyboard" },
  { name: 1, _id: 0 }
).explain("executionStats");
```

Các chỉ số quan trọng:

| Thành phần | Ý nghĩa |
|---|---|
| `winningPlan` | Query planner chọn kế hoạch nào |
| `IXSCAN` | Đang duyệt index |
| `FETCH` | Cần đọc document ngoài index |
| `COLLSCAN` | Quét collection thay vì chỉ dựa trên index |
| `totalKeysExamined` | Số khóa index đã xem xét |
| `totalDocsExamined` | Số document đã xem xét |
| `nReturned` | Số document trả về |
| `executionTimeMillis` | Thời gian ghi nhận trong kết quả explain |

Với covered query phù hợp, `totalDocsExamined` thường bằng `0`. Nhưng chỉ nhìn thấy `IXSCAN` **không đủ**: query plan có thể vừa `IXSCAN` vừa `FETCH`. Tên stage và định dạng kết quả có thể khác theo query engine/phiên bản.

### 8.3. Index theo cả filter, sort và projection

Ví dụ endpoint:

```javascript
db.products.find(
  { category: "keyboard", stock: { $gt: 0 } },
  { sku: 1, name: 1, price: 1, _id: 0 }
).sort({ price: 1 }).limit(20);
```

Index cần đánh giá theo cả filter `category`/`stock`, sort `price` và field trả về. Một index chứa rất nhiều field có thể giúp một số query, nhưng cũng làm tăng dung lượng và chi phí insert/update. Không nên tạo index chỉ từ danh sách cột hiển thị.

Multikey index có hạn chế khi cover field array; collation không tương thích hoặc biểu thức projection phức tạp cũng có thể khiến kế hoạch phải đọc document. Phải đo với dữ liệu và workload thực tế.

## 9. Projection khác filter, sort, limit và update

| Mục đích | MongoDB dùng gì? |
|---|---|
| Chọn **document nào** | Filter trong `find(query, ...)` |
| Chọn **field nào** | Projection trong `find(..., projection)` |
| Sắp thứ tự document | `sort()` |
| Giới hạn số document | `limit()` |
| Bỏ qua một số document | `skip()` hoặc keyset pagination |
| Lọc một phần array để trả | `$elemMatch`, `$slice` projection hoặc aggregation `$filter` |
| Thay đổi field đã lưu | Update, ví dụ `$set`, `$unset` |
| Giới hạn array đang lưu khi ghi | `$push` + `$slice` modifier |

Ví dụ:

```javascript
db.orders.find(
  { status: "PAID" },
  { customerId: 1, status: 1, createdAt: 1, _id: 0 }
).sort({ createdAt: -1 }).limit(20);
```

Bốn công việc độc lập: lọc order đã thanh toán; chọn field; sắp theo thời gian; lấy tối đa 20 record. Projection **không** tự sắp kết quả và không đảm bảo `find()` trả theo thứ tự field hoặc theo thứ tự chèn.

Nếu cần phân trang ổn định, nên sort theo các khóa đủ phân biệt (ví dụ thêm `_id` làm tie-breaker) và lưu các khóa cần thiết trong cursor token hoặc response.

## 10. Projection trong Java và Spring Data MongoDB

Khi ứng dụng Java truy vấn MongoDB, có thể dùng API projection của driver hoặc Spring Data MongoDB.

### 10.1. MongoDB Java Sync Driver

Ví dụ:

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Projections.fields;
import static com.mongodb.client.model.Projections.include;
import static com.mongodb.client.model.Projections.excludeId;

MongoCollection<Document> products =
    database.getCollection("products");

for (Document product : products
        .find(eq("category", "keyboard"))
        .projection(fields(include("name", "price"), excludeId()))) {
    System.out.println(product.toJson());
}
```

`include("name", "price")` chọn hai field, còn `excludeId()` bỏ `_id`. Nếu không gọi `excludeId()`, MongoDB mặc định trả `_id` cùng các trường được include.

### 10.2. Spring Data MongoDB với MongoTemplate

```java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = new Query(
    Criteria.where("category").is("keyboard")
);

query.fields()
     .include("name")
     .include("price")
     .exclude("_id");

List<Product> products =
    mongoTemplate.find(query, Product.class);
```

Ở kết quả chỉ tải một phần field, entity Java có thể chứa giá trị `null`/mặc định cho những trường chưa được trả, tùy kiểu field và cách mapping. Vì vậy, dùng partial entity này để **replace/save lại cả document** có thể nguy hiểm nếu mã nguồn không phân biệt field chưa tải với field có giá trị null.

Đối với API chỉ đọc vài thuộc tính, có thể dùng DTO hoặc repository projection riêng:

```java
public record ProductCard(String name, java.math.BigDecimal price) {}
```

Spring Data MongoDB có nhiều cách projection repository và mapping; cách khai báo cụ thể phụ thuộc phiên bản/thư viện, nhưng mục tiêu vẫn là tách **read model** khỏi entity dùng để ghi khi chỉ tải một phần dữ liệu.

### 10.3. Phân biệt _id trong MongoDB với id trong Java

Tên field của MongoDB là `_id`. Entity Java thường dùng thuộc tính `id` (có thể có annotation `@Id`) để ánh xạ sang `_id`. Dù tên thuộc tính ở Java là `id`, nguyên tắc projection bên MongoDB vẫn như cũ: `_id` xuất hiện mặc định khi include những field khác, và phải bỏ rõ ràng nếu không muốn trả về.

## 11. Thiết kế projection cho các endpoint thực tế

Giả sử một hệ thống thương mại điện tử có ba màn hình:

### 11.1. Danh sách sản phẩm

Danh sách cần tên, giá, ảnh nhỏ và ID để mở trang chi tiết:

```javascript
db.products.find(
  { status: "PUBLISHED" },
  { _id: 1, name: 1, price: 1, thumbnailUrl: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(20);
```

`createdAt` được dùng trong sort nhưng không bắt buộc xuất hiện trong response; tuy nhiên nếu API dùng cursor pagination, có thể cần cung cấp khóa sort đó trong token phân trang.

### 11.2. Trang chi tiết sản phẩm

```javascript
db.products.findOne(
  { _id: productId, status: "PUBLISHED" },
  {
    _id: 1,
    name: 1,
    price: 1,
    description: 1,
    specifications: 1,
    images: 1
  }
);
```

Không cần trả thông tin nhà cung cấp nội bộ hay các field chỉ dành cho vận hành.

### 11.3. Trang quản lý tồn kho

```javascript
db.products.find(
  {},
  {
    _id: 0,
    sku: 1,
    name: 1,
    price: 1,
    stock: 1,
    updatedAt: 1
  }
).sort({ sku: 1 }).limit(50);
```

Cùng một collection có thể phục vụ nhiều API với projection khác nhau. Mỗi endpoint cần thiết kế filter/sort/index phù hợp với đặc điểm truy cập, không dùng một projection chung chứa tất cả field cho mọi màn hình.

## 12. Những hiểu lầm cần tránh

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| `{ name: 1 }` chỉ trả name | Vẫn có `_id` theo mặc định |
| `{ _id: 0 }` không trả field nào | Trả mọi field khác ngoài `_id` |
| Có thể trộn `name: 1` và `price: 0` | Projection thông thường không cho phép ngoài ngoại lệ `_id` |
| Projection loại field khỏi database | Chỉ tác động lên kết quả đọc, không cập nhật dữ liệu |
| Chọn `items: 1` là chỉ lấy một item | Trả toàn bộ array `items` |
| `$elemMatch` trả tất cả phần tử khớp | Projection operator này trả tối đa một phần tử đầu tiên khớp |
| `$slice` projection giúp document trong DB nhỏ | Chỉ cắt mảng trả về, không thay đổi bản gốc |
| Projection luôn giảm I/O trên đĩa | Query có thể vẫn phải `FETCH` document |
| Index có `IXSCAN` chắc chắn covered | Có thể còn stage `FETCH` |
| Exclusion field bí mật là đủ bảo mật API | Cần quyền truy cập, allowlist và kiểm soát response |
| Partial Java entity có thể save như full entity | Field chưa tải có thể bị mất/ghi sai |
| Chọn field trong projection là quyết định thứ tự sort | Sort có cơ chế độc lập qua `sort()` |

## 13. Bài tập thực hành

### Bài 1 — Inclusion, exclusion và _id

Tạo dữ liệu:

```javascript
db.employees.insertMany([
  {
    _id: "E01",
    name: "An",
    department: "Engineering",
    salary: 25000000,
    email: "an@example.com",
    address: { city: "Hà Nội", street: "Phố A" }
  },
  {
    _id: "E02",
    name: "Bình",
    department: "Sales",
    salary: 18000000,
    email: "binh@example.com"
  }
]);
```

Hãy viết truy vấn:
1. Chỉ trả `name` và `department`, không trả `_id`.
2. Trả mọi trường trừ `salary` và `email`.
3. Chỉ trả `_id` của người thuộc Engineering.
4. Chỉ trả `name` và `address.city`, quan sát khác biệt khi document không có `address`.

### Bài 2 — Tìm lỗi projection

Đánh giá:

```javascript
db.employees.find({}, { name: 1, salary: 0 });
db.employees.find({}, { name: 1, _id: 0 });
db.employees.find({}, { _id: 0 });
db.employees.find({}, { address: 1, "address.city": 1 });
```

Câu nào hợp lệ? Câu nào lỗi do trộn chế độ hay path collision? So sánh `{ _id: 0 }` với `{ _id: 1 }`.

### Bài 3 — Array projection

Dùng document `orders` từ phần 6:
1. Chỉ lấy `items.sku` và `items.quantity`.
2. Trả hai phần tử cuối của `history`.
3. Dùng `$elemMatch` projection lấy một item `sku: "PN-02"`.
4. Dùng aggregation `$filter` lấy toàn bộ item có `price >= 50000`.
5. Giải thích vì sao `$slice` ở lệnh đọc không giảm kích thước BSON lưu trong collection.

### Bài 4 — Covered query

Tạo index `{ category: 1, name: 1 }` rồi so sánh:

```javascript
db.products.find(
  { category: "keyboard" },
  { name: 1 }
).explain("executionStats");

db.products.find(
  { category: "keyboard" },
  { name: 1, _id: 0 }
).explain("executionStats");
```

Dự đoán ảnh hưởng của `_id` mặc định. Quan sát `totalDocsExamined` và có hay không stage `FETCH`. Nếu planner chọn cách khác trên collection nhỏ, phân tích theo thống kê thực tế.

### Bài 5 — Projection cho public API

Một collection `users` có `_id`, `displayName`, `avatarUrl`, `email`, `passwordHash`, `recoveryCodes`, `role`. Thiết kế projection cho public profile và admin profile. Giải thích tại sao exclusion kiểu `{ passwordHash: 0, recoveryCodes: 0 }` có thể vô tình lộ field nhạy cảm mới và nên bổ sung cơ chế kiểm soát nào tại API.

## Kết luận

**Projection** chọn các trường của **kết quả truy vấn**, không thay đổi document đã lưu. Với `find()` hoặc `findOne()`, dùng `1` để **include**, `0` để **exclude**, không trộn hai kiểu đối với các field thông thường, ngoại trừ `_id`. **_id mặc định vẫn được trả** khi inclusion projection được dùng, nên cần `_id: 0` nếu response không cần ID.

Dot notation cho phép chọn trường lồng nhau; `$slice`, `$elemMatch` và positional projection giải quyết các nhu cầu khác nhau khi trả array; `$project` và `$filter` trong aggregation phù hợp với biến đổi phức tạp. Projection giảm payload về client và đôi khi tạo **covered query**, nhưng hiệu quả I/O phải được xác nhận qua query plan. Hãy thiết kế projection theo hợp đồng API, xử lý `_id` có chủ đích và đánh giá index cùng filter/sort thực tế.

