# Ranh giới document, tính gắn kết dữ liệu và thao tác nguyên tử trong MongoDB

Trong MongoDB, **document** không chỉ là đơn vị lưu trữ dữ liệu BSON mà còn là **ranh giới quan trọng của thao tác ghi nguyên tử**. Khi thiết kế mô hình dữ liệu, quyết định đặt những field nào cùng một document có ảnh hưởng trực tiếp đến cách ứng dụng đọc dữ liệu, giữ bất biến nghiệp vụ, xử lý cập nhật đồng thời và mở rộng quy mô.

Ví dụ, một đơn hàng gồm địa chỉ giao hàng, các dòng sản phẩm và tổng tiền. Nếu tất cả dữ liệu này cùng nằm trong một document, ứng dụng có thể cập nhật nhiều field của đơn hàng bằng **một thao tác ghi nguyên tử**. Nhưng số lượng tồn kho của sản phẩm thường nằm trong một document khác. Việc cập nhật đồng thời đơn hàng và tồn kho vì thế cần một cách phối hợp khác, chẳng hạn transaction, mô hình bảo lưu hoặc quy trình nghiệp vụ có khả năng phục hồi.

Ba câu hỏi xuyên suốt khi mô hình hóa MongoDB là:

1. **Ranh giới document:** Những dữ liệu nào phải được lưu và cập nhật như một đơn vị?
2. **Tính gắn kết dữ liệu:** Những thông tin nào thực sự thuộc cùng một đối tượng nghiệp vụ và thường được dùng cùng nhau?
3. **Tính nguyên tử:** Những thay đổi nào phải thành công hoặc thất bại cùng nhau, và liệu chúng có nằm trọn trong một document không?

## 1. Ranh giới document là gì?

Một document là một giá trị BSON gồm các cặp field và value, có thể chứa document lồng nhau và array:

~~~javascript
{
  _id: "ORD-1001",
  customerId: "CUS-101",
  status: "DRAFT",
  shippingAddress: {
    recipient: "Nguyễn An",
    city: "Đà Nẵng",
    street: "12 Nguyễn Văn Linh"
  },
  items: [
    {
      sku: "BOOK-01",
      quantity: 2,
      unitPrice: NumberDecimal("150000.00")
    }
  ],
  totalAmount: NumberDecimal("300000.00"),
  version: 1
}
~~~

Ở đây, **shippingAddress** là document lồng trong document đơn hàng; **items** là array các document con. Chúng **không phải những document độc lập** trong collection nếu được lưu theo cấu trúc trên.

Có thể hình dung:

~~~text
Database shop
└── Collection orders
    └── Document _id = "ORD-1001"       ← Ranh giới ghi nguyên tử
        ├── customerId
        ├── status
        ├── shippingAddress
        │   ├── recipient
        │   ├── city
        │   └── street
        ├── items[]
        │   └── { sku, quantity, unitPrice }
        ├── totalAmount
        └── version

Collection products
└── Document _id = "BOOK-01"          ← Ranh giới ghi khác
    ├── title
    ├── price
    └── stock
~~~

**Ranh giới document** là điểm phân cách giữa dữ liệu nằm cùng một BSON document và dữ liệu nằm trong document khác. Dù hai document ở cùng collection hay hai collection khác nhau, chúng vẫn có ranh giới ghi nguyên tử riêng.

### 1.1. Tại sao không coi collection là đơn vị nguyên tử?

Collection tập hợp nhiều document và hỗ trợ index, validation, truy vấn. Nhưng một lệnh cập nhật nhiều document như **updateMany** không mặc nhiên trở thành một giao dịch nguyên tử cho toàn bộ collection.

Ví dụ:

~~~javascript
db.products.updateMany(
  { category: "BOOK" },
  { $set: { featured: true } }
);
~~~

MongoDB bảo đảm tính nguyên tử **cho từng document** mà lệnh này cập nhật. Không có bảo đảm rằng tất cả document được sửa đồng thời thành một khối duy nhất. Trong khi lệnh đang chạy, thao tác khác có thể quan sát hoặc xen vào ở phạm vi nhiều document theo mức cô lập tương ứng.

Vì vậy, đặt hai phần dữ liệu trong **cùng một collection** không làm chúng có chung ranh giới nguyên tử; muốn có nguyên tử trong một write thông thường thì chúng phải thuộc **cùng một document**.

### 1.2. Ranh giới logic không đồng nghĩa với ranh giới vật lý

Ứng dụng thường gọi một đối tượng như **Order**, **Customer** hoặc **ShoppingCart** là một thực thể nghiệp vụ. MongoDB không bắt buộc mỗi thực thể phải có chính xác một document, cũng không tự hiểu các ràng buộc nghiệp vụ của thực thể đó.

Chẳng hạn, một khách hàng có thể có:

- Một document hồ sơ khách hàng.
- Nhiều document đơn hàng.
- Nhiều document hoạt động đăng nhập.
- Một hoặc nhiều document giỏ hàng theo phiên.

Tất cả liên quan đến một khách hàng nhưng không nhất thiết nên được nhét chung vào document khách hàng. Quyết định phải dựa trên mối quan hệ nghiệp vụ, kiểu truy cập, tốc độ tăng dữ liệu và nhu cầu cập nhật.

## 2. Tính gắn kết dữ liệu: dữ liệu nào thuộc về nhau?

**Data cohesion** trong mô hình document là mức độ các field và phần dữ liệu liên quan tạo thành **một đơn vị thông tin có ý nghĩa**: cùng mô tả một khái niệm, thường được đọc cùng nhau, có vòng đời gắn bó hoặc cần thay đổi thống nhất.

Tính gắn kết cao thường là tín hiệu tốt cho **embedding** (nhúng dữ liệu vào document cha). Tính gắn kết thấp thường nghiêng về **referencing** (lưu riêng và tham chiếu).

### 2.1. Gắn kết về ngữ nghĩa

Thông tin địa chỉ giao hàng tại thời điểm khách đặt hàng thuộc bản ghi **đơn hàng**, dù khách hàng cũng có địa chỉ trong hồ sơ cá nhân.

Nếu khách cập nhật địa chỉ mặc định sau khi đặt hàng, địa chỉ của đơn đã xác nhận thường **không được tự đổi**. Vì vậy, lưu một **shippingAddress snapshot** bên trong document đơn hàng là lựa chọn có ý nghĩa:

~~~javascript
{
  _id: "ORD-1001",
  customerId: "CUS-101",
  shippingAddress: {
    recipient: "Nguyễn An",
    city: "Đà Nẵng",
    street: "12 Nguyễn Văn Linh"
  }
}
~~~

Trong khi đó, danh mục sản phẩm có thể thay đổi độc lập:

~~~javascript
{
  _id: "BOOK-01",
  title: "Nhập môn MongoDB",
  currentPrice: NumberDecimal("180000.00"),
  stock: 20
}
~~~

Đơn hàng có thể nhúng **tên, giá tại lúc mua** trong từng dòng hàng để lưu lịch sử; sản phẩm trong catalog vẫn là document riêng. Đây là **sao chép dữ liệu có chủ đích** theo ngữ nghĩa nghiệp vụ, không nhất thiết là lỗi thiết kế.

### 2.2. Gắn kết theo cách đọc

Nếu một màn hình luôn cần cả tiêu đề bài viết, tác giả hiển thị và vài thẻ phân loại, việc nhúng một phần thông tin nhỏ có thể giúp đọc một document là đủ.

Ngược lại, nếu ứng dụng chỉ thường xuyên hiển thị danh sách sản phẩm với ID, tên và giá, nhưng lại nhúng toàn bộ lịch sử đánh giá vào mỗi document sản phẩm, việc đọc có thể kéo theo nhiều dữ liệu không cần thiết.

Hai câu hỏi thực dụng:

- **Ứng dụng thường đọc những trường này cùng nhau không?**
- **Khi trả về một phần dữ liệu, document cha có trở nên quá lớn hoặc quá nóng do những phần còn lại không?**

Cần nhớ rằng MongoDB có projection để chỉ chọn field trả về. Tuy nhiên, projection không tự làm cho việc nhúng một array tăng vô hạn trở thành thiết kế phù hợp; kích thước document, cập nhật và bộ nhớ vẫn là yếu tố phải cân nhắc.

### 2.3. Gắn kết theo vòng đời

Một địa chỉ giao hàng của đơn hàng thường được tạo và lưu cùng đơn hàng. Một dòng hàng trong đơn cũng thường được quản lý theo trạng thái đơn.

Ngược lại:

- **Product** tồn tại trước và sau nhiều đơn hàng.
- **Customer** tồn tại độc lập với từng đơn.
- **Payment** có thể có vòng đời, nhật ký và chính sách truy cập riêng.
- **Event log** có thể tiếp tục tăng lâu dài sau khi đối tượng chính không thay đổi.

Dữ liệu có vòng đời độc lập dễ phù hợp với document riêng, nhất là khi cần tìm kiếm, phân quyền, lưu trữ hoặc xóa theo quy tắc khác nhau.

### 2.4. Gắn kết theo điều kiện nhất quán

Đôi khi việc cần **cập nhật nguyên tử** quyết định ranh giới document mạnh hơn việc dữ liệu thường được đọc cùng nhau.

Ví dụ trạng thái đơn hàng và **totalAmount** phải được giữ nhất quán với dòng hàng. Nếu ứng dụng sửa dòng hàng và tổng tiền trong cùng một thao tác update document, không có thời điểm mà document được lưu chỉ chứa nửa của thao tác ghi đó.

Điều này không có nghĩa MongoDB tự tính đúng tổng tiền: **tính nguyên tử bảo đảm tất cả cập nhật trong một write được áp dụng như một đơn vị; tính đúng đắn của phép tính vẫn là trách nhiệm của logic ứng dụng**.

## 3. Embedded document và reference: hai cách vạch ranh giới

MongoDB cho phép mô hình quan hệ bằng nhúng dữ liệu hoặc tham chiếu giữa document. Cả hai đều hợp lệ; điều quan trọng là chọn đúng theo cách dữ liệu được sử dụng.

### 3.1. Embedding: dữ liệu nằm trong cùng document

~~~javascript
{
  _id: "ORD-1001",
  status: "DRAFT",
  items: [
    { sku: "BOOK-01", quantity: 2, unitPrice: 150000 },
    { sku: "PEN-02", quantity: 1, unitPrice: 10000 }
  ],
  totalAmount: 310000
}
~~~

Ưu điểm:

- Có thể đọc đơn hàng và dòng hàng bằng một document.
- Có thể cập nhật nhiều field và phần tử array của document trong **một write nguyên tử**.
- Không cần thao tác join giữa hai collection để dựng thông tin cơ bản của đơn.
- Ranh giới sở hữu rõ ràng nếu dữ liệu con chỉ có ý nghĩa trong document cha.

Chi phí và giới hạn:

- Document có thể lớn lên khi array được thêm phần tử.
- Những writer đồng thời muốn sửa các phần khác nhau trong một document có thể cạnh tranh cùng tài nguyên.
- Dữ liệu lặp lại giữa nhiều document có thể phải được duy trì theo nghiệp vụ.
- Document BSON thông thường bị giới hạn **16 MiB**.

**Nhúng không có nghĩa là nhúng mọi quan hệ.** Một array lịch sử sự kiện phát sinh không giới hạn sẽ dần trở thành gánh nặng dù về ngữ nghĩa các sự kiện đều liên quan đến cùng một đối tượng.

### 3.2. Referencing: dữ liệu nằm trong document riêng

~~~javascript
// Collection orders
{
  _id: "ORD-1001",
  customerId: "CUS-101",
  status: "DRAFT"
}

// Collection orderItems
{
  _id: "LINE-1",
  orderId: "ORD-1001",
  sku: "BOOK-01",
  quantity: 2,
  unitPrice: 150000
}

// Collection products
{
  _id: "BOOK-01",
  title: "Nhập môn MongoDB",
  stock: 20
}
~~~

Ưu điểm:

- Mỗi thực thể có thể tăng trưởng hoặc được cập nhật độc lập.
- Document nhỏ hơn nếu số phần tử liên quan lớn.
- Thuận tiện khi một đối tượng được tham chiếu từ nhiều nơi.
- Có thể đặt index, quyền quản lý và chính sách lưu trữ theo từng collection phù hợp.

Chi phí:

- Để hiển thị đơn hàng cùng tất cả dòng hàng, ứng dụng cần nhiều truy vấn hoặc aggregation như **$lookup**.
- Một thay đổi nghiệp vụ trên nhiều document không tự nguyên tử.
- Cần quản lý tham chiếu và dữ liệu mồ côi theo thiết kế; MongoDB không tự biến một field **orderId** thành khóa ngoại có kiểm tra ràng buộc như SQL.

### 3.3. Bảng chọn hướng mô hình

| Tiêu chí | Nghiêng về embedding | Nghiêng về referencing |
| --- | --- | --- |
| Tần suất đọc | Các phần thường được đọc cùng lúc | Các phần thường được đọc riêng |
| Vòng đời | Dữ liệu con thuộc sở hữu document cha | Dữ liệu con sống và thay đổi độc lập |
| Số lượng phần tử | Nhỏ hoặc có giới hạn hợp lý | Rất lớn, không có giới hạn rõ ràng |
| Yêu cầu nguyên tử | Nhiều field cần cập nhật cùng một write | Có thể chấp nhận phối hợp nhiều document |
| Tần suất ghi | Cập nhật theo một đối tượng nghiệp vụ | Các phần bị ghi độc lập, thường xuyên |
| Trùng lặp | Dữ liệu nhúng ổn định hoặc là snapshot | Dữ liệu được chia sẻ và phải đồng bộ hiện thời |
| Truy vấn riêng | Ít tìm dữ liệu con độc lập | Cần lọc, phân trang, tổng hợp dữ liệu con riêng |

Một hệ thống thường kết hợp cả hai: nhúng **items** và **shippingAddress** trong đơn hàng, nhưng tham chiếu **customerId**, **productId** hoặc **paymentId**.

## 4. Tính nguyên tử của thao tác ghi trên một document

**Atomicity** có nghĩa một thao tác ghi được áp dụng **trọn vẹn hoặc không được áp dụng** đối với đơn vị nguyên tử mà hệ thống hỗ trợ. MongoDB cung cấp tính nguyên tử cho **một thao tác ghi trên một document**, ngay cả khi thao tác này sửa nhiều field hoặc nhiều thành phần lồng nhau.

Ví dụ document ban đầu:

~~~javascript
{
  _id: "ORD-1001",
  status: "DRAFT",
  totalAmount: NumberDecimal("300000.00"),
  itemCount: 2,
  version: 1
}
~~~

Một thao tác update có thể cập nhật cả ba field:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001", status: "DRAFT" },
  {
    $inc: {
      totalAmount: NumberDecimal("15000.00"),
      itemCount: 1,
      version: 1
    },
    $set: {
      updatedAt: new Date()
    }
  }
);
~~~

Nếu thao tác được áp dụng thành công trên document phù hợp, các thay đổi trong thao tác đó được thực thi nguyên tử ở mức document. Không có trạng thái lưu trung gian mà chỉ **itemCount** đã tăng còn **totalAmount** chưa tăng do chính thao tác update này.

Tuy nhiên, nếu ứng dụng tính sai số tiền tăng hoặc quên cập nhật dòng hàng liên quan, MongoDB vẫn có thể thực thi nguyên tử một thay đổi **sai về nghiệp vụ**. Atomicity và tính đúng đắn logic là hai thuộc tính khác nhau.

### 4.1. Một thao tác có thể sửa nhiều field

Một lệnh **updateOne** có thể đồng thời dùng các toán tử phù hợp như:

| Toán tử | Mục đích | Ví dụ |
| --- | --- | --- |
| **$set** | Gán hoặc tạo field | Đổi trạng thái đơn hàng |
| **$inc** | Tăng/giảm giá trị số | Giảm tồn kho, tăng version |
| **$unset** | Xóa field | Bỏ thông tin tạm thời |
| **$push** | Thêm phần tử vào array | Thêm dòng hàng |
| **$pull** | Loại phần tử phù hợp khỏi array | Bỏ một sản phẩm khỏi giỏ |
| **$addToSet** | Thêm giá trị nếu chưa có phần tử bằng nó trong array | Ghi nhãn/tag |
| **$setOnInsert** | Gán field khi nhánh upsert insert document | Tạo metadata lần đầu |

Ví dụ thêm một item và cập nhật tổng tiền cùng một write:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001", status: "DRAFT" },
  {
    $push: {
      items: {
        sku: "PEN-02",
        quantity: 1,
        unitPrice: NumberDecimal("15000.00")
      }
    },
    $inc: {
      totalAmount: NumberDecimal("15000.00"),
      version: 1
    }
  }
);
~~~

**items** và **totalAmount** cùng thuộc document đơn hàng nên thay đổi được thực thi nguyên tử. Ví dụ giả định **items** đã là array, **totalAmount** là số phù hợp, và thông tin giá đã được ứng dụng xác thực.

### 4.2. Atomicity không đồng nghĩa với mọi tài liệu đều bất biến giữa các lệnh

Hai thao tác update riêng biệt, dù cùng tác động một document, vẫn là **hai thao tác nguyên tử khác nhau**:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001" },
  { $set: { status: "CONFIRMED" } }
);

db.orders.updateOne(
  { _id: "ORD-1001" },
  { $set: { confirmedAt: new Date() } }
);
~~~

Nếu thao tác đầu thành công còn thao tác thứ hai thất bại, document có thể đang ở trạng thái **CONFIRMED** nhưng thiếu **confirmedAt**.

Khi hai field cần thay đổi cùng nhau, nên đặt chúng trong **một write**:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001", status: "DRAFT" },
  {
    $set: {
      status: "CONFIRMED",
      confirmedAt: new Date()
    }
  }
);
~~~

Lệnh thứ hai có điều kiện **status: "DRAFT"** để ngăn xác nhận lại đơn vốn đã chuyển trạng thái. Ứng dụng vẫn phải kiểm tra số document được khớp trước khi cho rằng việc xác nhận đã xảy ra.

### 4.3. Một write, nhiều document: mỗi document nguyên tử riêng

~~~javascript
db.orders.updateMany(
  { status: "EXPIRED" },
  { $set: { archived: true } }
);
~~~

MongoDB có thể cập nhật nhiều document, nhưng thao tác **không có bảo đảm nguyên tử tập thể** nếu chạy ngoài multi-document transaction. Trong lúc xử lý, có thể đã có một số đơn được sửa còn những đơn khác chưa được sửa.

Tương tự:

- **insertMany** không tự là một transaction đa document.
- **bulkWrite** không tự biến mọi thao tác trong batch thành một khối nguyên tử.
- Một vòng lặp gọi **updateOne** nhiều lần cũng không nguyên tử như một write duy nhất.

Nếu toàn bộ nhóm document phải cùng commit hoặc cùng rollback, cần xem xét **multi-document transaction** và điều kiện deployment hỗ trợ.

## 5. Cập nhật đồng thời: nguyên tử nhưng có thể vẫn sai nghiệp vụ

Tính nguyên tử cho một document không tự giải quyết mọi lỗi do nhiều người dùng hoặc nhiều service đồng thời cập nhật.

### 5.1. Trường hợp lost update với $set

Giả sử số lượng tồn kho hiện tại là 10. Hai request cùng đọc 10 và tự tính ra 9, rồi đều ghi:

~~~javascript
db.products.updateOne(
  { _id: "BOOK-01" },
  { $set: { stock: 9 } }
);
~~~

Mỗi write vẫn nguyên tử. Nhưng kết quả cuối có thể là **9** thay vì **8**, vì cả hai request đều ghi lại giá trị được tính từ cùng trạng thái cũ.

Đây là ví dụ cho thấy **atomic write không tự ngăn lost update khi ứng dụng đọc rồi ghi lại bằng giá trị cũ**.

### 5.2. Dùng $inc để thay đổi tương đối

Nếu nghiệp vụ chỉ cần trừ một đơn vị tồn kho, dùng toán tử tăng/giảm trực tiếp:

~~~javascript
db.products.updateOne(
  { _id: "BOOK-01" },
  { $inc: { stock: -1 } }
);
~~~

Hai thao tác giảm thành công trên cùng document sẽ áp dụng mức giảm riêng của từng thao tác, thay vì đều ghi giá trị tuyệt đối 9 được tính sẵn.

Nhưng nếu tồn kho có thể về âm, chỉ dùng **$inc** là chưa đủ. Cần đưa ràng buộc nghiệp vụ vào điều kiện update.

### 5.3. Conditional update ngăn bán quá số lượng

~~~javascript
const result = db.products.updateOne(
  {
    _id: "BOOK-01",
    stock: { $gte: 2 }
  },
  {
    $inc: { stock: -2 }
  }
);

if (result.modifiedCount === 1) {
  print("Đã giữ/trừ 2 sản phẩm trong document tồn kho");
} else {
  print("Không cập nhật: không tồn tại hoặc không đủ hàng");
}
~~~

Điều kiện **stock >= 2** được đánh giá gắn với thao tác cập nhật trên document. Các request tranh nhau trừ tồn kho không thể đồng thời dựa vào cùng một giá trị cũ rồi làm tồn kho âm chỉ vì tính trước ở phía ứng dụng.

Cách này bảo vệ **bất biến tồn kho không âm của một product document** khi mọi đường ghi liên quan đều tuân thủ cùng quy tắc. Nó chưa bảo đảm việc tạo document đơn hàng ở collection khác thành công cùng với thao tác giảm tồn kho.

### 5.4. Optimistic concurrency bằng version

Khi cập nhật dựa trên dữ liệu đã đọc và phải phát hiện xung đột, có thể lưu một field **version**.

Document ban đầu:

~~~javascript
{
  _id: "ORD-1001",
  status: "DRAFT",
  shippingAddress: { city: "Hà Nội" },
  version: 7
}
~~~

Client A đọc **version = 7**. Client B có thể đã sửa document trước khi A ghi. Client A chỉ cập nhật khi version vẫn bằng 7:

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "ORD-1001",
    version: 7
  },
  {
    $set: {
      "shippingAddress.city": "Đà Nẵng"
    },
    $inc: {
      version: 1
    }
  }
);

if (result.matchedCount === 0) {
  print("Dữ liệu đã thay đổi hoặc document không còn tồn tại");
}
~~~

Nếu một update hợp lệ khác đã nâng version lên 8, filter trên sẽ không khớp. Ứng dụng cần tải lại, hợp nhất thay đổi hoặc báo xung đột phù hợp, thay vì ghi đè mù.

Chiến lược version có hiệu quả khi **tất cả writer liên quan cùng cập nhật version**. Một service sửa dữ liệu nhưng bỏ qua version sẽ làm mất tác dụng của quy ước.

### 5.5. Tính nguyên tử không thay thế write concern và read concern

Ba khái niệm khác nhau:

- **Atomicity:** một thao tác ghi vào document không bị áp dụng dở dang.
- **Write concern:** mức xác nhận ghi mà client yêu cầu từ deployment, có ảnh hưởng đến kỳ vọng về độ bền/khả năng phục hồi.
- **Read concern:** mức nhất quán và điều kiện hiển thị dữ liệu đối với thao tác đọc.

Một write nguyên tử không tự có nghĩa mọi client lập tức đọc được nó từ bất kỳ secondary nào, hoặc write đã được xác nhận với majority. Những điều này phụ thuộc cách cấu hình read/write concern, replication và thời điểm đọc.

## 6. Bất biến nghiệp vụ và ranh giới nguyên tử

Một **bất biến nghiệp vụ (business invariant)** là điều kiện phải đúng tại những thời điểm mà hệ thống yêu cầu, ví dụ:

- Tồn kho của một sản phẩm không âm.
- Tổng tiền đơn hàng khớp các dòng hàng theo quy tắc tính đã chọn.
- Đơn hàng chỉ được chuyển từ **DRAFT** sang **CONFIRMED** một lần.
- Một tài khoản không được rút quá số dư khả dụng.
- Hai bản ghi sổ cái của một giao dịch chuyển tiền phải cùng được ghi nhận.

Nếu tất cả dữ liệu cần bảo vệ một bất biến nằm trong **một document**, MongoDB cho phép kiểm tra điều kiện và thay đổi document bằng một atomic update.

Ví dụ trạng thái đơn hàng:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-1001",
    status: "DRAFT"
  },
  {
    $set: {
      status: "CONFIRMED",
      confirmedAt: new Date()
    }
  }
);
~~~

Tính nguyên tử giúp trạng thái và mốc thời gian cùng đổi; điều kiện **status: "DRAFT"** bảo vệ quy tắc chuyển trạng thái.

Nếu bất biến trải trên **hai document**, một atomic update đơn lẻ không đủ để bảo đảm cả hai cùng cập nhật. Ví dụ:

~~~text
Product document:
  stock phải giảm 2

Order document:
  order phải được tạo đúng một lần
~~~

Trừ tồn kho thành công nhưng insert order thất bại có thể dẫn tới sai lệch. Ngược lại, tạo order trước rồi giảm tồn kho thất bại có thể tạo đơn không thể thực hiện.

Tùy tính chất nghiệp vụ, có thể dùng transaction, chuyển sang mô hình reservation, quy trình có trạng thái và thao tác bù, hoặc thay đổi ranh giới lưu trữ để bất biến quan trọng nằm trong cùng document. Không có một lựa chọn duy nhất phù hợp cho mọi hệ thống.

## 7. Ví dụ thiết kế: đơn hàng, giỏ hàng và tồn kho

### 7.1. Một document đơn hàng có tính gắn kết cao

~~~javascript
{
  _id: "ORD-1001",
  customerId: "CUS-101",
  status: "DRAFT",
  items: [
    {
      sku: "BOOK-01",
      titleSnapshot: "Nhập môn MongoDB",
      quantity: 2,
      unitPrice: NumberDecimal("150000.00"),
      lineTotal: NumberDecimal("300000.00")
    },
    {
      sku: "PEN-02",
      titleSnapshot: "Bút ghi chú",
      quantity: 1,
      unitPrice: NumberDecimal("10000.00"),
      lineTotal: NumberDecimal("10000.00")
    }
  ],
  shippingAddress: {
    recipient: "Nguyễn An",
    city: "Đà Nẵng",
    street: "12 Nguyễn Văn Linh"
  },
  totalAmount: NumberDecimal("310000.00"),
  version: 1,
  createdAt: ISODate("2025-01-15T10:00:00Z")
}
~~~

Những phần này có tính gắn kết cao:

- **items** mô tả nội dung đơn hàng tại thời điểm giao dịch.
- **titleSnapshot** và **unitPrice** là dữ liệu lịch sử cần giữ khi catalog đổi.
- **shippingAddress** là nơi giao cho đơn cụ thể.
- **status**, **totalAmount**, **version** mô tả trạng thái nhất quán của đơn.

Có thể áp dụng thay đổi nhiều field của đơn hàng trong một atomic update. Một document đơn có số lượng dòng hàng hợp lý thường là mô hình dễ vận hành.

### 7.2. Tồn kho nằm trong document riêng

~~~javascript
{
  _id: "BOOK-01",
  title: "Nhập môn MongoDB",
  stock: 20,
  currentPrice: NumberDecimal("180000.00")
}
~~~

Một sản phẩm được nhiều khách hàng cùng mua, có vòng đời độc lập với mỗi đơn. Do đó tồn kho không thể được xem là một field “thuộc riêng” bất kỳ đơn hàng nào.

Có thể trừ tồn kho bằng conditional update, nhưng việc đồng thời tạo order document là thay đổi trên **hai document**. Nếu hệ thống yêu cầu hai thay đổi phải commit/rollback cùng nhau, cần transaction hoặc mô hình nghiệp vụ khác đảm bảo điều kiện tương đương.

### 7.3. Giỏ hàng và thứ tự tăng trưởng

Một giỏ hàng hoạt động thường có số item nhỏ và có thời gian sống giới hạn; embedding giúp cập nhật nội dung giỏ bằng một document.

Nhưng lịch sử **mọi lần thêm, bớt sản phẩm của khách trong nhiều năm** có số lượng không giới hạn. Lưu toàn bộ lịch sử vào array trong document giỏ sẽ làm document phình to và tạo cạnh tranh ghi. Lịch sử hoạt động thường nên nằm ở collection sự kiện riêng, có TTL/retention và index phù hợp với cách dùng.

Sự khác biệt không phải “giỏ hàng liên quan đến khách còn log thì không”. Cả hai đều liên quan đến khách hàng; nhưng **giỏ đang hoạt động có tính gắn kết và kích thước giới hạn**, còn **log có vòng đời và tốc độ tăng riêng**.

## 8. Khi nào cần multi-document transaction?

MongoDB hỗ trợ **multi-document transactions** trên deployment được hỗ trợ, như replica set và sharded cluster. Trong transaction, các thao tác trên nhiều document có thể được commit hoặc abort cùng nhau.

Ví dụ bài toán tạo đơn và trừ tồn kho:

~~~text
BEGIN TRANSACTION
  1. Trừ 2 sản phẩm BOOK-01 nếu stock >= 2.
  2. Tạo một order mới tham chiếu BOOK-01.
COMMIT
~~~

Nếu một bước gặp lỗi khiến transaction bị abort, các thay đổi trong transaction không được commit như một phần riêng lẻ.

### 8.1. Ví dụ Node.js Driver

Ví dụ dưới đây minh họa transaction trên hai document trong cùng database, với MongoDB deployment hỗ trợ transaction:

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient("mongodb://localhost:27017");

async function createOrder() {
  await client.connect();

  const session = client.startSession();

  try {
    const db = client.db("shop");
    const products = db.collection("products");
    const orders = db.collection("orders");

    await session.withTransaction(async () => {
      const stockResult = await products.updateOne(
        {
          _id: "BOOK-01",
          stock: { $gte: 2 }
        },
        {
          $inc: { stock: -2 }
        },
        { session }
      );

      if (stockResult.modifiedCount !== 1) {
        throw new Error("Không đủ hàng hoặc sản phẩm không tồn tại");
      }

      await orders.insertOne(
        {
          _id: "ORD-1001",
          productId: "BOOK-01",
          quantity: 2,
          status: "CONFIRMED",
          createdAt: new Date()
        },
        { session }
      );
    });

    console.log("Đã commit đơn hàng và thay đổi tồn kho");
  } finally {
    await session.endSession();
    await client.close();
  }
}

createOrder().catch(console.error);
~~~

Điều kiện áp dụng của ví dụ:

- Driver kết nối được đến **replica set hoặc sharded cluster** có hỗ trợ transaction; một standalone mongod độc lập không phù hợp để chạy ví dụ transaction này.
- Document **products** có **_id: "BOOK-01"** và field **stock** kiểu số.
- Document **orders** chưa có **_id: "ORD-1001"**.
- Ví dụ sử dụng một ID cố định để minh họa; chạy lại cần xử lý idempotency và quy trình đặt hàng thực tế.

Callback của **withTransaction** có thể được driver chạy lại với một số lỗi tạm thời. Không nên đặt các hành động không thể rollback, như gửi email thông báo hoặc gọi dịch vụ thanh toán, bên trong callback mà không có chiến lược chống lặp. Commit transaction chỉ bao trùm các thao tác database tham gia transaction.

### 8.2. Transaction có thay thế mô hình document tốt không?

Transaction hữu ích nhưng mang thêm chi phí điều phối, tài nguyên, xử lý retry, timeout và khả năng xung đột ghi. Nó cũng không tự động thiết kế đúng việc lưu trữ, truy vấn hoặc tăng trưởng dữ liệu.

Nếu một bất biến vốn thuộc **một đối tượng nhỏ và gắn kết**, đặt dữ liệu trong cùng document và dùng một atomic update thường đơn giản hơn. Khi nghiệp vụ thực sự trải trên nhiều đối tượng độc lập, transaction là một công cụ phù hợp.

Các hệ thống quy mô lớn còn có thể chọn luồng xử lý bất đồng bộ, outbox và thao tác bù. Những cách này cần định nghĩa rõ **nhất quán cuối cùng**, trạng thái trung gian và cơ chế phục hồi, chứ không thể thay thế transaction chỉ bằng việc chạy nhiều lệnh rồi hy vọng tất cả thành công.

### 8.3. Phân biệt transaction với read/write concern

Transaction có cơ chế snapshot và commit riêng; độ bền và khả năng nhìn thấy kết quả vẫn chịu ảnh hưởng của các lựa chọn read concern, write concern và cấu hình cluster. Không nên suy luận rằng chỉ cần dùng transaction là mọi thao tác đọc ngoài transaction sẽ lập tức nhìn thấy cùng một trạng thái trên tất cả secondary.

## 9. Giới hạn kích thước và tốc độ tăng của document

MongoDB giới hạn một BSON document thông thường ở **16 MiB**. Nhưng việc một document chưa chạm 16 MiB không có nghĩa mô hình nhúng đã tốt.

### 9.1. Array không giới hạn là dấu hiệu đáng chú ý

Ví dụ mô hình nhúng mọi sự kiện đăng nhập:

~~~javascript
{
  _id: "CUS-101",
  fullName: "Nguyễn An",
  loginEvents: [
    { at: ISODate("2025-01-01T10:00:00Z"), ip: "192.0.2.10" },
    { at: ISODate("2025-01-02T10:00:00Z"), ip: "192.0.2.11" }
    // Tiếp tục tăng theo thời gian...
  ]
}
~~~

Nếu ứng dụng ghi thêm mỗi lần đăng nhập, array này không có giới hạn tự nhiên. Sau nhiều năm, document có thể quá lớn, chi phí cập nhật và truyền dữ liệu cao, và nhiều writer cùng cạnh tranh sửa document khách hàng.

Một cách lưu khác:

~~~javascript
// Collection customers
{
  _id: "CUS-101",
  fullName: "Nguyễn An"
}

// Collection loginEvents
{
  _id: ObjectId(),
  customerId: "CUS-101",
  at: new Date(),
  ip: "192.0.2.10"
}
~~~

Có thể tạo index theo **customerId, at** để lọc và phân trang lịch sử. Vòng đời của event có thể được quản lý khác với document hồ sơ khách hàng.

### 9.2. Bounded array và subset pattern

Nếu chỉ cần lưu **ba địa chỉ gần đây** hoặc **mười hoạt động mới nhất**, có thể nhúng một tập con có giới hạn:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $push: {
      recentActivities: {
        $each: [
          { type: "LOGIN", at: new Date() }
        ],
        $slice: -10
      }
    }
  }
);
~~~

Ví dụ trên giữ **10 phần tử cuối** trong array **recentActivities**, giả sử thứ tự thêm phần tử chính là thứ tự muốn giữ. Lịch sử đầy đủ, nếu cần, có thể lưu ở collection khác.

Bounded array phù hợp khi giới hạn rõ ràng và cập nhật một document vẫn đáp ứng nhu cầu. Nhưng **$slice** không biến các document hoạt động riêng bên ngoài thành một phần của thao tác nguyên tử với document khách hàng.

### 9.3. Write hotspot và tranh chấp trên một document

Một document chứa bộ đếm chung có thể trở thành **hot document** nếu hàng nghìn request cùng cập nhật nó. Mỗi update vẫn nguyên tử, nhưng cạnh tranh ghi có thể ảnh hưởng throughput và latency.

Ví dụ một bộ đếm toàn hệ thống:

~~~javascript
db.counters.updateOne(
  { _id: "global-page-views" },
  { $inc: { value: 1 } }
);
~~~

Thiết kế này rất đơn giản nhưng có một điểm tập trung ghi. Tùy yêu cầu, ứng dụng có thể phân tách bộ đếm, gom batch, hoặc sử dụng mô hình sự kiện để tính toán. Khi phân tách, cần chấp nhận rằng **tổng trên nhiều document không còn được cập nhật bằng một atomic write đơn lẻ**.

## 10. Đọc dữ liệu, cập nhật dữ liệu và phạm vi nhất quán

Ranh giới document quyết định atomicity của write, còn cách truy vấn có thể cần nhiều document.

### 10.1. Đọc một document

~~~javascript
db.orders.findOne(
  { _id: "ORD-1001" },
  { _id: 1, status: 1, items: 1, totalAmount: 1 }
);
~~~

Nếu **items** và **totalAmount** cùng trong document, ứng dụng nhận các field đó từ cùng một document được truy vấn.

Tuy nhiên, nếu ứng dụng thực hiện **hai lệnh đọc riêng biệt** tại hai thời điểm, dữ liệu có thể đã thay đổi giữa hai lệnh. Atomicity không tự tạo ra một snapshot kéo dài qua nhiều truy vấn độc lập.

### 10.2. Cập nhật một field lồng nhau bằng dot notation

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001" },
  {
    $set: {
      "shippingAddress.city": "Huế"
    }
  }
);
~~~

Lệnh này cập nhật field con **city** và giữ các field khác trong **shippingAddress**.

Ngược lại:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001" },
  {
    $set: {
      shippingAddress: { city: "Huế" }
    }
  }
);
~~~

Lệnh sau **thay toàn bộ giá trị của field shippingAddress** bằng document chỉ có **city**. Đây vẫn là atomic update, nhưng có thể làm mất **recipient** và **street**. Vì vậy nguyên tử không đồng nghĩa với “giữ nguyên các field không được lập trình viên nghĩ tới”; hành vi cụ thể của toán tử phải được hiểu đúng.

### 10.3. Array và positional update

Giả sử một order chứa:

~~~javascript
{
  _id: "ORD-1001",
  items: [
    { sku: "BOOK-01", quantity: 2 },
    { sku: "PEN-02", quantity: 1 }
  ]
}
~~~

Có thể thay đổi số lượng của phần tử thỏa điều kiện bằng array filter:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001" },
  {
    $inc: {
      "items.$[item].quantity": 1
    }
  },
  {
    arrayFilters: [
      { "item.sku": "BOOK-01" }
    ]
  }
);
~~~

Dù sửa field ở bên trong một phần tử array, thao tác vẫn ghi vào **một document ORD-1001**. Nếu cần đổi cả **quantity** và **totalAmount**, có thể kết hợp các toán tử phù hợp trong một update, miễn logic tính tổng đúng.

Lưu ý, nếu array có nhiều phần tử cùng **sku**, array filter có thể tác động nhiều phần tử của document đó. Bất biến “mỗi sku chỉ xuất hiện một lần trong items” vẫn cần được quản lý trong schema và nghiệp vụ.

## 11. Thiết kế theo aggregate và tính nhất quán

Trong Domain-Driven Design, **aggregate** là nhóm đối tượng có một ranh giới giữ bất biến nghiệp vụ và một điểm điều phối thay đổi. MongoDB document có thể là nơi lưu một aggregate nhỏ, nhưng hai khái niệm **không hoàn toàn đồng nhất**.

Ví dụ một **Order aggregate** có:

~~~text
Order
├── orderId
├── customerId
├── status
├── shippingAddress
├── items[]
└── totalAmount
~~~

Nếu các quy tắc của Order có thể được xác định và cập nhật trọn vẹn trong một document, document là một ranh giới hợp lý.

Nhưng một aggregate quá lớn có thể không phù hợp để nhúng vì vượt giới hạn kích thước hoặc gây tranh chấp ghi. Ngược lại, hai aggregate nghiệp vụ độc lập không nên bị ghép vào cùng document chỉ để giảm số transaction nếu việc đó làm sai vòng đời hoặc cách truy cập dữ liệu.

### 11.1. Phân biệt bất biến cục bộ và bất biến liên đối tượng

| Loại bất biến | Ví dụ | Ranh giới phù hợp |
| --- | --- | --- |
| Cục bộ trong một đơn | Status và confirmedAt phải đổi cùng nhau | Một Order document |
| Cục bộ trong một sản phẩm | Stock không xuống âm | Một Product document với conditional update |
| Liên đối tượng | Tạo Order và giảm Product stock cùng commit | Multi-document transaction hoặc workflow phối hợp |
| Liên hệ thống | Trừ tiền qua cổng thanh toán và xác nhận đơn | Quy trình chống lặp, trạng thái và phục hồi ngoài phạm vi một MongoDB transaction |
| Lịch sử sự kiện | Mọi event phải lưu, cho phép truy vấn theo thời gian | Collection event riêng hoặc kiến trúc log phù hợp |

Bảng này giúp tránh một lỗi phổ biến: yêu cầu “mọi thay đổi phải nguyên tử” nhưng lại không chỉ ra **bất biến nào cần được bảo vệ**. Không phải mọi dữ liệu có quan hệ đều phải thay đổi trong cùng một transaction.

### 11.2. Snapshot khác với dữ liệu tham chiếu hiện thời

Một order nên giữ **unitPrice tại thời điểm mua**. Đây là snapshot có tính gắn kết với order. Nếu giá sản phẩm trong catalog thay đổi, snapshot không cần được cập nhật theo.

Trong khi đó, nếu màn hình quản trị cần hiển thị **tình trạng sản phẩm hiện tại**, tham chiếu tới product document là phù hợp hơn thay vì kỳ vọng snapshot của order luôn phản ánh dữ liệu mới.

Phân biệt **snapshot lịch sử** và **dữ liệu hiện thời** giúp quyết định có nên sao chép giá trị vào document hay không.

## 12. Ví dụ đối chiếu hai mô hình thiết kế

Giả sử làm tính năng quản lý lớp học. Một lớp có thông tin tên, giáo viên, danh sách học viên, điểm danh, bài tập và mọi bài nộp.

### Mô hình A: nhúng tất cả vào một document

~~~javascript
{
  _id: "CLASS-01",
  name: "MongoDB căn bản",
  teacherId: "T-01",
  students: [ /* hàng trăm học viên */ ],
  attendances: [ /* hàng nghìn bản ghi */ ],
  submissions: [ /* hàng chục nghìn bài nộp */ ]
}
~~~

Mô hình này gom các phần có liên quan về chủ đề vào cùng một document, nhưng dễ tạo vấn đề:

- Các array tăng liên tục và có thể đụng giới hạn 16 MiB.
- Nhiều học viên cùng nộp bài tạo ghi cạnh tranh trên cùng document lớp.
- Truy vấn điểm danh theo học viên hoặc bài nộp theo ngày không thuận tiện.
- Việc cập nhật một bài nộp có thể không nên ảnh hưởng tới điểm nóng của toàn document lớp.

Dù nhiều field cùng document và atomic update có lợi, **tính gắn kết nghiệp vụ thấp hơn độ lớn của ranh giới được chọn**.

### Mô hình B: tách phần có vòng đời độc lập

~~~text
classes
  { _id, name, teacherId, settings }

enrollments
  { _id, classId, studentId, enrolledAt, status }

attendances
  { _id, classId, studentId, sessionDate, present }

submissions
  { _id, classId, assignmentId, studentId, submittedAt, grade }
~~~

Với mô hình B:

- Thông tin lớp học gọn và ít thay đổi.
- Mỗi attendance/submission có thể được cập nhật riêng.
- Có thể lập index theo **classId, studentId, sessionDate** và các truy vấn độc lập.
- Khi một quy trình thay đổi nhiều document, hệ thống phải chọn cơ chế nhất quán phù hợp.

Có thể nhúng một **summary nhỏ** trong document lớp, như tổng học viên hiện tại, nếu đây là dữ liệu truy cập thường xuyên. Nhưng tổng nhúng đó cần chiến lược duy trì nhất quán với các enrollments, có thể bằng transaction hoặc quy trình tổng hợp được chấp nhận.

Điểm mấu chốt: **đặt ranh giới theo quan hệ sở hữu, vòng đời, kiểu truy cập và bất biến**, không chỉ vì mọi dữ liệu cùng nói về một chủ đề.

## 13. Quy trình quyết định ranh giới document

Khi thiết kế một mô hình MongoDB mới, có thể đi theo trình tự sau.

### Bước 1: Xác định thao tác nghiệp vụ thực tế

Ví dụ với hệ thống đặt hàng:

- Xem chi tiết một đơn.
- Thêm/xóa dòng hàng trước khi xác nhận.
- Xác nhận đơn.
- Trừ tồn kho của sản phẩm.
- Ghi nhận thanh toán.
- Lọc đơn theo khách hàng và khoảng thời gian.

Không chỉ liệt kê thực thể; cần hiểu **đường đọc/ghi thường xuyên nhất**.

### Bước 2: Viết rõ bất biến

Ví dụ:

- Đơn đã xác nhận không được sửa dòng hàng bằng API chỉnh giỏ thông thường.
- Tổng tiền của đơn phải khớp quy tắc tính từ items.
- Tồn kho không âm.
- Một yêu cầu đặt hàng có khóa idempotency không được tạo hai đơn.

Những bất biến chỉ nằm trong một order document là ứng viên tốt cho atomic update. Những bất biến liên quan product, payment hoặc nhiều order yêu cầu ranh giới lớn hơn.

### Bước 3: Tìm nhóm dữ liệu gắn kết

Nhóm theo:

- Cùng được đọc.
- Cùng vòng đời.
- Cùng có quan hệ sở hữu.
- Cùng được sửa trong một thao tác.
- Không tăng trưởng quá lớn.

Địa chỉ giao hàng snapshot, dòng hàng và trạng thái đơn thường gắn kết. Hồ sơ khách hàng, catalog, lịch sử giao dịch độc lập thường nên tham chiếu.

### Bước 4: Kiểm tra kích thước và cạnh tranh ghi

Ước lượng số phần tử array hiện tại và cực đại; xem có phát sinh không giới hạn không. Xem một document có trở thành điểm nóng khi nhiều writer đồng thời cập nhật không.

MongoDB giới hạn 16 MiB nhưng ứng dụng nên thiết kế với **biên an toàn**, không đợi tới khi chạm giới hạn mới tách dữ liệu.

### Bước 5: Chọn cơ chế nhất quán

| Nhu cầu | Hướng tiếp cận thường gặp |
| --- | --- |
| Sửa nhiều field trong một document | Một **updateOne/findOneAndUpdate** với điều kiện phù hợp |
| Cộng/trừ số mà không đọc rồi ghi lại | **$inc** |
| Chặn cập nhật trên phiên bản cũ | Filter có **version** và tăng version |
| Giữ stock không âm | Filter có **stock: { $gte: n }** và **$inc** |
| Cập nhật nhiều document cùng commit/rollback | **Multi-document transaction** |
| Phối hợp với dịch vụ ngoài database | Workflow có trạng thái, idempotency và xử lý thất bại |
| Lịch sử dữ liệu không giới hạn | Collection riêng hoặc thiết kế bounded subset |

### Bước 6: Đánh giá khi workload thay đổi

Thiết kế ban đầu có thể đúng với vài nghìn document nhưng bất hợp lý khi array tăng hàng triệu phần tử hoặc một document nhận nhiều nghìn lần ghi mỗi giây. Cần đo lường và thay đổi mô hình khi cách truy cập, quy mô hoặc bất biến thay đổi.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Mọi document trong cùng collection cùng được update nguyên tử | MongoDB mặc định bảo đảm atomicity **theo từng document**, không theo collection |
| Đặt dữ liệu trong cùng database là đủ để bảo đảm nhất quán | Database là tổ chức logic, không phải ranh giới atomic write |
| Embedded document là một document độc lập | Nó là cấu trúc lồng trong BSON document cha, cùng ranh giới nguyên tử |
| Một write cập nhật nhiều field có thể lưu nửa thay đổi | Một single-document write được áp dụng nguyên tử |
| Hai updateOne liên tiếp tự tạo thành một transaction | Mỗi update là một thao tác độc lập nếu không dùng transaction |
| $set là nguyên tử nên không có lost update | Hai writer có thể ghi đè giá trị tính từ dữ liệu cũ; cần $inc hoặc điều kiện/version phù hợp |
| updateMany là transaction vì chỉ có một lời gọi API | Mỗi document nguyên tử riêng, không có all-or-nothing cho cả tập nếu ngoài transaction |
| Nhúng mọi quan hệ giúp hệ thống nhanh hơn | Array vô hạn, hotspot và document lớn có thể gây vấn đề |
| Tách collection luôn bắt buộc phải dùng transaction | Chỉ cần transaction khi nghiệp vụ đòi hỏi nhóm thay đổi phải commit/rollback cùng nhau |
| Transaction MongoDB bao phủ thanh toán hoặc email ngoài hệ thống | Transaction chỉ quản lý các thao tác database tham gia nó |
| Một document dưới 16 MiB chắc chắn được thiết kế tốt | Còn phải xét tốc độ tăng, truy vấn, contention và vòng đời |
| Giữ tính nguyên tử đồng nghĩa MongoDB tự kiểm tra mọi quy tắc nghiệp vụ | Logic tính toán, điều kiện update và validation vẫn phải được thiết kế đúng |
| Nhúng giá tại lúc mua là dữ liệu trùng lặp sai | Snapshot lịch sử thường là lựa chọn có chủ đích |

## 15. Bài thực hành: xây dựng mô hình đơn hàng có atomic update

Phần này dùng **mongosh** và database thử nghiệm **document_boundary_lab**. Các lệnh độc lập có thể chạy theo thứ tự. Những số liệu và ID chỉ phục vụ minh họa.

### Bài 1: tạo document đơn hàng

~~~javascript
use document_boundary_lab

db.orders.insertOne({
  _id: "ORD-1001",
  status: "DRAFT",
  items: [
    {
      sku: "BOOK-01",
      quantity: 1,
      unitPrice: NumberDecimal("100000.00")
    }
  ],
  totalAmount: NumberDecimal("100000.00"),
  version: 1
});
~~~

Hãy xác định:

- Ranh giới nguyên tử nằm ở đâu?
- **items[0]** có phải document độc lập ở collection khác không?
- Những field nào có thể đổi cùng một thao tác update?

### Bài 2: thêm item và tăng tổng tiền nguyên tử

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001", status: "DRAFT" },
  {
    $push: {
      items: {
        sku: "PEN-02",
        quantity: 2,
        unitPrice: NumberDecimal("10000.00")
      }
    },
    $inc: {
      totalAmount: NumberDecimal("20000.00"),
      version: 1
    }
  }
);

db.orders.findOne({ _id: "ORD-1001" });
~~~

Kết quả mong đợi sau thao tác thành công trên document được tạo từ Bài 1:

~~~text
items có 2 dòng
totalAmount = 120000.00
version = 2
~~~

Hãy giải thích vì sao các thay đổi trên cùng document thuộc một atomic write, và trường hợp nào vẫn có thể khiến tổng tiền sai dù write được thực thi nguyên tử.

### Bài 3: xác nhận đơn có điều kiện

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "ORD-1001",
    status: "DRAFT",
    version: 2
  },
  {
    $set: {
      status: "CONFIRMED",
      confirmedAt: new Date()
    },
    $inc: {
      version: 1
    }
  }
);

printjson(result);
~~~

Chạy lại chính lệnh update với filter **status: "DRAFT", version: 2**. Lần tiếp theo sẽ không còn khớp document đã xác nhận. Sử dụng **matchedCount** để phân biệt “không có document phù hợp” với “đã xác nhận thành công”.

### Bài 4: tồn kho là ranh giới khác

~~~javascript
db.products.insertOne({
  _id: "BOOK-01",
  title: "Nhập môn MongoDB",
  stock: 3
});

db.products.updateOne(
  { _id: "BOOK-01", stock: { $gte: 2 } },
  { $inc: { stock: -2 } }
);
~~~

Bây giờ trả lời:

1. Vì sao **Product** và **Order** là hai document với hai ranh giới atomicity?
2. Nếu thao tác trừ stock thành công nhưng thao tác xác nhận order thất bại, hệ thống có thể rơi vào trạng thái nào?
3. Trường hợp nào nên cân nhắc transaction, trường hợp nào phù hợp với reservation và xử lý bất đồng bộ?
4. Nếu ứng dụng đọc tồn kho rồi **$set** bằng giá trị đã tính trước, có thể xuất hiện lost update nào?
5. Nếu thêm mọi lịch sử thay đổi stock vào một array của Product, rủi ro tăng trưởng nào có thể xảy ra?

### Bài 5: tự đưa ra quyết định mô hình

Xét một ứng dụng trò chuyện:

~~~text
Conversation
  ├── title
  ├── participants
  ├── messages (tăng liên tục)
  └── lastMessagePreview
~~~

Hãy quyết định phần nào nên nhúng, phần nào nên lưu collection riêng:

- **participants**: số lượng có giới hạn hay không, thay đổi cùng conversation hay độc lập?
- **messages**: có tăng không giới hạn, có cần phân trang theo thời gian không?
- **lastMessagePreview**: có cần hiển thị nhanh trên danh sách conversation không, được duy trì bằng cách nào?
- **unreadCount**: đếm toàn conversation hay riêng từng thành viên; ranh giới atomicity có đủ để cập nhật không?

Một lựa chọn khả thi là lưu **messages** ở collection riêng, giữ metadata conversation nhỏ và thiết kế việc cập nhật preview/counter theo mức nhất quán cần thiết. Kết luận cuối phụ thuộc vào quy mô và hành vi sử dụng thực tế.

## Tài liệu tham khảo

- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Embedded Data versus References](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/)
- [MongoDB Manual — Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Manual — BSON Document Size Limit](https://www.mongodb.com/docs/manual/reference/limits/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
