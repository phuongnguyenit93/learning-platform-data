# `updateFirst`, `updateMulti` và các biến thể fluent

> **Chương:** Ghi và cập nhật  
> **Module:** `SPRING_DATA_MONGODB` — sử dụng Spring Data MongoDB để kết nối, ánh xạ document, thao tác dữ liệu bằng `MongoTemplate` hoặc repository, đồng thời thực hành truy vấn, transaction, kiểm thử và chẩn đoán hiệu năng.  
> **Mục tiêu:** Phân biệt cập nhật một và nhiều document; xây `Query` và `Update` đúng theo entity; viết API fluent `.matching(...).apply(...).first()/all()/upsert()`; hiểu `UpdateResult`, `@Version`, tính nguyên tử, vấn đề chọn document đầu tiên và kiểm thử cập nhật có điều kiện.

## 1. Khi nào nên cập nhật bằng `MongoTemplate`?

Giả sử đơn hàng đang ở trạng thái `NEW`. Bạn cần chuyển nó thành `PROCESSING`, tăng bộ đếm retry, thêm nhãn hoặc cập nhật một trường nhúng mà **không muốn đọc toàn bộ entity rồi ghi thay thế**.

Spring Data MongoDB cung cấp hai nhóm API:

- **API trực tiếp:** `MongoTemplate.updateFirst(Query, UpdateDefinition, ...)` và `updateMulti(Query, UpdateDefinition, ...)`.
- **API fluent:** `template.update(OrderDocument.class).matching(...).apply(...).first()`, `.all()` và `.upsert()`.

Cả hai nhóm đều sử dụng những **update operator** của MongoDB, chẳng hạn `$set`, `$inc`, `$unset`, `$addToSet`, thay vì yêu cầu ứng dụng tải toàn bộ document chỉ để sửa một thuộc tính.

| Nhu cầu | API phù hợp | Ý nghĩa |
| --- | --- | --- |
| Đổi trạng thái một order đã biết ID | `updateFirst` hoặc fluent `first()` | Sửa tối đa một document khớp |
| Cộng bộ đếm cho tất cả order thỏa điều kiện | `updateMulti` hoặc fluent `all()` | Sửa mọi document khớp |
| Nếu order chưa có thì tạo, nếu có thì cập nhật | `upsert` hoặc fluent `upsert()` | Cập nhật một document hoặc chèn mới |
| Cập nhật một document và nhận lại bản trước/sau | `findAndModify` | Tìm-và-sửa một document, có thể chọn sort |
| Nhiều update khác nhau cho các document khác nhau | `BulkOperations` | Gom các thao tác, không đồng nghĩa updateMulti |

**Cần phân biệt:** “đầu tiên” trong `updateFirst` là **một document khớp query**, không có nghĩa document có `_id` nhỏ nhất, ngày tạo sớm nhất hay đứng đầu danh sách UI khi query không có thứ tự rõ ràng.

## 2. Chuẩn bị dữ liệu và entity nhất quán

### 2.1. Bộ dữ liệu thử nghiệm trong `mongosh`

Làm việc trên một **database học tập riêng**; các ví dụ ghi trong bài không dành cho dữ liệu production.

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_updates_demo_003;

orders.insertMany([
  {
    _id: "o301", tenant_id: "t01", state_code: "NEW",
    retry_count: 0, total_vnd: 100000, version: NumberLong(0),
    tags: [], delivery: { city: "Hà Nội", note: "Sáng" }
  },
  {
    _id: "o302", tenant_id: "t01", state_code: "NEW",
    retry_count: 1, total_vnd: 200000, version: NumberLong(0),
    tags: ["priority"], delivery: { city: "Hà Nội" }
  },
  {
    _id: "o303", tenant_id: "t01", state_code: "PAID",
    retry_count: 0, total_vnd: 350000, version: NumberLong(0),
    tags: ["paid"], delivery: { city: "Đà Nẵng" }
  },
  {
    _id: "o304", tenant_id: "t02", state_code: "NEW",
    retry_count: 0, total_vnd: 400000, version: NumberLong(0),
    tags: [], delivery: { city: "Hồ Chí Minh" }
  },
  {
    _id: "o305", tenant_id: "t01", state_code: "NEW",
    retry_count: 2, total_vnd: 500000, version: NumberLong(0),
    tags: ["manual-review"], delivery: { city: "Huế" }
  },
  {
    _id: "o306", tenant_id: "t01", state_code: "CANCELLED",
    retry_count: 0, total_vnd: 150000, version: NumberLong(0),
    tags: [], delivery: { city: "Hà Nội" }
  }
]);

orders.createIndex(
  { tenant_id: 1, state_code: 1 },
  { name: "tenant_state_idx" }
);
~~~

Collection ban đầu có 6 document. Trong đó `t01` có **3 order NEW** (`o301`, `o302`, `o305`), một order PAID và một order CANCELLED; `t02` có một order NEW. Không chạy lại `insertMany` nếu dữ liệu fixture còn đó, vì `_id` cố định sẽ gây duplicate key.

Các kết quả kỳ vọng trong mỗi mục được tính trên dữ liệu ban đầu **trừ khi mục đó nói rõ chạy tuần tự**. Những đoạn ghi ở các mục khác nhau thường là **kịch bản thay thế**, không phải chuỗi lệnh phải chạy hết từ đầu đến cuối.

### 2.2. Entity Java với tên property khác tên BSON

~~~java
// DeliveryInfo.java
package com.example.orderupdates;

public class DeliveryInfo {
    private String city;
    private String note;

    protected DeliveryInfo() { }

    public String getCity() { return city; }
    public String getNote() { return note; }
}
~~~

~~~java
// OrderDocument.java
package com.example.orderupdates;

import java.util.List;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_updates_demo_003")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("state_code")
    private String state;

    @Field("retry_count")
    private int retryCount;

    @Field("total_vnd")
    private long totalVnd;

    private List<String> tags;
    private DeliveryInfo delivery;

    @Version
    private Long version;

    protected OrderDocument() { }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getState() { return state; }
    public int getRetryCount() { return retryCount; }
    public long getTotalVnd() { return totalVnd; }
    public List<String> getTags() { return tags; }
    public DeliveryInfo getDelivery() { return delivery; }
    public Long getVersion() { return version; }
}
~~~

Điểm chủ đích:

- Java có `tenantId`, `state`, `retryCount` và `totalVnd`; MongoDB lưu lần lượt `tenant_id`, `state_code`, `retry_count`, `total_vnd`.
- `@MongoId(FieldType.STRING)` bảo đảm `_id` dùng BSON string.
- `@Version Long version` biểu diễn phiên bản và có hành vi cần chú ý khi update.
- `delivery` là embedded document nên đường dẫn Java `delivery.city` ánh xạ vào BSON `delivery.city`.

Đối với `MongoTemplate` **có entity class**, bạn nên viết query/update theo **tên property Java**; Spring Data ánh xạ đến tên trường BSON thực. Đừng trộn cách viết của `Query`/`Update` với cách viết raw `Filters`/`Updates` của MongoDB Java Driver.

### 2.3. Import thường dùng

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
~~~

Các đoạn code sau giả định `template` là bean `MongoTemplate` đã được inject trong service hoặc integration test.

## 3. `updateFirst`: cập nhật tối đa một document

### 3.1. Cập nhật một order bằng ID và trạng thái hiện tại

~~~java
Query query = Query.query(
    Criteria.where("id").is("o301")
        .and("tenantId").is("t01")
        .and("state").is("NEW")
);

Update update = new Update()
    .set("state", "PROCESSING")
    .inc("retryCount", 1);

UpdateResult result = template.updateFirst(
    query, update, OrderDocument.class
);
~~~

Ở mức BSON, ý tưởng của thao tác là:

~~~javascript
orders.updateOne(
  {
    _id: "o301",
    tenant_id: "t01",
    state_code: "NEW"
  },
  {
    $set: { state_code: "PROCESSING" },
    $inc: { retry_count: 1 }
  }
);
~~~

Với fixture ban đầu và write concern đã được server xác nhận, `matchedCount = 1`; `state_code` thành PROCESSING và `retry_count` thành 1. Vì entity có `@Version`, Spring Data còn **tự tăng phiên bản** nếu `version` không được chỉ định tường minh trong `Update` (xem mục 9).

### 3.2. Vì sao nên có điều kiện trạng thái?

Nếu chỉ lọc `_id`, một luồng xử lý có thể ghi đè trạng thái mới hơn của luồng khác. Khi thêm `state = NEW` vào query, MongoDB chỉ cập nhật nếu document **đang ở đúng trạng thái** tại thời điểm thao tác.

Một update trên **một document** có tính nguyên tử ở MongoDB. Vì vậy filter `_id + state` và update `$set` trong cùng lệnh tránh được race của mẫu:

~~~text
ĐỌC trạng thái NEW -> xử lý logic -> GHI trạng thái PROCESSING
~~~

nếu thực hiện đọc và ghi bằng **hai** thao tác rời nhau.

### 3.3. Khi có nhiều document khớp thì sao?

~~~java
UpdateResult result = template.updateFirst(
    Query.query(
        Criteria.where("tenantId").is("t01")
            .and("state").is("NEW")
    ),
    new Update().set("state", "REVIEW"),
    OrderDocument.class
);
~~~

Fixture ban đầu có **ba** order t01/NEW nhưng `updateFirst` chỉ sửa tối đa **một**. Không thể kết luận chắc đó là `o301`, `o302` hay `o305` nếu không có cơ chế chọn thứ tự được hỗ trợ và không có khóa chỉ định một document.

Để update một order xác định, ưu tiên điều kiện chứa `_id`. Nếu nhiệm vụ là “chọn order cũ nhất rồi chuyển trạng thái”, xem `findAndModify` với sort ở mục 10; không dựa vào “thứ tự tự nhiên” của collection.

### 3.4. Các overload thực tế

~~~java
// Đích được suy từ @Document của entity.
template.updateFirst(query, update, OrderDocument.class);

// Chỉ rõ entity và collection.
template.updateFirst(
    query, update,
    OrderDocument.class, "orders_updates_demo_003"
);

// Chỉ rõ tên collection, không cung cấp entity.
template.updateFirst(
    rawQuery, rawUpdate, "orders_updates_demo_003"
);
~~~

Với overload **chỉ có tên collection**, Spring Data không có metadata domain class để ánh xạ `tenantId` sang `tenant_id` hay hỗ trợ xử lý version tương ứng. Nếu dùng overload này, `rawQuery`/`rawUpdate` phải dựa trên **tên BSON thực** và chịu trách nhiệm về quy tắc dữ liệu.

## 4. `updateMulti`: cập nhật tất cả document khớp

### 4.1. Ví dụ trên một tenant và một trạng thái

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("state").is("NEW")
);

Update update = new Update()
    .set("state", "QUEUED")
    .addToSet("tags", "batch-queued");

UpdateResult result = template.updateMulti(
    query, update, OrderDocument.class
);
~~~

Tương ứng về ý nghĩa với MongoDB:

~~~javascript
orders.updateMany(
  { tenant_id: "t01", state_code: "NEW" },
  {
    $set: { state_code: "QUEUED" },
    $addToSet: { tags: "batch-queued" }
  }
);
~~~

Nếu chạy trên fixture ban đầu, **3 document** (`o301`, `o302`, `o305`) khớp điều kiện. `o304` cũng NEW nhưng thuộc tenant `t02` nên không bị cập nhật. `o303` PAID và `o306` CANCELLED cũng không bị chạm tới.

### 4.2. `updateMulti` không có nghĩa “update lặp `updateFirst` trong Java”

`updateMulti` gửi thao tác cập nhật nhiều document theo query tới MongoDB. Framework không cần tải entity rồi gọi `save` cho từng document. Đây là lợi thế quan trọng khi chỉ cần thay đổi vài field của hàng nghìn document.

Tuy nhiên:

- Một thao tác nhiều document **không tạo transaction nguyên tử cho cả tập**; mỗi document được cập nhật theo nguyên tắc nguyên tử riêng.
- Các update dựa trên `Query` không mặc định chạy mọi entity lifecycle callback/auditing như khi chuyển đổi và lưu một entity đầy đủ.
- Bạn cần kiểm tra số document khớp và thực sự thay đổi thay vì dựa vào lời gọi không phát sinh exception.
- Query quá rộng có thể sửa dữ liệu ngoài phạm vi nghiệp vụ; luôn kiểm tra tenant, trạng thái, ngày và quyền trước khi chạy.

### 4.3. Cập nhật một số field mà không ghi thay thế document

~~~java
Update change = new Update()
    .set("delivery.city", "Hải Phòng")
    .unset("delivery.note")
    .inc("retryCount", 1);

template.updateMulti(
    Query.query(Criteria.where("tenantId").is("t01")
        .and("state").is("NEW")),
    change,
    OrderDocument.class
);
~~~

`$set` sửa `delivery.city`, `$unset` loại trường `delivery.note`, `$inc` tăng bộ đếm. Những trường khác, như `total_vnd` và `tags`, vẫn được giữ nguyên. Đây là ưu điểm so với đọc một phần entity rồi gọi `save`: ghi thay thế entity thiếu field có thể làm mất dữ liệu không được tải.

### 4.4. Cập nhật nhiều document và hiệu năng

`updateMulti` phù hợp khi mọi document khớp cần nhận **cùng một tập update operator**. Nếu mỗi document cần giá trị khác nhau, hãy cân nhắc:

- Nhiều lời gọi `updateFirst` với filter theo khóa.
- `BulkOperations` để gom nhiều thao tác update khác nhau.
- Aggregation pipeline update nếu giá trị mới phụ thuộc vào field hiện tại của từng document.

Đừng dùng `updateMulti(new Query(), ...)` trên môi trường thật nếu không chủ đích cập nhật toàn collection. `new Query()` không giới hạn document; một lỗi thiếu filter có thể rất nghiêm trọng.

## 5. Bảng so sánh `updateFirst` và `updateMulti`

| Tiêu chí | `updateFirst` | `updateMulti` |
| --- | --- | --- |
| Số document mục tiêu | Tối đa 1 | Tất cả document khớp |
| MongoDB tương đương | `updateOne` | `updateMany` |
| Trả về | `UpdateResult` | `UpdateResult` |
| Không có document khớp | `matchedCount = 0` | `matchedCount = 0` |
| Có `@Version` và metadata entity | Có thể tự tăng version | Có thể tự tăng version trên các document bị update |
| Tính nguyên tử | Nguyên tử cho document được cập nhật | Nguyên tử **theo từng document**, không phải toàn tập |
| Hạn chế nguy cơ update nhầm | Filter theo `_id` và trạng thái | Filter tenant, trạng thái, thời gian, phạm vi chính xác |
| Khi cần chọn theo sort | Xem yêu cầu phiên bản MongoDB; `findAndModify` là lựa chọn phổ biến | Không phải API chọn “một document theo thứ tự” |
| Khi cần thêm document nếu không khớp | Không; dùng `upsert` | Không; dùng `upsert`, không phải multi |

Điểm thực hành: **xóa hoặc sửa nhiều document không đồng nghĩa gọi lại một API một document nhiều lần**. Phải chọn theo cả **số lượng đích**, **mức nhất quán cần thiết**, **cách xử lý xung đột** và **hình dạng kết quả trả về**.

## 6. Fluent update: cùng ngữ nghĩa, cách viết rõ luồng hơn

Spring Data MongoDB cung cấp cú pháp fluent bắt đầu từ `MongoTemplate.update(Entity.class)`, sau đó chỉ định điều kiện, update và hành động cuối:

~~~java
template.update(OrderDocument.class)
    .matching(query)
    .apply(update)
    .first();
~~~

Cú pháp này giúp đọc theo thứ tự:

~~~text
update(OrderDocument.class)
      .matching(điều kiện)
      .apply(thao tác ghi)
      .first() | .all() | .upsert()
~~~

### 6.1. Fluent `.first()`

~~~java
UpdateResult result = template.update(OrderDocument.class)
    .matching(
        Criteria.where("id").is("o301")
            .and("tenantId").is("t01")
            .and("state").is("NEW")
    )
    .apply(
        new Update()
            .set("state", "PROCESSING")
            .inc("retryCount", 1)
    )
    .first();
~~~

`.matching(...)` có thể nhận `Criteria` hoặc `Query` tùy overload của fluent API. `.first()` thực hiện update một document và trả `UpdateResult`.

**Quan trọng:** dòng này **không tự thực thi chỉ vì gọi `apply(...)`**; với API fluent, terminal operation `first()` là điểm thực hiện thao tác đồng bộ. Điều này khác việc xây `Update` chỉ mới mô tả các operator.

### 6.2. Fluent `.all()`

~~~java
UpdateResult result = template.update(OrderDocument.class)
    .matching(
        Criteria.where("tenantId").is("t01")
            .and("state").is("NEW")
    )
    .apply(
        new Update()
            .set("state", "QUEUED")
            .addToSet("tags", "batch-queued")
    )
    .all();
~~~

`.all()` là biến thể fluent của `updateMulti`, không phải `findAll`. Nó cập nhật mọi document khớp query và trả `UpdateResult`, không trả một `List<OrderDocument>` đã được tải lại.

### 6.3. Fluent `.upsert()`

~~~java
UpdateResult result = template.update(OrderDocument.class)
    .matching(
        Criteria.where("id").is("o399")
            .and("tenantId").is("t01")
    )
    .apply(
        new Update()
            .set("state", "NEW")
            .set("totalVnd", 180000L)
            .setOnInsert("retryCount", 0)
            .setOnInsert("tags", java.util.List.of())
    )
    .upsert();
~~~

Nếu không có document khớp, `upsert()` chèn document mới dựa trên điều kiện equality có thể áp dụng và nội dung update. Nếu đã có, nó cập nhật document khớp. `setOnInsert(...)` chỉ áp dụng ở **nhánh insert**; nó không ghi đè giá trị của document cũ.

Khác với `updateMulti`, upsert thông thường là thao tác **một document**, không phải yêu cầu tạo hàng loạt document cho mọi giá trị có thể có. Dùng một khóa duy nhất/index và thiết kế **idempotency** để tránh tạo trùng logic dưới ghi đồng thời.

### 6.4. Bảng ánh xạ API trực tiếp ↔ fluent

| API trực tiếp | API fluent tương đương về ý nghĩa |
| --- | --- |
| `template.updateFirst(query, update, OrderDocument.class)` | `template.update(OrderDocument.class).matching(query).apply(update).first()` |
| `template.updateMulti(query, update, OrderDocument.class)` | `template.update(OrderDocument.class).matching(query).apply(update).all()` |
| `template.upsert(query, update, OrderDocument.class)` | `template.update(OrderDocument.class).matching(query).apply(update).upsert()` |

Phương thức `update(...)` của fluent API không phải `Update` object. Vế đầu chọn **entity/collection**; `.apply(new Update()...)` mới cung cấp những thay đổi cụ thể.

### 6.5. Khi nào ưu tiên fluent?

Fluent phù hợp với service có nhiều bước lựa chọn collection/query/update, cần biểu diễn rõ luồng “chọn domain → chọn điều kiện → áp operator → quyết định one/all/upsert”.

API trực tiếp vẫn phù hợp với code hiện có hoặc nơi `Query` và `Update` được xây dựng riêng. Chọn một phong cách nhất quán với dự án; không đổi chỉ vì “fluent trông mới hơn” khi ý nghĩa xử lý không thay đổi.

## 7. Đọc `UpdateResult`: matched khác modified

Cả `updateFirst`, `updateMulti` và fluent terminal operations đều trả `com.mongodb.client.result.UpdateResult` trong API đồng bộ.

~~~java
UpdateResult result = template.updateFirst(
    query, update, OrderDocument.class
);

if (!result.wasAcknowledged()) {
    throw new IllegalStateException(
        "Cannot verify unacknowledged MongoDB update"
    );
}

long matched = result.getMatchedCount();
long modified = result.getModifiedCount();
var upsertedId = result.getUpsertedId();
~~~

| Giá trị | Diễn giải |
| --- | --- |
| `wasAcknowledged()` | Server đã xác nhận thao tác theo write concern phù hợp chưa? |
| `getMatchedCount()` | Bao nhiêu document khớp **filter update** |
| `getModifiedCount()` | Bao nhiêu document thực sự bị thay đổi |
| `getUpsertedId()` | ID document mới tạo bởi upsert, nếu có và được server báo |

### 7.1. Ví dụ matched = 1 nhưng modified = 0

Một update đặt field về chính giá trị hiện có có thể khớp document nhưng không thay đổi dữ liệu:

~~~javascript
db.orders_updates_demo_003.updateOne(
  { _id: "o303" },
  { $set: { state_code: "PAID" } }
);
// Với dữ liệu gốc: matchedCount=1, modifiedCount=0.
~~~

Khi chạy qua `MongoTemplate` với entity có `@Version`, có một chi tiết khác: framework **có thể tự tăng version**, nên ngay cả khi `$set` ghi lại một giá trị giống cũ, document vẫn thay đổi do field `version` tăng. Vì thế khi kiểm chứng matched/modified, **phải biết update thực tế có bao gồm version hoặc các field tự động khác không**.

### 7.2. Ví dụ matched = 0

~~~java
UpdateResult result = template.updateFirst(
    Query.query(Criteria.where("id").is("o999")),
    new Update().set("state", "PAID"),
    OrderDocument.class
);
// Không có o999: matchedCount=0, không tự tạo document.
~~~

`updateFirst` và `updateMulti` **không upsert mặc định**. Nếu phải tạo khi thiếu, chủ động gọi `upsert`. Đừng hiểu “không có exception” là “đã cập nhật một document”.

### 7.3. Dùng `UpdateResult` để thiết kế API nghiệp vụ

~~~java
public boolean markProcessing(String id, MongoTemplate template) {
    UpdateResult result = template.updateFirst(
        Query.query(
            Criteria.where("id").is(id)
                .and("state").is("NEW")
        ),
        new Update().set("state", "PROCESSING"),
        OrderDocument.class
    );

    if (!result.wasAcknowledged()) {
        throw new IllegalStateException("Write not acknowledged");
    }
    return result.getMatchedCount() == 1;
}
~~~

`false` nghĩa là không có document khớp **cả ID và trạng thái NEW**. Nó **không tự phân biệt** ID không tồn tại với order đang ở trạng thái khác. Nếu HTTP API cần phân biệt `404` và `409`, có thể truy vấn lại, nhưng phải hiểu dữ liệu có thể thay đổi thêm giữa hai thao tác.

## 8. Toán tử `Update` thường dùng

`Update` là builder cho các operator của MongoDB, không phải một entity mới:

| Spring Data `Update` | BSON tương ứng | Ý nghĩa |
| --- | --- | --- |
| `set("state", "PAID")` | `$set` | Gán/thay giá trị field |
| `unset("delivery.note")` | `$unset` | Xóa hẳn field khỏi document |
| `inc("retryCount", 1)` | `$inc` | Cộng vào trường số |
| `mul("totalVnd", 2)` | `$mul` | Nhân một trường số |
| `addToSet("tags", "new")` | `$addToSet` | Thêm phần tử vào array nếu chưa tồn tại |
| `push("tags", "new")` | `$push` | Thêm phần tử vào array, có thể trùng |
| `pull("tags", "old")` | `$pull` | Loại phần tử khớp |
| `setOnInsert("state", "NEW")` | `$setOnInsert` | Chỉ gán khi upsert tạo document |
| `currentDate("updatedAt")` | `$currentDate` | Gán ngày/giờ hiện tại từ MongoDB |

### 8.1. `set(null)` khác `unset`

~~~java
// Viết BSON null tường minh.
new Update().set("delivery.note", null);

// Loại trường delivery.note khỏi document.
new Update().unset("delivery.note");
~~~

Hai thao tác khác nhau khi truy vấn bằng `$exists` hoặc `$type`. Không coi Java `null` trong API PATCH mặc nhiên có nghĩa `$unset` hoặc `$set`; hợp đồng API phải quy định điều đó.

### 8.2. Vì sao `$inc` thường an toàn hơn read–modify–save?

Giả sử hai request cùng đọc `retryCount=1` rồi đều muốn tăng lên 2:

~~~text
Request A đọc 1 -> tính 2
Request B đọc 1 -> tính 2
A ghi 2, B ghi 2
Kết quả 2 thay vì 3.
~~~

Với `Update.inc("retryCount", 1)`, mỗi update là thao tác nguyên tử trên document; nếu cả hai update được áp dụng thành công, bộ đếm tăng hai lần theo quy tắc MongoDB. Cần bảo đảm field có kiểu số phù hợp; nếu đang lưu chuỗi hoặc null sai kiểu, `$inc` có thể lỗi.

### 8.3. Cập nhật trường trong array

Nếu entity có mảng nhúng `lines`, MongoDB hỗ trợ positional operator để sửa một phần tử khớp:

~~~javascript
db.orders_updates_demo_003.updateOne(
  { _id: "o301", "lines.sku": "A" },
  { $inc: { "lines.$.quantity": 1 } }
);
~~~

Fixture bài này không có trường `lines`, vì vậy đoạn trên chỉ **minh họa cú pháp**, không làm thay đổi document gốc. Khi dùng Spring Data, có thể biểu diễn qua `Update.inc("lines.$.quantity", 1)` và `Criteria.where("lines.sku").is("A")` nếu entity có mảng tương ứng.

Với yêu cầu cập nhật nhiều phần tử mảng theo điều kiện, có thể dùng **filtered positional operator** `$[identifier]` cùng `arrayFilters`; cần bảo đảm phiên bản MongoDB/driver phù hợp, tên BSON đúng và kiểm thử trên dữ liệu mảng thực.

### 8.4. Không được sửa `_id` bằng update thông thường

MongoDB không cho phép đổi `_id` của document đã tồn tại bằng `$set`:

~~~javascript
db.orders_updates_demo_003.updateOne(
  { _id: "o301" },
  { $set: { _id: "o999" } }
);
// Không hợp lệ: _id là khóa định danh bất biến.
~~~

Khi cần đổi định danh, phải thiết kế migration tạo document mới, xử lý tham chiếu và xóa cũ theo chính sách. Đây không phải chức năng của `Update.set("id", ...)`.

## 9. `@Version`: tăng version không có nghĩa tự kiểm tra version cũ

Ví dụ entity khai báo:

~~~java
@Version
private Long version;
~~~

Với thao tác update **có cung cấp entity class**, Spring Data MongoDB tự tăng thuộc tính version nếu phiên bản không được nhắc đến tường minh trong `Update`. Điều này áp dụng cho `updateFirst`, `updateMulti` và fluent update trên entity phù hợp.

**Nhưng phải tách hai việc:**

1. **Tăng version:** framework thêm cập nhật version khi phù hợp.
2. **Kiểm tra version kỳ vọng:** query phải có điều kiện version đúng nếu nghiệp vụ muốn từ chối writer đã đọc dữ liệu cũ.

Một `updateFirst` theo `_id` mà **không** ràng buộc `version` vẫn có thể cập nhật document đã thay đổi trước đó. Việc auto-increment version đơn thuần không biến nó thành optimistic lock theo phiên bản đã đọc.

### 9.1. Update có điều kiện version

~~~java
long expectedVersion = 0L;

Query query = Query.query(
    Criteria.where("id").is("o301")
        .and("state").is("NEW")
        .and("version").is(expectedVersion)
);

UpdateResult result = template.updateFirst(
    query,
    new Update().set("state", "PROCESSING"),
    OrderDocument.class
);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
        "Order not found, state changed, or stale version"
    );
}
~~~

Với fixture ban đầu, `o301` có `version=0`. Nếu writer khác đã tăng version lên 1, filter có `version=0` không còn khớp và update không thực thi. Với metadata entity, Spring Data sẽ tăng version trên document khi update thành công, nếu `Update` chưa cập nhật version tường minh.

### 9.2. So sánh với `save(entity)`

Khi tải entity có `@Version` rồi gọi `MongoTemplate.save(entity)`, framework có thể dùng version của entity đã đọc để kiểm soát ghi trùng và phát sinh `OptimisticLockingFailureException` khi không khớp.

Ngược lại, với `updateFirst(Query, Update, Class)`, chính service **tự đưa version kỳ vọng vào query** khi cần bảo vệ khỏi update stale. Không nên giả định template biết version mà client đã thấy nếu bạn chỉ truyền `_id`.

### 9.3. Không tự tăng version hai lần

Nếu `Update` đã thao tác tường minh trên version, Spring Data không còn cùng cơ chế tự thêm tăng version mặc định. Vì vậy phải thống nhất một chính sách:

- Để framework tự tăng version (trong thao tác mapped phù hợp).
- Hoặc chủ động xử lý trường version bằng update có điều kiện, kiểm tra đúng kiểu BSON và kết quả.

Đừng vừa gọi `inc("version", 1)` vừa cộng thêm 1 ở tầng nghiệp vụ trong một luồng không thống nhất. Đặc biệt với overload **chỉ truyền tên collection**, không có entity metadata nên không kỳ vọng auto-versioning giống overload theo class.

## 10. Thứ tự khi `updateFirst` có nhiều document khớp

Một câu hỏi phổ biến:

> Muốn lấy đơn hàng NEW **cũ nhất** và chuyển nó sang PROCESSING, có dùng `updateFirst` kèm `Sort` được không?

Tài liệu Spring Data MongoDB lưu ý: **`updateFirst` không hỗ trợ ordering trên MongoDB trước 8.0**. Với server cũ, không thể trông đợi `Query.with(Sort)` quyết định document nào bị update bởi `updateFirst`.

Để chọn theo sort trên các phiên bản đó, dùng `findAndModify`:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.FindAndModifyOptions;

Query oldest = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("state").is("NEW")
);

oldest.with(
    Sort.by(Sort.Order.asc("createdAt"), Sort.Order.asc("id"))
);

OrderDocument updated = template.findAndModify(
    oldest,
    new Update().set("state", "PROCESSING"),
    FindAndModifyOptions.options().returnNew(true),
    OrderDocument.class
);
~~~

**Chú ý:** fixture hiện tại chưa có `createdAt` trong entity/document. Đoạn này là **mẫu thiết kế khi mô hình thực có thêm `createdAt` thuộc kiểu ngày hợp lệ**, không phải lệnh chạy nguyên xi trên bộ dữ liệu đã nạp. Phải thiết kế index theo filter và sort, đồng thời có khóa duy nhất làm tie-breaker.

`findAndModify` có thể trả entity **trước** update (mặc định) hoặc **sau** update (`returnNew(true)`), còn `updateFirst` trả `UpdateResult` chứ không trả entity. Với MongoDB từ 8.0, có khả năng hỗ trợ sort khi updateOne tùy driver/server/API; khi cần tính di động giữa các phiên bản hoặc trả entity sau cập nhật, `findAndModify` vẫn là lựa chọn dễ diễn đạt rõ mục tiêu.

**Tránh mẫu hai thao tác:** `find(...).sort(...).first()` rồi `updateFirst(byId, ...)` nếu cần “claim công việc” nguyên tử, bởi writer khác có thể cập nhật document giữa lúc đọc và lúc ghi.

## 11. `upsert` và `$setOnInsert`

`upsert` là “update hoặc insert”:

~~~java
UpdateResult result = template.upsert(
    Query.query(
        Criteria.where("id").is("o399")
            .and("tenantId").is("t01")
    ),
    new Update()
        .set("state", "NEW")
        .set("totalVnd", 180000L)
        .setOnInsert("retryCount", 0)
        .setOnInsert("tags", java.util.List.of()),
    OrderDocument.class
);
~~~

Fluent tương đương:

~~~java
UpdateResult result = template.update(OrderDocument.class)
    .matching(Criteria.where("id").is("o399")
        .and("tenantId").is("t01"))
    .apply(new Update()
        .set("state", "NEW")
        .set("totalVnd", 180000L)
        .setOnInsert("retryCount", 0)
        .setOnInsert("tags", java.util.List.of()))
    .upsert();
~~~

Nếu tạo document mới, `getUpsertedId()` có thể cho biết `_id` vừa tạo, và `getMatchedCount()` thường bằng 0. Nếu document đã tồn tại, `$set` áp dụng ở nhánh update còn `$setOnInsert` không làm thay đổi giá trị hiện có.

### 11.1. Chọn filter upsert tránh sinh trùng logic

Nếu khóa tự nhiên là `externalOrderId`, hãy định nghĩa unique index phù hợp. Chỉ viết:

~~~java
template.upsert(
    Query.query(Criteria.where("externalOrderId").is(externalId)),
    update,
    OrderDocument.class
);
~~~

thì chưa chắc đã đủ chống hai request đồng thời cùng tạo một order. Unique index trên khóa nghiệp vụ giúp server ngăn trùng, nhưng caller vẫn cần xử lý duplicate key/retry phù hợp.

Ngoài ra, `upsert` không hỗ trợ ordering theo nghĩa chọn document nào trong nhiều kết quả; nếu yêu cầu sắp xếp, xem `findAndModify`. `updateMulti` không phải biến thể của upsert nhiều document.

### 11.2. Giá trị mặc định được đặt ở đâu?

| Cách đặt mặc định | Khi có hiệu lực |
| --- | --- |
| Java field initializer | Khi đối tượng Java được tạo và mapping xử lý |
| `new Update().setOnInsert("state", "NEW")` | Chỉ khi **upsert tạo mới** |
| `new Update().set("state", "NEW")` | Khi update và cả nhánh insert của upsert |
| MongoDB `$ifNull` trong aggregation | Khi đọc/tính kết quả, không sửa document gốc |

Đừng dùng `setOnInsert` để “sửa tất cả record cũ đang thiếu field” — nó không có tác dụng trên document đã tồn tại. Khi backfill, dùng `updateMulti` với filter missing/null đúng ý định.

## 12. Aggregation pipeline update khi giá trị phụ thuộc chính document

`Update` thông thường rất tiện cho các operator `$set`/`$inc`, nhưng có tình huống cần giá trị mới là biểu thức của nhiều field. MongoDB hỗ trợ **update with aggregation pipeline** (MongoDB 4.2+), và Spring Data MongoDB có `AggregationUpdate`.

Giả sử cần tính phí xử lý bằng 5% tổng tiền, giá trị ở `totalVnd` hiện tại (chỉ minh họa, không phải quy tắc tiền tệ production):

~~~java
import org.springframework.data.mongodb.core.aggregation.AggregationUpdate;

AggregationUpdate pipeline = AggregationUpdate.update()
    .set("processingFeeVnd")
    .toValue(
        org.springframework.data.mongodb.core.aggregation
            .ArithmeticOperators.Multiply.valueOf("totalVnd")
            .multiplyBy(0.05)
    );

UpdateResult changed = template.update(OrderDocument.class)
    .matching(Criteria.where("tenantId").is("t01")
        .and("state").is("PAID"))
    .apply(pipeline)
    .all();
~~~

`processingFeeVnd` ở đây chưa khai báo trong entity; ví dụ chỉ minh họa ý tưởng tạo field mới. Khi triển khai thật, hãy thêm property tương ứng, chọn kiểu số tiền phù hợp (thường `Decimal128`/`BigDecimal` thay cho `double` cho nghiệp vụ tài chính) và kiểm tra độ chính xác/rounding.

**Phân biệt:** pipeline update tính trên mỗi document và có tập stage được MongoDB cho phép trong update pipeline; nó không phải toàn bộ aggregation pipeline dùng cho báo cáo. Chỉ dùng khi bài toán thật sự cần tính toán từ field khác, không thay một `Update.inc(...)` đơn giản bằng pipeline phức tạp không cần thiết.

## 13. Dùng `@Query`/repository khi nào?

`MongoRepository.save(entity)` thuận tiện với một aggregate hoàn chỉnh, nhưng các cập nhật một vài field theo điều kiện thường dễ diễn đạt hơn qua `MongoTemplate` hoặc repository update method có annotation phù hợp.

Với repository, phải phân biệt các tên:

- `findBy...`: tạo query để tìm và đọc.
- `deleteBy...`: tạo thao tác xóa theo quy tắc repository.
- `@Update` trên repository method: có thể khai báo thao tác cập nhật theo query, tùy cơ chế và phiên bản Spring Data MongoDB.

Không nên tự động suy rằng đặt tên method `updateByState(...)` là framework sẽ tự biết nên `$set` field nào. Trong một bài về `MongoTemplate`, cách rõ ràng nhất là viết `Query`, `Update` và chọn `updateFirst`/`updateMulti`/fluent terminal operation. Điều này còn giúp kiểm soát trực tiếp `UpdateResult`.

## 14. Tính nguyên tử, transaction và các cập nhật hàng loạt

### 14.1. Một document là đơn vị nguyên tử thông thường

Với `updateFirst` có filter chính xác `_id` và trạng thái kỳ vọng, việc kiểm tra điều kiện và áp dụng các operator trên **document đó** là nguyên tử.

Với `updateMulti`, mỗi document được cập nhật theo nguyên tắc nguyên tử, nhưng toàn bộ nhiều document **không mặc định cùng commit hoặc rollback** như một transaction nhiều document. Nếu một thao tác bị gián đoạn giữa chừng, cần xem kết quả, trạng thái thực tế và chiến lược retry.

### 14.2. Transaction khi cần all-or-nothing

~~~java
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class MongoTxConfiguration {
    @Bean("mongoTransactionManager")
    MongoTransactionManager transactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BatchOrderService {
    private final MongoTemplate template;

    public BatchOrderService(MongoTemplate template) {
        this.template = template;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void markOrdersForReview(String tenantId) {
        template.updateMulti(
            Query.query(Criteria.where("tenantId").is(tenantId)
                .and("state").is("NEW")),
            new Update().set("state", "REVIEW"),
            OrderDocument.class
        );

        template.updateFirst(
            Query.query(Criteria.where("id").is("o306")
                .and("tenantId").is(tenantId)),
            new Update().addToSet("tags", "review-batch"),
            OrderDocument.class
        );
    }
}
~~~

Mã trên mô tả **hai thao tác trong một transaction** nếu cấu hình đúng. MongoDB cần topology hỗ trợ transaction (ví dụ replica set hoặc sharded cluster phù hợp), Spring cần `MongoTransactionManager`, và template phải dùng database factory/session tương ứng. Nếu gọi method nội bộ không đi qua Spring transaction proxy, `@Transactional` có thể không có hiệu lực.

Một transaction lớn cập nhật hàng trăm nghìn document thường tốn chi phí, có giới hạn thời gian/tài nguyên và không phải lựa chọn mặc định. Cân nhắc chia lô, job có checkpoint, retry idempotent hoặc thay đổi mô hình dữ liệu khi phù hợp.

### 14.3. Update lặp lại và idempotency

Xét:

~~~java
new Update().set("state", "REVIEW"); // Gần idempotent theo một field.
new Update().inc("retryCount", 1);  // Không idempotent nếu chạy lại.
~~~

Chạy lại `$set` cùng một giá trị thường không đổi giá trị field (nhưng `@Version` và những side effect khác có thể vẫn thay đổi). Chạy lại `$inc` sẽ tăng bộ đếm lần nữa. Khi gặp retry sau timeout không rõ thao tác trước đã commit chưa, phải thiết kế idempotency key, trạng thái điều kiện hoặc một cơ chế xử lý “đã áp dụng” rõ ràng; **không retry mù** `$inc`.

## 15. Index và hiệu năng cho update theo query

MongoDB phải **tìm các document khớp query** trước khi áp update. Với filter:

~~~javascript
{ tenant_id: "t01", state_code: "NEW" }
~~~

index:

~~~javascript
orders.createIndex({
  tenant_id: 1,
  state_code: 1
});
~~~

có thể giúp tìm các ứng viên. Nhưng hiệu năng phụ thuộc độ chọn lọc, số document thực sự ghi, kích thước document, replication, contention và index khác phải cập nhật.

### 15.1. Đừng đo update bằng mỗi số document trả về

`updateMulti` không trả danh sách document. Hãy ghi nhận:

- `getMatchedCount()` và `getModifiedCount()` (khi acknowledged).
- Thời gian thực thi, p95/p99 khi có tải.
- Số document theo tenant/trạng thái trước-sau khi cần kiểm chứng.
- Việc sử dụng index ở bước tìm ứng viên, quan sát qua query find cùng filter và `explain("executionStats")` trong môi trường đo.
- Áp lực I/O, oplog/replication, write conflict và chi phí cập nhật index.

`explain()` trên truy vấn `find` cùng filter hữu ích để kiểm tra kế hoạch chọn document, nhưng không đo đầy đủ chi phí ghi thực tế của lệnh update.

### 15.2. Update nhiều document nhưng mỗi document có điều kiện riêng

Nếu cần:

~~~text
o301 -> PROCESSING
o302 -> PAID
o305 -> MANUAL_REVIEW
~~~

thì **một** `updateMulti` không diễn đạt được ba `$set` khác nhau chỉ bằng cùng một `Update` đơn giản. Có thể dùng:

- Ba `updateFirst` có filter ID.
- `BulkOperations` để gom nhiều lệnh khác nhau vào một bulk operation.
- Pipeline update với điều kiện `$switch`/$cond` khi thực sự phù hợp.

`BulkOperations` là công cụ khác `updateMulti`, có semantics kết quả và ordering riêng; không nên thay thế chúng mà không kiểm tra yêu cầu transaction, version và audit.

## 16. ReactiveMongoTemplate và fluent update

Spring Data MongoDB có API reactive tương ứng. Điểm khác là **kết quả là publisher**, không phải `UpdateResult` ngay lập tức:

~~~java
import reactor.core.publisher.Mono;
import com.mongodb.client.result.UpdateResult;

Mono<UpdateResult> one = reactiveTemplate.update(OrderDocument.class)
    .matching(Criteria.where("id").is("o301"))
    .apply(new Update().set("state", "PROCESSING"))
    .first();

Mono<UpdateResult> all = reactiveTemplate.update(OrderDocument.class)
    .matching(Criteria.where("tenantId").is("t01")
        .and("state").is("NEW"))
    .apply(new Update().set("state", "QUEUED"))
    .all();

Mono<UpdateResult> upserted = reactiveTemplate.update(OrderDocument.class)
    .matching(Criteria.where("id").is("o399"))
    .apply(new Update().set("state", "NEW"))
    .upsert();
~~~

`reactiveTemplate` là `ReactiveMongoTemplate` đã inject; những publisher trên **chỉ thực thi khi có subscriber**. Trong ứng dụng WebFlux, nên trả hoặc compose `Mono` vào reactive chain, không gọi `block()` trong event loop.

Khi cần transaction reactive, dùng `ReactiveMongoTransactionManager` và `TransactionalOperator` hoặc `@Transactional` được cấu hình phù hợp. Reactive không thay đổi ý nghĩa `updateFirst`/`updateMulti` và không tự làm write operation nhiều document thành transaction.

## 17. Kiểm thử thực tế với MongoDB và Spring Data mapping

Unit test mock `MongoTemplate` chỉ kiểm tra việc gọi method. Nó **không** chứng minh query được ánh xạ `state → state_code`, `@Version` tự tăng hay MongoDB áp `$inc` đúng kiểu. Với cập nhật quan trọng, cần integration test trên MongoDB test instance hoặc Testcontainers.

### 17.1. Ma trận kiểm thử

| Kịch bản | Điều cần xác minh |
| --- | --- |
| `updateFirst` theo ID và state | Chỉ một document thay đổi |
| `updateFirst` với ID không tồn tại | `matchedCount=0`, không upsert |
| `updateMulti` theo tenant/state | Chỉ mọi document thuộc đúng phạm vi bị cập nhật |
| Fluent `first/all` | Cùng semantics với API trực tiếp |
| Fluent `upsert` | Chèn khi không khớp, có `getUpsertedId()` |
| `@Field("state_code")` | Query/update dùng property Java được ánh xạ đúng BSON |
| `@Version` | Tăng version khi update mapped và không chỉ định field này |
| Filter có version kỳ vọng | Không update bản stale |
| `set(null)` và `unset` | Phân biệt BSON null và missing |
| `$inc` chạy hai lần | Đúng số lần tăng, không coi retry là idempotent |
| Ghi đồng thời hai document | Không giả định transaction nếu chưa cấu hình |
| Reactive fluent update | Publisher được subscribe và trả `UpdateResult` phù hợp |

### 17.2. Integration test minh họa

Test tạo hai fixture thuộc tenant riêng, rồi kiểm tra một update và một fluent update; không chạm tới các document bài học:

~~~java
package com.example.orderupdates;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.model.Filters;

@DataMongoTest
class OrderUpdateIntegrationTest {
    @Autowired MongoTemplate template;

    @Test
    void updatesOneThenAllAndMapsFieldAliases() {
        var collection = template.getDb()
            .getCollection("orders_updates_demo_003");
        List<String> ids = List.of("fixture-003-a", "fixture-003-b");

        collection.deleteMany(Filters.in("_id", ids));
        try {
            collection.insertMany(List.of(
                new Document("_id", ids.get(0))
                    .append("tenant_id", "fixture-tenant-003")
                    .append("state_code", "NEW")
                    .append("retry_count", 0)
                    .append("version", 0L),
                new Document("_id", ids.get(1))
                    .append("tenant_id", "fixture-tenant-003")
                    .append("state_code", "NEW")
                    .append("retry_count", 0)
                    .append("version", 0L)
            ));

            var one = template.updateFirst(
                Query.query(Criteria.where("id").is(ids.get(0))),
                new Update().set("state", "PROCESSING"),
                OrderDocument.class
            );
            assertThat(one.getMatchedCount()).isEqualTo(1L);

            var all = template.update(OrderDocument.class)
                .matching(Criteria.where("tenantId")
                    .is("fixture-tenant-003")
                    .and("state").is("NEW"))
                .apply(new Update().inc("retryCount", 1))
                .all();
            assertThat(all.getMatchedCount()).isEqualTo(1L);

            Document first = collection.find(
                Filters.eq("_id", ids.get(0))
            ).first();
            Document second = collection.find(
                Filters.eq("_id", ids.get(1))
            ).first();

            assertThat(first).isNotNull();
            assertThat(first.getString("state_code"))
                .isEqualTo("PROCESSING");
            assertThat(second).isNotNull();
            assertThat(second.getInteger("retry_count"))
                .isEqualTo(1);
            assertThat(first.containsKey("state")).isFalse();
        } finally {
            collection.deleteMany(Filters.in("_id", ids));
        }
    }
}
~~~

**Chỉ chạy trên database test biệt lập**: test có thao tác xóa hai ID fixture ở setup/cleanup. Để kiểm tra optimistic locking đầy đủ, cần test thứ hai với version kỳ vọng, đọc lại BSON version và xác nhận update stale có `matchedCount = 0`. Test transaction phải dùng MongoDB topology thực sự hỗ trợ transaction.

### 17.3. Không dựa vào output Java để suy ra BSON gốc

Để xác nhận mapping `state` → `state_code`, kiểm tra document thô:

~~~javascript
db.orders_updates_demo_003.findOne(
  { _id: "fixture-003-a" },
  { _id: 1, state_code: 1, state: 1, version: 1 }
);
~~~

Nếu test đã dọn fixture, truy vấn này trả `null`. Chỉ dùng để đối chiếu **trong lúc fixture đang tồn tại**, hoặc thay bằng ID riêng trong môi trường học tập. Không chạy trên dữ liệu production để phán đoán hành vi từ một ví dụ không cùng schema.

## 18. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `updateFirst` không sửa document nào | Sai database, collection, ID, mapping field, state hoặc version trong filter | Xem `matchedCount` và document BSON thực |
| `updateFirst` sửa “order bất kỳ” | Filter khớp nhiều document nhưng không chọn khóa duy nhất | Dùng `_id` hoặc `findAndModify` với sort |
| Thêm `Sort` vẫn không chọn đúng order ở MongoDB cũ | `updateFirst` không hỗ trợ sort trên server trước 8.0 | Dùng `findAndModify` |
| `updateMulti` chỉ sửa một phần dữ liệu mong đợi | Filter tenant/state quá hẹp, writer đồng thời hoặc gián đoạn | Xem `matchedCount`, query và dữ liệu sau ghi |
| `modifiedCount=0` dù `matchedCount>0` | Gán cùng giá trị hiện có, hoặc thực tế update không đổi BSON | Xem operator và auto-version |
| Một update vẫn làm version tăng | `@Version` mapped và field version không được chỉ định tường minh | So sánh BSON trước/sau; tách auto-increment khỏi optimistic check |
| Cập nhật bản stale vẫn thành công | Query không có điều kiện version kỳ vọng | Thêm `Criteria.where("version")` |
| Raw update tạo field `state` ngoài ý muốn | Dùng tên property Java trong MongoDB driver trực tiếp | Dùng BSON field `state_code` trong driver hoặc mapped update |
| `upsert` sinh document ngoài dự kiến | Nhầm update với upsert hoặc filter quá rộng/không có unique key | Rà soát `getUpsertedId`, index và filter |
| `setOnInsert` không sửa document cũ | Operator chỉ chạy khi upsert chèn mới | Dùng `set` hoặc backfill có điều kiện |
| `$inc` tăng bộ đếm hai lần | Retry không có idempotency | Dùng điều kiện trạng thái/dấu sự kiện hoặc idempotency key |
| `$unset` làm field biến mất | Đúng semantics, không phải BSON null | Dùng `set(field, null)` nếu muốn null |
| Update nhiều document gặp lỗi giữa chừng | Không có transaction bao trùm | Thiết kế transaction hoặc job retry/compensation |
| Reactive update không có tác dụng | `Mono` chưa subscribe | Compose/subscribe và kiểm tra `UpdateResult` |
| Update theo state chậm | Thiếu index, filter không chọn lọc hoặc nhiều write conflict | Xem execution plan và metric ghi |

## 19. Bài thực hành

Mỗi bài dưới đây giả định bạn nạp lại fixture ở mục 2; **không chạy nối tiếp những bài cập nhật trên cùng một trạng thái dữ liệu**.

### Bài 1 — Chọn API

Yêu cầu: chuyển **một** order có `_id = o301` từ NEW sang PROCESSING. Nên dùng gì?

**Đáp án:**

~~~java
template.updateFirst(
    Query.query(Criteria.where("id").is("o301")
        .and("state").is("NEW")),
    new Update().set("state", "PROCESSING"),
    OrderDocument.class
);
~~~

Fluent tương đương dùng `template.update(OrderDocument.class).matching(...).apply(...).first()`.

### Bài 2 — Cập nhật nhiều document theo tenant

Yêu cầu: tăng `retry_count` thêm 1 cho **tất cả** order NEW của tenant t01. Có bao nhiêu document khớp trong fixture gốc?

**Đáp án:**

~~~java
UpdateResult result = template.update(OrderDocument.class)
    .matching(Criteria.where("tenantId").is("t01")
        .and("state").is("NEW"))
    .apply(new Update().inc("retryCount", 1))
    .all();
// matchedCount=3 trên fixture gốc (o301, o302, o305).
~~~

`o304` thuộc t02 nên không bị thay đổi.

### Bài 3 — Matched khác modified

Một raw MongoDB `updateOne({ _id: "o303" }, { $set: { state_code: "PAID" } })` trả `matchedCount=1, modifiedCount=0`. Có phải query thất bại?

**Đáp án:** Không. Document khớp, nhưng giá trị đã là PAID nên không có khác biệt BSON. Nếu cùng lệnh được chạy qua mapped `MongoTemplate` với `@Version`, phải kiểm tra liệu version được tăng hay không.

### Bài 4 — Optimistic locking thật sự

Entity o301 đã được client đọc tại version 0, nhưng writer khác đã đổi version lên 1. Cần ngăn update stale bằng cách nào?

**Đáp án:** thêm điều kiện `version=0` vào `Query` cùng ID và các điều kiện nghiệp vụ. Nếu `matchedCount=0` thì không ghi; sau đó xử lý conflict. `@Version` auto-increment trong update query **không thay thế** điều kiện version kỳ vọng.

### Bài 5 — Upsert và default

Yêu cầu: nếu `o399` chưa có thì chèn một order t01/NEW với `retryCount=0`; nếu đã có thì đổi `totalVnd` nhưng không reset retryCount.

**Đáp án tham khảo:**

~~~java
template.update(OrderDocument.class)
    .matching(Criteria.where("id").is("o399")
        .and("tenantId").is("t01"))
    .apply(new Update()
        .set("totalVnd", 180000L)
        .setOnInsert("state", "NEW")
        .setOnInsert("retryCount", 0))
    .upsert();
~~~

`setOnInsert` chỉ áp dụng ở nhánh insert; có thể bổ sung unique index nếu có khóa tự nhiên ngoài `_id`.

### Bài 6 — Sort và “order cũ nhất”

Tại sao không nên gọi `updateFirst(query.with(Sort.by("createdAt")), ...)` để “claim order cũ nhất” trên MongoDB 7.x?

**Đáp án:** `updateFirst` không hỗ trợ thứ tự lựa chọn trên MongoDB trước 8.0. Dùng `findAndModify` với `Query.with(Sort)` để chọn và đổi trạng thái trong một thao tác document nguyên tử, trên schema có `createdAt` và index thích hợp.

### Bài 7 — Cập nhật một phần embedded document

Muốn xóa `delivery.note` nhưng vẫn giữ `delivery.city`, dùng operator nào?

**Đáp án:**

~~~java
template.updateFirst(
    Query.query(Criteria.where("id").is("o301")),
    new Update().unset("delivery.note"),
    OrderDocument.class
);
~~~

Không thay toàn bộ `delivery` bằng một object chỉ có `city` nếu mục tiêu chỉ là xóa ghi chú.

### Bài 8 — Tác vụ cập nhật nhiều document và retry

Một batch tăng `retryCount` cho 2.000 order. Kết nối timeout sau khi gửi update; service không biết server đã thực hiện chưa. Có nên retry ngay bằng `$inc`?

**Đáp án:** Không nên retry mù, vì lần đầu có thể đã commit và lần sau sẽ tăng thêm một lần. Thiết kế điều kiện trạng thái, idempotency key hoặc tiến độ batch có thể xác minh; cân nhắc transaction/compensation theo yêu cầu.

## Tài liệu tham khảo

- [Spring Data MongoDB — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `updateFirst`, `updateMulti`, fluent update, `@Version`, upsert và `findAndModify`.
- [Spring Data MongoDB — `MongoOperations` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoOperations.html): overload `updateFirst`/`updateMulti` và kiểu kết quả.
- [Spring Data MongoDB — `Update` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Update.html): builder các update operator.
- [Spring Data MongoDB — Fluent Update API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/FluentMongoOperations.html): `update(Class)`, `matching`, `apply` và terminal operations.
- [MongoDB Manual — Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/): `updateOne`, `updateMany`, tính nguyên tử ở mức document và kết quả ghi.
- [MongoDB Manual — Update Operators](https://www.mongodb.com/docs/manual/reference/operator/update/): `$set`, `$inc`, `$unset`, `$setOnInsert` và các operator khác.
- [MongoDB Manual — Update with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/): tính giá trị cập nhật từ biểu thức trên document.
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): giới hạn cập nhật nhiều document và transaction.
