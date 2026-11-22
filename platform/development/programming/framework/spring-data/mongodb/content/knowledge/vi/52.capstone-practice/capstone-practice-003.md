# Dựng môi trường replica set và nạp dữ liệu mẫu

## 1. Mục tiêu của bài thực hành tổng hợp

Một ứng dụng **Spring Data MongoDB** có thể truy cập MongoDB bằng **MongoTemplate**, **MongoRepository**, **ReactiveMongoTemplate** hoặc repository reactive. Để thực hành thêm các tính năng như transaction, change stream và kiểm thử tích hợp, cần một môi trường MongoDB có topology phù hợp và bộ dữ liệu mẫu ổn định.

Bài này xây dựng một **single-node replica set** chạy bằng Docker Compose, khởi tạo một database bán hàng và nạp các collection **customers**, **products**, **orders**. Cuối bài, ứng dụng Spring có thể kết nối để chạy query, mapping document và các bài thực hành kế tiếp. Ngoài CRUD, ta thử một transaction bị rollback và quan sát một insert event qua change stream để xác nhận replica set thực sự hoạt động.

**Sau khi hoàn thành, người học cần tạo được:**

- Một MongoDB container chạy với **replSet = rs0** và thành viên đã đạt trạng thái **PRIMARY**.
- Database **shop_capstone** chứa **5 khách hàng, 6 sản phẩm, 8 đơn hàng** với ID và tổng tiền kiểm tra được.
- Index cho email, SKU và một số truy vấn đơn hàng.
- URI kết nối cho ứng dụng Spring Data MongoDB chạy **trên máy host**.
- Kết quả đọc dữ liệu từ **MongoTemplate/MongoRepository** và minh chứng transaction, change stream hoạt động.

**Phạm vi:** đây là môi trường **phát triển và học tập cục bộ**, dùng replica set một node, chưa bật authentication và không được coi là cấu hình an toàn cho production. Replica set một node hỗ trợ các bài test transaction/change stream cơ bản nhưng không kiểm chứng được failover, bầu primary thay thế hoặc độ trễ replication.

## 2. Kiến trúc và công cụ cần chuẩn bị

### 2.1. Kiến trúc

~~~mermaid
flowchart TB
    Host["Máy lập trình<br/>Spring Boot + Java"]
    CLI["Terminal<br/>docker compose / mongosh"]
    Port["127.0.0.1:27017<br/>published port"]
    RS[("MongoDB container<br/>mongod --replSet rs0<br/>Single PRIMARY + oplog")]
    Vol[("Named Docker volume<br/>mongo_rs_data")]
    DB["shop_capstone<br/>customers / products / orders"]
    Host -->|"mongodb://localhost:27017"| Port
    CLI -->|"docker compose exec"| RS
    Port --> RS
    RS --> Vol
    RS --> DB
~~~

**Điểm mấu chốt:** ứng dụng Spring trong bài chạy **trực tiếp trên máy host**, vì vậy MongoDB quảng bá địa chỉ thành viên replica set là **localhost:27017**. Nếu sau này chuyển Spring vào một container khác, phải đổi cách định tuyến và địa chỉ thành viên replica set; không thể sao chép nguyên URI **localhost** vào container ứng dụng rồi mong nó trỏ tới MongoDB.

### 2.2. Yêu cầu tối thiểu

| Công cụ | Mục đích | Cách tự kiểm tra |
| --- | --- | --- |
| Docker Engine / Docker Desktop | Chạy MongoDB container | **docker version** |
| Docker Compose v2 | Quản lý service và volume | **docker compose version** |
| Docker image MongoDB | Chạy **mongod** và **mongosh** bên trong container | **docker compose pull mongo** |
| JDK tương thích với dự án | Chạy ứng dụng Spring Boot | **java -version** |
| Maven/Gradle wrapper của dự án | Build và chạy ứng dụng | **mvnw / gradlew** theo hệ điều hành |
| Terminal/PowerShell | Tạo hai file ví dụ và thao tác container | Terminal hiện tại |

Các ví dụ bên dưới sử dụng image **mongo:7.0**, Spring Boot dòng **3.x** và Spring Data MongoDB tương thích. Đây là **phiên bản minh họa**, không phải tuyên bố về bản mới nhất. Với một dự án đang dùng Boot/driver/server khác, cần đối chiếu ma trận tương thích và kiểm tra API, property cấu hình theo phiên bản đó.

### 2.3. Hai file tự tạo cho bài thực hành

Trong một thư mục bài tập độc lập, tạo:

~~~text
mongo-capstone/
├── compose.yaml
└── seed.js
~~~

Các đoạn dưới đây là **nội dung mẫu của file**, người học có thể sao chép vào thư mục thực hành của mình. Không cần sửa source code Spring Data MongoDB để khởi động database ban đầu.

## 3. Tạo một MongoDB replica set bằng Docker Compose

### 3.1. Nội dung compose.yaml

~~~yaml
services:
  mongo:
    image: mongo:7.0
    command:
      - mongod
      - --replSet
      - rs0
      - --bind_ip_all
    ports:
      # Chỉ publish tới loopback của máy lập trình.
      - "127.0.0.1:27017:27017"
    volumes:
      - mongo_rs_data:/data/db
    restart: unless-stopped

volumes:
  mongo_rs_data:
~~~

**Giải thích cấu hình:**

1. **--replSet rs0** làm mongod chạy ở chế độ thành viên replica set tên **rs0**, nhưng **chưa khởi tạo** cấu hình thành viên.
2. **--bind_ip_all** cho phép process lắng nghe qua mạng bên trong container. **ports** chỉ đưa cổng ra địa chỉ loopback của host để phục vụ bài thực hành.
3. **mongo_rs_data** là named volume lưu data files. Xóa container thông thường không xóa dữ liệu trong volume.
4. **restart: unless-stopped** giúp container khởi động lại khi Docker khởi động, nhưng không bảo đảm mongod đã ở trạng thái **PRIMARY** ngay khi cổng TCP mở.

**Không có username/password hoặc TLS trong cấu hình này.** Chỉ sử dụng trong môi trường phát triển riêng có kiểm soát. Không publish port ra **0.0.0.0** trên máy dùng chung hoặc triển khai nguyên cấu hình này lên server có thể truy cập công khai.

### 3.2. Khởi chạy container

Từ thư mục chứa **compose.yaml**:

~~~bash
docker compose up -d
docker compose ps
docker compose logs mongo
~~~

Chạy shell MongoDB ngay bên trong container:

~~~bash
docker compose exec mongo mongosh
~~~

Lúc này **mongod** đang chạy với cờ replica set nhưng có thể **chưa được initiate**. Bước tiếp theo cần thực hiện đúng một lần cho volume dữ liệu mới.

### 3.3. Khởi tạo replica set

Trong cửa sổ **mongosh** vừa mở:

~~~javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "localhost:27017" }
  ]
});
~~~

Kết quả thành công thường có **ok: 1**. Replica set cần một khoảng thời gian ngắn để hoàn tất bầu primary; kiểm tra trạng thái thay vì đoán đã sẵn sàng:

~~~javascript
rs.status();
db.hello();
~~~

Kỳ vọng:

~~~text
Replica set name: rs0
Single member state: PRIMARY
db.hello().isWritablePrimary: true
~~~

Có thể kiểm tra trực tiếp biểu thức:

~~~javascript
db.hello().setName
db.hello().isWritablePrimary
rs.status().members.map(m => ({
  name: m.name,
  state: m.stateStr
}))
~~~

**Chỉ thực hiện rs.initiate trên replica set chưa có cấu hình.** Nếu volume đã dùng và **rs.status()** cho thấy một replica set hợp lệ, không chạy initiate lại. Nếu gặp lỗi **already initialized**, cần kiểm tra trạng thái hiện tại, không tự xóa dữ liệu để chạy lại lệnh.

### 3.4. Vì sao hostname phải là localhost trong ví dụ này?

MongoDB driver không chỉ kết nối tới địa chỉ ban đầu. Với replica set URI, driver **khám phá topology** và dùng địa chỉ thành viên được replica set công bố. Trong ví dụ này, ứng dụng chạy trên host nên cần địa chỉ **localhost:27017** có thể truy cập từ host.

| Ứng dụng chạy ở đâu? | Địa chỉ có thể dùng trong topology | Cần lưu ý |
| --- | --- | --- |
| Trên cùng máy host với Docker | **localhost:27017** | Phù hợp với cấu hình đang hướng dẫn |
| Trong container khác cùng Compose network | Tên DNS nội bộ như **mongo:27017** | Cần cấu hình địa chỉ replica set mà client đó phân giải được |
| Trên máy khác | Hostname/IP được cả client và các thành viên truy cập | Cần thiết kế mạng, TLS và auth phù hợp |

Khi đổi từ host sang container, phải thiết kế lại **advertised hostname** và URI một cách nhất quán, hoặc sử dụng môi trường Testcontainers được thiết kế cho ngữ cảnh test. **directConnection=true** có thể hữu ích cho một số tình huống chẩn đoán đơn node, nhưng không phải cách khắc phục tổng quát cho hostname replica set sai trong một hệ thống nhiều node.

## 4. Chuẩn bị database và mô hình dữ liệu mẫu

### 4.1. Chọn mô hình gần với nghiệp vụ thật

Database **shop_capstone** gồm ba collection:

| Collection | Nội dung | Ví dụ thao tác |
| --- | --- | --- |
| **customers** | Mã khách hàng, tên, email, ngày tạo | Tìm theo email, mapping entity |
| **products** | SKU, tên sản phẩm, giá tính bằng đơn vị nhỏ nhất, tồn kho | Index unique, update stock |
| **orders** | Khách hàng, trạng thái, các dòng hàng, tổng tiền và ngày tạo | Derived query, aggregation, transaction, change stream |

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : "customerId"
    ORDERS ||--|{ ORDER_ITEMS : "items"
    PRODUCTS ||--o{ ORDER_ITEMS : "productId"
    CUSTOMERS {
        string _id
        string name
        string email
        date createdAt
    }
    PRODUCTS {
        string _id
        string sku
        string name
        long priceCents
        int stock
    }
    ORDERS {
        string _id
        string customerId
        string status
        long totalCents
        date createdAt
    }
    ORDER_ITEMS {
        string productId
        int quantity
        long unitPriceCents
    }
~~~

**Các liên kết customerId/productId là tham chiếu bằng ID trong dữ liệu nghiệp vụ**, không phải foreign key do MongoDB tự enforce. Các **order items** được lưu nhúng trong document đơn hàng. Ví dụ này lưu snapshot **unitPriceCents** vào từng dòng hàng để việc thay đổi giá sản phẩm về sau không làm biến đổi tổng tiền của đơn hàng đã tạo.

Để tránh sai số khi tính tiền, ví dụ sử dụng **NumberLong** trong mongosh và **long** trong Java. Tên **priceCents/unitPriceCents/totalCents** biểu thị số đơn vị tiền nhỏ nhất. Bộ dữ liệu dùng các số nguyên minh họa; nếu xây dựng hệ thống tiền VND thật, nên đặt tên đơn vị phù hợp và thống nhất chính sách làm tròn.

### 4.2. Các trường và quy tắc nhất quán

- Customer ID có dạng **C001**..., email phải duy nhất.
- Product ID có dạng **P001**..., SKU phải duy nhất.
- Order ID có dạng **O1001**..., trạng thái thuộc nhóm **PENDING**, **PAID**, **SHIPPED**, **DELIVERED**, **CANCELLED**.
- **totalCents** bằng tổng của **quantity × unitPriceCents** trong các dòng hàng; chưa tính thuế, phí giao hàng hoặc coupon.
- **createdAt** lưu dưới dạng **BSON Date** qua **ISODate**, tương ứng với **Instant** trong entity Java.

Không cần tạo quan hệ database hoặc transaction chỉ để nạp bộ dữ liệu này; mỗi document được insert/upsert độc lập. Transaction sẽ được kiểm thử sau khi replica set đã hoạt động.

## 5. Viết seed.js để nạp dữ liệu có thể chạy lặp lại

Để tránh tạo bản ghi trùng khi chạy seed nhiều lần, ta dùng **updateOne** với **$setOnInsert** và **upsert: true** cho các ID cố định. Bản ghi đã tồn tại được giữ nguyên; bản ghi thiếu sẽ được thêm. Cách này phù hợp cho một bộ dữ liệu khởi tạo, nhưng **không có mục đích cập nhật giá hoặc trạng thái của dữ liệu đã tồn tại**.

### 5.1. Toàn bộ nội dung seed.js

~~~javascript
// seed.js - chạy trong mongosh, không cần Spring Boot.
const shop = db.getSiblingDB("shop_capstone");

// Chỉ thêm document nếu chưa có _id tương ứng.
function insertMissing(collection, documents) {
  for (const item of documents) {
    const { _id, ...fields } = item;
    collection.updateOne(
      { _id },
      { $setOnInsert: fields },
      { upsert: true }
    );
  }
}

insertMissing(shop.customers, [
  {
    _id: "C001",
    name: "Nguyễn Mai",
    email: "mai@example.test",
    createdAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: "C002",
    name: "Trần Bình",
    email: "binh@example.test",
    createdAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: "C003",
    name: "Lê An",
    email: "an@example.test",
    createdAt: ISODate("2026-10-03T08:00:00Z")
  },
  {
    _id: "C004",
    name: "Phạm Linh",
    email: "linh@example.test",
    createdAt: ISODate("2026-10-04T08:00:00Z")
  },
  {
    _id: "C005",
    name: "Võ Khoa",
    email: "khoa@example.test",
    createdAt: ISODate("2026-10-05T08:00:00Z")
  }
]);

insertMissing(shop.products, [
  {
    _id: "P001", sku: "KEY-001",
    name: "Mechanical Keyboard",
    priceCents: NumberLong(1299000), stock: 15
  },
  {
    _id: "P002", sku: "MOU-001",
    name: "Wireless Mouse",
    priceCents: NumberLong(499000), stock: 25
  },
  {
    _id: "P003", sku: "HUB-001",
    name: "USB-C Hub",
    priceCents: NumberLong(799000), stock: 12
  },
  {
    _id: "P004", sku: "STD-001",
    name: "Laptop Stand",
    priceCents: NumberLong(349000), stock: 30
  },
  {
    _id: "P005", sku: "MON-001",
    name: "Monitor 27 inch",
    priceCents: NumberLong(3999000), stock: 8
  },
  {
    _id: "P006", sku: "CAB-001",
    name: "USB-C Cable",
    priceCents: NumberLong(149000), stock: 40
  }
]);

insertMissing(shop.orders, [
  {
    _id: "O1001", customerId: "C001", status: "PAID",
    items: [
      { productId: "P001", quantity: 1,
        unitPriceCents: NumberLong(1299000) },
      { productId: "P002", quantity: 2,
        unitPriceCents: NumberLong(499000) }
    ],
    totalCents: NumberLong(2297000),
    createdAt: ISODate("2026-10-10T09:00:00Z")
  },
  {
    _id: "O1002", customerId: "C002", status: "PENDING",
    items: [
      { productId: "P003", quantity: 1,
        unitPriceCents: NumberLong(799000) }
    ],
    totalCents: NumberLong(799000),
    createdAt: ISODate("2026-10-11T09:00:00Z")
  },
  {
    _id: "O1003", customerId: "C003", status: "SHIPPED",
    items: [
      { productId: "P005", quantity: 1,
        unitPriceCents: NumberLong(3999000) },
      { productId: "P006", quantity: 2,
        unitPriceCents: NumberLong(149000) }
    ],
    totalCents: NumberLong(4297000),
    createdAt: ISODate("2026-10-12T09:00:00Z")
  },
  {
    _id: "O1004", customerId: "C001", status: "CANCELLED",
    items: [
      { productId: "P004", quantity: 2,
        unitPriceCents: NumberLong(349000) }
    ],
    totalCents: NumberLong(698000),
    createdAt: ISODate("2026-10-13T09:00:00Z")
  },
  {
    _id: "O1005", customerId: "C004", status: "PAID",
    items: [
      { productId: "P002", quantity: 1,
        unitPriceCents: NumberLong(499000) },
      { productId: "P003", quantity: 1,
        unitPriceCents: NumberLong(799000) }
    ],
    totalCents: NumberLong(1298000),
    createdAt: ISODate("2026-10-14T09:00:00Z")
  },
  {
    _id: "O1006", customerId: "C005", status: "PENDING",
    items: [
      { productId: "P006", quantity: 3,
        unitPriceCents: NumberLong(149000) }
    ],
    totalCents: NumberLong(447000),
    createdAt: ISODate("2026-10-15T09:00:00Z")
  },
  {
    _id: "O1007", customerId: "C002", status: "PAID",
    items: [
      { productId: "P001", quantity: 1,
        unitPriceCents: NumberLong(1299000) }
    ],
    totalCents: NumberLong(1299000),
    createdAt: ISODate("2026-10-16T09:00:00Z")
  },
  {
    _id: "O1008", customerId: "C003", status: "DELIVERED",
    items: [
      { productId: "P004", quantity: 1,
        unitPriceCents: NumberLong(349000) },
      { productId: "P006", quantity: 1,
        unitPriceCents: NumberLong(149000) }
    ],
    totalCents: NumberLong(498000),
    createdAt: ISODate("2026-10-17T09:00:00Z")
  }
]);

// Chỉ số duy nhất bảo vệ các khóa nghiệp vụ.
shop.customers.createIndex(
  { email: 1 },
  { unique: true, name: "ux_customers_email" }
);
shop.products.createIndex(
  { sku: 1 },
  { unique: true, name: "ux_products_sku" }
);

// Chỉ số hỗ trợ các kiểu truy vấn thường dùng.
shop.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "ix_orders_customer_created" }
);
shop.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "ix_orders_status_created" }
);

printjson({
  database: shop.getName(),
  customers: shop.customers.countDocuments({}),
  products: shop.products.countDocuments({}),
  orders: shop.orders.countDocuments({})
});
~~~

**Vì sao dùng trường _id là chuỗi?** Các mã **C001**, **P001**, **O1001** giúp dễ kiểm tra bằng mắt. Spring Data MongoDB có thể chuyển một số giá trị String **@Id** có dạng ObjectId hợp lệ thành BSON ObjectId; các mã trong bài không có dạng đó nên được lưu dưới dạng String. Nếu ứng dụng thật sử dụng ObjectId, cần thống nhất kiểu BSON và Java thay vì suy từ định dạng ID ở bài tập.

### 5.2. Chạy file seed

Trong thư mục **mongo-capstone**:

~~~bash
# Sao chép file từ host vào filesystem của container.
docker compose cp ./seed.js mongo:/tmp/seed.js

# Chạy bằng mongosh bên trong container.
docker compose exec mongo mongosh /tmp/seed.js
~~~

Cách dùng **docker compose cp** tránh phụ thuộc cú pháp redirect input khác nhau giữa Bash và Windows PowerShell. File được copy vào container chỉ phục vụ thực thi seed; dữ liệu thật nằm trong MongoDB volume.

Đầu ra mong đợi sau khi chạy lần đầu:

~~~text
{
  database: 'shop_capstone',
  customers: 5,
  products: 6,
  orders: 8
}
~~~

Chạy lại cùng file seed sẽ **không tạo thêm document** có ID trùng. Tuy nhiên nếu đã thử tạo thêm khách hàng, sản phẩm hoặc đơn hàng trong quá trình học, số lượng có thể lớn hơn các giá trị trên. Hãy phân biệt **môi trường mới vừa seed** với môi trường đã được chỉnh sửa.

**Không dùng dropDatabase() trong script seed chạy hằng ngày.** Khi muốn thực hành lại từ đầu, nên dùng một volume chuyên dành cho bài tập và hiểu rõ thao tác xóa volume là mất dữ liệu.

## 6. Xác minh dữ liệu mẫu bằng mongosh

Mở shell:

~~~bash
docker compose exec mongo mongosh
~~~

Chọn database:

~~~javascript
use shop_capstone

db.customers.countDocuments({})
db.products.countDocuments({})
db.orders.countDocuments({})
~~~

Trong một môi trường mới chỉ seed, kết quả lần lượt là:

~~~text
5
6
8
~~~

### 6.1. Truy vấn một đơn hàng và kiểm tra tổng tiền

~~~javascript
db.orders.findOne({ _id: "O1001" });
~~~

Đơn **O1001** có một bàn phím giá **1.299.000** và hai chuột giá **499.000**:

~~~text
1 × 1.299.000 + 2 × 499.000 = 2.297.000
~~~

Kiểm tra tổng tiền của **tất cả** đơn bằng aggregation:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      totalCents: 1,
      calculatedCents: {
        $sum: {
          $map: {
            input: "$items",
            as: "line",
            in: {
              $multiply: [
                "$$line.quantity",
                "$$line.unitPriceCents"
              ]
            }
          }
        }
      }
    }
  },
  {
    $match: {
      $expr: { $ne: ["$totalCents", "$calculatedCents"] }
    }
  }
]);
~~~

Nếu bộ dữ liệu mẫu chưa bị chỉnh sửa, truy vấn trên phải trả **không document nào**: mọi tổng tiền đều khớp dòng hàng. Đây là kiểm tra dữ liệu nghiệp vụ, không chỉ đếm số lượng bản ghi.

### 6.2. Tổng hợp số đơn và tổng tiền theo trạng thái

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      amountCents: { $sum: "$totalCents" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Kết quả kỳ vọng:

| Trạng thái | Số đơn | Tổng amountCents |
| --- | ---: | ---: |
| **CANCELLED** | 1 | 698000 |
| **DELIVERED** | 1 | 498000 |
| **PAID** | 3 | 4894000 |
| **PENDING** | 2 | 1246000 |
| **SHIPPED** | 1 | 4297000 |
| **Tất cả** | **8** | **11633000** |

**Tổng amountCents** trong bảng là tổng giá trị các đơn của từng trạng thái, **không phải doanh thu kế toán**: đơn CANCELLED/PENDING và có thể cả đơn chưa hoàn tất không được tính là doanh thu thực tế.

### 6.3. Kiểm tra index

~~~javascript
db.customers.getIndexes();
db.products.getIndexes();
db.orders.getIndexes();

db.orders.find({ customerId: "C001" })
  .sort({ createdAt: -1 })
  .explain("executionStats");
~~~

Kỳ vọng **orders** có index **ix_orders_customer_created** và **ix_orders_status_created**, bên cạnh index mặc định của **_id**. Trong kế hoạch explain, xem **winning plan**, **totalDocsExamined** và **nReturned** để biết truy vấn thực tế chọn index nào.

Với dữ liệu mẫu chỉ có tám đơn, MongoDB có thể chọn collection scan cho một số truy vấn vì chi phí rất nhỏ. **Không khẳng định index được sử dụng chỉ dựa vào việc index tồn tại**; cần đọc explain của môi trường thực tế.

## 7. Kết nối từ Spring Data MongoDB

### 7.1. Connection string trên máy host

Với Spring Boot 3.x, cấu hình minh họa trong **application.yml**:

~~~yaml
spring:
  data:
    mongodb:
      uri: "mongodb://localhost:27017/shop_capstone?replicaSet=rs0"
~~~

**replicaSet=rs0** yêu cầu driver nhận diện topology tương ứng. URI sử dụng database **shop_capstone** làm database mặc định của ứng dụng. Nếu dùng phiên bản Spring Boot có tên property MongoDB thay đổi, cần xem tài liệu configuration properties của đúng phiên bản thay vì sao chép nguyên YAML.

### 7.2. Khai báo document Java

Ví dụ có thể tách thành các file riêng trong package của ứng dụng:

~~~java
// Customer.java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("customers")
public record Customer(
    @Id String id,
    String name,
    String email,
    Instant createdAt
) {}
~~~

~~~java
// Product.java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("products")
public record Product(
    @Id String id,
    String sku,
    String name,
    long priceCents,
    int stock
) {}
~~~

~~~java
// OrderLine.java
public record OrderLine(
    String productId,
    int quantity,
    long unitPriceCents
) {}
~~~

~~~java
// ShopOrder.java
import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
public record ShopOrder(
    @Id String id,
    String customerId,
    String status,
    List<OrderLine> items,
    long totalCents,
    Instant createdAt
) {}
~~~

**Tên class ShopOrder** được chọn để tránh trùng với **Order** trong các thư viện khác. Document seed không có trường **_class**, nhưng vì repository yêu cầu kiểu đích cụ thể **ShopOrder**, dữ liệu vẫn có thể được ánh xạ theo các field tương ứng. Khi ghi dữ liệu mới bằng Spring Data, converter mặc định có thể bổ sung **_class**; cần lưu ý nếu nhiều ứng dụng cùng quản lý BSON schema.

### 7.3. Repository và truy vấn

~~~java
// ShopOrderRepository.java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ShopOrderRepository
        extends MongoRepository<ShopOrder, String> {

    List<ShopOrder> findByCustomerIdOrderByCreatedAtDesc(
        String customerId
    );

    long countByStatus(String status);
}
~~~

~~~java
// ShopQueryService.java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ShopQueryService {
    private final ShopOrderRepository orders;
    private final MongoTemplate mongoTemplate;

    public ShopQueryService(
        ShopOrderRepository orders,
        MongoTemplate mongoTemplate
    ) {
        this.orders = orders;
        this.mongoTemplate = mongoTemplate;
    }

    public List<ShopOrder> ordersOfCustomer(String customerId) {
        return orders.findByCustomerIdOrderByCreatedAtDesc(customerId);
    }

    public List<ShopOrder> paidOrders() {
        Query query = Query.query(
            Criteria.where("status").is("PAID")
        );
        return mongoTemplate.find(query, ShopOrder.class);
    }
}
~~~

Hai cách truy vấn này sử dụng cùng database/collection. **MongoRepository** thuận tiện cho derived query, còn **MongoTemplate** hữu ích khi cần xây filter, aggregation, update hoặc transaction cụ thể.

### 7.4. Kiểm thử đọc dữ liệu đã seed

Với ứng dụng Spring Boot đã có dependency **spring-boot-starter-data-mongodb** và **spring-boot-starter-test**, có thể tạo integration test:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;

@DataMongoTest
class SampleDataIntegrationTest {

    @Autowired
    ShopOrderRepository repository;

    @Test
    void canReadSeededOrderAndLines() {
        ShopOrder order =
            repository.findById("O1001").orElseThrow();

        assertEquals("C001", order.customerId());
        assertEquals("PAID", order.status());
        assertEquals(2, order.items().size());
        assertEquals(2_297_000L, order.totalCents());
    }

    @Test
    void canReadAllPaidOrders() {
        assertEquals(3L, repository.countByStatus("PAID"));
    }
}
~~~

**Đây là integration test có điều kiện:** trước khi chạy phải có MongoDB replica set và dữ liệu seed đúng như bài, Spring context phải được cấu hình kết nối **shop_capstone**. **@DataMongoTest** tự cấu hình phần MongoDB cần kiểm thử nhưng không tự tạo dữ liệu mẫu hoặc server. Nếu dự án sử dụng Boot 4.x, package annotation slice test có thể đã thay đổi; cần theo đúng API của phiên bản đang dùng.

Vì test đọc dữ liệu seed ở một database được chia sẻ, **không chạy song song với bài tập đang sửa đơn hàng**. Khi cần chạy độc lập trong CI, hãy khởi tạo database test riêng và chạy seed tự động trước test, hoặc dùng Testcontainers với replica set phù hợp.

## 8. Xác minh khả năng transaction bằng mongosh

Một replica set có thể báo **PRIMARY** nhưng cấu hình application service vẫn sai. Trước khi viết service phức tạp, ta chạy một smoke test nhỏ để xác minh khả năng sử dụng transaction từ MongoDB.

### 8.1. Chuẩn bị collection ngoài transaction

Trong **mongosh**:

~~~javascript
const shop = db.getSiblingDB("shop_capstone");
if (!shop.getCollectionNames().includes("tx_probe")) {
  shop.createCollection("tx_probe");
}
~~~

Tạo collection trước giúp bài test tập trung vào semantics rollback, tránh phụ thuộc những điều kiện/version liên quan tới tạo collection ngầm bên trong transaction.

### 8.2. Ghi rồi abort

~~~javascript
const probeId = "TX-" + new ObjectId().toString();
const session = db.getMongo().startSession();

try {
  session.startTransaction();
  session.getDatabase("shop_capstone")
    .getCollection("tx_probe")
    .insertOne({
      _id: probeId,
      kind: "ROLLBACK_CHECK",
      at: new Date()
    });

  session.abortTransaction();
} finally {
  session.endSession();
}

shop.tx_probe.countDocuments({ _id: probeId });
~~~

Kết quả mong đợi là **0**, vì document được insert trong transaction đã bị abort. Đây là smoke test của MongoDB server; nó **chưa xác minh @Transactional trong Spring**. Với Spring Data MongoDB đồng bộ, cần cấu hình **MongoTransactionManager** và test service thông qua Spring proxy. Với reactive access, cần **ReactiveMongoTransactionManager** và kiểm thử theo reactive transaction context.

Muốn kiểm thử đầy đủ, nên có hai case riêng: **commit thành công** khiến nhiều document cùng xuất hiện và **runtime failure** khiến tất cả thao tác trong transaction bị rollback. Không nên chỉ assert rằng transaction không ném exception.

## 9. Xác minh change stream bằng hai cửa sổ mongosh

Change stream cần có subscriber/cursor **đang quan sát trước khi tạo thay đổi**. Nếu insert trước rồi mới gọi watch, test có thể không nhận event đã xảy ra.

### 9.1. Cửa sổ A: mở stream

Mở mongosh:

~~~bash
docker compose exec mongo mongosh
~~~

Chạy:

~~~javascript
const shop = db.getSiblingDB("shop_capstone");
if (!shop.getCollectionNames().includes("stream_probe")) {
  shop.createCollection("stream_probe");
}

const stream = shop.stream_probe.watch([
  { $match: { operationType: "insert" } }
]);

while (stream.hasNext()) {
  printjson(stream.next());
}
~~~

**Vòng lặp sẽ chờ event**. Giữ cửa sổ A mở trong khi thực hiện bước tiếp theo.

### 9.2. Cửa sổ B: tạo một thay đổi mới

Mở một mongosh thứ hai và chạy:

~~~javascript
db.getSiblingDB("shop_capstone")
  .getCollection("stream_probe")
  .insertOne({
    _id: "EV-" + new ObjectId().toString(),
    kind: "REPLICA_CHECK",
    createdAt: new Date()
  });
~~~

Quay lại cửa sổ A. Kỳ vọng có event với **operationType = "insert"**, **ns.coll = "stream_probe"** và **fullDocument.kind = "REPLICA_CHECK"**. Trường **_id** của event chứa **resume token**, khác với **fullDocument._id**. Dừng vòng lặp ở cửa sổ A bằng **Ctrl+C**.

Khi dùng **ReactiveMongoTemplate.changeStream(...)** hoặc **ChangeStreamOptions**, cần bảo đảm có subscription thực sự và stream đã mở trước thao tác ghi. Một biến **Flux** chưa được subscribe không tự bảo đảm đang nhận event. Trong test tự động, dùng timeout hữu hạn, lọc theo document ID và đóng cursor/subscription.

## 10. Bộ kiểm tra dữ liệu mẫu từ ứng dụng

Khi kết hợp nhiều phần của module, hãy tạo một service kiểm tra dữ liệu trước khi viết transaction hoặc aggregation phức tạp:

| Điều kiện | Truy vấn / API kiểm tra | Kỳ vọng sau seed ban đầu |
| --- | --- | --- |
| Server là replica set đã khởi tạo | **rs.status()** | Set **rs0**, một member **PRIMARY** |
| Server chấp nhận ghi | **db.hello().isWritablePrimary** | **true** |
| Customer đủ dữ liệu | **customers.countDocuments({})** | **5** |
| Product đủ dữ liệu | **products.countDocuments({})** | **6** |
| Order đủ dữ liệu | **orders.countDocuments({})** | **8** |
| Số đơn PAID | **orders.countDocuments({status:"PAID"})** | **3** |
| Tổng giá trị tất cả đơn | Aggregation **$group/$sum** | **11633000** |
| Không có order sai tổng tiền | So sánh totalCents với từng dòng hàng | **0 document sai** |
| Entity mapping hoạt động | **findById("O1001")** | **totalCents = 2297000**, có 2 items |
| Transaction abort hoạt động | **tx_probe** theo probeId | **0 document** |
| Change stream hoạt động | Stream nhận event insert | Có một event **REPLICA_CHECK** |

**Cách nhận định kết quả:** nếu đếm thiếu document, hãy kiểm tra seed trước. Nếu mongosh đọc dữ liệu đúng nhưng Spring không đọc được, kiểm tra database trong URI, mapping **@Document/@Id**, kiểu field hoặc converter. Nếu truy vấn thường hoạt động nhưng transaction/change stream lỗi, ưu tiên kiểm tra topology và session.

## 11. Các lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh / xử lý |
| --- | --- | --- |
| **Connection refused** tới localhost:27017 | Container chưa chạy, port không được publish hoặc đã bị tiến trình khác chiếm | **docker compose ps**, **docker compose logs mongo**, kiểm tra cổng |
| **ReplicaSetNoPrimary** hoặc server selection timeout | Chưa initiate, chưa bầu PRIMARY, tên replica set sai hoặc advertised hostname không kết nối được | **rs.status()**, **db.hello()**, kiểm tra URI và hostname |
| Driver nhận host **mongo:27017** nhưng app chạy trên host | Tên DNS Docker không phân giải trên host | Cấu hình topology theo địa chỉ mà client thực sự truy cập |
| App chạy trong container kết nối **localhost:27017** | localhost trong app container là chính app container | Thiết kế lại networking/replica set hostname, không dùng URI host nguyên trạng |
| **Transaction numbers are only allowed on a replica set member or mongos** | Ứng dụng đang kết nối standalone hoặc sai deployment | Kiểm tra URI và trạng thái replica set thực tế |
| **$changeStream is only supported on replica sets** | MongoDB chưa chạy ở topology hỗ trợ change stream | Kiểm tra **--replSet**, **rs.initiate** và server |
| Nạp seed lần thứ hai không đổi dữ liệu đã sửa | Dùng **$setOnInsert** nên chỉ thêm document chưa có | Đây là hành vi chủ ý; không nhầm với overwrite/migration |
| **DuplicateKey** ở email hoặc SKU | Dữ liệu đã có giá trị unique trùng nhưng khác ID | Kiểm tra collection, dữ liệu cũ và index trước khi nhập |
| Seed đã chạy nhưng Spring thấy 0 orders | URI trỏ database khác hoặc không đúng replica set | So sánh **shop_capstone** trong URI với **db.getName()** |
| Spring đọc sai kiểu ngày/tiền | BSON seed khác kiểu Java hoặc tùy biến converter không nhất quán | Xem raw document, **ISODate/NumberLong**, mapping entity |
| Test transaction vẫn thấy document sau lỗi | Chưa dùng transaction manager, self-invocation hoặc ghi ngoài transaction | Kiểm tra **MongoTransactionManager**, proxy/session và trạng thái MongoDB |
| Change stream không nhận event | Bắt đầu watch sau khi ghi hoặc cursor/subscriber chưa sẵn sàng | Mở observer trước, dùng hai cửa sổ và deadline |
| **docker compose cp** không tìm thấy service | Sai thư mục Compose, service chưa chạy hoặc tên service khác | Chạy từ thư mục có **compose.yaml**, kiểm tra **docker compose ps** |
| Test khác làm thay đổi số lượng dữ liệu | Dùng chung database cho nhiều bài, seed không reset | Dùng database/volume riêng cho test, thống nhất quy trình cleanup |

### 11.1. Cần xem gì trong log?

~~~bash
docker compose ps
docker compose logs mongo
docker compose exec mongo mongosh
~~~

Trong mongosh:

~~~javascript
rs.status();
db.hello();
db.getSiblingDB("shop_capstone").orders.countDocuments({});
~~~

Không suy ra replica set đã sẵn sàng chỉ vì **docker compose ps** hiển thị container đang chạy. Trạng thái **PRIMARY** là điều kiện quan trọng cho các bài test ghi và transaction.

### 11.2. Muốn dùng hostname khác localhost?

Cần bảo đảm địa chỉ trong **rs.conf()** có thể được tất cả client liên quan phân giải và kết nối. Với nhiều container, có thể dùng tên dịch vụ trên một mạng Docker thống nhất; với host bên ngoài, cần DNS/routing phù hợp. Việc đổi hostname replica set bằng **rs.reconfig()** là thao tác thay đổi topology và cần thực hiện theo tài liệu đúng phiên bản, không tùy tiện thử trên dữ liệu quan trọng.

## 12. Dọn môi trường, chạy lại và bảo toàn dữ liệu

Khi kết thúc buổi học:

~~~bash
# Dừng và gỡ container/network do Compose tạo.
docker compose down
~~~

Lệnh **docker compose down** thông thường **giữ named volume**. Vì vậy khi chạy lại:

~~~bash
docker compose up -d
~~~

MongoDB đọc lại dữ liệu và cấu hình replica set từ volume. **Không cần rs.initiate lần nữa** nếu volume cũ vẫn còn và cấu hình hợp lệ.

Nếu muốn xóa **toàn bộ dữ liệu bài tập** và khởi tạo lại từ đầu, một thao tác như **docker compose down -v** sẽ xóa named volume của project cùng dữ liệu MongoDB bên trong. Chỉ dùng với volume **dành riêng cho bài thực hành**, sau khi xác minh không chứa dữ liệu cần giữ. Đây là thao tác phá hủy dữ liệu, không phải bước bắt buộc của bài.

Khi tổ chức CI, nên dùng database và container riêng cho job, tự seed rồi teardown ở cuối. Với môi trường production, cần authentication, TLS, backup, giám sát và replica set có nhiều thành viên theo nhu cầu khả dụng; không triển khai nguyên compose học tập này.

## 13. Bài tập mở rộng sau khi hoàn thành môi trường

### Bài tập A — Derived query và index

Viết repository method lấy đơn của khách hàng **C001** theo **createdAt** giảm dần. Kỳ vọng hai đơn: **O1004** rồi **O1001**. Dùng **explain** để quan sát kế hoạch query và index; không ép kết luận rằng bộ dữ liệu tám đơn luôn sử dụng index.

### Bài tập B — Aggregation theo customer

Tạo pipeline nhóm đơn theo **customerId**, đếm số đơn và tổng tiền; sau đó **$lookup** sang customers để trả tên khách hàng. Đối chiếu số đơn của **C001** bằng 2 và tiền cộng dồn bằng **2995000**.

### Bài tập C — Transaction cập nhật tồn kho

Viết service sử dụng **MongoTransactionManager** để đồng thời tạo đơn mới và giảm tồn kho của sản phẩm. Kiểm tra tồn kho trước và sau khi transaction commit; tạo tình huống lỗi để chứng minh rollback không để lại đơn hàng dở dang. Với production cần thiết kế **update có điều kiện** tránh oversell khi nhiều yêu cầu chạy đồng thời.

### Bài tập D — Change stream và consumer

Viết consumer lắng nghe insert trên **orders**. Ghi một đơn mới qua MongoTemplate; xác minh consumer nhận event đúng ID. Thêm checkpoint **resume token** hoặc cơ chế xử lý idempotent nếu muốn thực hành việc khởi động lại consumer.

### Bài tập E — Reactive access

Nếu ứng dụng dùng **ReactiveMongoTemplate** hoặc **ReactiveMongoRepository**, xây endpoint trả **Flux<ShopOrder>** cho đơn PAID và test bằng **StepVerifier**. Phần reactive vẫn kết nối tới cùng server, nhưng sử dụng reactive MongoDB driver và API phù hợp; không trộn transaction manager đồng bộ vào luồng reactive.

## 14. Checklist nghiệm thu

Đánh dấu các mục sau khi chạy trên môi trường thực tế của mình:

- [ ] Container MongoDB khởi chạy thành công từ **compose.yaml**.
- [ ] **rs.status()** cho thấy replica set **rs0** với một **PRIMARY**.
- [ ] **db.hello().isWritablePrimary** trả **true**.
- [ ] Chạy **seed.js** thành công và chạy lại không nhân đôi dữ liệu.
- [ ] Database **shop_capstone** có **5 customers**, **6 products** và **8 orders** trong môi trường mới seed.
- [ ] Các index unique và index tra cứu trên **orders** đã xuất hiện.
- [ ] Aggregation kiểm tra tổng tiền không phát hiện đơn có tổng sai.
- [ ] Tổng tiền tất cả đơn là **11633000**; có **3 đơn PAID**.
- [ ] Spring Data MongoDB đọc được đơn **O1001** qua repository và MongoTemplate.
- [ ] Transaction smoke test sau **abort** không để lại document.
- [ ] Change stream nhận được insert event khi cửa sổ watcher mở trước thao tác ghi.
- [ ] Đã ghi nhận URI, phiên bản MongoDB và các lỗi cấu hình nếu có để tái lập bài tập.

## Kết luận

Một môi trường **single-node replica set** đủ cho nhiều bài thực hành tổng hợp với **Spring Data MongoDB**, từ ánh xạ document và repository query đến kiểm tra **transaction** và **change stream**. Điều quyết định là server đã trở thành **PRIMARY**, URI phù hợp với hostname mà replica set quảng bá và bộ dữ liệu seed có thể kiểm tra, chạy lặp lại. Với **customers, products, orders** đã nạp, người học có nền tảng để tiếp tục thực hành **MongoTemplate**, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng bằng những tình huống dữ liệu cụ thể.

### Tài liệu tham khảo

- [MongoDB — Deploy a Replica Set](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set/)
- [MongoDB — rs.initiate()](https://www.mongodb.com/docs/manual/reference/method/rs.initiate/)
- [MongoDB — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [Spring Data MongoDB — Reference](https://docs.spring.io/spring-data/mongodb/reference/)
- [Docker Compose — Overview](https://docs.docker.com/compose/)
