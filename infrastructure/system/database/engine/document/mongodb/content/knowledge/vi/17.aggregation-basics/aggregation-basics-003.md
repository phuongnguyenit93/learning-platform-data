# Chọn, thêm, xóa trường bằng $project, $set và $unset trong MongoDB

## 1. Mục tiêu và tình huống thực tế

Aggregation pipeline trong MongoDB không chỉ dùng để lọc, nhóm hoặc tính toán dữ liệu. Một nhiệm vụ rất phổ biến là **định hình document đầu ra**: chọn những trường cần trả về, tạo trường tính toán, đổi cách trình bày dữ liệu hoặc loại bỏ những trường không nên xuất hiện trong kết quả.

Ví dụ một đơn hàng lưu đầy đủ:

~~~javascript
{
  _id: "ord-101",
  tenantId: "tenant-A",
  status: "PAID",
  customer: {
    id: "C01",
    name: "Lan",
    contact: {
      email: "lan@example.test",
      phone: "0900000001"
    }
  },
  items: [
    {
      sku: "BK-01",
      qty: 2,
      price: NumberDecimal("20.00"),
      internalCost: NumberDecimal("12.00")
    }
  ],
  internalNote: "Dữ liệu nội bộ"
}
~~~

Nhưng một API dành cho khách hàng chỉ cần:

~~~javascript
{
  orderId: "ord-101",
  status: "PAID",
  customerName: "Lan",
  itemCount: 1,
  items: [
    { sku: "BK-01", qty: 2 }
  ]
}
~~~

Ba aggregation stage giúp giải quyết bài toán này:

- **`$project`:** chọn trường được giữ, loại trường, hoặc tạo trường tính toán trong document đầu ra.
- **`$set`:** thêm trường mới hoặc ghi đè trường hiện có, đồng thời giữ các trường khác. Trong aggregation, `$set` là bí danh của **`$addFields`**.
- **`$unset`:** loại một hoặc nhiều trường khỏi document đang đi qua pipeline; là bí danh thuận tiện cho dạng projection loại trừ.

Bài học thuộc chương **Aggregation cơ bản** của module **Database Engine Document MongoDB**. Bạn sẽ học:

1. Phân biệt inclusion và exclusion projection, nhất là cách xử lý `_id`.
2. Dùng biểu thức aggregation để tính toán và đổi tên trường.
3. Thêm/ghi đè field bằng `$set` mà không mất các field còn lại.
4. Xóa field bằng `$unset`, kể cả field lồng nhau hoặc bên trong mảng document.
5. Hiểu ảnh hưởng của **thứ tự stage** và việc một stage được phép đọc những field nào.
6. Xử lý field thiếu, `null`, mảng, object lồng nhau và `$$REMOVE`.
7. Phân biệt aggregation `$set` với toán tử cập nhật `$set` trong `updateOne()`.
8. Quan sát kết quả bằng mongosh, Compass và ví dụ MongoDB Java Driver.

**Điểm cần nhớ ngay:** Một pipeline `aggregate()` thông thường **không thay đổi document lưu trong collection**. Các stage trên định hình document trung gian và đầu ra. Chỉ khi có thao tác ghi cụ thể như `$merge`, `$out` hoặc một lệnh update dùng pipeline thì dữ liệu lưu mới có thể bị thay đổi.

## 2. Mô hình pipeline: document đi qua từng stage

Aggregation pipeline là một chuỗi các stage. Đầu ra của stage trước là đầu vào của stage sau.

~~~text
Collection orders
      |
      v
  $match                 Chọn document nào đi tiếp
      |
      v
  $set                   Thêm trường, tính giá trị mới
      |
      v
  $project               Chọn cấu trúc kết quả cần giữ
      |
      v
  $unset                 Xóa những trường còn dư
      |
      v
  API / mongosh          Nhận document kết quả
~~~

Ví dụ:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $set: {
      customerName: "$customer.name"
    }
  },
  {
    $project: {
      _id: 0,
      customerName: 1,
      status: 1
    }
  }
]);
~~~

`$set` tạo `customerName` từ trường lồng nhau. `$project` giữ `customerName` và `status`, loại `_id`, đồng thời không đưa các field khác vào output.

**Lưu ý về toán tử và cú pháp:** Những tên có dấu `$` bên trong pipeline là tên stage hoặc tên expression của MongoDB, không phải biến JavaScript hay key tùy ý. Chuỗi bắt đầu bằng `$` trong ngữ cảnh expression thường được hiểu là tham chiếu tới field.

## 3. Chuẩn bị database và bộ dữ liệu thực hành

Các ví dụ dùng database độc lập. Trong `mongosh`:

~~~javascript
use aggregation_shape_lab
~~~

Tạo 6 đơn hàng có object lồng nhau, mảng dòng hàng và một số trường nội bộ:

~~~javascript
const demoOrders = [
  {
    _id: "ord-101",
    tenantId: "tenant-A",
    status: "PAID",
    customer: {
      id: "C01",
      name: "Lan",
      contact: {
        email: "lan@example.test",
        phone: "0900000001"
      }
    },
    shipping: {
      city: "Hà Nội",
      method: "STANDARD"
    },
    items: [
      {
        sku: "BK-01",
        qty: NumberInt(2),
        price: NumberDecimal("20.00"),
        internalCost: NumberDecimal("12.00")
      },
      {
        sku: "PEN-01",
        qty: NumberInt(3),
        price: NumberDecimal("2.00"),
        internalCost: NumberDecimal("1.00")
      }
    ],
    tags: ["gift", "vip"],
    discount: NumberDecimal("5.00"),
    internalNote: "Ưu tiên xử lý",
    createdAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: "ord-102",
    tenantId: "tenant-A",
    status: "NEW",
    customer: {
      id: "C02",
      name: "Minh",
      contact: {
        email: "minh@example.test",
        phone: "0900000002"
      }
    },
    shipping: {
      city: "Đà Nẵng",
      method: "EXPRESS"
    },
    items: [
      {
        sku: "BK-02",
        qty: NumberInt(1),
        price: NumberDecimal("15.50"),
        internalCost: NumberDecimal("9.00")
      }
    ],
    tags: ["new"],
    discount: NumberDecimal("0.00"),
    internalNote: "Chưa thanh toán",
    createdAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: "ord-103",
    tenantId: "tenant-A",
    status: "PAID",
    customer: {
      id: "C03",
      name: "An",
      contact: {
        email: "an@example.test"
      }
    },
    shipping: {
      city: "Huế",
      method: "STANDARD"
    },
    items: [],
    tags: [],
    discount: NumberDecimal("0.00"),
    createdAt: ISODate("2026-10-03T08:00:00Z")
  },
  {
    _id: "ord-104",
    tenantId: "tenant-B",
    status: "PAID",
    customer: {
      id: "C04",
      name: "Hà",
      contact: {
        email: "ha@example.test",
        phone: "0900000004"
      }
    },
    shipping: {
      city: "TP. Hồ Chí Minh",
      method: "EXPRESS"
    },
    items: [
      {
        sku: "BK-03",
        qty: NumberInt(1),
        price: NumberDecimal("30.00"),
        internalCost: NumberDecimal("18.00")
      }
    ],
    tags: ["vip"],
    discount: NumberDecimal("2.00"),
    internalNote: "Không chia sẻ",
    createdAt: ISODate("2026-10-04T08:00:00Z")
  },
  {
    _id: "ord-105",
    tenantId: "tenant-A",
    status: "CANCELLED",
    customer: {
      id: "C05",
      name: "Bình",
      contact: {
        email: "binh@example.test"
      }
    },
    shipping: {
      city: "Hà Nội",
      method: "STANDARD"
    },
    items: [
      {
        sku: "NOTE-01",
        qty: NumberInt(1),
        price: NumberDecimal("4.00"),
        internalCost: NumberDecimal("2.50")
      }
    ],
    tags: ["cancelled"],
    discount: null,
    internalNote: "Khách hủy",
    createdAt: ISODate("2026-10-05T08:00:00Z")
  },
  {
    _id: "ord-106",
    tenantId: "tenant-A",
    status: "SHIPPED",
    customer: {
      id: "C06",
      name: "Mai",
      contact: {
        email: "mai@example.test"
      }
    },
    shipping: {
      city: "Cần Thơ",
      method: "STANDARD"
    },
    items: [
      {
        sku: "PEN-02",
        qty: NumberInt(5),
        price: NumberDecimal("1.20"),
        internalCost: NumberDecimal("0.40")
      }
    ],
    tags: ["office"],
    createdAt: ISODate("2026-10-06T08:00:00Z")
  }
];

demoOrders.forEach(order => {
  db.orders.replaceOne(
    { _id: order._id },
    order,
    { upsert: true }
  );
});

db.orders.find(
  {},
  { _id: 1, tenantId: 1, status: 1 }
).sort({ _id: 1 });
~~~

Với collection ban đầu rỗng, có **6 document**, trong đó tenant-A có **5** và tenant-B có **1**. Việc dùng `replaceOne(..., {upsert:true})` cho phép nạp lại các ID mẫu mà không bị duplicate `_id`, nhưng sẽ đặt lại nội dung các record đã thay đổi trong quá trình thực hành; nó không xóa document ngoài tập ID trên.

Các trường hợp được bố trí cố ý:

- `items` là mảng object chứa cả `price` (được phép hiển thị) và `internalCost` (nội bộ).
- `customer.contact.phone` có thể thiếu.
- `discount` có thể là Decimal128, `null` hoặc thiếu field.
- `items` có thể là mảng rỗng (ID `ord-103`).
- `internalNote` có thể xuất hiện hoặc thiếu.

Các ví dụ đếm và bảng kết quả giả định collection chỉ có các document mẫu, không có record khác.

## 4. $project: chọn trường được giữ

### 4.1. Inclusion projection

Cú pháp cơ bản:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      status: 1,
      tenantId: 1
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Với document `ord-101`, kết quả có dạng:

~~~javascript
{
  _id: "ord-101",
  tenantId: "tenant-A",
  status: "PAID"
}
~~~

Ở đây:

- Giá trị `1` trong `$project` nghĩa là **giữ field**.
- Các field không được liệt kê thường bị bỏ khỏi output.
- **`_id` được giữ mặc định**, dù không khai báo `_id:1`.
- Những field không tồn tại trong document đầu vào không tự được tạo ra chỉ vì viết `field:1`.

Bộ lọc truy vấn và projection phục vụ hai mục tiêu khác nhau: `$match` chọn **document nào**; `$project` chọn **field nào** trong mỗi document.

### 4.2. Loại _id khỏi kết quả

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      status: 1,
      tenantId: 1
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  tenantId: "tenant-A",
  status: "PAID"
}
~~~

`_id: 0` là một trường hợp đặc biệt được phép kết hợp với các field inclusion.

Có thể viết `_id: 1` để nêu rõ ý định giữ ID, nhưng trong phần lớn inclusion projection, không cần thiết.

### 4.3. Chọn field lồng nhau bằng dot notation

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      status: 1,
      "customer.name": 1,
      "shipping.city": 1
    }
  }
]);
~~~

Kết quả có dạng:

~~~javascript
{
  status: "PAID",
  customer: { name: "Lan" },
  shipping: { city: "Hà Nội" }
}
~~~

**Quan trọng:** Chọn `"customer.name"` thường giữ **cấu trúc lồng nhau** của field, không tự tạo một field cấp gốc tên `customerName`.

Muốn tạo field phẳng có tên `customerName`, dùng expression:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      customerName: "$customer.name",
      city: "$shipping.city"
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  customerName: "Lan",
  city: "Hà Nội"
}
~~~

Ở dạng expression, chuỗi `"$customer.name"` là **tham chiếu field**, không phải một chuỗi literal cần xuất ra nguyên văn.

### 4.4. Chọn vài trường của mỗi phần tử trong mảng

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      "items.sku": 1,
      "items.qty": 1
    }
  }
]);
~~~

Kết quả có dạng:

~~~javascript
{
  items: [
    { sku: "BK-01", qty: 2 },
    { sku: "PEN-01", qty: 3 }
  ]
}
~~~

Cấu trúc mảng vẫn được giữ, nhưng mỗi object trong mảng chỉ còn các field được chọn. Với nhu cầu thay đổi sâu hơn hoặc tính toán cho từng phần tử, dùng `$map` ở phần sau.

### 4.5. Inclusion projection và field bị thiếu

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-103" } },
  {
    $project: {
      status: 1,
      "customer.contact.phone": 1
    }
  }
]);
~~~

`ord-103` không có `customer.contact.phone`. MongoDB không tự thêm giá trị `null` cho field thiếu chỉ vì nó được chọn bằng `1`. Nếu API cần một giá trị mặc định, hãy dùng một biểu thức như `$ifNull`.

## 5. $project: loại những trường không muốn trả

### 5.1. Exclusion projection

Muốn giữ gần như toàn bộ document nhưng bỏ ghi chú nội bộ:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      internalNote: 0
    }
  }
]);
~~~

`internalNote: 0` có nghĩa là loại field này. Những field khác, kể cả `_id` và `items`, được giữ trong output.

Có thể loại đồng thời nhiều field:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $project: {
      internalNote: 0,
      "customer.contact.phone": 0,
      "items.internalCost": 0
    }
  }
]);
~~~

Với `items` là mảng object, đường dẫn `"items.internalCost"` loại trường chi phí nội bộ khỏi các phần tử tương ứng. Nếu một field đã thiếu, projection loại trừ không tạo thêm lỗi chỉ vì field đó không tồn tại.

### 5.2. Không trộn inclusion và exclusion tùy ý

Cú pháp sau **không hợp lệ**:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      status: 1,
      internalNote: 0
    }
  }
]);
~~~

Một `$project` thông thường không cho trộn quy tắc **giữ field** và **loại field** trong cùng specification, **trừ ngoại lệ liên quan đến `_id`**.

Các cách đúng:

~~~javascript
// Inclusion: chỉ giữ status, mặc định vẫn giữ _id
{ $project: { status: 1 } }

// Inclusion: giữ status, bỏ _id
{ $project: { _id: 0, status: 1 } }

// Exclusion: chỉ loại internalNote
{ $project: { internalNote: 0 } }

// Exclusion: loại internalNote và _id
{ $project: { _id: 0, internalNote: 0 } }
~~~

Nếu cần vừa tính field mới vừa bỏ field nhạy cảm, có thể dùng:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      customerName: "$customer.name"
    }
  },
  {
    $unset: [
      "internalNote",
      "items.internalCost"
    ]
  }
]);
~~~

Hoặc định nghĩa hẳn một **allowlist output** bằng `$project` chứa các field được phép.

### 5.3. Trường hợp tính toán và exclusion

Khi projection tạo field tính toán, cần cẩn thận với quy tắc trộn include/exclude. Cách dễ đọc nhất là:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 0,
      status: 1,
      customerName: "$customer.name"
    }
  }
]);
~~~

Dạng này giữ `status` và tạo `customerName`, trong khi field khác tự bị bỏ.

Không viết một specification vừa yêu cầu `internalNote:0` vừa tạo các field inclusion/computed mà mong MongoDB tự xử lý như hai thao tác độc lập. Khi cần loại field theo điều kiện động, xem `$$REMOVE` ở mục 11.

## 6. $project: tạo trường tính toán và đổi hình dạng kết quả

`$project` không chỉ nhận `0` hoặc `1`. Giá trị của một field đầu ra có thể là một **aggregation expression**.

### 6.1. Tạo alias cho field

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      orderId: "$_id",
      customerName: "$customer.name",
      status: 1
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  orderId: "ord-101",
  customerName: "Lan",
  status: "PAID"
}
~~~

`orderId` là field mới chỉ có trong kết quả pipeline. `_id:0` loại khóa gốc khỏi output; nó **không đổi `_id` đang lưu ở collection**.

### 6.2. Tạo nhãn từ biểu thức

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $project: {
      _id: 1,
      status: 1,
      isPaid: { $eq: ["$status", "PAID"] },
      statusUpper: { $toUpper: "$status" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Ở đây:

- `$eq` trả boolean dựa trên phép so sánh.
- `$toUpper` chuyển chuỗi về chữ hoa theo biểu thức.
- `isPaid` và `statusUpper` được tính cho mỗi document.
- Cả hai field tính toán không cần có trong document gốc.

Nếu dữ liệu có `status` không phải chuỗi hoặc null/missing, nên xác định quy tắc dữ liệu và xử lý điều kiện trước khi dùng một biểu thức yêu cầu kiểu chuỗi cụ thể.

### 6.3. Tính số phần tử mảng

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      itemCount: {
        $size: { $ifNull: ["$items", []] }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Với ID `ord-101`, `itemCount = 2`; với `ord-103`, `itemCount = 0`.

`$ifNull` xử lý trường `items` thiếu hoặc bằng null bằng `[]`. Nếu dữ liệu có thể chứa sai kiểu như `items: "not-an-array"`, `$ifNull` **không tự chuyển chuỗi thành array**; `$size` vẫn đòi biểu thức đầu vào trả mảng. Khi cần chịu dữ liệu sai kiểu, dùng `$isArray` và `$cond` hoặc sửa dữ liệu nguồn.

Ví dụ an toàn hơn:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      itemCount: {
        $cond: [
          { $isArray: "$items" },
          { $size: "$items" },
          0
        ]
      }
    }
  }
]);
~~~

### 6.4. Sử dụng $ifNull để trả mặc định

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-103" } },
  {
    $project: {
      _id: 0,
      name: "$customer.name",
      phone: {
        $ifNull: ["$customer.contact.phone", "Chưa có"]
      },
      discount: {
        $ifNull: ["$discount", NumberDecimal("0.00")]
      }
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  name: "An",
  phone: "Chưa có",
  discount: NumberDecimal("0.00")
}
~~~

`$ifNull` coi giá trị missing và null là tình huống cần fallback. Nó không giống một projection exclusion: exclusion bỏ hẳn field, còn `$ifNull` tạo một field với giá trị mặc định.

### 6.5. Biểu thức trả về document lồng nhau

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      order: {
        id: "$_id",
        status: "$status"
      },
      customer: {
        name: "$customer.name",
        city: "$shipping.city"
      }
    }
  }
]);
~~~

Kết quả được tái cấu trúc:

~~~javascript
{
  order: {
    id: "ord-101",
    status: "PAID"
  },
  customer: {
    name: "Lan",
    city: "Hà Nội"
  }
}
~~~

Field `customer` trong output không còn giống object `customer` ban đầu; nó là một object mới được tạo từ các biểu thức. Đây là cách hữu ích để xây DTO trả về API.

## 7. $project và giá trị literal: phân biệt số 1 với dữ liệu 1

Trong `$project`, số `1` và `0` ở vị trí giá trị field có ý nghĩa **inclusion/exclusion**. Nếu cần tạo field có đúng giá trị số 1 hoặc 0, dùng `$literal`:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      status: 1,
      fixedOne: { $literal: 1 },
      fixedZero: { $literal: 0 },
      source: { $literal: "mongodb" }
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  status: "PAID",
  fixedOne: 1,
  fixedZero: 0,
  source: "mongodb"
}
~~~

Nếu viết:

~~~javascript
{
  $project: {
    fixedOne: 1
  }
}
~~~

MongoDB hiểu `fixedOne:1` là **giữ field fixedOne nếu đã tồn tại**, không phải tạo field mới mang số 1.

### 7.1. Chuỗi bắt đầu bằng dấu $ có ý nghĩa đặc biệt

~~~javascript
{
  $project: {
    copiedStatus: "$status"
  }
}
~~~

`"$status"` là tham chiếu tới field `status`. Muốn xuất ra nguyên văn chuỗi `"$status"`, phải dùng:

~~~javascript
{
  $project: {
    text: { $literal: "$status" }
  }
}
~~~

Quy tắc này cũng quan trọng với `$set` và các biểu thức aggregation khác. Đừng để chuỗi input của người dùng bắt đầu bằng `$` vô tình được coi là field reference nếu thật ra bạn muốn lưu hoặc hiển thị nguyên văn.

## 8. $set: thêm trường mới mà vẫn giữ dữ liệu cũ

Trong aggregation pipeline:

~~~javascript
{
  $set: {
    newField: <aggregation expression>
  }
}
~~~

`$set` là bí danh của `$addFields`. Nó lấy document đầu vào và **bổ sung** các field được khai báo, đồng thời giữ nguyên các field khác, trừ trường được ghi đè.

### 8.1. Thêm một field sao chép dữ liệu

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $set: {
      customerName: "$customer.name"
    }
  }
]);
~~~

Document đầu ra vẫn có `_id`, `tenantId`, `status`, `customer`, `shipping`, `items`, `tags`, `discount`, `internalNote`, `createdAt`; đồng thời xuất hiện thêm `customerName: "Lan"`.

So sánh:

~~~javascript
// Chỉ giữ một số trường, bỏ các trường khác:
{ $project: { status: 1, customerName: "$customer.name" } }

// Giữ mọi field đang có rồi thêm customerName:
{ $set: { customerName: "$customer.name" } }
~~~

Đây là lý do `$set` thuận tiện khi bạn cần nhiều bước tính toán trung gian nhưng chưa muốn giới hạn output quá sớm.

### 8.2. Ghi đè field đã tồn tại

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-102" } },
  {
    $set: {
      status: "PENDING"
    }
  },
  {
    $project: {
      _id: 1,
      status: 1
    }
  }
]);
~~~

Trong kết quả pipeline, `status` của `ord-102` trở thành `PENDING`, dù document gốc vẫn đang lưu `NEW`.

Giá trị mới của field trong `$set` có thể là literal hoặc expression. Với chuỗi `"PENDING"` không bắt đầu bằng `$`, MongoDB hiểu là chuỗi literal. Nếu cần giá trị nguyên văn `"$PENDING"`, dùng `{ $literal: "$PENDING" }`.

### 8.3. Thêm field lồng nhau bằng dot notation

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $set: {
      "shipping.label": {
        $concat: [
          "$shipping.city",
          " - ",
          "$shipping.method"
        ]
      }
    }
  },
  {
    $project: {
      _id: 0,
      shipping: 1
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  shipping: {
    city: "Hà Nội",
    method: "STANDARD",
    label: "Hà Nội - STANDARD"
  }
}
~~~

Nếu dùng đường dẫn `"shipping.label"`, các trường con khác như `city` và `method` vẫn có thể được giữ trong object `shipping`.

### 8.4. Thay nguyên object là chuyện khác

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $set: {
      shipping: {
        city: "Cần Thơ"
      }
    }
  },
  {
    $project: {
      shipping: 1
    }
  }
]);
~~~

Cách này **ghi đè toàn bộ giá trị `shipping` trong document trung gian** bằng một object chỉ có `city`. Field `shipping.method` không được tự giữ lại.

Nếu chỉ muốn sửa một field con mà giữ siblings, nên dùng dot notation với đường dẫn cụ thể.

### 8.5. Tạo nhiều field tính toán

~~~javascript
db.orders.aggregate([
  {
    $set: {
      customerName: "$customer.name",
      isPaid: { $eq: ["$status", "PAID"] },
      itemCount: {
        $size: { $ifNull: ["$items", []] }
      }
    }
  },
  {
    $project: {
      _id: 1,
      customerName: 1,
      isPaid: 1,
      itemCount: 1
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Kết quả với dữ liệu mẫu:

| ID | customerName | isPaid | itemCount |
|---|---|---|---:|
| `ord-101` | Lan | true | 2 |
| `ord-102` | Minh | false | 1 |
| `ord-103` | An | true | 0 |
| `ord-104` | Hà | true | 1 |
| `ord-105` | Bình | false | 1 |
| `ord-106` | Mai | false | 1 |

Lưu ý `$size` được dùng sau `$ifNull` ở đây vì dữ liệu mẫu giữ đúng kiểu array cho `items`.

## 9. $unset: xóa field khỏi document kết quả

### 9.1. Xóa một field

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $unset: "internalNote"
  }
]);
~~~

`$unset` loại `internalNote` khỏi document trung gian, giữ các field khác. Collection gốc vẫn lưu `internalNote` vì đây là aggregation thông thường.

### 9.2. Xóa nhiều field

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $unset: [
      "internalNote",
      "customer.contact.phone",
      "items.internalCost"
    ]
  }
]);
~~~

Đối số có thể là một **chuỗi tên field** hoặc **mảng các chuỗi tên field**. Với các ví dụ trên, MongoDB loại field ghi chú nội bộ, số điện thoại và chi phí nội bộ khỏi output.

Nếu một document vốn không có `internalNote` hoặc `phone`, việc loại field không làm phát sinh giá trị mới.

### 9.3. $unset tương đương exclusion projection

Ví dụ:

~~~javascript
{ $unset: ["internalNote", "items.internalCost"] }
~~~

có mục tiêu tương đương:

~~~javascript
{
  $project: {
    internalNote: 0,
    "items.internalCost": 0
  }
}
~~~

Cả hai cùng loại những field chỉ định khỏi output, trong khi giữ những field khác.

Chọn `$unset` khi ý định là “xóa các field này” và muốn giữ pipeline dễ đọc. Chọn `$project` inclusion khi bạn muốn xác định **chính xác tập field được phép xuất ra**.

### 9.4. Xóa _id khỏi output

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  { $unset: "_id" }
]);
~~~

Kết quả không có `_id`. Điều này hoàn toàn khác với việc cố xóa `_id` khỏi document **được lưu trữ** bằng lệnh update: `_id` là khóa bất biến trong các thao tác ghi document hiện hữu.

### 9.5. Loại field lồng nhau

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  { $unset: "customer.contact.phone" },
  {
    $project: {
      customer: 1
    }
  }
]);
~~~

Kết quả giữ `customer.id`, `customer.name` và `customer.contact.email` nhưng không còn `customer.contact.phone`.

Chỉ xóa trường con bằng đường dẫn, thay vì xóa toàn bộ `customer.contact`, giúp bảo toàn các field còn cần thiết.

## 10. Chọn $project, $set hay $unset?

| Nhu cầu | Stage phù hợp | Lý do |
|---|---|---|
| Chỉ trả `status` và `customer.name` | `$project` inclusion | Khai báo danh sách field cần giữ |
| Bỏ `internalNote` nhưng giữ gần như mọi field khác | `$unset` | Diễn đạt loại trừ rõ ràng |
| Thêm `itemCount` mà vẫn giữ document đầy đủ | `$set` | Bổ sung field tính toán, không bỏ các field khác |
| Đổi tên `customer.name` thành `customerName` trong DTO | `$project` với expression | Tạo output field ở vị trí mong muốn |
| Tạo `grossTotal` để stage tiếp theo dùng | `$set` | Làm giàu document trung gian |
| Bỏ nhiều field riêng tư ở cuối pipeline | `$unset` hoặc `$project` inclusion | Kiểm soát output |
| Vừa cần tính toán vừa muốn response chỉ có 4 field | `$set` trước rồi `$project` sau, hoặc một `$project` có expression | Tách bước tính và bước chọn output |
| Xóa field tùy theo điều kiện | `$$REMOVE` trong expression | Có thể bỏ field theo logic |
| Chỉnh sửa document lưu trong collection | Không dùng `aggregate()` đơn thuần | Cần lệnh update/pipeline write theo yêu cầu |

**Quy tắc chọn nhanh:** `$project` định nghĩa **hình dạng**, `$set` định nghĩa **các giá trị được bổ sung/thay**, `$unset` định nghĩa **các trường phải biến mất**.

## 11. $$REMOVE: loại field theo điều kiện

`$unset` loại trường một cách không điều kiện đối với mọi document đi qua stage. Nếu muốn trường xuất hiện với một số document nhưng biến mất ở các document khác, MongoDB hỗ trợ biến hệ thống **`$$REMOVE`** trong những biểu thức phù hợp.

Ví dụ: chỉ giữ `internalNote` trong output nếu trạng thái là `CANCELLED`; các trạng thái khác không trả field ấy.

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      noteForAudit: {
        $cond: [
          { $eq: ["$status", "CANCELLED"] },
          "$internalNote",
          "$$REMOVE"
        ]
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Ở output:

- Document `ord-105` có thể có `noteForAudit: "Khách hủy"`.
- Những document trạng thái khác không có field `noteForAudit`.
- Nếu trạng thái CANCELLED nhưng nguồn không có `internalNote`, field đầu ra cũng không tự được tạo.

### 11.1. $$REMOVE trong $set

~~~javascript
db.orders.aggregate([
  {
    $set: {
      internalNote: {
        $cond: [
          { $eq: ["$status", "PAID"] },
          "$$REMOVE",
          "$internalNote"
        ]
      }
    }
  }
]);
~~~

Khi trạng thái là `PAID`, field `internalNote` bị loại khỏi document trung gian. Với trạng thái khác, biểu thức có thể giữ giá trị field hiện có.

Điều này hữu ích khi yêu cầu định hình đầu ra là có điều kiện theo một field dữ liệu. Tuy nhiên, **phân quyền và bảo mật** không nên chỉ phụ thuộc một điều kiện trạng thái do dữ liệu quyết định. Những field nhạy cảm cần được kiểm soát bằng quyền truy cập và hợp đồng response an toàn.

### 11.2. Phân biệt $$REMOVE với null

~~~javascript
{
  $project: {
    fieldA: { $literal: null },
    fieldB: "$$REMOVE"
  }
}
~~~

- `fieldA` **xuất hiện** với giá trị null.
- `fieldB` **không xuất hiện** trong output.

Đây là sự khác biệt quan trọng đối với JSON API, nơi field vắng mặt và field có giá trị null có thể mang ý nghĩa khác nhau.

## 12. $project và xung đột đường dẫn

Một projection không thể đồng thời đặc tả một field cha và đường dẫn con của chính field đó theo cách gây **path collision**.

Ví dụ không hợp lệ:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      customer: 1,
      "customer.name": 1
    }
  }
]);
~~~

Vì đã yêu cầu giữ cả object `customer` và đồng thời chọn riêng `customer.name`, MongoDB có thể báo lỗi path collision. Đổi thứ tự hai key không giải quyết được vấn đề.

Các cách đúng:

~~~javascript
// Chọn toàn object:
{
  $project: {
    customer: 1
  }
}

// Chỉ chọn tên trong object:
{
  $project: {
    "customer.name": 1
  }
}

// Tạo field phẳng:
{
  $project: {
    customerName: "$customer.name"
  }
}
~~~

Với `$set` cũng cần tránh khai báo đồng thời những đường dẫn cha/con mâu thuẫn trong một stage. Nếu thật sự phải tạo object mới, hãy xác định cấu trúc cuối cùng một cách rõ ràng, thay vì đặt các đường dẫn chồng chéo rồi trông chờ một thứ tự ghi ngầm.

## 13. Xử lý mảng object bằng $map

Chọn `"items.sku":1` rất tiện để chỉ giữ field đơn giản. Nhưng nếu cần **tính tiền từng dòng**, cần một biểu thức duyệt từng phần tử mảng.

### 13.1. Tạo lineTotal cho mỗi phần tử

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      items: {
        $map: {
          input: "$items",
          as: "line",
          in: {
            sku: "$$line.sku",
            qty: "$$line.qty",
            price: "$$line.price",
            lineTotal: {
              $multiply: [
                "$$line.qty",
                "$$line.price"
              ]
            }
          }
        }
      }
    }
  }
]);
~~~

Kết quả với `ord-101`:

~~~javascript
{
  items: [
    {
      sku: "BK-01",
      qty: 2,
      price: NumberDecimal("20.00"),
      lineTotal: NumberDecimal("40.00")
    },
    {
      sku: "PEN-01",
      qty: 3,
      price: NumberDecimal("2.00"),
      lineTotal: NumberDecimal("6.00")
    }
  ]
}
~~~

Các field `internalCost` không được đưa vào object `in`, nên bị loại khỏi mảng kết quả.

Trong `$map`:

- `input` là mảng muốn duyệt.
- `as: "line"` đặt tên biến cho từng phần tử.
- `$$line` tham chiếu biến, khác `$line` tham chiếu field của document.
- `in` là expression tạo phần tử đầu ra.

### 13.2. Giữ nguyên thuộc tính cũ rồi thêm lineTotal

Khi muốn giữ các trường hiện có trong từng phần tử, dùng `$mergeObjects`:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $set: {
      items: {
        $map: {
          input: "$items",
          as: "line",
          in: {
            $mergeObjects: [
              "$$line",
              {
                lineTotal: {
                  $multiply: [
                    "$$line.qty",
                    "$$line.price"
                  ]
                }
              }
            ]
          }
        }
      }
    }
  },
  { $unset: "items.internalCost" },
  {
    $project: {
      _id: 0,
      items: 1
    }
  }
]);
~~~

Chuỗi stage:

1. `$set` thay giá trị `items` trong document trung gian bằng mảng đã tính `lineTotal`.
2. `$unset` loại `internalCost` trong từng phần tử.
3. `$project` chỉ trả mảng `items`.

Nếu document có `items: null` hoặc thiếu trường này, `$map` có thể trả null. Nếu `items` không phải array, `$map` có thể báo lỗi. Với dữ liệu không được kiểm soát schema, nên xử lý kiểu trước:

~~~javascript
{
  $map: {
    input: {
      $cond: [
        { $isArray: "$items" },
        "$items",
        []
      ]
    },
    as: "line",
    in: "$$line.sku"
  }
}
~~~

### 13.3. Tính tổng tiền từ mảng

Với `ord-101`, dòng BK-01 = 2 × 20.00 = 40.00; dòng PEN-01 = 3 × 2.00 = 6.00. Tổng trước giảm giá = 46.00.

Có thể tính bằng `$map` rồi `$sum`:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $set: {
      grossTotal: {
        $sum: {
          $map: {
            input: { $ifNull: ["$items", []] },
            as: "line",
            in: {
              $multiply: [
                "$$line.qty",
                "$$line.price"
              ]
            }
          }
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      grossTotal: 1
    }
  }
]);
~~~

Với dữ liệu mẫu, `grossTotal` có giá trị Decimal128 tương ứng **46.00**.

Khi dùng Decimal128 với giá tiền, tránh trộn quy tắc làm tròn không rõ ràng vào phép tính. Trong nghiệp vụ thật, cần thống nhất đơn vị tiền tệ, thuế, chiết khấu và quy tắc làm tròn theo hợp đồng dữ liệu.

### 13.4. Tính netTotal sau giảm giá

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $set: {
      grossTotal: {
        $sum: {
          $map: {
            input: { $ifNull: ["$items", []] },
            as: "line",
            in: {
              $multiply: [
                "$$line.qty",
                "$$line.price"
              ]
            }
          }
        }
      }
    }
  },
  {
    $set: {
      netTotal: {
        $subtract: [
          "$grossTotal",
          { $ifNull: ["$discount", NumberDecimal("0.00")] }
        ]
      }
    }
  },
  {
    $project: {
      _id: 0,
      grossTotal: 1,
      netTotal: 1
    }
  }
]);
~~~

Kết quả về giá trị: `grossTotal = 46.00` và `netTotal = 41.00`.

Dùng hai `$set` stage riêng giúp field `grossTotal` được tạo ở stage trước rồi mới tham chiếu ở stage sau. Không nên dựa vào việc các expression bên trong cùng một `$set` tự được đánh giá tuần tự theo thứ tự khai báo để tham chiếu ngay field vừa tạo.

## 14. Thứ tự stage: cùng toán tử nhưng kết quả khác nhau

### 14.1. Dùng $set trước $project

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $set: {
      customerName: "$customer.name"
    }
  },
  {
    $project: {
      _id: 0,
      customerName: 1,
      status: 1
    }
  }
]);
~~~

Kết quả chứa `customerName: "Lan"`, vì `$set` có thể đọc `customer.name` trước khi `$project` rút gọn document.

### 14.2. $project quá sớm có thể làm mất dữ liệu cần tính

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      status: 1
    }
  },
  {
    $set: {
      customerName: "$customer.name"
    }
  }
]);
~~~

Sau `$project`, field `customer` không còn trong document trung gian. Expression `"$customer.name"` ở stage sau không thể đọc lại dữ liệu đã bị bỏ. Vì vậy nó không thể tạo cùng giá trị `"Lan"` như ví dụ 14.1.

Nếu vẫn cần `customer.name` ở stage sau, hãy giữ field đó trong projection hoặc dời phép tính lên trước.

### 14.3. $unset quá sớm gây vấn đề tương tự

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  { $unset: "customer" },
  {
    $set: {
      customerName: "$customer.name"
    }
  }
]);
~~~

Vì `customer` đã bị xóa khỏi document trung gian, stage sau không còn dữ liệu để tạo `customerName`. Thứ tự stage cần theo dependency của field, không chỉ theo thói quen “xóa field càng sớm càng tốt”.

### 14.4. Match trước hay sau set?

Nếu lọc theo field gốc:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A", status: "PAID" } },
  { $set: { customerName: "$customer.name" } },
  { $project: { customerName: 1, status: 1 } }
]);
~~~

`$match` sớm thường giúp giới hạn số document cần tính toán và tạo cơ hội tận dụng index.

Nếu lọc theo field **vừa được tính**, bạn cần tạo nó trước:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      itemCount: {
        $size: { $ifNull: ["$items", []] }
      }
    }
  },
  { $match: { itemCount: { $gte: 2 } } },
  { $project: { _id: 1, itemCount: 1 } }
]);
~~~

Trong bộ mẫu, ID `ord-101` có 2 phần tử, những ID khác có tối đa 1 hoặc 0. Vì vậy kết quả gồm `ord-101`.

**Không có quy tắc cứng rằng mọi `$project` phải đặt đầu pipeline để tối ưu hiệu năng.** MongoDB có optimizer có thể tự tối ưu việc chọn các field cần thiết trong nhiều tình huống. Hãy ưu tiên pipeline đúng nghĩa và kiểm tra plan thực tế.

## 15. Phân biệt aggregation $set với update $set

Hai cú pháp có cùng tên nhưng xuất hiện trong **ngữ cảnh khác nhau**.

### 15.1. $set là aggregation stage

~~~javascript
db.orders.aggregate([
  {
    $set: {
      customerName: "$customer.name",
      status: "VIEWED"
    }
  }
]);
~~~

Đây là phép biến đổi document trong kết quả aggregation. Nó **không lưu** `customerName` hoặc `VIEWED` vào collection gốc.

### 15.2. $set là update operator

~~~javascript
db.orders.updateOne(
  { _id: "ord-101" },
  {
    $set: {
      status: "SHIPPED"
    }
  }
);
~~~

Đây là lệnh cập nhật document được lưu trong database. Sau khi thực thi thành công, `status` của `ord-101` bị thay đổi trên server.

Nếu viết update dạng operator:

~~~javascript
db.orders.updateOne(
  { _id: "ord-101" },
  {
    $set: {
      customerName: "$customer.name"
    }
  }
);
~~~

thì với **update operator** kiểu truyền thống, giá trị chuỗi `"$customer.name"` được coi là một giá trị cần ghi, không phải aggregation expression tự tính từ field nguồn. Không được nhầm nó với stage `$set` trong pipeline.

### 15.3. Update bằng aggregation pipeline

MongoDB hỗ trợ dùng một tập stage được phép trong **update pipeline**, ví dụ:

~~~javascript
db.orders.updateOne(
  { _id: "ord-101" },
  [
    {
      $set: {
        customerName: "$customer.name"
      }
    },
    {
      $unset: "internalNote"
    }
  ]
);
~~~

Trong dạng **update pipeline** (tham số update là một mảng stage), biểu thức `"$customer.name"` được đánh giá như field reference, rồi kết quả mới được **ghi vào document**.

Điểm khác biệt:

| Ngữ cảnh | Ví dụ | Có ghi thay đổi vào collection? |
|---|---|---|
| `aggregate([{ $set: ... }])` | Stage trong truy vấn aggregation | Không, nếu chỉ trả result thông thường |
| `updateOne(filter, { $set: ... })` | Update operator | Có |
| `updateOne(filter, [{ $set: ... }])` | Update pipeline stage | Có |
| `aggregate([...,$merge])` | Pipeline có stage ghi | Có thể ghi theo cấu hình `$merge` |

**Cảnh báo:** Nếu áp dụng `$unset` trong update pipeline, field bị xóa thật khỏi document lưu trữ. Vì vậy không thực hành dạng update trên dữ liệu sản xuất và không dùng nhầm với pipeline chỉ để định hình response.

### 15.4. Cú pháp $unset trong hai ngữ cảnh khác nhau

Aggregation stage:

~~~javascript
{ $unset: "internalNote" }
{ $unset: ["internalNote", "items.internalCost"] }
~~~

Update operator thông thường:

~~~javascript
db.orders.updateOne(
  { _id: "ord-101" },
  {
    $unset: {
      internalNote: ""
    }
  }
);
~~~

Aggregation `$unset` nhận chuỗi hoặc mảng chuỗi tên field. Update operator `$unset` dùng một object ánh xạ field tới giá trị placeholder; giá trị phía sau field không quyết định nội dung xóa. Không mang nguyên cú pháp từ ngữ cảnh này sang ngữ cảnh kia.

### 15.5. Trường _id và tính bất biến

Trong pipeline chỉ đọc, `$project: {_id:0}` hoặc `$unset:"_id"` làm ID biến mất khỏi **output**. Nhưng document lưu trữ vẫn có `_id`.

Trong các lệnh update đối với document hiện hữu, `_id` bất biến: không thể xóa hoặc thay đổi nó bằng update pipeline. Nếu muốn ID hiển thị khác, hãy tạo field alias như `orderId` trong kết quả thay vì cố sửa khóa định danh.

## 16. $set và $addFields

Hai aggregation stage:

~~~javascript
{
  $set: {
    customerName: "$customer.name"
  }
}
~~~

và:

~~~javascript
{
  $addFields: {
    customerName: "$customer.name"
  }
}
~~~

có cùng ý nghĩa trong aggregation: thêm hoặc ghi đè field, giữ lại các field khác.

Vì vậy, trong codebase, chọn một cách viết nhất quán để người đọc dễ theo dõi. `$set` thường trực quan đối với người quen update operator, còn `$addFields` diễn đạt rõ “làm giàu document” trong pipeline. Nhưng nhớ rằng `$set` có cả hai ngữ cảnh aggregate và update, nên cần xem nó nằm **trong lệnh nào**.

## 17. $project trong find() khác $project stage ở aggregate()

Truy vấn `find()` cũng có **projection** như tham số thứ hai:

~~~javascript
db.orders.find(
  { tenantId: "tenant-A" },
  {
    _id: 0,
    status: 1,
    "customer.name": 1
  }
);
~~~

Trong aggregation:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $project: {
      _id: 0,
      status: 1,
      "customer.name": 1
    }
  }
]);
~~~

Với những trường hợp inclusion đơn giản, hai cách có thể cho cấu trúc output tương đương.

Nhưng không nên coi chúng là một API hoàn toàn giống nhau trong mọi biểu thức hoặc giới hạn. `$project` stage là thành phần pipeline với khả năng tính toán và phối hợp stage trước/sau. `find()` projection đi kèm cú pháp, quy tắc và khả năng tối ưu riêng.

Khi chỉ cần một truy vấn đơn giản có filter, sort và projection, `find()` có thể phù hợp. Khi cần kết hợp nhiều phép tính mảng, nhóm, join hoặc định hình nhiều bước, aggregation pipeline giúp diễn đạt rõ hơn.

## 18. Bảo mật dữ liệu và lựa chọn allowlist/denylist

Giả sử `orders` có các field:

~~~text
public:
  _id
  status
  customer.name
  items.sku
  items.qty
  items.price

internal:
  tenantId
  customer.contact.phone
  items.internalCost
  internalNote
~~~

Có hai chiến lược định hình output.

### 18.1. Denylist bằng $unset

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $unset: [
      "tenantId",
      "customer.contact.phone",
      "items.internalCost",
      "internalNote"
    ]
  }
]);
~~~

Cách này đơn giản khi số field cần xóa ít và schema ổn định. Tuy nhiên, nếu một ứng dụng sau đó thêm field nhạy cảm mới `fraudScore` hoặc `privateToken`, denylist cũ **không tự loại field mới**.

### 18.2. Allowlist bằng $project

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $project: {
      _id: 1,
      status: 1,
      "customer.name": 1,
      "items.sku": 1,
      "items.qty": 1,
      "items.price": 1
    }
  }
]);
~~~

Chỉ những field được nêu xuất hiện. Field mới thêm trong collection không tự lộ qua output.

Với API public hoặc dữ liệu có thông tin nhạy cảm, allowlist thường dễ kiểm soát hơn. Dù vậy, projection **không thay thế authentication, authorization, phân quyền MongoDB hoặc kiểm tra tenant**. Truy vấn phải lọc đúng tài nguyên được phép, không chỉ dựa vào việc ẩn vài field.

### 18.3. $unset không phải cách xóa dữ liệu nhạy cảm vĩnh viễn

Trong aggregate thông thường:

~~~javascript
db.orders.aggregate([
  { $unset: "internalNote" }
]);
~~~

giá trị `internalNote` vẫn ở collection. Nếu yêu cầu là xóa thông tin khỏi database vì chính sách lưu trữ/riêng tư, cần thao tác ghi, quy trình quản trị dữ liệu, kiểm tra bản sao lưu và phạm vi liên quan; không xem projection output là data erasure.

## 19. Hiệu năng và thứ tự projection

### 19.1. Có nên $project thật sớm để giảm tải?

MongoDB optimizer có thể tự xác định những field cần thiết ở các stage trong nhiều tình huống. Việc thêm `$project` ngay đầu pipeline để “giảm dung lượng” không luôn mang lại lợi ích.

Ví dụ:

~~~javascript
db.orders.aggregate([
  { $project: { status: 1 } },
  { $match: { status: "PAID" } }
]);
~~~

Có thể được optimizer sắp xếp hoặc tối ưu theo cách khác với thứ tự văn bản bạn nhìn thấy, tùy biểu thức và phiên bản MongoDB. Nhưng nếu stage sau cần field đã bị loại, pipeline không thể khôi phục field đó.

Cách dễ hiểu hơn khi filter theo trường gốc:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $project: { _id: 1, status: 1 } }
]);
~~~

### 19.2. $project có giảm dữ liệu truyền qua mạng không?

Nếu kết quả không còn các field lớn như `items`, `customer.contact` hoặc metadata nội bộ, document trả về client thường nhỏ hơn. Điều này có thể giảm payload, network bandwidth và chi phí JSON serialization.

Tuy nhiên, mức giảm thời gian phụ thuộc số document, index, pipeline và hạ tầng. Nó không chứng minh rằng server không bao giờ phải đọc các field bị loại trong quá trình tính toán.

### 19.3. Covered query và index

Một index có thể hỗ trợ filter/sort/projection đến mức không cần fetch đầy đủ document trong một số mẫu truy vấn. Nhưng chỉ thêm `$project` không tự đảm bảo covered query. Cần xem plan thực tế và phân biệt trường được lấy từ index với trường phải đọc từ collection.

Ví dụ có thể cân nhắc index phục vụ filter:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

Sau đó xem plan:

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "tenant-A", status: "PAID" } },
  { $project: { _id: 1, status: 1, createdAt: 1 } }
]);
~~~

Tùy dữ liệu và optimizer, kế hoạch có thể chứa `IXSCAN` hoặc `COLLSCAN`. Với 6 document, collection scan thường không phải dấu hiệu cần tối ưu gấp.

### 19.4. Tính toán trên mảng có chi phí

`$map`, `$filter`, `$multiply`, `$sum` hay tái tạo mảng đều cần xử lý dữ liệu. Với mảng rất lớn hoặc pipeline nhiều stage, tính toán có thể tiêu thụ CPU và bộ nhớ đáng kể.

Hãy:

- Lọc những document không cần thiết bằng `$match` khi có thể.
- Giữ pipeline rõ dependency giữa các field.
- Đo `executionStats` và độ trễ tổng.
- Tránh trả mảng quá lớn nếu client chỉ cần tóm tắt.
- Cân nhắc mô hình dữ liệu khác nếu mảng tăng không giới hạn.

## 20. MongoDB Compass: thực hành định hình document

MongoDB Compass có tab **Aggregations** giúp xây dựng và chạy pipeline. Giao diện có thể khác theo phiên bản, nhưng cách thực hành chung:

1. Kết nối đến MongoDB Server/cluster đã nạp database `aggregation_shape_lab`.
2. Mở collection `orders`.
3. Vào tab **Aggregations** và tạo pipeline mới.
4. Thêm stage `$match` để lọc `tenant-A`:

   ~~~json
   {"tenantId":"tenant-A"}
   ~~~

5. Thêm stage `$set` để tạo `customerName`:

   ~~~json
   {"customerName":"$customer.name"}
   ~~~

6. Thêm stage `$project` để chọn output:

   ~~~json
   {"_id":1,"status":1,"customerName":1}
   ~~~

7. Chạy pipeline, quan sát sự thay đổi cấu trúc qua mỗi stage nếu Compass hỗ trợ xem kết quả trung gian.
8. Thay `$project` bằng `$unset` với field `internalNote` để đối chiếu inclusion và exclusion.
9. Thử mảng `items` trong `$project` hoặc `$map` theo các ví dụ ở mục 13.
10. Quay lại tab **Documents** và kiểm tra bản ghi gốc: các phép biến đổi từ aggregation thông thường không tự ghi thay đổi lên collection.

Nếu cấu hình stage editor không nhận nguyên một object gồm khóa `$project`, hãy xem giao diện có yêu cầu chọn tên stage ở ô riêng hay không. Trong mongosh, pipeline luôn viết đầy đủ:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  { $project: { status: 1 } }
]);
~~~

## 21. MongoDB Java Driver: xây dựng pipeline

Với Java Driver, có thể tạo aggregation pipeline bằng các `Document` BSON. Ví dụ sau giả định biến `database` kiểu `MongoDatabase` đã kết nối, và collection `orders` đã có dữ liệu:

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

MongoCollection<Document> orders = database.getCollection("orders");

List<Document> pipeline = Arrays.asList(
    new Document("$match",
        new Document("tenantId", "tenant-A")),

    new Document("$set",
        new Document("customerName", "$customer.name")),

    new Document("$project",
        new Document("_id", 1)
            .append("status", 1)
            .append("customerName", 1))
);

List<Document> result = orders.aggregate(pipeline)
    .into(new ArrayList<>());

for (Document order : result) {
    System.out.println(order.toJson());
}
~~~

Pipeline thực hiện giống các ví dụ mongosh:

- `$match` giới hạn tenant.
- `$set` bổ sung tên khách hàng từ nested field.
- `$project` tạo output chỉ có các field đã chọn.

### 21.1. Ví dụ xóa field bằng Java Driver

~~~java
List<Document> pipeline = Arrays.asList(
    new Document("$match",
        new Document("tenantId", "tenant-A")),

    new Document("$unset",
        Arrays.asList(
            "internalNote",
            "items.internalCost",
            "customer.contact.phone"
        ))
);

List<Document> publicOrders = orders.aggregate(pipeline)
    .into(new ArrayList<>());
~~~

`$unset` trong aggregation nhận mảng chuỗi; cách viết này giữ đúng cấu trúc MongoDB BSON. Ứng dụng có thể dùng các builder của Java Driver nếu team thống nhất, nhưng cần phân biệt stage expression với update operator.

### 21.2. DTO và hợp đồng response

Một API có thể chuyển document aggregation sang DTO:

~~~java
public record OrderSummary(
    String orderId,
    String status,
    String customerName,
    int itemCount
) {}
~~~

Để ánh xạ dễ dàng, pipeline có thể định hình đúng tên field mà DTO dùng:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $project: {
      _id: 0,
      orderId: "$_id",
      status: 1,
      customerName: "$customer.name",
      itemCount: {
        $size: { $ifNull: ["$items", []] }
      }
    }
  }
]);
~~~

Đó là một lợi ích lớn của `$project`: API có thể nhận sẵn shape phù hợp để serialize, thay vì tải document đầy đủ rồi tự loại hàng loạt field ở tầng ứng dụng.

### 21.3. Phân biệt output shape với cập nhật dữ liệu

Nếu lập trình viên dùng:

~~~java
orders.aggregate(pipeline).into(new ArrayList<>());
~~~

thì tác vụ này đọc kết quả. Nó không lưu field `customerName` vào database. Muốn ghi thay đổi, cần dùng đúng write API được phép; đừng coi sự xuất hiện của `$set` trong pipeline đọc là một thao tác update.

## 22. Các lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Output vẫn có `_id` | `$project` mặc định giữ `_id` | Dùng `_id:0` hoặc `$unset:"_id"` |
| Output mất hầu hết field | Dùng inclusion `$project` khi muốn bổ sung | Dùng `$set` hoặc liệt kê đầy đủ field cần giữ |
| Lỗi trộn `1` và `0` | Inclusion/exclusion không được trộn tùy ý | Chọn một kiểu, dùng stage khác hoặc ngoại lệ `_id` |
| Lỗi path collision | Vừa chọn parent vừa chọn child | Chọn một đường dẫn hoặc định nghĩa output object rõ |
| `customerName` không xuất hiện đúng | Field `customer` đã bị loại ở stage trước | Tính trước khi loại hoặc giữ field nguồn |
| `$set` làm mất object con | Ghi đè cả object `shipping` | Dùng dot notation khi chỉ sửa một field |
| `$unset` không xóa dữ liệu lưu | Aggregation thông thường không ghi | Hiểu đây chỉ là định hình output |
| Lỗi truyền object cho stage `$unset` | Nhầm với update operator `$unset` | Stage nhận chuỗi hoặc mảng chuỗi |
| Stage `$project` với `flag:1` không tạo số 1 | `1` nghĩa là inclusion | Dùng `{ $literal: 1 }` |
| Chuỗi `"$status"` hiển thị thành giá trị status | String bắt đầu `$` được hiểu là field reference | Dùng `$literal` nếu cần chuỗi nguyên văn |
| `$size` báo lỗi khi field không phải array | `$size` đòi array | Dùng `$isArray` và `$cond`/schema validation |
| `$map` trả null hoặc lỗi | Input null/missing hoặc sai kiểu | Chuẩn hóa/kiểm tra input array |
| Field có null dù muốn bỏ hẳn | Tạo `null` thay vì dùng `$$REMOVE` | Dùng `$$REMOVE` cho trường hợp cần thiếu field |
| Vô tình lộ thông tin nội bộ | Denylist `$unset` không bao phủ field mới | Dùng allowlist `$project` cho API public |
| Sau aggregation, `findOne` vẫn thấy dữ liệu cũ | Pipeline chỉ đọc không cập nhật collection | Muốn ghi phải dùng write API phù hợp |
| Filter query trang nhanh nhưng pipeline chậm | Tính toán mảng nhiều, stage order/index khác | Xem explain, đo CPU/I/O và giới hạn output |
| Đặt hai giá trị trong cùng `$set` rồi tham chiếu nhau không như mong đợi | Field mới chưa thuộc input của stage đó | Tách thành các `$set` stage theo dependency |

## 23. Bài tập thực hành tổng hợp

Thực hiện trong database `aggregation_shape_lab` sau khi nạp 6 document mẫu. Mỗi bài có thể chạy độc lập trên collection đã nạp vì chúng dùng `aggregate()` thông thường, không làm thay đổi dữ liệu gốc.

### Bài 1. Chỉ trả ba trường

Yêu cầu: chỉ trả `_id`, `status` và `customer.name` của tenant-A.

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $project: {
      _id: 1,
      status: 1,
      "customer.name": 1
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

**Kỳ vọng:** 5 document thuộc tenant-A, mỗi document chỉ còn các field yêu cầu.

### Bài 2. Ẩn ID và làm phẳng customer name

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      orderId: "$_id",
      customerName: "$customer.name",
      status: 1
    }
  }
]);
~~~

**Kỳ vọng:** `{orderId:"ord-101",customerName:"Lan",status:"PAID"}` (không có khóa `_id` ở output).

### Bài 3. Loại dữ liệu nội bộ

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $unset: [
      "internalNote",
      "customer.contact.phone",
      "items.internalCost"
    ]
  }
]);
~~~

**Câu hỏi:** Field nào còn xuất hiện trong `items`? Có thay đổi dữ liệu gốc trong collection không?

### Bài 4. Thêm customerName và itemCount

~~~javascript
db.orders.aggregate([
  {
    $set: {
      customerName: "$customer.name",
      itemCount: {
        $size: { $ifNull: ["$items", []] }
      }
    }
  },
  {
    $project: {
      _id: 1,
      customerName: 1,
      itemCount: 1
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

**Kỳ vọng:** `ord-101` có `itemCount:2`; `ord-103` có `itemCount:0`.

### Bài 5. Dùng literal đúng cách

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      status: 1,
      countConstant: { $literal: 1 },
      dollarText: { $literal: "$status" }
    }
  }
]);
~~~

**Kỳ vọng:** `countConstant` là số 1; `dollarText` là chuỗi literal `"$status"`, không phải `"PAID"`.

### Bài 6. Tính lineTotal

Với `ord-101`, dùng `$map` để trả mỗi item gồm `sku` và `lineTotal`; không trả `internalCost`.

Gợi ý:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      _id: 0,
      lines: {
        $map: {
          input: "$items",
          as: "line",
          in: {
            sku: "$$line.sku",
            lineTotal: {
              $multiply: ["$$line.qty", "$$line.price"]
            }
          }
        }
      }
    }
  }
]);
~~~

Kết quả giá trị của hai dòng: **40.00** và **6.00**.

### Bài 7. Tính grossTotal và netTotal

Dùng hai `$set` stage:

1. Tính `grossTotal` từ mảng `items`.
2. Tính `netTotal = grossTotal - discount`, coi discount null/missing là 0.

Với `ord-101`, kết quả mong đợi **46.00** và **41.00**.

### Bài 8. Loại field theo điều kiện

Chỉ trả `noteForAudit` khi `status = "CANCELLED"`.

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      noteForAudit: {
        $cond: [
          { $eq: ["$status", "CANCELLED"] },
          "$internalNote",
          "$$REMOVE"
        ]
      }
    }
  }
]);
~~~

**Câu hỏi:** Sự khác nhau giữa `$$REMOVE` và `null` là gì?

### Bài 9. Nhận diện projection không hợp lệ

Xét:

~~~javascript
{
  $project: {
    status: 1,
    internalNote: 0
  }
}
~~~

và:

~~~javascript
{
  $project: {
    customer: 1,
    "customer.name": 1
  }
}
~~~

**Yêu cầu:** Giải thích lỗi của mỗi đoạn, rồi viết cách diễn đạt đúng tương ứng.

### Bài 10. So sánh $set và $project

Chạy lần lượt:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  { $set: { isPaid: { $eq: ["$status", "PAID"] } } }
]);

db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  {
    $project: {
      isPaid: { $eq: ["$status", "PAID"] }
    }
  }
]);
~~~

**Câu hỏi:** Vì sao kết quả đầu có nhiều field hơn? Kết quả thứ hai có `_id` không?

### Bài 11. Nested object và dot notation

Thử hai cách:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  { $set: { "shipping.city": "Cần Thơ" } },
  { $project: { shipping: 1 } }
]);

db.orders.aggregate([
  { $match: { _id: "ord-101" } },
  { $set: { shipping: { city: "Cần Thơ" } } },
  { $project: { shipping: 1 } }
]);
~~~

**Kỳ vọng:** Truy vấn đầu vẫn có `shipping.method`; truy vấn sau không có field đó trong output. Đối chiếu `findOne` để xác nhận document gốc không bị sửa.

### Bài 12. Kiểm tra thứ tự stage

Chạy `$project` chỉ giữ `status` trước `$set:{customerName:"$customer.name"}`, rồi đổi thứ tự hai stage. Giải thích vì sao cách thứ nhất không tạo cùng giá trị `Lan` như cách thứ hai.

### Bài 13. Phân biệt update pipeline và aggregation

So sánh:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-102" } },
  { $set: { status: "PENDING" } }
]);
~~~

với:

~~~javascript
// Chỉ chạy trong database thực hành và khi muốn sửa dữ liệu.
db.orders.updateOne(
  { _id: "ord-102" },
  [
    { $set: { status: "PENDING" } }
  ]
);
~~~

**Câu hỏi:** Vì sao chỉ câu lệnh thứ hai thay document lưu? Lần sau nạp lại bộ dữ liệu mẫu sẽ có tác động gì?

### Bài 14. Thiết kế output cho API public

Yêu cầu API chỉ trả:

~~~javascript
{
  orderId: "...",
  status: "...",
  customerName: "...",
  items: [
    { sku: "...", qty: 0, price: NumberDecimal("0") }
  ]
}
~~~

Viết pipeline:

- `$match` theo `tenantId` đã xác thực.
- `$project` tạo `orderId`, `customerName`, giữ `status`.
- Chọn các field `sku`, `qty`, `price` của item.
- Không để `internalCost`, `internalNote` hoặc `customer.contact.phone` xuất hiện.

Hãy so sánh chiến lược dùng allowlist `$project` với chỉ dùng `$unset` theo danh sách field hiện tại.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** `$project:{status:1}` giữ `_id` không?

*Đáp án:* Có, trừ khi đặt `_id:0`.

**Câu 2.** Có thể viết `$project:{status:1, internalNote:0}` không?

*Đáp án:* Không theo quy tắc trộn include/exclude thông thường; ngoại lệ là cách xử lý `_id`.

**Câu 3.** Nếu chỉ muốn thêm field `itemCount` mà giữ toàn bộ các field khác thì dùng gì?

*Đáp án:* `$set` hoặc `$addFields`.

**Câu 4.** Làm thế nào xóa `items.internalCost` khỏi mỗi phần tử của mảng object trong output?

*Đáp án:* Dùng `$unset:"items.internalCost"` hoặc exclusion projection tương ứng nếu cấu trúc dữ liệu phù hợp.

**Câu 5.** `$unset:"internalNote"` trong aggregate có xóa field trong database thật không?

*Đáp án:* Không, nếu chỉ là pipeline aggregation trả kết quả và không có stage ghi.

**Câu 6.** Vì sao field tên `constant` không được gán bằng `constant:1` trong `$project` để tạo số 1?

*Đáp án:* `1` là ký hiệu inclusion; muốn literal 1 thì dùng `{$literal:1}`.

**Câu 7.** Sự khác nhau giữa `"$customer.name"` và `"$$line.sku"` là gì?

*Đáp án:* `$customer.name` đọc field của document đầu vào; `$$line.sku` đọc thuộc tính của biến `line` được tạo trong biểu thức như `$map`.

**Câu 8.** Hai stage `$set` và `$project` có thể đổi thứ tự tùy ý không?

*Đáp án:* Không. Nếu projection bỏ field mà stage sau cần, kết quả sẽ khác.

**Câu 9.** Muốn bỏ một field khi một điều kiện đúng, nên xem công cụ nào?

*Đáp án:* `$$REMOVE` kết hợp expression như `$cond`.

**Câu 10.** Khi API trả document cho khách, dùng allowlist hay denylist an toàn hơn về cấu trúc response?

*Đáp án:* Allowlist `$project` thường kiểm soát tốt hơn field mới xuất hiện sau này, nhưng không thay thế authorization hoặc hạn chế quyền truy cập.

## 25. Nguyên tắc ghi nhớ

- **`$project`**: Chọn, loại hoặc tính field trong **document output**. Mặc định giữ `_id`; không trộn inclusion và exclusion tùy ý.
- **`$set`**: Thêm/ghi đè field mà giữ các field khác; là bí danh của `$addFields` trong aggregation.
- **`$unset`**: Loại một hoặc nhiều field; tương đương exclusion projection về mục đích.
- **`$literal`**: Dùng khi cần số `0`/`1` làm giá trị hoặc chuỗi bắt đầu bằng `$` mà không muốn MongoDB diễn giải thành ký hiệu điều khiển.
- **`$$REMOVE`**: Loại field có điều kiện, khác việc tạo field với giá trị `null`.
- **Nested paths**: Dùng dot notation khi muốn giữ cấu trúc lồng nhau hoặc chỉ sửa một field con; chú ý xung đột parent/child.
- **Arrays**: Chọn vài field đơn giản bằng projection; dùng `$map` để tính từng phần tử và định hình sâu hơn.
- **Thứ tự stage quan trọng**: Field bị loại ở stage trước không thể được tham chiếu như dữ liệu gốc ở stage sau.
- **Aggregation đọc khác update ghi**: `$set`/`$unset` trong `aggregate()` thông thường không thay đổi collection; dùng update pipeline mới thực sự ghi.
- **API public**: Ưu tiên output allowlist và giữ filter theo tenant/quyền; không phụ thuộc chỉ vào việc xóa các field đã biết.
- **Hiệu năng**: Đặt `$match` hợp lý, đo `explain` và chi phí tính toán; không coi `$project` sớm là tối ưu chắc chắn.

Ba stage `$project`, `$set` và `$unset` là những khối xây dựng cơ bản của aggregation pipeline. Khi hiểu rõ **chọn field**, **thêm hoặc thay field** và **xóa field** là ba thao tác khác nhau, bạn có thể tạo kết quả truy vấn đúng hợp đồng API, giữ các phép tính dễ đọc và tránh làm lộ hoặc đánh mất dữ liệu ngoài ý định.
