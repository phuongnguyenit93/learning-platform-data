# Separating Test Data from Application Seed Data

## 1. Why Separate Them?

In a Spring Boot application, data loaded at startup and data prepared for tests are often lumped together as **seed data**. Yet these two sources serve different goals. Demo data lets developers launch the app and see a few products; test fixtures exist solely to create preconditions for verifying a behavior; mandatory reference data is part of the business contract. When mixed, repository tests accidentally rely on demo products, CI runs differently from local machines, or Test A leaves data that breaks Test B.

For example, a test asserting:

```java
assertEquals(3L, catalogRepository.count());
```

is brittle if those three products were seeded by a global startup runner: someone updating the demo can add a fourth product without changing any repository logic. A red test reflects coupling to demo data rather than a business regression.

This lesson belongs to the **Test Data** group and focuses specifically on **“Separating Test Data from Application Seed Data.”** We use **Java 17+, Spring Boot 3.3.5**, Spring Data JPA/Hibernate, H2, JUnit Jupiter, and Spring Test `@Sql`. The goal is a complete runnable example project with commands and concrete assertions.

### After This Lesson

- Distinguish **reference data**, **development/demo seeds**, and **per-test fixtures**.
- Understand all mechanisms that can auto-load data: `data.sql`, `import.sql`, Flyway/Liquibase, `ApplicationRunner`, `CommandLineRunner`, and `@Sql`.
- Know why placing fixtures in `src/test/resources` keeps them out of production JARs, yet **does not stop main resources from participating in test runtime**.
- Use `@Profile("dev")` to isolate demo seeds, `@ActiveProfiles("test")` for test config, and `spring.sql.init.mode=never` to disable automatic SQL initialization.
- Load dedicated fixtures from `src/test/resources/fixtures/catalog-items.sql` with `@Sql`.
- Understand `@DataJpaTest` default transaction rollback, as well as why real HTTP/server threads execute outside the test's transaction.
- Verify that the `test` profile contains no demo rows, test fixtures load only when declared, and the `dev` profile actually seeds demo data.
- Design data factories, migrations, cleanup, CI, and database isolation for reproducible suites.

**Scope:** the example targets Spring Boot 3.3.5 so imports and APIs stay consistent. Systems on other versions must verify package names and version-specific behavior; do not treat 3.3.5 as the latest release.

## 2. Three Kinds of Data That Must Have Separate Ownership

| Data Kind | Examples | Appropriate Location | Allowed in Which Tests? |
| --- | --- | --- | --- |
| Mandatory **reference/master data** | Business status codes, fee types, fixed roles | Official migrations or versioned bootstrap | Tests relying on that contract |
| **Development/demo seed** | Products `DEV-CUP`, `DEV-BAG` for local UI viewing | `dev` profile, dev-only loader, or dev-only script | Only tests explicitly verifying the demo profile |
| **Test/scenario fixture** | `TEST-BOOK`, `TEST-CABLE` for query verification | `src/test/resources`, `@Sql`, test factories | Only tests that declare or construct them |

### Reference Data Is Not “Junk”

Some rows are required for the application to function, such as order statuses and standard business codes. They should be versioned and tested alongside migrations and schemas. Do not strip out all reference rows in tests just to force an empty-database baseline; if production always contains standard code tables, tests should expect and verify them.

### Demo Seeds Are Not a Repository Contract

Demo data changes frequently for UI/UX needs. Repository tests should never assert the price of `DEV-CUP` or the total count of demo rows unless the **demo loader itself** is under test. For query tests, create dedicated, stable, minimal, and discriminating test rows.

### Fixtures Must Not Appear via Hidden Side Effects

Good fixtures are explicit right inside the test class or method: `@Sql("/fixtures/...")`, `repository.save(...)` in `Arrange`, or a test object builder. When a test secretly relies on data inserted by some `ApplicationRunner`, assertions become mysterious and test ordering causes cross-test pollution.

In this sample project, there is **no mandatory reference data**, so JPA tests without fixtures can assert `count() == 0`. In production systems with reference tables, adjust the baseline and filter by namespace or row scope instead of assuming the whole database is empty.

## 3. How Data Appears in Spring Boot

| Mechanism | When It Runs | Risk |
| --- | --- | --- |
| `schema.sql`/`data.sql` | Spring Boot SQL initializer | Main resources can auto-run against embedded test databases |
| `schema-PLATFORM.sql`/`data-PLATFORM.sql` | When `spring.sql.init.platform` is set | Dataset changes depending on platform |
| Hibernate `import.sql` | When Hibernate generates schemas via `create`/`create-drop` | Can still seed even if Boot's SQL initializer is disabled |
| Flyway/Liquibase | Migrations at context initialization | Test-only data accidentally placed in production migrations |
| `CommandLineRunner`/`ApplicationRunner` | After application context startup | Unguarded loaders execute during tests |
| `@PostConstruct`/event listeners | Bean/app lifecycle | Implicit seed side effects with unclear call sites |
| `@Sql` | TestContext per annotation and execution phase | Class-level fixtures give unrelated tests unwanted rows |
| `@BeforeEach`/factories | Test method lifecycle | Bloated fixtures or shared mutable objects |
| External DB snapshot/bootstrap | Before tests start | Duplicate data or drift from current schema |

### Spring Boot SQL Init and Default Behavior

Spring Boot 3.3 looks for locations matching `optional:classpath*:schema.sql` and `optional:classpath*:data.sql`. With embedded databases, the SQL initializer can run automatically under default policy. `spring.sql.init.mode=always` runs the initializer even on non-embedded datasources when scripts exist, while `spring.sql.init.mode=never` disables Boot's SQL script initialization specifically.

If `data.sql` must run **after** Hibernate creates the schema, Boot provides `spring.jpa.defer-datasource-initialization=true`. Even so, mixing multiple schema-management mechanisms makes ordering brittle. When using a migration tool, prefer one clear schema owner.

**Trap:** `spring.sql.init.mode=never` **does not** disable Hibernate's `import.sql`, Flyway/Liquibase, runners, or `@Sql` scripts explicitly requested by tests.

### Why `src/test/resources` Alone Is Not Enough

Gradle's test runtime sees both main and test classes/resources. Placing test fixtures in `src/test/resources` **keeps them out of the production executable JAR**, yet `src/main/resources/data.sql` still sits on the test classpath. You must control both **loading paths** and **profiles**, not merely move a few files around.

## 4. Demo Architecture: Load Demo Data Only Under the `dev` Profile

```text
PRODUCTION-LIKE DEFAULT:
  application.yml: SQL auto init disabled
  No main data.sql or import.sql

DEV:
  application-dev.yml: H2 and ddl-auto=create-drop
  @Profile("dev") ApplicationRunner -> DEV-CUP, DEV-BAG

TEST:
  application-test.yml: H2 test schema, SQL auto init disabled
  @DataJpaTest + @ActiveProfiles("test")
  Does not auto-load demo runner
  @Sql("/fixtures/catalog-items.sql") -> loads TEST-* only when needed
  Test transaction rolls back after each method
```

This is a learning design, not a production database configuration: never use Hibernate `create-drop` on real data and never use H2 in production just for convenience.

## 5. Complete Java 17+ Project

Directory tree:

```text
isolated-test-data/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/catalog/
│   ├── CatalogApplication.java
│   ├── CatalogItem.java
│   ├── CatalogRepository.java
│   └── DevCatalogSeedConfig.java
├── src/main/resources/
│   ├── application.yml
│   └── application-dev.yml
├── src/test/java/com/example/catalog/
│   ├── CatalogTestObjects.java
│   ├── CatalogWithoutSeedTest.java
│   ├── CatalogFixtureSqlTest.java
│   └── DevSeedProfileTest.java
└── src/test/resources/
    ├── application-test.yml
    └── fixtures/catalog-items.sql
```

### 5.1. settings.gradle

```groovy
rootProject.name = 'isolated-test-data'
```

### 5.2. build.gradle

```groovy
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
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

`spring-boot-starter-data-jpa` provides Hibernate/JPA and Spring Data repositories. H2 needs `runtimeOnly` so both the dev app and test runtime have the driver. `spring-boot-starter-test` provides JUnit Jupiter, Spring TestContext, `@DataJpaTest`, and assertions.

The Gradle Wrapper is omitted from the illustrative directory tree; if the project does not have `gradlew`, generate the Wrapper using a compatible Gradle version or run `gradle test` on a machine with Gradle installed. Do not run `./gradlew` in a directory without a Wrapper and treat the missing file error as a test failure.

### 5.3. CatalogApplication.java

`src/main/java/com/example/catalog/CatalogApplication.java`:

```java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

The application root shares the package with entities, repositories, and configuration. Spring Boot's component scan locates the dev seed config in a full context, whereas `@DataJpaTest` uses the package hierarchy to find the Boot configuration while intentionally loading only the JPA slice.

## 6. Entity and Repository

### 6.1. CatalogItem.java

`src/main/java/com/example/catalog/CatalogItem.java`:

```java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "catalog_items")
public class CatalogItem {

    @Id
    @Column(nullable = false, length = 40)
    private String sku;

    @Column(nullable = false, length = 160)
    private String title;

    @Column(name = "price_cents", nullable = false)
    private int priceCents;

    @Column(nullable = false)
    private boolean featured;

    protected CatalogItem() {
        // JPA constructor.
    }

    public CatalogItem(
            String sku, String title,
            int priceCents, boolean featured) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is required");
        }
        if (priceCents < 0) {
            throw new IllegalArgumentException(
                    "priceCents must be non-negative");
        }

        this.sku = sku;
        this.title = title;
        this.priceCents = priceCents;
        this.featured = featured;
    }

    public String getSku() {
        return sku;
    }

    public String getTitle() {
        return title;
    }

    public int getPriceCents() {
        return priceCents;
    }

    public boolean isFeatured() {
        return featured;
    }
}
```

`sku` is an explicitly assigned ID: values like `TEST-BOOK` and `DEV-CUP` are always predictable regardless of whether an auto-increment sequence rolls back. `priceCents` uses integer minor units to avoid `double` monetary comparisons in tests.

The class provides a protected no-arg constructor for JPA. It is not a Java record because JPA entities require mutable/managed Hibernate lifecycles. The constructor enforces local Java invariants; when real database `CHECK`, `UNIQUE`, or foreign-key constraints are needed, declare them in the matching schema/migration.

### 6.2. CatalogRepository.java

`src/main/java/com/example/catalog/CatalogRepository.java`:

```java
package com.example.catalog;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CatalogRepository
        extends JpaRepository<CatalogItem, String> {

    List<CatalogItem> findByFeaturedTrueOrderBySkuAsc();

    List<CatalogItem> findByPriceCentsBetweenOrderBySkuAsc(
            int minimum, int maximum);
}
```

Both derived queries are tested against **scenario fixtures**, never relying on demo rows. `OrderBySkuAsc` is specified because SQL does not guarantee row order without `ORDER BY`, even if H2 happens to return rows in primary-key order.

## 7. Default Configuration Does Not Auto-Seed

`src/main/resources/application.yml`:

```yaml
spring:
  sql:
    init:
      mode: never
  jpa:
    open-in-view: false
```

`spring.sql.init.mode=never` disables Spring Boot's JDBC SQL initializer. The project intentionally has **no** `src/main/resources/data.sql` or `src/main/resources/import.sql`. Without the `dev` profile active, the app also has no runner loading demo rows.

**Do not misunderstand:** `mode: never` does not block `ApplicationRunner`, Hibernate `import.sql`, Flyway/Liquibase, or Spring Test `@Sql` if those exist. That is why this architecture pairs it with a positive profile guard on the runner and test assertions confirming no demo rows load.

In real production environments, use Flyway/Liquibase migrations and an external `DataSource`. Never put `create-drop` in the default configuration, where starting against the wrong environment could wipe schemas.

## 8. application-dev.yml and a Guarded ApplicationRunner

`src/main/resources/application-dev.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:catalog_dev;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  jpa:
    hibernate:
      ddl-auto: create-drop
```

`create-drop` is intended for local H2 demos. Hibernate creates the schema when the application context starts and drops it on context shutdown. Never use this setting against a database holding valuable data.

`src/main/java/com/example/catalog/DevCatalogSeedConfig.java`:

```java
package com.example.catalog;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("dev")
public class DevCatalogSeedConfig {

    @Bean
    ApplicationRunner createDemoCatalog(
            CatalogRepository repository) {

        return arguments -> {
            if (!repository.existsById("DEV-CUP")) {
                repository.save(new CatalogItem(
                        "DEV-CUP",
                        "Demo ceramic cup",
                        1250,
                        true));
            }

            if (!repository.existsById("DEV-BAG")) {
                repository.save(new CatalogItem(
                        "DEV-BAG",
                        "Demo canvas bag",
                        4200,
                        false));
            }
        };
    }
}
```

### Why `@Profile("dev")`?

`@Profile("dev")` enables the config and runner only when the `dev` profile is active. This is a **positive allowlist**. Avoid `@Profile("!prod")` for demo data: `test` and `staging` profiles both match `!prod`, causing demo seeds to leak into unintended environments.

`ApplicationRunner` executes after Spring context startup, when the repository is ready for injection. It only populates two fake demo items; it is not a versioned migration mechanism for critical reference data.

### Limited Idempotency

`existsById` prevents a single loader from intentionally inserting duplicates when rerun against an existing key. However, multiple concurrent app instances still face a race between check and save. For production bootstraps, unique constraints and migrations/orchestration are far more reliable than simple check-then-insert loaders.

### Verifying Dev Execution

Example command (with Gradle Wrapper):

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

Because the project has no web starter, this starts the H2 database and runs the dev seed inside the context without exposing any REST endpoints. There is no fixed business stdout because the loader writes no custom log lines.

## 9. application-test.yml and Embedded Test Database

`src/test/resources/application-test.yml`:

```yaml
spring:
  sql:
    init:
      mode: never
  jpa:
    hibernate:
      ddl-auto: create-drop
```

`@DataJpaTest` auto-configures an embedded `DataSource` when H2 is on the test runtime classpath. In our tests we also declare explicitly:

```java
@DataJpaTest
@ActiveProfiles("test")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY)
class ExampleJpaTest {
}
```

This is a **configuration snippet**, not a full test class; real tests follow below. `@ActiveProfiles("test")` activates `application-test.yml` and leaves `dev` inactive. `@AutoConfigureTestDatabase(replace=ANY)` explicitly selects an embedded test `DataSource` rather than any regular `DataSource`.

**Security boundary caveat:** a profile named `test` is not a network sandbox. If a project configures multiple `DataSource`s or custom connectors, verify that every client and transaction manager targets test resources. Never call `repository.deleteAll()` against a production or shared database merely because a test carries `@ActiveProfiles("test")`.

## 10. SQL Fixtures Run Only When Requested by Tests

`src/test/resources/fixtures/catalog-items.sql`:

```sql
INSERT INTO catalog_items
    (sku, title, price_cents, featured)
VALUES
    ('TEST-BOOK', 'Testing Handbook', 1500, TRUE),
    ('TEST-DISPLAY', 'Display', 33000, TRUE),
    ('TEST-CABLE', 'USB Cable', 800, FALSE),
    ('TEST-PEN', 'Blue Pen', 200, FALSE);
```

Because the file is not named `data.sql` and lives under test resources, Boot's SQL initializer never auto-runs it. Tests opt in explicitly using `@Sql`:

```java
@Sql(
    scripts = "/fixtures/catalog-items.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
```

`@Sql` comes from `org.springframework.test.context.jdbc.Sql`. In a transactional `@DataJpaTest` with standard settings, the script executes inside the test-managed transaction before each applicable method and rolls back with the method. **Do not add `SqlConfig.TransactionMode.ISOLATED`** here: if setup commits in its own transaction, the test method's rollback cannot clean it up.

### Why These Four Intentional Rows?

| SKU | Title | Price cents | Featured |
| --- | --- | ---: | --- |
| `TEST-BOOK` | Testing Handbook | 1500 | true |
| `TEST-DISPLAY` | Display | 33000 | true |
| `TEST-CABLE` | USB Cable | 800 | false |
| `TEST-PEN` | Blue Pen | 200 | false |

The featured query must return two rows: `TEST-BOOK` and `TEST-DISPLAY`. The price-range query `[500, 2000]` returns `TEST-BOOK` and `TEST-CABLE`. Both tests assert SKU ordering because the repository methods specify sorting. You do not need thousands of rows to test two derived queries.

### What @Sql Does Not Do

`@Sql` does not turn rows into production seeds, does not create tables if the script only holds `INSERT`s, and does not guarantee rollback if the test lacks a transaction or uses `ISOLATED`. It is simply a TestContext script-execution mechanism governed by its phase and transaction configuration; know those settings before relying on them.

## 11. Java Test Object Factory

`src/test/java/com/example/catalog/CatalogTestObjects.java`:

```java
package com.example.catalog;

final class CatalogTestObjects {

    private CatalogTestObjects() {
    }

    static CatalogItem simpleItem(
            String sku, int priceCents) {
        return new CatalogItem(
                sku, "Test-only item", priceCents, false);
    }
}
```

Each factory call returns a fresh object; there is no shared mutable singleton entity across tests. Factories shine when a method needs a single item with valid defaults, while SQL fixtures suit predictable multi-row query setups.

A factory can support variations via builders, but should never hide key values under test. If a test verifies `featured=true`, make `featured` explicit in `Arrange` rather than burying it inside random defaults.

## 12. CatalogWithoutSeedTest: No Seed Unless Requested

`src/test/java/com/example/catalog/CatalogWithoutSeedTest.java`:

```java
package com.example.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(showSql = false)
@ActiveProfiles("test")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY)
class CatalogWithoutSeedTest {

    @Autowired
    CatalogRepository repository;

    @Test
    void testProfileDoesNotLoadDemoSeed() {
        assertEquals(0L, repository.count());
        assertFalse(repository.existsById("DEV-CUP"));
        assertFalse(repository.existsById("DEV-BAG"));
    }

    @Test
    void createsOnlyItsOwnScenarioRow() {
        CatalogItem item = CatalogTestObjects.simpleItem(
                "TEST-LOCAL", 990);
        repository.saveAndFlush(item);

        assertTrue(repository.existsById("TEST-LOCAL"));
        assertEquals(1L, repository.count());
        assertFalse(repository.existsById("DEV-CUP"));
    }

    @Test
    void noSqlFixtureMeansFixtureSkuIsMissing() {
        assertTrue(repository.findById("TEST-BOOK").isEmpty());
        assertTrue(
                repository.findByFeaturedTrueOrderBySkuAsc()
                        .isEmpty());
    }
}
```

There are **3 `@Test` methods**. None declare `@Sql` and all use the `test` profile; none expect data from a startup runner or another method. `CatalogTestObjects.simpleItem(...)` inserts a single row only in the method that needs it.

Because this sample project has no reference data, `repository.count() == 0` is valid here. **Do not copy that assertion verbatim into production apps with mandatory reference data**: query by namespace or test-owned SKUs instead of demanding an empty database.

### Why Doesn't the Third Test Depend on the Second?

`@DataJpaTest` is transactional by default and rolls back after each method. Thus `TEST-LOCAL` from the second method does not exist in the third. `findById("TEST-BOOK").isEmpty()` also proves fixtures declared on **another test class** never leak implicitly into this class.

## 13. CatalogFixtureSqlTest: Explicitly Declared Fixtures

`src/test/java/com/example/catalog/CatalogFixtureSqlTest.java`:

```java
package com.example.catalog;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.jdbc.Sql;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(showSql = false)
@ActiveProfiles("test")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY)
@Sql(
        scripts = "/fixtures/catalog-items.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
class CatalogFixtureSqlTest {

    @Autowired
    CatalogRepository repository;

    @Test
    void explicitFixtureContainsExactlyFourRows() {
        assertEquals(4L, repository.count());
        assertTrue(repository.existsById("TEST-BOOK"));
        assertTrue(repository.existsById("TEST-DISPLAY"));
        assertTrue(repository.existsById("TEST-CABLE"));
        assertTrue(repository.existsById("TEST-PEN"));
    }

    @Test
    void featuredQueryReturnsTwoRowsInSkuOrder() {
        List<String> skus = repository
                .findByFeaturedTrueOrderBySkuAsc()
                .stream()
                .map(CatalogItem::getSku)
                .toList();

        assertEquals(
                List.of("TEST-BOOK", "TEST-DISPLAY"),
                skus);
    }

    @Test
    void priceRangeUsesOnlyRelevantFixtures() {
        List<String> skus = repository
                .findByPriceCentsBetweenOrderBySkuAsc(
                        500, 2000)
                .stream()
                .map(CatalogItem::getSku)
                .toList();

        assertEquals(
                List.of("TEST-BOOK", "TEST-CABLE"),
                skus);
    }

    @Test
    void demoSeedNeverMixesWithTestFixture() {
        assertFalse(repository.existsById("DEV-CUP"));
        assertFalse(repository.existsById("DEV-BAG"));
        assertEquals(4L, repository.count());
    }

    @Test
    void methodMutationLivesOnlyInTestTransaction() {
        repository.saveAndFlush(new CatalogItem(
                "TEST-TEMP", "Temporary", 777, false));

        assertEquals(5L, repository.count());
        assertTrue(repository.existsById("TEST-TEMP"));
    }

    @Test
    void everyMethodHasTheSameExplicitBaseline() {
        assertEquals(4L, repository.count());
        assertFalse(repository.existsById("TEST-TEMP"));
        assertTrue(repository.findById("TEST-NOT-FOUND").isEmpty());
    }
}
```

There are **6 `@Test` methods**. The SQL fixture runs before each method (not just once for the class), the method exercises the repository, and the test transaction rolls back. Hence the four-row baseline is independent of JUnit execution order.

### Lifecycle of One Method

```text
BEGIN test-managed transaction
  |
  +-- @Sql BEFORE_TEST_METHOD
  |      INSERT TEST-BOOK / DISPLAY / CABLE / PEN
  |
  +-- @Test body
  |      SELECT / UPDATE / INSERT TEST-TEMP
  |
  +-- ROLLBACK (DataJpaTest default)
  |
next method: fresh BEGIN, @Sql re-inserts fixture
```

`methodMutationLivesOnlyInTestTransaction` verifies `TEST-TEMP` exists **within** that method. `everyMethodHasTheSameExplicitBaseline` verifies it begins with only the four fixture rows. Neither test requires a specific execution order: each builds its own baseline and rollback clears mutations.

If you remove `@Sql`, those query assertions fail or return no rows: that confirms setup is explicit rather than relying on a global `data.sql`.

### Class-Level vs. Method-Level @Sql

Class-level fits when every test in the class shares a concise fixture. Method-level fits when only one case needs specialized rows. When combining class-level and method-level `@Sql`, understand `@SqlMergeMode` and default override/merge semantics so tests do not accidentally load or drop scripts.

### When Does Rollback Not Happen?

If a test intentionally uses `@SqlConfig(transactionMode=ISOLATED)`, SQL setup commits in a separate transaction, so method rollback will not delete those rows. When tests are non-transactional, scripts also run/commit outside a test transaction. In those cases, add scoped teardown such as `@Sql(..., executionPhase=AFTER_TEST_METHOD)` or reset the database/container. Never apply a single rollback assumption across every framework annotation.

## 14. DevSeedProfileTest: Verifying the Real Dev Branch

To test an `ApplicationRunner` executing at application startup, you need the right context lifecycle. `@DataJpaTest` limits component scanning and skips general configurations/runners. Therefore, test dev seeding with `@SpringBootTest`:

`src/test/java/com/example/catalog/DevSeedProfileTest.java`:

```java
package com.example.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("dev")
class DevSeedProfileTest {

    @Autowired
    CatalogRepository repository;

    @Test
    void devProfileCreatesTwoDemoProducts() {
        assertTrue(repository.existsById("DEV-CUP"));
        assertTrue(repository.existsById("DEV-BAG"));
        assertEquals(2L, repository.count());
    }

    @Test
    void devProfileDoesNotLoadTestOnlyFixture() {
        assertFalse(repository.existsById("TEST-BOOK"));
        assertFalse(repository.existsById("TEST-CABLE"));
        assertEquals(2L, repository.count());
    }
}
```

There are **2 `@Test` methods**. With `dev` active, Spring creates `DevCatalogSeedConfig` and executes the `ApplicationRunner` after startup. Hibernate generates the H2 schema per `application-dev.yml` and the two `DEV-*` rows are inserted. The SQL fixture in `src/test/resources` does not auto-run because no `@Sql` is declared here and SQL init mode defaults to `never`.

**Suite total: 3 + 6 + 2 = 11 `@Test` methods.** These expectations come from inspecting the source code, not from an actual CI execution log.

### Why Not Annotate the Dev Test with @Transactional to “Delete the Seed”?

`ApplicationRunner` already ran **before test methods**. A transaction opened around a test method cannot roll back work already committed during startup. The dev-profile test intentionally only **reads** the two rows. If a test must mutate them, use a dedicated context/database with explicit cleanup or restoration.

## 15. Running Tests and Reading Reports Correctly

Run each class when a Gradle Wrapper is present:

```bash
./gradlew test --tests 'com.example.catalog.CatalogWithoutSeedTest'
./gradlew test --tests 'com.example.catalog.CatalogFixtureSqlTest'
./gradlew test --tests 'com.example.catalog.DevSeedProfileTest'
```

Run the full suite:

```bash
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

If no Wrapper exists yet but a compatible Gradle is installed:

```bash
gradle test
```

The report should show **11 test methods**. Inspect the real report in `build/reports/tests/test/index.html` and XML files in `build/test-results/test/` to confirm PASS/FAIL/SKIPPED; the sample code **was not executed with Gradle at authoring time**.

When testing slices without needing the full app, `@DataJpaTest` runs faster than `@SpringBootTest` because it boots only the JPA slice. Only `DevSeedProfileTest` needs full application startup to test `ApplicationRunner`.

## 16. Distinguishing @DataJpaTest Rollback from Real HTTP Requests

`@DataJpaTest` normally runs inside a **test-managed transaction**; `@Sql` and repository calls sharing that transaction roll back when the method finishes. However, in an HTTP test:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class HttpCatalogTest {
    // HTTP client runs on the test thread;
    // controller handles the request on a server thread.
}
```

this is an **architectural snippet** (no controller/client exists in the sample project). `@Transactional` on the **test thread** does not roll back writes handled by the server in its own transaction. If an HTTP request inserts and commits a row, rolling back the test method afterwards will not delete that row.

For real HTTP integration tests:

1. Use a dedicated test database, schema, or container.
2. Load fixtures visible to the server, never expecting uncommitted SQL on the test thread to be readable by the server.
3. Send requests and assert responses and persisted state.
4. Clean up by namespace or reset the database without wiping tables owned elsewhere.
5. If using `@SqlConfig(transactionMode=ISOLATED)` for committed setup, ensure matching teardown.
6. Never rely on test-thread `@Rollback` to undo background or async side effects.

Operations against Redis, Kafka, or MongoDB do not roll back with the test's JPA transaction either unless special transaction architecture exists; multi-store tests need dedicated cleanup/invalidation per store.

## 17. Reference Data with Flyway/Liquibase

The sample uses Hibernate `ddl-auto=create-drop` to create H2 schemas quickly **without** migrations. In real projects, schemas and mandatory reference data should be managed via versioned migrations.

### Flyway

Suppose production has:

```text
src/main/resources/db/migration/
  V1__create_catalog.sql
  V2__insert_required_status_codes.sql
```

Mandatory status codes are **reference data** and belong in integration tests running production migrations. Demo products belong in a dev-only directory or `@Profile("dev")` runner—never inside `V2__insert_required_status_codes.sql`.

A dev-only configuration might look like:

```properties
spring.flyway.locations=classpath:db/migration,classpath:dev/db/migration
```

This is an architectural snippet, **not part of the runnable project** since the sample has no Flyway dependency. Test-only migrations can live under `src/test/resources` or a dedicated test location; verify ordering, discovery, and packaging carefully.

### Liquibase

Similarly, a test changelog can include the production changelog and append test-only changesets; production must never point at the test changelog. When using contexts or labels, verify that active profiles enable the intended subset only.

### One Primary Schema Manager

Do not let Hibernate `create-drop`, `schema.sql`, and Flyway/Liquibase manage the same schema without explicit coordination. In production, migrations should own the schema, with Hibernate `validate` catching mismatches. In this lesson's H2 demo, Hibernate creates the tables and `@Sql` inserts fixture rows.

## 18. Using a Dev-Only SQL Initializer Instead of a Runner

An alternative—**never combined simultaneously with `DevCatalogSeedConfig` in the project above**—is placing a dev script in a dedicated folder and letting Boot's SQL initializer load it only under the `dev` profile:

```yaml
spring:
  sql:
    init:
      mode: always
      data-locations: classpath:/db/dev/demo-products.sql
  jpa:
    defer-datasource-initialization: true
    hibernate:
      ddl-auto: create-drop
```

This works only when `db/dev/demo-products.sql` **actually exists**, Hibernate creates the schema first, and Boot's SQL initializer seeds demo rows afterward. Place it in `application-dev.yml`, never default `application.yml`; storing it in a dev-only directory avoids the name `data.sql` auto-running in tests. Never use `create-drop` against a production `DataSource`.

If you already use Flyway/Liquibase, avoid mixing SQL initializer scripts and migrations on the same schema. Pick one approach aligned with your database strategy.

## 19. Why Is `@Profile("!prod")` Not Enough?

An error-prone seeding pattern:

```java
@Configuration
@Profile("!prod")
class UnsafeDemoSeed {
    // Runner writes demo products.
}
```

This is an **anti-pattern snippet** without a standalone runner implementation. `!prod` matches `test`, `staging`, `qa`, and any context where `prod` is inactive; the demo seed still runs whenever the config is scanned. That creates surprises and feeds integration tests unexpected rows.

Use `@Profile("dev")` or another explicit positive allowlist instead. When running multiple profiles simultaneously, if both `test` and `dev` are active, the dev loader **will still run**. Never enable `dev` in tests just to borrow H2 settings; provide a complete `application-test.yml` instead.

Profile guards are also not security boundaries: test jobs still need proper credentials and database isolation with zero write privileges against production DBs.

## 20. Deterministic Data and Clean Factories

Good test fixtures feature:

- Clear IDs: `TEST-BOOK` instead of unlogged random IDs.
- Intentional boundary values: `0`, min, max, just outside filter bounds.
- Explicit asserted fields, with valid defaults for everything else.
- Minimal row counts needed to distinguish success from failure.
- Fixed time whenever logic depends on the current instant.
- Zero real customer names, emails, or card numbers.
- Zero shared mutable global entity singletons edited across tests.

Fixed-clock snippet when production services inject `Clock`:

```java
Clock clock = Clock.fixed(
        Instant.parse("2026-01-15T10:00:00Z"),
        ZoneOffset.UTC);
```

Requires imports for `java.time.Clock`, `Instant`, and `ZoneOffset`. This is an extension snippet, not a project file. It avoids tests relying on `Instant.now()` and flaking near midnight or across timezones.

SQL fixtures work nicely for testing repository joins and constraints; factories suit unit/domain tests; test builders suit multi-field variations. Do not force every test into the same setup mechanism.

## 21. Test Pollution and Context Caching

**Test pollution** occurs when one test mutates state observed unexpectedly by another test. Warning signs:

- A test passes in isolation but fails in the full suite.
- Reordering test methods changes counts or outcomes.
- A SQL fixture triggers a duplicate primary-key error in the second test.
- A test without `@Sql` still sees `TEST-BOOK`.
- The `test` profile still sees `DEV-CUP`.
- A parallel CI job deletes data currently used by another job.
- `@SpringBootTest` context caching reuses a singleton bean holding mutable state.
- An async job writes to the DB after the test method rolls back.

**How to investigate:**

1. Confirm active profiles and test database/schema names (never log passwords).
2. Audit every seeding source: `data.sql`, `import.sql`, migrations, runners, listeners, external bootstraps.
3. Check class-level vs. method-level `@Sql` and transaction modes.
4. Check `@Transactional`, `@Commit`/`@Rollback(false)`, and real HTTP server threads.
5. Inspect Spring context caching and parallel execution settings.
6. Hunt down static mutable state in factories, caches, and services.
7. Restore per-test baselines and enforce rollback/cleanup at the right boundary.
8. Run both single methods and the full suite to confirm order independence.

Never “fix” pollution by adding `@Order` so Test A populates data for Test B; running Test B alone will immediately fail due to missing preconditions.

## 22. Properly Scoped Data Cleanup

### With @DataJpaTest

Transaction rollback is the cleanest choice when all DML and `@Sql` scripts share the test transaction. You do not need `repository.deleteAll()` in every test; broad deletes can even mask data-leak bugs.

### With @SpringBootTest and Committed Data

Startup runners, HTTP servers, and async jobs can commit outside the test-managed transaction. Use an isolated `DataSource`/test container and ownership-scoped cleanup. Use `AFTER_TEST_METHOD` SQL cleanup when transaction boundaries align, or reset the database/container.

`@AfterEach` normally runs even when assertions fail, but is **not guaranteed** if the JVM/process is killed. Per-suite isolated databases still protect shared environments.

### With Shared Databases

Never call `deleteAll()` or `TRUNCATE` on a database whose test ownership is unverified. If sharing an integration service is unavoidable, isolate by schema or tenant namespace with restricted privileges and delete only test-owned rows.

### With Parallel Execution

A fixed `TEST-BOOK` fixture is safe when each test runs in an isolated transaction or database, yet collides when multiple non-transactional suites write to the same database. Across parallel workers, use separate databases, containers, schemas, or unique per-suite namespaces. Never rely on ordered cleanup in a single global shared H2 instance.

## 23. H2 Tests Do Not Prove Production Migrations

H2 gives fast feedback for basic repository mappings and queries, but differs from PostgreSQL/MySQL in data types, SQL dialect, collations, locking, sequences, and transaction isolation. When behavior depends on the database vendor, run tests against **Testcontainers matching the production engine**, applying real schema migrations followed by test-only fixtures.

Never copy a production snapshot containing PII into a test repository; if production data shapes are needed, use synthetic or properly anonymized datasets per security policy.

### Migration and Fixture Order

```text
Testcontainers DB starts
     |
     +-- Apply production schema/reference migrations
     |
     +-- Apply test-specific setup (@Sql / test migrations)
     |
     +-- Execute repository/service test
     |
     +-- Roll back or reset test-owned state
```

When tests include production reference data, baselines are no longer zero rows across every table. Scope assertions to specific tables, tenants, or test SKUs rather than asserting `count() == 0` globally.

## 24. QA Checklist

- [ ] Are reference data, dev seeds, and test fixtures separated with clear owners?
- [ ] Does the dev seed use a positive `@Profile("dev")` guard?
- [ ] Is `@Profile("!prod")` avoided for demo data?
- [ ] Are root `data.sql`/`import.sql` controlled so they never auto-run unintentionally?
- [ ] Is it clear that `spring.sql.init.mode=never` only disables Boot's SQL initializer?
- [ ] Do test resources live in `src/test/resources` outside the production JAR?
- [ ] Are `application-test.yml` and `@ActiveProfiles("test")` configured properly?
- [ ] Is the embedded test `DataSource` isolated from dev and prod?
- [ ] Does `@Sql` load fixtures only where requested and in the right phase?
- [ ] Do SQL fixtures use minimal rows that distinguish branches?
- [ ] Do rollback-based tests avoid `@SqlConfig(transactionMode=ISOLATED)`?
- [ ] Are tests free of `@Order` and dependencies on prior methods?
- [ ] Do tests verify both the absence of `DEV-*` in `test` profile and presence in `dev` profile?
- [ ] Are full-context tests used when testing startup runners?
- [ ] Are test transactions distinguished from HTTP and async transactions?
- [ ] Is `deleteAll()` avoided on databases outside explicit test ownership?
- [ ] Are migrations and reference data verified against a production-compatible DB when needed?
- [ ] Are shared mutable fixture objects and nondeterministic time/randomness avoided?
- [ ] Are test datasets free of production credentials and PII?
- [ ] Were Gradle and the actual test report checked before claiming PASS?
- [ ] Do single methods and the full suite yield consistent results?

## 25. Reinforcement Exercises

1. Run `CatalogWithoutSeedTest`; explain why the demo runner does not run under the `test` profile.
2. Temporarily change `@Profile("dev")` to `@Profile("!prod")` in a sandbox and observe how a full-context test under `test` profile gets polluted.
3. Remove `@Sql` from `CatalogFixtureSqlTest` and explain why `TEST-BOOK` and `TEST-CABLE` disappear.
4. Move `@Sql` from class level to a single method and verify other methods do not see the fixture.
5. Add `TEST-HEADSET` to the SQL fixture and update the test assertion accordingly without modifying the demo seed.
6. Write a test with prices `0`, `500`, `2000`, and `2001` cents to verify inclusive range boundaries.
7. Experiment with `@SqlConfig(transactionMode=ISOLATED)` on an isolated test DB and design proper cleanup.
8. Create a reference table via a versioned Flyway migration and contrast it with test-only fixtures.
9. Write a `@SpringBootTest(RANDOM_PORT)` test with a web API and observe how test-thread rollback differs from server transactions.
10. Use the factory to persist a single item and verify JPA transaction rollback leaves no leaked row.
11. Run tests in randomized order or run a single method in isolation to confirm zero order dependence.
12. Compare `import.sql` vs. `data.sql` behavior under Hibernate `create-drop` in an H2 sandbox.
13. If using PostgreSQL in production, run repository queries against Testcontainers with production migrations.
14. Inspect the Gradle test report to verify all 11 `@Test` methods actually executed.
15. Audit fixtures to ensure zero customer PII or secrets exist.
16. Run CI in parallel with isolated databases/schemas and document how fixture conflicts are prevented.

## 26. Official References

- [Spring Boot 3.3 — Database Initialization](https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html): `data.sql`/`schema.sql`, `spring.sql.init.mode`, Hibernate `import.sql`, SQL init ordering, Flyway/Liquibase.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@DataJpaTest`, test databases and transaction rollback, `@SpringBootTest`.
- [Spring Framework — Executing SQL Scripts with @Sql](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): `@Sql`, execution phases, and `@SqlConfig`.
- [Spring Framework — Transactional Test Execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transactions and rollback.
- [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html): `@Profile` and profile-specific configuration.
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): YAML properties and configuration sources.
- [Spring Data JPA — Repositories](https://docs.spring.io/spring-data/jpa/reference/repositories.html): derived query methods and JPA repository behavior.
- [Testcontainers for Java](https://java.testcontainers.org/): database integration tests against the real vendor engine.
- [JUnit Jupiter — User Guide](https://junit.org/junit5/docs/current/user-guide/): test lifecycle and independence.

## 27. Conclusion

**Never let a global demo database dictate the outcome of repository tests.** Mandatory reference data belongs in migrations and contracts; demo seeds require an explicit `dev` profile; test fixtures belong to scenario tests and are loaded via `@Sql` or Java factories in test sources.

`spring.sql.init.mode=never` stops Spring Boot from auto-running `data.sql`, though it is no substitute for guarding Hibernate `import.sql`, migrations, or `ApplicationRunner` beans. With Spring Boot 3.3, `@ActiveProfiles("test")`, embedded H2, `@DataJpaTest` rollback, and per-test `@Sql` create a concise, clear, and reproducible test setup. When moving to HTTP servers, async work, or multiple storage backends, establish explicit transaction and cleanup boundaries instead of assuming every write rolls back automatically.

This example demonstrates both sides: the `test` profile **has zero `DEV-*` rows** and the `dev` profile **has exact demo rows**, while repository query tests use four dedicated `TEST-*` fixtures. As a result, editing demo content never breaks business tests, and whenever a test fails, you can trace it straight to the exact fixture, transaction, or query at fault.
