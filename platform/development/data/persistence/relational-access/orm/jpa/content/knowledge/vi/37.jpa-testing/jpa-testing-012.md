# Dùng hệ quản trị thật trong container khi cần hành vi tương đương

Trong **Jakarta Persistence (JPA)**, một bài kiểm thử dùng database in-memory có thể chạy xanh nhưng ứng dụng lại lỗi khi triển khai trên PostgreSQL, MySQL, Oracle hoặc SQL Server. Nguyên nhân không nhất thiết nằm ở entity Java. Nó có thể đến từ **SQL dialect, kiểu dữ liệu, cấu trúc schema, ràng buộc, collation, transaction isolation, locking, ID generation và hành vi của driver**.

Ví dụ, một entity lưu thuộc tính JSON vào cột PostgreSQL `jsonb` có thể chạy đúng trên PostgreSQL thật nhưng không thể xác nhận đầy đủ bằng H2 compatibility mode. Một test kiểm tra `@Version` hoặc `PESSIMISTIC_WRITE` trên database giả lập cũng có thể bỏ sót hành vi khóa mà DBMS production sẽ sử dụng.

Vì thế, khi yêu cầu là **hành vi tương đương với database đang triển khai**, cách thực dụng là chạy **chính hệ quản trị cơ sở dữ liệu đó trong một container cô lập** và cho JPA integration tests kết nối tới nó. Trong Java, **Testcontainers** là một thư viện phổ biến giúp tổ chức quy trình này từ JUnit và các framework kiểm thử.

> **Nguyên tắc:** Chọn database test dựa trên **điều cần chứng minh**, không dựa trên việc database nào khởi động nhanh nhất. In-memory DB phù hợp với một số bài kiểm tra nhanh; database thật trong container phù hợp khi hành vi DBMS ảnh hưởng đến tính đúng đắn. Container làm tăng độ tương đồng với production, nhưng **không tự tạo ra production parity hoàn toàn**.

Bài học thuộc chương **Kiểm thử JPA** của module **Data Persistence Relational Access ORM JPA**. Nội dung trình bày lý do cần database thật, cách chọn mức độ kiểm thử, cấu hình Testcontainers với Java SE/JUnit và Spring Data JPA, chạy migrations, kiểm tra mapping/constraints/query, transaction và concurrency, quản lý container trong CI, xử lý độ ổn định, đồng thời phân biệt “cùng DBMS” với “cùng điều kiện vận hành”.

---

## 1. Trước hết: thế nào là hành vi tương đương?

Hai hệ quản trị cùng hỗ trợ JDBC và SQL không có nghĩa chúng luôn hành xử như nhau. **Hành vi tương đương** nên được hiểu theo một tập yêu cầu quan sát được của ứng dụng.

Ví dụ, nếu production dùng PostgreSQL 16, bài kiểm thử JPA có thể muốn xác nhận:

- Mapping `BigDecimal` thành `NUMERIC(14, 2)` không làm mất độ chính xác ngoài chính sách đã định.
- `@Enumerated(EnumType.STRING)` được ghi/đọc theo kiểu và collation mong muốn.
- Foreign key và unique constraints có hiệu lực trên schema do migrations tạo.
- Native SQL có `jsonb` hoặc `ON CONFLICT` thực thi đúng.
- JPQL `JOIN FETCH` và pagination sinh SQL tương thích dialect.
- `@Version` phát hiện cập nhật dựa trên version cũ.
- `PESSIMISTIC_WRITE` tạo hành vi lock và timeout hợp lệ.
- Transaction khác không đọc được uncommitted changes nếu policy/database isolation không cho phép.
- Timestamp, timezone, case sensitivity và index behavior phù hợp.

Đây là những mục tiêu khác nhau; test suite nên nói rõ mục tiêu nào đang được chứng minh.

### 1.1. Tính tương đương có nhiều chiều

| Chiều so sánh | Câu hỏi | Container cùng DBMS giúp gì? |
| --- | --- | --- |
| **SQL dialect** | SQL do provider sinh có chạy được? | Rất hữu ích |
| **Kiểu dữ liệu** | JSON, UUID, DATE, NUMERIC có đúng? | Rất hữu ích |
| **Schema/constraints** | FK, UNIQUE, CHECK, index có hoạt động? | Rất hữu ích nếu chạy migrations thật |
| **Transaction/locking** | Isolation, deadlock, timeout có đúng? | Hữu ích với test nhiều connections |
| **Driver/JDBC** | Parameter binding, generated keys, batching? | Hữu ích nếu dùng đúng driver/config |
| **Performance** | Query có cùng p95 ở production không? | Chỉ phản ánh một phần |
| **Hạ tầng** | Replication, failover, proxies, TLS, pool? | Không tự tương đương |
| **Khối lượng dữ liệu** | Plan với 100 triệu rows có đúng? | Không nếu container chỉ có vài rows |
| **Bảo mật vận hành** | Roles, grants, RLS, secrets? | Cần cấu hình riêng để test |

Cùng một database image chỉ giải quyết **một số** yếu tố trong bảng.

### 1.2. “Chạy đúng” và “chạy nhanh” là hai kết luận

Một integration test xác nhận rằng câu JPQL chạy và trả dữ liệu đúng. Nó chưa chắc chứng minh câu SQL có performance tương đương production.

Để đánh giá performance cần thêm dữ liệu, index statistics, kích thước máy, cấu hình DB, concurrency, network và cache state. Container integration test trước hết là một công cụ kiểm tra **tính đúng đắn và khả năng tương thích hành vi**.

## 2. Vì sao H2/in-memory DB có thể tạo test xanh giả?

H2, HSQLDB, Derby và các database nhẹ vẫn có giá trị. Nhưng nếu production dùng một DBMS khác, chúng có thể khác về:

- SQL dialect và các function.
- `IDENTITY`, sequence, auto-increment.
- Kiểu `UUID`, `JSON`, `JSONB`, arrays, enum và timestamp.
- Quy tắc ép kiểu tự động.
- Kiểu dữ liệu boolean.
- Độ dài string, precision và scale.
- Chữ hoa/chữ thường, quoting và reserved words.
- Collation và cách so sánh chuỗi.
- Unique constraint với `NULL`.
- Deferred constraints, CHECK và foreign key.
- Isolation level, locking và deadlocks.
- Transactional DDL.
- Optimizer, execution plan và indexes.
- Stored procedures và native SQL.
- Cách JDBC driver trả generated keys.

### 2.1. Compatibility mode không biến H2 thành PostgreSQL

Ví dụ:

```properties
spring.datasource.url=jdbc:h2:mem:testdb;MODE=PostgreSQL
```

Chế độ tương thích có thể giúp hỗ trợ một số cú pháp/ngữ nghĩa, nhưng nó **không chạy engine PostgreSQL**.

Đặc biệt, những tính năng như `jsonb` operators, row-level security, PostgreSQL locking và execution planner cần kiểm thử trên PostgreSQL thật nếu chúng là một phần contract của ứng dụng.

### 2.2. Cùng JPQL vẫn có SQL khác nhau

JPA provider có thể chuyển:

```jpql
SELECT p
FROM Product p
WHERE p.active = true
ORDER BY p.id
```

thành SQL khác theo dialect:

```text
JPQL
   |
   +-- Hibernate + H2 dialect -> SQL for H2
   |
   +-- Hibernate + PostgreSQL dialect -> SQL for PostgreSQL
   |
   +-- EclipseLink + Oracle platform -> SQL for Oracle
```

Một test H2 có thể xác nhận một con đường SQL khác production.

### 2.3. Native queries thường là tín hiệu mạnh

Nếu code chứa:

```sql
SELECT id
FROM events
WHERE payload @> '{"type":"PAYMENT"}'::jsonb;
```

đó là cú pháp PostgreSQL-specific. H2 không phải môi trường xác nhận tương đương cho behavior này.

### 2.4. Có nên loại bỏ H2 hoàn toàn không?

Không nhất thiết. Có thể phân tầng:

- Unit tests thuần Java không cần database.
- JPA smoke tests nhanh có thể dùng in-memory DB, nếu mục tiêu giới hạn và chấp nhận khác biệt.
- Database contract/integration tests dùng DBMS đích trong container.
- Performance/failover/replication tests dùng môi trường thích hợp khác.

**Không biến một công cụ nhanh thành nguồn bảo đảm duy nhất cho sản phẩm production.**

## 3. Khi nào nên chọn DBMS thật trong container?

Những trường hợp đặc biệt nên dùng:

1. Có **native SQL** hoặc database functions đặc thù.
2. Dự án dùng **Flyway/Liquibase migrations** cần xác nhận chạy được trên DBMS mục tiêu.
3. Mapping chứa **JSON/JSONB, UUID, ARRAY, enum, custom types, sequences**.
4. Cần kiểm tra **FK, UNIQUE, CHECK, generated columns, partial indexes**.
5. Có **concurrency**, optimistic/pessimistic locking hoặc transaction isolation.
6. Có logic phụ thuộc **collation, timezone, decimal precision**.
7. Có **schema/catalog** hoặc identifier quoting nhạy cảm.
8. Cần xác nhận provider-generated SQL tương thích driver/dialect.
9. Cần kiểm thử **stored procedures, views, triggers**.
10. Hệ thống đã từng gặp lỗi chỉ xuất hiện ở production DB.
11. Muốn test **schema được migrations tạo** thay vì schema JPA tự sinh.
12. Muốn xác nhận code trước một lần nâng version provider/driver/DBMS.

### 3.1. Khi nào container là quá mức?

Một pure domain test:

```java
@Test
void subtotalIsQuantityTimesPrice() {
    OrderLine line = new OrderLine(
        3,
        new BigDecimal("19.50")
    );

    assertEquals(
        new BigDecimal("58.50"),
        line.subtotal()
    );
}
```

không cần khởi động PostgreSQL. Chạy database thật chỉ làm test chậm hơn mà không tăng được tính chắc chắn cho phép tính thuần Java.

### 3.2. Phân loại theo câu hỏi

| Câu hỏi kiểm thử | Lựa chọn phù hợp |
| --- | --- |
| Domain method tính đúng không? | Unit test |
| Mapping cơ bản có bootstrap không? | JPA test nhanh hoặc DB thật |
| PostgreSQL `jsonb` query chạy không? | PostgreSQL container |
| UNIQUE và FK trong migration có thật không? | DBMS container + migration |
| Hai transactions có conflict đúng không? | DBMS thật + 2 connections |
| API response/policy đúng không? | Web/service integration, có thể kết hợp DB |
| SQL p99 có đủ nhanh với 50 triệu rows? | Benchmark môi trường gần production |
| Replica lag/failover có đúng không? | Test topology riêng, không chỉ một DB container |

## 4. Testcontainers làm việc như thế nào?

**Testcontainers** là thư viện Java quản lý các containers phục vụ test, thường thông qua Docker-compatible container runtime.

Một mô hình:

```text
JUnit test JVM
       |
       v
Testcontainers library
       |
       v
Container runtime (Docker-compatible)
       |
       v
PostgreSQL container (isolated test database)
       |
       +---- ephemeral port exposed to host
       |
       v
JDBC DataSource
       |
       v
JPA provider (Hibernate/EclipseLink/...)
       |
       v
EntityManager / Repositories / Integration tests
```

Testcontainers có thể:

- Tạo và khởi động container.
- Chờ service sẵn sàng theo cơ chế hỗ trợ.
- Lấy JDBC URL/username/password được cấu hình.
- Quản lý dừng/xóa container theo lifecycle test thông thường.
- Gắn với JUnit 5 extension hoặc quản lý programmatically.

### 4.1. Một container không phải “database giả”

Nếu image là PostgreSQL, SQL thực thi bởi **engine PostgreSQL bên trong container**, không phải H2 chỉ bắt chước cú pháp.

### 4.2. Điều kiện để chạy

Máy developer hoặc CI runner cần có container runtime tương thích và quyền giao tiếp với daemon. Trên Windows, môi trường Docker Desktop/WSL2 thường phải được cấu hình phù hợp. Nếu daemon không khả dụng, test dựa vào Testcontainers có thể không khởi động được.

### 4.3. Network và cổng

Container thường expose một port trong container, còn Testcontainers cung cấp **host/port đã được ánh xạ động**.

Không hard-code:

```text
localhost:5432
```

trừ khi test setup của bạn thực sự cố định cổng đó. Sử dụng JDBC URL do container cung cấp để tránh xung đột với PostgreSQL local hoặc tests chạy song song.

### 4.4. Container lifecycle

```text
Before tests:
  Start PostgreSQL image
  Wait until ready
  Create datasource
  Apply schema migrations

During tests:
  Run JPA operations
  Assert DB behavior

After tests:
  Close EntityManagerFactory
  Stop/remove disposable container
```

Vòng đời thực tế có thể là per-class, per-suite hoặc theo một container manager khác; hãy chọn để tránh tests rò rỉ trạng thái.

## 5. Chọn phiên bản Testcontainers và DBMS có chủ đích

Các examples dưới đây dùng API phổ biến của **Testcontainers Java 1.x** cho PostgreSQL:

```java
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
```

Các major versions mới của Testcontainers có thể thay đổi module artifact, package hoặc API. Khi tích hợp thực tế, **kiểm tra tài liệu của đúng version đã khóa trong build**, không sao chép imports của ví dụ qua major version khác mà không đối chiếu.

### 5.1. Pin image version

Ví dụ:

```java
new PostgreSQLContainer<>("postgres:16.6");
```

Đây là image tag **minh họa**. Chọn patch version được dự án kiểm soát và có sẵn trong registry.

Không dùng `postgres:latest` cho test đòi hỏi reproducibility. Tag `latest` có thể đổi engine version qua các lần chạy.

### 5.2. Khi cần reproducibility mạnh hơn

Có thể pin image digest trong môi trường có chính sách image artifact phù hợp, và quản lý mirror/registry thay vì kéo image công khai tùy ý.

### 5.3. Pin đồng bộ nhiều phiên bản

Ghi rõ:

- PostgreSQL major/minor version.
- JDBC driver version.
- JPA provider/version.
- Testcontainers version.
- Java runtime.
- Schema migration tool version.
- Application properties ảnh hưởng SQL, timezone, encoding, isolation.

Một test thất bại sau upgrade có thể bắt nguồn từ **bất cứ thành phần nào** trong chuỗi này.

## 6. Dự án ví dụ: Catalog với PostgreSQL

Ta xây một mô hình đủ nhỏ để kiểm tra nhưng có những đặc điểm DB thật:

```text
Category
  id, code, name
       |
       | 1
       v
Product
  id, sku, price, category_id, version
       |
       v
AuditEvent
  id, payload JSONB, occurred_at
```

Ứng dụng cần xác nhận:

- SKU duy nhất trong database.
- Price không âm.
- Product trỏ tới Category hợp lệ.
- `@Version` xử lý stale updates.
- Audit event dùng PostgreSQL JSONB.
- DDL đến từ migrations chứ không được JPA tự tạo lại mỗi lần start.

### 6.1. Category entity

```java
package com.example.catalog.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "categories")
public class Category {

    @Id
    private Long id;

    @Column(name = "code", nullable = false, length = 40)
    private String code;

    @Column(name = "name", nullable = false, length = 160)
    private String name;

    protected Category() {}

    public Category(Long id, String code, String name) {
        this.id = id;
        this.code = code;
        this.name = name;
    }

    public Long getId() { return id; }
    public String getCode() { return code; }
    public String getName() { return name; }
}
```

### 6.2. Product entity

```java
package com.example.catalog.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @SequenceGenerator(
        name = "product_id_generator",
        sequenceName = "product_id_seq",
        allocationSize = 1
    )
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "product_id_generator"
    )
    private Long id;

    @Column(name = "sku", nullable = false, length = 50)
    private String sku;

    @Column(
        name = "price",
        nullable = false,
        precision = 14,
        scale = 2
    )
    private BigDecimal price;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "category_id", nullable = false)
    private Category category;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    protected Product() {}

    public Product(
            String sku,
            BigDecimal price,
            Category category) {

        this.sku = sku;
        this.price = price;
        this.category = category;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public BigDecimal getPrice() { return price; }
    public Category getCategory() { return category; }
    public Long getVersion() { return version; }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Price must not be negative"
            );
        }
        price = newPrice;
    }
}
```

### 6.3. Vì sao mapping chưa đủ?

Các annotations thể hiện mapping intent. Chúng **không chứng minh** database đang dùng có `UNIQUE(sku)`, `CHECK(price >= 0)` hay sequence `product_id_seq`. Cần chạy schema migrations thật và kiểm tra constraints.

## 7. Migrations PostgreSQL để tạo schema

Ví dụ migration SQL:

```sql
CREATE TABLE categories (
    id BIGINT PRIMARY KEY,
    code VARCHAR(40) NOT NULL,
    name VARCHAR(160) NOT NULL,
    CONSTRAINT uq_category_code UNIQUE (code)
);

CREATE SEQUENCE product_id_seq
    START WITH 1
    INCREMENT BY 1;

CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(50) NOT NULL,
    price NUMERIC(14, 2) NOT NULL,
    category_id BIGINT NOT NULL,
    version BIGINT NOT NULL,

    CONSTRAINT uq_product_sku UNIQUE (sku),
    CONSTRAINT fk_product_category
        FOREIGN KEY (category_id)
        REFERENCES categories(id),
    CONSTRAINT ck_product_price
        CHECK (price >= 0)
);

CREATE INDEX idx_product_category
    ON products(category_id);

CREATE TABLE audit_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_audit_payload
    ON audit_events USING GIN (payload);
```

Đây là một **migration minh họa cho PostgreSQL**. Khi xây pipeline thực tế, đặt file trong thư mục migrations được công cụ lựa chọn quản lý, có phiên bản và review, ví dụ Flyway `V1__create_catalog.sql`. Nếu chia nhiều files, mỗi file cần phù hợp thứ tự phụ thuộc.

### 7.1. Vì sao schema này cần PostgreSQL để test?

- `JSONB` và GIN index có ý nghĩa PostgreSQL-specific.
- `TIMESTAMPTZ` có semantics PostgreSQL.
- Sequence và ID strategy phải khớp.
- Ràng buộc `CHECK` và `UNIQUE` cần kiểm tra trên DB thực.
- Query native JSONB cần chính engine PostgreSQL.

### 7.2. Tắt schema generation của JPA khi test migrations

Trong persistence unit hoặc runtime overrides:

```properties
jakarta.persistence.schema-generation.database.action=none
```

Nếu dùng Hibernate-specific validation:

```properties
hibernate.hbm2ddl.auto=validate
```

thì `validate` là một tính năng của Hibernate, không phải action schema generation chuẩn JPA. Có thể dùng để phát hiện một số schema mismatches, nhưng không thay thế constraints/behavior integration tests.

### 7.3. Tránh hai schema owners

Không vừa chạy Flyway migrations, vừa cho JPA `drop-and-create` trên cùng test database nếu mục tiêu là xác nhận schema production.

```text
Correct:
  Fresh PostgreSQL DB
    -> Flyway/Liquibase migrations
    -> Hibernate/JPA runtime (no schema create/drop)
    -> integration tests

Wrong for migration contract:
  Fresh PostgreSQL DB
    -> migrations
    -> JPA drop-and-create
    -> tests
```

Trường hợp sai có thể xóa schema vừa được migration tạo và che lỗi migration.

## 8. Khai báo dependencies cho Testcontainers

Với Maven hoặc Gradle, cần các nhóm dependencies tương ứng:

- JUnit Jupiter.
- Testcontainers core/JUnit Jupiter integration.
- Testcontainers PostgreSQL module.
- PostgreSQL JDBC driver.
- Jakarta Persistence API.
- JPA provider như Hibernate hoặc EclipseLink.
- Flyway hoặc Liquibase nếu test migrations.
- Spring Boot Test nếu dùng Spring.

Ví dụ **Gradle Kotlin DSL mang tính định hướng** theo module organization của Testcontainers 1.x:

```kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter")

    testImplementation(
        "org.testcontainers:junit-jupiter:<tc-version>"
    )
    testImplementation(
        "org.testcontainers:postgresql:<tc-version>"
    )

    testRuntimeOnly("org.postgresql:postgresql:<jdbc-version>")
}
```

Các placeholder `<tc-version>` và `<jdbc-version>` phải thay bằng version/constraints thật theo dependency management của dự án. Không xem fragment này là build script đầy đủ: còn cần plugin, repositories, JPA provider, test runner và application dependencies.

### 8.1. Testcontainers major versions có thể đổi artifact

Trong một stack dùng Testcontainers 2.x hoặc mới hơn, artifact/module naming và package imports có thể khác so với ví dụ 1.x. Hãy dựa vào **version đang được build khóa** thay vì trộn API hai major versions.

### 8.2. Vì sao không dùng version động?

`latest.release` hoặc image `latest` làm tests khó lặp lại giữa developer và CI. Một kết quả xanh hôm nay có thể đổi mà source không đổi.

### 8.3. JDBC driver là một phần contract

Mặc dù chạy đúng engine PostgreSQL, JDBC driver khác version vẫn có thể khác behavior về generated keys, timezone, JSON binding hoặc batching. Với mục tiêu tương đồng production, pin driver phù hợp.

## 9. JUnit 5 + Testcontainers: khung test

Ví dụ dưới đây dùng **Testcontainers 1.x** và JUnit 5.

```java
package com.example.catalog.persistence;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class PostgreSqlContainerSmokeTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16.6")
            .withDatabaseName("catalog_test")
            .withUsername("catalog_test")
            .withPassword("local_test_password");

    @Test
    void postgresStartsAndHasJdbcUrl() {
        assertTrue(postgres.isRunning());
        assertTrue(
            postgres.getJdbcUrl().startsWith("jdbc:postgresql:")
        );
    }
}
```

Đoạn này là **smoke test của infrastructure**, chưa phải test JPA mapping. Nó minh họa:

- `@Testcontainers` gắn JUnit Jupiter extension.
- `@Container` khai báo container do extension quản lý.
- Static container thường được dùng chung cho các test methods trong class.
- JDBC URL được lấy từ container đang chạy.

### 9.1. Không hard-code host port

Dùng:

```java
postgres.getJdbcUrl();
postgres.getUsername();
postgres.getPassword();
```

thay vì tự ghép `jdbc:postgresql://localhost:5432/catalog_test`.

### 9.2. Password trong ví dụ

`local_test_password` chỉ là credential cho database test tạm, không phải production secret. Không copy production credentials vào fixture, log hoặc container configuration.

### 9.3. Không cần import chưa dùng

Các imports như `AfterAll` và `BeforeAll` trong snippet là cơ sở cho phiên bản tích hợp JPA ở phần sau; nếu chỉ chạy smoke test, có thể bỏ chúng. Phần trọng tâm là container lifecycle.

## 10. Java SE JPA integration test với container thật

Để có một phép thử JPA, cần kết nối `EntityManagerFactory` tới JDBC URL của container và khởi tạo schema.

Giả sử dự án có `META-INF/persistence.xml` khai báo `catalogTestPU` với entities cần test. Đoạn sau minh họa **hai bước setup**:

1. Migrate database test.
2. Tạo EntityManagerFactory bằng JDBC properties được override.

```java
package com.example.catalog.persistence;

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

import java.math.BigDecimal;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class ProductJpaContainerTest {

    @Container
    static final PostgreSQLContainer<?> db =
        new PostgreSQLContainer<>("postgres:16.6")
            .withDatabaseName("catalog_test")
            .withUsername("catalog_test")
            .withPassword("local_test_password");

    private static EntityManagerFactory emf;

    @BeforeAll
    static void initializeJpa() {
        // Container is started by the JUnit Testcontainers extension.
        Flyway.configure()
            .dataSource(
                db.getJdbcUrl(),
                db.getUsername(),
                db.getPassword()
            )
            .locations("classpath:db/migration")
            .load()
            .migrate();

        Map<String, Object> props = new HashMap<>();

        props.put(
            "jakarta.persistence.jdbc.url",
            db.getJdbcUrl()
        );
        props.put(
            "jakarta.persistence.jdbc.user",
            db.getUsername()
        );
        props.put(
            "jakarta.persistence.jdbc.password",
            db.getPassword()
        );
        props.put(
            "jakarta.persistence.schema-generation.database.action",
            "none"
        );

        emf = Persistence.createEntityManagerFactory(
            "catalogTestPU",
            props
        );
    }

    @AfterAll
    static void closeJpa() {
        if (emf != null) {
            emf.close();
        }
    }

    @Test
    void canPersistAndReloadProduct() {
        EntityManager em = emf.createEntityManager();

        try {
            em.getTransaction().begin();

            Category category = new Category(
                10L, "KEYBOARDS", "Keyboards"
            );
            em.persist(category);

            Product product = new Product(
                "KB-101",
                new BigDecimal("199.90"),
                category
            );
            em.persist(product);

            em.flush();
            Long id = product.getId();
            em.clear();

            Product loaded = em.find(Product.class, id);

            assertNotNull(loaded);
            assertEquals("KB-101", loaded.getSku());
            assertEquals(
                0,
                new BigDecimal("199.90").compareTo(
                    loaded.getPrice()
                )
            );
            assertEquals(
                Long.valueOf(10L),
                loaded.getCategory().getId()
            );

            em.getTransaction().rollback();
        } finally {
            if (em.getTransaction().isActive()) {
                em.getTransaction().rollback();
            }
            em.close();
        }
    }
}
```

Đây là khung **để thích nghi vào project thực tế**: cần entity imports, JPA provider và `persistence.xml` đúng cấu hình. `Flyway` có thể cần database-specific plugin/module theo major version và database version đang dùng.

### 10.1. Vì sao đặt migrations trước EntityManagerFactory?

Để provider bootstrap trên schema có đúng bảng, sequence và constraints đã được deploy bởi migration. Nếu provider dùng `validate`, nó có thể kiểm tra một phần tương thích ngay lúc khởi tạo.

### 10.2. Vì sao gọi flush rồi clear?

`persist` rồi `find` trong cùng persistence context có thể trả Java object từ L1 cache. `flush(); clear(); find()` giúp kiểm tra đường lưu và nạp lại. Nếu yêu cầu chứng minh SELECT vật lý, còn phải kiểm soát shared/L2 cache hoặc dùng JDBC assertion.

### 10.3. Vì sao rollback cuối test?

Rollback giúp tránh để lại dữ liệu `Category#10`/`Product#...` cho test khác. Nhưng test đó chỉ chứng minh round-trip trong transaction; **không chứng minh commit visibility** cho transaction khác.

### 10.4. Có cần tạo một PostgreSQL container cho mỗi test method?

Không mặc nhiên. Container startup tốn chi phí. Một container dùng chung nhiều test methods có thể hợp lý nếu test data/transactions được cô lập. Nhưng nếu các tests thay đổi schema/state toàn cục, cần reset đáng tin cậy hoặc dùng database/schema riêng.

## 11. Spring Boot @DataJpaTest + PostgreSQL container

Một cấu hình phổ biến là dùng Spring Data JPA test slice cùng Testcontainers.

Ví dụ với Testcontainers 1.x và Spring Boot có `@DynamicPropertySource`:

```java
package com.example.catalog.persistence;

import com.example.catalog.domain.Category;
import com.example.catalog.domain.Product;
import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.*;

@DataJpaTest
@Testcontainers
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class ProductRepositoryPostgresTest {

    @Container
    static final PostgreSQLContainer<?> db =
        new PostgreSQLContainer<>("postgres:16.6")
            .withDatabaseName("catalog_test")
            .withUsername("catalog_test")
            .withPassword("local_test_password");

    @DynamicPropertySource
    static void databaseProperties(
            DynamicPropertyRegistry registry) {

        registry.add(
            "spring.datasource.url",
            db::getJdbcUrl
        );
        registry.add(
            "spring.datasource.username",
            db::getUsername
        );
        registry.add(
            "spring.datasource.password",
            db::getPassword
        );

        registry.add(
            "spring.jpa.hibernate.ddl-auto",
            () -> "validate"
        );
        registry.add(
            "spring.flyway.enabled",
            () -> true
        );
    }

    @Autowired
    EntityManager em;

    @Test
    void persistsProductUsingRealPostgres() {
        em.persist(
            new Category(10L, "KEYBOARDS", "Keyboards")
        );

        Product product = new Product(
            "KB-202",
            new BigDecimal("25.00"),
            em.getReference(Category.class, 10L)
        );

        em.persist(product);
        em.flush();

        Long id = product.getId();
        em.clear();

        Product loaded =
            em.find(Product.class, id);

        assertNotNull(loaded);
        assertEquals("KB-202", loaded.getSku());
    }
}
```

Mẫu này dựa trên những version của Spring Boot có các annotation/packages tương ứng. Các major versions khác có thể đổi package hoặc cách auto-config. Mục đích là thể hiện **cách nối Spring Data JPA test datasource tới container thật**.

### 11.1. Vì sao cần @AutoConfigureTestDatabase(replace = NONE)?

Một `@DataJpaTest` có thể tự thay `DataSource` bằng embedded database khi một embedded driver có mặt và cấu hình test cho phép. Khi muốn test PostgreSQL container, cần bảo đảm auto-configuration **không thay datasource** thành H2 hoặc database khác.

### 11.2. Vai trò của @DynamicPropertySource

Các giá trị URL/username/password chỉ có ý nghĩa sau khi container chạy và port được map. `@DynamicPropertySource` cung cấp các properties động cho Spring test context.

### 11.3. Hibernate ddl-auto=validate là gì?

`spring.jpa.hibernate.ddl-auto=validate` là cấu hình Spring/Hibernate, **không phải một schema generation action tiêu chuẩn của Jakarta Persistence**.

Mục đích là tránh Hibernate tự tạo/xóa schema và yêu cầu nó xác nhận một số mapping/schema tương thích. Với provider khác, cần cơ chế phù hợp.

### 11.4. Đảm bảo migrations thực sự được chạy

Nếu dùng Flyway hoặc Liquibase, kiểm tra dependencies, resource locations, test profiles và thứ tự bootstrap. Đừng chỉ đặt `spring.flyway.enabled=true` rồi giả định tất cả migration files tồn tại và đã được thực thi.

### 11.5. @DataJpaTest thường rollback test transaction

Điều này phù hợp với persistence round-trip test nhưng không kiểm chứng **commit của transaction độc lập**. Với test concurrency/commit visibility, cần thiết kế transactions riêng, tránh outer rollback transaction che behavior.

## 12. Spring Boot @ServiceConnection: lựa chọn tích hợp khác

Một số phiên bản Spring Boot hỗ trợ integration với Testcontainers qua `@ServiceConnection`.

Ví dụ kiểu:

```java
@Testcontainers
@DataJpaTest
class ProductServiceConnectionTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16.6");

    // Repository tests...
}
```

`@ServiceConnection` là Spring Boot feature, không phải API JPA hay Testcontainers core. Chỉ sử dụng khi đúng Spring Boot version và đã có module hỗ trợ Testcontainers service connections.

### 12.1. Chọn @DynamicPropertySource hay @ServiceConnection?

| Cách | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| `@DynamicPropertySource` | Muốn kiểm soát properties rõ | Nhiều cấu hình thủ công |
| `@ServiceConnection` | Spring Boot hỗ trợ connection details | Phụ thuộc Spring Boot integration |
| Java SE manual properties | Không dùng Spring | Cần tự quản lý EMF/migrations |
| JDBC Testcontainers URL | Một số setup đơn giản | Cần biết lifecycle, naming và support đúng version |

### 12.2. Không trộn mọi phương pháp nếu không cần

Nếu đồng thời cấu hình một URL H2, một URL từ `@DynamicPropertySource` và một `@ServiceConnection` khác, khó xác định datasource thực sự được sử dụng. Chọn một chiến lược rõ, log identity của database test khi cần.

## 13. Kiểm tra database thật đang được dùng

Một lỗi cấu hình nguy hiểm là test tuyên bố dùng container nhưng thực tế nối H2 hoặc một database local cũ.

### 13.1. Xác nhận JDBC metadata

Một test hoặc bước setup có thể lấy:

```java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata =
        connection.getMetaData();

    assertEquals(
        "PostgreSQL",
        metadata.getDatabaseProductName()
    );
}
```

Đây là kiểm tra metadata, không phải benchmark hay xác nhận schema đúng. Product name có thể có format phụ thuộc driver; test nên chọn assertion phù hợp.

### 13.2. Kiểm tra version khi cần

```java
int major =
    metadata.getDatabaseMajorVersion();
```

Nếu feature phụ thuộc PostgreSQL major version, pin image tag và xác nhận version thực trong test setup.

### 13.3. Không chỉ kiểm tra URL string

Một string bắt đầu bằng `jdbc:postgresql:` là tín hiệu cấu hình, nhưng JPA thực tế có thể dùng datasource khác nếu nhiều connection factories cùng tồn tại. Tốt nhất kiểm tra **connection thật** mà tests dùng.

### 13.4. Chú ý database/schema hiện hành

Trong PostgreSQL:

```sql
SELECT current_database(), current_schema();
```

Hữu ích khi schema không nằm ở `public` hoặc tests dùng `search_path` tùy chỉnh. Test đã nối đúng PostgreSQL nhưng sai schema vẫn có thể đọc nhầm bảng.

## 14. Kiểm thử schema migrations thực sự chạy được

Container là môi trường phù hợp để test database **từ trạng thái rỗng**.

### 14.1. Quy trình chuẩn

```text
Start empty PostgreSQL container
              |
              v
Run V1...Vn migrations
              |
              v
Create JPA EntityManagerFactory
              |
              v
Execute CRUD and constraints tests
              |
              v
Assert current schema contract
```

### 14.2. Không lấy DDL Hibernate làm nguồn sự thật nếu production dùng migrations

Nếu production deploy bằng Flyway:

```text
Production schema owner = Flyway migrations
```

thì test cũng nên chạy Flyway migrations. Nếu test để Hibernate tự `create`, nó có thể sinh đúng bảng theo annotations mới dù migration production đã quên thêm cột.

### 14.3. Migration order matters

Ví dụ:

```text
V1__create_categories.sql
V2__create_product_sequence.sql
V3__create_products.sql
V4__add_product_constraints.sql
V5__create_audit_events.sql
```

Khi test bắt đầu từ DB trắng và chạy toàn bộ phiên bản, có thể phát hiện thiếu bảng, cú pháp không tương thích hoặc migration phụ thuộc sai thứ tự.

### 14.4. Test nâng cấp từ schema cũ

Chạy migrations từ DB trắng **không đủ** để chứng minh upgrade một DB có dữ liệu cũ an toàn.

Một test khác nên:

1. Tạo schema phiên bản cũ.
2. Chèn fixture dữ liệu phiên bản cũ.
3. Chạy migrations mới.
4. Xác nhận dữ liệu không bị mất và constraints/queries phù hợp.
5. Test application code mới trên schema nâng cấp.

### 14.5. Migrations và transaction

Một số DDL có transaction/lock behavior riêng theo DBMS. Container PostgreSQL cho thấy behavior gần engine thật hơn in-memory DB, nhưng test vẫn cần mô phỏng dữ liệu/locks thích hợp.

## 15. Test FK, UNIQUE và CHECK trên PostgreSQL thật

Một entity hợp lệ không chứng minh database constraints tồn tại. Hãy test **các điều kiện bị cấm**.

### 15.1. FK

Tạo Product với `category_id` không tồn tại bằng SQL/JPA và kiểm tra database từ chối.

Nếu muốn kiểm tra **DB constraint** độc lập Bean Validation/ORM, có thể dùng JDBC:

```java
try (Connection connection = dataSource.getConnection()) {
    try (PreparedStatement ps =
             connection.prepareStatement(
                 """
                 INSERT INTO products (
                     id, sku, price, category_id, version
                 )
                 VALUES (9999, 'BAD-FK', 10.00, 999999, 0)
                 """
             )) {

        assertThrows(
            SQLException.class,
            ps::executeUpdate
        );
    }
}
```

Đoạn code cần imports JDBC, datasource đã cấu hình và transaction/test cleanup phù hợp. PostgreSQL sẽ từ chối FK nếu constraint hiện hữu và được kiểm tra ngay; nếu constraint là deferred, lỗi có thể đến ở commit.

### 15.2. UNIQUE

Tạo hai Products cùng SKU:

```text
Product A: sku = "KB-100"
Product B: sku = "KB-100"
```

Chỉ check repository `existsBySku` trước khi insert **không bảo đảm** chống concurrent writes. Test database unique constraint sẽ kiểm chứng cơ chế cuối.

### 15.3. CHECK

```sql
CONSTRAINT ck_product_price CHECK (price >= 0)
```

nên từ chối giá âm ngay cả khi một writer không đi qua `Product.changePrice()`.

### 15.4. CHECK và NULL

`CHECK(price >= 0)` không tự thay thế `NOT NULL`. Trong SQL, biểu thức CHECK trả UNKNOWN có thể không bị từ chối; cần cả hai constraints nếu quy tắc là “có giá và không âm”.

### 15.5. Tại sao không chỉ assert lỗi của JPA flush?

Bean Validation có thể ném trước khi gửi JDBC SQL. Nếu muốn chứng minh **DB constraint** thật sự tồn tại, cần kiểm thử phù hợp với layer đó.

### 15.6. Deferred constraints

Một số constraints có thể được kiểm tra tại transaction commit, không phải flush. Test nên biết schema semantics và đặt assertion đúng điểm.

## 16. Test JSONB và native SQL theo dialect

Mô hình AuditEvent dùng:

```sql
CREATE TABLE audit_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
);
```

Ta có thể kiểm tra trực tiếp PostgreSQL:

```sql
INSERT INTO audit_events (
    payload, occurred_at
)
VALUES (
    '{"eventType":"PAYMENT","orderId":101}'::jsonb,
    CURRENT_TIMESTAMP
);
```

Query:

```sql
SELECT id
FROM audit_events
WHERE payload @> '{"eventType":"PAYMENT"}'::jsonb;
```

### 16.1. Vì sao cần PostgreSQL thật?

- Operator `@>` là PostgreSQL JSONB containment semantics.
- `::jsonb` cast là cú pháp PostgreSQL.
- JSON path/index behavior là PostgreSQL-specific.
- Query planner dùng GIN index theo semantics thật.

### 16.2. JPA native SQL test

Ví dụ với parameters, tốt hơn tránh nối JSON literal từ request:

```java
List<?> ids = em.createNativeQuery(
    """
    SELECT id
    FROM audit_events
    WHERE payload @> CAST(:filter AS jsonb)
    """
)
.setParameter(
    "filter",
    "{\"eventType\":\"PAYMENT\"}"
)
.getResultList();
```

Named parameters trong native SQL có thể phụ thuộc provider support. Test cần dùng cú pháp parameter được provider/version hỗ trợ; với portability JDBC, có thể dùng `PreparedStatement` và positional placeholders theo driver.

### 16.3. JSON mapping sang Java

Nếu entity dùng Hibernate-specific JSON mapping như `@JdbcTypeCode(SqlTypes.JSON)`, test với PostgreSQL container là cách tốt để xác nhận provider type binding/reading. Đây là **Hibernate extension**, không phải toàn bộ behavior portable của Jakarta Persistence.

### 16.4. Test không chỉ query pass

Cần kiểm tra:

- Serialize object Java thành JSON storage.
- Deserialize lại sau `flush/clear`.
- Truy vấn theo thuộc tính JSON.
- NULL handling.
- Query với nested fields/arrays.
- Index behavior khi cần performance testing riêng.

## 17. Precision, scale, timezone và locale

Hệ thống thương mại thường quan tâm hơn chỉ “INSERT có thành công?”.

### 17.1. BigDecimal

Một field:

```java
@Column(precision = 14, scale = 2)
private BigDecimal price;
```

nên được test bằng các giá trị:

```text
0.00
19.99
123456789012.34 (nếu phù hợp precision)
Số có hơn hai chữ số thập phân
Giá trị vượt precision
```

Quy tắc rounding/rejection có thể khác giữa DBMS và driver. Khi test mapping, phải round-trip qua DB và khẳng định **giá trị thực nhận** theo policy đã định.

### 17.2. Timezone

PostgreSQL `TIMESTAMPTZ` biểu diễn thời điểm thời gian với semantics khác “local timestamp” không timezone. Ứng dụng dùng `Instant`, `OffsetDateTime` hoặc `LocalDateTime` phải có policy rõ.

Test nên xác nhận:

- UTC instant được bảo toàn.
- Session timezone không làm đổi meaning ngoài ý định.
- Chuyển đổi Java ↔ JDBC ↔ DB đúng.
- Date-only không tự bị chuyển như timestamp.

### 17.3. Collation và case sensitivity

Đối với SKU/email/username, hỏi:

- `"ABC"` và `"abc"` có được coi trùng không?
- Case sensitivity trong `ORDER BY` thế nào?
- Dấu tiếng Việt có ảnh hưởng sort/collation?
- Database có functional/partial unique index không?

Một H2 test có thể cho kết quả khác PostgreSQL cấu hình collation production.

### 17.4. Encoding

Test với dữ liệu:

```text
Bàn phím cơ
Đơn hàng số ١٢٣
Café
emoji 🎹
```

Nếu domain cho phép Unicode, cần xác nhận JDBC/DB encoding và column constraints không phá dữ liệu.

### 17.5. Pin timezone và locale khi cần

Để tránh flaky tests, xác định rõ timezone của JVM, JDBC/session và DB. Nhưng đừng chỉ pin một timezone duy nhất nếu ứng dụng phải hoạt động với nhiều timezone; cần thêm boundary cases.

## 18. IDENTITY và SEQUENCE khác nhau theo DBMS

JPA định nghĩa:

```java
@GeneratedValue(strategy = GenerationType.IDENTITY)
@GeneratedValue(strategy = GenerationType.SEQUENCE)
@GeneratedValue(strategy = GenerationType.TABLE)
```

Nhưng DBMS cụ thể có capabilities khác nhau.

### 18.1. PostgreSQL sequence

```sql
CREATE SEQUENCE product_id_seq START WITH 1;
```

Với:

```java
@SequenceGenerator(
    name = "product_id_generator",
    sequenceName = "product_id_seq",
    allocationSize = 1
)
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "product_id_generator"
)
private Long id;
```

provider cần sequence matching như kỳ vọng.

### 18.2. Vì sao không chỉ test ID non-null?

Provider có thể cấp ID trước INSERT. Test nên:

```java
em.persist(product);
em.flush();

Long id = product.getId();

em.clear();

assertNotNull(em.find(Product.class, id));
```

### 18.3. Sequence gaps là bình thường

Sequence values có thể không rollback khi transaction rollback. Vì vậy một test “IDs phải liên tiếp 101,102,103” dễ sai giả định khi chạy thật.

### 18.4. JDBC batching

Hibernate có thể giới hạn batching INSERT với IDENTITY trong một số mapping, trong khi SEQUENCE có thể cho chiến lược batching khác.

Test DBMS thật giúp xác định SQL behavior của provider + driver, nhưng performance cần đo trong workload đại diện.

## 19. Flush, clear và dữ liệu thật

Một test JPA có thể bị đánh lừa bởi first-level cache.

### 19.1. Test yếu

```java
em.persist(product);

Product loaded =
    em.find(Product.class, product.getId());

assertEquals(product.getSku(), loaded.getSku());
```

Trong cùng persistence context, `loaded` có thể là chính managed entity `product`.

### 19.2. Test tốt hơn

```java
em.persist(product);
em.flush();

Long id = product.getId();

em.clear();

Product loaded = em.find(Product.class, id);

assertEquals("KB-101", loaded.getSku());
```

### 19.3. Nhưng L2 vẫn có thể tham gia

`clear()` chỉ detach L1 managed entities. Nếu shared/L2 cache bật, `find` vẫn có thể lấy state từ L2 mà không thực hiện SQL SELECT.

Nếu mục tiêu cụ thể là **database read path**, có thể:

- Tắt shared cache trong persistence unit test.
- Dùng `CacheRetrieveMode.BYPASS` khi phù hợp.
- Đọc bằng JDBC để kiểm tra physical representation.
- Đo SQL executions qua JDBC instrumentation.

### 19.4. Flush không phải commit

`em.flush()` đồng bộ DML trong transaction nhưng vẫn có thể rollback. Khi test yêu cầu committed state, cần transaction commit và reader transaction mới.

## 20. Transaction isolation không được test bằng một EntityManager

Một test cùng một `EntityManager` không thể mô phỏng đúng hai actors cạnh tranh.

### 20.1. Sơ đồ hai transactions

```text
Transaction A / EntityManager A
       |
       +-- READ Product#101, version=5
       |
Transaction B / EntityManager B
       |
       +-- READ Product#101, version=5
       +-- UPDATE and COMMIT version=6
       |
Transaction A
       |
       +-- UPDATE with stale version=5
       +-- Optimistic lock conflict
```

### 20.2. Vì sao cần database thật?

Optimistic locking liên quan JPA provider version checks và SQL UPDATE row counts; transaction isolation/locking còn phụ thuộc engine. Test trên PostgreSQL container giúp quan sát behavior PostgreSQL thật.

### 20.3. Mô hình JUnit test hai EntityManagers

```java
EntityManager a = emf.createEntityManager();
EntityManager b = emf.createEntityManager();

try {
    a.getTransaction().begin();
    b.getTransaction().begin();

    Product pa = a.find(Product.class, productId);
    Product pb = b.find(Product.class, productId);

    pb.changePrice(new BigDecimal("20.00"));
    b.getTransaction().commit();

    pa.changePrice(new BigDecimal("21.00"));

    assertThrows(
        RuntimeException.class,
        () -> {
            a.flush();
            a.getTransaction().commit();
        }
    );
} finally {
    if (a.getTransaction().isActive()) {
        a.getTransaction().rollback();
    }
    if (b.getTransaction().isActive()) {
        b.getTransaction().rollback();
    }
    a.close();
    b.close();
}
```

Đây là **khung ý tưởng**, cần setup Product đã committed, cấu hình `@Version` và tách transaction lifecycle đúng. Việc ngoại lệ xuất hiện ở `flush` hay `commit` có thể khác; assertion tổng quát `RuntimeException` trong ví dụ chỉ minh họa, test thực tế nên kiểm tra exception category/cause theo provider/version.

### 20.4. Không coi conflict xảy ra trong mọi thời điểm

Nếu A lấy lock hoặc provider flush khác thứ tự, behavior có thể thay đổi. Test concurrency phải kiểm soát timing và conditions, không chỉ chạy hai threads rồi hy vọng race xuất hiện.

### 20.5. Không chỉ test optimistic locking

Có thể cần test:

- Pessimistic lock waits.
- Deadlocks.
- Unique constraint races.
- Isolation visibility.
- Atomic conditional updates.
- Transaction timeout/retry.
- Referential integrity dưới concurrency.

## 21. Test pessimistic locking trên DBMS thật

JPA có lock modes chuẩn:

```java
Product p = em.find(
    Product.class,
    productId,
    LockModeType.PESSIMISTIC_WRITE
);
```

Nhưng actual SQL, lock compatibility và timeout semantics phụ thuộc DBMS/provider.

### 21.1. Kịch bản

```text
T1: SELECT product FOR UPDATE
    hold transaction open

T2: attempt PESSIMISTIC_WRITE on same product
    wait / timeout / conflict according to DB policy

T1: commit or rollback
T2: outcome inspected
```

### 21.2. Thiết kế test concurrency đúng

- Hai EntityManagers và hai independent connections.
- Hai transactions thực sự độc lập.
- Đồng bộ với `CountDownLatch`/`CyclicBarrier` thay vì `Thread.sleep` làm đồng hồ.
- Có timeouts để tránh test treo vô hạn.
- Khởi tạo committed fixture trước khi bắt đầu.
- Kiểm soát DB isolation/lock timeout policy.
- Đọc trạng thái committed cuối cùng để xác minh correctness.

### 21.3. Không test bằng REQUIRES_NEW tùy tiện trong outer rollback transaction

Trong Spring, test method có `@Transactional` có thể giữ một connection/lock khiến inner `REQUIRES_NEW` chờ trên chính fixture mà outer test đang giữ. Dùng transaction orchestration rõ và tránh deadlock do thiết kế test.

### 21.4. Có nên assert thời gian lock bằng milliseconds cố định?

Không nên đặt ngưỡng quá sát vì CI scheduling biến động. Quan sát trạng thái wait/timeout theo contract với ngưỡng hợp lý và đồng bộ deterministically.

## 22. Transaction isolation và hiện tượng đọc

Những hiện tượng phổ biến:

- Dirty read.
- Non-repeatable read.
- Phantom read.
- Serialization failure.
- Lock wait/deadlock.

JDBC/JPA sử dụng các isolation settings của DBMS/connection/transaction manager. **Không có một mức mặc định chung cho mọi DBMS**, và các chi tiết thực thi có thể khác ngay khi tên isolation giống nhau.

### 22.1. Ví dụ read committed

```text
T1: update Product price; not commit yet
T2: SELECT Product price

T2 under READ COMMITTED:
  should not see T1 uncommitted value
```

Trên PostgreSQL mặc định, dirty read không được phép. Test H2 không phải là bằng chứng đầy đủ về tất cả locking/isolation effects PostgreSQL khi có concurrency.

### 22.2. Repeatable read và snapshot

Nếu business phụ thuộc một snapshot nhất quán qua nhiều queries, test phải kiểm tra actual isolation behavior. Không tự suy rằng `@Transactional` mặc định cho repeatable reads.

### 22.3. Serializable

Serializable isolation có thể phát sinh serialization failures cần retry toàn transaction. A database container giúp kiểm thử behavior engine thật, nhưng concurrency harness phải tạo lịch thực thi dẫn tới tình huống đó.

### 22.4. Đọc dữ liệu sau commit

Một test làm:

```text
T1: persist + flush, not committed
T2: find -> null
```

không chứng minh persist thất bại. T2 có thể không thấy uncommitted data theo isolation. Muốn test commit visibility, cho T1 commit trước rồi T2 đọc.

## 23. Test unique race condition

Hai requests tạo cùng SKU:

```text
T1: SELECT exists sku="KB-999" -> false
T2: SELECT exists sku="KB-999" -> false

T1: INSERT sku="KB-999"
T2: INSERT sku="KB-999"

Commit behavior:
  one committed row if UNIQUE(sku) enforced
  other transaction conflicts/fails
```

### 23.1. Tại sao service check chưa đủ?

`SELECT exists` chỉ cho biết trạng thái tại thời điểm đọc. Hai transactions đồng thời có thể cùng thấy chưa tồn tại.

### 23.2. Database constraint bảo vệ cuối

`UNIQUE(sku)` thực sự ngăn trạng thái committed có hai rows với SKU giống nhau theo uniqueness semantics của DB.

### 23.3. Test phải kiểm tra final DB state

Không chỉ assert một exception. Kiểm tra:

- Có đúng một committed SKU.
- Không có partial dữ liệu liên quan sai.
- Transaction thất bại được rollback.
- Application trả error category phù hợp.
- Retry/idempotency policy có chủ đích.

### 23.4. Không chạy hai transaction trên cùng connection

Muốn test concurrency phải dùng separate DB transactions/connections. Một shared `EntityManager` không thread-safe và không nên chia sẻ giữa các worker threads.

## 24. @Version và thời điểm phát hiện conflict

Mapping:

```java
@Version
@Column(name = "version", nullable = false)
private Long version;
```

Provider có thể dùng SQL giống:

```sql
UPDATE products
SET price = 20.00,
    version = 6
WHERE id = 101
  AND version = 5;
```

Nếu row đã được transaction khác cập nhật version 6, operation có thể ảnh hưởng 0 rows và dẫn tới optimistic lock exception.

### 24.1. SQL chỉ để minh họa

Cú pháp và statement order thực tế phụ thuộc JPA provider, dialect và mapping.

### 24.2. Khi nào exception xuất hiện?

Có thể tại `flush` hoặc `commit`; trong JTA/Spring có thể được wrap bởi transaction/runtime exceptions.

### 24.3. Tại sao database container giúp?

Nó kiểm tra tương tác thực giữa provider, JDBC driver, transaction isolation và update row counts trên DBMS đích.

### 24.4. Không dùng cache để tạo hai versions giả

Hai biến được load trong cùng persistence context thường là cùng instance, không tạo conflict thực. Cần hai EntityManagers/transactions độc lập.

## 25. Test database-specific indexes và execution plan

PostgreSQL index:

```sql
CREATE INDEX idx_product_category
ON products(category_id);
```

Hoặc GIN index trên JSONB:

```sql
CREATE INDEX idx_audit_payload
ON audit_events USING GIN (payload);
```

### 25.1. Có thể kiểm thử index tồn tại

Kiểm tra catalog metadata hoặc thử query/schema introspection trên PostgreSQL container.

### 25.2. Index tồn tại không nghĩa optimizer luôn dùng

Với 10 rows trong test database, PostgreSQL có thể chọn sequential scan vì đó là plan rẻ nhất. Không assert “EXPLAIN phải chứa Index Scan” trong mọi dataset nếu index selection không phải contract chắc chắn.

### 25.3. EXPLAIN ANALYZE

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM products
WHERE category_id = 10;
```

có thể giúp hiểu plan và buffers khi có workload phù hợp. Tuy nhiên performance container nhỏ không phản ánh production indexes, thống kê và dữ liệu lớn.

### 25.4. Khi cần performance parity hơn

Dùng tập dữ liệu đại diện, ANALYZE/statistics, indexes production và phần cứng/network đủ tương đồng. Container integration test với vài fixtures chủ yếu kiểm tra **khả năng chạy và correctness**, không phải production p99.

## 26. Thử nghiệm trên nhiều DBMS khi sản phẩm hỗ trợ nhiều DB

Nếu sản phẩm tuyên bố chạy trên PostgreSQL và MySQL, cần ít nhất một test matrix:

```text
Shared contract tests
        |
        +--> PostgreSQL container
        |
        +--> MySQL container
```

### 26.1. Tách domain tests và DB-specific tests

- Common JPA CRUD contract tests chạy trên cả hai DB.
- PostgreSQL JSONB tests chỉ chạy PostgreSQL.
- MySQL-specific SQL tests chỉ chạy MySQL.
- Migrations có SQL riêng theo DBMS nếu sản phẩm thực sự hỗ trợ đa DB.

### 26.2. Đừng giả định chung một migration SQL cho mọi DB

`SERIAL`, `IDENTITY`, generated columns, JSON types, DDL clauses và index definitions có thể khác. Portability cần được thiết kế và kiểm thử.

### 26.3. Một container không chứng minh mọi DBMS

Nếu chỉ chạy PostgreSQL, không thể tuyên bố application cũng tương thích Oracle chỉ vì JPA API đều là chuẩn.

### 26.4. Khi nào chỉ hỗ trợ một DBMS là hợp lý?

Nếu business stack gắn cố định PostgreSQL, tập trung test sâu trên PostgreSQL có thể tốt hơn thử nông trên nhiều DB không có cam kết hỗ trợ.

## 27. CI: chạy Testcontainers trong pipeline

Một CI runner cần container runtime. Pipeline có thể:

```text
Checkout source
       |
       v
Compile test classes
       |
       v
Start Docker-compatible runtime
       |
       v
Pull/use pinned PostgreSQL image
       |
       v
Start Testcontainers PostgreSQL
       |
       v
Apply migrations
       |
       v
Run JPA integration tests
       |
       v
Collect test report/logs
       |
       v
Stop/remove test resources
```

### 27.1. Không cần host cố định port 5432

Testcontainers thường tự map ephemeral ports để hỗ trợ nhiều test jobs cùng runner.

### 27.2. CI runner phải có quyền truy cập daemon

Nếu chạy test bên trong một CI container khác, có thể cần kết nối đến Docker daemon sidecar hoặc cơ chế container-in-container được quản trị cho phép.

Không mở quyền Docker socket cho untrusted code tùy tiện; container runtime socket thường có quyền rất mạnh trên host.

### 27.3. Image pull có thể thất bại

Một build có thể fail vì:

- Registry không truy cập được.
- Rate limit.
- Image tag không tồn tại.
- Architecture không phù hợp.
- Proxy/network configuration lỗi.
- Container runtime không khởi động.

Cần logs rõ để phân biệt **infrastructure failure** với **JPA query failure**.

### 27.4. Làm rõ chính sách cache image

Caching images trên runner có thể giảm thời gian startup, nhưng không làm thay đổi version đang được pin hoặc phá isolation giữa jobs.

### 27.5. Test report phải ghi database identity

Khi gặp lỗi khó tái hiện, báo cáo nên có DBMS name/version, JPA provider/driver versions và migration version đã chạy — nhưng không in database passwords/secrets.

## 28. Dữ liệu test: cô lập, tái lập và đủ đại diện

Database thật trong container không tự giải quyết dữ liệu test.

### 28.1. Fixture tối thiểu

Cho một test FK:

```text
Category#10
Product#101 -> Category#10
```

Cho một test UNIQUE:

```text
Product SKU="KB-101" exists
Try to insert SKU="KB-101" again
```

Cho một test optimistic locking:

```text
Product#101 committed version=1
T1 and T2 load the same version
```

### 28.2. Fixture hợp lệ và bất hợp lệ

Không chỉ test “INSERT thành công”. Những test âm quan trọng xác nhận constraints thực sự từ chối dữ liệu không hợp lệ.

### 28.3. Rollback fixture

Một transaction test rollback sau assertion thường giúp giữ database sạch. Nhưng nếu test cần commit visibility, transaction thất bại hoặc DDL, rollback wrapper đơn giản có thể không đủ.

### 28.4. Cleanup sau committed tests

Có thể:

- Dùng database/schema tạm riêng.
- Dùng transaction cleanup.
- Reset data có thứ tự theo FK.
- Recreate container cho một nhóm test nhạy cảm với state.
- Quản lý unique fixture identifiers có kiểm soát.

### 28.5. Đừng dùng hard-coded ID liên tiếp

Sequence/IDENTITY có thể tạo gaps khi rollback hoặc concurrency. Test nên dựa trên returned IDs hoặc business keys, không giả định lần đầu luôn được ID 1.

## 29. Container lifetime: mỗi method hay mỗi class?

Một PostgreSQL container khởi động tốn thời gian; sử dụng lại có thể giảm chi phí.

### 29.1. Một container cho cả test class

Ưu điểm:

- Startup amortized.
- Dễ quản lý với static `@Container`.
- Thích hợp repository integration tests.

Rủi ro:

- Test methods có thể ảnh hưởng dữ liệu lẫn nhau.
- Parallel tests phải có isolation strategy.
- Schema mutations ngoài transaction có thể tồn tại.

### 29.2. Một container cho từng test method

Ưu điểm:

- Isolation mạnh hơn.
- Ít stale state.

Rủi ro:

- Startup chậm.
- CI resource consumption lớn.
- Không cần cho mọi test.

### 29.3. Một container chung cả test suite

Có thể hiệu quả nếu được tổ chức đúng, nhưng phải hiểu lifecycle giữa JUnit test classes, Spring application contexts và container ownership.

Một lỗi phổ biến là Spring context giữ datasource tới container đã bị dừng sau một test class, rồi context được reuse cho test class sau.

### 29.4. Testcontainers reusable containers

Một số chế độ tái sử dụng containers có thể hỗ trợ phát triển local, nhưng **không nên mặc nhiên bật lại sử dụng lâu dài cho CI** nếu mục tiêu là fresh disposable state và reproducibility. Cần chính sách explicit.

### 29.5. Đo thời gian build

Tối ưu lifecycle theo số lượng suites, tổng startup, CPU/memory và test flakiness. Đừng giảm vài giây bằng cách chia sẻ dữ liệu khiến tests không độc lập.

## 30. Transaction rollback trong Spring tests có giới hạn

Một `@DataJpaTest` hoặc `@Transactional` test thường rollback khi method kết thúc. Điều đó hữu ích, nhưng có những giới hạn.

### 30.1. Không kiểm tra commit-time exceptions

Nếu một constraint deferred chỉ được kiểm tra ở commit, test rollback có thể không phát hiện cùng lỗi như production.

### 30.2. REQUIRES_NEW có thể commit riêng

Một service method với `Propagation.REQUIRES_NEW` có thể commit một transaction độc lập, để lại dữ liệu sau test dù outer test rollback.

### 30.3. Async code không cùng test transaction

Một worker thread hoặc message listener có thể sử dụng transaction riêng. Không giả định rollback test tự hoàn tác mọi side effects.

### 30.4. Rollback không phục hồi sequence counters

Một số DBMS không rollback sequence increments, vì vậy expected IDs cần độc lập với số lần test đã chạy.

### 30.5. Kiểm tra commit bằng transaction orchestration riêng

Nếu test yêu cầu chứng minh dữ liệu committed, tránh outer test transaction hoặc dùng các công cụ như `TransactionTemplate` với propagation phù hợp, rồi mở transaction mới để đọc.

Không mở một transaction thứ hai “giả” cùng connection và gọi đó là kiểm thử concurrent visibility.

## 31. Một test migration upgrade có dữ liệu cũ

Giả sử schema V1:

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(50) NOT NULL
);
```

V2 thêm:

```sql
ALTER TABLE products
ADD COLUMN price NUMERIC(14,2);
```

Sau đó cần backfill, rồi mới `NOT NULL`.

### 31.1. Test từ DB trắng không kiểm tra backfill

Chạy toàn bộ migrations trên DB rỗng có thể pass, nhưng khi production có hàng triệu rows, `SET NOT NULL` có thể thất bại nếu migration chưa backfill.

### 31.2. Test upgrade đúng hơn

```text
Start Postgres container
       |
       v
Apply migrations up to V1
       |
       v
Insert historical fixture rows
       |
       v
Apply V2..Vn migrations
       |
       v
Assert old data preserved
       |
       v
Create JPA EMF with current mappings
       |
       v
Run domain reads/writes
```

### 31.3. Backfill phải được kiểm tra

Test rằng old Product có price hợp lệ sau upgrade, không chỉ new Product INSERT thành công.

### 31.4. Không thể mô phỏng production data volume bằng vài rows

Test upgrade trên fixture nhỏ kiểm tra logic; đánh giá thời gian migrate/locks cần dataset lớn và environment gần production hơn.

## 32. Kiểm tra Row-Level Security nếu dùng PostgreSQL

PostgreSQL RLS là cơ chế DBMS-specific, không thuộc JPA standard.

Ví dụ policy dạng:

```sql
ALTER TABLE purchase_orders
ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_orders
ON purchase_orders
USING (
    tenant_id = current_setting('app.tenant_id', true)
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)
);
```

### 32.1. Tại sao phải dùng PostgreSQL thật?

H2 không bảo đảm RLS semantics như PostgreSQL.

### 32.2. Test tenant isolation

- Tenant A chỉ nhìn thấy rows A.
- Tenant B chỉ nhìn thấy rows B.
- Thiếu tenant context phải fail closed theo policy.
- INSERT/UPDATE khác tenant bị từ chối.
- Connection reuse không rò tenant context.

### 32.3. Chú ý DB role

Role là table owner/superuser hoặc có `BYPASSRLS` có thể được xử lý khác. Nếu test dùng superuser, có thể vô tình bypass policies.

Tạo application-like DB role với quyền gần production khi test RLS.

### 32.4. Container cùng DBMS chưa đủ nếu role khác

Một PostgreSQL container mặc định dùng administrative credentials có thể chạy được queries mà runtime application role không có quyền. Vì vậy với security/privilege tests, cần mô phỏng roles và grants.

## 33. Kết nối pool, timeouts và settings

Để tăng độ tương đồng với production, xem:

- JDBC driver version.
- Connection pool implementation/version.
- Maximum pool size.
- Minimum idle.
- Connection timeout.
- Statement timeout.
- Transaction isolation.
- Auto-commit policy.
- Default schema/search path.
- Session timezone.
- SSL/TLS settings khi là phần requirement.

### 33.1. Không cần giả lập toàn bộ production cho test CRUD

Một test mapping đơn giản không cần 100 pool connections hoặc TLS termination. Chỉ cấu hình những yếu tố ảnh hưởng đến behavior cần xác nhận.

### 33.2. Pool saturation test

Một test pool saturation cần nhiều concurrent connections và workload có chủ đích. Container một mình không tạo workload này.

### 33.3. Session variables và connection reuse

Nếu tenant RLS hoặc timezone dựa vào session settings, kiểm tra reset khi connection trả về pool. Một lỗi tenant context có thể không xuất hiện nếu test luôn tạo connection mới.

### 33.4. Statement timeout

Timeout ở driver, JPA hint, pool và database có semantics khác nhau. Test trên DBMS thật hữu ích nhưng cần biết timeout đang được áp dụng ở tầng nào.

## 34. Docker/container không tự bằng production

Một ngộ nhận là:

> “Test dùng cùng PostgreSQL image nên chắc chắn tương đương production.”

Đúng hơn:

> “Test chạy cùng PostgreSQL engine/version trong những điều kiện được mô phỏng, nên kiểm tra tốt hơn các đặc điểm engine mà ta đã nêu và tạo dữ liệu kiểm thử phù hợp.”

### 34.1. Những khác biệt còn lại

| Yếu tố | Test container đơn giản | Production |
| --- | --- | --- |
| Data volume | Vài trăm rows | Có thể hàng triệu rows |
| CPU/RAM | Máy dev/CI | Tài nguyên riêng |
| Storage | Ephemeral local volume | SSD/network storage |
| Connection traffic | Ít hoặc đơn luồng | Nhiều concurrent requests |
| Schema | Tạo mới | Đã nâng cấp qua nhiều versions |
| Index statistics | Mới/vừa tạo | Phụ thuộc workload lâu dài |
| Pool/network | Local | Cross-zone/VPC/proxy |
| Roles/grants | Test account rộng quyền | Least privilege |
| Replication | Một primary | Primary/replicas/failover |
| Backups | Không hoặc rất ít | Backup/restore/retention |
| Config | Defaults | Tuned settings |
| Extensions | Có thể thiếu | Có thể có extension/permissions |
| Timezone/collation | Image defaults | Production policy |

### 34.2. Container là công cụ tăng fidelity, không phải oracle tuyệt đối

Có những vấn đề chỉ xuất hiện ở production-scale workload hoặc distributed topology. Cần phân biệt test đảm bảo **behavioral correctness** và performance/resilience test.

### 34.3. Production có managed database

Một dịch vụ như managed PostgreSQL có thể hạn chế superuser/extensions, có networking/failover riêng và patch policies khác container local. Với feature phụ thuộc managed-service specifics, cần thêm môi trường staging phù hợp.

## 35. Khi nào cần mô hình nhiều containers?

Một ứng dụng có thể phụ thuộc vào:

- PostgreSQL.
- Kafka/RabbitMQ.
- Redis.
- Object storage.
- External authentication mock.
- Một service nội bộ.

Để test end-to-end transaction/outbox/event consumer, có thể phối hợp nhiều service containers.

### 35.1. Nhưng đừng biến mọi repository test thành E2E

Một test xác nhận `@JoinColumn` không cần Kafka. Giữ phạm vi hẹp để test nhanh và lỗi dễ quy nguyên nhân.

### 35.2. Test transactional outbox

Nếu một Order update đồng thời ghi outbox row trong cùng DB transaction, test PostgreSQL container có thể xác nhận:

- Order và outbox row cùng commit.
- Rollback loại cả hai.
- Poller không đọc uncommitted outbox row.
- Retry/idempotency policy phù hợp.

Khi cần xác nhận broker delivery, có thể thêm broker container trong một suite riêng.

### 35.3. Network failures không tự xuất hiện

Muốn test connection disruption hoặc failover, cần công cụ chaos/fault injection hoặc topology riêng, không chỉ một container PostgreSQL mặc định.

## 36. Test data và tính bảo mật

Một container local không phải nơi hợp lý để sao chép tùy tiện production database chứa PII.

### 36.1. Ưu tiên dữ liệu tổng hợp

Tạo fixtures phản ánh:

- Kích thước chuỗi.
- Unicode.
- Numeric boundaries.
- Quan hệ FK.
- Distribution/skew khi benchmark.
- Edge cases transaction.

Không cần chép thông tin nhận dạng thật.

### 36.2. Nếu phải dùng dữ liệu trích xuất

Cần masking/anonymization phù hợp, quyền truy cập và retention; không lưu dumps chứa secrets/PII vào repository hoặc image layers.

### 36.3. Container logs có thể chứa dữ liệu

SQL logs, DB errors và bind values có thể tiết lộ thông tin nhạy cảm. Cấu hình logging theo môi trường và không xuất raw sensitive payload lên CI artifacts vô thời hạn.

### 36.4. Credentials của container

Test credentials có thể là giá trị tạm cho DB ephemeral, nhưng production credentials phải được quản lý riêng. Không dùng cùng secret thật trong source test.

## 37. Chọn chiến lược test theo tốc độ và độ tin cậy

Một cấu trúc hợp lý:

```text
Tests
  |
  +-- Pure unit tests
  |     fast, no DB
  |
  +-- JPA contract integration tests
  |     real PostgreSQL container
  |     migrations + entity round-trip
  |
  +-- Concurrency/locking tests
  |     real DB, independent transactions
  |
  +-- Migration upgrade tests
  |     old schema + old data -> new schema
  |
  +-- Performance/load tests
  |     representative dataset and infrastructure
  |
  +-- Production-like staging validation
        deployment + full stack/operational settings
```

### 37.1. Local developer feedback

Unit tests có thể chạy liên tục; JPA container tests có thể chạy theo module/test group. CI nên có đủ integration coverage để ngăn những lỗi sai database trước merge/release.

### 37.2. Không phải mọi test dùng container là integration test tốt

Một test chỉ assert container running không kiểm chứng JPA. Cần assertions về schema, behavior và transaction.

### 37.3. Không phải integration test nào cũng cần container mới

Một container dùng chung với isolation đúng có thể giảm build time mà vẫn giữ độ tin cậy.

### 37.4. Test đơn giản không nên phụ thuộc mạng Internet mỗi lần

Sử dụng pinned images và image caching/mirror theo chính sách CI; nhưng không thay đổi artifact không kiểm soát.

## 38. Một bảng các sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng H2 rồi tuyên bố đã test PostgreSQL behavior | Test xanh giả | Chạy đúng PostgreSQL engine |
| Bật H2 PostgreSQL mode và xem như tương đương hoàn toàn | Bỏ sót JSONB/locks/DDL | Test DBMS thật cho feature phụ thuộc |
| Dùng `postgres:latest` | Không reproducible | Pin image version/digest |
| Hard-code `localhost:5432` | Port conflict, sai DB | Dùng container JDBC URL |
| Dùng H2 datasource ngoài ý muốn | Test sai DB | Disable replacement, kiểm tra metadata |
| Cho Hibernate `create` sau migrations | Che lỗi schema drift | Migration là schema owner |
| Chỉ test DB trắng | Không thấy backfill bug | Test upgrade với old data |
| Test commit visibility trong rollback-only transaction | Kết luận sai | Transactions/EM độc lập |
| Chỉ `persist` rồi `find` cùng EM | L1 cache che read path | `flush/clear`, kiểm soát L2 |
| Assert exception luôn tại flush | Deferred constraint fail at commit | Test đúng DB constraint semantics |
| Một EM dùng cho hai concurrent actors | Không tạo concurrency thật | Hai EM/connections |
| Dùng `Thread.sleep` để sắp lịch race | Flaky | Latches/barriers và timeout |
| Assert IDs tăng liên tục | Sequence gaps | Dùng returned IDs |
| Assert optimizer luôn chọn index với 10 rows | Flaky/sai mục tiêu | Representative data + plan analysis |
| Container dùng admin role để test RLS | Policy bị bypass | Application-like role |
| Reuse DB mà không cleanup | Dữ liệu rò giữa tests | Transaction rollback/reset |
| Spring context reuse nhưng container đã stop | Connection refused ở test sau | Đồng bộ context/container lifecycle |
| Không pin JDBC driver | Khác binding behavior | Pin driver phù hợp |
| Không theo dõi database version | Debug khó | Log metadata/version |
| Benchmark container nhỏ rồi gán p99 production | Sai kết luận | Test performance riêng |
| Dùng production data không masking | Rò PII | Synthetic fixtures/masking |
| Mở Docker socket cho code không tin cậy | Rủi ro host | CI security policy |
| Không phân biệt infra error và DB assertion | Flaky builds khó điều tra | Logs/stages rõ |
| Bật container cho mọi pure unit test | Build chậm | Test pyramid |

## 39. Bài tập thực hành

### Bài 1 — Chọn database cho query JSONB

Ứng dụng dùng PostgreSQL `payload @> ...::jsonb`. Team chỉ chạy test trên H2.

**Câu hỏi:** Test này chứng minh được PostgreSQL syntax/semantics chưa?

**Đáp án:** Chưa. Cần PostgreSQL container hoặc một PostgreSQL instance test phù hợp.

### Bài 2 — H2 tương đương khi nào?

Một service chỉ có pure arithmetic domain methods, không dùng EntityManager.

**Đáp án:** Thậm chí không cần database; dùng unit test.

### Bài 3 — Port

CI có hai jobs chạy Postgres Testcontainers song song.

**Hỏi:** Có nên ép cả hai vào host port 5432?

**Đáp án:** Không. Dùng mapped ports/JDBC URLs từ container.

### Bài 4 — Schema owner

Test chạy migrations rồi Hibernate `ddl-auto=create`.

**Đáp án:** Không phù hợp để kiểm tra migration production contract; để JPA không tạo/xóa và chạy migrations thật.

### Bài 5 — L1 cache

Test `em.persist(p); em.find(id)` pass.

**Đáp án:** Có thể chỉ đọc từ L1; dùng `flush/clear` hoặc context mới để round-trip.

### Bài 6 — L2 cache

Sau `clear`, không thấy SQL SELECT.

**Đáp án:** L2 có thể được dùng; tắt/bypass hoặc đo SQL nếu mục tiêu yêu cầu.

### Bài 7 — UNIQUE race

Hai transactions cùng chọn SKU chưa có rồi insert.

**Đáp án:** DB UNIQUE constraint mới là cơ chế cưỡng chế cuối dưới concurrency; test với two transactions trên DB thật.

### Bài 8 — @Version

Hai biến cùng `em.find(Product.class,id)` trong một EM.

**Đáp án:** Không phải two-transaction optimistic locking test; cần EM A/EM B và commits độc lập.

### Bài 9 — FK

`@JoinColumn(nullable=false)` có mặt trong entity nhưng production migration thiếu FK.

**Đáp án:** Test dùng migrations thật và database constraints, không chỉ nhìn annotation.

### Bài 10 — CHECK

`Product.changePrice()` từ chối negative price. Team cho rằng database CHECK đã được xác nhận.

**Đáp án:** Không. Test DB CHECK riêng bằng SQL/JDBC hoặc cấu hình bỏ qua domain/Bean Validation phù hợp.

### Bài 11 — Deferred constraint

`flush()` thành công nhưng `commit()` ném lỗi.

**Đáp án:** Có thể do deferred constraint; test phải kiểm tra đúng thời điểm.

### Bài 12 — Sequence

Test hard-code Product ID thứ hai bằng 2 sau rollback.

**Đáp án:** Không ổn định; sequence có thể không rollback.

### Bài 13 — Migration upgrade

Migrations chạy tốt trên DB trống nhưng production có data legacy.

**Đáp án:** Thêm upgrade test từ schema cũ chứa dữ liệu và kiểm tra backfill.

### Bài 14 — Timezone

Test dùng `LocalDateTime` ở JVM UTC nhưng production session timezone khác.

**Đáp án:** Cần test timestamp semantics theo policy trên DBMS thật và cấu hình timezone liên quan.

### Bài 15 — Testcontainers version

Dự án nâng Testcontainers major, PostgreSQLContainer import cũ không còn khớp.

**Đáp án:** Kiểm tra module/package API của đúng version, không mix dependency và sample từ major khác.

### Bài 16 — CI không có daemon

Local tests pass, CI báo không thể kết nối Docker daemon.

**Đáp án:** Đây là infrastructure configuration failure, không chứng minh JPA query sai; runner cần container runtime phù hợp.

### Bài 17 — RLS

Test dùng PostgreSQL superuser rồi xác nhận tenant policy cho runtime app.

**Đáp án:** Chưa đủ vì privileged role có thể bypass RLS. Test với role/permissions gần production.

### Bài 18 — Index

PostgreSQL container có 20 Products; `EXPLAIN` dùng seq scan dù index tồn tại.

**Đáp án:** Không nhất thiết lỗi. Dataset nhỏ có thể khiến seq scan rẻ hơn. Test index existence và benchmark workload riêng.

### Bài 19 — Connection pool

Session tenant setting còn tồn tại khi pooled connection được tái sử dụng.

**Đáp án:** Cần test transaction-local context/reset, không chỉ schema/permissions.

### Bài 20 — Production parity

PostgreSQL container cùng version nhưng production chạy trên replica topology với 1 TB data.

**Đáp án:** Container kiểm tra engine behavior quan trọng, không chứng minh replica lag, failover hoặc p99 ở production.

## 40. Câu hỏi tự kiểm tra

**1. Mục tiêu chính của việc dùng DBMS thật trong container là gì?**

Kiểm tra các hành vi phụ thuộc engine, dialect, schema, constraints và transactions bằng chính DBMS mục tiêu.

**2. H2 PostgreSQL mode có thay PostgreSQL hoàn toàn không?**

Không.

**3. Testcontainers có phải JPA provider không?**

Không. Nó quản lý containers phục vụ test; JPA vẫn chạy qua Hibernate/EclipseLink/provider khác.

**4. Vì sao pin PostgreSQL image version?**

Để tăng tính reproducible và xác định runtime đang kiểm tra.

**5. Vì sao không hard-code localhost:5432?**

Container có thể được map sang host port động và chạy song song.

**6. JDBC URL nên lấy ở đâu?**

Từ container instance đang chạy.

**7. @DataJpaTest có thể thay datasource bằng embedded DB không?**

Có thể tùy cấu hình; khi muốn PostgreSQL cần ngăn việc thay datasource ngoài ý định.

**8. @DynamicPropertySource dùng làm gì?**

Cung cấp datasource properties động cho Spring test context.

**9. @ServiceConnection là chuẩn JPA không?**

Không, là tính năng tích hợp Spring Boot khi được hỗ trợ.

**10. Vì sao nên chạy Flyway/Liquibase migrations trong tests?**

Để kiểm tra schema thực tế được production deploy, không chỉ schema provider tự sinh.

**11. Hibernate ddl-auto=validate có phải JPA chuẩn không?**

Không, là Hibernate/Spring setting.

**12. Vì sao không chạy create/drop sau migrations?**

Nó có thể phá schema hoặc che lỗi migration.

**13. Một migration từ DB trắng có kiểm tra backfill old data không?**

Không đủ.

**14. Kiểm thử commit visibility cần gì?**

Writer commit và reader transaction/persistence context mới.

**15. flush có nghĩa commit không?**

Không.

**16. clear có bảo đảm SQL SELECT không?**

Không; L2 cache có thể can thiệp.

**17. @Version test cần một EM hay nhiều EM?**

Thông thường cần ít nhất hai EM/transactions độc lập để tạo conflict.

**18. Tại sao test constraints trên DB thật?**

Để xác nhận constraint thực tế và thời điểm database kiểm tra, không chỉ metadata/validation.

**19. Khi nào constraint có thể thất bại ở commit?**

Khi DB định nghĩa/evaluate deferred constraint hoặc transaction semantics khác phù hợp.

**20. Transaction isolation có giống nhau giữa mọi DBMS không?**

Không.

**21. UNIQUE race có thể bị Java exists-check ngăn chắc không?**

Không.

**22. PostgreSQL JSONB test nên chạy ở đâu?**

Trên PostgreSQL thật, ví dụ container.

**23. Index scan có phải luôn xuất hiện khi index tồn tại không?**

Không; optimizer chọn plan theo chi phí và dữ liệu.

**24. Container có tự cung cấp production data volume không?**

Không.

**25. Container có tự mô phỏng replica failover không?**

Không.

**26. Test RLS cần lưu ý gì về DB role?**

Dùng role/permissions tương đương runtime app, tránh bypass.

**27. Test migration nên bắt đầu ở trạng thái nào?**

Ít nhất từ DB trắng; với upgrade còn cần trạng thái cũ có dữ liệu.

**28. Vì sao sequence IDs có gaps?**

Rollback, concurrency và allocation semantics có thể không hoàn lại sequence values.

**29. Static @Container có ưu điểm gì?**

Giảm startup so với khởi tạo per-method, nếu test data isolation đúng.

**30. Vì sao không mặc định bật container reuse cho CI?**

Có nguy cơ state rò và khó đảm bảo fresh disposable test environment.

**31. Container runtime socket có rủi ro gì?**

Thường cấp quyền mạnh trên host, cần CI security controls.

**32. Vì sao không copy production data tùy tiện?**

Có thể lộ PII/secrets; nên dùng synthetic fixtures hoặc masking đúng policy.

**33. Khi nào cần JDBC direct assertion?**

Khi kiểm tra physical DB constraints/values/triggers hoặc query ngoài ORM cache.

**34. Java unit test có cần DB container không?**

Không nếu nó chỉ kiểm tra logic thuần Java.

**35. Nguyên tắc chọn database test quan trọng nhất?**

Dùng đúng DBMS/version khi yêu cầu tính đúng phụ thuộc DBMS; hiểu rõ những khác biệt với production vẫn còn.

## 41. Kịch bản tổng hợp: từ JPA test H2 đến PostgreSQL container

Một nhóm xây Catalog API bằng Spring Data JPA/Hibernate và triển khai trên PostgreSQL.

### 41.1. Giai đoạn ban đầu

Team chạy:

```text
@DataJpaTest
  -> H2 in-memory
  -> Hibernate creates schema
  -> repository.save(product)
  -> repository.findById(id)
```

Tests xanh, nhưng production deployment gặp lỗi:

- Migration thiếu `product_id_seq`.
- Unique constraint khác mong đợi.
- Native JSONB query sai cast.
- Date/time conversion khác.
- Một lock timeout chỉ xuất hiện với concurrent writes.

### 41.2. Xác định phạm vi test mới

Team không cần chuyển mọi unit test sang PostgreSQL. Họ thêm **JPA PostgreSQL contract tests** cho:

1. Migrations.
2. Entity round-trip.
3. ID generation.
4. Foreign keys và unique/check constraints.
5. JSONB native queries.
6. Commit visibility.
7. Optimistic/pessimistic locking.
8. Transaction rollback và error mapping.

### 41.3. Cấu hình mới

```text
JUnit / @DataJpaTest
       |
       v
PostgreSQL Testcontainers
       |
       v
Flyway migrations
       |
       v
Hibernate validate (optional, provider-specific)
       |
       v
JPA repository tests
```

### 41.4. Thêm test âm

Ngoài case “tạo Product thành công”, test:

- Trùng SKU.
- Category ID không tồn tại.
- Giá âm khi bypass domain validation.
- ID sequence thiếu hoặc sai.
- JSONB query với filter thực.
- Stale `@Version`.
- Hai transactions cùng sửa record.
- Connection/session settings khi test RLS.

### 41.5. Tạo test data xác định

Fixtures gồm một Category, nhiều Products, các giá trị BigDecimal ranh giới, JSON payload đa dạng, một record có timestamp với timezone policy rõ.

### 41.6. Phân biệt kết luận

**Những gì có thể nói:**

- Mapping và migrations chạy trên PostgreSQL version đã pin.
- Các constraints, JSONB queries và transactions đã được test trên engine đó.
- Một số lỗi chỉ có trên PostgreSQL có cơ hội được phát hiện trước deploy.

**Những gì chưa thể nói:**

- p99 của production sẽ bằng test container.
- Replica/failover hoạt động đúng.
- Migration nâng cấp 1 TB data không khóa bảng quá lâu.
- App runtime role an toàn nếu test chỉ dùng superuser.
- Không còn rủi ro nào từ connection pool, network hoặc concurrency khác.

### 41.7. Hoàn thiện test strategy

Một pipeline trưởng thành có thể:

```text
Every code change:
  pure unit tests
  JPA container integration tests
  migration-from-empty tests

When schema changes:
  migration upgrade tests with historical fixtures

When concurrency changes:
  locking/version/transaction tests

Before critical release:
  production-like performance and staging verification
```

Mỗi nhóm test trả lời một câu hỏi rõ ràng và tránh đánh đồng một container với toàn bộ production environment.

## 42. Checklist thiết kế thực dụng

Trước khi thêm container vào một JPA test suite, hãy tự hỏi:

1. **Feature cần đúng với DBMS nào?** PostgreSQL, MySQL hay một DB khác?
2. **Version đích là gì?** Có pin image/driver/provider không?
3. **Schema được tạo bằng gì?** Migrations hay JPA schema generation?
4. **Test dùng database thật không?** Có kiểm tra datasource/metadata thực tế không?
5. **Có dùng đúng transaction boundaries không?** Rollback hay commit?
6. **Có kiểm soát L1/L2 cache không?** Test `persist/find` có đọc lại state không?
7. **Có test constraints thực, không chỉ annotations không?**
8. **Có dùng hai EntityManagers/connections cho concurrency không?**
9. **Có dữ liệu edge cases và dữ liệu cũ cho migrations không?**
10. **Có test role/permission nếu dùng RLS không?**
11. **Có test timezone/collation/decimal/JSON khi domain cần không?**
12. **Có tránh hard-code host port, credentials thật và `latest` image không?**
13. **Có xác định container lifetime và cleanup không?**
14. **CI runner có container runtime được quản trị đúng quyền không?**
15. **Có phân biệt infrastructure fail và assertion fail không?**
16. **Có biết giới hạn production parity còn lại không?**
17. **Có giữ unit tests độc lập với Docker khi không cần DB không?**
18. **Có ghi version/setting để tái hiện lỗi không?**

Checklist này giúp xác định test contract; nó không buộc mỗi test phải khởi động mọi loại service.

## 43. Kết luận

**Dùng hệ quản trị thật trong container** là một kỹ thuật quan trọng trong kiểm thử JPA khi ứng dụng phụ thuộc vào hành vi của DBMS cụ thể. Nó cho phép chạy queries, JDBC bindings, constraints, migrations và transactions trên **cùng engine** với production thay vì một database chỉ mô phỏng hoặc dùng dialect khác.

Những nguyên tắc cần ghi nhớ:

1. **Database in-memory không phải bản sao đầy đủ của DBMS production.** Compatibility modes chỉ giải quyết một phần khác biệt.
2. **Chọn DBMS và version theo hành vi cần chứng minh.** Pin image, driver và JPA provider để kết quả dễ tái hiện.
3. **Chạy migrations thật trong integration tests** khi migrations là nguồn tạo schema ở production.
4. **Không để JPA create/drop ghi đè schema sau migrations** rồi kết luận schema production đã đúng.
5. **Kết nối tới host/port do Testcontainers cung cấp**, không hard-code địa chỉ cổng.
6. **Xác minh DataSource thực sự đang dùng container**, nhất là khi Spring test slice có thể thay bằng embedded DB.
7. **Kiểm tra INSERT/UPDATE/DELETE, quan hệ, converters và database constraints qua round-trip**, với `flush/clear` và cache controls phù hợp.
8. **Dùng transactions độc lập để test locking, optimistic conflicts và commit visibility**; rollback-only test không chứng minh dữ liệu đã commit.
9. **Test các tính năng DB-specific trên chính engine đó**, ví dụ PostgreSQL JSONB/RLS, partial indexes và deferred constraints.
10. **Phân biệt correctness tests và performance tests.** Một container ít dữ liệu không mô phỏng production query plans hay p99 latency.
11. **Giữ test data và container lifecycle cô lập**, tránh flaky tests do fixtures rò, sequence assumptions hoặc Spring context reuse.
12. **Đừng sao chép secrets/PII production vào container** và bảo vệ quyền container runtime trong CI.
13. **Nhớ giới hạn production parity:** data volume, topology, replication, managed-service settings, network, roles và concurrency vẫn cần các test khác.

Đích đến không phải “mọi test đều dùng Docker”, mà là một chiến lược kiểm thử có lớp lang: **unit tests nhanh cho logic thuần Java, JPA integration tests trên DBMS thật cho database semantics, migration/concurrency tests cho tính đúng khi thay đổi và những thử nghiệm production-like cho hiệu năng/vận hành**. Khi mỗi lớp có mục đích rõ, những lỗi chỉ xuất hiện với database thật sẽ được phát hiện sớm hơn mà không làm toàn bộ bộ kiểm thử trở nên chậm và khó bảo trì.
