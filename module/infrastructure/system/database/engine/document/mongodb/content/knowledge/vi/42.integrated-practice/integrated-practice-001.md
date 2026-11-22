# Khởi tạo môi trường và bộ dữ liệu ứng dụng bán hàng với MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chương:** Thực hành tổng hợp  
> **Bài học:** Khởi tạo môi trường và bộ dữ liệu ứng dụng bán hàng

## 1. Bối cảnh và kết quả cần đạt

Chúng ta sẽ xây dựng một môi trường thực hành MongoDB cho ứng dụng bán hàng nhỏ, gồm khách hàng, danh mục sản phẩm, sản phẩm, tồn kho, đơn hàng, thanh toán và một collection outbox để chuẩn bị cho bài thực hành giao dịch hoặc xử lý sự kiện.

Đây là bài **khởi tạo nền tảng thực hành**, không phải một website hoàn chỉnh. Kết quả cuối cùng là một database có dữ liệu mẫu, những index thiết yếu, các truy vấn kiểm tra và một kết nối Java có thể sử dụng cho các bài tập CRUD, aggregation, transaction và hiệu năng về sau.

### 1.1. Những thứ sẽ có sau bài

- Một MongoDB chạy riêng cho lab, khuyến nghị single-node replica set khi muốn thử transaction và change streams.
- Database `sales_lab` với bảy collections: `categories`, `customers`, `products`, `inventory`, `orders`, `payments` và `outbox`.
- Dữ liệu **giả lập, không chứa thông tin khách hàng thật**, seed có ID cố định.
- Giá tiền lưu bằng **số nguyên VND** dưới dạng BSON Int64, không dùng floating-point để đại diện số tiền trong ví dụ.
- Các timestamps dùng BSON Date theo UTC.
- Index phù hợp những truy vấn thường gặp, trong đó có unique index cho email, request ID và payment/order association.
- Kịch bản kiểm tra counts, data types, references, query plan và kết nối Java.
- Một ví dụ transaction đặt hàng trừ tồn kho, tạo order và ghi outbox cùng một commit.
- Các hướng mở rộng thành integration test, API và báo cáo doanh thu.

### 1.2. Phạm vi và giới hạn

Môi trường được thiết kế cho **development trên máy cá nhân**. Docker MongoDB trong ví dụ chỉ công bố cổng tới `127.0.0.1` của máy host, không bật authentication và **không được phép dùng nguyên cấu hình này trên máy production hoặc máy có người khác truy cập**.

Dữ liệu orders được seed như **lịch sử giả lập**; tồn kho là một snapshot độc lập nhằm phục vụ bài tập. Không suy ra:

```text
inventory.available
  = nhập kho - tổng quantity của 120 orders giả lập
```

vì bài seed chưa mô phỏng ledger nhập/xuất hàng từ đầu. Khi thử transaction sau này, ta bắt đầu từ snapshot hiện tại.

### 1.3. Sơ đồ mục tiêu

```text
                      sales_lab
                         │
    ┌────────────────────┼─────────────────────┐
    │                    │                     │
 categories           customers             products
    │                    │                     │
    └── categoryId ◄─────┼─────────────────────┤
                         │                     │
                  customerId                 sku/_id
                         │                     │
                         ▼                     ▼
                       orders                inventory
                         │
                  embedded items[]
                         │
                         ├───────► payments
                         │           orderId
                         │
                         └───────► outbox
                                     orderId
```

MongoDB không tự thực thi foreign-key constraints giống một RDBMS. Các chuỗi `customerId`, `categoryId`, `sku` và `orderId` là **tham chiếu ở cấp ứng dụng**; consistency phải được duy trì bằng service logic, giao dịch khi cần và kiểm thử dữ liệu.

---

## 2. Kiến trúc dữ liệu: nhúng hay tham chiếu?

Ứng dụng có nhiều quan hệ:

- Một category có nhiều products.
- Một customer có nhiều orders.
- Một order có nhiều line items.
- Một product có một tồn kho hiện tại cho demo.
- Một order có một payment record trong lab, nhưng hệ thống thật có thể có nhiều payment attempts.
- Một order có thể tạo một hoặc nhiều outbox events.

### 2.1. Quyết định cho lab

| Collection | `_id` | Thuộc tính chính | Quan hệ |
|---|---|---|---|
| `categories` | `CAT-01` | code, name | Products tham chiếu |
| `customers` | `CUS-001` | fullName, email, tier | Orders tham chiếu |
| `products` | `SKU-001` | categoryId, name, unitPriceVnd, active | Inventory và order items dùng SKU |
| `inventory` | `SKU-001` | available, reserved, updatedAt | Cùng key với product |
| `orders` | `ORD-0001` | requestId, customerId, items, totalVnd, status | Nhúng snapshot items |
| `payments` | `PAY-0001` | orderId, amountVnd, method, status | Order tham chiếu |
| `outbox` | `EVT-...` | eventType, aggregateId, payload, processed | Event phát sau commit |

### 2.2. Vì sao nhúng items trong orders?

Một line item của order cần snapshot **tên và giá tại thời điểm mua**. Nếu giá product thay đổi ngày mai, lịch sử đơn hàng vẫn phải ghi giá cũ.

Ví dụ:

```json
{
  "_id": "ORD-0001",
  "customerId": "CUS-002",
  "items": [
    {
      "sku": "SKU-001",
      "name": "Sản phẩm mẫu 001",
      "quantity": 2,
      "unitPriceVnd": {"$numberLong": "80000"},
      "lineTotalVnd": {"$numberLong": "160000"}
    }
  ],
  "totalVnd": {"$numberLong": "160000"}
}
```

Các `items[]` được nhúng bởi chúng thường được truy cập/cập nhật cùng order, kích thước giới hạn trong giao dịch bán hàng thông thường. Không nên nhúng toàn bộ lịch sử orders vào một customer document vì array sẽ tăng không giới hạn.

### 2.3. Vì sao tách inventory khỏi products?

Điều này tạo ra một tình huống thực hành transaction rõ ràng: trong checkout, phải cập nhật tồn kho và tạo order cùng một commit. Mô hình thật có thể đặt stock ngay trong product nếu pattern và invariants phù hợp; lựa chọn lab nhằm minh họa nhiều collections.

### 2.4. Vì sao tách payment?

Thanh toán có state và quyền truy cập khác order. Production thường cần payment attempts, gateway IDs và reconciliation; ví dụ ở đây đơn giản một payment cho một order PAID/SHIPPED, không lưu số thẻ, CVV hoặc dữ liệu nhạy cảm.

---

## 3. Công cụ và điều kiện tiên quyết

### 3.1. Phần mềm

Cần:

- Docker Engine hoặc Docker Desktop chạy được containers.
- Terminal: PowerShell, Command Prompt hoặc bash.
- `mongosh` thông qua Docker container (không bắt buộc cài trên máy host).
- Java 17+ và Maven/Gradle nếu làm các bài Java.
- IDE tùy chọn.
- Dung lượng disk trống cho MongoDB image, volume và dữ liệu test.

### 3.2. Phiên bản

Ví dụ lệnh dùng image:

```text
mongo:8.0
```

Đây là một **major-version tag cho môi trường học**, không phải lời khẳng định phiên bản mới nhất. Nếu project yêu cầu tái lập tuyệt đối, pin image patch release/digest và driver version. Đối chiếu MongoDB Server/Java Driver compatibility trước khi chạy trong stack thật.

### 3.3. Kiểm tra Docker

```bash
docker version
docker info
```

Nếu Docker chưa chạy, khởi động Docker Desktop/daemon rồi thử lại. Nếu port 27017 đang có MongoDB khác sử dụng, dùng một host port khác và sửa URI tương ứng.

### 3.4. Không cần Google Cloud hay MongoDB Atlas

Lab local đủ cho phần lớn thực hành. Nếu không thể chạy Docker, có thể dùng một MongoDB development deployment/Atlas sandbox do bạn sở hữu và có quyền tạo database/collections, nhưng phải thay URI và giới hạn quyền phù hợp.

---

## 4. Chạy MongoDB bằng Docker

### 4.1. Lệnh khởi động local replica set

Dùng một terminal trên máy host:

```bash
docker run -d --name sales-mongo \
  -p 127.0.0.1:27017:27017 \
  -v sales-mongo-data:/data/db \
  mongo:8.0 \
  --replSet rs0 --bind_ip_all
```

Trên Windows PowerShell 5.1, để tránh dấu xuống dòng của bash, nhập **một dòng**:

```powershell
docker run -d --name sales-mongo -p 127.0.0.1:27017:27017 -v sales-mongo-data:/data/db mongo:8.0 --replSet rs0 --bind_ip_all
```

Giải thích:

| Thành phần | Ý nghĩa |
|---|---|
| `--name sales-mongo` | Tên container |
| `-p 127.0.0.1:27017:27017` | Chỉ publish port trên localhost host |
| `-v sales-mongo-data:/data/db` | Named volume giữ dữ liệu khi container restart |
| `mongo:8.0` | MongoDB Docker image |
| `--replSet rs0` | Cho phép khởi tạo replica set |
| `--bind_ip_all` | Mongod lắng nghe các interface bên trong container |

**Lưu ý bảo mật:** Dù host port chỉ bind loopback, đây vẫn là cấu hình lab **không bật authentication**. Không dùng trên host không đáng tin hoặc chia sẻ Docker socket/volume cho người khác; production cần auth, TLS, network policy, RBAC, backups và cấu hình replica set nhiều nodes.

### 4.2. Nếu port 27017 đã bận

Có thể map host port 27018:

```powershell
docker run -d --name sales-mongo -p 127.0.0.1:27018:27017 -v sales-mongo-data:/data/db mongo:8.0 --replSet rs0 --bind_ip_all
```

Tuy nhiên replica set member sẽ tự quảng bá host `localhost:27017` nếu ta cấu hình như bước sau. Với một **host-port mapping khác**, connection string discovery qua replica set có thể gặp mismatch. Để đơn giản, lab khuyến nghị dùng host port 27017 trống; nếu buộc đổi port, cần cấu hình replica set host names/port mapping tương ứng hoặc dùng `directConnection=true` cho development trong điều kiện phù hợp. Đừng copy URI ví dụ một cách máy móc.

### 4.3. Kiểm tra container

```bash
docker ps --filter name=sales-mongo
docker logs --tail 30 sales-mongo
```

Có thể cần một khoảng khởi động tự nhiên trước khi `mongosh` kết nối được. Không cần viết sleep vô hạn; nếu lỗi, kiểm tra logs/port/volume.

---

## 5. Khởi tạo replica set một node

### 5.1. Mở mongosh trong container

```bash
docker exec -it sales-mongo mongosh
```

Trong prompt mongosh, chạy:

```javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "localhost:27017" }
  ]
});
```

Lệnh này chỉ chạy **một lần cho replica set mới**, không chạy lại trên replica set đã cấu hình.

### 5.2. Xác nhận PRIMARY

```javascript
rs.status();
db.adminCommand({ hello: 1 });
```

Chờ tới khi member trở thành PRIMARY:

```javascript
db.adminCommand({ hello: 1 }).isWritablePrimary;
```

Giá trị `true` xác nhận member có thể nhận writes theo trạng thái hiện tại.

### 5.3. Tại sao cần replica set?

MongoDB multi-document transactions và change streams có yêu cầu topology, không hỗ trợ đầy đủ trên standalone `mongod`. Single-node replica set cho phép thực hành nhiều tính năng nhưng **không có khả năng failover**, không tương đương một replica set nhiều node production.

### 5.4. Giới hạn hostname localhost

Trong ví dụ này, replica set member là `localhost:27017`, phù hợp cho client chạy **trên cùng máy host** và `mongosh` trong chính container.

Nếu Java app chạy trong **container khác**, `localhost` của container đó **không** trỏ tới MongoDB. Khi chuyển sang Docker Compose nhiều services hoặc cluster có nodes khác, phải dùng DNS/network hostnames hợp lệ, cùng MongoDB replica set member configuration và TLS/security phù hợp.

---

## 6. URI kết nối và kiểm tra ban đầu

### 6.1. URI từ host

```text
mongodb://127.0.0.1:27017/?replicaSet=rs0
```

Nếu MongoDB server quảng bá member hostname `localhost:27017` thì máy host phải resolve hostname đó đến đúng instance. Trong môi trường local mặc định thường thỏa điều kiện.

### 6.2. Kiểm tra với mongosh từ container

```bash
docker exec -it sales-mongo mongosh
```

Trong mongosh:

```javascript
db.adminCommand({ ping: 1 });
db.adminCommand({ hello: 1 });
rs.status();
```

### 6.3. Không hardcode URI production trong source code

Với Java:

```java
String uri = System.getenv("MONGODB_URI");
if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("MONGODB_URI is missing");
}
```

Các credential URIs phải nằm trong cấu hình/secrets, không commit lên Git hoặc paste vào tài liệu.

---

## 7. Quy ước schema và ID của bộ dữ liệu

Để code seed và truy vấn dễ theo dõi, lab dùng **String IDs có tiền tố**:

| Collection | Ví dụ ID |
|---|---|
| categories | `CAT-01` |
| customers | `CUS-001` |
| products | `SKU-001` |
| inventory | `SKU-001` |
| orders | `ORD-0001` |
| payments | `PAY-0001` |
| outbox | `EVT-ORD-DEMO-001` |

**Không convert các IDs này sang ObjectId**. BSON String `"SKU-001"` khác hẳn ObjectId; query phải dùng cùng kiểu. Ở một ứng dụng khác, dùng ObjectId hoặc UUID có thể phù hợp hơn, nhưng phải thống nhất.

### 7.1. Các kiểu BSON quan trọng

- `unitPriceVnd`, `lineTotalVnd`, `totalVnd`, `amountVnd`: BSON Int64 (qua `NumberLong`).
- `quantity`, `available`, `reserved`: số nguyên nhỏ, được mongosh encode theo numeric BSON type phù hợp.
- `createdAt`, `updatedAt`, `paidAt`: BSON Date.
- `active`, `processed`: boolean.
- `status`, `tier`, `method`: String với tập giá trị được định nghĩa.
- `items[]`: array embedded documents.

### 7.2. Vì sao dùng VND số nguyên?

Ví dụ ₫159.000 có thể lưu:

```javascript
unitPriceVnd: NumberLong("159000")
```

Không dùng `159000.00` với floating-point một cách tùy tiện nếu business yêu cầu amount chính xác. Cần thống nhất money unit và overflow policy; thực tế Java có thể dùng `long` cho VND minor unit hoặc `BigDecimal/Decimal128` khi cần số thập phân.

### 7.3. Dữ liệu giả lập và ngày cố định

Tất cả createdAt của seed bắt đầu từ:

```text
2026-01-01T00:00:00Z
```

Ngày cố định giúp truy vấn, assertions và aggregation có thể tái lập. Không dùng `new Date()` cho seed nếu bạn muốn mỗi lần test có cùng expected result.

---

## 8. Data model chi tiết cho categories và products

### 8.1. Category document

```javascript
{
  _id: "CAT-01",
  code: "ELECTRONICS",
  name: "Điện tử",
  createdAt: ISODate("2026-01-01T00:00:00Z")
}
```

### 8.2. Product document

```javascript
{
  _id: "SKU-001",
  categoryId: "CAT-01",
  name: "Sản phẩm mẫu 001",
  description: "Mặt hàng thực hành số 001",
  unitPriceVnd: NumberLong("80000"),
  active: true,
  tags: ["demo", "online"],
  createdAt: ISODate("2026-01-01T00:00:00Z"),
  updatedAt: ISODate("2026-01-01T00:00:00Z")
}
```

### 8.3. Vì sao không nhúng toàn bộ Category vào Product?

Category là thực thể dùng chung cho nhiều products, tên/thuộc tính có thể đổi. Lab dùng `categoryId` tham chiếu để minh họa lookup và quản lý consistency. Trong truy vấn hiển thị danh mục, có thể dùng aggregation `$lookup` hoặc application caching.

### 8.4. Product price và order item price không giống trách nhiệm

- `products.unitPriceVnd`: giá **hiện tại**.
- `orders.items[].unitPriceVnd`: giá snapshot **khi đặt hàng**.

Không tự cập nhật lịch sử đơn khi admin sửa product price.

---

## 9. Data model cho customer và inventory

### 9.1. Customer document

```javascript
{
  _id: "CUS-001",
  fullName: "Khách hàng mẫu 001",
  email: "customer001@example.test",
  tier: "STANDARD",
  active: true,
  createdAt: ISODate("2026-01-01T00:00:00Z")
}
```

Domain `example.test` chỉ dùng làm dữ liệu giả lập; không gửi email thật.

### 9.2. Inventory document

```javascript
{
  _id: "SKU-001",
  available: 24,
  reserved: 0,
  updatedAt: ISODate("2026-01-01T00:00:00Z")
}
```

### 9.3. Invariant tồn kho

Với mỗi SKU:

```text
available >= 0
reserved >= 0
```

Trong checkout:

```javascript
db.inventory.updateOne(
  { _id: "SKU-001", available: { $gte: 2 } },
  {
    $inc: { available: -2 },
    $currentDate: { updatedAt: true }
  }
);
```

Đây là atomic conditional update trên **một document**. Nhưng nếu còn phải tạo order ở collection khác, dùng transaction để đảm bảo các bước cùng commit.

### 9.4. Không giả lập inventory ledger

Bộ seed này không có stock movements và không tính available từ orders lịch sử. Nếu cần kiểm toán số lượng tồn kho, mở rộng thêm collection `stockMovements` hoặc event ledger và thiết kế invariant/reconciliation.

---

## 10. Data model cho orders, payments và outbox

### 10.1. Order

```javascript
{
  _id: "ORD-0001",
  requestId: "SEED-0001",
  customerId: "CUS-002",
  status: "CREATED",
  items: [
    {
      sku: "SKU-001",
      name: "Sản phẩm mẫu 001",
      quantity: 2,
      unitPriceVnd: NumberLong("80000"),
      lineTotalVnd: NumberLong("160000")
    }
  ],
  totalVnd: NumberLong("160000"),
  createdAt: ISODate("2026-01-01T01:00:00Z"),
  updatedAt: ISODate("2026-01-01T01:00:00Z")
}
```

### 10.2. Payment

```javascript
{
  _id: "PAY-0002",
  orderId: "ORD-0002",
  amountVnd: NumberLong("192000"),
  method: "CARD",
  status: "CAPTURED",
  paidAt: ISODate("2026-01-01T03:00:00Z")
}
```

Số tiền chỉ là ví dụ minh họa, không đại diện một transaction thanh toán thật. Không lưu số thẻ, CVV, authentication secrets hoặc thông tin ngân hàng thật.

### 10.3. Outbox

```javascript
{
  _id: "EVT-ORD-DEMO-001",
  aggregateType: "Order",
  aggregateId: "ORD-DEMO-001",
  eventType: "OrderCreated",
  payload: { orderId: "ORD-DEMO-001", customerId: "CUS-001" },
  processed: false,
  createdAt: ISODate("2026-01-05T00:00:00Z")
}
```

Outbox hỗ trợ bài tập “lưu order + ý định phát event cùng transaction”. Worker downstream vẫn cần idempotency/dedupe bởi publish ngoài database không nằm trong MongoDB transaction.

### 10.4. Danh sách trạng thái cho lab

```text
orders.status:
  CREATED
  PAID
  SHIPPED
  CANCELLED

payments.status:
  CAPTURED

outbox.processed:
  false | true
```

Trong ứng dụng thật cần state machine, không cho phép transitions tùy ý (ví dụ CANCELLED → SHIPPED) mà không có nghiệp vụ tương ứng.

---

## 11. Seed nguyên bộ dữ liệu bằng mongosh

Đây là phần trung tâm của bài. Đoạn script chạy trong mongosh kết nối đến MongoDB lab, khởi tạo:

- 5 categories.
- 24 customers.
- 30 products.
- 30 inventory records.
- 120 orders.
- 60 payments (cho orders PAID hoặc SHIPPED).
- Collection outbox ban đầu không có event; dùng ở bài transaction.

### 11.1. Quy tắc an toàn trước khi chạy

**Chỉ chạy trên MongoDB lab.** Script sử dụng `updateOne(..., {$setOnInsert:...}, {upsert:true})`, không drop database, không xóa documents, không gửi network requests ra ngoài. Lặp lại script với cùng IDs **không nhân đôi dữ liệu seed**.

Tuy nhiên `$setOnInsert` chỉ áp dụng cho documents **chưa có**. Nếu bạn đã thay đổi stock/status trong bài tập, seed lại **không reset** documents đó. Đây là chủ ý để tránh silently ghi đè dữ liệu bạn đã thao tác.

### 11.2. Mở mongosh

```bash
docker exec -it sales-mongo mongosh
```

### 11.3. Script

```javascript
const lab = db.getSiblingDB("sales_lab");

const categories = lab.getCollection("categories");
const customers = lab.getCollection("customers");
const products = lab.getCollection("products");
const inventory = lab.getCollection("inventory");
const orders = lab.getCollection("orders");
const payments = lab.getCollection("payments");
const outbox = lab.getCollection("outbox");

const seedTag = "sales-lab-v1";
const baseMs = ISODate("2026-01-01T00:00:00Z").getTime();

function pad(value, width) {
  return String(value).padStart(width, "0");
}

function dateAtHours(hours) {
  return new Date(baseMs + hours * 3600000);
}

function priceOf(productNumber) {
  // Tất cả giá nhỏ, là số nguyên VND.
  return 69000 + productNumber * 11000;
}

function longOf(value) {
  return NumberLong(String(value));
}

function insertIfMissing(collection, doc) {
  return collection.updateOne(
    { _id: doc._id },
    { $setOnInsert: doc },
    { upsert: true }
  );
}

// 1. Danh mục
const categoryNames = [
  ["ELECTRONICS", "Điện tử"],
  ["HOME", "Gia dụng"],
  ["OFFICE", "Văn phòng"],
  ["SPORT", "Thể thao"],
  ["BOOK", "Sách và học tập"]
];

for (let i = 0; i < categoryNames.length; i++) {
  const n = i + 1;

  insertIfMissing(categories, {
    _id: "CAT-" + pad(n, 2),
    code: categoryNames[i][0],
    name: categoryNames[i][1],
    seedTag,
    createdAt: dateAtHours(0)
  });
}

// 2. Khách hàng
for (let i = 1; i <= 24; i++) {
  const id = "CUS-" + pad(i, 3);

  insertIfMissing(customers, {
    _id: id,
    fullName: "Khách hàng mẫu " + pad(i, 3),
    email: "customer" + pad(i, 3) + "@example.test",
    tier: i % 4 === 0 ? "GOLD" : "STANDARD",
    active: true,
    seedTag,
    createdAt: dateAtHours(i)
  });
}

// 3. Sản phẩm và tồn kho
for (let i = 1; i <= 30; i++) {
  const sku = "SKU-" + pad(i, 3);
  const name = "Sản phẩm mẫu " + pad(i, 3);
  const categoryNumber = ((i - 1) % 5) + 1;

  insertIfMissing(products, {
    _id: sku,
    categoryId: "CAT-" + pad(categoryNumber, 2),
    name,
    description: "Mặt hàng thực hành số " + pad(i, 3),
    unitPriceVnd: longOf(priceOf(i)),
    active: i % 6 !== 0,
    tags: ["demo", i % 2 === 0 ? "online" : "store"],
    seedTag,
    createdAt: dateAtHours(i),
    updatedAt: dateAtHours(i)
  });

  insertIfMissing(inventory, {
    _id: sku,
    available: 20 + i * 4,
    reserved: 0,
    seedTag,
    updatedAt: dateAtHours(0)
  });
}

// 4. Đơn hàng lịch sử, có price snapshot
const orderStatuses = [
  "CREATED", "PAID", "SHIPPED", "CANCELLED"
];

for (let i = 1; i <= 120; i++) {
  const orderId = "ORD-" + pad(i, 4);
  const customerNumber = ((i - 1) % 24) + 1;
  const customerId = "CUS-" + pad(customerNumber, 3);

  const firstProductNumber = ((i - 1) % 30) + 1;
  const firstSku = "SKU-" + pad(firstProductNumber, 3);
  const firstQuantity = 1 + (i % 3);
  const firstPrice = priceOf(firstProductNumber);

  const items = [{
    sku: firstSku,
    name: "Sản phẩm mẫu " + pad(firstProductNumber, 3),
    quantity: firstQuantity,
    unitPriceVnd: longOf(firstPrice),
    lineTotalVnd: longOf(firstPrice * firstQuantity)
  }];

  let total = firstPrice * firstQuantity;

  // Mỗi đơn chẵn có thêm một dòng hàng.
  if (i % 2 === 0) {
    const secondProductNumber = ((i + 6) % 30) + 1;
    const secondQuantity = 1;
    const secondPrice = priceOf(secondProductNumber);

    items.push({
      sku: "SKU-" + pad(secondProductNumber, 3),
      name: "Sản phẩm mẫu " + pad(secondProductNumber, 3),
      quantity: secondQuantity,
      unitPriceVnd: longOf(secondPrice),
      lineTotalVnd: longOf(secondPrice * secondQuantity)
    });

    total += secondPrice * secondQuantity;
  }

  const status = orderStatuses[(i - 1) % 4];
  const createdAt = dateAtHours(i);
  const updatedAt =
    status === "CREATED" ? createdAt : dateAtHours(i + 1);

  insertIfMissing(orders, {
    _id: orderId,
    requestId: "SEED-" + pad(i, 4),
    customerId,
    status,
    items,
    totalVnd: longOf(total),
    currency: "VND",
    seedTag,
    createdAt,
    updatedAt
  });

  // Lab: chỉ PAID/SHIPPED có payment CAPTURED.
  if (status === "PAID" || status === "SHIPPED") {
    insertIfMissing(payments, {
      _id: "PAY-" + pad(i, 4),
      orderId,
      amountVnd: longOf(total),
      currency: "VND",
      method: i % 2 === 0 ? "CARD" : "BANK_TRANSFER",
      status: "CAPTURED",
      seedTag,
      paidAt: dateAtHours(i + 1)
    });
  }
}

// 5. Outbox collection sẽ được dùng ở bài transaction.
// Không seed các sự kiện giả thành events đã publish.

printjson({
  categories: categories.countDocuments({ seedTag }),
  customers: customers.countDocuments({ seedTag }),
  products: products.countDocuments({ seedTag }),
  inventory: inventory.countDocuments({ seedTag }),
  orders: orders.countDocuments({ seedTag }),
  payments: payments.countDocuments({ seedTag }),
  outbox: outbox.countDocuments({})
});
```

### 11.4. Số lượng kỳ vọng

| Collection | Số documents thuộc seed |
|---|---:|
| `categories` | 5 |
| `customers` | 24 |
| `products` | 30 |
| `inventory` | 30 |
| `orders` | 120 |
| `payments` | 60 |
| `outbox` | 0 lúc khởi tạo |

Nếu số lượng lệch, kiểm tra bạn có chạy script trên collection vốn đã có documents hoặc script đã dừng giữa chừng không. Seed có thể chạy lại để bổ sung các ID thiếu.

### 11.5. Vì sao script không reset dữ liệu?

Sau khi luyện checkout, bạn có thể đã giảm stock của SKU-001. Chạy lại `$setOnInsert` giữ nguyên tồn kho đó. Nếu muốn reset đúng trạng thái ban đầu, phải có quy trình làm mới lab **có chủ đích**, không tự biến script seed thành lệnh overwrite mọi business changes.

---

## 12. Kiểm tra số lượng và phân bố dữ liệu

Sau khi seed, chạy trong mongosh:

```javascript
const lab = db.getSiblingDB("sales_lab");

printjson({
  categories: lab.categories.countDocuments({ seedTag: "sales-lab-v1" }),
  customers: lab.customers.countDocuments({ seedTag: "sales-lab-v1" }),
  products: lab.products.countDocuments({ seedTag: "sales-lab-v1" }),
  inventory: lab.inventory.countDocuments({ seedTag: "sales-lab-v1" }),
  orders: lab.orders.countDocuments({ seedTag: "sales-lab-v1" }),
  payments: lab.payments.countDocuments({ seedTag: "sales-lab-v1" })
});
```

### 12.1. Đếm trạng thái đơn hàng

```javascript
lab.orders.aggregate([
  { $match: { seedTag: "sales-lab-v1" } },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Expected: `CREATED`, `PAID`, `SHIPPED`, `CANCELLED`, mỗi trạng thái 30 documents.

### 12.2. Tổng số line items

```javascript
lab.orders.aggregate([
  { $match: { seedTag: "sales-lab-v1" } },
  { $unwind: "$items" },
  { $count: "lineItems" }
]);
```

Kỳ vọng:

```text
120 orders
60 orders có 1 item
60 orders có 2 items
=> 180 line items
```

### 12.3. Kiểm tra inactive products

```javascript
lab.products.countDocuments({
  seedTag: "sales-lab-v1",
  active: false
});
```

Kỳ vọng có 5 products inactive (SKU-006, SKU-012, SKU-018, SKU-024, SKU-030).

### 12.4. Không coi “đếm đúng” là kiểm tra mọi quan hệ

Counts là smoke test. Những bài sau sẽ kiểm tra tham chiếu order/customer, payment/order và tổng tiền. Nếu có lỗi duplicate/missing references, counts vẫn có thể trông bình thường.

---

## 13. Tạo index cho các truy vấn chính

Dùng `mongosh` trên lab đã seed:

```javascript
const lab = db.getSiblingDB("sales_lab");

// Category code cần unique.
lab.categories.createIndex(
  { code: 1 },
  { unique: true, name: "uq_category_code" }
);

// Customer email cần unique.
lab.customers.createIndex(
  { email: 1 },
  { unique: true, name: "uq_customer_email" }
);

// Product listing theo category, active và tên.
lab.products.createIndex(
  { categoryId: 1, active: 1, name: 1 },
  { name: "idx_product_category_active_name" }
);

// Order listing cho một customer.
lab.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "idx_order_customer_created" }
);

// Dashboard theo trạng thái.
lab.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_order_status_created" }
);

// Idempotency key của request đặt hàng.
lab.orders.createIndex(
  { requestId: 1 },
  { unique: true, name: "uq_order_request" }
);

// Tìm orders có item theo SKU.
lab.orders.createIndex(
  { "items.sku": 1, status: 1 },
  { name: "idx_order_items_sku_status" }
);

// Lab chỉ có một payment record/order.
lab.payments.createIndex(
  { orderId: 1 },
  { unique: true, name: "uq_payment_order" }
);

// Outbox worker đọc các records chưa xử lý.
lab.outbox.createIndex(
  { processed: 1, createdAt: 1 },
  { name: "idx_outbox_pending" }
);

// Xem catalog.
printjson(lab.orders.getIndexes());
```

### 13.1. Vì sao _id không cần tạo index thủ công?

MongoDB tự tạo unique index trên `_id` của collection thông thường. `SKU-001` được tìm qua `products._id` hoặc `inventory._id` nhờ index mặc định.

### 13.2. Vì sao index customerId + createdAt?

Một truy vấn:

```javascript
lab.orders.find({ customerId: "CUS-001" })
  .sort({ createdAt: -1 })
  .limit(10);
```

có equality trên customerId và sort theo createdAt; compound index giúp giới hạn range theo customer rồi duyệt đúng thứ tự.

### 13.3. Vì sao có unique requestId?

Một HTTP request có thể được gửi lại do timeout. Unique index giúp ngăn tạo hai orders có cùng idempotency key. Tuy nhiên HTTP API vẫn phải xác minh payload tương ứng và xử lý duplicate như “đã xử lý” hoặc conflict, không đơn giản trả lỗi 500.

### 13.4. Vì sao chưa index mọi field?

Mỗi index có storage và write overhead. Không tạo index trên mọi field chỉ vì nó xuất hiện trong schema. Tạo thêm sau khi xác định query patterns và xem explain.

---

## 14. Cấu trúc index và các câu hỏi hiệu năng

### 14.1. Compound index không chỉ là ba index đơn

```javascript
{ customerId: 1, createdAt: -1 }
```

khác với:

```javascript
{ customerId: 1 }
{ createdAt: -1 }
```

Index compound giúp filter theo customer và trả results theo createdAt order trong range phù hợp.

### 14.2. ESR

Nguyên tắc gợi ý:

- Equality fields trước.
- Sort fields kế tiếp khi tránh sort là mục tiêu quan trọng.
- Range fields sau đó, nhưng có trường hợp ERS tốt hơn nếu range rất chọn lọc.

### 14.3. Kiểm tra bằng explain

```javascript
const lab = db.getSiblingDB("sales_lab");

const plan = lab.orders
  .find({ customerId: "CUS-001" })
  .sort({ createdAt: -1 })
  .limit(10)
  .explain("executionStats");

printjson({
  returned: plan.executionStats.nReturned,
  docsExamined: plan.executionStats.totalDocsExamined,
  keysExamined: plan.executionStats.totalKeysExamined,
  winningPlan: plan.queryPlanner.winningPlan
});
```

Với seed nhỏ, planner có thể chọn access path khác index và vẫn hợp lý. Không assert chính xác stage trên mọi MongoDB version.

### 14.4. Không dùng executionTimeMillis làm tiêu chuẩn CI

Một lần explain có thể chịu ảnh hưởng CPU, I/O/cache và query planner. Khi kiểm thử query efficiency, so result correctness và scan budget trên fixture đủ lớn; benchmark latency p95/p99 trên môi trường ổn định riêng.

---

## 15. Đặt schema validation sau khi thống nhất kiểu dữ liệu

MongoDB flexible schema không tự bảo đảm `createdAt` luôn là BSON Date hoặc `totalVnd` luôn là Int64. Một lỗi importer có thể ghi:

```javascript
{
  createdAt: "2026-01-01",
  totalVnd: "199000"
}
```

sau đó filter Date/numeric hoạt động không đúng.

### 15.1. Ví dụ validator cho products

Trong môi trường **lab đã biết validator hiện tại**, có thể thiết kế:

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.runCommand({
  collMod: "products",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "categoryId", "name",
        "unitPriceVnd", "active"
      ],
      properties: {
        _id: { bsonType: "string" },
        categoryId: { bsonType: "string" },
        name: { bsonType: "string" },
        unitPriceVnd: { bsonType: "long" },
        active: { bsonType: "bool" },
        createdAt: { bsonType: "date" },
        updatedAt: { bsonType: "date" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

**Không chạy `collMod` tùy tiện trên database thật**, vì lệnh này có thể thay thế validator hiện có và làm những writers không tương thích bị lỗi. Trong bài lab, đảm bảo product price đã lưu `NumberLong` theo seed trước khi bật.

### 15.2. Ví dụ validator cho orders

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "requestId", "customerId", "status",
        "items", "totalVnd", "currency", "createdAt"
      ],
      properties: {
        _id: { bsonType: "string" },
        requestId: { bsonType: "string" },
        customerId: { bsonType: "string" },
        status: {
          enum: [
            "CREATED", "PAID", "SHIPPED", "CANCELLED"
          ]
        },
        items: { bsonType: "array" },
        totalVnd: { bsonType: "long" },
        currency: { enum: ["VND"] },
        createdAt: { bsonType: "date" },
        updatedAt: { bsonType: "date" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

Đây là bước mở rộng **tùy chọn**, không cần thiết để seed chạy. Validator tối giản chưa kiểm tra mọi quy tắc business, chẳng hạn total bằng tổng lines hoặc từng item quantity dương.

### 15.3. Kiểm tra type distribution

```javascript
lab.orders.aggregate([
  {
    $group: {
      _id: { $type: "$totalVnd" },
      count: { $sum: 1 }
    }
  }
]);
```

Expected là nhóm `long` cho documents seed.

### 15.4. Schema validation không tạo foreign key

Ngay cả validator cho `customerId` kiểu String cũng không chứng minh customer tương ứng tồn tại. Với quan hệ cross-collection, cần application logic hoặc consistency tests.

---

## 16. Truy vấn 1: lấy sản phẩm đang bán theo danh mục

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.products.find(
  { categoryId: "CAT-01", active: true },
  { _id: 1, name: 1, unitPriceVnd: 1 }
)
.sort({ name: 1 })
.limit(10);
```

### 16.1. Index phù hợp

```javascript
{ categoryId: 1, active: 1, name: 1 }
```

Hai equality fields trước, tên sản phẩm sau để phục vụ sort.

### 16.2. Projection

Nếu chỉ hiển thị bảng sản phẩm, không cần tải mọi field. Projection giảm payload/decoding cost. Nếu query được covered bởi index theo điều kiện phù hợp, có thể tránh fetch full documents; không giả định mọi projection đều covered.

### 16.3. Thử explain

```javascript
lab.products.find({
  categoryId: "CAT-01",
  active: true
})
.sort({ name: 1 })
.explain("executionStats");
```

Không đánh giá hiệu năng production dựa trên chỉ 30 products. Lab nhỏ dùng để học plan structure; muốn efficiency regression test cần fixture lớn hơn.

---

## 17. Truy vấn 2: đơn hàng của khách theo thời gian

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.orders.find(
  { customerId: "CUS-001" },
  { _id: 1, status: 1, totalVnd: 1, createdAt: 1 }
)
.sort({ createdAt: -1 })
.limit(10);
```

Index:

```javascript
{ customerId: 1, createdAt: -1 }
```

### 17.1. Truy vấn theo status

```javascript
lab.orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(20);
```

Index:

```javascript
{ status: 1, createdAt: -1 }
```

### 17.2. Một lưu ý về phân trang

```javascript
.skip(100000).limit(20)
```

trên collection thực có thể tốn nhiều index scan dù có index. Với pagination sâu, cân nhắc keyset pagination và stable sort key.

### 17.3. Sort tie-breaker

Nếu nhiều orders trùng createdAt, thêm `_id` làm tie-breaker và cân nhắc index tương ứng. Seed này có timestamps phân biệt, nhưng production không nên dựa vào điều đó.

---

## 18. Truy vấn 3: lọc theo Date và kiểu dữ liệu

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.orders.find({
  createdAt: {
    $gte: ISODate("2026-01-02T00:00:00Z"),
    $lt: ISODate("2026-01-04T00:00:00Z")
  }
}).sort({ createdAt: 1 });
```

### 18.1. Vì sao phải dùng ISODate?

Seed `createdAt` là BSON Date. Query với string ISO:

```javascript
{ createdAt: { $gte: "2026-01-02" } }
```

không tự parse thành BSON Date; range comparison dùng type-bracketing semantics.

### 18.2. Kiểm tra kiểu

```javascript
lab.orders.aggregate([
  {
    $group: {
      _id: { $type: "$createdAt" },
      count: { $sum: 1 }
    }
  }
]);
```

### 18.3. Phân biệt UTC và ngày địa phương

Nếu người dùng chọn “ngày 2/1” theo timezone Việt Nam, application phải chuyển date-range địa phương sang hai UTC instants đúng. Không coi ngày local tự động bắt đầu lúc 00:00Z.

---

## 19. Truy vấn 4: thống kê doanh thu theo trạng thái

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.orders.aggregate([
  {
    $match: {
      seedTag: "sales-lab-v1",
      status: { $in: ["PAID", "SHIPPED"] }
    }
  },
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      revenueVnd: { $sum: "$totalVnd" }
    }
  },
  { $sort: { _id: 1 } }
]);
```

### 19.1. Đây là metric gì?

Đây là **tổng giá trị các orders có trạng thái PAID hoặc SHIPPED theo dữ liệu giả lập**. Nó không phải doanh thu kế toán, chưa xử lý hoàn tiền, discount, thuế, shipping fees hoặc refunds.

### 19.2. Numeric type

`totalVnd` là BSON Int64. MongoDB aggregation có thể tính tổng theo numeric semantics; với monetary values rất lớn, cần xem overflow/Decimal128 policy của hệ thống.

### 19.3. Index và aggregation

Index `{status:1,createdAt:-1}` có thể hỗ trợ lọc status, nhưng `$group` vẫn phải xét các documents thỏa điều kiện. Không kỳ vọng `nReturned=2` nghĩa là database chỉ đọc 2 orders.

---

## 20. Truy vấn 5: top sản phẩm theo số lượng bán

Dùng embedded items:

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.orders.aggregate([
  {
    $match: {
      seedTag: "sales-lab-v1",
      status: { $in: ["PAID", "SHIPPED"] }
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      totalQuantity: { $sum: "$items.quantity" },
      totalLineValueVnd: { $sum: "$items.lineTotalVnd" }
    }
  },
  { $sort: { totalQuantity: -1, _id: 1 } },
  { $limit: 10 }
]);
```

### 20.1. Vì sao $unwind?

Mỗi order có array `items[]`. `$unwind` tạo một pipeline row cho mỗi line item, sau đó `$group` tính tổng theo SKU.

### 20.2. Snapshot price

Tổng line value lấy từ order items tại thời điểm đặt, không lấy `products.unitPriceVnd` hiện tại. Điều này giữ đúng lịch sử giả lập khi product price thay đổi.

### 20.3. Về hiệu năng

Với dataset lớn, `$unwind/$group/$sort` có thể tốn CPU/memory. Query này phù hợp demo aggregation; production analytics có thể dùng materialized view, caching hoặc batch/reporting pipeline riêng.

---

## 21. Truy vấn 6: $lookup customer và product

### 21.1. Order + customer

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.orders.aggregate([
  { $match: { _id: "ORD-0001" } },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $unwind: "$customer" },
  {
    $project: {
      _id: 1,
      status: 1,
      totalVnd: 1,
      "customer.fullName": 1,
      "customer.tier": 1
    }
  }
]);
```

### 21.2. Foreign index

`customers._id` có index mặc định, giúp join equality lookup khi được tối ưu theo plan/version. Với custom `foreignField`, cần xem index tương ứng.

### 21.3. Không mặc định $lookup là foreign key enforcement

Nếu customer bị xóa, `$lookup` có thể trả array rỗng. MongoDB không tự ngăn document orders tham chiếu customer không tồn tại.

### 21.4. Không thêm $lookup vào mọi request

Order embeds price/name snapshot để hiển thị lịch sử mà không cần join products thường xuyên. Chỉ join khi cần dữ liệu current product/customer.

---

## 22. Truy vấn 7: xác minh tham chiếu bị thiếu

Ví dụ kiểm tra những orders không có customer tương ứng:

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.orders.aggregate([
  { $match: { seedTag: "sales-lab-v1" } },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "foundCustomer"
    }
  },
  { $match: { foundCustomer: { $size: 0 } } },
  { $project: { _id: 1, customerId: 1 } }
]);
```

Kỳ vọng empty results cho dataset seed còn nguyên.

### 22.1. Kiểm tra payments không có order

```javascript
lab.payments.aggregate([
  { $match: { seedTag: "sales-lab-v1" } },
  {
    $lookup: {
      from: "orders",
      localField: "orderId",
      foreignField: "_id",
      as: "foundOrder"
    }
  },
  { $match: { foundOrder: { $size: 0 } } },
  { $project: { orderId: 1, amountVnd: 1 } }
]);
```

### 22.2. Kết quả bị thiếu không luôn do seed

Nếu bạn đã thay đổi hoặc xóa dữ liệu trong bài tập, những kiểm tra này sẽ phản ánh trạng thái mới. Không tự động cho phép seed ghi đè để “làm biến mất” lỗi; điều tra lại business operation đã làm gì.

---

## 23. Truy vấn 8: đối chiếu tổng tiền với line items

Một invariant:

```text
orders.totalVnd
  = SUM(items[].lineTotalVnd)
```

Với orders seed:

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.orders.aggregate([
  { $match: { seedTag: "sales-lab-v1" } },
  {
    $project: {
      _id: 1,
      totalVnd: 1,
      calculatedVnd: { $sum: "$items.lineTotalVnd" }
    }
  },
  {
    $match: {
      $expr: { $ne: ["$totalVnd", "$calculatedVnd"] }
    }
  }
]);
```

Expected: empty result cho dữ liệu seed còn nguyên.

### 23.1. Kiểm tra quantity và unit price

Tương tự có thể dùng `$map` + `$multiply` để xác minh lineTotal theo quantity và unitPrice. Việc tính trong service nên dùng kiểu số không gây floating-point rounding nếu quy trình tiền tệ yêu cầu tính chính xác.

### 23.2. Vì sao cần reconciliation?

Order document có các giá trị snapshot trùng lặp có chủ đích. Cần consistency checks để tránh update một field mà quên những fields liên quan.

---

## 24. Kết nối Java Sync Driver

### 24.1. Dependency

Maven:

```xml
<dependency>
  <groupId>org.mongodb</groupId>
  <artifactId>mongodb-driver-sync</artifactId>
  <version>5.5.0</version>
</dependency>
```

Phiên bản là **ví dụ**, không phải tuyên bố latest; hãy dùng dependency/version được project quản lý và đối chiếu compatibility với MongoDB Server.

Gradle:

```groovy
dependencies {
  implementation "org.mongodb:mongodb-driver-sync:5.5.0"
}
```

### 24.2. Java connection smoke test

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class SalesLabPing {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase lab = client.getDatabase("sales_lab");

            Document ping = lab.runCommand(new Document("ping", 1));
            System.out.println("ping=" + ping.toJson());

            long productCount = lab.getCollection("products")
                    .countDocuments(new Document("seedTag", "sales-lab-v1"));

            long orderCount = lab.getCollection("orders")
                    .countDocuments(new Document("seedTag", "sales-lab-v1"));

            System.out.printf(
                    "products=%d orders=%d%n",
                    productCount, orderCount);
        }
    }
}
```

### 24.3. MONGODB_URI trên Windows PowerShell

```powershell
$env:MONGODB_URI = "mongodb://127.0.0.1:27017/?replicaSet=rs0"
```

Trong bash:

```bash
export MONGODB_URI="mongodb://127.0.0.1:27017/?replicaSet=rs0"
```

Không đặt password vào shell history khi làm việc với deployment thật; dùng secrets phù hợp.

### 24.4. MongoClient lifecycle

`MongoClient` thread-safe và giữ connection pool, nên được tái sử dụng ở ứng dụng, không tạo/đóng mỗi HTTP request. Ví dụ `try-with-resources` ở main chỉ phù hợp chương trình ngắn.

---

## 25. Java: đọc products, orders, arrays

### 25.1. Product theo category

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Sorts.ascending;

MongoCollection<Document> products =
        client.getDatabase("sales_lab")
              .getCollection("products");

for (Document product : products.find(and(
        eq("categoryId", "CAT-01"),
        eq("active", true)))
        .sort(ascending("name"))
        .limit(10)) {

    System.out.printf(
            "%s | %s | %s%n",
            product.getString("_id"),
            product.getString("name"),
            product.get("unitPriceVnd"));
}
```

### 25.2. Order theo customer

```java
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Sorts.descending;

MongoCollection<Document> orders =
        client.getDatabase("sales_lab")
              .getCollection("orders");

for (Document order : orders
        .find(eq("customerId", "CUS-001"))
        .sort(descending("createdAt"))
        .limit(10)) {

    System.out.println(order.toJson());
}
```

### 25.3. Nested item query

```java
for (Document order : orders.find(
        eq("items.sku", "SKU-001"))) {
    System.out.println(order.getString("_id"));
}
```

MongoDB dot notation có thể match một element trong embedded array. Khi nhiều predicates phải áp dụng **cùng một** array element, cân nhắc `$elemMatch` để không match nhầm các phần tử khác nhau.

### 25.4. Numeric reading

`unitPriceVnd` và `totalVnd` là Int64. `Document.getLong("totalVnd")` phù hợp nếu decoder trả Long theo BSON type đã seed. Nếu code xử lý dữ liệu cũ có mixed types, cần validation/typed mapper thay vì silently cast sai.

---

## 26. Java: transaction đặt hàng trừ tồn kho

Vì lab là replica set, có thể thử **multi-document transaction**. Ví dụ dùng Java Sync Driver:

1. Giảm `inventory.available` khi còn đủ hàng.
2. Tạo order.
3. Tạo outbox event.
4. Commit cả ba cùng nhau.

### 26.1. Ví dụ service

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import java.util.Date;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.currentDate;
import static com.mongodb.client.model.Updates.inc;

public final class CheckoutDemo {

    public static String checkout(MongoClient client) {
        MongoDatabase db = client.getDatabase("sales_lab");

        MongoCollection<Document> stock =
                db.getCollection("inventory");
        MongoCollection<Document> orders =
                db.getCollection("orders");
        MongoCollection<Document> outbox =
                db.getCollection("outbox");

        // IDs cố định để ví dụ dễ quan sát.
        // API thực cần request-scoped idempotency key.
        String requestId = "DEMO-CHECKOUT-001";
        String orderId = "ORD-DEMO-001";
        String eventId = "EVT-ORD-DEMO-001";

        TransactionOptions options = TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .readPreference(ReadPreference.primary())
                .build();

        try (ClientSession session = client.startSession()) {
            return session.withTransaction(() -> {

                UpdateResult result = stock.updateOne(
                        session,
                        and(
                                eq("_id", "SKU-001"),
                                gte("available", 1)
                        ),
                        combine(
                                inc("available", -1),
                                currentDate("updatedAt")
                        )
                );

                if (result.getModifiedCount() != 1) {
                    throw new IllegalStateException(
                            "Insufficient inventory");
                }

                long priceVnd = 80000L;

                Document item = new Document("sku", "SKU-001")
                        .append("name", "Sản phẩm mẫu 001")
                        .append("quantity", 1)
                        .append("unitPriceVnd", priceVnd)
                        .append("lineTotalVnd", priceVnd);

                orders.insertOne(
                        session,
                        new Document("_id", orderId)
                                .append("requestId", requestId)
                                .append("customerId", "CUS-001")
                                .append("status", "CREATED")
                                .append("items", java.util.List.of(item))
                                .append("totalVnd", priceVnd)
                                .append("currency", "VND")
                                .append("createdAt", new Date())
                                .append("updatedAt", new Date())
                );

                outbox.insertOne(
                        session,
                        new Document("_id", eventId)
                                .append("aggregateType", "Order")
                                .append("aggregateId", orderId)
                                .append("eventType", "OrderCreated")
                                .append("payload",
                                        new Document("orderId", orderId)
                                          .append("customerId", "CUS-001"))
                                .append("processed", false)
                                .append("createdAt", new Date())
                );

                return orderId;
            }, options);
        }
    }
}
```

### 26.2. Đọc lại kết quả

```javascript
const lab = db.getSiblingDB("sales_lab");

printjson(lab.inventory.findOne({ _id: "SKU-001" }));
printjson(lab.orders.findOne({ _id: "ORD-DEMO-001" }));
printjson(lab.outbox.findOne({ _id: "EVT-ORD-DEMO-001" }));
```

### 26.3. Cảnh báo khi chạy lại ví dụ

Chạy lại với cùng requestId/orderId sẽ đụng unique index hoặc duplicate `_id`. Vì thao tác trừ tồn kho nằm trong cùng transaction, một duplicate-key failure khiến transaction attempt không commit đúng, tránh trừ thêm hàng của lần lỗi. Nhưng service thật cần xử lý **idempotency lookup và unknown commit outcome** thay vì chỉ ném exception.

### 26.4. withTransaction callback có thể chạy lại

Driver có thể retry callback khi gặp transient transaction errors. Vì vậy không đặt HTTP payment, gửi email hoặc Kafka publish bên trong callback. Outbox event được ghi cùng transaction, worker phát sau commit.

### 26.5. Không đồng nghĩa exactly-once end-to-end

MongoDB transaction atomic trong phạm vi MongoDB writes; external broker vẫn cần idempotency. Một worker publish thành công nhưng crash trước khi đánh dấu processed có thể phát lại event.

---

## 27. Schema validation và transaction: thử rollback

### 27.1. Thử transaction abort

Trong Java:

```java
try (ClientSession session = client.startSession()) {
    session.startTransaction();

    orders.insertOne(
            session,
            new Document("_id", "ORD-ABORT-LAB")
                    .append("requestId", "REQ-ABORT-LAB")
                    .append("customerId", "CUS-001")
                    .append("status", "CREATED")
                    .append("items", java.util.List.of())
                    .append("totalVnd", 0L)
                    .append("currency", "VND")
                    .append("createdAt", new Date())
    );

    session.abortTransaction();
}
```

### 27.2. Kiểm tra

```javascript
db.getSiblingDB("sales_lab")
  .orders.findOne({ _id: "ORD-ABORT-LAB" });
```

Kỳ vọng `null` nếu document chưa tồn tại trước đó.

### 27.3. Quên truyền session là lỗi nghiêm trọng

Sai:

```java
session.startTransaction();
orders.insertOne(document); // Không truyền session.
session.abortTransaction();
```

Lệnh insert không được gắn transaction đang active. Muốn tham gia, dùng `orders.insertOne(session, document)`.

---

## 28. Kiểm tra seed có thể chạy lại mà không nhân đôi dữ liệu

### 28.1. Idempotent upsert

Script dùng:

```javascript
collection.updateOne(
  { _id: fixedId },
  { $setOnInsert: document },
  { upsert: true }
);
```

Khi ID đã tồn tại, document không bị viết đè; khi chưa có, MongoDB tạo mới.

### 28.2. Vì sao phải dùng _id cố định?

Nếu seed dùng `insertOne({_id:new ObjectId()})` mỗi lần, chạy lại script sẽ tạo thêm records và phá expected counts.

### 28.3. Index unique bảo vệ thêm

Ngoài _id, `orders.requestId` và `customers.email` có unique indexes. Chúng ngăn một số duplicates theo business key ngay cả khi application có bug.

### 28.4. Seed version và trạng thái lab

`seedTag:"sales-lab-v1"` giúp phân biệt records giả lập với records được tạo bởi các bài tập. Query counts nên filter seedTag khi bạn đã bắt đầu tạo nhiều records.

### 28.5. Seed không phải công cụ reset

Nếu bạn đã update một record, rerun không phục hồi giá trị cũ. Để làm mới toàn bộ, cần một **disposable lab instance hoặc reset procedure có explicit confirmation**, tuyệt đối không drop nhầm production database.

---

## 29. Dừng và khởi động lại môi trường

### 29.1. Dừng container

```bash
docker stop sales-mongo
```

### 29.2. Chạy lại container cũ

```bash
docker start sales-mongo
```

Named volume `sales-mongo-data` giữ dữ liệu. Replica set config cũng được lưu trong data directory.

### 29.3. Không chạy rs.initiate lại

Khi start lại volume cũ, replica set đã được initialize. Hãy kiểm tra `rs.status()` thay vì cố tạo lại config.

### 29.4. Xóa container không nhất thiết xóa volume

```bash
docker rm sales-mongo
```

xóa container đã dừng, nhưng named volume thường vẫn còn. Đây không phải reset dữ liệu. Đừng xóa volume nếu muốn giữ lab.

### 29.5. Cleanup hoàn toàn chỉ khi có chủ đích

Nếu muốn xóa sạch lab trên máy cá nhân, cần xác minh đúng tên container/volume rồi mới thực hiện destructive steps. Không tự động hóa `docker volume rm` trong script seed hoặc terminal dùng chung. Có thể tạo **volume tên mới** để bắt đầu một lab độc lập thay vì xóa state cũ.

---

## 30. Troubleshooting Docker và replica set

### 30.1. “port is already allocated”

Một process/container khác đang dùng host port 27017.

- Xem `docker ps` và listener của hệ điều hành.
- Không tắt service MongoDB thật đang phục vụ ứng dụng khác.
- Chọn một lab port/config riêng và sửa replica set hostname mapping đúng.

### 30.2. “not primary” hoặc chưa nhận writes

Kiểm tra:

```javascript
rs.status();
db.adminCommand({ hello: 1 });
```

Trong những giây đầu sau `rs.initiate()`, node chưa thành PRIMARY. Nếu lâu bất thường, kiểm tra replica set hostname, logs và system resources.

### 30.3. “Transaction numbers are only allowed ...”

Thường gặp khi server không chạy topology hỗ trợ retryable writes/transactions. Xác minh `--replSet`, `rs.initiate()`, member PRIMARY và driver URI. Không chỉ thêm `retryWrites=true` rồi kỳ vọng standalone hỗ trợ transaction.

### 30.4. “Server selection timed out”

Các nguyên nhân:

- Container chưa chạy.
- Host port mapping sai.
- Replica set member quảng bá hostname client không resolve được.
- Docker network configuration khác.
- Firewall/TLS/auth mismatch.
- Java app chạy ở một container khác nhưng URI dùng localhost.

Đọc full diagnostics an toàn, không log credentials.

### 30.5. “not authorized”

Lab không auth theo cấu hình trên; nếu dùng Atlas/cluster có auth phải có user/roles đúng. Không tắt auth trên production để “cho lab chạy”.

### 30.6. Không có dữ liệu sau restart

Kiểm tra container dùng đúng named volume, không tạo container khác với volume mới. Xem `docker inspect` và volumes qua Docker CLI theo quyền, không suy từ container name.

---

## 31. Troubleshooting seed và BSON types

### 31.1. Script chạy một phần

Nếu script bị đóng giữa chừng, có thể có categories/customers/products nhưng chưa đủ orders.

- Xem counts theo seedTag.
- Kiểm tra lỗi thực trong mongosh.
- Rerun idempotent seed để bổ sung documents có ID còn thiếu.
- Không xóa toàn bộ dữ liệu chỉ vì chạy chưa xong.

### 31.2. DuplicateKeyException

Có thể do:

- Seed khác dùng cùng _id.
- Unique email/requestId trùng.
- Dữ liệu lab cũ từ một version seed khác.
- Sự không nhất quán giữa ID và business key.

Không tự bỏ unique index để seed pass. Cần phân biệt dữ liệu thuộc lab nào.

### 31.3. Date lưu thành String

Nếu một writer dùng:

```javascript
createdAt: "2026-01-01T00:00:00Z"
```

thay vì `ISODate(...)`, range filter theo Date có thể không trả document đó. Dùng `$type` để phát hiện, sửa writer và migration thay vì áp `$toDate` cho mọi query.

### 31.4. Giá lưu thành String

Nếu `unitPriceVnd:"80000"`, numeric comparison/sum không có semantics mong muốn. Tránh relying on ICU numericOrdering cho tiền. Dùng numeric BSON và schema validation.

### 31.5. Java BigDecimal/Long mapping

Nếu ứng dụng Java model khác seed, xác minh BSON representation qua round-trip tests. `BigDecimal` có thể cần explicit Decimal128 mapping; `long` phù hợp giá VND nguyên của lab.

---

## 32. Kiểm tra dữ liệu liên kết sau khi thực hành

### 32.1. Orders/customer

```javascript
const lab = db.getSiblingDB("sales_lab");

lab.orders.aggregate([
  { $match: { seedTag: "sales-lab-v1" } },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $match: { customer: { $size: 0 } } },
  { $count: "missingCustomers" }
]);
```

Nếu pipeline không có output row, count bằng 0 theo nghĩa không có missing references.

### 32.2. Product references trong items

```javascript
lab.orders.aggregate([
  { $match: { seedTag: "sales-lab-v1" } },
  { $unwind: "$items" },
  {
    $lookup: {
      from: "products",
      localField: "items.sku",
      foreignField: "_id",
      as: "product"
    }
  },
  { $match: { product: { $size: 0 } } },
  {
    $project: {
      _id: 1,
      sku: "$items.sku"
    }
  }
]);
```

### 32.3. Payment order references

```javascript
lab.payments.aggregate([
  { $match: { seedTag: "sales-lab-v1" } },
  {
    $lookup: {
      from: "orders",
      localField: "orderId",
      foreignField: "_id",
      as: "order"
    }
  },
  { $match: { order: { $size: 0 } } }
]);
```

### 32.4. Payment amount equals order total

Có thể mở rộng `$lookup` để so `payments.amountVnd` với `orders.totalVnd` bằng `$expr`; seed kỳ vọng bằng nhau. Trong hệ thống thật có refunds, partial capture và nhiều attempts nên invariant sẽ phức tạp hơn.

---

## 33. Thiết kế một lần đặt hàng thực tế hơn

Một API checkout không chỉ gọi ba lệnh MongoDB:

```text
Validate request / principal
         │
         ▼
Check idempotency key
         │
         ▼
MongoDB transaction
    ├── conditional inventory decrement
    ├── insert order + price snapshot
    └── insert outbox OrderCreated
         │
         ▼
Commit
         │
         ├── return order response
         └── outbox worker publishes event
```

### 33.1. Price snapshot phải lấy từ nguồn đáng tin

Không tin `unitPriceVnd` do client tự gửi trong checkout. Service cần lấy product price/availability theo nguồn tin cậy và kiểm tra concurrent updates/price change policy.

### 33.2. Business idempotency

Một requestId phải gắn với canonical request payload (customer, items, quantity, currency). Nếu client gửi cùng key với payload khác, trả conflict thay vì coi là cùng order.

### 33.3. External payment không nằm trong MongoDB transaction

Không gọi cổng thanh toán trong `withTransaction` callback; callback có thể được chạy lại. Dùng payment provider idempotency key, saga hoặc reconciliation workflow.

### 33.4. Transaction không thay validation

Trong transaction vẫn phải kiểm tra `available >= quantity`, product active, positive quantities, price policy và các business states.

---

## 34. Kiểm thử tự động với JUnit/Testcontainers

### 34.1. Tại sao cần integration test?

Unit test mock MongoRepository không xác minh:

- BSON date/number mapping.
- Index creation.
- Aggregation result.
- Unique index behavior.
- Transaction rollback.
- Query plan.
- Replica set topology.

Nên có integration tests trên MongoDB thật, tốt nhất là isolated container/cluster.

### 34.2. Mẫu test

Trong JUnit 5:

```java
import org.bson.Document;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

@Test
void salesSeedHasExpectedCounts() {
    var db = client.getDatabase("sales_lab");

    assertEquals(
            30L,
            db.getCollection("products")
              .countDocuments(new Document(
                      "seedTag", "sales-lab-v1")));

    assertEquals(
            120L,
            db.getCollection("orders")
              .countDocuments(new Document(
                      "seedTag", "sales-lab-v1")));
}
```

Ví dụ là phần thân test trong test class đã được cấu hình `MongoClient client`, không phải một Java source file độc lập.

### 34.3. Testcontainers

Pin image/server version cho integration tests. Để test transactions, container phải được cấu hình replica set theo API của Testcontainers version đang dùng; không coi một mongod standalone là đủ.

### 34.4. Không dùng production URI trong CI

Tạo database/test environment disposable, có guard rõ và quyền hạn chế. Không tự chạy `dropDatabase()` với URI tùy ý.

### 34.5. Test idempotent seeding

Seed hai lần, assert counts không đổi; sau đó sửa một seeded record và seed lại, assert `$setOnInsert` không reset record. Test này bảo đảm đúng thiết kế “chỉ bổ sung dữ liệu thiếu”.

### 34.6. Test consistency

Kiểm tra:

- 5 categories, 24 customers, 30 products, 30 inventory, 120 orders, 60 payments.
- 30 orders ở mỗi status.
- 180 line items.
- Payment references trỏ tới orders.
- Order total = sum line totals.
- Tất cả seeded dates BSON Date, prices Int64.
- Không có stock âm ở thời điểm seed.

---

## 35. Quan sát truy vấn và phân biệt slow-query test

### 35.1. Explain

```javascript
db.getSiblingDB("sales_lab")
  .orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");
```

### 35.2. Các counters đáng đọc

- `nReturned`.
- `totalDocsExamined`.
- `totalKeysExamined`.
- Chosen index/stage.
- Sort stage khi có.

### 35.3. Dataset nhỏ không cho benchmark production

120 orders đủ để học CRUD và aggregation, nhưng planner có thể chọn COLLSCAN vì collection quá nhỏ. Không coi điều đó chứng minh index sai hoặc MongoDB chậm. Đối với performance regression, cần fixture đủ lớn với distribution đại diện.

### 35.4. Không assert milliseconds ngẫu nhiên

Một test:

```java
assertTrue(explainMillis < 5);
```

rất dễ flaky do CPU/cache/CI. Ưu tiên correctness/index contract/work budgets với dataset được kiểm soát, còn SLA p95/p99 đo riêng trên benchmark environment.

---

## 36. Vấn đề bảo mật cho một ứng dụng bán hàng thật

Lab có dữ liệu giả nhưng nên hình thành thói quen đúng:

- Không commit database passwords.
- Không dùng MongoDB root user cho web application.
- Giới hạn role theo database/collections.
- Bật authentication, TLS và network isolation trên môi trường được chia sẻ.
- Không lưu số thẻ/CVV hoặc credentials trong payment documents.
- Không dùng email khách hàng thật trong fixture.
- Dùng immutable order snapshot cho điều tra nghiệp vụ.
- Quản lý retention và backup.
- Kiểm soát logs/traces chứa PII.
- Kiểm tra tenant isolation trong queries và index design.

### 36.1. Tenant isolation

Dataset minh họa `customerId` và category, chưa có `tenantId`. Với SaaS đa tenant, mỗi query business phải được scope theo authenticated tenant, và index có thể cần `tenantId` ở prefix. Không tin tenantId do client tùy ý khai.

### 36.2. Bảo vệ outbox

Outbox có thể chứa customer IDs và business payload. Worker/analyst không nên có toàn quyền đọc tất cả PII nếu không cần.

### 36.3. Seed không dùng dữ liệu thật

Domain `example.test` và names giả là để lab an toàn. Nếu muốn mô phỏng production distribution, hãy dùng synthetic data có cấu trúc tương đương, không copy customer records không được phép.

---

## 37. Bài tập 1: mở rộng bộ seed

Thêm:

- 10 customers.
- 20 products.
- 100 orders mới với deterministic IDs.
- 2–3 items/order.
- Không nhân đôi khi seed lại.

Yêu cầu:

1. Không dùng ID ngẫu nhiên cho seed có thể rerun.
2. Unique requestId.
3. Price snapshot.
4. Valid dates/long amounts.
5. Thống kê counts và line items sau khi thêm.

---

## 38. Bài tập 2: thêm giỏ hàng

Thiết kế collection `carts`:

```javascript
{
  _id: "CART-CUS-001",
  customerId: "CUS-001",
  items: [
    { sku: "SKU-001", quantity: 2 },
    { sku: "SKU-005", quantity: 1 }
  ],
  updatedAt: ISODate("2026-01-05T00:00:00Z")
}
```

Câu hỏi:

1. Tại sao cart items không nhất thiết lưu giá snapshot cố định như order?
2. Nên index customerId hay dùng _id deterministic?
3. Khi khách checkout, cần validate inventory/price thế nào?
4. Giỏ hàng có được lớn vô hạn trong một document không?

---

## 39. Bài tập 3: tìm orders theo sản phẩm

Yêu cầu:

1. Tìm tất cả orders có `items.sku="SKU-001"`.
2. Chỉ lấy PAID/SHIPPED.
3. Projection orderId, customerId, createdAt.
4. Đọc explain, xác minh index `items.sku,status`.
5. So sánh behavior khi thiếu index.
6. Giải thích vì sao `items[]` tạo multikey index.

---

## 40. Bài tập 4: báo cáo doanh thu tháng

Thiết kế aggregation:

1. Match status PAID/SHIPPED.
2. Group theo tháng của createdAt.
3. Sum totalVnd.
4. Count orders.
5. Sort theo tháng.
6. Giải thích vì sao kết quả chỉ là doanh thu mô phỏng, chưa có refunds/taxes.

Sử dụng `$dateTrunc`/`$dateToString` theo MongoDB version, xác định timezone chính xác.

---

## 41. Bài tập 5: kiểm thử transaction

Viết service Java:

1. Nhận requestId, customerId, SKU, quantity.
2. Kiểm tra quantity dương.
3. Conditional update inventory.
4. Insert order.
5. Insert outbox.
6. Commit.
7. Thử cố ý tạo duplicate requestId và quan sát abort/reconciliation.

Không gọi external payment/email trong callback.

---

## 42. Bài tập 6: race condition

Đặt inventory của một SKU trong disposable lab về available=1 bằng một thay đổi có kiểm soát.

Hai requests đồng thời mua quantity=1:

1. Dùng sessions riêng, không share ClientSession giữa threads.
2. Dùng conditional update.
3. Chỉ một transaction được commit khi không có restock.
4. Tránh available âm.
5. Giải thích transient write conflicts và retry policy.

Chỉ làm trên lab; khôi phục dữ liệu bằng snapshot/new lab nếu cần.

---

## 43. Bài tập 7: kiểm tra dữ liệu sai kiểu

Thử insert một document lab có:

```javascript
{
  _id: "ORD-WRONG-TYPE",
  requestId: "TEST-TYPE",
  customerId: "CUS-001",
  status: "CREATED",
  items: [],
  totalVnd: "100000",
  currency: "VND",
  createdAt: "2026-01-01T00:00:00Z"
}
```

So sánh:

- Query range Date có match không?
- `$type` trả gì?
- Nếu bật schema validator, insert có bị từ chối không?
- Làm thế nào sửa dữ liệu cũ và writer mới?

Chỉ thử trên disposable lab; không thêm record invalid vào bộ seed chuẩn.

---

## 44. Bài tập 8: index và query plan

1. Truy vấn 10 orders gần nhất của CUS-001.
2. Xem explain với index `customerId,createdAt`.
3. So với forced natural scan bằng `hint({$natural:1})` ở lab.
4. Nhận diện docsExamined/keysExamined.
5. Giải thích vì sao 120 documents chưa đủ cho benchmark performance.
6. Mở rộng fixture đủ lớn nếu muốn regression test.

---

## 45. Bài tập 9: unique email và idempotency

1. Thử insert customer có email trùng.
2. Quan sát duplicate-key error.
3. Thử tạo order có requestId trùng nhưng _id khác.
4. Giải thích vì sao requestId phải gắn với payload.
5. Thiết kế API response khi retry HTTP request sau commit nhưng mất response.
6. Không retry DuplicateKey vô hạn.

---

## 46. Bài tập 10: kiểm toán doanh thu và payment

1. Liệt kê orders có status PAID/SHIPPED nhưng không có payment.
2. Liệt kê payments không có order.
3. So payment.amountVnd và order.totalVnd.
4. Mở rộng schema cho refund/partial capture.
5. Giải thích tại sao một payment/order unique index có thể không phù hợp khi cần nhiều payment attempts.

---

## 47. Bài tập 11: thiết kế local/CI/prod environments

Phân tích sự khác biệt:

| Môi trường | Mục tiêu |
|---|---|
| Local Docker | Học và phát triển |
| CI/Testcontainers | Integration tests cô lập, disposable |
| Staging | Triển khai cấu hình gần production |
| Production | Bảo mật, HA, backup, monitoring và SLO |

Đề xuất deployment configuration riêng cho từng môi trường. Không tái sử dụng unauthed single-node localhost Docker như architecture production.

---

## 48. Bài tập 12: mở rộng thành API Java

Thiết kế endpoints:

```text
GET    /products?categoryId=CAT-01
GET    /products/{sku}
GET    /customers/{id}/orders
GET    /orders/{id}
POST   /orders
GET    /reports/top-products
GET    /reports/revenue
```

Yêu cầu:

- Input validation.
- Typed BSON mapping.
- Actor/tenant authorization.
- Pagination và stable sort.
- Idempotency key ở POST /orders.
- Transaction cho checkout.
- Không đưa MongoDB URI vào code.
- Logging/tracing không tiết lộ PII.

---

## 49. Checklist hoàn thành lab

### 49.1. Môi trường

- [ ] MongoDB container chạy và host port bind localhost.
- [ ] Replica set rs0 đã initiate.
- [ ] `hello.isWritablePrimary == true`.
- [ ] Mongosh kết nối được.
- [ ] Java URI trỏ đúng host/replica set.
- [ ] Không dùng production secrets.

### 49.2. Dữ liệu

- [ ] 5 categories.
- [ ] 24 customers.
- [ ] 30 products.
- [ ] 30 inventory snapshots.
- [ ] 120 orders.
- [ ] 60 payments.
- [ ] Outbox ban đầu trống.
- [ ] 30 orders ở mỗi status.
- [ ] 180 line items.
- [ ] IDs, requestIds không trùng.
- [ ] Money fields là BSON Int64.
- [ ] Timestamp fields là BSON Date.

### 49.3. Index

- [ ] Customer email unique.
- [ ] Category code unique.
- [ ] Order requestId unique.
- [ ] Payment orderId unique theo lab design.
- [ ] Product listing compound index.
- [ ] Order customer/date compound index.
- [ ] Order status/date compound index.
- [ ] Items SKU index.
- [ ] Outbox pending index.
- [ ] Explain và index catalog đã được quan sát.

### 49.4. Nghiệp vụ

- [ ] Order line prices là snapshots.
- [ ] Order total bằng sum lineTotal.
- [ ] Payment references tồn tại.
- [ ] Product references tồn tại.
- [ ] Inventory không âm.
- [ ] Transaction demo commit đúng hoặc abort không tạo trạng thái nửa vời.
- [ ] Không external side effects trong withTransaction callback.
- [ ] Seed chạy lại không nhân đôi records.

### 49.5. An toàn

- [ ] Dữ liệu hoàn toàn giả lập.
- [ ] Không dùng unsecured lab cho môi trường chia sẻ/production.
- [ ] Không có script tự động dropDatabase/volume.
- [ ] Có phương án giữ hoặc xóa named volume có chủ đích.
- [ ] Không có raw credentials trong logs/Markdown.
- [ ] Schema/uniqueness assumptions được ghi rõ.

---

## 50. Lỗi thường gặp và cách tìm nguyên nhân

| Lỗi | Nguyên nhân khả dĩ | Hướng giải quyết |
|---|---|---|
| `docker: command not found` | Chưa cài hoặc PATH thiếu Docker | Cài/khởi động Docker |
| Docker daemon unavailable | Docker Desktop/daemon không chạy | Kiểm tra Docker info |
| Port 27017 đã dùng | Service/container khác chiếm port | Điều chỉnh lab network đúng |
| `rs.initiate()` báo already initialized | Volume giữ replica set config | Dùng `rs.status()` |
| Mongo chưa PRIMARY | Election/init chưa hoàn tất | Kiểm tra hello/status/logs |
| Java server selection timeout | URI/hostname/port mismatch | Kiểm tra advertised member address |
| Transaction unsupported | Standalone hoặc topology sai | Initiate replica set |
| Seed counts thấp | Script dừng giữa chừng | Kiểm tra lỗi, rerun idempotent |
| Duplicate key seed | ID/business key bị trùng | Kiểm tra dữ liệu lab cũ |
| `createdAt` filter thiếu docs | String vs BSON Date | Kiểm tra $type/migration |
| Giá tổng sai | Snapshot/calculation bug | Reconciliation |
| Customer lookup rỗng | Referential ID không tồn tại/sai kiểu | Kiểm tra _id và query |
| Product lookup chậm | Thiếu/sai index hoặc dataset khác | Explain/index catalog |
| Transaction chạy lại gây duplicate | IDs cố định/HTTP retry | Idempotency lookup/policy |
| Data không mất khi xóa container | Named volume vẫn còn | Hiểu volume lifecycle |
| Data mất khi dùng container khác | Đổi volume hoặc filesystem path | Xác minh mounts |
| Unique index tạo thất bại | Existing duplicates | Audit/clean dữ liệu theo policy |
| Java codec error | BSON type không khớp POJO | Schema/converter/typing |
| `COLLSCAN` với 120 records | Planner thấy scan rẻ | Không kết luận performance bug |
| Outbox message gửi hai lần | Worker crash trước checkpoint | Consumer dedupe |

---

## 51. Nguồn tham khảo

- [MongoDB Manual — Install with Docker](https://www.mongodb.com/docs/manual/tutorial/install-mongodb-community-with-docker/)
- [MongoDB Manual — Deploy a Replica Set](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set/)
- [MongoDB Manual — Connection Strings](https://www.mongodb.com/docs/manual/reference/connection-string/)
- [MongoDB Manual — Documents](https://www.mongodb.com/docs/manual/core/document/)
- [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Manual — Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Manual — Embedded Data](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/)
- [MongoDB Manual — $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Java Sync Driver — Get Started](https://www.mongodb.com/docs/drivers/java/sync/current/get-started/)
- [MongoDB Java Sync Driver — CRUD](https://www.mongodb.com/docs/drivers/java/sync/current/crud/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [Testcontainers — MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/)

Các links là tài liệu để đối chiếu **phiên bản server/driver đang sử dụng**. Một số API/link paths có thể được tổ chức lại theo phiên bản. Hãy ưu tiên tài liệu release line của dự án, không lấy cấu hình của lab làm runbook production.

---

## 52. Tổng kết

1. Bài thực hành đã xác định môi trường MongoDB local an toàn tương đối cho học tập, **single-node replica set** để hỗ trợ các bài giao dịch và change streams tiếp theo; môi trường này không có high availability và không bật auth.
2. Database `sales_lab` mô phỏng 7 thực thể nghiệp vụ. Chúng ta chọn nhúng line-item snapshot trong order, tham chiếu customer/product, tách inventory/payment/outbox theo trách nhiệm.
3. Script seed dùng deterministic IDs và `$setOnInsert` để **không nhân đôi dữ liệu khi chạy lại**. Nó không reset những document đã chỉnh sửa.
4. Dữ liệu được thiết kế thống nhất: IDs là BSON String, amounts là BSON Int64 VND, timestamps là BSON Date UTC, status là các giá trị có quy ước.
5. Index được tạo theo query shapes trọng yếu: unique business keys, listing theo category, orders theo customer/date, dashboard theo status/date, tìm SKU trong embedded items và outbox pending.
6. Các truy vấn thực hành gồm CRUD, filtering, sorting, aggregation, `$unwind`, `$group`, `$lookup`, kiểm tra references và reconciliation tổng tiền.
7. Java Sync Driver kết nối qua URI trong environment; transaction ví dụ cập nhật inventory, tạo order và ghi outbox trong cùng commit.
8. Để triển khai thực tế, còn cần authentication, RBAC, TLS, production topology, retries/idempotency, monitoring, migrations, backups và performance tests trên dữ liệu đại diện.

**Kết quả mong đợi:** Một database MongoDB tái lập được, có cấu trúc và dữ liệu nhất quán ở mức bài lab, đủ để thực hiện những bài tổng hợp kế tiếp mà không phải bắt đầu từ một collection rỗng hoặc tự tạo data tùy ý cho từng câu hỏi.
