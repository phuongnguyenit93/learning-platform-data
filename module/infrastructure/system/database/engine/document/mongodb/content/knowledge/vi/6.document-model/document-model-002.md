# Nhúng document và tham chiếu: tiêu chí lựa chọn

MongoDB lưu dữ liệu dưới dạng **document BSON** trong **collection**. Khi hai loại dữ liệu có quan hệ với nhau, ta thường có hai cách tổ chức: **nhúng (embedding)** dữ liệu liên quan vào cùng document, hoặc **tham chiếu (referencing)** bằng cách lưu định danh để truy xuất document ở collection khác khi cần. Quyết định này ảnh hưởng trực tiếp đến tốc độ đọc, số lần truy vấn, thao tác cập nhật, tính nhất quán, kích thước document và khả năng mở rộng hệ thống.

Bài học thuộc chủ đề **Mô hình document** trong MongoDB. Mục tiêu không phải đưa ra quy tắc “nhúng luôn nhanh hơn” hay “tham chiếu luôn sạch hơn”, mà là biết **khi nào nên chọn từng cách và tại sao**. Những ví dụ dùng `mongosh` và một hệ thống thương mại điện tử minh họa; các nguyên tắc cũng áp dụng cho blog, mạng xã hội, IoT và quản lý nghiệp vụ.

Sau bài này, bạn sẽ có thể:

- Phân biệt **embedded document**, **array of subdocuments**, **manual reference**, **DBRef** và dữ liệu sao chép có chủ đích.
- Phân tích **cardinality**, hướng truy cập, cách cập nhật, vòng đời và giới hạn tăng trưởng của quan hệ.
- Chọn cách biểu diễn các quan hệ **one-to-one**, **one-to-few**, **one-to-many không giới hạn** và **many-to-many**.
- Giải thích quan hệ giữa thiết kế document với **atomicity một document**, **transaction nhiều document** và **`$lookup`**.
- Áp dụng các mẫu thiết kế **subset**, **extended reference**, **snapshot**, **bucket** hoặc mô hình lai khi cần.
- Nhận diện những anti-pattern như **unbounded array**, duplication không có quy tắc đồng bộ và tham chiếu không có index phù hợp.

## 1. Khái niệm nền tảng

### 1.1. Nhúng (embedding)

**Embedding** nghĩa là đặt dữ liệu liên quan thành một **document lồng** hoặc một **mảng document lồng** ngay trong document cha. Ví dụ, một khách hàng có thông tin liên hệ và vài địa chỉ giao hàng:

~~~javascript
{
  _id: "C-100",
  name: "An",
  contact: {
    email: "an@example.test",
    phone: "0900000000"
  },
  shippingAddresses: [
    { addressId: "A1", city: "Hà Nội", isDefault: true },
    { addressId: "A2", city: "Đà Nẵng", isDefault: false }
  ]
}
~~~

Ở đây `contact` là **embedded document**; mỗi phần tử của `shippingAddresses` là một **subdocument** trong array. Một lần đọc document khách hàng có thể lấy được các thông tin liên quan mà không cần tìm ở collection khác.

~~~text
customers
└── Customer C-100
    ├── name
    ├── contact { email, phone }
    └── shippingAddresses [
          { addressId, city, isDefault },
          { addressId, city, isDefault }
        ]
~~~

Embedding hợp lý khi dữ liệu con **thường được đọc cùng cha**, **có số lượng nhỏ hoặc được giới hạn rõ ràng**, và có **vòng đời gắn với cha**. Ví dụ một hồ sơ có một đối tượng cấu hình cá nhân, hoặc một đơn hàng có tập mặt hàng được chốt tại thời điểm mua.

### 1.2. Tham chiếu (referencing)

**Referencing** nghĩa là dữ liệu liên quan tồn tại ở document riêng, còn document hiện tại lưu **ID của document kia**. Ví dụ:

~~~javascript
// Collection customers
{ _id: "C-100", name: "An", email: "an@example.test" }

// Collection orders
{
  _id: "O-1001",
  customerId: "C-100",
  status: "PAID",
  total: 290000
}
~~~

~~~text
customers                        orders
┌────────────────────┐          ┌───────────────────────┐
│ _id: C-100         │ <------- │ customerId: C-100     │
│ name: An           │          │ _id: O-1001           │
└────────────────────┘          │ total: 290000         │
                              └───────────────────────┘
~~~

Ví dụ trên dùng **manual reference**: tự định nghĩa field `customerId` có cùng giá trị và **cùng kiểu BSON** với `customers._id`. MongoDB không tự biến field này thành ràng buộc khóa ngoại. Muốn hiển thị tên khách hàng từ order, ứng dụng có thể truy vấn thêm collection `customers` hoặc sử dụng aggregation stage `$lookup`.

Referencing thường hợp lý khi dữ liệu liên quan **có thể tăng không giới hạn**, được đọc/cập nhật **độc lập**, có **vòng đời riêng** hoặc được nhiều thực thể cùng sử dụng.

### 1.3. Manual reference khác DBRef

**Manual reference** chỉ cần lưu ID:

~~~javascript
{ _id: "O-1001", customerId: "C-100" }
~~~

**DBRef** là một quy ước biểu diễn tham chiếu dạng document có các trường như `$ref` (collection), `$id` (ID), và tùy chọn `$db` (database):

~~~javascript
{
  customerRef: {
    $ref: "customers",
    $id: "C-100"
  }
}
~~~

Đây là **minh họa cấu trúc DBRef**, không phải một phép tự động join hay foreign key. MongoDB Server không tự tìm dữ liệu từ DBRef trong mọi truy vấn; hỗ trợ dereference tùy thuộc driver/công cụ và cách ứng dụng xây dựng. Trong phần lớn mô hình dữ liệu thông thường, **manual reference** đơn giản và dễ kiểm soát hơn. Chỉ chọn DBRef khi có lý do tương thích cụ thể với framework, schema hoặc hệ thống đang dùng.

### 1.4. Quan hệ khác với bố cục vật lý

Đặt hai đối tượng vào cùng document cho **atomicity tại document**, còn đặt ở hai collection giúp chúng tiến triển và mở rộng độc lập hơn. Tuy nhiên:

- Cùng collection **không có nghĩa** cùng document; hai document trong cùng collection vẫn có ranh giới atomicity riêng.
- Khác collection **không có nghĩa** không bao giờ lấy được dữ liệu kết hợp; MongoDB có `$lookup`, hoặc ứng dụng tự truy vấn theo ID.
- Một document MongoDB không nên được hiểu như một bảng SQL chỉ vì có nhiều field.
- ObjectId là kiểu ID phổ biến, **không bắt buộc**; reference có thể dùng chuỗi, số hoặc ObjectId miễn nhất quán.

## 2. Các tiêu chí quyết định quan trọng nhất

Không nên chọn embedding/reference chỉ bằng một tiêu chí. Cần xét **mẫu truy cập thực tế**, mức tăng trưởng và nghĩa vụ nhất quán của dữ liệu.

| Tiêu chí | Nghiêng về **nhúng** | Nghiêng về **tham chiếu** |
|---|---|---|
| **Đọc dữ liệu** | Cha và con gần như luôn được đọc cùng nhau. | Thường chỉ cần cha hoặc chỉ cần con. |
| **Cardinality** | Một–một, một–vài, hoặc một–nhiều có giới hạn rõ. | Một–rất nhiều, nhiều–nhiều, số phần tử tăng lâu dài. |
| **Kích thước tăng trưởng** | Dự đoán được và nằm an toàn dưới giới hạn document. | Có thể tăng không giới hạn hoặc mỗi phần tử rất lớn. |
| **Tần suất cập nhật** | Dữ liệu con ổn định, hoặc thường thay đổi cùng cha. | Dữ liệu con thay đổi độc lập và thường xuyên. |
| **Vòng đời** | Con thuộc về cha; xóa cha thường kéo theo bỏ con. | Con cần tồn tại sau khi cha thay đổi/xóa hoặc được chia sẻ. |
| **Sở hữu và tái sử dụng** | Dữ liệu thuộc riêng một aggregate nghiệp vụ. | Một thực thể được nhiều document tham chiếu. |
| **Atomicity cần thiết** | Các field phải thay đổi nguyên tử trong một document. | Các thay đổi độc lập, hoặc cần transaction khi cập nhật nhiều document. |
| **Nhân bản / nhất quán** | Sao chép có mục đích, ví dụ giá và tên tại thời điểm mua. | Muốn một bản dữ liệu chuẩn được cập nhật tại một nơi. |
| **Index và truy vấn** | Hay lọc/đọc theo cha; index trên field lồng là đủ. | Cần tìm, phân trang, sắp xếp hoặc lập index con độc lập. |
| **Phân quyền / lưu trữ** | Cùng chính sách truy cập, retention và TTL logic. | Khác quyền, thời hạn giữ dữ liệu hoặc nhu cầu archive. |
| **Sharding / mở rộng** | Truy vấn cùng document, hạn chế phụ thuộc cross-shard. | Dữ liệu cần được phân vùng/scale độc lập. |
| **Chi phí join** | Ưu tiên một lần đọc dữ liệu cùng nhau. | Chấp nhận truy vấn thêm hoặc `$lookup` có kiểm soát. |

### 2.1. Cardinality: đếm số lượng con thực tế

Các nhãn quan hệ quen thuộc là:

| Quan hệ | Ví dụ | Phương án khởi đầu cần đánh giá |
|---|---|---|
| **One-to-one** | Một user có một cấu hình hiển thị | Nhúng khi có cùng vòng đời và cách truy cập. |
| **One-to-few** | Một sản phẩm có vài thông số kỹ thuật; user có vài địa chỉ | Nhúng nếu có giới hạn tăng trưởng thực tế. |
| **One-to-many có giới hạn** | Một đơn hàng có số lượng line item bị khống chế bởi nghiệp vụ | Có thể nhúng để đọc/ghi cùng đơn hàng. |
| **One-to-many không giới hạn** | Bài viết có hàng triệu bình luận | Reference: bình luận là document riêng. |
| **Many-to-many** | Học viên tham gia nhiều khóa học, khóa học có nhiều học viên | Thường dùng collection liên kết/reference. |

**Cardinality chưa đủ để ra quyết định.** Một quan hệ one-to-one vẫn nên tách document nếu thông tin có chính sách bảo mật, tốc độ cập nhật hoặc vòng đời hoàn toàn khác. Một quan hệ one-to-many vẫn có thể nhúng khi số phần tử **thật sự bị giới hạn** và luôn truy xuất cùng cha.

Đặc biệt, “hiện tại mới có 8 phần tử” **khác** với “nghiệp vụ quy định tối đa 8 phần tử”. Luôn hỏi tập con sẽ tăng thành bao nhiêu sau 1–3 năm.

### 2.2. Query locality: có thật sự dùng dữ liệu cùng nhau không?

MongoDB có lợi thế khi các field mà một thao tác cần nằm trong **cùng document**, vì không cần client round trip thứ hai hay stage join để lấy dữ liệu liên quan.

Ví dụ trang xác nhận đơn hàng thường cần một lần lấy: thông tin đơn, mặt hàng, giá đã thanh toán và địa chỉ giao hàng **tại thời điểm đặt mua**. Những dữ liệu này là ứng viên tốt để nhúng vào order.

Ngược lại, một trang product có thể có **hàng trăm nghìn review** nhưng chỉ hiển thị 5 review mới nhất. Nhúng toàn bộ review vào product làm document lớn không cần thiết. Nên để review riêng, đánh index theo `productId` và thời gian, rồi phân trang/truy vấn có giới hạn.

### 2.3. Ranh giới atomicity

Một thao tác ghi trên **một document** trong MongoDB có tính nguyên tử, kể cả khi sửa nhiều field và subdocument lồng bên trong. Vì vậy nếu một bất biến nghiệp vụ gắn chặt với một aggregate, nhúng có thể giúp bảo vệ bất biến mà không cần multi-document transaction.

Ngược lại, tham chiếu tạo **hai hoặc nhiều document độc lập**. Cập nhật cả hai không mặc nhiên là một thao tác nguyên tử chung. Nếu nghiệp vụ bắt buộc “cả hai cùng commit hoặc abort”, cần cân nhắc **transaction** trong deployment hỗ trợ, hoặc một workflow có **idempotency/compensation** thích hợp.

**Đừng nhúng chỉ để né mọi transaction.** Nếu dữ liệu con không giới hạn hoặc có vòng đời độc lập, việc ép vào cùng document có thể gây vấn đề lớn hơn lợi ích atomicity.

### 2.4. Quy tắc thay đổi và sự thật lịch sử

Hai nhu cầu thường bị nhầm:

- **Thông tin hiện tại (live data):** email hiện tại của customer, giá hiện tại của sản phẩm, trạng thái hiện tại của kho. Nếu nhiều nơi dùng chung một giá trị mới nhất, reference tới **source of truth** giúp tránh sao chép không đồng bộ.
- **Thông tin chốt theo sự kiện (snapshot/historical data):** tên sản phẩm và giá **tại lúc mua**, địa chỉ đã sử dụng để giao đơn. Nhúng bản snapshot là lựa chọn đúng dù dữ liệu cũng tồn tại ở collection khác. Nếu tên/giá sản phẩm đổi sau đó, hóa đơn cũ **không được tự đổi theo**.

Vì thế, nhiều hệ thống thực tế dùng **mô hình lai**: reference tới thực thể gốc **và** nhúng vài field snapshot cần bảo tồn.

## 3. Trường hợp điển hình nên nhúng

### 3.1. Một cấu hình đi cùng đối tượng cha

~~~javascript
// Một user có một cấu hình hiển thị nhỏ.
db.getSiblingDB("modeling_lab").users.insertOne({
  _id: "U-100",
  name: "An",
  preferences: {
    language: "vi",
    theme: "dark",
    notifications: { email: true, push: false }
  }
})
~~~

Một lần đọc user lấy được `preferences`. Khi đổi theme, có thể cập nhật field lồng:

~~~javascript
db.getSiblingDB("modeling_lab").users.updateOne(
  { _id: "U-100" },
  { $set: { "preferences.theme": "light" } }
)
~~~

**Lý do chọn nhúng:** one-to-one, object nhỏ, thường đọc cùng user, vòng đời gắn với user. Tuy nhiên, nếu `preferences` chứa thông tin nhạy cảm phải tách quyền truy cập hoặc có chu kỳ lưu trữ khác, cần đánh giá lại.

### 3.2. Đơn hàng nhúng line items và snapshot

Mỗi order là một **aggregate nghiệp vụ**. Một cách thiết kế thường hợp lý:

~~~javascript
{
  _id: "O-1001",
  customerId: "C-100",
  createdAt: ISODate("2026-11-12T10:00:00Z"),
  status: "PAID",
  shippingAddress: {
    recipient: "An",
    city: "Hà Nội",
    addressLine: "12 Đường A"
  },
  items: [
    {
      productId: "P-10",
      sku: "BOOK-01",
      nameAtPurchase: "Sổ ghi chép",
      unitPriceAtPurchase: 120000,
      quantity: 2
    },
    {
      productId: "P-11",
      sku: "PEN-02",
      nameAtPurchase: "Bút mực",
      unitPriceAtPurchase: 50000,
      quantity: 1
    }
  ],
  total: 290000
}
~~~

Thiết kế này có **cả nhúng lẫn tham chiếu**:

- `customerId` và `productId` là reference tới những thực thể sống độc lập.
- `shippingAddress`, `nameAtPurchase` và `unitPriceAtPurchase` là snapshot lịch sử.
- `items` là tập con thuộc riêng order; thường có giới hạn nghiệp vụ thực tế.

Tất cả item, địa chỉ snapshot và trạng thái đơn cùng nằm trong một document nên phù hợp trang chi tiết hóa đơn. Khi thay đổi giá catalog `products`, **không cập nhật giá đã chốt trong đơn**.

Nếu hệ thống cho phép một order có số line item rất lớn hoặc sinh tự động không giới hạn, cần cân nhắc tách order lines riêng; không coi mọi order đều nhỏ một cách hiển nhiên.

### 3.3. Đọc và cập nhật subdocument

Truy cập field nhúng dùng **dot notation**:

~~~javascript
const lab = db.getSiblingDB("modeling_lab")

// Lấy đơn của khách ở Hà Nội đã thanh toán.
lab.orders.find(
  { "shippingAddress.city": "Hà Nội", status: "PAID" },
  { _id: 1, status: 1, total: 1 }
)

// Sửa một field trong subdocument, không thay thế cả order.
lab.orders.updateOne(
  { _id: "O-1001" },
  { $set: { status: "PACKING" } }
)
~~~

Đối với array of embedded documents, dùng `$elemMatch` để đặt nhiều điều kiện lên **cùng phần tử**:

~~~javascript
lab.orders.find({
  items: {
    $elemMatch: {
      productId: "P-10",
      quantity: { $gte: 2 }
    }
  }
})
~~~

Nếu viết các điều kiện dạng `"items.productId"` và `"items.quantity"` độc lập mà không dùng `$elemMatch`, chúng có thể khớp **hai phần tử khác nhau** trong cùng mảng. Đây là khác biệt đáng chú ý khi mô hình hóa embedded arrays.

## 4. Trường hợp điển hình nên tham chiếu

### 4.1. Một sản phẩm có rất nhiều review

Review có thể tăng liên tục, được phân trang theo thời gian, lọc theo rating và kiểm duyệt độc lập. Nếu nhúng tất cả review vào product, document sản phẩm sẽ lớn dần, gây áp lực lên kích thước document, chi phí update, cache và truy vấn.

Mô hình tham chiếu:

~~~javascript
// products
{
  _id: "P-10",
  name: "Sổ ghi chép",
  currentPrice: 120000
}

// reviews
{
  _id: "R-1001",
  productId: "P-10",
  authorId: "U-100",
  rating: 5,
  content: "Giấy tốt",
  createdAt: ISODate("2026-11-12T10:00:00Z")
}
~~~

Mỗi review là một document riêng. Truy vấn có phân trang và index:

~~~javascript
const lab = db.getSiblingDB("modeling_lab")

// Tối ưu cho truy vấn các review mới nhất của một product.
lab.reviews.createIndex({ productId: 1, createdAt: -1, _id: -1 })

lab.reviews.find({ productId: "P-10" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)
~~~

Trên dữ liệu lớn, phân trang theo **keyset/cursor** (`createdAt` và `_id`) thường phù hợp hơn `skip` rất sâu vì `skip` phải bỏ qua nhiều kết quả. Việc có index đúng access pattern quan trọng hơn chuyện reference được đặt tên field gì.

**Lợi ích:** review tăng mà product document không cần phình vô hạn; review có thể được truy vấn, xóa, kiểm duyệt và thống kê độc lập.

### 4.2. Quan hệ nhiều–nhiều dùng collection liên kết

Giả sử **students** và **courses** có quan hệ many-to-many: mỗi học viên học nhiều khóa, mỗi khóa có nhiều học viên.

Thiết kế tham chiếu hai chiều bằng hai mảng `student.courseIds` và `course.studentIds` thường khó duy trì, đặc biệt khi số học viên của một khóa tăng rất lớn. Một **link collection** `enrollments` giúp biểu diễn mỗi quan hệ thành một document:

~~~javascript
// students
{ _id: "S-1", name: "Minh" }

// courses
{ _id: "K-1", title: "MongoDB căn bản" }

// enrollments
{
  _id: "E-1",
  studentId: "S-1",
  courseId: "K-1",
  enrolledAt: ISODate("2026-11-12T10:00:00Z"),
  progressPercent: 20
}
~~~

~~~javascript
const lab = db.getSiblingDB("modeling_lab")

// Một học viên chỉ được ghi danh một lần vào cùng khóa.
lab.enrollments.createIndex(
  { studentId: 1, courseId: 1 },
  { unique: true }
)

// Liệt kê khóa của một học viên.
lab.enrollments.find({ studentId: "S-1" })

// Liệt kê học viên của một khóa theo thời gian ghi danh.
lab.enrollments.createIndex({ courseId: 1, enrolledAt: -1 })
lab.enrollments.find({ courseId: "K-1" }).sort({ enrolledAt: -1 })
~~~

`enrollments` có thể chứa **thuộc tính của quan hệ**, như ngày tham gia và tiến độ. Một document enrollment có vòng đời và nhu cầu cập nhật riêng, nên thường hợp lý hơn việc nhúng một mảng vô hạn vào course.

### 4.3. Quan hệ phải tồn tại độc lập hoặc được chia sẻ

Hãy tham chiếu khi:

- Một **customer** có rất nhiều **orders**; order cần truy vấn độc lập theo thời gian và trạng thái.
- Một **user** có rất nhiều **activity events**; event cần retention, partitioning hoặc archive riêng.
- Một **product** xuất hiện trong hàng triệu order; catalog là nguồn thông tin hiện tại, các order giữ snapshot riêng.
- Một **organization** quản lý nhiều **employees**, và employee chuyển đơn vị có vòng đời không đơn giản là dữ liệu con của organization.
- Một **article** có lượng comment tăng không giới hạn.

Một reference có thể hợp lệ về mặt schema nhưng trỏ tới document **đã bị xóa hoặc không tồn tại**. MongoDB không tự áp dụng foreign key và cascade delete giống RDBMS. Ứng dụng phải định nghĩa chính sách **chặn xóa**, **cascade**, **soft delete**, **giữ snapshot**, hoặc **dọn dẹp bất đồng bộ** phù hợp nghiệp vụ.

## 5. Truy xuất dữ liệu tham chiếu

### 5.1. Hai truy vấn từ ứng dụng

Với một order chứa `customerId`:

~~~javascript
const lab = db.getSiblingDB("modeling_lab")
const order = lab.orders.findOne({ _id: "O-1001" })

if (order !== null) {
  const customer = lab.customers.findOne({ _id: order.customerId })
  printjson({ order, customer })
}
~~~

Ưu điểm là đơn giản, kiểm soát được projection và cache; nhược điểm là thêm round trip nếu không gộp nhiều ID. Khi tải danh sách 100 orders, **không nên** đọc customer từng order kiểu N+1 query. Có thể gom các `customerId` duy nhất rồi dùng một truy vấn `$in` hoặc aggregation `$lookup`.

### 5.2. Kết hợp bằng `$lookup`

Aggregation stage `$lookup` có thể join documents từ collection khác **trong cùng database** theo điều kiện phù hợp:

~~~javascript
const lab = db.getSiblingDB("modeling_lab")

lab.orders.aggregate([
  { $match: { _id: "O-1001" } },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  {
    $unwind: {
      path: "$customer",
      preserveNullAndEmptyArrays: true
    }
  },
  {
    $project: {
      _id: 1,
      status: 1,
      total: 1,
      "customer._id": 1,
      "customer.name": 1
    }
  }
])
~~~

`$lookup` trả về **một mảng** ở field `customer`, vì về nguyên tắc có thể có nhiều document khớp. `$unwind` biến phần tử mảng thành dòng kết quả; `preserveNullAndEmptyArrays` giúp không làm mất order nếu customer chưa tồn tại. Ở trường hợp join theo `_id`, index mặc định trên `customers._id` hỗ trợ tìm document liên quan.

**`$lookup` không làm reference thành embedding.** Engine vẫn phải xử lý kết hợp dữ liệu; join nhiều collection lớn hoặc trả nhiều phần tử có thể tốn tài nguyên. Cần lọc sớm, giới hạn kết quả, projection hợp lý, index phía join và đo `explain()`. Khả năng `$lookup` với collection sharded và các giới hạn khác phụ thuộc phiên bản MongoDB; đối chiếu Database Manual của deployment đang dùng.

### 5.3. Không có ràng buộc khóa ngoại tự động

Tạo field `customerId` **không** tự:

- kiểm tra ID có tồn tại trong `customers` khi insert;
- tạo index cho `orders.customerId`;
- xóa orders khi customer bị xóa;
- đồng bộ tên/email khách hàng sang order;
- khóa chéo hai collection để đảm bảo nhất quán nghiệp vụ.

Ứng dụng cần lựa chọn chính sách tương ứng và tạo index theo truy vấn:

~~~javascript
lab.orders.createIndex({ customerId: 1, createdAt: -1 })

// Tra cứu các đơn của một khách hàng:
lab.orders.find({ customerId: "C-100" })
  .sort({ createdAt: -1 })
  .limit(20)
~~~

Nhớ rằng **kiểu ID phải trùng**: chuỗi `"65..."` không bằng BSON `ObjectId("65...")` dù chuỗi hex hiển thị tương tự.

## 6. Mô hình lai: nhúng một phần và tham chiếu phần còn lại

Trong thực tế, lựa chọn không nhất thiết là “tất cả nhúng” hoặc “tất cả tách riêng”. Một mô hình lai thường đạt cân bằng tốt hơn.

### 6.1. Extended reference pattern

Một order tham chiếu customer, nhưng màn hình danh sách cần hiển thị **tên khách** rất thường xuyên. Có thể nhúng một phần dữ liệu để giảm lookup:

~~~javascript
{
  _id: "O-1001",
  customerId: "C-100",            // reference chuẩn
  customerDisplay: {              // bản sao phục vụ đọc
    name: "An",
    membershipTierAtOrder: "GOLD"
  },
  status: "PAID",
  total: 290000
}
~~~

Đây là **extended reference**: vẫn có ID chuẩn, đồng thời giữ vài field cần thiết tại nơi đọc. Tuy nhiên cần trả lời rõ:

- `customerDisplay.name` là **snapshot lúc đặt hàng** hay phải luôn phản ánh tên hiện tại?
- Nếu phải là tên hiện tại, ai chịu trách nhiệm cập nhật bản sao khi customer đổi tên?
- Nếu việc đồng bộ thất bại, hiển thị bản cũ trong bao lâu thì chấp nhận được?

Không xác định được ba điều trên thì duplication dễ trở thành **data drift**. Với dữ liệu cần luôn mới tuyệt đối, lookup live hoặc một quy trình cập nhật có bảo đảm tốt hơn có thể phù hợp hơn.

### 6.2. Subset pattern: nhúng một phần nhỏ, tham chiếu toàn bộ

Trang sản phẩm chỉ cần vài review mới nhất và tổng số review, trong khi toàn bộ review ở collection riêng:

~~~javascript
// products
{
  _id: "P-10",
  name: "Sổ ghi chép",
  ratingCount: 12450,
  ratingAverage: 4.6,
  recentReviews: [
    { reviewId: "R-900", authorName: "Minh", rating: 5, excerpt: "Tốt" },
    { reviewId: "R-899", authorName: "Lan", rating: 4, excerpt: "Ổn" }
  ]
}

// reviews chứa toàn bộ tập review, tra cứu bởi productId.
~~~

`recentReviews` phải có **giới hạn rõ ràng** (ví dụ tối đa 3–5 phần tử); đây là cache trình bày, không phải nguồn review chính. Nếu muốn duy trì danh sách tối đa 5 ID mới nhất trong product:

~~~javascript
db.getSiblingDB("modeling_lab").products.updateOne(
  { _id: "P-10" },
  {
    $push: {
      recentReviewIds: {
        $each: ["R-901"],
        $position: 0,
        $slice: 5
      }
    }
  }
)
~~~

Đoạn trên minh họa **cách giới hạn một mảng**; nó không tự đảm bảo review mới đã tồn tại hoặc việc cập nhật product/review là nguyên tử qua hai document. Nếu cần tính nhất quán mạnh giữa chúng, xem xét transaction hoặc chấp nhận cập nhật bất đồng bộ có cơ chế phục hồi.

### 6.3. Snapshot pattern: đóng băng dữ liệu theo sự kiện

Khi đặt hàng, giá catalog hiện tại là 120.000 đồng. Một tuần sau giá chuyển thành 130.000 đồng. Hóa đơn đã chốt **phải giữ giá 120.000**, nên order nhúng `unitPriceAtPurchase`. Reference `productId` vẫn hữu ích để liên kết tới catalog, nhưng **không dùng giá live để tính lại số tiền đã thanh toán**.

Điều này giống extended reference ở hình dạng dữ liệu, khác ở **ngữ nghĩa**: snapshot lịch sử **cố ý không đồng bộ**, còn bản sao cache hiện tại **cần chiến lược đồng bộ**.

### 6.4. Bucket pattern khi có chuỗi dữ liệu dài

Sensor IoT có thể gửi hàng triệu readings, mỗi reading nhỏ. Nhúng tất cả readings vào một document `sensor` là không phù hợp. Có thể lưu mỗi reading thành document riêng, hoặc gộp chúng thành **các bucket có kích thước/thời gian giới hạn**:

~~~javascript
// readingsBuckets
{
  _id: "sensor-7:2026-11-14T10",
  sensorId: "sensor-7",
  hourStart: ISODate("2026-11-14T10:00:00Z"),
  samples: [
    { second: 0, temperature: 27.1 },
    { second: 15, temperature: 27.2 }
    // ... có giới hạn theo thời gian hoặc số phần tử
  ]
}
~~~

Bucket là **nhúng bên trong từng cửa sổ bị chặn**, đồng thời **tham chiếu/tra cứu theo sensorId và khoảng thời gian** giữa các bucket. Với telemetry/time-series, cũng cần tìm hiểu **MongoDB time series collections**, vì server có cơ chế lưu trữ tối ưu riêng; không tự triển khai bucket thủ công nếu chức năng time series đáp ứng yêu cầu.

## 7. Giới hạn kích thước, tăng trưởng và hiệu năng

### 7.1. Giới hạn 16 MiB cho BSON document

MongoDB giới hạn kích thước một **BSON document** thông thường ở **16 MiB**. Nếu nhúng một mảng phát triển mãi, sớm muộn document có thể chạm giới hạn và các thao tác ghi mới thất bại. Ngay cả khi chưa đến 16 MiB, document quá lớn vẫn có thể:

- khiến đọc dữ liệu dư thừa, tăng network payload;
- làm working set/cache chịu áp lực;
- tăng chi phí xử lý cập nhật một document nóng;
- gây khó khăn cho pagination hoặc quản lý retention;
- làm mọi cập nhật con cùng cạnh tranh vào một document.

**GridFS** dành cho tệp lớn không phải biện pháp hợp lý để tiếp tục nhúng mảng nghiệp vụ không giới hạn. Hãy xác định **trần số phần tử** và **trần kích thước** của quan hệ trước khi nhúng.

### 7.2. Anti-pattern: unbounded array

Ví dụ rủi ro:

~~~javascript
{
  _id: "ARTICLE-1",
  title: "MongoDB",
  comments: [
    // Cứ thêm mãi từng comment của hàng triệu người đọc...
  ]
}
~~~

Vấn đề không nằm ở việc MongoDB không hỗ trợ array: **array có giới hạn** là điểm mạnh của document model. Vấn đề là đưa **toàn bộ tập con không có giới hạn** vào **một document duy nhất**. Thay vì vậy:

~~~javascript
// articles
{ _id: "ARTICLE-1", title: "MongoDB", commentCount: 1000000 }

// comments
{
  _id: "COMMENT-1001",
  articleId: "ARTICLE-1",
  authorId: "U-100",
  text: "Bài viết hữu ích",
  createdAt: ISODate("2026-11-14T10:00:00Z")
}
~~~

Tạo index cho truy vấn comments theo bài:

~~~javascript
db.getSiblingDB("modeling_lab").comments.createIndex({
  articleId: 1,
  createdAt: -1,
  _id: -1
})
~~~

Nếu muốn hiển thị một vài bình luận gần đây ngay trên article, dùng **subset** với số phần tử cố định, còn toàn bộ comments vẫn ở collection riêng.

### 7.3. Index cho embedded fields và multikey

MongoDB có thể index field lồng bằng dot notation:

~~~javascript
const lab = db.getSiblingDB("modeling_lab")
lab.orders.createIndex({ "shippingAddress.city": 1, status: 1 })
~~~

Với một field có giá trị array, MongoDB có thể tạo **multikey index**:

~~~javascript
lab.orders.createIndex({ "items.productId": 1 })
~~~

Multikey index hỗ trợ truy vấn trên mảng, nhưng có quy tắc/giới hạn riêng, đặc biệt khi compound index liên quan nhiều array fields. Mỗi phần tử array có thể tác động đến số index entries và chi phí ghi; array lớn không tự trở thành thiết kế tốt chỉ vì đã có index.

Khi dữ liệu con thường được truy vấn, lọc, sort, phân trang **độc lập trên phạm vi rất nhiều document cha**, collection riêng với index phù hợp có thể đơn giản và hiệu quả hơn.

### 7.4. Chi phí cập nhật và độ nóng của document

Nếu một product chứa hàng nghìn lượt xem/like/comment trong cùng document, mọi người dùng cùng cập nhật nó có thể tạo **hot document** và write conflicts. Tách những sự kiện có tần suất ghi lớn sang collection riêng hoặc cơ chế aggregation phù hợp có thể giảm tranh chấp.

Ngược lại, tách quá nhiều thành các collection nhỏ khiến mỗi request cần nhiều round trips hoặc `$lookup`, thêm chi phí vận hành và ràng buộc consistency. Thiết kế tốt tìm **ranh giới document** đúng với đơn vị đọc/ghi và giới hạn tăng trưởng của hệ thống.

## 8. Atomicity, consistency và vòng đời dữ liệu

### 8.1. Nhúng giúp giữ một bất biến trong một document

Ví dụ order có `status` và danh sách `items`. Một update thay `status` và một field liên quan trong chính order là nguyên tử:

~~~javascript
db.getSiblingDB("modeling_lab").orders.updateOne(
  { _id: "O-1001", status: "PENDING" },
  {
    $set: {
      status: "PAID",
      paidAt: ISODate("2026-11-14T10:00:00Z")
    }
  }
)
~~~

Nếu hai worker cùng cố xác nhận một order, điều kiện `status: "PENDING"` giúp chỉ một worker chuyển trạng thái khi document còn ở trạng thái phù hợp. Kết hợp `matchedCount` và idempotency ở ứng dụng để xử lý retry. Việc này không cần transaction nhiều document cho **riêng cập nhật trạng thái order**.

### 8.2. Tham chiếu không tự đồng bộ các document

Nếu cùng một request phải **giảm inventory ở product** và **tạo order** để cả hai cùng commit/abort, hai write riêng không tự bảo đảm atomicity chung:

~~~text
Write 1: products[P-10].stock -= 1
Write 2: insert orders[O-1001]

Nếu một write thành công và write còn lại thất bại:
    trạng thái có thể không đáp ứng bất biến nghiệp vụ.
~~~

Khi cần ACID trên nhiều document, có thể dùng **multi-document transaction** trên deployment hỗ trợ. Tuy nhiên, transaction có chi phí, giới hạn tài nguyên và quy tắc retry; không biến mọi write thành transaction chỉ vì có reference. Với nghiệp vụ tích hợp nhiều dịch vụ độc lập, còn cần đánh giá **outbox**, **saga/compensation** và idempotency.

### 8.3. Xóa và thay đổi quan hệ

Ví dụ xóa customer:

- Order lịch sử có cần giữ lại không? Thường có, tùy chính sách nghiệp vụ/pháp lý.
- Khi customer bị xóa, `orders.customerId` trở thành reference không resolve được hay order cần lưu snapshot để vẫn hiển thị?
- Có thể soft-delete customer để giữ liên kết, hoặc biến thông tin cá nhân thành dữ liệu ẩn danh trong order theo yêu cầu bảo vệ dữ liệu.
- Một cascade xóa tự viết cần xử lý lỗi một phần; không mặc nhiên được MongoDB thực hiện.

Thiết kế quan hệ phải đi cùng **chính sách lifecycle** rõ ràng, không chỉ cấu trúc field.

### 8.4. Tránh duplication không có owner

Giả sử cả `customers.name`, `orders.customerName` và `invoices.customerName` đều được dùng để hiển thị **tên hiện tại**. Nếu customer đổi tên, ai cập nhật hai bản sao? Nếu một bản sửa thất bại thì xử lý sao?

Ba hướng thiết kế:

1. **Reference thuần** khi cần giá trị live chuẩn và latency tra cứu có thể chấp nhận.
2. **Snapshot có chủ đích** khi muốn dữ liệu lịch sử không đổi.
3. **Denormalization có kiểm soát** khi ưu tiên tốc độ đọc và chấp nhận consistency tạm thời; định nghĩa owner, event/update propagation và reconciliation.

Không nên đưa một field sao chép vào schema nếu chưa biết nó là snapshot, cache hay dữ liệu chuẩn.

## 9. Sharding và quy mô: dữ liệu có ở cùng nơi không?

Trong sharded cluster, cách phân bố dữ liệu và **shard key** ảnh hưởng đến truy vấn và join. Một document nhúng được lưu như **một document logic**, nên các field cần cùng nhau có tính locality tốt hơn so với những document tham chiếu có thể nằm trên nhiều shard. Tuy nhiên:

- Không thể nhúng mảng không giới hạn chỉ để tránh cross-shard access.
- Reference có thể trỏ tới document trên shard khác; phải xem khả năng **targeted query** theo shard key.
- `$lookup` trên sharded collections có hỗ trợ/giới hạn phụ thuộc phiên bản MongoDB và kiểu pipeline; không mặc định rằng join phân tán luôn rẻ.
- Một document cực nóng vẫn là điểm tranh chấp kể cả được đặt trên shard phù hợp.
- Document 16 MiB là giới hạn độc lập với việc cluster có bao nhiêu shard.

Đừng chọn nhúng chỉ vì “sau này sẽ sharding”. Hãy dựa trên **tần suất đọc cùng nhau, cardinality và tốc độ ghi**, rồi xem tác động của shard key khi có kế hoạch phân mảnh rõ ràng.

## 10. Một quy trình ra quyết định có thể lặp lại

### Bước 1 — Viết rõ các thao tác sử dụng dữ liệu

Thay vì bắt đầu từ sơ đồ entity SQL, liệt kê những request thật:

~~~text
GET /products/P-10         -> product, giá hiện tại, 5 review mới nhất
GET /products/P-10/reviews -> 20 review/trang, sort theo createdAt
GET /orders/O-1001         -> order, item snapshot, địa chỉ chốt, trạng thái
GET /customers/C-100/orders -> 20 order gần nhất
POST /orders               -> tạo order + xử lý inventory và payment
PUT /users/U-100/preferences -> sửa một nhóm thiết lập
~~~

Mỗi request cần field nào? Đọc cùng nhau bao nhiêu phần trăm? Có phải phân trang con? Có phải lọc/sort con độc lập?

### Bước 2 — Ước lượng quy mô và tốc độ tăng trưởng

Ghi số thực tế hoặc giả định có thể kiểm chứng:

~~~text
Customer:
  addresses: trung bình 2, tối đa theo nghiệp vụ 10
  orders: có thể tăng hàng chục nghìn

Product:
  categories: vài mục
  reviews: không giới hạn

Order:
  items: có giới hạn trên luồng checkout
  events/status history: có thể cần retention dài
~~~

Một array chỉ an toàn để nhúng khi có **trần giới hạn được hệ thống thực thi**, không chỉ dựa vào dữ liệu mẫu.

### Bước 3 — Xác định quyền sở hữu và nhất quán

Hỏi:

- Dữ liệu con có tồn tại độc lập khi cha bị xóa không?
- Nó có được chia sẻ giữa nhiều cha không?
- Có bao nhiêu tác vụ cùng cập nhật con?
- Tên/giá/địa chỉ cần là **bản hiện tại** hay **bản tại thời điểm sự kiện**?
- Hai hoặc nhiều field/document phải commit cùng nhau không?

### Bước 4 — Đề xuất document boundary và index

Chọn cách biểu diễn rồi **kiểm tra query plan** với dữ liệu đại diện. Nếu embedding, cần index phù hợp cho nested fields và cách query array. Nếu referencing, cần index cho foreign key logic và sort/filter thực tế; dự trù số query hoặc chi phí `$lookup`.

### Bước 5 — Kiểm tra giới hạn và tình huống xấu

Đặt câu hỏi phản biện:

- Nếu số con gấp 100 lần, parent document có còn hợp lý không?
- Một thay đổi dữ liệu con có khiến hàng nghìn bản sao phải đồng bộ không?
- Nếu reference đích không tồn tại, ứng dụng xử lý sao?
- Có nguy cơ hot document, 16 MiB hoặc nhiều write conflicts không?
- Khi cần chuyển sang sharding, access pattern có thể target hiệu quả không?

### Bước 6 — Lưu quyết định và giả định

Ghi ngắn vào tài liệu kiến trúc: **lý do nhúng/tham chiếu, giới hạn tăng trưởng, source of truth, quy tắc cập nhật, index, cách xóa, cách đo hiệu năng**. Nhờ vậy, khi workload thay đổi, nhóm biết điều kiện nào cần thiết kế lại.

## 11. Bảng quyết định cho những tình huống phổ biến

| Tình huống | Gợi ý thiết kế | Vì sao? |
|---|---|---|
| User có một đối tượng `preferences` nhỏ | **Embed** trong user | Thường đọc/sửa cùng user, cùng vòng đời. |
| User có vài địa chỉ giao hàng có giới hạn | **Embed** hoặc tách nếu quyền/truy cập khác | Số ít, nhưng cần xem trần thực tế và truy vấn riêng. |
| Order có tối đa vài chục line items | **Embed** items | Đọc cùng order, giữ snapshot và atomicity ở document. |
| Customer có hàng trăm nghìn orders | **Reference** từ order đến customer | Không nên nhúng tập orders không giới hạn vào customer. |
| Product có hàng triệu reviews | **Reference** reviews; có thể embed subset | Phân trang độc lập, growth unbounded; preview cần ít dữ liệu. |
| Catalog product được nhiều order nhắc đến | **Reference ID + snapshot trên order** | Catalog sống độc lập, hóa đơn bảo toàn lịch sử. |
| Student–Course many-to-many | **Link collection** enrollments | Quan hệ tăng lớn, cần thuộc tính và index riêng. |
| Sensor sinh dữ liệu thời gian liên tục | **Time series hoặc bucket bị giới hạn** | Không để một sensor document phình vô hạn. |
| Một hợp đồng có vài điều khoản luôn ký cùng nhau | **Embed** nếu kích thước/vòng đời ổn định | Cần đọc và thay đổi trong cùng document. |
| Comment có quyền kiểm duyệt/retention riêng | **Reference** | Vòng đời, lọc/sort và cập nhật độc lập. |
| Danh sách 5 thông báo mới nhất trên user | **Subset có giới hạn** + collection events | UI đọc nhanh, lịch sử dài nằm riêng. |
| Cấu hình nhạy cảm cần quyền khác hẳn profile công khai | Thường **reference / tách collection** | Dễ đặt kiểm soát truy cập và lifecycle riêng. |

Không có bảng nào thay thế được đo đạc workload. Một mô hình reference có thể đạt tốc độ tốt với index và cache; một mô hình embed có thể chậm nếu trả hàng megabyte dữ liệu chỉ để hiển thị một tên.

## 12. Ví dụ hoàn chỉnh: thiết kế shop kết hợp cả hai cách

Các lệnh sau tạo dữ liệu độc lập trong database `modeling_lab`. Đây là minh họa về cấu trúc, không phải bộ giao dịch e-commerce đầy đủ.

### 12.1. Tạo customer và product chuẩn

~~~javascript
const lab = db.getSiblingDB("modeling_lab")

lab.customers.replaceOne(
  { _id: "C-100" },
  {
    _id: "C-100",
    name: "An",
    email: "an@example.test",
    preferences: { language: "vi" }
  },
  { upsert: true }
)

lab.products.replaceOne(
  { _id: "P-10" },
  {
    _id: "P-10",
    sku: "BOOK-01",
    name: "Sổ ghi chép",
    currentPrice: 120000
  },
  { upsert: true }
)
~~~

`preferences` được **embed** vào customer; product là thực thể độc lập có giá hiện tại.

### 12.2. Tạo order chứa ID tham chiếu và thông tin lịch sử

~~~javascript
lab.orders.replaceOne(
  { _id: "O-1001" },
  {
    _id: "O-1001",
    customerId: "C-100",
    createdAt: ISODate("2026-11-12T10:00:00Z"),
    status: "PAID",
    shippingAddress: {
      recipient: "An",
      city: "Hà Nội",
      addressLine: "12 Đường A"
    },
    items: [
      {
        productId: "P-10",
        sku: "BOOK-01",
        nameAtPurchase: "Sổ ghi chép",
        unitPriceAtPurchase: 120000,
        quantity: 2
      }
    ],
    total: 240000
  },
  { upsert: true }
)
~~~

Ở đây:

1. `orders.customerId` là **reference**, để có thể tìm customer hiện tại.
2. `orders.items[].productId` là **reference**, để liên kết catalog nếu cần.
3. `orders.items[].unitPriceAtPurchase` và `shippingAddress` là **snapshot** được nhúng, để nội dung order không bị đổi do catalog/customer cập nhật sau này.
4. `orders.items` là **subdocument array** được giới hạn bởi nghiệp vụ checkout.

### 12.3. Tạo review riêng

~~~javascript
lab.reviews.replaceOne(
  { _id: "R-1" },
  {
    _id: "R-1",
    productId: "P-10",
    authorId: "C-100",
    rating: 5,
    content: "Sản phẩm phù hợp",
    createdAt: ISODate("2026-11-13T08:00:00Z")
  },
  { upsert: true }
)

lab.reviews.createIndex({ productId: 1, createdAt: -1 })
lab.orders.createIndex({ customerId: 1, createdAt: -1 })
~~~

`reviews` là collection độc lập vì số lượng có thể tăng mãi; index giúp tải review theo product. `orders` cũng cần index theo customer vì một customer có thể có rất nhiều đơn.

### 12.4. Thử thay đổi catalog nhưng giữ lịch sử

~~~javascript
lab.products.updateOne(
  { _id: "P-10" },
  { $set: { currentPrice: 130000 } }
)

printjson(lab.products.findOne({ _id: "P-10" }))
printjson(lab.orders.findOne({ _id: "O-1001" }))
~~~

`products.currentPrice` đã là 130.000, còn `orders.items[0].unitPriceAtPurchase` **vẫn 120.000** — đúng với nhu cầu hóa đơn lịch sử. Nếu thiếu snapshot và chỉ tra `products.currentPrice` để tính lại đơn, dữ liệu thanh toán cũ có thể bị diễn giải sai.

## 13. Phát triển mô hình khi workload thay đổi

Mô hình ban đầu không cần dự đoán mọi tình huống, nhưng nên có **đường mở rộng**. Giả sử ban đầu review được nhúng vì mỗi product chỉ có vài review; khi sản phẩm phổ biến, mảng bắt đầu lớn.

Một lộ trình migration an toàn về mặt khái niệm:

1. **Chọn nguồn dữ liệu chuẩn mới** (`reviews` collection) và xác định schema, ID, indexes.
2. **Chuyển dữ liệu đã tồn tại** từ embedded array sang review documents, giữ ID ổn định và xử lý record trùng.
3. **Điều chỉnh đường ghi** để không phát sinh hai sự thật khác nhau. Nếu có giai đoạn dual-write, cần cơ chế retry/reconciliation rõ ràng.
4. **Chuyển đường đọc** sang collection mới, có thể hỗ trợ fallback trong giai đoạn chuyển tiếp.
5. **Đối soát số lượng và kết quả hiển thị**; sau khi chắc chắn mới loại bỏ embedded array cũ hoặc chỉ giữ một subset bị giới hạn.

Không nên làm migration kiểu “copy một lần rồi xóa mảng ngay” trong hệ thống đang ghi liên tục: dữ liệu mới có thể xuất hiện trong khoảng chuyển tiếp. Với collection lớn, cần tính tới backfill, change capture, idempotency và thời gian rollout.

Một **schema version** trong ứng dụng (ví dụ `schemaVersion: 2`) có thể hỗ trợ đọc dữ liệu cũ/mới trong quá trình chuyển đổi; nó khác hoàn toàn với MongoDB Server version và FCV.

## 14. Sai lầm thường gặp

| Nhận định sai | Cách nhìn đúng |
|---|---|
| “MongoDB là document database nên mọi quan hệ phải nhúng.” | Document model hỗ trợ cả embedding, referencing và mô hình lai. |
| “MongoDB không có join.” | MongoDB có aggregation stage `$lookup`, nhưng join có chi phí và phạm vi hỗ trợ cụ thể. |
| “One-to-many thì cứ nhúng mảng.” | Chỉ nhúng nếu mức tăng trưởng có giới hạn phù hợp; tránh unbounded arrays. |
| “One-to-one thì luôn nhúng.” | Xem vòng đời, bảo mật, tần suất cập nhật và cách truy cập trước. |
| “Lưu `customerId` là đã có foreign key.” | Manual reference không tự tạo constraint, index hay cascade. |
| “ObjectId tham chiếu chỉ cần giống chuỗi hiển thị.” | Kiểu BSON phải tương thích; string khác ObjectId. |
| “Nhúng sẽ xóa mọi nhu cầu transaction.” | Chỉ atomicity trong **một document**; nghiệp vụ nhiều document vẫn có thể cần transaction. |
| “Tham chiếu sẽ luôn chậm vì phải query nhiều lần.” | Có thể batch bằng `$in`, dùng cache/index hoặc `$lookup`; phải đo workload thật. |
| “Sao chép tên khách vào order luôn gây inconsistency.” | Snapshot lịch sử cố ý giữ giá trị cũ là đúng; cache hiện tại cần đồng bộ. |
| “Dùng `$lookup` xong có thể coi kết quả như foreign key có ràng buộc.” | `$lookup` chỉ kết hợp dữ liệu lúc đọc, không tự áp ràng buộc quan hệ. |
| “Có index trên array thì có thể nhúng vô hạn.” | Index không loại bỏ giới hạn 16 MiB và chi phí cập nhật document lớn. |
| “Reference nghĩa là tất cả dữ liệu con phải ở một collection khác.” | Có thể reference giữa document cùng collection hoặc collection khác; lựa chọn dựa vào mô hình. |

## 15. Bài tập thực hành và đáp án gợi ý

### Bài 1 — Tài khoản người dùng

Mỗi user có một bộ thiết lập giao diện: ngôn ngữ, theme, quyền nhận email, tối đa vài chục field. Màn hình profile luôn hiển thị cùng user.

**Câu hỏi:** embed hay reference?

**Gợi ý:** **Embed** `preferences` trong user vì one-to-one, nhỏ, đọc cùng nhau và cùng vòng đời; đánh giá ngoại lệ nếu cần quyền truy cập hoặc lifecycle riêng.

### Bài 2 — Bài báo và bình luận

Mỗi article có thể có từ 0 đến hàng triệu comment; trang chỉ hiển thị 20 comment mỗi lần và lọc theo thời gian.

**Gợi ý:** **Reference** comment sang article bằng `articleId` và tạo index phục vụ phân trang. Có thể nhúng subset vài comment mới nhất vào article nếu có quy tắc cập nhật rõ ràng.

### Bài 3 — Đơn hàng và catalog

Product thay đổi giá theo tuần; order đã thanh toán phải giữ giá, tên và địa chỉ giao hàng tại thời điểm đặt.

**Gợi ý:** Dùng **reference ID** tới catalog/customer và **embed snapshot** trong order. Không dùng giá live để tính lại hóa đơn đã chốt.

### Bài 4 — Student và Course

Một student tham gia nhiều course, một course có nhiều student; cần lưu tiến độ từng cặp student–course.

**Gợi ý:** Dùng **link collection** `enrollments` với `studentId`, `courseId`, `progressPercent`. Tạo compound unique index cho cặp ID nếu nghiệp vụ không cho trùng ghi danh.

### Bài 5 — Nhúng array tăng trưởng

Thiết kế `users.notifications[]` chứa tất cả thông báo từ lúc đăng ký. Mỗi user có thể phát sinh vài trăm thông báo/ngày.

**Gợi ý:** Chuyển notifications sang collection riêng với `userId`, index theo thời gian; có thể giữ `recentNotifications` tối đa 5–10 phần tử trong user nếu cần hiển thị nhanh.

### Bài 6 — Tính nguyên tử

Một request cập nhật `orders.status` và `products.stock` trong hai document. Việc dùng reference `productId` có tự đảm bảo cả hai cùng thành công không?

**Gợi ý:** **Không**. Mỗi document có ranh giới atomicity riêng; nếu cần cùng commit/abort, đánh giá transaction hoặc workflow có idempotency và compensation.

### Bài 7 — Document nhỏ nhưng cập nhật rất nhiều

Một field `viewCount` được nhúng trong article; hàng nghìn client mỗi giây cùng tăng cùng document. Kích thước document rất nhỏ, nhưng latency update tăng.

**Gợi ý:** Nguyên nhân có thể là **hot document/write contention**, không phải 16 MiB. Cân nhắc giảm tần suất cập nhật, tích lũy số liệu theo lô hoặc phân phối counter rồi tổng hợp, tùy yêu cầu độ chính xác và độ trễ.

### Bài 8 — Review ID trong product

Product chứa mảng `reviewIds` của **tất cả** reviews, dù nội dung review đã ở collection riêng. Đây đã là thiết kế tham chiếu an toàn chưa?

**Gợi ý:** **Chưa chắc**. Mảng ID vẫn tăng không giới hạn và có thể chạm giới hạn document. Thay vì giữ mọi ID ở product, hãy query `reviews` theo `productId` với index.

## 16. Tài liệu chính thức để đọc sâu

Các đường dẫn dưới đây thuộc **MongoDB Database Manual**. Hãy chọn đúng phiên bản server trong bộ chọn tài liệu; nhánh `/docs/manual/` có thể thay đổi theo thời gian. Nếu một trang được đổi URL, bắt đầu từ mục **Data Modeling** của tài liệu phiên bản đang dùng.

- [Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/) — mục tổng quan về thiết kế document theo access pattern.
- [Embedding vs. References](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/) — tiêu chí chọn nhúng hay tham chiếu.
- [Embedded Data](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedded-documents/) — mô hình document lồng.
- [References](https://www.mongodb.com/docs/manual/data-modeling/concepts/references/) — manual references và DBRefs.
- [Document Structure](https://www.mongodb.com/docs/manual/core/document/) — BSON document, nested fields và giới hạn kích thước.
- [`$lookup` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/) — kết hợp dữ liệu từ collection khác.
- [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — giới hạn atomicity một document và cập nhật đồng thời.
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/) — index cho field array.
- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — kiểm soát cấu trúc/kiểu dữ liệu khi schema linh hoạt.
- [Unbounded Arrays](https://www.mongodb.com/docs/manual/data-modeling/design-antipatterns/unbounded-arrays/) — tránh nhúng array tăng trưởng không giới hạn.
- [Subset Pattern](https://www.mongodb.com/docs/manual/data-modeling/design-patterns/subset-pattern/) và [Extended Reference Pattern](https://www.mongodb.com/docs/manual/data-modeling/design-patterns/extended-reference-pattern/) — mô hình lai tối ưu access pattern.
- [Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/) — lựa chọn chuyên biệt cho dữ liệu chuỗi thời gian.

Một quyết định thiết kế document tốt có thể diễn đạt bằng câu: **“Dữ liệu này được đọc cùng nhau, có vòng đời phù hợp, giới hạn tăng trưởng rõ, và các bất biến cần thiết nằm trong đúng ranh giới document.”** Khi bất kỳ điều kiện nào không còn đúng, tham chiếu hoặc mô hình lai thường là hướng cần đánh giá. Chọn thiết kế dựa trên **workload thật và yêu cầu nhất quán**, rồi đo bằng truy vấn đại diện thay vì dựa vào khẩu hiệu chung về NoSQL.
