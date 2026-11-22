# Thuật ngữ cốt lõi và cách tra cứu tài liệu MongoDB theo phiên bản

Khi học MongoDB, hai khó khăn thường xuất hiện cùng lúc: một thuật ngữ có thể mang ý nghĩa khác với hệ quản trị cơ sở dữ liệu quan hệ, và ví dụ tìm được trên Internet có thể được viết cho phiên bản MongoDB khác với hệ thống đang sử dụng. Bài này xây dựng một bộ từ vựng chung, sau đó hướng dẫn cách xác định phiên bản thực tế và tra cứu đúng tài liệu chính thức trước khi áp dụng lệnh hoặc tính năng.

Sau bài học, bạn cần có thể:

- Giải thích mối quan hệ giữa **database, collection, document, field, BSON** và **`_id`**.
- Đọc được một truy vấn có **filter, projection, operator, cursor**, phân biệt truy vấn thông thường với **aggregation pipeline** và hiểu vai trò của **index**.
- Nhận diện các thuật ngữ vận hành như **replica set, primary, secondary, sharding, read concern, write concern**.
- Phân biệt **phiên bản MongoDB Server**, **Feature Compatibility Version (FCV)**, **phiên bản driver**, **phiên bản `mongosh`** và **Stable API**.
- Lần từ một vấn đề thực tế đến trang tài liệu **đúng sản phẩm, đúng phiên bản**, rồi đối chiếu ghi chú thay đổi và điều kiện tương thích.

> **Quy ước:** Ví dụ lệnh trong bài dùng `mongosh` (MongoDB Shell). Các đường dẫn phiên bản `v8.0` và `v7.0` là **ví dụ cách cố định phiên bản**, không hàm ý đây luôn là hai bản mới nhất. Với một hệ thống khác, hãy chọn nhánh tài liệu trùng phiên bản thực tế.

## 1. Bản đồ khái niệm: dữ liệu MongoDB được tổ chức như thế nào?

Trong mô hình document, một **deployment** (hệ thống MongoDB đang chạy) có thể chứa nhiều **database**; một database chứa nhiều **collection**; mỗi collection chứa các **document**. Document gồm các cặp **field–value**. Dữ liệu lưu trữ theo định dạng **BSON**.

```text
MongoDB deployment
└── Database: shop
    ├── Collection: customers
    │   ├── Document: { _id: ..., name: ..., ... }
    │   └── Document: { _id: ..., name: ..., ... }
    └── Collection: orders
        └── Document
            ├── Field: orderNo -> "ORD-1001"
            ├── Field: customer -> { id: "C01", city: "Hà Nội" }
            └── Field: items -> [ { sku: "A01", qty: 2 }, ... ]
```

| Thuật ngữ | Ý nghĩa | Cách ghi nhớ / lưu ý |
|---|---|---|
| **Deployment** | Một môi trường MongoDB có thể là máy đơn, replica set hoặc sharded cluster. | Cần biết đang kết nối đến kiểu triển khai nào trước khi dùng lệnh quản trị. |
| **Database** | Không gian logic chứa các collection và đối tượng liên quan. | `shop` là tên database; không đồng nghĩa một máy chủ vật lý. |
| **Collection** | Tập các document, tương đối gần với khái niệm bảng trong SQL. | Document cùng collection **không bắt buộc** có danh sách field giống hệt nhau. |
| **Document** | Bản ghi gồm các cặp field–value; đơn vị dữ liệu quan trọng của MongoDB. | Có thể chứa cấu trúc lồng nhau và mảng. |
| **Field** | Tên thuộc tính trong document. | Ví dụ `orderNo`, `customer.city`. |
| **BSON** | Biểu diễn nhị phân của dữ liệu kiểu document, hỗ trợ nhiều kiểu dữ liệu hơn JSON thông thường. | Ví dụ `ObjectId`, `Date`, `Decimal128`, dữ liệu nhị phân. |
| **`_id`** | Định danh của document trong collection thông thường, có giá trị duy nhất. | Không đồng nghĩa bắt buộc phải dùng kiểu `ObjectId`. |
| **Namespace** | Tên định danh đối tượng, thường ở dạng `database.collection`. | Ví dụ `shop.orders`. |

### 1.1. Document, JSON và BSON không hoàn toàn giống nhau

Một document mẫu trong `mongosh`:

```javascript
{
  _id: ObjectId("65d000000000000000000001"),
  orderNo: "ORD-1001",
  customer: { id: "C01", city: "Hà Nội" },
  items: [
    { sku: "A01", qty: 2, unitPrice: 120000 },
    { sku: "B02", qty: 1, unitPrice: 50000 }
  ],
  status: "PAID",
  createdAt: ISODate("2026-11-01T03:00:00Z")
}
```

Đây là **cú pháp hiển thị trong shell**, không phải JSON thuần: JSON thuần không có lời gọi `ObjectId(...)` hay `ISODate(...)`. Trong lưu trữ, MongoDB dùng BSON. Khi truyền dữ liệu BSON qua công cụ hoặc file JSON, có thể gặp **Extended JSON** với các biểu diễn như `{"$oid":"..."}` hoặc `{"$date":"..."}` nhằm bảo toàn kiểu dữ liệu. Không nên xem một chuỗi hex 24 ký tự và một giá trị BSON `ObjectId` là cùng một kiểu.

`_id` là khóa định danh; khi chèn document mà không cung cấp `_id`, driver hoặc máy chủ thường sinh một `ObjectId`. `ObjectId` gồm 12 byte, thường hiển thị thành 24 ký tự hex và có phần timestamp. Tuy nhiên, `_id` cũng có thể là chuỗi hoặc một kiểu BSON phù hợp khác; không nên suy ra một hệ thống bắt buộc sử dụng `ObjectId`. Trong collection thông thường, MongoDB mặc định có unique index trên `_id`. Một số loại collection chuyên biệt có quy tắc khác, nên phải đọc trang tài liệu tương ứng.

**Giới hạn quan trọng:** một BSON document thông thường có kích thước tối đa **16 MiB**. Với file lớn hơn, MongoDB có cơ chế **GridFS** để chia file thành các phần; đó không phải lý do để nhồi toàn bộ tệp vào một document.

### 1.2. Embedded document, array, reference và schema

- **Embedded document** là document lồng trong field khác, chẳng hạn `customer: { id, city }`. Truy vấn field lồng dùng **dot notation**: `"customer.city"`.
- **Array** là mảng các giá trị hoặc document, chẳng hạn `items`. Truy vấn và cập nhật array có cú pháp/điều kiện riêng; không được giả định rằng mọi phép so sánh trên mảng đều hoạt động như so sánh số đơn.
- **Reference** là việc lưu định danh liên kết sang document khác, ví dụ `customerId: ObjectId(...)`, rồi lấy dữ liệu liên quan theo nhu cầu. MongoDB có `$lookup` để kết hợp dữ liệu trong aggregation nhưng không mặc nhiên áp dụng ràng buộc khóa ngoại giống SQL.
- **Flexible schema** nghĩa là các document trong một collection có thể khác tập field hoặc kiểu field. Nó **không có nghĩa** dữ liệu không cần quy ước: ứng dụng vẫn cần hợp đồng dữ liệu; MongoDB hỗ trợ **schema validation** để áp đặt quy tắc, ví dụ với JSON Schema.

Khi mô hình hóa dữ liệu, cân nhắc **embed** nếu thông tin thường được đọc cùng nhau, kích thước có giới hạn và vòng đời phụ thuộc nhau; cân nhắc **reference** khi quan hệ có số lượng lớn, dữ liệu được cập nhật độc lập hoặc nhiều document cùng tham chiếu một thực thể. Đây là quyết định thiết kế dựa trên cách truy cập dữ liệu, không phải công thức tuyệt đối.

## 2. Từ vựng truy vấn: MongoDB làm gì với document?

MongoDB hỗ trợ **CRUD**: Create, Read, Update, Delete. Cần phân biệt **thao tác** (ví dụ `find()`), **điều kiện** (filter), **phép biến đổi kết quả** (projection) và **toán tử** (operator).

| Nhóm | Thuật ngữ / phương thức | Vai trò |
|---|---|---|
| Create | `insertOne()`, `insertMany()` | Thêm document. |
| Read | `find()`, `findOne()` | Tìm document theo điều kiện; `find()` trả về cursor. |
| Update | `updateOne()`, `updateMany()`, `replaceOne()` | Chỉnh sửa hoặc thay thế document phù hợp. |
| Delete | `deleteOne()`, `deleteMany()` | Xóa document phù hợp. |
| Filter / predicate | `{ status: "PAID" }`, `{ amount: { $gt: 100 } }` | Quy định document nào được chọn. |
| Projection | `{ orderNo: 1, _id: 0 }` | Chọn field cần trả về; thông thường `_id` được kèm theo nếu không loại bỏ. |
| Query operator | `$gt`, `$in`, `$and`, `$exists` | Diễn đạt điều kiện so sánh hoặc logic. |
| Update operator | `$set`, `$inc`, `$unset`, `$push` | Diễn đạt cách cập nhật field. |
| Cursor | Kết quả duyệt của `find()` | Cho phép nhận/duyệt dần các kết quả; không mặc định là một mảng chứa toàn bộ kết quả. |
| Sort / limit | `.sort()`, `.limit()` | Xác định thứ tự và giới hạn số document được trả về. |
| Upsert | `upsert: true` trong thao tác update phù hợp | Nếu không có document khớp, có thể tạo document mới từ filter và cập nhật. |

### 2.1. Ví dụ đọc–ghi có thể thử trong một database thực hành

Ví dụ minh họa thao tác với dữ liệu thử nghiệm, không dùng trực tiếp trên collection sản xuất:

```javascript
use shop_demo

db.orders.insertOne({
  orderNo: "ORD-1001",
  customer: { id: "C01", city: "Hà Nội" },
  items: [
    { sku: "A01", qty: 2, unitPrice: 120000 },
    { sku: "B02", qty: 1, unitPrice: 50000 }
  ],
  status: "PAID",
  createdAt: ISODate("2026-11-01T03:00:00Z")
})

// Filter: đơn PAID tại Hà Nội; projection: chỉ lấy mã đơn và trạng thái.
db.orders.find(
  { status: "PAID", "customer.city": "Hà Nội" },
  { orderNo: 1, status: 1, _id: 0 }
)

// $set là update operator; $in là query operator.
db.orders.updateOne(
  { orderNo: { $in: ["ORD-1001", "ORD-1002"] } },
  { $set: { status: "SHIPPED" } }
)

// Đọc kết quả theo thứ tự mới nhất trước, tối đa 5 document.
db.orders.find({}, { orderNo: 1, createdAt: 1 })
  .sort({ createdAt: -1 })
  .limit(5)
```

Ở đây `1` trong projection nghĩa là lấy field, còn `-1` trong sort nghĩa là giảm dần. Hai giá trị đó nằm trong **hai ngữ cảnh khác nhau**. Trong thao tác update, phân biệt `$set` (gán giá trị) với việc **thay toàn bộ document** bằng `replaceOne()`.

**Atomicity:** thao tác ghi trên **một document** có tính nguyên tử ở mức document, kể cả khi cập nhật nhiều field trong chính document đó. Nếu nghiệp vụ phải thay đổi nhất quán nhiều document, cần tìm hiểu **multi-document transaction** và những điều kiện đi kèm; không suy từ tính nguyên tử của một document thành tính nguyên tử của toàn bộ collection.

### 2.2. Aggregation: pipeline và stage

**Aggregation pipeline** nhận document đi qua một chuỗi **stage**. Mỗi stage lọc, tính toán, biến đổi hoặc nhóm dữ liệu để đưa vào stage tiếp theo. Tên stage thường bắt đầu bằng `$`, nhưng không nên nhầm **aggregation stage** với **query operator** hoặc **update operator**: chúng được dùng ở vị trí cú pháp khác nhau.

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      totalQuantity: { $sum: "$items.qty" }
    }
  },
  { $sort: { totalQuantity: -1 } }
])
```

Diễn giải: `$match` lọc đơn đã thanh toán, `$unwind` tách từng phần tử `items`, `$group` cộng số lượng theo SKU, `$sort` sắp xếp kết quả. Trong `$group`, trường `_id` là **khóa nhóm**, không nhất thiết là `_id` nguyên bản của document ban đầu. Một pipeline khác có thể dùng `$project`, `$lookup`, `$facet`, `$merge`, ...; từng stage phải được đối chiếu với tài liệu phiên bản đang dùng.

### 2.3. Index, query planner và `explain()`

**Index** là cấu trúc hỗ trợ tìm dữ liệu hiệu quả, giống ý tưởng chỉ mục ở các hệ thống cơ sở dữ liệu khác. MongoDB có nhiều loại index; ví dụ **single-field**, **compound** (nhiều field), **multikey** (index dữ liệu mảng), **unique**, **TTL**, **text** và các index chuyên dụng. Mỗi loại có điều kiện và giới hạn riêng.

```javascript
// Ví dụ compound index cho bộ lọc status và thứ tự createdAt.
db.orders.createIndex({ status: 1, createdAt: -1 })

// Quan sát kế hoạch và số lượng document/index entry đã duyệt.
db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .explain("executionStats")
```

- **Query planner** chọn kế hoạch thực thi từ các lựa chọn mà hệ thống xem xét.
- **`COLLSCAN`** biểu thị quét collection; **`IXSCAN`** biểu thị quét index trong cây kế hoạch thường gặp. Có `IXSCAN` chưa chắc truy vấn đã tối ưu nếu số lượng entry và document duyệt quá lớn.
- **`totalDocsExamined`**, **`totalKeysExamined`**, **`nReturned`** trong thống kê thực thi giúp đối chiếu khối lượng đọc với số kết quả. Tên trường, vị trí và hình dạng cây `explain` có thể khác theo bản MongoDB và engine thực thi.
- Index tăng khả năng tăng tốc một số truy vấn nhưng tốn dung lượng và chi phí khi ghi; không nên tạo index chỉ dựa trên tên field mà thiếu truy vấn thực tế.

Đọc phần **Indexing** và **Explain Results** đúng phiên bản trước khi kết luận một kế hoạch thực thi là tốt hoặc xấu. Đặc biệt, cách biểu diễn nội bộ của query engine có thể thay đổi theo phiên bản mà ý nghĩa nghiệp vụ truy vấn vẫn giữ nguyên.

## 3. Thuật ngữ triển khai, độ sẵn sàng và tính nhất quán

Khi đọc tài liệu thao tác cụm MongoDB, phải biết câu lệnh áp dụng cho **standalone**, **replica set** hay **sharded cluster**. Những thuật ngữ sau thường đi cùng nhau:

| Thuật ngữ | Diễn giải thực dụng |
|---|---|
| **`mongod`** | Tiến trình máy chủ MongoDB lưu trữ/xử lý dữ liệu. |
| **`mongos`** | Tiến trình định tuyến truy vấn vào các shard của sharded cluster; bản thân không phải shard chứa dữ liệu. |
| **Standalone** | Một `mongod` hoạt động độc lập; không có cơ chế replica set tự động failover. |
| **Replica set** | Nhóm tiến trình `mongod` duy trì các bản sao dữ liệu để tăng tính sẵn sàng. |
| **Primary / secondary** | Các vai trò trong replica set; primary nhận ghi thông thường, secondary sao chép dữ liệu từ oplog. Vai trò có thể đổi sau election. |
| **Oplog** | Nhật ký thao tác phục vụ replication trong replica set. |
| **Election / failover** | Bầu primary mới và chuyển vai trò khi điều kiện cụm thay đổi. |
| **Sharding** | Phân phối dữ liệu của một collection trên nhiều shard để mở rộng quy mô. |
| **Shard key** | Field hoặc tập field dùng để phân phối/định tuyến dữ liệu của collection sharded. |
| **Config server** | Lưu metadata cấu hình cần thiết cho sharded cluster. |
| **Read preference** | Chỉ dẫn ưu tiên đọc từ loại thành viên nào, ví dụ primary hay secondary. |
| **Read concern** | Mức đảm bảo về dữ liệu mà thao tác đọc có thể quan sát. |
| **Write concern** | Điều kiện xác nhận một thao tác ghi từ hệ thống, ví dụ xác nhận bởi bao nhiêu thành viên. |
| **Session / transaction** | Ngữ cảnh phiên giao tiếp và cơ chế nhóm nhiều thao tác trong một giao dịch khi phù hợp. |
| **Atlas** | Dịch vụ MongoDB được quản lý trên nền tảng đám mây. |

Hình dung hai loại cấu trúc phổ biến:

```text
Replica set:
Application / mongosh -> Primary mongod
                         ├── Secondary mongod
                         └── Secondary mongod
         (các thành viên phối hợp bầu chọn và sao chép dữ liệu)

Sharded cluster:
Application / driver -> mongos
                        ├── Shard A (thường là một replica set)
                        ├── Shard B (thường là một replica set)
                        └── Config server replica set (metadata)
```

**Ba khái niệm dễ nhầm:**

1. **Read preference** quyết định *đọc từ đâu*; nó không tự xác lập mức nhất quán của dữ liệu được đọc.
2. **Read concern** nói về *đảm bảo quan sát dữ liệu*; các mức như `local`, `majority`, `snapshot` có ngữ nghĩa và điều kiện riêng.
3. **Write concern** nói về *khi nào ghi được xác nhận*; `w: 1` và `w: "majority"` không có cùng bảo đảm, còn `journal`/`j` là khía cạnh khác.

Ví dụ, việc ứng dụng đọc ở secondary với một read preference phù hợp **không mặc nhiên** có nghĩa sẽ thấy ngay mọi ghi vừa thành công ở primary. Khi nghiệp vụ đòi hỏi độ mới của dữ liệu, tính nhân quả hoặc tính nhất quán giữa các thao tác, phải đọc chung tài liệu **Read Preference**, **Read Concern**, **Write Concern** và **Transactions**, cùng phiên bản server/driver.

## 4. Thuật ngữ về công cụ và API: đọc đúng loại tài liệu

Cùng một công việc (ví dụ truy vấn đơn hàng), cú pháp thao tác trong `mongosh`, Java Driver, Spring Data MongoDB và giao diện Atlas có thể khác nhau:

| Thành phần | Chức năng | Nơi tra cứu ưu tiên |
|---|---|---|
| **MongoDB Server / Database Manual** | Mô hình dữ liệu, database commands, cơ chế query/index/replication/sharding. | Database Manual theo **phiên bản server**. |
| **`mongosh`** | Shell tương tác với MongoDB; có helper như `db.orders.find()`. | MongoDB Shell và mục **mongosh Methods** trong Manual. |
| **MongoDB Driver** | Thư viện cho ngôn ngữ ứng dụng như Java, Python, Node.js. | Driver guide/API theo **phiên bản thư viện** đang cài. |
| **Spring Data MongoDB** | Lớp trừu tượng mapping/repository/template phía Spring. | Tài liệu **Spring Data MongoDB** theo phiên bản Spring Data. |
| **MongoDB Compass** | Giao diện đồ họa để truy vấn và khảo sát dữ liệu. | Compass documentation. |
| **MongoDB Atlas** | Quản lý cụm, backup, quyền, kết nối trên cloud. | Atlas documentation và thông tin phiên bản cụm. |
| **Database Tools** | Công cụ quản trị/backup như `mongodump`, `mongorestore`, `mongoexport`. | Database Tools documentation theo phiên bản công cụ. |

Ví dụ `db.orders.find({ status: "PAID" })` là cú pháp tiện dụng trong `mongosh`. Trong Java Sync Driver, truy vấn thường đi qua `MongoCollection` và builder như `Filters.eq(...)`; trong Spring Data có `MongoTemplate` hoặc repository. **Đừng chép nguyên cú pháp shell vào Java** rồi kết luận tài liệu sai. Trước hết xác định mình đang đọc hướng dẫn của **server**, **shell**, **driver** hay **framework**.

## 5. 'Phiên bản MongoDB' thực ra gồm nhiều lớp

Một ứng dụng có thể dùng MongoDB Server `8.0.x`, driver Java `5.x` và `mongosh` với số phiên bản hoàn toàn khác, đồng thời cụm vẫn có **FCV** của bản trước trong quá trình nâng cấp. Bởi vậy, câu trả lời "MongoDB đang dùng bản mấy?" chưa đủ để quyết định mọi lệnh/tính năng có sử dụng được hay không.

| Lớp phiên bản | Là gì? | Dùng để quyết định điều gì? |
|---|---|---|
| **Server version** (`X.Y.Z`) | Phiên bản MongoDB chạy trên `mongod`/`mongos`. | Cú pháp lệnh server, giới hạn, tính năng và hành vi server. |
| **Server release series** (`8.0`, `7.0`, ...) | Dòng phiên bản tài liệu và phát hành. | Chọn nhánh Database Manual tương ứng. |
| **Feature Compatibility Version (FCV)** | Mức tương thích của tính năng có thể tạo dữ liệu tồn tại dưới dạng không tương thích với bản cũ. | Kiểm tra một số tính năng sau nâng/hạ cấp; **không** thay thế server version. |
| **Driver version** | Phiên bản thư viện client, ví dụ Java Sync Driver. | API ứng dụng, kiểu dữ liệu, cấu hình và ma trận server tương thích. |
| **`mongosh` version** | Phiên bản chương trình shell cài trên máy. | Khả năng/cú pháp helper của shell; không xác định bản của server từ nó. |
| **Stable API version** | Hợp đồng API server mà client có thể yêu cầu dùng (ví dụ `apiVersion: "1"`). | Ổn định hành vi cho **nhóm lệnh thuộc Stable API** giữa các lần nâng server. |
| **Atlas / công cụ / framework version** | Phiên bản môi trường và lớp bổ sung. | Tính năng quản lý, UI, công cụ hoặc API framework. |

### 5.1. Cách đọc `X.Y.Z`

Theo quy ước phiên bản MongoDB Server, `X` là **major**, `Y` là **minor**, `Z` là **patch**. Major/minor có thể đưa tính năng mới hoặc thay đổi cần đối chiếu điều kiện tương thích; patch thường tập trung vào sửa lỗi trong cùng dòng phát hành. MongoDB có các loại release và chính sách cung cấp khác nhau theo phương thức triển khai, vì thế hãy kiểm tra trang **MongoDB Versions and Upgrade Paths** thay vì đoán một release có mặt trên Atlas hoặc self-managed hay không.

Không dùng nhãn **Latest** của website làm bằng chứng rằng hệ thống đang chạy bản mới nhất. `Latest` là một mục tài liệu **dịch chuyển theo thời gian**; để bảo đảm tính tái lập, ghi rõ dòng phát hành `8.0`, `7.0`, ... và patch đang chạy, nhất là khi hướng dẫn cho môi trường sản xuất.

### 5.2. FCV không phải phiên bản binary

Ví dụ sau khi nâng một deployment từ MongoDB `7.0` lên `8.0`, server binary đã là `8.0` nhưng FCV có thể vẫn là `7.0` cho đến khi hoàn tất các bước nâng cấp tương ứng. FCV kiểm soát việc dùng những tính năng lưu trữ dữ liệu không tương thích ngược; **không phải công tắc để biến binary 7.0 thành 8.0** và cũng không phải số phiên bản driver.

Việc **đọc** FCV để chẩn đoán khác với **thay đổi** FCV. Thao tác `setFeatureCompatibilityVersion` ảnh hưởng khả năng nâng/hạ cấp, có bước xác nhận/điều kiện phụ thuộc phiên bản; chỉ chạy theo quy trình nâng cấp chính thức, sau khi kiểm tra topology, backup và ghi chú phát hành. Bài này chỉ sử dụng lệnh đọc thông tin.

### 5.3. Stable API không phải 'Server phiên bản 1'

**Stable API** (có từ MongoDB Server 5.0) cho phép client yêu cầu một hợp đồng ổn định cho tập lệnh mà Stable API bao phủ; tên cũ là **Versioned API**. Ví dụ `apiVersion: "1"` không có nghĩa kết nối tới MongoDB Server `1.0`, cũng không bảo đảm **mọi** tính năng mới hoặc mọi câu lệnh của MongoDB sẽ hoạt động trên server cũ. Tính năng không thuộc tập Stable API, điều kiện FCV và tính tương thích của driver vẫn phải được kiểm tra riêng.

## 6. Xác định đúng phiên bản trước khi mở tài liệu

Hãy bắt đầu bằng **deployment mà ứng dụng thực sự kết nối tới**. Phiên bản của một chương trình đã cài trên máy phát triển có thể không trùng với phiên bản trên Atlas hoặc máy chủ từ xa.

### 6.1. Xem phiên bản server trong `mongosh`

```javascript
// Phiên bản instance mongod hoặc mongos đang kết nối.
db.version()

// Thông tin build; chọn trường version để xem ngắn gọn.
db.adminCommand({ buildInfo: 1 }).version
```

Kết quả có dạng chuỗi như `"8.0.x"`. Khi nối tới **sharded cluster**, cần lưu ý kết quả qua router không thay thế cho việc kiểm tra phiên bản của **tất cả** các thành phần trong cụm, đặc biệt ở giai đoạn rolling upgrade. Việc kết nối cũng phải đúng endpoint/môi trường (dev, staging, production).

Để **đọc** FCV từ một `mongod` với quyền thích hợp:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
})
```

Kết quả thường chứa `featureCompatibilityVersion.version`. Lệnh `getParameter` này **không được thực hiện trên `mongos`**; với sharded cluster cần làm theo chỉ dẫn chính thức cho từng thành phần và quyền truy cập. Nếu không có quyền đọc tham số, hỏi người vận hành thay vì tự thay đổi cấu hình.

### 6.2. Kiểm tra chương trình cục bộ và thư viện ứng dụng

Trong terminal của máy cài công cụ:

```bash
mongod --version
mongosh --version
```

Hai lệnh này cho biết **binary tại nơi chạy lệnh**, không chứng minh phiên bản của server từ xa. Với Java, đối chiếu version dependency thực tế trong `build.gradle`, `pom.xml` hoặc dependency tree, chẳng hạn `org.mongodb:mongodb-driver-sync`, rồi mở tài liệu **Java Sync Driver** đúng dòng phiên bản đó. Với Spring Data MongoDB, kiểm tra thêm phiên bản Spring Data vì API Spring Data không phải API MongoDB Java Driver thuần.

Nếu dùng **Atlas**, xem bản server trong trang deployment/cluster tương ứng. Khi nghi ngờ dữ liệu hiển thị trên dashboard và phiên kết nối không trùng nhau, xác minh lại endpoint cùng lệnh `db.version()` và trạng thái nâng cấp của cụm.

### 6.3. Mẫu ghi lại môi trường khi cần hỗ trợ

```text
Môi trường: staging
Deployment: Atlas / replica set / sharded cluster (ghi đúng loại)
MongoDB Server: 8.0.x (đọc từ endpoint đang dùng)
FCV: 8.0 (nếu có quyền đọc)
Client: mongosh ... hoặc Java Sync Driver ...
Framework (nếu có): Spring Data MongoDB ...
Tính năng / câu lệnh cần dùng: ...
Link tài liệu đã đối chiếu: ... (nhánh v8.0)
```

Mẫu này có ích khi trao đổi lỗi tương thích: người khác biết chính xác đang nói về **server**, **client** và **tài liệu** nào.

## 7. Quy trình tra cứu tài liệu chính thức theo phiên bản

### Bước 1 — Viết đúng câu hỏi kỹ thuật

Đừng chỉ tìm `MongoDB aggregate`. Hãy xác định việc cần làm, ví dụ: "Trong MongoDB Server 8.0, `find()` chọn một số field bằng projection như thế nào?" hoặc "Java Sync Driver phiên bản đang dùng thiết lập read concern ở đâu?". Câu hỏi càng cụ thể thì càng dễ chọn đúng sản phẩm và trang tham chiếu.

### Bước 2 — Chọn bộ tài liệu trước khi chọn trang

| Nếu bạn cần biết... | Nên bắt đầu từ... |
|---|---|
| Ý nghĩa document, BSON, index, replication, sharding, database command | **Database Manual** theo phiên bản server |
| Cú pháp helper `db.collection.find()` trong shell | **mongosh Methods** của Manual / MongoDB Shell |
| `MongoClient`, `MongoCollection`, `Filters`, `Updates` trong Java | **Java Sync Driver** theo phiên bản driver |
| `MongoTemplate`, `MongoRepository`, mapping Spring Data | **Spring Data MongoDB** theo phiên bản Spring Data |
| Quản trị cluster, backup, UI và giới hạn dịch vụ cloud | **MongoDB Atlas Docs** và cấu hình deployment |
| `mongodump`, `mongorestore` hoặc xuất file JSON/CSV | **MongoDB Database Tools** theo phiên bản công cụ |

### Bước 3 — Cố định nhánh phiên bản

Ví dụ hai nhánh chính thức cho Server Manual:

- [Database Manual — nhánh 8.0](https://www.mongodb.com/docs/v8.0/)
- [Database Manual — nhánh 7.0](https://www.mongodb.com/docs/v7.0/)

Ví dụ cùng chủ đề **Documents** nhưng ở hai nhánh:

- [Documents — 8.0](https://www.mongodb.com/docs/v8.0/core/document/)
- [Documents — 7.0](https://www.mongodb.com/docs/v7.0/core/document/)

Đường dẫn có `v8.0`, `v7.0` giúp nhận diện nhánh; trang ở `/docs/manual/` có thể dẫn đến nhánh hiện hành và thay đổi theo thời gian. Với driver, cách đánh số và đường dẫn phiên bản là **riêng của driver**, không thể thay `v8.0` máy móc vào URL driver. Nhiều trang còn có bộ chọn phiên bản ngay trên giao diện; luôn kiểm tra nhãn phiên bản sau khi chuyển trang hoặc bấm kết quả tìm kiếm.

### Bước 4 — Mở đúng loại trang, đọc đủ chú thích

Khi mở một tính năng hoặc phương thức, đọc theo thứ tự:

1. **Definition / Overview** — tính năng giải quyết vấn đề gì?
2. **Syntax / Parameters / Examples** — các tham số, kiểu dữ liệu và ví dụ nào hợp lệ?
3. **Compatibility / Behavior / Restrictions** — hỗ trợ môi trường nào, có yêu cầu FCV hoặc quyền gì không?
4. **New in version / Changed in version / Deprecated** — tính năng xuất hiện, đổi hành vi hay bị khuyến cáo ngừng dùng từ bản nào?
5. **Release Notes / Upgrade Guide** — có thay đổi tương thích, caveat hoặc lỗi đã sửa ở patch liên quan không?

Một ghi chú `New in version 8.0` trên tài liệu **8.0** không có nghĩa tính năng đó cũng khả dụng ở **7.0**. Ngược lại, một ví dụ rất cũ vẫn chạy được trên 8.0 không chứng minh rằng nó còn là hướng dẫn được khuyến nghị: có thể đã có API thay thế hoặc thay đổi bảo mật/vận hành.

### Bước 5 — Đối chiếu server, FCV, client và môi trường

Ví dụ một trang Manual xác nhận lệnh hỗ trợ từ server 8.0 nhưng Java Driver có API tương ứng từ một bản driver nhất định. Cần kiểm tra **cả hai**: server hiểu lệnh hay chưa, và client hiện tại có thể phát lệnh theo cách mong muốn hay chưa. Với thao tác quản trị hoặc tính năng có dữ liệu lưu trữ không tương thích ngược, đối chiếu thêm **FCV**; với Atlas, kiểm tra thêm khả năng hỗ trợ cho loại cluster/tier tương ứng.

### Bước 6 — Kiểm nghiệm trên môi trường phù hợp rồi lưu nguồn

Với ví dụ đọc, có thể thử trên môi trường phát triển bằng dữ liệu riêng. Với thao tác thay đổi dữ liệu hoặc cấu hình, thực hiện theo quy trình quản lý thay đổi của hệ thống. Khi ghi chép lại kiến thức, lưu **link nhánh phiên bản**, **phiên bản patch thực tế** và **ngày đối chiếu** nếu phát hành có thể tiếp tục thay đổi. Việc giữ lại URL giúp người đọc sau không vô tình chuyển qua hướng dẫn dành cho một dòng phát hành khác.

### 7.1. Cách tìm kiếm khi trang tài liệu quá lớn

Các truy vấn tìm kiếm có ích (thay số phiên bản bằng nhánh bạn dùng):

```text
site:mongodb.com/docs/v8.0/ "db.collection.find" projection
site:mongodb.com/docs/v8.0/ "read concern" "majority"
site:mongodb.com/docs/v8.0/ "Changed in version" index
site:mongodb.com/docs/drivers/java/sync/ "MongoCollection" "find"
```

Đây là **cú pháp tìm kiếm web**, không phải lệnh MongoDB. Kết quả tìm kiếm chỉ dẫn đường; nội dung cần dùng phải được kiểm tra trong trang chính thức sau khi mở. Nếu URL chuyển hướng, xem lại nhãn và đường dẫn cuối cùng. Các bài viết blog hoặc câu trả lời cũ chỉ nên dùng để định hướng từ khóa, không dùng thay thế tài liệu theo phiên bản khi quyết định tính tương thích.

## 8. Ví dụ thực tế: tra cứu lệnh `bulkWrite` khi nâng từ 7.0 lên 8.0

Giả sử một nhóm cần ghi nhiều thay đổi vào **nhiều collection** trong một request. Khi tìm kiếm, họ gặp hai tên rất giống nhau:

- **`db.collection.bulkWrite()`** — phương thức trong `mongosh` để thực hiện nhiều thao tác ghi trên **một collection**.
- **`bulkWrite` database command** được giới thiệu ở **MongoDB Server 8.0** — hỗ trợ thao tác bulk liên quan **nhiều collection** trong một request.

Nếu chỉ nhìn từ `bulkWrite`, nhóm có thể nhầm rằng hệ thống 7.0 đã hỗ trợ sẵn cả hai kiểu. Cách tra cứu đúng:

1. Ghi yêu cầu rõ ràng: "multi-collection bulk write, MongoDB Server 7.0 hay 8.0?".
2. Kiểm tra `db.version()` của deployment và xem FCV nếu môi trường đang nâng cấp.
3. Mở [Release Notes MongoDB 8.0](https://www.mongodb.com/docs/v8.0/release-notes/8.0/) để xác định **lệnh** mới được đưa vào phiên bản nào.
4. Mở reference của **database command** và trang của **`db.collection.bulkWrite()`** tương ứng; đọc phần giới hạn, quyền, cú pháp, điều kiện và khả năng phía driver.
5. Nếu môi trường vẫn là 7.0, không áp dụng lệnh server 8.0 chỉ vì phương thức cùng tên tồn tại ở 7.0. Nếu đã lên 8.0, tiếp tục kiểm tra patch, FCV và đường gọi từ client phù hợp.

Ví dụ này chỉ ra vì sao phải phân biệt **tên tính năng**, **loại API**, **sản phẩm tài liệu** và **nhánh phiên bản**. Một đoạn code có tên tương tự không đủ để chứng minh khả năng tương thích.

## 9. Những nhầm lẫn thường gặp và cách tự sửa

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| "Collection là bảng SQL nên document nào cũng phải có cùng cột." | Collection chứa document có schema linh hoạt; quy tắc schema có thể được áp dụng bằng validation và ở tầng ứng dụng. |
| "BSON chỉ là chuỗi JSON được mã hóa." | BSON là định dạng nhị phân có nhiều kiểu dữ liệu; hiển thị trong shell/Extended JSON không đồng nghĩa dữ liệu lưu trữ là JSON text. |
| "`_id` luôn là ObjectId." | `_id` là định danh; `ObjectId` chỉ là kiểu thường dùng, không phải kiểu bắt buộc trong mọi trường hợp. |
| "`find()` trả luôn một array." | `find()` thường trả **cursor**; phải duyệt hoặc chuyển thành mảng khi cần và cân nhắc bộ nhớ. |
| "Mọi toán tử bắt đầu `$` đều dùng được ở mọi vị trí." | Query operator, update operator, aggregation expression và pipeline stage có ngữ cảnh cú pháp khác nhau. |
| "Có index thì mọi truy vấn đều nhanh." | Cần khớp bộ lọc/sắp xếp và kiểm tra kế hoạch thực thi, dữ liệu thực tế, chi phí ghi. |
| "Replica set và sharding là một." | Replication phục vụ độ sẵn sàng/bản sao; sharding phân phối dữ liệu. Shard thường dùng replica set, nhưng là hai cơ chế khác nhau. |
| "Đọc secondary chắc chắn thấy ngay ghi mới nhất." | Phụ thuộc replication, read preference, read concern và ngữ cảnh phiên. |
| "`mongosh --version` là version database đang chạy." | Đó là phiên bản shell cục bộ; `db.version()` cho biết instance server đang kết nối. |
| "FCV = server version = Stable API version." | Đây là ba lớp độc lập, có mục đích khác nhau. |
| "Trang `/manual/` hôm nay dùng được thì sau này vẫn cùng phiên bản." | Đường dẫn hiện hành có thể thay đổi; lưu URL nhánh cố định khi cần tái lập. |
| "Tính năng có trên Server Manual thì Java Driver của tôi chắc chắn có API đó." | Cần đọc cả tài liệu driver, ma trận tương thích và các ghi chú phiên bản của client. |

## 10. Bài tập tự kiểm tra

**Bài 1 — Phân loại thuật ngữ.** Với document `orders` ở mục 1, hãy chỉ ra database, collection, field lồng nhau, array và khóa định danh. Trả lời: database minh họa là `shop`, collection `orders`, field lồng `customer.city`, array `items`, khóa định danh `_id`.

**Bài 2 — Dự đoán lệnh.** Đoạn `db.orders.find({ status: "PAID" }, { orderNo: 1, _id: 0 })` thực hiện những gì? Trả lời: filter chọn document `status = "PAID"`; projection trả `orderNo` và loại `_id`; kết quả là cursor.

**Bài 3 — Nhận dạng pipeline.** Trong `[{ $match: ... }, { $group: ... }]`, stage nào lọc document và stage nào tổng hợp? Trả lời: `$match` lọc, `$group` nhóm/tổng hợp theo khóa nhóm.

**Bài 4 — Tra cứu theo phiên bản.** Một máy dev cài `mongosh` bản mới nhưng ứng dụng kết nối MongoDB Server 7.0. Bạn định dùng một stage được trang tài liệu 8.0 đánh dấu `New in version 8.0`. Có thể áp dụng trực tiếp chưa? Trả lời: **chưa thể kết luận là dùng được**; phải dựa trên server deployment thực, tài liệu 7.0, các điều kiện FCV/driver/môi trường, và thử trên hệ thống phù hợp.

**Bài 5 — Phân biệt phiên bản.** Khi `db.version()` cho ra `8.0.x` nhưng `featureCompatibilityVersion.version` là `7.0`, phải ghi nhận ra sao? Trả lời: server binary thuộc nhánh 8.0, FCV đang ở mức 7.0; tra cứu hướng dẫn nâng cấp chính thức trước khi dùng tính năng có ràng buộc FCV, không tự đổi tham số để thử.

## 11. Bộ tài liệu tham chiếu chính thức

Các đường dẫn sau dành cho việc tra cứu tiếp; với trang không cố định phiên bản, hãy kiểm tra bộ chọn phiên bản và nhãn sản phẩm trên giao diện:

- [MongoDB Database Manual (nhánh hiện hành)](https://www.mongodb.com/docs/manual/) — điểm vào tổng quát.
- [Database Manual 8.0](https://www.mongodb.com/docs/v8.0/) và [Database Manual 7.0](https://www.mongodb.com/docs/v7.0/) — ví dụ tài liệu có nhánh phiên bản cố định.
- [Documents — 8.0](https://www.mongodb.com/docs/v8.0/core/document/) — BSON document, field, `_id`, giới hạn kích thước, dot notation.
- [Databases and Collections — 8.0](https://www.mongodb.com/docs/v8.0/core/databases-and-collections/) — cấu trúc dữ liệu.
- [CRUD Operations — 8.0](https://www.mongodb.com/docs/v8.0/crud/) và [`db.collection.find()` — 8.0](https://www.mongodb.com/docs/v8.0/reference/method/db.collection.find/) — thao tác truy vấn.
- [Manual Reference — 8.0](https://www.mongodb.com/docs/v8.0/reference/) — glossary, commands, mongosh methods, query language, giới hạn.
- [MongoDB Versions and Upgrade Paths](https://www.mongodb.com/docs/mongodb-versions/) — cách đánh số phiên bản và quy trình nâng cấp.
- [Release Notes — 8.0](https://www.mongodb.com/docs/v8.0/release-notes/) — thay đổi theo release/patch.
- [`db.version()`](https://www.mongodb.com/docs/manual/reference/method/db.version/) — kiểm tra phiên bản instance đang kết nối.
- [Feature Compatibility Version / `setFeatureCompatibilityVersion`](https://www.mongodb.com/docs/manual/reference/command/setfeaturecompatibilityversion/) — ngữ nghĩa FCV và cách **đọc** FCV qua `getParameter`; đọc đúng nhánh phiên bản trước khi làm thao tác quản trị.
- [Stable API](https://www.mongodb.com/docs/manual/reference/stable-api/) — phạm vi cam kết tương thích API.
- [Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — tài liệu Java driver; chọn đúng phiên bản thư viện trong dự án.

Điều cần duy trì khi học MongoDB là luôn đặt tên **đúng đối tượng** đang nói đến và luôn ghi **đúng phiên bản** của đối tượng đó. Khi biết một tên thuộc tầng dữ liệu, tầng truy vấn, tầng topology hay tầng client, bạn sẽ tìm được tài liệu phù hợp nhanh hơn và tránh áp dụng nhầm hướng dẫn giữa các bản phát hành.
