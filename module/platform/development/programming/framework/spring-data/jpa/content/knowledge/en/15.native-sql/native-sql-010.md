# Testing Correctness and Database Portability of Native SQL in Spring Data JPA

Native SQL lets you take advantage of a database management system's syntax and features, but it also couples the application more directly to the database. A query that passes on H2 is not guaranteed to work on PostgreSQL, MySQL, or MariaDB. Even when returning the same data, databases can differ in data types, collation, `NULL` handling, pagination, date/time functions, and constraints.

Good testing requires verifying two distinct dimensions:

- **Correctness:** the SQL statement returns the right rows, order, data types, total count, and edge-case handling.
- **Database portability:** the query, mappings, migrations, and transaction behavior work across each DBMS that the application commits to supporting.

This lesson builds a paginated native query repository, runs a shared contract test suite against both PostgreSQL and MariaDB using Testcontainers, and then explains how to extend coverage to schema migrations and common SQL differences.

## 1. Distinguishing Levels of Portability

"Portable" can mean different things. Clarify at which layer the application requires portability:

| Scope | Question to Answer | How to Test |
|---|---|---|
| Database portability | Does the same SQL run on all target databases? | Run integration tests on each target database |
| Schema portability | Do entities, column types, indexes, constraints, and migrations produce a valid schema? | Run migrations on a real database, then validate the schema |
| Result mapping portability | Do native query results map properly to entities/DTOs? | Check types, nulls, aliases, and returned values |
| Provider portability | Does the query work with both Hibernate and EclipseLink? | Run the same contract tests with each JPA provider if both are supported |
| Version portability | Does the SQL run on all supported database versions? | Test against the minimum supported and production versions |

Native SQL does not offer the database independence of JPQL. Statements using vendor-specific functions, data types, or pagination syntax may run on only one DBMS. Therefore, before writing tests, explicitly document the exact list of databases and versions your application supports.

A test running with Hibernate and PostgreSQL only proves behavior for that combination. It does not prove the query works with EclipseLink or MariaDB.

## 2. What Should You Test in a Native Query?

Do not merely check that a repository method throws no exception. A meaningful test verifies both content and result semantics.

For a product listing query, check:

1. **Filter predicates:** only rows matching all predicates are returned.
2. **Boundaries:** whether boundary values are included, e.g., `>=` vs. `>`.
3. **Empty data:** the query returns an empty list or empty `Page` per contract.
4. **NULLs:** nullable columns containing `NULL` are handled properly.
5. **Tied values:** rows sharing the same price or date still sort deterministically.
6. **Ordering:** a unique tie-breaker prevents order from varying randomly across runs.
7. **Pagination:** page content, next-page flags, total elements, and total pages are consistent.
8. **Mapping:** numeric, boolean, date/time types, and column names map accurately.
9. **Parameters:** user input is bound as parameters, never concatenated into SQL.
10. **Transactions:** the query observes data consistent with the application's transaction boundaries and isolation level.

For queries returning `Page<T>`, test both the content query and `countQuery`. A page showing the right rows with an inaccurate `totalElements` is still a functional bug.

## 3. Paginated Native Query Example

Let us build a query fetching active products priced at or above a threshold. Results are sorted by ascending price, then by ID for deterministic ordering.

### 3.1. Product Entity

Create `Product.java`:

~~~java
package com.example.nativequery;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    protected Product() {
    }

    public Product(String name, BigDecimal price, boolean active) {
        this.name = name;
        this.price = price;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

This entity contains only basic columns to keep the example focused on native queries. In real projects, an entity may have additional associations or audit fields; if the query returns an entity, ensure `SELECT` supplies all mapped columns.

### 3.2. Repository With @Query(nativeQuery = true)

Create `ProductRepository.java`:

~~~java
package com.example.nativequery;

import java.math.BigDecimal;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query(
        value = """
                SELECT p.id, p.name, p.price, p.active
                FROM products p
                WHERE p.active = TRUE
                  AND p.price >= ?1
                ORDER BY p.price ASC, p.id ASC
                """,
        countQuery = """
                     SELECT COUNT(*)
                     FROM products p
                     WHERE p.active = TRUE
                       AND p.price >= ?1
                     """,
        nativeQuery = true
    )
    Page<Product> findActiveAtOrAbove(
            BigDecimal minimumPrice,
            Pageable pageable);
}
~~~

The query uses standard SQL elements: `SELECT`, `FROM`, `WHERE`, `AND`, comparison operators, `ORDER BY`, and `COUNT(*)`.

Query design decisions:

- `p.active = TRUE` selects only active products.
- `p.price >= ?1` includes products priced exactly at the threshold.
- `?1` is a positional parameter in Spring Data JPA query syntax; the value is bound, never concatenated into SQL.
- `ORDER BY p.price ASC, p.id ASC` guarantees deterministic ordering even when multiple products have the same price.
- `countQuery` applies the exact same filter conditions as the content query so `totalElements` is accurate.
- `Pageable` lets Spring Data and Hibernate apply pagination per the database dialect.

Because the result is the `Product` entity, `SELECT` lists all mapped columns: `id`, `name`, `price`, `active`. If the entity adds required columns or mapped associations, include the corresponding columns. Never `SELECT` a subset of columns and ask the provider to map them to a full entity.

### 3.3. Calling the Repository

~~~java
Page<Product> page = productRepository.findActiveAtOrAbove(
        new BigDecimal("50.00"),
        PageRequest.of(0, 20)
);

List<Product> products = page.getContent();
long total = page.getTotalElements();
int totalPages = page.getTotalPages();
~~~

Do not hardcode `LIMIT` or `OFFSET` in this example query. When using `Pageable`, Spring Data/Hibernate can generate pagination syntax tailored to the active dialect. Inspect the actual SQL if you change providers or use complex queries.

## 4. Running the Same Contract Test Across Multiple Databases

The most reliable way to test database portability is running an identical assertion suite against each target database. Testcontainers starts real databases inside containers, so tests exercise real SQL engines instead of emulators.

The example below uses PostgreSQL and MariaDB. Docker or a CI environment capable of running containers is required.

### 4.1. Maven Dependencies

With Spring Boot 3.x and Java 17+, add these dependencies to `pom.xml`. The Spring Boot parent manages Spring dependencies; Testcontainers can be managed via its BOM or given a single consistent version across all modules.

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>1.21.1</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>postgresql</artifactId>
        <version>1.21.1</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>mariadb</artifactId>
        <version>1.21.1</version>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.mariadb.jdbc</groupId>
        <artifactId>mariadb-java-client</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Container images in tests should be pinned close to production versions. If production runs PostgreSQL 16.4 and MariaDB 11.4.4, use those exact tags in CI rather than `latest`.

### 4.2. Writing a Shared Contract Test

Create `ProductNativeQueryContract.java`. This base test class contains the sample fixture and assertions every database must satisfy:

~~~java
package com.example.nativequery;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;

abstract class ProductNativeQueryContract {

    @Autowired
    protected ProductRepository products;

    @Autowired
    protected TestEntityManager entityManager;

    protected void verifiesNativeQueryContract() {
        products.saveAll(List.of(
                new Product("Keyboard", new BigDecimal("80.00"), true),
                new Product("Mouse", new BigDecimal("50.00"), true),
                new Product("Monitor", new BigDecimal("200.00"), true),
                new Product("Cable", new BigDecimal("10.00"), true),
                new Product("Inactive", new BigDecimal("60.00"), false),
                new Product("USB Hub", new BigDecimal("80.00"), true)
        ));

        entityManager.flush();
        entityManager.clear();

        Page<Product> first = products.findActiveAtOrAbove(
                new BigDecimal("50.00"),
                PageRequest.of(0, 2)
        );

        assertThat(first.getContent())
                .extracting(Product::getName)
                .containsExactly("Mouse", "Keyboard");

        assertThat(first.getTotalElements()).isEqualTo(4);
        assertThat(first.getTotalPages()).isEqualTo(2);

        Page<Product> second = products.findActiveAtOrAbove(
                new BigDecimal("50.00"),
                PageRequest.of(1, 2)
        );

        assertThat(second.getContent())
                .extracting(Product::getName)
                .containsExactly("USB Hub", "Monitor");

        assertThat(second.getTotalElements()).isEqualTo(4);
    }
}
~~~

The dataset deliberately tests specific edge cases:

- `Mouse` has price equal to threshold `50.00` to test `>=`.
- `Cable` is priced below threshold to test price filtering.
- `Inactive` meets the price threshold but is inactive to test the boolean predicate.
- `Keyboard` and `USB Hub` share price `80.00` to test the `id` tie-breaker.
- Four qualifying products verify two pages of content and total element counts.

`flush()` sends setup data to the database. `clear()` evicts the persistence context so query results are not confused with already-managed entity instances. Assertions check content, ordering, and the count query.

### 4.3. Running the Contract Test Against PostgreSQL

Create `ProductNativeQueryPostgresTest.java`:

~~~java
package com.example.nativequery;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@DataJpaTest(properties = "spring.jpa.hibernate.ddl-auto=create-drop")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class ProductNativeQueryPostgresTest
        extends ProductNativeQueryContract {

    @Container
    static final PostgreSQLContainer<?> DATABASE =
            new PostgreSQLContainer<>("postgres:16.4-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", DATABASE::getJdbcUrl);
        registry.add("spring.datasource.username", DATABASE::getUsername);
        registry.add("spring.datasource.password", DATABASE::getPassword);
    }

    @Test
    void nativeQueryWorksOnPostgreSql() {
        verifiesNativeQueryContract();
    }
}
~~~

`@AutoConfigureTestDatabase(replace = NONE)` tells Spring to keep the Testcontainers datasource rather than replacing it with an embedded database. `@DynamicPropertySource` injects the container's JDBC URL and credentials into the Spring context.

### 4.4. Running the Same Contract Test Against MariaDB

Create `ProductNativeQueryMariaDbTest.java`:

~~~java
package com.example.nativequery;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MariaDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@DataJpaTest(properties = "spring.jpa.hibernate.ddl-auto=create-drop")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class ProductNativeQueryMariaDbTest
        extends ProductNativeQueryContract {

    @Container
    static final MariaDBContainer<?> DATABASE =
            new MariaDBContainer<>("mariadb:11.4.4");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", DATABASE::getJdbcUrl);
        registry.add("spring.datasource.username", DATABASE::getUsername);
        registry.add("spring.datasource.password", DATABASE::getPassword);
    }

    @Test
    void nativeQueryWorksOnMariaDb() {
        verifiesNativeQueryContract();
    }
}
~~~

Both test classes share `ProductNativeQueryContract`. If a query passes on PostgreSQL but fails on MariaDB, the MariaDB test highlights the difference immediately. When adding support for a new database, create a test class configuring its container and invoke the same contract method.

Run:

~~~bash
mvn -Dtest=ProductNativeQueryPostgresTest,ProductNativeQueryMariaDbTest test
~~~

Testcontainers pulls images on first run and requires Docker to be running. In CI, images can be cached to reduce startup time. Pin images to production versions and update them intentionally.

The example above uses Hibernate's `create-drop` to focus on query testing. It does not validate the application's own migrations; the next section explains how to test real migrations.

## 5. Testing Schemas and Migrations on Each Database

A native query can be syntactically valid and still fail on the actual schema. Common causes include:

- Table/column names differing from what the query assumes.
- Column types differing between migrations and entities.
- Mismatched nullability or default values.
- Missing indexes or foreign keys.
- Migrations using database-specific syntax.
- Identifiers colliding with reserved keywords or differing in casing.

`ddl-auto=create-drop` only tests schemas generated by Hibernate from entities. It does not prove that the repository's migrations build the right schema.

In a real project's integration tests:

1. Start a clean database container.
2. Run Flyway or Liquibase migrations just as in production.
3. Set `spring.jpa.hibernate.ddl-auto=validate` so Hibernate validates mappings against the migrated schema.
4. Run the native query contract tests against that schema.
5. Verify required indexes, constraints, and seed data exist.

Example configuration when migrations are enabled in tests:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=true
~~~

These properties assume Flyway has been added and configured in the project. If using Liquibase, use its corresponding configuration. Never enable `create-drop` at the same time and conclude migrations were verified; Hibernate may generate the schema itself and mask broken migrations.

If a migration relies on PostgreSQL-specific syntax, organize migrations by vendor or supply per-database scripts using your migration tool's supported mechanism. Then run the same contract tests on each resulting schema. Portability must include DDL, not just `SELECT` statements.

## 6. SQL Differences That Easily Break Portability

The more vendor-specific features a native query uses, the higher the cost of cross-database testing.

| Area | Potential Differences | How to Handle |
|---|---|---|
| Pagination | `LIMIT/OFFSET`, `FETCH FIRST`, `TOP` syntax | Use `Pageable` when suitable; inspect SQL dialect |
| Booleans | Native boolean, `BIT`, `TINYINT`, varying literals | Use matching entity types and test literals on each DB |
| Strings | Concatenation, substring, trim, regex functions | Prefer common SQL functions or isolate queries per vendor |
| Case sensitivity | Collation and case-insensitive matching | Test mixed-case data and actual collation settings |
| NULLs | `NULLS FIRST/LAST`, default NULL ordering | Specify NULL order explicitly if supported; test per vendor |
| Date/time | Date functions, intervals, timezones, timestamp precision | Bind suitable Java temporal types; check timezone and precision |
| Decimals | Precision, scale, and rounding | Use `BigDecimal`, declare precision/scale, test boundary values |
| Identifiers | Reserved keywords, quoting, case rules | Avoid reserved words for table/column names; keep names simple |
| JSON/Arrays | Vendor-specific types and functions | Isolate queries per vendor or use a clean abstraction |
| Upsert | `ON CONFLICT`, `ON DUPLICATE KEY`, `MERGE` | Write per-database implementations and test the same contract |
| CTE/Window | Syntax support and version limits | Document minimum database version and test on that version |
| Generated keys | Identity, sequences, and key-return behavior | Use matching JPA mappings; test insert and readback |
| Locking | Lock modes, timeouts, and isolation | Test on the production target database, not just H2 |

### 6.1. Pagination and Deterministic Ordering

A query without `ORDER BY` makes no row-order guarantee. Even with `ORDER BY price`, rows sharing the same price can change order across runs.

Add a unique key as a tie-breaker:

~~~sql
ORDER BY price ASC, id ASC
~~~

Writing `LIMIT` manually in native SQL may restrict the query to certain databases. With repository methods accepting `Pageable`, Spring Data/Hibernate can translate pagination per dialect. Even then, test the query on each database and verify `countQuery`.

### 6.2. NULL and Comparison Operators

In SQL, `column = NULL` does not check for null values. Use:

~~~sql
WHERE deleted_at IS NULL
~~~

or:

~~~sql
WHERE deleted_at IS NOT NULL
~~~

`NULL` ordering inside `ORDER BY` can vary across databases. If business rules require nulls to appear last, express that in a way supported by your supported databases and verify actual ordering. Never assume all engines share the same default.

### 6.3. Collation and String Comparisons

One database may treat `ABC` and `abc` as equal under a case-insensitive collation, while another treats them as distinct. This affects search, unique constraints, and sorting.

If business logic requires case-insensitive matching, define normalization rules explicitly. `LOWER(column) = LOWER(?)` works across many databases, though it can impact index usage. Test both correctness and performance.

### 6.4. Date/Time and Timezones

Databases differ in timestamp types, timezone handling, fractional-second precision, and session timezone conversions.

When a native query filters a time range:

~~~sql
WHERE created_at >= ?
  AND created_at < ?
~~~

prefer half-open intervals `[start, end)` to prevent overlapping boundaries between adjacent ranges. Test values immediately before, exactly on, and immediately after boundaries; check the timezones configured in both the application and database.

### 6.5. Parameters and SQL Injection

Never concatenate request data directly into SQL:

~~~java
// Unsafe: the input string becomes part of the SQL statement.
String sql = "SELECT * FROM products WHERE name = '" + name + "'";
~~~

Use parameter binding:

~~~java
@Query(
    value = "SELECT p.id, p.name, p.price, p.active "
          + "FROM products p WHERE p.name = ?1",
    nativeQuery = true
)
List<Product> findByExactName(String name);
~~~

Parameters substitute values only—not table names, column names, or SQL keywords. If sorting by a user-chosen column is needed, map the choice through a code-defined whitelist of allowed column names; never concatenate arbitrary strings into `ORDER BY`.

### 6.6. Column Names and Quoting

Names like `order`, `user`, or `group` can be reserved keywords or carry special meaning in certain databases. Choose clear table/column names that avoid common keywords. If quoting identifiers is unavoidable, quoting syntax varies by database; test on each vendor.

## 7. Should Native Queries Return Entities or DTOs?

Result mapping is part of correctness.

### 7.1. Returning Entities

When a repository returns `Product`, the query must select all columns required by the entity mapping:

~~~sql
SELECT p.id, p.name, p.price, p.active
FROM products p
~~~

If the entity also maps `created_at` or associations, check the provider's result set requirements. Missing columns can trigger errors when hydrating entities.

Returned entities are managed inside the persistence context per JPA query rules. If you only need a few fields for display, loading entire entities is often unnecessary.

### 7.2. Returning DTOs From Native Queries

JPQL's `SELECT NEW ...` syntax is not valid native SQL. With native queries, you can use:

- Interface projections with column aliases matching getters.
- `@SqlResultSetMapping` combined with `@ConstructorResult`.
- Provider-specific mappings if coupling to Hibernate/EclipseLink is acceptable.

Interface projection example:

~~~java
public interface ProductRow {
    Long getProductId();
    String getProductName();
    BigDecimal getUnitPrice();
}
~~~

~~~java
@Query(value = """
       SELECT p.id AS productId,
              p.name AS productName,
              p.price AS unitPrice
       FROM products p
       WHERE p.active = TRUE
       ORDER BY p.id
       """, nativeQuery = true)
List<ProductRow> findActiveRows();
~~~

Aliases must be verified against the target provider and database. Some databases or providers alter how column labels or casing are returned; testing projections on each database catches mismatches early.

When using `@SqlResultSetMapping`, verify column names, JDBC types, and the DTO constructor. Do not assume mapping behaves identically simply because the SQL executes.

## 8. Verifying countQuery and Pagination

For `Page<T>`, the content query and count query must describe the exact same result set.

Content query example:

~~~sql
SELECT p.id, p.name, p.price, p.active
FROM products p
WHERE p.active = TRUE
  AND p.price >= ?
ORDER BY p.price ASC, p.id ASC
~~~

Corresponding count query:

~~~sql
SELECT COUNT(*)
FROM products p
WHERE p.active = TRUE
  AND p.price >= ?
~~~

If the content query joins a table causing one product to appear in multiple rows, `COUNT(*)` will count joined rows instead of products. In that case, consider `COUNT(DISTINCT p.id)` and how the content query deduplicates rows.

With `GROUP BY`, the count query usually needs to count groups rather than source rows. A dedicated count query or subquery suited to the target database may be necessary.

Minimum tests:

- First page has the exact expected rows and order.
- Next page neither duplicates nor skips rows.
- `totalElements` equals the logical result count.
- `totalPages` aligns with page size.
- When no rows match, the page is empty and total is `0`.
- Two rows sharing the same sort value maintain deterministic order.

If callers do not need total result counts, `Slice<T>` may fit better than `Page<T>` because it avoids computing total elements. Still, native queries returning `Slice` require testing pagination behavior and actual generated SQL.

## 9. Using H2 in Its Proper Role

H2 is great for fast local tests, but it cannot fully represent PostgreSQL, MySQL, or MariaDB.

H2 provides compatibility modes for several databases, yet those modes do not turn H2 into the actual SQL engine. Differences in functions, data types, collation, locking, query planners, DDL, and constraints can still surface.

A sound strategy:

- Use H2 for fast feedback on simple queries that do not rely on vendor-specific features.
- Use Testcontainers with real databases for critical native queries.
- Run tests on database versions matching production.
- Maintain shared contract tests to compare behavior across vendors.

Never conclude a query is portable simply because it passes on H2 with `MODE=PostgreSQL` or `MODE=MySQL`.

## 10. Checking Performance After Correctness Is Verified

A native query that returns right data can still be slow on a large database. Correctness tests and performance tests answer different questions.

After verifying correctness:

1. Check that indexes support filter and sort columns.
2. Run `EXPLAIN` or the database's equivalent tool to inspect the execution plan.
3. Test with production-scale data volumes, not just a handful of fixture rows.
4. Inspect the separate count query used by `Page`.
5. Measure latency and rows scanned/returned.
6. Check for N+1 queries if results are combined with entity relationships.

Do not compare execution plans textually between PostgreSQL and MariaDB; each database has a different optimizer. Define meaningful performance metrics such as latency, rows scanned, index utilization, and resource limits.

## 11. When Should You Accept Per-Database SQL Implementations?

Sometimes an application needs vendor-specific features like JSON operators, full-text search, upserts, arrays, or specialized CTEs. Forcing a single SQL string across all databases can make the query hard to read and inefficient.

In those cases:

1. Explicitly define which databases are supported.
2. Place vendor-specific SQL in dedicated repository fragments or database-specific adapters.
3. Keep a single shared contract at the service layer.
4. Run the same contract test suite against each implementation.
5. Run migrations and tests on each database.
6. Document the minimum database/version required by each implementation.

Portability can mean "consistent business behavior across dedicated implementations", not necessarily "one single SQL string". What matters is isolating and testing the differences.

## 12. Native SQL Testing Checklist

- [ ] Target supported databases and versions are explicitly defined.
- [ ] Queries use parameter binding; no input concatenated into SQL.
- [ ] Result mappings include all required columns and matching types.
- [ ] Tests cover filters, boundary values, `NULL`s, and empty result sets.
- [ ] Deterministic ordering enforced with a unique tie-breaker.
- [ ] Page content, next page, and count query tested.
- [ ] Same contract tests run on each target database.
- [ ] Tests use database versions close to production.
- [ ] Migrations run on a clean database before validating entity mappings.
- [ ] Portability is never inferred from H2 alone.
- [ ] Collation, timezones, decimal precision, and boolean mapping verified.
- [ ] DTO/interface projections verified for aliases and return types.
- [ ] Database-specific SQL isolated into dedicated implementations.
- [ ] Performance measured separately using realistic data and execution plans.

## 13. References

- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html) — declaring `@Query`, native queries, count queries, and projections.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html) — integrating containers with Spring Boot tests.
- [Testcontainers — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/) — running PostgreSQL in integration tests.
- [Testcontainers — MariaDB Module](https://java.testcontainers.org/modules/databases/mariadb/) — running MariaDB in integration tests.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — native SQL queries, parameter binding, and result mapping.

A native query can only be considered verified once tests confirm data, ordering, mapping, counts, and edge cases. Database portability must be proven by running the same contract tests and migrations on each DBMS the application supports. Testcontainers brings that verification into CI so SQL changes or database upgrades do not surface bugs only after deployment.