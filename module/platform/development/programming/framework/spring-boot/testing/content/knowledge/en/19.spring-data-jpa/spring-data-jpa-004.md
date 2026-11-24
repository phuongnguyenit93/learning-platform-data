# Testing Derived Queries, JPQL, and Native Queries in Spring Data JPA

## Lesson Objectives

In Spring Data JPA, a repository typically has three ways to define queries: **derived queries** inferred from method names, **JPQL** written against Java entities/properties, and **native SQL** written directly against database tables/columns. All three can return seemingly identical data in a simple test, yet their evaluation mechanism, portability across database engines, pagination behavior, and hidden pitfalls differ.

For example, a test that merely calls `repository.findBySku("BK-001")` and checks `Optional.isPresent()` is insufficient to prove the query filters `active` status correctly, matches category names case-insensitively, preserves tie-breaking order when prices match, or avoids returning extra rows. For native queries, a green test on H2 **does not automatically prove** the SQL works on production PostgreSQL/MySQL.

After this lesson, you will be able to:

- Distinguish **derived queries**, **JPQL**, and **native SQL** by syntax and where they are interpreted.
- Name methods such as `findByCategoryIgnoreCaseAndActiveTrueOrderByPriceCentsAscSkuAsc`, `countBy...`, and `existsBy...`.
- Use `@Query` with JPQL, `@Param`, comparison operators, aggregate queries, and **constructor projections**.
- Use `@Query(nativeQuery = true)` with **table/column names**, bound parameters, entity results, and **Pageable/countQuery**.
- Design strong fixtures to catch filter bugs, boundary values, inactive records, equal-price tie-breaking, empty results, and pagination defects.
- Write `@DataJpaTest` with H2 and `TestEntityManager`, using `flush`/`clear` in the right places to observe real database state.
- Understand the default transaction/rollback of the JPA slice and why reading inside the same persistence context can produce misleading conclusions.
- Know when to replace H2 with **PostgreSQL/MySQL Testcontainers** and prevent an embedded DataSource from unintentionally replacing the container.
- Diagnose wrong property names, invalid JPQL entity names, wrong native SQL column names, projection type mismatches, pagination counts, query injection, and N+1 performance issues.
- Run a complete example with **Java 17, Spring Boot 3.3.5, Gradle, JUnit Jupiter, and Spring Data JPA**.

**Core principle:** A query test must use **expected values independent of the query under test**, run on **a database appropriate for the contract being protected**, and assert content as well as filter/ordering/pagination rules—not merely that “the query ran without throwing an exception”.

## 1. Three Query Styles: Same Interface, Different Languages

Suppose you have a Java entity:

~~~java
@Entity
@Table(name = "catalog_products")
public class CatalogProduct {
    // Java properties: sku, title, category, priceCents, active
}
~~~

This is an introductory snippet only. The full entity is in section 7.

### 1.1. Derived Query: From the Method Name

~~~java
List<CatalogProduct>
findByCategoryIgnoreCaseAndActiveTrueOrderByPriceCentsAscSkuAsc(
        String category);
~~~

Spring Data parses the method name into predicates/filters and sort ordering. For example:

- `findBy` requests matching entities.
- `CategoryIgnoreCase` filters `category` case-insensitively.
- `AndActiveTrue` filters `active = true`.
- `OrderByPriceCentsAscSkuAsc` sorts by `priceCents` ascending; on ties, by `sku` ascending.

This **is not SQL written inside Java**; Spring Data inspects entity properties and constructs the corresponding query. If you rename the field `priceCents` and forget to rename the method, the repository can fail immediately during Spring bean initialization because the property cannot be resolved.

### 1.2. JPQL: Against Entities and Java Properties

~~~java
@Query("""
    select p
    from CatalogProduct p
    where p.category = :category
      and p.active = true
      and p.priceCents >= :minimum
    order by p.priceCents asc, p.sku asc
    """)
List<CatalogProduct> findActiveCostingAtLeast(
        @Param("category") String category,
        @Param("minimum") long minimum);
~~~

In JPQL:

- `CatalogProduct` is the **entity name** (defaulting to the class name), not the table name `catalog_products`.
- `p.priceCents` is the **Java property**, not the `price_cents` column.
- `:category` and `:minimum` are bound named parameters.
- The JPA provider (e.g., Hibernate) translates JPQL into SQL per mapping/dialect.
- `>=` is an inclusive boundary, so products matching the minimum price are still returned.

If you write `from catalog_products` in JPQL without an entity named that, do not expect Hibernate to treat it as a table. Conversely, writing `price_cents` instead of `priceCents` in JPQL can fail because the property does not exist.

### 1.3. Native SQL: Against the Database Schema

~~~java
@Query(value = """
    SELECT *
    FROM catalog_products
    WHERE category = :category
      AND active = TRUE
    ORDER BY price_cents DESC, sku ASC
    """, nativeQuery = true)
List<CatalogProduct> findActiveNative(
        @Param("category") String category);
~~~

Native queries use **physical SQL table/column names**: `catalog_products`, `price_cents`, `active`. They can leverage dialect-specific functions, `CTE`s, window functions, or database extensions, though portability across H2/PostgreSQL/MySQL is lower than JPQL.

A native query returning `CatalogProduct` works only when the selected columns/result mapping suffice for Hibernate to construct the entity; avoid selecting fewer than the required columns and expecting the ORM to populate everything.

### 1.4. Comparison Table

| Criterion | Derived Query | JPQL | Native SQL |
| --- | --- | --- | --- |
| Syntax source | Repository method name | `@Query` string using entity/property | `@Query(nativeQuery=true)` string using table/column |
| Best suited for | Simple filters, counts, existence, basic sorting | Joins, DTO projections, aggregates, JPA expressions | Vendor-specific SQL, complex queries, targeted tuning |
| Common errors | Wrong property name or keyword | Wrong entity/property, type/projection | Wrong table/column name, dialect, alias, or count |
| Portability | Relatively good within JPA | Relatively good per JPQL/Hibernate support | More dependent on DB engine/dialect |
| Minimum tests | Exact record set, filters, sorting | Filters/boundaries, projections, aggregates | Real SQL, mapping, `countQuery`, dialect, pagination |
| Risk when testing only on H2 | Different collation/case/null semantics | Provider/dialect SQL translation can differ | Production native SQL may not run on H2 |

No single style is “always better”. Pick the simplest query type that expresses the contract clearly and meets performance needs, and write tests that protect the behavior.

## 2. What Does `@DataJpaTest` Test?

`@DataJpaTest` in Spring Boot 3.3 bootstraps a **JPA slice**. It typically:

- Scans JPA entities and Spring Data JPA repository interfaces.
- Configures JPA, Hibernate, and `EntityManager`.
- Creates an embedded database if a matching driver is on the test classpath.
- Runs tests inside a transaction by default and **rolls back after each test**.
- Allows injecting `TestEntityManager` to build fixtures.
- Does not automatically load all application `@Service`/`@Controller` beans like `@SpringBootTest`.

Example:

~~~java
@DataJpaTest
class CatalogRepositoryTest {
    @Autowired
    CatalogProductRepository repository;

    @Autowired
    TestEntityManager entityManager;
}
~~~

This is a test class snippet without test methods yet. The runnable project is in section 7.

### A Test Slice Is Not an HTTP Integration Test

The test invokes `repository.findBySku(...)` directly through the Spring Data JPA bean. It verifies derived/JPQL/native queries against the DB in the test context, yet **does not test** Spring MVC controllers, JSON responses, HTTP statuses, authentication filters, or a real API client.

If the requirement is “GET /api/products/{sku} returns HTTP 200 and the right JSON”, add an MVC/HTTP test at the appropriate layer. If the requirement is “JPQL returns active products with price >= minimum”, `@DataJpaTest` is focused and usually faster than a full context.

### Rollback Has Boundaries

By default `@DataJpaTest` opens a test transaction and rolls back. However, that rollback covers only data within the test-managed transaction; it does not automatically clear Redis caches, files, messages, or independently created transactions. With `@SpringBootTest(RANDOM_PORT)` receiving real HTTP requests, server transactions may commit outside the test transaction — requiring separate cleanup.

In this lesson, tests call the repository directly without sending HTTP requests, so fixtures created via `TestEntityManager` participate in the test transaction and are rolled back at the end of each method.

## 3. Fixtures Must Be Designed to Catch Bugs

A weak fixture:

~~~text
Only one product:
BK-001 | Java Essentials | books | 2500 | active=true
~~~

With a single row, many broken queries still pass:

- A query missing `active=true`.
- A query sorting in the wrong direction.
- A query using `>=` instead of `>`.
- A query filtering the wrong `category` when no other category exists.
- A native pagination `countQuery` that is wrong while page 0 still holds one record.

A stronger fixture, used in the runnable project:

| SKU | Title | Category | Price cents | Active |
| --- | --- | --- | ---: | --- |
| BK-001 | Java Essentials | books | 2500 | true |
| BK-002 | Spring Boot | books | 3900 | true |
| BK-003 | Legacy Java | books | 1800 | false |
| BK-004 | Java Practice | books | 3900 | true |
| GE-001 | USB Cable | gear | 1500 | true |
| GE-002 | Laptop Stand | gear | 5200 | true |

The fixture intentionally includes:

- **Three** active books and **one** inactive book.
- Two books with the same price **3900**, forcing the test to verify secondary sorting by `sku`.
- Another category `gear` to catch broken filters.
- Prices **2500 and 3900** to test inclusive boundaries.
- Titles containing “Java” in different positions, including an inactive record, to test `ContainingIgnoreCase`.
- SKUs guaranteed to exist and not exist.
- Sum of active book prices `2500 + 3900 + 3900 = 10300`.

**Expected values must come from the fixture specification**, not by calling the method under test to compute “expected”. For instance, `assertEquals(repository.countByCategory(...), repository.findByCategory(...).size())` can let two broken queries agree while both fail the spec.

## 4. Derived Queries: What Must Be Verified

### 4.1. `findBy...`: Present and Missing Data

~~~java
Optional<CatalogProduct> findBySku(String sku);
~~~

Two essential cases:

- `"BK-001"` → present and matching SKU/title/price.
- `"NO-SUCH-SKU"` → `Optional.empty()`, neither throwing arbitrarily nor returning another entity.

Do not stop at `isPresent()`; if the query accidentally returns another product, the test would still pass. When an entity has key contract fields, verify their values.

### 4.2. `IgnoreCase` and Logical Predicates

~~~java
List<CatalogProduct>
findByCategoryIgnoreCaseAndActiveTrueOrderByPriceCentsAscSkuAsc(
        String category);
~~~

Test with `"BOOKS"` even though the fixture stores `"books"`. Expected: `BK-001`, `BK-002`, `BK-004` in that order. Inactive `BK-003` **must not appear**. The `BK-002` and `BK-004` pair with equal prices verifies tie-breaking.

Asserting both the exact set and order catches bugs that `size() == 3` misses. For example, a buggy query returning `BK-001, BK-003, BK-004` still has size 3.

### 4.3. `ContainingIgnoreCase`

~~~java
List<CatalogProduct>
findByTitleContainingIgnoreCaseOrderBySkuAsc(String fragment);
~~~

With fragment `"JAVA"`, expect `BK-001`, `BK-003`, `BK-004` because all three titles contain “Java” in different positions. Inactive `BK-003` **is still returned** because the method name **does not include `ActiveTrue`**. This is an important assertion to avoid adding filters not required by the contract.

With a non-matching fragment, expect an empty list rather than null. `Containing` typically translates to a `LIKE` expression for substring matching; special-character escaping and collation details depend on the Spring Data JPA version and DB engine.

### 4.4. `countBy`, `existsBy`

~~~java
long countByCategoryAndActiveTrue(String category);
boolean existsBySku(String sku);
~~~

- `countByCategoryAndActiveTrue("books")` → 3.
- `countByCategoryAndActiveTrue("gear")` → 2.
- `existsBySku("BK-001")` → true.
- `existsBySku("unknown")` → false.

Do not test `existsBySku` by calling `findBySku` and comparing the two methods: if both map to the wrong property, they can agree while both fail the fixture.

### 4.5. `And`/`Or` Logic and Long Property Names

Spring Data parses method names into expressions. With combinations of `And` and `Or`, test **each branch and their intersection** to uncover logic bugs. When a query becomes too long or hard to read, JPQL or a Specification expresses predicates more clearly.

Example name:

~~~java
List<CatalogProduct>
findByCategoryAndActiveTrueOrSku(String category, String sku);
~~~

This is a **snippet not in the runnable repository**, used solely for explanation: readers very easily misinterpret operator grouping. Never write a test with only one record; add records isolated to each branch to verify exact precedence. When the business intent is `category AND (active OR sku = X)`, expressing it in `@Query`/Specification with explicit parentheses is much easier to review.

### 4.6. Nested Properties and Field Renaming

If an entity has `Customer customer` and `Customer.address.city`, Spring Data supports property traversal in method names. Underscores `_` are sometimes used to disambiguate property paths per Spring Data documentation. However, overly long names break easily during model refactors; tests should seed fixtures with customers across multiple cities and also unlinked cases.

**Do not assume SQL column names are used in derived method names.** `findByPriceCents` targets the Java property `priceCents`, not `price_cents`.

## 5. JPQL: Written Against the Model Instead of the SQL Schema

### 5.1. Named Parameters

~~~java
@Query("""
    select p from CatalogProduct p
    where p.category = :category
      and p.active = true
      and p.priceCents >= :minimum
    order by p.priceCents asc, p.sku asc
    """)
List<CatalogProduct> findActiveCostingAtLeast(
        @Param("category") String category,
        @Param("minimum") long minimum);
~~~

With `category="books"`, `minimum=2500`, expect `BK-001`, `BK-002`, `BK-004`. With `minimum=3900`, expect `BK-002`, `BK-004` and **not `BK-001`**. These cases catch:

- Forgetting the active filter.
- Mistaking `>=` for `>`.
- Filtering `category` incorrectly.
- Sorting price in the wrong direction.
- Missing a tie-breaker when two prices match.

**Named parameters** improve readability when multiple values are passed. `@Param("category")` matches `:category` in JPQL, not the column name.

### 5.2. `select new ...`: DTO Constructor Projection

When only SKU and price are needed, fetching the full entity is unnecessary:

~~~java
@Query("""
    select new com.example.jpaquery.SkuPrice(
        p.sku, p.priceCents)
    from CatalogProduct p
    where p.category = :category
      and p.active = true
    order by p.sku asc
    """)
List<SkuPrice> findActivePrices(
        @Param("category") String category);
~~~

`SkuPrice` is a Java record with constructor `(String,long)`. A JPQL **constructor expression** uses the fully qualified class name and matching argument order/types. Tests must verify SKU, price, and ordering—not just `list.size()`.

Some projections behave differently regarding constructors/aliases across Spring Data/Hibernate versions; if the constructor does not match, context validation or query execution can fail. Using a public record DTO with a clear constructor reduces ambiguity.

### 5.3. Aggregate `SUM` and Empty Results

~~~java
@Query("""
    select sum(p.priceCents) from CatalogProduct p
    where p.category = :category and p.active = true
    """)
Long totalPriceOfActiveProducts(
        @Param("category") String category);
~~~

For active books, the total is **10300**; for active gear, **6700**. However, when **no rows match**, SQL/JPA `SUM` typically returns **null**, not 0. Therefore the method declares `Long` (boxed) and the test asserts `assertNull` for a nonexistent category.

If the application contract requires 0, use `coalesce(sum(...), 0)` in JPQL or convert in the service **intentionally**; do not write tests expecting 0 while the query actually returns null.

### 5.4. JPQL Joins, `distinct`, and N+1

When an entity has a `@OneToMany` relationship, a join can produce multiple SQL rows per parent. A query like:

~~~java
@Query("""
    select p from ParentOrder p
    join p.items i
    where i.active = true
    """)
List<ParentOrder> findOrdersWithActiveItems();
~~~

This is a **theoretical snippet**, not part of the runnable project: it assumes `ParentOrder` and `OrderItem` entities. If an order has three active items, the join generates multiple SQL rows; depending on ORM deduplication and version, tests must verify the contract and consider `select distinct p`. Never seed only one item per order.

Do not assume “JPQL automatically avoids N+1”. Accessing lazy associations after the query can still trigger **N+1 selects**. When performance is part of the contract, add tests/SQL statement count checks using Hibernate statistics, `EntityGraph`/`join fetch`, or appropriate integration profiling; `@DataJpaTest` on a single unassociated entity does not test this.

## 6. Native SQL: Right Schema, Right Engine, and Right Count

### 6.1. Entity Mapping

~~~java
@Query(value = """
    SELECT *
    FROM catalog_products
    WHERE category = :category
      AND active = TRUE
    ORDER BY price_cents DESC, sku ASC
    """, nativeQuery = true)
List<CatalogProduct> findActiveNative(
        @Param("category") String category);
~~~

This statement uses the column `price_cents` and table `catalog_products`, rather than `CatalogProduct.priceCents` as in JPQL. In the demo, H2 accepts `TRUE` in boolean comparisons; PostgreSQL also supports `BOOLEAN`. If production MySQL maps booleans to `TINYINT`, verify the SQL and tests on real MySQL rather than relying on assumed compatibility.

Expected for active books ordered by descending price, then ascending SKU on ties: `BK-002`, `BK-004`, `BK-001`.

### 6.2. Named Parameters Prevent SQL Injection

~~~java
@Query(
    value = "SELECT * FROM catalog_products WHERE sku = :sku",
    nativeQuery = true)
CatalogProduct findOneNativeBySku(@Param("sku") String sku);
~~~

This is an illustrative snippet not in the runnable repository. `:sku` is a bind parameter; a user cannot turn `sku`'s value into new SQL operators merely by sending quotes. By contrast, direct string concatenation:

~~~java
// AVOID: user content goes directly into SQL syntax.
String sql = "SELECT * FROM catalog_products WHERE sku = '"
        + userInput + "'";
~~~

risks SQL injection and escaping bugs. **Bind parameters for values**; for dynamic sort columns or table names (which cannot be bound as value parameters), use an **allowlist** of permitted identifiers instead of concatenating raw input.

### 6.3. Native Pagination Requires `countQuery`

~~~java
@Query(
    value = """
        SELECT * FROM catalog_products
        WHERE category = :category
          AND active = TRUE
        ORDER BY price_cents ASC, sku ASC
        """,
    countQuery = """
        SELECT COUNT(*) FROM catalog_products
        WHERE category = :category
          AND active = TRUE
        """,
    nativeQuery = true)
Page<CatalogProduct> findNativePage(
        @Param("category") String category,
        Pageable pageable);
~~~

The `value` query fetches sorted page content; `countQuery` counts the **total matching records**. In the demo there are three active books:

- `PageRequest.of(0, 2)` → page 0: `BK-001`, `BK-002`; `totalElements=3`, `totalPages=2`.
- `PageRequest.of(1, 2)` → page 1: `BK-004`, same `totalElements`.
- `PageRequest.of(0, 2)` for a nonexistent category → empty content, `totalElements=0`.

`PageRequest.of` uses a **0-based page index**, not 1. `Page` may need a count query to determine total records; `Slice` usually checks only whether a next page exists. If native SQL has joins/`GROUP BY`/`DISTINCT`, `countQuery` must **count the true logical result set** (often requiring `COUNT(DISTINCT ...)` or a subquery), not blindly copy `COUNT(*)`.

**Why is a stable ORDER BY essential?** Without sorting, the DB can return rows in any order; different pages may overlap or skip rows if the execution plan changes. When prices tie, secondary sorting by SKU yields deterministic order in the fixture; production likewise needs uniqueness/tie-breakers fitting real data.

### 6.4. Native Dynamic Sorting Is Not Free

Spring Data JPA supports native query pagination/sorting to varying degrees across versions and query parsers. For **complex SQL**, the framework cannot always rewrite `ORDER BY`, inject counts, or handle vendor syntax properly. In our example, we **embed a fixed ORDER BY in SQL** and pass `PageRequest.of(page,size)` without a `Sort` to avoid relying on rewriting.

If an API allows user-specified sorting, use a repository/query builder with an allowlist of sort fields or approaches verified for your version. Do not feed an arbitrary `Sort.by(userInput)` into a native query assuming it is valid and safe across every dialect.

### 6.5. Native Projections and Aliases

When native SQL returns a DTO/interface projection, results often depend on **aliases**, type conversion, and naming:

~~~java
public interface PriceView {
    String getSku();
    Long getPriceCents();
}
~~~

Illustrative SQL direction:

~~~sql
SELECT
    sku AS sku,
    price_cents AS priceCents
FROM catalog_products
WHERE category = :category
~~~

This is an **extension snippet**, not a method used in the runnable project. Whether the `priceCents` alias preserves case or gets case-folded by the driver/dialect, and whether Spring Data maps camelCase/snake_case accordingly, must be tested on the real DB/driver. For complex projections or native SQL returning tuples that do not auto-map, consider `@SqlResultSetMapping`/custom repository mapping per the JPA API.

## 7. Runnable Project: Java 17 + Spring Boot 3.3.5 + H2

This example includes an **entity, repository, DTO, Gradle build, boot configuration, and a JUnit class with multiple independent tests**. No HTTP server, Docker, or external database is required. Production-style mappings/table names are set explicitly so learners can see the difference between JPQL and SQL.

### 7.1. Directory Tree

~~~text
jpa-query-test-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/jpaquery/
    │   ├── CatalogApplication.java
    │   ├── CatalogProduct.java
    │   ├── SkuPrice.java
    │   └── CatalogProductRepository.java
    └── test/java/com/example/jpaquery/
        └── CatalogProductRepositoryTest.java
~~~

Gradle Wrapper files should be generated by an appropriate Gradle installation or taken from a repository; **never paste text into `gradle-wrapper.jar`** as it is a binary file.

**`settings.gradle`**

~~~groovy
rootProject.name = 'jpa-query-test-demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**Dependency explanation:**

- `spring-boot-starter-data-jpa` provides Spring Data JPA, Hibernate, Spring JDBC, transaction manager, and JPA mapping APIs.
- H2 is `testRuntimeOnly` because the example avoids bundling the embedded test database driver in production runtime.
- `spring-boot-starter-test` includes JUnit Jupiter, Spring TestContext, assertions, and Spring testing utilities.
- `junit-platform-launcher` allows Gradle to run JUnit Platform under the configured setup.
- `useJUnitPlatform()` explicitly configures the Gradle `test` task.
- The Spring Boot BOM manages compatible versions of JPA/Hibernate/H2/JUnit; avoid forcing an incompatible Hibernate version just to run a tutorial.

### 7.2. Boot Application Configuration

**`src/main/java/com/example/jpaquery/CatalogApplication.java`**

~~~java
package com.example.jpaquery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

The purpose of `CatalogApplication` is to supply the `@SpringBootConfiguration`/auto-configuration root for the test slice. The demo declares no production datasource URL or driver; run the lesson with **Gradle test** as shown in section 8 rather than expecting `bootRun` to have a complete production DB.

### 7.3. Entity and Explicit Column Names

**`src/main/java/com/example/jpaquery/CatalogProduct.java`**

~~~java
package com.example.jpaquery;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "catalog_products")
public class CatalogProduct {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true,
            length = 32)
    private String sku;

    @Column(name = "title", nullable = false, length = 120)
    private String title;

    @Column(name = "category", nullable = false, length = 40)
    private String category;

    @Column(name = "price_cents", nullable = false)
    private long priceCents;

    @Column(name = "active", nullable = false)
    private boolean active;

    protected CatalogProduct() {
        // Required by JPA
    }

    public CatalogProduct(
            String sku, String title, String category,
            long priceCents, boolean active) {
        this.sku = sku;
        this.title = title;
        this.category = category;
        this.priceCents = priceCents;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getTitle() {
        return title;
    }

    public String getCategory() {
        return category;
    }

    public long getPriceCents() {
        return priceCents;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

Details to note:

- `@Table(name = "catalog_products")` sets the **SQL table name** for native queries.
- The Java property `priceCents` maps to column `price_cents`. Derived/JPQL queries use `priceCents`; native queries use `price_cents`.
- `GenerationType.IDENTITY` lets the database assign IDs; tests **never hardcode IDs** because IDENTITY values can vary across test runs.
- `sku` has a unique constraint so two products cannot share an SKU in the demo.
- `active` is a SQL boolean column; in the demo H2 schema, native `active = TRUE` works.
- Avoids `double` for price cents to eliminate floating-point rounding errors; real products need dedicated currency modeling, precision, rounding, and validation.

The demo entity has no `@OneToMany`, so it does not exercise joins/lazy loading/N+1. Those cases are discussed in section 11.

### 7.4. Record DTO Projection

**`src/main/java/com/example/jpaquery/SkuPrice.java`**

~~~java
package com.example.jpaquery;

public record SkuPrice(String sku, long priceCents) {
}
~~~

The record provides a public constructor matching JPQL `new com.example.jpaquery.SkuPrice(p.sku,p.priceCents)`. Component-based record equality lets JUnit `assertEquals` check the entire `SkuPrice` value instead of object identity.

### 7.5. Repository Containing All Three Query Types

**`src/main/java/com/example/jpaquery/CatalogProductRepository.java`**

~~~java
package com.example.jpaquery;

import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CatalogProductRepository
        extends JpaRepository<CatalogProduct, Long> {

    // 1. Derived query: exact SKU.
    Optional<CatalogProduct> findBySku(String sku);

    // 2. Derived query: case-insensitive category,
    // active-only and deterministic ordering.
    List<CatalogProduct>
    findByCategoryIgnoreCaseAndActiveTrueOrderByPriceCentsAscSkuAsc(
            String category);

    // 3. Derived query: substring search in title.
    List<CatalogProduct>
    findByTitleContainingIgnoreCaseOrderBySkuAsc(String fragment);

    // 4. Derived query: count and existence.
    long countByCategoryAndActiveTrue(String category);

    boolean existsBySku(String sku);

    // 5. JPQL: entity name and Java property names.
    @Query("""
        select p from CatalogProduct p
        where p.category = :category
          and p.active = true
          and p.priceCents >= :minimum
        order by p.priceCents asc, p.sku asc
        """)
    List<CatalogProduct> findActiveCostingAtLeast(
            @Param("category") String category,
            @Param("minimum") long minimum);

    // 6. JPQL constructor projection (DTO record).
    @Query("""
        select new com.example.jpaquery.SkuPrice(
            p.sku, p.priceCents)
        from CatalogProduct p
        where p.category = :category
          and p.active = true
        order by p.sku asc
        """)
    List<SkuPrice> findActivePrices(
            @Param("category") String category);

    // 7. JPQL aggregate. SUM may return null.
    @Query("""
        select sum(p.priceCents)
        from CatalogProduct p
        where p.category = :category
          and p.active = true
        """)
    Long totalPriceOfActiveProducts(
            @Param("category") String category);

    // 8. Native SQL: physical table/column names.
    @Query(value = """
        SELECT * FROM catalog_products
        WHERE category = :category
          AND active = TRUE
        ORDER BY price_cents DESC, sku ASC
        """, nativeQuery = true)
    List<CatalogProduct> findActiveNative(
            @Param("category") String category);

    // 9. Native SQL: scalar COUNT.
    @Query(value = """
        SELECT COUNT(*) FROM catalog_products
        WHERE category = :category AND active = TRUE
        """, nativeQuery = true)
    long countActiveNative(
            @Param("category") String category);

    // 10. Native Page: stable ORDER BY and exact countQuery.
    @Query(
        value = """
            SELECT * FROM catalog_products
            WHERE category = :category
              AND active = TRUE
            ORDER BY price_cents ASC, sku ASC
            """,
        countQuery = """
            SELECT COUNT(*) FROM catalog_products
            WHERE category = :category
              AND active = TRUE
            """,
        nativeQuery = true)
    Page<CatalogProduct> findNativePage(
            @Param("category") String category,
            Pageable pageable);
}
~~~

**Runnability of the query code:**

- Uses Java text blocks `"""`, supported since Java 15; compiles on Java 17.
- `Optional`, `List`, `Page`, `Pageable` are standard return types.
- JPQL `CatalogProduct` matches the entity name; native `catalog_products` matches `@Table`.
- `priceCents` in JPQL/derived matches the entity property; `price_cents` in native matches `@Column`.
- Named parameters use explicit `@Param` names to avoid depending on Java parameter name metadata.
- The native query has a fixed `ORDER BY` and `countQuery`, so tests do not require dynamic `Sort` rewriting.
- `count`/`exists` methods are derived queries rather than writing `@Query` just to invoke `COUNT(*)`.

### 7.6. `@DataJpaTest`: Fixtures, Flush/Clear, and Assertions

**`src/test/java/com/example/jpaquery/CatalogProductRepositoryTest.java`**

~~~java
package com.example.jpaquery;

import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.jdbc.EmbeddedDatabaseConnection;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(
        properties = "spring.jpa.hibernate.ddl-auto=create-drop",
        showSql = false)
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY,
        connection = EmbeddedDatabaseConnection.H2)
class CatalogProductRepositoryTest {

    @Autowired
    private CatalogProductRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @BeforeEach
    void prepareFixture() {
        entityManager.persist(new CatalogProduct(
                "BK-001", "Java Essentials", "books",
                2500L, true));
        entityManager.persist(new CatalogProduct(
                "BK-002", "Spring Boot", "books",
                3900L, true));
        entityManager.persist(new CatalogProduct(
                "BK-003", "Legacy Java", "books",
                1800L, false));
        entityManager.persist(new CatalogProduct(
                "BK-004", "Java Practice", "books",
                3900L, true));
        entityManager.persist(new CatalogProduct(
                "GE-001", "USB Cable", "gear",
                1500L, true));
        entityManager.persist(new CatalogProduct(
                "GE-002", "Laptop Stand", "gear",
                5200L, true));

        // Force SQL INSERT execution and clear the first-level entity cache.
        entityManager.flush();
        entityManager.clear();
    }

    private static List<String> skus(List<CatalogProduct> products) {
        return products.stream()
                .map(CatalogProduct::getSku)
                .toList();
    }

    @Test
    void derivedFindBySkuReturnsExactProduct() {
        CatalogProduct product =
                repository.findBySku("BK-001").orElseThrow();

        assertEquals("BK-001", product.getSku());
        assertEquals("Java Essentials", product.getTitle());
        assertEquals(2500L, product.getPriceCents());
        assertTrue(product.isActive());
    }

    @Test
    void derivedFindBySkuReturnsEmptyWhenMissing() {
        assertTrue(
                repository.findBySku("NO-SUCH-SKU").isEmpty());
    }

    @Test
    void derivedCategoryIgnoresCaseAndExcludesInactive() {
        var result = repository
                .findByCategoryIgnoreCaseAndActiveTrueOrderByPriceCentsAscSkuAsc(
                        "BOOKS");

        assertEquals(
                List.of("BK-001", "BK-002", "BK-004"),
                skus(result));
    }

    @Test
    void derivedContainingIgnoreCaseFindsSubstring() {
        var result = repository
                .findByTitleContainingIgnoreCaseOrderBySkuAsc("JAVA");

        // Includes inactive BK-003 because the method does not filter by active.
        assertEquals(
                List.of("BK-001", "BK-003", "BK-004"),
                skus(result));
    }

    @Test
    void derivedSearchWithoutMatchesReturnsEmptyList() {
        var result = repository
                .findByTitleContainingIgnoreCaseOrderBySkuAsc(
                        "never-appears");

        assertTrue(result.isEmpty());
    }

    @Test
    void derivedCountAndExistsUseIndependentFixtureFacts() {
        assertEquals(3L,
                repository.countByCategoryAndActiveTrue("books"));
        assertEquals(2L,
                repository.countByCategoryAndActiveTrue("gear"));

        assertTrue(repository.existsBySku("BK-001"));
        assertFalse(repository.existsBySku("NO-SUCH-SKU"));
    }

    @Test
    void jpqlFiltersInclusiveMinimumAndSorts() {
        var result = repository.findActiveCostingAtLeast(
                "books", 2500L);

        assertEquals(
                List.of("BK-001", "BK-002", "BK-004"),
                skus(result));
    }

    @Test
    void jpqlIncludesProductsExactlyOnBoundary() {
        var result = repository.findActiveCostingAtLeast(
                "books", 3900L);

        assertEquals(
                List.of("BK-002", "BK-004"),
                skus(result));
    }

    @Test
    void jpqlConstructorProjectionReturnsExactDtoValues() {
        var result = repository.findActivePrices("books");

        assertEquals(
                List.of(
                        new SkuPrice("BK-001", 2500L),
                        new SkuPrice("BK-002", 3900L),
                        new SkuPrice("BK-004", 3900L)),
                result);
    }

    @Test
    void jpqlSumCalculatesActivePrices() {
        Long booksTotal =
                repository.totalPriceOfActiveProducts("books");
        Long gearTotal =
                repository.totalPriceOfActiveProducts("gear");

        assertEquals(10300L, booksTotal);
        assertEquals(6700L, gearTotal);
    }

    @Test
    void jpqlSumWithNoMatchesReturnsNull() {
        assertNull(
                repository.totalPriceOfActiveProducts(
                        "no-such-category"));
    }

    @Test
    void nativeSqlMapsColumnsAndOrdersDescending() {
        var result = repository.findActiveNative("books");

        assertEquals(
                List.of("BK-002", "BK-004", "BK-001"),
                skus(result));
    }

    @Test
    void nativeCountMatchesExactActiveFilter() {
        assertEquals(3L,
                repository.countActiveNative("books"));
        assertEquals(2L,
                repository.countActiveNative("gear"));
        assertEquals(0L,
                repository.countActiveNative("missing"));
    }

    @Test
    void nativePageHasStableContentAndCorrectTotals() {
        Page<CatalogProduct> page0 =
                repository.findNativePage(
                        "books", PageRequest.of(0, 2));

        assertEquals(
                List.of("BK-001", "BK-002"),
                skus(page0.getContent()));
        assertEquals(3L, page0.getTotalElements());
        assertEquals(2, page0.getTotalPages());
        assertTrue(page0.hasNext());

        Page<CatalogProduct> page1 =
                repository.findNativePage(
                        "books", PageRequest.of(1, 2));

        assertEquals(
                List.of("BK-004"),
                skus(page1.getContent()));
        assertEquals(3L, page1.getTotalElements());
        assertFalse(page1.hasNext());
    }

    @Test
    void nativePageForMissingCategoryIsEmpty() {
        Page<CatalogProduct> page =
                repository.findNativePage(
                        "missing", PageRequest.of(0, 2));

        assertTrue(page.getContent().isEmpty());
        assertEquals(0L, page.getTotalElements());
        assertEquals(0, page.getTotalPages());
    }

    @Test
    void jpqlAndNativeReturnSameSetWhenPredicatesAgree() {
        Set<String> jpqlSkus = Set.copyOf(skus(
                repository.findActiveCostingAtLeast(
                        "books", 0L)));

        Set<String> nativeSkus = Set.copyOf(skus(
                repository.findActiveNative("books")));

        // Cross-query comparison, plus an independent expected set.
        assertEquals(
                Set.of("BK-001", "BK-002", "BK-004"),
                jpqlSkus);
        assertEquals(jpqlSkus, nativeSkus);
    }

    @Test
    void queryParameterIsDataNotSqlSyntax() {
        String suspicious = "' OR 1=1 --";

        var result = repository
                .findByTitleContainingIgnoreCaseOrderBySkuAsc(
                        suspicious);

        assertTrue(result.isEmpty());
    }

    @Test
    void allQueryResultsArePersistedEntities() {
        CatalogProduct result =
                repository.findBySku("GE-001").orElseThrow();

        assertNotNull(result.getId());
        assertEquals("gear", result.getCategory());
        assertEquals(1500L, result.getPriceCents());
    }
}
~~~

### 7.7. What Contract Does Each Test Protect?

The class has **18 `@Test` methods**, with no `@ParameterizedTest` or repeated invocations. Each method runs in its own test transaction with the six-product fixture and rolls back at the end of the test.

| Group | Test | Bugs It Can Catch |
| --- | --- | --- |
| Derived exact lookup | `derivedFindBySkuReturnsExactProduct` | Wrong SKU, title, price, active |
| Derived missing | `derivedFindBySkuReturnsEmptyWhenMissing` | Query returns wrong record when missing |
| Derived compound filter | `derivedCategoryIgnoresCaseAndExcludesInactive` | Missing IgnoreCase, missing active, wrong sort/tie-break |
| Derived substring | `derivedContainingIgnoreCaseFindsSubstring` | Wrong LIKE/IgnoreCase, extra inactive filter outside contract |
| Derived empty | `derivedSearchWithoutMatchesReturnsEmptyList` | Broken match predicate |
| Count/exists | `derivedCountAndExistsUseIndependentFixtureFacts` | Miscounting active/category, wrong exists result |
| JPQL inclusive | `jpqlFiltersInclusiveMinimumAndSorts` | Wrong min/active/category/order |
| JPQL boundary | `jpqlIncludesProductsExactlyOnBoundary` | Using `>` instead of `>=` |
| JPQL DTO | `jpqlConstructorProjectionReturnsExactDtoValues` | Wrong property/constructor/values |
| JPQL sum | `jpqlSumCalculatesActivePrices` | Forgot inactive or category |
| JPQL no rows | `jpqlSumWithNoMatchesReturnsNull` | Confusing empty `SUM` with 0 |
| Native mapping/order | `nativeSqlMapsColumnsAndOrdersDescending` | Wrong column names/sort |
| Native count | `nativeCountMatchesExactActiveFilter` | Wrong count predicate |
| Native Page | `nativePageHasStableContentAndCorrectTotals` | Wrong countQuery, offset/page, sort |
| Native empty Page | `nativePageForMissingCategoryIsEmpty` | Wrong count/content when no match |
| Cross-query | `jpqlAndNativeReturnSameSetWhenPredicatesAgree` | JPQL/native filter drift (also checks independent expected) |
| Parameter binding | `queryParameterIsDataNotSqlSyntax` | Input unexpectedly alters predicate |
| Persistence | `allQueryResultsArePersistedEntities` | Entity/ID/mapping not stored properly |

**Note:** In Spring Data, `Page` can skip executing the count SQL in certain situations where the framework infers the total from page contents. Therefore, `Page` tests protect **total/count behavior**, without claiming `countQuery` is guaranteed to be sent to the database on every request. When you need to verify **exact SQL count execution** or performance, observe SQL/metrics against the database with sufficiently large pagination scenarios.

## 8. Running the Project and Inspecting Results

In the root directory with Gradle Wrapper, JDK 17, and Maven dependency access:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run the JUnit class individually:

~~~bash
./gradlew test --tests 'com.example.jpaquery.CatalogProductRepositoryTest'
~~~

Expect **18 tests to pass** with the described project/environment. This is a **result deduced from the source code**, not proof of execution on the learner's machine. The tests do not print `System.out.println`, so there is no fixed business stdout; Gradle normally reports `BUILD SUCCESSFUL` when build/test succeed.

Reports are typically located at:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    └── TEST-com.example.jpaquery.CatalogProductRepositoryTest.xml
~~~

In multi-module builds, `build` belongs to the module containing the tests. If `test` reports `UP-TO-DATE` or `FROM-CACHE`, the result may be cached; for diagnostics you can run:

~~~bash
./gradlew test --rerun-tasks
~~~

If a new project lacks the Wrapper, a compatible pre-installed Gradle can bootstrap it, for example:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Then commit `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.properties`, and `gradle-wrapper.jar` per repository policy. Real projects should prefer their existing Wrapper rather than upgrading versions just for a lesson.

### SQL Logs and Executed Queries

In `@DataJpaTest`, the demo's `showSql = false` attribute disables SQL stdout so focus stays on test results. When debugging, enable Hibernate SQL and bind-parameter logging via a **separate test configuration**. Exact logger categories differ between Hibernate 5 and 6; with Boot 3.3/Hibernate 6, typically use:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

This config snippet is for **test/debug environments**, not to be placed in production logs: bind parameters can expose sensitive data. In the example, logs show JPQL/derived queries translated to SQL by Hibernate and native SQL referencing tables/columns directly.

## 9. `flush` and `clear`: Why Can Tests Produce False Greens?

JPA uses a **first-level cache / persistence context**. When `entityManager.persist(product)` is called, the entity may sit in the persistence context while the SQL INSERT has not flushed yet depending on timing/ID strategy. Hibernate can also return the managed entity from cache on `findById` without a database round trip.

If a test only writes:

~~~java
CatalogProduct saved = repository.save(product);
CatalogProduct loaded =
        repository.findById(saved.getId()).orElseThrow();
assertEquals(saved.getSku(), loaded.getSku());
~~~

sometimes the check only proves the persistence context holds the **same Java entity**, failing to thoroughly check schema, SQL, or database mappings.

In our demo:

~~~java
entityManager.flush();
entityManager.clear();
~~~

after fixture setup ensures:

1. `flush` forces JPA to synchronize pending INSERTs to the database **within the current test transaction**.
2. `clear` detaches managed entities from the persistence context.
3. Subsequent queries force the ORM to read/map from the database for entities that are no longer managed.
4. Tests still roll back at the end of the method; **flush is not commit**.

With `GenerationType.IDENTITY`, an INSERT may already have run early to obtain the ID; keep `flush/clear` as an explicit test rule applicable across mappings.

### When Does `flush` Expose Bugs?

- A unique/foreign-key constraint is actually violated.
- `nullable=false`/database NOT NULL disagrees with expectations.
- Column length is too short or type conversion is wrong.
- SQL INSERT/UPDATE does not match the schema.
- A query requires data to be written to the DB before matching.

Do not merely write `repository.save(...)` and check a property on that object; repository tests protecting **persistence behavior** should include at least one case that queries back from the database.

### Why Rely on `@DataJpaTest` Rollback Instead of `deleteAll()`?

Each test's fixture is created in a test-managed transaction and rolled back; clearing whole tables is unnecessary. Calling `deleteAll()` in `@AfterEach` can mask bugs or slow tests down; if the datasource accidentally points to production, it is dangerous. **Do not treat rollback as sufficient protection** against wrong credentials/URLs: ensure test databases are isolated by permissions and network.

## 10. Adding PostgreSQL Testing with Testcontainers

The H2 example verifies JPA query contracts on H2. If production runs PostgreSQL, add an integration test layer against **real PostgreSQL in Testcontainers**, especially when you have:

- Native SQL using `jsonb`, `ILIKE`, `ON CONFLICT`, `RETURNING`, CTEs, or window functions.
- Custom PostgreSQL enums, arrays, UUID, or timestamp/time zone behavior.
- PostgreSQL-specific casts, collations, indexes, or query plans.
- Flyway/Liquibase migrations running per dialect.
- Queries with engine-dependent transaction/locking behavior.
- Pagination and counts on complex native queries with joins/distinct/group by.

### 10.1. Testcontainers Template on Spring Boot 3.3

In a project already using JPA + Spring Boot Test, add compatible test dependencies:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}
~~~

This is an **addition**, not a standalone `build.gradle` file. Testcontainers requires Docker or a compatible container runtime and the PostgreSQL image available or pullable.

Test class structure snippet:

~~~java
@DataJpaTest
@Testcontainers
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class PostgresProductRepositoryTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    CatalogProductRepository repository;

    // @BeforeEach creates fixtures, @Test asserts native SQL behavior...
}
~~~

This is an **extension snippet**, lacking complete imports/methods to compile standalone; it requires Testcontainers libraries, schemas/fixtures, and matching JPA config.

**Critical for Spring Boot 3.3:** `@DataJpaTest` normally defaults to the `ANY` database replacement policy, so a DataSource configured by Testcontainers can be **replaced with H2** unless `@AutoConfigureTestDatabase(replace = NONE)` is set. In Boot 3.4+, `Replace.NON_TEST` was added as the default and attempts to recognize test DB/connection details; however, **`NON_TEST` does not exist in 3.3**. Use `NONE` explicitly when preserving container datasources across versions.

### 10.2. Do Not Only Check That “the Container Started”

Having a `PostgreSQLContainer` in the JVM **does not prove the repository is using PostgreSQL**. Add a diagnostic test:

~~~java
@Autowired
DataSource dataSource;

@Test
void repositoryReallyUsesPostgres() throws Exception {
    try (Connection connection = dataSource.getConnection()) {
        assertEquals(
                "PostgreSQL",
                connection.getMetaData().getDatabaseProductName());
    }
}
~~~

This snippet requires JUnit, `javax.sql.DataSource`, and `java.sql.Connection` imports. Checking the DB product name and a PostgreSQL-specific SQL feature prevents false conclusions if embedded replacement happens silently. Never print usernames/passwords or full connection URLs containing secrets in CI logs.

### 10.3. Verifying the Real Production Schema

In the H2 demo project, `spring.jpa.hibernate.ddl-auto=create-drop` builds the schema from entity mappings. In production systems using Flyway/Liquibase, repository tests need a layer verifying **actual migrations** on the right DB engine. If all tests rely on Hibernate-generated schemas, bugs in migration SQL can go unnoticed.

With PostgreSQL Testcontainers, typically:

1. Start an isolated test container.
2. Run versioned migrations.
3. Seed fixtures via repositories/SQL.
4. Execute derived/JPQL/native queries.
5. Assert database product, data, counts, and constraints.
6. Clean up via rollback, test schema, or appropriate container lifecycle.

Never run destructive migrations or `TRUNCATE` on a production DB; test infrastructure should use isolated credentials and namespaces.

## 11. Joins, Nulls, Distinct, and Pagination: Expanding the Test Suite

The runnable project focuses on a single entity for easy execution, whereas production repositories often involve relationships. Add the following checks to your checklist when writing real queries.

### 11.1. Joins Produce Duplicate Rows

Suppose an order has three items. A join query `Order o join o.items i` can produce three SQL rows. If you want a **deduplicated list of orders**, JPQL can use:

~~~java
@Query("""
    select distinct o from CustomerOrder o
    join o.items i
    where i.active = true
    """)
List<CustomerOrder> findOrdersWithActiveItems();
~~~

This is an illustrative snippet requiring separate entity mappings. Tests must create at least one order with **two active items**, then assert the order appears only once per contract. If fixtures have only one item per order, a query missing `distinct` can still pass.

With paginated joins, `countQuery` must count distinct parents rather than blindly using `COUNT(*)` over the join. A wrong `Page` total causes the UI to display incorrect page counts even when page 0 content looks right.

### 11.2. `null` and Optional Filtering

In SQL, `= NULL` is not `IS NULL`. JPQL/derived queries handle null parameters and nullability differently depending on syntax and version. Do not assume “passing null skips the filter” unless the repository contract defines it that way.

If you want:

- `category=null` → return all categories;
- or `category=null` → only records with null category;
- or `category=null` → throw a validation error;

**pick one** and test it explicitly. For complex optional filters, use Specification/Criteria API or JPQL:

~~~java
@Query("""
    select p from CatalogProduct p
    where (:category is null or p.category = :category)
    """)
List<CatalogProduct> findWithOptionalCategory(
        @Param("category") String category);
~~~

This is an extension snippet not in the runnable repository. In systems with large datasets, optional `OR` conditions can impact index usage and query plans; correctness tests do not replace profiling on a real DB.

### 11.3. Time Boundaries

When filtering by `Instant createdAt` or dates, a half-open interval is usually preferred:

~~~text
[startInclusive, endExclusive)
~~~

and test three points: just before start, equal to start, and equal to end (must be excluded). Avoid `23:59:59.999` depending on database precision because microseconds/nanoseconds can be missed. With PostgreSQL/MySQL, time zones and `timestamp with/without time zone` types must also be tested on the target engine.

### 11.4. Case Sensitivity and Collation

`IgnoreCase` typically generates SQL using `UPPER`/`LOWER` or an equivalent mechanism, yet **Unicode comparison, Vietnamese diacritics, and collation results** are not identical across H2, PostgreSQL, and MySQL. If the product requires accent-insensitive/case-insensitive Vietnamese name search, define an explicit search contract and strategy; `IgnoreCase` does not automatically mean “ignore Vietnamese accents”.

Create fixtures with uppercase/lowercase/accented variations and run them on the corresponding production database engine when that behavior matters.

### 11.5. Ordering When Values Tie

The project has two books with `priceCents=3900`. Secondary sorting by `sku` enforces deterministic order. If SKU can also tie (impossible in the demo due to unique constraint), use ID or another stable key as tie-breaker. Pagination with only `ORDER BY price` can drop or duplicate records across pages when execution plans or data change.

Even with stable `ORDER BY`, offset-based pagination under **concurrent writes** can shift records; for large or fast-changing feeds, consider keyset/cursor pagination and test on a real database.

## 12. Update/Delete Queries and the Persistence Context

Although the focus is SELECT, many repositories also have `@Modifying @Query`:

~~~java
@Modifying
@Query("""
    update CatalogProduct p
    set p.active = false
    where p.category = :category
    """)
int deactivateCategory(@Param("category") String category);
~~~

This is an illustrative snippet not added to the demo. Bulk update/delete **bypasses entity lifecycle callbacks and does not automatically synchronize managed entities in the persistence context** the way updating individual entities does. After a bulk query, entities already held in the test may retain **stale values**.

A proper test should:

1. Persist fixtures and `flush`.
2. Execute the bulk update/delete inside an appropriate transaction.
3. `clear` the persistence context (or use `@Modifying(clearAutomatically=true, flushAutomatically=true)` when understanding its side effects).
4. Re-query from the DB.
5. Assert both the affected row count and updated data.

Do not write:

~~~java
CatalogProduct product = repository.findBySku("BK-001").orElseThrow();
// Run bulk update...
assertFalse(product.isActive());
~~~

expecting the Java object `product` to change state automatically. It may remain the stale managed entity. Reload at the right context/time. Moreover, `@DataJpaTest` rolling back DML at the end of a method does not mean server-side transactions/messaging/caches outside the test roll back.

## 13. Testing Query Performance: Correctness Is Not Enough

Derived, JPQL, and native SQL queries can return the same records at very different costs:

- Is an index being used?
- Does the query scan the whole table or seek by key?
- Does `LIKE %fragment%` defeat a standard B-tree index?
- Does a join fetch produce a Cartesian product or N+1?
- Is the page `countQuery` slower than the main query?
- Does loading full entities pull too many columns when only a DTO is needed?
- Does sorting force an in-memory sort due to a missing composite index?
- Does native SQL use functions/CTEs incompatible across engines?

**Unit/slice tests** primarily prove correctness. To protect performance, use **query plans (`EXPLAIN`/`EXPLAIN ANALYZE`), integration benchmarks, Hibernate SQL statistics, and representative dataset sizes** on the right DB engine. Avoid asserting strict millisecond timings on H2 with six rows; results are noisy and unrepresentative of production.

### From Assertions to Useful Metrics

| Goal | Approach |
| --- | --- |
| Exact record set | Assert list/page content and counts |
| Prevent N+1 | Observe Hibernate SQL statement counts or profiling |
| Verify index usage | `EXPLAIN` on the real engine with real schema/migrations |
| Pagination accuracy with joins | Test `countQuery` with parents having multiple children |
| Stability under large data | Performance integration benchmarks with substantial datasets |
| Portable native SQL | Test on every supported DB engine |
| No tenant data leakage | Seed multi-tenant fixtures and assert only valid tenant rows return |
| No query injection | Bind parameters, allowlist dynamic identifiers, test adversarial inputs |

## 14. Common Errors and Diagnostics

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `PropertyReferenceException` | Derived method uses wrong Java property name | Cross-check entity getters/fields and Spring Data keywords |
| JPQL reports unknown entity | Used table name instead of entity name | Use `CatalogProduct` or declared entity name |
| JPQL reports unresolved property | Used `price_cents` instead of `priceCents` | Use Java property names in JPQL |
| Native SQL reports table not found | Table/schema/dialect mismatch | Check `@Table`, schema migrations, and active DB |
| Native SQL reports column not found | Used Java property instead of SQL column | Check `@Column` and physical DDL |
| Projection reports constructor mismatch | DTO class name/types/order mismatch | Verify `new fqcn(...)` and public constructor |
| `SUM` with no matches returns null | SQL aggregate semantics | Use boxed type or `coalesce` when contract expects 0 |
| List has right count but wrong records | Only asserted `size()` | Assert SKU/fields of each record |
| Sort test fails intermittently | Missing `ORDER BY`/tie-breaker | Sort by a stable key and test duplicate sort values |
| `Page.totalElements` is wrong | `countQuery` predicate differs from main query | Match distinct/group/filter logic accurately |
| Page 2 has duplicates or gaps | Unstable `ORDER BY` or mutating data | Use stable ordering/cursor strategy and proper fixtures |
| Query passes H2, fails PostgreSQL | Dialect/native SQL/collation/type mismatch | Use Testcontainers on the target DB engine |
| Test sees uncommitted data | Persistence context/test transaction | Flush/clear; test commit boundaries intentionally |
| Query test only checks saved Java object | First-level cache returned managed entity | Clear context and reload |
| Constraint doesn't fail as expected | Missing flush or different DB schema | `flush()` and assert the right root cause |
| Test suite depends on execution order | Fixtures/shared DB not reset | `@DataJpaTest` rollback, per-test namespace, cleanup |
| Native count scalar type mismatch | Driver/JPA returns different numeric type | Use compatible return type and verify on target engine |
| `IgnoreCase` fails Vietnamese expectations | Collation/Unicode semantics differ | Define search contract and test on real engine |
| Spring bean fails to initialize | `@Query` syntax or derived parsing error | Read root cause under `Failed to load ApplicationContext` |
| Potential SQL injection | Concatenating raw input into native SQL | Bind parameters and allowlist identifiers |
| `@DataJpaTest` silently uses H2 instead of container | Test datasource replacement policy | On Boot 3.3, set `Replace.NONE` for containers |
| “Tests pass” despite broken SQL migrations | Tests use Hibernate `create-drop` instead of migrations | Add migration integration tests |
| N+1 or slow query | Improper joins/lazy loading/indexes | Profile and check query plans on a real DB |

### Diagnostic Workflow for a Failing Repository Test

1. **Identify query type:** derived, JPQL, or native? Do not change SQL column names if the method parses Java properties.
2. **Verify the database:** H2 test slice or PostgreSQL/MySQL Testcontainers? Was embedded replacement triggered?
3. **Check schema:** are entity mappings, `@Column/@Table`, migrations, and data types right?
4. **Check fixtures:** are active/inactive records, multiple categories, price boundaries, and tie-ordering covered?
5. **Check transactions:** were fixtures flushed? Is the test reading from the persistence context or DB?
6. **Check query predicates:** AND/OR, >= vs >, nulls, case/LIKE, joins/distinct.
7. **Check result mapping:** do entities/DTOs/projections/scalars have matching types and aliases?
8. **Check pagination:** 0-based page index, `ORDER BY`, `countQuery`, and total records.
9. **Inspect root causes and SQL debug logs** carefully without logging secrets.
10. **Fix the query or fixture per spec**, never relax assertions just to get green.

## 15. Layered Testing Strategy in Real Projects

A repository can be protected by several layers of tests:

### Layer 1 — Derived/JPQL Correctness on an Embedded DB

Fast, well suited for:

- Method name parsing.
- Verifying DTO projections/basic aggregates.
- Filtering/ordering/boundaries with small fixtures.
- Dialect-independent repository contract behavior.

Use `@DataJpaTest` as in the sample project. Question any assertion that checks only existence/size without verifying the actual data set.

### Layer 2 — Native Queries on the Production DB Engine

Use Testcontainers or an equivalent test database for:

- Native SQL, functions/CTEs/casts/JSON types.
- Schema migrations, constraints, collations, and locking.
- Query plan/index behavior when performance matters.
- `countQuery`/pagination for complex SQL.

Configure the test datasource explicitly. Never pass production DB credentials to CI. When using multiple DataSources, verify the repository binds to the right datasource and transaction manager.

### Layer 3 — Service/API Contracts

If the repository is called by a service for business logic, write unit tests for pure logic and integration tests for wiring. When query results are exposed over HTTP/GraphQL, add WebMvcTest/HTTP integration tests to check authorization, serialization, status codes, API pagination, and error mapping. Do not replace all query tests with HTTP tests: when an API fails, tests should pinpoint whether the bug is in the repository or web layer.

### Layer 4 — Security and Data Isolation

In multi-tenant applications, `tenant_id` predicates must never be omitted even if a query looks up a single SKU. Fixtures should include **the same SKU across different tenants** if the schema permits, and tests must assert **no cross-tenant leakage**. Use security-aware repository/service filters and appropriate database policies; a single-tenant test never catches a missing tenant predicate.

## 16. Practice Exercises

**Exercise A — Flip boundary operator:** Change JPQL `p.priceCents >= :minimum` to `> :minimum`. Run `jpqlIncludesProductsExactlyOnBoundary`. The test must fail because the two books priced at exactly 3900 are excluded. Revert it.

**Exercise B — Remove active condition:** Temporarily remove `p.active = true` in `findActiveCostingAtLeast`. At minimum 0, the query will include `BK-003`. Confirm cross-query/expected tests turn red; explain why a test using only `min=3900` might miss this bug.

**Exercise C — Secondary sort:** Remove `sku ASC` in the corresponding JPQL/native/derived method. For the two 3900-priced books, order can depend on the query plan; explain why this is a stability bug even if tests occasionally pass.

**Exercise D — Native countQuery:** Change `countQuery` to `COUNT(*)` without the active filter and paginate `books`. Expect 3 active, yet count may report 4. Observe how count execution is optimized on different pages before assuming which test reliably catches the bug.

**Exercise E — H2 vs PostgreSQL:** Add a native query using PostgreSQL `ILIKE`/`jsonb`; observe H2 failing to support it. Try PostgreSQL Testcontainers and verify native SQL on the real engine. Never rewrite a production query solely because H2 does not understand a vendor dialect.

**Exercise F — Projection:** Swap argument order in `new SkuPrice(...)` or alter constructor types; observe validation/mapping failures. Write tests checking both SKU and price, not just record count.

**Exercise G — No matching records:** Try `totalPriceOfActiveProducts("missing")`. Explain why `SUM` can be null while `COUNT` is 0. If business logic requires total=0, update the query with `coalesce` and adjust assertions per contract.

**Exercise H — Persistence context changes:** Remove `entityManager.clear()` in the fixture setup. Compare entity lookup test results and SQL logs; explain when reads hit the first-level cache. Then alter a mapping and use `flush/clear` to catch the bug.

**Exercise I — Multiple categories/tenants:** Add `tenantId` to the entity and queries. Insert records for two tenants with the same category and verify isolation. A query missing the tenant predicate must fail against this fixture.

**Exercise J — Unstable pagination:** Add more products with identical prices; test `PageRequest.of(0,2)` and `PageRequest.of(1,2)`. Establish a stable sort on `priceCents, sku`, verifying no missing or duplicated SKUs.

**Exercise K — Preventing SQL injection:** Create a native repository query using bind parameter `:sku` and test input containing quotes/SQL operators. Assert it is treated purely as data without altering SQL structure. Never run DELETE/DROP tests on an unisolated database.

**Exercise L — Broken schema migration:** Use PostgreSQL Testcontainers with Flyway/Liquibase schemas. Rename a column in a test-branch migration without updating a native query; the query must fail with a missing-column error. Revert it.

## 17. Checklist Before Merging Repository Queries

- [ ] Do I know whether the query is **derived**, **JPQL**, or **native SQL**?
- [ ] Are derived method names based on **Java properties**, not SQL columns?
- [ ] Does JPQL use the right entity name, fields/properties, and `@Param`?
- [ ] Does native SQL use the right table/column names, schema, and DB dialect?
- [ ] Does the fixture cover active/inactive records, multiple categories, boundaries, empty cases, and tie-ordering?
- [ ] Do assertions verify **exact SKUs/prices/record sets**, not just counts or non-null?
- [ ] Do queries include `ORDER BY`/tie-breakers whenever the contract requires deterministic ordering?
- [ ] Are projection constructors/aliases/types accurate and tested?
- [ ] Does aggregate `SUM` handle null and `COUNT` handle zero per requirements?
- [ ] Does `Pageable` use a zero-based index, and does `countQuery` match the main predicate?
- [ ] Did the fixture `flush/clear` when testing a database round trip instead of the persistence context cache?
- [ ] Does `@DataJpaTest` point to a proper test datasource, roll back, and avoid touching production?
- [ ] Is native/dialect-specific SQL tested on the production engine via container/test DB?
- [ ] Are dynamic values bound as parameters and dynamic identifiers allowlisted?
- [ ] Are test data, transactions, and migrations isolated without deleting from a shared DB?
- [ ] Do join queries have tests for duplicates/distinct and N+1 when business/performance requires it?
- [ ] If multi-tenant, do queries prevent leaking other tenants' records?
- [ ] Do SQL logs avoid exposing sensitive data?
- [ ] Did the Gradle report confirm tests actually ran rather than mistaking `UP-TO-DATE` for fresh execution?

## 18. Official References

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@DataJpaTest`, embedded databases, TestEntityManager, and transactional rollback.
- [Spring Data JPA — Defining Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): derived queries, `@Query`, native queries, named parameters, pagination/projections.
- [Spring Data Commons — Query Methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): how derived query property expressions/keywords are parsed.
- [Spring Data JPA — Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html): interface and class/DTO-based projections.
- [Spring Data JPA — Transactions](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html): repository transaction behavior and method-level operations.
- [Spring Boot 3.3 — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): `@ServiceConnection` and database/container test setup.
- [Hibernate ORM — HQL/JPQL](https://docs.jboss.org/hibernate/orm/6.5/querylanguage/html_single/): entity queries, projections, and Hibernate query language semantics.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/3.1/): JPQL, entity mappings, `EntityManager`, persistence context, and transactions.

**Key takeaway:** Derived queries use **Java property names** in the method name; JPQL uses **entities/properties** in `@Query`; native SQL uses **tables/columns/database dialects**. Effective tests create counterexample fixtures, assert full content/order/boundaries, flush/clear when appropriate, and verify native queries on the **target database engine**. A test showing “the repository returned one row” is not proof that the query behaves properly across all branches.