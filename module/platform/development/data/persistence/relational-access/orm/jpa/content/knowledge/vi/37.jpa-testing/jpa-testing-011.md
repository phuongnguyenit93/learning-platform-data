# Kiểm thử ràng buộc, NULL, số thập phân và thời gian trong JPA

Một entity có thể được lưu thành công trên môi trường test nhưng thất bại hoặc trả dữ liệu sai trên database production. Những sai lệch khó nhận thấy thường tập trung vào bốn nhóm: **ràng buộc toàn vẹn**, **NULL**, **số thập phân** và **thời gian**.

Ví dụ:

```java
@Column(
    name = "total_amount",
    precision = 14,
    scale = 2
)
private BigDecimal totalAmount;
```

Annotation trên mô tả metadata ánh xạ, nhưng **không tự chứng minh mọi giá trị có hơn hai chữ số thập phân sẽ bị từ chối**. PostgreSQL có thể làm tròn khi ghi vào `NUMERIC(14,2)`. Tương tự, một thuộc tính `@Column(nullable = false)` trong Java không chứng minh schema production đã có `NOT NULL`, còn một thời điểm `Instant` lưu vào cột timestamp có thể mất những chữ số nano vượt độ chính xác của database.

Một bài kiểm thử đúng cần trả lời cả bốn câu hỏi:

1. **Ứng dụng** có kiểm tra input và bất biến nghiệp vụ như mong muốn không?
2. **JPA provider** có ánh xạ giá trị và phát SQL phù hợp không?
3. **Database thực** có enforce constraint, NULL semantics, numeric precision/scale và temporal type đúng không?
4. Sau **commit**, khi đọc bằng một persistence context mới, dữ liệu có đúng hợp đồng không?

Bài thuộc chủ đề **Data Persistence Relational Access ORM JPA**, chương **Kiểm thử JPA**, với đề mục trực tiếp **“Kiểm thử ràng buộc, NULL, số thập phân và thời gian”**.

Sau bài học, người đọc sẽ:

- Thiết kế integration tests kiểm tra `NOT NULL`, `UNIQUE`, `FOREIGN KEY`, `CHECK` trên database thật.
- Phân biệt Bean Validation với SQL constraint violation và lỗi ở `persist`, `flush`, `commit`.
- Kiểm thử ba trạng thái khác nhau: null, chuỗi rỗng và chuỗi toàn khoảng trắng.
- Hiểu SQL three-valued logic, `IS NULL` và các trường hợp `UNIQUE` cho phép nhiều NULL.
- Dùng `BigDecimal` với `precision`, `scale`, `@Digits`, rounding policy và boundary values rõ ràng.
- Phân biệt `LocalDate`, `LocalDateTime`, `Instant`, `OffsetDateTime` và kiểu cột database.
- Thiết kế phép thử thời điểm qua nhiều múi giờ, thời điểm chuyển giờ mùa hè (DST), độ chính xác microsecond và truy vấn khoảng thời gian.
- Kiểm tra kết quả thực bằng EntityManager mới sau commit, tránh L1 cache/transaction rollback mặc định che lỗi.
- Dùng JUnit 5, Testcontainers, PostgreSQL và JPA RESOURCE_LOCAL; biết điều chỉnh cho Spring Data JPA.

**Nguyên tắc trung tâm:** *Đừng chỉ kiểm tra một object Java sau `persist()` hoặc `flush()`. Hãy định nghĩa điều kiện ở tầng Java và database, commit giao dịch, rồi đọc lại bằng ngữ cảnh mới để xác nhận giá trị và ràng buộc thực tế.*

---

## 1. Bốn tầng cần kiểm thử

Một thao tác ghi có thể đi qua:

```text
DTO / request validation
         |
         v
Domain invariant
         |
         v
Bean Validation + JPA mapping
         |
         v
Provider / JDBC / SQL execution
         |
         v
Database constraints + column types
         |
         v
Transaction COMMIT
         |
         v
NEW EntityManager
         |
         v
Assert committed state
```

Mỗi tầng có thể thất bại ở thời điểm khác nhau.

### 1.1. Không đồng nhất metadata JPA và schema database

| Khai báo Java | Mục đích | Điều **chưa** được chứng minh |
| --- | --- | --- |
| `@Column(nullable=false)` | Metadata nullability | Cột production thực sự `NOT NULL` |
| `@Column(unique=true)` | Metadata unique | Constraint/index đã được migrate đúng |
| `@Table(uniqueConstraints=...)` | Khai báo unique constraint trong metadata | Unique behavior của database mục tiêu |
| `@JoinColumn(nullable=false)` | Metadata join column | FK và `NOT NULL` thực tế đúng |
| `@Digits(integer=12,fraction=2)` | Bean Validation digits | Database sẽ từ chối mọi SQL trực tiếp sai scale |
| `@DecimalMin("0.00")` | Bean Validation minimum | Có DB `CHECK (amount >= 0)` |
| `@Column(precision=14,scale=2)` | Metadata cột numeric | Chính sách rounding đã được áp trước SQL |
| `Instant` | Java instant trên trục UTC | Cột DB lưu được mọi nanosecond |
| `LocalDate` | Ngày lịch không có thời điểm | Tất cả clients dùng cùng timezone khi chuyển ngày |

**Bộ kiểm thử nên có hai nhóm độc lập:** tests validation ở application và tests enforcing ràng buộc của database.

### 1.2. Đừng chờ database làm công việc của domain validation

Database thường bảo vệ các invariant nền tảng: khóa ngoại, duy nhất, không null, phạm vi giá trị. Domain layer cần quyết định **ngữ nghĩa**: email có hợp lệ không, số tiền có được làm tròn không, ngày thanh toán có được ở tương lai không, hay một đơn hàng có được chuyển trạng thái không.

Không phải mọi business rule có thể hoặc nên biểu diễn thành một DB constraint.

### 1.3. Test phải có giả thuyết cụ thể

Ví dụ:

> Trong cùng một tenant, hai hóa đơn không được có cùng `invoiceNumber`. Ở hai tenants khác nhau, chúng có thể có cùng `invoiceNumber`.

Đây là test contract tốt hơn câu:

> Gọi `save` và kỳ vọng không có exception.

Nó buộc test tạo **ít nhất hai tình huống**: duplicate cùng tenant bị từ chối và duplicate khác tenant được chấp nhận.

---

# Phần I — Mô hình hóa dữ liệu để kiểm thử

## 2. Bài toán: Customer và Invoice

Ta dùng hai bảng:

```text
customers
   id (PK)
   full_name (NOT NULL)

invoices
   id (PK)
   tenant_id (NOT NULL)
   invoice_number (NOT NULL)
   customer_id (FK, NOT NULL)
   external_ref (NULL allowed)
   total_amount NUMERIC(14,2) (NOT NULL)
   status (CHECK)
   issue_date DATE (NOT NULL)
   created_at TIMESTAMPTZ (NOT NULL)
   paid_at TIMESTAMPTZ (NULL allowed)
```

Quy tắc nghiệp vụ:

1. `Invoice` phải thuộc một tenant.
2. Cặp `(tenant_id, invoice_number)` phải duy nhất.
3. Một invoice phải tham chiếu customer có thật.
4. Số tiền không âm và phải được quyết định với tối đa hai chữ số thập phân, **không tự làm tròn ngoài ý muốn**.
5. `issueDate` là ngày lịch; `createdAt`/`paidAt` là các thời điểm.
6. `paidAt` có thể null trước khi thanh toán.
7. `status` chỉ thuộc các giá trị đã định nghĩa.

Các ví dụ dùng Java 17+, `jakarta.persistence`, Bean Validation và PostgreSQL. Những phần riêng PostgreSQL sẽ được ghi chú, không xem là đặc tả portable của JPA.

---

## 3. Enum InvoiceStatus

```java
package com.example.invoice;

public enum InvoiceStatus {
    DRAFT,
    ISSUED,
    PAID,
    CANCELLED
}
```

Trong entity, dùng:

```java
@Enumerated(EnumType.STRING)
private InvoiceStatus status;
```

### 3.1. Vì sao ưu tiên STRING hơn ORDINAL trong bài học?

Với `ORDINAL`, thay thứ tự các enum constants có thể thay nghĩa dữ liệu cũ. Với `STRING`, tên constant được lưu rõ hơn, nhưng vẫn cần chiến lược migration khi đổi tên enum.

### 3.2. DB CHECK cần đồng bộ enum

Nếu Java thêm `REFUNDED` nhưng database `CHECK` chưa cho phép, provider vẫn có thể parse enum và object Java hợp lệ, nhưng INSERT/UPDATE sẽ bị DB từ chối. Test phải đi qua migrations thật để phát hiện mismatch.

---

## 4. Entity Customer

```java
package com.example.invoice;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.validation.constraints.NotBlank;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank
    @Column(name = "full_name", nullable = false)
    private String fullName;

    protected Customer() {
    }

    public Customer(String fullName) {
        if (fullName == null || fullName.isBlank()) {
            throw new IllegalArgumentException(
                "fullName is required"
            );
        }
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }
}
```

Ở ví dụ này, `@NotBlank` bảo vệ dữ liệu qua Bean Validation nếu được kích hoạt; `NOT NULL` ở database còn phải được kiểm tra độc lập.

**Không kết luận đã test NOT NULL ở DB chỉ vì `new Customer(null)` bị constructor từ chối.**

---

## 5. Entity Invoice

```java
package com.example.invoice;

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
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

@Entity
@Table(
    name = "invoices",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_invoices_tenant_number",
        columnNames = {"tenant_id", "invoice_number"}
    )
)
public class Invoice {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotNull
    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @NotNull
    @Column(name = "invoice_number", nullable = false)
    private String invoiceNumber;

    @NotNull
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(name = "external_ref")
    private String externalRef;

    @NotNull
    @DecimalMin("0.00")
    @Digits(integer = 12, fraction = 2)
    @Column(
        name = "total_amount",
        nullable = false,
        precision = 14,
        scale = 2
    )
    private BigDecimal totalAmount;

    @NotNull
    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private InvoiceStatus status;

    @NotNull
    @Column(name = "issue_date", nullable = false)
    private LocalDate issueDate;

    @NotNull
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "paid_at")
    private Instant paidAt;

    protected Invoice() {
    }

    public Invoice(
            Long tenantId,
            String invoiceNumber,
            Customer customer,
            BigDecimal totalAmount,
            LocalDate issueDate,
            Instant createdAt) {

        this.tenantId = tenantId;
        this.invoiceNumber = invoiceNumber;
        this.customer = customer;
        this.totalAmount = totalAmount;
        this.issueDate = issueDate;
        this.createdAt = createdAt;
        this.status = InvoiceStatus.DRAFT;
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getInvoiceNumber() {
        return invoiceNumber;
    }

    public String getExternalRef() {
        return externalRef;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public InvoiceStatus getStatus() {
        return status;
    }

    public LocalDate getIssueDate() {
        return issueDate;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getPaidAt() {
        return paidAt;
    }

    public Customer getCustomer() {
        return customer;
    }

    public void assignExternalRef(String value) {
        externalRef = value;
    }

    public void markPaid(Instant when) {
        if (when == null) {
            throw new IllegalArgumentException(
                "Payment time is required"
            );
        }
        if (status != InvoiceStatus.ISSUED) {
            throw new IllegalStateException(
                "Invoice must be issued before payment"
            );
        }
        paidAt = when;
        status = InvoiceStatus.PAID;
    }

    public void issue() {
        if (status != InvoiceStatus.DRAFT) {
            throw new IllegalStateException(
                "Only drafts may be issued"
            );
        }
        status = InvoiceStatus.ISSUED;
    }
}
```

### 5.1. Constructors trong ví dụ cố ý đơn giản

Đây là entity cho kiểm thử mapping. Production domain nên có factories/commands để validate `tenantId`, invoice number, money scale và tenant ownership chặt chẽ hơn.

### 5.2. `@Digits` không tự định nghĩa chính sách làm tròn

Annotation Bean Validation hạn chế số chữ số phần nguyên/phần thập phân của giá trị Java, nhưng database có thể tự round khi nhận `NUMERIC(14,2)`. Nếu yêu cầu **không được làm tròn**, cần business guard trước khi SQL được gửi.

### 5.3. `@Column` không thay migration

Một entity có `@Column(precision=14,scale=2)` không chứng minh cột đang chạy là `NUMERIC(14,2)`. Phải kiểm tra migrations/schema thực.

---

## 6. DDL PostgreSQL dùng trong integration tests

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT
        AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL
);

CREATE TABLE invoices (
    id BIGINT GENERATED BY DEFAULT
        AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    invoice_number VARCHAR(80) NOT NULL,
    customer_id BIGINT NOT NULL,
    external_ref VARCHAR(100),
    total_amount NUMERIC(14,2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    issue_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    paid_at TIMESTAMPTZ,

    CONSTRAINT uk_invoices_tenant_number
        UNIQUE (tenant_id, invoice_number),

    CONSTRAINT fk_invoices_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id),

    CONSTRAINT ck_invoices_amount
        CHECK (total_amount >= 0),

    CONSTRAINT ck_invoices_status
        CHECK (
            status IN (
                'DRAFT',
                'ISSUED',
                'PAID',
                'CANCELLED'
            )
        )
);

CREATE UNIQUE INDEX uk_invoices_tenant_external_ref
    ON invoices (tenant_id, external_ref);
```

### 6.1. Vai trò từng constraint

| Constraint/cột | Hợp đồng |
| --- | --- |
| `customers.full_name NOT NULL` | Cột không nhận SQL NULL |
| `invoices.tenant_id NOT NULL` | Invoice phải có tenant |
| `uk_invoices_tenant_number` | Không trùng invoice number trong tenant |
| `fk_invoices_customer` | Customer ID phải tham chiếu row tồn tại |
| `total_amount NUMERIC(14,2)` | Tối đa 14 chữ số, gồm 2 chữ số phần thập phân theo PostgreSQL |
| `ck_invoices_amount` | Giá trị sau chuyển kiểu không âm |
| `ck_invoices_status` | Chỉ lưu các trạng thái cho phép |
| `issue_date DATE` | Ngày lịch |
| `created_at TIMESTAMPTZ` | Thời điểm có diễn giải theo timezone |
| `paid_at TIMESTAMPTZ NULL` | Chưa thanh toán có thể không có thời điểm |
| Index unique trên `external_ref` | Unique theo tenant với semantics NULL của PostgreSQL |

### 6.2. DDL này là nguồn sự thật trong test

Nếu test muốn chứng minh migrations production, phải chạy migration thực tế (chẳng hạn Flyway/Liquibase), không cho Hibernate tự dựng schema rồi gọi đó là kiểm thử migration.

### 6.3. `NUMERIC(14,2)` không có nghĩa chặn input có scale = 3

PostgreSQL có thể **làm tròn** giá trị trước khi lưu. Vì vậy assertion kiểu “INSERT 1.235 phải thất bại” có thể sai nếu chỉ có numeric column và CHECK như trên.

### 6.4. FK không tự bảo đảm cùng tenant

DDL `customer_id REFERENCES customers(id)` kiểm tra row tồn tại, **chưa kiểm tra** customer có thuộc tenant của invoice hay không. Nếu ứng dụng multi-tenant, cần bổ sung authorization/domain logic hoặc constraint phù hợp, ví dụ composite keys/FK ở schema được thiết kế có tenant.

---

# Phần II — Phân biệt Bean Validation và database constraints

## 7. Hai loại ConstraintViolationException

Có hai exception rất dễ bị nhầm:

**Bean Validation:**

```java
jakarta.validation.ConstraintViolationException
```

**Hibernate ORM database constraint:**

```java
org.hibernate.exception.ConstraintViolationException
```

Hai class có **cùng simple name** nhưng package và semantics khác nhau.

### 7.1. Bean Validation có thể chạy trước SQL

Nếu property có:

```java
@NotNull
private BigDecimal totalAmount;
```

và integration với Bean Validation được bật, entity có thể bị từ chối khi persistence lifecycle validation diễn ra, trước khi INSERT/UPDATE gửi DB.

Đây không phải chứng minh database `NOT NULL` hoặc `CHECK`.

### 7.2. Database vẫn là hàng rào cuối

Một native SQL query hoặc external integration có thể bỏ qua Bean Validation của entity Java. Database constraints bảo vệ dữ liệu chung cho nhiều writers.

### 7.3. Đừng bắt mọi exception rồi trả một lỗi duy nhất

Một `DataIntegrityViolationException` trong Spring có thể bọc `UNIQUE`, `FK`, `NOT NULL` hay `CHECK`. Phải phân loại SQLSTATE/constraint name nếu muốn trả business error chính xác.

---

## 8. Test trực tiếp Bean Validation

Ví dụ tạo `Validator`:

```java
ValidatorFactory factory =
    Validation.buildDefaultValidatorFactory();

Validator validator = factory.getValidator();
```

Kiểm tra một entity sai:

```java
Invoice invoice = new Invoice(
    1L,
    "INV-001",
    validCustomer,
    new BigDecimal("-0.01"),
    LocalDate.of(2026, 7, 1),
    Instant.parse("2026-07-01T00:00:00Z")
);

Set<ConstraintViolation<Invoice>> violations =
    validator.validate(invoice);

assertFalse(violations.isEmpty());
```

Imports:

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import java.util.Set;
```

### 8.1. Validator test không cần database

Ưu điểm là nhanh và xác nhận annotation constraints. Nó **không kiểm tra** DB schema, `@Column` precision, SQL CHECK hoặc actual constraint names.

### 8.2. Xác nhận property path

Thay vì chỉ `!violations.isEmpty()`, test tốt hơn có thể xác minh:

```java
boolean totalAmountInvalid =
    violations.stream().anyMatch(
        violation ->
            "totalAmount".equals(
                violation.getPropertyPath().toString()
            )
    );

assertTrue(totalAmountInvalid);
```

### 8.3. Tách Bean Validation khỏi constructor validation

Nếu constructor ném exception trước khi tạo entity, test đó là domain validation; muốn kiểm tra Bean Validation annotation phải có object chứa state invalid (qua factory/test-only path phù hợp) để validator thực sự chạy.

Không làm yếu domain API production chỉ để tạo dữ liệu lỗi trong một unit test.

---

# Phần III — Bộ khung integration test JPA

## 9. Vì sao dùng database mục tiêu?

H2 thuận tiện nhưng các vấn đề sau có thể khác PostgreSQL:

- `UNIQUE` + `NULL`.
- Numeric scale/rounding.
- Timestamp precision.
- Kiểu `TIMESTAMPTZ`.
- Enum/SQL CHECK.
- SQLSTATE và constraint metadata.
- Constraint deferral.
- Timezone/collation.
- Transaction isolation.
- Native SQL dialect.

Nếu production dùng PostgreSQL, nên dùng PostgreSQL trong tests quan trọng về schema semantics. Testcontainers giúp khởi động database cô lập.

---

## 10. Dependencies của test

Các thành phần cần có:

- Jakarta Persistence API/JPA provider (ví dụ Hibernate).
- PostgreSQL JDBC driver.
- Jakarta Bean Validation provider (ví dụ Hibernate Validator).
- JUnit Jupiter.
- Testcontainers PostgreSQL và JUnit Jupiter integration.
- Flyway hoặc công cụ migration tương ứng nếu test migrations.

Mục tiêu của bài là thiết kế kiểm thử, không khóa một version thư viện cụ thể. Dùng versions tương thích trong dependency management của project.

### 10.1. Không giả định JPA tự validate mọi annotations

Nếu Bean Validation provider không có trên classpath hoặc validation mode/config tắt validation, hành vi `@NotNull` và `@Digits` trước SQL có thể khác. Test phải xác minh behavior của deployment mục tiêu.

---

## 11. JUnit 5 + Testcontainers + Flyway + RESOURCE_LOCAL

Phác thảo test fixture:

```java
package com.example.invoice;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import java.util.HashMap;
import java.util.Map;

@Testcontainers
class InvoicePersistenceIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    private static EntityManagerFactory emf;

    @BeforeAll
    static void setup() {
        Flyway.configure()
            .dataSource(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword()
            )
            .locations("classpath:db/migration")
            .load()
            .migrate();

        Map<String, Object> properties = new HashMap<>();

        properties.put(
            "jakarta.persistence.jdbc.driver",
            "org.postgresql.Driver"
        );
        properties.put(
            "jakarta.persistence.jdbc.url",
            postgres.getJdbcUrl()
        );
        properties.put(
            "jakarta.persistence.jdbc.user",
            postgres.getUsername()
        );
        properties.put(
            "jakarta.persistence.jdbc.password",
            postgres.getPassword()
        );

        // Hibernate-specific: test schema đã migrate.
        properties.put(
            "hibernate.hbm2ddl.auto",
            "validate"
        );

        emf = Persistence.createEntityManagerFactory(
            "invoice-it",
            properties
        );
    }

    @AfterAll
    static void tearDown() {
        if (emf != null) {
            emf.close();
        }
    }
}
```

Trong ví dụ, migration SQL ở phần 6 được đặt tại `src/test/resources/db/migration/V1__invoice_schema.sql` hoặc đường dẫn tương đương theo Flyway conventions.

### 11.1. Persistence unit cho tests

`src/test/resources/META-INF/persistence.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">

    <persistence-unit
        name="invoice-it"
        transaction-type="RESOURCE_LOCAL">

        <provider>
            org.hibernate.jpa.HibernatePersistenceProvider
        </provider>

        <class>com.example.invoice.Customer</class>
        <class>com.example.invoice.Invoice</class>

        <exclude-unlisted-classes>true</exclude-unlisted-classes>
    </persistence-unit>
</persistence>
```

Tên persistence unit và package phải khớp class trong project. Hibernate property `hibernate.hbm2ddl.auto=validate` kiểm tra một số khía cạnh schema, **không chứng minh tất cả constraints/indexes đã đúng**; các SQL-level tests vẫn cần thiết.

### 11.2. Đừng kết nối tests với production

Testcontainers dùng tài khoản/password của một container ephemeral. Không dùng `DB_PASSWORD` production trong integration tests hoặc PR CI.

### 11.3. Không dùng `create-drop` để chứng minh migrations

Nếu Hibernate tự sinh cả schema từ entity metadata, test có thể che đi một migration bị quên, thiếu CHECK, thiếu UNIQUE hoặc sai temporal type.

---

## 12. Transaction helper có commit thật

Trong cùng test class:

```java
private static <T> T tx(
        java.util.function.Function<EntityManager, T> body) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        T result = body.apply(em);

        // SQL/validation lỗi có thể xảy ra tại flush.
        em.flush();

        // Deferred constraints có thể lỗi ở commit.
        em.getTransaction().commit();

        return result;

    } catch (RuntimeException primary) {
        try {
            if (em.getTransaction().isActive()) {
                em.getTransaction().rollback();
            }
        } catch (RuntimeException rollbackFailure) {
            primary.addSuppressed(rollbackFailure);
        }

        throw primary;

    } finally {
        em.close();
    }
}
```

### 12.1. Tại sao phải bao cả flush và commit?

Một constraint violation có thể xuất hiện tại `persist` (đặc biệt với generated IDs), `flush`, hoặc `commit` (ví dụ deferred constraints). Bắt exception ở **toàn bộ transaction attempt** tránh test phụ thuộc sai vào timing.

### 12.2. Không tiếp tục dùng context sau SQL exception

Sau database constraint failure, transaction có thể rollback-only/aborted. Test phải rollback/close rồi dùng EM mới để xác minh DB.

### 12.3. `commit()` có thể thất bại

Không khẳng định giao dịch thành công chỉ vì `em.flush()` chạy qua. Chỉ trả success khi transaction boundary hoàn tất.

---

## 13. Read helper bằng EntityManager mới

```java
private static <T> T readFresh(
        java.util.function.Function<EntityManager, T> body) {

    EntityManager em = emf.createEntityManager();

    try {
        return body.apply(em);
    } finally {
        em.close();
    }
}
```

Một fresh context giúp tránh first-level cache giữ entity cũ hoặc pending changes chưa commit.

### 13.1. Read consistency còn phụ thuộc transaction isolation

Một context mới không tự thay đổi isolation của database. Khi cần consistency theo snapshot, hãy khai báo transaction/isolation policy rõ; bài test dùng transactions đã commit trước khi verify để giảm ambiguity.

### 13.2. Không dùng `em.find` của attempt thất bại

Persistence context sau failed flush có thể không an toàn; nếu cần verify outcome, dùng context/connection mới sau cleanup.

---

## 14. Tạo fixtures có reference hợp lệ

```java
private static Long createCustomer(String name) {
    return tx(em -> {
        Customer customer = new Customer(name);
        em.persist(customer);
        em.flush();
        return customer.getId();
    });
}
```

Tạo invoice:

```java
private static Long createInvoice(
        Long tenantId,
        String invoiceNumber,
        Long customerId,
        BigDecimal amount,
        LocalDate issueDate,
        Instant createdAt) {

    return tx(em -> {
        Customer customer =
            em.find(Customer.class, customerId);

        if (customer == null) {
            throw new IllegalArgumentException(
                "Customer fixture missing"
            );
        }

        Invoice invoice = new Invoice(
            tenantId,
            invoiceNumber,
            customer,
            amount,
            issueDate,
            createdAt
        );

        em.persist(invoice);
        em.flush();

        return invoice.getId();
    });
}
```

### 14.1. Tạo invoiceNumber unique cho từng test

```java
String number =
    "INV-" + java.util.UUID.randomUUID();
```

Không dùng cùng một số hóa đơn cố định trong nhiều tests nếu DB/container được share và tests chạy song song.

### 14.2. Không dùng fixture sai cho positive tests

Một test numeric rounding không nên tình cờ thất bại do customer FK thiếu. Giữ tất cả các fields khác hợp lệ để lỗi được quan sát chỉ thuộc điều đang kiểm tra.

### 14.3. `IDENTITY` có thể INSERT sớm

Trong ví dụ provider có thể phải gửi INSERT khi `persist()` để lấy ID. Vì vậy helper gọi `flush()` trước khi trả ID, song lỗi vẫn có thể xảy ra sớm hơn.

---

# Phần IV — Kiểm thử ràng buộc toàn vẹn

## 15. Test UNIQUE trong cùng tenant

```java
@Test
void rejectsDuplicateInvoiceNumberInSameTenant() {
    Long customerId = createCustomer("Customer A");
    Long tenantId = 101L;

    String invoiceNumber =
        "INV-" + UUID.randomUUID();

    createInvoice(
        tenantId,
        invoiceNumber,
        customerId,
        new BigDecimal("10.00"),
        LocalDate.of(2026, 6, 1),
        Instant.parse("2026-06-01T00:00:00Z")
    );

    RuntimeException error = assertThrows(
        RuntimeException.class,
        () -> createInvoice(
            tenantId,
            invoiceNumber,
            customerId,
            new BigDecimal("20.00"),
            LocalDate.of(2026, 6, 2),
            Instant.parse("2026-06-02T00:00:00Z")
        )
    );

    assertTrue(
        hasSqlState(error, "23505")
    );
}
```

`23505` là PostgreSQL `unique_violation`. `hasSqlState` được minh họa ở phần sau.

### 15.1. Khẳng định lỗi đúng nguyên nhân

Nếu chỉ `assertThrows(RuntimeException.class, ...)`, test có thể xanh vì mất kết nối hoặc thiếu bảng. Phải inspect SQLSTATE/constraint name phù hợp.

### 15.2. Cần verify row count sau rollback

```java
Long count = readFresh(em ->
    em.createQuery(
        """
        SELECT COUNT(i)
        FROM Invoice i
        WHERE i.tenantId = :tenant
          AND i.invoiceNumber = :number
        """,
        Long.class
    )
    .setParameter("tenant", tenantId)
    .setParameter("number", invoiceNumber)
    .getSingleResult()
);

assertEquals(1L, count);
```

Tình huống này xác nhận chỉ invoice đầu tiên tồn tại. Không chỉ dựa vào exception class.

### 15.3. Constraint thực tế là composite key

Nếu unique constraint không có `tenant_id`, hai tenants sẽ không được trùng invoice number; nếu unique chỉ trên tenant, duplicate trong tenant sẽ lọt qua. Positive và negative tests phải bao phủ cả hai chiều.

---

## 16. Test cùng invoice number ở hai tenants

```java
@Test
void sameInvoiceNumberIsAllowedInDifferentTenants() {
    Long customerId = createCustomer("Shared Test Customer");
    String number =
        "INV-" + UUID.randomUUID();

    Long firstId = createInvoice(
        201L,
        number,
        customerId,
        new BigDecimal("1.00"),
        LocalDate.of(2026, 7, 1),
        Instant.parse("2026-07-01T00:00:00Z")
    );

    Long secondId = createInvoice(
        202L,
        number,
        customerId,
        new BigDecimal("2.00"),
        LocalDate.of(2026, 7, 1),
        Instant.parse("2026-07-01T00:00:01Z")
    );

    assertNotEquals(firstId, secondId);
}
```

Đây là test phạm vi của `UNIQUE (tenant_id, invoice_number)`.

**Lưu ý:** ví dụ Customer chưa được scope theo tenant. Nếu production yêu cầu Customer thuộc đúng tenant, test fixture và schema cần bổ sung tenant ownership để không vô tình hợp thức hóa tham chiếu chéo tenant.

---

## 17. Test NOT NULL ở database, tránh Bean Validation chặn trước

Nếu constructor hoặc `@NotNull` từ chối null trước khi SQL, chưa chứng minh DB có ràng buộc `NOT NULL`.

Một test DB riêng dùng SQL constant trong môi trường test:

```java
@Test
void databaseRejectsNullCustomerName() {
    RuntimeException error = assertThrows(
        RuntimeException.class,
        () -> tx(em -> {
            em.createNativeQuery(
                """
                INSERT INTO customers(full_name)
                VALUES (NULL)
                """
            ).executeUpdate();
            return null;
        })
    );

    assertTrue(
        hasSqlState(error, "23502")
    );
}
```

`23502` là PostgreSQL `not_null_violation`.

### 17.1. Vì sao native SQL ở đây hợp lý?

Nó cố ý đi **qua database** mà không qua entity Bean Validation/constructor guard. Đây là test ràng buộc thật.

### 17.2. Không dùng native SQL để bypass validation trong production

Test cần cô lập các tầng. Production code thông thường vẫn nên có input/domain validation trước khi INSERT.

### 17.3. Check NULL khác blank

`NOT NULL` chặn SQL NULL, nhưng không tự chặn:

```text
""
" "
"   "
```

`@NotBlank` có thể chặn chuỗi rỗng/toàn whitespace ở Bean Validation. Nếu database cũng cần chặn, phải có CHECK phù hợp và test riêng.

---

## 18. Test FOREIGN KEY

Tạo một invoice hợp lệ, rồi cố gán `customer_id` không có row tương ứng bằng native SQL:

```java
@Test
void databaseRejectsUnknownCustomerReference() {
    Long customerId = createCustomer("Original Customer");

    Long invoiceId = createInvoice(
        301L,
        "INV-" + UUID.randomUUID(),
        customerId,
        new BigDecimal("15.00"),
        LocalDate.of(2026, 8, 1),
        Instant.parse("2026-08-01T00:00:00Z")
    );

    RuntimeException error = assertThrows(
        RuntimeException.class,
        () -> tx(em -> {
            em.createNativeQuery(
                """
                UPDATE invoices
                SET customer_id = ?
                WHERE id = ?
                """
            )
            .setParameter(1, -999999999L)
            .setParameter(2, invoiceId)
            .executeUpdate();

            return null;
        })
    );

    assertTrue(hasSqlState(error, "23503"));
}
```

`23503` là PostgreSQL `foreign_key_violation`.

### 18.1. Vì sao dùng native UPDATE?

Nếu dùng `em.getReference(Customer.class, missingId)`, provider có thể ném `EntityNotFoundException` trong một số đường truy cập trước khi DB nhận FK value. Native SQL cô lập việc **database có thực thi FK constraint** hay không.

### 18.2. Cần xác minh dữ liệu cũ vẫn còn

Sau failed UPDATE/rollback, fresh EM phải đọc được invoice vẫn có `customerId` ban đầu.

### 18.3. FK không đồng nghĩa authorization

Ngay cả FK đúng, một Customer thuộc tenant khác có thể tồn tại. Dữ liệu liên tenant cần domain authorization hoặc composite FK/RLS tương ứng.

---

## 19. Test CHECK constraint

Ví dụ một hóa đơn hợp lệ có `totalAmount=10.00`, sau đó SQL cố cập nhật âm:

```java
@Test
void databaseRejectsNegativeAmount() {
    Long customerId = createCustomer("Check Customer");

    Long invoiceId = createInvoice(
        401L,
        "INV-" + UUID.randomUUID(),
        customerId,
        new BigDecimal("10.00"),
        LocalDate.of(2026, 9, 1),
        Instant.parse("2026-09-01T00:00:00Z")
    );

    RuntimeException error = assertThrows(
        RuntimeException.class,
        () -> tx(em -> {
            em.createNativeQuery(
                """
                UPDATE invoices
                SET total_amount = -1
                WHERE id = ?
                """
            )
            .setParameter(1, invoiceId)
            .executeUpdate();

            return null;
        })
    );

    assertTrue(hasSqlState(error, "23514"));

    BigDecimal persisted = readFresh(em ->
        em.find(Invoice.class, invoiceId).getTotalAmount()
    );

    assertEquals(
        0,
        new BigDecimal("10.00").compareTo(persisted)
    );
}
```

`23514` là PostgreSQL `check_violation`.

### 19.1. Dùng CHECK trên DB không thay @DecimalMin

Hai lớp bảo vệ bổ sung nhau. Một native SQL path không đi qua entity Bean Validation vẫn phải bị DB từ chối.

### 19.2. Test rollback state

Assertion cuối cho thấy UPDATE âm không được commit; giá trị cũ vẫn còn.

### 19.3. Không quy mọi integrity error thành UNIQUE

Cùng một Spring exception wrapper có thể bọc CHECK, UNIQUE hoặc FK. Kiểm thử phải phân biệt theo SQLSTATE/constraint.

---

## 20. Test CHECK cho trạng thái enum

Native SQL có thể bỏ qua `@Enumerated(EnumType.STRING)`:

```java
RuntimeException error = assertThrows(
    RuntimeException.class,
    () -> tx(em -> {
        em.createNativeQuery(
            """
            UPDATE invoices
            SET status = 'NOT_A_REAL_STATE'
            WHERE id = ?
            """
        )
        .setParameter(1, invoiceId)
        .executeUpdate();

        return null;
    })
);

assertTrue(hasSqlState(error, "23514"));
```

Nếu DB không có CHECK tương ứng, native writer có thể lưu giá trị không được Java enum hỗ trợ, dẫn đến lỗi khi Hibernate materialize entity sau này.

### 20.1. Khi thêm enum constant

Test migration phải bảo đảm Java version và database CHECK cùng chấp nhận tập trạng thái được hỗ trợ, đặc biệt khi triển khai rolling upgrade.

### 20.2. Không dựa riêng vào Hibernate schema validation

Schema validation không nhất thiết phát hiện mọi khác biệt CHECK/index/privileges. Integration test trực tiếp là bằng chứng hữu ích hơn cho invariant cụ thể.

---

## 21. Helper đọc SQLSTATE

Một helper đơn giản:

```java
private static boolean hasSqlState(
        Throwable throwable,
        String expectedState) {

    for (Throwable current = throwable;
            current != null;
            current = current.getCause()) {

        if (current instanceof java.sql.SQLException sql) {
            if (expectedState.equals(sql.getSQLState())) {
                return true;
            }

            for (java.sql.SQLException next =
                    sql.getNextException();
                    next != null;
                    next = next.getNextException()) {

                if (expectedState.equals(
                        next.getSQLState())) {
                    return true;
                }
            }
        }
    }

    return false;
}
```

### 21.1. Giới hạn của helper minh họa

Một số JDBC batches có nhiều nested/linked SQLExceptions; production classifier có thể cần duyệt cả cause và `getNextException()` với bảo vệ vòng lặp. Ở đây test các tình huống đơn giản.

### 21.2. SQLSTATE có thể khác DB vendor

| PostgreSQL SQLSTATE | Ý nghĩa |
| --- | --- |
| `23505` | unique violation |
| `23503` | foreign key violation |
| `23502` | NOT NULL violation |
| `23514` | CHECK violation |
| `22003` | numeric value out of range |
| `22008` | datetime field overflow |
| `22007` | invalid datetime format |

Các mã chỉ là ví dụ PostgreSQL. Một driver/provider khác có thể bọc exception khác hoặc trả vendor error code cụ thể.

### 21.3. Đọc root cause, không parse message

Thông điệp raw SQL error có thể khác theo DB version/locale và đôi khi chứa dữ liệu nhạy cảm. Dùng SQLSTATE/constraint name khi có để phân loại.

---

# Phần V — Kiểm thử NULL

## 22. SQL NULL có nghĩa gì?

SQL NULL thường biểu diễn **unknown/missing/not applicable**, không giống số 0 hay chuỗi rỗng.

Ví dụ `Invoice.paidAt == null` có thể mang nghĩa hóa đơn chưa thanh toán.

Một số giá trị cần phân biệt:

| Giá trị | Ý nghĩa có thể có |
| --- | --- |
| `null` | Chưa có dữ liệu hoặc không áp dụng |
| `""` | Chuỗi có độ dài 0 |
| `" "` | Chuỗi chứa khoảng trắng |
| `BigDecimal.ZERO` | Giá trị số 0 thật |
| `LocalDate.of(1970,1,1)` | Một ngày thực, không phải NULL |
| `Instant.EPOCH` | Thời điểm 1970-01-01T00:00:00Z, không phải missing |
| `false` | Boolean false, khác unknown |

Không tự thay NULL bằng sentinel value nếu domain chưa định nghĩa rõ.

---

## 23. SQL three-valued logic

Trong SQL, biểu thức so sánh với NULL thường cho kết quả `UNKNOWN`, không phải `TRUE` hoặc `FALSE` theo Boolean hai giá trị thông thường.

Ví dụ:

```sql
WHERE paid_at = NULL
```

không chọn các rows `paid_at IS NULL`.

Cách đúng:

```sql
WHERE paid_at IS NULL
```

JPQL tương ứng:

```java
List<Invoice> unpaid = em.createQuery(
    """
    SELECT i
    FROM Invoice i
    WHERE i.paidAt IS NULL
    """,
    Invoice.class
)
.getResultList();
```

### 23.1. Query `= :value` với null không đồng nghĩa IS NULL

```java
query.setParameter("paidAt", null);
```

không biến biểu thức `i.paidAt = :paidAt` thành `IS NULL` một cách portable.

### 23.2. `IS NOT NULL`

```jpql
WHERE i.paidAt IS NOT NULL
```

phù hợp để tìm hóa đơn có thời điểm thanh toán.

### 23.3. SQL `NOT (x = NULL)` cũng không đúng

Vì `x = NULL` là `UNKNOWN`, phủ định của UNKNOWN vẫn UNKNOWN. Không sử dụng `<> NULL` hoặc `NOT = NULL` thay `IS NOT NULL`.

---

## 24. Test nullable field roundtrip

```java
@Test
void nullablePaidAtRemainsNullAfterCommit() {
    Long customerId = createCustomer("Null Customer");

    Long invoiceId = createInvoice(
        501L,
        "INV-" + UUID.randomUUID(),
        customerId,
        new BigDecimal("0.00"),
        LocalDate.of(2026, 10, 1),
        Instant.parse("2026-10-01T00:00:00Z")
    );

    Invoice saved = readFresh(
        em -> em.find(Invoice.class, invoiceId)
    );

    assertNull(saved.getPaidAt());
    assertNull(saved.getExternalRef());
}
```

### 24.1. Vì sao check sau commit?

Entity constructor có thể tự mặc định null. Test cần chứng minh **database chấp nhận NULL** và provider đọc lại đúng.

### 24.2. Không dùng một entity reference cũ

Sau transaction kết thúc, `Invoice` từ context cũ có thể detached. Nếu chỉ assert `invoice.getPaidAt()==null` ngay sau constructor, chưa test mapping.

### 24.3. NULL vẫn có thể không phải business hợp lệ

`paidAt=null` hợp lệ khi `status=DRAFT`, nhưng có thể không hợp lệ khi `status=PAID`. Nếu cần invariant chéo trường, có thể dùng domain validation và CHECK:

```sql
CHECK (
    status <> 'PAID'
    OR paid_at IS NOT NULL
)
```

Khi thêm constraint, cần migration và test cả trạng thái hợp lệ/không hợp lệ.

---

## 25. Test query IS NULL

```java
@Test
void queryIsNullFindsUnpaidInvoice() {
    Long customerId = createCustomer("Query Null");

    Long tenantId = 601L;
    String number = "INV-" + UUID.randomUUID();

    createInvoice(
        tenantId,
        number,
        customerId,
        new BigDecimal("42.00"),
        LocalDate.of(2026, 10, 5),
        Instant.parse("2026-10-05T00:00:00Z")
    );

    List<Invoice> results = readFresh(em ->
        em.createQuery(
            """
            SELECT i
            FROM Invoice i
            WHERE i.tenantId = :tenantId
              AND i.invoiceNumber = :number
              AND i.paidAt IS NULL
            """,
            Invoice.class
        )
        .setParameter("tenantId", tenantId)
        .setParameter("number", number)
        .getResultList()
    );

    assertEquals(1, results.size());
}
```

Trong repository production, tenant ID phải lấy từ authenticated context đã xác minh chứ không tin raw request.

### 25.1. Test `IS NOT NULL` đối lập

Tạo một invoice đã `issue()`/`markPaid(when)` trong transaction mới, commit, rồi xác nhận query `IS NOT NULL` tìm được invoice đã thanh toán.

### 25.2. Query trả entity sau EM close

Ví dụ `readFresh` trả `List<Invoice>` đã detached. Các scalar fields cơ bản đang loaded thường dùng được, nhưng không truy cập lazy association `getCustomer().getFullName()` sau EM close nếu chưa được tải; test NULL không nên phụ thuộc lazy loading ngoài transaction.

---

## 26. UNIQUE và NULL: database-specific semantics

Trong PostgreSQL, một unique index thông thường như:

```sql
CREATE UNIQUE INDEX uk_invoices_tenant_external_ref
    ON invoices(tenant_id, external_ref);
```

cho phép nhiều rows có `external_ref IS NULL` (theo mặc định), dù `tenant_id` giống nhau.

### 26.1. Hai NULL không bị coi là một duplicate mặc định

```text
tenant_id | external_ref
----------+-------------
601       | NULL
601       | NULL
```

có thể hợp lệ với PostgreSQL unique index thông thường.

### 26.2. Non-null values vẫn unique

```text
tenant_id | external_ref
----------+-------------
601       | EXT-001
601       | EXT-001  <- bị từ chối
```

### 26.3. PostgreSQL có lựa chọn `NULLS NOT DISTINCT`

Trong các phiên bản PostgreSQL có hỗ trợ, unique constraint/index có thể được cấu hình để xem NULL là không phân biệt nhằm áp uniqueness semantics khác.

Không giả định Oracle, MySQL, SQL Server và PostgreSQL có cùng xử lý nullable unique keys.

### 26.4. Test cả NULL và non-NULL

Một test đúng cần xác nhận:

1. Hai invoices cùng tenant, externalRef null → **được phép** theo schema hiện tại.
2. Hai invoices cùng tenant, externalRef `"EXT-001"` → **bị từ chối**.
3. Hai tenants khác nhau, cùng externalRef non-null → được phép nếu unique scope gồm tenant.

### 26.5. Một unique column nullable có thể sai domain

Nếu business yêu cầu external reference luôn unique kể cả “chưa có”, cần định nghĩa rõ có thực sự cho nhiều NULL không. Đừng đợi production mới biết database có cách hiểu khác application.

---

## 27. NULL, COALESCE và aggregate

Một số truy vấn dùng:

```jpql
SELECT COALESCE(i.externalRef, 'UNKNOWN')
FROM Invoice i
```

`COALESCE` thay NULL bằng một giá trị trong kết quả, nhưng **không sửa dữ liệu lưu ở database**.

### 27.1. COUNT khác nhau

SQL:

```sql
COUNT(*)
```

đếm rows.

```sql
COUNT(paid_at)
```

chỉ đếm các rows `paid_at` không NULL.

JPQL aggregate semantics tương ứng cần được test nếu báo cáo sử dụng nullable columns.

### 27.2. SUM và NULL

`SUM` của các giá trị có thể bỏ qua NULL, còn khi không có rows phù hợp, aggregate có thể trả NULL tùy hàm/semantics. Không mặc định mọi aggregate trả `BigDecimal.ZERO`.

### 27.3. Sort NULLS

Cách NULL được sắp trong `ORDER BY` có thể phụ thuộc database và sort direction; nếu API yêu cầu vị trí NULL cụ thể, hãy test dialect hoặc dùng biểu thức có semantics rõ.

---

# Phần VI — Số thập phân và precision/scale

## 28. Vì sao không dùng double cho tiền?

Java `double` dùng binary floating-point. Nhiều số thập phân như 0.1 không có biểu diễn nhị phân chính xác tuyệt đối.

Sai cho domain tiền:

```java
double amount = 0.1 + 0.2;
```

Tổng có thể không bằng literal `0.3` theo binary floating-point.

Dùng:

```java
BigDecimal amount =
    new BigDecimal("0.30");
```

### 28.1. Không dùng `new BigDecimal(0.1)`

```java
new BigDecimal(0.1)
```

chuyển giá trị `double` đã xấp xỉ sang decimal representation, có thể mang nhiều chữ số ngoài ý muốn.

Ưu tiên:

```java
new BigDecimal("0.1");
BigDecimal.valueOf(0.1);
```

`valueOf(double)` dùng chuỗi decimal theo `Double.toString`, nhưng tốt hơn vẫn nhận tiền từ request như một chuỗi decimal/DTO mapping có kiểm soát thay vì round-trip qua double.

---

## 29. Precision và scale là gì?

Với `NUMERIC(14,2)`:

- **Precision = 14**: tối đa 14 chữ số có nghĩa theo giới hạn kiểu dữ liệu.
- **Scale = 2**: hai chữ số sau dấu thập phân trong stored representation.
- Số chữ số phần nguyên tối đa thông thường: `14 - 2 = 12`.

Giá trị lớn nhất dương có thể biểu diễn theo scale này là:

```text
999999999999.99
```

Một giá trị:

```text
1000000000000.00
```

có 13 chữ số phần nguyên, vượt giới hạn và có thể bị DB từ chối.

### 29.1. Không tự tính precision bằng độ dài String tùy tiện

Dấu âm, leading zeros, scientific notation, trailing zeros và `BigDecimal` scale làm string length không tương đương precision/scale business logic.

### 29.2. Đọc thông số `BigDecimal`

```java
BigDecimal value = new BigDecimal("123.4500");

int precision = value.precision(); // 7
int scale = value.scale();         // 4
```

Giá trị có thể được biểu diễn tương đương về mặt số học với `123.45` nhưng scale của object ban đầu là 4.

### 29.3. Dữ liệu có scale khác vẫn có giá trị số học bằng nhau

```java
new BigDecimal("1.0")
    .compareTo(new BigDecimal("1.00")) == 0
```

nhưng:

```java
new BigDecimal("1.0")
    .equals(new BigDecimal("1.00"))
```

trả `false` vì `BigDecimal.equals` tính cả scale.

---

## 30. Test BigDecimal roundtrip đúng cách

```java
@Test
void decimalRoundtripPreservesCentValue() {
    Long customerId = createCustomer("Decimal Customer");

    BigDecimal expected =
        new BigDecimal("123456.78");

    Long invoiceId = createInvoice(
        701L,
        "INV-" + UUID.randomUUID(),
        customerId,
        expected,
        LocalDate.of(2026, 1, 15),
        Instant.parse("2026-01-15T00:00:00Z")
    );

    BigDecimal actual = readFresh(
        em -> em.find(Invoice.class, invoiceId)
                .getTotalAmount()
    );

    assertEquals(0, expected.compareTo(actual));
}
```

### 30.1. Tại sao dùng compareTo?

Test đang xác nhận **giá trị số học**. `BigDecimal.equals` có thể fail khi database hoặc converter chuẩn hóa scale về 2 dù giá trị số không đổi.

### 30.2. Khi nào cần assert scale?

Nếu API/database contract bắt buộc representation có `scale=2`, có thể thêm:

```java
assertEquals(2, actual.scale());
```

Nhưng đó là assertion **cụ thể theo mapping/driver/database**, không phải quy luật mọi JPA provider sẽ trả cùng scale cho mọi kiểu numeric.

### 30.3. Test số 0

`0`, `0.0` và `0.00` bằng nhau theo `compareTo`, khác nhau theo `equals`. Quyết định contract cần cả numeric equality và canonical representation hay không.

---

## 31. Rounding khác rejecting invalid scale

Với PostgreSQL:

```sql
SELECT CAST(1.235 AS NUMERIC(14,2));
```

có thể trả giá trị đã được làm tròn về hai chữ số thập phân.

Nếu ứng dụng yêu cầu **không bao giờ tự làm tròn**, DB numeric column một mình chưa đủ.

### 31.1. Test kỳ vọng làm tròn có chủ ý

Một hệ thống tính giá có thể cho phép:

```java
BigDecimal normalized =
    input.setScale(
        2,
        RoundingMode.HALF_UP
    );
```

Khi đó test:

```java
assertEquals(
    new BigDecimal("1.24"),
    new BigDecimal("1.235")
        .setScale(2, RoundingMode.HALF_UP)
);
```

Rounding mode phải được chọn theo nghiệp vụ, currency, thuế và pháp lý áp dụng. `HALF_UP` chỉ là ví dụ, không phải chuẩn cho mọi loại tiền.

### 31.2. Test kỳ vọng từ chối mọi rounding

```java
private static BigDecimal requireExactCents(
        BigDecimal input) {

    if (input == null) {
        throw new IllegalArgumentException(
            "Amount is required"
        );
    }

    return input.setScale(
        2,
        RoundingMode.UNNECESSARY
    );
}
```

Ví dụ:

```java
assertEquals(
    new BigDecimal("12.34"),
    requireExactCents(
        new BigDecimal("12.340")
    )
);
```

Chuỗi `"12.340"` có một chữ số 0 thừa nhưng không cần rounding để thành `12.34`.

```java
assertThrows(
    ArithmeticException.class,
    () -> requireExactCents(
        new BigDecimal("12.345")
    )
);
```

### 31.3. `@Digits` và `RoundingMode.UNNECESSARY` kiểm tra khác nhau

`@Digits(integer=12,fraction=2)` kiểm tra số chữ số theo Bean Validation; một object `12.340` có fractional digits nhiều hơn 2 có thể bị đánh giá khác với yêu cầu **giá trị biểu diễn chính xác đến cent**.

Nếu domain muốn cho phép trailing zeros, dùng `setScale(2, UNNECESSARY)` là một cách biểu đạt chính sách đó. Nếu muốn cấm mọi input có scale > 2, cần check trực tiếp theo contract.

### 31.4. Không viết test DB “phải từ chối 1.235” nếu DB đang round

Một bài test có assertion sai sẽ khiến người đọc nhầm DB behavior với validation rule. Tách test input validation, normalization và DB stored roundtrip.

---

## 32. Test vượt precision/range

Với `NUMERIC(14,2)`, một giá trị quá lớn như:

```text
1000000000000.00
```

không vừa 12 chữ số phần nguyên.

Để test **database numeric limit**, dùng native SQL trên một invoice hợp lệ, tránh Bean Validation chặn trước:

```java
RuntimeException error = assertThrows(
    RuntimeException.class,
    () -> tx(em -> {
        em.createNativeQuery(
            """
            UPDATE invoices
            SET total_amount =
                CAST('1000000000000.00' AS NUMERIC)
            WHERE id = ?
            """
        )
        .setParameter(1, invoiceId)
        .executeUpdate();

        return null;
    })
);

assertTrue(hasSqlState(error, "22003"));
```

Đây là PostgreSQL-specific test; cần bảo đảm row `invoiceId` hợp lệ và được tạo/commit trước.

### 32.1. Vì sao CAST trong ví dụ?

Để rõ rằng đây là numeric literal được DB xử lý, không phải string được ghép từ input người dùng. Production code vẫn phải bind values.

### 32.2. Test giới hạn dương và âm

Một test tốt xác nhận:

- `0.00` hợp lệ.
- `999999999999.99` hợp lệ nếu domain cho phép.
- Giá trị vượt range bị từ chối.
- Giá trị âm bị CHECK/domain validation từ chối.

### 32.3. Overflow có thể xuất hiện ở nhiều tầng

Java `BigDecimal` có precision rất lớn; lỗi chỉ có thể lộ khi mapping/driver/database chuyển sang cột hữu hạn. Nếu dùng DTO convert qua `double`, dữ liệu còn có thể mất chính xác trước khi tới DB.

---

## 33. Tính toán BigDecimal và MathContext

Không phải mọi phép tính decimal đều có kết quả hữu hạn với scale mong muốn.

Ví dụ:

```java
BigDecimal unit =
    new BigDecimal("10.00");

BigDecimal quantity =
    new BigDecimal("3");

BigDecimal total = unit.multiply(quantity);
```

Kết quả là một BigDecimal exact theo phép nhân decimal.

Nhưng:

```java
BigDecimal ratio =
    BigDecimal.ONE.divide(
        new BigDecimal("3")
    );
```

có thể ném `ArithmeticException` nếu không chỉ định rounding/MathContext, vì 1/3 có decimal expansion vô hạn.

### 33.1. Chọn rounding rõ

```java
BigDecimal ratio =
    BigDecimal.ONE.divide(
        new BigDecimal("3"),
        6,
        RoundingMode.HALF_EVEN
    );
```

Không biến rounding mode ở Java thành implicit database rounding mà không kiểm thử.

### 33.2. Nhiều loại tiền có số chữ số thập phân khác nhau

`NUMERIC(14,2)` phù hợp với một số domain nhưng không phải mọi currencies, cryptoassets, exchange rates, quantities. Không hard-code hai chữ số cho mọi nghiệp vụ tài chính.

### 33.3. Test phép tính trước khi lưu

Tách:

1. Unit test phép tính `BigDecimal`.
2. Test normalization/validation.
3. Integration test lưu/đọc DB.
4. Test báo cáo SUM/AVG và type conversion.

---

## 34. SUM, AVG và kiểu trả về

JPQL có aggregate:

```java
BigDecimal total = em.createQuery(
    """
    SELECT SUM(i.totalAmount)
    FROM Invoice i
    WHERE i.tenantId = :tenant
    """,
    BigDecimal.class
)
.setParameter("tenant", tenantId)
.getSingleResult();
```

Với BigDecimal fields, aggregate có semantics numeric phù hợp, nhưng test cần xem:

- Không có rows → SUM có thể trả `null`, không phải 0.
- Rounding của AVG có thể không giống rounding của tổng.
- Native SQL driver scalar type có thể là `BigDecimal` hoặc kiểu khác theo mapping.
- Total overflow limits tùy DB expression type.

### 34.1. Tránh `doubleValue()` trong assert money

Nếu test chuyển `BigDecimal` thành double rồi assert equality, nó có thể che hoặc tạo sai số không mong muốn.

### 34.2. Test aggregation bằng fixtures độc lập

Ví dụ `10.10 + 20.20 = 30.30`; so sánh với `BigDecimal("30.30")` bằng `compareTo`.

---

# Phần VII — Thời gian và múi giờ

## 35. Phân biệt bốn kiểu java.time

| Java type | Biểu diễn | Dùng cho |
| --- | --- | --- |
| `LocalDate` | Ngày lịch không timezone | Ngày phát hành, ngày sinh, kỳ hóa đơn |
| `LocalTime` | Giờ trong ngày không ngày/timezone | Giờ mở cửa theo địa phương |
| `LocalDateTime` | Ngày + giờ không offset/timezone | Lịch hẹn theo giờ địa phương khi có zone riêng |
| `Instant` | Điểm trên trục thời gian UTC | Event/audit createdAt, paidAt |
| `OffsetDateTime` | Ngày giờ + UTC offset | Timestamp có offset trong API |
| `ZonedDateTime` | Ngày giờ + `ZoneId` và rules | Lịch địa phương chịu DST |

Mỗi type có ý nghĩa riêng. Việc có thể “convert về timestamp” không biến chúng thành hoán đổi được.

### 35.1. LocalDate không phải một Instant

`2026-10-01` là ngày lịch, không chỉ định bắt đầu/kết thúc lúc nào trên trục UTC nếu chưa chọn timezone.

### 35.2. LocalDateTime không chứa timezone

```java
LocalDateTime.of(2026, 11, 1, 1, 30);
```

không cho biết đây là 01:30 ở đâu, hay lần 01:30 thứ nhất/thứ hai trong ngày có DST overlap.

### 35.3. Instant biểu diễn thời điểm rõ

```java
Instant.parse("2026-11-01T06:30:00Z")
```

là một thời điểm cụ thể, không phụ thuộc timezone của máy hiển thị.

---

## 36. Mapping kiểu SQL

Trong bài:

```java
@Column(name = "issue_date")
private LocalDate issueDate;
```

tương ứng PostgreSQL:

```sql
issue_date DATE NOT NULL
```

Và:

```java
@Column(name = "created_at")
private Instant createdAt;
```

tương ứng:

```sql
created_at TIMESTAMPTZ NOT NULL
```

### 36.1. TIMESTAMP WITHOUT TIME ZONE khác TIMESTAMPTZ

PostgreSQL:

- `TIMESTAMP WITHOUT TIME ZONE`: local date/time fields, không tự gắn một instant duy nhất.
- `TIMESTAMPTZ`: lưu thời điểm với timezone interpretation; thường được chuẩn hóa nội bộ, khi hiển thị có thể phụ thuộc session timezone.

`TIMESTAMPTZ` **không lưu nguyên tên timezone** như `"America/New_York"`. Khi chỉ lưu `Instant`, nếu cần biết timezone của user để hiển thị, phải lưu/biết `ZoneId` ở cấp application/domain.

### 36.2. OffsetDateTime không luôn round-trip offset gốc

Một value:

```text
2026-01-01T09:00:00+09:00
```

và:

```text
2026-01-01T00:00:00Z
```

biểu diễn cùng một instant. PostgreSQL `TIMESTAMPTZ` có thể đọc lại với offset khác mà vẫn đúng thời điểm.

Không viết test kỳ vọng offset/string representation y hệt nếu database không có contract lưu offset ban đầu.

### 36.3. Không tự gắn @Temporal cho java.time

`@Temporal` được dùng cho một số legacy `java.util.Date`/`Calendar` mappings theo Jakarta Persistence, không phải cách cấu hình mặc định cho `LocalDate`, `LocalDateTime`, `Instant`.

---

## 37. Test LocalDate roundtrip

```java
@Test
void dateRoundtripPreservesCalendarDate() {
    Long customerId = createCustomer("Date Customer");

    LocalDate expected =
        LocalDate.of(2026, 2, 28);

    Long invoiceId = createInvoice(
        801L,
        "INV-" + UUID.randomUUID(),
        customerId,
        new BigDecimal("15.00"),
        expected,
        Instant.parse("2026-02-28T12:00:00Z")
    );

    LocalDate actual = readFresh(
        em -> em.find(Invoice.class, invoiceId)
                .getIssueDate()
    );

    assertEquals(expected, actual);
}
```

### 37.1. Test ngày nhuận

Thêm:

```java
LocalDate.of(2024, 2, 29);
```

là ngày hợp lệ.

`LocalDate.of(2025,2,29)` ném Java `DateTimeException` trước SQL, nên test đó là Java input validation chứ không chứng minh DB DATE constraint.

### 37.2. Không chuyển LocalDate qua Instant tùy tiện

Nếu `issueDate` chỉ là ngày hóa đơn, việc đặt `Instant` lúc midnight UTC có thể khiến người dùng ở timezone phía Tây nhìn thấy ngày hôm trước.

### 37.3. Date boundary thuộc domain contract

Ngày hóa đơn theo timezone nào? Ngày hệ thống, ngày cửa hàng hay ngày người dùng? Test phải dùng chính sách đó, không dựa vào default timezone của máy chạy tests.

---

## 38. Test Instant roundtrip với độ chính xác phù hợp

Java `Instant` hỗ trợ nanosecond precision. Nhiều cơ sở dữ liệu và JDBC mapping lưu timestamp ở độ chính xác thấp hơn, ví dụ PostgreSQL phổ biến ở microsecond.

Ví dụ chọn value có đúng sáu chữ số phần microsecond:

```java
Instant expected =
    Instant.parse("2026-04-01T10:11:12.123456Z");
```

Integration test:

```java
@Test
void instantRoundtripPreservesMicrosecondValue() {
    Long customerId = createCustomer("Clock Customer");

    Instant expected =
        Instant.parse(
            "2026-04-01T10:11:12.123456Z"
        );

    Long invoiceId = createInvoice(
        901L,
        "INV-" + UUID.randomUUID(),
        customerId,
        new BigDecimal("25.00"),
        LocalDate.of(2026, 4, 1),
        expected
    );

    Instant actual = readFresh(
        em -> em.find(Invoice.class, invoiceId)
                .getCreatedAt()
    );

    assertEquals(expected, actual);
}
```

**Đây là test phụ thuộc PostgreSQL/provider/driver mapping đã cấu hình**, không phải lời hứa JPA mọi database giữ microsecond chính xác. Nếu mapping đang ép kiểu khác, test cần khai báo kỳ vọng tương ứng.

### 38.1. Test nanoseconds ngoài độ chính xác DB

```java
Instant input =
    Instant.parse("2026-04-01T10:11:12.123456789Z");
```

Không nên mặc định:

```java
assertEquals(input, loaded);
```

sẽ đúng với DB lưu microsecond.

Cần quyết định hợp đồng:

- **Normalize** trước khi ghi, ví dụ truncate về microseconds.
- **Round** theo chính sách có chủ đích.
- **Chấp nhận sai lệch trong giới hạn** khi đọc lại.
- Hoặc dùng storage representation có thể giữ toàn bộ nanoseconds nếu nghiệp vụ cần.

### 38.2. Truncation và rounding không giống nhau

```java
Instant normalized =
    input.truncatedTo(ChronoUnit.MICROS);
```

là **cắt** phần nano sau microsecond, không phải rounding. Database/provider có thể dùng cơ chế rounding khác. Test cần theo chính sách được thiết kế, không tự đoán.

### 38.3. Không so sánh formatted strings để kết luận instant

Hai timestamps có offset/text khác nhau vẫn có thể biểu diễn cùng instant. Ưu tiên so sánh `Instant` hoặc normalized epoch value.

---

## 39. Chuyển một ngày địa phương thành khoảng Instant

Giả sử UI yêu cầu: “Tìm hóa đơn được tạo trong ngày 2026-11-01 ở New York”.

Không viết:

```java
LocalDate day = LocalDate.of(2026, 11, 1);

Instant from =
    day.atStartOfDay(ZoneOffset.UTC)
       .toInstant();
```

nếu nghiệp vụ yêu cầu **ngày theo múi giờ New York**, không phải UTC.

Cách đúng:

```java
LocalDate day =
    LocalDate.of(2026, 11, 1);

ZoneId zone =
    ZoneId.of("America/New_York");

Instant from =
    day.atStartOfDay(zone).toInstant();

Instant toExclusive =
    day.plusDays(1)
       .atStartOfDay(zone)
       .toInstant();
```

Sau đó:

```java
List<Invoice> invoices = em.createQuery(
    """
    SELECT i
    FROM Invoice i
    WHERE i.tenantId = :tenant
      AND i.createdAt >= :fromTime
      AND i.createdAt < :toTime
    """,
    Invoice.class
)
.setParameter("tenant", tenantId)
.setParameter("fromTime", from)
.setParameter("toTime", toExclusive)
.getResultList();
```

### 39.1. Vì sao dùng `[from, to)`?

Khoảng half-open:

```text
from <= createdAt < to
```

tránh phải đoán “thời điểm cuối cùng trong ngày” theo độ chính xác seconds/millis/micros/nanos.

### 39.2. Không cộng 24 giờ một cách máy móc

Trong ngày chuyển DST, khoảng từ midnight ngày này đến midnight ngày sau ở một timezone có thể dài **23 hoặc 25 giờ**, không phải luôn 24 giờ.

Vì vậy:

```java
day.plusDays(1).atStartOfDay(zone)
```

thể hiện ngày lịch tiếp theo chính xác hơn:

```java
from.plus(1, ChronoUnit.DAYS)
```

khi mục tiêu là ngày địa phương.

### 39.3. Test DST ngày thu 2026

New York kết thúc daylight saving time vào ngày 2026-11-01 theo timezone rules hiện hành. Một test có thể xác nhận khoảng ngày địa phương đó dài 25 giờ:

```java
LocalDate day =
    LocalDate.of(2026, 11, 1);

ZoneId ny =
    ZoneId.of("America/New_York");

Instant start =
    day.atStartOfDay(ny).toInstant();

Instant end =
    day.plusDays(1).atStartOfDay(ny)
       .toInstant();

assertEquals(
    Duration.ofHours(25),
    Duration.between(start, end)
);
```

Test này phụ thuộc timezone database (tzdb) của JDK theo rules áp dụng. Với nghiệp vụ lịch lâu dài, cần xem thay đổi timezone rules do cơ quan quản lý địa phương.

---

## 40. DST gap và overlap

Một `LocalDateTime` địa phương có thể:

- **Hợp lệ duy nhất:** chỉ có một offset.
- **Không tồn tại:** đồng hồ nhảy qua một khoảng khi bắt đầu DST.
- **Mơ hồ:** đồng hồ lặp lại một khoảng khi kết thúc DST.

Ví dụ New York 2026:

```java
LocalDateTime gap =
    LocalDateTime.of(
        2026, 3, 8, 2, 30
    );
```

02:30 có thể nằm trong spring-forward gap.

Kiểm tra:

```java
ZoneId zone =
    ZoneId.of("America/New_York");

List<ZoneOffset> offsets =
    zone.getRules().getValidOffsets(gap);

assertEquals(0, offsets.size());
```

Một giờ overlap:

```java
LocalDateTime overlap =
    LocalDateTime.of(
        2026, 11, 1, 1, 30
    );
```

```java
List<ZoneOffset> offsets =
    zone.getRules().getValidOffsets(overlap);

assertEquals(2, offsets.size());
```

### 40.1. Không tự chuyển LocalDateTime sang Instant mà không có policy

Nếu một lịch hẹn bắt đầu lúc 01:30 trong ngày overlap, cần quyết định chọn offset sớm hay muộn, hoặc hỏi người dùng. Mặc định của một API có thể chọn một offset, nhưng bài test nghiệp vụ không nên dựa vào mặc định ngầm.

### 40.2. Lưu timezone nếu cần khôi phục lịch địa phương

Nếu cần biết người dùng đặt cuộc hẹn ở `America/New_York`, chỉ lưu Instant có thể không đủ để tái tạo ý định lịch khi timezone rules thay đổi. Có thể cần lưu `ZoneId` và local date/time tùy domain.

### 40.3. Không nhầm DST với lỗi ORM

Nếu đọc `LocalDateTime` thấy lệch hoặc một giờ lặp lại, nguyên nhân có thể thuộc conversion policy, timezone, session/JVM configuration hoặc DB type, không nhất thiết Hibernate query sai.

---

## 41. OffsetDateTime và cách kiểm thử

Ví dụ:

```java
OffsetDateTime input =
    OffsetDateTime.parse(
        "2026-01-01T09:00:00+09:00"
    );

Instant expected =
    input.toInstant();
```

Nếu lưu vào `TIMESTAMPTZ`, kiểm tra **instant** sau readback:

```java
assertEquals(
    expected,
    actualOffsetDateTime.toInstant()
);
```

Không luôn:

```java
assertEquals(input, actualOffsetDateTime);
```

bởi database/driver có thể trả offset khác.

### 41.1. Offset không phải timezone region

`+09:00` là offset, không nói timezone rules lâu dài như `Asia/Tokyo` hay một vùng lịch sử có DST.

### 41.2. JPA provider/version có thể map OffsetDateTime khác nhau

Có thể cần cấu hình kiểu cột, JDBC timezone hoặc provider extension. Bài test phải chạy trên stack thực và mô tả giá trị nào cần preserve.

---

## 42. Timezone của JVM, JDBC và database session

Một bug thường chỉ xuất hiện trong production:

```text
Developer machine: UTC+07
CI container: UTC
Database session: UTC
Application server: America/New_York
```

Nếu dùng `LocalDateTime` và một cột DB có timezone interpretation khác, việc chuyển đổi có thể dịch thời điểm.

### 42.1. Không đổi timezone toàn JVM trong tests chạy song song

```java
TimeZone.setDefault(...)
```

thay đổi global process state và có thể làm nhiễu tests khác, nhất là khi chạy parallel.

Để kiểm tra timezone matrix, ưu tiên:

- Chạy test suites ở JVM processes riêng với timezone configuration khác.
- Chọn `ZoneId` tường minh trong conversion code.
- Dùng database/session timezone config có kiểm soát.
- Giữ dữ liệu fixture có instant rõ ràng.

### 42.2. Hibernate JDBC timezone configuration là provider-specific

Một số Hibernate setups dùng property như:

```properties
hibernate.jdbc.time_zone=UTC
```

Hành vi cụ thể tùy Hibernate version, JDBC types và driver. Không xem property này là giải pháp vạn năng cho mọi `java.time` mapping hoặc như một phần chuẩn Jakarta Persistence.

### 42.3. `TIMESTAMPTZ` và session display timezone

PostgreSQL có thể hiển thị cùng instant khác string theo session timezone. Native SQL text output khác nhau không có nghĩa persisted instant sai.

So sánh bằng instant/epoch hoặc normalized Java temporal type.

---

## 43. Test khoảng thời gian và ranh giới

Giả sử khoảng:

```text
[2026-06-01T00:00:00Z,
 2026-06-02T00:00:00Z)
```

Tạo fixtures:

1. Một invoice trước `from` một microsecond.
2. Một invoice đúng `from`.
3. Một invoice ở giữa.
4. Một invoice đúng `toExclusive`.
5. Một invoice sau `toExclusive`.

Kỳ vọng:

- Đúng `from` → được chọn.
- Ở giữa → được chọn.
- Đúng `toExclusive` → không được chọn.
- Trước `from` → không được chọn.
- Sau `toExclusive` → không được chọn.

### 43.1. Tránh `BETWEEN` khi muốn half-open interval

JPQL `BETWEEN` thường bao gồm cả hai endpoints. Với audit/event time ranges, `>= from` và `< to` thường giảm overlap giữa các pagination/batch windows.

### 43.2. Query bind đúng type

```java
.setParameter("fromTime", from)
.setParameter("toTime", toExclusive)
```

`Instant` values cần được provider/driver mapping chính xác. Không ghép ISO date strings vào native SQL source.

### 43.3. Kiểm tra precision ở boundary

Nếu DB chỉ lưu microsecond, một input `...123456789` có thể được rounded/truncated làm biến đổi việc nằm bên trái/phải boundary. Normalize policy trước khi ghi và trước khi query theo contract.

---

## 44. Test giá trị thời gian NULL

`paidAt` có thể null. Kiểm tra:

1. Invoice mới `paidAt == null` sau commit.
2. JPQL `IS NULL` tìm được.
3. Sau `issue()` và `markPaid(Instant)`, commit rồi đọc lại, `paidAt` không null.
4. JPQL `IS NOT NULL` tìm được.
5. Không cho `markPaid(null)` theo domain validation.
6. Nếu DB `CHECK` đòi status PAID thì paid_at không null, test native SQL path.

### 44.1. NULL không bằng Instant.EPOCH

Không dùng:

```java
Instant.EPOCH
```

để biểu diễn “chưa thanh toán” khi schema đã cho phép NULL. Epoch là một thời điểm thực, có thể làm sai báo cáo và query.

### 44.2. Optional field đổi trạng thái

Một invoice được thanh toán có thể cần đặt `paidAt` và `status` trong cùng transaction, với invariant ở domain/DB. Test trạng thái sau commit, không chỉ gọi setter trong memory.

---

# Phần VIII — Transaction, Spring và xác minh trạng thái

## 45. `flush()` không phải `commit()`

Ví dụ:

```java
em.getTransaction().begin();

Invoice invoice = ...;
em.persist(invoice);
em.flush();

// Cột/constraint có thể được kiểm tra ở đây.
// Nhưng transaction chưa commit.

em.getTransaction().rollback();
```

Sau rollback, invoice row không phải committed data.

### 45.1. Dữ liệu Java object có thể không được undo

Ngay cả khi DB rollback, entity object có thể vẫn giữ generated ID hoặc các giá trị đã set.

Không dùng `invoice.getId() != null` làm bằng chứng row tồn tại trong database sau rollback.

### 45.2. Một số constraints có thể deferred

PostgreSQL hỗ trợ các constraints `DEFERRABLE` trong những trường hợp nhất định. Với constraint bị defer, `flush()` có thể thành công và lỗi chỉ xuất hiện ở `commit()`.

Bộ test cần bắt toàn transaction boundary để không bỏ lỡ deferred failure.

---

## 46. Spring @DataJpaTest thường rollback khi kết thúc

Ví dụ:

```java
@DataJpaTest
class InvoiceRepositoryTest {

    @Autowired
    TestEntityManager em;

    @Test
    void savesInvoice() {
        // Fixture tạo parent, invoice ...
        em.persistAndFlush(invoice);

        assertNotNull(invoice.getId());
    }
}
```

Test này hữu ích để kiểm tra ORM mapping trong một transaction, nhưng **không mặc định chứng minh dữ liệu đã committed** vì test transaction thường rollback.

### 46.1. Khi cần commit thực

Một cách là tắt outer test transaction cho test đó, dùng service/`TransactionTemplate` để thực thi và commit, rồi dùng transaction/context mới để verify.

Ví dụ cấu trúc:

```java
@Test
@Transactional(
    propagation = Propagation.NOT_SUPPORTED
)
void checksCommittedState() {
    Long id = transactionTemplate.execute(status -> {
        // create, persist and return ID
    });

    InvoiceDto actual =
        transactionTemplate.execute(status -> {
            // Load and map in another transaction
        });

    // Assert committed values.
}
```

Đây là skeleton: `InvoiceDto` và transactionTemplate cần được cấu hình trong test project. Nếu `TransactionTemplate` dùng propagation REQUIRED trong một outer transaction khác, các boundary có thể không tách như mong muốn.

### 46.2. `saveAndFlush` không đảm bảo commit

`saveAndFlush()` khiến pending changes được flush, không tự hoàn tất outer transaction. Test cần biết service/repository đang tham gia transaction nào.

### 46.3. Test DB constraints dưới runtime stack thật

Spring có thể dịch Hibernate constraint violation sang `DataIntegrityViolationException`. Một test mong `jakarta.persistence.PersistenceException` trên thuần JPA không nhất thiết nhận cùng lớp exception khi qua Spring Data repository.

Phân loại theo layer và cause chain phù hợp.

---

## 47. Cùng một test, hai mức assertion

**Mức application:**

```java
assertThrows(
    IllegalArgumentException.class,
    () -> requireExactCents(
        new BigDecimal("1.235")
    )
);
```

**Mức database:**

```java
assertTrue(
    hasSqlState(
        databaseError,
        "23514"
    )
);
```

Một lỗi validation trước persistence không chứng minh DB CHECK; một DB CHECK violation cũng không chứng minh API trả field validation message đúng.

### 47.1. Tách testcase theo nguồn lỗi

Để dễ điều tra, mỗi test nên nhắm đến một contract:

- Bean Validation.
- DB constraint.
- Numeric normalization.
- Temporal mapping.
- Query boundary.
- Transaction rollback.

Không cố dồn tất cả vào một test dài rồi chỉ assert final count.

### 47.2. Dữ liệu fixture cần tránh conflict chéo

Nếu test decimal invalid đồng thời dùng invoice number đã tồn tại, thất bại có thể do UNIQUE chứ không phải numeric scale. Mỗi test cần isolate đúng error source.

---

# Phần IX — Các sai lầm thường gặp

## 48. “Có @NotNull là database chắc chắn NOT NULL”

Sai. Bean Validation và JPA schema metadata không xác nhận migration production. Dùng native SQL test DB.

## 49. “@Column(nullable=false) khiến constructor tự ném lỗi”

Không. Annotation JPA là metadata; nếu cần validation lập tức ở constructor/domain service phải tự thực hiện.

## 50. “`BigDecimal` luôn lưu nguyên mọi chữ số”

Không. DB numeric column có precision/scale hữu hạn; provider/DB có thể round hoặc báo overflow theo rules tương ứng.

## 51. “NUMERIC(14,2) từ chối mọi số có ba chữ số thập phân”

Không đúng với PostgreSQL phổ biến: có thể round. Hãy test policy business và DB behavior riêng.

## 52. “BigDecimal equals là đúng cho mọi assert tiền”

`BigDecimal.equals` nhạy scale; `compareTo` xét giá trị số. Chọn assertion theo contract.

## 53. “0.1 dùng new BigDecimal(0.1) sẽ luôn chính xác decimal”

Sai. Constructor từ `double` có thể mang binary floating-point approximation. Dùng String hoặc `valueOf` khi phù hợp.

## 54. “NULL và empty string là một”

Không mặc định. PostgreSQL phân biệt; một số DB như Oracle có semantics đặc thù cho chuỗi rỗng và NULL. Test trên DB mục tiêu.

## 55. “WHERE x = NULL tìm các row null”

Sai. Dùng `IS NULL`; `= :param` với param null không tự tạo `IS NULL`.

## 56. “UNIQUE nghĩa là chỉ được một NULL”

Không phải quy luật portable. PostgreSQL default unique index thường cho phép nhiều NULL; có lựa chọn `NULLS NOT DISTINCT` ở versions phù hợp.

## 57. “FK đúng nghĩa là user được phép liên kết bất kỳ parent”

Sai. FK xác nhận reference tồn tại, không tự enforce tenant/ownership authorization.

## 58. “@Enumerated(STRING) bảo đảm DB CHECK cập nhật theo enum”

Sai. Migrations cần đồng bộ enum constants và CHECK values.

## 59. “LocalDate và Instant là hai cách lưu cùng ngày”

Sai. LocalDate là ngày lịch; Instant là thời điểm cụ thể trên trục UTC.

## 60. “TIMESTAMPTZ lưu nguyên timezone tên vùng”

Không. PostgreSQL TIMESTAMPTZ không lưu riêng `ZoneId` như `America/New_York`; cần lưu timezone context nếu domain yêu cầu.

## 61. “OffsetDateTime phải trả lại đúng offset ban đầu”

Không luôn; DB có thể preserve instant nhưng trả offset khác.

## 62. “Một ngày lịch luôn bằng 24 giờ”

Sai trong các timezone có DST transitions. Dùng start-of-day của ngày này và ngày sau theo cùng ZoneId.

## 63. “Instant luôn giữ nanoseconds sau DB roundtrip”

Không được bảo đảm với cột timestamp có độ chính xác thấp hơn. Test/normalize.

## 64. “Thay TimeZone default trong test song song là vô hại”

Sai. `TimeZone.setDefault()` thay global process state và có thể làm tests khác bị ảnh hưởng.

## 65. “persistAndFlush nghĩa là test đã commit”

Sai trong Spring transactional test; flush khác commit.

## 66. “Một RuntimeException là đủ chứng minh đúng constraint”

Không. Phải xác nhận SQLSTATE/constraint name và state DB sau rollback.

---

# Phần X — Bài tập và lời giải

## 67. Tình huống thực hành

### Bài 1. Customer tên null nhưng constructor đã từ chối

**Lời giải:** Đây là domain validation, chưa chứng minh DB NOT NULL. Dùng native SQL trong integration test và kiểm tra SQLSTATE 23502.

### Bài 2. Hai invoices trùng number trong một tenant

**Lời giải:** DB UNIQUE composite phải từ chối; assert 23505/constraint name và chỉ một committed row.

### Bài 3. Hai tenants trùng invoice number

**Lời giải:** Phải được cho phép nếu unique key là `(tenant_id, invoice_number)`. Test positive để phát hiện unique index đặt sai scope.

### Bài 4. Invoice tham chiếu customer không tồn tại

**Lời giải:** DB FK phải từ chối, thường SQLSTATE 23503 ở PostgreSQL. `getReference` có thể fail sớm ở provider; dùng native update để cô lập DB constraint.

### Bài 5. Tổng tiền âm

**Lời giải:** Bean Validation/domain và DB CHECK đều nên bảo vệ. Native SQL test DB trả 23514 theo PostgreSQL.

### Bài 6. Trạng thái Java enum thêm REFUNDED nhưng DB CHECK chưa đổi

**Lời giải:** Migration mismatch. Cần test update enum/constraint và rollout compatibility.

### Bài 7. Chuỗi rỗng với NOT NULL

**Lời giải:** NOT NULL không tự cấm `""`; dùng @NotBlank/domain rule hoặc CHECK tương ứng.

### Bài 8. `WHERE paidAt = NULL`

**Lời giải:** Sai SQL NULL semantics. Dùng `IS NULL`.

### Bài 9. Query param `:paidAt` được bind null

**Lời giải:** `i.paidAt = :paidAt` không portable để tìm NULL. Xây predicate `IS NULL` theo contract.

### Bài 10. Unique nullable external reference

**Lời giải:** PostgreSQL default cho phép nhiều NULL, nhưng duplicate non-null cùng tenant bị từ chối. Test đúng schema/DB version.

### Bài 11. COUNT(paid_at) ít hơn COUNT(*)

**Lời giải:** COUNT(column) bỏ NULL; COUNT(*) đếm mọi row. Không phải JPA mất dữ liệu.

### Bài 12. BigDecimal("1.0").equals(BigDecimal("1.00"))

**Lời giải:** False vì scale khác. `compareTo` bằng 0; chọn assertion đúng mục tiêu.

### Bài 13. Input 1.235 ghi NUMERIC(14,2)

**Lời giải:** DB có thể round. Nếu domain không cho rounding, validate trước SQL bằng `RoundingMode.UNNECESSARY` hoặc policy tương ứng.

### Bài 14. Input 12.340

**Lời giải:** Có thể normalize chính xác thành 12.34 bằng `setScale(2, UNNECESSARY)`; một rule kiểm tra scale ban đầu có thể xử lý khác, cần định nghĩa.

### Bài 15. Input 1000000000000.00

**Lời giải:** Vượt 12 chữ số phần nguyên của NUMERIC(14,2), PostgreSQL có thể trả SQLSTATE 22003.

### Bài 16. Tiền tính bằng double

**Lời giải:** Có sai số nhị phân. Dùng BigDecimal từ String/decimal representation, kiểm thử arithmetic và roundtrip.

### Bài 17. BigDecimal division 1/3

**Lời giải:** Chỉ định scale/MathContext/rounding policy; nếu không có thể ArithmeticException.

### Bài 18. SUM không có rows

**Lời giải:** Có thể trả NULL thay vì zero. Test query/DTO handling theo DB/JPA semantics.

### Bài 19. `LocalDate.of(2025,2,29)`

**Lời giải:** Java DateTimeException trước database. Muốn test DB invalid DATE phải dùng SQL path khác và phân loại lỗi tương ứng.

### Bài 20. Ngày phát hành bị lệch một ngày ở UTC−8

**Lời giải:** Có thể đã chuyển LocalDate qua midnight UTC thành Instant. Giữ `DATE`/LocalDate cho ngày lịch và định nghĩa timezone khi cần.

### Bài 21. Instant có 9 chữ số nano

**Lời giải:** PostgreSQL timestamp thường microsecond precision; normalize/compare theo hợp đồng, không mặc định exact nanos roundtrip.

### Bài 22. OffsetDateTime đọc lại ở +00:00 thay vì +09:00

**Lời giải:** Có thể vẫn cùng instant. So sánh `toInstant()`, lưu offset/ZoneId riêng nếu domain cần.

### Bài 23. New York ngày 2026-11-01

**Lời giải:** Ngày địa phương có thể dài 25 giờ do DST kết thúc. Dùng `day.atStartOfDay(zone)` và ngày kế tiếp, không thêm 24 giờ.

### Bài 24. LocalDateTime 02:30 lúc spring-forward

**Lời giải:** Có thể không tồn tại. Kiểm tra valid offsets và định nghĩa policy xử lý gap.

### Bài 25. LocalDateTime 01:30 lúc fall-back

**Lời giải:** Có thể mơ hồ hai offsets. Phải chọn offset theo business policy hoặc yêu cầu người dùng xác nhận.

### Bài 26. Query BETWEEN bao gồm endpoint cuối

**Lời giải:** Dùng half-open `[from,to)` khi muốn chia windows không trùng; `>= :from` và `< :to`.

### Bài 27. `TimeZone.setDefault` trong parallel tests

**Lời giải:** Có thể làm tests race vì global state. Dùng JVM processes riêng hoặc ZoneId tường minh.

### Bài 28. JPA entity trông đúng ngay sau flush

**Lời giải:** Chưa chứng minh commit/DB state; mở fresh EM sau commit để verify.

### Bài 29. `@DataJpaTest` pass nhưng production fail commit

**Lời giải:** Test method có thể rollback mặc định; cần test transaction boundary/commit đúng và chạy migration DB thật.

### Bài 30. `assertThrows(RuntimeException.class)` khi duplicate invoice

**Lời giải:** Chưa đủ. Kiểm tra PostgreSQL SQLSTATE 23505 và committed row count để tránh false positives.

### Bài 31. FK hợp lệ nhưng cross-tenant

**Lời giải:** FK chỉ chứng minh row tồn tại, không chứng minh authorization. Thêm tenant-aware policy/constraints và test.

### Bài 32. DTO amount null được đổi thành BigDecimal.ZERO

**Lời giải:** Có thể che dữ liệu thiếu. Domain phải phân biệt missing/null và giá trị số 0; test API mapping và JPA separately.

### Bài 33. Database session timezone khác JVM

**Lời giải:** Test temporal mapping, lựa chọn SQL type và instant conversion. Không chỉ so sánh timestamp text.

### Bài 34. `@Column(precision,scale)` trong Java nhưng schema production là FLOAT

**Lời giải:** Migration/schema mismatch, có thể mất chính xác. Test schema type và roundtrip với PostgreSQL database thực.

### Bài 35. Một test constraint không commit fixture trước

**Lời giải:** Có thể bị L1/outer transaction che. Tạo fixture transaction riêng, commit rồi test lỗi và verify bằng context mới.

---

## 68. Checklist hoàn thiện bài kiểm thử

### Ràng buộc

1. Có test DB NOT NULL bằng SQL path không bị Java validation chặn?
2. Có test Bean Validation độc lập?
3. Có kiểm tra UNIQUE cùng tenant và khác tenant?
4. Có kiểm tra FK với reference thực sự không tồn tại?
5. Có kiểm tra CHECK cho amount/status?
6. Có phân biệt constraint names/SQLSTATE?
7. Có kiểm tra data rollback bằng context mới?
8. Có dùng migration thật thay vì ORM auto-create?
9. Có test các constraints có thể deferred đến commit?
10. Có test raw native/bulk writers nếu hệ thống sử dụng?

### NULL

11. Có phân biệt NULL, empty string, whitespace, zero?
12. Có test nullable field roundtrip?
13. Có test JPQL IS NULL/IS NOT NULL?
14. Có hiểu COUNT(column) và COUNT(*)?
15. Có test nullable unique semantics trên DB đích?
16. Có tránh sentinel date/number tùy tiện thay NULL?
17. Có bảo vệ invariant giữa status và paidAt?

### Decimal

18. Có dùng BigDecimal thay vì double cho money?
19. Có parse decimal tránh binary approximation?
20. Có test precision/scale upper bounds?
21. Có kiểm soát rounding policy?
22. Có test giá trị cần rounding và giá trị chỉ có trailing zeros?
23. Có phân biệt @Digits và DB NUMERIC semantics?
24. Có test numeric roundtrip từ fresh context?
25. Assertion dùng compareTo hay equals đúng contract?
26. Có test arithmetic và aggregate types?

### Temporal

27. Có chọn đúng LocalDate/Instant/LocalDateTime/OffsetDateTime?
28. Có test DATE roundtrip và leap day?
29. Có test timestamp precision của DB?
30. Có test timezone/offset conversion phù hợp?
31. Có test DST gap/overlap khi nghiệp vụ dùng timezone có DST?
32. Có dùng half-open ranges cho time-window queries?
33. Có test from/to boundary values?
34. Có tránh dùng default timezone tùy môi trường?
35. Có lưu ZoneId nếu nghiệp vụ cần khôi phục giờ địa phương?
36. Có tránh đổi global TimeZone trong parallel tests?

### Transaction và môi trường

37. Fixture đã commit trước khi verify?
38. Có readback bằng EntityManager mới?
39. Có đóng EM/rollback khi error?
40. Có test JDBC/provider thực tế?
41. Có phân biệt `flush()` và `commit()`?
42. Với Spring tests, có biết outer transaction rollback mặc định?
43. Có tách provider-specific assertions khỏi portable JPA contracts?
44. Có tránh dữ liệu fixture trùng làm false positive?
45. Có log thông tin lỗi đủ nhưng không lộ dữ liệu nhạy cảm?

---

## 69. Sơ đồ ra quyết định khi viết một integration test

```text
              Bắt đầu với một invariant
                           |
                           v
                  Nó thuộc tầng nào?
                  /       |        \
                 /        |         \
                v         v          v
         Domain/Bean    JPA type   Database
          Validation     Mapping   constraint
                |         |          |
                v         v          v
         Unit/validator  Persist   Native SQL test
              test       & load   on real DB
                |         |          |
                +---------+----------+
                          |
                          v
              Bắt đúng transaction phase
               persist/flush/commit
                          |
                          v
                Commit hoặc rollback
                          |
                          v
              NEW EntityManager/connection
                          |
                          v
             Assert persisted values/rows
                          |
                          v
                Check edge boundaries:
                NULL, decimals, time
```

Từng assertion cần thể hiện **điều gì đã được chứng minh**. Việc Java constructor từ chối null chứng minh domain guard, nhưng không chứng minh SQL NOT NULL. Việc Hibernate query trả đúng một object trong cùng context không chứng minh commit. Và việc numeric value thay đổi sau roundtrip có thể là **rounding policy** chứ không phải ORM lỗi.

---

## 70. Kết luận

Kiểm thử **ràng buộc, NULL, số thập phân và thời gian** là bước quan trọng để bảo đảm rằng mô hình Java/JPA và dữ liệu quan hệ có cùng ý nghĩa.

Những nguyên tắc cần nhớ:

1. **Bean Validation, domain validation, JPA metadata và database constraints là các tầng khác nhau.** Test riêng từng tầng.
2. **UNIQUE cần kiểm thử theo đúng scope**, ví dụ `(tenant_id, invoice_number)`, và nullable unique có behavior đặc thù database.
3. **NOT NULL không cấm empty string**; `IS NULL` khác `= NULL`.
4. **FOREIGN KEY kiểm tra reference**, không tự bảo đảm tenant ownership/authorization.
5. **CHECK bảo vệ invariant ở database**, đặc biệt cho native SQL/external writers.
6. **BigDecimal là lựa chọn phù hợp cho decimal exact**, nhưng DB `NUMERIC(p,s)` vẫn có giới hạn và có thể làm tròn.
7. **Đặt rounding policy trước khi ghi**, không phụ thuộc vào việc database có làm tròn theo cách mong đợi hay không.
8. **So sánh BigDecimal bằng `compareTo` cho numeric equality**, chỉ dùng equals/scale assertions khi representation là một phần contract.
9. **LocalDate là ngày lịch, Instant là thời điểm**, còn LocalDateTime cần timezone context để trở thành một instant.
10. **TIMESTAMPTZ không lưu nguyên ZoneId**, offset có thể đổi khi đọc mà instant vẫn đúng.
11. **Timestamp nanoseconds không được mọi database giữ nguyên**; chọn precision và normalization policy rõ.
12. **Ngày địa phương có DST có thể dài 23 hoặc 25 giờ**, nên dùng start-of-day của ngày hiện tại và ngày tiếp theo.
13. **Truy vấn thời gian nên dùng khoảng `[from,to)`** để tránh trùng ranh giới.
14. **`flush` không phải `commit`**; test muốn kiểm tra dữ liệu cuối phải commit và đọc bằng EntityManager mới.
15. **Spring `@DataJpaTest` thường rollback mặc định**; cần transaction boundaries rõ nếu test committed state.
16. **Dùng DB/schema/provider mục tiêu**, không lấy H2 hay ORM-generated schema làm bằng chứng đầy đủ cho production.
17. **Không chỉ assert một RuntimeException**; kiểm tra SQLSTATE/constraint và trạng thái database sau rollback.
18. **Một bài test tốt có cả positive, negative, boundary và roundtrip cases** cho mọi kiểu dữ liệu quan trọng.

**Dữ liệu đáng tin cậy không chỉ là dữ liệu “lưu được”, mà là dữ liệu vẫn thỏa invariant và giữ đúng ý nghĩa sau khi đi qua validation, JPA, JDBC, database, commit và một lần đọc lại độc lập.**
