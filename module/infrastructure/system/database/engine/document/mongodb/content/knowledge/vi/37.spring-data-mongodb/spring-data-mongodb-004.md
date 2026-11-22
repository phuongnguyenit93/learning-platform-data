# MongoRepository, phương thức suy diễn và truy vấn @Query trong Spring Data MongoDB

## 1. Bài toán: viết truy vấn MongoDB trong ứng dụng Spring như thế nào?

Một ứng dụng Java quản lý đơn hàng thường cần các thao tác:

- Tìm đơn hàng theo `tenantId` và `status`.
- Lấy một đơn hàng theo ID, kiểm tra sự tồn tại.
- Lọc các đơn có số tiền từ một ngưỡng, theo ngày tạo hoặc địa chỉ giao hàng.
- Sắp xếp mới nhất trước, phân trang và chỉ lấy một vài trường.
- Kiểm tra trùng mã đơn trong cùng một tenant.
- Tìm theo một điều kiện MongoDB phức tạp hơn tên phương thức thông thường có thể diễn đạt.
- Cập nhật hoặc xóa có kiểm soát, theo dõi số bản ghi bị ảnh hưởng.

Spring Data MongoDB có **repository abstraction** để giải quyết phần lớn những công việc đó mà không phải viết mã `MongoTemplate` cho mọi truy vấn.

Ba khái niệm chính của bài:

1. **`MongoRepository<T, ID>`**: interface cho các thao tác CRUD và những truy vấn mặc định.
2. **Derived query methods (phương thức suy diễn)**: Spring Data phân tích tên phương thức, ví dụ `findByTenantIdAndStatus`, rồi tạo truy vấn MongoDB tương ứng.
3. **`@Query`**: khai báo truy vấn bằng chuỗi MongoDB JSON khi muốn rõ filter, các toán tử phức tạp, projection hoặc một số option không tiện diễn đạt qua tên.

Điểm then chốt: **`MongoRepository` không thay MongoDB query planner hay index**. Spring Data chỉ giúp diễn đạt/truyền truy vấn; tốc độ thực tế vẫn phụ thuộc index, dữ liệu, query shape, server capacity và network.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Tạo `@Document` entity và `MongoRepository` cho MongoDB.
- Dùng `save`, `insert`, `findById`, `findAll`, `deleteById`, `count`, `existsById` đúng semantics.
- Suy diễn `And`, `Or`, `GreaterThan`, `Between`, `In`, `IsNull`, `Exists`, `True`, `Containing`, `IgnoreCase`, `OrderBy`, `Top`.
- Truy vấn thuộc tính lồng nhau qua `findByShipping_City`; hiểu dấu gạch dưới tách property path.
- Dùng `Pageable`, `Sort`, `Page`, `Slice`, `Stream` và giới hạn số results.
- Viết `@Query` với `?0`, `?1`, `fields`, `sort`, `collation`, `hint`, `count`, `exists`, `delete`.
- Hiểu sự khác nhau giữa **Java property names**, BSON field names và `@Field`.
- Sử dụng projection interfaces/DTO để tránh tải document đầy đủ.
- Nhận biết khi nên chuyển sang `MongoTemplate`, `@Aggregation` hoặc custom repository implementation.
- Kiểm thử thực tế và phòng lỗi query logic, bảo mật multi-tenancy, pagination lớn và query chậm.

---

## 2. MongoRepository nằm ở đâu trong kiến trúc?

Một request Spring MVC có thể đi qua:

```text
HTTP /orders?status=PAID
            |
            v
       Controller
            |
            v
        Service
            |
            v
      OrderRepository
      extends MongoRepository
            |
            v
   Spring Data Repository Proxy
            |
            v
 MappingMongoConverter + MongoDB Java Driver
            |
            v
       MongoDB Server
       orders collection
```

Khi khởi động application context, Spring Data tìm các repository interfaces, tạo implementation/proxy tương ứng và dùng metadata entity để mapping/query.

### 2.1. Interface không cần class tự viết cho CRUD cơ bản

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<Order, String> {
}
```

Dù không có `OrderRepositoryImpl`, ứng dụng vẫn dùng:

```java
repository.save(order);
repository.findById("O-100");
repository.existsById("O-100");
repository.findAll();
repository.count();
repository.deleteById("O-100");
```

Các thao tác này do framework implement.

### 2.2. MongoRepository kế thừa những gì?

Ở các Spring Data MongoDB versions hiện đại, `MongoRepository` kế thừa những capabilities như:

- CRUD qua `ListCrudRepository`.
- Paging/sorting qua `ListPagingAndSortingRepository`.
- Query by Example qua `QueryByExampleExecutor`.
- Những phương thức MongoDB-specific như `insert`.

Điều này có nghĩa `MongoRepository` có các method CRUD với những signature/return types theo version hiện tại. Khi nâng Spring Data major version, kiểm tra interface API nếu mã dùng những methods kế thừa.

### 2.3. Repository abstraction không phải Active Record

`Order` là domain/mapping object; nó không tự gọi `order.save()` khi có repository theo mẫu này. Logic truy cập dữ liệu đặt ở repository/service.

Ví dụ:

```java
@Service
public class OrderService {
    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public Optional<Order> findOne(String id) {
        return orders.findById(id);
    }
}
```

Lớp `OrderService` là service bean Spring, còn `OrderRepository` được Spring Data tạo implementation lúc runtime.

---

## 3. Chuẩn bị Spring Boot và MongoDB

### 3.1. Dependency

Dùng Spring Boot dependency management thay vì tự trộn phiên bản Spring Data/driver:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "<approved-boot-version>"
    id("io.spring.dependency-management") version "<approved-version>"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-mongodb")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Đây là **mẫu cấu trúc Gradle Kotlin DSL**; placeholders phải thay bằng versions thực được duyệt. Không chạy Gradle trong bài học. Một Spring Boot project đã có plugin/BOM tương thích không cần khai báo lại mọi thành phần giống ví dụ.

Maven có dependency tương ứng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
```

### 3.2. Cấu hình database lab

Trong `src/main/resources/application.properties` của **môi trường học**:

```properties
spring.data.mongodb.uri=mongodb://127.0.0.1:27017/order_repository_lab
```

Nếu dùng Spring Boot phiên bản có khác biệt configuration properties, đối chiếu documentation đúng version. Production nên dùng secrets manager/environment variables và TLS/credentials, không commit URI chứa mật khẩu.

### 3.3. Repository scanning

Nếu repository nằm dưới package của class `@SpringBootApplication`, Spring Boot thường tự cấu hình Spring Data repositories.

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

Ví dụ package tree:

```text
com.example.orders
  OrdersApplication.java
  domain/Order.java
  repository/OrderRepository.java
  service/OrderService.java
```

Nếu repository ở ngoài vùng component/repository scanning, có thể dùng `@EnableMongoRepositories(basePackages = ...)`, nhưng phải kiểm tra multi-datasource/multiple MongoTemplates để tránh trỏ nhầm database.

---

## 4. Entity: mapping Java object thành MongoDB document

Tạo entity `Order`:

```java
package com.example.orders.domain;

import java.math.BigDecimal;
import java.util.Date;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.index.CompoundIndex;

@Document(collection = "orders")
@CompoundIndex(
    name = "ix_tenant_status_createdAt",
    def = "{ 'tenantId': 1, 'status': 1, 'createdAt': -1 }"
)
public class Order {

    @Id
    private String id;

    private String tenantId;
    private String orderNumber;
    private String status;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal amount;

    private Date createdAt;
    private boolean active;
    private List<String> tags;
    private Shipping shipping;

    public Order() {}

    // Getters/setters cho tất cả thuộc tính được lược bớt
    // để tập trung vào repository queries.

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getStatus() { return status; }
    public BigDecimal getAmount() { return amount; }
    public Date getCreatedAt() { return createdAt; }
    public Shipping getShipping() { return shipping; }

    public static class Shipping {
        private String city;
        private String district;

        public Shipping() {}

        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }
        public String getDistrict() { return district; }
        public void setDistrict(String district) {
            this.district = district;
        }
    }
}
```

Đây là đoạn entity phục vụ việc minh họa mapping/queries; khi xây ứng dụng thực, tạo đầy đủ constructors, getters/setters theo mô hình entity của dự án (hoặc dùng immutable types với constructor mapping đúng).

### 4.1. Ý nghĩa các annotations

| Annotation | Tác dụng |
| --- | --- |
| `@Document(collection = "orders")` | Mapping class vào collection `orders` |
| `@Id` | Mapping property ID vào BSON `_id` |
| `@Field` | Tùy chỉnh field name hoặc BSON target type |
| `@CompoundIndex` | Khai báo metadata index compound |
| `@Indexed` | Khai báo metadata single-field index |
| `@Version` | Hỗ trợ optimistic locking khi được cấu hình/mapping đúng |

**Quan trọng:** `@CompoundIndex` không đảm bảo MongoDB sẽ tự tạo index trên production. **Automatic index creation bị tắt mặc định** trong Spring Data MongoDB hiện đại; hãy quản lý index qua migration/provisioning được kiểm soát hoặc bật auto-index creation có chủ đích trong môi trường phù hợp.

### 4.2. BigDecimal và Decimal128

Java `BigDecimal` không nên được mặc định coi là cùng kiểu với BSON `Decimal128` ở mọi mapping configuration.

Trong entity trên:

```java
@Field(targetType = FieldType.DECIMAL128)
private BigDecimal amount;
```

yêu cầu mapping field theo BSON Decimal128. Điều này quan trọng với tìm kiếm tiền tệ/range; các documents thử nghiệm phải lưu cùng kiểu tương thích. Không dùng `double` cho tiền nếu business cần precision thập phân chính xác.

### 4.3. @Id và reserved methods

`findById(id)` là phương thức cơ sở đặc biệt, **nhắm vào identifier property**, dù entity có một Java field khác cũng tên `id` hoặc tên ID thật khác.

Ví dụ entity có `@Id String primaryKey` và `String id` thông thường:

- `findById(x)` nhắm tới `primaryKey` (BSON `_id`).
- Một query method có tên phân biệt, ví dụ `findUserById(x)`, có thể nhắm đến property `id` thông thường.

Đừng đặt property tên gần giống ID rồi dựa vào suy đoán; hiểu rõ repository reserved method names.

---

## 5. Dữ liệu lab cho toàn bài

Chạy các lệnh sau trong `mongosh` trên **MongoDB lab**, không chạy `drop()` ở production.

```javascript
const lab = db.getSiblingDB("order_repository_lab");

lab.orders.drop();

lab.orders.insertMany([
  {
    _id: "O-101",
    tenantId: "A",
    orderNumber: "A-001",
    status: "PAID",
    amount: NumberDecimal("125.50"),
    createdAt: ISODate("2026-11-01T08:00:00Z"),
    active: true,
    tags: ["vip", "online"],
    shipping: { city: "Hà Nội", district: "Ba Đình" }
  },
  {
    _id: "O-102",
    tenantId: "A",
    orderNumber: "A-002",
    status: "NEW",
    amount: NumberDecimal("49.90"),
    createdAt: ISODate("2026-11-02T08:00:00Z"),
    active: true,
    tags: ["online"],
    shipping: { city: "Đà Nẵng", district: "Hải Châu" }
  },
  {
    _id: "O-103",
    tenantId: "A",
    orderNumber: "A-003",
    status: "PAID",
    amount: NumberDecimal("300.00"),
    createdAt: ISODate("2026-11-03T08:00:00Z"),
    active: true,
    tags: ["priority"],
    shipping: { city: "Hà Nội", district: "Cầu Giấy" }
  },
  {
    _id: "O-104",
    tenantId: "B",
    orderNumber: "B-001",
    status: "PAID",
    amount: NumberDecimal("80.00"),
    createdAt: ISODate("2026-11-04T08:00:00Z"),
    active: true,
    tags: ["online"],
    shipping: { city: "TP. Hồ Chí Minh", district: "Quận 1" }
  },
  {
    _id: "O-105",
    tenantId: "A",
    orderNumber: "A-004",
    status: "CANCELLED",
    amount: NumberDecimal("10.00"),
    createdAt: ISODate("2026-11-05T08:00:00Z"),
    active: false,
    tags: [],
    shipping: { city: "Hà Nội", district: "Đống Đa" }
  },
  {
    _id: "O-106",
    tenantId: "B",
    orderNumber: "B-002",
    status: "NEW",
    amount: NumberDecimal("15.75"),
    createdAt: ISODate("2026-11-06T08:00:00Z"),
    active: true,
    tags: ["app"],
    shipping: { city: "Cần Thơ", district: "Ninh Kiều" }
  },
  {
    _id: "O-107",
    tenantId: "A",
    orderNumber: "A-005",
    status: "PAID",
    amount: NumberDecimal("9.95"),
    createdAt: ISODate("2026-11-07T08:00:00Z"),
    active: true,
    tags: ["online"],
    shipping: { city: "Hải Phòng", district: "Lê Chân" }
  },
  {
    _id: "O-108",
    tenantId: "B",
    orderNumber: "B-003",
    status: "PAID",
    amount: NumberDecimal("999.99"),
    createdAt: ISODate("2026-11-08T08:00:00Z"),
    active: true,
    tags: ["vip", "priority"],
    shipping: { city: "Hà Nội", district: "Long Biên" }
  }
]);

lab.orders.createIndex(
  { tenantId: 1, orderNumber: 1 },
  { unique: true, name: "uq_tenant_orderNumber" }
);

lab.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "ix_tenant_status_createdAt" }
);

lab.orders.countDocuments({});
// 8
```

### 5.1. Kiểm tra kiểu và indexes

```javascript
lab.orders.getIndexes();

lab.orders.aggregate([
  {
    $project: {
      orderNumber: 1,
      amountType: { $type: "$amount" },
      createdAtType: { $type: "$createdAt" }
    }
  }
]).toArray();
```

Kỳ vọng `amountType` là `decimal` và `createdAtType` là `date`. Thứ tự documents khi không có sort **không có bảo đảm nghiệp vụ**.

---

## 6. MongoRepository: CRUD cơ bản

Repository tối thiểu:

```java
package com.example.orders.repository;

import com.example.orders.domain.Order;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<Order, String> {
}
```

### 6.1. Tìm theo ID

```java
Optional<Order> found = repository.findById("O-101");

found.ifPresent(order ->
    System.out.println(order.getStatus())
);
```

`findById` trả `Optional<Order>`. Không có document → `Optional.empty()`, không phải exception “not found”.

### 6.2. Kiểm tra tồn tại và đếm

```java
boolean exists = repository.existsById("O-101");
long total = repository.count();
```

`existsById` không cần load toàn document như `findById` khi chỉ cần câu trả lời có/không.

### 6.3. Save và insert khác nhau

```java
Order saved = repository.save(order);
Order inserted = repository.insert(newOrder);
```

- `save`: lưu entity, có semantics insert hoặc update/replace theo ID và mapping/concurrency conditions.
- `insert`: dành cho entity mới; nếu ID đã tồn tại, có thể gặp duplicate key exception.
- Không mặc định `save` là `$set` một vài field. Khi lưu entity cũ với fields thiếu, có nguy cơ thay document không như mong muốn.
- Với concurrent changes, cân nhắc `@Version` optimistic locking hoặc targeted update bằng `MongoTemplate`/`@Update`.

### 6.4. Delete

```java
repository.deleteById("O-105");
```

**Lệnh xóa dữ liệu**: chỉ chạy ở lab hoặc nơi được phê duyệt. Không đưa endpoint xóa vào production mà bỏ qua authorization, audit và tenant scoping.

### 6.5. findAll() và findAll(Pageable)

```java
List<Order> all = repository.findAll();
```

Có thể nguy hiểm khi collection lớn: `findAll()` materialize nhiều documents và tăng RAM/network.

Ưu tiên:

```java
Pageable pageRequest = PageRequest.of(
    0, 20,
    Sort.by(Sort.Direction.DESC, "createdAt")
);

Page<Order> firstPage = repository.findAll(pageRequest);
```

`PageRequest` cần imports từ `org.springframework.data.domain`. Trong multi-tenant service, `findAll(pageRequest)` vẫn **không có tenant filter**; phải dùng repository method có điều kiện tenant.

---

## 7. Phương thức suy diễn là gì?

Spring Data đọc **tên method** rồi phân tích thành truy vấn MongoDB.

Ví dụ:

```java
List<Order> findByTenantIdAndStatus(
    String tenantId,
    String status
);
```

về mặt logic tương ứng:

```javascript
db.orders.find({
  tenantId: "A",
  status: "PAID"
});
```

Để Spring Data tạo method, chỉ cần khai báo nó trong repository interface:

```java
public interface OrderRepository
        extends MongoRepository<Order, String> {

    List<Order> findByTenantIdAndStatus(
        String tenantId,
        String status
    );
}
```

Bạn không phải viết implementation.

### 7.1. Cấu trúc tên method

```text
find   Orders   By    TenantId   And   Status   OrderByCreatedAtDesc
 |       |      |        |        |       |              |
prefix  mô tả  ranh     field     AND    field          sort
                giới
```

Các prefixes thường gặp:

- `find...By`, `read...By`, `get...By`, `query...By`, `search...By`.
- `count...By`.
- `exists...By`.
- `delete...By`, `remove...By`.

Phần giữa `find` và `By` thường là mô tả, trừ các từ khóa có ý nghĩa như `Distinct`, `Top`, `First`.

### 7.2. Query lookup strategy

Spring Data có ba chiến lược:

| Strategy | Ý nghĩa |
| --- | --- |
| `CREATE` | Tạo truy vấn từ tên phương thức |
| `USE_DECLARED_QUERY` | Bắt buộc phải tìm truy vấn khai báo, thiếu thì lỗi |
| `CREATE_IF_NOT_FOUND` | Ưu tiên truy vấn khai báo; nếu thiếu, suy diễn từ tên |

`CREATE_IF_NOT_FOUND` là default phổ biến. Nó giúp chuyển dần từ derived query sang `@Query` mà không cần viết implementation mới.

### 7.3. Tên property là tên Java, không phải BSON field tùy tiện

Nếu entity có `customer.email`, bạn có thể viết:

```java
List<Order> findByCustomer_Email(String email);
```

Spring Data dùng mapping metadata để tìm đúng field trong BSON, kể cả khi các Java properties có `@Field` rename. Vì vậy refactor tên Java property có thể làm thay đổi query methods.

---

## 8. Các toán tử suy diễn thường dùng

Bảng sau sử dụng entity `Order` trong lab.

| Method | Logic MongoDB | Ghi chú |
| --- | --- | --- |
| `findByStatus("PAID")` | `{status:"PAID"}` | Equality |
| `findByTenantIdAndStatus("A","PAID")` | `{$and:[...] }` | Kết hợp AND |
| `findByStatusOrActive("PAID",true)` | `{$or:[...] }` | OR |
| `findByAmountGreaterThan(x)` | `{amount:{$gt:x}}` | Lớn hơn, không gồm x |
| `findByAmountGreaterThanEqual(x)` | `{amount:{$gte:x}}` | Lớn hơn hoặc bằng |
| `findByAmountLessThan(x)` | `{amount:{$lt:x}}` | Nhỏ hơn |
| `findByCreatedAtAfter(date)` | `{createdAt:{$gt:date}}` | Sau mốc |
| `findByCreatedAtBefore(date)` | `{createdAt:{$lt:date}}` | Trước mốc |
| `findByStatusIn(list)` | `{status:{$in:list}}` | Tập giá trị |
| `findByStatusNotIn(list)` | `{status:{$nin:list}}` | Loại trừ |
| `findByActiveTrue()` | `{active:true}` | Boolean |
| `findByActiveFalse()` | `{active:false}` | Boolean |
| `findByShipping_City(city)` | `{"shipping.city":city}` | Nested path |
| `findByOrderNumberStartingWith(prefix)` | Regex prefix | Cần lưu ý index |
| `findByOrderNumberEndingWith(suffix)` | Regex suffix | Thường khó dùng index |
| `findByOrderNumberContaining(text)` | Regex contains | Có thể scan nhiều |
| `findByOrderNumberRegex(pattern)` | `$regex` | Xem input safety |
| `findByShippingExists(flag)` | `{shipping:{$exists:flag}}` | Field existence |
| `findByStatusIsNull()` | `{status:null}` | Match cả missing trong semantics MongoDB |
| `findByStatusNot("PAID")` | `{status:{$ne:"PAID"}}` | Match có thể bao gồm missing |
| `findByTagsContaining("vip")` | Membership trong collection | Kiểm tra semantics theo kiểu field và version |

Các method trên là **minh họa cú pháp**; muốn compile một method phải có kiểu property tương ứng trong entity.

### 8.1. Viết một repository thực tế

```java
import java.math.BigDecimal;
import java.util.Collection;
import java.util.Date;
import java.util.List;

public interface OrderRepository
        extends MongoRepository<Order, String> {

    List<Order> findByTenantIdAndStatus(
        String tenantId, String status);

    List<Order> findByTenantIdAndAmountGreaterThanEqual(
        String tenantId, BigDecimal min);

    List<Order> findByTenantIdAndStatusIn(
        String tenantId, Collection<String> statuses);

    List<Order> findByTenantIdAndActiveTrue(String tenantId);

    List<Order> findByShipping_City(String city);

    List<Order> findByCreatedAtAfter(Date after);

    List<Order> findByOrderNumberStartingWith(String prefix);

    long countByTenantIdAndStatus(String tenantId, String status);

    boolean existsByTenantIdAndOrderNumber(
        String tenantId, String orderNumber);
}
```

Imports của `Order` và `MongoRepository` đã được nêu ở mục trước.

### 8.2. Cần xem “Between” thật kỹ

Spring Data MongoDB documentation mô tả một số trường hợp `Between` với hai scalar arguments theo bounds mở:

```java
List<Order> findByAmountBetween(
    BigDecimal from, BigDecimal to);
```

Không mặc định “between” luôn là **bao gồm cả hai đầu**. Hãy xác minh mapping thành `$gt`/`$lt` hoặc kiểu `Range<T>` với bounds được chỉ rõ trên phiên bản đang dùng.

Để tránh mơ hồ và yêu cầu inclusive:

```java
List<Order>
findByAmountGreaterThanEqualAndAmountLessThanEqual(
    BigDecimal min, BigDecimal max);
```

Ở ngữ cảnh tenant, thêm `TenantId` vào method hoặc sử dụng `@Query` để không quên phân vùng dữ liệu.

### 8.3. “IsNull” và “Exists” không như nhau

Trong MongoDB:

```javascript
{ status: null }
```

thường khớp document có `status` là `null` **hoặc thiếu field**.

Ngược lại:

```javascript
{ status: { $exists: false } }
```

chỉ khớp document **không có field**.

Muốn tìm **null có field thực sự**, cần điều kiện bổ sung thích hợp (ví dụ `$type`) thay vì mặc định `findByStatusIsNull()` đủ chính xác.

---

## 9. AND/OR: tránh query logic sai

Giả sử muốn:

> Tìm tất cả đơn của tenant A và status là PAID **hoặc NEW**.

Điều kiện đúng:

```javascript
{
  tenantId: "A",
  status: { $in: ["PAID", "NEW"] }
}
```

Trong repository:

```java
List<Order> findByTenantIdAndStatusIn(
    String tenantId,
    Collection<String> statuses
);
```

Một tên method dễ đọc sai:

```java
List<Order> findByTenantIdAndStatusOrActive(
    String tenantId,
    String status,
    boolean active
);
```

có logic tương đương `(tenantId = A AND status = PAID) OR active = true`, có thể lấy dữ liệu **của tenant B** nếu `active=true`. Đây là lỗi truy cập chéo tenant nghiêm trọng.

### 9.1. Viết @Query khi cần ngoặc logic

```java
@Query("""
    {
      'tenantId': ?0,
      '$or': [
        { 'status': ?1 },
        { 'active': ?2 }
      ]
    }
    """)
List<Order> findByTenantAndStatusOrActive(
    String tenantId, String status, boolean active
);
```

Ở đây điều kiện tenant áp dụng cho **cả hai nhánh OR**, khác method sai phía trên.

Nếu dự án dùng Java trước 15, **text block `"""` không hỗ trợ**; dùng string thường nối dòng, nhưng vẫn giữ JSON structure.

### 9.2. Quy tắc multi-tenant

Với dữ liệu đa tenant:

- Tất cả queries nghiệp vụ phải có tenant scope hoặc cơ chế bảo vệ được kiểm chứng ở tầng dữ liệu/authorization.
- Không để client tự chỉ định tenant ID mà chưa đối chiếu với principal.
- Không trả `findAll()` trực tiếp qua REST API.
- Kiểm thử cả “tenant A không thấy tenant B” với từng query shape, bao gồm OR, delete và count.
- Index có `tenantId` ở prefix phù hợp có thể quan trọng cho hiệu năng và cách truy cập.

**Spring Data repository không tự thực thi tenant isolation** chỉ vì entity có field `tenantId`.

---

## 10. Nested property và dấu gạch dưới

Entity:

```java
public static class Shipping {
    private String city;
    private String district;
    // constructors/getters/setters...
}
```

MongoDB document:

```javascript
{
  shipping: {
    city: "Hà Nội",
    district: "Ba Đình"
  }
}
```

Method:

```java
List<Order> findByShipping_City(String city);
```

Spring Data diễn giải `Shipping_City` thành property path `shipping.city`.

### 10.1. Có thể bỏ underscore?

Thông thường có thể viết:

```java
List<Order> findByShippingCity(String city);
```

Parser thử tách camel-case, nhưng nếu class còn có một property `shippingCity`, việc phân giải có thể trở nên **mơ hồ**. Dấu gạch dưới cho phép định nghĩa điểm tách rõ ràng.

### 10.2. Đừng dùng underscore tùy tiện trong Java property names

Spring Data dành underscore cho property traversal. Nếu domain fields chứa underscore, những quy tắc escape đặc biệt có thể áp dụng; nên tuân theo Java camelCase khi thiết kế entity.

### 10.3. @Field mapping

Giả sử:

```java
@Field("shipping_city")
private String shippingCity;
```

Derived query vẫn dựa vào Java property `shippingCity`, và Spring Data mapping layer sẽ chuyển sang BSON `shipping_city`.

Với native `@Query`, cũng có mapping query fields qua `MappingMongoConverter` trong những trường hợp được hỗ trợ; không nên trộn Java property names/BSON field names mà không kiểm tra generated MongoDB query thực tế, đặc biệt với field name chứa dấu chấm hoặc schema migration.

---

## 11. Kiểu trả về: Optional, List, Page, Slice, Stream

Phương thức repository không chỉ khác nhau về filter. **Return type** tác động số records được đọc và semantics.

| Return type | Khi dùng | Điều chú ý |
| --- | --- | --- |
| `Optional<Order>` | Không hoặc một kết quả | Nhiều matches ngoài dự kiến có thể gây lỗi |
| `Order` | Dự kiến một kết quả | Không có kết quả có thể trả null/nullable theo cấu hình |
| `List<Order>` | Một tập nhỏ, có giới hạn hợp lý | Có thể tốn RAM nếu không limit |
| `Page<Order>` | Cần cả content và total count | Count query có thể tốn chi phí |
| `Slice<Order>` | Chỉ cần biết còn trang kế tiếp | Tránh total count chung |
| `Stream<Order>` | Đọc tuần tự số lượng lớn | Phải đóng stream/cursor |
| `long` | Count/delete count | Không tải entity đầy đủ |
| `boolean` | Exists | Kiểm tra nhanh tồn tại |
| `Mono/Flux` | ReactiveMongoRepository | Không phải Sync MongoRepository |

### 11.1. Optional có nghĩa gì?

```java
Optional<Order> order =
    repository.findByTenantIdAndOrderNumber(
        "A", "A-001"
    );
```

Nếu business rule yêu cầu duy nhất nhưng MongoDB không có unique index thì có thể tồn tại nhiều records matching. Method single-result **không phải công cụ đảm bảo uniqueness**; nên tạo index:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderNumber: 1 },
  { unique: true }
);
```

### 11.2. findFirst/Top hạn chế số results

```java
Optional<Order> findFirstByTenantIdAndStatusOrderByCreatedAtDesc(
    String tenantId,
    String status
);
```

`First`/`Top` giới hạn số kết quả. Kết hợp `OrderBy` giúp lấy “mới nhất” có chủ đích.

**Để ổn định khi timestamps bằng nhau**, cần thêm `IdDesc` hoặc sort theo khóa duy nhất:

```java
Optional<Order> findFirstByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
    String tenantId, String status
);
```

Nếu không có sort, “first” không bảo đảm là document mới nhất.

### 11.3. Top N

```java
List<Order> findTop5ByTenantIdAndStatusOrderByCreatedAtDesc(
    String tenantId, String status
);
```

Nó giới hạn tối đa 5 kết quả sau filter/sort. Với API tổng quát có dynamic page size, `Pageable` linh hoạt hơn.

### 11.4. Stream cần đóng

```java
try (Stream<Order> stream =
         repository.streamByTenantId("A")) {

    stream.forEach(order -> process(order));
}
```

`process(order)` là business function tự triển khai. `Stream` có thể giữ tài nguyên cursor; **dùng try-with-resources**. Không giữ stream vượt ngoài transaction/lifetime phù hợp.

---

## 12. Sort động và Sort tĩnh

### 12.1. Sort tĩnh trong tên

```java
List<Order> findByTenantIdOrderByCreatedAtDesc(
    String tenantId
);
```

### 12.2. Sort động bằng tham số

```java
List<Order> findByTenantId(
    String tenantId,
    Sort sort
);
```

Gọi:

```java
List<Order> results = repository.findByTenantId(
    "A",
    Sort.by(Sort.Direction.DESC, "createdAt")
        .and(Sort.by(Sort.Direction.DESC, "id"))
);
```

`Sort` dùng **domain property names**, Spring Data mapping quyết định field BSON tương ứng.

### 12.3. Sort theo nhiều khóa

Tại sao cần khóa thứ hai?

```text
createdAt có thể trùng giữa hai orders:
2026-11-07T08:00Z, O-101
2026-11-07T08:00Z, O-102
```

Nếu chỉ sort theo createdAt, thứ tự hai records có thể không ổn định khi index/plan/updates thay đổi. Thêm `id` tạo tie-breaker có tính xác định.

### 12.4. Đừng cho client truyền field sort tùy ý

Một API:

```text
GET /orders?sort=anyNestedField
```

có thể bị lạm dụng để sort theo field không index, expensive paths hoặc leak dữ liệu qua timing. Dùng **allow-list**:

```java
Set<String> allowedSortFields =
    Set.of("createdAt", "amount", "orderNumber");
```

Sau đó kiểm tra requested sort property/direction trước khi tạo `Sort`.

---

## 13. Paging bằng Pageable

Khai báo:

```java
Page<Order> findByTenantIdAndStatus(
    String tenantId,
    String status,
    Pageable pageable
);
```

Gọi:

```java
Pageable pageable = PageRequest.of(
    0,                                     // page đầu tiên, zero-based
    20,                                    // tối đa 20 items
    Sort.by(Sort.Direction.DESC, "createdAt")
        .and(Sort.by("id").descending())
);

Page<Order> page = repository.findByTenantIdAndStatus(
    "A", "PAID", pageable
);

System.out.println(page.getContent().size());
System.out.println(page.getTotalElements());
System.out.println(page.getTotalPages());
System.out.println(page.hasNext());
```

### 13.1. Page khác Slice

- `Page<T>` chứa content, page index và **total elements/pages**. Framework có thể cần chạy một **count query bổ sung**, tùy khả năng tối ưu.
- `Slice<T>` chỉ cần content và thông tin **có trang sau hay không**, có thể tránh count tổng.
- `List<T>` với `Pageable` có thể áp skip/limit/sort nhưng không tạo metadata count.

Ví dụ:

```java
Slice<Order> findByTenantIdAndStatus(
    String tenantId, String status, Pageable pageable
);
```

**Lưu ý Java overload:** không thể có hai methods cùng tên/cùng parameter types nhưng chỉ khác return type `Page` và `Slice` trong cùng interface. Hãy đặt tên khác nhau, ví dụ `findPageByTenantIdAndStatus` và `findSliceByTenantIdAndStatus`, hoặc chọn một dạng trả về cho mỗi method.

### 13.2. Offset pagination có chi phí

`PageRequest.of(100000, 20, sort)` thường chuyển thành skip rất lớn. MongoDB có thể phải duyệt qua nhiều records trước khi trả trang mong muốn; đồng thời insert/delete giữa các lần request làm thứ tự thay đổi.

Với dữ liệu lớn hoặc infinite scrolling, cân nhắc:

- Keyset/cursor-based pagination.
- `ScrollPosition`/`Window` trong những Spring Data versions hỗ trợ.
- Sort theo compound key ổn định, ví dụ `(createdAt, _id)`.
- Seek condition dựa last-seen key.
- Index phù hợp filter và sort.

**Không dùng offset sâu** làm mặc định nếu endpoint cần scan hàng triệu documents.

### 13.3. Pageable và Sort/Limit không luôn được ghép tùy tiện

Spring Data repository infrastructure có special parameters như `Pageable`, `Sort` và `Limit`, nhưng nhiều tổ hợp là **không hợp lệ**:

- `Pageable` đã chứa sort, không cần `Sort` thứ hai.
- `Pageable` đã chứa limit, không ghép `Limit` tùy tiện.
- `Top`/`First` có semantics giới hạn riêng.

Đối chiếu Query Methods documentation của đúng Spring Data release trước khi định nghĩa signatures mới.

---

## 14. Khi nào nên chuyển từ derived query sang @Query?

Derived queries rất thuận tiện với filter đơn giản nhưng có các giới hạn:

- Tên method quá dài, khó đọc.
- Điều kiện `$or` có ngoặc nhóm phức tạp.
- Cần `$elemMatch` cho mảng document.
- Cần explicit `$exists` kết hợp `$type`.
- Cần projection field list hoặc sort/hint/collation cụ thể.
- Phải biểu diễn MongoDB operators mà tên suy diễn không hỗ trợ rõ ràng.
- Muốn truy vấn cố định và dễ đối chiếu với mongosh/explain.

Ví dụ query phức tạp:

```javascript
{
  tenantId: "A",
  active: true,
  $or: [
    { status: "PAID", amount: { $gte: NumberDecimal("100.00") } },
    { tags: "vip" }
  ]
}
```

Một tên `findByTenantIdAndActiveTrueAndStatusAndAmountGreaterThanEqualOrTagsContaining` khó đọc và rất dễ bị **lỗi ưu tiên logic**.

Với `@Query`, diễn đạt cấu trúc rõ hơn.

---

## 15. @Query: khai báo MongoDB JSON filter

Import:

```java
import org.springframework.data.mongodb.repository.Query;
```

Ví dụ:

```java
@Query("{ 'tenantId': ?0, 'status': ?1 }")
List<Order> findExplicitlyByTenantAndStatus(
    String tenantId, String status
);
```

Cơ chế:

- `?0` lấy **đối số method thứ nhất**.
- `?1` lấy **đối số thứ hai**.
- Tham số là **zero-based**.
- Spring Data bind/conversion giá trị sang BSON/query phù hợp.

### 15.1. Filter JSON ở @Query không phải SQL

**Đúng:**

```java
@Query("{ 'amount': { '$gte': ?0 } }")
List<Order> amountAtLeast(BigDecimal min);
```

**Sai:**

```java
@Query("SELECT * FROM orders WHERE amount >= ?0")
List<Order> amountAtLeastSql(BigDecimal min);
```

Spring Data MongoDB sử dụng **MongoDB query language**, không dùng JDBC SQL/HQL/JPQL.

### 15.2. String binding tự escape giá trị

Tài liệu Spring Data MongoDB chỉ rõ: tham số String được **escaped trong quá trình binding**; không thể thêm MongoDB operators vào query chỉ bằng cách đưa một chuỗi chứa JSON vào `?0`.

Ví dụ:

```java
@Query("{ 'status': ?0 }")
List<Order> findStatus(String status);
```

Nếu tham số là chuỗi `"{ '$ne': null }"`, nó không được tự động biến thành operator `$ne`. Nó được xử lý như **giá trị String**.

Điều này **không có nghĩa mọi chỗ dùng SpEL hoặc tự nối JSON đều an toàn**. Không xây query JSON bằng string concatenation từ dữ liệu người dùng.

### 15.3. Query động dùng SpEL

```java
@Query("{ 'status': ?#{[0]} }")
List<Order> findStatusWithSpEL(String status);
```

Ở đây `?#{[0]}` lấy argument thứ nhất qua Spring Expression Language. SpEL mạnh hơn indexed parameters: có thể gọi functions, viết conditional, tạo subdocuments.

**Cảnh báo:** Spring Data docs nhấn mạnh cần sanitize input khi dùng SpEL vì expression có thể tạo cấu trúc query không mong muốn. Đối với filter đơn giản, **ưu tiên `?0` và `?1`**.

### 15.4. Áp điều kiện tenant lên toàn bộ OR

```java
@Query("""
    {
      'tenantId': ?0,
      'active': true,
      '$or': [
        {
          'status': ?1,
          'amount': { '$gte': ?2 }
        },
        { 'tags': ?3 }
      ]
    }
    """)
List<Order> findBusinessCandidates(
    String tenantId,
    String status,
    BigDecimal minAmount,
    String requiredTag
);
```

Lưu ý `tags: ?3` tìm array chứa giá trị tương ứng theo MongoDB array equality matching, không cần custom regex. Kiểm thử tenant A/B trước khi expose API.

---

## 16. @Query fields: trả ít trường hơn

Khi chỉ cần `status`, `amount` và `createdAt`, không nên luôn tải toàn bộ document dài gồm notes, address và large arrays.

```java
@Query(
    value = "{ 'tenantId': ?0, 'status': ?1 }",
    fields = "{ 'status': 1, 'amount': 1, 'createdAt': 1 }"
)
List<Order> findStatusAndAmount(
    String tenantId, String status
);
```

MongoDB projection **bao gồm `_id` theo mặc định** trừ khi khai báo loại bỏ.

### 16.1. Quan trọng: returned entity có thể là partial

Với return type `Order`, những fields **không được load** thường có giá trị Java mặc định (`null`/`false` tùy kiểu).

Không lấy entity partial rồi gọi `save` bừa bãi:

```java
// Cần tránh: đây là partial Order, không phải aggregate đầy đủ.
Order partial = repository.findStatusAndAmount("A", "PAID").get(0);
repository.save(partial);
```

Bạn có thể ghi đè document theo trạng thái thiếu fields, gây mất dữ liệu hoặc lỗi business.

### 16.2. Fields projection và @Field mapping

`fields` sử dụng MongoDB projection document dưới dạng JSON. Khi có `@Field`/custom conversions, kiểm tra cách field names được mapping để tránh trả thiếu property. Không nhầm `fields` với `$project` stage của aggregation pipeline.

### 16.3. Exclusion projection

```java
@Query(
    value = "{ 'tenantId': ?0 }",
    fields = "{ 'largePayload': 0, 'privateNotes': 0 }"
)
List<Order> findWithoutLargeFields(String tenantId);
```

Chỉ loại bỏ fields lớn không đồng nghĩa tránh leak dữ liệu nếu còn dữ liệu nhạy cảm khác. **Dùng DTO/projection rõ ràng cho API responses** tốt hơn việc trả raw entity.

---

## 17. Interface-based projections và DTOs

### 17.1. Closed interface projection

```java
public interface OrderSummary {
    String getId();
    String getStatus();
    BigDecimal getAmount();
}
```

Repository:

```java
List<OrderSummary> findByTenantIdAndStatus(
    String tenantId, String status
);
```

Spring Data có thể biết các properties cần thiết và tối ưu fields được tải khi dùng **closed projection**.

Nếu entity/repository đã có method trùng signature với return `List<Order>`, không thể khai báo thêm overload chỉ khác return type. Đặt tên khác, ví dụ:

```java
List<OrderSummary> findSummaryByTenantIdAndStatus(
    String tenantId, String status
);
```

### 17.2. DTO projection với record

```java
public record OrderCard(
    String status,
    BigDecimal amount
) {}
```

Repository có thể trả:

```java
List<OrderCard> findByTenantIdAndStatus(
    String tenantId, String status
);
```

Constructor/property mapping, version và field selection phải tương thích. Với class DTO có nhiều constructors, dùng `@PersistenceCreator` đúng chỗ.

### 17.3. Dynamic projection

```java
<T> List<T> findByTenantId(
    String tenantId, Class<T> type
);
```

Sử dụng:

```java
List<Order> entities =
    repository.findByTenantId("A", Order.class);

List<OrderSummary> summaries =
    repository.findByTenantId("A", OrderSummary.class);
```

**Điều kiện:** Spring Data nhận ra tham số `Class<T>` là dynamic projection parameter. Khi đã được nhận diện, tham số này không phải một filter argument có thể tham chiếu tùy ý trong `@Query`.

### 17.4. Open projections và performance

Projection dùng `@Value` với SpEL để tính field mới được gọi là **open projection**. Do có thể phụ thuộc nhiều properties, Spring Data không tối ưu field selection như closed projection trong mọi trường hợp.

Không tuyên bố mọi interface projection luôn ít network hơn; hãy đọc output thực tế/profiler.

### 17.5. API safety

Trong REST API, nên trả:

```java
public record OrderResponse(
    String id,
    String status,
    BigDecimal amount
) {}
```

Thay vì serialize `Order` nguyên entity chứa internal fields, token hoặc dữ liệu cần kiểm soát. Service chuyển đổi projection/domain sang response DTO theo authorization rules.

---

## 18. @Query sort: sắp xếp tĩnh và tùy biến

### 18.1. Sort mặc định ở annotation

```java
@Query(
    value = "{ 'tenantId': ?0, 'status': ?1 }",
    sort = "{ 'createdAt': -1, '_id': -1 }"
)
List<Order> findSortedPaidOrders(
    String tenantId, String status
);
```

Thứ tự ở JSON sort cố định theo các fields.

### 18.2. Sort parameter có thể ghi đè

```java
@Query(
    value = "{ 'tenantId': ?0 }",
    sort = "{ 'createdAt': -1 }"
)
List<Order> findWithDefaultSort(
    String tenantId, Sort sort
);
```

Theo Spring Data docs, `Sort.unsorted()` giữ sort mặc định từ `@Query`; `Sort.by(ASC,"createdAt")` ghi đè direction của cùng property; sort property mới có thể bổ sung vào sort mặc định.

Nếu API cho người dùng sort, **allow-list fields** và bảo đảm pagination có tie-breaker ổn định.

### 18.3. Pageable với @Query

```java
@Query(
    value = "{ 'tenantId': ?0, 'status': ?1 }",
    fields = "{ 'orderNumber': 1, 'status': 1, 'amount': 1 }"
)
Page<Order> pageByTenantAndStatus(
    String tenantId,
    String status,
    Pageable pageable
);
```

Pageable áp skip/limit/sort. `Page` có thể thêm count query để có total elements. Nếu không cần total, dùng `Slice`.

---

## 19. @Query count và exists

Ngoài các tên derived `countBy...` và `existsBy...`, `@Query` có các attributes dành cho count/exists.

### 19.1. Derived count

```java
long countByTenantIdAndStatus(
    String tenantId, String status
);
```

Với fixture, tenant A và PAID có **3** records (O-101, O-103, O-107).

### 19.2. Annotated count

```java
@Query(
    value = "{ 'tenantId': ?0, 'status': ?1 }",
    count = true
)
long countMatchingOrders(
    String tenantId, String status
);
```

`count = true` chạy truy vấn như một **count projection**, không phải load toàn bộ `List<Order>` rồi gọi `size()` ở Java.

### 19.3. Derived exists

```java
boolean existsByTenantIdAndOrderNumber(
    String tenantId, String orderNumber
);
```

Trước khi tạo order mới, exists check có thể giúp trả lỗi đẹp nhưng **không thay unique index**. Hai concurrent requests đều có thể thấy `false` rồi cùng insert; unique index mới là cơ chế chống duplicate mạnh ở database.

### 19.4. Annotated exists

```java
@Query(
    value = "{ 'tenantId': ?0, 'orderNumber': ?1 }",
    exists = true
)
boolean orderNumberExists(
    String tenantId, String orderNumber
);
```

Dùng khi filter không tiện suy diễn hoặc muốn giữ JSON query rõ ràng.

---

## 20. Xóa với derived methods và @Query(delete = true)

### 20.1. Derived delete

```java
long deleteByTenantIdAndStatus(
    String tenantId,
    String status
);
```

Theo MongoDB repository docs, method trả numeric count có thể xóa matching documents và trả **số lượng bị xóa**.

### 20.2. Return List có semantics khác

```java
List<Order> deleteByTenantIdAndStatus(
    String tenantId,
    String status
);
```

Với return `List<Order>`, Spring Data MongoDB có semantics **truy xuất entities matching trước khi xóa và trả entities đã bị xóa**. Điều này có thể tốn memory và có những tương tác concurrency khác với delete count.

**Không khai báo hai methods trùng cùng tên/tham số nhưng khác return type** trong một interface Java; ví dụ trên minh họa những lựa chọn độc lập.

### 20.3. Annotated delete

```java
@Query(
    value = "{ 'tenantId': ?0, 'active': false }",
    delete = true
)
long deleteInactiveForTenant(String tenantId);
```

**Chỉ chạy thử trên môi trường lab.** Điều kiện tenant phải luôn được áp dụng đúng; API production phải xác thực quyền xóa, audit và cân nhắc soft delete.

### 20.4. Delete và transaction/audit

Repository deletion không tự thực hiện toàn bộ business workflow:

- Phát audit event.
- Xóa references ở collections khác.
- Invalidate caches.
- Thực hiện transaction đa document.
- Kiểm tra legal retention.
- Phân quyền theo user/tenant.
- Cập nhật counters ở hệ thống ngoài.

Những việc này thuộc service/domain transaction logic hoặc outbox pattern, không tự có chỉ từ method `deleteBy...`.

---

## 21. @Update và cập nhật theo query

**Bên cạnh `@Query`**, Spring Data MongoDB còn có annotation `@Update` cho các repository update methods. Đây là chủ đề liên quan để tránh nhầm rằng `@Query` tự cập nhật dữ liệu.

### 21.1. @Query là filter, @Update là action

```java
import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.mongodb.repository.Update;

@Query("{ 'tenantId': ?0, '_id': ?1 }")
@Update("{ '$set': { 'status': ?2 } }")
long updateStatusForTenant(
    String tenantId,
    String orderId,
    String newStatus
);
```

Theo Spring Data docs, repository update methods có thể trả `void` hoặc numeric type để cho biết số documents được sửa. `@Update` định nghĩa update document, còn `@Query` cung cấp filter.

### 21.2. Derived update method naming

```java
@Update("{ '$inc': { 'visits': 1 } }")
long findAndIncrementVisitsByLastname(String lastname);
```

Mẫu trên từ repository update semantics: method có prefix derived finder như `find...By` và action được khai báo bằng `@Update`.

Từ `updateAllByLastname` **không được parser hiểu thành derived query theo cách này** trừ khi được kết hợp `@Query` phù hợp. Cần đối chiếu version.

### 21.3. Không nhầm update với save

`repository.save(entity)` có thể replace/merge theo semantics mapping và optimistic locking. `@Update` dùng các toán tử MongoDB như `$set`, `$inc` để sửa targeted fields. Với concurrency cao, targeted update có thể tránh lost updates nhưng vẫn cần idempotency/atomicity business rule.

### 21.4. Lifecycle events và @Version

Tài liệu Spring Data MongoDB nêu repository update methods **không phát persistence/mapping lifecycle events** như một số đường lưu entity. Nếu dự án dựa auditing callbacks hoặc `@Version`, hãy xác minh semantics của update trước khi đổi từ `save` sang repository update.

---

## 22. @Query với nested arrays và $elemMatch

Nếu một document chứa mảng các subdocuments:

```javascript
{
  _id: "O-200",
  tenantId: "A",
  lineItems: [
    { sku: "PEN", quantity: 2 },
    { sku: "BOOK", quantity: 5 }
  ]
}
```

Nhu cầu:

> Tìm đơn có **ít nhất một line item** vừa sku=BOOK vừa quantity≥3.

Nếu chỉ dùng hai điều kiện dot notation độc lập, chúng có thể match **hai phần tử khác nhau** trong array.

Dùng `$elemMatch`:

```java
@Query("""
    {
      'tenantId': ?0,
      'lineItems': {
        '$elemMatch': {
          'sku': ?1,
          'quantity': { '$gte': ?2 }
        }
      }
    }
    """)
List<Order> withItemAtLeast(
    String tenantId, String sku, int minQuantity
);
```

**Điều kiện:** Entity `Order` phải có property `lineItems` đúng mapping, ví dụ `List<LineItem>`. Fixture ban đầu chưa có field này; hãy thêm dữ liệu lab phù hợp trước khi chạy query.

### 22.1. Nếu cần nhiều aggregation stages

`@Query` là JSON find query; nó **không phải** nơi đặt một pipeline gồm `$match`, `$group`, `$lookup`, `$unwind`.

Dùng:

- `@Aggregation` trên repository method nếu pipeline phù hợp và tương đối cố định.
- `MongoTemplate.aggregate` cho pipeline phức tạp/dynamic.
- Custom repository implementation khi business query đòi nhiều lựa chọn, reusable code hoặc dynamic criteria.

---

## 23. @Query và @Meta, hint, collation

### 23.1. @Meta giới hạn thời gian thực thi

```java
import org.springframework.data.mongodb.repository.Meta;

@Meta(maxExecutionTimeMs = 3000)
@Query("{ 'tenantId': ?0, 'status': ?1 }")
List<Order> guardedQuery(String tenantId, String status);
```

`@Meta` cung cấp một số query options như max execution time, comments và allowDiskUse trong ngữ cảnh được hỗ trợ. `maxExecutionTimeMs` là giới hạn thực thi theo MongoDB semantics; không thay client socket timeout hoặc overall API deadline.

### 23.2. Hint index

```java
@Query(
    value = "{ 'tenantId': ?0, 'status': ?1 }",
    hint = "ix_tenant_status_createdAt"
)
List<Order> withSpecificIndex(
    String tenantId, String status
);
```

Hoặc dùng annotation `@Hint` trên method theo API được hỗ trợ.

**Đừng hint theo thói quen.** Nếu index bị đổi tên/xóa hoặc không phù hợp selectivity, hint có thể gây lỗi/hiệu năng tệ hơn. Thông thường để query planner chọn index là điểm xuất phát tốt.

### 23.3. Collation

```java
@Query(
    value = "{ 'shipping.city': ?0 }",
    collation = "en_US"
)
List<Order> byCityWithCollation(String city);
```

Collation quyết định cách so sánh/sắp xếp chuỗi theo locale/options. Với tiếng Việt, hãy chọn locale phù hợp với yêu cầu nghiệp vụ và đối chiếu collation/index support; `en_US` chỉ là ví dụ API, không phải đề xuất cho mọi tên tiếng Việt.

**Đặc biệt:** Query sử dụng collation khác collation của index có thể không tận dụng index cho string comparison/sort như mong đợi.

### 23.4. Read preference

Các repositories và methods có thể khai báo read preference bằng `@ReadPreference` hoặc `@Query(readPreference = ...)` khi framework/version hỗ trợ.

Nhưng đọc từ secondary có thể trả dữ liệu **chưa mới nhất** do replication lag. Không đổi `readPreference` sang secondary chỉ để giảm tải primary mà bỏ qua read-your-writes/consistency requirements.

---

## 24. Regex, IgnoreCase và input safety

### 24.1. Derived IgnoreCase

```java
List<Order> findByOrderNumberIgnoreCase(String orderNumber);
```

Spring Data MongoDB có thể triển khai ignore-case qua regex có option `i`. Điều này tiện nhưng không đồng nghĩa truy vấn sẽ dùng index hiệu quả như exact equality.

### 24.2. StartsWith, Contains và index

```java
List<Order> findByOrderNumberStartingWith(String prefix);

List<Order> findByOrderNumberContaining(String fragment);
```

- Regex prefix có thể tận dụng index trong những điều kiện phù hợp.
- Regex contains/mid-string thường khó sử dụng index B-tree hiệu quả.
- Case-insensitive regex và collation không phải lúc nào kết hợp index như bạn dự đoán.
- Với full-text use cases, xem MongoDB text search/Atlas Search thay vì nhiều regex chậm.

### 24.3. @Query với Regex

```java
@Query("{ 'orderNumber': { '$regex': ?0, '$options': 'i' } }")
List<Order> regexOrderNumber(String pattern);
```

**Không** cho phép client tự gửi regex phức tạp không giới hạn. Backtracking patterns và unbounded regex có thể gây resource exhaustion. Hãy áp input length/rate limits, validate allowed pattern syntax, chọn literal search khi có thể và có timeouts.

Nếu chỉ muốn tìm **literal substring**, cần escape regex metacharacters đúng cách trong Java trước khi truyền vào pattern, ví dụ `Pattern.quote(userInput)` theo semantics dự án.

### 24.4. @Query string binding không đồng nghĩa SpEL an toàn

`?0` được escape như tham số, trong khi `?#{...}` là expression layer mạnh hơn. Không lắp nối operator strings hoặc SpEL fragments từ dữ liệu người dùng.

---

## 25. @Aggregation khác @Query như thế nào?

`@Query` phù hợp find filter và field restriction/sort. Khi cần pipeline:

```javascript
[
  { $match: { tenantId: "A" } },
  { $group: { _id: "$status", total: { $sum: 1 } } },
  { $sort: { total: -1 } }
]
```

dùng `@Aggregation`:

```java
import org.springframework.data.mongodb.repository.Aggregation;

public interface OrderRepository
        extends MongoRepository<Order, String> {

    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0 } }",
        "{ '$group': { '_id': '$status', 'total': { '$sum': 1 } } }",
        "{ '$sort': { 'total': -1 } }"
    })
    List<StatusCount> countByStatusForTenant(String tenantId);
}

public interface StatusCount {
    String getId();
    long getTotal();
}
```

Đây là **ví dụ minh họa projection/mapping**; tùy version, mapping của `_id` trong aggregation output sang interface getter có thể cần điều chỉnh DTO/projection. Cần integration test.

### 25.1. Phân trang aggregation khác find query

Theo Spring Data MongoDB docs, repository methods có `@Aggregation` **không hỗ trợ return `Page` trực tiếp** như find query trong các phiên bản được mô tả; có thể dùng `Pageable` và trả `Slice` khi phù hợp. Muốn total count, cần thiết kế count riêng hoặc `$facet` tùy use case.

### 25.2. Khi nào dùng MongoTemplate?

Dùng `MongoTemplate` hoặc custom repository khi:

- Query filters được xây dựng động với nhiều điều kiện optional.
- Có nested `$and`/`$or` phức tạp.
- Có updates/aggregation nhiều stages.
- Cần cursor/hints/session controls rất cụ thể.
- Tái sử dụng Criteria helpers across queries.
- Repository method name trở nên khó đọc/khó bảo trì.

`@Query` không phải giải pháp cho mọi thao tác MongoDB.

---

## 26. Query by Example (QBE): một lựa chọn khác

Ngoài derived query và `@Query`, `MongoRepository` hỗ trợ `QueryByExampleExecutor`:

```java
Order probe = new Order();
// Thiết lập các field probe qua setters phù hợp.
// Ví dụ: probe.setStatus("PAID");

Example<Order> example = Example.of(probe);
List<Order> matches = repository.findAll(example);
```

QBE hữu ích cho những filter equality đơn giản từ “probe” entity. Tuy nhiên:

- `null` values thường bị bỏ qua theo default.
- Primitive booleans/ints có thể được đưa vào query vì luôn có giá trị mặc định.
- Không hỗ trợ linh hoạt nested grouped OR như `@Query`/Criteria.
- String matching theo `ExampleMatcher` có giới hạn của datastore.
- Cần cẩn thận với tenant scoping.

Không nên chọn QBE chỉ vì nó giảm số methods nếu business query có nhiều điều kiện OR/range.

---

## 27. Query correctness: đặc biệt với tenant, null và giới hạn số bản ghi

### 27.1. Tenant check trước database query

```java
public List<Order> paidOrders(String requestedTenant) {
    String allowedTenant = principalTenantId();

    if (!allowedTenant.equals(requestedTenant)) {
        throw new AccessDeniedException("Tenant mismatch");
    }

    return repository.findByTenantIdAndStatus(
        allowedTenant, "PAID"
    );
}
```

`principalTenantId()` là hàm minh họa lấy tenant từ authenticated principal. Việc nhận tenant từ header/client query parameter rồi đưa trực tiếp vào repository **không đủ** cho isolation.

### 27.2. Missing và null

MongoDB treats `{field: null}` khác các ngôn ngữ SQL null semantics. Nếu phải phân biệt missing vs explicit null, dùng `$exists`/`$type` và test.

### 27.3. Tên method không giới hạn resource

`List<Order> findByTenantId("A")` có thể trả hàng triệu documents. Hãy dùng Page/Slice, limit hoặc streaming cursor có lifecycle đúng.

### 27.4. Sort ổn định

Sort theo `createdAt` không unique dẫn đến page duplicates/missing khi dataset thay đổi. Dùng `createdAt` kết hợp `id` nếu cần keyset paging.

### 27.5. Unique business keys

`existsByTenantIdAndOrderNumber` là precheck, **không thay** unique index và xử lý duplicate key exceptions trong race conditions.

---

## 28. Hiệu năng: @Query và derived query có khác nhau không?

Hai phương thức:

```java
List<Order> findByTenantIdAndStatus(
    String tenantId, String status
);
```

và:

```java
@Query("{ 'tenantId': ?0, 'status': ?1 }")
List<Order> withQueryAnnotation(
    String tenantId, String status
);
```

thường tạo filter MongoDB tương đương. Nếu cùng projection/sort/options, MongoDB query planner có thể chọn cùng plan.

**Đừng cho rằng `@Query` nhanh hơn chỉ vì viết JSON thủ công.** Performance chủ yếu phụ thuộc:

- Index được dùng.
- Query selectivity.
- Sort và pagination.
- Document size và projection.
- Number of results.
- Cache/working set.
- Network latency.
- Read preference/consistency.
- Database/server resources.

### 28.1. Index gợi ý cho lab

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "ix_tenant_status_createdAt" }
);
```

Có thể hỗ trợ:

```javascript
db.orders.find({
  tenantId: "A",
  status: "PAID"
}).sort({ createdAt: -1 });
```

Index này **không** tối ưu mọi query theo `amount`/`shipping.city`/regex. Chọn indexes theo workload tổng thể, cardinality và write overhead.

### 28.2. Explain qua mongosh

```javascript
db.orders.find({
  tenantId: "A",
  status: "PAID"
}).sort({ createdAt: -1 }).explain("executionStats");
```

Xem:

- `winningPlan`, `IXSCAN` hay `COLLSCAN`.
- `totalKeysExamined`.
- `totalDocsExamined`.
- `nReturned`.
- `executionTimeMillis`.

Một `IXSCAN` quét 100.000 keys để trả 5 rows có thể vẫn kém hiệu quả.

### 28.3. Page count có thể tốn kém

Endpoint trả `Page<Order>` cần biết total elements, có thể tạo count query. Với high traffic và filter kém index, count đôi khi đắt hơn query lấy 20 docs.

Nếu UX chỉ cần nút “Load more”, dùng `Slice<Order>` hoặc keyset/scrolling hợp lý.

### 28.4. Reactive không tự nhanh hơn

Spring Data có `ReactiveMongoRepository` trả `Flux`/`Mono`. Nó khác Sync `MongoRepository` về execution model, **không làm MongoDB query thiếu index chạy nhanh hơn**. Chọn theo Spring WebFlux vs MVC và tổng concurrency architecture.

---

## 29. @Query, Spring Data mapping và conversion pitfalls

### 29.1. ID string và ObjectId

Với entity:

```java
@Id
private String id;
```

MongoDB `_id` thực tế có thể lưu dạng String hoặc ObjectId tùy nguồn dữ liệu/conversion. Spring Data có quy tắc chuyển đổi `String` sang ObjectId nếu giá trị hợp lệ, trong những mapping configurations phù hợp.

Fixture ở đây dùng `_id` dạng String như `"O-101"` nên tránh mơ hồ. Khi chuyển hệ thống, kiểm tra kiểu BSON của `_id` bằng `$type`.

### 29.2. Date/time zone

Sử dụng `java.util.Date` cho lab để giảm khác biệt converter. Nếu domain dùng `Instant`, `LocalDateTime`, `OffsetDateTime`, kiểm tra Java Time codecs/converters và timezone policy.

Không dùng local timezone không rõ ràng để tính query range:

```javascript
{ createdAt: { $gte: ISODate("2026-11-01T00:00:00Z") } }
```

MongoDB BSON Date lưu timestamp UTC; Date/Instant mappings cần tuân theo business timezone boundaries.

### 29.3. Decimal128

`@Field(targetType = FieldType.DECIMAL128)` giúp map `BigDecimal` sang BSON Decimal128. Nếu một collection đã lưu tiền dưới `double`/`string` ở các documents cũ, cùng một range query có thể có kết quả bất ngờ theo BSON type comparison. Dọn dữ liệu/validation trước khi chuyển.

### 29.4. Projection không thay access control

`fields = "{'amount':1}"` không được coi là authorization policy. Người dùng có thể gọi một repository method khác trả entity đầy đủ. Service/API security phải kiểm soát ai được xem field nào.

### 29.5. Entity save từ partial projection

Đọc một entity thiếu fields rồi `save` có thể làm mất những fields không được load. Dùng read-only DTO/projection cho list endpoints và load aggregate đầy đủ khi thực sự cập nhật hoặc dùng targeted update.

---

## 30. Integration test cho repository query methods

Không dùng H2/JPA SQL tests để chứng minh MongoDB query derivation đúng; cần MongoDB thật hoặc test container tương thích.

### 30.1. @DataMongoTest

Spring Boot hỗ trợ `@DataMongoTest` để tập trung test MongoDB mapping/repository thay vì khởi động toàn bộ web app.

Ví dụ logic test (giả sử test đã có database kết nối và mỗi test dùng dataset riêng):

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;

@DataMongoTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;

    @Test
    void findsTenantPaidOrders() {
        var result =
            repository.findByTenantIdAndStatus("A", "PAID");

        assertThat(result)
            .allMatch(order ->
                "A".equals(order.getTenantId())
                && "PAID".equals(order.getStatus())
            );
    }
}
```

**Quan trọng:** Đoạn test cần dữ liệu fixture/seed trước khi assert số documents cụ thể. `@DataMongoTest` không tự tạo dữ liệu MongoDB của bài.

### 30.2. Testcontainers và MongoDB thật

Một chiến lược integration test:

1. Tạo MongoDB test container/ephemeral deployment theo version được hỗ trợ.
2. Spring Boot trỏ `spring.data.mongodb.uri` tới container.
3. Seed data với MongoTemplate hoặc `mongosh`.
4. Tạo indexes theo migration/lifecycle.
5. Test derived methods, `@Query`, pagination, count, exists, delete.
6. Kiểm chứng typed fields (Date, Decimal128, ObjectId/String).
7. Test tenant isolation, boundaries và concurrent uniqueness.
8. Đảm bảo cleanup/container shutdown sau test.

Không cần test mọi method bằng cách mock toàn bộ repository, vì mock không thực thi parser/query mappings thực.

### 30.3. Các test cases bắt buộc

| Trường hợp | Kỳ vọng |
| --- | --- |
| `findByTenantIdAndStatus("A","PAID")` | Chỉ trả các orders của A đã PAID |
| `countByTenantIdAndStatus("A","PAID")` | 3 trên fixture |
| `existsByTenantIdAndOrderNumber("A","A-001")` | True |
| `findByShipping_City("Hà Nội")` | Các orders có shipping.city đúng |
| `findTop2...OrderByCreatedAtDesc` | Đúng 2 results mới nhất |
| `@Query` OR có tenant bên ngoài | Không lộ tenant B |
| `@Query(fields=...)` | Chỉ fields được yêu cầu |
| `Pageable` sort theo createdAt và id | Thứ tự ổn định |
| Đầu range số tiền | Inclusive/exclusive đúng theo query |
| Empty result | `Optional.empty()`/list rỗng |
| Input chứa special characters | Binding không đổi filter thành operator |
| Unique concurrent inserts | Một duplicate phải bị từ chối |
| Đọc entity partial rồi save | Có policy ngăn thao tác nguy hiểm |
| `@Query(delete=true)` | Chỉ xóa đúng tenant, có audit/approval |

### 30.4. Kiểm tra generated query

Tùy framework/driver version, có thể dùng Spring Data MongoDB logging và MongoDB Driver `CommandListener` để quan sát query shape. **Không log toàn bộ query literals nhạy cảm**. Khi tuning, nhìn `explain("executionStats")` trên MongoDB với query tương đương và dataset đại diện.

---

## 31. Khi nào không nên cố nhét logic vào một tên method?

Có những tên derived query dài như:

```java
findTop25ByTenantIdAndActiveTrueAndStatusInAndAmountGreaterThanEqualAndCreatedAtBeforeOrderByCreatedAtDesc(...)
```

Tên này khó bảo trì nếu:

- Có 5–10 optional filters.
- Cần nhóm OR phức tạp.
- Có regex + projection + dynamic sort.
- Business logic lặp giữa nhiều endpoints.
- Có toán tử MongoDB mới không được derivation hỗ trợ.
- Cần query planner hints/aggregation.

### 31.1. Chiến lược chọn công cụ

| Độ phức tạp | Cách phù hợp |
| --- | --- |
| CRUD và filter 1–3 fields | MongoRepository + derived methods |
| Filter cố định có OR/grouping/nested operators | `@Query` |
| Chỉ một vài fields ở list endpoint | Projection interface/DTO, `@Query(fields)` |
| Filter tùy chọn động từ UI | `MongoTemplate` + `Criteria` / custom repository |
| Grouping, join, facets | `@Aggregation` hoặc MongoTemplate aggregation |
| Bulk updates, complex write semantics | MongoTemplate/bulk operations hoặc `@Update` khi phù hợp |
| Multi-tenant security | Service/authorization + tenant-scoped repositories |
| Search features chuyên biệt | API/index chuyên biệt của MongoDB/Spring Data |
| Query-based data export khối lượng lớn | Stream/scroll + resource management |

**Kết luận:** Repository là nơi mô tả truy cập dữ liệu. Đừng biến interface thành “mini-programming language” với method name dài hàng trăm ký tự.

---

## 32. Các lỗi thường gặp

| Lỗi | Vì sao | Cách xử lý |
| --- | --- | --- |
| Repository method báo không tìm thấy property | Đặt tên không khớp Java entity | Sửa tên, kiểm tra nested path |
| `findByShippingCity` chọn nhầm field | Camel-case path ambiguity | Dùng `Shipping_City` |
| Dùng BSON field name trong derived method | Parser đọc Java properties | Đặt theo entity, để mapping làm việc |
| `findById` đọc field không mong muốn | Reserved ID method | Phân biệt identifier và property tên id |
| `findFirst...` không có sort | Không xác định “first” | Dùng `OrderBy` hoặc `Sort` |
| `findAll()` trên collection lớn | Materialize quá nhiều docs | Pagination/stream/limit |
| `Page` endpoint chậm | Total count query đắt | Xem `Slice`/keyset/index |
| `@Query` đặt SQL string | MongoDB không dùng SQL syntax | Dùng BSON query JSON |
| Sai `?0`/`?1` | Index từ 0 | Đối chiếu method params |
| Ghép chuỗi JSON từ input | Injection/malformed query | Parameter binding, validation |
| SpEL động từ user input | Expression injection/rủi ro logic | Sanitize, hạn chế expression |
| `fields` thiếu dữ liệu rồi save | Entity partial được ghi lại | Dùng DTO/read-only projection |
| `@Query(fields)` trả data nhạy cảm | Projection không phải auth | API authorization/DTO |
| Regex contains quá chậm | Không dùng index phù hợp | Search/index/queries khác |
| `IgnoreCase` không dùng index như mong muốn | Regex collation/index semantics | Explain và index strategy |
| `@CompoundIndex` khai báo nhưng DB không có index | Auto index creation tắt mặc định | Migrations/provisioning |
| Sort không có tie-breaker | Trang có trùng/mất records | Sort thêm unique key |
| `countBy...` dùng để kiểm tra uniqueness | Race condition | Unique index |
| Delete query thiếu tenant | Xóa chéo tenants | Scoped filter + auth + test |
| Return Optional cho query không unique | Nhiều matches gây exception | Index/`First`/`Top` |
| Quên xử lý null/missing | MongoDB null semantics khác SQL | `$exists`/`$type` khi cần |
| Gọi `save` với detached/partial entity | Ghi đè fields ngoài dự kiến | Optimistic lock/targeted update |
| Dùng `@Query` cho aggregation pipeline | Find JSON khác pipeline | `@Aggregation`/MongoTemplate |
| Dùng `Pageable` và `Sort` trùng trong signature | Special parameters conflicting | Chọn một cơ chế |
| So performance derived với @Query bằng 1 request | Cache/data khác nhau | Benchmark cùng shape/index |
| Dùng `@DataMongoTest` nhưng không seed fixture | Test không kiểm tra đúng dữ liệu | Testcontainers + seeding |
| Thay Spring Data major mà không đối chiếu | API/mapping/driver changes | BOM compatibility + integration tests |
| Log nguyên JSON query production | Lộ PII/tenant data | Redaction/tracing metadata |

---

## 33. Bài tập thực hành

### Bài 1 — CRUD

Tạo interface `OrderRepository extends MongoRepository<Order,String>`, gọi `findById`, `existsById`, `count`. Khi không tìm thấy ID, `findById` trả gì?

**Đáp án:** `Optional.empty()`.

### Bài 2 — Derived AND

Viết method lấy đơn của tenant A và status PAID.

**Đáp án:**

```java
List<Order> findByTenantIdAndStatus(
    String tenantId, String status);
```

### Bài 3 — Count fixture

Với 8 documents lab, `countByTenantIdAndStatus("A","PAID")` bằng bao nhiêu?

**Đáp án:** 3.

### Bài 4 — Exists

Viết method kiểm tra tenant A đã có order number A-001 chưa. Vì sao chỉ kiểm tra `exists` không đủ chống duplicate concurrency?

### Bài 5 — Range

Viết method lấy đơn có `amount >= min` trong tenant A. Phân biệt `GreaterThan` và `GreaterThanEqual`.

### Bài 6 — Between

`findByAmountBetween(min,max)` có phải luôn inclusive không?

**Đáp án:** Không. Đọc mapping `Between` theo Spring Data MongoDB version hoặc dùng `GreaterThanEqualAndLessThanEqual`.

### Bài 7 — In

Viết method lấy các orders của tenant A với status thuộc NEW/PAID.

### Bài 8 — OR security

Phân tích lỗi của `findByTenantIdAndStatusOrActive` trong ứng dụng đa tenant. Viết `@Query` với tenant filter áp cho toàn bộ OR.

### Bài 9 — Nested

`shipping.city` trong MongoDB sẽ trở thành method name nào? Vì sao dấu underscore có thể cần?

**Đáp án:** `findByShipping_City`; giúp phân tách property path.

### Bài 10 — @Field

Entity có `@Field("shipping_city")` trên Java property `shippingCity`. Derived method dùng tên nào?

**Đáp án:** Java property `ShippingCity` trong tên method.

### Bài 11 — Null

So `findByStatusIsNull()` và truy vấn `{status:{$exists:false}}`.

### Bài 12 — Top

Viết method lấy 3 orders PAID mới nhất của tenant A và có tie-breaker ID.

### Bài 13 — Pageable

Tạo PageRequest trang thứ hai, page size 20, sort `createdAt DESC, id DESC`. Spring Data đánh số trang từ mấy?

**Đáp án:** Từ 0; trang thứ hai index 1.

### Bài 14 — Page hay Slice

Một mobile app chỉ cần nút “Load more”. Tại sao `Slice` có thể tốt hơn `Page`?

### Bài 15 — Offset sâu

Tại sao `PageRequest.of(100000,20)` có thể chậm và bị lệch kết quả khi dữ liệu thay đổi? Đề xuất keyset strategy.

### Bài 16 — @Query JSON

Viết `@Query` lấy orders với `amount >= 100` và `status=PAID` của tenant A, dùng `?0`, `?1`, `?2`.

### Bài 17 — Zero-based binding

Đối với `@Query("{ 'tenantId': ?0, 'status': ?1 }")`, `?1` lấy argument thứ mấy?

**Đáp án:** Thứ hai.

### Bài 18 — JSON vs SQL

Vì sao `@Query("SELECT * FROM orders")` không phù hợp với MongoRepository?

### Bài 19 — @Query(fields)

Dùng `fields` chỉ trả `status` và `amount`. Tại sao không nên gọi `save` trên entity được load thiếu fields?

### Bài 20 — Projection

Tạo interface `OrderSummary` có `getId`, `getStatus`, `getAmount`; trả `List<OrderSummary>` từ repository.

### Bài 21 — Dynamic projection

Viết `<T> List<T> findByTenantId(String tenantId, Class<T> type)` và dùng cho `Order` cùng `OrderSummary`.

### Bài 22 — @Query sort

Viết `@Query(sort="{ 'createdAt': -1 }")`. Khi method có dynamic Sort theo cùng property ascending, điều gì xảy ra?

**Đáp án:** Dynamic sort có thể override mặc định của annotation theo tài liệu.

### Bài 23 — Count projection

Phân biệt `@Query(count=true) long count...` với `repository.find...().size()`.

### Bài 24 — Exists projection

Phân biệt `@Query(exists=true)` và `@Query(count=true)`.

### Bài 25 — Delete safety

Viết `@Query(delete=true)` chỉ xóa inactive documents của đúng tenant; đề xuất audit/authorization checks.

### Bài 26 — Update

Dùng `@Query` làm filter và `@Update` để đặt `status` của một order theo tenant + ID. Vì sao cần kiểm tra matched/modified count?

### Bài 27 — $elemMatch

Mảng `lineItems` có sku và quantity. Tại sao không dùng hai điều kiện dot notation độc lập nếu cần cùng một item thỏa cả hai?

### Bài 28 — Regex

So `StartingWith`, `Containing` và `Regex`. Trường hợp nào có thể tận dụng B-tree index tốt hơn? Rủi ro regex user input?

### Bài 29 — Index

Truy vấn `findByTenantIdAndStatusOrderByCreatedAtDesc`. Hãy thiết kế compound index phù hợp và so `explain("executionStats")`.

### Bài 30 — @CompoundIndex

Tại sao chỉ đặt `@CompoundIndex` trên entity không đủ bảo đảm index đã tồn tại ở production?

**Đáp án:** Auto index creation tắt mặc định; cần migration/provisioning hoặc cấu hình chủ đích.

### Bài 31 — Null và missing

Nếu business muốn kiểm tra field tồn tại nhưng giá trị null, cần toán tử gì ngoài `{field:null}`?

### Bài 32 — Optional và uniqueness

Khi query theo orderNumber nhưng database có hai documents trùng, `Optional<Order>` có bảo đảm chọn một record ngẫu nhiên không?

**Đáp án:** Không; single-result query có thể ném lỗi nếu nhiều matches. Unique index là giải pháp đúng.

### Bài 33 — Transaction

Một service vừa tạo order vừa tạo audit event ở collection khác. `MongoRepository.save` hai lần có tự thành atomic multi-document transaction không?

**Đáp án:** Không. Cần transaction/session deployment phù hợp nếu business yêu cầu atomicity.

### Bài 34 — Integration test

Viết `@DataMongoTest` với dữ liệu seed; kiểm chứng method derived và `@Query` trả cùng orders. Vì sao mock repository không chứng minh query JSON hợp lệ?

### Bài 35 — Tenant isolation

Thiết kế test đảm bảo một request của tenant A không xem/xóa được O-104 thuộc tenant B, kể cả qua OR, Pageable và delete method.

### Bài 36 — Khi nào dùng MongoTemplate?

Cho một trang tìm kiếm có 12 filters tùy chọn, OR theo nhóm, sort và projection thay đổi. Nên viết method name dài hay dùng Criteria/MongoTemplate? Giải thích.

### Bài 37 — Hiệu năng

Hai methods derived và `@Query` tạo cùng filter/index/sort. Có lý do gì đảm bảo @Query nhanh hơn?

**Đáp án:** Không. Hãy đo execution plan và workload thực.

### Bài 38 — So sánh Page và Slice

Một trang danh sách có 1 triệu orders, UX chỉ hiện “More”. Hãy giải thích chi phí count query và cách tránh.

### Bài 39 — Date/Decimal128

Vì sao mapping `BigDecimal`/`Date` phải nhất quán BSON types? Hãy dùng `$type` để xem dữ liệu lab.

### Bài 40 — Bài tổng hợp

Thiết kế repository cho API:

```text
GET /orders?status=PAID&minAmount=100&page=0&size=20
```

Yêu cầu: tenant lấy từ authenticated principal, limit size, sort ổn định, projection chỉ fields cần, index phù hợp, test multi-tenant và p95 latency. Chọn derived query hay `@Query` và giải thích.

---

## 34. Checklist khi đưa repository vào production

### Correctness và data access

- [ ] `@Document`/`@Id`/`@Field` mapping đã đúng BSON schema.
- [ ] Derived method names khớp Java properties.
- [ ] Nested paths rõ, tránh ambiguity.
- [ ] `@Query` dùng zero-based binding đúng.
- [ ] `@Query` JSON filter và projection được kiểm tra.
- [ ] Null vs missing được xử lý theo yêu cầu nghiệp vụ.
- [ ] `Optional` chỉ áp dụng khi dữ liệu thực sự unique hoặc đã giới hạn đúng.
- [ ] Tenant filter được áp dụng cho mọi branches của OR và mọi deletes.
- [ ] Không dựa vào exists precheck thay unique index.
- [ ] User không thể điều khiển sort/filter operators trái phép.

### Performance

- [ ] Không trả `findAll()` không giới hạn ở public API.
- [ ] Page/Slice được chọn theo UX.
- [ ] Page size có upper bound.
- [ ] Sort ổn định theo khóa unique.
- [ ] Deep pagination có chiến lược keyset/scrolling.
- [ ] Compound indexes phù hợp filter/sort, không tạo index dư.
- [ ] Có `explain`/profiler metrics: docs/keys examined, nReturned.
- [ ] Projection loại dữ liệu lớn không cần thiết.
- [ ] Kiểm tra regex/IgnoreCase tác động index.
- [ ] Theo dõi count query cost của Page.

### Bảo mật và vận hành

- [ ] URI/TLS/credentials theo secrets manager.
- [ ] Repository methods không bypass authorization.
- [ ] Không log query literals chứa PII.
- [ ] Updates/deletes có audit/approval theo business.
- [ ] Không save lại partial entity thiếu fields.
- [ ] Optimistic locking/transaction strategy được kiểm tra.
- [ ] Dependency BOM và Spring Data version tương thích.
- [ ] Testcontainers/integration tests chạy trong CI trên MongoDB thực.
- [ ] Có load tests và rollback plan cho query/index changes.

---

## 35. Tổng kết

**`MongoRepository`** giúp ứng dụng Spring truy cập MongoDB qua interface đơn giản, nhưng cần biết rõ từng tầng:

1. **CRUD repository** hỗ trợ `save`, `insert`, `findById`, `existsById`, `count`, `deleteById`.
2. **Derived query methods** đọc Java property names và các keywords như `And`, `Or`, `GreaterThan`, `In`, `IsNull`, `IgnoreCase`, `OrderBy` và `Top` để sinh filter/sort.
3. **`@Query`** cho phép khai báo MongoDB JSON với tham số `?0`, `?1`, projection `fields`, sort, collation, hint và các flags count/exists/delete.
4. **Derived hay @Query không tự nhanh hơn nhau** nếu MongoDB nhận cùng query plan. Index, selectivity, pagination, projection và server resources quyết định performance.
5. **Page khác Slice**: Page có total count; Slice thích hợp khi chỉ cần biết có trang sau.
6. **Projection giúp giảm dữ liệu cần tải**, nhưng không là cơ chế phân quyền và không nên save entity partial.
7. **Multi-tenancy, uniqueness và transactions** cần được bảo vệ ở service/DB, không tự có chỉ nhờ repository abstraction.
8. Với query có cấu trúc phức tạp, ưu tiên `@Query`, `MongoTemplate` hoặc `@Aggregation` thay vì tên method quá dài.
9. **Integration test trên MongoDB thật** là cách xác minh query derivation, mapping, indexes và các semantics được mô tả.

Bài học quan trọng nhất: **dùng repository để mã nguồn rõ ràng hơn, nhưng luôn hiểu truy vấn MongoDB thực tế mà framework tạo ra**.

### Tài liệu chính thức

- [Spring Data MongoDB — MongoDB-specific Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html) — derived methods, `@Query`, fields, sort, SpEL, @Meta.
- [Spring Data — Defining Query Methods](https://docs.spring.io/spring-data/mongodb/reference/repositories/query-methods-details.html) — lookup strategies, property traversal, reserved methods, paging/sorting.
- [Spring Data — Repository Query Keywords](https://docs.spring.io/spring-data/mongodb/reference/repositories/query-keywords-reference.html) — supported prefixes và predicate modifiers.
- [Spring Data MongoDB — MongoRepository API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/repository/MongoRepository.html) — methods và inherited interfaces.
- [Spring Data MongoDB — @Query Annotation](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/repository/Query.html) — count/exists/delete/fields/sort/collation/hint.
- [Spring Data MongoDB — Modifying Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/modifying-methods.html) — `@Update` và derived deletions.
- [Spring Data — Projections](https://docs.spring.io/spring-data/mongodb/reference/repositories/projections.html) — closed/open, DTO và dynamic projections.
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html) — `@Document`, `@Id`, `@Field`, indexes.
- [Spring Data MongoDB — Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html) — auto-index defaults và management.
- [Spring Data MongoDB — Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html) — `MongoTemplate`/`Criteria`.
- [Spring Data MongoDB — Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html) — pipeline và aggregation alternatives.
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — sessions, transaction manager.
- [Spring Boot — Data MongoDB](https://docs.spring.io/spring-boot/reference/data/nosql.html) — Boot MongoDB integration.
- [Spring Boot — Auto-configured Data MongoDB Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html) — `@DataMongoTest`, testing support.
- [MongoDB — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — `IXSCAN`/`COLLSCAN` và execution stats.
