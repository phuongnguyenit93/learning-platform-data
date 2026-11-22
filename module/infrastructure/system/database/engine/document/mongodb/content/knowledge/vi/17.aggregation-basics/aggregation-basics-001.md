# Luồng document qua pipeline và cách phân biệt stage với expression trong MongoDB

## 1. Vì sao cần hiểu luồng document trong Aggregation Framework?

Truy vấn **find()** thường tập trung vào việc chọn document thỏa một điều kiện và trả về các field mong muốn. Khi ứng dụng cần tính toán, chuyển đổi cấu trúc, thống kê, nối dữ liệu hoặc chuẩn bị một báo cáo phức tạp, MongoDB cung cấp **Aggregation Framework**.

Trọng tâm của Aggregation Framework là **pipeline**: một chuỗi các bước xử lý, trong đó kết quả của bước trước trở thành đầu vào cho bước tiếp theo.

~~~text
Collection orders
      |
      |  Document từ nguồn
      v
  [$match]          Chọn đơn hàng cần tính
      |
      v
  [$unwind]         Tách mảng items thành nhiều document
      |
      v
  [$group]          Gom theo SKU và cộng số lượng
      |
      v
  [$sort]           Sắp xếp kết quả thống kê
      |
      v
 Kết quả cuối cùng
~~~

Hai khái niệm thường bị nhầm khi mới học:

1. **Stage:** một **bước trong pipeline**, chẳng hạn **$match**, **$project**, **$group** hoặc **$sort**. Stage nhận một luồng document và xác định cách tạo ra luồng đầu ra.
2. **Expression:** một **biểu thức tính giá trị** bên trong những stage cho phép sử dụng nó, chẳng hạn **$multiply**, **$add**, **$cond**, **$concat** hoặc **$toUpper**. Expression nhận các giá trị và trả về một giá trị; bản thân nó **không phải một bước pipeline**.

Ví dụ:

~~~javascript
db.orders.aggregate([
  {
    $project: {                    // Stage
      _id: 0,
      customerId: 1,
      totalWithFee: {              // Trường được tính
        $add: [                   // Expression
          "$subtotal",           // Field-path expression
          "$shippingFee"
        ]
      }
    }
  }
]);
~~~

**$project** là stage. **$add** là expression bên trong stage đó. **"$subtotal"** là biểu thức tham chiếu field của document hiện tại, không phải chuỗi ký tự thông thường khi được dùng trong vị trí expression.

Hiểu được sự phân tầng này giúp đọc đúng truy vấn, tránh lỗi cú pháp và dự đoán **hình dạng dữ liệu** cũng như **số document** sau từng bước.

## 2. Dữ liệu thực hành: đơn hàng và các dòng hàng

Các ví dụ dùng **mongosh** và một collection thử nghiệm riêng. Trong thực tế, đừng chạy thao tác ghi dữ liệu lab lên production.

~~~javascript
use aggregation_flow_lab

db.orders.insertMany([
  {
    _id: "O101",
    tenantId: "SHOP-A",
    customerId: "C01",
    channel: "WEB",
    status: "PAID",
    createdAt: ISODate("2026-07-01T09:00:00Z"),
    shippingFee: NumberDecimal("10.00"),
    items: [
      {
        sku: "SKU-A",
        qty: NumberInt(2),
        unitPrice: NumberDecimal("100.00")
      },
      {
        sku: "SKU-B",
        qty: NumberInt(1),
        unitPrice: NumberDecimal("50.00")
      }
    ]
  },
  {
    _id: "O102",
    tenantId: "SHOP-A",
    customerId: "C02",
    channel: "APP",
    status: "PAID",
    createdAt: ISODate("2026-07-02T09:00:00Z"),
    shippingFee: NumberDecimal("0.00"),
    items: [
      {
        sku: "SKU-A",
        qty: NumberInt(1),
        unitPrice: NumberDecimal("100.00")
      },
      {
        sku: "SKU-C",
        qty: NumberInt(3),
        unitPrice: NumberDecimal("20.00")
      }
    ]
  },
  {
    _id: "O103",
    tenantId: "SHOP-A",
    customerId: "C01",
    channel: "WEB",
    status: "CANCELLED",
    createdAt: ISODate("2026-07-02T12:00:00Z"),
    shippingFee: NumberDecimal("0.00"),
    items: [
      {
        sku: "SKU-B",
        qty: NumberInt(2),
        unitPrice: NumberDecimal("50.00")
      }
    ]
  },
  {
    _id: "O104",
    tenantId: "SHOP-B",
    customerId: "C03",
    channel: "WEB",
    status: "PAID",
    createdAt: ISODate("2026-07-03T09:00:00Z"),
    shippingFee: NumberDecimal("10.00"),
    items: [
      {
        sku: "SKU-A",
        qty: NumberInt(4),
        unitPrice: NumberDecimal("100.00")
      }
    ]
  },
  {
    _id: "O105",
    tenantId: "SHOP-A",
    customerId: "C03",
    channel: "WEB",
    status: "PAID",
    createdAt: ISODate("2026-07-03T13:00:00Z"),
    shippingFee: NumberDecimal("0.00"),
    items: [
      {
        sku: "SKU-C",
        qty: NumberInt(2),
        unitPrice: NumberDecimal("20.00")
      }
    ]
  },
  {
    _id: "O106",
    tenantId: "SHOP-A",
    customerId: "C04",
    channel: "POS",
    status: "PENDING",
    createdAt: ISODate("2026-07-04T09:00:00Z"),
    shippingFee: NumberDecimal("0.00"),
    items: [
      {
        sku: "SKU-B",
        qty: NumberInt(1),
        unitPrice: NumberDecimal("50.00")
      }
    ]
  },
  {
    _id: "O107",
    tenantId: "SHOP-A",
    customerId: "C04",
    channel: "WEB",
    status: "PAID",
    createdAt: ISODate("2026-07-05T09:00:00Z"),
    shippingFee: NumberDecimal("0.00"),
    items: []
  }
]);
~~~

**Lưu ý:** mỗi **_id** được đặt cố định để dễ đối chiếu. Chạy lại nguyên lệnh **insertMany()** sẽ gặp duplicate key nếu dữ liệu đã tồn tại. Tạo collection mới hoặc reset dữ liệu lab có chủ đích trước khi thực hành lại.

Các document trên có:

- **Field chung:** _id, tenantId, customerId, channel, status, createdAt, shippingFee.
- **Field mảng:** items chứa những object có sku, qty và unitPrice.
- **Kiểu BSON cụ thể:** **createdAt** là BSON Date, **qty** là Int32, **unitPrice** và **shippingFee** là Decimal128.
- **Các trường hợp có chủ đích:** một đơn CANCELLED, một đơn thuộc tenant khác, một đơn PENDING và một đơn PAID có mảng items rỗng.

Điều này giúp minh họa rõ hơn việc **$match chọn document** và **$unwind thay đổi số lượng document**.

## 3. Pipeline là một mảng stage được thực thi theo thứ tự

### 3.1. Cú pháp tổng quát

~~~javascript
db.collection.aggregate([
  { $stageA: { /* cấu hình stage A */ } },
  { $stageB: { /* cấu hình stage B */ } },
  { $stageC: { /* cấu hình stage C */ } }
]);
~~~

Đối số đầu của **aggregate()** là **một mảng các stage documents**. Mỗi phần tử trong mảng đại diện cho một bước xử lý.

Ví dụ:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  },
  {
    $project: {
      _id: 1,
      customerId: 1,
      channel: 1
    }
  },
  {
    $sort: {
      _id: 1
    }
  }
]);
~~~

Pipeline này:

1. Nhận document từ collection **orders**.
2. **$match:** chỉ giữ đơn hàng PAID của SHOP-A.
3. **$project:** chỉ giữ _id, customerId và channel.
4. **$sort:** sắp xếp theo _id tăng dần.
5. Trả về một cursor chứa các document đầu ra.

Kết quả dự kiến:

~~~javascript
[
  { _id: "O101", customerId: "C01", channel: "WEB" },
  { _id: "O102", customerId: "C02", channel: "APP" },
  { _id: "O105", customerId: "C03", channel: "WEB" },
  { _id: "O107", customerId: "C04", channel: "WEB" }
]
~~~

**Điểm cốt lõi:** stage sau nhận **hình dạng document sau stage trước**, chứ không tự nhìn lại document gốc nếu một field đã bị loại hoặc bị thay đổi.

### 3.2. Hình dung document đi qua từng stage

~~~text
Nguồn (7 orders)
  |
  |  O101, O102, O103, O104, O105, O106, O107
  v
$match (tenantId=SHOP-A, status=PAID)
  |
  |  O101, O102, O105, O107            (4 documents)
  v
$project (_id, customerId, channel)
  |
  |  {O101,C01,WEB}
  |  {O102,C02,APP}
  |  {O105,C03,WEB}
  |  {O107,C04,WEB}                    (4 documents)
  v
$sort (_id tăng dần)
  |
  |  4 documents theo thứ tự mới
  v
Cursor kết quả
~~~

Không phải mọi stage đều làm thay đổi số document. Một số chỉ thay field; một số có thể **giảm** hoặc **tăng** số document; một số gom cả một tập thành những document thống kê.

## 4. Phân biệt stage và expression theo vị trí cú pháp

### 4.1. Stage: thao tác trên luồng document

Ví dụ ba stage:

~~~javascript
[
  { $match: { status: "PAID" } },
  { $set: { flag: true } },
  { $sort: { createdAt: -1 } }
]
~~~

- **$match** quyết định document nào được giữ.
- **$set** tạo/thay field trong từng document.
- **$sort** thay đổi thứ tự các document.

Mỗi stage thường có **một tên stage ở top level của stage document**. Không đặt hai stage khác nhau trong cùng một object rồi mong MongoDB tự thực thi hai bước.

### 4.2. Expression: tính giá trị bên trong stage

~~~javascript
db.orders.aggregate([
  {
    $set: {
      channelUpper: {
        $toUpper: "$channel"
      },
      hasItems: {
        $gt: [
          { $size: "$items" },
          0
        ]
      }
    }
  }
]);
~~~

Trong lệnh này:

- **$set** là stage.
- **$toUpper**, **$gt** và **$size** là expressions.
- **"$channel"** và **"$items"** là field-path expressions.
- **0** là hằng số.

Một expression **đánh giá giá trị**. Một stage **điều khiển luồng và hình dạng document**.

### 4.3. Ví dụ sai vì đặt expression làm stage

~~~javascript
// Sai: $add không phải một aggregation pipeline stage.
db.orders.aggregate([
  {
    $add: ["$shippingFee", 10]
  }
]);
~~~

Muốn tính giá trị, đặt **$add** trong stage hỗ trợ expression:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      increasedFee: {
        $add: [
          "$shippingFee",
          NumberDecimal("10.00")
        ]
      }
    }
  }
]);
~~~

### 4.4. Ví dụ sai vì dùng stage bên trong expression

~~~javascript
// Sai: $match là stage, không phải expression trả boolean.
db.orders.aggregate([
  {
    $project: {
      isPaid: {
        $match: { status: "PAID" }
      }
    }
  }
]);
~~~

Nếu muốn tính giá trị **isPaid** của từng document, dùng expression **$eq**:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      isPaid: {
        $eq: ["$status", "PAID"]
      }
    }
  }
]);
~~~

Nếu muốn **loại document không PAID**, đặt một **$match stage** riêng thay vì tính boolean.

### 4.5. Một số tên bắt đầu bằng $ có nhiều vai trò khác nhau

Không phải mọi từ khóa bắt đầu bằng **$** đều thuộc cùng loại:

| Ký hiệu | Vai trò phổ biến | Ví dụ |
|---|---|---|
| **$match** | Pipeline stage | **{$match:{status:"PAID"}}** |
| **$project** | Pipeline stage | **{$project:{name:1}}** |
| **$group** | Pipeline stage | **{$group:{_id:"$status",n:{$sum:1}}}** |
| **$add** | Aggregation expression | **{$add:["$a","$b"]}** |
| **$cond** | Aggregation expression | **{$cond:[condition,a,b]}** |
| **$gt** | Có dạng query operator và expression | **{qty:{$gt:2}}** khác **{$gt:["$qty",2]}** |
| **$sum** | Aggregation accumulator hoặc expression tùy ngữ cảnh | Trong **$group** hoặc **$project** |
| **$in** | Query operator hoặc aggregation expression tùy ngữ cảnh | **{tags:{$in:["a"]}}** và **{$in:["a","$tags"]}** |
| **$literal** | Aggregation expression | Giữ một giá trị nguyên văn thay vì diễn giải đặc biệt. |
| **$set** | Pipeline stage; cũng là update operator ngoài aggregation | **{$set:{x:1}}** trong pipeline hoặc update document. |

Cùng tên một toán tử đôi khi có cú pháp khác tùy **ngữ cảnh**. Đừng chỉ nhìn tên bắt đầu bằng **$** để suy ra nó là stage.

## 5. Cách đọc luồng qua các stage thường gặp

### 5.1. $match: lọc document

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  }
]);
~~~

**$match** giữ những document thỏa điều kiện. Với dữ liệu mẫu, từ 7 document đầu vào còn **4 document**: O101, O102, O105 và O107.

Đặc trưng:

- **Giảm hoặc giữ nguyên số lượng document**, không nhân document.
- Không tự làm thay đổi field trong các document được giữ.
- Cú pháp điều kiện thông thường theo **MongoDB query predicate**, tương tự **find()**.
- Thường nên đặt sớm khi có thể để giảm lượng dữ liệu cho các stage sau.

Nếu **$match** nằm đầu pipeline và query/index phù hợp, MongoDB có thể sử dụng index trên collection nguồn. Nếu đặt sau một stage làm biến đổi field, optimizer chỉ có thể đẩy điều kiện lên trước trong những trường hợp giữ nguyên semantics.

### 5.2. $project: chọn, bỏ và tính field

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 0,
      customerId: 1,
      status: 1,
      itemCount: {
        $size: "$items"
      }
    }
  }
]);
~~~

**$project** tạo hình dạng đầu ra mong muốn:

- **customerId: 1** và **status: 1** giữ các field có sẵn.
- **_id: 0** loại _id khỏi kết quả.
- **itemCount: {$size:"$items"}** tạo field tính toán.

Ví dụ O101 sau stage:

~~~javascript
{
  customerId: "C01",
  status: "PAID",
  itemCount: 2
}
~~~

**$project thường giữ nguyên số lượng document**, nhưng có thể làm mất các field mà stage sau cần. Mọi expression bên trong $project đánh giá trong ngữ cảnh document đầu vào của chính stage đó.

**Quy tắc projection:** không được trộn tùy tiện cách **include** và **exclude** trong cùng một **$project** (trừ _id và một số trường hợp expression đặc biệt). Ví dụ vừa đặt **customerId:1** vừa **status:0** thường là cấu hình không hợp lệ. Muốn bỏ một vài field mà giữ những field khác, cân nhắc **$unset**.

### 5.3. $set / $addFields: bổ sung hoặc thay field

~~~javascript
db.orders.aggregate([
  {
    $set: {
      itemCount: {
        $size: "$items"
      },
      channelUpper: {
        $toUpper: "$channel"
      }
    }
  }
]);
~~~

**$set** là alias của **$addFields** trong aggregation. Nó **giữ các field không bị nhắc đến** và thêm/thay field được khai báo. Nếu stage sau cần document gốc cùng các field tính toán, **$set** có thể thuận tiện hơn **$project**.

~~~text
Document trước $set:
  {_id, tenantId, status, items, shippingFee, ...}
            |
            v
Document sau $set:
  {_id, tenantId, status, items, shippingFee,
   itemCount, channelUpper, ...}
~~~

**Cảnh báo:** nếu **$set** định nghĩa field đã tồn tại, giá trị mới có thể ghi đè giá trị cũ trong kết quả của stage. Vì vậy khi đặt tên field cần biết rõ semantics.

### 5.4. $unset: loại bỏ field

~~~javascript
db.orders.aggregate([
  {
    $unset: [
      "shippingFee",
      "items.unitPrice"
    ]
  }
]);
~~~

**$unset** trong aggregation là stage chuyên loại field, thường thuận tiện khi muốn giữ phần còn lại của document. Nó **không xóa dữ liệu trong collection nguồn** khi dùng trong một pipeline đọc thông thường.

Phân biệt **$unset stage** và **$unset update operator** trong câu lệnh update thông thường: tên giống nhau nhưng ngữ cảnh và tác dụng lưu trữ khác nhau.

### 5.5. $sort: đổi thứ tự document

~~~javascript
db.orders.aggregate([
  {
    $sort: {
      createdAt: -1,
      _id: 1
    }
  }
]);
~~~

**$sort** thay đổi thứ tự của document nhưng không tự thêm/bỏ field. Với cùng lượng document đầu vào, số document đầu ra vẫn bằng nhau.

Nếu các document có cùng createdAt mà query chỉ sắp theo createdAt, thứ tự giữa chúng có thể không được bảo đảm ổn định. Bổ sung field phân biệt như **_id** giúp định nghĩa thứ tự rõ hơn, đặc biệt khi phân trang.

### 5.6. $limit và $skip: thay đổi số document được giữ

~~~javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: 2 },
  { $limit: 3 }
]);
~~~

**$skip** bỏ qua hai document đầu trong luồng sau sort, **$limit** chỉ lấy tối đa ba document tiếp theo.

Thứ tự của **$sort**, **$skip**, **$limit** có ý nghĩa. Nếu đặt **$limit** trước **$sort**, query sẽ chỉ sắp xếp tập đã bị giới hạn thay vì tìm ba document mới nhất của cả tập.

### 5.7. $unwind: một document có thể thành nhiều document

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "SHOP-A", status: "PAID" } },
  { $unwind: "$items" },
  {
    $project: {
      _id: 1,
      customerId: 1,
      sku: "$items.sku",
      qty: "$items.qty"
    }
  }
]);
~~~

Sau **$match**, có bốn đơn O101, O102, O105, O107. Mảng items của từng đơn:

| Đơn | Số phần tử items | Số document sau $unwind mặc định |
|---|---:|---:|
| O101 | 2 | 2 |
| O102 | 2 | 2 |
| O105 | 1 | 1 |
| O107 | 0 | 0 |
| **Tổng** | **5** | **5** |

Sau **$unwind**, mỗi document đầu ra chứa **một** item tại field items thay vì nguyên mảng.

Ví dụ O101 biến thành hai document:

~~~javascript
{
  _id: "O101",
  customerId: "C01",
  sku: "SKU-A",
  qty: 2
}

{
  _id: "O101",
  customerId: "C01",
  sku: "SKU-B",
  qty: 1
}
~~~

Việc trùng **_id: "O101"** trong kết quả pipeline là bình thường. Đây là **document kết quả trung gian**, không phải hai document mới được insert vào collection gốc với cùng _id.

**$unwind mặc định loại document có mảng rỗng, null hoặc missing** ở đường dẫn chỉ định. Muốn giữ chúng:

~~~javascript
db.orders.aggregate([
  {
    $unwind: {
      path: "$items",
      preserveNullAndEmptyArrays: true,
      includeArrayIndex: "itemIndex"
    }
  }
]);
~~~

Khi **preserveNullAndEmptyArrays: true**, document không có item có thể được giữ trong kết quả, nhưng field được unwind và giá trị **itemIndex** có thể có hình dạng khác với document chứa phần tử mảng thật. Cần quyết định cách xử lý null/missing khi group hoặc tính toán.

### 5.8. $group: nhiều document thành thống kê theo nhóm

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      unitsSold: {
        $sum: "$items.qty"
      },
      lineCount: {
        $sum: 1
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Kết quả:

~~~javascript
[
  { _id: "SKU-A", unitsSold: 3, lineCount: 2 },
  { _id: "SKU-B", unitsSold: 1, lineCount: 1 },
  { _id: "SKU-C", unitsSold: 5, lineCount: 2 }
]
~~~

Trong **$group**:

- **_id** là **grouping key**, không bắt buộc là _id của document nguồn.
- **"$items.sku"** là field-path expression tính khóa nhóm.
- **$sum** là accumulator tính tổng trên các document thuộc nhóm.
- **$sum: 1** đếm số document đầu vào của nhóm.
- **$sum: "$items.qty"** cộng tổng qty.

**$group** có thể giảm hàng nghìn document thành vài document nhóm. Nó không mặc định bảo đảm thứ tự kết quả; nếu cần thứ tự, thêm **$sort**.

### 5.9. $count: đếm số document đang đi qua stage

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  },
  {
    $count: "paidOrders"
  }
]);
~~~

Kết quả:

~~~javascript
[
  { paidOrders: 4 }
]
~~~

**$count stage** trả một document mang kết quả đếm nếu có document đầu vào. Nếu pipeline đầu vào rỗng, **$count stage** có thể trả **không document nào**, thay vì luôn trả **{paidOrders:0}**. Ứng dụng cần hiểu trường hợp này khi đọc cursor.

Nếu cần đếm **từng loại status**, sử dụng **$group** với khóa là status thay vì chỉ **$count**.

### 5.10. Bảng nhận diện thay đổi cardinality

| Stage | Vai trò | Số document sau stage |
|---|---|---|
| **$match** | Lọc theo điều kiện. | Không tăng; có thể giảm về 0. |
| **$project** | Chọn/tính field. | Thường giữ nguyên. |
| **$set / $addFields** | Thêm/thay field. | Thường giữ nguyên. |
| **$unset** | Bỏ field. | Thường giữ nguyên. |
| **$sort** | Sắp thứ tự. | Giữ nguyên. |
| **$skip** | Bỏ n document đầu. | Giảm hoặc giữ 0. |
| **$limit** | Chỉ cho tối đa n document. | Giảm hoặc giữ nguyên. |
| **$unwind** | Tách mảng. | Có thể tăng hoặc giảm. |
| **$group** | Gom nhóm. | Phụ thuộc số nhóm; thường giảm. |
| **$count** | Đếm cả luồng. | 1 nếu có input, 0 nếu input rỗng. |
| **$lookup** | Thêm dữ liệu join dưới dạng mảng. | Thường giữ nguyên số document ở dạng mặc định, có thể tăng sau unwind. |
| **$facet** | Xử lý nhiều nhánh pipeline. | Tạo một document gồm các mảng kết quả khi thực thi hợp lệ. |

**Cardinality** là số document ở một bước, còn **shape** là tập field và cấu trúc của mỗi document. Khi đọc một pipeline, phải theo dõi cả hai.

## 6. Luồng biến đổi shape: stage sau chỉ thấy dữ liệu stage trước trả ra

### 6.1. Ví dụ mất field sau $project

~~~javascript
db.orders.aggregate([
  {
    $project: {
      customerId: 1,
      status: 1
    }
  },
  {
    $match: {
      channel: "WEB"
    }
  }
]);
~~~

Stage **$project** không giữ field **channel**, nên ở stage sau **channel không còn tồn tại trong document trung gian**. Điều kiện **$match: {channel:"WEB"}** vì vậy không lọc được như mong muốn và có thể không trả document nào.

Viết hợp lý hơn:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      channel: "WEB"
    }
  },
  {
    $project: {
      customerId: 1,
      status: 1
    }
  }
]);
~~~

Trường hợp này cho thấy **thứ tự stage là một phần của semantics**, không chỉ quyết định hiệu năng.

### 6.2. Tên field thay đổi trong $group

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      orders: { $sum: 1 }
    }
  },
  {
    $sort: {
      status: 1
    }
  }
]);
~~~

Sau **$group**, key nhóm được lưu ở **_id**, còn field **status** gốc không còn. Do đó **$sort: {status:1}** không sắp theo trạng thái như người đọc có thể tưởng.

Sắp theo _id:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      orders: { $sum: 1 }
    }
  },
  {
    $sort: {
      _id: 1
    }
  }
]);
~~~

Hoặc đổi tên lại:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      orders: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: 0,
      status: "$_id",
      orders: 1
    }
  },
  {
    $sort: {
      status: 1
    }
  }
]);
~~~

### 6.3. $set không xóa field nên dễ dùng khi thử nghiệm

Nếu đang xây một pipeline nhiều bước, có thể tạm dùng **$set** để tạo field tính toán mà chưa bỏ field gốc:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      itemCount: {
        $size: "$items"
      }
    }
  },
  {
    $match: {
      itemCount: { $gt: 1 }
    }
  }
]);
~~~

Stage thứ hai **$match** thấy field **itemCount** vì stage đầu đã thêm nó. Sau khi hoàn thiện logic, có thể dùng **$project** ở cuối để thu nhỏ kết quả cần trả về client.

## 7. Đọc và viết aggregation expressions

### 7.1. Expression hằng số và field path

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      originalChannel: "$channel",
      literalChannel: "WEB",
      currentStatus: "$status"
    }
  }
]);
~~~

Trong ngữ cảnh expression:

- **"$channel"** lấy giá trị field channel từ document hiện tại.
- **"WEB"** là chuỗi ký tự hằng.
- **"$status"** lấy status từ document hiện tại.

Để phân biệt:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 0,
      a: "$status",
      b: "status"
    }
  }
]);
~~~

**a** là giá trị như PAID/PENDING; **b** luôn là chuỗi **"status"**.

### 7.2. Toán học với $add, $multiply, $divide

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      feeWithTax: {
        $multiply: [
          "$shippingFee",
          NumberDecimal("1.10")
        ]
      }
    }
  }
]);
~~~

Expression **$multiply** đánh giá **giá trị field shippingFee** nhân với một hằng số. Kết quả trả vào field mới **feeWithTax**.

Các expressions có thể **lồng nhau**:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      feePlusFive: {
        $add: [
          {
            $multiply: [
              "$shippingFee",
              NumberDecimal("1.10")
            ]
          },
          NumberDecimal("5.00")
        ]
      }
    }
  }
]);
~~~

MongoDB sẽ đánh giá biểu thức con rồi dùng kết quả cho biểu thức ngoài. Đây vẫn là **một $project stage**, không phải hai stage chỉ vì có hai phép tính.

### 7.3. Logic với $cond

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      paymentLabel: {
        $cond: [
          { $eq: ["$status", "PAID"] },
          "COMPLETED",
          "NOT_COMPLETED"
        ]
      }
    }
  }
]);
~~~

**$cond** là expression gồm:

1. Điều kiện;
2. Giá trị khi điều kiện true;
3. Giá trị khi điều kiện false.

Nó không loại document. Muốn chỉ lấy đơn PAID, dùng **$match**.

### 7.4. $ifNull xử lý null hoặc missing

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      channel: {
        $ifNull: [
          "$channel",
          "UNKNOWN"
        ]
      }
    }
  }
]);
~~~

**$ifNull** cho giá trị thay thế nếu expression đầu là null hoặc missing (và theo semantics của phiên bản tương ứng). Nó hữu ích khi dữ liệu có field tùy chọn.

Không nên tự điền default chỉ để lấp dữ liệu nếu **null có ý nghĩa nghiệp vụ khác missing**. Trước tiên xác định contract của field.

### 7.5. $concat và $toUpper xử lý chuỗi

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      displayKey: {
        $concat: [
          "$tenantId",
          "-",
          { $toUpper: "$channel" }
        ]
      }
    }
  }
]);
~~~

Với O101, **displayKey** là **"SHOP-A-WEB"**. Nếu channel có thể null/missing, cần xử lý trước vì các phép chuỗi có semantics về null và kiểu dữ liệu.

### 7.6. Expression kiểm tra kiểu và convert

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      dateType: {
        $type: "$createdAt"
      },
      createdYear: {
        $year: "$createdAt"
      }
    }
  }
]);
~~~

Ở đây **$type** và **$year** là expressions. **$year** cần dữ liệu ngày giờ phù hợp; nếu createdAt lưu string không hợp lệ, pipeline có thể lỗi. MongoDB không tự hiểu mọi string ngày tháng trong mọi expression.

## 8. $match dùng query predicate; $expr là cầu nối tới aggregation expression

Đây là một trong những chỗ dễ nhầm nhất.

### 8.1. Điều kiện $match thông thường

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: { $eq: "PAID" },
      tenantId: "SHOP-A"
    }
  }
]);
~~~

Trong **$match**, **$eq** là **query operator**: nó so sánh field status với giá trị **"PAID"**.

### 8.2. $eq ở dạng expression

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      isPaid: {
        $eq: ["$status", "PAID"]
      }
    }
  }
]);
~~~

Ở đây **$eq** là **aggregation expression** và nhận **mảng gồm hai toán hạng**. Một toán hạng là tham chiếu field, toán hạng còn lại là hằng số.

So sánh:

| Ngữ cảnh | Cú pháp | Ý nghĩa |
|---|---|---|
| Query predicate trong **$match** | **{status: {$eq:"PAID"}}** | Chọn document có status = PAID. |
| Expression trong **$project** | **{$eq:["$status","PAID"]}** | Tính boolean true/false. |

### 8.3. $expr cho phép expression trong $match

Giả sử collection khác có hai field số **paidAmount** và **expectedAmount**. Muốn lọc document mà hai field bằng nhau:

~~~javascript
db.invoices.aggregate([
  {
    $match: {
      $expr: {
        $eq: [
          "$paidAmount",
          "$expectedAmount"
        ]
      }
    }
  }
]);
~~~

**$expr** là **query operator** cho phép dùng aggregation expression để tạo điều kiện lọc. Trong trường hợp này **$eq** so sánh **hai field của cùng document**.

Nếu không cần biểu thức so sánh giữa các field mà chỉ lọc status = PAID, dạng **$match: {status:"PAID"}** thường ngắn gọn, dễ hiểu và thuận lợi cho query/index hơn. Không nên dùng **$expr** chỉ vì thấy cú pháp trông tổng quát.

### 8.4. Dấu $ ở tên field không phải phép toán

~~~javascript
{
  $project: {
    total: {
      $add: [
        "$subtotal",
        "$shippingFee"
      ]
    }
  }
}
~~~

Trong expression context, **"$subtotal"** là field path. Nhưng trong filter:

~~~javascript
{ status: "PAID" }
~~~

**status** là tên field của query predicate, còn **"PAID"** là literal. Cùng một chuỗi có thể được diễn giải khác nhau theo vị trí.

## 9. $sum có thể là accumulator hoặc expression

### 9.1. $sum trong $group: accumulator trên nhiều document

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  }
]);
~~~

Ở đây **$sum** cộng 1 cho **mỗi document đi vào nhóm**. Nó hoạt động như **accumulator**, gom giá trị qua nhiều document.

### 9.2. $sum trong $project/$set: expression trên dữ liệu của một document

~~~javascript
db.orders.aggregate([
  {
    $set: {
      quantities: {
        $map: {
          input: "$items",
          as: "line",
          in: "$$line.qty"
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      totalUnits: {
        $sum: "$quantities"
      }
    }
  }
]);
~~~

Trong **$project**, **$sum** ở dạng expression có thể tính tổng **các giá trị số trong một mảng** của **một document**. Với O101, quantities = [2,1], totalUnits = 3. Với O102, quantities = [1,3], totalUnits = 4.

Hai thao tác khác nhau:

~~~text
$sum trong $group:
  nhiều document -> 1 giá trị tổng của một nhóm

$sum trong $project:
  dữ liệu của một document -> 1 giá trị được tính
~~~

### 9.3. Một tổng từ mảng embedded objects dùng $map + $sum

Để tính subtotal của mỗi order mà **không unwind**, sử dụng:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      subtotal: {
        $sum: {
          $map: {
            input: "$items",
            as: "line",
            in: {
              $multiply: [
                "$$line.qty",
                "$$line.unitPrice"
              ]
            }
          }
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      subtotal: 1
    }
  },
  {
    $sort: {
      _id: 1
    }
  }
]);
~~~

Ví dụ giá trị subtotal:

| Đơn | Diễn giải | Subtotal |
|---|---|---:|
| O101 | 2 × 100 + 1 × 50 | 250 |
| O102 | 1 × 100 + 3 × 20 | 160 |
| O103 | 2 × 50 | 100 |
| O104 | 4 × 100 | 400 |
| O105 | 2 × 20 | 40 |
| O106 | 1 × 50 | 50 |
| O107 | Không có item | 0 |

Các con số trên mô tả giá trị, không biểu diễn đầy đủ wrapper BSON Decimal128. Trong các ví dụ giá được lưu bằng **NumberDecimal**, phép tính sẽ được thực thi theo quy tắc số của MongoDB; khi xuất JSON/Java DTO cần giữ type tương ứng.

**$map** và **$multiply** là expressions lồng bên trong **$sum expression**, tất cả nằm trong **$set stage**.

### 9.4. $sum trên các document sau $unwind

Cùng yêu cầu thống kê doanh thu theo SKU có thể được diễn đạt bằng **$unwind + $group**:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      unitsSold: {
        $sum: "$items.qty"
      },
      grossAmount: {
        $sum: {
          $multiply: [
            "$items.qty",
            "$items.unitPrice"
          ]
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Kết quả theo dữ liệu mẫu:

~~~text
SKU-A: unitsSold = 3, grossAmount = 300
SKU-B: unitsSold = 1, grossAmount = 50
SKU-C: unitsSold = 5, grossAmount = 100
~~~

Kết quả này **không tính shippingFee** vì doanh thu gộp theo item được tính riêng từ qty × unitPrice. Nếu nghiệp vụ cần phân bổ shippingFee theo SKU, phải định nghĩa quy tắc phân bổ chứ không tự cộng shippingFee vào mỗi dòng.

## 10. Biến trong expression: $, $$ và $$ROOT

### 10.1. Field path bằng một dấu $

~~~javascript
"$customerId"
"$items.sku"
"$shippingFee"
~~~

Trong expression context, ký hiệu **$fieldPath** lấy giá trị của field trên document hiện tại.

### 10.2. Biến trong expression bằng hai dấu $$

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      expensiveItems: {
        $filter: {
          input: "$items",
          as: "line",
          cond: {
            $gte: [
              "$$line.unitPrice",
              NumberDecimal("50.00")
            ]
          }
        }
      }
    }
  }
]);
~~~

Trong **$filter**, **as: "line"** đặt tên biến đại diện cho phần tử đang xét. **"$$line.unitPrice"** tham chiếu field unitPrice của biến line, khác với **"$items.unitPrice"**, vốn là field path dựa trên document hiện tại.

Các expressions khác cũng sử dụng biến như **$map**, **$let** và những cơ chế có biến do pipeline định nghĩa.

### 10.3. Biến hệ thống $$ROOT

**$$ROOT** thường chỉ document gốc tại **đầu vào của stage hiện tại**, sau những biến đổi đã xảy ra ở các stage trước.

Ví dụ giữ toàn bộ document trong group:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$customerId",
      orders: {
        $push: "$$ROOT"
      }
    }
  }
]);
~~~

Mỗi nhóm sẽ có **orders** là mảng document đã được chọn. Với tập dữ liệu lớn, **$push: "$$ROOT"** có thể tạo document group rất lớn, vượt giới hạn BSON 16 MiB. Chỉ giữ những field cần thiết khi gom mảng để tránh vượt giới hạn.

### 10.4. Biến hệ thống $$NOW

MongoDB có system variable **$$NOW** để tham chiếu thời gian hiện tại trong aggregation. Nó hữu ích khi tính tuổi document, điều kiện liên quan thời gian và báo cáo nhất quán trong một pipeline.

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      ageMilliseconds: {
        $subtract: [
          "$$NOW",
          "$createdAt"
        ]
      }
    }
  }
]);
~~~

Lưu ý **$subtract** giữa hai Date trả ra thời gian chênh lệch theo mili giây. Đừng coi **$$NOW** là biến JavaScript ở mongosh; nó được MongoDB diễn giải trong aggregation.

### 10.5. $literal khi cần giữ chuỗi bắt đầu bằng $

Trong expression context, **"$PAID"** bị hiểu như một field path. Nếu muốn trả nguyên văn chuỗi **"$PAID"**, dùng **$literal**:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      literalValue: {
        $literal: "$PAID"
      }
    }
  }
]);
~~~

Khi user input hoặc cấu hình có chuỗi bắt đầu bằng **$**, cần cẩn trọng để không vô tình biến literal thành một field/expression không mong muốn. Dùng query builder và validate đầu vào ở ứng dụng.

## 11. Một pipeline đầy đủ: từ orders tới báo cáo sản phẩm

Mục tiêu: thống kê các mặt hàng đã bán của **SHOP-A**, chỉ tính đơn **PAID**, tính tổng số lượng và tổng giá trị dòng hàng, sắp theo tổng giá trị giảm dần.

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  },
  {
    $unwind: "$items"
  },
  {
    $set: {
      lineAmount: {
        $multiply: [
          "$items.qty",
          "$items.unitPrice"
        ]
      }
    }
  },
  {
    $group: {
      _id: "$items.sku",
      unitsSold: {
        $sum: "$items.qty"
      },
      grossAmount: {
        $sum: "$lineAmount"
      },
      orderIds: {
        $addToSet: "$_id"
      }
    }
  },
  {
    $project: {
      _id: 0,
      sku: "$_id",
      unitsSold: 1,
      grossAmount: 1,
      distinctOrders: {
        $size: "$orderIds"
      }
    }
  },
  {
    $sort: {
      grossAmount: -1,
      sku: 1
    }
  }
]);
~~~

### 11.1. Stage 1: $match

Input: 7 orders.

Output: **4 orders** gồm O101, O102, O105, O107. O103 bị loại vì CANCELLED, O104 vì tenant SHOP-B, O106 vì PENDING.

### 11.2. Stage 2: $unwind

Input: 4 orders.

Output: **5 line documents**:

~~~text
O101 / SKU-A / qty 2 / unitPrice 100
O101 / SKU-B / qty 1 / unitPrice  50
O102 / SKU-A / qty 1 / unitPrice 100
O102 / SKU-C / qty 3 / unitPrice  20
O105 / SKU-C / qty 2 / unitPrice  20
~~~

O107 có items rỗng nên không tạo line document với **$unwind mặc định**.

### 11.3. Stage 3: $set

Input: 5 line documents.

Output: vẫn **5 line documents**, nhưng mỗi document có **lineAmount**:

~~~text
O101 / SKU-A / lineAmount 200
O101 / SKU-B / lineAmount  50
O102 / SKU-A / lineAmount 100
O102 / SKU-C / lineAmount  60
O105 / SKU-C / lineAmount  40
~~~

**$multiply là expression** đánh giá bên trong **$set stage**.

### 11.4. Stage 4: $group

Input: 5 line documents.

Output: **3 grouped documents** theo SKU.

~~~javascript
[
  {
    _id: "SKU-A",
    unitsSold: 3,
    grossAmount: NumberDecimal("300.00"),
    orderIds: ["O101", "O102"]
  },
  {
    _id: "SKU-B",
    unitsSold: 1,
    grossAmount: NumberDecimal("50.00"),
    orderIds: ["O101"]
  },
  {
    _id: "SKU-C",
    unitsSold: 5,
    grossAmount: NumberDecimal("100.00"),
    orderIds: ["O102", "O105"]
  }
]
~~~

**Lưu ý:** thứ tự phần tử trong **orderIds** do **$addToSet** tạo ra không được bảo đảm. Đoạn trên chỉ minh họa các giá trị có trong tập, không cam kết thứ tự output thực tế.

### 11.5. Stage 5: $project

Input: 3 grouped documents.

Output: 3 documents với **sku** được đổi tên từ **_id**, thêm **distinctOrders** = kích thước tập orderIds, bỏ **orderIds** và **_id**.

### 11.6. Stage 6: $sort

Input: 3 documents.

Output:

~~~javascript
[
  {
    sku: "SKU-A",
    unitsSold: 3,
    grossAmount: NumberDecimal("300.00"),
    distinctOrders: 2
  },
  {
    sku: "SKU-C",
    unitsSold: 5,
    grossAmount: NumberDecimal("100.00"),
    distinctOrders: 2
  },
  {
    sku: "SKU-B",
    unitsSold: 1,
    grossAmount: NumberDecimal("50.00"),
    distinctOrders: 1
  }
]
~~~

Đây là ví dụ điển hình của hai dòng biến đổi song song:

~~~text
CARDINALITY:
  7 -> 4 -> 5 -> 5 -> 3 -> 3 -> 3

SHAPE:
  Order
    -> Order đã lọc
    -> Order + một item
    -> Order + một item + lineAmount
    -> Summary theo SKU
    -> Report DTO
    -> Report DTO đã sắp thứ tự
~~~

Nếu chỉ ghi nhớ một ý khi thiết kế aggregation, hãy theo dõi **số document** và **các field còn tồn tại** sau mỗi stage.

## 12. Accumulator và expression trong $group

### 12.1. $group sử dụng grouping key và accumulator

~~~javascript
{
  $group: {
    _id: "$customerId",
    count: { $sum: 1 },
    totalUnits: { $sum: "$items.qty" }
  }
}
~~~

Ở đây **$group** phân loại document theo customerId và các accumulator tính thống kê cho mỗi nhóm.

Nếu **items** là mảng object chưa unwind, **"$items.qty"** có thể mang giá trị mảng/đường dẫn xuyên mảng. **$sum accumulator trong $group** không tự duyệt sâu mỗi phần tử như bài toán tổng số lượng từng dòng, và các dạng array operand có semantics riêng. Muốn tính theo từng line, dùng **$unwind** trước hoặc tính **per-document sum bằng $map/$sum expression** trước khi group.

Không nên chỉ thay cú pháp mà không xác định **đơn vị đang được cộng**: một order, một dòng hàng, một khách hàng hay một group.

### 12.2. $avg, $min, $max, $push, $addToSet

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      totalOrders: { $sum: 1 },
      firstCreatedAt: { $min: "$createdAt" },
      lastCreatedAt: { $max: "$createdAt" },
      customerIds: { $addToSet: "$customerId" }
    }
  }
]);
~~~

Ý nghĩa:

- **$sum:** tổng số document trong nhóm.
- **$min:** giá trị nhỏ nhất.
- **$max:** giá trị lớn nhất.
- **$addToSet:** tập các giá trị phân biệt, **không bảo đảm thứ tự**.
- **$push:** gom các giá trị vào mảng; thứ tự phụ thuộc luồng đầu vào nếu cần dựa trên thứ tự.

Nếu cần kết quả có thứ tự xác định, chủ động thiết kế **$sort** ở vị trí phù hợp và hiểu hành vi accumulator. Không dựa vào thứ tự ngẫu nhiên của kết quả nhóm.

### 12.3. $group với _id: null

~~~javascript
db.orders.aggregate([
  {
    $match: { tenantId: "SHOP-A" }
  },
  {
    $group: {
      _id: null,
      totalOrders: { $sum: 1 }
    }
  }
]);
~~~

**_id: null** nghĩa là gom tất cả document đầu vào vào **một nhóm chung**, không phải nhóm theo một field tên null. Nếu đầu vào không có document, kết quả phụ thuộc stage/accumulators và thường không tạo group document.

## 13. $lookup, $facet và stage thay đổi hình dạng đặc biệt

### 13.1. $lookup thường thêm một mảng kết quả join

Giả sử collection **customers**:

~~~javascript
db.customers.insertMany([
  { _id: "C01", displayName: "Alice" },
  { _id: "C02", displayName: "Bob" },
  { _id: "C03", displayName: "Charlie" },
  { _id: "C04", displayName: "Dana" }
]);
~~~

Join thông tin khách hàng vào orders:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  },
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
      customerId: 1,
      customerInfo: 1
    }
  }
]);
~~~

**$lookup** ở dạng cơ bản đưa các match vào **customerInfo** là mảng. Nếu mỗi order match một customer, mảng có một phần tử. Nếu không match, mảng thường rỗng.

~~~javascript
{
  _id: "O101",
  customerId: "C01",
  customerInfo: [
    { _id: "C01", displayName: "Alice" }
  ]
}
~~~

Một **$lookup** thường không làm tăng số document của luồng bên ngoài vì nó đính kèm mảng vào từng document đầu vào. Nếu sau đó có **$unwind: "$customerInfo"**, số document có thể thay đổi theo số phần tử join.

### 13.2. $facet tạo nhiều nhánh xử lý song song trên cùng luồng đầu vào

Ví dụ muốn trả cả thống kê theo status và số đơn tổng cộng:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A"
    }
  },
  {
    $facet: {
      byStatus: [
        {
          $group: {
            _id: "$status",
            count: { $sum: 1 }
          }
        }
      ],
      totals: [
        {
          $count: "totalOrders"
        }
      ]
    }
  }
]);
~~~

**$facet** là **stage**, còn **byStatus** và **totals** là tên các nhánh. Mỗi nhánh chứa **một sub-pipeline**, tức một mảng các stage riêng.

Kết quả có hình dạng:

~~~javascript
[
  {
    byStatus: [
      { _id: "PAID", count: 4 },
      { _id: "CANCELLED", count: 1 },
      { _id: "PENDING", count: 1 }
    ],
    totals: [
      { totalOrders: 6 }
    ]
  }
]
~~~

Thứ tự các phần tử trong **byStatus** không được bảo đảm khi thiếu sort. **$facet** không phải expression, dù nó chứa các sub-pipelines có stages và expressions lồng bên trong.

**Lưu ý tài nguyên:** $facet có giới hạn bộ nhớ và kích thước document đầu ra; không cho rằng **allowDiskUse** giúp $facet có thể tạo một document kết quả vô hạn.

### 13.3. $replaceRoot hoặc $replaceWith thay document hiện tại

Giả sử sau **$lookup**, mỗi document có trường **customerInfo** chứa object. Nếu muốn thay toàn bộ document hiện tại bằng một object khác, có thể dùng **$replaceRoot** hoặc **$replaceWith** với expression trả về document hợp lệ.

Các stage này thay đổi **shape** rất mạnh. Nếu expression trả về null hoặc một giá trị không phải document trong trường hợp không được hỗ trợ, pipeline có thể lỗi. Vì vậy không nên đặt chúng vào pipeline chỉ để đổi tên một field; **$project/$set** thường rõ ràng hơn.

## 14. Stage có thể stream, block hoặc làm tăng khối lượng trung gian

Về mặt tư duy, pipeline là luồng document qua nhiều stage. Nhưng **không phải mọi stage đều xử lý mỗi document và phát kết quả ngay lập tức**.

### 14.1. Streaming-like stages

Những stage như **$match** hoặc **$project** có thể xử lý tuần tự một document rồi cho ra document tương ứng, tùy kế hoạch thực thi và tối ưu hóa.

~~~text
Input Doc 1 -> $match -> Output Doc 1 / loại
Input Doc 2 -> $match -> Output Doc 2 / loại
...
~~~

### 14.2. Blocking stages

Những stage như **$group** và **$sort** thường phải gom hoặc duy trì trạng thái của nhiều document trước khi có thể trả kết quả cuối cùng:

~~~text
Input: rất nhiều document
     |
     v
$group xây các nhóm / accumulators
     |
     v
Output: các nhóm thống kê
~~~

Điều này có thể tiêu tốn bộ nhớ và thời gian hơn các stage lọc đơn giản. **$sort** có thể hưởng lợi từ index hoặc tối ưu hóa với **$limit** trong những điều kiện thích hợp, nên hành vi thực tế do query planner quyết định.

### 14.3. $unwind có thể gây bùng nổ số document

Nếu mỗi order có 1.000 items và có 100.000 orders, **$unwind** có thể tạo ra tới **100 triệu line documents** trung gian nếu tất cả mảng đều đủ phần tử và không bị lọc.

Không phải MongoDB sẽ materialize toàn bộ chúng đồng thời ở mọi trường hợp, nhưng khối lượng xử lý có thể tăng rất lớn.

Để giảm chi phí:

1. **$match sớm** trên các điều kiện nguồn có index.
2. Chỉ unwind khi cần xử lý **theo phần tử**.
3. Dùng **$map/$filter/$sum** trên mảng trong từng document nếu yêu cầu có thể giải quyết mà không unwind.
4. Tránh tạo mảng đầu ra quá lớn bằng **$push: "$$ROOT"** hoặc **$facet**.
5. Phân biệt đúng đơn vị thống kê để không đếm lại một order nhiều lần sau unwind.

### 14.4. Giới hạn bộ nhớ và allowDiskUse

Một số stage có thể cần dùng nhiều bộ nhớ. MongoDB có giới hạn khoảng **100 MB** cho những stage có yêu cầu bộ nhớ đáng kể trong các phiên bản/ngữ cảnh thông dụng; một số stage có thể **ghi dữ liệu tạm ra đĩa** nếu được phép.

Trong mongosh:

~~~javascript
db.orders.aggregate(
  [
    { $match: { tenantId: "SHOP-A" } },
    { $group: { _id: "$customerId", count: { $sum: 1 } } },
    { $sort: { count: -1 } }
  ],
  {
    allowDiskUse: true
  }
);
~~~

**allowDiskUse: true** cho phép các stage có hỗ trợ sử dụng tệp tạm khi cần, thay vì bị giới hạn hoàn toàn trong RAM. Từ MongoDB 6.0, server có thêm cấu hình **allowDiskUseByDefault** ảnh hưởng hành vi mặc định trong các trường hợp tương ứng.

Nhưng:

- Không phải mọi stage đều có thể spill to disk; **$facet** có giới hạn riêng.
- **allowDiskUse** không bỏ giới hạn **16 MiB cho một BSON document đầu ra**.
- Tệp tạm tiêu tốn disk I/O và dung lượng.
- Một pipeline tạo output quá lớn vẫn có thể thất bại.
- Quy tắc bộ nhớ khác nhau theo stage và phiên bản, nên cần kiểm tra tài liệu server đang sử dụng.

### 14.5. Giới hạn số stage

MongoDB đặt giới hạn số stage trong một pipeline, với giá trị thông dụng **1.000 stages**. Đừng chia một tính toán đơn giản thành hàng nghìn stage hoặc tạo pipeline không giới hạn từ input của user.

Khi pipeline quá dài, cần xem lại mô hình dữ liệu, biểu thức tính toán, số lượng sub-pipelines và kiến trúc xử lý thay vì chỉ cố tăng một ngưỡng cấu hình.

## 15. Thứ tự stage và tối ưu hóa

### 15.1. Lọc sớm để giảm khối lượng dữ liệu

Pipeline:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "SHOP-A", status: "PAID" } },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      totalQty: { $sum: "$items.qty" }
    }
  }
]);
~~~

lọc còn bốn orders trước khi unwind. Nếu **$unwind** xảy ra trước rồi mới lọc, database có thể phải xử lý thêm những items của orders bị loại, dù kết quả logic vẫn có thể giống trong một số trường hợp.

### 15.2. Không được hoán đổi tùy tiện mọi stage

Ví dụ:

~~~javascript
[
  { $sort: { createdAt: -1 } },
  { $limit: 10 }
]
~~~

nghĩa là “10 document mới nhất” theo sort.

Trong khi:

~~~javascript
[
  { $limit: 10 },
  { $sort: { createdAt: -1 } }
]
~~~

nghĩa là “lấy tối đa 10 document từ luồng hiện tại rồi mới sort chúng”. Hai pipeline có thể trả kết quả khác nhau.

Tương tự, **$match** theo field tính toán trong **$set** không thể tùy tiện chuyển lên trước **$set**, vì field đó chưa tồn tại ở document nguồn.

### 15.3. MongoDB có query optimizer

MongoDB có thể tự sắp xếp lại hoặc kết hợp các bước trong một số điều kiện nhằm tối ưu hiệu năng mà giữ nguyên semantics; ví dụ đẩy một số điều kiện **$match** lên trước **$project/$set**, kết hợp **$sort** với **$limit** trong một số trường hợp.

Do vậy:

- **Mảng stage bạn viết** thể hiện logic mong muốn.
- **Execution plan thực tế** có thể được optimizer biến đổi.
- Không suy ra chính xác số lần materialize dữ liệu chỉ từ cú pháp mảng stage.
- Dùng **explain()** và số liệu thực tế để hiểu cách MongoDB thực thi.

Đừng dựa vào một thứ tự thực thi nội bộ không được đảm bảo trong tài liệu để viết logic nghiệp vụ phụ thuộc side effects.

## 16. Dùng explain để đọc execution plan của pipeline

Ví dụ:

~~~javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$customerId",
      count: { $sum: 1 }
    }
  },
  {
    $sort: {
      count: -1
    }
  }
]);
~~~

**explain** giúp quan sát query plan và các chỉ số thực thi. Những thông tin quan trọng có thể gồm:

- **COLLSCAN / IXSCAN** hoặc stage thực thi tương ứng: nguồn dữ liệu được tìm như thế nào?
- **totalDocsExamined:** số document nguồn đã được đọc/xem xét.
- **totalKeysExamined:** số index key đã được xem xét.
- **nReturned:** số document trả về trong phạm vi của bộ đếm tương ứng.
- **Các pipeline stages:** xử lý group, sort, unwind, execution timing và hoạt động spill nếu được cung cấp.

Tùy phiên bản MongoDB và execution engine, cấu trúc response của explain có thể khác nhau. Không viết công cụ cố định giả định mọi phiên bản đều có một đường dẫn JSON duy nhất cho các metric.

### 16.1. Index giúp những stage nào?

Trong nhiều trường hợp:

- **$match đầu pipeline** có thể hưởng lợi từ index theo field lọc.
- **$sort** có thể hưởng lợi từ index nếu thứ tự stage, sort pattern và query phù hợp.
- **$group** có các tối ưu đặc biệt theo index trong một số query, nhưng không mặc định mọi group đều được index tăng tốc trực tiếp.
- **$unwind** thường làm nhiều document trung gian và không “tự tạo index” trên kết quả.

Ví dụ tạo index phục vụ tìm orders theo tenant/status:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1 },
  { name: "ix_tenant_status" }
);
~~~

Sau đó đo lại explain trên dataset đại diện. Với collection chỉ có bảy document trong lab, query planner có thể chọn scan vì chi phí thấp; không đánh giá một index production chỉ từ ví dụ nhỏ.

## 17. Aggregation trong MongoDB Java Sync Driver

MongoDB Java Sync Driver cho phép xây pipeline từ **List<Bson>**, sử dụng builder như **Aggregates**, **Filters**, **Accumulators** và **Sorts**.

### 17.1. Ví dụ tìm và group theo SKU

~~~java
import com.mongodb.client.AggregateIterable;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Accumulators;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.List;

public final class OrdersAggregationExample {
    public static void run(MongoDatabase database) {
        MongoCollection<Document> orders =
                database.getCollection("orders");

        List<Bson> pipeline = List.of(
                Aggregates.match(
                        Filters.and(
                                Filters.eq("tenantId", "SHOP-A"),
                                Filters.eq("status", "PAID")
                        )
                ),
                Aggregates.unwind("$items"),
                Aggregates.group(
                        "$items.sku",
                        Accumulators.sum("unitsSold", "$items.qty")
                ),
                Aggregates.sort(
                        Sorts.ascending("_id")
                )
        );

        AggregateIterable<Document> results =
                orders.aggregate(pipeline);

        for (Document row : results) {
            System.out.println(row.toJson());
        }
    }
}
~~~

Đoạn code có **bốn stages**:

1. **Aggregates.match(...)** xây **$match stage**.
2. **Aggregates.unwind("$items")** xây **$unwind stage**.
3. **Aggregates.group(...)** xây **$group stage**, bên trong dùng accumulator **Accumulators.sum**.
4. **Aggregates.sort(...)** xây **$sort stage**.

**Filters.eq** là builder dành cho query predicate, còn **Accumulators.sum** biểu diễn accumulator trong group. Việc có các Java builders khác nhau giúp làm rõ một phần sự khác biệt stage/expression.

### 17.2. Expression trong Java bằng BSON Document

Một biểu thức lồng nhau có thể được dựng thủ công bằng **Document**:

~~~java
import com.mongodb.client.model.Aggregates;
import org.bson.Document;
import org.bson.conversions.Bson;
import java.util.List;

Bson calculatedField = Aggregates.addFields(
        new org.bson.Field<>(
                "lineAmount",
                new Document(
                        "$multiply",
                        List.of("$items.qty", "$items.unitPrice")
                )
        )
);
~~~

**Aggregates.addFields** xây stage **$addFields**, trong khi **new Document("$multiply", ...)** thể hiện expression được đặt vào giá trị field **lineAmount**.

Trong hệ thống production, builder có thể được đóng gói thành reusable functions, nhưng cần phân biệt rõ:

~~~text
List<Bson>       -> danh sách STAGES
Bson stage       -> một stage
Document expr    -> expression dùng BÊN TRONG stage
~~~

### 17.3. Đọc cursor thay vì materialize kết quả vô hạn

~~~java
for (Document row : orders.aggregate(pipeline)) {
    processRow(row);
}
~~~

Ứng dụng có thể xử lý từng kết quả từ cursor. Không nên mặc định gọi **into(new ArrayList<>())** rồi giữ toàn bộ hàng triệu kết quả trong RAM nếu bài toán có thể stream.

MongoDB aggregation cursor không có nghĩa mọi stage đều stream ngay từ đầu: các stage như **$sort/$group** có thể vẫn phải xử lý nhiều dữ liệu trước khi trả kết quả.

### 17.4. allowDiskUse với Java driver

~~~java
orders.aggregate(pipeline)
        .allowDiskUse(true)
        .forEach(document -> System.out.println(document.toJson()));
~~~

Tùy phiên bản driver/server, API cho phép điều chỉnh việc spill ra đĩa trong các stage được hỗ trợ. Không dùng allowDiskUse như giải pháp mặc định cho pipeline không giới hạn đầu ra.

## 18. Aggregation trong Spring Data MongoDB

Spring Data cung cấp **Aggregation**, **AggregationOperation**, **AggregationResults** và các builders cho nhiều stage. Mục tiêu là biểu diễn pipeline MongoDB trong Java với hỗ trợ mapping entity.

### 18.1. Ví dụ match, unwind, group, sort

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;
import org.bson.Document;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;
import org.springframework.data.domain.Sort.Direction;

public final class OrderReportService {
    private final MongoTemplate mongoTemplate;

    public OrderReportService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public void printUnitsBySku() {
        Aggregation pipeline = newAggregation(
                match(
                        Criteria.where("tenantId").is("SHOP-A")
                                .and("status").is("PAID")
                ),
                unwind("items"),
                group("items.sku")
                        .sum("items.qty").as("unitsSold"),
                sort(Direction.ASC, "_id")
        );

        AggregationResults<Document> result =
                mongoTemplate.aggregate(
                        pipeline,
                        "orders",
                        Document.class
                );

        for (Document row : result.getMappedResults()) {
            System.out.println(row.toJson());
        }
    }
}
~~~

Các builder **match**, **unwind**, **group**, **sort** tạo **stages**. **Criteria** mô tả query predicate trong match, còn **sum(...).as(...)** cấu hình accumulator trong group.

Ví dụ gọi **getMappedResults()** để đơn giản hóa minh họa; với kết quả lớn, nên cân nhắc API streaming/cursor phù hợp thay vì giữ mọi document trong một List.

### 18.2. Stage $project với expression trong Spring Data

~~~java
Aggregation pipeline = newAggregation(
        project("customerId", "status")
                .and("shippingFee")
                .as("fee")
);
~~~

Đây là phép **project/rename field**, chưa có tính toán số học. Để dùng expressions phức tạp, Spring Data có nhiều builder theo nhóm toán tử và hỗ trợ các dạng expression tương ứng. Khi dùng những expression MongoDB mới chưa được builder version hiện tại hỗ trợ, có thể cân nhắc **custom AggregationOperation** với BSON Document.

### 18.3. Mapping và tên field sau từng stage

Trong Spring Data, tên property Java có thể ánh xạ sang tên BSON khác qua annotation **@Field**. Nhưng sau **$group**, **$project** hay **$replaceRoot**, document đầu ra không còn hình dạng entity gốc.

Do đó:

- Chọn đúng **input collection/entity mapping**.
- Xác định field path ở mỗi stage sau các phép đổi tên.
- Dùng **DTO kết quả** khi output là báo cáo chứ không phải entity ban đầu.
- Chú ý **_id** sau group thường chứa grouping key, không phải ID của order.
- Kiểm tra type Decimal128 và các phép chuyển đổi vào Java **BigDecimal** hoặc kiểu tương ứng.

### 18.4. Không trộn nhầm builder query và expression

**Criteria.where("status").is("PAID")** mô tả predicate. Nó không phải expression boolean trả về một field **isPaid** trong project. Muốn tính isPaid, cần dùng **aggregation comparison expression** hoặc custom expression phù hợp.

Tư duy giống mongosh: **query predicate** để lọc, **expression** để tính, **stage** để điều phối luồng.

## 19. Aggregation đọc dữ liệu và aggregation ghi dữ liệu

### 19.1. Pipeline đọc thông thường không sửa collection nguồn

~~~javascript
db.orders.aggregate([
  {
    $set: {
      summaryFlag: true
    }
  }
]);
~~~

Pipeline này **chỉ tạo field summaryFlag trong document kết quả**, không lưu field đó vào từng order trong collection.

Tên **$set** có thể gây nhầm bởi MongoDB cũng có **$set update operator**:

~~~javascript
db.orders.updateOne(
  { _id: "O101" },
  {
    $set: {
      summaryFlag: true
    }
  }
);
~~~

Lệnh **updateOne** thực sự ghi thay đổi vào collection nếu match và hợp lệ.

### 19.2. Update bằng aggregation pipeline

MongoDB cho phép một số update operations dùng **aggregation pipeline** làm phần update. Ví dụ:

~~~javascript
db.orders.updateOne(
  { _id: "O101" },
  [
    {
      $set: {
        itemCount: {
          $size: "$items"
        }
      }
    }
  ]
);
~~~

Trong ví dụ này, **$set là aggregation stage được phép trong update pipeline**, nhưng vì toàn bộ pipeline nằm trong **updateOne()**, kết quả được ghi lại vào document phù hợp.

**Quan trọng:** update pipeline chỉ hỗ trợ **một tập con các stages**, ví dụ **$set/$addFields**, **$project/$unset** và **$replaceRoot/$replaceWith** theo tài liệu. Không thể đưa bất kỳ stage đọc nào như **$group** hay **$lookup** vào update pipeline và mong MongoDB chấp nhận.

### 19.3. $out và $merge ghi kết quả pipeline

Aggregation Framework có **$out** và **$merge** để ghi kết quả vào collection đích theo quy tắc riêng. Chúng là **pipeline stages**, không phải expressions.

Sự khác nhau ở mức khái niệm:

- **$out:** ghi kết quả pipeline vào collection đích theo semantics của stage và phiên bản/topology.
- **$merge:** hợp nhất kết quả với collection đích, có cấu hình xử lý match/not match.

Các stage này có tác dụng ghi, có ràng buộc về vị trí trong pipeline và cách chạy. Không nên dùng tùy tiện trong bài thực hành vì có thể ảnh hưởng dữ liệu đích. Một pipeline chỉ chứa **$match/$project/$group** không tự ghi tài liệu thống kê vào collection mới.

## 20. Dùng pipeline cho báo cáo phân trang và nhiều kết quả

### 20.1. Phân trang với sort, skip, limit

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A"
    }
  },
  {
    $sort: {
      createdAt: -1,
      _id: 1
    }
  },
  { $skip: 2 },
  { $limit: 2 },
  {
    $project: {
      _id: 1,
      createdAt: 1,
      status: 1
    }
  }
]);
~~~

Với tập lớn, **skip sâu** có thể đắt vì database cần bỏ qua nhiều kết quả. Nếu có thể, cân nhắc **keyset/range pagination** theo những field có thứ tự và index phù hợp.

### 20.2. Facet cho dữ liệu trang và tổng số

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A"
    }
  },
  {
    $facet: {
      page: [
        { $sort: { createdAt: -1, _id: 1 } },
        { $skip: 0 },
        { $limit: 3 },
        { $project: { _id: 1, status: 1, createdAt: 1 } }
      ],
      totals: [
        { $count: "count" }
      ]
    }
  }
]);
~~~

Kết quả là **một document** có hai field **page** và **totals**, mỗi field chứa một array. Đây là ví dụ sub-pipelines của $facet, có thể thuận tiện cho một API trả cả dữ liệu trang và tổng số.

Tuy nhiên cần kiểm soát:

- giới hạn bộ nhớ $facet;
- kích thước document đầu ra 16 MiB;
- tác động của sort và skip;
- query có index thích hợp trước $facet;
- consistency/độ trễ theo yêu cầu của API.

Không mặc định $facet nhanh hơn hai query riêng trong mọi workload.

## 21. Những lỗi tư duy và cú pháp thường gặp

### 21.1. Đặt expression trực tiếp làm stage

~~~javascript
// Sai:
db.orders.aggregate([
  { $multiply: ["$qty", "$price"] }
]);
~~~

**$multiply** chỉ là expression. Đặt nó trong **$project/$set** hoặc stage có vị trí expression phù hợp.

### 21.2. Đặt $match như biểu thức trả boolean

~~~javascript
// Sai:
{
  $project: {
    isPaid: {
      $match: { status: "PAID" }
    }
  }
}
~~~

Tính boolean bằng **$eq** hoặc **$cond**. Lọc document bằng **$match stage**.

### 21.3. Nhầm cú pháp $gt query và $gt expression

~~~javascript
// Predicate trong $match:
{ $match: { qty: { $gt: 5 } } }

// Expression trong $project:
{ $project: { aboveFive: { $gt: ["$qty", 5] } } }
~~~

Một bên nhận giá trị so sánh như operator của field, bên kia nhận hai toán hạng trong array.

### 21.4. Dùng field đã bị $project xóa

~~~javascript
[
  { $project: { status: 1 } },
  { $match: { tenantId: "SHOP-A" } }
]
~~~

Nếu tenantId không được giữ sau project, stage match không còn thấy giá trị đó. Đặt match trước project hoặc giữ tenantId cho tới khi dùng xong.

### 21.5. Đếm order sau khi unwind items

~~~javascript
[
  { $unwind: "$items" },
  { $count: "orders" }
]
~~~

Pipeline này đếm **line documents**, không phải số orders ban đầu. Muốn đếm orders, dùng **$count trước unwind**, hoặc group theo order ID / **$addToSet** và đo distinct đúng semantics.

### 21.6. Nghĩ $group giữ tất cả field nguồn

~~~javascript
{
  $group: {
    _id: "$customerId",
    totalOrders: { $sum: 1 }
  }
}
~~~

Sau group, output chỉ chứa **_id** và **totalOrders**; không tự giữ **status**, **createdAt** hoặc **items** của document nguồn.

### 21.7. Dựa vào thứ tự kết quả $group

**$group không bảo đảm thứ tự đầu ra**. Muốn sắp xếp theo key hoặc tổng, thêm **$sort** sau group.

### 21.8. Nghĩ $unwind chỉ biến đổi field

**$unwind** có thể làm một document thành nhiều document hoặc loại document có array rỗng. Nó thay đổi **cardinality**, không chỉ shape.

### 21.9. Sử dụng $$line bên ngoài phạm vi biến

Biến được khai báo bởi **$map/$filter/$let** chỉ có hiệu lực trong phạm vi expression tương ứng. Không dùng **"$$line.qty"** ở một expression khác nếu không có biến **line** thích hợp.

### 21.10. Tưởng $set stage tự cập nhật database

Trong **aggregate()**, $set chỉ thay đổi document trung gian. Nếu muốn ghi, dùng **updateOne/updateMany** với update hợp lệ hoặc các output stages có chủ đích.

### 21.11. Cho user gửi pipeline tùy ý

API báo cáo không nên nhận trực tiếp một mảng stage từ client chưa được kiểm soát. Nó có thể gây query quá tốn tài nguyên hoặc đưa vào stage ghi dữ liệu nếu quyền cho phép. Hãy xác minh field, operators, giới hạn kết quả, timeout và quyền truy cập.

### 21.12. Đọc aggregation cursor như một List có sẵn

Kết quả aggregation thường được trả qua cursor. Ứng dụng nên chọn cách duyệt phù hợp; không đưa hàng triệu document vào RAM nếu có thể xử lý từng batch kết quả.

## 22. Bài thực hành từng bước

### Bài 1 — Quan sát stage lọc

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "PAID"
    }
  }
]);
~~~

Ghi lại số document còn lại và danh sách _id. Vì sao O103, O104, O106 bị loại?

### Bài 2 — Thêm một expression tính số lượng item

~~~javascript
db.orders.aggregate([
  {
    $set: {
      itemCount: {
        $size: "$items"
      }
    }
  },
  {
    $project: {
      _id: 1,
      itemCount: 1
    }
  },
  {
    $sort: {
      _id: 1
    }
  }
]);
~~~

Trả lời: có bao nhiêu stage? Có bao nhiêu expressions? Stage nào giữ nguyên số document và stage nào thay shape?

### Bài 3 — Thay $set bằng $project

Viết lại ví dụ sao cho chỉ trả **_id**, **customerId** và **itemCount**. Giải thích vì sao field **items** không còn có mặt ở kết quả.

### Bài 4 — Đếm orders trước và sau unwind

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "SHOP-A", status: "PAID" } },
  { $count: "orders" }
]);
~~~

So với:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "SHOP-A", status: "PAID" } },
  { $unwind: "$items" },
  { $count: "lines" }
]);
~~~

Kết quả lần lượt là **4 orders** và **5 lines**. Hãy giải thích khác biệt bằng một sơ đồ cardinality.

### Bài 5 — Tính subtotal cho từng order không unwind

Sử dụng **$map + $multiply + $sum** trong **$set**, sau đó **$project** để trả _id/subtotal. Với O101 dự kiến subtotal 250; O107 có items rỗng nên subtotal 0.

### Bài 6 — Thống kê số lượng theo SKU

Viết pipeline gồm:

1. **$match:** SHOP-A, PAID;
2. **$unwind:** items;
3. **$group:** theo items.sku và cộng qty;
4. **$sort:** theo _id.

Đối chiếu kết quả SKU-A = 3, SKU-B = 1, SKU-C = 5.

### Bài 7 — Phân biệt predicate và expression

Viết:

- Một **$match** chỉ lấy đơn PAID theo query predicate;
- Một **$project** tạo field **isPaid** bằng expression **$eq**;
- Một **$match dùng $expr** so sánh hai field số của cùng một document giả định.

Giải thích sự khác biệt về shape và cardinality.

### Bài 8 — Phân tích lỗi thứ tự stage

Với pipeline:

~~~javascript
[
  { $project: { customerId: 1 } },
  { $match: { status: "PAID" } }
]
~~~

Xác định lỗi logic, sửa lại và giải thích stage nào được phép di chuyển lên trước nếu vẫn giữ nguyên semantics.

### Bài 9 — Truy vấn nhiều nhánh bằng $facet

Trên orders của SHOP-A, viết **$facet** trả:

- **byStatus:** thống kê số orders theo trạng thái;
- **totals:** tổng số orders;
- **recent:** hai orders mới nhất theo createdAt/_id.

Kết quả của $facet là một document hay nhiều document? Mỗi nhánh trả kiểu dữ liệu gì?

### Bài 10 — Tìm vấn đề hiệu năng

Giả sử có một triệu orders, mỗi order có trung bình 50 items. Một pipeline bắt đầu bằng **$unwind** toàn bộ rồi mới **$match tenantId/status**.

Hãy đề xuất thứ tự khác và giải thích vì sao có thể giảm số line documents phải xử lý. Sau đó nêu cách dùng **explain** và index để đánh giá.

## 23. Câu hỏi ôn tập

1. **Stage** và **expression** khác nhau ở đơn vị đầu vào/đầu ra và vị trí cú pháp như thế nào?
2. Vì sao **$add** không thể đặt trực tiếp như một phần tử stage trong **aggregate([...])**?
3. **$match** khác **$project** ở tác động tới số lượng document và field ra sao?
4. Khi nào nên dùng **$set** thay vì **$project**?
5. Sau **$unwind** của một mảng 5 phần tử, một document nguồn thường trở thành bao nhiêu document trung gian?
6. Vì sao **$unwind** mặc định loại order có items rỗng?
7. **$group** thay đổi **_id** và những field còn tồn tại như thế nào?
8. **$sum** bên trong **$group** khác với **$sum** expression trong **$project** ra sao?
9. Sự khác nhau giữa **$gt** query operator và **$gt** aggregation expression là gì?
10. **$expr** dùng khi nào trong **$match**?
11. Ký hiệu **"$status"** khác **"status"** ở vị trí expression thế nào?
12. **$$line** trong **$map** được định nghĩa ở đâu và có hiệu lực trong phạm vi nào?
13. **$$ROOT** trong group giúp gì, và tại sao **$push: "$$ROOT"** có thể gây vấn đề?
14. Tại sao không được tùy tiện đổi chỗ **$sort** và **$limit**?
15. Một **$lookup** thông thường tạo ra field với kiểu gì? Khi nào cardinality tăng?
16. **$facet** gồm những thành phần nào là sub-pipeline và thành phần nào là expression?
17. Nếu một pipeline có **$set stage**, collection nguồn có bị thay đổi không?
18. **allowDiskUse** có loại bỏ giới hạn 16 MiB cho document kết quả không?
19. Tại sao **aggregation cursor** không đồng nghĩa mọi stage đều phát kết quả ngay?
20. Làm thế nào để quan sát MongoDB có sử dụng index ở đầu aggregation pipeline hay không?

## 24. Tóm lược mô hình tư duy

Một pipeline MongoDB là **chuỗi stages**, mỗi stage nhận và chuyển một luồng document:

~~~text
db.collection.aggregate([
  { $stage1: ... },
  { $stage2: ... },
  { $stage3: ... }
])
~~~

Trong các stage, MongoDB dùng expressions để tính giá trị:

~~~text
STAGE:  $project
    |
    +-- FIELD:  total
           |
           +-- EXPRESSION: $add
                  |
                  +-- FIELD PATH: "$subtotal"
                  +-- FIELD PATH: "$shippingFee"
~~~

Ba câu hỏi nên hỏi ở từng bước:

1. **Số document thay đổi thế nào?** Lọc bớt, giữ nguyên, nhân lên, hay gom nhóm?
2. **Shape của mỗi document thay đổi thế nào?** Field nào còn, field nào mới, field nào đã được đổi tên?
3. **Từ khóa ở đây là stage hay expression?** Nó điều khiển luồng document hay chỉ tính một giá trị bên trong stage?

Khi đã phân biệt rõ ba câu hỏi, những pipeline phức tạp gồm **$match**, **$project**, **$unwind**, **$group**, **$lookup**, **$facet** và expressions lồng nhau sẽ dễ đọc và dễ kiểm soát hơn.

### Tài liệu MongoDB và Java để đọc tiếp

- [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) — mô hình luồng xử lý và tối ưu hóa.
- [Aggregation Stages](https://www.mongodb.com/docs/manual/reference/operator/aggregation-pipeline/) — danh mục các pipeline stages.
- [Aggregation Expressions](https://www.mongodb.com/docs/manual/reference/operator/aggregation/) — danh mục expressions và accumulators.
- [$match](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/) và [$expr](https://www.mongodb.com/docs/manual/reference/operator/query/expr/) — query predicate và biểu thức điều kiện.
- [$project](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/) và [$set](https://www.mongodb.com/docs/manual/reference/operator/aggregation/set/) — kiểm soát shape và giá trị field.
- [$unwind](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/) và [$group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/) — thay đổi cardinality và gom nhóm.
- [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/) — bộ nhớ, số stage và giới hạn kết quả.
- [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/) — cách MongoDB optimizer có thể biến đổi kế hoạch.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — APIs Aggregates, Accumulators và aggregate cursor.
- [Spring Data MongoDB Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html) — xây aggregation bằng Java/Spring Data.

Khi thiết kế báo cáo hay API với Aggregation Framework, hãy bắt đầu từ **dữ liệu đầu vào**, xác định **thông tin cần trả**, rồi viết từng stage theo luồng dữ liệu. Đừng chỉ ghép các toán tử có tên giống nhau: **stage tạo bước xử lý, expression tính giá trị, và ngữ cảnh quyết định cách một toán tử được diễn giải**.
