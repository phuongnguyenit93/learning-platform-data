# `find`, `findOne` và cấu trúc bộ lọc truy vấn trong MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chương:** Truy vấn document

## 1. Mục tiêu

Khi ứng dụng cần lấy dữ liệu từ MongoDB, câu hỏi đầu tiên là **document nào phù hợp với điều kiện tìm kiếm?** Hai phương thức quen thuộc trong MongoDB Shell là `find()` và `findOne()`. Cả hai nhận một **query filter** (bộ lọc truy vấn) viết dưới dạng document. Filter quy định điều kiện khớp; các tùy chọn khác như projection, sort và limit quy định cách dữ liệu được trả về.

Sau bài học, bạn có thể phân biệt `find()` và `findOne()`, viết filter từ đơn giản đến lồng nhau, dùng toán tử so sánh/logic, truy vấn embedded document và array, xử lý đúng `null`/field thiếu, sử dụng projection và cursor, rồi triển khai filter tương đương qua MongoDB Java Sync Driver.

Bài học tập trung vào truy vấn **đọc document**. Với thao tác update/delete, filter cũng có cấu trúc tương tự nhưng hậu quả khác hẳn: một filter rỗng ở lệnh ghi/xóa có thể ảnh hưởng dữ liệu, vì vậy cần kiểm soát cẩn thận.

## 2. Chuẩn bị bộ dữ liệu mẫu

Kết nối bằng `mongosh` tới MongoDB Server, ví dụ:

```bash
mongosh "mongodb://127.0.0.1:27017"
```

Trong `mongosh`, chạy đoạn sau. Dữ liệu được đưa vào database **`query_filter_lab`**; sáu đơn hàng dùng `_id` cố định. `replaceOne` với `upsert: true` giúp chạy lại đoạn tạo dữ liệu mà không nhân đôi bản ghi mẫu:

```javascript
const lab = db.getSiblingDB("query_filter_lab");
const orders = lab.getCollection("orders");

const samples = [
  {
    _id: "O1001",
    status: "PAID",
    total: NumberDecimal("125.00"),
    createdAt: ISODate("2026-11-01T09:00:00Z"),
    customer: { name: "Lan", city: "Hà Nội" },
    tags: ["priority", "online"],
    items: [
      { sku: "A", qty: 1, price: NumberDecimal("90.00") },
      { sku: "B", qty: 2, price: NumberDecimal("17.50") }
    ],
    shipped: true,
    coupon: null
  },
  {
    _id: "O1002",
    status: "NEW",
    total: NumberDecimal("45.00"),
    createdAt: ISODate("2026-11-02T10:30:00Z"),
    customer: { name: "Minh", city: "Đà Nẵng" },
    tags: ["online"],
    items: [{ sku: "A", qty: 1, price: NumberDecimal("45.00") }],
    shipped: false
  },
  {
    _id: "O1003",
    status: "PAID",
    total: NumberDecimal("210.00"),
    createdAt: ISODate("2026-11-03T11:00:00Z"),
    customer: { name: "Hòa", city: "TP Hồ Chí Minh" },
    tags: ["priority"],
    items: [
      { sku: "C", qty: 3, price: NumberDecimal("60.00") },
      { sku: "D", qty: 1, price: NumberDecimal("30.00") }
    ],
    shipped: true,
    coupon: "WELCOME"
  },
  {
    _id: "O1004",
    status: "CANCELLED",
    total: NumberDecimal("60.00"),
    createdAt: ISODate("2026-11-04T08:15:00Z"),
    customer: { name: "An", city: "Hà Nội" },
    tags: [],
    items: [{ sku: "D", qty: 2, price: NumberDecimal("30.00") }],
    shipped: false,
    coupon: null
  },
  {
    _id: "O1005",
    status: "PAID",
    total: NumberDecimal("80.00"),
    createdAt: ISODate("2026-11-05T14:00:00Z"),
    customer: { name: "Linh", city: "Hà Nội" },
    tags: ["online", "gift"],
    items: [
      { sku: "A", qty: 2, price: NumberDecimal("25.00") },
      { sku: "B", qty: 3, price: NumberDecimal("10.00") }
    ],
    shipped: false
  },
  {
    _id: "O1006",
    status: "PAID",
    total: NumberDecimal("140.00"),
    createdAt: ISODate("2026-11-06T16:45:00Z"),
    customer: { name: "Mai", city: "TP Hồ Chí Minh" },
    tags: ["priority", "online"],
    items: [{ sku: "A", qty: 4, price: NumberDecimal("35.00") }],
    shipped: true,
    coupon: "VIP"
  }
];

for (const document of samples) {
  orders.replaceOne({ _id: document._id }, document, { upsert: true });
}

print("Số document:", orders.countDocuments({
  _id: { $in: samples.map(document => document._id) }
}));
```

Sau khi chạy, bạn sẽ có các kiểu dữ liệu để thực hành:

| Field | Kiểu BSON | Ví dụ |
|---|---|---|
| `_id` | String | `"O1001"` |
| `status` | String | `"PAID"` |
| `total` | Decimal128 | `NumberDecimal("125.00")` |
| `createdAt` | Date | `ISODate("2026-11-01T09:00:00Z")` |
| `customer` | Embedded document | `{ name: "Lan", city: "Hà Nội" }` |
| `tags` | Array of strings | `["priority", "online"]` |
| `items` | Array of documents | `[{ sku: "A", qty: 1, ... }]` |
| `coupon` | String, null hoặc missing | `"VIP"`, `null`, không có field |

Các ví dụ kết quả trong bài giả định collection chỉ chứa sáu đơn mẫu. Nếu đã có dữ liệu khác trong database lab, tổng số kết quả có thể thay đổi.

## 3. Phân biệt `find()` và `findOne()`

### 3.1. `find()` trả về cursor

Cú pháp trong MongoDB Shell:

```javascript
db.collection.find(query, projection, options)
```

Trong đó:

- **`query`:** document mô tả điều kiện lọc; bỏ trống tương đương filter `{}`.
- **`projection`:** document lựa chọn các field cần trả về; tùy chọn.
- **`options`:** các tùy chọn mở rộng khi cần.

Ví dụ:

```javascript
orders.find();                   // Mọi document
orders.find({});                 // Mọi document
orders.find({ status: "PAID" }); // Chỉ các document có status = "PAID"
```

Giá trị trả về là **cursor**, dùng để duyệt từ 0 đến nhiều document. MongoDB Shell có thể hiển thị một batch kết quả nhưng không có nghĩa toàn bộ document đã được tải vào RAM của client.

```javascript
const cursor = orders.find({ status: "PAID" });

for (const document of cursor) {
  print(document._id, document.status);
}
```

Khi bộ kết quả nhỏ, có thể chuyển thành array:

```javascript
const paidOrders = orders.find({ status: "PAID" }).toArray();
print("Số đơn:", paidOrders.length);
```

Tránh gọi `toArray()` tùy tiện trên hàng triệu document; cursor, projection và limit giúp quản lý dữ liệu trả về.

### 3.2. `findOne()` trả về một document hoặc `null`

Cú pháp thông dụng:

```javascript
db.collection.findOne(query, projection, options)
```

Ví dụ tra cứu theo `_id`:

```javascript
const order = orders.findOne({ _id: "O1001" });
if (order === null) {
  print("Không tìm thấy");
} else {
  printjson(order);
}
```

Nếu không có document nào khớp, `findOne()` trả `null`; còn `find()` trả về cursor rỗng.

| Tiêu chí | `find()` | `findOne()` |
|---|---|---|
| Trả về | Cursor (0..N document) | Một document hoặc `null` |
| Dùng để | Danh sách, tìm kiếm, duyệt batch | Tra cứu một bản ghi |
| Khi không khớp | Cursor rỗng | `null` |
| Sort/limit dạng chain | `.sort().limit()` | Không trả cursor để chain |
| Projection | Có | Có |

### 3.3. Một document không có nghĩa là “mới nhất”

Nếu viết:

```javascript
orders.findOne({ status: "PAID" });
```

có nhiều đơn `PAID` thỏa điều kiện. Không giả định MongoDB sẽ trả đơn mới nhất, đơn có `_id` nhỏ nhất hoặc bản ghi đầu tiên theo thời gian. Nếu cần đơn mới nhất, dùng sort và limit rõ ràng:

```javascript
orders.find({ status: "PAID" })
  .sort({ createdAt: -1, _id: 1 })
  .limit(1);
```

`-1` nghĩa là giảm dần; `1` nghĩa là tăng dần. Tie-breaker `_id` làm thứ tự xác định hơn khi nhiều document có cùng `createdAt`. Nếu cần chính document đó thay vì cursor, có thể dùng `.sort(...).limit(1).next()` sau khi kiểm tra cursor còn kết quả, hoặc trong Java driver dùng `.sort(...).first()`.

### 3.4. Filter rỗng không có nghĩa “document rỗng”

```javascript
orders.find({});
```

`{}` nghĩa là **không có ràng buộc lọc**. Khi API vô tình truyền filter rỗng do lỗi lập trình, truy vấn có thể trả dữ liệu rộng hơn mong đợi. Cần xác định các điều kiện bắt buộc và phạm vi quyền truy cập ở tầng ứng dụng.

## 4. Cấu trúc query filter

Filter là **document** với key mô tả field hoặc toán tử MongoDB. Dạng thường gặp:

```javascript
{
  status: "PAID",
  total: { $gte: NumberDecimal("100.00") }
}
```

Đọc là: tìm document có `status` bằng `PAID` **và** `total` lớn hơn hoặc bằng 100.

```text
Query filter
{
  <field-name>: <literal-value | operator-document>,
  <another-field>: <literal-value | operator-document>,
  ...
}
```

**Equality dạng ngắn:**

```javascript
{ status: "PAID" }
```

**Equality dùng operator:**

```javascript
{ status: { $eq: "PAID" } }
```

Với string scalar trong ví dụ, hai filter tương đương.

### 4.1. AND ngầm định

Các điều kiện nằm trong cùng filter nhưng thuộc các field khác nhau được kết hợp bằng AND:

```javascript
orders.find({
  status: "PAID",
  shipped: true
});
```

Document phải thỏa **cả hai** điều kiện.

### 4.2. Nhiều toán tử trên một field

```javascript
orders.find({
  total: {
    $gte: NumberDecimal("80"),
    $lt: NumberDecimal("150")
  }
});
```

Điều kiện có nghĩa `80 ≤ total < 150`. Cần gom toán tử cùng field vào một object, tránh lặp key `total` hai lần trong cùng JavaScript object.

### 4.3. Tên field khác toán tử

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Field cấp cao | `status` | Tên field trong document |
| Field lồng nhau | `"customer.city"` | Đường dẫn tới field city |
| Toán tử so sánh | `$gte` | Lớn hơn hoặc bằng |
| Toán tử logic | `$or` | Một trong các nhánh filter |
| Giá trị | `"PAID"` | Chuỗi BSON cần so sánh |
| Giá trị số đúng kiểu | `NumberDecimal("100")` | Giá trị Decimal128 |

MongoDB phân biệt chữ hoa/chữ thường trong **tên field**. Filter `{ Status: "PAID" }` không tương đương `{ status: "PAID" }`.

## 5. Toán tử so sánh

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| `$eq` | Bằng | `{ status: { $eq: "PAID" } }` |
| `$ne` | Khác | `{ status: { $ne: "CANCELLED" } }` |
| `$gt` | Lớn hơn | `{ total: { $gt: NumberDecimal("100") } }` |
| `$gte` | Lớn hơn hoặc bằng | `{ total: { $gte: NumberDecimal("100") } }` |
| `$lt` | Nhỏ hơn | `{ total: { $lt: NumberDecimal("100") } }` |
| `$lte` | Nhỏ hơn hoặc bằng | `{ total: { $lte: NumberDecimal("100") } }` |
| `$in` | Nằm trong một tập giá trị | `{ status: { $in: ["NEW", "PAID"] } }` |
| `$nin` | Không nằm trong một tập | `{ status: { $nin: ["NEW", "PAID"] } }` |

### 5.1. Lọc tổng tiền

```javascript
orders.find({
  total: { $gte: NumberDecimal("100.00") }
});
```

Với dữ liệu mẫu, `O1001`, `O1003` và `O1006` phù hợp.

### 5.2. Lọc khoảng thời gian bằng BSON Date

```javascript
orders.find({
  createdAt: {
    $gte: ISODate("2026-11-02T00:00:00Z"),
    $lt: ISODate("2026-11-05T00:00:00Z")
  }
});
```

Đây là khoảng **bao gồm cận dưới, không bao gồm cận trên**: từ đầu ngày 2/11 đến trước đầu ngày 5/11 theo UTC. Mẫu này hữu ích khi lọc khoảng ngày mà không dựa vào giả định về số giờ trong từng ngày của múi giờ địa phương.

Không nhầm BSON Date với string:

```javascript
// Không tương đương: giá trị dưới đây là string.
orders.find({ createdAt: { $gte: "2026-11-02" } });
```

MongoDB có quy tắc so sánh theo kiểu BSON và type bracketing. Hãy gửi giá trị filter đúng kiểu của dữ liệu đang lưu, nhất là với date, ObjectId, Decimal128 và số nguyên.

### 5.3. So sánh khác `$ne` có thể gồm field thiếu

```javascript
orders.find({
  status: { $ne: "PAID" }
});
```

`$ne` có thể khớp document không có field `status`. Nếu bạn yêu cầu field này tồn tại:

```javascript
orders.find({
  status: { $exists: true, $ne: "PAID" }
});
```

Cần phân biệt điều kiện `“không phải PAID”` với `“đang có trạng thái khác PAID”` khi schema cho phép field thiếu.

### 5.4. Dùng `$in` và `$nin`

```javascript
orders.find({ status: { $in: ["NEW", "PAID"] } });

orders.find({ status: { $nin: ["NEW", "CANCELLED"] } });
```

Với cùng một field, `$in` ngắn gọn hơn nhiều nhánh OR. `$nin` có thể khớp document thiếu field đang so sánh, nên cân nhắc thêm `$exists` hoặc một tập trạng thái cho phép nếu dữ liệu có thể chưa đầy đủ. Danh sách `$in` quá dài cũng có thể tốn chi phí truy vấn; nên giới hạn theo nhu cầu nghiệp vụ.

## 6. Toán tử logic `$and`, `$or`, `$nor`, `$not`

### 6.1. Dùng `$and` khi cần nối các filter

Điều kiện sau tương đương với AND ngầm định giữa hai field:

```javascript
orders.find({
  $and: [
    { status: "PAID" },
    { shipped: true }
  ]
});
```

`$and` hữu ích khi ghép các bộ lọc từ nhiều thành phần mà không thể biểu diễn gọn bằng một object, hoặc khi phải áp nhiều biểu thức phức tạp lên cùng field.

### 6.2. Dùng `$or` cho nhiều nhánh

Tìm đơn:

- Đã thanh toán và total từ 200 trở lên; **hoặc**
- Mới tạo và total nhỏ hơn 50.

```javascript
orders.find({
  $or: [
    {
      status: "PAID",
      total: { $gte: NumberDecimal("200") }
    },
    {
      status: "NEW",
      total: { $lt: NumberDecimal("50") }
    }
  ]
});
```

Với dữ liệu mẫu, `O1003` và `O1002` thỏa hai nhánh tương ứng.

### 6.3. Kết hợp AND với OR

Tìm đơn đã thanh toán ở Hà Nội hoặc TP Hồ Chí Minh:

```javascript
orders.find({
  status: "PAID",
  $or: [
    { "customer.city": "Hà Nội" },
    { "customer.city": "TP Hồ Chí Minh" }
  ]
});
```

Điều kiện tương đương: `status = PAID AND (city = Hà Nội OR city = TP Hồ Chí Minh)`. Khi hai nhánh chỉ khác giá trị của cùng một field, có thể thay bằng `$in`:

```javascript
orders.find({
  status: "PAID",
  "customer.city": {
    $in: ["Hà Nội", "TP Hồ Chí Minh"]
  }
});
```

### 6.4. Dùng `$nor` và `$not`

```javascript
orders.find({
  $nor: [
    { status: "CANCELLED" },
    { total: { $gt: NumberDecimal("200") } }
  ]
});
```

`$nor` chọn document **không khớp bất kỳ nhánh nào** trong danh sách.

```javascript
orders.find({
  total: { $not: { $gte: NumberDecimal("100") } }
});
```

`$not` phủ định biểu thức trên **một field**. Tùy trường hợp, `$not` cũng có thể khớp document thiếu field. Không coi `$not` là toán tử cấp cao thay thế tùy ý cho `$nor`.

### 6.5. Đừng lặp cùng một key trong JavaScript object

Cách viết này gây lỗi logic:

```javascript
// Không dùng: cùng key status xuất hiện hai lần.
{
  status: { $ne: "NEW" },
  status: { $ne: "CANCELLED" }
}
```

Một key trùng có thể ghi đè điều kiện trước. Dùng:

```javascript
{ status: { $nin: ["NEW", "CANCELLED"] } }
```

Hoặc dùng `$and` để giữ riêng các filter con nếu có lý do rõ ràng.

## 7. Truy vấn embedded document bằng dot notation

Với dữ liệu:

```javascript
customer: {
  name: "Lan",
  city: "Hà Nội"
}
```

hãy truy vấn một field lồng nhau bằng dot notation:

```javascript
orders.find({
  "customer.city": "Hà Nội"
});
```

Dấu chấm trong chuỗi `"customer.city"` biểu thị đường dẫn field. Nó không tạo collection riêng và cũng không liên quan đến tên namespace.

Có thể kết hợp các field lồng nhau:

```javascript
orders.find({
  "customer.name": "Lan",
  "customer.city": "Hà Nội"
});
```

### 7.1. So sánh toàn bộ embedded document

```javascript
orders.find({
  customer: { name: "Lan", city: "Hà Nội" }
});
```

So sánh equality trên embedded document yêu cầu object khớp cả cấu trúc và **thứ tự field**. Nếu object lưu trong MongoDB có thêm field hoặc sắp xếp field khác, filter equality có thể không khớp như mong đợi. Khi chỉ cần một vài thuộc tính, dot notation thường dễ đọc và ít phụ thuộc cấu trúc hơn.

### 7.2. Đường dẫn lồng nhau có thể thiếu

```javascript
orders.find({
  "customer.phone": { $exists: false }
});
```

Điều kiện này tìm document không có đường dẫn `customer.phone`. Trên dữ liệu thật, thiếu object cha `customer` và thiếu riêng `phone` có thể có ý nghĩa nghiệp vụ khác nhau; query cần phản ánh đúng contract.

## 8. Truy vấn array và `$elemMatch`

### 8.1. Tìm phần tử trong array string

Với `tags` là array:

```javascript
orders.find({ tags: "priority" });
```

Trong MongoDB, equality với scalar có thể khớp khi array chứa phần tử đó. Điều này khác với equality nguyên array:

```javascript
orders.find({ tags: ["priority", "online"] });
```

Query thứ hai yêu cầu array tương đương đúng các phần tử **và thứ tự**.

Nếu muốn array chứa cả hai giá trị bất kể vị trí:

```javascript
orders.find({
  tags: { $all: ["priority", "online"] }
});
```

Với mẫu, `O1001` và `O1006` thỏa điều kiện `$all`.

### 8.2. Kiểm tra số phần tử array

```javascript
orders.find({
  tags: { $size: 0 }
});
```

`$size: 0` tìm array rỗng (`O1004` trong ví dụ). `$size` dùng cho số phần tử chính xác; không thể trực tiếp đưa `$gte` vào `$size` để so sánh “ít nhất N phần tử”.

### 8.3. Field của array chứa object

Tìm đơn có item SKU `A`:

```javascript
orders.find({
  "items.sku": "A"
});
```

Có thể thêm điều kiện số lượng:

```javascript
orders.find({
  "items.sku": "A",
  "items.qty": { $gte: 3 }
});
```

**Điểm dễ nhầm:** hai điều kiện có thể khớp **hai phần tử khác nhau** trong array. `O1005` có item SKU `A` với `qty = 2` và item SKU `B` với `qty = 3`, nên document vẫn có thể khớp filter trên.

### 8.4. Dùng `$elemMatch` để buộc cùng một phần tử thỏa điều kiện

```javascript
orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 }
    }
  }
});
```

Trong dữ liệu mẫu, `O1006` thỏa vì có phần tử `{ sku: "A", qty: 4, ... }`, còn `O1005` không. So sánh:

```text
"items.sku" = "A" AND "items.qty" >= 3
→ Có thể là hai phần tử khác nhau.

items: { $elemMatch: { sku: "A", qty: { $gte: 3 } } }
→ Cùng một phần tử thỏa cả hai điều kiện.
```

Đây là khác biệt quan trọng khi lọc order items, event attributes hoặc bất kỳ array các embedded document nào.

## 9. `null`, field thiếu, `$exists` và `$type`

Bộ dữ liệu mẫu có ba trạng thái của `coupon`:

- `O1001` và `O1004` có `coupon: null`.
- `O1002` và `O1005` không có field `coupon`.
- `O1003` và `O1006` có coupon là string.

### 9.1. `{ coupon: null }` khớp cả null và missing

```javascript
orders.find({ coupon: null });
```

Kết quả trong lab gồm `O1001`, `O1002`, `O1004`, `O1005`. Điều này là semantics equality null của MongoDB, không phải MongoDB tự thêm `coupon` vào document thiếu field.

### 9.2. Chỉ tìm explicit null hoặc missing

```javascript
// Field tồn tại và mang BSON null:
orders.find({ coupon: { $type: "null" } });

// Field không tồn tại:
orders.find({ coupon: { $exists: false } });

// Field tồn tại, kể cả nếu value bằng null:
orders.find({ coupon: { $exists: true } });

// Field là BSON string:
orders.find({ coupon: { $type: "string" } });
```

| Filter | Ý nghĩa |
|---|---|
| `{ coupon: null }` | Null **hoặc** missing |
| `{ coupon: { $type: "null" } }` | Explicit null |
| `{ coupon: { $exists: false } }` | Missing |
| `{ coupon: { $exists: true } }` | Field có mặt, kể cả null |
| `{ coupon: { $ne: null } }` | Field có mặt và khác null |
| `{ coupon: { $type: "string" } }` | Có giá trị string |

### 9.3. Truy vấn kiểu dữ liệu

```javascript
orders.find({ total: { $type: "decimal" } });
orders.find({ createdAt: { $type: "date" } });
orders.find({ shipped: { $type: "bool" } });
```

Trên dữ liệu schema linh hoạt, có thể tồn tại nhiều kiểu BSON cho cùng field; hãy xác định kiểu trước khi viết so sánh số/ngày. Với array, `$type` còn có những quy tắc đặc biệt khi xét phần tử của array; tham khảo tài liệu để tránh suy luận sai.

## 10. Lọc string bằng collation và regular expression

### 10.1. Equality theo mặc định thường phân biệt chữ hoa

```javascript
orders.find({ status: "PAID" });
orders.find({ status: "paid" });
```

Nếu collection không định nghĩa collation khác, so sánh mặc định theo binary simple collation khiến `"PAID"` khác `"paid"`.

### 10.2. Collation điều khiển so sánh string

```javascript
orders.find({ status: "paid" })
  .collation({ locale: "en", strength: 2 });
```

Collation có thể cho phép so sánh string không phân biệt casing. `strength: 2` giữ một số khác biệt accent/diacritics, còn `strength: 1` là mức so sánh cơ bản hơn; kết quả phụ thuộc locale. Collation chỉ điều chỉnh **giá trị string**, không làm tên field `Status` và `status` trở nên tương đương.

Để truy vấn tận dụng index trên string với collation, index và query cần có collation tương thích.

### 10.3. Filter dùng `$regex`

Tìm tên khách hàng bắt đầu bằng `L`:

```javascript
orders.find({
  "customer.name": { $regex: /^L/ }
});
```

Hoặc không phân biệt casing:

```javascript
orders.find({
  "customer.name": { $regex: "^l", $options: "i" }
});
```

Regex nên có giới hạn về độ dài và độ phức tạp. Regex không neo đầu chuỗi hoặc có tùy chọn `i` thường khó được index tối ưu như truy vấn equality/prefix thích hợp. Index dùng collation không tự động giúp `$regex` trở nên case-insensitive theo cùng cơ chế. Không đưa trực tiếp regex tùy ý của người dùng vào API tìm kiếm nếu chưa thiết kế cách kiểm soát tài nguyên và escaping metacharacter.

## 11. Projection: chọn field trả về

**Filter** quyết định document nào phù hợp; **projection** quyết định field nào từ các document đó được trả về.

```javascript
orders.find(
  { status: "PAID" },
  { status: 1, total: 1, "customer.name": 1 }
);
```

Giá trị `1` trong projection yêu cầu đưa field vào kết quả. MongoDB trả `_id` theo mặc định, trừ khi loại bỏ:

```javascript
orders.find(
  { status: "PAID" },
  { _id: 0, status: 1, total: 1, "customer.name": 1 }
);
```

Projection loại trừ:

```javascript
orders.find(
  { status: "PAID" },
  { items: 0, tags: 0 }
);
```

Trong projection thông thường, không trộn inclusion và exclusion cho các field khác nhau, **ngoại trừ `_id`**. Projection không sửa dữ liệu bên trong database.

### 11.1. Filter và projection khác nhau

```javascript
orders.find({ status: "PAID" });
// Chỉ những document có status PAID, trả đầy đủ các field.

orders.find({}, { status: 1 });
// Mọi document, chỉ trả status và _id.

orders.find(
  { status: "PAID" },
  { _id: 0, status: 1, total: 1 }
);
// Chỉ PAID, chỉ trả status và total.
```

`findOne()` cũng nhận projection:

```javascript
orders.findOne(
  { _id: "O1001" },
  { _id: 0, status: 1, total: 1 }
);
```

Projection hữu ích để giảm kích thước response. Tuy vậy, với dữ liệu nhạy cảm, **phân quyền, kiểm tra danh tính và API contract** vẫn cần thiết; projection trong một hàm không phải biện pháp bảo mật toàn diện.

## 12. Cursor, sort, limit và phân trang

### 12.1. Sắp xếp và giới hạn

```javascript
orders.find({ status: "PAID" })
  .sort({ createdAt: -1, _id: 1 })
  .limit(3);
```

Điều kiện `status` chọn bản ghi; `sort` cho biết thứ tự; `limit` chỉ trả tối đa ba document.

Nếu thiếu sort, thứ tự kết quả không được bảo đảm ổn định qua các lần thực thi. Điều này có thể gây lỗi phân trang, so sánh snapshot và hiển thị danh sách.

### 12.2. Phân trang bằng `skip()`

```javascript
orders.find({ status: "PAID" })
  .sort({ createdAt: -1, _id: 1 })
  .skip(2)
  .limit(2);
```

Cách này đơn giản cho tập dữ liệu nhỏ. Với trang sâu, server vẫn cần xử lý các bản ghi bị bỏ qua; dữ liệu thay đổi giữa hai request có thể gây trùng/mất bản ghi trong các trang.

### 12.3. Phân trang theo khóa cuối

Với thứ tự `{ createdAt: 1, _id: 1 }`, một query trang sau có thể tìm các bản ghi nằm sau cặp khóa cuối của trang trước:

```javascript
const lastCreatedAt = ISODate("2026-11-03T11:00:00Z");
const lastId = "O1003";

orders.find({
  status: "PAID",
  $or: [
    { createdAt: { $gt: lastCreatedAt } },
    { createdAt: lastCreatedAt, _id: { $gt: lastId } }
  ]
})
  .sort({ createdAt: 1, _id: 1 })
  .limit(2);
```

Cách này gọi là keyset/seek pagination. Nó phù hợp khi cần trang sâu và có khóa sort ổn định. Ứng dụng cần giữ thống nhất filter, sort, collation và trạng thái dữ liệu mong muốn trong thời gian người dùng duyệt trang.

### 12.4. `find()` không tự tải mọi kết quả

Cursor có thể nhận dữ liệu theo batch. Trên kết quả rất lớn, `toArray()` dùng bộ nhớ phía client nhiều hơn cách lặp cursor; projection và limit giúp giảm dữ liệu truyền. Trong Java driver, đóng cursor/tham chiếu tài nguyên theo vòng đời ứng dụng.

## 13. Filter và index: kiểm tra kế hoạch truy vấn

Một filter đúng có thể chạy nhanh trên sáu document nhưng chậm trên hàng triệu document. Index giúp một số filter và sort chọn lọc hoạt động hiệu quả hơn.

Trong lab, có thể tạo index phục vụ truy vấn status và ngày:

```javascript
orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_status_createdAt_desc" }
);
```

Truy vấn:

```javascript
orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(5);
```

Xem kế hoạch thực thi:

```javascript
orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(5)
  .explain("executionStats");
```

Các mục thường gặp:

| Thành phần | Ý nghĩa |
|---|---|
| `COLLSCAN` | Quét các document của collection |
| `IXSCAN` | Quét index |
| `nReturned` | Số document trả về |
| `totalKeysExamined` | Số index key được xét |
| `totalDocsExamined` | Số document được xét |

Kế hoạch có thể khác theo phiên bản MongoDB và bộ dữ liệu. Trên dữ liệu lab nhỏ, collection scan có thể là lựa chọn hợp lý của query planner. Không thêm index bừa bãi: index tiêu tốn dung lượng, bộ nhớ và làm tăng chi phí ghi. Hãy chọn index theo truy vấn thật và đo hiệu quả bằng `explain`.

## 14. Ví dụ Java Sync Driver

Trong dự án Java sử dụng MongoDB Sync Driver, bộ lọc có thể được tạo bằng các builder như `Filters`, `Projections` và `Sorts`.

Ví dụ dependency Maven:

```xml
<dependency>
    <groupId>org.mongodb</groupId>
    <artifactId>mongodb-driver-sync</artifactId>
    <version>5.5.0</version>
</dependency>
```

Phiên bản `5.5.0` chỉ là **mốc minh họa**, không phải khẳng định bản mới nhất. Chọn phiên bản thực tế theo dependency management, JDK và bảng tương thích của MongoDB Driver.

### 14.1. Dùng `Filters` để tạo điều kiện

```java
import com.mongodb.client.FindIterable;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.bson.types.Decimal128;

import java.math.BigDecimal;

public class FindOrders {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            uri = "mongodb://127.0.0.1:27017";
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                    .getDatabase("query_filter_lab")
                    .getCollection("orders");

            Bson filter = Filters.and(
                    Filters.eq("status", "PAID"),
                    Filters.gte(
                            "total",
                            new Decimal128(new BigDecimal("100.00"))
                    )
            );

            FindIterable<Document> results = orders.find(filter)
                    .projection(Projections.fields(
                            Projections.include(
                                    "status", "total", "customer.name"
                            ),
                            Projections.excludeId()
                    ))
                    .sort(Sorts.descending("createdAt"))
                    .limit(10);

            for (Document order : results) {
                System.out.println(order.toJson());
            }
        }
    }
}
```

Trong đoạn trên:

- `Filters.eq("status", "PAID")` tương đương `{ status: "PAID" }`.
- `Filters.gte("total", ...)` tương đương `{ total: { $gte: ... } }`.
- `Filters.and(...)` kết hợp hai điều kiện.
- `Decimal128` khớp kiểu BSON Decimal128 của dữ liệu mẫu.
- `Projections`, `Sorts` và `limit` điều khiển dữ liệu trả về.

### 14.2. Tương đương `findOne` trong Java

Với Java Sync Driver, cách thường dùng để lấy một document là `find(filter).first()`:

```java
Document first = orders.find(
        Filters.eq("_id", "O1001")
).first();

if (first == null) {
    System.out.println("Không tìm thấy");
} else {
    System.out.println(first.toJson());
}
```

Nếu cần document mới nhất, thêm `sort` trước `first()`:

```java
Document newest = orders
        .find(Filters.eq("status", "PAID"))
        .sort(Sorts.descending("createdAt", "_id"))
        .first();
```

### 14.3. Dùng `elemMatch` trong Java

```java
Bson filter = Filters.elemMatch(
        "items",
        Filters.and(
                Filters.eq("sku", "A"),
                Filters.gte("qty", 3)
        )
);

orders.find(filter).forEach(doc ->
        System.out.println(doc.getString("_id"))
);
```

Builder giúp tổ chức truy vấn rõ ràng, nhưng không tự kiểm tra field có tồn tại trong schema hay không. Một lỗi nhỏ như `customer.City` thay vì `customer.city` vẫn có thể khiến kết quả sai. Cần định nghĩa hợp đồng dữ liệu nhất quán và kiểm thử bằng database phù hợp ở bước phát triển ứng dụng.

## 15. Tạo filter an toàn từ yêu cầu API

API thường cho phép tham số như `status`, `minTotal`, `fromDate`. Không nên nhận nguyên một document MongoDB filter tùy ý từ Internet rồi chuyển thẳng vào `find()`.

Ví dụ tạo filter từ giá trị đã kiểm tra:

```javascript
const allowedStatuses = ["NEW", "PAID", "CANCELLED"];
const requestedStatus = "PAID";

if (!allowedStatuses.includes(requestedStatus)) {
  throw new Error("status không hợp lệ");
}

const query = {
  status: requestedStatus,
  total: { $gte: NumberDecimal("100.00") }
};

printjson(orders.find(query).limit(20).toArray());
```

Các yêu cầu quan trọng:

1. **Chỉ cho phép field và operator được công bố** trong API; tránh để client tự ý đưa `$where`, expression phức tạp hoặc filter không giới hạn.
2. **Parse và validate kiểu** trước khi tạo BSON filter: số tiền là Decimal128 theo hợp đồng, ngày là BSON Date, định danh đúng kiểu.
3. **Giới hạn kết quả** và kiểm soát pagination để tránh vô tình xuất toàn bộ collection.
4. **Bổ sung điều kiện phân quyền** từ identity đáng tin cậy của server. Ví dụ, filter `tenantId` phải được nối bằng AND với filter của người dùng, không dựa vào tenantId trong request body.
5. **Không tự ghép query JSON bằng nối chuỗi**, vì dễ sai escaping, sai logic và tạo lỗ hổng NoSQL injection.
6. **Đo thời gian truy vấn** và áp dụng giới hạn tài nguyên phù hợp với endpoint tìm kiếm.

Bảo vệ truy vấn không dừng ở câu lệnh `find`: xác thực, phân quyền, projection dữ liệu nhạy cảm và kiểm soát kết quả phải được thực thi đồng bộ.

## 16. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `find()` trả nhiều dữ liệu hơn dự kiến | Filter `{}` hoặc bỏ sót điều kiện | Kiểm tra filter và ràng buộc quyền truy cập |
| `findOne()` trả bản ghi “không đúng thứ tự” | Có nhiều bản ghi khớp, không có sort | Tìm bằng ID duy nhất hoặc sort/limit |
| Không khớp trường ngày | Dùng string thay cho BSON Date | Dùng `ISODate` hoặc date type của driver |
| Không khớp trường số | Dữ liệu lẫn decimal, double, string | Xác minh kiểu BSON, chuẩn hóa schema |
| `Status` không khớp `status` | Tên field phân biệt casing | Dùng đúng tên field |
| Filter `{ coupon: null }` trả cả missing | Equality với null khớp null/missing | Dùng `$type: "null"` hay `$exists: false` |
| `$ne` / `$nin` trả field thiếu | Semantics phủ định | Kết hợp kiểm tra tồn tại nếu cần |
| Filter array cho kết quả bất ngờ | Các điều kiện khớp các phần tử khác nhau | Dùng `$elemMatch` |
| Equality trên array không khớp | Thứ tự phần tử hoặc nội dung khác | Dùng `$all` nếu chỉ cần chứa cả hai giá trị |
| Lặp key trong object filter | Key trước bị ghi đè | Gộp operator hoặc dùng `$and` |
| Regex quá chậm | Pattern ít chọn lọc, index không phù hợp | Giới hạn pattern và xem `explain()` |
| Phân trang trùng/mất bản ghi | Không sort, skip quá sâu hoặc dữ liệu đổi | Sort có tie-breaker, cân nhắc keyset |
| API trả field không cần thiết | Thiếu projection và kiểm soát quyền | Chỉ trả field theo contract, kiểm tra quyền |

## 17. Bài thực hành tổng hợp

Các bài sau sử dụng `orders` tạo ở mục 2.

### Bài 1: Tìm đơn với điều kiện đơn giản

Viết truy vấn để:

- Lấy các đơn `PAID`.
- Lấy đúng đơn `O1003`.
- Lấy các đơn có tổng tiền từ 80 đến dưới 150.
- Lấy đơn tạo từ đầu 3/11 đến trước đầu 6/11 theo UTC.

Gợi ý:

```javascript
orders.find({ status: "PAID" });
orders.findOne({ _id: "O1003" });

orders.find({
  total: {
    $gte: NumberDecimal("80"),
    $lt: NumberDecimal("150")
  }
});

orders.find({
  createdAt: {
    $gte: ISODate("2026-11-03T00:00:00Z"),
    $lt: ISODate("2026-11-06T00:00:00Z")
  }
});
```

### Bài 2: Kết hợp AND và OR

Tìm đơn `PAID` và đồng thời thỏa một trong hai điều kiện: tổng tiền từ 200 hoặc khách ở Hà Nội.

```javascript
orders.find({
  status: "PAID",
  $or: [
    { total: { $gte: NumberDecimal("200") } },
    { "customer.city": "Hà Nội" }
  ]
});
```

Trong mẫu, các đơn `O1001`, `O1003`, `O1005` thỏa. Hãy xác định mỗi đơn thuộc nhánh OR nào.

### Bài 3: So sánh array query và `$elemMatch`

```javascript
const separate = orders.find({
  "items.sku": "A",
  "items.qty": { $gte: 3 }
}).toArray();

const sameItem = orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 }
    }
  }
}).toArray();

printjson(separate.map(doc => doc._id));
printjson(sameItem.map(doc => doc._id));
```

Vì sao `O1005` có thể xuất hiện ở truy vấn đầu nhưng không xuất hiện ở truy vấn sau? Vì item có `sku = "A"` và item có `qty ≥ 3` của nó là **hai phần tử khác nhau**.

### Bài 4: Phân biệt null với missing

```javascript
print("Null hoặc missing:");
printjson(orders.find(
  { coupon: null },
  { _id: 1 }
).toArray());

print("Explicit null:");
printjson(orders.find(
  { coupon: { $type: "null" } },
  { _id: 1 }
).toArray());

print("Missing:");
printjson(orders.find(
  { coupon: { $exists: false } },
  { _id: 1 }
).toArray());
```

Đối chiếu ba danh sách và giải thích sự khác biệt.

### Bài 5: Projection, sort và limit

Lấy ba đơn `PAID` mới nhất, chỉ trả `_id`, `status`, `total`:

```javascript
orders.find(
  { status: "PAID" },
  { _id: 1, status: 1, total: 1 }
)
  .sort({ createdAt: -1, _id: 1 })
  .limit(3);
```

Thay projection thành `{ _id: 0, status: 1, total: 1 }` để quan sát việc loại `_id` khỏi kết quả; điều kiện filter không thay đổi.

### Bài 6: Chuyển query sang Java driver

Filter shell:

```javascript
{
  status: "PAID",
  "customer.city": "Hà Nội",
  total: { $gte: NumberDecimal("80") }
}
```

Bộ lọc tương đương trong Java:

```java
Bson filter = Filters.and(
        Filters.eq("status", "PAID"),
        Filters.eq("customer.city", "Hà Nội"),
        Filters.gte("total", new Decimal128(new BigDecimal("80.00")))
);
```

Kiểm tra cả hai bên kết nối cùng database `query_filter_lab`, collection `orders` và dùng đúng kiểu Decimal128.

## 18. Tài liệu chính thức

- [Query Documents](https://www.mongodb.com/docs/manual/tutorial/query-documents/)
- [db.collection.find()](https://www.mongodb.com/docs/manual/reference/method/db.collection.find/)
- [db.collection.findOne()](https://www.mongodb.com/docs/manual/reference/method/db.collection.findOne/)
- [Query and Projection Operators](https://www.mongodb.com/docs/manual/reference/operator/query/)
- [Comparison Query Operators](https://www.mongodb.com/docs/manual/reference/operator/query-comparison/)
- [Logical Query Operators](https://www.mongodb.com/docs/manual/reference/operator/query-logical/)
- [Query an Array](https://www.mongodb.com/docs/manual/tutorial/query-arrays/)
- [Query an Array of Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/)
- [Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/)
- [Project Fields to Return from Query](https://www.mongodb.com/docs/manual/tutorial/project-fields-from-query-results/)
- [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Java Sync Driver – Read Data](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)

MongoDB filter là một document mô tả **điều kiện logic**. Nắm đúng cấu trúc filter, kiểu BSON, đường dẫn field và semantics của array/null giúp cả `find()` lẫn `findOne()` trả đúng document; projection, sort, limit và index tiếp tục quyết định cách truy vấn phục vụ ứng dụng thực tế.
