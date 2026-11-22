# Ví dụ MongoDB với giới hạn triển khai cụ thể của mô hình tài liệu

## 1. Bối cảnh và phạm vi

**Document database** lưu dữ liệu thành các **document** gồm các cặp tên trường – giá trị. Giá trị có thể là chuỗi, số, ngày giờ, đối tượng lồng nhau hoặc mảng. MongoDB là một cơ sở dữ liệu tài liệu tiêu biểu: document được biểu diễn gần với JSON nhưng lưu dưới dạng **BSON**, và các document cùng loại thường đặt trong một **collection**.

Ta xây dựng một ví dụ giới hạn cho hệ thống bán sách. Collection `orders` lưu đơn hàng, hỗ trợ:

1. Tạo đơn với người nhận, địa chỉ và nhiều dòng sản phẩm.
2. Lấy chi tiết một đơn theo mã.
3. Liệt kê đơn của khách theo trạng thái, thời gian và thứ tự mới nhất.
4. Tìm đơn có sản phẩm cụ thể với số lượng tối thiểu.
5. Cập nhật trạng thái đơn có điều kiện.
6. Tổng hợp doanh thu từ những đơn đã thanh toán.

Ví dụ sử dụng **MongoDB và trình dòng lệnh `mongosh`** để minh họa trực tiếp mô hình tài liệu. Đây là chương trình học tập trên máy local, **chưa phải hệ thống thanh toán/tồn kho thực tế**. Ta sẽ chỉ rõ giới hạn liên quan đến kích thước document, index, tính nguyên tử, schema, replication, sharding và bảo mật triển khai.

## 2. Chuẩn bị môi trường MongoDB local

Nếu đã có Docker và có thể kéo image, mở một MongoDB chỉ bind vào loopback của máy:

```powershell
docker run -d --rm --name mongo-doc-demo -p 127.0.0.1:27017:27017 mongo:7.0
docker exec -it mongo-doc-demo mongosh
```

Trong cửa sổ `mongosh`:

```javascript
use doc_model_demo
```

Các lệnh tạo collection và chèn dữ liệu dưới đây dự kiến chạy **một lần trên database thử nghiệm trống**. Khi muốn dừng ví dụ:

```powershell
docker stop mongo-doc-demo
```

**Ranh giới của cấu hình này:** MongoDB chạy standalone, chưa bật xác thực, TLS, replica set, transaction nhiều document hoặc persistent volume. Container có `--rm` nên khi dừng, tài nguyên container bị xóa; ví dụ không dành để lưu dữ liệu quan trọng. Không mở cổng MongoDB chưa được bảo vệ này ra mạng hoặc dùng trong production.

## 3. Thiết kế một document đơn hàng

Ứng dụng thường xem thông tin giao hàng và các dòng sản phẩm **cùng với** đơn hàng. Có thể đặt những trường này chung vào một document:

```javascript
{
  _id: "ORD-1001",
  customerId: "CUS-007",
  status: "PAID",
  createdAt: ISODate("2026-11-10T08:30:00Z"),
  paidAt: ISODate("2026-11-10T08:35:00Z"),
  shipping: {
    recipient: "Mai",
    city: "Hà Nội",
    district: "Cầu Giấy",
    addressLine: "Đường Mẫu số 1"
  },
  items: [
    { sku: "BK-101", name: "Sách A", quantity: 2, unitPriceVnd: 150000 },
    { sku: "BK-202", name: "Sách B", quantity: 1, unitPriceVnd: 220000 }
  ],
  totalVnd: 520000
}
```

Ý nghĩa của những quyết định thiết kế:

- `_id` định danh duy nhất một đơn trong collection `orders`. MongoDB tạo chỉ mục duy nhất cho `_id` của collection thông thường.
- `customerId` tham chiếu đến khách hàng được lưu riêng. Một khách có thể có rất nhiều đơn; không nhúng mọi đơn vào document khách hàng.
- `shipping` là **embedded document**: đối tượng lồng nhau mô tả nơi nhận hàng.
- `items` là **mảng embedded document**: một đơn có nhiều dòng hàng.
- `name`, `unitPriceVnd` là thông tin **chụp lại lúc đặt**. Nếu giá hay tên của sản phẩm hiện tại thay đổi, lịch sử giao dịch vẫn đúng.
- `totalVnd` là giá trị do logic nghiệp vụ tính từ các dòng hàng và các khoản phí/giảm giá có liên quan; không được tin hoàn toàn vào số tiền do client gửi lên.

Sơ đồ quan hệ lưu trữ:

```text
customers collection                 orders collection

  Customer CUS-007 <---customerId--- Order ORD-1001
                                         |
                                         +-- shipping (object)
                                         |      recipient, city, ...
                                         |
                                         +-- items (array)
                                         |      +-- BK-101, qty=2, price=150000
                                         |      +-- BK-202, qty=1, price=220000
                                         |
                                         +-- totalVnd=520000
```

So với việc tách từng item thành document riêng rồi luôn phải kết hợp khi xem chi tiết, cách nhúng có thể giúp đọc trọn một đơn bằng **một truy vấn theo khóa**. Đổi lại, nếu items tăng quá lớn hoặc được xử lý độc lập thường xuyên, phải xem lại ranh giới document.

## 4. Đặt ràng buộc schema cho collection

Tính linh hoạt của document model không có nghĩa dữ liệu được phép tùy tiện. Ví dụ đơn hàng nên yêu cầu mã khách, trạng thái, ngày tạo, địa chỉ giao hàng, ít nhất một item và tổng tiền.

Tạo collection `orders` với trình xác thực `$jsonSchema`:

```javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["customerId", "status", "createdAt", "shipping", "items", "totalVnd"],
      properties: {
        customerId: { bsonType: "string" },
        status: { enum: ["PENDING", "PAID", "CANCELLED"] },
        createdAt: { bsonType: "date" },
        paidAt: { bsonType: "date" },
        shipping: {
          bsonType: "object",
          required: ["recipient", "city"],
          properties: {
            recipient: { bsonType: "string" },
            city: { bsonType: "string" }
          }
        },
        items: {
          bsonType: "array",
          minItems: 1,
          items: {
            bsonType: "object",
            required: ["sku", "quantity", "unitPriceVnd"],
            properties: {
              sku: { bsonType: "string" },
              quantity: { bsonType: ["int", "long"] },
              unitPriceVnd: { bsonType: ["int", "long"] }
            }
          }
        },
        totalVnd: { bsonType: ["int", "long"] }
      }
    }
  },
  validationAction: "error"
})
```

Quy tắc này chỉ kiểm tra **kiểu và một số trường bắt buộc**. Nó chưa tự chứng minh `totalVnd` bằng tổng giá từng item, quantity dương, SKU có thật trong danh mục hay `paidAt` chỉ xuất hiện với đơn đã thanh toán. Các bất biến đó cần được bảo vệ bởi tầng nghiệp vụ và cách ghi dữ liệu phù hợp.

Ví dụ sử dụng `NumberInt` cho số lượng và giá trị VND nhỏ. Khi có nguy cơ vượt giới hạn 32-bit, phải chọn kiểu số thích hợp như `NumberLong` hoặc `Decimal128`, định nghĩa quy tắc làm tròn và đảm bảo cùng cách biểu diễn ở service, database và báo cáo. Tránh lưu số tiền dưới dạng chuỗi không chuẩn hóa.

## 5. Thêm dữ liệu minh họa

```javascript
db.orders.insertMany([
  {
    _id: "ORD-1001",
    customerId: "CUS-007",
    status: "PAID",
    createdAt: ISODate("2026-11-10T08:30:00Z"),
    paidAt: ISODate("2026-11-10T08:35:00Z"),
    shipping: {
      recipient: "Mai",
      city: "Hà Nội",
      district: "Cầu Giấy",
      addressLine: "Đường Mẫu số 1"
    },
    items: [
      {
        sku: "BK-101",
        name: "Sách A",
        quantity: NumberInt(2),
        unitPriceVnd: NumberInt(150000)
      },
      {
        sku: "BK-202",
        name: "Sách B",
        quantity: NumberInt(1),
        unitPriceVnd: NumberInt(220000)
      }
    ],
    totalVnd: NumberInt(520000)
  },
  {
    _id: "ORD-1002",
    customerId: "CUS-007",
    status: "PENDING",
    createdAt: ISODate("2026-11-11T10:00:00Z"),
    shipping: {
      recipient: "Mai",
      city: "Đà Nẵng",
      district: "Hải Châu",
      addressLine: "Đường Mẫu số 2"
    },
    items: [
      {
        sku: "BK-101",
        name: "Sách A",
        quantity: NumberInt(1),
        unitPriceVnd: NumberInt(150000)
      },
      {
        sku: "BK-303",
        name: "Sách C",
        quantity: NumberInt(3),
        unitPriceVnd: NumberInt(90000)
      }
    ],
    totalVnd: NumberInt(420000)
  }
])
```

Hai đơn có cùng khách `CUS-007` nhưng khác trạng thái và thành phố. Số tiền tương ứng:

```text
ORD-1001 = 2 × 150.000 + 1 × 220.000 = 520.000 VND
ORD-1002 = 1 × 150.000 + 3 ×  90.000 = 420.000 VND
```

Nếu chạy lại đoạn `insertMany` với hai mã `_id` này, lỗi duplicate key là hành vi được mong đợi. Không cần xóa collection khi chỉ muốn thực hiện lại truy vấn đọc.

## 6. Truy vấn theo khóa và trường lồng nhau

### 6.1. Tìm một document bằng khóa

```javascript
db.orders.findOne({ _id: "ORD-1001" })
```

Đây là **point lookup**, trả một đơn theo định danh đã biết. Truy vấn theo `_id` thường rất phù hợp cho màn hình xem chi tiết.

### 6.2. Lọc theo nhiều trường

```javascript
db.orders.find({
  customerId: "CUS-007",
  status: "PAID"
})
```

Hai điều kiện trong cùng một đối tượng mang nghĩa **AND**: đơn phải thuộc khách `CUS-007` *và* có trạng thái `PAID`. Với dữ liệu khởi tạo, chỉ `ORD-1001` thỏa mãn.

### 6.3. Truy cập trường con bằng dot notation

```javascript
db.orders.find({
  "shipping.city": "Hà Nội"
})
```

`"shipping.city"` là đường dẫn đến trường `city` bên trong `shipping`. Không cần so sánh toàn bộ object `shipping`, vốn có thể chứa thêm `district`, `addressLine` và các trường khác.

Truy vấn tổng tiền trong một khoảng:

```javascript
db.orders.find({
  totalVnd: { $gte: 400000, $lt: 600000 }
})
```

Các toán tử phổ biến gồm `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in` và `$or`. Cần phân biệt kiểu số, chuỗi và ngày khi so sánh.

### 6.4. Điều kiện trên mảng object

```javascript
// Tìm đơn có ít nhất một item mang SKU BK-101.
db.orders.find({ "items.sku": "BK-101" })
```

Cả hai đơn đều khớp. Nhưng nếu muốn **một dòng hàng vừa là BK-101 vừa có quantity >= 2**, phải ràng buộc vào **cùng một phần tử**:

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

Kết quả chỉ có `ORD-1001`. So sánh với:

```javascript
db.orders.find({
  "items.sku": "BK-101",
  "items.quantity": { $gte: 2 }
})
```

Truy vấn thứ hai vẫn có thể khớp `ORD-1002`: item `BK-101` có số lượng 1 nhưng item `BK-303` có số lượng 3. Các điều kiện trên mảng đặt riêng qua dot notation **không bắt buộc cùng phần tử**. Đây là giới hạn ngữ nghĩa truy vấn cần hiểu rõ.

### 6.5. Projection tránh trả dữ liệu không cần thiết

```javascript
db.orders.find(
  { customerId: "CUS-007" },
  {
    _id: 1,
    createdAt: 1,
    status: 1,
    "shipping.city": 1,
    totalVnd: 1
  }
)
```

Projection giúp giảm lượng dữ liệu truyền về application. Tuy nhiên, chỉ chọn ít trường **không bảo đảm** database sẽ tránh đọc document gốc; điều này còn phụ thuộc chỉ mục và execution plan.

## 7. Sắp xếp, phân trang và index ghép

Một màn hình danh sách phổ biến cần 20 đơn mới nhất của khách:

```javascript
db.orders
  .find({ customerId: "CUS-007" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
```

`-1` nghĩa là giảm dần. Khóa phụ `_id` tạo thứ tự xác định khi nhiều đơn có cùng `createdAt`. Với lượng dữ liệu lớn, dùng `skip(100000)` để đi tới trang sâu thường tốn chi phí vì hệ thống phải đi qua nhiều kết quả trước đó. Một phương án là **cursor/keyset pagination**:

```javascript
const lastTime = ISODate("2026-11-11T10:00:00Z");
const lastId = "ORD-1002";

db.orders
  .find({
    customerId: "CUS-007",
    $or: [
      { createdAt: { $lt: lastTime } },
      { createdAt: lastTime, _id: { $lt: lastId } }
    ]
  })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
```

Cursor ở trên giữ hai thành phần của khóa sắp xếp. Ví dụ giả định `_id` đều là chuỗi có thứ tự so sánh ổn định. Khi dữ liệu được thêm hoặc sửa liên tục, phân trang theo cursor vẫn cần chiến lược nhất quán phù hợp nếu ứng dụng muốn một ảnh chụp bất biến.

Nếu truy vấn chủ đạo là "đơn PAID của khách, mới nhất trước", có thể tạo **compound index**:

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
})

db.orders
  .find({ customerId: "CUS-007", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
```

Trường lọc bằng thường đặt trước trường hỗ trợ sắp xếp. Tuy nhiên, index này được thiết kế cho một **mẫu truy vấn cụ thể**, không tự động tối ưu mọi cách lọc theo ngày hoặc mọi sort. Nếu ứng dụng liên tục truy vấn các đơn theo `customerId` nhưng không lọc `status`, cần phân tích xem có nên có index khác.

Index trên đường dẫn mảng:

```javascript
db.orders.createIndex({ "items.sku": 1 })
```

Vì `items` là mảng, MongoDB tạo **multikey index** để hỗ trợ truy vấn theo các phần tử. Kết quả `find` vẫn là document đơn hàng, không phải một dòng trả về cho mỗi item. MongoDB có các giới hạn đối với một số compound index gồm nhiều trường mảng; không thể mặc định mọi cách kết hợp mảng đều lập chỉ mục được.

Để quan sát cách truy vấn được thực hiện:

```javascript
db.orders
  .find({ customerId: "CUS-007", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .explain("executionStats")
```

Đọc các trường như `nReturned`, `totalDocsExamined`, `totalKeysExamined` và stage `IXSCAN`/`COLLSCAN`. Với collection chỉ có hai document, một full scan vẫn có thể được lựa chọn; cần đánh giá trên lượng dữ liệu và tải đại diện trước khi rút ra kết luận về hiệu năng.

**Đánh đổi của index:** tăng dung lượng lưu trữ, thêm chi phí duy trì khi insert/update/delete và không bảo đảm mọi phép nhóm/sort đều rẻ. Tạo index theo mẫu truy vấn đã quan sát, không tạo tràn lan chỉ vì document có nhiều trường.

## 8. Cập nhật có điều kiện trên một document

Ví dụ chỉ cho phép đổi địa chỉ nếu đơn còn đang chờ xử lý:

```javascript
db.orders.updateOne(
  { _id: "ORD-1002", status: "PENDING" },
  { $set: { "shipping.addressLine": "Đường Mẫu số 3" } }
)
```

**Dot notation** cho phép sửa một trường con mà không thay cả object. Lệnh sau có nghĩa khác:

```javascript
db.orders.updateOne(
  { _id: "ORD-1002" },
  { $set: { shipping: { city: "Huế" } } }
)
```

Lệnh này thay **toàn bộ** trường `shipping`; các trường `recipient`, `district`, `addressLine` không được đưa vào object mới sẽ mất. Với validator ở mục 4, cập nhật này bị từ chối vì thiếu `shipping.recipient`. Khi chỉ muốn sửa thành phố, cần viết `$set: { "shipping.city": "Huế" }`.

Ví dụ chuyển trạng thái:

```javascript
db.orders.updateOne(
  { _id: "ORD-1002", status: "PENDING" },
  { $set: { status: "PAID", paidAt: new Date() } }
)
```

Điều kiện lọc và phép cập nhật **trên một document** được thực hiện nguyên tử. Nếu hai request cùng muốn chuyển trạng thái từ `PENDING`, khi request thứ nhất cập nhật thành công thì request thứ hai không còn khớp điều kiện `status: "PENDING"`. Kết quả `updateOne` chứa `matchedCount` và `modifiedCount` để ứng dụng biết thao tác có thật sự áp dụng hay không.

**Giới hạn nghiệp vụ:** lệnh trên chỉ minh họa truy vấn có điều kiện. Trong hệ thống thật, chỉ ghi `PAID` sau khi xác minh kết quả thanh toán từ nguồn tin cậy. MongoDB không tự biết một giao dịch thanh toán đã được ngân hàng xác nhận.

## 9. Aggregation: báo cáo doanh thu

Thống kê doanh thu của các đơn đã thanh toán trong tháng 11/2026 theo khách hàng:

```javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 },
      revenueVnd: { $sum: "$totalVnd" }
    }
  },
  { $sort: { revenueVnd: -1, _id: 1 } }
])
```

Pipeline `$match` → `$group` → `$sort` thể hiện ba hoạt động: lọc, tính tổng theo nhóm và sắp xếp kết quả. Khoảng ngày dùng dạng **[đầu tháng, đầu tháng sau)** để không phụ thuộc mili giây cuối tháng; ví dụ giả định ngày ở UTC.

Nếu chạy cập nhật `ORD-1002` sang `PAID` ở mục 8 trước khi tổng hợp, đơn đó cũng được tính vào doanh thu. Nếu chưa chạy, báo cáo chỉ tính `ORD-1001`. Kết quả phụ thuộc trạng thái dữ liệu thực tế, không cố định sau từng lần thực hành.

Khi có hàng triệu đơn, aggregation có thể cần đọc và xử lý nhiều bản ghi ngay cả khi bước lọc có index. Dashboard gọi liên tục có thể cần **materialized summary** theo ngày/khách, batch hoặc stream aggregation; đổi lại phải quản lý độ trễ và tính lại khi đơn bị hủy hoặc hoàn tiền.

## 10. Embed hay reference: ví dụ khách hàng và sản phẩm

Trong đơn hàng, thông tin giao hàng và từng dòng sản phẩm thường được đọc cùng nhau, nên nhúng là hợp lý. Nhưng hồ sơ khách hàng có vòng đời riêng:

```javascript
db.customers.insertOne({
  _id: "CUS-007",
  displayName: "Mai",
  loyaltyTier: "SILVER"
})
```

`orders.customerId` tham chiếu tới khách hàng. Khi thực sự cần hiển thị thông tin hiện tại của khách cùng đơn, có thể dùng `$lookup`:

```javascript
db.orders.aggregate([
  { $match: { _id: "ORD-1001" } },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customerInfo"
    }
  },
  {
    $project: {
      _id: 1,
      status: 1,
      totalVnd: 1,
      "customerInfo.displayName": 1
    }
  }
])
```

`$lookup` trả về trường `customerInfo` dưới dạng **mảng**, kể cả khi mã khách chỉ khớp một document. Phép kết hợp cũng có chi phí: cần quan tâm index, số document tham gia và cách phân bố dữ liệu trên cluster.

Một quy tắc thiết kế hữu ích:

| Dữ liệu | Thiết kế ví dụ | Lý do |
|---|---|---|
| Địa chỉ giao hàng khi đặt đơn | Nhúng trong `orders.shipping` | Đọc cùng đơn và cần giữ lịch sử |
| Dòng hàng của một đơn thông thường | Nhúng trong `orders.items` | Thường đọc/cập nhật cùng đơn; kích thước có thể kiểm soát |
| Hồ sơ khách hàng | Collection `customers` riêng, đơn giữ `customerId` | Thay đổi độc lập và được nhiều đơn dùng |
| Danh mục sản phẩm hiện tại | Collection `products` riêng; đơn lưu snapshot tên/đơn giá | Giá hiện tại không làm thay đổi hóa đơn cũ |
| Toàn bộ lịch sử đơn của khách | Nhiều document `orders`, index theo `customerId` | Tránh mảng tăng không giới hạn trong document khách |

## 11. Giới hạn kỹ thuật cụ thể của mô hình MongoDB

### 11.1. Giới hạn 16 MiB trên một BSON document

MongoDB giới hạn kích thước **một BSON document ở 16 MiB**. Một document khách hàng chứa mảng `orders` tăng mãi sẽ có ngày vượt giới hạn. Vì vậy, hệ thống nên lưu từng đơn thành document độc lập, rồi tìm theo `customerId`. Ngay cả `orders.items` cũng cần quy định số lượng item tối đa theo nghiệp vụ; một đơn chứa hàng trăm nghìn dòng không còn là trường hợp nhúng nhỏ gọn.

### 11.2. Nguyên tử ở một document khác với nhiều document

MongoDB đảm bảo tính nguyên tử của **mỗi thao tác ghi trên một document**, kể cả khi thao tác thay đổi nhiều trường của document ấy. Nhưng nếu ứng dụng tạo đơn và giảm tồn kho ở hai document:

```text
1. INSERT orders[ORD-1003]         -> thành công
2. UPDATE products[BK-101].stock   -> thất bại
```

thì dữ liệu có thể bị lệch nếu ứng dụng không có biện pháp xử lý. **Multi-document transaction** được MongoDB hỗ trợ trên topology replica set hoặc sharded cluster phù hợp; bản standalone local ở mục 2 không được cấu hình cho tính năng này. Ngay cả khi dùng transaction, các thao tác với cổng thanh toán bên ngoài không tự động tham gia cùng giao dịch ACID của MongoDB. Hệ thực cần thiết kế kiểm tra điều kiện tồn kho, idempotency, retry, trạng thái đặt chỗ và/hoặc quy trình bù trừ.

### 11.3. Tăng trưởng index và chi phí ghi

Một collection có nhiều index cho mọi kết hợp trường sẽ tốn bộ nhớ/đĩa và tăng chi phí ghi. Một số truy vấn lọc sâu vào mảng hoặc tổng hợp nhiều nhóm vẫn phải đọc nhiều dữ liệu. Việc lập index chỉ hữu ích nếu đúng với **access pattern** và độ chọn lọc thực tế.

### 11.4. Schema linh hoạt và vấn đề chuyển phiên bản

Giả sử ứng dụng đổi `shipping.city` thành `shipping.provinceCity`. Tài liệu cũ không tự chuyển đổi:

```javascript
// Phiên bản cũ:
{ shipping: { city: "Hà Nội" } }

// Phiên bản mới:
{ shipping: { provinceCity: "Hà Nội" } }
```

Ứng dụng có thể cần đọc tương thích hai trường trong thời gian chuyển tiếp, chạy backfill có kiểm soát, dùng `schemaVersion` hoặc tạo công cụ migration. Phải đồng bộ quy tắc validation với thời điểm triển khai code mới. **Không có schema cứng ở tầng lưu trữ không đồng nghĩa không có nghĩa vụ quản lý data contract.**

### 11.5. Giới hạn về truy vấn quan hệ

MongoDB hỗ trợ `$lookup` nhưng một truy vấn liên tục duyệt nhiều lớp quan hệ phức tạp có thể trở nên tốn tài nguyên. Nếu ứng dụng chủ yếu cần duyệt graph nhiều bước, phải đánh giá mô hình dữ liệu/loại hệ lưu trữ phù hợp; không nên nhúng vô hạn hoặc kỳ vọng một phép join bất kỳ luôn rẻ.

## 12. Giới hạn triển khai: demo và production

| Chủ đề | Trong bài học này | Trong ứng dụng production |
|---|---|---|
| Topology | Một tiến trình MongoDB standalone | Replica set cho tính sẵn sàng và phù hợp yêu cầu giao dịch; sharding nếu thực sự cần |
| Kết nối | Chỉ bind `127.0.0.1`, không auth/TLS | Xác thực, TLS, network policy, quyền tối thiểu, quản lý secret |
| Dữ liệu trên đĩa | Container thử nghiệm không gắn persistent volume | Persistent storage, dung lượng, backup và khôi phục đã thử |
| Tải thử | Hai document mẫu | Dữ liệu đại diện, kiểm thử tải, latency p95/p99, phân tích index |
| Nguyên tử | Ghi một document | Định nghĩa giao dịch và idempotency xuyên nhiều thành phần |
| Mở rộng | Chưa shard | Đánh giá shard key, phân bố tải, hot partition và chi phí cross-shard |
| Mã hóa thông tin | Dữ liệu giả | Phân quyền, chính sách PII, log an toàn, thời hạn lưu |
| Kiểu dữ liệu | Số nguyên VND, trường cơ bản | Quy tắc overflow, precision, schema migration, tương thích API |
| Quan sát | Truy vấn `explain` | Metrics, slow queries, cảnh báo, thời gian phục hồi và quy trình sự cố |

### Replica set không đồng nghĩa chia đều tải ghi

Replica set có primary và các secondary để sao chép dữ liệu, hỗ trợ tính sẵn sàng và một số tính năng giao dịch. Nó không tự động biến một khóa hoặc một document bị ghi cực nhiều thành nhiều bản ghi độc lập có thể ghi song song trên các primary. Cần phân biệt **replication** với **sharding**.

### Sharding không tự động giải quyết mọi nút thắt

Khi cần chia collection trên nhiều shard, cách chọn **shard key** tác động lớn tới khả năng định tuyến truy vấn, phân bố dữ liệu và điểm nóng. Nếu ứng dụng thường tìm đơn theo khách hàng và thời gian, cần đánh giá bộ khóa phân vùng với các mẫu truy vấn đó. Chọn sai có thể khiến truy vấn phải hỏi nhiều shard hoặc một shard chịu tải vượt trội.

### Nhất quán đọc và ghi còn phụ thuộc topology

Trên cluster, độ bền và khả năng quan sát kết quả ghi còn phụ thuộc vào **write concern**, **read concern**, session và replication lag. Không nên khẳng định mọi lần đọc luôn thấy ngay một giá trị mới từ mọi replica trong mọi cấu hình. Các quyết định về ưu tiên tính sẵn sàng, độ trễ và mức nhất quán phải xuất phát từ yêu cầu nghiệp vụ.

### Hạn chế dữ liệu nhạy cảm

Đơn hàng có thể chứa tên và địa chỉ người nhận. Cần quy định ai có quyền truy vấn trường nào, dữ liệu được ghi log ra sao và khi nào phải xóa hoặc ẩn danh. Không nhúng token thanh toán hay thông tin thẻ nhạy cảm vào document chỉ vì schema có thể chứa thêm trường.

## 13. Cần làm gì khi đơn hàng và tồn kho cùng thay đổi?

Hãy xét một yêu cầu mới: người dùng mua hai cuốn `BK-101`. Bên cạnh tạo đơn, ứng dụng phải giảm tồn kho ở document sản phẩm và gửi yêu cầu thanh toán. Đây là điểm phạm vi của ví dụ trở nên rõ:

1. **Đơn hàng:** một document có thể lưu toàn bộ trạng thái đơn và items.
2. **Tồn kho:** document sản phẩm/kho cần kiểm tra điều kiện không âm trước khi giảm.
3. **Thanh toán:** dịch vụ ngoài database cần idempotency và cơ chế chờ nhận kết quả.

Có thể dùng transaction MongoDB khi các cập nhật nhiều document cùng nằm trong phạm vi hỗ trợ và cần commit/rollback cùng nhau. Hoặc thiết kế workflow trạng thái `PENDING → RESERVED → PAID` có thời hạn giữ hàng và các bước bù trừ rõ ràng. Gọi API ngân hàng không nằm trong cùng transaction database; phải xử lý kết quả đến muộn, timeout, retry và webhook gửi trùng.

**Bài học thiết kế:** nhúng những dữ liệu có vòng đời chung giúp giảm nhu cầu giao dịch nhiều document, nhưng không thể xóa bỏ mọi quan hệ và mọi yêu cầu nhất quán giữa các hệ thống.

## 14. Bài tập thực hành

Trên database `doc_model_demo` sau khi chèn dữ liệu mẫu:

1. Tìm `ORD-1001` nhưng chỉ trả `status`, `shipping.city` và `totalVnd`.
2. Tìm đơn của `CUS-007` giao đến `"Đà Nẵng"`.
3. Tìm đơn có **một item** thỏa `sku = "BK-101"` và `quantity >= 2`; so sánh với việc lọc hai trường `items.sku` và `items.quantity` độc lập.
4. Liệt kê đơn theo `createdAt` giảm dần, một đơn mỗi trang, dùng cặp `createdAt` và `_id` để lấy trang tiếp.
5. Đổi `ORD-1002` từ `PENDING` sang `PAID`. Chạy lại thao tác với cùng điều kiện và giải thích vì sao `matchedCount` bằng 0 ở lần sau.
6. Tính tổng doanh thu từ các đơn `PAID` trước và sau khi thực hiện bài 5.
7. Xem `explain("executionStats")` trước và sau khi tạo một index phù hợp; giải thích vì sao dữ liệu chỉ có hai đơn chưa đủ để kết luận về hiệu năng thực tế.

Ví dụ lời giải bài 1:

```javascript
db.orders.find(
  { _id: "ORD-1001" },
  { _id: 0, status: 1, "shipping.city": 1, totalVnd: 1 }
)
```

Lưu ý: các bài thay đổi trạng thái ảnh hưởng kết quả thống kê ở bài kế tiếp. Hãy thực hành trên database riêng, không chạy các lệnh ghi này trên dữ liệu sản xuất.

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Nhúng mọi đơn trong một document khách hàng | Mảng tăng vô hạn, có thể vượt 16 MiB | Tách mỗi đơn thành document riêng, index theo khách |
| Chỉ tham chiếu giá sản phẩm hiện tại | Giá của đơn lịch sử bị thay đổi gián tiếp | Lưu snapshot tên và đơn giá trong đơn |
| Đặt hai điều kiện riêng trên `items.*` | Có thể khớp hai phần tử mảng khác nhau | Dùng `$elemMatch` khi yêu cầu cùng item |
| Thay nguyên `shipping` khi chỉ sửa một trường | Mất thông tin con hoặc bị schema validator từ chối | `$set` đường dẫn con |
| Tạo index cho mọi trường | Tăng dung lượng và chi phí ghi | Thiết kế từ truy vấn thật và đo bằng `explain` |
| Coi hai update trên hai document là nguyên tử | Trạng thái nghiệp vụ có thể lệch nếu bước sau lỗi | Transaction hoặc quy trình bù trừ |
| Dùng standalone demo cho production | Rủi ro mất dữ liệu, truy cập trái phép, downtime | Thiết kế topology, bảo mật, backup, monitoring phù hợp |
| Coi document linh hoạt là không cần quy ước | Sai kiểu dữ liệu, code cũ không đọc được tài liệu mới | Validation, versioning, migration |

## 16. Kết luận

Ví dụ MongoDB cho thấy document model phù hợp với thực thể có dữ liệu **được đọc cùng nhau**: một đơn hàng có thể chứa địa chỉ và mảng dòng sản phẩm, được tìm theo khóa, lọc theo trường lồng nhau, truy vấn phần tử bằng `$elemMatch`, sắp xếp qua index và cập nhật nguyên tử trong phạm vi **một document**.

Các giới hạn triển khai quan trọng gồm **16 MiB cho mỗi BSON document**, chi phí index và aggregation, ranh giới nguyên tử giữa một document với nhiều document, việc cần quản lý schema khi dữ liệu tiến hóa, và khác biệt đáng kể giữa MongoDB standalone để học với cluster production có bảo mật, sao lưu và quan sát vận hành.

Khi triển khai một tính năng NoSQL thật, trước hết cần mô tả rõ **những thao tác đọc/ghi chủ đạo, dữ liệu nào cần nằm cùng nhau, tính nhất quán mong muốn và tốc độ tăng trưởng**. Sau đó chọn cách nhúng/tham chiếu, chỉ mục và topology phù hợp, kiểm chứng bằng dữ liệu và tải đại diện.
