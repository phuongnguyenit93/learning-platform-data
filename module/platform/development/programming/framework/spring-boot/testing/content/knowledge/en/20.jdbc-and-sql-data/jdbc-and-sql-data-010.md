# Choosing a Slice or Full Context to Verify Actual DataSource Configuration

## Learning Objectives

In a JDBC/Spring Boot test, confirming that a `DataSource` exists and `SELECT 1` succeeds **is not enough** to prove the application connects to the intended database and connection pool. Specifically, `@JdbcTest` and `@DataJpaTest` have mechanisms to create or replace the DataSource for the test slice. In Spring Boot 3.3, that mechanism commonly picks an embedded database even when test properties declare a different JDBC URL.

This lesson belongs to the **JDBC and SQL data** branch of the **Spring Boot – testing** module, focusing on one practical decision: **when to choose a test slice, when to choose a full ApplicationContext, and what evidence to gather to verify the actual DataSource in use**.

After this lesson, you will be able to:

- Distinguish `@JdbcTest`, `@DataJpaTest`, `@DataJdbcTest`, and `@SpringBootTest`.
- Explain why `@JdbcTest` may use H2 instead of the database declared in properties.
- Choose `@AutoConfigureTestDatabase` policies (`Replace.ANY`, `AUTO_CONFIGURED`, `NONE`) and understand the addition of `NON_TEST` starting in Spring Boot 3.4.
- Distinguish the three layers of evidence: **Environment property → DataSource bean → runtime JDBC Connection**.
- Inspect actual database metadata with `Connection.getMetaData()`, DataSource type, and Hikari pool configuration.
- Write a Java 17 / Spring Boot 3.3.5 / Gradle project with three test groups: slice replacing the DataSource, slice preserving the DataSource, and full context with HikariCP.
- Know when to use Testcontainers/PostgreSQL for questions involving production database engines, migrations, or native SQL.
- Handle custom DataSources, multiple DataSources, `@Primary`, routing, test profiles, and dynamic configuration.
- Avoid connecting to production, leaking secrets, or leaving hard-to-clean data behind in CI.

**Main takeaway:** When proving which DB the application actually connects to, **never assert only `spring.datasource.url`**. Open a `Connection` from the **exact DataSource the application uses**, inspect JDBC metadata, and run appropriate SQL/schema checks.

## 1. What Actually Is a DataSource?

`javax.sql.DataSource` is the interface for obtaining JDBC connections. In a Spring Boot application, the `DataSource` bean can be:

- `HikariDataSource` auto-configured by Boot from `spring.datasource.*` and `spring.datasource.hikari.*`.
- An embedded DataSource for H2, HSQLDB, or Derby.
- A manually defined `@Bean DataSource`.
- `LazyConnectionDataSourceProxy` or `TransactionAwareDataSourceProxy`.
- `AbstractRoutingDataSource` routing by tenant, read/write role, or thread context.
- Multiple DataSources: orders, audit, reporting, read replicas.
- A DataSource created from Testcontainers connection details or an external secrets source.

Example properties:

~~~properties
spring.datasource.url=jdbc:postgresql://db.example.internal:5432/shop
spring.datasource.username=shop_app
spring.datasource.password=...
spring.datasource.hikari.maximum-pool-size=12
~~~

**This is an illustrative configuration, not a runnable configuration for this lesson.** Never copy production passwords into tests. Having this file present or readable via `Environment` does not guarantee that the injected `DataSource` actually connects to that URL.

Configuration flow:

~~~text
application.yml / application-test.yml / environment variables
             |
             v
 Spring Environment, configuration properties
             |
             v
 DataSourceAutoConfiguration / custom @Bean
             |
             +---- test database replacement (if enabled)
             |
             v
 DataSource bean: Hikari / embedded / custom / proxy
             |
             v
 dataSource.getConnection()
             |
             v
 Real JDBC Driver + Server/Database
             |
             +-- Connection.getMetaData().getURL()
             +-- Connection.getMetaData().getDatabaseProductName()
             +-- SQL verifying schema / database-specific behavior
~~~

Three observation layers:

| Layer | How to Check | What It Proves |
| --- | --- | --- |
| Declared value | `environment.getProperty("spring.datasource.url")` | Property value inside `Environment` |
| Injected bean | `DataSource` type, Hikari pool properties, qualifiers | Wiring/pool type if unwrapped |
| Real connection | `Connection.getMetaData()` and executed SQL | Engine/URL/schema/behavior at connection time |

Checking only the first layer misses **embedded replacement**. Checking only the pool type still leaves the target address unproven. Checking only `SELECT 1` leaves schema/migrations and tenant routing unverified.

## 2. Choosing a Test Slice vs. Full Context

Test slices intentionally bootstrap a narrow subset of the application to reduce startup cost and isolate the layer under test. A full context loads broader application configuration and may pull in unrelated integrations.

| Annotation | Primary Scope | DataSource Behavior |
| --- | --- | --- |
| `@JdbcTest` | JDBC infrastructure, `JdbcTemplate`, SQL | Includes test database auto-configuration/replacement, typically embedded DB |
| `@DataJpaTest` | Entities, Spring Data JPA repositories, Hibernate, `TestEntityManager` | Usually embedded DB; transactional/rollback by default |
| `@DataJdbcTest` | Spring Data JDBC repositories | Similar test DB mechanism |
| `@JooqTest` | jOOQ/`DSLContext` | Check annotation and auto-config per exact version |
| `@WebMvcTest` | MVC controllers and request binding | Not for proving connection pool/JDBC setup |
| `@SpringBootTest` | Broader Spring application configuration | Does not apply JDBC/JPA slice replacement policy by default |
| Plain JUnit unit test | Java logic | No Spring context or DataSource needed |

### When to Use `@JdbcTest`

- You want to prove a query through `JdbcTemplate` or `NamedParameterJdbcTemplate` returns the expected data.
- You are verifying `RowMapper`, JDBC exception translation, and standard SQL.
- You do not need the web server, security, messaging, caches, or business services.
- You accept an embedded DB because SQL/query behavior does not depend on engine-specific features, **or** you explicitly preserve a Testcontainers DataSource using `Replace.NONE`.

### When to Use `@DataJpaTest`

- You want to verify repository methods, entity mappings, JPQL, transactions, and Hibernate behavior.
- You have entity fixtures and need `EntityManager` or `TestEntityManager`.
- You understand persistence context flush/clear and test slice rollback.
- If native SQL/migrations target PostgreSQL, you test on the real engine instead of H2 alone.

### When to Use `@SpringBootTest`

- You need to know whether real application `@Configuration` classes load a custom DataSource.
- You want to verify `@Primary`, `@Qualifier`, custom routing, connection pool properties, or app-wide transaction managers.
- You want to protect how config, profiles, connection details, and migrations wire together.
- You need to test a multi-layer integration flow, accepting longer startup times.

**You do not need an HTTP port just to test a DataSource.** `@SpringBootTest(webEnvironment = NONE)` still loads the full non-web Spring ApplicationContext. Use `RANDOM_PORT` only when the test scope includes the HTTP server, networking, or server-side transactions.

## 3. Why Can a Test Slice Swap the Database?

In Spring Boot 3.3, `@JdbcTest` and `@DataJpaTest` include `@AutoConfigureTestDatabase` to avoid accidentally hitting the app's configured database when testing only the data layer. When H2/HSQLDB/Derby drivers are present, Spring Boot can create an embedded test DB and replace the configured DataSource.

Example:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/order_test
~~~

~~~java
@JdbcTest
class OrderJdbcTest {
    // ...
}
~~~

These are two illustrative snippets, not a standalone runnable project. With Boot 3.3 and an embedded driver present, the DataSource inside `OrderJdbcTest` **can be H2**, not PostgreSQL. `Environment.getProperty(...)` still reports the PostgreSQL URL, while JDBC metadata fetched from the connection reports `H2`.

### `Replace` Policies in Spring Boot 3.3

~~~java
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY)
~~~

| Policy | Meaning |
| --- | --- |
| `ANY` | Replaces the DataSource whether auto-configured or manually defined; **default in Boot 3.3** |
| `AUTO_CONFIGURED` | Replaces only a DataSource created by Spring Boot auto-configuration |
| `NONE` | **Does not replace** the configured DataSource |
| `NON_TEST` | **Does not exist in Boot 3.3**; introduced in Boot 3.4 |

Starting in **Spring Boot 3.4+**, `Replace.NON_TEST` was added and became the new default, preserving many auto-configured DataSources that Boot recognizes as **test DBs** (such as Testcontainers metadata, `@DynamicPropertySource`, or `jdbc:tc` depending on version conditions). Do not write `Replace.NON_TEST` in a Boot 3.3 project because it will not compile.

When the requirement is **"do not swap out the DataSource chosen for the test"**, `Replace.NONE` expresses that intent clearly in both 3.3 and newer releases. However, it **does not** verify the DB is safe: if the active URL points to production, tests can connect to real production.

### `connection = H2` Differs from `replace = NONE`

~~~java
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.ANY,
    connection = EmbeddedDatabaseConnection.H2)
~~~

- `replace` controls **whether to replace the DataSource**.
- `connection` controls **which embedded engine to use when replacing**.
- `EmbeddedDatabaseConnection.NONE` means do not force a specific embedded engine; it **does not mean `Replace.NONE`**.
- Using H2 during replacement requires the H2 JDBC driver on the test runtime classpath.
- Requesting embedded replacement without an embedded driver on the classpath can cause context startup to fail.

With multiple DataSources, test database replacement per Spring Boot 3.3 Javadoc **considers only the `@Primary DataSource`**, rather than replacing every datasource bean. Thus, an application with a separate audit datasource must test and guard it separately instead of assuming one slice test makes all datasources safe.

## 4. Designing Evidence Around the Goal

Before writing code, state the exact question you want to answer:

| Question | Minimum Evidence |
| --- | --- |
| Is the DataSource created? | `@Autowired DataSource` and opening a connection |
| Is the DB H2 or PostgreSQL? | `DatabaseMetaData.getDatabaseProductName()` |
| Is it the right database name/URL? | `DatabaseMetaData.getURL()` after sanitization |
| Did test replacement swap the URL? | Compare configured URL against runtime URL |
| Did Hikari properties bind? | Inspect the actual Hikari bean (`getMaximumPoolSize()`) |
| Can `JdbcTemplate` execute on it? | SQL query with an independent expected result |
| Are schema/migrations applied? | Query actual tables/migration versions/constraints |
| Are custom services/configs loaded? | Assert bean presence/config behavior in full context |
| Are there multiple DataSources? | Inject each bean via `@Qualifier`, check metadata on each connection |
| Is the test using the right container DB? | Assert product name + runtime URL + vendor-specific behavior |

A test with only `assertNotNull(dataSource)` or `SELECT 1` passes on almost any DB. It is a smoke check, **not a substitute** for the validation you actually need.

## 5. Runnable Java 17 + Spring Boot 3.3.5 Project

The example uses in-memory H2 so it runs **without Docker, an external database server, or external services**. We intentionally create three contexts:

1. **JDBC slice replacing the DB:** configures URL `configured_slice`, while `Replace.ANY` forces embedded replacement.
2. **JDBC slice preserving the DB:** configures URL `kept_slice` with `Replace.NONE`.
3. **Full context:** uses URL `full_context_db`, Hikari pool size 3, and loads a real application `@Service`.

Then we compare the JDBC metadata of each context. **All three databases are H2**, cleanly isolating the replacement and scope mechanics. A later section extends to PostgreSQL Testcontainers for verifying a real engine.

### 5.1. File Structure

~~~text
datasource-test-scope/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/datasource/
    │   ├── DataSourceApplication.java
    │   └── ApplicationMarker.java
    └── test/java/com/example/datasource/
        ├── JdbcSliceReplacementTest.java
        ├── JdbcSlicePreservationTest.java
        └── FullContextDataSourceTest.java
~~~

The Gradle Wrapper consists of scripts and a binary JAR that must be generated from a matching Gradle installation or copied from the repo. Never try to author `gradle-wrapper.jar` as a text file.

**`settings.gradle`**

~~~groovy
rootProject.name = 'datasource-test-scope'
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

Explanation:

- `spring-boot-starter-jdbc` brings JDBC infrastructure, `JdbcTemplate`, transaction support, and HikariCP by default.
- H2 sits in `testRuntimeOnly`, keeping the embedded driver out of the demo's production runtime module.
- `spring-boot-starter-test` brings JUnit Jupiter, Spring TestContext, and test slices.
- The Spring Boot BOM manages compatible H2/JUnit/JDBC versions.
- `useJUnitPlatform()` tells Gradle to run JUnit Jupiter.

**`src/main/java/com/example/datasource/DataSourceApplication.java`**

~~~java
package com.example.datasource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DataSourceApplication {

    public static void main(String[] args) {
        SpringApplication.run(DataSourceApplication.class, args);
    }
}
~~~

This is the app's root configuration. The project lacks a production DataSource URL/driver to run `bootRun` as a real deployment; **the task designed to run is `test`** with H2 on the test classpath.

**`src/main/java/com/example/datasource/ApplicationMarker.java`**

~~~java
package com.example.datasource;

import org.springframework.stereotype.Service;

@Service
public class ApplicationMarker {

    public String identity() {
        return "full-application";
    }
}
~~~

`ApplicationMarker` is a simple service that does not touch the DB. It demonstrates **component scanning**: the JDBC slice excludes ordinary services, whereas the full application context loads them.

## 6. Test A — `@JdbcTest` Replacing the DataSource

**`src/test/java/com/example/datasource/JdbcSliceReplacementTest.java`**

~~~java
package com.example.datasource;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.jdbc.EmbeddedDatabaseConnection;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JdbcTest(properties = {
    "spring.datasource.url="
        + "jdbc:h2:mem:configured_slice;DB_CLOSE_DELAY=-1"
})
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.ANY,
    connection = EmbeddedDatabaseConnection.H2)
class JdbcSliceReplacementTest {

    @Autowired
    private DataSource dataSource;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private Environment environment;

    @Autowired
    private ApplicationContext context;

    @Test
    void declaredUrlDiffersFromEffectiveConnection()
            throws SQLException {

        String declared = environment.getProperty(
                "spring.datasource.url");

        assertEquals(
                "jdbc:h2:mem:configured_slice;DB_CLOSE_DELAY=-1",
                declared);

        try (Connection connection = dataSource.getConnection()) {
            String actual = connection.getMetaData().getURL();

            assertTrue(actual.startsWith("jdbc:h2:mem:"), actual);
            assertFalse(actual.contains("configured_slice"), actual);
            assertEquals(
                    "H2",
                    connection.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void replacementDataSourceRunsSql() {
        Integer result = jdbcTemplate.queryForObject(
                "SELECT 2 + 3", Integer.class);

        assertNotNull(result);
        assertEquals(5, result.intValue());
    }

    @Test
    void unrelatedServiceIsExcludedFromJdbcSlice() {
        assertTrue(
                context.getBeansOfType(ApplicationMarker.class)
                        .isEmpty());
    }
}
~~~

**What Test A proves:**

1. `Environment` still reports the declared URL `configured_slice`.
2. JDBC metadata of the **actual DataSource** starts with `jdbc:h2:mem:` yet **does not contain** `configured_slice`.
3. The actual connection's engine is H2.
4. `JdbcTemplate` executes SQL over the injected connection.
5. Application services outside the JDBC slice are not auto-scanned.

The Spring-generated embedded DB name can vary, so **never hardcode** the generated database name. Assert only the essential invariant: it is **not the originally declared database**.

If you switch `Replace.ANY` to `Replace.NONE`, the first test must fail at `assertFalse(actual.contains("configured_slice"))`, because the runtime retains the configured URL. That is a valuable mutation check proving the assertions genuinely catch DataSource replacement policy changes.

## 7. Test B — `@JdbcTest` Preserving the DataSource

**`src/test/java/com/example/datasource/JdbcSlicePreservationTest.java`**

~~~java
package com.example.datasource;

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
        + "jdbc:h2:mem:kept_slice;DB_CLOSE_DELAY=-1"
})
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
class JdbcSlicePreservationTest {

    @Autowired
    private DataSource dataSource;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void effectiveUrlMatchesConfiguredTestDatabase()
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            String actual = connection.getMetaData().getURL();

            assertTrue(
                    actual.startsWith("jdbc:h2:mem:kept_slice"),
                    actual);
            assertEquals(
                    "H2",
                    connection.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void keptDataSourceStillExecutesSql() {
        Integer result = jdbcTemplate.queryForObject(
                "SELECT 4 + 5", Integer.class);

        assertNotNull(result);
        assertEquals(9, result.intValue());
    }
}
~~~

**Differences from Test A:**

- `Replace.NONE` disables **test database replacement**; it does not turn H2 into PostgreSQL.
- The test still uses H2 because **the properties themselves declared H2**.
- The runtime JDBC URL retains `kept_slice`.
- Even without replacement, it remains a JDBC slice: application services do not appear automatically because `NONE` does not alter component scanning.

Common trap: some developers read "NONE" and think "do not use an embedded database". In fact, `NONE` means only **do not replace the DataSource**; if the configured DataSource is H2, it remains H2.

## 8. Test C — `@SpringBootTest` Verifying the Full Application Context

**`src/test/java/com/example/datasource/FullContextDataSourceTest.java`**

~~~java
package com.example.datasource;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import com.zaxxer.hikari.HikariDataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    classes = DataSourceApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.datasource.url="
            + "jdbc:h2:mem:full_context_db;DB_CLOSE_DELAY=-1",
        "spring.datasource.username=sa",
        "spring.datasource.password=",
        "spring.datasource.hikari.maximum-pool-size=3"
    })
class FullContextDataSourceTest {

    @Autowired
    private DataSource dataSource;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private ApplicationMarker marker;

    @Test
    void effectiveUrlMatchesFullContextConfig()
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            String actual = connection.getMetaData().getURL();

            assertTrue(
                    actual.startsWith("jdbc:h2:mem:full_context_db"),
                    actual);
            assertEquals(
                    "H2",
                    connection.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void hikariPropertyIsAppliedToActualPoolBean() {
        HikariDataSource pool =
                assertInstanceOf(HikariDataSource.class, dataSource);

        assertEquals(3, pool.getMaximumPoolSize());
    }

    @Test
    void applicationServiceIsLoadedInFullContext() {
        assertEquals("full-application", marker.identity());
    }

    @Test
    void jdbcTemplateCanExecuteAgainstFullContextDataSource() {
        Integer result = jdbcTemplate.queryForObject(
                "SELECT 7 + 8", Integer.class);

        assertNotNull(result);
        assertEquals(15, result.intValue());
    }
}
~~~

**What Test C proves:**

- `@SpringBootApplication` loaded the full non-web `ApplicationContext`.
- `DataSource` connects to the exact H2 URL `full_context_db`.
- `HikariDataSource` is the real bean in the **demo project** (`starter-jdbc` without a custom bean).
- `spring.datasource.hikari.maximum-pool-size=3` was bound and applied.
- `ApplicationMarker` was component-scanned into the full context.
- `JdbcTemplate` executes SQL cleanly.

Not every app using `@SpringBootTest` exposes `HikariDataSource` directly: custom DataSources, proxies, routing wrappers, or other pools can make a direct `instanceof` check fail. We use it here because **the lesson specifically tests Hikari binding in the demo's default configuration**.

### Why Use `webEnvironment = NONE`?

We are not testing HTTP endpoints. `SpringBootTest.WebEnvironment.NONE` loads the application's config beans without starting a web server. To test HTTP + JDBC transaction commits across POST/GET, use `RANDOM_PORT` and an HTTP client alongside explicit cleanup, since server threads run in transactions separate from the test thread.

## 9. Executing the Test Suite and Expected Outcomes

| Class | Test Methods | Purpose |
| --- | ---: | --- |
| `JdbcSliceReplacementTest` | 3 | Property differs from runtime DB, embedded SQL, slice scope |
| `JdbcSlicePreservationTest` | 2 | URL preserved and JDBC query runs |
| `FullContextDataSourceTest` | 4 | Full app wiring, real URL, Hikari settings, service |
| **Total** | **9** | Three separate contexts |

In the directory with Gradle Wrapper and JDK 17:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run each class individually:

~~~bash
./gradlew test --tests 'com.example.datasource.JdbcSliceReplacementTest'
./gradlew test --tests 'com.example.datasource.JdbcSlicePreservationTest'
./gradlew test --tests 'com.example.datasource.FullContextDataSourceTest'
~~~

**Expect all 9 JUnit tests to pass** when sources and dependencies match. This is the expected result from the code, not a run observed on the learner's machine. There is no `System.out.println`, so no fixed business stdout exists; Gradle may print `BUILD SUCCESSFUL` or reuse its test task cache.

To force re-execution:

~~~bash
./gradlew test --rerun-tasks
~~~

Typical JUnit reports:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.datasource.JdbcSliceReplacementTest.xml
    ├── TEST-com.example.datasource.JdbcSlicePreservationTest.xml
    └── TEST-com.example.datasource.FullContextDataSourceTest.xml
~~~

When no Wrapper exists yet, a compatible installed Gradle can generate one:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Then commit `gradlew`, `gradlew.bat`, Wrapper properties, and the Wrapper JAR per team convention. On an existing project, prefer the team's Gradle Wrapper instead of changing its version to match a tutorial.

### Expected Runtime Summary Table

~~~text
JdbcSliceReplacementTest
  Environment URL: jdbc:h2:mem:configured_slice;...
  Replace.ANY + EmbeddedDatabaseConnection.H2
  Runtime URL:     jdbc:h2:mem:<generated-name>...
  Runtime Engine:  H2
  ApplicationMarker bean: absent

JdbcSlicePreservationTest
  Environment URL: jdbc:h2:mem:kept_slice;...
  Replace.NONE
  Runtime URL:     jdbc:h2:mem:kept_slice;...
  Runtime Engine:  H2

FullContextDataSourceTest
  Environment URL: jdbc:h2:mem:full_context_db;...
  Full app context, no slice replacement
  Runtime URL:     jdbc:h2:mem:full_context_db;...
  Runtime Engine:  H2
  DataSource type: HikariDataSource (in this project)
  Hikari maxPool:  3
  ApplicationMarker bean: present
~~~

The `<generated-name>` token is an **explanatory model placeholder**, not a hardcoded database name in tests or fixed stdout.

## 10. Why Reading Only `Environment` Gives False Confidence

In practice, test properties can come from many sources simultaneously:

- `application.yml` and `application-test.yml`.
- `@ActiveProfiles("test")`.
- Inline test properties on `@SpringBootTest`/`@JdbcTest`.
- `@TestPropertySource`.
- Environment variables, system properties, command-line options.
- `@DynamicPropertySource` from Testcontainers.
- `@ServiceConnection` connection details from a container.
- Custom beans reading a prefix other than `spring.datasource`.
- `@AutoConfigureTestDatabase` replacing the bean during test bootstrap.

Example:

~~~java
@ActiveProfiles("test")
@SpringBootTest
class DatabaseSmokeTest {
    // ...
}
~~~

This is an illustrative snippet. The `test` profile loads test config, yet **it does not guarantee the URL is safe or that the active DataSource uses that file**. If a custom DataSource pulls its URL elsewhere or slice replacement kicks in, inspecting a single `application-test.yml` value is insufficient.

Some tests write:

~~~java
assertEquals(
    "jdbc:postgresql://localhost:5432/shop_test",
    environment.getProperty("spring.datasource.url"));
~~~

That assertion can pass even when the real DataSource was replaced with H2. Pair it with:

~~~java
try (Connection connection = dataSource.getConnection()) {
    assertEquals(
        "PostgreSQL",
        connection.getMetaData().getDatabaseProductName());
}
~~~

This snippet assumes `dataSource` and imports are in a safely configured context. If the contract also requires a specific schema, verify real SQL against that schema as well.

### `DataSourceProperties` Is Not Final Proof Either

`DataSourceProperties` holds bound/inferred configuration for creating a datasource, yet not every custom bean or wrapper uses it. Confirming the property object has the right URL **does not prove** repository/`JdbcTemplate` connections actually go there.

A reliable verification path is:

1. Identify the exact `DataSource` bean used by the component under test.
2. Open a connection from that bean.
3. Verify engine and URL/schema/catalog per contract.
4. Execute meaningful SQL.
5. Close the connection without logging secrets.

## 11. Checking Connection Metadata Safely

A test helper might look like:

~~~java
private void assertDatabaseEngine(
        DataSource dataSource, String expected)
        throws SQLException {

    try (Connection connection = dataSource.getConnection()) {
        assertEquals(
                expected,
                connection.getMetaData().getDatabaseProductName());
    }
}
~~~

This is a helper method snippet inside a test class requiring JUnit and JDBC imports. `getDatabaseProductName()` confirms the engine reported by the JDBC driver. `getURL()` reports the metadata JDBC URL; because it can contain query parameters or internal endpoints, **sanitize** it before logging in CI.

### When Checking Database/Schema Matters More Than URL

For PostgreSQL, inside a dedicated test context:

~~~sql
SELECT current_database(), current_schema()
~~~

For MySQL, use the equivalent dialect functions. This is illustrative SQL, **not executed in the H2 demo project**. Only use it in tests targeting that known engine/driver. Connections routed through a proxy or load balancer can report the proxy's URL rather than the backend instance; database/schema query results and migration tables often provide better evidence.

### Distinguishing Pool Properties from Connection Properties

- `HikariDataSource.getMaximumPoolSize()` inspects the Hikari bean's pool configuration.
- `Connection.getMetaData()` inspects metadata of the DB connection.
- `Connection.isReadOnly()` reflects a connection's read-only flag; it does not prove replica routing or database transaction isolation.
- `DataSource.getLoginTimeout()` does not prove SQL query timeouts or network socket behavior.
- `JdbcTemplate.queryForObject(...)` proves query execution, not that all tables and migrations exist.

Match each assertion to its exact goal instead of writing one giant test that blurs which layer failed.

## 12. Testcontainers When a Real Database Engine Is Needed

The H2 demo does not exercise native PostgreSQL SQL or driver behavior. When you need:

- `jsonb`, arrays, enums, UUIDs, `ILIKE`, `ON CONFLICT`, `RETURNING`.
- Transaction isolation/locking or specific collations.
- PostgreSQL/MySQL Flyway/Liquibase migrations.
- Native SQL with real indexes and constraints.
- Connection pool behavior with the PostgreSQL JDBC driver.

use **PostgreSQL Testcontainers** or an equivalent test DB.

### Additional Dependencies in Boot 3.3

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}
~~~

This is a **snippet added to an existing Spring Boot/JDBC project**, not a standalone build. It requires a compatible Docker/container runtime and permission to run the Postgres image on CI.

### `@JdbcTest` with a Container: Preserving the DataSource in Boot 3.3

~~~java
@JdbcTest
@Testcontainers
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
class PostgresJdbcSliceTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    private DataSource dataSource;

    @Test
    void confirmsPostgresNotAccidentalH2() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            assertEquals(
                    "PostgreSQL",
                    connection.getMetaData().getDatabaseProductName());
        }
    }
}
~~~

**This snippet is not a standalone compilable class**: add Spring Boot/JUnit/Testcontainers imports, dependencies, and schemas/fixtures when running domain queries. It illustrates the core setup: the container starts, `@ServiceConnection` provides connection details, and `Replace.NONE` stops the test slice from replacing Postgres with H2.

In Boot **3.3**, `Replace.NONE` is especially critical because the slice defaults to `Replace.ANY`. Boot 3.4+ adds `NON_TEST` which recognizes many test databases, yet when the goal is **guaranteeing the container stays intact**, `NONE` remains explicit.

### `@DynamicPropertySource` Is Another Option

~~~java
@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

This snippet uses the declared `postgres` field. In Boot 3.3 with `@JdbcTest`, even when `Environment` has the exact dynamic JDBC URL, **embedded replacement still occurs** unless the right replacement policy is set. Avoid combining both `@ServiceConnection` and dynamic properties for the same goal unnecessarily.

### With Full Context

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Testcontainers
class PostgresFullContextTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // @Autowired DataSource...
    // Assert PostgreSQL metadata, schema and migration.
}
~~~

This is an architectural snippet requiring a full test class/config. `@SpringBootTest` does not enable slice embedded replacement by default, yet you should still **inspect the runtime connection** — starting a container does not prove an app's custom DataSource actually connected to it.

### When Migrations Are Present

A `SELECT 1` test on PostgreSQL proves only that the driver and connection work. If the goal is "production migrations apply cleanly", run the real schema migrations against the test DB and assert tables, columns, constraints, and versions. A test using Hibernate `ddl-auto=create-drop` can stay green **even when production migration SQL is broken**, so never mistake that for migration verification.

## 13. Custom DataSources and Out-of-Slice `@Configuration`

Suppose the application has custom configuration:

~~~java
@Configuration
class DbConfig {

    @Bean
    DataSource customizedDataSource() {
        // Build custom pool from dedicated config.
    }
}
~~~

This is an illustrative snippet, not standalone compilable code. `@JdbcTest` may skip scanning this config/bean if it lies outside slice scan scope, and `Replace.NONE` **does not automatically add missing beans**. Two sound options:

- Use `@Import(DbConfig.class)` in a targeted test slice when testing JDBC specifically with that config.
- Use `@SpringBootTest(NONE)` when guarding **the real application's wiring**.

Importing into a slice intentionally widens that context. The result protects **that imported context**, not necessarily every component in production. Do not treat it as a full context just because you added one `@Configuration`.

### Multiple DataSources: `@Primary`, `@Qualifier`, and Routing

~~~java
@Configuration
class MultiDbConfig {

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

Architectural snippet; needs method bodies and imports to run. When an application has multiple DataSources, `@Primary` selects the default candidate while `@Qualifier("auditDataSource")` targets the secondary bean.

Autowiring just `DataSource` and checking one connection inspects only the **primary path**. Other `JdbcTemplate`s or Spring Data repositories may bind to the audit/reporting datasource via qualifiers or separate transaction managers.

A robust test should:

- Inject each datasource bean by name/qualifier.
- Open connections and verify metadata on **each actual source**.
- Verify the DataSource used by specific repositories/`JdbcTemplate`s, not merely that beans exist.
- If using `AbstractRoutingDataSource`, set the tenant/route context properly before opening a connection and test multiple routes.
- Never assume test database replacement applies to **every** DataSource in the context.

### Proxy DataSources and Hikari

`LazyConnectionDataSourceProxy`, `TransactionAwareDataSourceProxy`, or routing wrappers will not be `HikariDataSource` directly when injected, even when backed by a Hikari pool. Therefore:

- If the goal is **connection target**, inspect JDBC metadata/SQL.
- If the goal is **pool configuration**, unwrap or access the underlying Hikari target bean via supported APIs.
- If the goal is **app transactions/routing**, verify behavior inside the proper context.

In our runnable project, there are no custom wrappers, so asserting the Hikari type directly is both valid and meaningful.

## 14. Transactions in Slices vs. Full Context

`@JdbcTest` is normally configured as transactional and rolls back DML after each method. `@DataJpaTest` includes a JPA persistence context and rolls back by default. `@SpringBootTest` does not make tests transactional automatically, and HTTP calls to a real server run on server threads/transactions.

| Case | What to Remember |
| --- | --- |
| JDBC slice calls `jdbcTemplate.update` on test thread | Normally joins test transaction and rolls back |
| JPA slice calls `repository.save` | May need `flush/clear` to verify DB round-trip |
| Full context test runs direct JDBC without `@Transactional` | DML may commit per auto-commit/transaction scope |
| `@SpringBootTest(RANDOM_PORT)` sends HTTP POST | Server transaction can commit independently; test rollback won't delete it |
| DataSource metadata test | Only opens/closes a connection without writing data |
| Testcontainers shared across methods | Container does not reset DB state automatically between methods |

**Do not slap `@Transactional` onto every test thinking it makes them "safe"**. With a real HTTP server, a transaction on the JUnit thread cannot roll back server-committed rows. For cleanup, use test markers/IDs, well-understood rollbacks, independent cleanup transactions, or isolated schemas/containers.

### Why Do Metadata-Only Tests Need No Fixtures?

In our sample project, all SQL queries are `SELECT 2+3`, `SELECT 4+5`, and `SELECT 7+8`. They create no tables, insert nothing, and delete nothing. That keeps the suite focused on **DataSource configuration** without needing complex cleanup strategies.

When testing repositories or schemas as well, add purposeful fixtures at the appropriate test level rather than overloading configuration tests with business logic.

## 15. Staying Safe with Real Databases

`Replace.NONE` is not a security boundary. Enforce independent safeguards:

1. **Test-only** databases/containers; never use production credentials.
2. CI networks must have no route to production DBs unless explicitly authorized.
3. Grant test users least privilege, especially around DDL/DELETE/TRUNCATE.
4. Assert runtime engine and test database/schema markers prior to destructive actions.
5. Never print usernames, passwords, tokens, or full secret-bearing URLs to logs.
6. Never truncate/wipe shared tables in cleanup just to "keep tests clean".
7. Use `testRunId`/tenant schemas/resource IDs when suites run in parallel.
8. Configure TTLs/container teardown if a test process dies before `@AfterEach`.
9. When `@SpringBootTest` boots the full context, ensure external integrations (email, billing, queues) point to sandboxes/fakes.
10. Manage credentials and test profiles via CI secrets, never committed to the repository.

**In-memory H2 is not the production engine.** It is ideal for basic SQL and learning replacement behavior, yet native SQL, locking, collations, and migrations can differ from PostgreSQL/MySQL. Whenever the goal requires the real engine, test on that engine.

## 16. Common Pitfalls

| Symptom | Common Cause | Solution |
| --- | --- | --- |
| `@JdbcTest` uses H2 despite PostgreSQL URL | Boot 3.3 replacement defaults to `ANY` | Use `Replace.NONE` and inspect runtime connection |
| `spring.datasource.url` matches yet queries hit another DB | Test replacement, custom bean, or routing | Inspect JDBC metadata on the actual bean |
| `Failed to replace DataSource with an embedded database` | Missing embedded JDBC driver | Add H2/HSQLDB/Derby test runtime or change policy |
| `Cannot determine a suitable driver class` | Incomplete driver/URL/connection details | Check test dependencies and properties |
| Custom DataSource missing in `@JdbcTest` | Slice does not scan that config | `@Import` or full context |
| `Replace.NONE` yet startup fails | No usable DataSource/driver configured | Configure real test DataSource, not just the annotation |
| Hikari type assertion fails in slice | Embedded replacement created a different pool | Assert engine/URL instead of Hikari if that is the goal |
| `HikariDataSource` cast fails in full context | Proxy/routing/custom DataSource | Unwrap target pool or inspect metadata |
| Hikari pool size mismatches | Custom bean does not bind `hikari` prefix | Check bean source and configuration prefix |
| PostgreSQL container runs yet app hits H2 | Test slice replacement | `Replace.NONE` in Boot 3.3; assert product name |
| H2 test passes, native Postgres SQL fails | Different dialect/schema | PostgreSQL Testcontainers |
| `@ActiveProfiles("test")` still points at wrong DB | Different property source or connection details | Check effective connection and safety allowlist |
| Full context test fails on external service | Loaded all beans/integrations | Use test-specific stubs or slices |
| Test pool runs out of connections | Forgot to close `Connection` | Use try-with-resources |
| SQL test passes yet schema migration fails | Tested only `SELECT 1` | Test real migrations and schema separately |
| JUnit rollback fails to remove server rows | Separate HTTP server transaction | Clean up server-committed data explicitly |
| Multiple DataSources, audit still hits prod | Only `@Primary` gets replaced/tested | Verify all qualified/routed DataSources |
| `Replace.NON_TEST` fails to compile | Not present in Spring Boot 3.3 | Use `NONE`/`ANY` appropriate for your Boot version |

### Debugging Workflow

1. Identify the Spring Boot version and exact test annotation.
2. Clarify the requirement: **query correctness, bean wiring, connection target, or pool config**.
3. Check `@AutoConfigureTestDatabase` and its replacement policy.
4. Check the test runtime classpath for the expected JDBC driver.
5. Verify test URL/credentials are safe before opening connections.
6. Inspect the actual `DataSource` bean (custom/primary/proxy/routing).
7. Open a connection from that bean and assert metadata and meaningful SQL.
8. If migrations matter, query the actual schema and migration version table.
9. Check transactions/rollback and cleanup when writing to the DB.
10. Read the real root cause, not just the outer `Failed to load ApplicationContext` wrapper.

## 17. Exercises

**Exercise A — Proving replacement:** Run `JdbcSliceReplacementTest`, then change `Replace.ANY` to `Replace.NONE`. Predict why `assertFalse(actual.contains("configured_slice"))` fails and explain it.

**Exercise B — Preserving URL:** In `JdbcSlicePreservationTest`, change the URL from `kept_slice` to `another_slice` without changing the expected value. The test must fail. Revert afterward.

**Exercise C — Hikari binding:** In `FullContextDataSourceTest`, change max pool size from 3 to 5 while keeping the assertion at 3. The test must fail, proving it catches config changes.

**Exercise D — Slice scanning:** Use `ApplicationMarker` to observe the service absent in `@JdbcTest` and present in full context. Try adding `@Import(ApplicationMarker.class)` to a new slice class and analyze why that intentionally widens the context.

**Exercise E — Profiles:** Create `application-test.yml` with a distinct H2 URL, enable `@ActiveProfiles("test")`, and inspect both `Environment` and the runtime URL. Add inline test properties to observe override precedence.

**Exercise F — PostgreSQL:** Use Testcontainers, `@JdbcTest` + `Replace.NONE` on Boot 3.3. Assert the PostgreSQL engine and a Postgres-specific query. Never point at a production DB.

**Exercise G — Migrations:** Create a table via a Flyway/Liquibase test migration and query the actual table. Explain why `SELECT 1`/metadata does not prove migrations succeeded.

**Exercise H — Multiple DataSources:** Define `orders` and `audit` DataSources with distinct H2 URLs. Inject via qualifiers and inspect metadata for each connection; never assume replacement applies to every bean.

**Exercise I — Transactions:** Write a JDBC slice test writing/reading inside the test transaction, and compare it with an HTTP integration test where the server commits separately. Implement cleanup scoped by test ID rather than `deleteAll()` on shared DBs.

**Exercise J — Connection leaks:** Open a connection and intentionally omit closing it in an isolated test with a tiny pool, observing the timeout. Fix it with try-with-resources. Never run overload experiments on a production DB.

## 18. Checklist Before Merging DataSource Tests

- [ ] Did I select a slice or full context based on a **specific goal** rather than habit?
- [ ] Do I know the Spring Boot version and default replacement policy of the test annotation?
- [ ] Do I distinguish `Replace.ANY`, `Replace.NONE`, `AUTO_CONFIGURED`, and `NON_TEST` (Boot 3.4+ only)?
- [ ] Did I avoid inferring the runtime DataSource solely from `spring.datasource.url` in `Environment`?
- [ ] Did I check JDBC metadata on the exact `DataSource`/qualifier/route?
- [ ] Did I verify engine/URL/schema per contract without logging secrets?
- [ ] If testing Hikari, did I access the actual pool bean and assert real settings?
- [ ] If using Testcontainers, did I confirm **the app actually uses the container**, not just that the container started?
- [ ] For vendor-specific SQL, did I run against the matching database engine?
- [ ] For migrations, did I verify the real schema rather than connectivity alone?
- [ ] Am I aware `@JdbcTest`/`@DataJpaTest` may skip out-of-slice services/configs?
- [ ] Did I avoid using `@DirtiesContext` in place of database cleanup?
- [ ] Are connections closed properly so tests do not leak pool connections?
- [ ] Are test profiles, credentials, and networks prevented from accidentally hitting production?
- [ ] Did I handle test data/transaction cleanup if the test writes rows?
- [ ] Does the Gradle/JUnit report show test methods actually ran, not confused with cached tasks?

## 19. Official References

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): test slices and `@SpringBootTest`.
- [Spring Boot 3.3 — AutoConfigureTestDatabase API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html): replacement, embedded connections, primary DataSource.
- [Spring Boot 3.3 — Replace API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html): `ANY`, `AUTO_CONFIGURED`, `NONE`.
- [Spring Boot 3.4 — Replace API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html): `NON_TEST` and test database cases.
- [Spring Boot 3.3 — SQL Databases](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html): `DataSource`, `JdbcTemplate`, Hikari, auto-configuration.
- [Spring Boot 3.3 — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): `@ServiceConnection` and connection details.
- [Spring Framework — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback of test-managed transactions.
- [HikariCP Documentation](https://github.com/brettwooldridge/HikariCP): connection pool configuration.

**Key takeaway:** `@JdbcTest` tests JDBC fast, yet it can **replace the DataSource** in the test context. `@SpringBootTest` tests full application configuration, yet is not automatically insulated from real DBs. Verify the exact **runtime connection**, exact **database engine/schema**, and exact **pool bean** whenever they form part of your contract. Choose the smallest test delivering sufficient evidence, and supplement with full-context/Testcontainers tests for critical integration wiring.