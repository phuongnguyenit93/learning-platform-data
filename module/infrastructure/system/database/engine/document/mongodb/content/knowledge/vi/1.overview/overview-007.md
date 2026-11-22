# Kiến thức đầu vào và trình tự học MongoDB: từ document đến vận hành

MongoDB là cơ sở dữ liệu hướng tài liệu (document database). Để sử dụng tốt MongoDB, người học cần đi theo một chuỗi năng lực liên thông: **hiểu dữ liệu được biểu diễn thành document như thế nào → thiết kế collection theo cách ứng dụng truy cập → đọc, ghi và tổng hợp dữ liệu đúng → đo và tối ưu truy vấn → bảo đảm tính nhất quán, an toàn → triển khai, sao lưu, giám sát và xử lý sự cố**.

Bài này xây dựng bản đồ học tập từ người đã biết lập trình cơ bản đến người có thể tham gia vận hành một hệ thống MongoDB. Các lệnh minh họa dùng **mongosh**, JavaScript và một cơ sở dữ liệu thực hành tên **`mongo_learning`**. Tên collection, dữ liệu và số liệu chỉ phục vụ học tập; khi triển khai thật phải điều chỉnh theo nhu cầu, tải và phiên bản đang sử dụng.

## 1. Đích đến: cần làm được gì?

Một người hoàn thành lộ trình phải trả lời được ba nhóm câu hỏi:

1. **Dữ liệu:** Một thực thể nên lưu thành document nào? Khi nào nhúng (embed) và khi nào tham chiếu (reference)? Làm sao bảo vệ tính hợp lệ của dữ liệu?
2. **Truy cập:** Với các truy vấn và cập nhật thật, cần chỉ mục nào? Làm sao biết MongoDB đang quét nhiều document, tốn thời gian ở đâu và khi nào cần transaction?
3. **Vận hành:** Hệ thống chịu lỗi của máy chủ ra sao? Dữ liệu có được sao lưu, phục hồi và bảo vệ không? Khi độ trễ tăng, dung lượng gần đầy hoặc replication chậm thì phải quan sát và xử lý theo thứ tự nào?

### Bản đồ phụ thuộc kiến thức

~~~mermaid
flowchart TD
    A["Nền tảng: JSON, HTTP, ứng dụng, truy vấn dữ liệu"] --> B["BSON, document, collection, _id"]
    B --> C["CRUD và truy vấn"]
    C --> D["Thiết kế schema theo access pattern"]
    D --> E["Validation, index, explain"]
    E --> F["Aggregation và hiệu năng"]
    F --> G["Atomicity, concurrency, transaction"]
    G --> H["Ứng dụng, driver, connection"]
    H --> I["Replica set và tính sẵn sàng"]
    I --> J["Sharding, mở rộng quy mô"]
    H --> K["Bảo mật, sao lưu, phục hồi"]
    I --> K
    J --> L["Giám sát, tuning và runbook"]
    K --> L
~~~

Sơ đồ biểu thị **thứ tự ưu tiên học**; khi làm dự án thực tế, thiết kế dữ liệu, index, bảo mật và quan sát vận hành cần được xem xét lặp lại cùng nhau.

## 2. Kiến thức đầu vào

| Nền tảng | Cần hiểu đến mức nào? | Vì sao cần? |
|---|---|---|
| Lập trình | Biến, hàm, điều kiện, vòng lặp, object, array, exception | Đọc ví dụ mongosh/driver, xử lý kết quả và lỗi |
| JSON và kiểu dữ liệu | Object lồng nhau, array, string, number, boolean, null | Nhận diện cấu trúc document và hiểu khác biệt với BSON |
| Cơ sở dữ liệu | Khái niệm lưu trữ bền vững, khóa, truy vấn, index, ràng buộc dữ liệu | So sánh mô hình quan hệ với mô hình document một cách đúng đắn |
| Ứng dụng backend | Luồng HTTP → service → database, phân trang, lọc, cập nhật | Thiết kế dữ liệu theo cách ứng dụng thật sử dụng |
| Command line | Chạy chương trình, cấu hình, đọc log, dùng biến môi trường | Dựng môi trường, chẩn đoán và sao lưu |
| Mạng máy tính | Host, port, DNS, TLS, timeout, kết nối bị ngắt | Hiểu connection string, kết nối client và sự cố kết nối |
| Hệ điều hành | Process, RAM, CPU, disk, file system, quyền truy cập | Phân biệt sự cố MongoDB với sự cố hạ tầng |

**Không bắt buộc** biết trước cơ sở dữ liệu quan hệ hoặc hệ thống phân tán, nhưng có kiến thức SQL sẽ giúp đối chiếu. Nếu chưa biết index, transaction hay replication, có thể học ngay ở các chặng tương ứng.

### Bản đồ thuật ngữ

| Khái niệm gần với SQL | MongoDB | Điểm khác biệt cần nhớ |
|---|---|---|
| Database | Database | Chứa các collection |
| Table | Collection | Collection chứa document, không đòi mọi document có cùng tập field |
| Row | Document | Là cấu trúc BSON có thể chứa object/array lồng nhau |
| Column | Field | Một field có thể là giá trị đơn, object hoặc array |
| Primary key | `_id` | Duy nhất trong collection; thường là ObjectId nhưng có thể dùng kiểu khác |
| Join | `$lookup` hoặc thiết kế dữ liệu nhúng/tham chiếu | Không phải mọi quan hệ đều cần join ở thời điểm đọc |
| Index | Index | Tăng tốc một số truy vấn nhưng tiêu tốn lưu trữ và chi phí ghi |

Không nên hiểu MongoDB đơn thuần là “SQL với dữ liệu JSON”. Cách đặt ranh giới document và cách chọn index quyết định rất nhiều đến hiệu năng, tính nhất quán và độ phức tạp vận hành.

## 3. Chuẩn bị phòng thực hành

Cần một MongoDB server và **mongosh** tương thích. Có thể dùng máy cá nhân, một môi trường lab được cấp sẵn hoặc cụm được quản lý. Chỉ chạy các ví dụ ghi/xóa trong môi trường thử nghiệm.

Ví dụ chạy MongoDB bằng Docker để học cục bộ:

~~~bash
docker run --name mongo-learning \
  -p 127.0.0.1:27017:27017 \
  -d mongo:8

mongosh "mongodb://127.0.0.1:27017"
~~~

Container minh họa chưa bật authentication; chỉ dùng cục bộ với port bind vào loopback. **Không mở dịch vụ không xác thực ra mạng công cộng**, không dùng cấu hình lab này làm cấu hình production. Môi trường production phải có kiểm soát truy cập, TLS, cấu hình bền vững cho lưu trữ và phương án khôi phục.

Trong mongosh:

~~~javascript
use mongo_learning
db.getName()
db.runCommand({ ping: 1 })
~~~

Nếu lệnh trả `ok: 1`, kết nối đang hoạt động. Khi thực hành phân tích hành vi replica set, transaction đa document hoặc sharding, cần một môi trường riêng có cấu hình tương ứng; **MongoDB standalone không cung cấp mọi tính năng của cluster**.

### Bộ dữ liệu xuyên suốt

Ta giả định một ứng dụng bán hàng có sản phẩm, khách hàng và đơn hàng. Để dễ theo dõi, ID trong lab là chuỗi dễ đọc; ở ứng dụng thật cần chọn chiến lược ID nhất quán.

~~~javascript
use mongo_learning

db.products.insertMany([
  {
    _id: "p-101",
    name: "Bàn phím",
    category: "accessory",
    status: "ACTIVE",
    price: NumberDecimal("125000.00"),
    stock: 10,
    tags: ["office", "usb"],
    createdAt: ISODate("2026-01-01T08:00:00Z")
  },
  {
    _id: "p-102",
    name: "Chuột",
    category: "accessory",
    status: "ACTIVE",
    price: NumberDecimal("99000.00"),
    stock: 20,
    tags: ["office", "wireless"],
    createdAt: ISODate("2026-01-02T08:00:00Z")
  },
  {
    _id: "p-103",
    name: "Màn hình",
    category: "display",
    status: "HIDDEN",
    price: NumberDecimal("2900000.00"),
    stock: 4,
    tags: ["office"],
    createdAt: ISODate("2026-01-03T08:00:00Z")
  }
])

db.customers.insertOne({
  _id: "c-001",
  name: "Lan",
  contact: { email: "lan@example.test" },
  addresses: [
    { label: "home", city: "Hà Nội", isDefault: true }
  ],
  createdAt: ISODate("2026-01-01T09:00:00Z")
})

db.orders.insertOne({
  _id: "o-1001",
  customerId: "c-001",
  status: "PAID",
  items: [
    {
      productId: "p-101",
      productName: "Bàn phím",
      qty: 2,
      unitPrice: NumberDecimal("125000.00")
    }
  ],
  total: NumberDecimal("250000.00"),
  createdAt: ISODate("2026-01-05T10:00:00Z")
})
~~~

Nếu chạy lại dữ liệu mẫu lần thứ hai, `insertOne/insertMany` với cùng `_id` sẽ gặp lỗi trùng khóa. Điều đó là hành vi đúng; nên dùng database mới hoặc xóa dữ liệu lab có chủ đích trước khi lặp lại. **Không sao chép lệnh xóa dữ liệu sang môi trường thật**.

## 4. Chặng 1 — Hiểu document, BSON và ranh giới collection

### 4.1. Document không hoàn toàn là JSON

MongoDB lưu document dưới dạng **BSON** (Binary JSON), hỗ trợ những kiểu vượt quá JSON thông thường, chẳng hạn:

- `ObjectId`: giá trị định danh thường được MongoDB tạo mặc định cho `_id`.
- `Date`: thời điểm; phải phân biệt giá trị thời gian có múi giờ hiển thị với chuỗi ngày.
- `Decimal128`: số thập phân có độ chính xác thích hợp cho nhiều nghiệp vụ tài chính.
- `Int32`, `Int64`, `Double`: các biểu diễn số khác nhau.
- `Binary`, `Boolean`, `String`, `Array`, object lồng nhau và `Null`.

Ví dụ:

~~~javascript
db.examples.insertOne({
  title: "BSON types",
  publishedAt: new Date(),
  amount: NumberDecimal("19.95"),
  active: true,
  labels: ["intro", "database"],
  author: { name: "Mai", level: 2 },
  optionalNote: null
})
~~~

**Field vắng mặt khác với field mang giá trị `null`**. Sự khác nhau này ảnh hưởng đến validation, cách lọc và cập nhật. Khi cần lọc chính xác field tồn tại, nên dùng `$exists` và hiểu thêm hành vi của toán tử khi dữ liệu có `null`.

Một document BSON có giới hạn kích thước **16 MiB**. Đây là tín hiệu kiến trúc quan trọng: không nhúng vô hạn lịch sử sự kiện, danh sách bình luận hoặc dữ liệu tăng không giới hạn vào một document duy nhất.

### 4.2. Tư duy theo aggregate và truy cập

Hãy hỏi “Những trường nào thường được lấy, hiển thị và cập nhật cùng nhau?” trước khi hỏi “Mỗi đối tượng có phải một collection riêng không?”. Ví dụ:

- Địa chỉ giao hàng của khách có thể nhúng trong document khách nếu danh sách nhỏ và luôn hiển thị cùng hồ sơ.
- Các dòng hàng của một đơn hàng thường nhúng vào đơn; mỗi dòng giữ `unitPrice` tại thời điểm mua để giá lịch sử không thay đổi theo catalog.
- Thông tin sản phẩm đầy đủ thuộc collection `products`; trong order chỉ giữ snapshot cần thiết như tên và giá.
- Dòng sự kiện hay log tăng mãi nên nằm ở collection riêng, phân vùng/giới hạn vòng đời theo nhu cầu.

MongoDB bảo đảm atomicity cho **một thao tác ghi trên một document**. Đây là một trong những lý do ranh giới document rất quan trọng.

**Bài thực hành:** Vẽ lại collection `customers`, `products` và `orders`, đánh dấu phần nào là dữ liệu sở hữu riêng, phần nào là snapshot và phần nào là tham chiếu. Giải thích cách xử lý nếu đổi tên sản phẩm sau khi đã có đơn hàng.

**Hoàn thành khi:** Đọc được document BSON, phân biệt `_id`/field/array, xác định đúng ba cấu trúc nhúng/tham chiếu và chỉ ra ít nhất một nguy cơ document tăng không giới hạn.

## 5. Chặng 2 — CRUD: đọc, lọc, cập nhật, xóa

CRUD là nền tảng cho mọi hoạt động dữ liệu. Cần đọc được filter, projection, sort, limit và các update operator thông dụng.

### 5.1. Truy vấn

~~~javascript
// Lấy sản phẩm đang bán, không trả về _id
db.products.find(
  { status: "ACTIVE" },
  { _id: 0, name: 1, price: 1, stock: 1 }
)

// Giá ít nhất 100000, sắp xếp tăng dần
db.products.find({
  price: { $gte: NumberDecimal("100000.00") }
}).sort({ price: 1, _id: 1 }).limit(10)

// Lọc mảng tags theo một phần tử
db.products.find({ tags: "wireless" })

// Lọc object lồng nhau bằng dot notation
db.customers.find({ "contact.email": "lan@example.test" })
~~~

Trong tìm kiếm theo mảng, phép so sánh một phần tử như `{ tags: "wireless" }` sẽ tìm document có phần tử tương ứng. Với nhiều điều kiện phải đúng trên **cùng một phần tử object trong mảng**, tìm hiểu `$elemMatch`.

### 5.2. Cập nhật

~~~javascript
// Chỉ cập nhật field được nêu, không thay toàn document
db.products.updateOne(
  { _id: "p-101" },
  {
    $set: { status: "ACTIVE" },
    $inc: { stock: 5 },
    $currentDate: { updatedAt: true }
  }
)

// Thêm tag nếu chưa có
db.products.updateOne(
  { _id: "p-101" },
  { $addToSet: { tags: "featured" } }
)

// Trừ tồn kho khi còn đủ: điều kiện và cập nhật xảy ra nguyên tử
const result = db.products.updateOne(
  { _id: "p-101", stock: { $gte: 2 } },
  { $inc: { stock: -2 } }
)
print(result.modifiedCount)
~~~

Trong ví dụ cuối, `modifiedCount === 1` cho biết một document đã được giảm tồn kho. Nếu bằng 0, cần kiểm tra điều kiện không khớp hay dữ liệu không đáp ứng, rồi trả lỗi nghiệp vụ phù hợp. Tránh mẫu **đọc số lượng → kiểm tra ở ứng dụng → ghi số lượng mới** vì nhiều yêu cầu đồng thời có thể tranh chấp.

### 5.3. Thao tác xóa, upsert và idempotency

`deleteOne` và `deleteMany` là thao tác có tác dụng xóa dữ liệu; chỉ dùng trên bản ghi được chọn có chủ đích. `updateOne(..., { upsert: true })` có thể thêm document khi chưa tồn tại, nhưng phải hiểu khóa xác định bản ghi và rủi ro tạo trùng trong thao tác đồng thời. Dùng unique index để bảo đảm tính duy nhất khi nghiệp vụ đòi hỏi.

Không nên dùng `skip` với offset rất lớn làm chiến lược phân trang mặc định. Ở bước nâng cao, học **keyset pagination**: lấy trang tiếp theo qua điều kiện trên bộ khóa sắp xếp ổn định, ví dụ `(createdAt, _id)`.

**Bài thực hành:** Tạo bộ lọc kết hợp category/status/price, trả tối đa 10 bản ghi; cập nhật tag và tồn kho; dùng `$elemMatch` trên một mảng object tự tạo; giải thích điều kiện để một thao tác cập nhật có thể chạy lặp lại mà không gây tăng số lượng sai.

**Hoàn thành khi:** Tự viết được CRUD, hiểu `matchedCount` khác `modifiedCount`, biết xử lý dữ liệu không tìm thấy và không phát sinh mất cập nhật do kiểm tra tách khỏi lệnh ghi.

## 6. Chặng 3 — Thiết kế schema theo access pattern

MongoDB cho phép document linh hoạt, nhưng **schema linh hoạt không đồng nghĩa với bỏ qua thiết kế dữ liệu**. Thiết kế bắt đầu bằng danh sách use case và hình dạng truy vấn, không chỉ bằng sơ đồ thực thể.

### 6.1. Thu thập access pattern trước khi chọn mô hình

Ví dụ với ứng dụng bán hàng:

| Nghiệp vụ | Đọc/ghi chính | Gợi ý mô hình |
|---|---|---|
Xem giỏ/đơn cùng các dòng hàng | Một đơn, toàn bộ `items` | Nhúng `items` vào `orders` |
| Tra cứu lịch sử đơn của khách | Nhiều đơn theo `customerId`, mới nhất trước | Tham chiếu khách; index trên `customerId, createdAt` |
| Hiển thị giá sản phẩm mới nhất | Đọc `products` theo `_id` | Product có nguồn dữ liệu riêng |
| Xem đơn hàng đã chốt giá | Giá tại thời điểm mua | Snapshot `unitPrice` trong order |
| Ghi nhật ký thao tác liên tục | Tần suất ghi cao, dữ liệu tăng liên tục | Collection log/event riêng, retention phù hợp |

### 6.2. Chọn embed hoặc reference

**Ưu tiên embed** khi dữ liệu con có kích thước được giới hạn, cùng vòng đời, thường cần lấy đồng thời và cần cập nhật nguyên tử trong cùng document.

**Ưu tiên reference** khi dữ liệu có vòng đời riêng, được nhiều document dùng chung, có độ lớn tăng không giới hạn hoặc cần truy vấn độc lập. Reference có thể dẫn đến nhiều truy vấn hoặc dùng `$lookup`; chi phí cần đo bằng dữ liệu và workload thực.

Các tình huống cần chú ý:

- **Quan hệ một–một:** có thể gộp khi cùng vòng đời và ít dùng độc lập.
- **Một–nhiều có giới hạn:** nhúng mảng khi kích thước được kiểm soát.
- **Một–nhiều không giới hạn:** không nhúng mọi phần tử vào một document cha.
- **Nhiều–nhiều:** thường cần tham chiếu hoặc cấu trúc trung gian; quyết định theo truy vấn cụ thể.
- **Dữ liệu snapshot:** chủ động lặp một phần dữ liệu giúp giữ đúng lịch sử; phải rõ field nào được đồng bộ và field nào bất biến.

### 6.3. Quản lý thay đổi schema

Khi ứng dụng thay đổi, document cũ và mới có thể cùng tồn tại. Cần xác định:

1. Field nào được thêm, đổi tên hoặc đổi kiểu?
2. Phiên bản ứng dụng cũ có đọc được document mới không?
3. Có cần backfill dữ liệu cũ không, và backfill có thể chạy từng đợt không?
4. Index mới có được tạo trước khi phát hành truy vấn mới không?
5. Rollback ứng dụng có tương thích với dữ liệu đã ghi không?

Có thể thêm `schemaVersion` khi có nhu cầu migrate phức tạp, nhưng đừng làm field này thành cách né validation. Với dữ liệu quan trọng, định nghĩa và kiểm tra schema ngay cả khi database cho phép linh hoạt.

**Bài thực hành:** Thiết kế lại một hệ thống bình luận bài viết, trong đó số bình luận có thể tăng rất lớn. Viết ba truy vấn mục tiêu; quyết định field nào nằm trong bài viết, field nào ở collection bình luận, index dự kiến và cách lấy trang.

**Hoàn thành khi:** Mỗi quyết định embed/reference đều gắn với một access pattern, ràng buộc kích thước, nguyên tử hoặc vòng đời dữ liệu cụ thể.

## 7. Chặng 4 — Validation, ràng buộc và tính đúng đắn của dữ liệu

Không thể dựa vào tính linh hoạt của document để mặc định rằng mọi dữ liệu đều hợp lệ. Nên kết hợp kiểm tra ở application với **collection validation** và **unique index** khi cần.

Ví dụ tạo collection riêng có schema validation:

~~~javascript
db.createCollection("products_validated", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name", "price", "stock", "status"],
      properties: {
        name:   { bsonType: "string", minLength: 1 },
        price:  { bsonType: "decimal" },
        stock:  { bsonType: ["int", "long"], minimum: 0 },
        status: { enum: ["ACTIVE", "HIDDEN"] }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
~~~

Đây là ví dụ tạo collection mới. Các lệnh insert vào `products` ở đầu bài **không tự động** bị ràng buộc bởi validator của `products_validated`. Trong ứng dụng thật cần kiểm tra kiểu số do driver ghi: `2` có thể được mã hóa thành những BSON number type khác nhau tùy driver/cách tạo giá trị.

### Ba lớp tính đúng đắn

- **Application validation:** kiểm tra nghiệp vụ và thông báo lỗi tốt cho người dùng, ví dụ số lượng phải dương.
- **Database validation:** ngăn document sai kiểu hoặc thiếu field quan trọng ngay ở tầng lưu trữ; không thay thế logic nghiệp vụ phức tạp.
- **Index duy nhất:** ví dụ email normalized phải duy nhất trong một tập người dùng, kể cả khi hai request tạo tài khoản đồng thời. Chú ý giá trị thiếu/null, collation và việc index có phải partial hay không.

Đọc kết quả lỗi ghi: `duplicate key` khác `document validation failure` và khác `network timeout`. Một lần ghi bị timeout **không tự chứng minh** dữ liệu chưa được ghi; cách retry phải xét tính idempotent, retryable writes, khóa nghiệp vụ và trạng thái thực tế.

**Bài thực hành:** Dựng collection người dùng có email duy nhất theo quy tắc nghiệp vụ, cố tình insert trùng; thêm validator bắt buộc `name` và `createdAt`; ghi lại loại lỗi quan sát được.

**Hoàn thành khi:** Nêu rõ ràng buộc nào ở application, ràng buộc nào ở database và giải thích vì sao kiểm tra tồn tại trước khi insert chưa đủ bảo đảm uniqueness.

## 8. Chặng 5 — Index, query planner và `explain`

Query chạy đúng chưa đủ; phải biết query chạy thế nào khi dữ liệu lớn. MongoDB có thể dùng index để tránh quét nhiều document, nhưng mỗi index cũng tiêu thụ disk, memory và làm tăng chi phí cập nhật.

### 8.1. Bắt đầu từ query thật

Giả sử trang catalog yêu cầu: `status = ACTIVE`, `category = accessory`, sắp xếp giá tăng.

~~~javascript
db.products.find({
  status: "ACTIVE",
  category: "accessory"
}).sort({ price: 1 }).explain("executionStats")

db.products.createIndex({
  status: 1,
  category: 1,
  price: 1
})

db.products.find({
  status: "ACTIVE",
  category: "accessory"
}).sort({ price: 1 }).explain("executionStats")
~~~

Các chỉ số cần so sánh gồm **`winningPlan`**, `totalKeysExamined`, `totalDocsExamined`, `nReturned` và thời gian thực thi quan sát được. `COLLSCAN` thường thể hiện quét collection; `IXSCAN` cho biết một nhánh kế hoạch sử dụng index. Chỉ riêng thấy `IXSCAN` chưa đủ kết luận truy vấn tối ưu: vẫn có thể quét quá nhiều khóa hoặc phải fetch/filter nhiều document.

Tập dữ liệu ví dụ rất nhỏ nên query planner có thể chọn scan toàn collection; điều đó không có nghĩa index sai. Phải đo với dữ liệu đại diện và cùng kiểu truy vấn của hệ thống thật.

### 8.2. Các loại index học theo thứ tự

| Loại | Khi nào học/dùng? | Điều cần chú ý |
|---|---|---|
| Single-field | Lọc hoặc sort theo một field | Có thể không đáp ứng query kết hợp |
| Compound | Lọc nhiều field, sort, range | Thứ tự field phụ thuộc workload; xét equality, sort và range |
| Multikey | Field là array | Index có semantics và hạn chế riêng khi dữ liệu là mảng |
| Unique | Bảo đảm uniqueness | Dữ liệu trùng hiện có khiến tạo index thất bại |
| Partial | Chỉ index document thỏa điều kiện | Truy vấn phải tương thích điều kiện lọc mới tận dụng được |
| TTL | Tự động loại dữ liệu hết vòng đời | Xóa không xảy ra đúng thời điểm đến hạn; không thay thế lịch retention/backup |
| Text / search chuyên dụng | Tìm kiếm văn bản | Phân biệt khả năng native text index với dịch vụ full-text search chuyên biệt |
| Wildcard / hashed / geospatial | Workload đặc thù | Chỉ dùng khi đã hiểu truy vấn và giới hạn tương ứng |

**Quy tắc học:** viết query trước, quan sát plan, chọn index, chạy lại `explain`, đo tác động đến ghi và dung lượng. Tránh tạo index “cho mọi field”.

### 8.3. Sắp xếp và phân trang

Một sort ổn định cần tiêu chí phân xử các bản ghi có cùng khóa. Ví dụ lịch sử đơn:

~~~javascript
db.orders.createIndex({ customerId: 1, createdAt: -1, _id: -1 })

db.orders.find({ customerId: "c-001" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
~~~

Khi lượng đơn lớn, có thể dùng keyset dựa trên `createdAt` và `_id` của phần tử cuối trang trước; thiết kế điều kiện so sánh đúng thứ tự sort và lưu ý dữ liệu được thêm trong lúc phân trang.

**Bài thực hành:** Tạo nhiều document demo hơn, thu `explain("executionStats")` trước/sau index, giải thích cả số quét và lợi ích thực. Làm hai query có access pattern khác nhau và thảo luận liệu một index có đáp ứng cả hai.

**Hoàn thành khi:** Chọn index dựa trên filter/sort, đọc được `explain`, hiểu trade-off đọc–ghi và không kết luận tối ưu chỉ từ một lần chạy trên dataset tí hon.

## 9. Chặng 6 — Aggregation pipeline

Aggregation xử lý dữ liệu qua chuỗi stage. Nên bắt đầu bằng `$match`, `$project`, `$unwind`, `$group`, `$sort`, `$limit` rồi mới đến `$lookup`, `$facet` và các stage chuyên biệt.

Ví dụ doanh thu theo khách từ các đơn đã thanh toán:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$customerId",
      revenue: {
        $sum: { $multiply: ["$items.qty", "$items.unitPrice"] }
      },
      itemCount: { $sum: "$items.qty" }
    }
  },
  { $sort: { revenue: -1 } }
])
~~~

Ở đây, `$unwind` biến mỗi phần tử `items` thành một đầu vào cho group. Nếu một đơn có nhiều dòng hàng, chỉ `$sum: "$total"` sau `$unwind` sẽ **đếm trùng tổng đơn**; vì thế phải xác định rõ đơn vị thống kê. Bài tập nên thử thêm đơn với hai dòng hàng để kiểm chứng.

### Câu hỏi cần trả lời cho mỗi pipeline

1. Mỗi stage nhận loại document nào và tạo loại document nào?
2. Lọc sớm có giảm số dữ liệu qua các stage sau không?
3. Có nhân số dòng vì `$unwind` hoặc `$lookup` không?
4. Stage nào dùng index và stage nào phải xử lý/sort nhiều dữ liệu?
5. Kết quả có phụ thuộc múi giờ, tiền tệ, null/missing hay dữ liệu bị ghi đồng thời không?

`$lookup` có thể liên kết dữ liệu từ collection khác, nhưng nếu một màn hình thường xuyên phải gọi nhiều lookup lớn, cần xem lại data model, index và mục tiêu độ trễ. Không nên biến toàn bộ nghiệp vụ thành một pipeline quá phức tạp chỉ để giảm số lần gọi API.

**Bài thực hành:** Viết pipeline tính số đơn và tổng doanh thu theo tháng; thêm điều kiện thời gian; so sánh pipeline lọc trước/đếm sau với pipeline làm ngược; chỉ ra timezone dùng để chia tháng.

**Hoàn thành khi:** Giải thích được data shape qua từng stage, tự tìm lỗi đếm trùng và phân tích được chi phí của `$unwind`, `$sort`, `$group` và `$lookup`.

## 10. Chặng 7 — Atomicity, concurrency và transaction

Đây là chặng chuyển từ “lệnh ghi chạy được” sang “nghiệp vụ đúng khi nhiều yêu cầu xảy ra cùng lúc”.

### 10.1. Một document và nhiều document

MongoDB bảo đảm một thao tác ghi đơn lẻ trên một document là **atomic**. Với một đơn hàng nhúng các item, cập nhật trạng thái và ghi thêm field trong cùng một `updateOne` có thể là một atomic write.

Khi nghiệp vụ cần cập nhật nhiều document/collection như **trừ stock và tạo order**, có thể cần một distributed transaction. Trước khi dùng transaction, vẫn phải cân nhắc:

- Có thể thay cấu trúc dữ liệu để cập nhật một document không?
- Có thể dùng quy trình trạng thái, reservation, outbox hoặc bù trừ phù hợp không?
- Có cần tính nhất quán tức thời giữa các document không?
- Chi phí transaction, khả năng retry và điều kiện chạy cluster là gì?

### 10.2. Ví dụ transaction trong replica set

Ví dụ sau yêu cầu kết nối tới replica set/sharded cluster hỗ trợ transaction. Dùng ID mới cho đơn và bảo đảm lần gọi không tạo trùng:

~~~javascript
const session = db.getMongo().startSession()
try {
  await session.withTransaction(async () => {
    const txDb = session.getDatabase("mongo_learning")
    const stockResult = await txDb.products.updateOne(
      { _id: "p-101", stock: { $gte: 2 } },
      { $inc: { stock: -2 } }
    )
    if (stockResult.modifiedCount !== 1) {
      throw new Error("INSUFFICIENT_STOCK")
    }

    await txDb.orders.insertOne({
      _id: "o-1002",
      customerId: "c-001",
      status: "CREATED",
      items: [{
        productId: "p-101",
        productName: "Bàn phím",
        qty: 2,
        unitPrice: NumberDecimal("125000.00")
      }],
      total: NumberDecimal("250000.00"),
      createdAt: new Date()
    })
  }, {
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })
} finally {
  await session.endSession()
}
~~~

Ví dụ thể hiện ý tưởng atomic nhiều document, **chưa phải hàm checkout production**: cần xử lý lỗi commit không chắc chắn, các lỗi có thể retry, timeout, duplicate order và quy tắc idempotency ở mức request. Driver thường có helper transaction riêng; dùng theo tài liệu của driver/version triển khai. Không tự retry mọi loại lỗi và không đưa side effect bên ngoài database (gửi email, gọi payment API) vào callback có thể chạy lại mà thiếu cơ chế chống lặp.

### 10.3. Read concern, write concern và read preference

| Cấu hình | Câu hỏi mà nó trả lời |
|---|---|
| Write concern | Cần mức xác nhận ghi nào trước khi trả kết quả? Ví dụ `w: "majority"` |
| Read concern | Dữ liệu đọc cần những bảo đảm nhất quán/độ bền nào? |
| Read preference | Đọc từ primary hay secondary nào và trade-off độ trễ/staleness ra sao? |
| Retryable writes/transactions | Có điều kiện retry nào và một thao tác được lặp lại an toàn trong hoàn cảnh nào? |

Không đánh đồng `writeConcern: "majority"` với transaction, không mặc định đọc secondary là dữ liệu mới nhất, và không coi timeout là bằng chứng thao tác chưa xảy ra.

**Bài thực hành:** Mô tả race condition khi hai khách cùng mua món còn một sản phẩm; dùng conditional update giải quyết bước trừ tồn. Chỉ ra khi nào cần transaction để ghi đơn; xây dựng quy tắc chống tạo hai đơn khi request bị gửi lại.

**Hoàn thành khi:** Phân biệt atomic một document với transaction nhiều document và giải thích được ý nghĩa của read/write concern cùng chiến lược retry.

## 11. Chặng 8 — Kết nối ứng dụng và dữ liệu trong production

Học driver (Java, Node.js, Python hoặc ngôn ngữ đang dùng) sau khi hiểu truy vấn trong mongosh. Ở môi trường ứng dụng, tập trung vào:

- Quản lý `MongoClient`/connection pool theo vòng đời ứng dụng, tránh tạo một client mới cho từng request.
- Connection string và cấu hình TLS, chứng thực, DNS, timeout; bí mật đặt trong secret manager hoặc biến môi trường phù hợp, không commit vào Git.
- Ánh xạ kiểu BSON sang kiểu ứng dụng: `ObjectId`, ngày giờ UTC, `Decimal128` và số nguyên lớn.
- Mapping exception sang lỗi nghiệp vụ: duplicate key, validation failure, timeout, transient error, unavailable primary.
- Pagination, projection, giới hạn số document trả về, cancellation/timeout và backpressure khi đọc lượng lớn.
- Thực thi migration có kiểm soát, tương thích nhiều phiên bản ứng dụng khi rolling deployment.
- Thu telemetry theo operation/request nhưng tránh ghi dữ liệu cá nhân hoặc thông tin nhạy cảm vào log.

### Một luồng request có thể quan sát

~~~text
HTTP POST /orders
  -> xác thực và kiểm tra input
  -> xác định idempotency key/định danh đơn
  -> kiểm tra và cập nhật dữ liệu theo quy tắc cạnh tranh
  -> ghi order/stock với cơ chế atomic/transaction phù hợp
  -> xác nhận kết quả hoặc lỗi có phân loại
  -> ghi metrics/log có correlation ID
  -> trả mã HTTP và response ổn định
~~~

Đánh giá thiết kế qua câu hỏi: “Nếu kết nối rớt ngay sau khi server xử lý ghi, ứng dụng trả gì, có retry an toàn không và người dùng có thể tạo hai đơn hay không?”.

**Bài thực hành:** Viết API tối thiểu để tạo và lấy đơn. Thử hai request cùng lúc mua cùng sản phẩm, gửi lại cùng idempotency key, và ngắt kết nối giả lập. Quan sát response, tồn kho và số đơn.

**Hoàn thành khi:** Ứng dụng không làm rò rỉ mật khẩu, có pool/timeout hợp lý, phản hồi lỗi rõ ràng và không tạo dữ liệu trùng khi retry hợp lệ.

## 12. Chặng 9 — Replica set và high availability

MongoDB thường dùng **replica set** để tăng khả năng sẵn sàng và duy trì bản sao dữ liệu. Một replica set có primary nhận phần lớn thao tác ghi và các secondary sao chép thay đổi thông qua cơ chế replication. Khi primary không còn khả dụng, các thành viên đủ điều kiện có thể bầu primary mới.

~~~mermaid
flowchart LR
    App["Application / Driver"] --> P["Primary"]
    P -->|replication| S1["Secondary A"]
    P -->|replication| S2["Secondary B"]
    S1 -. "election khi đủ điều kiện" .-> P
    S2 -. "election khi đủ điều kiện" .-> P
~~~

Sơ đồ đơn giản hóa kiến trúc. Không có bảo đảm “mất primary = failover tức thì không gián đoạn”: election mất thời gian, một số thao tác đang chạy phải retry và ứng dụng cần timeout/cơ chế khôi phục đúng.

### Các khái niệm phải phân biệt

- **Primary / secondary:** vai trò thành viên; primary có thể thay đổi sau election.
- **Oplog:** nhật ký thao tác để secondary theo kịp thay đổi; độ dài cửa sổ oplog là yếu tố quan trọng với bản sao bị chậm/ngắt.
- **Replication lag:** độ trễ sao chép; ảnh hưởng đến độ mới dữ liệu khi đọc secondary và khả năng khôi phục.
- **Majority:** yêu cầu số phiếu/xác nhận phù hợp cấu hình; không đơn giản là “ghi vào mọi node”.
- **Election, quorum, partition:** quyết định node nào có thể làm primary khi mạng hoặc máy chủ gặp sự cố.
- **Read preference / concern:** chọn node và mức nhất quán; phải phù hợp kỳ vọng API.

Các lệnh quan sát trong môi trường replica set:

~~~javascript
rs.status()
db.adminCommand({ hello: 1 })
~~~

Không thực hiện thay đổi cấu hình replica set hoặc cố tình ngắt primary trên hệ thống đang phục vụ người dùng chỉ để thử kiến thức. Làm các bài failover trong cụm lab được kiểm soát.

**Bài thực hành:** Dựng replica set lab theo hướng dẫn tương ứng với phiên bản triển khai; xem vai trò node, tiến hành failover có chủ đích trong lab, ghi nhận biểu hiện ở client và chiến lược retry. Giải thích vì sao secondary lag không đồng nghĩa dữ liệu đã mất.

**Hoàn thành khi:** Vẽ được đường ghi/replication/election, hiểu majority và mô tả giới hạn sẵn sàng thực tế khi xảy ra failover.

## 13. Chặng 10 — Sharding và mở rộng

**Replica set** thường được giới thiệu để học tính sẵn sàng trước; **sharding** nhằm phân phối dữ liệu và tải trên nhiều shard khi một tập dữ liệu hoặc workload vượt khả năng của cấu hình đơn giản. Sharded cluster bổ sung router và metadata quản lý placement.

~~~mermaid
flowchart TB
    Client["Client / Driver"] --> Router["mongos router"]
    Router --> S1["Shard 1 (replica set)"]
    Router --> S2["Shard 2 (replica set)"]
    Router --> S3["Shard 3 (replica set)"]
    Config["Config server replica set"] -. "cluster metadata" .-> Router
~~~

### Shard key là quyết định thiết kế lớn

Shard key ảnh hưởng đến việc định tuyến query, phân phối dữ liệu, phân phối ghi và khả năng xuất hiện **hotspot**. Cần đánh giá:

1. Tần suất và phân bố các giá trị shard key.
2. Query quan trọng có chứa điều kiện shard key để target đúng shard không?
3. Khóa có độ đa dạng (cardinality) phù hợp không?
4. Ghi có dồn lên một vùng khóa tăng tuần tự không?
5. Cơ chế unique index, transaction, join và các thao tác quản trị có bị giới hạn bởi sharding không?

Đừng học sharding bằng cách “cứ dữ liệu lớn là thêm shard”. Nhiều bài toán được giải quyết trước bằng schema tốt, index phù hợp, tối ưu truy vấn, dung lượng máy hoặc chính sách retention.

**Bài thực hành:** Giả định 100 triệu đơn hàng và truy vấn chủ yếu là “đơn theo khách”. So sánh shard key theo `customerId`, `createdAt` và một khóa ghép; chỉ rõ rủi ro skew/hotspot và query phải quét nhiều shard. Sau đó quan sát routing trong cluster lab.

**Hoàn thành khi:** Phân biệt replica set/sharding, giải thích `mongos` và thiết kế được bảng đánh giá shard key dựa trên workload thay vì chọn ngẫu nhiên.

## 14. Chặng 11 — Bảo mật và quản trị quyền

An toàn phải được đưa vào thiết kế từ sớm, nhưng sau khi hiểu ứng dụng và cluster, người học có thể cấu hình đầy đủ hơn:

- **Authentication:** xác thực client/người vận hành; cấu hình trong môi trường được quản lý thay vì để database mở.
- **Authorization:** mỗi ứng dụng, job migration và người vận hành có quyền phù hợp chức năng; áp dụng nguyên tắc quyền tối thiểu.
- **TLS:** mã hóa kết nối, kiểm tra danh tính server/certificate phù hợp; không vô hiệu hóa xác minh chứng chỉ để “cho chạy được”.
- **Network isolation:** giới hạn nguồn có thể kết nối; không công khai port database khi không cần.
- **Secrets management:** luân chuyển mật khẩu/token/certificate; không ghi mật khẩu thô vào source, URL công khai, log hoặc screenshot.
- **Encryption at rest / backup protection:** xem xét cơ chế mã hóa, quản lý khóa và chính sách lưu bản sao.
- **Audit và data governance:** xác định ai có thể truy cập/sửa dữ liệu quan trọng, retention và xóa dữ liệu theo yêu cầu.

Ví dụ phân loại danh tính: ứng dụng chỉ cần quyền đọc/ghi trên database nghiệp vụ; tài khoản quản trị cluster và tài khoản backup nên tách khỏi tài khoản ứng dụng. Việc tạo user, role hoặc bật authentication phải theo hướng dẫn cụ thể của topology và cơ chế deployment đang dùng.

**Bài thực hành:** Lập ma trận quyền cho API backend, report job, backup job và người vận hành. Với mỗi vai trò, ghi rõ database, collection, thao tác cần thiết và cách thu hồi quyền. Kiểm tra kết nối TLS/auth trong lab.

**Hoàn thành khi:** Không còn dùng tài khoản quản trị cho mọi kết nối và giải thích được bốn lớp bảo vệ: mạng, xác thực, phân quyền và quản lý bí mật.

## 15. Chặng 12 — Backup, restore và kế hoạch khôi phục

**Replica set không phải backup.** Nếu ứng dụng xóa nhầm dữ liệu, thao tác xóa có thể được nhân bản sang các secondary. Backup cần đáp ứng mục tiêu khôi phục khi lỗi ứng dụng, xóa nhầm, lỗi vận hành hoặc sự cố hạ tầng.

### 15.1. Hai mục tiêu cần có trước khi chọn công cụ

- **RPO (Recovery Point Objective):** chấp nhận mất tối đa bao nhiêu dữ liệu, tính từ thời điểm sự cố?
- **RTO (Recovery Time Objective):** phải khôi phục dịch vụ trong bao lâu?

Ví dụ, “không mất hơn 15 phút dữ liệu” là yêu cầu RPO; “dịch vụ hoạt động lại trong 2 giờ” là yêu cầu RTO. Một bản dump ban đêm thường không đáp ứng RPO 15 phút nếu không có cơ chế bổ sung.

### 15.2. Các lựa chọn cần hiểu

| Phương án | Ưu điểm | Giới hạn/cần kiểm chứng |
|---|---|---|
| `mongodump` / `mongorestore` | Logical backup, hữu ích cho lab và một số tác vụ chuyển dữ liệu | Cần xét tính nhất quán, thời gian dump/restore và tải lên hệ thống |
| Snapshot storage | Có thể hiệu quả ở mức volume | Cần bảo đảm snapshot nhất quán với trạng thái database và topology |
| Managed backup / PITR | Có thể cung cấp lịch backup và khôi phục tới thời điểm | Phụ thuộc nhà cung cấp, retention, quyền, giới hạn và chi phí |
| Backup lưu ngoài cụm | Tách khỏi điểm lỗi của cluster | Phải mã hóa, giới hạn quyền, kiểm thử restore và theo dõi dung lượng |

Ví dụ logical backup cho **lab** với cơ sở dữ liệu đã tạo:

~~~bash
mongodump --uri="mongodb://127.0.0.1:27017/mongo_learning" \
  --archive=mongo-learning.archive.gz --gzip

# Restore có thể ghi thêm/ghi đè theo namespace và tùy chọn dùng.
# Chỉ thực hiện vào database lab đích đã chuẩn bị.
mongorestore --uri="mongodb://127.0.0.1:27017" \
  --archive=mongo-learning.archive.gz --gzip \
  --nsFrom="mongo_learning.*" --nsTo="mongo_restore_lab.*"
~~~

Các lệnh xuống dòng trên giả định shell tương thích với dấu `\`; trên PowerShell phải viết một dòng hoặc dùng cú pháp nối dòng phù hợp. Việc restore phải thử trên namespace/database đích riêng và xác minh kết quả; đừng dựa vào việc công cụ báo thành công để kết luận dữ liệu khôi phục dùng được.

### 15.3. Một lần khôi phục thành công cần chứng cứ

1. Xác nhận bản backup có timestamp, chính sách retention và quyền truy cập phù hợp.
2. Khôi phục trong môi trường cô lập, dùng cấu hình/phiên bản tương thích.
3. Kiểm tra số lượng document, các collection quan trọng, index và validation.
4. Chạy một số truy vấn nghiệp vụ đại diện, kiểm tra tính nhất quán tham chiếu.
5. Đo thời gian từ bắt đầu tới khi ứng dụng dùng lại được dữ liệu.
6. Ghi nhận khác biệt so với mục tiêu RPO/RTO và cập nhật quy trình.

**Bài thực hành:** Tạo backup của lab, restore vào `mongo_restore_lab`, đọc lại một order và sản phẩm liên quan; đo thời gian. Viết kế hoạch xử lý khi xóa nhầm một collection lúc 14:00 nhưng bản backup gần nhất lúc 00:00.

**Hoàn thành khi:** Phân biệt sao chép với sao lưu, nêu được RPO/RTO và trình diễn restore + xác minh dữ liệu thật.

## 16. Chặng 13 — Quan sát, tối ưu và phản ứng sự cố

Sau khi truy vấn, data model và cluster hoạt động, cần vận hành bằng **dấu hiệu có thể đo**. Độ trễ truy vấn tăng không phải lúc nào cũng do thiếu index; nó có thể xuất phát từ pool hết kết nối, disk chậm, bộ nhớ chịu áp lực, replication lag hoặc request tăng đột biến.

### 16.1. Những tín hiệu tối thiểu cần theo dõi

| Nhóm | Tín hiệu tiêu biểu | Câu hỏi để điều tra |
|---|---|---|
| Truy vấn | p50/p95/p99 latency, slow operations, `explain`, scanned/returned ratio | Truy vấn nào đang đắt và plan có đổi không? |
| Tải | Query/insert/update rate, connections, concurrency | Có thay đổi traffic hoặc pool saturation không? |
| Tài nguyên | CPU, RAM/cache pressure, disk usage, disk I/O latency | Giới hạn nào bị chạm trước? |
| Replica set | Member health, primary changes, replication lag, oplog window | Đọc dữ liệu có bị chậm hoặc failover đang xảy ra không? |
| Sharding | Phân bố dữ liệu/tải, targeted vs scatter-gather queries, hot shards | Shard key hoặc phân phối dữ liệu có gây lệch tải không? |
| Dữ liệu | Tốc độ tăng collection/index, backup age, restore success | Dữ liệu có vượt dự báo và còn khôi phục được không? |
| Bảo mật | Authentication failures, thay đổi role, audit events | Có truy cập bất thường hoặc thay đổi quyền không? |

Trong môi trường lab có thể quan sát các công cụ/lệnh như:

~~~javascript
db.stats()
db.products.stats()
db.serverStatus()
db.products.find({ status: "ACTIVE" }).explain("executionStats")
~~~

Các lệnh cần quyền phù hợp và có thể trả nhiều dữ liệu; trong production ưu tiên dashboard/telemetry có kiểm soát. `explain` phản ánh kế hoạch và thống kê của lần đo, không thay thế chuỗi giám sát dài hạn.

### 16.2. Runbook điều tra một API chậm

1. **Xác định phạm vi:** một endpoint, một collection hay toàn bộ dịch vụ? Bắt đầu từ p95/p99 và lỗi của người dùng.
2. **Đối chiếu thời điểm:** vừa deploy, thêm index, thay schema, tăng traffic, failover hay có backup job nào không?
3. **Chọn truy vấn tiêu biểu:** lấy filter/sort/projection thật đã ẩn thông tin nhạy cảm; chạy `explain` ở môi trường phù hợp.
4. **Kiểm tra kế hoạch:** có scan lớn, blocking sort hoặc stage xử lý nhiều dữ liệu không?
5. **Kiểm tra hạ tầng:** pool, số connection, CPU, cache, storage latency, replication lag và sharding.
6. **Đề xuất thay đổi nhỏ có thể đo:** chỉnh index, query, projection, pagination, schema hoặc cấu hình được phép; kiểm tra ảnh hưởng ghi/disk.
7. **Theo dõi sau thay đổi:** xác minh latency/error rate và khả năng rollback; ghi nguyên nhân vào runbook.

### 16.3. Tình huống vận hành phải tập

**Tình huống A — Query từ 40 ms lên 2 s.** So sánh request/filter mới, `explain` và tỷ lệ scanned/returned; kiểm tra thay đổi số document, index, sort và áp lực I/O. Không thêm index mù quáng.

**Tình huống B — Ghi thất bại khi primary đổi.** Quan sát tình trạng replica set, ứng dụng có retry/timeout đúng không, có thao tác bị ghi thành công nhưng client không nhận xác nhận không. Xác minh idempotency trước khi cho người dùng retry thủ công.

**Tình huống C — Disk gần đầy.** Phân biệt dung lượng dữ liệu, index, log, backup và tăng trưởng bất thường. Lập phương án capacity hoặc retention an toàn; tránh xóa file dữ liệu database trực tiếp.

**Tình huống D — Restore thành công nhưng API vẫn lỗi.** Kiểm tra namespace, version, index, validation, quyền truy cập, connection string và tính đúng đắn nghiệp vụ. Restore chỉ hoàn tất khi ứng dụng có thể dùng dữ liệu đạt mục tiêu.

**Hoàn thành khi:** Có dashboard tối thiểu, biết chọn triệu chứng và đo trước khi sửa, thực hành được ít nhất một runbook trọn vẹn và ghi rõ nguyên nhân/chứng cứ.

## 17. Trình tự học gợi ý theo tuần

Thời gian chỉ mang tính tham khảo; có thể kéo dài mỗi chặng nếu cần. Không nên học sharding chỉ vì đã hết tuần trước mà chưa hiểu document, index và concurrency.

| Giai đoạn | Nội dung ưu tiên | Sản phẩm cần nộp |
|---|---|---|
| Tuần 1 | Nền tảng, BSON, CRUD | Bộ data mẫu + tập lệnh truy vấn có giải thích |
| Tuần 2 | Access pattern, embed/reference, validation | Sơ đồ collection, 5 truy vấn chính và schema rules |
| Tuần 3 | Index, `explain`, aggregation | Báo cáo before/after index, 3 pipeline đúng |
| Tuần 4 | Atomic write, transaction, driver/API | API tạo đơn không bán âm kho, xử lý retry/idempotency |
| Tuần 5 | Replica set, read/write concern, security, sharding căn bản | Sơ đồ topology và bài failover trong lab |
| Tuần 6 | Backup/restore, metrics, capacity, incident response | Restore drill và runbook xử lý một sự cố |

### Quy tắc chuyển chặng

Mỗi chặng nên có **một hiện vật có thể chạy/kiểm tra**: lệnh mongosh, schema, `explain`, test cạnh tranh, sơ đồ topology, bản backup được restore, hoặc dashboard. Không cần thuộc lòng mọi operator; quan trọng hơn là giải thích được lựa chọn và chỉ ra cách kiểm chứng.

## 18. Dự án tích hợp cuối lộ trình

**Đề bài:** Xây dựng backend quản lý đơn hàng với ít nhất `customers`, `products`, `orders` và một tập log/event phù hợp. Nghiệp vụ tối thiểu:

1. Tạo, sửa, tìm kiếm sản phẩm theo status, category, price; có phân trang ổn định.
2. Đặt đơn với nhiều item, lưu snapshot giá tại thời điểm mua; không bán vượt tồn kho khi request đồng thời.
3. Xem lịch sử đơn của một khách theo thời gian, tính tổng doanh thu theo tháng.
4. Bảo vệ dữ liệu bằng validation, unique index và quyền truy cập ứng dụng.
5. Đưa ra index tương ứng với query thực tế, đính kèm phân tích `explain`.
6. Chạy ứng dụng với replica set lab, ghi lại cách client xử lý một lần đổi primary.
7. Backup và restore vào môi trường khác, kiểm chứng dữ liệu và thời gian khôi phục.
8. Ghi dashboard hoặc báo cáo metric, kèm runbook xử lý query chậm hay disk pressure.

### Bộ câu hỏi bảo vệ thiết kế

- Vì sao dòng hàng nhúng vào order, còn catalog product ở collection riêng?
- Nếu giá sản phẩm đổi sau khi thanh toán, order cũ có bị ảnh hưởng không?
- Nếu hai request giảm stock cùng lúc, điều kiện nào ngăn số lượng âm?
- Nếu client timeout sau commit, cơ chế nào ngăn tạo thêm order khi retry?
- Index nào phục vụ lịch sử đơn của khách, và evidence từ `explain` là gì?
- Khi đọc secondary, dữ liệu có thể cũ trong hoàn cảnh nào?
- Nếu xóa nhầm 10.000 order, replica set có giúp phục hồi được không?
- Mục tiêu RPO/RTO của dự án là bao nhiêu và đã kiểm chứng qua restore drill chưa?

### Tiêu chí tự đánh giá

| Năng lực | Mức cơ bản | Mức sẵn sàng tham gia vận hành |
|---|---|---|
| Data model | Tạo document và collection đúng | Biện minh embed/reference bằng query, tăng trưởng và atomicity |
| Query | Viết CRUD/aggregation chính xác | Phân tích được plan/index, phân trang và giới hạn workload |
| Consistency | Biết atomic một document | Xử lý cạnh tranh, idempotency, transaction và retry đúng |
| Topology | Biết primary, secondary, shard | Hiểu trade-off lag, failover, shard key và tác động đến client |
| Safety | Biết auth và backup | Có least privilege, TLS, restore drill và mục tiêu RPO/RTO |
| Operations | Xem metric cơ bản | Điều tra theo bằng chứng, đề xuất thay đổi, xác minh sau sửa |

## 19. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “NoSQL là không có schema” | Schema tồn tại dưới dạng cấu trúc dữ liệu và contract ứng dụng; có thể và nên validation |
| “Nhúng càng nhiều thì càng nhanh” | Chỉ nhúng khi truy cập, kích thước và vòng đời phù hợp; mảng vô hạn gây rủi ro |
| “Có index thì query luôn nhanh” | Index chỉ hữu ích với workload phù hợp; vẫn có thể scan nhiều khóa hoặc phát sinh sort |
| “Transaction giải quyết mọi vấn đề” | Transaction có chi phí và không tự giải quyết idempotency hay side effect ngoài database |
| “Replica set là backup” | Replication sao chép cả thay đổi sai; backup cần độc lập và restore được |
| “Đọc secondary luôn nhanh mà không có đánh đổi” | Có thể đọc dữ liệu cũ, chịu ảnh hưởng lag và consistency requirements |
| “Sharding chỉ là thêm máy” | Shard key, query routing và phân phối tải quyết định hiệu quả mở rộng |
| “Có file backup là an toàn” | Phải có retention, quyền, khôi phục kiểm chứng và RPO/RTO thực tế |
| “Slow query nào cũng sửa bằng index” | Có thể do schema, mạng, pool, tài nguyên, contention hoặc topology |

## 20. Checklist tự học và thứ tự ưu tiên khi thiếu thời gian

Nếu mới bắt đầu, học **document/BSON → CRUD → embed/reference → validation/index/`explain` → concurrency → backup/replica set** trước. Những chủ đề như sharding, index đặc thù và tối ưu cluster nâng cao nên học sâu khi dự án thật có yêu cầu.

- [ ] Tôi phân biệt được document, collection, BSON, `_id` và giới hạn kích thước.
- [ ] Tôi giải thích được lựa chọn embed/reference từ ít nhất ba truy vấn thực.
- [ ] Tôi dùng được CRUD, update operator, query mảng và projection.
- [ ] Tôi có validation, unique index và cách xử lý lỗi dữ liệu.
- [ ] Tôi đọc được `explain`, đo scan và chọn index dựa trên workload.
- [ ] Tôi viết được pipeline có `$match`, `$unwind`, `$group` mà không đếm trùng.
- [ ] Tôi xử lý được tranh chấp tồn kho và request retry mà không tạo dữ liệu sai.
- [ ] Tôi phân biệt atomic write, transaction, read/write concern và read preference.
- [ ] Tôi hiểu replica set/election/lag, phân biệt chúng với sharding.
- [ ] Tôi áp dụng quyền tối thiểu, TLS và quản lý secrets.
- [ ] Tôi đã restore dữ liệu lab thành công và đối chiếu mục tiêu RPO/RTO.
- [ ] Tôi có thể điều tra một truy vấn chậm bằng metrics, query plan và trạng thái tài nguyên.

**Kết quả cuối cùng của việc học MongoDB** không chỉ là biết cú pháp truy vấn, mà là xây dựng một mô hình dữ liệu phục vụ nghiệp vụ, chứng minh được hiệu năng và giữ dịch vụ có thể khôi phục khi xảy ra lỗi. Mỗi quyết định nên đi kèm **truy vấn đại diện, giả định tải, ràng buộc tính đúng đắn và cách kiểm chứng bằng thực nghiệm**.
