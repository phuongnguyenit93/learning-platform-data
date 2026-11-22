# Tạo bộ dữ liệu mẫu và quy ước thực hành MongoDB có thể chạy lại

## 1. Mục tiêu và bối cảnh

Khi học MongoDB, một truy vấn chỉ có ý nghĩa nếu người thực hành biết chính xác dữ liệu ban đầu là gì. Nếu mỗi lần thử lại tự thêm vài document bằng tay, kết quả của lệnh tìm kiếm, cập nhật, thống kê hoặc tạo index sẽ khác nhau giữa các lần học. Vì vậy, trước khi đi vào CRUD và aggregation, ta cần một **bộ dữ liệu mẫu có hợp đồng rõ ràng** và một **quy trình khởi tạo có thể chạy lại** (reproducible seed).

Sau bài này, bạn có thể:

- Thiết kế một tập document vừa thể hiện đặc trưng document database, vừa có cấu trúc thống nhất để dễ truy vấn.
- Phân biệt kiểu BSON quan trọng như String, Boolean, Date, Int32, Decimal128, Array và Embedded Document.
- Tạo ba collection có liên kết bằng mã định danh ổn định, kèm index phục vụ bài thực hành.
- Chạy lại script seed nhiều lần mà không làm tăng số document hoặc làm biến dạng dữ liệu mẫu.
- Kiểm tra nhanh trạng thái dữ liệu, chạy truy vấn mẫu và dọn riêng dữ liệu do bài thực hành sở hữu.

Ta sử dụng tình huống **cửa hàng bán đồ dùng học tập và phụ kiện**. Các đơn hàng tham chiếu khách hàng, trong khi từng dòng hàng được nhúng vào đơn để lưu số lượng và **giá tại thời điểm đặt hàng**. Đây là cách mô phỏng cả quan hệ bằng tham chiếu lẫn cấu trúc nhúng của MongoDB.

> **Phạm vi an toàn:** Các lệnh dưới đây dành cho máy hoặc cơ sở dữ liệu thực hành riêng. Script sử dụng database **mongo_replay_lab_v1**, các collection bắt đầu bằng **lab_**, và chỉ xóa document gắn nhãn **dataset: "practice-v1"**. Không thực thi trên cơ sở dữ liệu sản xuất hoặc database dùng chung chưa được kiểm soát.

## 2. Chốt quy ước dữ liệu trước khi viết script

### 2.1. Hợp đồng cho ba collection

| Collection | Số document | Mã định danh cố định | Mục đích |
| --- | ---: | --- | --- |
| **lab_customers** | 3 | c001, c002, c003 | Thông tin khách hàng và ngày tham gia |
| **lab_products** | 4 | p001, p002, p003, p004 | Danh mục sản phẩm, giá và tồn kho mẫu |
| **lab_orders** | 5 | o001 đến o005 | Đơn hàng với khách hàng tham chiếu và các dòng hàng nhúng |

Các thuộc tính dùng xuyên suốt:

| Thuộc tính | Quy ước | Lý do |
| --- | --- | --- |
| **_id** | Chuỗi cố định, ví dụ c001 hoặc o003 | Kết quả seed dễ đọc, ổn định qua nhiều lần chạy |
| **dataset** | Luôn là chuỗi practice-v1 | Phân biệt dữ liệu thuộc bài thực hành và giới hạn phạm vi dọn dẹp |
| **customerId / productId** | Chuỗi tham chiếu cùng loại với _id tương ứng | Tránh so sánh sai kiểu khi lọc hoặc dùng $lookup |
| **email / sku** | Chuỗi không trùng trong cùng dataset | Phù hợp tạo unique compound index |
| **createdAt / joinedAt** | BSON Date với thời điểm UTC cố định | So sánh theo thời gian, không lệ thuộc thời điểm chạy script |
| **price / unitPrice / total** | BSON Decimal128, ví dụ NumberDecimal("75000.00") | Biểu diễn tiền theo hệ thập phân có chủ đích |
| **stock / quantity** | BSON Int32 qua NumberInt | Biểu diễn số đếm nguyên |
| **status** | Một trong pending, paid, shipped, cancelled | Giúp thực hành lọc và thống kê theo trạng thái |
| **lineItems** | Mảng document gồm productId, quantity, unitPrice | Giữ cấu trúc đơn hàng và bản chụp giá bán |

Trong dữ liệu thật, MongoDB thường tự cấp ObjectId cho **_id**. Ở bài này, chuỗi cố định là quyết định có chủ đích để việc chạy lại và đối chiếu kết quả dễ dàng. Không nên suy ra rằng tất cả hệ thống MongoDB phải dùng chuỗi thay ObjectId.

**Nhất quán tên trường:** dùng camelCase cho thuộc tính (customerId, lineItems, createdAt), tên collection số nhiều, nhãn trạng thái chữ thường tiếng Anh, và một kiểu dữ liệu duy nhất cho mỗi trường có cùng ý nghĩa. Giá tiền trong toàn bộ bài được hiểu là **VND**, không tự chuyển sang kiểu số thực JavaScript.

### 2.2. Vì sao vừa tham chiếu vừa nhúng?

Một khách hàng có thể có nhiều đơn, nên **lab_orders.customerId** giữ mã khách hàng, tránh chép toàn bộ hồ sơ khách hàng vào mỗi đơn. Ngược lại, **lab_orders.lineItems** là một phần của chính đơn hàng: số lượng, sản phẩm và giá bán lúc đặt hàng cần giữ nguyên khi bảng giá sản phẩm thay đổi.

~~~text
lab_customers                    lab_orders
_id: "c001"  <--- customerId ---  _id: "o001"
name: "Lan"                      customerId: "c001"
                                  lineItems: [
                                    { productId: "p001", quantity: 2,
                                      unitPrice: Decimal128("75000.00") },
                                    { productId: "p002", quantity: 3,
                                      unitPrice: Decimal128("12000.00") }
                                  ]
                                  total: Decimal128("186000.00")

lab_products
_id: "p001"  <--- lineItems[].productId
price: Decimal128("75000.00")
~~~

MongoDB không tự tạo ràng buộc khóa ngoại giống một số hệ quản trị quan hệ. Dữ liệu seed phải chủ động bảo đảm customerId và productId trỏ đến mã có tồn tại. Trong ứng dụng thực tế, trách nhiệm này thường nằm ở tầng ứng dụng hoặc ở quy trình kiểm soát dữ liệu.

## 3. Chuẩn bị môi trường thực hành

Bạn cần một MongoDB server có thể kết nối và **mongosh**. Có thể sử dụng MongoDB chạy cục bộ, trong container hoặc một môi trường học tập riêng có quyền tạo collection và index.

Kiểm tra kết nối bằng mongosh:

~~~bash
mongosh "mongodb://127.0.0.1:27017" --eval "db.runCommand({ ping: 1 })"
~~~

Nếu kết nối thành công, kết quả có trường **ok: 1**. Nếu dùng môi trường khác, thay URI bằng địa chỉ tương ứng. Không đưa mật khẩu hoặc connection string có thông tin bí mật vào tài liệu, mã nguồn hoặc lịch sử commit.

Tạo một thư mục làm việc tùy ý, sau đó chép toàn bộ khối JavaScript ở mục tiếp theo vào file **seed_mongo_lab.js**. Chạy file từ thư mục ấy bằng lệnh:

~~~bash
mongosh "mongodb://127.0.0.1:27017" --file seed_mongo_lab.js
~~~

Không cần gọi lệnh **use** trong script. Câu lệnh **db.getSiblingDB("mongo_replay_lab_v1")** chọn đích rõ ràng, kể cả khi URI hiện đang trỏ đến database khác.

## 4. Script tạo bộ dữ liệu mẫu

Script dưới đây cố định toàn bộ ID, thời gian, giá, số lượng và trạng thái. Trước khi chèn lại, nó xóa **đúng các document có dataset = practice-v1** trong ba collection của bài. Các lần chạy nối tiếp vì thế trả về cùng dữ liệu. Wrapper dạng hàm giúp gọi lại bằng **load("seed_mongo_lab.js")** trong một phiên mongosh mà không vướng lỗi khai báo lại const.

~~~javascript
// seed_mongo_lab.js
(() => {
  const lab = db.getSiblingDB("mongo_replay_lab_v1");
  const DATASET = "practice-v1";

  const customers = [
    {
      _id: "c001",
      dataset: DATASET,
      name: "Nguyễn Lan",
      email: "lan@example.test",
      city: "Hà Nội",
      joinedAt: ISODate("2025-12-15T09:00:00.000Z"),
      active: true
    },
    {
      _id: "c002",
      dataset: DATASET,
      name: "Trần Minh",
      email: "minh@example.test",
      city: "TP. Hồ Chí Minh",
      joinedAt: ISODate("2025-12-20T10:30:00.000Z"),
      active: true
    },
    {
      _id: "c003",
      dataset: DATASET,
      name: "Lê Hoa",
      email: "hoa@example.test",
      city: "Đà Nẵng",
      joinedAt: ISODate("2026-01-02T08:15:00.000Z"),
      active: false
    }
  ];

  const products = [
    {
      _id: "p001",
      dataset: DATASET,
      sku: "ST-001",
      name: "Sổ tay",
      category: "stationery",
      price: NumberDecimal("75000.00"),
      stock: NumberInt(80),
      active: true
    },
    {
      _id: "p002",
      dataset: DATASET,
      sku: "ST-002",
      name: "Bút bi",
      category: "stationery",
      price: NumberDecimal("12000.00"),
      stock: NumberInt(200),
      active: true
    },
    {
      _id: "p003",
      dataset: DATASET,
      sku: "AC-001",
      name: "Ly sứ",
      category: "accessory",
      price: NumberDecimal("95000.00"),
      stock: NumberInt(40),
      active: true
    },
    {
      _id: "p004",
      dataset: DATASET,
      sku: "EL-001",
      name: "Bàn phím",
      category: "electronics",
      price: NumberDecimal("450000.00"),
      stock: NumberInt(25),
      active: true
    }
  ];

  const orders = [
    {
      _id: "o001",
      dataset: DATASET,
      customerId: "c001",
      createdAt: ISODate("2026-01-05T08:00:00.000Z"),
      status: "paid",
      lineItems: [
        {
          productId: "p001",
          quantity: NumberInt(2),
          unitPrice: NumberDecimal("75000.00")
        },
        {
          productId: "p002",
          quantity: NumberInt(3),
          unitPrice: NumberDecimal("12000.00")
        }
      ],
      total: NumberDecimal("186000.00")
    },
    {
      _id: "o002",
      dataset: DATASET,
      customerId: "c002",
      createdAt: ISODate("2026-01-10T09:30:00.000Z"),
      status: "shipped",
      lineItems: [
        {
          productId: "p003",
          quantity: NumberInt(1),
          unitPrice: NumberDecimal("95000.00")
        },
        {
          productId: "p002",
          quantity: NumberInt(5),
          unitPrice: NumberDecimal("12000.00")
        }
      ],
      total: NumberDecimal("155000.00")
    },
    {
      _id: "o003",
      dataset: DATASET,
      customerId: "c001",
      createdAt: ISODate("2026-02-03T14:00:00.000Z"),
      status: "pending",
      lineItems: [
        {
          productId: "p004",
          quantity: NumberInt(1),
          unitPrice: NumberDecimal("450000.00")
        }
      ],
      total: NumberDecimal("450000.00")
    },
    {
      _id: "o004",
      dataset: DATASET,
      customerId: "c003",
      createdAt: ISODate("2026-02-10T16:00:00.000Z"),
      status: "cancelled",
      lineItems: [
        {
          productId: "p001",
          quantity: NumberInt(1),
          unitPrice: NumberDecimal("75000.00")
        }
      ],
      total: NumberDecimal("75000.00")
    },
    {
      _id: "o005",
      dataset: DATASET,
      customerId: "c002",
      createdAt: ISODate("2026-02-14T11:45:00.000Z"),
      status: "paid",
      lineItems: [
        {
          productId: "p004",
          quantity: NumberInt(1),
          unitPrice: NumberDecimal("450000.00")
        },
        {
          productId: "p003",
          quantity: NumberInt(2),
          unitPrice: NumberDecimal("95000.00")
        }
      ],
      total: NumberDecimal("640000.00")
    }
  ];

  // Chỉ làm sạch dữ liệu do bài thực hành này sở hữu.
  // Không drop database hoặc collection.
  const names = ["lab_orders", "lab_products", "lab_customers"];
  for (const name of names) {
    lab.getCollection(name).deleteMany({ dataset: DATASET });
  }

  // Chèn theo thứ tự: khách hàng, sản phẩm, đơn hàng.
  lab.getCollection("lab_customers").insertMany(customers);
  lab.getCollection("lab_products").insertMany(products);
  lab.getCollection("lab_orders").insertMany(orders);

  // Index duy nhất trong phạm vi dataset.
  lab.getCollection("lab_customers").createIndex(
    { dataset: 1, email: 1 },
    { name: "ux_lab_customers_dataset_email", unique: true }
  );
  lab.getCollection("lab_products").createIndex(
    { dataset: 1, sku: 1 },
    { name: "ux_lab_products_dataset_sku", unique: true }
  );

  // Index hỗ trợ các truy vấn đơn hàng thường dùng.
  lab.getCollection("lab_orders").createIndex(
    { dataset: 1, customerId: 1, createdAt: -1 },
    { name: "ix_lab_orders_customer_date" }
  );
  lab.getCollection("lab_orders").createIndex(
    { dataset: 1, status: 1, createdAt: -1 },
    { name: "ix_lab_orders_status_date" }
  );

  const counts = {
    customers: lab.getCollection("lab_customers").countDocuments({
      dataset: DATASET
    }),
    products: lab.getCollection("lab_products").countDocuments({
      dataset: DATASET
    }),
    orders: lab.getCollection("lab_orders").countDocuments({
      dataset: DATASET
    })
  };

  if (
    counts.customers !== 3 ||
    counts.products !== 4 ||
    counts.orders !== 5
  ) {
    throw new Error("Số lượng document sau seed không đúng: " +
      JSON.stringify(counts));
  }

  print("Seed hoàn tất: " + JSON.stringify(counts));
})();
~~~

Khi chạy thành công, bạn sẽ thấy số lượng tương đương:

~~~text
Seed hoàn tất: {"customers":3,"products":4,"orders":5}
~~~

**Giải thích thứ tự thực hiện:**

1. Chọn database bằng tên tường minh và khai báo nhãn dataset. Mọi document mẫu đều có nhãn này.
2. Tạo dữ liệu trong mã nguồn, không sử dụng giá trị ngẫu nhiên hay thời điểm hiện tại. Các ngày đều có hậu tố **Z** để biểu diễn UTC.
3. Dọn dữ liệu mẫu của lần chạy trước bằng bộ lọc có điều kiện. Ba collection khác và những document không mang nhãn dataset này không nằm trong lệnh dọn.
4. Chèn dữ liệu và tạo index bằng tên cố định. Khi một index đã tồn tại với cùng định nghĩa, MongoDB tái sử dụng định nghĩa đó.
5. Đếm lại số document để phát hiện lỗi lưu dữ liệu rõ ràng ngay tại thời điểm seed.

Lệnh dọn rồi chèn **không phải một giao dịch nguyên tử**: nếu script bị ngắt ở giữa, một phần dữ liệu có thể tạm thời trống. Với môi trường thực hành riêng, chỉ cần chạy lại toàn bộ file để khôi phục. Trong ứng dụng thật cần cân nhắc transaction, migration, upsert và cơ chế điều phối phù hợp. Không nên dùng lệnh xóa hàng loạt này làm cách triển khai dữ liệu production.

## 5. Thực hành truy vấn trên trạng thái dữ liệu đã biết

Sau khi seed, mở mongosh hoặc tạo file JavaScript riêng để chạy các đoạn dưới đây. Tất cả truy vấn đều chọn đúng database và dùng bộ lọc **dataset** để bảo đảm kết quả chỉ thuộc bài thực hành.

### 5.1. Tìm đơn hàng có tổng tiền từ 200.000 VND

~~~javascript
const lab = db.getSiblingDB("mongo_replay_lab_v1");

lab.getCollection("lab_orders")
  .find(
    {
      dataset: "practice-v1",
      total: { $gte: NumberDecimal("200000.00") }
    },
    { _id: 1, customerId: 1, status: 1, total: 1 }
  )
  .sort({ _id: 1 })
  .toArray();
~~~

**Kết quả mong đợi:** o003 (450.000 VND, pending) và o005 (640.000 VND, paid). Truy vấn này lọc theo số tiền, **chưa lọc trạng thái đã hoàn tất**, vì vậy đơn chờ xử lý vẫn xuất hiện.

### 5.2. Kết hợp đơn hàng với tên khách hàng bằng $lookup

~~~javascript
lab.getCollection("lab_orders").aggregate([
  { $match: { dataset: "practice-v1" } },
  {
    $lookup: {
      from: "lab_customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $unwind: "$customer" },
  {
    $project: {
      _id: 1,
      customerId: 1,
      customerName: "$customer.name",
      status: 1,
      total: 1
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
~~~

Kết quả có **5 đơn**; o001 và o003 mang tên Nguyễn Lan, o002 và o005 mang tên Trần Minh, o004 mang tên Lê Hoa. **$lookup** kết hợp document theo khóa bằng nhau; **$unwind** biến phần tử duy nhất trong mảng customer thành một document để đọc các thuộc tính thuận tiện.

### 5.3. Tính doanh thu hợp lệ theo khách hàng

Giả sử quy ước báo cáo của bài chỉ tính đơn **paid** hoặc **shipped**. Đơn **pending** và **cancelled** không được cộng doanh thu.

~~~javascript
lab.getCollection("lab_orders").aggregate([
  {
    $match: {
      dataset: "practice-v1",
      status: { $in: ["paid", "shipped"] }
    }
  },
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
~~~

| Khách hàng | Đơn được tính | Doanh thu mong đợi |
| --- | --- | ---: |
| c001 | o001 | 186.000,00 VND |
| c002 | o002 và o005 | 795.000,00 VND |
| c003 | Không có đơn hợp lệ | 0 VND, không xuất hiện trong kết quả $group |
| **Tổng** | **3 đơn** | **981.000,00 VND** |

Trường **revenue** có kiểu Decimal128 vì nguồn **total** là Decimal128. Phép cộng trong aggregation không bắt buộc chuyển giá trị về kiểu số thực.

### 5.4. Đối chiếu số tiền với từng dòng hàng

Mỗi đơn có thể tự tính lại tổng bằng công thức **tổng của (quantity × unitPrice)**. Dưới đây là truy vấn tìm **đơn hàng có tổng tiền sai**:

~~~javascript
lab.getCollection("lab_orders").aggregate([
  { $match: { dataset: "practice-v1" } },
  {
    $project: {
      total: 1,
      calculatedTotal: {
        $sum: {
          $map: {
            input: "$lineItems",
            as: "item",
            in: {
              $multiply: ["$$item.quantity", "$$item.unitPrice"]
            }
          }
        }
      }
    }
  },
  { $match: { $expr: { $ne: ["$total", "$calculatedTotal"] } } }
]).toArray();
~~~

**Kết quả mong đợi:** mảng rỗng **[]**. Chẳng hạn, o001 có 2 × 75.000 + 3 × 12.000 = 186.000 VND. Đây là truy vấn thực hành để quan sát dữ liệu, chưa phải quy trình kiểm định toàn diện của một ứng dụng bán hàng.

### 5.5. Nhìn index và giải thích kế hoạch truy vấn

~~~javascript
lab.getCollection("lab_orders").getIndexes();

lab.getCollection("lab_orders")
  .find({
    dataset: "practice-v1",
    customerId: "c002"
  })
  .sort({ createdAt: -1 })
  .explain("executionStats");
~~~

Index **{ dataset: 1, customerId: 1, createdAt: -1 }** phù hợp với điều kiện lọc dataset, customerId và thứ tự giảm dần của createdAt. Tuy nhiên, với dữ liệu chỉ có 5 đơn, MongoDB có thể chọn quét collection thay vì dùng index; **không nên mặc định mọi kết quả explain đều có IXSCAN**. Đọc các trường của executionStats và so sánh khi tăng kích thước dữ liệu ở một bài thực hành khác.

## 6. Kiểm chứng khả năng chạy lại

Một seed thật sự có thể lặp lại phải cho trạng thái logic như nhau sau mỗi lần chạy. Thực hiện tuần tự:

1. Chạy **seed_mongo_lab.js** lần thứ nhất.
2. Chạy các câu truy vấn ở mục 5 và ghi nhận số document, các ID, trạng thái, doanh thu.
3. Chạy lại **chính file seed đó** lần thứ hai, không sửa giá trị đầu vào.
4. Chạy lại truy vấn. Số document và kết quả phải không đổi.

Ví dụ chạy file hai lần từ terminal:

~~~bash
mongosh "mongodb://127.0.0.1:27017" --file seed_mongo_lab.js
mongosh "mongodb://127.0.0.1:27017" --file seed_mongo_lab.js
~~~

Hoặc trong một phiên mongosh đã kết nối:

~~~javascript
load("seed_mongo_lab.js");
load("seed_mongo_lab.js");
~~~

Kiểm tra nhanh bằng một đoạn mã đọc dữ liệu:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_replay_lab_v1");
  const filter = { dataset: "practice-v1" };

  print("customers = " +
    lab.getCollection("lab_customers").countDocuments(filter));
  print("products = " +
    lab.getCollection("lab_products").countDocuments(filter));
  print("orders = " +
    lab.getCollection("lab_orders").countDocuments(filter));

  print("orderIds = " + JSON.stringify(
    lab.getCollection("lab_orders")
      .find(filter, { _id: 1 })
      .sort({ _id: 1 })
      .toArray()
      .map(order => order._id)
  ));
})();
~~~

Kết quả phải là **3 khách hàng**, **4 sản phẩm**, **5 đơn**, với các ID **o001, o002, o003, o004, o005**. Nếu sau hai lượt có 10 đơn, quy trình khởi tạo đang sai: thường là dùng _id ngẫu nhiên hoặc chỉ insert thêm mà không xử lý dữ liệu cũ. Nếu kết quả thay đổi theo ngày chạy, thường là script phụ thuộc Date hiện tại hoặc dữ liệu ngẫu nhiên không được cố định.

**Khác nhau giữa các cách làm:**

| Cách làm | Khi chạy lại | Phù hợp khi |
| --- | --- | --- |
| insertMany với _id ngẫu nhiên | Dễ nhân đôi document | Chỉ nạp dữ liệu mới một lần, có kiểm soát |
| insertMany với _id cố định nhưng không dọn | Lần hai gặp duplicate key | Muốn chủ động ngăn ghi lại, không phải seed lặp |
| deleteMany có lọc dataset rồi insertMany cố định | Trả bộ dữ liệu mẫu về trạng thái ban đầu | Phòng lab riêng, cần kết quả ổn định mỗi lần học |
| replaceOne với upsert theo _id cố định | Có thể ghi đè document tương ứng mà không cần xóa toàn bộ | Muốn đồng bộ từng record; vẫn phải xử lý record cũ không còn trong seed |

Ví dụ upsert một record nếu bạn muốn tìm hiểu thêm về hướng đồng bộ theo khóa:

~~~javascript
lab.getCollection("lab_products").replaceOne(
  { _id: "p001", dataset: "practice-v1" },
  {
    _id: "p001",
    dataset: "practice-v1",
    sku: "ST-001",
    name: "Sổ tay",
    category: "stationery",
    price: NumberDecimal("75000.00"),
    stock: NumberInt(80),
    active: true
  },
  { upsert: true }
);
~~~

**replaceOne** thay thế toàn bộ document phù hợp (trừ _id bất biến). Nếu cập nhật schema hoặc xóa một sản phẩm khỏi danh sách seed, chỉ upsert các record hiện tại sẽ **không tự xóa record cũ**. Vì mục tiêu bài này là luôn quay về đúng một bộ dữ liệu mẫu nhỏ, quy trình dọn có phạm vi rồi chèn lại dễ theo dõi hơn.

## 7. Dọn dữ liệu do bài thực hành sở hữu

Khi đã học xong, có thể xóa đúng các document mang nhãn dataset của bài mà vẫn giữ database, collection và index:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_replay_lab_v1");
  const filter = { dataset: "practice-v1" };

  for (const name of ["lab_orders", "lab_products", "lab_customers"]) {
    const result = lab.getCollection(name).deleteMany(filter);
    print(name + ": deleted " + result.deletedCount);
  }
})();
~~~

Nếu bộ dữ liệu còn nguyên, số document bị xóa lần lượt là **5, 4, 3**. Chạy lại seed sẽ tái tạo toàn bộ dữ liệu. Không dùng **db.dropDatabase()** hay **collection.drop()** trong bài thực hành này vì phạm vi của chúng rộng hơn nhu cầu dọn dataset và còn loại bỏ index tương ứng.

## 8. Lỗi hay gặp và cách tự xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc xử lý |
| --- | --- | --- |
| Không kết nối được MongoDB | Server chưa chạy, sai URI hoặc chưa xác thực | Kiểm tra lại URI, trạng thái server và quyền của tài khoản thực hành |
| E11000 duplicate key | Trùng _id/email/sku với document đang tồn tại | Xác nhận đúng database riêng, kiểm tra document đang chiếm khóa và chỉ dọn dữ liệu bạn sở hữu |
| countDocuments trả về 0 | Đang xem sai database hoặc quên lọc đúng dataset | In lab.getName(), kiểm tra tên collection và bộ lọc practice-v1 |
| Giá hoặc tổng tiền sai lệch khi tính toán | Nhập giá bằng JavaScript Number, lẫn kiểu dữ liệu hoặc tính total sai | Dùng NumberDecimal, quan sát $type và chạy đối chiếu dòng hàng ở mục 5.4 |
| Không so sánh ngày đúng | Lưu ngày dưới dạng chuỗi hoặc dùng múi giờ không thống nhất | Dùng ISODate với UTC và kiểm tra kiểu BSON thực tế |
| Lần chạy sau có thêm record | Dùng ObjectId mới, insert nối tiếp hoặc thiếu bước reset | Sử dụng _id cố định và chạy lại toàn bộ script |
| Tạo index lỗi vì định nghĩa trùng tên | Index cũ cùng tên nhưng key hoặc options đã đổi | Xem getIndexes(); trong database lab riêng mới cân nhắc chỉnh index có chủ đích |

Để quan sát kiểu BSON đã lưu, chạy:

~~~javascript
lab.getCollection("lab_products").aggregate([
  { $match: { _id: "p001", dataset: "practice-v1" } },
  {
    $project: {
      _id: 1,
      priceType: { $type: "$price" },
      stockType: { $type: "$stock" }
    }
  }
]).toArray();
~~~

Với dữ liệu mẫu trên, **priceType** là **decimal**, còn **stockType** là **int**. Khi thao tác bằng driver của một ngôn ngữ lập trình, cần dùng kiểu dữ liệu tương ứng của driver; biểu thức **NumberDecimal**, **NumberInt** và **ISODate** trong bài là các helper của mongosh.

## 9. Bài tập tự thực hành

1. **Lọc theo ngày và trạng thái:** Tìm đơn có status = paid và createdAt từ ngày 01/02/2026 UTC trở đi. Kết quả dự kiến có đúng **o005**.
2. **Truy vấn mảng lồng nhau:** Tìm các đơn chứa sản phẩm p003 bằng điều kiện trên **lineItems.productId**. Kết quả dự kiến là **o002** và **o005**.
3. **Thống kê theo danh mục:** Đếm số sản phẩm thuộc category = stationery; kết quả dự kiến là **2**.
4. **Quan sát thay đổi có thể phục hồi:** Sửa stock của p001 thành 1, kiểm tra đã thay đổi, chạy lại seed và xác nhận stock quay về **80**.
5. **Giải thích quyết định mô hình hóa:** Nêu tại sao lineItems phải lưu unitPrice riêng, kể cả khi lab_products đã có price. Sau đó thử đổi price của p001 và quan sát total của o001 vẫn là **186.000 VND**.

Gợi ý thao tác cho bài 2 và bài 4:

~~~javascript
// Bài 2
lab.getCollection("lab_orders")
  .find(
    { dataset: "practice-v1", "lineItems.productId": "p003" },
    { _id: 1 }
  )
  .sort({ _id: 1 })
  .toArray();

// Bài 4
lab.getCollection("lab_products").updateOne(
  { _id: "p001", dataset: "practice-v1" },
  { $set: { stock: NumberInt(1) } }
);
// Sau đó chạy lại seed_mongo_lab.js để khôi phục stock = 80.
~~~

Sau khi làm xong mỗi bài tập có thay đổi dữ liệu, chạy lại **seed_mongo_lab.js** để khôi phục trạng thái khởi đầu. Khi mọi người cùng dùng đúng bộ seed và quy ước trường dữ liệu, các bài CRUD, aggregation, index, liên kết bằng $lookup và xử lý cập nhật ở những phần sau đều có cùng điểm xuất phát và kết quả dễ đối chiếu.
