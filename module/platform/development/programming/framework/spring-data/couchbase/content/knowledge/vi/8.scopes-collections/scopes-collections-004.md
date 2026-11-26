# Chọn scope và collection qua API của Template trong Spring Data Couchbase

Trong Spring Data Couchbase, `CouchbaseTemplate` cung cấp API thao tác trực tiếp với document và truy vấn SQL++ thông qua kiểu thực thể Java. Khi một ứng dụng quản lý nhiều tập dữ liệu trong cùng bucket, ta cần chỉ định **scope** và **collection** ngay tại từng lệnh đọc/ghi. Hai phương thức fluent `inScope()` và `inCollection()` cho phép làm việc này mà không cần thay đổi mapping chung của entity hoặc tạo repository riêng cho mọi collection.

Bài học thuộc chương **Scope và Collection** của module `SPRING_DATA_COUCHBASE`, tập trung vào cách chọn keyspace khi sử dụng `CouchbaseTemplate` và `ReactiveCouchbaseTemplate`. Các ví dụ gắn với thiết kế bucket/scope/collection, document mapping, SQL++, chỉ mục, TTL, CAS và cách lựa chọn API reactive để ứng dụng hoạt động đúng và dễ vận hành.

## 1. Vì sao cần chọn scope và collection ở cấp thao tác?

Giả sử ứng dụng bán hàng dùng một bucket `shop`:

```text
shop  (bucket)
├── _default  (scope)
│   └── _default  (collection)
├── commerce  (scope)
│   ├── orders  (collection)
│   └── customers  (collection)
└── archive  (scope)
    └── orders_history  (collection)
```

Đối với đơn hàng có key `order::1001`, các đường dẫn sau là **hai vị trí dữ liệu độc lập**:

- `shop.commerce.orders`: đơn hàng hiện hành.
- `shop.archive.orders_history`: bản lưu trữ lịch sử.

Mặc dù hai document có thể cùng key, chúng không tự đồng bộ và không cùng một giá trị CAS. Nếu mã truy cập sai scope hoặc collection, lệnh KV theo key có thể báo không tìm thấy document; câu SQL++ có thể trả về kết quả khác mong đợi.

Có ba cách phổ biến để xác định nơi lưu dữ liệu trong Spring Data Couchbase:

| Cách chọn | Phạm vi | Thích hợp khi |
| --- | --- | --- |
| Cấu hình scope nền của ứng dụng | Mặc định cho các thao tác không ghi đè | Phần lớn dữ liệu dùng một scope. |
| `@Scope` và `@Collection` trên entity/repository | Theo model hoặc repository | Mỗi nhóm nghiệp vụ gắn với một collection ổn định. |
| `inScope()` và `inCollection()` của Template | **Theo từng thao tác** | Một luồng cần truy cập nhiều collection hoặc scope. |

**Điểm mấu chốt:** `inScope("archive")` và `inCollection("orders_history")` chỉ định vị trí cho một chuỗi thao tác Template cụ thể. Chúng không di chuyển document, không tạo tài nguyên Couchbase và không thay đổi vĩnh viễn cấu hình của toàn ứng dụng.

## 2. Cơ chế fluent API của CouchbaseTemplate

Spring Data Couchbase triển khai các phép đọc/ghi thông qua **fluent API**: bắt đầu bằng loại thao tác, lựa chọn các tùy chọn, chỉ rõ scope/collection, rồi gọi một hàm kết thúc để thực thi.

```text
couchbaseTemplate
    .<loại thao tác>(OrderDocument.class)
    .inScope("commerce")
    .inCollection("orders")
    .<lệnh kết thúc>
```

Ví dụ hoàn chỉnh:

```java
OrderDocument found = couchbaseTemplate
    .findById(OrderDocument.class)
    .inScope("commerce")
    .inCollection("orders")
    .one("order::1001");
```

Mỗi phần có vai trò riêng:

1. `findById(OrderDocument.class)` chọn cách truy cập key/value (KV) và kiểu entity để Spring Data chuyển đổi JSON.
2. `inScope("commerce")` chọn scope trong bucket được cấu hình.
3. `inCollection("orders")` chọn collection thuộc scope đó.
4. `one("order::1001")` chạy thao tác cho key được truyền vào.

Trong ví dụ, nếu bucket của Template là `shop`, đường dẫn thực tế là **`shop.commerce.orders`**.

### Phân biệt tên bucket với scope và collection

Các phương thức `inScope()` và `inCollection()` **không chọn bucket**. Bucket được lấy từ cấu hình hay đối tượng Template đang được sử dụng. Nếu cần truy cập một bucket khác, phải sử dụng cấu hình/client factory hoặc Template phù hợp, thay vì truyền tên bucket vào `inScope()`.

Một số cặp scope/collection hợp lệ:

| Scope | Collection | Kết quả |
| --- | --- | --- |
| `_default` | `_default` | Collection mặc định có sẵn trong bucket. |
| `_default` | `audit` | Collection tự tạo trong scope mặc định. |
| `commerce` | `orders` | Collection tự tạo trong scope tự tạo. |
| `commerce` | `_default` | **Không hợp lệ** vì scope tùy chỉnh không có collection `_default`. |

Với scope do ứng dụng tạo, nên chỉ rõ collection được tạo sẵn, tránh kỳ vọng rằng tên `_default` sẽ tự hoạt động.

## 3. Chuẩn bị cấu hình và entity minh họa

Ví dụ ứng dụng Spring Boot có cấu hình cơ bản:

```yaml
spring:
  couchbase:
    connection-string: couchbase://localhost
  data:
    couchbase:
      bucket-name: shop
      scope-name: commerce
```

Tên người dùng và mật khẩu cần được cấu hình an toàn qua môi trường hoặc cơ chế quản lý bí mật của dự án. Các giá trị trong YAML chỉ là minh họa; phải có Couchbase Server đang chạy và tài khoản được cấp quyền.

Giả sử entity đơn hàng có mã định danh, mã khách hàng và trạng thái:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;

@Document
public class OrderDocument {

    @Id
    private String id;

    private String customerId;
    private String status;

    public OrderDocument() {
    }

    public OrderDocument(String id, String customerId, String status) {
        this.id = id;
        this.customerId = customerId;
        this.status = status;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getCustomerId() { return customerId; }
    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
}
```

Entity này không gắn `@Scope` hay `@Collection`; các ví dụ dưới đây sẽ chọn nơi lưu bằng fluent API. Nếu entity có annotation riêng, `inScope()` / `inCollection()` của thao tác Template vẫn có thể ghi đè chúng theo thứ tự ưu tiên của Spring Data.

Inject Template vào service:

```java
import org.springframework.data.couchbase.core.CouchbaseTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStore {

    private final CouchbaseTemplate couchbaseTemplate;

    public OrderStore(CouchbaseTemplate couchbaseTemplate) {
        this.couchbaseTemplate = couchbaseTemplate;
    }

    public OrderDocument loadCurrent(String id) {
        return couchbaseTemplate
            .findById(OrderDocument.class)
            .inScope("commerce")
            .inCollection("orders")
            .one(id);
    }
}
```

Khi sử dụng `findById().one(id)`, cần xử lý trường hợp không tìm thấy document theo hợp đồng API của phiên bản đang sử dụng; không nên mặc định rằng phương thức luôn trả về một entity hợp lệ.

## 4. Thực hiện CRUD trên collection được chỉ định

Nhóm thao tác KV của Template sử dụng document ID nên thường không cần secondary index SQL++. Điểm quan trọng là **tất cả lệnh phải chọn cùng keyspace nếu chúng cùng xử lý một document**.

### 4.1. Insert: chỉ tạo nếu chưa tồn tại

```java
OrderDocument order =
    new OrderDocument("order::1001", "customer::42", "NEW");

couchbaseTemplate
    .insertById(OrderDocument.class)
    .inScope("commerce")
    .inCollection("orders")
    .one(order);
```

`insertById` phù hợp khi ứng dụng muốn tránh vô tình ghi đè document hiện có. Nếu key đã tồn tại **trong collection đó**, thao tác insert sẽ thất bại. Key giống nhau ở collection khác không làm insert này trùng key.

### 4.2. Upsert: tạo mới hoặc cập nhật theo ID

```java
OrderDocument order =
    new OrderDocument("order::1001", "customer::42", "CONFIRMED");

OrderDocument saved = couchbaseTemplate
    .upsertById(OrderDocument.class)
    .inScope("commerce")
    .inCollection("orders")
    .one(order);
```

`upsertById` lưu document theo key được xác định từ `@Id`; nó sẽ tạo mới nếu key chưa tồn tại hoặc cập nhật document tương ứng nếu đã tồn tại. Vì vậy, chỉ dùng upsert khi nghiệp vụ chấp nhận hành vi ghi này; đối với cập nhật có kiểm soát xung đột, cần xem xét replace/CAS và `@Version`.

### 4.3. Find by ID: lấy đúng document

```java
OrderDocument current = couchbaseTemplate
    .findById(OrderDocument.class)
    .inScope("commerce")
    .inCollection("orders")
    .one("order::1001");

OrderDocument archived = couchbaseTemplate
    .findById(OrderDocument.class)
    .inScope("archive")
    .inCollection("orders_history")
    .one("order::1001");
```

Hai biến có thể chứa hai bản dữ liệu khác nhau, hoặc một trong hai không có kết quả. Không nên kết luận “document bị mất” nếu chưa kiểm tra đúng bucket, scope, collection và key.

### 4.4. Exists: kiểm tra sự tồn tại

```java
boolean present = couchbaseTemplate
    .existsById(OrderDocument.class)
    .inScope("commerce")
    .inCollection("orders")
    .one("order::1001");
```

Kết quả chỉ phản ánh sự tồn tại của key trong **collection đã chọn**. Nó không tìm key đó trên tất cả collection trong bucket.

### 4.5. Remove: xóa tại một collection cụ thể

```java
couchbaseTemplate
    .removeById(OrderDocument.class)
    .inScope("archive")
    .inCollection("orders_history")
    .one("order::1001");
```

Lệnh trên xóa ở `archive.orders_history`; document có cùng ID trong `commerce.orders` không bị ảnh hưởng chỉ vì trùng key. Đây là thao tác có tác động thật, nên trong ứng dụng production cần có quy trình kiểm tra quyền, kiểm soát điều kiện xóa và ghi log phù hợp.

### Bảng thao tác nhanh

| Mục đích | Fluent API | Cách kết thúc |
| --- | --- | --- |
| Tạo mới | `insertById(Entity.class)` | `.one(entity)` |
| Upsert | `upsertById(Entity.class)` | `.one(entity)` |
| Tìm theo key | `findById(Entity.class)` | `.one(id)` |
| Kiểm tra key | `existsById(Entity.class)` | `.one(id)` |
| Xóa theo key | `removeById(Entity.class)` | `.one(id)` |
| Truy vấn SQL++ | `findByQuery(Entity.class)` | `.all()`, `.one()` hoặc lựa chọn khác |

Tất cả ví dụ ở bảng đều có thể gắn `inScope(...)` và `inCollection(...)` vào chuỗi API tương ứng khi phiên bản Spring Data hỗ trợ.

## 5. Truy vấn nhiều document bằng findByQuery

KV API phù hợp khi đã có ID; nhưng nếu cần tìm các đơn hàng theo trạng thái hay mã khách hàng, phải dùng truy vấn. Spring Data Couchbase dùng **SQL++** (tên cũ N1QL) cho `findByQuery`.

### 5.1. Chỉ định scope/collection trong truy vấn

```java
import java.util.List;
import org.springframework.data.couchbase.core.query.Query;
import org.springframework.data.couchbase.core.query.QueryCriteria;

Query query = Query.query(
    QueryCriteria.where("status").is("CONFIRMED")
);

List<OrderDocument> confirmed = couchbaseTemplate
    .findByQuery(OrderDocument.class)
    .inScope("commerce")
    .inCollection("orders")
    .matching(query)
    .all();
```

Ý nghĩa:

- `QueryCriteria.where("status").is("CONFIRMED")` xây dựng tiêu chí lọc.
- `findByQuery(OrderDocument.class)` sử dụng SQL++ và ánh xạ kết quả thành entity.
- `inScope(...)` / `inCollection(...)` chọn **keyspace mà câu truy vấn của Template nhắm tới**.
- `matching(query)` áp dụng điều kiện lọc.
- `all()` thực thi và trả danh sách kết quả.

Một truy vấn tương đương về ý tưởng trong Query Workbench:

```sql
SELECT META(o).id AS documentId, o.customerId, o.status
FROM `shop`.`commerce`.`orders` AS o
WHERE o.status = "CONFIRMED";
```

Trong câu SQL++ này, đường dẫn đầy đủ là **`shop.commerce.orders`**. Spring Data có thể thêm các trường/điều kiện mapping cần thiết, chẳng hạn metadata phân biệt kiểu entity, vì vậy không nên giả định SQL++ sinh ra giống hệt ví dụ Workbench.

### 5.2. Truy vấn collection lịch sử mà không đổi entity

```java
Query historyQuery = Query.query(
    QueryCriteria.where("customerId").is("customer::42")
);

List<OrderDocument> history = couchbaseTemplate
    .findByQuery(OrderDocument.class)
    .inScope("archive")
    .inCollection("orders_history")
    .matching(historyQuery)
    .all();
```

Cùng `OrderDocument.class` nhưng truy vấn trên collection khác. Điều này hữu ích cho dữ liệu lưu trữ, tuy nhiên yêu cầu document tại collection đích có cấu trúc tương thích với entity và metadata mà Spring Data mong đợi.

### 5.3. Chuẩn bị chỉ mục ở đúng collection

SQL++ dùng các chỉ mục phù hợp để lập kế hoạch truy vấn. Ví dụ chỉ mục theo `status` trên collection đơn hàng hiện hành:

```sql
CREATE INDEX ix_orders_status
ON `shop`.`commerce`.`orders`(status);
```

Và theo `customerId` trên collection lịch sử:

```sql
CREATE INDEX ix_history_customer
ON `shop`.`archive`.`orders_history`(customerId);
```

Chỉ mục của `commerce.orders` không tự được dùng cho `archive.orders_history`. Nếu thay `inCollection("orders")` thành `inCollection("orders_history")` nhưng chưa xây dựng index trên keyspace mới, query có thể không chạy được hoặc có kế hoạch kém hiệu quả.

**Phân biệt:** `findById`/`upsertById` là thao tác KV theo key và thường không cần secondary index. `findByQuery` là truy vấn SQL++, cần xem xét index, quyền Query và scan consistency.

## 6. Điều chỉnh tính nhất quán khi truy vấn SQL++

Đôi khi ứng dụng vừa ghi một document bằng KV rồi lập tức tìm lại bằng SQL++. Kết quả truy vấn có thể chưa thấy document mới do **độ trễ cập nhật chỉ mục**, dù `findById` đã đọc được.

Tùy yêu cầu, Template cung cấp tùy chọn scan consistency. Ví dụ khi cần chỉ mục bắt kịp trước khi thực thi truy vấn:

```java
import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.data.couchbase.core.query.Query;
import org.springframework.data.couchbase.core.query.QueryCriteria;

Query query = Query.query(
    QueryCriteria.where("status").is("CONFIRMED")
);

List<OrderDocument> found = couchbaseTemplate
    .findByQuery(OrderDocument.class)
    .withConsistency(QueryScanConsistency.REQUEST_PLUS)
    .inScope("commerce")
    .inCollection("orders")
    .matching(query)
    .all();
```

Mức `REQUEST_PLUS` yêu cầu đợi chỉ mục bắt kịp các mutation trước truy vấn, nên có thể tăng độ trễ. Chọn mức consistency dựa trên yêu cầu nghiệp vụ và đo hiệu năng thực tế.

**Thứ tự trong chuỗi API có ý nghĩa về kiểu Java:** một số hàm trả về interface fluent hẹp hơn. Vì thế, nếu một chuỗi có cả `withConsistency(...)` và `inScope(...).inCollection(...)`, hãy đặt tùy chọn consistency **trước** bước chọn collection như ví dụ, thay vì giả định mọi phương thức luôn gọi được ở mọi thứ tự.

## 7. Chọn scope/collection kết hợp TTL và durability

Cơ chế chọn collection vẫn hoạt động với các lựa chọn ghi như expiry (TTL) và durability.

Ví dụ lưu một document thử nghiệm có thời hạn 2 giờ:

```java
import java.time.Duration;

OrderDocument trial =
    new OrderDocument("order::trial-1", "customer::42", "PENDING");

OrderDocument saved = couchbaseTemplate
    .upsertById(OrderDocument.class)
    .withExpiry(Duration.ofHours(2))
    .inScope("commerce")
    .inCollection("orders")
    .one(trial);
```

Với ứng dụng cần cấp độ durability cao hơn cho thao tác ghi, API cũng cho phép chỉ định:

```java
import com.couchbase.client.java.durability.DurabilityLevel;

OrderDocument saved = couchbaseTemplate
    .upsertById(OrderDocument.class)
    .withDurability(DurabilityLevel.MAJORITY)
    .inScope("commerce")
    .inCollection("orders")
    .one(order);
```

Ý nghĩa của từng lựa chọn:

| API | Chọn điều gì? | Không bảo đảm điều gì? |
| --- | --- | --- |
| `inScope()` | Scope đích | Không tạo scope hoặc migrate dữ liệu. |
| `inCollection()` | Collection đích | Không tạo collection hay chỉ mục. |
| `withExpiry()` | Thời hạn document cho thao tác hỗ trợ | Không thiết lập chính sách TTL cho toàn bộ bucket. |
| `withDurability()` | Yêu cầu xác nhận durability cho mutation | Không tự tạo transaction nhiều document. |

Cần hiểu giới hạn expiry do bucket/collection/server thiết lập và các điều kiện hỗ trợ durability của môi trường chạy. Với CAS, dùng mapping `@Version` cùng thao tác cập nhật phù hợp hoặc các API hỗ trợ kiểm tra phiên bản; không coi upsert không kiểm soát phiên bản là cơ chế chống ghi đè cạnh tranh.

## 8. Dùng ReactiveCouchbaseTemplate theo cách tương tự

Spring Data Couchbase có Template reactive cho luồng xử lý không blocking theo Reactor. Cách chọn scope/collection vẫn là `inScope()` và `inCollection()`; khác biệt chính nằm ở kiểu kết quả.

```java
import org.springframework.data.couchbase.core.ReactiveCouchbaseTemplate;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ReactiveOrderStore {

    private final ReactiveCouchbaseTemplate template;

    public ReactiveOrderStore(ReactiveCouchbaseTemplate template) {
        this.template = template;
    }

    public Mono<OrderDocument> find(String id) {
        return template
            .findById(OrderDocument.class)
            .inScope("commerce")
            .inCollection("orders")
            .one(id);
    }

    public Mono<OrderDocument> save(OrderDocument order) {
        return template
            .upsertById(OrderDocument.class)
            .inScope("commerce")
            .inCollection("orders")
            .one(order);
    }

    public Flux<OrderDocument> findAllConfirmed() {
        Query query = Query.query(
            QueryCriteria.where("status").is("CONFIRMED")
        );

        return template
            .findByQuery(OrderDocument.class)
            .inScope("commerce")
            .inCollection("orders")
            .matching(query)
            .all();
    }
}
```

Phần mã trên sử dụng `Query` và `QueryCriteria` đã được import tương tự ví dụ truy vấn trước đó.

- `Mono<OrderDocument>` biểu diễn tối đa một entity.
- `Flux<OrderDocument>` biểu diễn luồng nhiều entity.
- Việc thực thi thao tác reactive gắn với cơ chế subscription của Reactor; chỉ tạo publisher chưa đồng nghĩa đã thực hiện xong một lệnh ghi.
- Không gọi `block()` trong luồng xử lý reactive của ứng dụng chỉ để dùng được kiểu kết quả quen thuộc, trừ khi có ranh giới đồng bộ được thiết kế rõ.

Reactive giúp mô hình hóa xử lý bất đồng bộ, nhưng không tự giảm chi phí query hoặc thay thế việc tạo index. Với cùng `inScope`/`inCollection`, ứng dụng reactive và imperative đều nhắm đến cùng keyspace.

## 9. Ưu tiên của fluent API so với annotation và cấu hình

Ứng dụng có thể khai báo scope/collection ở nhiều nơi cùng lúc. Theo tài liệu Spring Data Couchbase, các cơ chế ưu tiên cao hơn sẽ ghi đè giá trị thấp hơn:

| Ưu tiên | Nơi chọn scope/collection |
| --- | --- |
| 1 – cao nhất | `inScope()` / `inCollection()` của fluent operation trên Template. |
| 2 | `withScope()` / `withCollection()` của Template hoặc repository hỗ trợ. |
| 3 | Annotation trên phương thức repository. |
| 4 | Annotation trên repository interface. |
| 5 | Annotation trên entity. |
| 6 – nền | Cấu hình ứng dụng, chẳng hạn `getScopeName()`. |

Ví dụ entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.repository.Scope;
import org.springframework.data.couchbase.repository.Collection;

@Document
@Scope("commerce")
@Collection("orders")
public class OrderDocument {
    @Id
    private String id;
    // Các trường và getter/setter khác được lược bỏ.
}
```

Mặc dù entity mặc định dùng `commerce.orders`, câu lệnh sau vẫn đọc `archive.orders_history`:

```java
OrderDocument history = couchbaseTemplate
    .findById(OrderDocument.class)
    .inScope("archive")
    .inCollection("orders_history")
    .one("order::1001");
```

Lý do là lựa chọn ở **fluent API của chính thao tác** có ưu tiên cao hơn annotation của entity.

Khi nhiều nguồn khai báo khác nhau, nên xác định keyspace thực tế của **từng thao tác**, tránh chỉ nhìn cấu hình bucket hoặc annotation rồi kết luận mọi lời gọi đều đọc cùng nơi.

### Chọn chỉ scope hoặc chỉ collection có được không?

API cho phép một số thao tác chỉ gọi `inScope(...)` hoặc `inCollection(...)` để ghi đè một phần đích. Nhưng giá trị còn lại sẽ đến từ mapping/cấu hình có hiệu lực, do đó dễ tạo cặp không hợp lệ.

Ví dụ, nếu entity ánh xạ collection `orders`, câu lệnh `inScope("archive")` chỉ hợp lý khi trong scope `archive` thật sự có collection `orders`. Nếu collection lịch sử tên `orders_history`, cách an toàn và rõ ràng hơn là khai báo cả:

```java
.inScope("archive")
.inCollection("orders_history")
```

## 10. Bài toán thực tế: đọc hiện hành và đọc lịch sử

Một service trả về đơn hàng hiện hành theo ID, nhưng cần tìm lại bản lưu trữ khi khách hàng tra cứu đơn hàng cũ. Cả hai collection dùng cùng cấu trúc `OrderDocument`.

```java
public OrderDocument loadCurrent(String id) {
    return couchbaseTemplate
        .findById(OrderDocument.class)
        .inScope("commerce")
        .inCollection("orders")
        .one(id);
}

public OrderDocument loadArchived(String id) {
    return couchbaseTemplate
        .findById(OrderDocument.class)
        .inScope("archive")
        .inCollection("orders_history")
        .one(id);
}
```

Khi hai tập dữ liệu được phân tách rõ như vậy:

- Luồng đọc đơn hàng hiện hành không phải đổi repository hoặc tạo entity mới.
- Luồng lưu trữ có thể dùng collection lịch sử, với chỉ mục và quyền riêng.
- Các document cùng key ở hai nơi được xử lý độc lập.

Tuy nhiên, nếu nghiệp vụ yêu cầu **chuyển** đơn hàng từ current sang archive, chỉ gọi `inScope`/`inCollection` ở thao tác mới là chưa đủ. Cần thực hiện sao chép/migration, kiểm tra dữ liệu và xử lý những cập nhật đồng thời; khi có nhu cầu nguyên tử qua nhiều document, phải xét API transaction và các điều kiện hỗ trợ của Couchbase.

### Tránh truyền thẳng scope/collection từ dữ liệu không tin cậy

Không nên cho client HTTP tự do truyền bất kỳ tên scope và collection nào rồi gọi thẳng `inScope(userInput)`, `inCollection(userInput)`. Nên sử dụng tập giá trị được ứng dụng cho phép, ví dụ `CURRENT` ánh xạ `commerce.orders`, `ARCHIVED` ánh xạ `archive.orders_history`, và cấp quyền tối thiểu cho tài khoản dịch vụ.

Tính linh hoạt của Template phải đi kèm giới hạn quyền truy cập và ghi log phù hợp, nhất là hệ thống đa tenant.

## 11. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `findById` trả không có dữ liệu nhưng Console thấy key. | Chọn sai scope hoặc collection. | So sánh đầy đủ `bucket.scope.collection` của document và code. |
| Có lỗi collection/scope không tồn tại. | Tài nguyên chưa tạo, tên sai hoặc cặp scope/collection không hợp lệ. | Kiểm tra cấu trúc bucket và quyền trên Couchbase Server. |
| `findById` hoạt động, `findByQuery` báo lỗi index. | Chưa có chỉ mục trên collection thực tế được chọn. | Kiểm tra keyspace trong SQL++, tạo index phù hợp. |
| Vừa `upsertById` xong, truy vấn SQL++ chưa thấy ngay document. | Index chưa bắt kịp mutation. | Kiểm tra KV theo ID và scan consistency của query. |
| Ghi vào collection lịch sử không cập nhật collection hiện hành. | Hai collection chứa document độc lập. | Thiết kế đồng bộ/migrate theo yêu cầu nghiệp vụ. |
| Compile không được khi gọi `withExpiry` sau `inCollection`. | Fluent API trả về interface hẹp hơn theo thứ tự gọi. | Đưa tùy chọn `withExpiry` lên trước `inScope`/`inCollection` và đối chiếu Javadoc. |
| Fluent API dùng đúng collection nhưng báo lỗi quyền. | Tài khoản chưa được cấp quyền trên keyspace đó. | Kiểm tra RBAC theo bucket/scope/collection. |
| Reactive method trả `Mono` nhưng không thấy ghi. | Publisher chưa được subscribe trong luồng thực thi. | Kiểm tra chain Reactor và nơi subscriber kích hoạt. |
| Đổi annotation entity mà lệnh Template vẫn truy vấn scope cũ. | Fluent API của thao tác ghi đè annotation. | Xem `inScope`/`inCollection` ngay tại lời gọi. |

Để chẩn đoán có hệ thống, thực hiện các bước:

1. Xác định bucket của `CouchbaseTemplate` được inject.
2. Ghi lại scope và collection được chọn trong fluent chain.
3. Kiểm tra annotation/cấu hình nền nếu một trong hai chưa được chỉ định trực tiếp.
4. Dùng KV theo ID để xác nhận document có tồn tại trong keyspace dự kiến.
5. Kiểm tra Query Service, chỉ mục và quyền nếu lỗi phát sinh từ `findByQuery`.
6. Xác minh TTL, CAS, transaction hoặc consistency nếu lỗi liên quan trạng thái dữ liệu.

## 12. Bài tập thực hành

Cho cấu trúc:

```text
shop
├── commerce
│   ├── orders
│   └── customers
└── archive
    └── orders_history
```

Entity `OrderDocument` có `@Scope("commerce")` và `@Collection("orders")`. Hãy xác định đích của các thao tác:

**Câu 1**

```java
couchbaseTemplate.findById(OrderDocument.class)
    .one("order::1001");
```

**Đáp án:** `shop.commerce.orders`, vì không có override trên Template và entity đã khai báo scope/collection.

**Câu 2**

```java
couchbaseTemplate.findById(OrderDocument.class)
    .inScope("archive")
    .inCollection("orders_history")
    .one("order::1001");
```

**Đáp án:** `shop.archive.orders_history`, vì fluent API của thao tác ưu tiên hơn annotation entity.

**Câu 3**

```java
couchbaseTemplate.upsertById(OrderDocument.class)
    .inScope("archive")
    .inCollection("orders_history")
    .one(order);
```

**Hỏi:** Lệnh trên có tự chuyển document cũ khỏi `commerce.orders` không?

**Đáp án:** Không. Upsert vào collection mới không xóa hoặc đồng bộ document tương ứng ở collection cũ.

**Câu 4**

```java
couchbaseTemplate.findByQuery(OrderDocument.class)
    .inScope("archive")
    .inCollection("orders_history")
    .matching(Query.query(
        QueryCriteria.where("status").is("CONFIRMED")))
    .all();
```

**Hỏi:** Index `ix_orders_status` ở `commerce.orders` đã đủ chưa?

**Đáp án:** Chưa. Query nhắm tới `archive.orders_history`, nên cần chỉ mục thích hợp trên collection lịch sử (hoặc một index khác đủ điều kiện cho truy vấn đó).

**Câu 5**

Ứng dụng cần thực hiện ghi reactive vào `commerce.orders`. Lời gọi sau cần được sử dụng thế nào?

```java
Mono<OrderDocument> result = reactiveCouchbaseTemplate
    .upsertById(OrderDocument.class)
    .inScope("commerce")
    .inCollection("orders")
    .one(order);
```

**Đáp án:** `result` là publisher của Reactor. Nó cần được kết nối vào luồng reactive và subscribe bởi runtime/caller thích hợp; chỉ khởi tạo publisher chưa xác nhận thao tác ghi hoàn tất.

## Ghi nhớ

- **`inScope()` và `inCollection()`** chọn vị trí thực tế cho từng phép thao tác fluent của Template.
- Dùng `findById`/`upsertById` cho KV theo key; dùng `findByQuery` cho lọc dữ liệu qua SQL++, với chỉ mục thích hợp.
- Fluent API của Template có ưu tiên cao hơn annotation trên entity và cấu hình nền. Nếu chuyển scope, nên kiểm tra lại collection tương ứng.
- Kết hợp `withExpiry()`, `withDurability()`, `withConsistency()` theo đúng kiểu trả về và thứ tự method của API.
- Reactive Template sử dụng cách chọn scope/collection tương tự, nhưng trả về `Mono`/`Flux` và tuân theo ngữ nghĩa subscription.
- Chọn collection không tự tạo tài nguyên, không di chuyển document và không thay thế chính sách quyền, consistency, CAS hay transaction.

## Tài liệu tham khảo

- [Spring Data Couchbase — Template & direct operations](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): mô hình fluent API, thao tác KV và truy vấn SQL++.
- [Spring Data Couchbase — Collection Support](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): lựa chọn scope/collection và thứ tự ưu tiên.
- [Spring Data Couchbase — CouchbaseTemplate Javadoc](https://docs.spring.io/spring-data/couchbase/docs/current/api/org/springframework/data/couchbase/core/CouchbaseTemplate.html): các fluent operation của Template.
- [Spring Data Couchbase — Query Javadoc](https://docs.spring.io/spring-data/couchbase/docs/current/api/org/springframework/data/couchbase/core/query/Query.html): cách tạo điều kiện `Query` và scan consistency.
- [Spring Data Couchbase — QueryCriteria Javadoc](https://docs.spring.io/spring-data/couchbase/docs/current/api/org/springframework/data/couchbase/core/query/QueryCriteria.html): API xây dựng tiêu chí truy vấn.

