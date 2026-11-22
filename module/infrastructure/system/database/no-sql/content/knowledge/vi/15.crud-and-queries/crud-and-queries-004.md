# Lọc theo khóa, trường, đường dẫn hoặc mẫu quan hệ trong NoSQL

## 1. Bài toán: “tìm dữ liệu” có nhiều kiểu khác nhau

Trong ứng dụng bán hàng, người dùng có thể yêu cầu:

- “Mở đơn hàng có mã `ORD-1001`.”
- “Liệt kê các đơn đã thanh toán của khách `C007`.”
- “Tìm đơn giao tới Hà Nội.”
- “Tìm đơn có **một dòng hàng** mua sản phẩm `P10` với số lượng ít nhất 2.”
- “Tìm mọi sản phẩm được mua bởi những khách hàng đã đặt đơn trong tháng này.”

Các câu hỏi trên đều là **truy vấn**, nhưng cách xác định bản ghi phù hợp rất khác nhau. Có truy vấn biết trước **khóa định danh**; có truy vấn lọc theo **thuộc tính**; có truy vấn đi vào **object/mảng lồng nhau**; có truy vấn diễn đạt **mẫu quan hệ giữa nhiều thực thể**.

Trong NoSQL, không có một cơ chế query duy nhất cho mọi kiểu cơ sở dữ liệu:

- **Key–value** tối ưu thao tác tìm theo khóa.
- **Document database** cho phép lọc theo trường, đường dẫn con và điều kiện trên mảng.
- **Wide-column** thường yêu cầu truy vấn khớp với partition key và clustering key đã chọn.
- **Graph database** biểu diễn mối quan hệ thành cạnh và cho phép tìm một mẫu đường đi giữa các nút.

Bài học tập trung vào **cách chọn kiểu lọc đúng với câu hỏi và mô hình lưu trữ**, sau đó kiểm tra hiệu quả thực thi thay vì chỉ viết được cú pháp.

## 2. Bốn cách lọc cốt lõi

| Loại lọc | Câu hỏi minh họa | Đơn vị được so khớp | Điểm cần chú ý |
|---|---|---|---|
| **Theo khóa** | Đơn `ORD-1001` là gì? | Khóa định danh hoặc khóa phân vùng | Biết trước ID; thường là đường truy cập trực tiếp |
| **Theo trường** | Đơn nào có `status = PAID`? | Thuộc tính phẳng, khoảng số/ngày, tập giá trị | Có index hay phải quét? |
| **Theo đường dẫn** | Đơn nào có `shipping.city = Hà Nội`? | Thuộc tính lồng nhau hoặc phần tử mảng | Điều kiện trên nhiều phần tử có cùng item không? |
| **Theo mẫu quan hệ** | Khách C007 đã mua sản phẩm nào? | Nút, cạnh, loại cạnh, hướng và đường đi | Mẫu có bao nhiêu hop, fan-out thế nào? |

**Lọc dữ liệu** là xác định phần tử nào khớp điều kiện; **sắp xếp** là quyết định thứ tự trả về; **projection** là chọn những trường cần xuất ra; **phân trang** là giới hạn lượng kết quả mỗi lần. Bốn việc liên quan nhau nhưng không nên dùng lẫn.

Ví dụ:

```text
lọc: tenant = T01 AND status = PAID
    |
    v
sắp xếp: createdAt giảm dần, _id giảm dần
    |
    v
giới hạn: 20 đơn / lần
    |
    v
projection: _id, createdAt, status, totalVnd
```

Đây là một query pattern cụ thể. Muốn tối ưu, cần biết **điểm bắt đầu, tập dữ liệu phải xét và loại index hỗ trợ**.

## 3. Bộ dữ liệu đơn hàng minh họa

Các ví dụ MongoDB sử dụng collection `orders` trong `mongosh`, giả sử chạy trong một **database thử nghiệm trống**. Dữ liệu gồm bốn đơn thuộc hai tenant:

```javascript
db.orders.insertMany([
  {
    _id: "ORD-1001",
    tenantId: "T01",
    customerId: "C007",
    status: "PAID",
    createdAt: ISODate("2026-11-10T08:30:00Z"),
    totalVnd: 520000,
    shipping: {
      recipient: "Mai",
      city: "Hà Nội",
      district: "Cầu Giấy"
    },
    items: [
      { sku: "P10", quantity: 2, unitPriceVnd: 150000 },
      { sku: "P20", quantity: 1, unitPriceVnd: 220000 }
    ],
    labels: ["gift", "priority"]
  },
  {
    _id: "ORD-1002",
    tenantId: "T01",
    customerId: "C007",
    status: "PENDING",
    createdAt: ISODate("2026-11-11T10:00:00Z"),
    totalVnd: 420000,
    shipping: {
      recipient: "Mai",
      city: "Đà Nẵng",
      district: "Hải Châu"
    },
    items: [
      { sku: "P10", quantity: 1, unitPriceVnd: 150000 },
      { sku: "P30", quantity: 3, unitPriceVnd: 90000 }
    ],
    labels: ["standard"]
  },
  {
    _id: "ORD-1003",
    tenantId: "T01",
    customerId: "C008",
    status: "PAID",
    createdAt: ISODate("2026-11-12T09:00:00Z"),
    totalVnd: 660000,
    shipping: {
      recipient: "Bình",
      city: "Hà Nội",
      district: "Ba Đình"
    },
    items: [
      { sku: "P20", quantity: 3, unitPriceVnd: 220000 }
    ],
    labels: ["gift"]
  },
  {
    _id: "ORD-2001",
    tenantId: "T02",
    customerId: "C007",
    status: "PAID",
    createdAt: ISODate("2026-11-13T14:00:00Z"),
    totalVnd: 600000,
    shipping: {
      recipient: "An",
      city: "Hà Nội",
      district: "Đống Đa"
    },
    items: [
      { sku: "P10", quantity: 4, unitPriceVnd: 150000 }
    ],
    labels: ["priority"]
  }
]);
```

Đây là dữ liệu học tập, không bao gồm đầy đủ phí, giảm giá, thuế hoặc vòng đời thanh toán. Cả hai tenant có thể dùng cùng `customerId = "C007"`; do đó **không được hiểu customerId riêng lẻ là duy nhất toàn hệ thống**.

Sơ đồ cấu trúc một document:

```text
Order ORD-1001
├── tenantId: T01
├── customerId: C007
├── status: PAID
├── createdAt: Date
├── shipping: object
│   ├── recipient: Mai
│   ├── city: Hà Nội
│   └── district: Cầu Giấy
├── items: array
│   ├── {sku: P10, quantity: 2, unitPriceVnd: 150000}
│   └── {sku: P20, quantity: 1, unitPriceVnd: 220000}
└── labels: ["gift", "priority"]
```

Với collection này, ta sẽ phân tích lần lượt những câu hỏi được trả lời tốt bằng **khóa, trường và đường dẫn**.

## 4. Lọc theo khóa: biết đúng định danh cần tìm

### 4.1. MongoDB: tìm theo `_id`

```javascript
db.orders.findOne({ _id: "ORD-1001" });
```

Kết quả là document `ORD-1001` nếu nó tồn tại. Trong collection MongoDB thông thường, `_id` có unique index, nên lookup bằng `_id` là một đường truy cập tự nhiên cho màn hình chi tiết.

Nếu nguồn dữ liệu dùng `_id` là chuỗi, truy vấn bằng `ObjectId("...")` không thể tự động khớp một chuỗi có nội dung tương tự. **Kiểu của khóa cũng là một phần của điều kiện so khớp.**

Muốn tìm theo một cặp khóa nghiệp vụ, ví dụ `tenantId + externalOrderNo`:

```javascript
db.orders.findOne({
  tenantId: "T01",
  externalOrderNo: "WEB-1234"
});
```

Truy vấn này chỉ có ý nghĩa nếu collection thực tế có trường `externalOrderNo`. Trong dữ liệu mẫu của mục 3, trường đó chưa tồn tại nên kết quả sẽ là `null`. Nếu đây là khóa nghiệp vụ thực, cần đặt quy tắc duy nhất và index phù hợp:

```javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderNo: 1 },
  {
    unique: true,
    partialFilterExpression: {
      externalOrderNo: { $type: "string" }
    }
  }
);
```

Partial unique index này chỉ áp dụng cho các document có `externalOrderNo` kiểu string; việc dùng hay không phải theo chính sách dữ liệu. Không nên tạo index chỉ vì có thể viết được điều kiện, mà phải biết **truy vấn này có xảy ra trong ứng dụng hay không**.

### 4.2. Redis: truy xuất bằng key

Trong Redis, một thiết kế key–value có thể lưu:

```redis
HSET order:T01:ORD-1001 status PAID customerId C007 totalVnd 520000
HGETALL order:T01:ORD-1001
HGET order:T01:ORD-1001 status
EXISTS order:T01:ORD-1001
```

Redis xử lý rất tốt yêu cầu “tôi biết key `order:T01:ORD-1001`, hãy lấy giá trị”. Nhưng nếu yêu cầu “tìm tất cả hash có `status=PAID`”, Redis core không tự cung cấp một secondary index tổng quát cho mọi field của mọi hash.

Một ứng dụng có thể tự duy trì tập khóa:

```redis
SADD orders:by-status:T01:PAID order:T01:ORD-1001
SMEMBERS orders:by-status:T01:PAID
```

Đây là **index do ứng dụng quản lý**, không phải kết quả tự động của `HSET`. Khi trạng thái đơn đổi, phải cập nhật/remove các member tương ứng và kiểm soát tính nhất quán. Với số lượng member lớn, `SMEMBERS` có thể rất tốn dữ liệu; cân nhắc `SSCAN` hoặc cấu trúc truy cập khác tùy yêu cầu.

### 4.3. DynamoDB: khóa partition và sort key

Một bảng DynamoDB có thể chọn khóa:

```text
PK = "TENANT#T01#CUSTOMER#C007"
SK = "ORDER#2026-11-10T08:30:00Z#ORD-1001"
```

Nếu biết **cả PK lẫn SK**, dùng thao tác tương đương `GetItem`. Nếu biết PK và muốn liệt kê các đơn của khách, dùng `Query` với điều kiện partition key và, khi cần, điều kiện trên sort key.

Ví dụ dạng giả mã:

```text
GetItem(
  PK = "TENANT#T01#CUSTOMER#C007",
  SK = "ORDER#2026-11-10T08:30:00Z#ORD-1001"
)

Query(
  PK = "TENANT#T01#CUSTOMER#C007",
  SK begins_with "ORDER#"
)
```

Nếu chỉ biết `orderId` nhưng không biết PK/SK, thiết kế khóa trên **chưa tối ưu cho lookup theo orderId**. Có thể cần một item ánh xạ orderId → khóa chính, GSI phù hợp hoặc thay đổi access pattern. Không nên mặc định mọi thuộc tính có thể dùng để query hiệu quả như khóa chính.

### 4.4. Khóa logic khác khóa vật lý

Trong thiết kế phân tán, hai bản ghi có thể cùng “mã” trong hai tenant khác nhau. Ví dụ `C007` không đủ xác định khách nếu hệ cho phép trùng customerId giữa tenant:

```text
tenant T01, customer C007 != tenant T02, customer C007
```

Vì vậy lookup phải giữ phạm vi khóa:

```javascript
db.orders.find({
  tenantId: "T01",
  customerId: "C007"
});
```

Tuy cùng viết hai điều kiện, đây không phải một point lookup nếu khách có nhiều đơn. Nó là **truy vấn trả tập đơn** và thường cần index theo cặp trường để đủ nhanh ở dữ liệu lớn.

## 5. Lọc theo trường phẳng: bằng, khoảng, tập giá trị

Document database hỗ trợ nhiều phép so khớp trên field. MongoDB dùng object điều kiện và các toán tử bắt đầu bằng `$`.

### 5.1. Bằng và AND

```javascript
db.orders.find({
  tenantId: "T01",
  status: "PAID"
});
```

Các điều kiện trong cùng object mang nghĩa **AND**: vừa thuộc tenant T01 vừa đã thanh toán. Với dữ liệu mẫu, trả `ORD-1001` và `ORD-1003`; không trả `ORD-2001` dù cũng `PAID` vì thuộc tenant khác.

### 5.2. OR và tập `$in`

```javascript
db.orders.find({
  tenantId: "T01",
  status: { $in: ["PAID", "PENDING"] }
});
```

Lọc đơn thuộc tenant T01 và trạng thái trong một tập. Nếu muốn diễn đạt hai nhánh phức tạp:

```javascript
db.orders.find({
  tenantId: "T01",
  $or: [
    { status: "PAID", totalVnd: { $gte: 500000 } },
    { status: "PENDING", totalVnd: { $lt: 450000 } }
  ]
});
```

`tenantId` áp dụng cho **cả hai nhánh**, còn mỗi nhánh là một nhóm AND riêng. Truy vấn này dự kiến trả `ORD-1001`, `ORD-1002` và `ORD-1003`.

Lưu ý: Khi kết hợp điều kiện tenant với OR, đặt tenant ở phạm vi chung để tránh vô tình có một nhánh không bị giới hạn quyền truy cập.

### 5.3. So sánh khoảng số và ngày

```javascript
db.orders.find({
  tenantId: "T01",
  totalVnd: { $gte: 500000, $lt: 700000 }
});
```

Khoảng `[500000, 700000)` có đầu dưới bao gồm và đầu trên không bao gồm. Tương tự, lọc đơn trong tháng 11 năm 2026:

```javascript
db.orders.find({
  tenantId: "T01",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
});
```

Chọn khoảng **[đầu kỳ, đầu kỳ sau)** giúp tránh phải biết mili giây cuối ngày/tháng. Ví dụ sử dụng UTC; nếu “tháng” theo giờ địa phương, cần chuyển ranh giới từ timezone nghiệp vụ sang instant UTC cho đúng.

### 5.4. Kiểu dữ liệu và ý nghĩa so sánh

`totalVnd: "520000"` là **chuỗi**, khác `totalVnd: 520000` là **số**. Không nên trông chờ phép lọc khoảng tự chuyển chuỗi thành số. Tương tự, ngày ở dạng string thiếu chuẩn hóa có thể phá truy vấn khoảng thời gian. Hãy quy định kiểu dữ liệu và migration khi schema thay đổi.

### 5.5. Null, missing và chuỗi rỗng

MongoDB phân biệt trường không có, trường explicit null và chuỗi rỗng. Trên field scalar:

```javascript
// Null HOẶC field không tồn tại.
db.orders.find({ couponCode: null });

// Chỉ field không tồn tại.
db.orders.find({ couponCode: { $exists: false } });

// Chỉ explicit BSON null.
db.orders.find({ couponCode: { $type: "null" } });

// Chỉ chuỗi rỗng.
db.orders.find({ couponCode: "" });
```

Trong dữ liệu mẫu, cả bốn document đều **thiếu** `couponCode`. Chúng khớp hai truy vấn đầu, nhưng không khớp hai truy vấn cuối. “Trường có tồn tại” không đồng nghĩa “đã có giá trị hữu ích”, và việc gán null không tương đương xóa field.

## 6. Lọc theo đường dẫn: object lồng nhau

Một document có thể chứa object con:

```javascript
{
  _id: "ORD-1001",
  shipping: {
    recipient: "Mai",
    city: "Hà Nội",
    district: "Cầu Giấy"
  }
}
```

Trong MongoDB, **dot notation** truy cập trường con:

```javascript
db.orders.find({
  tenantId: "T01",
  "shipping.city": "Hà Nội"
});
```

Kết quả: `ORD-1001` và `ORD-1003`.

Lọc theo hai điều kiện ở object con:

```javascript
db.orders.find({
  tenantId: "T01",
  "shipping.city": "Hà Nội",
  "shipping.district": "Cầu Giấy"
});
```

Kết quả chỉ còn `ORD-1001`.

### Dot notation khác với so khớp nguyên object

Hai truy vấn sau **không mang cùng nghĩa**:

```javascript
// Chỉ cần trường con city đúng.
db.orders.find({ "shipping.city": "Hà Nội" });

// So khớp giá trị nguyên object shipping theo cấu trúc.
db.orders.find({
  shipping: {
    recipient: "Mai",
    city: "Hà Nội",
    district: "Cầu Giấy"
  }
});
```

Truy vấn đầu có thể khớp object `shipping` có thêm trường mới như `postalCode`. Truy vấn thứ hai so khớp giá trị embedded document theo cấu trúc được cung cấp; việc thiếu/thừa trường hoặc thứ tự trường có thể ảnh hưởng so khớp nguyên object trong MongoDB.

Với nghiệp vụ “giao tới Hà Nội”, truy vấn theo đường dẫn con thường đúng và bền hơn trước tiến hóa schema. Không nên so khớp cả object chỉ để kiểm tra một thuộc tính.

### Đường dẫn lồng sâu và tên trường

Ví dụ:

```javascript
db.orders.find({
  "shipping.geo.regionCode": "NORTH"
});
```

Truy vấn này chỉ có kết quả nếu dữ liệu thực có cấu trúc `shipping.geo.regionCode`. Dot notation là **đường dẫn dữ liệu**, không phải một cơ chế join giữa các collection.

Trong hệ lưu trữ khác, tên đường dẫn có thể được biểu diễn bằng cú pháp JSONPath, biểu thức thuộc tính, hoặc API riêng. Không được tự áp dụng cú pháp MongoDB `"shipping.city"` cho mọi NoSQL.

## 7. Lọc trong mảng: bẫy điều kiện khác phần tử

Document có trường `items` là **mảng object**:

```javascript
items: [
  { sku: "P10", quantity: 1 },
  { sku: "P30", quantity: 3 }
]
```

### 7.1. Tìm mảng chứa giá trị

```javascript
db.orders.find({
  tenantId: "T01",
  "items.sku": "P10"
});
```

Kết quả là `ORD-1001` và `ORD-1002`. Với điều kiện đơn này, chỉ cần **có ít nhất một phần tử** có `sku = P10`.

Mảng scalar cũng có thể được truy vấn theo membership:

```javascript
db.orders.find({
  tenantId: "T01",
  labels: "gift"
});
```

Điều kiện trên khớp đơn có mảng `labels` chứa `"gift"`; với dữ liệu mẫu là `ORD-1001` và `ORD-1003`.

### 7.2. Hai điều kiện trên mảng có thể khớp hai item khác nhau

Xét truy vấn:

```javascript
db.orders.find({
  tenantId: "T01",
  "items.sku": "P10",
  "items.quantity": { $gte: 2 }
});
```

Nó có thể trả **cả `ORD-1001` và `ORD-1002`**:

- `ORD-1001` có item P10 số lượng 2.
- `ORD-1002` có item P10 số lượng 1 **và một item P30 số lượng 3**.

Khi các điều kiện đặt riêng trên `items.sku` và `items.quantity`, MongoDB không nhất thiết buộc chúng khớp **cùng một phần tử** của mảng. Đây là một lỗi query có thể làm sai màn hình lọc, thống kê hoặc quy tắc giảm giá.

### 7.3. Dùng `$elemMatch` để ràng buộc cùng phần tử

Nếu câu hỏi thực sự là “đơn chứa một dòng hàng P10 có số lượng ít nhất 2”, viết:

```javascript
db.orders.find({
  tenantId: "T01",
  items: {
    $elemMatch: {
      sku: "P10",
      quantity: { $gte: 2 }
    }
  }
});
```

Kết quả **chỉ có `ORD-1001`**. `$elemMatch` buộc điều kiện `sku` và `quantity` áp lên **cùng một element**.

### Khi mảng có nhiều tầng

Với các cấu trúc như `orders[].items[]` hoặc một document có nhiều cấp array, cần biết chính xác điều kiện nào phải cùng thuộc một object ở tầng nào. Có thể phải sử dụng `$elemMatch` ở đúng cấp mảng hoặc thay đổi mô hình lưu trữ nếu truy vấn trở nên khó kiểm soát.

**Quy tắc đọc truy vấn:** hỏi “các điều kiện này chỉ cần đúng ở đâu đó trong document, hay phải cùng đúng trên một item cụ thể?”. Câu trả lời quyết định dùng dot notation thông thường hay `$elemMatch`.

## 8. Lọc theo đường dẫn và tối ưu index

MongoDB có thể tạo index trên nested field:

```javascript
db.orders.createIndex({
  tenantId: 1,
  "shipping.city": 1
});
```

Index này có thể hỗ trợ mẫu truy vấn:

```javascript
db.orders.find({
  tenantId: "T01",
  "shipping.city": "Hà Nội"
});
```

Đối với mảng, có thể tạo index trên đường dẫn:

```javascript
db.orders.createIndex({
  tenantId: 1,
  "items.sku": 1
});
```

Vì `items` là mảng, index liên quan có thể trở thành **multikey index**. Nó phục vụ tìm document có SKU tương ứng, **không biến mỗi dòng hàng thành một kết quả document riêng**.

### Không phải mọi compound index có mảng đều hợp lệ

Một số tổ hợp nhiều trường mảng trong cùng compound index bị giới hạn bởi quy tắc multikey. Ngoài ra, có index không bảo đảm mọi truy vấn nhiều điều kiện trong mảng sẽ tự động được tối ưu hiệu quả. Với yêu cầu điều kiện phải cùng một phần tử, `$elemMatch` vừa là lựa chọn **đúng ngữ nghĩa**, vừa có thể ảnh hưởng cách optimizer xử lý các ràng buộc index.

**Index được chọn theo mẫu truy vấn và dữ liệu thực**, không chỉ theo việc trường có tồn tại.

## 9. Sắp xếp, projection và phân trang sau khi lọc

Giả sử màn hình yêu cầu “20 đơn mới nhất của khách C007 thuộc tenant T01”:

```javascript
db.orders
  .find(
    { tenantId: "T01", customerId: "C007" },
    {
      _id: 1,
      status: 1,
      createdAt: 1,
      totalVnd: 1
    }
  )
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

- `find()` xác định **tập document cần xét** và projection.
- `sort()` sắp theo ngày mới nhất trước, dùng `_id` làm khóa phụ để thứ tự xác định nếu trùng ngày.
- `limit(20)` giới hạn số document trả về.
- Projection giảm số trường truyền về, nhưng **không bảo đảm** truy vấn không cần đọc document gốc; điều này phụ thuộc execution plan và index.

### Index phù hợp với lọc và sort

```javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  createdAt: -1,
  _id: -1
});
```

Index này được thiết kế cho mẫu lọc chính xác theo `tenantId` + `customerId`, sau đó sắp xếp theo `createdAt` và `_id` giảm dần.

Nếu một màn hình khác liên tục lọc thêm `status = PAID`, có thể cần xem index khác:

```javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
```

Không nên tạo tràn lan nhiều index giống nhau: mỗi index tốn đĩa, RAM và chi phí duy trì trong quá trình ghi.

### Keyset pagination thay vì bỏ qua hàng loạt

`skip(100000)` có thể làm truy vấn phải đi qua nhiều kết quả trước đó. Với sort `createdAt DESC, _id DESC`, có thể dùng cursor của phần tử cuối:

```javascript
const cursorTime = ISODate("2026-11-11T10:00:00Z");
const cursorId = "ORD-1002";

db.orders
  .find({
    tenantId: "T01",
    customerId: "C007",
    $or: [
      { createdAt: { $lt: cursorTime } },
      { createdAt: cursorTime, _id: { $lt: cursorId } }
    ]
  })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

Điều kiện cursor phải giữ **đúng thứ tự sort**. Ví dụ giả định `_id` là chuỗi, so sánh cùng kiểu. Nếu document mới được thêm hoặc ngày tạo bị sửa giữa các trang, keyset pagination giúp tránh nhiều vấn đề của offset nhưng **không tự tạo snapshot bất biến**. Cần chiến lược riêng nếu người dùng cần kết quả nhất quán tại một mốc thời gian.

## 10. Kiểm chứng kế hoạch truy vấn thay vì đoán

Trong MongoDB, dùng `explain("executionStats")`:

```javascript
db.orders
  .find({
    tenantId: "T01",
    customerId: "C007",
    status: "PAID"
  })
  .sort({ createdAt: -1, _id: -1 })
  .explain("executionStats");
```

Những thông tin thường cần xem:

- `nReturned`: số document kết quả.
- `totalKeysExamined`: số mục index được xem xét.
- `totalDocsExamined`: số document được đọc để đánh giá.
- Các stage như `IXSCAN` hoặc `COLLSCAN`: hướng truy cập dữ liệu.
- Những bước sort, fetch, filter còn phải thực hiện ngoài index.

Với **chỉ bốn document mẫu**, collection scan có thể là một lựa chọn hợp lý. Không nên xem việc MongoDB chọn `COLLSCAN` cho bộ dữ liệu nhỏ là bằng chứng rằng index sai. Phải đánh giá trên dữ liệu đại diện và tải ứng dụng thực tế.

Một chỉ số trực giác:

\[
\text{Selectivity} =
\frac{\text{số bản ghi khớp điều kiện}}
{\text{số bản ghi trong phạm vi xét}}
\]

Nếu điều kiện chỉ giữ 1% dữ liệu, index có thể giúp thu hẹp tập ứng viên đáng kể; nếu giữ 90% dữ liệu, index không nhất thiết tốt hơn quét tuần tự. Kết luận vẫn phụ thuộc kích thước record, thứ tự sort, phân bố giá trị và execution plan cụ thể.

### Đọc và lọc không phải luôn diễn ra ở cùng nơi

Trong một số API, bộ lọc được dùng để **giới hạn dữ liệu trước khi đọc** bằng index; trong API khác, nó được áp dụng **sau khi một lượng dữ liệu đã được đọc**. Cùng một biểu thức “`status = PAID`” có thể có chi phí rất khác nhau giữa MongoDB, DynamoDB và Cassandra.

## 11. Wide-column: truy vấn cần đi theo partition key

Trong Cassandra, query pattern cần được xem xét từ lúc thiết kế bảng. Giả sử cần đọc danh sách đơn theo khách và thời gian:

```sql
CREATE TABLE orders_by_customer (
    tenant_id text,
    customer_id text,
    created_at timestamp,
    order_id text,
    status text,
    total_vnd bigint,
    PRIMARY KEY ((tenant_id, customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Khóa được chia thành:

```text
Partition key: (tenant_id, customer_id)
Clustering keys: created_at, order_id
```

Truy vấn tự nhiên cho thiết kế này:

```sql
SELECT order_id, status, created_at, total_vnd
FROM orders_by_customer
WHERE tenant_id = 'T01'
  AND customer_id = 'C007'
  AND created_at >= '2026-11-01T00:00:00Z'
  AND created_at < '2026-12-01T00:00:00Z'
LIMIT 20;
```

Vì biết partition key, Cassandra có thể xác định phạm vi partition cần đọc. Clustering key hỗ trợ thứ tự và điều kiện theo cấu trúc khóa đã chọn. Mẫu truy vấn hợp lệ chính xác vẫn phụ thuộc phiên bản Cassandra và giới hạn CQL trên các clustering column.

### Nếu chỉ biết status?

```sql
-- Không phải mẫu truy vấn tốt cho bảng có partition key theo khách:
SELECT *
FROM orders_by_customer
WHERE status = 'PAID';
```

`status` là non-key column trong bảng này. CQL không mặc định cho phép truy vấn hiệu quả trên một field bất kỳ khi không biết partition key. Cố dùng `ALLOW FILTERING` trên truy vấn rộng có thể yêu cầu đọc rất nhiều dữ liệu và làm tải khó dự đoán; nó không phải giải pháp thiết kế index chung cho mọi access pattern.

Nếu nghiệp vụ liên tục cần “đơn PAID theo tenant và tháng”, có thể cần một bảng **theo truy vấn**, ví dụ:

```sql
CREATE TABLE orders_by_status_month (
    tenant_id text,
    status text,
    month_bucket text,
    created_at timestamp,
    order_id text,
    customer_id text,
    total_vnd bigint,
    PRIMARY KEY ((tenant_id, status, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Đây là **một bản biểu diễn khác** của dữ liệu đơn hàng. Ứng dụng cần duy trì nó khi status đổi, khi đơn bị hủy hoặc khi dữ liệu được sửa. Kích thước partition theo tháng có thể vẫn quá lớn ở tenant lớn; bucket theo thời gian hoặc cách chia tải phải dựa trên khối lượng thật.

**Bài học wide-column:** lọc theo khóa phân vùng là đường truy vấn chủ đạo; trường không nằm trong khóa thường đòi bảng truy cập khác, index có khả năng tương ứng hoặc thay đổi thiết kế dữ liệu.

## 12. DynamoDB: `KeyConditionExpression` khác `FilterExpression`

DynamoDB cũng đặt trọng tâm vào khóa:

```text
PK = TENANT#T01#CUSTOMER#C007
SK = ORDER#2026-11-10T08:30:00Z#ORD-1001
```

Một lệnh Query có thể diễn đạt:

```javascript
// Pseudocode tham khảo cấu trúc Query API;
// không phụ thuộc vào một SDK phiên bản cụ thể.
{
  TableName: "Orders",
  KeyConditionExpression:
    "PK = :pk AND begins_with(SK, :prefix)",
  ExpressionAttributeValues: {
    ":pk": "TENANT#T01#CUSTOMER#C007",
    ":prefix": "ORDER#"
  }
}
```

Phần `KeyConditionExpression` quyết định nhóm item có thể được tìm theo cấu trúc khóa của table hoặc index.

### Thêm filter trên non-key attribute

```javascript
{
  TableName: "Orders",
  KeyConditionExpression:
    "PK = :pk AND begins_with(SK, :prefix)",
  FilterExpression: "#st = :paid",
  ExpressionAttributeNames: {
    "#st": "status"
  },
  ExpressionAttributeValues: {
    ":pk": "TENANT#T01#CUSTOMER#C007",
    ":prefix": "ORDER#",
    ":paid": "PAID"
  }
}
```

`FilterExpression` lọc kết quả từ tập item đã được truy xuất theo key. Nó **không tương đương** một secondary index tự động và **không làm giảm lượng đọc được tính phí chỉ vì nhiều item bị loại**. Trong DynamoDB, `Query` xử lý một trang kết quả theo giới hạn dung lượng, áp filter lên những item đã được đọc, rồi trả trang; vì vậy một trang có thể có rất ít hoặc thậm chí không có item trả về mặc dù vẫn còn các trang tiếp theo.

Khi phân trang, theo dõi `LastEvaluatedKey` và tiếp tục đến khi không còn. Không kết luận “hết dữ liệu phù hợp” chỉ vì một trang trả mảng `Items` rỗng nếu còn continuation token.

### Global Secondary Index khi cần đường truy cập khác

Nếu yêu cầu thường xuyên tìm “đơn theo status của tenant”, cần cân nhắc **GSI** với key phù hợp, ví dụ `GSI1PK = TENANT#T01#STATUS#PAID` và sort key gồm thời gian + order ID.

GSI phải được duy trì khi dữ liệu nguồn đổi và có đặc điểm nhất quán/capacity riêng; truy vấn GSI thường cung cấp **eventual consistency**, không phải đọc strongly consistent như một số thao tác trên base table. Một GSI theo status có thể gặp hot partition nếu dồn quá nhiều ghi vào cùng một partition key; time bucket hoặc cách chia partition phải được đánh giá.

**Bài học DynamoDB:** key condition giới hạn đường truy cập; filter expression không thay thế thiết kế primary key/GSI theo access pattern.

## 13. Đồ thị: lọc theo mẫu quan hệ, không chỉ theo field

Với graph database, câu hỏi có thể là:

> “Khách C007 thuộc T01 đã đặt những đơn PAID nào có dòng hàng P10 số lượng ít nhất 2?”

Ta có thể biểu diễn:

```text
(Customer C007/T01)
        |
        | PLACED
        v
   (Order ORD-1001)
        |
        | HAS_LINE
        v
   (OrderLine L1001-A) --OF_PRODUCT--> (Product P10)
     quantity = 2
```

Ở đây:

- `Customer`, `Order`, `OrderLine`, `Product` là loại nút.
- `PLACED`, `HAS_LINE`, `OF_PRODUCT` là loại quan hệ có hướng.
- `tenantId`, `customerId`, `orderId`, `sku`, `quantity`, `status` là thuộc tính.
- `OrderLine` là nút riêng vì mỗi dòng hàng có định danh và số lượng độc lập. Một mô hình khác có thể đặt `quantity` trên cạnh `CONTAINS`; cần nhất quán với mô hình đã chọn.

### 13.1. Dữ liệu minh họa bằng Cypher

Giả sử có Neo4j trong database thử nghiệm và chạy một lần những lệnh sau:

```cypher
CREATE (c:Customer {
  tenantId: 'T01',
  customerId: 'C007',
  name: 'Mai'
});

CREATE (o:Order {
  tenantId: 'T01',
  orderId: 'ORD-1001',
  status: 'PAID',
  totalVnd: 520000
});

CREATE (p:Product {
  tenantId: 'T01',
  sku: 'P10',
  name: 'Sản phẩm P10'
});

CREATE (line:OrderLine {
  tenantId: 'T01',
  lineId: 'L1001-A',
  quantity: 2,
  unitPriceVnd: 150000
});

MATCH (c:Customer {tenantId: 'T01', customerId: 'C007'})
MATCH (o:Order {tenantId: 'T01', orderId: 'ORD-1001'})
MATCH (p:Product {tenantId: 'T01', sku: 'P10'})
MATCH (line:OrderLine {tenantId: 'T01', lineId: 'L1001-A'})
CREATE (c)-[:PLACED]->(o);

MATCH (o:Order {tenantId: 'T01', orderId: 'ORD-1001'})
MATCH (line:OrderLine {tenantId: 'T01', lineId: 'L1001-A'})
CREATE (o)-[:HAS_LINE]->(line);

MATCH (line:OrderLine {tenantId: 'T01', lineId: 'L1001-A'})
MATCH (p:Product {tenantId: 'T01', sku: 'P10'})
CREATE (line)-[:OF_PRODUCT]->(p);
```

Đây là cách tạo dữ liệu nhỏ để minh họa cú pháp, **không phải quy trình ghi idempotent cho production**. Chạy lại `CREATE` có thể tạo thêm nút/cạnh trùng logic nếu không có ràng buộc và quy tắc ghi tương ứng.

### 13.2. MATCH một mẫu đường đi cố định

```cypher
MATCH (c:Customer {tenantId: 'T01', customerId: 'C007'})
      -[:PLACED]->(o:Order)
      -[:HAS_LINE]->(line:OrderLine)
      -[:OF_PRODUCT]->(p:Product)
WHERE o.tenantId = 'T01'
  AND line.tenantId = 'T01'
  AND p.tenantId = 'T01'
  AND o.status = 'PAID'
  AND p.sku = 'P10'
  AND line.quantity >= 2
RETURN DISTINCT o.orderId, o.status, p.sku, line.quantity;
```

Truy vấn mô tả một **mẫu quan hệ gồm ba cạnh**:

1. Bắt đầu từ khách C007 của tenant T01.
2. Đi theo `PLACED` đến đơn.
3. Đi theo `HAS_LINE` đến dòng hàng.
4. Đi theo `OF_PRODUCT` đến sản phẩm P10.
5. Lọc thêm trạng thái đơn và số lượng ở node tương ứng.

Với dữ liệu graph vừa tạo, trả `ORD-1001`. `DISTINCT` giúp tránh lặp những dòng kết quả trùng giá trị khi một mẫu quan hệ có thể khớp nhiều đường khác nhau; nhưng cũng có chi phí và không nên dùng để che lỗi thiết kế dữ liệu trùng không được phép.

### 13.3. Hướng cạnh và vai trò của nhãn

Mẫu:

```cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN c, o;
```

chỉ khớp cạnh có loại `PLACED` từ Customer đến Order. Có thể duyệt ngược cạnh đã lưu:

```cypher
MATCH (o:Order {orderId: 'ORD-1001'})<-[:PLACED]-(c:Customer)
RETURN c.customerId;
```

Viết ngược **mũi tên trong mẫu truy vấn** không có nghĩa graph tự chứa thêm một cạnh đối xứng. Với quan hệ mang nghĩa một chiều như `FOLLOWS`, `PAYMENT_FOR` hay `DEPENDS_ON`, hướng cạnh là một phần quan trọng của câu hỏi.

### 13.4. Truy vấn quan hệ không phải join miễn phí

Mẫu graph giúp biểu diễn ngữ nghĩa liên kết rõ ràng, nhưng độ trễ vẫn phụ thuộc:

- Số node đầu tiên khớp điều kiện.
- Số cạnh mỗi node (**degree/fan-out**).
- Độ dài đường đi và điều kiện thu hẹp.
- Index trên label/property dùng tìm node bắt đầu.
- Số kết quả trung gian và việc loại trùng.

Một node có hàng triệu cạnh đi ra có thể khiến truy vấn một hop đã tốn nhiều tài nguyên. Graph query không phải bảo đảm “duyệt bao nhiêu quan hệ cũng nhanh”.

## 14. Mẫu quan hệ biến độ dài: giới hạn hop để tránh nở kết quả

Ngoài đường đi cố định, một ứng dụng quản lý hạ tầng có thể hỏi:

> “Dịch vụ API phụ thuộc trực tiếp hoặc gián tiếp vào những dịch vụ nào, trong tối đa ba bước?”

Sơ đồ:

```text
(Service API) -[:DEPENDS_ON]-> (Service AUTH)
      |                            |
      |                            +--[:DEPENDS_ON]-> (Service DB)
      |
      +--[:DEPENDS_ON]-> (Service CACHE)
```

Ví dụ Cypher với cú pháp đường đi biến độ dài phổ biến:

```cypher
MATCH p = (start:Service {serviceId: 'API'})
          -[:DEPENDS_ON*1..3]->(target:Service)
RETURN target.serviceId, length(p) AS hops
ORDER BY hops, target.serviceId
LIMIT 100;
```

`*1..3` nghĩa là đi qua từ một đến ba relationship phù hợp. Cú pháp biến độ dài và cách khai báo path trong các phiên bản Neo4j/Cypher mới có thể cung cấp lựa chọn khác; khi triển khai nên đối chiếu phiên bản sử dụng.

**Quan trọng:** giới hạn `LIMIT 100` ở đầu ra không tự bảo đảm công việc mở rộng đường đi trước đó luôn nhỏ. Với graph có nhiều nhánh và chu trình, truy vấn cần ràng buộc loại cạnh, độ sâu, node đầu, điều kiện node/relationship và có thể chính sách không lặp node/path theo nhu cầu.

Nếu cần kết quả “mỗi dịch vụ đích một lần”, có thể thiết kế `DISTINCT` hoặc tính khoảng cách tối thiểu theo đúng ngữ nghĩa. Cùng đích có thể được tìm thấy qua nhiều đường đi và có số hop khác nhau; trả về “100 path” khác với “100 service”.

## 15. Nhãn/loại cạnh và index trong graph

Trong Neo4j, có thể tạo ràng buộc/lookup index cho business key. Với hệ multi-tenant, ví dụ:

```cypher
CREATE CONSTRAINT customer_tenant_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;

CREATE CONSTRAINT order_tenant_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
```

Ràng buộc unique giúp bảo vệ không có hai node cùng nhãn có cùng **cặp giá trị đã khai báo**, khi các thuộc tính được cung cấp đúng. Nó không tự chứng minh mọi node đều bắt buộc có hai field; yêu cầu tồn tại cần được kiểm soát riêng hoặc dùng tính năng constraint tương ứng khi được hỗ trợ.

Truy vấn khởi đầu bằng:

```cypher
MATCH (c:Customer {tenantId: 'T01', customerId: 'C007'})
RETURN c;
```

có thể được hỗ trợ hiệu quả bởi unique constraint/index thích hợp. Sau khi tìm node đầu, các bước truy vấn còn phải **duyệt cạnh**. Index tìm Customer không có nghĩa số lượng cạnh `PLACED` sẽ nhỏ.

Đối với truy vấn bắt đầu từ Product SKU, cũng cần cách tìm chính xác Product theo ID nghiệp vụ. Không nên dùng `name` hay label như một ID nếu chúng có thể trùng hoặc thay đổi.

## 16. Cùng một câu hỏi, các mô hình NoSQL triển khai khác nhau

Xét yêu cầu:

> “Lấy các đơn PAID của khách C007 thuộc tenant T01 trong tháng 11, mới nhất trước.”

| Mô hình | Cách truy cập gợi ý | Đánh đổi |
|---|---|---|
| Key–value | Có danh sách ID theo khách/trạng thái hoặc một key chứa view | Phải quản lý index/view bổ sung |
| Document | `find` theo `tenantId`, `customerId`, `status`, khoảng ngày | Compound index theo filter + sort |
| DynamoDB | Query theo PK của khách và SK theo ngày; filter status hoặc GSI | FilterExpression không thay index |
| Cassandra | Bảng `orders_by_customer` theo partition khách + clustering thời gian | Có thể cần bảng riêng theo status để đọc hiệu quả |
| Graph | Bắt đầu từ Customer rồi theo `PLACED` tới Order, lọc status/date | Dễ duyệt quan hệ; chú ý fan-out và index node đầu |

**Đừng cố tái tạo nguyên một query SQL bất kỳ trên mọi NoSQL store.** Hãy xác định dữ liệu nào được truy cập thường xuyên, qua khóa/đường dẫn/quan hệ nào, rồi lựa chọn model hoặc bản đọc phù hợp.

### Một dạng denormalization theo truy vấn

Nếu lưu đơn theo khách để đọc lịch sử và đồng thời lưu đơn theo trạng thái để phục vụ dashboard, cùng một đơn xuất hiện ở nhiều bản biểu diễn:

```text
orders_by_customer[tenant,customer,time] ---> danh sách của khách
orders_by_status[tenant,status,month,time] -> danh sách theo trạng thái
```

Khi đơn chuyển từ `PENDING` sang `PAID`, bản theo status phải được cập nhật đúng. Đây là chi phí nhất quán của thiết kế theo truy vấn. Có thể dùng event/outbox/CDC, idempotency, version và reconciliation, tùy kiến trúc; không nên giả định đồng bộ tự xảy ra.

## 17. Truy vấn kết hợp nhiều điều kiện: đúng logic trước khi tối ưu

Một query phức tạp thường có:

```text
(tenantId = T01)
  AND
(status IN {PAID, PENDING})
  AND
(createdAt >= start AND createdAt < end)
  AND
(exists item with sku=P10 AND quantity>=2)
```

Biểu diễn MongoDB:

```javascript
db.orders.find({
  tenantId: "T01",
  status: { $in: ["PAID", "PENDING"] },
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  },
  items: {
    $elemMatch: {
      sku: "P10",
      quantity: { $gte: 2 }
    }
  }
});
```

Kết quả mẫu chỉ là `ORD-1001`. Mỗi nhóm điều kiện có mục đích rõ:

- `tenantId` giới hạn phạm vi dữ liệu.
- `status` thuộc tập trạng thái hợp lệ với màn hình.
- `createdAt` giới hạn khoảng thời gian.
- `$elemMatch` bảo đảm SKU và quantity thuộc **một dòng hàng**.

Một cách thiết kế không tốt là bỏ tenant ở một nhánh, dùng hai điều kiện mảng rời rồi chỉ sửa kết quả ở client. **Điều kiện đúng ngữ nghĩa phải được xác định trước khi nghĩ tới index và hiệu năng.**

## 18. Phân quyền multi-tenant: bộ lọc không chỉ phục vụ tiện ích

Trong hệ multi-tenant, `tenantId` thường là ranh giới **an toàn dữ liệu**, không chỉ một lựa chọn UI.

Sai:

```javascript
// Nguy hiểm nếu người dùng có thể tự gửi tenantId tùy ý.
db.orders.find({
  tenantId: request.body.tenantId,
  status: request.body.status
});
```

Một luồng tốt hơn:

```javascript
const tenantId = authenticatedPrincipal.tenantId;
const allowedStatus = ["PAID", "PENDING", "CANCELLED"];

if (!allowedStatus.includes(requestedStatus)) {
  throw new Error("Invalid status");
}

const query = {
  tenantId: tenantId,
  status: requestedStatus
};

db.orders.find(query);
```

Đây là ví dụ về ý tưởng; ứng dụng thật cần xác thực người dùng, kiểm tra quyền từng action và có thể cả quyền theo từng order. **Không lấy tenantId của client làm nguồn có thẩm quyền**.

### Kiểm soát truy vấn động

Không nên ghép chuỗi hoặc object query tùy ý từ input:

- Với MongoDB, tránh cho client tự gửi operator như `$where` hoặc biểu thức không nằm trong allowlist.
- Với Cypher, dùng **parameterized query** thay vì nối chuỗi trực tiếp từ input; các phần như tên label/relationship type động thường cần allowlist hoặc cách xây dựng query an toàn.
- Với Redis, tránh cho người dùng quyết định tiền tố key chứa tenant không được phép.
- Với DynamoDB/Cassandra, giới hạn các query pattern mà API có quyền sử dụng; đừng mở một “generic query endpoint” cho phép scan rộng mọi dữ liệu.

Một query filter được viết đúng cú pháp vẫn có thể **lộ dữ liệu hoặc gây tải** nếu người dùng không được phép sử dụng nó.

## 19. Những trường hợp cần lưu ý về tính nhất quán của kết quả

### 19.1. Dữ liệu vừa cập nhật có thể chưa hiện ở index phụ

Một số hệ NoSQL phân phối/đồng bộ secondary index hoặc read model theo cơ chế bất đồng bộ. Ví dụ GSI trong DynamoDB có đặc điểm eventual consistency; một search index được cập nhật từ event cũng có thể chậm so với nguồn.

Nếu ứng dụng cần **read-your-writes**, có thể trả kết quả mới từ nguồn sau commit hoặc dùng version barrier/fallback phù hợp. Không nên đánh đồng “truy vấn index không thấy” với “ghi thất bại”.

### 19.2. Truy vấn nhiều bước không tạo transaction xuyên hệ

Ví dụ:

```text
1. Query order IDs từ index
2. Fetch chi tiết từng order từ database nguồn
3. Fetch giá và tồn kho hiện tại từ service khác
```

Giữa bước 1 và 3, dữ liệu có thể thay đổi. Nếu dùng kết quả để xác nhận thanh toán hoặc đặt hàng, cần thực hiện kiểm tra điều kiện tại thời điểm commit ở nguồn nghiệp vụ, thay vì dựa hoàn toàn vào một ảnh hiển thị ban đầu.

### 19.3. Null, missing và stale cache

Truy vấn không trả document có thể do không có ID, filter không khớp, tenant khác, projection chưa bắt kịp, hoặc dữ liệu đã hết hạn theo logic. API cần phân biệt phản hồi nghiệp vụ phù hợp, nhưng không tiết lộ thông tin bị cấm như “ID tồn tại ở tenant khác”.

## 20. Quy trình thiết kế truy vấn theo access pattern

Một quy trình thường đủ thực dụng:

1. **Viết câu hỏi nghiệp vụ** bằng ngôn ngữ người dùng: tra đơn theo ID, danh sách đơn theo khách, sản phẩm cùng danh mục, đường đi phụ thuộc giữa service.
2. **Xác định đầu vào và phạm vi:** tenant, user/role, khóa nào đã biết, bộ lọc nào bắt buộc.
3. **Xác định kết quả:** một record, danh sách, đường đi, aggregate; có sort và phân trang không?
4. **Phân loại loại lọc:** key lookup, field/range, nested path/array hay graph pattern.
5. **Chọn ranh giới dữ liệu:** cần đọc một document, một partition, một danh sách ID hay duyệt nhiều edge?
6. **Xây cấu trúc/index theo mẫu đọc:** compound index, partition+clustering key, GSI, tập key do ứng dụng quản lý, graph node constraints.
7. **Kiểm tra ngữ nghĩa:** AND/OR, cùng phần tử `$elemMatch`, hướng cạnh, null/missing, thời điểm đọc.
8. **Kiểm tra an toàn:** tenant và quyền do server thực thi; chống query injection, limit, timeout.
9. **Đo bằng dữ liệu đại diện:** query plan, số record/index entry xét, fan-out, latency p95/p99 và chi phí ghi index.
10. **Định nghĩa cách cập nhật bản đọc:** nếu denormalize, phải có cơ chế đồng bộ, replay và đối soát.

### Phiếu thiết kế một truy vấn

```text
Tên query: OrdersForCustomer
Đầu vào: tenantId (từ auth), customerId, cursor, limit
Kết quả: orderId, createdAt, status, totalVnd
Điều kiện: tenantId = ?, customerId = ?
Sắp xếp: createdAt DESC, orderId DESC
Tần suất: cao, màn hình lịch sử đơn
Độ trễ mục tiêu: theo SLA ứng dụng
Mô hình: document / wide-column / DynamoDB access pattern
Index/partition: (tenantId, customerId, createdAt DESC, orderId DESC)
Phân trang: keyset hoặc continuation token phù hợp
Giới hạn quyền: không cho client tự đổi tenant
Nhất quán: định nghĩa rõ có chấp nhận index lag không
```

Việc viết phiếu này trước khi triển khai giúp tránh kiểu “database đã có nên tìm cách lọc bất kỳ trường nào”, vốn có thể tạo scan tốn kém hoặc kết quả không đúng nghiệp vụ.

## 21. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ biết `status` nhưng dùng bảng partition theo customer để quét toàn cục | Truy vấn chậm/không được hỗ trợ | Thiết kế bảng/index theo access pattern |
| Dùng DynamoDB `FilterExpression` thay GSI | Vẫn đọc nhiều item trước khi lọc | Chọn key condition/GSI đúng mẫu |
| Dùng `KEYS *` hoặc quét mọi Redis key để lọc field | Tốn tải và gây khó kiểm soát | Lookup theo key hoặc index nghiệp vụ |
| Lọc hai điều kiện trên mảng object bằng hai dot path độc lập | Hai điều kiện có thể khớp hai item khác nhau | `$elemMatch` khi cần cùng phần tử |
| So khớp nguyên embedded object chỉ để lọc city | Bị ảnh hưởng bởi trường mới và thứ tự/cấu trúc | Dot notation theo field con |
| Dùng một index cho mọi filter và sort | Hiệu năng khác kỳ vọng | Thiết kế theo điều kiện equality/range/sort thật |
| Dùng `skip` rất sâu | Đọc qua lượng lớn kết quả | Keyset/continuation pagination |
| Không có điều kiện tenant trong một nhánh `$or` | Có thể lộ bản ghi ngoài phạm vi | Đặt điều kiện tenant ở phạm vi chung |
| Dùng tên hiển thị làm định danh nút graph | Trùng tên, đổi tên gây truy vấn sai | Business ID ổn định và unique constraint |
| Duyệt graph nhiều hop không giới hạn | Bùng nổ kết quả trung gian | Hạn chế hop/type/start node/fan-out |
| Cho input client quyết định query operator/label | Query injection hoặc truy vấn quá rộng | Parameter, allowlist và authorization |
| Xem kết quả đọc ngay từ GSI/search là nguồn giao dịch cuối cùng | Gặp stale data và race | Kiểm tra nguồn có thẩm quyền ở commit |
| Quá tin kết quả `explain` trên vài record | Kết luận hiệu năng không đại diện | Đo với dữ liệu và tải thực tế |

## 22. Bài tập thực hành

### Bài 1 — Lọc theo khóa và trường

Với dữ liệu mẫu ở mục 3, viết:

1. MongoDB lookup `ORD-1003` bằng `_id`.
2. Truy vấn các đơn `PAID` thuộc tenant T01.
3. Truy vấn đơn của `C007` thuộc T01, sắp ngày tạo mới nhất trước.

**Gợi ý:**

```javascript
db.orders.findOne({ _id: "ORD-1003" });

db.orders.find({ tenantId: "T01", status: "PAID" });

db.orders.find({
  tenantId: "T01",
  customerId: "C007"
}).sort({ createdAt: -1, _id: -1 });
```

### Bài 2 — Điều kiện trên object con

Tìm đơn tenant T01 giao tới Hà Nội, thuộc quận Cầu Giấy. Hãy viết điều kiện theo dot notation và cho biết tại sao so khớp nguyên object `shipping` có thể không phù hợp khi thêm field `postalCode`.

### Bài 3 — `$elemMatch` và kết quả sai tiềm ẩn

So sánh:

```javascript
// Cách A
db.orders.find({
  tenantId: "T01",
  "items.sku": "P10",
  "items.quantity": { $gte: 2 }
});

// Cách B
db.orders.find({
  tenantId: "T01",
  items: { $elemMatch: { sku: "P10", quantity: { $gte: 2 } } }
});
```

Hãy giải thích vì sao cách A có thể trả `ORD-1002` nhưng cách B không trả. Cách nào đúng với yêu cầu “một dòng hàng P10 số lượng ít nhất 2”?

### Bài 4 — Thiết kế index

Trang lịch sử đơn liên tục dùng:

```javascript
db.orders.find({
  tenantId: "T01",
  customerId: "C007",
  status: "PAID"
}).sort({ createdAt: -1, _id: -1 }).limit(20);
```

Hãy đề xuất compound index và dùng `explain("executionStats")` để xem kế hoạch. Tại sao chỉ bốn document demo chưa đủ chứng minh lợi ích?

### Bài 5 — DynamoDB FilterExpression

Một partition có 10.000 đơn, trong đó chỉ 100 đơn PAID. Developer dùng `Query` theo PK rồi `FilterExpression status = PAID`. Hãy giải thích vì sao filter không làm thao tác thành query theo index status. Đề xuất GSI hoặc data access model nếu truy vấn PAID rất thường xuyên. Khi nào phải theo `LastEvaluatedKey` dù một trang không có item khớp?

### Bài 6 — Cassandra partition key

Thiết kế bảng `orders_by_customer` theo `(tenant_id, customer_id)`, clustering theo `created_at`. Một báo cáo yêu cầu tất cả đơn PAID của tenant trong một tháng, không biết customer ID. Vì sao bảng hiện tại không phù hợp? Hãy đề xuất bảng theo `(tenant_id, status, month_bucket)` và nêu trách nhiệm đồng bộ khi status đổi.

### Bài 7 — Mẫu quan hệ Cypher

Cho graph:

```text
(Customer C007) -PLACED-> (Order O1001)
(Order O1001) -HAS_LINE-> (OrderLine L1 {quantity: 2})
(OrderLine L1) -OF_PRODUCT-> (Product P10)
```

Viết Cypher tìm các `Order` của C007 có dòng hàng thuộc P10 và `quantity >= 2`. Hãy chỉ rõ hướng của từng cạnh và vai trò của `WHERE`.

### Bài 8 — Bảo vệ tenant

Một endpoint tìm đơn nhận `tenantId` và biểu thức filter tùy ý từ client. Hãy nêu những vấn đề bảo mật và thay bằng hợp đồng nhận field lọc nằm trong allowlist, lấy tenant từ authentication, giới hạn page size và dùng parameterized query.

## 23. Kết luận

Trong NoSQL, “lọc dữ liệu” không chỉ là thêm một điều kiện `WHERE`. Có bốn kiểu truy vấn cần phân biệt:

1. **Theo khóa:** xác định đúng bản ghi/key/partition bằng định danh đã biết.
2. **Theo trường:** lọc giá trị, tập giá trị, khoảng số hoặc ngày; hiệu quả phụ thuộc index và mô hình phân vùng.
3. **Theo đường dẫn:** tìm thuộc tính lồng nhau và phần tử mảng; cần hiểu sự khác biệt giữa dot notation và `$elemMatch`.
4. **Theo mẫu quan hệ:** tìm các nút/cạnh phù hợp một đường đi có hướng; chú ý điểm xuất phát, số hop và fan-out.

MongoDB cho phép nhiều biểu thức lọc trực tiếp trên document; Redis chủ yếu tra theo key; DynamoDB và Cassandra nhấn mạnh khóa/partition theo access pattern; Neo4j thể hiện điều kiện trên node và mẫu quan hệ qua Cypher. Mỗi hệ có **đường truy cập nhanh và giới hạn riêng**.

Khi xây dựng một truy vấn thực tế, hãy bắt đầu từ **câu hỏi nghiệp vụ, khóa đã biết và kết quả cần trả**, sau đó chọn cấu trúc dữ liệu, index, phân trang, mức nhất quán và ràng buộc quyền phù hợp. Một query **trả đúng trên bốn document demo** chưa đủ: nó còn phải đúng ở trường hợp mảng, tenant, dữ liệu vừa cập nhật và hoạt động hiệu quả khi hệ thống mở rộng.
