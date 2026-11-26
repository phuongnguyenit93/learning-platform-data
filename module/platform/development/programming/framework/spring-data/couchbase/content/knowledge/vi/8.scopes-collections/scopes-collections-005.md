# DynamicProxyable và đổi đích truy cập của repository trong Spring Data Couchbase

Trong một ứng dụng **Spring Data Couchbase**, repository thường được ánh xạ tới một scope và collection cố định qua cấu hình hoặc annotation. Tuy nhiên, có những trường hợp cùng một kiểu document và cùng bộ phương thức repository phải làm việc với nhiều tập dữ liệu: đơn hàng hiện hành và đơn hàng lưu trữ, dữ liệu ở các môi trường khác nhau, hay những vùng dữ liệu đã được phân quyền theo khách hàng.

Interface **`DynamicProxyable<REPO>`** của Spring Data Couchbase giải quyết tình huống này bằng cách cho repository tạo ra một **proxy truy cập với scope/collection được lựa chọn tại thời điểm gọi**. Hai phương thức quan trọng nhất là `withScope(String)` và `withCollection(String)`.

Bài thuộc chương **Scope và Collection** của module `SPRING_DATA_COUCHBASE`. Bạn sẽ học cách khai báo repository hỗ trợ lựa chọn động, hiểu thứ tự ưu tiên của cơ chế định tuyến, thực hiện CRUD và query đúng keyspace, áp dụng với reactive repository và nhận diện rủi ro về chỉ mục, quyền, TTL, CAS và tính nhất quán.

## 1. Bài toán: một repository, nhiều nơi lưu document

Giả sử bucket `shop` chứa các scope và collection sau:

```text
Bucket: shop
├── Scope: _default
│   └── Collection: _default
├── Scope: commerce
│   ├── Collection: orders
│   └── Collection: customers
└── Scope: archive
    └── Collection: orders_history
```

Repository đơn hàng bình thường dùng `shop.commerce.orders`. Khi chức năng tra cứu lịch sử chạy, ta muốn sử dụng **cùng các phương thức repository** để đọc `shop.archive.orders_history`.

Ví dụ hai vị trí có cùng document key `order::1001`:

| Keyspace | Document key | Giá trị `status` minh họa |
| --- | --- | --- |
| `shop.commerce.orders` | `order::1001` | `CONFIRMED` |
| `shop.archive.orders_history` | `order::1001` | `ARCHIVED` |

Đây là **hai document độc lập**. Key của Couchbase chỉ định danh duy nhất trong một collection; thay đổi scope hoặc collection làm thay đổi không gian khóa được truy cập.

Có thể tạo hai repository riêng với `@Scope` và `@Collection`, nhưng khi các collection có cùng model và cùng thao tác, việc lặp lại nhiều interface làm mã kém gọn. `DynamicProxyable` là một lựa chọn cho những trường hợp cần **định tuyến repository theo ngữ cảnh của lời gọi**.

## 2. DynamicProxyable là gì?

`DynamicProxyable<REPO>` là một interface trong package:

```java
import org.springframework.data.couchbase.repository.DynamicProxyable;
```

Các phương thức chính theo Javadoc Spring Data Couchbase:

| Phương thức | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `withScope(String scope)` | `REPO` | Trả về một đối tượng repository có scope được chỉ định. |
| `withCollection(String collection)` | `REPO` | Trả về một đối tượng repository có collection được chỉ định. |
| `withOptions(CommonOptions<?> options)` | `REPO` | Trả về repository với tùy chọn SDK chung, dành cho các nhu cầu nâng cao. |

Ký hiệu generic **`REPO` phải là kiểu interface repository cụ thể** mà bạn đang định nghĩa. Ví dụ:

```java
public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String>,
                DynamicProxyable<OrderRepository> {
}
```

Ở đây, `DynamicProxyable<OrderRepository>` cho phép kết quả của `withScope()` và `withCollection()` vẫn có kiểu **`OrderRepository`**, nên vẫn gọi được `findById()`, `save()` và các finder tùy chỉnh.

Cách này được tài liệu Spring Data Couchbase hỗ trợ cho cả repository **imperative** (`CouchbaseRepository`) và **reactive** (`ReactiveCouchbaseRepository`). Yêu cầu nền cho Scope/Collection là Couchbase Server **7.0 trở lên** và Spring Data Couchbase **4.3.1 trở lên**; kiểm tra phiên bản cụ thể của dự án khi áp dụng.

**Phân biệt:** `DynamicProxyable` là cơ chế của **repository Spring Data**, không phải class tạo Couchbase scope/collection mới và không phải Java SDK `Collection`.

## 3. Ví dụ đầy đủ: khai báo entity và repository

### 3.1. Entity đơn hàng

Một document dùng chung cho đơn hàng hiện hành và bản lưu trữ:

```java
package example.shop;

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

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
```

Entity không cố định `@Scope` hay `@Collection`. Phạm vi mặc định sẽ đến từ cấu hình và annotation ở các cấp khác; khi cần, lời gọi `withScope()`/`withCollection()` sẽ chọn nơi khác.

### 3.2. Repository vừa có CRUD vừa có khả năng định tuyến động

```java
package example.shop;

import java.util.List;

import org.springframework.data.couchbase.repository.Collection;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.DynamicProxyable;
import org.springframework.data.couchbase.repository.Scope;

@Scope("commerce")
@Collection("orders")
public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String>,
                DynamicProxyable<OrderRepository> {

    List<OrderDocument> findByStatus(String status);

    List<OrderDocument> findByCustomerId(String customerId);
}
```

Có ba điểm cần chú ý:

1. `CouchbaseRepository<OrderDocument, String>` mang lại các thao tác chuẩn như `save`, `findById`, `existsById`, `deleteById`.
2. `DynamicProxyable<OrderRepository>` bổ sung `withScope` và `withCollection` với kiểu trả về đúng interface.
3. `@Scope("commerce")` và `@Collection("orders")` khai báo **đích mặc định** của repository. Hai annotation này thuộc package `org.springframework.data.couchbase.repository`, khác với `org.springframework.context.annotation.Scope` dùng cho Spring bean.

Với bucket ứng dụng được cấu hình là `shop`, lời gọi `orderRepository.findById(id)` thông thường sẽ đọc từ `shop.commerce.orders`.

## 4. Dùng withScope() và withCollection() để đổi đích

Ví dụ một service cần đọc đơn hàng hiện hành và đơn hàng lịch sử:

```java
package example.shop;

import java.util.Optional;

import org.springframework.stereotype.Service;

@Service
public class OrderLookupService {

    private final OrderRepository orderRepository;

    public OrderLookupService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public Optional<OrderDocument> findCurrent(String id) {
        return orderRepository.findById(id);
    }

    public Optional<OrderDocument> findArchived(String id) {
        return orderRepository
                .withScope("archive")
                .withCollection("orders_history")
                .findById(id);
    }
}
```

Giả sử bucket là `shop`, kết quả định tuyến:

| Lệnh gọi | Scope | Collection |
| --- | --- | --- |
| `orderRepository.findById(id)` | `commerce` | `orders` |
| `orderRepository.withScope("archive").withCollection("orders_history").findById(id)` | `archive` | `orders_history` |

Lệnh `withScope(...)` và `withCollection(...)` trả về **một repository proxy đã được cấu hình lựa chọn phạm vi**. Hãy sử dụng đối tượng trả về cho thao tác cần đổi đích. Không cần thay annotation trên interface và không nên coi đây là lệnh thay cấu hình chung của ứng dụng.

Có thể tách proxy thành biến để mã dễ đọc:

```java
OrderRepository historicalOrders = orderRepository
        .withScope("archive")
        .withCollection("orders_history");

Optional<OrderDocument> oldOrder =
        historicalOrders.findById("order::1001");
```

Biến `historicalOrders` tiếp tục dùng được các phương thức của `OrderRepository`, bao gồm các finder được khai báo trên interface.

**Thói quen tốt:** tạo proxy có đích rõ ràng trong phạm vi xử lý cần dùng, hoặc truyền proxy đã cấu hình tới lớp chịu trách nhiệm tương ứng. Tránh dùng chung một tham chiếu proxy định tuyến động cho nhiều luồng có yêu cầu truy cập khác nhau nếu luồng sử dụng chưa được thiết kế, kiểm thử và quản lý rõ.

## 5. Chọn cả scope lẫn collection: không tách rời keyspace

Spring Data có thể kế thừa tên collection từ annotation hoặc cấu hình nếu bạn chỉ gọi `withScope(...)`. Điều này chỉ phù hợp khi **collection còn hiệu lực thực sự tồn tại trong scope mới**.

Ví dụ repository mặc định dùng `commerce.orders`:

```java
OrderRepository archive = orderRepository.withScope("archive");
```

Nếu không có override collection nào khác, `archive` có thể tiếp tục sử dụng tên collection `orders`. Nhưng cấu trúc ví dụ của chúng ta chỉ có `archive.orders_history`. Vì vậy, cách rõ ràng là:

```java
OrderRepository archive = orderRepository
        .withScope("archive")
        .withCollection("orders_history");
```

Cũng tương tự, nếu chỉ đổi collection trong scope hiện hành:

```java
OrderRepository anotherCollection =
        orderRepository.withCollection("orders_backup");
```

Lệnh này chỉ có ý nghĩa khi `commerce.orders_backup` **đã tồn tại** và đúng với nghiệp vụ. Đừng giả định rằng `withCollection` tự tạo collection hoặc sao chép dữ liệu.

### Cặp scope và collection hợp lệ

| Scope | Collection | Hợp lệ? |
| --- | --- | --- |
| `_default` | `_default` | Có, collection mặc định của bucket. |
| `_default` | `audit` | Có, nếu `audit` đã được tạo. |
| `commerce` | `orders` | Có, nếu cả hai tài nguyên đã được tạo. |
| `archive` | `orders_history` | Có, nếu cả hai tài nguyên đã được tạo. |
| `archive` | `_default` | **Không**: scope tùy chỉnh không có collection `_default`. |

Việc chọn scope tùy chỉnh đòi hỏi collection tùy chỉnh phù hợp. Tên đầy đủ của nơi lưu là `bucket.scope.collection`; chọn sai bất kỳ thành phần nào cũng có thể khiến thao tác đọc/ghi không tìm thấy dữ liệu như mong đợi.

## 6. Không chỉ đọc: save, delete và các finder cũng đổi đích

Vì proxy có kiểu `OrderRepository`, nó cung cấp cả những lệnh repository gốc.

### Lưu document vào collection lịch sử

```java
OrderDocument snapshot = new OrderDocument(
        "order::1001",
        "customer::42",
        "ARCHIVED"
);

OrderRepository archiveRepo = orderRepository
        .withScope("archive")
        .withCollection("orders_history");

archiveRepo.save(snapshot);
```

Lệnh `save(snapshot)` ghi vào `shop.archive.orders_history`, theo mapping của repository và proxy đang dùng. **Nó không tự xóa bản ghi ở `shop.commerce.orders`**.

Nếu cần một quy trình lưu trữ thật, có thể phải đọc bản hiện hành, tạo bản lưu, kiểm tra kết quả và xử lý bản hiện hành theo chính sách. Khi có thao tác nhiều document và yêu cầu nguyên tử, cần nghiên cứu cơ chế transaction tương ứng của Couchbase.

### Truy vấn theo thuộc tính

```java
List<OrderDocument> current = orderRepository
        .findByStatus("CONFIRMED");

List<OrderDocument> archived = orderRepository
        .withScope("archive")
        .withCollection("orders_history")
        .findByStatus("ARCHIVED");
```

Finder `findByStatus` được Spring Data suy ra từ tên phương thức, thường dùng SQL++ và cần **chỉ mục phù hợp trên đúng collection được chọn**. Một repository động không làm chỉ mục của collection hiện hành có hiệu lực trên collection lưu trữ.

### Xóa theo ID tại đúng nơi

```java
orderRepository
        .withScope("archive")
        .withCollection("orders_history")
        .deleteById("order::1001");
```

Thao tác trên không đụng đến document cùng key tại `commerce.orders`. Trong hệ thống thực, cần kiểm tra quyền và điều kiện nghiệp vụ trước khi xóa.

**Kết luận kỹ thuật:** việc chọn phạm vi động tác động tới các thao tác truy cập repository dùng proxy tương ứng. Nó không phải một thao tác đọc đặc biệt; các lệnh ghi cũng có thể hướng tới đích mới.

## 7. Thứ tự ưu tiên so với annotation và cấu hình

Spring Data Couchbase cung cấp nhiều cách chọn scope/collection, và chúng có thứ tự ưu tiên. Theo tài liệu chính thức, từ cao xuống thấp:

| Thứ tự | Cơ chế | Ví dụ |
| --- | --- | --- |
| **1** | Fluent API của thao tác Template | `inScope(...).inCollection(...)` |
| **2** | Repository/Template proxy với phạm vi được chọn | `withScope(...).withCollection(...)` |
| **3** | Annotation trên phương thức repository | `@Scope` / `@Collection` tại finder |
| **4** | Annotation trên repository interface | `@Scope` / `@Collection` trên interface |
| **5** | Annotation trên entity | `@Scope` / `@Collection` trên class `@Document` |
| **6** | Cấu hình ứng dụng | `getScopeName()` hoặc thuộc tính scope tương ứng |

Ví dụ repository có annotation:

```java
@Scope("commerce")
@Collection("orders")
public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String>,
                DynamicProxyable<OrderRepository> {

    @Scope("archive")
    @Collection("orders_history")
    List<OrderDocument> findByStatus(String status);
}
```

Khi gọi trực tiếp `orderRepository.findByStatus("ARCHIVED")`, annotation cấp **phương thức** có ưu tiên hơn annotation cấp interface, nên phương thức chọn `archive.orders_history`.

Nhưng với:

```java
List<OrderDocument> result = orderRepository
        .withScope("commerce")
        .withCollection("orders")
        .findByStatus("CONFIRMED");
```

Giá trị từ `withScope/withCollection` có ưu tiên **cao hơn annotation cấp phương thức**, do đó lời gọi qua proxy đã chọn `commerce.orders`.

**Đọc code theo thứ tự:** xác định repository được gọi có phải proxy tạo qua `withScope/withCollection` không, sau đó mới xét annotation trên method, interface, entity và cấu hình nền. Tránh nhìn riêng `@Scope` trên một lớp rồi kết luận toàn bộ thao tác chắc chắn truy cập scope đó.

## 8. DynamicProxyable so với repository cố định và CouchbaseTemplate

| Cách tiếp cận | Điểm mạnh | Trường hợp dùng |
| --- | --- | --- |
| Repository có `@Scope/@Collection` cố định | Mã dễ lần theo, ranh giới dữ liệu rõ ràng | Một nghiệp vụ luôn dùng cùng collection. |
| Repository mở rộng `DynamicProxyable` | Tái sử dụng cùng API repository, chọn đích khi gọi | Cùng entity/finder dùng cho current và archive. |
| `CouchbaseTemplate` với `inScope/inCollection` | Điều khiển từng thao tác, dựng query hoặc KV linh hoạt | Các thao tác đặc thù không biểu diễn thuận tiện qua repository. |
| `ReactiveCouchbaseRepository` + `DynamicProxyable` | Cơ chế chọn đích tương tự, trả về publisher | Luồng dữ liệu reactive cần chọn scope/collection. |

Ví dụ lựa chọn qua Template:

```java
OrderDocument current = couchbaseTemplate
        .findById(OrderDocument.class)
        .inScope("commerce")
        .inCollection("orders")
        .one("order::1001");
```

Ví dụ tương đương về ý định qua repository động:

```java
Optional<OrderDocument> current = orderRepository
        .withScope("commerce")
        .withCollection("orders")
        .findById("order::1001");
```

Cách trả kết quả khác nhau theo API; mục đích chọn keyspace giống nhau. Khi cần query nhiều điều kiện, các API `CouchbaseTemplate` có thể kiểm soát tiêu chí truy vấn chi tiết hơn.

**Không nên chuyển toàn bộ repository sang định tuyến động chỉ vì tính năng này tồn tại.** Nếu toàn hệ thống luôn dùng `commerce.orders`, annotation tĩnh đơn giản và dễ bảo trì hơn. Chỉ dùng lựa chọn động khi thực sự có nhiều đích và có quy tắc chọn rõ ràng.

## 9. Sử dụng với ReactiveCouchbaseRepository

`DynamicProxyable` cũng có thể được gắn vào interface `ReactiveCouchbaseRepository`. Mẫu ví dụ:

```java
package example.shop;

import org.springframework.data.couchbase.repository.Collection;
import org.springframework.data.couchbase.repository.DynamicProxyable;
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import org.springframework.data.couchbase.repository.Scope;

import reactor.core.publisher.Flux;

@Scope("commerce")
@Collection("orders")
public interface ReactiveOrderRepository
        extends ReactiveCouchbaseRepository<OrderDocument, String>,
                DynamicProxyable<ReactiveOrderRepository> {

    Flux<OrderDocument> findByStatus(String status);
}
```

Lời gọi:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<OrderDocument> one = reactiveOrderRepository
        .withScope("archive")
        .withCollection("orders_history")
        .findById("order::1001");

Flux<OrderDocument> many = reactiveOrderRepository
        .withScope("archive")
        .withCollection("orders_history")
        .findByStatus("ARCHIVED");
```

- `Mono<OrderDocument>` biểu diễn luồng tối đa một document.
- `Flux<OrderDocument>` biểu diễn luồng nhiều document.
- Lựa chọn scope/collection vẫn phải phù hợp với nơi dữ liệu thực sự tồn tại và quyền được cấp.
- Việc tạo `Mono` hoặc `Flux` không xác nhận một thao tác đã hoàn thành; luồng reactive cần được subscribe/tiêu thụ bởi tầng gọi thích hợp.
- Không nên gọi `block()` trên event loop của một ứng dụng reactive chỉ để lấy kết quả đồng bộ.

Có thể kết hợp repository dynamic với Reactor trong service:

```java
public Mono<OrderDocument> loadArchived(
        ReactiveOrderRepository repository, String id) {

    return repository
            .withScope("archive")
            .withCollection("orders_history")
            .findById(id);
}
```

Không cần tạo một entity riêng chỉ vì dùng reactive. Reactive ảnh hưởng mô hình xử lý bất đồng bộ; quy tắc bucket/scope/collection của document không thay đổi.

## 10. Chỉ mục và SQL++ khi repository đổi collection

Couchbase thường truy cập theo **KV** khi thao tác trên một document đã biết ID, ví dụ `findById`. Những finder theo thuộc tính như `findByCustomerId` hoặc `findByStatus` thường được Spring Data chuyển thành truy vấn **SQL++** (tên cũ N1QL).

Ví dụ cùng một điều kiện lọc trên hai keyspace:

```sql
SELECT META(o).id AS documentId, o.status
FROM `shop`.`commerce`.`orders` AS o
WHERE o.customerId = "customer::42";
```

```sql
SELECT META(h).id AS documentId, h.status
FROM `shop`.`archive`.`orders_history` AS h
WHERE h.customerId = "customer::42";
```

Câu SQL++ nên chỉ rõ bucket, scope và collection nếu thực thi bên ngoài ngữ cảnh query được cấu hình sẵn. Chỉ mục cũng phải tạo **trên collection tương ứng**:

```sql
CREATE INDEX ix_orders_customer
ON `shop`.`commerce`.`orders`(customerId);

CREATE INDEX ix_history_customer
ON `shop`.`archive`.`orders_history`(customerId);
```

Nếu repository dùng một finder trên `orders_history` mà index chỉ tồn tại tại `commerce.orders`, truy vấn có thể không có chỉ mục thích hợp để thực thi hoặc gặp vấn đề hiệu năng.

**Lưu ý mapping:** Spring Data có thể lưu metadata phân biệt kiểu entity. Nếu dữ liệu lịch sử được chép bằng SDK trực tiếp mà làm mất metadata cần thiết, một query repository có thể trả kết quả khác so với câu SQL++ tự viết. Khi di chuyển document giữa các collection, cần xác minh cấu trúc và metadata thực tế.

### Consistency khi tìm ngay sau ghi

Sau khi `save` một document mới bằng KV, một truy vấn SQL++ có thể tạm thời chưa thấy document nếu index chưa bắt kịp mutation. Vì vậy, khi truy vấn sau ghi, cần kiểm tra cả **đường dẫn keyspace** lẫn mức scan consistency; không mặc định mọi hiện tượng “chưa thấy dữ liệu” đều do `DynamicProxyable` chọn sai nơi.

## 11. Thiết kế chọn đích an toàn trong ứng dụng nhiều tenant

Giả sử ứng dụng hỗ trợ hai tập đơn hàng: current và archive. Thay vì nhận tên scope và collection tùy ý từ HTTP request, service nên ánh xạ từ một tập lựa chọn được phép:

```java
public enum OrderDataSet {
    CURRENT,
    ARCHIVED
}
```

```java
public OrderRepository selectRepository(
        OrderRepository base, OrderDataSet dataSet) {

    return switch (dataSet) {
        case CURRENT -> base
                .withScope("commerce")
                .withCollection("orders");

        case ARCHIVED -> base
                .withScope("archive")
                .withCollection("orders_history");
    };
}
```

Ví dụ trên dùng cú pháp `switch` expression của Java hiện đại. Nếu ứng dụng dùng Java cũ hơn, có thể thay bằng `switch` thông thường.

Việc chọn dataset vẫn phải đi kèm **kiểm tra quyền của người dùng** ở service: không phải ai cũng được phép xem đơn hàng lưu trữ. Quyền Couchbase của tài khoản dịch vụ cũng cần giới hạn phù hợp ở cấp bucket/scope/collection.

Với nhiều tenant, không nên chỉ lấy `tenantId` từ request rồi ghép thẳng thành tên scope:

```java
// Không nên dùng trực tiếp dữ liệu không đáng tin cậy:
OrderRepository selected = orderRepository
        .withScope(requestedScope)
        .withCollection(requestedCollection);
```

Cần kiểm tra người dùng có quyền truy cập tenant được yêu cầu, sử dụng ánh xạ tenant → keyspace do hệ thống kiểm soát, và chỉ cho phép các tên đã được provision. **DynamicProxyable chỉ chọn vị trí dữ liệu, không tự thực hiện tenant isolation hay authorization.**

## 12. TTL, CAS, transaction và chuyển dữ liệu

Một số tính chất dữ liệu **không tự thay đổi** chỉ vì repository đã đổi keyspace:

| Khía cạnh | Ý nghĩa khi đổi scope/collection |
| --- | --- |
| **TTL/expiry** | Mỗi document có thể có expiry riêng. Chọn collection khác không tự bảo toàn expiry của bản dữ liệu cũ. |
| **CAS** | Mỗi document có phiên bản/CAS riêng trong collection của nó. Hai document cùng ID ở hai collection không chia sẻ CAS. |
| **Transaction** | Ghi nhiều document/collection có yêu cầu nguyên tử phải dùng cơ chế transaction phù hợp với phiên bản Couchbase và API của ứng dụng. |
| **Index** | Index được xây dựng theo collection; cần tạo index riêng cho keyspace mới. |
| **RBAC** | Service account phải có quyền thao tác trên keyspace được chọn. |
| **Migration** | `withScope()`/`withCollection()` không tạo scope, không tạo collection và không chuyển tài liệu cũ. |

Ví dụ, nếu hệ thống muốn chuyển một đơn hàng từ current sang archive, chỉ gọi:

```java
orderRepository
        .withScope("archive")
        .withCollection("orders_history")
        .save(order);
```

là **chưa đủ để “di chuyển”**: document ở `commerce.orders` vẫn tồn tại trừ khi có bước xử lý khác. Quy trình chuyển dữ liệu cần xác định cách xử lý việc ghi đồng thời, điều kiện thành công, chính sách TTL, cấu trúc document và khả năng quay lại.

Khi cần tránh ghi đè cạnh tranh, cân nhắc phiên bản entity với `@Version` hoặc API CAS phù hợp. Ghi bằng repository proxy ở một collection không cho phép dùng CAS của document khác trong collection kia để tạo một quy trình cập nhật nguyên tử.

## 13. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không gọi được `withScope()` hoặc `withCollection()` trên repository. | Interface chưa mở rộng `DynamicProxyable<ChínhRepository>` hoặc phiên bản dependency chưa hỗ trợ. | Xem định nghĩa interface, import và phiên bản Spring Data Couchbase. |
| Có `DynamicProxyable` nhưng lỗi kiểu trả về. | Tham số generic không phải kiểu repository hiện tại. | Dùng `DynamicProxyable<OrderRepository>` khi interface là `OrderRepository`. |
| `findById` không thấy document dù Console có cùng key. | Proxy chọn scope/collection khác nơi dữ liệu tồn tại. | So sánh đầy đủ `bucket.scope.collection` và ID. |
| Chỉ gọi `withScope("archive")` rồi gặp lỗi collection. | Tên collection kế thừa là `orders` nhưng archive chỉ có `orders_history`. | Gọi đủ cả `withScope` và `withCollection`. |
| `findById` hoạt động, `findByStatus` lỗi. | Query SQL++ thiếu index hoặc quyền Query ở collection mới. | Kiểm tra index, keyspace và quyền. |
| Vừa lưu xong chưa thấy document khi tìm theo thuộc tính. | Độ trễ cập nhật secondary index. | Kiểm tra bằng KV theo ID, sau đó xem scan consistency. |
| Repository không sử dụng annotation trên method như dự kiến. | Proxy động với `withScope/withCollection` có ưu tiên cao hơn annotation. | Kiểm tra thứ tự ưu tiên và nơi tạo proxy. |
| Một tenant thấy dữ liệu tenant khác. | Ánh xạ tenant → keyspace hoặc phân quyền ứng dụng sai. | Rà soát authorization, allowlist, cấu hình RBAC. |
| Dữ liệu đã `save` sang archive nhưng current vẫn còn. | `save` không phải thao tác move. | Thiết kế migration/sao chép và bước xóa riêng nếu nghiệp vụ yêu cầu. |
| Dữ liệu tạo bằng SDK thô không hiện qua finder repository. | Mapping metadata hoặc cấu trúc document không phù hợp. | Kiểm tra các field thực tế và SQL++ mà Spring Data tạo ra. |

### Checklist kiểm tra khi phát triển

1. Xác định đúng bucket và tên scope/collection của từng trường hợp sử dụng.
2. Xác nhận repository mở rộng `CouchbaseRepository` hoặc `ReactiveCouchbaseRepository` **cùng** `DynamicProxyable<RepositoryCụThể>`.
3. Kiểm tra annotation trên entity, repository và method; đối chiếu ưu tiên với `withScope/withCollection`.
4. Tạo đầy đủ scope/collection và cấp quyền phù hợp trước khi chạy ứng dụng.
5. Tạo index phù hợp cho từng query finder trên collection được định tuyến tới.
6. Kiểm tra cả luồng đọc và ghi, nhất là khi cùng ID tồn tại ở nhiều nơi.
7. Nếu dùng tenant/dataset động, giới hạn lựa chọn theo quyền và ánh xạ được quản lý.
8. Nếu chuyển dữ liệu, có quy trình migrate và xác minh độc lập; không coi việc đổi đích proxy là di chuyển document.

## 14. Bài tập thực hành

Cho bucket `shop` và repository:

```java
@Scope("commerce")
@Collection("orders")
public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String>,
                DynamicProxyable<OrderRepository> {

    List<OrderDocument> findByCustomerId(String customerId);

    @Scope("archive")
    @Collection("orders_history")
    List<OrderDocument> findByStatus(String status);
}
```

Hãy xác định đích của các thao tác sau.

**Câu 1:**

```java
orderRepository.findById("order::1001");
```

**Đáp án:** `shop.commerce.orders`. Không có override tại lời gọi; repository khai báo scope và collection hiện hành.

**Câu 2:**

```java
orderRepository.withScope("archive")
        .withCollection("orders_history")
        .findById("order::1001");
```

**Đáp án:** `shop.archive.orders_history` vì proxy đã chọn phạm vi tại runtime.

**Câu 3:**

```java
orderRepository.findByStatus("ARCHIVED");
```

**Đáp án:** `shop.archive.orders_history`, do `@Scope` và `@Collection` trên phương thức `findByStatus` có ưu tiên hơn annotation interface.

**Câu 4:**

```java
orderRepository.withScope("commerce")
        .withCollection("orders")
        .findByStatus("CONFIRMED");
```

**Đáp án:** `shop.commerce.orders`. `withScope/withCollection` trên proxy có ưu tiên cao hơn annotation trên phương thức.

**Câu 5:** Sau khi `save(order)` qua proxy `archive.orders_history`, cùng key ở `commerce.orders` có tự mất đi không?

**Đáp án:** Không. Hai collection độc lập; cần có quy trình di chuyển hoặc xóa rõ ràng nếu nghiệp vụ yêu cầu.

**Câu 6:** Một finder chạy được trên `commerce.orders` nhưng lỗi Query Service khi chuyển qua `archive.orders_history`. Nên kiểm tra gì trước?

**Đáp án:** Xác minh keyspace mới, quyền Query và index ở `archive.orders_history`; index của collection hiện hành không áp dụng thay cho collection lịch sử.

## Ghi nhớ

- **`DynamicProxyable<REPO>`** cho repository khả năng trả về một repository proxy với scope/collection được chọn qua `withScope()` và `withCollection()`.
- Generic `REPO` là **kiểu interface repository cụ thể**, ví dụ `DynamicProxyable<OrderRepository>`.
- Lựa chọn động ở cấp repository có ưu tiên cao hơn annotation trên method, interface, entity và cấu hình nền.
- Dùng cả `withScope()` lẫn `withCollection()` khi đổi giữa những keyspace có tên collection khác nhau.
- Repository động giữ nguyên các phương thức CRUD và finder; KV theo ID và SQL++ theo thuộc tính có yêu cầu vận hành khác nhau.
- DynamicProxyable **không tự tạo collection, không migrate document và không tự cấp quyền truy cập**. Cần kiểm tra RBAC, chỉ mục, TTL, CAS và transaction theo yêu cầu nghiệp vụ.

## Tài liệu tham khảo

1. [Spring Data Couchbase — Collection Support](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): cách dùng `DynamicProxyable` và thứ tự ưu tiên các cơ chế chọn scope/collection.
2. [Spring Data Couchbase — DynamicProxyable Javadoc](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/repository/DynamicProxyable.html): kiểu generic và chữ ký của `withScope`, `withCollection`, `withOptions`.
3. [Spring Data Couchbase — Couchbase repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): đặc điểm KV theo ID, SQL++ của các repository query và yêu cầu chỉ mục.
4. [Couchbase — Scopes and Collections](https://docs.couchbase.com/server/current/learn/data/scopes-and-collections.html): cấu trúc tổ chức dữ liệu và phạm vi collection.

