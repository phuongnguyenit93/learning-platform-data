# Spring Data JPA: Embedded Databases, Real Databases, and @AutoConfigureTestDatabase

## 1. The Key Question: Which Database Is the Repository Test Actually Using?

A Spring Data JPA repository test can persist an entity, query it back, and pass on H2. Yet that same SQL query may fail on PostgreSQL or MySQL due to differences in SQL dialect, data types, collation, constraints, transactions, indexes, and migrations. Conversely, not every entity mapping check justifies the cost of booting PostgreSQL.

Two complementary strategies:

- **Embedded database** (such as in-memory H2) for many simple JPA mapping and repository tests: fast, minimal infrastructure, easy fixture setup.
- **Real database with the production engine** (such as PostgreSQL running in Testcontainers) for native SQL, constraints, schema migrations, locking, isolation, indexing, or vendor-specific behaviors.

There is an important trap: with `@DataJpaTest`, Spring Boot can **replace the application's DataSource** with an embedded database. So even if a test configures a PostgreSQL container, it might still query H2 if the replacement rule is wrong.

**Version matters:** In Spring Boot **3.3**, `@AutoConfigureTestDatabase` defaults to `replace = Replace.ANY`; starting in **3.4**, `Replace.NON_TEST` was added and became the default to better detect datasources provided by test containers. This guide uses Java 17 and Spring Boot 3.3, then explains the differences when upgrading versions.

## 2. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **embedded**, **in-memory**, **file-backed**, **real database server**, and **production database**.
2. Understand the scope of `@DataJpaTest`, repository/entity scanning, `TestEntityManager`, and default transaction rollback.
3. Explain what `@AutoConfigureTestDatabase` does, Boot 3.3's three `Replace.ANY`, `AUTO_CONFIGURED`, `NONE` values, and the `connection` parameter.
4. Verify the datasource using `DatabaseMetaData` instead of guessing the engine from a URL or test name.
5. Write H2 tests and PostgreSQL Testcontainers tests covering the same repository.
6. Use `@ServiceConnection`/`@DynamicPropertySource` appropriately, without letting a container datasource accidentally be replaced by H2.
7. Distinguish `save`, `flush`, `clear`, commit, rollback, and data created by migrations/startup tasks.
8. Explain the limitations of using H2 in place of PostgreSQL for native SQL, JSONB, unique constraints, collations, transaction isolation, and locking.
9. Safely manage Docker-dependent tests, test profiles, context caching, data isolation, and sensitive data.
10. Pick the smallest test scope sufficient to catch the bug: unit, JPA slice, real-DB JPA test, or full application integration.

## 3. Embedded Does Not Mean In-Memory, and Real Does Not Mean Production

| Database Type | Example | Characteristics |
| --- | --- | --- |
| Embedded in-memory | `jdbc:h2:mem:catalog` | H2 runs inside the JVM; data follows connection/DB lifecycle |
| Embedded file-backed | `jdbc:h2:file:./sandbox/catalog` | H2 inside the JVM but persisted to files; requires cleanup |
| Dedicated database server in container | PostgreSQL `postgres:16-alpine` via Testcontainers | Real engine/server and JDBC protocol, ephemerally managed |
| Shared test database server | Staging/test PostgreSQL instance | Real engine, but prone to shared state and migration conflicts |
| Production database | DB serving live users | **Never use** as a target for automated tests that write data |

H2/HSQLDB/Derby all have embedded modes. An H2 database can run in memory or on disk; `in-memory` describes where data is stored, whereas `embedded` describes how the engine is hosted, so the two terms are not strictly synonymous.

Testcontainers PostgreSQL **is not embedded**. It starts a PostgreSQL server inside a container and uses the real driver/protocol. This brings you closer to the production engine without sharing production data.

**Do not use H2 `MODE=PostgreSQL` as proof that “it was tested on PostgreSQL”.** Compatibility mode only emulates a subset of SQL; it does not cover full MVCC, JSONB, extensions, collations, locking, or PostgreSQL transaction behavior.

## 4. What Scope Does `@DataJpaTest` Select?

Spring Boot `@DataJpaTest` is a **test slice**. In Boot 3.3, according to the official documentation, it:

- Loads entities and Spring Data JPA repositories.
- Configures JPA/Hibernate, the transaction manager, and appropriate test database auto-configuration.
- Can spin up an embedded database when a driver is available.
- Provides `TestEntityManager` for persist/flush/clear operations in tests.
- Runs tests in a transaction by default, **rolling back at the end of the method**.
- Enables show-SQL by default; `@DataJpaTest(showSql = false)` can reduce log noise.
- Does not scan ordinary `@Service`/`@Controller` beans like a full Spring Boot application context.

```java
@DataJpaTest
class RepositoryTest {
    @Autowired
    ProductRepository repository;

    @Autowired
    TestEntityManager entityManager;
}
```

The snippet above is just a template; runnable classes are in section 9.

**Test slice goal:** verify persistence behavior, not HTTP mapping, controller-service integration, schedulers, message brokers, or network communication. If you need a real service that depends on a repository, you can `@Import` that small service into the JPA slice; if you want the full HTTP flow, consider `@SpringBootTest`.

### 4.1. Why Does Rollback Not Create a Fresh Database per Method?

Spring TestContext caches `ApplicationContext` by configuration. The H2 datasource and EntityManagerFactory may be reused across multiple methods. Test-managed transaction rollback normally prevents each test from leaving behind uncommitted rows, **not because Boot recreates the database before every `@Test`**.

Effects running outside the test transaction (migrations, startup jobs, code opening `REQUIRES_NEW`, or another thread) are not necessarily rolled back per method.

## 5. What Does `@AutoConfigureTestDatabase` Actually Control?

In Spring Boot 3.3:

```java
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
```

This annotation controls **whether to replace the DataSource** with an embedded test datasource (if replacement is performed) and selects the embedded database type. It does not create a PostgreSQL server or guarantee schema/migrations.

### 5.1. Three `Replace` Modes in Boot 3.3

| Value | Behavior |
| --- | --- |
| `Replace.ANY` | Replaces the DataSource whether it was auto-configured by Boot or manually defined by the user |
| `Replace.AUTO_CONFIGURED` | Replaces only a DataSource auto-configured by Boot |
| `Replace.NONE` | Does not replace the current DataSource with an embedded test database |

**Boot 3.3 defaults to `ANY`**, per the official Javadoc; do not confuse it with the `NON_TEST` default introduced in 3.4.

```java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.ANY
)
class EmbeddedRepositoryTest { }
```

The example above expresses “use an embedded datasource if possible”, without specifying whether the engine is H2 or PostgreSQL. It requires an actual embedded driver on the classpath.

### 5.2. Explicitly Selecting H2 with `connection`

```java
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY,
        connection = EmbeddedDatabaseConnection.H2
)
class H2RepositoryTest { }
```

Additional import:

```java
import org.springframework.boot.jdbc.EmbeddedDatabaseConnection;
```

`connection = H2` specifies the embedded database when replacement occurs. If `replace = NONE`, adding `connection=H2` **is not** an instruction to start H2. Furthermore, the classpath must contain the H2 JDBC driver.

### 5.3. What Counts as an “Auto-Configured” DataSource?

In many Spring Boot apps, `DataSourceAutoConfiguration` uses `spring.datasource.*`, a driver, and HikariCP to create the DataSource. That is what `AUTO_CONFIGURED` can replace.

If the application defines a manual `@Bean DataSource`, `AUTO_CONFIGURED` does not intend to replace that bean; `ANY` can replace it. `NONE` keeps the DataSource intact — even if it accidentally points to a dangerous database.

### 5.4. When the Application Has Multiple DataSources

Boot 3.3 Javadoc states that when multiple `DataSource` beans exist, test replacement considers only the **`@Primary` DataSource**. Secondary datasources, routing datasources, or multiple persistence units must be tested and protected separately.

Never infer that a single `@AutoConfigureTestDatabase` on a test class stops the entire application from connecting to external databases. Verify the URL, profile, and credentials for **each** DataSource.

## 6. Rules by Version: Boot 3.3, 3.4, and 4.x

| Version | `Replace` Modes | Default | Testcontainers |
| --- | --- | --- | --- |
| 3.3.x | `ANY`, `AUTO_CONFIGURED`, `NONE` | `ANY` | Must specify `replace=NONE` explicitly to preserve the container datasource |
| 3.4–3.5 | Adds `NON_TEST` | `NON_TEST` | Attempts to recognize test datasources from `@ServiceConnection`, `@DynamicPropertySource`, Testcontainers JDBC URLs |
| 4.x | Corresponding modes, though test packages changed | `NON_TEST` in current lines | Check test modules and imports for the exact version |

`Replace.NON_TEST` was added in **Boot 3.4.0**. It avoids replacing an auto-configured DataSource recognized as a **test database**. Connections with container metadata (`@ServiceConnection`), URLs supplied by `@DynamicPropertySource`, and Testcontainers-style JDBC URLs fall under recognized cases.

**However, `NON_TEST` is not an absolute safety barrier distinguishing production from staging.** Never give tests credentials or network access to production. When targeting a specific test PostgreSQL instance, `replace=NONE` still states the intent clearly, provided you verify that datasource is test-only.

In **Spring Boot 4**, test annotations moved to feature-specific modules/packages; do not copy imports from Boot 3.3 examples without checking the migration guide.

## 7. Choosing H2 or a Vendor Database by Business Question

| What the Test Needs to Prove | What to Choose | Why? |
| --- | --- | --- |
| Entity persists and derived query works? | `@DataJpaTest` + H2 | Lightweight, fast feedback |
| Basic `@Column`/association mapping? | H2 first, vendor test for dialect-sensitive cases | Covers basic bugs at low cost |
| `@Query(nativeQuery=true)` using PostgreSQL JSONB/arrays? | PostgreSQL Testcontainers | H2 is not the PostgreSQL engine |
| Production-like unique/index and collation? | Matching vendor/config database | H2 has different semantics |
| Transaction isolation and pessimistic locking? | Vendor DB and multiple transactions | Engine/concurrency behavior is what needs proof |
| Flyway/Liquibase migrations run on PostgreSQL? | Container DB + real migrations | Hibernate `create-drop` does not test scripts |
| Service coordinating repository without web? | JPA slice + `@Import` small service or service integration test | No embedded HTTP needed |
| Controller + service + DB over real HTTP? | Full Boot context + test DB | JPA slice does not cover HTTP |
| Pure pricing calculation algorithm? | JUnit unit test | No database needed |

H2 is not “bad”, and a PostgreSQL container is not unconditionally “good”. The goal is **the right evidence at the right cost**.

## 8. Runnable Java 17 and Spring Boot 3.3.0 Project

The same entity/repository will be tested by:

1. **H2 tests:** run without Docker; prove basic mapper/repository behavior and unique constraints.
2. **PostgreSQL Testcontainers tests:** enabled only when `RUN_PG_TESTS=true` and the machine has Docker/a compatible runtime; prove the engine is genuinely PostgreSQL.

The project uses **Spring Boot 3.3.0** for consistent imports. This is a technical demonstration, not a recommendation to run an old release in production. There is no production database or network access beyond Testcontainers.

### 8.1. File Structure

```text
jpa-database-choice/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/catalog/
    │   ├── CatalogApplication.java
    │   ├── CatalogProduct.java
    │   └── CatalogProductRepository.java
    └── test/java/example/catalog/
        ├── CatalogRepositoryH2Test.java
        └── CatalogRepositoryPostgresTest.java
```

### 8.2. Gradle Settings

**`settings.gradle`:**

```groovy
rootProject.name = 'jpa-database-choice'
```

### 8.3. Gradle Build

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'

    testRuntimeOnly 'com.h2database:h2'
    testRuntimeOnly 'org.postgresql:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Boot dependency management provides aligned versions for JPA/Hibernate/JUnit/Testcontainers/JDBC drivers. The H2 and PostgreSQL drivers are only on the **test runtime classpath**, avoiding production database connections with default credentials.

For a test-only project like this example, this is sufficient. If you want to run `bootRun` outside tests, declare a runtime driver and separate datasource; do not assume the example is a complete production deployment.

### 8.4. Spring Boot Application

**`src/main/java/example/catalog/CatalogApplication.java`:**

```java
package example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

Placing the application in package `example.catalog` lets classes and tests in the same package discover the primary configuration. `@DataJpaTest` applies JPA slice filters instead of loading full application services like `@SpringBootTest`.

### 8.5. Entity with Primary Key and Unique SKU

**`src/main/java/example/catalog/CatalogProduct.java`:**

```java
package example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
        name = "catalog_products",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_catalog_product_sku",
                columnNames = "sku")
)
public class CatalogProduct {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 64)
    private String sku;

    @Column(nullable = false, length = 150)
    private String displayName;

    @Column(nullable = false)
    private long priceCents;

    protected CatalogProduct() {
        // Required by JPA.
    }

    public CatalogProduct(
            String sku,
            String displayName,
            long priceCents) {
        this.sku = sku;
        this.displayName = displayName;
        this.priceCents = priceCents;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getDisplayName() {
        return displayName;
    }

    public long getPriceCents() {
        return priceCents;
    }
}
```

`jakarta.persistence` matches Spring Boot 3.x; do not use `javax.persistence` from Boot 2.x. `UniqueConstraint` is translated into DDL by Hibernate when tests use `create-drop`. `IDENTITY` works with H2/PostgreSQL in this demo but differs in sequence/identity behavior across other databases.

**Do not treat `long` as a guarantee that price is positive**: `@Column(nullable=false)` only states the value is non-null (a primitive is already non-null); there is no business validation `priceCents > 0`. If that invariant is required, add explicit validation/check constraints and test them separately.

### 8.6. Spring Data Repository

**`src/main/java/example/catalog/CatalogProductRepository.java`:**

```java
package example.catalog;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CatalogProductRepository
        extends JpaRepository<CatalogProduct, Long> {
    Optional<CatalogProduct> findBySku(String sku);
}
```

Spring Data JPA supplies the implementation of `findBySku` from the entity property name. Tests execute SQL through the repository proxy rather than mocking it.

## 9. Test A: Running with H2, No Docker Needed

**`src/test/java/example/catalog/CatalogRepositoryH2Test.java`:**

```java
package example.catalog;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.jdbc.EmbeddedDatabaseConnection;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.dao.DataIntegrityViolationException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@DataJpaTest(properties =
        "spring.jpa.hibernate.ddl-auto=create-drop")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY,
        connection = EmbeddedDatabaseConnection.H2
)
class CatalogRepositoryH2Test {
    @Autowired
    CatalogProductRepository repository;

    @Autowired
    TestEntityManager entityManager;

    @Autowired
    DataSource dataSource;

    @Test
    void reallyUsesH2() throws SQLException {
        try (Connection connection =
                     dataSource.getConnection()) {
            assertEquals("H2",
                    connection.getMetaData()
                            .getDatabaseProductName());
        }
    }

    @Test
    void savesFlushesAndReloadsAnEntity() {
        CatalogProduct saved = repository.saveAndFlush(
                new CatalogProduct(
                        "SKU-H2-10", "Green Tea", 12500L));

        assertNotNull(saved.getId());

        entityManager.clear();

        CatalogProduct reloaded = repository
                .findBySku("SKU-H2-10")
                .orElseThrow();

        assertEquals(saved.getId(), reloaded.getId());
        assertEquals("Green Tea",
                reloaded.getDisplayName());
        assertEquals(12500L, reloaded.getPriceCents());
    }

    @Test
    void rejectsSameSkuAtDatabaseConstraint() {
        repository.saveAndFlush(
                new CatalogProduct(
                        "SKU-H2-20", "Sample A", 1000L));

        entityManager.clear();

        assertThrows(DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(
                        new CatalogProduct(
                                "SKU-H2-20", "Sample B", 2000L)));
    }
}
```

### 9.1. Why Assert the Database Vendor?

The annotation `@AutoConfigureTestDatabase(connection=H2)` states the intended configuration, whereas `Connection.getMetaData().getDatabaseProductName()` actually checks whether **the JDBC connection in use** reports H2. This catches situations where the datasource was unintentionally replaced.

For the PostgreSQL test, we will assert `"PostgreSQL"`, preventing tests from **passing on H2 by mistake**.

### 9.2. Why `saveAndFlush` Then `clear`?

- `save` puts the entity into the persistence context; SQL writes may occur on flush/commit (with IDENTITY inserts may occur early to obtain the ID).
- `saveAndFlush` requests flushing pending changes to the database in the current transaction.
- `entityManager.clear()` removes managed entities from the first-level cache without **deleting database rows**.
- `findBySku` after `clear` verifies that the repository query re-fetches the data.

This is stronger evidence than `assertNotNull(repository)` or asserting only on the object returned by `save`.

### 9.3. Unique Constraints and Transactions After Failure

If you call `repository.save(duplicate)` and immediately wrap it in `assertThrows`, the exception might **not yet occur at that moment** if SQL has not flushed. `saveAndFlush` pins the exact moment the database checks the constraint.

After PostgreSQL/Hibernate detects a constraint violation, the transaction can enter a rollback-only/aborted state. Therefore, in negative tests, **do not run further queries in the same transaction after the exception**; let the test end and let the framework roll back.

**Do not assert raw SQL error message strings** because they depend on database version/driver; `DataIntegrityViolationException` or observable invariants are much more durable.

## 10. Test B: Real PostgreSQL via Testcontainers (Runs Only When Enabled)

In a Boot 3.3 project with the H2 test driver on the classpath, using Testcontainers requires **preventing the PostgreSQL DataSource from being replaced by H2**. Therefore, set `replace=NONE` explicitly.

**`src/test/java/example/catalog/CatalogRepositoryPostgresTest.java`:**

```java
package example.catalog;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@EnabledIfEnvironmentVariable(
        named = "RUN_PG_TESTS",
        matches = "true"
)
@Testcontainers
@DataJpaTest(properties =
        "spring.jpa.hibernate.ddl-auto=create-drop")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class CatalogRepositoryPostgresTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    CatalogProductRepository repository;

    @Autowired
    DataSource dataSource;

    @Test
    void connectsToPostgreSQLAndPersistsEntity()
            throws SQLException {
        try (Connection connection =
                     dataSource.getConnection()) {
            assertEquals("PostgreSQL",
                    connection.getMetaData()
                            .getDatabaseProductName());
        }

        CatalogProduct saved = repository.saveAndFlush(
                new CatalogProduct(
                        "SKU-PG-10", "Coffee", 35000L));

        assertNotNull(saved.getId());

        CatalogProduct reloaded = repository
                .findBySku("SKU-PG-10")
                .orElseThrow();

        assertEquals("Coffee",
                reloaded.getDisplayName());
        assertEquals(35000L, reloaded.getPriceCents());
    }

    @Test
    void postgresReallyEnforcesUniqueKey() {
        repository.saveAndFlush(
                new CatalogProduct(
                        "SKU-PG-20", "Sample A", 1000L));

        assertThrows(DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(
                        new CatalogProduct(
                                "SKU-PG-20", "Sample B", 2000L)));
    }
}
```

### 10.1. Meaning of Each Annotation

- `@EnabledIfEnvironmentVariable(named="RUN_PG_TESTS", matches="true")`: runs the class only when the environment variable is enabled. **Skipped** by default, so `./gradlew test` on a machine without Docker still runs H2 tests.
- `@Testcontainers`: activates the Testcontainers JUnit Jupiter extension.
- `@Container`: manages the PostgreSQL test container lifecycle.
- `@ServiceConnection`: instructs Spring Boot to create connection details from the typed container; requires `spring-boot-testcontainers`.
- `@DataJpaTest`: loads only the JPA slice, without a full Boot context.
- `@AutoConfigureTestDatabase(replace=NONE)`: preserves the container datasource, critical under Boot 3.3's `ANY` default.
- `ddl-auto=create-drop`: auto-generates schema for the demo. When testing real migrations, do not use this as evidence of Flyway/Liquibase.
- Metadata assertion: proves connection to the `PostgreSQL` engine, not merely having the PostgreSQL driver in the build.

### 10.2. Which Tests Require Docker?

**Only** `CatalogRepositoryPostgresTest` when `RUN_PG_TESTS=true`. H2 tests run independently and never start a container. In CI, you can separate a fast test stage (H2) and a database integration stage (PostgreSQL).

However, “skipped” does not mean “PostgreSQL passed”. Reports must distinguish **unexecuted tests** from **executed and passing tests**.

### 10.3. JPA Slice Can Still Use a Real Database

You do not need `@SpringBootTest` just to run Testcontainers. Choosing the **database engine** and choosing the **Spring context width** are two orthogonal decisions:

| Scope | H2 | PostgreSQL |
| --- | --- | --- |
| `@DataJpaTest` | Yes | Yes |
| `@SpringBootTest` | Yes | Yes |

If you need controller-service-repository end-to-end verification, pick a full Boot context; if you only need repository queries/constraints, a JPA slice with PostgreSQL is completely appropriate.

## 11. Run Commands and Expected Results

Assuming JDK 17, a compatible Gradle Wrapper (e.g., Gradle 8.5), and downloadable dependencies:

### 11.1. Without Docker

Linux/macOS:

```bash
./gradlew test
./gradlew test --tests example.catalog.CatalogRepositoryH2Test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.catalog.CatalogRepositoryH2Test
```

Expect **3 H2 test methods to pass**. The PostgreSQL test class is skipped if `RUN_PG_TESTS` is absent or not `true`.

### 11.2. With Docker, Enabling PostgreSQL

Linux/macOS:

```bash
RUN_PG_TESTS=true ./gradlew test --tests example.catalog.CatalogRepositoryPostgresTest
RUN_PG_TESTS=true ./gradlew test
```

Windows PowerShell:

```powershell
$env:RUN_PG_TESTS = 'true'
.\gradlew.bat test --tests example.catalog.CatalogRepositoryPostgresTest
Remove-Item Env:RUN_PG_TESTS
```

Expect **2 PostgreSQL test methods to pass** when selecting only the Postgres class, or **5 methods total passing** when running the full suite with the env var enabled. There is no fixed business stdout; Gradle typically reports `BUILD SUCCESSFUL` when all tasks succeed.

These outcomes are **expected based on the code and configuration**, not claims of having run Docker in the author's environment. A Docker environment with the PostgreSQL image is needed to confirm.

### 11.3. Checking Image/Engine Version

The example uses `postgres:16-alpine`, not `postgres:latest`. When production uses PostgreSQL 15 or 17, tests should match the major/minor/extension setup or an approved compatibility set. For strict reproducibility, pin the image digest and use a registry mirror.

## 12. `@DynamicPropertySource`: Another Way to Connect

Besides `@ServiceConnection` (Boot 3.1+), Spring TestContext offers `@DynamicPropertySource`. When using this alternative, omit `@ServiceConnection` on the same container and register dynamic JDBC properties:

```java
@Container
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

@DynamicPropertySource
static void postgresProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url",
            postgres::getJdbcUrl);
    registry.add("spring.datasource.username",
            postgres::getUsername);
    registry.add("spring.datasource.password",
            postgres::getPassword);
}
```

This is an **alternative snippet**, requiring `@Testcontainers` on the class, `DynamicPropertySource`/`DynamicPropertyRegistry` imports, and Testcontainers imports. Do not copy it into the class above alongside `@ServiceConnection` without clear reason.

In **Boot 3.3**, even when JDBC properties come from a container, `@DataJpaTest` can still replace the datasource under the `ANY` default. Therefore keep `@AutoConfigureTestDatabase(replace=NONE)`.

From Boot 3.4 onward, the `NON_TEST` default detects databases from dynamic properties/containers better. Still, when a test must hit a specific database, explicit configuration and vendor assertions remain valuable.

### 12.1. Static Containers and Spring Context Cache Have Different Lifecycles

A static `@Container` typically follows the JUnit test class lifecycle, whereas Spring TestContext can cache `ApplicationContext`. In a suite with multiple classes sharing a context, a datasource could point to a stopped container if lifecycles are designed inconsistently.

The example here has only one PostgreSQL test class, keeping lifecycles simple. In larger suites, consider Spring Boot-managed container beans or a singleton container lifecycle aligned with caching. Do not share static mutable containers across dozens of tests while relying on accidental execution order.

## 13. What Bugs Can H2 Hide?

### 13.1. Native Queries/Dialect

H2 compatibility mode is not PostgreSQL. Features requiring vendor tests include:

- PostgreSQL `jsonb`/JSON operators, arrays, and extensions.
- `ON CONFLICT`, `RETURNING`, native casts, and SQL functions.
- Expression/partial indexes, collations, and case-insensitive uniqueness.
- Vendor-specific window functions/CTEs/locking behavior.
- Query planner/index statistics and performance.
- PostgreSQL error codes and transaction abortion semantics.

A repository method using only Spring Data's derived `findBySku` might pass on both H2 and PostgreSQL. That does not prove a `@Query(nativeQuery=true)` using `jsonb` will work.

### 13.2. Constraints and Collation

`UNIQUE(sku)` on H2 does not automatically prove case-insensitive uniqueness on PostgreSQL with a specific collation/index. If a business rule treats `sku-1` and `SKU-1` as duplicates, design a meaningful index/normalization and test on the production engine.

In the demo, we only check **the exact same SKU string** to avoid over-extrapolating requirements.

### 13.3. Identity/Sequence Behavior

`@GeneratedValue(IDENTITY)` or `SEQUENCE` may generate different SQL across vendors. Sequence counters can advance even when a transaction rolls back, so never assert “the first ID is always 1”. Assert `getId() != null` and reload by business key.

### 13.4. Transaction Isolation/Locking

H2 and PostgreSQL differ in MVCC, lock modes, deadlock detection, and isolation. A test in a single transaction does not prove two competing requests update correctly.

When using `@Version`, `@Lock(PESSIMISTIC_WRITE)`, or specific transaction isolation, tests require **multiple connections/transactions** on the real engine. Do not use arbitrary `Thread.sleep` calls to handle races; coordinate concurrency with barriers/latches with timeouts and assert invariants.

### 13.5. Timezones and Monetary Amounts

Timestamp/offset types, `BigDecimal` precision/scale, and database rounding can differ. For money, use minor units or `BigDecimal` with schema constraints/scale. Test on the vendor DB when numeric/timezone conversions affect business logic.

## 14. `save`, `flush`, `clear`, `commit`, and `rollback`

| Action | What It Does | What It Does **Not** Guarantee |
| --- | --- | --- |
| `repository.save(...)` | Makes entity managed/schedules persist | Committed |
| `flush()` | Synchronizes pending changes to DB in current transaction | Committed |
| `entityManager.clear()` | Removes entities from first-level cache | Deletes DB data |
| `commit` | Completes transaction and publishes changes | Other transactions will roll back too |
| `rollback` | Discards changes in that transaction | Undoes data committed by other transactions |

Default `@DataJpaTest` flow:

```text
Spring Test opens test-managed transaction
   |
   +--> repository.saveAndFlush(...)
   +--> entityManager.clear()
   +--> repository.findBySku(...)
   +--> assert data / constraints
   |
   +--> rollback after @Test
```

**Why is `clear()` useful?** Without it, EntityManager can return a managed entity already present in the persistence context, leaving the test short of proving the data was reloaded via query. `clear()` reduces false confidence (though second-level/custom caches, if enabled, must be considered separately).

### 14.1. Committed Data Needs a Different Style of Test

If the goal is data **visible to another transaction after commit**, default `@DataJpaTest` rollback does not prove it. You can use `TestTransaction` to control the test-managed transaction:

```java
repository.saveAndFlush(
        new CatalogProduct("SKU-COMMIT", "Sample", 100L));

TestTransaction.flagForCommit();
TestTransaction.end();

// Test-managed transaction has ended.
// From here on, explicit cleanup or an ephemeral test DB is needed.
assertTrue(repository.findBySku("SKU-COMMIT").isPresent());
```

This is an **advanced pattern**, not a method in the runnable demo. Using it requires importing `org.springframework.test.context.transaction.TestTransaction`, `assertTrue`, and a test running inside a test-managed transaction; do not add it carelessly to an ordinary H2 suite because the data will commit.

With `@SpringBootTest(RANDOM_PORT)` running a real HTTP server, server requests execute in a separate transaction from the test thread. `@Transactional` on the test method does not automatically roll back writes committed by the server.

## 15. Schema: `ddl-auto=create-drop` Is Not a Migration Test

The example set intentionally uses:

```properties
spring.jpa.hibernate.ddl-auto=create-drop
```

so H2 and PostgreSQL test DBs get a schema from entities **without requiring migration scripts**. This is a convenient choice for demonstrating persistence mapping.

In a production-like project:

- Use Flyway/Liquibase with real SQL migrations.
- Run migrations on a test database of the same vendor.
- Set `spring.jpa.hibernate.ddl-auto=validate` or `none` per policy so Hibernate does not alter the migrated schema.
- Verify the constraints/indexes/extensions/DB enum types the application expects.
- Never turn on `create-drop` against a datasource with data you need to keep; it can destroy the schema.

If an H2 test creates its schema solely via Hibernate, that test **does not prove** a PostgreSQL Flyway SQL migration runs cleanly.

### 15.1. `schema.sql`, `data.sql`, and `@Sql`

Spring Boot offers SQL initialization and Spring Test offers `@Sql`, but ordering relative to JPA DDL/migrations depends on configuration:

- `schema.sql`/`data.sql`: startup scripts if enabled per Boot config.
- `Flyway`/`Liquibase`: migration lifecycle.
- Hibernate `ddl-auto`: may create/validate/drop schema.
- `@Sql`: scripts tied to test lifecycle, typically before or after a test method.

**Do not enable all of them at once and assume the schema will work out.** Pick one primary schema source, verify the exact ordering, and test migrations on the vendor DB if production uses migrations.

`@Sql` running before a test method **has not necessarily run before application context startup runners**. If startup code requires fixtures, prepare them before context bootstrap.

## 16. Rollback Does Not Undo Every Side Effect

Certain things can outlive the test-managed transaction:

- Sequence/identity counters.
- Data committed by `Propagation.REQUIRES_NEW` or another thread.
- Startup seed jobs and migrations executed before the test method.
- Events/emails/HTTP calls emitted by services.
- File writes or caches external to the database.
- Data committed from an HTTP server thread in a live integration test.

Therefore tests should not rely on `@DirtiesContext` for “cleanup”. That annotation only evicts the context from the cache; it does not roll back commits or delete external data.

When testing committed side effects, use an isolated database/schema, unique test keys, and targeted record cleanup. Never call `repository.deleteAll()` on a shared database without explicit permission and intent.

## 17. When Multiple DataSources or Persistence Units Exist

Complex applications may have:

- `ordersDataSource` (primary).
- `analyticsDataSource`.
- Multiple `EntityManagerFactory` beans.
- Multiple transaction managers.
- Tenant-based routing datasources.

`@AutoConfigureTestDatabase` Javadoc states it only considers the **primary datasource** when multiple DataSources exist. It does not mean it will safely replace every source. `@DataJpaTest` defaults fit a standard single JPA configuration; custom persistence units need explicit test configuration.

Checklist:

1. Identify which EntityManagerFactory owns each repository.
2. Identify the datasource URL/driver/test credentials for each unit.
3. Ensure no secondary datasource points to production.
4. Enable replacement or supply an explicit test connection per unit.
5. Assert the exact vendor/DB name when required.
6. Keep state isolated and roll back/clean up per transaction manager.

## 18. Ensuring Safety When Using `Replace.NONE`

**`Replace.NONE` does not mean “use only a PostgreSQL test database”.** It means “do not replace the current datasource”. If a test mistakenly loads production configuration, you could execute INSERT/DELETE/`create-drop` on an unauthorized database.

Put guardrails in place:

- Never supply production credentials to CI test workflows.
- Use ephemeral containers or test-only servers.
- Where possible, restrict network access so test jobs cannot reach production DBs.
- Assert the vendor and allowed environment/schema/database name.
- Keep `ddl-auto=create-drop` strictly to demos/ephemeral DBs.
- Use a limited-privilege test role, not a production superuser.
- Avoid logging JDBC URLs if they contain secrets; never log passwords.
- Testing personal data: use synthetic fixtures, never copy production records.
- With multiple datasources, audit every connection.
- If Docker is missing, let tests skip or fail explicitly; **never** silently fall back to staging/production.

`PostgreSQL` metadata only confirms the vendor; it does not prove the target server is a test container. Combine connection details, safe environment rules, and network isolation.

## 19. Spring TestContext Cache and Container Lifecycle

Spring TestContext caches contexts by configuration classes, profiles, inline properties, context customizers, bean overrides, and loaders. H2 tests and PostgreSQL tests have different settings and therefore usually get separate cache keys.

Notes:

- Context caching can reuse an H2 datasource across test methods.
- Default rollback does not reset identity counters.
- A static `@Container` follows the JUnit class lifecycle; the Spring context cache has its own lifecycle.
- If a container stops at the end of a class while a cached DataSource still holds its connection URL, another class reusing that context can fail.
- `@DirtiesContext` forces restarts, slowing the suite and potentially re-running migrations/startup jobs multiple times.
- Parallel tests on a single DB/schema can collide; isolation and unique business keys are necessary.

In the demo, having a single PG class keeps lifecycles simple. As a suite grows, choose Boot-managed container lifecycles or a consistent singleton lifecycle, and design cleanup carefully.

## 20. Troubleshooting Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| PostgreSQL test appears to pass but metadata reports H2 | Boot 3.3 replaced DataSource with H2 | `@AutoConfigureTestDatabase(replace=NONE)` |
| `Failed to replace DataSource with an embedded database` | Missing H2/HSQL/Derby test driver or replacement cannot succeed | Add embedded driver or use real datasource + NONE |
| `Failed to determine suitable driver class` | Missing URL/driver/runtime dependency | Check datasource properties and Gradle deps |
| `Connection refused` to PostgreSQL | Container not running, wrong port, network issue | Check Testcontainers logs and service connection |
| `Could not find a valid Docker environment` | No Docker/compatible runtime | Run PG tests on an appropriate CI node |
| `Not a managed type` | Entity excluded from JPA scan | Check package/`@Entity`/`@EntityScan` |
| `NoSuchBeanDefinitionException` for service | `@DataJpaTest` does not scan ordinary services | Small `@Import` or `@SpringBootTest` |
| Table does not exist | Schema not created/migrations not run | Check `ddl-auto`, Flyway, schema |
| H2 passes, PostgreSQL query fails | Different native SQL/dialect | Test query on the vendor engine |
| Unique duplicate does not throw on `save` | SQL not flushed | `saveAndFlush`/`flush` |
| Every query fails after constraint error | Transaction is aborted/rollback-only | Stop operations in that test, roll back |
| Another test method sees no data | Default transaction rollback | Prepare fixtures per test |
| Data remains despite `@Transactional` test | Data committed outside the test transaction | Clean up and verify transaction boundaries |
| Boot 3.3 lacks `Replace.NON_TEST` | Mode was added in 3.4 | Use the enum values valid for your version |
| Boot 4 upgrade breaks `DataJpaTest` import | Test modules/packages changed | Use dependencies/imports for Boot 4 |
| Test passes alone, fails in suite | Shared DB, context cache, container lifecycle, parallelism | Isolate test state and lifecycle |

### 20.1. Root Cause Matters More Than the Outer Exception

`Failed to load ApplicationContext` is only a generic symptom. Always inspect `Caused by`:

- Failed to create embedded DataSource?
- PostgreSQL container failed to start?
- Missing JDBC driver?
- Hibernate DDL invalid on the DB vendor?
- Migration failed?
- Repository query validation failed?
- Service/application bean outside the slice accidentally depended upon?

Only change `@AutoConfigureTestDatabase` when you have actual evidence that datasource replacement is the problem.

## 21. Hands-On Exercises

### Exercise 1 — Prove H2 Instead of Guessing

Run `CatalogRepositoryH2Test.reallyUsesH2`. Change the expected vendor from `H2` to `PostgreSQL` on a sandbox branch and watch the assertion turn red. Revert it.

### Exercise 2 — Remove the H2 Driver

Temporarily remove `testRuntimeOnly 'com.h2database:h2'`, run the H2 class, and read the datasource replacement root cause. Restore it. Explain why having only the PostgreSQL driver does not make `connection=H2` work.

### Exercise 3 — `save` vs `saveAndFlush`

Try using `repository.save(duplicate)` instead of `saveAndFlush` and analyze when the exception appears. With `IDENTITY`, inserts may occur early to generate the ID; do not conclude “save never runs SQL”.

### Exercise 4 — Testing Real PostgreSQL

Enable `RUN_PG_TESTS=true` in a Docker environment. Verify metadata is `PostgreSQL`. Try removing `replace=NONE` on Boot 3.3 to observe the test getting replaced by H2, then restore it. Never use a production database as a fallback.

### Exercise 5 — Schema Migration

Use Flyway in an advanced test: create `V1__create_catalog_products.sql` for PostgreSQL, switch to `ddl-auto=validate`, and assert repository queries run. Explain why `create-drop` is not a migration test.

### Exercise 6 — Native PostgreSQL Query

Write a simple native query using PostgreSQL JSONB in a sandbox test. See why H2 cannot guarantee behavior; assert on the PostgreSQL container.

### Exercise 7 — Transaction Commit

Use `TestTransaction.flagForCommit()`/`end()` in a separate test, query data after commit, and clean up. Do not include this test in the fast suite without isolation.

### Exercise 8 — Concurrency

Design two transactions updating the same row with `@Version` or `@Lock(PESSIMISTIC_WRITE)`. Use the vendor database and coordination primitives with timeouts; do not use fixed sleeps as proof of ordering.

### Exercise 9 — Multiple Datasources

Suppose you have a primary orders datasource and a secondary analytics datasource. List which connections could still point to production if you only configure replacement for the primary. Design separate test profiles per persistence unit.

### Exercise 10 — Propose a Test Suite for a Real Project

A system has 80 repositories, 8 native PostgreSQL queries, Flyway migrations, multiple services, and HTTP APIs. Propose test counts/groups across H2, PostgreSQL, full context, and unit tests by risk. Each PostgreSQL test must answer: “Which vendor-specific bug can H2 not prove?”

## 22. Checklist When Reviewing Database Tests

- [ ] Clearly stated whether the target is H2 or a vendor database.
- [ ] Aware of the default replacement policy of the Spring Boot version in use.
- [ ] Not using `Replace.NON_TEST` on Boot 3.3 (this enum was added in 3.4).
- [ ] `@DataJpaTest` is a JPA slice, not full application integration.
- [ ] H2 tests have the embedded driver on the right runtime classpath.
- [ ] PostgreSQL tests use a safe datasource and `replace=NONE` on Boot 3.3.
- [ ] Have a JDBC metadata assertion to avoid passing on the wrong vendor.
- [ ] Do not use H2 compatibility mode as proof of the real engine.
- [ ] Unique constraints are tested at the SQL flush boundary.
- [ ] No further queries in the transaction after a constraint violation.
- [ ] Understand default rollback and the difference between flush and commit.
- [ ] Do not assert fixed generated identity sequences.
- [ ] Do not assume migrations are valid when only using Hibernate `create-drop`.
- [ ] Test database/schema is isolated and cleaned up.
- [ ] No production credentials/network access in automated tests.
- [ ] When using multiple DataSources, audit the connection of every unit.
- [ ] Testcontainers lifecycle aligns with Spring context caching.
- [ ] If PostgreSQL tests are skipped because Docker is unavailable, do not report them as passed.
- [ ] Do not add `@DirtiesContext` just to delete database rows.
- [ ] When upgrading to Boot 4, check the new version's packages/imports/test modules.

## 23. Conclusion

**Embedded H2** and **PostgreSQL Testcontainers** do not replace each other; they complement each other. H2 gives fast feedback for many JPA mappings and repository methods. Real PostgreSQL is necessary when bugs involve SQL dialect, native queries, schemas, constraints, migrations, concurrency, or production vendor transaction behavior.

In **Spring Boot 3.3**, `@AutoConfigureTestDatabase` defaults to `Replace.ANY`; to use a PostgreSQL test datasource without it being replaced by H2, set `replace=NONE` and **assert the actual vendor**. From Boot 3.4 onward, the `NON_TEST` default detects many test datasources better, though it does not automatically protect against accidentally connecting to an external database.

Base your choice on the behavior you need to prove, isolate data, and control test lifecycles — never assume “a repository test with a PostgreSQL dependency definitely ran against PostgreSQL”.

## 24. Official Documentation

- Spring Boot 3.3 — Testing Spring Boot Applications, `@DataJpaTest`: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — `@AutoConfigureTestDatabase` Javadoc, default `ANY`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html
- Spring Boot 3.3 — Testcontainers, `@ServiceConnection` and `@DynamicPropertySource`: https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html
- Spring Boot 3.4 — `Replace.NON_TEST` Javadoc: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html
- Spring Boot 3.4 — Release notes, database replacement with containers: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes
- Spring Boot 3.3 — Test slices auto-configurations: https://docs.spring.io/spring-boot/3.3/appendix/test-auto-configuration/slices.html
- Spring Framework — Transaction management in tests: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- Spring Framework — TestContext caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Data JPA — JPA query methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Testcontainers Java — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
- JUnit Jupiter — Conditional test execution: https://docs.junit.org/current/user-guide/