# Mô hình tài liệu trong NoSQL: dữ liệu lồng nhau và truy vấn theo trường

## 1. Mô hình tài liệu là gì?

**Document database (cơ sở dữ liệu tài liệu)** lưu dữ liệu thành các **tài liệu (document)**. Mỗi tài liệu mô tả một thực thể hoặc một đơn vị dữ liệu nghiệp vụ, gồm các cặp **tên trường – giá trị**. Giá trị có thể là kiểu đơn giản như chuỗi, số, boolean, ngày giờ hoặc kiểu phức hợp như **đối tượng lồng nhau** và **mảng**.

Các document thường được tập hợp trong một **collection**. Chẳng hạn, hệ thống bán hàng có collection `orders` chứa đơn hàng, `customers` chứa khách hàng và `products` chứa sản phẩm. Trong MongoDB, mỗi document có trường `_id` dùng để định danh duy nhất trong collection.

Điểm đặc trưng của mô hình tài liệu là có thể đặt dữ liệu thường được đọc cùng nhau **trong cùng một document**. Thay vì bắt buộc chia mọi thông tin thành nhiều bảng và kết hợp bằng `JOIN`, một đơn hàng có thể chứa ngay địa chỉ giao hàng và danh sách dòng hàng.

Ví dụ, cấu trúc dữ liệu rút gọn:

```json
{
  "_id": "ORD-1052",
  "customerId": "CUS-007",
  "status": "PAID",
  "shipping": {
    "recipient": { "name": "Mai", "phone": "0900000000" },
    "address": { "city": "Hà Nội", "district": "Cầu Giấy" }
  },
  "items": [
    { "sku": "BK-101", "quantity": 2, "unitPrice": 150000 },
    { "sku": "BK-202", "quantity": 1, "unitPrice": 220000 }
  ],
  "tags": ["priority", "gift"]
}
```

Ở đây:

- `shipping` là **embedded document** (đối tượng lồng nhau).
- `shipping.recipient` và `shipping.address` tạo thêm các cấp lồng nhau.
- `items` là **mảng đối tượng**; mỗi phần tử mô tả một dòng hàng.
- `tags` là **mảng giá trị đơn giản**.
- `customerId` lưu **tham chiếu** đến khách hàng thay vì nhúng toàn bộ khách hàng.

> Từ "tài liệu" trong document database không nhất thiết là file Word/PDF hay văn bản dài. Một document thường là bản ghi cấu trúc JSON-like đại diện cho dữ liệu ứng dụng.

MongoDB là ví dụ phổ biến của document database. Nó biểu diễn dữ liệu theo cú pháp gần JSON nhưng lưu bên trong bằng **BSON**, có thêm kiểu như `Date`, `ObjectId`, `Decimal128`. Các ví dụ tiếp theo dùng **MongoDB/mongosh** để minh họa; lệnh cụ thể không mặc nhiên dùng được trên mọi hệ NoSQL.

## 2. Tài liệu lồng nhau biểu diễn một thực thể ra sao?

Giả sử ứng dụng muốn hiển thị chi tiết đơn hàng, bao gồm người nhận, địa chỉ, phương thức thanh toán và từng sản phẩm. Có thể thiết kế một document `orders` đầy đủ hơn:

```javascript
db.orders.insertOne({
  _id: "ORD-1052",
  customerId: "CUS-007",
  status: "PAID",
  createdAt: ISODate("2026-11-11T08:30:00Z"),
  shipping: {
    recipient: {
      name: "Mai",
      phone: "0900000000"
    },
    address: {
      city: "Hà Nội",
      district: "Cầu Giấy",
      street: "Đường Mẫu số 1"
    },
    deliveryMethod: "STANDARD"
  },
  payment: {
    method: "CARD",
    paidAt: ISODate("2026-11-11T08:32:00Z")
  },
  items: [
    {
      sku: "BK-101",
      name: "Sách A",
      quantity: 2,
      unitPrice: 150000,
      attributes: { language: "vi", edition: 2 }
    },
    {
      sku: "BK-202",
      name: "Sách B",
      quantity: 1,
      unitPrice: 220000,
      attributes: { language: "en", edition: 1 }
    }
  ],
  tags: ["priority", "gift"],
  totals: {
    merchandise: 520000,
    shippingFee: 30000,
    grandTotal: 550000
  }
})
```

Sơ đồ cấu trúc:

```text
Document Order
├── _id: "ORD-1052"
├── customerId: "CUS-007"
├── status: "PAID"
├── createdAt: Date
├── shipping: object
│   ├── recipient: object
│   │   ├── name
│   │   └── phone
│   ├── address: object
│   │   ├── city
│   │   ├── district
│   │   └── street
│   └── deliveryMethod
├── payment: object
│   ├── method
│   └── paidAt
├── items: array<object>
│   ├── item 0: sku, name, quantity, unitPrice, attributes
│   └── item 1: sku, name, quantity, unitPrice, attributes
├── tags: array<string>
└── totals: object
    ├── merchandise
    ├── shippingFee
    └── grandTotal
```

Nếu màn hình đơn hàng luôn cần `shipping`, `items` và `totals` cùng lúc, một phép đọc theo `_id` có thể trả toàn bộ thông tin cần thiết. Tuy vậy, nhúng không đồng nghĩa mọi dữ liệu đều phải đặt chung: hồ sơ khách hàng dùng ở nhiều đơn thường nên được quản lý riêng; trong đơn hàng chỉ giữ `customerId` và những thông tin cần **chụp lại tại thời điểm đặt đơn**, chẳng hạn tên sản phẩm và đơn giá.

### Document khác hàng trong bảng quan hệ ở điểm nào?

| Khía cạnh | Mô hình tài liệu | Mô hình quan hệ truyền thống |
|---|---|---|
| Đơn vị dữ liệu chính | Document trong collection | Row trong table |
| Dữ liệu nhiều cấp | Object lồng nhau và array | Thường tách thành bảng/quan hệ |
| Chi tiết đơn hàng | Có thể nằm trong `orders.items` | Thường có bảng `order_items` |
| Khai báo cấu trúc | Có thể linh hoạt theo document, vẫn nên có quy ước/schema | Lược đồ bảng được khai báo rõ |
| Kết hợp thực thể | Embed, reference, phép lookup nếu hệ hỗ trợ | Foreign key và `JOIN` |
| Truy vấn theo thuộc tính | Truy cập trường kể cả đường dẫn lồng nhau | Truy cập cột, có thể phải join bảng |

Đây là cách mô tả xu hướng thiết kế; cả hệ quan hệ hiện đại lẫn hệ document đều có thêm khả năng ngoài bảng so sánh, ví dụ cột JSON trong SQL hoặc `$lookup` trong MongoDB.

## 3. Truy vấn theo trường đơn giản

**Field query** là truy vấn dựa trên giá trị một hoặc nhiều trường trong document. Ta có thể so sánh bằng, so sánh khoảng, kiểm tra thuộc tập giá trị hoặc kết hợp các điều kiện.

### So sánh bằng và nhiều điều kiện

```javascript
// Tất cả đơn PAID của khách CUS-007.
db.orders.find({
  customerId: "CUS-007",
  status: "PAID"
})
```

Hai cặp khóa – giá trị trong cùng đối tượng điều kiện mặc định được kết hợp theo logic **AND**: cả `customerId` và `status` phải khớp.

### So sánh và điều kiện thuộc tập

```javascript
// Đơn đã thanh toán, tổng tiền từ 500.000 VND trở lên.
db.orders.find({
  status: "PAID",
  "totals.grandTotal": { $gte: 500000 }
})

// Đơn thuộc một trong hai trạng thái.
db.orders.find({
  status: { $in: ["PAID", "SHIPPED"] }
})
```

Các toán tử thường gặp:

| Toán tử MongoDB | Ý nghĩa | Ví dụ |
|---|---|---|
| `$eq` / gán trực tiếp | Bằng | `{ status: "PAID" }` |
| `$ne` | Khác | `{ status: { $ne: "CANCELLED" } }` |
| `$gt`, `$gte` | Lớn hơn, lớn hơn hoặc bằng | `{ "totals.grandTotal": { $gte: 500000 } }` |
| `$lt`, `$lte` | Nhỏ hơn, nhỏ hơn hoặc bằng | `{ "totals.grandTotal": { $lt: 1000000 } }` |
| `$in` | Giá trị nằm trong danh sách | `{ status: { $in: ["PAID", "SHIPPED"] } }` |
| `$and`, `$or` | Kết hợp điều kiện | `{ $or: [{status: "PAID"}, {status: "SHIPPED"}] }` |
| `$exists` | Có/không có trường | `{ "payment.paidAt": { $exists: true } }` |

Ví dụ lọc đơn theo ngày và trạng thái:

```javascript
db.orders.find({
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
})
```

Đoạn trên sử dụng **khoảng thời gian nửa mở** từ đầu tháng đến trước đầu tháng sau, tránh vấn đề xác định mili giây cuối cùng của tháng. Dữ liệu ví dụ lưu ngày ở UTC; ứng dụng cần thống nhất múi giờ khi diễn giải kỳ báo cáo.

## 4. Truy vấn theo đường dẫn trường lồng nhau (dot notation)

Document có cấu trúc sâu không buộc phải truy vấn nguyên đối tượng. MongoDB hỗ trợ **dot notation** để đi từ tên trường cha xuống trường con. Khi tên đường dẫn có dấu chấm, đặt đường dẫn trong chuỗi:

```javascript
// Tìm các đơn giao đến Hà Nội.
db.orders.find({
  "shipping.address.city": "Hà Nội"
})

// Tìm các đơn thanh toán bằng thẻ.
db.orders.find({
  "payment.method": "CARD"
})

// Tìm đơn PAID của khách CUS-007 giao đến Hà Nội.
db.orders.find({
  customerId: "CUS-007",
  status: "PAID",
  "shipping.address.city": "Hà Nội"
})
```

Điều kiện `"shipping.address.city": "Hà Nội"` đi qua các cấp `shipping` → `address` → `city`. Nó không yêu cầu document phải giống hoàn toàn một mẫu `shipping` định sẵn; chỉ quan tâm trường ở đường dẫn đó.

**So sánh cả object không giống so sánh một trường bên trong.** Ví dụ:

```javascript
db.orders.find({
  "shipping.address": {
    city: "Hà Nội",
    district: "Cầu Giấy",
    street: "Đường Mẫu số 1"
  }
})
```

Đây là phép so sánh **embedded document nguyên vẹn**; các trường có thêm, bị thiếu hoặc khác thứ tự có thể khiến kết quả không khớp. Khi chỉ cần đối chiếu thành phố và quận, nên viết:

```javascript
db.orders.find({
  "shipping.address.city": "Hà Nội",
  "shipping.address.district": "Cầu Giấy"
})
```

### Trường không tồn tại, `null` và kiểu dữ liệu

Lược đồ linh hoạt khiến các document có thể khác nhau về trường. Cần phân biệt:

```javascript
// Có trường payment.paidAt (kể cả khi giá trị là null).
db.orders.find({
  "payment.paidAt": { $exists: true }
})

// Không có trường payment.paidAt.
db.orders.find({
  "payment.paidAt": { $exists: false }
})

// Trong MongoDB, so sánh bằng null khớp cả trường null và trường thiếu.
db.orders.find({
  "payment.paidAt": null
})
```

Nếu yêu cầu nghiệp vụ cần phân biệt **chưa có trường** với **trường tồn tại nhưng chưa có giá trị**, cần viết điều kiện rõ ràng và thống nhất quy ước dữ liệu. Không nên mặc định rằng `null` luôn tương đương với "không có thông tin" trong mọi hệ thống.

## 5. Truy vấn bên trong mảng và mảng đối tượng

Mảng là một lợi thế lớn của document model: một document có thể chứa nhiều giá trị cùng loại hoặc nhiều đối tượng con. Tuy nhiên, điều kiện truy vấn mảng có những ngữ nghĩa cần hiểu rõ.

### Mảng giá trị đơn giản

```javascript
// Chỉ cần có "gift" trong mảng tags.
db.orders.find({
  tags: "gift"
})

// Yêu cầu có cả "gift" và "priority".
db.orders.find({
  tags: { $all: ["gift", "priority"] }
})

// Mảng tags chứa đúng 2 phần tử.
db.orders.find({
  tags: { $size: 2 }
})
```

Trong MongoDB, `{ tags: "gift" }` khớp nếu `tags` là mảng **chứa** chuỗi `"gift"`; không đòi cả trường `tags` phải bằng chuỗi này. Còn điều kiện `{ tags: ["priority", "gift"] }` là so sánh toàn bộ mảng theo nội dung và thứ tự, khác với `$all`.

### Mảng object và dot notation

```javascript
// Đơn có ít nhất một dòng hàng mang SKU BK-101.
db.orders.find({
  "items.sku": "BK-101"
})

// Đơn có ít nhất một item quantity >= 2.
db.orders.find({
  "items.quantity": { $gte: 2 }
})

// Đơn có item chứa thuộc tính ngôn ngữ "vi".
db.orders.find({
  "items.attributes.language": "vi"
})
```

Với mảng object, một đường dẫn như `items.sku` sẽ lần lượt kiểm tra các phần tử thích hợp của `items`.

### Khi nhiều điều kiện phải thuộc **cùng một phần tử**: `$elemMatch`

Xét hai dòng hàng:

```json
[
  { "sku": "BK-101", "quantity": 1 },
  { "sku": "BK-202", "quantity": 3 }
]
```

Truy vấn sau:

```javascript
db.orders.find({
  "items.sku": "BK-101",
  "items.quantity": { $gte: 2 }
})
```

có thể **vẫn khớp document trên**, bởi một phần tử khớp `sku`, còn phần tử khác khớp `quantity`. Hai điều kiện không tự động bị ràng buộc vào cùng một dòng hàng.

Để yêu cầu **dòng hàng có SKU BK-101 cũng phải có quantity từ 2 trở lên**, dùng `$elemMatch`:

```javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "BK-101",
      quantity: { $gte: 2 }
    }
  }
})
```

Điểm khác nhau rất quan trọng:

| Cú pháp | Điều kiện được thỏa bởi |
|---|---|
| `"items.sku": "BK-101"` và `"items.quantity": { $gte: 2 }` | Có thể là hai item **khác nhau** |
| `items: { $elemMatch: { sku: "BK-101", quantity: { $gte: 2 } } }` | Phải là **cùng một item** |

Điều này thường xuất hiện khi tìm giỏ hàng, đơn hàng, sự kiện có nhiều thuộc tính, danh sách vai trò và các mảng object khác.

## 6. Chọn trường cần trả về (projection)

Không phải truy vấn nào cũng cần đọc toàn bộ document về phía ứng dụng. Nếu màn hình danh sách chỉ hiển thị mã đơn, trạng thái, thành phố giao hàng và tổng tiền, có thể giới hạn trường đầu ra:

```javascript
db.orders.find(
  { customerId: "CUS-007" },
  {
    _id: 1,
    status: 1,
    "shipping.address.city": 1,
    "totals.grandTotal": 1
  }
)
```

Projection `1` nghĩa là đưa trường vào kết quả; `0` là bỏ trường. MongoDB thông thường không cho trộn các trường bao gồm và loại trừ trong cùng một projection, ngoại lệ thường gặp là `_id` có thể đặt `0`:

```javascript
db.orders.find(
  { status: "PAID" },
  { _id: 0, customerId: 1, "totals.grandTotal": 1 }
)
```

Projection giúp tránh truyền dư dữ liệu qua mạng và giảm lượng dữ liệu ứng dụng phải xử lý. Tuy nhiên, nó **không đảm bảo** database không đọc document gốc: điều đó còn phụ thuộc chỉ mục và kế hoạch thực thi. Nếu một chỉ mục chứa đủ các trường cần lọc và trả về, truy vấn có thể trở thành **covered query** trong những trường hợp được hỗ trợ.

## 7. Sắp xếp kết quả theo trường

Truy vấn theo trường thường kết hợp với `sort` và `limit`. Ví dụ danh sách 20 đơn mới nhất của một khách:

```javascript
db.orders
  .find(
    { customerId: "CUS-007" },
    { _id: 1, status: 1, createdAt: 1, "totals.grandTotal": 1 }
  )
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
```

`-1` nghĩa là giảm dần; `1` là tăng dần. Trường `_id` được dùng làm khóa phụ để có thứ tự xác định khi nhiều đơn trùng `createdAt`. Nếu dữ liệu nhiều, việc sắp xếp có thể tốn bộ nhớ; chỉ mục tương thích với điều kiện lọc và thứ tự sort sẽ giúp giảm chi phí.

Chẳng hạn:

```javascript
db.orders.createIndex({ customerId: 1, createdAt: -1, _id: -1 })
```

Chỉ mục này hướng đến truy vấn có điều kiện bằng trên `customerId` và sắp theo `createdAt`, `_id` giảm dần. Việc chọn chỉ mục cần dựa trên các truy vấn và mức tải thực tế; không có một chỉ mục ghép tối ưu mọi điều kiện.

## 8. Chỉ mục cho trường lồng nhau và mảng

**Index** là cấu trúc dữ liệu cho phép cơ sở dữ liệu tìm những document phù hợp mà không phải luôn quét toàn bộ collection.

### Chỉ mục cho trường lồng nhau

```javascript
db.orders.createIndex({ "shipping.address.city": 1 })

db.orders.find({
  "shipping.address.city": "Hà Nội"
})
```

Chỉ mục theo đường dẫn `shipping.address.city` hỗ trợ lọc dựa trên thành phố mà không cần đưa toàn bộ object `shipping.address` vào khóa chỉ mục.

### Chỉ mục ghép cho truy vấn thường dùng

Giả sử màn hình quản trị thường lọc theo trạng thái, thành phố và thời gian tạo:

```javascript
db.orders.createIndex({
  status: 1,
  "shipping.address.city": 1,
  createdAt: -1
})

db.orders
  .find({
    status: "PAID",
    "shipping.address.city": "Hà Nội"
  })
  .sort({ createdAt: -1 })
  .limit(20)
```

Ví dụ này đặt các điều kiện so sánh bằng ở đầu chỉ mục, sau đó đến trường phục vụ thứ tự sắp xếp. Nếu truy vấn thực tế khác về bộ lọc hoặc sort, thứ tự các trường chỉ mục có thể phải thay đổi.

### Multikey index cho mảng

Khi tạo chỉ mục trên một trường mảng trong MongoDB, cơ sở dữ liệu tạo **multikey index**: các phần tử mảng đóng góp khóa chỉ mục để tìm document.

```javascript
db.orders.createIndex({ "items.sku": 1 })

db.orders.find({ "items.sku": "BK-101" })
```

Mỗi đơn có thể chứa nhiều SKU, nhưng kết quả `find` vẫn là **document đơn hàng**, không phải một dòng kết quả riêng cho mỗi SKU. Khi phối hợp nhiều trường từ mảng trong compound index, còn có những giới hạn của multikey index và quy tắc `$elemMatch`; không nên giả định mọi tổ hợp trường mảng đều lập chỉ mục được hay được tận dụng như chỉ mục trên trường đơn.

**Đánh đổi:** index tăng tốc một số thao tác đọc nhưng chiếm thêm dung lượng và phải được cập nhật khi ghi dữ liệu. Các đường dẫn có tính biến động cao hoặc ít được truy vấn không nhất thiết cần index riêng.

### Quan sát kế hoạch truy vấn

Trong MongoDB có thể dùng `explain`:

```javascript
db.orders.find({
  "shipping.address.city": "Hà Nội",
  status: "PAID"
}).explain("executionStats")
```

Các số liệu như `totalDocsExamined`, `totalKeysExamined` và `nReturned` cho biết số document/khóa chỉ mục đã xét và số kết quả trả về. Có chỉ mục chưa chắc truy vấn nhanh nếu điều kiện ít chọn lọc, lượng kết quả lớn hoặc kế hoạch không dùng chỉ mục như dự kiến.

## 9. Cập nhật trường lồng nhau và phần tử mảng

Mô hình tài liệu cho phép thay đổi **một trường sâu bên trong document** mà không cần thay thế toàn bộ document.

### Cập nhật một trường con bằng `$set`

```javascript
db.orders.updateOne(
  { _id: "ORD-1052" },
  { $set: { "shipping.address.street": "Đường Mẫu số 2" } }
)
```

Nếu viết `$set: { shipping: { ... } }` thay vì dùng đường dẫn con, hệ thống sẽ **thay thế toàn bộ giá trị của trường `shipping`**; những trường con không được đưa vào object mới sẽ bị mất. Vì vậy, dot notation còn quan trọng trong các lệnh ghi.

### Thêm một giá trị vào mảng

```javascript
// Thêm tag nếu chưa có tag đó.
db.orders.updateOne(
  { _id: "ORD-1052" },
  { $addToSet: { tags: "verified" } }
)
```

`$addToSet` giúp tránh thêm trùng một giá trị vào mảng trong một document. Nếu nghiệp vụ cần mảng có phần tử trùng nhau và có thứ tự, `$push` phù hợp hơn. Không nên dùng mảng tăng vô hạn để chứa toàn bộ log/sự kiện nhiều năm trong một document.

### Cập nhật phần tử cụ thể trong mảng object

Ví dụ thêm ghi chú cho dòng hàng có SKU `BK-101`:

```javascript
db.orders.updateOne(
  { _id: "ORD-1052" },
  { $set: { "items.$[line].note": "Gói quà" } },
  { arrayFilters: [{ "line.sku": "BK-101" }] }
)
```

`$[line]` kết hợp `arrayFilters` xác định phần tử mảng cần cập nhật. Đây là cách biểu đạt rõ điều kiện theo thuộc tính phần tử. Không nên dựa vào vị trí cứng như `items.0` khi thứ tự mảng có thể thay đổi.

### Tính nguyên tử của một document

Trong MongoDB, thao tác ghi lên **một document** có tính nguyên tử: các trường thay đổi trong cùng một thao tác ghi không bị quan sát ở trạng thái cập nhật dở dang của riêng thao tác đó. Điều này hữu ích nếu địa chỉ, trạng thái hoặc nhiều giá trị liên quan được giữ chung một document. Nhưng khi nghiệp vụ phải cập nhật nhiều document/collection, cần cân nhắc cơ chế đảm bảo nhất quán khác, như transaction được hệ hỗ trợ hoặc thiết kế xử lý sự kiện thích hợp.

## 10. Khi nào nên nhúng dữ liệu, khi nào nên tham chiếu?

Hai lựa chọn chính trong thiết kế document model là:

- **Embedding:** đặt dữ liệu phụ thuộc bên trong document cha, chẳng hạn `orders.items` hoặc `shipping.address`.
- **Referencing:** lưu định danh liên kết sang document khác, chẳng hạn `orders.customerId = "CUS-007"`.

### Nhúng phù hợp khi...

- Dữ liệu con thường được đọc cùng document cha.
- Quan hệ có phạm vi, kích thước và tốc độ tăng trưởng có thể kiểm soát.
- Dữ liệu con có vòng đời gắn chặt với document cha.
- Muốn cập nhật một nhóm giá trị liên quan trong một lần ghi document.
- Cần lưu **snapshot lịch sử**: tên sản phẩm, đơn giá, địa chỉ tại lúc phát sinh đơn.

### Tham chiếu phù hợp khi...

- Một thực thể được nhiều document cùng dùng, ví dụ hồ sơ khách hàng hoặc danh mục sản phẩm.
- Thực thể con có vòng đời riêng, được cập nhật hoặc phân quyền độc lập.
- Danh sách con có thể tăng không giới hạn, ví dụ toàn bộ đơn của một khách trong nhiều năm.
- Truy vấn chủ yếu cần một phần dữ liệu và việc nhúng sẽ tạo document quá lớn hoặc tải nhiều dữ liệu thừa.

| Nhu cầu | Thiết kế thường hợp lý | Lý do |
|---|---|---|
| Địa chỉ giao nhận của một đơn | Nhúng vào `order.shipping` | Đọc cùng đơn; lưu ảnh chụp tại thời điểm giao |
| Các dòng hàng của một đơn thông thường | Nhúng vào `order.items` | Hiển thị và tính tổng cùng đơn; số dòng thường có giới hạn |
| Tài khoản khách hàng được hàng nghìn đơn tham chiếu | Collection `customers` riêng; trong đơn lưu `customerId` | Khách hàng có vòng đời và thao tác độc lập |
| Danh mục sản phẩm thay đổi liên tục | `products` riêng; trong đơn có `sku` và snapshot tên/giá | Tránh sửa lịch sử khi thông tin sản phẩm thay đổi |
| Toàn bộ lịch sử sự kiện của người dùng nhiều năm | Collection sự kiện riêng theo khóa phù hợp | Mảng tăng liên tục có thể làm document khổng lồ |

**Giới hạn cần nhớ:** MongoDB có giới hạn kích thước BSON document là **16 MiB**. Không nên đặt các tập dữ liệu lớn dần vô hạn vào một document. Các hệ document khác có giới hạn kích thước và hành vi cập nhật khác nhau.

### Cùng một bài toán nhưng hai cách lưu

**Mô hình nhúng:**

```json
{
  "_id": "ORD-1052",
  "items": [
    { "sku": "BK-101", "name": "Sách A", "quantity": 2 }
  ]
}
```

**Mô hình tham chiếu:**

```json
{
  "_id": "ORD-1052",
  "itemIds": ["OI-001", "OI-002"]
}
```

Với mô hình tham chiếu, cần thêm collection `order_items` chứa các document `OI-001`, `OI-002`. Cách này có thể phù hợp khi từng dòng hàng cần được xử lý độc lập ở quy mô lớn, nhưng một lần đọc đơn có thể cần thêm truy vấn hoặc kết hợp dữ liệu.

Thiết kế thực tế thường **kết hợp cả hai**: nhúng những phần gắn chặt với đơn và tham chiếu tới khách hàng/sản phẩm. Không cần chọn embedding hay referencing như một quy tắc tuyệt đối cho toàn bộ hệ thống.

## 11. Lược đồ linh hoạt không có nghĩa dữ liệu tùy tiện

Trong document database, các document có thể có bộ trường khác nhau:

```json
{ "_id": "CUS-001", "name": "An", "phone": "0900000001" }
{ "_id": "CUS-002", "name": "Bình", "preferences": { "language": "vi" } }
```

Điều này hỗ trợ dữ liệu không đồng nhất và tiến hóa phiên bản nhưng cũng tạo rủi ro:

- Trường `total` có document ghi dạng số, document khác ghi dạng chuỗi, làm lọc/tính toán sai.
- Cùng một ý nghĩa nhưng đặt tên khác nhau: `city`, `cityName`, `province`.
- Các phiên bản ứng dụng khác nhau giả định cấu trúc `shipping.address` khác nhau.
- Trường bắt buộc bị thiếu, hoặc giá trị `null` được xử lý không thống nhất.

Để kiểm soát, nhóm phát triển nên định nghĩa **hợp đồng dữ liệu (data contract)**: tên trường, kiểu, trường bắt buộc, giá trị hợp lệ, mặc định và cách nâng cấp tài liệu cũ. MongoDB hỗ trợ **schema validation** cho collection, ví dụ:

```javascript
db.createCollection("orderExamples", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["customerId", "status", "items"],
      properties: {
        customerId: { bsonType: "string" },
        status: { enum: ["PENDING", "PAID", "SHIPPED", "CANCELLED"] },
        items: { bsonType: "array" }
      }
    }
  }
})
```

Ví dụ tạo một collection minh họa riêng với các trường cơ bản; ứng dụng thực tế có thể đặt ràng buộc sâu hơn cho `items`, `shipping` và `totals`. Ngoài validation ở database, cần kiểm tra dữ liệu đầu vào tại API/service và xác định cách chuyển đổi khi thay đổi schema.

Đối với tiền tệ, nên thống nhất cách biểu diễn, chẳng hạn số nguyên VND hoặc đơn vị nhỏ nhất của đồng tiền, hay kiểu số thập phân có độ chính xác phù hợp. Tránh trộn số và chuỗi; tránh mặc nhiên dùng số thực dấu phẩy động cho tính toán tiền yêu cầu chính xác.

## 12. Tình huống thực hành: truy vấn một collection đơn hàng

Giả sử collection `orders` chứa document mẫu ở đầu bài cùng nhiều đơn khác. Hãy ánh xạ yêu cầu nghiệp vụ sang thao tác đọc:

| Yêu cầu | Truy vấn/cơ chế phù hợp |
|---|---|
| Lấy đơn theo mã | `findOne({ _id: "ORD-1052" })` |
| Tìm các đơn giao đến Hà Nội | `find({ "shipping.address.city": "Hà Nội" })` |
| Tìm đơn có ít nhất một sản phẩm ngôn ngữ Việt | `find({ "items.attributes.language": "vi" })` |
| Tìm đơn chứa SKU BK-101 với số lượng ít nhất 2 **trong cùng dòng hàng** | `$elemMatch` trên `items` |
| Hiển thị mã, trạng thái và tổng tiền | Projection |
| Hiển thị 20 đơn mới nhất theo khách hàng | Lọc `customerId`, sort `createdAt`, `_id` và `limit(20)` |

**Ví dụ kết hợp nhiều nhu cầu:** lấy tối đa 10 đơn đã thanh toán, có dòng hàng `BK-101` số lượng từ 2, giao đến Hà Nội, mới nhất trước; chỉ trả mã đơn, thời điểm tạo và tổng tiền:

```javascript
db.orders
  .find(
    {
      status: "PAID",
      "shipping.address.city": "Hà Nội",
      items: {
        $elemMatch: {
          sku: "BK-101",
          quantity: { $gte: 2 }
        }
      }
    },
    {
      _id: 1,
      createdAt: 1,
      "totals.grandTotal": 1
    }
  )
  .sort({ createdAt: -1, _id: -1 })
  .limit(10)
```

Truy vấn này minh họa bốn thao tác phối hợp: **lọc trường đơn giản**, **lọc đường dẫn lồng nhau**, **ràng buộc trong cùng phần tử mảng** và **sắp xếp/giới hạn kết quả**. Khi dữ liệu tăng, cần đo độ thường xuyên của truy vấn và xem execution plan trước khi quyết định thêm chỉ mục.

## 13. Các sai lầm thường gặp

1. **Đồng nhất document với JSON thuần.** Cú pháp hiển thị có thể giống JSON, nhưng cơ sở dữ liệu thực tế có thêm kiểu, chỉ mục, quy tắc so sánh và giao dịch riêng.
2. **So sánh object nguyên vẹn khi chỉ cần một thuộc tính.** Điều kiện bằng cho toàn embedded document thường nhạy với cấu trúc và thứ tự trường; dùng dot notation để lọc đúng trường mong muốn.
3. **Nhầm nhiều điều kiện trên mảng thành cùng một phần tử.** Truy vấn nhiều đường dẫn `items.*` có thể khớp ở các phần tử khác nhau; dùng `$elemMatch` khi cần ràng buộc cùng item.
4. **Nhúng danh sách tăng vô hạn.** Mảng giao dịch/sự kiện/đơn hàng của một khách có thể tăng đến mức document lớn, cập nhật khó và vượt giới hạn kích thước.
5. **Tưởng projection luôn tránh đọc document.** Projection giảm dữ liệu trả về, nhưng muốn tránh đọc document gốc còn cần kế hoạch truy vấn/chỉ mục thích hợp.
6. **Tưởng NoSQL không có schema.** Dù có thể ghi document khác cấu trúc, ứng dụng vẫn cần quy ước kiểu, validation, cách diễn giải trường thiếu và chiến lược nâng cấp dữ liệu.
7. **Đặt chỉ mục cho mọi trường.** Chỉ mục cần phục vụ những truy vấn thực tế; mỗi chỉ mục kéo theo chi phí dung lượng và ghi.
8. **Nhầm dữ liệu hiện tại với dữ liệu lịch sử.** Nếu đơn hàng chỉ tham chiếu đến giá sản phẩm hiện tại, sau khi giá thay đổi có thể không còn biết đơn cũ đã bán ở mức giá nào; lưu snapshot cần thiết trong document đơn hàng.

## 14. Tổng kết

Mô hình tài liệu cho phép tổ chức dữ liệu thành các **document có cấu trúc lồng nhau**, với object, array và giá trị đơn giản cùng tồn tại trong một đơn vị dữ liệu. Trong MongoDB, **dot notation** giúp truy vấn trường sâu bên trong object; truy vấn mảng hỗ trợ tìm giá trị hoặc thuộc tính của phần tử; **`$elemMatch`** dùng khi nhiều điều kiện phải cùng đúng trên một phần tử. Projection, sort và index giúp hoàn thiện đường đọc dữ liệu theo nhu cầu ứng dụng.

Thiết kế hiệu quả bắt đầu bằng câu hỏi: **thành phần nào luôn được đọc hoặc cập nhật cùng nhau, thành phần nào tăng trưởng độc lập, và ứng dụng thường lọc theo trường nào?** Từ câu trả lời đó, chọn embedding/reference, cấu trúc trường, quy tắc dữ liệu và chỉ mục phù hợp. Tính linh hoạt của document model chỉ thật sự có ích khi cấu trúc phục vụ chính xác các mẫu truy cập nghiệp vụ.
