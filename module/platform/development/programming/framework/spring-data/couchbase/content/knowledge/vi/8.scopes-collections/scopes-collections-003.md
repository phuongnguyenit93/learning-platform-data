# @Scope và @Collection trên entity, repository và phương thức

Trong **Spring Data Couchbase**, mỗi document nằm trong một **bucket, scope và collection** cụ thể. Hai annotation `@Scope` và `@Collection` giúp khai báo đích đọc/ghi ở ba cấp: entity, repository và phương thức repository. Đặt annotation đúng cấp giúp hệ thống dùng cùng một kiểu document cho nhiều tình huống mà vẫn kiểm soát được nơi dữ liệu được lưu, truy vấn và cập nhật.

Bài học thuộc chương **Scope và Collection** của module `SPRING_DATA_COUCHBASE`. Ngoài mapping document và repository, bài minh họa liên hệ với `CouchbaseTemplate`, SQL++, chỉ mục, API reactive và các khía cạnh nhất quán, TTL, CAS và vận hành.

## 1. Hai annotation dùng để làm gì?

Giả sử bucket `shop` được tổ chức như sau:

```text
Bucket: shop
├── Scope: _default
│   ├── Collection: _default
│   └── Collection: audit
├── Scope: commerce
│   ├── Collection: orders
│   └── Collection: customers
└── Scope: archive
    └── Collection: orders_history
```

Khi viết:

```java
@Scope("commerce")
@Collection("orders")
```

Spring Data Couchbase hiểu rằng thao tác tương ứng nhắm tới scope `commerce` và collection `orders` trong bucket đã cấu hình. Với bucket `shop`, keyspace thực tế là **`shop.commerce.orders`**.

| Annotation | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `@Scope("commerce")` | Chọn scope | `commerce` |
| `@Collection("orders")` | Chọn collection nằm trong scope đang được chọn | `orders` |
| `@Document` | Đánh dấu kiểu Java được mapping thành Couchbase document | `OrderDocument` |
| `@Id` | Xác định thuộc tính dùng làm document key | `order::1001` |

**Phân biệt quan trọng:** cùng document key `order::1001` tại `shop.commerce.orders` và `shop.archive.orders_history` biểu diễn **hai document độc lập**. Thay đổi annotation không tự di chuyển dữ liệu từ collection này sang collection khác.

Ba tổ hợp scope–collection hợp lệ theo Couchbase là:

1. Scope `_default` và collection `_default`.
2. Scope `_default` và một collection do ứng dụng tạo, ví dụ `audit`.
3. Scope do ứng dụng tạo và collection do ứng dụng tạo, ví dụ `commerce.orders`.

**Không thể** sử dụng collection `_default` trong một scope tùy chỉnh như `commerce`. Cần khai báo collection nghiệp vụ hợp lệ khi chọn scope riêng.

## 2. Import đúng annotation

Đối với Spring Data Couchbase hiện đại, hai annotation nằm trong package **`org.springframework.data.couchbase.repository`**:

```java
import org.springframework.data.couchbase.repository.Scope;
import org.springframework.data.couchbase.repository.Collection;
```

Các import khác thường cần dùng:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
```

Không nhầm `org.springframework.data.couchbase.repository.Scope` với `org.springframework.context.annotation.Scope`, vì annotation của Spring Framework dùng để cấu hình vòng đời bean, không chọn Couchbase scope.

Tương tự, `org.springframework.data.couchbase.repository.Collection` là annotation, khác với `java.util.Collection` là interface tập hợp trong Java. Các annotation của Couchbase có thể áp dụng ở mức **kiểu** và **phương thức** theo Javadoc của Spring Data Couchbase.

Phần này áp dụng cho Couchbase Server 7.0 trở lên cùng các phiên bản Spring Data Couchbase hỗ trợ scope/collection (từ 4.3.1). Khi làm việc trong dự án cụ thể, nên đối chiếu phiên bản dependency với Javadoc tương ứng.

## 3. Đặt @Scope và @Collection trên entity

Khai báo ở cấp entity phù hợp khi một loại document gần như luôn được lưu vào cùng một collection:

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
    public String getCustomerId() { return customerId; }
    public String getStatus() { return status; }

    public void setId(String id) { this.id = id; }
    public void setCustomerId(String customerId) { this.customerId = customerId; }
    public void setStatus(String status) { this.status = status; }
}
```

Repository tương ứng có thể không cần lặp lại annotation:

```java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
```

Với bucket mặc định `shop` và không có cấu hình override có ưu tiên cao hơn:

```java
OrderDocument order =
    new OrderDocument("order::1001", "customer::42", "NEW");

orderRepository.save(order);

OrderDocument restored = orderRepository
    .findById("order::1001")
    .orElseThrow();
```

Cả `save` và `findById` đều thao tác trên **`shop.commerce.orders`**.

**Ưu điểm:** thông tin vị trí lưu gắn chặt với kiểu document, khiến việc đọc code dễ hiểu.

**Điểm cần cân nhắc:** nếu một entity được tái sử dụng ở nhiều môi trường (dev, staging, production) với tên scope khác nhau, việc hardcode `@Scope("commerce")` trên entity có thể ghi đè scope mặc định được khai báo trong cấu hình ứng dụng.

## 4. Đặt @Scope và @Collection trên repository interface

Nếu cần xác định nơi lưu theo một đường truy cập cụ thể, có thể đặt annotation ở interface repository:

```java
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.Scope;
import org.springframework.data.couchbase.repository.Collection;

@Scope("commerce")
@Collection("orders")
public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
```

Annotation trên repository interface có **ưu tiên cao hơn** annotation tương ứng trên entity. Vì vậy, giả sử entity có `@Scope("commerce")` và `@Collection("orders")`, một repository chuyên truy cập dữ liệu lịch sử có thể viết:

```java
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.Scope;
import org.springframework.data.couchbase.repository.Collection;

@Scope("archive")
@Collection("orders_history")
public interface HistoricalOrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
```

Khi dùng `HistoricalOrderRepository`, các thao tác mặc định trỏ tới **`shop.archive.orders_history`**. Khi dùng `OrderRepository`, thao tác mặc định vẫn trỏ tới **`shop.commerce.orders`**.

Đây là hai nguồn dữ liệu độc lập dù cùng ánh xạ về lớp `OrderDocument`. Việc sử dụng chung entity yêu cầu cấu trúc document ở cả hai collection phù hợp với mapping Java và metadata cần thiết.

**Khi nên chọn cấp repository:**

- Tách đường truy cập đơn hàng hiện hành và đơn hàng lịch sử.
- Cùng một entity cần được dùng ở nhiều collection có cấu trúc tương đồng.
- Muốn entity mô tả dữ liệu, còn repository mô tả nơi lưu.
- Muốn tránh việc mọi thao tác với entity đều cố định vào một scope.

Người bảo trì cần phân biệt rõ repository nào đang được inject vào service, vì cùng tên phương thức `findById` trên hai repository có thể trả về document khác nhau.

## 5. Đặt @Scope và @Collection trên phương thức repository

Hai annotation cũng có thể được áp dụng trực tiếp trên một phương thức repository. Chúng sẽ ghi đè cấu hình ở mức interface và entity **cho phương thức đó**.

Ví dụ phần lớn truy vấn lấy đơn hàng đang hoạt động, riêng một finder lấy dữ liệu lịch sử:

```java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.Scope;
import org.springframework.data.couchbase.repository.Collection;

@Scope("commerce")
@Collection("orders")
public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    // Dùng shop.commerce.orders
    List<OrderDocument> findByStatus(String status);

    // Chỉ phương thức này dùng shop.archive.orders_history
    @Scope("archive")
    @Collection("orders_history")
    List<OrderDocument> findByCustomerId(String customerId);
}
```

Bảng kết quả:

| Lời gọi repository | Scope/collection hiệu lực |
| --- | --- |
| `save(order)` | `shop.commerce.orders` |
| `findById("order::1001")` | `shop.commerce.orders` |
| `findByStatus("NEW")` | `shop.commerce.orders` |
| `findByCustomerId("customer::42")` | `shop.archive.orders_history` |

Annotation trên `findByCustomerId` chỉ áp dụng cho lời gọi này, không đổi đích lưu của `save`, `findById` hay các finder khác.

Ví dụ cố ý làm rõ **độ ưu tiên**. Trong mã thực tế, tên phương thức cần thể hiện rằng nó truy vấn archive để tránh nhầm lẫn, hoặc có thể tách một repository lịch sử riêng. Với query derivation được phiên bản Spring Data hỗ trợ, phần mô tả trước `By` có thể dùng để làm rõ mục đích, ví dụ `findArchivedByCustomerId`.

### Kết hợp @Query ở cấp phương thức

Trường hợp dùng SQL++ tùy chỉnh, Spring Data Couchbase cung cấp các biểu thức SpEL như `#{#n1ql.selectEntity}`, `#{#n1ql.filter}` và tham số vị trí `$1`.

```java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.Query;
import org.springframework.data.couchbase.repository.Scope;
import org.springframework.data.couchbase.repository.Collection;

@Scope("commerce")
@Collection("orders")
public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    @Scope("archive")
    @Collection("orders_history")
    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} " +
           "AND customerId = $1")
    List<OrderDocument> findArchivedByCustomerId(String customerId);
}
```

Ở đây:

- `#{#n1ql.selectEntity}` sinh phần SELECT/FROM thích hợp cho việc ánh xạ entity.
- `#{#n1ql.filter}` thêm điều kiện lọc kiểu document mà Spring Data sử dụng.
- `$1` là tham số thứ nhất của phương thức.
- Annotation phương thức chọn scope `archive` và collection `orders_history` cho truy vấn.

**Cảnh báo:** nếu viết SQL++ tùy chỉnh với mệnh đề `FROM` hardcode tới collection khác, annotation không thể được kỳ vọng tự sửa nội dung SQL++. Nên dùng SpEL do Spring Data hỗ trợ hoặc kiểm tra câu truy vấn cuối cùng.

## 6. Thứ tự ưu tiên khi khai báo trùng nhau

Spring Data Couchbase quy định độ ưu tiên từ **cao xuống thấp** như sau:

| Thứ tự | Cách chọn | Ví dụ |
| --- | --- | --- |
| **1** | Fluent API của thao tác template | `inScope("archive").inCollection("orders_history")` |
| **2** | API đổi phạm vi trên template/repository có hỗ trợ | `withScope("archive").withCollection("orders_history")` |
| **3** | Annotation trên phương thức repository | `@Scope`/`@Collection` trên finder |
| **4** | Annotation trên repository interface | `@Scope`/`@Collection` trên interface |
| **5** | Annotation trên entity | `@Scope`/`@Collection` trên lớp `@Document` |
| **6** | Cấu hình chung của ứng dụng | `getScopeName()`, hoặc thuộc tính Spring Boot tương ứng |

Ví dụ:

```text
Bucket cấu hình                  : shop
Scope cấu hình                   : _default
Entity                           : commerce / orders
Repository                       : commerce / orders
Phương thức findByCustomerId     : archive / orders_history
=> Đích của findByCustomerId      : shop.archive.orders_history
=> Đích của save/findById         : shop.commerce.orders
```

Khi một cấp không chỉ định scope/collection, Spring Data sẽ xét các giá trị hiệu lực ở cấp thấp hơn theo cơ chế mapping của phiên bản đó. Nếu một phương thức đổi scope nhưng không chỉ định collection, cần kiểm tra rằng **collection được chọn cuối cùng tồn tại trong scope mới**.

Ví dụ không nên viết thiếu thông tin khi hai scope có tên collection khác nhau:

```java
@Scope("commerce")
@Collection("orders")
public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    // Mơ hồ nếu archive chỉ có collection orders_history.
    @Scope("archive")
    List<OrderDocument> findByStatus(String status);
}
```

Cách rõ ràng hơn:

```java
@Scope("archive")
@Collection("orders_history")
List<OrderDocument> findByStatus(String status);
```

**Khuyến nghị:** nếu override sang scope khác và tên collection cũng thay đổi, hãy khai báo đủ cả `@Scope` và `@Collection` tại cùng một mức. Điều đó giúp người đọc code nhận ra đường dẫn lưu trữ ngay tại chỗ.

## 7. Ghi đè ở runtime bằng template và DynamicProxyable

### CouchbaseTemplate

Ngoài annotation, Spring Data Couchbase cho phép một thao tác template chọn trực tiếp phạm vi:

```java
List<OrderDocument> archived = couchbaseTemplate
    .findByQuery(OrderDocument.class)
    .inScope("archive")
    .inCollection("orders_history")
    .all();
```

Câu lệnh `inScope(...)` và `inCollection(...)` có ưu tiên cao hơn annotation trên entity cho **lần gọi này**. Các thao tác khác của `CouchbaseTemplate` không bị thay đổi chỉ vì một lần gọi chọn archive.

### DynamicProxyable

Repository hỗ trợ `DynamicProxyable` có thể dùng `withScope(...)` và `withCollection(...)`:

```java
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.DynamicProxyable;
import org.springframework.data.couchbase.repository.Scope;
import org.springframework.data.couchbase.repository.Collection;

@Scope("commerce")
@Collection("orders")
public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String>,
                DynamicProxyable<OrderRepository> {
}
```

Một lời gọi đổi phạm vi:

```java
OrderDocument historical = orderRepository
    .withScope("archive")
    .withCollection("orders_history")
    .findById("order::1001")
    .orElseThrow();
```

Không phải mọi đối tượng repository tự động expose API này: interface phải khai báo hỗ trợ theo hợp đồng và phiên bản Spring Data Couchbase đang dùng. Giá trị scope/collection do caller chọn cần được kiểm soát, đặc biệt khi ứng dụng có nhiều tenant hoặc phạm vi quyền khác nhau.

## 8. Spring Boot profile: khi nào chỉ dùng @Collection?

Giả sử môi trường dev dùng scope `commerce_dev`, production dùng scope `commerce`, nhưng cả hai đều có collection `orders`.

```yaml
# application-dev.yml
spring:
  data:
    couchbase:
      bucket-name: shop
      scope-name: commerce_dev
```

```yaml
# application-prod.yml
spring:
  data:
    couchbase:
      bucket-name: shop
      scope-name: commerce
```

Nếu entity cần dùng scope được cấu hình theo môi trường, có thể chỉ khai báo collection:

```java
@Document
@Collection("orders")
public class OrderDocument {
    @Id
    private String id;
    // Các field và phương thức khác được lược bỏ.
}
```

Với điều kiện không có annotation/override scope ở cấp cao hơn:

- **Dev:** `shop.commerce_dev.orders`.
- **Production:** `shop.commerce.orders`.

Ngược lại, nếu entity có `@Scope("commerce")`, annotation này có thể ghi đè `scope-name: commerce_dev`. Do đó, chọn scope theo profile và hardcode scope trên entity là hai chiến lược cần được phối hợp có chủ đích.

**Quy tắc thiết kế:** với những repository cần đổi scope theo profile, giữ scope ở cấu hình nền và chỉ khai báo `@Collection` khi thích hợp. Nếu luôn trỏ vào một scope nghiệp vụ cụ thể, khai báo đủ hai annotation ở entity hoặc repository có thể dễ đọc hơn.

## 9. Liên hệ với SQL++, chỉ mục và reactive repository

### Truy vấn SQL++ đọc đúng keyspace

Khi kiểm tra kết quả repository, có thể chạy các truy vấn SQL++ tường minh sau trong Couchbase Query Workbench:

```sql
SELECT META(o).id AS documentId, o.customerId, o.status
FROM `shop`.`commerce`.`orders` AS o
WHERE o.customerId = "customer::42";

SELECT META(h).id AS documentId, h.customerId, h.status
FROM `shop`.`archive`.`orders_history` AS h
WHERE h.customerId = "customer::42";
```

Trong SQL++ thực tế, mỗi thành phần tên bucket/scope/collection cần bao bằng backtick khi cần escape, và đoạn minh họa dùng backtick thay cho các dấu bao thông thường.

Chỉ mục là tài nguyên theo collection; ví dụ:

```sql
CREATE INDEX ix_orders_customer
ON `shop`.`commerce`.`orders`(customerId);

CREATE INDEX ix_history_customer
ON `shop`.`archive`.`orders_history`(customerId);
```

Đổi `@Collection` không chuyển chỉ mục từ collection cũ sang mới. Các finder/query dựa trên SQL++ cần chỉ mục phù hợp trên keyspace hiệu lực, trong khi thao tác KV biết trước ID như `findById` thường không cần secondary index.

Lưu ý truy vấn qua index có thể mang tính **eventual consistency** tùy mức scan consistency: vừa `save` xong, query SQL++ có thể chưa thấy ngay document mới. Khi chẩn đoán phải phân biệt tình trạng này với lỗi chọn sai scope/collection.

### ReactiveCouchbaseRepository

Cơ chế scope/collection cũng áp dụng khi xây dựng tầng reactive:

```java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import org.springframework.data.couchbase.repository.Scope;
import org.springframework.data.couchbase.repository.Collection;
import reactor.core.publisher.Flux;

@Scope("commerce")
@Collection("orders")
public interface ReactiveOrderRepository
        extends ReactiveCouchbaseRepository<OrderDocument, String> {

    @Scope("archive")
    @Collection("orders_history")
    Flux<OrderDocument> findByCustomerId(String customerId);
}
```

API reactive thay đổi cách trả và tiêu thụ kết quả, nhưng **không thay đổi nguyên tắc chọn keyspace**. Cần chuẩn bị scope, collection, quyền và chỉ mục cho các thao tác reactive giống như với repository đồng bộ.

## 10. Ảnh hưởng đến TTL, CAS, giao dịch và phân quyền

Hai annotation quyết định **đích thao tác**; chúng không tự áp đặt chính sách expiry, CAS hoặc transaction:

- **TTL/expiry:** document ở hai collection có thể có thời hạn hết hạn khác nhau theo từng lần ghi và chính sách của server. Đổi annotation không tự sao chép document hoặc giữ nguyên expiry cũ.
- **CAS:** cơ chế compare-and-swap bảo vệ cập nhật trên từng document ở collection cụ thể. Hai document cùng key trong hai collection không chia sẻ một CAS chung.
- **Giao dịch:** nếu cần cập nhật nhiều document một cách nguyên tử, phải dùng API transaction thích hợp cùng điều kiện hỗ trợ của Couchbase/Spring Data; annotation không tự tạo giao dịch.
- **Phân quyền:** tài khoản ứng dụng cần được cấp quyền đối với chính collection mà repository/method đang trỏ đến. Ví dụ tài khoản chỉ được đọc `commerce.orders` không mặc nhiên được đọc `archive.orders_history`.
- **Vận hành:** collection mới có chỉ mục, quy tắc truy cập và dữ liệu riêng trong bucket; thay đổi annotation trên code cần được phối hợp với việc tạo tài nguyên và kiểm tra truy vấn thực tế.

Khi chuyển repository từ current sang archive, cần có quy trình migrate/sao chép nếu nghiệp vụ yêu cầu giữ dữ liệu cũ. Chỉ thay đổi annotation không thực hiện bước này.

## 11. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Import `Scope`/`Collection` không đúng kiểu. | Dùng annotation Spring context hoặc import sai package. | Dùng `org.springframework.data.couchbase.repository.Scope` và `Collection`. |
| `findById` không thấy document, nhưng Console có cùng ID. | Repository trỏ vào collection khác. | So sánh đầy đủ `bucket.scope.collection` với vị trí document. |
| Hai finder trên cùng repository trả dữ liệu ở hai scope khác nhau. | Một finder có annotation cấp phương thức. | Đọc annotation trên từng method và bảng ưu tiên. |
| Đổi annotation báo lỗi collection không tồn tại. | Scope/collection chưa được tạo hoặc cặp scope–collection không hợp lệ. | Kiểm tra tài nguyên, tên và quyền trên Couchbase Server. |
| Query finder lỗi nhưng `findById` vẫn hoạt động. | Thiếu SQL++ index hoặc quyền Query ở collection đích. | Kiểm tra query, index và phân quyền. |
| Profile dev đặt scope mới nhưng repository vẫn đọc scope cũ. | Annotation entity/interface/method ghi đè cấu hình. | Dò lại thứ tự ưu tiên và cấu hình runtime. |
| `@Query` đọc collection khác với annotation. | Query tự viết hardcode keyspace. | Dùng SpEL phù hợp hoặc sửa lại phần SQL++ nguồn. |
| `save` vào archive không thấy bản ghi trong current. | Hai collection lưu độc lập. | Thiết kế luồng đồng bộ/di chuyển khi thật sự cần. |

### Checklist trước khi hoàn tất thay đổi

1. Xác định bucket, scope và collection dự kiến cho từng nhóm thao tác.
2. Kiểm tra annotation ở entity, repository interface và từng phương thức.
3. Kiểm tra override thông qua `CouchbaseTemplate` hoặc `DynamicProxyable`.
4. Xác minh scope/collection tồn tại và được cấp đúng quyền.
5. Tạo/kiểm tra chỉ mục SQL++ tại collection hiệu lực cho query finder.
6. Đối chiếu dữ liệu có sẵn; nếu đổi đích lưu, lập kế hoạch migrate/sao chép và xử lý ghi phát sinh trong thời gian chuyển đổi.

## 12. Bài tập đọc code

Giả sử bucket `shop`, scope cấu hình nền `_default` và đoạn mã:

```java
@Document
@Scope("commerce")
@Collection("orders")
public class OrderDocument {
    @Id
    private String id;
}

@Scope("commerce")
@Collection("orders")
public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByStatus(String status);

    @Scope("archive")
    @Collection("orders_history")
    List<OrderDocument> findByIdStartingWith(String prefix);
}
```

Trả lời:

1. `orderRepository.findById("order::1001")` đọc ở đâu?
2. `orderRepository.findByStatus("NEW")` đọc ở đâu?
3. `orderRepository.findByIdStartingWith("order::")` đọc ở đâu?
4. Nếu đổi scope cấu hình nền từ `_default` sang `commerce_dev`, ba lời gọi có tự đổi phạm vi không?
5. Nếu `archive.orders_history` chưa có trên server, annotation có tự tạo nó không?

**Đáp án:**

1. `shop.commerce.orders`: repository khai báo collection hiện hành.
2. `shop.commerce.orders`: phương thức không ghi đè.
3. `shop.archive.orders_history`: annotation phương thức có ưu tiên cao hơn interface.
4. Không. Entity/interface đã chọn `commerce`, phương thức thứ ba chọn `archive`; cả hai cao hơn cấu hình nền.
5. Không. Cần tạo scope/collection và cấp quyền, tạo chỉ mục khi truy vấn cần.

## Ghi nhớ

**Entity** khai báo đích lưu mặc định của kiểu document. **Repository interface** có thể ghi đè entity cho mọi thao tác qua repository. **Phương thức repository** có thể ghi đè interface chỉ cho lần gọi phương thức đó. Khi cần chọn phạm vi động, API của template hoặc repository hỗ trợ `withScope`/`withCollection` có thể có ưu tiên cao hơn. Luôn xác định keyspace hiệu lực trước khi xử lý lỗi dữ liệu, SQL++, chỉ mục hoặc quyền truy cập.

### Tài liệu tham khảo

- [Spring Data Couchbase — Collection Support](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): vị trí annotation, tổ hợp hợp lệ và thứ tự ưu tiên.
- [Spring Data Couchbase — Scope Javadoc](https://docs.spring.io/spring-data/couchbase/docs/current/api/org/springframework/data/couchbase/repository/Scope.html): package và nơi có thể đặt annotation.
- [Spring Data Couchbase — Collection Javadoc](https://docs.spring.io/spring-data/couchbase/docs/current/api/org/springframework/data/couchbase/repository/Collection.html): package và nơi có thể đặt annotation.
- [Spring Data Couchbase — Repository Queries](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): query derivation, `@Query`, SQL++ và chỉ mục.

