# How H2 Differs from Production Databases in Dialect, Data Types, and SQL Behavior

> **Module:** Spring Boot – testing  
> **Group:** Spring Data JPA  
> **Focus:** Why repository tests passing on H2 do not guarantee correct execution on PostgreSQL/MySQL/Oracle/SQL Server; picking the right database for each test type; verifying SQL dialect, data types, schema migrations, transactions, concurrency, and performance on the target engine.

## 1. Core Lesson

**H2 is its own database engine**, not an exact clone of PostgreSQL or other production databases. H2 runs fast in memory and is convenient for `@DataJpaTest`; however, its SQL parser, data types, transactions/locking, collations, DDL, and optimizer do not match real RDBMS engines identically.

```text
               THE SAME JPA ENTITY / REPOSITORY
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
      Test passes on H2        Does not automatically imply
                               equivalent behavior on PostgreSQL
```

For example, a simple `findByStatusOrderByIdAsc` may run cleanly on both engines, whereas native SQL using `jsonb`, `ON CONFLICT DO UPDATE`, `SKIP LOCKED`, or an expression index may only be valid on PostgreSQL. An H2 test running a Hibernate-generated schema does not prove production Flyway migration files execute cleanly.

**Solution:** keep H2 at the simple JPA smoke-test layer, while running real PostgreSQL/MySQL/Oracle/SQL Server or matching containers at the layer testing dialect, types, schemas, and transactions.

### 1.1. When Is H2 Still Useful?

H2 is valuable for:

- Testing basic JPA entity/relationship/enum mappings and persist–flush–clear–readback.
- Testing derived Spring Data repository queries and relatively portable JPQL/HQL.
- Testing simple constraints for quick feedback when exact production semantics are not required.
- Fast developer feedback on machines without Docker.
- CI smoke tests before running real-database integration test jobs.

H2 **should not be the sole evidence** when:

- Repositories contain `@Query(nativeQuery=true)` using engine-specific syntax.
- Schemas use PostgreSQL JSONB, arrays, UUID casts, `citext`, partial indexes, or extensions.
- The system relies on Flyway/Liquibase migrations, triggers, generated columns, or complex CHECK constraints.
- String comparisons depend on collations, timezones, numeric precision, or NULL ordering.
- Behavior involves locking, optimistic/pessimistic concurrency, upserts/idempotency, or deadlock retries.
- Queries risk slowdowns from production query planners/statistics/indexes.

## 2. Relevant Layers and What Tests Actually Prove

| Layer | Examples | What an H2 Test Can Prove | What It Does Not Prove |
| --- | --- | --- | --- |
| Java/domain | `PurchaseOrder`, `BigDecimal` | Object fields and domain logic | Real SQL/storage behavior |
| JPA mapping | `@Column`, `@Enumerated` | Hibernate maps cleanly to H2 schema | Matching DDL/types on PostgreSQL |
| Spring Data | `findByStatusOrderByIdAsc` | Derived query runs properly on H2 | SQL planner, collation, target behavior |
| JPQL/HQL | `select e from Entity e` | Hibernate translates and runs on H2 | Identical translation across all dialects |
| Native SQL | `@Query(nativeQuery=true)` | That specific SQL runs on H2 | PostgreSQL-specific syntax/semantics |
| JDBC driver | H2 JDBC | Reads/writes via H2 driver | PostgreSQL JDBC types/exceptions |
| Schema migration | Hibernate create/drop | Entities can generate an H2 schema | Real production Flyway/Liquibase scripts |
| Transactions | Rollback tests | Rollback inside H2 test context | PG races, deadlocks, lock timeouts |

Never equate `@DataJpaTest` with “testing the entire service”. It is a **JPA slice**: it loads entities, Spring Data repositories, `EntityManager`, and JPA/transaction infrastructure; business `@Service`/`@Controller` beans are normally not scanned. This keeps tests fast while scoping what they prove.

### 2.1. How Can a Green Test Give False Confidence?

Suppose production uses PostgreSQL, while local tests:

1. Have H2 on the test classpath.
2. `@DataJpaTest` picks or replaces the DataSource with H2.
3. Hibernate generates the schema using `ddl-auto=create-drop`.
4. Queries are derived queries that never touch native SQL or real DB indexes.
5. Tests pass.
6. Upon deployment, PostgreSQL migrations create different column types, a query calls an unsupported function, or a unique index fails.

The test in step 5 **is not wrong**; it simply covers a **narrower** contract than the reader imagined. QA reports must explicitly state which engine and schema were used.

## 3. Dialects: Hibernate-Generated SQL Differs Across Databases

`Hibernate Dialect` selects SQL forms per database engine: pagination, generated keys, casts, DDL, locking, function translations, and more. When connected to H2, Hibernate uses an H2 dialect; when connected to PostgreSQL, it uses the PostgreSQL dialect.

**Do not force `PostgreSQLDialect` onto a JDBC connection actually pointing to H2 and conclude you tested PostgreSQL.**

Anti-pattern example:

```properties
spring.datasource.url=jdbc:h2:mem:testdb;MODE=PostgreSQL
spring.jpa.database-platform=org.hibernate.dialect.PostgreSQLDialect
```

The generated SQL may use features H2 does not support; even if it runs, it still executes on the H2 engine. That provides zero evidence about PostgreSQL's planner, transaction locks, or extensions. The solid approach is using PostgreSQL Testcontainers when testing the PostgreSQL dialect.

### 3.1. H2 Compatibility Mode Only Emulates a Subset

H2 offers a PostgreSQL compatibility mode, for example:

```properties
spring.datasource.url=jdbc:h2:mem:compat;MODE=PostgreSQL;DATABASE_TO_LOWER=TRUE;DEFAULT_NULL_ORDERING=HIGH;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
```

Key settings:

- `MODE=PostgreSQL`: H2 emulates **a subset** of PostgreSQL syntax/behaviors.
- `DATABASE_TO_LOWER=TRUE`: alters case handling for unquoted identifiers.
- `DEFAULT_NULL_ORDERING=HIGH`: adjusts default NULL ordering closer to PostgreSQL.
- `DB_CLOSE_DELAY=-1`: keeps in-memory H2 alive until the JVM exits even if connections close.

**Limitation:** H2's own documentation states compatibility mode handles only a **small fraction** of differences. It does not turn H2 into PostgreSQL, nor guarantee parity for JSONB, partial indexes, extensions, MVCC, concurrency, or the query optimizer.

### 3.2. Named Identifiers and Case Folding

PostgreSQL normally folds unquoted identifiers to lowercase; regular H2 handles them differently, typically uppercasing them in metadata. Thus `purchase_orders`, `"Purchase_Orders"`, and `PURCHASE_ORDERS` should never be mixed carelessly.

Example:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY
);
```

A native query referencing a quoted mixed-case table name may fail on PostgreSQL even if local H2 accepts it. Adopt a consistent naming convention; when quotes or case-sensitive schemas exist, test on the target engine.

## 4. H2 vs. PostgreSQL by Difference Category

| Topic | H2 | PostgreSQL | Impact on Writing Tests |
| --- | --- | --- | --- |
| SQL grammar | Own SQL and compatibility modes | PostgreSQL SQL | Native queries must run on PG |
| Identity/sequence | H2 implementation | PostgreSQL identity/sequence | Never assert fixed IDs starting at 1 |
| JSON/JSONB | H2 JSON support | `json`, `jsonb`, operators/indexes | Never treat JSONB queries as tested on H2 |
| UUID | H2 UUID support | Native `uuid`, JDBC casts | Test parameter binding/casts on PG |
| Arrays | H2 ARRAY semantics | PostgreSQL arrays, `ANY`, `unnest` | Native arrays require PG |
| Numeric | H2 precision/rounding | PostgreSQL `numeric(p,s)` | Money/overflow needs the real DB |
| Timestamp | H2 datetime/zone rules | `timestamp`/`timestamptz` | Test UTC, offsets/precision on PG |
| Text/collation | H2 settings | Locale/collation/ICU/`citext` | Search, accents, casing, and ordering can differ |
| NULL sort | Depends on H2 config | PostgreSQL defaults NULLs high | Explicit NULL ordering and tie-breakers |
| Constraints | H2 unique/check/FK | PostgreSQL constraints/partial indexes/DEFERRABLE | Test real constraints after flush/commit |
| Transactions | H2 MVCC/locks | PostgreSQL MVCC/isolation/deadlocks | Run concurrency tests on PostgreSQL |
| Optimizer | H2 planner | PostgreSQL statistics/optimizer | Performance tests on PG with representative data |
| Migrations | Tests often auto-create | Flyway/Liquibase scripts | Must execute migrations on target engine |

### 4.1. JSONB and Database Functions

PostgreSQL supports JSONB operators:

```sql
SELECT payload ->> 'status' AS status
FROM outbox_events
WHERE payload @> '{"type":"order.created"}'::jsonb;
```

In this query:

- `->>` extracts a JSON value as text.
- `@>` checks JSONB containment.
- `::jsonb` performs a PostgreSQL cast.

H2 has a JSON type and a few functions, yet does not reproduce all PostgreSQL JSONB operators, GIN index/operator classes, or index selection behavior. If a repository uses JSONB, test with PostgreSQL Testcontainers.

### 4.2. Native UPSERT Differs Across Databases

A typical PostgreSQL UPSERT:

```sql
INSERT INTO purchase_orders(external_ref, amount, status, placed_on)
VALUES ('order-001', 25.50, 'NEW', DATE '2026-06-17')
ON CONFLICT (external_ref)
DO UPDATE SET amount = EXCLUDED.amount
RETURNING id;
```

H2 PostgreSQL mode supports some conflict forms like `ON CONFLICT DO NOTHING`, yet **never assume** `ON CONFLICT DO UPDATE`/`EXCLUDED`/`RETURNING` share PostgreSQL's syntax and semantics. For an idempotent order upsert, test on real PostgreSQL with two calls sharing `external_ref` and assert the final state.

An H2-only implementation using `MERGE` might pass locally while **failing to test** the actual SQL sent in production.

### 4.3. Arrays, `ANY`, and Custom Types

```sql
SELECT *
FROM products
WHERE category_id = ANY (?);
```

This is **illustrative JDBC SQL**: the `?` placeholder requires proper PostgreSQL array binding; passing a Java `List<Long>` does not automatically work in every case. H2 and PG differ on arrays, JSON, intervals, `citext`/`inet` types, and JDBC casts. Test null/empty arrays, duplicates, and parameter types on the target DB.

### 4.4. `ILIKE`, Accents, and Collation

```sql
SELECT *
FROM customers
WHERE email ILIKE '%example.test%';
```

`ILIKE` is PostgreSQL's case-insensitive match operator. Collation, accent sensitivity, and Unicode normalization can produce different search results between H2 and PostgreSQL or across two PostgreSQL databases with different collations.

If Vietnamese search must handle `lan/Lan`, `hoa/Hòa`, or pagination, test against the exact production collation/extensions. Never use H2 `IGNORECASE=TRUE` and treat it as equivalent to PostgreSQL `ILIKE`/ICU/`unaccent`.

### 4.5. NULL Ordering and Pagination

```sql
SELECT id, priority
FROM tasks
ORDER BY priority ASC NULLS LAST, id ASC;
```

PostgreSQL treats NULLs as larger than non-NULL values by default when sorting; H2 has its own defaults. When UI specs put nulls last, write explicit ordering instead of relying on defaults. Tie-breaker `id` keeps pagination stable when multiple rows share the same priority.

Likewise, asserting `containsExactly(...)` on a repository query **without an ORDER BY** is brittle: one DB may happen to return insertion order while another does not.

### 4.6. Unique Constraints and NULL

A unique index may allow multiple NULL entries or treat NULLs as duplicates depending on engine/schema. PostgreSQL 15+ supports `UNIQUE NULLS NOT DISTINCT`; H2 tests do not prove that migration or setting works. For critical business uniqueness, test both duplicate non-nulls and multiple nulls on a PostgreSQL container to verify the intended policy.

## 5. Data Values and SQL Types Can Alter Contracts

### 5.1. Money: `BigDecimal` vs. `NUMERIC(p,s)`

```java
@Column(nullable = false, precision = 12, scale = 2)
private BigDecimal amount;
```

The field above is an **illustrative snippet**; the full entity is in section 8. `BigDecimal` preserves exact decimal digits in Java, yet does not automatically guarantee:

- Whether the DB rounds or rejects values with too many fractional digits per contract.
- Whether the real column precision/scale matches the annotation.
- Whether the JDBC driver reads/writes identical scales.
- Whether H2 matches PostgreSQL `NUMERIC(12,2)` overflow/rounding behavior.

For money, test boundary values (0, max value, negatives if permitted, values with 3 decimal places) on the real DB. If business rules require strictly two decimal places, assert scale as well; if only numeric equality matters, use AssertJ `isEqualByComparingTo` rather than scale-sensitive `BigDecimal.equals`.

### 5.2. UUID/Native Casts

JPA mapping of `UUID` is usually straightforward, yet native queries like:

```sql
SELECT *
FROM customers
WHERE id = CAST(? AS uuid);
```

rely on PostgreSQL casting and JDBC binding. H2 supports UUIDs, but does not prove every PostgreSQL-specific expression. Test on the target DB whenever using native UUID operators or indexes.

### 5.3. Timestamps/Timezones

- `LocalDate`: calendar date without timezone.
- `LocalDateTime`: local date and time without timezone.
- `Instant`: UTC instant, ideal for recording moments in time when mapped consistently.
- `OffsetDateTime`: carries an offset, though PostgreSQL `timestamptz` normalizes the instant and **does not preserve the client's original offset string**.

Test with fixed timestamps such as `Instant.parse("2026-06-17T01:02:03Z")` and defined timezone/session settings. Never use `LocalDateTime.now()` as a fixed expected value. JDBC drivers, Hibernate, DB session timezones, and precision can all cause H2 to differ from PostgreSQL.

### 5.4. Enums and Custom JSON Mappings

`@Enumerated(EnumType.STRING)` stores enum names rather than ordinals; however, a PostgreSQL native `ENUM` is a separate DB type with its own DDL/driver binding rules. `@JdbcTypeCode(SqlTypes.JSON)` in Hibernate 6 maps JSON per dialect, while `columnDefinition="jsonb"` is explicitly PostgreSQL-specific.

When an app uses JSONB, enum types, arrays, or `citext`, write persist–flush–clear–reload and native query tests on PostgreSQL—not just Java object creation and field comparisons.

## 6. Hibernate-Generated DDL Differs from Production Schema Migrations

Separate these two scenarios:

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

Hibernate `ddl-auto=create-drop` generates a schema from entity metadata, which usually suffices for quick mapping tests. Yet a production schema may include:

- Partial/expression/GiST/GIN indexes.
- Custom constraints, triggers, stored procedures, policies.
- PostgreSQL extensions, partitions, generated columns.
- Custom identity/sequence behaviors.
- DDL naming, column defaults, collations, and stored types.
- Data migrations from older schema versions to newer ones.

### 6.1. Three Levels of Schema Verification

1. **H2 + Hibernate-generated schema:** smoke tests for JPA/derived queries.
2. **PostgreSQL container + Hibernate-generated schema:** tests PostgreSQL dialect and mappings, **without testing migration scripts**.
3. **PostgreSQL container + Flyway/Liquibase + Hibernate `validate`:** verifies the real migrated schema and entity compatibility.

When production uses migrations, level 3 is essential. Do not treat `ddl-auto=validate` as a complete index/trigger validator: it does not check every DB structure outside JPA mappings.

### 6.2. Avoid `ddl-auto=update` Masking Bugs

`update` can silently alter schemas so entities appear to work, hiding missing migrations. For migration tests, run the versioned scripts themselves with `spring.jpa.hibernate.ddl-auto=validate`, never letting Hibernate modify the schema. Never run `create`, `create-drop`, `update`, or `clean` against a production database.

## 7. `@DataJpaTest` and Which Database Is Actually Used

Spring Boot `@DataJpaTest` typically configures an embedded DB when H2/HSQL/Derby is present and conditions match. That does not mean the database is always H2 in every project; properties, custom DataSources, and test infrastructure can override the selection.

**Two intentional choices:**

```java
@DataJpaTest
class H2RepositoryTest {
    // If H2 is on the classpath, typically uses embedded DB.
}
```

```java
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class RealDatabaseRepositoryTest {
    // Use only when certain the DataSource points to a TEST-ONLY DB.
}
```

These two classes are **annotation examples**, not runnable tests. Never use `replace=NONE` just to make tests “more production-like” unless the DataSource is guaranteed to be test-only. In this article, `replace=NONE` is paired with PostgreSQL Testcontainers in section 9.

### 7.1. Why Not Trust the Config URL Alone?

An `application-test.yml` might specify an H2 URL while `@ServiceConnection`, `@DynamicPropertySource`, or environment variables override it. Conversely, `application.yml` might list a PostgreSQL URL while `@DataJpaTest` silently replaces it with H2. Tests should know **which DataSource is actually active** and, when testing PostgreSQL-only features, execute a PG-specific query on the container.

## 8. Runnable Maven Project: Basic H2 JPA Tests

This example uses **Java 17, Maven, Spring Boot 3.5.0**. This part requires only in-memory H2, no Docker. Tests use `TestEntityManager`, `flush/clear`, and explicit assertions.

### 8.1. File Structure

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

Each public class/enum sits in its matching file under `package com.example.dbcompare`. The PostgreSQL classes in section 9 are **optional extensions**, excluded from the base project until Docker dependencies are added.

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

`spring-boot-starter-data-jpa` provides JPA/Hibernate/Spring Data; `h2` in `test` scope is strictly for tests; `spring-boot-starter-test` provides JUnit Jupiter/AssertJ/TestEntityManager infrastructure. Boot BOM manages versions.

### 8.3. Application Entrypoint

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

**Design choices:** avoids naming the table `order` (a SQL keyword); unique constraint on business key; decimal amount; string-mapped enum status; and timezone-free date. This entity is simple enough to test on both H2 and PostgreSQL without external services.

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

Methods are **Spring Data derived queries**, not PostgreSQL native SQL. They are good candidates for H2 smoke tests alongside PostgreSQL checks where risk warrants.

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

**Meaning of each test:**

1. `roundTripPersistsAllFields` verifies field mappings and the derived find query on H2. `flush` sends SQL to the DB; `clear` removes managed entities from the persistence context so readback does not rely on cached managed objects.
2. `duplicateBusinessKeyIsRejectedByH2` verifies **H2's** unique constraint. Since exception wrappers vary across providers/drivers, the test checks root cause `SQLException` rather than locking onto a Hibernate-specific exception class.
3. `derivedQueryFiltersAndSortsExplicitly` verifies enum filtering and explicit `OrderByIdAsc` sorting without relying on default row ordering.

**Do not conclude:** PostgreSQL behaves identically for all native SQL, collations, migrations, locking, decimal boundaries, or query plans. The H2 sample project proves none of those.

### 8.8. Running the Base Project

Requires JDK 17+ and Maven:

```bash
java -version
mvn -version
mvn test
mvn -Dtest=PurchaseOrderH2Test test
```

There are **3 `@Test` methods** in the base project. Maven may download dependencies on the first run; neither Docker nor a PostgreSQL server is needed. No fixed stdout is guaranteed. If tests fail with `No suitable driver`, check the H2 test dependency and Spring DataSource auto-configuration.

## 9. PostgreSQL Testcontainers: Running the Real Target SQL Engine

When real PostgreSQL testing is needed, add a test class and container. The benefit is that PostgreSQL's real SQL parser, JSONB operators, data types, and transaction semantics execute—not H2's emulation.

### 9.1. Adding Dependencies

Add these entries to the base `pom.xml` (without duplicates):

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

Versions are managed by the Boot BOM. Docker or a Testcontainers-compatible runtime is required. If Docker is unavailable, PostgreSQL tests cannot run; never silently fall back to H2 and report PostgreSQL QA PASS.

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

**Analysis:**

- `@Testcontainers` activates the Testcontainers JUnit 5 extension; static `@Container` shares the container across test methods in the class.
- `@ServiceConnection` feeds Spring Boot connection details for the PostgreSQL instance without hardcoding ports or usernames.
- `@AutoConfigureTestDatabase(replace=NONE)` ensures the JPA slice **does not replace** the container DataSource with H2. H2 remains on the classpath, yet is not this test class's DB.
- `ddl-auto=create-drop` is only for mapping smoke tests on ephemeral PostgreSQL; it **does not** check Flyway scripts.
- Query `jsonb_build_object(...)->>...` is PostgreSQL-specific and proves the test is running against the target PostgreSQL SQL engine.
- The PostgreSQL image version is pinned in the example to reduce drift, and should align with your production major version.

### 9.3. Running Both Suites

```bash
docker info
mvn -Dtest=PurchaseOrderPostgresTest test
mvn test
```

After adding the Postgres class, the project has **5 test methods**: 3 H2 + 2 PostgreSQL. Running the PostgreSQL tests requires an active container runtime; no fixed stdout/port/logs are guaranteed. In CI, jobs need Docker permissions and must report skipped vs. failed states accurately.

### 9.4. Is a Full `@SpringBootTest` Necessary?

Not necessarily. `@DataJpaTest` defines the **bean scope**; the PostgreSQL container defines the **database engine**. You can run the JPA slice on PG to verify repositories/dialects faster than booting the entire app context.

When testing a full workflow across controllers, services, transactions, and repositories, use `@SpringBootTest` with a test-only DataSource/container while isolating outbound clients. A full-context test running on H2 still fails to verify PostgreSQL SQL behavior.

## 10. Going Further: Running Flyway/Liquibase on PostgreSQL

In section 9, Hibernate still generated the schema. If production uses migrations, add dedicated tests that execute the **actual migration scripts** on the PostgreSQL container.

### 10.1. Example SQL Migration

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

**This is a migration example for a PostgreSQL application**; do not drop it directly into section 8's H2 base project unless migration testing is configured. It contains PostgreSQL-oriented DDL and a production-like index.

### 10.2. Dependencies and Properties

With Flyway managed by Spring Boot 3.5, add the matching modules:

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

Migration tests on PostgreSQL aim for:

```properties
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=true
```

Workflow: supply PostgreSQL container DataSource → Flyway executes migrations → Hibernate validates mappings → tests verify repositories and schema constraints. Never combine `ddl-auto=create-drop` when proving migrations created the tables.

**Do not conclude `validate` checks every index, trigger, or partition.** It focuses on Hibernate entity/schema mapping within supported bounds; for critical indexes, extensions, or partial constraints, query PostgreSQL's catalog or test SQL behavior directly.

### 10.3. Migrations with Existing Data

A thorough migration test also checks upgrading from schema N to N+1:

1. Initialize the database at version N with sample data.
2. Apply the new migration.
3. Assert legacy rows remain intact and new constraints/indexes work.
4. Ensure proper rollback/repair paths if a migration fails.
5. Never run `flyway clean` or destructive DDL on production.

Run these tests against a PostgreSQL sandbox/container; never use production credentials to “make tests more realistic”.

## 11. Transactions, Flush, and Rollback: JPA Test Traps

### 11.1. Persist Does Not Necessarily Verify SQL

`EntityManager.persist` puts an object into the persistence context; SQL may be deferred until flush, or issued early under `GenerationType.IDENTITY` to fetch generated IDs. Avoid tying assertions solely to the moment `persist` returns.

```java
entityManager.persistAndFlush(order);
entityManager.clear();

PurchaseOrder loaded = repository
        .findByExternalRef("order-001")
        .orElseThrow();
```

This snippet assumes `entityManager` and `order` exist in a test, and is not a standalone program. `flush` forces pending SQL execution, and `clear` ensures the query proves a DB round trip instead of reading a managed entity.

### 11.2. Test Rollback Does Not Guarantee Every Side Effect Reverts

`@DataJpaTest` is transactional by default and rolls back after each test method. However:

- Sequence/identity counters do not necessarily reset after rollback; never assert IDs always start at 1.
- Another thread/transaction can commit independently.
- HTTP server threads in `@SpringBootTest(RANDOM_PORT)` do not share the test thread's transaction; test rollback does not delete data committed by the server.
- DDL/migrations have different rollback semantics than DML depending on engine.
- Schedulers, message consumers, and outbound network calls are not rolled back by the test transaction.

Use ephemeral databases, isolated fixtures, intentional cleanup, and never let tests touch production.

### 11.3. Unique Constraints and Races

Two requests can both observe `existsByExternalRef=false` and both try to insert. Single-threaded H2 tests prove only H2's unique constraint; to verify idempotency/race handling on PostgreSQL, use **two real connections/transactions** and coordination primitives like `CountDownLatch`/barriers, never flaky `Thread.sleep` guesses.

### 11.4. Locking

`SELECT ... FOR UPDATE`, `NOWAIT`, `SKIP LOCKED`, deadlocks, isolation levels, and lock timeouts depend on PostgreSQL MVCC. Example:

```sql
SELECT id
FROM outbox_events
WHERE delivered_at IS NULL
ORDER BY id
FOR UPDATE SKIP LOCKED
LIMIT 50;
```

When worker queues must claim disjoint jobs, write PostgreSQL concurrency tests running two transactions. H2 mock execution cannot prove rows will not be double-claimed.

## 12. Distinguishing Correctness from Performance

A test with 3 rows on a PostgreSQL container proves SQL syntax runs and returns expected rows. It **does not** prove queries stay fast with millions of rows, index fragmentation, table statistics, disk I/O, connection pool saturation, or concurrent writers.

Address performance separately:

- Use synthetic/anonymized representative datasets, never real customer data.
- Inspect indexes/migrations, query plans, and `EXPLAIN (ANALYZE, BUFFERS)` safely.
- Measure tail latency, load/concurrency, lock waits, and DB resource consumption.
- Avoid tight timing assertions in unit/CI tests that make suites flaky.
- Track SQL statement count baselines to catch N+1 ORM regressions.
- Remember that a container runs the real PostgreSQL engine, not production hardware, tuning, or load.

## 13. Database Selection Matrix by Test Objective

| Test Objective | Appropriate Choice | Evidence Gained |
| --- | --- | --- |
| Java business logic | JUnit + fake repository | Database-independent logic |
| Basic entity mappings | `@DataJpaTest` + H2 | H2 persist/readback |
| Portable derived repository queries | H2, plus PG when critical | Filter/order correctness across engines |
| PostgreSQL-native JSONB/UPSERT/UUID casts | PostgreSQL Testcontainers | Real SQL on PostgreSQL |
| Flyway migrations | PostgreSQL container + validate | Real migrated schema |
| Row-level locks/concurrency | PostgreSQL with 2+ transactions | Target race/lock behavior |
| Service + repository workflows | `@SpringBootTest` + test DB | Multi-layer application wiring |
| Query plans/performance | PostgreSQL with representative data | Index/latency/optimizer evidence |
| Production-like rollout | Isolated staging | Deployment-close migrations and behavior |

**Optimal strategy combines layers**, rather than picking one database for all testing. H2 tests run continuously; target-engine tests run in PR/main CI gates proportional to risk.

## 14. Common Symptoms and Fixes

| Symptom | Typical Cause | Resolution |
| --- | --- | --- |
| H2 passes, PostgreSQL throws syntax error | Native SQL dialect mismatch | Test the real SQL on PG container |
| H2 compatibility mode still lacks JSONB operator | Partial compatibility | PostgreSQL Testcontainers |
| H2 resolves lowercase table, PG reports missing relation | Identifier casing/quotes/naming | Naming conventions + PG schema tests |
| H2/PG return rows in different orders | Missing `ORDER BY` or differing NULL/collation rules | Explicit `ORDER BY`/tie-breakers |
| `@DataJpaTest` with container still hits H2 | Embedded datasource replacement | `@AutoConfigureTestDatabase(replace=NONE)` |
| `UUID`/`ARRAY` binding fails | JDBC driver/type differences | PG tests with native bindings |
| Migration fails after deploy | Tests used Hibernate `create-drop` instead of Flyway | PostgreSQL migration tests + `validate` |
| Unique constraint test shows no error | Missing flush or deferrable constraint | Flush/commit in proper transaction scope |
| `BigDecimal` rounded or overflows | `NUMERIC` precision/scale | Boundary tests on target DB |
| Time shifts after readback | Timezone/session/driver mapping | UTC/offset policy + PG tests |
| Post-rollback IDs do not start at 1 | Sequences do not roll back | Never assert fixed IDs |
| CI skips PostgreSQL tests | Missing Docker/runtime/pipeline split | Separate jobs; report failures/skips clearly |
| Fast on H2, slow in production | Different planner/indexes/statistics | PostgreSQL query-plan/performance tests |
| Two workers claim the same event | Lock/transaction race | PG concurrency tests |
| H2 works despite missing production index | Hibernate-generated schema differs from migrations | Catalog/index assertions on PG |

## 15. Anti-Patterns to Avoid

### 15.1. “H2 PASS Means PostgreSQL PASS”

No. It confirms only H2 under the test configuration.

### 15.2. “`MODE=PostgreSQL` Equals a PostgreSQL Server”

No. H2 docs state compatibility mode emulates only a subset of differences, without full PostgreSQL engine/extension/locking behavior.

### 15.3. “`ddl-auto=create-drop` Verified Our Migrations”

No. Hibernate-generated schemas do not verify that Flyway/Liquibase scripts actually work.

### 15.4. “Adding `@AutoConfigureTestDatabase(replace=NONE)` Is Always Better”

Dangerous if the DataSource points to production. Use it only when a test-only DB is provisioned and URLs/credentials are controlled (e.g., via Testcontainers).

### 15.5. “`save` Already Checked Constraints”

Not necessarily. SQL/DB constraints may be checked only at flush or commit; deferrable constraints require commit-boundary tests.

### 15.6. “`@Transactional` Cleans Up Everything”

No. Sequences, async tasks, separate threads/transactions, migrations, and outbound calls behave differently.

### 15.7. “Testcontainers Guarantees Production Performance”

No. The engine matches better, yet dataset sizes, stats, hardware, and networking do not match production.

### 15.8. “Rewrite Production Native SQL as H2 SQL So Unit Tests Pass”

You may test separate SQL branches, but you must also run **the exact production SQL** on the target engine. Never leave two unverified diverging query versions.

## 16. Repository and Migration Test Review Checklist

- [ ] Clearly identified the DB engine per test: H2, PostgreSQL container, or sandbox database.
- [ ] Avoided confusing H2 compatibility mode with real PostgreSQL.
- [ ] When PostgreSQL is intended, ensured DataSource is not silently replaced by embedded DB.
- [ ] No production credentials/URLs exist in tests.
- [ ] Entity tests use flush/clear/readback when verifying DB behavior.
- [ ] Checked constraints and key negative cases.
- [ ] Verified numeric precision, scale, timezones, enums, and UUID/JSONB where relevant.
- [ ] Native queries/functions/operators have tests on the target engine.
- [ ] Defined `ORDER BY`/NULL ordering/collation wherever the contract demands it.
- [ ] H2 tests and PostgreSQL tests report separately in CI.
- [ ] Clearly separated Hibernate-generated schemas from Flyway/Liquibase migrations.
- [ ] Migration tests execute actual scripts and validate the schema on PostgreSQL.
- [ ] Concurrency around locking/transactions/idempotency is tested on the real engine.
- [ ] Query correctness and performance are separate test suites.
- [ ] Avoided asserting generated IDs start at a fixed number after rollback.
- [ ] Never auto-create/drop/alter production schemas from CI tests.
- [ ] Reviewed Postgres image/version and test data strategy during database upgrades.

## 17. Exercises and Self-Check Questions

**Exercise 1:** Build the project in section 8, run `mvn test`, and explain what the three H2 tests prove. Identify one thing they **do not** prove, such as PostgreSQL JSONB behavior.

**Exercise 2:** Add PostgreSQL Testcontainers as in section 9 and run `mvn -Dtest=PurchaseOrderPostgresTest test`. Explain the distinct roles of `@ServiceConnection` and `@AutoConfigureTestDatabase(replace=NONE)`.

**Exercise 3:** Add a Flyway migration creating the table on PostgreSQL and switch a separate test to `ddl-auto=validate`. Verify the created schema and index; never let Hibernate `update` patch the schema.

**Exercise 4:** Write a PostgreSQL UPSERT using `ON CONFLICT DO UPDATE`, invoke it twice with the same business key, and assert row state. Distinguish “new insert” from “update existing row”.

**Exercise 5:** Write a query with `ORDER BY priority ASC NULLS LAST, id ASC`; run it on regular H2, H2 PG mode, and real PostgreSQL, recording observed results instead of guessing.

**Exercise 6:** Simulate two transactions concurrently inserting the same `external_ref` on a PostgreSQL container. Use coordination primitives with timeouts and verify the resulting constraint/idempotency behavior.

**Question 1.** Why doesn't `@DataJpaTest` on H2 guarantee PostgreSQL native queries work?

**Answer:** Native SQL is executed by H2's parser/dialect, not the PostgreSQL engine.

**Question 2.** Can `MODE=PostgreSQL` replace PostgreSQL Testcontainers entirely?

**Answer:** No. Compatibility mode covers only partial compatibility and does not reproduce all data types, operators, or locking behavior.

**Question 3.** Must `@DataJpaTest` always use H2?

**Answer:** No. It can use PostgreSQL Testcontainers with `replace=NONE` to keep a real test DataSource.

**Question 4.** Why is `ddl-auto=create-drop` insufficient for apps using Flyway?

**Answer:** It generates schema from Hibernate metadata, bypassing production's versioned migration scripts.

**Question 5.** Does `save` succeeding without a unique-key error mean the constraint works?

**Answer:** Not necessarily. SQL must be synchronized via appropriate flush/commit so the database checks the constraint.

**Question 6.** Why is asserting id equals 1 after rollback brittle?

**Answer:** Sequences/identity counters do not necessarily roll back alongside DML transactions.

**Question 7.** If a PostgreSQL container test passes, is production query speed proven?

**Answer:** No. Correctness tests do not replace representative-data/query-plan performance tests.

**Question 8.** When is H2 most valuable?

**Answer:** Fast-feedback JPA smoke tests and portable derived queries, paired with DB-specific integration tests based on risk.

## 18. Official References

- [H2 Database – Features and Compatibility Modes](https://h2database.github.io/html/features.html#compatibility): capabilities and limits of `MODE=PostgreSQL`.
- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@DataJpaTest`, transactions, and database replacement.
- [Spring Boot 3.5 – Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection` and database connection details.
- [Testcontainers for Java – PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): `PostgreSQLContainer`.
- [Testcontainers for Java – JUnit Jupiter Integration](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container` lifecycle.
- [PostgreSQL – SQL Data Types](https://www.postgresql.org/docs/current/datatype.html): NUMERIC, UUID, JSON/JSONB, date/time.
- [PostgreSQL – JSON Functions and Operators](https://www.postgresql.org/docs/current/functions-json.html): JSONB operators `->>`, `@>`.
- [PostgreSQL – Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): MVCC, transaction isolation, and concurrency.
- [Flyway Documentation](https://documentation.red-gate.com/fd): versioned migrations, migration history.

**In summary:** H2 is a great tool for fast testing of **relatively portable JPA**, yet **your production database remains the source of truth for its own dialect, data types, and SQL behavior**. Combine H2 tests, PostgreSQL Testcontainers, and migration integration tests, while always keeping test data isolated from production.