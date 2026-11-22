# Array filters với $[identifier] và filterArray

## 1. Mục tiêu và vấn đề nghiệp vụ

Một đơn hàng MongoDB có thể chứa mảng `items` gồm nhiều dòng sản phẩm. Khi nhân viên điều chỉnh số lượng của SKU `BOOK-A`, ứng dụng cần sửa **đúng các phần tử phù hợp**, không thay cả mảng, không ảnh hưởng SKU khác và không dựa vào một chỉ số array cố định. MongoDB cung cấp **filtered positional operator** `$[identifier]` kết hợp với tùy chọn **`arrayFilters`** để làm việc này.

Trong Spring Data MongoDB, lớp `Update` có các phương thức `filterArray(...)` giúp đưa điều kiện chọn phần tử vào lệnh ghi qua `MongoOperations`/`MongoTemplate`. Đây là nội dung thuộc chương **Thao tác array** của module **SPRING_DATA_MONGODB**: sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác qua template hoặc repository; thiết kế query, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.

Sau bài học, bạn có thể:

1. Phân biệt `$`, `$[]`, `$[identifier]` và `$elemMatch` theo **chức năng đọc/lọc/cập nhật**.
2. Viết `updateOne`/`updateMany` với `arrayFilters` để chọn đúng phần tử trong mảng document.
3. Dùng `Update.filterArray(...)` của Spring Data và xác định chỗ nào dùng **tên property Java**, chỗ nào phải dùng **tên field BSON**.
4. Xử lý nhiều phần tử phù hợp, nhiều identifier, array lồng nhau và document không có mảng hợp lệ.
5. Phân tích `matchedCount`/`modifiedCount`, bảo đảm tenant, trạng thái và concurrency trong filter ghi.
6. Viết integration test và đánh giá index, lỗi cú pháp, khả năng hỗ trợ của phiên bản MongoDB.

**Điểm mấu chốt:** Filter trong `Query` chọn **document nào** được cập nhật; filter trong `arrayFilters` chọn **phần tử nào bên trong array** của document đó. Hai tầng điều kiện không thể dùng thay thế cho nhau.

## 2. Chuẩn bị dữ liệu mẫu

### 2.1. Document BSON

Ví dụ trên collection thử nghiệm `orders`:

```javascript
db.orders.insertMany([
  {
    _id: "ord-001",
    tenantId: "tenant-a",
    status: "READY_TO_SHIP",
    items: [
      { sku_code: "BOOK-A", quantity: 1, state: "NEW", priceVnd: NumberLong("90000") },
      { sku_code: "BOOK-B", quantity: 4, state: "NEW", priceVnd: NumberLong("60000") }
    ],
    updatedAt: ISODate("2026-11-19T08:00:00Z")
  },
  {
    _id: "ord-002",
    tenantId: "tenant-a",
    status: "READY_TO_SHIP",
    items: [
      { sku_code: "BOOK-A", quantity: 2, state: "NEW", priceVnd: NumberLong("90000") },
      { sku_code: "BOOK-A", quantity: 3, state: "NEW", priceVnd: NumberLong("90000") },
      { sku_code: "BOOK-C", quantity: 1, state: "NEW", priceVnd: NumberLong("75000") }
    ],
    updatedAt: ISODate("2026-11-19T09:00:00Z")
  },
  {
    _id: "ord-003",
    tenantId: "tenant-a",
    status: "CANCELLED",
    items: [],
    updatedAt: ISODate("2026-11-19T10:00:00Z")
  },
  {
    _id: "ord-004",
    tenantId: "tenant-b",
    status: "READY_TO_SHIP",
    items: [
      { sku_code: "BOOK-A", quantity: 7, state: "NEW", priceVnd: NumberLong("90000") }
    ],
    updatedAt: ISODate("2026-11-19T11:00:00Z")
  }
]);
```

Các ID và giá trị này chỉ dành cho database thực hành. Tránh chạy `insertMany` nguyên trạng vào dữ liệu thật hoặc collection đã có ID trùng.

```text
ord-001  (tenant-a, READY_TO_SHIP)
└── items
    ├── [0] sku=BOOK-A, quantity=1, state=NEW
    └── [1] sku=BOOK-B, quantity=4, state=NEW

ord-002  (tenant-a, READY_TO_SHIP)
└── items
    ├── [0] sku=BOOK-A, quantity=2, state=NEW
    ├── [1] sku=BOOK-A, quantity=3, state=NEW
    └── [2] sku=BOOK-C, quantity=1, state=NEW
```

Chủ ý đặt **hai dòng BOOK-A trong cùng `ord-002`** để kiểm tra một điều quan trọng: `$[identifier]` có thể sửa **nhiều phần tử** thỏa filter, không phải luôn chỉ một phần tử.

### 2.2. Model Java với @Field đổi tên BSON

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record OrderDocument(
    @MongoId(FieldType.STRING) String id,
    String tenantId,
    String status,
    List<OrderLine> items,
    Instant updatedAt
) {}

record OrderLine(
    @Field("sku_code") String sku,
    int quantity,
    String state,
    long priceVnd
) {}
```

| Khái niệm | Tên property Java | Field BSON |
| --- | --- | --- |
| Định danh đơn | `id` | `_id` |
| Mảng dòng hàng | `items` | `items` |
| SKU của dòng | `items.sku` | `items.sku_code` |
| Số lượng của dòng | `items.quantity` | `items.quantity` |
| Trạng thái của dòng | `items.state` | `items.state` |

Mục đích của `@Field("sku_code")` là tạo ví dụ thực tế về một lỗi dễ mắc: phần `arrayFilters` có quy tắc mapping khác với `Query` gắn domain entity.

## 3. Phân biệt bốn cú pháp thường bị nhầm

| Cú pháp | Dùng ở đâu? | Ý nghĩa |
| --- | --- | --- |
| `$elemMatch` | Query filter hoặc projection phù hợp | Yêu cầu **cùng một phần tử** của array thỏa nhiều điều kiện |
| `$` | Đường dẫn update positional | Tham chiếu phần tử đầu tiên phù hợp điều kiện array của query trong trường hợp hỗ trợ |
| `$[]` | Đường dẫn update all positional | Cập nhật **mọi phần tử** của array được nhắm tới |
| `$[line]` | Đường dẫn update filtered positional | Cập nhật **mọi phần tử thỏa `arrayFilters` của `line`** |

Ví dụ cập nhật trường `quantity`:

```javascript
// (A) Một phần tử được xác định theo positional $ và filter của query.
db.orders.updateOne(
  { _id: "ord-001", "items.sku_code": "BOOK-A" },
  { $set: { "items.$.quantity": 5 } }
);

// (B) Mọi phần tử của items, bất kể SKU.
db.orders.updateOne(
  { _id: "ord-001" },
  { $set: { "items.$[].quantity": 5 } }
);

// (C) Mọi phần tử có SKU BOOK-A.
db.orders.updateOne(
  { _id: "ord-001" },
  { $set: { "items.$[line].quantity": 5 } },
  { arrayFilters: [{ "line.sku_code": "BOOK-A" }] }
);
```

Ba lệnh minh họa **ba lựa chọn thay thế**, không phải một chuỗi nên chạy liên tiếp nếu bạn muốn quan sát kết quả riêng của từng toán tử. Hãy reset fixture hoặc chạy từng lệnh trên bản sao độc lập.

### 3.1. $elemMatch không tự cập nhật

```javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku_code: "BOOK-A",
      quantity: { $gte: 2 }
    }
  }
});
```

Lệnh này **chỉ đọc/lọc document**. Nó không sửa dòng hàng nào. Khi cần update các dòng cùng thỏa điều kiện, bạn đưa predicate đó vào `arrayFilters` rồi đặt `$[line]` trong update path.

### 3.2. Vì sao $[] quá rộng?

Nếu yêu cầu nghiệp vụ là «chỉ cập nhật BOOK-A», `"items.$[].quantity"` có thể sửa cả `BOOK-B` và `BOOK-C`. Nó chỉ đúng khi muốn áp thay đổi cho **tất cả** phần tử, chẳng hạn đặt một cờ chung. Đừng chọn `$[]` chỉ vì cú pháp ngắn hơn.

### 3.3. $ không phải $[line]

Filtered positional `$[line]` không có nghĩa «chọn phần tử đầu tiên tên line». `line` là **nhãn do lập trình viên đặt**, được ràng buộc với điều kiện trong `arrayFilters`; tất cả phần tử thỏa điều kiện có thể bị ảnh hưởng trong document được chọn.

## 4. Cấu trúc đầy đủ của $[identifier] và arrayFilters

Một lệnh điển hình có ba phần:

```javascript
db.orders.updateOne(
  // 1. Chọn document.
  {
    _id: "ord-002",
    tenantId: "tenant-a",
    status: "READY_TO_SHIP"
  },
  // 2. Mô tả field sẽ sửa trong từng phần tử phù hợp.
  {
    $set: {
      "items.$[line].quantity": 6
    }
  },
  // 3. Chọn phần tử nào ứng với identifier "line".
  {
    arrayFilters: [
      { "line.sku_code": "BOOK-A" }
    ]
  }
);
```

Kết quả của `ord-002`:

```javascript
items: [
  { sku_code: "BOOK-A", quantity: 6, state: "NEW", priceVnd: NumberLong("90000") },
  { sku_code: "BOOK-A", quantity: 6, state: "NEW", priceVnd: NumberLong("90000") },
  { sku_code: "BOOK-C", quantity: 1, state: "NEW", priceVnd: NumberLong("75000") }
]
```

Lệnh thay **cả hai phần tử BOOK-A**, không thay `BOOK-C`. Với một update trên một document, các thay đổi trong document được xử lý nguyên tử ở tầng MongoDB.

### 4.1. Identifier là biến của câu lệnh update

Trong đường dẫn `"items.$[line].quantity"`, `line` không phải field trong BSON. Nó là tên biến liên kết với object filter có path `line.sku_code`.

Một identifier hợp lệ phải bắt đầu bằng **chữ thường** và chỉ chứa ký tự chữ/số theo quy tắc của MongoDB; nên đặt tên đơn giản như `line`, `item`, `row2`. Tránh nhầm với field `sku_code`, và tránh identifier có dấu, dấu cách hoặc dấu gạch nối.

Mỗi identifier khác nhau dùng trong update phải có điều kiện array filter tương ứng. Không khai báo hai document filter riêng lẻ cho cùng một identifier rồi mong server tự gộp: kết hợp các điều kiện trong **một** filter document.

### 4.2. Một filter document có nhiều predicate

```javascript
db.orders.updateOne(
  { _id: "ord-002", tenantId: "tenant-a" },
  {
    $set: { "items.$[line].state": "CHECKED" }
  },
  {
    arrayFilters: [
      {
        "line.sku_code": "BOOK-A",
        "line.quantity": { $gte: 3 }
      }
    ]
  }
);
```

Ở `ord-002` ban đầu, chỉ dòng `BOOK-A` có quantity 3 thỏa cả hai điều kiện; dòng BOOK-A quantity 2 không thỏa. Nếu trước đó bạn đã chạy ví dụ đổi quantity thành 6, kết quả khác. Các ví dụ độc lập cần seed lại dữ liệu trước khi so sánh.

### 4.3. Quy tắc và giới hạn cú pháp

- `$[line]` phải có filter cho `line` trong `arrayFilters`; nếu thiếu, server có thể báo lỗi không tìm thấy định nghĩa identifier.
- Identifier không phải tên của field array; path bên trái vẫn phải là `items` hoặc đường dẫn BSON thực.
- Không dùng các toán tử truy vấn bị hạn chế trong `arrayFilters` như `$expr`, `$text`, `$where`.
- Mỗi identifier có một filter document; có thể dùng `$and`/`$or` hợp lệ bên trong filter đó khi cần.
- Filter ngoài của `updateOne` và array filters có **mục đích riêng**; identifier không tự gắn điều kiện tenant hay kiểm tra trạng thái nghiệp vụ.

Khi dùng MongoDB có phiên bản cũ, hãy kiểm tra hỗ trợ array filters: tính năng filtered positional update được đưa vào MongoDB **3.6**. Trong các dự án dùng Spring Data hoặc driver đời cũ, convenience method `Update.filterArray(...)` có thể chưa có; đừng giả định server hỗ trợ là API Java nào cũng có.

## 5. Document filter và element filter phải được thiết kế cùng nhau

Một lỗi phổ biến là chỉ quan tâm `arrayFilters` rồi bỏ qua phạm vi document.

### 5.1. Query chọn đơn, arrayFilters chọn dòng

```javascript
db.orders.updateMany(
  {
    tenantId: "tenant-a",
    status: "READY_TO_SHIP"
  },
  {
    $set: { "items.$[line].state": "RESERVED" }
  },
  {
    arrayFilters: [
      { "line.sku_code": "BOOK-A" }
    ]
  }
);
```

Lệnh này chọn những đơn của `tenant-a` đang `READY_TO_SHIP`, rồi đặt trạng thái các dòng BOOK-A trong **mỗi đơn phù hợp**. Nó không sửa `ord-004` của tenant-b dù `ord-004` cũng chứa BOOK-A.

Nếu filter document quá rộng:

```javascript
// KHÔNG PHÙ HỢP cho thao tác chỉ được tác động một tenant.
db.orders.updateMany(
  { status: "READY_TO_SHIP" },
  { $set: { "items.$[line].state": "RESERVED" } },
  { arrayFilters: [{ "line.sku_code": "BOOK-A" }] }
);
```

arrayFilters **không bảo vệ được ranh giới tenant**. Authorization và invariant phải xuất hiện ở tầng application service và điều kiện chọn document.

### 5.2. MatchedCount không phải số phần tử array đã sửa

Khi update `ord-002` có hai dòng BOOK-A:

```javascript
const result = db.orders.updateOne(
  { _id: "ord-002", tenantId: "tenant-a" },
  { $set: { "items.$[line].state": "CHECKED" } },
  { arrayFilters: [{ "line.sku_code": "BOOK-A" }] }
);

printjson(result);
```

Thông thường `matchedCount` là **số document** khớp filter, còn `modifiedCount` là **số document thực sự thay đổi**. Nếu hai dòng trong cùng document thay đổi, `modifiedCount` vẫn có thể chỉ bằng 1. Kết quả ghi không cung cấp số lượng phần tử array đã sửa.

Ngay cả khi document khớp nhưng không có dòng nào đáp ứng array filter, thao tác có thể trả `matchedCount=1` và `modifiedCount=0`. Vì thế:

- `matchedCount=0`: không có document khớp filter ngoài.
- `matchedCount=1`, `modifiedCount=0`: có document nhưng update có thể no-op, không có element match, hoặc giá trị mới giống cũ.
- `modifiedCount=1`: có thay đổi trong document, không phải chính xác một array element.

Để cần số phần tử cụ thể cho báo cáo, hãy thiết kế đọc trước/sau hoặc phép tính chuyên biệt và xác định yêu cầu nhất quán/concurrency; không suy luận từ `UpdateResult.getModifiedCount()`.

### 5.3. Khi cần xác nhận có dòng phù hợp ngay trong query ngoài

Có thể thêm `$elemMatch` để filter ngoài chỉ khớp những document có một phần tử cần cập nhật:

```javascript
db.orders.updateOne(
  {
    _id: "ord-002",
    tenantId: "tenant-a",
    items: { $elemMatch: { sku_code: "BOOK-A", state: "NEW" } }
  },
  { $set: { "items.$[line].state": "RESERVED" } },
  {
    arrayFilters: [
      { "line.sku_code": "BOOK-A", "line.state": "NEW" }
    ]
  }
);
```

Filter ngoài quyết định document có đạt điều kiện bắt buộc hay không; array filter vẫn cần đầy đủ điều kiện để sửa đúng dòng. Nếu có phần tử BOOK-A `NEW` và phần tử BOOK-A `DONE` trong cùng đơn, không được chỉ lọc `sku_code` bên trong rồi vô tình đổi cả dòng DONE.

## 6. Spring Data: Update.filterArray(...) cơ bản

### 6.1. MongoOperations và MongoTemplate

Một ví dụ service dùng `MongoOperations` thay vì phụ thuộc trực tiếp implementation:

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class OrderLineCommandService {
    private final MongoOperations mongo;

    public OrderLineCommandService(MongoOperations mongo) {
        this.mongo = mongo;
    }

    public UpdateResult setQuantityForSku(
        String authenticatedTenantId,
        String orderId,
        String sku,
        int quantity
    ) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || orderId == null || orderId.isBlank()
                || sku == null || sku.isBlank()
                || quantity <= 0) {
            throw new IllegalArgumentException("Invalid input");
        }

        Query query = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(authenticatedTenantId)
                .and("status").is("READY_TO_SHIP")
        );

        Update update = new Update()
            .set("items.$[line].quantity", quantity)
            .filterArray(
                Criteria.where("line.sku_code").is(sku)
            );

        return mongo.updateFirst(query, update, OrderDocument.class);
    }
}
```

`MongoTemplate` thường là implementation cho interface `MongoOperations`. Trong ví dụ, `authenticatedTenantId` phải đến từ context đã xác thực, không được tin một tenantId tùy ý do client gửi.

### 6.2. Vì sao filterArray dùng line.sku_code, không phải line.sku?

Đây là chi tiết dễ sai nhất khi dùng `@Field`. Spring Data hỗ trợ ánh xạ query/update dựa trên metadata của entity, nhưng các **array filter expressions được đưa xuống driver mà không qua cùng cơ chế mapping field/type** như query bình thường.

Do đó:

```java
Update correct = new Update()
    .set("items.$[line].quantity", 5)
    .filterArray(Criteria.where("line.sku_code").is("BOOK-A"));

// DỄ SAI nếu entity chỉ đổi tên Java property sku -> BSON sku_code.
Update wrong = new Update()
    .set("items.$[line].quantity", 5)
    .filterArray(Criteria.where("line.sku").is("BOOK-A"));
```

Trong array filter, `line.sku_code` dùng **tên field lưu thật**. `line` là identifier, không phải Java entity để Spring Data tra metadata `@Field("sku_code")`.

**Quy tắc thực hành:** Ghi và xác nhận **BSON vật lý** trước khi xây arrayFilters, đặc biệt khi có custom converters, enum, ObjectId, UUID, Date, nested aliases hoặc dữ liệu do service khác ghi.

### 6.3. Vai trò của Query mapping so với array filter mapping

Ví dụ:

```java
Query query = Query.query(
    Criteria.where("id").is("ord-001")
        .and("items.sku").is("BOOK-A")
);

Update update = new Update()
    .set("items.$[line].quantity", 5)
    .filterArray(Criteria.where("line.sku_code").is("BOOK-A"));
```

Với `OrderDocument.class`, Spring Data có thể ánh xạ:

| Thành phần | Developer cung cấp | BSON mong đợi |
| --- | --- | --- |
| Query trên ID | `id` | `_id` |
| Query trên SKU | `items.sku` | `items.sku_code` |
| Update path | `items.$[line].quantity` | `items.$[line].quantity` |
| Array filter | `line.sku_code` | `line.sku_code` |

Không coi `Update.toString()` hoặc `Query.getQueryObject()` là bằng chứng đầy đủ về mapping cuối. Dùng integration test hoặc command monitoring để kiểm tra BSON gửi đi trong đúng phiên bản Spring Data đang dùng.

### 6.4. Một filter với nhiều điều kiện

```java
Update update = new Update()
    .set("items.$[line].state", "CHECKED")
    .filterArray(
        Criteria.where("line.sku_code").is("BOOK-A")
            .and("line.quantity").gte(3)
            .and("line.state").is("NEW")
    );
```

Điều kiện trên phải cùng thỏa **trong một array element**. Nếu cần phức tạp hơn, có thể dùng `Criteria` với `andOperator`/`orOperator`, nhưng phải đảm bảo BSON array filter cuối cùng hợp lệ và identifier được định nghĩa đúng.

## 7. Hai cách cung cấp filterArray và việc quản lý biểu thức BSON

Các thế hệ Spring Data MongoDB hỗ trợ filtered positional có thể cung cấp những overload của `Update.filterArray(...)`, bao gồm:

```java
// Khai báo nguyên CriteriaDefinition chứa tên identifier đã gắn prefix.
Update byCriteria = new Update()
    .set("items.$[line].state", "RESERVED")
    .filterArray(
        Criteria.where("line.sku_code").is("BOOK-A")
    );
```

Một overload khác ở các phiên bản hỗ trợ cho phép truyền **identifier và expression** tách nhau; cần kiểm tra chữ ký chính xác và cách serialize expression của bản thư viện đang dùng. Không suy ra rằng một `Criteria.where("sku")` không có prefix sẽ tự được ánh xạ thành `line.sku_code`.

### 7.1. Khi muốn kiểm soát BSON trực tiếp

Với MongoDB Java driver, bạn có thể truyền `arrayFilters` qua `UpdateOptions`:

```java
import java.util.List;
import org.bson.Document;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.UpdateOptions;

MongoCollection<Document> collection =
    database.getCollection("orders");

collection.updateOne(
    new Document("_id", "ord-001")
        .append("tenantId", "tenant-a"),
    new Document("$set",
        new Document("items.$[line].state", "RESERVED")),
    new UpdateOptions().arrayFilters(
        List.of(new Document("line.sku_code", "BOOK-A"))
    )
);
```

Ở đây `database` là đối tượng `MongoDatabase` được cấu hình sẵn trong một ứng dụng; snippet nhằm minh họa tầng driver, không phải hướng dẫn tạo thêm MongoClient cho mỗi request. Driver nhận tên BSON như `_id` và `sku_code`, không hiểu annotation `@Field`.

**Chọn công cụ:** Ưu tiên `MongoOperations` nếu đã dùng Spring Data domain mapping. Chỉ xuống driver API khi có yêu cầu cụ thể, vì bạn phải tự chịu trách nhiệm mapping, validation, session, callbacks và cấu hình consistency liên quan.

## 8. UpdateFirst và UpdateMulti khác nhau ở cấp document

### 8.1. updateFirst

```java
Query query = Query.query(
    Criteria.where("id").is("ord-001")
        .and("tenantId").is("tenant-a")
);

Update update = new Update()
    .set("items.$[line].state", "CHECKED")
    .filterArray(Criteria.where("line.sku_code").is("BOOK-A"));

var result = mongo.updateFirst(query, update, OrderDocument.class);
```

`updateFirst` chọn **tối đa một document**. Trong document đó, `$[line]` vẫn có thể sửa **nhiều array elements**. Đừng nhầm «first document» với «first element».

### 8.2. updateMulti

```java
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("status").is("READY_TO_SHIP")
);

Update update = new Update()
    .set("items.$[line].state", "CHECKED")
    .filterArray(Criteria.where("line.sku_code").is("BOOK-A"));

var result = mongo.updateMulti(query, update, OrderDocument.class);
```

`updateMulti` có thể sửa các phần tử BOOK-A trong **nhiều document** phù hợp. Kết quả `modifiedCount` vẫn được tính **theo document**.

| Câu hỏi | `updateFirst` | `updateMulti` |
| --- | --- | --- |
| Tối đa bao nhiêu document? | Một | Nhiều |
| Mỗi document có thể sửa mấy element? | Nhiều nếu filter khớp nhiều phần tử | Nhiều nếu filter khớp nhiều phần tử |
| Có atomicity xuyên toàn bộ document không? | Trên một document được ghi | Không tự thành transaction chung cho mọi document |
| Có cần ràng buộc tenant/status không? | Có | Có, đặc biệt quan trọng |
| Có thể trả số element được sửa không? | Không trực tiếp từ UpdateResult | Không trực tiếp từ UpdateResult |

### 8.3. Chọn đúng scope cập nhật

Nếu yêu cầu «sửa một dòng hàng của một đơn», nhưng schema cho phép hai dòng có cùng SKU, `$[line]` chỉ lọc SKU sẽ **sửa cả hai**. Để sửa đúng một dòng logic, nên có `lineId` ổn định duy nhất trong mảng, sau đó lọc theo `line.lineId`.

```javascript
db.orders.updateOne(
  { _id: "ord-002", tenantId: "tenant-a" },
  { $set: { "items.$[line].quantity": 5 } },
  { arrayFilters: [{ "line.lineId": "line-002-b" }] }
);
```

Ví dụ này **yêu cầu schema đã có `lineId`**; dataset mục 2 chưa chứa field đó. Nếu cần bảo đảm duy nhất `lineId` bên trong mảng, phải có validation/logic riêng: unique multikey index không nên được hiểu là tự bảo đảm mọi phần tử trong cùng một document đều có một giá trị khác nhau trong mọi thiết kế.

## 9. update với nhiều filtered identifiers

Một đơn giao hàng có thể chứa nhiều nhóm kiện, mỗi kiện có nhiều sản phẩm. Ví dụ một document khác:

```javascript
db.shipments.insertOne({
  _id: "shipment-001",
  tenantId: "tenant-a",
  batches: [
    {
      batchCode: "B1",
      packages: [
        { packageCode: "P1", state: "WAITING" },
        { packageCode: "P2", state: "WAITING" }
      ]
    },
    {
      batchCode: "B2",
      packages: [
        { packageCode: "P1", state: "WAITING" },
        { packageCode: "P3", state: "WAITING" }
      ]
    }
  ]
});
```

Yêu cầu: chỉ cập nhật package P1 thuộc batch B2:

```javascript
db.shipments.updateOne(
  { _id: "shipment-001", tenantId: "tenant-a" },
  {
    $set: {
      "batches.$[batch].packages.$[pkg].state": "READY"
    }
  },
  {
    arrayFilters: [
      { "batch.batchCode": "B2" },
      { "pkg.packageCode": "P1" }
    ]
  }
);
```

Hai identifier độc lập:

- `batch` chọn phần tử trong mảng `batches`.
- `pkg` chọn phần tử trong mảng `packages` bên trong các batch phù hợp.

Lệnh trên không đổi P1 của batch B1. Cách cập nhật nhiều array lồng nhau là một lợi ích quan trọng của filtered positional operator so với việc dựa vào một vị trí array duy nhất.

### 9.1. Spring Data cho hai identifier

```java
Update update = new Update()
    .set("batches.$[batch].packages.$[pkg].state", "READY")
    .filterArray(Criteria.where("batch.batchCode").is("B2"))
    .filterArray(Criteria.where("pkg.packageCode").is("P1"));
```

Snippet này minh họa cấu trúc `Update`. Muốn thực thi với entity `ShipmentDocument.class`, bạn phải định nghĩa đúng entity mapping và query tenant/ID tương ứng; không lấy `OrderDocument.class` của ví dụ trước để cập nhật collection `shipments`.

### 9.2. Phân biệt nhiều identifier với nhiều filter cho cùng identifier

```javascript
// Cách rõ ràng: một filter document cho "line", chứa mọi predicate.
arrayFilters: [
  {
    "line.sku_code": "BOOK-A",
    "line.quantity": { $gte: 2 }
  }
]
```

Không tạo hai mục riêng cùng tên:

```javascript
// Không phải cách khai báo đúng theo mong muốn ghép AND:
arrayFilters: [
  { "line.sku_code": "BOOK-A" },
  { "line.quantity": { $gte: 2 } }
]
```

Ở mẫu sai, identifier `line` bị định nghĩa nhiều lần. Với các predicate cùng identifier, kết hợp chúng trong một object hoặc biểu thức logic hợp lệ.

## 10. Điều kiện số học trên phần tử: tăng, giới hạn và bất biến

### 10.1. $inc trên phần tử phù hợp

Ví dụ tăng quantity của các dòng BOOK-A:

```javascript
db.orders.updateOne(
  { _id: "ord-002", tenantId: "tenant-a" },
  { $inc: { "items.$[line].quantity": 1 } },
  { arrayFilters: [{ "line.sku_code": "BOOK-A" }] }
);
```

Nếu có hai dòng BOOK-A, **cả hai** tăng 1. Retry lệnh này có thể tăng lần nữa. Vì vậy, `$inc` phù hợp cho thao tác cộng thực sự, nhưng không có tính idempotent nếu cùng command được thực hiện lại vô điều kiện.

Trong Spring Data:

```java
Update update = new Update()
    .inc("items.$[line].quantity", 1)
    .filterArray(
        Criteria.where("line.sku_code").is("BOOK-A")
    );
```

### 10.2. Không dùng $set số lượng tùy ý nếu có ràng buộc nghiệp vụ

Nếu số lượng phải nằm trong khoảng 1 đến 100, kiểm tra input là cần nhưng **chưa đủ** nếu còn ràng buộc theo giá trị hiện tại, tồn kho hoặc trạng thái dòng. Thêm điều kiện trong array filter nếu cần:

```javascript
db.orders.updateOne(
  {
    _id: "ord-002",
    tenantId: "tenant-a",
    status: "READY_TO_SHIP",
    items: {
      $elemMatch: {
        sku_code: "BOOK-A",
        state: "NEW",
        quantity: { $lte: 10 }
      }
    }
  },
  {
    $set: { "items.$[line].state": "RESERVED" }
  },
  {
    arrayFilters: [
      {
        "line.sku_code": "BOOK-A",
        "line.state": "NEW",
        "line.quantity": { $lte: 10 }
      }
    ]
  }
);
```

Filter ở ngoài có ý nghĩa «có ít nhất một dòng hợp lệ». Filter trong `arrayFilters` ràng buộc **từng dòng được sửa**. Nếu chỉ đặt quantity điều kiện ở ngoài, có thể cập nhật sai một dòng khác khi array chứa nhiều phần tử.

### 10.3. Lệnh nguyên tử không tự bảo đảm mọi invariant

Update một document là nguyên tử, nhưng MongoDB không tự biết rằng:

- Tổng `quantity * priceVnd` phải bằng số tiền ở field khác.
- Không được đặt cùng SKU ở hai dòng nếu nghiệp vụ cấm.
- Dòng `DONE` không bao giờ được sửa.
- Tồn kho ở collection khác phải giảm cùng giao dịch.

Nếu update một phần tử kéo theo cập nhật tổng tiền, có thể cần thêm thao tác trên cùng document, kiểm tra concurrency hoặc thiết kế lại để tránh field tổng bị stale. Khi có invariant xuyên collection, cân nhắc transaction phù hợp topology và workflow.

## 11. Array không tồn tại, null, object thay vì array

Filtered positional update **yêu cầu đường dẫn array có dạng hợp lệ**. Những document bất thường như sau có thể tạo lỗi hoặc không có phần tử để sửa:

```javascript
{ _id: "bad-001", tenantId: "tenant-a" }

{ _id: "bad-002", tenantId: "tenant-a", items: null }

{ _id: "bad-003", tenantId: "tenant-a", items: { sku_code: "BOOK-A" } }

{ _id: "empty-001", tenantId: "tenant-a", items: [] }
```

Những trường hợp này **không tương đương**:

| Dữ liệu | Vấn đề |
| --- | --- |
| Không có `items` | Không có array để đi vào |
| `items: null` | Field có mặt nhưng không phải array |
| `items: {...}` | Sai kiểu BSON theo schema dự kiến |
| `items: []` | Array hợp lệ nhưng không có phần tử phù hợp |
| `items: [{ sku_code: "BOOK-B" }]` | Array hợp lệ nhưng không khớp filter BOOK-A |

### 11.1. Kiểm kê dữ liệu trước khi cập nhật hàng loạt

```javascript
// Document có items đúng kiểu BSON array.
db.orders.find({
  tenantId: "tenant-a",
  items: { $type: "array" }
});

// Document thiếu items.
db.orders.find({
  tenantId: "tenant-a",
  items: { $exists: false }
});

// Document có BSON Null.
db.orders.find({
  tenantId: "tenant-a",
  items: { $type: "null" }
});
```

Đặt điều kiện về loại dữ liệu vào query khi cần có thể giúp loại document sai schema, nhưng **không thay cho migration**. Nếu một document cần `items` mà lại lưu object hoặc Null, hãy xác định nguồn lỗi và sửa dữ liệu theo contract đã duyệt.

### 11.2. Khi cần thêm phần tử mới

`$[line]` **không tự tạo phần tử BOOK-A** nếu array chưa chứa BOOK-A. Để thêm một phần tử, cân nhắc `$push`/`$addToSet` hoặc logic nghiệp vụ riêng; sau khi thêm, hãy đảm bảo uniqueness/validation.

Đừng dùng filtered positional để «tạo sẵn phần tử thiếu» — đó không phải chức năng của toán tử.

## 12. Tránh upsert không phù hợp với $[identifier]

Một command «chỉnh dòng hàng của đơn đã tồn tại» thường phải dùng `updateFirst`/**không upsert**. Nếu cho phép upsert, thao tác có thể cố tạo document mới trong lúc đường dẫn filtered positional yêu cầu array có sẵn.

### 12.1. Quy tắc khi upsert buộc phải dùng arrayFilters

MongoDB đặt ràng buộc riêng: nếu operation dùng `$[identifier]` theo nhánh **upsert tạo mới**, query phải có **exact equality match** trên trường array tương ứng; nếu không, server có thể báo lỗi vì không có đường dẫn array để áp update.

Ví dụ sau là trường hợp **dễ lỗi**, không nên dùng cho sửa đơn:

```javascript
db.orders.updateOne(
  { _id: "ord-missing" },
  { $set: { "items.$[line].quantity": 5 } },
  {
    upsert: true,
    arrayFilters: [{ "line.sku_code": "BOOK-A" }]
  }
);
```

Trong nghiệp vụ bình thường, tách rõ:

- **Tạo đơn mới:** insert document có mảng `items` theo schema.
- **Sửa dòng hàng:** update document đã có với `$[line]`.
- **Thêm dòng:** dùng logic thêm phần tử có validation, không cố tạo bằng filtered positional.

### 12.2. State transition không nên upsert

Nếu đơn đã hủy hoặc không tồn tại, lệnh «đặt dòng hàng thành RESERVED» phải trả kết quả không phù hợp, **không tạo một đơn mới**. Điều kiện status ở filter document và việc **không bật upsert** giúp biểu diễn đúng hợp đồng nghiệp vụ.

## 13. Optimistic locking, version và concurrency

### 13.1. Vì sao update có thể thắng nhau?

Hai worker cùng đọc dòng BOOK-A quantity 2, rồi một worker muốn đổi thành 3, worker khác đổi thành 5. Nếu hai lệnh cùng:

```javascript
{ $set: { "items.$[line].quantity": newValue } }
```

và arrayFilters chỉ lọc SKU, kết quả cuối có thể là giá trị của thao tác đến sau. Atomicity trên một document **không tự ngăn lost update về mặt nghiệp vụ**.

### 13.2. Dùng expected version trong document filter

Một cách quản lý là thêm `version` cho document, rồi kiểm tra và tăng version trong cùng update:

```javascript
db.orders.updateOne(
  {
    _id: "ord-001",
    tenantId: "tenant-a",
    version: NumberLong("7"),
    status: "READY_TO_SHIP"
  },
  {
    $set: {
      "items.$[line].quantity": 5,
      updatedAt: new Date()
    },
    $inc: { version: NumberLong("1") }
  },
  {
    arrayFilters: [
      { "line.sku_code": "BOOK-A", "line.state": "NEW" }
    ]
  }
);
```

Với schema có version và chính sách tương ứng, chỉ một update với version 7 có thể thắng; lần còn lại sẽ không match sau khi version đổi. Nhưng đây là **ví dụ cho một schema mở rộng**: fixture ở mục 2 chưa có `version`.

Nếu dùng `@Version` trong Spring Data, cần kiểm tra behavior của đường update hiện tại; đừng cho rằng mọi lệnh `MongoTemplate.updateFirst(...)` tự thực hiện đầy đủ kiểm tra version theo entity Java mà không cần điều kiện/thiết kế thêm.

### 13.3. Đổi trạng thái một dòng theo expected state

Một phương án khác khi không có version toàn document:

```java
Query query = Query.query(
    Criteria.where("id").is(orderId)
        .and("tenantId").is(authenticatedTenantId)
        .and("status").is("READY_TO_SHIP")
        .and("items").elemMatch(
            Criteria.where("sku").is(sku)
                .and("state").is("NEW")
        )
);

Update update = new Update()
    .set("items.$[line].state", "RESERVED")
    .filterArray(
        Criteria.where("line.sku_code").is(sku)
            .and("line.state").is("NEW")
    );

var result = mongo.updateFirst(
    query, update, OrderDocument.class
);
```

Filter ngoài và trong đều có expected state. Để phân biệt *một dòng logic* khi có SKU trùng, dùng `lineId` duy nhất thay vì SKU.

## 14. Index và hiệu năng cập nhật phần tử array

### 14.1. Index hỗ trợ chọn document, không chọn hộ phần tử

Truy vấn ngoài cần chọn document nhanh. Nếu thường sửa một đơn theo `_id + tenantId`, index mặc định trên `_id` có thể đã đủ để tìm đúng document rồi kiểm tra tenant; không tạo compound index mới một cách máy móc.

Nếu update hàng loạt theo tenant/status/SKU:

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, "items.sku_code": 1 },
  { name: "ix_orders_tenant_status_item_sku" }
);
```

Đây là index ứng viên cho filter document có `items.sku_code`. Vì field nằm trong array, index sẽ có đặc tính **multikey**; nó có chi phí cập nhật khi các phần tử array thay đổi. Không phải mọi array filter đều biến thành index lookup độc lập: server vẫn phải xác định các phần tử phù hợp bên trong document được cập nhật.

### 14.2. Có nên thêm SKU vào filter ngoài?

```javascript
db.orders.updateMany(
  {
    tenantId: "tenant-a",
    status: "READY_TO_SHIP",
    "items.sku_code": "BOOK-A"
  },
  { $set: { "items.$[line].state": "CHECKED" } },
  { arrayFilters: [{ "line.sku_code": "BOOK-A" }] }
);
```

Điều kiện `items.sku_code` bên ngoài có thể giúp index chọn đúng document và tránh document hoàn toàn không chứa SKU. Tuy nhiên, **vẫn cần arrayFilters** để giới hạn phần tử được ghi; điều kiện ngoài không thay thế điều kiện trong.

### 14.3. explain: đo filter trước, đo write sau

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP",
  "items.sku_code": "BOOK-A"
}).explain("executionStats");
```

Quan sát `winningPlan`, `IXSCAN`/`COLLSCAN`, `totalKeysExamined` và `totalDocsExamined`. Đây là cách khảo sát chi phí tìm **document** tương đương, **không phải** phép đo đầy đủ chi phí update array (ghi BSON, sửa index, replication, lock hoặc kích thước document).

Đo thực tế cần phân biệt:

| Tình huống | Cần quan sát |
| --- | --- |
| Một document, một element | Độ trễ và modifiedCount |
| Một document, nhiều element | Chi phí cập nhật trong một document |
| Nhiều document, updateMulti | Docs scanned, write throughput, chi phí replication |
| Array rất dài | Kích thước document, số element, thời gian xử lý |
| Có multikey index | Index maintenance khi thay field được index |
| Concurrent updates | Contention, write conflict/retry |

MongoDB có giới hạn BSON document **16 MiB**. Nếu array lớn tăng không giới hạn, cân nhắc tách thành collection riêng thay vì cố xử lý một document cực lớn bằng arrayFilters.

## 15. Thay đổi trường có @Field và converter: kiểm tra BSON cuối

### 15.1. Array filter và property alias

Model `OrderLine.sku` được lưu là `sku_code`. Ví dụ:

```java
@Field("sku_code")
String sku;
```

Các biểu thức ở những lớp khác nhau:

```java
// Query: có entity mapping khi thực thi với OrderDocument.class.
Criteria.where("items.sku").is("BOOK-A");

// Update field số lượng: tên BSON và Java đang giống nhau.
new Update().set("items.$[line].quantity", 5);

// Array filter: truyền xuống driver, dùng tên BSON thực.
Criteria.where("line.sku_code").is("BOOK-A");
```

Với kiểu dữ liệu phức tạp như `ObjectId`, `UUID` hoặc enum có converter riêng, đặc biệt cẩn thận: điều kiện nằm trong `arrayFilters` không tự hưởng mọi phép chuyển đổi của `QueryMapper`. Truyền đúng **kiểu BSON** mà field đang lưu và kiểm tra lệnh thực tế bằng integration test.

### 15.2. Ví dụ lỗi kiểu dữ liệu

Giả sử field `items.productId` lưu BSON ObjectId. Lọc bằng chuỗi 24 ký tự:

```javascript
arrayFilters: [
  { "line.productId": "507f1f77bcf86cd799439011" }
]
```

có thể **không khớp** với BSON ObjectId. Nếu schema dùng ObjectId, phải truyền ObjectId:

```javascript
arrayFilters: [
  { "line.productId": ObjectId("507f1f77bcf86cd799439011") }
]
```

Đừng kết luận arrayFilters sai vì `modifiedCount=0` trước khi kiểm tra BSON type của từng giá trị điều kiện.

### 15.3. Query/Update logging an toàn

Có thể bật command monitoring hoặc logging có giới hạn trong môi trường test để xác định filter document, update path và arrayFilters. Ở production không nên log trọn document chứa dữ liệu cá nhân, token hoặc thông tin nhạy cảm; dùng redaction và correlation ID theo chính sách dự án.

## 16. Cập nhật theo vị trí cố định và xử lý array lồng nhau

### 16.1. Khi nào dùng items.0.quantity?

```javascript
db.orders.updateOne(
  { _id: "ord-001" },
  { $set: { "items.0.quantity": 5 } }
);
```

Đường dẫn này chỉ sửa phần tử **chỉ số 0**. Nó phù hợp khi nghiệp vụ thật sự gắn ý nghĩa với vị trí, không phù hợp khi người dùng có thể đổi thứ tự dòng hoặc import dữ liệu mới.

### 16.2. $[] và $[identifier] có thể kết hợp

Trong những trường hợp cần đi qua mọi nhóm nhưng chỉ sửa một package theo code, có thể đặt `$[]` ở cấp array đầu và `$[pkg]` ở cấp array sau:

```javascript
db.shipments.updateOne(
  { _id: "shipment-001", tenantId: "tenant-a" },
  {
    $set: {
      "batches.$[].packages.$[pkg].state": "CHECKED"
    }
  },
  {
    arrayFilters: [
      { "pkg.packageCode": "P1" }
    ]
  }
);
```

Khác với ví dụ chỉ batch B2 ở mục 9, lệnh này cập nhật **mọi package P1 ở mọi batch**. Tên `pkg` chỉ đại diện cho filter cấp packages, còn `$[]` không cần một array filter identifier riêng.

### 16.3. Tránh suy luận sai từ vị trí array

Chỉ số, `$`, `$[]` và `$[identifier]` đều là công cụ khác nhau. Khi thiết kế API, đặt tên nghiệp vụ như `reserveLineById` hoặc `markPackagesByCode`; không phơi ra một «update arbitrary path» để client tự gửi đường dẫn và toán tử.

## 17. Reactive access, transaction và phiên bản

### 17.1. ReactiveMongoOperations

Ở ứng dụng reactive:

```java
import reactor.core.publisher.Mono;
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;

public final class ReactiveOrderLineWriter {
    private final ReactiveMongoOperations mongo;

    public ReactiveOrderLineWriter(ReactiveMongoOperations mongo) {
        this.mongo = mongo;
    }

    public Mono<UpdateResult> reserveBookA(
        String tenantId,
        String orderId
    ) {
        Query query = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(tenantId)
                .and("status").is("READY_TO_SHIP")
        );

        Update update = new Update()
            .set("items.$[line].state", "RESERVED")
            .filterArray(
                Criteria.where("line.sku_code").is("BOOK-A")
                    .and("line.state").is("NEW")
            );

        return mongo.updateFirst(query, update, OrderDocument.class);
    }
}
```

Ví dụ giả định có imports `Query`, `Criteria`, `Update`, `OrderDocument` như trước. `Mono<UpdateResult>` chỉ biểu diễn kết quả khi có subscription phù hợp; không có nghĩa server update ngay tại lúc gọi method nếu publisher chưa được subscribe.

Reactive không tự bảo đảm tenant authorization, unique array elements hay transaction. Không dùng `block()` trong một đường xử lý non-blocking chỉ để chuyển sang imperative.

### 17.2. Multi-document transactions

Khi sửa một mảng của **một document**, update nguyên tử trên document thường đã đủ về mặt database. Nếu phải đồng thời sửa order, shipment và stock ở nhiều collection và cần tất cả thành công/rollback, xem xét MongoDB multi-document transaction với topology/transaction manager phù hợp.

Không coi việc thêm `@Transactional` là thay thế cho thiết kế state transition hoặc array filter đúng. Transaction không làm cho hai điều kiện thuộc hai phần tử khác nhau tự trở thành cùng một phần tử.

### 17.3. Khả năng hỗ trợ theo phiên bản

| Thành phần | Điều cần kiểm tra |
| --- | --- |
| MongoDB server | Có hỗ trợ `$[identifier]` và `arrayFilters` không; thao tác update nào nhận option? |
| MongoDB Java driver | `UpdateOptions.arrayFilters(...)` và hành vi mã hóa BSON |
| Spring Data MongoDB | `Update.filterArray(...)`, `MongoOperations.updateFirst/updateMulti`, kiểu mapping |
| Spring Boot | Phiên bản Spring Data/driver được quản lý, bean `MongoTemplate`/reactive |
| Collection schema | `items` có đúng là array, nested fields và types phù hợp không? |

MongoDB 3.6 là mốc giới thiệu filtered positional array updates. Không phải mọi cú pháp update pipeline hoặc mọi operation đều nhận `arrayFilters` theo cách giống một lệnh `updateOne` thông thường; phải xem đúng API theo version và loại operation. Đặc biệt, **aggregation pipeline updates không dùng tùy chọn arrayFilters theo cùng cơ chế này**.

## 18. Kiểm thử đầy đủ: đúng document, đúng phần tử, đúng trường

### 18.1. Ma trận hành vi

| Test | Kỳ vọng |
| --- | --- |
| Một dòng BOOK-A trong `ord-001` | Chỉ dòng BOOK-A thay đổi |
| Hai dòng BOOK-A trong `ord-002` | **Cả hai** thay đổi nếu filter chỉ theo SKU |
| Dòng BOOK-B hoặc BOOK-C | Không thay đổi |
| Document thuộc tenant-b | Không thay đổi |
| Document CANCELLED | Không thay đổi khi filter yêu cầu READY_TO_SHIP |
| Không có dòng phù hợp | Matched có thể 1, modified 0 |
| Mảng rỗng | Không có element được update |
| Mảng missing/null/sai kiểu | Cần test lỗi hoặc no-match theo cấu trúc và query |
| Một identifier với hai điều kiện | Chỉ phần tử thỏa cả hai |
| Hai identifier ở hai cấp array | Chỉ phần tử ở đúng cấp/batch |
| Filter dùng `line.sku` thay vì `line.sku_code` | Không mong đợi match trên BSON dùng alias |
| `$inc` gọi lại hai lần | Giá trị có thể tăng hai lần |
| Update có expected version | Tránh ghi đè khi version đã đổi |
| Lỗi array filter identifier thiếu | Thao tác thất bại, không bị bỏ qua âm thầm |

### 18.2. Khung integration test cho Spring Data

Ví dụ JUnit 5, giả định dự án có MongoDB test context, seed fixture trong mục 2, và `MongoOperations` được inject:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

class ArrayFilterIntegrationTest {
    MongoOperations mongo; // Inject qua test configuration.

    @Test
    void changesAllMatchingLinesNotOtherSkus() {
        Query key = Query.query(
            Criteria.where("id").is("ord-002")
                .and("tenantId").is("tenant-a")
        );
        Update update = new Update()
            .set("items.$[line].state", "CHECKED")
            .filterArray(
                Criteria.where("line.sku_code").is("BOOK-A")
            );

        var result = mongo.updateFirst(
            key, update, OrderDocument.class
        );
        assertEquals(1, result.getMatchedCount());
        assertEquals(1, result.getModifiedCount());

        OrderDocument saved = mongo.findOne(key, OrderDocument.class);
        assertNotNull(saved);
        List<OrderLine> items = saved.items();
        assertEquals("CHECKED", items.get(0).state());
        assertEquals("CHECKED", items.get(1).state());
        assertEquals("NEW", items.get(2).state());
    }
}
```

Đây là **khung test học tập**, không phải class chạy độc lập ngay. Cần annotation/test context, injection, seed dữ liệu trước test, cleanup và phiên bản Spring Data phù hợp. Test phải reset fixture để những lần chạy trước không làm `modifiedCount` thay đổi; trên record đã CHECKED, một lần set lại CHECKED có thể cho `modifiedCount=0`.

### 18.3. Test JSON BSON thực tế

```javascript
db.orders.findOne(
  { _id: "ord-002", tenantId: "tenant-a" },
  { items: 1, status: 1 }
);
```

Kiểm tra:

- `sku_code` là field BSON thật, không phải `sku`.
- `items` vẫn là array với số lượng phần tử ban đầu.
- Chỉ các field đích được thay đổi.
- Các dòng không phù hợp và dữ liệu tenant khác vẫn giữ nguyên.
- Cách phân biệt `matchedCount` và `modifiedCount` đúng như contract.

### 18.4. Test concurrency và retry

Tạo hai worker/test thread cập nhật cùng document với expected version khác nhau; xác nhận không có lost update ngoài ý muốn. Với `$inc`, đánh giá retry policy để không nhân đôi tác dụng. Với `updateMulti`, test khả năng lỗi giữa chừng và tính nguyên tử theo từng document, không giả định cả batch là một transaction.

## 19. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Điều cần làm |
| --- | --- | --- |
| Identifier `line` không có filter | Có `$[line]` nhưng thiếu `arrayFilters` | Đăng ký một filter cho line |
| Identifier được định nghĩa lặp | Hai object arrayFilters dùng cùng identifier | Gộp predicate của line vào một object |
| `modifiedCount=0` | Không có element phù hợp hoặc giá trị không đổi | Đọc BSON, so sánh matchedCount/modifiedCount |
| `modifiedCount=1` nhưng hai dòng bị sửa | Count theo document, không theo element | Test số phần tử qua document sau ghi |
| Cập nhật sai cả BOOK-B | Dùng `$[]` hoặc thiếu điều kiện bên trong | Dùng `$[line]` và arrayFilters rõ ràng |
| BOOK-A duplicate đều bị sửa | Filter theo SKU không định danh duy nhất một dòng | Dùng lineId hoặc predicate chi tiết |
| Tenant khác bị sửa | Filter ngoài không ràng buộc tenant | Thêm tenant từ authentication context |
| Update state DONE thành RESERVED | Chỉ lọc SKU, không lọc expected state | Bổ sung line.state trong arrayFilters |
| `line.sku` không khớp | BSON lưu `sku_code`, arrayFilters không được map như query | Dùng tên BSON thật |
| Array missing hoặc Null gây lỗi | Đường dẫn update yêu cầu array hợp lệ | Validate schema, migration dữ liệu |
| Upsert báo lỗi đường dẫn array | Thiếu exact equality array match trong insert branch | Không upsert cho update phần tử |
| Truy vấn có kết quả nhưng update no-op | Query chọn document, arrayFilters không khớp phần tử | Kiểm tra cả hai tầng điều kiện |
| Cập nhật hai array lồng nhau sai batch | Thiếu filter batch ở cấp ngoài | Dùng hai identifier |
| Server không hiểu $[line] | Version hoặc operation không hỗ trợ | Kiểm tra MongoDB, driver, Spring Data |
| Mảng lớn, update chậm | BSON document lớn, index maintenance, contention | Đo workload, cân nhắc tách collection |
| Version thay đổi nhưng ghi bị đè | Thiếu expected version hoặc expected state trong filter | Bổ sung concurrency guard |

### 19.1. Quy trình điều tra ngắn

```text
1. Document filter: có đúng _id, tenantId, trạng thái?
                 ↓
2. BSON thực: items có là array không? sku_code hay sku?
                 ↓
3. Update path: items.$[line].quantity hay items.$[]?
                 ↓
4. arrayFilters: identifier line, điều kiện và kiểu BSON đã khớp?
                 ↓
5. UpdateResult: matchedCount / modifiedCount theo DOCUMENT.
                 ↓
6. Đọc lại document và so sánh đúng các phần tử.
                 ↓
7. Sau khi đúng logic mới tối ưu index/throughput.
```

Đừng dùng «không có lỗi exception» làm bằng chứng rằng thao tác đã cập nhật đúng: một update có thể thành công nhưng không sửa gì.

## 20. Bài thực hành có lời giải

### Bài 1 — Thay quantity chỉ cho BOOK-A

**Đề bài:** `ord-001` có BOOK-A quantity 1 và BOOK-B quantity 4. Chỉ đặt BOOK-A thành 5.

**Lời giải:**

```javascript
db.orders.updateOne(
  { _id: "ord-001", tenantId: "tenant-a" },
  { $set: { "items.$[line].quantity": 5 } },
  { arrayFilters: [{ "line.sku_code": "BOOK-A" }] }
);
```

BOOK-B giữ nguyên. Nếu thay bằng `$[]`, cả hai quantity sẽ bị đặt thành 5.

### Bài 2 — Dự đoán số phần tử được cập nhật

**Đề bài:** Chạy lệnh ở bài 1 trên `ord-002`, nơi có **hai** phần tử BOOK-A. Có bao nhiêu phần tử đổi quantity? `modifiedCount` có chắc bằng 2 không?

**Lời giải:** Có thể **hai phần tử** đổi quantity nếu giá trị mới khác cũ; `modifiedCount` thường là 1 vì **một document** bị sửa. Driver trả số document, không phải số phần tử array.

### Bài 3 — Một phần tử phải thỏa hai điều kiện

**Đề bài:** Đặt state CHECKED chỉ cho dòng BOOK-A có quantity từ 3 trở lên.

**Lời giải:**

```javascript
db.orders.updateOne(
  { _id: "ord-002", tenantId: "tenant-a" },
  { $set: { "items.$[line].state": "CHECKED" } },
  {
    arrayFilters: [{
      "line.sku_code": "BOOK-A",
      "line.quantity": { $gte: 3 }
    }]
  }
);
```

Hai predicate thuộc **cùng một filter của line**, nên cùng áp dụng lên một phần tử. Với fixture ban đầu, dòng BOOK-A quantity 3 được sửa, dòng quantity 2 không bị sửa.

### Bài 4 — Viết bằng Spring Data Update.filterArray

**Đề bài:** Entity dùng `@Field("sku_code") String sku`. Viết Update đổi `state` thành RESERVED cho dòng BOOK-A đang NEW.

**Lời giải:**

```java
Update update = new Update()
    .set("items.$[line].state", "RESERVED")
    .filterArray(
        Criteria.where("line.sku_code").is("BOOK-A")
            .and("line.state").is("NEW")
    );
```

Trong `arrayFilters` phải dùng `line.sku_code` theo BSON. Sau đó gọi `mongo.updateFirst(queryWithTenantAndStatus, update, OrderDocument.class)`; query phải được xây và xác thực riêng.

### Bài 5 — Chọn batch B2, package P1

**Đề bài:** Trong document `shipments`, chỉ đặt `READY` cho package P1 của batch B2.

**Lời giải:**

```javascript
db.shipments.updateOne(
  { _id: "shipment-001", tenantId: "tenant-a" },
  { $set: { "batches.$[b].packages.$[p].state": "READY" } },
  {
    arrayFilters: [
      { "b.batchCode": "B2" },
      { "p.packageCode": "P1" }
    ]
  }
);
```

Hai identifier giúp lọc ở hai cấp. Không dùng `batches.$[].packages.$[p]` nếu chỉ muốn batch B2.

### Bài 6 — Sự khác nhau giữa $elemMatch và arrayFilters

**Đề bài:** Một developer chỉ đặt `items: {$elemMatch: {sku_code: "BOOK-A"}}` vào filter ngoài nhưng update lại dùng `items.$[].state`. Có bảo đảm chỉ sửa BOOK-A không?

**Lời giải:** Không. `$elemMatch` ở filter ngoài chỉ quyết định document nào có ít nhất một BOOK-A. `$[]` ở đường dẫn update vẫn sửa **tất cả phần tử**. Cần `$[line]` và `arrayFilters` phù hợp.

### Bài 7 — No-op và matchedCount

**Đề bài:** `updateOne` có `matchedCount=1` và `modifiedCount=0`. Kết luận «không có SKU BOOK-A» có chắc đúng không?

**Lời giải:** Không. Có thể không có phần tử khớp, hoặc phần tử khớp đã có giá trị đích. Đọc lại BSON hoặc thiết kế query/kiểm tra nghiệp vụ để phân biệt hai trường hợp.

### Bài 8 — Tránh update nhầm tenant

**Đề bài:** Lệnh `updateMany` dùng arrayFilters cho BOOK-A nhưng filter ngoài chỉ có `status: READY_TO_SHIP`. Vấn đề gì?

**Lời giải:** Có thể sửa đơn của tenant khác. Thêm `tenantId` lấy từ security context và giới hạn scope theo use case; arrayFilters không thay cho authorization.

### Bài 9 — Chọn update hay upsert

**Đề bài:** Một request muốn sửa dòng hàng của đơn chưa chắc tồn tại. Có nên dùng `mongo.upsert(...)` với `items.$[line]`?

**Lời giải:** Thường **không**. Upsert insert branch có yêu cầu exact equality trên trường array và có thể báo lỗi nếu không có array. Nếu business muốn sửa đơn hiện hữu, dùng `updateFirst` không upsert; nếu muốn tạo đơn, dùng quy trình insert với danh sách items hợp lệ.

### Bài 10 — Kiểm tra concurrency

**Đề bài:** Hai worker cùng đặt quantity của một dòng thành 3 và 5; cả hai đều lọc theo SKU. Làm sao hạn chế lost update?

**Lời giải:** Dùng version/expected state hoặc expected quantity trong điều kiện phù hợp và thực hiện update nguyên tử, kiểm tra `matchedCount`. Nếu cần chính xác một dòng, dùng `lineId` duy nhất thay vì SKU; test hai request chạy đồng thời.

## 21. Checklist bàn giao

| Câu hỏi | Tiêu chí kiểm chứng |
| --- | --- |
| API muốn sửa một phần tử hay mọi phần tử phù hợp? | Chọn đúng `$`, `$[]` hoặc `$[id]` |
| Document filter đã đủ ID/tenant/status chưa? | Không thể ghi dữ liệu ngoài quyền |
| Một SKU có thể xuất hiện nhiều lần không? | Dùng `lineId` nếu nghiệp vụ chỉ cho sửa một dòng |
| Identifier hợp lệ và được định nghĩa chưa? | Một filter document cho mỗi identifier |
| Các predicate phải trên cùng phần tử? | Một filter object cho identifier tương ứng |
| Có dùng tên field BSON trong arrayFilters? | `line.sku_code` thay vì `line.sku` |
| Có custom converter/kiểu ObjectId/enum không? | Test BSON type và arrayFilter matching |
| Mảng có thể null/missing/sai kiểu không? | Data validation và kiểm kê legacy |
| Có nhầm `$elemMatch` với filtered update không? | Test document match khác element match |
| Có dùng upsert cho update mảng không? | Xác định rõ insert branch; thường tắt upsert |
| Có concurrency guard không? | Version/expected state trong filter |
| UpdateResult được diễn giải theo document chưa? | Không đếm element bằng modifiedCount |
| Có cần transaction xuyên document? | Topology/transaction manager được kiểm tra |
| Index hỗ trợ filter document? | `getIndexes()` và `explain` |
| Dữ liệu array quá lớn không? | Document size, workload và giải pháp tách collection |
| Có test đúng hai tenant, nhiều phần tử và no-op? | Integration test MongoDB + đọc lại document |
| MongoDB và Spring Data version hỗ trợ không? | Test filtered positional/arrayFilters theo dependency |

### Ghi nhớ

1. **`$[identifier]`** là filtered positional operator; **`arrayFilters`** định nghĩa điều kiện cho identifier. Nó có thể cập nhật **nhiều phần tử** trong cùng một document.
2. **Query filter chọn document**, **arrayFilters chọn phần tử**. Phải đặt tenant, trạng thái và các ràng buộc khác ở đúng cấp.
3. Phân biệt **`$`** (positional đầu tiên), **`$[]`** (mọi phần tử), **`$[line]`** (mọi phần tử phù hợp) và **`$elemMatch`** (lọc nhiều predicate cùng phần tử).
4. Trong Spring Data, `Update.filterArray(...)` cần được viết theo **tên BSON thực tế** vì filter expressions không tự được map đầy đủ theo `@Field` của domain entity.
5. `matchedCount`/`modifiedCount` đếm **document**, không phải array elements. Một document có thể có nhiều dòng được sửa.
6. Khi mảng lồng nhau, dùng nhiều identifier hoặc kết hợp `$[]` và `$[id]` phù hợp; không dựa vào chỉ số vị trí nếu schema không cam kết thứ tự.
7. Không dùng array filter để thay thế schema validation, authorization, optimistic locking, unique line identity hoặc transaction cần thiết.
8. Luôn **đọc lại BSON thật**, kiểm thử nhiều dòng cùng SKU, dữ liệu lỗi, concurrency và xem xét index/phiên bản trước khi triển khai.
