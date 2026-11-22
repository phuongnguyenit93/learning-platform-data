# Projection và giảm dữ liệu phải truyền về ứng dụng

Trong một ứng dụng sử dụng NoSQL, nhiều thao tác đọc chỉ cần **một phần nhỏ của tài liệu hoặc bản ghi**. Màn hình danh sách sản phẩm cần tên, giá và ảnh đại diện; nó không cần nội dung mô tả dài, toàn bộ ảnh, thông tin nhà cung cấp, nhật ký kiểm duyệt hay lịch sử cập nhật. Nếu backend luôn đọc mọi trường rồi mới xóa bớt trước khi trả response, hệ thống có thể lãng phí băng thông, bộ nhớ, thời gian giải mã và tài nguyên xử lý.

**Projection** là kỹ thuật **chỉ chọn những trường hoặc biểu thức cần trả về** khi truy vấn dữ liệu. Trong ngữ cảnh CRUD và truy vấn NoSQL, projection thường được áp dụng ngay trong câu truy vấn DBMS, trước khi kết quả đi qua mạng tới ứng dụng.

Ví dụ, thay vì:

~~~text
DBMS → tài liệu đầy đủ (20 KiB) → backend lọc còn 5 trường (0,8 KiB) → client
~~~

ta có thể yêu cầu:

~~~text
DBMS → chỉ 5 trường cần thiết (0,8 KiB) → backend → client
~~~

**Điểm cần hiểu đúng:** projection thường giúp giảm **dữ liệu trả về và công xử lý kết quả**, nhưng **không tự động làm giảm số tài liệu phải quét hoặc số byte phải đọc từ bộ lưu trữ**. Hiệu quả thực tế phụ thuộc DBMS, kế hoạch truy vấn, index, kích thước tài liệu, kiểu trường và cách dữ liệu được lưu.

Bài học sử dụng **MongoDB** làm ví dụ chính và đối chiếu với Redis, DynamoDB, Cassandra để hình dung projection trong các mô hình NoSQL khác nhau. Sau bài này, người học có thể thiết kế truy vấn chỉ lấy trường cần thiết, chọn điểm thực hiện projection và kiểm tra những đánh đổi về hiệu năng, bảo mật và tính đúng đắn.

## 1. Projection là gì?

Hãy xét một tài liệu sản phẩm:

~~~json
{
  "_id": "mongo-internal-id",
  "tenantId": "T17",
  "productId": "P1001",
  "title": "Sổ tay bìa cứng",
  "categoryId": "stationery",
  "status": "ACTIVE",
  "priceMinor": 89000,
  "currency": "VND",
  "thumbnailUrl": "https://example.invalid/img/P1001-thumb.jpg",
  "description": "Mô tả dài của sản phẩm...",
  "images": [
    {"url": "https://example.invalid/img/P1001-1.jpg", "width": 1600},
    {"url": "https://example.invalid/img/P1001-2.jpg", "width": 1600}
  ],
  "attributes": {
    "color": "blue",
    "pages": 160,
    "paperWeightGsm": 100
  },
  "supplierCostMinor": 54000,
  "internalNotes": "Chỉ nhân viên mua hàng được xem",
  "createdAt": "2026-11-01T08:00:00Z",
  "updatedAt": "2026-11-14T09:00:00Z"
}
~~~

Màn hình **thẻ sản phẩm** chỉ cần:

~~~json
{
  "productId": "P1001",
  "title": "Sổ tay bìa cứng",
  "priceMinor": 89000,
  "currency": "VND",
  "thumbnailUrl": "https://example.invalid/img/P1001-thumb.jpg"
}
~~~

**Projection** là phép biến đổi một kết quả có nhiều thuộc tính thành kết quả chỉ chứa **những thuộc tính được chọn**, hoặc một cấu trúc đầu ra được tính từ những thuộc tính đó.

### Phân biệt bốn thao tác thường được kết hợp

| Thao tác | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **Filter** | Bản ghi **nào** được chọn? | Chỉ sản phẩm có `categoryId = stationery` |
| **Projection** | Trường **nào** của bản ghi được trả về? | Chỉ `productId`, `title`, `priceMinor` |
| **Sort** | Các bản ghi được xếp **theo thứ tự nào**? | `createdAt DESC` |
| **Pagination/limit** | Trả **bao nhiêu** bản ghi trong một lần? | 20 sản phẩm/trang |

Một câu truy vấn thường cần cả bốn. Projection **không thay thế** filter hay phân trang: chọn 4 trường từ 2 triệu tài liệu vẫn có thể tạo kết quả rất lớn.

~~~text
Tập tài liệu ban đầu
       │
       ▼
Filter: chỉ tài liệu khớp điều kiện
       │
       ▼
Sort/limit: xác định thứ tự và số lượng bản ghi
       │
       ▼
Projection: chỉ đưa trường cần thiết vào kết quả
       │
       ▼
Truyền dữ liệu tới ứng dụng
~~~

Sơ đồ thể hiện **cách tư duy về kết quả**, không phải quy định thứ tự vật lý mà mọi DBMS phải thực thi. Bộ tối ưu hóa có thể sắp xếp các bước, đọc index hoặc xử lý biểu thức theo kế hoạch riêng.

## 2. Projection ở phía DBMS khác việc cắt trường tại backend

Giả sử backend có hai cách triển khai.

**Cách A — lấy toàn bộ tài liệu rồi chọn trường trong code:**

~~~javascript
const products = await db.collection("products")
  .find({ tenantId: "T17", categoryId: "stationery" })
  .limit(20)
  .toArray();

const cards = products.map((p) => ({
  productId: p.productId,
  title: p.title,
  priceMinor: p.priceMinor,
  currency: p.currency,
  thumbnailUrl: p.thumbnailUrl
}));
~~~

**Cách B — projection ngay trong truy vấn MongoDB:**

~~~javascript
const cards = await db.collection("products")
  .find(
    { tenantId: "T17", categoryId: "stationery" },
    {
      projection: {
        _id: 0,
        productId: 1,
        title: 1,
        priceMinor: 1,
        currency: 1,
        thumbnailUrl: 1
      }
    }
  )
  .limit(20)
  .toArray();
~~~

Ở cách B, kết quả mà DBMS gửi cho driver **chỉ gồm các trường đã yêu cầu**. Ứng dụng không phải tiếp nhận `description`, `images`, `attributes`, `supplierCostMinor` hoặc `internalNotes` chỉ để loại bỏ chúng.

### Các lợi ích có thể đạt được

- **Giảm lưu lượng mạng DBMS → ứng dụng:** không chuyển những trường lớn hoặc không cần.
- **Giảm chi phí giải mã:** driver ít giá trị phải deserialise thành đối tượng trong bộ nhớ.
- **Giảm bộ nhớ ứng dụng:** ít thuộc tính, ít chuỗi, mảng và đối tượng lớn phải giữ tạm.
- **Giảm công ánh xạ response:** data transfer object (DTO) có thể gần với dữ liệu lấy về hơn.
- **Giảm rủi ro rò rỉ ngoài ý muốn:** backend không nhận một số trường nhạy cảm không cần thiết, nhưng vẫn phải thực thi phân quyền thật.
- **Tạo cơ hội cho covered query:** nếu query/index đáp ứng những điều kiện nhất định, DBMS có thể trả kết quả từ index mà không tải toàn bộ tài liệu nguồn.

### Những lợi ích không được tự suy ra

Projection **không mặc định**:

- Làm giảm số tài liệu/partition DBMS phải xem xét để lọc.
- Giúp tìm kiếm bằng một trường không có index trở thành nhanh.
- Loại bỏ chi phí sắp xếp nếu truy vấn vẫn cần sort đắt đỏ.
- Giảm read capacity hoặc phí đọc của mọi DBMS.
- Làm kết quả nhất quán hơn hoặc mới hơn.
- Thay thế quy tắc authorization ở tầng ứng dụng.

Vì vậy, “trả ít cột hơn” thường là một cải tiến hữu ích, nhưng để kết luận query nhanh hơn bao nhiêu cần **đo theo hệ quản trị cụ thể**.

## 3. Ước lượng lượng dữ liệu truyền qua mạng

Một phép tính sơ bộ giúp thấy lợi ích của projection.

Giả sử:

- API trả **50 sản phẩm** mỗi trang.
- Mỗi document đầy đủ khoảng **24 KiB** sau khi mã hóa ở mức xét đến.
- Mỗi kết quả sau projection khoảng **1 KiB**.
- Trong giờ cao điểm backend xử lý **200 trang/giây**.

Nếu lấy toàn bộ tài liệu:

\[
50 \times 24\ \mathrm{KiB} = 1200\ \mathrm{KiB}
\]

Tức khoảng **1,17 MiB/trang**.

Nếu projection còn 1 KiB/sản phẩm:

\[
50 \times 1\ \mathrm{KiB}=50\ \mathrm{KiB}
\]

Tại 200 trang/giây, phần dữ liệu kết quả thô ước lượng:

| Chỉ tiêu | Đọc toàn bộ | Có projection |
| --- | ---: | ---: |
| Số document/trang | 50 | 50 |
| Kích thước kết quả/document giả định | 24 KiB | 1 KiB |
| Kết quả/trang | 1.200 KiB | 50 KiB |
| Kết quả/giây ở 200 trang/s | 240.000 KiB | 10.000 KiB |
| Tỉ lệ dung lượng theo giả định | 24 phần | 1 phần |

Theo giả định, lượng kết quả truyền giảm khoảng **95,8%**. Đây chỉ là **minh họa số học**, không phải benchmark MongoDB: dữ liệu thực có thể được nén, nhiều trường rất nhỏ, kết quả từ index hoặc có chi phí khác ngoài payload.

### Hai đoạn mạng khác nhau

Trong một kiến trúc backend thông thường:

~~~text
           (A) Mạng nội bộ                  (B) Mạng client
MongoDB ────────────────────> Backend API ──────────────────> Browser
             BSON result                        JSON response
~~~

Projection ở DBMS trực tiếp giảm lượng dữ liệu kết quả trên chặng **A**. Backend chỉ gửi những trường public trong API có thể giảm lượng dữ liệu chặng **B**.

Nếu backend đã cắt trường trước khi trả client, thêm DBMS projection vẫn **không nhất thiết giảm kích thước response HTTP**, bởi response trước đó vốn đã nhỏ. Lợi ích mới chủ yếu nằm ở chặng DB → backend, CPU, RAM và khả năng truy vấn được index bao phủ.

### Công thức suy nghĩ về tải

Một ước lượng đơn giản:

\[
\text{Bytes/second}
\approx
\text{requests/second}
\times
\text{rows/request}
\times
\text{bytes/row}
\]

Projection tác động trực tiếp lên thành phần **bytes/row trả về**. Filter và pagination tác động lên **rows/request**; index và chiến lược truy vấn quyết định lớn đến chi phí **tìm ra các rows đó**.

Nếu bỏ phân trang, giảm bytes/row nhưng vẫn trả hàng triệu bản ghi có thể không đủ để giữ hệ thống ổn định.

## 4. MongoDB: projection dạng inclusion

Trong MongoDB, cách phổ biến nhất là **chỉ định danh sách trường cần lấy** bằng `1` hoặc `true`.

Ví dụ trong `mongosh`:

~~~javascript
db.products.find(
  {
    tenantId: "T17",
    status: "ACTIVE"
  },
  {
    productId: 1,
    title: 1,
    priceMinor: 1,
    currency: 1,
    _id: 0
  }
);
~~~

Kết quả mẫu:

~~~json
{
  "productId": "P1001",
  "title": "Sổ tay bìa cứng",
  "priceMinor": 89000,
  "currency": "VND"
}
~~~

Các trường không được yêu cầu sẽ không xuất hiện trong kết quả của projection.

### Trường `_id` mặc định

Trong MongoDB, `_id` thường **được trả về mặc định**, kể cả khi projection chọn vài trường khác:

~~~javascript
db.products.find(
  { productId: "P1001" },
  { title: 1, priceMinor: 1 }
);
~~~

Kết quả vẫn có thể gồm `_id`. Nếu API không cần trường này, dùng:

~~~javascript
db.products.find(
  { productId: "P1001" },
  { _id: 0, title: 1, priceMinor: 1 }
);
~~~

**Đừng nhầm `_id` với `productId`.** Một hệ thống có thể dùng `_id` là ObjectId nội bộ còn `productId` là mã nghiệp vụ ổn định. Có nên gửi `_id` ra ngoài API hay không là quyết định hợp đồng dữ liệu, không phải quy tắc chung.

### Inclusion nên phù hợp với endpoint

Một endpoint có thể yêu cầu:

~~~text
GET /products/P1001
  → productId, title, priceMinor, description,
    images, attributes, availability

GET /products?category=stationery
  → productId, title, priceMinor, thumbnailUrl
~~~

Hai đường đọc có **projection khác nhau** dù cùng dùng collection `products`. Một object “product đầy đủ” dùng chung cho mọi API thường kéo theo dữ liệu thừa trên danh sách và có nguy cơ làm lộ field nội bộ.

## 5. MongoDB: projection dạng exclusion và quy tắc phối hợp

MongoDB cũng cho phép **loại trừ** trường không cần bằng `0`:

~~~javascript
db.products.find(
  { tenantId: "T17", productId: "P1001" },
  {
    internalNotes: 0,
    supplierCostMinor: 0,
    auditTrail: 0
  }
);
~~~

Cách này giữ phần lớn nội dung document và bỏ một số trường không mong muốn.

### Không trộn tùy ý inclusion và exclusion

Với projection thông thường của `find`, MongoDB **không cho trộn các chỉ định include và exclude tùy ý** trong cùng một projection. Ngoại lệ quen thuộc là **loại `_id`** khi đang dùng inclusion:

~~~javascript
// Hợp lệ: include trường cần lấy và bỏ _id.
db.products.find({}, {
  _id: 0,
  productId: 1,
  title: 1
});

// Không hợp lệ: include title nhưng exclude internalNotes
// trong projection find theo kiểu thông thường.
db.products.find({}, {
  title: 1,
  internalNotes: 0
});
~~~

Khi cần nhiều phép biến đổi, biểu thức computed hoặc lựa chọn phức tạp, hãy cân nhắc **aggregation pipeline** thay vì cố nhồi mọi hành vi vào object projection của `find`.

### Inclusion và exclusion khác nhau khi schema thay đổi

Giả sử hôm nay document có 15 trường; ngày mai nhóm phát triển thêm `employeeOnlyMargin`.

- Projection dạng **inclusion** chỉ có các field đã cho phép, nên field mới **không tự xuất hiện**.
- Projection dạng **exclusion** chỉ bỏ các trường đã biết, nên field mới có thể **xuất hiện ngoài dự kiến** nếu endpoint trả thẳng kết quả.

Vì vậy với **API public và dữ liệu nhạy cảm**, danh sách cho phép (*allowlist/inclusion*) thường an toàn hơn danh sách từ chối (*denylist/exclusion*).

Đây vẫn **không phải cơ chế authorization đầy đủ**: phải kiểm tra tenant, chủ sở hữu, vai trò và quyền trên từng bản ghi hoặc trường trước khi trả dữ liệu.

## 6. Projection trường lồng nhau trong document

Document NoSQL thường có object lồng nhau:

~~~json
{
  "productId": "P1001",
  "title": "Sổ tay bìa cứng",
  "manufacturer": {
    "name": "Nhà máy A",
    "address": {
      "city": "Đà Nẵng",
      "street": "Thông tin nội bộ"
    },
    "phone": "Thông tin nội bộ"
  },
  "dimensions": {
    "widthMm": 145,
    "heightMm": 210,
    "weightG": 300
  }
}
~~~

Nếu UI chỉ hiển thị tên nhà sản xuất và kích thước hai chiều, MongoDB có thể dùng **dot notation**:

~~~javascript
db.products.find(
  { productId: "P1001" },
  {
    _id: 0,
    productId: 1,
    title: 1,
    "manufacturer.name": 1,
    "dimensions.widthMm": 1,
    "dimensions.heightMm": 1
  }
);
~~~

Kết quả dự kiến theo dữ liệu mẫu:

~~~json
{
  "productId": "P1001",
  "title": "Sổ tay bìa cứng",
  "manufacturer": {
    "name": "Nhà máy A"
  },
  "dimensions": {
    "widthMm": 145,
    "heightMm": 210
  }
}
~~~

Projection chọn field lồng nhau nhưng **không tự làm phẳng** thành `manufacturerName` hoặc `widthMm` ở top-level. Muốn đổi cấu trúc đầu ra, dùng aggregation `$project` hoặc mapping có kiểm soát ở backend.

### Missing, null và optional fields

Với document linh hoạt, không phải mọi tài liệu đều có `manufacturer.name`. Khi projection yêu cầu một trường thiếu, kết quả không nhất thiết có trường đó. Điều này khác với trường được lưu rõ ràng bằng `null`.

Ứng dụng nên xác định:

- Trường có **bắt buộc** với API này không?
- Nếu không có, trả `null`, bỏ trường hay dùng giá trị mặc định?
- Giá trị mặc định là hiển thị UI hay có ý nghĩa nghiệp vụ?
- Tài liệu schema cũ có cần migration hoặc mapping tương thích không?

Projection không tự biến dữ liệu thiếu thành dữ liệu hợp lệ. Nó chỉ quyết định trường nào được đưa ra kết quả.

## 7. Projection trên mảng: đừng nhầm chọn trường với giới hạn phần tử

Giả sử một sản phẩm có mảng ảnh:

~~~json
{
  "productId": "P1001",
  "images": [
    {"url": "img-1.jpg", "width": 1600, "height": 900},
    {"url": "img-2.jpg", "width": 1600, "height": 900},
    {"url": "img-3.jpg", "width": 1600, "height": 900}
  ]
}
~~~

Nếu projection yêu cầu `images.url`, nó lựa chọn field `url` trong các phần tử liên quan; **không có nghĩa chỉ giữ một phần tử ảnh**:

~~~javascript
db.products.find(
  { productId: "P1001" },
  { _id: 0, productId: 1, "images.url": 1 }
);
~~~

Để giới hạn **số phần tử** của một mảng khi dùng `find`, MongoDB có toán tử projection `$slice`:

~~~javascript
db.products.find(
  { productId: "P1001" },
  {
    _id: 0,
    productId: 1,
    images: { $slice: 2 }
  }
);
~~~

Ví dụ này yêu cầu **tối đa hai phần tử đầu của mảng `images`**, nhưng mỗi phần tử được trả có thể vẫn chứa các thuộc tính khác nhau theo cấu trúc gốc.

### Có thể vừa chọn phần tử vừa chọn thuộc tính không?

Khi muốn “hai ảnh đầu, mỗi ảnh chỉ có URL”, cần hiểu giới hạn cú pháp projection và hành vi của phiên bản MongoDB. Một phương án rõ ràng là dùng **aggregation** với `$slice` và `$map` để tạo mảng đầu ra mới:

~~~javascript
db.products.aggregate([
  {
    $match: { tenantId: "T17", productId: "P1001" }
  },
  {
    $project: {
      _id: 0,
      productId: 1,
      thumbnails: {
        $map: {
          input: {
            $slice: [
              { $ifNull: ["$images", []] },
              2
            ]
          },
          as: "image",
          in: {
            url: "$$image.url"
          }
        }
      }
    }
  }
]);
~~~

Kết quả:

~~~json
{
  "productId": "P1001",
  "thumbnails": [
    {"url": "img-1.jpg"},
    {"url": "img-2.jpg"}
  ]
}
~~~

Đây là **computed projection**: không chỉ chọn field mà còn **định hình mảng đầu ra** bằng các toán tử.

### `$elemMatch` có nghĩa khác `$filter`

Trong một số trường hợp MongoDB `find` có projection `$elemMatch` để lấy **phần tử mảng đầu tiên phù hợp** một điều kiện. Nó không phải lựa chọn để trả **mọi phần tử** khớp.

Nếu muốn nhiều phần tử đáp ứng điều kiện, aggregation với `$filter` thường phù hợp hơn. Cần phân biệt ba yêu cầu:

1. Lấy **toàn mảng** nhưng chỉ một vài thuộc tính.
2. Lấy **N phần tử đầu/cuối**.
3. Lấy **những phần tử phù hợp điều kiện**.

Projection trên field không tự giải quyết cả ba yêu cầu.

## 8. Projection trong MongoDB aggregation pipeline

MongoDB có stage `$project` trong aggregation. Nó hữu ích khi cần:

- Chọn một tập trường.
- Đổi tên field.
- Tính toán trường mới.
- Loại bỏ các trường trung gian.
- Định hình object/mảng trong response.

Ví dụ API danh sách đơn hàng cần mã, tiền, trạng thái và tên người mua:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "T17",
      status: "PAID"
    }
  },
  {
    $sort: {
      createdAt: -1,
      orderId: -1
    }
  },
  {
    $limit: 20
  },
  {
    $project: {
      _id: 0,
      orderId: 1,
      status: 1,
      createdAt: 1,
      totalMinor: 1,
      currency: 1,
      customerName: "$customerSnapshot.displayName"
    }
  }
]);
~~~

Ở đây:

- `$match` xác định tập đơn hàng.
- `$sort` tạo thứ tự.
- `$limit` giới hạn số đơn.
- `$project` chọn các trường và đổi đường dẫn lồng nhau `customerSnapshot.displayName` thành `customerName`.

Kết quả chỉ chứa trường đã tạo/chọn trong stage `$project`, giả định dữ liệu nguồn đầy đủ.

### Projection có biểu thức tính toán

Giả sử hệ thống lưu số tiền bằng minor units, API muốn thêm tổng số lượng sản phẩm:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "T17", orderId: "O1001" } },
  {
    $project: {
      _id: 0,
      orderId: 1,
      totalMinor: 1,
      currency: 1,
      lineCount: {
        $size: { $ifNull: ["$items", []] }
      }
    }
  }
]);
~~~

`$size` đếm phần tử mảng `items`. `$ifNull` trả mảng rỗng trong ví dụ nếu `items` null hoặc thiếu; tuy nhiên nếu field chứa giá trị **không phải mảng**, biểu thức vẫn cần có validation/schema phù hợp.

### Khi nào không nên tính toán ngay trong projection?

Một biểu thức như “tổng tiền sau thuế”, “số dư có thể rút”, “giá được phép thanh toán” có thể cần quy tắc nghiệp vụ phức tạp, làm tròn và kiểm soát đồng thời. Không nên tự thêm công thức vào `$project` chỉ để giảm code backend nếu điều đó làm **hai nơi tính ra hai kết quả khác nhau**.

Nên cân nhắc:

- Phép tính chỉ để **hiển thị** hay quyết định một giao dịch?
- Có cần precision/decimal và quy tắc làm tròn chặt chẽ không?
- Có thực hiện được trên các kiểu dữ liệu đang lưu không?
- Có làm tăng CPU trên DBMS khi query chạy nhiều lần không?
- Một trường tính sẵn có được dùng liên tục tới mức nên xây read model riêng không?

Projection nên làm nhẹ dữ liệu trả về, chứ không tự biến DBMS thành nơi triển khai toàn bộ nghiệp vụ nếu chi phí và quy tắc chưa được làm rõ.

## 9. Đặt projection ở đâu trong pipeline?

Trong một pipeline nhiều stage, vị trí projection có thể ảnh hưởng cả hiệu năng lẫn tính đúng đắn.

Giả sử:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "T17" } },
  { $project: { _id: 0, orderId: 1, totalMinor: 1 } },
  { $sort: { createdAt: -1 } },
  { $limit: 20 }
]);
~~~

Trong cách viết này, stage `$project` **đã bỏ `createdAt` trước khi `$sort` cần dùng nó**. Do đó pipeline không còn đủ dữ liệu để sắp xếp đúng theo thời gian tạo. Cách sắp xếp và kết quả có thể không phản ánh yêu cầu.

Một cấu trúc rõ hơn:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "T17" } },
  { $sort: { createdAt: -1, orderId: -1 } },
  { $limit: 20 },
  {
    $project: {
      _id: 0,
      orderId: 1,
      totalMinor: 1
    }
  }
]);
~~~

**Nguyên tắc tư duy:** một stage không nên loại bỏ field trước khi stage sau cần nó để lọc, sắp xếp, group hoặc tính toán.

Tuy nhiên, điều này không có nghĩa “luôn phải đặt `$project` cuối cùng”. MongoDB có bộ tối ưu hóa pipeline và khả năng tự rút gọn trường cần thiết trong nhiều trường hợp. Nếu projection chủ động bỏ một blob cực lớn ở bước trước một phép xử lý đắt đỏ, cần đánh giá bằng kế hoạch thực thi thực tế.

Khi làm việc với nhiều stage:

1. Viết đúng **ngữ nghĩa** của kết quả trước.
2. Đảm bảo những stage cần field nào vẫn còn field đó.
3. Xem query plan/`explain` thay vì suy đoán chỉ từ vị trí cú pháp.
4. Chỉ tối ưu pipeline khi có bằng chứng về nút thắt CPU, RAM, index hoặc mạng.

## 10. Projection và covered query

Đây là một trong những liên hệ quan trọng nhất giữa **projection** và **hiệu năng truy vấn**.

Giả sử có index MongoDB:

~~~javascript
db.products.createIndex({
  tenantId: 1,
  categoryId: 1,
  status: 1,
  createdAt: -1,
  productId: -1,
  title: 1,
  priceMinor: 1,
  currency: 1
});
~~~

Một truy vấn:

~~~javascript
db.products.find(
  {
    tenantId: "T17",
    categoryId: "stationery",
    status: "ACTIVE"
  },
  {
    _id: 0,
    productId: 1,
    title: 1,
    priceMinor: 1,
    currency: 1
  }
).sort({
  createdAt: -1,
  productId: -1
}).limit(20);
~~~

Các trường dùng để lọc, sắp xếp và trả kết quả **đều xuất hiện trong index minh họa**. Tùy kế hoạch thực thi, loại index và các điều kiện khác, MongoDB có thể xử lý truy vấn bằng **index keys** mà không cần đọc toàn bộ document.

Một truy vấn như vậy thường được gọi là **covered query** khi toàn bộ thông tin cần cho điều kiện và kết quả được lấy từ index theo cơ chế DBMS.

### Phân biệt “projection nhỏ” với “covered query”

~~~text
Trường hợp A — index tìm vị trí, phải fetch document:

Index scan
    │
    ▼
Fetch full document from collection
    │
    ▼
Projection chọn field
    │
    ▼
Network response

Trường hợp B — query có thể được index bao phủ:

Index scan
    │
    ▼
Lấy field trực tiếp từ index keys
    │
    ▼
Network response
~~~

**Trường hợp A** có thể giảm dữ liệu gửi qua mạng nhưng DBMS vẫn phải fetch tài liệu. **Trường hợp B**, nếu thực sự được áp dụng, còn có thể tránh fetch tài liệu nguồn cho các dòng kết quả.

### Cẩn thận với `_id`

MongoDB thường trả `_id` mặc định. Nếu index không chứa `_id` mà projection vẫn yêu cầu nó, truy vấn có thể **không được bao phủ** chỉ vì thiếu field này. Do đó trong những trường hợp cần không trả `_id`, dùng `_id: 0` rõ ràng.

### Index rộng không phải lúc nào cũng tốt

Index chứa 8 trường có thể lớn hơn, tăng chi phí ghi/cập nhật và sử dụng RAM/disk nhiều hơn index chứa 3 trường. Việc cố thêm mọi field của response vào index có thể **làm toàn bộ workload đắt đỏ hơn**.

Những cân nhắc chính:

- Tần suất query và lợi ích latency khi tránh fetch.
- Kích thước và số lượng index.
- Tần suất cập nhật các trường được lập chỉ mục.
- Mức độ chọn lọc của điều kiện lọc.
- Sort có phù hợp thứ tự khóa index không.
- Các trường có phải array/multikey hoặc dữ liệu quá lớn không.
- Tác động khi schema hoặc projection thay đổi.

**Không nên nhầm câu “query có projection” với kết luận “query được covering index”.** Covered query là đặc tính của kế hoạch thực thi thực tế.

## 11. Đo kết quả projection bằng explain và telemetry

Ví dụ MongoDB:

~~~javascript
db.products.find(
  {
    tenantId: "T17",
    categoryId: "stationery",
    status: "ACTIVE"
  },
  {
    _id: 0,
    productId: 1,
    title: 1,
    priceMinor: 1,
    currency: 1
  }
).sort({
  createdAt: -1,
  productId: -1
}).limit(20).explain("executionStats");
~~~

Khi đọc `explain`, có thể quan tâm:

| Thành phần | Cần tìm hiểu |
| --- | --- |
| `totalDocsExamined` | Có bao nhiêu document nguồn được xem xét? |
| `totalKeysExamined` | Có bao nhiêu key index được duyệt? |
| `nReturned` | Trả bao nhiêu kết quả? |
| Các stage index/fetch/projection | Có bước fetch document nguồn hay không? |
| Sort stage | Có phải sắp xếp thêm ngoài khả năng index không? |
| Thời gian và thống kê thực thi | Có cải thiện dưới dữ liệu, tải và cấu hình đại diện không? |

Không được suy ra rằng `totalDocsExamined` giảm chỉ vì output ít trường. Nếu filter không có index phù hợp, truy vấn vẫn có thể phải xét nhiều document.

### Các phép đo ở ứng dụng

Ngoài query plan, nên đo:

- **Response bytes DB → ứng dụng** trên cùng bộ lọc và số kết quả.
- **Thời gian query** ở p50, p95, p99 dưới mức tải đại diện.
- **CPU của DBMS** và **CPU của backend**.
- **Bộ nhớ đỉnh** khi nhận và chuyển đổi danh sách.
- **Số document thực sự xem xét** và tỷ lệ examined/returned.
- **Dung lượng HTTP response** nếu có thay đổi DTO trả client.
- **Tổng số request** khi projection làm ứng dụng cần gọi thêm DB để lấy field bị thiếu.

Ví dụ, trước khi đổi:

~~~text
50 documents × ~24 KiB = ~1.200 KiB result
backend maps to 1 KiB/card
~~~

Sau khi đổi:

~~~text
50 documents × ~1 KiB = ~50 KiB result
backend maps without full payload
~~~

Nếu query latency hầu như không đổi vì bị giới hạn bởi filter/IO, projection vẫn có thể có lợi ở mạng hoặc backend RAM. Nhưng phải ghi đúng kết quả đo, không tự tuyên bố index scan nhanh gấp 24 lần.

## 12. Projection không thay thế phân trang

Giả sử collection chứa 3 triệu sự kiện. Một truy vấn:

~~~javascript
db.events.find(
  { tenantId: "T17" },
  { _id: 0, eventId: 1, occurredAt: 1 }
);
~~~

chỉ trả hai field, nhưng nếu trả 3 triệu tài liệu thì vẫn có chi phí lớn về quét, truyền, memory và thời gian xử lý.

Ứng dụng thường cần:

~~~javascript
db.events.find(
  {
    tenantId: "T17",
    occurredAt: {
      $gte: ISODate("2026-11-01T00:00:00Z"),
      $lt: ISODate("2026-12-01T00:00:00Z")
    }
  },
  {
    _id: 0,
    eventId: 1,
    occurredAt: 1
  }
).sort({
  occurredAt: -1,
  eventId: -1
}).limit(100);
~~~

Ở ví dụ này, **filter theo tenant/thời gian**, **sort ổn định**, **limit** và **projection** phối hợp để trả số lượng dữ liệu phù hợp.

### Cursor/keyset pagination

Với bảng hoặc collection lớn, pagination bằng offset cao có thể tốn kém và dễ gặp dịch chuyển dữ liệu khi có ghi đồng thời. Một thiết kế dùng cursor có thể dựa trên cặp `(occurredAt, eventId)`:

~~~text
Page 1:
  ORDER BY occurredAt DESC, eventId DESC
  LIMIT 100

Cursor:
  (lastOccurredAt, lastEventId)

Page 2:
  Đọc tiếp các event có key sắp xếp nhỏ hơn cursor,
  cùng filter, quyền và phiên bản ngữ nghĩa.
~~~

**Cursor cũng là một phần của projection hợp đồng API**: nếu backend cần `occurredAt` và `eventId` để tạo next cursor nhưng query bỏ chúng, phải điều chỉnh projection hoặc tạo cursor ở phía DB thích hợp.

Không nên xóa field sort khỏi dữ liệu trung gian quá sớm nếu ứng dụng còn cần nó cho phân trang, chống trùng hoặc đối soát.

## 13. Projection trong Redis: hash field so với giá trị JSON nguyên khối

Redis là key–value store với nhiều kiểu cấu trúc dữ liệu. Cách lấy một phần giá trị phụ thuộc **kiểu dữ liệu được chọn**.

### Trường hợp A — JSON được lưu dưới dạng Redis string

~~~redis
SET cache:product:P1001 '{"productId":"P1001","title":"Sổ tay","priceMinor":89000,"description":"..."}' EX 300
GET cache:product:P1001
~~~

Với Redis string chứa JSON thường, lệnh `GET` trả **toàn bộ chuỗi giá trị**. Redis không tự biết cấu trúc các field JSON bên trong string để thực hiện `GET only title`.

Muốn chọn field từ JSON được lưu theo cách này, ứng dụng có thể:

- Đọc chuỗi rồi parse/cắt trường ở backend.
- Thiết kế lại các key theo access pattern.
- Dùng một kiểu dữ liệu/hỗ trợ JSON có khả năng truy cập theo đường dẫn nếu được triển khai.

Việc bỏ trường ở backend **không giảm payload Redis → backend** trong trường hợp `GET` nguyên chuỗi.

### Trường hợp B — Redis hash có thể đọc field riêng

~~~redis
HSET cache:product:P1001 productId "P1001" title "Sổ tay" priceMinor "89000" currency "VND" description "..."
EXPIRE cache:product:P1001 300
~~~

Đọc tất cả field:

~~~redis
HGETALL cache:product:P1001
~~~

Chỉ đọc một field:

~~~redis
HGET cache:product:P1001 title
~~~

Đọc vài field:

~~~redis
HMGET cache:product:P1001 title priceMinor currency
~~~

`HMGET` giúp ứng dụng chỉ nhận những field đã yêu cầu từ Redis hash, thay vì `HGETALL`. Đây là **projection theo cấu trúc hash**.

### Những đánh đổi của hash

- Cần định nghĩa cách lưu giá trị scalar, số và trường thiếu.
- Object/mảng lồng nhau cần cách mã hóa hoặc cấu trúc khác.
- Việc thay đổi từng field có ngữ nghĩa khác thay thế nguyên chuỗi JSON.
- TTL trong Redis gắn với **key**, không tự phân biệt thời hạn cho từng field hash trong mô hình minh họa này.
- Hash không tự bảo đảm quyền truy cập theo từng field nếu ứng dụng dùng chung tài khoản đọc toàn bộ key.

Nếu ứng dụng luôn đọc/ghi toàn bộ object và object nhỏ, Redis string chứa JSON có thể đơn giản hơn. Không cần đổi mọi cache item sang hash chỉ để tối ưu một truy vấn hiếm.

## 14. Projection trong DynamoDB: tiết kiệm dữ liệu trả về chưa chắc tiết kiệm read capacity

Amazon DynamoDB hỗ trợ **ProjectionExpression** để chọn thuộc tính xuất hiện trong kết quả của các thao tác đọc.

Ví dụ API mức thấp, ý tưởng:

~~~json
{
  "TableName": "Products",
  "Key": {
    "pk": {"S": "TENANT#T17"},
    "sk": {"S": "PRODUCT#P1001"}
  },
  "ProjectionExpression": "productId, title, priceMinor"
}
~~~

Đây là cấu trúc yêu cầu minh họa cho `GetItem` theo kiểu AttributeValue của DynamoDB. Trong ứng dụng thực tế, phải dùng SDK, tên bảng và khóa đúng schema, đồng thời dùng `ExpressionAttributeNames` nếu field name là từ khóa dành riêng hoặc có ký tự đặc biệt.

Ý nghĩa là chỉ trả về các thuộc tính đã chọn trong kết quả.

### Điểm rất dễ hiểu sai: RCU

Trong DynamoDB, **read capacity được tính theo kích thước item được đọc và kiểu nhất quán của thao tác**, chứ không chỉ theo số byte của các thuộc tính được trả về. Vì vậy, thêm `ProjectionExpression` có thể:

- **Giảm payload response và chi phí mạng.**
- **Giảm dữ liệu ứng dụng phải xử lý.**
- Nhưng **không mặc định giảm số read capacity units của thao tác đọc cùng item**.

Đây là sự khác biệt quan trọng với suy luận “trả 10% field thì phí đọc chỉ còn 10%”.

### Projection của index khác projection của kết quả

DynamoDB cho phép định nghĩa thuộc tính nào được **projected vào secondary index**; cách này thuộc **thiết kế index**, khác với `ProjectionExpression` của một lần đọc.

Ví dụ trên global secondary index (GSI), các thuộc tính sẵn có là khóa của index, khóa chính bảng và các thuộc tính được project tùy định nghĩa index. Một query GSI cần thuộc tính không có trong index thì không thể mặc định DBMS tự lấy chúng từ bảng nguồn như một index covering ở mọi hệ.

Vì vậy:

| Loại projection | Ý nghĩa chính |
| --- | --- |
| `ProjectionExpression` khi đọc | Giới hạn thuộc tính **trả về** |
| Index projection khi tạo GSI/LSI | Quyết định thuộc tính **được lưu trong index** |

Hai khái niệm có liên quan nhưng không thay thế nhau. Khi thiết kế cần xác định đường truy cập nào dùng base table, đường nào dùng index và field nào cần có ở mỗi nơi.

### FilterExpression cũng không giải quyết tất cả

Một query/scan có `FilterExpression` và `ProjectionExpression` không có nghĩa DynamoDB chỉ phải đọc những item cuối cùng được trả về. Phép lọc có thể diễn ra sau khi dữ liệu đã được đọc ở phạm vi của thao tác, theo ngữ nghĩa DynamoDB. Do vậy cần phân biệt **item được đọc**, **item khớp filter** và **thuộc tính được trả**.

## 15. Projection trong Cassandra và các hệ wide-column

Với CQL, ứng dụng có thể chọn các cột:

~~~sql
SELECT order_id, created_at, status, total_minor
FROM orders_by_customer_month
WHERE tenant_id = 'T17'
  AND customer_id = 'C42'
  AND bucket_month = '2026-11'
LIMIT 20;
~~~

So với:

~~~sql
SELECT *
FROM orders_by_customer_month
WHERE tenant_id = 'T17'
  AND customer_id = 'C42'
  AND bucket_month = '2026-11'
LIMIT 20;
~~~

Truy vấn đầu chỉ đưa những cột được chọn vào kết quả. Điều này có thể giảm serialization và băng thông cho những cột payload không cần.

### Partition key vẫn là nền tảng

Trong Cassandra, một truy vấn hiệu quả thường cần xác định đúng partition key/clustering range theo mô hình bảng. Việc chọn ít cột không tự sửa được một query thiếu đường truy cập phù hợp.

Ví dụ một bảng theo khách hàng/tháng chưa chắc phục vụ tốt yêu cầu “mọi đơn trạng thái PAID của tenant trong ngày” khi không biết `customer_id`, dù projection chỉ có một cột `order_id`.

### Không nhầm cột rộng với việc có thể lấy mọi field theo ý thích

Hệ wide-column có cách tổ chức dữ liệu và chi phí truy cập khác document store. Việc `SELECT` vài cột có giúp ít I/O vật lý hơn hay không phụ thuộc tổ chức SSTable, clustering, loại cột, bộ nhớ đệm, index và lượng dữ liệu cần quét. Hãy đo theo workload và phiên bản DBMS thực tế.

Nếu một ứng dụng có hai mẫu truy vấn khác nhau về khóa lọc/sort, projection không tự làm chúng dùng chung một bảng hiệu quả. Có thể cần **bảng đọc theo access pattern** hoặc read model khác.

## 16. Projection kết quả và projection dữ liệu dẫn xuất là hai việc khác nhau

Từ “projection” đôi khi xuất hiện ở hai tầng:

**A. Query projection — chọn trường trong kết quả của một truy vấn**

~~~text
products collection
    │ find(..., projection={title, priceMinor})
    ▼
title, priceMinor
~~~

Không nhất thiết tạo dữ liệu lưu mới. Mỗi truy vấn chọn những trường cần trả tại thời điểm đọc.

**B. Read-model projection — tạo biểu diễn dữ liệu dẫn xuất phục vụ đường đọc**

~~~text
Product source of truth
         │
   ProductChanged events
         │
         ▼
 product_cards_by_category
   {productId, title, priceMinor, thumbnailUrl}
         │
         ▼
   Danh sách sản phẩm
~~~

Ở cách B, hệ thống **duy trì một bản dữ liệu khác** được thiết kế cho một nhóm truy vấn. Đây có thể được gọi là *projection* trong kiến trúc CQRS/materialized read model.

| Khía cạnh | Query projection | Read-model projection |
| --- | --- | --- |
| Có lưu thêm bản sao dữ liệu? | Thường không | Có |
| Có đường cập nhật riêng? | Không nhất thiết | Có; phải đồng bộ khi nguồn đổi |
| Giảm trường trả về? | Có | Có thể |
| Giải quyết truy vấn theo khóa khác? | Không tự động | Có thể, nếu read model có khóa/index phù hợp |
| Rủi ro dữ liệu trễ? | Theo nguồn đang đọc | Có thể có lag khi đồng bộ bất đồng bộ |
| Chi phí | Truy vấn và xử lý kết quả | Lưu trữ, ghi dẫn xuất, đồng bộ, rebuild, đối soát |

### Khi nào cần read-model projection?

Nếu API danh sách sản phẩm chỉ cần 5 trường nhưng vẫn phải **lọc theo danh mục, sắp theo doanh số và gộp điểm đánh giá từ hệ khác**, một query projection của collection nguồn có thể chưa đủ. Một read model chuyên dụng có thể hợp lý khi:

- Truy vấn yêu cầu **đường khóa/sort khác** với dữ liệu nguồn.
- Cần kết hợp nhiều nguồn mà API được phép dùng dữ liệu trễ.
- Phép tính được dùng lặp lại và tốn kém.
- Muốn cô lập tải đọc khỏi tải giao dịch.

Nhưng phải định nghĩa **nguồn có thẩm quyền**, cơ chế cập nhật, xử lý sự kiện lặp/đến trễ, độ trễ được phép và cách rebuild projection.

**Không nên tạo read model riêng chỉ để thay thế một projection field đơn giản đã đáp ứng nhu cầu.**

## 17. Projection và bảo mật dữ liệu

Chọn đúng trường làm giảm nguy cơ gửi dữ liệu nhạy cảm không cần thiết. Tuy nhiên, **field-level selection không đồng nghĩa field-level authorization**.

Giả sử document khách hàng:

~~~json
{
  "customerId": "C42",
  "displayName": "An",
  "email": "an@example.invalid",
  "phone": "0900000000",
  "shippingAddresses": [
    {"city": "Đà Nẵng", "details": "Thông tin riêng"}
  ],
  "riskScore": 0.8,
  "internalSupportNotes": "Không công khai"
}
~~~

Trang hồ sơ công khai chỉ cần:

~~~javascript
db.customers.find(
  { customerId: "C42" },
  {
    _id: 0,
    customerId: 1,
    displayName: 1
  }
);
~~~

Nhưng trong ứng dụng nhiều tenant hoặc có quyền theo người dùng, query còn phải bảo đảm **đúng đối tượng được phép truy cập**, không chỉ đúng những field được trả.

### Ba lớp cần phân biệt

1. **Authentication:** ai đang thực hiện yêu cầu?
2. **Authorization:** người đó có quyền xem document/field này không?
3. **Projection:** sau khi có đường truy cập hợp lệ, những field nào thật sự cần trả?

Một câu query lấy `displayName` của **khách hàng không được phép xem** vẫn là lỗi phân quyền, dù không trả số điện thoại.

### Không cho client tùy ý yêu cầu field nội bộ

Một API GraphQL/REST có lựa chọn field có thể nhận:

~~~text
GET /customers/C42?fields=displayName,riskScore,internalSupportNotes
~~~

Nếu backend xây projection trực tiếp từ `fields` mà không đối chiếu **allowlist theo quyền**, client có thể lấy dữ liệu không được công bố. Nên kiểm tra tên field, quyền và giới hạn độ sâu/kích thước selection trước khi tạo truy vấn.

Ví dụ pseudocode:

~~~javascript
const publicFields = new Set([
  "customerId",
  "displayName"
]);

function validateRequestedFields(requested) {
  for (const field of requested) {
    if (!publicFields.has(field)) {
      throw new Error("Field not allowed");
    }
  }
}
~~~

Trong hệ có nhiều vai trò, danh sách cho phép phải đi theo quyền cụ thể. Với field lồng nhau hoặc biểu thức động, cần chặn việc truy cập đường dẫn nội bộ hay alias không được phép.

### Projection tại DB không thay thế che dữ liệu nhạy cảm

Một endpoint chỉ lấy `email` khi người dùng được phép; một endpoint khác có thể cần dạng che `a***@example.invalid`. Khi đó quy tắc **masking/redaction** có thể diễn ra ở DBMS hoặc backend tùy kiến trúc, nhưng vẫn phải bảo đảm một nơi có thẩm quyền áp dụng đúng chính sách.

Không ghi log toàn bộ document chỉ để debug trong lúc response đã dùng projection. Nhật ký, traces và error dump có thể là một đường rò rỉ dữ liệu khác.

## 18. Chiến lược projection theo từng màn hình và API

Một ứng dụng thương mại điện tử có ít nhất ba đường đọc sản phẩm:

| Đường đọc | Các field cần thiết | Những field thường không cần |
| --- | --- | --- |
| **Danh sách sản phẩm** | ID, tên, giá, tiền tệ, thumbnail, trạng thái hiển thị | Description dài, tất cả ảnh, audit |
| **Chi tiết sản phẩm** | ID, tên, giá, description, ảnh, thuộc tính, thông tin hiển thị | Giá vốn nhà cung cấp, ghi chú nội bộ |
| **Trang admin chỉnh sửa** | ID, version, dữ liệu chỉnh sửa phù hợp quyền, trạng thái | Dữ liệu cá nhân không liên quan, log toàn bộ |

Một thiết kế query shape có thể viết:

~~~yaml
accessPatterns:
  - id: PRODUCT-LIST
    filter: "tenantId + categoryId + status"
    sort: "createdAt DESC, productId DESC"
    pageSize: 20
    projection:
      - productId
      - title
      - priceMinor
      - currency
      - thumbnailUrl

  - id: PRODUCT-DETAIL
    filter: "tenantId + productId"
    projection:
      - productId
      - title
      - priceMinor
      - currency
      - description
      - images
      - attributes

  - id: PRODUCT-ADMIN-EDIT
    filter: "authorized tenant + productId"
    projection:
      - productId
      - title
      - priceMinor
      - currency
      - status
      - revision
~~~

Đây là **đặc tả access pattern minh họa**, không phải cấu hình MongoDB tự chạy. Ý nghĩa là tập field được chọn phải xuất phát từ **nhu cầu sử dụng** chứ không phải từ thói quen luôn `SELECT *`.

### Chọn trường tối thiểu nhưng đủ cho nghiệp vụ

Lấy ít field không phải lúc nào cũng tốt. Ví dụ một API cập nhật có điều kiện cần `revision` để thực hiện optimistic concurrency control:

~~~text
GET product for edit:
  productId, title, priceMinor, revision

PATCH product:
  expectedRevision = revision đã đọc
~~~

Nếu projection bỏ `revision` nhưng backend cần nó để tránh ghi đè thay đổi đồng thời, ứng dụng có thể phát sinh request phụ hoặc xử lý sai. **Trường cần thiết** bao gồm cả field phục vụ validation, phân quyền, cursor, concurrency và mapping, không chỉ field hiển thị.

## 19. Một projection tốt phải ổn định trước schema linh hoạt

NoSQL document có thể phát triển theo phiên bản:

~~~json
{
  "schemaVersion": 1,
  "productId": "P1001",
  "name": "Sổ tay",
  "price": 89000
}
~~~

Trong schema mới:

~~~json
{
  "schemaVersion": 2,
  "productId": "P1001",
  "title": "Sổ tay",
  "priceMinor": 89000,
  "currency": "VND"
}
~~~

Một projection chỉ lấy `title` và `priceMinor` sẽ không đủ để dựng response đúng cho tài liệu version 1.

### Hai hướng xử lý

**Hướng A — Migration dữ liệu nguồn** về một schema thống nhất, bảo đảm writer/reader và index phù hợp.

**Hướng B — Compatibility mapping** lấy các trường cần thiết từ nhiều version rồi chuẩn hóa đầu ra:

~~~javascript
db.products.aggregate([
  { $match: { tenantId: "T17" } },
  {
    $project: {
      _id: 0,
      productId: 1,
      title: { $ifNull: ["$title", "$name"] },
      priceMinor: { $ifNull: ["$priceMinor", "$price"] },
      currency: { $ifNull: ["$currency", "VND"] }
    }
  }
]);
~~~

Ví dụ trên giả định **price v1 và priceMinor v2 cùng biểu diễn đơn vị đồng VND**. Nếu schema cũ lưu tiền theo đơn vị khác, tuyệt đối không chỉ đổi tên field; phải chuyển giá trị theo một quy tắc đúng và có thể đối soát.

### Giá trị mặc định phải có nghĩa nghiệp vụ

`$ifNull` có thể giúp xử lý thiếu field, nhưng đặt currency mặc định `VND` chỉ đúng nếu domain đảm bảo dữ liệu cũ thực sự dùng VND. Nếu tài liệu cũ có nhiều loại tiền và không lưu currency, một fallback mặc định sẽ tạo dữ liệu có vẻ hợp lệ nhưng sai.

Projection không thay thế validation, data migration và schema contract.

## 20. Các anti-pattern khi dùng projection

| Anti-pattern | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Luôn dùng `find()` không projection cho danh sách | Trả về payload lớn, tốn mạng và RAM | Chỉ chọn field của màn hình |
| Dùng `SELECT *` trên dữ liệu nhiều trường lớn | Truyền trường không cần và tốn serialization | Chọn cột cần thiết |
| Backend nhận toàn bộ rồi cắt trường | Chặng DB → ứng dụng vẫn lớn | Projection tại DBMS khi hỗ trợ |
| Dùng exclusion cho public API | Field mới có thể lộ ngoài ý muốn | Inclusion allowlist và phân quyền |
| Nghĩ projection giúp tránh collection scan | Query vẫn thiếu index/partition key | Tối ưu đường lọc/sort riêng |
| Nghĩ projection luôn giảm read capacity | Sai với một số DBMS như DynamoDB | Hiểu cách tính chi phí đọc cụ thể |
| Đặt `$project` trước `$sort` rồi bỏ field sắp xếp | Sort sai hoặc không còn dữ liệu cần thiết | Đảm bảo stage sau còn trường cần |
| Chỉ chọn ít field nhưng trả hàng triệu bản ghi | Kết quả vẫn quá lớn | Phân trang, lọc và giới hạn |
| Bỏ trường dùng tạo cursor hoặc revision | API phải đọc thêm hoặc không kiểm soát concurrency | Ghi rõ field bắt buộc ngoài UI |
| Chuyển cả object lồng nhau khi chỉ cần một field | Mảng/object lớn vẫn được truyền | Dot projection hoặc computed projection |
| Dùng `HGETALL` Redis hash cho mọi request | Trả nhiều field không cần | `HGET`/`HMGET` |
| Gọi `GET` Redis string JSON rồi kỳ vọng chỉ lấy một field | GET trả nguyên chuỗi | Chọn data structure/JSON path phù hợp |
| Thêm mọi field vào covering index | Index phình to, làm ghi chậm | Đánh giá toàn workload và hiệu quả thực |
| Cho client nhập projection không kiểm soát | Lộ field nhạy cảm, query bất thường | Allowlist và giới hạn theo quyền |
| Projection theo schema mới nhưng tài liệu cũ thiếu field | Response không đúng hoặc thiếu dữ liệu | Compatibility mapping/migration |
| Lạm dụng projection computed cho nghiệp vụ tài chính | Logic và rounding phân tán nhiều nơi | Chọn nơi tính có thẩm quyền, kiểm tra precision |
| Tạo materialized read model chỉ để bỏ 2 field | Tăng chi phí đồng bộ không cần thiết | Bắt đầu bằng query projection |

## 21. Bài tập thực hành

### Bài 1 — Projection cho thẻ sản phẩm

Cho document:

~~~json
{
  "productId": "P77",
  "tenantId": "T17",
  "title": "Balo",
  "priceMinor": 350000,
  "currency": "VND",
  "thumbnailUrl": "bag-thumb.jpg",
  "description": "Một mô tả sản phẩm rất dài...",
  "images": ["bag-1.jpg", "bag-2.jpg"],
  "supplierCostMinor": 270000
}
~~~

Viết truy vấn MongoDB `find` chỉ trả `productId`, `title`, `priceMinor`, `currency`, `thumbnailUrl`, không trả `_id`. Vì sao không nên lấy `supplierCostMinor`?

**Gợi ý:** dùng inclusion projection với `_id: 0`. Giá vốn không phục vụ màn hình public, có thể là thông tin nội bộ.

### Bài 2 — So sánh filter với projection

Hai truy vấn:

~~~javascript
// A
db.products.find(
  { categoryId: "books" },
  { title: 1, priceMinor: 1, _id: 0 }
);

// B
db.products.find(
  { priceMinor: { $lt: 100000 } },
  { title: 1, priceMinor: 1, _id: 0 }
);
~~~

Chúng có cùng projection nhưng có nhất thiết cùng đường truy cập và chi phí thực thi không?

**Gợi ý:** không. Filter khác nhau, index và độ chọn lọc có thể khác. Projection chỉ quyết định field của kết quả.

### Bài 3 — Mảng ảnh

Một document có 200 phần tử `images`, mỗi phần tử có `url`, `width`, `height` và `metadata`. Màn hình chỉ hiển thị 3 URL đầu.

Giải thích vì sao projection `"images.url": 1` chưa đủ, rồi đề xuất một aggregation dùng `$slice` và `$map` để chỉ trả URL của tối đa 3 phần tử.

**Gợi ý:** chọn field trong từng phần tử khác với giới hạn số phần tử.

### Bài 4 — MongoDB và `_id`

Một query được kỳ vọng là covered query nhưng `explain` vẫn cho thấy bước fetch document. Query chọn `title` và `priceMinor`, nhưng không chỉ định `_id: 0`; index không chứa `_id`. Việc này có thể liên quan thế nào?

**Gợi ý:** `_id` được trả mặc định; nếu không nằm trong index, nó có thể phá điều kiện index coverage. Cần xem toàn bộ query plan.

### Bài 5 — Tính lưu lượng giảm nhờ projection

Một API trả 100 document/trang, mỗi document đầy đủ 12 KiB. Sau projection còn 1,5 KiB/document. Có 80 lượt tải trang/giây. Tính:

1. Dung lượng kết quả mỗi trang trước/sau.
2. Dung lượng kết quả mỗi giây trước/sau.
3. Phần trăm giảm payload.
4. Vì sao kết quả đó chưa cho biết query latency giảm tương ứng?

**Gợi ý:** trước 1.200 KiB/trang, sau 150 KiB/trang; payload giảm 87,5% theo giả định. Kế hoạch lọc/index/I/O vẫn có thể giống nhau.

### Bài 6 — Redis hash và JSON string

Một product cache lưu dưới dạng Redis string chứa JSON với 20 trường. API chỉ cần giá và currency. Nếu muốn giảm dữ liệu Redis → ứng dụng, những cách nào có thể cân nhắc? Vì sao chỉ mapping ở backend không đạt mục tiêu đó?

**Gợi ý:** Redis hash + `HMGET`, key riêng cho summary hoặc khả năng truy cập JSON theo path nếu được triển khai. `GET` string trả toàn bộ payload.

### Bài 7 — DynamoDB và RCU

Một item DynamoDB có kích thước lớn; query `GetItem` chỉ dùng `ProjectionExpression` trả hai thuộc tính. Có thể khẳng định read capacity giảm theo tỷ lệ byte được trả về không?

**Gợi ý:** không. Phải phân biệt dung lượng response và cách tính dung lượng item khi đọc.

### Bài 8 — Đặt vị trí `$project`

Cho pipeline:

~~~javascript
[
  { $match: { tenantId: "T17" } },
  { $project: { _id: 0, orderId: 1, totalMinor: 1 } },
  { $sort: { createdAt: -1 } },
  { $limit: 20 }
]
~~~

Phân tích vì sao pipeline chưa diễn đạt đúng yêu cầu “20 đơn mới nhất”, rồi sửa vị trí stage hoặc danh sách field.

**Gợi ý:** stage `$project` bỏ `createdAt` trước `$sort`. Có thể sort và limit trước khi bỏ field không cần trả về.

### Bài 9 — Không làm lộ thông tin nội bộ

Một API cho phép client truyền `fields=title,priceMinor,supplierCostMinor`. Tại sao việc dùng trực tiếp danh sách này làm MongoDB projection có thể nguy hiểm? Hãy viết quy tắc allowlist cho hai vai trò `CUSTOMER` và `CATALOG_ADMIN`.

**Gợi ý:** phân quyền theo vai trò; ngay cả khi field được cho phép, phải kiểm tra quyền truy cập document/tenant.

### Bài 10 — Khi nào cần read model?

Một màn hình cần top 20 sản phẩm bán chạy trong mỗi category, có tên và giá từ Product service cùng doanh số từ Order service. Projection đơn giản của collection sản phẩm đã đủ chưa?

**Gợi ý:** chưa chắc. Thứ tự bán chạy và dữ liệu thống kê có thể cần read model/projection dẫn xuất hoặc truy vấn tổng hợp khác; phải đánh giá độ mới và chi phí đồng bộ.

## 22. Hướng dẫn triển khai trong ứng dụng

Một checklist ngắn trước khi đưa projection vào một endpoint:

### Bước 1 — Viết hợp đồng response

Ví dụ:

~~~json
{
  "productId": "P1001",
  "title": "Sổ tay bìa cứng",
  "priceMinor": 89000,
  "currency": "VND",
  "thumbnailUrl": "thumb.jpg"
}
~~~

Nêu rõ field bắt buộc, có thể thiếu, đơn vị số tiền và quyền truy cập. Không lấy thẳng toàn bộ document DBMS làm API contract.

### Bước 2 — Xác định field phục vụ xử lý nội bộ

Ngoài field public có thể cần thêm:

~~~text
createdAt + productId → tạo cursor
revision             → optimistic concurrency
tenantId             → kiểm tra phạm vi theo thiết kế
schemaVersion        → mapping v1/v2
~~~

Không phải field nào backend cần cũng phải được gửi về client.

### Bước 3 — Chọn projection đúng ngay trong truy vấn

Với MongoDB:

~~~javascript
const cursor = db.collection("products").find(
  {
    tenantId: "T17",
    categoryId: "stationery",
    status: "ACTIVE"
  },
  {
    projection: {
      _id: 0,
      productId: 1,
      title: 1,
      priceMinor: 1,
      currency: 1,
      thumbnailUrl: 1,
      createdAt: 1
    }
  }
).sort({ createdAt: -1, productId: -1 }).limit(20);

const rows = await cursor.toArray();
~~~

Backend dùng `createdAt` và `productId` để tạo cursor, rồi có thể đưa dữ liệu qua DTO serializer chỉ chứa năm field public.

### Bước 4 — Kiểm tra filter, sort, index và pagination riêng

Projection không sửa một access pattern thiếu index hoặc dùng offset cực lớn. Phải đánh giá `tenantId + categoryId + status`, thứ tự `createdAt/productId` và số trang theo dữ liệu thực.

### Bước 5 — Đo trước/sau

Thu thập:

~~~text
Before:
  query latency p95
  DB response bytes/request
  backend memory at peak
  documents examined
  index keys examined

After:
  same metrics for same workload

Notes:
  dataset size
  index definitions
  query filter/sort
  client/driver version
  cache warm/cold state
~~~

Nếu thấy byte trả về giảm nhưng query vẫn chậm, tiếp tục điều tra bộ lọc, sort, hot partition và điều kiện index. Không mở rộng projection một cách ngẫu nhiên chỉ để cải thiện chỉ số không liên quan.

## 23. Tổng kết

**Projection** là thao tác chọn hoặc tạo các trường cần thiết trong kết quả truy vấn. Khi dùng đúng, nó có thể giảm **băng thông DBMS → ứng dụng**, chi phí deserialization, bộ nhớ backend và dữ liệu phải mapping; với index phù hợp, nó còn có thể giúp tạo **covered query**.

Để áp dụng hiệu quả trong NoSQL, hãy ghi nhớ:

1. **Projection khác filter/sort/pagination.** Nó xác định field trả về, không tự giải quyết cách tìm tài liệu.
2. **Chọn field tại DBMS khi có thể.** Cắt field sau khi đã truyền toàn bộ dữ liệu về backend không giảm payload DB → ứng dụng.
3. **Đọc đúng ngữ nghĩa từng hệ:** MongoDB `find`/`$project`, Redis `HMGET`, DynamoDB `ProjectionExpression`, Cassandra chọn cột bằng `SELECT` có những giới hạn và chi phí khác nhau.
4. **Không mặc định giảm I/O/RCU.** Projection giảm dữ liệu kết quả; việc giảm tài liệu phải fetch hoặc dung lượng tính phí đọc phụ thuộc storage engine, index và DBMS.
5. **Projection và index hỗ trợ nhau.** Covered query có thể tránh fetch nguồn, nhưng index rộng làm tăng chi phí ghi và lưu trữ.
6. **Giữ đủ field cho ứng dụng.** Cursor, revision, tenant scope, schema version hoặc validation có thể cần field không hiển thị trên UI.
7. **Không coi projection là authorization.** API phải kiểm tra quyền theo tài nguyên và chỉ cho phép những field được công bố; inclusion thường phù hợp hơn exclusion khi có dữ liệu nhạy cảm.
8. **Phân biệt query projection với read-model projection.** Một cái chọn field lúc đọc, cái kia tạo và duy trì dữ liệu dẫn xuất phục vụ access pattern.

**Nguyên tắc thực hành:** *trả đúng dữ liệu cần dùng, ở đúng nơi và đúng phạm vi quyền; đồng thời đo cả số byte truyền về lẫn chi phí tìm kiếm dữ liệu*. Đó là cách projection giúp các truy vấn NoSQL nhẹ hơn mà không đánh đổi tính đúng đắn của ứng dụng.
