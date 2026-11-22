# Nhúng dữ liệu có cùng vòng đời hoặc cùng mẫu truy cập

## 1. Nhúng dữ liệu trong mô hình tài liệu là gì?

Trong cơ sở dữ liệu NoSQL dạng document, **nhúng dữ liệu (embedding)** là lưu một đối tượng con hoặc một nhóm đối tượng con ngay bên trong tài liệu cha, thay vì đưa chúng vào một collection riêng rồi nối bằng mã định danh.

Ví dụ, thông tin giao hàng được nhúng trực tiếp trong một tài liệu đơn hàng:

~~~json
{
  "_id": "order-1001",
  "customerId": "customer-42",
  "status": "CONFIRMED",
  "shippingAddress": {
    "recipient": "Minh",
    "city": "Da Nang",
    "district": "Hai Chau",
    "street": "12 Nguyen Van Linh"
  }
}
~~~

Ở đây, `shippingAddress` không cần một ID độc lập để hiển thị cùng đơn hàng. Ứng dụng đọc đơn hàng là có thông tin giao hàng tương ứng.

Nếu thiết kế theo hướng tham chiếu, dữ liệu có thể tách ra:

~~~json
{
  "_id": "order-1001",
  "customerId": "customer-42",
  "shippingAddressId": "address-7"
}
~~~

~~~json
{
  "_id": "address-7",
  "recipient": "Minh",
  "city": "Da Nang",
  "district": "Hai Chau",
  "street": "12 Nguyen Van Linh"
}
~~~

Cách tham chiếu khiến ứng dụng cần lấy thêm tài liệu địa chỉ hoặc thực hiện cơ chế truy vấn ghép nếu muốn hiển thị đầy đủ đơn hàng. Nhưng tham chiếu có lợi khi địa chỉ là một thực thể riêng được nhiều nơi dùng chung và cập nhật độc lập.

**Câu hỏi quyết định không chỉ là “dữ liệu có quan hệ với nhau không?”, mà là “dữ liệu này có được tạo, đọc, cập nhật và xóa như một phần của cùng thực thể nghiệp vụ không?”**

Nhúng phù hợp nhất khi dữ liệu con **cùng vòng đời** với tài liệu cha, **thường được truy cập cùng cha**, hoặc cả hai. Cần xét thêm giới hạn kích thước, tần suất thay đổi, khả năng chia sẻ và mức độ đồng thời.

## 2. Hiểu hai tiêu chí chính

### 2.1. “Cùng vòng đời” nghĩa là gì?

Hai phần dữ liệu có **cùng vòng đời** khi chúng thường:

- Được tạo trong cùng một thao tác nghiệp vụ.
- Cùng thuộc quyền sở hữu của một thực thể cha.
- Được sửa đổi như các phần của cùng một trạng thái.
- Được lưu giữ và xóa theo cùng chính sách.
- Ít có nhu cầu tồn tại độc lập sau khi cha bị xóa.
- Thường cần được thay đổi một cách nhất quán trong cùng một thao tác.

Ví dụ:

- Một **đơn hàng** và các **dòng sản phẩm đã mua** được tạo cùng lúc. Dòng hàng là một phần cấu thành đơn hàng và thường phải được giữ cùng đơn hàng để bảo toàn lịch sử.
- Một **hồ sơ người dùng** và **tùy chọn hiển thị** như ngôn ngữ, giao diện sáng/tối thường được tạo và quản lý cùng hồ sơ.
- Một **bài khảo sát** và những **lựa chọn trả lời cố định** thuộc bản định nghĩa khảo sát có thể được lưu trong cùng tài liệu khi số lựa chọn nhỏ và có giới hạn.

Ngược lại, một **sản phẩm trong danh mục** có vòng đời độc lập với một đơn hàng. Sản phẩm có thể đổi tên hoặc giá trong khi đơn hàng cũ cần giữ tên và giá tại thời điểm mua. Vì vậy, thường nhúng **bản chụp thông tin sản phẩm tại lúc đặt hàng** vào dòng hàng, nhưng vẫn giữ tài liệu sản phẩm gốc độc lập.

“Cùng vòng đời” còn có nghĩa cả hai phải tuân cùng quy tắc giữ dữ liệu. Nếu một nhóm dữ liệu cần hết hạn sau 30 ngày nhưng cha cần giữ 10 năm, nhúng cả hai có thể làm chính sách xóa trở nên khó thực hiện.

### 2.2. “Cùng mẫu truy cập” nghĩa là gì?

**Mẫu truy cập (access pattern)** là những thao tác mà ứng dụng thực sự thực hiện trên dữ liệu: đọc theo khóa nào, lấy trường nào, lọc theo thuộc tính nào, ghi/đổi trường nào, tần suất bao nhiêu và yêu cầu độ trễ ra sao.

Hai phần dữ liệu có **cùng mẫu truy cập** khi chúng thường được đọc hoặc cập nhật chung trong một yêu cầu.

Ví dụ, màn hình chi tiết đơn hàng cần:

~~~text
GET /orders/order-1001

Cần trả về:
- Mã đơn, ngày tạo và trạng thái
- Địa chỉ giao hàng tại thời điểm đặt
- Các dòng sản phẩm, số lượng và giá tại thời điểm mua
- Tổng tiền và thông tin tiền tệ
~~~

Nếu ứng dụng gần như luôn hiển thị các trường trên cùng nhau, nhúng chúng trong một tài liệu giúp có khả năng đáp ứng bằng **một lần đọc tài liệu**.

Một màn hình khác chỉ liệt kê 20 đơn hàng gần nhất có thể chỉ cần mã, thời gian, tổng tiền và trạng thái. Khi đó, ứng dụng nên dùng **projection** hoặc cấu trúc đọc phù hợp, không phải tải toàn bộ từng đơn hàng lớn.

Điểm cốt lõi: **cách dữ liệu được tiêu thụ quan trọng không kém cách dữ liệu được phân loại trong nghiệp vụ**. Hai thực thể liên quan nhưng ít khi được đọc cùng nhau có thể nên tách; hai phần nhỏ, có quan hệ sở hữu chặt và thường được đọc chung có thể nên nhúng.

### 2.3. Cùng vòng đời và cùng mẫu truy cập không phải hai điều kiện bắt buộc đồng thời

| Tình huống | Cùng vòng đời? | Thường truy cập cùng nhau? | Hướng thiết kế thường cân nhắc |
|---|---|---|---|
| Đơn hàng và các dòng hàng | Có | Có | Nhúng các dòng hàng vào đơn hàng nếu số lượng có giới hạn |
| Hồ sơ và tùy chọn giao diện | Thường có | Thường có | Nhúng đối tượng cấu hình nhỏ |
| Bài viết và hàng triệu bình luận | Có quan hệ sở hữu, nhưng bình luận có thể cần quản lý riêng | Thường đọc theo trang, không đọc tất cả | Tách bình luận; có thể nhúng vài bình luận gần nhất như bản chiếu |
| Đơn hàng và sản phẩm danh mục | Không | Có lúc cần hiển thị cùng nhau | Nhúng snapshot cần thiết, giữ sản phẩm gốc riêng |
| Người dùng và lịch sử đăng nhập nhiều năm | Không hoàn toàn | Hiếm khi đọc cùng hồ sơ | Tách lịch sử; phân trang và TTL độc lập |
| Cấu hình ứng dụng và tập cài đặt nhỏ | Thường có | Có | Nhúng nếu kích thước và tần suất cập nhật phù hợp |

Nhúng là **một lựa chọn mô hình hóa**, không phải quy tắc tuyệt đối cho mọi quan hệ “một–nhiều”.

## 3. Nhìn dữ liệu dưới góc độ aggregate nghiệp vụ

Một cách hữu ích để suy nghĩ về embedding là xác định **aggregate**: một cụm dữ liệu cần được xử lý như một đơn vị nhất quán cho những quy tắc nghiệp vụ quan trọng.

Ví dụ đơn hàng:

~~~text
Order
├── id
├── customerId
├── status
├── shippingAddress (snapshot)
├── items[]
│   ├── lineId
│   ├── productId
│   ├── productName (snapshot)
│   ├── unitPriceVnd
│   └── quantity
├── totalVnd
└── createdAt
~~~

Đơn hàng là **aggregate root**; các dòng hàng có thể là phần con, được truy cập qua đơn hàng. Tuy nhiên, khái niệm aggregate trong thiết kế nghiệp vụ và giới hạn document của một DBMS không hoàn toàn giống nhau: một aggregate rất lớn có thể cần phân rã vì giới hạn kích thước hoặc hiệu năng.

### 3.1. Một tài liệu đơn hàng mẫu

~~~json
{
  "_id": "order-1001",
  "customerId": "customer-42",
  "status": "CONFIRMED",
  "currency": "VND",
  "shippingAddress": {
    "recipient": "Minh",
    "phoneMasked": "***1234",
    "city": "Da Nang",
    "district": "Hai Chau",
    "street": "12 Nguyen Van Linh"
  },
  "items": [
    {
      "lineId": "line-1",
      "productId": "product-8",
      "productName": "Chuột không dây",
      "unitPriceVnd": 450000,
      "quantity": 2
    },
    {
      "lineId": "line-2",
      "productId": "product-21",
      "productName": "Bàn di chuột",
      "unitPriceVnd": 150000,
      "quantity": 1
    }
  ],
  "totalVnd": 1050000,
  "createdAt": "2026-11-14T08:15:27Z",
  "schemaVersion": 1
}
~~~

Trong ví dụ, `totalVnd` được tính từ hai dòng: `450000 × 2 + 150000 × 1 = 1050000`. Giá được lưu dưới dạng số nguyên theo đơn vị VND để tránh sai số nhị phân khi xử lý số tiền trong ví dụ; hệ thực tế cần có quy ước tiền tệ, thuế, chiết khấu và làm tròn rõ ràng.

Những thành phần được nhúng:

- `shippingAddress` là **ảnh chụp địa chỉ lúc mua**. Người dùng đổi địa chỉ mặc định sau này không nên làm thay đổi lịch sử giao hàng.
- `items` chứa các dòng hàng đã đặt, bao gồm tên và giá tại thời điểm xác nhận. Sản phẩm danh mục có thể đổi tên hoặc giá mà không ảnh hưởng đơn cũ.
- `totalVnd` và `status` được dùng với dòng hàng trong các thao tác quản lý đơn.

Những thành phần vẫn nên cân nhắc tham chiếu độc lập:

- `customerId` trỏ tới hồ sơ khách hàng, vì khách hàng có vòng đời riêng.
- `productId` trỏ tới sản phẩm gốc để hỗ trợ truy vết nhưng **không thay thế snapshot tên/giá**.
- Kho tồn, thanh toán, vận chuyển hoặc nhật ký kiểm toán có thể cần các thực thể, quy tắc nhất quán và chính sách lưu giữ riêng.

Nhúng các dòng hàng không có nghĩa **mọi nghiệp vụ của đơn hàng** phải hoặc có thể nằm trong một document.

### 3.2. Sơ đồ nhúng và tham chiếu kết hợp

~~~mermaid
flowchart LR
    Customer["Customer document"] -->|"customerId"| Order["Order document"]
    Order --> Address["shippingAddress: snapshot nhúng"]
    Order --> Items["items[]: các dòng hàng nhúng"]
    Items -. "productId tham chiếu" .-> Product["Product catalog document"]
    Order -. "orderId" .-> Payment["Payment record độc lập"]
    Order -. "orderId" .-> Inventory["Inventory / reservation độc lập"]
~~~

Các mũi tên biểu thị **quan hệ logic**. Độ nguyên tử của các thao tác cập nhật qua nhiều tài liệu phụ thuộc DBMS và giao dịch được cấu hình; không thể suy ra từ sơ đồ.

## 4. Tại sao embedding hỗ trợ đọc dữ liệu?

### 4.1. Giảm số lần truy cập và ghép dữ liệu

Giả sử màn hình chi tiết đơn cần trạng thái, địa chỉ giao và 10 dòng hàng.

**Thiết kế nhúng:**

~~~text
Ứng dụng
   |
   | Đọc orders/order-1001
   v
Một document chứa dữ liệu cần hiển thị
~~~

**Thiết kế tham chiếu:**

~~~text
Ứng dụng
   |
   +--> Đọc orders/order-1001
   |
   +--> Đọc shippingAddresses/address-7
   |
   +--> Đọc orderItems theo orderId
   |
   +--> Có thể phải ghép dữ liệu ở ứng dụng hoặc DBMS
~~~

Embedding thường giảm nhu cầu ghép dữ liệu và các vòng truyền mạng. Điều đó đặc biệt có ích khi dữ liệu con nhỏ, được truy xuất với cha trong đa số lần đọc.

Tuy nhiên, **một lần đọc document không luôn rẻ hơn mọi cách khác**. Một tài liệu lớn có thể gây:

- Lượng dữ liệu truyền qua mạng cao nếu ứng dụng cần rất ít trường.
- Nhiều dữ liệu phải nạp vào bộ nhớ hoặc cache.
- Chi phí giải mã, serialization và xử lý kết quả.
- Vấn đề tranh chấp cập nhật trên cùng tài liệu.

Do đó lợi ích phải được đánh giá bằng **mẫu đọc cụ thể** và kích thước dữ liệu thực tế.

### 4.2. Locality và tính dự đoán được của truy vấn

Đặt các trường liên quan gần nhau về mặt logic giúp người lập trình dễ biết rằng việc lấy một đơn hàng có thể mang đủ những phần dữ liệu cần thiết. Không cần giả định mọi lần đọc sẽ phải tra thêm mười collection.

Đây là **tính cục bộ dữ liệu (data locality) ở mức mô hình tài liệu**. Nó không đảm bảo mọi trường được đặt liên tiếp vật lý trên đĩa, cũng không có nghĩa truy vấn luôn tránh được mạng trong một cụm phân tán.

### 4.3. Đọc đúng phạm vi và dùng projection

Ví dụ truy vấn MongoDB minh họa cách lấy toàn bộ đơn hàng:

~~~javascript
db.orders.findOne({ _id: "order-1001" });
~~~

Nếu chỉ xây danh sách đơn, dùng projection:

~~~javascript
db.orders.find(
  { customerId: "customer-42" },
  {
    _id: 1,
    status: 1,
    totalVnd: 1,
    createdAt: 1
  }
).sort({ createdAt: -1, _id: -1 }).limit(20);
~~~

Projection giúp giảm trường được trả về qua mạng, nhưng **không đồng nghĩa mọi DBMS chỉ đọc đúng những byte đã chọn từ đĩa**; điều đó tùy engine và việc truy vấn có được chỉ mục bao phủ hay không.

Có thể tạo chỉ mục phù hợp cho thao tác liệt kê:

~~~javascript
db.orders.createIndex({ customerId: 1, createdAt: -1, _id: -1 });
~~~

Với document store, nên thiết kế cùng lúc **cấu trúc tài liệu và các truy vấn quan trọng**, thay vì xem embedding là một phép tối ưu độc lập.

## 5. Nhúng hỗ trợ tính nhất quán khi cập nhật một tài liệu

Một lợi ích quan trọng của nhúng là các trường thuộc cùng document thường nằm trong **phạm vi ghi nguyên tử ở cấp tài liệu** nếu DBMS cung cấp bảo đảm đó. Chẳng hạn, MongoDB bảo đảm thao tác ghi vào **một document** là nguyên tử, kể cả khi thao tác sửa nhiều trường trong chính document ấy.

### 5.1. Ví dụ chuyển trạng thái đơn hàng có điều kiện

Giả sử chỉ cho phép chuyển `PENDING` sang `CONFIRMED`:

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "order-1001",
    status: "PENDING",
    version: 3
  },
  {
    $set: {
      status: "CONFIRMED",
      updatedAt: new Date()
    },
    $inc: { version: 1 }
  }
);

if (result.matchedCount === 0) {
  // Đơn không còn đúng trạng thái/phiên bản dự kiến.
  // Ứng dụng cần tải lại dữ liệu và xử lý xung đột.
}
~~~

Ví dụ này giả định tài liệu có trường `version` và trạng thái ban đầu là `PENDING`. Điều kiện trên `status` và `version` là cách **kiểm soát cập nhật đồng thời (optimistic concurrency)** đơn giản: chỉ cập nhật khi trạng thái còn như mong đợi.

Việc đổi trạng thái và tăng phiên bản xảy ra trong một lần cập nhật document. Nhưng nếu cần đồng thời trừ tồn kho ở một tài liệu khác hoặc ghi giao dịch thanh toán, tính nguyên tử **không tự mở rộng qua các tài liệu**. Khi đó phải xem cơ chế transaction của DBMS và cách phối hợp nghiệp vụ.

### 5.2. Nhúng một nhóm dữ liệu cần đổi cùng nhau

Ví dụ cấu hình thông báo của người dùng:

~~~json
{
  "_id": "user-101",
  "displayName": "Lan",
  "notificationPreferences": {
    "email": true,
    "push": false,
    "digestFrequency": "WEEKLY"
  },
  "theme": "dark"
}
~~~

Đổi một nhóm thiết lập có thể thực hiện trong một thao tác trên document:

~~~javascript
db.users.updateOne(
  { _id: "user-101" },
  {
    $set: {
      "notificationPreferences.email": false,
      "notificationPreferences.digestFrequency": "MONTHLY"
    }
  }
);
~~~

Các thuộc tính không liên quan như `displayName` không cần thay đổi.

**Lưu ý:** Một document có thể được cập nhật nguyên tử không có nghĩa mọi cập nhật đồng thời đều tự giải quyết đúng mọi tranh chấp. Ứng dụng vẫn cần xét các thao tác đọc–sửa–ghi có nguy cơ ghi đè, áp dụng điều kiện version, toán tử cập nhật phù hợp hoặc transaction khi cần.

## 6. Các dấu hiệu cho thấy nên nhúng dữ liệu

Dưới đây là những câu hỏi hữu ích khi thiết kế.

### 6.1. Dữ liệu con thuộc độc quyền một tài liệu cha

Một địa chỉ giao hàng đã được chốt trong đơn hàng thường là **bản sao thuộc riêng đơn đó**. Dù hai đơn có cùng địa chỉ, mỗi đơn cần giữ ảnh chụp lịch sử tại thời điểm tạo.

Ngược lại, hồ sơ một khách hàng được nhiều đơn tham chiếu; không nên nhúng toàn bộ hồ sơ sống vào từng đơn rồi phải cập nhật mọi đơn khi khách đổi tên.

### 6.2. Dữ liệu con nhỏ hoặc số phần tử có giới hạn

Ví dụ `shippingAddress` có số trường tương đối cố định; `order.items` của một đơn bán lẻ thông thường cũng thường có giới hạn theo nghiệp vụ. Một mảng vài lựa chọn cấu hình hoặc vài số điện thoại liên hệ có thể dễ nhúng.

Với danh sách có thể phát triển không giới hạn như **mọi sự kiện truy cập của người dùng**, **toàn bộ bình luận của bài đăng phổ biến** hoặc **mọi lần thanh toán trong nhiều năm**, nhúng tất cả vào một tài liệu cha dễ gây vấn đề kích thước và cập nhật.

Giới hạn phải do nghiệp vụ và số liệu thực tế xác định. “Hiện chỉ có vài phần tử” chưa phải bằng chứng dữ liệu sẽ mãi nhỏ.

### 6.3. Dữ liệu thường được đọc cùng cha

Ví dụ màn hình hồ sơ luôn cần cài đặt ngôn ngữ và múi giờ, còn hệ thống chỉ thỉnh thoảng chỉnh những cài đặt này. Nhúng giúp đọc gọn.

Nếu khách hàng chỉ mở lịch sử đơn hàng trong một màn hình riêng và có thể có hàng trăm nghìn đơn, không nên nhúng toàn bộ đơn hàng vào hồ sơ khách hàng.

### 6.4. Dữ liệu có nhịp cập nhật tương tự

Nếu dữ liệu con thay đổi khi đối tượng cha chuyển trạng thái, việc nhúng thường tự nhiên. Ví dụ một giỏ hàng chứa một danh sách mặt hàng có giới hạn, được hiển thị và cập nhật cùng giỏ.

Tuy nhiên, nếu một phần dữ liệu được cập nhật cực kỳ thường xuyên bởi nhiều tác nhân độc lập, việc nhúng có thể làm các cập nhật dồn vào cùng một document, tăng tranh chấp hoặc tải lên cùng một đơn vị lưu trữ.

### 6.5. Dữ liệu có cùng yêu cầu phân quyền và lưu giữ

Nếu con phải được xóa hoặc ẩn theo chính sách khác cha, việc nhúng có thể gây phức tạp. Ví dụ tài liệu nghiệp vụ phải giữ nhiều năm nhưng dữ liệu nhạy cảm chỉ được lưu ngắn hạn; lúc đó cần thiết kế retention và cách xóa trường con rất cẩn thận, hoặc tách hẳn thành tài liệu khác.

## 7. Khi nào không nên nhúng toàn bộ?

### 7.1. Quan hệ một–nhiều không giới hạn

Một bài đăng có thể nhận hàng triệu bình luận:

~~~text
post-1
  comments[0]
  comments[1]
  comments[2]
  ...
  comments[999999]
~~~

Nếu nhúng tất cả bình luận:

- Document liên tục tăng kích thước.
- Các tác giả khác nhau cùng ghi vào một document, có thể gây tranh chấp.
- Việc phân trang bình luận và tìm kiếm theo tác giả trở nên khó hơn.
- Xóa một bình luận, lưu metadata/moderation và đặt TTL riêng có thể phức tạp.
- Tài liệu có thể vượt giới hạn kích thước của DBMS.

MongoDB, chẳng hạn, có giới hạn **16 MiB cho một BSON document**. Đây là giới hạn của MongoDB, không phải quy tắc chung của mọi hệ NoSQL document. Ngay cả khi chưa chạm giới hạn, document lớn cũng có thể tạo chi phí đọc/ghi đáng kể.

Một mô hình thường hợp lý hơn:

~~~json
{
  "_id": "post-1",
  "title": "Tìm hiểu NoSQL",
  "commentCount": 58210,
  "recentCommentsPreview": [
    { "commentId": "c58209", "text": "Rất hữu ích!" },
    { "commentId": "c58210", "text": "Cảm ơn bài viết." }
  ]
}
~~~

Và comment riêng:

~~~json
{
  "_id": "c58210",
  "postId": "post-1",
  "authorId": "user-89",
  "text": "Cảm ơn bài viết.",
  "createdAt": "2026-11-14T08:20:00Z"
}
~~~

Danh sách `recentCommentsPreview` nếu được lưu trong post là **bản chiếu giới hạn**, không phải nguồn dữ liệu bình luận đầy đủ. Ứng dụng phải quyết định cập nhật bản chiếu bằng cơ chế nào, độ trễ chấp nhận được và xử lý khi bản chiếu lệch với dữ liệu chính.

### 7.2. Dữ liệu con tồn tại độc lập và được nhiều cha dùng chung

Ví dụ sản phẩm danh mục có thể xuất hiện trong hàng triệu đơn hàng. Không nên mỗi lần đổi mô tả sản phẩm lại phải cập nhật hàng triệu đơn, vừa tốn tài nguyên vừa sửa sai lịch sử giao dịch.

Cách phù hợp thường là:

- Lưu **product document** làm nguồn thông tin sản phẩm hiện tại.
- Lưu **productId** trong dòng đơn hàng để liên kết.
- Nhúng **snapshot** tên, giá và các thông số cần bảo toàn tại thời điểm mua.

Một phần dữ liệu có thể được nhúng vì mục tiêu lịch sử, trong khi thực thể gốc vẫn phải là tài liệu riêng.

### 7.3. Dữ liệu có nhịp ghi, chỉ mục hoặc quyền truy cập khác nhau

Hồ sơ tài khoản được đọc thường xuyên nhưng nhật ký đăng nhập được ghi liên tục, có TTL riêng và chỉ người quản trị được phép truy vấn. Lưu toàn bộ lịch sử đăng nhập trong một document hồ sơ là một lựa chọn kém phù hợp.

Tách thành tài liệu riêng sẽ giúp:

- Đánh chỉ mục và phân vùng nhật ký theo thời gian.
- Phân trang lịch sử độc lập.
- Áp dụng retention và quyền truy cập khác nhau.
- Tránh làm phình to document hồ sơ và tăng tranh chấp ghi.

### 7.4. Quan hệ nhiều–nhiều hoặc mạng liên kết phức tạp

Nhúng toàn bộ danh sách bạn bè của mọi người dùng vào mỗi hồ sơ có thể phù hợp với danh sách rất nhỏ, nhưng không thích hợp nếu có nhiều mối quan hệ và cần truy vấn nhiều bước. Khi liên kết có vòng đời riêng hoặc quy mô lớn, dùng collection quan hệ/cạnh hoặc mô hình graph có thể hợp lý hơn.

### 7.5. Nhúng dữ liệu nhạy cảm không phù hợp với phạm vi đọc

Nếu mọi màn hình đọc document đơn hàng đều có khả năng nhận dữ liệu cá nhân nhạy cảm nhúng bên trong, ứng dụng dễ trả dư dữ liệu nếu không giới hạn projection, quyền và cách serialize. Một nhóm dữ liệu cần kiểm soát truy cập riêng có thể đáng tách ra.

Phải xét cả kiểm soát truy cập, encryption, logging và chính sách xóa, ngoài hiệu năng.

## 8. Nhúng và tham chiếu: so sánh theo tiêu chí nghiệp vụ

| Tiêu chí | Nhúng (embedding) | Tham chiếu (referencing) |
|---|---|---|
| Đọc cha cùng dữ liệu con | Thường thuận tiện vì một document đã chứa dữ liệu | Có thể cần đọc thêm hoặc truy vấn ghép |
| Cập nhật các trường con cùng cha | Có thể hưởng bảo đảm nguyên tử trong một document nếu DBMS hỗ trợ | Phụ thuộc giao dịch và cách phối hợp nhiều document |
| Sửa một thực thể dùng chung | Dễ tạo nhiều bản sao cần cập nhật | Dễ duy trì một nguồn dữ liệu chính |
| Số lượng con tăng không giới hạn | Có nguy cơ document phình to | Dễ quản lý từng con riêng và phân trang |
| Tải ghi của nhiều đối tượng con | Có thể tập trung vào một document | Có thể phân tán theo khóa các document con |
| Xóa cả cây dữ liệu | Xóa cha thường xóa luôn dữ liệu nhúng | Có thể cần cascade hoặc xử lý dọn dữ liệu |
| Lưu con độc lập với cha | Khó hơn khi vòng đời khác nhau | Thuận tiện hơn |
| Bảo toàn snapshot lịch sử | Rất phù hợp khi cố ý sao chép bất biến | Chỉ tham chiếu tới dữ liệu sống có thể làm thay đổi cách diễn giải lịch sử |
| Chỉ mục trên trường con | Có thể hỗ trợ, nhưng tốn chỉ mục trên document/array | Có thể tối ưu riêng cho collection con |
| Khả năng mở rộng | Phụ thuộc kích thước document và phân vùng cha | Có thể phân vùng linh hoạt, đổi lại nhiều truy vấn và đồng bộ hơn |

Đây là các đặc tính thiết kế thường gặp, không phải cam kết rằng một phương án luôn có độ trễ thấp hơn phương án còn lại.

## 9. Ba mẫu embedding phổ biến

### 9.1. Nhúng đối tượng con nhỏ

Ví dụ hồ sơ có tùy chọn:

~~~json
{
  "_id": "user-101",
  "name": "Lan",
  "preferences": {
    "language": "vi",
    "theme": "dark",
    "receiveDigest": true
  }
}
~~~

Đối tượng `preferences` nhỏ, thường đọc cùng hồ sơ, không cần tồn tại khi người dùng bị xóa. Đây là ví dụ thuận lợi để nhúng.

### 9.2. Nhúng danh sách có giới hạn

Ví dụ khảo sát có một số câu hỏi, mỗi câu có vài lựa chọn:

~~~json
{
  "_id": "survey-11",
  "title": "Đánh giá khóa học",
  "questions": [
    {
      "questionId": "q1",
      "text": "Bạn đánh giá nội dung thế nào?",
      "options": [
        { "optionId": "A", "label": "Rất tốt" },
        { "optionId": "B", "label": "Tốt" },
        { "optionId": "C", "label": "Cần cải thiện" }
      ]
    }
  ]
}
~~~

Nếu một bản khảo sát được phát hành và quản lý như **một phiên bản cố định**, nhúng bộ câu hỏi giúp đọc một lần là có cấu trúc hoàn chỉnh. Nhưng **các câu trả lời của hàng triệu người** phải là tập dữ liệu riêng hoặc có cấu trúc phân vùng thích hợp; không nhúng toàn bộ vào cùng tài liệu khảo sát.

### 9.3. Nhúng snapshot

Dòng đơn hàng thường cần giữ lại:

~~~json
{
  "productId": "product-8",
  "productName": "Chuột không dây",
  "unitPriceVnd": 450000,
  "quantity": 2
}
~~~

Tên và giá ở đây là **snapshot**. Nếu catalog hiện tại đổi giá thành 490000 VND, đơn cũ vẫn ghi 450000 VND theo giao dịch tại thời điểm đặt.

Snapshot là cách nhúng có chủ ý **dữ liệu lặp** để bảo toàn đúng ngữ cảnh lịch sử. Nó phù hợp khi người đọc cần bản dữ liệu như tại thời điểm sự kiện; không nên coi mọi bản sao này là dữ liệu sống cần cập nhật đồng bộ với nguồn.

## 10. Ví dụ MongoDB: thao tác với dữ liệu nhúng

Ví dụ trong phần này minh họa cú pháp MongoDB. Những nguyên tắc vòng đời và mẫu truy cập vẫn áp dụng cho nhiều document database khác, nhưng các toán tử và giới hạn cụ thể tùy sản phẩm.

### 10.1. Chèn một tài liệu có thông tin nhúng

~~~javascript
db.orders.insertOne({
  _id: "order-2001",
  customerId: "customer-42",
  status: "PENDING",
  shippingAddress: {
    recipient: "Minh",
    city: "Da Nang",
    street: "12 Nguyen Van Linh"
  },
  items: [
    {
      lineId: "line-1",
      productId: "product-8",
      productName: "Chuột không dây",
      unitPriceVnd: 450000,
      quantity: 2
    }
  ],
  totalVnd: 900000,
  createdAt: new Date(),
  schemaVersion: 1
});
~~~

Vì thông tin địa chỉ và dòng hàng đã nằm trong tài liệu, thao tác đọc chi tiết đơn không cần truy vấn một collection `order_items` chỉ để xây màn hình này.

### 10.2. Đọc trường lồng nhau

Tìm đơn giao tới Đà Nẵng:

~~~javascript
db.orders.find(
  { "shippingAddress.city": "Da Nang" },
  { _id: 1, customerId: 1, status: 1, shippingAddress: 1 }
);
~~~

Tìm đơn chứa sản phẩm cụ thể:

~~~javascript
db.orders.find(
  { "items.productId": "product-8" },
  { _id: 1, customerId: 1, items: 1 }
);
~~~

Nếu muốn nhiều điều kiện áp dụng cho **cùng một phần tử mảng**, nên dùng `$elemMatch`:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      productId: "product-8",
      quantity: { $gte: 2 }
    }
  }
});
~~~

Nếu viết hai điều kiện riêng như `"items.productId"` và `"items.quantity"` mà không có `$elemMatch`, MongoDB có thể khớp hai phần tử **khác nhau** của cùng mảng. Đây là khác biệt cần hiểu khi truy vấn mảng document.

### 10.3. Cập nhật trường con

Thay đổi trạng thái đơn:

~~~javascript
db.orders.updateOne(
  { _id: "order-2001", status: "PENDING" },
  {
    $set: {
      status: "CONFIRMED",
      updatedAt: new Date()
    }
  }
);
~~~

Không cần gửi lại toàn bộ tài liệu. Với những trường có tính lịch sử như `shippingAddress` và giá tại thời điểm mua, thường không nên cập nhật theo thay đổi hiện tại của khách hoặc catalog sau khi đơn đã xác nhận.

### 10.4. Chỉ mục cho thuộc tính nhúng

Để phục vụ truy vấn đơn của khách hàng theo thời gian:

~~~javascript
db.orders.createIndex({
  customerId: 1,
  createdAt: -1
});
~~~

Nếu thường xuyên tra đơn theo mã sản phẩm, có thể cân nhắc:

~~~javascript
db.orders.createIndex({
  "items.productId": 1
});
~~~

Vì `items` là mảng, index trên `items.productId` là một dạng **multikey index**. Nó giúp một số mẫu lọc nhưng tốn không gian và chi phí bảo trì khi thêm/sửa phần tử. Chọn chỉ mục theo khối lượng truy vấn thực tế, không nên tạo mọi chỉ mục có thể tưởng tượng.

### 10.5. Giới hạn mảng được nhúng

Với một danh sách **bản xem trước** có giới hạn, MongoDB có thể dùng toán tử `$push` cùng `$each`, `$sort` và `$slice`:

~~~javascript
db.users.updateOne(
  { _id: "user-101" },
  {
    $push: {
      recentViews: {
        $each: [{
          productId: "product-8",
          viewedAt: new Date()
        }],
        $sort: { viewedAt: -1 },
        $slice: 20
      }
    }
  }
);
~~~

Thao tác trên giữ tối đa 20 lượt xem có `viewedAt` mới nhất trong mảng theo logic cập nhật. Nhưng đây chỉ là **lịch sử xem rút gọn**; nếu cần lưu đầy đủ mọi sự kiện, phải dùng collection hoặc hệ lưu trữ độc lập cho lịch sử. Thời gian từ các nguồn khác nhau cũng có thể lệch, và phần tử có cùng `viewedAt` không tự có thứ tự duy nhất.

## 11. Giới hạn kích thước và sự tăng trưởng của document

### 11.1. Dự đoán kích thước theo số phần tử

Giả sử một tài liệu cha có 5 KB dữ liệu gốc, mỗi phần tử nhúng trung bình 2 KB:

~~~text
Kích thước xấp xỉ
= kích thước cha + số phần tử × kích thước mỗi phần tử + overhead

100 phần tử   -> khoảng 205 KB, chưa tính overhead
1.000 phần tử -> khoảng 2 MB, chưa tính overhead
5.000 phần tử -> khoảng 10 MB, chưa tính overhead
~~~

Con số chỉ để minh họa. Kích thước thật phụ thuộc định dạng BSON/JSON, tên trường, dữ liệu lồng nhau, encoding, index, compression và thay đổi theo thời gian.

Với MongoDB, một document BSON có giới hạn **16 MiB**. Nhưng không nên đợi gần 16 MiB mới xem xét thiết kế lại. Document lớn có thể trở nên bất tiện từ sớm vì:

- Tốn băng thông khi nhiều truy vấn cần phần dữ liệu lớn.
- Tăng áp lực bộ nhớ, cache và serializer.
- Làm một tài liệu thành điểm tập trung ghi của nhiều người dùng.
- Tăng chi phí đọc/ghi khi thêm mảng hoặc cập nhật các cấu trúc lớn.
- Làm snapshot, backup, replication và thao tác quản trị có thêm chi phí.

### 11.2. Phân biệt “bounded” theo kỹ thuật và theo nghiệp vụ

Một mảng có thể được giới hạn bằng chính sách sản phẩm, ví dụ giỏ hàng tối đa 100 dòng, mỗi dòng có kích thước hợp lý. Giới hạn đó phải được **thực thi**, không chỉ được ghi trong tài liệu thiết kế.

Một mảng ban đầu có vài phần tử nhưng không có giới hạn rõ ràng, chẳng hạn danh sách người theo dõi hoặc bình luận, về bản chất là **không giới hạn**. Khi dữ liệu tăng, phải cân nhắc tách collection, time bucket hoặc cách phân vùng riêng.

### 11.3. Bucket pattern

Nếu nhiều sự kiện có chung khóa truy vấn, có thể nhóm chúng thành **các document theo bucket có kích thước/chu kỳ hữu hạn**:

~~~json
{
  "_id": "sensor-17#2026-11-14T08",
  "sensorId": "sensor-17",
  "bucketHour": "2026-11-14T08:00:00Z",
  "measurements": [
    { "at": "2026-11-14T08:00:01Z", "value": 29.1 },
    { "at": "2026-11-14T08:00:02Z", "value": 29.2 }
  ],
  "measurementCount": 2
}
~~~

Mô hình bucket giúp giới hạn một tài liệu bằng khoảng thời gian hoặc số mẫu. Tuy nhiên, nếu mọi sự kiện cùng giờ ghi vào một bucket duy nhất, bucket đó có thể trở thành **điểm nóng ghi**. Cần chọn kích thước bucket, cách chia tải và chính sách kết thúc bucket theo workload.

Bucket pattern không phải lựa chọn bắt buộc cho mọi dữ liệu thời gian; một collection mỗi sự kiện một document cũng có thể đơn giản và phù hợp hơn.

## 12. Thay đổi dữ liệu nhúng theo thời gian

### 12.1. Một schema linh hoạt vẫn cần quy tắc

Document store cho phép tài liệu cùng collection có thuộc tính khác nhau. Điều đó hữu ích khi phần con cần thêm trường, nhưng ứng dụng vẫn phải biết cách đọc các phiên bản dữ liệu.

Ví dụ:

~~~json
{
  "_id": "order-1001",
  "schemaVersion": 1,
  "shippingAddress": {
    "recipient": "Minh",
    "city": "Da Nang"
  }
}
~~~

Phiên bản mới bổ sung mã vùng và chỉ dẫn:

~~~json
{
  "_id": "order-1002",
  "schemaVersion": 2,
  "shippingAddress": {
    "recipient": "Lan",
    "city": "Da Nang",
    "postalCode": "550000",
    "deliveryNote": "Gọi trước khi giao"
  }
}
~~~

Ứng dụng cần xử lý tài liệu cũ chưa có trường mới, áp dụng giá trị mặc định khi phù hợp và tránh cập nhật sai dữ liệu lịch sử.

### 12.2. Chiến lược tương thích khi triển khai

Một chu kỳ thay đổi có thể gồm:

1. **Xác định hợp đồng đọc mới:** trường nào bắt buộc, trường nào tùy chọn.
2. **Triển khai mã đọc chịu được phiên bản cũ** trước khi ghi dữ liệu cấu trúc mới.
3. **Bắt đầu ghi schema mới** với version rõ ràng.
4. **Backfill/migrate** những document cũ khi cần thiết và có thể làm an toàn.
5. **Theo dõi lỗi giải mã, dữ liệu thiếu trường và xung đột** trong thời gian chuyển đổi.
6. **Loại bỏ đường đọc cũ** khi đã bảo đảm không còn dữ liệu cần tương thích.

Với dữ liệu snapshot lịch sử, không nhất thiết phải ép mọi tài liệu cũ có toàn bộ trường mới; nên giữ ngữ nghĩa gốc và xử lý lúc đọc.

### 12.3. Validation quan trọng ngay cả khi schema linh hoạt

Với tài liệu đơn hàng, những ràng buộc như `quantity > 0`, `unitPriceVnd >= 0`, `currency` hợp lệ, và mỗi `lineId` phải có giá trị duy nhất trong một đơn cần được định nghĩa rõ.

Một số ràng buộc có thể áp dụng bằng schema validation của DBMS, số khác cần được thực thi trong ứng dụng hoặc cơ chế giao dịch. Không nên mặc nhiên cho rằng mọi validation trên quan hệ giữa các phần tử mảng đều được DBMS kiểm tra tự động.

## 13. Đồng thời ghi và giới hạn của “một tài liệu nguyên tử”

Nhúng một nhóm dữ liệu giúp cập nhật một document theo một lần ghi, nhưng nếu nhiều tác nhân cùng ghi:

- Hai người cùng sửa danh sách mặt hàng trong một giỏ.
- Nhiều thiết bị cùng cập nhật tài liệu thống kê.
- Hàng nghìn bình luận mới cùng ghi vào một bài đăng.
- Một tiến trình đọc tài liệu rồi ghi đè nguyên document khi tiến trình khác vừa sửa một trường.

Ứng dụng có thể gặp xung đột hoặc mất cập nhật nếu dùng mẫu đọc–sửa–ghi thiếu bảo vệ.

### 13.1. Ưu tiên toán tử cập nhật theo trường

Ví dụ muốn tăng bộ đếm:

~~~javascript
db.posts.updateOne(
  { _id: "post-1" },
  { $inc: { commentCount: 1 } }
);
~~~

Trong phạm vi một document, `$inc` tránh được một số vấn đề của việc đọc số hiện tại rồi ghi lại số mới từ client. Tuy nhiên, nếu comment chính được lưu trong collection khác, thao tác tăng `commentCount` và tạo comment là **hai ghi trên hai document**. Để bảo đảm bất biến giữa chúng, cần transaction hoặc mô hình đồng bộ phù hợp.

### 13.2. Không dùng document duy nhất làm điểm ghi tập trung vô hạn

Một thiết kế lưu tất cả phiên đăng nhập của mọi người dùng vào một document hệ thống sẽ nhanh chóng tạo nút nóng và giới hạn mở rộng. Mô hình “một document = một aggregate” có ích khi aggregate có phạm vi hợp lý, chứ không phải khi mọi dữ liệu của hệ thống bị gộp vào một đối tượng khổng lồ.

### 13.3. Quy tắc nhất quán phải theo phạm vi nghiệp vụ

Với đơn hàng, cập nhật trạng thái và version trong cùng document có thể dùng một ghi nguyên tử. Nhưng với đặt hàng:

~~~text
1. Tạo đơn
2. Giữ/chốt tồn kho
3. Thu tiền
4. Phát sự kiện xác nhận
~~~

Đây là nhiều tài nguyên và dịch vụ. Nhúng dòng hàng vào đơn **không tự bảo đảm** rằng tồn kho, thanh toán và sự kiện đều nhất quán. Cần cân nhắc transaction nhiều document nếu DBMS hỗ trợ trong phạm vi yêu cầu, hoặc các quy trình như outbox, xử lý idempotent, saga/bù trừ tùy kiến trúc.

## 14. Lựa chọn kết hợp embedding và referencing

Thực tế, mô hình hiệu quả thường không chọn “nhúng tất cả” hoặc “tham chiếu tất cả”. Một document có thể:

- Nhúng dữ liệu nhỏ, cùng vòng đời và thường được đọc chung.
- Chứa ID tham chiếu đến thực thể sống độc lập.
- Lưu snapshot tối thiểu của thực thể được tham chiếu để bảo toàn ngữ cảnh.
- Lưu một bản chiếu giới hạn cho màn hình đọc nhanh.
- Giữ lịch sử lớn trong collection riêng.

Ví dụ một bài học:

~~~json
{
  "_id": "lesson-80",
  "title": "Embedding trong document database",
  "authorId": "author-5",
  "authorDisplayNameAtPublish": "An",
  "metadata": {
    "language": "vi",
    "difficulty": "INTERMEDIATE"
  },
  "tags": ["nosql", "document"],
  "latestCommentPreview": [
    { "commentId": "c-900", "text": "Ví dụ dễ hiểu" }
  ],
  "commentCount": 458
}
~~~

Có thể tách:

~~~json
{
  "_id": "comment-c-900",
  "lessonId": "lesson-80",
  "authorId": "reader-11",
  "text": "Ví dụ dễ hiểu",
  "createdAt": "2026-11-14T08:20:00Z"
}
~~~

Trong đó:

- `metadata` và `tags` nhỏ, cùng vòng đời bài học nên có thể nhúng.
- `authorId` tham chiếu tới hồ sơ tác giả vốn tồn tại độc lập.
- `authorDisplayNameAtPublish` là snapshot phục vụ lịch sử xuất bản.
- `latestCommentPreview` giúp hiển thị nhanh nhưng là bản chiếu có thể trễ.
- `comments` đầy đủ được lưu riêng để tìm kiếm, phân trang, xóa và quản lý quyền.

Thiết kế này kết hợp nhiều tiêu chí thay vì xem embedding như lựa chọn nhị phân.

## 15. Một cách ra quyết định theo truy vấn và vòng đời

~~~mermaid
flowchart TD
    A["Xác định dữ liệu con và truy vấn thật"] --> B{"Con có vòng đời và quyền sở hữu độc lập?"}
    B -->|"Có"| R["Ưu tiên tham chiếu hoặc mô hình lai"]
    B -->|"Không / chủ yếu thuộc cha"| C{"Thường được đọc hay cập nhật cùng cha?"}
    C -->|"Có"| D{"Kích thước và số phần tử có giới hạn?"}
    C -->|"Không"| R
    D -->|"Không"| E["Tách collection hoặc bucket; có thể giữ preview"]
    D -->|"Có"| F{"Nhịp ghi và chính sách truy cập/lưu giữ tương thích?"}
    F -->|"Có"| G["Cân nhắc embedding"]
    F -->|"Không"| R
    G --> H["Đo truy vấn, tải, index và cạnh tranh ghi"]
    R --> H
    E --> H
~~~

Sơ đồ là một **hướng dẫn suy nghĩ**, không phải thuật toán tự động. Có trường hợp dữ liệu không cùng vòng đời nhưng cần nhúng **snapshot** phục vụ lịch sử. Cũng có trường hợp đọc cùng nhau thường xuyên nhưng mảng không giới hạn, buộc phải dùng mô hình lai.

### 15.1. Năm câu hỏi kiểm tra trước khi nhúng

**1. Nếu xóa cha, có nên xóa luôn con?** Nếu câu trả lời thường là có, đây là dấu hiệu vòng đời thống nhất. Nếu con cần tồn tại riêng vì pháp lý, chia sẻ hoặc vận hành, nên cân nhắc tách.

**2. Nếu đổi con, có cần cập nhật nhiều cha?** Nếu có, dữ liệu có thể là thực thể dùng chung; nhúng bản sao sống sẽ tạo chi phí đồng bộ. Nếu bản sao là snapshot lịch sử cố ý giữ nguyên, đó lại là lý do tốt để nhúng.

**3. Các màn hình đọc con như thế nào?** Nếu 90% lần đọc cha cần luôn một nhóm con nhỏ, nhúng có thể hữu ích. Nếu con chỉ đọc qua API riêng, hoặc luôn phân trang, cần xem xét tham chiếu.

**4. Số lượng con tăng tới đâu trong vài năm?** Phải ước lượng cả kích thước trung bình, trường hợp lớn nhất, tốc độ tăng và giới hạn document. Không chỉ dựa trên dữ liệu thử nghiệm.

**5. Bao nhiêu tác nhân sẽ cùng cập nhật document?** Nếu hàng nghìn yêu cầu cùng sửa một cha, embedding có thể tạo tranh chấp dù từng ghi riêng lẻ được xử lý nguyên tử.

## 16. Tình huống thực hành: hệ thống khóa học

Một nền tảng học tập lưu thông tin khóa học:

~~~text
Course
├── id
├── title
├── description
├── chapters[]             (mỗi khóa thường vài chục chương)
├── author
├── enrollments[]          (có thể hàng trăm nghìn học viên)
├── reviews[]              (số lượng tăng theo thời gian)
└── displayPreferences
~~~

Hệ thống cần:

1. Hiển thị trang chi tiết khóa học gồm tiêu đề, mô tả và danh sách chương.
2. Xem bài học trong từng chương và giữ thứ tự học.
3. Cho học viên ghi tiến độ học độc lập.
4. Tìm kiếm và phân trang đánh giá của khóa học.
5. Cho giảng viên chỉnh sửa khóa học, nhưng không sửa dữ liệu lịch sử học tập của học viên.
6. Lưu thông tin tác giả hiện tại và tên tác giả tại thời điểm phát hành chứng nhận.

### Yêu cầu phân tích

Hãy xác định:

- Những phần nào có vòng đời phụ thuộc `Course` và thường đọc cùng khóa học?
- Những phần nào có số lượng không giới hạn hoặc quyền sở hữu khác?
- Phần nào nên dùng tham chiếu tới thực thể sống?
- Phần nào nên giữ snapshot lịch sử?
- Nếu các chương dài hoặc được chỉnh sửa đồng thời, có nên nhúng toàn bộ nội dung bài học không?

### Phương án tham khảo

| Phần dữ liệu | Cách tiếp cận khả dĩ | Lý do |
|---|---|---|
| `title`, `description`, metadata nhỏ | Nhúng trong Course | Thuộc chính khóa học và thường đọc cùng |
| Danh sách chương có giới hạn, chỉ gồm ID/tiêu đề/thứ tự | Có thể nhúng mục lục | Thường hiển thị cùng trang chi tiết |
| Nội dung bài học dài, sửa độc lập | Cân nhắc document Lesson riêng | Kích thước và nhu cầu cập nhật riêng |
| Hồ sơ tác giả | Tham chiếu bằng `authorId` | Tác giả có vòng đời độc lập |
| Tên tác giả trên chứng nhận đã phát hành | Snapshot trong Certificate | Cần giữ trạng thái lịch sử |
| Danh sách học viên đăng ký | Document Enrollment riêng | Số lượng lớn, phân trang và quyền truy cập riêng |
| Tiến độ theo học viên | Document Progress riêng | Ghi độc lập, tốc độ cập nhật cao |
| Đánh giá | Document Review riêng, có thể giữ vài preview | Tăng không giới hạn, cần sắp xếp/lọc riêng |
| Tùy chọn hiển thị của cá nhân | Thuộc hồ sơ người dùng hoặc cấu hình riêng | Quyền sở hữu là người dùng, không phải khóa học |

Ví dụ một Course chứa mục lục ngắn:

~~~json
{
  "_id": "course-nosql",
  "title": "Nhập môn NoSQL",
  "authorId": "author-5",
  "chapters": [
    { "chapterId": "ch-1", "title": "Tổng quan", "order": 1 },
    { "chapterId": "ch-2", "title": "Mô hình tài liệu", "order": 2 }
  ],
  "chapterCount": 2
}
~~~

Trong khi nội dung bài học lưu riêng:

~~~json
{
  "_id": "lesson-89",
  "courseId": "course-nosql",
  "chapterId": "ch-2",
  "title": "Nhúng dữ liệu có cùng vòng đời hoặc cùng mẫu truy cập",
  "content": "...",
  "order": 5
}
~~~

Đây không phải thiết kế bắt buộc. Nếu số chương cực ít, mỗi bài rất ngắn và luôn được đọc cùng khóa học, nhúng sâu hơn có thể hợp lý. Nếu khóa học có hàng nghìn bài, thay đổi riêng và có nhu cầu phát hành phiên bản, tách Lesson thường dễ quản lý hơn.

## 17. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “NoSQL document nghĩa là phải nhúng mọi thứ.” | Document store vẫn hỗ trợ tham chiếu; mô hình lai thường phù hợp hơn. |
| “Có quan hệ một–nhiều thì cứ dùng mảng nhúng.” | Phải xét mảng có giới hạn không, có thường đọc cùng cha không và mức ghi đồng thời. |
| “Cùng vòng đời là đủ để nhúng.” | Còn phải xét kích thước, truy cập, quyền, retention, tải và transaction. |
| “Nhúng luôn nhanh hơn tham chiếu.” | Đọc nguyên document lớn hoặc ghi nhiều lên cùng cha có thể tốn kém hơn. |
| “Embedding không gây lặp dữ liệu.” | Snapshot nhúng thường là bản sao có chủ đích, cần hiểu nó có được cập nhật hay không. |
| “Cập nhật một document là nguyên tử thì toàn bộ nghiệp vụ đã nhất quán.” | Nhiều document và dịch vụ khác nhau vẫn cần transaction hoặc giao thức phối hợp. |
| “Schema linh hoạt thì không cần validation.” | Vẫn cần kiểm soát trường bắt buộc, kiểu dữ liệu, phiên bản và ràng buộc. |
| “Một mảng mới có vài phần tử nên an toàn mãi mãi.” | Phải xét tăng trưởng về lâu dài và giới hạn kích thước document. |
| “Projection bảo đảm DBMS chỉ đọc các byte trường được chọn.” | Projection giới hạn dữ liệu trả về; chi phí đọc đĩa tùy engine và index. |
| “Đã nhúng snapshot thì nên cập nhật nó khi dữ liệu gốc đổi.” | Snapshot lịch sử thường phải bất biến để giữ ngữ cảnh giao dịch hoặc phát hành. |

## 18. Kết luận

**Nhúng dữ liệu có cùng vòng đời hoặc cùng mẫu truy cập** là một trong những kỹ thuật quan trọng nhất của mô hình document. Nó giúp một tài liệu đại diện cho một thực thể nghiệp vụ tương đối hoàn chỉnh, hỗ trợ đọc các phần liên quan cùng nhau và có thể tận dụng cập nhật nguyên tử trong phạm vi một document khi DBMS cung cấp bảo đảm đó.

Nhưng embedding chỉ hiệu quả khi ranh giới dữ liệu được chọn đúng:

- **Cùng vòng đời:** phần con thuộc riêng cha, thường được tạo/xóa chung và có cùng chính sách quản lý.
- **Cùng mẫu truy cập:** ứng dụng thường cần các phần dữ liệu ấy trong cùng một yêu cầu đọc hoặc ghi.
- **Có giới hạn và ít tranh chấp:** kích thước, số phần tử, nhịp cập nhật và vòng đời thực tế phù hợp với giới hạn document.
- **Bản sao có chủ đích:** dữ liệu lịch sử như tên/giá sản phẩm lúc mua có thể nhúng snapshot, trong khi thực thể sản phẩm gốc vẫn tồn tại riêng.
- **Tách khi cần:** dữ liệu được chia sẻ, tăng không giới hạn, có quyền/retention khác hoặc cập nhật độc lập nên được cân nhắc tham chiếu hay mô hình lai.

Thiết kế document nên bắt đầu từ **các thao tác ứng dụng thực hiện nhiều nhất, bất biến nghiệp vụ cần bảo vệ và cách dữ liệu phát triển theo thời gian**. Khi ba yếu tố đó rõ ràng, việc chọn nhúng hay tham chiếu sẽ có cơ sở thực tế hơn việc chỉ nhìn vào sơ đồ quan hệ giữa các thực thể.
