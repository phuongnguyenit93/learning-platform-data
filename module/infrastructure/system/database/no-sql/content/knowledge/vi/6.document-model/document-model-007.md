# Truy vấn theo trường, đường dẫn lồng nhau và điều kiện trên mảng

Document database thường lưu thông tin liên quan trong một tài liệu JSON/BSON: trường đơn giản, object lồng nhau và mảng các giá trị hoặc các object. Cách lưu này giúp đọc dữ liệu nghiệp vụ theo một cấu trúc tự nhiên, nhưng cũng làm phát sinh câu hỏi quan trọng: **khi truy vấn một đường dẫn lồng nhau, điều kiện đang áp dụng lên document, object nào hay phần tử mảng nào?**

Ví dụ, một sản phẩm có hai biến thể màu đỏ và màu xanh. Biến thể đỏ còn hàng ở Hà Nội, biến thể xanh còn hàng ở TP. Hồ Chí Minh. Nếu muốn tìm **sản phẩm có biến thể đỏ còn hàng ở TP. Hồ Chí Minh**, không thể chỉ kiểm tra rằng document “có màu đỏ”, “có kho HCM” và “có số lượng lớn hơn 0” mà bỏ qua việc ba thông tin ấy thuộc cùng biến thể và cùng kho hay không.

Bài học sử dụng **MongoDB và mongosh** để minh họa. Những khái niệm như truy vấn theo field, truy cập nested path và điều kiện “cùng phần tử” có thể gặp trong nhiều hệ NoSQL, nhưng **cú pháp và bảo đảm thực thi là của MongoDB**, không phải chuẩn chung cho mọi document database.

## 1. Document mẫu và dữ liệu dùng xuyên suốt

Xét collection `products` của một nền tảng bán hàng đa cửa hàng. Mỗi sản phẩm có thông tin chung và các mảng mô tả thuộc tính, biến thể, tồn kho và đánh giá.

~~~javascript
db.products.insertMany([
  {
    _id: "prod-101",
    tenantId: "shop-17",
    name: "Bàn phím cơ",
    status: "ACTIVE",
    category: {
      code: "KEYBOARD",
      department: "ACCESSORIES"
    },
    price: {
      amount: NumberLong("1250000"),
      currency: "VND"
    },
    tags: ["mechanical", "wireless"],
    variants: [
      {
        sku: "KB-RED",
        color: "red",
        priceAmount: NumberLong("1250000"),
        stock: [
          { warehouse: "HN", available: 12 },
          { warehouse: "HCM", available: 0 }
        ]
      },
      {
        sku: "KB-BLUE",
        color: "blue",
        priceAmount: NumberLong("1320000"),
        stock: [
          { warehouse: "HN", available: 0 },
          { warehouse: "HCM", available: 7 }
        ]
      }
    ],
    reviews: [
      { userId: "u-1", score: 5, verified: true },
      { userId: "u-2", score: 2, verified: false }
    ],
    ratings: [2, 9],
    createdAt: ISODate("2026-11-01T10:00:00Z")
  },
  {
    _id: "prod-102",
    tenantId: "shop-17",
    name: "Chuột không dây",
    status: "ACTIVE",
    category: {
      code: "MOUSE",
      department: "ACCESSORIES"
    },
    price: {
      amount: NumberLong("490000"),
      currency: "VND"
    },
    tags: ["wireless", "compact"],
    variants: [
      {
        sku: "MOUSE-BLACK",
        color: "black",
        priceAmount: NumberLong("490000"),
        stock: [
          { warehouse: "HN", available: 0 },
          { warehouse: "HCM", available: 15 }
        ]
      }
    ],
    reviews: [
      { userId: "u-3", score: 5, verified: false },
      { userId: "u-4", score: 2, verified: true }
    ],
    ratings: [4, 5],
    createdAt: ISODate("2026-11-03T08:30:00Z")
  },
  {
    _id: "prod-103",
    tenantId: "shop-42",
    name: "Bàn phím văn phòng",
    status: "ARCHIVED",
    category: {
      code: "KEYBOARD",
      department: "OFFICE"
    },
    price: {
      amount: NumberLong("350000"),
      currency: "VND"
    },
    tags: ["office"],
    variants: [],
    reviews: [],
    ratings: [],
    createdAt: ISODate("2026-10-20T14:00:00Z")
  }
]);
~~~

Đây là dữ liệu học tập, được thiết kế để quan sát rõ sự khác nhau giữa các kiểu điều kiện. Trong ứng dụng thật, cần có chính sách về kiểu BSON, validation, index và giới hạn kích thước document. Các lệnh ví dụ có thể chạy trong môi trường thử nghiệm MongoDB với quyền tạo collection và ghi dữ liệu.

Sơ đồ cấu trúc tài liệu:

~~~text
Product
├── _id: string
├── tenantId: string
├── name: string
├── status: string
├── category: object
│   ├── code: string
│   └── department: string
├── price: object
│   ├── amount: int64
│   └── currency: string
├── tags: string[]
├── variants: object[]
│   ├── sku: string
│   ├── color: string
│   ├── priceAmount: int64
│   └── stock: object[]
│       ├── warehouse: string
│       └── available: number
├── reviews: object[]
│   ├── userId: string
│   ├── score: number
│   └── verified: boolean
├── ratings: number[]
└── createdAt: date
~~~

Các truy vấn dưới đây có thể chia thành bốn nhóm: **theo trường ở cấp gốc**, **theo đường dẫn trong object**, **theo giá trị trong mảng** và **theo tập điều kiện cần đúng trên cùng một phần tử mảng**.

## 2. Truy vấn theo trường ở cấp gốc

Trong MongoDB, `find(filter, projection)` dùng đối tượng điều kiện để chọn document.

~~~javascript
db.products.find({
  tenantId: "shop-17",
  status: "ACTIVE"
});
~~~

Hai điều kiện cùng cấp trong filter được kết hợp theo logic **AND**: chỉ các document có `tenantId` tương ứng **và** `status` là `ACTIVE` mới khớp. Với dữ liệu ví dụ, đó là `prod-101` và `prod-102`.

### So sánh bằng và các toán tử so sánh

~~~javascript
// Giá sản phẩm phải lớn hơn hoặc bằng 500.000 VND.
db.products.find({
  "price.amount": { $gte: NumberLong("500000") }
});

// Trạng thái thuộc một trong các giá trị cho phép.
db.products.find({
  status: { $in: ["ACTIVE", "ARCHIVED"] }
});

// Lọc theo nhiều điều kiện đơn giản.
db.products.find({
  tenantId: "shop-17",
  status: "ACTIVE",
  "price.amount": { $gte: NumberLong("300000") }
});
~~~

Một số toán tử thường dùng:

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| `$eq` | Bằng | `{ status: { $eq: "ACTIVE" } }` |
| `$ne` | Không bằng | `{ status: { $ne: "ARCHIVED" } }` |
| `$gt` / `$gte` | Lớn hơn / lớn hơn hoặc bằng | `{ "price.amount": { $gte: 500000 } }` |
| `$lt` / `$lte` | Nhỏ hơn / nhỏ hơn hoặc bằng | `{ "price.amount": { $lt: 2000000 } }` |
| `$in` | Thuộc một danh sách giá trị | `{ status: { $in: ["ACTIVE", "DRAFT"] } }` |
| `$nin` | Không thuộc danh sách | `{ status: { $nin: ["ARCHIVED"] } }` |
| `$and` | Tất cả điều kiện đúng | `{ $and: [condition1, condition2] }` |
| `$or` | Ít nhất một điều kiện đúng | `{ $or: [condition1, condition2] }` |
| `$exists` | Có hoặc không có field theo đường dẫn | `{ "category.code": { $exists: true } }` |
| `$type` | Kiểm tra kiểu BSON | `{ "price.amount": { $type: "long" } }` |

Cần đặc biệt chú ý `$ne` và `$nin`: chúng có thể khớp cả document **không có trường đang xét**. Nếu yêu cầu “trường phải tồn tại và khác X”, phải biểu diễn thêm điều kiện tồn tại hoặc kiểu dữ liệu theo hợp đồng.

### AND và OR không đồng nghĩa

~~~javascript
// Sản phẩm thuộc shop-17, đồng thời
// là KEYBOARD hoặc có giá dưới 500.000.
db.products.find({
  tenantId: "shop-17",
  $or: [
    { "category.code": "KEYBOARD" },
    { "price.amount": { $lt: NumberLong("500000") } }
  ]
});
~~~

Filter này có nghĩa:

\[
tenantId = shop17 \land
(category.code = KEYBOARD \lor price.amount < 500000)
\]

Nó **khác** với việc đưa `tenantId` vào một nhánh `$or`, vì khi đó có thể lấy cả sản phẩm của tenant khác.

## 3. Đường dẫn lồng nhau với dot notation

MongoDB cho phép truy cập field bên trong object bằng **dot notation**: dùng dấu chấm nối các cấp, viết đường dẫn thành chuỗi.

~~~javascript
db.products.find({
  "category.code": "KEYBOARD"
});
~~~

Điều kiện trên tìm document có object `category` chứa field `code` bằng `KEYBOARD`; khớp `prod-101` và `prod-103`.

~~~javascript
db.products.find({
  tenantId: "shop-17",
  "category.department": "ACCESSORIES",
  "price.currency": "VND"
});
~~~

**Đường dẫn có ý nghĩa cấu trúc**: `"category.code"` là field `code` nằm trong object `category`. Không viết `category.code` trực tiếp như một key JavaScript không đặt trong dấu nháy.

### So sánh cả object khác với so sánh field bên trong

Hai cách sau không tương đương:

~~~javascript
// So sánh object nhúng theo giá trị BSON đầy đủ.
// Với so sánh equality object, cấu trúc và thứ tự field có ý nghĩa.
db.products.find({
  category: {
    code: "KEYBOARD",
    department: "ACCESSORIES"
  }
});

// Chỉ kiểm tra hai trường con, không yêu cầu object
// có đúng hai field hoặc đúng thứ tự khai báo.
db.products.find({
  "category.code": "KEYBOARD",
  "category.department": "ACCESSORIES"
});
~~~

Cách thứ nhất là **equality trên embedded document**: thứ tự field và tập field liên quan đến so sánh có thể làm kết quả khác kỳ vọng. Nếu muốn lọc theo thuộc tính nghiệp vụ, cách thứ hai thường dễ diễn đạt hơn.

### Đường dẫn có thể không tồn tại

Một document có thể không có `category`, hoặc có `category` nhưng thiếu `code`.

~~~javascript
db.products.find({
  "category.code": { $exists: true }
});
~~~

`$exists: true` nghĩa là đường dẫn có mặt, **kể cả khi giá trị là `null`**. `$exists: false` tìm đường dẫn không tồn tại theo quy tắc của MongoDB.

Không nên giả định mọi document trong NoSQL đều có cùng schema, nhất là khi dữ liệu đến từ import, hệ thống cũ hoặc nhiều phiên bản producer.

## 4. Projection: chọn trường trả về thay vì lấy cả document

Phần thứ hai của `find(filter, projection)` dùng để chọn các field cần trả về.

~~~javascript
db.products.find(
  { tenantId: "shop-17", status: "ACTIVE" },
  {
    _id: 0,
    name: 1,
    "category.code": 1,
    "price.amount": 1
  }
);
~~~

Kết quả chỉ chứa các trường được chọn; các object cha cần thiết được dựng theo cấu trúc tương ứng. `_id` mặc định được đưa vào kết quả trừ khi loại bằng `_id: 0`.

Một số nguyên tắc:

- Projection giúp giảm dữ liệu truyền qua mạng, deserialize và hiển thị.
- Projection không thay thế kiểm tra quyền truy cập: không được cấp quyền đọc document nhạy cảm chỉ vì UI dự kiến không hiển thị field.
- Phần lớn projection có quy tắc **chọn field (1)** hoặc **loại field (0)**, với ngoại lệ đặc biệt như `_id`; không trộn chọn và loại tùy ý.
- Projection của trường thuộc mảng object, ví dụ `"variants.sku": 1`, **không có nghĩa chỉ trả về phần tử mảng khớp filter**. Nó chọn đường dẫn field cho các phần tử theo semantics projection; để lọc phần tử mảng cần cơ chế phù hợp như `$elemMatch` projection hoặc aggregation `$filter`.

### Vì sao chọn trường giúp nhưng không đủ tối ưu?

Nếu query không dùng index phù hợp, database vẫn có thể phải quét nhiều document dù response nhỏ. Cần phân biệt **số document được đọc để tìm kết quả** và **số byte cuối cùng trả về API**.

## 5. Truy vấn mảng giá trị đơn giản

Trường `tags` là mảng chuỗi:

~~~json
{
  "tags": ["mechanical", "wireless"]
}
~~~

### 5.1. Kiểm tra mảng chứa một giá trị

~~~javascript
db.products.find({
  tags: "wireless"
});
~~~

Truy vấn này khớp document nếu mảng `tags` có phần tử bằng `"wireless"`. Với dữ liệu mẫu, cả `prod-101` và `prod-102` khớp.

Cần phân biệt:

~~~javascript
// Mảng chứa ít nhất một phần tử bằng "wireless".
db.products.find({ tags: "wireless" });

// Mảng đúng bằng danh sách được khai báo, theo thứ tự và giá trị.
db.products.find({ tags: ["mechanical", "wireless"] });
~~~

So sánh `tags` với **một chuỗi** và với **một mảng hoàn chỉnh** có ngữ nghĩa khác nhau. Với field có kiểu mảng đúng theo hợp đồng, việc so sánh cả mảng cần xem cả thứ tự phần tử.

### 5.2. Ít nhất một giá trị thuộc tập cho trước: `$in`

~~~javascript
db.products.find({
  tags: { $in: ["mechanical", "compact"] }
});
~~~

Document khớp khi `tags` có ít nhất một phần tử bằng một giá trị trong `$in`. Trên dữ liệu mẫu, `prod-101` khớp vì `mechanical`, còn `prod-102` khớp vì `compact`.

### 5.3. Phải chứa tất cả các giá trị: `$all`

~~~javascript
db.products.find({
  tags: { $all: ["mechanical", "wireless"] }
});
~~~

`prod-101` thỏa điều kiện vì mảng chứa cả hai nhãn. `$all` **không yêu cầu các giá trị xuất hiện theo đúng thứ tự** trong danh sách truyền vào.

### 5.4. Kiểm tra số phần tử: `$size`

~~~javascript
db.products.find({
  tags: { $size: 2 }
});
~~~

Truy vấn yêu cầu mảng có đúng hai phần tử. Với các toán tử MongoDB thông thường, `$size` dùng để kiểm tra kích thước chính xác, không phải cách viết `{ $size: { $gte: 2 } }` để kiểm tra khoảng.

Nếu hệ thống thường xuyên cần query theo số lượng phần tử, có thể cân nhắc lưu một trường đếm có chính sách đồng bộ rõ ràng, hoặc dùng aggregation expression khi phù hợp. Lưu trường đếm bổ sung kéo theo trách nhiệm cập nhật nhất quán.

### 5.5. Truy cập một vị trí cụ thể trong mảng

~~~javascript
db.products.find({
  "tags.0": "mechanical"
});
~~~

Đường dẫn `tags.0` chỉ phần tử đầu tiên của mảng. Chỉ dùng cách này khi vị trí phần tử **có ý nghĩa nghiệp vụ ổn định**. Nếu mảng chỉ là tập các nhãn không có thứ tự, truy vấn theo chỉ số thường dễ sai khi dữ liệu thay đổi.

## 6. Truy vấn mảng object bằng dot notation

Mảng `reviews` chứa các embedded document:

~~~javascript
reviews: [
  { userId: "u-1", score: 5, verified: true },
  { userId: "u-2", score: 2, verified: false }
]
~~~

Để tìm sản phẩm có **ít nhất một đánh giá đạt 5 điểm**:

~~~javascript
db.products.find({
  "reviews.score": 5
});
~~~

MongoDB có thể tìm giá trị `score` bên trong **các phần tử object của mảng** theo đường dẫn `reviews.score`.

Tương tự:

~~~javascript
db.products.find({
  "variants.sku": "KB-RED"
});
~~~

Truy vấn trên chọn sản phẩm có một phần tử của `variants` với `sku = "KB-RED"`.

### Bẫy quan trọng: nhiều điều kiện trên cùng mảng

Xét filter:

~~~javascript
db.products.find({
  "reviews.score": { $gte: 4 },
  "reviews.verified": true
});
~~~

Nhiều người đọc thành “có một đánh giá vừa đạt ít nhất 4 điểm vừa đã xác minh”. Đây **không phải bảo đảm của truy vấn**.

Với `prod-102`:

~~~javascript
reviews: [
  { userId: "u-3", score: 5, verified: false },
  { userId: "u-4", score: 2, verified: true }
]
~~~

- Điều kiện `reviews.score >= 4` đúng nhờ phần tử đầu.
- Điều kiện `reviews.verified = true` đúng nhờ phần tử thứ hai.
- **Không có phần tử nào** đồng thời đạt hai điều kiện.
- Tuy vậy, filter dùng hai dot path độc lập vẫn có thể khớp cả document.

Đây là điểm phân biệt quan trọng nhất khi thiết kế query trên mảng các object.

## 7. `$elemMatch`: nhiều điều kiện phải đúng trên cùng một phần tử

`$elemMatch` dùng để yêu cầu **ít nhất một phần tử của mảng** thỏa **tất cả điều kiện** bên trong.

~~~javascript
db.products.find({
  reviews: {
    $elemMatch: {
      score: { $gte: 4 },
      verified: true
    }
  }
});
~~~

Với dữ liệu mẫu:

- `prod-101` khớp vì đánh giá `{ score: 5, verified: true }`.
- `prod-102` không khớp vì một đánh giá đạt 5 nhưng chưa xác minh; đánh giá đã xác minh chỉ đạt 2.
- `prod-103` không khớp vì mảng `reviews` rỗng.

Có thể mô tả ý nghĩa:

\[
\exists r \in product.reviews :
(r.score \ge 4)\ \land\ (r.verified = true)
\]

So với hai điều kiện dot path độc lập:

\[
(\exists r_1 : r_1.score \ge 4)
\ \land\
(\exists r_2 : r_2.verified = true)
\]

Ở biểu thức thứ hai, `r_1` và `r_2` **có thể là hai phần tử khác nhau**.

### Cách đọc một truy vấn `$elemMatch`

~~~javascript
db.products.find({
  variants: {
    $elemMatch: {
      color: "red",
      priceAmount: { $lte: NumberLong("1300000") }
    }
  }
});
~~~

Đọc chính xác: “Tìm document có **ít nhất một** phần tử `variants` mà **chính phần tử đó** có `color = red` và `priceAmount <= 1.300.000`”.

Không đọc thành: “Sản phẩm nào có màu đỏ ở đâu đó và một biến thể nào đó có giá phù hợp”.

### Khi chỉ có một điều kiện thì sao?

Với một điều kiện đơn giản như `"reviews.score": 5`, dot notation thường đủ. `$elemMatch` có ý nghĩa lớn nhất khi yêu cầu **nhiều điều kiện đồng thời trên cùng một phần tử** hoặc cần biểu diễn tường minh điều kiện gắn với một phần tử mảng.

Ngoài ra, `$elemMatch` áp dụng cho **array**. Một object nhúng đơn lẻ trông giống phần tử mảng sẽ không tự được xem như mảng khi dùng toán tử này. Schema cần quy định nhất quán field đang là object hay array.

## 8. `$elemMatch` với mảng số: điều kiện khoảng trên cùng giá trị

Bẫy “hai phần tử khác nhau” không chỉ xảy ra với mảng object.

Trong dữ liệu mẫu:

~~~javascript
// prod-101
ratings: [2, 9]

// prod-102
ratings: [4, 5]
~~~

Giả sử cần tìm sản phẩm có **một giá trị rating từ 4 đến 6**.

Truy vấn sau **không thể hiện rõ yêu cầu cùng phần tử**:

~~~javascript
db.products.find({
  ratings: { $gte: 4, $lte: 6 }
});
~~~

Với cách MongoDB áp dụng nhiều điều kiện so sánh lên field mảng, document có thể khớp nhờ **một phần tử đáp ứng giới hạn dưới** và **phần tử khác đáp ứng giới hạn trên**. Mảng `[2, 9]` là ví dụ cần chú ý.

Để yêu cầu một phần tử nằm trong khoảng, dùng:

~~~javascript
db.products.find({
  ratings: {
    $elemMatch: {
      $gte: 4,
      $lte: 6
    }
  }
});
~~~

Truy vấn này khớp `prod-102` nhờ `4` hoặc `5`, và không khớp `prod-101` vì `2` và `9` đều nằm ngoài khoảng 4–6.

Đối với **field số đơn lẻ**, `{ score: { $gte: 4, $lte: 6 } }` lại thể hiện hai điều kiện trên cùng một giá trị field. Vấn đề khác biệt xuất hiện khi giá trị đang xét là **mảng**.

## 9. Mảng lồng trong mảng: chọn đúng biến thể và đúng kho

Quay lại yêu cầu nghiệp vụ: “Tìm sản phẩm có **biến thể màu đỏ còn hàng tại kho HCM**”.

Dữ liệu của `prod-101`:

~~~javascript
variants: [
  {
    sku: "KB-RED",
    color: "red",
    stock: [
      { warehouse: "HN", available: 12 },
      { warehouse: "HCM", available: 0 }
    ]
  },
  {
    sku: "KB-BLUE",
    color: "blue",
    stock: [
      { warehouse: "HN", available: 0 },
      { warehouse: "HCM", available: 7 }
    ]
  }
]
~~~

### Truy vấn dễ gây kết quả sai

~~~javascript
db.products.find({
  "variants.color": "red",
  "variants.stock.warehouse": "HCM",
  "variants.stock.available": { $gt: 0 }
});
~~~

Ba điều kiện trên có thể được thỏa bởi các nhánh khác nhau trong các mảng. `prod-101` **không có biến thể đỏ nào còn hàng tại HCM**, nhưng document vẫn chứa:

- Một biến thể màu đỏ.
- Một kho HCM.
- Một phần tử kho có `available > 0`.

Chỉ dựa vào dot notation sẽ không bảo đảm các trường cùng thuộc một biến thể và cùng một phần tử kho.

### Truy vấn đúng với `$elemMatch` lồng nhau

~~~javascript
db.products.find({
  variants: {
    $elemMatch: {
      color: "red",
      stock: {
        $elemMatch: {
          warehouse: "HCM",
          available: { $gt: 0 }
        }
      }
    }
  }
});
~~~

Đọc theo từng cấp:

1. Phải tồn tại một phần tử `variants` có màu đỏ.
2. **Trong chính biến thể đó**, phải tồn tại một phần tử `stock`.
3. **Trong chính phần tử stock đó**, `warehouse = HCM` và `available > 0` đều đúng.

Với dữ liệu mẫu, `prod-101` không khớp vì biến thể đỏ có tồn kho HCM bằng 0.

Nếu thay màu đỏ bằng xanh:

~~~javascript
db.products.find({
  variants: {
    $elemMatch: {
      color: "blue",
      stock: {
        $elemMatch: {
          warehouse: "HCM",
          available: { $gt: 0 }
        }
      }
    }
  }
});
~~~

Khi đó `prod-101` khớp nhờ biến thể xanh có 7 đơn vị ở HCM.

### Sơ đồ phạm vi điều kiện

~~~mermaid
flowchart TD
    P["Product document"] --> V["Tồn tại một phần tử variants"]
    V --> C{"color = blue?"}
    C -->|Không| N["Xét phần tử variants khác"]
    C -->|Có| S["Trong biến thể này, xét stock[]"]
    S --> W{"Một phần tử stock có warehouse = HCM và available > 0?"}
    W -->|Có| Y["Document khớp"]
    W -->|Không| N
~~~

Sơ đồ thể hiện **logic điều kiện**, không mô tả thuật toán vật lý hay thứ tự mà query engine buộc phải duyệt mảng.

## 10. Nếu cần hai phần tử khác nhau cùng đáp ứng hai vai trò?

`$elemMatch` chỉ tìm **một phần tử** đáp ứng điều kiện đã nêu. Một yêu cầu khác có thể là:

> Sản phẩm có ít nhất một biến thể đỏ **và** ít nhất một biến thể xanh.

Không cần ép hai màu trái nhau vào cùng một phần tử:

~~~javascript
// Yêu cầu hai điều kiện tồn tại trong mảng.
// Chúng có thể được thỏa bởi hai biến thể khác nhau.
db.products.find({
  "variants.color": "red",
  $and: [
    { "variants.color": "blue" }
  ]
});
~~~

Một cách tường minh hơn là dùng `$all` với các biểu thức `$elemMatch`:

~~~javascript
db.products.find({
  variants: {
    $all: [
      { $elemMatch: { color: "red" } },
      { $elemMatch: { color: "blue" } }
    ]
  }
});
~~~

Trường hợp “có biến thể đỏ và có biến thể xanh” **khác** với “một biến thể vừa đỏ vừa xanh”. Việc chọn cách viết phụ thuộc ràng buộc nghiệp vụ đang muốn mô tả.

Với điều kiện phức tạp hơn, có thể dùng các nhánh `$and` riêng biệt, mỗi nhánh là một `$elemMatch` trên cùng trường mảng. Mỗi nhánh tìm sự tồn tại của phần tử thỏa **nhóm điều kiện của chính nhánh ấy**.

## 11. Filter chọn document, không tự cắt phần tử mảng trong kết quả

Giả sử truy vấn:

~~~javascript
db.products.find({
  "reviews.score": { $gte: 4 }
});
~~~

Document được trả về nếu có ít nhất một đánh giá đạt 4 điểm. **Kết quả mặc định vẫn chứa toàn bộ mảng `reviews`**, gồm cả đánh giá thấp.

Điều này thường gây nhầm lẫn khi API mong muốn chỉ gửi về các đánh giá tốt.

### 11.1. Projection bình thường không lọc các phần tử

~~~javascript
db.products.find(
  { "reviews.score": { $gte: 4 } },
  {
    _id: 0,
    name: 1,
    "reviews.userId": 1,
    "reviews.score": 1
  }
);
~~~

Projection chỉ chọn các field cần trả về trong cấu trúc mảng; nó không nói rằng chỉ được giữ review có `score >= 4`.

### 11.2. `$elemMatch` trong projection: lấy một phần tử khớp

~~~javascript
db.products.find(
  { tenantId: "shop-17" },
  {
    name: 1,
    reviews: {
      $elemMatch: {
        score: { $gte: 4 },
        verified: true
      }
    }
  }
);
~~~

Cần phân biệt hai cách sử dụng cùng tên toán tử:

- **`$elemMatch` trong filter:** chọn document nếu mảng có ít nhất một phần tử thỏa điều kiện.
- **`$elemMatch` trong projection:** trả về **phần tử khớp đầu tiên** của mảng theo cơ chế projection; không có mục tiêu trả về mọi phần tử khớp.

Nếu API cần **tất cả** đánh giá đạt điều kiện, dùng aggregation với `$filter`.

### 11.3. `$filter` trong aggregation: giữ mọi phần tử phù hợp

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "shop-17",
      status: "ACTIVE"
    }
  },
  {
    $project: {
      _id: 0,
      name: 1,
      positiveVerifiedReviews: {
        $filter: {
          input: "$reviews",
          as: "review",
          cond: {
            $and: [
              { $gte: ["$$review.score", 4] },
              { $eq: ["$$review.verified", true] }
            ]
          }
        }
      }
    }
  }
]);
~~~

Ở đây:

- `$match` chọn **những product document** cần xét.
- `$project` tạo kết quả đầu ra mới.
- `$filter` duyệt các phần tử trong mảng `reviews`.
- `$$review.score` và `$$review.verified` là đường dẫn tới biến `review` trong ngữ cảnh expression.
- Kết quả `positiveVerifiedReviews` chứa **tất cả phần tử** khớp điều kiện, theo thứ tự còn lại trong mảng.

Chữ `$` trong aggregation expression không đồng nghĩa với `$` trong filter query. Ví dụ `"$reviews"` ở đây là tham chiếu field trong expression, còn `"$$review.score"` tham chiếu biến được khai báo bằng `as`.

## 12. `$unwind` khi cần biến mỗi phần tử thành một bản ghi xử lý

Một nhu cầu khác là lập báo cáo: tổng số đánh giá đạt từ 4 điểm trở lên theo sản phẩm, hoặc tổng tồn kho theo kho.

`$unwind` có thể tách mỗi phần tử mảng thành một document ở bước pipeline tương ứng:

~~~javascript
db.products.aggregate([
  { $match: { tenantId: "shop-17" } },
  { $unwind: "$reviews" },
  { $match: { "reviews.score": { $gte: 4 } } },
  {
    $group: {
      _id: "$_id",
      name: { $first: "$name" },
      positiveReviewCount: { $sum: 1 }
    }
  }
]);
~~~

Ý nghĩa:

1. Giới hạn sản phẩm thuộc tenant cần báo cáo.
2. Mỗi review trở thành một bản ghi trung gian.
3. Giữ review đạt từ 4 điểm.
4. Gom lại theo ID sản phẩm và đếm.

**Lưu ý:** Sau `$unwind`, số bản ghi trung gian có thể tăng nhiều lần so với số product document. Một sản phẩm có 10.000 review có thể tạo 10.000 bản ghi trung gian; pipeline cần được xem xét hiệu năng. `$unwind` với mảng rỗng hoặc thiếu thường không tạo bản ghi đầu ra, trừ khi cấu hình `preserveNullAndEmptyArrays` cho tình huống phù hợp.

Nếu mục tiêu chỉ là trả về danh sách review khớp mà vẫn giữ một document sản phẩm, `$filter` có thể rõ ràng và phù hợp hơn.

## 13. Trường thiếu, `null` và mảng rỗng

Trong document database linh hoạt, các tình trạng sau khác nhau:

~~~javascript
// Không có reviews.
{ _id: "a", name: "A" }

// reviews tồn tại, nhưng có giá trị null.
{ _id: "b", name: "B", reviews: null }

// reviews là mảng rỗng.
{ _id: "c", name: "C", reviews: [] }

// reviews có một phần tử.
{ _id: "d", name: "D", reviews: [{ score: 5 }] }
~~~

### 13.1. So sánh với `null`

~~~javascript
db.products.find({
  reviews: null
});
~~~

Trong MongoDB, truy vấn bằng `null` có thể khớp document có field `reviews` bằng `null` **hoặc không có field đó**. Nó không đồng nghĩa với “mảng rỗng”.

Muốn tìm field tồn tại và giá trị có BSON type `null`, có thể dùng:

~~~javascript
db.products.find({
  reviews: { $type: "null" }
});
~~~

Muốn tìm field hoàn toàn thiếu:

~~~javascript
db.products.find({
  reviews: { $exists: false }
});
~~~

Muốn tìm mảng có đúng 0 phần tử:

~~~javascript
db.products.find({
  reviews: { $size: 0 }
});
~~~

### 13.2. Không dùng “không tìm thấy phần tử” như chứng cứ field hợp lệ

~~~javascript
db.products.find({
  "reviews.score": { $ne: 5 }
});
~~~

Đây **không phải** truy vấn “mọi review đều khác 5 điểm” trong mọi mô hình dữ liệu. Với field mảng và toán tử phủ định, cần đọc đúng semantics của MongoDB, kể cả document thiếu đường dẫn. Nếu yêu cầu nghiệp vụ là “không có review nào đạt 5 điểm”, có thể biểu diễn rõ sự phủ định tồn tại một phần tử:

~~~javascript
db.products.find({
  reviews: {
    $not: {
      $elemMatch: { score: 5 }
    }
  }
});
~~~

Tuy nhiên, cách này cũng có thể khớp document thiếu `reviews`, bởi **không có phần tử khớp** khác với **mảng chắc chắn tồn tại và hợp lệ**. Nếu nghiệp vụ đòi field phải là mảng, nên kết hợp validation/schema hoặc thêm điều kiện kiểm tra kiểu tương ứng.

## 14. Điều kiện logic nhiều cấp trong filter

Có thể kết hợp `$and`, `$or` và `$elemMatch` để mô tả tình huống thực tế.

Ví dụ: một cửa hàng muốn tìm sản phẩm ACTIVE, thuộc nhóm phụ kiện, đồng thời **có biến thể còn hàng tại HN** và **có đánh giá đã xác minh đạt ít nhất 4 điểm**:

~~~javascript
db.products.find({
  tenantId: "shop-17",
  status: "ACTIVE",
  "category.department": "ACCESSORIES",
  variants: {
    $elemMatch: {
      stock: {
        $elemMatch: {
          warehouse: "HN",
          available: { $gt: 0 }
        }
      }
    }
  },
  reviews: {
    $elemMatch: {
      verified: true,
      score: { $gte: 4 }
    }
  }
});
~~~

Các điều kiện trên hai mảng **khác nhau** (`variants` và `reviews`) không cần chung phần tử nào; mỗi mảng chỉ phải có phần tử thỏa nhóm điều kiện của nó.

Nếu thêm yêu cầu “có nhãn `wireless` hoặc `mechanical`”:

~~~javascript
db.products.find({
  tenantId: "shop-17",
  status: "ACTIVE",
  tags: { $in: ["wireless", "mechanical"] },
  reviews: {
    $elemMatch: { verified: true, score: { $gte: 4 } }
  }
});
~~~

Cách viết một query tốt là **đặt mỗi nhóm điều kiện đúng trong phạm vi thực thể mà nó áp dụng**, sau đó kết hợp các nhóm bằng logic AND/OR.

## 15. Điều kiện thời gian, số và kiểu dữ liệu

Đường dẫn lồng nhau không làm biến mất yêu cầu **đồng nhất kiểu**.

### Ngày tháng

~~~javascript
db.products.find({
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
});
~~~

Đây là cách biểu diễn một khoảng thời gian nửa kín: từ đầu tháng 11/2026 (bao gồm) đến đầu tháng 12/2026 (không bao gồm), theo UTC của ví dụ.

Nếu một số document lưu `createdAt` là chuỗi ISO thay vì BSON Date, các toán tử so sánh kiểu ngày không tự hiểu mọi chuỗi đó như Date. Kết quả lọc/sort/index có thể khác mong đợi. Hãy chọn một kiểu lưu và chuyển đổi dữ liệu cũ có kiểm soát.

### Giá tiền

~~~javascript
db.products.find({
  "price.amount": {
    $gte: NumberLong("500000"),
    $lt: NumberLong("1500000")
  },
  "price.currency": "VND"
});
~~~

Nếu lưu giá ở đơn vị nhỏ nhất của tiền tệ theo chính sách, nên dùng kiểu số nguyên phù hợp hoặc decimal chính xác. Đừng trộn chuỗi như `"1.250.000"` với số nguyên mà kỳ vọng mọi truy vấn so sánh có cùng ý nghĩa.

Khi mô hình cho phép nhiều currency, điều kiện tiền còn phải gắn với currency hoặc quy tắc quy đổi. So sánh trực tiếp `100 USD` và `100 VND` bằng một field amount không có ý nghĩa nghiệp vụ.

## 16. Từ câu hỏi nghiệp vụ đến đúng hình dạng query

Xét ba yêu cầu có vẻ giống nhau nhưng khác ý nghĩa.

| Câu hỏi nghiệp vụ | Hình dạng điều kiện thích hợp |
|---|---|
| Có ít nhất một biến thể màu đỏ | `{ "variants.color": "red" }` |
| Có một biến thể vừa màu đỏ vừa có giá không quá 1,3 triệu | `{ variants: { $elemMatch: { color: "red", priceAmount: { $lte: 1300000 } } }` |
| Có một biến thể đỏ và (có thể là biến thể khác) màu xanh | Hai điều kiện tồn tại độc lập hoặc `$all` với hai `$elemMatch` |
| Có ít nhất một rating từ 4 đến 6 | `{ ratings: { $elemMatch: { $gte: 4, $lte: 6 } } }` |
| Có tag wireless | `{ tags: "wireless" }` |
| Có cả tag wireless và mechanical | `{ tags: { $all: ["wireless", "mechanical"] } }` |
| Mảng review rỗng | `{ reviews: { $size: 0 } }` |
| Không có review đạt 5 điểm | `{ reviews: { $not: { $elemMatch: { score: 5 } } } }`, xét thêm hợp đồng field |
| Chỉ trả về review được xác minh | Aggregation `$filter` |
| Đếm số review đạt điều kiện | `$unwind` + `$match` + `$group`, hoặc expression phù hợp |

Việc viết lại yêu cầu thành “tồn tại một phần tử...” hoặc “tồn tại hai phần tử...” giúp tránh những query nhìn hợp lý nhưng trả dữ liệu sai.

## 17. Multikey index: vì sao mảng ảnh hưởng đến truy vấn và index?

Truy vấn đúng logic là bước đầu; hiệu năng phụ thuộc dữ liệu, kích thước mảng và chiến lược index.

MongoDB có **multikey index** cho field chứa mảng. Một index trên đường dẫn trong mảng có thể tạo các entry tương ứng với các giá trị của mảng theo cách engine quản lý. Điều này hỗ trợ nhiều truy vấn trên mảng, nhưng cũng làm tăng số entry và chi phí duy trì index khi document có nhiều phần tử.

Ví dụ một index phục vụ các truy vấn lọc theo tenant và tag:

~~~javascript
db.products.createIndex({
  tenantId: 1,
  tags: 1
});
~~~

Tương tự, có thể tạo index phục vụ đường dẫn lồng nhau:

~~~javascript
db.products.createIndex({
  tenantId: 1,
  "category.code": 1
});
~~~

Với điều kiện lọc theo biến thể:

~~~javascript
db.products.createIndex({
  tenantId: 1,
  "variants.color": 1,
  "variants.priceAmount": 1
});
~~~

Đây là **ví dụ cấu trúc index có thể cân nhắc**, không phải bảo đảm query nào cũng dùng index hoặc dùng hiệu quả. Cần đo bằng `explain` và kiểm tra giới hạn index của phiên bản MongoDB cũng như mô hình sharding thực tế.

### 17.1. `$elemMatch` giúp chỉ rõ sự ràng buộc trong cùng phần tử

Với array of embedded documents, cách biểu diễn điều kiện cùng phần tử qua `$elemMatch` có ý nghĩa không chỉ về **độ đúng của kết quả** mà còn có thể ảnh hưởng khả năng query planner kết hợp các khoảng của multikey index.

~~~javascript
db.products.find({
  tenantId: "shop-17",
  variants: {
    $elemMatch: {
      color: "red",
      priceAmount: { $lte: NumberLong("1300000") }
    }
  }
});
~~~

Nếu chỉ dùng hai dot path độc lập, database không thể tự giả định hai điều kiện phải đúng trên một phần tử. Không nên suy ra cùng phạm vi phần tử chỉ từ việc hai đường dẫn cùng bắt đầu bằng `variants.`.

### 17.2. Compound multikey index có giới hạn

MongoDB có giới hạn đối với compound multikey index khi một document có nhiều trường mảng được index song song. Ví dụ không nên tự động tạo một compound index trên `tags` và `ratings` rồi giả định hợp lệ cho mọi document chứa **hai mảng độc lập**.

Lựa chọn index cần xem các đường dẫn đến **cùng một mảng embedded document**, các mảng độc lập, thao tác ghi và tài liệu giới hạn multikey của phiên bản đang dùng. Một thiết kế index phù hợp trên môi trường dữ liệu cũ có thể thất bại hoặc gây ảnh hưởng khi sau này thêm document với cấu trúc mảng khác.

### 17.3. Unique multikey index không chặn mọi giá trị trùng trong cùng document

Một chi tiết dễ bỏ sót: unique multikey index trong MongoDB chủ yếu bảo vệ uniqueness **giữa các document** theo entry index. Các giá trị lặp trong cùng một mảng của cùng một document không luôn bị xem là vi phạm uniqueness như người thiết kế kỳ vọng.

Nếu nghiệp vụ quy định `variants[].sku` **không được trùng trong một product**, cần xác định cách bảo vệ bất biến trong validation/service hoặc đổi mô hình lưu trữ, thay vì chỉ dựa vào giả định “unique index trên mảng chắc chắn chặn mọi phần tử trùng”.

## 18. Dùng `explain` để kiểm tra cách truy vấn chạy

Sau khi có dữ liệu và index phù hợp, có thể xem kế hoạch truy vấn:

~~~javascript
db.products.find({
  tenantId: "shop-17",
  "category.code": "KEYBOARD"
}).explain("executionStats");
~~~

Những thông tin thường cần đọc:

- `winningPlan`: kế hoạch được query planner chọn theo định dạng của phiên bản DB.
- `nReturned`: số document thực sự trả về.
- `totalDocsExamined`: số document được kiểm tra.
- `totalKeysExamined`: số entry index được kiểm tra.
- Các stage như `IXSCAN`, `FETCH` hoặc `COLLSCAN` có thể xuất hiện tùy phiên bản và engine.

Nếu chỉ trả về 10 document nhưng phải quét hàng triệu document, có thể có vấn đề về index, độ chọn lọc hoặc query shape. Tuy nhiên, không được dùng riêng một con số examined để kết luận index tốt/xấu: phải xem số dữ liệu, tần suất query, chi phí ghi do index và latency thực tế.

### Vì sao index không phải lúc nào cũng thắng?

- Tập dữ liệu thử quá nhỏ khiến collection scan rẻ hơn.
- Điều kiện có độ chọn lọc thấp: phần lớn document đều khớp.
- Cần sort/aggregation mà index không hỗ trợ hiệu quả.
- Document hoặc mảng lớn làm tăng số index entry và số byte đọc.
- Query shape thay đổi do nhiều tùy chọn filter.
- Dữ liệu lệch: một tenant hoặc tag rất phổ biến, làm index kém chọn lọc hơn dự tính.

Index phục vụ **access pattern đã đo được**. Không tạo index mới cho mọi field chỉ vì document có nhiều trường.

## 19. Sắp xếp và phân trang với nested field

Có thể sắp xếp theo trường nhúng:

~~~javascript
db.products.find({
  tenantId: "shop-17",
  status: "ACTIVE"
}).sort({
  "price.amount": 1,
  _id: 1
});
~~~

`1` nghĩa là tăng dần, `-1` nghĩa là giảm dần.

Thêm `_id` làm khóa phân định thứ tự phụ khi giá bằng nhau giúp kết quả ổn định hơn trong các trường hợp cùng giá. Index kết hợp điều kiện filter và sort có thể cải thiện hiệu năng tùy query planner.

Với một tập lớn, `skip` trên nhiều document có thể tốn chi phí. Có thể dùng **keyset pagination** khi sort theo cặp trường ổn định. Ví dụ sắp theo `createdAt` giảm dần, sau đó `_id` giảm dần:

~~~javascript
const cursorDate = ISODate("2026-11-03T08:30:00Z");
const cursorId = "prod-102";

db.products.find({
  tenantId: "shop-17",
  $or: [
    { createdAt: { $lt: cursorDate } },
    {
      createdAt: cursorDate,
      _id: { $lt: cursorId }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Cursor phải dựa trên document cuối của trang trước theo đúng sort, với kiểu dữ liệu đồng nhất. Trong thực tế, filter gốc (ví dụ `status`) cũng phải giữ nguyên giữa các trang. Với dữ liệu thay đổi liên tục, cần xác định độ nhất quán phân trang và mức chấp nhận document được thêm/xóa trong quá trình duyệt.

### Cẩn trọng khi sort trên array field

Khi một field được sort là mảng, cách MongoDB chọn giá trị dùng cho sort phụ thuộc thứ tự sort và semantics của array; nó **không nhất thiết chỉ lấy phần tử đã khớp filter**. Nếu nghiệp vụ cần “sắp theo giá thấp nhất của biến thể đỏ”, nên tính ra một scalar có nghĩa rõ ràng hoặc dùng aggregation để chọn đúng tập phần tử rồi tính giá trị sort, thay vì sort trực tiếp trên `variants.priceAmount` và suy đoán.

## 20. Xây dựng query động an toàn trong ứng dụng Java

Một API thường nhận tham số tìm kiếm như:

~~~http
GET /products?category=KEYBOARD&tag=wireless&minPrice=500000
~~~

Ứng dụng cần chuyển các tham số này thành **filter có danh sách field và toán tử được cho phép**. Không nên nhận một object JSON tùy ý từ client rồi truyền nguyên vẹn vào `find`. Khi đó client có thể đưa operator hoặc đường dẫn không dự kiến, tạo truy vấn tốn kém, truy cập field nội bộ hoặc gây query selector injection.

Ví dụ với Spring Data MongoDB:

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public Query buildProductSearch(
        String tenantId,
        String categoryCode,
        String tag,
        Long minPriceMinor) {

    Query query = new Query();
    query.addCriteria(Criteria.where("tenantId").is(tenantId));
    query.addCriteria(Criteria.where("status").is("ACTIVE"));

    if (categoryCode != null && !categoryCode.isBlank()) {
        query.addCriteria(
            Criteria.where("category.code").is(categoryCode)
        );
    }

    if (tag != null && !tag.isBlank()) {
        query.addCriteria(Criteria.where("tags").is(tag));
    }

    if (minPriceMinor != null) {
        if (minPriceMinor < 0) {
            throw new IllegalArgumentException("Minimum price must be nonnegative");
        }
        query.addCriteria(
            Criteria.where("price.amount").gte(minPriceMinor)
        );
    }

    return query;
}
~~~

Ví dụ này chỉ minh họa xây dựng filter. Trong ứng dụng thật:

- `tenantId` phải lấy từ ngữ cảnh đã xác thực hoặc được ủy quyền, không tin trực tiếp tham số không kiểm soát.
- Kiểm tra format và giới hạn độ dài của các tham số.
- Cần đặt giới hạn `limit`, thời gian xử lý, projection và chính sách sort.
- Kiểu `Long` trong Java phải được ánh xạ phù hợp với kiểu BSON đang lưu.
- Nếu filter lồng nhiều mảng, phải dùng `elemMatch` phù hợp với ý nghĩa nghiệp vụ.

### Ví dụ dùng `elemMatch` trong Spring Data MongoDB

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = new Query();

query.addCriteria(Criteria.where("tenantId").is("shop-17"));

Criteria reviewCondition = Criteria.where("score").gte(4)
    .and("verified").is(true);

query.addCriteria(
    Criteria.where("reviews").elemMatch(reviewCondition)
);
~~~

Ý định ở đây tương đương truy vấn MongoDB yêu cầu cùng một review có `score >= 4` và `verified = true`. Khi điều kiện lồng nhiều tầng hoặc thư viện có cách ghép Criteria riêng, nên kiểm tra document filter sinh ra trong quá trình phát triển để chắc chắn nhóm điều kiện đúng phạm vi mảng.

### Không ghép đường dẫn tự do từ request

Ví dụ client gửi `sortField=variants.stock.available` hoặc `filterField=internal.secret`. Nếu server sử dụng trực tiếp tên field, client có thể truy cập logic không được thiết kế hoặc làm phát sinh query nặng. Thay vào đó, ánh xạ một tập tên công khai, chẳng hạn `name`, `price`, `createdAt`, sang field nội bộ đã được phê duyệt.

## 21. Thiết kế document dựa vào kiểu truy vấn

Truy vấn theo mảng không tách rời mô hình dữ liệu. Nếu ứng dụng liên tục hỏi “trong một sản phẩm, có biến thể nào đáp ứng nhiều điều kiện hay không?”, embedding `variants[]` có thể phù hợp. Nhưng nếu mỗi biến thể có vòng đời độc lập, số phần tử tăng rất lớn, tồn kho cập nhật liên tục ở nhiều kho và mỗi biến thể cần index/quyền riêng, lưu tất cả trong một product document có thể trở thành điểm nghẽn.

Các tiêu chí quyết định:

| Tình huống | Gợi ý thiết kế |
|---|---|
| Một sản phẩm có vài biến thể, luôn đọc cùng thông tin chung | Nhúng `variants[]` có thể đơn giản và hiệu quả |
| Một sản phẩm có hàng trăm nghìn event hoặc review tăng liên tục | Cân nhắc collection riêng cho event/review thay vì mảng phình không giới hạn |
| Tồn kho thay đổi nhanh, có cập nhật cạnh tranh | Cân nhắc tách trạng thái tồn kho thành thực thể được cập nhật riêng, giữ bất biến bằng cơ chế phù hợp |
| Cần tìm kiếm review theo user/date/rating trên toàn hệ thống | Collection review riêng có thể giúp index và phân trang tốt hơn |
| API cần một bản tổng hợp nhanh | Có thể duy trì trường tổng hợp/materialized view với quy tắc đồng bộ được định nghĩa |
| Query thường lọc một biến thể cụ thể, sort/phân trang trên biến thể | Có thể thích hợp coi biến thể là đơn vị document độc lập |

MongoDB có tính nguyên tử của thao tác trên **một document** ở cấp document, nhưng điều đó không có nghĩa nhúng mọi thứ vào một document luôn tốt hơn. Cần cân bằng kích thước, contention, số lần cập nhật, giới hạn document và các query thực tế.

## 22. Các lỗi thường gặp khi truy vấn nested field và array

**“Cứ ghép nhiều dot path là kiểm tra cùng một phần tử.”** Không đúng. Với mảng embedded document, các điều kiện có thể được thỏa bởi các phần tử khác nhau. Dùng `$elemMatch` khi cần cùng phần tử.

**“`$elemMatch` trong filter sẽ cắt bớt phần tử trả về.”** Filter chỉ chọn document. Dùng `$elemMatch` projection cho phần tử khớp đầu tiên hoặc `$filter` nếu cần mọi phần tử khớp.

**“Query `tags: ["a", "b"]` và `$all: ["a", "b"]` tương đương.”** Query equality toàn mảng xét giá trị mảng và thứ tự; `$all` yêu cầu chứa mọi giá trị mà không phụ thuộc thứ tự.

**“`$in` yêu cầu mảng chứa tất cả giá trị.”** `$in` yêu cầu ít nhất một giá trị khớp, còn `$all` dùng cho tập giá trị cần có đủ.

**“Trường bằng `null` nghĩa là đã lưu giá trị null.”** Trong MongoDB, equality với `null` còn khớp trường thiếu. Cần phân biệt `$exists`, `$type` và schema.

**“`$size` có thể nhận `$gte` bên trong để kiểm tra mảng dài hơn 10.”** `$size` trong query chỉ diễn đạt kích thước chính xác. Dùng phương án khác có semantics và hiệu năng phù hợp cho khoảng kích thước.

**“Tìm document theo review tốt thì kết quả chỉ chứa review tốt.”** Mảng kết quả không tự được lọc. Dùng aggregation khi cần biến đổi cấu trúc đầu ra.

**“Một unique index trên mảng ngăn trùng mọi phần tử trong một document.”** Unique multikey index không thể được mặc nhiên dùng như validator chống trùng phần tử nội bộ.

**“Index trên field lồng nhau luôn tối ưu.”** Hiệu năng phụ thuộc query shape, số lượng và phân bố giá trị, kích thước mảng, thứ tự field trong compound index và cách dùng `$elemMatch`.

**“NoSQL tự chuyển mọi kiểu dữ liệu khi so sánh.”** Chuỗi, số và BSON Date không được xem là cùng một kiểu về nghiệp vụ; nên duy trì schema nhất quán.

**“Có `_id` khó đoán nên không cần lọc tenant.”** Mọi query trong mô hình đa tenant vẫn phải áp dụng phạm vi được ủy quyền phù hợp.

## 23. Bài tập thực hành theo tình huống

### Bài tập A — Có cả hai nhãn

Yêu cầu: tìm sản phẩm của `shop-17` vừa có tag `wireless` vừa có tag `mechanical`.

**Gợi ý:**

~~~javascript
db.products.find({
  tenantId: "shop-17",
  tags: { $all: ["wireless", "mechanical"] }
});
~~~

Với dữ liệu mẫu, `prod-101` khớp.

### Bài tập B — Đánh giá cao và đã xác minh

Yêu cầu: tìm sản phẩm có **cùng một review** vừa có `score >= 4` vừa `verified = true`.

**Gợi ý:**

~~~javascript
db.products.find({
  reviews: {
    $elemMatch: {
      score: { $gte: 4 },
      verified: true
    }
  }
});
~~~

Với dữ liệu mẫu, `prod-101` khớp; `prod-102` không khớp.

### Bài tập C — Biến thể còn hàng tại HCM

Yêu cầu: tìm sản phẩm có một biến thể màu xanh, và trong chính biến thể đó có kho HCM còn hàng.

**Gợi ý:**

~~~javascript
db.products.find({
  variants: {
    $elemMatch: {
      color: "blue",
      stock: {
        $elemMatch: {
          warehouse: "HCM",
          available: { $gt: 0 }
        }
      }
    }
  }
});
~~~

Với dữ liệu mẫu, `prod-101` khớp vì `KB-BLUE` còn 7 sản phẩm ở HCM.

### Bài tập D — Phân biệt thiếu mảng và mảng rỗng

Yêu cầu: viết hai truy vấn khác nhau cho “document không có field `reviews`” và “document có mảng `reviews` rỗng”.

**Gợi ý:**

~~~javascript
// Không có field.
db.products.find({ reviews: { $exists: false } });

// Mảng tồn tại và có đúng 0 phần tử.
db.products.find({ reviews: { $size: 0 } });
~~~

Hai tập kết quả không tương đương trong schema linh hoạt.

### Bài tập E — Vì sao query sau có thể sai?

~~~javascript
db.products.find({
  "variants.color": "red",
  "variants.stock.warehouse": "HCM",
  "variants.stock.available": { $gt: 0 }
});
~~~

**Câu hỏi:** query có bảo đảm biến thể đỏ còn hàng tại kho HCM không?

**Gợi ý:** không. Điều kiện có thể do nhiều biến thể và nhiều mục stock khác nhau thỏa. Dùng `$elemMatch` lồng nhau như phần 9 để diễn đạt đúng phạm vi.

### Bài tập F — Trả về mọi review tốt

Yêu cầu: với mỗi sản phẩm ACTIVE của `shop-17`, chỉ trả về tên và danh sách review có `score >= 4` và đã xác minh.

**Gợi ý:**

~~~javascript
db.products.aggregate([
  { $match: { tenantId: "shop-17", status: "ACTIVE" } },
  {
    $project: {
      _id: 0,
      name: 1,
      reviews: {
        $filter: {
          input: "$reviews",
          as: "r",
          cond: {
            $and: [
              { $gte: ["$$r.score", 4] },
              { $eq: ["$$r.verified", true] }
            ]
          }
        }
      }
    }
  }
]);
~~~

Khác với filter chọn sản phẩm, `$filter` tạo một mảng đầu ra đã loại các review không thỏa điều kiện.

## 24. Quy trình tư duy trước khi viết truy vấn NoSQL

Khi đọc một yêu cầu lọc dữ liệu lồng nhau, có thể thực hiện theo thứ tự:

1. **Xác định đơn vị cần trả về:** product document, variant, stock entry hay review? `find` thường trả về cả document nếu không có projection/aggregation thích hợp.
2. **Vẽ cấu trúc field:** đường dẫn nào là object đơn, đường dẫn nào là array, có bao nhiêu cấp mảng?
3. **Viết câu điều kiện bằng ngôn ngữ tự nhiên:** “có tồn tại một phần tử mà...” hay “có hai phần tử khác nhau...”?
4. **Đặt đúng nhóm điều kiện:** dùng dot notation cho truy cập theo path, `$elemMatch` khi nhiều điều kiện phải đồng thời đúng trong một phần tử.
5. **Phân biệt lọc document và lọc array đầu ra:** `find` filter, projection `$elemMatch`, aggregation `$filter` và `$unwind` phục vụ mục tiêu khác nhau.
6. **Xác định null, missing, empty và kiểu BSON:** điều kiện lọc phải phản ánh schema thật, không giả định dữ liệu luôn đầy đủ.
7. **Gắn quyền và phạm vi dữ liệu:** đặc biệt `tenantId`, trạng thái bản ghi và quyền truy cập.
8. **Đánh giá hiệu năng:** xem query shape, index, multikey, kích thước mảng, `explain` và các trường hợp phân bố lệch.
9. **Kiểm tra bằng ví dụ phản chứng:** tạo hai phần tử mà mỗi phần tử chỉ thỏa một nửa điều kiện; query đúng phải không trả về document nếu yêu cầu “cùng phần tử”.
10. **Xác định hợp đồng API đầu ra:** có trả mọi phần tử hay chỉ phần tử khớp, có cần sort/pagination và hạn chế số lượng hay không?

Một cách ghi nhớ:

~~~text
Document-level filter:
  "Có document nào chứa giá trị này theo đường dẫn?" → dot notation

Array element scope:
  "Có MỘT phần tử thỏa đồng thời nhiều điều kiện?" → $elemMatch

Array membership:
  "Có ít nhất một trong các giá trị?" → $in
  "Có đủ tất cả các giá trị?" → $all

Array output:
  "Chỉ lấy phần tử đầu tiên phù hợp?" → projection $elemMatch
  "Lấy tất cả phần tử phù hợp?" → aggregation $filter
  "Biến phần tử thành dòng để tính toán?" → aggregation $unwind
~~~

Điểm mấu chốt là **đường dẫn cho biết dữ liệu nằm ở đâu, còn phạm vi điều kiện cho biết các tiêu chí phải đúng trên cùng đối tượng nào**. Với document có mảng lồng nhau, hai ý này không tự động trùng nhau. Khi đọc rõ yêu cầu, đặt đúng `$elemMatch` và chủ động quyết định cách trả mảng kết quả, truy vấn NoSQL sẽ chính xác hơn, dễ kiểm tra hơn và dễ tối ưu dựa trên mô hình dữ liệu thực tế.
