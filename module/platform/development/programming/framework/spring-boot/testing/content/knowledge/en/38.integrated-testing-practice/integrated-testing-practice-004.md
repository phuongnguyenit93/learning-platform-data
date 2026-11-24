# Testing Repositories with a Real Database in Testcontainers — Spring Boot and PostgreSQL

## 1. Why not just mock the repository or use H2?

A repository in Spring Boot is not merely a Java interface: calls traverse a Spring Data proxy, `EntityManager`, Hibernate, and the JDBC driver before being executed by PostgreSQL under SQL constraints and transactions. A Mockito mock can return fake data on cue, yet proves nothing about generated SQL, column mappings, unique constraints, indexes, migrations, or how the engine handles transactions.

In-memory H2 is valuable for certain fast tests, yet it cannot fully replace PostgreSQL: `ILIKE`, `JSONB`, `ON CONFLICT`, PostgreSQL arrays, timestamp types, NULL ordering, collations, identity columns, isolation levels, and SQLSTATE error codes can all differ. When production runs PostgreSQL, at least one integration suite must run against **real PostgreSQL**.

**Goal:** Spin up PostgreSQL 16 via Testcontainers, apply Flyway schema migrations, test a Spring Data JPA repository with JUnit 5 in Spring Boot 3.5 / Java 17+, and verify CRUD, JPQL, native SQL, constraints, pagination, and rollback. No PostgreSQL installation on the host and no fixed port 5432 are required.

After this lesson, you will be able to distinguish logic/service tests, JPA slices, and full application integration; apply `@DataJpaTest`, `@AutoConfigureTestDatabase(replace=NONE)`, `@ServiceConnection`, `TestEntityManager`, and `flush/clear`; assert DB errors at the right moment; and design reproducible Docker-enabled CI workflows.

## 2. Test layers and contract scope

| Test type | Context | Database | What it guarantees |
| --- | --- | --- | --- |
| Mockito unit test | None or MockitoExtension | Mock | Business logic branches interacting with repository |
| `@DataJpaTest` with H2 | JPA slice | H2 | Partial mapping/JPQL, no dialect guarantee |
| `@DataJpaTest` with Testcontainers | JPA slice | Real PostgreSQL | Queries, mapping, constraints, JPA transactions |
| `@SpringBootTest` + Testcontainers | Full Boot | Real PostgreSQL | Service/transaction/wiring together with repository |
| End-to-end on deployed environment | Multiple services | System-dependent | API + network + DB + operations |

If you are asking “Does `findBySku` generate valid SQL, return Optional, and map fields properly?”, **do not mock that repository**. If you are asking “What error does the service throw when the repository cannot find an SKU?”, mocking the repository in a unit test is appropriate. Choose the layer by goal, not merely because one test runs faster.

### What does Testcontainers actually run?

~~~text
JUnit test JVM
  |
  +-- @Testcontainers / @Container
  |     +-- Docker API discovery
  |     +-- pull postgres:16-alpine if needed
  |     +-- create/start PostgreSQL container
  |     +-- wait until PostgreSQL is ready
  |
  +-- @DataJpaTest Spring context
        +-- @ServiceConnection JDBC/Flyway details
        +-- DataSource / JPA / Hibernate / transaction manager
        +-- Flyway V1 migration
        +-- Hibernate ddl-auto=validate
        +-- ProductRepository proxy
                 |
                 +-- SQL -> JDBC -> PostgreSQL mapped port
~~~

`PostgreSQLContainer` starts a real PostgreSQL server. The Docker API endpoint used by the JVM to start the container **differs** from the host/port the JVM uses to send SQL. The mapped host port is usually random, so never hardcode `jdbc:postgresql://localhost:5432/...`.

## 3. Required annotations and their meanings

A Boot 3.5 repository test can start like this:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class ProductRepositoryPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

This is an opening snippet; the complete test class appears later.

- `@DataJpaTest` creates a JPA slice, scans entities and Spring Data repositories, and configures `TestEntityManager`.
- `@AutoConfigureTestDatabase(replace=NONE)` prevents auto-configuration from swapping the datasource to H2/embedded DB if that dependency sits on the classpath.
- `@Testcontainers` activates the JUnit Jupiter extension.
- Static `@Container` manages one `PostgreSQLContainer` for the entire test class; an instance field creates one container per method.
- `@ServiceConnection`, provided by `spring-boot-testcontainers`, supplies JDBC/Flyway connection details from the container.
- `@DataJpaTest` meta-registers `SpringExtension` for Jupiter, so repeating `@ExtendWith(SpringExtension.class)` is unnecessary.
- `@DataJpaTest` uses test-managed transactions by default and rolls back after each test method.

**Lifecycle note:** a static `@Container` belongs to the JUnit extension and stops after the class. If the Spring TestContext cache retains the `ApplicationContext` for another class, the cached `DataSource` may point to a stopped container. The demo project has one repository test class; a later section explains how to tie container lifecycle to the context when scaling up.

## 4. Runnable practice project

Structure:

~~~text
repository-postgres-test/
  settings.gradle
  build.gradle
  src/main/java/example/catalog/
    CatalogApplication.java
    Product.java
    ProductRepository.java
  src/main/resources/
    application.properties
    db/migration/V1__create_products.sql
  src/test/java/example/catalog/
    ProductRepositoryPostgresTest.java
  .github/workflows/
    repository-tests.yml
~~~

Requirements: Java 17+, a Gradle wrapper compatible with Spring Boot 3.5, a Docker-compatible runtime (Docker Engine/Desktop or supported equivalent), and permission to pull images. File names and packages in the example are consistent.

## 5. settings.gradle

~~~groovy
rootProject.name = 'repository-postgres-test'
~~~

## 6. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

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
    runtimeOnly 'org.postgresql:postgresql'

    implementation 'org.flywaydb:flyway-core'
    implementation 'org.flywaydb:flyway-database-postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
    forkEvery = 0

    testLogging {
        events 'passed', 'failed', 'skipped'
        exceptionFormat 'full'
    }
    reports {
        html.required = true
        junitXml.required = true
    }
}
~~~

### Why choose these dependencies?

`spring-boot-starter-data-jpa` brings Hibernate, Spring Data repositories, and transactions; `org.postgresql:postgresql` is the JDBC driver. `flyway-core` + `flyway-database-postgresql` enable Flyway to recognize PostgreSQL: in modern Flyway versions, PostgreSQL support resides in a database-specific module. `spring-boot-starter-test` provides Jupiter, AssertJ, Mockito, and TestContext utilities; `spring-boot-testcontainers` provides `@ServiceConnection`; Testcontainers `junit-jupiter` and `postgresql` handle lifecycle and `PostgreSQLContainer`.

Do not add H2 for this integration test. If a larger project includes H2 for other tests, `replace=NONE` still preserves PostgreSQL.

**Version note:** Spring Boot 3.5.0 / Java 17 is a demo baseline, not a claim that it is the latest release. Rely on Boot's dependency management to avoid Testcontainers/JUnit module mismatches instead of mixing arbitrary major versions.

### Why `maxParallelForks=1`?

This is a baseline with minimal CPU/RAM contention. Multiple Gradle test JVMs maintain separate Spring TestContext caches and can spin up multiple DB containers. After profiling runner resources and CI throughput, forks can be raised in a controlled way. `forkEvery=1` adds JVM/context startup overhead and prevents cache reuse, so it is not set as the default.

## 7. application.properties

`src/main/resources/application.properties`:

~~~properties
# Flyway is the schema source of truth.
spring.flyway.enabled=true

# Hibernate checks columns and types; it must not recreate tables.
spring.jpa.hibernate.ddl-auto=validate

# No web application is required for JPA slice tests.
spring.jpa.open-in-view=false

# Don't mix schema.sql/data.sql initialization with Flyway.
spring.sql.init.mode=never

spring.jpa.show-sql=false
~~~

Do not hardcode `spring.datasource.url/username/password` here. In tests, Spring Boot gets connection details from `PostgreSQLContainer` via `@ServiceConnection`.

**Running the main app outside tests still requires a real datasource** configured via environment/secrets. Do not claim `java -jar` alone will auto-start Testcontainers: `spring-boot-testcontainers` is in test scope, not a production daemon provisioner.

## 8. Flyway V1__create_products.sql

`src/main/resources/db/migration/V1__create_products.sql`:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(64) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price_cents BIGINT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uk_products_sku UNIQUE (sku),
    CONSTRAINT ck_products_price_nonnegative
        CHECK (price_cents >= 0)
);

CREATE INDEX idx_products_enabled_price_id
    ON products (enabled, price_cents, id);
~~~

### DDL notes

- `id BIGINT GENERATED BY DEFAULT AS IDENTITY` matches JPA `GenerationType.IDENTITY`.
- `sku` is non-null, up to 64 characters, and unique.
- `price_cents` is non-negative, enforced by a DB CHECK constraint even if Java validation is bypassed.
- `enabled` has DB default `TRUE`; when Hibernate sends an explicit boolean, that default is not applied.
- `created_at TIMESTAMPTZ` is set by the database using the current timestamp default.
- The index can assist queries filtering `enabled` and sorting by price/id; the PostgreSQL planner decides whether to use the index or a sequential scan.

Migrations run at context startup, before test transactions. Rolling back a test method **does not undo** the V1 schema migration; it rolls back rows seeded or written inside the transaction.

### Use migrations, not `ddl-auto=create-drop`

Setting `spring.jpa.hibernate.ddl-auto=create-drop` lets Hibernate build the schema from entities and can make CRUD tests PASS even when production SQL migrations are broken. `validate` catches certain mapping/column/type mismatches, while querying `flyway_schema_history` confirms Flyway ran.

Once a schema is released, add `V2__...sql` instead of editing V1 and breaking Flyway checksums. Never run Flyway repair casually to ignore production DDL drift.

## 9. CatalogApplication.java

`src/main/java/example/catalog/CatalogApplication.java`:

~~~java
package example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

This root package contains the entity and repository. Spring Boot discovers `@SpringBootConfiguration` and scans properly without extra `@EntityScan` or `@EnableJpaRepositories` for a simple project.

## 10. Product.java — PostgreSQL-compatible entity

`src/main/java/example/catalog/Product.java`:

~~~java
package example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, length = 64)
    private String sku;

    @Column(name = "name", nullable = false, length = 200)
    private String name;

    @Column(name = "price_cents", nullable = false)
    private long priceCents;

    @Column(name = "enabled", nullable = false)
    private boolean enabled;

    protected Product() {
        // Required by JPA.
    }

    public Product(
            String sku, String name,
            long priceCents, boolean enabled) {

        this.sku = sku;
        this.name = name;
        this.priceCents = priceCents;
        this.enabled = enabled;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public long getPriceCents() {
        return priceCents;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void changePrice(long updatedPriceCents) {
        this.priceCents = updatedPriceCents;
    }

    public void rename(String updatedName) {
        this.name = updatedName;
    }

    public void changeEnabled(boolean value) {
        this.enabled = value;
    }
}
~~~

### Why not map `created_at`?

`created_at` is a DB-only column demonstrating PostgreSQL defaults. Hibernate `validate` accepts a table having extra columns beyond entity mappings; tests use `JdbcTemplate` to verify the DB default was populated. If production needs to return `createdAt`, map `Instant` and refresh/reload the entity after insert, while verifying timestamp/timezone/dialect semantics.

### Why doesn't the constructor block negative prices?

The test needs to reach the **DB CHECK constraint** to prove Postgres rejects negative data. In a real application, validate input in Java/service/DTOs as well, though Java validation never replaces DB constraints. If the constructor threw early, the test would never prove CHECK works.

### Mapping vs migration

`@Column(name="price_cents")` matches the DDL, and `@GeneratedValue(IDENTITY)` matches PostgreSQL identity. DDL UNIQUE/CHECK constraints are defined in Flyway, without enabling Hibernate schema generation to create constraints. Hibernate `validate` is not guaranteed to verify every index/constraint, so database-specific tests are essential.

## 11. ProductRepository.java

`src/main/java/example/catalog/ProductRepository.java`:

~~~java
package example.catalog;

import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Optional<Product> findBySku(String sku);

    boolean existsBySku(String sku);

    List<Product>
        findByEnabledTrueOrderByPriceCentsAscIdAsc();

    Page<Product> findByEnabledTrue(Pageable pageable);

    @Query("""
           select p from Product p
           where p.priceCents >= :min
             and p.priceCents <= :max
           order by p.priceCents asc, p.id asc
           """)
    List<Product> findByPriceRange(
            @Param("min") long min,
            @Param("max") long max);

    @Query(
        value = """
                SELECT *
                FROM products
                WHERE sku ILIKE CONCAT('%', :fragment, '%')
                ORDER BY id
                """,
        nativeQuery = true)
    List<Product> findBySkuFragmentIgnoreCase(
            @Param("fragment") String fragment);
}
~~~

Distinctions:

- **Derived query** `findBySku` relies on entity field `sku`.
- **JPQL** uses entity name `Product` and property `priceCents`.
- **Native SQL** uses actual PostgreSQL table `products` and column `sku`.
- **Page** requires `Pageable`, and may run an additional count query for `totalElements`.
- **Sorting** by price plus an `id` tie-breaker keeps order deterministic when rows share the same price.
- **ILIKE** is PostgreSQL-specific, fitting the integration goal.

`:fragment` is safely bound without concatenating user input into raw SQL. However, `%`/`_` in user input remain LIKE/ILIKE pattern wildcards; if business needs **literal substring search**, escape them. Parameter binding prevents SQL injection without automatically escaping wildcard semantics.

## 12. ProductRepositoryPostgresTest.java — complete JUnit 5 suite

File `src/test/java/example/catalog/ProductRepositoryPostgresTest.java`:

~~~java
package example.catalog;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.TestTransaction;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(
    showSql = false,
    properties = {
        "spring.jpa.hibernate.ddl-auto=validate",
        "spring.flyway.enabled=true"
    })
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class ProductRepositoryPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("catalog_it")
                .withUsername("catalog")
                .withPassword("catalog");

    @Autowired ProductRepository repository;
    @Autowired TestEntityManager entityManager;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void seedRows() {
        repository.saveAll(List.of(
            new Product("P-ALPHA", "Alpha", 1200, true),
            new Product("P-BETA", "Beta", 2500, true),
            new Product("P-GAMMA", "Gamma", 2500, false)
        ));
        repository.flush();
        entityManager.clear();
    }

    @Test
    void connectsToActualPostgres() {
        String database = jdbc.queryForObject(
                "SELECT current_database()", String.class);

        assertEquals("catalog_it", database);
        assertTrue(postgres.isRunning());
    }

    @Test
    void readsProductAndMapsColumns() {
        Product found = repository.findBySku("P-ALPHA")
                .orElseThrow();

        assertNotNull(found.getId());
        assertEquals("Alpha", found.getName());
        assertEquals(1200L, found.getPriceCents());
        assertTrue(found.isEnabled());
    }

    @Test
    void unknownSkuIsEmpty() {
        assertTrue(repository.findBySku("MISSING").isEmpty());
        assertFalse(repository.existsBySku("MISSING"));
    }

    @Test
    void filtersAndSortsEnabled() {
        List<String> skus = repository
                .findByEnabledTrueOrderByPriceCentsAscIdAsc()
                .stream()
                .map(Product::getSku)
                .toList();

        assertEquals(
                List.of("P-ALPHA", "P-BETA"), skus);
    }

    @Test
    void paginatesEnabledProducts() {
        repository.saveAndFlush(
                new Product("P-DELTA", "Delta", 500, true));

        Sort order = Sort.by(
                Sort.Order.asc("priceCents"),
                Sort.Order.asc("id"));

        Page<Product> first = repository.findByEnabledTrue(
                PageRequest.of(0, 2, order));

        assertEquals(3L, first.getTotalElements());
        assertEquals(2, first.getTotalPages());
        assertEquals(
                List.of("P-DELTA", "P-ALPHA"),
                first.getContent().stream()
                        .map(Product::getSku).toList());

        Page<Product> second = repository.findByEnabledTrue(
                PageRequest.of(1, 2, order));

        assertEquals(1, second.getNumberOfElements());
        assertEquals("P-BETA",
                second.getContent().get(0).getSku());
    }

    @Test
    void executesJpqlPriceRange() {
        List<String> skus = repository
                .findByPriceRange(1000, 1500)
                .stream()
                .map(Product::getSku)
                .toList();

        assertEquals(List.of("P-ALPHA"), skus);
    }

    @Test
    void executesNativePostgresIlike() {
        List<String> skus = repository
                .findBySkuFragmentIgnoreCase("alpha")
                .stream()
                .map(Product::getSku)
                .toList();

        assertEquals(List.of("P-ALPHA"), skus);
    }

    @Test
    void dirtyCheckingPersistsUpdate() {
        Product managed = repository.findBySku("P-ALPHA")
                .orElseThrow();
        managed.changePrice(1750);

        entityManager.flush();
        entityManager.clear();

        Product reread = repository.findBySku("P-ALPHA")
                .orElseThrow();

        assertEquals(1750L, reread.getPriceCents());
    }

    @Test
    void deleteRemovesRow() {
        Long id = repository.findBySku("P-BETA")
                .orElseThrow().getId();

        repository.deleteById(id);
        repository.flush();
        entityManager.clear();

        assertFalse(repository.existsBySku("P-BETA"));
    }

    @Test
    void uniqueConstraintRejectsDuplicate() {
        assertThrows(DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(
                    new Product("P-ALPHA", "Duplicate",
                            100, true)));
        // Do not run more SQL in this failed PostgreSQL transaction.
    }

    @Test
    void checkRejectsNegativePrice() {
        assertThrows(DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(
                    new Product("P-BAD", "Bad", -5, true)));
        // Database CHECK rejects value during SQL execution.
    }

    @Test
    void databaseTimestampIsCreated() {
        Boolean exists = jdbc.queryForObject(
                """
                SELECT created_at IS NOT NULL
                FROM products
                WHERE sku = ?
                """,
                Boolean.class, "P-ALPHA");

        assertEquals(Boolean.TRUE, exists);
    }

    @Test
    void flywayMigrationApplied() {
        Long count = jdbc.queryForObject(
                """
                SELECT COUNT(*)
                FROM flyway_schema_history
                WHERE success = TRUE
                """,
                Long.class);

        assertNotNull(count);
        assertTrue(count >= 1);
    }

    @Test
    void transactionRollsBackAcrossBoundary() {
        String sku = "P-ROLLBACK";
        repository.saveAndFlush(
                new Product(sku, "Temporary", 10, true));

        assertTrue(repository.existsBySku(sku));

        TestTransaction.flagForRollback();
        TestTransaction.end();

        try {
            Long remaining = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM products WHERE sku = ?",
                    Long.class, sku);
            assertEquals(0L, remaining);
        } finally {
            TestTransaction.start();
        }
    }
}
~~~

**14 `@Test` methods** are written in this file. `@BeforeEach` creates shared fixtures inside the test-managed transaction. The two constraint tests expect exceptions, so they PASS when the database actually rejects the statements.

### What does each method prove?

| Test | Layer verified |
| --- | --- |
| connectsToActualPostgres | JDBC to real database, not H2 |
| readsProductAndMapsColumns | Entity mapping + derived query |
| unknownSkuIsEmpty | Optional/exists semantics |
| filtersAndSortsEnabled | Derived filter and sort |
| paginatesEnabledProducts | Page content, count, tie-breaker |
| executesJpqlPriceRange | JPQL and named parameters |
| executesNativePostgresIlike | PostgreSQL SQL dialect |
| dirtyCheckingPersistsUpdate | JPA dirty checking + flush/clear |
| deleteRemovesRow | DELETE and requery |
| uniqueConstraintRejectsDuplicate | Database UNIQUE |
| checkRejectsNegativePrice | Database CHECK |
| databaseTimestampIsCreated | DB default CURRENT_TIMESTAMP |
| flywayMigrationApplied | Versioned migration history |
| transactionRollsBackAcrossBoundary | Spring test transaction rollback |

This is expected coverage from source code, **not a Gradle execution result**.

## 13. Data seeding and test isolation

Each method's fixture consists of:

| SKU | price_cents | enabled |
| --- | ---: | --- |
| P-ALPHA | 1200 | true |
| P-BETA | 2500 | true |
| P-GAMMA | 2500 | false |

Tests must not depend on method execution order. `@DataJpaTest` opens a transaction per test method by default; `@BeforeEach` runs inside that test-managed transaction, so seeded rows roll back after each test. This differs from Flyway migrations, which run at context startup and **do not roll back** after each method.

If a test disables transactions or uses `@Commit`, fixture data can leak to subsequent methods. In that case, perform explicit cleanup or use a separate database/schema. Never assume a static container resets data automatically between methods: the container holds the process, while rollbacks/fixtures maintain isolation.

### Sequence IDs do not necessarily roll back

PostgreSQL sequences can advance even when transaction inserts roll back. Never assert `id == 1` in a test method when a suite has multiple methods. Assert only that the ID is non-null or use the ID returned by the repository; never hardcode identity values.

## 14. Flush and clear: proving real SQL

JPA keeps managed entities in the first-level persistence context. Calling `save` then `findById` with the same ID can cause `EntityManager` to return the managed object rather than making a DB roundtrip.

Compare this fragment:

~~~java
Product p = repository.save(new Product(
        "P-EXTRA", "Extra", 100, true));

Product maybeManaged = repository.findById(p.getId())
        .orElseThrow();
~~~

This **does not** prove all column mappings and SELECT execution worked as you think.

Make the SQL boundary explicit:

~~~java
Product saved = repository.saveAndFlush(new Product(
        "P-EXTRA", "Extra", 100, true));

entityManager.clear();

Product fromDb = repository.findById(saved.getId())
        .orElseThrow();
~~~

These fragments illustrate transaction/repository testing and are not added to the full class because doing so would change the method count. `flush` pushes pending changes to JDBC/DB; `clear` detaches managed entities so the subsequent read is not masked by the first-level context. `flush` **is not commit**: rows may have been INSERTed in the DB yet still roll back at the end of the method.

### Identity generation nuance

With PostgreSQL identity columns and JPA `GenerationType.IDENTITY`, Hibernate may have to execute INSERT early to obtain the ID, even before an explicit flush. That is no reason to skip flushing: it keeps SQL error detection timing consistent with batched/deferred inserts, updates, and deletes.

### Dirty checking vs detached entity

An entity loaded inside a transaction is managed; mutating a field and flushing generates an UPDATE. After `entityManager.clear()`, the old reference is detached, and further mutations do not automatically update the database. To persist detached changes, merge/save per JPA semantics and verify the real outcome.

## 15. Why must constraint tests assert after flush?

In PostgreSQL:

- Duplicate SKU violates the UNIQUE constraint: SQLSTATE `23505`.
- Negative price violates CHECK: SQLSTATE `23514`.
- After a statement error inside a transaction, subsequent SQL statements can return `25P02` (“current transaction is aborted”).

Therefore the test:

~~~java
assertThrows(
    DataIntegrityViolationException.class,
    () -> repository.saveAndFlush(
        new Product("P-ALPHA", "Duplicate", 100, true)));
~~~

is on the right track; it forces the repository to send SQL and verifies Spring exception translation. `save` without flushing may return before the DB checks the constraint (depending on ID strategy and Hibernate), producing hard-to-explain false PASS/FAIL negative tests.

**After `assertThrows`, do not run another query inside the same PostgreSQL transaction**, because the DB may be in an aborted state. Spring's rollback at the end of the test cleans up the state. If you genuinely need to query after an error, use a separate explicitly designed transaction/savepoint boundary or a separate test.

### Java validation differs from database constraints

If you put `@Min(0)` or a constructor guard on `priceCents`, the code can throw before sending SQL; the test would then prove Java validation rather than CHECK. The sample intentionally keeps the constructor simple so negative prices reach Postgres. Production should still keep both API/service validation **and** DB constraints.

### SQLSTATE vs exception messages

If business logic needs to distinguish unique vs check violations, walk the cause chain to `java.sql.SQLException.getSQLState()` and assert `23505`/`23514`. Hibernate/Spring wrappers can change across versions, and error messages can depend on locale/driver. Never write tests coupled to full message strings.

## 16. Testing rollback with `TestTransaction`

A flawed approach is having test method A INSERT and test method B expect A's row to be missing. JUnit does not guarantee A runs before B; B could PASS even when rollback is broken.

`TestTransaction` gives a test a controlled transaction boundary within **the same method**:

1. The test transaction created by `@DataJpaTest` is used to seed/write.
2. `TestTransaction.flagForRollback()` marks it for rollback.
3. `TestTransaction.end()` ends and rolls back the test transaction.
4. A subsequent JDBC query uses another connection/transaction and confirms the record is gone.
5. `TestTransaction.start()` starts a new test-managed transaction so afterTest callbacks clean up normally.

The complete example appears in `transactionRollsBackAcrossBoundary` and uses `try/finally` to restart even if assertions fail.

Never use `TestTransaction` outside a Spring TestContext-managed transaction. In a test with `@Transactional(propagation=NOT_SUPPORTED)` or a pure unit test, there is no active test transaction to end.

### Cases default rollback does not cover

- An HTTP server under `@SpringBootTest(RANDOM_PORT)` handles requests on a different thread/transaction than the test caller.
- Async/scheduled tasks run on different thread pools.
- `REQUIRES_NEW` transactions can commit independently.
- Flyway migrations run at context initialization.
- External Kafka/Redis side effects.
- JDBC operations on another DataSource/transaction manager.

Distinguish test-managed transactions, Spring-managed transactions, and application-managed transactions. Never use `assertTimeoutPreemptively` in a transactional test without checking ThreadLocal semantics: code running on another thread may not join the rollback.

## 17. Pagination, sorting, and count queries

Pagination tests need more than a single empty page. In the sample, adding `P-DELTA` at price 500 with `enabled=true` brings total enabled rows to 3. With page size 2:

- Page 0: `P-DELTA` and `P-ALPHA`.
- Page 1: `P-BETA`.
- `getTotalElements() == 3`.
- `getTotalPages() == 2`.

`Page<T>` includes total count; `Slice<T>` usually skips the full count. For custom native queries with JOIN/GROUP BY, framework-generated count queries can be wrong; assert `totalElements` on fixtures containing duplicates/filters and declare `countQuery` when needed.

**`ORDER BY` must be deterministic:** when multiple rows share `priceCents`, also sort by `id`. Ordering only by price gives PostgreSQL no guarantee of stable row ordering across runs or page boundaries.

## 18. JPQL vs native PostgreSQL queries

### JPQL

~~~java
@Query("""
       select p from Product p
       where p.priceCents >= :min and p.priceCents <= :max
       order by p.priceCents, p.id
       """)
List<Product> range(@Param("min") long min,
                    @Param("max") long max);
~~~

`Product` is the JPA entity name and `priceCents` is the Java property. Those are not SQL table/column names.

### Native PostgreSQL

~~~java
@Query(
    value = """
            SELECT *
            FROM products
            WHERE sku ILIKE CONCAT('%', :term, '%')
            ORDER BY id
            """,
    nativeQuery = true)
List<Product> search(@Param("term") String term);
~~~

`products`/`sku` are the PostgreSQL table/column; `ILIKE` is a DB-specific operator. Both snippets are **illustrative fragments**; the runnable file defines the corresponding methods.

Native SQL should use bound parameters rather than string concatenation of user input. For literal substring search, escape LIKE wildcards `%` and `_`. For complex Unicode/collation rules, test the target locale because case folding can differ from ASCII English.

## 19. Should you use `@Sql` to seed fixtures?

`@Sql` is useful when multiple repository test classes share a fixed dataset or need SQL INSERTs outside entity mappings:

~~~java
@Sql(
    scripts = "/sql/products.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
~~~

This is an annotation fragment requiring `src/test/resources/sql/products.sql`, imports, and a test class. `@Sql` supports transaction modes; for example, `@SqlConfig(transactionMode=ISOLATED)` commits fixtures before the test and **does not roll back with the test**. If used, design cleanup explicitly.

Options:

| Fixture strategy | Benefit | Risk |
| --- | --- | --- |
| `@BeforeEach` via repository | Readable, valid entities | Only tests data creatable via JPA |
| `TestEntityManager` | Explicit flush/clear | Alters persistence context |
| `JdbcTemplate` raw SQL | DB-only columns/legacy rows | Must manage table/column names |
| `@Sql` files | Large/versioned datasets | Transaction mode and cleanup |
| Flyway migration | Schema source of truth | Should not hold per-method fixtures |
| Separate database per test | Strong isolation | Slow startup, requires Docker capacity |

If a test needs to verify the repository reads raw SQL rows not seeded via Hibernate, JDBC/`@Sql` is a strong strategy. Never delete production migrations to clean up test data.

## 20. `@ServiceConnection` vs `@DynamicPropertySource`

The sample uses `@ServiceConnection` because Spring Boot 3.5 supports connection details from `PostgreSQLContainer`, covering both JDBC and Flyway.

An alternative when custom properties are needed:

~~~java
@DynamicPropertySource
static void databaseProperties(
        DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username",
            postgres::getUsername);
    registry.add("spring.datasource.password",
            postgres::getPassword);
}
~~~

This fragment assumes static `postgres`, imports, and a test class. **Do not mix both approaches** without knowing precedence; if the app configures a separate Flyway connection URL, verify Flyway targets the same DB as JPA.

### Why not use a `jdbc:tc:postgresql` URL here?

Testcontainers also supports JDBC URLs like `jdbc:tc:postgresql:16-alpine:///catalog_it`, starting the container along with JDBC connection lifecycle. That is a valid alternative with different ownership; this lesson prefers an explicit `PostgreSQLContainer` to use `@ServiceConnection`, check `isRunning()`, and manage lifecycle transparently.

## 21. Static `@Container` and the Spring TestContext cache

A static `@Container` in JUnit Jupiter normally lives for **one test class**, not automatically the entire suite. The Spring TestContext cache can retain an `ApplicationContext` across multiple classes sharing the same cache key. If class A stops the DB after running and class B reuses the cached context, the `DataSource` can point to a stopped container.

### Spring-managed container bean

When multiple classes share a context, Spring Boot 3.5 lets you tie container lifecycle to the `ApplicationContext` via test configuration:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class PostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
~~~

This snippet needs imports, and classes use `@Import(PostgresTestConfig.class)`. Spring manages bean lifecycle and closes the DB when the cached context closes, rather than the JUnit extension stopping it right after class A. You can also consider `@ImportTestcontainers` per Boot docs.

Do not attach Jupiter's `@Container` lifecycle to a Spring-owned bean at the same time without deciding who owns stop/cleanup.

### Reusable containers and CI

Testcontainers `withReuse(true)` is an opt-in/experimental feature not suited for general CI per official docs: it can retain containers and data across runs, making tests nondeterministic. On shared runners, do not enable it just to save startup time without data isolation and cleanup policies.

## 22. Running Gradle on a developer machine

Linux/macOS:

~~~bash
./gradlew clean test
./gradlew test --tests '*ProductRepositoryPostgresTest'
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
.\gradlew.bat test --tests '*ProductRepositoryPostgresTest'
~~~

A corresponding Gradle wrapper file is required. If the task is `UP-TO-DATE`, Gradle might not re-run tests; to force execution:

~~~bash
./gradlew test --rerun-tasks
~~~

`--rerun-tasks` forces dependent tasks to re-run, so do not treat total build wall time as a PostgreSQL startup benchmark. Test logs/reports are located at:

~~~text
build/test-results/test/TEST-*.xml
build/reports/tests/test/index.html
~~~

### Expected outcome

The 14 `@Test` methods in the source are designed to PASS when Docker, PostgreSQL, and Flyway versions align. Both `uniqueConstraintRejectsDuplicate` and `checkRejectsNegativePrice` intentionally assert exceptions thrown by the DB — this is an **expected PASS**, not a SQL failure failing the test. No specific stdout is assumed for container port or startup duration.

This lesson did not execute Gradle or Docker; outcomes described here are design/expected behavior, not observed runtime evidence.

## 23. GitHub Actions CI running PostgreSQL Testcontainers

`.github/workflows/repository-tests.yml`:

~~~yaml
name: PostgreSQL Repository Integration Tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  jpa-tests:
    runs-on: ubuntu-24.04
    timeout-minutes: 30

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Gradle
        uses: gradle/actions/setup-gradle@v4

      - name: Docker preflight
        shell: bash
        run: |
          set -euo pipefail
          docker version
          docker info --format 'Docker server={{.ServerVersion}}'
          df -h
          df -i

      - name: Run repository tests
        shell: bash
        run: |
          chmod +x ./gradlew
          ./gradlew --no-daemon clean test --stacktrace

      - name: Diagnostics on failure
        if: failure()
        shell: bash
        run: |
          docker ps -a || true
          docker system df || true
          df -h || true

      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: postgres-jpa-test-results
          path: |
            build/test-results/test/
            build/reports/tests/test/
          if-no-files-found: warn
          retention-days: 7
~~~

This workflow runs **directly on the Ubuntu VM**, with no job-level `container:` and no `services.postgres` declaration (since Testcontainers manages Postgres). Docker is normally present on GitHub-hosted Ubuntu runners, though preflight still verifies it.

On GitLab/Kubernetes runners, provision an appropriate Docker API-compatible runtime and mapped-port routing: Docker-in-Docker, socket passthrough, or a managed remote runtime per security policy. Never expose an unencrypted TCP Docker API on an untrusted network, and never grant host socket access to untrusted fork PRs.

Upload JUnit reports with `if: always()` to distinguish missing Docker, Flyway failures, SQL assertions, or skipped tests. Never upload Docker credentials, TLS private keys, DB test secrets, or shared daemon resources belonging to other jobs.

## 24. Performance optimization without sacrificing integration coverage

Starting a container can spend time pulling images, creating/starting Docker containers, initializing PostgreSQL, and running the wait strategy. The Spring context also runs Flyway migrations, Hibernate metadata scanning, and Hikari pool creation. Measure stages separately:

~~~text
Docker image pull/cache lookup
    |
postgres.start() and DB ready
    |
Spring @DataJpaTest context + Flyway + Hibernate validate
    |
@BeforeEach seed rows
    |
repository method execution
    |
transaction rollback
    |
container stop/cleanup
~~~

If CI is slow, measure the exact boundary first:

- Cold image pull vs warm image cache.
- Context cache hit vs cache miss.
- Gradle `Test` task wall time vs single repository method latency.
- One static container per class vs instance container per method.
- Multiple Gradle forks/CI jobs multiplying containers and RAM usage.
- `@DirtiesContext` after every method causing unnecessary context reloads.
- `@DataJpaTest` is usually lighter than full `@SpringBootTest` for repository-only tests, but never replace integration/full tests when business wiring is required.

**Never add hard-coded timeout assertions** forcing `postgres.start() < 2s` on shared CI. Docker, network, registry, and runner specs vary; if you need a performance regression gate, collect baselines across multiple runs using median/p95 on a controlled machine.

## 25. Troubleshooting real errors

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| No valid Docker environment | Daemon/socket/TLS | Docker preflight in the right job |
| Ryuk privilege denied | Runner policy | Dedicated runtime or cleanup plan |
| Image 401/403/429 | Registry | Token/mirror/rate limit |
| Postgres exit 137 | OOM/SIGKILL | Cgroup RAM/Gradle forks |
| No space left | Docker layers/inodes | `df -h`, `df -i`, `docker system df` |
| JDBC connection refused | Host/mapped port | `getJdbcUrl`, host/port routing |
| Flyway unsupported DB | Missing database-specific module | `flyway-database-postgresql` |
| Flyway checksum mismatch | V1 migration edited | New migration/version governance |
| Relation products missing | Flyway didn't apply/wrong schema | Check startup logs/history |
| Hibernate validate error | Entity vs SQL schema | Compare `@Column` with DDL |
| SQL 23505 | Unique violation | Check SKU, catch at SQL flush |
| SQL 23514 | CHECK violation | Verify price and constraint |
| SQL 25P02 | Transaction aborted | Stop queries/rollback |
| Wrong page total | Count-query/filters | Seed enough cases, assert totals |
| Test ignored/skipped | JUnit tags/conditions | Mandatory CI gate |
| Cached context points to stopped DB | Lifecycle mismatch | Spring-owned container |
| Slow startup | Cold image/context/Flyway | Measure each stage |

### Flyway startup failures are not repository bugs

If Flyway fails to create `products`, repository tests fail during context load or the first query. Do not “fix” it by running `CREATE TABLE` in `@BeforeEach`: that hides production migration failures. Fix the Flyway module, script, or migration compatibility.

### Do not run further queries after a constraint error

A Postgres transaction can enter an aborted state after a duplicate or check violation. If a test then calls `findAll`, it gets `25P02` instead of the expected data. Assert the exception and let the transaction roll back, or split transaction boundaries properly.

### Do not fall back to H2 when Docker is unavailable

If production SQL depends on PostgreSQL, falling back to H2 makes CI green while leaving the integration contract untested. Route tests to a Docker-enabled runner or fail loudly on missing environments; never silently skip mandatory suites.

## 26. Migrations, concurrency, and data locking

CRUD tests suffice for basic repository behavior, yet do not prove advanced contracts:

- Atomic stock reservations and lost updates.
- Optimistic locking `@Version`/`OptimisticLockingFailureException`.
- Pessimistic row locks `@Lock(PESSIMISTIC_WRITE)`.
- Deadlocks and retry policies.
- Concurrent inserts of the same SKU and unique-key races.
- Transactions with `REQUIRES_NEW`/async threads.
- PostgreSQL `JSONB`/`ON CONFLICT`/partial indexes.

These require **two or more independent transactions/threads** with clear barriers/timing. A single-threaded `@DataJpaTest` method does not prove isolation or concurrency. Never launch a helper thread inside a test-managed transaction assuming the transaction context propagates; Spring transactions are usually thread-bound.

### SQL indexes are not proved by three test rows

V1 creates an index, yet the PostgreSQL optimizer may pick a sequential scan on tiny tables. Verify functional results in JUnit; verify performance/index plans with a sufficiently large dataset, `EXPLAIN (ANALYZE, BUFFERS)`, and a controlled environment. Do not assert that a query always uses an index in a three-row fixture.

## 27. Practice checklist

- [ ] Tests use real PostgreSQL, without mocking the repository or substituting embedded H2.
- [ ] A Docker-compatible runtime is reachable from the test JVM.
- [ ] `@DataJpaTest` loads the right entities and Spring Data repositories.
- [ ] `@AutoConfigureTestDatabase(replace=NONE)` preserves the real datasource.
- [ ] `@ServiceConnection` and `spring-boot-testcontainers` are present.
- [ ] PostgreSQL image version is pinned, and host port 5432 is not hardcoded.
- [ ] Flyway V1 migration executes with `flyway-database-postgresql`.
- [ ] Hibernate `ddl-auto=validate` does not create/drop schemas.
- [ ] JPA entity `@Column` mappings match the DDL.
- [ ] Fixtures include enabled/disabled rows, equal prices, and boundary cases.
- [ ] Flush and clear are called before verifying database roundtrips.
- [ ] Derived queries, JPQL, and native PostgreSQL `ILIKE` are tested.
- [ ] Pagination tests check `totalElements`, `totalPages`, and stable ordering.
- [ ] UNIQUE/CHECK tests execute SQL and assert exceptions at the flush boundary.
- [ ] No further queries run inside an aborted PostgreSQL transaction.
- [ ] Database-generated defaults are verified via JDBC.
- [ ] `TestTransaction`/rollback tests do not depend on test ordering.
- [ ] Static container lifecycle does not conflict with cached contexts across multiple classes.
- [ ] Reusable containers are not enabled in CI lacking isolation.
- [ ] Tests do not assert exact sequence-generated IDs across methods.
- [ ] CI has Docker preflight, JUnit reports, and a policy against skipping integration tests.
- [ ] Registry/database secrets are never exposed in uploaded logs.
- [ ] Performance is measured by DB/container/context/SQL stages rather than lumped together.

## 28. Conclusion

**Testing repositories against a real database means JPA → JDBC → a PostgreSQL server actually executing SQL, migrations, and constraints.** The example uses `@DataJpaTest` to start the JPA slice, `@ServiceConnection` to connect `PostgreSQLContainer`, `@AutoConfigureTestDatabase(replace=NONE)` to prevent H2 replacement, Flyway to build the schema, and Hibernate to validate mappings.

The 14 tests in the project verify reads/writes/deletes, sorting, pagination, JPQL, PostgreSQL `ILIKE`, unique/CHECK constraints, DB defaults, migrations, and rollbacks. When applying this to a real project, preserve fixture isolation, flush/clear at the right boundaries, prevent cached contexts from pointing to stopped containers, and run the integration suite in Docker-enabled CI. Repository mocks remain useful at the **unit layer**, but they do not replace these real SQL checks.

### Official documentation

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@DataJpaTest`, `TestEntityManager`, `@AutoConfigureTestDatabase`.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection`, `FlywayConnectionDetails`, Spring-managed containers.
- [Spring Boot 3.5 — Database Initialization](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html): Flyway and Hibernate DDL.
- [Spring Framework 6.2 — Test Transactions](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): `TestTransaction`, rollback, thread boundaries.
- [Spring Framework 6.2 — Executing SQL Scripts](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/executing-sql.html): `@Sql` and transaction modes.
- [Testcontainers Java — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): `PostgreSQLContainer` and mapped JDBC URLs.
- [Testcontainers Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers` and static/instance `@Container`.
- [Testcontainers Java — Reuse](https://java.testcontainers.org/features/reuse/): experimental reuse, unsuitable for CI.
- [Flyway — PostgreSQL Database](https://documentation.red-gate.com/flyway/reference/database-driver-reference/postgresql-database): Flyway database plugin.
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): named parameters, JPQL, native queries.
- [PostgreSQL 16 — Constraints](https://www.postgresql.org/docs/16/ddl-constraints.html): UNIQUE/CHECK/identity.
- [PostgreSQL 16 — Error Codes](https://www.postgresql.org/docs/16/errcodes-appendix.html): 23505/23514/25P02.
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): `useJUnitPlatform`, reports.
