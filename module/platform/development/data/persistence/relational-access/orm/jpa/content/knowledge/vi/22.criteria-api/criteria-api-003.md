# Truy cập thuộc tính bằng Path và mô hình siêu dữ liệu có kiểu trong Criteria API

Trong **Jakarta Persistence (JPA)**, JPQL cho phép viết truy vấn theo entity và thuộc tính Java bằng chuỗi ký tự. Cách viết đó dễ đọc nhưng có một nhược điểm: khi đổi tên thuộc tính, trình biên dịch Java thường **không phát hiện lỗi trong chuỗi JPQL**. **Criteria API** giải quyết một phần vấn đề bằng cách biểu diễn truy vấn dưới dạng **cây đối tượng Java**. Thành phần trung tâm để đi từ entity đến thuộc tính là **`Path<T>`**.

Giả sử entity `Customer` có thuộc tính `email`. Với Criteria API, ta có thể viết:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Customer> cq = cb.createQuery(Customer.class);
Root<Customer> customer = cq.from(Customer.class);

Path<String> emailPath = customer.get("email");

cq.select(customer)
  .where(cb.equal(emailPath, "an@example.com"));

List<Customer> result = em.createQuery(cq).getResultList();
```

Ví dụ hoạt động dựa trên thuộc tính persistent có tên `email`, nhưng chuỗi `"email"` vẫn có thể bị gõ sai hoặc không còn hợp lệ khi refactor. Nếu dự án sinh **static metamodel** (`Customer_`), ta viết:

```java
Path<String> emailPath = customer.get(Customer_.email);
```

Lúc này `Customer_.email` đại diện cho thuộc tính persistent kiểu `String` của `Customer`. Trình biên dịch có thể phát hiện nhiều lỗi như tham chiếu đến thuộc tính không tồn tại hoặc dùng metadata thuộc entity không tương thích.

**Mục tiêu bài học:** Hiểu `Path`, `Root`, `Join` và **static metamodel** liên hệ thế nào; biết chọn `get(String)` hay `get(SingularAttribute)`, truy cập thuộc tính đơn/embedded/association, dựng điều kiện có kiểu, tổ chức query động an toàn và nhận diện những giới hạn của khả năng kiểm tra kiểu tại compile time.

> Bài học thuộc chương **Criteria API** trong module *Data Persistence Relational Access ORM JPA*. Mã ví dụ sử dụng `jakarta.persistence.*`, thích hợp với các phiên bản Jakarta Persistence hiện đại; dự án JPA cũ có thể dùng `javax.persistence.*` với API tương ứng.

---

## 1. Criteria API là gì và Path xuất hiện ở đâu?

JPQL mô tả truy vấn bằng chuỗi:

```jpql
select c
from Customer c
where c.email = :email
order by c.displayName
```

Criteria API mô tả cùng ý định bằng các đối tượng:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Customer> cq =
    cb.createQuery(Customer.class);

Root<Customer> customer = cq.from(Customer.class);

cq.select(customer)
  .where(
      cb.equal(
          customer.get(Customer_.email),
          cb.parameter(String.class, "email")
      )
  )
  .orderBy(cb.asc(customer.get(Customer_.displayName)));

List<Customer> customers = em.createQuery(cq)
    .setParameter("email", "an@example.com")
    .getResultList();
```

Các vai trò:

| Thành phần | Vai trò |
|---|---|
| `EntityManager` | Tạo và thực thi Criteria query |
| `CriteriaBuilder` | Factory tạo query, predicate, biểu thức, phép so sánh, hàm |
| `CriteriaQuery<T>` | Cấu trúc của SELECT và kiểu kết quả `T` |
| `Root<X>` | Điểm bắt đầu từ một entity `X` trong FROM |
| `Path<Y>` | Đường dẫn từ Root/Join/Path tới một persistent attribute kiểu `Y` |
| `Expression<T>` | Biểu thức có thể tham gia so sánh, tính toán, select, order |
| `Predicate` | Biểu thức điều kiện boolean do CriteriaBuilder tạo |
| `Join<X,Y>` | Liên kết entity `X` sang entity/phần tử `Y` qua association |
| `SingularAttribute<X,Y>` | Metadata cho thuộc tính đơn của kiểu `X`, mang giá trị `Y` |
| `ListAttribute<X,Y>` | Metadata cho thuộc tính collection kiểu List chứa `Y` |
| `Customer_` | Static metamodel class, thông thường được annotation processor sinh ra |

Mối quan hệ khái niệm:

```text
EntityManager
     |
     v
CriteriaBuilder -----> CriteriaQuery<Customer>
                              |
                              v
                       Root<Customer>
                              |
               +--------------+---------------+
               |              |               |
               v              v               v
      Path<String>      Path<Address>     Join<Customer,Order>
      email             address           orders
                              |               |
                              v               v
                         Path<String>    Path<OrderStatus>
                         city            status
               \              |               /
                \             |              /
                 +---- CriteriaBuilder ------+
                          Predicate
                              |
                              v
                      CriteriaQuery.where
                              |
                              v
                        TypedQuery
                              |
                              v
                        SQL do JPA dịch
```

`Path` trong bài này là **`jakarta.persistence.criteria.Path`**, **không phải** `java.nio.file.Path` dùng để thao tác đường dẫn file.

## 2. Entity mẫu: Customer, Address, SalesOrder và OrderLine

Để thấy các loại đường dẫn khác nhau, ta dùng một mô hình nhỏ:

```text
 Customer                          SalesOrder
 +-----------------------+        +-----------------------+
 | id : Long             | 1    N | id : Long             |
 | email : String        |<-------| customer : Customer   |
 | displayName : String  |        | status : OrderStatus  |
 | address : Address     |        | totalAmount:BigDecimal|
 | orders : List<Order>  |        | createdAt : Instant   |
 +-----------------------+        | lines : List<Line>    |
                                  +-----------------------+
                                            |
                                            | 1:N
                                            v
                                  OrderLine
                                  +-----------------------+
                                  | id : Long             |
                                  | sku : String          |
                                  | quantity : int        |
                                  | order : SalesOrder    |
                                  +-----------------------+

 Address (@Embeddable)
 +-----------------------+
 | city : String         |
 | postalCode : String   |
 +-----------------------+
```

### 2.1. Customer

```java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "crm_customer")
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "email_address", nullable = false, unique = true)
    private String email;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Embedded
    private Address address;

    @OneToMany(mappedBy = "customer")
    private List<SalesOrder> orders = new ArrayList<>();

    protected Customer() {
    }
}
```

### 2.2. Address là kiểu nhúng

```java
package com.example.shop.domain;

import jakarta.persistence.*;

@Embeddable
public class Address {

    @Column(name = "city_name")
    private String city;

    @Column(name = "postal_code")
    private String postalCode;

    protected Address() {
    }
}
```

`Address` không phải entity độc lập, không có `@Id` riêng; nó là **embeddable** được nhúng trong Customer. Trường `Customer.address.city` vẫn là một đường dẫn thuộc tính hợp lệ trong mô hình JPA.

### 2.3. SalesOrder và enum

```java
package com.example.shop.domain;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

```java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity(name = "SalesOrder")
@Table(name = "sales_order")
public class SalesOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_status", nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();

    protected SalesOrder() {
    }
}
```

### 2.4. OrderLine

```java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private SalesOrder order;

    @Column(name = "sku", nullable = false)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {
    }
}
```

Tại đây, tất cả tên mà Criteria API thường truy cập là **thuộc tính Java**:

| Thuộc tính trong Criteria | Tên vật lý của database (ví dụ) |
|---|---|
| `Customer.email` | `crm_customer.email_address` |
| `Customer.displayName` | `crm_customer.display_name` |
| `Customer.address.city` | `crm_customer.city_name` |
| `SalesOrder.status` | `sales_order.order_status` |
| `SalesOrder.totalAmount` | `sales_order.total_amount` |
| `SalesOrder.customer` | Association dùng FK `customer_id` |
| `SalesOrder.lines` | Collection gắn tới bảng `order_line` |

Không viết `customer.get("email_address")` nếu persistent attribute tên `email`, trừ khi entity thực sự có một thuộc tính Java đúng tên `email_address`.

## 3. Bắt đầu từ Root<T>: đường dẫn gốc của một truy vấn

Để tạo truy vấn từ entity `Customer`:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Customer> cq = cb.createQuery(Customer.class);

Root<Customer> customer = cq.from(Customer.class);
cq.select(customer);

List<Customer> result = em.createQuery(cq).getResultList();
```

`Root<Customer>` biểu diễn Customer ở mệnh đề FROM, tương tự:

```jpql
select c from Customer c
```

Về mặt cấu trúc API, `Root<T>` cũng là một dạng đường dẫn có thể được dùng để truy cập thuộc tính. Có thể gọi:

```java
Path<Long> id = customer.get("id");
Path<String> email = customer.get("email");
```

hoặc — khi đã có static metamodel:

```java
Path<Long> id = customer.get(Customer_.id);
Path<String> email = customer.get(Customer_.email);
```

**Không dùng tên bảng trong `cq.from(...)`.** Đối số `Customer.class` đại diện cho entity class; metadata JPA sẽ ánh xạ lớp này tới bảng `crm_customer`.

### 3.1. Root không đồng nghĩa với một entity instance đang được tải

`Root<Customer>` không chứa một Customer thực tế trong heap để gọi `getEmail()`. Nó là **node của cây truy vấn**. Do đó:

```java
// Đây là query path, không phải giá trị email của một Customer:
Path<String> p = customer.get(Customer_.email);
```

Chỉ khi JPA thực thi query và nhận result, ứng dụng mới có giá trị thực tế như `"an@example.com"`.

### 3.2. Root có thể đại diện cho nhiều rows

`Root<Customer>` có thể match hàng nghìn bản ghi. Một `Path<String>` được tạo từ Root diễn tả cách lấy thuộc tính email của mỗi record tương ứng, không phải một String duy nhất có sẵn khi build query.

## 4. Path<T> là gì?

`Path<T>` là giao diện của Criteria API đại diện cho **đường dẫn tới một giá trị có kiểu `T`** bên trong mô hình persistent. Nó cũng có thể dùng ở nơi API chấp nhận `Expression<T>`: chọn thuộc tính, so sánh, sắp xếp, group by hoặc đưa vào phép tính phù hợp.

Ví dụ:

```java
Root<SalesOrder> order = cq.from(SalesOrder.class);

Path<BigDecimal> amount = order.get(SalesOrder_.totalAmount);
```

`amount` không phải một `BigDecimal` thực. Nó là biểu thức “giá trị của thuộc tính `totalAmount` trên SalesOrder ở mỗi row”.

Từ đó dùng CriteriaBuilder:

```java
Predicate expensive =
    cb.greaterThan(amount, new BigDecimal("500000"));

cq.where(expensive);
```

Tương đương ý tưởng JPQL:

```jpql
where o.totalAmount > :threshold
```

### 4.1. Các kiểu liên quan

| Kiểu | Ý nghĩa |
|---|---|
| `Path<T>` | Đường dẫn tới thuộc tính có kiểu `T` |
| `Expression<T>` | Biểu thức trả về giá trị kiểu `T`, có thể do hàm/tính toán tạo |
| `Predicate` | Điều kiện logic dùng trong WHERE, HAVING và JOIN ON |
| `Root<T>` | Điểm xuất phát entity trong FROM |
| `Join<X,Y>` | Đường dẫn và cấu trúc JOIN từ `X` sang `Y` |
| `SingularAttribute<X,Y>` | Metadata typed cho thuộc tính đơn của `X` trả `Y` |
| `PluralAttribute<X,C,E>` | Metadata collection với container `C` và element `E` |

Một `Path<BigDecimal>` có thể được truyền vào nhiều hàm nhận `Expression<? extends Number>` hoặc `Expression<T>` phù hợp.

### 4.2. Expression không phải lúc nào cũng là Path

```java
Path<String> email = customer.get(Customer_.email);

Expression<String> normalizedEmail = cb.lower(email);
```

`normalizedEmail` là biểu thức áp dụng hàm LOWER; nó **không phải** đường dẫn tới một persistent attribute mới có tên `lower`.

Tương tự:

```java
Expression<BigDecimal> increased = cb.sum(
    order.get(SalesOrder_.totalAmount),
    new BigDecimal("10000")
);
```

`increased` là biểu thức toán học của query, không phải một field được lưu tên `increased`.

## 5. Truy cập thuộc tính bằng get(String)

Cách trực tiếp, không cần metamodel:

```java
Root<Customer> customer = cq.from(Customer.class);

Path<String> email = customer.get("email");
```

`"email"` phải là tên **persistent attribute**, không phải tên cột SQL. Path có thể lồng nhau:

```java
Path<String> city = customer
    .get("address")
    .get("city");
```

Nhưng có một điểm yếu: `"address"` và `"city"` chỉ là chuỗi. Nếu field `city` được đổi thành `cityName` trong Java mà chuỗi vẫn giữ nguyên, Java compiler không biết đây là tên thuộc tính đã lỗi thời.

### 5.1. Generic type ở get(String) không chứng minh mapping đúng

`get(String)` là phương thức generic. Bạn có thể viết:

```java
Path<String> email = customer.get("email");
```

hoặc:

```java
Path<String> email = customer.<String>get("email");
```

Cả hai giúp Java chọn một generic type cho kết quả. Tuy nhiên việc gõ `<String>` **không kiểm chứng** rằng metadata JPA của `"email"` thực sự có kiểu String. Nếu bạn vô tình viết:

```java
Path<Integer> wrong = customer.<Integer>get("email");
```

mã có thể vẫn qua compile time vì bạn đã tự khai báo tham số kiểu, trong khi mapping thực tế là String. Lỗi có thể chỉ được phát hiện khi provider phân tích/dịch query hoặc thực thi.

Đây chính là lý do dùng static metamodel:

```java
Path<String> correct = customer.get(Customer_.email);
```

Meta-attribute `Customer_.email` mang thông tin kiểu từ entity, thay vì để lập trình viên tự khẳng định một type không được kiểm tra với tên chuỗi.

### 5.2. get(String) khi nào vẫn hữu ích?

- Xây công cụ có bộ lọc động theo tên thuộc tính đã được whitelist.
- Viết query nhỏ mà project chưa cấu hình annotation processor.
- Xử lý metadata runtime khi tên thuộc tính được chọn từ một tập hợp hợp lệ.
- Tương thích với một số code legacy.

Nếu dùng string-based access, nên giới hạn tên thuộc tính bởi enum/whitelist và có integration test truy vấn thực tế. Không nối trực tiếp tên field tùy ý từ user vào criteria hoặc JPQL.

## 6. Static metamodel là gì?

**Static metamodel** là các Java classes thường có hậu tố dấu gạch dưới, được sinh từ các entity/embeddable đã ánh xạ. Ví dụ:

```text
Customer.java         ---> Customer_.java
Address.java          ---> Address_.java
SalesOrder.java       ---> SalesOrder_.java
OrderLine.java        ---> OrderLine_.java
```

Với entity `Customer`, một lớp metamodel điển hình trông như sau:

```java
package com.example.shop.domain;

import jakarta.persistence.metamodel.*;
import jakarta.persistence.metamodel.StaticMetamodel;

@StaticMetamodel(Customer.class)
public abstract class Customer_ {

    public static volatile SingularAttribute<Customer, Long> id;

    public static volatile SingularAttribute<Customer, String> email;

    public static volatile SingularAttribute<Customer, String> displayName;

    public static volatile SingularAttribute<Customer, Address> address;

    public static volatile ListAttribute<Customer, SalesOrder> orders;
}
```

**Đoạn trên minh họa hình dạng lớp được sinh, không phải khuyến nghị tự viết tay toàn bộ `Customer_`.** Các field metadata này được provider/annotation processing hỗ trợ theo cơ chế JPA static metamodel; cấu hình code generation mới là cách duy trì đồng bộ với entity.

Ý nghĩa:

- `SingularAttribute<Customer, String> email`: Customer sở hữu một thuộc tính đơn kiểu String.
- `SingularAttribute<Customer, Address> address`: thuộc tính đơn có kiểu embeddable Address.
- `ListAttribute<Customer, SalesOrder> orders`: thuộc tính collection chứa SalesOrder.

Ví dụ static metamodel của SalesOrder:

```java
@StaticMetamodel(SalesOrder.class)
public abstract class SalesOrder_ {

    public static volatile SingularAttribute<SalesOrder, Long> id;

    public static volatile SingularAttribute<SalesOrder, Customer> customer;

    public static volatile SingularAttribute<SalesOrder, OrderStatus> status;

    public static volatile SingularAttribute<SalesOrder, BigDecimal> totalAmount;

    public static volatile SingularAttribute<SalesOrder, Instant> createdAt;

    public static volatile ListAttribute<SalesOrder, OrderLine> lines;
}
```

Và Address:

```java
@StaticMetamodel(Address.class)
public abstract class Address_ {

    public static volatile SingularAttribute<Address, String> city;

    public static volatile SingularAttribute<Address, String> postalCode;
}
```

### 6.1. Vì sao dùng tên lớp có hậu tố _?

Tên như `Customer_` là **quy ước canonical static metamodel**: nó liên hệ trực tiếp với `Customer` để tooling và lập trình viên nhận biết. `Customer_.email` là một Java field, giúp code completion và refactor hoạt động tốt hơn so với `"email"`.

### 6.2. Static metamodel không phải DTO hay entity

`Customer_` không biểu diễn một bản ghi Customer, không dùng `EntityManager.persist`, không có dữ liệu từng người dùng. Nó chỉ là **metadata của mapping**.

### 6.3. Static metamodel và runtime metamodel là hai cách truy cập metadata

- **Static metamodel:** tham chiếu field `Customer_.email` trong Java code và được kiểm tra kiểu ở compile time.
- **Runtime metamodel:** gọi `em.getMetamodel()` rồi tra `EntityType`, `ManagedType`, `Attribute` bằng API lúc chạy.

Chúng không phải hai mô hình dữ liệu khác nhau; đều mô tả entity model do JPA quản lý, nhưng phục vụ những cách sử dụng khác nhau.

## 7. Sinh static metamodel trong dự án thực tế

Thường cấu hình **annotation processor** cho build để sinh các lớp hậu tố `_`. Tên artifact, phiên bản và namespace phải phù hợp provider và Jakarta Persistence đang dùng.

Ví dụ minh họa với Gradle cho dự án Hibernate ORM sử dụng Jakarta namespace:

```groovy
dependencies {
    implementation "jakarta.persistence:jakarta.persistence-api:<version>"
    implementation "org.hibernate.orm:hibernate-core:<hibernate-version>"

    annotationProcessor "org.hibernate.orm:hibernate-jpamodelgen:<hibernate-version>"
}
```

`<version>` và `<hibernate-version>` trong ví dụ là **placeholder**, phải thay bằng các phiên bản thực tế tương thích với BOM, framework và Java runtime của dự án. Không sao chép nguyên chuỗi placeholder để chạy build.

Trong một số phiên bản Hibernate, packaging/tooling của metamodel generator có thể được phân phối hoặc cấu hình khác; hãy dùng processor đúng theo provider/version đã chọn. Với EclipseLink hoặc provider khác, dùng trình sinh canonical metamodel tương ứng và cấu hình annotation processing thích hợp.

### 7.1. Các lớp tạo ra thường nằm ở đâu?

Với Gradle/Maven, generated sources thường xuất hiện trong thư mục build do annotation processor quản lý. IDE cần nhận diện generated sources để code completion và compile hoạt động.

Ví dụ quy trình:

```text
Customer.java, SalesOrder.java, ...
             |
             | Java annotation processing
             v
Customer_.java, SalesOrder_.java, ...
             |
             | Java compiler
             v
Application sử dụng Customer_.email
```

Không nên tự chỉnh các file generated: lần build sau có thể ghi đè. Thay đổi entity gốc hoặc cấu hình processor rồi tái sinh.

### 7.2. Namespace jakarta và javax phải đồng bộ

Trong dự án Jakarta Persistence hiện đại:

```java
import jakarta.persistence.criteria.*;
import jakarta.persistence.metamodel.*;
```

Trong dự án cũ:

```java
import javax.persistence.criteria.*;
import javax.persistence.metamodel.*;
```

Không trộn `jakarta.persistence.metamodel.SingularAttribute` với `javax.persistence.criteria.Path`. Mặc dù tên class gần giống nhau, chúng thuộc hai package khác biệt; processor cũng phải tương thích.

### 7.3. Khi Customer_ không được sinh

Một số nguyên nhân phổ biến:

- Chưa khai báo `annotationProcessor` hoặc chưa bật annotation processing trong IDE/build.
- Dùng phiên bản processor không tương thích với Hibernate/JPA hiện hành.
- Dùng namespace `javax` trong entity và `jakarta` ở processor/query.
- Generated source directory không được IDE hoặc compiler nhận diện.
- Build cache/generated files cũ chưa được cập nhật sau đổi tên field.
- Mô hình entity vi phạm mapping rules, làm processor không sinh metadata đúng.
- Multi-module project chưa đưa generated metamodel vào compile classpath của module cần sử dụng.

Khi gặp lỗi `cannot find symbol: Customer_`, cần kiểm tra **code generation**, không sửa Criteria query thành string-based một cách vội vàng. Worker bài học này không chạy build; phần cấu hình mang tính hướng dẫn để người học tự thiết lập trong dự án.

## 8. Path.get(SingularAttribute): đi qua thuộc tính có kiểu

Đây là trọng tâm của bài.

### 8.1. Chọn một thuộc tính cơ bản

```java
Root<Customer> c = cq.from(Customer.class);

Path<String> email = c.get(Customer_.email);
Path<Long> id = c.get(Customer_.id);
```

Kiểu phía bên phải được suy ra từ metadata:

- `Customer_.email` là `SingularAttribute<Customer, String>`.
- `c.get(Customer_.email)` trả đường dẫn String.
- `Customer_.id` mang kiểu Long, kết quả là `Path<Long>`.

Đây là lợi thế so với `get("email")`: nếu đổi field Java từ `email` sang `primaryEmail`, processor sẽ sinh `Customer_.primaryEmail` thay vì `Customer_.email`; phần query còn dùng field cũ sẽ bị Java compiler báo lỗi sau khi generated code được cập nhật.

### 8.2. Một ví dụ lỗi compile-time

```java
Root<Customer> c = cq.from(Customer.class);

// Sai kiểu: email là String chứ không phải BigDecimal.
Path<BigDecimal> amount = c.get(Customer_.email);
```

Đoạn trên không phù hợp với kiểu generic metadata, nên compiler có thể phát hiện thay vì đợi JPA provider phân tích một query string.

### 8.3. Một ví dụ lỗi thuộc tính của entity khác

```java
Root<Customer> c = cq.from(Customer.class);

// Sai: totalAmount là thuộc tính của SalesOrder,
// không phải của Customer.
Path<BigDecimal> p = c.get(SalesOrder_.totalAmount);
```

`SingularAttribute<SalesOrder,BigDecimal>` không phù hợp với `Root<Customer>`. Đây là khả năng kiểm tra kiểu/cấu trúc rất hữu ích trong code query lớn.

### 8.4. Static metamodel không bảo đảm tuyệt đối mọi Criteria đều type-safe

Một số method của `CriteriaBuilder`, chẳng hạn những overload của `equal` nhận `Expression<?>` và `Object`, có hợp đồng generic khá rộng:

```java
cb.equal(c.get(Customer_.email), 12345);
```

Mã có thể vẫn compile vì overload chấp nhận Object, dù so sánh String với số không hợp lệ về ngữ nghĩa hoặc không được provider/DB hỗ trợ.

**Không nên quảng cáo Criteria API như “trình biên dịch chắc chắn bắt được mọi lỗi query”.** Static metamodel loại bỏ nhiều lỗi đặt tên và truy cập sai loại thuộc tính, nhưng không thay việc kiểm thử mapping, tham số và SQL thực tế.

## 9. Đi qua @Embedded với Path lồng nhau

Customer có:

```java
@Embedded
private Address address;
```

Address có:

```java
private String city;
```

Với static metamodel:

```java
Root<Customer> c = cq.from(Customer.class);

Path<Address> address = c.get(Customer_.address);
Path<String> city = address.get(Address_.city);

cq.where(cb.equal(city, "Hà Nội"));
```

Có thể viết ngắn:

```java
cq.where(
    cb.equal(
        c.get(Customer_.address).get(Address_.city),
        "Hà Nội"
    )
);
```

Tương đương ý tưởng JPQL:

```jpql
select c
from Customer c
where c.address.city = :city
```

Provider biết Address được nhúng vào Customer và `city` được ánh xạ sang `city_name`. Không cần tự viết join bảng Address nếu mô hình dùng `@Embeddable` và các cột cùng bảng.

### 9.1. @AttributeOverride không đổi tên đường dẫn Criteria

Giả sử ở Customer:

```java
@Embedded
@AttributeOverride(
    name = "city",
    column = @Column(name = "billing_city")
)
private Address address;
```

Path vẫn là:

```java
c.get(Customer_.address).get(Address_.city);
```

`@AttributeOverride` đổi tên cột SQL, không đổi tên persistent attribute Java.

### 9.2. Embedded object có thể NULL

Nếu địa chỉ không bắt buộc, trường `address` có thể nullable theo mô hình/provider. Điều kiện:

```java
cb.equal(c.get(Customer_.address).get(Address_.city), cityName)
```

không tự coi address null là city rỗng. Nếu cần tìm khách không có địa chỉ hoặc city null, thiết kế predicate `isNull` phù hợp với mapping và database. Với embedded objects, cơ chế phân biệt toàn bộ component null với mọi cột component null còn phụ thuộc provider/mapping.

## 10. Đi qua @ManyToOne: Path hay Join?

SalesOrder có:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
```

Có hai cách thường gặp để truy cập email của Customer.

### 10.1. Đi qua Path của association đơn

```java
CriteriaQuery<SalesOrder> cq =
    cb.createQuery(SalesOrder.class);

Root<SalesOrder> order = cq.from(SalesOrder.class);

Path<String> customerEmail = order
    .get(SalesOrder_.customer)
    .get(Customer_.email);

cq.select(order)
  .where(cb.equal(customerEmail, "an@example.com"));
```

Path chain này biểu diễn:

```text
SalesOrder
   |
   | .get(SalesOrder_.customer)
   v
Customer
   |
   | .get(Customer_.email)
   v
String email
```

JPA provider dùng relationship metadata để tạo SQL join/foreign-key access tương ứng. Đường dẫn xuyên association đơn có thể dẫn tới **implicit join**; chi tiết SQL phụ thuộc query và provider.

### 10.2. JOIN tường minh

```java
CriteriaQuery<SalesOrder> cq =
    cb.createQuery(SalesOrder.class);

Root<SalesOrder> order = cq.from(SalesOrder.class);

Join<SalesOrder, Customer> customer =
    order.join(SalesOrder_.customer, JoinType.INNER);

cq.select(order)
  .where(
      cb.equal(
          customer.get(Customer_.email),
          "an@example.com"
      )
  );
```

`Join` được dùng khi muốn điều khiển kiểu join (`INNER`, `LEFT`), đặt điều kiện `ON` phù hợp hoặc sử dụng các thuộc tính của đối tượng liên quan nhiều lần.

### 10.3. LEFT JOIN với association tùy chọn

Giả sử business cho phép SalesOrder không có Customer. Muốn giữ cả các đơn không có Customer:

```java
Root<SalesOrder> order = cq.from(SalesOrder.class);

Join<SalesOrder, Customer> customer =
    order.join(SalesOrder_.customer, JoinType.LEFT);

cq.select(order)
  .where(
      cb.or(
          cb.equal(customer.get(Customer_.email), email),
          cb.isNull(customer.get(Customer_.id))
      )
  );
```

Ví dụ này chỉ hợp nghĩa nếu mapping cho phép quan hệ Customer là optional; entity mẫu `optional = false` nên không có đơn như vậy trong dữ liệu hợp lệ. Với mục tiêu lọc/giữ các row không có relation, cần xem ngữ nghĩa `LEFT JOIN` và `WHERE` cùng nhau.

Nếu chỉ cần điều kiện `email = :email` trong WHERE, các row có Customer NULL vẫn bị loại, dù JOIN là LEFT. Chọn LEFT JOIN không tự bảo đảm mọi row phía trái sẽ có mặt sau WHERE.

### 10.4. Đọc Path không khởi tạo entity ngay

```java
Path<String> email = customer.get(Customer_.email);
```

Câu này chỉ **xây query**. Nó không lập tức tải Customer hoặc thực thi SQL. Khi gọi `em.createQuery(cq).getResultList()`, provider mới thực thi truy vấn theo ngữ cảnh.

## 11. Collection-valued attribute cần Join, không thể điều hướng như một đối tượng đơn

`Customer.orders` là `List<SalesOrder>`. Một thao tác sai về mặt tư duy là:

```java
// KHÔNG phải cách điều hướng hợp lệ qua collection:
customer.get("orders").get("status");
```

`orders` chứa **nhiều SalesOrder**, không phải một SalesOrder duy nhất. Để lọc theo thuộc tính của các phần tử, cần JOIN collection.

### 11.1. ListJoin có kiểu

```java
CriteriaQuery<Customer> cq =
    cb.createQuery(Customer.class);

Root<Customer> customer = cq.from(Customer.class);

ListJoin<Customer, SalesOrder> order =
    customer.join(Customer_.orders, JoinType.INNER);

cq.select(customer)
  .distinct(true)
  .where(cb.equal(order.get(SalesOrder_.status), OrderStatus.PAID));
```

`Customer_.orders` mang kiểu `ListAttribute<Customer,SalesOrder>`. Phương thức `join` tạo `ListJoin<Customer,SalesOrder>`, nên biểu thức `order.get(SalesOrder_.status)` nhận metadata thuộc SalesOrder.

Tương đương JPQL:

```jpql
select distinct c
from Customer c
join c.orders o
where o.status = :paid
```

### 11.2. Vì sao thường dùng distinct(true)?

Nếu một Customer có ba đơn PAID, INNER JOIN tạo ba joined rows tham chiếu cùng Customer. Khi `select(customer)`, một người có thể xuất hiện nhiều lần trong query result về mặt ngữ nghĩa join. `cq.distinct(true)` yêu cầu loại trùng kết quả.

`distinct(true)` không phải chỉ định tải Customer với quan hệ đã được fetch; nó điều chỉnh tính duy nhất của query result. Chi tiết SQL DISTINCT và de-duplication của provider có thể khác theo phiên bản.

### 11.3. Các loại Join theo collection

| Metadata | Loại Join thường dùng | Phần tử sau JOIN |
|---|---|---|
| `ListAttribute<X,Y>` | `ListJoin<X,Y>` | `Y` |
| `SetAttribute<X,Y>` | `SetJoin<X,Y>` | `Y` |
| `CollectionAttribute<X,Y>` | `CollectionJoin<X,Y>` | `Y` |
| `MapAttribute<X,K,V>` | `MapJoin<X,K,V>` | Giá trị `V` cùng thao tác key/value |
| `SingularAttribute<X,Y>` là relation | `Join<X,Y>` | Entity `Y` |

Không phải mọi collection đều cần tải toàn bộ để query. JOIN trong Criteria diễn đạt phép liên kết ở database, không tương đương gọi getter collection trên entity đã tải.

### 11.4. ListJoin.index và MapJoin.key

Với những list được ánh xạ chỉ số bằng `@OrderColumn`, `ListJoin.index()` giúp biểu diễn vị trí của phần tử theo mapping. Với map, `MapJoin.key()` và `MapJoin.value()` giúp truy cập key/value.

Các phương thức này cần mapping collection phù hợp; không giả định mọi List entity đều có chỉ số persistent dùng được trong SQL nếu chỉ áp dụng `@OrderBy` mà không có `@OrderColumn`.

## 12. Điều kiện CriteriaBuilder với Path có kiểu

Sau khi có Path, ta dùng `CriteriaBuilder` để tạo Predicate.

### 12.1. So sánh bằng

```java
Root<SalesOrder> order = cq.from(SalesOrder.class);

Predicate paid = cb.equal(
    order.get(SalesOrder_.status),
    OrderStatus.PAID
);
```

Tương đương:

```jpql
where o.status = :paid
```

Để tham số không hard-code:

```java
ParameterExpression<OrderStatus> statusParam =
    cb.parameter(OrderStatus.class, "status");

cq.where(
    cb.equal(order.get(SalesOrder_.status), statusParam)
);

List<SalesOrder> result = em.createQuery(cq)
    .setParameter("status", OrderStatus.PAID)
    .getResultList();
```

### 12.2. So sánh số bằng greaterThan/lessThan

```java
Path<BigDecimal> amount =
    order.get(SalesOrder_.totalAmount);

Predicate minPrice = cb.greaterThanOrEqualTo(
    amount,
    new BigDecimal("100000")
);
```

`BigDecimal` triển khai `Comparable<BigDecimal>`, nên các overload `greaterThan`/`lessThan` áp dụng.

Không ép `amount` thành `Path<String>` để so sánh như chuỗi. Thứ tự từ điển của chữ số khác thứ tự số học.

### 12.3. Khoảng thời gian

```java
Path<Instant> createdAt =
    order.get(SalesOrder_.createdAt);

Predicate inWindow = cb.and(
    cb.greaterThanOrEqualTo(createdAt, startInstant),
    cb.lessThan(createdAt, endInstant)
);
```

Khoảng `[start, end)` (bao gồm đầu, loại cuối) thường phù hợp cho báo cáo theo ngày/tháng. Lúc bind `Instant`, cần hiểu cách database lưu timezone và kiểu thời gian.

### 12.4. LIKE và LOWER

```java
Path<String> name = customer.get(Customer_.displayName);

Predicate matches = cb.like(
    cb.lower(name),
    "%" + keyword.toLowerCase(Locale.ROOT) + "%"
);
```

Cách này mang tính minh họa. Trong production, ký tự `%` và `_` từ input có ý nghĩa wildcard; nếu muốn match literal thì phải escape pattern theo quy tắc hỗ trợ. Collation, normalization và index cũng ảnh hưởng kết quả và hiệu năng.

### 12.5. NULL

```java
Predicate noAddress = cb.isNull(
    customer.get(Customer_.address)
);
```

Với các thuộc tính nullable cụ thể:

```java
Predicate noCity = cb.isNull(
    customer.get(Customer_.address).get(Address_.city)
);
```

Tránh:

```java
// Không nên coi equal(path, null) là cách đọc rõ nhất:
cb.equal(customer.get(Customer_.email), null);
```

Dùng `isNull` hoặc `isNotNull` khi cần truy vấn NULL.

### 12.6. IN

```java
Path<OrderStatus> status =
    order.get(SalesOrder_.status);

Predicate allowed = status.in(
    OrderStatus.NEW,
    OrderStatus.PAID
);
```

Hoặc sử dụng collection giá trị:

```java
List<OrderStatus> statuses = List.of(
    OrderStatus.NEW,
    OrderStatus.PAID
);

Predicate allowed = status.in(statuses);
```

Cần xử lý trường hợp collection rỗng rõ ràng; không dựa vào việc provider tự tạo cú pháp `IN ()` portable hoặc áp dụng đúng ý nghĩa “không có trạng thái nào được phép”.

### 12.7. AND / OR / NOT

```java
Predicate paid = cb.equal(
    order.get(SalesOrder_.status),
    OrderStatus.PAID
);

Predicate large = cb.greaterThanOrEqualTo(
    order.get(SalesOrder_.totalAmount),
    minimum
);

cq.where(cb.and(paid, large));
```

Có thể viết:

```java
cq.where(cb.or(paid, large));
```

Tùy nghiệp vụ. Không nhầm “đơn đã thanh toán **và** giá trị lớn” với “đã thanh toán **hoặc** giá trị lớn”.

## 13. Truy vấn mẫu hoàn chỉnh dùng Path + static metamodel

### 13.1. Tìm Customer theo email

```java
public List<Customer> findCustomersByEmail(
        EntityManager em,
        String email
) {
    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<Customer> cq =
        cb.createQuery(Customer.class);

    Root<Customer> c = cq.from(Customer.class);

    ParameterExpression<String> emailParam =
        cb.parameter(String.class, "email");

    cq.select(c)
      .where(cb.equal(c.get(Customer_.email), emailParam));

    return em.createQuery(cq)
        .setParameter(emailParam, email)
        .getResultList();
}
```

Điểm cần nhớ:

- `Customer.class` là result type, không phải SQL table.
- `Customer_.email` là metadata typed, không phải String column name.
- `ParameterExpression<String>` làm rõ kiểu đầu vào.
- `getResultList()` trả danh sách rỗng khi không có dữ liệu, thay vì kết luận mỗi email chắc chắn tồn tại.

### 13.2. Lấy đơn theo trạng thái, giá trị và thời gian

```java
public List<SalesOrder> searchOrders(
        EntityManager em,
        OrderStatus status,
        BigDecimal minAmount,
        Instant fromInclusive,
        Instant toExclusive
) {
    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<SalesOrder> cq =
        cb.createQuery(SalesOrder.class);

    Root<SalesOrder> o = cq.from(SalesOrder.class);

    List<Predicate> predicates = new ArrayList<>();

    if (status != null) {
        predicates.add(
            cb.equal(o.get(SalesOrder_.status), status)
        );
    }

    if (minAmount != null) {
        predicates.add(
            cb.greaterThanOrEqualTo(
                o.get(SalesOrder_.totalAmount),
                minAmount
            )
        );
    }

    if (fromInclusive != null) {
        predicates.add(
            cb.greaterThanOrEqualTo(
                o.get(SalesOrder_.createdAt),
                fromInclusive
            )
        );
    }

    if (toExclusive != null) {
        predicates.add(
            cb.lessThan(
                o.get(SalesOrder_.createdAt),
                toExclusive
            )
        );
    }

    cq.select(o)
      .where(cb.and(predicates.toArray(new Predicate[0])))
      .orderBy(
          cb.desc(o.get(SalesOrder_.createdAt)),
          cb.desc(o.get(SalesOrder_.id))
      );

    return em.createQuery(cq)
        .setMaxResults(100)
        .getResultList();
}
```

Các import bổ sung:

```java
import java.util.ArrayList;
import java.util.List;
import java.math.BigDecimal;
import java.time.Instant;
import jakarta.persistence.criteria.*;
```

Đây là ví dụ query động: chỉ thêm điều kiện khi có giá trị lọc, nhưng các field vẫn được tham chiếu bằng static metamodel. `cb.and()` với mảng predicate rỗng biểu diễn điều kiện true theo API, nên query không có filter vẫn có thể trả dữ liệu, được giới hạn tối đa 100 rows.

### 13.3. Tại sao đây là một lợi thế của Criteria?

Với JPQL chuỗi, một query có 10 điều kiện tùy chọn thường cần lắp ráp câu WHERE, quản lý khoảng trắng, tên parameter và JOIN. Criteria cho phép ghép các `Predicate` và `Path` theo cấu trúc Java. Trong ứng dụng có nhiều bộ lọc tùy chọn, điều này có thể giảm lỗi ghép chuỗi.

Tuy nhiên Criteria API có nhiều boilerplate hơn JPQL. Không cần chuyển mọi query đơn giản thành Criteria nếu JPQL đọc dễ hơn và project có đủ test.

## 14. Dynamic filter: tái sử dụng Path, không lặp tên field

Giả sử nhiều điều kiện cần truy cập cùng thuộc tính:

```java
Root<SalesOrder> o = cq.from(SalesOrder.class);

Path<BigDecimal> total = o.get(SalesOrder_.totalAmount);

Predicate positive = cb.greaterThan(total, BigDecimal.ZERO);
Predicate underLimit = cb.lessThan(total, maximum);

cq.where(cb.and(positive, underLimit));
```

Việc đặt tên `total` cho Path:

- Làm rõ biểu thức đang truy cập.
- Hạn chế lặp metadata field.
- Hỗ trợ tái sử dụng trong `where` và `orderBy` của cùng query.
- Giảm nhầm lẫn khi association chain dài.

**Chú ý:** Path và Root gắn với cấu trúc Criteria query nhất định. Không tự ý lưu một `Path` vào singleton/cache rồi tái sử dụng cho những CriteriaQuery hoàn toàn khác. Nên tạo Root/Join/Path **trong ngữ cảnh xây dựng query hiện tại**.

### 14.1. Phân biệt helper tạo Path và helper giữ Path

Một helper typed có thể nhận Root/Path và metadata:

```java
public static <X, Y> Path<Y> pathOf(
        Path<X> parent,
        SingularAttribute<? super X, Y> attribute
) {
    return parent.get(attribute);
}
```

Dùng:

```java
Path<String> email =
    pathOf(customerRoot, Customer_.email);
```

Helper không giữ bất kỳ mutable Criteria state nào qua các truy vấn; nó chỉ trích xuất Path ngay khi cần.

## 15. Tạo JOIN chỉ khi cần, tránh tạo JOIN trùng

Ví dụ query đơn hàng lọc theo nhiều thuộc tính Customer:

```java
Root<SalesOrder> o = cq.from(SalesOrder.class);

Join<SalesOrder, Customer> c =
    o.join(SalesOrder_.customer, JoinType.INNER);

Predicate matchEmail = cb.equal(
    c.get(Customer_.email), email
);

Predicate matchName = cb.like(
    cb.lower(c.get(Customer_.displayName)),
    pattern
);

cq.where(cb.and(matchEmail, matchName));
```

Tái sử dụng biến `c` rõ ràng hơn việc gọi `o.join(SalesOrder_.customer)` nhiều lần ở những nhánh filter khác nhau. Gọi `join` lặp có thể tạo **nhiều join nodes riêng biệt**, kéo theo SQL phức tạp hoặc ngữ nghĩa khác dự kiến.

Với query builder có rất nhiều điều kiện động, có thể dùng một cấu trúc quản lý join theo association và join type, nhưng cần rất cẩn trọng về alias, ON condition và query scope. Không dùng map toàn cục ngoài query để lưu Join.

## 16. Có nên truy cập khóa ngoại bằng Path thay vì JOIN?

Nếu muốn lọc SalesOrder theo Customer ID:

```java
Predicate fromCustomer = cb.equal(
    order.get(SalesOrder_.customer).get(Customer_.id),
    customerId
);
```

Đây là một cách diễn đạt JPA theo **association path**. Provider có thể tối ưu việc so sánh ID qua foreign key, không nhất thiết tải Customer entity vào Java.

Cách khác là so sánh entity reference:

```java
Customer customerRef =
    em.getReference(Customer.class, customerId);

Predicate fromCustomer = cb.equal(
    order.get(SalesOrder_.customer),
    customerRef
);
```

Không dùng `getReference` để kết luận row đã tồn tại: nó có thể trả proxy/reference trước khi database xác nhận identity. Nếu nghiệp vụ cần kiểm tra Customer có thật hoặc user có quyền truy cập, phải thực hiện xác thực riêng.

Một JOIN rõ ràng cũng có thể dùng:

```java
Join<SalesOrder, Customer> c =
    order.join(SalesOrder_.customer);

Predicate fromCustomer =
    cb.equal(c.get(Customer_.id), customerId);
```

Chọn phương pháp dựa trên dữ liệu cần lấy và query plan thực tế; không nên tạo JOIN không cần thiết khi chỉ cần so sánh FK và mapping cho phép tối ưu.

## 17. CriteriaQuery<T> và Path<T> không phải cùng một kiểu T

Một điểm dễ nhầm:

```java
CriteriaQuery<Customer> cq =
    cb.createQuery(Customer.class);

Root<Customer> c = cq.from(Customer.class);
Path<String> email = c.get(Customer_.email);
```

Ở đây:

- `CriteriaQuery<Customer>` yêu cầu SELECT trả **Customer**.
- `Path<String>` biểu diễn một thuộc tính String có thể được dùng trong WHERE.
- Không thể `cq.select(email)` rồi kỳ vọng kết quả vẫn là Customer, vì result type không khớp.

Muốn SELECT email:

```java
CriteriaQuery<String> cq =
    cb.createQuery(String.class);

Root<Customer> c = cq.from(Customer.class);
cq.select(c.get(Customer_.email));

List<String> emails =
    em.createQuery(cq).getResultList();
```

Ngược lại, muốn trả cả Customer, dùng:

```java
CriteriaQuery<Customer> cq =
    cb.createQuery(Customer.class);

Root<Customer> c = cq.from(Customer.class);
cq.select(c);
```

**Chọn result type trước**, sau đó để các Path/Expression đưa vào SELECT có kiểu tương thích.

## 18. Chọn nhiều thuộc tính bằng Tuple và Path

Nếu cần email + tên thay vì entity:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Tuple> cq = cb.createTupleQuery();

Root<Customer> c = cq.from(Customer.class);

Path<String> email = c.get(Customer_.email);
Path<String> name = c.get(Customer_.displayName);

cq.multiselect(
    email.alias("email"),
    name.alias("name")
);

List<Tuple> tuples =
    em.createQuery(cq).getResultList();

for (Tuple tuple : tuples) {
    String e = tuple.get("email", String.class);
    String n = tuple.get("name", String.class);
}
```

`Tuple` là result container, không phải entity managed. Aliases ở `Tuple` không phải database column aliases bắt buộc; chúng là tên được dùng để lấy các selection elements trong kết quả Criteria.

### 18.1. DTO projection với cb.construct

Một DTO:

```java
package com.example.shop.readmodel;

import java.math.BigDecimal;

public record OrderSummary(
    Long orderId,
    String customerName,
    BigDecimal totalAmount
) { }
```

Query:

```java
CriteriaQuery<OrderSummary> cq =
    cb.createQuery(OrderSummary.class);

Root<SalesOrder> o = cq.from(SalesOrder.class);
Join<SalesOrder, Customer> c =
    o.join(SalesOrder_.customer);

cq.select(
    cb.construct(
        OrderSummary.class,
        o.get(SalesOrder_.id),
        c.get(Customer_.displayName),
        o.get(SalesOrder_.totalAmount)
    )
);

List<OrderSummary> summaries =
    em.createQuery(cq).getResultList();
```

Constructor của `OrderSummary` phải khớp số lượng và kiểu selected expressions. Criteria giúp kiểm tra nhiều loại Path, nhưng việc khớp constructor/selection và provider behavior vẫn cần integration tests.

Kết quả DTO không được JPA dirty-check. Đây thường là lựa chọn hợp lý cho read-only API chỉ cần vài field.

## 19. ORDER BY và Path

```java
CriteriaQuery<SalesOrder> cq =
    cb.createQuery(SalesOrder.class);

Root<SalesOrder> order = cq.from(SalesOrder.class);

Path<Instant> createdAt =
    order.get(SalesOrder_.createdAt);

Path<Long> id =
    order.get(SalesOrder_.id);

cq.select(order)
  .orderBy(
      cb.desc(createdAt),
      cb.desc(id)
  );
```

Hai trường sắp xếp tạo thứ tự ổn định hơn khi nhiều đơn có cùng `createdAt`.

### 19.1. Không bind tên thuộc tính sắp xếp như parameter

Không thể coi tên cột/field như một giá trị bind:

```java
// Không dùng parameter để thay đổi định danh attribute.
cb.asc(cb.parameter(String.class, "sortField"));
```

Biểu thức trên sắp xếp theo một **giá trị biểu thức String**, không biến dữ liệu "createdAt" thành một Path của thuộc tính.

Khi client chọn sort key, dùng whitelist:

```java
Expression<?> sortExpression = switch (sortKey) {
    case "created" -> order.get(SalesOrder_.createdAt);
    case "amount"  -> order.get(SalesOrder_.totalAmount);
    case "id"      -> order.get(SalesOrder_.id);
    default -> throw new IllegalArgumentException(
        "Sort key không được hỗ trợ"
    );
};

cq.orderBy(cb.asc(sortExpression));
```

Điều này ngăn client tự tạo đường dẫn đến trường nội bộ hoặc gõ tên JPQL/SQL không được phép.

### 19.2. Pagination

```java
List<SalesOrder> page = em.createQuery(cq)
    .setFirstResult(20)
    .setMaxResults(10)
    .getResultList();
```

`setFirstResult`/`setMaxResults` giới hạn kết quả truy vấn, không thuộc `Path`. Nếu phân trang theo collection fetch join, cần thận trọng vì nhiều SQL rows có thể ứng với một entity parent; phân trang có thể không hiệu quả hoặc cần xử lý ở memory.

## 20. GROUP BY, COUNT và Path

Criteria API vẫn dùng Path để nhóm hoặc tổng hợp.

Ví dụ đếm SalesOrder theo status:

```java
CriteriaQuery<Tuple> cq = cb.createTupleQuery();

Root<SalesOrder> order = cq.from(SalesOrder.class);

Path<OrderStatus> status =
    order.get(SalesOrder_.status);

Expression<Long> count = cb.count(order);

cq.multiselect(
      status.alias("status"),
      count.alias("orderCount")
  )
  .groupBy(status)
  .orderBy(cb.desc(count));

List<Tuple> stats =
    em.createQuery(cq).getResultList();
```

Đọc:

```java
for (Tuple t : stats) {
    OrderStatus s = t.get("status", OrderStatus.class);
    Long n = t.get("orderCount", Long.class);
}
```

### 20.1. SUM trên numeric Path

```java
CriteriaQuery<BigDecimal> cq =
    cb.createQuery(BigDecimal.class);

Root<SalesOrder> o = cq.from(SalesOrder.class);

Expression<BigDecimal> total =
    cb.sum(o.get(SalesOrder_.totalAmount));

cq.select(total);
```

`SUM` trả giá trị aggregate, không tạo một SalesOrder instance. Khi không có dữ liệu phù hợp, tổng có thể là null, trong khi `COUNT` thường trả 0.

### 20.2. JOIN collection có thể làm COUNT bị nhân đôi

```java
Root<Customer> c = cq.from(Customer.class);
ListJoin<Customer, SalesOrder> o =
    c.join(Customer_.orders);
```

Nếu một Customer có ba order, JOIN tạo ba result rows tương ứng. `cb.count(c)` có thể đếm ba lần xuất hiện, không phải một Customer duy nhất.

Để đếm số Customer phân biệt thỏa điều kiện:

```java
Expression<Long> countCustomers =
    cb.countDistinct(c);
```

Và để đếm order:

```java
Expression<Long> countOrders =
    cb.count(o);
```

Dùng biểu thức đếm theo **grain** cần tính. Không cho rằng static metamodel sẽ tự ngăn lỗi logic JOIN làm nhân bản kết quả.

## 21. Mô hình siêu dữ liệu runtime: em.getMetamodel()

Static metamodel giúp code dùng compile-time references. Nhưng khi xây công cụ generic, ta có thể tra metadata **lúc chạy**:

```java
import jakarta.persistence.metamodel.*;

Metamodel model = em.getMetamodel();

EntityType<Customer> customerType =
    model.entity(Customer.class);

SingularAttribute<? super Customer, String> emailAttribute =
    customerType.getSingularAttribute("email", String.class);
```

Từ metadata runtime này:

```java
CriteriaQuery<Customer> cq =
    cb.createQuery(Customer.class);

Root<Customer> c = cq.from(Customer.class);

Path<String> emailPath =
    c.get(emailAttribute);
```

Cách tiếp cận này vẫn có tra cứu chuỗi `"email"` trong runtime metadata, nên **không có lợi ích compile-time như `Customer_.email`** ở bước chọn tên. Nhưng sau khi lấy được `SingularAttribute`, các bước xây Path tiếp theo mang generic type rõ hơn.

### 21.1. Khi nào chọn runtime metamodel?

- Công cụ tạo form/filter dựa trên entity metadata.
- Query builder nhận bộ lọc cấu hình động nhưng có whitelist.
- Framework nội bộ cần biết thuộc tính singular/plural và Java type.
- Kiểm tra mapping runtime, chẳng hạn attribute có phải association không.
- Chức năng chung áp dụng cho nhiều entity types.

Trong business service đã biết rõ Customer/SalesOrder ở compile time, static metamodel thường đơn giản và an toàn hơn.

## 22. Path.getJavaType, getModel và introspection

Một Path có một số phương thức giúp kiểm tra đặc trưng của biểu thức.

Ví dụ:

```java
Path<String> email =
    customer.get(Customer_.email);

Class<?> type = email.getJavaType();
```

`getJavaType()` cho biết kiểu Java mà Criteria selection/path biểu diễn. Với email, thường là `String.class`.

`getModel()` trên Path cung cấp metadata `Bindable` của phần tử mô hình mà đường dẫn biểu diễn. Với root, join hoặc basic path, cần xem type cụ thể của metadata trước khi ép kiểu.

### 22.1. Có thể dùng getParentPath()

```java
Path<Address> address =
    customer.get(Customer_.address);

Path<String> city =
    address.get(Address_.city);

Path<?> parent = city.getParentPath();
```

`parent` biểu diễn phần Path trước `city` (ở đây là đường dẫn address). Những phương thức này hữu ích khi xây công cụ phân tích query hay generic DSL, nhưng business code thông thường chỉ cần lưu các Path variables rõ tên.

### 22.2. Không nhầm metadata object với dữ liệu từng row

`SingularAttribute<Customer, String>` không có giá trị email của một khách hàng. Nó chứa thông tin về thuộc tính **email** của mô hình. Chỉ khi query thực thi, provider mới đọc các giá trị row tương ứng.

### 22.3. Attribute.getName và getJavaType

Với runtime metamodel:

```java
String name = emailAttribute.getName();
Class<?> javaType = emailAttribute.getJavaType();
```

Ví dụ name có thể là `"email"` và Java type là `String.class`. Đây là thông tin mapping, không phải tên cột SQL bắt buộc. Cột có thể được đặt `email_address` qua `@Column`.

## 23. Tự xây Path từ metamodel cho thuộc tính tùy chọn

Một ứng dụng admin cho phép lọc Customer theo vài thuộc tính đã whitelist:

```java
public enum CustomerField {
    EMAIL,
    DISPLAY_NAME,
    CITY
}
```

Hàm chọn Path theo field:

```java
private static Path<String> stringField(
        Root<Customer> customer,
        CustomerField field
) {
    return switch (field) {
        case EMAIL -> customer.get(Customer_.email);
        case DISPLAY_NAME -> customer.get(Customer_.displayName);
        case CITY -> customer
            .get(Customer_.address)
            .get(Address_.city);
    };
}
```

Dùng:

```java
Path<String> path =
    stringField(customerRoot, requestedField);

Predicate p =
    cb.equal(path, requestedValue);
```

Thiết kế này:

- Không cho người dùng nhập chuỗi bất kỳ như `"passwordHash"` để đọc field nội bộ.
- Bảo đảm mỗi lựa chọn trả `Path<String>`.
- Refactor thuộc tính sẽ tác động tới metadata field được compiler tham chiếu.
- Có thể phân quyền từng field trong whitelist.
- Tránh chuyển lỗi typos trong UI thành lỗi JPA runtime khó hiểu.

Nếu field có các kiểu khác nhau (`Instant`, `BigDecimal`, enum...), đừng ép tất cả về String. Dùng DTO filter có kiểu, hoặc một abstraction generic với metadata/validator rõ ràng.

## 24. Generic Path builder: lợi ích và giới hạn của kiểu

Một helper typed:

```java
public static <X, Y> Path<Y> get(
        Path<X> parent,
        SingularAttribute<? super X, Y> attribute
) {
    return parent.get(attribute);
}
```

Ví dụ:

```java
Path<String> email =
    get(customerRoot, Customer_.email);

Path<Address> address =
    get(customerRoot, Customer_.address);

Path<String> city =
    get(address, Address_.city);
```

Compiler kiểm tra:

- Parent `Customer` phù hợp metadata `Customer_.email`.
- Kết quả của `Customer_.address` là `Address`.
- Parent `Address` phù hợp `Address_.city`.

Nếu parent generic bị suy giảm thành `Path<?>`, Java có thể mất thông tin kiểu để gọi các overload typed. Vì thế tránh thiết kế generic framework bằng cách biến tất cả Path thành raw `Path` hoặc ép kiểu không kiểm soát.

### 24.1. Không dùng raw types nếu không cần

```java
Path rawPath = customer.get(Customer_.email);
```

Raw type bỏ kiểm tra generic và có thể gây unchecked warnings hoặc lỗi runtime.

Ưu tiên:

```java
Path<String> email = customer.get(Customer_.email);
```

### 24.2. Metamodel không xác minh mọi cấu hình database

Dù compile thành công với `Customer_.email`, project vẫn có thể lỗi ở runtime do:

- Tên cột thực tế không khớp `@Column`.
- Migration chưa được áp dụng.
- SQL dialect hoặc driver không hỗ trợ biểu thức đã dùng.
- Mapping association không nhất quán.
- Entity/provider được khởi tạo với phiên bản khác generated metamodel.
- Nullability/concurrency phát sinh từ dữ liệu thật.
- Predicate có logic không đúng nghiệp vụ dù đúng kiểu Java.

Static metamodel cải thiện **an toàn về tên và kiểu mô hình**, không thay integration test với database.

## 25. Fetch join và Path: cùng association nhưng mục đích khác

Hai thao tác sau cùng bắt đầu từ relationship:

```java
Join<SalesOrder, Customer> c =
    order.join(SalesOrder_.customer, JoinType.INNER);
```

```java
Fetch<SalesOrder, Customer> f =
    order.fetch(SalesOrder_.customer, JoinType.LEFT);
```

Nhưng:

- `join(...)` tạo `Join` để lọc/điều hướng trong query và có thể chọn thuộc tính.
- `fetch(...)` tạo `Fetch` nhằm điều chỉnh **fetch plan** — tải association cùng root.
- `Fetch` không được thiết kế như một `Join` thông thường để tiếp tục `get(Customer_.email)` trong Criteria chuẩn.

Vì vậy không nên ép kiểu một `Fetch` sang `Join` chỉ để dùng `get`; cách này phụ thuộc provider hoặc gây lỗi runtime.

Nếu vừa muốn filter vừa muốn tải association, cần thiết kế query/fetch plan rõ ràng. Có thể dùng `join` cho điều kiện và `fetch` cho việc tải, hoặc dùng EntityGraph/projection khi phù hợp, đồng thời quan sát SQL để tránh trùng join không cần thiết.

### 25.1. N+1 không tự biến mất nhờ Criteria

```java
CriteriaQuery<SalesOrder> cq =
    cb.createQuery(SalesOrder.class);

Root<SalesOrder> o = cq.from(SalesOrder.class);
cq.select(o);
```

Kết quả chỉ chọn SalesOrder. Nếu sau đó truy cập `o.getCustomer()` với LAZY association cho nhiều đơn, vẫn có thể xảy ra N+1.

Criteria API là **cách xây query**, không tự động là giải pháp eager loading. Cần chọn fetch join, entity graph hoặc DTO projection đúng use case.

### 25.2. Collection fetch join và pagination

Nếu fetch nhiều collection hoặc fetch một collection lớn, SQL có thể nhân bản row parent. Kết hợp với `setMaxResults` có thể dẫn đến phân trang không hiệu quả hoặc provider phải xử lý trong memory.

Khi cần phân trang đơn hàng kèm lines, cân nhắc query trang ID trước, rồi tải collection theo danh sách ID bằng query thứ hai.

## 26. LEFT JOIN và điều kiện ON trong Criteria

Để lấy mọi Customer, đồng thời đếm các đơn PAID nếu có, dùng LEFT JOIN với điều kiện trên join:

```java
CriteriaQuery<Tuple> cq = cb.createTupleQuery();

Root<Customer> c = cq.from(Customer.class);

ListJoin<Customer, SalesOrder> o =
    c.join(Customer_.orders, JoinType.LEFT);

o.on(cb.equal(
    o.get(SalesOrder_.status),
    OrderStatus.PAID
));

cq.multiselect(
      c.get(Customer_.id).alias("customerId"),
      cb.count(o).alias("paidOrders")
  )
  .groupBy(c.get(Customer_.id));

List<Tuple> rows = em.createQuery(cq).getResultList();
```

Điều kiện `o.on(...)` được gắn vào JOIN và giúp giữ Customer không có Order PAID trong kết quả LEFT JOIN. Nếu thay bằng `cq.where(cb.equal(o.get(SalesOrder_.status), PAID))`, các Customer không có order PAID có thể bị lọc mất.

**Phân biệt:** `Join.on(...)` là điều kiện liên kết; `CriteriaQuery.where(...)` là điều kiện lọc toàn truy vấn sau FROM/JOIN theo ngữ nghĩa SQL tương ứng.

## 27. Subquery: Path từ Root của truy vấn con

Tìm Customer có ít nhất một đơn PAID:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Customer> cq =
    cb.createQuery(Customer.class);

Root<Customer> c = cq.from(Customer.class);

Subquery<Long> sq = cq.subquery(Long.class);
Root<SalesOrder> o = sq.from(SalesOrder.class);

sq.select(cb.literal(1L))
  .where(
      cb.equal(o.get(SalesOrder_.customer), c),
      cb.equal(o.get(SalesOrder_.status), OrderStatus.PAID)
  );

cq.select(c)
  .where(cb.exists(sq));

List<Customer> customers =
    em.createQuery(cq).getResultList();
```

Truy vấn con có **Root riêng** `o`, nhưng tham chiếu tới `c` của truy vấn ngoài để tạo điều kiện tương quan.

Trong trường hợp này, dùng `EXISTS` tránh việc JOIN collection làm lặp Customer khi có nhiều đơn PAID. Với bài toán “có ít nhất một phần tử”, EXISTS thường diễn đạt ý định rõ ràng hơn COUNT sau JOIN.

Không trộn Root/Join của một CriteriaQuery hoàn toàn khác vào truy vấn hiện tại rồi mong provider tự gắn ngữ cảnh. Khi xây subquery, tạo Root/Correlation đúng theo API và xác định rõ scope của các biến.

## 28. Mô hình typed metamodel và kế thừa entity

Giả sử có:

```java
@MappedSuperclass
public abstract class AuditedEntity {

    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "created_at")
    private Instant createdAt;
}
```

Và:

```java
@Entity
public class Invoice extends AuditedEntity {

    private BigDecimal amount;
}
```

Một canonical static metamodel có thể có:

```java
@StaticMetamodel(AuditedEntity.class)
public abstract class AuditedEntity_ {
    public static volatile SingularAttribute<AuditedEntity, Long> id;
    public static volatile SingularAttribute<AuditedEntity, Instant> createdAt;
}
```

```java
@StaticMetamodel(Invoice.class)
public abstract class Invoice_ extends AuditedEntity_ {
    public static volatile SingularAttribute<Invoice, BigDecimal> amount;
}
```

Vì Path typed overload chấp nhận `SingularAttribute<? super X,Y>`, một `Root<Invoice>` có thể truy cập metadata thuộc superclass phù hợp:

```java
Root<Invoice> invoice = cq.from(Invoice.class);

Path<Long> id = invoice.get(AuditedEntity_.id);
Path<BigDecimal> amount = invoice.get(Invoice_.amount);
```

Một số processor có thể thể hiện kế thừa metadata theo cách sinh code cụ thể, nhưng nguyên tắc của Criteria là **thuộc tính kế thừa từ persistent superclass có thể truy cập trên subtype khi mapping hợp lệ**.

### 28.1. Treat khi cần subtype-specific attributes

Nếu một association hoặc Root được khai báo với kiểu cha mà cần thuộc tính riêng của subtype, Criteria có `CriteriaBuilder.treat(...)` trong các phiên bản hỗ trợ.

Ví dụ khái niệm:

```java
Root<BasePayment> payment = cq.from(BasePayment.class);
Root<CardPayment> cardPayment = cb.treat(payment, CardPayment.class);

Path<String> lastFour = cardPayment.get(CardPayment_.lastFour);
```

Phần này giả định có entity inheritance mapping `BasePayment/CardPayment` hợp lệ và result query tương thích. Không dùng `get("lastFour")` trên Root<BasePayment> như thể mọi subtype đều có thuộc tính ấy. Chi tiết SQL/discriminator cần kiểm tra theo mapping chiến lược kế thừa.

## 29. Các lỗi thường gặp khi dùng Path và metamodel

### 29.1. Dùng tên SQL column trong get

```java
customer.get("email_address"); // Sai nếu attribute tên email.
```

Cách đúng:

```java
customer.get(Customer_.email);
```

`@Column(name=...)` ảnh hưởng mapping DB; Criteria dùng tên thuộc tính Java.

### 29.2. Nhầm Root với entity object

```java
Root<Customer> c = cq.from(Customer.class);
// c.getEmail() không tồn tại như getter business entity.
```

Root là node query, dùng `get(...)`.

### 29.3. Nhầm get(String) generic là compile-time type-safe tuyệt đối

```java
Path<Long> wrong = customer.<Long>get("email");
```

Java compiler có thể chấp nhận generic type tự khẳng định dù field email là String. Dùng `Customer_.email` để có metadata kiểu thật.

### 29.4. Không có Customer_ khi compile

Cần cấu hình annotation processor và đúng namespace/version; không tự gán `Customer_.email = null` để làm compiler im lặng.

### 29.5. Trộn javax và jakarta metamodel

`javax.persistence.metamodel.SingularAttribute` không tương thích với `jakarta.persistence.criteria.Path` trong cùng chữ ký API. Đồng bộ dependency và imports.

### 29.6. get thuộc tính của entity không liên quan

```java
customer.get(SalesOrder_.totalAmount);
```

Sử dụng metadata sai owner type. Trước tiên JOIN Customer.orders hoặc tạo Root<SalesOrder> đúng mục đích.

### 29.7. Chấm qua collection mà không JOIN

`customer.get(Customer_.orders).get(SalesOrder_.status)` không phải đường dẫn hợp lệ tới một thuộc tính đơn vì `orders` là collection. Dùng `ListJoin<Customer,SalesOrder>`.

### 29.8. Dùng JOIN để fetch mà không kiểm tra fetch plan

`order.join(SalesOrder_.customer)` không tự tương đương `order.fetch(SalesOrder_.customer)`. JOIN cho truy vấn, FETCH cho tải association.

### 29.9. Cast Fetch sang Join

Không portable. `Fetch` và `Join` có giao diện/contract khác nhau.

### 29.10. Tái sử dụng Root/Path giữa nhiều query

Path gắn với cây Criteria hiện tại. Tạo lại trong từng query để tránh reference lệch scope.

### 29.11. JOIN hai collection khiến kết quả bị nhân bản

Metamodel typed không thay đổi cardinality. Query JOIN hai collection có thể tạo tích các phần tử; cần DISTINCT/EXISTS hoặc tách query theo grain.

### 29.12. Dùng cb.equal(..., null) thay vì isNull

`NULL` có ngữ nghĩa đặc biệt. Dùng `cb.isNull(path)`/`cb.isNotNull(path)`.

### 29.13. Lấy Path<String> làm SELECT cho CriteriaQuery<Customer>

Result type không khớp. Nếu muốn select email, dùng `CriteriaQuery<String>`; nếu muốn entity, select Root<Customer>.

### 29.14. Bắt mọi field động bằng string từ user

Kết quả là query khó kiểm soát, có thể truy cập field không được phép. Dùng whitelist, typed filters và authentication/authorization rules.

### 29.15. Nghĩ static metamodel thay thế toàn bộ test

Chưa đủ: provider version, DB schema, query semantics, indexes và transaction behavior vẫn cần integration tests.

### 29.16. Nhầm path tới association với SQL JOIN FETCH

`order.get(SalesOrder_.customer).get(Customer_.email)` diễn đạt điều hướng thuộc tính, không tự bảo đảm Customer association của các result entities được khởi tạo để sử dụng sau transaction.

### 29.17. Dùng Path.getJavaType làm giá trị row

`getJavaType()` trả metadata kiểu, không trả nội dung `email` của một Customer cụ thể.

### 29.18. Dùng JPA static metamodel cũ sau khi refactor

Generated sources bị stale có thể khiến lỗi được phát hiện sai thời điểm hoặc không khớp runtime. Bảo đảm code generation chạy đúng trong build và không commit những file generated cũ tùy tiện.

### 29.19. Bỏ qua alias và JOIN scope trong subquery

Root của subquery khác Root của query ngoài; cần tham chiếu theo correlation/association hợp lệ.

### 29.20. Cho rằng CriteriaBuilder.equal bắt mọi lỗi kiểu

Overload nhận Object có thể cho phép biểu thức không tương thích compile-time; vẫn cần kiểm tra logic và test.

## 30. Hướng dẫn kiểm thử query dùng Path typed

Mặc dù static metamodel mang lại compile-time checking, integration test vẫn cần xác nhận truy vấn thực tế.

### 30.1. Test truy vấn thuộc tính đơn

Tạo Customer có `email = "an@example.com"`. Chạy:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Customer> cq = cb.createQuery(Customer.class);
Root<Customer> c = cq.from(Customer.class);

cq.select(c)
  .where(cb.equal(c.get(Customer_.email), "an@example.com"));

List<Customer> rows = em.createQuery(cq).getResultList();
```

Kỳ vọng chỉ những Customer tương ứng được trả. Việc kết quả đúng phụ thuộc fixture và transaction isolation của test.

### 30.2. Test embedded path

Tạo Customer có `address.city = "Đà Nẵng"` rồi kiểm tra:

```java
cb.equal(
    c.get(Customer_.address).get(Address_.city),
    "Đà Nẵng"
);
```

Test với cả address khác city và trường hợp address null nếu mapping cho phép.

### 30.3. Test Join collection

Tạo một Customer có hai đơn PAID, một Customer có một đơn NEW. Query JOIN + `distinct(true)` phải trả đúng Customer khi lọc PAID.

Nếu bỏ DISTINCT, test nên thể hiện hậu quả lặp parent theo join semantics nếu provider/selection tạo duplicate result rows.

### 30.4. Test typed metamodel sau khi đổi tên field

Đổi tên `Customer.displayName` thành `Customer.fullName` trong mô hình giả định rồi sinh lại metamodel. Những query còn dùng `Customer_.displayName` phải được compiler phát hiện, giúp giảm lỗi runtime do refactor.

### 30.5. Test trên provider/database mục tiêu

In-memory DB hữu ích cho thử nhanh, nhưng query path, timezone, collation, NULL và SQL dialect có thể khác production. Với chức năng quan trọng, dùng integration test chạy provider và database tương thích production, quan sát SQL khi cần phân tích JOIN/implicit join.

Các bước này là gợi ý thực hành cho người học; theo phạm vi STEP 4 của tác vụ soạn bài, không thực thi lượt Content QA hay build ở bước hiện tại.

## 31. Bài tập có gợi ý

### Bài 1: Path cơ bản

**Đề:** Dùng Criteria API tìm Customer theo email.

**Gợi ý:**

```java
Root<Customer> c = cq.from(Customer.class);
Path<String> email = c.get(Customer_.email);
cq.select(c).where(cb.equal(email, emailValue));
```

### Bài 2: Tên cột khác tên field

`Customer.email` ánh xạ `@Column(name = "email_address")`.

**Câu hỏi:** Dùng `get("email_address")` hay `get(Customer_.email)`?

**Gợi ý:** Criteria theo persistent attribute Java, dùng `get(Customer_.email)`.

### Bài 3: String-based path có thực sự type-safe?

```java
Path<Long> x = customer.<Long>get("email");
```

**Câu hỏi:** Vì sao code có thể compile mà vẫn sai?

**Gợi ý:** Generic type của `get(String)` được caller khẳng định; metamodel thực tế không được compiler xác minh ở đây.

### Bài 4: Embedded address

**Đề:** Lọc Customer có `address.city = "Huế"`.

**Gợi ý:**

```java
Path<String> city = customer
    .get(Customer_.address)
    .get(Address_.city);
cq.where(cb.equal(city, "Huế"));
```

### Bài 5: ManyToOne

**Đề:** Tìm SalesOrder theo email Customer.

**Gợi ý:**

```java
Path<String> email = order
    .get(SalesOrder_.customer)
    .get(Customer_.email);
cq.where(cb.equal(email, requestedEmail));
```

Hoặc JOIN tường minh tới Customer.

### Bài 6: Collection path

**Đề:** Tìm Customer có đơn PAID.

**Gợi ý:**

```java
ListJoin<Customer, SalesOrder> orders =
    customer.join(Customer_.orders);

cq.select(customer)
  .distinct(true)
  .where(cb.equal(
      orders.get(SalesOrder_.status),
      OrderStatus.PAID
  ));
```

### Bài 7: LEFT JOIN

**Đề:** Truy vấn Customer và chỉ join đơn PAID nhưng vẫn giữ người không có đơn PAID.

**Gợi ý:** `customer.join(Customer_.orders, JoinType.LEFT)` và `join.on(...)`; tránh đặt điều kiện status đơn thuần trong WHERE nếu muốn giữ parent không có child thỏa.

### Bài 8: GreaterThan BigDecimal

**Đề:** Lấy đơn có `totalAmount >= 500000`.

**Gợi ý:**

```java
cb.greaterThanOrEqualTo(
    order.get(SalesOrder_.totalAmount),
    new BigDecimal("500000")
);
```

### Bài 9: Khoảng thời gian

**Đề:** Lọc đơn ở khoảng `[start, end)`.

**Gợi ý:** Hai Predicate `cb.greaterThanOrEqualTo` và `cb.lessThan` trên `SalesOrder_.createdAt`.

### Bài 10: Dynamic filters

**Đề:** Có optional status, minAmount và startTime. Không có filter nào thì trả tối đa 100 đơn.

**Gợi ý:** Tạo `List<Predicate>`, thêm điều kiện khi input khác null, `cb.and(predicates.toArray(new Predicate[0]))` và `setMaxResults(100)`.

### Bài 11: Dynamic ORDER BY an toàn

**Đề:** Client chỉ được chọn `createdAt` hoặc `totalAmount`.

**Gợi ý:** Dùng switch/enum whitelist trả về Path typed; không lấy String field tùy ý từ client.

### Bài 12: Typed result

**Đề:** Chỉ trả danh sách email Customer.

**Gợi ý:**

```java
CriteriaQuery<String> cq =
    cb.createQuery(String.class);
Root<Customer> c = cq.from(Customer.class);
cq.select(c.get(Customer_.email));
```

### Bài 13: DTO

**Đề:** Trả `OrderSummary(id, customerName, amount)` không cần entity managed.

**Gợi ý:** Dùng `cb.construct` với `SalesOrder_.id`, `Customer_.displayName` và `SalesOrder_.totalAmount` sau JOIN.

### Bài 14: COUNT theo status

**Đề:** Đếm số SalesOrder mỗi trạng thái.

**Gợi ý:** `cb.count(order)` kết hợp `groupBy(order.get(SalesOrder_.status))` và `CriteriaQuery<Tuple>`.

### Bài 15: Static metamodel sinh tự động

**Câu hỏi:** Nếu IDE báo `Customer_ cannot be resolved`, cần kiểm tra gì?

**Gợi ý:** Annotation processor, generated source root, JPA namespace, provider version và compile classpath.

### Bài 16: Truy cập metadata runtime

**Đề:** Lấy kiểu Java của thuộc tính email trong mô hình Customer.

**Gợi ý:**

```java
EntityType<Customer> type =
    em.getMetamodel().entity(Customer.class);
Class<?> javaType =
    type.getSingularAttribute("email").getJavaType();
```

### Bài 17: Fetch vs Join

**Câu hỏi:** Dùng `order.fetch(SalesOrder_.customer)` có thể tiếp tục `.get(Customer_.email)` như Join chuẩn không?

**Gợi ý:** Không xem Fetch là Join/Path; dùng `join` cho filter, `fetch` cho fetch plan.

### Bài 18: Reuse Path

**Câu hỏi:** Có nên lưu `Path<String> email` thành singleton để dùng cho mọi request không?

**Gợi ý:** Không. Path phụ thuộc cấu trúc Criteria query đang build.

### Bài 19: Type safety không tuyệt đối

**Đề:** Phân tích `cb.equal(customer.get(Customer_.email), 42)`.

**Gợi ý:** Một số overload CriteriaBuilder chấp nhận Object nên code có thể compile dù kiểu giá trị không phù hợp. Static metamodel không thay test.

### Bài 20: Optional association

**Đề:** Đơn hàng có thể thiếu Customer. Cần giữ các đơn không có Customer khi query.

**Gợi ý:** Xem `JoinType.LEFT` và predicate WHERE; chỉ LEFT JOIN chưa đủ nếu WHERE lọc theo Customer khiến null rows bị loại.

### Bài 21: Refactor persistent field

**Đề:** Đổi `displayName` thành `fullName` nhưng giữ DB column `display_name`.

**Câu hỏi:** Criteria `Customer_.displayName` còn đúng không?

**Gợi ý:** Phải sinh lại metamodel và dùng `Customer_.fullName`; tên column không quyết định tên Path.

### Bài 22: Multi-tenant filter

**Đề:** Entity SalesOrder có `tenantId` và hệ thống nhiều tenant.

**Gợi ý:** Nếu mapping thật sự có thuộc tính này và generated metamodel tương ứng, thêm `cb.equal(order.get(SalesOrder_.tenantId), authorizedTenantId)` từ security context đã xác thực, không nhận tenantId tùy ý từ user.

## 32. Bảng tra cứu nhanh

| Mục đích | Criteria API |
|---|---|
| Tạo builder | `em.getCriteriaBuilder()` |
| Khai báo SELECT Customer | `cb.createQuery(Customer.class)` |
| Root Customer | `cq.from(Customer.class)` |
| Basic path theo String | `c.get("email")` |
| Basic path có kiểu | `c.get(Customer_.email)` |
| Embedded path | `c.get(Customer_.address).get(Address_.city)` |
| Singular association path | `o.get(SalesOrder_.customer).get(Customer_.email)` |
| Join ManyToOne | `o.join(SalesOrder_.customer)` |
| Join List collection | `c.join(Customer_.orders)` |
| LEFT JOIN | `c.join(Customer_.orders, JoinType.LEFT)` |
| Điều kiện trên JOIN | `join.on(predicate)` |
| So sánh bằng | `cb.equal(path, value)` |
| So sánh lớn hơn | `cb.greaterThan(path, value)` |
| Null | `cb.isNull(path)` |
| Chuỗi LIKE | `cb.like(path, pattern)` |
| AND | `cb.and(predicates...)` |
| OR | `cb.or(predicates...)` |
| ORDER BY | `cq.orderBy(cb.desc(path))` |
| Chọn attribute | `cq.select(path)` với đúng result type |
| DISTINCT parent sau JOIN | `cq.distinct(true)` |
| DTO projection | `cb.construct(Dto.class, selections...)` |
| Count | `cb.count(rootOrPath)` |
| Count distinct | `cb.countDistinct(expression)` |
| Grouping | `cq.groupBy(path)` |
| Runtime metamodel | `em.getMetamodel()` |
| Java type của Path | `path.getJavaType()` |
| Type-safe metadata | `Customer_.email` |

## 33. Tổng kết

Khi học Criteria API, hãy nhớ những điều sau:

1. **`Root<T>` là điểm bắt đầu từ entity**, còn **`Path<Y>` là đường dẫn tới thuộc tính kiểu `Y`** trong cây truy vấn.
2. `Path` là **biểu thức của truy vấn**, không phải Java value đọc từ một entity instance.
3. **`get("attributeName")`** tiện cho truy vấn động nhưng tên thuộc tính và kiểu generic có thể sai mà compiler không phát hiện.
4. **`get(Entity_.attribute)`** dùng **static metamodel** để tham chiếu thuộc tính theo Java symbol có kiểu và giúp refactor an toàn hơn.
5. Static metamodel thường do **annotation processor sinh ra**; không nên tự chỉnh generated code. Đồng bộ namespace `jakarta`/`javax` và phiên bản provider.
6. Với thuộc tính `@Embedded` và association đơn, có thể **chaining Path.get(...)** theo mô hình entity.
7. Với collection-valued association, muốn lọc theo thuộc tính phần tử phải dùng **`Join`/`ListJoin`/`SetJoin`/`MapJoin`** thích hợp, không điều hướng collection như một object đơn.
8. **`Join` và `Fetch` khác nhau**: một cái giúp diễn đạt liên kết/điều kiện truy vấn, cái kia điều chỉnh fetch plan.
9. **`Path<T>` có thể đưa vào CriteriaBuilder** để tạo predicate, order, group hoặc selection khi kiểu tương thích.
10. **Static metamodel không đảm bảo mọi lỗi logic/SQL bị bắt ở compile time**; các API như `equal(Expression<?>, Object)` vẫn cần kiểm tra kiểu, provider và integration test.
11. Với query động, **whitelist tên field**, tái sử dụng Path/Join trong cùng query và không truyền thẳng tên field từ user.
12. Query typed không miễn nhiễm với N+1, JOIN duplication, incorrect NULL semantics hay stale persistence context; vẫn cần hiểu SQL và model.
13. Khi chỉ cần vài field, dùng **Tuple/DTO projection** thay vì tải entity graph không cần thiết.
14. Không tái sử dụng Root/Path của một CriteriaQuery sang query khác; mọi node thuộc cấu trúc query đang xây dựng.

**Kết luận:** `Path<T>` là chiếc cầu nối giữa mô hình entity Java và những biểu thức Criteria API, còn **static metamodel** đưa tên thuộc tính và kiểu dữ liệu vào mã Java có thể được trình biên dịch kiểm tra. Thay vì phụ thuộc vào chuỗi `"email"`, `"address"` hay `"totalAmount"` rải rác, bạn có thể viết những truy vấn có cấu trúc như `customer.get(Customer_.address).get(Address_.city)` hoặc `order.get(SalesOrder_.totalAmount)`, giảm sai sót khi refactor và xây bộ lọc động an toàn hơn. Hãy kết hợp đường dẫn có kiểu với JOIN đúng quan hệ, điều kiện có ngữ nghĩa rõ ràng và kiểm thử trên provider/database thật để Criteria API trở thành công cụ truy vấn mạnh, dễ bảo trì trong ứng dụng JPA.
