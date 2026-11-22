# Ánh xạ giá trị vô hướng, thực thể và kết quả nhiều cột

Native SQL cho phép ứng dụng Hibernate/Jakarta Persistence thực thi câu SQL theo cú pháp database, thay vì viết HQL/JPQL. Đây là lựa chọn hữu ích khi cần Common Table Expressions, window functions, JSON operators, các phép tổng hợp đặc thù, SQL đã được tối ưu theo dialect hoặc một báo cáo phức tạp khó biểu đạt bằng entity query.

Nhưng **SQL chạy thành công không đồng nghĩa kết quả đã được ánh xạ đúng vào Java**. Một `ResultSet` có thể chứa một số, vài cột, toàn bộ dữ liệu một entity, hoặc kết quả ghép nhiều entity và scalar. Mỗi trường hợp cần một hợp đồng ánh xạ khác nhau:

- **Scalar**: một giá trị như `email`, `COUNT(*)`, `SUM(total)`.
- **Nhiều scalar**: một hàng gồm `id`, `name`, `total`…; thông thường đọc từ `Object[]` hoặc map thành DTO.
- **Entity**: các cột đầy đủ được hydrate thành object entity managed, có identity trong persistence context.
- **Kết quả hỗn hợp**: entity cùng scalar, hai entity cùng hàng, hoặc một DTO constructor kèm số liệu.
- **Mapping tường minh**: `@SqlResultSetMapping` với `@ColumnResult`, `@EntityResult`, `@FieldResult` và `@ConstructorResult`.
- **API Hibernate-specific**: `NativeQuery.addScalar()`, `addEntity()` và `TupleTransformer`.

Vấn đề thường gặp nhất không nằm ở SQL syntax, mà ở **thiếu cột entity**, **trùng column alias khi JOIN**, **kiểu trả về JDBC khác kiểu Java dự kiến**, **nhầm DTO với managed entity**, hoặc **dựa vào thứ tự cột không được bảo vệ**.

Bài học này đi từ native query đơn giản đến ánh xạ nhiều thành phần, cùng cách kiểm thử, xử lý persistence context và các nguyên tắc sử dụng an toàn.

## 1. Mô hình dữ liệu minh họa

Hệ thống có khách hàng và đơn hàng:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(200) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_no VARCHAR(60) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    total NUMERIC(18, 2) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT fk_purchase_order_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);
```

Dữ liệu mẫu:

**customers**

| id | name | email | status |
| ---: | --- | --- | --- |
| 1 | An | an@example.org | ACTIVE |
| 2 | Bình | binh@example.org | ACTIVE |
| 3 | Chi | chi@example.org | INACTIVE |

**purchase_orders**

| id | order_no | customer_id | total | status |
| ---: | --- | ---: | ---: | --- |
| 101 | PO-101 | 1 | 120.00 | PAID |
| 102 | PO-102 | 1 | 80.50 | DRAFT |
| 103 | PO-103 | 2 | 250.00 | PAID |

Customer Chi chưa có order. Với báo cáo tổng chi tiêu, `Chi` phải xuất hiện với tổng `0.00` nếu nghiệp vụ muốn hiển thị mọi customer.

Entity mẫu:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, unique = true)
    private String email;

    @Column(nullable = false)
    private String status;

    protected Customer() {}

    public Long getId() { return id; }
    public String getName() { return name; }
    public String getEmail() { return email; }
    public String getStatus() { return status; }

    public void rename(String newName) {
        this.name = java.util.Objects.requireNonNull(newName);
    }
}
```

```java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column(name = "order_no", nullable = false)
    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal total;

    @Column(nullable = false)
    private String status;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Version
    private long version;

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public String getOrderNumber() { return orderNumber; }
    public Customer getCustomer() { return customer; }
    public BigDecimal getTotal() { return total; }
}
```

Đây là mô hình minh họa. DDL sinh khóa, loại temporal và cách quản lý timezone cần điều chỉnh theo DBMS/ứng dụng. Các code fragment phía dưới giả định `EntityManager em` đã được tạo, tồn tại trong unit of work phù hợp và dữ liệu seed như bảng trên.

## 2. Từ SQL result set đến Java result

Khi dùng HQL, Hibernate biết rõ entity và attribute:

```hql
select c
from Customer c
where c.status = :status
```

Khi dùng native SQL:

```sql
select id, name, email, status
from customers
where status = ?
```

Hibernate nhận column labels, JDBC types và các rows. Sau đó result mapping quyết định output:

```text
SQL string
     |
     v
Database + JDBC ResultSet
     |
     ├─ columns: id, name, email, ...
     ├─ JDBC types: BIGINT, VARCHAR, NUMERIC, ...
     └─ rows
            |
            v
     Result mapping
        |
        ├─ 1 scalar         -> String / Number / BigDecimal / ...
        ├─ N scalars        -> Object[] / DTO
        ├─ entity           -> managed Customer
        ├─ entity + scalar  -> Object[] { Customer, Long }
        └─ 2 entities       -> Object[] { Customer, PurchaseOrder }
```

Một query chọn hai cột **không tự trở thành một entity đầy đủ**. Ngược lại, nếu ánh xạ thành entity, kết quả không còn chỉ là một mảng dữ liệu vô hướng mà tham gia vào cơ chế persistence context.

## 3. Các overload `createNativeQuery()`

Ba dạng JPA phổ biến:

```java
Query q1 = em.createNativeQuery(sql);

Query q2 = em.createNativeQuery(sql, Customer.class);

Query q3 = em.createNativeQuery(sql, "CustomerMapping");
```

| Lời gọi | Ý định |
| --- | --- |
| `createNativeQuery(sql)` | Dùng kết quả scalar/multi-scalar theo mapping mặc định |
| `createNativeQuery(sql, Customer.class)` | Ánh xạ mỗi row thành `Customer` entity |
| `createNativeQuery(sql, "CustomerMapping")` | Sử dụng `@SqlResultSetMapping` đã đăng ký |

Các phiên bản JPA mới có thể thêm typed overload cho một số kiểu result; không nên sao chép code dựa vào overload của một major version khác mà chưa xem API trong dự án.

### 3.1. `getResultList()` và `getSingleResult()`

```java
List<?> rows = em.createNativeQuery(
    "select name from customers"
).getResultList();
```

`getResultList()` cho danh sách có 0..N hàng.

```java
Object value = em.createNativeQuery(
    "select name from customers where id = ?"
).setParameter(1, 1L).getSingleResult();
```

`getSingleResult()` mong đợi đúng một hàng; có thể ném `NoResultException` hoặc `NonUniqueResultException`.

Lưu ý một hàng có **giá trị SQL NULL** khác với **không có hàng nào**.

### 3.2. Parameter binding trong native SQL

Ví dụ positional parameter:

```java
List<?> rows = em.createNativeQuery("""
    select id, name
    from customers
    where status = ?
      and id > ?
    """)
    .setParameter(1, "ACTIVE")
    .setParameter(2, 0L)
    .getResultList();
```

Trong ứng dụng cần tính portable giữa JPA providers, nên dùng positional binding cho native SQL. Hibernate có hỗ trợ named parameters trong nhiều trường hợp, nhưng không lấy khả năng mở rộng này làm bảo đảm của mọi provider.

Giá trị có thể bind, nhưng **tên bảng, tên cột, function name, hướng ORDER BY** là cấu trúc SQL, không phải value parameters. Những lựa chọn này cần whitelist.

## 4. Kết quả vô hướng: một cột

Native query:

```sql
select email from customers where id = ?
```

Java:

```java
String email = (String) em.createNativeQuery("""
    select email
    from customers
    where id = ?
    """)
    .setParameter(1, 1L)
    .getSingleResult();
```

Với cột `VARCHAR`, JDBC thường trả `String`.

Ví dụ `COUNT(*)`:

```java
Object raw = em.createNativeQuery("""
    select count(*)
    from customers
    where status = ?
    """)
    .setParameter(1, "ACTIVE")
    .getSingleResult();

long count = ((Number) raw).longValue();
```

Tại sao không cast thẳng sang `Long`? Một số JDBC/dialect/provider có thể dùng `BigInteger`, `BigDecimal`, `Long` hoặc một kiểu số khác cho aggregate. Nếu chưa khai báo mapping tường minh, `Number` thường là cách xử lý số đếm linh hoạt hơn.

### 4.1. Đừng chuyển tiền tệ thành số nguyên

```java
Object raw = em.createNativeQuery(
    "select sum(total) from purchase_orders"
).getSingleResult();
```

Nếu kết quả là `BigDecimal("450.50")`, gọi:

```java
((Number) raw).longValue();
```

sẽ mất phần lẻ. Với tiền tệ, nên giữ `BigDecimal` và kiểu SQL `NUMERIC/DECIMAL` thích hợp.

### 4.2. Aggregate và tập rỗng

- `COUNT(*)` trên tập rỗng thường trả `0`.
- `SUM(column)` trên tập rỗng thường trả `NULL`.
- `AVG(column)` có thể trả `NULL`.
- `MIN`/`MAX` không có row phù hợp có thể trả `NULL`.

Nếu domain muốn tổng bằng 0:

```sql
select coalesce(sum(total), 0) as total_spent
from purchase_orders
```

Không dùng `COALESCE` mù quáng nếu `NULL` mang ý nghĩa nghiệp vụ khác 0.

## 5. Nhiều cột: `Object[]`

Query:

```sql
select id, name, email
from customers
where status = ?
order by id
```

Đọc kết quả:

```java
List<?> rawRows = em.createNativeQuery("""
    select id, name, email
    from customers
    where status = ?
    order by id
    """)
    .setParameter(1, "ACTIVE")
    .getResultList();

for (Object value : rawRows) {
    Object[] row = (Object[]) value;

    long id = ((Number) row[0]).longValue();
    String name = (String) row[1];
    String email = (String) row[2];

    System.out.println(id + " / " + name + " / " + email);
}
```

Vị trí phụ thuộc thứ tự `SELECT`:

```text
SELECT id, name, email
        |    |      |
        v    v      v
row[0]  row[1]  row[2]
```

Nếu đổi query thành `select email, id, name`, code phía trên sẽ đọc sai. Một mapping DTO rõ ràng bền vững hơn khi query có nhiều nơi dùng.

### 5.1. Một cột không luôn là `Object[]`

Nếu query giảm từ ba cột xuống một cột:

```sql
select id from customers
```

mỗi row thông thường là scalar `Number`, **không phải `Object[]` độ dài 1** theo mapping native query mặc định. Không viết mapper luôn cast `Object[]` mà không xét result shape.

### 5.2. Column labels và vị trí là hai khái niệm

Trong raw `Object[]`, code thường đọc theo vị trí. Nhưng trong `@SqlResultSetMapping`, `addScalar` hoặc tuple transformer, **SQL column alias** trở thành một phần của contract. Dù chưa dùng mapping theo alias, đặt alias rõ vẫn hữu ích cho refactor và kiểm tra SQL.

## 6. Trả entity managed bằng `resultClass`

Khi SQL select **đủ các cột entity**:

```java
Customer customer = (Customer) em.createNativeQuery("""
    select id, name, email, status
    from customers
    where id = ?
    """, Customer.class)
    .setParameter(1, 1L)
    .getSingleResult();
```

Hibernate dùng metadata entity để hydrate `Customer`.

| SQL column | Java property |
| --- | --- |
| `id` | `Customer.id` |
| `name` | `Customer.name` |
| `email` | `Customer.email` |
| `status` | `Customer.status` |

Object kết quả là entity được provider quản lý trong persistence context nếu entity result được ánh xạ thành công. Do đó:

```java
customer.rename("Tên mới");
em.flush();
```

có thể tạo `UPDATE` bằng dirty checking khi đang trong transaction hợp lệ.

### 6.1. Entity mapping cần đủ dữ liệu

Nếu viết:

```java
em.createNativeQuery(
    "select id, name from customers",
    Customer.class
);
```

trong khi `Customer` còn `email` và `status`, query **không cung cấp đầy đủ state entity**. Kết quả khi thiếu các cột ánh xạ là không xác định theo đặc tả; thực tế thường gây lỗi hydration hoặc alias/column lookup.

Khi entity phức tạp, cần tính đến:

- Primary key và composite identifier components.
- Basic fields.
- Foreign key columns cho những quan hệ to-one thuộc state entity.
- Cột `@Version`.
- `@Embedded`/`@EmbeddedId`.
- Cột discriminator cho inheritance.
- Cột ánh xạ từ secondary tables hoặc các mapping đặc biệt.

Chỉ muốn `id, name`? Hãy dùng DTO/scalar projection, không yêu cầu partial managed entity.

### 6.2. Entity result và DTO khác nhau

| Đặc điểm | Entity result | DTO/scalar result |
| --- | --- | --- |
| Object tham gia persistence context | Có, theo entity mapping | Không |
| Identity map theo PK | Có | Không |
| Dirty checking | Có nếu managed | Không |
| Phải có đủ entity columns | Có | Chỉ các cột projection cần |
| Có thể có lazy associations | Có | Không, trừ khi tự chứa entity |
| Thích hợp cập nhật trong transaction | Có | Không trực tiếp |
| Thích hợp báo cáo chỉ đọc | Có thể nhưng thường nặng hơn | Thường phù hợp |

## 7. Vì sao không nên `SELECT *` trên nhiều bảng?

Với một bảng đơn giản:

```sql
select * from customers where id = ?
```

có thể đủ cột để Hibernate tạo Customer.

Nhưng khi JOIN:

```sql
select *
from customers c
join purchase_orders o on o.customer_id = c.id
```

hai bảng cùng có `id`, `status`. ResultSet có column labels trùng nhau, dễ dẫn đến lỗi **duplicate discovered SQL alias** hoặc ambiguity khi mapping entity.

Nên chọn cột và alias tường minh:

```sql
select
    c.id as c_id,
    c.name as c_name,
    c.email as c_email,
    c.status as c_status,
    o.id as o_id,
    o.order_no as o_order_no,
    o.customer_id as o_customer_id,
    o.total as o_total,
    o.status as o_status,
    o.created_at as o_created_at,
    o.version as o_version
from customers c
join purchase_orders o
  on o.customer_id = c.id
```

Đặt alias độc nhất đặc biệt quan trọng khi dùng nhiều `@EntityResult` hoặc ánh xạ theo tên cột.

## 8. `@SqlResultSetMapping`: khai báo kết quả

JPA hỗ trợ khai báo:

```java
@SqlResultSetMapping(
    name = "SomeMapping",
    entities = { ... },
    classes = { ... },
    columns = { ... }
)
```

Ba nhóm:

| Thành phần | Annotation bên trong | Ý nghĩa |
| --- | --- | --- |
| `entities` | `@EntityResult` | Ánh xạ row thành entity |
| `classes` | `@ConstructorResult` | Gọi constructor Java, thường tạo DTO |
| `columns` | `@ColumnResult` | Ánh xạ scalar columns |

`@SqlResultSetMapping` được khai báo trên một managed type như entity và được đăng ký trong persistence unit; không nhất thiết đặt mapping trên DTO class.

### 8.1. Result shape và thứ tự array

Nếu mapping có **đúng một** result mapping component (một EntityResult, một ConstructorResult hoặc một ColumnResult), mỗi row là trực tiếp entity/DTO/scalar tương ứng.

Nếu mapping gồm **nhiều components**, mỗi row là `Object[]`. Theo Jakarta Persistence 3.2, thứ tự là:

1. Entity results theo thứ tự khai báo trong `entities`.
2. Constructor results theo thứ tự khai báo trong `classes`.
3. Scalar results theo thứ tự khai báo trong `columns`.

**Thứ tự của `Object[]` là thứ tự mapping components, không được suy từ thứ tự SELECT columns**. Cần phân biệt “thứ tự cột dùng để hydrate từng component” và “thứ tự components trong kết quả hàng”.

## 9. `@ColumnResult` cho scalar có kiểu tường minh

SQL:

```sql
select count(*) as paid_order_count
from purchase_orders
where status = ?
```

Khai báo trên entity:

```java
@SqlResultSetMapping(
    name = "PaidOrderCountMapping",
    columns = {
        @ColumnResult(
            name = "paid_order_count",
            type = Long.class
        )
    }
)
@Entity
@Table(name = "customers")
public class Customer {
    // Entity fields...
}
```

Thực thi:

```java
Object value = em.createNativeQuery("""
    select count(*) as paid_order_count
    from purchase_orders
    where status = ?
    """, "PaidOrderCountMapping")
    .setParameter(1, "PAID")
    .getSingleResult();

long count = ((Number) value).longValue();
```

`name` là tên **cột trong result set**, tức SQL column label/alias. `type` yêu cầu kiểu Java scalar theo mapping.

Nếu SQL trả `"abc"` mà mapping chọn `Long.class`, nó không tự trở thành số hợp lệ; cần sửa SQL/type.

### 9.1. Mapping hai scalar

```java
@SqlResultSetMapping(
    name = "CustomerIdAndName",
    columns = {
        @ColumnResult(name = "customer_id", type = Long.class),
        @ColumnResult(name = "customer_name", type = String.class)
    }
)
```

SQL:

```sql
select id as customer_id, name as customer_name
from customers
```

Vì mapping gồm hai scalar components, mỗi row là:

```text
Object[]
  [0] Long customerId
  [1] String customerName
```

Không có managed Customer nào được hydrate.

## 10. `@EntityResult` và `@FieldResult`

Khi SQL alias khác tên cột entity thông thường:

```sql
select
    c.id as c_id,
    c.name as c_name,
    c.email as c_email,
    c.status as c_status
from customers c
```

Khai báo mapping:

```java
@SqlResultSetMapping(
    name = "CustomerAliasEntity",
    entities = {
        @EntityResult(
            entityClass = Customer.class,
            fields = {
                @FieldResult(name = "id", column = "c_id"),
                @FieldResult(name = "name", column = "c_name"),
                @FieldResult(name = "email", column = "c_email"),
                @FieldResult(name = "status", column = "c_status")
            }
        )
    }
)
```

- `@FieldResult.name`: tên persistent Java field/property.
- `@FieldResult.column`: SQL result column label/alias.
- `@EntityResult.entityClass`: loại entity cần hydrate.

Dùng mapping:

```java
List<?> rows = em.createNativeQuery("""
    select c.id as c_id,
           c.name as c_name,
           c.email as c_email,
           c.status as c_status
    from customers c
    where c.status = ?
    order by c.id
    """, "CustomerAliasEntity")
    .setParameter(1, "ACTIVE")
    .getResultList();

for (Object value : rows) {
    Customer customer = (Customer) value;
    System.out.println(customer.getName());
}
```

Vì chỉ có một `EntityResult`, mỗi row là Customer, không phải mảng có một phần tử.

### 10.1. FieldResult và association FK

Nếu entity có:

```java
@ManyToOne
@JoinColumn(name = "customer_id")
private Customer customer;
```

thì khi ánh xạ entity PurchaseOrder, SQL vẫn cần chọn `customer_id` nếu nó thuộc persistent state. Có thể ánh xạ FK alias bằng:

```java
@FieldResult(name = "customer", column = "o_customer_id")
```

Với composite foreign key hoặc embedded path, cần nhiều field mappings và quy tắc tên của JPA tương ứng; không giả định một column alias đủ cho mọi quan hệ.

## 11. `@ConstructorResult`: DTO theo constructor

Record:

```java
package com.example.dto;

import java.math.BigDecimal;

public record CustomerSpendRow(
    Long customerId,
    String customerName,
    BigDecimal totalSpent
) {}
```

SQL báo cáo:

```sql
select
    c.id as customer_id,
    c.name as customer_name,
    coalesce(sum(o.total), 0) as total_spent
from customers c
left join purchase_orders o
  on o.customer_id = c.id
group by c.id, c.name
order by c.id
```

Mapping:

```java
@SqlResultSetMapping(
    name = "CustomerSpendDto",
    classes = {
        @ConstructorResult(
            targetClass = com.example.dto.CustomerSpendRow.class,
            columns = {
                @ColumnResult(
                    name = "customer_id", type = Long.class
                ),
                @ColumnResult(
                    name = "customer_name", type = String.class
                ),
                @ColumnResult(
                    name = "total_spent", type = BigDecimal.class
                )
            }
        )
    }
)
```

Thực thi:

```java
List<?> rows = em.createNativeQuery("""
    select c.id as customer_id,
           c.name as customer_name,
           coalesce(sum(o.total), 0) as total_spent
    from customers c
    left join purchase_orders o
      on o.customer_id = c.id
    group by c.id, c.name
    order by c.id
    """, "CustomerSpendDto")
    .getResultList();

for (Object value : rows) {
    CustomerSpendRow row = (CustomerSpendRow) value;

    System.out.println(
        row.customerName() + ": " + row.totalSpent()
    );
}
```

Kết quả mong đợi:

```text
An: 200.50
Bình: 250.00
Chi: 0.00
```

### 11.1. Thứ tự các `ColumnResult` phải khớp constructor

Constructor nhận:

```text
(Long customerId, String customerName, BigDecimal totalSpent)
```

Do đó `@ConstructorResult.columns` phải khai báo theo đúng thứ tự này, dù SQL select columns ở thứ tự khác.

Không giả định provider tìm constructor bằng **tên tham số**. Nó dựa trên danh sách cột và kiểu/vị trí constructor.

### 11.2. DTO không phải managed entity

Đối tượng `CustomerSpendRow` là một value object phục vụ đọc, không tham gia dirty checking. Hibernate không gọi UPDATE nếu ứng dụng tạo một DTO mới.

Trường hợp đặc biệt: `@ConstructorResult(targetClass=SomeEntity.class)` không tự tạo managed entity như `@EntityResult`. Đặc tả nói entity object được tạo theo constructor result có thể ở trạng thái **new hoặc detached**, tùy primary key có được cấp không. Vì vậy không dùng ConstructorResult để dựng một “partial managed entity”.

## 12. Kết hợp entity và scalar

Yêu cầu: trả một managed `Customer` và số đơn hàng của khách hàng đó.

SQL:

```sql
select
    c.id as c_id,
    c.name as c_name,
    c.email as c_email,
    c.status as c_status,
    count(o.id) as order_count
from customers c
left join purchase_orders o on o.customer_id = c.id
group by c.id, c.name, c.email, c.status
order by c.id
```

Mapping:

```java
@SqlResultSetMapping(
    name = "CustomerWithOrderCount",
    entities = {
        @EntityResult(
            entityClass = Customer.class,
            fields = {
                @FieldResult(name = "id", column = "c_id"),
                @FieldResult(name = "name", column = "c_name"),
                @FieldResult(name = "email", column = "c_email"),
                @FieldResult(name = "status", column = "c_status")
            }
        )
    },
    columns = {
        @ColumnResult(
            name = "order_count", type = Long.class
        )
    }
)
```

Đọc:

```java
List<?> result = em.createNativeQuery(sql, "CustomerWithOrderCount")
    .getResultList();

for (Object value : result) {
    Object[] row = (Object[]) value;

    Customer customer = (Customer) row[0];
    long count = ((Number) row[1]).longValue();

    System.out.println(customer.getName() + ": " + count);
}
```

Mỗi row chứa `[Customer managed, Long orderCount]`. Theo dữ liệu mẫu: An = 2, Bình = 1, Chi = 0.

### 12.1. Vì sao dùng `count(o.id)`?

Với `LEFT JOIN`, customer không có order vẫn tạo một row mở rộng NULL ở phía order.

- `COUNT(o.id)` đếm 0 nếu không có order.
- `COUNT(*)` đếm cả null-extended row, có thể ra 1.

Vì vậy chọn `count(o.id)` nếu mục tiêu là số order thực tế.

### 12.2. Mixed result không đổi lifecycle của entity

Scalar `order_count` không phải field của Customer. Nó không được Hibernate tự đồng bộ sau khi một order khác được tạo. Nếu cần số liệu mới, phải query lại phù hợp với transaction isolation và cache.

## 13. Hai entity trong cùng row

Khi query JOIN Customer và PurchaseOrder, một row có thể chứa hai entity.

SQL cần đủ tất cả cột mapped của mỗi entity và aliases riêng:

```sql
select
    c.id as c_id,
    c.name as c_name,
    c.email as c_email,
    c.status as c_status,
    o.id as o_id,
    o.order_no as o_order_no,
    o.customer_id as o_customer_id,
    o.total as o_total,
    o.status as o_status,
    o.created_at as o_created_at,
    o.version as o_version
from customers c
join purchase_orders o on o.customer_id = c.id
order by c.id, o.id
```

Mapping:

```java
@SqlResultSetMapping(
    name = "CustomerAndOrder",
    entities = {
        @EntityResult(
            entityClass = Customer.class,
            fields = {
                @FieldResult(name = "id", column = "c_id"),
                @FieldResult(name = "name", column = "c_name"),
                @FieldResult(name = "email", column = "c_email"),
                @FieldResult(name = "status", column = "c_status")
            }
        ),
        @EntityResult(
            entityClass = PurchaseOrder.class,
            fields = {
                @FieldResult(name = "id", column = "o_id"),
                @FieldResult(
                    name = "orderNumber", column = "o_order_no"
                ),
                @FieldResult(
                    name = "customer", column = "o_customer_id"
                ),
                @FieldResult(name = "total", column = "o_total"),
                @FieldResult(name = "status", column = "o_status"),
                @FieldResult(
                    name = "createdAt", column = "o_created_at"
                ),
                @FieldResult(name = "version", column = "o_version")
            }
        )
    }
)
```

Thực thi:

```java
List<?> raw = em.createNativeQuery(sql, "CustomerAndOrder")
    .getResultList();

for (Object value : raw) {
    Object[] row = (Object[]) value;

    Customer customer = (Customer) row[0];
    PurchaseOrder order = (PurchaseOrder) row[1];
}
```

Vì hai `EntityResult`, mỗi row có `Object[]` gồm hai entity.

### 13.1. Một Customer có thể xuất hiện ở nhiều SQL rows

Dữ liệu mẫu:

```text
Customer#1 | Order#101
Customer#1 | Order#102
Customer#2 | Order#103
```

Trong cùng persistence context, Hibernate thường dùng **một managed Customer instance** cho identity `(Customer, 1)`, dù SQL trả Customer#1 ở hai result rows.

Không nhầm:
- Số SQL rows.
- Số phần tử list kết quả.
- Số distinct entity identities.
- Số Java instances managed trong persistence context.

Nếu cần một customer duy nhất kèm danh sách orders, có thể group DTO rows trong Java hoặc dùng fetch plan/JPQL khác; không mặc định native result mapping hai entity đã xây hoàn chỉnh collection owner.

## 14. Mapping entity + DTO + scalar

`@SqlResultSetMapping` cho phép các nhóm `entities`, `classes`, `columns` cùng tồn tại.

Ví dụ nếu mapping có:

```text
entities = [Customer]
classes  = [CustomerSpendRow]
columns  = [rank_no, order_count]
```

mỗi row được đóng gói theo thứ tự:

```text
row[0] = Customer managed
row[1] = CustomerSpendRow DTO
row[2] = rank_no scalar
row[3] = order_count scalar
```

Đây là thứ tự **mapping components**. Thứ tự SQL SELECT thực tế có thể khác miễn mỗi alias trỏ đúng cột và constructor arguments đúng thứ tự.

Hãy tránh trộn quá nhiều component nếu UI chỉ cần một DTO: result shape phức tạp làm tăng rủi ro cast sai. Chỉ nên kết hợp entity và scalar khi use case thực sự cần **managed entity cùng thông tin tổng hợp**.

## 15. `@NamedNativeQuery` và mapping đã đăng ký

Khi native SQL có tính ổn định và được dùng lại, có thể đặt tên:

```java
@NamedNativeQuery(
    name = "Customer.spendReport",
    query = """
        select c.id as customer_id,
               c.name as customer_name,
               coalesce(sum(o.total), 0) as total_spent
        from customers c
        left join purchase_orders o
          on o.customer_id = c.id
        group by c.id, c.name
        order by c.id
        """,
    resultSetMapping = "CustomerSpendDto"
)
@Entity
@Table(name = "customers")
public class Customer {
    // Fields...
}
```

Dùng:

```java
List<?> results = em.createNamedQuery("Customer.spendReport")
    .getResultList();
```

Đặt `@SqlResultSetMapping` và `@NamedNativeQuery` trên managed type/metadata được provider scan. Đừng chỉ đặt trên record DTO rồi mong ORM tự đăng ký như entity metadata.

Tên mapping cần duy nhất trong persistence unit và đủ rõ, ví dụ `CustomerSpendDto`, `CustomerAndOrder`.

## 16. API Hibernate `NativeQuery.addScalar()`

Khi không muốn định nghĩa annotation cố định, Hibernate hỗ trợ mapping programmatically:

```java
import org.hibernate.Session;
import org.hibernate.query.NativeQuery;

Session session = em.unwrap(Session.class);

NativeQuery<?> query = session.createNativeQuery("""
    select c.id as customer_id,
           c.name as customer_name
    from customers c
    where c.status = :status
    order by c.id
    """);

query.addScalar("customer_id", Long.class);
query.addScalar("customer_name", String.class);
query.setParameter("status", "ACTIVE");

List<?> rows = query.getResultList();
```

Đây là Hibernate-specific, không phải JPA portable. Kết quả là hai scalar theo các aliases đã khai báo, thường đóng gói `Object[]` mỗi row.

### 16.1. Lợi ích của `addScalar`

- Xác định column aliases cần đọc.
- Khai báo Java type tương ứng.
- Hạn chế phụ thuộc vào suy luận từ JDBC metadata.
- Hữu ích với aggregate, custom SQL functions và vendor types.
- Tránh tạo annotation mapping dùng một lần nếu codebase đã phụ thuộc Hibernate.

Các overload nhận `Class`, basic type hoặc type reference có thể khác theo Hibernate version. Hãy dùng Javadoc của đúng Hibernate major version.

### 16.2. `addScalar` không tạo entity

Mapping:

```java
query.addScalar("customer_id", Long.class);
query.addScalar("customer_name", String.class);
```

không tạo một managed `Customer`, dù hai scalar có cùng tên với thuộc tính entity.

## 17. API Hibernate `NativeQuery.addEntity()`

Hibernate cũng cho khai báo entity result:

```java
Session session = em.unwrap(Session.class);

NativeQuery<?> query = session.createNativeQuery("""
    select id, name, email, status
    from customers
    where status = :status
    """);

query.addEntity(Customer.class);
query.setParameter("status", "ACTIVE");

List<?> customers = query.getResultList();
```

Tương tự `resultClass=Customer.class`, Hibernate hydrate entity. Cần chọn đầy đủ persistent state.

Có các overload `addEntity` nhận table alias/entity name phù hợp với SQL join phức tạp. Khi dùng nhiều entity returns, hãy đọc Javadoc và bảo đảm aliases độc nhất, tránh `SELECT c.*, o.*` tạo trùng labels.

### 17.1. Khi nào chọn JPA mapping hay Hibernate API?

| Nhu cầu | Chọn |
| --- | --- |
| Portable, mapping cố định và tái sử dụng | `@SqlResultSetMapping` |
| Entity đơn giản, full columns | `createNativeQuery(sql, Entity.class)` |
| Mapping scalar linh hoạt | Hibernate `addScalar` |
| Query SQL thay đổi hình dạng theo use case | Hibernate result mapping/transformer |
| Hai entity + scalar với aliases ổn định | `@EntityResult` + `@ColumnResult` |
| Báo cáo chỉ đọc | DTO `@ConstructorResult` hoặc mapper rõ ràng |

## 18. `TupleTransformer` để tạo DTO

Hibernate có `TupleTransformer` cho mỗi row. Ví dụ:

```java
import org.hibernate.Session;
import org.hibernate.query.NativeQuery;

Session session = em.unwrap(Session.class);

NativeQuery<?> query = session.createNativeQuery("""
    select c.id as customer_id,
           c.name as customer_name,
           coalesce(sum(o.total), 0) as total_spent
    from customers c
    left join purchase_orders o
      on o.customer_id = c.id
    group by c.id, c.name
    """);

query.addScalar("customer_id", Long.class);
query.addScalar("customer_name", String.class);
query.addScalar("total_spent", BigDecimal.class);

var mappedQuery = query.setTupleTransformer(
    (tuple, aliases) -> new CustomerSpendRow(
        ((Number) tuple[0]).longValue(),
        (String) tuple[1],
        (BigDecimal) tuple[2]
    )
);

List<?> rows = mappedQuery.getResultList();
```

Mỗi phần tử là DTO theo transformer. Exact generic signature có thể khác theo Hibernate version; ví dụ tập trung vào ý tưởng callback nhận `tuple` và `aliases`.

### 18.1. Dùng aliases cẩn thận

`aliases` biểu diễn label/alias của các cột được mapping. Có thể dùng để xác định vị trí:

```java
Map<String, Integer> indexByAlias = new HashMap<>();
for (int i = 0; i < aliases.length; i++) {
    indexByAlias.put(aliases[i], i);
}
```

Nhưng phải bảo đảm alias không trùng, không null ngoài dự kiến và xử lý case folding của driver/database.

`TupleTransformer` làm việc với **từng row**, còn một số Hibernate API như `ResultListTransformer` biến đổi cả danh sách. Không cần dùng transformer phức tạp nếu `@ConstructorResult` đáp ứng đủ.

## 19. JPA `Tuple`, Map và tính portable

Trong JPQL/Criteria, `Tuple` giúp truy xuất các projection theo alias/type. Native SQL với result type `Tuple` có thể được Hibernate hỗ trợ ở một số overload/version, nhưng **không nên xem đó là contract portable giống nhau ở mọi JPA provider**.

Với native query không khai báo mapper:

```java
Object row = em.createNativeQuery(
    "select id, name from customers"
).getResultList().get(0);
```

đừng tự ý cast:

```java
Map<String, Object> map = (Map<String, Object>) row;
```

Mapping mặc định của JPA không tự biến mỗi row thành map theo column names.

Muốn map by alias, dùng transformer, adapter JDBC hoặc projection mapping được hỗ trợ rõ trong stack.

## 20. Kiểu JDBC và kiểu Java

Một giá trị đi qua nhiều lớp:

```text
SQL type: NUMERIC(18,2)
     |
     v
JDBC metadata/extraction
     |
     v
Hibernate basic type / result mapping
     |
     v
Java BigDecimal
```

Không trộn ba khái niệm:

- SQL database type: `BIGINT`, `NUMERIC`, `DATE`, `TIMESTAMP`, `JSONB`...
- JDBC type code/driver representation.
- Java type: `Long`, `BigDecimal`, `LocalDateTime`, `UUID`, `String`...

### 20.1. Số và tiền tệ

`COUNT`/`SUM` có thể được provider suy luận ra Java numeric types khác theo SQL expression và dialect.

- Số đếm: `Number.longValue()` khi giá trị nằm trong phạm vi an toàn.
- Tiền: giữ `BigDecimal` và precision/scale, tránh `double`.
- Decimal aggregate: cần kiểm tra `SUM`/`AVG` type derivation.
- DTO constructor: khai báo `@ColumnResult(type=BigDecimal.class)` khi cần type rõ.

### 20.2. Date/time và timezone

`TIMESTAMP` trong raw scalar query có thể được JDBC trả thành `java.sql.Timestamp` hoặc kiểu Java time phù hợp tùy provider/version. Không ép thẳng sang `LocalDateTime` khi chưa biết type thực tế.

`TIMESTAMP WITH TIME ZONE`, `Instant`, `OffsetDateTime` và `LocalDateTime` không có cùng ngữ nghĩa. Khi xây DTO, kiểm tra mapping và timezone policy của application/database.

### 20.3. Boolean, enum, UUID, JSON

- `BOOLEAN`/`BIT`/`SMALLINT` có thể tạo Java type khác.
- Enum entity dùng `@Enumerated`/converter, raw scalar thường phản ánh DB representation nếu không khai báo converter/type.
- UUID có thể là native DB UUID, binary hoặc VARCHAR.
- JSON vendor type có thể trả `String`, driver object hoặc Hibernate type được cấu hình.
- LOB/array có thể cần lifecycle JDBC/streaming riêng.

**Entity result mapping** có metadata attribute/converter. **Raw scalar** không mặc nhiên biết một column label vốn thuộc converter của entity field nào.

## 21. NULL và OUTER JOIN trong kết quả nhiều cột

Ví dụ:

```sql
select c.id as customer_id,
       o.total as order_total
from customers c
left join purchase_orders o on o.customer_id = c.id
```

Customer Chi không có order, nên `order_total` là NULL.

```java
Object[] row = (Object[]) value;

long customerId = ((Number) row[0]).longValue();
BigDecimal total = (BigDecimal) row[1]; // Có thể null.
```

Không viết:

```java
long total = ((Number) row[1]).longValue();
```

nếu cột có thể null: sẽ lỗi `NullPointerException`, chưa kể mất phần thập phân.

DTO thường nên dùng wrapper/nullable type cho scalar ngoài join. Nếu domain cần mặc định 0, dùng `coalesce` có chủ đích.

## 22. Inheritance, discriminator và embedded state

Một entity hierarchy:

```java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "payment_type")
public abstract class Payment {
    @Id
    private Long id;
}
```

Khi native SQL trả `Payment`, provider cần đủ metadata để xác định concrete subtype. `@EntityResult` có thuộc tính:

```java
@EntityResult(
    entityClass = Payment.class,
    discriminatorColumn = "p_type",
    fields = {
        @FieldResult(name = "id", column = "p_id")
    }
)
```

SQL phải select `payment_type AS p_type` và các persistent columns liên quan. Snippet là cấu trúc minh họa, **không phải mapping đầy đủ** cho một hierarchy thật.

Với `JOINED` inheritance, secondary tables, composite IDs hoặc embedded state, mapping càng phức tạp. Đừng chỉ chọn base ID rồi trông chờ ORM tự xác định mọi cột subtype.

## 23. Native entity result và first-level cache

Nếu cùng một `EntityManager` đã quản lý Customer#1:

```java
Customer byFind = em.find(Customer.class, 1L);

Customer byNative = (Customer) em.createNativeQuery("""
    select id, name, email, status
    from customers
    where id = ?
    """, Customer.class)
    .setParameter(1, 1L)
    .getSingleResult();

System.out.println(byFind == byNative); // Thường true.
```

Persistence context bảo đảm identity map: cùng persistent key được biểu diễn bằng một managed instance trong context.

Vì vậy:

- Native SQL vẫn có thể chạy để xác định hàng trả về.
- Provider có thể tái sử dụng managed instance thay vì tạo object thứ hai.
- Không mặc định native SELECT **ghi đè trạng thái đã managed** bằng dữ liệu vừa query.
- Nếu cần đọc lại DB state, dùng `refresh()` trong transaction/isolation phù hợp.
- DTO/scalar result không có cùng identity-map semantics.

### 23.1. DTO không được Hibernate dirty-check

```java
CustomerSpendRow row = ...;
```

DTO không tự tạo SQL UPDATE khi giá trị thay đổi. Đối với báo cáo lớn, đây là ưu điểm: không cần quản lý nhiều entity trong L1 cache.

## 24. Native query, flush và query synchronization

Một transaction có pending changes:

```java
Customer customer = em.find(Customer.class, 1L);
customer.rename("Tên mới");

Object value = em.createNativeQuery(
    "select name from customers where id = ?"
).setParameter(1, 1L).getSingleResult();
```

Native query nhìn thấy state mới hay cũ có thể phụ thuộc flush mode, API dùng để bootstrap Hibernate (JPA `EntityManager` hay native `Session`), version và query synchronization.

Nếu business cần chắc đã gửi pending DML:

```java
em.flush();
Object value = em.createNativeQuery(
    "select name from customers where id = ?"
).setParameter(1, 1L).getSingleResult();
```

**Flush không phải commit**: DML vẫn có thể rollback trong transaction.

Hibernate `NativeQuery` có các API như `addSynchronizedEntityClass()` để thông báo những entity spaces liên quan, phục vụ auto flush/query cache synchronization theo semantics phiên bản. Không mặc định native SQL luôn tự biết các bảng bị ảnh hưởng.

## 25. Native DML khác native entity SELECT

Native UPDATE:

```java
int affected = em.createNativeQuery("""
    update customers
    set status = ?
    where id = ?
    """)
    .setParameter(1, "INACTIVE")
    .setParameter(2, 1L)
    .executeUpdate();
```

thực thi trực tiếp tại database, **không đi qua dirty checking từng managed Customer** như sửa field entity bình thường.

Nếu trước đó `Customer#1` đã nằm trong L1 cache, status trong object có thể vẫn cũ. Cần kế hoạch `flush()`, `refresh()`/`clear()` và transaction boundaries phù hợp.

Nếu entity có `@Version`, native bulk SQL không tự tăng version hoặc kiểm tra version giống Hibernate-managed entity update. Mọi write paths cần thống nhất cơ chế concurrency control.

Không gọi `clear()` tùy tiện khi còn pending changes chưa flush: có thể làm mất thay đổi Java chưa được đồng bộ.

## 26. Pagination và nhiều rows cho một entity

JPA cho phép:

```java
List<?> page = em.createNativeQuery("""
    select id, name, email, status
    from customers
    order by id
    """, Customer.class)
    .setFirstResult(20)
    .setMaxResults(10)
    .getResultList();
```

Hibernate/dialect áp dụng pagination theo SQL capability. Luôn có `ORDER BY` ổn định khi phân trang; không phụ thuộc thứ tự vật lý của bảng.

Nếu query JOIN customers với orders, một customer có thể xuất hiện trên nhiều SQL rows. Giới hạn SQL rows không tương đương giới hạn **distinct customers**.

Một phương án:

1. Query IDs của root entity ở trang cần xem.
2. Query chi tiết/DTO cho những IDs đó.
3. Giữ lại thứ tự page bằng sorting/reorder.
4. Xây count query riêng với `count(distinct root.id)` hoặc EXISTS đúng semantics.

Đừng tạo một native query fetch toàn bộ entity graph chỉ để lấy hai cột cho màn hình summary.

## 27. DTO mapper thủ công khi chỉ có vài cột

Cho query nhỏ, `Object[]` có thể được chuyển sang record trong Java:

```java
public record SimpleCustomerRow(
    Long id,
    String name
) {}

List<?> rawRows = em.createNativeQuery("""
    select id, name
    from customers
    where status = ?
    order by id
    """)
    .setParameter(1, "ACTIVE")
    .getResultList();

List<SimpleCustomerRow> customers = new ArrayList<>();

for (Object value : rawRows) {
    Object[] columns = (Object[]) value;
    customers.add(new SimpleCustomerRow(
        ((Number) columns[0]).longValue(),
        (String) columns[1]
    ));
}
```

Ưu điểm: SQL và Java mapper nằm gần nhau, dễ nhìn.

Nhược điểm: phụ thuộc vị trí và runtime cast; dùng ở nhiều nơi sẽ khó bảo trì. Khi projection phức tạp hoặc cố định lâu dài, `@ConstructorResult`/mapper có test riêng thường rõ hơn.

## 28. Security: raw SQL phải tự kiểm soát quyền truy cập

Native SQL viết trực tiếp trên bảng:

```sql
select * from purchase_orders
```

không tự kế thừa mọi điều kiện application-level từ repository JPQL, các Hibernate filters hay soft-delete mapping. Tùy cơ chế provider, câu SQL có thể bỏ qua tenant predicate/soft-delete restriction nếu bạn không viết nó.

Trong hệ thống multi-tenant:

- Lấy `tenantId` từ authenticated context, không tin parameter do client tự khai báo.
- Lọc tenant ở bảng gốc và joins/subqueries theo model dữ liệu.
- Dùng row-level security database nếu có, nhưng phải kiểm thử.
- Không cho raw native query trả dữ liệu tenant khác.
- Bind values, whitelist tên cột/ORDER BY, không nối input trực tiếp.

Ví dụ:

```java
em.createNativeQuery("""
    select id, order_no, total
    from purchase_orders
    where tenant_id = ?
    """)
  .setParameter(1, currentTenantId)
  .getResultList();
```

Query này giả định schema thực tế có `tenant_id`, không thuộc DDL ví dụ ban đầu; cần thêm cột/schema/constraints tương ứng nếu dùng multi-tenancy.

Không bật SQL bind-parameter logging ở production khi có email, token, thông tin riêng tư hoặc dữ liệu thanh toán.

## 29. Hiệu năng: chọn entity hay DTO?

| Use case | Hướng phù hợp |
| --- | --- |
| Một số tổng hợp | Một scalar `Number` hoặc `@ColumnResult` |
| Danh sách vài field cho UI | `Object[]` mapped DTO/`@ConstructorResult` |
| Entity cần sửa tiếp trong transaction | `resultClass` hoặc `@EntityResult` |
| Entity + một số liệu tổng hợp | `@EntityResult` + `@ColumnResult` |
| SQL JOIN hai entity và cần object managed | Hai `@EntityResult` |
| Projection linh hoạt theo runtime | `NativeQuery.addScalar`/transformer |
| Báo cáo rất lớn | DTO projection/streaming/JDBC phù hợp |
| Query portable trên nhiều DBMS | Ưu tiên HQL/JPQL/Criteria nếu có thể |

Một query ít statement nhưng trả hàng triệu SQL rows và hydrate hàng triệu managed entities có thể gây áp lực memory/GC lớn. `ResultSet` streaming và transaction/connection lifetime cần được quản lý cẩn thận; không mở database cursor rồi giữ qua nhiều phút xử lý không kiểm soát.

### 29.1. Index và query plan quan trọng hơn syntax mapper

`@ConstructorResult` không tự làm SQL nhanh hơn nếu database vẫn scan bảng lớn. Cần đo:

- Số statement, số SQL rows.
- `EXPLAIN`/query plan.
- Index trên FK và filter columns.
- Phân bố dữ liệu/cardinality.
- Chi phí DISTINCT/GROUP BY/ORDER BY.
- Heap, GC, timeouts và connection duration.

## 30. Integration tests cho result shape

Nên kiểm thử trên database giống production để phát hiện khác biệt JDBC numeric/time/UUID và SQL alias handling.

### 30.1. Scalar COUNT

```java
@Test
void countIsNumeric() {
    Object raw = em.createNativeQuery(
        "select count(*) from customers"
    ).getSingleResult();

    assertEquals(3L, ((Number) raw).longValue());
}
```

### 30.2. Multi-column result

```java
@Test
void twoColumnsAreInSelectOrder() {
    Object value = em.createNativeQuery("""
        select id, name
        from customers
        where id = ?
        """)
        .setParameter(1, 1L)
        .getSingleResult();

    Object[] row = (Object[]) value;
    assertEquals(1L, ((Number) row[0]).longValue());
    assertEquals("An", row[1]);
}
```

### 30.3. Managed entity

```java
@Test
void nativeEntitySharesPersistenceContextIdentity() {
    Customer fromFind = em.find(Customer.class, 1L);

    Customer fromNative = (Customer) em.createNativeQuery("""
        select id, name, email, status
        from customers
        where id = ?
        """, Customer.class)
        .setParameter(1, 1L)
        .getSingleResult();

    assertSame(fromFind, fromNative);
    assertTrue(em.contains(fromNative));
}
```

### 30.4. Constructor mapping

```java
@Test
void nativeDtoConstructorMappingReturnsRecord() {
    List<?> rows = em.createNativeQuery("""
        select c.id as customer_id,
               c.name as customer_name,
               coalesce(sum(o.total), 0) as total_spent
        from customers c
        left join purchase_orders o
          on o.customer_id = c.id
        group by c.id, c.name
        order by c.id
        """, "CustomerSpendDto")
        .getResultList();

    assertFalse(rows.isEmpty());
    assertInstanceOf(CustomerSpendRow.class, rows.get(0));
}
```

### 30.5. Entity + scalar

```java
@Test
void mixedMappingHasEntityAndCount() {
    List<?> rows = em.createNativeQuery("""
        select c.id as c_id,
               c.name as c_name,
               c.email as c_email,
               c.status as c_status,
               count(o.id) as order_count
        from customers c
        left join purchase_orders o on o.customer_id = c.id
        group by c.id, c.name, c.email, c.status
        order by c.id
        """, "CustomerWithOrderCount")
        .getResultList();

    Object[] first = (Object[]) rows.get(0);
    assertInstanceOf(Customer.class, first[0]);
    assertEquals(2L, ((Number) first[1]).longValue());
}
```

Các đoạn trên là **test bodies minh họa**, chưa có JUnit fixture/seed/cleanup. Cần một `EntityManagerFactory` thật, EntityManager đúng lifecycle và class/mappings được provider discover. Với JUnit 5, `assertInstanceOf` có ở phiên bản phù hợp; bản cũ có thể dùng `instanceof`.

Test cần kiểm tra **giá trị cụ thể, kiểu cụ thể và số rows**, không chỉ query “không ném exception”.

## 31. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `ClassCastException: Object[] -> Customer` | Trả nhiều scalar nhưng cast entity | Dùng `resultClass`/`EntityResult` |
| `ClassCastException: Number -> Object[]` | Query chỉ select một cột | Đọc scalar |
| `Column not found` | Mapping alias khác SQL label | Đồng bộ aliases |
| Non-unique discovered SQL alias | Hai bảng cùng `id`/`status` | Alias duy nhất |
| Không hydrate được entity | Thiếu persistent columns/FK/version | Select đủ fields |
| DTO constructor mismatch | Sai kiểu/thứ tự cột | Kiểm tra `ConstructorResult.columns` |
| COUNT cast Long lỗi | Driver trả numeric type khác | Dùng Number/ColumnResult type |
| `SUM(total)` thành null | Không có rows phù hợp | COALESCE theo business |
| LEFT JOIN count sai | Dùng `COUNT(*)` | Dùng `COUNT(child.id)` |
| Khách hàng xuất hiện hai lần | Một customer có nhiều orders | Aggregate/DTO/đếm distinct |
| Native result entity có state cũ | L1 reuse managed object | Refresh/context mới khi phù hợp |
| Native UPDATE không đổi managed object | DML bypass dirty checking | Transaction/refresh/clear đúng |
| Mapping name không được tìm thấy | Annotation không được scan | Đặt trên managed type, kiểm tra persistence unit |
| Query chạy H2 nhưng lỗi PostgreSQL | SQL/driver/dialect khác | Test đúng database |
| SQL trả lộ dữ liệu tenant | Native query thiếu tenant predicate | Security/tenant scope tường minh |

## 32. Quy trình chọn result mapping

1. **Xác định thứ cần trả:** một scalar, nhiều cột, một entity hay kết quả hỗn hợp?
2. **Có cần entity managed không?** Nếu không, ưu tiên DTO/projection để tránh hydrate toàn bộ entity.
3. **SQL có chọn đủ persistent columns không?** Nếu dùng entity mapping, phải có ID/FK/version/discriminator khi cần.
4. **Cột có alias duy nhất không?** Đặc biệt JOIN nhiều bảng đều có `id`, `status`.
5. **JDBC/Java type là gì?** Kiểm tra numeric, temporal, UUID, JSON, boolean, nullable values.
6. **Mapping dùng một lần hay tái sử dụng?** Object[] thủ công cho query nhỏ; `@ConstructorResult`/`@EntityResult` cho contract ổn định.
7. **Có cần API riêng Hibernate?** Dùng `addScalar`, `addEntity`, `TupleTransformer` khi có lợi ích rõ.
8. **Result array có đúng thứ tự không?** `entities → classes → columns` khi multi-component mapping.
9. **L1 context có state cũ không?** Native entity mapping không mặc định refresh object đã managed.
10. **DML/flush có ảnh hưởng query không?** Chọn transaction boundaries và synchronization phù hợp.
11. **Có tenant/security policy không?** Không bỏ qua điều kiện bảo vệ vì dùng raw SQL.
12. **Kiểm thử production dialect.** Xác nhận SQL, aliases, result shape, nulls, precision và query plan.

## 33. Bài tập tình huống

### Bài 1 — Scalar hay entity?

```sql
select name from customers where id = ?
```

Có thể cast trực tiếp kết quả mặc định sang Customer không?

**Đáp án:** Không. Đây là một scalar `String`; không đủ dữ liệu để hydrate managed entity.

### Bài 2 — Multi-column result

```sql
select id, name, status from customers
```

Một row mặc định thường trả kiểu nào?

**Đáp án:** `Object[]`, với ba phần tử theo thứ tự SELECT.

### Bài 3 — COUNT khác kiểu

DB A trả `Long`, DB B trả `BigInteger` cho COUNT. Cách đọc linh hoạt?

**Đáp án:** `((Number) query.getSingleResult()).longValue()`, với điều kiện kết quả phù hợp phạm vi long. Có thể khai báo mapping kiểu rõ nếu cần.

### Bài 4 — Partial entity

SQL chỉ chọn `id, name`, nhưng entity Customer còn `email` và `status`. Có nên dùng `Customer.class` result?

**Đáp án:** Không. Mapping entity cần đủ persistent state; dùng DTO hai cột.

### Bài 5 — Hai cột ID

JOIN customer và order đều có `id`. Cách tránh ambiguous column label?

**Đáp án:** `c.id AS c_id`, `o.id AS o_id` và mapping riêng.

### Bài 6 — FieldResult

```java
@FieldResult(name="orderNumber", column="o_order_no")
```

Hai giá trị này trỏ tới đâu?

**Đáp án:** `name` là property Java; `column` là alias SQL result.

### Bài 7 — Constructor order

Record nhận `(Long, String, BigDecimal)`, nhưng mapping dùng `(BigDecimal, String, Long)`. Kết quả?

**Đáp án:** Constructor mismatch hoặc lỗi type conversion; thứ tự ColumnResult phải khớp constructor.

### Bài 8 — Mixed mapping

Mapping có một EntityResult(Customer) và một ColumnResult(order_count). Một row là gì?

**Đáp án:** `Object[]` với `[0]` là Customer managed, `[1]` là scalar count.

### Bài 9 — Hai entity results

Có Customer và PurchaseOrder trong một SQL row. Mapping có hai EntityResult trả gì?

**Đáp án:** `Object[]` gồm hai entity theo thứ tự khai báo trong `entities`.

### Bài 10 — ConstructorResult entity

`ConstructorResult(targetClass=Customer.class)` có tự tạo managed Customer không?

**Đáp án:** Không. Entity object tạo bằng constructor result có thể new/detached; dùng EntityResult nếu cần entity managed.

### Bài 11 — Null qua LEFT JOIN

Customer Chi không có order. `SUM(o.total)` trả gì?

**Đáp án:** Thường NULL; `COALESCE(SUM(o.total),0)` nếu muốn báo tổng 0.

### Bài 12 — COUNT(*) qua LEFT JOIN

Customer Chi chưa có order. `COUNT(*)` trong group của Chi có thể trả bao nhiêu?

**Đáp án:** Một, vì null-extended row. `COUNT(o.id)` trả 0.

### Bài 13 — Native DML

Native UPDATE đổi Customer.status nhưng entity đã load vẫn giá trị cũ. Vì sao?

**Đáp án:** Bulk native SQL không tự đồng bộ state managed trong persistence context. Cần refresh/clear có chủ đích.

### Bài 14 — Scalar monetary

Có `BigDecimal("200.50")`. Dùng `.longValue()` có an toàn không?

**Đáp án:** Không cho tiền tệ, vì mất phần lẻ.

### Bài 15 — Result-set mapping group order

Một mapping gồm `entities=[Customer]`, `classes=[CustomerSpendRow]`, `columns=[rank]`. `Object[]` có thứ tự nào?

**Đáp án:** Customer, CustomerSpendRow, rank; đó là thứ tự mapping components chứ không dựa riêng vào SQL SELECT.

### Bài 16 — Multi-tenant

Native query không có tenant predicate trong khi HQL repository có. Có an toàn tự động không?

**Đáp án:** Không. Native SQL phải được bảo vệ bằng điều kiện tenant/security hoặc database RLS đã kiểm chứng.

## 34. Tài liệu tham khảo chính thức

- [Jakarta Persistence 3.2 Specification — Native SQL & SQL result set mappings](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): entity, constructor, scalar và composite query results.
- [Jakarta Persistence 3.2 — `SqlResultSetMapping`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/SqlResultSetMapping.html): `entities`, `classes`, `columns`.
- [Jakarta Persistence 3.2 — `EntityResult`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/EntityResult.html): entity mapping và yêu cầu đủ cột persistent state.
- [Jakarta Persistence 3.2 — `FieldResult`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/FieldResult.html): property Java và SQL alias mapping.
- [Jakarta Persistence 3.2 — `ConstructorResult`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/ConstructorResult.html): DTO constructor, thứ tự columns, entity constructor result lifecycle.
- [Jakarta Persistence 3.2 — `ColumnResult`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/ColumnResult.html): scalar result và explicit Java type.
- [Jakarta Persistence 3.2 — `NamedNativeQuery`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/NamedNativeQuery.html): native query có tên và result mapping.
- [Hibernate ORM User Guide — Native SQL](https://docs.hibernate.org/stable/orm/userguide/html_single/#sql): native result handling, entity returns, scalar returns, synchronization.
- [Hibernate ORM Javadoc — `NativeQuery`](https://docs.hibernate.org/stable/orm/javadocs/org/hibernate/query/NativeQuery.html): `addScalar`, `addEntity`, typed native mapping.
- [Hibernate ORM Javadoc — `TupleTransformer`](https://docs.hibernate.org/stable/orm/javadocs/org/hibernate/query/TupleTransformer.html): chuyển mỗi row thành Java object.
- [Hibernate ORM User Guide — Persistence Context](https://docs.hibernate.org/stable/orm/userguide/html_single/#pc): identity map và managed state.
- [PostgreSQL — Aggregate Functions](https://www.postgresql.org/docs/current/functions-aggregate.html): COUNT/SUM/AVG và null behavior.

**Phạm vi phiên bản:** `SqlResultSetMapping`, `EntityResult`, `ColumnResult`, `ConstructorResult` thuộc Jakarta Persistence. `NativeQuery.addScalar/addEntity` và transformers là Hibernate-specific; signature có thể đổi theo major version. SQL grammar, alias folding và Java/JDBC types tùy DBMS/driver. Hãy kiểm tra trên đúng phiên bản triển khai.

## Kết luận

**Ánh xạ native SQL phải bắt đầu từ hình dạng dữ liệu cần trả**, không bắt đầu từ thói quen cast `Object`. Một cột thường là scalar; nhiều cột là một tuple/DTO; một entity cần đủ persistent columns và được quản lý bởi persistence context; một kết quả entity + scalar hoặc nhiều entity cần mapping hỗn hợp rõ ràng.

`@SqlResultSetMapping` mô tả những thành phần này bằng `@ColumnResult`, `@EntityResult`, `@FieldResult` và `@ConstructorResult`. Với nhiều mapping components, mỗi row là `Object[]` theo thứ tự **entity → constructor → scalar**. Hibernate còn có `NativeQuery.addScalar`, `addEntity` và tuple transformer cho mapper programmatic.

Để hệ thống bền vững, hãy **đặt SQL aliases duy nhất, giữ đúng JDBC/Java types, select đủ state khi trả entity, dùng DTO cho báo cáo, phân biệt L1-managed data với scalar snapshot, kiểm soát flush/native DML và tenant/security constraints**, rồi kiểm thử tất cả trên DBMS thực tế. Một native query chạy không lỗi vẫn chưa chứng minh rằng dữ liệu Java đã có đúng kiểu, đúng lifecycle và đúng ý nghĩa nghiệp vụ.
