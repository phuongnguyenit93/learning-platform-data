# H2 khác database production ở dialect, kiểu dữ liệu và hành vi SQL

> **Module:** Spring Boot – testing  
> **Nhóm:** Spring Data JPA  
> **Trọng tâm:** Vì sao repository test chạy xanh trên H2 chưa bảo đảm chạy đúng trên PostgreSQL/MySQL/Oracle/SQL Server; chọn đúng database cho từng loại test; kiểm tra SQL dialect, data types, schema migration, transaction, concurrency và performance trên engine đích.

## 1. Bài học cốt lõi

**H2 là một database engine riêng**, không phải bản sao chính xác của PostgreSQL hay các database production khác. H2 chạy in-memory nhanh và thuận tiện cho `@DataJpaTest`; nhưng SQL parser, data types, transaction/locking, collation, DDL và optimizer của nó không hoàn toàn giống hệ quản trị thật.

```text
              CÙNG MỘT JPA ENTITY/REPOSITORY
                          |
              +-----------+-----------+
              |                       |
              v                       v
      H2 Test DataSource       PostgreSQL DataSource
      H2 JDBC Driver           PostgreSQL JDBC Driver
      Hibernate H2Dialect      Hibernate PostgreSQLDialect
      H2 SQL engine            PostgreSQL SQL engine
      H2 metadata/locks        PostgreSQL MVCC/indexes
              |                       |
              v                       v
      Test xanh trên H2       Không tự động suy ra kết quả
                              tương đương trên PostgreSQL
```

Ví dụ: một `findByStatusOrderByIdAsc` đơn giản có thể chạy đúng cả hai engine, còn native SQL dùng `jsonb`, `ON CONFLICT DO UPDATE`, `SKIP LOCKED` hoặc một expression index có thể chỉ hợp lệ trên PostgreSQL. Một test H2 chạy schema do Hibernate tự tạo không chứng minh file migration Flyway của production đã chạy đúng.

**Giải pháp:** giữ H2 ở tầng smoke test JPA đơn giản, đồng thời chạy PostgreSQL/MySQL/Oracle/SQL Server thực hoặc container tương ứng ở tầng kiểm thử phụ thuộc dialect, type, schema và transaction.

### 1.1. Khi nào H2 vẫn hữu ích?

H2 có giá trị cho:

- Test JPA entity/relationship/enum mapping cơ bản, persist–flush–clear–readback.
- Test derived Spring Data repository queries và JPQL/HQL tương đối portable.
- Test các ràng buộc đơn giản để nhận phản hồi nhanh, khi không cần semantics production chính xác.
- Developer feedback nhanh trên máy không có Docker.
- CI smoke tests trước khi chạy job integration test database thật.

H2 **không nên là bằng chứng duy nhất** khi:

- Repository có `@Query(nativeQuery=true)` dùng cú pháp riêng của engine.
- Schema có PostgreSQL JSONB, array, UUID casts, `citext`, partial indexes, extensions.
- Hệ thống dựa vào Flyway/Liquibase migrations, triggers, generated columns, CHECK constraints phức tạp.
- Có so sánh chuỗi theo collation, timezone, numeric precision hoặc NULL ordering.
- Có locking, optimistic/pessimistic concurrency, upsert/idempotency hoặc deadlock retry.
- Một query có thể bị chậm bởi planner/statistics/indexes của database production.

## 2. Các tầng liên quan và điều test thật sự chứng minh

| Tầng | Ví dụ | Điều H2 test có thể chứng minh | Điều chưa chứng minh |
| --- | --- | --- | --- |
| Java/domain | `PurchaseOrder`, `BigDecimal` | Object fields và domain logic | SQL/storage thật |
| JPA mapping | `@Column`, `@Enumerated` | Hibernate map được vào schema H2 | Cùng DDL/types với PostgreSQL |
| Spring Data | `findByStatusOrderByIdAsc` | Derived query chạy đúng trên H2 | SQL planner, collation, behavior target |
| JPQL/HQL | `select e from Entity e` | Hibernate chuyển query và chạy trên H2 | Mọi dialect translation giống nhau |
| Native SQL | `@Query(nativeQuery=true)` | SQL cụ thể chạy trên H2 | PostgreSQL-specific syntax/semantics |
| JDBC driver | H2 JDBC | Đọc/ghi trên driver H2 | PostgreSQL JDBC types/exceptions |
| Schema migration | Hibernate create/drop | Entity có thể tạo schema trong H2 | Flyway/Liquibase thực ở production |
| Transaction | Rollback test | Rollback test trong H2 context | Race, deadlock, lock timeout của PG |

Đừng đồng nhất `@DataJpaTest` với “test toàn bộ service”. Nó là một **JPA slice**: nạp các entity, Spring Data repositories, `EntityManager` và thành phần JPA/transaction liên quan; `@Service`/`@Controller` nghiệp vụ thường không được scan. Điều này giúp test nhanh nhưng giới hạn phạm vi.

### 2.1. Test xanh có thể là false confidence thế nào?

Giả sử production dùng PostgreSQL nhưng local test:

1. Có H2 trong test classpath.
2. `@DataJpaTest` tự chọn hoặc thay DataSource thành H2.
3. Hibernate tạo schema bằng `ddl-auto=create-drop`.
4. Query là derived query nên không đi qua native SQL/DB indexes thật.
5. Test pass.
6. Khi deploy, migration PostgreSQL tạo column type khác, query dùng hàm không hỗ trợ hoặc fail unique index.

Test ở bước 5 **không hề sai**; nó chỉ bảo vệ một hợp đồng **hẹp hơn** người đọc tưởng tượng. Báo cáo QA cần nêu rõ engine và schema được sử dụng.

## 3. Dialect: SQL do Hibernate tạo không giống mọi database

`Hibernate Dialect` là thành phần chọn một số SQL forms theo engine: pagination, generated keys, casts, DDL, locking, function translation và nhiều tính năng khác. Khi kết nối H2, Hibernate sử dụng dialect phù hợp H2; khi kết nối PostgreSQL, sử dụng dialect PostgreSQL.

**Không nên ép `PostgreSQLDialect` trên một JDBC connection thực sự đến H2 rồi kết luận đã test PostgreSQL.**

Ví dụ anti-pattern:

```properties
spring.datasource.url=jdbc:h2:mem:testdb;MODE=PostgreSQL
spring.jpa.database-platform=org.hibernate.dialect.PostgreSQLDialect
```

SQL được sinh có thể dùng chức năng H2 không hỗ trợ; nếu chạy được thì cũng chỉ chạy trên H2 engine. Đây không phải bằng chứng về PostgreSQL planner, transaction locks hay extensions. Cách vững chắc hơn là dùng PostgreSQL Testcontainers khi muốn kiểm thử dialect PostgreSQL.

### 3.1. H2 compatibility mode chỉ hỗ trợ một phần

H2 cung cấp PostgreSQL compatibility mode, ví dụ:

```properties
spring.datasource.url=jdbc:h2:mem:compat;MODE=PostgreSQL;DATABASE_TO_LOWER=TRUE;DEFAULT_NULL_ORDERING=HIGH;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
```

Ý nghĩa chính:

- `MODE=PostgreSQL`: H2 mô phỏng **một tập** cú pháp/hành vi PostgreSQL.
- `DATABASE_TO_LOWER=TRUE`: thay đổi cách xử lý case của unquoted identifiers.
- `DEFAULT_NULL_ORDERING=HIGH`: thay default ordering của NULL cho gần PostgreSQL.
- `DB_CLOSE_DELAY=-1`: giữ H2 in-memory cho tới khi JVM kết thúc dù các connections đóng.

**Giới hạn:** Chính tài liệu H2 nói compatibility mode chỉ xử lý **một phần nhỏ** khác biệt. Nó không làm H2 trở thành PostgreSQL, không bảo đảm đồng nhất JSONB, partial indexes, extensions, MVCC, concurrency hay query optimizer.

### 3.2. Named identifiers và case folding

PostgreSQL thường fold các identifier không đặt dấu quote về lowercase; H2 regular mode có cách xử lý khác, thường upper-case trong metadata. Vì vậy `purchase_orders`, `"Purchase_Orders"` và `PURCHASE_ORDERS` không nên được dùng lẫn lộn không kiểm soát.

Ví dụ:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY
);
```

Một native query dùng quoted mixed-case table name có thể fail trên PostgreSQL dù local H2 chạy. Hãy dùng naming convention rõ; khi có quotes hoặc case-sensitive schema cần test trên engine đích.

## 4. H2 vs PostgreSQL theo từng nhóm khác biệt

| Chủ đề | H2 | PostgreSQL | Hệ quả khi viết test |
| --- | --- | --- | --- |
| SQL grammar | Có SQL và compatibility modes riêng | PostgreSQL SQL | Native query phải chạy trên PG |
| Identity/sequence | H2 implementation | PostgreSQL identity/sequence | Không assert IDs cố định/từ 1 |
| JSON/JSONB | JSON support riêng | `json`, `jsonb`, operators/indexes | Không coi JSONB query đã được test trên H2 |
| UUID | Có UUID support | Native `uuid`, JDBC casts | Test parameter binding/casts trên PG |
| Arrays | H2 ARRAY semantics | PostgreSQL arrays, `ANY`, `unnest` | Native arrays cần PG |
| Numeric | H2 precision/rounding | PostgreSQL `numeric(p,s)` | Tiền/overflow cần DB thực |
| Timestamp | H2 datetime/zone rules | `timestamp`/`timestamptz` | Test UTC, offset/precision trên PG |
| Text/collation | Settings riêng | Locale/collation/ICU/`citext` | Search, accents, case và ordering có thể khác |
| NULL sort | Phụ thuộc H2 config | PostgreSQL mặc định NULL cao | Explicit NULL ordering/tie-breaker |
| Constraints | H2 unique/check/FK | PostgreSQL constraints/partial indexes/DEFERRABLE | Test constraints thực sau flush/commit |
| Transactions | H2 MVCC/locks | PostgreSQL MVCC/isolation/deadlocks | Concurrent test trên PostgreSQL |
| Optimizer | H2 planner | PostgreSQL statistics/optimizer | Performance test với PG và data đại diện |
| Migrations | Test thường auto-create | Flyway/Liquibase scripts | Bắt buộc chạy migration trên engine đích |

### 4.1. JSONB và database functions

PostgreSQL hỗ trợ JSONB operators:

```sql
SELECT payload ->> 'status' AS status
FROM outbox_events
WHERE payload @> '{"type":"order.created"}'::jsonb;
```

Trong query này:

- `->>` lấy một value JSON dưới dạng text.
- `@>` kiểm tra JSONB containment.
- `::jsonb` ép kiểu PostgreSQL.

H2 có JSON type và một số functions nhưng không tái tạo toàn bộ PostgreSQL JSONB operators, GIN index/operator classes hay cách optimizer chọn index. Nếu repository dùng JSONB, test với PostgreSQL Testcontainers.

### 4.2. Native UPSERT khác database

Một PostgreSQL UPSERT điển hình:

```sql
INSERT INTO purchase_orders(external_ref, amount, status, placed_on)
VALUES ('order-001', 25.50, 'NEW', DATE '2026-06-17')
ON CONFLICT (external_ref)
DO UPDATE SET amount = EXCLUDED.amount
RETURNING id;
```

H2 PostgreSQL mode hỗ trợ một số hình thức conflict như `ON CONFLICT DO NOTHING`, nhưng **đừng suy ra** `ON CONFLICT DO UPDATE`/`EXCLUDED`/`RETURNING` có cú pháp và semantics giống PostgreSQL. Nếu đây là idempotent upsert cho đơn hàng, cần test PostgreSQL thật với hai calls cùng external_ref rồi assert state cuối cùng.

Một implementation H2-only dùng `MERGE` có thể pass local nhưng **không** chứng minh production query được gửi giống vậy.

### 4.3. Arrays, `ANY` và custom types

```sql
SELECT *
FROM products
WHERE category_id = ANY (?);
```

Đây là **minh họa JDBC SQL**: dấu `?` cần binding PostgreSQL array chính xác; không phải cứ truyền Java `List<Long>` là driver hiểu mọi trường hợp. H2 và PG khác về arrays, JSON, interval, types `citext`/`inet` và JDBC casts. Hãy thử null/empty arrays, duplicates và parameter type trên target DB.

### 4.4. `ILIKE`, accents và collation

```sql
SELECT *
FROM customers
WHERE email ILIKE '%example.test%';
```

`ILIKE` là cú pháp case-insensitive của PostgreSQL. Collation, accent sensitivity và Unicode normalization có thể tạo kết quả search khác giữa H2/PostgreSQL hoặc giữa hai PostgreSQL databases với collation khác nhau.

Nếu chức năng search tiếng Việt cần xử lý `lan/Lan`, `hoa/Hòa` hoặc phân trang, test trên đúng collation/extension của production. Không dùng H2 `IGNORECASE=TRUE` rồi coi nó tương đương PostgreSQL `ILIKE`/ICU/`unaccent`.

### 4.5. NULL order và pagination

```sql
SELECT id, priority
FROM tasks
ORDER BY priority ASC NULLS LAST, id ASC;
```

PostgreSQL mặc định coi NULL lớn hơn non-NULL khi sort; H2 có thiết lập riêng. Khi UI yêu cầu null cuối cùng, viết ordering tường minh thay vì dựa vào default. Tie-breaker `id` giúp pagination ổn định khi nhiều rows cùng priority.

Tương tự, chỉ assert `containsExactly(...)` trên repository query **không có ORDER BY** là giòn: một DB có thể trả insertion order và DB khác thì không.

### 4.6. Unique constraints và NULL

Một unique index có thể cho nhiều NULL entries hoặc coi NULL trùng nhau tùy engine/schema. PostgreSQL 15+ có lựa chọn `UNIQUE NULLS NOT DISTINCT`; test H2 không tự chứng minh đúng migration hoặc cấu hình đó. Với business uniqueness quan trọng, tạo cases duplicate non-null và multiple null trên PostgreSQL container rồi kiểm tra đúng policy.

## 5. Dữ liệu và kiểu SQL có thể thay đổi contract

### 5.1. Tiền: `BigDecimal` vs `NUMERIC(p,s)`

```java
@Column(nullable = false, precision = 12, scale = 2)
private BigDecimal amount;
```

Field trên là **snippet minh họa**; entity đầy đủ ở phần 8. `BigDecimal` giúp giữ số thập phân chính xác trong Java nhưng không tự bảo đảm:

- DB sẽ làm tròn hay reject giá trị có quá nhiều chữ số theo đúng contract.
- Precision/scale của column thật giống annotation.
- JDBC driver đọc/ghi scale giống nhau.
- H2 có cùng overflow/rounding behavior với `NUMERIC(12,2)` PostgreSQL.

Với tiền, test boundary values (0, số lớn nhất, -nếu cho phép, giá trị có 3 số lẻ) trên DB thật. Nếu business yêu cầu đúng hai số lẻ, assert thêm scale; nếu chỉ yêu cầu numeric equality, dùng AssertJ `isEqualByComparingTo` thay vì `BigDecimal.equals` phụ thuộc scale.

### 5.2. UUID/native casts

JPA mapping `UUID` thường tương đối đơn giản, nhưng native query như:

```sql
SELECT *
FROM customers
WHERE id = CAST(? AS uuid);
```

phụ thuộc PostgreSQL casting/JDBC binding. H2 có UUID support nhưng không chứng minh mọi PostgreSQL-specific expression. Cần test DB đích nếu dùng native UUID operators hoặc indexes.

### 5.3. Timestamp/timezone

- `LocalDate`: ngày không có timezone.
- `LocalDateTime`: ngày giờ địa phương không chứa timezone.
- `Instant`: thời điểm UTC, thích hợp lưu sự kiện tức thời khi mapping nhất quán.
- `OffsetDateTime`: mang offset, nhưng PostgreSQL `timestamptz` có thể normalize thời điểm và **không giữ nguyên offset string của client**.

Test với mốc cố định như `Instant.parse("2026-06-17T01:02:03Z")` và timezone/session được định nghĩa. Không dùng `LocalDateTime.now()` làm expected cố định. JDBC, Hibernate, DB session timezone và precision đều có thể làm H2 khác PostgreSQL.

### 5.4. Enum và JSON custom mapping

`@Enumerated(EnumType.STRING)` dùng tên enum thay vì ordinal; nhưng PostgreSQL native ENUM là kiểu khác và có DDL/driver binding riêng. `@JdbcTypeCode(SqlTypes.JSON)` trong Hibernate 6 có thể map JSON theo dialect, song `columnDefinition="jsonb"` là một lựa chọn rõ PostgreSQL-specific.

Nếu app dùng JSONB, enum type, array hoặc `citext`, phải có test persist–flush–clear–reload và native query trên PostgreSQL, không chỉ tạo object/so sánh Java fields.

## 6. DDL do Hibernate tạo khác schema migration production

Hai kịch bản phải được tách:

```text
TEST H2                                      PRODUCTION PG
--------                                     -------------
@Entity                                      @Entity
   │                                           │
Hibernate ddl-auto=create-drop             Flyway/Liquibase V1..Vn
   │                                           │
H2 tables/columns/indexes                  PostgreSQL real schema
   │                                           │
Spring Data query succeeds                 Query can still fail or differ
```

Hibernate `ddl-auto=create-drop` tạo schema dựa trên metadata entity, thường đủ để test mapping nhanh. Nhưng production schema có thể có:

- Partial/expression/GiST/GIN indexes.
- Custom constraints, triggers, stored procedures, policies.
- PostgreSQL extensions, partitions, generated columns.
- Custom identity/sequence behaviors.
- DDL naming, column defaults, collations và stored types.
- Migration dữ liệu từ schema version cũ lên version mới.

### 6.1. Ba mức xác nhận schema

1. **H2 + Hibernate-generated schema:** smoke test JPA/derived queries.
2. **PostgreSQL container + Hibernate-generated schema:** test PostgreSQL dialect và mapping, **chưa kiểm tra migration scripts**.
3. **PostgreSQL container + Flyway/Liquibase + Hibernate `validate`:** kiểm tra schema thật được dựng bởi migrations và entity tương thích.

Nếu dùng migration ở production, tầng 3 có giá trị lớn. Đừng xem `ddl-auto=validate` là test index/trigger hoàn chỉnh: nó không bảo đảm kiểm tra tất cả cấu trúc DB ngoài mapping JPA.

### 6.2. Tránh `ddl-auto=update` để che lỗi

`update` có thể âm thầm sửa schema để entity chạy được, che việc thiếu migration. Với migration tests, dùng chính scripts versioned và cấu hình `spring.jpa.hibernate.ddl-auto=validate`, không tự sửa schema bằng Hibernate. Không chạy `create`, `create-drop`, `update` hoặc `clean` lên database production.

## 7. `@DataJpaTest` và chuyện database thật đang dùng

Spring Boot `@DataJpaTest` thường cấu hình embedded DB khi H2/HSQL/Derby có sẵn và conditions phù hợp. Nó không có nghĩa database hẳn là H2 trong mọi project; properties, custom DataSource và test infrastructure có thể thay đổi lựa chọn.

**Hai lựa chọn có chủ đích:**

```java
@DataJpaTest
class H2RepositoryTest {
    // Nếu H2 có trên classpath, thường là embedded DB.
}
```

```java
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class RealDatabaseRepositoryTest {
    // Chỉ dùng khi chắc chắn DataSource trỏ DB TEST-ONLY.
}
```

Hai class trên là **ví dụ annotation**, chưa phải tests runnable. Không dùng `replace=NONE` chỉ để làm test “giống production hơn” nếu DataSource chưa chắc chắn test-only. Trong bài, `replace=NONE` sẽ được kết hợp PostgreSQL Testcontainers ở phần 9.

### 7.1. Vì sao không nên chỉ tin config URL?

Một file `application-test.yml` có URL H2 nhưng `@ServiceConnection`, `@DynamicPropertySource` hoặc environment variables có thể override. Ngược lại, có thể có một PostgreSQL URL trong `application.yml` nhưng `@DataJpaTest` lại auto-replace bằng H2. Test cần biết **DataSource thực được dùng** và nếu có tính năng PostgreSQL-only hãy gọi một query đặc trưng PG trên container.

## 8. Dự án Maven chạy được: test H2 JPA cơ bản

Ví dụ sử dụng **Java 17, Maven, Spring Boot 3.5.0**. Phần này chỉ cần H2 in-memory, không cần Docker. Test dùng `TestEntityManager`, `flush/clear` và assertions cụ thể.

### 8.1. Cấu trúc tệp

```text
jpa-dialect-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/dbcompare/
    │   ├── DbCompareApplication.java
    │   ├── OrderStatus.java
    │   ├── PurchaseOrder.java
    │   └── PurchaseOrderRepository.java
    └── test/java/com/example/dbcompare/
        └── PurchaseOrderH2Test.java
```

Mỗi public class/enum nằm trong tệp cùng tên với `package com.example.dbcompare`. Các class PostgreSQL ở phần 9 là **bản mở rộng tùy chọn**, không nằm trong base project nếu chưa thêm Docker dependencies.

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>jpa-dialect-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-data-jpa` cung cấp JPA/Hibernate/Spring Data; `h2` ở test scope chỉ dành cho tests; `spring-boot-starter-test` cung cấp JUnit Jupiter/AssertJ/TestEntityManager test infrastructure. Boot BOM quản lý versions.

### 8.3. Application entrypoint

```java
// src/main/java/com/example/dbcompare/DbCompareApplication.java
package com.example.dbcompare;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DbCompareApplication {
    public static void main(String[] args) {
        SpringApplication.run(DbCompareApplication.class, args);
    }
}
```

### 8.4. `OrderStatus.java`

```java
// src/main/java/com/example/dbcompare/OrderStatus.java
package com.example.dbcompare;

public enum OrderStatus {
    NEW,
    PAID
}
```

### 8.5. `PurchaseOrder.java`

```java
// src/main/java/com/example/dbcompare/PurchaseOrder.java
package com.example.dbcompare;

import java.math.BigDecimal;
import java.time.LocalDate;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
        name = "purchase_orders",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_purchase_orders_external_ref",
                columnNames = "external_ref"))
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "external_ref",
            nullable = false, length = 64)
    private String externalRef;

    @Column(name = "amount", nullable = false,
            precision = 12, scale = 2)
    private BigDecimal amount;

    @Enumerated(EnumType.STRING)
    @Column(name = "status",
            nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "placed_on", nullable = false)
    private LocalDate placedOn;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            String externalRef,
            BigDecimal amount,
            OrderStatus status,
            LocalDate placedOn) {
        this.externalRef = externalRef;
        this.amount = amount;
        this.status = status;
        this.placedOn = placedOn;
    }

    public Long getId() { return id; }
    public String getExternalRef() { return externalRef; }
    public BigDecimal getAmount() { return amount; }
    public OrderStatus getStatus() { return status; }
    public LocalDate getPlacedOn() { return placedOn; }
}
```

**Mục đích thiết kế:** không đặt tên table `order` là SQL keyword; unique constraint cho business key, amount dạng decimal, status dạng enum string và date không có timezone. Entity này đủ đơn giản để test H2 và PostgreSQL mà không cần external service.

### 8.6. `PurchaseOrderRepository.java`

```java
// src/main/java/com/example/dbcompare/PurchaseOrderRepository.java
package com.example.dbcompare;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByExternalRef(
            String externalRef);

    List<PurchaseOrder> findByStatusOrderByIdAsc(
            OrderStatus status);
}
```

Các methods là **Spring Data derived queries**, không phải PostgreSQL native SQL. Nó là ứng viên tốt để smoke test H2 và test lại trên PostgreSQL ở rủi ro phù hợp.

### 8.7. `PurchaseOrderH2Test.java`

```java
// src/test/java/com/example/dbcompare/PurchaseOrderH2Test.java
package com.example.dbcompare;

import java.math.BigDecimal;
import java.sql.SQLException;
import java.time.LocalDate;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataJpaTest(
        showSql = false,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop")
class PurchaseOrderH2Test {

    @Autowired
    TestEntityManager entityManager;

    @Autowired
    PurchaseOrderRepository repository;

    private PurchaseOrder order(
            String reference, String amount, OrderStatus status) {
        return new PurchaseOrder(
                reference,
                new BigDecimal(amount),
                status,
                LocalDate.of(2026, 6, 17));
    }

    @Test
    void roundTripPersistsAllFields() {
        entityManager.persistAndFlush(
                order("order-001", "12.50", OrderStatus.NEW));
        entityManager.clear();

        PurchaseOrder loaded =
                repository.findByExternalRef("order-001")
                        .orElseThrow();

        assertThat(loaded.getId()).isNotNull();
        assertThat(loaded.getExternalRef()).isEqualTo("order-001");
        assertThat(loaded.getAmount())
                .isEqualByComparingTo("12.50");
        assertThat(loaded.getStatus()).isEqualTo(OrderStatus.NEW);
        assertThat(loaded.getPlacedOn())
                .isEqualTo(LocalDate.of(2026, 6, 17));
    }

    @Test
    void duplicateBusinessKeyIsRejectedByH2() {
        entityManager.persistAndFlush(
                order("duplicate", "10.00", OrderStatus.NEW));

        assertThatThrownBy(() ->
                entityManager.persistAndFlush(
                        order("duplicate", "20.00", OrderStatus.PAID)))
                .hasRootCauseInstanceOf(SQLException.class);
    }

    @Test
    void derivedQueryFiltersAndSortsExplicitly() {
        entityManager.persistAndFlush(
                order("order-101", "10.00", OrderStatus.NEW));
        entityManager.persistAndFlush(
                order("order-102", "20.00", OrderStatus.PAID));
        entityManager.persistAndFlush(
                order("order-103", "30.00", OrderStatus.NEW));
        entityManager.clear();

        assertThat(repository
                .findByStatusOrderByIdAsc(OrderStatus.NEW))
                .extracting(PurchaseOrder::getExternalRef)
                .containsExactly("order-101", "order-103");
    }
}
```

**Ý nghĩa từng test:**

1. `roundTripPersistsAllFields` kiểm tra mapping fields và derived find query trên H2. `flush` yêu cầu SQL được gửi tới DB, `clear` bỏ managed entities khỏi persistence context để readback không chỉ dựa object đang được quản lý.
2. `duplicateBusinessKeyIsRejectedByH2` kiểm tra ràng buộc unique của **H2**. Vì exception wrappers thay đổi theo provider/driver, test check root cause `SQLException` thay vì khóa cứng Hibernate exception class.
3. `derivedQueryFiltersAndSortsExplicitly` xác nhận repository filter enum và có thứ tự `OrderByIdAsc` rõ ràng. Không dựa vào default row ordering.

**Không kết luận:** PostgreSQL có cùng behavior cho mọi native SQL, collation, migrations, locking, decimal boundary và query plan. Project mẫu H2 không chứng minh các điều đó.

### 8.8. Chạy base project

Yêu cầu JDK 17+ và Maven:

```bash
java -version
mvn -version
mvn test
mvn -Dtest=PurchaseOrderH2Test test
```

Có **3 phương thức `@Test`** trong base project. Maven có thể cần tải dependencies lần đầu; không cần Docker hay PostgreSQL server. Không có stdout cố định được cam kết. Nếu test thất bại vì `No suitable driver`, xem H2 test dependency và Spring DataSource auto-configuration.

## 9. PostgreSQL Testcontainers: chạy đúng SQL engine đích

Khi cần test PostgreSQL thật, thêm một test class và container. Lợi ích là PostgreSQL SQL parser, JSONB operators, data types và transaction semantics đến từ engine thực, không phải mô phỏng của H2.

### 9.1. Bổ sung dependencies

Thêm các mục sau vào `pom.xml` base (không khai báo trùng):

```xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
```

Phiên bản được Boot BOM quản lý. Cần Docker/container runtime Testcontainers hỗ trợ. Nếu Docker không khả dụng, PostgreSQL test không thể chạy; không được âm thầm quay sang H2 rồi tuyên bố PostgreSQL QA PASS.

### 9.2. `PurchaseOrderPostgresTest.java`

```java
// src/test/java/com/example/dbcompare/PurchaseOrderPostgresTest.java
package com.example.dbcompare;

import java.math.BigDecimal;
import java.time.LocalDate;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(
        showSql = false,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class PurchaseOrderPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    TestEntityManager entityManager;

    @Autowired
    PurchaseOrderRepository repository;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void repositoryMappingWorksOnRealPostgres() {
        entityManager.persistAndFlush(
                new PurchaseOrder(
                        "pg-order-001",
                        new BigDecimal("12.50"),
                        OrderStatus.NEW,
                        LocalDate.of(2026, 6, 17)));
        entityManager.clear();

        PurchaseOrder loaded =
                repository.findByExternalRef("pg-order-001")
                        .orElseThrow();

        assertThat(loaded.getId()).isNotNull();
        assertThat(loaded.getAmount())
                .isEqualByComparingTo("12.50");
        assertThat(loaded.getStatus())
                .isEqualTo(OrderStatus.NEW);
    }

    @Test
    void postgresJsonbOperatorIsAvailable() {
        String text = jdbc.queryForObject(
                "select jsonb_build_object('origin', 'container')"
                        + " ->> 'origin'",
                String.class);

        assertThat(text).isEqualTo("container");
    }
}
```

**Phân tích:**

- `@Testcontainers` kích hoạt Testcontainers JUnit 5 extension; static `@Container` dùng container cho các test methods của class.
- `@ServiceConnection` cho Spring Boot connection details đúng PostgreSQL instance, không hard-code port/username.
- `@AutoConfigureTestDatabase(replace=NONE)` bảo đảm JPA slice **không thay** DataSource container bằng H2. H2 vẫn có trên classpath nhưng không phải DB của test class này.
- `ddl-auto=create-drop` chỉ dùng cho smoke test mapping trên PostgreSQL ephemeral; **chưa** kiểm tra Flyway scripts.
- Query `jsonb_build_object(...)->>...` là PostgreSQL-specific và chứng minh khả năng chạy SQL engine PostgreSQL cần test.
- PostgreSQL image version được pin ở ví dụ để giảm biến động, nhưng nên căn chỉnh với major version của production.

### 9.3. Chạy cả hai bộ

```bash
docker info
mvn -Dtest=PurchaseOrderPostgresTest test
mvn test
```

Sau khi thêm class Postgres, project có **5 test methods**: 3 H2 + 2 PostgreSQL. Lệnh chạy PostgreSQL yêu cầu container runtime thực sự hoạt động; không có fixed stdout/port/log. Trong CI, job cần quyền Docker phù hợp và phải báo đúng tình trạng skip/fail.

### 9.4. Có cần full `@SpringBootTest` không?

Không nhất thiết. `@DataJpaTest` là **phạm vi bean**; PostgreSQL container là **loại database**. Bạn có thể dùng JPA slice trên PG để kiểm tra repository/dialect nhanh hơn full app context.

Khi cần kiểm tra một workflow đi qua controller, service, transaction và repository thật, dùng `@SpringBootTest` với test-only DataSource/container, đồng thời cô lập outbound clients. Một full-context test dùng H2 vẫn không kiểm tra PostgreSQL SQL behavior.

## 10. Nâng cao hơn: chạy Flyway/Liquibase trên PostgreSQL

Ở phần 9, Hibernate vẫn tự sinh schema. Nếu production dùng migrations, hãy có test riêng để thực thi **chính migration scripts** trên PostgreSQL container.

### 10.1. Ví dụ SQL migration

```sql
-- src/main/resources/db/migration/V1__create_purchase_orders.sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    external_ref VARCHAR(64) NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    placed_on DATE NOT NULL,
    CONSTRAINT uk_purchase_orders_external_ref
        UNIQUE (external_ref)
);

CREATE INDEX ix_purchase_orders_status_placed_on
    ON purchase_orders(status, placed_on);
```

**Đây là ví dụ migration cho một application PostgreSQL**, không đặt ngay vào base project H2 trong phần 8 nếu chưa chủ động cấu hình cách test migrations. Nó chứa PostgreSQL-oriented DDL và index production-like.

### 10.2. Dependencies và properties

Khi dùng Flyway do Spring Boot 3.5 quản lý, bổ sung các modules thích hợp:

```xml
<dependency>
    <groupId>org.flywaydb</groupId>
    <artifactId>flyway-core</artifactId>
</dependency>
<dependency>
    <groupId>org.flywaydb</groupId>
    <artifactId>flyway-database-postgresql</artifactId>
</dependency>
```

Test migration trên PostgreSQL có mục tiêu:

```properties
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=true
```

Quy trình: cấp DataSource PostgreSQL container → Flyway chạy migrations → Hibernate validate mapping → test repository và ràng buộc schema. Không dùng `ddl-auto=create-drop` đồng thời khi muốn chứng minh migration đã tạo tables.

**Đừng kết luận `validate` đã kiểm tra mọi index/trigger/partition.** Nó tập trung mapping Hibernate/schema ở phạm vi hỗ trợ; với index, extension hoặc partial constraints quan trọng, assert trực tiếp PostgreSQL catalog hoặc hành vi SQL.

### 10.3. Migration có dữ liệu cũ

Một bài migration test tốt còn kiểm tra chuyển từ schema N lên N+1:

1. Khởi tạo database ở version N với dữ liệu thử.
2. Chạy migration mới.
3. Assert hàng dữ liệu cũ còn đúng, constraints/index mới hoạt động.
4. Đảm bảo rollback/repair path phù hợp nếu migration thất bại.
5. Không dùng `flyway clean` hoặc DDL destructive trên production.

Đây là test trên PostgreSQL sandbox/container; không dùng production credentials để “tăng độ sát thực”.

## 11. Transaction, flush và rollback: những bẫy của test JPA

### 11.1. Persist không nhất thiết đã kiểm chứng SQL

`EntityManager.persist` đưa object vào persistence context; SQL có thể được gửi lúc flush, và với `GenerationType.IDENTITY` có thể insert sớm do cần generated ID. Không nên gắn assertion chỉ vào thời điểm gọi `persist`.

```java
entityManager.persistAndFlush(order);
entityManager.clear();

PurchaseOrder loaded = repository
        .findByExternalRef("order-001")
        .orElseThrow();
```

Đây là snippet từ một test có `entityManager`/`order` sẵn, không phải chương trình độc lập. `flush` buộc thực hiện pending SQL, `clear` giúp query kiểm chứng DB round trip thay vì chỉ đọc managed entity.

### 11.2. Rollback test không đảm bảo mọi side effect đảo ngược

`@DataJpaTest` mặc định transactional và rollback sau mỗi test method. Tuy nhiên:

- Sequence/identity IDs không nhất thiết được hoàn lại sau rollback; đừng assert ID luôn bắt đầu từ 1.
- Một thread/transaction khác có thể commit độc lập.
- HTTP server thread của `@SpringBootTest(RANDOM_PORT)` không tự dùng transaction test thread; rollback test không tự xóa data do server commit.
- DDL/migrations có behavior rollback khác DML theo engine.
- Scheduler/message consumer và outbound network calls không bị transaction test rollback.

Dùng database ephemeral, fixtures, cleanup có chủ đích và không cho tests chạm production.

### 11.3. Unique constraint và race

Hai request có thể cùng thấy `existsByExternalRef=false` rồi cùng insert. Test single-thread H2 chỉ chứng minh unique constraint trên H2; muốn xác minh idempotency/race xử lý đúng trên PostgreSQL, dùng **hai connections/transactions thật** và coordination tools như `CountDownLatch`/barriers, không dựa vào `Thread.sleep` may rủi.

### 11.4. Locking

`SELECT ... FOR UPDATE`, `NOWAIT`, `SKIP LOCKED`, deadlocks, isolation levels và lock timeouts phụ thuộc PostgreSQL MVCC. Ví dụ:

```sql
SELECT id
FROM outbox_events
WHERE delivered_at IS NULL
ORDER BY id
FOR UPDATE SKIP LOCKED
LIMIT 50;
```

Khi worker queue cần claim các jobs không trùng nhau, phải có PostgreSQL concurrency test xác minh kết quả dưới hai transactions. H2 mock execution không đủ để kết luận các rows không bị double-claimed.

## 12. Phân biệt correctness và performance

Một test với 3 records trên PostgreSQL container kiểm tra SQL có chạy và trả đúng. Nó **không** chứng minh query nhanh với vài triệu rows, index fragmentation, table statistics, disk IO, connection pool saturation hoặc concurrent writers.

Những việc cần làm riêng:

- Dùng representative dataset đã tổng hợp/ẩn danh, không dùng dữ liệu khách hàng thật.
- Kiểm tra indexes/migration, query plans và `EXPLAIN (ANALYZE, BUFFERS)` khi an toàn.
- Đo tail latency, load/concurrency, lock waits và database resource use.
- Tránh assertion thời gian cực chặt trong unit/CI tests dễ flaky.
- Giữ baseline về số SQL statements để phát hiện N+1 nếu là ORM performance risk.
- Phân biệt bản thân container có PostgreSQL engine thật với việc nó chạy trên hardware/tuning y hệt production.

## 13. Ma trận chọn database cho từng mục tiêu

| Mục tiêu test | Lựa chọn phù hợp | Bằng chứng nhận được |
| --- | --- | --- |
| Java business logic | JUnit + fake repository | Logic độc lập database |
| Entity mapping cơ bản | `@DataJpaTest` + H2 | Persist/readback H2 |
| Derived repository queries portable | H2, bổ sung PG khi quan trọng | Kết quả filter/order ở các engines |
| PostgreSQL-native JSONB/UPSERT/UUID casts | PostgreSQL Testcontainers | SQL thật trên PostgreSQL |
| Flyway migrations | PostgreSQL container + validate | Schema thật từ migrations |
| Row-level locks/concurrency | PostgreSQL với 2+ transactions | Race/lock behavior trên target |
| Service + repository workflow | `@SpringBootTest` + test DB | Nhiều tầng ứng dụng phối hợp |
| Query plan/performance | PostgreSQL với representative data | Index/latency/optimizer evidence |
| Production-like rollout | Staging biệt lập | Migration và behavior gần deployment |

**Tối ưu là kết hợp nhiều tầng**, không phải chọn một database cho mọi loại kiểm thử. Test H2 có thể chạy liên tục; test engine đích phải có trong PR/main CI tùy mức rủi ro.

## 14. Triệu chứng thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| H2 pass, PostgreSQL báo syntax error | Native SQL khác dialect | Test đúng SQL trên PG container |
| H2 compatibility mode vẫn thiếu JSONB operator | Compatibility không đầy đủ | PostgreSQL Testcontainers |
| H2 nhận lowercase table, PG báo không có relation | Identifier case/quotes/naming | Naming convention + PG schema test |
| H2/PG trả rows khác thứ tự | Query không ORDER BY hoặc NULL/collation khác | Explicit ORDER BY/tie-breaker |
| `@DataJpaTest` với container vẫn connect H2 | Embedded datasource replacement | `@AutoConfigureTestDatabase(replace=NONE)` |
| Query fail về `UUID`/`ARRAY` binding | JDBC driver/type khác | PG test với native bindings |
| Migration fail sau deploy | Test dùng Hibernate create-drop thay Flyway | Migration test PostgreSQL + validate |
| Unique constraint test không thấy lỗi | Chưa flush hoặc constraint deferrable | Flush/commit ở đúng transaction scope |
| BigDecimal bị làm tròn/overflow | NUMERIC precision/scale | Boundary tests trên DB target |
| Test nhận khác giờ sau đọc lại | Timezone/session/driver mapping | UTC/offset policy + PG test |
| ID sau rollback không bắt đầu từ 1 | Sequence không rollback | Đừng assert ID cố định |
| CI không chạy PostgreSQL test | Thiếu Docker/runtime/skip pipeline | Phân tách job, báo fail/skip rõ |
| Test nhanh trên H2, production chậm | Planner/index/statistics khác | PostgreSQL query-plan/performance test |
| Two-worker claim trùng event | Lock/transaction race | PG concurrency tests |
| H2 chạy được dù production không có index | Hibernate-generated schema khác migrations | Catalog/index assertions trên PG |

## 15. Những anti-pattern cần tránh

### 15.1. “H2 PASS nghĩa là PostgreSQL PASS”

Không. Nó chỉ xác nhận H2 dưới test configuration.

### 15.2. “`MODE=PostgreSQL` tương đương PostgreSQL server”

Không. H2 docs nói compatibility mode chỉ mô phỏng một phần differences. Không có đầy đủ PostgreSQL engine/extension/locking behavior.

### 15.3. “`ddl-auto=create-drop` đã xác nhận migration”

Không. Hibernate-generated schema không đồng nghĩa Flyway/Liquibase scripts đang chạy thật.

### 15.4. “Thêm `@AutoConfigureTestDatabase(replace=NONE)` luôn tốt hơn”

Nguy hiểm nếu DataSource trỏ production. Chỉ dùng khi đã cấp DB test-only và kiểm soát URL/credentials qua Testcontainers.

### 15.5. “`save` đã kiểm tra constraint”

Không nhất thiết. SQL/DB constraint có thể chỉ được kiểm tra khi flush hoặc commit; với deferrable constraints còn phải test transaction boundary.

### 15.6. “`@Transactional` tự dọn mọi dữ liệu”

Không. Sequence, async, thread/transaction khác, migration và outbound calls có semantics khác.

### 15.7. “Test trên Testcontainers bảo đảm production performance”

Không. Engine giống hơn nhưng dataset/stats/hardware và network không giống production.

### 15.8. “Đổi native SQL production thành H2 SQL để unit tests pass”

Bạn có thể kiểm tra các nhánh SQL riêng, nhưng phải có test chạy **cùng SQL production thực sự gửi** trên target engine. Không để hai phiên bản query tách rời không được verify.

## 16. Checklist review repository và migration tests

- [ ] Xác định rõ DB engine trong từng test: H2, PostgreSQL container, hoặc database sandbox.
- [ ] Không nhầm H2 compatibility mode với PostgreSQL thực.
- [ ] Khi cần PostgreSQL, DataSource không bị embedded replacement.
- [ ] Không dùng credentials/URL production trong tests.
- [ ] Test entity dùng flush/clear/readback khi xác minh DB behavior.
- [ ] Kiểm tra constraints và các negative cases quan trọng.
- [ ] Numeric precision, scale, timezone, enum, UUID/JSONB được kiểm tra khi liên quan.
- [ ] Native queries/functions/operators có test trên engine đích.
- [ ] ORDER BY/NULL order/collation được định nghĩa khi contract yêu cầu.
- [ ] H2 tests và PostgreSQL tests có báo cáo riêng trong CI.
- [ ] Hibernate-generated schema được phân biệt với Flyway/Liquibase migrations.
- [ ] Migration tests chạy actual scripts và validate schema trên PostgreSQL.
- [ ] Lock/transaction/idempotency concurrency được kiểm tra trên engine thật.
- [ ] Query correctness và performance là hai bộ kiểm thử khác nhau.
- [ ] Không assert generated ID bắt đầu từ một số cố định sau rollback.
- [ ] Không tự động tạo/xóa/sửa production schema trong CI test.
- [ ] Postgres image/version và test data strategy được review khi nâng cấp database.

## 17. Bài tập và câu hỏi tự kiểm tra

**Bài tập 1:** Dựng project ở phần 8, chạy `mvn test` rồi giải thích ba test H2 đang chứng minh điều gì. Hãy xác định một điều mà nó **không** chứng minh, ví dụ PostgreSQL JSONB behavior.

**Bài tập 2:** Thêm PostgreSQL Testcontainers như phần 9, chạy `mvn -Dtest=PurchaseOrderPostgresTest test`. Giải thích vai trò khác nhau của `@ServiceConnection` và `@AutoConfigureTestDatabase(replace=NONE)`.

**Bài tập 3:** Thêm Flyway migration tạo bảng trên PostgreSQL, chuyển test riêng sang `ddl-auto=validate`. Kiểm tra schema và index đã tạo; đừng cho Hibernate `update` tự sửa schema.

**Bài tập 4:** Viết PostgreSQL UPSERT `ON CONFLICT DO UPDATE`, gọi hai lần cùng business key và assert row state. Phân biệt case “insert mới” và “update row tồn tại”.

**Bài tập 5:** Viết query có `ORDER BY priority ASC NULLS LAST, id ASC`; thử trên H2 regular, H2 PG mode và PostgreSQL thật, ghi nhận kết quả thay vì giả định.

**Bài tập 6:** Mô phỏng hai transactions cùng insert `external_ref` trùng nhau trên PostgreSQL container. Dùng coordination primitives có timeout và bắt đúng constraint/idempotency behavior.

**Câu 1.** Vì sao `@DataJpaTest` trên H2 không bảo đảm PostgreSQL native query chạy đúng?

**Đáp án:** Native SQL được thực thi bởi H2 parser/dialect, không phải PostgreSQL engine.

**Câu 2.** Dùng `MODE=PostgreSQL` có thể bỏ toàn bộ PostgreSQL Testcontainers không?

**Đáp án:** Không. Mode chỉ là một phần compatibility, không tái hiện mọi data type/operator/lock behavior.

**Câu 3.** `@DataJpaTest` có bắt buộc dùng H2 không?

**Đáp án:** Không. Có thể dùng PostgreSQL Testcontainers và `replace=NONE` để giữ DataSource test thật.

**Câu 4.** Vì sao `ddl-auto=create-drop` không đủ cho ứng dụng dùng Flyway?

**Đáp án:** Nó tạo schema từ Hibernate metadata, bỏ qua versioned migration scripts của production.

**Câu 5.** Một `save` chưa gặp lỗi unique key có nghĩa constraint đúng không?

**Đáp án:** Chưa chắc. Cần đồng bộ SQL bằng flush/commit phù hợp để database kiểm tra constraint.

**Câu 6.** Vì sao assert id bằng 1 sau rollback dễ sai?

**Đáp án:** Sequences/identity counters không nhất thiết rollback cùng transaction DML.

**Câu 7.** Nếu PostgreSQL container test pass, đã chứng minh query nhanh ở production chưa?

**Đáp án:** Chưa. Test correctness không thay thế representative-data/performance plan tests.

**Câu 8.** Khi nào H2 có giá trị nhất?

**Đáp án:** JPA smoke tests/derived queries đơn giản cần feedback nhanh, kết hợp DB-specific integration tests theo rủi ro.

## 18. Tài liệu tham khảo chính thức

- [H2 Database – Features and Compatibility Modes](https://h2database.github.io/html/features.html#compatibility): khả năng và giới hạn `MODE=PostgreSQL`.
- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@DataJpaTest`, transaction và database replacement.
- [Spring Boot 3.5 – Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection` và database connection details.
- [Testcontainers for Java – PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): `PostgreSQLContainer`.
- [Testcontainers for Java – JUnit Jupiter Integration](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container` lifecycle.
- [PostgreSQL – SQL Data Types](https://www.postgresql.org/docs/current/datatype.html): NUMERIC, UUID, JSON/JSONB, date/time.
- [PostgreSQL – JSON Functions and Operators](https://www.postgresql.org/docs/current/functions-json.html): JSONB operators `->>`, `@>`.
- [PostgreSQL – Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): MVCC, transaction isolation và concurrency.
- [Flyway Documentation](https://documentation.red-gate.com/fd): versioned migrations, migration history.

**Tóm lại:** H2 là công cụ tốt để kiểm thử nhanh **JPA tương đối portable**, nhưng **database production mới là nguồn chân lý cho dialect, kiểu dữ liệu và hành vi SQL của chính nó**. Kết hợp H2 tests, PostgreSQL Testcontainers và migration integration tests, đồng thời luôn tách test data khỏi production.