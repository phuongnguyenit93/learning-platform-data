# Phân loại lỗi truy vấn, ánh xạ, ràng buộc và giao dịch trong JPA

Trong ứng dụng dùng **Jakarta Persistence (JPA)**, một thao tác đơn giản như `repository.save(entity)` hoặc `entityManager.createQuery(...)` có thể thất bại vì nhiều nguyên nhân hoàn toàn khác nhau. Cùng một triệu chứng “không lưu được dữ liệu” có thể đến từ:

- **Truy vấn**: JPQL viết sai tên entity/field, thiếu parameter, result type không khớp, không có kết quả hoặc query timeout.
- **Ánh xạ**: `@Id` sai, `mappedBy` trỏ nhầm property, entity không thuộc persistence unit, tên cột khác schema, enum/converter không phù hợp.
- **Ràng buộc dữ liệu**: database từ chối `UNIQUE`, `NOT NULL`, `FOREIGN KEY`, `CHECK`, hoặc Bean Validation từ chối giá trị đầu vào.
- **Giao dịch và đồng thời**: thiếu transaction, transaction rollback-only, optimistic version conflict, lock timeout, deadlock, serialization failure hoặc lỗi lúc commit.
- **Hạ tầng**: mất kết nối, database không sẵn sàng, sai credential, hết connection pool, schema chưa được migrate.

Nếu phân loại sai, cách “phục hồi” có thể khiến vấn đề nghiêm trọng hơn. Retry một `UNIQUE` violation không sửa được duplicate key; bắt và nuốt lỗi trong transaction đã rollback-only có thể dẫn đến `UnexpectedRollbackException`; còn retry toàn bộ nghiệp vụ thanh toán mà không có idempotency có thể tạo tác dụng phụ hai lần.

Bài thuộc chủ đề **Data Persistence Relational Access ORM JPA**, chương **Lỗi và phục hồi**, với đề mục trực tiếp **“Phân loại lỗi truy vấn, ánh xạ, ràng buộc và giao dịch”**.

Mục tiêu sau bài:

1. Nhận diện tầng phát sinh lỗi từ triệu chứng và exception chain.
2. Phân biệt lỗi lập trình/schema với lỗi dữ liệu nghiệp vụ hoặc lỗi tạm thời.
3. Xác định khi nào sửa code/migration, khi nào báo lỗi cho client, khi nào rollback và khi nào có thể retry.
4. Hiểu vì sao exception có thể xuất hiện tại `persist`, `flush`, query hoặc `commit`.
5. Đọc đúng các nhóm exception của JPA, Bean Validation, Hibernate, JDBC và Spring.
6. Thiết kế logging, HTTP error mapping, transaction boundaries và integration tests có khả năng kiểm chứng.

**Nguyên tắc cốt lõi:** *Đọc **nguyên nhân và ranh giới transaction**, không chỉ đọc tên exception ngoài cùng. Không retry một lỗi trước khi xác định nó có thực sự tạm thời và thao tác retry có an toàn hay không.*

---

## 1. Bản đồ các lớp phát sinh lỗi

Một request có thể đi qua:

```text
HTTP Controller / Message Consumer
             |
             v
Application Service
             |
             v
Spring Data Repository / EntityManager
             |
             v
JPA Provider (Hibernate, EclipseLink, ...)
             |
             v
JDBC Driver / Connection Pool
             |
             v
Database Engine
```

Exception có thể được **bọc nhiều lần** khi đi từ dưới lên:

```text
Database SQLSTATE 23505
       |
       v
java.sql.SQLException
       |
       v
org.hibernate.exception.ConstraintViolationException
       |
       v
jakarta.persistence.PersistenceException
       |
       v
org.springframework.dao.DataIntegrityViolationException
       |
       v
HTTP exception handler
```

Chuỗi trên chỉ là **một khả năng**, không phải cấu trúc bất biến. Với một driver/provider khác, wrapper và nơi exception phát sinh có thể khác.

### 1.1. Đừng chỉ nhìn message ngoài cùng

Ví dụ:

```text
TransactionSystemException: Could not commit JPA transaction
Caused by: RollbackException
Caused by: PersistenceException
Caused by: ConstraintViolationException
Caused by: SQLException: duplicate key
```

Thông điệp ngoài cùng nói **commit thất bại**. Nguyên nhân gốc lại là **UNIQUE violation**. Một hệ thống chỉ phân loại theo `TransactionSystemException` sẽ bỏ lỡ conflict nghiệp vụ.

Tương tự, hai `PersistenceException` khác nhau có thể yêu cầu hai hành động đối lập:

- JPQL sai cú pháp → sửa code, không retry.
- Database mất kết nối tạm thời → có thể retry giao dịch mới nếu thao tác idempotent và chính sách cho phép.

### 1.2. Không đồng nhất “loại exception” với “lệnh xử lý”

Một `SQLTransientException` hoặc lỗi class `40` có thể là tín hiệu tạm thời; vẫn phải kiểm tra **giao dịch có thể retry an toàn không**. Một ngoại lệ `DataIntegrityViolationException` lại có thể là `UNIQUE`, `FK` hoặc `CHECK` và cần lỗi nghiệp vụ khác nhau.

---

## 2. Ma trận phân loại tổng quan

| Nhóm lỗi | Ví dụ | Thời điểm thường gặp | Khả năng retry nguyên lệnh | Hướng xử lý chính |
| --- | --- | --- | --- | --- |
| JPQL sai tên entity/property | `UnknownEntity`, `SemanticException` | Tạo/biên dịch query, thực thi | **Không** | Sửa JPQL/mapping |
| Thiếu/sai parameter | `IllegalArgumentException`, provider query exception | `setParameter`, thực thi | Không | Sửa binding và type |
| Không có một kết quả | `NoResultException` | `getSingleResult()` | Không mặc định | Xử lý not-found hợp đồng |
| Có nhiều kết quả | `NonUniqueResultException` | `getSingleResult()` | Không mặc định | Sửa cardinality/query/invariant |
| Query timeout | `QueryTimeoutException` | Query execution | Có điều kiện | Tối ưu query/giới hạn retry |
| Entity mapping sai | Mapping/bootstrap exception | Khởi động EntityManagerFactory | Không | Sửa annotation/schema |
| Bảng/cột không có | SQLSTATE `42P01`, `42703` (PostgreSQL) | SQL execution | Không đến khi sửa schema | Migration/schema config |
| Bean Validation | `jakarta.validation.ConstraintViolationException` | Validation/persist/flush | Không với dữ liệu cũ | Sửa input/domain state |
| UNIQUE violation | SQLSTATE `23505` (PostgreSQL) | INSERT/UPDATE/flush/commit | Không với cùng key | Business conflict/409 |
| FK violation | SQLSTATE `23503` (PostgreSQL) | INSERT/DELETE/flush/commit | Không mặc định | Kiểm tra reference/order |
| NOT NULL violation | SQLSTATE `23502` (PostgreSQL) | INSERT/UPDATE | Không | Sửa input/mapping |
| CHECK violation | SQLSTATE `23514` (PostgreSQL) | INSERT/UPDATE | Không với giá trị cũ | Sửa nghiệp vụ/validation |
| Optimistic lock conflict | `OptimisticLockException` | Flush/commit | **Có điều kiện** | Rollback, reload, reconcile |
| Pessimistic lock failure | `PessimisticLockException` | Lock/query | Có điều kiện | Rollback, retry bounded |
| Lock timeout | `LockTimeoutException` | Lock/query | Có điều kiện | Retry chính sách, giảm contention |
| Deadlock/serialization | SQLSTATE `40P01`/`40001` (PostgreSQL) | DML/commit | Thường có điều kiện | Retry **toàn transaction mới** |
| Thiếu transaction | `TransactionRequiredException` | Flush/ghi/lock | Không | Sửa transaction boundary |
| Transaction rollback-only | `RollbackException`, `UnexpectedRollbackException` | Commit | Không retry mù | Truy ngược lỗi đầu tiên |
| Mất kết nối | SQLSTATE class `08` | Query/commit | Rất thận trọng | Health, idempotency, retry policy |

**Các SQLSTATE trong bảng có ví dụ theo PostgreSQL**, không phải mã lỗi áp dụng y hệt cho mọi database engine.

---

## 3. Mô hình ví dụ xuyên suốt

Các ví dụ dùng Java 17+, `jakarta.persistence`, Spring Data JPA/Spring Transaction khi có chú thích tương ứng.

### 3.1. Trạng thái đơn hàng

```java
package com.example.orders.domain;

public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
```

### 3.2. Entity Customer

```java
package com.example.orders.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import jakarta.persistence.Version;

@Entity
@Table(
    name = "customers",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customers_tenant_email",
        columnNames = {"tenant_id", "normalized_email"}
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "normalized_email", nullable = false)
    private String normalizedEmail;

    @Column(nullable = false)
    private String displayName;

    @Version
    private Long version;

    protected Customer() {
    }

    public Customer(
            Long tenantId,
            String normalizedEmail,
            String displayName) {
        this.tenantId = tenantId;
        this.normalizedEmail = normalizedEmail;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getNormalizedEmail() {
        return normalizedEmail;
    }
}
```

### 3.3. Entity PurchaseOrder

```java
package com.example.orders.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import jakarta.persistence.Version;

@Entity
@Table(
    name = "purchase_orders",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_orders_tenant_code",
        columnNames = {"tenant_id", "order_code"}
    )
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "order_code", nullable = false)
    private String orderCode;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Version
    private Long version;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            Long tenantId,
            String orderCode,
            Customer customer) {
        this.tenantId = tenantId;
        this.orderCode = orderCode;
        this.customer = customer;
        this.status = OrderStatus.DRAFT;
    }

    public Long getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Long getVersion() {
        return version;
    }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only draft orders can be confirmed"
            );
        }
        status = OrderStatus.CONFIRMED;
    }
}
```

Trong production multi-tenant, `tenantId` phải được kiểm soát theo security context và associations có thể cần bảo đảm cùng tenant. Ví dụ tập trung vào exception classification, **không thay thế hệ thống authorization/tenant isolation hoàn chỉnh**.

### 3.4. Database schema minh họa

PostgreSQL:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    normalized_email VARCHAR(255) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT uk_customers_tenant_email
        UNIQUE (tenant_id, normalized_email)
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    order_code VARCHAR(255) NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT uk_orders_tenant_code
        UNIQUE (tenant_id, order_code),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id),
    CONSTRAINT ck_orders_status
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED'))
);
```

Schema thực tế nên được quản lý qua migration và phù hợp mapping/provider/dialect. Việc thêm annotation vào Java class không tự chứng minh constraint đã tồn tại trong database đang chạy.

---

# Phần I — Lỗi truy vấn

## 4. Lỗi cú pháp và ngữ nghĩa JPQL

JPQL dùng **entity names và Java mapped attributes**, không mặc định dùng tên bảng/cột SQL.

Giả sử entity là `PurchaseOrder`:

**Sai:**

```java
em.createQuery(
    """
    SELECT o
    FROM purchase_orders o
    WHERE o.order_code = :code
    """,
    PurchaseOrder.class
);
```

Đây là tên table/column ở SQL, không phải tên entity/property JPQL.

**Đúng:**

```java
em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.orderCode = :code
    """,
    PurchaseOrder.class
)
.setParameter("code", "PO-100")
.getResultList();
```

### 4.1. Những lỗi JPQL thường gặp

| Lỗi | Ví dụ | Nguyên nhân |
| --- | --- | --- |
| Sai tên entity | `FROM purchase_orders` | JPQL tìm entity name |
| Sai property | `o.order_code` | Attribute mapped là `orderCode` |
| Sai path | `o.customer_email` | Cần navigation qua relationship |
| Sai alias | `WHERE x.id=...` khi chỉ có alias `o` | Alias không tồn tại |
| Sai hàm/biểu thức | SQL dialect function dùng trực tiếp không hỗ trợ | JPQL không đồng nhất native SQL |
| Sai constructor expression | DTO không có constructor tương ứng | Projection mapping sai |
| Sai aggregate result | Trả `Long` nhưng khai báo `Integer` | Type mismatch |

Câu query có thể bị phân tích ngay khi gọi `createQuery`, hoặc chỉ thất bại khi thực thi tùy provider và loại truy vấn.

### 4.2. Một query JPQL đúng cú pháp vẫn có thể sai schema runtime

JPQL:

```java
SELECT o FROM PurchaseOrder o
```

có thể parse thành công, nhưng khi SQL được gửi tới database, lỗi có thể là:

```text
relation "purchase_orders" does not exist
column "customer_id" does not exist
permission denied for table ...
```

Đó là **schema/configuration/permission error**, không phải lỗi cú pháp JPQL.

### 4.3. Chọn JPQL hay native SQL đúng mục đích

JPQL:

```java
em.createQuery(
    "SELECT o FROM PurchaseOrder o WHERE o.orderCode = :code",
    PurchaseOrder.class
);
```

Native SQL:

```java
em.createNativeQuery(
    "SELECT * FROM purchase_orders WHERE order_code = :code",
    PurchaseOrder.class
);
```

Cần phân biệt mapping/result type và parameter conventions; tên bảng/cột SQL không phải tên entity attribute JPQL.

---

## 5. Sai parameter name, type và binding

Ví dụ JPQL có named parameter `:code`:

```java
TypedQuery<PurchaseOrder> query = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.orderCode = :code
    """,
    PurchaseOrder.class
);
```

**Sai tên:**

```java
query.setParameter("orderCode", "PO-100");
```

Parameter được khai báo là `code`, không phải `orderCode`. JPA/provider có thể ném `IllegalArgumentException` khi bind.

**Đúng:**

```java
query.setParameter("code", "PO-100");
```

### 5.1. Thiếu parameter có thể lỗi khi thực thi

```java
query.getResultList(); // Chưa bind :code.
```

Provider có thể báo named parameter chưa được gán. Không catch rồi mặc định xem nó như “không tìm thấy dữ liệu”.

### 5.2. Type mismatch

Nếu entity có `OrderStatus status`:

```java
SELECT o FROM PurchaseOrder o WHERE o.status = :status
```

thì nên bind enum:

```java
query.setParameter("status", OrderStatus.CONFIRMED);
```

Không tự chuyển enum thành string theo dạng SQL column trong JPQL khi provider mong Java enum type.

### 5.3. Không ghép chuỗi input thành JPQL

Sai:

```java
String jpql =
    "SELECT o FROM PurchaseOrder o WHERE o.orderCode = '"
    + input + "'";
```

Rủi ro injection, sai escape và query-plan fragmentation. Dùng parameter binding để tách input khỏi query structure.

### 5.4. Query parameter error thường không cần retry

Parameter name sai hay type sai là **bug của application**. Retry nguyên request với cùng code/input thường lặp lại lỗi. Cần sửa query/binding và bổ sung test.

---

## 6. NoResultException và NonUniqueResultException

Với JPA `getSingleResult()`:

```java
PurchaseOrder order = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.orderCode = :code
    """,
    PurchaseOrder.class
)
.setParameter("code", "UNKNOWN")
.getSingleResult();
```

Nếu không có row, API có thể ném:

```java
jakarta.persistence.NoResultException
```

Nếu trả nhiều hơn một kết quả mà `getSingleResult()` yêu cầu duy nhất, API có thể ném:

```java
jakarta.persistence.NonUniqueResultException
```

Đây là **lỗi cardinality theo hợp đồng truy vấn**, không nhất thiết là lỗi hạ tầng.

### 6.1. Không có kết quả không luôn là 500

Đối với GET `/orders/{id}`, không có entity thường map thành HTTP `404 Not Found`. Đối với truy vấn thống kê, không có row có thể là `Optional.empty()` hoặc list rỗng.

### 6.2. `getResultList()` thường đơn giản hơn khi chấp nhận zero rows

```java
List<PurchaseOrder> rows = em.createQuery(
    "SELECT o FROM PurchaseOrder o WHERE o.orderCode = :code",
    PurchaseOrder.class
)
.setParameter("code", code)
.setMaxResults(2)
.getResultList();

if (rows.isEmpty()) {
    // Not found.
}

if (rows.size() > 1) {
    // Violated expected uniqueness.
}
```

Nếu `orderCode` chỉ unique **trong một tenant**, query phải có `tenantId`. Thiếu tenant predicate có thể dẫn đến `NonUniqueResultException`, hoặc tệ hơn là trả dữ liệu sai tenant.

### 6.3. `getSingleResultOrNull()` có version dependency

Một số phiên bản Jakarta Persistence có `getSingleResultOrNull()` để biểu diễn “không có kết quả” mà không ném `NoResultException`. Không giả định API này tồn tại trên mọi version đang dùng.

### 6.4. Transaction impact

Theo semantics JPA, `NoResultException` và `NonUniqueResultException` thông thường **không khiến active transaction bị đánh dấu rollback chỉ bởi chính exception đó**. Tuy nhiên, Spring `@Transactional` có thể đánh dấu rollback nếu một unchecked exception thoát khỏi transactional method theo rollback rules mặc định.

Đây là hai lớp quy tắc khác nhau: **JPA exception contract** và **Spring transaction interceptor policy**.

---

## 7. QueryTimeoutException và lỗi quá chậm

Một query có thể thất bại vì timeout:

```java
jakarta.persistence.QueryTimeoutException
```

Có thể cấu hình hint theo Jakarta Persistence version/provider, ví dụ:

```java
query.setHint("jakarta.persistence.query.timeout", 2_000);
```

Giá trị minh họa thường được hiểu theo milliseconds trong hỗ trợ provider tương ứng; cần kiểm tra phiên bản và khả năng hỗ trợ thực tế.

### 7.1. Tìm nguyên nhân trước khi retry

- Thiếu index hoặc query plan xấu.
- Truy vấn quét bảng quá lớn.
- Lock contention hoặc database quá tải.
- Fetch graph rộng/N+1.
- Timeout quá thấp so với SLA.
- Connection pool hoặc network delay.

### 7.2. QueryTimeoutException khác transaction-level failure

Trong JPA, `QueryTimeoutException` được dùng khi **chỉ statement bị rollback**, không phải toàn transaction; nếu timeout buộc toàn transaction rollback, provider có thể dùng `PersistenceException` theo contract tương ứng.

Không suy luận transaction vẫn chắc chắn lành mạnh chỉ từ tên exception trong mọi stack. Sau timeout, kiểm tra transaction rollback-only/DB state và framework policy trước khi tiếp tục.

### 7.3. Retry không thay query optimization

Nếu một query 30 giây luôn timeout ở 2 giây do thiếu index, retry 5 lần chỉ gây thêm tải. Cần tối ưu SQL, index, pagination, fetch plan và giới hạn kết quả.

---

# Phần II — Lỗi ánh xạ

## 8. Mapping error thường lộ ngay khi khởi động

Lỗi mapping có thể khiến JPA provider **không tạo được EntityManagerFactory**. Ví dụ:

- Thiếu `@Id` hoặc metadata identifier không hợp lệ.
- `mappedBy` trỏ tới property không tồn tại.
- Hai attributes ánh xạ trùng cột theo cách không được phép.
- Quan hệ `@OneToMany`, `@ManyToOne`, `@OneToOne` thiếu metadata cần thiết.
- `@EmbeddedId`, `@MapsId` hoặc composite key sai.
- Inheritance/collection mapping không nhất quán.
- Entity class không được scan/đăng ký trong persistence unit.
- `AttributeConverter` hoặc enum mapping không hợp lệ.

### 8.1. Ví dụ `mappedBy` sai

```java
@Entity
public class Customer {

    @OneToMany(mappedBy = "customerWrong")
    private List<PurchaseOrder> orders;
}
```

Trong `PurchaseOrder` property thực tế là:

```java
@ManyToOne
private Customer customer;
```

`mappedBy = "customerWrong"` không trỏ tới property hợp lệ. Cần sửa thành:

```java
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders;
```

Đây là **mapping bug**, không phải lỗi trùng dữ liệu hoặc lỗi transaction để retry.

### 8.2. Entity không được quản lý

Ví dụ:

```java
em.persist(new SomeUnmappedClass());
```

Nếu class không phải entity được quản lý, provider có thể ném `IllegalArgumentException` hoặc provider-specific exception.

Không nhầm “table có tồn tại trong DB” với “class được map là entity trong persistence unit”.

### 8.3. Mapping lỗi ở bootstrap khác lỗi DB runtime

Nếu khởi tạo EntityManagerFactory thất bại do `mappedBy`, cần sửa Java metadata. Nếu bootstrap thành công nhưng SQL báo thiếu cột, cần xem schema/migration/datasource.

Hai loại lỗi có thể được log cùng dưới từ khóa “mapping”, nhưng đường phục hồi khác nhau.

---

## 9. Schema mismatch: ánh xạ đúng Java, database sai trạng thái

Ví dụ entity ánh xạ:

```java
@Column(name = "order_code", nullable = false)
private String orderCode;
```

nhưng DB cũ vẫn có cột `code`.

Khi truy vấn, SQL có thể bị từ chối vì `order_code` không tồn tại.

Các nguyên nhân thường gặp:

- Chưa chạy migration.
- Chạy sai schema/database.
- Datasource trỏ nhầm môi trường.
- Entity naming strategy khác môi trường.
- Quoted identifiers làm phân biệt chữ hoa/thường.
- DB schema/search_path sai.
- DB permission không đủ.
- Migrations và application version triển khai lệch nhau.

### 9.1. PostgreSQL SQLSTATE ví dụ

| SQLSTATE | Ý nghĩa | Hướng điều tra |
| --- | --- | --- |
| `42P01` | undefined_table | Migration, schema/search_path, tên bảng |
| `42703` | undefined_column | Mapping column và migration |
| `42601` | syntax_error | Native SQL, dialect, generated SQL |
| `42501` | insufficient_privilege | DB role/GRANT, không mặc định migration |
| `42804` | datatype_mismatch | Column type, expression/cast |
| `22P02` | invalid_text_representation | Input DB conversion/enum/type |

Đây là ví dụ PostgreSQL. DB khác có thể có mã SQLSTATE hoặc vendor error code khác.

### 9.2. `ddl-auto=update` không thay migration production

Một hệ thống production nên dùng quy trình migrations có kiểm soát. Chạy một cơ chế ORM tự sửa schema trong mọi môi trường có thể gây divergence, đổi constraint không như mong muốn hoặc che lỗi rollout.

**Mapping mới không tự bảo đảm schema thực tế mới.**

### 9.3. Đừng sửa lỗi schema bằng retry request

Nếu bảng chưa tồn tại, cùng query sẽ tiếp tục thất bại cho đến khi migration/schema được sửa. Retry nhiều lần không giúp và có thể làm tăng tải.

### 9.4. EntityGraph/fetch mapping sai

Một query có thể tham chiếu attribute path không đúng trong entity graph:

```java
em.createEntityGraph(PurchaseOrder.class)
    .addAttributeNodes("customerName");
```

Nếu `customerName` không phải mapped attribute của `PurchaseOrder`, provider có thể báo lỗi khi tạo graph hoặc dùng graph. Đây là mapping/query-configuration bug, không phải lỗi dữ liệu bản ghi.

---

## 10. Enum, converter và serialization errors

Mapping enum bằng:

```java
@Enumerated(EnumType.STRING)
private OrderStatus status;
```

đòi hỏi DB có giá trị phù hợp enum name. Nếu row chứa `"PAID"` nhưng Java enum chỉ có `DRAFT`, `CONFIRMED`, `CANCELLED`, provider có thể thất bại khi materialize.

### 10.1. EnumType.ORDINAL có rủi ro khác

Nếu dùng `EnumType.ORDINAL`, đổi thứ tự enum constants có thể biến dữ liệu cũ thành trạng thái sai mà không ném exception.

Vì vậy không phải lỗi nào của mapping cũng có exception rõ ràng; có những **data correctness bugs** âm thầm.

### 10.2. AttributeConverter có thể ném lỗi khi đọc/ghi

```java
@Converter(autoApply = false)
public class MoneyCodeConverter
        implements AttributeConverter<MoneyCode, String> {
    // ...
}
```

Nếu converter không xử lý một giá trị DB legacy, JPA có thể bọc lỗi dưới `PersistenceException` hoặc provider exception.

Cần:

- Kiểm tra data range.
- Schema migration/backfill.
- Version compatibility.
- Logging root cause/field liên quan mà không lộ dữ liệu nhạy cảm.

### 10.3. Không retry converter bug

Với cùng row hỏng, một lần query lại thường sẽ ném cùng lỗi. Đây là lỗi dữ liệu/mapping cần sửa, không phải transient DB failure.

---

# Phần III — Lỗi ràng buộc dữ liệu

## 11. UNIQUE, FK, NOT NULL và CHECK khác nhau

Một bảng có thể chứa:

```sql
CONSTRAINT uk_orders_tenant_code
    UNIQUE (tenant_id, order_code),

CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id)
    REFERENCES customers(id),

CONSTRAINT ck_orders_status
    CHECK (status IN ('DRAFT','CONFIRMED','CANCELLED'))
```

Nếu ứng dụng bắt mọi lỗi `DataIntegrityViolationException` và trả `"ORDER_CODE_ALREADY_EXISTS"`, nó sẽ báo sai khi `customer_id` không tồn tại hoặc trạng thái không hợp lệ.

### 11.1. PostgreSQL SQLSTATE class 23

| SQLSTATE | Loại lỗi | Ví dụ |
| --- | --- | --- |
| `23505` | unique_violation | Trùng `(tenant_id, order_code)` |
| `23503` | foreign_key_violation | `customer_id` không tồn tại |
| `23502` | not_null_violation | Không gán trường bắt buộc |
| `23514` | check_violation | Trạng thái không thuộc tập cho phép |

Những mã này dành cho PostgreSQL. Để biết **constraint nào** bị vi phạm, đọc metadata/tên constraint khi driver/provider cung cấp.

### 11.2. UNIQUE violation

```sql
INSERT INTO purchase_orders (
    tenant_id, order_code, customer_id, status, version
)
VALUES (1, 'PO-100', 10, 'DRAFT', 0);
```

Nếu `(1, 'PO-100')` đã có, DB phải bảo vệ unique key.

Một `SELECT EXISTS` trước INSERT không loại được race giữa hai transactions. Không retry cùng value vô hạn; trả business conflict hoặc tạo key mới nếu chính sách nghiệp vụ cho phép.

### 11.3. Foreign key violation

Nếu `customer_id = 9999` không tồn tại, database từ chối INSERT. Điều tra:

- ID từ client có hợp lệ và thuộc tenant không?
- Entity parent đã persist chưa?
- Cấu hình cascade có đúng không?
- Flush ordering có bị tác động bởi bulk/native writes?
- Có transaction khác đang delete parent?
- Có migration thiếu relationship?

Không đổi FK error thành “order code trùng”.

### 11.4. NOT NULL violation

Nếu `order_code` bị null mà DB cột `NOT NULL`, nguyên nhân có thể là DTO mapping thiếu giá trị, domain validation chưa đủ hoặc đường native SQL bỏ qua Java check.

Cần sửa input/mapping và bảo vệ bằng DB constraint thật.

### 11.5. CHECK violation

Ví dụ DB chỉ cho `status` thuộc tập ba trạng thái, nhưng native SQL ghi `"UNKNOWN"`. Kiểm tra business rule, schema `CHECK`, enum mapping và các writers ngoài JPA.

Một `CHECK` violation không nên được retry với chính giá trị không hợp lệ.

---

## 12. Bean Validation khác database constraint exception

Bean Validation có:

```java
jakarta.validation.ConstraintViolationException
```

Thường liên quan:

```java
@NotNull
@NotBlank
@Size(max = 100)
@Email
```

Database/ORM constraint error có thể là:

```java
org.hibernate.exception.ConstraintViolationException
```

Cùng tên ngắn `ConstraintViolationException` nhưng **khác package và khác ý nghĩa**.

### 12.1. Ví dụ lỗi Bean Validation

```java
@NotBlank
@Column(name = "order_code", nullable = false)
private String orderCode;
```

Nếu Bean Validation được tích hợp và phát hiện giá trị blank, nó có thể ném trước SQL INSERT.

Nhưng `@NotBlank` không thay `NOT NULL`, `UNIQUE` hoặc CHECK constraint đã triển khai trong database.

### 12.2. Custom validator kiểm tra uniqueness vẫn có race

Một validator gọi repository để kiểm tra tồn tại chỉ là **pre-check**, không bảo đảm tính duy nhất khi nhiều transactions cùng INSERT. Constraint thực tế ở database vẫn phải tồn tại.

### 12.3. Bean Validation thường xử lý như invalid input

Lỗi input có thể map HTTP 400/422 tùy API contract, với field errors an toàn. Nhưng validation failure trong quá trình flush một entity được tạo từ dữ liệu nội bộ cũng có thể là **bug của service**. Không mặc định lỗi đó đều do client.

---

## 13. Exception wrapping và phân loại constraint name

Một trường hợp PostgreSQL/Hibernate có thể có chain:

```text
DataIntegrityViolationException
  -> ConstraintViolationException (Hibernate ORM)
      -> PSQLException (SQLSTATE=23505)
```

Trong Hibernate:

```java
org.hibernate.exception.ConstraintViolationException
    .getConstraintName()
```

có thể trả `uk_orders_tenant_code`.

Classifier minh họa:

```java
public final class DbIntegrityClassifier {

    private static final String ORDER_CODE_UNIQUE =
        "uk_orders_tenant_code";

    private DbIntegrityClassifier() {
    }

    public static boolean isDuplicateOrderCode(
            Throwable error) {

        for (Throwable current = error;
                current != null;
                current = current.getCause()) {

            if (current instanceof
                    org.hibernate.exception.ConstraintViolationException
                    hibernateEx) {

                String name = hibernateEx.getConstraintName();

                if (name != null &&
                        ORDER_CODE_UNIQUE.equalsIgnoreCase(name)) {
                    return true;
                }
            }
        }

        return false;
    }
}
```

**Giới hạn:** tên constraint có thể null, có schema prefix hoặc quoting khác nhau tùy driver/dialect. Cần integration test đúng DB target. SQLSTATE `23505` chỉ cho biết *loại unique violation*, không nói đó là email, order code hay username.

### 13.1. Không parse raw message text

Tránh:

```java
if (ex.getMessage().contains("duplicate key")) {
    // ...
}
```

Thông điệp có thể thay theo phiên bản, locale, DB và có thể chứa dữ liệu nhạy cảm. Ưu tiên SQLSTATE/vendor code/constraint name có cấu trúc.

### 13.2. Nếu không phân loại được, đừng đoán

Một lỗi integrity chưa rõ không nên biến thành `"ORDER_CODE_ALREADY_EXISTS"`. Dùng một fallback an toàn và log metadata phục vụ điều tra.

---

# Phần IV — Lỗi giao dịch và đồng thời

## 14. TransactionRequiredException: thiếu transaction phù hợp

Một số thao tác JPA cần active transaction/context joined:

```java
jakarta.persistence.TransactionRequiredException
```

Ví dụ với application-managed resource-local EntityManager:

```java
EntityManager em = emf.createEntityManager();

try {
    PurchaseOrder order =
        em.find(PurchaseOrder.class, id);

    order.confirm();

    em.flush(); // Có thể ném TransactionRequiredException.
} finally {
    em.close();
}
```

Nếu chưa gọi `em.getTransaction().begin()`, flush một thay đổi yêu cầu transaction là không hợp lệ.

### 14.1. Cách sửa đúng

```java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    PurchaseOrder order =
        em.find(PurchaseOrder.class, id);

    order.confirm();

    em.getTransaction().commit();

} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Đây là ví dụ RESOURCE_LOCAL. Trong Jakarta EE JTA/Spring, dùng transaction manager của container/framework, không gọi `em.getTransaction()` trên container-managed EM.

### 14.2. Spring @Transactional không phải phép màu

Nếu method `@Transactional` được gọi bằng self-invocation:

```java
this.confirm(id);
```

trong một Spring bean dùng proxy-based AOP, transaction advice có thể không chạy như dự kiến. Cần đi qua proxy hoặc dùng `TransactionTemplate`.

Không giải quyết `TransactionRequiredException` bằng cách catch và bỏ qua flush.

---

## 15. OptimisticLockException: dữ liệu bị thay đổi cạnh tranh

Entity có:

```java
@Version
private Long version;
```

Kịch bản:

```text
T1 read Order#101 version=4
T2 read Order#101 version=4

T1 confirm -> UPDATE ... WHERE id=101 AND version=4
T1 COMMIT -> version=5

T2 confirm -> UPDATE ... WHERE id=101 AND version=4
             affected rows=0
             OptimisticLockException
             ROLLBACK
```

JPA:

```java
jakarta.persistence.OptimisticLockException
```

có thể xuất hiện tại `flush()` hoặc `commit()`, không nhất thiết tại dòng `order.confirm()`.

### 15.1. Phân loại: conflict, không phải bug cú pháp

Lỗi này thường có nghĩa entity state mà thao tác dựa vào đã cũ. Cách xử lý phụ thuộc nghiệp vụ:

- Hiển thị conflict, yêu cầu user xem state mới.
- Tải lại entity trong transaction mới và áp lại **ý định nghiệp vụ**.
- Retry tự động có giới hạn nếu operation có thể thực hiện an toàn trên state mới.
- Nếu state mới khiến operation không còn hợp lệ, trả conflict nghiệp vụ.

### 15.2. Không retry trên cùng EntityManager đã thất bại

Sau optimistic conflict, transaction thường bị rollback-only. Không làm:

```java
catch (OptimisticLockException ex) {
    em.refresh(order);
    em.flush(); // Sai hướng nếu transaction đã lỗi.
}
```

Đúng hướng: rollback, bỏ failed persistence context, mở transaction/context mới, reload và quyết định lại.

### 15.3. Không tự cộng version

`@Version` do provider quản lý. Không tự sửa field version để ép update thắng; sẽ đánh mất cơ chế phát hiện concurrent change.

---

## 16. PessimisticLockException và LockTimeoutException

JPA hỗ trợ pessimistic locking:

```java
PurchaseOrder order = em.find(
    PurchaseOrder.class,
    id,
    LockModeType.PESSIMISTIC_WRITE
);
```

Hai exception quan trọng:

```java
jakarta.persistence.PessimisticLockException
jakarta.persistence.LockTimeoutException
```

### 16.1. Ý nghĩa trong JPA contract

- `PessimisticLockException` thường dùng khi lock failure làm transaction rollback theo semantics JPA.
- `LockTimeoutException` dùng cho trường hợp **statement-level rollback** mà toàn transaction không bị đánh dấu rollback chỉ vì lock attempt đó.

Tuy nhiên driver/database/framework có thể bọc exception khác nhau và Spring có thể áp rollback rules riêng. **Không tiếp tục giao dịch một cách mù quáng sau bất kỳ DB lock error nào.**

### 16.2. Lock timeout khác query timeout

| Lỗi | Tín hiệu | Điều tra |
| --- | --- | --- |
| Lock timeout | Không lấy được lock trong thời hạn | Transactions giữ lock, lock order |
| Query timeout | Query execution vượt deadline | Query plan, index, load, locking |
| Deadlock | DB phát hiện cycle chờ lock | Thứ tự khóa, transaction size |
| Optimistic conflict | Version không còn khớp | Concurrent updates, retry logic |

### 16.3. Giảm lock contention

- Giữ transaction ngắn.
- Khóa resources theo thứ tự nhất quán.
- Có index cho các predicate cập nhật.
- Tránh network call chậm trong DB transaction.
- Giảm số rows bị khóa.
- Dùng lock timeout có ý nghĩa nghiệp vụ và retry bounded nếu phù hợp.

---

## 17. Deadlock và serialization failure

Trong PostgreSQL:

```text
SQLSTATE 40P01 = deadlock_detected
SQLSTATE 40001 = serialization_failure
```

Một database có thể chủ động hủy một transaction để giải quyết deadlock hoặc duy trì isolation.

### 17.1. Có thể retry, nhưng phải retry **toàn giao dịch**

Sai:

```text
BEGIN
  SELECT inventory
  UPDATE first row
  UPDATE second row -> deadlock
  catch exception
  retry only second UPDATE in same transaction
```

Giao dịch có thể đã bị abort; retry một statement trong failed transaction là sai.

Đúng hướng:

```text
Attempt 1:
  BEGIN -> read -> business decision -> write -> deadlock
  ROLLBACK + close context

Backoff có giới hạn

Attempt 2:
  BEGIN mới -> read state mới -> business decision mới -> write
  COMMIT
```

### 17.2. Retry phải dựa trên operation idempotency

Nếu transaction còn gọi email/payment gateway ở giữa, retry toàn bộ có thể thực hiện side effect hai lần.

Đưa external side effects ra ngoài transaction theo policy hoặc dùng **transactional outbox**, idempotency key và consumer deduplication.

### 17.3. Có điều kiện, không phải retry vô hạn

Một policy có thể giới hạn:

- Số lần thử tối đa.
- Tổng thời gian từ deadline request.
- Backoff tăng dần và jitter.
- Các SQLSTATE/class được phép retry.
- Ngừng retry khi conflict là business decision chứ không tạm thời.
- Logging correlation ID và attempt count.

Không áp cùng policy retry cho query typo, missing column, UNIQUE hay invalid input.

---

## 18. RollbackException và transaction rollback-only

JPA có:

```java
jakarta.persistence.RollbackException
```

Spring có thể báo:

```java
org.springframework.transaction.UnexpectedRollbackException
org.springframework.transaction.TransactionSystemException
```

Một tình huống phổ biến:

```text
Outer @Transactional service begins
       |
       v
Inner operation fails
       |
       v
Transaction marked rollback-only
       |
       v
Outer code catches exception and continues
       |
       v
Outer method returns normally
       |
       v
Transaction interceptor tries commit
       |
       v
UnexpectedRollbackException
```

### 18.1. Tên exception sau cùng có thể che lỗi đầu tiên

Khi nhìn thấy `UnexpectedRollbackException`, cần tìm **điểm đầu tiên** transaction bị đánh dấu rollback-only. Có thể là:

- Một repository SQL exception đã được catch.
- Runtime exception từ inner `@Transactional` method.
- Validation failure.
- Locking/optimistic conflict.
- Một component gọi `setRollbackOnly`.
- Transaction timeout.

### 18.2. Không “chữa” bằng catch rồi return success

Nếu inner operation đã đánh dấu rollback-only, outer code không thể biến transaction đó thành successful commit bằng cách nuốt exception.

Muốn một nhánh thất bại độc lập không rollback transaction ngoài, phải thiết kế propagation và transaction boundaries **trước**, ví dụ transaction con độc lập có semantics phù hợp. `REQUIRES_NEW` có chi phí và không tự phù hợp mọi nghiệp vụ.

### 18.3. Cần phân biệt exception escaping và JPA rule

`NoResultException` thông thường không đánh dấu transaction rollback theo JPA contract, nhưng một unchecked exception thoát khỏi Spring `@Transactional` method thường khiến Spring đánh dấu rollback theo default rollback rules.

Do đó luôn xem cả exception semantics **và** framework transaction policy.

---

## 19. Commit outcome unknown: nguy hiểm khi mất kết nối

Giả sử application gửi `COMMIT`, sau đó connection bị cắt trước khi client nhận phản hồi.

```text
Application ---- COMMIT ----> Database
Application <--- connection lost --X

Database có thể:
  - đã commit,
  - chưa commit,
  - hoặc outcome chưa được application biết.
```

Không thể luôn suy ra “không nhận được response nghĩa là DB rollback”.

### 19.1. Không retry tạo order mù quáng

Nếu lệnh create đã commit nhưng client không biết, retry toàn bộ có thể tạo order thứ hai.

Cần:

- Business idempotency key hoặc stable request ID.
- UNIQUE key tương ứng.
- Tra cứu outcome/reconcile khi cần.
- Không gửi side effect ngoài DB hai lần.
- Phân biệt transient read failure với **ambiguous commit outcome**.

### 19.2. Chờ retry không bảo đảm an toàn

Backoff có thể giúp giảm contention, nhưng **không giải quyết ambiguity của commit**. Phải có dữ liệu định danh idempotency để biết một request đã được áp dụng hay chưa.

---

# Phần V — Phục hồi theo từng nhóm lỗi

## 20. Quy trình xử lý lỗi chuẩn theo transaction scope

Một sơ đồ quyết định:

```text
JPA operation failed
       |
       v
Có transaction đã tham gia không?
       |
       v
Xác định exception chain + SQLSTATE + constraint name
       |
       +-- JPQL/mapping/schema bug
       |      -> fail fast, sửa code/migration
       |
       +-- invalid input / business unique
       |      -> rollback nếu cần, trả validation/conflict
       |
       +-- optimistic conflict
       |      -> rollback, reload/reconcile,
       |         có thể retry bounded
       |
       +-- deadlock/serialization
       |      -> rollback, transaction mới,
       |         retry bounded nếu idempotent
       |
       +-- timeout/connection failure
       |      -> xem scope/commit outcome,
       |         điều tra hạ tầng, retry có kiểm soát
       |
       +-- unknown
              -> rollback, không nuốt,
                 ghi log an toàn và báo lỗi tương ứng
```

### 20.1. Ưu tiên trả lời các câu hỏi

1. Query/mapping có hợp lệ không?
2. SQL đã được gửi đến DB chưa?
3. Exception có từ driver/database không?
4. Transaction còn active hay rollback-only?
5. Lỗi có thể lặp lại với cùng input không?
6. Nếu retry, có thể tạo side effects/trùng dữ liệu không?
7. Client có được phép xem chi tiết lỗi không?
8. Dữ liệu cuối cùng đã commit hay chưa?

### 20.2. Transaction mới, persistence context mới

Sau lỗi SQL/optimistic locking/rollback, cách xử lý an toàn thường là rollback transaction hiện tại và tạo **new unit of work**. Không mặc định EntityManager đã thất bại vẫn sẵn sàng cho business logic tiếp theo.

---

## 21. Resource-local JPA: rollback và đóng EntityManager

Ví dụ:

```java
public void confirmOrder(
        EntityManagerFactory emf,
        Long orderId) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        PurchaseOrder order =
            em.find(PurchaseOrder.class, orderId);

        if (order == null) {
            throw new OrderNotFoundException(orderId);
        }

        order.confirm();

        // Có thể phát lỗi DB/optimistic lock ở flush.
        em.flush();

        // Cũng có thể thất bại ở commit.
        em.getTransaction().commit();

    } catch (RuntimeException ex) {
        if (em.getTransaction().isActive()) {
            try {
                em.getTransaction().rollback();
            } catch (RuntimeException rollbackFailure) {
                ex.addSuppressed(rollbackFailure);
            }
        }

        throw ex;

    } finally {
        em.close();
    }
}
```

`OrderNotFoundException` là domain exception minh họa:

```java
public class OrderNotFoundException
        extends RuntimeException {

    public OrderNotFoundException(Long id) {
        super("Order not found: " + id);
    }
}
```

### 21.1. Không để rollback exception che nguyên nhân ban đầu

Trong catch, rollback cũng có thể thất bại khi connection hỏng. Ghi rollback failure vào suppressed exceptions hoặc log có kiểm soát, đồng thời giữ nguyên primary failure để điều tra.

### 21.2. Không dùng em sau close

Đóng EntityManager ở `finally` làm kết thúc context. Với retry, mở EntityManager khác; các objects của context cũ không còn là managed state đáng tin cho transaction mới.

### 21.3. Transaction status có thể đã không active

Sau commit/rollback failure, `isActive()` có thể trả false; vì vậy check trước khi rollback. Không giả định mọi exception xảy ra lúc transaction vẫn active.

---

## 22. Spring @Transactional và exception translation

Spring bổ sung các nhóm exception có ý nghĩa:

| Spring exception | Thường liên quan | Ghi chú |
| --- | --- | --- |
| `DataIntegrityViolationException` | UNIQUE/FK/NOT NULL/CHECK | Cần phân loại constraint |
| `InvalidDataAccessResourceUsageException` | SQL/schema/query resource không hợp lệ | Có thể do mapping/native SQL |
| `InvalidDataAccessApiUsageException` | API usage/query binding không đúng | Lỗi lập trình thường không retry |
| `OptimisticLockingFailureException` | Optimistic concurrency | Rollback, reload/reconcile |
| `PessimisticLockingFailureException` | Pessimistic lock failure | Xem rollback semantics |
| `CannotAcquireLockException` | Không lấy được lock | Retry có điều kiện |
| `QueryTimeoutException` (Spring DAO) | Query timeout | Không đồng nhất với JPA class |
| `JpaSystemException` | Lỗi JPA không dịch được cụ thể | Xem cause chain |
| `TransactionSystemException` | Transaction completion/system | Xem root cause/commit boundary |
| `UnexpectedRollbackException` | Transaction rollback-only | Tìm lỗi đánh dấu trước đó |

Tên lớp và phân loại thực tế tùy phiên bản Spring và provider. Không dùng bảng làm bản bảo đảm mọi Hibernate exception được map chính xác vào một Spring subclass.

### 22.1. Hai QueryTimeoutException khác package

JPA:

```java
jakarta.persistence.QueryTimeoutException
```

Spring DAO:

```java
org.springframework.dao.QueryTimeoutException
```

Đừng import nhầm khi viết `@ExceptionHandler` hoặc retry classification.

### 22.2. Repository exception translation không bao phủ mọi lỗi commit giống nhau

`@Repository` exception translation thường xử lý exception trong repository invocations. Lỗi tại transaction commit của service có thể được bọc theo transaction manager và cần xử lý ở outer boundary. Test đúng behavior trên stack thật.

### 22.3. Spring method propagation ảnh hưởng rollback

Một method `@Transactional(propagation = REQUIRED)` thường tham gia transaction đang có. Nếu inner method đánh dấu rollback-only, outer method không thể commit bằng cách bắt exception rồi tiếp tục.

`REQUIRES_NEW` là một transaction độc lập, không phải phép phục hồi mặc định. Tự gọi `this.innerMethod()` trong proxy-based Spring có thể bỏ qua transaction advice.

---

## 23. HTTP/API error mapping theo bản chất lỗi

Không gửi stack trace hay raw SQL exception tới client. Có thể chuẩn hóa response:

```java
public record ApiError(
    String code,
    String message
) {
}
```

Ma trận gợi ý:

| Loại | HTTP có thể phù hợp | Code nghiệp vụ |
| --- | --- | --- |
| Input validation sai | 400 hoặc 422 | `INVALID_INPUT` |
| Entity không tồn tại | 404 | `ORDER_NOT_FOUND` |
| UNIQUE business key trùng | 409 | `ORDER_CODE_CONFLICT` |
| Optimistic concurrency conflict | 409 | `ORDER_CHANGED_CONCURRENTLY` |
| Query syntax/mapping bug | 500 | `INTERNAL_ERROR` |
| Database hạ tầng tạm thời không sẵn sàng | 503 hoặc 500 tùy contract | `DEPENDENCY_UNAVAILABLE` |
| Deadlock/serialization hết retry budget | 503/409 tùy semantics | `RETRYABLE_OPERATION_FAILED` |
| Unauthorized database access ở backend | 500, không lộ detail | `INTERNAL_ERROR` |

Đây là **gợi ý API design**, không phải quy định JPA. Cần tách lỗi 4xx do request/business state khỏi lỗi 5xx do hệ thống.

### 23.1. Ví dụ Spring exception handler

```java
@RestControllerAdvice
public class OrderErrorAdvice {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ApiError> notFound(
            OrderNotFoundException ex) {

        return ResponseEntity
            .status(HttpStatus.NOT_FOUND)
            .body(new ApiError(
                "ORDER_NOT_FOUND",
                "Order does not exist"
            ));
    }

    @ExceptionHandler(OptimisticLockingFailureException.class)
    public ResponseEntity<ApiError> conflict(
            OptimisticLockingFailureException ex) {

        return ResponseEntity
            .status(HttpStatus.CONFLICT)
            .body(new ApiError(
                "ORDER_CHANGED_CONCURRENTLY",
                "Order was modified by another request"
            ));
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<ApiError> integrity(
            DataIntegrityViolationException ex) {

        if (DbIntegrityClassifier.isDuplicateOrderCode(ex)) {
            return ResponseEntity
                .status(HttpStatus.CONFLICT)
                .body(new ApiError(
                    "ORDER_CODE_CONFLICT",
                    "Order code is already used"
                ));
        }

        return ResponseEntity
            .status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(new ApiError(
                "DATA_INTEGRITY_ERROR",
                "Request could not be completed"
            ));
    }
}
```

Imports:

```java
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
```

Handler minh họa một phần. Các exception wrappers khác ở commit có thể cần classification ở tầng service/API sau khi transaction kết thúc.

### 23.2. Không trả SQL diagnostics ra HTTP

DB name, SQL text, constraint error detail và bind values có thể chứa dữ liệu nhạy cảm. Client chỉ cần code/message có kiểm soát; chi tiết điều tra nằm ở logs/telemetry có quyền truy cập phù hợp.

---

## 24. Retry policy: chọn lọc và giới hạn

Không có retry policy chung cho mọi `PersistenceException`.

| Lỗi | Retry nguyên input? | Vì sao |
| --- | --- | --- |
| Sai JPQL property | Không | Code lỗi |
| Entity mapping sai | Không | Bootstrap/configuration |
| Missing table/column | Không | Migration/schema mismatch |
| Bean Validation | Không | Input/state không hợp lệ |
| UNIQUE duplicate | Không, nếu cùng key | Business conflict bền vững |
| FK invalid | Không mặc định | Reference không tồn tại; sửa dữ liệu |
| Optimistic lock conflict | Có điều kiện | Cần reload/reconcile |
| Deadlock | Thường có điều kiện | DB đã abort một attempt |
| Serialization failure | Thường có điều kiện | Retry transaction mới |
| Query timeout | Có điều kiện | Có thể do tải hoặc plan |
| Connection failure trước query | Có điều kiện | Health + idempotency |
| Connection lost quanh COMMIT | Rất thận trọng | Outcome có thể unknown |

### 24.1. Mẫu retry conceptual

```text
for attempt = 1..maxAttempts:
    create NEW transaction / EntityManager
    try:
        read current state
        apply business intent
        flush and commit
        return success
    catch allowedTransientError:
        rollback and close resources
        if attempts exhausted: propagate
        bounded backoff + jitter
```

Đây là **thuật toán khái niệm**, không phải đoạn Java đồng bộ đã triển khai.

### 24.2. Cần tránh retry trong failed transaction

Một DB exception có thể làm transaction unusable. Mọi attempt mới phải có **new transaction/context** và reload dữ liệu từ DB.

### 24.3. Cần tránh duplicate external effects

Không gửi email, thu tiền hoặc publish event không idempotent giữa những attempt rồi retry toàn bộ. Cân nhắc:

- Idempotency key.
- Durable request status.
- Transactional outbox.
- Event ID và consumer deduplication.
- Cơ chế reconcile khi commit outcome không rõ.

### 24.4. Không retry vì một exception class quá rộng

`DataAccessException` và `PersistenceException` bao gồm cả bug cố định lẫn lỗi tạm thời. Retry trên superclass sẽ che root cause và tăng tải.

---

# Phần VI — Quan sát, kiểm thử và điều tra

## 25. Ghi log đủ để phân loại lỗi

Thông tin hữu ích:

- Operation name (`createOrder`, `confirmOrder`, `findByCode`).
- Correlation/request ID.
- Transaction attempt number.
- Loại exception ngoài cùng và root cause.
- SQLSTATE/vendor code khi có.
- Constraint name khi có.
- Entity type/operation (không nhất thiết raw field values).
- Giai đoạn: bootstrap, query binding, flush, commit, rollback.
- Database/provider versions và migration revision.
- Lock timeout/deadlock details nếu được phép log.
- Có retry không, vì sao dừng retry.

### 25.1. Không log toàn bộ dữ liệu nhạy cảm

SQL bind logs có thể chứa email, tokens, IDs và dữ liệu khách hàng. Chỉ bật TRACE trong môi trường kiểm soát; production cần redaction, access control và retention.

Hibernate 6 dev/test:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Đây là cấu hình Hibernate-specific. Không dùng raw SQL log như một phần public HTTP response.

### 25.2. Thời điểm exception rất có giá trị

| Mốc | Lỗi hay gặp |
| --- | --- |
| Tạo `EntityManagerFactory` | Metadata/mapping/persistence-unit config |
| `createQuery()` | JPQL syntax/semantics/result declaration |
| `setParameter()` | Tên/type parameter |
| `getResultList()`/`getSingleResult()` | SQL runtime, timeout, result cardinality |
| `persist()` | Entity state, generated ID INSERT, mapping |
| `flush()` | SQL DML, constraints, locking |
| `commit()` | Flush deferred, DB constraint, rollback-only, network ambiguity |

Không có gì bảo đảm một loại lỗi chỉ xuất hiện ở đúng một dòng; đó là các mốc để điều tra.

---

## 26. Đọc cause chain an toàn

Một helper có thể duyệt `Throwable.getCause()`:

```java
public final class ExceptionCauses {

    private ExceptionCauses() {
    }

    public static <T extends Throwable> T findCause(
            Throwable error,
            Class<T> type) {

        for (Throwable current = error;
                current != null;
                current = current.getCause()) {

            if (type.isInstance(current)) {
                return type.cast(current);
            }
        }

        return null;
    }
}
```

Ví dụ:

```java
SQLException sql = ExceptionCauses.findCause(
    exception, SQLException.class
);

if (sql != null) {
    String state = sql.getSQLState();
    int vendorCode = sql.getErrorCode();
}
```

### 26.1. SQLException còn có `getNextException()`

JDBC batch operations có thể liên kết thêm SQL exceptions bằng `SQLException.getNextException()`, không chỉ `getCause()`. Khi phân tích batch exception phức tạp, classifier production có thể cần duyệt chuỗi next-exception với phòng vệ vòng lặp.

### 26.2. Đừng sửa classifier thành một cây `instanceof` quá tổng quát

Với `DataIntegrityViolationException`, cần SQLSTATE/constraint name hoặc domain metadata phù hợp. Với unknown error, nên trả lỗi chung và log có kiểm soát thay vì đoán “khách hàng nhập sai”.

### 26.3. Cause chain có thể dài nhưng không phải bằng chứng tuyệt đối

Một provider/driver có thể không giữ đủ structured metadata. Kết luận nên dựa trên exception thực tế của stack mục tiêu và integration tests.

---

## 27. Integration test lỗi UNIQUE

Giả định database đã có constraint `uk_orders_tenant_code` hoặc dùng đơn giản `Customer` unique theo tenant/email.

### 27.1. Fixture RESOURCE_LOCAL

```java
private static Long insertCustomer(
        EntityManagerFactory emf,
        Long tenantId,
        String email) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        Customer customer = new Customer(
            tenantId, email, "Test Customer"
        );

        em.persist(customer);
        em.flush();

        Long id = customer.getId();
        em.getTransaction().commit();
        return id;

    } catch (RuntimeException ex) {
        rollbackIfActive(em);
        throw ex;

    } finally {
        em.close();
    }
}

private static void rollbackIfActive(EntityManager em) {
    if (em.isOpen() && em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
}
```

### 27.2. Tạo duplicate để DB từ chối

```java
@Test
void uniqueConstraintIsEnforcedByDatabase() {
    Long tenantId = 11L;
    String email =
        "duplicate-" + UUID.randomUUID() + "@example.test";

    insertCustomer(emf, tenantId, email);

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        RuntimeException error = assertThrows(
            RuntimeException.class,
            () -> {
                em.persist(new Customer(
                    tenantId, email, "Duplicate"
                ));
                em.flush();
                em.getTransaction().commit();
            }
        );

        SQLException sql = ExceptionCauses.findCause(
            error, SQLException.class
        );

        assertNotNull(sql);
        assertEquals("23505", sql.getSQLState());

    } finally {
        rollbackIfActive(em);
        em.close();
    }
}
```

Ví dụ test **PostgreSQL-specific** do SQLSTATE `23505`. Với DB khác cần assertion tương ứng.

Test bọc cả `persist`, `flush`, `commit` vì IDENTITY có thể gửi INSERT ngay trong `persist`, còn DB deferred constraints có thể chỉ fail ở commit.

### 27.3. Test phải kiểm chứng state cuối

Sau rollback, dùng EntityManager mới kiểm tra chỉ có **một** customer với `(tenantId, normalizedEmail)`, không dựa trên Java object thất bại.

### 27.4. Không mock DB nếu muốn kiểm chứng ràng buộc thật

Mock repository trả lỗi dựng sẵn chỉ kiểm tra mapping exception ở tầng Java; nó không chứng minh schema constraint tồn tại.

---

## 28. Integration test optimistic locking

Kịch bản hai contexts:

```text
Fixture: Order#101 version=1

EM A load Order#101
EM B load Order#101

EM A confirm + commit -> version=2
EM B confirm + flush/commit -> optimistic conflict
EM B rollback
```

Skeleton:

```java
@Test
void detectsConcurrentUpdateUsingVersion() {
    Long orderId = createDraftOrderFixture();

    EntityManager emA = emf.createEntityManager();
    EntityManager emB = emf.createEntityManager();

    try {
        emA.getTransaction().begin();
        emB.getTransaction().begin();

        PurchaseOrder a =
            emA.find(PurchaseOrder.class, orderId);

        PurchaseOrder b =
            emB.find(PurchaseOrder.class, orderId);

        a.confirm();
        emA.getTransaction().commit();

        b.confirm();

        RuntimeException conflict = assertThrows(
            RuntimeException.class,
            () -> {
                emB.flush();
                emB.getTransaction().commit();
            }
        );

        // Kiểm tra cause/exception classification
        // tương ứng provider đang dùng.
        assertTrue(isOptimisticConflict(conflict));

    } finally {
        rollbackIfActive(emB);
        rollbackIfActive(emA);
        emB.close();
        emA.close();
    }

    // Dùng EntityManager mới đọc persisted status/version.
}
```

Trong đó:

- `createDraftOrderFixture()` là helper tạo customer/order hợp lệ và **commit trước test**.
- `isOptimisticConflict()` là helper được triển khai bằng cause inspection cho `jakarta.persistence.OptimisticLockException` và provider-specific wrappers.
- Cần kiểm tra exception class thực tế với stack mục tiêu; `RollbackException` có thể bọc optimistic conflict.
- Nếu database locking/isolation khiến phép đo bị chặn thay vì optimistic conflict theo lịch mong muốn, điều chỉnh transaction schedule và environment test.

### 28.1. Kiểm tra state cuối

Một test tốt xác nhận transaction A đã commit, transaction B rollback và version/status của database là state của transaction thắng.

### 28.2. Retry phải thay context

Test retry riêng phải tạo **EntityManager/transaction mới**, tải lại version rồi áp ý định. Không dùng lại `b` detached/failure state để ghi đè mù quáng.

---

## 29. Integration test query result cardinality

```java
@Test
void getSingleResultFailsWhenNoRow() {
    EntityManager em = emf.createEntityManager();

    try {
        assertThrows(
            NoResultException.class,
            () -> em.createQuery(
                """
                SELECT o FROM PurchaseOrder o
                WHERE o.orderCode = :code
                """,
                PurchaseOrder.class
            )
            .setParameter("code", "NON-EXISTENT")
            .getSingleResult()
        );

    } finally {
        em.close();
    }
}
```

Ví dụ này kiểm tra `NoResultException` ở JPA API, không phải database unique violation.

Muốn kiểm tra `NonUniqueResultException` một cách có kiểm soát, dùng truy vấn **có thể có nhiều orders**, ví dụ `WHERE o.status = :status`, tạo từ hai fixture hợp lệ. Không cố tạo duplicate unique key chỉ để test cardinality.

### 29.1. Test query typo

Một JPQL sai property như `o.order_code` cần fail trong provider. Do error timing khác nhau, test có thể bọc cả query creation và execution.

### 29.2. Test nhầm kiểu result

Ví dụ projection constructor thiếu constructor tương ứng có thể fail tại compile/execution. Test phải assert root cause liên quan query projection, không chỉ một `RuntimeException` bất kỳ.

---

## 30. Kiểm thử lỗi migration/schema

Để phát hiện schema mismatch:

- Chạy migrations trên database test sạch.
- Tạo EntityManagerFactory bằng config mục tiêu.
- Thực thi minimal read/write/query.
- Kiểm tra unique/FK/CHECK bằng dữ liệu kiểm thử.
- Nếu dùng PostgreSQL partial/expression indexes, kiểm tra metadata và behavior.
- Đừng dựa vào H2 để xác nhận hoàn toàn PostgreSQL-specific semantics.
- Tách migration test khỏi test schema auto-generation; nếu ORM tự tạo schema, nó có thể vô tình che migration bị thiếu.

### 30.1. Lỗi startup phải fail fast

Nếu mapping không hợp lệ hoặc migration thiếu ở startup, service nên báo readiness failure hoặc fail deployment theo chính sách. Đừng để mọi request đầu tiên nhận lỗi bảng/cột chưa tồn tại rồi retry mù.

### 30.2. Không sửa schema bằng query retry

`relation does not exist` hoặc `column does not exist` là vấn đề cấu hình/triển khai, cần hành động sửa schema hoặc rollback phiên bản ứng dụng.

---

## 31. Spring Test và transaction rollback mặc định

Trong Spring integration tests, `@Transactional` trên test method có thể tạo một outer transaction và rollback khi test hoàn tất. Điều này có thể khiến test tưởng `commit()` đã xảy ra trong service nhưng thực ra service tham gia transaction của test.

Nếu muốn kiểm tra unique violation **ở commit**, cần boundary tường minh:

- Không gắn outer `@Transactional` lên test method đó.
- Dùng `TransactionTemplate` để xác định commit/rollback.
- Hoặc dùng `TestTransaction` đúng cách nếu môi trường hỗ trợ.
- Dùng context mới để xác minh state đã commit.

Không chỉ gọi `repository.save()` rồi assert DB final state khi transaction thực chưa hoàn tất.

---

## 32. Monitoring: đo loại lỗi thay vì một counter tổng

Có thể phân loại metrics theo nhóm:

```text
jpa_query_invalid_total
jpa_query_timeout_total
jpa_mapping_bootstrap_failure_total
db_unique_violation_total
db_foreign_key_violation_total
db_check_violation_total
jpa_optimistic_conflict_total
db_deadlock_total
db_serialization_failure_total
transaction_rollback_total
transaction_commit_unknown_total
```

Tên metrics minh họa, không phải counters mặc định của JPA.

### 32.1. Tỷ lệ lỗi giúp tìm nguyên nhân

- UNIQUE tăng đột biến → retry trùng key, bot, bug sinh mã, race.
- FK tăng → tạo child trước parent, xóa parent sai, dữ liệu tham chiếu không hợp lệ.
- Mapping/bootstrap failures → deployment/schema mismatch.
- Query timeout tăng → query plan hoặc DB load xấu.
- Deadlock tăng → lock ordering/transaction length.
- Optimistic conflicts tăng → tranh chấp nghiệp vụ, granular aggregate hoặc retry policy.

### 32.2. Log nên lưu correlation, không log dữ liệu nhạy cảm

Đối với SQL errors, ưu tiên SQLSTATE, constraint name, entity type, operation và request ID. Không mặc định log raw emails, payment data hoặc bind values vào mọi exception.

### 32.3. Phân biệt alert và conflict nghiệp vụ

Một lượng nhỏ HTTP 409 từ unique business key có thể là bình thường. Mất kết nối hoặc hàng loạt migration errors thường nghiêm trọng hơn và cần alert vận hành.

---

# Phần VII — Bài tập thực hành

## 33. Các tình huống và lời giải

### Bài 1. JPQL dùng tên bảng SQL

```java
SELECT o FROM purchase_orders o
```

**Đáp án:** JPQL dùng entity name `PurchaseOrder`. Sửa query; không retry.

### Bài 2. Parameter name không khớp

Query có `:code` nhưng code bind `"orderCode"`.

**Đáp án:** Sửa tên parameter. Đây là lỗi lập trình.

### Bài 3. getSingleResult không có row

**Đáp án:** Xử lý `NoResultException` theo hợp đồng not-found/optional, không mặc định là lỗi hạ tầng 500.

### Bài 4. getSingleResult trả nhiều rows

**Đáp án:** Kiểm tra query filter/cardinality/tenant scope, và UNIQUE invariant nếu business yêu cầu. Không bắt rồi chọn ngẫu nhiên một row.

### Bài 5. QueryTimeoutException

**Đáp án:** Kiểm tra query plan/index, DB load, statement/transaction semantics. Retry chỉ khi có lý do tạm thời và an toàn.

### Bài 6. `mappedBy` sai property

**Đáp án:** Mapping bug ở Java metadata. Sửa annotation và integration bootstrap test.

### Bài 7. Undefined column trong PostgreSQL

**Đáp án:** Kiểm tra migration, datasource, schema, naming strategy. SQLSTATE `42703` không phải lỗi người dùng nhập.

### Bài 8. Enum value mới không được code cũ hiểu

**Đáp án:** Version compatibility/data migration/converter mapping. Retry truy vấn không khắc phục được.

### Bài 9. Hai requests cùng tạo order code

**Đáp án:** Pre-check không đủ; DB UNIQUE bảo vệ. Trả conflict phù hợp, không retry nguyên key vô hạn.

### Bài 10. Foreign key không tồn tại

**Đáp án:** Phân loại FK, kiểm tra reference/tenant/flush ordering. Không trả “order code trùng”.

### Bài 11. @NotBlank từ chối order code

**Đáp án:** Bean Validation. Phân biệt `jakarta.validation.ConstraintViolationException` với Hibernate ORM DB exception.

### Bài 12. PostgreSQL SQLSTATE 23505

**Đáp án:** UNIQUE violation. Cần constraint name nếu muốn phân biệt email và order code.

### Bài 13. DataIntegrityViolationException không có constraint name

**Đáp án:** Không đoán business error. Dùng metadata bổ sung hoặc fallback an toàn.

### Bài 14. flush không có transaction

**Đáp án:** Có thể `TransactionRequiredException`. Sửa transaction boundary, không chỉ catch và bỏ qua.

### Bài 15. @Version conflict sau hai updates

**Đáp án:** Rollback, mở context mới, tải state mới, reconcile/retry có điều kiện.

### Bài 16. LockTimeoutException

**Đáp án:** Phân biệt statement-level và transaction-level rollback, xem Spring rules/DB state. Giảm contention và chỉ retry bounded khi an toàn.

### Bài 17. Deadlock SQLSTATE 40P01

**Đáp án:** Rollback toàn attempt, tạo transaction/context mới, retry có giới hạn và idempotent.

### Bài 18. Serialization failure 40001

**Đáp án:** Có thể retry toàn transaction từ bước đọc, không chỉ retry UPDATE thất bại.

### Bài 19. UnexpectedRollbackException ở outer service

**Đáp án:** Tìm lỗi ban đầu đã đánh dấu rollback-only; không nuốt exception rồi mong commit.

### Bài 20. Connection lost khi gửi COMMIT

**Đáp án:** Outcome có thể unknown. Dùng idempotency key và reconciliation trước retry.

### Bài 21. Spring @Transactional self-invocation

**Đáp án:** Proxy-based advice có thể không kích hoạt; điều chỉnh bean boundary hoặc dùng TransactionTemplate.

### Bài 22. Một test mock repository ném UNIQUE

**Đáp án:** Chỉ kiểm tra Java error mapping. Không chứng minh DB thật có unique constraint.

### Bài 23. H2 test pass nhưng PostgreSQL fail

**Đáp án:** Test DB target/schema/driver/isolation vì SQLSTATE, NULL, locking và collations có thể khác.

### Bài 24. Batch insert chỉ báo BatchUpdateException

**Đáp án:** Xem `SQLException.getNextException()` và cause chain để tìm SQLState/constraint; rollback và kiểm tra transaction outcome.

### Bài 25. Email gateway gửi trong transaction rồi deadlock

**Đáp án:** Retry transaction có thể gửi email lần hai. Dùng outbox/idempotent message flow.

### Bài 26. Missing table chỉ xuất hiện production

**Đáp án:** Kiểm tra deployment/migration/schema/data source. Không coi là transient query failure để retry vô hạn.

### Bài 27. Query typo bị gọi là 404

**Đáp án:** Sai: 404 là not-found theo dữ liệu. JPQL invalid là lỗi implementation/configuration, không phải bản ghi vắng mặt.

### Bài 28. CHECK constraint violation vì native UPDATE

**Đáp án:** Xác minh business rule và DB CHECK. Native SQL có thể bypass Java domain validators.

### Bài 29. Commit thành công nhưng after-commit email lỗi

**Đáp án:** Không thể rollback DB đã commit. Sử dụng outbox/retry và phân loại notification failure riêng.

### Bài 30. Optimistic conflict được retry mà không reload

**Đáp án:** Sai: phiên bản và business state cũ vẫn stale. Mỗi attempt cần context mới và re-evaluate.

---

## 34. Checklist điều tra một JPA exception

Trước khi kết luận, hãy kiểm tra:

1. Lỗi xảy ra ở bootstrap, query creation, query execution, flush hay commit?
2. Entity và persistence unit có được scan/đăng ký đúng?
3. JPQL dùng tên entity và mapped attributes?
4. Parameters có được bind đúng tên/type?
5. Kết quả truy vấn cho phép zero/multiple rows không?
6. Mapping relationship có `mappedBy` đúng?
7. `@Id`, `@Version`, `@Converter`, enum mappings có đúng?
8. Database migration đã chạy đúng môi trường chưa?
9. Tên table/column/schema/search_path có trùng?
10. DB permissions/credentials có phù hợp?
11. Có Bean Validation failure không?
12. Có DB constraint violation không?
13. Là UNIQUE, FK, NOT NULL hay CHECK?
14. Constraint/index name có được cung cấp không?
15. Có SQLSTATE/vendor error code không?
16. SQLSTATE là theo DB engine nào?
17. Có `SQLException.getNextException()` khi batch không?
18. Transaction có active/joined không?
19. Transaction đã rollback-only/aborted chưa?
20. Lỗi có xảy ra tại commit sau khi method body trả?
21. Có optimistic version conflict không?
22. Có lock timeout/deadlock/serialization failure không?
23. Nếu commit bị mất kết nối, outcome có unknown không?
24. Có external side effects khiến retry không idempotent không?
25. Có thể rollback và mở context mới không?
26. Có đủ transaction budget/deadline cho retry?
27. HTTP status/error code có phân biệt business và system failure?
28. Có log correlation ID nhưng không lộ dữ liệu nhạy cảm?
29. Integration test có dùng database mục tiêu?
30. Có test cả data correctness sau rollback/commit?
31. Error classification có bị catch quá rộng?
32. Có cơ chế monitoring theo lỗi thay vì một counter chung?

---

## 35. Sơ đồ phân loại nhanh

```text
                   JPA operation failed
                            |
                            v
                   Có root cause nào?
                            |
         +------------------+-------------------+
         |                  |                   |
         v                  v                   v
   Query/Mapping      DB Constraint       Transaction/Lock
         |                  |                   |
         v                  v                   v
  JPQL/parameter?      SQLSTATE 23?       Version conflict?
  Metadata/schema?     Constraint name?   Deadlock/timeout?
         |                  |                   |
         v                  v                   v
  Fix code/migrate    4xx/business or     Rollback and decide
  Test boot/query     integrity error     whether retry is safe
         |                  |                   |
         +------------------+-------------------+
                            |
                            v
                  Verify transaction outcome
                            |
                            v
             Never reuse failed persistence context
                    without valid recovery
```

Sơ đồ giúp định hướng; với lỗi connection và ambiguous commit cần nhánh phân tích riêng để tránh retry gây trùng.

---

## 36. Kết luận

Một exception từ JPA không chỉ là “lỗi database”. Nó thường thuộc một trong bốn nhóm chính:

1. **Lỗi truy vấn**: JPQL/parameters/cardinality/timeout. Sửa code hoặc xử lý dữ liệu vắng mặt theo hợp đồng; không retry lỗi cú pháp.
2. **Lỗi ánh xạ**: entity metadata, relationship, converter hoặc schema mismatch. Sửa mapping/migration và fail fast khi khởi tạo.
3. **Lỗi ràng buộc**: Bean Validation hoặc UNIQUE/FK/NOT NULL/CHECK ở database. Phân loại đúng constraint, rollback và trả lỗi nghiệp vụ thích hợp.
4. **Lỗi giao dịch**: transaction boundary, optimistic/pessimistic lock, deadlock, serialization failure, rollback-only hoặc commit outcome không rõ. Xem transaction status, tạo unit of work mới và retry **chỉ khi an toàn**.

Những điểm cần nhớ:

- **Không chỉ đọc exception class ngoài cùng**; xem cause chain, SQLSTATE/vendor code và constraint name.
- **`persist()` không bảo đảm đã ghi**, **`flush()` không phải commit**, và lỗi có thể lộ ở **`commit()`**.
- **Không xem `NoResultException` là query syntax error**, cũng không xem mọi `DataIntegrityViolationException` là duplicate.
- **Mapping/schema bugs thường không thể sửa bằng retry**, trong khi một số deadlock/serialization failures có thể retry giao dịch mới.
- **Sau failed transaction, rollback và bỏ persistence context lỗi** trước khi tiếp tục.
- **Không retry toàn transaction có external side effects mà chưa có idempotency/outbox**, đặc biệt khi outcome của commit chưa rõ.
- **Kiểm thử với database/provider thực tế** để xác minh SQLSTATE, constraint names, rollback, optimistic locks và transaction propagation.
- **Trả error code rõ ràng, log đủ metadata nhưng không lộ SQL/bind values nhạy cảm**.

**Phân loại lỗi chính xác là điều kiện tiên quyết của phục hồi đúng: lỗi lập trình cần được sửa, lỗi dữ liệu cần được giải thích, lỗi đồng thời cần được đối soát và lỗi hạ tầng chỉ được retry khi transaction outcome và idempotency cho phép.**
