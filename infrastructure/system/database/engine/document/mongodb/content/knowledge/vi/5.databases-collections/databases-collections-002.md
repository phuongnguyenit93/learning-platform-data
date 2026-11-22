# Tạo collection ngầm định và tạo tường minh với tùy chọn trong MongoDB

## Mục tiêu bài học

Trong MongoDB, một **collection** là nơi lưu các **document BSON** thuộc cùng một nhóm dữ liệu, chẳng hạn `customers`, `orders`, `products` hoặc `application_logs`. Collection thường được so sánh với table trong cơ sở dữ liệu quan hệ, nhưng document trong cùng collection không bắt buộc có cấu trúc giống hệt nhau nếu người thiết kế không khai báo quy tắc kiểm tra dữ liệu.

MongoDB hỗ trợ hai cách hình thành collection:

1. **Tạo ngầm định (implicit creation):** collection chưa tồn tại sẽ được MongoDB tự tạo khi có một thao tác ghi thích hợp, chẳng hạn chèn document đầu tiên.
2. **Tạo tường minh (explicit creation):** chủ động gọi `db.createCollection()`, kể cả khi chưa có document, để đặt tên và cấu hình các tùy chọn cần thiết ngay từ đầu.

Sau bài học, người học có thể:

- Giải thích thời điểm một database và collection thực sự được tạo trên server.
- Thực hành tạo collection thông qua `insertOne()`, `insertMany()` và qua `db.createCollection()`.
- Phân biệt các tùy chọn quan trọng của `db.createCollection()`: **validator**, **validationLevel**, **validationAction**, **collation**, **capped**, **size**, **max**, **timeseries** và **expireAfterSeconds**.
- Kiểm tra collection đã tồn tại, loại collection và các tùy chọn được lưu.
- Nhận biết rủi ro của việc để ứng dụng tự tạo collection khi hệ thống cần schema validation, collation hoặc cấu hình chuyên biệt.
- Chọn cách tạo collection phù hợp với môi trường học tập, ứng dụng Java/Spring Boot, migration và production.

> **Ý chính:** Nếu chỉ cần một collection thông thường với thiết lập mặc định, lệnh ghi đầu tiên thường đã đủ. Nếu collection phải tuân theo một **hợp đồng dữ liệu hoặc cấu hình riêng**, hãy tạo tường minh trước khi ứng dụng bắt đầu ghi.

---

## 1. Database, collection và document liên hệ với nhau như thế nào?

MongoDB tổ chức dữ liệu theo cấu trúc khái niệm:

~~~text
MongoDB deployment
|
+-- Database: shop_demo
|   |
|   +-- Collection: customers
|   |   +-- Document: { _id: ..., name: "An" }
|   |   +-- Document: { _id: ..., name: "Bình" }
|   |
|   +-- Collection: products
|   |   +-- Document: { _id: ..., sku: "P-001", price: 120000 }
|   |
|   +-- Collection: orders
|       +-- Document: { _id: ..., orderCode: "O-101", items: [...] }
|
+-- Database: audit_demo
    |
    +-- Collection: events
        +-- Document: { _id: ..., action: "LOGIN" }
~~~

Các thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Database | Namespace logic chứa các collection và đối tượng liên quan | `shop_demo` |
| Collection | Nhóm document, có thể kèm validator, default collation và các thuộc tính khác | `orders` |
| Document | Dữ liệu BSON, gồm các cặp field–value và có `_id` duy nhất trong collection | `{ _id: 1, status: "NEW" }` |
| Index | Cấu trúc tăng tốc truy vấn hoặc áp đặt ràng buộc như uniqueness | `{ orderCode: 1 }` với `unique: true` |

Một document có thể có field kiểu string, number, date, array, object lồng nhau, ObjectId hoặc Decimal128. MongoDB không tự suy ra rằng mọi document trong collection phải theo một cấu trúc cố định chỉ vì document đầu tiên có một số field nhất định.

### 1.1. Lệnh `use` chưa tạo database vật lý

Trong **mongosh**:

~~~javascript
use shop_demo
~~~

Lệnh này chuyển ngữ cảnh làm việc sang database `shop_demo`. Nếu database chưa tồn tại, **chỉ chuyển ngữ cảnh chưa làm database xuất hiện như một database có dữ liệu trên server**.

Tương tự, các thao tác chỉ lấy tham chiếu đến collection không tự tạo collection:

~~~javascript
db.getCollection("customers");
db.customers.findOne();
~~~

Chúng có thể trả về một object tham chiếu hoặc kết quả đọc rỗng. Collection chỉ được tạo khi có thao tác tạo/ghi phù hợp.

**Phân biệt quan trọng:**

~~~text
use shop_demo
    -> Chọn ngữ cảnh database.

db.customers.findOne()
    -> Đọc collection; nếu chưa có, không tự tạo.

db.customers.insertOne({ name: "An" })
    -> Có thể tạo database + collection ngầm định,
       rồi lưu document đầu tiên.

db.createCollection("orders")
    -> Tạo collection tường minh, kể cả đang trống.
~~~

### 1.2. Collection mặc định có gì?

Một collection thông thường được tạo ngầm định sử dụng các thiết lập mặc định của server, không kèm validator tự định nghĩa và không có default collation chuyên biệt do ứng dụng đặt. Mỗi document phải có **`_id`**; nếu document insert không cung cấp, driver hoặc MongoDB sẽ tạo giá trị phù hợp.

Không nên nhầm **có `_id`** với **đã có schema validation đầy đủ**. Một collection có thể chứa các document có field khác nhau:

~~~javascript
db.customers.insertMany([
  { name: "An", age: 20 },
  { name: "Bình", email: "binh@example.test" },
  { name: "Chi", interests: ["Java", "MongoDB"] }
]);
~~~

Đây là tính linh hoạt của document database, nhưng cũng đặt trách nhiệm thiết kế dữ liệu lên ứng dụng và người quản trị.

---

## 2. Tạo collection ngầm định

### 2.1. Tạo thông qua `insertOne()`

Giả sử kết nối đến MongoDB đã có quyền ghi vào database thực hành.

~~~javascript
use shop_demo

db.products.insertOne({
  sku: "JAVA-101",
  name: "Sách học Java",
  price: 125000,
  available: true,
  tags: ["book", "java"]
});
~~~

Nếu `products` chưa tồn tại và thao tác ghi được chấp nhận, MongoDB tự tạo collection rồi lưu document.

Kết quả lệnh chèn thường có dạng:

~~~javascript
{
  acknowledged: true,
  insertedId: ObjectId("...")
}
~~~

MongoDB lưu thêm một giá trị `_id` nếu document chưa có:

~~~javascript
db.products.findOne({ sku: "JAVA-101" });
~~~

Kết quả minh họa:

~~~javascript
{
  _id: ObjectId("..."),
  sku: "JAVA-101",
  name: "Sách học Java",
  price: 125000,
  available: true,
  tags: ["book", "java"]
}
~~~

**Dấu hiệu tạo ngầm định** là collection không có trước lệnh insert nhưng xuất hiện sau khi insert thành công.

### 2.2. Tạo thông qua `insertMany()`

~~~javascript
db.categories.insertMany([
  { code: "BOOK", title: "Sách" },
  { code: "COURSE", title: "Khóa học" },
  { code: "DEVICE", title: "Thiết bị" }
]);
~~~

Nếu collection `categories` chưa có, nó được tạo để chứa các document này.

Lưu ý: `insertMany()` không tự áp đặt tính duy nhất cho `code`. Mặc định, tính duy nhất chắc chắn được kiểm soát đối với `_id`. Nếu muốn `code` không trùng, hãy tạo **unique index**:

~~~javascript
db.categories.createIndex(
  { code: 1 },
  { unique: true, name: "uk_categories_code" }
);
~~~

Index là một đối tượng cấu hình riêng, không phải thuộc tính tự suy ra từ field `code`.

### 2.3. Một số thao tác ghi khác cũng có thể tạo collection

Một lệnh **upsert** có thể chèn document vào collection chưa tồn tại:

~~~javascript
db.settings.updateOne(
  { key: "currency" },
  { $setOnInsert: { value: "VND" } },
  { upsert: true }
);
~~~

Nếu không tìm thấy document phù hợp, MongoDB có thể tạo collection `settings` và chèn document mới. Việc tạo index trên namespace chưa tồn tại cũng có thể dẫn đến tạo collection.

**Không nên dựa vào tác dụng phụ này** để thiết kế schema production. Nếu collection cần cấu hình riêng, tạo tường minh trước khi dùng các lệnh ghi, upsert hoặc tạo index.

### 2.4. Kiểm tra collection đã được tạo

~~~javascript
db.getCollectionNames();
~~~

Ví dụ:

~~~javascript
[
  "products",
  "categories",
  "settings"
]
~~~

Kiểm tra riêng một tên:

~~~javascript
db.getCollectionInfos({ name: "products" });
~~~

`db.getCollectionInfos()` trả về thông tin của collection/view phù hợp, trong đó có các trường như `name`, `type` và `options`. Cấu trúc chi tiết có thể khác theo phiên bản MongoDB.

Có thể dùng câu lệnh:

~~~javascript
show collections
~~~

trong mongosh để liệt kê nhanh các collection.

### 2.5. Khi nào tạo ngầm định là đủ?

Cách tạo này thuận tiện cho:

- Bài học CRUD đầu tiên.
- Prototype cần lưu dữ liệu nhanh.
- Test tạm thời với collection bình thường, không yêu cầu cấu hình đặc biệt.
- Script seed dữ liệu vào môi trường lab có thể xóa và dựng lại dễ dàng.

Tuy nhiên, tạo ngầm định có những hạn chế:

- Không có validator doanh nghiệp yêu cầu trừ khi cấu hình sau.
- Không chủ động đặt default collation ngay thời điểm tạo.
- Không tự tạo một **capped collection** hay **time series collection** theo ý định.
- Một lỗi đánh máy trong tên collection có thể làm xuất hiện namespace mới ngoài dự kiến, nếu user có quyền tạo.
- Khi service đầu tiên ghi dữ liệu trước migration, collection có thể được tạo với options mặc định; tác vụ `createCollection()` sau đó có thể báo đã tồn tại.

Vì thế, trong môi trường nhiều service hoặc pipeline triển khai, collection quan trọng nên được quản lý bằng **migration/provisioning có kiểm soát**.

---

## 3. Tạo collection tường minh bằng `db.createCollection()`

### 3.1. Cú pháp cơ bản

Trong mongosh:

~~~javascript
db.createCollection("orders");
~~~

Cú pháp tổng quát:

~~~javascript
db.createCollection("<collectionName>", {
  // Các tùy chọn tạo collection
});
~~~

`db.createCollection()` tạo collection theo tên, ngay cả khi chưa có document nào. Ví dụ:

~~~javascript
use shop_demo

db.createCollection("draft_orders");

db.getCollectionNames();

db.draft_orders.countDocuments({});
~~~

Khi vừa tạo, `draft_orders` tồn tại nhưng `countDocuments({})` trả về **0**.

Nếu collection đã tồn tại, lời gọi tạo trùng tên không được xem như một cách cập nhật options. Server có thể trả lỗi namespace đã tồn tại. Tùy ngữ cảnh ứng dụng, cần quyết định giữa **bỏ qua nếu cấu hình khớp**, **thực hiện migration hợp lệ**, hoặc **báo lỗi cấu hình**.

### 3.2. Vì sao phải tạo tường minh?

Có ba nhóm mục đích:

1. **Tạo cấu trúc trước dữ liệu:** collection phải tồn tại khi một service bắt đầu, dù chưa có sự kiện ghi.
2. **Định nghĩa hợp đồng dữ liệu:** thêm validator, mức kiểm tra và hành vi khi dữ liệu không hợp lệ.
3. **Chọn đặc tính chuyên biệt:** collation mặc định, capped collection, time series hoặc các tính năng hỗ trợ khác theo phiên bản và deployment.

Ví dụ, collection `orders` chỉ chấp nhận đơn hàng có mã, số tiền và trạng thái hợp lệ. Nếu để tự tạo trên insert đầu tiên, các document sai cấu trúc có thể lọt vào trước khi validator được áp dụng.

### 3.3. Bảng tổng quan các tùy chọn thường dùng

| Tùy chọn | Mục đích | Ví dụ |
|---|---|---|
| `validator` | Biểu thức kiểm tra document khi insert/update | `{ $jsonSchema: { ... } }` |
| `validationLevel` | Quy định mức áp dụng validation | `"strict"`, `"moderate"`, `"off"` |
| `validationAction` | Hành vi khi vi phạm validator | `"error"`, `"warn"` |
| `collation` | Quy tắc so sánh/sắp xếp chuỗi mặc định | `{ locale: "vi", strength: 2 }` |
| `capped` | Collection có dung lượng giới hạn, tự loại dữ liệu cũ khi cần | `true` |
| `size` | Dung lượng tối đa dự kiến, đơn vị byte, cho capped | `10485760` |
| `max` | Giới hạn số document cho capped | `10000` |
| `timeseries` | Tạo collection tối ưu cho dữ liệu theo thời gian | `{ timeField: "recordedAt", metaField: "sensor" }` |
| `expireAfterSeconds` | Thiết lập thời gian lưu tự động cho time series theo tính năng hỗ trợ | `2592000` |
| `clusteredIndex` | Chọn clustered collection khi deployment/phiên bản hỗ trợ | Chỉ dùng sau khi kiểm tra yêu cầu riêng |
| `changeStreamPreAndPostImages` | Cấu hình lưu pre/post images cho Change Streams khi được hỗ trợ | `{ enabled: true }` |

**Chú ý:** Không thể kết hợp tùy ý mọi option. Ví dụ, capped collection và time series collection là hai loại có ràng buộc cấu trúc khác nhau. Các tính năng như clustered collection, pre/post images và queryable encryption phụ thuộc phiên bản/tier, vì vậy cần đối chiếu tài liệu chính thức trước khi triển khai.

Các mục sau tập trung vào các nhóm tùy chọn xuất hiện nhiều nhất khi học và thiết kế MongoDB.

---

## 4. Tạo collection với schema validation

### 4.1. Vì sao MongoDB linh hoạt vẫn cần validation?

Khả năng lưu các document không giống nhau là ưu điểm khi dữ liệu phát triển, nhưng có thể khiến ứng dụng nhận dữ liệu không hợp lệ:

~~~javascript
// Dữ liệu mong muốn
{ orderCode: "ORD-001", total: NumberDecimal("250000.00"), status: "NEW" }

// Sai: thiếu mã đơn hàng
{ total: NumberDecimal("250000.00"), status: "NEW" }

// Sai: total là chuỗi thay vì Decimal128
{ orderCode: "ORD-002", total: "hai trăm nghìn", status: "NEW" }

// Sai: trạng thái ngoài danh sách cho phép
{ orderCode: "ORD-003", total: NumberDecimal("200000"), status: "UNKNOWN" }
~~~

Nếu không có validation, MongoDB thông thường vẫn nhận những document có cấu trúc hợp lệ về mặt BSON. Điều đó làm tăng chi phí kiểm tra lỗi ở service, báo cáo và migration.

**Schema validation** cho phép server đánh giá mỗi thao tác ghi theo quy tắc đã định nghĩa.

### 4.2. Tạo collection `orders` có `$jsonSchema`

Ví dụ bên dưới yêu cầu:

- Có `orderCode`, `customerId`, `total`, `status`, `createdAt` và `items`.
- `orderCode` là string không rỗng.
- `total` phải có kiểu BSON **decimal** và không âm.
- `status` chỉ nhận ba giá trị.
- `createdAt` là BSON date.
- `items` là array có ít nhất một phần tử; mỗi phần tử có `sku` và `quantity`.

~~~javascript
use shop_demo

db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "orderCode",
        "customerId",
        "total",
        "status",
        "createdAt",
        "items"
      ],
      properties: {
        orderCode: {
          bsonType: "string",
          minLength: 1,
          description: "Mã đơn hàng bắt buộc"
        },
        customerId: {
          bsonType: "string",
          minLength: 1
        },
        total: {
          bsonType: "decimal",
          minimum: 0,
          description: "Tổng tiền phải là Decimal128 và không âm"
        },
        status: {
          enum: ["NEW", "PAID", "CANCELED"]
        },
        createdAt: {
          bsonType: "date"
        },
        items: {
          bsonType: "array",
          minItems: 1,
          items: {
            bsonType: "object",
            required: ["sku", "quantity"],
            properties: {
              sku: {
                bsonType: "string"
              },
              quantity: {
                bsonType: "int",
                minimum: 1
              }
            }
          }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Đây là **MongoDB JSON Schema**, sử dụng các từ khóa như `bsonType`; nó không đồng nhất hoàn toàn với mọi phiên bản JSON Schema hoặc Java Bean Validation. Khi dùng kiểu decimal và integer, cần gửi đúng kiểu BSON.

Chèn document hợp lệ:

~~~javascript
db.orders.insertOne({
  orderCode: "ORD-1001",
  customerId: "CUS-001",
  total: NumberDecimal("250000.00"),
  status: "NEW",
  createdAt: new Date(),
  items: [
    { sku: "BOOK-01", quantity: NumberInt(2) }
  ]
});
~~~

Lệnh này được chấp nhận nếu không có vi phạm khác (chẳng hạn trùng `_id`).

Thử document không hợp lệ:

~~~javascript
db.orders.insertOne({
  orderCode: "ORD-1002",
  customerId: "CUS-002",
  total: "250000",
  status: "INVALID_STATUS",
  createdAt: new Date(),
  items: []
});
~~~

Trong collection có `validationAction: "error"`, MongoDB từ chối thao tác vi phạm quy tắc, thường báo lỗi **Document failed validation**. Lỗi xuất hiện ở bước ghi, không phải chỉ khi ứng dụng đọc dữ liệu.

### 4.3. Vai trò của `required`, `bsonType` và `enum`

| Quy tắc | Ý nghĩa | Ví dụ sai |
|---|---|---|
| `required` | Field bắt buộc phải có mặt | Thiếu `orderCode` |
| `bsonType` | Kiểm tra kiểu BSON | `total: "250000"` khi yêu cầu `decimal` |
| `enum` | Chỉ chấp nhận giá trị trong tập quy định | `status: "UNKNOWN"` |
| `minLength` | Độ dài string tối thiểu | `orderCode: ""` |
| `minimum` | Giá trị số tối thiểu | `total: NumberDecimal("-1")` |
| `minItems` | Số phần tử array tối thiểu | `items: []` |
| `properties` và `items` | Kiểm tra field lồng nhau hoặc phần tử array | `quantity` sai kiểu |

Đừng nhầm validator với **unique index**. Để ngăn hai đơn có cùng mã, cần thêm:

~~~javascript
db.orders.createIndex(
  { orderCode: 1 },
  { unique: true, name: "uk_orders_orderCode" }
);
~~~

`required` chỉ bảo đảm field tồn tại; nó không bảo đảm giá trị duy nhất trên toàn collection.

### 4.4. `validationLevel`: strict, moderate và off

| Giá trị | Hành vi | Tình huống |
|---|---|---|
| `"strict"` | Áp dụng validation cho mọi insert và update cần kiểm tra | Collection mới, dữ liệu cần đúng schema |
| `"moderate"` | Áp dụng với insert và update các document hiện đang hợp lệ; document cũ vốn không hợp lệ được xử lý theo quy tắc moderate | Triển khai validation dần trên dữ liệu legacy |
| `"off"` | Tắt kiểm tra validator | Trường hợp đặc biệt có kiểm soát; cần cân nhắc kỹ |

`moderate` không đồng nghĩa “chỉ cảnh báo”. Mức này quyết định **document nào được đưa vào kiểm tra**; còn `validationAction` quyết định **điều gì xảy ra khi một document bị kiểm tra và vi phạm**.

`strict` là lựa chọn dễ hiểu cho một collection mới đã có hợp đồng dữ liệu rõ ràng.

### 4.5. `validationAction`: error và warn

| Giá trị | Hành vi |
|---|---|
| `"error"` | Từ chối thao tác ghi không vượt qua validation |
| `"warn"` | Cho phép ghi nhưng phát cảnh báo theo cơ chế log của MongoDB |

Ví dụ, khi chuẩn bị áp dụng schema cho một collection cũ, nhóm có thể dùng `warn` để quan sát các trường hợp vi phạm trước khi chuyển sang `error`.

Tuy nhiên, `warn` **không bảo vệ chất lượng dữ liệu bằng cách chặn ghi**. Một hệ thống đòi hỏi tính đúng đắn của trạng thái đơn hàng phải có kế hoạch xử lý dữ liệu sai và chuyển đổi cấu hình rõ ràng.

Một số phiên bản MongoDB mới có thêm giá trị `validationAction` nâng cao; hãy kiểm tra version cụ thể thay vì sao chép một option không được server hiện tại hỗ trợ.

### 4.6. Validation có tự sửa dữ liệu cũ không?

**Không.** Việc thêm hoặc sửa validator không tự quét sửa lại mọi document đã được lưu. Với collection có dữ liệu lịch sử, có thể cần:

1. Truy vấn các document không phù hợp schema mục tiêu.
2. Lập migration để chuẩn hóa kiểu BSON và field bắt buộc.
3. Kiểm tra xung đột uniqueness hoặc các giá trị enum cũ.
4. Áp dụng validator với `strict/error` khi dữ liệu và ứng dụng đã sẵn sàng.

Một số thao tác đặc quyền có thể sử dụng cơ chế bỏ qua document validation; vì vậy quyền database và quy trình vận hành cũng là một phần của bảo đảm dữ liệu.

---

## 5. Tạo collection với `collation` mặc định

### 5.1. Collation giải quyết vấn đề gì?

**Collation** xác định cách MongoDB so sánh chuỗi cho việc sắp xếp, đối chiếu và một số hoạt động của index. Đặc biệt quan trọng khi ứng dụng có ngôn ngữ, ký tự có dấu hoặc yêu cầu không phân biệt chữ hoa/chữ thường.

Nếu không khai báo collation riêng, collection dùng quy tắc so sánh mặc định dạng binary/simple trong những ngữ cảnh liên quan.

Ví dụ tạo collection `contacts` với collation cho tiếng Việt:

~~~javascript
db.createCollection("contacts", {
  collation: {
    locale: "vi",
    strength: 2
  }
});
~~~

`locale: "vi"` chọn quy tắc locale tiếng Việt theo hệ thống collation hỗ trợ. `strength: 2` thường xét khác biệt dấu nhưng không phân biệt hoa/thường ở cấp so sánh tương ứng. Hành vi cụ thể còn phụ thuộc quy tắc locale và phiên bản ICU.

Chèn dữ liệu:

~~~javascript
db.contacts.insertMany([
  { fullName: "Nguyễn An", city: "Hà Nội" },
  { fullName: "nguyễn bình", city: "Đà Nẵng" },
  { fullName: "Trần Chi", city: "Huế" }
]);
~~~

Sắp xếp:

~~~javascript
db.contacts.find().sort({ fullName: 1 });
~~~

Nếu cần collation khác cho một truy vấn, có thể chỉ định ở truy vấn:

~~~javascript
db.contacts
  .find({ fullName: "Nguyễn An" })
  .collation({ locale: "vi", strength: 3 });
~~~

### 5.2. Collation ảnh hưởng đến index

Index trên collection có thể kế thừa default collation nếu không chỉ định khác. Một truy vấn cần sử dụng index cho so sánh string phải có collation tương thích với index đó trong các trường hợp liên quan.

~~~javascript
db.contacts.createIndex(
  { fullName: 1 },
  { name: "idx_contacts_fullName" }
);
~~~

Khi dùng **unique index** trên field kiểu string, collation có thể ảnh hưởng đến việc hai giá trị được coi là trùng. Ví dụ, một unique index không phân biệt chữ hoa có thể coi `"Lan"` và `"lan"` là cùng khóa trong phạm vi so sánh của index.

**Thiết kế trước khi ghi dữ liệu:** Default collation của collection là thuộc tính tạo ban đầu, không đơn giản thay thế bằng một lời gọi `db.createCollection()` khác sau khi collection đã tồn tại. Nếu cấu hình sai, có thể phải tạo collection mới và di chuyển dữ liệu theo kế hoạch.

---

## 6. Tạo capped collection với `capped`, `size`, `max`

### 6.1. Capped collection là gì?

**Capped collection** là collection có dung lượng giới hạn, giữ document theo thứ tự chèn và có thể tự loại bỏ document cũ khi cần chỗ cho document mới. Nó có hành vi khác collection bình thường.

Ví dụ tạo collection log thực hành tối đa khoảng 10 MiB và tối đa 10.000 document:

~~~javascript
db.createCollection("recent_logs", {
  capped: true,
  size: 10 * 1024 * 1024,
  max: 10000
});
~~~

Ý nghĩa:

- `capped: true` bật kiểu collection có giới hạn dung lượng.
- `size` quy định kích thước bộ nhớ lưu trữ tối đa dự kiến theo byte và là option bắt buộc khi tạo capped collection.
- `max` đặt thêm giới hạn số document, nhưng collection có thể loại document cũ sớm hơn nếu đạt ngưỡng dung lượng.

Khi vượt giới hạn phù hợp, MongoDB loại các document cũ để nhường chỗ cho document mới. Dung lượng thực tế và cơ chế lưu trữ có các chi tiết triển khai riêng; **đừng diễn giải `size` thành một SLA lưu log đủ đúng N giờ**.

### 6.2. Sử dụng capped collection

~~~javascript
db.recent_logs.insertMany([
  { event: "APP_START", createdAt: new Date() },
  { event: "USER_LOGIN", userId: "u-01", createdAt: new Date() },
  { event: "REQUEST_DONE", durationMs: 18, createdAt: new Date() }
]);
~~~

Đọc theo thứ tự tự nhiên:

~~~javascript
db.recent_logs.find().sort({ $natural: 1 });
~~~

Kiểm tra collection có capped hay không:

~~~javascript
db.recent_logs.isCapped();
~~~

### 6.3. Những giới hạn cần cân nhắc

Capped collection có các ràng buộc đáng chú ý:

- Không phù hợp cho dữ liệu nghiệp vụ cần giữ lâu dài.
- Không hỗ trợ xóa tùy ý document như collection thông thường.
- Các thao tác update không được làm document tăng kích thước theo cách vi phạm giới hạn của capped collection.
- Dữ liệu cũ có thể bị loại bỏ tự động; không được xem đây là backup hay archive.
- Capped collection thường gắn với nhu cầu luồng dữ liệu gần đây, trong đó có các tính năng lịch sử của MongoDB như tailable cursor.

**Đừng dùng capped collection để giữ đơn hàng, chứng từ kế toán hoặc dữ liệu phải tồn tại vĩnh viễn.**

Nếu yêu cầu của hệ thống là “giữ log đúng 30 ngày”, một collection thông thường với **TTL index** hoặc time series collection có chính sách thời gian lưu có thể phù hợp hơn. Capped chủ yếu giới hạn **dung lượng/số document**, không đảm bảo tuổi tối thiểu của dữ liệu.

---

## 7. Tạo time series collection với `timeseries`

### 7.1. Time series phù hợp loại dữ liệu nào?

**Time series** phù hợp với chuỗi các phép đo hoặc sự kiện có timestamp, thường có thêm metadata mô tả nguồn:

- Nhiệt độ, độ ẩm hoặc áp suất từ cảm biến.
- CPU, bộ nhớ, độ trễ và các chỉ số vận hành.
- Giá trị đo theo thời gian.
- Telemetry có nhiều bản ghi tại các mốc thời gian khác nhau.

MongoDB cung cấp time series collection để tổ chức và tối ưu cách lưu các phép đo theo thời gian. Đây là kiểu collection cần **tạo tường minh**; chỉ chèn document có field ngày giờ vào collection bình thường **không biến nó thành time series collection**.

### 7.2. Tạo collection `sensor_readings`

~~~javascript
db.createCollection("sensor_readings", {
  timeseries: {
    timeField: "recordedAt",
    metaField: "sensor",
    granularity: "minutes"
  },
  expireAfterSeconds: 30 * 24 * 60 * 60
});
~~~

Các option chính:

| Tùy chọn | Ý nghĩa |
|---|---|
| `timeField` | Tên field chứa thời điểm đo; document phải cung cấp giá trị kiểu BSON Date hợp lệ |
| `metaField` | Field chứa thông tin nhóm/nguồn đo; ví dụ mã thiết bị, vị trí, loại cảm biến |
| `granularity` | Gợi ý mức độ gần nhau của các thời điểm đo: `"seconds"`, `"minutes"`, `"hours"` |
| `expireAfterSeconds` | Thiết lập thời gian lưu dữ liệu theo timestamp; việc xóa diễn ra bất đồng bộ, không chính xác đến từng giây |

Chèn dữ liệu:

~~~javascript
db.sensor_readings.insertMany([
  {
    sensor: { deviceId: "D-01", room: "A1" },
    recordedAt: new Date("2026-11-14T08:00:00Z"),
    temperatureC: 27.2,
    humidityPercent: 65
  },
  {
    sensor: { deviceId: "D-01", room: "A1" },
    recordedAt: new Date("2026-11-14T08:01:00Z"),
    temperatureC: 27.4,
    humidityPercent: 64
  },
  {
    sensor: { deviceId: "D-02", room: "A2" },
    recordedAt: new Date("2026-11-14T08:01:00Z"),
    temperatureC: 26.9,
    humidityPercent: 67
  }
]);
~~~

Truy vấn theo thiết bị và khoảng thời gian:

~~~javascript
db.sensor_readings.find({
  "sensor.deviceId": "D-01",
  recordedAt: {
    $gte: new Date("2026-11-14T08:00:00Z"),
    $lt: new Date("2026-11-14T09:00:00Z")
  }
});
~~~

MongoDB có thể lưu dữ liệu time series theo các **bucket nội bộ** để tiết kiệm dung lượng và tối ưu truy vấn. Ứng dụng vẫn làm việc với collection logic `sensor_readings`; không nên tự sửa các bucket collection nội bộ.

### 7.3. Vì sao `metaField` quan trọng?

Các document đo cùng thiết bị thường chia sẻ metadata. Đặt field đó đúng cách giúp MongoDB nhóm và tổ chức dữ liệu hiệu quả hơn.

Ví dụ:

~~~javascript
sensor: {
  deviceId: "D-01",
  room: "A1",
  sensorType: "THERMOMETER"
}
~~~

Ngược lại, thông số thay đổi theo mỗi phép đo như nhiệt độ nên đặt ở field đo:

~~~javascript
temperatureC: 27.2
~~~

Tránh đưa vào metaField những giá trị thay đổi liên tục theo từng measurement, vì điều đó có thể làm giảm hiệu quả nhóm dữ liệu.

### 7.4. Time series khác collection bình thường ở điểm nào?

| Tiêu chí | Collection thông thường | Time series collection |
|---|---|---|
| Mục đích | Dữ liệu nghiệp vụ tổng quát | Dữ liệu đo có timestamp |
| Tạo ngầm định qua insert | Có | Không tạo thành time series chỉ từ insert |
| Cấu hình thời gian | Do ứng dụng tự chọn schema/index | Khai báo `timeField` khi tạo |
| Tối ưu lưu trữ | Theo cơ chế collection thông thường | Có cách tổ chức bucket nội bộ |
| Cập nhật/xóa dữ liệu | Hỗ trợ CRUD theo quy tắc chung | Có giới hạn riêng theo phiên bản |
| Retention | Có thể dùng TTL index | Có thể dùng `expireAfterSeconds` theo cách hỗ trợ |
| Thiết kế index | Theo workload | Phải xét đặc tính time series và hỗ trợ của phiên bản |

Khả năng sửa document, dùng transaction, tạo index, shard và các giới hạn khác của time series thay đổi theo phiên bản. Không bê nguyên các giả định về collection thông thường sang time series trước khi kiểm tra tài liệu triển khai.

### 7.5. `expireAfterSeconds` không phải bộ hẹn giờ chính xác tuyệt đối

Ví dụ `30 * 24 * 60 * 60` tương ứng 30 ngày theo đơn vị giây. Tuy nhiên, quá trình loại dữ liệu cũ diễn ra theo cơ chế background và bucket, nên một document có thể còn xuất hiện một thời gian sau khi vượt tuổi dự kiến.

Vì vậy:

- Không dùng TTL để bảo đảm xóa đúng tại một giây pháp lý chính xác.
- Kiểm tra logic thời gian và múi giờ của ứng dụng.
- Phân biệt **retention của collection đang hoạt động** với **retention của backup**; document bị xóa khỏi collection không có nghĩa đã bị loại khỏi mọi bản sao lưu.

---

## 8. Thay đổi options sau khi collection đã tồn tại

### 8.1. Không thể dùng lại `createCollection()` để cập nhật

Giả sử `orders` đã được tạo ngầm định:

~~~javascript
db.orders.insertOne({
  orderCode: "OLD-001",
  status: "UNKNOWN"
});
~~~

Sau đó gọi:

~~~javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["orderCode"],
      properties: {
        orderCode: { bsonType: "string" }
      }
    }
  }
});
~~~

**Cách này không “bổ sung” validator vào collection cũ.** Cần một thay đổi cấu hình/migration được MongoDB hỗ trợ, và phải đánh giá dữ liệu đã tồn tại.

### 8.2. `collMod` cho những thuộc tính được hỗ trợ

MongoDB cung cấp lệnh **collMod** để sửa một số thuộc tính của collection hiện có.

Ví dụ chỉ thay đổi mức validation đã được khai báo:

~~~javascript
db.runCommand({
  collMod: "orders",
  validationLevel: "moderate",
  validationAction: "warn"
});
~~~

Lệnh minh họa này thay đổi hành vi kiểm tra validation; nó không tự tạo validator nếu chưa có.

Có thể dùng `collMod` để điều chỉnh validator khi phiên bản và loại collection hỗ trợ, chẳng hạn cập nhật rule kiểm tra dữ liệu sau migration. Nhưng **không phải mọi thuộc tính có trong `createCollection()` đều có thể sửa bằng `collMod`**.

### 8.3. Thuộc tính nên quyết định trước khi có dữ liệu

Một số quyết định ảnh hưởng trực tiếp đến cấu trúc collection:

- **Default collation**: không thể đơn giản đổi trực tiếp như một field bình thường; thường cần tạo namespace mới và migration.
- **Capped collection**: có cơ chế và giới hạn riêng; không nên giả định có thể chuyển qua lại giữa capped và collection thường mà không ảnh hưởng dữ liệu.
- **Time series timeField/metaField**: gắn với tổ chức dữ liệu và có các hạn chế sửa đổi; phải tra đúng phiên bản.
- **Clustered/indexed storage**: phụ thuộc loại collection, phiên bản và yêu cầu lưu trữ.

Quy trình an toàn đối với thay đổi lớn là **tạo collection mới có cấu hình đích → migrate dữ liệu → kiểm tra → chuyển ứng dụng**. Quy trình thật còn cần xử lý ghi phát sinh trong lúc migrate, tính nhất quán, index và rollback.

---

## 9. Kiểm tra loại collection và options đang sử dụng

### 9.1. `getCollectionInfos()`

~~~javascript
db.getCollectionInfos({ name: "orders" });
~~~

Kết quả sẽ chứa metadata của collection phù hợp, ví dụ dạng khái quát:

~~~javascript
[
  {
    name: "orders",
    type: "collection",
    options: {
      validator: {
        $jsonSchema: {
          bsonType: "object",
          // ...
        }
      },
      validationLevel: "strict",
      validationAction: "error"
    }
    // Những trường metadata khác tùy phiên bản
  }
]
~~~

Đây là cách xem MongoDB đang lưu **options thực tế** nào, thay vì chỉ dựa vào file script migration mà nhóm nghĩ đã chạy.

### 9.2. `listCollections` command

Có thể truy vấn trực tiếp qua database command:

~~~javascript
db.runCommand({
  listCollections: 1,
  filter: { name: "sensor_readings" },
  nameOnly: false
});
~~~

Kết quả có thể chứa metadata về loại collection và options time series. Lệnh này đòi hỏi quyền phù hợp với user kết nối.

### 9.3. Kiểm tra index

~~~javascript
db.orders.getIndexes();
~~~

Nếu bạn khai báo `validator` với `orderCode` bắt buộc, điều đó **không tự động tạo unique index** trên `orderCode`. Vì vậy, kiểm tra hai lớp độc lập:

~~~javascript
db.getCollectionInfos({ name: "orders" }); // Options, validator, collation...
db.orders.getIndexes();                    // Index definitions
~~~

### 9.4. Phân biệt collection và view

MongoDB còn có **view**: một namespace chỉ định nguồn và aggregation pipeline, thường không lưu document của chính view như một collection bình thường.

~~~javascript
db.createView(
  "paid_orders_view",
  "orders",
  [
    { $match: { status: "PAID" } }
  ]
);
~~~

Khi liệt kê bằng `getCollectionInfos()`, `type` có thể là `"view"` thay vì `"collection"`. Không nên gộp view vào nhóm capped/time series hoặc xem nó là collection vật lý bình thường.

---

## 10. Thực hành tổng hợp: từ implicit đến explicit

Phần này sử dụng một database lab tên **`collection_lab`**. Các lệnh chỉ nên thực hiện trong database thử nghiệm được phép tạo và xóa dữ liệu.

### Bước 1 — Chọn database và quan sát trạng thái

~~~javascript
use collection_lab

db.getCollectionNames();
~~~

Nếu đây là database mới, danh sách collection thường rỗng.

### Bước 2 — Tạo ngầm định một collection

~~~javascript
db.notes.insertOne({
  title: "Ghi chú đầu tiên",
  body: "Tạo collection bằng thao tác insert",
  createdAt: new Date()
});
~~~

Kiểm tra:

~~~javascript
db.getCollectionNames();
db.notes.find().pretty();
~~~

Collection `notes` đã được tạo nhờ insert thành công.

### Bước 3 — Tạo tường minh một collection rỗng

~~~javascript
db.createCollection("tasks");

db.getCollectionInfos({ name: "tasks" });
db.tasks.countDocuments({});
~~~

Collection `tasks` tồn tại dù chưa có document.

### Bước 4 — Tạo collection với validator đơn giản

~~~javascript
db.createCollection("students", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["studentCode", "fullName"],
      properties: {
        studentCode: {
          bsonType: "string",
          minLength: 1
        },
        fullName: {
          bsonType: "string",
          minLength: 1
        },
        age: {
          bsonType: "int",
          minimum: 0
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Chèn hợp lệ:

~~~javascript
db.students.insertOne({
  studentCode: "ST-001",
  fullName: "Nguyễn An",
  age: NumberInt(20)
});
~~~

Chèn không hợp lệ để quan sát lỗi:

~~~javascript
db.students.insertOne({
  studentCode: "ST-002",
  fullName: "Bình",
  age: "twenty"
});
~~~

MongoDB sẽ từ chối thao tác thứ hai trong cấu hình `error` vì `age` không đúng `bsonType: "int"`.

### Bước 5 — Bổ sung unique index

~~~javascript
db.students.createIndex(
  { studentCode: 1 },
  { unique: true, name: "uk_students_studentCode" }
);
~~~

Thử chèn một document có `studentCode: "ST-001"` khác `_id`. Khi unique index tồn tại, MongoDB từ chối vì khóa bị trùng, độc lập với validator.

### Bước 6 — Tạo capped collection

~~~javascript
db.createCollection("lab_events", {
  capped: true,
  size: 1024 * 1024,
  max: 1000
});

db.lab_events.insertOne({
  type: "LAB_STARTED",
  occurredAt: new Date()
});

db.lab_events.isCapped();
~~~

### Bước 7 — Tạo time series collection

~~~javascript
db.createCollection("room_temperatures", {
  timeseries: {
    timeField: "recordedAt",
    metaField: "room",
    granularity: "minutes"
  },
  expireAfterSeconds: 7 * 24 * 60 * 60
});

db.room_temperatures.insertOne({
  room: { id: "A101", floor: 1 },
  recordedAt: new Date(),
  temperatureC: 27.5
});
~~~

### Bước 8 — Quan sát metadata đã tạo

~~~javascript
db.getCollectionInfos({ name: "notes" });
db.getCollectionInfos({ name: "tasks" });
db.getCollectionInfos({ name: "students" });
db.getCollectionInfos({ name: "lab_events" });
db.getCollectionInfos({ name: "room_temperatures" });
~~~

Hãy ghi lại sự khác biệt giữa `options` của collection thường, collection có validator, capped và time series.

### Bước 9 — Dọn dữ liệu lab khi đã hoàn tất

Nếu muốn xóa **một collection thử nghiệm duy nhất**:

~~~javascript
db.lab_events.drop();
~~~

`drop()` **xóa collection và toàn bộ document/index của nó**. Chỉ chạy khi chắc chắn đó là dữ liệu lab. Không dùng lệnh này trên collection đang chứa dữ liệu cần giữ.

---

## 11. Tích hợp với ứng dụng Java và Spring Boot

### 11.1. Ứng dụng có cần gọi `createCollection()` không?

Trong Java, driver hoặc Spring Data MongoDB có thể ghi vào namespace mới và dẫn đến tạo collection ngầm định. Ví dụ một repository gọi `save()` lần đầu thường không đòi hỏi lập trình viên chạy `createCollection()` riêng nếu collection bình thường được phép tạo.

Tuy nhiên, điều này **không tự cấu hình validator, collation hay đặc tính time series theo yêu cầu doanh nghiệp**. Annotation, mapping hoặc kiểu Java trong ứng dụng không đương nhiên có nghĩa MongoDB đã lưu một collection validator tương ứng.

Vì vậy nên tách trách nhiệm:

~~~text
Provisioning / migration:
  Tạo collection với options mong muốn
  Tạo index cần thiết
  Xác minh version và metadata
            |
            v
Application startup:
  Kết nối và kiểm tra quyền
  Ghi/đọc dữ liệu theo hợp đồng
  Không dựa vào request đầu tiên để cấu hình schema
~~~

Đối với collection không có tùy chọn đặc biệt và dùng trong test/demo, tạo ngầm định là lựa chọn đơn giản. Với hệ thống cần dữ liệu đúng schema, tính nhất quán giữa môi trường dev/staging/prod quan trọng hơn sự tiện lợi của một lần insert.

### 11.2. Ví dụ gọi `createCollection` qua MongoDB Java Driver

Đây là đoạn code minh họa ý tưởng. Trong dự án thực tế, kết nối, vòng đời `MongoClient`, exception handling và việc quản lý secret cần tuân theo ứng dụng.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;

public class CreateCollectionExample {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                    client.getDatabase("collection_lab");

            database.createCollection("java_events");
        }
    }
}
~~~

Kết nối sử dụng biến môi trường `MONGODB_URI`, tránh hardcode credential. Nếu `java_events` đã tồn tại, lời gọi cần xử lý trường hợp namespace trùng; **đừng mặc định chạy lặp vô hạn rồi bỏ qua mọi exception**.

Khi cần schema validation hoặc collection loại đặc biệt, Java Driver cung cấp các tùy chọn tạo collection tương ứng qua API `CreateCollectionOptions` và các lớp cấu hình liên quan. Phần cú pháp cụ thể phụ thuộc phiên bản driver; khi triển khai nên đọc Java Driver documentation và xác nhận tính năng server.

### 11.3. Dự án Spring Boot nên tổ chức việc tạo collection thế nào?

Một cách tổ chức dễ quản trị:

- **Local dev:** script mongosh hoặc migration tạo collection và index trước khi chạy test tích hợp.
- **CI:** tạo môi trường MongoDB mới, chạy migration rồi chạy test, sau đó hủy dữ liệu.
- **Staging:** chạy đúng migration phiên bản production và kiểm tra metadata.
- **Production:** thay đổi schema theo đợt triển khai có kiểm soát, có quyền tạo/sửa collection riêng và kế hoạch rollback.

Nếu chọn tự động tạo collection lúc startup, hãy thiết kế để **không gây race condition khi nhiều instance chạy cùng lúc** và không làm startup fail chỉ vì namespace đã tồn tại với cấu hình mong muốn. Cần xác minh options, không chỉ kiểm tra tên.

---

## 12. Thiết kế migration và quyền truy cập

### 12.1. Rủi ro tạo collection ngoài ý muốn

Ví dụ service dự định ghi vào `customer_profiles` nhưng viết sai:

~~~javascript
db.customer_profiels.insertOne({
  customerId: "C-100",
  enabled: true
});
~~~

Nếu user có quyền tạo collection, MongoDB có thể tạo namespace sai tên **`customer_profiels`** mà không biết ý định ban đầu.

Trong hệ thống nhiều service, lỗi tên namespace dẫn đến:

- Hai collection có dữ liệu cùng mục đích nhưng không tương thích.
- Service này ghi vào collection mới, service khác đọc collection cũ.
- Validator/index mong muốn không tồn tại ở namespace bị gõ sai.
- Backup, monitoring, dashboard hoặc permission policy không bao phủ dữ liệu mới.

Khuyến nghị:

1. Chốt tên collection trong cấu hình hoặc hằng số dùng chung khi phù hợp.
2. Tạo tường minh những collection quan trọng bằng migration.
3. Áp dụng quyền tối thiểu: quyền tạo/sửa collection chỉ cấp cho thành phần cần thiết.
4. Phát hiện namespace lạ bằng metadata hoặc quan sát deployment.
5. Kiểm tra startup đối với collection bắt buộc thay vì để lỗi xuất hiện trong request đầu tiên.

### 12.2. Mẫu migration có thể chạy lại

Một script deployment nên đạt hai tính chất:

- Chạy lần đầu tạo đúng collection và index.
- Chạy lần sau xác nhận đã đúng, không âm thầm bỏ qua cấu hình sai.

Ví dụ khung logic trong mongosh:

~~~javascript
const targetName = "validated_events";

const existing = db.getCollectionInfos({
  name: targetName
});

if (existing.length === 0) {
  db.createCollection(targetName, {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["eventType", "createdAt"],
        properties: {
          eventType: { bsonType: "string" },
          createdAt: { bsonType: "date" }
        }
      }
    },
    validationLevel: "strict",
    validationAction: "error"
  });
} else {
  print("Collection exists: verify its options before proceeding");
}
~~~

Đây là **khung minh họa**, chưa phải migration hoàn chỉnh. Trong deployment nhiều instance, có thể xảy ra tình huống hai tiến trình đều thấy collection chưa tồn tại rồi cùng tạo. Một tiến trình sẽ nhận lỗi đã tồn tại; script phải phân biệt lỗi tranh chấp có thể chấp nhận với lỗi cấu hình thật và **đọc lại metadata để xác minh**.

Đặc biệt, chỉ so tên collection là không đủ. Hai môi trường có thể đều có `validated_events` nhưng một bên có validator, bên kia không.

### 12.3. Quyền database

Để tạo collection, MongoDB user cần có privilege phù hợp trên database hoặc collection. Các role tích hợp như `readWrite` có thể bao gồm quyền tạo collection trong phạm vi được cấp; hệ thống production nên thiết kế quyền theo nhiệm vụ thay vì cấp quyền rộng cho mọi service.

Một mô hình thường dùng:

- **Migration principal:** có quyền tạo/sửa collection và index theo phạm vi cần thiết.
- **Application principal:** chỉ được đọc/ghi các collection ứng dụng cần sử dụng, hạn chế thay đổi cấu trúc nếu có thể.
- **Monitoring principal:** quyền đọc metadata/metrics phù hợp, không cần sửa dữ liệu.

Khi chuyển từ tạo ngầm định sang tạo tường minh, cần xác nhận cả **quyền của migration** và **quyền của ứng dụng**.

### 12.4. Tên collection và quy ước

Đặt tên rõ mục đích, dễ tìm kiếm và thống nhất:

~~~text
products
customers
orders
payment_attempts
audit_events
sensor_readings
~~~

Tránh thay đổi chữ hoa/chữ thường tùy tiện, khoảng trắng, tên mơ hồ hoặc tên dễ lẫn với collection hệ thống. MongoDB có những quy tắc và tên namespace đặc biệt; hãy kiểm tra hạn chế đặt tên của phiên bản đang dùng trước khi chuẩn hóa schema.

---

## 13. Chọn phương thức theo nhu cầu

| Bối cảnh | Cách tạo phù hợp | Lý do |
|---|---|---|
| Học lệnh insert lần đầu | **Ngầm định** qua `insertOne()` | Ít bước, tập trung vào document |
| Prototype một collection đơn giản | **Ngầm định** | Không cần options đặc biệt |
| Collection rỗng cần hiện diện khi ứng dụng khởi động | **Tường minh** | Tạo trước cả khi chưa có dữ liệu |
| Đơn hàng cần ràng buộc kiểu và field | **Tường minh + validator** | Chặn document không đạt hợp đồng |
| Danh bạ cần so sánh tên theo locale | **Tường minh + collation** | Quy định hành vi so sánh string |
| Log luân phiên giới hạn khoảng dung lượng | **Tường minh + capped** | Loại dữ liệu cũ theo giới hạn dung lượng/số document |
| Telemetry cảm biến theo thời gian | **Tường minh + timeseries** | Tối ưu dạng dữ liệu theo timestamp |
| Production nhiều service và yêu cầu nhất quán | **Tường minh qua migration** | Cấu hình được kiểm soát, kiểm tra, lặp lại |
| Bài test tạm thời không có schema riêng | **Ngầm định hoặc migration đơn giản** | Tạo nhanh, dễ dọn |
| Collection cũ cần bổ sung validation | **Migration/collMod khi hỗ trợ** | Không gọi lại `createCollection()` để sửa |

Lựa chọn giữa hai cách không phải về độ “hiện đại” của cú pháp. Nó phụ thuộc vào **mức kiểm soát cấu trúc cần có trước thao tác ghi đầu tiên**.

---

## 14. Những hiểu lầm thường gặp

### “Chạy `use databaseName` là database đã được tạo”

Không hoàn toàn. `use` chỉ đổi database context trong mongosh. Database và collection được materialize khi có thao tác thích hợp tạo đối tượng hoặc ghi dữ liệu.

### “`db.collection.find()` tự tạo collection nếu chưa tồn tại”

Không. Đọc một namespace không có dữ liệu không đồng nghĩa tạo namespace đó.

### “`insertOne()` tạo collection với schema từ document đầu tiên”

Không. MongoDB không tự tạo validator từ kiểu và field của document đầu. Collection mặc định vẫn linh hoạt nếu không có schema validation tự cấu hình.

### “`db.createCollection()` chỉ dùng khi cần validator”

Không. Bạn cũng có thể dùng để tạo collection rỗng, khai báo collation, capped collection hoặc time series.

### “Collection đã có thì gọi `createCollection()` với options mới để sửa”

Không. Đây là thao tác tạo, không phải cập nhật cấu hình tùy ý. Một số thay đổi dùng `collMod`; một số khác đòi hỏi collection mới và migration.

### “Có validator thì không cần unique index”

Sai. `$jsonSchema` kiểm tra cấu trúc và giá trị document theo quy tắc của nó; uniqueness xuyên các document thường do unique index bảo đảm.

### “`validationAction: "warn"` sẽ ngăn dữ liệu sai được lưu”

Sai. `warn` ghi nhận vi phạm theo cơ chế cảnh báo nhưng vẫn cho phép thao tác. Muốn chặn ghi không hợp lệ, sử dụng hành vi `error` khi thích hợp.

### “Capped collection đảm bảo giữ log ít nhất 30 ngày”

Sai. Nó bị giới hạn bởi dung lượng và/hoặc số document. Tốc độ ghi tăng có thể làm document cũ bị loại sớm hơn dự tính.

### “Chèn document có timestamp thì collection tự trở thành time series”

Sai. Time series collection phải được tạo với cấu hình `timeseries` phù hợp.

### “TTL loại document chính xác ngay khi đến hạn”

Không. Cơ chế expiration chạy bất đồng bộ và có các chi tiết riêng, đặc biệt đối với time series buckets.

### “Annotation Java quyết định toàn bộ options trong MongoDB”

Không nhất thiết. Mapping ở lớp ứng dụng và metadata thực tế trên database là hai lớp khác nhau; cần kiểm tra collection options trên server.

### “Có collection là đã có index tối ưu cho truy vấn”

Không. MongoDB có index phục vụ `_id` theo quy định của loại collection, nhưng các field truy vấn như `customerId`, `status`, `createdAt` thường cần index được thiết kế dựa trên workload.

---

## 15. Bài tập tự thực hành

### Bài tập 1 — Phân biệt thao tác tạo

Trong database mới `lesson_creation`, thực hiện tuần tự:

~~~javascript
use lesson_creation
db.getCollectionNames()

db.books.findOne()
db.getCollectionNames()

db.books.insertOne({
  isbn: "978-000001",
  title: "MongoDB Basics"
})
db.getCollectionNames()
~~~

Giải thích ở bước nào collection `books` được tạo, và vì sao thao tác đọc trước đó không tạo collection.

### Bài tập 2 — Schema validation cho khóa học

Tạo collection `courses` bằng `db.createCollection()` với các điều kiện:

- `courseCode` và `title` bắt buộc, kiểu string không rỗng.
- `durationHours` kiểu int, lớn hơn hoặc bằng 1.
- `level` chỉ được `BEGINNER`, `INTERMEDIATE`, `ADVANCED`.
- `createdAt` là BSON date.

Chèn hai document: một document hợp lệ và một document có `durationHours` kiểu string. Mô tả phản hồi khi `validationAction` lần lượt là `error` và `warn`.

Sau đó tạo unique index trên `courseCode` và thử insert hai khóa học có cùng mã.

### Bài tập 3 — So sánh collation

Tạo collection `people` với collation locale `vi`, `strength: 2`. Chèn các tên có khác biệt chữ hoa/chữ thường và dấu. So sánh kết quả:

~~~javascript
db.people.find().sort({ fullName: 1 });

db.people
  .find()
  .collation({ locale: "simple" })
  .sort({ fullName: 1 });
~~~

Giải thích vì sao cùng dữ liệu có thể được sắp xếp khác nhau khi collation khác.

### Bài tập 4 — Chọn capped hay time series

Với hai bài toán sau, hãy chọn một kiểu collection và giải thích:

1. Buffer hiển thị 500 sự kiện ứng dụng gần đây, chấp nhận tự loại sự kiện cũ, không cần lưu lịch sử dài hạn.
2. Lưu nhiệt độ mỗi phút từ 1.000 cảm biến, thường truy vấn theo thiết bị và khoảng ngày, tự hết hạn dữ liệu sau 90 ngày.

Hãy chỉ rõ option `capped/size/max` hoặc `timeseries/timeField/metaField/granularity/expireAfterSeconds` thích hợp.

### Bài tập 5 — Phát hiện cấu hình lệch môi trường

Dev có collection `orders` với validator; staging cũng có collection `orders` nhưng được tạo ngầm định, không có validator.

Hãy trình bày:

- Cách dùng `getCollectionInfos()` để kiểm tra khác biệt.
- Vì sao chỉ chạy `db.getCollectionNames()` không phát hiện lỗi này.
- Vì sao không nên xóa collection staging đang có dữ liệu để sửa nhanh.
- Quy trình migration an toàn trước khi áp dụng `validationAction: "error"`.

---

## 16. Câu hỏi ôn tập

1. `use` trong mongosh có ngay lập tức tạo database trên server không?
2. Thao tác nào tạo collection ngầm định phổ biến nhất?
3. Vì sao `findOne()` không phải thao tác tạo collection?
4. Khi nào nên dùng `db.createCollection("name")` không có options?
5. `validator` và `unique index` khác nhau ra sao?
6. `validationLevel: "moderate"` và `validationAction: "warn"` có cùng ý nghĩa không?
7. Collection default collation ảnh hưởng thế nào đến so sánh chuỗi và index?
8. Trong capped collection, `size` và `max` kiểm soát những giới hạn nào?
9. Vì sao dữ liệu sensor nên xem xét time series collection?
10. Có thể thay đổi mọi option tạo collection bằng cách gọi lại `createCollection()` không?
11. Làm sao kiểm chứng một collection thật sự có validator như bản thiết kế?
12. Vì sao môi trường production nên quản lý nhiều collection bằng migration có kiểm soát?

## 17. Kết luận

**Tạo collection ngầm định** đơn giản và hữu ích khi bắt đầu học MongoDB: một lệnh `insertOne()` có thể tạo collection bình thường rồi lưu document ngay. Tuy nhiên, cách này không tự định nghĩa validator, collation hay cấu trúc dành riêng cho capped/time series.

**Tạo collection tường minh** bằng `db.createCollection()` cho phép chuẩn bị namespace trước khi có dữ liệu và khai báo các thuộc tính ảnh hưởng đến chất lượng dữ liệu, so sánh chuỗi và cách lưu trữ. Với ứng dụng nghiệp vụ cần vận hành ổn định, hãy kết hợp việc tạo tường minh với **index, quyền truy cập, migration và xác minh metadata**.

Nguyên tắc thực hành dễ áp dụng:

- **Collection thường và thử nghiệm nhanh:** có thể tạo ngầm định.
- **Collection có hợp đồng dữ liệu hoặc đặc tính riêng:** tạo tường minh trước ghi đầu tiên.
- **Môi trường production:** quản lý định nghĩa collection bằng quy trình migration có thể kiểm tra và triển khai lặp lại, tránh tạo namespace ngoài ý muốn.

## Tài liệu tham khảo chính thức

- [MongoDB Manual — Databases and Collections](https://www.mongodb.com/docs/manual/core/databases-and-collections/)
- [MongoDB Manual — db.createCollection()](https://www.mongodb.com/docs/manual/reference/method/db.createCollection/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Specify JSON Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/)
- [MongoDB Manual — Collation](https://www.mongodb.com/docs/manual/reference/collation/)
- [MongoDB Manual — Capped Collections](https://www.mongodb.com/docs/manual/core/capped-collections/)
- [MongoDB Manual — Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/)
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Manual — collMod Command](https://www.mongodb.com/docs/manual/reference/command/collMod/)
- [MongoDB Java Sync Driver — Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
