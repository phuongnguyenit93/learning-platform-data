# Giảm lộ dữ liệu trong nhật ký SQL, ngoại lệ và biểu diễn entity trong JPA

Trong một ứng dụng dùng Jakarta Persistence (JPA), dữ liệu nhạy cảm không chỉ có nguy cơ bị lộ khi trả sai API response. Dữ liệu có thể rời khỏi ranh giới bảo vệ thông qua **SQL logging**, **giá trị bind parameters**, **exception messages**, **stack traces**, **`toString()` tự sinh**, **JSON serialization của entity** hoặc **tracing/APM**.

Ví dụ hệ thống quản lý khách hàng lưu email, số điện thoại và địa chỉ giao hàng:

```java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    private Long id;

    private String email;

    private String phone;

    @Column(name = "internal_note")
    private String internalNote;

    @ManyToOne(fetch = FetchType.LAZY)
    private Organization organization;

    // ...
}
```

Một developer bật Hibernate bind logging để tìm lỗi:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

Khi application chạy:

```java
em.createQuery(
    "select c from Customer c where c.email = :email",
    Customer.class
)
.setParameter("email", "sample.person@example.invalid")
.getResultList();
```

SQL log có thể chỉ chứa:

```sql
select ... from customer c where c.email=?
```

nhưng **bind parameter logging** có thể bổ sung giá trị email thật. Việc dùng named parameter giúp tránh SQL injection, **không có nghĩa giá trị parameter sẽ không xuất hiện trong log**.

Một đoạn logging khác cũng nguy hiểm:

```java
log.warn("Could not update customer: {}", customer);
```

Nếu `Customer.toString()` được IDE hoặc Lombok tự sinh từ tất cả fields, nó có thể đưa email, số điện thoại, ghi chú nội bộ và thông tin tổ chức vào nhật ký. Với association lazy, nó còn có thể kích hoạt truy vấn SQL ngoài ý muốn.

Mục tiêu bài học là xây dựng một nguyên tắc xuyên suốt:

> **Chỉ đưa dữ liệu tối thiểu cần thiết cho mục tiêu vận hành vào telemetry.** Log phải nói được *sự kiện gì xảy ra*, *ở đâu*, *mức độ ảnh hưởng nào*, và *cần lần theo yêu cầu nào*, nhưng không được trở thành bản sao thiếu kiểm soát của dữ liệu nghiệp vụ.

Bài thuộc chương **Bảo mật dữ liệu** trong module *Data Persistence Relational Access ORM JPA*. Nội dung áp dụng cho JPA nói chung, với ví dụ Hibernate ORM, Spring Data JPA, Spring Boot và SLF4J được chỉ rõ là phụ thuộc thư viện hoặc phiên bản khi thích hợp.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Liệt kê các đường rò rỉ dữ liệu thường gặp khi JPA xử lý entity và SQL.
2. Phân biệt SQL statement logging với JDBC bind-value/extract-value logging.
3. Hiểu vì sao `PreparedStatement` bảo vệ khỏi một lớp SQL injection nhưng **không bảo vệ log** trước việc lộ bind values.
4. Cấu hình logging thận trọng cho môi trường production và diagnostic session.
5. Nhận diện dữ liệu nhạy cảm trong `SQLException`, `PersistenceException`, constraint violation và Spring exception translation.
6. Thiết kế thông điệp lỗi API ổn định, không trả raw SQL và stack trace.
7. Tránh lộ thông tin qua `toString()`, Lombok `@Data` và Java record auto-generated methods.
8. Phân biệt `@JsonIgnore`, DTO, entity graph và chính sách logging.
9. Thiết kế logging theo **allowlist** và structured event fields thay vì log nguyên object.
10. Sử dụng request correlation ID và pseudonymous identifiers có kiểm soát.
11. Phân biệt audit log cần thiết với debug log chứa dữ liệu nghiệp vụ.
12. Xây kiểm thử ngăn payload/secret canary lọt ra log hoặc JSON response.
13. Thiết lập runbook chẩn đoán production an toàn, có giới hạn thời gian và quyền.
14. Áp dụng nguyên tắc dữ liệu tối thiểu vào tracing, APM và database-side logs.
15. Không nhầm masking, encryption, hashing với giải quyết mọi bề mặt lộ dữ liệu.

## 2. Lập bản đồ những nơi dữ liệu có thể xuất hiện

Một thao tác JPA thường đi qua nhiều thành phần:

```text
HTTP request
  |
  v
Controller / DTO validation
  |
  v
Service / domain model
  |
  +-- application logger / exception handler
  |
  v
EntityManager / JPA provider
  |
  +-- entity.toString(), lifecycle callback
  +-- SQL statement logging
  +-- parameter binding logging
  +-- ORM exception/stack trace
  |
  v
JDBC driver / connection pool
  |
  +-- driver tracing
  +-- JDBC proxy / APM instrumentation
  |
  v
Database server
  |
  +-- query/error/slow query logs
  +-- query statistics / monitoring
  +-- audit extension
  |
  v
Collector / log storage / alerts / dashboards
```

Cùng một email hoặc address có thể xuất hiện ở nhiều điểm. **Tắt một logger ở application không bảo đảm toàn bộ luồng đã an toàn**.

### 2.1. Các bề mặt cần rà soát

| Bề mặt | Dữ liệu có thể lộ | Nguyên nhân |
|---|---|---|
| Hibernate SQL logger | Tên bảng/cột, SQL literals | SQL rendering và native SQL |
| Hibernate JDBC bind logger | Email, tên, token, identifier | Log parameters ở TRACE |
| JDBC driver/proxy | SQL và parameter values | Driver diagnostics, datasource proxy |
| DB error/slow query log | SQL, literals, constraint names | Server-side diagnostics |
| JPA/JDBC exception | SQL, bind info, key conflict detail | Exception message/cause chain |
| Validation exception | Invalid value, object graph | Log `getInvalidValue()`/root bean |
| Entity `toString()` | Toàn bộ fields/relationships | IDE/Lombok generated output |
| DTO/record `toString()` | Request payload | Auto-generated record representation |
| JSON serialization | PII/internal fields, lazy associations | Trả entity trực tiếp |
| Tracing/APM | Query text, spans, tags, headers | Auto-instrumentation |
| Audit/event logs | Actor/resource/action details | Log quá nhiều thay vì tối thiểu |
| Exception response | Stack trace, SQL error text | Trả `ex.getMessage()` cho client |

### 2.2. Không chỉ có dữ liệu “rõ ràng nhạy cảm”

Email, địa chỉ, số điện thoại, mã định danh cá nhân, dữ liệu sức khỏe, token, API key, session cookie và mật khẩu là những ví dụ dễ nhận. Nhưng đôi khi **tenant ID, customer ID, order ID, SQL predicates hoặc bảng quan hệ** cũng có thể tiết lộ hành vi hoặc thông tin riêng tư khi bị kết hợp với nguồn khác.

### 2.3. Metadata cũng có thể hữu ích cho kẻ tấn công

SQL error chứa `orders.payment_account_id`, table name hoặc constraint name có thể giúp suy đoán cấu trúc ứng dụng. Không nhất thiết mọi tên bảng đều tuyệt mật, nhưng **không có lý do gửi chi tiết nội bộ cho mọi client**.

### 2.4. Log có vòng đời khác database

Dữ liệu đã bị xóa khỏi database theo yêu cầu có thể còn trong log archive, tracing backend, email alert hoặc export từ dashboard. Vì vậy log không được xem là nơi lưu bản sao tuỳ ý của dữ liệu nghiệp vụ.

---

## 3. Phân loại dữ liệu trước khi quyết định log

Ví dụ một chính sách phân loại thực dụng:

| Nhóm | Ví dụ | Chính sách logging đề xuất |
|---|---|---|
| Public | Tên tính năng, phiên bản public API | Có thể log khi cần |
| Operational | Endpoint template, service name, latency, SQL count | Cho phép có kiểm soát |
| Internal identifier | Order ID, tenant ID, user ID | Hạn chế, cân nhắc pseudonymization |
| Personal data | Email, phone, địa chỉ, ghi chú khách hàng | Không log theo mặc định |
| Sensitive personal data | Hồ sơ y tế, tài chính, dữ liệu riêng tư đặc biệt | Không log; quy trình ngoại lệ nghiêm ngặt |
| Secrets | Password, token, key, cookie, JDBC credentials | Không log; rotate khi bị lộ |

Đây là **mẫu phân loại kỹ thuật**. Việc dữ liệu nào chịu hạn chế pháp lý hoặc chính sách nào phải dựa trên yêu cầu của tổ chức và phạm vi hoạt động thực tế.

### 3.1. “Không cần” thì không thu thập

Một stack trace có thể giúp điều tra nhiều hơn một email. Một correlation ID thường hữu ích hơn cả email khi kết nối log giữa services.

### 3.2. Không cho phép log tự do chỉ vì test data giả

Test có thể chứa canary email giả để phát hiện lộ dữ liệu, nhưng production logger vẫn cần chính sách an toàn. Đừng để config logging “tạm thời” của test trôi sang deploy.

### 3.3. Dữ liệu định danh có thể nhạy cảm theo ngữ cảnh

`Customer#42` có thể là một khóa kỹ thuật vô nghĩa nếu đứng riêng. Nhưng một log có timestamp, endpoint và user action có thể biến nó thành thông tin cá nhân khi liên kết với database. Chỉ dùng identifier nếu phục vụ nhu cầu truy vết đã xác định.

---

## 4. Entity minh họa và ranh giới an toàn

Ví dụ:

```java
package com.example.customer.persistence;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @Column(name = "customer_id")
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "email", nullable = false)
    private String email;

    @Column(name = "phone")
    private String phone;

    @Column(name = "delivery_address")
    private String deliveryAddress;

    @Column(name = "internal_note")
    private String internalNote;

    @Column(name = "created_at")
    private Instant createdAt;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "organization_id")
    private Organization organization;

    @Version
    @Column(name = "row_version")
    private Long version;

    protected Customer() {}

    public Long getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getEmail() { return email; }
    public String getPhone() { return phone; }
    public String getDeliveryAddress() { return deliveryAddress; }
    public String getInternalNote() { return internalNote; }
    public Organization getOrganization() { return organization; }
}
```

### 4.1. Java getters không phải chính sách công bố

Việc `getEmail()` tồn tại để application sử dụng không đồng nghĩa email được phép đưa vào log hoặc response của mọi endpoint.

### 4.2. @Column(nullable=false) không bảo vệ confidentiality

`nullable=false` mô tả mapping/constraint intent. Nó không mã hóa, mask hoặc hạn chế người đọc log.

### 4.3. @Version không che dữ liệu

Optimistic version dùng cho concurrency. Nó không có ý nghĩa bảo mật log.

### 4.4. @ManyToOne có thể mở rộng bề mặt lộ dữ liệu

Nếu `toString()` hoặc JSON serializer duyệt `organization`, các fields của Organization có thể được đưa ra ngoài dù endpoint chỉ cần Customer ID.

---

## 5. SQL statement logging khác bind parameter logging

Với JPQL:

```java
List<Customer> customers = em.createQuery(
    """
    select c
    from Customer c
    where c.tenantId = :tenant
      and c.email = :email
    """,
    Customer.class
)
.setParameter("tenant", authorizedTenant)
.setParameter("email", emailFromRequest)
.getResultList();
```

Hibernate có thể tạo SQL dạng:

```sql
SELECT
    c.customer_id,
    c.tenant_id,
    c.email,
    c.phone,
    c.delivery_address,
    c.internal_note,
    c.organization_id,
    c.row_version
FROM customer c
WHERE c.tenant_id = ?
  AND c.email = ?;
```

Bản SQL với dấu hỏi thường không chứa giá trị email trong placeholder. Nhưng logger bind parameters có thể ghi giá trị `emailFromRequest` và `authorizedTenant`.

### 5.1. Dùng bind parameters vẫn rất quan trọng

Bind parameters giúp tách query structure khỏi data values, giảm nguy cơ SQL injection đối với values. **Đây là yêu cầu bảo mật khác** với kiểm soát log.

### 5.2. Parameter name không phải parameter value

`:email` là tên tham số trong JPQL. Không mặc định nó được giữ nguyên trong SQL provider sinh ra, và cũng không mặc định nó bị ẩn trong mọi diagnostic tool.

### 5.3. SQL text vẫn có thể chứa literal

Ngay cả khi bind logging tắt, một native SQL query tự nối chuỗi:

```java
String sql =
    "select * from customer where email = '" +
    emailFromRequest +
    "'";
```

có thể chứa email trực tiếp trong SQL text; đồng thời có nguy cơ SQL injection. **Chỉ tắt bind logger không giải quyết query construction nguy hiểm**.

### 5.4. Column names có thể tự tiết lộ loại dữ liệu

SQL statement `select password_hash, secret_note from ...` có thể để lộ cấu trúc nhạy cảm dù không có rows. Production statement logging vẫn cần giới hạn audience và retention.

---

## 6. Hibernate SQL logger và show_sql

Hai cấu hình thường bị nhầm:

```properties
hibernate.show_sql=true
```

và logger category:

```properties
logging.level.org.hibernate.SQL=DEBUG
```

### 6.1. show_sql có thể ghi SQL trực tiếp ra console

`hibernate.show_sql` là tùy chọn provider-specific. Nó có thể đưa SQL ra standard output không đi qua toàn bộ các cơ chế filtering/formatting của logging framework. Tránh bật nó mặc định trong production.

### 6.2. Hibernate SQL logger

`org.hibernate.SQL` thường dùng để quan sát SQL do Hibernate phát ra. Đây là **category logger**, không phải một JPA standard setting.

### 6.3. SQL formatting không phải masking

`hibernate.format_sql=true` chỉ định dạng SQL dễ đọc. Nó **không bảo đảm xóa giá trị nhạy cảm**.

### 6.4. Khác biệt giữa phiên bản Hibernate

Hibernate 6.x thường dùng categories như `org.hibernate.orm.jdbc.bind` cho bind values; Hibernate 5.x có thể dùng `org.hibernate.type.descriptor.sql.BasicBinder`. Không sao chép cấu hình logger của phiên bản khác và khẳng định nó đang hoạt động; hãy kiểm tra provider version và logger categories thực tế.

### 6.5. Log SQL ở DEBUG cũng có rủi ro

Một native query có literal values hoặc SQL comments chứa thông tin request vẫn có thể đưa PII vào SQL logger dù bind category đã tắt.

---

## 7. Cấu hình production theo hướng hạn chế

Ví dụ Spring Boot với Hibernate 6.x:

```yaml
spring:
  jpa:
    show-sql: false
    properties:
      hibernate:
        format_sql: false
        generate_statistics: false

logging:
  level:
    org.hibernate.SQL: WARN
    org.hibernate.orm.jdbc.bind: OFF
    org.hibernate.orm.jdbc.extract: OFF
    org.hibernate.type.descriptor.sql.BasicBinder: OFF
```

Đây là **cấu hình mẫu**, không phải bảo đảm tất cả PII không bao giờ được log. Tên logger/level hỗ trợ có thể khác theo stack, và application/driver/APM/DB còn nhiều kênh riêng.

### 7.1. Điều gì được chặn?

Cấu hình trên giảm xác suất application vô tình ghi raw SQL/bind/extracted values qua các Hibernate logger categories thường gặp.

### 7.2. Điều gì chưa được chặn?

- Application tự log entity/request.
- Exception message có SQL/value.
- JDBC proxy tự log bind.
- Database server slow query logs.
- APM collector có capture parameters.
- SQL native concatenated literals.
- Framework debug dump của configuration.

### 7.3. Cần xem log configuration ở deployment

Spring properties có thể bị override bởi environment variables, command-line, config server hoặc logger level thay đổi runtime theo framework. Không kết luận production an toàn chỉ bằng file YAML trong repository.

### 7.4. Nếu phải bật SQL debug

Dùng một procedure có hạn mức: staging với synthetic data trước; production chỉ khi được phép, giới hạn logger category, duration, sampling và người có quyền truy cập. Sau đó khôi phục level và xác minh log pipeline.

---

## 8. JDBC driver, connection pool và datasource proxy

Không phải tất cả SQL logging đều thuộc Hibernate.

Một số application dùng:

- JDBC driver tracing.
- ProxyDataSource/P6Spy hoặc công cụ SQL interception.
- APM auto-instrumentation.
- Connection pool diagnostics.
- Driver/server-side prepared statement logging.

Các công cụ này có thể tái dựng SQL với parameter values, kể cả khi `org.hibernate.orm.jdbc.bind` đã tắt.

### 8.1. Kiểm tra từng tầng

| Tầng | Câu hỏi cần đặt |
|---|---|
| JPA provider | SQL/bind logger có bật không? |
| JDBC driver | Có trace parameters/connection properties không? |
| Datasource proxy | Có formatter inlined parameter values không? |
| APM | Có capture db.statement/db.query.text hoặc bind details không? |
| Collector | Có auto-enrichment với HTTP headers/body không? |
| Storage | Ai được xem, giữ bao lâu, mã hóa thế nào? |

### 8.2. StatementInspector không phải cơ chế redaction toàn diện

Hibernate `StatementInspector` là extension có thể xem hoặc thay đổi SQL text trước execution. Nó **không đại diện đầy đủ bind parameters** và không phải giải pháp tổng quát để scrub mọi dữ liệu được các tầng khác log.

### 8.3. Không tự thay SQL bằng regex vì mục tiêu masking

Regex có thể phá SQL semantics hoặc không xử lý literals trong comments, escaping, JSON, dialect-specific syntax. Tốt hơn là **không capture giá trị nhạy cảm ngay từ đầu**; khi cần sanitizer, dùng structured data/allowlist và kiểm thử.

### 8.4. Giám sát và bảo mật là hai yêu cầu cùng tồn tại

Một datasource proxy có thể thu query duration, SQL count, operation type và normalized query fingerprint mà không cần lưu raw bind values.

---

## 9. Database-side logs là bề mặt riêng

Nếu database dùng PostgreSQL, MySQL, SQL Server hoặc Oracle, máy chủ DB có thể có error/slow/audit logs và monitoring chứa query text. Tên settings, format và khả năng capture bind parameters tùy engine/version.

### 9.1. PostgreSQL

Các cơ chế có thể cần đánh giá:

- `log_statement`.
- `log_min_duration_statement`.
- Error/statement logging.
- `pg_stat_activity` và query text hiện thời.
- `pg_stat_statements` khi được bật.
- Audit extensions/managed database diagnostics.

`pg_stat_statements` thường tổng hợp normalized query text và statistics, nhưng không được giả định mọi literal/comment/parameter ở mọi đường đi đều được loại bỏ theo chính sách bảo mật mong muốn.

### 9.2. MySQL/MariaDB

General log, slow query log, Performance Schema và audit tooling có bề mặt/retention riêng. Không đồng nhất chúng với Java-side Hibernate logger.

### 9.3. Quản lý quyền xem database diagnostics

Một database user có quyền truy cập query/monitoring views có thể thấy nội dung mà API user không được xem. Áp least privilege, phân tách role vận hành và theo dõi truy cập vào log store.

### 9.4. Backup/log archive là một phần retention policy

Nếu hệ thống xóa log online sau 7 ngày nhưng giữ archive 2 năm không có kiểm soát, dữ liệu nhạy cảm vẫn tồn tại trong bản sao. Cần retention/lifecycle xuyên các tầng.

---

## 10. Native SQL và giá trị nối chuỗi: hai rủi ro cùng lúc

Sai:

```java
String sql =
    "select * from customer " +
    "where email = '" + emailFromRequest + "'";

List<?> rows = em.createNativeQuery(sql)
    .getResultList();
```

Vấn đề:

1. Có thể bị SQL injection.
2. Giá trị email hiện trực tiếp trong SQL text.
3. SQL text có thể đi vào ORM/JDBC/DB/APM logs.
4. Exception có thể chứa toàn bộ SQL.
5. Query text khác nhau theo mỗi email, khó grouping/tracing.

### 10.1. Dùng bind parameter cho data value

```java
List<?> rows = em.createNativeQuery(
    """
    select customer_id
    from customer
    where email = ?1
    """
)
.setParameter(1, emailFromRequest)
.getResultList();
```

Native positional parameter support và syntax cần phù hợp JPA/provider. Quan trọng là **bind value**, không nối literal.

### 10.2. Nhưng bind logging vẫn phải được tắt/kiểm soát

Bind parameter có thể bị log ở TRACE. SQL injection defense và telemetry minimization không thay nhau.

### 10.3. Dynamic table/column names không bind như values

Nếu cần sort theo column động, dùng allowlist:

```java
String orderColumn = switch (sortKey) {
    case "created" -> "created_at";
    case "name" -> "customer_name";
    default -> throw new IllegalArgumentException(
        "Unsupported sort key"
    );
};
```

Không đưa free-form client text vào SQL identifier hoặc SQL comment.

### 10.4. Không thêm email vào SQL comments để debug

```sql
/* request-email=sample.person@example.invalid */
SELECT ...
```

Comments cũng có thể vào logs/DB monitoring. Nếu cần correlation, dùng opaque request ID đã kiểm soát và kiểm tra log/tooling có capture comment hay không.

---

## 11. Exception message có thể lộ dữ liệu theo những cách nào?

Một exception từ JDBC/ORM có thể chứa:

- Original SQL text.
- Column/table/constraint name.
- Rejected key hoặc value.
- Bind parameter contents theo provider/driver.
- Connection URL hoặc database name.
- Details của nested cause.
- Object dump trong custom exception message.

Ví dụ SQL constraint violation khi insert trùng email:

```text
Database reports:
  unique constraint violated
  duplicate key value includes (...email...)
```

Không phải mọi DB/driver đều ghi rõ giá trị trùng, nhưng **ứng dụng không được giả định exception message sạch**.

### 11.1. EntityExistsException không luôn có cùng message

`jakarta.persistence.EntityExistsException` có thể xảy ra vì duplicate identity trong persistence context hoặc khi provider phát hiện row đã có. Message tùy provider và context.

### 11.2. PersistenceException có nhiều nguyên nhân

`PersistenceException` có thể đại diện SQL syntax, connection, constraint hoặc provider errors. Không đưa nguyên message ra API như nội dung người dùng có thể xem.

### 11.3. RollbackException/TransactionSystemException có nested causes

Commit-time failures có thể được bọc qua nhiều tầng. Log `ex` với stack trace đầy đủ có thể ghi cả message của các causes chứa data. Không chỉ kiểm tra message của exception ngoài cùng.

### 11.4. Đừng tin prefix “ConstraintViolationException”

`jakarta.validation.ConstraintViolationException` và `org.hibernate.exception.ConstraintViolationException` là hai loại khác nhau. Một cái nói Java Bean Validation, một cái thường nói database constraint. Cả hai đều có đường tiếp cận invalid values và phải được xử lý thận trọng.

---

## 12. Phân biệt exception và dữ liệu nên sử dụng để xử lý

| Exception/source | Ngữ nghĩa | Có thể log an toàn |
|---|---|---|
| `EntityExistsException` | JPA entity identity conflict | Error code/class, operation, request ID |
| `PersistenceException` | Lỗi persistence tổng quát | Exception category, DB operation, safe correlation |
| `RollbackException` | Commit/transaction failed | Transaction outcome, safe category |
| `OptimisticLockException` | Concurrent stale version | Conflict category, non-sensitive resource ref |
| `jakarta.validation.ConstraintViolationException` | Bean validation failed | Field name/code đã allowlist; không invalid value |
| Hibernate SQL `ConstraintViolationException` | DB constraint failed | Safe SQLState/constraint category nếu policy cho phép |
| `SQLException` | Driver/server error | SQLState, vendor code, no raw SQL/value by default |
| Spring `DataIntegrityViolationException` | Database integrity category | Stable application error code |
| Spring `DataAccessException` | Data access failures | Error category, operation ID |

### 12.1. SQLState không tự đủ để phân loại nghiệp vụ

Ví dụ PostgreSQL `23505` thường báo unique violation, nhưng để biết trùng email, SKU hay PK cần xác định constraint/index đúng. Nếu muốn trả lỗi cụ thể, thiết kế mapping từ *constraint known* sang *application error code* có kiểm soát.

### 12.2. Constraint name cũng có thể nhạy cảm

`uk_customer_email` có thể tiết lộ schema. Có thể dùng nội bộ khi cần chẩn đoán, không đưa trực tiếp vào public error response.

### 12.3. Không log nguyên entity kèm exception

Sai:

```java
log.error(
    "Failed to save customer {}",
    customer,
    exception
);
```

Ngay cả khi logger dùng placeholders, `customer.toString()` có thể in PII và `exception` có thể in SQL/cause chain.

### 12.4. Logging exception object không mặc định an toàn

`log.error("...", ex)` thường in stack trace chứa nested messages. Chỉ dùng trong diagnostic channel đã được phê duyệt và có cơ chế hạn chế truy cập/lọc dữ liệu, hoặc log structured safe fields thay vì exception object.

---

## 13. Tách xử lý lỗi cho client khỏi chi tiết chẩn đoán nội bộ

Ví dụ API cố tạo Customer với email trùng. Điều client cần biết thường là:

```json
{
  "code": "CUSTOMER_CONFLICT",
  "message": "Cannot create the requested customer"
}
```

Không cần:

```text
org.postgresql.util.PSQLException:
 duplicate key violates uk_customer_email
 key (email)=(sample.person@example.invalid)
 SQL: insert into customer (...)
```

### 13.1. Mã lỗi ổn định hơn raw message

`CUSTOMER_CONFLICT` hoặc `RESOURCE_ALREADY_EXISTS` là application contract. Nếu message DB đổi giữa PostgreSQL versions, API vẫn ổn định.

### 13.2. Không lộ sự tồn tại của tài nguyên ngoài tenant

Một client thuộc tenant A gửi email/ID của tenant B. Thông báo quá chi tiết có thể tiết lộ “khách hàng này đã tồn tại”. Chọn behavior theo authorization và chống user enumeration.

### 13.3. 409 chỉ khi thực sự là business conflict

`DataIntegrityViolationException` cũng có thể do NOT NULL, FK, CHECK. Không catch mọi SQL integrity error và trả “Email đã tồn tại”.

### 13.4. Lỗi không phân loại được

Trả message chung, status phù hợp (thường server error) và correlation ID. Không đưa raw exception để “giúp client tự sửa” vì nó có thể lộ dữ liệu khác.

---

## 14. Ví dụ Spring REST exception handler an toàn

Domain exception không chứa entity/payload:

```java
public final class DomainConflictException
        extends RuntimeException {

    private final String code;

    public DomainConflictException(String code) {
        super("Domain conflict"); // Không chứa PII.
        this.code = code;
    }

    public String code() {
        return code;
    }
}
```

Advice:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class SafeApiExceptionHandler {

    @ExceptionHandler(DomainConflictException.class)
    public ProblemDetail conflict(DomainConflictException ex) {
        ProblemDetail problem =
            ProblemDetail.forStatus(HttpStatus.CONFLICT);

        problem.setTitle("Resource conflict");
        problem.setDetail(
            "The requested operation could not be completed."
        );
        problem.setProperty("code", ex.code());
        return problem;
    }

    @ExceptionHandler(Exception.class)
    public ProblemDetail unexpected(Exception ex) {
        ProblemDetail problem =
            ProblemDetail.forStatus(
                HttpStatus.INTERNAL_SERVER_ERROR
            );

        problem.setTitle("Unexpected error");
        problem.setDetail(
            "The service could not complete the request."
        );
        problem.setProperty("code", "INTERNAL_ERROR");
        return problem;
    }
}
```

`ProblemDetail` là Spring Framework API, không phải JPA API. Đây là **mẫu response tối thiểu**; production cần thêm mapping status chuyên biệt, correlation ID đã validate, logging an toàn và xử lý các exception theo cấu hình framework thực tế.

### 14.1. Không set detail = ex.getMessage()

Một số domain exception chứa message an toàn, một số persistence exception không. Chính sách mặc định nên chọn message từ allowlist thay vì tự động truyền exception message.

### 14.2. Không set property "debug" bằng stack trace

Trả stack trace có thể lộ classpath, database structure, parameters và application secrets.

### 14.3. Phân loại conflict ở đúng boundary

Nếu Spring transaction commit xảy ra sau method body, exception có thể phát sinh bên ngoài `try/catch` bên trong transactional method. Cần thiết kế error translation/coordination ở boundary thực sự bao trùm flush/commit.

### 14.4. Không tự đổi DB failure thành success

Nếu exception ở commit và không biết transaction đã hoàn tất hay chưa (mất kết nối), có thể cần idempotency/reconciliation. Bảo vệ log không có nghĩa bỏ qua transaction correctness.

---

## 15. Bean Validation: invalid value không phải nội dung log mặc định

Bean Validation có thể cung cấp:

```java
ConstraintViolation<?> violation = ...;

String propertyPath =
    violation.getPropertyPath().toString();

String messageTemplate =
    violation.getMessageTemplate();

Object invalidValue =
    violation.getInvalidValue();
```

### 15.1. Đừng log invalidValue

Nếu constraint `@Email` lỗi, giá trị invalid có thể là email thật. Nếu `@NotBlank` lỗi trên access token, invalid value có thể là secret.

### 15.2. Đừng log rootBean

`violation.getRootBean()` có thể trỏ tới một object graph có nhiều fields. Log object này thường gọi `toString()`.

### 15.3. Custom validator message phải tránh nội suy dữ liệu

Không tạo thông báo như:

```text
Invalid token value: eyJhbGciOi...
```

Nên nói:

```text
token: invalid format
```

với field identifier/code đã được phép công khai, không kèm input value.

### 15.4. Field names cũng cần allowlist khi là public response

Một validation framework có thể trả path vào nested internal object. Chỉ lộ API field names đã là một phần public contract.

### 15.5. Không lưu request body đầy đủ để debug validation

Validation failures có thể chiếm tỷ lệ cao và đưa payload nhạy cảm vào log. Thay bằng error code, endpoint template, field category và correlation.

---

## 16. Lombok @Data: rủi ro khi áp lên JPA entity

Một mẫu dễ gặp:

```java
import lombok.Data;

@Data
@Entity
public class Customer {

    @Id
    private Long id;

    private String email;

    private String phone;

    @OneToMany(mappedBy = "customer")
    private List<SalesOrder> orders;
}
```

`@Data` có thể tạo `toString()`, `equals()`, `hashCode()` và getters/setters dựa trên fields theo quy tắc Lombok. Với JPA entities, điều đó có thể:

- In PII ra log.
- Traverse lazy relationships.
- Gây recursive relationship traversal.
- Làm phát sinh SQL bất ngờ.
- Gây performance issue hoặc lazy initialization exception.
- Tạo equality/hash semantics không phù hợp mutable/generated identity.

### 16.1. Tránh @Data cho entity như một convention an toàn

Ưu tiên khai getters/setters cần thiết có kiểm soát. Không tự động generate all-fields `toString`/`equals`/`hashCode` mà không hiểu JPA lifecycle.

### 16.2. @ToString.Exclude vẫn cần rà soát

Nếu vẫn dùng Lombok:

```java
@Getter
@Setter
@ToString(onlyExplicitlyIncluded = true)
@Entity
public class Customer {

    @Id
    @ToString.Include
    private Long id;

    @ToString.Exclude
    private String email;

    @ToString.Exclude
    private String phone;

    @ToString.Exclude
    @OneToMany(mappedBy = "customer")
    private List<SalesOrder> orders;
}
```

Đoạn minh họa; ở thực tế ID cũng có thể nhạy cảm/giúp liên kết dữ liệu, nên chỉ `@ToString.Include` khi được policy cho phép. **Allowlist** là cách giảm nguy cơ khi sau này thêm field nhạy cảm.

### 16.3. Equals/hashCode là chủ đề khác toString

Không dùng `@EqualsAndHashCode(onlyExplicitlyIncluded = true)` một cách máy móc nếu ID được generate sau persist hoặc entity có proxies. Cần thiết kế entity equality theo lifecycle, chứ không để logging requirement làm thay đổi equality semantics tùy ý.

---

## 17. Viết toString() thủ công theo nguyên tắc tối thiểu

Một phương án đơn giản:

```java
@Override
public String toString() {
    return "Customer{entityType=Customer}";
}
```

Nếu cần log một định danh không nhạy cảm theo policy:

```java
@Override
public String toString() {
    return "Customer{id=" + id + "}";
}
```

### 17.1. Không truy cập relation từ toString()

Tránh:

```java
return "Customer{organization=" +
    organization.getName() +
    "}";
```

vì có thể kích hoạt lazy load, N+1 hoặc lỗi khi persistence context đã đóng.

### 17.2. Không dump tất cả getters qua reflection

Một helper debug “tự động in mọi property” có thể vượt cả những fields developer định không log và kích hoạt lazy associations.

### 17.3. toString không phải representation cho API

Mục đích chủ yếu của `toString` là mô tả đối tượng cho developer, không phải JSON/API response contract. Vì vậy tránh biến nó thành toàn bộ nội dung entity.

### 17.4. Không coi “đã mask vài trường” là hoàn toàn an toàn

Khi thêm field mới như `governmentId`, auto-inclusion có thể làm lộ dữ liệu. Allowlist hạn chế nguy cơ tương lai tốt hơn blacklist fields hiện có.

---

## 18. Java record và request DTO cũng có thể bị log ngoài ý muốn

Một record:

```java
public record CreateCustomerRequest(
    String email,
    String phone,
    String deliveryAddress
) {}
```

Record có `toString()` tự sinh chứa các component values.

Sai:

```java
log.info("Create customer request: {}", request);
```

Kết quả có thể hiển thị toàn bộ email/phone/address.

### 18.1. Entity và DTO đều cần data minimization

Chỉ chuyển từ entity sang DTO **không bảo đảm log sạch** nếu DTO vẫn chứa PII và bị in nguyên object.

### 18.2. Thiết kế một event log riêng

```java
log.info(
    "event=customer_create_requested requestId={} source={}",
    requestId,
    "web"
);
```

`requestId` phải là opaque, validated correlation identifier không chứa payload.

### 18.3. Có thể override toString của record

Nhưng không dựa hoàn toàn vào override, vì JSON serializer hoặc reflection-based logger vẫn có thể đọc record components. Đặt policy ở tầng logging và transport serialization riêng.

---

## 19. Lazy associations làm vấn đề toString nghiêm trọng hơn

Giả sử:

```java
@OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
private List<SalesOrder> orders;
```

Generated `toString()` in `orders` có thể khiến JPA tải collection từ database.

### 19.1. N+1 có thể xuất hiện chỉ từ log.debug

```java
for (Customer c : customers) {
    log.debug("{}", c);
}
```

Nếu `toString` traverse collection, vòng lặp có thể tạo thêm nhiều SELECT. Với logger disabled, SLF4J có thể tránh stringify ở một số hình thức call, nhưng không nên dựa vào level để biện minh cho unsafe `toString`.

### 19.2. Bidirectional relationship có thể recursive

Customer.orders → SalesOrder.customer → Customer.orders → ... có thể gây recursion hoặc exception, tùy generated methods và proxy behavior.

### 19.3. LazyInitializationException có thể chứa thông tin mapping

Nếu gọi relation sau khi EntityManager đóng, Hibernate có thể ném exception với entity/association details. Không gửi raw message đó cho client.

### 19.4. Không dùng EAGER để “sửa” logging

Đổi mapping sang EAGER để `toString` chạy được chỉ gây over-fetch và che nguyên nhân. Sửa `toString`/logging thay vì phá fetch design.

---

## 20. @JsonIgnore không phải chính sách log

Một entity:

```java
@JsonIgnore
private String internalNote;
```

Có thể khiến Jackson không serialize field này trong một số đường đi JSON, nhưng:

- `toString()` vẫn có thể in nó.
- Hibernate bind logger vẫn có thể log giá trị lúc ghi.
- DB exception vẫn có thể chứa giá trị.
- Một serializer khác có thể không tôn trọng Jackson annotations.
- Reflection/debuggers có thể đọc field.

### 20.1. Jackson annotations điều khiển một kênh

`@JsonIgnore`, `@JsonProperty` và views giải quyết JSON serialization behavior theo Jackson configuration. Chúng không tự điều khiển JPA provider diagnostics.

### 20.2. Không trả entity trực tiếp

Controller:

```java
@GetMapping("/customers/{id}")
public Customer getCustomer(...) {
    return repository.findById(...).orElseThrow();
}
```

có thể serialize email, phone, internalNote, organization và lazy proxies theo cấu hình.

### 20.3. Dùng response DTO allowlist

```java
public record CustomerPublicResponse(
    Long id,
    String displayName
) {}
```

Service xây DTO từ dữ liệu đã được authorize. Nếu endpoint không cho phép xem email, email không xuất hiện trong DTO.

### 20.4. DTO không miễn trừ kiểm tra authorization

Có DTO chỉ có displayName nhưng truy vấn thiếu tenant predicate vẫn có thể trả dữ liệu tenant khác. Projection và security phải kết hợp.

---

## 21. JPA projections giúp giảm dữ liệu đi qua application

Khi API chỉ cần Customer ID và display name:

```java
public record CustomerListRow(
    Long id,
    String displayName
) {}
```

JPQL:

```java
List<CustomerListRow> rows = em.createQuery(
    """
    select new com.example.api.CustomerListRow(
        c.id,
        c.displayName
    )
    from Customer c
    where c.tenantId = :tenant
    order by c.id
    """,
    CustomerListRow.class
)
.setParameter("tenant", authorizedTenant)
.getResultList();
```

Đây là một **ví dụ projection**: giả sử entity thực tế có persistent field `displayName` và DTO type đúng. Nó không khớp nguyên xi entity minh họa ở phần đầu vốn chỉ có email/phone/internalNote; hãy thêm displayName vào model hoặc thay biểu thức bằng field public được phép theo ứng dụng.

### 21.1. Giảm lượng dữ liệu xử lý

Nếu query chỉ chọn 2 columns, application không cần hydrate đầy đủ entity chứa address/internalNote để tạo danh sách.

### 21.2. Không coi projection như mã hóa

Đó là **data minimization** trong read path, không phải kỹ thuật cryptography.

### 21.3. SQL vẫn có thể mang PII trong WHERE

Ngay cả khi SELECT chỉ lấy ID/displayName, `where c.email = :email` có email ở bind values. Logging policy vẫn cần.

### 21.4. Đừng đổi security boundary theo nhu cầu tối ưu

Tenant filter/authorization phải là điều kiện bất biến của query plan.

---

## 22. Log theo sự kiện, không log theo entity

Sai:

```java
log.info("Saved: {}", customer);
```

Tốt hơn:

```java
log.info(
    "event={} outcome={} requestId={} entityType={}",
    "customer_create",
    "success",
    requestId,
    "Customer"
);
```

### 22.1. Trường nên có khi cần

- Stable event code.
- Outcome category (success/conflict/failure).
- Endpoint template hoặc operation name.
- Correlation/request ID.
- Latency bucket.
- Non-sensitive version/build ID.
- Error category/SQLState nếu thực sự cần.
- Sanitized/pseudonymous resource ref nếu có use case.

### 22.2. Trường không nên log mặc định

- Request body.
- Response body.
- Entity object.
- Password/token/session cookie.
- Email, phone, address.
- SQL bind values.
- Raw query parameters.
- Complete exception chain.
- Sensitive HTTP headers.
- JDBC connection string có credentials.

### 22.3. Log “số bản ghi” khi phù hợp

```java
log.info(
    "event=customer_import outcome=completed count={}",
    importedCount
);
```

Có thể đủ cho vận hành mà không cần log từng Customer row.

### 22.4. Log theo business outcome, không theo full payload

Một payment attempt có thể log trạng thái/safe operation ID, nhưng không log toàn bộ payment method details. Nếu phải phục vụ compliance audit, audit events vẫn cần data minimization và access controls riêng.

---

## 23. Structured logging và allowlist

Structured JSON log ví dụ:

```json
{
  "event": "customer_create",
  "outcome": "conflict",
  "requestId": "req-7f0c2a",
  "errorCode": "CUSTOMER_CONFLICT",
  "operation": "POST /customers",
  "durationMs": 18
}
```

### 23.1. Vì sao structure có lợi?

Có thể filter, aggregate và alert theo fields mà không cần parse một chuỗi tự do chứa PII.

### 23.2. Allowlist tốt hơn “dump object rồi mask bằng regex”

Nếu log builder chỉ cho `event`, `errorCode`, `durationMs`, khả năng vô tình thêm `email` thấp hơn khi serialize toàn bộ DTO rồi scrub.

### 23.3. Structured logging vẫn có thể chứa PII

JSON encoder không tự bảo vệ nếu code đặt `"email": customer.getEmail()`. Format an toàn chỉ khi **field selection** an toàn.

### 23.4. Tránh dynamic keys từ user input

Đừng dùng email/user input làm JSON field name, metric label hoặc high-cardinality logging key.

---

## 24. Correlation ID thay vì tìm theo email

Một lỗi vận hành thường dẫn tới yêu cầu:

> “Cho tôi log tất cả events có email X để debug.”

Thay bằng request ID, business operation ID hoặc opaque reference đã được thiết kế:

```text
requestId=req-7f0c2a
operation=customer_create
outcome=conflict
errorCode=CUSTOMER_CONFLICT
```

### 24.1. Yêu cầu đối với correlation ID

- Không chứa email/phone/token.
- Có format/length hợp lệ.
- Khó đoán nếu dùng như handle nhạy cảm; nhưng không coi ID là authentication.
- Được tạo hoặc validate ở trusted boundary.
- Được propagate qua services có kiểm soát.

### 24.2. Không tin raw X-Request-Id tuyệt đối

Client có thể gửi header chứa newline, chuỗi rất dài hoặc thông tin cá nhân. Nếu nhận correlation ID từ client, giới hạn length/charset và tạo ID mới nếu không hợp lệ.

### 24.3. Request ID không thay audit identity

Audit nghiệp vụ có thể phải xác định actor/resource, nhưng log vận hành không cần luôn chứa trực tiếp user email. Dùng correlation giữa hai kênh với quyền phù hợp.

---

## 25. MDC và bảo vệ context giữa requests

SLF4J MDC thường dùng để gắn `requestId` vào log:

```java
import org.slf4j.MDC;

public void handleRequest(
        String validatedRequestId,
        Runnable action
) {
    try {
        MDC.put("requestId", validatedRequestId);
        action.run();
    } finally {
        MDC.remove("requestId");
    }
}
```

### 25.1. Phải cleanup MDC

Thread pools tái sử dụng threads. Nếu không xóa context trong finally, log của request sau có thể mang ID/tenant của request trước.

### 25.2. Không đặt secret vào MDC

MDC có thể được include vào nhiều log lines và exported sang centralized collectors. Tránh user token, session ID hoặc customer email.

### 25.3. Async/reactive execution cần propagation riêng

MDC dựa trên thread context trong nhiều logging frameworks. Với `CompletableFuture`, virtual threads, Reactor hoặc executors, phải có propagation/cleanup strategy tương ứng, không suy luận context luôn đi theo request.

### 25.4. MDC cũng chịu input validation

Một request ID chứa control characters có thể làm bẩn log line nếu không được validate/encode.

---

## 26. Log injection và dữ liệu người dùng

Một giá trị do client kiểm soát:

```text
searchTerm = "normal-text\nERROR payment-approved"
```

Nếu log trực tiếp:

```java
log.info("searchTerm={}", searchTerm);
```

nó có thể tạo dòng giả trong text logs hoặc ảnh hưởng parser/alert.

### 26.1. Placeholder không tự escape control characters

SLF4J parameterized logging giúp format/avoid eager concatenation, nhưng không tự cam kết chống log injection.

### 26.2. Cách phòng ngừa

- Không log user input nếu không cần.
- Nếu cần, chỉ log normalized category/length/bucket.
- Với giá trị allowlisted, validate charset/length.
- Dùng structured encoder an toàn.
- Tránh multiline raw payload.
- Hạn chế length để chống log volume amplification.

### 26.3. Cẩn thận exception messages từ external systems

Một error message từ DB/API khác có thể chứa data không tin cậy. Không coi message đó là “internal trusted string” để in thẳng ra log.

---

## 27. Cần correlation theo người dùng? Dùng pseudonymous reference có chủ đích

Có trường hợp vận hành cần biết các events liên quan cùng một người mà không đưa email thô vào log. Một chiến lược là tạo **HMAC token** từ canonical identifier bằng secret key được quản lý an toàn.

### 27.1. Vì sao không dùng SHA-256(email) đơn giản?

Email có không gian tìm kiếm giới hạn và dễ đoán. Một kẻ có danh sách email có thể hash thử để so khớp. **Unsalted hash không phải cách ẩn danh email đáng tin**.

### 27.2. Mã Java HMAC-SHA256 minh họa

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class SafeLogSubjectKey {

    private final byte[] secretKey;

    public SafeLogSubjectKey(byte[] secretKey) {
        this.secretKey = secretKey.clone();
    }

    public String pseudonymFor(String canonicalSubjectId) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");

            mac.init(
                new SecretKeySpec(secretKey, "HmacSHA256")
            );

            byte[] digest = mac.doFinal(
                canonicalSubjectId.getBytes(
                    StandardCharsets.UTF_8
                )
            );

            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (Exception ex) {
            throw new IllegalStateException(
                "Cannot create log pseudonym"
            );
        }
    }
}
```

### 27.3. Key không được hard-code

Lấy HMAC key từ secret manager; kiểm soát quyền, rotation và key version. Không log key, không commit key vào repository và không đưa value được HMAC từ raw secret/token nếu không có business justification.

### 27.4. HMAC vẫn là pseudonymization, không phải xóa danh tính tuyệt đối

Một token ổn định cho phép liên kết hành vi qua nhiều events. Nó vẫn có thể chịu ràng buộc privacy/security policy và cần retention/rotation.

### 27.5. Khi không cần correlation lâu dài, đừng tạo token

Mỗi request có một request ID có thể đã đủ. Dùng HMAC subject key chỉ khi có mục đích rõ và thời hạn lưu giữ hợp lệ.

---

## 28. Mã hóa dữ liệu ở database không tự làm log an toàn

Giả sử entity field được mã hóa bằng `AttributeConverter`:

```java
@Convert(converter = SensitiveTextConverter.class)
@Column(name = "encrypted_note")
private String internalNote;
```

Dù giá trị xuống JDBC là ciphertext trong một số đường đi, plaintext vẫn có thể tồn tại trong Java entity/request DTO và bị log qua `toString()`.

### 28.1. Mã hóa tại chỗ nào?

- Application-level encryption có thể giảm plaintext ở storage/driver path nhất định.
- Database-side encryption có thể bảo vệ storage hoặc column data theo kiến trúc.
- TLS bảo vệ data in transit.
- Log minimization bảo vệ observability surfaces.

Chúng là các lớp khác nhau.

### 28.2. Converter không phải cơ chế chống mọi logging

Application vẫn có thể log field **trước khi converter chạy**. Nếu ciphertext được log thường xuyên, nó vẫn có thể là dữ liệu nhạy cảm có thể linkability/rotation concerns.

### 28.3. Database error vẫn có thể tiết lộ context

Constraint name/SQL query text và những fields không mã hóa vẫn lộ. Encryption không thay exception handling.

### 28.4. Không tự xây crypto tùy tiện

Ví dụ HMAC ở trên là pseudonymization của identifier để phục vụ log; không phải hướng dẫn mã hóa data column. Encryption cần authenticated scheme, key lifecycle và threat model đầy đủ.

---

## 29. Log secrets: những đường không hiển nhiên

Một số cách secrets bị lộ:

```java
log.debug("Datasource properties: {}", properties);
log.warn("Failed request: {}", httpRequest);
log.error("JWT decode failed for token=" + token);
log.info("Authorization header: {}", authorization);
log.debug("JDBC URL: {}", jdbcUrl);
```

### 29.1. JDBC URL có thể chứa credentials

Một URL hoặc connection property map có thể chứa username/password. Đừng ghi raw configuration map ra log.

### 29.2. Header/HTTP request dump

Authorization, Cookie, Set-Cookie, X-API-Key và custom headers có thể chứa secrets. Reverse proxy/APM cũng cần policy masking.

### 29.3. ORM exception từ connection

Một exception liên quan datasource có thể chứa hostname, DB name hoặc URL. Tránh trả `getMessage()` công khai.

### 29.4. Khi secret đã bị log

Cần containment, rotation/revocation, hạn chế access và điều tra theo incident procedure. Không chỉ xóa log rồi coi như không còn rủi ro vì có thể đã có replicas/backups.

---

## 30. Phân biệt operational log và audit log

Operational log phục vụ:

- Quan sát lỗi hệ thống.
- Đo latency.
- Theo dõi request.
- Điều tra query plans/SQL count.
- Cảnh báo quá tải.

Audit log phục vụ:

- Ai thực hiện hành động nào?
- Trên resource nào?
- Kết quả gì?
- Khi nào?
- Có được phê duyệt hay không?

### 30.1. Audit không có nghĩa lưu full entity snapshot

Ví dụ một audit event:

```json
{
  "event": "customer_address_updated",
  "actorRef": "user-ref-...",
  "resourceRef": "customer-ref-...",
  "outcome": "success",
  "timestamp": "2026-11-15T03:00:00Z"
}
```

Không cần đưa nguyên địa chỉ cũ/mới vào audit log nếu policy chỉ yêu cầu ghi nhận rằng địa chỉ đã được cập nhật.

### 30.2. Nếu cần field-level change history

Cân nhắc thiết kế audit history riêng có schema, encryption/access controls, retention và business justification. Đừng dựa vào `entity.toString()` trước/sau trong log.

### 30.3. Audit integrity

Với workflows quan trọng, audit cần protection chống sửa/xóa không được phép, cùng cơ chế rotation và kiểm soát privileged access. Đây là yêu cầu riêng, không được giải quyết chỉ bằng bật DEBUG.

### 30.4. Audit access cũng phải được audit

Một người có quyền xem audit có thể truy xuất hành vi nhạy cảm. Áp RBAC/least privilege và logging cho hoạt động xem/export audit.

---

## 31. Dữ liệu trong tracing/APM

Distributed tracing thường lưu:

- Service/span name.
- HTTP route template.
- Request/correlation ID.
- Database operation/system.
- Query fingerprint hoặc query text.
- Duration/status.
- Exception event/message/stacktrace.

### 31.1. Không tự động capture db bind values

Ngay cả một APM agent mặc định không capture values hôm nay, một setting mới có thể bật chúng. Quản lý config và verify khi upgrade.

### 31.2. Span attributes cũng cần allowlist

Không gắn:

```text
db.customer.email=sample.person@example.invalid
http.request.body=...
jwt.token=...
```

vào spans.

### 31.3. Tên span có thể vô tình chứa giá trị

Sai: `spanName="Find customer " + email`. Tốt hơn: `spanName="customer.lookup"` với attributes chỉ gồm safe identifiers/categories.

### 31.4. Sampling không thay masking

Sample 1% vẫn có thể thu giá trị rất nhạy cảm. Data minimization phải được áp trước khi ingest vào collector.

---

## 32. Nhiều sink dữ liệu: console, file, collector, alert

Một log event có thể được phát tán:

```text
Application logger
    |
    +-- stdout / container runtime
    +-- local file
    +-- log shipper
    +-- central log store
    +-- APM / SIEM
    +-- alert webhook / email / chat channel
    +-- backup / archive
```

### 32.1. Mức bảo vệ thấp nhất là bề mặt nguy hiểm

Log store được bảo vệ tốt nhưng alert email tự động gửi raw stacktrace ra hộp thư rộng vẫn là lộ thông tin.

### 32.2. Retention theo loại log

Operational debug logs nên có thời gian lưu ngắn phù hợp; audit có thể cần lâu hơn theo yêu cầu. Không dùng “giữ vô hạn vì có thể hữu ích”.

### 32.3. RBAC và truy xuất log

Chỉ những người có nhiệm vụ mới được xem query traces/cause chains, và nên có audit trail cho truy cập dữ liệu nhạy cảm khi cần.

### 32.4. Export/download từ dashboard

CSV export của logs cũng là bản sao dữ liệu. DLP/redaction/access controls cần áp cho các hành động export, không chỉ view.

---

## 33. Cách mở diagnostic logging an toàn khi production gặp lỗi

Không phải lúc nào cũng có thể chẩn đoán lỗi mà không thêm telemetry. Nhưng nên có **quy trình break-glass có giới hạn**.

1. Xác định symptom và correlation IDs trước.
2. Ưu tiên reproduce trong staging với synthetic data.
3. Bật metrics/SQL count/query fingerprints thay vì bind values.
4. Nếu cần chi tiết hơn, chọn một service instance/request cohort giới hạn.
5. Giới hạn thời gian bật logger và phạm vi người truy cập.
6. Tránh ghi PII, credentials, full request bodies.
7. Cảnh báo log retention/export paths.
8. Khôi phục cấu hình và kiểm tra logger đã tắt.
9. Lưu diagnosis/result vào incident report không có payload nhạy cảm.
10. Nếu phát hiện dữ liệu lộ, kích hoạt incident handling.

### 33.1. Không bật TRACE toàn `org.hibernate`

TRACE quá rộng có thể tạo khối log lớn chứa SQL/bind/ORM internals. Chọn category cần thiết và kiểm tra hậu quả trước.

### 33.2. Remote log level changes phải được quản lý

Nếu hệ thống có actuator/runtime logging control, endpoint phải được bảo vệ bằng authentication/authorization và audit; tránh cho public client bật bind logging.

### 33.3. Time-limited access

Quyền truy cập raw diagnostics nên có expiry nếu cơ chế hỗ trợ. Việc “tạm cấp” rồi không thu hồi là một rủi ro vận hành thường gặp.

---

## 34. Thiết kế logger utility an toàn

Một lỗi kiến trúc là cung cấp helper:

```java
logger.logObject("customer", customer);
```

thực hiện reflection/toString trên mọi entity.

Thay bằng event API với fields được định nghĩa trước:

```java
public record PersistenceEvent(
    String operation,
    String result,
    String requestId,
    long durationMs
) {}
```

Logger:

```java
public final class PersistenceEventLogger {

    private static final Logger LOG =
        LoggerFactory.getLogger(
            PersistenceEventLogger.class
        );

    public static void record(
            PersistenceEvent event
    ) {
        LOG.info(
            "operation={} result={} requestId={} durationMs={}",
            event.operation(),
            event.result(),
            event.requestId(),
            event.durationMs()
        );
    }
}
```

### 34.1. Cần validate event fields

`operation` và `result` nên là enum/allowlisted values; `requestId` được validate ở request boundary. Đừng cho callers đặt arbitrary string với payload vào `operation`.

### 34.2. Hạn chế log utility nhận Object hoặc Map tùy ý

`Map<String,Object>` tiện lợi nhưng dễ bị thêm `requestBody`, `entity`, `exception`. Nếu dùng structured logging API, vẫn phải có field schema/allowlist.

### 34.3. Error category do service quyết định

Log `errorCode="PERSISTENCE_CONFLICT"` thay vì raw `ex.toString()`.

### 34.4. Không biến utility thành security boundary duy nhất

Nếu các teams vẫn trực tiếp gọi `log.info("{}", entity)`, cần conventions, code review và regression tests.

---

## 35. Log thông tin kỹ thuật không chứa dữ liệu nghiệp vụ

Những metrics thường hữu ích:

```text
jpa_query_count = 18
jpa_flush_duration_ms = 35
db_connection_wait_ms = 14
orm_entity_load_count = 120
persistence_operation = "order_list"
result_size_bucket = "50-99"
exception_category = "integrity_violation"
sqlstate_class = "23"
```

### 35.1. Số liệu tổng hợp giảm nhu cầu raw SQL

N+1 có thể được nhận diện qua `SELECT count`/trace fingerprint mà không cần giá trị email hay customer address.

### 35.2. Cẩn thận metric labels high-cardinality

Không gắn `email`, user ID hoặc full SQL vào metric labels. Chúng có thể tăng cardinality và vô tình lưu PII trong monitoring.

### 35.3. Query fingerprint thay raw SQL

Normalized fingerprint giúp nhóm các query structures tương tự. Nhưng vẫn cần biết công cụ fingerprint có giữ comments/literals hay không; nếu không có bảo đảm, không coi fingerprint từ raw SQL là đã vô hiệu nguy cơ.

### 35.4. Không log mọi giá trị query parameters để phân tích performance

Có thể log parameter **class** như “hot tenant/medium tenant” nếu được tính từ an toàn và không làm lộ tenant cụ thể. Chỉ lưu các buckets hữu ích.

---

## 36. Truy vấn SQL chứa dữ liệu dù chỉ là SELECT

Đôi khi SQL statement mang literal business value do thiết kế query:

```java
String nativeQuery = """
    select *
    from orders
    where tenant_id = 'tenant-a'
      and customer_email = 'sample.person@example.invalid'
    """;
```

Tắt `org.hibernate.orm.jdbc.bind` không che các literal này vì chúng đã nằm trong SQL text.

### 36.1. Tất cả dynamic data values nên bind

```java
em.createNativeQuery(
    """
    select order_id
    from sales_order
    where tenant_id = ?1
      and customer_email = ?2
    """
)
.setParameter(1, tenant)
.setParameter(2, email)
.getResultList();
```

### 36.2. SQL stored ở named queries vẫn cần review

Named native query có hard-coded literals hoặc vendor-specific comments vẫn có thể lộ thông tin. Không chỉ audit dynamic SQL builders.

### 36.3. Generated SQL từ ORM còn phụ thuộc filters

Tenant/soft-delete filters, row-level security, comments/hints có thể thêm predicates/SQL fragments. Đừng suy luận về log safety từ riêng JPQL string.

---

## 37. Xử lý lỗi DB constraint mà không lộ giá trị trùng

Một database UNIQUE constraint trên email:

```sql
ALTER TABLE customer
ADD CONSTRAINT uk_customer_tenant_email
UNIQUE (tenant_id, email);
```

Service/API cần phản hồi tùy authorization và intent. Có thể phân loại constraint known trong data layer, sau rollback khi cần.

### 37.1. Đừng parse raw DB message để lấy email

Error message có thể chứa full email. Không lấy `ex.getMessage()` rồi đưa vào domain exception.

### 37.2. Cố định error code

```text
CUSTOMER_CONFLICT
```

hoặc dạng cụ thể `EMAIL_ALREADY_USED` **chỉ nếu không tạo user enumeration/cross-tenant disclosure**.

### 37.3. Tránh log exception với toàn bộ SQL/cause chain

Log:

```java
log.warn(
    "event=customer_create outcome=conflict requestId={} category={}",
    requestId,
    "unique_constraint"
);
```

Với incident cần cause chain, dùng restricted diagnostics và quy trình redaction riêng thay vì mọi warning đều in full stack trace.

### 37.4. Tính đúng đắn transaction

`flush`/`commit` có thể phát sinh exception. Sau lỗi SQL transaction có thể rollback-only/aborted. Không tiếp tục dùng cùng persistence context để “thử lại” rồi làm lộ dữ liệu trong những exceptions nối tiếp.

---

## 38. Multi-tenancy: log sai có thể biến lỗi nội bộ thành rò rỉ chéo tenant

Query có thể cần:

```jpql
select c
from Customer c
where c.id = :id
  and c.tenantId = :authorizedTenant
```

Nếu lỗi xảy ra, một log message chứa cả Customer entity của tenant khác có thể tạo kênh lộ mà API đã cố ngăn.

### 38.1. Tenant ID có thể được log không?

Chỉ khi cần, được phân loại đúng và có quyền xem. Có thể log pseudonymous tenant reference để so sánh mà không lộ trực tiếp tenant name.

### 38.2. Không phản hồi “khách hàng thuộc tenant B”

Nếu user tenant A cố truy cập ID của tenant B, một thông báo lỗi quá cụ thể có thể tiết lộ sự tồn tại của data. Chọn 404/403 theo security policy, không dùng DB exception message.

### 38.3. Không tin tenantId do client cung cấp

Log và repository phải sử dụng authorized tenant từ trusted security context; raw header có thể bị giả mạo.

### 38.4. Logging không thay row-level security

Cần authorization/service predicates và DB controls theo architecture. Che log không sửa một SQL query thiếu tenant filter.

---

## 39. Đừng in request/response entity khi cần hỗ trợ khách hàng

Một support team có thể yêu cầu:

> “Chụp log đầy đủ request customer update để debug.”

Một cách an toàn hơn:

- Gửi request ID và timestamp.
- Xác định endpoint template/operation.
- Ghi field names đã thay đổi (nếu được phép), không ghi values.
- Ghi validation error code.
- Ghi transaction outcome và latency.
- Nếu cần xem dữ liệu thực, dùng công cụ support có authorization/audit theo policy, không dùng raw log.

### 39.1. Field changed không luôn vô hại

Một field name kiểu `medicalDiagnosis` có thể lộ loại dữ liệu liên quan. Đánh giá theo domain/security policy.

### 39.2. Không chụp stack trace vào ticket công khai

Các kênh ticket/chat có audience, retention và access controls khác log store. Sanitize trước khi chia sẻ.

### 39.3. Không dùng screenshot log như một cách thoát kiểm soát

Ảnh chụp vẫn là bản sao dữ liệu. Nếu cần chia sẻ, redact và kiểm tra quyền nhận.

---

## 40. Cơ chế redaction: ưu tiên phòng ngừa trước thu thập

Có ba hướng:

1. **Không tạo dữ liệu nhạy cảm trong event** (tốt nhất).
2. **Chỉ chọn fields an toàn** khi tạo event.
3. **Redact/mask** khi không thể tránh được dữ liệu đầu vào (lớp bổ sung).

### 40.1. Regex redaction có giới hạn

Regex tìm email có thể bỏ sót unicode, URL encoded, nested JSON, free text, structured values hoặc tokens không giống email. Một pattern cũng có thể thay sai dữ liệu hợp lệ.

### 40.2. Masking có thể giữ lại quá nhiều

`s***@example.com` vẫn có thể là PII nếu kết hợp với tài khoản, thời gian và các sự kiện khác. Không giả định partial masking biến dữ liệu thành public.

### 40.3. Redact ở gần nguồn

Nếu collector đã nhận raw secret, việc UI dashboard giấu nó không có nghĩa secret không còn trong pipeline/storage. Cố gắng giảm/loại bỏ trước ingest.

### 40.4. Test output trên nhiều sink

Application logger sạch nhưng APM exception event có raw stack trace vẫn là rò rỉ. Kiểm chứng các pipelines được dùng thật.

---

## 41. Retention, xóa log và quyền truy cập

Log cần có chính sách:

| Thành phần | Câu hỏi |
|---|---|
| Retention | Giữ bao lâu, tại sao? |
| Role-based access | Ai xem được SQL/errors/traces? |
| Data export | Ai được tải log ra ngoài? |
| Encryption | Log lưu trữ và vận chuyển được bảo vệ thế nào? |
| Redaction | Thực hiện ở nguồn hay collector? |
| Backup | Có bản sao lâu hơn retention trực tuyến? |
| Incident procedure | Khi leak, cách cô lập và kiểm tra phạm vi? |
| Data subject requests | Các yêu cầu liên quan privacy xử lý thế nào theo policy? |

### 41.1. Không ghi “retention = forever”

Cần thời hạn và lý do. Một log entry có thể mất mục đích chẩn đoán rất lâu trước khi dữ liệu nghiệp vụ liên quan hết thời gian lưu trữ.

### 41.2. Data access phải có nhu cầu

Người có thể deploy ứng dụng không mặc định cần quyền xem toàn bộ database debug logs.

### 41.3. Log audit trail nên được bảo vệ

Trong một số quy trình security, cần ghi ai đã xem/export logs. Cần tránh vòng lặp “audit log lại chứa toàn bộ dữ liệu mà nó đang bảo vệ”.

---

## 42. Kiểm thử rò rỉ bằng dữ liệu canary

Một chiến lược test:

1. Tạo entity test chứa email giả **dễ nhận diện**.
2. Gây một JPA query có parameter bound chứa email đó.
3. Gây validation/persistence failure an toàn trong test.
4. Capture application log output đã cấu hình.
5. Capture API JSON response.
6. Assert email canary không xuất hiện trong các outputs không được phép.

Ví dụ canary:

```text
canary-row434-927@example.invalid
phone-canary-000000
note-canary-sensitive-do-not-log
```

Đây là dữ liệu **giả để kiểm thử**, không phải thông tin người dùng.

### 42.1. Ví dụ assertion ở mức ý tưởng

```java
String logs = testLogCapture.contents();
String responseJson = mvcResult.getResponse()
    .getContentAsString();

assertFalse(
    logs.contains("canary-row434-927@example.invalid")
);
assertFalse(
    logs.contains("note-canary-sensitive-do-not-log")
);
assertFalse(
    responseJson.contains("note-canary-sensitive-do-not-log")
);
```

`testLogCapture` là một test helper cần được cài đặt/khởi tạo trong dự án (ví dụ Logback ListAppender). Đoạn code thể hiện **nguyên tắc kiểm thử** chứ không phải JPA standard API.

### 42.2. Kiểm thử đúng logger configuration

Nếu test dùng logging config khác production, một assertion “không có email trong log” có thể không chứng minh production an toàn. Test cả effective config trong deployment pipeline theo khả năng.

### 42.3. Cần capture exception chain và response

Nếu handler chỉ che top-level message nhưng backend logger in full cause chain, test phải quan sát logger sink thực.

### 42.4. Không dựa vào một canary duy nhất

Dùng email, token-like string, multiline text, JSON nested value, Unicode và long value để phát hiện nhiều đường rò rỉ. Không cần dùng secret thật.

---

## 43. Test Lombok toString và lazy association

Một JUnit test có thể nêu yêu cầu:

```java
@Test
void customerToStringDoesNotIncludeSensitiveFields() {
    Customer customer = customerFixture(
        "canary-row434-927@example.invalid",
        "note-canary-sensitive-do-not-log"
    );

    String output = customer.toString();

    assertFalse(output.contains("example.invalid"));
    assertFalse(output.contains("note-canary"));
}
```

### 43.1. Test không phụ thuộc DB chỉ để kiểm tra format

Nếu entity constructor/fixture hỗ trợ, đây là unit test thuần Java.

### 43.2. Test không kích hoạt lazy SQL

Với EntityManager/SQL recorder, có thể xác minh gọi `toString()` của managed entity không làm tăng SELECT count. Với detached entity, nó không được tự buộc lazy initialization.

### 43.3. Tốt nhất không dựa vào auto-generated toString

Một class thêm field nhạy cảm trong tương lai cần tự động bị loại khỏi logs. Allowlist toString hoặc thậm chí constant type representation giúp giảm regression.

---

## 44. Test API serialization không trả entity ngoài ý muốn

Response DTO:

```java
public record CustomerSummaryResponse(
    Long id,
    String displayName
) {}
```

Test:

```java
String json = objectMapper.writeValueAsString(
    new CustomerSummaryResponse(42L, "Guest")
);

assertFalse(json.contains("internalNote"));
assertFalse(json.contains("email"));
assertFalse(json.contains("deliveryAddress"));
```

### 44.1. Đây là test shape, chưa phải authorization

Cần integration test bảo đảm dữ liệu người dùng tenant A không được truy vấn/trả từ tenant B.

### 44.2. Khi JSON có nested DTOs

Kiểm tra toàn graph. Một nested object do mapper mới thêm có thể đưa PII vào response dù top-level DTO vẫn an toàn.

### 44.3. Không serialize entity vào test rồi “xem có lỗi không” như chiến lược chính

Hãy quy định API trả DTO/specific projection, không expose JPA graph qua framework defaults.

---

## 45. Test lỗi database mà không để error payload bị lộ

Một scenario hữu ích:

- Tạo Customer có email canary trong DB.
- Cố INSERT thêm Customer trùng UNIQUE email.
- Bắt exception ở Spring/JPA boundary.
- Xác nhận transaction rollback.
- Xác nhận public response chỉ có safe code/message.
- Xác nhận application logs không chứa canary email hoặc SQL values.
- Xác nhận correlation ID tồn tại và có thể tra lỗi.

### 45.1. Cùng một exception nhưng nhiều bề mặt

API response có thể sạch nhưng datasource proxy/DB error log vẫn ghi value; test application logs chỉ bao phủ phần có thể quan sát trong test. Cần audit môi trường DB/APM theo policy.

### 45.2. Không bỏ qua commit-time error

Constraint có thể được phát hiện ở flush/commit. Test phải bao gồm transaction boundary thực sự.

### 45.3. Sau lỗi persistence, không tái dùng transaction tùy tiện

Rollback attempt thất bại; dùng context/transaction mới để xác minh DB state.

### 45.4. Đừng ghi raw exception vào test reports được upload công khai

Test frameworks có thể in assertion/error logs lên CI artifacts. Canary là giả, nhưng khi dùng real user data trong tests đây sẽ là rủi ro. Test fixtures phải luôn synthetic/approved.

---

## 46. Kiểm tra cấu hình logger theo phiên bản thư viện

Một change upgrade Hibernate có thể chuyển category bind logger và khiến policy cũ không còn bao quát.

### 46.1. Khi upgrade

- Xác định phiên bản Hibernate ORM, JDBC driver, Spring, log framework.
- Xem effective logging configuration theo môi trường.
- Thử canary bind query trong test.
- Capture logs/traces ở sinks liên quan.
- Kiểm tra có categories mới nào ghi bind/extract values không.
- Xác nhận default log levels không thay ngoài ý muốn.

### 46.2. Không giả định một property đủ cho mọi stack

`spring.jpa.show-sql=false` không điều khiển SQL log của P6Spy, DB slow log, APM hay custom `log.debug`.

### 46.3. Tracing auto-instrumentation là dependency có behavior riêng

Một agent có thể tự instrument JDBC; nâng agent version/config cũng cần review data capture và privacy settings.

---

## 47. Runbook nếu phát hiện PII/secret trong log

Một incident response có thể gồm:

1. **Xác định loại dữ liệu:** PII, token, password, API key hay schema metadata.
2. **Xác định nguồn:** SQL bind logger, entity `toString()`, exception, APM, DB log hay HTTP body.
3. **Containment:** tắt/giới hạn bề mặt thu thập theo procedure được phép.
4. **Hạn chế access:** khóa export/view của log/sink bị ảnh hưởng nếu cần.
5. **Đánh giá phạm vi:** từ thời điểm nào, bao nhiêu records/events, sinks/backups nào nhận dữ liệu.
6. **Thu hồi/rotate secret:** khi credentials/token bị lộ, dùng đúng key/credential rotation policy.
7. **Preserve evidence có kiểm soát:** không xóa bừa dữ liệu phục vụ điều tra nếu policy/yêu cầu pháp lý cần lưu.
8. **Remediation:** sửa logging code/config, exception translation và entity representation.
9. **Validation:** thử canary và kiểm tra logs/traces sau deploy.
10. **Thông báo/escalation:** theo security/privacy incident process, không tự suy đoán nghĩa vụ pháp lý.
11. **Cleanup/retention:** xử lý bản sao/archives theo policy.
12. **Prevention:** thêm regression tests và guardrails.

### 47.1. Không chỉ sửa ứng dụng

Nếu raw values đã được ingest bởi external collector hoặc gửi vào alert email, sửa Java logger không xóa bản sao đã phân phối.

### 47.2. Không công bố incident details trên kênh rộng

Mô tả loại sự cố và mitigation, không paste PII/secret vào ticket chat để minh họa.

---

## 48. Quy trình review khi thêm một field mới vào entity

Ví dụ developer thêm:

```java
@Column(name = "national_identifier")
private String nationalIdentifier;
```

Trước khi merge:

- Trường này có cần persisted không?
- Có ràng buộc privacy nào không?
- Entity `toString()`/Lombok `@Data` có tự include không?
- DTO/JSON serializer có lộ trường không?
- Logs có in entity object không?
- Native SQL statements có chứa literal value không?
- Exceptions/validation messages có include invalid value không?
- APM/DB traces có thể capture binds không?
- Cache/audit/log retention có được xử lý không?
- Có test canary field mới?

### 48.1. Allowlist giảm hậu quả khi thêm field

Nếu mặc định `toString` chỉ in entity type và response DTO chỉ có public fields, thêm field mới ít có nguy cơ tự động làm lộ.

### 48.2. Một annotation không tạo đủ boundary

`@JsonIgnore` có thể hỗ trợ serialization nhưng không quyết định SQL logging, exception messages, APM và database logs.

---

## 49. Tình huống thực tế: lỗi UNIQUE email ở production

**Bối cảnh:** Endpoint POST /customers trả 500 với body chứa `duplicate key value (email)=(...)`.

### 49.1. Điều tra

- Handler có trả `ex.getMessage()` không?
- Global exception config có include-message/stacktrace không?
- Hibernate/JDBC/DB log đang bật categories nào?
- Email value xuất hiện ở application log/APM/DB slow log không?
- Có tenant-scoped uniqueness và authorization đúng không?

### 49.2. Sửa response

Trả safe code như `CUSTOMER_CONFLICT` khi xác định được conflict thuộc business contract và user được phép biết; nếu không, generic error.

### 49.3. Sửa logging

Không in full exception/payload trên warning path. Dùng safe constraint category, request ID, operation code. Với full diagnostics, chỉ mở restricted channel có kiểm soát và masking strategy.

### 49.4. Test regression

Dùng canary email trùng unique; xác nhận response/collected logs sạch và transaction rollback.

---

## 50. Tình huống thực tế: thêm Lombok @Data làm log chứa địa chỉ

**Bối cảnh:** Một refactor chuyển entity sang `@Data`; request log sau đó xuất hiện `deliveryAddress` của khách hàng.

### 50.1. Nguyên nhân

Generated `toString()` giờ đưa nhiều fields vào output. Trước đây logger dùng `log.debug("{}", customer)` nhưng `toString` chỉ in ID.

### 50.2. Sửa đúng

Bỏ `@Data` hoặc định nghĩa `@ToString(onlyExplicitlyIncluded = true)`/toString thủ công. Rà soát `equals/hashCode` và lazy relations.

### 50.3. Không chỉ hạ log level

Hạ INFO→WARN có thể giảm một đường xuất, nhưng helper khác vẫn có thể in entity và bug tái diễn khi production bật debug. Sửa data representation contract.

### 50.4. Kiểm tra bản sao

Lượng PII đã ghi trước khi sửa cần xử lý theo log incident/retention policy.

---

## 51. Tình huống thực tế: APM xuất raw SQL dù Hibernate bind logger OFF

**Bối cảnh:** Application log không chứa bind values, nhưng trace backend có full SQL statement với email.

### 51.1. Những nguồn cần xem

- Query construction có inline email không?
- APM JDBC instrumentation có bind capture?
- Datasource proxy có inlined parameter formatter?
- DB driver trace có bật?
- SQL comments có chứa request payload?

### 51.2. Sửa ở nơi phát sinh

Không chỉ thêm masking regex ở dashboard. Tắt capture/raw value tại instrumentation/ingest; đổi native SQL concatenation sang bind; giới hạn tracing metadata.

### 51.3. Test across sinks

Dùng synthetic canary query, xác nhận không xuất hiện ở application logs lẫn APM traces và exported events theo khả năng quan sát.

---

## 52. Bài tập thực hành có gợi ý

### Bài 1 — SQL và bind values

SQL log chỉ có `WHERE email=?`. Có chắc email không bị log không?

**Gợi ý:** Không; bind logger, JDBC proxy hoặc DB tools có thể ghi values.

### Bài 2 — PreparedStatement

Bind parameters có giúp chống SQL injection không? Có tự làm log an toàn không?

**Đáp án:** Có cho một lớp injection khi dùng đúng; không bảo đảm log secrecy.

### Bài 3 — Hibernate show_sql

Vì sao tránh `hibernate.show_sql=true` mặc định trong production?

**Gợi ý:** SQL có thể ra stdout ngoài filtering chuẩn, gây exposure và overhead.

### Bài 4 — Hibernate 6

Logger category thường dùng cho JDBC binds?

**Gợi ý:** `org.hibernate.orm.jdbc.bind`, nhưng verify theo version.

### Bài 5 — Hibernate 5

Một logger bind category lịch sử?

**Gợi ý:** `org.hibernate.type.descriptor.sql.BasicBinder`.

### Bài 6 — format_sql

`hibernate.format_sql=true` có che PII không?

**Đáp án:** Không, chỉ formatting.

### Bài 7 — Native SQL concatenation

Vì sao SQL chứa email literal nguy hiểm hơn một vấn đề logging?

**Gợi ý:** SQL injection và literal exposure.

### Bài 8 — SQL comments

Gắn customer email vào SQL comment để trace request có an toàn không?

**Đáp án:** Không; comments có thể đến DB/APM/logs.

### Bài 9 — Exception message

Có nên trả `ex.getMessage()` trực tiếp từ `DataIntegrityViolationException` không?

**Đáp án:** Không; có thể chứa SQL/constraint/data.

### Bài 10 — JPA vs JDBC

`EntityExistsException` và `SQLException` thuộc cùng lớp exception không?

**Gợi ý:** Không; JPA provider có thể wrap JDBC errors.

### Bài 11 — Bean Validation

`violation.getInvalidValue()` có thể chứa gì?

**Gợi ý:** Email/token/PII từ input.

### Bài 12 — Constraint names

Có nên gửi `uk_customer_tenant_email` trong public API error không?

**Gợi ý:** Không cần; map sang application code.

### Bài 13 — Conflict status

Có nên trả 409 cho mọi `DataIntegrityViolationException` không?

**Đáp án:** Không; có FK/NOT NULL/CHECK và lỗi khác.

### Bài 14 — Global handler

`ProblemDetail.setDetail(ex.getMessage())` có an toàn không?

**Đáp án:** Không với untrusted persistence exceptions.

### Bài 15 — Lombok @Data

Có nguy cơ gì khi dùng `@Data` cho JPA entity có PII và lazy collection?

**Gợi ý:** toString/equals/hashCode có thể in PII, traverse graph, tạo SQL và recursion.

### Bài 16 — toString allowlist

Tại sao `@ToString(onlyExplicitlyIncluded=true)` an toàn hơn auto-all-fields?

**Gợi ý:** Field mới không tự xuất hiện.

### Bài 17 — @ToString.Exclude

Có nên chỉ exclude email mà quên phone/address không?

**Đáp án:** Không; blacklist dễ bỏ sót.

### Bài 18 — Entity lazy loading

Vì sao `log.debug("{}", entity)` có thể tăng query count?

**Gợi ý:** toString truy cập association lazy.

### Bài 19 — @JsonIgnore

Có làm Hibernate bind logger ngừng log field không?

**Đáp án:** Không.

### Bài 20 — DTO

Controller trả `CustomerPublicResponse(id,displayName)` giúp gì?

**Gợi ý:** Allowlist response fields, tránh entity serialization.

### Bài 21 — Record toString

Một record request có `email`/`phone`, log nguyên record có an toàn không?

**Gợi ý:** Không; record toString thường in components.

### Bài 22 — Correlation ID

Có nên dùng email làm request correlation key?

**Đáp án:** Không; dùng opaque ID.

### Bài 23 — Untrusted request ID

Client gửi request ID chứa newline và chuỗi rất dài.

**Gợi ý:** Validate length/charset, có thể tạo lại.

### Bài 24 — MDC

Tại sao cần `MDC.remove("requestId")` trong finally?

**Gợi ý:** Thread reuse/cross-request contamination.

### Bài 25 — Log forging

SLF4J placeholder có tự loại newline trong user input không?

**Đáp án:** Không bảo đảm; validate/encode hoặc không log input.

### Bài 26 — Hash email

SHA-256(email) không secret có đủ tránh membership guessing không?

**Gợi ý:** Không; có thể dictionary attack.

### Bài 27 — HMAC

HMAC pseudonym có hoàn toàn anonymous không?

**Đáp án:** Không; vẫn linkable, cần key/retention controls.

### Bài 28 — Secret key

HMAC key có nên hard-code trong entity? 

**Đáp án:** Không; dùng secret management.

### Bài 29 — Converter encryption

`@Convert` mã hóa field khi persist; `toString` có còn thể lộ plaintext không?

**Gợi ý:** Có; Java field vẫn có plaintext.

### Bài 30 — Database log

Tắt `org.hibernate.SQL` có tắt PostgreSQL slow query log không?

**Đáp án:** Không; hai tầng khác nhau.

### Bài 31 — APM

Agent tự capture SQL values. Có nên chỉ mask khi render dashboard?

**Gợi ý:** Không; cần hạn chế capture/ingest.

### Bài 32 — Audit log

Audit “customer address updated” có nhất thiết lưu toàn bộ địa chỉ mới/cũ không?

**Đáp án:** Không, trừ khi policy/use case thực sự yêu cầu và có controls phù hợp.

### Bài 33 — Log retention

Vì sao log giữ lâu có rủi ro khác DB?

**Gợi ý:** Bản sao/collector/alert/archive giữ data ngoài lifecycle nghiệp vụ.

### Bài 34 — Test canary

Thiết kế test với `canary-row434-927@example.invalid` để phát hiện điều gì?

**Gợi ý:** Email xuất hiện trong logs, traces hoặc API response ngoài ý muốn.

### Bài 35 — Test exception

Unique constraint lỗi ở commit thay vì persist. Test nên bao gồm gì?

**Gợi ý:** Transaction boundary thực và response/log capture sau commit failure.

### Bài 36 — Test new entity field

Sau khi thêm `nationalIdentifier`, những bề mặt nào cần rà soát?

**Gợi ý:** toString, JSON DTO, exceptions, SQL bind logs, APM và retention.

### Bài 37 — Log metrics

N+1 cần đo SQL count; có cần log mọi email bind value không?

**Đáp án:** Không.

### Bài 38 — Tenant scope

Log raw tenant ID cùng customer email có thể gây rủi ro gì?

**Gợi ý:** Cross-tenant privacy/correlation; áp minimize/pseudonymization/authorization.

### Bài 39 — Production debugging

Khi cần tăng debug, có nên bật TRACE toàn Hibernate không giới hạn?

**Đáp án:** Không; dùng category/scope/duration/approval rõ.

### Bài 40 — Security incident

Phát hiện API key trong log collector. Chỉ tắt logger là đủ chưa?

**Gợi ý:** Chưa; cần contain, rotate/revoke, evaluate sinks/backups và response procedure.

---

## 53. Checklist code review và triển khai

Trước khi merge một thay đổi JPA hoặc logging:

- [ ] Đã liệt kê entity fields có PII, secrets hoặc dữ liệu nội bộ.
- [ ] Không log nguyên entity/request DTO/response DTO.
- [ ] `toString()` của entity có allowlist và không đọc lazy relations.
- [ ] Không dùng Lombok `@Data` không kiểm soát trên entities.
- [ ] Java record request không bị in toàn bộ components.
- [ ] `equals/hashCode` không traverse relation và có semantics JPA phù hợp.
- [ ] Controller không trả nguyên JPA entity khi cần giới hạn fields.
- [ ] Response DTO chỉ có thông tin được authorized.
- [ ] Tenant/authorization predicates không bị bỏ.
- [ ] Hibernate `show_sql` tắt theo production policy.
- [ ] Hibernate SQL/bind/extract log levels được kiểm tra theo version.
- [ ] JDBC driver/proxy/APM capture settings đã được rà soát.
- [ ] Database-side SQL/error/audit logs có retention/access policy.
- [ ] Native SQL sử dụng parameters thay vì nối literal input.
- [ ] Không dùng email/token trong SQL comments/query labels.
- [ ] Không có raw JDBC URL/credentials/config dumps.
- [ ] Không có request body/token/header dumps trong diagnostics.
- [ ] Exception response không trả raw `ex.getMessage()` hoặc stack trace.
- [ ] Domain error code ổn định và không lộ constraint/schema details.
- [ ] `DataIntegrityViolationException` được phân loại cẩn thận; không xem mọi lỗi là trùng.
- [ ] Validation failures không log invalid values/root beans.
- [ ] Không log nested exception chain vào broad-access sink.
- [ ] Operational logs dùng structured allowlist fields.
- [ ] Request ID được validate và không chứa user data.
- [ ] MDC được dọn dẹp trong finally và propagate đúng async context.
- [ ] Không đặt user input vào dynamic log keys/metric labels.
- [ ] Có chống control-character/log injection khi log text từ ngoài.
- [ ] Nếu dùng HMAC pseudonym, key được quản lý/rotate đúng và có mục đích.
- [ ] Mã hóa storage không bị xem nhầm thành log protection.
- [ ] Audit data có mục đích, schema, quyền và retention riêng.
- [ ] Có test canary cho entity, exception, serializer và logs.
- [ ] Có kiểm tra thực tế ở log/trace sinks quan trọng.
- [ ] Có runbook time-limited diagnostics và incident containment.
- [ ] Có monitoring config drift sau dependency/provider upgrades.

## 54. Bảng tra cứu nhanh

| Câu hỏi | Trả lời thực dụng |
|---|---|
| Log `org.hibernate.SQL` chứa gì? | SQL statement text, có thể có literals |
| Hibernate 6 bind logger? | Thường `org.hibernate.orm.jdbc.bind` |
| Hibernate 5 bind logger? | Thường `org.hibernate.type.descriptor.sql.BasicBinder` |
| `hibernate.show_sql` trong production? | Tránh bật mặc định |
| `format_sql` có redact không? | Không |
| SQL parameter binding có che khỏi log không? | Không bảo đảm |
| Native SQL nối email? | Tránh; injection và log leak |
| JDBC proxy có thể log binds? | Có, tùy tool/config |
| Database slow log có thể chứa query? | Có |
| Tắt Hibernate SQL logger đủ? | Không |
| Exception `getMessage()` an toàn? | Không mặc định |
| Return raw SQL error ra API? | Không |
| `DataIntegrityViolationException` luôn duplicate? | Không |
| Validation invalidValue có log được? | Không mặc định |
| `@JsonIgnore` chặn toString? | Không |
| Lombok `@Data` cho JPA entity? | Rủi ro; tránh dùng không kiểm soát |
| `@ToString(onlyExplicitlyIncluded=true)`? | Allowlist fields |
| toString đọc LAZY relation? | Tránh |
| Record request toString chứa PII? | Có thể |
| REST có nên trả entity? | Ưu tiên DTO allowlist |
| SQL bind tracing phục vụ N+1? | SQL count/fingerprint thường đủ |
| SQLState/constraint category có dùng được? | Có kiểm soát, không gửi raw details |
| Correlation ID là gì? | Opaque request/operation reference |
| MDC cần cleanup? | Có, finally |
| Log user input có newline? | Cần tránh/validate/encode |
| SHA-256(email) là anonymous? | Không đáng tin |
| HMAC subject key? | Pseudonymous, quản lý secret key |
| Encryption converter có bảo vệ mọi log? | Không |
| Audit có cần entity snapshot? | Chỉ khi có yêu cầu cụ thể |
| APM capture bind values? | Phải kiểm tra/giới hạn |
| Retention áp dụng ở đâu? | App, collector, alerts, exports, backups |
| Test log safety? | Synthetic canary + capture sinks |
| Production debug? | Bật phạm vi nhỏ, có thời hạn/quyền |
| Secret lộ trong log? | Contain, rotate/revoke, xử lý incident |
| Nguồn thiết kế quan trọng nhất? | Data minimization + allowlist |

## 55. Tổng kết

Những nguyên tắc quan trọng nhất:

1. **JPA entity không nên là một logging payload.** `toString()`, Lombok `@Data` và serializer có thể làm lộ toàn bộ fields/associations.
2. **SQL statement logging và bind value logging là hai bề mặt khác nhau**; tắt một logger không đồng nghĩa mọi values được bảo vệ.
3. **Bind parameters giúp chống SQL injection nhưng không che bind values trong diagnostics** nếu provider/JDBC/APM được cấu hình capture chúng.
4. **Native SQL nối raw values là nguy cơ kép**: injection và literal exposure trong query logs/exception.
5. **Database, driver, proxy, APM và log collectors cần được kiểm tra độc lập**, không chỉ Spring/Hibernate settings.
6. **Exception messages/cause chains không phải nội dung API an toàn**, đặc biệt với constraint errors có thể chứa rejected values.
7. **Phân loại lỗi bằng application codes ổn định** và chỉ trả message đã được phép công khai.
8. **Bean Validation invalid values và root beans không nên được log theo mặc định**.
9. **DTO projection/response DTO theo allowlist** giới hạn dữ liệu được hydrate/trả ra khi use case chỉ cần vài fields; nhưng vẫn cần authorization.
10. **Structured event logging và data minimization** hiệu quả hơn dump entity rồi cố mask bằng regex.
11. **Correlation ID, pseudonymization và audit log có mục tiêu khác nhau**; không dùng email làm request ID hoặc coi hash email là ẩn danh hoàn toàn.
12. **MDC và input validation** cần được xử lý để tránh cross-request contamination, log injection và high-cardinality telemetry.
13. **Encryption ở storage/AttributeConverter không thay log policy**, vì plaintext có thể xuất hiện trước khi được mã hóa.
14. **Kiểm thử canary qua log, exception và JSON** giúp ngăn regression khi thay entity fields, logging libraries hoặc provider versions.
15. **Production troubleshooting phải được giới hạn phạm vi, thời gian và quyền**, và một leak đã xảy ra cần containment, rotation khi có secrets và xử lý các bản sao theo incident policy.

**Kết luận:** Bảo mật dữ liệu trong JPA không dừng ở việc thêm `@JsonIgnore` hay tắt một dòng DEBUG. Một ứng dụng an toàn phải kiểm soát **dữ liệu nào rời khỏi entity, qua đường nào và được giữ ở đâu**: SQL/bind diagnostics, nested exceptions, object representations, REST DTOs, tracing, database logs và audit stores. Khi sử dụng allowlist fields, không log raw objects, tránh in SQL parameters, thiết kế error responses an toàn và kiểm thử bằng synthetic canaries, hệ thống vẫn giữ được khả năng điều tra lỗi và đo hiệu năng mà không biến telemetry thành một nguồn rò rỉ thông tin nhạy cảm.
