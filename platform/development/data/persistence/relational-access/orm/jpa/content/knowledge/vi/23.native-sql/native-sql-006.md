# Sử dụng `EntityResult`, `FieldResult` và `ColumnResult` trong Native SQL của JPA

## 1. Vấn đề: SQL trả hàng và cột, JPA cần entity hoặc giá trị Java

Khi dùng **Jakarta Persistence (JPA)**, truy vấn JPQL thường làm việc với tên entity và tên thuộc tính Java:

```java
List<Customer> customers = em.createQuery(
    "SELECT c FROM Customer c WHERE c.tier = :tier",
    Customer.class
).setParameter("tier", "GOLD")
 .getResultList();
```

Provider biết `Customer` được ánh xạ tới bảng nào, cột nào là khóa chính, cột nào thuộc thuộc tính `fullName`, và cách biến dữ liệu database thành entity.

Nhưng có những bài toán cần **Native SQL**:

- Báo cáo dùng truy vấn SQL đã được tối ưu cho database cụ thể.
- Dùng CTE, window function, database-specific aggregation hoặc các hàm chưa được phiên bản JPQL hỗ trợ.
- Join nhiều bảng hoặc view và trả về cột đã đổi tên.
- Cần vừa lấy **entity managed** vừa lấy **giá trị thống kê**, chẳng hạn số đơn hàng của từng khách.
- Một truy vấn SQL trả alias như `customer_key`, `display_name`, trong khi entity ánh xạ các cột gốc là `id` và `full_name`.

Ví dụ SQL:

```sql
SELECT
    c.id AS customer_key,
    c.full_name AS display_name,
    c.tier AS customer_tier,
    c.row_version AS customer_version,
    COUNT(o.id) AS order_count
FROM customers c
LEFT JOIN purchase_orders o
       ON o.customer_id = c.id
GROUP BY c.id, c.full_name, c.tier, c.row_version;
```

Kết quả SQL có dạng:

| `customer_key` | `display_name` | `customer_tier` | `customer_version` | `order_count` |
|---:|---|---|---:|---:|
| 1 | An | GOLD | 2 | 2 |
| 2 | Bình | STANDARD | 0 | 0 |
| 3 | Chi | SILVER | 1 | 1 |

Ứng dụng có thể muốn mỗi hàng thành:

```text
Object[] {
    Customer managedEntity,
    Long orderCount
}
```

Ở đây có **hai loại kết quả**:

1. Các cột của `Customer` tạo thành **một entity**.
2. `order_count` là **một scalar value**, không phải thuộc tính được lưu trong entity.

JPA cung cấp `@SqlResultSetMapping` cùng ba thành phần quan trọng:

- **`@EntityResult`**: một nhóm cột trong result set đại diện cho một entity.
- **`@FieldResult`**: cột/alias nào đi vào thuộc tính persistent nào của entity đó.
- **`@ColumnResult`**: một cột/biểu thức đơn lẻ trong result set được trả về như scalar value.

Đây là công cụ trung tâm của bài học.

### 1.1. Mục tiêu sau bài này

Sau khi học, bạn có thể:

1. Chọn giữa `createNativeQuery(sql, Entity.class)` và `@SqlResultSetMapping`.
2. Ánh xạ alias SQL khác tên cột gốc bằng `@EntityResult` và `@FieldResult`.
3. Lấy kết quả `COUNT`, `SUM`, biểu thức SQL bằng `@ColumnResult`.
4. Kết hợp **entity + scalar** trong một hàng kết quả và đọc đúng `Object[]`.
5. Xử lý entity có **khóa ghép/`@EmbeddedId`**.
6. Dùng mapping với `@NamedNativeQuery`.
7. Phân biệt kết quả entity managed với DTO tạo bằng `@ConstructorResult`.
8. Tránh lỗi thiếu khóa chính, sai alias, nhầm kiểu dữ liệu và vô tình dùng entity chưa được tải đầy đủ.

---

## 2. Sơ đồ tổng quan

```text
                            Native SQL
                                |
                                v
                      JDBC ResultSet rows
             +------------------+----------------+
             |                  |                |
         customer_key       display_name     order_count
             |                  |                |
             +---------+--------+                |
                       |                         |
                       v                         v
                @EntityResult               @ColumnResult
                       |                         |
              +--------+--------+                |
              |                 |                |
          @FieldResult     @FieldResult          |
          id <- alias      fullName <- alias      |
              |                 |                |
              +--------+--------+                |
                       |                         |
                       v                         v
                Customer entity                Long
                       |                         |
                       +------------+------------+
                                    |
                                    v
                              Object[] row
                       [ Customer, orderCount ]
```

`@SqlResultSetMapping` là **metadata khai báo sẵn** cách chuyển một result set SQL thành những kết quả Java. Nó không phải SQL query, không tự thực thi truy vấn và không tự thay thế entity mapping `@Entity` / `@Column`.

**Điểm then chốt:** SQL quyết định **những cột nào được trả về**; `@SqlResultSetMapping` quyết định **những cột đó được diễn giải thành object/value nào**.

## 3. Những annotation cần biết

### 3.1. `@SqlResultSetMapping`

Một mapping có tên:

```java
@SqlResultSetMapping(
    name = "CustomerNativeMapping",
    entities = @EntityResult(
        entityClass = Customer.class
    )
)
```

Các thành phần quan trọng của `@SqlResultSetMapping`:

| Thuộc tính | Dùng để làm gì? |
|---|---|
| `name` | Tên mapping, được dùng ở `createNativeQuery(..., mappingName)` hoặc `@NamedNativeQuery(resultSetMapping=...)`. |
| `entities` | Một hoặc nhiều `@EntityResult`. |
| `columns` | Một hoặc nhiều `@ColumnResult`. |
| `classes` | Một hoặc nhiều `@ConstructorResult` để tạo object theo constructor. |

Có thể kết hợp nhiều loại trong **một mapping** nếu mỗi hàng trả nhiều phần kết quả.

### 3.2. `@EntityResult`

```java
@EntityResult(
    entityClass = Customer.class,
    fields = {
        @FieldResult(name = "id", column = "customer_key"),
        @FieldResult(name = "fullName", column = "display_name")
    }
)
```

- `entityClass`: lớp `@Entity` cần tạo/quản lý.
- `fields`: khai báo mapping rõ ràng từng thuộc tính được trả từ SQL.
- `discriminatorColumn`: dùng cho một số trường hợp **entity inheritance** khi phải nhận diện loại subclass từ discriminator trong result set.

`EntityResult` **không biến một POJO bất kỳ thành entity**. Lớp đích vẫn phải là JPA entity hợp lệ, được provider quản lý và thuộc persistence unit.

### 3.3. `@FieldResult`

```java
@FieldResult(
    name = "fullName",
    column = "display_name"
)
```

- `name` là **tên thuộc tính persistent trong entity**, ví dụ `fullName`.
- `column` là **tên cột hoặc alias có trong result set của SQL**, ví dụ `display_name`.

Không phải:

```java
// Sai nếu Customer không có thuộc tính tên display_name:
@FieldResult(name = "display_name", column = "fullName")
```

Trong JPQL, ta viết `c.fullName`. Trong native SQL, ta viết `c.full_name AS display_name`. `FieldResult` nối hai cách gọi ấy.

### 3.4. `@ColumnResult`

```java
@ColumnResult(name = "order_count")
```

hoặc:

```java
@ColumnResult(
    name = "order_count",
    type = Long.class
)
```

- `name` là cột/alias trong result set.
- `type` cho biết kiểu Java mong muốn của scalar result, khi khả năng chuyển đổi được provider/database hỗ trợ.

`ColumnResult` **không yêu cầu** entity có thuộc tính `orderCount`. Nó thích hợp cho tổng, đếm, phép toán, hàm SQL và các cột trả về mà không cần quản lý như một entity.

### 3.5. Ba annotation phối hợp với nhau ra sao?

```java
@SqlResultSetMapping(
    name = "CustomerWithOrderCount",
    entities = @EntityResult(
        entityClass = Customer.class,
        fields = {
            @FieldResult(name = "id", column = "c_id"),
            @FieldResult(name = "fullName", column = "c_name")
        }
    ),
    columns = @ColumnResult(
        name = "order_count",
        type = Long.class
    )
)
```

Mỗi hàng truy vấn có thể trả một `Customer` và một `Long`. Vì có **nhiều thành phần kết quả**, ứng dụng nhận một hàng dưới dạng `Object[]`.

---

## 4. Khi nào không cần `@SqlResultSetMapping`?

Trước khi thêm metadata, hãy kiểm tra trường hợp đơn giản.

### 4.1. Chỉ trả một entity, tên cột đúng mapping

Giả sử entity:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @Column(name = "full_name")
    private String fullName;

    protected Customer() {}
}
```

SQL:

```java
List<?> raw = em.createNativeQuery(
    """
    SELECT id, full_name
    FROM customers
    WHERE id = ?
    """,
    Customer.class
)
.setParameter(1, customerId)
.getResultList();
```

Với những entity đơn giản mà SQL trả đủ các cột được mapping bằng tên kết quả provider trông đợi, `createNativeQuery(sql, Customer.class)` là lựa chọn gọn hơn.

Điều kiện cần đánh giá:

- Có đủ cột khóa chính và các cột cần thiết để tạo entity hợp lệ không?
- Tên/alias SQL có tương ứng mapping entity không?
- Có khóa version, discriminator, embedded field hoặc relationship FK cần thêm cột không?
- Provider/dialect có xác định đúng kiểu cột không?

### 4.2. Chỉ lấy scalar đơn giản

```java
Object result = em.createNativeQuery(
    "SELECT COUNT(*) FROM customers"
).getSingleResult();

long count = ((Number) result).longValue();
```

Nếu chỉ là một phép đếm ngắn, không nhất thiết khai báo `@ColumnResult`.

Tuy nhiên, khi query phức tạp, cần kết quả nhiều scalar, cần tái sử dụng mapping hoặc cần kiểu dữ liệu tường minh, `@SqlResultSetMapping` thường giúp code dễ đọc và dễ bảo trì hơn.

### 4.3. Khi nào nên dùng mapping tường minh?

| Tình huống | Gợi ý |
|---|---|
| `SELECT` đủ cột entity, dùng tên cột gốc. | Cân nhắc `createNativeQuery(sql, Entity.class)`. |
| SQL đổi alias khác tên cột mapping. | `EntityResult` + `FieldResult`. |
| SQL join nhiều bảng cùng có cột `id`/`name`. | Dùng alias riêng và `FieldResult` tránh mơ hồ. |
| SQL trả entity cùng `COUNT`/`SUM`. | `EntityResult` + `ColumnResult`. |
| SQL chỉ trả nhiều scalar cần định kiểu. | Một hoặc nhiều `ColumnResult`. |
| SQL trả dữ liệu cho read-only DTO. | `ConstructorResult` hoặc tự map result/projection. |
| Entity có `@EmbeddedId` / embedded fields. | `FieldResult` với đường dẫn dấu chấm khi cần. |
| Không muốn quản lý entity, chỉ làm báo cáo. | Ưu tiên scalar/DTO thay vì ép thành partial entity. |

---

## 5. Mô hình dữ liệu xuyên suốt bài học

Ta dùng hai bảng:

```text
customers
  id (PK)
  full_name
  tier
  row_version

purchase_orders
  id (PK)
  customer_id (FK -> customers.id)
  total_amount
  status
```

Dữ liệu mẫu:

**Khách hàng**

| id | full_name | tier | row_version |
|---:|---|---|---:|
| 1 | An | GOLD | 2 |
| 2 | Bình | STANDARD | 0 |
| 3 | Chi | SILVER | 1 |

**Đơn hàng**

| id | customer_id | total_amount | status |
|---:|---:|---:|---|
| 101 | 1 | 300000.00 | PAID |
| 102 | 1 | 90000.00 | DRAFT |
| 103 | 3 | 120000.00 | PAID |

Kết quả báo cáo mong muốn:

| Customer | Số đơn | Tổng tiền đơn PAID |
|---|---:|---:|
| An | 2 | 300000.00 |
| Bình | 0 | 0.00 |
| Chi | 1 | 120000.00 |

Bình không có đơn hàng nhưng **vẫn phải xuất hiện** trong báo cáo; do đó SQL sử dụng `LEFT JOIN`.

### 5.1. DDL tham khảo

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    tier VARCHAR(30) NOT NULL,
    row_version BIGINT NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT fk_purchase_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
);

CREATE INDEX ix_orders_customer_id
ON purchase_orders(customer_id);
```

Đây là DDL minh họa. Cú pháp `GENERATED BY DEFAULT AS IDENTITY` và các chi tiết numeric có thể khác giữa RDBMS.

### 5.2. Entity `PurchaseOrder`

```java
package com.example.nativesql;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(
        name = "total_amount",
        nullable = false,
        precision = 15,
        scale = 2
    )
    private BigDecimal totalAmount;

    @Column(name = "status", nullable = false, length = 20)
    private String status;

    protected PurchaseOrder() {}

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public String getStatus() {
        return status;
    }
}
```

Entity dùng `@ManyToOne` để biểu diễn FK. Trong SQL native, ta vẫn được quyền viết `o.customer_id = c.id` vì đây là **SQL theo tên bảng/cột thật**, không phải JPQL relationship navigation.

### 5.3. Entity `Customer` với các result-set mappings

Ví dụ dưới đây minh họa **ba mapping độc lập** trên một entity:

- `CustomerEntityAliased`: chỉ một entity.
- `CustomerOrderOverview`: entity + hai scalar.
- `CustomerTierCounts`: chỉ các scalar.

```java
package com.example.nativesql;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "customers")

@SqlResultSetMapping(
    name = "CustomerEntityAliased",
    entities = @EntityResult(
        entityClass = Customer.class,
        fields = {
            @FieldResult(name = "id",
                         column = "c_id"),
            @FieldResult(name = "fullName",
                         column = "c_name"),
            @FieldResult(name = "tier",
                         column = "c_tier"),
            @FieldResult(name = "version",
                         column = "c_version")
        }
    )
)

@SqlResultSetMapping(
    name = "CustomerOrderOverview",
    entities = @EntityResult(
        entityClass = Customer.class,
        fields = {
            @FieldResult(name = "id",
                         column = "c_id"),
            @FieldResult(name = "fullName",
                         column = "c_name"),
            @FieldResult(name = "tier",
                         column = "c_tier"),
            @FieldResult(name = "version",
                         column = "c_version")
        }
    ),
    columns = {
        @ColumnResult(
            name = "order_count",
            type = Long.class
        ),
        @ColumnResult(
            name = "paid_total",
            type = BigDecimal.class
        )
    }
)

@SqlResultSetMapping(
    name = "CustomerTierCounts",
    columns = {
        @ColumnResult(
            name = "tier_label",
            type = String.class
        ),
        @ColumnResult(
            name = "customer_count",
            type = Long.class
        )
    }
)

@NamedNativeQuery(
    name = "Customer.orderOverview",
    query = """
        SELECT
            c.id AS c_id,
            c.full_name AS c_name,
            c.tier AS c_tier,
            c.row_version AS c_version,
            COUNT(o.id) AS order_count,
            COALESCE(
                SUM(
                    CASE WHEN o.status = 'PAID'
                         THEN o.total_amount
                         ELSE 0
                    END
                ),
                0
            ) AS paid_total
        FROM customers c
        LEFT JOIN purchase_orders o
               ON o.customer_id = c.id
        GROUP BY
            c.id, c.full_name, c.tier, c.row_version
        ORDER BY c.id
        """,
    resultSetMapping = "CustomerOrderOverview"
)

public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 150)
    private String fullName;

    @Column(name = "tier", nullable = false, length = 30)
    private String tier;

    @Version
    @Column(name = "row_version", nullable = false)
    private Long version;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {}

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getTier() {
        return tier;
    }

    public Long getVersion() {
        return version;
    }

    public List<PurchaseOrder> getOrders() {
        return orders;
    }
}
```

Các annotation được đặt ở cấp **class entity** để provider phát hiện và đăng ký metadata khi khởi tạo persistence unit. `@SqlResultSetMapping` là annotation có thể lặp lại trong các phiên bản JPA hiện đại; cũng có thể dùng container `@SqlResultSetMappings` nếu codebase yêu cầu phong cách đó.

Những entity này là **mô hình để đọc dữ liệu**, nên ví dụ chỉ cần getters và constructor không tham số `protected`. Trong ứng dụng thực, domain methods, validation và quyền sửa dữ liệu cần được thiết kế riêng.

### 5.4. Vì sao mapping có cả `version`?

`Customer` chứa:

```java
@Version
@Column(name = "row_version", nullable = false)
private Long version;
```

Vì query đang trả **entity**, cần cung cấp đầy đủ dữ liệu bắt buộc để provider tái tạo một managed entity hợp lệ. Đối với entity có `@Version`, cột version đặc biệt quan trọng cho optimistic locking.

Truy vấn partial entity bỏ `row_version` có thể dẫn tới lỗi mapping, version không đáng tin cậy hoặc hành vi không được đặc tả bảo đảm. Không nên bỏ một cột chỉ vì màn hình không hiển thị nó.

---

## 6. Ví dụ 1: `@EntityResult` với `@FieldResult`

### 6.1. SQL đổi tên các cột

```sql
SELECT
    c.id AS c_id,
    c.full_name AS c_name,
    c.tier AS c_tier,
    c.row_version AS c_version
FROM customers c
WHERE c.id = ?;
```

SQL trả các nhãn cột `c_id`, `c_name`, `c_tier`, `c_version`.

Trong entity, các thuộc tính lại tên:

```text
Customer.id
Customer.fullName
Customer.tier
Customer.version
```

`@FieldResult` tạo bảng quy chiếu:

| Java persistent attribute | Alias SQL trong result set |
|---|---|
| `id` | `c_id` |
| `fullName` | `c_name` |
| `tier` | `c_tier` |
| `version` | `c_version` |

### 6.2. Khai báo mapping

Trích từ entity `Customer`:

```java
@SqlResultSetMapping(
    name = "CustomerEntityAliased",
    entities = @EntityResult(
        entityClass = Customer.class,
        fields = {
            @FieldResult(name = "id", column = "c_id"),
            @FieldResult(name = "fullName", column = "c_name"),
            @FieldResult(name = "tier", column = "c_tier"),
            @FieldResult(name = "version", column = "c_version")
        }
    )
)
```

Ở đây:

- `entityClass = Customer.class` nói nhóm result columns tạo thành `Customer`.
- `FieldResult(name="id",column="c_id")` gắn **khóa chính** từ alias.
- Các field còn lại đi vào persistent attributes.
- Không có `@ColumnResult` riêng vì toàn bộ projection được dùng để tái tạo một entity.

### 6.3. Chạy truy vấn với mapping name

```java
String sql = """
    SELECT
        c.id AS c_id,
        c.full_name AS c_name,
        c.tier AS c_tier,
        c.row_version AS c_version
    FROM customers c
    WHERE c.id = ?
    """;

List<?> rows = em.createNativeQuery(
        sql,
        "CustomerEntityAliased"
    )
    .setParameter(1, customerId)
    .getResultList();

for (Object row : rows) {
    Customer customer = (Customer) row;

    System.out.println(
        customer.getId() + " - " +
        customer.getFullName()
    );
}
```

Vì mapping chỉ có **một entity result** và không có scalar/class results, mỗi phần tử kết quả là một `Customer` theo dạng mapping trên, **không cần ép sang `Object[]`**.

### 6.4. Vì sao nên dùng alias rõ ràng?

Một SQL join có thể có nhiều cột cùng tên:

```sql
SELECT c.id, o.id
FROM customers c
JOIN purchase_orders o
  ON o.customer_id = c.id;
```

Result set có **hai nhãn `id`**. Provider/JDBC driver có thể xử lý tên cột trùng không như người viết mong đợi.

Đặt alias riêng:

```sql
SELECT
    c.id AS c_id,
    o.id AS o_id
FROM customers c
JOIN purchase_orders o
  ON o.customer_id = c.id;
```

Sau đó khai báo `FieldResult` trỏ đúng alias tương ứng.

**Quy tắc:** với native SQL join và entity mapping tường minh, tên alias cần **rõ nghĩa và không trùng** trên toàn bộ projection cần đọc.

## 7. `@FieldResult` map theo tên Java, không theo tên cột gốc

Giả sử:

```java
@Column(name = "full_name")
private String fullName;
```

Và SQL:

```sql
SELECT c.full_name AS display_name
FROM customers c;
```

Mapping đúng:

```java
@FieldResult(name = "fullName", column = "display_name")
```

Không phải:

```java
@FieldResult(name = "full_name", column = "display_name")
```

vì `name` của `FieldResult` tham chiếu **thuộc tính persistent Java**.

### 7.1. Field access và property access

JPA hỗ trợ hai phong cách truy cập:

- **Field access**: các annotation mapping nằm trên field.
- **Property access**: annotation nằm trên getter.

Khi dùng property access:

```java
@Id
public Long getId() {
    return id;
}
```

`FieldResult.name` vẫn tham chiếu **tên persistent property** `id` chứ không phải tên method `getId` và cũng không phải tên SQL column.

Đặt sai:

```java
@FieldResult(name = "getId", column = "c_id")
```

không thể thay thế `name = "id"`.

### 7.2. Không map field transient bằng `FieldResult`

Giả sử entity có:

```java
@Transient
private long orderCount;
```

Vì `orderCount` không phải persistent attribute, không nên cố gắn:

```java
@FieldResult(
    name = "orderCount",
    column = "order_count"
)
```

vào `EntityResult` như thể đó là cột entity bình thường. Thay vào đó, dùng **`ColumnResult`** để nhận một scalar value, hoặc dùng `ConstructorResult` để xây DTO có `orderCount`.

---

## 8. Ví dụ 2: `@ColumnResult` cho kết quả chỉ gồm scalar

Yêu cầu:

> Thống kê mỗi nhóm khách hàng (`tier`) có bao nhiêu khách.

SQL:

```sql
SELECT
    c.tier AS tier_label,
    COUNT(*) AS customer_count
FROM customers c
GROUP BY c.tier
ORDER BY c.tier;
```

Không có nhu cầu tải entity `Customer`, vì mỗi hàng là một **group thống kê**, không tương ứng một customer riêng lẻ.

### 8.1. Mapping hai scalar

```java
@SqlResultSetMapping(
    name = "CustomerTierCounts",
    columns = {
        @ColumnResult(
            name = "tier_label",
            type = String.class
        ),
        @ColumnResult(
            name = "customer_count",
            type = Long.class
        )
    }
)
```

### 8.2. Truy vấn và đọc kết quả

```java
String sql = """
    SELECT
        c.tier AS tier_label,
        COUNT(*) AS customer_count
    FROM customers c
    GROUP BY c.tier
    ORDER BY c.tier
    """;

List<?> rows = em.createNativeQuery(
        sql,
        "CustomerTierCounts"
    ).getResultList();

for (Object row : rows) {
    Object[] values = (Object[]) row;

    String tier = (String) values[0];
    Long customerCount = (Long) values[1];

    System.out.println(tier + ": " + customerCount);
}
```

Với dữ liệu mẫu, có ba nhóm: GOLD, SILVER, STANDARD; mỗi nhóm có một customer.

Điểm quan trọng:

- `@ColumnResult` diễn giải **một scalar**.
- Khi mapping có **hai scalar results**, hàng có hai phần tử: `Object[]`.
- Thứ tự các giá trị theo **thứ tự khai báo `columns` trong mapping**, không phải dựa trên suy đoán từ vị trí cột ban đầu của SELECT.
- Mỗi alias phải tồn tại trong result set SQL.

### 8.3. Một `ColumnResult` duy nhất

Mapping:

```java
@SqlResultSetMapping(
    name = "SingleCount",
    columns = @ColumnResult(
        name = "total_rows",
        type = Long.class
    )
)
```

SQL:

```sql
SELECT COUNT(*) AS total_rows FROM customers;
```

Một hàng chỉ chứa một scalar result có thể được trả dưới dạng một giá trị `Long`, không phải bắt buộc `Object[]`:

```java
Object result = em.createNativeQuery(
        "SELECT COUNT(*) AS total_rows FROM customers",
        "SingleCount"
    ).getSingleResult();

Long count = (Long) result;
```

Trong dự án cần chạy trên nhiều driver/provider, test `type = Long.class` thực tế là quan trọng; nếu bỏ `type`, `COUNT(*)` có thể được driver/provider trả về dạng `BigInteger`, `Long` hoặc kiểu `Number` khác.

### 8.4. Vì sao `type` có ích?

Không có kiểu tường minh:

```java
@ColumnResult(name = "order_count")
```

thì kết quả scalar mặc định chịu quy tắc JDBC type mapping của provider.

Khai báo:

```java
@ColumnResult(
    name = "order_count",
    type = Long.class
)
```

giúp thể hiện kỳ vọng rõ ràng và yêu cầu provider chuyển đổi tương thích. Tuy nhiên, `type` không thể sửa một biểu thức SQL không thể convert hoặc một giá trị vượt miền kiểu Java.

**Ví dụ:** `SUM(total_amount)` nên dùng kiểu số thập phân phù hợp như `BigDecimal` trong báo cáo tiền tệ, không tùy tiện ép sang `Double` và chấp nhận mất độ chính xác.

---

## 9. Ví dụ 3: kết hợp `EntityResult` + `ColumnResult`

Đây là tình huống rất thường gặp của native SQL.

Yêu cầu:

> Trả **entity Customer** để tiếp tục sử dụng trong persistence context, đồng thời có **số đơn và tổng tiền đã thanh toán** của khách.

SQL đã khai báo trong `@NamedNativeQuery`:

```sql
SELECT
    c.id AS c_id,
    c.full_name AS c_name,
    c.tier AS c_tier,
    c.row_version AS c_version,
    COUNT(o.id) AS order_count,
    COALESCE(
        SUM(
            CASE WHEN o.status = 'PAID'
                 THEN o.total_amount
                 ELSE 0
            END
        ),
        0
    ) AS paid_total
FROM customers c
LEFT JOIN purchase_orders o
       ON o.customer_id = c.id
GROUP BY c.id, c.full_name, c.tier, c.row_version
ORDER BY c.id;
```

### 9.1. Vì sao dùng `LEFT JOIN`?

Nếu dùng `INNER JOIN`, customer Bình không có đơn sẽ bị loại trước bước `GROUP BY`.

Với `LEFT JOIN`:

- Customer có nhiều order → SQL join tạo nhiều hàng, rồi `GROUP BY` gom lại.
- Customer không có order → vẫn có một hàng với `o.id = NULL`.
- `COUNT(o.id)` đếm số order thật, không đếm hàng null.
- `SUM(CASE...)` tính tiền chỉ cho order PAID.
- `COALESCE(...,0)` cho 0 nếu biểu thức tổng không có giá trị thích hợp.

**Chú ý:** `COUNT(*)` trên LEFT JOIN sẽ cho Bình bằng **1** do vẫn có một hàng kết hợp. Dùng `COUNT(o.id)` để lấy **số child**.

### 9.2. Mapping phối hợp

```java
@SqlResultSetMapping(
    name = "CustomerOrderOverview",
    entities = @EntityResult(
        entityClass = Customer.class,
        fields = {
            @FieldResult(name = "id", column = "c_id"),
            @FieldResult(name = "fullName", column = "c_name"),
            @FieldResult(name = "tier", column = "c_tier"),
            @FieldResult(name = "version", column = "c_version")
        }
    ),
    columns = {
        @ColumnResult(
            name = "order_count",
            type = Long.class
        ),
        @ColumnResult(
            name = "paid_total",
            type = BigDecimal.class
        )
    }
)
```

Thứ tự phần tử của kết quả:

```text
row[0] -> Customer
row[1] -> Long orderCount
row[2] -> BigDecimal paidTotal
```

### 9.3. Chạy bằng `createNamedQuery`

Vì `Customer` đã khai báo:

```java
@NamedNativeQuery(
    name = "Customer.orderOverview",
    query = "...",
    resultSetMapping = "CustomerOrderOverview"
)
```

ta có thể gọi:

```java
List<?> rows = em.createNamedQuery(
    "Customer.orderOverview"
).getResultList();

for (Object item : rows) {
    Object[] row = (Object[]) item;

    Customer customer = (Customer) row[0];
    Long orderCount = (Long) row[1];
    BigDecimal paidTotal = (BigDecimal) row[2];

    System.out.printf(
        "%s: %d orders, paid total=%s%n",
        customer.getFullName(),
        orderCount,
        paidTotal.toPlainString()
    );
}
```

Ở mức kết quả Java, `Customer` là entity, còn hai giá trị thống kê không phải những trường managed state của entity. Chúng chỉ thuộc **projection của câu query**.

### 9.4. Chạy SQL động bằng mapping name

Không bắt buộc phải dùng `@NamedNativeQuery`. Có thể dùng chính mapping trên với SQL truyền khi thực thi:

```java
String sql = """
    SELECT
        c.id AS c_id,
        c.full_name AS c_name,
        c.tier AS c_tier,
        c.row_version AS c_version,
        COUNT(o.id) AS order_count,
        COALESCE(SUM(CASE WHEN o.status = 'PAID'
                          THEN o.total_amount ELSE 0 END), 0)
            AS paid_total
    FROM customers c
    LEFT JOIN purchase_orders o
           ON o.customer_id = c.id
    WHERE c.tier = ?
    GROUP BY c.id, c.full_name, c.tier, c.row_version
    ORDER BY c.id
    """;

List<?> rows = em.createNativeQuery(
        sql,
        "CustomerOrderOverview"
    )
    .setParameter(1, "GOLD")
    .getResultList();
```

Phần `WHERE` thay đổi, nhưng nếu SQL vẫn trả đúng các alias và kiểu được mapping, cùng `CustomerOrderOverview` có thể được tái sử dụng.

**Lưu ý portability:** native SQL không được JPQL parser bảo vệ khỏi mọi khác biệt dialect. Với positional parameters, dạng `?` kết hợp `setParameter(1, value)` là lựa chọn portable cơ bản theo JPA. Native named parameters như `:tier` được nhiều provider hỗ trợ nhưng không nên coi đó là cam kết portable của mọi provider.

---

## 10. Kết quả entity khác kết quả scalar ở điểm nào?

### 10.1. Entity result là entity thuộc JPA persistence context

Nếu native query tạo `Customer` bằng `EntityResult`, object kết quả có **persistent identity** theo khóa chính và được provider quản lý như một entity tương ứng trong persistence context.

Trong transaction thích hợp:

```java
Customer customer = (Customer) em.createNativeQuery(
        """
        SELECT
            c.id AS c_id,
            c.full_name AS c_name,
            c.tier AS c_tier,
            c.row_version AS c_version
        FROM customers c
        WHERE c.id = ?
        """,
        "CustomerEntityAliased"
    )
    .setParameter(1, customerId)
    .getSingleResult();

// customer là entity result.
System.out.println(em.contains(customer));
```

Trong điều kiện entity result được quản lý bởi chính `em`, `em.contains(customer)` phản ánh object đó thuộc persistence context.

Khi entity managed được sửa qua domain method trong transaction, provider có thể dùng dirty checking để ghi thay đổi khi flush/commit.

### 10.2. ColumnResult không tạo managed entity

```java
@ColumnResult(name = "order_count", type = Long.class)
```

chỉ cho ra `Long`. Giá trị này không có identity trong JPA, không được dirty checking, và không tự “gắn” vào một `@Transient` field của `Customer`.

Không nên viết code với giả định:

```java
// Không tự xảy ra chỉ vì SELECT có order_count:
customer.getOrderCount();
```

trừ khi bạn thiết kế một phương thức tính/DTO khác.

### 10.3. Các entity cùng khóa chính trong một persistence context

Một persistence context duy trì **identity map**: cùng entity type và primary key thường được biểu diễn bởi cùng managed instance trong context đó.

Giả sử:

```java
Customer first = em.find(Customer.class, customerId);

Customer second = (Customer) em.createNativeQuery(
    """
    SELECT c.id AS c_id,
           c.full_name AS c_name,
           c.tier AS c_tier,
           c.row_version AS c_version
    FROM customers c
    WHERE c.id = ?
    """,
    "CustomerEntityAliased"
)
.setParameter(1, customerId)
.getSingleResult();
```

Khi cả hai do cùng context quản lý, chúng có cùng persistent identity. Không được coi native query là “bắt buộc tạo một Java object hoàn toàn độc lập” để tránh identity-map behavior.

### 10.4. Native query không tự bảo đảm làm mới entity đã managed

Giả sử context đã load `Customer#1` và đang giữ state:

```text
fullName = "An"
version = 2
```

Một transaction khác đổi tên và commit. Cùng context gọi native entity query lần nữa không nên được dùng như một phương án bảo đảm lấy **snapshot mới nhất** của các field entity.

Provider phải duy trì identity của managed entity; cache/persistence-context state có thể ảnh hưởng kết quả entity mà ứng dụng nhìn thấy. Nếu cần dữ liệu mới, cân nhắc:

- Transaction/context mới.
- `em.refresh(managedEntity)` nếu chấp nhận ghi đè pending local changes.
- `@Version` và optimistic locking khi cập nhật.
- Isolation phù hợp với yêu cầu nghiệp vụ.

**`EntityResult` là công cụ ánh xạ, không phải cơ chế tự động giải quyết stale data.**

### 10.5. Entity result không phải read-only DTO

Khi SQL chỉ phục vụ báo cáo và ứng dụng không muốn:

- Managed entities.
- Dirty checking.
- Identity map.
- Lazy relationships.
- Rủi ro thao tác vô tình làm state thay đổi.

thì hãy dùng `ColumnResult`, `ConstructorResult` hoặc mapping DTO riêng. Không nên đưa entity vào mọi report chỉ vì có thể tạo được `EntityResult`.

---

## 11. Đặc biệt quan trọng: EntityResult cần đầy đủ thông tin ánh xạ

Một sai lầm phổ biến:

```sql
SELECT
    c.id AS c_id,
    c.full_name AS c_name
FROM customers c;
```

rồi cố tạo `Customer`, trong khi entity còn có `tier` và `@Version version`.

### 11.1. Tại sao partial entity nguy hiểm?

JPA entity không phải một DTO có thể chỉ khai báo vài field tùy ý. Provider cần dữ liệu phù hợp để tạo state entity nhất quán.

Theo nguyên tắc result-set mapping của JPA, kết quả **không được xác định** khi SQL không trả đủ dữ liệu cần thiết cho entity mapping. Thiếu primary key đặc biệt nghiêm trọng; thiếu version, discriminator hoặc các persistent fields cần thiết cũng có thể gây lỗi hoặc hành vi không portable.

**Không nên diễn giải:** “FieldResult chỉ map hai field, những field còn lại mặc định null là được.”

### 11.2. Cần mang theo những cột nào?

Tùy entity mapping, ít nhất phải xem:

- Cột khóa chính `@Id` hoặc toàn bộ khóa ghép.
- Các basic persistent fields của entity.
- Cột `@Version` nếu entity có optimistic locking.
- Cột discriminator nếu có inheritance cần phân biệt subclass.
- Các cột embedded/secondary table thuộc mapping.
- Các foreign key của association mà provider cần để dựng entity state.
- Các cột khác theo yêu cầu mapping/provider.

Danh sách cụ thể phụ thuộc entity; **không có mẹo cố định “chỉ SELECT id là JPA tự nạp các field còn lại”** cho native entity result.

### 11.3. Chỉ cần vài field? Hãy dùng DTO

Nếu dashboard chỉ cần:

```text
customer ID
customer name
number of orders
```

thì query:

```sql
SELECT c.id AS customer_id,
       c.full_name AS customer_name,
       COUNT(o.id) AS order_count
...
```

nên được map bằng scalar/DTO, **không ép dựng một Customer entity thiếu tier/version**.

### 11.4. Phương án `SELECT c.*` có luôn đủ không?

```sql
SELECT c.*
FROM customers c;
```

có thể phù hợp cho entity đơn giản khi các cột mapping khớp. Nhưng:

- SQL join thêm bảng khác có cột trùng tên làm alias mơ hồ.
- Entity có secondary tables/complex inheritance cần dữ liệu bổ sung.
- Schema migration hoặc alias conventions có thể làm truy vấn gãy.
- `SELECT c.*` không tự định nghĩa cách map một scalar `COUNT` bên cạnh.

Vì vậy, khi query đã phức tạp, **liệt kê cột cùng alias rõ ràng** là thói quen dễ review hơn.

---

## 12. Mapping alias SQL: đặt tên thống nhất từ đầu

Một quy ước trong native SQL join:

| Entity / giá trị | Alias đề xuất |
|---|---|
| Customer ID | `c_id` |
| Customer fullName | `c_name` |
| Customer tier | `c_tier` |
| Customer version | `c_version` |
| Order ID | `o_id` |
| Order total | `o_total` |
| Count of orders | `order_count` |
| Sum of paid orders | `paid_total` |

Trong SQL:

```sql
SELECT
    c.id AS c_id,
    c.full_name AS c_name,
    o.id AS o_id,
    o.total_amount AS o_total
FROM customers c
JOIN purchase_orders o
  ON o.customer_id = c.id;
```

Trong mapping:

```java
@FieldResult(name = "id", column = "c_id")
@FieldResult(name = "fullName", column = "c_name")
```

Những alias rõ ràng giúp:

- Tránh trùng tên `id` từ hai bảng.
- Tách tên SQL physical column khỏi Java persistent property.
- Giảm nhầm lẫn khi thêm cột.
- Dễ đọc lỗi `column not found`.
- Có thể tái sử dụng mapping với nhiều SQL query có cùng output contract.

### 12.1. Quoting và case sensitivity

Một số database/JDBC driver chuẩn hóa nhãn cột thành chữ hoa/chữ thường hoặc xử lý quoted identifiers khác nhau.

Ví dụ:

```sql
SELECT c.id AS "cId" FROM customers c;
```

và:

```sql
SELECT c.id AS cId FROM customers c;
```

có thể cho metadata column label khác nhau tùy database.

Để hạn chế lỗi:

- Chọn alias đơn giản như `c_id`, `order_count`.
- Tránh từ khóa SQL làm alias.
- Hạn chế case-sensitive quoted alias trừ khi có lý do.
- Kiểm thử query trên database mục tiêu.
- Giữ đúng nhãn SQL với `@FieldResult(column=...)` và `@ColumnResult(name=...)`.

`@FieldResult.name` không phụ thuộc SQL case, vì nó là thuộc tính Java; còn `column` phải khớp nhãn result set được provider nhận.

---

## 13. `@EmbeddedId` và `FieldResult` với dấu chấm

Một trường hợp nâng cao nhưng rất quan trọng là **entity có khóa ghép**.

Giả sử bảng dòng hóa đơn:

```text
invoice_lines
  invoice_id       (PK part 1)
  line_number      (PK part 2)
  sku
  quantity
```

Khóa chính là cặp:

```text
(invoice_id, line_number)
```

### 13.1. Khóa nhúng `InvoiceLineId`

```java
package com.example.nativesql;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class InvoiceLineId implements Serializable {

    @Column(name = "invoice_id")
    private Long invoiceId;

    @Column(name = "line_number")
    private Integer lineNumber;

    protected InvoiceLineId() {}

    public InvoiceLineId(Long invoiceId, Integer lineNumber) {
        this.invoiceId = Objects.requireNonNull(invoiceId);
        this.lineNumber = Objects.requireNonNull(lineNumber);
    }

    public Long getInvoiceId() {
        return invoiceId;
    }

    public Integer getLineNumber() {
        return lineNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof InvoiceLineId that)) return false;

        return Objects.equals(invoiceId, that.invoiceId)
            && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(invoiceId, lineNumber);
    }
}
```

`equals`/`hashCode` giúp ID class diễn đạt identity ổn định. Một embeddable key phải tuân thủ yêu cầu JPA về constructor/access/serialization và không nên thay đổi tùy tiện sau khi đã dùng làm identity.

### 13.2. Entity `InvoiceLine`

```java
package com.example.nativesql;

import jakarta.persistence.*;

@Entity
@Table(name = "invoice_lines")

@SqlResultSetMapping(
    name = "InvoiceLineNativeMapping",
    entities = @EntityResult(
        entityClass = InvoiceLine.class,
        fields = {
            @FieldResult(
                name = "id.invoiceId",
                column = "invoice_key_alias"
            ),
            @FieldResult(
                name = "id.lineNumber",
                column = "line_no_alias"
            ),
            @FieldResult(
                name = "sku",
                column = "sku_alias"
            ),
            @FieldResult(
                name = "quantity",
                column = "quantity_alias"
            )
        }
    )
)

public class InvoiceLine {

    @EmbeddedId
    private InvoiceLineId id;

    @Column(name = "sku", nullable = false, length = 64)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private Integer quantity;

    protected InvoiceLine() {}

    public InvoiceLineId getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public Integer getQuantity() {
        return quantity;
    }
}
```

Các đường dẫn:

```java
name = "id.invoiceId"
name = "id.lineNumber"
```

không phải tên cột SQL. Chúng mô tả **thuộc tính bên trong embeddable ID**.

### 13.3. SQL và kết quả

```sql
SELECT
    il.invoice_id AS invoice_key_alias,
    il.line_number AS line_no_alias,
    il.sku AS sku_alias,
    il.quantity AS quantity_alias
FROM invoice_lines il
WHERE il.invoice_id = ?;
```

Java:

```java
List<?> raw = em.createNativeQuery(
        """
        SELECT
            il.invoice_id AS invoice_key_alias,
            il.line_number AS line_no_alias,
            il.sku AS sku_alias,
            il.quantity AS quantity_alias
        FROM invoice_lines il
        WHERE il.invoice_id = ?
        """,
        "InvoiceLineNativeMapping"
    )
    .setParameter(1, invoiceId)
    .getResultList();

for (Object item : raw) {
    InvoiceLine line = (InvoiceLine) item;
    InvoiceLineId id = line.getId();

    System.out.println(
        id.getInvoiceId() + "-" +
        id.getLineNumber() + ": " +
        line.getSku()
    );
}
```

### 13.4. Không được thiếu một phần khóa ghép

Sai:

```sql
SELECT
    il.invoice_id AS invoice_key_alias,
    il.sku AS sku_alias
FROM invoice_lines il;
```

Vì khóa là **`(invoice_id, line_number)`**, nếu không trả `line_number`, provider không có đủ identity để phân biệt hai dòng trong cùng hóa đơn.

Đây không phải trường hợp có thể sửa bằng cách cho `lineNumber = null`: entity có khóa ghép chưa đầy đủ là không hợp lệ cho native entity result portable.

---

## 14. `@Embedded` thông thường và đường dẫn trong `FieldResult`

`FieldResult` với dấu chấm cũng hữu ích khi cần diễn đạt thuộc tính thuộc một **embeddable**.

Giả sử entity `Customer` có địa chỉ:

```java
@Embeddable
public class Address {

    @Column(name = "city")
    private String city;

    @Column(name = "postal_code")
    private String postalCode;

    protected Address() {}
}

@Embedded
private Address shippingAddress;
```

Native SQL có alias:

```sql
SELECT
    c.city AS ship_city,
    c.postal_code AS ship_zip
FROM customers c;
```

Trong mapping đầy đủ cho entity, có thể dùng đường dẫn thuộc tính nhúng:

```java
@FieldResult(
    name = "shippingAddress.city",
    column = "ship_city"
),
@FieldResult(
    name = "shippingAddress.postalCode",
    column = "ship_zip"
)
```

Đây là **phần mở rộng của ví dụ**; khi thực sự gắn `Address` vào `Customer`, truy vấn cũng phải trả **mọi trường entity cần thiết** (id, fullName, tier, version, và các thuộc tính embedded liên quan), không chỉ hai cột địa chỉ.

### 14.1. Phân biệt embedded field và relationship

`shippingAddress.city` là đường dẫn field thuộc **embeddable value object** trong entity.

Với `@ManyToOne` hoặc `@OneToOne`, relationship được quản lý theo metadata FK và có những quy tắc riêng khi trả entity; không nên tùy ý coi mọi `relationship.someField` như một embedded property có thể map bằng hai `FieldResult` rồi mặc nhiên ghép cả object graph đúng.

Nếu native SQL trả nhiều entity có relationship, nên:

- Trả đủ primary key của mỗi entity.
- Khai báo `EntityResult` cho mỗi entity cần lấy.
- Trả đủ FK/related columns mà mapping yêu cầu.
- Kiểm thử lazy/eager association và identity map trên provider thực tế.

---

## 15. Mapping nhiều entity trong một result set

Ngoài dạng entity + scalar, `@SqlResultSetMapping` có thể có **nhiều `@EntityResult`**.

Ví dụ một SQL join lấy customer và order:

```sql
SELECT
    c.id AS c_id,
    c.full_name AS c_name,
    c.tier AS c_tier,
    c.row_version AS c_version,

    o.id AS o_id,
    o.customer_id AS o_customer_id,
    o.total_amount AS o_total,
    o.status AS o_status
FROM customers c
JOIN purchase_orders o
  ON o.customer_id = c.id;
```

Một mapping hai entity về mặt ý tưởng:

```java
@SqlResultSetMapping(
    name = "CustomerAndOrder",
    entities = {
        @EntityResult(
            entityClass = Customer.class,
            fields = {
                @FieldResult(name = "id", column = "c_id"),
                @FieldResult(name = "fullName", column = "c_name"),
                @FieldResult(name = "tier", column = "c_tier"),
                @FieldResult(name = "version", column = "c_version")
            }
        ),
        @EntityResult(
            entityClass = PurchaseOrder.class,
            fields = {
                @FieldResult(name = "id", column = "o_id"),
                @FieldResult(name = "totalAmount", column = "o_total"),
                @FieldResult(name = "status", column = "o_status"),
                @FieldResult(name = "customer", column = "o_customer_id")
            }
        )
    }
)
```

Mapping trên cần được **đặt ở class entity hoặc metadata thích hợp** để persistence unit đăng ký. Với một `@ManyToOne` FK đơn như `PurchaseOrder.customer`, `@FieldResult` có thể được dùng để chỉ alias của join column. Nếu relationship dùng **nhiều FK columns hoặc derived identity**, phải tuân thủ quy tắc đường dẫn/mapping của loại quan hệ đó; không tự giả định một alias FK đơn luôn đủ.

Khi truy vấn thành công, mỗi hàng có thể là:

```text
Object[] {
    Customer,
    PurchaseOrder
}
```

Ví dụ:

```java
List<?> rows = em.createNativeQuery(
    sql,
    "CustomerAndOrder"
).getResultList();

for (Object rawRow : rows) {
    Object[] row = (Object[]) rawRow;
    Customer customer = (Customer) row[0];
    PurchaseOrder order = (PurchaseOrder) row[1];

    System.out.println(
        customer.getFullName() + " / " +
        order.getId()
    );
}
```

### 15.1. Join nhiều-nhiều hàng không tạo nhiều Customer objects độc lập

Nếu khách An có hai order, SQL trả:

```text
(An, Order#101)
(An, Order#102)
```

Danh sách có **hai hàng**, nhưng `Customer#1` trong cùng persistence context có một persistent identity. Không nhầm:

- **Số hàng result set SQL**.
- **Số object Java được provider quản lý**.
- **Số phần tử trong collection `customer.orders`**.

### 15.2. Hai EntityResult không tự populate collection

Việc một query trả cả `Customer` lẫn `PurchaseOrder` **không có nghĩa** `customer.getOrders()` đã được provider gán đầy đủ từ các hàng SQL như một fetch join có collection mapping.

Provider có thể quản lý entity references và relationship theo metadata, nhưng đừng dựa vào việc result-set mapping đơn giản tự tái tạo mọi collection.

Nếu muốn tải đầy đủ graph, hãy đánh giá:

- JPQL `JOIN FETCH` hoặc entity graph nếu biểu diễn được nhu cầu.
- Provider-specific native SQL result transformer/fetch mapping khi thực sự cần.
- Hai query: lấy parent, rồi lấy children theo IDs.
- DTO projection nếu chỉ cần báo cáo.

### 15.3. Phạm vi và tính portable của FK mapping

Mẫu `@FieldResult(name="customer", column="o_customer_id")` minh họa FK đơn. Nếu entity `PurchaseOrder` chuyển sang `@EmbeddedId`/`@MapsId` hoặc association với composite foreign key, mapping phức tạp hơn. Tại các trường hợp nhiều khóa/đa bảng/inheritance, hãy dựa vào đặc tả và kiểm tra provider thay vì áp dụng máy móc ví dụ FK đơn.

**Quan trọng:** không bắt buộc ứng dụng phải tạo mapping nhiều entity chỉ vì SQL có `JOIN`. Một query chỉ muốn Customer + order count như phần 9 đơn giản hơn khi dùng **một EntityResult và một ColumnResult**.

---

## 16. `@NamedNativeQuery` và `resultSetMapping`

`@NamedNativeQuery` khai báo một native SQL query có tên, có thể tham chiếu result-set mapping.

```java
@NamedNativeQuery(
    name = "Customer.orderOverview",
    query = """
        SELECT ...
        FROM customers c
        LEFT JOIN purchase_orders o
               ON o.customer_id = c.id
        ...
        """,
    resultSetMapping = "CustomerOrderOverview"
)
```

Ở nơi gọi:

```java
List<?> rows = em.createNamedQuery(
    "Customer.orderOverview"
).getResultList();
```

Cần phân biệt hai cái tên:

- `Customer.orderOverview` là **tên của query**.
- `CustomerOrderOverview` là **tên của result-set mapping**.

Một mapping có thể được dùng bởi nhiều SQL queries nếu chúng trả về cùng tập alias/type cần thiết.

### 16.1. `@NamedNativeQuery` không bắt buộc đồng nghĩa “trả entity”

Named native query có thể trả:

- Entity.
- Scalar columns.
- DTO từ constructor result.
- Một tổ hợp entity + scalar + DTO, tùy mapping.

Nội dung SQL và `resultSetMapping` quyết định output contract.

### 16.2. Cấu hình mapping nằm ở đâu?

`@SqlResultSetMapping` thường được đặt trên một entity class hoặc trong ORM XML metadata được quản lý bởi persistence unit.

Nó **không phải annotation gắn trên một DTO tùy ý** rồi mong JPA tự quét mọi class trong classpath. Provider phải biết metadata của lớp khai báo mapping.

Một cách tổ chức:

```text
src/main/java/
  com/example/nativesql/
    Customer.java        <- @Entity + @SqlResultSetMapping(s)
    PurchaseOrder.java   <- @Entity
    CustomerReportDto.java
    CustomerRepository.java
```

Các mapping names nên độc nhất trong phạm vi persistence unit. Không khai báo trùng tên ở nhiều entity khác nhau rồi mong provider chọn “mapping gần nhất”.

### 16.3. Có cần dùng `@NamedNativeQuery` cho mọi SQL không?

Không. Một truy vấn có SQL động hoặc filter khác nhau có thể dùng:

```java
em.createNativeQuery(sql, "CustomerOrderOverview");
```

Việc đặt mapping tĩnh không bắt buộc đặt SQL tĩnh.

Ngược lại, khi query dùng ở nhiều nơi và không đổi cấu trúc, named native query giúp giữ SQL và mapping contract gần nhau để review.

---

## 17. `ColumnResult` với `COUNT`: kiểu Java dễ gây nhầm

Một trong các lỗi runtime phổ biến:

```java
Long count = (Long) em.createNativeQuery(
    "SELECT COUNT(*) FROM purchase_orders"
).getSingleResult();
```

Truy vấn native không có mapping tường minh có thể trả `BigInteger` hoặc một kiểu `Number` khác tùy provider/driver. Ép trực tiếp sang `Long` có thể gây:

```text
ClassCastException:
java.math.BigInteger cannot be cast to java.lang.Long
```

### 17.1. Hai hướng xử lý

**Cách A — Scalar thông thường:**

```java
Number number = (Number) em.createNativeQuery(
    "SELECT COUNT(*) FROM purchase_orders"
).getSingleResult();

long count = number.longValue();
```

Cách này linh hoạt cho các kiểu `Number` tương thích nhưng **không tự bảo vệ khỏi overflow** khi giá trị quá lớn so với `long`.

**Cách B — `ColumnResult(type=Long.class)`:**

```java
@ColumnResult(
    name = "order_count",
    type = Long.class
)
```

và SQL phải có alias `AS order_count`.

### 17.2. `SUM` trên DECIMAL

Với tiền tệ:

```sql
SELECT SUM(total_amount) AS total_revenue
FROM purchase_orders;
```

nên thiết kế projection/DTO mong đợi `BigDecimal` khi muốn giữ decimal precision:

```java
@ColumnResult(
    name = "total_revenue",
    type = BigDecimal.class
)
```

Không tự đổi `BigDecimal` sang `Double` để “ép cho dễ cast”; floating-point có thể làm mất độ chính xác của số thập phân.

### 17.3. `COUNT` và `SUM` khác nhau về null

`COUNT` trả số lượng; khi không có hàng, `COUNT(*)` vẫn trả **0**.

`SUM(expression)` có thể trả **null** nếu không có giá trị để tính tổng. Muốn báo cáo 0, cân nhắc:

```sql
COALESCE(SUM(o.total_amount), 0) AS total_revenue
```

Nhưng cần kiểm tra DB/type coercion vì literal `0` là integer còn tổng có thể là DECIMAL. Tùy yêu cầu, có thể xử lý `null` ở DTO để tránh khác biệt dialect.

### 17.4. `ColumnResult(type=...)` không thay thế Java validation

Nếu giá trị DB không thể chuyển thành kiểu yêu cầu:

```java
@ColumnResult(name = "text_amount", type = Long.class)
```

nhưng SQL trả `'N/A'`, provider có thể báo lỗi convert. Annotation chỉ khai báo **kỳ vọng kiểu**, không làm biến mất dữ liệu bẩn hoặc tự tạo giá trị hợp lệ.

---

## 18. `@ConstructorResult`: khi nào nên dùng thay entity + scalar?

Bài này tập trung vào `EntityResult`, `FieldResult` và `ColumnResult`, nhưng cần biết thêm `@ConstructorResult` vì nó là lựa chọn thường đúng cho **báo cáo chỉ đọc**.

Giả sử màn hình chỉ cần:

```text
Tên khách
Số đơn
```

Không cần entity managed, version hay collection.

### 18.1. DTO

```java
package com.example.nativesql;

public record CustomerCountDto(
    String customerName,
    Long orderCount
) {}
```

### 18.2. Mapping constructor

Khai báo trên một managed entity class phù hợp, ví dụ `Customer`:

```java
@SqlResultSetMapping(
    name = "CustomerCountDtoMapping",
    classes = @ConstructorResult(
        targetClass = CustomerCountDto.class,
        columns = {
            @ColumnResult(
                name = "customer_name",
                type = String.class
            ),
            @ColumnResult(
                name = "order_count",
                type = Long.class
            )
        }
    )
)
```

### 18.3. SQL

```sql
SELECT
    c.full_name AS customer_name,
    COUNT(o.id) AS order_count
FROM customers c
LEFT JOIN purchase_orders o
       ON o.customer_id = c.id
GROUP BY c.id, c.full_name
ORDER BY c.id;
```

### 18.4. Truy xuất DTO

```java
List<?> rows = em.createNativeQuery(
    sql,
    "CustomerCountDtoMapping"
).getResultList();

for (Object row : rows) {
    CustomerCountDto dto = (CustomerCountDto) row;

    System.out.println(
        dto.customerName() + ": " + dto.orderCount()
    );
}
```

Khi `classes` chỉ khai báo một `ConstructorResult`, mỗi hàng là một instance DTO theo constructor.

**Phân biệt:**

| Tiêu chí | `EntityResult` | `ConstructorResult` |
|---|---|---|
| Lớp đích | JPA entity. | Lớp Java có constructor phù hợp, thường DTO. |
| Primary key bắt buộc? | Có, cần đủ identity entity. | Không, trừ khi constructor nghiệp vụ yêu cầu. |
| Có managed lifecycle? | Có theo semantics entity result. | DTO thông thường không được JPA quản lý. |
| Dirty checking? | Có trên managed entity trong transaction thích hợp. | Không áp dụng cho DTO. |
| Phù hợp báo cáo chỉ đọc? | Có thể nhưng đôi khi tốn kém/không cần thiết. | Thường rất phù hợp. |
| Muốn entity + scalar cạnh nhau? | `EntityResult` + `ColumnResult`. | Có thể thiết kế DTO thay thế hoặc kết hợp mapping phức hợp. |

**Lưu ý:** nếu `targetClass` của `ConstructorResult` là một entity class thực sự, trạng thái kết quả có các quy tắc đặc biệt tùy khóa chính và không được hiểu đơn giản như một DTO. Với nhu cầu read-only report, dùng class DTO độc lập sẽ rõ nghĩa nhất.

### 18.5. DTO constructor phải đúng thứ tự và kiểu

Trong:

```java
columns = {
    @ColumnResult(name = "customer_name", type = String.class),
    @ColumnResult(name = "order_count", type = Long.class)
}
```

constructor cần nhận:

```java
CustomerCountDto(String customerName, Long orderCount)
```

Không thể đảo hai tham số mà mong JPA tự tìm theo tên record component. `ConstructorResult` chọn constructor dựa trên thứ tự/type của `columns`.

---

## 19. Kết hợp `EntityResult`, `ColumnResult` và `ConstructorResult`

`@SqlResultSetMapping` cho phép một result set được khai báo với nhiều thành phần. Hình dung:

```java
@SqlResultSetMapping(
    name = "MixedReport",
    entities = @EntityResult(
        entityClass = Customer.class,
        fields = {
            @FieldResult(name = "id", column = "c_id"),
            @FieldResult(name = "fullName", column = "c_name"),
            @FieldResult(name = "tier", column = "c_tier"),
            @FieldResult(name = "version", column = "c_version")
        }
    ),
    columns = @ColumnResult(
        name = "order_count",
        type = Long.class
    )
)
```

Kết quả:

```text
Object[] row:
  [0] Customer
  [1] Long
```

Nếu mapping có thêm constructor results, thứ tự kết quả được đặc tả theo **nhóm kết quả**: entity results, constructor results, rồi scalar column results, theo thứ tự phần tử trong từng nhóm. Không tự suy ra rằng thứ tự `SELECT` luôn giống thứ tự `Object[]` khi một mapping khai báo nhiều nhóm.

Với ứng dụng mới, tránh một `Object[]` quá dài trộn nhiều loại nếu không cần thiết. Nếu output của API là một view/report rõ ràng, một DTO duy nhất từ `ConstructorResult` thường dễ kiểm soát hơn.

### 19.1. Không map một alias tùy tiện tới nhiều ý nghĩa mơ hồ

Ví dụ:

```java
@FieldResult(name = "id", column = "id"),
@ColumnResult(name = "id")
```

không sai về mặt ý tưởng nếu SQL thực sự cần trả cả entity ID lẫn scalar ID, nhưng dễ khiến người đọc nhầm rằng đó là hai giá trị độc lập. Nên đặt alias cụ thể hoặc tránh scalar trùng với entity field không cần thiết.

### 19.2. Thứ tự mapping và thứ tự SQL khác nhau

Giả sử SQL:

```sql
SELECT
    COUNT(o.id) AS order_count,
    c.full_name AS c_name,
    c.id AS c_id,
    c.tier AS c_tier,
    c.row_version AS c_version
...
```

Mapping vẫn có thể dùng alias để nhận các cột theo tên. Kết quả Java đối với `CustomerOrderOverview` vẫn theo contract:

```text
[ Customer, orderCount, paidTotal ]
```

miễn là SQL cung cấp mọi alias và type mà mapping yêu cầu. Không có `paid_total` thì phải sửa SQL hoặc mapping; không thể mong JPA điền mặc định.

---

## 20. Native SQL với tham số: SQL syntax và query portability

`createNativeQuery` nhận SQL trực tiếp, ví dụ:

```java
Query query = em.createNativeQuery(
    """
    SELECT
        c.id AS c_id,
        c.full_name AS c_name,
        c.tier AS c_tier,
        c.row_version AS c_version
    FROM customers c
    WHERE c.tier = ?
      AND c.id >= ?
    """,
    "CustomerEntityAliased"
);

query.setParameter(1, "GOLD");
query.setParameter(2, 100L);
```

Một số lưu ý:

- Native SQL dùng **tên bảng/cột SQL**, không phải `Customer.fullName`.
- `?` và `setParameter(1,...)` biểu diễn **positional parameter binding**.
- Tránh nối input người dùng trực tiếp vào SQL.
- Không cố parameterize tên bảng/cột hoặc tên hàm bằng query value parameter; query structure phải được kiểm soát bởi code.
- Provider hỗ trợ native named parameter có thể khác nhau; nếu yêu cầu portable theo JPA, đừng dựa vào một cú pháp extension chưa được kiểm chứng.
- Native query result mapping không tự chuyển SQL đặc thù PostgreSQL sang SQL hợp lệ cho Oracle/MySQL.

### 20.1. SQL injection vẫn là rủi ro

Không viết:

```java
String sql = "SELECT * FROM customers WHERE tier = '"
        + userTier + "'";
```

Dù có `@EntityResult` mapping chuẩn, truy vấn vẫn có thể bị injection vì cách xây SQL.

Dùng:

```java
String sql = """
    SELECT c.id AS c_id,
           c.full_name AS c_name,
           c.tier AS c_tier,
           c.row_version AS c_version
    FROM customers c
    WHERE c.tier = ?
    """;

em.createNativeQuery(sql, "CustomerEntityAliased")
  .setParameter(1, userTier);
```

Result mapping là vấn đề **chuyển kết quả**; parameter binding là vấn đề **truy vấn an toàn**. Không được dùng một cơ chế thay thế cơ chế kia.

---

## 21. `discriminatorColumn` trong `@EntityResult` khi có kế thừa

JPA hỗ trợ entity inheritance, ví dụ:

```text
PaymentRecord
   |
   +-- CardPaymentRecord
   |
   +-- BankTransferRecord
```

Với `InheritanceType.SINGLE_TABLE`, nhiều subclass được lưu chung một bảng, có cột discriminator xác định loại entity.

Ví dụ entity base:

```java
@Entity
@Table(name = "payment_records")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "payment_kind")
public abstract class PaymentRecord {

    @Id
    private Long id;

    @Column(name = "amount")
    private BigDecimal amount;

    protected PaymentRecord() {}
}
```

Nếu native SQL dùng:

```sql
SELECT
    p.id AS payment_id,
    p.amount AS payment_amount,
    p.payment_kind AS payment_type,
    ...
FROM payment_records p;
```

mapping có thể khai báo:

```java
@EntityResult(
    entityClass = PaymentRecord.class,
    discriminatorColumn = "payment_type",
    fields = {
        @FieldResult(name = "id", column = "payment_id"),
        @FieldResult(name = "amount", column = "payment_amount")
    }
)
```

`discriminatorColumn` là **alias trong result set** dùng để xác định subtype, không phải tên property Java `paymentKind`.

Đoạn này chỉ minh họa ý tưởng. Một mapping inheritance đầy đủ còn phải xử lý **các cột cần thiết của subclass cụ thể**, đúng hierarchy và database inheritance strategy. Không thể chỉ SELECT hai base fields rồi mong provider tự điền mọi thuộc tính của `CardPaymentRecord`.

**Sai lầm hay gặp:** entity kế thừa có discriminator nhưng native SQL không trả discriminator/child columns, dẫn tới provider không biết instantiate class nào hoặc nạp state không đầy đủ.

---

## 22. `EntityResult` không phải cách tự động sửa lỗi schema khác mapping

Một câu hỏi thường gặp:

> Database có cột `customer_id` nhưng entity `Customer.id`, chỉ cần `@FieldResult` là thay được `@Column` không?

Không. Hai loại metadata có nhiệm vụ khác nhau.

```java
@Id
@Column(name = "id")
private Long id;
```

là mapping **entity ↔ database schema** bình thường.

Trong result-set mapping:

```java
@FieldResult(name = "id", column = "c_id")
```

chỉ nói **alias `c_id` của một SQL result set cụ thể** chứa giá trị cho property `id`.

Nếu SQL:

```sql
SELECT c.id AS c_id FROM customers c;
```

thì `c_id` chỉ là nhãn của cột được SELECT. Nó không đổi tên cột thật trong database thành `c_id`.

### 22.1. Dùng đúng công cụ cho từng vấn đề

| Vấn đề | Công cụ |
|---|---|
| Database column có tên khác property Java. | `@Column(name=...)` hoặc `@JoinColumn(name=...)`. |
| Native SQL SELECT dùng alias khác tên column mapping. | `@FieldResult`. |
| Query trả một tính toán không phải persistent property. | `@ColumnResult`. |
| Muốn dựng một read-only DTO từ nhiều cột. | `@ConstructorResult`. |
| Muốn đổi cấu trúc bảng hoặc FK. | Database migration / DDL. |
| Muốn query bằng tên entity thay vì bảng SQL. | JPQL / Criteria API. |
| Muốn tùy biến SQL riêng database. | Native SQL / provider-specific function. |

### 22.2. Mapping native result không cập nhật schema

Đặt:

```java
@ColumnResult(name = "paid_total")
```

không tạo cột `paid_total` trong bảng. Nó chỉ trỏ tới alias của biểu thức truy vấn, ví dụ:

```sql
SUM(...) AS paid_total
```

Nếu SQL không tạo alias đó, mapping không có dữ liệu để đọc.

---

## 23. Truy vấn aggregate và alias: `GROUP BY` đúng là phần của SQL

Để map một `Customer` cùng `COUNT(o.id)`, SQL cần aggregate đúng:

```sql
SELECT
    c.id AS c_id,
    c.full_name AS c_name,
    c.tier AS c_tier,
    c.row_version AS c_version,
    COUNT(o.id) AS order_count,
    COALESCE(SUM(o.total_amount), 0) AS total_amount
FROM customers c
LEFT JOIN purchase_orders o
  ON o.customer_id = c.id
GROUP BY c.id, c.full_name, c.tier, c.row_version;
```

Các cột non-aggregate của `Customer` được đưa vào `GROUP BY` theo cách rõ ràng, tránh dựa vào mở rộng SQL của một database cho phép nhóm chỉ theo PK.

Đặc biệt, nếu entity sau này có thêm persistent fields, một SQL “dựng nguyên entity” kết hợp aggregate cần được rà soát lại:

- SELECT có đủ entity columns không?
- GROUP BY có phù hợp với các cột non-aggregate không?
- Query có còn một hàng cho mỗi customer không?
- Alias mapping có còn đúng không?

### 23.1. Một SQL report có thể dễ hơn bằng DTO

Nếu `Customer` có hàng chục persistent fields, SELECT đầy đủ các field rồi GROUP BY tất cả để chỉ lấy tên và count có thể quá nặng.

Thay vào đó:

```sql
SELECT
    c.full_name AS customer_name,
    COUNT(o.id) AS order_count
FROM customers c
LEFT JOIN purchase_orders o
  ON o.customer_id = c.id
GROUP BY c.id, c.full_name;
```

dùng `ConstructorResult` là thiết kế đơn giản hơn.

### 23.2. Đừng giả định count đúng khi join nhiều collection

Nếu SQL join cả order lẫn địa chỉ giao hàng:

```sql
FROM customers c
LEFT JOIN purchase_orders o ON ...
LEFT JOIN shipping_addresses a ON ...
```

một customer có 2 orders và 3 addresses có thể tạo **6 hàng**. Khi đó `COUNT(o.id)` có thể trả 6 thay vì 2.

Điều này là lỗi **SQL join/aggregation**, `@ColumnResult` không tự sửa nó. Cân nhắc:

- `COUNT(DISTINCT o.id)` khi ý nghĩa phù hợp.
- Subquery tổng hợp trước khi join.
- Tách thống kê thành các query riêng.
- Chọn đúng grain của dữ liệu report.

---

## 24. Entity có association: cần hiểu cột FK và lazy loading

Trong `PurchaseOrder`:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
```

Một native entity result cho `PurchaseOrder` cần cân nhắc cột FK `customer_id`. Provider có thể dùng FK để biểu diễn reference/proxy của `Customer` theo mapping.

Nếu query bỏ FK trong lúc cố tạo entity `PurchaseOrder`, provider có thể thiếu dữ liệu cần thiết để dựng association state.

**Nhưng:** việc SQL có `customer_id` **không có nghĩa** `Customer` cũng được fetch toàn bộ. FK đủ để biết reference khác với việc tải mọi field của entity liên quan.

### 24.1. Native entity result không làm LAZY biến thành EAGER

Truy vấn:

```sql
SELECT o.id, o.customer_id, o.total_amount, o.status
FROM purchase_orders o;
```

dùng result class `PurchaseOrder.class` không có yêu cầu tự tải collection của Customer.

Nếu code sau đó gọi:

```java
order.getCustomer().getFullName()
```

provider có thể cần load customer theo fetch plan/transaction/persistence context.

### 24.2. SQL join không đồng nghĩa fetch join JPQL

```sql
SELECT o.*, c.*
FROM purchase_orders o
JOIN customers c
  ON c.id = o.customer_id;
```

không tự biến thành:

```sql
SELECT o FROM PurchaseOrder o JOIN FETCH o.customer
```

của JPQL. Native SQL và JPQL fetch join dùng cơ chế ánh xạ khác nhau; nếu trả hai entity, cần mapping tương ứng, còn nếu chỉ trả một entity thì cột join không được provider tự coi là toàn bộ graph theo mong đợi của developer.

### 24.3. N+1 và round trip

Một SQL phức tạp không tự bảo đảm hiệu năng tốt hơn JPQL. Native query có thể trả rất nhiều rows; khi truy cập các association LAZY sau đó, ứng dụng vẫn có thể gặp N+1 queries.

Chọn native SQL khi thực sự cần khả năng SQL, chứ không phải chỉ vì “viết native là tự động tối ưu”.

---

## 25. Cập nhật entity từ native result: transaction và optimistic locking

Nếu `EntityResult` trả managed `Customer`, ta vẫn phải áp dụng quy tắc transaction JPA.

Ví dụ entity có domain method:

```java
public void changeTier(String newTier) {
    if (newTier == null || newTier.isBlank()) {
        throw new IllegalArgumentException("Tier không hợp lệ");
    }
    this.tier = newTier;
}
```

Trong một transaction resource-local:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Customer customer = (Customer) em.createNativeQuery(
            """
            SELECT c.id AS c_id,
                   c.full_name AS c_name,
                   c.tier AS c_tier,
                   c.row_version AS c_version
            FROM customers c
            WHERE c.id = ?
            """,
            "CustomerEntityAliased"
        )
        .setParameter(1, customerId)
        .getSingleResult();

    customer.changeTier("PLATINUM");

    // Managed entity được dirty checking.
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Để dùng đoạn này, bổ sung `changeTier` vào `Customer` và import `jakarta.persistence.*`. Ví dụ chỉ nhấn mạnh lifecycle; quyền được đổi tier và invariant domain là trách nhiệm tầng ứng dụng/domain.

### 25.1. `@Version` vẫn quan trọng

Khi `Customer` có `@Version`, provider dùng version trong optimistic locking để phát hiện một số cập nhật dựa trên state cũ.

Native entity query không được phép biến optimistic locking thành “không cần version”; `@FieldResult(name="version",column="c_version")` chính là một phần của state ánh xạ.

### 25.2. Native SQL UPDATE không tự đồng bộ managed state

Phân biệt entity SELECT từ native SQL với việc tự chạy native UPDATE:

```java
em.createNativeQuery(
    "UPDATE customers SET tier = ? WHERE id = ?"
)
.setParameter(1, "GOLD")
.setParameter(2, customerId)
.executeUpdate();
```

Lệnh native UPDATE này không tự đi qua dirty checking, entity callbacks và version handling của managed entity như một cập nhật entity bình thường.

Nếu cùng persistence context đã giữ `Customer#1`, giá trị `tier` trong managed object có thể **stale** sau UPDATE trực tiếp. Khi cần:

- Tránh trộn managed entity writes với bulk native SQL trong cùng unit of work nếu không cần.
- Chủ động `flush` trước khi SQL phụ thuộc pending changes.
- `refresh` hoặc `clear` theo trình tự có chủ đích.
- Bảo đảm DB UPDATE xử lý version/constraints thích hợp nếu concurrency là yêu cầu.

### 25.3. Rollback không tự hoàn tác object Java

Nếu transaction rollback sau `customer.changeTier`, object Java trong memory có thể vẫn mang tier mới dù database đã rollback. Không tái sử dụng context của transaction lỗi để quyết định nghiệp vụ như thể state đã được khôi phục hoàn toàn.

---

## 26. Bẫy lớn: kết quả native SQL có nhiều hàng cho một entity

Giả sử truy vấn:

```sql
SELECT
    c.id AS c_id,
    c.full_name AS c_name,
    c.tier AS c_tier,
    c.row_version AS c_version
FROM customers c
JOIN purchase_orders o
  ON o.customer_id = c.id;
```

Với An có 2 orders, SQL trả Customer An **hai lần** ở hai hàng.

Nếu mapping `CustomerEntityAliased`, `getResultList()` có thể phản ánh nhiều row kết quả cùng persistent identity `Customer#1`. Persistence context có thể duy trì **cùng instance**, nhưng số phần tử danh sách không nhất thiết bằng số identity duy nhất.

Không nên nhầm:

```text
Danh sách rows:       [Customer#1, Customer#1, Customer#3]
Identity map:          Customer#1, Customer#3
```

### 26.1. Khử trùng ở đúng nơi

Khi muốn mỗi customer một lần:

```sql
SELECT DISTINCT
    c.id AS c_id,
    c.full_name AS c_name,
    c.tier AS c_tier,
    c.row_version AS c_version
FROM customers c
JOIN purchase_orders o
  ON o.customer_id = c.id;
```

hoặc dùng `EXISTS` trong SQL để chỉ kiểm tra có order:

```sql
SELECT
    c.id AS c_id,
    c.full_name AS c_name,
    c.tier AS c_tier,
    c.row_version AS c_version
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM purchase_orders o
    WHERE o.customer_id = c.id
);
```

`DISTINCT` ở native SQL áp lên **toàn bộ cột projection**, không tự hiểu “distinct theo customer ID” nếu bạn còn select các trường child khác nhau.

### 26.2. Phân trang trên JOIN

Nếu dùng:

```sql
SELECT c.*, o.id
FROM customers c
JOIN purchase_orders o
  ON o.customer_id = c.id
ORDER BY c.id
```

rồi giới hạn 10 SQL rows, bạn có thể chỉ nhận vài customer có nhiều orders chứ không phải 10 customer khác nhau.

Tùy yêu cầu, hãy:

1. Phân trang customer IDs trước.
2. Tải entity/report cho danh sách IDs đó.
3. Hoặc dùng SQL window/CTE có thiết kế grain phù hợp.

Result mapping không thể sửa một lỗi phân trang xảy ra **trước khi dữ liệu đến JPA**.

---

## 27. Lựa chọn giữa `@FieldResult` và aliases khớp tên cột gốc

Đôi khi bạn có thể tránh liệt kê nhiều `FieldResult` nếu native SQL trả tất cả entity columns với tên/alias tương ứng mapping.

Ví dụ:

```java
@SqlResultSetMapping(
    name = "CustomerDirect",
    entities = @EntityResult(
        entityClass = Customer.class
    )
)
```

SQL:

```sql
SELECT
    c.id,
    c.full_name,
    c.tier,
    c.row_version
FROM customers c;
```

Trong trường hợp mapping rõ ràng và provider nhận đúng cột, `FieldResult` có thể không cần.

Nhưng nếu SQL đổi:

```sql
c.full_name AS customer_display_name
```

thì nên khai báo:

```java
@FieldResult(
    name = "fullName",
    column = "customer_display_name"
)
```

**Không nên lẫn lộn hai chiến lược trong một query phức tạp:** nếu dùng alias tường minh cho phần lớn cột, hãy cân nhắc liệt kê đủ field để người đọc có thể kiểm tra output contract một cách rõ ràng.

### 27.1. FieldResult không cần phải map scalar

```sql
COUNT(o.id) AS order_count
```

không phải persistent field của `Customer`. Map nó bằng `ColumnResult`, không tạo một `@FieldResult(name="orderCount",...)` tưởng tượng.

### 27.2. Cột entity bị alias giống cột khác

Nếu hai entity đều có `row_version` và cùng select:

```sql
SELECT c.row_version, o.row_version
```

provider có thể không biết nhãn nào dành cho entity nào. Chọn:

```sql
SELECT
    c.row_version AS c_version,
    o.row_version AS o_version
```

và map riêng.

---

## 28. Xử lý kết quả tùy số thành phần mapping

Một quy tắc thực hành:

| Mapping khai báo | Hình dạng phần tử kết quả thường gặp |
|---|---|
| 1 `EntityResult` | Entity object. |
| 1 `ColumnResult` | Scalar object. |
| 1 `ConstructorResult` | DTO/class instance. |
| 2 `ColumnResult` | `Object[]` gồm 2 scalar. |
| 1 entity + 1 scalar | `Object[]` gồm entity, scalar. |
| 2 entity | `Object[]` gồm hai entity. |
| 1 entity + 2 scalar | `Object[]` gồm entity và hai scalar. |

Đừng viết một helper ép tất cả native query results về `Object[]` nếu có query chỉ trả một entity hoặc một scalar.

### 28.1. Xử lý output trước khi trả ra API

Một lớp DTO đơn giản:

```java
package com.example.nativesql;

import java.math.BigDecimal;

public record CustomerOverviewDto(
    Long customerId,
    String fullName,
    String tier,
    long orderCount,
    BigDecimal paidTotal
) {}
```

Mapping kết quả trong service:

```java
List<CustomerOverviewDto> dtos = new ArrayList<>();

for (Object item : em.createNamedQuery(
        "Customer.orderOverview"
    ).getResultList()) {

    Object[] row = (Object[]) item;
    Customer customer = (Customer) row[0];
    Long count = (Long) row[1];
    BigDecimal paid = (BigDecimal) row[2];

    dtos.add(
        new CustomerOverviewDto(
            customer.getId(),
            customer.getFullName(),
            customer.getTier(),
            count,
            paid
        )
    );
}
```

DTO có thể được trả qua API mà không làm lộ managed entity. Nếu toàn bộ mục tiêu chỉ là DTO, `ConstructorResult` có thể loại bỏ bước dựng entity không cần thiết.

### 28.2. Đừng giữ entity ngoài transaction như một DTO

Một entity còn tham chiếu LAZY relationships có thể ném exception khi truy cập ngoài persistence context. Ngoài ra, nếu trực tiếp serialize entity, API có thể vô tình lộ trường nội bộ hoặc tạo vòng tham chiếu giữa associations.

DTO giúp xác định response contract rõ ràng hơn; việc mapping native query trả managed entity không làm mất nhu cầu thiết kế tầng API.

---

## 29. Khi nào result mapping không portable?

**`@SqlResultSetMapping` là API chuẩn JPA**, nhưng SQL bên trong vẫn có thể **phụ thuộc database**.

Ví dụ:

```sql
SELECT
    DATE_TRUNC('month', o.placed_at) AS month_bucket,
    SUM(o.total_amount) AS total
FROM purchase_orders o
GROUP BY DATE_TRUNC('month', o.placed_at);
```

`DATE_TRUNC` là hàm của một số hệ quản trị, không phải SQL portable với mọi database.

Bạn có thể viết:

```java
@SqlResultSetMapping(
    name = "MonthlyTotals",
    columns = {
        @ColumnResult(name = "month_bucket"),
        @ColumnResult(name = "total", type = BigDecimal.class)
    }
)
```

nhưng điều đó **không khiến `DATE_TRUNC` tự chạy được trên mọi database**.

### 29.1. Những tầng có thể gây khác biệt

- Cú pháp SQL: `LIMIT`, `FETCH FIRST`, CTE, window functions.
- Kiểu cột: `JSONB`, `UUID`, arrays, native enum.
- Tên alias được JDBC driver chuẩn hóa.
- Kiểu kết quả của `COUNT`/`SUM`.
- Cách chuyển timestamp/timezone.
- Collation và case sensitivity.
- Quy tắc số học/rounding.
- Function signatures.
- Row count và loại result set khi dùng stored procedures.

### 29.2. Mức portable thực tế

Có thể phân loại:

1. **Portable JPA mapping**: annotation hợp lệ, field names đúng.
2. **Portable SQL semantics**: dùng cấu trúc SQL được các database mục tiêu hỗ trợ.
3. **Portable Java result type**: provider/driver trả kiểu phù hợp.

Cần xác nhận **cả ba**, không chỉ thấy annotation compile được.

---

## 30. Kiểm thử integration: đừng chỉ kiểm tra compile

`@SqlResultSetMapping` là metadata. Compiler Java có thể kiểm tra annotation type, nhưng không thể biết alias SQL có tồn tại trong database hay không.

Do đó, bài toán cần **integration test trên JPA provider và database mục tiêu**.

### 30.1. Test entity-only mapping

Giả sử:

- `EntityManagerFactory emf` đã cấu hình persistence unit.
- Database test có Customer#1.
- JUnit 5 được sử dụng.

```java
@Test
void nativeEntityMappingReadsCustomer() {
    EntityManager em = emf.createEntityManager();

    try {
        Customer customer = (Customer) em.createNativeQuery(
            """
            SELECT
                c.id AS c_id,
                c.full_name AS c_name,
                c.tier AS c_tier,
                c.row_version AS c_version
            FROM customers c
            WHERE c.id = ?
            """,
            "CustomerEntityAliased"
        )
        .setParameter(1, 1L)
        .getSingleResult();

        assertEquals(1L, customer.getId());
        assertEquals("An", customer.getFullName());
        assertTrue(em.contains(customer));
    } finally {
        em.close();
    }
}
```

Điều này kiểm tra:

- Mapping name đã được đăng ký.
- Các alias SQL đúng.
- Khóa chính được đọc.
- Entity result có thể được quản lý trong context.

### 30.2. Test entity + scalars

```java
@Test
void nativeOverviewPreservesCustomersWithNoOrders() {
    EntityManager em = emf.createEntityManager();

    try {
        List<?> rows = em.createNamedQuery(
            "Customer.orderOverview"
        ).getResultList();

        Map<String, Long> counts = new HashMap<>();

        for (Object item : rows) {
            Object[] row = (Object[]) item;

            Customer c = (Customer) row[0];
            Long count = (Long) row[1];
            BigDecimal total = (BigDecimal) row[2];

            assertNotNull(total);
            counts.put(c.getFullName(), count);
        }

        assertEquals(2L, counts.get("An"));
        assertEquals(0L, counts.get("Bình"));
        assertEquals(1L, counts.get("Chi"));
    } finally {
        em.close();
    }
}
```

Test đặc biệt cần **customer không có order** để phát hiện nếu ai đó vô tình đổi `LEFT JOIN` thành `INNER JOIN`.

### 30.3. Test composite ID

```java
@Test
void nativeMappingBuildsEmbeddedId() {
    EntityManager em = emf.createEntityManager();

    try {
        List<?> rows = em.createNativeQuery(
            """
            SELECT
                il.invoice_id AS invoice_key_alias,
                il.line_number AS line_no_alias,
                il.sku AS sku_alias,
                il.quantity AS quantity_alias
            FROM invoice_lines il
            WHERE il.invoice_id = ?
            """,
            "InvoiceLineNativeMapping"
        )
        .setParameter(1, knownInvoiceId)
        .getResultList();

        for (Object item : rows) {
            InvoiceLine line = (InvoiceLine) item;

            assertNotNull(line.getId());
            assertEquals(
                knownInvoiceId,
                line.getId().getInvoiceId()
            );
            assertNotNull(line.getId().getLineNumber());
        }
    } finally {
        em.close();
    }
}
```

`knownInvoiceId` là fixture được tạo trong test, không phải biến có sẵn từ JPA. Bài test cần chuẩn bị bảng invoice_lines và dữ liệu tương ứng.

### 30.4. Test kiểu numeric

```java
@Test
void columnResultCountUsesLong() {
    EntityManager em = emf.createEntityManager();

    try {
        Object item = em.createNativeQuery(
            "SELECT COUNT(*) AS total_rows FROM customers",
            "SingleCount"
        ).getSingleResult();

        assertInstanceOf(Long.class, item);
    } finally {
        em.close();
    }
}
```

Nếu test không pass trên provider/database mục tiêu, cần xem loại chuyển đổi được hỗ trợ và sửa mapping hoặc cách đọc kết quả. Không nên “chữa” bằng một cast không đúng kiểu runtime.

### 30.5. Test trên database gần production

Nếu production dùng PostgreSQL mà test chỉ dùng một database in-memory khác, nhiều chi tiết có thể không được phát hiện:

- Alias case.
- Kiểu trả về `COUNT`.
- `SUM` và DECIMAL precision.
- SQL-specific syntax.
- Null/coalesce numeric type.
- Timezone.
- Cách JDBC driver báo duplicate column labels.

Với mapping quan trọng, chạy integration test bằng database/container gần môi trường production giúp phát hiện vấn đề sớm.

---

## 31. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| `Unknown SqlResultSetMapping` / không tìm thấy mapping | Mapping chưa được JPA đăng ký hoặc sai tên. | Đặt annotation ở entity/metadata được scan; dùng đúng mapping name. |
| `@FieldResult` không đọc được property | `name` dùng tên cột SQL thay vì Java property. | `name="fullName"`, không phải `name="full_name"`. |
| Provider báo không thấy column alias | `column`/`name` không khớp SQL result label. | Kiểm tra `AS alias` và metadata JDBC. |
| Join hai bảng cùng có `id` cho kết quả mơ hồ | Trùng label `id`. | Đặt `c_id`, `o_id` và khai báo FieldResult. |
| Entity result thiếu khóa chính | SQL chỉ SELECT vài fields. | Chọn đủ toàn bộ ID; với composite ID phải đủ các thành phần. |
| Entity có `@Version` nhưng query bỏ version | Result mapping thiếu dữ liệu entity cần thiết. | Chọn `row_version` và FieldResult tương ứng. |
| Entity inheritance tạo sai subtype | Thiếu discriminator/required subclass columns. | Dùng `discriminatorColumn` và SELECT đủ cột theo strategy. |
| Query trả entity nhưng code cast `Object[]` | Mapping chỉ có một `EntityResult`. | Đọc kết quả là entity. |
| Query trả `Object[]` nhưng code cast entity | Mapping có entity + scalar hoặc nhiều results. | Dùng `Object[]` với thứ tự đúng. |
| `COUNT(*)` gây `ClassCastException` khi cast Long | JDBC/provider trả `BigInteger` hoặc Number khác. | Dùng `@ColumnResult(type=Long.class)` hoặc xử lý `Number`. |
| `SUM` gây NPE | SQL không có hàng, SUM trả null. | `COALESCE` hoặc xử lý null ở DTO. |
| Mapping tiền bằng Double bị mất số lẻ chính xác | Dùng binary floating-point. | Dùng BigDecimal phù hợp DECIMAL. |
| Một customer xuất hiện nhiều lần | SQL join một-nhiều sinh nhiều rows. | DISTINCT/EXISTS/aggregation đúng grain. |
| Đếm customer không có đơn thành 1 | `COUNT(*)` trên LEFT JOIN. | `COUNT(o.id)`. |
| Native SQL trả Customer nhưng `orders` không được khởi tạo | Native result mapping không tự fetch collection. | Fetch plan, query riêng hoặc DTO theo nhu cầu. |
| Native query trả dữ liệu mới nhưng managed object vẫn cũ | Persistence context giữ entity cùng identity. | Context mới hoặc refresh có chủ đích. |
| Sau native UPDATE, entity managed không khớp DB | Native SQL bypass dirty checking của object. | Flush/clear/refresh/version policy phù hợp. |
| `@FieldResult` trên field `@Transient` không có tác dụng mong muốn | Field không phải persistent attribute. | `ColumnResult`/DTO thay vì ép thành entity property. |
| `ConstructorResult` không tìm được constructor | Thứ tự/kiểu column results không khớp. | Khai báo constructor chính xác, test runtime. |
| Dùng `@SqlResultSetMapping` như thể nó sửa schema | Nhầm result mapping và `@Column`/DDL. | Phân biệt metadata query result với entity schema. |
| Mapping đặt trên DTO nhưng không được phát hiện | DTO không được metadata scanning mặc định nhận. | Khai báo mapping trên entity/mapped metadata được quản lý. |
| SQL chạy trên DB test nhưng fail ở production | Native SQL/dialect/type khác nhau. | Integration test trên DB production-compatible. |
| Dùng SQL input nối chuỗi với user input | SQL injection. | Dùng positional parameters và whitelist cấu trúc. |
| Thêm cột entity mới khiến mapping cũ lỗi | Native result không còn đủ state entity. | Rà soát SQL alias và FieldResult khi entity mapping đổi. |
| Trả entity trực tiếp qua HTTP gây lỗi lazy loading | Entity không phải DTO API. | Chuyển sang DTO tại transaction boundary. |

---

## 32. Debug một lỗi mapping theo thứ tự nào?

Giả sử log:

```text
Could not resolve column position by name: c_version
```

Nên kiểm tra từng lớp.

**Bước 1 — Xem SQL thực sự được gửi tới database.**

SQL có `AS c_version` hay không? Một alias có bị đổi tên khi refactor `SELECT` không?

**Bước 2 — Xem metadata result set.**

JDBC driver báo column label nào? Alias có bị upper-case/lower-case hoặc quoted khác mong đợi không?

**Bước 3 — Xem `@FieldResult(column=...)` hoặc `@ColumnResult(name=...)`.**

Metadata có trỏ đúng alias không? Chỉ cần khác một chữ là provider có thể không đọc được cột.

**Bước 4 — Xem entity persistent property.**

`@FieldResult(name="version")` có đúng tên property trong entity? Field có bị đổi thành `rowVersion` trong refactor không?

**Bước 5 — Kiểm tra cột bắt buộc.**

ID, version, discriminator, composite ID components và các mapped fields cần thiết đã xuất hiện chưa?

**Bước 6 — Kiểm tra kiểu Java.**

SQL trả `NUMERIC` nhưng code ép `Long`? `SUM` có thể null? DTO constructor có đúng signature?

**Bước 7 — Kiểm tra hình dạng hàng Java.**

Một entity, một scalar, hay nhiều kết quả cần `Object[]`?

**Bước 8 — Kiểm tra persistence context.**

Nếu value “không mới”, liệu entity đã được load trước đó trong cùng context? Có native UPDATE nào bypass managed state không?

**Bước 9 — Kiểm tra provider/dialect.**

Nếu SQL có CTE/window/database function, lỗi có thể xuất phát từ SQL backend chứ không phải result mapping.

Quy trình này tách rõ **lỗi câu SQL**, **lỗi metadata mapping**, **lỗi Java type** và **lỗi persistence lifecycle**.

---

## 33. Lựa chọn thiết kế cho hệ thống production

### 33.1. Mapping tường minh tốt cho truy vấn ổn định

Nếu SQL báo cáo được dùng ở nhiều nơi và output contract không đổi:

```text
@NamedNativeQuery + @SqlResultSetMapping
```

có ưu điểm:

- SQL và metadata được đặt tên.
- Alias có thể review như một API nội bộ.
- Có thể test mapping tại startup/integration.
- Ít ép kiểu rải rác trong business service.

### 33.2. DTO tốt khi chỉ cần dữ liệu đọc

Nếu query chỉ trả một report với 5 cột và không cần sửa entity:

```text
Native SQL -> ConstructorResult -> DTO
```

thường rõ ràng và ít phụ thuộc entity lifecycle hơn:

```text
Native SQL
   |
   +-- customer_name
   +-- order_count
   +-- paid_total
   |
   v
CustomerReportDto
```

Không tạo managed entity chỉ để lấy một con số thống kê.

### 33.3. EntityResult tốt khi thực sự cần entity identity

Nếu use case cần Customer managed entity và thêm một metric để quyết định tiếp:

```text
Native SQL
   |
   +-- tất cả fields của Customer -> EntityResult
   +-- metric                  -> ColumnResult
   |
   v
[Customer, metric]
```

Lúc này `EntityResult` có lý do rõ ràng. Nhưng cần xem metric đó có thể thay đổi sau khi query chạy hay không; nó vẫn chỉ là một **giá trị được tính tại thời điểm truy vấn**.

### 33.4. Một số report không nên gắn với entity

Một kết quả như:

```text
month
total_sales
unique_buyers
conversion_rate
```

không có primary key của một entity cụ thể. Đừng tạo entity giả với `@Id` không ổn định chỉ để dùng `EntityResult`.

Dùng `ColumnResult`/`ConstructorResult` hoặc một read-only view model phù hợp.

### 33.5. Khi SQL thay đổi, coi alias như interface contract

Nếu mapping đòi:

```java
@FieldResult(name = "fullName", column = "c_name")
```

thì SQL phải luôn trả `c_name`. Đổi alias thành `customer_name` là một **breaking change** đối với mapping, dù giá trị SQL về mặt nghiệp vụ không đổi.

Để tránh lỗi refactor:

- Dùng alias convention nhất quán.
- Đặt test cho các named native queries.
- Giữ cùng mapping name chỉ khi output contract thực sự tương thích.
- Không tái sử dụng mapping cho một SELECT thiếu bớt entity fields.

---

## 34. Bài tập thực hành có lời giải

### Bài 1 — Entity Customer với alias khác tên cột

**Yêu cầu:** SQL trả `cust_pk`, `display_name`, `membership`, `version_no`; tạo `Customer`.

**Lời giải:**

```java
@SqlResultSetMapping(
    name = "CustomerExercise",
    entities = @EntityResult(
        entityClass = Customer.class,
        fields = {
            @FieldResult(name = "id", column = "cust_pk"),
            @FieldResult(name = "fullName", column = "display_name"),
            @FieldResult(name = "tier", column = "membership"),
            @FieldResult(name = "version", column = "version_no")
        }
    )
)
```

SQL tương ứng:

```sql
SELECT c.id AS cust_pk,
       c.full_name AS display_name,
       c.tier AS membership,
       c.row_version AS version_no
FROM customers c;
```

### Bài 2 — Đếm số đơn của mỗi customer, không cần entity

**Yêu cầu:** lấy `customer_id` và `order_count` thành hai scalars.

**Lời giải:**

```java
@SqlResultSetMapping(
    name = "CustomerCountScalars",
    columns = {
        @ColumnResult(name = "customer_id", type = Long.class),
        @ColumnResult(name = "order_count", type = Long.class)
    }
)
```

```sql
SELECT c.id AS customer_id,
       COUNT(o.id) AS order_count
FROM customers c
LEFT JOIN purchase_orders o
       ON o.customer_id = c.id
GROUP BY c.id;
```

Kết quả mỗi hàng là `Object[] {Long customerId, Long orderCount}`.

### Bài 3 — Chỉ cần một tổng doanh thu

**Yêu cầu:** trả tổng tiền các đơn đã PAID.

**Lời giải:**

```java
@SqlResultSetMapping(
    name = "PaidRevenue",
    columns = @ColumnResult(
        name = "paid_revenue",
        type = BigDecimal.class
    )
)
```

```sql
SELECT COALESCE(SUM(o.total_amount), 0)
       AS paid_revenue
FROM purchase_orders o
WHERE o.status = 'PAID';
```

Kết quả có một scalar. Cần integration test kiểu numeric thực tế.

### Bài 4 — Entity + số đơn

**Yêu cầu:** mỗi hàng gồm `Customer` managed và số lượng order.

**Lời giải:** dùng `entities = @EntityResult(...)` cho tất cả mapped fields của Customer, kèm:

```java
columns = @ColumnResult(
    name = "order_count",
    type = Long.class
)
```

Trong Java:

```java
Object[] row = (Object[]) raw;
Customer c = (Customer) row[0];
Long count = (Long) row[1];
```

### Bài 5 — Khóa ghép

**Yêu cầu:** entity có `@EmbeddedId InvoiceLineId` với `invoiceId` và `lineNumber`.

**Lời giải:**

```java
@FieldResult(
    name = "id.invoiceId",
    column = "invoice_key_alias"
),
@FieldResult(
    name = "id.lineNumber",
    column = "line_no_alias"
)
```

SQL phải trả **cả hai alias**.

### Bài 6 — SQL SELECT thiếu version

**Tình huống:** entity có `@Version` nhưng native SQL chỉ trả `id` và `full_name`.

**Đáp án:** không nên dùng làm EntityResult đầy đủ. Cần trả đủ persistent fields và `row_version`; nếu chỉ cần id/name, dùng `ColumnResult`/`ConstructorResult` tạo DTO.

### Bài 7 — Native COUNT trả BigInteger

**Tình huống:** `(Long) query.getSingleResult()` gây `ClassCastException`.

**Đáp án:** dùng `Number.longValue()` khi type compatible và hiểu giới hạn miền, hoặc dùng `@ColumnResult(name="...",type=Long.class)` với query alias tương ứng. Test provider/database.

### Bài 8 — Customer có 0 đơn không xuất hiện trong report

**Tình huống:** SQL dùng `INNER JOIN purchase_orders`.

**Đáp án:** dùng `LEFT JOIN`, `COUNT(o.id)` và `GROUP BY` để giữ customer và count 0. `FieldResult` không tự sửa lỗi mất hàng ở SQL.

### Bài 9 — Trả nhiều entity từ một SQL

**Yêu cầu:** SELECT customer và order, muốn cả hai entity ở mỗi hàng.

**Đáp án:** khai báo hai `@EntityResult` với alias phân biệt; đọc `Object[] {Customer, PurchaseOrder}`. Không suy ra collection `customer.orders` đã được fetch hoàn chỉnh.

### Bài 10 — Thống kê tổng tiền cần response DTO

**Yêu cầu:** HTTP API trả tên khách, số đơn, tiền PAID, không cần dirty checking.

**Đáp án:** ưu tiên `@ConstructorResult` với DTO constructor nhận `String, Long, BigDecimal`. Không cần tạo managed entity chỉ vì query join từ bảng customers.

---

## 35. Câu hỏi tự kiểm tra

**1. `@EntityResult` làm gì?**

Nó khai báo một phần của result set SQL đại diện cho entity class được JPA quản lý.

**2. `@FieldResult(name="fullName",column="display_name")` có hai tên thuộc hai tầng nào?**

`fullName` là Java persistent attribute; `display_name` là alias/label trong result set SQL.

**3. `@ColumnResult` có bắt buộc gắn với một entity property không?**

Không. Nó nhận scalar result từ một cột hoặc biểu thức SQL, chẳng hạn `COUNT` hoặc `SUM`.

**4. Muốn trả một entity và một count, dùng gì?**

Một `@SqlResultSetMapping` gồm `@EntityResult` và `@ColumnResult`; hàng kết quả thường là `Object[]`.

**5. Một mapping chỉ có một EntityResult trả kiểu gì?**

Thông thường mỗi hàng trả entity instance tương ứng, không phải một `Object[]` chỉ có một phần tử.

**6. Vì sao không nên SELECT một nửa thuộc tính khi muốn EntityResult?**

Entity cần đầy đủ state/identity cần thiết; mapping thiếu dữ liệu có thể không được đặc tả bảo đảm và gây lỗi hoặc state không nhất quán.

**7. Entity có `@Version` thì native entity SQL cần lưu ý gì?**

Cần trả và ánh xạ version column phù hợp để provider có entity state đúng cho optimistic locking.

**8. `@FieldResult` map khóa ghép `@EmbeddedId` như thế nào?**

Dùng dot notation cho thành phần ID, ví dụ `id.invoiceId` và `id.lineNumber`, trỏ đến alias riêng.

**9. Native SQL có thể trả nhiều entity trong một hàng không?**

Có, với nhiều `@EntityResult`. Mỗi hàng chứa các entity ở các vị trí trong `Object[]` theo mapping.

**10. SQL join Customer và Order có tự tạo `customer.orders` được khởi tạo đầy đủ không?**

Không nên giả định. Native result mapping và fetch plan/collection initialization là các vấn đề riêng.

**11. `@NamedNativeQuery.name` có phải `@SqlResultSetMapping.name` không?**

Không. Named query có tên riêng, và thuộc tính `resultSetMapping` chỉ đến mapping name.

**12. Có thể dùng `@SqlResultSetMapping` để đổi tên cột trong database không?**

Không. Nó chỉ mô tả cách đọc result set; schema mapping/DDL là tầng khác.

**13. Nếu một customer có ba order thì SQL JOIN có thể trả bao nhiêu hàng?**

Ba hàng tương ứng ba kết hợp, dù trong persistence context chỉ có một entity identity cho customer đó.

**14. Vì sao `COUNT(*)` trên LEFT JOIN có thể sai?**

Parent không có child vẫn có một hàng null-extended, nên `COUNT(*)` đếm một. Muốn đếm child dùng `COUNT(child.id)`.

**15. Khi native query trả `COUNT(*)`, có thể luôn cast trực tiếp `Long` không?**

Không nếu chưa xác nhận kiểu. Driver/provider có thể trả kiểu Number khác; `ColumnResult(type=...)` hoặc xử lý `Number` giúp xác định contract.

**16. Có thể đặt `@SqlResultSetMapping` trên một DTO thuần Java và mong provider tự quét không?**

Không nên. Mapping phải nằm trong metadata được persistence unit nhận diện, thường khai báo trên entity class.

**17. `EntityResult` có tự giải quyết stale data không?**

Không. Persistence context/identity map vẫn chi phối managed entity; dùng transaction mới, refresh và optimistic locking theo yêu cầu.

**18. Dùng `ConstructorResult` khi nào tốt hơn EntityResult?**

Khi chỉ cần read-only DTO/report, không cần entity managed, dirty checking hoặc identity.

**19. `@ColumnResult(type=BigDecimal.class)` có làm mọi database SUM trả đúng tiền không?**

Không tự động. Phải xét kiểu SQL, precision/scale và khả năng conversion, rồi kiểm thử.

**20. Native SQL dùng `:id` có portable như JPQL không?**

Không thể mặc định. Nhiều provider hỗ trợ native named parameters, nhưng positional binding là cách portable cơ bản được JPA bảo đảm cho native query.

**21. Một query kết hợp nhiều loại result sẽ đọc theo SQL column order hay mapping declaration?**

JPA xác định thứ tự các thành phần kết quả theo metadata của `SqlResultSetMapping`; alias map các cột, còn `Object[]` tuân thủ thứ tự khai báo nhóm kết quả/column results, không chỉ copy mọi SQL column theo vị trí thô.

**22. Vì sao một query có `@EntityResult` vẫn cần phân tích index/SQL plan?**

Annotation chỉ ánh xạ kết quả, không tự tối ưu SQL, giảm số hàng join hoặc giải quyết index thiếu.

---

## 36. Tổng kết

Ba annotation trọng tâm của native result mapping có ba nhiệm vụ khác nhau:

```text
@SqlResultSetMapping
  |
  +-- @EntityResult
  |      |
  |      +-- @FieldResult
  |              name   = Java persistent attribute
  |              column = SQL result alias
  |
  +-- @ColumnResult
  |      |
  |      +-- name = SQL result alias
  |      +-- type = Java scalar type mong muốn
  |
  +-- @ConstructorResult
         |
         +-- Dựng DTO theo constructor
```

**Mẫu entity-only:**

```java
@SqlResultSetMapping(
    name = "CustomerEntityAliased",
    entities = @EntityResult(
        entityClass = Customer.class,
        fields = {
            @FieldResult(name = "id", column = "c_id"),
            @FieldResult(name = "fullName", column = "c_name"),
            @FieldResult(name = "tier", column = "c_tier"),
            @FieldResult(name = "version", column = "c_version")
        }
    )
)
```

**Mẫu entity + scalar:**

```java
@SqlResultSetMapping(
    name = "CustomerWithCount",
    entities = @EntityResult(
        entityClass = Customer.class,
        fields = { /* đầy đủ các field cần thiết */ }
    ),
    columns = @ColumnResult(
        name = "order_count",
        type = Long.class
    )
)
```

**Mẫu scalar-only:**

```java
@SqlResultSetMapping(
    name = "CustomerTierCounts",
    columns = {
        @ColumnResult(name = "tier_label", type = String.class),
        @ColumnResult(name = "customer_count", type = Long.class)
    }
)
```

Khi lựa chọn, hãy tự hỏi:

1. **Cần entity managed hay chỉ một DTO/report?**
2. **SQL đã trả đủ cột để tạo entity hợp lệ chưa?**
3. **Alias SQL có khớp `FieldResult.column` và `ColumnResult.name` không?**
4. **Khóa chính, version, discriminator, FK và embedded ID có được xử lý đúng không?**
5. **Kiểu scalar có tương thích JDBC/provider không?**
6. **JOIN/COUNT/GROUP BY có đúng tập kết quả nghiệp vụ không?**
7. **Có test trên database thực tế cho mapping này không?**

**Ghi nhớ ngắn gọn:**

- `EntityResult` nói **“nhóm cột này là một entity”**.
- `FieldResult` nói **“alias này thuộc property nào của entity”**.
- `ColumnResult` nói **“alias này là một scalar result”**.
- `SqlResultSetMapping` nói **“toàn bộ hàng SQL được diễn giải theo cấu trúc nào”**.

Hiểu và tách đúng bốn ý trên giúp ứng dụng kết hợp sức mạnh của Native SQL với JPA mà không nhầm tên cột, kiểu dữ liệu, vòng đời entity hoặc phép tổng hợp SQL.

### Tài liệu tham khảo

- [Jakarta Persistence — các phiên bản đặc tả chính thức](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence 3.1 — phần Native SQL Queries và SqlResultSetMapping](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1.html)
- [Jakarta Persistence API — `SqlResultSetMapping`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/sqlresultsetmapping)
- [Jakarta Persistence API — `EntityResult`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/entityresult)
- [Jakarta Persistence API — `FieldResult`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/fieldresult)
- [Jakarta Persistence API — `ColumnResult`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/columnresult)
- [Jakarta Persistence API — `ConstructorResult`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/constructorresult)
- [Jakarta Persistence API — `NamedNativeQuery`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/namednativequery)
- [Jakarta Persistence API — `EntityManager`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/entitymanager)
