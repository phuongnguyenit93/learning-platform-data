# Changes in Test Database Replacement, Service Connection, and Container Libraries

A `@DataJpaTest` using PostgreSQL Testcontainers passes on Spring Boot 3.3, yet after an upgrade its query results or generated SQL behave differently. Sometimes Spring Boot **replaced the `DataSource` with H2**; sometimes starting in Spring Boot 3.4 the test-database replacement default changed to **recognize container databases**; sometimes `@ServiceConnection` is declared without producing `JdbcConnectionDetails`; or the classpath mixed Testcontainers 1.x and 2.x. A dangerous failure mode is tests passing on H2 while the author assumes real PostgreSQL and migrations were verified.

This Knowledge lesson, **"Changes in Test Database Replacement, Service Connection, and Container Libraries"**, belongs to **Versions and Migration** in **Spring Boot – testing**. It is a practical upgrade and diagnostics guide, not merely a version-number lookup table. We establish **which database is actually connected**, **why the framework chose it**, **precedence between connection details and properties**, **container lifecycles**, and **which BOM governs dependency versions**. Then we write tests that make CI **fail clearly if PostgreSQL is silently replaced with H2**.

**Baseline used to run the main example:** Java 17+, Spring Boot **3.5.16**, Spring Framework 6.2.x, Gradle, JUnit 5, Spring Data JPA, H2, and PostgreSQL Testcontainers **1.21.4** managed by Spring Boot 3.5. In Spring Boot 4.x, several packages/test modules and Testcontainers **2.x** changed; Boot 3.5 runnable code cannot have its imports or artifacts copied verbatim to Boot 4 without migration. Always consult **the BOM and Java API docs for your exact minor version**.

**Testing rule:** never assert only that a repository returns rows. When a test *must* run against PostgreSQL, assert `DatabaseMetaData.getDatabaseProductName()`, inspect the connection URL/details safely, and verify at least one meaningful database difference (migration/constraint/query). If a test runs only on H2, label it "H2 slice test" rather than "integration with production dialect".

## 1. Learning Objectives

- Explain how `@AutoConfigureTestDatabase` applies to JDBC/JPA test slices rather than all Spring tests.
- Distinguish the four `Replace` values: `ANY`, `AUTO_CONFIGURED`, `NON_TEST`, and `NONE`.
- Remember the default shift: Spring Boot **3.3: `ANY`**, from **3.4/3.5: `NON_TEST`**.
- Understand how `NON_TEST` recognizes a datasource connected to a test database via containers, `@DynamicPropertySource`, or Testcontainers JDBC URLs.
- Know that `@ServiceConnection` creates matching `ConnectionDetails` beans that **take precedence over `spring.datasource.*` connection properties** when auto-configuration consumes details.
- Know that `spring-boot-testcontainers` must be in test dependencies to use service connections.
- Distinguish `@Container` static fields, `@TestConfiguration @Bean` containers, and `@ImportTestcontainers` regarding lifecycle and context caching.
- Write both an explicit H2 `@DataJpaTest` and a PostgreSQL `@DataJpaTest` preserving the DB.
- Use `JdbcConnectionDetails` and JDBC metadata to verify which database was actually selected.
- Check how a full `@SpringBootTest` with `@ServiceConnection` differs from test-slice replacement.
- Know `@DynamicPropertySource` as a flexible alternative; avoid declaring both for the same JDBC DB unnecessarily.
- Choose `Replace.NONE` when tests must retain the exact datasource, especially across version migrations.
- Distinguish a Testcontainers JDBC URL `jdbc:tc:...` from a Java-managed `PostgreSQLContainer`.
- Understand BOM/version alignment and **Testcontainers 1.x vs. 2.x** Maven artifact/package differences.
- Know how to migrate Spring Boot 3.5 → 4.x without wrong `DataJpaTest`/`AutoConfigureTestDatabase` imports.
- Troubleshoot unavailable Docker, image pulls, missing drivers, constructor/package mismatches, and DB cache contamination.
- Plan upgrades with a baseline, version matrix, negative tests, logs, and rollback.
- Never touch production DBs, someone else's Docker daemon, or production credentials in tests.

## 2. Why Is "All Tests Green" Sometimes a False Signal?

Suppose a repository has a native query relying on PostgreSQL. If the test is replaced with H2 or skips real migrations, two outcomes happen:

1. The test fails early due to incompatible SQL syntax—an obvious signal.
2. The test still passes because the query happens to work on both, yet **it never tested** PostgreSQL partial indexes, `JSONB`, type mappings, locking/transactions, or constraint semantics.

Case 2 is far more dangerous: CI stays green while the underlying proof changed. Naming a class `ProductPostgresIntegrationTest` or starting a `PostgreSQLContainer` **does not prove** the `DataSource` used by Spring Data repositories points at that container. A container can boot on the side while `TestDatabaseAutoConfiguration` replaced the `DataSource` with embedded H2.

**Defensive technique:** assert the DB vendor and a query/constraint matching the test goal, not just `contextLoads`. Log partial metadata **without usernames, passwords, or tokens**, avoiding printing full JDBC URLs if they embed credentials.

## 3. Map of Key Version Changes

| Line | Default `@AutoConfigureTestDatabase.replace` | How Are Containers Preserved? | Testcontainers Library and Imports |
|---|---|---|---|
| Spring Boot 3.3.x | `ANY` | Usually requires `replace=NONE` to prevent slice datasource replacement | Boot 3.3 BOM manages Testcontainers 1.x; `org.testcontainers.containers.PostgreSQLContainer` |
| Spring Boot 3.4.x | `NON_TEST` (new in 3.4) | Attempts to recognize test DBs from container/metadata/dynamic URL | Testcontainers 1.x; `@MockitoBean` overrides also become standard |
| Spring Boot 3.5.16 | `NON_TEST` | Preserves **recognized** auto-configured test DBs; verify actual connection | Boot BOM manages Testcontainers **1.21.4**; 1.x imports |
| Spring Boot 4.0/4.1 | `NON_TEST` | Similar core logic while test modules/packages split by technology | Newer BOM manages Testcontainers 2.x; many artifacts/packages renamed |

Versions in this table are **verified against API docs and BOMs**, not a recommendation to jump directly from 3.3 to an arbitrary 4.x patch. Spring Boot 4 brings additional breaking changes in module layout and requirements: read the target line's migration guide rather than only bumping plugin versions.

### 3.1. The Turning Point in 3.4

Spring Boot 3.4 introduced `NON_TEST` and changed the long-standing `ANY` default. Its purpose is to avoid replacing a datasource already recognized as a **Testcontainers test database** with H2 inside `@DataJpaTest`/`@JdbcTest`. Consequently, an unchanged test source file can switch its actual runtime database simply by upgrading Spring Boot.

**Do not rely on defaults as a long-term contract when a test must target a specific vendor.** For mandatory PostgreSQL tests, `@AutoConfigureTestDatabase(replace=NONE)` states intent explicitly and stays clearer across versions. For intentional H2 tests, use `Replace.ANY` or explicit H2 config instead of relying on guesswork.

## 4. What Does `AutoConfigureTestDatabase` Actually Handle?

In Spring Boot 3.5, the annotation:

```java
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;

@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class SomeJpaOrJdbcTest {
    // An illustrative fragment; complete with the matching test slice.
}
```

only configures **`DataSource` replacement handled by test auto-configuration**. It does not magically alter R2DBC, MongoDB, or Redis connections. When multiple `DataSource` beans exist, the API docs note **only the `@Primary DataSource`** participates in replacement behavior; secondary datasources need separate test configuration and verification.

Slices such as `@DataJpaTest` and `@JdbcTest` include test database auto-configuration. Plain `@SpringBootTest` **does not automatically swap the datasource for H2 just because H2 is on the test classpath**; to apply replacement in a full context, apply the matching annotation/config explicitly. Whether an embedded DB starts automatically also depends on application configuration and drivers on the classpath.

## 5. Four `Replace` Choices: When to Use Each?

| `Replace` | Meaning | When to Use |
|---|---|---|
| `ANY` | Replace any `DataSource`, whether auto-configured or manually defined | Slices intentionally forced to run on H2/embedded DB |
| `AUTO_CONFIGURED` | Replace only a `DataSource` auto-configured by Boot | Reproducing legacy behavior distinguishing manual datasources |
| `NON_TEST` | Replace datasource **unless** it is auto-configured and connects to a recognized test database | Default since Boot 3.4; supports container tests |
| `NONE` | Do not replace the existing `DataSource` | PostgreSQL Testcontainers/real-DB tests that must retain the configured DB |

With `NON_TEST`, "test" **does not mean** "a database name ending in `_test`". Boot inspects specific configuration and metadata. A URL like `jdbc:postgresql://localhost:5432/mydb`—even if named `test`—is not automatically treated as a recognized test database.

### 5.1. `AUTO_CONFIGURED` Does Not Mean "Replace Only Production DBs"

It inspects **bean origin** (whether Boot auto-configured it), not whether the environment is production or test. An auto-configured datasource pointing at a PostgreSQL Testcontainer can still be replaced under `AUTO_CONFIGURED`. Therefore, do not use it to "protect containers"; its purpose is restoring legacy distinction against manual beans.

### 5.2. `ANY` Can Turn a PostgreSQL Test Into an H2 Test

A class annotated with:

```java
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY)
class IntendedPostgresTest {
    // If embedded H2 is available, @DataJpaTest may use H2.
    // A running container does not guarantee the repository uses PostgreSQL.
}
```

This snippet omits imports and container setup, illustrating the effect of the option. In real tests, inspect JDBC metadata after context startup to verify what happened.

## 6. How Does `NON_TEST` Recognize a Test Database?

According to Boot 3.5 Java API docs, recognized test database setups include:

1. A bean definition carrying `ContainerImageMetadata`, including Testcontainers databases annotated with `@ServiceConnection` and connections from Docker Compose.
2. `spring.datasource.url` whose value is supplied by `@DynamicPropertySource`.
3. `spring.datasource.url` using **Testcontainers JDBC URL syntax**, e.g., `jdbc:tc:postgresql:17-alpine:///testdb`.

Practical implication: Boot 3.4/3.5 can **preserve** an auto-configured datasource backed by these recognized sources. However, if you declare a manual `@Bean DataSource` or override it with complex configuration, recognition can behave differently. `NON_TEST` applies to "auto-configured and connecting to a test database", not simply "any bean vaguely related to Docker".

**Rule:** if PostgreSQL is mandatory for a test, set `Replace.NONE` to state intent explicitly—or at minimum **assert the database vendor** to catch regressions. If testing Boot's `NON_TEST` default itself is the goal (as in one class below), intentionally omit `NONE` and write assertions verifying how Boot detected it.

## 7. What Problem Does `@ServiceConnection` Solve?

Since Spring Boot 3.1, `@ServiceConnection` on a Testcontainers declaration lets Boot create `ConnectionDetails` beans based on container type or image name. Auto-configuration uses `ConnectionDetails` to configure JDBC/R2DBC/Redis/Kafka/etc., saving you from manually copying host, mapped port, username, and password into multiple `spring.*` properties.

Example in Boot 3.5 (snippet):

```java
@Testcontainers
@SpringBootTest
class PostgresServiceConnectionExample {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:17-alpine");

    // Boot can create JdbcConnectionDetails for the datasource.
}
```

Requires imports from `org.testcontainers.containers.PostgreSQLContainer`, `org.testcontainers.junit.jupiter.*`, `org.springframework.boot.testcontainers.service.connection.ServiceConnection`, and the `spring-boot-testcontainers` artifact. The container lifecycle is managed by JUnit's Testcontainers extension via `@Container`, while Spring Boot creates the connection details.

### 7.1. Do Not Confuse `@ServiceConnection` With Container Lifecycle

`@ServiceConnection` **does not** replace JUnit's `@Container` or Spring's `@Bean`. It declares "this container supplies connection details" to auto-configuration. The container must still be **created, started, and stopped** by an appropriate lifecycle owner. With a `@Bean` container, Spring Boot 3.5 manages start/stop with the `ApplicationContext`; with a static field, the `@Testcontainers` extension manages lifecycle.

## 8. How `ConnectionDetails` Takes Precedence Over Connection Properties

Spring Boot service connection docs state: when an appropriate `ConnectionDetails` bean exists, it **takes precedence over** connection-related configuration properties consumed by auto-configuration. For instance:

```properties
# If JdbcConnectionDetails from PostgreSQLContainer exists,
# the URL below is not necessarily the URL the DataSource actually uses!
spring.datasource.url=jdbc:h2:mem:decoy
```

If an app context imports a PostgreSQL container bean with `@ServiceConnection`, Boot's JDBC auto-configuration uses the JDBC URL, username, and password from `JdbcConnectionDetails` instead of `spring.datasource.url`. Thus, reading `Environment.getProperty("spring.datasource.url")` **does not prove** which database is actually connected.

**Reliable check:** `dataSource.getConnection().getMetaData().getDatabaseProductName()` or JDBC connection metadata in test-only code, alongside `JdbcConnectionDetails.getJdbcUrl()` to trace the source. Never log passwords, and never treat a decoy H2 property as proof the `DataSource` is H2.

### 8.1. Source of `JdbcConnectionDetails`

In Boot 3.5, the interface:

```java
import org.springframework.boot.autoconfigure.jdbc.JdbcConnectionDetails;
```

exposes methods like `getJdbcUrl()`, `getUsername()`, `getPassword()`, and default `getDriverClassName()`. Do not dump all bean fields in logs/CI where credentials could leak. Bean names and sources vary with auto-configuration, so tests should avoid depending on internal auto-config bean counts unnecessarily.

## 9. `@DynamicPropertySource`: The Alternative When Not Using `@ServiceConnection`

Prior to service connections—and still for custom services—`@DynamicPropertySource` injects dynamic values into the Spring `Environment`:

```java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url",
            postgres::getJdbcUrl);
    registry.add("spring.datasource.username",
            postgres::getUsername);
    registry.add("spring.datasource.password",
            postgres::getPassword);
}
```

This is a snippet requiring a `postgres` container and `org.springframework.test.context.DynamicPropertyRegistry/DynamicPropertySource` imports. In Boot 3.5, default `NON_TEST` recognizes a database URL supplied via `@DynamicPropertySource` per docs; in Boot 3.3, default `ANY` can still replace the datasource, so **`@AutoConfigureTestDatabase(replace=NONE)`** is commonly required.

**Do not declare both `@ServiceConnection` and `@DynamicPropertySource` for the same JDBC container without a clear reason.** Having two configuration sources describing the same database obscures which path is active. Pick one mechanism and assert the real connection after upgrades.

## 10. Testcontainers JDBC URL: A Third Path

Testcontainers supports a JDBC URL pattern:

```properties
spring.datasource.url=jdbc:tc:postgresql:17-alpine:///catalog_test
spring.datasource.driver-class-name=org.testcontainers.jdbc.ContainerDatabaseDriver
```

With the Testcontainers JDBC module/driver on the classpath, the container starts through the JDBC URL mechanism. This differs from instantiating a `PostgreSQLContainer` Java object with `@ServiceConnection`. In Boot 3.5, default `NON_TEST` includes logic recognizing `jdbc:tc:` as a test datasource.

**Limitations:** starting a container via JDBC URL has different lifecycle and reuse behavior compared to a Spring `@Bean` or JUnit `@Container`. Never combine three container mechanisms at once assuming they share one database. If a project uses Flyway, HikariCP, and multiple connections, verify migrations run against the right URL at the right container startup moment.

**Recommendation:** standardize on one primary mechanism per test group and keep alternatives documented as separate migration scenarios.

## 11. Required Libraries for Spring Boot 3.5 + `PostgreSQLContainer`

With Spring Boot 3.5.16, the BOM manages Testcontainers **1.21.4**; declare coordinates **without versions**:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:postgresql'
    testImplementation 'org.testcontainers:junit-jupiter'
    testRuntimeOnly 'org.postgresql:postgresql'
}
```

**Dependency breakdown:**

- `spring-boot-starter-test`: JUnit Jupiter, Spring Boot Test, and assertions.
- `spring-boot-testcontainers`: Boot integration, `@ServiceConnection`, connection-details factories.
- `org.testcontainers:postgresql`: `PostgreSQLContainer` class (Testcontainers **1.x**).
- `org.testcontainers:junit-jupiter`: `@Testcontainers`/`@Container` extension for static fields.
- `org.postgresql:postgresql`: JDBC driver (the container module does not replace the driver).
- `org.testcontainers:jdbc`: add if using `jdbc:tc:` URLs and the module is not pulled transitively by your setup.

Do not mix Testcontainers 2.x coordinates into the Boot 3.5 BOM. A build declaring `org.testcontainers:postgresql:1.21.4` alongside `org.testcontainers:testcontainers-postgresql:2.0.5` risks duplicate classes, inconsistent dependency trees, class-loading errors, and API mismatches. Pick one version family intentionally.

## 12. Testcontainers 1.x vs. 2.x: Coordinate, Artifact, and Package Changes

A frequent pitfall when reading recent blog posts on a Boot 3.5 project: **modern** Testcontainers Java docs describe the 2.x line, whereas the Boot 3.5 BOM uses 1.21.x. Migration map:

| Component | Testcontainers 1.21.x | Testcontainers 2.x |
|---|---|---|
| Core | `org.testcontainers:testcontainers` | Core keeps the same group/name |
| PostgreSQL module | `org.testcontainers:postgresql` | `org.testcontainers:testcontainers-postgresql` |
| JUnit 5 extension | `org.testcontainers:junit-jupiter` | `org.testcontainers:testcontainers-junit-jupiter` |
| Java `PostgreSQLContainer` | `org.testcontainers.containers.PostgreSQLContainer` | `org.testcontainers.postgresql.PostgreSQLContainer` |
| Redis/Kafka/... modules | 1.x module coordinates/packages | New 2.x module artifacts/packages; check each module |
| Managed version | Spring Boot 3.5 BOM: **1.21.4** | Some Spring Boot 4.x BOMs: **2.0.x** |

These are two **version families requiring deliberate migration**, not a simple version-string bump. When upgrading to Testcontainers 2.x, update **Gradle coordinates, imports, constructor/generic signatures, transitive dependencies, and Docker compatibility** together. Do not drop `2.0.5` into a Boot 3.5 build while keeping 1.x imports; overriding the BOM requires a full compatibility check.

### 12.1. Imports Are Easily Copied From the Wrong Version

**Boot 3.5 / Testcontainers 1.x:**

```java
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
```

**When using Testcontainers 2.x modules and new packages:**

```java
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
```

The JUnit package names stay the same, yet **the extension's artifact coordinate changed**. If code uses wildcard imports or module-specific classes like MongoDB/Kafka, inspect each package in the v2 API. In 2.x, do not copy the old `PostgreSQLContainer<?>` generic style blindly; consult current docs for updated signatures. Sections 20–25 of this lesson target **Boot 3.5/Testcontainers 1.x only**.

## 13. Spring Boot 4.x Also Changes Test Annotations and Imports

Beyond Testcontainers, Spring Boot 4 modularizes test support by technology. For example:

| Concept | Boot 3.5 Import | Boot 4.x Import |
|---|---|---|
| `@DataJpaTest` | `org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest` | `org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest` |
| `@AutoConfigureTestDatabase` | `org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase` | `org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase` |
| `@ServiceConnection` | `org.springframework.boot.testcontainers.service.connection.ServiceConnection` | Check 4.x branch API; service-connection package in Boot Testcontainers module |
| Test slice modules | 3.x `spring-boot-test-autoconfigure`/`starter-test` layout | Specialized modules `spring-boot-data-jpa-test`, `spring-boot-jdbc-test`, and 4.x starters |

Therefore, migrating 3.5 → 4.x requires auditing **dependency artifacts** and **Java packages** together. "Cannot resolve symbol DataJpaTest" does not mean Boot 4 dropped the JPA slice; it relocated the package and module. Do not switch the runnable 3.5 code below to 4.0 imports while keeping 3.5 Gradle artifacts—that is invalid mixing.

**Reference docs:** Javadocs for `@DataJpaTest`/`@AutoConfigureTestDatabase` on your exact Boot 4.x branch, managed dependency coordinates, and the migration guide. Avoid blindly following "latest" docs if your repo has not bumped majors yet.

## 14. Choosing the Right Mechanism for Your Test Goal

| What Do You Want to Verify? | Appropriate Approach | Annotations / Notes |
|---|---|---|
| Repository methods with portable SQL, fast PRs | H2 `@DataJpaTest` | `Replace.ANY` if forcing embedded; assert H2 |
| PostgreSQL-specific queries, JSONB, partial indexes | PostgreSQL Testcontainers + `@DataJpaTest` | `@ServiceConnection`, `Replace.NONE` for clarity or default `NON_TEST` + assert |
| Full service transactions/proxies + Postgres | `@SpringBootTest` + Postgres container | Not subject to slice replacement by default; assert vendor |
| Legacy/custom JDBC config | `@DynamicPropertySource` | `Replace.NONE` on slices to stay version-invariant |
| PostgreSQL test without creating a Java container object | `jdbc:tc:` URL | Requires JDBC module, driver, lifecycle, and default replacement checks |
| Multiple datasources | Bean-specific test config | `@Primary`/qualifiers, assert each datasource |
| R2DBC | Dedicated `R2dbcConnectionDetails`/test support | JDBC replacement does not apply to R2DBC |
| MongoDB/Redis/Kafka | Matching connection-details factory | Never use `AutoConfigureTestDatabase` for NoSQL |
| Flyway/Liquibase migrations | Matching DB dialect and real migrations | Never substitute `ddl-auto=create-drop` for real migrations |
| Reproducing Boot 3.3 behavior | Explicit `Replace.ANY` on Boot 3.4+ | Deliberate, with DB vendor assertions to prevent false confidence |

**An H2 test can be completely valid**, as long as its name, gate, and evidence match reality. The problem is never H2 itself, but **misidentifying which database actually ran**.

## 15. Runnable Demo: A Small Single-Table Catalog

We build a Spring Boot app storing `CatalogItem` with:

- `id`: UUID generated by JPA/Hibernate.
- `sku`: item code, unique in the database.
- `priceCents`: non-negative integer.

The repository exposes `findBySku`, and the service exposes `create` and `load`. Tests are split into four classes:

1. **`EmbeddedReplacementTest`:** `@DataJpaTest` + `Replace.ANY`, asserting **H2**.
2. **`PostgresDefaultNonTestTest`:** `@DataJpaTest` + `@Import(PostgresContainerConfig)`, **with no `replace` override** to verify Boot 3.5's `NON_TEST` default; asserting **PostgreSQL**.
3. **`PostgresExplicitNoneTest`:** `@DataJpaTest` + `Replace.NONE`, making policy explicit; asserting **PostgreSQL**.
4. **`PostgresFullContextTest`:** `@SpringBootTest` + test container config, verifying `JdbcConnectionDetails` overrides a decoy `spring.datasource.url` and that the service writes/reads PostgreSQL across a real transaction.

The demo omits controllers/APIs because the lesson focuses on **datasource selection and migration**, not HTTP serialization. For services needing HTTP coverage, add `@SpringBootTest(RANDOM_PORT)` without changing the primary datasource setup.

## 16. Directory Tree and Preconditions

```text
database-test-migration/
  settings.gradle
  build.gradle
  src/main/java/com/example/dbmigration/
    DbMigrationApplication.java
    CatalogItem.java
    CatalogRepository.java
    CatalogService.java
  src/test/resources/
    application.properties
  src/test/java/com/example/dbmigration/
    PostgresContainerConfig.java
    EmbeddedReplacementTest.java
    PostgresDefaultNonTestTest.java
    PostgresExplicitNoneTest.java
    PostgresFullContextTest.java
```

Requirements:

- Java 17+, Gradle Wrapper compatible with Boot 3.5, Maven Central access.
- Running Docker daemon/runtime with permission to pull/run `postgres:17-alpine` for the three PostgreSQL tests.
- Air-gapped environments need an image cache or properly configured internal registry.
- `H2` and `postgresql` JDBC drivers on the test runtime classpath.
- Never point tests at a production DB; the demo container creates **an isolated test database**.
- Never alter out-of-scope credentials, registries, or paths without authorization.

**Execution honesty:** the sources below were designed and reviewed against Boot 3.5.16 docs, yet have not been executed inside the learner's Gradle/Docker environment. "Expected behavior" sections are not captured runtime logs.

## 17. Full Gradle Configuration: Boot 3.5 With BOM-Managed Testcontainers

**`settings.gradle`**

```groovy
rootProject.name = 'database-test-migration'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
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

    // H2 used for explicitly embedded slice tests.
    testRuntimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'

    // Boot 3.5.16 BOM selects Testcontainers 1.21.4.
    testImplementation 'org.testcontainers:postgresql'
    testImplementation 'org.testcontainers:junit-jupiter'

    // Testcontainers does not replace a JDBC driver.
    testRuntimeOnly 'org.postgresql:postgresql'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Why omit `:1.21.4` on `org.testcontainers:postgresql`?** With the Spring Boot BOM and `io.spring.dependency-management`, omitting versions keeps the dependency graph unified. Manually overriding one module to 2.x without updating the rest of the suite's artifacts and imports risks an inconsistent classpath.

**Why are H2 and PostgreSQL drivers `testRuntimeOnly`?** Main app core code only needs JPA interfaces; concrete databases are chosen in tests. To run `bootRun` outside tests, configure the runtime app's datasource/driver separately. Never commit static production JDBC usernames/passwords in a repo outside training examples.

### 17.1. Inspecting Actually Resolved Versions

```bash
./gradlew dependencyInsight \
  --dependency org.testcontainers:postgresql \
  --configuration testRuntimeClasspath

./gradlew dependencies \
  --configuration testRuntimeClasspath
```

These commands reveal version conflicts and selections. Neither `dependencyInsight` nor Gradle reports alone prove Docker is running or that tests connected to PostgreSQL; pair them with `DataSource` metadata assertions inside JUnit tests.

## 18. Spring Boot Application Class

**`src/main/java/com/example/dbmigration/DbMigrationApplication.java`**

```java
package com.example.dbmigration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DbMigrationApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                DbMigrationApplication.class, args);
    }
}
```

Place the application root in a package enclosing entities, repositories, and services so `@DataJpaTest` scans JPA types and `@SpringBootTest` loads the app properly. Avoid redundant `@EnableJpaRepositories` when standard package layout suffices.

## 19. JPA Entity and Repository

**`src/main/java/com/example/dbmigration/CatalogItem.java`**

```java
package com.example.dbmigration;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.UUID;

@Entity
@Table(
        name = "catalog_items",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_catalog_items_sku",
                columnNames = "sku"))
public class CatalogItem {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false, length = 40)
    private String sku;

    @Column(nullable = false)
    private long priceCents;

    protected CatalogItem() {
        // Required by JPA.
    }

    public CatalogItem(String sku, long priceCents) {
        if (sku == null || sku.isBlank() || priceCents < 0) {
            throw new IllegalArgumentException(
                    "Invalid catalog item");
        }
        this.sku = sku;
        this.priceCents = priceCents;
    }

    public UUID getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public long getPriceCents() {
        return priceCents;
    }
}
```

**`src/main/java/com/example/dbmigration/CatalogRepository.java`**

```java
package com.example.dbmigration;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CatalogRepository
        extends JpaRepository<CatalogItem, UUID> {

    Optional<CatalogItem> findBySku(String sku);
}
```

The entity defines a unique constraint valid in both H2 and PostgreSQL; tests call `saveAndFlush` so SQL constraint violations surface at a clear boundary. Never use this constraint to claim H2 matches PostgreSQL across all index or locking semantics.

## 20. Real Service With Transactions

**`src/main/java/com/example/dbmigration/CatalogService.java`**

```java
package com.example.dbmigration;

import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CatalogService {

    private final CatalogRepository repository;

    public CatalogService(CatalogRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public UUID create(String sku, long priceCents) {
        CatalogItem item = repository.save(
                new CatalogItem(sku, priceCents));
        return item.getId();
    }

    @Transactional(readOnly = true)
    public CatalogItem load(UUID id) {
        return repository.findById(id).orElseThrow();
    }
}
```

In the full-context test, calling `CatalogService.create` goes through the Spring proxy so the transaction commits upon method return. A unit test instantiating `new CatalogService(...)` will not test AOP transactions; here we use a real PostgreSQL datasource/repository to verify behavior across layers.

## 21. Test-Only Properties: Do Not Override the Container by Mistake

**`src/test/resources/application.properties`**

```properties
# Training only: generate schema inside owned test databases.
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false

# Avoid accidental H2 in-memory database name collisions.
spring.datasource.generate-unique-name=true

# Uncomment to diagnose which datasource Boot initialized:
# logging.level.org.springframework.boot.autoconfigure.jdbc=DEBUG
# logging.level.org.springframework.boot.test.autoconfigure.jdbc=DEBUG
# logging.level.org.testcontainers=INFO
```

Do not put `spring.datasource.url=jdbc:h2:mem:...` in global test properties when PostgreSQL tests need `@ServiceConnection` to supply the URL. The full-context sample intentionally places an H2 `decoy` **on that test class alone** to demonstrate precedence.

**Important:** `spring.jpa.hibernate.ddl-auto=create-drop` lets Hibernate generate the schema for testing, which does not verify real Flyway migrations. When validating production migration compatibility, switch to running Flyway/Liquibase against a container/database of matching dialect with `ddl-auto=validate` or `none`, rather than letting Hibernate synthesize tables in place of migrations.

## 22. H2 Test: Intentionally Replacing DataSource With Embedded DB

**`src/test/java/com/example/dbmigration/EmbeddedReplacementTest.java`**

```java
package com.example.dbmigration;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY)
class EmbeddedReplacementTest {

    @Autowired
    DataSource dataSource;

    @Autowired
    CatalogRepository repository;

    @Test
    void replacementReallyUsesH2() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            assertEquals("H2",
                    connection.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void repositoryWorksOnEmbeddedDatabase() {
        String sku = "H2-" + UUID.randomUUID();
        repository.saveAndFlush(new CatalogItem(sku, 1200));

        assertTrue(repository.findBySku(sku).isPresent());
    }
}
```

**Two tests** explicitly state their intent: this is an **H2 slice**, not PostgreSQL integration. `Replace.ANY` mandates replacing the datasource; H2 is on the test runtime classpath so embedded replacement succeeds. `@DataJpaTest` rolls back transactions by default, so the second method's row is not committed to a shared DB.

**Why assert the vendor?** If an upgrade or config error causes `DataSource` to point at PostgreSQL or another DB, `replacementReallyUsesH2` fails immediately instead of silently running against the wrong environment. For tests intentionally allowing H2/Derby/HSQLDB based on classpath, assert against your allowed policy.

## 23. `PostgresContainerConfig`: Spring Manages the Container Lifecycle

**`src/test/java/com/example/dbmigration/PostgresContainerConfig.java`**

```java
package com.example.dbmigration;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class PostgresContainerConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> catalogPostgres() {
        return new PostgreSQLContainer<>("postgres:17-alpine")
                .withDatabaseName("catalog_test")
                .withUsername("catalog")
                .withPassword("test_only");
    }
}
```

This uses Spring Boot's **container bean** pattern:

- `@TestConfiguration` is imported only by tests needing PostgreSQL; it is not component-scanned into the regular application.
- `@Bean` returns a **typed** `PostgreSQLContainer<?>`; Boot can infer the JDBC service connection without requiring `name`.
- `@ServiceConnection` creates `JdbcConnectionDetails` from the container.
- Spring manages **start/stop tied to the `ApplicationContext` lifecycle**, working cleanly with Spring TestContext cache reuse.
- Test classes using `@Import(PostgresContainerConfig.class)` **do not need** `@Testcontainers/@Container`, because this is a Spring bean rather than a JUnit static field.

**Why not mix both lifecycles at once?** Putting `@Container` on a `@Bean` method does not turn it into a JUnit field. Conversely, stopping a static `@Container` in `@AfterAll` can leave a cached `ApplicationContext` in another test class holding a `DataSource` pointed at a stopped container.

### 23.1. Container Image and Password

Image tag `postgres:17-alpine` is a lab example. Production-like CI can pin a digest for reproducibility and supply-chain integrity. The `test_only` password is strictly for ephemeral test containers, never for shared staging or production. Avoid printing Postgres passwords in test reports.

## 24. Spring Boot 3.5 Default `NON_TEST` Preserves PostgreSQL

**`src/test/java/com/example/dbmigration/PostgresDefaultNonTestTest.java`**

```java
package com.example.dbmigration;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest
@Import(PostgresContainerConfig.class)
class PostgresDefaultNonTestTest {

    @Autowired
    DataSource dataSource;

    @Autowired
    CatalogRepository repository;

    @Test
    void defaultNonTestPreservesServiceConnectionPostgres()
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            assertEquals("PostgreSQL",
                    connection.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void repositoryActuallyQueriesPostgres() {
        String sku = "PG-DEFAULT-" + UUID.randomUUID();

        repository.saveAndFlush(new CatalogItem(sku, 2399));

        assertTrue(repository.findBySku(sku).isPresent());
    }
}
```

**Two tests** running real PostgreSQL in Testcontainers. The class **omits `@AutoConfigureTestDatabase(replace=NONE)`** so we test Spring Boot 3.5.16's default `NON_TEST` behavior: Spring service connection carries container metadata, so test-database replacement preserves the datasource rather than replacing it with H2. If you run this exact code on Boot 3.3, **do not assume** it keeps Postgres: pre-3.4 default `ANY` can replace it.

The decisive QA check is `getDatabaseProductName() == "PostgreSQL"`. If the test started a container while repositories silently hit H2, this test fails immediately.

## 25. Explicit `NONE`: Clear Intent and Readable Across Migrations

**`src/test/java/com/example/dbmigration/PostgresExplicitNoneTest.java`**

```java
package com.example.dbmigration;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(PostgresContainerConfig.class)
class PostgresExplicitNoneTest {

    @Autowired
    DataSource dataSource;

    @Autowired
    CatalogRepository repository;

    @Test
    void explicitNoneKeepsPostgresDataSource()
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            assertEquals("PostgreSQL",
                    connection.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void generatedUuidAndRepositoryWorkOnPostgres() {
        CatalogItem saved = repository.saveAndFlush(
                new CatalogItem("PG-NONE-" + java.util.UUID.randomUUID(),
                        3100));

        assertNotNull(saved.getId());
    }
}
```

**Two methods.** `Replace.NONE` makes "do not replace datasource" unmistakable, aiding reviews when migrating across Boot 3.3/3.4/3.5. It **does not create** a PostgreSQL connection on its own; `@ServiceConnection`, dynamic properties, or a JDBC URL is still needed. A test using `NONE` without a configured URL fails due to a missing datasource or wrong host—that is a setup error to fix, not a reason to drop `NONE`.

**Never say `Replace.NONE` is always best:** in fast H2 slices relying on auto-replacement, `NONE` can accidentally keep a real DB URL if test config is misconfigured. Match the mode to the test goal, assert the vendor, and isolate credentials.

## 26. Full Context: `@ServiceConnection` Takes Precedence Over Configured URLs

**`src/test/java/com/example/dbmigration/PostgresFullContextTest.java`**

```java
package com.example.dbmigration;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(properties =
        "spring.datasource.url=jdbc:h2:mem:decoy")
@Import(PostgresContainerConfig.class)
class PostgresFullContextTest {

    @Autowired
    DataSource dataSource;

    @Autowired
    CatalogService service;

    @Autowired
    CatalogRepository repository;

    @Test
    void serviceConnectionOverridesDecoyJdbcUrl()
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            assertEquals("PostgreSQL",
                    connection.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void realServiceCommitsAndCanBeReadBack() {
        String sku = "FULL-" + UUID.randomUUID();
        UUID id = service.create(sku, 4500);

        try {
            CatalogItem loaded = repository.findById(id)
                    .orElseThrow();

            assertEquals(sku, loaded.getSku());
            assertEquals(4500, loaded.getPriceCents());
            assertNotNull(loaded.getId());
        } finally {
            repository.deleteById(id);
        }
    }
}
```

**Two methods** running the full Spring app with the Postgres container bean. This class intentionally sets `spring.datasource.url` to an H2 `decoy`, yet `JdbcConnectionDetails` from `@ServiceConnection` takes precedence during JDBC auto-configuration, so the assertion remains **PostgreSQL**. That is a stronger migration check than merely inspecting an `Environment` property.

The second test **omits `@Transactional` on the test class**. `CatalogService.create` runs in its own transaction and commits on return. Reading back via the repository runs separately and verifies committed data. The `finally` block deletes only the ID created by this test rather than wiping the entire database.

**Scope limitation:** there is no HTTP server in default `@SpringBootTest` (`MOCK` web environment, as the app lacks a Web starter). This test proves full service→repository→Postgres wiring and transactions, **not** inbound HTTP, authentication, or production deployment.

## 27. Total Tests and Expected Outcomes

| Class | `@Test` Count | Actual Database Required | Purpose |
|---|---:|---|---|
| `EmbeddedReplacementTest` | 2 | H2 | Replacement `ANY` |
| `PostgresDefaultNonTestTest` | 2 | PostgreSQL | Boot 3.5 default `NON_TEST` |
| `PostgresExplicitNoneTest` | 2 | PostgreSQL | Explicit `NONE` |
| `PostgresFullContextTest` | 2 | PostgreSQL | `ServiceConnection` precedence + real commit |
| **Total** | **8** | H2 + PostgreSQL (separate containers) | Never confuse DB vendors |

Run with Gradle Wrapper:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

JDK 17+, a valid Gradle wrapper, a running Docker daemon, and the PostgreSQL image are **preconditions**. When Docker is unavailable, PostgreSQL tests should **FAIL setup** in a mandatory container CI job rather than skipping everything and reporting "PostgreSQL verified".

**Expected outcome from source review:** 8 tests designed to pass on Boot 3.5.16 and TC 1.21.4. This is **not an observed Gradle run log**, and no actual runtime/test report exists yet in the learner's workspace.

## 28. Why Can `@DataJpaTest` Run Against H2 Even While Postgres Is Starting?

Common source of confusion:

```java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY)
class WronglyAssumedPostgresTest {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:17-alpine");
}
```

This snippet omits imports and test methods for illustration. A JUnit-managed, running container **does not mean** the Spring JPA datasource points at it. Without `@ServiceConnection` or `@DynamicPropertySource`, Boot does not even know the container's host/port/username/password. Even with them, if `replace = ANY` and H2 is present, the datasource gets replaced.

**How to investigate:**

1. Safely print/log the actual `DatabaseMetaData.getDatabaseProductName()`.
2. Check the effective `@AutoConfigureTestDatabase` mode and version default.
3. Verify whether `JdbcConnectionDetails` was created.
4. Confirm the `PostgreSQLContainer` instance uses the right class and actually started.
5. Check whether the test uses `@DataJpaTest` (auto-replace) vs. `@SpringBootTest` (different default).
6. Check if H2 is on the test classpath.
7. Check `@Primary DataSource` when multiple datasources exist.
8. Inspect migrations and connection URL at startup.
9. Where PostgreSQL is mandatory, set `NONE` and vendor assertions.
10. Avoid "fixing" this by deleting H2 project-wide if fast H2 slices still rely on it.

## 29. `@Container` Static Fields and the Context Cache: Lifetime Pitfalls

Two distinct Testcontainers patterns:

**JUnit-managed:**

```java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class LegacyContainerTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:17-alpine");
}
```

**Spring-managed (runnable pattern in Section 23):**

```java
@TestConfiguration(proxyBeanMethods = false)
class SharedPostgresTestConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgres() {
        return new PostgreSQLContainer<>("postgres:17-alpine");
    }
}
```

Both require `spring-boot-testcontainers` to create service connections. With a **static field**, JUnit's Testcontainers extension scopes container lifetime to the test class, while Spring TestContext can cache the `ApplicationContext` beyond that class's lifecycle. A subsequent class reusing the cached context hits a `DataSource` pointing at a stopped container, causing connection refused errors. With a **Spring `@Bean`**, Boot ties container lifecycle to the context and stops it only when the context closes—far safer with context cache reuse.

Never call `postgres.stop()` manually inside `@AfterAll` if cached contexts still reference it. When tests genuinely require distinct container lifecycles, separate context cache keys or manage context teardown intentionally rather than scattering `@DirtiesContext` everywhere.

## 30. `@DynamicPropertySource` When Migrating From Legacy Code

A Boot 3.2/3.3 project often contains:

```java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class LegacyDynamicPropertiesTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:17-alpine");

    @DynamicPropertySource
    static void register(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }
}
```

This is an **illustrative snippet**, not a core runnable file: it requires JUnit, Spring, TC imports, and a test method. It remains valid for custom non-JDBC properties or services lacking a service-connection factory.

**When migrating to `@ServiceConnection`:**

1. Add `org.springframework.boot:spring-boot-testcontainers`.
2. Annotate the container with `@ServiceConnection` (or convert it to a Spring `@Bean` container).
3. Standardize on one connection source; remove redundant dynamic JDBC properties.
4. For `@DataJpaTest`, keep `NONE` for explicit DB retention, or test default `NON_TEST` with vendor assertions.
5. Keep `@DynamicPropertySource` for custom **non-database properties** if still needed.
6. Verify bean lifecycle/caching and DB schema migrations.
7. Run tests against Docker and inspect JDBC metadata.

Do not replace `@DynamicPropertySource` just because the new annotation is "shorter" if the project relies on custom schemas, multiple datasources, or connection properties unsupported by the factory.

## 31. Container Types, Image Names, and `ConnectionDetails` Factories

Spring Boot uses `ContainerConnectionDetailsFactory` to build details from **container subtype** or **image repository name**. For typed containers like `PostgreSQLContainer`, Boot recognizes them directly. Generic containers can lack type metadata when declared as `@Bean`:

```java
@TestConfiguration(proxyBeanMethods = false)
class RedisContainerConfig {

    @Bean
    @ServiceConnection(name = "redis")
    GenericContainer<?> redis() {
        return new GenericContainer<>("redis:7-alpine")
                .withExposedPorts(6379);
    }
}
```

This snippet needs `GenericContainer`/`Bean`/`TestConfiguration`/`ServiceConnection` imports and is not part of the runnable Postgres project. `name="redis"` matters because Boot cannot invoke the `@Bean` method early to read the image name from a `GenericContainer<?>` return type. With custom/private mirrors such as `registry.company.test/mirror/redis`, `name` also helps the factory identify the service type.

### 31.1. One Container Can Supply Multiple `ConnectionDetails` Types

`PostgreSQLContainer` can produce both `JdbcConnectionDetails` and `R2dbcConnectionDetails` when the corresponding factories and auto-configurations are present. Restrict this via `@ServiceConnection(type=...)` if needed. In a JDBC-only project, do not enable R2DBC drivers. **Do not assume R2DBC datasources are replaced by `@AutoConfigureTestDatabase`**, which applies strictly to JDBC `DataSource`.

## 32. Multiple `DataSource`s and Custom `@Bean DataSource`

An application has `primaryDataSource` for orders and `auditDataSource` for auditing:

```java
@Bean
@Primary
DataSource primaryDataSource() { /* ... */ }

@Bean
DataSource auditDataSource() { /* ... */ }
```

This is a dummy snippet without implementations. With multiple datasources, `@AutoConfigureTestDatabase` considers only the `@Primary` bean. If tests need both databases backed by Docker, configure, qualify, and assert **each** datasource rather than inferring from one repository query.

With a manually defined `@Bean DataSource`, Boot JDBC auto-configuration may back off. Testcontainers `JdbcConnectionDetails` **does not automatically override a custom `DataSource` bean** that reads its own fixed URL. Update the factory to consume `JdbcConnectionDetails`, bind properties properly, or provide test-specific bean configuration. Vendor assertions will catch a manual bean bypassing Spring Boot auto-configuration.

## 33. Flyway/Liquibase Migrations Are Separate From Replacement

A `@DataJpaTest` using H2 and `ddl-auto=create-drop` can generate valid entity tables while completely skipping real PostgreSQL migrations. Upgrading Boot or Testcontainers can surface failures from:

- Flyway plugin/version and PostgreSQL-specific modules.
- Migration scripts containing `CREATE INDEX CONCURRENTLY`, `JSONB`, partial indexes, or operators unsupported by H2.
- Differing schema search paths or user permissions.
- Liquibase changelog contexts, labels, or tablespaces differing from production.
- Hibernate dialect/validation changes across ORM versions.
- Container image upgrades from PostgreSQL 14 to 17 changing engine behavior.
- Docker Compose service connections picking up a different DB than expected.

**Separate two test goals:**

1. **JPA fast slice:** H2, Hibernate DDL from entities, high speed; never claims migrations were validated.
2. **DB migration integration:** PostgreSQL Testcontainers, applying real Flyway/Liquibase scripts with `ddl-auto=validate` or Hibernate DDL disabled, asserting both DB vendor and schema constraints.

An integration test still using `ddl-auto=create-drop` only verifies Hibernate can create tables—it **never** proves Flyway migrations `V001..V100` execute cleanly.

### 33.1. `ServiceConnection` for Flyway and Liquibase

Boot's Testcontainers factories also support Flyway/Liquibase connection details from `JdbcDatabaseContainer`. Still verify auto-configuration conditions, Flyway/Liquibase dependencies on the classpath, and migration locations. A working service connection **does not run migrations** if the migration library is missing or disabled.

## 34. Maven BOM, Gradle BOM, and Version Management

A safe build picks **one BOM aligned with your Spring Boot version**:

```groovy
plugins {
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    testImplementation 'org.testcontainers:postgresql'
    testImplementation 'org.testcontainers:junit-jupiter'
}
```

With the right dependency management plugin, Testcontainers module versions come from Spring Boot's BOM. If your team must override versions for Docker API compatibility or a security update, upgrade **the whole family together** via BOM override, verify Spring Boot service connection compatibility, and run the test matrix. Never bump a single module while leaving core, Testcontainers JDBC, and the JUnit extension on mismatched versions.

**Verify in two places:**

- Build dependency graph: right artifacts/versions with zero conflicts.
- Runtime JDBC metadata: right actual DB (PostgreSQL/H2) and schema/migrations.

`dependencies --configuration testRuntimeClasspath` proves classpath versions, **not** which container the `DataSource` actually talks to.

## 35. Docker and CI During Version Upgrades

Testcontainers requires an **available container runtime**. A CI job running PostgreSQL tests needs:

- Docker daemon or a Testcontainers-supported runtime with appropriate socket/endpoint permissions.
- Network/image registry access and an appropriate pull policy.
- Sufficient disk and RAM for containers and JVMs.
- Controlled image tags/digests; avoid `latest` introducing unannounced shifts.
- Isolation from another job's database container if data ownership is unclear.
- Lifecycle cleanup of containers/resources without leaking Docker networks or volumes.
- CI logs/artifacts scrubbed of container passwords and sensitive DB data.
- Test DB users/roles scoped strictly to the test container.
- Finite Gradle test task timeouts and readiness checks.
- If Docker is unavailable in a mandatory integration job, report **SETUP FAIL** rather than skipping and reporting integration pass.
- Avoid running Testcontainers privileged/unrestricted in disallowed environments; testing is no reason to drop security controls.
- On Windows/macOS Docker Desktop, verify Docker API compatibility with your Testcontainers/`docker-java` version.

**Especially on Spring Boot 3.5:** Boot documents `docker-java.properties` and Docker Desktop API compatibility; do not swap Docker daemon versions or `DOCKER_HOST` blindly before reading startup causes and the dependency graph.

## 36. Diagnostic Symptoms and Remedies

| Symptom | Possible Cause | Verification / Remedy |
|---|---|---|
| Test meant for PostgreSQL reports H2 in JDBC metadata | TestDatabase replacement, H2 on classpath | Check `Replace` mode; use `NONE`/assertions |
| After 3.3→3.4, test suddenly hits PostgreSQL | Default `ANY`→`NON_TEST` | Verify test intent; pin `ANY` if H2 is wanted |
| `NoSuchBeanDefinitionException JdbcConnectionDetails` | Missing factory/`@ServiceConnection` or bean setup bug | Check `spring-boot-testcontainers`/container type |
| Container starts yet datasource points elsewhere | Details not wired or custom `DataSource` bean | Assert actual connection; inspect `@Bean`/auto-config |
| `Failed to replace DataSource with embedded database` | `Replace` expects embedded DB, no H2/HSQL/Derby driver | Add embedded driver or use `NONE` for PG |
| `Could not find a valid Docker environment` | Runtime/permissions/`DOCKER_HOST` | Fix Docker setup; do not auto-skip |
| `No suitable driver` for PostgreSQL | Missing `org.postgresql:postgresql` | Add JDBC driver to test runtime |
| `NoClassDefFoundError org.testcontainers...PostgreSQLContainer` | Mixed 1.x/2.x modules or wrong import | Re-align BOM, artifacts, packages |
| `ClassNotFoundException` for Testcontainers JUnit Jupiter | Missing/mismatched JUnit extension module | Use matching family artifact |
| Boot 4 cannot find old `DataJpaTest` | Package/module relocated | Update imports and add Boot 4 module |
| Property `datasource.url` says H2 while metadata says Postgres | `ConnectionDetails` precedence | Trust JDBC metadata; inspect factory |
| `@ServiceConnection` on `GenericContainer` lacks factory | Missing name/type hint | Add `name="redis"` or custom details |
| Docker container stops before Spring context closes | Per-class JUnit lifecycle vs. cached context | Use Spring-managed `@Bean`/`@ImportTestcontainers` |
| Cached context in another test hits stale container port | Dynamic property/container lifecycle mismatch | Align context cache key/lifecycle |
| `@DataJpaTest` cannot find a service bean | Slice intentionally excludes services | Import targeted config or use full context |
| JPA/Hibernate schema broken on Postgres | DDL/migrations differ from H2 | Run real migrations; validate |
| H2 tests pass while native SQL fails in production | DB dialect/feature differences | Test against real Postgres, not only H2 |
| Flaky tests under parallel runs | Shared DB/IDs/cached state | Use unique fixtures, transaction rollback |
| Boot upgrade breaks repository method | Spring Data/Hibernate semantics changed | Inspect root exception and release notes |
| `BeanDefinitionOverrideException` | Duplicate DB configs/imports | Pick one source; audit qualifiers |
| Password leaked in CI logs | Printing full `ConnectionDetails`/JDBC URL | Log `productName` and masked details only |

### 36.1. Start From the Root Cause, Not the Outer Exception

When context startup fails, do not throw `@DirtiesContext`, `@Transactional`, or delete assertions blindly. Gather the **first exception cause chain**, dependency graph, Boot version, TC version, Docker environment, and actual connection details. Test one hypothesis per change and re-run deterministically.

## 37. Four-Step Debug Sequence for `DataSource` Selection

```text
1. Which context type is running?
     @DataJpaTest / @JdbcTest / @SpringBootTest

2. What is the effective Replace mode?
     ANY / AUTO_CONFIGURED / NON_TEST / NONE

3. Is there a valid test connection recognized by Boot?
     ServiceConnection -> JdbcConnectionDetails
     DynamicPropertySource -> datasource URL
     jdbc:tc:... -> Testcontainers JDBC driver
     custom @Bean DataSource -> may bypass auto-config

4. Actual DataSource.getConnection().getMetaData():
     DatabaseProductName = "H2" or "PostgreSQL"?
     -> Test FAILS if it differs from target.
```

Never start from `spring.datasource.url` alone: with `ConnectionDetails`, properties may not reflect the active connection. Never rely solely on seeing `PostgreSQLContainer started` in logs: the container may not be the DB backing your repository.

## 38. Controlled Upgrade Process

**Before upgrading:**

1. Record versions of the Boot plugin, Spring Framework, Spring Data, Hibernate, Testcontainers BOM, and Postgres image.
2. List all JPA/JDBC test slices and `@AutoConfigureTestDatabase` annotations.
3. Locate all `@DynamicPropertySource` methods, `@ServiceConnection` fields/beans, and `jdbc:tc:` URLs.
4. Classify which tests **must run PostgreSQL** and which are **intentionally H2**.
5. Add JDBC vendor assertions to representative tests to catch silent DB swaps.
6. Record real schemas/migrations and DB-specific tests currently running.
7. Baseline Gradle test counts, startup times, context cache misses, and Docker versions.
8. Confirm test DBs are isolated and users/credentials cannot touch production.

**During upgrade:**

9. Upgrade the Boot BOM centrally without overriding individual Testcontainers modules randomly.
10. For Boot 3.3 → 3.4, audit the `ANY` → `NON_TEST` default shift.
11. For Boot 3.5 → 4.x, update test imports/modules and TC 1.x → 2.x artifacts/packages per docs.
12. Standardize on a single source of JDBC connection details per test group.
13. Configure `Replace.NONE`/`ANY` explicitly according to intent.
14. Run H2 tests first, then PostgreSQL container tests, then full integration/migrations.
15. If cached contexts reuse a stopped container, fix lifecycle ownership rather than disabling the entire cache.
16. Verify every test runs against **the intended database product**, not merely a passing status.

**After upgrade:**

17. Compare query/constraint behavior, migrations, cleanup, and rollback.
18. Archive JUnit XML/HTML reports, dependency insights, and Docker diagnostics.
19. Measure performance/CI cost, image pulls, and memory usage.
20. Document decisions, test scope, and known differences.
21. If rolling back, revert versions, imports, and dependency families together—never roll back just the plugin.

## 39. Common Migration Scenarios

### 39.1. Boot 3.3 → 3.4: Fast H2 Slice Accidentally Turns Into Postgres

Previously `@DataJpaTest` defaulted to `ANY` and replaced the datasource with H2; after bumping to Boot 3.4, default `NON_TEST` recognizes the container so the test starts hitting PostgreSQL, slowing down CI. If the test intends portable H2 mapping, pin `@AutoConfigureTestDatabase(replace=ANY)` and assert `H2`. If it intends Postgres-specific integration, keep Postgres and place it in the proper CI gate.

### 39.2. PostgreSQL Testcontainers Test Runs on H2

Usually caused by `replace=ANY`, missing `@ServiceConnection`/`@DynamicPropertySource`, or a custom `DataSource` override. Do not just rename the class. Assert the actual vendor, inspect replacement mode, and add connection details or `NONE`.

### 39.3. Boot 3.5 Copying Testcontainers 2.0 Docs

A recent blog post uses `org.testcontainers:testcontainers-postgresql`, yet the Boot 3.5 BOM still manages `org.testcontainers:postgresql:1.21.4`. Do not mix them arbitrarily. Follow Testcontainers 1.x docs while on Boot 3.5; when upgrading to Boot 4.x, upgrade the full dependency family, modules, and imports together and test compatibility.

### 39.4. `GenericContainer` Redis Is Not Recognized

With `@Bean GenericContainer<?>`, Boot cannot invoke the bean early to inspect its image name; add `@ServiceConnection(name="redis")` or use a supported details factory/custom bean. The typed PostgreSQL container in the demo does not have this issue.

### 39.5. PostgreSQL Tests Pass While Flyway Migrations Never Ran

`@ServiceConnection` only provides connection details; it does not add Flyway or schema scripts. Ensure test dependencies, migration locations, and `ddl-auto=validate` are configured, then assert that the migration-created schema exists. Distinguish "JPA `create-drop` passes" from "database migration passes".

### 39.6. Context Cache Reuses a Stale Port

A per-class static `@Container` stops after Class A, yet Class B reuses the cached context holding the old datasource URL. Use a Spring-managed container bean sharing the cached context's lifecycle, or separate contexts properly. Never "fix" it by hardcoding a mapped port, as Docker port mapping is dynamic.

## 40. Practice Exercises With Answers

### A. Default Configuration Shift

A `@DataJpaTest` defaults to `ANY` on Boot 3.3 and `NON_TEST` on Boot 3.5. What can change?

**Answer:** A recognized Testcontainers test datasource may be preserved in Boot 3.5 instead of being replaced by embedded H2, changing the target DB and CI timing. Assert the vendor and specify an explicit mode if needed.

### B. H2 on the Classpath

A PostgreSQL test has H2 on `testRuntimeClasspath`. Does that mean Boot will definitely pick H2?

**Answer:** No. It depends on `@AutoConfigureTestDatabase` mode, JDBC auto-configuration, and `ConnectionDetails`. Inspect metadata; `NONE` preserves the configured DB when wired properly.

### C. Missing Service Connection Module

`@ServiceConnection` fails to resolve on Boot 3.5. Which dependency is usually missing?

**Answer:** `testImplementation 'org.springframework.boot:spring-boot-testcontainers'`.

### D. Missing PostgreSQL JDBC Driver

The Postgres container starts, yet Hikari reports "No suitable driver". What is missing?

**Answer:** The PostgreSQL JDBC driver, e.g., `testRuntimeOnly 'org.postgresql:postgresql'`. The Testcontainers module does not replace the driver.

### E. `ConnectionDetails` vs. Property

`spring.datasource.url` shows H2 while `DataSource.getConnection()` reports PostgreSQL. Which should you trust?

**Answer:** Actual JDBC metadata/`ConnectionDetails`. Service connections take higher precedence than connection-related properties in auto-configuration.

### F. Multiple Datasources

There are two `DataSource` beans, one `@Primary`. Does `@AutoConfigureTestDatabase` replace both automatically?

**Answer:** No. The API docs state only the primary datasource is considered; test each datasource and qualifier separately.

### G. Testcontainers Module Versions

You add `org.testcontainers:testcontainers-postgresql:2.0.5` to Boot 3.5 while `org.testcontainers:postgresql:1.21.4` remains. Should you merge?

**Answer:** Not without aligning the version family, imports, and verifying compatibility. Mixing 1.x and 2.x risks classpath failures.

### H. `DataJpaTest` Package in Boot 4

A project upgrades to Boot 4 and `org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest` fails to resolve. Was `DataJpaTest` removed?

**Answer:** No. Boot 4 modularized tests; the new import is `org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest`, paired with the matching test module/starter.

### I. `@Bean` and `@Container`

Does a `@Bean PostgreSQLContainer` method in `@TestConfiguration` need JUnit's `@Container`?

**Answer:** No. Spring Boot manages the container bean lifecycle; use `@ServiceConnection` to generate connection details.

### J. Static Container Cache

A JUnit container stops after Class A, and Class B reuses the Spring `ApplicationContext`. What is the symptom?

**Answer:** The datasource may point at a dead container's port. Align container lifetime and context caching instead of adding random sleeps.

### K. Dynamic Properties

A Boot 3.3 JPA slice uses `@DynamicPropertySource`. Should `Replace.NONE` still be set?

**Answer:** Yes, when preserving the container DB is required, because 3.3 defaults to `ANY`. Boot 3.4+ `NON_TEST` recognizes dynamic URLs in supported patterns, yet explicit `NONE` makes intent clear alongside vendor verification.

### L. Container Image Starts Successfully

Logs show `PostgreSQLContainer started`. Is that enough to prove repositories use PostgreSQL?

**Answer:** No. The `DataSource` may still have been replaced with H2; assert database metadata.

### M. H2 Migration Confidence

Does passing JPA `create-drop` on H2 prove Flyway PostgreSQL migrations work?

**Answer:** No. Use a Postgres container, real migrations, and schema validation.

### N. Docker Unavailable

A CI runner lacks Docker, 4 PostgreSQL tests skip via assumptions, and the job is green. Can you report "Postgres integration passed"?

**Answer:** No. Those are `NOT RUN`/`SKIPPED`; the job needs Docker provisioned or must fail as a blocker—critical integration gates must never stay silently green.

### O. JDBC vs. R2DBC

A `PostgreSQLContainer` can supply both `Jdbc` and `R2dbcConnectionDetails`. Does `@AutoConfigureTestDatabase` replace the R2DBC `ConnectionFactory` automatically?

**Answer:** No. That annotation targets JDBC `DataSource`; R2DBC test auto-configuration and drivers must be checked separately.

### P. Should H2 Be Removed Completely?

Both H2 slices and PostgreSQL integration tests have value. Must H2 be removed from the build to avoid accidental replacement?

**Answer:** No. Keep H2 for fast portable tests where appropriate; use `Replace` modes, `ConnectionDetails`, and metadata assertions to distinguish vendors clearly and prevent misdirected tests.

## 41. Pre-Merge Upgrade Checklist

- [ ] Know current and target Spring Boot versions/BOMs, with the matching migration guide.
- [ ] Compared `TestDatabase` `Replace` defaults across 3.3/3.4/3.5/4.x.
- [ ] Understand the differences between `ANY`/`AUTO_CONFIGURED`/`NON_TEST`/`NONE`.
- [ ] Fast H2 tests explicitly enforce their intended mode and metadata.
- [ ] PostgreSQL-specific tests assert `DatabaseProductName=PostgreSQL`.
- [ ] Never infer the active database solely from container-started logs.
- [ ] Verified `@Primary DataSource` handling if multiple datasources exist.
- [ ] Never assume `spring.datasource.url` always equals the active JDBC URL.
- [ ] `@ServiceConnection` has `spring-boot-testcontainers` in test dependencies.
- [ ] Typed containers or image-name factories are recognized properly.
- [ ] `GenericContainer` includes a `name` hint when the factory cannot infer from type.
- [ ] Avoided ambiguous combinations of dynamic JDBC props and service connections.
- [ ] Container lifecycle aligns with the TestContext cache without stopping prematurely.
- [ ] Distinguished `@DataJpaTest` and `@SpringBootTest` replacement behaviors.
- [ ] PostgreSQL JDBC driver is present on the test runtime classpath.
- [ ] Testcontainers 1.x artifacts are not mixed with 2.x modules.
- [ ] BOM manages versions instead of manually pinning mismatched versions.
- [ ] After a Boot 4 upgrade, relocated test annotation packages and modules are updated.
- [ ] CI has Docker runtime, permissions, and image access for container-based tests.
- [ ] Unavailable Docker does not report PostgreSQL tests as passing.
- [ ] Container image tag/digest and DB engine versions are pinned and documented.
- [ ] H2 is never used to prove PostgreSQL JSONB, locking, or partial indexes.
- [ ] Flyway/Liquibase migrations are tested explicitly against the matching DB dialect.
- [ ] Hibernate `create-drop` is never mistaken for a migration test.
- [ ] Zero production credentials or production DB URLs in tests.
- [ ] Test-owned DBs/rows roll back or clean up without affecting unrelated data.
- [ ] CI artifacts archive JUnit XML/HTML alongside dependency insights and relevant logs.
- [ ] Executed test counts do not drop to 0 due to tags, skips, or source mismatches.
- [ ] Context cache misses, container startups, and suite durations are measured.
- [ ] `TestConfig`/`ConnectionDetails` never leak into the production application.
- [ ] Startup errors are diagnosed from root cause rather than trial-and-error edits.
- [ ] A coordinated rollback plan covers versions, dependencies, and imports if needed.
- [ ] QA reports clearly distinguish code-reviewed vs. actually executed tests.

**Conclusion:** Upgrading Spring Boot or Testcontainers can silently change **the real database** a test runs against even when test logic is untouched. Spring Boot 3.3 defaults to `Replace.ANY`; from 3.4, `NON_TEST` preserves recognized container-backed test datasources. `@ServiceConnection` generates `JdbcConnectionDetails` and takes precedence over connection properties, yet does not replace container lifecycle ownership or bypass a manual `@Bean DataSource`. Meanwhile, Boot 3.5 manages **Testcontainers 1.21.4**, whereas Boot 4 and Testcontainers 2.x bring module and package changes requiring migration. The best defense against regressions is not guessing annotations until builds turn green, but **stating H2 vs. Postgres intent explicitly, aligning BOMs and imports, asserting database metadata, validating real migrations, and managing test-data and container lifecycles**.

### Official References

- Spring Boot 3.3 — AutoConfigureTestDatabase JavaDoc, `replace` default ANY: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html
- Spring Boot 3.5.16 — AutoConfigureTestDatabase JavaDoc, `replace` default NON_TEST: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html
- Spring Boot 3.5.16 — Replace enum, NON_TEST recognition patterns: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html
- Spring Boot 3.4 Release Notes — `@AutoConfigureTestDatabase` and containers: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes
- Spring Boot 3.5 — Testcontainers service connections, container beans and dynamic properties: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Boot 3.5 — Testing Spring Boot Applications, `@DataJpaTest`: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Managed dependency coordinates, Testcontainers 1.21.4: https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html
- Spring Boot 3.5 — JdbcConnectionDetails API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/JdbcConnectionDetails.html
- Spring Boot 3.5 — Docker Desktop/Testcontainers Docker API troubleshooting: https://docs.spring.io/spring-boot/3.5/how-to/testing.html
- Spring Boot 4 — DataJpaTest package change: https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/data/jpa/test/autoconfigure/DataJpaTest.html
- Spring Boot 4 — AutoConfigureTestDatabase package change: https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/jdbc/test/autoconfigure/AutoConfigureTestDatabase.html
- Testcontainers 2 — PostgreSQL module/artifact and API: https://java.testcontainers.org/modules/databases/postgres/
- Testcontainers — Managing versions with BOM: https://java.testcontainers.org/
- Spring Framework 6.2 — DynamicPropertySource: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dynamicpropertysource.html
- Spring Framework 6.2 — TestContext caching: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
