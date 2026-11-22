# Định danh tổng hợp và yêu cầu về cấu trúc, thứ tự trường trong MongoDB

## 1. Định danh tổng hợp là gì?

Trong MongoDB, mỗi document có trường `_id` để định danh. Giá trị thường gặp là `ObjectId`, nhưng `_id` cũng có thể là **một document lồng nhau** chứa nhiều thành phần định danh. Cách này thường được gọi là **định danh tổng hợp** (*composite identifier* hoặc *compound identity*). Ví dụ trong một ứng dụng đa tenant, mã đơn hàng chỉ duy nhất **trong phạm vi từng tenant**, nên định danh có thể gồm cả mã tenant và mã đơn:

```javascript
{
  _id: {
    tenantId: "acme",
    orderNo: "ORD-001"
  },
  status: "CREATED",
  total: 125000
}
```

Hai thành phần `tenantId` và `orderNo` hợp thành một khóa định danh. Đơn hàng `ORD-001` của tenant `acme` khác đơn hàng `ORD-001` của tenant `beta`. MongoDB bảo đảm tính duy nhất của giá trị `_id` theo phạm vi collection và điều kiện triển khai tương ứng.

Đối với **Spring Data MongoDB**, bài toán không chỉ là mô hình hóa một lớp Java gồm hai field. Cần quyết định **hình dạng BSON được ghi vào `_id`**, **thứ tự các field trong document khóa**, cách query dùng `MongoTemplate` và repository, cách đặt index, và cách giữ khóa ổn định qua các phiên bản ứng dụng.

Mục tiêu của bài thuộc chương **Định danh và trạng thái**:

- Biết khi nào nên dùng `_id` dạng document và khi nào chỉ cần `ObjectId` cùng unique index nhiều trường.
- Hiểu vì sao **cấu trúc, tên field, kiểu BSON và thứ tự field** ảnh hưởng phép so sánh khóa tổng hợp.
- Thiết kế và ánh xạ khóa sang lớp Java, query an toàn bằng `MongoTemplate`/repository.
- Xác định hệ quả cho index, upsert, transaction, migration và việc thay đổi định danh.
- Kiểm thử để tránh lỗi không tìm được dữ liệu, trùng logic hoặc ghi sai document.

## 2. Chọn cách định danh phù hợp

MongoDB có nhiều cách giải quyết yêu cầu “mỗi tenant có một mã đơn hàng duy nhất”:

| Thiết kế | Document minh họa | Ràng buộc duy nhất | Đặc điểm |
|---|---|---|---|
| `_id` tổng hợp | `{ _id: { tenantId: "acme", orderNo: "ORD-001" } }` | Trên giá trị `_id` đầy đủ | Trực tiếp dùng khóa nghiệp vụ làm định danh; phụ thuộc cấu trúc BSON |
| `ObjectId` + unique compound index | `{ _id: ObjectId(...), tenantId: "acme", orderNo: "ORD-001" }` | Index `{ tenantId: 1, orderNo: 1 }` với `unique: true` | Dễ đổi mã nghiệp vụ hơn; có khóa kỹ thuật riêng |
| Chuỗi tổng hợp | `{ _id: "acme:ORD-001" }` | Trên chuỗi `_id` | Đơn giản khi tìm theo khóa toàn phần, nhưng cần chuẩn hóa/escape separator và mất cấu trúc field |

Ví dụ tạo unique index nếu chọn khóa kỹ thuật riêng:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderNo: 1 },
  { unique: true, name: "uq_tenant_order" }
);
```

Điều kiện `unique: true` trên **compound index của các field thường** không có nghĩa `_id` được biến thành khóa tổng hợp. Hai thiết kế có vòng đời, truy vấn và khả năng thay đổi mã nghiệp vụ khác nhau.

**Nên cân nhắc `_id` tổng hợp khi:** bộ thành phần định danh đã ổn định, luôn có mặt, có kích thước nhỏ, được chuẩn hóa và ứng dụng thường truy vấn đúng toàn bộ khóa. **Nên cân nhắc khóa kỹ thuật + unique index khi:** mã nghiệp vụ có thể đổi, cần liên kết tham chiếu đơn giản, hoặc có nhiều cách tra cứu và tích hợp bên ngoài.

Không nhồi quá nhiều thông tin vào `_id` chỉ để tránh tạo index. Khóa quá dài làm tăng kích thước document và chỉ mục, đồng thời tăng độ phức tạp của mọi đường dẫn truyền/nhận định danh.

## 3. Cấu trúc vật lý của khóa trong BSON

Chạy trong `mongosh` trên database thử nghiệm:

```javascript
db.orders.insertMany([
  {
    _id: { tenantId: "acme", orderNo: "ORD-001" },
    status: "CREATED"
  },
  {
    _id: { tenantId: "acme", orderNo: "ORD-002" },
    status: "PAID"
  },
  {
    _id: { tenantId: "beta", orderNo: "ORD-001" },
    status: "CREATED"
  }
]);

db.orders.find({}, { _id: 1, status: 1 });
```

Đây là ba document có khóa khác nhau. `_id` không đơn thuần là một “tuple trừu tượng”; nó là **một BSON document có tên field, kiểu giá trị và thứ tự field cụ thể**:

```text
_id (BSON document)
├── tenantId (BSON string): "acme"
└── orderNo  (BSON string): "ORD-001"
```

Với khóa `{ tenantId: "acme", orderNo: "ORD-001" }`, các biến thể sau **không có cùng cấu trúc BSON**:

```javascript
{ orderNo: "ORD-001", tenantId: "acme" } // Đảo thứ tự
{ tenantId: "acme", orderNo: 1 }         // Đổi kiểu string thành number
{ tenantId: "acme", orderNo: "ORD-001", region: "VN" } // Thêm field
{ tenantId: "acme" }                     // Thiếu thành phần khóa
```

Vì MongoDB so sánh document lồng nhau theo cả giá trị lẫn thứ tự cặp key–value trong phép so khớp equality, **không được coi hai object có cùng tập thuộc tính nhưng khác thứ tự là biểu diễn khóa tương đương để tra cứu trực tiếp**.

### 3.1. Truy vấn equality trên toàn bộ `_id`

```javascript
// Tìm thấy ORD-001 của acme
db.orders.findOne({
  _id: { tenantId: "acme", orderNo: "ORD-001" }
});

// Không khớp với _id đã lưu nếu thứ tự field bị đảo
db.orders.findOne({
  _id: { orderNo: "ORD-001", tenantId: "acme" }
});

// Không khớp vì thiếu thành phần orderNo
db.orders.findOne({
  _id: { tenantId: "acme" }
});
```

Khi so sánh bằng một **embedded document**, MongoDB yêu cầu cấu trúc document tương ứng, trong đó **thứ tự field có ý nghĩa**. Điều này rất quan trọng với `findById(...)`, `deleteById(...)`, `replaceOne(...)` hoặc thao tác upsert nếu ứng dụng dựng khóa BSON theo các cách khác nhau.

### 3.2. Truy vấn từng thành phần bằng dot notation

Nếu viết điều kiện cho từng field con của `_id`, thứ tự các điều kiện trong query **không làm thay đổi ý nghĩa** như equality với toàn bộ document:

```javascript
db.orders.findOne({
  "_id.tenantId": "acme",
  "_id.orderNo": "ORD-001"
});

db.orders.findOne({
  "_id.orderNo": "ORD-001",
  "_id.tenantId": "acme"
});

db.orders.find({
  "_id.tenantId": "acme"
});
```

Hai truy vấn `findOne` đầu tiên cùng mô tả điều kiện trên từng field con và cùng tìm document trong dữ liệu mẫu. Truy vấn cuối lấy tất cả đơn thuộc tenant `acme`. Dot notation phù hợp để tìm kiếm theo một phần khóa, nhưng phải thiết kế **index riêng** nếu workload đòi hỏi hiệu năng cao.

Không suy ra rằng các điều kiện tìm theo `_id.tenantId` và `_id.orderNo` tự động được tối ưu tương đương tìm bằng `_id` đầy đủ. Index trên toàn bộ `_id` và compound index trên các **đường dẫn thành phần** là hai khái niệm khác nhau.

### 3.3. Chuẩn hóa tên, kiểu và thứ tự trường

Hãy xác định hợp đồng khóa một cách tường minh:

| Thuộc tính | Hợp đồng ví dụ |
|---|---|
| Tên và thứ tự | `tenantId` trước, `orderNo` sau |
| Kiểu BSON | Cả hai là `string`, không có `null` |
| Giá trị | Chuẩn hóa khoảng trắng/case theo quy tắc nghiệp vụ trước khi ghi |
| Field bắt buộc | Không thiếu field nào |
| Field phụ | Không tự thêm `region`, `_class` hoặc metadata khác vào subdocument `_id` |
| Ổn định | Không đổi tên, kiểu, thứ tự hoặc ý nghĩa trường trong quá trình nâng cấp nếu chưa migration |

**Phân biệt:** MongoDB quan tâm đến **thứ tự field bên trong BSON document**, không phải thứ tự các property trong một JSON API bên ngoài. Trình ánh xạ dữ liệu và serializer có thể tạo thứ tự field khác với thứ tự hiển thị khi lập trình; vì vậy hãy kiểm tra document thực tế đã lưu.

Một hệ thống sinh khóa từ nhiều ngôn ngữ (Java, Node.js, Python...) càng cần thống nhất cách đóng gói và chuẩn hóa. Không tự suy rằng hai map có cùng cặp key/value sẽ được mọi serializer ghi thành cùng chuỗi byte hoặc cùng thứ tự BSON.

## 4. Ánh xạ định danh tổng hợp bằng Spring Data MongoDB

### 4.1. Mô hình bằng một kiểu khóa rõ ràng

Với Java 17+ và phiên bản Spring Data MongoDB hỗ trợ record mapping, có thể biểu diễn khóa dưới dạng record:

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.repository.MongoRepository;

record OrderKey(String tenantId, String orderNo) {
    OrderKey {
        if (tenantId == null || tenantId.isBlank()
                || orderNo == null || orderNo.isBlank()) {
            throw new IllegalArgumentException("Composite key is incomplete");
        }
    }
}

@Document(collection = "orders")
record PurchaseOrder(
    @Id OrderKey id,
    String status,
    Instant createdAt
) {}

interface PurchaseOrderRepository
        extends MongoRepository<PurchaseOrder, OrderKey> {}
```

Trong mô hình này, `PurchaseOrder.id` là một đối tượng `OrderKey`. Với mapping mặc định phù hợp, Spring Data chuyển đối tượng khóa thành `_id` dạng BSON document. Tên và thứ tự trường sau khi chuyển đổi phải khớp **hợp đồng BSON đã thống nhất**; kiểm tra thực tế khi có mapping tùy biến, `@Field`, converter, alias hoặc khi nâng cấp thư viện.

Không cần khai báo `@Id` trên từng thành phần `tenantId`, `orderNo`. Chỉ có **một thuộc tính Java đại diện cho trường MongoDB `_id`**. Không giả định hai field Java cùng gắn `@Id` sẽ tự động kết hợp thành compound identifier.

Tạo và truy vấn bằng repository:

```java
OrderKey key = new OrderKey("acme", "ORD-003");
PurchaseOrder order = new PurchaseOrder(
    key, "CREATED", Instant.now());

repository.insert(order);

PurchaseOrder loaded = repository.findById(
    new OrderKey("acme", "ORD-003"))
    .orElseThrow();
```

Đoạn code trên giả định biến `repository` đã được inject vào service. Repository hỗ trợ các phương thức như `findById`, `existsById` và `deleteById` theo kiểu ID được khai báo, nhưng độ đúng của phép so khớp phụ thuộc **biểu diễn BSON** mà converter tạo ra.

### 4.2. Kiểm tra raw BSON thay vì suy từ Java object

Khi sử dụng `MongoTemplate`, có thể đọc document dưới dạng `org.bson.Document` để xác minh cấu trúc:

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

Document raw = mongoTemplate.getCollection("orders")
    .find(new Document("_id", new Document("tenantId", "acme")
        .append("orderNo", "ORD-003")))
    .first();

if (raw != null) {
    Document bsonId = raw.get("_id", Document.class);
    System.out.println(bsonId.toJson());
    System.out.println(bsonId.keySet()); // Kiểm tra thứ tự thực tế
}
```

`getCollection(...)` trả collection từ driver đồng bộ; ví dụ raw này hữu ích cho việc kiểm chứng cấu trúc BSON khi debug. Trong ứng dụng thông thường, dùng `MongoTemplate`/repository đã khai báo kiểu domain để tận dụng mapping Spring.

**Cẩn thận với `_class`:** Spring Data có thể ghi type hints trong một số tình huống mapping. Nếu type hint hoặc converter thay đổi cấu trúc subdocument khóa, phép so khớp chính xác có thể bị ảnh hưởng. Đừng xóa toàn cục thông tin kiểu hoặc tùy biến converter chỉ để khớp một truy vấn; trước tiên kiểm tra raw document và chuẩn hóa hợp đồng ánh xạ trên mọi đường ghi/đọc.

### 4.3. Truy vấn bằng MongoTemplate và Criteria

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// Tìm theo ID đối tượng, chuyển qua mapping của Spring Data.
PurchaseOrder order = mongoTemplate.findById(
    new OrderKey("acme", "ORD-003"), PurchaseOrder.class);

// Tìm theo thành phần khóa; không phụ thuộc thứ tự các field
// trong equality của toàn bộ _id.
Query byParts = Query.query(
    Criteria.where("_id.tenantId").is("acme")
        .and("_id.orderNo").is("ORD-003"));

PurchaseOrder found = mongoTemplate.findOne(
    byParts, PurchaseOrder.class);

// Liệt kê tất cả order theo tenant:
Query byTenant = Query.query(
    Criteria.where("_id.tenantId").is("acme"));
var orders = mongoTemplate.find(
    byTenant, PurchaseOrder.class);
```

Nếu mapping dùng tên BSON khác tên thuộc tính Java (ví dụ `tenantId` thành `tenant`), hãy kiểm tra đường dẫn mà `QueryMapper` ánh xạ và query thực tế gửi đến MongoDB. Không trộn tên property Java và tên field BSON khi chưa biết mapping áp dụng ở lớp nào.

## 5. Vòng đời khóa: bất biến, insert, update, upsert

### 5.1. `_id` là định danh bất biến

MongoDB không cho cập nhật trực tiếp `_id` của document đã có. Điều này bao gồm cả thay một thành phần trong subdocument `_id`:

```javascript
// Hợp lệ: đổi thuộc tính KHÔNG thuộc _id
db.orders.updateOne(
  { _id: { tenantId: "acme", orderNo: "ORD-001" } },
  { $set: { status: "PAID" } }
);

// Không hợp lệ: cố thay thành phần của _id
db.orders.updateOne(
  { "_id.tenantId": "acme", "_id.orderNo": "ORD-001" },
  { $set: { "_id.orderNo": "ORD-900" } }
);
```

Nếu nghiệp vụ cho phép sửa mã đơn hàng hoặc chuyển đơn sang tenant khác, `_id` tổng hợp có thể là lựa chọn bất tiện. Hãy cân nhắc `ObjectId` làm khóa kỹ thuật và unique index cho khóa nghiệp vụ, hoặc thiết kế quy trình tạo document mới, cập nhật tham chiếu rồi loại bỏ document cũ một cách có kiểm soát. Việc sao chép và xóa không mặc nhiên là thao tác nguyên tử; nếu cần tính nhất quán giữa nhiều document, phải xét transaction và topology hỗ trợ.

### 5.2. Insert và xử lý trùng khóa

```javascript
db.orders.insertOne({
  _id: { tenantId: "acme", orderNo: "ORD-010" },
  status: "CREATED"
});

// Cùng _id đầy đủ, cùng cấu trúc: bị từ chối vì trùng khóa.
db.orders.insertOne({
  _id: { tenantId: "acme", orderNo: "ORD-010" },
  status: "CREATED"
});
```

Lỗi duplicate key (`E11000`) là tín hiệu quan trọng khi nhiều request cùng tạo một đơn hàng. Đừng tự thực hiện “tìm thấy chưa, sau đó insert” rồi cho rằng hai thao tác tách rời bảo đảm duy nhất khi chạy đồng thời. Hãy dựa trên ràng buộc unique ở database cùng cơ chế xử lý retry/idempotency có thiết kế.

Với `MongoRepository`, `insert(...)` thể hiện ý định tạo document mới; `save(...)` có thể cập nhật/thay thế document khi ID đã có. Nếu sửa object rồi gọi `save(...)`, cần xét rủi ro ghi đè trạng thái của request khác. Cho thay đổi một trường, thường phù hợp hơn với atomic update `$set` hoặc optimistic locking bằng `@Version` khi đã cấu hình, thử nghiệm đúng.

### 5.3. Upsert phải dùng khóa chính tắc

```javascript
const id = { tenantId: "acme", orderNo: "ORD-020" };

db.orders.updateOne(
  { _id: id },
  {
    $set: { status: "PAID" },
    $setOnInsert: { createdAt: new Date() }
  },
  { upsert: true }
);
```

Ở ví dụ này, `_id` luôn được xây dựng theo một **thứ tự và kiểu BSON cố định**. Không tạo biểu diễn khóa khác nhau theo thứ tự tham số đến từ JSON, thứ tự lặp của map hoặc thứ tự ghép động. Khi upsert đồng thời, vẫn cần kiểm tra kết quả, xử lý duplicate key theo thiết kế, và tránh các phép cập nhật có thể ghi đè trái ý nghiệp vụ.

## 6. Định danh tổng hợp liên quan thế nào đến index?

### 6.1. Unique index trên `_id` là index cho giá trị khóa đầy đủ

MongoDB tạo index mặc định tên `_id_` trên trường `_id`. Với khóa:

```javascript
_id: { tenantId: "acme", orderNo: "ORD-001" }
```

index `_id_` phục vụ truy vấn equality bằng **giá trị `_id` đầy đủ**. Đừng suy rằng index này tương đương một compound index trên hai đường dẫn:

```javascript
{ "_id.tenantId": 1, "_id.orderNo": 1 }
```

Hai index có **key pattern khác nhau**. Truy vấn theo một phần khóa, chẳng hạn lấy toàn bộ đơn hàng của tenant, cần được phân tích kế hoạch thực thi và có thể cần index riêng.

### 6.2. Index cho truy vấn theo thành phần khóa

Giả sử workload thường hỏi: “Các đơn gần nhất của tenant `acme` là gì?”. Định nghĩa field `createdAt` ngoài `_id`, rồi tạo index:

```javascript
db.orders.createIndex(
  { "_id.tenantId": 1, createdAt: -1 },
  { name: "ix_tenant_recent_orders" }
);

db.orders.find({ "_id.tenantId": "acme" })
  .sort({ createdAt: -1 })
  .limit(20);
```

Với query tìm theo cả hai thành phần qua dot notation và tần suất lớn, có thể xem xét:

```javascript
db.orders.createIndex(
  { "_id.tenantId": 1, "_id.orderNo": 1 },
  { name: "ix_tenant_order_parts" }
);
```

Nếu mọi lookup đều dùng equality toàn bộ `_id` với BSON canonical, index `_id_` sẵn có thường là lựa chọn trực tiếp; không thêm index phụ nếu workload không cần. Mỗi index làm tăng chi phí storage và ghi dữ liệu.

### 6.3. Thứ tự trường trong compound index cũng có ý nghĩa

MongoDB compound index có thứ tự **thành phần key pattern**, ví dụ:

```javascript
{ "_id.tenantId": 1, createdAt: -1 }
```

khác với:

```javascript
{ createdAt: -1, "_id.tenantId": 1 }
```

Thứ tự ảnh hưởng khả năng dùng index prefix, lọc và sắp xếp. Đây là **hai khái niệm cần tách bạch**:

1. Thứ tự field **bên trong subdocument `_id`** ảnh hưởng phép so khớp equality trên cả document khóa.
2. Thứ tự field **trong định nghĩa compound index** ảnh hưởng cách database sử dụng index cho query và sort.

Chúng có thể trùng tên field nhưng không phải cùng một cơ chế.

### 6.4. Đo thay vì đoán

Sử dụng `explain("executionStats")` trên các truy vấn đại diện:

```javascript
// Lookup đúng toàn bộ khóa
db.orders.find({
  _id: { tenantId: "acme", orderNo: "ORD-001" }
}).explain("executionStats");

// Lookup theo một phần khóa
db.orders.find({
  "_id.tenantId": "acme"
}).explain("executionStats");

// Lookup theo tenant và sort thời gian
db.orders.find({
  "_id.tenantId": "acme"
}).sort({ createdAt: -1 }).explain("executionStats");
```

Quan sát `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, thời gian thực thi và các stage như `IXSCAN`/`COLLSCAN`. Dữ liệu mẫu chỉ vài document khó phản ánh lựa chọn index ở quy mô thực; hãy thử với tập dữ liệu và phân bố tenant gần với môi trường sử dụng.

## 7. Validation để bảo vệ cấu trúc khóa

Một rủi ro lớn của `_id` tổng hợp là các client khác nhau gửi cấu trúc sai: thiếu `orderNo`, gán `null`, dùng số thay chuỗi hoặc thêm field bất ngờ. Validation ở application layer hữu ích, nhưng **collection validator** giúp bảo vệ thêm ở database.

Ví dụ dưới đây tạo collection **mới** với yêu cầu `_id` là object có đúng hai trường string khác rỗng:

```javascript
db.createCollection("ordersValidated", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id"],
      properties: {
        _id: {
          bsonType: "object",
          required: ["tenantId", "orderNo"],
          additionalProperties: false,
          properties: {
            tenantId: { bsonType: "string", minLength: 1 },
            orderNo: { bsonType: "string", minLength: 1 }
          }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

Quy tắc trên áp dụng cho `ordersValidated`, không tác động đến `orders` trong các ví dụ trước. Với collection đã tồn tại, dùng cơ chế `collMod` và chiến lược xử lý dữ liệu cũ thích hợp. Validator dùng `validationAction: "error"` từ chối ghi không hợp lệ theo cách MongoDB áp dụng validation.

**Giới hạn của validator:** `$jsonSchema` không dùng để ép **thứ tự key BSON**. Một subdocument có đúng hai field nhưng thứ tự đảo vẫn có thể qua các kiểm tra kiểu/bắt buộc ở trên. Vì thế vẫn cần serializer/converter nhất quán và test equality trên raw document.

Nếu mapping Spring Data tự ghi type hint vào khóa hoặc chuẩn hóa alias khác nhau, `additionalProperties: false` có thể từ chối dữ liệu. Hãy chọn hợp đồng BSON trước, kiểm tra tài liệu ghi thực tế và chỉ sau đó áp validation.

### 7.1. Chuẩn hóa đầu vào ở ranh giới hệ thống

Giả sử API nhận tenant và mã đơn từ hai trường JSON:

```json
{
  "tenantId": "acme",
  "orderNo": "ORD-001",
  "status": "CREATED"
}
```

Quy trình tốt là:

1. Xác thực tenant của request theo cơ chế authentication/authorization; không chỉ tin vào `tenantId` do client tự gửi.
2. Kiểm tra `tenantId` và `orderNo` có mặt, đúng kiểu, không rỗng.
3. Chuẩn hóa case/Unicode/whitespace **nếu nghiệp vụ yêu cầu**; không tùy tiện `toLowerCase()` nếu mã có phân biệt chữ hoa chữ thường.
4. Xây một `OrderKey` canonical theo thứ tự và tên field đã cam kết.
5. Chỉ dùng một cơ chế ghi khóa BSON trong tất cả các đường tạo/upsert/migration.

Validation này bảo vệ cả dữ liệu và logic phân quyền: trong ứng dụng nhiều tenant, lấy document chỉ qua `orderNo` mà không ràng buộc `tenantId` là nguy cơ truy xuất sai phạm vi dữ liệu dù định danh MongoDB vẫn hợp lệ.

## 8. Transaction, sharding và phạm vi duy nhất

### 8.1. Transaction không thay thế ràng buộc định danh

Với single-document insert hoặc update, MongoDB cung cấp tính nguyên tử ở mức document. Khi thao tác nghiệp vụ liên quan nhiều document, chẳng hạn tạo đơn và giảm tồn kho, có thể cần multi-document transaction trên **replica set hoặc sharded cluster** phù hợp. Bản thân `_id` tổng hợp không tự tạo transaction, cũng không làm các thao tác nhiều document thành nguyên tử.

Ví dụ hai tác vụ cùng tạo order có cùng khóa đầy đủ: ràng buộc unique trên `_id` vẫn quan trọng để ngăn ghi trùng; transaction không phải cách thay thế việc xác định uniqueness. Với Spring Data, dùng `MongoTransactionManager` hoặc `ReactiveMongoTransactionManager` đúng loại truy cập khi nghiệp vụ cần giao dịch.

### 8.2. Sharding cần xét shard key và uniqueness riêng

Ở collection sharded, cần kiểm tra:

- **Shard key** là gì? Có chứa tenant để định tuyến truy vấn hay không?
- Query có điều kiện shard key phù hợp để hạn chế scatter-gather hay không?
- MongoDB phiên bản/topology đang dùng bảo đảm uniqueness của `_id` và các unique index ở **phạm vi nào**?
- Có tránh được hot shard khi tenant phân bố lệch hoặc nhiều bản ghi mang cùng shard-key prefix không?

Đặc biệt, trong những cấu hình sharded collection mà `_id` không phải shard key hoặc không có shard-key prefix phù hợp, khả năng áp ràng buộc duy nhất của index `_id` có thể chỉ ở **phạm vi từng shard**. Ứng dụng cần bảo đảm tính duy nhất ở phạm vi toàn cluster theo yêu cầu nghiệp vụ; không thể suy rằng mọi cấu hình sharding bảo đảm giống collection không sharded. Quy tắc chọn shard key/unique index có ràng buộc theo phiên bản và kiểu sharding, cần kiểm tra thiết kế trước khi triển khai.

Thay đổi `_id` tổng hợp hoặc bổ sung thành phần khóa **sau khi đã shard** có thể kéo theo migration phức tạp hơn, đặc biệt nếu shard key gắn với các thành phần đó. Nên quyết định tên, kiểu và thứ tự thành phần khóa từ sớm.

## 9. Tác động tới truy vấn, aggregation và reactive access

### 9.1. Aggregate theo từng thành phần của khóa

Định danh tổng hợp không ngăn aggregation. Dùng đường dẫn field con để nhóm theo tenant:

```javascript
db.orders.aggregate([
  { $match: { "_id.tenantId": "acme" } },
  {
    $group: {
      _id: "$_id.tenantId",
      orderCount: { $sum: 1 }
    }
  }
]);
```

Khi pipeline nhóm theo `"$_id.tenantId"`, `_id` của **kết quả aggregation** là khóa nhóm (ở đây là chuỗi tenant), không có nghĩa đã thay đổi `_id` trong các document nguồn.

Nếu dữ liệu có nhiều biểu diễn khóa khác nhau, aggregation theo thành phần có thể vẫn trả kết quả dù lookup equality trên cả `_id` thất bại; điều này có thể làm lỗi mô hình hóa bị che khuất. Nên kiểm tra đầu vào và raw BSON chứ không chỉ xem báo cáo aggregate.

### 9.2. Repository query theo thành phần

Repository có thể định nghĩa query theo các field con. Ví dụ:

```java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

interface OrderLookupRepository
        extends MongoRepository<PurchaseOrder, OrderKey> {

    @Query("{ '_id.tenantId': ?0 }")
    List<PurchaseOrder> findOrdersForTenant(String tenantId);

    @Query("{ '_id.tenantId': ?0, '_id.orderNo': ?1 }")
    List<PurchaseOrder> findByKeyParts(String tenantId, String orderNo);
}
```

Các query này minh họa đường dẫn BSON thực tế. Trong hệ thống có custom mapping, luôn kiểm tra câu query gửi tới MongoDB và index tương ứng. Đừng dựa vào tên method dài, khó kiểm soát để tự suy ra mapping chính xác.

### 9.3. Reactive MongoDB cũng phải giữ cùng hợp đồng khóa

`ReactiveMongoRepository<PurchaseOrder, OrderKey>` hoặc `ReactiveMongoTemplate` dùng MongoDB reactive driver. Dù API trả về `Mono`/`Flux`, cách biểu diễn `_id` trong BSON vẫn là yêu cầu của **database**, không phụ thuộc reactive hay synchronous.

Nếu cùng một collection được ghi bởi service đồng bộ và reactive, cả hai cần áp dụng cùng schema, tên/kiểu/thứ tự khóa và converter nhất quán. Đừng tùy tiện dùng `Map` không có quy ước thứ tự ở một service và `record`/POJO ở service khác rồi giả định lookup theo full `_id` luôn tương đương.

## 10. Migration khi đã có nhiều dạng khóa

Một số thay đổi thường dẫn đến dữ liệu không đồng nhất:

- Đổi tên `orderNo` thành `orderId` trong kiểu Java nhưng chưa migration dữ liệu cũ.
- Thay `tenantId` từ string sang number.
- Đảo thứ tự hai field trong serializer của một phiên bản service.
- Thêm `region` vào `_id` chỉ với dữ liệu mới.
- Chuyển từ `ObjectId` sang `_id` dạng document mà vẫn giữ API tra cứu cũ.

Do `_id` bất biến, **không thể cập nhật tại chỗ một phần khóa** như sửa field trạng thái. Quy trình migration cần thiết kế ở mức document:

1. **Kiểm kê:** đọc mẫu raw BSON, thống kê các dạng khóa và đối tượng phụ thuộc/tham chiếu.
2. **Định nghĩa canonical key:** chọn chính xác tên, kiểu, thứ tự và cách chuẩn hóa.
3. **Kiểm tra trùng logic:** xác định hai document dạng khóa cũ khác nhau có cùng danh tính nghiệp vụ hay không.
4. **Thực hiện có kiểm soát:** tạo document với khóa mới, di chuyển dữ liệu/tham chiếu theo kế hoạch, cân nhắc transaction hoặc cơ chế đồng bộ trong giai đoạn chuyển đổi.
5. **Chuyển đường đọc/ghi:** quản lý thời điểm deploy để service cũ không tiếp tục sinh khóa sai dạng.
6. **Xác minh và dọn dẹp:** đối chiếu số bản ghi, tham chiếu, truy vấn, index và chỉ xóa bản cũ sau khi có phương án rollback/backup phù hợp.

Không chạy script sửa `_id` hàng loạt bằng `$set`; MongoDB sẽ từ chối. Tránh migration không có phương án xử lý concurrent writes vì có thể phát sinh mất cập nhật khi dữ liệu cũ và mới cùng được ghi.

## 11. Kiểm thử những hành vi dễ sai

### 11.1. Bộ trường hợp kiểm thử tối thiểu

| Kiểm thử | Kết quả cần xác minh |
|---|---|
| Insert hai document có cùng `orderNo` nhưng khác `tenantId` | Được phân biệt là hai định danh khác nhau |
| Insert lại cùng `_id` đầy đủ, đúng cấu trúc | Database từ chối duplicate key |
| Query equality với đúng thứ tự BSON | Tìm đúng document |
| Query equality với thứ tự field đảo | Không khớp document lưu theo thứ tự ban đầu |
| Query dot notation với thứ tự điều kiện đảo | Vẫn tìm đúng dữ liệu |
| Query chỉ `_id.tenantId` | Tìm các đơn của đúng tenant, đo kế hoạch index |
| Gửi `orderNo` dạng number thay vì string | Bị từ chối bởi validator/DTO nếu schema yêu cầu string |
| Gửi khóa thiếu field hoặc có field phụ | Bị kiểm tra validation từ chối |
| Gọi repository `findById` sau khi ghi bằng `insert` | Tìm được cùng document, raw `_id` đúng hợp đồng |
| Gọi `save` khi object có cùng ID | Xác minh hành vi cập nhật và rủi ro ghi đè |
| Cố cập nhật `_id.orderNo` | MongoDB từ chối đổi định danh |
| Truy vấn sau khi nâng cấp converter/serialization | Không bị thay đổi cấu trúc BSON của `_id` |

Tập test nên chạy với MongoDB thật (ví dụ môi trường integration test bằng Testcontainers hoặc deployment kiểm thử) để quan sát behavior BSON và index thực tế, không chỉ mock `MongoRepository`.

### 11.2. Ví dụ kiểm tra raw field order trong Java

```java
import java.util.List;
import org.bson.Document;

Document canonical = new Document("tenantId", "acme")
    .append("orderNo", "ORD-001");

List<String> expectedOrder = List.of("tenantId", "orderNo");
List<String> actualOrder = List.copyOf(canonical.keySet());

if (!expectedOrder.equals(actualOrder)) {
    throw new IllegalStateException("Unexpected composite ID field order");
}
```

Đây là kiểm tra document được xây dựng trong Java. Với Spring Data, cần kiểm tra thêm **document đã lưu và đọc từ MongoDB** qua driver; test một `Document` tự tạo không đủ chứng minh converter Spring tạo cùng cấu trúc.

### 11.3. Chẩn đoán khi `findById` trả rỗng bất ngờ

Thực hiện theo thứ tự:

1. Dùng `mongosh` hoặc raw driver đọc một document hiện có và in toàn bộ `_id`, gồm thứ tự key và kiểu BSON.
2. So sánh với khóa mà Java đang tạo: field name, alias, thứ tự, null/missing, string/number, khoảng trắng và case.
3. So sánh kết quả query full equality `{ _id: {...} }` với dot notation trên từng thành phần.
4. Kiểm tra có nhiều MongoDB URI, database, collection, converter hoặc phiên bản service cùng ghi dữ liệu không.
5. Chạy `explain("executionStats")` để phân biệt lỗi **không khớp dữ liệu** với truy vấn **chậm do index**.

Không vội tăng connection pool hay timeout khi truy vấn thực tế **không tìm thấy khóa do cấu trúc BSON khác nhau**; đó là lỗi mô hình và serialization.

## 12. Thực hành và tiêu chí hoàn thành

**Bài tập:** Một dịch vụ Spring Data MongoDB lưu đơn hàng của nhiều tenant. Mỗi tenant có thể dùng `orderNo = "ORD-001"`, nhưng không được có hai đơn trùng mã trong cùng tenant.

1. Tạo collection `orders` và ghi ba document ở mục 3. Kiểm tra `_id_` index đã có.
2. Thử query full `_id` với thứ tự field đúng/sai, sau đó query bằng hai đường dẫn `_id.tenantId` và `_id.orderNo`. Ghi nhận kết quả khác nhau.
3. Xây `OrderKey` và `PurchaseOrder` trong Spring Data, tạo repository có ID type `OrderKey`. Thực hành `insert` và `findById`.
4. Đọc lại document bằng `MongoTemplate.getCollection(...)` để xác minh raw `_id` trùng hợp đồng BSON.
5. Tạo index phù hợp cho truy vấn tìm tất cả đơn theo tenant và sắp xếp `createdAt`; dùng `explain` để đánh giá.
6. Tạo collection kiểm thử có `$jsonSchema` như mục 7; thử chèn khóa thiếu thành phần và khóa sai kiểu để kiểm tra validator.
7. Thử sửa một thành phần `_id` và quan sát lỗi; mô tả quy trình migration nếu nghiệp vụ muốn sửa `orderNo`.
8. So sánh với phương án `ObjectId` + unique compound index `{ tenantId: 1, orderNo: 1 }`, nêu khi nào nên chọn từng phương án.

**Hoàn thành** khi có thể giải thích sự khác biệt giữa **document equality và dot notation**, giữ ổn định **cấu trúc/thứ tự/kiểu field của khóa**, truy vấn bằng repository/`MongoTemplate` đúng BSON, chọn index dựa trên workload và xử lý việc thay đổi định danh một cách có kiểm soát.

Định danh tổng hợp chỉ bền vững khi mọi lớp cùng thống nhất **một hợp đồng BSON**: thứ tự thành phần, tên field, kiểu dữ liệu, cách chuẩn hóa và tính bất biến. Đây là điều kiện nền tảng để Spring Data MongoDB truy cập chính xác các document trong hệ thống nhiều tenant hoặc dùng khóa nghiệp vụ đa thành phần.
