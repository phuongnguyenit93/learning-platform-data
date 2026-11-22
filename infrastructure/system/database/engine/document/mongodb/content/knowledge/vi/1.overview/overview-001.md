# MongoDB là gì và mô hình cơ sở dữ liệu hướng document

## 1. MongoDB giải quyết bài toán gì?

MongoDB là một hệ quản trị cơ sở dữ liệu (DBMS) thuộc nhóm **NoSQL**, lưu dữ liệu theo **document** thay vì theo các hàng trong bảng như nhiều hệ quản trị quan hệ. Một document thường biểu diễn một thực thể hoặc một đối tượng nghiệp vụ, chẳng hạn sản phẩm, hồ sơ người dùng hay đơn hàng. Các trường của document có thể là giá trị đơn, đối tượng lồng nhau hoặc mảng.

Ví dụ, một ứng dụng bán hàng có thể lưu thông tin sản phẩm cùng tồn kho và thuộc tính kỹ thuật trong một document. Khi ứng dụng cần hiển thị chi tiết sản phẩm, nhiều dữ liệu liên quan đã nằm trong cùng một đơn vị lưu trữ. Đây là điểm xuất phát của **mô hình dữ liệu hướng document**: tổ chức dữ liệu theo cách ứng dụng đọc, ghi và cập nhật dữ liệu thực tế.

MongoDB không đồng nghĩa với “không có cấu trúc”. Mỗi document có cấu trúc xác định; điểm khác biệt là cấu trúc giữa các document trong cùng collection có thể linh hoạt, trong khi ứng dụng vẫn cần quy ước kiểu dữ liệu, các trường bắt buộc và cơ chế kiểm tra tính hợp lệ.

## 2. Database, collection, document và field

MongoDB tổ chức dữ liệu theo các cấp:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Database** | Không gian chứa các collection của một ứng dụng hoặc miền dữ liệu | `shop` |
| **Collection** | Tập hợp các document cùng mục đích nghiệp vụ | `products`, `orders`, `customers` |
| **Document** | Một bản ghi gồm các cặp tên trường – giá trị | Một sản phẩm `SP001` |
| **Field** | Thuộc tính bên trong document; giá trị có thể đơn hoặc phức hợp | `name`, `price`, `stock.available` |

Hình dung cấu trúc:

```text
Database: shop
├── Collection: products
│   ├── Document: sản phẩm SP001
│   └── Document: sản phẩm SP002
├── Collection: customers
│   └── Document: khách hàng KH102
└── Collection: orders
    └── Document: đơn hàng DH001
```

### Document có hình dạng như thế nào?

Trong `mongosh` (MongoDB Shell), một sản phẩm có thể được mô tả như sau:

```javascript
{
  _id: "SP001",
  name: "Bàn phím cơ",
  price: 1200000,
  categories: ["phụ kiện", "bàn phím"],
  stock: {
    available: 12,
    warehouse: "HCM"
  },
  specs: {
    switch: "Brown",
    layout: "TKL"
  },
  active: true
}
```

Ở đây:

- `_id` nhận diện duy nhất document trong collection. MongoDB tự tạo `_id` kiểu `ObjectId` nếu thao tác chèn không cung cấp trường này; ứng dụng cũng có thể tự chọn một giá trị `_id` phù hợp.
- `name`, `price`, `active` chứa giá trị đơn.
- `categories` là một **mảng**, có thể chứa nhiều giá trị.
- `stock` và `specs` là **document lồng nhau** (embedded document). Có thể truy cập trường con bằng cú pháp dấu chấm như `stock.available`.

Document thường được trình bày bằng cú pháp gần với JSON, nhưng MongoDB lưu trữ nội bộ bằng **BSON** (*Binary JSON*). BSON hỗ trợ các kiểu dữ liệu bổ sung ngoài JSON thông thường, chẳng hạn `ObjectId`, `Date`, dữ liệu nhị phân và `Decimal128`. Vì vậy cần phân biệt ví dụ trong `mongosh` với JSON thuần dùng khi trao đổi qua API. Ví dụ, `ObjectId(...)` và `ISODate(...)` là cách biểu diễn thường gặp trong shell, không phải cú pháp JSON thuần.

**Hai giới hạn cần nhớ:** tên field có phân biệt chữ hoa/chữ thường (`price` khác `Price`); mỗi document BSON có giới hạn kích thước **16 MiB**. Không nên nhồi một tập dữ liệu tăng không giới hạn vào một document.

## 3. Vì sao gọi là mô hình “hướng document”?

Trong mô hình quan hệ, một đơn hàng thường được tách thành hàng ở bảng `orders`, nhiều hàng ở bảng `order_items`, rồi liên kết bằng khóa ngoại. Với MongoDB, ta có thể lưu các dòng hàng trực tiếp trong document đơn hàng nếu chúng thường được đọc cùng nhau.

Ví dụ đơn hàng trong `orders`:

```javascript
{
  _id: "DH001",
  customerId: "KH102",
  status: "NEW",
  shippingAddress: {
    city: "Hồ Chí Minh",
    district: "Quận 3"
  },
  items: [
    { productId: "SP001", name: "Bàn phím cơ", quantity: 2, unitPrice: 1200000 },
    { productId: "SP002", name: "Chuột không dây", quantity: 1, unitPrice: 650000 }
  ],
  totalAmount: 3050000,
  createdAt: ISODate("2026-01-05T09:00:00Z")
}
```

Document này chứa **giá trị đơn** (`status`), **đối tượng lồng nhau** (`shippingAddress`) và **mảng đối tượng** (`items`). Mỗi dòng hàng có giá và tên tại thời điểm đặt hàng, giúp đơn hàng giữ nguyên lịch sử ngay cả khi thông tin sản phẩm trong `products` thay đổi về sau.

Mô hình hướng document có ba đặc điểm cốt lõi:

1. **Nhóm dữ liệu thường đi cùng nhau.** Một truy vấn lấy đơn hàng có thể trả về luôn danh sách dòng hàng và địa chỉ giao hàng.
2. **Cấu trúc có thể lồng nhau.** Một thực thể phức hợp không nhất thiết bị trải ra nhiều bảng.
3. **Thiết kế dựa trên cách truy cập.** Cùng là quan hệ khách hàng–đơn hàng, việc nhúng hay tham chiếu phụ thuộc vào số lượng đơn, tần suất thay đổi và các truy vấn cần hỗ trợ.

Không nên suy ra rằng “MongoDB luôn lưu mọi thứ trong một document”. Document quá lớn, mảng tăng vô hạn hay sao chép dữ liệu khó đồng bộ thường là dấu hiệu cần điều chỉnh mô hình.

## 4. Thao tác cơ bản với document

Các ví dụ dưới đây dùng `mongosh` và database thử nghiệm `shop`. Các câu lệnh minh họa cách làm việc với collection `products`; chúng không phải mã chạy trên dữ liệu sản xuất.

### 4.1. Tạo và chèn dữ liệu

```javascript
use("shop");

db.products.insertMany([
  {
    _id: "SP001",
    name: "Bàn phím cơ",
    price: 1200000,
    categories: ["phụ kiện", "bàn phím"],
    stock: { available: 12, warehouse: "HCM" },
    specs: { switch: "Brown", layout: "TKL" },
    active: true
  },
  {
    _id: "SP002",
    name: "Chuột không dây",
    price: 650000,
    categories: ["phụ kiện", "chuột"],
    stock: { available: 8, warehouse: "HN" },
    specs: { connection: "2.4GHz" },
    active: true
  }
]);
```

`insertOne()` thêm một document; `insertMany()` thêm nhiều document. Collection có thể được tạo tường minh hoặc xuất hiện khi lần đầu chèn dữ liệu, tùy thao tác và cấu hình.

Hai document trên cùng thuộc collection `products`, nhưng `specs` có các trường khác nhau vì đặc tính của bàn phím và chuột khác nhau. Điều này thể hiện tính linh hoạt của cấu trúc document.

### 4.2. Đọc và lọc dữ liệu

```javascript
// Sản phẩm đang còn hàng, thuộc nhóm "phụ kiện"
db.products.find(
  { "stock.available": { $gt: 0 }, categories: "phụ kiện" },
  { _id: 0, name: 1, price: 1 }
);

// Tìm chính xác một sản phẩm theo _id
db.products.findOne({ _id: "SP001" });
```

`find()` nhận **bộ lọc** và tùy chọn **projection** để chọn trường trả về. Toán tử `$gt` có nghĩa “lớn hơn”; cú pháp `"stock.available"` truy cập trường lồng nhau. Điều kiện `categories: "phụ kiện"` có thể khớp với một phần tử của mảng `categories`.

### 4.3. Cập nhật và xóa

```javascript
// Giảm tồn kho một đơn vị và ghi nhận lần cập nhật
db.products.updateOne(
  { _id: "SP001" },
  {
    $inc: { "stock.available": -1 },
    $set: { updatedAt: new Date() }
  }
);

// Xóa một bản ghi thử nghiệm
db.products.deleteOne({ _id: "SP002" });
```

`$inc` thay đổi giá trị số, `$set` đặt giá trị trường. `updateOne()` và `deleteOne()` tác động đến một document phù hợp bộ lọc. Khi cần cập nhật nhiều document, MongoDB cũng có `updateMany()`; phải chọn bộ lọc cẩn thận để tránh ảnh hưởng ngoài phạm vi mong muốn.

**Tính nguyên tử ở mức document:** một thao tác ghi đơn lẻ lên một document được thực hiện nguyên tử, kể cả khi thao tác thay đổi nhiều field hoặc phần tử lồng nhau của document đó. Đây là lợi thế khi các dữ liệu cần cập nhật cùng lúc đã được nhóm phù hợp trong một document. Nếu nghiệp vụ phải thay đổi nhiều document như một đơn vị, cần thiết kế thêm giao dịch hoặc cách phối hợp khác.

## 5. Hai cách biểu diễn quan hệ: nhúng và tham chiếu

Trong MongoDB, quyết định mô hình hóa quan trọng là **embedding** (nhúng document) và **referencing** (lưu khóa tham chiếu). Có thể kết hợp cả hai trong cùng hệ thống.

### 5.1. Nhúng document (embedding)

Nhúng nghĩa là đặt dữ liệu phụ thuộc bên trong document cha:

```javascript
{
  _id: "KH102",
  name: "An",
  contact: {
    email: "an@example.test",
    phone: "0900000000"
  },
  addresses: [
    { label: "Nhà", city: "Hồ Chí Minh" },
    { label: "Cơ quan", city: "Đà Nẵng" }
  ]
}
```

Nhúng phù hợp khi dữ liệu có quan hệ sở hữu rõ ràng, thường được đọc cùng document cha và số lượng phần tử được kiểm soát. Ví dụ, một hồ sơ có một cấu hình liên hệ hoặc một số địa chỉ thường dễ xử lý khi nhúng.

Ưu điểm: ứng dụng có thể đọc thông tin liên quan bằng ít truy vấn hơn; cập nhật nhiều trường trong cùng document được nguyên tử. Đổi lại, nếu dữ liệu nhúng trở nên lớn, tăng mãi hoặc bị chỉnh sửa đồng thời với tần suất cao, document có thể cồng kềnh và gây khó khăn trong quản lý.

### 5.2. Tham chiếu (referencing)

Tham chiếu nghĩa là lưu định danh của document khác và tra cứu riêng khi cần:

```javascript
// Collection customers
{ _id: "KH102", name: "An", email: "an@example.test" }

// Collection orders
{ _id: "DH001", customerId: "KH102", totalAmount: 3050000 }
{ _id: "DH002", customerId: "KH102", totalAmount: 780000 }
```

Tham chiếu hợp lý khi một thực thể có nhiều bản ghi con và số lượng tăng liên tục, khi dữ liệu được dùng chung hoặc cần vòng đời cập nhật độc lập. Chẳng hạn, không nên mặc định nhét toàn bộ lịch sử hàng triệu đơn hàng vào document khách hàng. Các đơn hàng có thể nằm ở collection riêng và có chỉ mục theo `customerId`.

MongoDB cho phép truy vấn nhiều collection và có toán tử aggregation `$lookup` để kết hợp dữ liệu tương tự một số trường hợp `JOIN`. Tuy nhiên, khóa tham chiếu do ứng dụng lưu không tự trở thành ràng buộc khóa ngoại giống cơ sở dữ liệu quan hệ. Ứng dụng phải quản lý tính hợp lệ của tham chiếu theo thiết kế của mình.

### 5.3. Chọn cách nào?

| Câu hỏi thiết kế | Thường nghiêng về nhúng | Thường nghiêng về tham chiếu |
| --- | --- | --- |
| Có thường đọc cha và con cùng lúc? | Có | Không nhất thiết |
| Số lượng bản ghi con có giới hạn rõ? | Có | Không, có thể tăng lâu dài |
| Dữ liệu con cần cập nhật độc lập? | Ít khi | Thường xuyên |
| Một bản ghi con được nhiều cha dùng chung? | Hiếm | Phổ biến |
| Cần cập nhật các trường cùng một thao tác nguyên tử? | Rất hữu ích | Có thể cần giao dịch nếu qua nhiều document |

Ví dụ ứng dụng bán hàng có thể **tham chiếu** `orders.customerId` đến khách hàng và **nhúng** `orders.items` vào mỗi đơn hàng. Đây là lựa chọn dựa trên hành vi truy vấn, không phải quy tắc cố định cho mọi ứng dụng.

### 5.4. Phi chuẩn hóa có chủ đích

Với dữ liệu hướng document, đôi khi ta sao chép một vài trường để tối ưu truy vấn hoặc giữ bản chụp lịch sử. Ví dụ đơn hàng lưu `unitPrice` và `name` của sản phẩm tại thời điểm mua, dù `productId` vẫn trỏ đến sản phẩm hiện tại.

Việc sao chép này có thể đúng về nghiệp vụ: giá đơn hàng đã chốt không nên thay đổi vì giá niêm yết hôm nay thay đổi. Nhưng nếu sao chép một trường phải luôn đồng nhất ở nhiều nơi, cần xác định dữ liệu nguồn, thời điểm đồng bộ và cách xử lý khi cập nhật thất bại.

## 6. Schema linh hoạt không có nghĩa là bỏ qua ràng buộc

MongoDB cho phép các document cùng collection không bắt buộc có bộ field giống hệt nhau. Điều này hữu ích khi nhiều loại sản phẩm có các thuộc tính riêng hoặc ứng dụng phải phát triển dần phiên bản dữ liệu.

Ví dụ trong cùng collection:

```javascript
{ _id: "SP001", name: "Bàn phím", specs: { layout: "TKL" } }
{ _id: "SP002", name: "Chuột", specs: { dpi: 1600 } }
```

Tuy nhiên, một ứng dụng thực tế nên quy định rõ các field chung, kiểu dữ liệu và giá trị hợp lệ. Có thể thực hiện bằng kiểm tra ở tầng ứng dụng và **schema validation** của MongoDB. Chẳng hạn, collection sản phẩm có thể yêu cầu `name` là chuỗi, `price` là số không âm:

```javascript
db.createCollection("validatedProducts", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name", "price"],
      properties: {
        name: { bsonType: "string" },
        price: {
          bsonType: ["int", "long", "double", "decimal"],
          minimum: 0
        }
      }
    }
  }
});
```

`validatedProducts` chỉ là tên collection minh họa riêng cho quy tắc validation. Các quy tắc chi tiết cần khớp với kiểu dữ liệu mà ứng dụng thật sự sử dụng; ví dụ tiền tệ có thể cần cách biểu diễn chính xác như `Decimal128` hoặc số nguyên ở đơn vị nhỏ nhất.

Một số nguyên tắc schema thực tế:

- Thống nhất tên field và kiểu của cùng một thuộc tính; tránh nơi lưu `price` là số, nơi khác lại là chuỗi `"1200000"`.
- Phân biệt field không tồn tại với field có giá trị `null`, vì truy vấn và logic ứng dụng có thể xử lý chúng khác nhau.
- Đặt quy tắc cho trường bắt buộc và phiên bản dữ liệu khi thay đổi cấu trúc qua nhiều lần phát hành.
- Tránh mảng tăng không giới hạn trong một document; tách collection hoặc phân trang dữ liệu con khi cần.

## 7. Truy vấn, chỉ mục và aggregation

Thiết kế document chỉ là một nửa bài toán; nửa còn lại là cách ứng dụng tìm dữ liệu. Một collection nhiều document có thể được quét để lọc kết quả, nhưng với các truy vấn phổ biến nên cân nhắc **index**.

Ví dụ truy vấn sản phẩm theo danh mục và tồn kho:

```javascript
db.products.find({
  categories: "phụ kiện",
  "stock.available": { $gt: 0 }
});

// Chỉ mục phục vụ mẫu truy vấn trên
db.products.createIndex({ categories: 1, "stock.available": 1 });
```

Chỉ mục giúp hệ quản trị có đường tìm kiếm phù hợp thay vì luôn xem mọi document. Trường `categories` là mảng, nên chỉ mục chứa trường này có thể trở thành **multikey index**. Mỗi chỉ mục có chi phí lưu trữ và chi phí bảo trì khi ghi; vì thế cần chọn dựa trên truy vấn thực tế, không tạo chỉ mục cho mọi field một cách máy móc. Có thể dùng `explain()` để quan sát kế hoạch truy vấn.

Ngoài truy vấn đơn giản, **aggregation pipeline** xử lý dữ liệu theo chuỗi bước như lọc, tách mảng, nhóm và sắp xếp:

```javascript
db.products.aggregate([
  { $match: { active: true } },
  { $unwind: "$categories" },
  {
    $group: {
      _id: "$categories",
      productCount: { $sum: 1 },
      averagePrice: { $avg: "$price" }
    }
  },
  { $sort: { productCount: -1 } }
]);
```

Pipeline trên lấy sản phẩm đang hoạt động, tách từng danh mục trong mảng, tính số sản phẩm và giá trung bình theo danh mục, sau đó sắp xếp theo số lượng giảm dần. Nó minh họa rằng MongoDB vừa lưu document, vừa hỗ trợ biến đổi và tổng hợp dữ liệu có cấu trúc.

## 8. MongoDB so với cơ sở dữ liệu quan hệ

| Khía cạnh | MongoDB | Cơ sở dữ liệu quan hệ (ví dụ PostgreSQL, MySQL) |
| --- | --- | --- |
| Đơn vị dữ liệu điển hình | Document BSON | Hàng trong bảng |
| Tổ chức | Database → collection → document | Database/schema → table → row |
| Thuộc tính lồng nhau | Document và mảng là cấu trúc tự nhiên | Thường biểu diễn bằng bảng liên quan; một số hệ có kiểu JSON |
| Schema | Linh hoạt, có thể đặt validation | Thường định nghĩa cột và ràng buộc tường minh |
| Liên kết dữ liệu | Nhúng, tham chiếu, `$lookup` | Khóa ngoại và `JOIN` |
| Trọng tâm mô hình hóa | Mẫu truy cập và ranh giới document | Quan hệ, chuẩn hóa, ràng buộc dữ liệu |

Đây là sự khác nhau về cách mô hình hóa thường gặp, không phải bảng xếp hạng hệ nào “mạnh hơn”. Cơ sở dữ liệu quan hệ hiện đại cũng hỗ trợ JSON; MongoDB cũng hỗ trợ index, aggregation và giao dịch đa document. Chọn hệ quản trị cần dựa trên tính chất dữ liệu, tính nhất quán, kiểu truy vấn, năng lực vận hành và yêu cầu nghiệp vụ.

## 9. Tính nhất quán, khả năng mở rộng và vận hành

MongoDB thường được nhắc cùng các khả năng sau; cần phân biệt chúng với bản thân mô hình document:

**Atomicity và transaction.** Thay đổi một document có tính nguyên tử. Khi nghiệp vụ cần nhiều document thay đổi cùng thành công hoặc cùng thất bại, MongoDB hỗ trợ giao dịch đa document trong các triển khai phù hợp. Giao dịch có chi phí xử lý; thiết kế document tốt có thể giảm số giao dịch phải dùng nhưng không loại bỏ mọi nhu cầu giao dịch.

**Replication.** Một *replica set* duy trì các bản sao dữ liệu giữa nhiều thành viên để tăng khả năng sẵn sàng và hỗ trợ phục hồi khi một node gặp sự cố. Replication không thay thế chính sách backup hay kiểm thử khôi phục dữ liệu.

**Sharding.** Khi cần phân phối khối lượng dữ liệu và tải xử lý, MongoDB có thể chia dữ liệu của collection thành các phần trên nhiều shard. Việc chọn *shard key* ảnh hưởng đến phân phối dữ liệu và hiệu quả truy vấn. Không phải mọi ứng dụng nhỏ đều cần sharding.

**Read concern và write concern.** Ứng dụng có thể cấu hình mức bảo đảm phù hợp cho đọc và ghi. Khi cần độ bền và tính nhất quán cụ thể, phải hiểu cấu hình triển khai và các lựa chọn này, thay vì suy luận chỉ từ việc dữ liệu nằm trong document.

Các khía cạnh trên giúp xây dựng hệ thống chạy ổn định, nhưng không thay thế các quyết định đầu tiên: document chứa gì, dữ liệu nào cần tách, ứng dụng sẽ truy vấn như thế nào và field nào cần được kiểm soát.

## 10. Tình huống phù hợp và sai lầm thường gặp

Mô hình hướng document thường thuận lợi cho hồ sơ, nội dung, catalog có thuộc tính biến thiên, dữ liệu cấu hình và các đối tượng nghiệp vụ có nhiều thông tin lồng nhau. Ví dụ một ứng dụng quản lý khóa học có thể lưu một bài học cùng các mục nội dung và metadata trong một document nếu kích thước có giới hạn và chúng thường được tải cùng lúc.

Ngược lại, với dữ liệu có rất nhiều mối quan hệ phức tạp, ràng buộc toàn vẹn liên bảng chặt chẽ hoặc các phép kết hợp dữ liệu nặng, cần đánh giá kỹ giữa thiết kế MongoDB và một hệ quan hệ. Ngay cả khi dùng MongoDB, đôi khi tham chiếu và nhiều collection vẫn là cách tổ chức đúng.

Những lỗi mô hình hóa dễ gặp:

| Cách làm | Vấn đề | Hướng cải thiện |
| --- | --- | --- |
| Đưa mọi đơn hàng vào mảng `customer.orders` | Mảng tăng mãi, document phình lớn | Tạo collection `orders` riêng, truy vấn theo `customerId` |
| Sao chép thông tin phải luôn đồng nhất khắp nơi | Khó cập nhật, dễ lệch dữ liệu | Xác định nguồn dữ liệu chuẩn và quy tắc đồng bộ |
| Cho cùng field nhiều kiểu dữ liệu tùy ý | Logic truy vấn, lọc và thống kê phức tạp | Chuẩn hóa kiểu, thêm validation và kế hoạch chuyển đổi |
| Tạo index cho tất cả field | Tốn dung lượng, làm tăng chi phí ghi | Dựa vào truy vấn quan trọng và đo bằng `explain()` |
| Coi tham chiếu là khóa ngoại tự kiểm soát | Có thể tồn tại tham chiếu không hợp lệ | Kiểm tra ở tầng ứng dụng và trong quy trình ghi/xóa |
| Thiết kế từ sơ đồ dữ liệu mà bỏ qua truy vấn | Phải đọc quá nhiều collection hoặc dữ liệu dư thừa | Liệt kê các thao tác đọc/ghi chủ yếu trước khi chọn nhúng hoặc tham chiếu |

Một cách bắt đầu thiết kế cho dự án thực tế là viết ra ba truy vấn quan trọng nhất, ba thao tác cập nhật phổ biến nhất, kích thước dữ liệu dự kiến và quan hệ nào tăng không giới hạn. Từ đó xác định ranh giới document, các tham chiếu và các chỉ mục cần thiết. Sau khi có dữ liệu và lưu lượng đại diện, đo lại truy vấn để điều chỉnh mô hình.

## 11. Tự kiểm tra mức độ hiểu

1. Một document đơn hàng chứa `items` là mảng các sản phẩm đã mua. Điều gì khiến việc nhúng `items` hợp lý, và trong tình huống nào nên cân nhắc tách chúng ra?
2. Vì sao hai sản phẩm có thể có `specs` khác nhau nhưng vẫn nằm trong collection `products`? Điều gì cần thống nhất giữa chúng?
3. Khóa `customerId` trong `orders` khác ràng buộc khóa ngoại tự động ở cơ sở dữ liệu quan hệ như thế nào?
4. Khi câu lệnh `find()` theo `stock.available` trở nên chậm, cần xem xét những yếu tố nào trước khi thêm index?
5. Nếu cần cập nhật cùng lúc nhiều document và không chấp nhận trạng thái cập nhật dở, tính nguyên tử của một document đã đủ chưa?

Sau khi trả lời được các câu hỏi này, người học có thể chuyển từ việc nhìn MongoDB như “nơi lưu JSON” sang việc thiết kế dữ liệu đúng theo **ranh giới document, quan hệ và mẫu truy cập** của ứng dụng.
