# `@AutoConfigureTestDatabase` and `DataSource` Replacement Policies in Spring Boot Test Slices

## Learning Objectives

Testing repositories/JDBC in Spring Boot usually requires a database to run SQL, create tables, and read/write data. For test slices such as `@DataJpaTest` or `@JdbcTest`, Spring Boot can **replace the `DataSource` configured for the application with an embedded database dedicated to testing**. This mechanism lets tests start fast without relying on an external database server, yet it can also cause tests to silently run on H2 instead of the PostgreSQL/MySQL engine you thought you were testing.

The **`@AutoConfigureTestDatabase`** annotation controls **whether the `DataSource` is replaced, what kind of replacement occurs, and which embedded database is used**. The rules **are not identical between Spring Boot 3.3 and 3.4+**, especially with Testcontainers.

After this lesson, you will be able to:

- Explain `DataSource` and "replacement" inside a Spring Boot test slice.
- Distinguish `Replace.ANY`, `Replace.AUTO_CONFIGURED`, `Replace.NONE`, and `Replace.NON_TEST` by **Spring Boot version**.
- Understand why `@DataJpaTest` and `@JdbcTest` normally use an embedded database, whereas `@SpringBootTest` does not automatically share the same replacement rule.
- Choose **H2 test database**, a custom configured database, or **Testcontainers** based on goals and SQL compatibility.
- Write a runnable **Java 17 + Spring Boot 3.3.5 + Gradle + JUnit Jupiter** project verifying both replacing a DataSource and preserving a DataSource.
- Verify the **database actually in use** via JDBC metadata, rather than trusting `application-test.yml` or logs alone.
- Diagnose missing embedded drivers, wrong DB ports, dialect mismatches, migrations/transactions, multiple DataSources, and accidental connections to production.

**Core takeaway:** `replace = NONE` does not create a new DataSource; it merely **prevents Spring Boot from replacing the DataSource** already configured for the test context. To test PostgreSQL, you still have to actually provide PostgreSQL, configure the connection, and verify the test used the right DB.

## 1. Why Do Test Slices Replace the `DataSource`?

In JDBC/JPA, a `javax.sql.DataSource` is the abstraction providing JDBC connections, typically backed by a connection pool such as HikariCP. A service or repository obtains a `Connection` from the `DataSource`, executes SQL, and returns results.

Suppose the application has configuration:

~~~properties
spring.datasource.url=jdbc:postgresql://db.example.internal:5432/shop
spring.datasource.username=shop_app
spring.datasource.password=...
~~~

This is an **illustrative configuration**, not values to use in tests; never place production passwords inside tests or repositories. If `@DataJpaTest` connected directly to a real production database by default, tests could alter sensitive data or depend on unstable external infrastructure.

Therefore, in JDBC/JPA test slices, Boot provides a **test database auto-configuration** mechanism:

~~~text
Test class @DataJpaTest / @JdbcTest
             |
             v
Spring Boot creates test ApplicationContext with DataSource
             |
             +-- DataSource already configured via properties / @Bean
             |
             v
TestDatabaseAutoConfiguration
             |
             +-- Does the replacement policy allow replacement?
             |       |
             |       +-- Yes -> find embedded driver, build test DataSource
             |       |          (H2/HSQLDB/Derby when suitable)
             |       |
             |       +-- No  -> keep the configured DataSource
             |
             v
Repository/JdbcTemplate/JPA talks to the effective DataSource
             |
             v
@Test verifies SQL/data on that DB
~~~

This mechanism **swaps the `DataSource` bean selection inside the test context**; it does not edit `application.yml` or reconfigure any production DB server. When running against an embedded database, passing tests prove behavior against that embedded database, **not necessarily production SQL/dialect behavior**.

A test passing on H2 may still fail on PostgreSQL due to column types, native SQL, collations, indexes, constraints, or transaction semantics. Conversely, standard CRUD on small schemas works nicely on H2 for fast feedback during development.

## 2. Which Test Slices Are Involved?

| Annotation/test type | Primary scope | Default database behavior |
| --- | --- | --- |
| `@DataJpaTest` | JPA entities, Spring Data JPA repositories, Hibernate, `TestEntityManager` | May replace DataSource with an embedded test DB; typically transactional and rolls back after each test |
| `@JdbcTest` | `DataSource`, `JdbcTemplate`, SQL/JDBC | May replace DataSource with an embedded test DB; typically transactional and rolls back |
| `@DataJdbcTest` | Spring Data JDBC repositories, relational mapping | Has a similar test database mechanism |
| `@JooqTest` | jOOQ `DSLContext` and SQL | Normally keeps configured DataSource; can use `@AutoConfigureTestDatabase` to request replacement |
| `@SpringBootTest` | Broader Spring Boot ApplicationContext | **Does not apply `@DataJpaTest`'s embedded replacement policy by default**; to swap, configure a test DB explicitly or add `@AutoConfigureTestDatabase` appropriately |
| `@WebMvcTest` | Controller/MVC serialization, validation | Does not aim to create JPA/DataSource; usually mocks service boundary |
| Plain JUnit unit test | Java logic without Spring | No Spring DataSource; `@AutoConfigureTestDatabase` is not needed |

For example, `@DataJpaTest` usually loads only relevant JPA components without loading every `@Service`/`@Controller` in the app. `@JdbcTest` does not test Hibernate entity mapping; it focuses directly on JDBC. The DB replacement annotation is **a test-infrastructure choice**, not something that turns a slice into a full integration test.

### Correct Imports for Spring Boot 3.3.x

~~~java
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase.Replace;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
~~~

These are illustrative imports; in a complete Java program, include only the imports actually used. Spring Boot 4 reorganized several test modules/packages, so **do not copy Boot 3.x imports into Boot 4** without checking Javadoc for your version.

## 3. Replacement Policies: Understanding Each `Replace` Value

`@AutoConfigureTestDatabase` has a `replace` attribute accepting the enum `AutoConfigureTestDatabase.Replace`.

### `Replace.ANY`

~~~java
@AutoConfigureTestDatabase(replace = Replace.ANY)
~~~

Allows **replacing the DataSource whether created by auto-configuration or declared manually via `@Bean`**, subject to test database auto-configuration rules and constraints. This is the aggressive option, suitable when you want to ensure the slice uses a selected embedded DB instead of the application's DataSource.

In Spring Boot **3.3.x**, `Replace.ANY` is the **default value** of `@AutoConfigureTestDatabase`. Test slices carrying this annotation also tend to use an embedded database when a driver is available. This is crucial when pairing Testcontainers with Boot 3.3: **even a test-configured container DataSource can be replaced with an embedded DB** unless `Replace.NONE` is set.

### `Replace.AUTO_CONFIGURED`

~~~java
@AutoConfigureTestDatabase(replace = Replace.AUTO_CONFIGURED)
~~~

Considers replacing only a DataSource that was **auto-configured by Spring Boot**, leaving a manually declared user DataSource intact in supported cases. This is not "replace only if it is production"; the criterion is **the origin of the bean definition**, not whether the database is dangerous or safe.

Be careful: if you use `spring.datasource.url` to point at Postgres, the Hikari `DataSource` can still be created by **Boot auto-configuration**. Hence `AUTO_CONFIGURED` can replace a DataSource connecting to PostgreSQL; **do not rely on it to guarantee keeping Testcontainers or a JDBC URL configuration** without verifying the exact auto-configuration path.

### `Replace.NONE`

~~~java
@AutoConfigureTestDatabase(replace = Replace.NONE)
~~~

**Does not replace** the application/configured DataSource with an embedded database. Typically used when you need to:

- Verify migrations/schemas/queries on real PostgreSQL or MySQL in a test environment.
- Use Testcontainers without having it replaced by H2.
- Preserve a test DataSource explicitly configured via properties, `@DynamicPropertySource`, `@ServiceConnection`, or test config.
- Test the behavior of the chosen datasource/pool/driver rather than isolated SQL logic.

**`NONE` does not create a Postgres container, does not grant DB access, does not rewrite URLs into test JDBC URLs, and does not guarantee production won't be touched.** If active properties currently point to a production DB, the test **can connect to production**. Ensure fixtures, credentials, network isolation, and JDBC URL checks are in place.

### `Replace.NON_TEST` — Added in Spring Boot 3.4

~~~java
@AutoConfigureTestDatabase(replace = Replace.NON_TEST)
~~~

Starting in **Spring Boot 3.4**, `NON_TEST` was added and became the new default value of the annotation: replace the DataSource unless it is **auto-configured and already recognized as connecting to a test database**.

Signals of a test database recognized by Boot 3.4+ include, depending on version/configuration:

- `ContainerImageMetadata` originating from Testcontainers `@ServiceConnection` or Docker Compose connection metadata.
- A JDBC URL configured via `@DynamicPropertySource`.
- Testcontainers JDBC URLs with the `jdbc:tc:...` syntax.

As a result, a `@DataJpaTest` using an auto-configured test container can **keep** it without needing `replace = NONE`. Understand the limits, though:

- `NON_TEST` **does not exist in Boot 3.3.x**. Writing `Replace.NON_TEST` on Boot 3.3 **will not compile**.
- The "test DB" check is not simply whether the database name contains `test` or the host is `localhost`.
- Protection mainly applies when the DataSource is **auto-configured** and Boot has enough metadata to recognize it; a manually declared `@Bean` DataSource may need a more explicit policy.
- If your explicit decision is "**strictly keep the specified test DataSource**," `Replace.NONE` remains an unambiguous, review-friendly way to state it.
- Read the Javadoc for your exact 3.4/3.5 release because test-database detection may evolve across versions.

### Version Summary Table

| Policy | Spring Boot 3.3.x | Spring Boot 3.4+ | Main meaning |
| --- | --- | --- | --- |
| `ANY` | Yes; **default in 3.3** | Yes | Allows replacing auto-configured or manually defined DataSources |
| `AUTO_CONFIGURED` | Yes | Yes | Replaces only DataSources created by auto-configuration |
| `NONE` | Yes | Yes | Does not replace the configured DataSource |
| `NON_TEST` | **Not available** | Yes; **default from 3.4** | Preserves auto-configured DataSources Boot recognizes as test DBs |

No single claim like "`@DataJpaTest` always replaces every DataSource" holds across all Spring Boot versions. **Always state the version before explaining default behavior.** In projects where modules upgrade unevenly, use an explicit enum value to make intent clear and inspect the actual dependency tree.

## 4. `connection`: Which Embedded Database Replaces It?

Another attribute on the annotation is `connection`, accepting `EmbeddedDatabaseConnection`:

~~~java
@AutoConfigureTestDatabase(
    replace = Replace.ANY,
    connection = EmbeddedDatabaseConnection.H2)
~~~

Traditional embedded database choices in Spring Boot 3.x include H2, HSQLDB, and Derby, plus `NONE` to let the mechanism auto-detect on the classpath. **`connection = EmbeddedDatabaseConnection.NONE` is not the same as `replace = Replace.NONE`**:

- `replace = NONE` = **do not replace the DataSource**.
- `connection = NONE` = **do not force a specific embedded engine**; Boot can auto-detect a suitable engine when replacement runs.

To replace with H2, the **H2 JDBC driver must be on the test runtime classpath**. The annotation does not download libraries from Maven for you. If no compatible H2/HSQLDB/Derby driver is present when the policy demands an embedded DB, context startup can fail.

Common scenarios:

| Configuration | Expected outcome |
| --- | --- |
| `replace = ANY`, H2 present at test runtime | Target DataSource is replaced with embedded H2 |
| `replace = ANY, connection = H2` without H2 driver | Cannot build H2 DataSource; context may fail |
| `replace = NONE` with `spring.datasource.url=jdbc:postgresql:...` | Preserves DataSource per properties; requires PostgreSQL running |
| `replace = NONE` with test-declared in-memory H2 URL | Preserves **that exact H2 instance**; still embedded, yet **not replaced** |
| `replace = AUTO_CONFIGURED` with manual DataSource | Manual DataSource does not belong to auto-configured replacement group |
| `replace = NON_TEST` on Boot 3.3.x | Compile error because enum constant does not exist |

Choose the embedded database based on **what you want to verify**: generic SQL and simple CRUD may suit H2; mapping/native SQL/DB-specific features require the matching database engine.

## 5. Runnable Demo: Verifying Replacement Policy via JDBC Metadata

This example uses **Spring Boot 3.3.5**, **Java 17**, **Gradle Groovy DSL**, `@JdbcTest`, and H2. The two test classes initialize **two different test ApplicationContexts**:

- Class A sets the JDBC URL to `jdbc:h2:mem:configureddb`, yet **`Replace.ANY`** instructs Boot to **replace** it with an embedded H2 instance chosen/created by test auto-configuration.
- Class B sets the JDBC URL to `jdbc:h2:mem:keptdb` and **`Replace.NONE`**, so Boot must **keep** the DataSource auto-configured from `keptdb`.

Both use H2 so the demo **requires no PostgreSQL, Docker, or external service**. Therefore Class B proves only that "`NONE` keeps the configuration," **not that real PostgreSQL is used**. That is a crucial distinction.

### 5.1. File Structure

~~~text
test-datasource-policy-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/testing/
    │   └── JdbcTestApplication.java
    └── test/java/com/example/testing/
        ├── ReplacedDataSourceJdbcTest.java
        └── PreservedDataSourceJdbcTest.java
~~~

The demo project focuses on **running tests**, without needing to launch the app without a test DataSource via `bootRun`. H2 is a **test-only dependency** and must not be placed into production artifacts inadvertently.

**`settings.gradle`**

~~~groovy
rootProject.name = 'test-datasource-policy-demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**Configuration explanation:**

- `spring-boot-starter-jdbc` provides JDBC support, `JdbcTemplate`, transaction infrastructure, and related JDBC `DataSource` auto-configuration when a driver exists.
- `spring-boot-starter-test` provides Spring TestContext and JUnit Jupiter.
- `testRuntimeOnly 'com.h2database:h2'` limits H2 to **test runtime** so the H2 driver does not leak into the demo module's production runtime.
- `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'` lets Gradle/JUnit Platform execute tests cleanly.
- `useJUnitPlatform()` tells Gradle to run JUnit Jupiter tests.
- The Spring Boot 3.3.5 BOM manages dependency versions; do not pin mismatched H2/JUnit versions manually.

Requires Java 17 and a compatible Gradle Wrapper. If the repo already has `gradlew`, use the repo's version. If creating fresh, you can bootstrap the wrapper with an installed Gradle via `gradle wrapper --gradle-version 8.8 --distribution-type bin` for the demo project. Commit the wrapper files to the repository; do not hand-craft `gradle-wrapper.jar`.

### 5.2. Root Class Helping the Slice Locate Boot Application Configuration

**`src/main/java/com/example/testing/JdbcTestApplication.java`**

~~~java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JdbcTestApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdbcTestApplication.class, args);
    }
}
~~~

For `@JdbcTest`, Spring Boot still needs to find `@SpringBootConfiguration` to bootstrap the context. The `@SpringBootApplication` class provides that root, though **the test slice does not auto-load all services/controllers like `@SpringBootTest`**. Because the project supplies no production JDBC URL/driver to run standalone, the `main` method serves only as bootstrap metadata for tests; the exercise is verified via the `test` task.

### 5.3. Test A — `ANY` Replaces the DataSource Despite a Configured JDBC URL

**`src/test/java/com/example/testing/ReplacedDataSourceJdbcTest.java`**

~~~java
package com.example.testing;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.jdbc.EmbeddedDatabaseConnection;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JdbcTest(properties = {
        "spring.datasource.url="
            + "jdbc:h2:mem:configureddb;DB_CLOSE_DELAY=-1"
})
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY,
        connection = EmbeddedDatabaseConnection.H2)
class ReplacedDataSourceJdbcTest {

    @Autowired
    private DataSource dataSource;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void anyReplacesConfiguredDataSourceWithEmbeddedH2()
            throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            String jdbcUrl = connection.getMetaData().getURL();

            assertTrue(jdbcUrl.startsWith("jdbc:h2:mem:"), jdbcUrl);
            assertFalse(jdbcUrl.contains("configureddb"), jdbcUrl);
        }
    }

    @Test
    void replacedDataSourceIsUsableByJdbcTemplate() {
        Integer result = jdbcTemplate.queryForObject(
                "select 3 + 4", Integer.class);

        assertNotNull(result);
        assertEquals(7, result.intValue());
    }
}
~~~

**What to observe:**

- `spring.datasource.url` has a configured value, yet `replace = ANY` requests replacement.
- Because `connection = H2` and H2 is available at test runtime, Boot builds an **embedded H2 test DataSource**.
- The actual URL from `Connection.getMetaData().getURL()` starts with `jdbc:h2:mem:`, yet **does not contain `configureddb`** — the originally configured database name. Generated H2 instance names can vary, so the test **does not hardcode a random name**.
- The query `select 3 + 4` runs through `JdbcTemplate` and returns 7, proving the DataSource works, not just that it was injected.
- The test needs no open TCP port for in-memory H2; this is neither an HTTP endpoint nor a separate running database server.

The test data here is intentionally simple to prove the **replacement policy**. It does not yet exercise complex SQL, schema migrations, or repository persistence.

### 5.4. Test B — `NONE` Keeps the Test-Configured DataSource

**`src/test/java/com/example/testing/PreservedDataSourceJdbcTest.java`**

~~~java
package com.example.testing;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JdbcTest(properties = {
        "spring.datasource.url="
            + "jdbc:h2:mem:keptdb;DB_CLOSE_DELAY=-1"
})
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class PreservedDataSourceJdbcTest {

    @Autowired
    private DataSource dataSource;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void nonePreservesTheExplicitJdbcUrl() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            String jdbcUrl = connection.getMetaData().getURL();

            assertTrue(
                    jdbcUrl.startsWith("jdbc:h2:mem:keptdb"),
                    jdbcUrl);
        }
    }

    @Test
    void preservedDataSourceStillRunsQueries() {
        Integer result = jdbcTemplate.queryForObject(
                "select 1 + 2", Integer.class);

        assertNotNull(result);
        assertEquals(3, result.intValue());
    }
}
~~~

**What to observe:**

- `Replace.NONE` preserves the JDBC URL specified by the test.
- The actual URL must start with `jdbc:h2:mem:keptdb`.
- The test still uses **H2**, because **the test itself** configured H2 as the DataSource. "NONE" **does not mean using a production DB**.
- The simple query returns 3, proving the connection works.

The two classes have **two distinct test configurations**—one replacing the DataSource, one preserving it—so tests should not assume they share the same context. `JdbcTest` normally runs each test method in a transaction and rolls back when finished, yet transactions do not protect you if `DataSource` accidentally points to production and migrations/DDL or side effects outside the transaction already ran. Always verify the target DB before feeding sensitive data into a test.

### 5.5. Running the Tests and Expected Results

At the project root with Gradle Wrapper:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run only the replacement test:

~~~bash
./gradlew test --tests 'com.example.testing.ReplacedDataSourceJdbcTest'
~~~

Run only the preserved DataSource test:

~~~bash
./gradlew test --tests 'com.example.testing.PreservedDataSourceJdbcTest'
~~~

Each class has **2 `@Test` methods**, for a total of **4 JUnit test runs**. All four are expected to pass with the code/config described. There is no `System.out.println` and no JDBC URL printed to stdout, so **there is no fixed business stdout**. When Gradle succeeds, it prints `BUILD SUCCESSFUL`. If the test task is `UP-TO-DATE` or `FROM-CACHE`, cached results may be reused; to force re-execution while diagnosing, run `./gradlew test --rerun-tasks`.

Reports are typically located at:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.testing.ReplacedDataSourceJdbcTest.xml
    └── TEST-com.example.testing.PreservedDataSourceJdbcTest.xml
~~~

In multi-module projects, paths reside inside the `build` directory of the module containing the test. If a test fails with `Failed to load ApplicationContext`, read the root cause related to drivers/DataSource before changing assertions.

## 6. Testing `@DataJpaTest` with PostgreSQL Testcontainers

The earlier demo used H2 to avoid needing Docker, yet many systems must verify **real PostgreSQL SQL**: `jsonb`, native queries, indexes/constraints, transaction isolation, sequences, timestamp/UUID types, or dialect-specific migrations. In those cases, **Testcontainers** can run an ephemeral PostgreSQL instance in the test environment.

Idea:

~~~text
JUnit / @DataJpaTest
       |
       +-- PostgreSQLContainer ("postgres:16-alpine")
       |           |
       |           +-- Dynamic JDBC URL/credentials, no hardcoded port
       |
       +-- Spring Boot @ServiceConnection / @DynamicPropertySource
       |           |
       |           v
       |       DataSource connects to container
       |
       +-- @AutoConfigureTestDatabase(replace = NONE)
                   |
                   v
         Does not swap to an H2 test DB
                   |
                   v
             JPA repositories run on real PostgreSQL
~~~

### 6.1. Additional Dependencies in Spring Boot 3.3.x

If the project already has Spring Boot `spring-boot-starter-data-jpa` and `spring-boot-starter-test`, typical Testcontainers additions are:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}
~~~

This is an **addition to an existing Gradle project with JPA, the Spring Boot plugin, and dependency management**; not a standalone build file. Versions must align with the project's Spring Boot version. Testcontainers requires a working Docker/container runtime in the test execution environment.

### 6.2. Annotation Structure of the Integration Test

~~~java
@DataJpaTest
@Testcontainers
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class OrderRepositoryPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    private OrderRepository repository;

    // @Test queries/constraints to verify on PostgreSQL.
}
~~~

This is a **directional snippet, not a standalone compilable class**: you must define `Order`, `OrderRepository`, and Testcontainers, Spring Data JPA, JUnit, and Boot Test imports, plus appropriate schema migrations/DDL. `@ServiceConnection` (Boot Testcontainers) supplies connection details from the container; in Spring Boot 3.3, `replace = NONE` prevents the test DataSource from being overwritten by default embedded replacement.

**Important version note:** From Spring Boot 3.4+, the default `NON_TEST` policy includes logic recognizing certain Testcontainers DataSources, so `replace = NONE` may not be needed in many auto-configured cases where detection succeeds. Still, when your explicit goal is **never replacing the DataSource** under any implicit rule, declaring `NONE` makes intent unmistakable and stays compatible across 3.3/3.4+.

### 6.3. When Using `@DynamicPropertySource`

Another pattern has Testcontainers supply JDBC URL/user/password via dynamic properties:

~~~java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

This snippet requires an initialized `postgres` container variable and imports; it is not a standalone test. In Boot 3.3, even when dynamic properties point straight to PostgreSQL, `@DataJpaTest`'s default `ANY` replacement can **swap the DataSource to H2**, so add `@AutoConfigureTestDatabase(replace = NONE)`. From 3.4 onward, an auto-configured datasource whose URL comes from `@DynamicPropertySource` is one pattern `NON_TEST` can recognize as a test DB.

Do not combine both `@ServiceConnection` and all the same dynamic properties for the same purpose **unnecessarily**. Pick one clear container-wiring mechanism suited to your version and keep the configuration easy to verify.

### 6.4. Checking Which Database Is Actually Used

A passing repository test **does not prove PostgreSQL** if the SQL also works on H2 and the datasource was replaced. You can assert JDBC metadata with a diagnostic check:

~~~java
try (Connection connection = dataSource.getConnection()) {
    String product = connection.getMetaData()
            .getDatabaseProductName();

    assertEquals("PostgreSQL", product);
}
~~~

This snippet needs `dataSource`, `assertEquals`, `Connection`, and proper imports. Use `getDatabaseProductName()` as a clean infrastructure assertion without printing credentials or full connection URLs to CI logs. When testing vendor-specific migrations, confirm the engine matches and the test DB schema is properly initialized.

## 7. Multiple `DataSource` Beans: Limits You Should Know

`@AutoConfigureTestDatabase` **does not mean every DataSource in the context will be replaced**. Per the Spring Boot 3.3 Javadoc, when **multiple `DataSource` beans** exist, test database auto-configuration only **considers the `@Primary DataSource`**.

For example:

~~~java
@Configuration
class MultiDataSourceConfig {

    @Bean
    @Primary
    DataSource ordersDataSource() {
        // ...
    }

    @Bean
    DataSource auditDataSource() {
        // ...
    }
}
~~~

This is an **illustrative snippet** without implementations. If a test requires both `ordersDataSource` and `auditDataSource` to function properly, do not assume `@AutoConfigureTestDatabase(replace = ANY)` automatically creates two embedded databases or replaces both. You must configure each datasource/transaction manager/repository scan explicitly and verify both via qualifiers, metadata, or separate tests.

### `@Primary` and `@Qualifier` Differ from Replacement Policy

- `@Primary` resolves **bean selection by type** when multiple `DataSource` candidates exist.
- `@Qualifier("auditDataSource")` selects a specific bean at an injection point.
- `@AutoConfigureTestDatabase` applies the test DataSource replacement policy to the **target bean scope**, not as a rule governing every JDBC connection across the entire application.
- `spring.main.allow-bean-definition-overriding` controls registering bean definitions with duplicate **names**, **not** `Replace.ANY/NONE`.

If a repository is explicitly wired to `auditDataSource` and its own transaction manager, embedded replacement affecting only the primary DataSource can leave that repository still pointing at a real DB. This scenario requires **verifying each DataSource's infrastructure** and guarding test environment credentials and network isolation.

## 8. Safe Testing Policy: Never Connect to Production Accidentally

In repository integration tests, a connection misconfiguration can be worse than a failing test: tests can **delete, modify, or migrate real data**. Design the infrastructure policy before picking annotations.

### Mandatory Safety Checklist

1. **Dedicated database:** use in-memory H2 or ephemeral container DBs. Never use production connection strings/credentials.
2. **Test credentials:** dedicated account with minimum necessary privileges; never embed real passwords in committed `application-test.yml`.
3. **Network isolation:** CI can reach only provisioned test databases/containers, with no accidental route to production.
4. **Verify runtime DataSource:** when a test requires PostgreSQL, assert the database product name; if needed, inspect a sanitized JDBC URL confirming no production host.
5. **Schema/namespace:** use a dedicated test schema/database with a deterministic name; reset data per fixture.
6. **Migrations:** if using Flyway/Liquibase, run only on a verified test DB with migrations valid for that engine.
7. **Transactions:** understand that slice rollback usually protects DML inside the test transaction, without substituting for network isolation; DDL and out-of-transaction side effects may not roll back as hoped.
8. **No secrets in logs:** never print full JDBC URLs containing credentials/tokens; avoid dumping datasource properties in uncontrolled CI logs.

If a test only checks domain logic without SQL, **do not create a DataSource**. Plain Java unit tests with constructor-injected dependencies are safer, faster, and clearer.

## 9. Embedded H2 vs. Production DB: Scope of Evidence

| Characteristic | Embedded H2/HSQLDB/Derby | PostgreSQL/MySQL in Testcontainers |
| --- | --- | --- |
| Container runtime required | No | Yes, typically needs Docker or a compatible runtime |
| Setup time | Usually fast | Includes container and image startup time |
| SQL dialect matches production | Not guaranteed | Higher fidelity when matching DB engine/version |
| Engine-specific `jsonb`, arrays, enums | May be unsupported or differ semantically | Tested directly on the right engine |
| Migrations and indexes/constraints | May differ from production | Closer to production |
| Isolation | Good when each test context has an isolated DB | Good when containers/schemas/fixtures are managed independently |
| Native query reliability | Limited by dialect | Better with the exact DB |
| Best suited for | Simple CRUD, JPA/JDBC smoke tests, fast feedback | Critical SQL integration, migrations, constraints, vendor-specific behavior |

**There is no rule that "every test must run PostgreSQL."** A sound strategy usually layers tests: unit tests for domain logic, slices with embedded DBs for fast checks, and a set of Testcontainers integration tests for behavior tied to the real DB engine.

A passing H2 test **is not wrong** if the goal is merely checking compatible mappings or basic CRUD; the mistake is **falsely claiming** H2 tests verified production DB queries or migrations.

### Does H2 Compatibility Mode Replace Real PostgreSQL?

H2 offers compatibility modes for certain dialects, yet it does not fully reproduce PostgreSQL's SQL planner, isolation, extensions, collations, index behavior, data types, or migration semantics. Use compatibility mode only as a limited test aid, never claiming it equals the production DB. For vendor-specific features, test on the corresponding engine.

## 10. Transactions, Rollback, and Database Lifecycle

### `@DataJpaTest` and `@JdbcTest` Are Usually Transactional

In Spring Boot test slices, `@DataJpaTest`/`@JdbcTest` configurations typically wrap each test in a transaction that rolls back by default. This keeps DML tests more independent when the same context/database is reused.

However, rollback **does not automatically guarantee**:

- That you connected to the right test DB.
- That DDL/migrations/triggers acting outside the transaction revert.
- That side effects through external services (HTTP, message brokers, email) revert.
- That HTTP tests running on a separate server thread roll back with the test thread's transaction.
- That every test starts with a brand-new database; context caching can reuse the DataSource.
- That no data remains if a test commits explicitly, changes propagation, or writes state outside the transaction.

`@Transactional` and database replacement solve **two different problems**: one manages transaction boundaries, the other determines the actual DataSource. Do not use one as a substitute for the other.

### Context Caching and Embedded Databases

Spring TestContext can cache contexts across multiple test classes with matching configurations. When in-memory H2 and its connection pool remain attached to the cached context, the database can stay alive across multiple tests. `DB_CLOSE_DELAY=-1` in a JDBC URL can also keep an H2 DB alive until JVM shutdown even after connections close.

Therefore:

- Never write Test A to insert data that Test B relies on unless it is an explicit shared fixture.
- Reset fixtures or use `@Sql`, repository cleanup, and proper transactions.
- Do not treat `@DirtiesContext` as a default data-reset tool: it forces contexts to rebuild and slows tests down.
- When test DBs have multiple schemas or require strict isolation, design isolation at the DB level instead of relying purely on Spring context caching.

### Is Using `@Sql` Appropriate?

`@Sql` can run scripts to prepare test data in Spring TestContext, yet it is safe only when you know **which DataSource** the script runs against and under which transaction mode. With multiple DataSources, the annotation/script may need to specify the exact dataSource/transaction manager. A script containing `DELETE FROM orders` must never run before confirming the datasource is not production.

## 11. `@SpringBootTest` with `@AutoConfigureTestDatabase`

`@SpringBootTest` loads the Boot application context, differing from test slices: it **does not bring in all test database replacement auto-configurations by default** like `@DataJpaTest`. If you want a full context to use an embedded DB, you can add `@AutoConfigureTestDatabase` or configure a test datasource explicitly:

~~~java
@SpringBootTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY,
        connection = EmbeddedDatabaseConnection.H2)
class ApplicationWithEmbeddedDbTest {
    // @Autowired DataSource / services...
}
~~~

Illustrative snippet requiring imports and matching app config. In applications with multiple databases, `@ConfigurationProperties`, migrations, or customized JDBC wiring, adding the annotation does not magically fix every dependency: inspect the actual DataSource. In large codebases, using explicit test profiles and container DBs is usually clearer than trying to swap data in a full context without knowing which infrastructure is active.

### When NOT to Use This Annotation?

- Pure Java unit tests without a Spring context.
- `@WebMvcTest` controller tests that mock services and never touch repositories/JDBC.
- Tests verifying only Jackson/validation with no DB dependency.
- R2DBC modules using `ConnectionFactory` rather than JDBC `DataSource`. `@AutoConfigureTestDatabase` targets JDBC DataSources; R2DBC has its own policies and auto-configurations—do not assume this annotation replaces reactive connection factories.

## 12. `spring.test.database.replace` and Configuration via Properties

`@AutoConfigureTestDatabase` maps to the `spring.test.database` property namespace. You may encounter `spring.test.database.replace` in Boot test environments, for example:

~~~properties
spring.test.database.replace=NONE
~~~

**Do not place this property in production configuration** as a way to control runtime datasources. It belongs to **test database auto-configuration**; production should configure datasources, drivers, and connection pools per deployment contracts.

However, annotation/meta-annotations on test slices, property mapping, and default values interact differently by version. When unambiguous behavior is needed on a specific test, **declaring `@AutoConfigureTestDatabase(replace = Replace.NONE)` directly** on the class lets reviewers read the policy immediately without hunting through multiple property files.

### Do Not Confuse with Bean Definition Overriding

`@AutoConfigureTestDatabase(replace = ANY)` and `spring.main.allow-bean-definition-overriding=true` are not two ways of doing the same thing:

- Test database replacement is Boot's mechanism for **selecting/swapping the DataSource in the test context** according to policy.
- Bean definition overriding is a `BeanFactory` setting allowing a definition with the **same name** to overwrite another, carrying its own risks.
- `@Primary` and `@Qualifier` govern **candidate resolution by type/metadata**.

If the test DataSource is not getting picked up, look at **test database auto-configuration, how the DataSource is configured, names/types/qualifiers, and Boot version**, instead of flipping on global bean overriding out of luck.

## 13. Common Errors and Resolutions

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Test meant to use PostgreSQL actually uses H2 | Boot 3.3 `@DataJpaTest` defaults to `Replace.ANY` | Use `Replace.NONE` and check metadata |
| `Replace.NON_TEST` fails to compile | Project uses Boot 3.3 or older | Use `NONE`/`ANY`/`AUTO_CONFIGURED` available in that version |
| Boot 3.4+ still replaces manual DB | `NON_TEST` detection relies on auto-configuration + test DB metadata | Use `NONE` if preserving the DataSource is mandatory |
| `Failed to replace DataSource with an embedded database` | Missing H2/HSQLDB/Derby driver on test runtime | Add test runtime driver or change policy/connection appropriately |
| `Cannot determine a suitable driver class` | Datasource URL/driver missing or driver absent from classpath | Check JDBC URL, dependencies, and test profile |
| `Connection refused` to DB | Test kept DataSource, but DB server/container is not ready | Start the test DB properly; verify host/port and lifecycle |
| `FATAL: database does not exist` | Wrong test DB URL/schema | Create the right test DB and use test credentials |
| Hibernate fails with SQL syntax error | H2 dialect differs from PostgreSQL or migration incompatible | Run integration tests on the matching production engine |
| `No qualifying bean of type DataSource` | Context lacks datasource config or slice skipped expected bean | Check test slice, auto-config, driver, and bean registration |
| Multiple DataSources test the wrong DB | Only the primary DataSource is considered by replacement | Configure each DataSource/qualifier and assert each JDBC URL |
| Tests pass individually, fail as a suite | Database state or context cache/shared fixtures | Clean up data, avoid cross-test state, check transactions |
| Enabling `replace = NONE` makes test hit production | DataSource uses real production config | Forbid production credentials/network; use dedicated test URL |
| Tests pass yet production migration fails | Tested only H2, not vendor SQL | Add Testcontainers migration/repository integration tests |
| Fast unit tests turn slow | Loading DB/containers unnecessarily | Separate domain unit tests; keep DB tests in their own layer |
| `@SpringBootTest` does not auto-use H2 | Full context lacks slice database replacement by default | Configure test DB explicitly or use appropriate annotation |
| Testcontainers created without container connection | Missing `@ServiceConnection`/`@DynamicPropertySource`/dependency | Wire container to datasource auto-config per your Boot version |

### Step-by-Step Diagnostic Process

1. **Identify the Boot version:** print/inspect the dependency tree to check whether `NON_TEST` exists; do not rely on blogs from another version.
2. **Identify the test annotation:** `@DataJpaTest`, `@JdbcTest`, `@SpringBootTest`, or something else? Is replacement active?
3. **Identify the effective policy:** `ANY`, `AUTO_CONFIGURED`, `NONE`, or `NON_TEST`. Is it overridden on the test class?
4. **Check the embedded driver:** is H2/HSQLDB/Derby on the test runtime classpath?
5. **Inspect the runtime DataSource:** check JDBC `getMetaData().getURL()`/`getDatabaseProductName()` when needed, **without logging secrets**.
6. **Check container/migrations:** is the container running, DB ready, schema valid, and credentials test-only?
7. **Read the root cause:** `Failed to load ApplicationContext` is only the outer wrapper; inner exceptions usually point to driver, URL, DDL, or query issues.
8. **Evaluate the test goal:** do you need the real engine or just basic CRUD/JDBC? Adjust the test level instead of altering production config for an incomplete test setup.

## 14. Process for Choosing a Replacement Policy in Your Project

Use the following decision table as a starting point, then verify with actual tests:

| Goal | Example | Recommended policy |
| --- | --- | --- |
| Test basic SQL, H2 acceptable | `@JdbcTest` with H2 test runtime | `ANY` or version-appropriate default |
| Test JDBC/JPA on a specific test-chosen H2 URL | `spring.datasource.url=jdbc:h2:mem:chosen` | `NONE` if keeping that exact URL matters |
| Test Hibernate/JPA/native queries on PostgreSQL Testcontainers, Boot 3.3 | `@DataJpaTest` + container | **`NONE`** |
| Test Testcontainers, Boot 3.4+ | Auto-configured DataSource recognized as test DB | Default `NON_TEST` usually works; `NONE` for explicit clarity |
| Replace any DataSource with an embedded DB | Test does not care about the original DB | **`ANY`**, with H2/HSQLDB/Derby driver |
| Replace only Boot auto-configured DataSources | Avoid replacing a manually declared DataSource | `AUTO_CONFIGURED` |
| Test multiple custom DataSource beans | Primary + named DataSources | Configure and test each bean individually; annotation won't replace all |
| Test full integration with real DB engine | `@SpringBootTest` + Testcontainers | Configure Testcontainers explicitly; usually **do not want embedded replacement** |
| Test logic not needing a DB | Domain service/validator | No annotation; plain Java unit test |

Pick the policy based on **the evidence you need to gather**, not merely the goal of "making tests green." If a test exercises complex SQL yet Boot keeps swapping it to H2, a passing test says little about PostgreSQL. If a test just verifies arithmetic pricing, spinning up a PostgreSQL container adds needless complexity.

## 15. Practice Exercises

**Exercise A — Verify real replacement:** In the demo, run `ReplacedDataSourceJdbcTest`. Notice the test does not hardcode the generated H2 name; assertions only confirm the right DB type and **that the URL no longer contains `configureddb`**. Change `replace = ANY` to `NONE` and predict that `assertFalse(jdbcUrl.contains("configureddb"))` will fail. Revert afterward.

**Exercise B — Preserve configuration:** In `PreservedDataSourceJdbcTest`, change the annotation's JDBC URL to `jdbc:h2:mem:anotherdb;DB_CLOSE_DELAY=-1` while keeping the expected `keptdb`. The test should fail. This shows the assertion detects which DB is actually used rather than just running any arbitrary query.

**Exercise C — Simulate a missing embedded driver:** On a separate test branch, remove the H2 dependency while keeping `replace = ANY, connection = H2`. Predict that the context fails to build the embedded datasource; read the root cause and revert. Never alter business source code to hide driver errors.

**Exercise D — Change Boot version:** Compare the Javadoc of 3.3 and 3.4, noting default `ANY` vs. `NON_TEST`. Explain why `Replace.NON_TEST` does not exist in 3.3 and why the exact same `@DataJpaTest` + Testcontainers setup can pick a different DB after upgrading.

**Exercise E — Test vendor-specific behavior:** Create a repository test using PostgreSQL's `jsonb` type or a native query. Run it on PostgreSQL Testcontainers and compare against H2; analyze the differences instead of relying on H2 compatibility mode to claim the two engines behave identically.

**Exercise F — Ensure isolation:** In a JPA slice test, add a test that inserts an entity and rolls back. Verify that the next test does not see the entity due to fixture independence; explain why rollback still does not protect against connecting to the wrong production DB or running DDL migrations against real infrastructure.

**Exercise G — Multiple DataSources:** In a test context with primary and audit datasources, inspect the URL of each bean via qualifiers. Change the primary policy and confirm the audit URL was not unintentionally replaced.

## 16. Pre-Merge Database Test Checklist

- [ ] Do I know the exact Spring Boot version and which `Replace` enum values exist?
- [ ] Is the test using `@DataJpaTest`/`@JdbcTest` or full `@SpringBootTest`?
- [ ] Is the goal basic SQL, JPA mapping, or production database engine behavior?
- [ ] Did I choose an explicit policy: `ANY`, `AUTO_CONFIGURED`, `NONE`, or `NON_TEST` when supported?
- [ ] If using Testcontainers in Boot 3.3, did I prevent unwanted replacement with `Replace.NONE`?
- [ ] Is the H2/HSQLDB/Derby driver on test runtime when expecting embedded replacement?
- [ ] If `replace=NONE`, do the test DataSource URL, credentials, and DB server stay **safe and isolated from production**?
- [ ] Do I have at least one **runtime DataSource** verification when DB infrastructure is part of the goal?
- [ ] Did I distinguish `connection=NONE` from `replace=NONE`?
- [ ] With multiple DataSources, did I avoid assuming the annotation replaces all beans?
- [ ] Are migrations/transactions/data cleanup appropriate for the engine and test slice?
- [ ] Does the test avoid production passwords or giving CI access to production DBs?
- [ ] Do assertions verify actual business/query contracts, not just "can connect"?
- [ ] Does the Gradle/JUnit report confirm tests actually ran, rather than `UP-TO-DATE`?

## 17. Official References

The official Spring Boot sources below are for verifying **your exact version**. Consult the documentation matching your project's dependencies before changing policies in a real repository.

- [Spring Boot 3.3 — AutoConfigureTestDatabase API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html): default **ANY** policy, `connection` choices, and primary `DataSource` scope limit.
- [Spring Boot 3.3 — Replace API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html): `ANY`, `AUTO_CONFIGURED`, `NONE`.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@DataJpaTest`, `@JdbcTest`, keeping a real database with `Replace.NONE`.
- [Spring Boot 3.4 — Replace API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html): addition of `NON_TEST` and test database detection logic.
- [Spring Boot 3.4 — Testcontainers](https://docs.spring.io/spring-boot/3.4/reference/testing/testcontainers.html): `@ServiceConnection`, `@DynamicPropertySource`, and using container tests.
- [Spring Boot 3.4 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes): test database replacement policy changes reducing the need for `replace=NONE` with containers.

**Remember:** `@AutoConfigureTestDatabase` is the **DataSource replacement policy in the test context**. `ANY` can swap the configured datasource to an embedded DB; `NONE` preserves the specified datasource without **automatically making it safe**; `AUTO_CONFIGURED` scopes strictly by bean origin; `NON_TEST` (Boot 3.4+) preserves auto-configured datasources recognized as test DBs. Always **verify the actual database in use**, especially when tests must run on PostgreSQL/MySQL or in systems with multiple DataSources.
