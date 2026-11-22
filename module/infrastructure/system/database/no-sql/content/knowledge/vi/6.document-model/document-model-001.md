# Tài liệu, collection, trường và cấu trúc lồng nhau trong NoSQL

Trong **mô hình dữ liệu tài liệu** (*document model*), dữ liệu được tổ chức thành các **tài liệu** (*documents*) có cấu trúc gần với đối tượng mà ứng dụng xử lý. Một tài liệu thường chứa các **trường** (*fields*) đơn giản và các cấu trúc phức hợp như đối tượng lồng nhau hoặc mảng. Nhiều tài liệu liên quan được quản lý trong một **collection**.

Cách tổ chức này xuất hiện trong các document database như MongoDB và ở những hệ lưu dữ liệu dạng tài liệu khác. Dù thường được minh họa bằng JSON, chi tiết về kiểu dữ liệu, cú pháp truy vấn, khả năng cập nhật và giới hạn lưu trữ thay đổi theo sản phẩm.

Bài học sẽ đi từ bốn khái niệm nền tảng **document → collection → field → nested structure**, rồi liên hệ chúng với truy vấn, cập nhật, lập chỉ mục và thiết kế dữ liệu thực tế.

## 1. Từ đối tượng nghiệp vụ đến tài liệu

Giả sử một ứng dụng bán hàng cần lưu đơn hàng. Đơn hàng có mã, khách hàng, địa chỉ giao hàng và các dòng sản phẩm. Thay vì chia mọi thuộc tính thành nhiều bảng riêng như một thiết kế quan hệ chuẩn hóa, document database cho phép biểu diễn những phần thường được sử dụng cùng nhau trong một đối tượng lồng nhau.

~~~json
{
  "_id": "order-1001",
  "customerId": "usr-007",
  "status": "PAID",
  "placedAt": "2026-11-14T08:00:00Z",
  "currency": "VND",
  "shipping": {
    "recipient": "Mai",
    "address": {
      "street": "12 Duong A",
      "city": "Da Nang",
      "country": "VN"
    },
    "method": "STANDARD"
  },
  "items": [
    {
      "lineId": "line-1",
      "sku": "sku-book-01",
      "name": "Sach A",
      "quantity": 2,
      "unitPrice": 100000
    },
    {
      "lineId": "line-2",
      "sku": "sku-pen-02",
      "name": "But B",
      "quantity": 3,
      "unitPrice": 50000
    }
  ],
  "totalAmount": 350000
}
~~~

Đây là **một tài liệu đơn hàng**, dù nó có nhiều trường và hai dòng sản phẩm. Các đối tượng nằm trong `shipping` và `items` là **cấu trúc lồng nhau**, chưa mặc nhiên trở thành những tài liệu độc lập có khóa riêng trong collection khác.

Sơ đồ phân cấp của tài liệu:

~~~text
Tài liệu đơn hàng (_id: order-1001)
├── customerId: "usr-007"               [trường chuỗi]
├── status: "PAID"                       [trường chuỗi]
├── placedAt: "2026-11-14T08:00:00Z"    [trường thời gian biểu diễn bằng chuỗi]
├── currency: "VND"                      [trường chuỗi]
├── shipping                            [đối tượng lồng nhau]
│   ├── recipient: "Mai"
│   ├── address                          [đối tượng lồng thêm một cấp]
│   │   ├── street: "12 Duong A"
│   │   ├── city: "Da Nang"
│   │   └── country: "VN"
│   └── method: "STANDARD"
├── items                               [mảng]
│   ├── phần tử 0                        [đối tượng dòng hàng]
│   │   ├── lineId, sku, name
│   │   └── quantity, unitPrice
│   └── phần tử 1                        [đối tượng dòng hàng]
│       ├── lineId, sku, name
│       └── quantity, unitPrice
└── totalAmount: 350000                  [trường số]
~~~

Giá trị `placedAt` được viết dưới dạng chuỗi ISO 8601 để ví dụ giữ đúng cú pháp JSON. Khi triển khai, nên dùng **kiểu ngày giờ gốc** của cơ sở dữ liệu nếu cần so sánh thời gian, tính khoảng cách hoặc lập chỉ mục theo thời gian. Ví dụ trong MongoDB có thể dùng BSON Date thay vì chuỗi.

## 2. Bốn khái niệm và mối quan hệ

| Khái niệm | Ý nghĩa | Ví dụ | Điều dễ nhầm |
| --- | --- | --- | --- |
| **Document** | Đơn vị dữ liệu logic, chứa các trường và giá trị của một đối tượng | Tài liệu đơn hàng `order-1001` | Một document không tương đương với một file vật lý |
| **Collection** | Tập hợp có tên gồm các document được quản lý và truy vấn trong cùng một phạm vi | `orders`, `users`, `products` | Collection không tự động có cùng mọi ràng buộc như bảng quan hệ |
| **Field** | Thuộc tính có tên trong document hoặc đối tượng lồng nhau | `status`, `shipping.method` | Field không nhất thiết chỉ chứa chuỗi hoặc số |
| **Nested structure** | Đối tượng hoặc mảng nằm bên trong document, có thể chứa nhiều cấp | `shipping.address`, `items[]` | Lồng nhau không đồng nghĩa với có quan hệ khóa ngoại |

Một document thường được nhận diện bằng khóa riêng. Nhiều document cùng loại thường được đặt trong một collection. Mỗi document chứa tập field riêng; giá trị field có thể là dữ liệu đơn giản hoặc một cấu trúc lồng nhau.

~~~text
Database: commerce
│
├── Collection: users
│   ├── Document: usr-007
│   │   ├── name
│   │   └── contact
│   │       ├── email
│   │       └── phone
│   └── Document: usr-008
│
├── Collection: products
│   ├── Document: sku-book-01
│   └── Document: sku-pen-02
│
└── Collection: orders
    ├── Document: order-1001
    │   ├── customerId
    │   ├── shipping
    │   │   └── address
    │   └── items[]
    │       ├── item 0
    │       └── item 1
    └── Document: order-1002
~~~

Sơ đồ mô tả **tổ chức logic**. Nó không nói tài liệu nằm trên đĩa nào, được lưu thành bao nhiêu tệp, có bao nhiêu bản sao hay collection được phân mảnh ra sao.

## 3. Document: đơn vị dữ liệu có cấu trúc

### 3.1. Document khác hàng của bảng quan hệ ở điểm nào?

Trong một bảng quan hệ điển hình, các hàng tuân theo các cột được khai báo trong lược đồ. Trong document database, mỗi tài liệu thường mang theo các cặp tên trường–giá trị, nên hai tài liệu cùng collection có thể có tập trường khác nhau nếu hệ và chính sách validation cho phép.

Ví dụ hai tài liệu khách hàng:

~~~json
{
  "_id": "usr-007",
  "name": "Mai",
  "contact": { "email": "mai@example.invalid" },
  "preferences": { "language": "vi" }
}
~~~

~~~json
{
  "_id": "usr-008",
  "name": "An",
  "contact": {
    "email": "an@example.invalid",
    "phone": "+84000000001"
  },
  "loyaltyLevel": "GOLD"
}
~~~

Tài liệu `usr-008` có `contact.phone` và `loyaltyLevel` mà tài liệu `usr-007` không có. Điều này minh họa **tính linh hoạt của schema**. Tuy nhiên, ứng dụng vẫn phải biết những field nào bắt buộc, field nào tùy chọn và các kiểu giá trị hợp lệ. “Flexible schema” không có nghĩa “không cần hợp đồng dữ liệu”.

### 3.2. Các kiểu dữ liệu thường gặp

Một field không chỉ chứa văn bản. Các kiểu thường gặp gồm:

| Nhóm kiểu | Ví dụ biểu diễn bằng JSON | Ý nghĩa |
| --- | --- | --- |
| String | `"PAID"` | Trạng thái, mã, tên hiển thị |
| Number | `350000`, `4.5` | Số lượng, giá trị đo |
| Boolean | `true`, `false` | Cờ bật/tắt |
| Null | `null` | Giá trị được thể hiện rõ là null |
| Object | `{"city": "Da Nang"}` | Nhóm thuộc tính liên quan |
| Array | `["RED", "BLUE"]` | Tập phần tử có thứ tự |
| Date/time | `"2026-11-14T08:00:00Z"` | Biểu diễn thời gian trong JSON; database có thể có kiểu date gốc |
| Binary, decimal, ID chuyên dụng | Không có biểu diễn nguyên thủy thống nhất trong JSON | Thường là kiểu mở rộng của sản phẩm |

JSON chuẩn có tập kiểu giới hạn. **MongoDB lưu BSON**, có thêm kiểu như `ObjectId`, `Date` và `Decimal128`. Một số hệ document khác lưu JSON hoặc một biểu diễn nội bộ khác. Khi trao đổi qua API JSON, thông tin kiểu BSON có thể cần biểu diễn bằng **Extended JSON** hoặc một định dạng chuyển đổi phù hợp.

**Số tiền** nên dùng số nguyên theo đơn vị nhỏ nhất (ví dụ VND) hoặc kiểu thập phân chính xác theo yêu cầu nghiệp vụ. Không mặc nhiên dùng số thực dấu phẩy động cho tính toán tài chính.

### 3.3. Khóa định danh tài liệu

Mỗi tài liệu cần một cách nhận diện. Trong MongoDB, trường `_id` xác định duy nhất tài liệu **trong một collection**. Ví dụ:

~~~text
orders:
    _id = "order-1001"
    _id = "order-1002"

users:
    _id = "usr-007"
    _id = "usr-008"
~~~

Hai collection khác nhau có thể có giá trị `_id` giống nhau vì phạm vi duy nhất của MongoDB là collection. Tên trường định danh và quy tắc duy nhất không giống nhau ở mọi document database.

Phân biệt:

- **Document ID**: nhận diện một tài liệu.
- **Business key**: mã có ý nghĩa nghiệp vụ như số đơn hàng hoặc email; có thể hoặc không trùng document ID.
- **Partition/shard key**: dùng để phân phối tài liệu tới phần dữ liệu hoặc máy thích hợp trong hệ phân tán; có thể khác document ID.
- **Reference ID**: giá trị nằm trong tài liệu A để trỏ tới thực thể ở tài liệu B, chẳng hạn `customerId`.

Khi ứng dụng thay đổi email của người dùng, một document ID độc lập và ổn định sẽ giúp các đơn hàng không phải sửa chỉ vì email đổi.

## 4. Collection: nhóm tài liệu và ranh giới quản lý

**Collection** là không gian đặt tên và quản lý một tập document. Khi một ứng dụng nói “lấy những đơn hàng đang chờ xử lý”, nó thường truy vấn collection `orders` rồi lọc theo field `status`.

Ví dụ MongoDB:

~~~javascript
// Chọn database "commerce" trong mongosh.
use commerce

// Đếm những tài liệu đơn hàng có trạng thái PENDING.
db.orders.countDocuments({ status: "PENDING" })

// Đọc một người dùng bằng ID.
db.users.findOne({ _id: "usr-007" })
~~~

Với mô hình minh họa, `users`, `products` và `orders` là ba collection. Chúng thường được tách vì vòng đời, cách truy vấn, ràng buộc, chỉ mục và quyền truy cập khác nhau.

### Collection và bảng SQL: gần nhau nhưng không giống nhau

| Khía cạnh | Collection trong document database | Bảng trong RDBMS điển hình |
| --- | --- | --- |
| Đơn vị chứa | Document | Row |
| Hình dạng bản ghi | Có thể khác tập trường giữa các document, tùy validator | Tuân theo danh sách cột và ràng buộc của bảng |
| Cấu trúc con | Có thể nhúng object/array trực tiếp | Thường dùng bảng con và khóa ngoại; một số RDBMS cũng hỗ trợ JSON |
| Quan hệ | Thường biểu diễn bằng nhúng hoặc ID tham chiếu ở tầng ứng dụng | Có cơ chế khóa ngoại và JOIN được định nghĩa rõ |
| Chỉ mục | Có thể đánh chỉ mục field và đường dẫn lồng nhau | Đánh chỉ mục cột, biểu thức, JSON tùy hệ |
| Phân phối | Collection có thể được phân mảnh/replicate tùy sản phẩm | RDBMS cũng có thể partition/replicate |

Cần tránh hai suy luận cực đoan: **collection không phải bản sao chính xác của SQL table**, và **document database không cấm schema, join hoặc transaction**. Khả năng cụ thể phụ thuộc từng hệ và cách cấu hình.

### Một collection có cần lưu mọi loại đối tượng không?

Không. Đặt tất cả người dùng, đơn hàng, sản phẩm vào cùng một collection và thêm field `type` chỉ để phân biệt sẽ khiến quy tắc truy vấn, indexing, validation và quyền truy cập khó quản lý. Tuy nhiên, một collection chứa một số biến thể cùng họ đối tượng là hoàn toàn hợp lý nếu có hợp đồng dữ liệu rõ ràng.

Ví dụ `payments` có thể chứa thanh toán thẻ và chuyển khoản, nhưng cần có field phân loại như `method`, hợp đồng các field chung và quy tắc riêng cho từng biến thể.

## 5. Field: thuộc tính, giá trị và đường dẫn

**Field** là một thuộc tính có tên. Trong document:

~~~json
{
  "_id": "order-1001",
  "status": "PAID",
  "shipping": {
    "method": "STANDARD",
    "address": {
      "city": "Da Nang",
      "country": "VN"
    }
  }
}
~~~

- `status` là field ở cấp gốc.
- `shipping` là field cấp gốc có giá trị là object.
- `method` là field bên trong `shipping`.
- `address` là field bên trong `shipping`, tiếp tục chứa object.
- `city` và `country` là field ở cấp sâu hơn.

**Đường dẫn trường** (*field path*) là cách biểu diễn vị trí một field trong cây dữ liệu. Trong MongoDB, cú pháp dấu chấm biểu diễn field lồng nhau, ví dụ:

~~~text
status
shipping.method
shipping.address.city
shipping.address.country
~~~

Đường dẫn `shipping.address.city` có nghĩa “đọc field `city` bên trong object `address`, mà `address` nằm trong object `shipping`”. Đó là một phép truy cập cấu trúc, không phải quan hệ JOIN.

### 5.1. Field vắng mặt khác field có giá trị null

Hai document sau không có ý nghĩa giống nhau:

~~~json
{ "_id": "usr-101", "nickname": null }
~~~

~~~json
{ "_id": "usr-102" }
~~~

Tài liệu đầu có field `nickname` với giá trị `null`; tài liệu sau **không có field** `nickname`. Ngoài ra còn trường hợp field có chuỗi rỗng `""` hoặc mảng rỗng `[]`.

Trong MongoDB:

~~~javascript
// Chỉ tìm tài liệu thiếu field nickname.
db.users.find({ nickname: { $exists: false } })

// Tìm tài liệu có nickname với giá trị BSON null rõ ràng.
db.users.find({ nickname: { $type: "null" } })

// Lưu ý: truy vấn sau khớp cả null lẫn field vắng mặt.
db.users.find({ nickname: null })
~~~

Khác biệt này ảnh hưởng đến validation, logic cập nhật và báo cáo. Ví dụ “chưa cung cấp số điện thoại”, “đã xác nhận không có số điện thoại” và “đang tải dữ liệu” có thể là ba trạng thái nghiệp vụ khác nhau. Không nên mặc định tất cả tương đương `null`.

### 5.2. Tên field là một phần hợp đồng dữ liệu

Ứng dụng cần thống nhất quy tắc đặt tên, kiểu, đơn vị đo và ý nghĩa của từng field:

| Field | Hợp đồng nên nêu rõ |
| --- | --- |
| `totalAmount` | Đơn vị tiền là gì, số nguyên hay decimal, đã gồm thuế/chuyển phát chưa? |
| `status` | Các giá trị hợp lệ và chuyển trạng thái được phép |
| `placedAt` | UTC hay múi giờ địa phương; dùng kiểu Date gốc hay string |
| `customerId` | Trỏ tới ID chuẩn của collection nào; có tồn tại tenant scope không? |
| `items.quantity` | Số nguyên dương hay cho phép số lẻ? |
| `shipping.address.country` | Mã ISO hay tên quốc gia tự do? |

Nếu một bản ghi ghi `amount` là VND còn bản ghi khác ghi USD mà không có `currency`, tính tổng sẽ sai dù JSON hoàn toàn hợp lệ về mặt cú pháp.

## 6. Cấu trúc lồng nhau: object, array và mảng tài liệu

Điểm mạnh của document model là khả năng đặt những thành phần liên quan gần nhau theo cấu trúc cây. Có hai dạng lồng nhau cần phân biệt.

### 6.1. Embedded object

Một **object lồng nhau** tập hợp nhiều field thành một giá trị có cấu trúc:

~~~json
{
  "_id": "usr-007",
  "profile": {
    "fullName": "Mai",
    "contact": {
      "email": "mai@example.invalid",
      "phone": null
    }
  }
}
~~~

`profile` là object lồng trong document, còn `contact` là object lồng trong `profile`. Truy cập `profile.contact.email` nghĩa là đi qua ba field theo thứ tự.

Dạng này phù hợp khi các thuộc tính thuộc cùng thực thể, thường được đọc cùng nhau và có vòng đời gần nhau.

### 6.2. Array

Mảng là tập phần tử **có thứ tự**. Phần tử có thể là chuỗi, số, object hoặc thậm chí mảng khác tùy hệ.

~~~json
{
  "_id": "product-11",
  "tags": ["education", "java", "database"],
  "prices": [120000, 110000, 100000]
}
~~~

`tags` là mảng chuỗi; `prices` là mảng số. Vị trí phần tử có thể được truy cập bằng chỉ số trong một số API/cú pháp truy vấn. Không nên dùng chỉ số mảng như ID ổn định của thực thể vì chèn, xóa hay sắp xếp lại phần tử có thể thay đổi vị trí.

### 6.3. Array of embedded documents

Đơn hàng thường có mảng các dòng sản phẩm:

~~~json
{
  "_id": "order-1001",
  "items": [
    { "lineId": "line-1", "sku": "sku-book-01", "quantity": 2 },
    { "lineId": "line-2", "sku": "sku-pen-02", "quantity": 3 }
  ]
}
~~~

Từng phần tử `items[0]` và `items[1]` là object; chúng không nhất thiết là document độc lập trong collection khác. Chúng được lưu **bên trong document cha**.

`lineId` là định danh logic ổn định của dòng hàng, giúp tìm và cập nhật đúng phần tử kể cả khi thứ tự mảng thay đổi. `lineId` trong ví dụ không phải `_id` của một document riêng.

### 6.4. Mức lồng nhau có chi phí

Có thể tạo cấu trúc rất sâu, nhưng “nhúng được” không có nghĩa “nên nhúng tất cả”. Cấu trúc sâu làm việc viết truy vấn, cập nhật một phần, validation, index và xử lý thay đổi schema phức tạp hơn.

Một document có mảng `orders` tăng mãi dưới tài liệu `customer` là dấu hiệu cần xem xét lại: kích thước document phình lên theo thời gian, mỗi lần cập nhật có thể ảnh hưởng tài liệu lớn và giới hạn kích thước của sản phẩm có thể bị vượt qua. Trong MongoDB, chẳng hạn, mỗi BSON document có giới hạn kích thước riêng; các hệ khác có giới hạn khác. Thiết kế nên tính trước kích thước tối đa có thể xảy ra.

## 7. Truy vấn document và field lồng nhau

Phần này dùng cú pháp **MongoDB Query Language** để minh họa, không phải cú pháp chuẩn áp dụng cho mọi document database.

Giả sử `db.orders` chứa tài liệu `order-1001` ở đầu bài.

### 7.1. Tìm theo field cấp gốc

~~~javascript
// Các đơn hàng đã thanh toán.
db.orders.find({ status: "PAID" })

// Đúng một đơn hàng bằng khóa _id.
db.orders.findOne({ _id: "order-1001" })
~~~

Kết quả truy vấn có thể gồm toàn bộ document, nghĩa là chứa cả `shipping` và `items`, dù ứng dụng chỉ quan tâm mã đơn.

### 7.2. Tìm bằng đường dẫn lồng nhau

~~~javascript
// Các đơn có địa chỉ giao ở Đà Nẵng.
db.orders.find({ "shipping.address.city": "Da Nang" })
~~~

Dấu chấm ở đây biểu thị **đường dẫn tới field lồng nhau**. Nếu dùng `{ shipping: { address: { city: "Da Nang" } } }` để so khớp cả object, ngữ nghĩa có thể khác vì phải xét cấu trúc object đầy đủ; dùng field path thường phù hợp hơn khi chỉ lọc một thuộc tính con.

### 7.3. Chỉ lấy những field cần thiết (projection)

~~~javascript
db.orders.find(
  { status: "PAID" },
  {
    _id: 0,
    customerId: 1,
    totalAmount: 1,
    "shipping.address.city": 1
  }
)
~~~

Projection trả về những field đã chọn theo quy tắc của MongoDB. Việc trả ít field làm phản hồi gọn hơn, nhưng **không tự chứng minh engine đọc ít byte trên đĩa** trong mọi tình huống; khả năng covered query phụ thuộc chỉ mục và đường thực thi.

### 7.4. Truy vấn mảng object và bẫy hai điều kiện

Với document ví dụ ở đầu bài, có hai phần tử: dòng sách có `quantity = 2` và dòng bút có `quantity = 3`.

~~~javascript
// Tìm đơn hàng có sản phẩm sku-book-01 ở đâu đó trong items.
db.orders.find({ "items.sku": "sku-book-01" })
~~~

Nhưng nếu thêm điều kiện:

~~~javascript
db.orders.find({
  "items.sku": "sku-book-01",
  "items.quantity": { $gte: 3 }
})
~~~

Truy vấn này **có thể khớp hai phần tử khác nhau** trong cùng mảng: phần tử thứ nhất có `sku-book-01`, phần tử thứ hai có số lượng 3. Nó không bắt buộc hai điều kiện nằm trên **cùng một dòng hàng**.

Để yêu cầu cùng một phần tử thỏa cả hai điều kiện, dùng `$elemMatch`:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "sku-book-01",
      quantity: { $gte: 3 }
    }
  }
})
~~~

Với mẫu ban đầu, truy vấn cuối **không khớp** vì sách có số lượng 2. Đây là khác biệt ngữ nghĩa quan trọng khi làm việc với **array of embedded documents**.

### 7.5. Array of scalars

Với sản phẩm:

~~~json
{
  "_id": "product-11",
  "tags": ["education", "java", "database"]
}
~~~

Một truy vấn MongoDB như `{ tags: "java" }` khớp document nếu phần tử của mảng chứa giá trị `"java"`. Điều này khác với so sánh nguyên mảng theo đúng thứ tự và kích thước. Các toán tử `$all`, `$in` và `$elemMatch` có ngữ nghĩa riêng; cần chọn theo câu hỏi nghiệp vụ cụ thể.

## 8. Cập nhật field lồng nhau và phần tử mảng

Lưu trữ một đơn hàng trong một document giúp nhiều thay đổi của **cùng đơn hàng** có thể được thực hiện trong một thao tác cập nhật tài liệu.

### 8.1. Cập nhật một field sâu bằng đường dẫn

~~~javascript
db.orders.updateOne(
  { _id: "order-1001" },
  {
    $set: {
      "shipping.address.city": "Hue"
    }
  }
)
~~~

`$set` với dot notation chỉ thay đổi field đích, không thay toàn bộ object `shipping`. Ngược lại, câu lệnh như sau có ý nghĩa khác:

~~~javascript
db.orders.updateOne(
  { _id: "order-1001" },
  {
    $set: {
      shipping: { method: "EXPRESS" }
    }
  }
)
~~~

Nó **thay thế giá trị của cả field `shipping`**, khiến các thông tin cũ như `recipient` và `address` không còn nằm trong object đó. Đây là một lỗi phổ biến khi ứng dụng nhầm **merge field** với **replace object**.

### 8.2. Cập nhật đúng phần tử mảng

Ví dụ chuyển số lượng dòng `line-1` từ 2 lên 3:

~~~javascript
db.orders.updateOne(
  { _id: "order-1001" },
  {
    $set: {
      "items.$[line].quantity": 3
    }
  },
  {
    arrayFilters: [
      { "line.lineId": "line-1" }
    ]
  }
)
~~~

`$[line]` là biến định danh phần tử mảng, và `arrayFilters` chọn những phần tử phù hợp. Cách này rõ ràng hơn việc sửa theo chỉ số `items.0.quantity` khi thứ tự mảng có thể thay đổi.

Tuy nhiên, thay `quantity` từ 2 lên 3 phải đi kèm kiểm tra lại `totalAmount`, thuế, tồn kho hoặc các bất biến nghiệp vụ. **Cơ sở dữ liệu không tự biết các field này phải đồng bộ với nhau** chỉ vì chúng được lưu trong một document.

### 8.3. Thêm phần tử mảng

~~~javascript
db.orders.updateOne(
  { _id: "order-1001" },
  {
    $push: {
      items: {
        lineId: "line-3",
        sku: "sku-note-03",
        name: "Vo C",
        quantity: 1,
        unitPrice: 30000
      }
    }
  }
)
~~~

Thao tác này minh họa cách thêm một object vào mảng. Nếu hệ thống gửi lại yêu cầu do timeout, `$push` lặp có thể tạo phần tử trùng; ứng dụng cần cơ chế **idempotency** và kiểm tra `lineId` khi yêu cầu nghiệp vụ không cho phép dòng trùng.

### 8.4. Tính nguyên tử trong một document

Trong MongoDB, thao tác ghi đối với **một document** có tính nguyên tử. Một lệnh cập nhật nhiều field trong cùng document có thể bảo vệ tính nhất quán của chính thao tác đó. Nhưng nếu thay đổi liên quan **nhiều document** — chẳng hạn tạo đơn hàng và trừ tồn kho ở tài liệu sản phẩm — phải xem khả năng transaction và chiến lược xử lý lỗi của sản phẩm.

Ví dụ có thể kết hợp điều kiện phiên bản để chống ghi đè khi hai người sửa cùng lúc:

~~~javascript
db.orders.updateOne(
  { _id: "order-1001", version: 4 },
  {
    $set: { status: "SHIPPED" },
    $inc: { version: 1 }
  }
)
~~~

Nếu không có document nào khớp `version = 4`, ứng dụng cần kiểm tra tình huống **version đã đổi hoặc đơn hàng không tồn tại**. Nó không được mặc định cập nhật thành công rồi ghi đè một trạng thái mới hơn.

## 9. Nhúng dữ liệu hay tham chiếu sang collection khác?

Một quyết định cốt lõi trong document modeling là: **thông tin nào thuộc một tài liệu, thông tin nào nên là tài liệu riêng?**

### 9.1. Nhúng (embedding)

Ví dụ một đơn hàng nhúng danh sách dòng hàng:

~~~json
{
  "_id": "order-1001",
  "customerId": "usr-007",
  "items": [
    { "sku": "sku-book-01", "name": "Sach A", "quantity": 2, "unitPrice": 100000 },
    { "sku": "sku-pen-02", "name": "But B", "quantity": 3, "unitPrice": 50000 }
  ]
}
~~~

**Ưu điểm:** đọc chi tiết đơn hàng thường lấy được nhiều thông tin liên quan trong một lần đọc; một thao tác cập nhật đơn hàng có thể thay đổi nhiều field nhúng cùng nhau.

**Chi phí:** nếu mảng tăng vô hạn, document trở nên quá lớn; nếu một object nhúng bị nhiều tài liệu khác sao chép, thay đổi thông tin dùng chung có thể cần cập nhật nhiều nơi.

Trong ví dụ, `name` và `unitPrice` của dòng hàng có thể là **ảnh chụp tại thời điểm mua**. Ngay cả khi tên hoặc giá sản phẩm thay đổi sau này, đơn hàng cũ vẫn cần giữ giá trị lúc chốt đơn. Đây là lý do nghiệp vụ hợp lý để **nhúng một bản sao có chủ ý**, không phải đồng bộ mọi giá trị theo catalog mới.

### 9.2. Tham chiếu (referencing)

Khách hàng thường tồn tại độc lập với từng đơn hàng. Vì vậy, thay vì nhúng toàn bộ tài liệu người dùng vào mỗi đơn, đơn hàng có thể lưu:

~~~json
{
  "_id": "order-1001",
  "customerId": "usr-007",
  "items": [
    { "sku": "sku-book-01", "quantity": 2 }
  ]
}
~~~

Document khách hàng:

~~~json
{
  "_id": "usr-007",
  "name": "Mai",
  "email": "mai@example.invalid",
  "membership": "GOLD"
}
~~~

`customerId` là **tham chiếu logic** tới một thực thể bên ngoài đơn hàng. Document database không mặc nhiên tạo ràng buộc foreign key chỉ vì trường có tên `customerId`. Ứng dụng cần đảm bảo khóa trỏ đúng thực thể và xử lý trường hợp đối tượng được tham chiếu đã bị xóa hoặc không còn quyền truy cập.

### 9.3. Bảng quyết định

| Tình huống | Thường nghiêng về | Lý do |
| --- | --- | --- |
| Địa chỉ giao hàng tại thời điểm đặt đơn | **Nhúng** | Cần lưu đúng địa chỉ đã dùng cho giao dịch lịch sử |
| Các dòng sản phẩm trong một đơn hàng có giới hạn hợp lý | **Nhúng** | Thường được đọc và cập nhật theo đơn hàng |
| Danh mục sản phẩm độc lập, tái sử dụng bởi nhiều đơn | **Tham chiếu** | Có vòng đời và thuộc tính hiện tại riêng |
| Hàng triệu lượt truy cập của một tài khoản | **Document/collection riêng** | Mảng nhúng không nên tăng không giới hạn |
| Cài đặt nhỏ, chỉ dùng cùng hồ sơ người dùng | **Nhúng** | Đọc hồ sơ và cài đặt cùng nhau |
| Bản ghi cần chia sẻ giữa nhiều tenant/quy trình | **Thường tham chiếu** | Giúp quản lý quyền và cập nhật độc lập |
| Số liệu tổng hợp thường đọc cùng document chính | **Có thể lưu sẵn/nhúng có kiểm soát** | Giảm truy vấn tính lại, nhưng phải quản lý dữ liệu dẫn xuất |

Không có quy tắc “luôn nhúng” hoặc “luôn tham chiếu”. Xác định từ **quan hệ nghiệp vụ**, **kiểu truy vấn**, **tần suất cập nhật**, **số lượng phần tử tối đa** và **mức nhất quán cần giữ**.

## 10. Chỉ mục trên field và cấu trúc lồng nhau

Nếu thường lọc đơn theo thành phố, việc quét toàn bộ `orders` có thể tốn kém. Nhiều document database cho phép lập chỉ mục trên field path. MongoDB ví dụ:

~~~javascript
db.orders.createIndex({ "shipping.address.city": 1 })
~~~

Truy vấn:

~~~javascript
db.orders.find({
  "shipping.address.city": "Da Nang"
})
~~~

có thể sử dụng chỉ mục này tùy bộ tối ưu và phân bố dữ liệu. Dấu `1` chỉ hướng sắp xếp tăng dần trong chỉ mục MongoDB, không phải chỉ mục của phần tử mảng.

### 10.1. Chỉ mục trên mảng (multikey)

MongoDB có thể tạo **multikey index** khi field được đánh chỉ mục chứa mảng:

~~~javascript
db.orders.createIndex({ "items.sku": 1 })
~~~

Nhờ đó, truy vấn tìm các đơn hàng chứa một SKU có thể tránh quét tất cả document. Tuy nhiên, lập chỉ mục field mảng thường tạo nhiều index entries; mảng lớn và thao tác ghi thường xuyên có thể làm tăng chi phí lưu trữ, ghi và bảo trì index.

### 10.2. Chỉ mục ghép

Ví dụ giao diện quản trị thường lấy đơn của một khách hàng theo thời điểm mới nhất:

~~~javascript
db.orders.createIndex({
  customerId: 1,
  placedAt: -1
})
~~~

Chỉ mục ghép phù hợp với một số truy vấn lọc theo `customerId` và sắp xếp theo `placedAt`, nếu dữ liệu được lưu bằng kiểu thời gian thích hợp và truy vấn đáp ứng các quy tắc sử dụng index của engine.

**Không tạo index cho mọi field**: mỗi index tiêu tốn bộ nhớ/dung lượng và làm tăng chi phí cập nhật. Cần xuất phát từ truy vấn thực tế và xem execution plan, độ chọn lọc dữ liệu, cùng thống kê hiệu năng.

### 10.3. Index khác collection và field

Một field có thể tồn tại mà không được đánh chỉ mục. Một collection có thể chứa hàng triệu document nhưng chỉ có một số chỉ mục. Và index trên `shipping.address.city` không biến `address` thành collection độc lập. Đây là những tầng kỹ thuật khác nhau.

## 11. Schema linh hoạt và kiểm soát tiến hóa cấu trúc

Document database thường cho phép bổ sung field thuận tiện khi ứng dụng thay đổi. Ví dụ phiên bản đầu lưu:

~~~json
{
  "_id": "usr-007",
  "name": "Mai",
  "email": "mai@example.invalid"
}
~~~

Phiên bản tiếp theo chuyển `email` vào `contact` và thêm `notificationPreferences`:

~~~json
{
  "_id": "usr-007",
  "name": "Mai",
  "contact": {
    "email": "mai@example.invalid"
  },
  "notificationPreferences": {
    "emailEnabled": true
  },
  "schemaVersion": 2
}
~~~

Trong giai đoạn chuyển đổi, collection có thể chứa cả document phiên bản 1 và 2. Ứng dụng phải có quy tắc để đọc dữ liệu cũ, chuyển đổi và ghi dữ liệu mới.

### 11.1. Ba cách tiến hóa schema

1. **Đọc tương thích:** reader nhận diện `schemaVersion` hoặc sự hiện diện của field để đọc được cả định dạng cũ lẫn mới.
2. **Backfill:** chuyển tài liệu cũ theo lô và ghi kết quả có kiểm tra phiên bản để không ghi đè thay đổi phát sinh trong lúc chạy.
3. **Chỉ ghi cấu trúc mới:** từ một mốc nhất định, writer mới luôn tạo document phiên bản hiện hành; chỉ bỏ nhánh đọc cũ sau khi dữ liệu đã được chuyển xong và xác minh theo quy trình hệ thống.

Ngoài ra, có thể dùng **schema validation** ở database hoặc ứng dụng để ngăn document sai kiểu, thiếu field bắt buộc hoặc chứa dữ liệu không phù hợp. Những validation như “`totalAmount` phải khớp tổng dòng hàng” thường cần logic nghiệp vụ bổ sung.

### 11.2. Thiết kế có biến thể

Nếu một collection `payments` lưu nhiều loại thanh toán, có thể dùng trường phân biệt:

~~~json
{
  "_id": "payment-1001",
  "method": "CARD",
  "card": {
    "network": "VISA",
    "last4": "1234"
  }
}
~~~

~~~json
{
  "_id": "payment-1002",
  "method": "BANK_TRANSFER",
  "bankTransfer": {
    "bankCode": "BANK-A",
    "reference": "REF-205"
  }
}
~~~

Cả hai đều có `_id` và `method`, nhưng phần dữ liệu riêng cho từng phương thức nằm trong object tương ứng. Hợp đồng dữ liệu nên quy định rõ: nếu `method = CARD` thì phải có những field nào, có được phép chứa `bankTransfer` hay không và xử lý giá trị không hợp lệ thế nào.

Các ví dụ thanh toán chỉ mang tính mô hình dữ liệu; không nên lưu thông tin thẻ nhạy cảm tùy tiện trong document. Trường `last4` chỉ là bốn chữ số cuối để minh họa thuộc tính hiển thị.

## 12. Document model trong hệ thống phân tán

Document, collection và field là các khái niệm **logic**. Khi cơ sở dữ liệu mở rộng, chúng còn liên quan tới cách lưu trữ vật lý và phân tán.

~~~text
Ứng dụng
  |
  v
Database / namespace
  |
  +-- Collection: orders
  |     |
  |     +-- Document order-1001 (shipping, items, ...)
  |     +-- Document order-1002
  |     +-- Document order-1003
  |
  +-- Collection: users
        |
        +-- Document usr-007
        +-- Document usr-008

Bên dưới lớp logic:
  - index hỗ trợ đường truy vấn
  - partition/shard xác định nơi chứa dữ liệu (nếu hệ có phân mảnh)
  - replica duy trì bản sao phục vụ sẵn sàng/đọc (nếu triển khai)
  - node/cluster vận hành các thành phần lưu trữ
~~~

Nhiều tài liệu của một collection có thể được đặt trên nhiều phân vùng; các phân vùng có thể có replica. **Một document không mặc nhiên là một file, một shard hoặc một replica.** Tương tự, **collection không nhất thiết chỉ tồn tại trên một máy**.

Nếu một thao tác chủ yếu đọc và cập nhật thông tin thuộc một document, nhúng có thể giảm việc phối hợp nhiều bản ghi. Nếu nghiệp vụ cần thay đổi nhiều document độc lập, phải kiểm tra khả năng transaction, chính sách nhất quán và kiến trúc phân tán của sản phẩm. Document model giúp tổ chức dữ liệu theo thực thể nhưng không xóa bỏ chi phí phối hợp trên nhiều thực thể.

## 13. Những lỗi mô hình hóa thường gặp

### 13.1. Nhúng danh sách không giới hạn vào một document

~~~json
{
  "_id": "usr-007",
  "allOrders": [
    "... hàng nghìn hoặc hàng triệu đơn hàng ..."
  ]
}
~~~

Nếu danh sách liên tục tăng, việc đọc hồ sơ người dùng kéo theo dữ liệu không cần thiết, cập nhật gây áp lực lên document và có nguy cơ chạm giới hạn kích thước. Thường nên lưu đơn hàng trong collection riêng theo `customerId`, rồi truy vấn bằng index phù hợp.

### 13.2. Sao chép dữ liệu thay đổi thường xuyên mà không có quy tắc

Nhúng `customer.email` vào 500 đơn hàng có thể tiện hiển thị, nhưng nếu giao diện phải luôn phản ánh email hiện tại, cập nhật một email có thể đòi hỏi ghi lại nhiều document. Cần quyết định dữ liệu nhúng là **snapshot lịch sử** hay **bản sao phải đồng bộ**; hai trường hợp có chiến lược cập nhật khác nhau.

### 13.3. Lạm dụng cấu trúc sâu để thay thế thiết kế truy vấn

Một tài liệu nhiều cấp như `company.departments[].teams[].members[].activity[]` có vẻ tiện vì chứa “mọi thứ trong một chỗ”, nhưng truy vấn một hoạt động của một thành viên có thể khó chỉ mục, khó cập nhật và khó phân quyền theo thành viên. Cần cân nhắc tách các thực thể có vòng đời và tần suất truy cập riêng.

### 13.4. Thay cả object khi chỉ muốn thay một field

Dùng `$set: { shipping: { method: "EXPRESS" } }` trên MongoDB sẽ thay nội dung `shipping`. Nếu muốn giữ `address` và `recipient`, hãy cập nhật đường dẫn cụ thể `shipping.method` hoặc thực hiện một phép biến đổi có chủ đích.

### 13.5. Hiểu sai truy vấn trên mảng

Điều kiện `items.sku = A` và `items.quantity >= 3` có thể khớp trên hai phần tử khác nhau trong cùng mảng. Khi cần kiểm tra **cùng một phần tử**, dùng toán tử thích hợp như `$elemMatch` trong MongoDB.

### 13.6. Nhầm thiếu field với giá trị null

Nếu ứng dụng trả mặc định `false` cho mọi trường `emailVerified` bị thiếu, có thể vô tình coi dữ liệu “chưa từng được xác minh” như một quyết định xác minh đã được ghi nhận. Thiết kế cần nêu rõ ý nghĩa của **missing**, **null** và giá trị cụ thể.

### 13.7. Coi collection là một schema tự do mãi mãi

Nếu mỗi service ghi `totalAmount` theo kiểu khác nhau (string, number, object), truy vấn sẽ khó và sai số tăng. Dù collection cho phép khác biệt cấu trúc, nên có quy ước field, validator, version và kiểm thử hợp đồng giữa các producer/consumer.

### 13.8. Nhúng dữ liệu nhạy cảm vào tài liệu dùng chung

Một document lớn có thể trộn thông tin công khai với số điện thoại, địa chỉ hoặc bí mật dùng riêng. Nếu API trả nguyên document cho client, thông tin nhạy cảm dễ bị lộ do projection hoặc phân quyền không đầy đủ. Cần giới hạn field trả về, áp dụng quyền truy cập theo thực thể và thuộc tính phù hợp, và cân nhắc tách dữ liệu có mức truy cập khác nhau.

## 14. Chọn cấu trúc bằng kiểu truy vấn thực tế

Một thiết kế document tốt nên bắt đầu bằng những màn hình và thao tác ứng dụng phải hỗ trợ.

| Nhu cầu | Gợi ý mô hình |
| --- | --- |
| Xem một đơn hàng cùng địa chỉ và dòng sản phẩm | Một document `orders` có `shipping` và mảng `items` với kích thước kiểm soát |
| Tìm mọi đơn của một khách hàng | `orders.customerId` làm tham chiếu, index theo khách hàng và thời gian |
| Đổi thông tin liên hệ hiện tại của khách | Document `users` lưu `contact`, tham chiếu bằng ID ổn định |
| Lưu giá sản phẩm đúng thời điểm đặt hàng | Snapshot `name`, `unitPrice` trong `orders.items[]` |
| Xem lịch sử nhiều năm với hàng triệu sự kiện | Collection sự kiện riêng, phân vùng/chỉ mục theo kiểu truy vấn |
| Lọc đơn hàng theo thành phố nhận hàng | Đường dẫn `shipping.address.city` và index nếu workload cần |
| Tìm dòng hàng thỏa đồng thời SKU và số lượng | Truy vấn phần tử mảng với ngữ nghĩa cùng phần tử, ví dụ `$elemMatch` |

Cũng cần tính đến **tần suất đọc/ghi**, **số document tối đa**, **kích thước document tối đa**, **phân bố dữ liệu**, **tính nhất quán** và **yêu cầu phân quyền**. Không nên quyết định nhúng chỉ vì JSON cho phép lồng sâu.

## 15. Bài tập thực hành tư duy

### Bài 1: nhận diện cấp dữ liệu

Cho tài liệu:

~~~json
{
  "_id": "course-01",
  "title": "NoSQL Basics",
  "metadata": {
    "language": "vi",
    "level": "BEGINNER"
  },
  "lessons": [
    { "id": "l1", "title": "Documents", "minutes": 20 },
    { "id": "l2", "title": "Collections", "minutes": 25 }
  ]
}
~~~

**Câu hỏi:** Có bao nhiêu document cấp gốc? `metadata` là field hay collection? `lessons[1].minutes` là gì?

**Gợi ý đáp án:** Đây là **một document cấp gốc** có `_id = course-01`. `metadata` là field có giá trị object, không phải collection. `lessons[1].minutes` là field `minutes` trong object thứ hai của mảng `lessons`; giá trị là 25.

### Bài 2: truy vấn đường dẫn

Với đơn hàng ở đầu bài, muốn lọc đơn theo thành phố `Da Nang` và chỉ trả `_id`, `status`, `totalAmount`. Hãy viết truy vấn MongoDB.

**Một cách viết:**

~~~javascript
db.orders.find(
  { "shipping.address.city": "Da Nang" },
  { _id: 1, status: 1, totalAmount: 1 }
)
~~~

### Bài 3: phân biệt hai truy vấn mảng

Một đơn có hai dòng: `{sku: "A", quantity: 1}` và `{sku: "B", quantity: 5}`. Truy vấn yêu cầu có `items.sku = "A"` đồng thời `items.quantity >= 5`. Nó có thể khớp không?

**Gợi ý đáp án:** Có thể khớp nếu hai điều kiện được đánh giá trên **hai phần tử khác nhau** theo ngữ nghĩa của MongoDB. Nếu muốn tìm một dòng có cả `sku = "A"` lẫn `quantity >= 5`, dùng `$elemMatch`; với dữ liệu đó sẽ không khớp.

### Bài 4: nhúng hay tham chiếu?

Ứng dụng có một tài liệu người dùng và 200.000 bản ghi hoạt động mỗi người dùng, tiếp tục tăng hằng ngày. Có nên nhúng tất cả hoạt động vào mảng `users.activities[]`?

**Gợi ý đáp án:** Thường không. Đây là quan hệ một–nhiều có kích thước không giới hạn, nên xem xét collection hoạt động riêng, lưu `userId` và khóa thời gian để truy vấn theo người dùng. Có thể giữ một tập hoạt động gần nhất được giới hạn kích thước trong document người dùng nếu ứng dụng cần truy cập nhanh và có cơ chế cập nhật rõ ràng.

### Bài 5: phiên bản schema

Collection `profiles` có document cũ dùng `email` ở cấp gốc, document mới dùng `contact.email`. Khi hệ vẫn phục vụ lưu lượng đọc/ghi, cần chuẩn bị điều gì?

**Gợi ý đáp án:** Reader hỗ trợ cả hai cấu trúc trong thời gian chuyển tiếp; writer mới dùng schema thống nhất; backfill tài liệu cũ theo lô với kiểm soát cập nhật đồng thời; sau khi đối chiếu đủ, bật validator và loại bỏ đường đọc cũ khi không còn dữ liệu phụ thuộc.

### Bài 6: tính nguyên tử

Một thao tác chuyển đơn hàng sang trạng thái `PAID` đồng thời cập nhật `paidAt` trong cùng document. Một thao tác khác phải giảm tồn kho tại document sản phẩm. Có thể suy ra một transaction nguyên tử cho cả hai chỉ vì tất cả là document không?

**Gợi ý đáp án:** Không. Cập nhật nhiều field **trong một document** có phạm vi bảo đảm riêng; cập nhật **nhiều document** cần khả năng transaction của hệ cụ thể hoặc chiến lược phối hợp, retry và đối chiếu.

## 16. Nắm chắc bốn tầng trước khi thiết kế tiếp

- **Document:** một đơn vị thông tin logic có định danh, gồm các field và giá trị.
- **Collection:** tập document có tên, có thể được truy vấn, đánh chỉ mục và kiểm soát schema theo cơ chế của sản phẩm.
- **Field:** thuộc tính của document; giá trị có thể đơn giản hoặc phức hợp, và field lồng nhau có thể được truy cập bằng đường dẫn.
- **Cấu trúc lồng nhau:** object và array nằm trong document; giúp mô hình hóa các thành phần được đọc và cập nhật cùng nhau.

Khi nhìn một thiết kế NoSQL dạng tài liệu, hãy hỏi lần lượt: **một tài liệu đại diện cho thực thể gì, vì sao các tài liệu nằm trong collection này, những field nào mang ý nghĩa nghiệp vụ, cấu trúc lồng nhau tăng trưởng ra sao, và truy vấn thực tế có đọc/cập nhật chúng cùng nhau không?** Những câu hỏi đó giúp chuyển từ việc “biết viết JSON” sang việc **thiết kế document model phù hợp với ứng dụng**.
