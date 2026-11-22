# MongoTemplate cho CRUD có điều kiện, bulk và cập nhật mảng trong Spring Data MongoDB

## Mục tiêu bài học

Trong Spring Data MongoDB, `MongoRepository` giúp lập trình viên thao tác với entity theo cách quen thuộc, nhưng có những nghiệp vụ phải thể hiện **điều kiện ngay khi ghi**: trừ tồn kho chỉ khi đủ hàng, chuyển đơn từ `PENDING` sang `PAID` nếu chưa bị hủy, cập nhật hàng nghìn records từ ERP hoặc sửa đúng các phần tử thuộc một mảng embedded documents. Đọc document về Java, sửa rồi `save` không phải lúc nào cũng đúng, vì giữa lần đọc và lần ghi có thể có một request khác cập nhật dữ liệu.

**`MongoTemplate`** cung cấp API chi tiết cho `Query`, `Criteria`, `Update`, `findAndModify`, `upsert`, `BulkOperations` và cập nhật mảng qua positional operators của MongoDB.

Bài thuộc **Database Engine Document MongoDB → Spring Data MongoDB → MongoTemplate cho CRUD có điều kiện, bulk và cập nhật mảng**.

Sau khi học, bạn có thể:

- Giải thích vai trò của `MongoTemplate` so với `MongoRepository` và MongoDB Java Driver.
- Dùng `Query`/`Criteria` để lọc đúng tenant, trạng thái, phạm vi thời gian và phần tử mảng.
- Thực hiện `insert`, `save`, `find`, `findOne`, `exists`, `count`, `remove`.
- Dùng `Update` để thao tác `$set`, `$unset`, `$inc`, `$setOnInsert`, `$push`, `$addToSet`, `$pull`.
- Đọc `UpdateResult` để phân biệt matched, modified, upserted và no-op.
- Dùng `updateFirst`, `updateMulti`, `upsert`, `findAndModify` để thực hiện update có điều kiện.
- Thiết kế atomic conditional writes, optimistic locking và idempotent retries.
- Phân biệt `BulkOperations.BulkMode.ORDERED` và `UNORDERED`, xử lý partial success.
- Áp dụng `$`, `$[]` và `$[identifier]` để cập nhật phần tử mảng thích hợp.
- Cấu hình `Update.filterArray` và hiểu giới hạn mapping của array filters.
- Xử lý nested arrays, duplicate elements, missing arrays, nested field names, schema evolution.
- Phân biệt atomicity của một document, bulk nhiều documents và MongoDB transaction.
- Đánh giá index, performance, security và quan sát lỗi.
- Viết các ví dụ Java và thực hành trên dữ liệu lab an toàn.

> **Nguyên tắc cốt lõi:** Trong MongoDB, một update trên **một document** là atomic, kể cả khi sửa nhiều fields hoặc nhiều phần tử của array đó. `updateMulti` và `BulkOperations` **không mặc nhiên atomic toàn bộ các documents**.

---

## 1. MongoTemplate nằm ở đâu trong Spring Data MongoDB?

~~~text
REST API / Scheduler / Message Consumer
               |
               v
          Service Layer
               |
         +-----+------+
         |            |
         v            v
   MongoRepository  MongoTemplate
   CRUD abstraction Query/Update/Bulk
         |            |
         +-----+------+
               |
               v
       MappingMongoConverter
       @Document/@Field/@Id/@Version
               |
               v
       MongoDB Java Driver
               |
               v
       mongod / mongos / Atlas
~~~

### 1.1. MongoRepository

Repository giúp truy xuất entity qua methods như `save`, `findById`, `deleteById`, derived queries và paging. Phù hợp với phần lớn CRUD đơn giản.

### 1.2. MongoTemplate

Template cho phép thao tác trực tiếp:

~~~java
mongoTemplate.find(query, Order.class);
mongoTemplate.updateFirst(query, update, Order.class);
mongoTemplate.updateMulti(query, update, Order.class);
mongoTemplate.upsert(query, update, Order.class);
mongoTemplate.findAndModify(query, update, options, Order.class);
mongoTemplate.bulkOps(BulkMode.UNORDERED, Order.class);
~~~

Nhờ đó service có thể cập nhật một field mà không ghi lại toàn bộ entity.

### 1.3. Native driver và Spring mapping

`MongoTemplate` sử dụng Spring Data entity metadata. Nếu một property Java được annotate `@Field("tenant_id")`, template có thể map path `tenantId` thành BSON field `tenant_id` trong truy vấn có entity type. Nhưng không được suy rằng **mọi API**, nhất là raw driver hoặc `arrayFilters`, đều map tên trường theo cùng một cách.

### 1.4. Không phải lựa chọn loại trừ

Một dự án có thể dùng `MongoRepository` cho queries đơn giản, `MongoTemplate` trong custom repository/service cho conditional writes và bulk operations.

---

## 2. Chuẩn bị Spring Boot

Dependency Maven minh họa:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

Spring Boot thường tạo `MongoTemplate` qua auto-configuration khi cấu hình MongoDB phù hợp.

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final MongoTemplate mongoTemplate;

    public OrderService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    // Methods sử dụng template được viết ở các mục sau.
}
~~~

Tùy phiên bản Spring Boot/Spring Data, chữ ký methods và dependency versions có thể thay đổi. Dùng BOM/dependency management của dự án và kiểm tra tài liệu chính thức của phiên bản đang triển khai.

### 2.1. URI và bảo mật

Trong môi trường triển khai, sử dụng biến môi trường hoặc secret manager để cung cấp MongoDB URI. Không commit password trực tiếp vào file cấu hình hoặc in toàn bộ connection string ra logs.

### 2.2. Lab database

Các ví dụ dùng database `mongo_template_lab` và collections `orders`/`inventory`. Không chạy commands cập nhật/xóa trong bài trên production.

---

## 3. Entity minh họa và mapping tên field

MongoDB lưu BSON:

~~~javascript
{
  _id: "ORD-101",
  tenant_id: "tenant-a",
  status: "PENDING",
  items: [
    { sku: "SKU-A", quantity: 2, unit_price_minor: NumberLong("100000") },
    { sku: "SKU-B", quantity: 1, unit_price_minor: NumberLong("200000") }
  ],
  tags: ["priority"],
  total_minor: NumberLong("400000"),
  version: NumberLong("1"),
  created_at: ISODate("2026-11-14T01:00:00Z")
}
~~~

Entity Spring Data:

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("orders")
public class Order {

    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String status;

    private List<OrderLine> items;

    private List<String> tags;

    @Field("total_minor")
    private Long totalMinor;

    @Version
    private Long version;

    @Field("created_at")
    private Instant createdAt;

    public Order() {
    }

    // Getters/setters lược bớt vì trọng tâm là MongoTemplate.
}
~~~

~~~java
public class OrderLine {

    private String sku;
    private int quantity;

    @Field("unit_price_minor")
    private long unitPriceMinor;

    public OrderLine() {
    }

    // Getters/setters tương ứng.
}
~~~

### 3.1. Tên Java khác BSON

| Java property | MongoDB BSON field |
|---|---|
| `id` | `_id` |
| `tenantId` | `tenant_id` |
| `status` | `status` |
| `items.quantity` | `items.quantity` |
| `items.unitPriceMinor` | `items.unit_price_minor` |
| `totalMinor` | `total_minor` |
| `createdAt` | `created_at` |
| `version` | `version` |

Khi dùng entity type `Order.class`, có thể truyền property paths được Spring Data map. Với raw collection name hoặc `Update.filterArray`, phải hiểu rõ path nào được ánh xạ và path nào chuyển thẳng đến MongoDB.

### 3.2. Query đúng tenant

`tenantId` không nên lấy tùy tiện từ request body. Trong ứng dụng multi-tenant, tenant phải đến từ ngữ cảnh đã xác thực.

---

## 4. Chuẩn bị dữ liệu trong mongosh

~~~javascript
use mongo_template_lab

db.orders.insertMany([
  {
    _id: "ORD-101",
    tenant_id: "tenant-a",
    status: "PENDING",
    items: [
      { sku: "SKU-A", quantity: 2, unit_price_minor: NumberLong("100000") },
      { sku: "SKU-B", quantity: 1, unit_price_minor: NumberLong("200000") }
    ],
    tags: ["priority"],
    total_minor: NumberLong("400000"),
    version: NumberLong("1"),
    created_at: ISODate("2026-11-14T01:00:00Z")
  },
  {
    _id: "ORD-102",
    tenant_id: "tenant-a",
    status: "PAID",
    items: [
      { sku: "SKU-A", quantity: 1, unit_price_minor: NumberLong("100000") }
    ],
    tags: [],
    total_minor: NumberLong("100000"),
    version: NumberLong("2"),
    created_at: ISODate("2026-11-13T02:00:00Z")
  },
  {
    _id: "ORD-201",
    tenant_id: "tenant-b",
    status: "PENDING",
    items: [
      { sku: "SKU-A", quantity: 3, unit_price_minor: NumberLong("100000") }
    ],
    tags: [],
    total_minor: NumberLong("300000"),
    version: NumberLong("1"),
    created_at: ISODate("2026-11-14T02:00:00Z")
  }
]);

db.inventory.insertMany([
  { _id: "SKU-A", tenant_id: "tenant-a", available: 3 },
  { _id: "SKU-B", tenant_id: "tenant-a", available: 1 }
]);
~~~

**Quan trọng:** Các bài thực hành dùng snapshot/reset data hoặc IDs riêng cho mỗi bài để kết quả không bị ảnh hưởng bởi thao tác trước.

---

## 5. CRUD cơ bản với MongoTemplate

### 5.1. Insert

~~~java
Order order = new Order();
// Thiết lập id, tenantId, status và các thuộc tính.
Order saved = mongoTemplate.insert(order);
~~~

`insert` tạo document mới; nếu `_id` đã tồn tại, unique index gây duplicate key error. Không mặc định chuyển sang update.

### 5.2. Save

~~~java
mongoTemplate.save(order);
~~~

`save` có hành vi insert/update theo ID và thông tin mapping. Khi lưu entity đã tồn tại, thao tác có thể thay **toàn bộ** document, trừ các ràng buộc đặc biệt; không dùng nó làm PATCH từng field một cách vô điều kiện. `@Version` có behavior optimistic locking trong các trường hợp được Spring Data hỗ trợ.

### 5.3. FindById

~~~java
Order found = mongoTemplate.findById(
    "ORD-101",
    Order.class
);
~~~

### 5.4. FindOne có điều kiện

~~~java
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Criteria;

Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("status").is("PENDING")
);

Order order = mongoTemplate.findOne(
    query,
    Order.class
);
~~~

Nếu nhiều documents match, “first” không phải lựa chọn có thứ tự nghiệp vụ ổn định. Khi cần ưu tiên theo thời gian, thêm sort với tie-break.

### 5.5. Find, sort, limit

~~~java
import org.springframework.data.domain.Sort;

Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
);

query.with(
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("_id")
    )
);
query.limit(20);

List<Order> orders = mongoTemplate.find(
    query,
    Order.class
);
~~~

### 5.6. Projection

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
);

query.fields()
    .include("id")
    .include("status")
    .include("totalMinor");
~~~

Entity được load từ projection có thể chỉ chứa một phần fields. **Không dùng partial entity này để replace/save toàn document** trừ khi đó là chủ đích và được bảo vệ.

### 5.7. Exists và count

~~~java
boolean exists = mongoTemplate.exists(
    Query.query(
        Criteria.where("id").is("ORD-101")
            .and("tenantId").is("tenant-a")
    ),
    Order.class
);

long count = mongoTemplate.count(
    Query.query(
        Criteria.where("tenantId").is("tenant-a")
            .and("status").is("PENDING")
    ),
    Order.class
);
~~~

Dùng `exists` thay vì tải toàn entity nếu chỉ cần kiểm tra sự tồn tại.

---

## 6. Criteria: điều kiện là một phần của nghiệp vụ

### 6.1. So sánh và phạm vi

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("status").in("PENDING", "PROCESSING")
        .and("totalMinor").gte(100_000L)
);
~~~

### 6.2. Operators thường dùng

| Phương thức | Ý nghĩa |
|---|---|
| `is(value)` | Bằng |
| `ne(value)` | Khác |
| `gt/gte/lt/lte` | So sánh phạm vi |
| `in/nin` | Tập hợp |
| `exists` | Có hoặc không có field |
| `elemMatch` | Cùng một element array thỏa các điều kiện |
| `andOperator` | Kết hợp AND |
| `orOperator` | Kết hợp OR |
| `regex` | Regex, cần kiểm soát input/index |
| `size` | Kích thước array |

### 6.3. AND/OR rõ ràng

~~~java
Criteria states = new Criteria().orOperator(
    Criteria.where("status").is("PENDING"),
    Criteria.where("status").is("PROCESSING")
);

Query query = Query.query(
    new Criteria().andOperator(
        Criteria.where("tenantId").is("tenant-a"),
        states
    )
);
~~~

Nếu cần ràng buộc nhiều conditions trên cùng field, dùng operator có thể biểu diễn đúng logic; đừng cố gắn nhiều Criteria xung đột lên cùng một BSON key.

### 6.4. Đừng biến JSON từ client thành raw query

Cho phép user tùy ý truyền `$where`, `$regex` rất lớn, tên field hệ thống hoặc update operators có thể gây query quá tải hoặc sửa dữ liệu ngoài quyền. Whitelist fields, operators, sort và tenant scope.

---

## 7. Động lực: read–modify–save có race condition

Giả sử tồn kho SKU-A chỉ còn 1:

~~~text
A đọc available=1
B đọc available=1
A giảm về 0 rồi save
B giảm về 0 rồi save
-> Cả hai requests đều nghĩ đã giữ được 1 sản phẩm.
~~~

Giải pháp là đưa **precondition** vào **cùng một write**.

### 7.1. MongoDB native

~~~javascript
db.inventory.updateOne(
  {
    _id: "SKU-A",
    tenant_id: "tenant-a",
    available: { $gte: 1 }
  },
  {
    $inc: { available: -1 }
  }
);
~~~

### 7.2. MongoTemplate conditional update

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.query.Update;

int requestedQuantity = 1;

if (requestedQuantity <= 0) {
    throw new IllegalArgumentException(
        "Quantity must be positive"
    );
}

Query query = Query.query(
    Criteria.where("_id").is("SKU-A")
        .and("tenant_id").is("tenant-a")
        .and("available").gte(requestedQuantity)
);

Update update = new Update()
    .inc("available", -requestedQuantity);

UpdateResult result = mongoTemplate.updateFirst(
    query,
    update,
    "inventory"
);

boolean reserved =
    result.wasAcknowledged()
    && result.getModifiedCount() == 1;
~~~

Dùng tên collection `"inventory"` và BSON paths vì chưa có entity `Inventory.class`. Khi dùng typed entity, có thể dùng các property names được mapping.

### 7.3. Vì sao tránh oversell?

Server đánh giá filter và update của document trong một thao tác atomic. Khi A đã giảm stock=0, B không còn match `available>=1`.

### 7.4. Vẫn cần transaction khi nhiều documents liên quan

Nếu giữ tồn kho trên một document nhưng tạo order trên document khác, hai thao tác không tự atomically commit cùng nhau. Cần transaction hoặc compensating workflow/outbox theo yêu cầu.

---

## 8. Update builder và các phép toán thông dụng

### 8.1. `$set`

~~~java
Update update = new Update()
    .set("status", "PAID")
    .set("updatedAt", Instant.now());
~~~

Chỉ thay các fields được set. Khi update với `Order.class`, `updatedAt` có thể map sang `updated_at`.

### 8.2. `$unset`

~~~java
new Update().unset("obsoleteNote");
~~~

Xóa field khỏi BSON. Khác với `set("obsoleteNote", null)`: null là một giá trị BSON, còn unset làm field không tồn tại.

### 8.3. `$inc`

~~~java
new Update().inc("retryCount", 1);
~~~

Increment atomic ở cấp document. Với retry không kiểm soát, một operation có thể cộng hai lần nếu request được xử lý lại độc lập.

### 8.4. `$min` và `$max`

~~~java
new Update()
    .min("lowestPrice", 100_000)
    .max("highestPrice", 500_000);
~~~

Không dùng với hỗn hợp BSON number/string mà chưa xác định semantics so sánh.

### 8.5. `$mul`

~~~java
new Update().multiply("coefficient", 2);
~~~

Chú ý overflow/precision nếu dùng tính giá.

### 8.6. `$currentDate`

~~~java
new Update().currentDate("updatedAt");
~~~

Để MongoDB server tạo thời điểm hiện tại, tránh phụ thuộc vào từng máy application. Tùy mục tiêu audit, có thể dùng Spring Data auditing.

### 8.7. `$setOnInsert`

~~~java
new Update()
    .set("status", "PENDING")
    .setOnInsert("createdAt", Instant.now());
~~~

`setOnInsert` chỉ áp dụng khi **upsert insert** document mới. Không đặt cùng một field trong `set` và `setOnInsert` vì có thể tạo conflict.

---

## 9. `updateFirst`: chuyển trạng thái có điều kiện

~~~java
Query query = Query.query(
    Criteria.where("id").is("ORD-101")
        .and("tenantId").is("tenant-a")
        .and("status").is("PENDING")
);

Update update = new Update()
    .set("status", "PAID")
    .currentDate("updatedAt");

UpdateResult result = mongoTemplate.updateFirst(
    query,
    update,
    Order.class
);
~~~

Nếu order đã `CANCELLED`, filter không match. Đây là cách chuyển trạng thái có điều kiện thay vì ghi đè.

### 9.1. `UpdateResult`

~~~java
boolean ack = result.wasAcknowledged();
long matched = result.getMatchedCount();
long modified = result.getModifiedCount();
~~~

**Chỉ truy cập count khi write được acknowledged**. Với write concern unacknowledged, một số getters không khả dụng.

### 9.2. Matched và modified

| Matched | Modified | Diễn giải |
|---:|---:|---|
| 0 | 0 | Không có document khớp predicate |
| 1 | 1 | Một document được thay đổi |
| 1 | 0 | Document match nhưng update không làm giá trị đổi |
| N | M | Có thể xảy ra với updateMulti; số documents match/đổi khác nhau |

Đặc biệt, `modifiedCount=0` **không tự chứng minh document không tồn tại**.

### 9.3. First không có order đảm bảo

Nếu filter match nhiều documents, `updateFirst` không nên được dùng để chọn “đơn cũ nhất” dựa trên thứ tự tự nhiên. Dùng unique filter hoặc `findAndModify` với query sort để làm work queue.

---

## 10. `updateMulti`: cập nhật nhiều documents

Ví dụ đóng các orders PENDING đã quá hạn:

~~~java
Instant cutoff = Instant.parse(
    "2026-11-14T00:00:00Z"
);

Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("status").is("PENDING")
        .and("createdAt").lt(cutoff)
);

Update update = new Update()
    .set("status", "EXPIRED")
    .currentDate("updatedAt");

UpdateResult result = mongoTemplate.updateMulti(
    query,
    update,
    Order.class
);
~~~

### 10.1. Atomic theo document, không atomic toàn tập

Nếu 10.000 orders khớp, một số documents có thể đã thay trước khi operation lỗi. Đừng hiểu updateMulti là transaction across all documents.

### 10.2. Retry và idempotency

`$set status=EXPIRED` kết hợp predicate `status=PENDING` thường dễ retry hơn một bulk `$inc`. Nếu business cho phép các trạng thái chuyển đổi cạnh tranh, phải kiểm tra preconditions.

### 10.3. Phạm vi cập nhật

Batch job nên luôn có tenant/status/date hoặc ID ranges, audit incident/ticket và threshold phù hợp. Không chấp nhận update toàn collection qua một request client không được kiểm soát.

### 10.4. Không mặc định toàn bộ indexes sẽ được dùng

Predicate chọn lọc và index phù hợp như `tenant_id,status,created_at` có thể giảm scan; phải đo bằng explain.

---

## 11. `upsert`: tạo nếu không tồn tại

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("externalId").is("ERP-1001")
);

Update update = new Update()
    .set("status", "PENDING")
    .set("totalMinor", 300_000L)
    .setOnInsert("createdAt", Instant.now());

UpdateResult result = mongoTemplate.upsert(
    query,
    update,
    Order.class
);
~~~

Ví dụ giả định entity có property `externalId` map sang BSON `external_id`.

### 11.1. Unique index ngăn upsert race

~~~javascript
db.orders.createIndex(
  { tenant_id: 1, external_id: 1 },
  { unique: true, name: "uk_orders_tenant_external" }
);
~~~

Nếu hai workers cùng upsert một business key chưa có, unique index là cơ chế quan trọng bảo vệ identity. Cần xử lý duplicate key / retry phù hợp.

### 11.2. Upsert với volatile filter có thể nguy hiểm

Không dùng upsert cho conditional stock decrement với filter `available>=3`. Khi stock thấp, filter không match và upsert có thể **insert document mới**, trái nghiệp vụ. Dùng `updateFirst`.

### 11.3. Phân biệt update hay insert

~~~java
if (result.getUpsertedId() != null) {
    // Một document mới được tạo.
}
~~~

Khi upsert update existing record, `getUpsertedId()` thường null.

### 11.4. Upsert không mặc định idempotent

Upsert chứa `$inc` hoặc một timestamp thay đổi ở mỗi request có thể không idempotent. Định nghĩa source version/idempotency key khi dữ liệu được đồng bộ qua event hoặc API retries.

---

## 12. `findAndModify`: thay đổi và nhận document trước/sau

~~~java
import org.springframework.data.mongodb.core.FindAndModifyOptions;

Query query = Query.query(
    Criteria.where("id").is("ORD-101")
        .and("tenantId").is("tenant-a")
        .and("status").is("PENDING")
);

Update update = new Update()
    .set("status", "PROCESSING");

Order updated = mongoTemplate.findAndModify(
    query,
    update,
    FindAndModifyOptions.options()
        .returnNew(true)
        .upsert(false),
    Order.class
);
~~~

- `returnNew(false)`: lấy trạng thái trước update.
- `returnNew(true)`: lấy trạng thái sau update.
- `upsert(false)` và không match: kết quả có thể null.

### 12.1. Job claim có sort

~~~java
Query ready = Query.query(
    Criteria.where("status").is("READY")
);
ready.with(
    Sort.by(Sort.Direction.ASC, "createdAt")
);

Job job = mongoTemplate.findAndModify(
    ready,
    new Update().set("status", "RUNNING"),
    FindAndModifyOptions.options()
        .returnNew(true),
    Job.class
);
~~~

Giả định entity `Job` đã được định nghĩa. Việc chọn và đổi trạng thái của một job là atomic ở cấp document; với worker queue thực cần thêm lease, timeout, heartbeat và retry/idempotency.

### 12.2. Vì sao không find rồi update?

Hai requests có thể cùng đọc job READY trước khi một request thay trạng thái. `findAndModify` giúp chọn và thay đổi trong một operation.

---

## 13. `@Version` và optimistic locking

Spring Data hỗ trợ optimistic locking với `@Version` khi dùng các entity operations tương ứng.

~~~java
@Document("orders")
public class Order {
    @Id
    private String id;

    @Version
    private Long version;

    // ...
}
~~~

### 13.1. Save và version

~~~text
Request A đọc order, version=3
Request B đọc order, version=3
A sửa, save -> version tăng
B save trên version cũ -> optimistic lock conflict
~~~

Với acknowledged writes, Spring Data có thể báo `OptimisticLockingFailureException` khi stale version.

### 13.2. Template update không tự CAS theo @Version

Một `updateFirst` chỉ lọc theo ID **không tự thêm điều kiện expected version** chỉ vì class có `@Version`. Spring Data có thể tự tăng version property ở một số mapped update paths nếu update chưa khai báo nó, nhưng **tăng version không giống kiểm tra version cũ**.

### 13.3. CAS chủ động

~~~java
long expectedVersion = 3L;

Query query = Query.query(
    Criteria.where("id").is("ORD-101")
        .and("tenantId").is("tenant-a")
        .and("version").is(expectedVersion)
);

Update update = new Update()
    .set("status", "PAID")
    .inc("version", 1);

UpdateResult result = mongoTemplate.updateFirst(
    query,
    update,
    Order.class
);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
        "Version conflict, forbidden or missing order"
    );
}
~~~

Trong ví dụ, version được tăng explicit, tránh dựa vào behavior auto-increment chưa được kiểm thử.

### 13.4. Bulk không thay thế optimistic entity saves

`BulkOperations` không tự bảo đảm optimistic locking per entity/callbacks tương tự `save`. Nếu cần CAS trong bulk, thêm expected version vào từng Query và kiểm tra kết quả theo từng business key hoặc chiến lược đối soát.

---

## 14. Xóa có điều kiện

### 14.1. Remove nhiều documents

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("status").is("EXPIRED")
        .and("createdAt").lt(cutoff)
);

var deleteResult = mongoTemplate.remove(
    query,
    Order.class
);

System.out.println(
    deleteResult.getDeletedCount()
);
~~~

`remove(Query,Class)` có thể xóa nhiều documents. Nếu chỉ được xóa một, dùng unique predicate hoặc `findAndRemove` phù hợp.

### 14.2. Soft delete

~~~java
new Update()
    .set("deleted", true)
    .currentDate("updatedAt");
~~~

Soft delete hỗ trợ audit/recovery nhưng mọi readers phải tôn trọng deleted flag; uniqueness/TTL/retention cũng phải được thiết kế.

### 14.3. Xóa document khác xóa array element

`remove` xóa cả order document. `Update.pull("items",...)` xóa những phần tử matching trong mảng `items` của document.

### 14.4. Security

Đối với multi-tenant, filter luôn gồm trusted tenant. Không cho caller gửi ID của tenant khác rồi xóa khi chưa authorize.

---

## 15. BulkOperations: tối ưu nhiều writes

Giả sử đồng bộ 30.000 thay đổi từ ERP. Gửi từng update qua network riêng có overhead lớn. `BulkOperations` gom các write models vào lô.

~~~java
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.BulkOperations.BulkMode;

BulkOperations bulk = mongoTemplate.bulkOps(
    BulkMode.UNORDERED,
    Order.class
);
~~~

### 15.1. Ordered và unordered

| Mode | Semantics | Dùng khi |
|---|---|---|
| `ORDERED` | Thực hiện theo thứ tự; thường dừng khi lỗi | Operations có dependency |
| `UNORDERED` | Không đảm bảo thứ tự; có thể tiếp tục operations khác khi một write lỗi | Writes độc lập, throughput |

**Cả hai không tự có all-or-nothing transaction semantics.**

### 15.2. Khi nào không nên bulk?

- Cần atomic transaction xuyên nhiều documents nhưng chưa cấu hình transaction.
- Cần entity callbacks/optimistic locking per record theo lộ trình mà bulk không cung cấp.
- Muốn trả chi tiết từng entity updated ngay lập tức.
- Batch lớn vô hạn khiến JVM giữ nhiều request objects.

### 15.3. Một bulk operation không tương đương một document

`bulk.updateMulti(query,update)` có thể thay đổi hàng nghìn documents dù chỉ là một operation được thêm vào builder. Kết quả phải phân biệt số write models và số documents thực sự thay đổi.

---

## 16. Bulk update/upsert/remove với Java

~~~java
import com.mongodb.bulk.BulkWriteResult;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.BulkOperations.BulkMode;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

BulkOperations bulk = mongoTemplate.bulkOps(
    BulkMode.UNORDERED,
    Order.class
);

bulk.updateOne(
    Query.query(
        Criteria.where("id").is("ORD-101")
            .and("tenantId").is("tenant-a")
            .and("status").is("PENDING")
    ),
    new Update().set("status", "PROCESSING")
);

bulk.updateMulti(
    Query.query(
        Criteria.where("tenantId").is("tenant-a")
            .and("status").is("EXPIRED")
    ),
    new Update().set("status", "ARCHIVED")
);

bulk.upsert(
    Query.query(
        Criteria.where("tenantId").is("tenant-a")
            .and("externalId").is("ERP-102")
    ),
    new Update()
        .set("status", "NEW")
        .setOnInsert("createdAt", Instant.now())
);

bulk.remove(
    Query.query(
        Criteria.where("tenantId").is("tenant-a")
            .and("status").is("PURGED")
    )
);

BulkWriteResult result = bulk.execute();

System.out.println(result.getInsertedCount());
System.out.println(result.getMatchedCount());
System.out.println(result.getModifiedCount());
System.out.println(result.getDeletedCount());
~~~

### 16.1. Kích thước batch

Driver có giới hạn protocol/command size và có thể chia batches nội bộ. Tuy vậy, application vẫn nên chia input thành batches hữu hạn (ví dụ vài trăm operations theo benchmark) để tránh giữ hàng triệu objects trong heap, dễ checkpoint và xử lý partial success.

### 16.2. Không mặc định callbacks, auditing và version

Spring Data bulk operations không mang đầy đủ semantics của từng entity save, đặc biệt optimistic locking/callbacks. Nếu muốn ghi `updatedAt`, `version` hoặc audit fields, xác định chúng explicit và kiểm tra behavior.

### 16.3. Atomicity

Bulk làm tăng hiệu quả throughput nhưng không tự làm tất cả operations cùng commit. Nếu batch bị lỗi, một phần writes có thể đã thành công.

---

## 17. Bulk partial success và xử lý lỗi

### 17.1. Ordered bulk

Nếu operation thứ 12 bị duplicate key, operations sau có thể không chạy. Những operations trước đã được thực thi không tự rollback.

### 17.2. Unordered bulk

MongoDB có thể tiếp tục xử lý các operations không phụ thuộc. Không được giả định thứ tự chúng hoàn thành giống thứ tự append.

### 17.3. Exceptions

Tùy tầng driver/Spring Data, lỗi có thể hiện ra dưới `MongoBulkWriteException` hoặc dạng exception đã được dịch. Cần ghi lại error indices, server code và kết quả partial khi API cung cấp, thay vì chỉ catch Exception và retry toàn batch.

### 17.4. Network timeout không đồng nghĩa không ghi

Nếu client timeout sau khi server áp dụng một phần hoặc toàn bộ writes, không thể coi toàn batch chưa chạy. Cần đọc state theo business key trước khi retry.

### 17.5. Idempotency

- `$set` cùng giá trị dễ retry hơn.
- `$inc` có thể cộng hai lần.
- `$push` có thể thêm hai phần tử trùng.
- `upsert` có unique key giúp bảo vệ identity.
- Side effects ra broker/payment provider cần idempotency riêng.

### 17.6. Checkpoint

Một job sync nên xử lý:

~~~text
Read next source chunk
        |
        v
Build BulkOperations
        |
        v
Execute, record partial failures
        |
        v
Verify/reconcile affected business keys
        |
        v
Persist checkpoint
~~~

Checkpoint trước khi write xong có thể làm mất operations; checkpoint sau khi write làm retry trùng có thể xảy ra, nên idempotency là bắt buộc.

---

## 18. Ba positional operators của MongoDB

| Operator | Ý nghĩa | Ví dụ |
|---|---|---|
| `$` | Phần tử đầu tiên khớp array condition của query | `items.$.quantity` |
| `$[]` | Mọi phần tử trong array của document được chọn | `items.$[].gift` |
| `$[line]` | Mọi phần tử thỏa array filter có identifier `line` | `items.$[line].quantity` |

Ví dụ array:

~~~javascript
{
  _id: "ORD-101",
  items: [
    { sku: "SKU-A", quantity: 2 },
    { sku: "SKU-B", quantity: 1 },
    { sku: "SKU-A", quantity: 4 }
  ]
}
~~~

Nếu array có hai item SKU-A:

- `$` sửa **một** item phù hợp đầu tiên.
- `$[]` sửa **cả ba** items.
- `$[line]` với filter SKU-A sửa **hai** items.

Đọc chính xác business requirement trước khi chọn operator.

---

## 19. Positional `$`: cập nhật phần tử đầu tiên

### 19.1. mongosh

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    tenant_id: "tenant-a",
    "items.sku": "SKU-A"
  },
  {
    $inc: { "items.$.quantity": 1 }
  }
);
~~~

### 19.2. MongoTemplate

~~~java
Query query = Query.query(
    Criteria.where("id").is("ORD-101")
        .and("tenantId").is("tenant-a")
        .and("items.sku").is("SKU-A")
);

Update update = new Update()
    .inc("items.$.quantity", 1);

UpdateResult result = mongoTemplate.updateFirst(
    query,
    update,
    Order.class
);
~~~

### 19.3. Phải có matching array condition

Query chọn một document bằng ID nhưng không xác định array element có thể dẫn tới lỗi positional operator không tìm được match cần thiết.

### 19.4. Giới hạn

- Chỉ phần tử đầu theo binding.
- Khi query có nhiều array paths, binding `$` có thể mơ hồ.
- Không dùng để upsert tạo array element tùy ý.
- Với nested arrays, nên cân nhắc `$[identifier]`.

### 19.5. Nếu một SKU có thể xuất hiện nhiều lần

`$` không thể thay thế quy tắc business “cập nhật tất cả items cùng SKU”. Dùng `$[line]` nếu đó mới là ý định.

---

## 20. `$elemMatch`: nhiều điều kiện trên cùng một element

Có array:

~~~javascript
items: [
  { sku: "SKU-A", quantity: 1 },
  { sku: "SKU-B", quantity: 8 }
]
~~~

Query này:

~~~javascript
{
  "items.sku": "SKU-A",
  "items.quantity": { $gte: 5 }
}
~~~

có thể match do hai điều kiện được đáp ứng bởi **hai elements khác nhau**.

Dùng `$elemMatch`:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "SKU-A",
      quantity: { $gte: 5 }
    }
  }
});
~~~

MongoTemplate:

~~~java
Criteria line = Criteria.where("sku")
    .is("SKU-A")
    .and("quantity").gte(5);

Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("items").elemMatch(line)
);
~~~

Điều này xác định SKU và quantity trên **cùng một phần tử**. Nó có thể quan trọng cả trong query và positional update matching.

---

## 21. All positional `$[]`: sửa mọi phần tử

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101", tenant_id: "tenant-a" },
  { $set: { "items.$[].gift": true } }
);
~~~

MongoTemplate:

~~~java
Query query = Query.query(
    Criteria.where("id").is("ORD-101")
        .and("tenantId").is("tenant-a")
);

Update update = new Update()
    .set("items.$[].gift", true);

mongoTemplate.updateFirst(
    query,
    update,
    Order.class
);
~~~

### 21.1. Điều kiện query không giới hạn elements

Nếu query có `items.sku="SKU-A"` nhưng update là `items.$[].gift`, **mọi** item được cập nhật, gồm SKU-B.

### 21.2. Mảng rỗng/missing

Khi array không có phần tử, có thể không thay đổi gì. Nếu path không tồn tại hoặc không có kiểu array, một số positional updates có thể lỗi. Test behavior trên dữ liệu thực.

### 21.3. Upsert constraints

Với `$[]` trong upsert, MongoDB có yêu cầu exact equality match với array field trong filter khi cần insert mới. Không dùng `upsert` cho positional array edits thông thường nếu chỉ muốn sửa document đang tồn tại.

---

## 22. Filtered positional `$[line]` với arrayFilters

Để tăng quantity của **mọi** item SKU-A:

### 22.1. Mongosh

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    tenant_id: "tenant-a"
  },
  {
    $inc: {
      "items.$[line].quantity": 2
    }
  },
  {
    arrayFilters: [
      { "line.sku": "SKU-A" }
    ]
  }
);
~~~

### 22.2. Spring Data

~~~java
Query query = Query.query(
    Criteria.where("id").is("ORD-101")
        .and("tenantId").is("tenant-a")
);

Update update = new Update()
    .inc("items.$[line].quantity", 2)
    .filterArray(
        Criteria.where("line.sku").is("SKU-A")
    );

UpdateResult result = mongoTemplate.updateFirst(
    query,
    update,
    Order.class
);
~~~

### 22.3. Vai trò của Query và arrayFilters

- `Query` xác định **document nào** được chọn.
- `arrayFilters` xác định **element nào** trong array cần update.

Nếu document không match, không có update. Nếu document match nhưng không có element phù hợp, `modifiedCount` có thể bằng 0.

### 22.4. Mapping của `Update.filterArray`

Tài liệu Spring Data cho biết filter của `filterArray` được gửi trực tiếp tới driver, **không qua field mapping bổ sung**.

Giả sử entity:

~~~java
@Field("unit_price_minor")
private long unitPriceMinor;
~~~

Để lọc theo BSON field của line, dùng:

~~~java
Update update = new Update()
    .set("items.$[line].gift", true)
    .filterArray(
        Criteria.where("line.unit_price_minor")
            .gte(100_000L)
    );
~~~

Không truyền `"line.unitPriceMinor"` nếu database thực lưu `unit_price_minor`.

### 22.5. Identifier

`line` là tên identifier hợp lệ, không phải tên class. Nó cần bắt đầu bằng chữ thường và tuân thủ quy tắc identifier của MongoDB.

### 22.6. Nhiều điều kiện

~~~java
Update update = new Update()
    .set("items.$[line].gift", true)
    .filterArray(
        Criteria.where("line.sku").is("SKU-A")
            .and("line.quantity").gte(2)
    );
~~~

Cả SKU và quantity áp trên một line element.

---

## 23. So sánh ba operators trên cùng dữ liệu

Trạng thái gốc:

~~~javascript
items: [
  { sku: "A", quantity: 1 },
  { sku: "B", quantity: 2 },
  { sku: "A", quantity: 3 }
]
~~~

### 23.1. `$`

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101", "items.sku": "A" },
  { $inc: { "items.$.quantity": 1 } }
);
~~~

Kết quả:

~~~javascript
[
  { sku: "A", quantity: 2 },
  { sku: "B", quantity: 2 },
  { sku: "A", quantity: 3 }
]
~~~

### 23.2. `$[]`

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  { $inc: { "items.$[].quantity": 1 } }
);
~~~

Kết quả:

~~~javascript
[
  { sku: "A", quantity: 2 },
  { sku: "B", quantity: 3 },
  { sku: "A", quantity: 4 }
]
~~~

### 23.3. `$[line]`

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  { $inc: { "items.$[line].quantity": 1 } },
  { arrayFilters: [{ "line.sku": "A" }] }
);
~~~

Kết quả:

~~~javascript
[
  { sku: "A", quantity: 2 },
  { sku: "B", quantity: 2 },
  { sku: "A", quantity: 4 }
]
~~~

**Mỗi thử nghiệm bắt đầu từ dữ liệu gốc**, không chạy ba commands nối tiếp rồi so với ba kết quả riêng.

---

## 24. `updateMulti` kết hợp filtered positional

Nếu cần đánh dấu `gift=true` cho SKU-A trong mọi orders PENDING của tenant-a:

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("status").is("PENDING")
);

Update update = new Update()
    .set("items.$[line].gift", true)
    .filterArray(
        Criteria.where("line.sku").is("SKU-A")
    );

UpdateResult result = mongoTemplate.updateMulti(
    query,
    update,
    Order.class
);
~~~

### 24.1. Matched/modified đếm **documents**

Nếu một order có 100 items SKU-A được đổi, `modifiedCount` vẫn chỉ tăng **1** cho order đó. Nó không phải số array elements được cập nhật.

### 24.2. Không phải transaction toàn tập

Mỗi order được update atomic, nhưng nếu có 200 orders, một sự cố giữa chừng có thể để lại một số orders chưa được đổi. Dùng idempotent update/compensation/reconciliation hoặc transaction khi phù hợp.

### 24.3. Tenant filter là bắt buộc

`arrayFilters` chọn line item, không hạn chế tenant. Nếu thiếu tenant filter ở query, có thể đổi items của khách hàng khác.

---

## 25. Nested arrays với hai identifiers

Document:

~~~javascript
{
  _id: "CAT-1",
  warehouses: [
    {
      code: "HCM",
      bins: [
        { sku: "A", available: 10 },
        { sku: "B", available: 2 }
      ]
    },
    {
      code: "HN",
      bins: [
        { sku: "A", available: 8 }
      ]
    }
  ]
}
~~~

Giảm SKU-A trong warehouse HCM:

~~~javascript
db.catalog.updateOne(
  { _id: "CAT-1" },
  {
    $inc: {
      "warehouses.$[wh].bins.$[bin].available": -1
    }
  },
  {
    arrayFilters: [
      { "wh.code": "HCM" },
      { "bin.sku": "A", "bin.available": { $gte: 1 } }
    ]
  }
);
~~~

MongoTemplate:

~~~java
Update update = new Update()
    .inc(
        "warehouses.$[wh].bins.$[bin].available",
        -1
    )
    .filterArray(
        Criteria.where("wh.code").is("HCM")
    )
    .filterArray(
        Criteria.where("bin.sku").is("A")
            .and("bin.available").gte(1)
    );

mongoTemplate.updateFirst(
    Query.query(
        Criteria.where("id").is("CAT-1")
    ),
    update,
    CatalogEntity.class
);
~~~

Ví dụ giả định `CatalogEntity` mapping đúng collection `catalog`. Để tránh oversell thực tế, cần schema invariant và concurrency strategy đầy đủ.

### 25.1. Duplicated keys

Nếu có hai warehouses cùng code HCM hoặc hai bins SKU-A, filtered operators có thể sửa **nhiều** elements. Nếu business chỉ cho phép một, dùng subdocument IDs/validation hoặc tái thiết kế schema.

### 25.2. Nested array lớn

Một document chứa hàng nghìn bins nóng có thể gây write contention và tăng chi phí serialization. Cân nhắc mô hình mỗi warehouse+sku là document riêng khi workload cần concurrent updates mạnh.

---

## 26. `$push`: thêm phần tử

~~~java
Update update = new Update()
    .push("tags", "priority");

mongoTemplate.updateFirst(
    query,
    update,
    Order.class
);
~~~

`$push` thêm phần tử vào cuối array, kể cả khi phần tử giống hệt đã tồn tại.

### 26.1. Push nhiều phần tử

~~~java
Update update = new Update()
    .push("tags")
    .each("priority", "gift");
~~~

### 26.2. Các modifiers

MongoDB `$push` hỗ trợ `$each`, `$position`, `$sort` và `$slice` để thêm, sắp xếp, giới hạn array. Spring Data có builder tương ứng; kiểm tra signatures theo dependency version.

### 26.3. Không dùng unbounded event array

Nếu push mọi audit event vào một order, document có thể tăng tới giới hạn BSON 16 MiB và tạo hotspot. Với lịch sử dài, dùng collection events riêng, có unique eventId/index thích hợp.

### 26.4. Retry không idempotent

Nếu request bị gửi lại, push có thể tạo phần tử trùng. Với các events cần at-least-once processing, dùng stable event IDs/dedup.

---

## 27. `$addToSet`: thêm nếu chưa tồn tại

~~~java
Update update = new Update()
    .addToSet("tags", "priority");
~~~

Thêm nhiều:

~~~java
new Update()
    .addToSet("tags")
    .each("priority", "gift");
~~~

### 27.1. Equality là của toàn phần tử

Với embedded documents:

~~~javascript
{ sku: "A", quantity: 1 }
{ sku: "A", quantity: 2 }
~~~

Hai documents khác nhau, nên `$addToSet` có thể giữ cả hai. Nó **không unique theo một field con** như `sku`.

### 27.2. Không thay unique index

Nếu cần uniqueness cho line items theo tenant+SKU trên hàng triệu records, cân nhắc schema tách collection và compound unique index hoặc application invariant; `$addToSet` không tự giải quyết tất cả.

### 27.3. Ordering

`$addToSet` là thao tác set membership, không dùng làm sorted list có contract thứ tự. Nó cũng không tự dọn duplicates đã tồn tại trước đó.

---

## 28. `$pull`: xóa những phần tử phù hợp

Xóa tag:

~~~java
new Update()
    .pull("tags", "priority");
~~~

Xóa items SKU-B:

~~~java
import org.bson.Document;

Update update = new Update()
    .pull(
        "items",
        new Document("sku", "SKU-B")
    );
~~~

### 28.1. Nhiều phần tử có thể bị xóa

Nếu array có hai line items SKU-B, `$pull` theo SKU xóa cả hai. Không nhầm với “xóa phần tử đầu tiên”.

### 28.2. `$pull` khác `$pop` và `$unset`

- `$pull`: xóa các elements thỏa điều kiện.
- `$pop`: xóa đầu/cuối array.
- `$unset` trên positional array element có semantics khác, có thể để lại null slot.

### 28.3. Cập nhật tổng tiền

Khi xóa item nhưng `total_minor` vẫn giữ giá cũ, order có thể sai business invariant. Cần transaction ở phạm vi document/update pipeline hoặc tính toán lại dựa trên source, không coi array edit đủ cho nghiệp vụ.

---

## 29. Vì sao không read Java List rồi save lại?

Một flow dễ viết:

~~~text
A đọc Order với items=[A,B]
B thêm item C bằng $push
A sửa quantity item A
A save toàn Order từ bản cũ
-> Item C của B có thể bị mất.
~~~

### 29.1. Sửa đúng một element

~~~java
Update update = new Update()
    .inc("items.$[line].quantity", 1)
    .filterArray(
        Criteria.where("line.sku").is("SKU-A")
    );

mongoTemplate.updateFirst(
    Query.query(
        Criteria.where("id").is(orderId)
            .and("tenantId").is(tenantId)
    ),
    update,
    Order.class
);
~~~

Giảm payload/lost-update risk so với thay toàn array.

### 29.2. `@Version` và save

Nếu dùng entity save có optimistic locking đúng, request A có thể nhận conflict thay vì mất item C. Nhưng application vẫn phải xử lý conflict/re-read/retry; không hứa `save` tự merge lists.

### 29.3. Array quá lớn

Một document có items/events tăng không giới hạn sẽ tốn băng thông, memory, write contention và có thể vượt 16 MiB BSON document limit. Schema phải phù hợp query/update patterns.

---

## 30. Update bằng aggregation pipeline

Nếu thay đổi nhiều field dựa trên giá trị hiện tại trong cùng document, MongoDB hỗ trợ **aggregation pipeline updates**.

Ví dụ mongosh tính lại total quantity:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    tenant_id: "tenant-a"
  },
  [
    {
      $set: {
        total_quantity: {
          $sum: "$items.quantity"
        }
      }
    }
  ]
);
~~~

Spring Data cung cấp `AggregationUpdate` cho các trường hợp tương ứng; API builder cụ thể phụ thuộc phiên bản Spring Data. Khi cần `$map`/`$filter` phức tạp, có thể xây pipeline theo DSL được hỗ trợ hoặc dùng raw BSON với việc kiểm soát tên field/mapping.

### 30.1. Khi thích hợp

- Tính field mới từ các fields hiện tại.
- Tính lại tổng từ array.
- Dùng `$map` để biến đổi nhiều phần tử theo biểu thức.
- Dùng `$filter` để giữ/xóa phần tử theo logic phức tạp.
- Tránh read-modify-save trên cùng document.

### 30.2. Khi không cần

Để `inc` một quantity, `set` status hoặc `pull` một item, update operators thông thường dễ đọc/đo hơn.

### 30.3. Atomicity vẫn ở cấp document

Một update pipeline trên một document vẫn là single-document atomic write; không có nghĩa nhiều documents hoặc external payments cùng transaction.

---

## 31. Transaction cho nhiều documents

Nếu một lần đặt hàng phải:

1. Trừ tồn kho trong `inventory`.
2. Tạo `orders`.
3. Ghi `outboxEvents`.

và nghiệp vụ đòi all-or-nothing trong MongoDB, cần cân nhắc **multi-document transaction** trên deployment hỗ trợ.

### 31.1. MongoTransactionManager

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {

    @Bean
    MongoTransactionManager transactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

### 31.2. Transaction boundary

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void reserveAndCreate(
        String tenantId,
        String sku,
        int quantity) {

    // Conditional inventory decrement.
    // Insert order.
    // Insert outbox event.
    // Nếu thất bại, transaction được rollback
    // theo semantics MongoDB/Spring đã cấu hình.
}
~~~

Đây là pseudo-service, chưa đủ logic chống oversell/retry. Cần check modified count, abort transaction khi không đủ stock, và xử lý transient transaction errors/unknown commit result.

### 31.3. Không dùng transaction cho mọi bulk lớn

Transaction tăng chi phí và có giới hạn thời gian/tài nguyên. Hàng triệu backfill writes có thể phù hợp với idempotent batches + reconciliation hơn một transaction khổng lồ.

### 31.4. External systems

MongoDB transaction không tự làm atomic với payment provider, Kafka hoặc email gateway. Dùng outbox, idempotency và compensating actions.

---

## 32. Indexes cho conditional CRUD và array queries

### 32.1. Query theo tenant/status/time

~~~javascript
db.orders.createIndex({
  tenant_id: 1,
  status: 1,
  created_at: 1
});
~~~

Hữu ích cho job expire orders theo ngày khi query shape phù hợp.

### 32.2. Unique business identity

~~~javascript
db.orders.createIndex(
  { tenant_id: 1, external_id: 1 },
  { unique: true }
);
~~~

Nếu một số documents chưa có external_id, xem xét partial index/schema policy để uniqueness phản ánh đúng nghiệp vụ.

### 32.3. Multikey array index

~~~javascript
db.orders.createIndex({
  tenant_id: 1,
  "items.sku": 1
});
~~~

Có thể giúp tìm documents chứa SKU. Nhưng nó không tự thay đổi `arrayFilters` semantics hoặc đảm bảo mỗi SKU unique trong array.

### 32.4. Query theo `_id`

MongoDB đã có unique `_id` index. Khi filter theo ID và tenant, thường không cần compound index mới chỉ cho query một document, nhưng tenant vẫn là bắt buộc để kiểm tra quyền.

### 32.5. Chi phí write

Indexes tăng chi phí insert/update/delete và storage. Không tạo index trên mọi update field một cách máy móc.

### 32.6. Explain

~~~javascript
db.orders.find({
  tenant_id: "tenant-a",
  status: "PENDING"
}).explain("executionStats");
~~~

Quan sát keys/docs examined, `IXSCAN`/`COLLSCAN` và thời gian. Dataset lab chỉ có vài documents không phản ánh production.

---

## 33. Bulk jobs, checkpoints và retry strategy

Một sync job nên có:

~~~text
Read source page
      |
Build operations (max batch size)
      |
Execute bulk
      |
Classify write errors and partial results
      |
Reconcile by business keys
      |
Persist checkpoint
      |
Next page
~~~

### 33.1. Vì sao checkpoint sau khi write?

Checkpoint trước khi bulk có thể khiến crash làm mất dữ liệu chưa ghi. Checkpoint sau bulk có thể khiến retry lặp; vì thế cần idempotency/unique keys/version.

### 33.2. Không retry `$inc` mù

Nếu một phần increments đã thành công, retry toàn batch có thể nhân đôi counts. Dùng source version, contribution ledger hoặc expected state and reconciliation.

### 33.3. Giới hạn tài nguyên

Batch quá lớn làm tăng heap, network, lock contention và ảnh hưởng p95 latency của online API. Điều chỉnh batch size/concurrency dựa trên metrics thực tế.

### 33.4. Lỗi cần phân loại

- Duplicate key.
- Schema validation.
- Bad update path/arrayFilter.
- Write concern.
- Network timeout.
- Permission/authorization.
- Optimistic conflict.
- Document size limit.
- Transient topology change.

Không phải lỗi nào cũng có thể retry ngay.

---

## 34. Observability khi cập nhật dữ liệu

### 34.1. UpdateResult

~~~java
boolean acknowledged = result.wasAcknowledged();

if (acknowledged) {
    System.out.println(result.getMatchedCount());
    System.out.println(result.getModifiedCount());
    System.out.println(result.getUpsertedId());
}
~~~

### 34.2. BulkWriteResult

~~~java
BulkWriteResult result = bulk.execute();

System.out.println(result.getInsertedCount());
System.out.println(result.getMatchedCount());
System.out.println(result.getModifiedCount());
System.out.println(result.getDeletedCount());
System.out.println(result.getUpserts());
~~~

### 34.3. Matched/modified không phải số array elements

Một order match có 10 elements thay đổi trong cùng update vẫn tính là **một modified document**.

### 34.4. Theo dõi SLO và lỗi

| Metric gợi ý | Mục đích |
|---|---|
| `conditional_update_conflict_total` | Query không còn match version/status |
| `bulk_batch_size` | Kích thước lô |
| `bulk_partial_failure_total` | Partial writes |
| `bulk_duplicate_key_total` | Unique conflict |
| `mongo_write_latency_p95` | Độ trễ write |
| `array_update_noop_total` | Không có element phù hợp |
| `mongo_write_concern_error_total` | Lỗi xác nhận durability |
| `reconciliation_backlog` | Những records cần sửa/replay |

Tên metrics là ví dụ của application instrumentation, không phải tên metrics mặc định của MongoDB.

---

## 35. Troubleshooting thường gặp

### 35.1. Positional operator không tìm được element

Nguyên nhân: query không có array condition nhưng update dùng `items.$.quantity`. Thêm matching array predicate hoặc chuyển sang filtered positional operator với arrayFilters.

### 35.2. Array field missing/non-array

`$[]` hoặc `$[line]` gặp field không tồn tại/không phải array có thể lỗi. Cần schema migration/validation hoặc xử lý điều kiện rõ trước khi sửa.

### 35.3. No-op khi arrayFilter không match

`matchedCount=1` và `modifiedCount=0` có thể là document đã match nhưng không phần tử nào thỏa `line.sku`, hoặc giá trị mới giống cũ.

### 35.4. Sai tên BSON trong arrayFilters

`line.unitPriceMinor` có thể không match vì document lưu `line.unit_price_minor`. `filterArray` không thực hiện mapping bổ sung.

### 35.5. `$[]` vô tình sửa quá nhiều

Document match `items.sku=A` không có nghĩa `$[]` chỉ sửa A. Dùng `$[id]` nếu cần select elements.

### 35.6. `$pull` xóa tất cả matching elements

Nếu duplicated SKU xuất hiện, mọi matching elements có thể biến mất. Dùng subdocument ID khi cần cập nhật/xóa chính xác một line.

### 35.7. Bulk không dừng khi lỗi

`UNORDERED` có thể tiếp tục những operations khác. Cần đọc errors và partial result; không coi batch failure là rollback.

### 35.8. Upsert tạo record không mong muốn

Nếu filter có status/stock condition không match, upsert sẽ tạo document mới. Conditional business updates nên dùng updateFirst không upsert.

### 35.9. Optimistic locking không như mong đợi

Chỉ có `@Version` không tự biến mọi `updateFirst` thành CAS. Thêm expected version predicate hoặc dùng save path hỗ trợ, kiểm tra acknowledged writes.

### 35.10. Projection rồi save mất data

Entity load một phần không có fields khác, `save` có thể thay toàn document. Dùng partial update hoặc DTO.

### 35.11. Bad field names

`@Field("tenant_id")` nhưng Query raw dùng `tenantId` không qua mapping có thể không match. Xem raw BSON và kiểm tra pipeline/driver command nếu cần.

### 35.12. Performance chậm sau khi thêm index

Nhiều indexes tăng write amplification và storage. Chọn index theo filter/sort thực tế và đo với explain/load tests.

---

## 36. Lỗi thiết kế phổ biến

1. **“`save` là PATCH.”** Có thể replace toàn document.
2. **“Đọc rồi ghi bảo đảm điều kiện vẫn đúng.”** Có race condition.
3. **“`updateFirst` chọn ổn định một record bất kỳ.”** Không dùng natural order cho nghiệp vụ.
4. **“`updateMulti` là một transaction lớn.”** Không.
5. **“`upsert` tự chống duplicate ở mọi tình huống.”** Cần unique index.
6. **“`$inc` retry tự an toàn.”** Có thể double-count.
7. **“Bulk ordered là all-or-nothing.”** Không.
8. **“Unordered bulk chạy đúng thứ tự.”** Không bảo đảm.
9. **“Bulk tự mang mọi @Version callbacks.”** Không.
10. **“`modifiedCount=0` nghĩa là không tồn tại.”** Có thể no-op.
11. **“`$` cập nhật mọi items trùng SKU.”** Chỉ first matching.
12. **“`$[]` chỉ cập nhật items thỏa array condition trong Query.”** Sai.
13. **“`$[line]` không cần arrayFilters.”** Sai.
14. **“`filterArray` tự map @Field names.”** Không.
15. **“Dotted predicates luôn thuộc một item.”** Cần `$elemMatch` khi có nhiều điều kiện same-element.
16. **“`$push` không tạo duplicates.”** Có thể.
17. **“`$addToSet` unique theo SKU của subdocument.”** Không; equality toàn value.
18. **“`$pull` chỉ xóa phần tử đầu.”** Không.
19. **“Xóa line item không ảnh hưởng order total.”** Có thể phá invariant.
20. **“Chỉ ID là đủ trong multi-tenant update.”** Cần tenant authorization.
21. **“Network timeout chứng minh write fail.”** Không.
22. **“Có index là mọi array update nhanh.”** Phải xét query plan/workload.
23. **“Transaction MongoDB atomic với payment gateway.”** Không.
24. **“Một request cập nhật thành công là dữ liệu đúng nghiệp vụ.”** Cần preconditions và validation.
25. **“Kết quả modified documents là số phần tử mảng được đổi.”** Không.

---

## 37. Checklist trước khi triển khai

### 37.1. Query và mapping

- [ ] Có tenant/authorization predicates.
- [ ] Dùng `Order.class` với `@Field` mapping phù hợp.
- [ ] Raw collection name APIs dùng tên BSON thực.
- [ ] Query có điều kiện trạng thái/version tại lúc ghi.
- [ ] Có unique keys cho upsert.
- [ ] Sort/limit không làm sai nghiệp vụ.

### 37.2. Atomicity và concurrency

- [ ] Single-document invariant dùng conditional update.
- [ ] Kiểm tra matchedCount/modifiedCount.
- [ ] Có optimistic locking/version nếu cần.
- [ ] Không read-modify-save thiếu bảo vệ.
- [ ] Multi-document invariants dùng transaction/workflow phù hợp.
- [ ] HTTP/event retries có idempotency policy.

### 37.3. Bulk

- [ ] Chọn ORDERED/UNORDERED theo dependencies.
- [ ] Batch size/concurrency có giới hạn.
- [ ] Partial success được xử lý.
- [ ] Không retry increments/push mù.
- [ ] Checkpoint và reconciliation.
- [ ] Auditing/version behavior được xác minh.
- [ ] Có metrics và alerts.

### 37.4. Mảng

- [ ] Chọn đúng `$`/`$[]`/`$[id]`.
- [ ] Có query array predicate khi dùng `$`.
- [ ] Có `$elemMatch` khi cần same-element checks.
- [ ] ArrayFilters dùng đúng BSON field names.
- [ ] Xử lý arrays missing/empty.
- [ ] Không sửa tất cả elements ngoài ý muốn.
- [ ] Xác định duplicate SKU/subdocument behavior.
- [ ] Cập nhật các totals/invariants liên quan.
- [ ] Tránh unbounded arrays và BSON 16 MiB limit.

---

## 38. Bài tập thực hành

### Bài tập 1 — CRUD cơ bản

Tạo `Order` có ID, tenantId, status. Thử `insert`, `findById`, `findOne`, `save`; quan sát khi ID trùng.

### Bài tập 2 — Query có điều kiện

Tìm 20 orders PENDING mới nhất của tenant-a, sort theo `createdAt` và `_id`.

### Bài tập 3 — Projection

Chỉ đọc id/status/totalMinor rồi giải thích vì sao entity này không nên dùng `save` để thay cả order.

### Bài tập 4 — Tồn kho

Stock SKU-A=1, hai clients cùng trừ 1. Dùng conditional update với `available>=1` và chứng minh không oversell.

### Bài tập 5 — Transition

Chuyển PENDING sang PAID, chỉ khi tenant/id/status khớp. Phân biệt matched=0 và modified=0.

### Bài tập 6 — UpdateMulti

Đổi orders PENDING cũ thành EXPIRED, chỉ của tenant-a. Quan sát count và retry.

### Bài tập 7 — Upsert

Đồng bộ ERP order theo tenantId+externalId và unique index; mô phỏng hai writers insert đồng thời.

### Bài tập 8 — FindAndModify

Claim job READY cũ nhất bằng sorted Query và returnNew(true).

### Bài tập 9 — @Version

Hai threads cùng load version=1, sau đó save khác nhau. Phân tích optimistic conflict và acknowledged write.

### Bài tập 10 — Bulk ORDERED

Tạo bulk có một duplicate key giữa batch. Quan sát các operations trước/sau lỗi.

### Bài tập 11 — Bulk UNORDERED

Lặp lại bài 10 với unordered và xử lý partial result.

### Bài tập 12 — Bulk retry

Job tăng counter bằng `$inc` nhận timeout không rõ kết quả. Đề xuất idempotency key/reconciliation.

### Bài tập 13 — Positional $

Mảng có hai SKU-A. Dùng `items.$.quantity` tăng phần tử đầu.

### Bài tập 14 — elemMatch

Một item SKU-A qty=1, item B qty=8. So sánh dotted query với `$elemMatch` SKU-A qty≥5.

### Bài tập 15 — All positional

Dùng `items.$[].gift=true`, kiểm chứng mọi phần tử đổi dù query lọc theo SKU-A.

### Bài tập 16 — Filtered positional

Dùng `Update.filterArray` để tăng qty cho mọi SKU-A mà không đổi SKU-B.

### Bài tập 17 — BSON mapping

Java `unitPriceMinor` mapping BSON `unit_price_minor`. Viết array filter đúng trên `line.unit_price_minor`.

### Bài tập 18 — Nested arrays

Cập nhật warehouse HCM, bin SKU-A, chỉ khi available≥1 bằng hai identifiers.

### Bài tập 19 — Missing arrays

Thử positional update trên document thiếu `items`; phân tích error/schema validation.

### Bài tập 20 — Push vs addToSet

Thêm tag priority hai lần với từng operator, so sánh array.

### Bài tập 21 — Pull

Xóa items SKU-B, tính lại totalMinor đúng.

### Bài tập 22 — Transaction

Thiết kế service trừ inventory, insert order, insert outbox trong MongoTransactionManager; mô tả lỗi giữa chừng.

### Bài tập 23 — Multi-tenant security

Thiết kế endpoint chỉ được đổi status của order thuộc trustedTenantId; không cho client tự đặt tenantId.

### Bài tập 24 — Index

Tạo index tenant/status/created_at và dùng explain so sánh trên dataset đủ lớn.

### Bài tập 25 — Metrics

Theo dõi matched/modified/upserted/deleted và bulk partial failures; chọn cảnh báo khi conditional conflict tăng.

---

## 39. Câu hỏi ôn tập

1. MongoTemplate khác MongoRepository thế nào?
2. Khi nào nên dùng MongoTemplate thay repository method?
3. Mapping `@Field` ảnh hưởng Query ra sao?
4. Khi nào nên dùng tên BSON thực trong query?
5. Vì sao tenant filter quan trọng?
6. `insert` và `save` khác nhau ở đâu?
7. Vì sao `save` không nên dùng cho partial PATCH?
8. `findOne` có trả bản ghi “đầu tiên” ổn định không?
9. `Query/Criteria` diễn đạt những điều kiện gì?
10. `$set` khác `$unset` thế nào?
11. `$inc` có atomic ở cấp document không?
12. Vì sao retry `$inc` có thể double-count?
13. `$setOnInsert` chỉ có tác dụng khi nào?
14. `updateFirst` sửa mấy documents?
15. `updateMulti` có atomic toàn bộ collection không?
16. `matchedCount` khác `modifiedCount` thế nào?
17. Matched=1, modified=0 nghĩa là gì?
18. Vì sao upsert cần unique business key?
19. Upsert theo stock condition có rủi ro gì?
20. `findAndModify` có thể trả document sau update không?
21. Vì sao find rồi update không đồng nghĩa findAndModify?
22. `@Version` tự thêm CAS cho mọi updateFirst không?
23. Khi nào cần expected version filter?
24. Bulk ORDERED và UNORDERED khác nhau thế nào?
25. Bulk có thay transaction không?
26. Bulk gặp partial success nên retry thế nào?
27. Vì sao bulk không đảm bảo auditing/optimistic callbacks per entity?
28. `$` sửa bao nhiêu phần tử matching?
29. `$[]` sửa những phần tử nào?
30. `$[line]` cần arrayFilters không?
31. `$elemMatch` đảm bảo điều gì?
32. `Update.filterArray` có map `@Field` trong filter không?
33. Query document selection khác array element selection thế nào?
34. Upsert với positional `$` có hạn chế gì?
35. Nested arrays có thể dùng nhiều identifiers không?
36. `$push` khác `$addToSet` ở điểm nào?
37. `$addToSet` có unique theo subdocument.sku không?
38. `$pull` xóa một hay mọi matching elements?
39. Vì sao array update có thể làm order total sai?
40. Khi nào nên dùng aggregation update pipeline?
41. MongoTransactionManager giải quyết vấn đề gì?
42. MongoDB transaction có bao phủ payment gateway không?
43. Unknown outcome khi timeout nghĩa là gì?
44. Tại sao phải kiểm tra BSON field names?
45. Index multikey có làm arrayFilters tự nhanh không?
46. Bulk checkpoint cần lưu trước hay sau và vì sao?
47. Vì sao BSON array quá lớn nguy hiểm?
48. Các metrics nào giúp phát hiện CAS conflicts?
49. Vì sao test trên 3 documents chưa đủ kết luận performance?
50. Khi nào một update “thành công” ở database vẫn sai về nghiệp vụ?

---

## 40. Tổng kết

**MongoTemplate** cho phép Spring Data MongoDB diễn đạt những writes cần điều kiện, cập nhật một phần entity và thao tác hàng loạt mà repository CRUD thông thường không tiện bằng.

Ba nhóm kiến thức phải phân biệt rõ:

1. **Conditional CRUD**: `Query`/`Criteria` quy định precondition ngay lúc ghi; `Update` thực hiện toán tử atomic trên document; `updateFirst`/`updateMulti`/`upsert`/`findAndModify` có semantics khác nhau.
2. **Bulk**: `BulkOperations` tối ưu nhiều write models nhưng không mặc nhiên có all-or-nothing atomicity; cần xử lý ordered/unordered, partial success, idempotent retries và checkpoint.
3. **Arrays**: `$` chọn first matching element, `$[]` chọn mọi phần tử, `$[identifier]` với `arrayFilters` chọn những phần tử phù hợp. `$elemMatch` có vai trò khi nhiều predicates phải thuộc cùng một element.

Các nguyên tắc vận hành:

- **Đừng đọc rồi save cả entity** khi update một field có concurrency.
- **`@Version` không tự biến mọi template update thành CAS**; điều kiện version phải được thiết kế.
- **Bulk không thay transaction** và các external side effects không tự trở thành atomic.
- **Array filters của Spring Data không được map bổ sung**, nên cần dùng đúng BSON field names.
- **Matched/modified counts là số documents**, không phải số phần tử mảng.
- **Tenant filter, unique indexes, business invariants, retries và observability** là một phần của tính đúng, không chỉ là chi tiết performance.

Một thao tác update đáng tin phải **sửa đúng dữ liệu, trong đúng trạng thái được phép, chịu được concurrent requests và khôi phục/retry an toàn**.

## Tài liệu tham khảo

- [Spring Data MongoDB — MongoTemplate CRUD Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
- [Spring Data MongoDB — Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html)
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html)
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
- [Spring Data MongoDB — BulkOperations API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/BulkOperations.html)
- [Spring Data MongoDB — Update API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Update.html)
- [Spring Data MongoDB — MongoTemplate API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoTemplate.html)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/)
- [MongoDB Manual — Update Operators](https://www.mongodb.com/docs/manual/reference/operator/update/)
- [MongoDB Manual — Positional $](https://www.mongodb.com/docs/manual/reference/operator/update/positional/)
- [MongoDB Manual — All Positional $[]](https://www.mongodb.com/docs/manual/reference/operator/update/positional-all/)
- [MongoDB Manual — Filtered Positional $[identifier]](https://www.mongodb.com/docs/manual/reference/operator/update/positional-filtered/)
- [MongoDB Manual — $elemMatch](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/)
- [MongoDB Manual — $push](https://www.mongodb.com/docs/manual/reference/operator/update/push/)
- [MongoDB Manual — $addToSet](https://www.mongodb.com/docs/manual/reference/operator/update/addToSet/)
- [MongoDB Manual — $pull](https://www.mongodb.com/docs/manual/reference/operator/update/pull/)
- [MongoDB Manual — Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/)
- [MongoDB Java Sync Driver — Bulk Write Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/bulk/)
